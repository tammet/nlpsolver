"""Round 4 after the v5 run: the replay's law forms, the verification's negative obligation, the semantic move to
types, the stop-reason rule, the merged messages, the new messages, the narrow typing cleanups, the url fields and the
frame part of a confidence, offline.

The saved v5 responses in regression/v5_translations.json replay through the current code with a fake provider.  They
test the repairs against the rows that motivated them; they say nothing about what a model does with revision H.  Each
cleanup has a negative control where its guard fails and the correction still runs.  No model call, no GK launch.

  R1  the replay reads every law form of the compiler's grammar: quantifiers and conjunctions inside a consequent,
      conjunctions of laws; the saved claude robot rule validates its one-step plan
  R2  "is the egg raw?" after a second step needs negative persistence for its No side only: it runs, and the
      answer policy decides; "is the egg not raw?" is refused before any launch (T2)
  R3  the class of a referent that its own law sentence introduces is moved to types, and only that move is accepted
  R5  a handoff error and the compiler's errors come in one message; errors that v5 hid appear in the first response
  R6  the messages for a types variable, a proper name, a non-entity and an unstated endpoint
  N1-N5  each cleanup on its motivating response, and its negative control
  R7  no url field reaches Stage 2
  R8  the frame axioms' part of a plan confidence
  T1  the drone rule reads the stated air route; without the route no step is valid
"""
import copy
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "solver"))
sys.path.insert(0, HERE)

import action_answer as aa          # noqa: E402
import action_gk as ag              # noqa: E402
import action_pipeline as ap        # noqa: E402
import action_prompt as apt         # noqa: E402
import action_replay as rp          # noqa: E402
import action_route as ar           # noqa: E402
import check_action_round3 as c3    # noqa: E402
import lc_action as la              # noqa: E402

SAVED = os.path.join(HERE, "regression", "v5_translations.json")


def saved():
  with open(SAVED) as f:
    return json.load(f)["rows"]


def row(rows, model, case, mode="natural"):
  return next(r for r in rows if r["model"] == model and r["id"] == case and r["mode"] == mode)


def stage2(r):
  return [h for h in r["history"] if h["stage"] == 2 and h.get("raw") and h.get("kind") != "semantic_correction"]


def attempt(r, h, bundle):
  units, errors = ap.stage1_units(r["stage1_packages"])
  assert not errors, errors
  return ap.stage2_attempt(h["raw"], h.get("finish_reason") or "STOP", r["text"], units, bundle, set())


def gold_attempt(e, s2, bundle):
  units, errors = ap.stage1_units(e["stage1"])
  assert not errors, errors
  return ap.stage2_attempt(json.dumps(s2), "STOP", e["text"], units, bundle, set())


def kinds(att):
  return [n["kind"] for n in att["normalizations"]]


