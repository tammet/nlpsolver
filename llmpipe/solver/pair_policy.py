"""What a paired-direction judgement may do to two six-axis records.

One rule, and one rule only: the paired judgement may PRESERVE or REDUCE what
the individual assessments decided.  It can archive a direction, or move it from
executable to exploratory; it can never make a rejected rule runnable, and it
can never make an exploratory rule executable.  A judge that could promote would
turn "the model liked the pair" into permission, which is precisely what the
six-axis record was built to prevent.

    EQUIVALENT          both keep whatever their individual assessment allowed
    A_ONLY              A keeps it; B is ARCHIVED with the counterexample
    B_ONLY              B keeps it; A is ARCHIVED
    CONTEXT_ONLY_BOTH   grounded forms keep it; generalised forms drop to
                        exploratory
    NEITHER             both archived
    UNCERTAIN           both drop to exploratory — kept, never deleted

A counterexampled direction is never executable, whatever its individual axes
said.  Nothing here is deleted: an archived record keeps its formula, its axes
and every derivation path, and says who archived it and why.

Pure: no file, no call, no gold.
"""

import copy

import admission_record as AR

VERSION = "pair_policy/1.0"

RELATIONS = ("EQUIVALENT", "A_ONLY", "B_ONLY", "CONTEXT_ONLY_BOTH",
             "NEITHER", "UNCERTAIN")

KIND_RANK = {AR.EXECUTABLE: 0, AR.EXPLORATORY: 1, AR.ARCHIVED: 2,
             AR.REJECTED: 3}


def _reduce(record, to_kind, why, judgement):
    """Move a record DOWN the runnability order, never up."""
    out = copy.deepcopy(record)
    if KIND_RANK[to_kind] <= KIND_RANK[record["world_kind"]]:
        out.setdefault("pair_judgement", {}).update(
            {"relation": judgement.get("relation"),
             "effect": "none: the individual assessment is already at or below "
                       "what the pair implies",
             "individual_world_kind": record["world_kind"]})
        return out
    out["world_kind"] = to_kind
    out["executable"] = to_kind == AR.EXECUTABLE
    out["gate_reasons"] = list(record["gate_reasons"]) + [why]
    out["order_key"] = AR.order_key(out)
    out["pair_judgement"] = {
        "relation": judgement.get("relation"),
        "effect": "reduced from %s to %s" % (record["world_kind"], to_kind),
        "why": why,
        "individual_world_kind": record["world_kind"],
        "counterexample": judgement.get("counterexample_for_this_side"),
        "scope": judgement.get("scope"),
    }
    return out


def _keep(record, judgement, why):
    out = copy.deepcopy(record)
    out["pair_judgement"] = {
        "relation": judgement.get("relation"),
        "effect": "unchanged", "why": why,
        "individual_world_kind": record["world_kind"],
        "scope": judgement.get("scope"),
    }
    return out


def is_grounded(record, pair, side):
    terms = pair.get("grounded_terms_a" if side == "a"
                     else "grounded_terms_b") or []
    return bool(terms)


