"""Construction operators, version 2: executable slot contracts.

AL-68 asked a model to name a target, some sources and an operator, and told it
only a one-sentence summary of what each operator does.  Two of the five misses
were arity failures — the model named one source for an operator that needs two,
and two sources for one that needs three — and the contract that would have said
so existed only as prose in an artifact the model never saw.

So the contract becomes executable.  Each operator declares named SLOTS with a
cardinality, a mechanical form test, whether filling the slot puts an atom in the
rule's body, and a direction policy.  One declaration drives three things that
used to be written separately and could drift apart:

  * the operator card rendered into the prompt;
  * validation of what the model named, with refusals that name the slot;
  * enumeration of completions when a required slot is empty.

Three further corrections over v1, each of them a thing v1 did silently:

  * **Terms are typed.**  A word that appears as an argument is a concept, an
    individual, a variable, a control value or converter machinery, and the
    operators care which.  Only a concept may be promoted to a class label, and
    only an individual may be generalised into a quantified variable — v1 would
    quantify over `breeding back` and `artificial selection` and call the result
    a rule about anything at all.
  * **Attachments have provenance.**  When a guard shares no term with the rule,
    identifying one of its participants with a rule participant is a hypothesis,
    not a mechanical fact.  It is still offered, and it is recorded as an
    unverified attachment on the alternative that used it.
  * **Direction is separated from interface.**  Finding that `from` and
    `product of` are two ways of saying one thing is one act; deciding which
    implies which is another.  For paraphrase-like operators code emits both
    directions as separate hypotheses.  Taxonomy stays directional.

Nothing here reads a reviewed rule or an expected answer.
"""

import re

import alignment_occurrences as AO
import construction_operators as CO

VERSION = "construction_slots/2.0"

MAX_GUARDS = 2
MAX_MAPPINGS_PER_COMPLETION = 5
MAX_ALTERNATIVES = 24
MAX_COMPLETIONS = 12
MAX_GUARD_CANDIDATES = 8

# Direction policies.
FIXED = "fixed_direction"
SEMANTIC = "semantic_direction_required"
BIDIRECTIONAL = "bidirectional_hypotheses"

# Term types.
CONCEPT = "concept_or_label"
INDIVIDUAL = "individual_entity"
VARIABLE = "variable"
CONTROL = "control_or_degree_value"
MACHINERY = "converter_or_context_machinery"

_CONTROL_WORDS = {
    "none", "very", "more", "less", "most", "least", "equal", "much",
    "little", "past", "present", "future", "in", "at", "on", "by", "with",
    "before", "after", "into", "from",
}
_MACHINERY = re.compile(r"^(\$|sk\d|skq_|\?:)")
_NUMBERED_ENTITY = re.compile(r" \d+$")
_URL = re.compile(r"^(https?://|www\.)")


class SlotError(CO.ConstructionError):
    """A slot is missing, or what was named cannot fill it.  Never guessed."""


# ------------------------------------------------------------------ typing

def term_type(term):
    """What kind of thing an argument position holds.

    Used for two decisions and no others: what may be promoted into a class
    label, and what may be generalised into a quantified variable.
    """
    if not isinstance(term, str):
        return MACHINERY
    t = term.strip()
    if AO._is_var(t):
        return VARIABLE
    if _MACHINERY.match(t):
        return VARIABLE if t.startswith("?:") else MACHINERY
    if CO.normalize(t) in _CONTROL_WORDS:
        return CONTROL
    if t.startswith("#:") or _URL.match(t) or _NUMBERED_ENTITY.search(t):
        return INDIVIDUAL
    return CONCEPT


PROMOTABLE = (CONCEPT,)
GENERALIZABLE = (INDIVIDUAL,)


class TypedAssembly(CO.Assembly):
    """v1's assembly, with generalisation restricted to individuals.

    v1 offered a generalised variant for every participant constant, which
    quantified over concept words and produced rules about everything.  Here a
    constant is generalised only when it names an individual; a concept keeps
    its own name, and what changed is recorded.
    """

    def resolve(self, unit, term):
        if not isinstance(term, str):
            return term
        k = self._find(self.key(unit, term))
        if k[0] == "const":
            if not self.generalize or term_type(k[1]) not in GENERALIZABLE:
                return k[1]
            if k[1] not in self.generalized_constants:
                self.generalized_constants.append(k[1])
        if k not in self.names:
            self.n += 1
            self.names[k] = "V%d" % self.n
        return self.names[k]


def generalizable_constants(occs):
    out = []
    for o in occs:
        for _i, t in CO._participants_of(o):
            if isinstance(t, str) and term_type(t) in GENERALIZABLE \
                    and t not in out:
                out.append(t)
    return out


# ------------------------------------------------------------------ forms

def _parts(occ):
    return [t for _i, t in CO._participants_of(occ)]


def form_any(occ):
    return True


def form_class(occ):
    return CO.family(occ["predicate"]) == "isa" and len(_parts(occ)) == 1


def form_one_place(occ):
    return len(_parts(occ)) == 1 and CO.family(occ["predicate"]) in (
        "isa", "has property")


def form_two_place(occ):
    return len(_parts(occ)) == 2


def form_event_type(occ):
    return occ["predicate"] == "has type"


def form_role(occ):
    return occ["predicate"] in CO.ROLE_PREDICATES


def form_variable_label(occ):
    return bool(AO._is_var(occ.get("label") or ""))


def form_guard(occ):
    return CO.family(occ["predicate"]) in ("isa", "has property")


def form_carrier(occ):
    """An atom carrying a promotable concept in an argument position."""
    return any(term_type(t) in PROMOTABLE for t in _parts(occ))


