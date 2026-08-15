"""A small fixed library of abstraction-rule construction operators.

The previous round asked a model to pick which semantic expression the prover
needed (AL-67).  Picking is not building: a selected group says *where* the two
halves of the problem fail to meet, not *what rule* would join them.  This
module is the deterministic half of building.  A model names four things —

    a target, some source occurrences, one operator, optional conditions

— and code does everything else: it chooses the argument mapping, connects the
variables, quantifies, checks, and emits a Stage-2 rule package.  **The model
never writes a quantified formula.**  That was tried in an earlier round and
produced right connections with wrong scope; naming is what a model is reliable
at, and the serialisation is what code is reliable at.

Each operator is declared, not improvised.  A spec fixes the source and target
forms it accepts, the direction it may run in, how the arguments connect, which
atoms may serve as conditions, the package it emits, and — as important as the
rest — the conditions under which it mechanically REFUSES.  An operator that
cannot express a construction says so; it never approximates one.

`typed_taxonomy` is the one operator that rests on a semantic judgment (is this
class a kind of that one), and the judgment is the model's, named by choosing
the operator.  `other_restructure` emits nothing at all: it is how the model
records that the construction it can see is outside this library, which is a
result and not a failure.

Nothing here reads a reviewed rule or an expected answer.
"""

import re

import alignment_occurrences as AO

VERSION = "construction_operators/1.0"

MAX_SOURCES = 3
MAX_CONDITIONS = 2
MAX_ALTERNATIVES = 5

# Predicates that carry content a rule may be built from.  Everything else —
# set machinery, world plumbing, modal classifiers — is refused as a source.
CONTENT_PREDICATES = {
    "isa", "has property", "has degree property", "is rel2", "has degree rel2",
    "has part", "have", "has type", "has actor", "has target", "has content",
    "has result", "has location",
}
# Predicate families that mean the same thing at different levels of detail.
# The degree form carries two extra arguments (the degree and the comparison
# class); it says everything the plain form says and more.
FAMILY = {
    "has degree property": "has property",
    "has degree rel2": "is rel2",
}
ROLE_PREDICATES = {"has actor", "has target", "has content", "has result",
                   "has location"}
EVENT_PREDICATES = {"has type"} | ROLE_PREDICATES
# Never a source, never a condition: the compiler's own scaffolding.
PLUMBING = {"member", "is set of", "$block", "state time", "isa activity",
            "typical", "capability", "necessity", "obligation", "volition",
            "intention", "expectation", "speech_act", "actuality"}


class ConstructionError(Exception):
    """The construction cannot be built.  Never worked around, never guessed."""


# ------------------------------------------------------------------ morphology

_SUFFIXES = ("ations", "ation", "ings", "ing", "ers", "er", "ors", "or",
             "ies", "ied", "ed", "es", "s", "ment", "ness", "ity", "ive",
             "ally", "ly", "al", "ic", "ary", "ous", "ful", "able", "ible")


def normalize(s):
    if not isinstance(s, str):
        return ""
    t = re.sub(r"\s+", " ", s.strip().lower())
    t = re.sub(r"^(the|a|an) ", "", t)
    t = re.sub(r"^#:", "", t)
    return re.sub(r" \d+$", "", t)


def tokens(label):
    return [t for t in normalize(label).replace("-", " ").split(" ") if t]


def stem(word):
    """A crude, deliberate stemmer.

    It exists to answer one mechanical question — could these two words be
    forms of one another — and it is allowed to be blunt about it, because the
    operator that uses it also has to satisfy a structural pattern.  It is
    never used to decide meaning.
    """
    w = normalize(word)
    for suf in sorted(_SUFFIXES, key=len, reverse=True):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[:-len(suf)]
            break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "aeiou":
        w = w[:-1]                      # running -> runn -> run
    if len(w) > 3 and w.endswith("e"):
        w = w[:-1]                      # love / lover / loving all -> lov
    return w


def morph_related(a, b):
    """True when two words are plausibly forms of one another."""
    x, y = normalize(a), normalize(b)
    if not x or not y:
        return False
    if x == y:
        return True
    if len(x) >= 3 and len(y) >= 3 and (x.startswith(y) or y.startswith(x)):
        return True
    sx, sy = stem(x), stem(y)
    return bool(sx) and sx == sy


def compound_parts(label):
    """`animal lover` -> (`animal`, `lover`).  None when not a compound."""
    ts = tokens(label)
    if len(ts) < 2:
        return None
    return (" ".join(ts[:-1]), ts[-1])


def label_related(a, b):
    """Whole-label relatedness: token-wise, last token by morphology."""
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if len(ta) == len(tb) and ta[:-1] == tb[:-1]:
        return morph_related(ta[-1], tb[-1])
    return morph_related(" ".join(ta), " ".join(tb))


# ------------------------------------------------------------------ literals

def pred_of(lit):
    lit = strip_neg(lit)
    return lit[0] if isinstance(lit, list) and lit else None


def strip_neg(lit):
    while isinstance(lit, list) and len(lit) == 2 and lit[0] == "not":
        lit = lit[1]
    return lit


def is_negated(lit):
    return isinstance(lit, list) and len(lit) == 2 and lit[0] == "not"


def family(pred):
    return FAMILY.get(pred, pred)


def label_index(pred):
    """Index INTO THE ARGUMENT LIST of the content label, or None."""
    return AO.LABEL_SLOT.get(pred)


def split_atom(atom):
    """-> (predicate, label or None, [participant positions as (index, term)])."""
    atom = strip_neg(atom)
    pred, args = atom[0], list(atom[1:])
    slot = label_index(pred)
    if pred == "has type":
        slot = 1
    label = args[slot] if (slot is not None and slot < len(args)) else None
    parts = [(i, a) for i, a in enumerate(args) if i != slot]
    return pred, label, parts


