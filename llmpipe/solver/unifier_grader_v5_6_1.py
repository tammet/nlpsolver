"""v5.6 with the copied-id defect removed, and the raw axes reported separately.

Two changes, both small:

  * the example output header is `ASSESS_LOGIC <rule id>` / `ASSESS_BASIS <rule
    id>` instead of a concrete `R7`.  In the v5.6 run 25 replies of 68 copied
    the example's id into their own block.  The parser's one-block recovery
    caught all of them, but a recovery should not be the normal path.  Every
    substantive instruction is unchanged;
  * `axes()` and `descriptive_group()` expose what the two calls actually said,
    instead of collapsing it into one word.  The v5.6 report showed why: almost
    any bad rule can be called `NEEDS_CONDITION`, so that label alone answers no
    question about soundness.

Nothing else moves.  The connectivity diagnostic, both message builders, the
parsers and `combine()` are v5.6's, imported unchanged.
"""

import os
import re

import unifier_grader_v5_6 as GR56

VERSION = "unifier_grader_v5_6_1/1.0"

PROMPT_DIR = GR56.PROMPT_DIR
LOGIC_PROMPT_NAME = "grade_rule_logic_v5_6_1_system"
BASIS_PROMPT_NAME = "grade_rule_basis_v5_6_1_system"
SET_PROMPT_NAME = "grade_rule_set_v5_5_system"

# everything below is v5.6's, by reference
sha256_of = GR56.sha256_of
connectivity = GR56.connectivity
render_connectivity = GR56.render_connectivity
participants = GR56.participants
display_mapping = GR56.display_mapping
shown = GR56.shown
printed_rule = GR56.printed_rule
formal_reading = GR56.formal_reading
literals_of_rule = GR56.literals_of_rule
role_index = GR56.role_index
roles_of = GR56.roles_of
rule_logic_message = GR56.rule_logic_message
rule_basis_message = GR56.rule_basis_message
parse_logic = GR56.parse_logic
parse_basis = GR56.parse_basis
combine = GR56.combine
trust_class = GR56.trust_class
set_user_message = GR56.set_user_message
validate_manufacture = GR56.validate_manufacture
SINGLE_RULE_SET = GR56.SINGLE_RULE_SET
DECISIONS = GR56.DECISIONS

_SET_ANY = re.compile(r"^\s*SET\s+(\S+)\s*:\s*([A-Z_]+)\s*$", re.I)


def logic_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % LOGIC_PROMPT_NAME)) as f:
        return f.read()


def basis_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % BASIS_PROMPT_NAME)) as f:
        return f.read()


def set_system_prompt():
    return GR56.set_system_prompt()


def parse_set(text, set_id, rule_ids):
    """v5.5's parser, with the same one-block recovery the rule parsers have."""
    got = GR56.parse_set(text, set_id, rule_ids)
    got["written_under"] = None
    if got["explicitly_assessed"]:
        return got
    headers = [m.group(1) for m in
               (_SET_ANY.match(line) for line in (text or "").splitlines())
               if m]
    if len(headers) != 1 or headers[0].upper() == set_id.upper():
        return got
    other = GR56.parse_set(
        re.sub(r"(?im)^(\s*SET\s+)\S+(\s*:)", r"\g<1>%s\g<2>" % set_id, text),
        set_id, rule_ids)
    if other["explicitly_assessed"]:
        other["written_under"] = headers[0]
        other["note"] = ("the only SET block was written under %s, not %s; one "
                         "call carries one set, so it was used" % (headers[0],
                                                                   set_id))
        return other
    return got


# ------------------------------------------------------- WP1: the raw axes

REASONABLE = "reasonable_as_written"
REPAIR_CANDIDATE = "passage_repair_candidate"
INCOMPLETE = "incomplete_without_passage_repair"
WRONG_OR_COUNTEREXAMPLE = "wrong_direction_or_counterexample_reported"
UNCERTAIN_OR_UNPARSED = "uncertain_or_unparsed"

GROUPS = (REASONABLE, REPAIR_CANDIDATE, INCOMPLETE, WRONG_OR_COUNTEREXAMPLE,
          UNCERTAIN_OR_UNPARSED)


def axes(row):
    """-> the fields of one assessed rule, each on its own, nothing collapsed.

    `row` is a record written by the widening runner: `logic`, `basis`,
    `connectivity`, `combined`.
    """
    logic = row.get("logic") or {}
    basis = row.get("basis") or {}
    conn = row.get("connectivity") or {}
    return {"case_id": row.get("case_id"), "rule_id": row.get("rule_id"),
            "printed": row.get("printed"),
            "direction": logic.get("direction"),
            "body_sufficient": logic.get("body_sufficient"),
            "missing_condition": logic.get("missing_condition") or "",
            "ordinary_counterexample": logic.get("counterexample") or "",
            "basis": basis.get("basis"),
            "scope": basis.get("scope"),
            "missing_condition_present_in_passage":
                basis.get("condition_in_passage"),
            "supporting_sentence": basis.get("supporting_sentence") or "",
            "body_groups": conn.get("component_count"),
            "body_disconnected": conn.get("disconnected"),
            "conclusion_terms_in_no_premise":
                conn.get("conclusion_terms_in_no_premise") or [],
            "combined_decision": (row.get("combined") or {}).get("decision"),
            "combination_rule": (row.get("combined") or {}).get("rule_used"),
            "parser_recovery_used": bool(logic.get("written_under")
                                         or basis.get("written_under")),
            "logic_readable": bool(logic.get("explicitly_assessed")),
            "basis_readable": bool(basis.get("explicitly_assessed"))}


def descriptive_groups(row):
    """-> every group this rule belongs to.  The groups may overlap.

    Overlap is the point: a rule whose missing condition is in the passage AND
    which has an ordinary counterexample belongs to both, and forcing it into
    one class would hide half of what was reported.
    """
    got = axes(row)
    out = []
    if not (got["logic_readable"] and got["basis_readable"]):
        out.append(UNCERTAIN_OR_UNPARSED)
    if got["direction"] == "WRONG" or got["ordinary_counterexample"]:
        out.append(WRONG_OR_COUNTEREXAMPLE)
    if got["body_sufficient"] == "YES" and got["direction"] == "CORRECT" \
            and not got["ordinary_counterexample"]:
        out.append(REASONABLE)
    if got["body_sufficient"] == "NO" and got["missing_condition"]:
        if got["missing_condition_present_in_passage"] == "YES":
            out.append(REPAIR_CANDIDATE)
        else:
            out.append(INCOMPLETE)
    if got["body_sufficient"] == "UNCERTAIN" or got["direction"] == "UNCERTAIN":
        if UNCERTAIN_OR_UNPARSED not in out:
            out.append(UNCERTAIN_OR_UNPARSED)
    if not out:
        out.append(UNCERTAIN_OR_UNPARSED)
    return out


def report_rows(rows):
    """-> [{axes..., groups: [...]}] for a readable table, in the given order."""
    out = []
    for row in rows:
        got = axes(row)
        got["groups"] = descriptive_groups(row)
        out.append(got)
    return out


def group_counts(rows):
    counts = dict((g, 0) for g in GROUPS)
    overlap = {}
    for row in rows:
        groups = descriptive_groups(row)
        for g in groups:
            counts[g] += 1
        if len(groups) > 1:
            key = " + ".join(sorted(groups))
            overlap[key] = overlap.get(key, 0) + 1
    return {"groups": counts, "rules": len(rows), "overlaps": overlap}
