"""Reading a compiled bridge by provenance instead of by clause sign.

`unifier_feedback_v5_3.body_and_head` takes a bridge clause's negative literals
for its premises and its positive literal for its conclusion.  That holds for a
positive rule and fails for a signed one: the clause of

    ["isa","bee","?X"] -> NOT ["isa","vertebrate","?X"]

is `[-isa(bee,X), -isa(vertebrate,X)]`, so the sign split would call both
literals premises and find no conclusion — the rule would look unstartable and
its conclusion would be treated as another thing to supply.

The signed compiler records which compiled literal came from the parsed head and
which came from each premise.  This module reads that record, and falls back to
the v5.3 sign split only for a hypothesis compiled before the record existed.

The ordering policy is not changed: `order_by_chain` is v5.4's, imported.
"""

import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB53
import unifier_feedback_v5_4 as FB54

VERSION = "unifier_feedback_v6_signed/1.0"

STARTABLE_NOW = FB54.STARTABLE_NOW
STARTABLE_AFTER = FB54.STARTABLE_AFTER
NOT_STARTABLE = FB54.NOT_STARTABLE
MAX_ROUNDS = FB54.MAX_ROUNDS

categorise = FB54.categorise
supplier_inventory = FB54.supplier_inventory
match_body = FB54.match_body
printed_literal = FB54.printed_literal
bridge_literals = FB53.bridge_literals
order_by_chain = FB54.order_by_chain
report = FB54.report
_head_suppliers = FB54._head_suppliers


def has_provenance(hypothesis):
    return hypothesis.get("head_literal") is not None


def body_and_head(hypothesis):
    """-> (the premise literals, the conclusion literals) of a bridge clause.

    From the compiler's own record when it is there, and from the v5.3 sign
    split when it is not.
    """
    if has_provenance(hypothesis):
        return (list(hypothesis.get("body_literals") or []),
                [hypothesis["head_literal"]])
    return FB53.body_and_head(hypothesis)


def chain_status(view, hypotheses, extra_hypotheses=()):
    """v5.4's bounded fixpoint, reading each bridge through `body_and_head`."""
    suppliers = categorise(supplier_inventory(view))
    pool = list(suppliers)
    pending = {}
    for h in list(hypotheses) + list(extra_hypotheses):
        body, head = body_and_head(h)
        pending[h["rule_id"]] = {"h": h, "body": body, "head": head,
                                 "asked": h in hypotheses}
    status = {}
    truncated = False
    for round_index in range(MAX_ROUNDS):
        added, changed = [], False
        for rid, row in pending.items():
            if rid in status:
                continue
            got = match_body(row["body"], pool)
            truncated = truncated or got["truncated"]
            if not got["may_start"]:
                continue
            used_rules = []
            if got["assignments"]:
                used_rules = sorted(set(
                    s["from_rule"] for s in got["assignments"][0]
                    if s.get("from_rule")))
            status[rid] = {
                "status": STARTABLE_NOW if round_index == 0 and not used_rules
                else STARTABLE_AFTER if used_rules else STARTABLE_NOW,
                "after": used_rules,
                "premises": [{"premise": printed_literal(UA.unsigned_atom(l)),
                              "supplier": s["printed"],
                              "category": s["category"],
                              "clause": s["clause_name"]}
                             for l, s in zip(row["body"],
                                             got["assignments"][0])]
                if got["assignments"] else [],
                "unmatched": [printed_literal(UA.unsigned_atom(l))
                              for l in got["unmatched"]],
                "negative_conclusion": bool(
                    row["h"].get("negative_conclusion")),
                "read_from": ("the compiler's head provenance"
                              if has_provenance(row["h"])
                              else "the clause sign split"),
                "round": round_index + 1}
            added.extend(_head_suppliers(row["h"], row["head"]))
            changed = True
        pool = pool + added
        if not changed:
            break
    for rid, row in pending.items():
        if rid in status:
            continue
        got = match_body(row["body"], pool)
        status[rid] = {"status": NOT_STARTABLE, "after": [],
                       "premises": [],
                       "unmatched": [printed_literal(UA.unsigned_atom(l))
                                     for l in got["unmatched"]],
                       "negative_conclusion": bool(
                           row["h"].get("negative_conclusion")),
                       "read_from": ("the compiler's head provenance"
                                     if has_provenance(row["h"])
                                     else "the clause sign split"),
                       "why": got.get("why"), "round": None}
    return {"status": dict((k, v) for k, v in status.items()
                           if pending[k]["asked"]),
            "all_status": status,
            "search_bound_reached": truncated,
            "rounds_allowed": MAX_ROUNDS,
            "version": VERSION}