def occ_literal(occ):
    return AO.signed_literal(occ)


def usable_source(occ):
    """A content atom this library may build from."""
    pred = occ.get("predicate")
    if pred in PLUMBING or pred not in CONTENT_PREDICATES:
        return False
    args = occ.get("arguments_or_roles")
    if not isinstance(args, list) or not args:
        return False
    return all(isinstance(a, str) for a in args)


# ------------------------------------------------------------------ assembly

class Assembly(object):
    """Variable identification and rebuilding, shared by every operator.

    Terms are named by keys: a variable is ("var", unit, name) so two units
    cannot collide by accident, a constant is ("const", text) so the SAME
    constant in two atoms is the same thing.  An operator declares which keys
    are one thing; nothing is unified by luck.
    """

    def __init__(self, generalize=False):
        self.parent = {}
        self.generalize = generalize
        self.names = {}
        self.n = 0
        self.generalized_constants = []

    # union-find
    def _find(self, k):
        self.parent.setdefault(k, k)
        while self.parent[k] != k:
            self.parent[k] = self.parent[self.parent[k]]
            k = self.parent[k]
        return k

    def unify(self, a, b):
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            # a constant class absorbs a variable class, so a preserved
            # constant is never renamed away
            if ra[0] == "const" and rb[0] != "const":
                self.parent[rb] = ra
            else:
                self.parent[ra] = rb

    def key(self, unit, term):
        if AO._is_var(term):
            return ("var", unit, term)
        return ("const", term)

    def resolve(self, unit, term):
        if not isinstance(term, str):
            return term
        k = self._find(self.key(unit, term))
        if k[0] == "const" and not self.generalize:
            return k[1]
        if k[0] == "const":
            if k[1] not in self.generalized_constants:
                self.generalized_constants.append(k[1])
        if k not in self.names:
            self.n += 1
            self.names[k] = "V%d" % self.n
        return self.names[k]

    def rebuild(self, occ, force_positive=False):
        """The occurrence as a signed literal with its participants resolved.

        `force_positive` is never a default: it is used only by the operators
        that relate one WORD to another, where the sign of the place the word
        was found (a question's negation, say) is not part of the relation
        being stated.  Every other use keeps the occurrence's own polarity,
        because dropping it turns one rule into a different rule.
        """
        atom = AO.bare_atom(occ)
        pred = atom[0]
        slot = label_index(pred)
        if pred == "has type":
            slot = 1
        unit = occ["unit_id"]
        out = [pred]
        for i, a in enumerate(atom[1:]):
            if i == slot and isinstance(a, str) and AO._is_var(a):
                # a label position holding a VARIABLE is not content, it is a
                # variable, and it has to be freshened like any other
                out.append(self.resolve(unit, a))
            elif i == slot or not isinstance(a, str):
                out.append(a)
            else:
                out.append(self.resolve(unit, a))
        if force_positive:
            return out
        return ["not", out] if AO.literal_sign(occ) == "-" else out


def _vars_in(node, out=None):
    out = [] if out is None else out
    if isinstance(node, list):
        for x in node:
            _vars_in(x, out)
    elif isinstance(node, str) and AO._is_var(node) and node not in out:
        out.append(node)
    return out


def _contradicts(a, b):
    """Same content, opposite sign."""
    return (is_negated(a) != is_negated(b)
            and strip_neg(a) == strip_neg(b))


def package_of(body, head, world="W0", defeasible=True):
    """`forall vars . BODY -> normally(HEAD)`, quantified last.

    The one place a formula is written.  Quantification happens after every
    unification, over the variables that survive, in first-appearance order.
    """
    if not body:
        raise ConstructionError("a rule with no body is not a rule")
    inner = ["implies", body[0] if len(body) == 1 else ["and"] + list(body),
             ["normally", head] if defeasible else head]
    used = _vars_in(inner)
    f = inner
    for v in reversed(used):
        f = ["forall", v, f]
    return ["holds", world, f], used


# ------------------------------------------------------------------ specs

def _spec(name, **kw):
    kw["name"] = name
    return kw


