"""The mechanical connection report shown after a pool proves nothing (WP6).

This is not a failed proof and does not pretend to be one.  It is a reachability
calculation over the atoms the model was shown:

    available   = every candidate labelled PREMISE or BOTH
    a rule is reachable when EVERY body atom unifies with an available atom
    a reachable rule's head joins the available set
    repeat to a fixpoint

From that, three facts per rule — which premises nothing supplies, whether its
head reaches an atom something needs, and, for a one-premise rule only, whether
the reverse direction would fit the roles better — and one list: the
CONSEQUENCE atoms no reachable rule head reaches.

A rule refused by the compiler, or already present in the theory, is reported
as such instead of being diagnosed as unreachable.
"""

import json

import simple_rule_parser_v3 as P3
import unifier_abstraction as UA
import unifier_candidates_v3 as CV

VERSION = "unifier_feedback_v3/1.0"

MAX_NEW_RULES = 8


def _shape(atom):
    return P3._clause_shape(atom)


def unifies(a_sign, a_atom, b_sign, b_atom):
    if a_sign != b_sign:
        return False
    return UA.unify_unsigned_atoms(_shape(a_atom), _shape(b_atom))["unifiable"]


def available_atoms(candidates):
    """The signed atoms the theory can currently supply."""
    return [{"id": r["id"], "sign": r["sign"], "atom": r["surface_atom"],
             "printed": r["printed"]}
            for r in candidates if r["role"] in (CV.PREMISE, CV.BOTH)]


def needed_atoms(candidates):
    """The signed atoms the theory has a place for."""
    return [{"id": r["id"], "sign": r["sign"], "atom": r["surface_atom"],
             "printed": r["printed"]}
            for r in candidates if r["role"] in (CV.CONSEQUENCE, CV.BOTH)]


def reachability(rules, candidates):
    """-> (available set after the fixpoint, {rule_id: reachable})."""
    pool = [dict(a) for a in available_atoms(candidates)]
    reachable = {}
    changed = True
    while changed:
        changed = False
        for r in rules:
            if reachable.get(r["rule_id"]):
                continue
            if all(any(unifies(l["sign"], l["atom"], p["sign"], p["atom"])
                       for p in pool) for l in r["body"]):
                reachable[r["rule_id"]] = True
                pool.append({"id": None, "sign": r["head"]["sign"],
                             "atom": r["head"]["atom"],
                             "printed": "the head of %s" % r["rule_id"],
                             "from_rule": r["rule_id"]})
                changed = True
    for r in rules:
        reachable.setdefault(r["rule_id"], False)
    return pool, reachable


def missing_premises(rule, pool):
    out = []
    for l in rule["body"]:
        if not any(unifies(l["sign"], l["atom"], p["sign"], p["atom"])
                   for p in pool):
            out.append(l)
    return out


def head_reaches(rule, needed):
    for n in needed:
        if unifies(rule["head"]["sign"], rule["head"]["atom"], n["sign"],
                   n["atom"]):
            return n
    return None


def reverse_would_fit(rule, candidates):
    """One-premise rules only: would swapping premise and conclusion fit better?

    A mechanical statement about the role labels, not a claim that the reverse
    implication is true.  A taxonomic rule can fit the roles in the direction
    that is false, which is why the feedback prompt says so in words.
    """
    if len(rule["body"]) != 1:
        return None
    now = P3.role_fit(rule, {"atoms": [
        {"id": r["id"], "atom": r["surface_atom"], "sign": r["sign"],
         "role": r["role"], "priority_cost": r["priority_cost"]}
        for r in candidates]})
    swapped = {"body": [rule["head"]], "head": rule["body"][0]}
    then = P3.role_fit(swapped, {"atoms": [
        {"id": r["id"], "atom": r["surface_atom"], "sign": r["sign"],
         "role": r["role"], "priority_cost": r["priority_cost"]}
        for r in candidates]})
    return {"now_fits": now["fits"], "reversed_fits": then["fits"],
            "reverse_is_better": bool(then["fits"] and not now["fits"])}


