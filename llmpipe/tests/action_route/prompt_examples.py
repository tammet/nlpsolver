#!/usr/bin/env python3
"""The authored examples and routing contrasts of the action route: each compiles, the controller accepts it, the
example files are in their layout (json_layout.py), and the prompt manifest is current; no model or GK invocation.

The examples that the prompts show are in prompts/actions/, the others in tests/action_route/unseen/; this check
reads both.  --show stage1|stage2 prints the assembled prompt; --manifest prints the prompts' identity.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "solver"))
import action_pipeline as ap
import action_prompt as apt
import action_route as ar
import lc_action as la

import json_layout

UNSEEN = Path(__file__).resolve().parent / "unseen"


def corpus():
  """Every authored example: those that the prompts show, then those that no prompt shows."""
  return json.loads((apt.PROMPTS / "examples.json").read_text()) + json.loads((UNSEEN / "examples.json").read_text())


def routing_cases():
  """Every routing contrast: those that the Stage-1 prompt shows, then those that no prompt shows."""
  return (json.loads((apt.PROMPTS / "routing_cases.json").read_text())
          + json.loads((UNSEEN / "routing_cases.json").read_text()))


def compile_example(e):
  units, errors = ap.stage1_units(e["stage1"])
  assert not errors, (e["id"], errors)
  assert " ".join(p["raw"] for p in e["stage1"]) == e["text"], (e["id"], "raw coverage")
  assert apt.select_route(units)["route_selected"] == e["route"], e["id"]
  got, errors = ap.stage2_packages(e["stage2"])
  assert not errors, (e["id"], errors)
  worlds, contexts, packages = got
  errors = apt.handoff_errors(units, e["stage2"], packages)
  assert not errors, (e["id"], errors)
  src, qs = ap.split_packages(packages)
  record = {"query_contexts": e["stage2"].get("query_contexts", {})}
  stop = ap.compile_translation(record, e["text"], units, worlds, contexts, src, qs, (), e["stage2"].get("types"))
  assert stop in ([], "unsupported"), (e["id"], stop)
  source = record["source"]
  exp = e["expect"]
  assert source["support"]["status"] == exp["source"], (e["id"], source["support"])
  if exp.get("reason"):
    assert exp["reason"] in source["support"]["reasons"], (e["id"], source["support"])
  forms = {u["id"]: u["form"] for u in source["units"]}
  for uid, form in exp.get("forms", {}).items():
    assert forms.get(uid) == form, (e["id"], uid, forms)
  compiled = []
  for q in qs:
    qa = ar.compile_query(q, source, **record["query_contexts"].get(q[1], {}))
    outcome = (qa.get("outcome") or {}).get("outcome") or "ready"
    assert outcome == exp["queries"], (e["id"], outcome, qa.get("diagnostics"))
    if "query_reason" in exp:
      assert exp["query_reason"] in qa["outcome"]["reasons"], (e["id"], qa["outcome"])
    if "root" in exp:
      assert qa["planning_root"] == exp["root"], e["id"]
    if "excluded" in exp:
      assert [{"unit": x["unit"], "reason": x["reason"]} for x in qa["excluded"]] == exp["excluded"], e["id"]
    compiled.append(qa)
  return source, compiled


def mutations(examples):
  cases = {e["id"]: e for e in examples}
  checks = 0
  for field, value in (("step_bound", "two"), ("step_bound", {"comparison": "at_most", "count": True}),
                       ("action_order", "random"), ("action_reading", []),
                       ("action_issue", "oops"), ("planning_root", "W77"),
                       ("ambient", "undeclared 99"), ("context", {"tense": "yesterday"})):
    e = copy.deepcopy(cases["travel_goal"])
    e["stage1"][-1]["units"][0][field] = value
    assert ap.stage1_units(e["stage1"])[1], field
    checks += 1
  for name, mutate in (
      ("world_selection", lambda e: e["stage2"]["query_contexts"].clear()),
      ("scope_and_knower", lambda e: e["stage2"]["contexts"].clear()),
      ("travel_goal", lambda e: e["stage2"]["logic"][-1][2].pop()),
      ("travel_goal", lambda e: e["stage2"]["logic"].pop(0)),
      ("travel_goal", lambda e: e["stage2"]["logic"].append(e["stage2"]["logic"][0])),
      ("explicit_point99", lambda e: e["stage2"]["logic"][2].__setitem__(2, e["stage2"]["logic"][2][1])),
  ):
    e = copy.deepcopy(cases[name]); mutate(e)
    units, _ = ap.stage1_units(e["stage1"])
    assert apt.handoff_errors(units, e["stage2"], e["stage2"]["logic"]), name
    checks += 1
  # Order is checkable when the mapped participants distinguish the steps.
  # Two different verbs with identical mapped participants require semantic
  # translation review; an extra-role ban is not a sound substitute for that.
  actions = [{"root": "take", "roles": {"actor": "Ann 1", "target": b}}
             for b in ("a 2", "b 3")]
  # K3: the roles are compared as declared concrete ids
  units = [{"unit_id": "Q", "type": "query", "action_reading": "verify_question",
            "action_order": "sequence", "actions": actions,
            "entities": [{"id": x, "type": "concrete"} for x in ("Ann 1", "a 2", "b 3")]}]
  packages = [["@id", "Q", ["verify", [["take", "Ann 1", "a 2"],
                                       ["take", "Ann 1", "b 3"]], ["have", "Ann 1", "b 3"]]]]
  assert not apt.handoff_errors(units, {}, packages)
  packages[0][2][1].reverse()
  assert apt.handoff_errors(units, {}, packages)
  checks += 1
  return checks


def translation_checks(examples):
  # Feed authored responses through the real two-stage controller; isolate the
  # model boundary. Source compilation and query selection are production code.
  count = 0
  for e in examples:
    with patch.object(ap.llmcall, "call_llm", side_effect=[json.dumps(e["stage1"]), json.dumps(e["stage2"])]) as call:
      record = ap.translate(e["text"], apt.assemble())
    expected = "unsupported_translation" if e["expect"]["source"] == "unsupported" or e["expect"]["queries"] == "unsupported_translation" else "ok"
    assert record["status"] == expected, (e["id"], record["status"], record["errors"])
    # the Stage-2 input is the accepted Stage 1 without the entities' url fields (round 4, R7)
    assert json.loads(call.call_args_list[1].args[1]) == ap.without_urls(e["stage1"]), "raw packages lost"
    assert record["stage1_packages"] == e["stage1"], "the accepted Stage 1 lost a field"
    assert record["query_contexts"] == e["stage2"]["query_contexts"], "selection lost"
    count += 1
  return count


def boundary_checks(examples):
  cases = {e["id"]: e for e in examples}
  # Correction changes the representation, not the source meaning.
  e = cases["uncertain_source"]
  bad = copy.deepcopy(e["stage2"])
  bad["logic"][2][2] = ["and", ["holds", "W0", ["exists", "E", ["and",
      ["isa", "event", "E"], ["has type", "E", "go"], ["has actor", "E", "Robo 1"],
      ["has source", "E", "Harbor 2", "from"], ["has destination", "E", "Hilltown 3", "to"],
      ["has means", "E", "bus", "by"]]]], ["@p", "S3", 0.8]]
  with patch.object(ap.llmcall, "call_llm", side_effect=[json.dumps(e["stage1"]), json.dumps(bad), json.dumps(e["stage2"])]) as call:
    rec = ap.translate(e["text"], apt.assemble())
  assert rec["status"] == "ok" and call.call_count == 3, rec
  assert "reading_form_mismatch" in call.call_args_list[2].args[1]
  # Check selection at the final solver dispatch, not only query preflight.
  e = cases["scope_and_knower"]
  with patch.object(ap.llmcall, "call_llm", side_effect=[json.dumps(e["stage1"]), json.dumps(e["stage2"])]) , patch.object(ap, "solve_one_query", return_value={"outcome": "verification_result", "answer": "Unknown"}) as solve:
    ap.run_text(e["text"], {"bundle": ap.DEFAULT_BUNDLE, "think": False}, {}, {"gk_calls": []}, None, None, None)
  assert solve.call_args.args[-1] == e["stage2"]["query_contexts"]["S4"]
  for e in routing_cases():
    if e["route"] != "diagnostic":
      continue
    with patch.object(ap.llmcall, "call_llm", return_value=json.dumps(e["stage1"])) as call:
      rec = ap.translate(e["text"], apt.assemble())
    assert rec["status"] == "unsupported_translation" and call.call_count == 1, rec


def review_repairs(examples):
  """Fable N1–N6: qualifiers, roles, open verbs and diagnostic precision."""
  cases = {e["id"]: e for e in examples}
  units, errors = ap.stage1_units(cases["occurrence_not_permission"]["stage1"])
  assert not errors
  expected, _ = apt.contexts_for(units)
  assert expected == {"S1": {"tense": "past"}}, expected
  wrong = copy.deepcopy(cases["occurrence_not_permission"]["stage2"])
  del wrong["contexts"]["S1"]
  errors = apt.handoff_errors(units, wrong, wrong["logic"])
  assert any('unit S1: context should be {"tense": "past"}' in x for x in errors), errors
  wrong = copy.deepcopy(cases["occurrence_not_permission"]["stage2"])
  wrong["contexts"]["S2"] = {"tense": "past"}
  assert any("unit S2: context should be null" in x for x in apt.handoff_errors(units, wrong, wrong["logic"]))
  for reading in ("availability", "restriction", "effect"):
    u = {"unit_id": "T", "type": "strict_rule", "action_reading": reading,
         "time": "until noon", "state_tense": "present"}
    assert apt.contexts_for([u]) == ({}, {}), reading
  for time, state_tense, expected_tense in (("past", None, "past"), ("yesterday", "past", "past")):
    u = {"unit_id": "T", "type": "situation", "time": time}
    if state_tense:
      u["state_tense"] = state_tense
    assert apt.contexts_for([u])[0] == {"T": {"tense": expected_tense}}
  u = copy.deepcopy(units[0])
  u["context"] = {"tense": "past"}
  assert any("tense uses time/state_tense" in x for x in apt.validate_units([u]))

  base = cases["blocks_verify"]
  for take_root, put_root in (("pick", "place"), ("grab", "stack"), ("pick up", "set")):
    e = copy.deepcopy(base)
    actions = e["stage1"][-1]["units"][0]["actions"]
    actions[0]["root"], actions[1]["root"] = take_root, put_root
    compile_example(e)
  for alias in ("means", "support", "container"):
    e = copy.deepcopy(base)
    roles = e["stage1"][-1]["units"][0]["actions"][1]["roles"]
    roles[alias] = roles.pop("location")
    assert any("unknown roles " + alias in x for x in ap.stage1_units(e["stage1"])[1])
  e = copy.deepcopy(base)
  e["stage2"]["logic"][-1][2][1][1][0] = "put_in"
  units, _ = ap.stage1_units(e["stage1"])
  assert any("order/participants mismatch" in x for x in apt.handoff_errors(units, e["stage2"], e["stage2"]["logic"]))

  # Revision-C re-review R1/R2: ordinary extra roles do not invalidate a
  # constructor, and a matching preposition cannot erase a wrong participant.
  e = copy.deepcopy(base)
  e["stage1"][-1]["units"][0]["actions"][0]["roles"]["source"] = "table 4"
  compile_example(e)
  for keep_instrument in (False, True):
    e = copy.deepcopy(cases["conditional_signed_effect"])
    roles = e["stage1"][-1]["units"][0]["actions"][0]["roles"]
    roles.update(location=roles["instrument"], location_prep="in")
    if not keep_instrument:
      del roles["instrument"]
    compile_example(e)
  e = copy.deepcopy(base)
  e["stage1"][-1]["units"][0]["actions"][1]["roles"]["instrument"] = "table 4"
  compile_example(e)
  e["stage2"]["logic"][-1][2][1][1][1] = "block 3"
  units, _ = ap.stage1_units(e["stage1"])
  assert any("order/participants mismatch" in x for x in apt.handoff_errors(units, e["stage2"], e["stage2"]["logic"]))

  # A well-formed event is unsupported in the formal compiler, but an action
  # reading reified this way receives a bounded correction at the English boundary.
  base = cases["open_values_unspecified_tool"]
  for root in ("zap", "boil", "fry"):
    e = copy.deepcopy(base)
    e["stage1"][1]["units"][0]["actions"][0]["root"] = root
    for reading in ("availability", "restriction", "effect"):
      e["stage1"][1]["units"][0]["action_reading"] = reading
      units, errors = ap.stage1_units(e["stage1"])
      assert not errors, errors
      bad = copy.deepcopy(e["stage2"])
      bad["logic"][1][2][2] = ["exists", "E", ["and", ["capability", "E"],
          ["has type", "E", root], ["has actor", "E", "Zed 1"],
          ["has target", "E", "gronk 2"]]]
      src, qs = ap.split_packages(bad["logic"])
      errors = ap.compile_translation({}, e["text"], units, bad["worlds"], bad["contexts"], src, qs)
      assert isinstance(errors, list) and any("unit S2: reading_form_mismatch" in x for x in errors), errors
      # The same correction must occur when the event also has invalid arity.
      bad["logic"][1][2][2][2][2].append("extra")
      errors = ap.compile_translation({}, e["text"], units, bad["worlds"], bad["contexts"], src, qs)
      assert isinstance(errors, list) and any("unit S2: reading_form_mismatch" in x for x in errors), errors
  bad = copy.deepcopy(base["stage2"])
  bad["logic"][1][2][2] = ["exists", "E", ["and", ["capability", "E"],
      ["has type", "E", "zap"], ["has actor", "E", "Zed 1"], ["has target", "E", "gronk 2"]]]
  with patch.object(ap.llmcall, "call_llm", side_effect=[json.dumps(base["stage1"]), json.dumps(bad),
                                                      json.dumps(base["stage2"])]) as call:
    rec = ap.translate(base["text"], apt.assemble())
  assert rec["status"] == "ok" and call.call_count == 3, rec
  assert "unit S2: reading_form_mismatch" in call.call_args_list[2].args[1]
  # A genuinely unrepresentable operation may keep a valid event after the
  # clarification. It must remain unsupported, never be forced into change.
  unsupported = copy.deepcopy(base)
  sentence = "Zed can create the gronk."
  unsupported["stage1"][1]["raw"] = sentence
  u = unsupported["stage1"][1]["units"][0]
  u["text"] = "Zed 1 can create the gronk 2."
  u["actions"][0]["root"] = "create"
  del u["actions"][0]["roles"]["result"]
  u.pop("adjectives", None)
  unsupported["text"] = " ".join(p["raw"] for p in unsupported["stage1"])
  bad["logic"][1][2][2][2][2][2] = "create"
  with patch.object(ap.llmcall, "call_llm", side_effect=[json.dumps(unsupported["stage1"]),
                                                      json.dumps(bad), json.dumps(bad)]) as call:
    rec = ap.translate(unsupported["text"], apt.assemble())
  assert rec["status"] == "unsupported_translation" and call.call_count == 3, rec
  assert rec["unsupported"]["reasons"] == ["unsupported_action_kind"], rec
  print("  review repairs: occurrence tense and unit diagnostic; law timing; rejected role aliases; "
        "3 synonym pairs; placement preposition; 18 event-form probes; zap correction; creation stays unsupported")


def identity():
  b = apt.assemble()
  return {"schema": 1, "revision": "I",
          "status": "the planning fixes after the first run of the planning test set (2026-09-30): Q1 to Q10 and "
                    "the state-rule convention, with 7 prompt examples of new nouns; WP19, v3, v4, v5, v6 and the "
                    "planning run's outputs seen",
          "files": b["files"], "sha256": b["sha256"],
          "bytes": {k: len(b[k].encode()) for k in ("stage1", "stage2")},
          "rendered_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in b["rendered_examples"].items()}}


def run():
  examples = corpus()
  for e in examples:
    compile_example(e)
  routes = routing_cases()
  for e in routes:
    units, errors = ap.stage1_units(e["stage1"])
    assert not errors, (e["id"], errors)
    assert apt.select_route(units)["route_selected"] == e["route"], e["id"]
  n = mutations(examples)
  t = translation_checks(examples)
  boundary_checks(examples)
  review_repairs(examples)
  bad = json_layout.misplaced()
  assert not bad, "not in the layout of json_layout.py: %s" % ", ".join(str(x) for x in bad)
  manifest = apt.PROMPTS / "manifest.json"
  assert json.loads(manifest.read_text()) == identity(), "prompt manifest is stale; regenerate after reviewable edits"
  print("%d compiled examples; %d routing contrasts; %d rejected mutations; %d controller checks; 0 GK/model calls" % (len(examples), len(routes), n, t))


if __name__ == "__main__":
  p = argparse.ArgumentParser()
  p.add_argument("--show", choices=("stage1", "stage2"))
  p.add_argument("--manifest", action="store_true")
  args = p.parse_args()
  if args.show:
    print(apt.assemble()[args.show], end="")
  elif args.manifest:
    print(json.dumps(identity(), indent=2, sort_keys=True))
  else:
    run()