OPERATOR_SPECS = [
    _spec(
        "compound_head",
        summary="Build a compound class from its head and its modifier: "
                "what a thing does or is, plus what the other participant is, "
                "makes it a `<modifier> <head>`.",
        source_forms=["one atom whose label supplies the compound's HEAD word "
                      "(a relation, an event, or a class)",
                      "one class atom whose label is the compound's MODIFIER",
                      "optionally one relation linking the modifier's "
                      "participant to the subject"],
        target_forms=["a class label of two or more words"],
        direction="parts -> compound (the compound is concluded)",
        argument_connection="the subject is the head source's first "
                            "participant; the modifier's participant is the "
                            "head source's other participant, or is joined to "
                            "the subject by the link atom",
        conditions="class or property atoms sharing a term with the rule",
        emits="isa(<modifier> <head>, subject)",
        refuses=["the target label is a single word",
                 "no source label is morphologically related to the head word",
                 "no source is a class atom whose label is the modifier",
                 "the modifier participant is joined to nothing"],
    ),
    _spec(
        "nominalization",
        summary="Relate a word to another form of the same word: a verb and "
                "its noun, an adjective and its noun.",
        source_forms=["any content atom"],
        target_forms=["a label morphologically related to the source label"],
        direction="source form -> target form",
        argument_connection="participants are carried in their own order",
        conditions="class or property atoms sharing a term with the rule",
        emits="the target predicate with the source's participants",
        refuses=["the two labels are not morphologically related",
                 "the target needs more participants than the source has"],
    ),
    _spec(
        "event_nominal_equivalence",
        summary="Turn a described event into the relation or property it "
                "amounts to: `E is a breaking, E's actor is x, E's target is "
                "y` becomes a relation between x and y.",
        source_forms=["a `has type` atom naming the event",
                      "one or two role atoms of the same event"],
        target_forms=["a relation label, or a property label"],
        direction="event -> nominal only; the reverse would invent an event",
        argument_connection="the actor becomes the first participant, the "
                            "target or content the second",
        conditions="class or property atoms sharing a term with the rule",
        emits="is rel2(<label>, actor, target) or has property(<label>, actor)",
        refuses=["the sources are not one event's type plus its roles",
                 "no role atom is given",
                 "the direction is nominal -> event"],
    ),
    _spec(
        "property_class_conversion",
        summary="Move between being a kind of thing and having a property: "
                "`isa(P, x)` and `has property(P, x)`.",
        source_forms=["a class atom, or a property atom"],
        target_forms=["the other form of the same label"],
        direction="either way",
        argument_connection="the bearer is carried unchanged",
        conditions="class or property atoms sharing a term with the rule",
        emits="the other predicate with the same label and bearer",
        refuses=["the labels differ", "the source has no single bearer"],
    ),
    _spec(
        "role_or_relation_projection",
        summary="Relate one two-place relation to another: same participants, "
                "different relation, possibly in the other order.",
        source_forms=["a two-place relation atom, or a role atom"],
        target_forms=["a two-place relation label"],
        direction="source relation -> target relation",
        argument_connection="participants in the same order, or swapped; both "
                            "are offered as alternatives",
        conditions="class or property atoms sharing a term with the rule",
        emits="is rel2(<target label>, a, b)",
        refuses=["the source does not have exactly two participants",
                 "the target label is the source label"],
    ),
    _spec(
        "predication_transfer",
        summary="Carry a predication from one participant to another along a "
                "stated link: what holds of the part holds of the whole, or "
                "the other way.",
        source_forms=["a class or property atom about one participant",
                      "a relation linking that participant to another"],
        target_forms=["the same predication about the other participant"],
        direction="along the link, in the direction the link is written",
        argument_connection="the predication's bearer must be one end of the "
                            "link; the conclusion is about the other end",
        conditions="class or property atoms sharing a term with the rule",
        emits="the same predicate and label, about the other participant",
        refuses=["the bearer is not an end of the link",
                 "no link atom is given"],
    ),
    _spec(
        "argument_label_promotion",
        summary="Promote a word that only ever appears as an argument into a "
                "class of its own: `x is a source of organic matter` makes "
                "`organic matter` something a thing can be.",
        source_forms=["an atom carrying the label in an ARGUMENT position",
                      "a class or property atom binding the subject"],
        target_forms=["that argument's word, as a class label"],
        direction="argument -> predicate label",
        argument_connection="the subject is the other participant of the "
                            "carrying atom",
        conditions="class or property atoms sharing a term with the rule",
        emits="isa(<promoted label>, subject)",
        refuses=["the label does not occur as an argument constant",
                 "the carrying atom has no other participant"],
    ),
    _spec(
        "label_variable_transport",
        summary="Carry a label that is itself a variable from one participant "
                "to another, without ever naming it.",
        source_forms=["an atom whose LABEL position holds a variable",
                      "a relation linking the two participants"],
        target_forms=["the same predicate with the same label variable"],
        direction="along the link",
        argument_connection="the label variable is shared; the bearer changes",
        conditions="class or property atoms sharing a term with the rule",
        emits="the same predicate, same label variable, other bearer",
        refuses=["the source label is a constant", "no link atom is given"],
    ),
    _spec(
        "typed_taxonomy",
        summary="One class or relation is a kind of another. This is the one "
                "operator that rests on your judgment about the words rather "
                "than on their shape.",
        source_forms=["a class atom, or a two-place relation atom"],
        target_forms=["a broader class label, or a broader relation label"],
        direction="specific -> general",
        argument_connection="participants carried in order",
        conditions="class or property atoms sharing a term with the rule",
        emits="the target predicate with the source's participants",
        refuses=["the target label equals the source label",
                 "the arities do not match"],
    ),
    _spec(
        "other_restructure",
        summary="The construction you can see is not in this library. Nothing "
                "is built; the case is recorded as unsupported.",
        source_forms=["any"], target_forms=["any"], direction="none",
        argument_connection="none", conditions="none",
        emits="nothing",
        refuses=["always: this operator never emits a formula"],
    ),
]
OPERATORS = dict((s["name"], s) for s in OPERATOR_SPECS)
OPERATOR_NAMES = tuple(s["name"] for s in OPERATOR_SPECS)


# ------------------------------------------------------------------ targets

def resolve_target(case, text):
    """`G4`, `L7` or `O7.label` -> what the head must say.

    A GROUP fixes the head's predicate, label and sign and nothing else: its
    participants are what the prover happened to need, not what the rule should
    quantify over, and imposing them would rewrite the rule as an instance.
    A LABEL fixes only the word; the operator fixes the predicate.
    """
    t = (text or "").strip()
    m = re.match(r"^(O\d+)\.label$", t)
    if m:
        occ = case["by_oid"].get(m.group(1))
        if occ is None:
            raise ConstructionError("%s is not an occurrence in this case" % m.group(1))
        lab = occ.get("label")
        if not isinstance(lab, str) or not lab:
            raise ConstructionError("%s has no label" % m.group(1))
        return {"kind": "label", "text": lab, "is_variable": AO._is_var(lab),
                "from": m.group(1), "sign": "+"}
    if re.match(r"^L\d+$", t):
        row = case["by_lid"].get(t)
        if row is None:
            raise ConstructionError("%s is not a label in this case" % t)
        return {"kind": "label", "text": row["text"], "is_variable": False,
                "from": t, "sign": "+"}
    if re.match(r"^G\d+$", t):
        g = case["by_gid"].get(t)
        if g is None:
            raise ConstructionError("%s is not a group in this case" % t)
        return {"kind": "group", "text": g["label"], "is_variable": False,
                "predicate": g["predicate"], "sign": g["sign"], "from": t,
                "group": g}
    raise ConstructionError("%r is not a target id (expected G<n>, L<n> or "
                            "O<n>.label)" % t)