FORMS = {
    form_any: "any content atom",
    form_class: "a one-place class atom, `isa(word, x)`",
    form_one_place: "a one-place class or property atom",
    form_two_place: "an atom with exactly two participants",
    form_event_type: "a `has type` atom naming an event",
    form_role: "a role atom of an event",
    form_variable_label: "an atom whose label position holds a variable",
    form_guard: "a class or property atom",
    form_carrier: "an atom carrying the word in an argument position",
}


# ------------------------------------------------------------------ slots

def slot(name, required, form, note, maximum=1, premise=True):
    return {"name": name, "required": required, "form": form, "note": note,
            "max": maximum, "premise": premise,
            "form_note": FORMS.get(form, "")}


GUARDS = slot("guards", False, form_guard,
              "extra conditions the rule must also satisfy", maximum=MAX_GUARDS)


def op(name, summary, slots, direction, emits, note=""):
    return {"name": name, "summary": summary, "slots": slots,
            "direction": direction, "emits": emits, "note": note,
            "slot_names": [s["name"] for s in slots]}


OPERATORS = [
    op("compound_head",
       "A compound class built from its head word and its modifier: what a "
       "thing does or is, plus what the other participant is, makes it a "
       "`<modifier> <head>`.",
       [slot("head", True, form_any,
             "supplies the compound's HEAD word and the subject of the "
             "conclusion"),
        slot("modifier", True, form_class,
             "a class atom whose label is the compound's MODIFIER"),
        slot("link", "conditional", form_two_place,
             "joins the modifier's participant to the subject; required "
             "unless the modifier is already a participant of `head`"),
        GUARDS],
       FIXED, "isa(<modifier> <head>, subject)"),

    op("nominalization",
       "One word and another form of the same word: a verb and its noun, an "
       "adjective and its noun.",
       [slot("source", True, form_any,
             "the atom whose label is the other form of the word"),
        GUARDS],
       BIDIRECTIONAL, "the target predicate with the source's participants"),

    op("event_nominal_equivalence",
       "A described event read as the relation or property it amounts to.",
       [slot("event_type", True, form_event_type,
             "the `has type` atom naming the event"),
        slot("role", True, form_role,
             "a role atom of that event; its filler becomes the first "
             "participant"),
        slot("second_role", "conditional", form_role,
             "a second role of the same event; required when the target is a "
             "two-place relation"),
        GUARDS],
       FIXED, "is rel2(<label>, first, second) or has property(<label>, first)",
       note="event -> nominal only; the reverse would invent an event"),

    op("property_class_conversion",
       "Being a kind of thing and having a property, as two ways of writing "
       "the same word.",
       [slot("source", True, form_one_place,
             "the class or property atom carrying the word"),
        GUARDS],
       BIDIRECTIONAL, "the other predicate, same word, same bearer"),

    op("role_or_relation_projection",
       "One two-place relation and another: same participants, different "
       "relation, possibly in the other order.",
       [slot("source", True, form_two_place,
             "the relation atom to project"),
        GUARDS],
       BIDIRECTIONAL, "is rel2(<target word>, a, b)"),

    op("predication_transfer",
       "A predication carried from one participant to another along a stated "
       "link: what holds of the part holds of the whole, or the other way.",
       [slot("predication", True, form_one_place,
             "what is being carried; its word must be the target word"),
        slot("link", True, form_two_place,
             "the relation the predication travels along"),
        GUARDS],
       FIXED, "the same predicate and word, about the other participant"),

    op("argument_label_promotion",
       "A word that only ever appears as an argument, promoted into a class "
       "of its own.",
       [slot("carrier", True, form_carrier,
             "the atom in which the word appears as an argument. It LICENSES "
             "the word; it does not become a premise of the rule",
             premise=False),
        slot("subject_premise", True, form_one_place,
             "what the rule's subject must satisfy — this IS a premise",
             maximum=2),
        GUARDS],
       FIXED, "isa(<promoted word>, subject)"),

    op("label_variable_transport",
       "A label that is itself a variable, carried from one participant to "
       "another without ever being named.",
       [slot("holder", True, form_variable_label,
             "the atom whose label position holds the variable"),
        slot("link", True, form_two_place,
             "the relation the label travels along"),
        GUARDS],
       FIXED, "the same predicate, same label variable, other bearer"),

    op("typed_taxonomy",
       "One class or relation is a kind of another. This is the operator that "
       "rests on your judgment about the words rather than on their shape.",
       [slot("source", True, form_any,
             "the more specific class or relation"),
        GUARDS],
       SEMANTIC, "the target word with the source's participants",
       note="specific -> general only; taxonomy is not symmetric"),

    op("other_restructure",
       "The construction you can see is not in this library. Nothing is "
       "built; the case is recorded as unsupported.",
       [], FIXED, "nothing"),
]
BY_NAME = dict((o["name"], o) for o in OPERATORS)
NAMES = tuple(o["name"] for o in OPERATORS)
ROLE_NAMES = sorted(set(s["name"] for o in OPERATORS for s in o["slots"]))

REPORT_OUTCOMES = ("no_abstraction_needed", "ordinary_inference_gap",
                   "translation_repair", "unsupported_construction")


# ------------------------------------------------------------------ atoms

def _atom_spec(pred, label, pairs):
    return (pred, label, tuple(pairs))


def _build_atom(asm, spec):
    """A synthetic atom: the only place an atom is written from parts."""
    pred, label, args = spec
    if isinstance(label, tuple) and label and label[0] == "label_var":
        occ = label[1]
        lab = asm.resolve(occ["unit_id"], occ["label"])
    else:
        lab = label
    pred = CO.family(pred)
    slot_i = CO.label_index(pred)
    if pred == "has type":
        slot_i = 1
    terms = [asm.resolve(o["unit_id"], t) for (o, t) in args]
    out, ti = [pred], 0
    total = len(terms) + (1 if slot_i is not None else 0)
    for i in range(total):
        if slot_i is not None and i == slot_i:
            out.append(lab)
        else:
            out.append(terms[ti])
            ti += 1
    return out


