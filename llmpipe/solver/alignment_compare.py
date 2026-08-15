"""Structural comparison of a compiled bridge rule against a reviewed rule.

Replaces the measurement that `tools/run_alignment_chain2.py` used, which was

    bool(set(ants) & gprod) and all(i in allowed for i in ants)

— a nonempty intersection with a broad producer set.  That accepts a rule that
drops a required condition, and it accepted both animal-lover rules:

    generated  love(X,Y)                 -> animal_lover(X)
    reviewed   love(X,Y) AND animal(Y)   -> normally animal_lover(X)

`legacy_antecedent_measure` below is that old test, kept so a fixture can show
what it accepts.  Nothing else uses it.

What is compared here is the compiled Stage-2 package against the reviewed
`gold_replacement_packages` entry, structurally.  Bound variables may be
renamed — consistently and bijectively, so two gold variables can never collapse
into one.  Nothing else is normalised away: predicate, negation, constants,
argument order and the `normally` wrapper all have to survive.

Six components are scored separately and never summed:

  1. consequent and direction
  2. argument correspondence
  3. missing antecedents      (in the reviewed rule, absent from the compiled one)
  4. extra antecedents        (the other way round)
  5. strict versus normally
  6. constant specialization / variable generalization

A predicate-family difference (`is rel2(loving,...)` where the reviewed rule
says `has degree rel2(loving,...)`) is a real difference and is reported as one.
`label_only=True` relaxes only that, and the relaxed figure is always reported
beside the strict one, never instead of it.
"""

import itertools
import json

import alignment_context as CX
import alignment_occurrences as AO

STRICT, DEFAULT = "strict", "default"


class ShapeError(Exception):
    """The package is not a rule of the shape this comparison understands."""


# ---------------------------------------------------------------- shape

def _norm_const(x):
    return AO.normalize_label(x) if isinstance(x, str) else json.dumps(x,
                                                                      sort_keys=True)


def atom_of(node):
    """-> (polarity, predicate, args) for an atom, possibly under `not`."""
    pol = "+"
    while isinstance(node, list) and len(node) == 2 and node[0] == "not":
        pol = "-" if pol == "+" else "+"
        node = node[1]
    if not isinstance(node, list) or not node or not isinstance(node[0], str):
        raise ShapeError("not an atom: %s" % json.dumps(node)[:60])
    if node[0] in AO.LOGICAL_HEADS:
        raise ShapeError("%s is a connective, not an atom" % node[0])
    return (pol, node[0], list(node[1:]))


def _conjuncts(node):
    if isinstance(node, list) and node and node[0] == "and":
        out = []
        for ch in node[1:]:
            out.extend(_conjuncts(ch))
        return out
    return [node]


def parse_rule_package(pkg):
    """-> {world, bound, strength, antecedents, consequent}, or raise.

    Accepts `normally` anywhere in the quantifier prefix, which is where both
    the compiler and the reviewed rules put it.
    """
    f, world = pkg, None
    if isinstance(f, list) and f and f[0] == "holds" and len(f) == 3:
        world, f = f[1], f[2]
    bound, strength = [], STRICT
    while isinstance(f, list) and f:
        if f[0] in ("forall", "exists") and len(f) >= 3:
            bound.append((f[0], f[1]))
            f = f[2]
        elif f[0] == "normally" and len(f) == 2:
            strength = DEFAULT
            f = f[1]
        else:
            break
    if not (isinstance(f, list) and len(f) == 3 and f[0] == "implies"):
        raise ShapeError("not a quantified implication: %s"
                         % json.dumps(pkg)[:80])
    head = f[2]
    # `forall vars . BODY -> normally(HEAD)` is the shape `bridge_world` emits,
    # because it is the one that survives conversion with its `$block`.  It says
    # the same thing as a `normally` in the prefix and is read the same way here.
    while isinstance(head, list) and len(head) == 2 and head[0] == "normally":
        strength = DEFAULT
        head = head[1]
    return {"world": world, "bound": bound, "strength": strength,
            "antecedents": [atom_of(c) for c in _conjuncts(f[1])],
            "consequent": atom_of(head)}


# ---------------------------------------------------------------- matching

