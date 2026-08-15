"""The v6 signed-conclusion experiment: a new system prompt, the same messages.

The only thing this version changes is which system prompt the three generation
calls carry.  The case-specific user message is built by `unifier_prompt_v5_9`
itself, called here, so the initial, no-proof and alternative messages are
byte-identical to v5.9's for the same case and the same call — one positive
display row per atom, no positive/negative duplicate row, no new field and no
new instruction.  A complete request differs from v5.9's only in the system
prompt's name, hash and text.

The approved prompt is `unifier_rules_v6_signed_system.txt` and is used
byte-for-byte for all three calls.
"""

import hashlib
import os

import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_9 as PR59

VERSION = "unifier_prompt_v6_signed/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_rules_v6_signed_system"

BASE_SYSTEM_PROMPT_NAME = PR59.SYSTEM_PROMPT_NAME

MAIN = PR59.MAIN
HELPER = PR59.HELPER
MAIN_PREFIX, HELPER_PREFIX = PR59.MAIN_PREFIX, PR59.HELPER_PREFIX
MAX_USER_MESSAGE_CHARS = PR59.MAX_USER_MESSAGE_CHARS
MAIN_CAP, SECONDARY_CAP = PR59.MAIN_CAP, PR59.SECONDARY_CAP

# the inventory, the atom lists and the message bodies are v5.9's, by reference
complete_inventory = PR59.complete_inventory
build_candidates = PR59.build_candidates
split_case_text = PR59.split_case_text
question_preflight = PR59.question_preflight
printed_atom = PR59.printed_atom
vocabulary_rows = PR59.vocabulary_rows
relabel = PR59.relabel
render_lists = PR59.render_lists
render_case = PR59.render_case
render_tried = PR59.render_tried
render_proof_used = PR59.render_proof_used

INITIAL_INSTRUCTIONS = PR59.INITIAL_INSTRUCTIONS
SECOND_INSTRUCTIONS = PR59.SECOND_INSTRUCTIONS
NO_PROOF_NOTE = PR59.NO_PROOF_NOTE
ALTERNATIVE_NOTE = PR59.ALTERNATIVE_NOTE


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


def _restamp(got):
    """The v5.9 message record, re-headed for this version.

    `text` and `sha256` are not touched: the user message is v5.9's own bytes.
    """
    got["version"] = VERSION
    got["user_message_builder"] = PR59.VERSION
    got["system_prompt_name"] = SYSTEM_PROMPT_NAME
    got["system_prompt_sha256"] = system_prompt_sha256()
    return got


def build_initial_user_prompt(view, candidates):
    return _restamp(PR59.build_initial_user_prompt(view, candidates))


def build_no_proof_user_prompt(view, candidates, tried):
    return _restamp(PR59.build_no_proof_user_prompt(view, candidates, tried))


def build_alternative_user_prompt(view, candidates, cited, unused):
    return _restamp(PR59.build_alternative_user_prompt(view, candidates, cited,
                                                       unused))


def check_fixed_inputs():
    """The approved signed prompt must be present and unmodified in shape."""
    text = system_prompt()
    for want in ("MAIN ATOMS", "HELPER ATOMS", "MEANING:", "RULE:", "NO_RULE",
                 "NOT CONCLUSION",
                 'RULE: ["isa","bee","?X"] -> NOT ["isa","vertebrate","?X"]'):
        if want not in text:
            raise P51.PromptError("the approved signed system prompt lacks %r"
                                  % want)
    return {"system_prompt_name": SYSTEM_PROMPT_NAME,
            "system_prompt_sha256": system_prompt_sha256(),
            "chars": len(text)}
