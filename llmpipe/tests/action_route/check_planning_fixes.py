"""The controller repairs K1 to K16 of the planning fixes (memos/TASK_2026_09_30_planning_fixes_opus.md) and the
two parser and controller repairs after the full run of 2026-10-02, offline.

Each repair is checked on the saved response that motivated it (regression/planning_2026_09_30_translations.json,
from the first run of the planning test set) and on the negative cases of its row: a repair whose condition fails
changes nothing, and the ordinary check decides.  Every applied repair is recorded with its kind, repair id, unit,
text before and after, and supporting units.

  K1   a plain denial under the reading restriction; not with unless or only, not when a condition is lost
  K2   a rule between two states under the reading effect; not with an effect marker or an actor
  K3   a verify role compared only as a declared concrete id; the concrete ids and the lexical result stay compared
  K4   ["ask", V, ["executable", ACTION]] with V in one entity slot; not in a lexical slot or outside the action
  K5   the omitted tool of a mention filled from its one permission; not with two tools, another value or its own tool
  K6   the unstated endpoints of a travel law bound at the head's scope; not with a stated endpoint, a variable used
       elsewhere, or in a supplied step
  K7   take of a standard travel mode in a travel law is a move; not take of an entity
  K8   a permission with no actor is existential, and the compiler's unsupported diagnosis follows
  K9   a clear anaphor merges two ids; the same index with another head noun is two entities; the same index and
       head noun without the anaphor is a Stage-1 correction
  K10  a misplaced @p equal to the derived probability, or to the convention confidence of an article, is dropped;
       another number or a response without a stop reason is not repaired
  K11  a law form accepted for a unit without a reading, and the route selection computed again; not without a
       capability action
  K12  the replay never raises: a default state rule gives not_checked, and an internal failure gives replay_error
  A2   Inconsistent: in English on the saved gpt row 100
  K13  the messages name the form that fits: the value slot, the actor slot, the query form of a reading, and a later
       mention with another value than its permission (asked once per unit; not when the sentence states the value)
  K14  after a correction that returned the same response, one focused request quotes only the failing packages and
       splices the reply in; nothing to quote, or a second repeat, stops as before
  K15  one clarification for method_collision and unsupported_law_form: a repeated translation, a reply with errors,
       no reply, a reply that changes a value no sentence states as a positive result of that operation on that
       object, and a reply that changes anything but result labels and the arrangement of a law keep the
       unsupported outcome with its reason; a valid supported reply within these limits is accepted
  K16  a dependency between states that Stage 1 types as a strict rule becomes state_law; the negative cases keep
       their form
  F1   (full run) a formula with a list where an operator stands is a structural error, not a crash (gpt 13)
  F2   (full run) a run of surplus closing brackets before a field of the action envelope is dropped (gemini); the
       other malformed responses of the saved runs are not repaired by it, and neither are the negative texts

F1 and F2 use regression/planning_2026_10_02_responses.json.  No model call (a fake provider returns the saved responses by request hash), no GK launch.
"""
import copy
import hashlib
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE]

import action_answer as aa              # noqa: E402

import action_english as aen
import action_pipeline as ap            # noqa: E402
import action_json as aj
import llmparse
import action_repair as arep            # noqa: E402
import action_replay as rp              # noqa: E402
import check_action_availability as cav  # noqa: E402

need = cav.need
SAVED = os.path.join(HERE, "regression", "planning_2026_09_30_translations.json")
FULL_RUN = os.path.join(HERE, "regression", "planning_2026_10_02_responses.json")
BUNDLE = ap.load_bundle(ap.DEFAULT_BUNDLE)


def rows():
  with open(SAVED) as f:
    return {(r["model"], r["id"]): r for r in json.load(f)["rows"]}


def units_of(r, edit=None):
  units, errors = ap.stage1_units(r["stage1_packages"])
  need(not errors, errors)
  units = copy.deepcopy(units)
  if edit:
    edit({u["unit_id"]: u for u in units})
  return units


def raw_of(r, k):
  return [h for h in r["history"] if h["stage"] == 2 and h.get("raw")][k]["raw"]


def edited(raw, edit):
  parsed, err, _ = aj.parse_response(raw, "stop")
  need(err is None, err)
  logic = parsed["logic"] if isinstance(parsed, dict) else parsed
  edit({p[1]: p for p in logic})
  return json.dumps(parsed)


def attempt(r, raw, units=None, finish="stop", cached=False, merges=()):
  return ap.stage2_attempt(raw, finish, r["text"], units if units is not None else units_of(r), BUNDLE, set(),
                            cached, merges)


def repairs(att, k):
  return [n for n in att["normalizations"] if n.get("repair") == k]


def recorded(n):
  return all(k in n for k in ("kind", "repair", "unit", "before", "after", "support"))


def mismatch(att, uid):
  return any(e.startswith("unit %s: reading_form_mismatch" % uid) for e in att["errors"])


def translate(r, stage1=None):
  """translate() with a fake provider: the saved response of the request with the same input hash; with `stage1`, every
  Stage-1 request gets that response (so a Stage-1 correction is visible in the history)."""
  by_sha = {h["input_sha256"]: h for h in r["history"] if h.get("raw") is not None}
  sent = []

  def fake(sysprompt, prompt, **kwargs):
    # a rerun of the run gets its responses from the LLM cache: one logical call served by the cache
    ap.llmcall.call_log.append({"source": "cache", "logical": True})
    sent.append(prompt)
    if stage1 is not None and sysprompt == BUNDLE["stage1"]:
      return stage1
    h = by_sha.get(hashlib.sha256(prompt.encode("utf-8")).hexdigest())
    if h is not None:
      return h["raw"]
    return stage1 if stage1 is not None else json.dumps(r["stage1_packages"])
  with patch.object(ap.llmcall, "call_llm", side_effect=fake):
    return ap.translate(r["text"], BUNDLE), sent


# ---------------------------------------------------------------------------