class _Map(object):
    """A bijection between compiled-rule variables and reviewed-rule ones."""

    def __init__(self, fwd=None, bwd=None):
        self.fwd = dict(fwd or {})
        self.bwd = dict(bwd or {})

    def copy(self):
        return _Map(self.fwd, self.bwd)

    def bind(self, a, b):
        if self.fwd.get(a, b) != b or self.bwd.get(b, a) != a:
            return False
        self.fwd[a] = b
        self.bwd[b] = a
        return True


def _args_match(ra, ga, vmap):
    """-> (ok, notes).  `notes` records specialization/generalization."""
    if len(ra) != len(ga):
        return False, []
    notes = []
    for i, (a, b) in enumerate(zip(ra, ga)):
        av, bv = AO._is_var(a), AO._is_var(b)
        if av and bv:
            if not vmap.bind(a, b):
                return False, []
        elif not av and not bv:
            if _norm_const(a) != _norm_const(b):
                return False, []
        elif not av and bv:
            notes.append({"position": i, "kind": "constant_specialization",
                          "compiled": a, "reviewed": b})
        else:
            notes.append({"position": i, "kind": "variable_generalization",
                          "compiled": a, "reviewed": b})
    return True, notes


def label_and_participants(atom):
    """(content label, participant terms) of an atom tuple.

    The degree families carry a degree and a comparison class after their
    participants; those are not participants, and treating them as such makes
    every graded adjective look as though it shared an argument with every
    other one.
    """
    pol, pred, args = atom
    slot = AO.LABEL_SLOT.get(pred)
    label = args[slot] if (slot is not None and slot < len(args)) else pred
    if pred in CX.PARTICIPANT_ARGS:
        parts = [args[i] for i in CX.PARTICIPANT_ARGS[pred] if i < len(args)]
    else:
        parts = [a for i, a in enumerate(args) if i != slot]
    return label, parts


def _match_representation(r, g, vmap, permute):
    """Same content under a possibly different predicate family.

    `is rel2(loving, X, A)` and `has degree rel2(loving, X, A, none, person)`
    say the same thing about the same two participants in two representations.
    Matching them here is what lets the classification below call that a
    representation difference instead of a missing condition — but it is
    recorded as a difference, never as equality.
    """
    if r[0] != g[0]:
        return None
    rl, rp = label_and_participants(r)
    gl, gp = label_and_participants(g)
    if _norm_const(rl) != _norm_const(gl) or len(rp) != len(gp):
        return None
    orders = [tuple(range(len(rp)))]
    if permute and len(rp) > 1:
        orders = list(itertools.permutations(range(len(rp))))
    for order in orders:
        m = vmap.copy()
        ok, notes = _args_match([rp[i] for i in order], gp, m)
        if not ok:
            continue
        if order != tuple(range(len(rp))):
            how = "permuted"
        elif r[1] == g[1] and len(r[2]) == len(g[2]):
            how = "exact"
        else:
            how = "predicate_family_differs"
        return m, notes, how
    return None


def _atoms_match(r, g, vmap, label_only=False, mode=None):
    """One compiled atom against one reviewed atom, under a variable map."""
    mode = mode or ("label_only" if label_only else "exact")
    if mode in ("representation", "permuted"):
        return _match_representation(r, g, vmap, mode == "permuted")
    label_only = mode == "label_only"
    if r[0] != g[0]:
        return None
    if r[1] != g[1]:
        if not label_only:
            return None
        # the same content under a different predicate family: the label slots
        # must still agree, and so must the term positions
        rs, gs = AO.LABEL_SLOT.get(r[1]), AO.LABEL_SLOT.get(g[1])
        if rs is None or gs is None or rs >= len(r[2]) or gs >= len(g[2]):
            return None
        if _norm_const(r[2][rs]) != _norm_const(g[2][gs]):
            return None
        rr = [a for i, a in enumerate(r[2]) if i != rs]
        gg = [a for i, a in enumerate(g[2]) if i != gs]
        m = vmap.copy()
        ok, notes = _args_match(rr, gg, m)
        return (m, notes, "predicate_family_differs") if ok else None
    m = vmap.copy()
    ok, notes = _args_match(r[2], g[2], m)
    return (m, notes, "exact") if ok else None


