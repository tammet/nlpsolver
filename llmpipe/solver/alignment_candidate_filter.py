"""Route mechanically-surviving candidate pairs, and collapse them to schemas.

Three things the 08-10 pilot got wrong, and this fixes:

  * it offered **ordinary proof steps** as missing abstractions.  A pair whose
    two signed literals already unify needs no rule; it needs the prover to take
    a step it can already take.
  * it offered links **an existing rule already states**.  folio-0183's
    `nice to animals -> not mean to animals` is written in the problem.
  * it ran the **same rule twice** as two worlds, because two different
    occurrence pairs compile to one rule.

So every surviving pair gets a status —

    ordinary_unification | already_encoded_by_rule | candidate_abstraction

— and the remaining ones are collapsed into canonical **schemas**: one signed
rule, however many occurrence pairs produce it.

Nothing is deleted.  A routed-out pair stays in the diagnostics with its reason,
because a wrong filter is worse than an extra probe: when the encoded-by-rule
check is not certain, the pair stays a candidate.
"""

import collections
import json

import alignment_candidates as AC
import alignment_occurrences as AO
import alignment_rule as AR
import formula_print as FP

STATUSES = ("ordinary_unification", "already_encoded_by_rule",
            "candidate_abstraction")


# ---------------------------------------------------------------- signatures

def _sig(lit):
    """(sign, predicate, content label, arity) — a conservative signature."""
    neg = isinstance(lit, list) and lit and lit[0] == "not"
    atom = lit[1] if neg else lit
    if not (isinstance(atom, list) and atom and isinstance(atom[0], str)):
        return None
    pred, args = atom[0], atom[1:]
    slot = AO.LABEL_SLOT.get(pred)
    label = args[slot] if (slot is not None and slot < len(args)) else pred
    return ("-" if neg else "+", pred,
            AO.normalize_label(label) if isinstance(label, str) else str(label),
            len(args))


def occurrence_sig(occ):
    return _sig(AO.signed_literal(occ))


# ---------------------------------------------------------------- ordinary

def _terms(occ):
    args = occ.get("arguments_or_roles") or []
    slot = AO.LABEL_SLOT.get(occ.get("predicate"))
    return [a for i, a in enumerate(args) if i != slot]


def unify_terms(left, right):
    """A conservative identity filter over two aligned term lists.

    NOT a complete unifier, and not used as one: it keeps a substitution per
    side and never propagates a variable-variable constraint that a later
    constant would solve, so it can answer "not identical" where a real unifier
    would answer "unifiable".  That direction is the safe one for its only
    caller, `is_ordinary`, which uses it to decide whether a pair is plain
    instantiation and needs no abstraction at all: refusing to call something
    ordinary costs one probe, calling it ordinary wrongly loses the abstraction.

    Both sides may carry variables and both may repeat one, so `r(a,b)` does not
    match `r(X,X)` — X would have to be both `a` and `b` — and `r(X,X)` does not
    match `r(a,b)` either.  The signature-only version accepted both.

    Routing a candidate out against an existing rule is a different question
    with a direction to it; that is `already_encoded`, which does its own
    one-sided subsumption.

    -> (ok, why, substitution)
    """
    if len(left) != len(right):
        return False, "different arity", {}
    subL, subR = {}, {}
    for a, b in zip(left, right):
        av, bv = AO._is_var(a), AO._is_var(b)
        ka = a if av else AO.normalize_label(a) if isinstance(a, str) \
            else json.dumps(a, sort_keys=True)
        kb = b if bv else AO.normalize_label(b) if isinstance(b, str) \
            else json.dumps(b, sort_keys=True)
        if av and bv:
            if subL.setdefault(a, kb) != kb or subR.setdefault(b, ka) != ka:
                return False, "a variable would have to be two things", {}
        elif av:
            if subL.setdefault(a, kb) != kb:
                return False, "%s would have to be two things" % a, {}
        elif bv:
            if subR.setdefault(b, ka) != ka:
                return False, "%s would have to be two things" % b, {}
        else:
            if ka != kb:
                return False, "two different constants in one position", {}
    return True, "the terms unify", {"left": subL, "right": subR}


