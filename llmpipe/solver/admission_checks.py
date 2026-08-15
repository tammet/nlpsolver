"""Mechanical gates a dynamic bridge must pass before any model sees it.

These run before the meaning judge and again after conditions are compiled.
None of them is a judgement about meaning; each is a statement about the
representation, decidable from the formula alone.  They exist because the 08-10
corrected run promoted two rules that no semantic reading could have licensed
and one that the compiler's own condition contract forbids.

    variable_in_content_label       a lexical content slot holds a variable
    condition_contradicts_conclusion a chosen guard is the head's complement
    opposite_head_conflict          a sibling rule concludes the opposite

The first two are refusals.  The third is a property of a pair, and its
consequence is that neither is promoted — both stay as probes.

Range restriction, target-mode preservation, base-antecedent preservation and
the condition count live in `alignment_rule` and `dynamic_probe_pipeline`, which
already enforce them at compile time; `mechanical_gates` calls them here too so
one function answers "may this be promoted".
"""

import json

import alignment_compare as CMP
import alignment_occurrences as AO
import formula_print as FP

MAX_CONDITIONS = 3

# The refusal names.  Fixed strings: they are recorded in artifacts and read by
# scorers, so they are part of the interface.
VARIABLE_IN_CONTENT_LABEL = "variable_in_content_label"
CONDITION_CONTRADICTS_CONCLUSION = "condition_contradicts_conclusion"
OPPOSITE_HEAD_CONFLICT = "opposite_head_conflict"
UNBOUND_CONCLUSION_VARIABLE = "unbound_conclusion_variable"
TOO_MANY_CONDITIONS = "too_many_conditions"
BASE_ANTECEDENT_DROPPED = "base_antecedent_dropped"
CONCLUSION_CHANGED = "conclusion_changed"


# ---------------------------------------------------------------- 2.2

def content_label_variables(pkg):
    """Variables sitting in a lexical content slot.

    `isa`, `has property`, `has degree property` and `is rel2` carry the word
    they are about in a fixed argument.  That slot names a predicate of the
    problem's vocabulary, not an entity, so a variable there quantifies over
    lexical content — which this representation does not mean and gk does not
    read that way.  `folio-0069`'s admitted rule put `?Working` in the property
    slot and the result was a rule about every property whatever.

    If higher-order predicate variables are ever wanted, that is a
    representation change, decided deliberately somewhere else.
    """
    out = []
    for atom in _atoms(pkg):
        sign, pred, args = atom
        slot = AO.LABEL_SLOT.get(pred)
        if slot is None or slot >= len(args):
            continue
        term = args[slot]
        if isinstance(term, str) and AO._is_var(term):
            out.append({"predicate": pred, "slot": slot, "variable": term,
                        "atom": _show(atom)})
    return out


# ---------------------------------------------------------------- 2.3

def _unifiable(a, b):
    """Same predicate and arity, with variables matching anything.

    Deliberately loose: a guard whose label slot is a variable still counts as
    contradicting a head about that label, because that is exactly the shape
    that reached gk on `folio-0069`.
    """
    if a[1] != b[1] or len(a[2]) != len(b[2]):
        return False
    for x, y in zip(a[2], b[2]):
        xv = isinstance(x, str) and AO._is_var(x)
        yv = isinstance(y, str) and AO._is_var(y)
        if xv or yv:
            continue
        kx = AO.normalize_label(x) if isinstance(x, str) \
            else json.dumps(x, sort_keys=True)
        ky = AO.normalize_label(y) if isinstance(y, str) \
            else json.dumps(y, sort_keys=True)
        if kx != ky:
            return False
    return True


def contradicting_conditions(pkg, condition_atoms):
    """Chosen guards that are the complement of the head.

    A condition compiles to `BASE AND G -> HEAD` and to nothing else.  It is not
    an exception, it does not block the head, and it does not mean "unless".  A
    guard that asserts the head's complement makes the rule say that whenever
    its own conclusion is false it holds — which is not a restriction, it is a
    contradiction.  gk's `$block` handles an independently present contrary
    fact; that is a different mechanism and is not chosen here.
    """
    try:
        head = CMP.parse_rule_package(pkg)["consequent"]
    except CMP.ShapeError:
        return []
    out = []
    for c in condition_atoms or []:
        atom = _atom_of(c)
        if atom is None:
            continue
        if atom[0] != head[0] and _unifiable(atom, head):
            out.append({"condition": _show(atom), "head": _show(head),
                        "why": "the guard asserts the complement of the "
                               "conclusion, and a guard is a conjunct, not an "
                               "exception"})
    return out


