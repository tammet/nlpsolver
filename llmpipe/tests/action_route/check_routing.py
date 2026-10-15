"""The choice of pipeline: the cheap classifier (`solver/route_classify.py`), `solve.route_choice` and the runner,
offline.

  classifier  the planning test files (the set, its development file and its contrasts) give no `ordinary`; the
              tracked ordinary test sets give no `actions`; the routing cases of the prompt bundle: an ordinary case
              gives no `actions`, an action case no `ordinary`
  choice      -actions and -noactions force a route; both together, and an action option with -noactions, are
              errors; without either a formal input and a text with a strong signal go to the action route with
              the action and shared keys only, and any other text to the ordinary pipeline without the action keys
  dispatch    english_to_answer and a one-example call of solve.py call the route that route_choice names from the
              text alone, and record the choice
  runner      a planning file (rows of four) is graded with the planning checker without -actions; an ordinary file
              is not; the case record keeps route_choice

No model call, no GK launch.
"""
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE, ROOT]

import route_classify as rc             # noqa: E402
import runtests                         # noqa: E402
import solve                            # noqa: E402
import check_action_availability as cav  # noqa: E402
import prompt_examples as pe             # noqa: E402

need = cav.need
PLANNING = ("tests_planning_basic.py", "tests_planning_dev.py", "tests_planning_contrasts.py")
ORDINARY = ("tests_core.py", "tests_core_challenging.py", "tests_folio_v2.py", "tests_multilogieval.py",
            "tests_multilogieval_heldout100.py", "tests_eb2_100.py", "tests_eb_100.py",
            "tests_arc_negatives_2026_08.py", "tests_eb_negatives_2026_08.py")
TRAVEL = "Ann is in Haapsalu. There is a bus route from Haapsalu to Tallinn. How can Ann get to Tallinn?"
ELEPHANT = "Elephants are animals. John is an elephant. Is John an animal?"


def check_classifier():
  counts = {}
  for name in PLANNING:
    for _, text, _ in runtests.load_tests(os.path.join(ROOT, "tests", name)):
      v = rc.classify(text)["verdict"]
      need(v != "ordinary", "%s: ordinary for %r" % (name, text[:80]))
      counts[("planning", v)] = counts.get(("planning", v), 0) + 1
  for name in ORDINARY:
    for _, text, _ in runtests.load_tests(os.path.join(ROOT, "tests", name)):
      v = rc.classify(text)
      need(v["verdict"] != "actions", "%s: actions for %r (%s)" % (name, text[:80], v["signals"]))
      counts[("ordinary", v["verdict"])] = counts.get(("ordinary", v["verdict"]), 0) + 1
  # a past-tense question after a narrative is no action signal; the present tense is
  for text, want in (("After Mary arrived, did she call Tom?", "ordinary"),
                     ("After Ann broke the egg, was the egg broken?", "ordinary"),
                     ("Ann can break the egg. After Ann breaks the egg, is the egg broken?", "actions")):
    need(rc.classify(text)["verdict"] == want, "%r: %r" % (text, rc.classify(text)))
  for case in pe.routing_cases():
    v = rc.classify(case["text"])["verdict"]
    bad = "actions" if case["route"] == "ordinary" else "ordinary"
    need(v != bad, "routing case %s (%s): %s" % (case["id"], case["route"], v))
  return "classifier: planning texts %d actions, %d unclear, none ordinary; ordinary texts %d ordinary, %d unclear, " \
         "none actions; the 12 routing cases on their side" % (
           counts.get(("planning", "actions"), 0), counts.get(("planning", "unclear"), 0),
           counts.get(("ordinary", "ordinary"), 0), counts.get(("ordinary", "unclear"), 0))


