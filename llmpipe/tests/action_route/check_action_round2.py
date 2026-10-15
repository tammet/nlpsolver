"""Round 2 after the v3 run: the answer policy, the reading check, two messages and the correction memory, offline.

The saved v3 responses and, for five rows, the saved GK evidence in regression/v3_translations.json replay through
the current code with a fake provider.  They test the repairs against the rows that motivated them; they say
nothing about what a model does with the new prompts.  No model call, no GK launch.

  R1  a negative step verdict needs the replay's own No at the same place, at step 1 too: the saved gemini
      conditional_signed_effect evidence (GK No at 0.99 through a frame axiom, replay "permission unknown") now
      decides Unknown with replay_disagrees; the four other saved evidence rows keep their answers
  R2  a public service that Stage 1 labelled availability without an actor, compiled to its connected fact, is
      accepted with a note: the saved claude travel_goal, new_tartu_train and worked_p01_travel first attempts
      translate ok; an availability label with an actor still needs an availability form
  R4  the package message names the @time position; a flattened plan goal names the plan package form
  R6  a correction quotes the errors of earlier attempts that the current response no longer has
"""
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "solver"))

import action_answer as aa          # noqa: E402
import action_pipeline as ap        # noqa: E402
import action_prompt as apt         # noqa: E402
import prompt_examples as pe        # noqa: E402

SAVED = os.path.join(HERE, "regression", "v3_translations.json")


def saved():
  with open(SAVED) as f:
    return json.load(f)["rows"]


def row(rows, model, case, mode="natural"):
  return next(r for r in rows if r["model"] == model and r["id"] == case and r["mode"] == mode)


def raws(r, stage):
  return [h["raw"] for h in r["history"] if h["stage"] == stage and h.get("raw") is not None]


def translate_with(bundle, text, stage1_raws, stage2_raws):
  """translate() with a fake provider that returns the given responses per stage in order, repeating the last."""
  queues = {1: list(stage1_raws), 2: list(stage2_raws)}
  sent = []

  def fake(sysprompt, prompt, **kwargs):
    stage = 1 if sysprompt == bundle["stage1"] else 2
    sent.append((stage, prompt))
    q = queues[stage]
    return q.pop(0) if len(q) > 1 else q[0]
  with patch.object(ap.llmcall, "call_llm", fake):
    return ap.translate(text, bundle), sent


def check_policy(rows):
  r = row(rows, "gemini", "conditional_signed_effect")
  a = r["answered"]
  assert a["recorded_answer"] == "No", a["recorded_answer"]
  res = aa.decide(a["source"], a["query"], a["evidence"])
  assert res["outcome"] == "verification_result" and res["answer"] == "Unknown", (res["outcome"], res["answer"])
  assert res.get("validation") == "replay_disagrees", res.get("validation")
  assert any("the replay reads Unknown there" in str(d) for d in res["diagnostics"]), res["diagnostics"]
  kept = []
  for r in rows:
    if "answered" not in r or (r["model"], r["id"]) == ("gemini", "conditional_signed_effect"):
      continue
    a = r["answered"]
    res = aa.decide(a["source"], a["query"], a["evidence"])
    assert res["outcome"] == a["recorded_outcome"] and res.get("answer") == a["recorded_answer"], (r["model"], r["id"])
    kept.append("%s %s %s" % (r["model"], r["id"], res.get("answer")))
  assert len(kept) == 4, kept
  return "policy: the saved frame negative at step 1 is Unknown (replay_disagrees); %s unchanged" % ", ".join(kept)