def check_replay_forms(rows, bundle):
  r = row(rows, "claude", "robot_rule_public_route")
  last = stage2(r)[-1]
  tr, _ = c3.translate_with(bundle, r["text"], [json.dumps(r["stage1_packages"])], [last["raw"]])
  s4 = next(p for p in tr["stage2"]["packages"] if p[1] == "S4")[2][2]
  assert s4[0] == "forall" and s4[2][0] == "implies" and s4[2][2][0] == "forall", s4
  plan = [["move", "Robo 1", "Harbor 2", "Hilltown 3", "bus"]]
  res = rp.replay(tr["source"], plan, goal=["is rel2", "located_at", "Robo 1", "Hilltown 3"])
  assert res["verdict"] == "valid", res["reason"]
  # every law form of lc_action._law_shape: quantifiers, conjunctions, an implication, and each head kind
  can = lambda a, t="Hilltown 3": ["can", a, ["move", a, "Harbor 2", t, "bus"]]
  cond = ["isa", "robot", "X"]
  forms = {
    "availability": [can("Robo 1"), ["implies", ["isa", "robot", "Robo 1"], can("Robo 1")],
                     ["forall", "X", ["implies", cond, can("X")]],
                     ["forall", "X", ["implies", cond, ["forall", "T", can("X", "T")]]],
                     ["forall", "X", ["implies", cond, ["and", can("X"), can("X", "Island 4")]]],
                     ["forall", "X", ["implies", cond, ["and", ["forall", "T", can("X", "T")], can("X")]]],
                     ["and", can("Robo 1"), can("Robo 1", "Island 4")],
                     ["and", ["forall", "X", ["implies", cond, can("X")]], ["implies", ["isa", "robot", "Robo 1"], can("Robo 1")]],
                     ["forall", "X", ["implies", cond, ["normally", can("X")]]],
                     ["forall", "X", ["implies", cond, ["forall", "T", ["normally", can("X", "T")]]]]],
    "denial": [["not", can("Robo 1")], ["forall", "X", ["implies", cond, ["not", can("X")]]],
               ["forall", "X", ["implies", cond, ["forall", "T", ["not", can("X", "T")]]]]],
    "effect": [["after", ["move", "Robo 1", "Harbor 2", "Hilltown 3", "bus"], ["has property", "tired", "Robo 1"]],
               ["forall", "X", ["implies", cond, ["forall", "T", ["after", ["move", "X", "Harbor 2", "T", "bus"],
                                                                     ["has property", "tired", "X"]]]]]],
    "restriction": [["forall", "X", ["implies", ["and", cond, ["executable", ["move", "X", "Harbor 2", "Hilltown 3", "bus"]]],
                                     ["has property", "fuelled", "X"]]],
                    ["and", ["implies", ["executable", ["move", "Robo 1", "Harbor 2", "Hilltown 3", "bus"]],
                             ["has property", "fuelled", "Robo 1"]],
                     ["implies", ["executable", ["move", "Robo 1", "Harbor 2", "Island 4", "bus"]],
                      ["has property", "fuelled", "Robo 1"]]]]}
  base = [["@id", "S1", ["holds", "W0", ["isa", "robot", "Robo 1"]]],
          ["@id", "S2", ["holds", "W0", ["is rel2", "located_at", "Robo 1", "Harbor 2"]]]]
  ents = {"Robo 1": "robot", "Harbor 2": "place", "Hilltown 3": "place", "Island 4": "place"}
  n = 0
  for form, laws in forms.items():
    for law in laws:
      src = ar.compile_source(None, base + [["@id", "S3", ["holds", "W0", law]]], la.PROFILE, entities=ents)
      u = next(x for x in src["units"] if x["id"] == "S3")
      assert u["status"] == "supported" and u["form"] in (form, "availability" if form == "denial" else form), \
        (form, law, u["status"], u["diagnostics"])
      assert la.law_shape(law) is not None, law
      rp.Source(src)                  # raises NotChecked for a form outside the replay's fragment
      n += 1
  # K12 of the planning fixes: every state-rule form that the compiler accepts replays without an exception; a strict
  # literal rule gives a checked initial state, and a default, a disjunction, a quantifier in the consequent or a
  # standing law outside forall(implies(body, fluent)) gives not_checked, never a strict reading
  sbase = [["@id", "S1", ["holds", "W0", ["and", ["isa", "block", "a 1"], ["has property", "clear_top", "a 1"]]]],
           ["@id", "S2", ["holds", "W0", ["and", ["isa", "block", "b 2"], ["has property", "clear_top", "b 2"]]]]]
  sents = {"a 1": "block", "b 2": "block"}
  c, h = ["has property", "clear_top", "X"], ["has property", "usable", "X"]
  states = {
    "valid": [["forall", "X", ["implies", c, h]],
              ["implies", ["has property", "clear_top", "a 1"], ["has property", "usable", "a 1"]],
              ["forall", "X", ["implies", c, ["and", h, ["has property", "red", "X"]]]],
              ["forall", "X", ["implies", c, ["not", h]]],
              ["forall", "X", ["implies", ["isa", "block", "X"], ["isa", "thing", "X"]]],
              ["state_law", ["forall", "X", ["implies", c, h]]]],
    "not_checked": [["forall", "X", ["implies", c, ["normally", h]]],
                    ["normally", ["forall", "X", ["implies", c, h]]],
                    ["forall", "X", ["implies", c, ["or", h, ["has property", "red", "X"]]]],
                    ["forall", "X", ["implies", c, ["exists", "Y", ["is rel2", "on", "Y", "X"]]]],
                    ["forall", "X", ["implies", c, ["forall", "Y", ["implies", ["is rel2", "on", "Y", "X"],
                                                                        ["has property", "red", "Y"]]]]],
                    ["state_law", ["forall", "X", ["implies", c, ["normally", h]]]],
                    ["state_law", ["forall", "X", ["implies", c, ["not", h]]]],
                    ["state_law", ["forall", "X", ["implies", c, ["and", h, ["has property", "red", "X"]]]]]]}
  m = 0
  for verdict, rules in states.items():
    for rule in rules:
      for pkg in (["@id", "S3", ["holds", "W0", rule]], ["@id", "S3", ["and", ["holds", "W0", rule], ["@p", "S3", 0.9]]]):
        src = ar.compile_source(None, sbase + [pkg], la.PROFILE, entities=sents)
        u = next(x for x in src["units"] if x["id"] == "S3")
        assert u["status"] == "supported" and u["form"] in ("description_initial", "description_static", "state_law"), \
          (rule, u["status"], u["form"])
        got = rp.replay(src, [])
        assert got["verdict"] == verdict and got["uncovered"] != "replay_error", (rule, got["verdict"], got["reason"])
        m += 1
  return "R1: the saved claude robot rule (forall inside the consequent) validates its one-step plan; %d law forms " \
         "of the compiler's grammar are read by the replay; K12: %d state-rule forms replay without an exception, " \
         "a default or a non-literal consequent as not_checked" % (n, m)