def is_ordinary(p, c):
    """Do the two signed literals unify directly under the pair's mapping?

    Variable renaming and ground instantiation are ordinary.  A change of
    predicate family, content label, arity or polarity is not, an argument swap
    is not, and neither is a position that would have to identify two different
    constants OR a repeated variable that would have to be two things.
    """
    sp, sc = occurrence_sig(p), occurrence_sig(c)
    if sp is None or sc is None or sp != sc:
        return False, "different signature: %s vs %s" % (sp, sc)
    mapping, swapped = AC.argument_mappings(p, c)
    if not mapping or swapped:
        return False, "no order-preserving argument correspondence"
    pt, ct = _terms(p), _terms(c)
    if len(mapping) != len(pt) or len(mapping) != len(ct):
        return False, "the correspondence does not cover every participant"
    ok, why, _ = unify_terms([a for a, _ in mapping], [b for _, b in mapping])
    if not ok:
        return False, why
    return True, "the two literals unify directly"


# ---------------------------------------------------------------- encoded

def rule_edges(stage2):
    """Signed antecedent/consequent LITERALS of every explicit implication.

    Conservative on purpose: it reads the implications the parse actually
    wrote, and makes no attempt to chain them.  This is routing, not proving.

    Complete literals, not signatures: the audit's §6.2 showed that comparing
    only (sign, predicate, label, arity) lets a rule `p(X,Y) -> q(Y,X)` route out
    an unrelated candidate `p(X,Y) -> q(X,Y)`.
    """
    out = []

    def walk(node, unit, polarity):
        if not isinstance(node, list) or not node:
            return
        head = node[0]
        if not isinstance(head, str):
            for ch in node:
                walk(ch, unit, polarity)
            return
        if head == "not" and len(node) == 2:
            walk(node[1], unit, "-" if polarity == "+" else "+")
            return
        if head == "implies" and len(node) == 3:
            ants = _conjunct_literals(node[1], polarity)
            cons = _conjunct_literals(node[2], polarity)
            if ants and cons:
                out.append({"unit": unit, "antecedents": ants,
                            "consequents": cons})
            walk(node[1], unit, polarity)
            walk(node[2], unit, polarity)
            return
        if head in AO.LOGICAL_HEADS:
            for ch in node[1:]:
                walk(ch, unit, polarity)
            return

    for uid, pkg in AO.packages(stage2):
        walk(pkg, uid, "+")
    return out


def _conjunct_literals(node, polarity):
    """The complete signed atoms in one side of an implication."""
    out = []

    def walk(n, pol):
        if not isinstance(n, list) or not n:
            return
        head = n[0]
        if not isinstance(head, str):
            return
        if head == "not" and len(n) == 2:
            walk(n[1], "-" if pol == "+" else "+")
            return
        if head in AO.LOGICAL_HEADS:
            for ch in n[1:]:
                if isinstance(ch, list):
                    walk(ch, pol)
            return
        out.append(n if pol == "+" else ["not", n])
    walk(node, polarity)
    return out


def _split(lit):
    """(sign, predicate, participants, label) of a signed literal."""
    neg = isinstance(lit, list) and lit and lit[0] == "not"
    atom = lit[1] if neg else lit
    pred, args = atom[0], list(atom[1:])
    slot = AO.LABEL_SLOT.get(pred)
    label = args[slot] if (slot is not None and slot < len(args)) else pred
    parts = [a for i, a in enumerate(args) if i != slot]
    return ("-" if neg else "+"), pred, parts, label