def _plan(body_items, head, note, unions=(), **kw):
    d = {"body_items": list(body_items), "head": head, "note": note,
         "unions": list(unions)}
    d.update(kw)
    return d


def _occ_item(occ, positive=False):
    return ("occ", occ, positive)


def _atom_item(spec):
    return ("atom", spec, False)


def _one(occ):
    return occ[0] if isinstance(occ, list) else occ


# ------------------------------------------------------------------ emitters
#
# Every emitter receives slots that are already filled and already form-checked.
# It applies the operator's own structural requirements and refuses by NAMING
# the slot that does not work — the v1 message "no source supplies the head
# word" was emitted when a head source was present and only the modifier could
# not attach, and it sent an eb2-0121 diagnosis down the wrong path.

def em_compound_head(case, target, f):
    label = CO._head_label(target)
    parts = CO.compound_parts(label)
    if not parts:
        raise SlotError("compound_head needs a target of two or more words, "
                        "got %r" % label, )
    mod, head_word = parts
    h, m = f["head"][0], f["modifier"][0]
    ht = CO.tokens(h.get("label") or "")
    if not ht or not CO.morph_related(ht[-1], head_word):
        raise SlotError("slot `head`: %s is labelled %r, which is not a form "
                        "of the compound's head word %r"
                        % (h["occurrence_id"], h.get("label"), head_word))
    if CO.normalize(m.get("label")) != CO.normalize(mod):
        raise SlotError("slot `modifier`: %s is labelled %r, not the "
                        "compound's modifier %r"
                        % (m["occurrence_id"], m.get("label"), mod))
    hparts = _parts(h)
    if not hparts:
        raise SlotError("slot `head`: %s has no participant to be the subject"
                        % h["occurrence_id"])
    subject, mterm = hparts[0], _parts(m)[0]
    links = f.get("link") or []
    plans = []
    if not links:
        if len(hparts) < 2:
            raise SlotError(
                "slot `link` is required here: `head` %s has one participant, "
                "so the modifier %s attaches to nothing"
                % (h["occurrence_id"], m["occurrence_id"]))
        for other in hparts[1:]:
            plans.append(_plan(
                [_occ_item(h), _occ_item(m)],
                _atom_spec("isa", label, [(h, subject)]),
                "the modifier is the head atom's other participant",
                unions=[((m, mterm), (h, other))]))
        return plans
    link = links[0]
    lp = _parts(link)
    if len(lp) != 2:
        raise SlotError("slot `link`: %s does not have two participants"
                        % link["occurrence_id"])
    for a, b, why in ((0, 1, ""), (1, 0, ", other way round")):
        plans.append(_plan(
            [_occ_item(h), _occ_item(link), _occ_item(m)],
            _atom_spec("isa", label, [(h, subject)]),
            "the modifier is joined to the subject by %s%s"
            % (link["occurrence_id"], why),
            unions=[((m, mterm), (link, lp[a])),
                    ((h, subject), (link, lp[b]))]))
    return plans


def _word_pair_plans(case, target, s, default_pred, orders, note):
    """Forward and reverse hypotheses for a word-to-word operator.

    Both atoms are read positively: the operator states a relation between two
    WORDS, and the sign of the place a word was found — a question's negation,
    for instance — is not part of that relation.  It is recorded.
    """
    label = CO._head_label(target)
    pred = CO._target_predicate(target, default_pred or s["predicate"])
    sparts = _parts(s)
    need = 2 if CO.family(pred) == "is rel2" else 1
    if len(sparts) < need:
        raise SlotError("slot `source`: %s has %d participant(s), the target "
                        "needs %d" % (s["occurrence_id"], len(sparts), need))
    plans = []
    for order in orders:
        pairs = [(s, sparts[i]) for i in order]
        tgt = _atom_spec(pred, label, pairs)
        src = _atom_spec(s["predicate"], s.get("label"),
                         [(s, t) for t in sparts])
        plans.append(_plan([_occ_item(s, positive=True)], tgt,
                           "%s, source -> target%s"
                           % (note, "" if order == tuple(range(need))
                              else ", participants swapped"),
                           direction="source_to_target"))
        plans.append(_plan([_atom_item(tgt)], src,
                           "%s, target -> source%s"
                           % (note, "" if order == tuple(range(need))
                              else ", participants swapped"),
                           direction="target_to_source"))
    return plans


def em_nominalization(case, target, f):
    s = f["source"][0]
    label = CO._head_label(target)
    if not CO.label_related(s.get("label"), label):
        raise SlotError("slot `source`: %r and %r are not forms of one another"
                        % (s.get("label"), label))
    if CO.normalize(s.get("label")) == CO.normalize(label):
        raise SlotError("slot `source`: that is the target word itself")
    need = 2 if CO.family(CO._target_predicate(target, s["predicate"])) == \
        "is rel2" else 1
    return _word_pair_plans(case, target, s, None, [tuple(range(need))],
                            "other word form")


def em_property_class_conversion(case, target, f):
    s = f["source"][0]
    label = CO._head_label(target)
    if CO.normalize(s.get("label")) != CO.normalize(label):
        raise SlotError("slot `source`: labelled %r, not the target word %r"
                        % (s.get("label"), label))
    fam = CO.family(s["predicate"])
    other = "has property" if fam == "isa" else "isa"
    pred = CO._target_predicate(target, other)
    if CO.family(pred) == fam:
        raise SlotError("slot `source`: that is already the form the target "
                        "asks for (%s)" % fam)
    return _word_pair_plans(case, target, s, pred, [(0,)],
                            "same word, other predicate")


