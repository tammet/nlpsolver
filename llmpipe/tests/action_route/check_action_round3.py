"""Round 3 after the v4 run: the controller normalizations, the messages, the semantic correction and the type
records, offline.

The saved v4 responses in regression/v4_translations.json replay through the current code with a fake provider. They
test the repairs against the rows that motivated them; they say nothing about what a model does with revision G. Each
repair also has negative controls.  No model call, no GK launch.

  A2  end-of-JSON repair: the four saved gemini responses parse to the logic they meant; an interior mismatch, an
      unterminated string, a text ending after a comma and a truncated response are not repaired; every saved
      response that parsed before parses to the same value now
  A1  envelope derivation (D7): a bare list keeps a non-default root, a past tense and a knower/ambient selection
      from Stage 1; an omitted field is derived, a supplied contradictory field is still rejected
  A3  a one-conjunct ["and", holds] is unwrapped; a confidence package and a two-holds conjunction are not
  A4, A6', A10  the messages for normally above a quantifier, a class atom beside a law, @time on a description, a
      tense word as @time text and a step_bound on a verification
  A8  the semantic correction: findings compared with the rule's own sentence; the exact removal is accepted, any
      other reply is refused and the accepted translation stays; a diagnostic row sends nothing
  A5  the Stage-1 person convention: compiler and replay agree; robot, conflicting category, knower-only,
      query-only and stated-negative controls give no person type
  A11 lexical types of a past description stay when the query excludes it; knower-scoped, conditional, uncertain,
      negated and predicated types do not
  D5  a robot movement rule with unconditioned endpoints reads the stated connection; without it no step is valid
"""
import copy
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "solver"))

import action_pipeline as ap        # noqa: E402

import action_json as aj
import action_prompt as apt         # noqa: E402
import prompt_examples as pe        # noqa: E402
import action_replay as rp          # noqa: E402
import action_route as ar           # noqa: E402
import lc_action_query as lq        # noqa: E402
import llmparse                     # noqa: E402

SAVED = os.path.join(HERE, "regression", "v4_translations.json")
V3 = os.path.join(HERE, "regression", "v3_translations.json")


def saved():
  with open(SAVED) as f:
    return json.load(f)["rows"]


def row(rows, model, case, mode="natural"):
  return next(r for r in rows if r["model"] == model and r["id"] == case and r["mode"] == mode)


def raws(r, stage):
  return [h["raw"] for h in r["history"] if h["stage"] == stage and h.get("raw") is not None]


def examples():
  return {e["id"]: e for e in pe.corpus()}


def translate_with(bundle, text, stage1_raws, stage2_raws, semantic=True):
  """translate() with a fake provider that returns the given responses per stage in order, repeating the last."""
  queues = {1: list(stage1_raws), 2: list(stage2_raws)}
  sent = []

  def fake(sysprompt, prompt, **kwargs):
    stage = 1 if sysprompt == bundle["stage1"] else 2
    sent.append((stage, prompt))
    q = queues[stage]
    return q.pop(0) if len(q) > 1 else q[0]
  with patch.object(ap.llmcall, "call_llm", fake):
    return ap.translate(text, bundle, semantic=semantic), sent


def units_of(e):
  return [u for p in e["stage1"] for u in p["units"]]


def gold_translation(bundle, e, stage2=None):
  return translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(stage2 or e["stage2"])])[0]


