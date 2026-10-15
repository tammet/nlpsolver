"""The basic file of the planning test set (tests/tests_planning_basic.py) and its checker (solver/planning_check.py),
offline.

  rows      every row is [id, text, expected, actions] with texts and an action list or None per text; the ids and
            texts equal those of the detailed file; every expected text graded against itself is correct in the
            three modes, with its own action list as the plan
  text      the text rules T1-T8 on positive and negative pairs
  actions   the action rules A1-A2 and the modes actions and both
  runner    runtests.py with -actions and -answer-check: the grade fields of a case record, the summary block, the
            refusal of the detailed file

No model call, no GK launch.
"""
import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE, ROOT]

import planning_check as pc             # noqa: E402
import runtests                         # noqa: E402
import check_action_availability as cav  # noqa: E402

need = cav.need
BASIC = os.path.join(ROOT, "tests", "tests_planning_basic.py")
DETAILED = os.path.join(ROOT, "tests", "tests_planning.py")


def check_rows():
  rows = runtests.load_rows(BASIC)
  detailed = runtests.load_rows(DETAILED)
  need(len(rows) == 126 and [r[:2] for r in rows] == [r[:2] for r in detailed], "the ids and texts of the detailed file")
  n = plans = 0
  for r in rows:
    need(not pc.check_row(r), "row %d: %s" % (r[0], pc.check_row(r)))
    texts = r[2] if isinstance(r[2], list) else [r[2]]
    lists = r[3] if isinstance(r[2], list) else [r[3]]
    for text, acts in zip(texts, lists):
      for mode in pc.MODES:
        g = pc.grade(r[2], r[3], text, acts, mode)
        need(g["correct"], "row %d %s: %r against itself: %r" % (r[0], mode, text, g))
      n += 1
      plans += acts is not None
  return "rows: the 126 rows are complete, with the ids and texts of the detailed file; %d expected texts (%d with an " \
         "action list) are correct against themselves in the modes text, actions and both" % (n, plans)


TEXT_CASES = [
  # (rule, expected, answer, grade)
  ("T1", "Plan: Ann bakes a cake.", "Plan: Ann bakes the cake.", "match"),
  ("T1", "Plan: The hand takes block a.", "Plan: The hand takes block c.", "mismatch"),
  ("T1", "Yes.", "yes", "match"),
  ("T2", "Yes.", "Probably yes.", "mismatch"),
  ("T2", "Probably no.", "Probably no.", "match"),
  ("T2", True, "Yes.", "match"),
  ("T2", "No.", "Yes.", "mismatch"),
  ("T3", "Yes.", "Yes. Plan: Mira goes from Harbor to Hilltown.", "match"),
  ("T3", "Yes. Plan: Robo goes from Harbor to Hilltown by bus.", "Yes. Plan: Robo goes from Harbor to Hilltown by bus.",
   "match"),
  ("T3", "Yes. Plan: Robo goes from Harbor to Hilltown by bus.", "Yes. Plan: Robo goes from Harbor to Hilltown by taxi.",
   "mismatch"),
  ("T4", "Plan: The hand takes block c, then puts block c on the table, then takes block a.",
   "Plan: The robot hand takes block c, then puts block c on the table, then takes block a.", "match"),
  ("T4", "Plan: The hand takes block c, then takes block a.", "Plan: The hand takes block a, then takes block c.",
   "mismatch"),
  ("T4", "Plan: Lin paints the door white with the brush.", "Plan: Lin paints the door with the brush.", "mismatch"),
  ("T4", "Plan: Lin paints the door white with the brush.", "Plan: Lin paints the door green with the brush.",
   "mismatch"),
  ("T4", "Plan: Ann fries the egg in the pan.", "Plan: Ann fries the egg with the pan.", "match"),
  ("T4", "Plan: Robo puts the key in the box.", "Plan: Robo puts the key with the box.", "mismatch"),
  ("T4", "Plan: Ann bakes a cake.", "Plan: Ann bakes the flour cake.", "match"),
  ("T4", "Plan: Ann fries the egg.", "Probable plan: Ann fries the egg.", "mismatch"),
  ("T4", "Plan: Greta goes from Bergen to Voss by train, then paints the cabin red.",
   "Plan: Greta goes from Bergen to Voss, then paints the cabin red.", "mismatch"),
  ("T4", "Plan: Ann fries the egg.", "Plan: Ann fries the egg, then fries the egg.", "mismatch"),
  ("T5", "The key and the cup.", "The cup and the key.", "match"),
  ("T5", "The key.", "The key and the cup.", "mismatch"),
  ("T6", "Cannot answer: the route read an action as creating, transporting or handing over an object, which it does "
   "not model.", "Cannot answer: the route read an action as making something exist, which it does not model. "
   "[unsupported_creation; S2]", "match"),
  ("T6", "Cannot answer: x.", "Unknown.", "not_answered"),
  ("T6", "Cannot answer: x.", "No plan found.", "not_answered"),
  ("T6", "Cannot answer: x.", "Plan: Ann fries the egg.", "mismatch"),
  ("T6", "Yes.", "Cannot answer: x. [a; S1]", "no_answer"),
  ("T7", "Inconsistent.", "Inconsistent: the robot hand is empty and the robot hand holds the block a.", "match"),
  ("T7", "No action is needed.", "Yes. No action is needed.", "match"),
  ("T7", "Unknown.", "No plan found.", "match"),
  ("T7", "No plan found.", "Unknown.", "mismatch"),
  ("T8", "Yes.", "Error: model_timeout: a detail", "error"),
]