def em_role_or_relation_projection(case, target, f):
    s = f["source"][0]
    label = CO._head_label(target)
    if len(_parts(s)) != 2:
        raise SlotError("slot `source`: %s does not have exactly two "
                        "participants" % s["occurrence_id"])
    if CO.normalize(s.get("label")) == CO.normalize(label):
        raise SlotError("slot `source`: that is the target word itself")
    return _word_pair_plans(case, target, s, "is rel2", [(0, 1), (1, 0)],
                            "one relation for another")


def em_typed_taxonomy(case, target, f):
    s = f["source"][0]
    label = CO._head_label(target)
    if CO.normalize(s.get("label")) == CO.normalize(label):
        raise SlotError("slot `source`: that is the target word itself")
    pred = CO._target_predicate(target, s["predicate"])
    sparts = _parts(s)
    need = 2 if CO.family(pred) == "is rel2" else 1
    if len(sparts) < need:
        raise SlotError("slot `source`: %s has %d participant(s), the target "
                        "needs %d" % (s["occurrence_id"], len(sparts), need))
    return [_plan([_occ_item(s, positive=True)],
                  _atom_spec(pred, label, [(s, t) for t in sparts[:need]]),
                  "specific -> general", direction="source_to_target")]


def em_event_nominal_equivalence(case, target, f):
    label = CO._head_label(target)
    ty = f["event_type"][0]
    roles = list(f.get("role") or []) + list(f.get("second_role") or [])
    atom = AO.bare_atom(ty)
    verb = atom[2] if len(atom) > 2 else None
    if not CO.label_related(verb, label):
        raise SlotError("slot `event_type`: the event is a %r, which is not a "
                        "form of %r" % (verb, label))
    ev = atom[1]
    for r in roles:
        if AO.bare_atom(r)[1] != ev or r["unit_id"] != ty["unit_id"]:
            raise SlotError("slot `role`: %s is a role of a different event "
                            "than %s" % (r["occurrence_id"],
                                         ty["occurrence_id"]))
    pred = CO._target_predicate(target,
                                "is rel2" if len(roles) > 1 else "has property")
    if CO.family(pred) == "is rel2" and len(roles) < 2:
        raise SlotError("slot `second_role` is required: the target is a "
                        "two-place relation and only one role was given")
    fillers = [(r, AO.bare_atom(r)[2]) for r in roles[:2 if CO.family(pred) ==
                                                     "is rel2" else 1]]
    return [_plan([_occ_item(o) for o in [ty] + roles],
                  _atom_spec(pred, label, fillers),
                  "the event read as its nominal")]


def em_predication_transfer(case, target, f):
    label = CO._head_label(target)
    p, link = f["predication"][0], f["link"][0]
    if CO.normalize(p.get("label")) != CO.normalize(label):
        raise SlotError("slot `predication`: labelled %r, not the target word "
                        "%r" % (p.get("label"), label))
    pp = _parts(p)
    lp = _parts(link)
    if len(pp) != 1:
        raise SlotError("slot `predication`: %s has no single bearer"
                        % p["occurrence_id"])
    if len(lp) != 2:
        raise SlotError("slot `link`: %s does not have two participants"
                        % link["occurrence_id"])
    pred = CO._target_predicate(target, p["predicate"])
    plans = []
    for a, b, why in ((0, 1, "first end to the second"),
                      (1, 0, "second end to the first")):
        plans.append(_plan(
            [_occ_item(p), _occ_item(link)],
            _atom_spec(pred, label, [(link, lp[b])]),
            "carried along %s, %s" % (link["occurrence_id"], why),
            unions=[((p, pp[0]), (link, lp[a]))]))
    return plans


def em_argument_label_promotion(case, target, f):
    label = CO._head_label(target)
    carrier = f["carrier"][0]
    premises = list(f["subject_premise"])
    ttype = term_type(label)
    if ttype not in PROMOTABLE:
        raise SlotError("the target %r is a %s, and only a concept may be "
                        "promoted to a class" % (label, ttype))
    hits = [(i, t) for i, t in CO._participants_of(carrier)
            if isinstance(t, str) and CO.normalize(t) == CO.normalize(label)]
    if not hits:
        raise SlotError("slot `carrier`: %r does not appear as an argument of "
                        "%s" % (label, carrier["occurrence_id"]))
    plans = []
    for idx, _t in hits:
        others = [t for i, t in CO._participants_of(carrier) if i != idx]
        if not others:
            raise SlotError("slot `carrier`: %s has no participant besides "
                            "the word itself" % carrier["occurrence_id"])
        for subj in others:
            plans.append(_plan(
                [_occ_item(o) for o in premises],
                _atom_spec("isa", label, [(carrier, subj)]),
                "%s licenses the word and is NOT a premise; the body is %s"
                % (carrier["occurrence_id"],
                   ", ".join(p["occurrence_id"] for p in premises)),
                licence=carrier["occurrence_id"]))
    return plans


def em_label_variable_transport(case, target, f):
    if not target.get("is_variable"):
        raise SlotError("the target must be a label position holding a "
                        "variable")
    h, link = f["holder"][0], f["link"][0]
    hp, lp = _parts(h), _parts(link)
    if not hp:
        raise SlotError("slot `holder`: %s has no participant"
                        % h["occurrence_id"])
    if len(lp) != 2:
        raise SlotError("slot `link`: %s does not have two participants"
                        % link["occurrence_id"])
    plans = []
    for a, b, why in ((0, 1, "along"), (1, 0, "back along")):
        plans.append(_plan(
            [_occ_item(h), _occ_item(link)],
            _atom_spec(h["predicate"], ("label_var", h), [(link, lp[b])]),
            "the label variable is carried %s %s" % (why,
                                                     link["occurrence_id"]),
            unions=[((h, hp[0]), (link, lp[a]))]))
    return plans


