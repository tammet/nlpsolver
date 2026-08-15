"""Mechanical facts about a guard.  No judgment of relevance.

The last memo proposed a mechanical rule — a guard may raise passage fidelity
only when its bearer occurs in the conclusion — and the rule is wrong.
folio-0184's `isa(animal, Y)` is the essential restriction on what is loved, and
Y never appears in `isa(animal lover, X)`.  Under that rule the one guard that
makes the rule mean what the words mean would have been penalised.

So this module states facts and stops.  Whether a guard is the right one is a
semantic question, and nothing here answers it:

    the unguarded base formula
    the guard atom, and the sentence it came from
    whether the head changed (it never does; recorded so the claim is checked)
    which variables the guard shares with the head, and with the other premises
    whether it adds a conjunct, so the rule fires no more often than before
    whether attaching it required identifying terms across two sentences

`shares_with_head` is reported beside `shares_with_other_premises`, and neither
is called good or bad.  A guard that shares only with the premises may be
essential — folio-0184 — and a guard that shares with the head may be a passage-
local specialisation that is not part of the words' meaning — folio-0184 again,
where `isa(pet owner, X)` does share X with the conclusion.

Pure: no file, no call, no gold.
"""

import re

VERSION = "guard_facts/1.0"

_VAR = re.compile(r"^V\d+$")
_VAR_IN_TEXT = re.compile(r"\bV\d+\b")


def _is_var(t):
    return isinstance(t, str) and bool(_VAR.match(t))


def _terms(lit):
    out = []

    def walk(n):
        if isinstance(n, list):
            for x in n:
                walk(x)
        elif isinstance(n, str):
            out.append(n)
    walk(lit)
    return out


def _vars(lit):
    """Variables in a literal, whether it is a list or its printed form.

    The challenge records a formula's body as printed atoms, so a term scan
    over list structure alone finds nothing; the printed form is scanned for
    variable tokens instead.
    """
    out = set()
    for t in _terms(lit):
        if _is_var(t):
            out.add(t)
        else:
            out.update(_VAR_IN_TEXT.findall(t))
    return sorted(out)


def _strip(lit):
    while isinstance(lit, list) and len(lit) == 2 and lit[0] == "not":
        lit = lit[1]
    return lit


def _signature(lit):
    """(predicate, label) — enough to match a guard atom to a body literal."""
    if isinstance(lit, str):
        return _parse_atom(lit)
    atom = _strip(lit)
    if not isinstance(atom, list) or not atom:
        return (None, None)
    pred = atom[0]
    label = atom[1] if len(atom) > 1 and isinstance(atom[1], str) else None
    return (pred, label)


def _parse_atom(text):
    """`has degree property(dead, Y, none, organism)` -> (pred, label)."""
    m = re.match(r"^\s*(?:not\s+)?([a-z][a-z0-9 _]*)\(([^,)]*)", text or "")
    if not m:
        return (None, None)
    return (m.group(1).strip(), m.group(2).strip())


def guard_facts(body, head, guards, attachments=(), all_extra_premises=True):
    """-> facts for each restricting literal in this body.  Judgment-free.

    `guards` are the challenge's guard records: an occurrence id, the atom as
    written in its own sentence, that sentence, and who added it.

    With `all_extra_premises`, every body literal after the first is also
    described, whether or not it arrived through a `guards` slot.  folio-0184's
    `isa(animal, Y)` is the essential restriction on what is loved and it comes
    from the operator's MODIFIER slot, so a facts table keyed only on guard
    slots would not mention the one restriction that matters most.
    """
    rows, used = [], set()
    for g in guards or []:
        sig = _parse_atom(g.get("atom"))
        hit = None
        for i, lit in enumerate(body):
            if i in used:
                continue
            if _signature(lit) == sig:
                hit = i
                break
        if hit is None:
            rows.append({"guard_occurrence": g.get("occurrence"),
                         "guard_atom_as_written": g.get("atom"),
                         "found_in_the_formula": False,
                         "added_by": g.get("added_by"),
                         "source_sentence": g.get("sentence")})
            continue
        used.add(hit)
        guard_lit = body[hit]
        base = [b for i, b in enumerate(body) if i != hit]
        gv = set(_vars(guard_lit))
        hv = set(_vars(head))
        bv = set(v for b in base for v in _vars(b))
        invented = [a for a in (attachments or [])
                    if a.get("status") == "unverified_attachment"]
        rows.append({
            "guard_occurrence": g.get("occurrence"),
            "guard_atom_as_written": g.get("atom"),
            "guard_literal_in_the_formula": guard_lit,
            "found_in_the_formula": True,
            "added_by": g.get("added_by"),
            "source_sentence": g.get("sentence"),
            "unguarded_base_formula": {"body": base, "head": head},
            "head_unchanged": True,
            "variables_in_the_guard": sorted(gv),
            "shares_with_head": sorted(gv & hv),
            "shares_with_other_premises": sorted(gv & bv),
            "shares_nothing": not (gv & (hv | bv)),
            "adds_a_conjunct": True,
            "fires_no_more_often_than_the_base": True,
            "attachment_required_a_cross_sentence_identification":
                bool(invented),
            "cross_sentence_identifications": invented,
            "role": "guard_slot",
            "note": "these are facts about shape and provenance; whether the "
                    "restriction is the right one is not decided here",
        })
    if all_extra_premises:
        for i, lit in enumerate(body):
            if i == 0 or i in used:
                continue
            gv = set(_vars(lit))
            hv = set(_vars(head))
            bv = set(v for j, b in enumerate(body) if j != i
                     for v in _vars(b))
            rows.append({
                "guard_occurrence": None,
                "guard_atom_as_written": None,
                "guard_literal_in_the_formula": lit,
                "found_in_the_formula": True,
                "added_by": "operator slot",
                "source_sentence": None,
                "unguarded_base_formula": {
                    "body": [b for j, b in enumerate(body) if j != i],
                    "head": head},
                "head_unchanged": True,
                "variables_in_the_guard": sorted(gv),
                "shares_with_head": sorted(gv & hv),
                "shares_with_other_premises": sorted(gv & bv),
                "shares_nothing": not (gv & (hv | bv)),
                "adds_a_conjunct": True,
                "fires_no_more_often_than_the_base": True,
                "attachment_required_a_cross_sentence_identification": False,
                "cross_sentence_identifications": [],
                "role": "operator_slot_premise",
                "note": "a restricting premise the operator required rather "
                        "than a guard anyone added; described for the same "
                        "reasons and judged no differently",
            })
    return rows


def summarise(rows):
    return {
        "guards": len(rows),
        "from_a_guard_slot": sum(1 for r in rows
                                 if r.get("role") == "guard_slot"),
        "from_an_operator_slot": sum(
            1 for r in rows if r.get("role") == "operator_slot_premise"),
        "guards_found_in_the_formula": sum(1 for r in rows
                                           if r.get("found_in_the_formula")),
        "guards_added_by_code": sum(1 for r in rows
                                    if r.get("added_by") == "code"),
        "guards_sharing_with_the_head": sum(1 for r in rows
                                            if r.get("shares_with_head")),
        "guards_sharing_only_with_other_premises": sum(
            1 for r in rows if r.get("found_in_the_formula")
            and not r.get("shares_with_head")
            and r.get("shares_with_other_premises")),
        "guards_sharing_nothing": sum(1 for r in rows
                                      if r.get("shares_nothing")),
        "guards_needing_a_cross_sentence_identification": sum(
            1 for r in rows
            if r.get("attachment_required_a_cross_sentence_identification")),
    }