def check_choice():
  rch = solve.route_choice
  need(rch(ELEPHANT, {"actions_flag": True})["route"] == "actions", "-actions forces the action route")
  need(rch(TRAVEL, {"noactions_flag": True})["route"] == "ordinary", "-noactions forces the ordinary pipeline")
  need(rch(TRAVEL, {"noactions_flag": True, "llm_call_limit": 3})["options"] == {"llm_call_limit": 3},
       "-noactions leaves the route keys out")
  need(rch(TRAVEL, {"actions_flag": True, "noactions_flag": True}) ==
       {"error": "Error: -actions and -noactions exclude each other"}, "both switches")
  need(rch(TRAVEL, {"noactions_flag": True, "formal_flag": True})["error"].startswith("Error: -formal"),
       "-formal with -noactions")
  # without either switch
  opts = {"fallback_norm_flag": True, "critic_flag": True, "llm_call_limit": 7, "plan_depth": 3, "_collect": 1}
  got = rch(TRAVEL, opts)
  need(got["mode"] == "auto" and got["route"] == "actions" and got["verdict"] == "actions"
       and got["options"] == {"llm_call_limit": 7, "plan_depth": 3, "_collect": 1, "actions_flag": True},
       "a strong signal: the action route with the action and shared keys: %r" % got)
  got = rch(ELEPHANT, opts)
  need(got["route"] == "ordinary" and got["verdict"] == "ordinary"
       and got["options"] == {"fallback_norm_flag": True, "critic_flag": True, "llm_call_limit": 7, "_collect": 1},
       "an ordinary text: the ordinary pipeline without the action keys: %r" % got)
  got = rch("Birds can fly. Can Tweety fly?", {})
  need(got["route"] == "ordinary" and got["verdict"] == "unclear", "an unclear text goes to the ordinary pipeline")
  got = rch("{}", {"formal_flag": True})
  need(got["route"] == "actions" and got["signals"] == ["formal_input"], "a formal input")
  return "choice: -actions and -noactions force a route; both, and an action option with -noactions, are errors; " \
         "without them a strong signal or a formal input goes to the action route with the action and shared keys, " \
         "and an ordinary or unclear text to the ordinary pipeline without the action keys"


def check_dispatch():
  calls = []
  with patch("action_pipeline.run", side_effect=lambda text, options, collect, **k: calls.append(("actions", options))
             or "Plan: x."), \
       patch.object(solve, "ordinary_pipeline", side_effect=lambda text, options, collect: calls.append(
         ("ordinary", options)) or "Yes."):
    for text, opts, want in ((TRAVEL, {}, "actions"), (ELEPHANT, {}, "ordinary"), (TRAVEL, {"noactions_flag": True},
                                                                                   "ordinary"),
                             (ELEPHANT, {"actions_flag": True}, "actions")):
      del calls[:]
      collect = {}
      solve.english_to_answer(text, opts, collect)
      need(len(calls) == 1 and calls[0][0] == want and collect["route_choice"]["route"] == want
           and "options" not in collect["route_choice"], "%r %r: %r %r" % (text[:30], opts, calls, collect))
    collect = {}
    ans = solve.english_to_answer(TRAVEL, {"actions_flag": True, "noactions_flag": True}, collect)
    need(ans.startswith("Error:") and collect["answer"] == ans, "both switches: %r" % ans)
    # a one-example call of solve.py: the same decision from the text alone
    import io
    import contextlib
    for argv, want in ((["solve.py", TRAVEL], "actions"), (["solve.py", ELEPHANT], "ordinary"),
                       (["solve.py", "-noactions", TRAVEL], "ordinary"), (["solve.py", "-actions", ELEPHANT], "actions")):
      del calls[:]
      with patch.object(sys, "argv", argv), patch.object(solve.llmcall, "validate_provider_configuration"), \
           contextlib.redirect_stdout(io.StringIO()):
        solve.main()
      need(len(calls) == 1 and calls[0][0] == want, "solve.py %r: %r" % (argv[1:], calls))
  # the ordinary pipeline rebuilds the collector, and the choice stays
  def rebuild(text, options, collect, stage1_json=None):
    collect.clear()
    collect["answer"] = "Yes."
    return "Yes."
  with patch.object(solve, "ordinary_pipeline", side_effect=rebuild):
    collect = {}
    solve.english_to_answer(ELEPHANT, {}, collect)
  need(collect.get("route_choice", {}).get("route") == "ordinary", "the choice survives the ordinary pipeline: %r"
       % collect)
  return "dispatch: english_to_answer, and a one-example call of solve.py, call the route that route_choice names " \
         "from the text alone, and record the choice"


def check_runner():
  basic = os.path.join(ROOT, "tests", "tests_planning_basic.py")
  core = os.path.join(ROOT, "tests", "tests_core_100.py")
  need(runtests.planning_file(basic) and runtests.planning_file(os.path.join(ROOT, "tests", "tests_planning.py"))
       and not runtests.planning_file(core), "planning_file")
  args, extra = runtests.parse_args([basic, "-llms", "gemini"])
  need(args.answer_check == "text" and "actions_flag" not in runtests.build_run_options(args, extra),
       "a planning file needs no -actions")
  payload = runtests.build_case_json("planning_basic", 1, "t", "Yes.", "gemini",
                                     {"answer": "Yes.", "route_choice": {"mode": "auto", "route": "actions",
                                                                         "verdict": "actions", "signals": ["x"]}},
                                     None, runtests.PlanningGrader(basic))
  need(payload["route_choice"]["route"] == "actions", "the case record keeps route_choice")
  return "runner: a planning file is graded with the planning checker without -actions; an ordinary file is not; " \
         "the case record keeps route_choice"


def run():
  for line in (check_classifier(), check_choice(), check_dispatch(), check_runner()):
    print("  " + line)


if __name__ == "__main__":
  run()