def check_k1(R):
  r = R[("gpt", 17)]
  att = attempt(r, raw_of(r, 1))
  k1 = repairs(att, "K1")
  need(not att["errors"] and len(k1) == 1 and k1[0]["unit"] == "S4" and k1[0]["before"] == "restriction"
       and k1[0]["after"] == "availability" and recorded(k1[0]), "K1 gpt 17: %r %r" % (att["errors"], k1))

  def unless(us):
    us["S4"]["text"] = "Babies cannot take the bus unless they are accompanied."
  att = attempt(r, raw_of(r, 1), units_of(r, unless))
  need(mismatch(att, "S4") and not repairs(att, "K1"), "K1 unless: %r" % att["errors"])

  def only(us):
    us["S4"]["text"] = "Only adults can take the bus; babies cannot take the bus."
  att = attempt(r, raw_of(r, 1), units_of(r, only))
  need(mismatch(att, "S4"), "K1 only: %r" % att["errors"])
  # a lost condition: claude 30's denial without "not licensed"
  r = R[("claude", 30)]
  att = attempt(r, raw_of(r, 1))
  need(repairs(att, "K1") and not mismatch(att, "S5"), "K1 claude 30: %r" % att["errors"])

  def lose(ps):
    body = ps["S5"][2][2]
    while body[0] == "forall":
      body = body[2]
    body[1] = body[1][1]            # ["and", person, not licensed] -> person
  att = attempt(r, edited(raw_of(r, 1), lose))
  need(mismatch(att, "S5") and not repairs(att, "K1"), "K1 a lost condition: %r" % att["errors"])
  return "K1: gpt 17's plain denial accepted under restriction and recorded; unless, only and a lost condition " \
         "(claude 30 without \"not licensed\") keep reading_form_mismatch"


def check_k2(R):
  r = R[("gpt", 21)]
  att = attempt(r, raw_of(r, 0))
  k2 = repairs(att, "K2")
  need(not att["errors"] and len(k2) == 1 and k2[0]["unit"] == "S5" and k2[0]["before"] == "effect"
       and k2[0]["after"] is None and recorded(k2[0]), "K2 gpt 21: %r %r" % (att["errors"], k2))

  def after(us):
    us["S5"]["text"] = "After the egg 2 is whisked, the egg 2 is ready."
  att = attempt(r, raw_of(r, 0), units_of(r, after))
  need(mismatch(att, "S5"), "K2 a passive effect: %r" % att["errors"])

  def actor(us):
    us["S5"]["actions"] = [{"root": "whisk", "mode": "event", "roles": {"actor": "Ann 1", "target": "egg 2"}}]
  att = attempt(r, raw_of(r, 0), units_of(r, actor))
  need(mismatch(att, "S5"), "K2 an actor: %r" % att["errors"])
  return "K2: gpt 21's state rule accepted under effect (reading none); an effect marker (after) and an actor keep " \
         "reading_form_mismatch"


def check_k3(R):
  r = R[("claude", 30)]
  att = attempt(r, raw_of(r, 1))
  k3 = repairs(att, "K3")
  need(not att["errors"] and k3 and k3[0]["role"] == "target" and k3[0]["stage1"] == "licence", "K3: %r %r" % (att["errors"], k3))

  def concrete(us):
    us["S7"]["actions"][0]["roles"]["target"] = "Tallinn 3"
  att = attempt(r, raw_of(r, 1), units_of(r, concrete))
  need(any("participants mismatch" in e for e in att["errors"]), "K3 a concrete id compared: %r" % att["errors"])

  def result(us):
    us["S7"]["actions"][0]["roles"]["result"] = "rich"
  att = attempt(r, raw_of(r, 1), units_of(r, result))
  need(any("participants mismatch" in e for e in att["errors"]), "K3 the result compared: %r" % att["errors"])
  return "K3: claude 30's verify step with the word licence as target is accepted with a note; a concrete target " \
         "and a differing result stay compared"


def check_k4(R):
  r = R[("claude", 8)]
  att = attempt(r, raw_of(r, 1))
  k4 = repairs(att, "K4")
  need(not att["errors"] and k4 and k4[0]["variable"] == "X" and k4[0]["slot"] == 1, "K4: %r %r" % (att["errors"], k4))
  for name, edit in (("outside", lambda ps: ps["S9"][2].__setitem__(1, "Y")),
                     ("lexical", lambda ps: ps["S9"][2][2][1].__setitem__(1, "Ann 1") or
                      ps["S9"][2][2][1].__setitem__(3, "X")),
                     ("twice", lambda ps: ps["S9"][2][2][1].__setitem__(4, "X"))):
    att = attempt(r, edited(raw_of(r, 1), edit))
    need(any("query reading/package mismatch" in e for e in att["errors"]) and not repairs(att, "K4"),
         "K4 %s: %r" % (name, att["errors"]))
  return "K4: claude 8's who-question as ask over executable is accepted; a variable outside the action, in the " \
         "value slot, or in two slots is a mismatch"


