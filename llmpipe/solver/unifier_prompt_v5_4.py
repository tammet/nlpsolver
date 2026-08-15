"""The v5.4 no-proof message.  Only that message changes (WP5).

The initial call, the alternative call, the candidate display, the source
aliases, the clause-native forms and the fixed system prompt are v5.3's,
imported and unchanged.  What changes is the second message sent after a bridge
set proved nothing:

  * no question literal is named as a target, and no annotation says that a
    conclusion could reach one;
  * every atom the existing clauses can offer carries one honest category, and
    a question assumption is labelled as such;
  * the closing instruction asks for a chain that can START.
"""

import unifier_feedback_v5_4 as FB54
import unifier_prompt_v5_3 as PR53

VERSION = "unifier_prompt_v5_4/1.0"

MAX_USER_MESSAGE_CHARS = PR53.MAX_USER_MESSAGE_CHARS
MAIN_CAP = PR53.MAIN_CAP
SECONDARY_CAP = PR53.SECONDARY_CAP

# everything the plan freezes for the comparison
system_prompt = PR53.system_prompt
system_prompt_sha256 = PR53.system_prompt_sha256
example_sha256 = PR53.example_sha256
check_fixed_inputs = PR53.check_fixed_inputs
printed_atom = PR53.printed_atom
render_case = PR53.render_case
render_candidates = PR53.render_candidates
render_tried = PR53.render_tried
render_proof_used = PR53.render_proof_used
split_case_text = PR53.split_case_text
question_preflight = PR53.question_preflight
complete_inventory = PR53.complete_inventory
build_candidates = PR53.build_candidates
vocabulary_rows = PR53.vocabulary_rows
build_initial_user_prompt = PR53.build_initial_user_prompt
build_alternative_user_prompt = PR53.build_alternative_user_prompt
CLOSING_LINE = PR53.CLOSING_LINE

NO_PROOF_RESULT = PR53.NO_PROOF_RESULT

SUPPLIER_NOTE_OF = {
    FB54.PASSAGE: "MAY BE SUPPLIED BY: PASSAGE",
    FB54.GENERAL_LOGIC: "MAY BE SUPPLIED BY: GENERAL_LOGIC",
    FB54.QUESTION_ASSUMPTION: "MAY BE SUPPLIED BY: QUESTION_ASSUMPTION",
    FB54.EARLIER_PROPOSED_RULE: "MAY BE SUPPLIED BY: EARLIER_PROPOSED_RULE",
}


def supplier_annotations(candidates, feedback):
    """-> {group id: which category could supply this atom}.

    One category per atom, never "the existing clauses", and nothing about
    reaching a question literal.
    """
    import unifier_abstraction as UA
    out = {}
    order = list(FB54.CATEGORIES)
    for g in candidates["groups"]:
        literal = g["literal"]
        found = set()
        for s in feedback.get("suppliers") or []:
            if s["sign"] != UA.sign_of(literal):
                continue
            other = FB54.standardise_apart(UA.unsigned_atom(s["literal"]), "a")
            if FB54.unify(UA.unsigned_atom(literal), other, {}):
                found.add(s["category"])
        if found:
            best = [c for c in order if c in found][0]
            out[g["id"]] = SUPPLIER_NOTE_OF[best]
    return out


def build_no_proof_user_prompt(view, candidates, tried, refused, feedback):
    """The repair call: what could not start, and what is available instead."""
    split = split_case_text(view)
    annotations = supplier_annotations(candidates, feedback)
    blocks = [render_case(split), NO_PROOF_RESULT,
              render_tried(tried, refused=refused), FB54.render(feedback),
              render_candidates(candidates["sections"], annotations),
              FB54.INSTRUCTIONS]
    got = PR53._record("no_proof", candidates, blocks, split,
                       {"annotations": annotations,
                        "connection_report_version": feedback["version"]})
    got["version"] = VERSION
    return got
