"""The clear positive prompt, built from the COMPLETE inventory (WP3).

`unifier_prompt_v5_1` builds its positive groups from whatever the v4 candidate
builder hands it, and that has already been truncated to 80 Stage-2 rows and 24
final-clause rows.  On `mle-0087` thirteen writable positive atoms were removed
before the prompt was rendered.  The prompt was concise; the inventory was not
complete.

Here the inventory is built with limits high enough that no case of either
frozen cohort reaches them — the preflight proves it — and every surviving
group is displayed.  There is no hidden row or group cap.  A single technical
guard remains: a user message over `MAX_USER_MESSAGE_CHARS` refuses the case and
is reported, and is never truncated.

Each displayed group also records whether it existed under the old 80/24 caps,
by building the same inventory a second time with those caps, so any gain can be
attributed honestly.

The system prompt, the display check, the writability probe, the sections and
the renderers are `unifier_prompt_v5_1`'s, imported unchanged.  The passage /
question split is `unifier_question_v5_2`'s.
"""

import unifier_candidates_v4 as CV4
import unifier_prompt_v5_1 as P51
import unifier_question_v5_2 as Q

VERSION = "unifier_prompt_v5_2/1.0"

# High enough that no case of the frozen cohorts reaches them; the preflight
# asserts it rather than assuming it.
MAIN_CAP = 400
SECONDARY_CAP = 200

OLD_MAIN_CAP = CV4.MAIN_CAP
OLD_SECONDARY_CAP = CV4.SECONDARY_CAP

# A safety refusal, not a truncation point.
MAX_USER_MESSAGE_CHARS = 60000

PromptError = P51.PromptError

system_prompt = P51.system_prompt
system_prompt_sha256 = P51.system_prompt_sha256
example_sha256 = P51.example_sha256
check_fixed_inputs = P51.check_fixed_inputs
attempted_status = P51.attempted_status
printed_rule = P51.printed_rule
printed_atom = P51.printed_atom
render_case = P51.render_case
render_candidates = P51.render_candidates
render_attempted = P51.render_attempted
CLOSING_LINE = P51.CLOSING_LINE
NO_PROOF_BLOCK = P51.NO_PROOF_BLOCK
ALTERNATIVE_BLOCK = P51.ALTERNATIVE_BLOCK

split_case_text = Q.split_case_text
question_preflight = Q.question_preflight


def complete_inventory(view, configuration):
    """The v4 candidate inventory with limits no case reaches."""
    return CV4.build(view, configuration, main_cap=MAIN_CAP,
                     secondary_cap=SECONDARY_CAP)


def _surface_keys(candidates):
    import unifier_abstraction as UA
    return set(UA.alpha_key(r["surface_atom"])
               for r in (candidates.get("main") or [])
               + (candidates.get("secondary") or []))


def build_candidates(view, configuration, complete=None, old=None):
    """-> the v5.1 candidate record, over the complete inventory, annotated.

    `available_under_the_old_caps` is measured, not inferred: the same builder
    is run again with the v4 caps and the surface atoms are compared.
    """
    import unifier_abstraction as UA
    complete = complete if complete is not None else complete_inventory(
        view, configuration)
    old = old if old is not None else CV4.build(view, configuration)
    got = P51.build_candidates(view, configuration, complete)
    old_keys = _surface_keys(old)
    for g in got["groups"]:
        seen = [UA.alpha_key(a) for a in g["surface_atoms"]]
        g["available_under_the_old_caps"] = any(k in old_keys for k in seen)
        g["hidden_by_the_old_caps"] = not g["available_under_the_old_caps"]
    hidden = [g["id"] for g in got["groups"] if g["hidden_by_the_old_caps"]]
    got["version"] = VERSION
    got["inventory"] = {
        "complete_main_rows": len(complete.get("main") or []),
        "complete_secondary_rows": len(complete.get("secondary") or []),
        "old_cap_main_rows": len(old.get("main") or []),
        "old_cap_secondary_rows": len(old.get("secondary") or []),
        "limits_used": {"main_cap": MAIN_CAP, "secondary_cap": SECONDARY_CAP},
        "old_limits": {"main_cap": OLD_MAIN_CAP,
                       "secondary_cap": OLD_SECONDARY_CAP},
        "reached_a_limit": (len(complete.get("main") or []) >= MAIN_CAP
                            or len(complete.get("secondary") or [])
                            >= SECONDARY_CAP),
    }
    got["counts"]["displayed_groups_hidden_by_the_old_caps"] = len(hidden)
    got["groups_hidden_by_the_old_caps"] = hidden
    return got


def _record(call, candidates, blocks, split, attempted=None):
    got = P51._record(call, candidates, blocks, split, attempted)
    got["version"] = VERSION
    got["size_guard"] = MAX_USER_MESSAGE_CHARS
    got["exceeds_size_guard"] = got["chars"] > MAX_USER_MESSAGE_CHARS
    if got["exceeds_size_guard"]:
        got["why_refused"] = ("the user message is %d characters, over the "
                              "%d-character guard; the case is refused rather "
                              "than truncated" % (got["chars"],
                                                  MAX_USER_MESSAGE_CHARS))
    return got


def build_initial_user_prompt(view, candidates):
    split = split_case_text(view)
    blocks = [render_case(split), render_candidates(candidates["sections"]),
              CLOSING_LINE]
    return _record("initial", candidates, blocks, split)


def _followup(call, block, view, candidates, attempted_rules, refusals):
    split = split_case_text(view)
    statuses = dict((r.get("rule_id"), attempted_status(r, candidates["groups"]))
                    for r in attempted_rules or [])
    blocks = [render_case(split), block,
              render_attempted(attempted_rules or [], statuses, refusals or []),
              render_candidates(candidates["sections"]), CLOSING_LINE]
    return _record(call, candidates, blocks, split, statuses)


def build_no_proof_user_prompt(view, candidates, attempted_rules, refusals):
    return _followup("no_proof", NO_PROOF_BLOCK, view, candidates,
                     attempted_rules, refusals)


def build_alternative_user_prompt(view, candidates, attempted_rules, refusals):
    return _followup("alternative", ALTERNATIVE_BLOCK, view, candidates,
                     attempted_rules, refusals)