def check_k5(R):
  r = R[("gpt", 9)]
  att = attempt(r, raw_of(r, 0))
  k5 = repairs(att, "K5")
  need(not att["errors"] and len(k5) == 1 and k5[0]["support"] == ["S3"] and recorded(k5[0]) and
       '"pan 2"' in k5[0]["after"], "K5 gpt 9: %r %r" % (att["errors"], k5))
  r = R[("gemini", 33)]
  att = attempt(r, raw_of(r, 0))
  need(len(repairs(att, "K5")) == 2 and not att["errors"], "K5 gemini 33, the effect and the step: %r" % att["errors"])
  units = units_of(r)
  base = json.loads(json.dumps(aj.parse_response(raw_of(r, 0))[0]["logic"]))
  perm = ["@id", "S4", ["holds", "W0", ["can", "Ann 1", ["change", "Ann 1", "egg 2", "cooked", "pan 3"]]]]

  def run(packages):
    pk = copy.deepcopy(packages)
    return arep.repair_packages(units, pk), pk
  # two permissions with two tools: ambiguous
  other = copy.deepcopy(base)
  other[3] = ["@id", "S4", ["holds", "W0", ["and", perm[2][2], ["can", "Ann 1", ["change", "Ann 1", "egg 2", "cooked",
                                                                                "pot 9"]]]]]
  recs, _ = run(other)
  need(not [x for x in recs if x["repair"] == "K5"], "K5 two tools: %r" % recs)
  # a mention with another value, or with its own tool, is kept
  for slot, value in ((3, "fried"), (4, "fork 8")):
    m = copy.deepcopy(base)
    m[4][2][2][1][slot] = value
    recs, pk = run(m)
    need(pk[4][2][2][1][slot] == value and not [x for x in recs if x["repair"] == "K5" and x["unit"] == "S5"],
         "K5 a mention with its own %s: %r" % ("value" if slot == 3 else "tool", recs))
  # a mention whose Stage-1 action names another tool keeps its term (a tool that only the question names)
  def other_tool(us):
    us["S6"]["actions"][0]["roles"]["location"] = "pot 9"
  recs = arep.repair_packages(units_of(r, other_tool), copy.deepcopy(base))
  need([x["unit"] for x in recs if x["repair"] == "K5"] == ["S5"], "K5 a stated other tool: %r" % recs)
  # two conditional permissions of one term are one term
  two = copy.deepcopy(base)
  two[3] = ["@id", "S4", ["holds", "W0", ["and", ["implies", ["has property", "raw", "egg 2"], perm[2][2]],
                                           ["implies", ["have", "Ann 1", "pan 3"], perm[2][2]]]]]
  recs, _ = run(two)
  need(len([x for x in recs if x["repair"] == "K5"]) == 2, "K5 one term twice: %r" % recs)
  return "K5: gpt 9's question and gemini 33's effect and step take the permission's tool; two tools, another " \
         "value, an own tool and another tool named in Stage 1 change nothing; two conditional permissions of one " \
         "term are one term"


def check_k6_k7(R):
  r = R[("gpt", 17)]
  att = attempt(r, raw_of(r, 0))
  k6 = repairs(att, "K6")
  s4 = [p for p in att["packages"] if p[1] == "S4"][0][2][2]
  need(not att["errors"] and len(k6) == 1 and recorded(k6[0]) and s4[0] == "forall" and s4[1] == "X"
       and s4[2][:2] == ["forall", "F"] and s4[2][2][:2] == ["forall", "T"], "K6 gpt 17: %r %r" % (att["errors"], s4))
  r = R[("gemini", 17)]
  att = attempt(r, raw_of(r, 0))
  need(not att["errors"] and repairs(att, "K7") and repairs(att, "K6"), "K7 gemini 17: %r" % att["errors"])

  def stated(us):
    us["S4"]["actions"][0]["roles"]["source"] = "Haapsalu 2"
  r = R[("gpt", 17)]
  att = attempt(r, raw_of(r, 0), units_of(r, stated))
  need(any("unspecified_position" in e for e in att["errors"]) and not repairs(att, "K6"),
       "K6 a stated endpoint: %r" % att["errors"])

  def elsewhere(ps):
    body = ps["S4"][2][2]
    body[2][1] = ["and", body[2][1], ["is rel2", "located_at", "X", "F"]]
    body[2][2][1][2][2] = "F"
  att = attempt(r, edited(raw_of(r, 0), elsewhere))
  need(any("unbound_variable" in e and "F" in e for e in att["errors"]), "K6 a variable used elsewhere: %r" % att["errors"])
  units = units_of(r)
  q = [["@id", "S5", ["question", ["executable", ["move", "Ann 1", "unspecified", "unspecified", "bus"]]]]]
  recs = arep.repair_packages(units, q)
  need(not recs and q[0][2][1][1][2] == "unspecified", "K6 a supplied step: %r" % recs)
  r = R[("gemini", 17)]

  def toy(ps):
    ps["S4"][2][2][2][2][1][2] = "toy bus 9"
  att = attempt(r, edited(raw_of(r, 0), toy))
  need(not repairs(att, "K7"), "K7 an entity: %r" % att["normalizations"])
  return "K6: gpt 17's unstated endpoints bound as forall F, forall T below forall X; K7: gemini 17's take of the " \
         "bus is a move; a stated endpoint, a variable used elsewhere, a supplied step and take of an entity are " \
         "left as written"


def check_k8(R):
  r = R[("gpt", 98)]
  att = attempt(r, raw_of(r, 0))
  k8 = repairs(att, "K8")
  need(att["stop"] == "unsupported" and k8 and recorded(k8[0])
       and att["result"]["unsupported"]["reasons"] == ["existential_availability_head"], "K8: %r" % att)
  units = units_of(r)
  named = [["@id", "S2", ["holds", "W0", ["can", "unspecified", ["change", "egg 1", "egg 1", "whisked", "unspecified"]]]]]
  need(not arep.repair_packages(units, named), "K8 an action with its own actor")
  negated = [["@id", "S2", ["holds", "W0", ["not", ["can", "unspecified", ["change", "unspecified", "egg 1", "whisked",
                                                                            "unspecified"]]]]]]
  need(not arep.repair_packages(units, negated), "K8 a negated can")
  return "K8: gpt 98's agentless permission becomes existential and stays unsupported " \
         "(existential_availability_head); an action with its own actor and a negated can are left as written"


