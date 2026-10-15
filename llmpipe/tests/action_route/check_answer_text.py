"""The answer text of the action route and the plan sentence, offline.

  table     one fixed answer form per question kind and outcome (docs/architecture/action-answers.md, "Answer
            text"): Plan:, No action is needed., No plan found., Yes. Plan:, Unknown., Yes., No., a name,
            Inconsistent: in English, Cannot answer:, Error:; a stated probability below 0.95 gives Probably
            (A1), the frame part of a confidence gives nothing
  reasons   every reason code that an unsupported outcome can carry has an English sentence of the form "the route
            read ..., which ..." (A3)
  render    T1 the value of a change with a result role, and no participle of the verb (A4: a participle test, no
            shared beginning); T2 a one-letter name
            with a stated class; T3 a capital first letter; T4 one sentence per step; T5 the plan with names; T6 a
            wh-answer by the plan's naming; a move after another kind of step keeps its verb; the change of the actor
            itself names its Stage-1 target with a or an (A4)
  resume    runtests keeps a Cannot answer case on a resume with -redo-errors and repeats an Error: case

No model call, no GK launch (the wh-answer runs on a fake GK build of check_action_answer).
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE, ROOT]

import action_answer as aa              # noqa: E402

import linguistics

import action_english as aen
import action_gk as ag                  # noqa: E402
import action_pipeline as ap            # noqa: E402
import action_replay as rp              # noqa: E402
import action_route as ar               # noqa: E402
import check_action_answer as caa       # noqa: E402
import check_action_round3 as c3        # noqa: E402
import lc_action as la                  # noqa: E402
import lc_action_query as lq            # noqa: E402

need = caa.need


def result(outcome, kind=None, **fields):
  return dict({"outcome": outcome, "query": {"kind": kind} if kind else None, "diagnostics": []}, **fields)


def check_table():
  rows = [
    (result("plan_found", "plan", render="Ann goes from A to B by bus"), "Plan: Ann goes from A to B by bus."),
    (result("goal_already_holds", "plan", render="No action is needed: the goal already holds"), "No action is needed."),
    (result("not_found", "plan", answer="none"), "No plan found."),
    (result("plan_found", "reachable", render="Ann goes from A to B by bus"), "Yes. Plan: Ann goes from A to B by bus."),
    (result("goal_already_holds", "reachable"), "Yes. No action is needed."),
    (result("not_found", "reachable", answer="Unknown"), "Unknown."),
    (result("verification_result", "verify", answer="Yes"), "Yes."),
    (result("verification_result", "question", answer="No"), "No."),
    (result("verification_result", "executable", answer="Unknown"), "Unknown."),
    (result("verification_result", "question", answer="contested"), "Contested."),
    (result("verification_result", "executable", answer="Yes",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.6}), "Probably yes."),
    (result("verification_result", "question", answer="No",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.8}), "Probably no."),
    (result("verification_result", "question", answer="Yes",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.95}), "Yes."),
    (result("verification_result", "question", answer="Yes",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.9499}), "Probably yes."),
    (result("verification_result", "verify", answer="Yes",
            confidence_parts={"frame_uses": {"frame_have": 1}, "frame_product": 0.99, "other_uncertain_uses": {},
                              "other_product": 1.0}), "Yes."),
    (result("plan_found", "plan", render="Robo goes from A to B by bus",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.6}), "Probable plan: Robo goes from A to B by bus."),
    (result("plan_found", "reachable", render="Robo goes from A to B by bus",
            confidence_parts={"frame_uses": {}, "frame_product": 1.0, "other_uncertain_uses": {"S3": 1},
                              "other_product": 0.6}), "Probably yes. Plan: Robo goes from A to B by bus."),
    (result("verification_result", "ask", answer="key 2", answers=["key 2"], answer_names=["the key"]), "The key."),
    (result("verification_result", "ask", answer="key 2", answers=["key 2", "cup 3"],
            answer_names=["the key", "the cup"]), "The key and the cup."),
    (result("inconsistent_action_state", "plan", facts=["empty(hand,W0)", "holding(hand,a,W0)"],
            facts_english=["the robot hand is empty", "the robot hand holds block a"]),
     "Inconsistent: the robot hand is empty and the robot hand holds block a."),
    (result("candidate_not_validated", "plan"), "Unknown: no candidate plan was validated."),
    (result("source_compiled"), "Source compiled: no question."),
    (result("unsupported_translation", reasons=["unsupported_location_granularity"], units=["S4"]),
     "Cannot answer: the route read one place as inside another, or one thing at two places at once, which it "
     "does not model. "
     "[unsupported_location_granularity; S4]"),
    (result("unsupported_translation", "plan", diagnostics=[{"reasons": ["occurrence"], "units": ["S1", "S2"]}]),
     "Cannot answer: the route read a sentence as a report of an action that happened, which it does not model. "
     "[occurrence; S1, S2]"),
    (result("unsupported_backend_requirement", "verify",
            diagnostics=[{"reason": "negative_persistence_unavailable", "units": ["S3"]}]),
     "Cannot answer: the route read the question as needing a negative fact kept across an action, which its "
     "prover does not support yet. [negative_persistence_unavailable; S3]"),
    (result("unsupported_translation", reasons=["ambiguous_directive"], units=["S2"]),
     "Cannot answer: the route read the request in more than one way, which it does not resolve. "
     "[ambiguous_directive; S2]"),
    (result("unsupported_translation", reasons=["unsupported_restriction_scope"], units=["S2"]),
     "Cannot answer: the route read a rule as a restriction of a means, an actor or a tool, which it does not "
     "model. [unsupported_restriction_scope; S2]"),
    (result("unsupported_translation", reasons=["a_new_code"], units=[]),
     "Cannot answer: the route read a form of the text, which it does not model. [a_new_code; -]"),
  ]
  for res, want in rows:
    got = aen.answer_text(res)
    need(got == want, "%s: %r, expected %r" % (res["outcome"], got, want))
  for outcome in ("translation_invalid", "model_timeout", "call_limit", "prover_error", "backend_unavailable",
                  "insufficient_search_allowance", ar.NOT_IMPLEMENTED):
    got = aen.answer_text(result(outcome, diagnostics=["a detail"]))
    need(got == "Error: %s: a detail" % outcome, "%s: %r" % (outcome, got))
    need(not aen.answered(result(outcome)), "%s is no answer" % outcome)
  for outcome in aen.CANNOT_ANSWER:
    need(not aen.answered(result(outcome)), "%s stays no answer in the record" % outcome)
  return "table: %d answer forms; %d failed-run outcomes give Error:; Cannot answer outcomes stay unanswered in the " \
         "record" % (len(rows), 7)


def check_reasons():
  codes = set(la.REASONS) | set(lq.UNAVAILABLE.values()) | {"ambiguous_directive", "unsupported_request",
                                                            "capability_not_validated"}
  missing = sorted(codes - set(aen.REASON_SENTENCES))
  need(not missing, "reason codes without a sentence: %s" % missing)
  bad = [k for k, v in aen.REASON_SENTENCES.items() if not v or v[0].isupper() or v.endswith(".")]
  need(not bad, "a sentence starts in lower case and has no final period: %s" % bad)
  # A3: what the route read, and why it gives no answer; no quoted word
  form = [k for k, v in aen.REASON_SENTENCES.items() if not v.startswith("the route read ") or ", which " not in v
          or '"' in v]
  need(not form, "a sentence outside the form \"the route read ..., which ...\": %s" % form)
  return "reasons: %d reason codes, each with a sentence of the form \"the route read ..., which ...\"" % len(codes)


def gold(case):
  with open(os.path.join(HERE, "v6", "cohort.json")) as f:
    e = {x["id"]: x for x in json.load(f)}[case]
  rec = c3.compile_gold(e)
  src, q = rec["source"], rec["queries"][0]
  qa = ar.compile_query(q, src, **(e["stage2"].get("query_contexts") or {}).get(q[1], {}))
  return e, src, qa


def rendered(case, plan=None):
  e, src, qa = gold(case)
  plan = plan or e["answer_expect"]["plan"]
  r = rp.replay(src, plan, goal=qa["query"]["goal"], steps=qa["query"]["steps"], **lq.selection_of(qa))
  need(r["verdict"] == "valid", "%s: the gold plan replays: %s" % (case, r["reason"]))
  return src, plan, r["steps"]


def check_render():
  out = []
  # T1: a result role adds the value; a participle of the verb is left out; no result role, no value
  for case, want in (("plan_travel_then_paint", "Greta goes from Bergen to Voss by train, then paints the cabin red"),
                     ("plan_two_objects_one_tool", "Lin paints the door white with the brush, then paints the shutter "
                                                   "green with the brush"),
                     ("worked_p03_food", "Ann breaks the egg, then whisks the egg with the whisk, then cooks the egg "
                                         "in the pan"),
                     ("plan_precondition_other_object", "Pia heats the oven, then bakes the bread")):
    src, plan, steps = rendered(case)
    got = aen.render(src, plan, steps)
    need(got == want, "%s: %r" % (case, got))
  need(not aen.repeats_verb("paint", "red") and aen.repeats_verb("cook", "cooked") and aen.repeats_verb("bake", "baked"),
       "the participle rule")
  # A4: a participle test, no shared beginning
  for root, value, same in (("tie", "tied", True), ("tie", "tight", False), ("fry", "fried", True),
                            ("chop", "chopped", True), ("break", "broken", True), ("cook", "cool", False),
                            ("open", "opened", True), ("whisk", "whisked", True), ("heat", "heated", True),
                            ("dry", "dry", False), ("paint", "painted", True), ("pain", "painted", False)):
    need(aen.repeats_verb(root, value) == same, "A4: %s %s" % (root, value))
  need(linguistics.indef_article("egg") == "an" and linguistics.indef_article("licence") == "a" and linguistics.indef_article("umbrella") == "an", "A4: a or an")
  out.append("T1 a result value (red, white, green), no participle (cooks the egg), no value without a result role; "
             "A4 the participle test (tie tied, not tie tight) and a or an")
  # T2: block c has no class in the identity map; the source states it
  src, plan, steps = rendered("plan_unstack_then_take")
  need(not (src["identity"]["c 4"] or {}).get("class") and aen.name(src, "c 4") == "block c", "T2")
  out.append("T2 block c from a stated class")
  # T3, T4, T5
  got = aen.render(src, plan, steps)
  need(got == "The hand takes block c, then puts block c on the table, then takes block a", "T3: %r" % got)
  need(aen.plan_steps(src, plan, steps) == ["The hand takes block c.", "The hand puts block c on the table.",
                                           "The hand takes block a."], "T4")
  need(aen.plan_named(src, plan) == [["take", "hand", "c"], ["put_on", "hand", "c", "table"], ["take", "hand", "a"]],
       "T5")
  out.append("T3 a capital letter, T4 a sentence per step with its actor, T5 the plan with names")
  # T6: a wh-answer by the plan's naming (a fake GK build answers the ask)
  r = caa.solve("c18_initial_binding:base", "Q5", {"q:positive": caa.answers((["#:Ann 1"], 1.0))})
  need(r["answer_names"] == ["Ann"] and aen.answer_text(r) == "Ann.", "T6: %r" % r.get("answer_names"))
  e, src, qa = gold("snapshot_ask")
  need(aen.name(src, "key 2") == "the key", "T6: the key")
  out.append("T6 Ann. and the key")
  # a move after a change keeps goes; the change of the actor itself names its Stage-1 target
  import fixture_materialize as fm
  import check_action_validation as cv
  c = {x["case"]: x for x in fm.load_all()}["c02_licence_granted:base"]
  src = cv.gold_source(c)
  q = [x for x in c["queries"] if x["id"] == "Q1"][0]
  plan = q["expect"]["on_validated_backend"]["plan"]
  qa = ar.compile_query(q["stage2"], src, None, {"validated": ["negative_persistence"]})
  r = rp.replay(src, plan, goal=qa["query"]["goal"], steps=qa["query"]["steps"])
  got = aen.render(src, plan, r["steps"])
  need(got == "Ann obtains a licence, then goes from Haapsalu to Tallinn by bus", "c02: %r" % got)
  out.append("a move after a change keeps goes; Ann obtains a licence")
  return "render: " + "; ".join(out)


def check_resume():
  import runtests
  d = tempfile.mkdtemp()
  kept = []
  for name, payload in (("cannot", {"answer": "Cannot answer: the text puts one place inside another. [x; S1]"}),
                        ("error", {"answer": "Error: translation_invalid: Stage 2: ..."}),
                        ("error_key", {"answer": None, "error": {"exception": "PipelineError"}}),
                        ("answer", {"answer": "Plan: Ann goes from A to B by bus."})):
    path = os.path.join(d, name + ".json")
    with open(path, "w") as f:
      json.dump(payload, f)
    kept.append((name, runtests.should_skip(path, True), runtests.should_skip(path, False)))
  need(kept == [("cannot", True, True), ("error", False, True), ("error_key", False, True), ("answer", True, True)],
       "resume: %r" % kept)
  need(not runtests._answer_is_definite("Cannot answer: x. [y; S1]") and runtests._answer_is_definite("Plan: a."),
       "a Cannot answer is no definite answer")
  return "resume: with -redo-errors a Cannot answer case is kept and an Error: case is repeated; without it both stay"


def run():
  try:
    for line in (check_table(), check_reasons(), check_render(), check_resume()):
      print("  " + line)
  finally:
    while caa.FAKES:
      ag.BACKENDS.pop(caa.FAKES.pop(), None)


if __name__ == "__main__":
  run()