def _head_label(target):
    if target.get("text") in (None, "", "?"):
        raise ConstructionError("the target carries no label to build with")
    return target["text"]


def _target_predicate(target, default):
    if target["kind"] == "group":
        return target["predicate"]
    return default


def _negate_if(sign, lit):
    return ["not", lit] if sign == "-" else lit


# ------------------------------------------------------------------ emitters
#
# Every emitter returns a list of PLANS.  A plan is
# {"unions": [(keyA, keyB)], "body": [occ], "head": callable(asm) -> literal,
#  "note": str}.  The shared finisher applies the unions, rebuilds the body,
# builds the head, attaches the conditions and runs the checks, so no operator
# writes a formula and no operator invents a check.


def _participants_of(occ):
    _p, _l, parts = split_atom(AO.bare_atom(occ))
    return parts


def _first_part(occ):
    parts = _participants_of(occ)
    if not parts:
        raise ConstructionError("%s has no participant" % occ["occurrence_id"])
    return parts[0][1]


def _k(asm, occ, term):
    return asm.key(occ["unit_id"], term)


def _plan(body, head, note, unions=(), **kw):
    d = {"body": list(body), "head": head, "note": note, "unions": list(unions)}
    d.update(kw)
    return d


def em_compound_head(case, target, sources, spec):
    label = _head_label(target)
    parts = compound_parts(label)
    if not parts:
        raise ConstructionError("compound_head needs a target label of two or "
                                "more words, got %r" % label)
    mod, head_word = parts
    plans = []
    for h in sources:
        hl = h.get("label")
        if not isinstance(hl, str):
            continue
        if not morph_related(tokens(hl)[-1] if tokens(hl) else "", head_word):
            continue
        hparts = [t for _i, t in _participants_of(h)]
        if not hparts:
            continue
        subject = hparts[0]
        for m in sources:
            if m is h or m.get("predicate") != "isa":
                continue
            if normalize(m.get("label")) != normalize(mod):
                continue
            mterm = _first_part(m)
            rest = [s for s in sources if s is not h and s is not m]
            if not rest:
                # the modifier must already be a participant of the head atom
                others = [t for t in hparts[1:]]
                for o in others:
                    plans.append(_plan(
                        [h, m], ("isa", label, ((h, subject),)),
                        "modifier is the head atom's other participant",
                        unions=[((m, mterm), (h, o))]))
                continue
            for link in rest:
                lp = [t for _i, t in _participants_of(link)]
                if len(lp) != 2:
                    continue
                plans.append(_plan(
                    [h, link, m], ("isa", label, ((h, subject),)),
                    "modifier joined to the subject by %s"
                    % link["occurrence_id"],
                    unions=[((m, mterm), (link, lp[0])),
                            ((h, subject), (link, lp[1]))]))
                plans.append(_plan(
                    [h, link, m], ("isa", label, ((h, subject),)),
                    "modifier joined to the subject by %s, other way round"
                    % link["occurrence_id"],
                    unions=[((m, mterm), (link, lp[1])),
                            ((h, subject), (link, lp[0]))]))
    if not plans:
        raise ConstructionError(
            "no source supplies the head word %r and none is a class atom "
            "labelled %r" % (head_word, mod))
    return plans


def em_nominalization(case, target, sources, spec):
    label = _head_label(target)
    if len(sources) != 1:
        raise ConstructionError("nominalization takes exactly one source")
    s = sources[0]
    if not label_related(s.get("label"), label):
        raise ConstructionError("%r and %r are not forms of one another"
                                % (s.get("label"), label))
    if normalize(s.get("label")) == normalize(label):
        raise ConstructionError("the target label is the source label")
    pred = _target_predicate(target, s["predicate"])
    parts = [t for _i, t in _participants_of(s)]
    need = 2 if family(pred) == "is rel2" else 1
    if len(parts) < need:
        raise ConstructionError("%s has %d participants, the target needs %d"
                                % (s["occurrence_id"], len(parts), need))
    return [_plan([s], (pred, label, tuple((s, p) for p in parts[:need])),
                  "same participants, other word form", word_relation=True)]


def em_event_nominal_equivalence(case, target, sources, spec):
    label = _head_label(target)
    types = [s for s in sources if s.get("predicate") == "has type"]
    roles = [s for s in sources if s.get("predicate") in ROLE_PREDICATES]
    if not types or not roles:
        raise ConstructionError("event_nominal_equivalence needs a `has type` "
                                "atom and at least one role atom")
    ty = types[0]
    verb = AO.bare_atom(ty)[2] if len(AO.bare_atom(ty)) > 2 else None
    if not label_related(verb, label):
        raise ConstructionError("%r and %r are not forms of one another"
                                % (verb, label))
    ev = AO.bare_atom(ty)[1]
    for r in roles:
        if AO.bare_atom(r)[1] != ev or r["unit_id"] != ty["unit_id"]:
            raise ConstructionError("%s is a role of a different event"
                                    % r["occurrence_id"])
    fillers = [(r, AO.bare_atom(r)[2]) for r in roles]
    pred = _target_predicate(target, "is rel2" if len(fillers) > 1
                             else "has property")
    if family(pred) == "is rel2" and len(fillers) < 2:
        raise ConstructionError("a two-place target needs two role atoms")
    args = tuple(fillers[:2] if family(pred) == "is rel2" else fillers[:1])
    return [_plan(list(sources), (pred, label, args),
                  "event read as its nominal")]