def _shape_ok(rule_lit, cand_lit):
    """Same sign, predicate, content label and participant count."""
    sa, pa, ta, la = _split(rule_lit)
    sb, pb, tb, lb = _split(cand_lit)
    if sa != sb or pa != pb or len(ta) != len(tb):
        return False
    if AO.normalize_label(str(la)) != AO.normalize_label(str(lb)):
        return False
    for x, y in zip(ta, tb):
        if not AO._is_var(x) and not AO._is_var(y):
            kx = AO.normalize_label(x) if isinstance(x, str) else \
                json.dumps(x, sort_keys=True)
            ky = AO.normalize_label(y) if isinstance(y, str) else \
                json.dumps(y, sort_keys=True)
            if kx != ky:
                return False
    return True


def link_pattern(a, b):
    """Which positions of two literals carry the same term.

    This is what makes `p(X,Y) -> q(Y,X)` a different rule from
    `p(X,Y) -> q(X,Y)`: the first links antecedent position 0 to conclusion
    position 1, the second links 0 to 0.  Comparing signatures could not see it
    (audit 6.2).
    """
    _, _, ta, _ = _split(a)
    _, _, tb, _ = _split(b)

    def key(t):
        return ("v", t) if AO._is_var(t) else (
            "c", AO.normalize_label(t) if isinstance(t, str)
            else json.dumps(t, sort_keys=True))
    return set((i, j) for i, x in enumerate(ta) for j, y in enumerate(tb)
               if key(x) == key(y))


def candidate_link_positions(p, c):
    """The positions the pipeline would identify for this pair.

    The producer and consumer come from DIFFERENT packages, so a shared
    variable NAME across them means nothing and a different one means nothing
    either.  The only real cross-literal link is the argument mapping the
    candidate already carries — which is also the mapping the compiler will
    use — so that is what the rule's own link pattern is compared against.
    """
    mapping, swapped = AC.argument_mappings(p, c)
    if not mapping:
        return set()
    n = len(mapping)
    if swapped and n == 2:
        return {(0, 1), (1, 0)}
    return set((i, i) for i in range(n))


def candidate_skeleton(p, c):
    """The candidate link as two rigid literals.

    The producer and consumer come from different packages, so their variable
    NAMES carry no shared meaning.  What is real is the argument mapping: the
    positions the compiler will identify.  Linked positions become one rigid
    symbol, everything else becomes a distinct one, and constants stay
    themselves.  Matching against rigid symbols is what makes the subsumption
    test below directional.
    """
    ps, pp, pt, pl_ = _split(AO.signed_literal(p))
    cs, cp, ct, cl_ = _split(AO.signed_literal(c))
    links = candidate_link_positions(p, c)
    pkey, ckey = [], []
    for i, t in enumerate(pt):
        pkey.append(("c", AO.normalize_label(t)) if not AO._is_var(t)
                    and isinstance(t, str) else ("p", i))
    for j, t in enumerate(ct):
        src = [i for (i, jj) in links if jj == j and i < len(pkey)]
        if src:
            ckey.append(pkey[src[0]])
        elif isinstance(t, str) and not AO._is_var(t):
            ckey.append(("c", AO.normalize_label(t)))
        else:
            ckey.append(("k", j))
    return ((ps, pp, AO.normalize_label(str(pl_)), pkey),
            (cs, cp, AO.normalize_label(str(cl_)), ckey))


def _subsumes_literal(rule_lit, skel, sub):
    """Does the rule literal cover this rigid skeleton under `sub`?

    `sub` maps the RULE's variables to skeleton keys.  Only the rule's variables
    move; the skeleton is rigid.  That asymmetry is the whole point: a general
    rule covers a grounded candidate, and a rule about `a` does not cover a
    candidate about everything.
    """
    sign, pred, parts, label = _split(rule_lit)
    s2, p2, l2, keys = skel
    if sign != s2 or pred != p2 or len(parts) != len(keys):
        return None
    if AO.normalize_label(str(label)) != l2:
        return None
    out = dict(sub)
    for t, k in zip(parts, keys):
        if AO._is_var(t):
            if out.setdefault(t, k) != k:
                return None
        else:
            kt = ("c", AO.normalize_label(t)) if isinstance(t, str) \
                else ("j", json.dumps(t, sort_keys=True))
            if kt != k:
                return None
    return out


