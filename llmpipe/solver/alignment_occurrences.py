"""Source-linked occurrence table over a stored Stage-1 / Stage-2 pair (DA2 WP1).

Plan: memos/PLAN_2026_08_09_dynamic_abstraction_alignment_pilot_opus5.md §7.

An occurrence is one use of an entity, class, property, relation, event, event
role, rule variable or question proposition, tied to the JSON path it came from
and, where the text supports it, to a span of the source sentence.  The table is
provenance for the issue detectors and for readable prompt construction; it is
never an interpretation of the sentence.

Deliberate limits:

  * a source span is recorded only when the label occurs literally in the unit's
    sentence.  One hit is `exact`, several are `repeated` (all offsets kept, none
    chosen), none is `unavailable`.  Offsets are never invented.
  * Stage-1 and Stage-2 occurrences are paired only on explicit evidence (§7.3).
    Two labels being synonyms, or overlapping in tokens, is not evidence.

No LLM calls, no GK, no conversion: this module reads stored JSON only.
"""

import re

# Formula heads that structure a package rather than assert something.
LOGICAL_HEADS = {
    "and", "or", "not", "xor", "implies", "forall", "exists", "normally",
    "holds", "question", "ask", "@id", "@p", "kb", "kb force", "kb holds",
}

# Predicate -> the kind of occurrence its atom introduces.
RELATION_PREDS = {
    "is rel2", "have", "has part", "member", "=", "has degree rel2",
}
PROPERTY_PREDS = {"has property", "has degree property"}
ROLE_PREDS = {
    "has actor", "has target", "has recipient", "has source", "has instrument",
    "has manner", "has beneficiary", "has accompaniment", "has topic",
    "has result", "has path", "has direction", "has content", "has cause",
    "has time", "has location", "has destination", "state time",
}
MODAL_PREDS = {
    "typical", "capability", "necessity", "obligation", "volition",
    "intention", "expectation", "speech_act", "actuality",
}

# Arity-independent: which argument of an atom carries the label, and which
# carry terms.  `label_slot` is the 0-based index into the atom's arguments.
LABEL_SLOT = {
    "isa": 0, "has type": 1, "is rel2": 0, "has property": 0,
    "has degree property": 0, "has degree rel2": 0,
}


def _is_var(tok):
    return isinstance(tok, str) and bool(re.match(r"^[A-Z][A-Za-z0-9_]*$", tok))


def normalize_label(label):
    """Lowercase, collapse whitespace, drop a leading determiner and a trailing
    Stage-1 entity number.  Multiword labels stay whole."""
    if not isinstance(label, str):
        return ""
    t = re.sub(r"\s+", " ", label.strip().lower())
    t = re.sub(r"^(the|a|an) ", "", t)
    t = re.sub(r"^#:", "", t)
    t = re.sub(r" \d+$", "", t)
    return t


def _spans(text, needle):
    """All literal spans of `needle` in `text`, case-insensitively."""
    if not text or not needle or not isinstance(needle, str):
        return []
    out, low, n = [], text.lower(), needle.lower().strip()
    if not n:
        return []
    i = low.find(n)
    while i >= 0:
        out.append([i, i + len(n)])
        i = low.find(n, i + 1)
    return out


def _match_status(spans):
    if not spans:
        return "unavailable"
    return "exact" if len(spans) == 1 else "repeated"


class Occurrence(dict):
    """A dict with the contract of plan §5.1; dict so it serialises directly."""

    @property
    def id(self):
        return self["occurrence_id"]


def _mk(unit_id, stage, path, kind, label, term, sentence, **kw):
    spans = _spans(sentence, label if isinstance(label, str) else None)
    occ = Occurrence({
        "occurrence_id": "%s:%s:%s" % (unit_id, stage, path),
        "unit_id": unit_id,
        "source_sentence": sentence,
        "source_quote": label if spans else None,
        "source_offsets": spans or None,
        "source_match_status": _match_status(spans),
        "stage": stage,
        "json_path": path,
        "kind": kind,
        "label": label,
        "normalized_label": normalize_label(label),
        "term": term,
        "arguments_or_roles": kw.pop("arguments_or_roles", None),
        "polarity": kw.pop("polarity", "+"),
        "binder_stack": kw.pop("binder_stack", []),
        "rule_side": kw.pop("rule_side", "none"),
    })
    occ.update(kw)
    return occ