def em_property_class_conversion(case, target, sources, spec):
    label = _head_label(target)
    if len(sources) != 1:
        raise ConstructionError("property_class_conversion takes one source")
    s = sources[0]
    if normalize(s.get("label")) != normalize(label):
        raise ConstructionError("the labels differ: %r and %r"
                                % (s.get("label"), label))
    fam = family(s["predicate"])
    other = "has property" if fam == "isa" else "isa"
    pred = _target_predicate(target, other)
    if family(pred) == fam:
        raise ConstructionError("that is the form the source already has")
    parts = [t for _i, t in _participants_of(s)]
    if len(parts) != 1:
        raise ConstructionError("%s has no single bearer" % s["occurrence_id"])
    return [_plan([s], (pred, label, ((s, parts[0]),)),
                  "same label, other predicate", word_relation=True)]


def em_role_or_relation_projection(case, target, sources, spec):
    label = _head_label(target)
    if len(sources) != 1:
        raise ConstructionError("role_or_relation_projection takes one source")
    s = sources[0]
    parts = [t for _i, t in _participants_of(s)]
    if len(parts) != 2:
        raise ConstructionError("%s does not have exactly two participants"
                                % s["occurrence_id"])
    if normalize(s.get("label")) == normalize(label):
        raise ConstructionError("the target label is the source label")
    pred = _target_predicate(target, "is rel2")
    return [_plan([s], (pred, label, ((s, parts[0]), (s, parts[1]))),
                  "same order", word_relation=True),
            _plan([s], (pred, label, ((s, parts[1]), (s, parts[0]))),
                  "participants swapped", word_relation=True)]


def em_predication_transfer(case, target, sources, spec):
    label = _head_label(target)
    preds = [s for s in sources
             if len(_participants_of(s)) == 1
             and normalize(s.get("label")) == normalize(label)]
    links = [s for s in sources if len(_participants_of(s)) == 2]
    if not preds or not links:
        raise ConstructionError("predication_transfer needs a one-place "
                                "predication labelled %r and a link atom"
                                % label)
    plans = []
    for p in preds:
        bearer = _first_part(p)
        for link in links:
            lp = [t for _i, t in _participants_of(link)]
            pred = _target_predicate(target, p["predicate"])
            plans.append(_plan(
                [p, link], (pred, label, ((link, lp[1]),)),
                "carried from the first end of %s to the second"
                % link["occurrence_id"],
                unions=[((p, bearer), (link, lp[0]))]))
            plans.append(_plan(
                [p, link], (pred, label, ((link, lp[0]),)),
                "carried from the second end of %s to the first"
                % link["occurrence_id"],
                unions=[((p, bearer), (link, lp[1]))]))
    return plans


def em_argument_label_promotion(case, target, sources, spec):
    label = _head_label(target)
    carriers = []
    for s in sources:
        for i, t in _participants_of(s):
            if isinstance(t, str) and not AO._is_var(t) \
                    and normalize(t) == normalize(label):
                carriers.append((s, i))
    if not carriers:
        raise ConstructionError("%r does not occur as an argument constant of "
                                "any named source" % label)
    plans = []
    for carrier, idx in carriers:
        others = [t for i, t in _participants_of(carrier) if i != idx]
        if not others:
            raise ConstructionError("%s has no participant besides the label"
                                    % carrier["occurrence_id"])
        binders = [s for s in sources if s is not carrier]
        if not binders:
            raise ConstructionError(
                "argument_label_promotion needs a second source binding the "
                "subject: the carrying atom licenses the word, it is not the "
                "rule's premise")
        for subj in others:
            plans.append(_plan(
                binders, ("isa", label, ((carrier, subj),)),
                "%s licenses the word; the body is %s"
                % (carrier["occurrence_id"],
                   ", ".join(b["occurrence_id"] for b in binders)),
                licence=carrier["occurrence_id"]))
    return plans


def em_label_variable_transport(case, target, sources, spec):
    if not target.get("is_variable"):
        raise ConstructionError("label_variable_transport needs a target whose "
                                "label is a variable")
    holders = [s for s in sources if AO._is_var(s.get("label"))]
    links = [s for s in sources if len(_participants_of(s)) == 2
             and s not in holders]
    if not holders or not links:
        raise ConstructionError("it needs an atom with a variable label and a "
                                "link atom")
    plans = []
    for h in holders:
        parts = [t for _i, t in _participants_of(h)]
        if not parts:
            continue
        bearer = parts[0]
        for link in links:
            lp = [t for _i, t in _participants_of(link)]
            plans.append(_plan(
                [h, link], (h["predicate"], ("label_var", h),
                            ((link, lp[1]),)),
                "label variable carried along %s" % link["occurrence_id"],
                unions=[((h, bearer), (link, lp[0]))]))
            plans.append(_plan(
                [h, link], (h["predicate"], ("label_var", h),
                            ((link, lp[0]),)),
                "label variable carried back along %s"
                % link["occurrence_id"],
                unions=[((h, bearer), (link, lp[1]))]))
    return plans


def em_typed_taxonomy(case, target, sources, spec):
    label = _head_label(target)
    if len(sources) != 1:
        raise ConstructionError("typed_taxonomy takes one source")
    s = sources[0]
    if normalize(s.get("label")) == normalize(label):
        raise ConstructionError("the target label is the source label")
    pred = _target_predicate(target, s["predicate"])
    parts = [t for _i, t in _participants_of(s)]
    need = 2 if family(pred) == "is rel2" else 1
    if len(parts) < need:
        raise ConstructionError("%s has %d participants, the target needs %d"
                                % (s["occurrence_id"], len(parts), need))
    return [_plan([s], (pred, label, tuple((s, p) for p in parts[:need])),
                  "specific to general", word_relation=True)]