def check_reading(rows):
  bundle = apt.assemble()
  out = []
  for model, case in (("claude", "travel_goal"), ("claude", "new_tartu_train"), ("claude", "worked_p01_travel")):
    r = row(rows, model, case)
    tr, sent = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1])
    assert tr["status"] == "ok", (case, tr["status"], tr["errors"][-1:] if tr["errors"] else tr["history"][-1]["errors"])
    notes = [d for u in tr["source"]["units"] for d in u["diagnostics"] if d.get("reason") == "reading_adjusted"]
    assert notes, case
    routes = [p for p in tr["stage2"]["packages"] if "connected" in json.dumps(p)]
    assert routes and len(sent) == 2, (case, len(sent))
    out.append("%s (%d route%s)" % (case, len(notes), "s" if len(notes) > 1 else ""))
  # an availability label with an actor is not a public route: the mismatch stays a correction request
  r = row(rows, "claude", "travel_goal")
  units = json.loads(raws(r, 1)[0].strip().strip("`").split("\n", 1)[1] if raws(r, 1)[0].strip().startswith("```")
                     else raws(r, 1)[0])
  for p in units:
    for u in p["units"]:
      for a in u.get("actions") or []:
        a["roles"]["actor"] = "Mira 1"
  tr, sent = translate_with(bundle, r["text"], [json.dumps(units)], raws(r, 2)[:1])
  assert tr["status"] != "ok" and any("reading_form_mismatch" in e for e in tr["errors"]), tr["status"]
  return "reading: a route under an actorless availability label is kept with a note (%s); with an actor the " \
         "mismatch is still requested" % ", ".join(out)


def check_messages(rows):
  bundle = apt.assemble()
  r = row(rows, "gemini", "temporal_permission")
  second = raws(r, 2)[1]     # @time outside holds, no context
  tr, _ = translate_with(bundle, r["text"], raws(r, 1)[:1], [second])
  msgs = [e for h in tr["history"] for e in (h.get("errors") or [])]
  assert any("@time goes inside holds" in m for m in msgs), msgs
  r = row(rows, "claude", "worked_p02_tower")
  tr, _ = translate_with(bundle, r["text"], raws(r, 1)[:1], raws(r, 2)[:1])
  msgs = [e for h in tr["history"] for e in (h.get("errors") or [])]
  assert any("a plan package is" in m and "one formula" in m for m in msgs), msgs
  assert not any("step_bound mismatch" in m for m in msgs), msgs
  return "messages: the @time position and the plan package form are named; the flattened goal is no bound mismatch"


def check_memory(rows):
  """The saved gemini temporal_permission responses no longer serve: their first error was a context that the
  controller now derives.  Two responses built from the gold have errors that no derivation removes: @time outside
  holds, then a plan package with two goals."""
  bundle = apt.assemble()
  e = {x["id"]: x for x in pe.corpus()}["temporal_permission"]
  law = e["stage2"]["logic"][1][2][2]
  timed_outside = json.loads(json.dumps(e["stage2"]))
  timed_outside["logic"][1][2] = ["@time", law[1], ["holds", "W0", law[2]]]
  two_goals = json.loads(json.dumps(e["stage2"]))
  goal = two_goals["logic"][2][2][1]
  two_goals["logic"][2][2] = ["plan", goal, ["is rel2", "located_at", "Mira 1", "Harbor 2"]]
  tr, sent = translate_with(bundle, e["text"], [json.dumps(e["stage1"])],
                            [json.dumps(timed_outside), json.dumps(two_goals), json.dumps(two_goals)])
  second = [p for s, p in sent if s == 2]
  assert len(second) == 3, len(second)
  assert "keep those fixes" in second[2] and "@time goes inside holds" in second[2], second[2][-1500:]
  assert "keep those fixes" not in second[1]
  return "memory: the third request quotes the first attempt's resolved error (@time outside holds) as a constraint " \
         "to keep"


def _absent(paths):
  """The saved model responses of `regression/` that are not present: the folder is local and not in the
  repository, so a check that replays them skips that part and says so."""
  return [os.path.relpath(p, HERE) for p in paths if not os.path.exists(p)]


def run():
  gone = _absent([SAVED])
  if gone:
    print("  skipped: every part replays saved responses that are not present (regression/ is local): %s" % ", ".join(gone))
    return
  rows = saved()
  for line in (check_policy(rows), check_reading(rows), check_messages(rows), check_memory(rows)):
    print("  " + line)


if __name__ == "__main__":
  run()
