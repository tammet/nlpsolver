"""The no-proof report, without a target to copy (WP5, WP6).

The v5.3 report ended by naming the exact question literal no rule had reached
and asking the model to derive one of them.  On `folio-0069` the model did
precisely that: it wrote a rule asserting the named atom, and the grader called
it false.  Three of the run's three FALSE sets came from that call.

This version keeps the half that worked and removes the half that invited target
copying:

  * gone: `QUESTION ATOMS NOT REACHED BY A USABLE RULE`,
    `CONCLUSION CAN CONNECT TO ...`, the annotation saying a conclusion could
    reach an unreached question atom, and the closing instruction to derive one
    of them;
  * kept: whether each first rule's body can start at all, and which premises
    nothing can supply;
  * new: every possible supplier carries ONE honest category -- `PASSAGE`,
    `GENERAL_LOGIC`, `QUESTION_ASSUMPTION`, `EARLIER_PROPOSED_RULE` -- instead
    of all of them being "the existing clauses", and the message says in as many
    words that a question assumption is not a fact of the passage;
  * new: what the model is asked for is a chain that can START, not a conclusion
    that reaches the question.

The supplier inventory, the joint body matching and the unifier are
`unifier_feedback_v5_3`'s, imported unchanged.
"""

import json

import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB53

VERSION = "unifier_feedback_v5_4/1.0"

PASSAGE = "PASSAGE"
GENERAL_LOGIC = "GENERAL_LOGIC"
QUESTION_ASSUMPTION = "QUESTION_ASSUMPTION"
EARLIER_PROPOSED_RULE = "EARLIER_PROPOSED_RULE"

CATEGORIES = (PASSAGE, GENERAL_LOGIC, QUESTION_ASSUMPTION,
              EARLIER_PROPOSED_RULE)

CATEGORY_OF = {FB53.FACT: PASSAGE, FB53.RULE_HEAD: PASSAGE,
               FB53.AXIOM_HEAD: GENERAL_LOGIC,
               FB53.QUESTION_ASSUMPTION: QUESTION_ASSUMPTION,
               FB53.ATTEMPTED_HEAD: EARLIER_PROPOSED_RULE}

STARTABLE_NOW = "STARTABLE_NOW"
STARTABLE_AFTER = "STARTABLE_AFTER"
NOT_STARTABLE = "NOT_STARTABLE"

MAX_ROUNDS = FB53.MAX_ROUNDS
MAX_SHOWN_SUPPLIERS = 12

supplier_inventory = FB53.supplier_inventory
match_body = FB53.match_body
body_and_head = FB53.body_and_head
standardise_apart = FB53.standardise_apart
unify = FB53.unify
printed_literal = FB53.printed_literal


def categorise(suppliers):
    """One honest label per possible supplier; nothing is merged."""
    out = []
    for s in suppliers:
        row = dict(s)
        row["category"] = CATEGORY_OF.get(s["kind"], GENERAL_LOGIC)
        out.append(row)
    return out


def _head_suppliers(hypothesis, head):
    return [{"clause_name": "%s (a rule this case proposed)"
                            % hypothesis["rule_id"],
             "kind": FB53.ATTEMPTED_HEAD, "category": EARLIER_PROPOSED_RULE,
             "source_kind": "attempted", "sign": UA.sign_of(lit),
             "literal": lit, "printed": printed_literal(lit),
             "from_rule": hypothesis["rule_id"], "one_of": 1}
            for lit in head]


# ------------------------------------------------------------ WP5.2: the rows

def report(view, hypotheses, refused=()):
    """-> why each first rule could not start, with honest supplier categories.

    No question literal is named as a target anywhere in this record.
    """
    suppliers = categorise(supplier_inventory(view))
    rows = []
    for h in hypotheses:
        body, _head = body_and_head(h)
        got = match_body(body, suppliers)
        assignment = []
        if got["assignments"]:
            for lit, s in zip(body, got["assignments"][0]):
                assignment.append({"premise": printed_literal(
                    UA.unsigned_atom(lit)),
                    "supplier": s["printed"], "category": s["category"],
                    "clause": s["clause_name"]})
        rows.append({"rule_id": h["rule_id"],
                     "printed": h.get("printed_formula"),
                     "body_may_start": got["may_start"],
                     "why_not": got.get("why"),
                     "premises_with_no_possible_supplier":
                         [printed_literal(UA.unsigned_atom(l))
                          for l in got["unmatched"]],
                     "available_premises": assignment,
                     "search_truncated": got["truncated"]})
    return {"version": VERSION,
            "policy": "a possible supplier is a clause literal a premise could "
                      "resolve with; it is not a derived fact and this is not "
                      "a proof",
            "supplier_counts": _counts(suppliers),
            "suppliers": suppliers,
            "rules": rows,
            "refused_rules": list(refused),
            "question_literals_are_not_shown": True}


