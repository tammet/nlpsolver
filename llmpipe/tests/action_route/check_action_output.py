"""The output levels of the action route and the pipeline block of both pipelines (`solver/action_display.py`,
`solve.py`), offline.

  levels     a one-example call of solve.py prints the answer alone; -explain adds the explanation (sentences used,
             laws used, plan steps, replay); -logic the input first, the pipeline block, the source clauses, the query,
             the stages block and the proof steps; -details the action Stage-1/2 JSON, the controller's checks and
             each launch's prover input and result; -debug each model request and raw response, the library clauses
             and each GK command
  options    -summary and -summary-json name the pipeline; -nosolve answers "" with no GK launch; -rawresult answers
             with GK's output; -gkin writes a GK input file; -debug is accepted with -actions and -printlevel is not
  collect    a runner's collector gets the short answer and the explanation as nl_proof
  ordinary   from -logic up the ordinary pipeline prints the input once and the pipeline block; -summary names it

No model call and no GK launch: the fake provider, the fake prompt bundle and the fake GK build of
check_action_pipeline.
"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE, ROOT]

import check_action_answer as caa       # noqa: E402
import check_action_pipeline as cap     # noqa: E402
import globals as G                     # noqa: E402
import llmcall                          # noqa: E402
import llmparse                         # noqa: E402
import solve                            # noqa: E402

need = cap.need
TEXT = cap.TRAVEL_TEXT


def main_with(world, argv):
  """(exit status, stdout) of solve.main on argv, with the debug switches and options restored afterwards."""
  saved = (sys.argv, solve.debug, llmparse.debug, llmcall.debug, copy.deepcopy(G.options),
           llmcall.validate_provider_configuration)
  out = io.StringIO()
  sys.argv = ["solve.py"] + argv
  llmcall.validate_provider_configuration = lambda *a, **k: None
  try:
    with contextlib.redirect_stdout(out):
      code = solve.main()
    return code, out.getvalue()
  finally:
    sys.argv, solve.debug, llmparse.debug, llmcall.debug, options, llmcall.validate_provider_configuration = saved
    G.options.clear()
    G.options.update(options)


def action(world, argv):
  world.script = {"a1": [cap.travel_stage1()], "a2": [cap.travel_stage2()]}
  return main_with(world, ["-action-backend", world.backend] + argv + [TEXT])


def check_levels(w):
  plan = "Plan: Ann goes from Haapsalu to Tallinn by bus, then from Tallinn to Helsinki by ship."
  code, out = action(w, [])
  need(code == 0 and out.strip() == plan, "no level: the answer alone: %r" % out)
  code, out = action(w, ["-explain"])
  for part in ("Explained:", "Sentences used:", "Laws used:", "  eff_move_at (effect)",
               "Plan steps (each checked by replay):", "  (1) Ann goes from Haapsalu to Tallinn by bus.",
               "Replay: valid"):
    need(part in out, "-explain: %r missing:\n%s" % (part, out))
  need(out.startswith(plan) and "=== " not in out, "-explain: the answer first and no block: %r" % out)
  code, logic = action(w, ["-logic"])
  for part in ("=== pipeline ===", 'action route (chosen automatically: a question "How can ...?"', "=== sentences mapped to "
               "clauses: ===", "=== query Q1 (plan) ===", "=== stages ===", "  answer       plan_found  <- the answer",
               "=== result ===", "Proof steps (GK, plan positive):", "        move(ann,haapsalu,tallinn,bus)",
               "  (4) p  [from steps 2, 3]"):
    need(part in logic, "-logic: %r missing" % part)
  need(logic.startswith(TEXT + "\n\n=== pipeline ===") and logic.count("=== pipeline ===") == 1,
       "-logic prints the input first, then the pipeline block once")
  need("=== prover input" not in logic and "INPUT:" not in logic, "-logic shows no prover input and no request")
  code, details = action(w, ["-details"])
  for part in ("=== action stage 1 (ASU JSON, gemini) ===", "=== action stage 2 (logic JSON, gemini) ===",
               "=== translation checks ===", "=== prover input (JSON), launch 1 of 1: Q1.plan.positive ===",
               "// [library axioms_action.js: ", "=== prover result (JSON), launch 1 of 1"):
    need(part in details, "-details: %r missing" % part)
  need("=== prover params" not in details and "INPUT:" not in details, "-details shows no GK command and no request")
  code, debug = action(w, ["-debug"])
  for part in ("=== action stage 1 LLM call (gemini), request 1 ===", "=== action stage 2 LLM call (gemini), "
               "request 1 ===", "INPUT:", "RAW OUTPUT:", "// [library]", "=== prover params, launch 1 of 1"):
    need(part in debug, "-debug: %r missing" % part)
  code, js = action(w, ["-jsonlogic"])
  need('[["connected", "#:Haapsalu 2", "#:Tallinn 3", "bus"]]' in js, "-json shows the clauses in JSON")
  return "levels: the answer alone; -explain the sentences, laws, plan steps and replay; -logic the input first, the " \
         "pipeline block, clauses, query, stages and proof steps; -details the action Stage-1/2 JSON, the checks and " \
         "each launch's input and result; -debug each request and response, the library and each GK command"


def check_options(w):
  code, out = action(w, ["-summary"])
  for part in ("=== summary ===", 'pipeline: action route (chosen automatically: a question "How can ...?"', "outcome: plan_found",
               "llm calls: stage1 1 (live 1); stage2 1 (live 1); total 2, live 2", "gk launches: 1 (discovery:positive 1)"):
    need(part in out, "-summary: %r missing:\n%s" % (part, out))
  code, out = action(w, ["-summary-json"])
  rec = json.loads(out.splitlines()[0])
  need(rec["pipeline"] == "actions" and rec["route_choice"]["route"] == "actions" and rec["gk_launches"] == 1,
       "-summary-json: %r" % rec)
  calls = len(w.requests)
  w.script = {"a1": [cap.travel_stage1()], "a2": [cap.travel_stage2()]}
  collect = {}
  ans = cap.quiet(solve.english_to_answer, TEXT, {"action_backend": w.backend, "prover_nosolve_flag": True}, collect)
  need(ans == "" and not collect.get("gk_calls") and len(w.requests) == calls + 2,
       "-nosolve: the two model calls, no GK launch, answer '': %r %r" % (ans, collect.get("gk_calls")))
  code, out = action(w, ["-rawresult"])
  need(json.loads(out)["result"] == "answer found", "-rawresult answers with GK's output: %r" % out[:200])
  path = os.path.join(tempfile.mkdtemp(), "travel.js")
  code, out = action(w, ["-gkin", path])
  with open(path) as f:
    text = f.read()
  objs = json.loads("\n".join(x for x in text.splitlines() if not x.startswith("//")))
  need(text.startswith("// ") and path in text.splitlines()[0] and any(o.get("@question") for o in objs)
       and any(o.get("@name") == "reach_step" for o in objs), "-gkin writes a GK input with its command")
  code, out = action(w, ["-actions", "-debug"])
  need(code == 0 and "Plan: Ann goes" in out, "-actions -debug is accepted")
  code, out = action(w, ["-actions", "-printlevel", "12"])
  need(code == 1 and "-printlevel" in out, "-actions -printlevel is an error naming the flag: %r" % out[-200:])
  return "options: -summary and -summary-json name the pipeline; -nosolve answers '' without GK; -rawresult gives " \
         "GK's output; -gkin writes a GK input file; -actions takes -debug and refuses -printlevel by its flag name"


def check_collect(w):
  w.script = {"a1": [cap.travel_stage1()], "a2": [cap.travel_stage2()]}
  collect = {}
  ans = cap.quiet(solve.english_to_answer, TEXT, {"action_backend": w.backend}, collect)
  need(ans.startswith("Plan: ") and "\n" not in ans and collect["answer"] == ans
       and collect.get("nl_proof", "").startswith("Explained:\n\nSentences used:"), "collect: %r %r" % (ans, collect))
  return "collect: the short answer, and the explanation as nl_proof"


def check_ordinary(w):
  code, out = main_with(w, ["-logic", cap.ELEPHANT])
  need(out.startswith(cap.ELEPHANT + "\n") and out.count(cap.ELEPHANT) == 1
       and "=== pipeline ===\n\n  ordinary pipeline (chosen automatically: no sign of actions)" in out,
       "ordinary -logic: %r" % out[:400])
  code, out = main_with(w, ["-noactions", "-summary", cap.ELEPHANT])
  need("pipeline: ordinary pipeline (forced by -noactions)" in out and "answered_by: front_door" in out,
       "ordinary -summary: %r" % out)
  code, out = main_with(w, [cap.ELEPHANT])
  need("=== pipeline" not in out, "no pipeline block below -logic")
  return "ordinary: from -logic up the input once and the pipeline block; -summary names the pipeline"


# a found plan whose proof cites the question, a source unit and a library law
PROOF = [[1, ["in", "query:Q1:plan:positive", "goal", 1], [["-p"], ["$ans", "?:X"]]],
         [2, ["in", "eff_move_at", "axiom", 1], [["-q"], ["p"]]],
         [3, ["in", "src:S1:initial_fact:1", "axiom", 1], [["q"]]],
         [4, ["mp", [2, 1], 3, "fromgoal", 1], [["p"]]],
         [5, ["mp", 1, 4, "fromgoal", 1], [["$ans", "?:X"]]]]
FOUND = {"result": "answer found", "answers": [{"answer": [["$ans", cap.PLAN]], "confidence": 1.0,
                                                "positive proof": PROOF}]}


def run():
  with cap.World() as w:
    w.backend = caa.fake({"plan:positive": FOUND})
    for line in (check_levels(w), check_options(w), check_collect(w), check_ordinary(w)):
      print("  " + line)


if __name__ == "__main__":
  run()
