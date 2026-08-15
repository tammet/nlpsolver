"""The twelve-rule limit, meaning what it says (WP1).

`simple_rule_parser_v5_1` calls the v4 parser first and applies its own refusals
afterwards, so a line the v5.1 checks reject can still occupy one of the twelve
slots, and a valid rule further down the reply is put in `over_cap` and never
recovered.  The same inherited code counts program-generated ground
specializations in the same allowance, so a rule the model never wrote can push
out one it did.

Here the limit means **twelve valid, distinct, model-written base rules after
every check**:

  * the v4 parser runs with no cap, so nothing is refused for position alone;
  * explicit-negative, malformed, invented-vocabulary, helper-only,
    self-repeating, self-contradictory and range-unsafe lines are removed and
    do not consume a slot;
  * a duplicate does not consume a slot: the v4 parser already keeps one entry
    per canonical rule;
  * generated specializations do not consume a base slot.  They stay bounded by
    `MAX_GROUND_SPECIALIZATIONS` per base rule and keep their
    `specialization_of` provenance;
  * retained rules are renumbered from `start_index` with no gaps, and every
    `specialization_of` and `variants` reference is renumbered with them;
  * the thirteenth valid base rule, and its variants, are recorded in
    `over_cap` by name.

Nothing in `simple_rule_parser`, `_v3`, `_v4` or `_v5_1` is modified.
"""

import simple_rule_parser_v3 as P3
import simple_rule_parser_v4 as P4
import simple_rule_parser_v5_1 as P51

VERSION = "simple_rule_parser_v5_2/1.0"

MAX_BASE_RULES_PER_CALL = 12
MAX_GROUND_SPECIALIZATIONS = P3.MAX_GROUND_SPECIALIZATIONS
MAX_BODY_LITERALS = P3.MAX_BODY_LITERALS
WARN_GENERALIZES = P3.WARN_GENERALIZES

LLM_GENERAL = P3.LLM_GENERAL
GROUND_SPECIALIZATION = P3.GROUND_SPECIALIZATION

REASON_NEGATIVE = P51.REASON_NEGATIVE
REASON_HELPER_ONLY = P51.REASON_HELPER_ONLY
REASON_CONTRADICTS = P51.REASON_CONTRADICTS
REASON_OVER_CAP = ("beyond the %d valid model-written rules this call may "
                   "contribute")

vocabulary = P51.vocabulary
extra_refusals = P51.extra_refusals
split_negative_lines = P51.split_negative_lines

# The v4 parser's own cap is not the limit here; it is turned off and the limit
# is applied to what survives.
_UNBOUNDED = 10 ** 6


def _renumber(rules, start_index):
    """Consecutive ids from `start_index`, with every reference rewritten."""
    mapping = {}
    for i, r in enumerate(rules):
        mapping[r["rule_id"]] = "R%d" % (start_index + i)
    for r in rules:
        r["rule_id"] = mapping[r["rule_id"]]
        if r.get("specialization_of"):
            r["specialization_of"] = mapping.get(r["specialization_of"],
                                                 r["specialization_of"])
        if r.get("variants"):
            r["variants"] = [mapping.get(v, v) for v in r["variants"]]
    return rules


def parse_response(text, vocab, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=()):
    """-> the v5.1 parse whose cap counts only valid model-written base rules."""
    kept_text, negative = split_negative_lines(text)
    got = P4.parse_response(kept_text, vocab, source_rules,
                            max_rules=_UNBOUNDED, start_index=start_index,
                            existing=existing)
    variants_of = {}
    for r in got["accepted"]:
        if r.get("specialization_of"):
            variants_of.setdefault(r["specialization_of"], []).append(r)

    kept, over_cap, refused = [], [], []
    base_kept = 0
    for r in got["accepted"]:
        if r.get("specialization_of"):
            continue                        # taken with its base rule, below
        mine = variants_of.get(r["rule_id"], [])
        why = extra_refusals(r, vocab)
        if why:
            refused.append({"line": (r.get("lines") or [""])[0],
                            "reasons": why, "printed": r["printed"]})
            continue
        if base_kept >= max_rules:
            over_cap.append({"line": (r.get("lines") or [""])[0],
                             "printed": r["printed"],
                             "why": REASON_OVER_CAP % max_rules})
            for v in mine:
                over_cap.append({"line": (v.get("lines") or [""])[0],
                                 "printed": v["printed"],
                                 "why": "a generated specialization of a rule "
                                        "beyond that limit"})
            continue
        base_kept += 1
        kept.append(r)
        kept.extend(mine)

    _renumber(kept, start_index)
    got["accepted"] = kept
    got["rejected"] = negative + got["rejected"] + refused
    got["over_cap"] = got["over_cap"] + over_cap
    got["rejection_reasons"] = sorted(set(x for r in got["rejected"]
                                          for x in r["reasons"]))[:20]
    got["refused_negative_lines"] = len(negative)
    got["base_rules_accepted"] = base_kept
    got["generated_specializations_accepted"] = len(kept) - base_kept
    got["base_rule_limit"] = max_rules
    got["next_index"] = start_index + len(kept)
    got["version"] = VERSION
    got["cap_policy"] = ("the limit counts valid, distinct, model-written base "
                         "rules only; refused lines and generated "
                         "specializations do not consume it")
    return got