# ---------------------------------------------------------------- Stage 1

def _units(stage1):
    for si, sent in enumerate(stage1 or []):
        if not isinstance(sent, dict):
            continue
        for ui, u in enumerate(sent.get("units") or []):
            yield si, ui, sent, u


def extract_stage1(stage1):
    """-> [Occurrence] for entities, action roots and roles, and modifiers."""
    out = []
    for si, ui, sent, u in _units(stage1):
        uid = u.get("unit_id") or "S?"
        text = u.get("text") or sent.get("raw") or ""
        base = "/%d/units/%d" % (si, ui)
        for ei, e in enumerate(u.get("entities") or []):
            out.append(_mk(uid, "stage1", "%s/entities/%d" % (base, ei),
                           "entity", e.get("id"), e.get("id"), text,
                           entity_type=e.get("type"),
                           category=e.get("category"),
                           scope=e.get("scope"),
                           unit_type=u.get("type")))
        for ai, act in enumerate(u.get("actions") or []):
            roles = act.get("roles") or {}
            out.append(_mk(uid, "stage1", "%s/actions/%d" % (base, ai),
                           "event", act.get("root"), None, text,
                           arguments_or_roles=dict(roles),
                           mode=act.get("mode"), unit_type=u.get("type")))
            for rname, filler in sorted(roles.items()):
                out.append(_mk(uid, "stage1",
                               "%s/actions/%d/roles/%s" % (base, ai, rname),
                               "event_role", filler, filler, text,
                               role=rname, action_root=act.get("root"),
                               unit_type=u.get("type")))
        for ji, adj in enumerate(u.get("adjectives") or []):
            if not isinstance(adj, list) or not adj:
                continue
            label = adj[0]
            bearer = adj[2] if len(adj) > 2 else None
            out.append(_mk(uid, "stage1", "%s/adjectives/%d" % (base, ji),
                           "property", label, bearer, text,
                           bearer=bearer, degree=adj[1] if len(adj) > 1 else None,
                           unit_type=u.get("type")))
    return out


# ---------------------------------------------------------------- Stage 2

def packages(stage2):
    out = []
    if isinstance(stage2, list) and stage2 and stage2[0] == "and":
        for it in stage2[1:]:
            if isinstance(it, list) and len(it) >= 3 and it[0] == "@id":
                out.append((it[1], it[2]))
    return out


def _atom_occurrences(atom, unit_id, path, sentence, binders, side, polarity,
                      in_question):
    """One predicate atom -> zero or more occurrences."""
    pred = atom[0]
    args = atom[1:]
    kind = ("class" if pred == "isa" else
            "property" if pred in PROPERTY_PREDS else
            "relation" if pred in RELATION_PREDS else
            "event_role" if pred in ROLE_PREDS else
            "event" if pred == "has type" else
            "modal" if pred in MODAL_PREDS else
            "other")
    slot = LABEL_SLOT.get(pred)
    label = args[slot] if (slot is not None and slot < len(args)) else pred
    if pred == "has type":
        label = args[1] if len(args) > 1 else pred
    terms = [a for i, a in enumerate(args) if i != slot]
    event_term = None
    if pred in ROLE_PREDS and len(args) >= 2:
        # A role atom is about its filler: ["has target", E, filler].  Carrying
        # the event as the term would make every role occurrence look like the
        # event and hide the filler from the detectors.
        event_term = args[0]
        terms = [args[1]] + [a for a in args[2:]]
    occ = _mk(unit_id, "s2", path, kind, label if isinstance(label, str) else pred,
              terms[0] if terms else None, sentence,
              predicate=pred, event_term=event_term,
              arguments_or_roles=list(args),
              polarity=polarity, binder_stack=list(binders), rule_side=side,
              in_question=in_question,
              term_is_variable=_is_var(terms[0]) if terms else None,
              label_is_variable=_is_var(label))
    out = [occ]
    # a bound variable used as a term is itself an occurrence worth naming
    for ai, a in enumerate(args):
        if _is_var(a) and any(b[1] == a for b in binders):
            out.append(_mk(unit_id, "s2", "%s/%d" % (path, ai + 1),
                           "rule_variable", a, a, sentence,
                           predicate=pred, arg_index=ai,
                           term_is_variable=True, label_is_variable=True,
                           polarity=polarity, binder_stack=list(binders),
                           rule_side=side, in_question=in_question))
    return out


