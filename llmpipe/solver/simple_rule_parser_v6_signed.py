"""The v5.9 two-line contract with one addition: the conclusion may be negated.

    MEANING: If something is a bee, then it is normally not a vertebrate.
    RULE: ["isa","bee","?X"] -> NOT ["isa","vertebrate","?X"]

`simple_rule_parser.parse_line` has always read `NOT` into a literal sign; the
v5.3 parser then refused any line carrying one, because writing opposition rules
was a different task.  Here that refusal is narrowed to the premises: a negative
premise, `NOT NOT`, a second conclusion and a conjunction after the arrow are
still refused by name, and the conclusion alone may be signed.

Nothing about the atom inventory changes.  The displayed atoms stay positive and
the negative conclusion must be one of them, matched unsigned under the same
exact/allowed-generalisation rules as a positive conclusion; the sign is an
operation on that displayed atom, recorded beside the matched candidate.  Every
mechanical check of v5.3 and v5.9 still runs, and the sign is part of the
canonical form, so

    A -> B
    A -> NOT B

are two different rules for deduplication, for the tried-rule check and for
source-rule redundancy.

Historical parsers are untouched: `simple_rule_parser_v5_3.parse_response` still
refuses every negative line, and `simple_rule_parser_v5_9` still calls it.
"""

import re

import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import simple_rule_parser_v5_1 as P51
import simple_rule_parser_v5_3 as P53
import simple_rule_parser_v5_9 as P59
import unifier_abstraction as UA
import unifier_prompt_v5_1 as PRINT

VERSION = "simple_rule_parser_v6_signed/1.0"

MAX_BASE_RULES_PER_CALL = P53.MAX_BASE_RULES_PER_CALL
MAX_BODY_LITERALS = P53.MAX_BODY_LITERALS
NO_RULE = P59.NO_RULE

LLM_GENERAL = P53.LLM_GENERAL
GROUND_SPECIALIZATION = P53.GROUND_SPECIALIZATION
WARN_GENERALIZES = P53.WARN_GENERALIZES

REASON_NEGATIVE_PREMISE = ("a premise may not be negated: write `NOT` only "
                           "immediately before the conclusion")
REASON_DOUBLE_NEGATION = "`NOT NOT` is not a rule"
REASON_HELPER_ONLY = P59.REASON_HELPER_ONLY
REASON_TRIED = P53.REASON_TRIED
REASON_SOURCE_RULE = P53.REASON_SOURCE_RULE
REASON_OVER_CAP = P53.REASON_OVER_CAP
REASON_CONTRADICTS = P51.REASON_CONTRADICTS

CATEGORY_NEGATIVE_PREMISE = "negated_premise"
CATEGORY_DOUBLE_NEGATION = "double_negation"

# the block splitter, the vocabulary, the canonical form, the printer, the
# variable rules and the ground specialiser are v5.9's and v5.3's, by reference
split_blocks = P59.split_blocks
vocabulary = P53.vocabulary
canonical = P53.canonical
printed_rule = P53.printed_rule
to_rule = P53.to_rule
source_rule_keys = P53.source_rule_keys
rule_variables = P53.rule_variables
atom_variables = P53.atom_variables
alpha_equivalent = P53.alpha_equivalent
validate = P53.validate
ground_specializations = P53.ground_specializations
role_fit = P53.role_fit

_DOUBLE_NOT = re.compile(r"\bNOT\s+NOT\b", re.I)


# ------------------------------------------------------- signed atom matching

def _matching_rows(lit, vocab, rule):
    """The displayed rows this literal was copied from, matched UNSIGNED.

    Every displayed row is positive.  A negative conclusion names a displayed
    positive atom and negates it, so the match ignores the sign and the sign is
    reported separately.
    """
    want = lit["atom"]
    exact = [row for row in vocab["atoms"]
             if alpha_equivalent(row["atom"], want)]
    if exact:
        return exact, "alpha_exact"
    loose = [row for row in vocab["atoms"]
             if UA.unify_unsigned_atoms(P3._clause_shape(row["atom"]),
                                        P3._clause_shape(want))["unifiable"]]
    loose.sort(key=lambda r: (len(atom_variables(r["atom"],
                                                 rule_variables(rule))),
                              str(r.get("id"))))
    return loose, "unifier"


def rule_candidates(rule, vocab):
    """-> (matched candidate ids per literal, unmatched atoms, total cost).

    Same as v5.3's, except that a literal matches a displayed row by its atom
    rather than by its atom and sign, and each match records the sign the rule
    wrote.
    """
    matched, unmatched, total = [], [], 0
    for lit in rule["body"] + [rule["head"]]:
        rows, kind = _matching_rows(lit, vocab, rule)
        best = (rows or [None])[0]
        if best is None:
            unmatched.append(PRINT.printed_atom(UA.display_atom(lit["atom"]),
                                                negated=lit["sign"] == "-"))
            continue
        matched.append({"literal": PRINT.printed_atom(
                            UA.display_atom(lit["atom"]),
                            negated=lit["sign"] == "-"),
                        "candidate": best["id"], "role": best["role"],
                        "priority_cost": best["priority_cost"],
                        "match_kind": kind,
                        "sign": lit["sign"],
                        "displayed_sign": best["sign"],
                        "equally_good": [r["id"] for r in rows][:6]})
        total += best["priority_cost"]
    return matched, unmatched, total


