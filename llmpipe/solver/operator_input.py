"""What the model is shown before it proposes a construction.

Three id spaces, and nothing outside them may be named:

    O<n>   a Stage-2 occurrence — one atom the translation actually produced,
           with the role of the sentence it came from
    L<n>   a label — every word the case uses as a predicate label AND every
           word it uses only as an ARGUMENT.  The second kind is the point:
           `organic matter` appears in eb2-0009 only as the second argument of
           `source of`, so a target space made of predicate labels could not
           express the reviewed rule at all.
    G<n>   a semantic group the AL-67 selector chose, carrying its own id from
           the v2 group artifact

A question occurrence is marked as a question everywhere it appears.  It tells
you which expression is at issue; it is not evidence that the expression holds,
and the prompt says so.

Nothing here reads a reviewed rule or an expected answer.
"""

import construction_operators as CO
import alignment_occurrences as AO

VERSION = "operator_input/1.0"

ROLE_OF = {"antecedent": "rule-premise", "conclusion": "rule-conclusion"}


def role_of(occ):
    if occ.get("in_question"):
        return "question"
    return ROLE_OF.get(occ.get("rule_side"), "fact")


def _show(lit):
    """A literal as the prompt prints it: `isa(animal lover, X)`."""
    neg = CO.is_negated(lit)
    atom = CO.strip_neg(lit)
    return "%s%s(%s)" % ("not " if neg else "", atom[0],
                         ", ".join(_term(a) for a in atom[1:]))


def _term(t):
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        return "%s(...)" % (t[0] if t and isinstance(t[0], str) else "...")
    return str(t)


def occurrences(stored):
    """Every source-linked Stage-2 atom this library could build from."""
    table = AO.extract(stored.get("stage1"), stored.get("stage2"))
    out, n = [], 0
    for occ in table["stage2"]:
        if occ.get("kind") == "rule_variable":
            continue
        if not CO.usable_source(occ):
            continue
        n += 1
        oid = "O%d" % n
        out.append({
            "oid": oid, "occurrence_id": occ["occurrence_id"],
            "unit": occ["unit_id"], "role": role_of(occ),
            "in_question": bool(occ.get("in_question")),
            "predicate": occ["predicate"], "label": occ.get("label"),
            "label_is_variable": bool(AO._is_var(occ.get("label") or "")),
            "literal": AO.signed_literal(occ),
            "shown": _show(AO.signed_literal(occ)),
            "sentence": occ.get("source_sentence"),
            "occ": occ,
        })
    return out


def labels(rows):
    """The label table: predicate labels and argument-only words, kept apart."""
    seen, out = {}, []
    for r in rows:
        lab = r["label"]
        if isinstance(lab, str) and lab and not r["label_is_variable"]:
            k = CO.normalize(lab)
            e = seen.get(k)
            if e is None:
                e = {"text": lab, "as_predicate_label": [],
                     "as_argument": []}
                seen[k] = e
                out.append(e)
            e["as_predicate_label"].append(r["oid"])
    for r in rows:
        _p, _l, parts = CO.split_atom(CO.strip_neg(r["literal"]))
        for _i, t in parts:
            if not isinstance(t, str) or AO._is_var(t):
                continue
            k = CO.normalize(t)
            e = seen.get(k)
            if e is None:
                e = {"text": t, "as_predicate_label": [], "as_argument": []}
                seen[k] = e
                out.append(e)
            e["as_argument"].append(r["oid"])
    for i, e in enumerate(out, start=1):
        e["lid"] = "L%d" % i
        e["argument_only"] = not e["as_predicate_label"]
    return out


def build_case(case_id, stored, split, groups, selected_ids):
    """-> the case view.  `groups` are the v2 groups, `selected_ids` the ones
    the AL-67 selector chose, already remapped to v2 ids."""
    rows = occurrences(stored)
    labs = labels(rows)
    by_gid = {g["group_id"]: g for g in groups}
    chosen = [by_gid[g] for g in selected_ids if g in by_gid]
    return {
        "case_id": case_id, "split": split,
        "input_text": stored.get("input_text"),
        "occurrences": rows,
        "labels": labs,
        "groups": chosen,
        "by_oid": dict((r["oid"], r["occ"]) for r in rows),
        "by_lid": dict((e["lid"], e) for e in labs),
        "by_gid": dict((g["group_id"], g) for g in chosen),
    }


# ---------------------------------------------------------------- rendering

def render(case, operators=CO.OPERATOR_SPECS):
    """The case as the prompt shows it.  Deterministic; no gold, no answer."""
    L = []
    L.append("THE PROBLEM")
    L.append("")
    L.append((case["input_text"] or "").strip())
    L.append("")
    L.append("WHAT THE TRANSLATION PRODUCED")
    L.append("")
    L.append("Each line is one atom, with the role of the sentence it came "
             "from. A line marked `question` comes from the question: it says "
             "which expression is at issue and asserts nothing.")
    L.append("")
    by_unit = {}
    for r in case["occurrences"]:
        by_unit.setdefault(r["unit"], []).append(r)
    for unit in sorted(by_unit, key=_unit_key):
        rows = by_unit[unit]
        sent = (rows[0].get("sentence") or "").strip()
        L.append("  %s  %s" % (unit, sent))
        for r in rows:
            L.append("    %-5s %-16s %s" % (r["oid"], r["role"], r["shown"]))
        L.append("")
    L.append("WORDS THIS PROBLEM USES")
    L.append("")
    L.append("A word marked `argument only` never appears as a predicate "
             "label: the logic can talk about it, but nothing can BE it.")
    L.append("")
    for e in case["labels"]:
        where = ("argument only" if e["argument_only"] else
                 "predicate label" if not e["as_argument"] else
                 "predicate label and argument")
        L.append("  %-5s %-34s %s" % (e["lid"], e["text"][:34], where))
    L.append("")
    L.append("WHAT THE PROVER NEEDED AND COULD NOT GET")
    L.append("")
    for g in case["groups"]:
        L.append("  %-5s %s" % (g["group_id"], g["readable"]))
    L.append("")
    L.append("THE OPERATORS")
    L.append("")
    for s in operators:
        L.append("  %-28s %s" % (s["name"], s["summary"]))
    L.append("")
    return "\n".join(L)


def _unit_key(u):
    try:
        return (0, int("".join(c for c in u if c.isdigit()) or 0))
    except ValueError:
        return (1, u)