def check_k9(R):
  r = R[("gemini", 15)]
  units = units_of(r)
  merges, questions = arep.id_findings(units)
  need(merges == [{"before": "hand 1", "after": "robot hand 1", "units": ["S5", "S6", "S7"], "first": "S1"}]
       and not questions, "K9 gemini 15: %r %r" % (merges, questions))
  rec, sent = translate(r)
  s1 = [h for h in rec["history"] if h["stage"] == 1][0]
  need(rec["status"] == "ok" and len(sent) == 2 and [n["repair"] for n in s1.get("normalizations") or []] == ["K9"] * 3,
       "K9 through translate: %r %r" % (rec["status"], rec["errors"]))
  need("hand 1" not in json.dumps([rec["stage1_units"], rec["stage2"]]).replace("robot hand 1", ""),
       "K9: one id in Stage 1 and Stage 2")
  need(rec["stage1_units"][4]["text"] == "The robot hand 1 is empty.", rec["stage1_units"][4]["text"])
  # two different entities with one index
  merges, questions = arep.id_findings(units_of(R[("claude", 18)]))
  need(not merges and not questions, "K9 claude 18: %r %r" % (merges, questions))

  # the same index and head noun without "the": a Stage-1 correction
  def no_the(us):
    us["S5"]["text"] = "A hand 1 is empty."
  merges, questions = arep.id_findings(units_of(r, no_the))
  need(not merges and len(questions) == 1 and "'robot hand 1'" in questions[0] and "'hand 1'" in questions[0],
       "K9 no anaphor: %r" % questions)

  def other_hand(us):
    us["S2"]["entities"].append({"id": "hand 9", "type": "concrete", "category": "artifact"})
  merges, questions = arep.id_findings(units_of(r, other_hand))
  need(not merges and questions, "K9 another hand: %r" % merges)
  stage1 = json.loads(json.dumps(r["stage1_packages"]))
  for p in stage1:
    for u in p["units"]:
      if u["unit_id"] == "S5":
        u["text"] = "A hand 1 is empty."
  rec, sent = translate(r, json.dumps(stage1))
  s1 = [h for h in rec["history"] if h["stage"] == 1]
  need(len(s1) >= 2 and any("share the index 1" in e for e in s1[0]["errors"]) and "share the index 1" in sent[1],
       "K9 the correction request: %r" % [h.get("errors") for h in s1])
  return "K9: gemini 15's robot hand 1 and hand 1 merged in Stage 1 and in each Stage-2 response; claude 18's two " \
         "entities with index 1 stay apart; without the anaphor, or with another hand, Stage 1 gets a correction " \
         "that names both ids"


def check_k10(R):
  r = R[("deepseek", 96)]
  raw = raw_of(r, 0)
  att = attempt(r, raw)
  k10 = repairs(att, "K10")
  need(att["stop"] == "unsupported" and k10 and k10[0]["unit"] == "S3" and recorded(k10[0])
       and att["result"]["unsupported"]["reasons"] == ["unsupported_confidence_form"], "K10: %r" % att["errors"])
  att = attempt(r, raw.replace('["@p","S3",0.2]', '["@p","S3",0.3]'))
  need(att["errors"] and att["errors"][0].startswith("the response is not JSON"), "K10 another number: %r" % att["errors"])
  att = attempt(r, raw, finish=None, cached=False)
  need(att["errors"] and att["parse"]["repair"]["reason"] == "no stop reason", "K10 no stop reason: %r" % att["parse"])
  att = attempt(r, raw, finish="length")
  need(att["errors"] and "output limit" in att["errors"][0], "K10 at the output limit: %r" % att["errors"])
  # an intact response with the misplaced @p
  intact = '{"worlds":["W0"],"contexts":{},"query_contexts":{},"logic":[' + \
    '["@id","S1",["holds","W0",["isa","robot","Robo 1"]]],' + \
    '["@id","S2",["holds","W0",["is rel2","located_at","Robo 1","Haapsalu 2"]]],' + \
    '["@id","S3",["and",["holds","W0",["not",["can","Robo 1",["move","Robo 1","Haapsalu 2","Tallinn 3","bus"]]]]],' + \
    '["@p","S3",0.2]],' + \
    '["@id","S4",["question",["executable",["move","Robo 1","Haapsalu 2","Tallinn 3","bus"]]]]]}'
  att = attempt(r, intact)
  need(att["stop"] == "unsupported" and repairs(att, "K10"), "K10 intact: %r" % att["errors"])
  att = attempt(r, intact.replace('["@p","S3",0.2]', '["@p","S3",0.99]'))
  need(att["errors"] == ['the output is not a list of ["@id", ID, PACKAGE] packages'], "K10 intact, 0.99: %r" % att["errors"])
  # the convention confidence 0.99 of an article, misplaced in gpt 65, is dropped as a well-placed one is (S1)
  r = R[("gpt", 65)]
  att = attempt(r, raw_of(r, 0))
  need(not att["errors"] and [n["unit"] for n in repairs(att, "K10")] == ["S2", "S3", "S4", "S5"],
       "K10 the convention 0.99: %r" % att["errors"])
  return "K10: deepseek 96's misplaced @p 0.2 is dropped after the bracket repair and in an intact response, and " \
         "gpt 65's article convention 0.99; 0.3, 0.99 on a unit with 0.2, no stop reason and the output limit get no " \
         "repair"


def check_k11(R):
  r = R[("gpt", 73)]
  att = attempt(r, raw_of(r, 1))
  k11 = repairs(att, "K11")
  need(k11 and k11[0]["unit"] == "S5" and k11[0]["before"] is None and k11[0]["after"] == "availability"
       and not mismatch(att, "S5"), "K11 gpt 73: %r" % att["errors"])

  def no_action(us):
    us["S5"]["actions"] = []
  att = attempt(r, raw_of(r, 1), units_of(r, no_action))
  need(mismatch(att, "S5") and not repairs(att, "K11"), "K11 without a capability action: %r" % att["errors"])
  # the route selection is computed again (gemini default_and_exception of WP19: no Stage-1 readings), with the saved
  # responses per stage in order, as check_action_corrections replays them
  with open(os.path.join(HERE, "regression", "wp19_translations.json")) as f:
    w = [x for x in json.load(f)["rows"] if (x["model"], x["id"], x["mode"]) ==
         ("gemini", "default_and_exception", "natural")][0]
  queues = {s: [h["raw"] for h in w["history"] if h["stage"] == s and h.get("raw") is not None] for s in (1, 2)}

  def fake(sysprompt, prompt, **kwargs):
    q = queues[1 if sysprompt == BUNDLE["stage1"] else 2]
    return q.pop(0) if len(q) > 1 else q[0]
  with patch.object(ap.llmcall, "call_llm", side_effect=fake):
    rec = ap.translate(w["text"], BUNDLE)
  need(rec["status"] == "ok" and rec["route_selection_stage1"]["route_selected"] == "ordinary"
       and rec["route_selected"] == "actions" and [x["unit"] for x in rec["route_reasons"]] == ["S1", "S2"],
       "K11 the route selection: %r" % {k: rec.get(k) for k in ("status", "route_selected", "route_reasons")})
  return "K11: gpt 73's denial without a reading is availability; without a capability action it stays a " \
         "mismatch; WP19 gemini default_and_exception gets the route actions from the adjusted readings"