def check_json_repair(rows):
  v4 = {e["id"]: e for e in json.load(open(os.path.join(HERE, "v4", "cohort.json")))}
  fixed = 0
  for model, case, mode in (("gemini", "class_guard_holds", "natural"), ("gemini", "distinct_methods_board",
                                                                         "gold_stage1_diagnostic")):
    r = row(rows, model, case, mode)
    for raw in raws(r, 2):
      old, err = llmparse.fix_json(raw)[0], None
      try:
        json.loads(old)
      except ValueError as e:
        err = e
      assert err is not None, case                       # the v4 path failed on it
      parsed, error, info = aj.parse_response(raw, "STOP")
      assert error is None and info["repair"]["status"] == "applied", (case, error, info)
      # round 4 (R4): the same response without a stop reason (a cached one) is not repaired
      none, error_none, info_none = aj.parse_response(raw)
      assert none is None and info_none["repair"] == {"status": "refused", "reason": "no stop reason"}, info_none
      assert info["error"]["pos"] > len(raw) - 20, info["error"]     # the error lies at the end of the model's JSON
      assert parsed["logic"] == v4[case]["stage2"]["logic"], case   # the repaired text is the logic it meant
      fixed += 1
  for bad, why in (('{"a": [1}, [2]]', "not intact"), ('{"a": ["x, y]', "not intact"), ('{"a": [1, 2,]]', "comma"),
                   ('{"a": "text"', "does not end"), ('[1, 2] 3]', "not intact")):
    parsed, error, info = aj.parse_response(bad, "STOP")
    assert info["repair"] and info["repair"]["status"] == "refused" and why in info["repair"]["reason"], (bad, info)
  parsed, error, info = aj.parse_response('{"a": [1, [2]]', finish="MAX_TOKENS")
  assert parsed is None and "output limit" in error and info["repair"]["status"] == "refused"
  parsed, error, info = aj.parse_response('```json\n{"a": [1]}\n```', "STOP")
  assert parsed == {"a": [1]} and error is None and info["repair"] is None and info["unfenced"]
  same = 0
  for path in (SAVED, V3):
    with open(path) as f:
      data = json.load(f)["rows"]
    for r in data:
      for h in r["history"]:
        raw = h.get("raw")
        if not raw:
          continue
        try:
          old = json.loads(llmparse.fix_json(raw)[0])
        except ValueError:
          continue
        new, error, _ = aj.parse_response(raw, "STOP")
        assert error is None and new == old, (r["id"], h["stage"], h["attempt"])
        same += 1
  return "A2/R4: %d saved responses with a wrong final bracket run parse to the logic they meant, and are not " \
         "repaired without a stop reason; 5 malformed texts and a truncated one are refused; %d responses that parsed " \
         "before parse to the same value" % (fixed, same)


def check_envelope(rows, ex):
  bundle = apt.assemble()
  out = []
  for case, key in (("world_selection", "query_contexts"), ("scope_and_knower", "query_contexts")):
    r = row(rows, "gemini", case, "gold_stage1_diagnostic")
    tr, sent = translate_with(bundle, r["text"], [json.dumps(r["stage1_packages"])], raws(r, 2)[:1], semantic=False)
    assert tr["status"] == "ok" and len(sent) == 2, (case, tr["errors"])
    assert tr["normalizations"][0]["kind"] == "envelope_derived", tr["normalizations"]
    assert tr["query_contexts"] == ex[case]["stage2"]["query_contexts"] != {}, (case, tr["query_contexts"])
    out.append(case)
  # a bare list of the gold logic: the past tense, a three-world root and a knower come from Stage 1
  for case in ("past_fact_excluded", "root_selection_three_snapshots", "scope_and_knower", "world_selection"):
    e = ex[case]
    tr = gold_translation(bundle, e, e["stage2"]["logic"])
    assert tr["status"] == "ok", (case, tr["errors"])
    s2 = tr["stage2"]
    assert (s2["worlds"], s2["contexts"], s2["query_contexts"]) == \
      (e["stage2"]["worlds"], e["stage2"]["contexts"], e["stage2"]["query_contexts"]), (case, s2)
    q = ar.compile_query(tr["queries"][0], tr["source"], **tr["query_contexts"].get(tr["queries"][0][1], {}))
    assert q["planning_root"] == e["expect"].get("root", q["planning_root"])
  # one omitted field is derived; a supplied contradictory field is replaced by the derived value, and the model's
  # value is recorded
  e = ex["root_selection_three_snapshots"]
  partial = {k: v for k, v in e["stage2"].items() if k != "query_contexts"}
  tr = gold_translation(bundle, e, partial)
  assert tr["status"] == "ok" and tr["normalizations"] == [{"kind": "envelope_derived", "fields": ["query_contexts"],
                                                            "form": "object"}], tr["normalizations"]
  for field, value in (("query_contexts", {"S4": {"planning_root": "W2"}}), ("worlds", ["W0", "W1"])):
    wrong = dict(e["stage2"], **{field: value})
    tr, sent = translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(wrong)])
    assert tr["status"] == "ok" and len(sent) == 2, (field, tr["errors"])
    assert tr["normalizations"] == [{"kind": "derived_field", "field": field, "model": value,
                                     "derived": e["stage2"][field]}], tr["normalizations"]
    assert tr["stage2"][field] == e["stage2"][field], (field, tr["stage2"][field])
  return "A1: the saved gemini bare lists of %s are accepted with the derived envelope; bare gold lists keep a past " \
         "tense, a three-world root W1 and a knower/ambient selection; an omitted field is derived, a contradictory " \
         "supplied root or world list is replaced by the derived one and recorded" % " and ".join(out)