def report(rules, candidates, refused=(), already=()):
    """-> the complete connection report, one row per rule plus the residue."""
    pool, reachable = reachability(rules, candidates)
    needed = needed_atoms(candidates)
    refused_by = dict((r["rule_id"], r) for r in refused)
    already_by = dict((r["rule_id"], r) for r in already)
    rows = []
    for r in rules:
        row = {"rule_id": r["rule_id"], "printed": r["printed"],
               "origin": r.get("origin")}
        if r["rule_id"] in already_by:
            row["status"] = "already_present"
            row["detail"] = already_by[r["rule_id"]]["why"]
            rows.append(row)
            continue
        if r["rule_id"] in refused_by:
            row["status"] = "compiler_refusal"
            row["detail"] = refused_by[r["rule_id"]]["why"]
            rows.append(row)
            continue
        missing = missing_premises(r, pool)
        reaches = head_reaches(r, needed)
        row.update({
            "status": "in_the_pool",
            "reachable": bool(reachable.get(r["rule_id"])),
            "missing_premises": [
                {"printed": UA.print_atom(UA.display_atom(l["atom"]),
                                          negated=l["sign"] == "-"),
                 "candidate": _candidate_id(l, candidates)}
                for l in missing],
            "head_reaches": reaches["id"] if reaches else None,
            "head_reaches_printed": reaches["printed"] if reaches else None,
            "reverse": reverse_would_fit(r, candidates)})
        rows.append(row)
    reached = set()
    for r in rules:
        if r["rule_id"] in refused_by or r["rule_id"] in already_by:
            continue
        if not reachable.get(r["rule_id"]):
            continue
        got = head_reaches(r, needed)
        if got and got["id"]:
            reached.add(got["id"])
    unsupplied = [n for n in needed if n["id"] not in reached]
    return {"version": VERSION, "rules": rows,
            "available_after_fixpoint": len(pool),
            "still_unsupplied": unsupplied,
            "note": "a reachability calculation over the displayed atoms, not "
                    "a partial or failed proof"}


def _candidate_id(literal, candidates):
    for r in candidates:
        if r["sign"] == literal["sign"] and P3.alpha_equivalent(
                r["surface_atom"], literal["atom"]):
            return r["id"]
    for r in candidates:
        if r["sign"] == literal["sign"] and unifies(
                r["sign"], r["surface_atom"], literal["sign"],
                literal["atom"]):
            return r["id"]
    return None


# ---------------------------------------------------------------- rendering

def render(report_rows, candidate_body):
    """The dynamic block appended to the frozen feedback instructions."""
    lines = ["MAIN AND SECONDARY CANDIDATES", "", candidate_body, "",
             "EXISTING RULES AND MECHANICAL CONNECTION REPORT", ""]
    for row in report_rows["rules"]:
        lines.append("  %-4s %s" % (row["rule_id"], row["printed"]))
        if row["status"] == "already_present":
            lines.append("       ALREADY IN THE PROGRAM: %s" % row["detail"])
            lines.append("")
            continue
        if row["status"] == "compiler_refusal":
            lines.append("       NOT USABLE: %s" % row["detail"])
            lines.append("")
            continue
        if row["missing_premises"]:
            lines.append("       BODY: NOT AVAILABLE: %s"
                         % ", ".join(m["candidate"] or m["printed"]
                                     for m in row["missing_premises"]))
        else:
            lines.append("       BODY: AVAILABLE")
        if row["head_reaches"]:
            lines.append("       HEAD: REACHES %s" % row["head_reaches"])
        else:
            lines.append("       HEAD: REACHES NO CURRENT CONSEQUENCE")
        rev = row.get("reverse")
        if rev is None:
            lines.append("       DIRECTION: NO SIMPLE TEST")
        elif rev["reverse_is_better"]:
            lines.append("       DIRECTION: REVERSE WOULD FIT ROLES BETTER")
        elif rev["now_fits"]:
            lines.append("       DIRECTION: FITS ROLES")
        else:
            lines.append("       DIRECTION: NO SIMPLE TEST")
        lines.append("")
    lines.append("STILL UNSUPPLIED CONSEQUENCES")
    lines.append("")
    if report_rows["still_unsupplied"]:
        for n in report_rows["still_unsupplied"]:
            lines.append("  %-4s %s" % (n["id"], n["printed"]))
    else:
        lines.append("  (none: every consequence candidate is reached by some "
                     "rule)")
    return "\n".join(lines)