def _align(rule_atoms, gold_atoms, vmap, label_only=False, mode=None):
    """Best injective alignment of compiled antecedents onto reviewed ones.

    Both sides are at most a handful of atoms, so every injection is tried and
    the one matching most atoms wins; ties break on fewer specialization notes.
    """
    best = None
    n, m = len(rule_atoms), len(gold_atoms)
    for perm in itertools.permutations(range(n), min(n, m)):
        cur, notes, pairs = vmap.copy(), [], []
        ok = True
        for gi, ri in enumerate(perm):
            res = _atoms_match(rule_atoms[ri], gold_atoms[gi], cur, label_only,
                               mode)
            if res is None:
                ok = False
                break
            cur, nts, how = res
            notes.extend(nts)
            pairs.append((ri, gi, how))
        if not ok:
            continue
        key = (len(pairs), -len(notes))
        if best is None or key > best[0]:
            best = (key, cur, notes, pairs)
    if best is None:
        # no full injection matched; fall back to a greedy partial alignment so
        # partial credit is still visible
        cur, notes, pairs, used = vmap.copy(), [], [], set()
        for gi, g in enumerate(gold_atoms):
            for ri, r in enumerate(rule_atoms):
                if ri in used:
                    continue
                res = _atoms_match(r, g, cur, label_only, mode)
                if res is not None:
                    cur, nts, how = res
                    notes.extend(nts)
                    pairs.append((ri, gi, how))
                    used.add(ri)
                    break
        return cur, notes, pairs
    return best[1], best[2], best[3]


def _show(a):
    pol = "" if a[0] == "+" else "not "
    return "%s%s(%s)" % (pol, a[1], ", ".join(
        x if isinstance(x, str) else json.dumps(x) for x in a[2]))


# ---------------------------------------------------------------- comparison

def compare(rule_pkg, gold_pkg, label_only=False, mode=None):
    """Component-wise comparison.  Never collapses into one number.

    `mode` selects how two atoms are allowed to match: `exact` (default),
    `label_only` (the historical relaxation, label slot only), `representation`
    (same content label and participants, any predicate family), or `permuted`
    (as `representation`, with participants allowed to permute — used only to
    detect swapped arguments, never to award credit).
    """
    mode = mode or ("label_only" if label_only else "exact")
    try:
        r = parse_rule_package(rule_pkg)
    except ShapeError as e:
        return {"comparable": False, "why": "compiled rule: %s" % e}
    try:
        g = parse_rule_package(gold_pkg)
    except ShapeError as e:
        return {"comparable": False, "why": "reviewed rule: %s" % e}

    def run(rants, rcons):
        vm = _Map()
        res = _atoms_match(rcons, g["consequent"], vm, label_only, mode)
        if res is None:
            return None
        vm, notes, how = res
        vm, anotes, pairs = _align(rants, g["antecedents"], vm, label_only, mode)
        return {"vmap": vm, "consequent_how": how,
                "notes": notes + anotes, "pairs": pairs}

    forward = run(r["antecedents"], r["consequent"])
    # a reversed rule: what the compiled rule concludes is what the reviewed one
    # assumes.  Detected explicitly so it is never scored as a near miss.  Any
    # antecedent may be the one that changed places with the conclusion.
    reversed_ = None
    for i in range(len(r["antecedents"])):
        cand = run(r["antecedents"][:i] + r["antecedents"][i + 1:]
                   + [r["consequent"]], r["antecedents"][i])
        if cand is not None:
            reversed_ = cand
            break

    if forward is not None:
        direction, best = "forward", forward
    elif reversed_ is not None:
        direction, best = "reversed", reversed_
    else:
        direction, best = "unmatched", None

    out = {
        "comparable": True,
        "label_only": label_only,
        "mode": mode,
        "direction": direction,
        "consequent_and_direction": direction == "forward",
        "consequent_match_kind": best["consequent_how"] if best else None,
        "compiled": {"antecedents": [_show(a) for a in r["antecedents"]],
                     "consequent": _show(r["consequent"]),
                     "strength": r["strength"]},
        "reviewed": {"antecedents": [_show(a) for a in g["antecedents"]],
                     "consequent": _show(g["consequent"]),
                     "strength": g["strength"]},
    }
    if direction != "forward":
        out.update({
            "argument_correspondence": False,
            "missing_antecedents": [_show(a) for a in g["antecedents"]],
            "extra_antecedents": [_show(a) for a in r["antecedents"]],
            "antecedents_complete": False,
            "no_extra_antecedents": False,
            "specializations": [], "generalizations": [],
            "constants_and_variables_as_reviewed": False,
        })
    else:
        matched_r = set(ri for ri, _, _ in best["pairs"])
        matched_g = set(gi for _, gi, _ in best["pairs"])
        missing = [_show(a) for i, a in enumerate(g["antecedents"])
                   if i not in matched_g]
        extra = [_show(a) for i, a in enumerate(r["antecedents"])
                 if i not in matched_r]
        spec = [n for n in best["notes"] if n["kind"] == "constant_specialization"]
        gen = [n for n in best["notes"] if n["kind"] == "variable_generalization"]
        out.update({
            "argument_correspondence": not spec and not gen,
            "variable_map": dict(best["vmap"].fwd),
            "missing_antecedents": missing,
            "extra_antecedents": extra,
            "antecedents_complete": not missing,
            "no_extra_antecedents": not extra,
            "specializations": spec,
            "generalizations": gen,
            "constants_and_variables_as_reviewed": not spec and not gen,
            "matched_antecedent_kinds": sorted(set(h for _, _, h in best["pairs"])),
        })
    out["strength_compiled"] = r["strength"]
    out["strength_reviewed"] = g["strength"]
    out["strength_match"] = r["strength"] == g["strength"]
    out["all_components_correct"] = bool(
        out["consequent_and_direction"] and out["argument_correspondence"]
        and out["antecedents_complete"] and out["no_extra_antecedents"]
        and out["strength_match"])
    return out


