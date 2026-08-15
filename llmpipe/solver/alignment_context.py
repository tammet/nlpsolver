"""Bounded, source-linked context around a Stage-2 occurrence.

An atom pulled out of a larger formula loses the conditions that made it true.
`is rel2(love, X, Y)` in

    forall X . ( isa("pet owner", X) ->
                 forall Y . ( isa(animal, Y) -> is rel2(love, X, Y) ) )

is not "X loves Y" — the loved thing is an animal, and that restriction is what
the reviewed animal-lover bridge needs.  A rule built from the atom alone is
too strong, and chain v2 built exactly that rule twice.

So an occurrence gets a small menu of COMPANION conditions, each with the reason
it was offered:

    nearest_conjunction   a sibling conjunct of the atom
    quantifier_guard      the antecedent of an enclosing quantified implication,
                          with its distance (1 = innermost)
    shared_variable       another atom in the same package using one of the
                          atom's variables
    shared_entity         an atom anywhere using one of its grounded entities
    same_unit             anything else from the same sentence, capped

Two things this deliberately does not do.  It does not decide which companions
belong in the rule — `isa("pet owner", X)` above is a guard, and offering it is
right, but forcing it into a general lexical bridge from loving animals to being
an animal lover is not.  And it does not copy every outer premise: the menu is
capped and ordered, and everything in it is an existing occurrence with an
existing id.
"""

import re

import alignment_issues as AI
import alignment_occurrences as AO

REASONS = ("nearest_conjunction", "quantifier_guard", "shared_variable",
           "shared_entity", "same_unit")
REASON_RANK = {r: i for i, r in enumerate(REASONS)}
DEFAULT_CAP = 8
SAME_UNIT_CAP = 3


def path_of(occurrence_id):
    """The JSON path an occurrence id carries, as a list of child indices."""
    if ":s2:" not in occurrence_id:
        return None
    p = occurrence_id.split(":s2:", 1)[1]
    out = []
    for part in p.split("/"):
        if part == "":
            continue
        if not part.lstrip("-").isdigit():
            return None
        out.append(int(part))
    return out


def node_at(pkg, path):
    node = pkg
    for i in path:
        if not isinstance(node, list) or i >= len(node):
            return None
        node = node[i]
    return node


def _atoms_under(pkg, path, node=None):
    """(path, atom) for every predicate atom inside a subtree."""
    node = node_at(pkg, path) if node is None else node
    if not isinstance(node, list) or not node:
        return []
    head = node[0]
    if not isinstance(head, str) or head not in AO.LOGICAL_HEADS:
        return [(list(path), node)]
    out = []
    for i, ch in enumerate(node):
        if i == 0 or not isinstance(ch, list):
            continue
        out.extend(_atoms_under(pkg, path + [i], ch))
    return out


# Which argument positions of an atom hold PARTICIPANTS.  The degree families
# carry a degree and a comparison class after their participants, and treating
# those as participants makes every graded adjective in a problem look as
# though it shared an entity with every other one.
PARTICIPANT_ARGS = {"has degree rel2": (1, 2), "has degree property": (1,)}


def _terms(occ):
    args = occ.get("arguments_or_roles") or []
    pred = occ.get("predicate")
    if pred in PARTICIPANT_ARGS:
        return [args[i] for i in PARTICIPANT_ARGS[pred] if i < len(args)]
    slot = AO.LABEL_SLOT.get(pred)
    return [a for i, a in enumerate(args) if i != slot]


def _is_entity_const(t):
    """A grounded individual, not a class word.

    Stage 1 numbers the individuals it introduces (`Tom 1`, `onion 4`), and
    entity constants also arrive as `#:`-prefixed ids or as URLs.  Sharing the
    class word `person` is not sharing an entity.
    """
    if not isinstance(t, str) or AO._is_var(t):
        return False
    return bool(re.search(r" \d+$", t.strip()) or t.startswith("#:")
                or t.startswith("http"))


def _oid(unit_id, path):
    return "%s:s2:%s" % (unit_id, "".join("/%d" % i for i in path))


def _usable(occ):
    """Bookkeeping atoms are not conditions; a purely relational atom is.

    This is deliberately weaker than `alignment_issues._meaning_bearing`, which
    drops an atom carrying no problem word.  `has part(X, Y)` carries no word
    and is exactly the condition the onion-cell rule needs.
    """
    return (occ is not None and occ.get("stage") == "s2"
            and occ.get("kind") not in ("rule_variable", "modal")
            and occ.get("predicate") not in AI.STRUCTURAL_PREDS)