def em_other_restructure(case, target, sources, spec):
    raise ConstructionError("other_restructure emits no formula: the "
                            "construction is recorded as unsupported")


EMITTERS = {
    "compound_head": em_compound_head,
    "nominalization": em_nominalization,
    "event_nominal_equivalence": em_event_nominal_equivalence,
    "property_class_conversion": em_property_class_conversion,
    "role_or_relation_projection": em_role_or_relation_projection,
    "predication_transfer": em_predication_transfer,
    "argument_label_promotion": em_argument_label_promotion,
    "label_variable_transport": em_label_variable_transport,
    "typed_taxonomy": em_typed_taxonomy,
    "other_restructure": em_other_restructure,
}


# ------------------------------------------------------------------ finisher

def _apply_unions(asm, unions):
    for (oa, ta), (ob, tb) in unions:
        asm.unify(asm.key(oa["unit_id"], ta), asm.key(ob["unit_id"], tb))


def _build_head(asm, head):
    """The conclusion literal.  The only place a head is written."""
    pred, label, args = head
    if isinstance(label, tuple) and label and label[0] == "label_var":
        occ = label[1]
        lab = asm.resolve(occ["unit_id"], occ["label"])
    else:
        lab = label
    # A degree form carries two arguments this library never invents, so the
    # head is written in the plain form of the same family.
    pred = family(pred)
    slot = label_index(pred)
    if pred == "has type":
        slot = 1
    terms = [asm.resolve(o["unit_id"], t) for (o, t) in args]
    out, ti = [pred], 0
    total = len(terms) + (1 if slot is not None else 0)
    for i in range(total):
        if slot is not None and i == slot:
            out.append(lab)
        else:
            out.append(terms[ti])
            ti += 1
    return out


def _condition_choices(plan_keys, cond, asm_probe):
    """How this condition could attach: nothing invented, everything listed."""
    own = [(cond, t) for _i, t in _participants_of(cond)]
    shared = [k for k in own
              if asm_probe.key(cond["unit_id"], k[1]) in plan_keys]
    if shared:
        return [[]]                       # it already shares a term
    if not own:
        return []
    first = own[0]
    out = []
    for k in plan_keys:
        if k[0] == "var":
            out.append([(first, ("__key__", k))])
        elif k[0] == "const":
            out.append([(first, ("__key__", k))])
    return out


def _keys_of(asm, occs, head):
    keys = set()
    for o in occs:
        for _i, t in _participants_of(o):
            if isinstance(t, str):
                keys.add(asm._find(asm.key(o["unit_id"], t)))
    for (o, t) in head[2]:
        if isinstance(t, str):
            keys.add(asm._find(asm.key(o["unit_id"], t)))
    return keys


def _choices_for(plan, conds):
    """Per condition, every way it could attach.  Empty means it attaches to
    nothing, which is a refusal, not a silent drop."""
    probe = Assembly()
    _apply_unions(probe, plan["unions"])
    keys = _keys_of(probe, plan["body"], plan["head"])
    out = []
    for c in conds:
        out.append(_condition_choices(keys, c, probe))
    return out


def _one(case, target, plan, conds, combo, generalize, polarity="as_found"):
    """One plan + one chosen attachment -> one checked alternative.

    Returns (alternative, None) or (None, refusal).  Nothing is repaired: a
    malformed construction is refused with its reason, never patched.
    """
    asm = Assembly(generalize=generalize)
    _apply_unions(asm, plan["unions"])
    for chosen in combo:
        for (cond_term, key) in chosen:
            asm.unify(asm.key(cond_term[0]["unit_id"], cond_term[1]), key[1])
    positive = (polarity == "positive")
    body = [asm.rebuild(o, force_positive=positive) for o in plan["body"]]
    for c in conds:
        # a condition is a guard on THIS rule, so its own sign always stands
        body.append(asm.rebuild(c))
    head = _build_head(asm, plan["head"])
    if target.get("sign") == "-":
        head = ["not", head]

    body_vars = set(v for b in body for v in _vars_in(b))
    unbound = sorted(set(_vars_in(head)) - body_vars)
    if unbound:
        return None, {"why": "unbound_conclusion_variable",
                      "detail": ", ".join(unbound)}
    for b in body:
        if _contradicts(b, head):
            return None, {"why": "condition_contradicts_head",
                          "detail": str(b)[:90]}
        if b == head:
            return None, {"why": "head_repeats_a_premise",
                          "detail": str(b)[:90]}
    seen = []
    for b in body:
        if b in seen:
            return None, {"why": "a_premise_is_repeated", "detail": str(b)[:90]}
        seen.append(b)
    pkg, used = package_of(body, head)
    rec = {
        "note": plan["note"], "generalized": bool(generalize),
        "polarity": polarity,
        "generalized_constants": list(asm.generalized_constants),
        "body_occurrences": [o["occurrence_id"] for o in plan["body"]],
        "condition_occurrences": [c["occurrence_id"] for c in conds],
        "licence_occurrence": plan.get("licence"),
        "quantified_variables": used,
        "uses_question_occurrence": [
            o["occurrence_id"] for o in list(plan["body"]) + list(conds)
            if o.get("in_question")],
        "body": body, "head": head,
    }
    return {"package": pkg, "record": rec}, None


def _combos(choices, cap):
    out = [[]]
    for per_condition in choices:
        nxt = []
        for sofar in out:
            for ch in per_condition:
                nxt.append(sofar + [ch])
                if len(nxt) >= cap:
                    break
            if len(nxt) >= cap:
                break
        out = nxt or []
    return out[:cap]