def components(cmp_result):
    """The six scored components, as booleans, for tabulation."""
    if not cmp_result.get("comparable"):
        return {k: False for k in COMPONENTS}
    return {
        "consequent_and_direction": bool(cmp_result["consequent_and_direction"]),
        "argument_correspondence": bool(cmp_result["argument_correspondence"]),
        "antecedents_complete": bool(cmp_result["antecedents_complete"]),
        "no_extra_antecedents": bool(cmp_result["no_extra_antecedents"]),
        "strength_match": bool(cmp_result["strength_match"]),
        "constants_and_variables_as_reviewed": bool(
            cmp_result["constants_and_variables_as_reviewed"]),
    }


COMPONENTS = ("consequent_and_direction", "argument_correspondence",
              "antecedents_complete", "no_extra_antecedents", "strength_match",
              "constants_and_variables_as_reviewed")


# ---------------------------------------------------------------- classification

CLASSES = ("exact", "safe_specialization", "different_representation",
           "unsafe_generalization", "incompatible")

SAFE_CLASSES = ("exact", "safe_specialization", "different_representation")


def classify(rule_pkg, gold_pkg):
    """How a compiled rule stands to the reviewed one, semantically.

    The exact structural comparison above is unchanged and is returned intact.
    This adds the question it does not answer: a rule can differ from the
    reviewed one and still be sound.

      exact                   the same rule up to bound-variable renaming
      safe_specialization     narrower: a reviewed variable grounded, or an
                              extra antecedent, or defeasible where the
                              reviewed rule is strict.  It fires in fewer
                              situations and concludes no more, so admitting it
                              cannot license anything the reviewed rule does not
      different_representation the same rule written in another predicate
                              family.  NOT equality: the two do not interact in
                              the prover, and the difference is reported
      unsafe_generalization   broader or stronger: a reviewed antecedent
                              dropped, a reviewed constant turned into a
                              variable, or a reviewed default promoted to strict
      incompatible            reversed, arguments swapped, or a conclusion that
                              is not the reviewed one

    The asymmetry is deliberate.  Extra conditions and grounded constants make a
    rule weaker; missing conditions and strict promotion make it stronger. Only
    the second kind can license a conclusion the reviewer did not sanction.
    """
    ce = compare(rule_pkg, gold_pkg, mode="exact")
    if not ce.get("comparable"):
        return _cls("incompatible", [ce.get("why")], ce, None,
                    {"not_a_rule": True})
    cr = compare(rule_pkg, gold_pkg, mode="representation")
    cp = compare(rule_pkg, gold_pkg, mode="permuted")
    why, flags = [], {}

    if cr["direction"] == "reversed" or cp["direction"] == "reversed":
        why.append("the rule concludes what the reviewed rule assumes")
        return _cls("incompatible", why, ce, cr, {"reversed": True})
    if cr["direction"] != "forward":
        why.append("the conclusion is not the reviewed rule's conclusion "
                   "(compiled %s, reviewed %s)"
                   % (ce["compiled"]["consequent"], ce["reviewed"]["consequent"]))
        return _cls("incompatible", why, ce, cr, {"consequent_unmatched": True})

    permuted = ("permuted" in (cp.get("matched_antecedent_kinds") or [])
                or cp.get("consequent_match_kind") == "permuted")
    if permuted and cr["missing_antecedents"]:
        why.append("an atom matches the reviewed rule only with its arguments "
                   "in the other order")
        return _cls("incompatible", why, ce, cr, {"arguments_swapped": True})

    if cr["generalizations"]:
        for n in cr["generalizations"]:
            why.append("the reviewed rule names %s where this one quantifies %s"
                       % (n["reviewed"], n["compiled"]))
        flags["variable_generalization"] = True
    if cr["missing_antecedents"]:
        why.append("the reviewed rule requires %s, which this one does not"
                   % "; ".join(cr["missing_antecedents"]))
        flags["missing_antecedents"] = cr["missing_antecedents"]
    if ce["strength_compiled"] == STRICT and ce["strength_reviewed"] == DEFAULT:
        why.append("a reviewed defeasible rule is compiled strict")
        flags["strict_promotion"] = True
    if flags:
        return _cls("unsafe_generalization", why, ce, cr, flags)

    if ce["all_components_correct"]:
        return _cls("exact", ["the same rule up to bound-variable renaming"],
                    ce, cr, {})

    if cr["specializations"]:
        why.append("narrowed to %s where the reviewed rule quantifies"
                   % ", ".join(sorted(set(str(n["compiled"])
                                          for n in cr["specializations"]))))
        flags["constant_specialization"] = True
    if cr["extra_antecedents"]:
        why.append("carries the extra condition %s"
                   % "; ".join(cr["extra_antecedents"]))
        flags["extra_antecedents"] = cr["extra_antecedents"]
    if ce["strength_compiled"] == DEFAULT and ce["strength_reviewed"] == STRICT:
        why.append("defeasible where the reviewed rule is strict, which is "
                   "weaker, not broader")
        flags["strength_reduced"] = True
    family = "predicate_family_differs" in (
        cr.get("matched_antecedent_kinds") or []) or \
        cr.get("consequent_match_kind") == "predicate_family_differs"
    if family:
        flags["predicate_family_differs"] = True
        why.append("written in a different predicate family from the reviewed "
                   "rule; the two do not meet in the prover")
    if not flags:
        # nothing unsafe, nothing narrowing, yet not exact: report rather than
        # invent a class
        return _cls("safe_specialization",
                    why + ["differs from the reviewed rule only in ways the "
                           "exact comparison records"], ce, cr, {})
    if family and set(flags) == {"predicate_family_differs"}:
        return _cls("different_representation", why, ce, cr, flags)
    return _cls("safe_specialization", why, ce, cr, flags)


def _cls(name, why, ce, cr, flags):
    assert name in CLASSES
    return {"classification": name, "why": why, "flags": flags,
            "safe": name in SAFE_CLASSES,
            "exact_components": components(ce),
            "exact": ce, "representation": cr}


# ---------------------------------------------------------------- superseded

def legacy_antecedent_measure(antecedent_ids, gold_producer_ids, allowed_ids):
    """The measurement this module replaces.  Used only by its own fixture.

    It asks whether ANY named antecedent is in a broad set of occurrences whose
    content label matches the reviewed rule's producer side, and whether every
    named antecedent was on the menu.  It cannot see a dropped condition, an
    extra condition, the direction, the argument map or the strength.
    """
    return bool(set(antecedent_ids) & set(gold_producer_ids)) and all(
        i in allowed_ids for i in antecedent_ids)