def em_other_restructure(case, target, f):
    raise SlotError("other_restructure builds nothing: the construction is "
                    "recorded as unsupported")


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
    for a, b in unions:
        ka = a[1] if a[0] == "__key__" else asm.key(a[0]["unit_id"], a[1])
        kb = b[1] if b[0] == "__key__" else asm.key(b[0]["unit_id"], b[1])
        asm.unify(ka, kb)


def _rule_keys(plan):
    probe = TypedAssembly()
    _apply_unions(probe, plan["unions"])
    keys = set()
    for kind, payload, _pos in plan["body_items"]:
        if kind == "occ":
            for _i, t in CO._participants_of(payload):
                if isinstance(t, str):
                    keys.add(probe._find(probe.key(payload["unit_id"], t)))
        else:
            for (o, t) in payload[2]:
                if isinstance(t, str):
                    keys.add(probe._find(probe.key(o["unit_id"], t)))
    for (o, t) in plan["head"][2]:
        if isinstance(t, str):
            keys.add(probe._find(probe.key(o["unit_id"], t)))
    return keys


def guard_attachments(plan, guards):
    """How each guard could attach.  Invented identifications are labelled.

    A guard that already shares a term with the rule attaches mechanically.  A
    guard that does not is still offered — the reviewed eb2-0009 rule needs one
    — but identifying one of its variables with a rule participant is a
    HYPOTHESIS, and every alternative that uses one carries it.
    """
    keys = _rule_keys(plan)
    out = []
    for g in guards:
        own = [(i, t) for i, t in CO._participants_of(g)]
        probe = TypedAssembly()
        shares = [t for _i, t in own
                  if isinstance(t, str) and probe.key(g["unit_id"], t) in keys]
        if shares:
            out.append([{"guard": g, "union": None,
                         "status": "shares_a_term", "shared": shares[0]}])
            continue
        variables = [t for _i, t in own if AO._is_var(t)]
        if not variables:
            out.append([])            # refused: nothing to attach
            continue
        choices = []
        for k in sorted(keys, key=lambda x: (x[0], str(x[1:]))):
            choices.append({"guard": g, "union": ((g, variables[0]),
                                                  ("__key__", k)),
                            "status": "unverified_attachment",
                            "identified": "%s of %s with %s"
                            % (variables[0], g["occurrence_id"],
                               k[-1] if k[0] == "const" else "%s/%s"
                               % (k[1], k[2]))})
        out.append(choices)
    return out


def _combos(choices, cap):
    out = [[]]
    for per in choices:
        nxt = []
        for sofar in out:
            for ch in per:
                nxt.append(sofar + [ch])
                if len(nxt) >= cap:
                    break
            if len(nxt) >= cap:
                break
        out = nxt
        if not out:
            return []
    return out[:cap]


def _assemble(case, target, opspec, plan, attach, generalize, provenance):
    """One plan, one guard attachment, one generalisation choice -> one rule."""
    asm = TypedAssembly(generalize=generalize)
    _apply_unions(asm, plan["unions"])
    _apply_unions(asm, [a["union"] for a in attach if a.get("union")])
    body = []
    for kind, payload, positive in plan["body_items"]:
        if kind == "occ":
            body.append(asm.rebuild(payload, force_positive=positive))
        else:
            body.append(_build_atom(asm, payload))
    for a in attach:
        body.append(asm.rebuild(a["guard"]))
    head = _build_atom(asm, plan["head"])
    if target.get("sign") == "-":
        head = ["not", head]
    if not body:
        return None, {"why": "a_rule_with_no_body", "slot": None}
    body_vars = set(v for b in body for v in CO._vars_in(b))
    unbound = sorted(set(CO._vars_in(head)) - body_vars)
    if unbound:
        return None, {"why": "unbound_conclusion_variable",
                      "detail": ", ".join(unbound), "slot": None}
    seen = []
    for b in body:
        if CO._contradicts(b, head):
            return None, {"why": "a_premise_contradicts_the_head",
                          "detail": str(b)[:90], "slot": None}
        if b == head:
            return None, {"why": "the_head_repeats_a_premise",
                          "detail": str(b)[:90], "slot": None}
        if b in seen:
            return None, {"why": "a_premise_is_repeated",
                          "detail": str(b)[:90], "slot": None}
        seen.append(b)
    pkg, used = CO.package_of(body, head)
    unverified = [a for a in attach if a["status"] == "unverified_attachment"]
    rec = {
        "operator": opspec["name"], "target": target.get("from"),
        "target_label": target.get("text"), "target_kind": target["kind"],
        "direction_policy": opspec["direction"],
        "direction": plan.get("direction", "fixed"),
        "note": plan["note"],
        "generalized": bool(generalize),
        "generalized_constants": list(asm.generalized_constants),
        "quantified_variables": used,
        "slots": provenance["slots"],
        "slot_provenance": provenance["provenance"],
        "completions": provenance["completions"],
        "licence_occurrence": plan.get("licence"),
        "attachments": [{"guard": a["guard"]["occurrence_id"],
                         "status": a["status"],
                         "detail": a.get("identified") or a.get("shared")}
                        for a in attach],
        "has_unverified_attachment": bool(unverified),
        "uses_question_occurrence": sorted(set(
            payload["occurrence_id"]
            for kind, payload, _p in plan["body_items"] if kind == "occ"
            and payload.get("in_question")) | set(
            a["guard"]["occurrence_id"] for a in attach
            if a["guard"].get("in_question"))),
        "body": body, "head": head,
    }
    return {"package": pkg, "record": rec}, None