def negative_persistence_raw(ex):
  e = copy.deepcopy(ex["negative_persistence"])
  q = e["stage1"][-1]
  q["raw"] = "After Nia cooks the egg with the pan and then puts the pan inside the box, is the egg raw?"
  q["units"][0]["text"] = ("After Nia 1 cooks the egg 3 with the pan 2 and then puts the pan 2 inside the box 4, is the "
                           "egg 3 raw?")
  q["units"][0]["adjectives"] = [["raw", "none", "entity"]]
  e["stage2"]["logic"][-1][2][2] = ["has property", "raw", "egg 3"]
  e["text"] = " ".join(p["raw"] for p in e["stage1"])
  return e


def check_negative_obligation(ex):
  """T2: only the negative obligation of the final formula reads the carried negative, so the query runs and the
  answer policy decides (check_action_answer.py tests the answers on x03_partial_effects)."""
  e = negative_persistence_raw(ex)
  rec = c3.compile_gold(e)
  qa = ar.compile_query(e["stage2"]["logic"][-1], rec["source"])
  assert qa["outcome"] is None and ag.planned_launches(qa), qa["outcome"]
  need = [r for r in qa["backend_requirements"] if r["capability"] == "negative_persistence"]
  assert len(need) == 1 and need[0]["polarities"] == ["negative"], qa["backend_requirements"]
  assert all(h["read_by"] == "final formula" for h in need[0]["evidence"]), need[0]["evidence"]
  ok = ar.compile_query(e["stage2"]["logic"][-1], rec["source"], None, {"validated": ["negative_persistence"]})
  assert ok["outcome"] is None and ok["obligations"], ok["outcome"]
  # the question with its literal negated reads the negative in its positive obligation: refused before any launch
  neg = copy.deepcopy(e["stage2"]["logic"][-1])
  neg[2][2] = ["not", neg[2][2]]
  qn = ar.compile_query(neg, rec["source"])
  assert qn["outcome"]["outcome"] == "unsupported_backend_requirement" and ag.planned_launches(qn) == [], qn["outcome"]
  return "R2/T2: \"is the egg raw?\" after a second step needs negative persistence for its No side only: it compiles " \
         "with its obligations and a requirement with polarities [negative]; \"is the egg not raw?\" is refused " \
         "before any launch"


