"""A general operator: one binary relation written as another, either order.

    source: R(X, D)      target: S(?, ?)      mapping: target.1 = source.2
                                                       target.2 = source.1

    R(X, D)  ->  S(D, X)

eb2-0020 needs `part of(X,D) -> have(D,X)` and the library had no way to say
it: `role_or_relation_projection` maps one relation to another, but the argument
order it produces is a by-product of the plan rather than a declared,
replayable claim.  Here the mapping IS the claim.  Every plan carries the
mapping it used, and `verify_mapping` replays it against the head that was
built; a plan whose head does not match its own declaration is refused rather
than shipped.

What this does NOT assume:

  * that every relation has an inverse.  The reversed mapping is offered as an
    explicit alternative, marked `argument_order: reversed`, and whether it is
    true of these two relations is a question for admission AFTER a proof, not
    a property of the operator;
  * that the two relations mean the same thing.  Nothing here checks or claims
    that; the operator only writes the implication down;
  * that reversal is the interesting case.  The same-order mapping is emitted
    too, and remains separately available.

No relation name and no case identifier is written here.
"""

import construction_forms as CF
import construction_operators as CO
import construction_slots as CS

VERSION = "operator_inverse_relation/1.0"
NAME = "inverse_relation_projection"

SAME_ORDER = "same_order"
REVERSED = "reversed"

SUMMARY = ("One binary relation restated as another, with the argument mapping "
           "made explicit: `R(X, D)` gives `S(X, D)` or `S(D, X)`, and the "
           "mapping belongs to the rule rather than being a side effect.")
NOTE = ("the mapping is declared and replayed; a reversed mapping is an "
        "explicit alternative, not an assumption that the relation has an "
        "inverse")

# The encoding's binary predicate families.  These are predicates of the
# representation — like `isa` elsewhere in the library — not a choice about any
# case: a two-place conclusion has to be written in one of them.
BINARY_OUTPUT_FAMILIES = ("is rel2", "have")

MAPPINGS = (
    (SAME_ORDER, ((1, 1), (2, 2)),
     "target.1 = source.1, target.2 = source.2"),
    (REVERSED, ((1, 2), (2, 1)),
     "target.1 = source.2, target.2 = source.1"),
)


def target_relation(case, target):
    """-> (predicate, label, how) the target names, or None when not binary.

    The emitter receives a TARGET FORM — predicate, label, sign, arity — and
    that form calls a predicate binary only when its family is `is rel2`.  Some
    relations in this encoding are binary without being `is rel2` (`have` is
    one), so when the form says otherwise the group's own participants are
    consulted.  Nothing frozen is changed; the operator asks a second question
    instead of trusting one answer.
    """
    if not isinstance(target, dict):
        return None
    pred = target.get("predicate")
    label = target.get("label")
    if not pred:
        return None
    if target.get("arity") == 2:
        return pred, label, "the target form declares two arguments"
    for g in (case.get("by_gid") or {}).values():
        if g.get("predicate") != pred:
            continue
        if str(g.get("label")) != str(label):
            continue
        if len(g.get("participants") or []) == 2:
            return pred, label, ("the target form said one argument; the "
                                 "group it came from has two")
    return None


def verify_mapping(source_args, head_args, pairs):
    """Replay a declared mapping against the head that was built."""
    if len(head_args) != len(pairs):
        return False
    for (t_i, s_i), got in zip(pairs, head_args):
        if s_i - 1 >= len(source_args):
            return False
        if str(source_args[s_i - 1]) != str(got):
            return False
    return True


def emit(case, target, f):
    """-> one plan per declared mapping, each carrying and passing its own."""
    occ = f["source"][0]
    parts = CS._parts(occ)
    if len(parts) != 2:
        raise CS.SlotError("slot `source`: %s is not a two-place relation"
                           % occ["occurrence_id"])
    got = target_relation(case, target)
    if got is None:
        raise CS.SlotError("the target does not name a two-place relation")
    pred, label, arity_from = got
    src_label = occ.get("label")
    if pred == occ["predicate"] and str(label) == str(src_label):
        raise CS.SlotError("slot `source`: that is the target relation itself")
    plans = []
    for name, pairs, said in MAPPINGS:
        args = [parts[s_i - 1] for _t_i, s_i in pairs]
        spec = CS._atom_spec(pred, label, [(occ, a) for a in args])
        if not verify_mapping(parts, args, pairs):
            continue                      # a declaration its own head refutes
        plans.append(CS._plan(
            [CS._occ_item(occ)], spec,
            "%s, %s" % (occ["occurrence_id"], said),
            argument_order=name,
            declared_mapping=said,
            mapping_pairs=[list(p) for p in pairs],
            source_relation=str(src_label or occ["predicate"]),
            target_relation=str(label or pred),
            target_arity_established_by=arity_from,
            reversal_is_an_explicit_alternative=(name == REVERSED)))
    if not plans:
        raise CS.SlotError("no declared mapping survived its own replay")
    return plans


SPEC = CS.op(
    NAME, SUMMARY,
    [CS.slot("source", True, CS.form_two_place,
             "the two-place relation atom to restate; its arguments are "
             "mapped onto the target relation's in a declared order"),
     CS.GUARDS],
    CS.BIDIRECTIONAL,
    "the target relation with the source's two arguments, in the declared "
    "order",
    note=NOTE)


def enumerate_extra(case):
    """Every (binary relation atom, target) pair this operator could use."""
    out = []
    for oid, occ in (case.get("by_oid") or {}).items():
        if len(CS._parts(occ)) != 2:
            continue
        for tid in CS.known_targets(case):
            out.append({"operator": NAME, "target": tid,
                        "roles": {"source": [oid]}, "sources": []})
    return out


def register():
    """Add the operator to the live library.  Idempotent."""
    if NAME in CS.BY_NAME:
        return False
    CS.OPERATORS.append(SPEC)
    CS.BY_NAME[NAME] = SPEC
    CS.NAMES = tuple(o["name"] for o in CS.OPERATORS)
    CS.ROLE_NAMES = sorted(set(s["name"] for o in CS.OPERATORS
                               for s in o["slots"]))
    CS.EMITTERS[NAME] = emit
    CF.OUTPUT_FORMS[NAME] = {"forms": [(fam, 2)
                                       for fam in BINARY_OUTPUT_FAMILIES]}
    CF._ANCHOR_SLOT[NAME] = "source"
    import construction_provenance as CP
    CP.register_enumerator(NAME, enumerate_extra)
    return True


def unregister():
    if NAME not in CS.BY_NAME:
        return False
    CS.OPERATORS[:] = [o for o in CS.OPERATORS if o["name"] != NAME]
    del CS.BY_NAME[NAME]
    CS.NAMES = tuple(o["name"] for o in CS.OPERATORS)
    CS.ROLE_NAMES = sorted(set(s["name"] for o in CS.OPERATORS
                               for s in o["slots"]))
    CS.EMITTERS.pop(NAME, None)
    CF.OUTPUT_FORMS.pop(NAME, None)
    CF._ANCHOR_SLOT.pop(NAME, None)
    import construction_provenance as CP
    CP.unregister_enumerator(NAME)
    return True