def extract_stage2(stage2, stage1=None):
    """-> [Occurrence] over the raw packages, before any conversion."""
    text_by_unit = {}
    for si, ui, sent, u in _units(stage1 or []):
        text_by_unit[u.get("unit_id")] = u.get("text") or sent.get("raw") or ""
    out = []

    def walk(node, unit_id, path, binders, side, polarity, in_question):
        if not isinstance(node, list) or not node:
            return
        head = node[0]
        if not isinstance(head, str):
            for i, ch in enumerate(node):
                walk(ch, unit_id, "%s/%d" % (path, i), binders, side, polarity,
                     in_question)
            return
        sentence = text_by_unit.get(unit_id, "")
        if head in ("forall", "exists") and len(node) >= 3:
            walk(node[2], unit_id, "%s/2" % path, binders + [(head, node[1])],
                 side, polarity, in_question)
            return
        if head == "implies" and len(node) == 3:
            walk(node[1], unit_id, "%s/1" % path, binders, "antecedent",
                 polarity, in_question)
            walk(node[2], unit_id, "%s/2" % path, binders, "conclusion",
                 polarity, in_question)
            return
        if head == "not" and len(node) == 2:
            walk(node[1], unit_id, "%s/1" % path, binders, side,
                 "-" if polarity == "+" else "+", in_question)
            return
        if head == "question":
            walk(node[1], unit_id, "%s/1" % path, binders, side, polarity, True)
            return
        if head == "ask" and len(node) == 3:
            walk(node[2], unit_id, "%s/2" % path, binders + [("ask", node[1])],
                 side, polarity, True)
            return
        if head == "holds" and len(node) == 3:
            walk(node[2], unit_id, "%s/2" % path, binders, side, polarity,
                 in_question)
            return
        if head in LOGICAL_HEADS:
            for i, ch in enumerate(node[1:], start=1):
                walk(ch, unit_id, "%s/%d" % (path, i), binders, side, polarity,
                     in_question)
            return
        out.extend(_atom_occurrences(node, unit_id, path, sentence, binders,
                                     side, polarity, in_question))

    for uid, pkg in packages(stage2):
        walk(pkg, uid, "", [], "none", "+", False)
    return out


# ---------------------------------------------------------------- literals

def bare_atom(occ):
    """The occurrence's atom, WITHOUT its sign.  Rarely what you want."""
    args = occ.get("arguments_or_roles")
    if not isinstance(args, list) or not occ.get("predicate"):
        raise ValueError("occurrence %s carries no atom"
                         % occ.get("occurrence_id"))
    return [occ["predicate"]] + list(args)


def signed_literal(occ):
    """The occurrence's COMPLETE Stage-2 literal, sign included.

    The one authoritative conversion from an occurrence to logic.  An
    occurrence records the polarity it was found under — `-` inside a `not`, or
    in a negated position — and dropping it silently turns
    `not mean(X,Y) -> not mean(X,Y)` into `mean(X,Y) -> mean(X,Y)`, which is a
    different rule about different things.  That is exactly what happened to
    folio-0183 in the 08-10 pilot.

    The sign comes from `polarity` and from nowhere else.  In particular it is
    NOT read off `supply`/`contradiction`: those describe how a pair could be
    used in a proof, not what the literal says.
    """
    atom = bare_atom(occ)
    return ["not", atom] if occ.get("polarity") == "-" else atom


def literal_sign(occ):
    return "-" if occ.get("polarity") == "-" else "+"


# ---------------------------------------------------------------- pairing