def check_semantic_move(ex, bundle):
  e = copy.deepcopy(ex["class_guard_holds"])
  s2 = copy.deepcopy(e["stage2"])
  s2.pop("types")
  s3 = next(p for p in s2["logic"] if p[1] == "S3")
  s3[2][2][1] = s3[2][2][1] + [["isa", "fence", "fence 3"]]
  moved = copy.deepcopy(e["stage2"])
  removed = copy.deepcopy(e["stage2"])
  removed.pop("types")
  base, sent = c3.translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(s2)], semantic=False)
  f = base["class_condition_findings"]
  assert [(x["atom"], x["confidence"], x["repair"]) for x in f] == [(["isa", "fence", "fence 3"], "high", "move_to_types")], f
  tr, sent = c3.translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(s2), json.dumps(moved)])
  assert tr["semantic_correction"]["status"] == "accepted" and tr["stage2"]["types"] == {"S3": [["isa", "fence", "fence 3"]]}
  assert "goes to the envelope field types" in sent[-1][1]
  tr, _ = c3.translate_with(bundle, e["text"], [json.dumps(e["stage1"])], [json.dumps(s2), json.dumps(removed)])
  assert tr["semantic_correction"]["status"] == "refused" and "types" in tr["semantic_correction"]["reason"], \
    tr["semantic_correction"]
  # a guard of another entity keeps the plain removal
  f = apt.class_condition_findings(c3.units_of(ex["conditional_signed_effect"]), [
    ["@id", "S4", ["holds", "W0", ["implies", ["and", ["have", "Nia 1", "pan 3"], ["isa", "person", "Nia 1"]],
                                   ["can", "Nia 1", ["change", "Nia 1", "egg 2", "cooked", "pan 3"]]]]]])
  assert [x["repair"] for x in f] == ["remove"], f
  return "R3: a fence class written as a condition of its own law sentence is asked to move to types; the move is " \
         "accepted, a plain removal is refused; an invented person guard keeps the removal"


def check_merged(rows, bundle):
  r = row(rows, "gemini", "route_vs_permission_other_person")
  att = attempt(r, stage2(r)[0], bundle)
  assert att["merged"] >= 1 and any("query reading/package mismatch" in x for x in att["errors"]) and \
    any("unknown_predicate" in x for x in att["errors"]), att["errors"]
  # the unstated endpoints of gemini's robot rule ("Every robot can travel by bus") are bound by K6 of the planning
  # fixes, so the endpoint message of R5 no longer arises for it; the message stays for a law that K6 does not cover
  r = row(rows, "gemini", "robot_rule_public_route")
  att = attempt(r, stage2(r)[0], bundle)
  assert not any("universally quantified variable" in x for x in att["errors"]) and "types_dropped" in kinds(att) \
    and "travel_endpoints_bound" in kinds(att), att
  r = row(rows, "gemini", "worked_c10_ticket_or_pass")
  first, second = [attempt(r, h, bundle) for h in stage2(r)[:2]]
  assert any("https://" in x for x in first["errors"]) and kinds(first) == ["types_dropped", "types_dropped"], first
  assert second["errors"] == [] and kinds(second) == ["types_dropped", "types_dropped"], second
  # an invalid selection is replaced by the derived one and recorded, so it never reaches the compiler (it raised a
  # TypeError there once)
  r = row(rows, "gemini", "past_fact_excluded")
  att = attempt(r, stage2(r)[0], bundle)
  note = [n for n in att["normalizations"] if n["kind"] == "derived_field" and n["field"] == "query_contexts"]
  assert note and note[0]["model"]["S2"] == {"tense": "present"} and "tense" not in json.dumps(att["selections"]), att
  # every saved Stage-2 response of the v3, v4 and v5 extracts passes through the controller without an exception
  n = 0
  for name in ("v3", "v4", "v5"):
    with open(os.path.join(HERE, "regression", "%s_translations.json" % name)) as f:
      for r in json.load(f)["rows"]:
        units, errors = ap.stage1_units(r["stage1_packages"])
        for h in stage2(r):
          ap.stage2_attempt(h["raw"], h.get("finish_reason"), r["text"], units, bundle, set())
          n += 1
  return "R5: the query-form error and the compiler's error of gemini route_vs_permission come in one message; the " \
         "unstated endpoints of gemini's robot rule are bound (K6) and the url ids of worked_c10, hidden in v5, now " \
         "appear in the first response; worked_c10's second response is accepted; an invalid selection is replaced by the derived " \
         "one; %d saved responses of v3, v4 and v5 pass the controller without an exception" % n