def check_wrapper(rows, ex):
  bundle = apt.assemble()
  r = row(rows, "gemini", "default_and_exception")
  tr, sent = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1])
  assert tr["status"] == "ok" and len(sent) == 2, tr["errors"]
  assert {"kind": "wrapper_dropped", "unit": "S1"} in tr["normalizations"], tr["normalizations"]
  e = ex["uncertain_source"]
  tr = gold_translation(bundle, e)
  assert tr["status"] == "ok" and not any(n["kind"] == "wrapper_dropped" for n in tr["normalizations"])
  assert any(p[2][0] == "and" and p[2][2][0] == "@p" for p in tr["stage2"]["packages"])
  two = copy.deepcopy(ex["travel_goal"]["stage2"])
  two["logic"][1][2] = ["and", two["logic"][1][2], two["logic"][2][2]]
  tr, _ = translate_with(bundle, ex["travel_goal"]["text"], [json.dumps(ex["travel_goal"]["stage1"])], [json.dumps(two)])
  assert tr["status"] == "translation_invalid" and any('["holds",W,F]' in x for x in tr["errors"]), tr["errors"]
  return "A3: the saved gemini default_and_exception wrapper is dropped and the source compiles; a confidence " \
         "package keeps its @p; an and of two holds is refused, and the message names both package forms"


def check_messages(rows, ex):
  bundle = apt.assemble()
  r = row(rows, "claude", "default_and_exception")
  tr, _ = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[1:2])
  msgs = [m for h in tr["history"] for m in (h.get("errors") or [])]
  assert any("normally wraps the can head only" in m for m in msgs), msgs
  r = row(rows, "gemini", "new_dated_fact", "gold_stage1_diagnostic")
  tr, _ = translate_with(bundle, r["text"], [json.dumps(r["stage1_packages"])], raws(r, 2)[:1])
  msgs = [m for h in tr["history"] for m in (h.get("errors") or [])]
  assert any("a description takes no @time" in m for m in msgs), msgs
  r = row(rows, "gemini", "new_dated_fact")
  tr, _ = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1])
  msgs = tr["history"][1]["errors"]
  assert any('"person", "Anna 2"' in m and "remove it" in m for m in msgs), msgs
  assert any('"gate", "gate 1"' in m and "unit S1" in m for m in msgs), msgs
  e = ex["possession_and_holding"]
  bad = copy.deepcopy(e["stage2"])
  del bad["types"]
  bad["logic"][3][2][2] = ["and", ["isa", "box", "box 3"], bad["logic"][3][2][2]]
  tr, _ = translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(bad)])
  assert any('types: {"S4"' in m for m in tr["history"][1]["errors"]), tr["history"][1]["errors"]
  tense = copy.deepcopy(ex["past_fact_excluded"]["stage2"])
  tense["logic"][0][2][2] = ["@time", "past", tense["logic"][0][2][2]]
  tr, _ = translate_with(bundle, ex["past_fact_excluded"]["text"], [json.dumps(ex["past_fact_excluded"]["stage1"])],
                         [json.dumps(tense)])
  assert any("a tense is the context tense" in m for m in tr["history"][1]["errors"]), tr["history"][1]["errors"]
  assert not any("context_record_position" in m for m in tr["history"][1]["errors"]), tr["history"][1]["errors"]
  s1 = copy.deepcopy(ex["empty_verify"]["stage1"])
  s1[-1]["units"][0]["step_bound"] = {"comparison": "exactly", "count": 0}
  assert any("a verify_question has no step_bound" in x for x in ap.stage1_units(s1)[1])
  wrong = copy.deepcopy(ex["hand_in_permission"]["stage2"])
  wrong["types"] = {"S2": [["isa", "table", "table 3"]]}
  errs = apt.handoff_errors(units_of(ex["hand_in_permission"]), wrong, wrong["logic"])
  assert any("a description states its class facts in its own formula" in x for x in errs), errs
  assert any("state [\"isa\",\"hand\",\"robot hand 1\"] once in the envelope field types" in x for x in errs), errs
  wrong["types"] = {"S1": [["isa", "hand", "robot hand 1"], ["isa", "block", "a 2"], ["isa", "table", "table 3"]]}
  errs = apt.handoff_errors(units_of(ex["hand_in_permission"]), wrong, wrong["logic"])
  assert any("does not mention" in x for x in errs), errs
  return "A4/A6'/A10: normally above forall, a description's @time, a tense word as @time text, a class atom beside " \
         "a law (types, its first unit, or removal), a verification's step_bound and misplaced types entries get " \
         "their own messages"


