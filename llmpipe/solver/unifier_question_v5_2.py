"""Separating the passage from the question, corrected (WP2).

The v5.1 splitter removed the final sentence only when it carried at least 70%
of the wording Stage 1 stored for the question.  On these benchmarks Stage 1
often paraphrases — `Who is nice?` is stored as `Which entity is nice?` — so
five of ninety cases were refused although the input plainly ended in its own
question, and refusing them means not running them at all.

The rule here is the one the audit asks for:

  * Stage 1 has a `question` or `query` unit AND the input's final sentence ends
    in `?`  ->  remove that final sentence and show it, exactly as written, as
    the question.  Word containment stays in the record as a diagnostic and no
    longer decides anything;
  * Stage 1 has no question or query unit  ->  a final `?` alone is not enough
    and the case is UNRESOLVED.  `folio-0006` ends in the annotation
    `[contrapositive is more natural]?` and has no stored query: it stays
    refused;
  * the input ends declaratively and Stage 1 supplies a question of its own ->
    the v5.1 separate-field behaviour, admitted only when the input
    demonstrably does not already carry that question.

`unifier_prompt_v5` and `_v5_1` are not modified; their sentence scanner, word
scanner and stored-question reader are imported.
"""

import unifier_prompt_v5 as P5

VERSION = "unifier_question_v5_2/1.0"

EXACT_SUFFIX = P5.EXACT_SUFFIX
FINAL_QUESTION = "final_question_sentence_removed"
SEPARATE_FIELD = P5.SEPARATE_FIELD
UNRESOLVED = P5.UNRESOLVED

ALLOWED_SPLITS = (EXACT_SUFFIX, FINAL_QUESTION)

# Only for the separate-field fallback: how much of the stored question's
# wording the passage may carry before showing it as a separate field would be
# showing the question twice.
SEPARATE_FIELD_MAX_OVERLAP = 0.5

stored_question = P5.stored_question

WHY_REFUSED = {
    UNRESOLVED: "Stage 1 recorded no question or query unit, so the question "
                "cannot be separated from the passage",
    SEPARATE_FIELD: "the input does not end in a question and its wording "
                    "already carries the stored question, so showing that "
                    "question as a separate field would also state it as a "
                    "passage fact",
}


def split_case_text(view):
    """-> {status, passage, question, stored_question, evidence}."""
    text = (view.get("input_text") or "").strip()
    stored = stored_question(view).strip()
    sents = P5._sentences(text)
    last = sents[-1] if sents else ""
    evidence = {"final_sentence": last,
                "final_sentence_is_a_question": last.endswith("?"),
                "stored_question": stored,
                "containment": round(P5._containment(stored, last), 4)
                if stored else None,
                "containment_is_diagnostic_only": True,
                "sentences": len(sents)}
    if not stored:
        return {"status": UNRESOLVED, "passage": text, "question": "",
                "stored_question": "", "version": VERSION,
                "evidence": dict(evidence,
                                 why="Stage 1 recorded no question or query "
                                     "unit")}
    if text.endswith(stored):
        return {"status": EXACT_SUFFIX,
                "passage": text[:len(text) - len(stored)].strip(),
                "question": stored, "stored_question": stored,
                "version": VERSION,
                "evidence": dict(evidence,
                                 why="the stored question is a literal suffix "
                                     "of the input text")}
    if last.endswith("?"):
        return {"status": FINAL_QUESTION,
                "passage": text[:len(text) - len(last)].strip(),
                "question": last, "stored_question": stored,
                "version": VERSION,
                "evidence": dict(evidence,
                                 why="Stage 1 stored a question and the input's "
                                     "final sentence is itself a question, so "
                                     "that sentence is the question and is "
                                     "shown as the passage wrote it")}
    return {"status": SEPARATE_FIELD, "passage": text, "question": stored,
            "stored_question": stored, "version": VERSION,
            "evidence": dict(evidence,
                             why="the input does not end in a question, so "
                                 "nothing was removed and Stage 1's question "
                                 "is shown on its own")}


def question_preflight(view):
    """-> one row.  May this case be sent at all?

    Fails closed: a case whose question cannot be separated is refused for
    review rather than shown with its question standing in the passage.
    """
    split = split_case_text(view)
    status = split["status"]
    allowed = status in ALLOWED_SPLITS
    why = None
    overlap = None
    if not allowed:
        why = WHY_REFUSED.get(status, "unknown split status")
        if status == SEPARATE_FIELD:
            words = P5._words(split["question"])
            carried = set(P5._words(split["passage"]))
            overlap = (sum(1 for w in words if w in carried) / float(len(words))
                       if words else 1.0)
            if overlap < SEPARATE_FIELD_MAX_OVERLAP:
                allowed, why = True, None
    return {"case_id": view.get("case_id"), "status": status,
            "llm_call_allowed": allowed, "why_refused": why,
            "question": split["question"],
            "passage_overlap_with_the_question": overlap,
            "version": VERSION, "evidence": split["evidence"]}
