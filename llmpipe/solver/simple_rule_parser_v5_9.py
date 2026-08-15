"""The two-line proposal format: one MEANING, one RULE, or the word NO_RULE.

The v5.4 contract accepted any `RULE:` line anywhere in a reply.  The audit of
the widened run found responses whose prose said a rule was too strong and whose
`RULE:` line emitted it anyway — the warning was discarded and the bad rule was
kept.  Here a rule exists only inside a block:

    MEANING: <one nonempty line>
    RULE: <one to three premises joined by AND> -> <one conclusion>

A bare `RULE:` is refused, a `MEANING:` with no rule is refused, and only the
`RULE:` line is ever compiled.  The English meaning is never used to infer or
repair a formula; it is stored beside the rule for a later audit.

Everything after the block split is v5.3's parser, unchanged: the displayed
vocabulary, aliases, variable scope, range restriction, constants, nested
forms, signs, duplicates, writability and per-rule conversion.  Two rules are
added on top: a rule must use at least one MAIN atom, and the twelve-rule limit
counts only distinct, mechanically valid, model-written base rules.
"""

import re

import simple_rule_parser_v5_3 as P53

VERSION = "simple_rule_parser_v5_9/1.0"

MAX_BASE_RULES_PER_CALL = P53.MAX_BASE_RULES_PER_CALL
MAX_BODY_LITERALS = P53.MAX_BODY_LITERALS
NO_RULE = "NO_RULE"

REASON_BARE_RULE = "a RULE line without the MEANING line above it"
REASON_LONE_MEANING = "a MEANING line with no RULE line after it"
REASON_EMPTY_MEANING = "an empty MEANING line"
REASON_HELPER_ONLY = "every atom of the rule is a helper atom"
REASON_OVER_CAP = "beyond the %d valid model-written rules this call may add"

_MEANING = re.compile(r"^\s*MEANING\s*:\s*(.*)$", re.I)
_RULE = re.compile(r"^\s*RULE\s*:\s*(.*)$", re.I)
_NO_RULE = re.compile(r"^\s*NO_RULE\s*$", re.I)

vocabulary = P53.vocabulary
canonical = P53.canonical
printed_rule = P53.printed_rule
to_rule = P53.to_rule
source_rule_keys = P53.source_rule_keys


def split_blocks(text):
    """-> (blocks, refusals, said_no_rule).  Order is the reply's own order."""
    blocks, refusals = [], []
    pending = None
    said_no_rule = False
    for raw in (text or "").splitlines():
        if _NO_RULE.match(raw):
            said_no_rule = True
            continue
        m = _MEANING.match(raw)
        if m:
            if pending is not None:
                refusals.append({"line": pending["raw"][:220],
                                 "reasons": [REASON_LONE_MEANING],
                                 "category": "meaning_without_rule"})
            meaning = m.group(1).strip()
            pending = {"meaning": meaning, "raw": raw.strip()}
            if not meaning:
                refusals.append({"line": raw.strip()[:220],
                                 "reasons": [REASON_EMPTY_MEANING],
                                 "category": "empty_meaning"})
                pending = None
            continue
        r = _RULE.match(raw)
        if r:
            if pending is None:
                refusals.append({"line": raw.strip()[:220],
                                 "reasons": [REASON_BARE_RULE],
                                 "category": "rule_without_meaning"})
                continue
            blocks.append({"meaning": pending["meaning"],
                           "rule_line": raw.strip(),
                           "rule_text": r.group(1).strip()})
            pending = None
            continue
    if pending is not None:
        refusals.append({"line": pending["raw"][:220],
                         "reasons": [REASON_LONE_MEANING],
                         "category": "meaning_without_rule"})
    return blocks, refusals, said_no_rule


def _uses_a_main_atom(entry, main_ids):
    for got in entry.get("candidate_matches") or []:
        if got.get("candidate") in main_ids:
            return True
        for other in got.get("equally_good") or []:
            if other in main_ids:
                return True
    return False


def parse_response(text, vocab, main_ids, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
    """-> the v5.3 parse of the block rules, plus this format's own refusals."""
    blocks, refusals, said_no_rule = split_blocks(text)
    meaning_of = {}
    for b in blocks:
        meaning_of.setdefault(b["rule_line"][:220], b["meaning"])
    synthetic = "\n".join(b["rule_line"] for b in blocks)
    got = P53.parse_response(synthetic, vocab, source_rules,
                             max_rules=10 ** 6, start_index=start_index,
                             existing=existing, tried=tried)
    for entry in got["accepted"]:
        entry["meaning"] = meaning_of.get((entry.get("lines") or [""])[0], "")
    for row in got["rejected"]:
        row["meaning"] = meaning_of.get(row.get("line", ""), "")

    kept, dropped, base_kept = [], [], 0
    by_parent = {}
    for entry in got["accepted"]:
        if entry.get("origin") == P53.GROUND_SPECIALIZATION:
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
                            "why": REASON_OVER_CAP % max_rules,
                            "category": "over_cap", "over_cap": True})
            continue
        base_kept += 1
        kept.append(entry)
        by_parent[entry["rule_id"]] = entry
    for entry in got["accepted"]:
        if entry.get("origin") != P53.GROUND_SPECIALIZATION:
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
            "next_index": (max(ids) + 1) if ids else got["next_index"],
            "version": VERSION}