def check_k12_a2(R):
  r = R[("gpt", 5)]
  rec, _ = translate(r)
  need(rec["status"] == "ok", rec["errors"])
  res = rp.replay(rec["source"], [])
  need(res["verdict"] == "not_checked" and "normally" in res["reason"], "K12 gpt 5: %r" % res["reason"])
  with patch.object(rp.Source, "initial_state", side_effect=TypeError("unhashable type: 'list'")):
    res = rp.replay(rec["source"], [])
  need(res["verdict"] == "not_checked" and res["uncovered"] == "replay_error", "K12 replay_error: %r" % res)
  r = R[("gpt", 100)]
  rec, _ = translate(r)
  res = rp.replay(rec["source"], [])
  english = [aen.fact_english(rec["source"], a) for c in res["conflicts"] for a in c["atoms"]]
  need(res["verdict"] == "inconsistent_action_state"
       and english == ["the robot hand is empty", "the robot hand holds block a"], "A2: %r" % english)
  need(aen.answer_text({"outcome": "inconsistent_action_state", "query": {"kind": "question"}, "facts_english": english})
       == "Inconsistent: the robot hand is empty and the robot hand holds block a.", "A2 text")
  return "K12: gpt 5's normally rule gives not_checked (the saved run raised TypeError), an internal failure gives " \
         "replay_error; A2: gpt 100 reads Inconsistent: the robot hand is empty and the robot hand holds block a."


def check_k13(R):
  r = R[("deepseek", 13)]
  att = attempt(r, raw_of(r, 0))
  need(any("value slot" in e and "past participle" in e for e in att["errors"]), "K13 value slot: %r" % att["errors"])
  r = R[("gemini", 7)]
  att = attempt(r, raw_of(r, 0))
  need(any("actor slot" in e and "a rule between two states has no after" in e for e in att["errors"]),
       "K13 actor slot: %r" % att["errors"])
  r = R[("deepseek", 100)]
  att = attempt(r, raw_of(r, 0))
  need(any("executable question needs its reading" in e and "without an action reading has the form" in e
           for e in att["errors"]), "K13 question form: %r" % att["errors"])

  def plan(us):
    us["S5"]["action_reading"] = "plan_question"
  att = attempt(r, raw_of(r, 0), units_of(r, plan))
  need(any("query reading/package mismatch" in e and '["plan",GOAL]' in e for e in att["errors"]),
       "K13 plan form: %r" % att["errors"])
  # a later mention with another value than its permission
  r = R[("deepseek", 36)]
  att = attempt(r, raw_of(r, 0))
  msg = [e for e in att["errors"] if "names the action of the permission in unit S4" in e]
  need(msg and '["change","Ann 1","egg 2","whisked","whisk 3"]' in msg[0] and att["value_asked"] == ["S5"],
       "K13 value: %r" % att["errors"])
  att = ap.stage2_attempt(raw_of(r, 0), "stop", r["text"], units_of(r), BUNDLE, set(), False, (), {"S5"})
  need(not any("names the action of the permission" in e for e in att["errors"]), "K13 asked once: %r" % att["errors"])

  # the clause that names the action holds its verb, also after a condition (Fable's review, S2)
  clause = arep.action_clause({"text": "If egg 2 is raw, after Nia 1 cooks egg 2 with pan 3, egg 2 is no longer raw."},
                               {"root": "cook"})
  need(clause.strip() == "after Nia 1 cooks egg 2 with pan 3", "K13 the action clause: %r" % clause)

  def stated(us):
    us["S5"]["text"] = "After Ann 1 whisks the egg 2 fluffy, the egg 2 is fluffy."
  att = attempt(r, raw_of(r, 0), units_of(r, stated))
  need(not any("names the action of the permission" in e for e in att["errors"]), "K13 a stated value: %r" % att["errors"])
  return "K13: the value slot names the stated result or the participle (deepseek 13); the actor slot says that a " \
         "rule between two states has no after (gemini 7); the question messages name the form of the reading " \
         "(deepseek 100); deepseek 36's effect gets the permission's unit S4 and term, once, and not when the " \
         "sentence states the value"


def stub(r, replies):
  """translate() where Stage 1 is the saved response and Stage 2 gets `replies` in order (the last repeats)."""
  queue = list(replies)
  sent = []

  def fake(sysprompt, prompt, **kwargs):
    ap.llmcall.call_log.append({"source": "cache", "logical": True})
    if sysprompt == BUNDLE["stage1"]:
      return json.dumps(r["stage1_packages"])
    sent.append(prompt)
    return queue.pop(0) if len(queue) > 1 else queue[0]
  with patch.object(ap.llmcall, "call_llm", side_effect=fake):
    return ap.translate(r["text"], BUNDLE, semantic=False), sent


def check_k14(R):
  r = R[("gemini", 7)]
  first = raw_of(r, 0)
  fixed = [["@id", "S5", ["holds", "W0", ["implies", ["has property", "whisked", "egg 2"],
                                          ["has property", "ready", "egg 2"]]]]]
  rec, sent = stub(r, [first, first, json.dumps(fixed)])
  kinds = [h.get("kind") for h in rec["history"] if h["stage"] == 2]
  need(rec["status"] == "ok" and kinds == [None, None, "focused_correction"] and len(sent) == 3,
       "K14 gemini 7: %r %r" % (rec["status"], kinds))
  need("was the same as the output before it" in sent[2] and '["@id", "S5"' in sent[2] and '["@id", "S1"' not in sent[2],
       "K14: only the failing package is quoted")
  s5 = [p for p in rec["stage2"]["packages"] if p[1] == "S5"][0]
  need(s5[2][2][0] == "implies" and len(rec["stage2"]["packages"]) == 6, "K14 splice: %r" % s5)
  # the focused reply repeats the failing package: no fourth request
  rec, sent = stub(r, [first, first, first])
  need(rec["status"] == "translation_invalid" and len(sent) == 3, "K14 a second repeat: %r" % rec["status"])
  # nothing to quote: a response that is no JSON stops as before
  rec, sent = stub(r, ["this is not JSON"])
  need(rec["status"] == "translation_invalid" and rec.get("stop_reason") == "repeated_request" and len(sent) == 2,
       "K14 nothing to quote: %r" % rec.get("stop_reason"))
  return "K14: gemini 7's unchanged correction is followed by one focused request that quotes only S5, and the reply " \
         "is spliced in; a repeated reply and a response without packages stop as before"


