"""The positive-rule output contract, as an adapter over the v4 parser (WP5).

Nothing in `simple_rule_parser`, `_v3` or `_v4` is changed: the grammar, the
validator, the nested-term rule, the signed grounding evidence, the recorded
object-constant generalisation and the twelve-rule cap are theirs, imported and
called.  This module adds only what the clear positive prompt promises:

  * the vocabulary is built from the DISPLAYED positive candidates, one atom per
    line, with the section each came from;
  * a line containing explicit semantic `NOT` is refused by name before the v4
    parser sees it.  The prompt says opposition rules are a separate task, so a
    negative rule is not a mechanical error to be repaired but a rule this task
    does not collect;
  * a rule must use at least one atom from a content section: a rule made only
    of event-role helpers connects nothing;
  * a conclusion that negates one of its premises is refused (the v3 validator
    already refuses a conclusion that repeats one).

Every refusal carries its own reason string, and the reasons are constants so a
caller can count them.
"""

import json

import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import simple_rule_parser_v4 as P4
import unifier_abstraction as UA
import unifier_prompt_v5_1 as P51

VERSION = "simple_rule_parser_v5_1/1.0"

MAX_BODY_LITERALS = P3.MAX_BODY_LITERALS
MAX_RULES_PER_CALL = P3.MAX_RULES_PER_CALL
WARN_GENERALIZES = P3.WARN_GENERALIZES

REASON_NEGATIVE = ("explicit semantic NOT is outside this task: write ordinary "
                   "positive implication rules only")
REASON_HELPER_ONLY = ("every rule must use at least one atom from a content "
                      "section; helper atoms alone connect nothing")
REASON_CONTRADICTS = "the conclusion negates one of its own premises"

alpha_equivalent = P3.alpha_equivalent
validate = P3.validate
role_fit = P3.role_fit
ground_specializations = P4.ground_specializations


def vocabulary(candidates):
    """The v4 vocabulary over the displayed positive atoms, plus sections."""
    rows = []
    for g in candidates["groups"]:
        rows.append({"id": g["id"], "surface_atom": g["atom"], "sign": "+",
                     "role": g["internal_role"], "priority_cost": g["cost"],
                     "section": g["section"], "printed": g["printed"],
                     "same_sign_source_kinds": g["same_sign_source_kinds"]})
    vocab = P4.vocabulary(rows)
    vocab["sections"] = dict((r["id"], r["section"]) for r in rows)
    vocab["content_ids"] = sorted(r["id"] for r in rows
                                  if r["section"] != P51.HELPER_SECTION)
    vocab["policy"] = ("the vocabulary is exactly the atoms the message "
                       "displayed, all positive; a displayed object constant "
                       "may be generalised to a variable, which is recorded as "
                       "a warning")
    return vocab


def _matching_rows(lit, vocab):
    """The displayed rows a rule literal may have been copied from."""
    want = lit["atom"]
    exact = [r for r in vocab["atoms"]
             if r["sign"] == lit["sign"] and alpha_equivalent(r["atom"], want)]
    if exact:
        return exact
    return [r for r in vocab["atoms"]
            if r["sign"] == lit["sign"]
            and UA.unify_unsigned_atoms(P3._clause_shape(r["atom"]),
                                        P3._clause_shape(want))["unifiable"]]


def extra_refusals(rule, vocab):
    """-> the refusals this prompt version adds to the v3 validator."""
    why = []
    content = set(vocab.get("content_ids") or [])
    used = []
    for lit in rule["body"] + [rule["head"]]:
        used += [r["id"] for r in _matching_rows(lit, vocab)]
    if content and not (set(used) & content):
        why.append(REASON_HELPER_ONLY)
    head = rule["head"]
    for lit in rule["body"]:
        if lit["sign"] != head["sign"] \
                and alpha_equivalent(lit["atom"], head["atom"]):
            why.append(REASON_CONTRADICTS)
            break
    return why


def split_negative_lines(text):
    """-> (the lines the v4 parser may see, the refused negative lines)."""
    keep, refused = [], []
    for raw in (text or "").splitlines():
        if not SP.RULE_PREFIX.match(raw):
            keep.append(raw)
            continue
        line = raw.strip()
        try:
            parsed = SP.parse_line(line)
        except SP.RuleError:
            keep.append(raw)                # v4 reports the syntax error
            continue
        signs = [s for s, _a in parsed["body"] + [parsed["head"]]]
        if "-" in signs:
            refused.append({"line": line[:220], "reasons": [REASON_NEGATIVE],
                            "printed": _printed(parsed)})
            continue
        keep.append(raw)
    return "\n".join(keep), refused


def _printed(parsed):
    try:
        return P51.printed_rule(SP.to_stage2_variables(parsed))
    except Exception:                                       # pragma: no cover
        return json.dumps(parsed)[:200]


def parse_response(text, vocab, source_rules=(), max_rules=MAX_RULES_PER_CALL,
                   start_index=1, existing=()):
    """The v4 parse, restricted to the positive contract of this prompt."""
    kept_text, negative = split_negative_lines(text)
    got = P4.parse_response(kept_text, vocab, source_rules, max_rules=max_rules,
                            start_index=start_index, existing=existing)
    accepted, dropped = [], []
    for r in got["accepted"]:
        if r.get("specialization_of") and r["specialization_of"] in dropped:
            dropped.append(r["rule_id"])
            continue
        why = extra_refusals(r, vocab)
        if why:
            dropped.append(r["rule_id"])
            got["rejected"].append({"line": (r.get("lines") or [""])[0],
                                    "reasons": why, "printed": r["printed"]})
            continue
        accepted.append(r)
    got["accepted"] = accepted
    got["rejected"] = negative + got["rejected"]
    got["rejection_reasons"] = sorted(set(x for r in got["rejected"]
                                          for x in r["reasons"]))[:20]
    got["refused_negative_lines"] = len(negative)
    got["version"] = VERSION
    return got