def check_semantic(rows, ex):
  bundle = apt.assemble()
  r = row(rows, "gemini", "conditional_signed_effect")
  base, sent = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1], semantic=False)
  assert len(sent) == 2 and "semantic_correction" not in base
  high = [f for f in base["class_condition_findings"] if f["confidence"] == "high"]
  assert [f["atom"] for f in high] == [["isa", "person", "Nia 1"], ["isa", "pan", "pan 3"]], high
  paths = [f["path"] for f in high]
  fixed = [apt.drop_conjuncts(p, paths) if p[1] == "S4" else p for p in base["stage2"]["packages"]]
  assert next(p for p in fixed if p[1] == "S4")[2][2][1] == ["have", "Nia 1", "pan 3"]
  reply = {k: base["stage2"][k] for k in ("worlds", "contexts", "query_contexts")}
  reply["logic"] = fixed
  tr, sent = translate_with(bundle, r["text"], raws(r, 1)[:1], [raws(r, 2)[0], json.dumps(reply)])
  assert tr["semantic_correction"]["status"] == "accepted" and len(sent) == 3 and tr["status"] == "ok"
  assert tr["class_condition_findings"] == [] and tr["semantic_correction"]["requested"] == high
  assert "path /2/2/1/2" in sent[-1][1]
  # any other reply is refused, and the accepted translation stands with its findings
  for label, other in (("the same reply", raws(r, 2)[0]),
                       ("a changed goal", json.dumps(dict(reply, logic=fixed[:-1] + [
                         ["@id", fixed[-1][1], ["verify", fixed[-1][2][1], ["has property", "cooked", "egg 2"]]]]))),
                       ("one condition kept", json.dumps(dict(reply, logic=[
                         apt.drop_conjuncts(p, paths[:1]) if p[1] == "S4" else p for p in base["stage2"]["packages"]]))),
                       ("not JSON", "no")):
    tr, sent = translate_with(bundle, r["text"], raws(r, 1)[:1], [raws(r, 2)[0], other])
    sc = tr["semantic_correction"]
    assert sc["status"] == "refused" and tr["status"] == "ok" and tr["stage2"]["packages"] == base["stage2"]["packages"], \
      (label, sc)
  # no response: the accepted translation stands
  q = [raws(r, 1)[0]]

  def fake(sysprompt, prompt, **kwargs):
    return q[0] if sysprompt == bundle["stage1"] else (raws(r, 2)[0] if "CORRECTION" not in prompt else None)
  with patch.object(ap.llmcall, "call_llm", fake):
    tr = ap.translate(r["text"], bundle)
  assert tr["status"] == "ok" and tr["semantic_correction"]["status"] == "no_response" and not tr["errors"], tr
  # a stated guard, a quantified guard and an ambiguous class word are not requested
  for case in ("class_guard_holds", "class_guard_unknown", "stated_guard", "worked_c10_ticket_or_pass"):
    f = apt.class_condition_findings(units_of(ex[case]), ex[case]["stage2"]["logic"])
    assert f == [], (case, f)
  units = copy.deepcopy(units_of(ex["class_guard_holds"]))
  units[2]["text"] = "If Nia 1, a doctor, has pan 2, Nia 1 can paint fence 3 red."
  f = apt.class_condition_findings(units, ex["class_guard_holds"]["stage2"]["logic"])
  assert [x["confidence"] for x in f] == ["ambiguous"], f
  return "A8: the saved gemini row has two high findings; the exact removal is accepted (3 calls); the same reply, " \
         "a changed goal, a partial removal and a non-JSON reply are refused and the accepted translation stays; a " \
         "missing reply keeps it too; stated and quantified guards give no finding, an appositive class is ambiguous"