# ---------------------------------------------------------------- 2.4

def opposite_head_groups(schemas):
    """Schemas sharing a base antecedent and an unsigned conclusion, opposite signs.

    Both remain probes.  Neither may be promoted, because promoting one is a
    claim the other is wrong and nothing at this stage establishes that.
    """
    by_key = {}
    for s in schemas:
        pkg = s.get("stage2_rule")
        if pkg is None:
            continue
        try:
            r = CMP.parse_rule_package(pkg)
        except CMP.ShapeError:
            continue
        ante = tuple(sorted(_show(a) for a in r["antecedents"]))
        head = r["consequent"]
        key = (ante, head[1], tuple(_key(x) for x in head[2]))
        by_key.setdefault(key, {"+": [], "-": []})[head[0]].append(
            s["schema_id"])
    out = []
    for key, sides in by_key.items():
        if sides["+"] and sides["-"]:
            out.append({"positive": sorted(sides["+"]),
                        "negative": sorted(sides["-"]),
                        "antecedents": list(key[0]),
                        "conclusion_predicate": key[1]})
    return out


def in_conflict(schema_id, groups):
    for g in groups:
        if schema_id in g["positive"] or schema_id in g["negative"]:
            return g
    return None


# ---------------------------------------------------------------- all of them

def mechanical_gates(pkg, base_pkg=None, condition_atoms=(), schema_id=None,
                     opposite_groups=()):
    """-> {"ok": bool, "refusals": [{"name", "detail"}], "notes": [...]}.

    Everything decidable without a model, in one place.  A refusal is a reason
    never to promote; it does not remove the probe result.
    """
    refusals = []
    cl = content_label_variables(pkg)
    if cl:
        refusals.append({"name": VARIABLE_IN_CONTENT_LABEL, "detail": cl})
    bad = contradicting_conditions(pkg, condition_atoms)
    if bad:
        refusals.append({"name": CONDITION_CONTRADICTS_CONCLUSION,
                         "detail": bad})
    unb = unbound_conclusion_variables(pkg)
    if unb:
        refusals.append({"name": UNBOUND_CONCLUSION_VARIABLE, "detail": unb})
    if len(condition_atoms or []) > MAX_CONDITIONS:
        refusals.append({"name": TOO_MANY_CONDITIONS,
                         "detail": len(condition_atoms)})
    if base_pkg is not None:
        same = CMP.compare(pkg, base_pkg, mode="exact")
        if not same.get("comparable") or same["direction"] != "forward":
            refusals.append({"name": CONCLUSION_CHANGED,
                             "detail": same.get("why") or same.get("direction")})
        elif same["missing_antecedents"]:
            refusals.append({"name": BASE_ANTECEDENT_DROPPED,
                             "detail": same["missing_antecedents"]})
    # An opposite-head sibling is NOT a refusal here.  Target modes mean almost
    # every question-goal candidate has one, so refusing on that alone would
    # refuse everything.  It is reported so the judge sees the pair together and
    # adjudicates it; only an adjudication that supports both, or cannot choose,
    # becomes the `opposite_head_conflict` refusal — in the policy, not here.
    sibling = in_conflict(schema_id, opposite_groups) if schema_id else None
    return {"ok": not refusals, "refusals": refusals,
            "opposite_head_sibling": sibling,
            "printed": FP.formula(pkg)}


def unbound_conclusion_variables(pkg):
    import alignment_rule as AR
    try:
        r = CMP.parse_rule_package(pkg)
    except CMP.ShapeError:
        return []
    ante = set()
    for a in r["antecedents"]:
        ante |= set(AR._vars_in(list(a[2])))
    return sorted(set(AR._vars_in(list(r["consequent"][2]))) - ante)


# ---------------------------------------------------------------- helpers

def _atoms(pkg):
    try:
        r = CMP.parse_rule_package(pkg)
    except CMP.ShapeError:
        return []
    return list(r["antecedents"]) + [r["consequent"]]


def _atom_of(node):
    if isinstance(node, dict):
        node = node.get("atom")
    try:
        return CMP.atom_of(node)
    except (CMP.ShapeError, TypeError, IndexError):
        return None


def _key(x):
    if isinstance(x, str):
        return x if AO._is_var(x) else AO.normalize_label(x)
    return json.dumps(x, sort_keys=True)


def _show(atom):
    pol, pred, args = atom
    return "%s%s(%s)" % ("" if pol == "+" else "not ", pred,
                         ", ".join(x if isinstance(x, str)
                                   else json.dumps(x) for x in args))
