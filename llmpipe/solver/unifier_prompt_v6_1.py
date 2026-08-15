"""v6.1: the signed system prompt plus the polarity section, nothing else.

`unifier_rules_v6_1_signed_system.txt` is `unifier_rules_v6_signed_system.txt`
with one section inserted before `OUTPUT`, so the output contract still comes
last and every other byte of the v6 prompt is unchanged.  A test pins that.

The case-specific user message is still built by `unifier_prompt_v5_9`, through
`unifier_prompt_v6_signed`, so an initial, no-proof or alternative message is
byte-identical to v5.9's and v6's for the same case and call.
"""

import hashlib
import os

import unifier_prompt_v5_1 as P51
import unifier_prompt_v6_signed as PR6

VERSION = "unifier_prompt_v6_1/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_rules_v6_1_signed_system"
BASE_SYSTEM_PROMPT_NAME = PR6.SYSTEM_PROMPT_NAME

POLARITY_HEADING = "POLARITY MUST MATCH"

MAIN, HELPER = PR6.MAIN, PR6.HELPER
MAX_USER_MESSAGE_CHARS = PR6.MAX_USER_MESSAGE_CHARS

complete_inventory = PR6.complete_inventory
build_candidates = PR6.build_candidates
split_case_text = PR6.split_case_text
question_preflight = PR6.question_preflight
printed_atom = PR6.printed_atom
vocabulary_rows = PR6.vocabulary_rows
relabel = PR6.relabel
render_lists = PR6.render_lists
render_case = PR6.render_case


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def base_system_prompt():
    with open(os.path.join(PROMPT_DIR,
                           "%s.txt" % BASE_SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


def _restamp(got):
    got["version"] = VERSION
    got["user_message_builder"] = PR6.PR59.VERSION
    got["system_prompt_name"] = SYSTEM_PROMPT_NAME
    got["system_prompt_sha256"] = system_prompt_sha256()
    return got


def build_initial_user_prompt(view, candidates):
    return _restamp(PR6.build_initial_user_prompt(view, candidates))


def build_no_proof_user_prompt(view, candidates, tried):
    return _restamp(PR6.build_no_proof_user_prompt(view, candidates, tried))


def build_alternative_user_prompt(view, candidates, cited, unused):
    return _restamp(PR6.build_alternative_user_prompt(view, candidates, cited,
                                                      unused))


def only_the_polarity_section_differs():
    """-> True when the prompt is v6's with exactly one section inserted."""
    mine, base = system_prompt(), base_system_prompt()
    if POLARITY_HEADING not in mine or POLARITY_HEADING in base:
        return False
    start = mine.index(POLARITY_HEADING)
    end = mine.index("OUTPUT\n\nFor each proposed rule")
    return mine[:start] + mine[end:] == base


def check_fixed_inputs():
    text = system_prompt()
    for want in ("MAIN ATOMS", "HELPER ATOMS", "MEANING:", "RULE:", "NO_RULE",
                 POLARITY_HEADING,
                 'RULE: ["isa","person","?X"] -> NOT ["isa","elephant","?X"]'):
        if want not in text:
            raise P51.PromptError("the v6.1 system prompt lacks %r" % want)
    if not only_the_polarity_section_differs():
        raise P51.PromptError("the v6.1 prompt differs from v6 by more than "
                              "the polarity section")
    return {"system_prompt_name": SYSTEM_PROMPT_NAME,
            "system_prompt_sha256": system_prompt_sha256(),
            "chars": len(text)}