def compile_gold(e, stage1=None, stage2=None):
  """The source artifact of a gold translation through the production _compile, and its query."""
  s1 = stage1 or e["stage1"]
  s2 = stage2 or e["stage2"]
  units, errors = ap.stage1_units(s1)
  assert not errors, errors
  got, errors = ap.stage2_packages(s2)
  assert not errors, errors
  worlds, contexts, packages = got
  src, qs = ap.split_packages(packages)
  rec = {"query_contexts": s2.get("query_contexts", {})}
  stop = ap.compile_translation(rec, e["text"], units, worlds, contexts, src, qs, (), s2.get("types"))
  assert stop in ([], "unsupported"), stop
  return rec


def check_person(rows, ex):
  bundle = apt.assemble()
  r = row(rows, "gemini", "worked_p01_travel")
  tr, _ = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1])
  src = tr["source"]
  assert [(t["entity"], t["kind"]) for t in src["types"]] == [("Ann 1", "stage1_person")], src["types"]
  plan = ex_plan = [["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"], ["move", "Ann 1", "Tallinn 3", "Helsinki 4", "ship"]]
  goal = tr["queries"][0][2][1]
  assert rp.replay(src, plan, goal=goal)["verdict"] == "valid"
  q = ar.compile_query(tr["queries"][0], src)
  assert any(n.startswith("src:types:static_type:") for n in q["selected_clauses"]["source"])
  bare = ar.compile_source([{"id": u["unit_id"], "text": u["text"], "stage1": {k: v for k, v in u.items()
                                                                              if k not in ("unit_id", "text")}}
                            for u in tr["stage1_units"] if u.get("type") != "query"],
                           ap.split_packages(tr["stage2"]["packages"])[0], "physical_v1", r["text"])
  assert "types" not in bare and rp.replay(bare, ex_plan, goal=goal)["verdict"] == "invalid"
  # the gold p01 (no written person class) and a robot (category artifact): a type only for the person
  assert compile_gold(ex["worked_p01_travel"])["types"]["stage1_person"][0]["entity"] == "Ann 1"
  assert compile_gold(ex["robot_public_route"])["types"]["stage1_person"] == []
  # N14's injected input: Stage 1 says person, Stage 2 says robot: a note, no type
  e = copy.deepcopy(ex["robot_named_ann"])
  for p in e["stage1"]:
    for u in p["units"]:
      for x in u["entities"]:
        if x["id"] == "Ann 1":
          x["category"] = "person"
  rec = compile_gold(e)
  assert rec["types"]["stage1_person"] == [] and rec["types"]["notes"][0]["reason"] == "conflicting_category"
  assert any(d.get("reason") == "conflicting_category" and d["level"] == "note" for d in rec["source"]["diagnostics"])
  assert "types" not in rec["source"]
  # a stated negative person fact, a knower-only mention and a query-only mention give no type
  units = [{"unit_id": "S1", "text": "Kim 1 is at Dock 2.", "type": "situation", "pre_state": "W0",
            "entities": [{"id": "Kim 1", "type": "concrete", "category": "person"}, {"id": "Dock 2", "type": "concrete"}]}]
  pk = [["@id", "S1", ["holds", "W0", ["and", ["not", ["isa", "person", "Kim 1"]],
                                       ["is rel2", "located_at", "Kim 1", "Dock 2"]]]]]
  recs, notes = apt.person_types(units, pk)
  assert recs == [] and notes[0]["reason"] == "stated_not_person"
  units[0]["context"] = {"knower": "Dock 2"}
  assert apt.person_types(units, [["@id", "S1", ["holds", "W0", ["is rel2", "located_at", "Kim 1", "Dock 2"]]]]) == ([], [])
  units = [dict(units[0], type="query", context=None)]
  assert apt.person_types(units, []) == ([], [])
  # an explicit person fact needs no record; an unlisted extra class (passenger) is no conflict
  assert compile_gold(ex["travel_goal"])["types"]["stage1_person"] == []
  e = copy.deepcopy(ex["worked_p01_travel"])
  e["stage2"]["logic"][0][2][2] = ["and", ["isa", "passenger", "Ann 1"], e["stage2"]["logic"][0][2][2]]
  assert compile_gold(e)["types"]["stage1_person"][0]["entity"] == "Ann 1"
  # the dependency analyses read the type records: a holder whose person class is derived may move, so the key's
  # location is a transport dependency; without the record the holder cannot move and the query is ready
  e = copy.deepcopy(ex["held_object_transport"])
  e["stage1"] = e["stage1"][1:]
  e["stage2"]["logic"] = e["stage2"]["logic"][1:]
  e["text"] = " ".join(p["raw"] for p in e["stage1"])
  rec = compile_gold(e)
  assert [t["entity"] for t in rec["source"]["types"] if t["kind"] == "stage1_person"] == ["Mira 1"]
  assert rec["unsupported"]["reasons"] == ["unsupported_transport_dependency"], rec.get("unsupported")
  source, queries = ap.split_packages(e["stage2"]["logic"])
  bare = ar.compile_source(None, source, "physical_v1")
  assert "types" not in bare and not ar.compile_query(queries[0], bare)["outcome"]
  return "A5: the saved gemini p01 translation gets Ann's person type from Stage 1, the view holds it and the replay " \
         "validates the plan (invalid without it); a robot, an injected conflicting category (note " \
         "conflicting_category), a stated negative, a knower-only and a query-only mention give none; a stated person " \
         "fact needs none; an unlisted class such as passenger is no conflict; the transport analysis reads a derived " \
         "person type"