def check_text():
  for rule, exp, ans, want in TEXT_CASES:
    g = pc.grade(exp, None, ans)
    need(g["grade"] == want and g["correct"] == (want in pc.CORRECT), "%s: %r against %r: %r" % (rule, ans, exp, g))
  # a list: the best grade counts and names its alternative
  g = pc.grade(["Plan: A goes from X to Y.", "Cannot answer: x."], [None, None], "Unknown.")
  need(g["grade"] == "not_answered" and g["detail"]["alternative"] == 1, "alternatives: %r" % g)
  return "text: %d pairs of T1-T8 (%d negative), and the best of a list of alternatives" % (
    len(TEXT_CASES), sum(1 for c in TEXT_CASES if c[3] not in pc.CORRECT))


def check_actions():
  exp = "Plan: Greta goes from Bergen to Voss by train, then paints the cabin red."
  plan = [["move", "Greta", "Bergen", "Voss", "train"], ["change", "Greta", "cabin", "red", "unspecified"]]
  cases = [
    ("actions", "Plan: some other words.", plan, "match"),
    ("actions", exp, [["move", "greta", "bergen", "voss", "train"], ["change", "Greta", "the cabin", "red",
                                                                      "unspecified"]], "match"),
    ("actions", exp, plan[:1], "mismatch"),
    ("actions", exp, [plan[0], ["change", "Greta", "cabin", "painted", "unspecified"]], "mismatch"),
    ("actions", exp, plan[::-1], "mismatch"),
    ("actions", exp, None, "mismatch"),
    ("both", exp, plan, "match"),
    ("both", "Plan: Greta paints the cabin red.", plan, "mismatch"),
    ("both", exp, plan[:1], "mismatch"),
    ("text", exp, None, "match"),
  ]
  for mode, ans, run_plan, want in cases:
    g = pc.grade(exp, plan, ans, run_plan, mode)
    need(g["grade"] == want, "%s: %r with %r: %r" % (mode, ans, run_plan, g))
  # A1: an extra word before the noun of a name; A2: the empty plan
  hand = [["take", "hand", "c"], ["put_on", "hand", "c", "table"], ["take", "hand", "a"]]
  g = pc.grade("Plan: x.", hand, "Plan: y.", [["take", "robot hand", "c"], ["put_on", "robot hand", "c", "table"],
                                               ["take", "robot hand", "a"]], "actions")
  need(g["correct"], "A1 robot hand: %r" % g)
  need(pc.grade("Yes. No action is needed.", [], "Yes. No action is needed.", [], "both")["correct"], "A2 []")
  need(not pc.grade("Yes. No action is needed.", [], "Yes. Plan: x.", [["move", "a", "b", "c", "bus"]],
                    "actions")["correct"], "A2 [] against a plan")
  # A3: the value of a change step named in another word, with the step's verb; not with another verb
  fry = "Plan: Ann fries the egg in the pan."
  cooked = [["change", "Ann", "egg", "cooked", "pan"]]
  need(pc.grade(fry, cooked, fry, [["change", "Ann", "egg", "fried", "pan"]], "actions", ["fry"])["correct"], "A3")
  need(not pc.grade(fry, cooked, fry, [["change", "Ann", "egg", "fried", "pan"]], "actions", ["boil"])["correct"],
       "A3 another verb")
  need(not pc.grade(fry, cooked, fry, [["change", "Ann", "egg", "fried", "pan"]], "actions")["correct"],
       "A3 without the run's verbs")
  need(not pc.grade(fry, cooked, fry, [["change", "Ann", "cup", "fried", "pan"]], "actions", ["fry"])["correct"],
       "A3 another object")
  # an alternative without an action list is compared by its text, also in the mode actions
  g = pc.grade(["Plan: x.", "Cannot answer: y."], [plan, None], "Cannot answer: z. [r; S1]", None, "actions")
  need(g["grade"] == "match" and g["detail"]["alternative"] == 1 and g["detail"]["by"] == "text", "fallback: %r" % g)
  return "actions: %d cases of A1-A3 in the modes actions, both and text; an extra word before a name's noun; the " \
         "empty plan; a change value named in another word with the same verb; an alternative without an action " \
         "list compared by its text" % (len(cases) + 7)