def check_messages(ex):
  units = c3.units_of(ex["worked_c10_ticket_or_pass"])
  law = next(u["unit_id"] for u in units if u.get("action_reading") == "availability")
  msg = lambda a: apt.types_errors(units, {law: [a]})
  assert "Y is a variable of the rule; its class stays in the rule's guard" in msg(["isa", "ticket", "Y"])[0]
  assert "is a proper name; a proper name gets no class" in msg(["isa", "Robo", "Robo 1"])[0]
  assert "bus service is no entity of Stage 1; a service or a route is a connected fact" in msg(["isa", "bus service", "bus service"])[0]
  rep = la.Report("S4")
  la.check_term("unspecified", {"A"}, rep, [2], None, "from")
  assert "universally quantified variable" in rep.items[0]["message"]
  src = ar.compile_source(None, [["@id", "S1", ["holds", "W0", ["isa", "Dock", "Dock 3"]]]], la.PROFILE)
  assert "Dock 3 is a proper name" in src["units"][0]["diagnostics"][0]["message"]
  return "R6: a types variable, a proper name, a non-entity and an unstated endpoint get messages that name the fault"


def check_cleanups(rows, ex, bundle):
  out = []
  # N1: a description's class in types goes into its formula
  e = ex["possession_and_holding"]
  s2 = copy.deepcopy(e["stage2"])
  s2["logic"][1][2][2] = ["have", "Robo 1", "key 2"]
  s2["types"]["S2"] = [["isa", "key", "key 2"]]
  att = gold_attempt(e, s2, bundle)
  assert att["errors"] == [] and "types_relocated" in kinds(att) and att["packages"] == e["stage2"]["logic"], att["errors"]
  # two relocated atoms keep their order in types, ahead of the relation
  g = ex["new_gripper_hand"]
  s2g = copy.deepcopy(g["stage2"])
  s2g["logic"][1][2][2] = ["is rel2", "on", "a 2", "table 4"]
  s2g["types"] = {"S2": [["isa", "block", "a 2"], ["isa", "table", "table 4"]]}
  att = gold_attempt(g, s2g, bundle)
  assert att["errors"] == [] and kinds(att) == ["types_relocated"] * 2 and att["packages"] == g["stage2"]["logic"]
  for label, mutate in (("a class the unit's text does not name", lambda s: s["types"].update(S2=[["isa", "tool", "key 2"]])),
                        ("an entity the unit does not mention", lambda s: s["types"].update(S2=[["isa", "box", "box 3"]]))):
    bad = copy.deepcopy(s2)
    mutate(bad)
    att = gold_attempt(e, bad, bundle)
    assert "types_relocated" not in kinds(att) and any("a description states its class facts" in x for x in att["errors"]), \
      (label, att["errors"])
  prob = copy.deepcopy(e)
  u2 = prob["stage1"][1]["units"][0]
  u2.update(text="Robo 1 probably has the key 2.", confidence=0.8)
  prob["stage1"][1]["raw"] = "Robo probably has the key."
  prob["text"] = " ".join(p["raw"] for p in prob["stage1"])
  bad = copy.deepcopy(s2)
  bad["logic"][1][2] = ["and", ["holds", "W0", ["have", "Robo 1", "key 2"]], ["@p", "S2", 0.8]]
  att = gold_attempt(prob, bad, bundle)
  assert "types_relocated" not in kinds(att) and any("a description states its class facts" in x for x in att["errors"])
  out.append("N1 relocates a description's classes in their order in types (3 negative controls keep the correction)")
  # N2: the saved worked_c10 second response; an entry for another unit's entity keeps its message
  bad = copy.deepcopy(e["stage2"])
  bad["types"]["S4"].append(["isa", "robot", "Robo 1"])
  att = gold_attempt(e, bad, bundle)
  assert "types_dropped" not in kinds(att) and any("Robo 1 is first named in unit S1" in x for x in att["errors"]), att
  out.append("N2 drops variable and non-entity entries (saved worked_c10); another unit's entity keeps its message")
  # N3: the saved route_vs second response; a differing capital and an antecedent keep their messages
  r = row(rows, "gemini", "route_vs_permission_other_person")
  att = attempt(r, stage2(r)[1], bundle)
  assert att["errors"] == [] and kinds(att).count("self_class_dropped") == 2
  e3 = ex["route_vs_permission_other_person"]
  for label, atom_place in (("a capital that differs from the name", "description"), ("inside a rule antecedent", "rule")):
    bad = copy.deepcopy(e3["stage2"])
    s3 = next(p for p in bad["logic"] if p[1] == "S3")
    if atom_place == "description":
      s3[2][2] = ["and", ["isa", "City", "Dock 3"], s3[2][2]]
      want = "a class name is a lexical constant"
    else:
      s6 = next(p for p in bad["logic"] if p[1] == "S6")
      s6[2][2] = ["implies", ["isa", "Dock", "Dock 3"], s6[2][2]]
      want = "Dock 3 is a proper name"
    att = gold_attempt(e3, bad, bundle)
    assert "self_class_dropped" not in kinds(att) and any(want in x for x in att["errors"]), (label, att["errors"])
  out.append("N3 drops a place's own-name class (saved route_vs); a differing capital and an antecedent keep messages")
  # N4 is now part of the derived envelope: an explicit root that Stage 1 does not state is replaced by the derived
  # selection and recorded, with one world or two
  for case in ("travel_goal", "default_root_two_snapshots"):
    e4 = ex[case]
    q = e4["stage2"]["logic"][-1][1]
    att = gold_attempt(e4, dict(copy.deepcopy(e4["stage2"]), query_contexts={q: {"planning_root": "W0"}}), bundle)
    assert att["errors"] == [] and kinds(att) == ["derived_field"] and att["selections"] == e4["stage2"]["query_contexts"]
    assert att["normalizations"][0]["model"] == {q: {"planning_root": "W0"}}, att["normalizations"]
  out.append("N4: an explicit root W0 that Stage 1 does not state is replaced by the derived selection and recorded, "
             "with one world or two")
  # N5: a later law unit that names the class noun; a later unit that does not
  s2 = copy.deepcopy(e["stage2"])
  s2["types"]["S4"].append(["isa", "key", "key 2"])
  att = gold_attempt(e, s2, bundle)
  assert att["errors"] == [] and "later_class_accepted" in kinds(att)
  out.append("N5 accepts a later class the unit's text names (the other case: see N2)")
  return "cleanups: " + "; ".join(out)