def check_lexical(ex):
  e = ex["past_first_type"]
  rec = compile_gold(e)
  src = rec["source"]
  assert sorted((t["entity"], t["class"], t["kind"]) for t in src["types"]) == \
    [("b 1", "block", "lexical_identification"), ("table 2", "table", "lexical_identification")], src["types"]
  q = ar.compile_query(rec["queries"][0], src)
  assert q["excluded"] == [{"unit": "S1", "reason": "underspecified_temporal_root"}]
  kept = [n for n in q["selected_clauses"]["source"] if n.startswith("src:types:")]
  assert len(kept) == 2, kept
  goal = rec["queries"][0][2][1]
  assert rp.replay(src, [["take", "hand 3", "b 1"]], goal=goal)["verdict"] == "valid"
  # a present unit keeps its own clause: no type record enters a view for it
  q = ar.compile_query(["@id", "S9", ["question", ["isa", "block", "b 1"]]], src, planning_root="W0")
  assert q["excluded"] == [{"unit": "S1", "reason": "underspecified_temporal_root"}]
  plain = compile_gold(ex["blocks_verify"])["source"]
  assert "types" not in plain

  def variant(mutate):
    x = copy.deepcopy(e)
    mutate(x)
    return compile_gold(x)["source"]
  # knower-scoped: the qualification stays with the unit, and an objective query gets no block type
  def knower(x):
    u = x["stage1"][0]["units"][0]
    u["context"] = {"knower": "hand 3"}
    x["stage2"]["contexts"]["S1"] = {"tense": "past", "knower": "hand 3"}
  src = variant(knower)
  assert "types" not in src and rp.replay(src, [["take", "hand 3", "b 1"]], goal=goal)["verdict"] == "invalid"
  # uncertain, negated and predicated types give no certain positive type
  def uncertain(x):
    x["stage1"][0]["units"][0]["confidence"] = 0.8
    x["stage1"][0]["units"][0]["text"] = "Yesterday block b 1 was probably on the table 2."
    x["stage2"]["logic"][0][2] = ["and", x["stage2"]["logic"][0][2], ["@p", "S1", 0.8]]
  assert "types" not in variant(uncertain)

  def negated(x):
    x["stage2"]["logic"][0][2][2] = ["and", ["not", ["isa", "block", "b 1"]], ["isa", "table", "table 2"],
                                     ["is rel2", "on", "b 1", "table 2"]]
  assert [(t["entity"], t["class"]) for t in variant(negated)["types"]] == [("table 2", "table")]

  def predicated(x):
    x["stage1"][0]["units"][0]["text"] = "Yesterday b 1 was a block on the table 2."
  assert [(t["entity"], t["class"]) for t in variant(predicated)["types"]] == [("table 2", "table")]
  # a class guard is a condition, never a fact
  f = apt.class_condition_findings(units_of(ex["class_guard_unknown"]), ex["class_guard_unknown"]["stage2"]["logic"])
  src = compile_gold(ex["class_guard_unknown"])["source"]
  assert f == [] and not any(t["class"] == "doctor" for t in src.get("types") or [])
  return "A11: block b and the table of a past first mention stay as type records in the plan view (2 clauses) and " \
         "the replay validates the take; a knower-scoped, an uncertain, a negated and a predicated type give no " \
         "record; a class guard never becomes a fact"


