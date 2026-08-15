"""Compare a constructed rule with a reference rule.

Both sides are given as literals; this module never loads a reviewed rule, an
expected answer or any scored artifact — the caller supplies both rules, and
only a gold-loading scorer is allowed to supply the second one.

Five outcomes, and the distinctions between them are the point:

    exact                  the same rule, up to variable renaming
    safe_specialization    the same conclusion, from a body that is at least as
                           restrictive: extra conjuncts, a degree form in place
                           of the plain form, a constant where the reference
                           generalises.  It fires on a subset of what the
                           reference fires on, so it is sound wherever the
                           reference is
    base_connection_only   the same conclusion, but a reference premise is
                           MISSING: the rule is more general than the reference
                           and its extra reach is not licensed
    head_mismatch          it concludes something else
    no_match               nothing lined up

`base_connection_only` is deliberately not called a partial success.  A missing
guard is the failure mode that makes a bridge derive things the source never
said, and merging it into "close enough" is how that failure hides.
"""

import alignment_occurrences as AO
import construction_operators as CO

VERSION = "rule_compare/1.0"

EXACT = "exact"
SAFE = "safe_specialization"
BASE_ONLY = "base_connection_only"
HEAD_MISMATCH = "head_mismatch"
NO_MATCH = "no_match"
ORDER = [EXACT, SAFE, BASE_ONLY, HEAD_MISMATCH, NO_MATCH]


def view(lit):
    """-> (sign, family predicate, normalized label, [participants], raw pred)."""
    neg = CO.is_negated(lit)
    atom = CO.strip_neg(lit)
    pred, label, parts = CO.split_atom(atom)
    return {"sign": "-" if neg else "+", "family": CO.family(pred),
            "predicate": pred,
            "label": CO.normalize(label) if isinstance(label, str) else None,
            "label_is_var": bool(isinstance(label, str) and AO._is_var(label)),
            "label_raw": label,
            "parts": [t for _i, t in parts]}


def from_reviewed(lit):
    """A reviewed literal `["+", "isa", ["organism", "Y"]]` as a view."""
    sign, pred, args = lit
    slot = CO.label_index(pred)
    if pred == "has type":
        slot = 1
    label = args[slot] if (slot is not None and slot < len(args)) else None
    parts = [a for i, a in enumerate(args) if i != slot]
    return {"sign": sign, "family": CO.family(pred), "predicate": pred,
            "label": CO.normalize(label) if isinstance(label, str) else None,
            "label_is_var": bool(isinstance(label, str) and AO._is_var(label)),
            "label_raw": label, "parts": list(parts)}


def _is_var(t):
    return isinstance(t, str) and AO._is_var(t)


def _unify_term(ref, got, mapping, flags):
    """Map a reference term onto a constructed one.  One direction only."""
    if _is_var(ref):
        prev = mapping.get(ref)
        if prev is not None:
            return prev == got
        if not _is_var(got):
            flags.add("constant_for_a_variable")
        mapping[ref] = got
        return True
    if _is_var(got):
        flags.add("variable_for_a_constant")     # MORE general: never safe
        return CO.normalize(ref) == CO.normalize(ref)   # accepted, flagged
    return CO.normalize(ref) == CO.normalize(got)


def _match_literal(ref, got, mapping, flags):
    if ref["sign"] != got["sign"]:
        return False
    if ref["family"] != got["family"]:
        return False
    if ref["label_is_var"] or got["label_is_var"]:
        if ref["label_is_var"] != got["label_is_var"]:
            return False
    elif ref["label"] != got["label"]:
        return False
    if len(got["parts"]) < len(ref["parts"]):
        return False
    if len(got["parts"]) > len(ref["parts"]):
        # a degree form says everything the plain form says and more
        if ref["predicate"] == got["predicate"]:
            return False
        flags.add("degree_form_for_plain_form")
    local = dict(mapping)
    lf = set()
    for a, b in zip(ref["parts"], got["parts"]):
        if not _unify_term(a, b, local, lf):
            return False
    mapping.clear()
    mapping.update(local)
    flags.update(lf)
    return True


def _search(refs, gots, mapping, used, flags):
    """Every reference body atom matched to a distinct constructed atom."""
    if not refs:
        return True, dict(mapping), set(flags), set(used)
    ref = refs[0]
    for i, got in enumerate(gots):
        if i in used:
            continue
        m, f = dict(mapping), set(flags)
        if not _match_literal(ref, got, m, f):
            continue
        ok, m2, f2, u2 = _search(refs[1:], gots, m, used | {i}, f)
        if ok:
            return True, m2, f2, u2
    return False, None, None, None


def compare(constructed_body, constructed_head, reviewed):
    """-> {"category", "flags", "unmatched", "extra", "mapping"}.

    `reviewed` is `{"antecedents": [...], "consequent": ...}` in the reviewed
    rule's own literal form.  The comparison is one-directional on purpose: it
    asks whether the constructed rule SAYS what the reference says, not whether
    the two are interchangeable.
    """
    ref_head = from_reviewed(reviewed["consequent"])
    ref_body = [from_reviewed(a) for a in reviewed["antecedents"]]
    got_head = view(constructed_head)
    got_body = [view(b) for b in constructed_body]

    mapping, flags = {}, set()
    if not _match_literal(ref_head, got_head, mapping, flags):
        return {"category": HEAD_MISMATCH, "flags": sorted(flags),
                "unmatched": len(ref_body), "extra": len(got_body),
                "mapping": {}}
    ok, m, f, used = _search(ref_body, got_body, mapping, set(), flags)
    if not ok:
        # how much of the body did line up, for the report
        best, bm, bf, bu = 0, {}, set(), set()
        for k in range(len(ref_body) - 1, 0, -1):
            for drop in range(len(ref_body)):
                subset = [r for i, r in enumerate(ref_body) if i != drop][:k]
                ok2, m2, f2, u2 = _search(subset, got_body, dict(mapping),
                                          set(), set(flags))
                if ok2 and len(subset) > best:
                    best, bm, bf, bu = len(subset), m2, f2, u2
            if best:
                break
        return {"category": BASE_ONLY if best or not ref_body else NO_MATCH,
                "flags": sorted(bf), "unmatched": len(ref_body) - best,
                "extra": len(got_body) - len(bu), "mapping": bm}
    extra = len(got_body) - len(used)
    if "variable_for_a_constant" in f:
        # the constructed rule quantifies where the reference names a thing:
        # strictly MORE general, so it is not a safe specialization
        return {"category": BASE_ONLY, "flags": sorted(f), "unmatched": 0,
                "extra": extra, "mapping": m}
    specialized = bool(extra) or bool(f)
    if not specialized and len(got_body) == len(ref_body):
        return {"category": EXACT, "flags": [], "unmatched": 0, "extra": 0,
                "mapping": m}
    return {"category": SAFE, "flags": sorted(f), "unmatched": 0,
            "extra": extra, "mapping": m}


def best(results):
    """The strongest category among several comparisons."""
    for cat in ORDER:
        for r in results:
            if r["category"] == cat:
                return r
    return {"category": NO_MATCH, "flags": [], "unmatched": None,
            "extra": None, "mapping": {}}