def check_k15(R):
  out = []
  for key, reason, fix in ((("gemini", 41), "method_collision", None), (("gpt", 39), "unsupported_law_form", None)):
    r = R[key]
    first = raw_of(r, 0)
    rec, sent = stub(r, [first])
    kinds = [h.get("kind") for h in rec["history"] if h["stage"] == 2]
    need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == [reason]
         and kinds == [None, "clarification"] and "CLARIFICATION" in sent[1] and "Do not invent an effect" in sent[1],
         "K15 %s repeated: %r %r" % (key, rec.get("unsupported"), kinds))
    rec, sent = stub(r, [first, "not JSON"])
    need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == [reason] and len(sent) == 2,
         "K15 %s a reply with errors: %r" % (key, rec.get("unsupported")))
    rec, sent = stub(r, [first, None])
    need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == [reason],
         "K15 %s no reply: %r" % (key, rec.get("status")))
    out.append("%s %s" % key)
  # a valid reply whose changed values the text states for their verbs (wet for boil, crisp for fry) is accepted;
  # a reply relabelled with participles that no sentence states keeps the collision (Fable's review, F2)
  r = R[("gemini", 41)]

  def relabel(values):
    def edit(ps):
      for uid, value in zip(("S2", "S4", "S3", "S5"), values):
        body = ps[uid][2][2]
        (body[2] if body[0] == "can" else body[1])[3] = value
    return edit
  rec, _ = stub(r, [raw_of(r, 0), edited(raw_of(r, 0), relabel(("wet", "wet", "crisp", "crisp")))])
  need(rec["status"] == "ok" and [h.get("clarification") for h in rec["history"] if h.get("kind") == "clarification"]
       == ["accepted"], "K15 a reply with the stated results: %r %r" % (rec["status"], rec["errors"]))
  rec, _ = stub(r, [raw_of(r, 0), edited(raw_of(r, 0), relabel(("boiled", "boiled", "fried", "fried")))])
  last = [h for h in rec["history"] if h.get("kind") == "clarification"][0]
  need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == ["method_collision"]
       and {x["value"] for x in last.get("unstated_values") or []} == {"boiled", "fried"},
       "K15 a reply with unstated participles: %r %r" % (rec["status"], last.get("unstated_values")))
  # a real collision: both methods state only the one result cooked; the relabelled reply keeps the outcome
  real = copy.deepcopy(r)
  for p in real["stage1_packages"]:
    for u in p["units"]:
      if u["unit_id"] in ("S4", "S5"):
        u["text"] = u["text"].replace(" and the egg 2 is wet", "").replace(" and the egg 2 is crisp", "")
        p["raw"] = p["raw"].replace(" and the egg is wet", "").replace(" and the egg is crisp", "")
      if u["unit_id"] == "S6":
        u["text"] = u["text"].replace(" cooked and crisp", " cooked")
        p["raw"] = p["raw"].replace(" cooked and crisp", " cooked")
  real["text"] = " ".join(p["raw"] for p in real["stage1_packages"])

  def one_result(ps):
    for uid in ("S4", "S5"):
      ps[uid][2][2][2] = ["has property", "cooked", "egg 2"]
    ps["S6"][2][1] = ["has property", "cooked", "egg 2"]
  first = edited(raw_of(r, 0), one_result)
  second = json.loads(edited(first, relabel(("boiled", "boiled", "fried", "fried"))))
  rec, sent = stub(real, [first, json.dumps(second)])
  last = [h for h in rec["history"] if h.get("kind") == "clarification"][0]
  need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == ["method_collision"]
       and len(sent) == 2 and not last["errors"] and {x["value"] for x in last.get("unstated_values") or []}
       == {"boiled", "fried"}, "K15 a relabelled real collision: %r %r" % (rec["status"], last))
  # a stated result is a positive result of the same operation on the same object (Sol's review): controls on the
  # check itself, with a permission to boil the egg and one effect sentence
  def result_units(effect_text, actor="Ann 1"):
    return [{"unit_id": "S2", "text": "Ann 1 can boil the egg 2.", "type": "strict_rule", "action_reading": "availability",
             "actions": [{"root": "boil", "mode": "capability", "roles": {"actor": "Ann 1", "target": "egg 2"}}]},
            {"unit_id": "S4", "text": effect_text, "type": "strict_rule", "action_reading": "effect",
             "actions": [{"root": "boil", "mode": "event", "roles": {"actor": actor, "target": "egg 2"}}]}]

  def result_packages(value, head, actor="Ann 1", condition=None, permission_condition=None):
    can = ["can", "Ann 1", ["change", "Ann 1", "egg 2", value, "unspecified"]]
    law = ["after", ["change", actor, "egg 2", value, "unspecified"], head]
    return [["@id", "S2", ["holds", "W0", can if permission_condition is None else
                           ["implies", permission_condition, can]]],
            ["@id", "S4", ["holds", "W0", law if condition is None else ["implies", condition, law]]]]
  before = result_packages("cooked", ["has property", "cooked", "egg 2"])
  wet = ["has property", "wet", "egg 2"]
  raw = ["has property", "raw", "egg 2"]
  cases = [("stated", result_units("After Ann 1 boils the egg 2, the egg 2 is wet."), result_packages("wet", wet), []),
           ("wrong object", result_units("After Ann 1 boils the egg 2, the pot 3 is wet."),
            result_packages("wet", ["has property", "wet", "pot 3"]), [("S2", "wet"), ("S4", "wet")]),
           ("negative result", result_units("After Ann 1 boils the egg 2, the egg 2 is not wet."),
            result_packages("wet", ["not", wet]), [("S2", "wet"), ("S4", "wet")]),
           ("different actor", result_units("After Bob 5 boils the egg 2, the egg 2 is wet.", "Bob 5"),
            result_packages("wet", wet, "Bob 5"), [("S2", "wet")]),
           ("conditional effect", result_units("If the egg 2 is raw, after Ann 1 boils the egg 2, the egg 2 is wet."),
            result_packages("wet", wet, condition=raw), [("S2", "wet"), ("S4", "wet")]),
           ("conditional effect, same condition on the permission",
            result_units("If the egg 2 is raw, after Ann 1 boils the egg 2, the egg 2 is wet."),
            result_packages("wet", wet, condition=raw, permission_condition=raw), [])]
  for name, units, after, want in cases:
    got = arep.unstated_values(units, before, after)
    need(got == want, "K15 %s: %r" % (name, got))
  r = R[("gpt", 39)]

  def antecedent(ps):
    for uid in ("S5", "S6"):
      imp = ps[uid][2][2]
      imp[1] = ["and", imp[1], imp[2][1]]
      imp[2] = imp[2][2]
  rec, _ = stub(r, [raw_of(r, 0), edited(raw_of(r, 0), antecedent)])
  need(rec["status"] == "ok", "K15 gpt 39 a valid reply: %r %r" % (rec["status"], rec["errors"]))
  # the reply may change nothing else (Sol's review): a deleted condition, a deleted goal conjunct and a changed
  # unrelated unit keep the unsupported outcome

  def deleted_condition(ps):
    antecedent(ps)
    ps["S5"][2][2][1] = ps["S5"][2][2][1][2]           # and(broken, have) -> have
  cases = [(r, deleted_condition, "unsupported_law_form", "S5")]
  g41 = R[("gemini", 41)]

  def goal_conjunct(ps):
    relabel(("wet", "wet", "crisp", "crisp"))(ps)
    ps["S6"][2][1] = ["has property", "crisp", "egg 2"]

  def unrelated(ps):
    relabel(("wet", "wet", "crisp", "crisp"))(ps)
    ps["S1"][2][2] = ["have", "Ann 1", "egg 2"]
  cases += [(g41, goal_conjunct, "method_collision", "S6"), (g41, unrelated, "method_collision", "S1")]
  for case, edit, reason, unit in cases:
    rec, _ = stub(case, [raw_of(case, 0), edited(raw_of(case, 0), edit)])
    last = [h for h in rec["history"] if h.get("kind") == "clarification"][0]
    need(rec["status"] == "unsupported_translation" and rec["unsupported"]["reasons"] == [reason]
         and any(x.startswith("unit %s:" % unit) for x in last.get("clarification_refusals") or []),
         "K15 %s: %r %r" % (edit.__name__, rec["status"], last.get("clarification_refusals")))
  return "K15: gemini 41 (method_collision) and gpt 39 (unsupported_law_form) get one clarification; a repeated " \
         "translation, a reply with errors, no reply, a reply relabelled with unstated participles and a relabelled " \
         "real collision end as Cannot answer with the same reason; the stated results wet and crisp, and the " \
         "possession moved into the antecedent, are accepted; a result of another object, a negated result, a " \
         "result of another actor and a conditional effect whose condition the permission lacks state no value; a " \
         "reply that deletes a condition, deletes a goal conjunct or changes an unrelated unit is refused"


