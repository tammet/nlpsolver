"""The v5.9 revised case message: two atom lists, no provenance, one format.

The inventory is v5.4's, unchanged — the same complete candidate set, the same
displayed atom forms, aliases, clause-native forms, suggested roles, costs and
deterministic order.  What changes is what the model is told about it:

  * the question-related and other-content sections become one `MAIN ATOMS`
    list, in their previous relative order.  The earlier message told the model
    which atoms came from the question; the audit
    (`memos/MEMO_2026_08_14_first_second_bridge_generation_unsoundness.md`)
    found that this reads as a target, and rules were written to reach it;
  * no row carries a source, a source status or a supplier category.  A row is
    an id, an atom, a suggested role and a cost;
  * the second message no longer says "repair the first rules" or names an
    unreached question atom.  It says the first rules did not prove anything,
    that this is not evidence another rule exists, and that `NO_RULE` is a
    correct answer;
  * every rule must use at least one main atom, which is enforced in code as
    well as stated in the message.

The approved system prompt is used byte-for-byte for all three calls, so its
prefix stays cacheable.
"""

import hashlib
import os

import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_3 as PR53

VERSION = "unifier_prompt_v5_9/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_rules_v5_9_revised_system"

MAIN = "main"
HELPER = "helper"
MAIN_PREFIX, HELPER_PREFIX = "M", "H"

MAX_USER_MESSAGE_CHARS = PR53.MAX_USER_MESSAGE_CHARS
MAIN_CAP = PR53.MAIN_CAP
SECONDARY_CAP = PR53.SECONDARY_CAP

# the inventory itself is v5.4's, by reference
complete_inventory = PR53.complete_inventory
build_candidates = PR53.build_candidates
split_case_text = PR53.split_case_text
question_preflight = PR53.question_preflight
printed_atom = PR53.printed_atom
vocabulary_rows = PR53.vocabulary_rows

INITIAL_INSTRUCTIONS = """Propose sound implication rules connecting the \
displayed atoms. Every rule
must contain at least one main atom. Helpers may be used only when they add a
necessary link or restriction. Prefer lower total cost among equally sound
rules. If there is no sound connection, write NO_RULE."""

SECOND_INSTRUCTIONS = """Propose only rules not already tried. Every rule must \
contain at least one
main atom. Helpers may be used only when they add a necessary link or
restriction. Prefer lower total cost among equally sound rules. If there is no
additional sound connection, write NO_RULE."""

NO_PROOF_NOTE = """The rules tried in the first call did not produce a proof. \
This does not show
that another sound rule exists. Propose a different rule only if it is
independently reasonable. Otherwise write NO_RULE."""

ALTERNATIVE_NOTE = """The first rules produced a proof. Look for a different \
independently sound
connection that could support an alternative proof. Do not weaken semantic
standards merely to produce a different answer. If there is no additional sound
rule, write NO_RULE."""


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


# ------------------------------------------------------ the two atom lists

def relabel(candidates):
    """Merge the two content sections into MAIN and renumber M1.. / H1.. .

    The relative order inside each former section is the v5.4 order, and the
    former question-related atoms keep their place at the front: only the
    heading and the id prefix change, so a comparison with AL-92 stays about
    the message, not about which atoms were offered.
    """
    main, helper = [], []
    for name in (P51.QUESTION_SECTION, P51.CONTENT_SECTION):
        main.extend(candidates["sections"].get(name) or [])
    helper.extend(candidates["sections"].get(P51.HELPER_SECTION) or [])
    seen = {}
    ordered = []
    for g in main:                     # collapse only duplicates the builder
        key = g["printed"]             # already treated as one candidate
        if key in seen:
            continue
        seen[key] = True
        ordered.append(g)
    for i, g in enumerate(ordered, start=1):
        g["v5_4_id"] = g.get("v5_4_id", g["id"])
        g["id"] = "%s%d" % (MAIN_PREFIX, i)
        g["list"] = MAIN
    for i, g in enumerate(helper, start=1):
        g["v5_4_id"] = g.get("v5_4_id", g["id"])
        g["id"] = "%s%d" % (HELPER_PREFIX, i)
        g["list"] = HELPER
    candidates["lists"] = {MAIN: ordered, HELPER: helper}
    candidates["main_ids"] = set(g["id"] for g in ordered)
    candidates["helper_ids"] = set(g["id"] for g in helper)
    return candidates


