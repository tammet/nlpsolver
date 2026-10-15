"""Repair round after WP20: the correction controller and the validator messages, offline.

The saved WP19 responses in regression/wp19_translations.json replay through
the current controller with a fake provider that returns them in order.  They
test plumbing and messages; they say nothing about what a model does with the
new requests.  No model call, no GK launch.

  A1  a correction request holds the previous response; a request equal to the
      previous one is not sent, and the translation records the reason
  A2  unit-level compile diagnostics reach the correction with the slot they name
  A3  the confidence message names the convention and the fix
  A4  a query unit with pre_state or next_state is rejected; a query never
      declares a world
  A5  context on a query unit, a snapshot in ambient, a selector on a source unit
  A6  the context message says which timing rule applies
  D4  an entity whose head noun is hand needs the class hand in Stage 2
  E1  an in fact between two declared places is unsupported_location_granularity
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

SAVED = os.path.join(HERE, "regression", "wp19_translations.json")


def saved():
  with open(SAVED) as f:
    return json.load(f)["rows"]


def row(rows, model, case, mode="natural"):
  return next(r for r in rows if r["model"] == model and r["id"] == case and r["mode"] == mode)


def raws(r, stage):
  return [h["raw"] for h in r["history"] if h["stage"] == stage and h.get("raw") is not None]


def replay(r, bundle):
  """Run translate on r's text; the fake provider returns r's saved responses per stage, in order, and repeats the
  last one when the controller asks for more.  Returns (record, [(stage, prompt)])."""
  queues = {1: raws(r, 1), 2: raws(r, 2)}
  sent = []

  def fake(sysprompt, prompt, **kwargs):
    stage = 1 if sysprompt == bundle["stage1"] else 2
    sent.append((stage, prompt))
    q = queues[stage]
    return q.pop(0) if len(q) > 1 else q[0]
  if r["mode"] != "natural":
    queues[1] = [json.dumps(r["stage1_packages"])] if r.get("stage1_packages") else queues[1]
  with patch.object(ap.llmcall, "call_llm", side_effect=fake):
    rec = ap.translate(r["text"], bundle)
  return rec, sent


def parsed(raw):
  p, err, _ = aj.parse_response(raw)
  assert err is None, err
  return p


def units_of(raw):
  units, errors = ap.stage1_units(parsed(raw))
  return units, errors


def check_a1(rows, bundle):
  doubles = [r for r in rows if r["mode"] == "natural" and
             any(len([h for h in r["history"] if h["stage"] == s]) == 3 for s in (1, 2))]
  assert len(doubles) == 10, [(r["model"], r["id"]) for r in doubles]
  stopped = differed = earlier = focused = 0
  for r in doubles:
    stage = next(s for s in (1, 2) if len([h for h in r["history"] if h["stage"] == s]) == 3)
    rec, sent = replay(r, bundle)
    mine = [p for s, p in sent if s == stage]
    for i, p in enumerate(mine[1:], 1):
      previous = [h for h in rec["history"] if h["stage"] == stage and h.get("raw")][i - 1]["raw"].strip()
      # K14 (planning fixes): after a correction that returned the same response, one focused request quotes only
      # the failing packages
      assert ("CORRECTION: your previous Stage-%d output was:\n%s\n" % (stage, previous) in p
              or "was the same as the output before it" in p), (r["id"], i)
    first = [h for h in rec["history"] if h["stage"] == stage][0]
    if len(mine) == 1:
      # the @p that the saved correction asked for is now the derived one: the first response is used.  gemini
      # default_and_exception has no Stage-1 readings; its two law forms are accepted by K11 (planning fixes)
      assert rec["status"] in ("ok", "unsupported_translation") and not first["errors"], (r["model"], r["id"])
      assert any(n["kind"] == "derived_probability" for n in first["normalizations"]), (r["model"], r["id"])
      k11 = [n["unit"] for n in first["normalizations"] if n.get("repair") == "K11"]
      assert k11 == (["S1", "S2"] if (r["model"], r["id"]) == ("gemini", "default_and_exception") else []), \
        (r["model"], r["id"], k11)
      earlier += 1
    elif rec.get("stop_reason") == "repeated_request":
      assert len(mine) == 2, (r["model"], r["id"], len(mine))
      skipped = [h for h in rec["history"] if h.get("skipped")]
      assert skipped and skipped[0]["attempt"] == 2 and rec["status"] == "translation_invalid", rec["history"]
      stopped += 1
    elif any(h.get("kind") == "focused_correction" for h in rec["history"]):
      assert len(mine) == 3 and "was the same as the output before it" in mine[2], (r["model"], r["id"])
      focused += 1
    else:
      assert len(mine) == 3 and mine[2] != mine[1], (r["model"], r["id"])
      differed += 1
  assert (stopped, focused, differed, earlier) == (0, 2, 5, 3), (stopped, focused, differed, earlier)
  return "A1: 10 double-correction histories: %d stop after one correction (repeated request, nothing to quote), " \
         "%d send the one focused request of K14 after a correction that returned the same response, %d send a " \
         "different second correction, %d need no correction since the derived @p replaces the model's (one of " \
         "them with the readings of K11)" % (stopped, focused, differed, earlier)


def check_a2(rows):
  out = []
  for model, case, needles in (("claude", "worked_c10_ticket_or_pass",
                                 ("https://en.wikipedia.org/wiki/Haapsalu", "the origin slot of move",
                                  "the place slot of located_at", "entity_slot")),
                                ("gemini", "slot_restriction_unsupported",
                                 ("unspecified", "the origin slot of move", "unspecified_position"))):
    r = row(rows, model, case)
    units = r["stage1_units"]
    got, errors = ap.stage2_packages(parsed(raws(r, 2)[-1]))
    assert not errors
    worlds, contexts, packages = got
    src, qs = ap.split_packages(packages)
    errors = ap.compile_translation({}, r["text"], units, worlds, contexts, src, qs)
    assert isinstance(errors, list) and errors, errors
    text = ap.correction_request(2, errors, raws(r, 2)[-1])
    for n in needles:
      assert n in text, (case, n, errors)
    assert "the source is invalid:" not in text
    assert len(errors) == len(set(errors))
    out.append("%s %s: %d lines" % (model, case, len(errors)))
  return "A2: unit diagnostics with the slot: " + "; ".join(out)


def handoff(r, raw_index=-1, stage1=None):
  units = stage1 if stage1 is not None else r["stage1_units"]
  env = parsed(raws(r, 2)[raw_index])
  got, errors = ap.stage2_packages(env)
  assert not errors
  return apt.handoff_errors(units, env if isinstance(env, dict) else {}, got[2])


def check_a3(rows):
  e = handoff(row(rows, "claude", "travel_goal"))
  assert "unit S3: omit @p; 0.99 comes from the indefinite article and the text states no probability" in e, e
  assert "unit S4: omit @p; 0.99 comes from the indefinite article and the text states no probability" in e, e
  for model in ("gemini", "claude"):
    e = handoff(row(rows, model, "default_and_exception"))
    assert any("normally produces no @p; drop 0.98" in x for x in e), (model, e)
  e = handoff(row(rows, "claude", "held_object_transport"))
  assert any("omit @p; 0.99 comes from the indefinite article" in x for x in e), e
  # the stated probability keeps its @p; a missing one gets its fix
  assert "add" not in apt.confidence_message("S2", 0.6, 0.6, 0.6)
  assert "\"@p\",\"S2\",0.6" in apt.confidence_message("S2", None, 0.6, 0.6)
  assert "must be 0.6" in apt.confidence_message("S2", 0.8, 0.6, 0.6)
  return "A3: the confidence messages of travel (claude), default (both) and held-object (claude) name the fix"


def check_a4(rows):
  for model in ("gemini", "claude"):
    r = row(rows, model, "world_selection")
    stage1 = [h for h in r["history"] if h["stage"] == 1 and not h["errors"]][0]["raw"]
    units, errors = units_of(stage1)
    assert "unit S3: a query selects its snapshot with planning_root, not pre_state" in errors, (model, errors)
  # a query's pre_state does not declare a world, and planning_root must name one a source unit declares
  q = {"unit_id": "S2", "type": "query", "text": "Can Mira be at Harbor?", "planning_root": "W1", "entities": []}
  s = {"unit_id": "S1", "type": "situation", "text": "Mira 1 is at Harbor 2.",
       "entities": [{"id": "Mira 1", "type": "concrete"}, {"id": "Harbor 2", "type": "concrete"}]}
  assert apt.declared_worlds([s, dict(q, pre_state="W1")]) == ["W0"]
  errors = apt.validate_units([s, q])
  assert "unit S2: planning_root names a declared world: W0 or a snapshot that a source unit establishes" in errors, errors
  assert not apt.validate_units([dict(s, pre_state="W1"), q])
  return "A4: both world_selection Stage-1 outputs rejected with the planning_root message; a query declares no world"


def check_a5(rows):
  r = row(rows, "claude", "scope_and_knower")
  _, errors = units_of(raws(r, 1)[0])
  assert "unit S4: a query selects with ambient and knower, not context" in errors, errors
  r = row(rows, "gemini", "world_selection")
  _, errors = units_of(raws(r, 1)[0])
  assert "unit S3: ambient is a location entity; a snapshot goes in planning_root" in errors, errors
  r = row(rows, "gemini", "scope_and_knower")
  _, errors = units_of(raws(r, 1)[0])
  assert any(x.startswith("unit S3: knower selects a view on the query unit") for x in errors), errors
  assert any("location_role belongs inside context" in x for x in errors), errors
  return "A5: context on a query (claude), a snapshot in ambient (gemini) and a source-unit knower (gemini) name the field"


def check_a6(rows):
  seen = []
  for model, mode in (("gemini", "natural"), ("claude", "gold_stage1_diagnostic")):
    r = row(rows, model, "occurrence_not_permission", mode)
    for i in range(len(raws(r, 2))):
      e = handoff(r, i)
      if any("an occurrence keeps its time as a has time atom" in x for x in e):
        seen.append((model, mode, i))
  assert seen, "no occurrence tense message"
  r = row(rows, "gemini", "temporal_permission", "gold_stage1_diagnostic")
  e = handoff(r)
  assert any("the timing of an action rule goes in @time" in x and "time is not an entry" in x for x in e), e
  for model in ("gemini", "claude"):
    r = row(rows, model, "past_fact_excluded")
    e = handoff(r, 0)
    assert any("add \"tense\": \"past\"" in x for x in e), (model, e)
  return "A6: occurrence tense (%d saved attempts), rule time in contexts (gemini) and a missing past tense (both)" % len(seen)


def check_d4(rows, examples):
  for model in ("gemini", "claude"):
    e = handoff(row(rows, model, "worked_p02_tower"))
    assert any(x.startswith("entity robot hand 1: its head noun is hand") for x in e), (model, e)
  ex = {x["id"]: x for x in examples}
  gold = ex["worked_p02_tower"]
  units, _ = ap.stage1_units(gold["stage1"])
  assert not apt.handoff_errors(units, gold["stage2"], gold["stage2"]["logic"])
  # a compound hand with both classes passes; a robot that is not a hand needs no class
  env = copy.deepcopy(parsed(raws(row(rows, "claude", "worked_p02_tower"), 2)[-1]))
  units = row(rows, "claude", "worked_p02_tower")["stage1_units"]
  s1 = next(p for p in env["logic"] if p[1] == "S1")
  s1[2][2] = ["and", s1[2][2], ["isa", "hand", "robot hand 1"]]
  assert not any(x.startswith("entity robot hand 1") for x in apt.handoff_errors(units, env, env["logic"]))
  assert apt.head_noun("robot hand 1") == "hand" and apt.head_noun("handle 3") == "handle"
  assert apt.head_noun("hand cart 2") == "cart"
  pos = ex["possession_and_holding"]
  units, _ = ap.stage1_units(pos["stage1"])
  assert not apt.handoff_errors(units, pos["stage2"], pos["stage2"]["logic"])
  return "D4: both tower outputs request the class hand; gold tower, a compound hand with both classes and a " \
         "non-hand robot pass"


def check_e1(rows):
  """E1: both saved nested_places translations wrote in between two places; they now compile unsupported."""
  for model in ("gemini", "claude"):
    r = row(rows, model, "nested_places")
    got, errors = ap.stage2_packages(parsed(raws(r, 2)[-1]))
    worlds, contexts, packages = got
    src, qs = ap.split_packages(packages)
    assert any(isinstance(p[2], list) and "in" in json.dumps(p[2]) for p in src)
    record = {}
    stop = ap.compile_translation(record, r["text"], r["stage1_units"], worlds, contexts, src, qs)
    assert stop == "unsupported" and record["unsupported"]["reasons"] == ["unsupported_location_granularity"], \
      (model, stop, record.get("unsupported"))
  return "E1: both saved nested_places translations (in between two places) now compile unsupported_location_granularity"


def check_gold(examples):
  n = 0
  for e in examples:
    units, errors = ap.stage1_units(e["stage1"])
    assert not errors, (e["id"], errors)
    assert not apt.handoff_errors(units, e["stage2"], e["stage2"]["logic"]), e["id"]
    n += 1
  return "gold: %d authored examples pass the new validator and handoff checks" % n


def _absent(paths):
  """The saved model responses of `regression/` that are not present: the folder is local and not in the
  repository, so a check that replays them skips that part and says so."""
  return [os.path.relpath(p, HERE) for p in paths if not os.path.exists(p)]


def run():
  examples = pe.corpus()
  gone = _absent([SAVED])
  if gone:
    print("  skipped: A1-A6, D4 and E1 replay saved responses that are not present (regression/ is local): %s" % ", ".join(gone))
    parts = [lambda: check_gold(examples)]
  else:
    rows = saved()
    bundle = apt.assemble()
    parts = [lambda: check_a1(rows, bundle), lambda: check_a2(rows), lambda: check_a3(rows), lambda: check_a4(rows),
             lambda: check_a5(rows), lambda: check_a6(rows), lambda: check_d4(rows, examples), lambda: check_e1(rows),
             lambda: check_gold(examples)]
  for part in parts:
    print("  " + part())


if __name__ == "__main__":
  run()