def extra_refusals(rule, vocab):
    """v5.1's extra refusals, with the content check matched unsigned."""
    why = []
    content = set(vocab.get("content_ids") or [])
    used = []
    for lit in rule["body"] + [rule["head"]]:
        rows, _kind = _matching_rows(lit, vocab, rule)
        used += [r["id"] for r in rows]
    if content and not (set(used) & content):
        why.append(REASON_HELPER_ONLY)
    head = rule["head"]
    for lit in rule["body"]:
        if lit["sign"] != head["sign"] \
                and alpha_equivalent(lit["atom"], head["atom"]):
            why.append(REASON_CONTRADICTS)
            break
    return why


def head_is_negative(rule):
    return (rule.get("head") or {}).get("sign") == "-"


def signed_counts(rules):
    neg = sum(1 for r in rules if head_is_negative(r))
    return {"rules": len(rules), "positive_conclusion": len(rules) - neg,
            "negative_conclusion": neg}


# -------------------------------------------------------------- the rule loop

def _parse_one_line(line):
    """-> (parsed, refusal).  Signed conclusions pass; signed premises do not."""
    if _DOUBLE_NOT.search(line):
        return None, {"line": line[:220], "reasons": [REASON_DOUBLE_NEGATION],
                      "category": CATEGORY_DOUBLE_NEGATION}
    try:
        parsed = SP.parse_line(line)
    except SP.RuleError as e:
        return None, {"line": line[:220], "reasons": [str(e)],
                      "category": "unreadable"}
    if any(s == "-" for s, _a in parsed["body"]):
        return None, {"line": line[:220], "reasons": [REASON_NEGATIVE_PREMISE],
                      "category": CATEGORY_NEGATIVE_PREMISE}
    return parsed, None


def parse_rule_lines(text, vocab, source_rules=(),
                     max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                     existing=(), tried=()):
    """v5.3's `parse_response` with a signed conclusion allowed.

    Every step is v5.3's own function; only the sign rule, the candidate match
    and the two new refusals differ.
    """
    lines = (text or "").splitlines()
    rule_lines = [l for l in lines if SP.RULE_PREFIX.match(l)]
    source_keys = source_rule_keys(source_rules)
    tried_keys = set(tried or [])
    seen = dict((r["canonical"], r) for r in existing)
    accepted, rejected, over_cap, notes = [], [], [], []
    base_kept = 0
    n = [start_index - 1]

    def fresh_id():
        n[0] += 1
        return "R%d" % n[0]

    for raw in rule_lines:
        line = raw.strip()
        parsed, refusal = _parse_one_line(line)
        if refusal is not None:
            rejected.append(refusal)
            continue
        rule = to_rule(parsed)
        why, warn, got_notes = validate(rule, vocab, source_keys)
        if not why:
            why = extra_refusals(rule, vocab)
        if why:
            rejected.append({"line": line[:220], "reasons": why,
                             "printed": printed_rule(rule),
                             "category": P53._category(why)})
            continue
        key = canonical(rule)
        if key in tried_keys:
            rejected.append({"line": line[:220], "reasons": [REASON_TRIED],
                             "printed": printed_rule(rule),
                             "category": "repeat_of_a_tried_rule"})
            continue
        if key in seen:
            seen[key].setdefault("lines", []).append(line[:220])
            continue
        if base_kept >= max_rules:
            over_cap.append({"line": line[:220],
                             "printed": printed_rule(rule),
                             "why": REASON_OVER_CAP % max_rules})
            continue
        matched, unmatched, cost = rule_candidates(rule, vocab)
        entry = {"rule_id": fresh_id(), "body": rule["body"],
                 "head": rule["head"], "canonical": key,
                 "llm_variables": rule["llm_variables"],
                 "printed": printed_rule(rule), "lines": [line[:220]],
                 "origin": LLM_GENERAL, "warnings": warn,
                 "premises": len(rule["body"]),
                 "head_sign": rule["head"]["sign"],
                 "negative_conclusion": rule["head"]["sign"] == "-",
                 "candidate_matches": matched,
                 "atoms_matching_no_candidate": unmatched,
                 "rule_priority_cost": cost,
                 "role_fit": role_fit(rule, vocab),
                 "generalisation_notes": got_notes,
                 "variants": []}
        seen[key] = entry
        accepted.append(entry)
        notes.extend(got_notes)
        base_kept += 1
        if WARN_GENERALIZES in warn:
            for variant in ground_specializations(rule, vocab):
                if variant["canonical"] in seen:
                    continue
                vmatched, vunmatched, vcost = rule_candidates(variant, vocab)
                child = {"rule_id": fresh_id(), "body": variant["body"],
                         "head": variant["head"],
                         "canonical": variant["canonical"],
                         "llm_variables": variant["llm_variables"],
                         "printed": variant["printed"],
                         "lines": [line[:220]],
                         "origin": GROUND_SPECIALIZATION,
                         "specialization_of": entry["rule_id"],
                         "substitution": variant["substitution"],
                         "grounded_on": variant["grounded_on"],
                         "warnings": [], "premises": len(variant["body"]),
                         "head_sign": variant["head"]["sign"],
                         "negative_conclusion":
                             variant["head"]["sign"] == "-",
                         "candidate_matches": vmatched,
                         "atoms_matching_no_candidate": vunmatched,
                         "rule_priority_cost": vcost,
                         "role_fit": role_fit(variant, vocab),
                         "generalisation_notes": [],
                         "variants": []}
                seen[variant["canonical"]] = child
                entry["variants"].append(child["rule_id"])
                accepted.append(child)
    return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
            "readable_lines": len(rule_lines), "response_lines": len(lines),
            "rejection_reasons": sorted(set(r for x in rejected
                                            for r in x["reasons"]))[:20],
            "rejections_by_category": P53._counts(rejected),
            "base_rules_accepted": base_kept,
            "generated_specializations_accepted": len(accepted) - base_kept,
            "base_rule_limit": max_rules,
            "refused_negative_lines": sum(
                1 for r in rejected
                if r["category"] in (CATEGORY_NEGATIVE_PREMISE,
                                     CATEGORY_DOUBLE_NEGATION)),
            "generalisation_notes": notes,
            "next_index": n[0] + 1, "version": VERSION}