def _counts(suppliers):
    out = {}
    for s in suppliers:
        out[s["category"]] = out.get(s["category"], 0) + 1
    return out


# ---------------------------------------------------------- WP6: chain status

def chain_status(view, hypotheses, extra_hypotheses=()):
    """-> {rule_id: status} over a bounded fixpoint of jointly matchable bodies.

    `hypotheses` are the rules whose status is asked for; `extra_hypotheses`
    are other compiled rules whose heads may also be used (the first-call
    bridges, for the accumulated calculation).
    """
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
                       "why": got.get("why"), "round": None}
    return {"status": dict((k, v) for k, v in status.items()
                           if pending[k]["asked"]),
            "all_status": status,
            "search_bound_reached": truncated,
            "rounds_allowed": MAX_ROUNDS}


def order_by_chain(rules, status):
    """Startable now, then startable after another rule, then not startable."""
    rank = {STARTABLE_NOW: 0, STARTABLE_AFTER: 1, NOT_STARTABLE: 2}

    def key(r):
        got = (status or {}).get(r["rule_id"]) or {}
        return (rank.get(got.get("status"), 3),
                int(str(r["rule_id"])[1:] or 0))
    return sorted(rules, key=key)


# ------------------------------------------------------------------ rendering

HEADING = "WHAT HAPPENED TO THE FIRST RULES"
SUPPLIED_HEADING = "REPRESENTATIONS THE EXISTING CLAUSES CAN OFFER"
STARTED_BUT_NO_PROOF = ("The body may start, but this rule did not produce a "
                        "proof in the first submission.")
ASSUMPTION_NOTE = ("QUESTION_ASSUMPTION is not a fact from the passage. It may "
                   "participate in a contradiction argument, but it is not "
                   "evidence that the question is true.")

INSTRUCTIONS = """Repair the first rules by using representations which are
available now.

Your proposed rules must form a chain which can start. At least one proposed
rule must have all its premises available from PASSAGE, GENERAL_LOGIC, or a
legitimate QUESTION_ASSUMPTION. A later proposed rule may use the conclusion of
an earlier proposed rule.

Prefer rewriting an unusable representation over directly asserting the
question. Do not repeat the first rules. Output only new RULE: lines."""


def render(rec):
    lines = [HEADING, ""]
    for row in rec["rules"]:
        lines.append("  %-4s %s" % (row["rule_id"], row["printed"]))
        lines.append("       CAN ITS BODY START NOW: %s"
                     % ("YES" if row["body_may_start"] else "NO"))
        if row["premises_with_no_possible_supplier"]:
            lines.append("       UNAVAILABLE PREMISES: %s"
                         % ", ".join(row["premises_with_no_possible_supplier"]))
        elif not row["body_may_start"]:
            lines.append("       UNAVAILABLE PREMISES: NONE — but its premises "
                         "cannot hold of the same objects at once")
        else:
            lines.append("       UNAVAILABLE PREMISES: NONE")
        for a in row["available_premises"]:
            lines.append("       AVAILABLE PREMISES AND SOURCE: %s — %s"
                         % (a["premise"], a["category"]))
        if row["body_may_start"]:
            lines.append("       %s" % STARTED_BUT_NO_PROOF)
        lines.append("")
    for row in rec["refused_rules"]:
        lines.append("  %-4s %s" % (row.get("rule_id"), row.get("printed")))
        lines.append("       THE PROGRAM COULD NOT USE IT: %s"
                     % row.get("why"))
        lines.append("")
    shown = _supplied_block(rec)
    if shown:
        lines.append(SUPPLIED_HEADING)
        lines.append("")
        lines.extend(shown)
        lines.append("")
    lines.append(ASSUMPTION_NOTE)
    return "\n".join(lines)


def _supplied_block(rec):
    """A compact list of what can be supplied, by category, deduplicated."""
    out, seen = [], set()
    for category in CATEGORIES:
        mine = []
        for s in rec["suppliers"]:
            if s["category"] != category:
                continue
            key = json.dumps([s["category"], s["printed"]])
            if key in seen:
                continue
            seen.add(key)
            mine.append(s["printed"])
        for printed in mine[:MAX_SHOWN_SUPPLIERS]:
            out.append("  %-22s %s" % (category, printed))
        if len(mine) > MAX_SHOWN_SUPPLIERS:
            out.append("  %-22s (%d more)" % (category,
                                              len(mine) - MAX_SHOWN_SUPPLIERS))
    return out