def already_encoded(p, c, edges):
    """Is this link already written as one of the problem's own rules?

    The test is DIRECTIONAL: does an existing rule SUBSUME this candidate, under
    one consistent substitution of the existing rule's variables?

      existing p(X) -> q(X)   routes out candidate p(a) -> q(a)
      existing p(a) -> q(a)   does NOT route out candidate p(X) -> q(X)

    The second is the audit's §4: a rule local to `a` does not already encode a
    general rule, and treating it as though it did silently deletes the general
    candidate.  One substitution covers both literals at once, so repeated
    variables, constants, argument order and the cross-literal link are all
    checked together — `p(X,Y) -> q(Y,X)` cannot cover `p(X,Y) -> q(X,Y)`.

    When subsumption is uncertain the candidate is retained: a false route-out
    loses a real abstraction, an extra probe costs one gk call.
    """
    pskel, cskel = candidate_skeleton(p, c)
    for e in edges:
        for ant in e["antecedents"]:
            sub = _subsumes_literal(ant, pskel, {})
            if sub is None:
                continue
            for con in e["consequents"]:
                if _subsumes_literal(con, cskel, sub) is None:
                    continue
                others = [a for a in e["antecedents"] if a is not ant]
                return True, {"unit": e["unit"],
                              "other_premises": [FP.formula(a) for a in others],
                              "matched_antecedent": FP.formula(ant),
                              "matched_conclusion": FP.formula(con),
                              "subsumption": "the existing rule covers this "
                                             "candidate under one substitution"}
    return False, None


# ---------------------------------------------------------------- schemas

def canonical_rule(p_id, c_id, table, target_mode=None):
    """The signed base rule this pair would compile into with no conditions.

    Produced by the real compiler, so the canonical form preserves exactly what
    the compiler preserves — signs, participant order, constants, predicate
    family, target mode — and normalises exactly what it normalises: bound
    variable names.
    """
    pkg, rec = AR.compile_from_base(p_id, c_id, [], table,
                                    target_mode=target_mode)
    return FP.formula(pkg), pkg, rec