def _uses_a_main_atom(entry, main_ids):
    return P59._uses_a_main_atom(entry, main_ids)


def parse_response(text, vocab, main_ids, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
    """The v5.9 block contract over the signed rule loop."""
    blocks, refusals, said_no_rule = split_blocks(text)
    meaning_of = {}
    for b in blocks:
        meaning_of.setdefault(b["rule_line"][:220], b["meaning"])
    synthetic = "\n".join(b["rule_line"] for b in blocks)
    got = parse_rule_lines(synthetic, vocab, source_rules,
                           max_rules=10 ** 6, start_index=start_index,
                           existing=existing, tried=tried)
    for entry in got["accepted"]:
        entry["meaning"] = meaning_of.get((entry.get("lines") or [""])[0], "")
    for row in got["rejected"]:
        row["meaning"] = meaning_of.get(row.get("line", ""), "")

    kept, dropped, base_kept = [], [], 0
    by_parent = {}
    for entry in got["accepted"]:
        if entry.get("origin") == GROUND_SPECIALIZATION:
            continue
        if not _uses_a_main_atom(entry, main_ids):
            dropped.append({"line": (entry.get("lines") or [""])[0],
                            "printed": entry["printed"],
                            "meaning": entry.get("meaning", ""),
                            "reasons": [REASON_HELPER_ONLY],
                            "category": "helper_only"})
            continue
        if base_kept >= max_rules:
            dropped.append({"line": (entry.get("lines") or [""])[0],
                            "printed": entry["printed"],
                            "meaning": entry.get("meaning", ""),
                            "why": P59.REASON_OVER_CAP % max_rules,
                            "category": "over_cap", "over_cap": True})
            continue
        base_kept += 1
        kept.append(entry)
        by_parent[entry["rule_id"]] = entry
    for entry in got["accepted"]:
        if entry.get("origin") != GROUND_SPECIALIZATION:
            continue
        if entry.get("specialization_of") in by_parent:
            entry["meaning"] = by_parent[entry["specialization_of"]].get(
                "meaning", "")
            kept.append(entry)
    kept.sort(key=lambda r: int(str(r["rule_id"])[1:] or 0))
    over_cap = list(got["over_cap"]) + [d for d in dropped
                                        if d.get("over_cap")]
    rejected = list(got["rejected"]) + refusals + [
        d for d in dropped if not d.get("over_cap")]
    ids = [int(str(r["rule_id"])[1:] or 0) for r in kept]
    return {"accepted": kept, "rejected": rejected, "over_cap": over_cap,
            "blocks": blocks, "format_refusals": refusals,
            "said_no_rule": said_no_rule and not blocks,
            "readable_blocks": len(blocks),
            "readable_lines": len(blocks),
            "response_lines": len((text or "").splitlines()),
            "rejection_reasons": sorted(set(
                r for x in rejected for r in (x.get("reasons") or [])))[:20],
            "rejections_by_category": P53._counts(rejected),
            "base_rules_accepted": base_kept,
            "generated_specializations_accepted": len(kept) - base_kept,
            "base_rule_limit": max_rules,
            "refused_negative_lines": got["refused_negative_lines"],
            "generalisation_notes": got["generalisation_notes"],
            "meanings": dict((r["rule_id"], r.get("meaning", ""))
                             for r in kept),
            "signed_counts": signed_counts(kept),
            "negative_conclusions": [r["rule_id"] for r in kept
                                     if head_is_negative(r)],
            "next_index": (max(ids) + 1) if ids else got["next_index"],
            "version": VERSION}