# ------------------------------------------------------------------ filling

def _occ_of(case, oid):
    occ = case["by_oid"].get(oid)
    if occ is None:
        raise SlotError("%s is not an occurrence in this case" % oid)
    if not CO.usable_source(occ):
        raise SlotError("%s is not a content atom this library can build from "
                        "(%s)" % (oid, occ.get("predicate")))
    return occ


def fill_named(case, opspec, proposal):
    """What the model named, checked slot by slot.  Nothing is reassigned."""
    filled, prov = {}, {}
    roles = dict(proposal.get("roles") or {})
    for s in opspec["slots"]:
        ids = list(roles.pop(s["name"], []) or [])
        if len(ids) > s["max"]:
            raise SlotError("slot `%s` takes at most %d, %d were named"
                            % (s["name"], s["max"], len(ids)))
        occs = []
        for oid in ids:
            occ = _occ_of(case, oid)
            if not s["form"](occ):
                raise SlotError("slot `%s`: %s is not %s"
                                % (s["name"], oid, s["form_note"]))
            occs.append(occ)
            prov[oid] = "named_by_model"
        if occs:
            filled[s["name"]] = occs
    for extra in roles:
        raise SlotError("%s has no slot called `%s` (its slots are %s)"
                        % (opspec["name"], extra,
                           ", ".join(opspec["slot_names"])))
    # the generic form: sources assigned to slots by code, and recorded as such
    for oid in list(proposal.get("sources") or []):
        occ = _occ_of(case, oid)
        placed = None
        for s in opspec["slots"]:
            if s["name"] == "guards":
                continue
            if len(filled.get(s["name"], [])) >= s["max"]:
                continue
            if s["form"](occ):
                filled.setdefault(s["name"], []).append(occ)
                prov[oid] = "assigned_by_code_to_%s" % s["name"]
                placed = s["name"]
                break
        if placed is None:
            raise SlotError("%s fills no free slot of %s"
                            % (oid, opspec["name"]))
    return filled, prov


def _anchor_units(filled):
    return set(o["unit_id"] for v in filled.values() for o in v)


def _candidates(case, opspec, s, filled, cap):
    """Occurrences that could fill this slot, ordered, never truncated silently."""
    used = set(o["occurrence_id"] for v in filled.values() for o in v)
    units = _anchor_units(filled)
    rows = []
    for oid in sorted(case["by_oid"], key=lambda k: int(k[1:])):
        occ = case["by_oid"][oid]
        if occ["occurrence_id"] in used or not CO.usable_source(occ):
            continue
        if not s["form"](occ):
            continue
        rows.append((0 if occ["unit_id"] in units else 1, int(oid[1:]), oid,
                     occ))
    rows.sort()
    return [(oid, occ) for _u, _n, oid, occ in rows[:cap]], len(rows)


def completions(case, opspec, filled, complete=True, complete_guards=True,
                slot_cap=MAX_COMPLETIONS, guard_cap=MAX_GUARD_CANDIDATES):
    """Every mechanically compatible way to fill what the model left empty.

    The model's own choices are anchors and are never replaced.  Each added
    occurrence is recorded with the slot it filled and why it was eligible.
    Combinations are ordered fewest-additions-first, so a proposal that needed
    nothing added is always built before one that needed two.
    """
    dims, counts, missing = [], {}, []
    for s in opspec["slots"]:
        have = filled.get(s["name"], [])
        if have:
            continue
        if s["name"] == "guards":
            if not complete_guards:
                continue
            cands, total = _candidates(case, opspec, s, filled, guard_cap)
            counts["guards"] = {"eligible": total, "kept": len(cands)}
            dims.append(("guards", [None] + cands))
            continue
        if s["required"] is True:
            if not complete:
                missing.append(s["name"])
                continue
            cands, total = _candidates(case, opspec, s, filled, slot_cap)
            counts[s["name"]] = {"eligible": total, "kept": len(cands)}
            if not cands:
                raise SlotError("slot `%s` is required and no occurrence in "
                                "this case can fill it (needs %s)"
                                % (s["name"], s["form_note"]))
            dims.append((s["name"], cands))
        elif s["required"] == "conditional":
            if not complete:
                continue
            cands, total = _candidates(case, opspec, s, filled, slot_cap)
            counts[s["name"]] = {"eligible": total, "kept": len(cands)}
            dims.append((s["name"], [None] + cands))
    if missing:
        raise SlotError("required slot(s) not filled: %s" % ", ".join(missing))
    combos = [[]]
    for name, cands in dims:
        combos = [c + [(name, x)] for c in combos for x in cands]
    combos.sort(key=lambda c: sum(1 for _n, x in c if x is not None))
    return combos, counts


def _apply_combo(filled, combo):
    out = dict((k, list(v)) for k, v in filled.items())
    added = []
    for name, x in combo:
        if x is None:
            continue
        oid, occ = x
        out.setdefault(name, []).append(occ)
        added.append({"slot": name, "occurrence": oid,
                      "why": "required slot was empty; this occurrence is %s"
                             % next(s["form_note"] for s in
                                    [t for o in OPERATORS for t in o["slots"]]
                                    if s["name"] == name)})
    return out, added


