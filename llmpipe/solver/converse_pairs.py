"""Which two candidate rules are each other's converse, and which merely rhyme.

    A:  BODY_A -> HEAD_A
    B:  BODY_B -> HEAD_B

They are converses when A's head IS B's principal source literal and B's head IS
A's principal source literal, under ONE argument correspondence used for both
directions.  "Is" means the same sign, the same predicate, the same content
label, the same constants, and the same argument order — a bijective renaming of
bound variables is the only thing allowed to differ.

That is deliberately strict.  `part of(X,Y) -> in(X,Y)` and `in(Y,X) -> part
of(X,Y)` are NOT converses: the argument correspondence is not the same one, and
treating them as a pair would put a swapped relation in front of a judge as if
it were a direction question.  Everything the pair does not share — the guards
each side carries, whether one side is grounded where the other is general,
scope — is recorded on the pair rather than smoothed away, because those are
exactly the differences the judge has to see.

Pure: no file, no call, no gold.
"""

import construction_operators as CO
import operator_input as OI

VERSION = "converse_pairs/1.0"


def _split(lit):
    """-> (sign, predicate, label, [participants]) for either negation form."""
    neg = CO.is_negated(lit)
    atom = CO.strip_neg(lit)
    if isinstance(atom, list) and atom and isinstance(atom[0], str) \
            and atom[0].startswith("-"):
        neg = True
        atom = [atom[0][1:]] + list(atom[1:])
    pred, label, parts = CO.split_atom(atom)
    return ("-" if neg else "+", pred, label, [t for _i, t in parts])


def _is_var(term):
    return isinstance(term, str) and term in CO._vars_in([term])


def match(a, b, mapping):
    """True when `a` and `b` are the same literal up to a bijective renaming.

    `mapping` accumulates the correspondence and is shared across both halves of
    a pair, so a renaming that works for the heads must be the same one that
    works for the bodies.  Constants must be equal, not merely both constants.
    """
    sa, pa, la, aa = _split(a)
    sb, pb, lb, ab = _split(b)
    if (sa, pa, la) != (sb, pb, lb) or len(aa) != len(ab):
        return False
    for x, y in zip(aa, ab):
        if _is_var(x) and _is_var(y):
            if mapping.get(x, y) != y or mapping.get("<-" + y, x) != x:
                return False
            mapping[x] = y
            mapping["<-" + y] = x
        elif _is_var(x) or _is_var(y):
            return False            # a variable never matches a constant here
        elif x != y:
            return False
    return True


def principal_index(row, other_head, mapping):
    """Which body literal of `row` is the other rule's head, if any."""
    for i, lit in enumerate(row["body"]):
        trial = dict(mapping)
        if match(other_head, lit, trial):
            mapping.clear()
            mapping.update(trial)
            return i
    return None


def grounded(row):
    """Constants anywhere in the rule: a grounded form, not a general one."""
    out = []
    for lit in list(row["body"]) + [row["head"]]:
        for t in _split(lit)[3]:
            if isinstance(t, str) and not _is_var(t) and t not in out:
                out.append(t)
    return out


def converse(a, b):
    """-> a pair record, or None when they are not converses.

    Both halves are matched under ONE mapping: A's head against a body literal
    of B, and B's head against a body literal of A.
    """
    mapping = {}
    ib = principal_index(b, a["head"], mapping)
    if ib is None:
        return None
    ia = principal_index(a, b["head"], mapping)
    if ia is None:
        return None
    if _split(a["head"])[:3] == _split(b["head"])[:3] and len(a["body"]) == \
            len(b["body"]) == 1:
        # same head predicate on both sides: not two directions, one rule twice
        return None
    guards_a = [lit for i, lit in enumerate(a["body"]) if i != ia]
    guards_b = [lit for i, lit in enumerate(b["body"]) if i != ib]
    ga, gb = grounded(a), grounded(b)
    return {
        "a": a["printed_formula"], "b": b["printed_formula"],
        "argument_correspondence": dict(
            (k, v) for k, v in mapping.items() if not k.startswith("<-")),
        "principal_literal_of_a": OI._show(a["body"][ia]),
        "principal_literal_of_b": OI._show(b["body"][ib]),
        "guards_on_a": [OI._show(g) for g in guards_a],
        "guards_on_b": [OI._show(g) for g in guards_b],
        "guard_count": (len(guards_a), len(guards_b)),
        "grounded_terms_a": ga, "grounded_terms_b": gb,
        "form": ("both general" if not ga and not gb else
                 "both grounded" if ga and gb else
                 "one grounded, one general"),
        "same_sign": _split(a["head"])[0] == _split(b["head"])[0],
        "differences": [d for d in [
            "guards differ" if guards_a or guards_b else None,
            "one side is grounded" if bool(ga) != bool(gb) else None,
            "different constants" if ga and gb and set(ga) != set(gb) else None,
        ] if d],
    }


def find_pairs(rows, ids=None):
    """Every converse pair among `rows`, with provenance from both sides.

    `rows` are canonical formula rows: `body`, `head`, `printed_formula`,
    `derivation_paths`.  `ids` optionally names them (a variant id per row).
    """
    out = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            got = converse(rows[i], rows[j])
            if got is None:
                continue
            got.update({
                "a_id": (ids[i] if ids else "R%d" % (i + 1)),
                "b_id": (ids[j] if ids else "R%d" % (j + 1)),
                "a_paths": [p.get("path_id") for p in
                            rows[i].get("derivation_paths") or []],
                "b_paths": [p.get("path_id") for p in
                            rows[j].get("derivation_paths") or []],
                "a_operators": sorted(set(
                    p["operator"] for p in
                    rows[i].get("derivation_paths") or [])),
                "b_operators": sorted(set(
                    p["operator"] for p in
                    rows[j].get("derivation_paths") or [])),
                "a_path_count": len(rows[i].get("derivation_paths") or []),
                "b_path_count": len(rows[j].get("derivation_paths") or []),
            })
            out.append(got)
    return out