def apply_pair(rec_a, rec_b, pair, judgement):
    """-> (record for A, record for B) after the paired judgement.

    `judgement` carries `relation`, `counterexample_a`, `counterexample_b` and
    `scope`.  A counterexample on a side archives that side even when the
    relation would have let it run.
    """
    rel = judgement.get("relation")
    if rel not in RELATIONS:
        raise ValueError("unknown relation %r" % rel)
    ca = (judgement.get("counterexample_a") or "").strip().lower()
    cb = (judgement.get("counterexample_b") or "").strip().lower()
    has_ca = ca not in ("", "none", "-", "n/a")
    has_cb = cb not in ("", "none", "-", "n/a")
    ja = dict(judgement, counterexample_for_this_side=judgement.get(
        "counterexample_a"))
    jb = dict(judgement, counterexample_for_this_side=judgement.get(
        "counterexample_b"))

    if rel == "EQUIVALENT":
        a = _keep(rec_a, ja, "the pair was judged equivalent; the individual "
                             "assessment still decides")
        b = _keep(rec_b, jb, "the pair was judged equivalent; the individual "
                             "assessment still decides")
    elif rel == "A_ONLY":
        a = _keep(rec_a, ja, "the pair judgement kept this direction")
        b = _reduce(rec_b, AR.ARCHIVED, "pair=A_ONLY: this direction is the "
                    "one the judge did not keep", jb)
    elif rel == "B_ONLY":
        a = _reduce(rec_a, AR.ARCHIVED, "pair=B_ONLY: this direction is the "
                    "one the judge did not keep", ja)
        b = _keep(rec_b, jb, "the pair judgement kept this direction")
    elif rel == "CONTEXT_ONLY_BOTH":
        a = (_keep(rec_a, ja, "grounded: the judgement covers the things this "
                              "passage names")
             if is_grounded(rec_a, pair, "a") else
             _reduce(rec_a, AR.EXPLORATORY,
                     "pair=CONTEXT_ONLY_BOTH and this form is generalised", ja))
        b = (_keep(rec_b, jb, "grounded: the judgement covers the things this "
                              "passage names")
             if is_grounded(rec_b, pair, "b") else
             _reduce(rec_b, AR.EXPLORATORY,
                     "pair=CONTEXT_ONLY_BOTH and this form is generalised", jb))
    elif rel == "NEITHER":
        a = _reduce(rec_a, AR.ARCHIVED, "pair=NEITHER", ja)
        b = _reduce(rec_b, AR.ARCHIVED, "pair=NEITHER", jb)
    else:                                                    # UNCERTAIN
        a = _reduce(rec_a, AR.EXPLORATORY,
                    "pair=UNCERTAIN: kept, and only as an isolated exploratory "
                    "world", ja)
        b = _reduce(rec_b, AR.EXPLORATORY,
                    "pair=UNCERTAIN: kept, and only as an isolated exploratory "
                    "world", jb)

    # a counterexampled direction is never executable, whatever the relation
    if has_ca and a["world_kind"] == AR.EXECUTABLE:
        a = _reduce(a, AR.ARCHIVED, "a counterexample was given for this "
                    "direction", ja)
    if has_cb and b["world_kind"] == AR.EXECUTABLE:
        b = _reduce(b, AR.ARCHIVED, "a counterexample was given for this "
                    "direction", jb)
    return a, b


def apply_all(records, pairs, judgements):
    """Apply every pair judgement to a case's records.

    `judgements` maps (a_id, b_id) -> judgement.  A record in several pairs
    takes the STRICTEST outcome, because a direction refuted in any pairing is
    refuted.
    """
    by_id = dict((r["variant_id"], copy.deepcopy(r)) for r in records)
    applied = []
    for pair in pairs:
        j = judgements.get((pair["a_id"], pair["b_id"]))
        if j is None:
            continue
        ra, rb = by_id.get(pair["a_id"]), by_id.get(pair["b_id"])
        if ra is None or rb is None:
            continue
        na, nb = apply_pair(ra, rb, pair, j)
        for nid, new in ((pair["a_id"], na), (pair["b_id"], nb)):
            cur = by_id[nid]
            if KIND_RANK[new["world_kind"]] >= KIND_RANK[cur["world_kind"]]:
                by_id[nid] = new
        applied.append({"pair": (pair["a_id"], pair["b_id"]),
                        "relation": j.get("relation"),
                        "a_before": ra["world_kind"],
                        "a_after": by_id[pair["a_id"]]["world_kind"],
                        "b_before": rb["world_kind"],
                        "b_after": by_id[pair["b_id"]]["world_kind"]})
    out = [by_id[r["variant_id"]] for r in records]
    for r in out:
        if KIND_RANK[r["world_kind"]] < KIND_RANK[
                next(x["world_kind"] for x in records
                     if x["variant_id"] == r["variant_id"])]:
            raise AssertionError("a pair judgement promoted %s"
                                 % r["variant_id"])
    return out, applied