def check_urls(ex, bundle):
  e = copy.deepcopy(ex["new_tartu_train"])
  s1 = copy.deepcopy(e["stage1"])
  s1[1]["units"][0]["entities"][1]["url"] = "https://en.wikipedia.org/wiki/Tartu"
  tr, sent = c3.translate_with(bundle, e["text"], [json.dumps(s1)], [json.dumps(e["stage2"])])
  assert tr["status"] == "ok" and "wikipedia" not in sent[1][1] and "wikipedia" in json.dumps(tr["stage1_packages"])
  return "R7: an entity's url stays in the accepted Stage 1 and does not reach the Stage-2 request"


def check_frame_parts():
  path = os.path.join(ROOT, "elogs", "round3_2026_09_29", "gold_gk_v5", "worked_p03_food", "record.json")
  if not os.path.exists(path):
    return "R8: skipped (no saved gold proof on this machine)"
  res = json.load(open(path))["answers"][0]["result"]
  parts = aa.confidence_parts(res["proof"]["proof"])
  assert parts["frame_uses"] == {"frame_have": 3} and parts["frame_product"] == res["confidence"] == 0.9703, parts
  assert parts["other_uncertain_uses"] == {} and parts["other_product"] == 1.0
  return "R8: worked_p03_food's plan confidence 0.9703 is three uses of frame_have and no stated probability"