def build(case, proposal, max_alternatives=MAX_ALTERNATIVES):
    """A named proposal -> checked alternatives, or a recorded refusal.

    The model named the target, the sources, the operator and the conditions.
    Everything below this line — which argument maps to which, whether a
    constant is kept or generalised, the quantifier prefix, every check — is
    decided here, deterministically, and reported.
    """
    op = proposal.get("operator")
    if op not in OPERATORS:
        raise ConstructionError("unknown operator %r" % op)
    spec = OPERATORS[op]
    sids = list(proposal.get("sources") or [])
    cids = list(proposal.get("conditions") or [])
    if len(sids) > MAX_SOURCES:
        raise ConstructionError("at most %d sources" % MAX_SOURCES)
    if len(cids) > MAX_CONDITIONS:
        raise ConstructionError("at most %d conditions" % MAX_CONDITIONS)
    if len(set(sids)) != len(sids) or len(set(cids)) != len(cids):
        raise ConstructionError("an occurrence is named twice")
    if set(sids) & set(cids):
        raise ConstructionError("an occurrence is both a source and a condition")
    sources, conds = [], []
    for oid in sids:
        occ = case["by_oid"].get(oid)
        if occ is None:
            raise ConstructionError("%s is not an occurrence in this case" % oid)
        if not usable_source(occ):
            raise ConstructionError("%s is not a content atom this library can "
                                    "build from (%s)" % (oid, occ.get("predicate")))
        sources.append(occ)
    for oid in cids:
        occ = case["by_oid"].get(oid)
        if occ is None:
            raise ConstructionError("%s is not an occurrence in this case" % oid)
        if not usable_source(occ):
            raise ConstructionError("%s cannot be a condition (%s)"
                                    % (oid, occ.get("predicate")))
        conds.append(occ)
    if not sources:
        raise ConstructionError("a proposal needs at least one source")
    target = resolve_target(case, proposal.get("target"))
    plans = EMITTERS[op](case, target, sources, spec)

    alts, refusals = [], []
    for plan in plans:
        choices = _choices_for(plan, conds)
        if any(not c for c in choices):
            bad = conds[[i for i, c in enumerate(choices) if not c][0]]
            refusals.append({"why": "condition_connected_to_nothing",
                             "detail": bad["occurrence_id"],
                             "plan": plan["note"]})
            continue
        # A word-relation operator states something about two WORDS, so it is
        # also offered with the source read positively: `product of` occurs in
        # folio-0080 only inside the question's negation, and the relation
        # between the two words does not inherit that negation.
        polarities = (("as_found", "positive") if plan.get("word_relation")
                      else ("as_found",))
        for combo in _combos(choices, max_alternatives):
            for polarity in polarities:
              for generalize in (False, True):
                alt, why = _one(case, target, plan, conds, combo, generalize,
                                polarity)
                if why is not None:
                    refusals.append(dict(why, plan=plan["note"]))
                    continue
                if any(a["package"] == alt["package"] for a in alts):
                    continue
                alt["record"]["operator"] = op
                alt["record"]["target"] = proposal.get("target")
                alt["record"]["target_kind"] = target["kind"]
                alt["record"]["target_label"] = target.get("text")
                alts.append(alt)
                if len(alts) >= max_alternatives:
                    return {"alternatives": alts, "refusals": refusals,
                            "capped": True, "target": target}
    return {"alternatives": alts, "refusals": refusals, "capped": False,
            "target": target}


# ------------------------------------------------------------------ ceiling
#
# The admissible space of the library, enumerated WITHOUT any reference to a
# reviewed rule.  A scorer may compare what comes out of here against gold; this
# code never sees it.  Everything is capped, and the caps are reported rather
# than applied silently.

# Raised until nothing in the development split was capped: a ceiling measured
# under a cap that bites is a measurement of the cap.
ENUM_CAPS = {"targets": 60, "per_operator": 6000, "links": 12, "binders": 14,
             "conditions": 12}


def _two_place(occ):
    return len(_participants_of(occ)) == 2


def candidate_targets(case):
    out = []
    for g in case["groups"]:
        if isinstance(g.get("label"), str) and g["label"] not in ("", "?"):
            out.append((g["group_id"], g["label"], "group"))
    for e in case["labels"]:
        out.append((e["lid"], e["text"], "label"))
    for oid, occ in sorted(case["by_oid"].items(), key=lambda kv: kv[0]):
        if AO._is_var(occ.get("label") or ""):
            out.append(("%s.label" % oid, occ["label"], "variable label"))
    return out[:ENUM_CAPS["targets"]]


def _oid(case, occ):
    for k, v in case["by_oid"].items():
        if v is occ:
            return k
    return None