def check_runner():
  """runtests.py with -actions: the case fields, the summary and the refusal of the detailed file."""
  for mode in pc.MODES:
    grader = runtests.PlanningGrader(BASIC, mode)
    need(grader.policy["mode"] == mode and len(grader.rows) == 126, "the grader in mode %s" % mode)
  try:
    runtests.PlanningGrader(DETAILED)
    need(False, "the detailed file is refused")
  except runtests.RunConfigurationError as e:
    need("[id, text, expected, actions] rows" in str(e), "the refusal names the row form: %s" % e)
  args, _ = runtests.parse_args([BASIC, "-actions", "-answer-check", "both"])
  need(args.answer_check == "both", "-answer-check")
  args, _ = runtests.parse_args([BASIC, "-actions"])
  need(args.answer_check == "text", "-answer-check defaults to text")
  grader = runtests.PlanningGrader(BASIC, "both")
  rows = grader.rows
  plan66 = rows[66][3]
  cases = [(66, rows[66][2], plan66, "match"),
           (66, rows[66][2], plan66[:1], "mismatch"),
           (91, "Cannot answer: the route read one place as inside another, which it does not model. "
                "[unsupported_location_granularity; S4]", None, "match"),
           (64, "No plan found.", None, "mismatch"),
           (1, "Error: translation_invalid: Stage 2: x", None, "error")]
  d = tempfile.mkdtemp()
  for k, (cid, answer, plan, want) in enumerate(cases):
    route = {"result": {"plan_named": plan} if plan is not None else {}}
    payload = runtests.build_case_json("planning_basic", cid, rows[cid][1], rows[cid][2], "gemini",
                                       {"answer": answer, "action_route": route}, None, grader)
    need(payload["grade"] == want and payload["scoring_policy"]["name"] == "planning_check"
         and payload["answer_check"]["mode"] == "both" and payload["correctness"] == (want in pc.CORRECT),
         "case %d: %r" % (cid, {key: payload.get(key) for key in ("grade", "correctness", "answer_check")}))
    if k != 1:
      runtests.write_case_file(runtests.case_filename(d, cid), payload)
  runtests.update_summary(d, "gemini")
  with open(os.path.join(d, "summary.json")) as f:
    p = json.load(f)["planning"]
  need(p == {"mode": "both", "all": {"total": 4, "answered_correctly": 2, "correctly_not_answered": 0, "wrong": 1,
                                     "errors": 1}}, "the summary: %r" % p)
  # the run ceiling with this grader: two cases of 3 calls run under the ceiling 12,12 with the per-case bound 7
  import llmcall
  from unittest.mock import patch
  calls = []

  def fake(task):
    calls.append(task[0])
    for _ in range(3):
      llmcall._take_call_slot()
      llmcall._take_request_slot("Fake")
    log = [{"logical": True, "source": "api", "requests": 1} for _ in range(3)]
    return task[0], task[3], {"answer": "Unknown.", "_llm_calls": log, "action_route": {"result": {}}}
  args = argparse.Namespace(sequential=True, run_ceiling="12,12", redo=False, redo_errors=False)
  llmcall.reset_call_limit()
  with patch.object(runtests, "_worker", side_effect=fake):
    runtests._run_batch(args, ["claude"], [tuple(rows[i][:3]) for i in (1, 2, 3, 4)], "planning_basic",
                        tempfile.mkdtemp(), {"llm_call_limit": 7}, None, None, grader)
  need(calls == [1, 2], "the run ceiling: %r" % calls)
  return "runner: the grader reads the basic file in the modes text, actions and both and refuses the detailed file; " \
         "-answer-check defaults to text; a case record holds grade and answer_check with the mode; the summary " \
         "counts answered correctly, correctly not answered, wrong and errors; -run-ceiling stops before a case that " \
         "could pass the ceiling"


def run():
  for line in (check_rows(), check_text(), check_actions(), check_runner()):
    print("  " + line)


if __name__ == "__main__":
  run()
