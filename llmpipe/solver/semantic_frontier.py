"""Source-level semantic groups over the AL-66 interface frontier.

The frontier is hundreds of final-clause literals per case (median 928).  Most
of that count is the compiler talking to itself: the same content expression
appears once per context variable, once per reified event term, once per skolem
witness and once per copy introduced by a frame axiom.  None of those
distinctions is visible in the English, and none of them is a different thing to
ask a reader about.

A **semantic group** is one content expression: a sign, a predicate family, the
content label, and the participants that a person could point at in the source
sentence.  Everything the compiler invented — context and world arguments,
`$ev_of` reifications, skolem constants, unbound variables — collapses into
*variants* of the group and is kept, so nothing is lost, only folded.

Two things are deliberately not folded:

* **The two question targets stay apart.**  Whether the question needs `part of`
  or its denial is the difference between two different rules, and a group that
  mixed them would hide exactly the distinction the earlier work got wrong.
* **Material with no source link is set aside**, not merged into the content
  groups.  A frame axiom talking to another frame axiom is not something to ask
  a reader about; it goes to a low-priority list that is reported and not shown.

Nothing here reads a reviewed rule, an accepted answer or a label.
"""

import collections
import json
import os
import re

# v1 stripped every term at its first "#".  That is right for the freshening
# suffix a converter appends to a variable (`?:X#12_34`) and wrong for a
# UNA-marked entity constant, which BEGINS with the marker: `#:Tom 1` became the
# empty string, so 176 of 1,217 groups showed a reader a blank where a name
# belongs.  v2 strips only the suffix, and only from a variable.
#
# v1 stays reachable because the AL-67 artifact was closed under it and must
# still rebuild byte for byte; nothing new should use it.
STRIP_TAG_MODES = ("v1", "v2")
STRIP_TAG_MODE = os.environ.get("SEMANTIC_FRONTIER_STRIP", "v2")
if STRIP_TAG_MODE not in STRIP_TAG_MODES:
    raise ValueError("SEMANTIC_FRONTIER_STRIP must be one of %s"
                     % (STRIP_TAG_MODES,))

VERSION = ("semantic_frontier/1.0" if STRIP_TAG_MODE == "v1"
           else "semantic_frontier/2.0")

ANY = "?"

# Compiler-created argument material.  These are positions the source never
# mentions: contexts and the event terms reification invents.
#
# Only names the converter itself generates are listed.  A bare `?:C` or `?:W`
# is NOT one: eb2-0121's reviewed rule calls the cell `C` and eb2-0055's calls
# a participant `W`, and treating those as contexts dropped a real participant
# and produced a zero-argument group for a one-argument predicate.
CONTEXT_VAR = re.compile(r"^\?:(Ctxt|Cre|Cu\d+|Cub\d+|Fv\d+)\b")
CONTEXT_COMPOUND = ("$ctxt",)
EVENT_COMPOUND = ("$ev_of",)
SKOLEM = re.compile(r"^(sk\d+\w*|\$some_\w+|\$not_\w+)$")

# Predicates whose arguments are all compiler plumbing rather than content.
PLUMBING_PREDICATES = {
    "is_past_world", "is_future_world", "is_present_world", "next", "before",
    "after", "member", "is set of", "$block",
}


def strip_tag(v):
    """`?:X#12_34` -> `?:X`, and `#:Tom 1` -> `#:Tom 1`.

    The freshening tag is per application, not content, so it goes.  A
    UNA-marked entity constant is content and is never touched: the marker is a
    prefix, so splitting on "#" would erase the whole name.
    """
    if not isinstance(v, str):
        return v
    if STRIP_TAG_MODE == "v1":
        return v.split("#")[0]
    return v.split("#")[0] if v.startswith("?:") else v


def is_context_arg(term):
    if isinstance(term, str):
        return bool(CONTEXT_VAR.match(strip_tag(term)))
    if isinstance(term, list) and term:
        return term[0] in CONTEXT_COMPOUND
    return False