def enumerate_proposals(case):
    """Every proposal the frozen library admits for this case.

    Generated from the operators' own structural anchors, not from a search
    over all subsets: an operator that needs a compound target and a modifier
    class atom only ever proposes those.
    """
    occs = [(oid, case["by_oid"][oid]) for oid in sorted(
        case["by_oid"], key=lambda k: int(k[1:]))]
    links = [(oid, o) for oid, o in occs if _two_place(o)][:ENUM_CAPS["links"]]
    conds = [(oid, o) for oid, o in occs
             if family(o["predicate"]) in ("isa", "has property")
             ][:ENUM_CAPS["conditions"]]
    out, capped = [], []

    def add(op, target, sources):
        rows = [{"operator": op, "target": target, "sources": list(sources),
                 "conditions": []}]
        for cid, _c in conds:
            if cid in sources:
                continue
            rows.append({"operator": op, "target": target,
                         "sources": list(sources), "conditions": [cid]})
        for r in rows:
            out.append(r)

    for tid, ttext, _kind in candidate_targets(case):
        parts = compound_parts(ttext)
        if parts:
            mod, head_word = parts
            heads = [(oid, o) for oid, o in occs
                     if isinstance(o.get("label"), str) and tokens(o["label"])
                     and morph_related(tokens(o["label"])[-1], head_word)]
            mods = [(oid, o) for oid, o in occs
                    if o.get("predicate") == "isa"
                    and normalize(o.get("label")) == normalize(mod)]
            for hoid, _h in heads:
                for moid, _m in mods:
                    if moid == hoid:
                        continue
                    add("compound_head", tid, [hoid, moid])
                    for loid, _l in links:
                        if loid in (hoid, moid):
                            continue
                        add("compound_head", tid, [hoid, moid, loid])
        for oid, o in occs:
            lab = o.get("label")
            if not isinstance(lab, str) or AO._is_var(lab):
                continue
            same = normalize(lab) == normalize(ttext)
            if label_related(lab, ttext) and not same:
                add("nominalization", tid, [oid])
            if same:
                add("property_class_conversion", tid, [oid])
                if len(_participants_of(o)) == 1:
                    for loid, _l in links:
                        if loid != oid:
                            add("predication_transfer", tid, [oid, loid])
            if not same:
                add("typed_taxonomy", tid, [oid])
                if _two_place(o):
                    add("role_or_relation_projection", tid, [oid])
            if o["predicate"] == "has type" and label_related(lab, ttext):
                ev = AO.bare_atom(o)[1]
                roles = [(roid, r) for roid, r in occs
                         if r["predicate"] in ROLE_PREDICATES
                         and r["unit_id"] == o["unit_id"]
                         and AO.bare_atom(r)[1] == ev][:2]
                if roles:
                    add("event_nominal_equivalence", tid,
                        [oid] + [roid for roid, _r in roles])
            for _i, t in _participants_of(o):
                if isinstance(t, str) and not AO._is_var(t) \
                        and normalize(t) == normalize(ttext):
                    for boid, _b in occs[:ENUM_CAPS["binders"]]:
                        if boid != oid:
                            add("argument_label_promotion", tid, [oid, boid])
                    break
        if tid.endswith(".label"):
            hoid = tid[:-len(".label")]
            for loid, _l in links:
                if loid != hoid:
                    add("label_variable_transport", tid, [hoid, loid])

    seen, uniq = set(), []
    for r in out:
        k = (r["operator"], r["target"], tuple(r["sources"]),
             tuple(r["conditions"]))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    by_op = {}
    final = []
    for r in uniq:
        n = by_op.get(r["operator"], 0)
        if n >= ENUM_CAPS["per_operator"]:
            if r["operator"] not in capped:
                capped.append(r["operator"])
            continue
        by_op[r["operator"]] = n + 1
        final.append(r)
    return final, capped


# ------------------------------------------------------------------ parsing

_FIELD = re.compile(r"^\s*([a-z_]+)\s*=\s*(.*?)\s*$", re.I)
_NONE = ("none", "-", "n/a", "na", "nothing", "", "[]", "()")
MAX_PROPOSALS = 3


def parse_proposals(text, known_oids, known_targets):
    """Read the final `PROPOSE:` lines and nothing else.

    Prose is never scraped: an id that appears only in the explanation does not
    exist, and an id that is not in this case is reported, never snapped to a
    nearby one.  At most the last three lines are read.
    """
    lines = []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() != "PROPOSE":
            continue
        lines.append(v.strip())
    if not lines:
        return {"readable": False, "proposals": [], "rejected": [],
                "lines_seen": 0}
    kept = lines[-MAX_PROPOSALS:]
    good, bad = [], []
    for line in kept:
        parsed, why = _parse_one(line, known_oids, known_targets)
        if why:
            bad.append({"line": line[:160], "why": why})
        else:
            good.append(parsed)
    return {"readable": True, "proposals": good, "rejected": bad,
            "lines_seen": len(lines), "lines_read": len(kept)}


def _parse_one(line, known_oids, known_targets):
    fields = {}
    for chunk in line.split(";"):
        if not chunk.strip():
            continue
        m = _FIELD.match(chunk)
        if not m:
            return None, "not a field: %r" % chunk.strip()[:40]
        key = m.group(1).lower()
        if key not in ("target", "sources", "operator", "conditions"):
            return None, "unknown field %r" % key
        if key in fields:
            return None, "%s given twice" % key
        fields[key] = m.group(2).strip()
    for need in ("target", "sources", "operator"):
        if need not in fields:
            return None, "no %s" % need
    op = fields["operator"].strip().strip(".").lower()
    if op not in OPERATORS:
        return None, "unknown operator %r" % op[:40]
    target = fields["target"].strip().strip(".")
    if target not in known_targets:
        return None, "unknown target %r" % target[:40]
    sources = _ids(fields["sources"])
    if not sources:
        return None, "no sources"
    conds = _ids(fields.get("conditions", ""))
    for oid in sources + conds:
        if oid not in known_oids:
            return None, "unknown occurrence %r" % oid
    if len(sources) > MAX_SOURCES:
        return None, "more than %d sources" % MAX_SOURCES
    if len(conds) > MAX_CONDITIONS:
        return None, "more than %d conditions" % MAX_CONDITIONS
    return {"target": target, "sources": sources, "operator": op,
            "conditions": conds}, None


def _ids(field):
    f = (field or "").strip().strip(".").lower()
    if f in _NONE:
        return []
    return re.findall(r"\bO\d+\b", (field or "").upper())


def known_targets(case):
    out = set()
    for g in case["groups"]:
        out.add(g["group_id"])
    for e in case["labels"]:
        out.add(e["lid"])
    for oid, occ in case["by_oid"].items():
        if isinstance(occ.get("label"), str) and occ["label"]:
            out.add("%s.label" % oid)
    return out