def pair(stage1_occs, stage2_occs):
    """Explicit-evidence pairing only (§7.3).

    Four admissible reasons, all requiring an identical string on both sides
    within the same unit: entity id, action root, modifier label with its
    declared bearer, and a bound variable's class.  A synonym or a token
    overlap is never a reason, so unmatched occurrences stay visible instead of
    being paired optimistically.
    """
    pairs, s2_by_unit = [], {}
    for o in stage2_occs:
        s2_by_unit.setdefault(o["unit_id"], []).append(o)
    for s1 in stage1_occs:
        uid = s1["unit_id"]
        cands = s2_by_unit.get(uid, [])
        n1 = s1["normalized_label"]
        for s2 in cands:
            reason = None
            if s1["kind"] == "entity" and n1 and (
                    normalize_label(s2.get("term")) == n1
                    or s2["normalized_label"] == n1):
                reason = "same unit and identical entity id"
            elif s1["kind"] == "event" and s2["kind"] == "event" \
                    and s2["normalized_label"] == n1:
                reason = "same unit and identical action root"
            elif s1["kind"] == "event_role" and s2["kind"] == "event_role" \
                    and normalize_label(s2.get("term")) == n1:
                reason = "same unit and identical explicit role filler"
            elif s1["kind"] == "property" and s2["kind"] == "property" \
                    and s2["normalized_label"] == n1:
                reason = "same unit and identical modifier label"
            if reason:
                pairs.append({"stage1": s1["occurrence_id"],
                              "stage2": s2["occurrence_id"],
                              "reason": reason})
    paired1 = set(p["stage1"] for p in pairs)
    paired2 = set(p["stage2"] for p in pairs)
    return {
        "pairs": pairs,
        "unpaired_stage1": [o["occurrence_id"] for o in stage1_occs
                            if o["occurrence_id"] not in paired1],
        "unpaired_stage2": [o["occurrence_id"] for o in stage2_occs
                            if o["occurrence_id"] not in paired2
                            and o["kind"] not in ("rule_variable", "modal")],
    }


def extract(stage1, stage2):
    s1 = extract_stage1(stage1)
    s2 = extract_stage2(stage2, stage1)
    return {"stage1": s1, "stage2": s2, "pairing": pair(s1, s2),
            "by_id": {o["occurrence_id"]: o for o in s1 + s2}}


# ---------------------------------------------------------------- rendering

def render_unit(table, unit_id, concerns=None):
    """The compact critic view of one unit (§7.3).

    Assistance, not a substitute: the critic also receives the full Stage-2
    JSON, so nothing here needs to be lossless.
    """
    s1 = [o for o in table["stage1"] if o["unit_id"] == unit_id]
    s2 = [o for o in table["stage2"] if o["unit_id"] == unit_id]
    sentence = (s1 or s2 or [{}])[0].get("source_sentence") or ""
    lines = ["%s English: %s" % (unit_id, sentence)]
    parts = []
    for o in s1:
        if o["kind"] == "event":
            roles = o.get("arguments_or_roles") or {}
            parts.append("action %s(%s)" % (
                o["label"], ",".join("%s=%s" % (k, v)
                                     for k, v in sorted(roles.items()))))
        elif o["kind"] == "property":
            parts.append("%s modifies %s" % (o["label"], o.get("bearer")))
        elif o["kind"] == "entity":
            parts.append("entity %s(%s)" % (o["label"], o.get("entity_type")))
    if parts:
        lines.append("Stage 1: " + "; ".join(parts))
    parts = []
    for o in s2:
        if o["kind"] == "rule_variable":
            continue
        term = o.get("term")
        shape = ("variable" if o.get("term_is_variable") else
                 "kind constant" if isinstance(term, str) and not _is_var(term)
                 else "term")
        side = "" if o["rule_side"] == "none" else " [%s]" % o["rule_side"]
        q = " [question]" if o.get("in_question") else ""
        head = o["label"] if o["label"] == o.get("predicate") else \
            "%s %s" % (o.get("predicate"), o["label"])
        parts.append("%s=%s(%s)%s%s" % (head, term, shape, side, q))
    if parts:
        lines.append("Stage 2: " + "; ".join(parts))
    for c in concerns or []:
        lines.append("Detected concern: " + c)
    return "\n".join(lines)