def normalize_participant(term):
    """A participant as the source would name it, or `?`.

    A URL, a quoted entity, a lexical constant: kept as itself.  A variable, a
    skolem witness, a populated placeholder or a reified event term: `?`, since
    the source names none of them and telling them apart makes variants, not
    groups.
    """
    if isinstance(term, list):
        if term and term[0] in EVENT_COMPOUND:
            return ANY
        return ANY
    if not isinstance(term, str):
        return ANY
    t = strip_tag(term)
    if t.startswith("?:"):
        return ANY
    if SKOLEM.match(t):
        return ANY
    return t


def label_slot(predicate):
    import alignment_occurrences as AO
    return AO.LABEL_SLOT.get(predicate)


def content_of(literal):
    """-> (label, participants) with compiler arguments removed."""
    import demand_regression as DR
    pred = DR.bare(literal)
    args = DR.args_of(literal)
    slot = label_slot(pred)
    label = None
    if slot is not None and slot < len(args):
        v = args[slot]
        label = strip_tag(v) if isinstance(v, str) and not v.startswith("?:") \
            else ANY
    parts = []
    for i, a in enumerate(args):
        if slot is not None and i == slot:
            continue
        if is_context_arg(a):
            continue
        parts.append(normalize_participant(a))
    return label, parts


def group_key(literal, question_target):
    import demand_regression as DR
    label, parts = content_of(literal)
    return (question_target, DR.sign_of(literal), DR.bare(literal),
            label, tuple(parts))


def readable(key):
    """The group as a person would read it."""
    _target, sign, pred, label, parts = key
    inner = ([label] if label is not None else []) + list(parts)
    return "%s%s(%s)" % ("not " if sign == "-" else "", pred,
                         ", ".join(inner))


# ---------------------------------------------------------------- sources

UNIT = re.compile(r"^sent_(S\d+)$")


def source_units(chains):
    out = []
    for chain in chains or []:
        for name in chain or []:
            m = UNIT.match(name or "")
            if m and m.group(1) not in out:
                out.append(m.group(1))
    return out


def clause_kinds(chains):
    kinds = set()
    for chain in chains or []:
        for name in chain or []:
            if UNIT.match(name or ""):
                kinds.add("source sentence")
            elif name == "static_axiom":
                kinds.add("standard axiom")
            elif (name or "").startswith("frm_"):
                kinds.add("frame axiom")
            elif (name or "").startswith("compound_"):
                kinds.add("compound axiom")
            elif name:
                kinds.add(name)
    return sorted(kinds)


def source_vocabulary(stored):
    """The (predicate, label) pairs the problem's own sentences actually use.

    This is what "source-linked" has to mean.  Every regression path begins at
    the question's own clause, so "some source clause appears in the chain" is
    true of almost everything and separates nothing; what distinguishes content
    from plumbing is whether the expression's own predicate and label occur in
    the source at all.
    """
    import demand_regression as DR
    vocab = set()
    for c in stored.get("final_clauses") or []:
        if not isinstance(c, dict) or "@question" in c:
            continue
        if not UNIT.match(c.get("@name") or ""):
            continue
        if c.get("@sourcetype") == "populate":
            continue
        for lit in DR.literals_of(c.get("@logic")) or []:
            if DR.classify_literal(lit) != DR.ORDINARY:
                continue
            label, _parts = content_of(lit)
            vocab.add((DR.bare(lit), label))
    return vocab


