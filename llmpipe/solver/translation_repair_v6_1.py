"""WP6: a broken translation is repaired once, or recorded as a failure.

A case whose translation failed used to walk into bridge generation carrying
nothing to bridge, and — worse — an accepted-Unknown case that failed this way
was scored as a correct abstention.  It is neither: nothing was understood.

What counts as a failure, before any candidate atom is built:

  * the parse recorded `parse_failed`;
  * Stage 1 or Stage 2 is missing or unreadable;
  * no clause theory was produced, or the final clause list is missing;
  * there is no usable question clause, or several incompatible ones;
  * the conservative answer begins with `Error:`.

Then exactly one bounded correction attempt is made, with the arm's own model:

  * Stage 1 invalid  -> one Stage-1 correction request, then Stage 2 normally;
  * Stage 1 valid, the question unusable -> one Stage-2 question correction
    request carrying the original question, the valid Stage-1 units, the failed
    response and the exact validation error.

The correction request always contains the error, so it is a different request
from the one that failed.  Every request/reply pair is fingerprinted: a pair
that has already failed is never sent again, and that path stops with
`repeated_failed_request_reply`.  The ordinary validators judge the reply; a
question-shaped string is not enough.

If the one attempt fails the case stops with `translation_failure`, makes no
bridge call and no dynamic gk call, and is never counted as an abstention.
"""

import hashlib
import json

import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB

VERSION = "translation_repair_v6_1/1.0"

TRANSLATION_FAILURE = "translation_failure"
REPEATED = "repeated_failed_request_reply"

NO_STAGE1 = "stage1_missing_or_unreadable"
NO_STAGE2 = "stage2_missing_or_unreadable"
NO_CLAUSES = "no_clause_theory"
NO_QUESTION = "no_usable_question_clause"
MANY_QUESTIONS = "incompatible_question_clauses"
PARSE_FAILED = "parse_failed"
ERROR_ANSWER = "conservative_answer_is_an_error"


def _question_clauses(view):
    out = []
    for clause in view.get("final_clauses") or []:
        if FB._source_kind(clause) == UA.QUESTION:
            out.append(clause)
        elif clause.get("@question") is not None:
            out.append(clause)
    return out


def _question_sources(clauses):
    """The sentences the question clauses came from.

    One English question converts to MANY clauses — the negated goal in CNF —
    and `folio-0101` has 44 of them from one sentence.  So the count of clauses
    says nothing; what would be incompatible is question clauses from more than
    one source sentence, which is a translation that asked two things at once.
    """
    return set(str(c.get("@name") or "") for c in clauses)


def _blank(term):
    if isinstance(term, str):
        return "?" if UA.is_clause_variable(term) else term
    if isinstance(term, list):
        return [_blank(x) for x in term]
    return term


def status_of(view, conservative=None):
    """-> {usable, why, detail}.  Checked before any candidate is built."""
    detail = {}
    if view.get("parse_failed"):
        return {"usable": False, "why": PARSE_FAILED, "detail": detail}
    if not view.get("stage1"):
        return {"usable": False, "why": NO_STAGE1, "detail": detail}
    if not view.get("stage2"):
        return {"usable": False, "why": NO_STAGE2, "detail": detail}
    clauses = view.get("final_clauses")
    if not clauses:
        return {"usable": False, "why": NO_CLAUSES, "detail": detail}
    questions = _question_clauses(view)
    detail["question_clauses"] = len(questions)
    if not questions:
        return {"usable": False, "why": NO_QUESTION, "detail": detail}
    sources = _question_sources(questions)
    detail["question_source_sentences"] = sorted(sources)
    if len(sources) > 1:
        return {"usable": False, "why": MANY_QUESTIONS, "detail": detail}
    answer = (conservative or {}).get("answer")
    if isinstance(answer, str) and answer.strip().lower().startswith("error"):
        detail["answer"] = answer[:120]
        return {"usable": False, "why": ERROR_ANSWER, "detail": detail}
    return {"usable": True, "why": None, "detail": detail}


