"""A general operator: being in a named category, and being of its type.

    R(X, C)   ->   isa(K, X)      or      has type(X, K)

`R` is a membership- or containment-like relation, `C` is a named category, and
`K` is the type word taken from `C`'s own source label.  eb2-0020 needs exactly
this — "the organisms in the kingdom animalia are animals" — and nothing in the
library could build it, but the operator is written for the pattern, not for
that case: no case id, no `Animal`, no `animal` appears here.

What it will and will not do:

  * `K` comes from the category argument's SOURCE LABEL, normalised the way
    every other label is, and both the phrase and its normalisation are
    recorded on the plan.  Nothing is invented from the predicate or the target;
  * the member is the FIRST argument.  `R(C, X)` is not read as membership with
    the arguments the other way round — that is a different claim, and the
    reversed fixture asserts it is refused;
  * a category with no usable label — a variable, a skolem, converter
    machinery, a bare number — is refused, naming the slot;
  * containment relations that are ordinarily PHYSICAL (`in`, `at`, `inside`)
    still build, because "in the kingdom animalia" is written with the same
    predicate as "in France", and no mechanical test separates them.  Those
    plans carry a `physical_location_reading_possible` warning, and the pilot
    treats such a candidate as speculative rather than dropping it.

Registration is explicit.  The frozen ten-operator library is unchanged until a
program calls `register()`, so earlier runs and their hashes stand.
"""

import construction_forms as CF
import construction_operators as CO
import construction_slots as CS

VERSION = "operator_category_membership/1.0"
NAME = "category_membership_projection"

# Relations that can carry membership in a named category.  `part of` and `in`
# are here because passages use them that way ("animals are a part of the
# kingdom animalia", "the organisms in the kingdom animalia"); the ones that
# read as physical containment are marked, not excluded.
MEMBERSHIP_RELATIONS = ("member of", "belong to", "belongs to", "in",
                        "part of", "within", "inside", "at", "of")
PHYSICAL_READING = ("in", "at", "inside", "within")

SUMMARY = ("Being in, a member of, or part of a NAMED CATEGORY, read as being "
           "of that category's type: `R(X, C)` gives `isa(<C's word>, X)`.")
NOTE = ("the category's word comes from its own source label and nothing else; "
        "a containment relation that may be read as a physical location is "
        "built but marked")


def _usable_label(term):
    """-> (phrase, normalised word) for a category argument, or None.

    A category has to name something.  A variable, a skolem, a converter term
    or a control word does not, and the operator refuses rather than inventing
    a word for it.
    """
    if not isinstance(term, str) or not term.strip():
        return None
    kind = CS.term_type(term)
    if kind in (CS.VARIABLE, CS.MACHINERY, CS.CONTROL):
        return None
    phrase = term
    if "/" in term:                       # a URL entity: its last path segment
        tail = [p for p in term.rstrip("/").split("/") if p]
        if not tail:
            return None
        phrase = tail[-1].replace("_", " ")
    word = CO.normalize(phrase)
    if not word or not any(c.isalpha() for c in word):
        return None
    return phrase, word


def emit(case, target, f):
    """-> plans.  The head's word is the category's, not the target's."""
    occ = f["membership"][0]
    parts = CS._parts(occ)
    if len(parts) != 2:
        raise CS.SlotError("slot `membership`: %s does not have two "
                           "participants" % occ["occurrence_id"])
    relation = CO.normalize(occ.get("label") or occ["predicate"])
    if relation not in MEMBERSHIP_RELATIONS:
        raise CS.SlotError("slot `membership`: %r is not a membership or "
                           "containment relation" % relation)
    member, category = parts[0], parts[1]
    got = _usable_label(category)
    if got is None:
        raise CS.SlotError("slot `membership`: the second argument %r carries "
                           "no usable category label" % (category,))
    phrase, word = got
    if CS.term_type(member) not in (CS.VARIABLE, CS.INDIVIDUAL, CS.CONCEPT):
        raise CS.SlotError("slot `membership`: the first argument %r cannot be "
                           "a member" % (member,))
    if CO.normalize(member) == word:
        raise CS.SlotError("slot `membership`: the member and the category are "
                           "the same word")
    physical = relation in PHYSICAL_READING
    plans = []
    for pred, spec in (("isa", CS._atom_spec("isa", word, [(occ, member)])),
                       ("has type",
                        CS._atom_spec("has type", word, [(occ, member)]))):
        plans.append(CS._plan(
            [CS._occ_item(occ)], spec,
            "the category argument %r of %s supplies the type word %r"
            % (phrase, occ["occurrence_id"], word),
            category_source_phrase=phrase,
            category_normalized_word=word,
            head_predicate_synthesized_from="the category argument, not the "
                                            "target",
            membership_relation=relation,
            physical_location_reading_possible=physical,
            warning=("this relation can also be read as a physical location, "
                     "which would not license a type" if physical else None)))
    return plans


SPEC = CS.op(
    NAME, SUMMARY,
    [CS.slot("membership", True, CS.form_two_place,
             "the `R(member, category)` atom: its FIRST argument is the "
             "prospective member and its second names the category"),
     CS.GUARDS],
    CS.FIXED, "isa(<the category's word>, member) or has type(member, <word>)",
    note=NOTE)


def enumerate_extra(case):
    """Every (membership atom, target) pair this operator could use."""
    out = []
    for oid, occ in (case.get("by_oid") or {}).items():
        if len(CS._parts(occ)) != 2:
            continue
        relation = CO.normalize(occ.get("label") or occ["predicate"])
        if relation not in MEMBERSHIP_RELATIONS:
            continue
        for tid in CS.known_targets(case):
            out.append({"operator": NAME, "target": tid,
                        "roles": {"membership": [oid]}, "sources": []})
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
    CF.OUTPUT_FORMS[NAME] = {"forms": [("isa", 1), ("has type", 1)]}
    CF._ANCHOR_SLOT[NAME] = "membership"
    import construction_provenance as CP
    CP.register_enumerator(NAME, enumerate_extra)
    return True


def unregister():
    """Put the library back as it was.  For tests that assert the frozen ten."""
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