def companions(table, stage2, base_id, exclude=(), cap=DEFAULT_CAP):
    """-> [{occurrence_id, reason, reasons, atom, ...}] for one base occurrence.

    Ordered by reason, nearest first; capped.  Every entry is an existing
    occurrence, so the compiler can take it without any new parsing.
    """
    by_id = table["by_id"]
    base = by_id.get(base_id)
    if base is None or base.get("stage") != "s2":
        return []
    pkgs = dict(AO.packages(stage2))
    pkg = pkgs.get(base["unit_id"])
    path = path_of(base_id)
    if pkg is None or path is None:
        return []
    skip = set(exclude) | {base_id}
    found = {}          # occurrence_id -> {"reasons": [(rank, reason, detail)]}

    def offer(oid, reason, detail=None, distance=0):
        occ = by_id.get(oid)
        if oid in skip or not _usable(occ):
            return
        rec = found.setdefault(oid, {"reasons": []})
        rec["reasons"].append((REASON_RANK[reason], distance, reason, detail))

    # ---- 1. the nearest enclosing conjunction
    for i in range(len(path) - 1, -1, -1):
        anc = node_at(pkg, path[:i])
        if isinstance(anc, list) and anc and anc[0] == "and":
            child = path[i] if i < len(path) else None
            for j, ch in enumerate(anc):
                if j == 0 or j == child or not isinstance(ch, list):
                    continue
                for p, _ in _atoms_under(pkg, path[:i] + [j], ch):
                    offer(_oid(base["unit_id"], p), "nearest_conjunction",
                          "a sibling conjunct of the base atom")
            break

    # ---- 2. guards of enclosing quantified implications, innermost first
    depth = 0
    for i in range(len(path) - 1, -1, -1):
        anc = node_at(pkg, path[:i])
        if isinstance(anc, list) and len(anc) == 3 and anc[0] == "implies" \
                and path[i] == 2:
            depth += 1
            for p, _ in _atoms_under(pkg, path[:i] + [1], anc[1]):
                offer(_oid(base["unit_id"], p), "quantifier_guard",
                      "guard of the enclosing implication, distance %d" % depth,
                      distance=depth)

    # ---- 3/4. atoms sharing a variable (same package) or a grounded entity
    bt = _terms(base)
    bvars = set(t for t in bt if AO._is_var(t))
    bconst = set(AO.normalize_label(t) for t in bt if _is_entity_const(t))
    for occ in table["stage2"]:
        oid = occ["occurrence_id"]
        if oid in skip or not _usable(occ):
            continue
        ts = _terms(occ)
        common = bvars & set(t for t in ts if AO._is_var(t))
        if occ["unit_id"] == base["unit_id"] and common:
            offer(oid, "shared_variable", "uses %s" % ", ".join(sorted(common)))
        shared = bconst & set(AO.normalize_label(t) for t in ts
                              if _is_entity_const(t))
        if shared:
            offer(oid, "shared_entity", "about %s" % ", ".join(sorted(shared)))

    # ---- 5. anything else from the same sentence, capped
    same_unit = [o for o in table["stage2"]
                 if o["unit_id"] == base["unit_id"]
                 and o["occurrence_id"] not in skip
                 and o["occurrence_id"] not in found and _usable(o)]
    for occ in same_unit[:SAME_UNIT_CAP]:
        offer(occ["occurrence_id"], "same_unit", "another atom in this sentence")

    out = []
    for oid, rec in found.items():
        rec["reasons"].sort()
        occ = by_id[oid]
        out.append({
            "occurrence_id": oid,
            "reason": rec["reasons"][0][2],
            "distance": rec["reasons"][0][1],
            "why_offered": rec["reasons"][0][3],
            "reasons": sorted(set(r for _, _, r, _ in rec["reasons"]),
                              key=lambda r: REASON_RANK[r]),
            "all_reasons": [{"reason": r, "detail": d}
                            for _, _, r, d in rec["reasons"]],
            "unit_id": occ["unit_id"],
            "predicate": occ.get("predicate"),
            "label": occ.get("label"),
            "source_quote": occ.get("source_quote"),
            "atom": [occ["predicate"]] + list(occ.get("arguments_or_roles") or []),
            "shares_variable_with_base": bool(
                bvars & set(t for t in _terms(occ) if AO._is_var(t))
                and occ["unit_id"] == base["unit_id"]),
        })
    out.sort(key=lambda r: (REASON_RANK[r["reason"]], r["distance"],
                            r["occurrence_id"]))
    return out[:cap]


def menu(table, stage2, base_producer_id, base_consumer_id, cap=DEFAULT_CAP):
    """The companion menu for one selected candidate.

    Companions come from the producer's neighbourhood: an added condition
    restricts what the rule fires on, and that is the antecedent side.  The
    consumer is excluded so the rule cannot quietly assume its own conclusion.
    """
    return companions(table, stage2, base_producer_id,
                      exclude=(base_consumer_id,), cap=cap)