def check_drone(ex):
  e = ex["drone_rule_air_route"]
  src = c3.compile_gold(e)["source"]
  step = [["move", "Zip 1", "Tartu 2", "Tallinn 3", "air"]]
  goal = ["is rel2", "located_at", "Zip 1", "Tallinn 3"]
  assert rp.replay(src, step, goal=goal)["verdict"] == "valid"
  law = next(u for u in src["units"] if u["id"] == "S4")
  assert [x.get("template") for x in law["clauses"]] == ["tpl_move_public"]
  assert not any(t["class"] == "person" for t in src.get("types") or [])
  x = copy.deepcopy(e)
  route = x["stage1"][2]
  route["raw"] = "Tallinn is a place."
  route["units"][0].update(text="Tallinn 3 is a place.", type="situation")
  route["units"][0].pop("confidence", None)
  route["units"][0]["entities"] = [y for y in route["units"][0]["entities"] if y["id"] == "Tallinn 3"]
  x["stage2"]["logic"][2] = ["@id", "S3", ["holds", "W0", ["isa", "place", "Tallinn 3"]]]
  x["text"] = " ".join(p["raw"] for p in x["stage1"])
  assert rp.replay(c3.compile_gold(x)["source"], step, goal=goal)["verdict"] == "invalid"
  return "T1: the drone rule compiles to tpl_move_public and moves Zip over the stated air route; without the route " \
         "the step is not valid"


def _absent(paths):
  """The saved model responses of `regression/` that are not present: the folder is local and not in the
  repository, so a check that replays them skips that part and says so."""
  return [os.path.relpath(p, HERE) for p in paths if not os.path.exists(p)]


def run():
  ex = c3.examples()
  bundle = apt.assemble()
  gone = _absent([SAVED] + [os.path.join(HERE, "regression", "%s_translations.json" % n) for n in ("v3", "v4")])
  if gone:
    print("  skipped: replay forms, merged and cleanups replay saved responses that are not present (regression/ is local): %s" % ", ".join(gone))
    parts = [lambda: check_negative_obligation(ex), lambda: check_semantic_move(ex, bundle), lambda: check_messages(ex),
             lambda: check_urls(ex, bundle), lambda: check_frame_parts(), lambda: check_drone(ex)]
  else:
    rows = saved()
    parts = [lambda: check_replay_forms(rows, bundle), lambda: check_negative_obligation(ex),
             lambda: check_semantic_move(ex, bundle), lambda: check_merged(rows, bundle), lambda: check_messages(ex),
             lambda: check_cleanups(rows, ex, bundle), lambda: check_urls(ex, bundle), lambda: check_frame_parts(),
             lambda: check_drone(ex)]
  for part in parts:
    print("  " + part())


if __name__ == "__main__":
  run()