def render_lists(candidates):
    parts = []
    for name, heading in ((MAIN, "MAIN ATOMS:"), (HELPER, "HELPER ATOMS:")):
        mine = (candidates.get("lists") or {}).get(name) or []
        if not mine:
            continue
        parts.append("%s\n\n%s" % (heading,
                                   "\n\n".join(P51.render_group(g)
                                               for g in mine)))
    return "\n\n".join(parts)


def render_case(split):
    return "\n".join(["CASE", "", "PASSAGE:", split["passage"], "",
                      "QUESTION:", split["question"]])


def render_tried(rules):
    lines = ["RULES ALREADY TRIED:", ""]
    if not rules:
        lines.append("  (none)")
    for r in rules:
        lines.append("  %s" % r.get("printed"))
    return "\n".join(lines)


def render_proof_used(cited, unused):
    parts = ["RULES USED IN THE PROOF:", ""]
    for r in cited:
        parts.append("  %s" % r.get("printed"))
    if not cited:
        parts.append("  (none)")
    parts += ["", "RULES TRIED BUT NOT USED:", ""]
    for r in unused:
        parts.append("  %s" % r.get("printed"))
    if not unused:
        parts.append("  (none)")
    return "\n".join(parts)


# ------------------------------------------------------------ the messages

def _record(call, candidates, blocks, split, extra=None):
    text = "\n\n".join(b for b in blocks if b)
    P51._forbidden(text)
    got = {"call": call, "version": VERSION,
           "case_id": candidates.get("case_id"),
           "system_prompt_name": SYSTEM_PROMPT_NAME,
           "system_prompt_sha256": system_prompt_sha256(),
           "text": text, "sha256": P51.sha256_of(text), "chars": len(text),
           "question_split": split, "counts": candidates["counts"],
           "main_atoms": len((candidates.get("lists") or {}).get(MAIN) or []),
           "helper_atoms": len((candidates.get("lists")
                                or {}).get(HELPER) or []),
           "size_guard": MAX_USER_MESSAGE_CHARS,
           "exceeds_size_guard": len(text) > MAX_USER_MESSAGE_CHARS}
    if got["exceeds_size_guard"]:
        got["why_refused"] = ("the user message is %d characters, over the "
                              "%d-character guard; the case is refused rather "
                              "than truncated" % (got["chars"],
                                                  MAX_USER_MESSAGE_CHARS))
    got.update(extra or {})
    return got


def build_initial_user_prompt(view, candidates):
    split = split_case_text(view)
    blocks = [render_case(split), render_lists(candidates),
              INITIAL_INSTRUCTIONS]
    return _record("initial", candidates, blocks, split)


def build_no_proof_user_prompt(view, candidates, tried):
    split = split_case_text(view)
    blocks = [render_case(split), NO_PROOF_NOTE, render_tried(tried),
              render_lists(candidates), SECOND_INSTRUCTIONS]
    return _record("no_proof", candidates, blocks, split)


def build_alternative_user_prompt(view, candidates, cited, unused):
    split = split_case_text(view)
    blocks = [render_case(split), ALTERNATIVE_NOTE,
              render_proof_used(cited, unused), render_lists(candidates),
              SECOND_INSTRUCTIONS]
    return _record("alternative", candidates, blocks, split)


def check_fixed_inputs():
    """The approved prompt must be present and unmodified in shape."""
    text = system_prompt()
    for want in ("MAIN ATOMS", "HELPER ATOMS", "MEANING:", "RULE:", "NO_RULE"):
        if want not in text:
            raise P51.PromptError("the approved system prompt lacks %r" % want)
    return {"system_prompt_name": SYSTEM_PROMPT_NAME,
            "system_prompt_sha256": system_prompt_sha256(),
            "chars": len(text)}
