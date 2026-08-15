"""v6.1: the English meaning and the formal conclusion must agree in polarity.

Everything about the v6 signed contract stays: the two-line `MEANING`/`RULE`
block, the signed conclusion, the positive premises, the displayed vocabulary,
the range restriction, the candidate matching and every existing refusal.

One check is added, after parsing and before compilation.  Only the
**consequence** of the `MEANING` line is inspected — the text after `then` when
that marker is present — and only for an explicit negation.  If the consequence
says the conclusion does not hold while the formula concludes that it does, the
rule is refused.

The prose is never used to build or repair a formula: a negative meaning does
not silently become `-> NOT`.  The model must write `NOT`, or correct its
English.
"""

import re

import simple_rule_parser_v6_signed as P6

VERSION = "simple_rule_parser_v6_1/1.0"

REASON_POLARITY = "meaning_formula_polarity_mismatch"
CATEGORY_POLARITY = REASON_POLARITY

POLARITY_MESSAGE = (
    "The English meaning states a negative consequence, but the formal "
    "conclusion is positive. Write `-> NOT [...]`, or correct the English "
    "meaning if the consequence is meant to be positive.")

# the explicit negations the plan names, and nothing else
NEGATION = re.compile(
    r"\b(?:not|never|cannot|can't|does\s+not|do\s+not|is\s+not|are\s+not|"
    r"will\s+not|doesn't|don't|isn't|aren't|won't)\b", re.I)

_THEN = re.compile(r"\bthen\b", re.I)

# everything else is v6's, by reference
MAX_BASE_RULES_PER_CALL = P6.MAX_BASE_RULES_PER_CALL
MAX_BODY_LITERALS = P6.MAX_BODY_LITERALS
NO_RULE = P6.NO_RULE
GROUND_SPECIALIZATION = P6.GROUND_SPECIALIZATION
LLM_GENERAL = P6.LLM_GENERAL
REASON_CONTRADICTS = P6.REASON_CONTRADICTS
REASON_HELPER_ONLY = P6.REASON_HELPER_ONLY
CATEGORY_NEGATIVE_PREMISE = P6.CATEGORY_NEGATIVE_PREMISE
CATEGORY_DOUBLE_NEGATION = P6.CATEGORY_DOUBLE_NEGATION
vocabulary = P6.vocabulary
canonical = P6.canonical
printed_rule = P6.printed_rule
to_rule = P6.to_rule
split_blocks = P6.split_blocks
head_is_negative = P6.head_is_negative
signed_counts = P6.signed_counts
parse_rule_lines = P6.parse_rule_lines
rule_candidates = P6.rule_candidates


def consequence_of(meaning):
    """The part of the meaning that states what follows.

    `then` splits an `If ..., then ...` sentence; without it the whole line is
    the consequence, which is the conservative reading for this check.
    """
    text = meaning or ""
    parts = _THEN.split(text, maxsplit=1)
    return parts[1] if len(parts) > 1 else text


def says_negative(meaning):
    """Does the consequence explicitly deny its conclusion?"""
    return bool(NEGATION.search(consequence_of(meaning)))


_PAREN = re.compile(r"\([^)]*\)")


def negation_only_in_an_aside(meaning):
    """Is the only negation inside a parenthetical remark?

    The plan says to inspect the consequence, and a parenthetical justification
    sits inside it, so such a rule is refused like any other.  The fact is
    recorded per refusal, because it is the one class of refusal that may be a
    false positive and the count has to be visible.
    """
    tail = consequence_of(meaning)
    return bool(NEGATION.search(tail)) and not NEGATION.search(
        _PAREN.sub("", tail))


def polarity_mismatch(entry):
    """True when the English consequence is negative and the formula is not."""
    if head_is_negative(entry):
        return False
    return says_negative(entry.get("meaning"))


def parse_response(text, vocab, main_ids, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
    """The v6 signed parse, with polarity-mismatched rules refused by name."""
    got = P6.parse_response(text, vocab, main_ids, source_rules,
                            max_rules=max_rules, start_index=start_index,
                            existing=existing, tried=tried)
    kept, refused = [], []
    dropped_parents = set()
    for entry in got["accepted"]:
        if entry.get("origin") == GROUND_SPECIALIZATION:
            continue
        if polarity_mismatch(entry):
            dropped_parents.add(entry["rule_id"])
            refused.append({"line": (entry.get("lines") or [""])[0],
                            "printed": entry["printed"],
                            "meaning": entry.get("meaning", ""),
                            "reasons": [REASON_POLARITY],
                            "message": POLARITY_MESSAGE,
                            "category": CATEGORY_POLARITY,
                            "negation_only_in_an_aside":
                                negation_only_in_an_aside(
                                    entry.get("meaning"))})
            continue
        kept.append(entry)
    for entry in got["accepted"]:
        if entry.get("origin") != GROUND_SPECIALIZATION:
            continue
        if entry.get("specialization_of") in dropped_parents:
            refused.append({"line": (entry.get("lines") or [""])[0],
                            "printed": entry["printed"],
                            "meaning": entry.get("meaning", ""),
                            "reasons": [REASON_POLARITY],
                            "message": POLARITY_MESSAGE,
                            "category": CATEGORY_POLARITY,
                            "variant_of": entry.get("specialization_of")})
            continue
        kept.append(entry)
    kept.sort(key=lambda r: int(str(r["rule_id"])[1:] or 0))
    got["accepted"] = kept
    got["rejected"] = list(got["rejected"]) + refused
    got["polarity_refusals"] = refused
    got["rejections_by_category"] = P6.P53._counts(got["rejected"])
    got["rejection_reasons"] = sorted(set(
        r for x in got["rejected"] for r in (x.get("reasons") or [])))[:20]
    got["base_rules_accepted"] = sum(
        1 for r in kept if r.get("origin") != GROUND_SPECIALIZATION)
    got["generated_specializations_accepted"] = len(kept) - got[
        "base_rules_accepted"]
    got["signed_counts"] = signed_counts(kept)
    got["negative_conclusions"] = [r["rule_id"] for r in kept
                                   if head_is_negative(r)]
    got["meanings"] = dict((r["rule_id"], r.get("meaning", "")) for r in kept)
    got["version"] = VERSION
    return got