def build(case, proposal, complete=True, complete_guards=True,
          max_alternatives=MAX_ALTERNATIVES, slot_cap=MAX_COMPLETIONS,
          guard_cap=MAX_GUARD_CANDIDATES):
    """A named proposal -> checked alternatives, or a precise refusal.

    `complete=False` answers a different question: did the MODEL fill every
    required slot?  That is the measurement AL-68 could not make.
    """
    name = proposal.get("operator")
    if name not in BY_NAME:
        raise SlotError("unknown operator %r" % name)
    opspec = BY_NAME[name]
    if name == "other_restructure":
        raise SlotError("other_restructure builds nothing: the construction is "
                        "recorded as unsupported")
    target = CO.resolve_target(case, proposal.get("target"))
    filled, prov = fill_named(case, opspec, proposal)
    combos, counts = completions(case, opspec, filled, complete=complete,
                                 complete_guards=complete_guards,
                                 slot_cap=slot_cap, guard_cap=guard_cap)

    alts, refusals = [], []
    generated = 0
    for combo in combos:
        use, added = _apply_combo(filled, combo)
        guards = use.get("guards", [])
        provenance = {
            "slots": dict((k, [o["occurrence_id"] for o in v])
                          for k, v in use.items()),
            "provenance": dict(prov),
            "completions": added}
        try:
            plans = EMITTERS[name](case, target, use)
        except CO.ConstructionError as e:
            refusals.append({"why": str(e)[:200],
                             "completion": [a["occurrence"] for a in added]})
            continue
        for plan in plans:
            attach_choices = guard_attachments(plan, guards)
            if any(not c for c in attach_choices):
                refusals.append({
                    "why": "a guard shares no term with the rule and has no "
                           "variable to attach", "plan": plan["note"]})
                continue
            for attach in _combos(attach_choices,
                                  MAX_MAPPINGS_PER_COMPLETION):
                for generalize in (False, True):
                    generated += 1
                    alt, why = _assemble(case, target, opspec, plan, attach,
                                         generalize, provenance)
                    if why is not None:
                        refusals.append(dict(why, plan=plan["note"]))
                        continue
                    if any(a["package"] == alt["package"] for a in alts):
                        continue
                    alts.append(alt)
                    if len(alts) >= max_alternatives:
                        return {"alternatives": alts, "refusals": refusals,
                                "capped": True, "target": target,
                                "candidate_counts": counts,
                                "completion_combinations": len(combos),
                                "alternatives_generated": generated,
                                "operator": name}
    return {"alternatives": alts, "refusals": refusals, "capped": False,
            "target": target, "candidate_counts": counts,
            "completion_combinations": len(combos),
            "alternatives_generated": generated, "operator": name}


def refusal_reasons(got):
    """The distinct reasons a build produced nothing, in order.

    An emitter's structural refusal is recorded rather than raised, because
    another completion of the same proposal may still work.  When none does,
    these are the mechanical facts the model gets back.
    """
    out = []
    for r in (got or {}).get("refusals") or []:
        why = r.get("why") or ""
        if why not in out:
            out.append(why)
    return out


def names_slot(got, slot_name):
    return any(("`%s`" % slot_name) in w for w in refusal_reasons(got))


# ------------------------------------------------------------------ parsing