def check_k16():
  """K16: a dependency between states that Stage 1 types as a rule becomes state_law; the negative cases stay."""
  rule = ["forall", "X", ["implies", ["and", ["isa", "block", "X"], ["is rel2", "on", "X", "table 3"]],
                          ["has property", "steady", "X"]]]

  def run_one(text, kind="strict_rule", formula=rule, extra=None):
    u = {"unit_id": "S5", "text": text, "type": kind}
    u.update(extra or {})
    pk = [["@id", "S5", ["holds", "W0", json.loads(json.dumps(formula))]]]
    recs = arep.repair_packages([u], pk)
    return [x["repair"] for x in recs], pk[0][2][2]
  got, f = run_one("Whenever a block is on the table 3, that block is steady.")
  need(got == ["K16"] and f[0] == "state_law" and f[1] == rule, "K16: %r %r" % (got, f))
  got, f = run_one("Whenever a block is on the table 3, that block is steady.", extra={"time": "present",
                                                                                       "pre_state": "W0"})
  need(got == ["K16"], "K16 present and W0 stated: %r" % got)
  default = ["forall", "X", ["implies", ["and", ["isa", "block", "X"], ["is rel2", "on", "X", "table 3"]],
                             ["normally", ["has property", "steady", "X"]]]]
  where = "If a block is on the table 3, the block is steady."
  for name, args in (("a normal rule without normally", (where, "normal_rule")),
                     ("a normal rule with a default head", ("If a block is on the table 3, the block is normally "
                                                            "steady.", "normal_rule", default)),
                     ("a strict rule with a default head", (where, "strict_rule", default)),
                     ("a past time", ("Whenever a block was on the table 3, it was steady.", "strict_rule", rule,
                                      {"time": "past"})),
                     ("a future state tense", ("Whenever a block is on the table 3, it will be steady.", "strict_rule",
                                               rule, {"state_tense": "future"})),
                     ("a named time", ("On Monday, whenever a block was on the table 3, it was steady.",
                                       "strict_rule", rule, {"time": "Monday"})),
                     ("a snapshot", ("In snapshot W1, every block on the table 3 is steady.", "strict_rule", rule,
                                     {"pre_state": "W1"})),
                     ("a next snapshot", (where, "strict_rule", rule, {"next_state": "W1"})),
                     ("a knower", ("Ann believes that a block on the table 3 is steady.", "strict_rule", rule,
                                   {"context": {"knower": "Ann"}})),
                     ("a location", ("In the hall, a block on the table 3 is steady.", "strict_rule", rule,
                                     {"context": {"location": "hall"}})),
                     ("a start marker", ("Initially, every block on the table 3 is steady.",)),
                     ("a description of the start", ("Every block on the table 3 is steady.", "situation")),
                     ("a static head", ("A block is a solid.", "strict_rule",
                                        ["forall", "X", ["implies", ["isa", "block", "X"], ["isa", "solid", "X"]]])),
                     ("a class guard only", ("Nothing is on top of any block.", "strict_rule",
                                             ["forall", "X", ["implies", ["isa", "block", "X"],
                                                              ["has property", "clear_top", "X"]]])),
                     ("already standing", ("Whenever a block is on the table 3, it is steady.", "strict_rule",
                                           ["state_law", rule])),
                     ("an action reading", ("If a block is on the table 3, the block is steady.", "strict_rule", rule,
                                            {"action_reading": "effect"})),
                     ("a stated action", ("If a block is on the table 3, the block is steady.", "strict_rule", rule,
                                          {"actions": [{"root": "take", "mode": "event", "roles": {}}]}))):
    got, f = run_one(*args)
    need(got == [] and f == (args[2] if len(args) > 2 else rule), "K16 %s: %r %r" % (name, got, f))
  # a package in another world, and a package with a stated probability, keep their form
  u = {"unit_id": "S5", "text": "Whenever a block is on the table 3, that block is steady.", "type": "strict_rule"}
  pk = [["@id", "S5", ["holds", "W1", json.loads(json.dumps(rule))]]]
  need(not arep.repair_packages([u], pk) and pk[0][2][2] == rule, "K16 a package in W1")
  u = {"unit_id": "S5", "text": "If a block is on the table 3, it is probably steady.", "type": "strict_rule"}
  pk = [["@id", "S5", ["and", ["holds", "W0", rule], ["@p", "S5", 0.8]]]]
  need(not arep.repair_packages([u], pk) and pk[0][2][1][2] == rule, "K16 a stated probability")
  return "K16: a strict-rule dependency between states becomes state_law; a normal rule (with or without a default " \
         "head), a default head under a strict rule, a past, future or named time, a snapshot, a next snapshot, a " \
         "knower, a location, a package in W1, a start marker, a description of the start, a static head, a class " \
         "guard only, a standing rule, an action reading, a stated action and a stated probability keep their form"