def fingerprint(sysprompt, request, reply):
    return hashlib.sha256(("%s\x00%s\x00%s" % (sysprompt, request, reply or ""))
                          .encode()).hexdigest()


def no_repair(status):
    """The record written when no repair callable was supplied."""
    return {"version": VERSION, "attempted": False, "usable": False,
            "why": status["why"],
            "note": "no correction attempt was configured for this run"}


STAGE1_CORRECTION = """The previous response could not be used.

VALIDATION ERROR:
%s

THE RESPONSE THAT FAILED:
%s

Read the original text again and return a corrected Stage-1 result in the same
format. Fix only what the validation error names."""

STAGE2_CORRECTION = """The previous response could not be used: its question \
package is missing or unusable.

VALIDATION ERROR:
%s

THE ENGLISH QUESTION:
%s

THE STAGE-1 UNITS, WHICH ARE VALID AND MUST BE PRESERVED:
%s

THE RESPONSE THAT FAILED:
%s

Return the corrected Stage-2 result. Preserve the non-question logic exactly as
it is and correct only the question package."""


def stage1_correction(text, error, failed_reply):
    return STAGE1_CORRECTION % (error, (failed_reply or "")[:4000])


def stage2_correction(question, units, error, failed_reply):
    return STAGE2_CORRECTION % (error, question,
                                json.dumps(units)[:4000],
                                (failed_reply or "")[:4000])


class Repair(object):
    """One bounded correction attempt, with the arm's own model.

    The caller supplies `parse`, which re-runs the ordinary pipeline for a
    corrected response, so the ordinary validators judge it.  Nothing here
    decides that a reply is good because it looks like a question.
    """

    def __init__(self, respond, parse, case_id, seen=None):
        self.respond = respond
        self.parse = parse
        self.case_id = case_id
        self.seen = seen if seen is not None else set()
        self.log = []

    def __call__(self, view, status):
        got = {"version": VERSION, "attempted": True, "usable": False,
               "why": status["why"], "requests": []}
        stage = "stage1" if status["why"] in (NO_STAGE1, PARSE_FAILED) \
            else "stage2"
        error = "%s (%s)" % (status["why"],
                             json.dumps(status.get("detail") or {}))
        if stage == "stage1":
            request = stage1_correction(view.get("input_text"), error,
                                        view.get("stage1_raw"))
        else:
            request = stage2_correction(
                (view.get("_split") or {}).get("question")
                or view.get("input_text"), view.get("stage1"), error,
                view.get("stage2_raw"))
        key = fingerprint(stage, request, "")
        if key in self.seen:
            got.update({"stopped": REPEATED,
                        "note": "this correction request has already failed "
                                "for this case"})
            return got
        self.seen.add(key)
        reply, note = self.respond("format_retry_%s" % stage,
                                   "%s/%s_repair" % (self.case_id, stage),
                                   request)
        pair = fingerprint(stage, request, reply)
        got["requests"].append({"stage": stage, "request": request,
                                "request_sha256": hashlib.sha256(
                                    request.encode()).hexdigest(),
                                "reply": reply, "llm_note": note,
                                "pair_sha256": pair})
        if pair in self.seen:
            got.update({"stopped": REPEATED,
                        "note": "this request produced a reply that has "
                                "already failed"})
            return got
        self.seen.add(pair)
        try:
            fixed = self.parse(view, stage, reply)
        except Exception as e:                                  # noqa: BLE001
            got.update({"stopped": "the corrected response did not parse",
                        "error": "%s: %s" % (type(e).__name__, e)})
            return got
        if fixed is None:
            got["stopped"] = "the corrected response produced no view"
            return got
        after = status_of(fixed)
        got["status_after"] = after
        if not after["usable"]:
            got["stopped"] = "the corrected response is still unusable: %s" \
                % after["why"]
            return got
        got.update({"usable": True, "view": fixed})
        return got