_FIELD = re.compile(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$")
_NONE = ("none", "-", "n/a", "na", "nothing", "", "[]", "()")
MAX_PROPOSALS = 3


def parse_response(text, known_oids, known_targets):
    """Read the final `PROPOSE:` and `REPORT:` lines and nothing else.

    Prose is never scraped, an unknown id is never snapped to a nearby one, and
    a line naming a role the operator does not have is rejected with the reason
    rather than reinterpreted.
    """
    proposes, reports = [], []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().strip("*_# ").upper()
        if key == "PROPOSE":
            proposes.append(v.strip())
        elif key == "REPORT":
            reports.append(v.strip())
    report = None
    for r in reports:
        want = r.strip().strip(".").lower().replace(" ", "_")
        if want in REPORT_OUTCOMES:
            report = want
    if not proposes:
        return {"readable": bool(report), "proposals": [], "rejected": [],
                "report": report, "lines_seen": 0, "lines_read": 0}
    kept = proposes[-MAX_PROPOSALS:]
    good, bad = [], []
    for line in kept:
        parsed, why = _parse_one(line, known_oids, known_targets)
        if why:
            bad.append({"line": line[:200], "why": why})
        else:
            good.append(parsed)
    return {"readable": True, "proposals": good, "rejected": bad,
            "report": report, "lines_seen": len(proposes),
            "lines_read": len(kept)}


def _parse_one(line, known_oids, known_targets):
    fields = []
    for chunk in line.split(";"):
        if not chunk.strip():
            continue
        m = _FIELD.match(chunk)
        if not m:
            return None, "not a field: %r" % chunk.strip()[:40]
        fields.append((m.group(1).lower(), m.group(2).strip()))
    got = dict(fields)
    if len(got) != len(fields):
        return None, "a field is given twice"
    op_name = (got.pop("operator", "") or "").strip().strip(".").lower()
    if op_name not in BY_NAME:
        return None, "unknown operator %r" % op_name[:40]
    opspec = BY_NAME[op_name]
    target = (got.pop("target", "") or "").strip().strip(".")
    if op_name != "other_restructure" and target not in known_targets:
        return None, "unknown target %r" % target[:40]
    roles, sources = {}, []
    for key, value in got.items():
        ids = _ids(value)
        if key == "sources":
            sources = ids
            continue
        if key not in opspec["slot_names"]:
            return None, ("%s has no slot called `%s` (its slots are %s)"
                          % (op_name, key, ", ".join(opspec["slot_names"])))
        if ids:
            roles[key] = ids
    for oid in sources + [i for v in roles.values() for i in v]:
        if oid not in known_oids:
            return None, "unknown occurrence %r" % oid
    if op_name != "other_restructure" and not roles and not sources:
        return None, "no sources named"
    return {"operator": op_name, "target": target, "roles": roles,
            "sources": sources}, None


def _ids(field):
    f = (field or "").strip().strip(".").lower()
    if f in _NONE:
        return []
    return re.findall(r"\bO\d+\b", (field or "").upper())


def known_targets(case):
    return CO.known_targets(case)


# ------------------------------------------------------------------ cards

def _required_text(s, opspec):
    if s["name"] == "guards":
        return "optional, up to %d" % s["max"]
    if s["required"] is True:
        return "required" + (", up to %d" % s["max"] if s["max"] > 1 else "")
    if s["required"] == "conditional":
        return "sometimes required"
    return "optional"


DIRECTION_TEXT = {
    FIXED: "one direction only, as described",
    SEMANTIC: "you choose the direction by choosing this operator; it runs "
              "from the more specific word to the more general one",
    BIDIRECTIONAL: "you name the two wordings; code builds BOTH directions as "
                   "separate hypotheses, so do not worry about which implies "
                   "which",
}


def operator_cards(operators=None):
    """The prompt's operator cards, generated from the same declarations the
    validator uses, so the two cannot drift apart."""
    out = []
    for o in operators or OPERATORS:
        out.append("%s" % o["name"])
        out.append("    %s" % o["summary"])
        for s in o["slots"]:
            out.append("    %-14s %-22s %s"
                       % (s["name"], _required_text(s, o), s["note"]))
            if s["form_note"]:
                out.append("    %-14s %-22s (%s)" % ("", "", s["form_note"]))
        out.append("    %-14s %s" % ("direction:", DIRECTION_TEXT[o["direction"]]))
        if o["note"]:
            out.append("    %-14s %s" % ("", o["note"]))
        out.append("    %-14s %s" % ("builds:", o["emits"]))
        out.append("")
    return "\n".join(out)


def proposal_line(opspec):
    """The exact line shape for one operator, for the prompt's format block."""
    bits = ["operator=%s" % opspec["name"], "target=<id>"]
    for s in opspec["slots"]:
        if s["name"] == "guards":
            bits.append("guards=NONE")
        else:
            bits.append("%s=<O id>" % s["name"])
    return "PROPOSE: " + "; ".join(bits)


# ------------------------------------------------------------------ ceiling
#
# The admissible space, enumerated without reference to any reviewed rule.  Each
# operator's DISCRIMINATING slots are anchored structurally — a compound_head
# proposal only ever offers a head whose word matches and a modifier that is the
# modifier — and the loose slots are left to completion.  Nothing is capped
# here; the caller passes the caps and the counts are reported.

def enumerate_targets(case):
    out = []
    for g in case["groups"]:
        if isinstance(g.get("label"), str) and g["label"] not in ("", "?"):
            out.append((g["group_id"], g["label"]))
    for e in case["labels"]:
        out.append((e["lid"], e["text"]))
    for oid in sorted(case["by_oid"], key=lambda k: int(k[1:])):
        occ = case["by_oid"][oid]
        if AO._is_var(occ.get("label") or ""):
            out.append(("%s.label" % oid, occ["label"]))
    return out


def enumerate_proposals(case):
    """Every proposal the library admits, anchored on its own structure."""
    occs = [(oid, case["by_oid"][oid]) for oid in
            sorted(case["by_oid"], key=lambda k: int(k[1:]))
            if CO.usable_source(case["by_oid"][oid])]
    out = []

    def add(op_name, tid, roles):
        out.append({"operator": op_name, "target": tid, "roles": roles,
                    "sources": []})

    for tid, ttext in enumerate_targets(case):
        parts = CO.compound_parts(ttext)
        if parts:
            mod, head_word = parts
            heads = [oid for oid, o in occs
                     if isinstance(o.get("label"), str) and CO.tokens(o["label"])
                     and CO.morph_related(CO.tokens(o["label"])[-1], head_word)]
            mods = [oid for oid, o in occs
                    if form_class(o)
                    and CO.normalize(o.get("label")) == CO.normalize(mod)]
            for h in heads:
                for m in mods:
                    if h != m:
                        add("compound_head", tid, {"head": [h], "modifier": [m]})
        for oid, o in occs:
            lab = o.get("label")
            if not isinstance(lab, str) or AO._is_var(lab):
                continue
            same = CO.normalize(lab) == CO.normalize(ttext)
            if not same and CO.label_related(lab, ttext):
                add("nominalization", tid, {"source": [oid]})
            if same and form_one_place(o):
                add("property_class_conversion", tid, {"source": [oid]})
                add("predication_transfer", tid, {"predication": [oid]})
            if not same:
                add("typed_taxonomy", tid, {"source": [oid]})
                if form_two_place(o):
                    add("role_or_relation_projection", tid, {"source": [oid]})
            if o["predicate"] == "has type" and CO.label_related(lab, ttext):
                ev = AO.bare_atom(o)[1]
                roles = [roid for roid, r in occs
                         if form_role(r) and r["unit_id"] == o["unit_id"]
                         and AO.bare_atom(r)[1] == ev]
                for i, r1 in enumerate(roles):
                    add("event_nominal_equivalence", tid,
                        {"event_type": [oid], "role": [r1]})
                    for r2 in roles[i + 1:]:
                        add("event_nominal_equivalence", tid,
                            {"event_type": [oid], "role": [r1],
                             "second_role": [r2]})
            if term_type(ttext) in PROMOTABLE and any(
                    isinstance(t, str)
                    and CO.normalize(t) == CO.normalize(ttext)
                    for _i, t in CO._participants_of(o)):
                add("argument_label_promotion", tid, {"carrier": [oid]})
        if tid.endswith(".label"):
            holder = tid[:-len(".label")]
            if holder in case["by_oid"]:
                add("label_variable_transport", tid, {"holder": [holder]})

    seen, uniq = set(), []
    for r in out:
        k = (r["operator"], r["target"],
             tuple(sorted((n, tuple(v)) for n, v in r["roles"].items())))
        if k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    return uniq