def check_f1_f2():
  """F1 and F2: the repairs after the full run of 2026-10-02, on its saved responses."""
  with open(FULL_RUN) as f:
    data = json.load(f)
  # F1: gpt 13 wraps the bodies of its forall in a list; the controller asks for a correction of the formula
  c = data["contains"]
  units, errors = ap.stage1_units(aj.parse_response(c["stage1_raw"], "completed")[0])
  need(not errors, errors)
  att = ap.stage2_attempt(c["stage2_raw"], "completed", c["text"], units, BUNDLE, set())
  need(att["errors"] == c["stage2_errors"] and any(e.startswith("unit S5: formula:") for e in att["errors"]),
       "F1: %r" % att["errors"])
  # F2: each gemini response parses after its surplus closing brackets are dropped, and gives a list of packages
  for r in data["envelope"]:
    parsed, err, info = aj.parse_response(r["raw"], r["finish_reason"], r["cached"])
    e = info["envelope_repair"] or {}
    need(err is None and e.get("status") == "applied" and e["removed"].strip("] \n") == ""
         and e["before_field"] == "types" and ap.stage2_packages(parsed)[0] is not None,
         "F2 %s: %r %r" % (r["where"][0], err, e))
    # only the run of closing brackets is dropped: the rest of the text is the model's own
    text = llmparse.strip_fence(r["raw"])[0]
    need(e["text"] == text[:e["offset"]] + text[e["offset"] + len(e["removed"]):], "F2 %s: the edit" % r["where"][0])
    # without a stop reason a response is not repaired
    need(aj.parse_response(r["raw"])[1] is not None, "F2 %s: no stop reason" % r["where"][0])
  for r in data["other"]:
    _, err, info = aj.parse_response(r["raw"], r["finish_reason"], r["cached"])
    need(err is not None and (info["envelope_repair"] or {}).get("status") == "refused",
         "F2 other %s: %r" % (r["where"][0], info["envelope_repair"]))
  for bad, why in (('{"logic": [["@id", "S1", ["p", "a 1"]]]], "extra": {}}', "not followed by a field"),
                   ('{"logic": [["@id", "S1", ["p", "a 1"]]], ["@id", "S2", ["q"]]], "types": {}}', "not a closing"),
                   ('{"logic": [["@id", "S1", {"a": [1]]]}], "types": {}}', "not a closing"),
                   ('{"logic": [["@id", "S1", ["p", "a 1"]]]], "types": {"S1": [1}}', "does not parse")):
    _, err, info = aj.parse_response(bad, "STOP")
    need(err is not None and why in (info["envelope_repair"] or {}).get("reason", ""), "F2 %s: %r" % (bad, info))
  return "F1: the gpt 13 response with a list where an operator stands gets the formula error, not a crash; F2: %d " \
         "gemini responses parse after their surplus closing brackets before \"types\" are dropped, none without a " \
         "stop reason; %d other malformed responses and 4 negative texts are refused" % (
           len(data["envelope"]), len(data["other"]))


def _absent(paths):
  """The saved model responses of `regression/` that are not present: the folder is local and not in the
  repository, so a check that replays them skips that part and says so."""
  return [os.path.relpath(p, HERE) for p in paths if not os.path.exists(p)]


def run():
  gone = _absent([SAVED, FULL_RUN, os.path.join(HERE, "regression", "wp19_translations.json")])
  if gone:
    print("  skipped: K1-K15, F1 and F2 replay saved responses that are not present (regression/ is local): %s" % ", ".join(gone))
    parts = [check_k16]
  else:
    R = rows()
    parts = [lambda: check_k1(R), lambda: check_k2(R), lambda: check_k3(R), lambda: check_k4(R), lambda: check_k5(R),
             lambda: check_k6_k7(R), lambda: check_k8(R), lambda: check_k9(R), lambda: check_k10(R),
             lambda: check_k11(R), lambda: check_k12_a2(R), lambda: check_k13(R), lambda: check_k14(R),
             lambda: check_k15(R), check_k16, check_f1_f2]
  for part in parts:
    print("  " + part())


if __name__ == "__main__":
  run()