def check_robot_route(ex):
  e = ex["robot_rule_public_route"]
  src = compile_gold(e)["source"]
  law = next(u for u in src["units"] if u["id"] == "S4")
  assert [r.get("template") for r in law["clauses"]] == ["tpl_move_public"], law["clauses"]
  fixed = next(u for u in compile_gold(ex["default_rule_applied"])["source"]["units"] if u["id"] == "S1")
  assert {r.get("template") for r in fixed["clauses"] if r.get("template")} == {"tpl_move_stated"}, fixed["clauses"]
  step = [["move", "Robo 1", "Harbor 2", "Hilltown 3", "bus"]]
  goal = ["is rel2", "located_at", "Robo 1", "Hilltown 3"]
  r = rp.replay(src, step, goal=goal)
  assert r["verdict"] == "valid", r
  # the paired control: the same source with "Hilltown is a place." in place of the bus service
  x = copy.deepcopy(e)
  bus = next(p for p in x["stage1"] if p["raw"].startswith("A bus service"))
  bus["raw"] = "Hilltown is a place."
  bus["units"][0].update(text="Hilltown 3 is a place.", type="situation")
  bus["units"][0].pop("confidence", None)
  bus["units"][0]["entities"] = [x2 for x2 in bus["units"][0]["entities"] if x2["id"] == "Hilltown 3"]
  x["stage2"]["logic"] = [["@id", "S3", ["holds", "W0", ["isa", "place", "Hilltown 3"]]] if p[1] == "S3" else p
                          for p in x["stage2"]["logic"]]
  x["text"] = " ".join(p["raw"] for p in x["stage1"])
  src = compile_gold(x)["source"]
  r = rp.replay(src, step, goal=goal)
  assert r["verdict"] == "invalid", r
  # without the rule the robot has no path: the library's movement default is for persons
  src = compile_gold(ex["robot_public_route"])["source"]
  assert rp.replay(src, step, goal=goal)["verdict"] == "invalid"
  return "D5: a robot rule with unconditioned endpoints compiles to tpl_move_public (N3's fixed endpoints to " \
         "tpl_move_stated) and moves Robo over the stated bus connection; without the connection, or without the " \
         "rule, the step is not valid"


def _absent(paths):
  """The saved model responses of `regression/` that are not present: the folder is local and not in the
  repository, so a check that replays them skips that part and says so."""
  return [os.path.relpath(p, HERE) for p in paths if not os.path.exists(p)]


def run():
  ex = examples()
  gone = _absent([SAVED, V3])
  if gone:
    print("  skipped: json repair, envelope, wrapper, messages, semantic and person replay saved responses that are not present "
          "(regression/ is local): %s" % ", ".join(gone))
    parts = [lambda: check_lexical(ex), lambda: check_robot_route(ex)]
  else:
    rows = saved()
    parts = [lambda: check_json_repair(rows), lambda: check_envelope(rows, ex), lambda: check_wrapper(rows, ex),
             lambda: check_messages(rows, ex), lambda: check_semantic(rows, ex), lambda: check_person(rows, ex),
             lambda: check_lexical(ex), lambda: check_robot_route(ex)]
  for part in parts:
    print("  " + part())


if __name__ == "__main__":
  run()