def build(gen, stage2, table=None):
    """-> {"schemas": [...], "routed": [...], "counts": {...}}."""
    table = table or gen["table"]
    by_id = table["by_id"]
    edges = rule_edges(stage2)
    routed, schemas = [], collections.OrderedDict()
    counts = collections.Counter()
    for i, row in enumerate(gen["candidates"], start=1):
        cid = "K%d" % i
        p, c = by_id[row["producer"]], by_id[row["consumer"]]
        ordinary, why = is_ordinary(p, c)
        if ordinary:
            counts["ordinary_unification"] += 1
            routed.append({"candidate_id": cid, "status": "ordinary_unification",
                           "why": why, "producer": row["producer"],
                           "consumer": row["consumer"]})
            continue
        enc, detail = already_encoded(p, c, edges)
        if enc:
            counts["already_encoded_by_rule"] += 1
            routed.append({"candidate_id": cid,
                           "status": "already_encoded_by_rule",
                           "why": "%s already states this link" % detail["unit"],
                           "detail": detail, "producer": row["producer"],
                           "consumer": row["consumer"]})
            continue
        counts["candidate_abstraction"] += 1
        # A question consumer supports two hypotheses — supply it, or derive its
        # complement and refute it — and they are different rules.  Both are
        # built; the mode is part of the schema key and visible in the formula.
        for mode in AR.target_modes_for(c):
            try:
                printed, pkg, rec = canonical_rule(
                    row["producer"], row["consumer"], table, target_mode=mode)
            except AR.RuleError as e:
                counts["not_compilable"] += 1
                routed.append({"candidate_id": cid, "status": "not_compilable",
                               "target_mode": mode, "why": str(e),
                               "producer": row["producer"],
                               "consumer": row["consumer"]})
                continue
            # Keyed on the compiled formula, not on (mode, formula): two modes
            # can reach the same rule — supplying one consumer and refuting
            # another are different reasons to want one axiom, and gk would see
            # one axiom either way.  The reasons are kept in `target_modes`.
            key = printed
            s = schemas.get(key)
            if s is None:
                s = {"schema_id": "H%d" % (len(schemas) + 1),
                     "canonical_signed_rule": printed,
                     "target_mode": mode,
                     "target_modes": [],
                     # WP1: how this formula was built.  Probe and refined
                     # compilation must replay THIS, not re-derive the mode from
                     # the consumer — otherwise the runtime can send gk a rule
                     # with the opposite head from the one displayed.
                     "construction_witness": {
                         "producer": row["producer"],
                         "consumer": row["consumer"],
                         "target_mode": mode,
                         "compiled_base_formula": printed},
                     "witnesses": [],
                     "stage2_rule": pkg,
                     "member_candidate_ids": [],
                     "producer_occurrences": [], "consumer_occurrences": [],
                     "source_evidence": [],
                     "argument_correspondence": rec.get("unified_positions"),
                     "grounded_positions": rec.get("grounded_positions") or {},
                     "unbound_conclusion_variables":
                         rec.get("unbound_conclusion_variables") or [],
                     "structurally_unsafe_probe":
                         bool(rec.get("unbound_conclusion_variables")),
                     "polarity": {"producer": AO.literal_sign(p),
                                  "consumer": AO.literal_sign(c)},
                     "features": row.get("features")}
                schemas[key] = s
            if mode not in s["target_modes"]:
                s["target_modes"].append(mode)
            w = {"producer": row["producer"], "consumer": row["consumer"],
                 "target_mode": mode, "compiled_base_formula": printed}
            if w not in s["witnesses"]:
                s["witnesses"].append(w)
            s["member_candidate_ids"].append(cid)
            if row["producer"] not in s["producer_occurrences"]:
                s["producer_occurrences"].append(row["producer"])
            if row["consumer"] not in s["consumer_occurrences"]:
                s["consumer_occurrences"].append(row["consumer"])
            ev = {"producer_unit": p["unit_id"], "consumer_unit": c["unit_id"],
                  "producer_phrase": p.get("source_quote"),
                  "consumer_phrase": c.get("source_quote"),
                  "producer_position": _position(p),
                  "consumer_position": _position(c)}
            if ev not in s["source_evidence"]:
                s["source_evidence"].append(ev)
    out = list(schemas.values())
    counts["unique_schemas"] = len(out)
    counts["supply_schemas"] = sum(
        1 for s in out
        if any(m != "contradict_question" for m in s["target_modes"]))
    counts["contradict_question_schemas"] = sum(
        1 for s in out if "contradict_question" in s["target_modes"])
    counts["schemas_wanted_for_two_reasons"] = sum(
        1 for s in out if len(s["target_modes"]) > 1)
    counts["structurally_unsafe_schemas"] = sum(
        1 for s in out if s["structurally_unsafe_probe"])
    counts["duplicate_members_collapsed"] = (
        sum(len(s["member_candidate_ids"]) for s in out) - len(out))
    counts["raw_pairs"] = len(gen["candidates"])
    return {"schemas": out, "routed": routed, "counts": dict(counts),
            "rule_edges": len(edges)}


def _position(o):
    if o.get("in_question"):
        return "question goal" if o["rule_side"] != "antecedent" \
            else "question assumption"
    return {"antecedent": "rule premise", "conclusion": "rule conclusion"}.get(
        o["rule_side"], "fact")