def build(case, unit_roles=None, unit_texts=None, vocabulary=None):
    """-> {"groups": [...], "low_priority": [...], "counts": {...}}.

    `case` is one AL-65/AL-66 raw case record.  `unit_roles` and `unit_texts`
    map `S3` to its role and its sentence; `vocabulary` is the problem's own
    (predicate, label) pairs.  All three come from the stored parse, not from
    anything reviewed.
    """
    import demand_regression as DR
    groups, low = collections.OrderedDict(), collections.OrderedDict()
    for i in case["analysis"].get("interfaces", []):
        pred = i["predicate"]
        if not isinstance(pred, str) or pred.startswith("$"):
            continue                      # $defq roots, $block, other control
        lit = i.get("instantiated_literal") or []
        if not lit:
            continue
        key = group_key(lit, i["question_target"])
        units = source_units(i.get("example_chains"))
        # content the source never uses is set aside, never merged in
        in_vocab = vocabulary is None or (key[2], key[3]) in vocabulary
        target = groups if (in_vocab and not _all_plumbing(pred)) else low
        g = target.get(key)
        if g is None:
            g = {"key": list(key), "question_target": key[0],
                 "sign": key[1], "predicate": key[2], "label": key[3],
                 "participants": list(key[4]),
                 "readable": readable(key),
                 "variants": 0, "occurrences": 0,
                 "min_depth": i.get("min_depth", i.get("depth")),
                 "kinds": set(), "source_units": [], "clause_kinds": set(),
                 "axiom_only": True, "examples": []}
            target[key] = g
        g["variants"] += 1
        g["occurrences"] += i.get("occurrences", 1)
        g["min_depth"] = min(g["min_depth"], i.get("min_depth",
                                                   i.get("depth")))
        g["kinds"].add(i["kind"])
        g["clause_kinds"] |= set(clause_kinds(i.get("example_chains")))
        for u in units:
            if u not in g["source_units"]:
                g["source_units"].append(u)
        if not i.get("axiom_internal"):
            g["axiom_only"] = False
        if len(g["examples"]) < 3:
            g["examples"].append(i["signed_literal"][:120])

    def finish(d, low_priority):
        out = []
        for g in d.values():
            g = dict(g)
            g["kinds"] = sorted(g["kinds"])
            g["clause_kinds"] = sorted(g["clause_kinds"])
            g["source_units"] = sorted(g["source_units"])
            g["roles"] = sorted(set((unit_roles or {}).get(u, "unknown")
                                    for u in g["source_units"])) or ["none"]
            g["source_sentences"] = [(unit_texts or {}).get(u)
                                     for u in g["source_units"]
                                     if (unit_texts or {}).get(u)]
            g["low_priority"] = low_priority
            g.pop("key")
            out.append(g)
        out.sort(key=_order)
        for n, g in enumerate(out, start=1):
            g["group_id"] = "G%d" % n
        return out

    gs = finish(groups, False)
    ls = finish(low, True)
    for n, g in enumerate(ls, start=1):
        g["group_id"] = "L%d" % n
    return {"version": VERSION, "groups": gs, "low_priority": ls,
            "counts": {"groups": len(gs), "low_priority": len(ls),
                       "variants": sum(g["variants"] for g in gs + ls),
                       "by_target": dict(collections.Counter(
                           g["question_target"] for g in gs))}}


def _all_plumbing(pred):
    return pred in PLUMBING_PREDICATES


def _order(g):
    """Shallow first, then source-linked before axiom-only, then readable form.

    Fixed here, before any reviewed rule is loaded, and identical in spirit to
    the frontier ordering it replaces.
    """
    return (g["min_depth"], 1 if g["axiom_only"] else 0,
            -len([p for p in g["participants"] if p != ANY]),
            g["readable"], g["question_target"])


# ---------------------------------------------------------------- matching

def matches_group(head_literal, group):
    """Does a rule head belong to this group?

    The same content test the grouping itself uses — sign, predicate, label and
    normalized participants — so a head and its instance land together whatever
    context or witness the compiler gave them.
    """
    import demand_regression as DR
    label, parts = content_of(head_literal)
    if DR.sign_of(head_literal) != group["sign"]:
        return False
    if DR.bare(head_literal) != group["predicate"]:
        return False
    if label != group["label"] and not (label == ANY or group["label"] == ANY):
        return False
    gp = group["participants"]
    if len(parts) != len(gp):
        return False
    for a, b in zip(parts, gp):
        if a == ANY or b == ANY:
            continue
        if a != b:
            return False
    return True
