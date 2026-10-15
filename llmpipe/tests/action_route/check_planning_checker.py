"""The answer checker of the planning test set (`solver/action_check.py`), offline.

  plans     a listed plan by terms and by text; the other order of two independent steps (valid); a repeated step
            (valid, extra_steps 1); two dependent steps reversed and a missing last step (invalid); a name that does not
            align (unverified); another plan without a reference (unlisted); a reachable Yes whose plan is invalid
  answers   yes, no and unknown, as True, False and None; the confidence as a word (C7): Probably in both or in
            neither; a wh-answer; No plan found. against a plan and a plan against No plan found. (with the replay
            verdict); No action is needed.; Inconsistent.
  fixes     C1 the terms decide over an equal sentence; C2 a change step aligned by its verb (row 52), and not without
            the verb or with two candidates; C3 by text without terms; C4 "with" equals "in" only before the tool of a
            change step; C5 a plan answer to a reachable True is replayed, and No plan found. matches a reachable
            Unknown; C6 the translation compared up to renaming, with its worlds, contexts and query selections
  cannot    a Cannot answer row against Cannot answer (with and without the reference's reason code), Unknown., No plan
            found., a plan, Yes., an Error:, and against its listed second alternative
  error     Error: is never correct
  rows      grade_row reads the reference from a row [id, text, expected, reference] with the row's text and grades as
            grade does; a row without a reference compares a plan by its text

The reference records come from a fresh build of the test files (make_planning_tests.build).  No model call, no GK
launch.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE]

import action_check as ac               # noqa: E402
import check_action_availability as cav  # noqa: E402
import make_planning_tests as mp        # noqa: E402

need = cav.need


def refs():
  rows, built = mp.build()
  tests, rr = built["rows"]
  by_name = {rr[str(t[0])]["name"]: (t[2], rr[str(t[0])]) for t in tests}
  return by_name


def record(named):
  return {"result": {"plan": named, "plan_named": named}}


def g(expected, answer, named=None, ref=None):
  return ac.grade(expected, answer, record(named) if named is not None else None, ref)


def check_plans(R):
  out = []
  exp, ref = R["plan_route_dead_end"]
  listed = [["move", "Oskar", "Lund", "Malmo", "bus"], ["move", "Oskar", "Malmo", "Copenhagen", "train"],
            ["move", "Oskar", "Copenhagen", "Oslo", "ferry"]]
  r = g(exp, exp, listed, ref)
  need(r["grade"] == "listed" and r["detail"]["by"] == "terms" and r["detail"]["extra_steps"] == 0, "listed: %r" % r)
  r = g(exp, exp)
  need(r["grade"] == "listed" and r["detail"]["by"] == "text", "listed by text: %r" % r)
  r = g(exp, "Plan: Oskar goes from Lund to Malmo by bus, then from Malmo to Copenhagen by train.",
        listed[:2], ref)
  need(r["grade"] == "invalid", "a missing last step: %r" % r)
  r = g(exp, "Plan: ...", list(reversed(listed)), ref)
  need(r["grade"] == "invalid" and r["detail"]["step"] == 1, "reversed dependent steps: %r" % r)
  r = g(exp, "Plan: ...", [["move", "Oskarr", "Lund", "Malmo", "bus"]] + listed[1:], ref)
  need(r["grade"] == "unverified" and r["detail"]["name"] == "Oskarr", "an unaligned name: %r" % r)
  r = g(exp, "Plan: Oskar goes from Lund to Oslo by plane.")
  need(r["grade"] == "unlisted", "no reference: %r" % r)
  out.append("listed by terms and by text; a missing last step and reversed dependent steps invalid; an unaligned "
             "name unverified; no reference unlisted")
  exp, ref = R["plan_two_travellers"]
  other = [["move", "Juri", "Vilnius", "Kaunas", "train"], ["move", "Ilze", "Riga", "Kaunas", "bus"]]
  need(isinstance(exp, list) and len(exp) == 2, "two listed orders")
  r = g(exp[0], exp[1], other, dict(ref, plans=ref["plans"][:1]))
  need(r["grade"] == "valid" and r["detail"]["extra_steps"] == 0, "the other order of independent steps: %r" % r)
  r = g(exp, exp[1], other, ref)
  need(r["grade"] == "listed", "the other order, listed: %r" % r)
  exp, ref = R["plan_precondition_other_object"]
  rep = [["change", "Pia", "oven", "hot", "unspecified"], ["change", "Pia", "oven", "hot", "unspecified"],
         ["change", "Pia", "bread", "baked", "unspecified"]]
  r = g(exp, "Plan: Pia heats the oven, then heats the oven, then bakes the bread.", rep, ref)
  need(r["grade"] == "valid" and r["detail"]["extra_steps"] == 1, "a repeated step: %r" % r)
  out.append("the other order of independent steps valid (and listed when listed); a repeated step valid with "
             "extra_steps 1")
  # an alias: robot hand in the model's plan, hand in the reference
  exp, ref = R["plan_take_then_put_in"]
  alias = [["take", "robot hand", "d"], ["put_in", "robot hand", "d", "crate"]]
  r = g(exp, "Plan: The robot hand takes block d, then puts block d in the crate.", alias, ref)
  need(r["grade"] in ("listed", "valid"), "the last word aligns robot hand with hand: %r" % r)
  # a reachable question: Yes with a plan that the reference rejects
  exp, ref = R["drone_rule_air_route"]
  bad = [["move", "Zip", "Tartu", "Tallinn", "bus"]]
  r = g(exp, "Yes. Plan: Zip goes from Tartu to Tallinn by bus.", bad, ref)
  need(exp is True and r["grade"] == "invalid", "a reachable Yes with an invalid plan: %r" % r)
  r = g(exp, "Yes. Plan: Zip goes from Tartu to Tallinn by air.", [["move", "Zip", "Tartu", "Tallinn", "air"]], ref)
  need(r["grade"] == "match" and r["detail"]["plan_replay"] == "valid", "a reachable Yes: %r" % r)
  out.append("robot hand aligns with hand; a reachable Yes is replayed")
  return "plans: " + "; ".join(out)


def check_answers(R):
  rows = [(True, "Yes.", "match"), (True, "No.", "mismatch"), (False, "No.", "match"), (None, "Unknown.", "match"),
          (None, "Yes.", "mismatch"), (True, "True.", "match"),
          ("Probably yes.", "Probably yes.", "match"), ("Probably yes.", "Yes.", "mismatch"),
          (True, "Probably yes.", "mismatch"), (False, "Probably no.", "mismatch"), ("Probably no.", "Probably no.", "match"),
          ("Probably no.", "No.", "mismatch"), ("Probably yes. Plan: Ann goes from A to B by bus.",
                                                "Probably yes. Plan: Ann goes from A to B by bus.", "match"),
          ("Probable plan: Ann goes from A to B by bus.", "Probable plan: Ann goes from A to B by bus.", "listed"),
          ("Plan: Ann goes from A to B by bus.", "Probable plan: Ann goes from A to B by bus.", "mismatch"),
          ("The key.", "The key.", "match"), ("The key.", "The cup.", "mismatch"), ("Ann.", "Ann.", "match"),
          ("The key and the cup.", "The cup and the key.", "match"),
          ("No plan found.", "No plan found.", "match"), ("No plan found.", "Plan: Ann goes from A to B.", "mismatch"),
          ("Plan: Ann goes from A to B by bus.", "No plan found.", "mismatch"),
          ("No action is needed.", "No action is needed.", "match"),
          ("No action is needed.", "Yes. No action is needed.", "match"),
          ("No action is needed.", "Plan: Ann goes from A to B.", "mismatch"),
          ("Inconsistent.", "Inconsistent: the robot hand is empty and the robot hand holds block a.", "match"),
          (True, "Cannot answer: the route read one place as inside another, or one thing at two places at once, "
                 "which it does not model. [unsupported_location_granularity; S4]", "no_answer")]
  for exp, ans, want in rows:
    r = ac.grade(exp, ans)
    need(r["grade"] == want and r["correct"] == (want in ac.CORRECT), "%r against %r: %r" % (ans, exp, r))
  # No plan found. against a plan: the replay verdict is in the detail
  exp, ref = R["c04_negative_capability:base:Q3"]
  r = g(exp, "Plan: Ann goes from Haapsalu to Tallinn by bus.", [["move", "Ann", "Haapsalu", "Tallinn", "bus"]], ref)
  need(r["grade"] == "mismatch" and r["detail"].get("replay") == "invalid", "No plan found. against a plan: %r" % r)
  return "answers: %d expected-answer pairs (yes, no, unknown, Probably, names, no plan, no action, " \
         "inconsistent); a plan against No plan found. carries the replay verdict" % len(rows)


def check_fixes(R):
  out = []
  # C1: the terms decide: the expected sentence with terms that the replay rejects is invalid
  exp, ref = R["plan_route_dead_end"]
  listed = [["move", "Oskar", "Lund", "Malmo", "bus"], ["move", "Oskar", "Malmo", "Copenhagen", "train"],
            ["move", "Oskar", "Copenhagen", "Oslo", "ferry"]]
  r = g(exp, exp, list(reversed(listed)), ref)
  need(r["grade"] == "invalid" and r["detail"]["by"] == "terms", "C1: %r" % r)
  out.append("C1 an expected sentence with invalid terms is invalid")
  # C2: row 52, the change value crisp where the reference's permission has another value
  exp, ref = R["c11_method_collision:tools_distinguish:Q1"]
  fry = [["change", "Ann", "egg", "crisp", "pan"]]
  rec = {"result": {"plan": fry, "plan_named": fry, "plan_verbs": ["fry"]}}
  r = ac.grade(exp, "Plan: Ann fries the egg in the pan.", rec, ref)
  aligned = r["detail"].get("verb_alignment") or []
  need(r["grade"] == "valid" and aligned and aligned[0]["aligned"], "C2 by the verb: %r" % r)
  rec = {"result": {"plan": fry, "plan_named": fry, "plan_verbs": [None]}}
  r = ac.grade(exp, "Plan: Ann fries the egg in the pan.", rec, ref)
  need(r["grade"] == "invalid", "C2 without the verb, the term as written: %r" % r)
  rec = {"result": {"plan": fry, "plan_named": fry, "plan_verbs": ["boil"]}}
  r = ac.grade(exp, "Plan: Ann fries the egg in the pan.", rec, ref)
  need(r["grade"] == "invalid", "C2 another verb's permission has another tool: %r" % r)
  out.append("C2 row 52 valid by the verb fry, invalid without a verb or with the verb boil (the pot)")
  # C3: no terms: by text
  r = ac.grade(exp, "Plan: Ann fries the egg in the pan.", None, ref)
  need(r["grade"] == "listed" and r["detail"]["by"] == "text" and r["detail"]["why"] == "no plan terms", "C3: %r" % r)
  out.append("C3 by text without terms")
  # C4: with and in before the tool of a change step; never in put_in, put_on or a move
  r = ac.grade("Plan: Ann fries the egg in the pan.", "Plan: Ann fries the egg with the pan.")
  need(r["grade"] == "listed", "C4 change: %r" % r)
  for want, got in (("Plan: The hand puts block d in the crate.", "Plan: The hand puts block d with the crate."),
                    ("Plan: The hand puts block d on the table.", "Plan: The hand puts block d with the table."),
                    ("Plan: Ann goes from A to B by bus.", "Plan: Ann goes from A to B with bus."),
                    ("Plan: Ann cooks the egg in the pan, then goes from A to B by bus.",
                     "Plan: Ann cooks the egg in the pan, then goes from A to B in bus.")):
    r = ac.grade(want, got)
    need(r["grade"] == "unlisted", "C4 %r: %r" % (got, r))
  out.append("C4 with equals in before the tool of a change step, not in put_in, put_on or a move")
  # C5: a plan answer to a reachable question whose expected value is True; No plan found. for Unknown
  exp, ref = R["drone_rule_air_route"]
  air = [["move", "Zip", "Tartu", "Tallinn", "air"]]
  r = g(exp, "Plan: Zip goes from Tartu to Tallinn by air.", air, ref)
  need(exp is True and r["grade"] == "valid", "C5 a plan answer to a reachable True: %r" % r)
  r = g(exp, "Plan: Zip goes from Tartu to Tallinn by bus.", [["move", "Zip", "Tartu", "Tallinn", "bus"]], ref)
  need(r["grade"] == "invalid", "C5 an invalid plan answer to a reachable True: %r" % r)
  exp, ref = R["robot_public_route"]
  r = ac.grade(exp, "No plan found.", None, ref)
  need(exp is None and r["grade"] == "match", "C5 No plan found. for a reachable Unknown: %r" % r)
  exp, ref = R["plan_route_dead_end"]
  r = ac.grade(None, "No plan found.", None, ref)
  need(r["grade"] == "mismatch", "C5 No plan found. for Unknown of a plan question: %r" % r)
  out.append("C5 a plan answer to a reachable True replayed; No plan found. matches a reachable Unknown only")
  # C6: the translation up to renaming
  exp, ref = R["c11_method_collision:tools_distinguish:Q1"]
  pk = [u["stage2"] for u in ref["formal"]["units"]] + [ref["formal"]["query"]["stage2"]]
  ren = {"Ann 1": "Ann 7", "egg 2": "egg 3", "S1": "S9", "S2": "S8"}

  def rename(x):
    return [rename(y) for y in x] if isinstance(x, list) else ren.get(x, x)
  rec = {"translation": {"stage2": {"packages": rename(pk)}}}
  need(ac.translation_equal(rec, ref) is True, "C6 equal up to renaming")
  changed = rename(pk)
  changed[1][2][2][2][3] = "boiled"
  rec = {"translation": {"stage2": {"packages": changed}}}
  need(ac.translation_equal(rec, ref) is False, "C6 a changed value")
  need(ac.translation_equal({"translation": {}}, ref) is None, "C6 without an accepted translation")
  need("translation_equal" in ac.grade(exp, "No plan found.", rec, ref), "C6 in the grade")
  # worlds, contexts and query selections (Sol's review): row 4 has the snapshots W0 and W1
  exp, ref = R["default_root_two_snapshots"]
  pk, types, worlds, contexts, sel = ac.reference_translation(ref)

  def same(packages=pk, ctx=contexts, qsel=sel, ws=worlds):
    return ac.translation_equal({"translation": {"stage2": {"packages": packages, "types": types, "worlds": ws,
                                                            "contexts": ctx, "query_contexts": qsel}}}, ref)
  need(same() is True and same(qsel={"S4": {"planning_root": "W1"}}) is True
       and same(ctx={"S1": {"tense": "present"}}) is True, "C6 the default root and tense are equal to explicit ones")
  moved = json.loads(json.dumps(pk))
  moved[1][2][1] = "W0"
  need(same(packages=moved) is False, "C6 a fact moved to another world")
  need(same(qsel={"S4": {"planning_root": "W0"}}) is False, "C6 another root")
  need(same(ctx={"S1": {"tense": "past"}}) is False, "C6 another tense")
  need(same(qsel={"S4": {"knower": "Mira 1"}}) is False, "C6 a knower")
  need(same(ws=["W0"]) is False, "C6 another world declaration")
  out.append("C6 equal up to renaming, a changed value differs, no translation gives None; a changed world, root, "
             "tense, knower or world declaration differs, and an explicit default root or tense present is equal")
  return "fixes: " + "; ".join(out)


def check_cannot(R):
  exp, ref = R["nested_places"]
  need(isinstance(exp, list) and exp[0] == "No action is needed." and exp[1].startswith("Cannot answer"), exp)
  rows = [("Cannot answer: the route read one place as inside another, or one thing at two places at once, which "
           "it does not model. [unsupported_location_granularity; S4]", "not_answered", True),
          ("Cannot answer: the route read a rule as a restriction of a means, an actor or a tool, which it does not "
           "model. [unsupported_restriction_scope; S2]", "not_answered", False),
          ("Unknown.", "not_answered", None), ("No plan found.", "not_answered", None),
          ("No action is needed.", "match", None),
          ("Plan: Mira goes from Harbor to Hilltown by bus.", "definite_answer", None),
          ("Yes.", "definite_answer", None), ("Error: translation_invalid: Stage 2: ...", "error", None)]
  for ans, want, agrees in rows:
    r = ac.grade(exp, ans, None, ref)
    need(r["grade"] == want, "nested_places %r: %r" % (ans, r))
    if want == "not_answered":
      need(r["detail"]["reason_agrees"] == agrees, "reason_agrees %r: %r" % (ans, r["detail"]))
  exp, ref = R["x01_identity:agentless:Q1"]
  need(isinstance(exp, str) and exp.startswith("Cannot answer"), exp)
  r = ac.grade(exp, "Plan: Ann whisks the egg.", None, ref)
  need(r["grade"] == "definite_answer", "a plan on a Cannot answer row without alternative: %r" % r)
  exp, ref = R["slot_restriction_unsupported"]
  r = ac.grade(exp, "Plan: Mira goes from Harbor to Hilltown by ship.", None, ref)
  need(r["grade"] == "listed" and r["detail"]["alternative"] == 0, "the listed plan of a Cannot answer row: %r" % r)
  return "cannot: Cannot answer (the reason code agreeing or not), Unknown. and No plan found. are not_answered; the " \
         "listed No action is needed. matches; a plan and Yes. are definite answers; an Error: is an error; a listed " \
         "plan alternative is compared by its text"


def check_error():
  for exp in (True, False, None, "No plan found.", "Plan: a.", "Cannot answer: x.", ["No action is needed.", "Cannot answer: x."]):
    r = ac.grade(exp, "Error: model_timeout: a detail")
    need(r["grade"] == "error" and not r["correct"], "Error: against %r: %r" % (exp, r))
  return "error: Error: is wrong against every expected value"


def check_rows():
  rows, built = mp.build()
  tests, rr = built["rows"]
  row = [t for t in tests if t[0] == 65][0]
  ref = ac.reference_of(row)
  need(ref == {k: v for k, v in rr["65"].items() if k not in ("id", "expected")},
       "reference_of: the row's reference with its text")
  listed = [["move", "Oskar", "Lund", "Malmo", "bus"], ["move", "Oskar", "Malmo", "Copenhagen", "train"],
            ["move", "Oskar", "Copenhagen", "Oslo", "ferry"]]
  r = ac.grade_row(row, row[2], record(listed))
  need(r == ac.grade(row[2], row[2], record(listed), ref) and r["grade"] == "listed" and r["detail"]["by"] == "terms",
       "grade_row with the row's reference: %r" % r)
  r = ac.grade_row(row[:3], row[2], record(listed))
  need(r["grade"] == "listed" and r["detail"]["by"] == "text", "a row without a reference: %r" % r)
  return "rows: grade_row grades with the row's reference and its text; a row without a reference compares by text"


def run():
  R = refs()
  for line in (check_plans(R), check_answers(R), check_fixes(R), check_cannot(R), check_error(), check_rows()):
    print("  " + line)


if __name__ == "__main__":
  run()
