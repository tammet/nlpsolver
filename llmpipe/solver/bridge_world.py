"""Dynamic CONNECT bridges: defeasible shape, isolated conversion, evidence.

A bridge is not an abstraction of the problem.  It is a small, invented,
defeasible rule added beside an already converted theory, and it needs two
properties the base theory's own conversion does not give it:

  1. a `$block` literal, so a later fact can defeat it;
  2. a low, configurable evidence weight, so a proof that leans on it says so.

Both are lost if the bridge is converted the way the base theory was.
`tools/bridge_conversion_matrix.py` measures where they survive:

  * `normally` must sit inside a quantifier.  The unquantified
    `normally(implies(A,B))` produces no rule clause at all.  All three
    quantified placements produce a `$block`; this module uses
    `forall vars . BODY -> normally(HEAD)`, the shape the converter's own
    rewrite normalises toward.
  * the strict finaliser (`logconvert`'s `_ultra`, gated by the `typeenrich`
    `plural` sub-gate and therefore on under every `-abstract*` preset) unwraps
    `normally` and drops `$block`.  That is correct for its documented purpose —
    classical, strict abstraction — and is not changed here.  The bridge is
    converted with it off instead.

So the bridge is compiled **separately**, under its own options, and only its
own clauses are kept and appended to the stored base theory.  The base theory is
never reconverted; abstract-max keeps its global meaning.

`bridge_evidence` is a weight on the evidence for the rule, written straight
onto the clause as `@confidence`.  It is deliberately not routed through a
Stage-2 `@p`: that path treats a value below 0.5 as evidence for the NEGATED
conclusion, so an `@p` of 0.1 would assert the opposite of the bridge.  The name
says weight of evidence, not probability of truth.
"""

import copy
import json

import option_scope

# `bridge_evidence` is a DIAGNOSTIC compiler option, not the runtime mechanism
# for abstraction confidence.  Writing a low confidence onto the clause prunes
# proof search and compounds on repeated application (see
# `memos/MEMO_2026_08_10_bridge_world.md` §5), so at runtime a bridge clause is
# full-confidence and the uncertainty is applied to the returned proof instead
# (`solver/dynamic_score.py`).
DEFAULT_EVIDENCE = 0.1
FULL_EVIDENCE = 1.0
RUNTIME_EVIDENCE = None      # no @confidence written; scoring happens on proofs

# The isolated conversion configuration.  Everything the base preset does for
# vocabulary and shape is kept; only what destroys defeasibility or deletes a
# selected condition is turned off.
BRIDGE_OPTION_OVERRIDES = {
    "typeenrich_flag": False,   # off: its `plural` sub-gate gates the strict
                                # finaliser, which unwraps `normally` and drops
                                # `$block`
    "guarddrop_flag": False,    # off: it deleted isa(animal, ?V2) from both
                                # animal-lover bridges in the 08-10 gk pilot
    "noexceptions_flag": False,  # explicit: blockers are the point
}

PROVENANCE = "dynamic_bridge_%s_%s_%d"
HYPOTHESIS_PROVENANCE = "dynamic_bridge_%s_%d"


class BridgeError(Exception):
    """The bridge cannot be built.  Never worked around."""


# ---------------------------------------------------------------- shape

def _split_prefix(pkg):
    """-> (world, [bound vars], inner formula) for a compiled rule package."""
    if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "holds"):
        raise BridgeError("not a holds package: %s" % json.dumps(pkg)[:80])
    world, f = pkg[1], pkg[2]
    bound = []
    while isinstance(f, list) and f and f[0] == "forall" and len(f) >= 3:
        bound.append(f[1])
        f = f[2]
    return world, bound, f


def _rebuild(world, bound, inner):
    out = inner
    for v in reversed(bound):
        out = ["forall", v, out]
    return ["holds", world, out]


def to_defeasible_shape(pkg):
    """`forall vars . normally(A -> B)`  ->  `forall vars . A -> normally(B)`.

    Idempotent, and it refuses anything that is not a quantified implication
    rather than guessing.
    """
    world, bound, f = _split_prefix(pkg)
    if isinstance(f, list) and f and f[0] == "normally" and len(f) == 2:
        f = f[1]
    if not (isinstance(f, list) and len(f) == 3 and f[0] == "implies"):
        raise BridgeError("not a quantified implication: %s"
                          % json.dumps(pkg)[:80])
    head = f[2]
    if not (isinstance(head, list) and head and head[0] == "normally"):
        head = ["normally", head]
    return _rebuild(world, bound, ["implies", f[1], head])


def to_strict_shape(pkg):
    """The same rule with no `normally` anywhere.  Diagnosis only."""
    world, bound, f = _split_prefix(pkg)
    if isinstance(f, list) and f and f[0] == "normally" and len(f) == 2:
        f = f[1]
    if not (isinstance(f, list) and len(f) == 3 and f[0] == "implies"):
        raise BridgeError("not a quantified implication: %s"
                          % json.dumps(pkg)[:80])
    head = f[2]
    while isinstance(head, list) and head and head[0] == "normally" \
            and len(head) == 2:
        head = head[1]
    return _rebuild(world, bound, ["implies", f[1], head])




# ---------------------------------------------------------------- conversion

def default_options():
    """`globals.options` as the module defines it, captured before any run."""
    return option_scope.full_options()


def bridge_options(base_configuration):
    """The option set the bridge is converted under.

    It starts from the base theory's own configuration, so predicate
    canonicalization, entity merging and the event encoding stay compatible with
    the clauses the bridge has to unify with, and then turns off exactly the two
    passes that would destroy it.
    """
    import replay_case
    overrides = {}
    if base_configuration == "abstracted":
        overrides.update(replay_case._abstract_max_options(noprenorm=True))
    overrides.update(BRIDGE_OPTION_OVERRIDES)
    return option_scope.full_options(overrides)


def _convert(stage2, stage1, opts):
    """One conversion inside a complete, isolated option scope."""
    import globals as g
    import llmparse
    import logconvert
    import semnormalize
    with option_scope.scoped(opts):
        s1, s2 = copy.deepcopy(stage1), copy.deepcopy(stage2)
        stats = llmparse._make_stats()
        llmparse._fill_missing_asu_time(s1, stats)
        s2 = llmparse._repair_entity_ids(s1, s2, stats)
        fixes = []
        logic = logconvert.rawlogic_convert(s2, s1, fixes)
        if logic is None:
            raise BridgeError("rawlogic_convert returned None")
        if not g.options.get("nosemnormal_flag"):
            logic = semnormalize.sem_normalize_clauses(logic)
    return logic, fixes


def _base_uses_ctxt_terms(base_clauses):
    return "$ctxt" in json.dumps(base_clauses or [])


def _share_ctxt(clauses, counter):
    """Collapse each clause's `$ctxt` terms to one shared fresh `?:Cu` variable.

    This is step 1 of the strict finaliser, and only that step.  The finaliser
    itself cannot be used because it also unwraps `normally` and drops
    `$block`, which is the whole point of a bridge; but its context handling is
    what the base theory went through, so a bridge appended to such a theory has
    to match it or the context slots will not line up.
    """
    out = []
    for c in clauses:
        c = copy.deepcopy(c)
        counter[0] += 1
        var = "?:Cub%d" % counter[0]

        def walk(node):
            if isinstance(node, list):
                if node and node[0] == "$ctxt":
                    return var
                return [walk(x) for x in node]
            return node
        for k in ("@logic", "@question"):
            if k in c:
                c[k] = walk(c[k])
        out.append(c)
    return out


def compile_bridge(case_id, world_name, pkg, stage1, stage2, configuration,
                   bridge_evidence=RUNTIME_EVIDENCE, package_id="A1",
                   base_clauses=None, hypothesis_id=None):
    """-> (clauses, record).  The clauses the bridge alone contributes.

    The case is converted only to obtain them in the case's own vocabulary and
    context conventions; everything else the conversion produces is discarded
    and the caller appends these to the STORED base theory.  Nothing about the
    base theory is recomputed.

    `bridge_evidence` is written as `@confidence` on the rule clauses.  The
    population clauses a conversion emits alongside a rule are kept unannotated
    and reported separately: they are not the rule and weighting them would be
    weighting an artefact.
    """
    if bridge_evidence is not None and not (0.0 < bridge_evidence <= 1.0):
        raise BridgeError("bridge_evidence must be None or in (0, 1], got %r"
                          % bridge_evidence)
    edited = _splice(stage2, package_id, pkg)
    clauses, fixes = _convert(edited, stage1, bridge_options(configuration))
    mine = [c for c in clauses
            if str(c.get("@name", "")).startswith("sent_%s" % package_id)]
    if not mine:
        raise BridgeError("conversion produced no clause for the bridge")
    # context compatibility: match whatever the base theory did
    collapsed = base_clauses is not None and not _base_uses_ctxt_terms(
        base_clauses)
    if collapsed:
        mine = _share_ctxt(mine, [0])
    out, rule_idx, pop_idx, provenance = [], [], [], {}
    for i, c in enumerate(mine, start=1):
        c = copy.deepcopy(c)
        c["@name"] = (HYPOTHESIS_PROVENANCE % (hypothesis_id, i)
                      if hypothesis_id else
                      PROVENANCE % (case_id, world_name, i))
        if hypothesis_id:
            provenance[c["@name"]] = hypothesis_id
        if c.get("@sourcetype") == "populate":
            pop_idx.append(c["@name"])
        else:
            if bridge_evidence is not None:
                c["@confidence"] = bridge_evidence
            rule_idx.append(c["@name"])
        out.append(c)
    blob = json.dumps(out)
    rec = {
        "case_id": case_id, "world": world_name,
        "bridge_evidence": bridge_evidence,
        "hypothesis_id": hypothesis_id,
        "clause_provenance": provenance,
        "evidence_written_as": ("@confidence on the rule clauses"
                                if bridge_evidence is not None else
                                "nothing: a runtime bridge clause is "
                                "full-confidence and the world weight is "
                                "applied to the returned proof instead"),
        "options": {k: bridge_options(configuration)[k]
                    for k in sorted(BRIDGE_OPTION_OVERRIDES)},
        "base_configuration": configuration,
        "rule_clause_names": rule_idx,
        "population_clause_names": pop_idx,
        "has_block": "$block" in blob,
        "clause_count": len(out),
        "context_terms_collapsed_to_variables": collapsed,
        "context_policy": ("the base theory holds no $ctxt term, so the "
                           "bridge's were collapsed to one shared variable per "
                           "clause, as the base's were"
                           if collapsed else
                           "the base theory holds $ctxt terms, so the bridge's "
                           "were left as they are" if base_clauses is not None
                           else "no base theory given; context left as "
                                "converted"),
        "converter_notes": fixes,
    }
    return out, rec


def _splice(stage2, pid, pkg):
    if not (isinstance(stage2, list) and stage2 and stage2[0] == "and"):
        raise BridgeError("stage2 is not an [\"and\", ...] list")
    out = copy.deepcopy(stage2)
    for item in out[1:]:
        if isinstance(item, list) and len(item) >= 2 and item[0] == "@id" \
                and item[1] == pid:
            raise BridgeError("%s already exists in this Stage 2" % pid)
    out.append(["@id", pid, copy.deepcopy(pkg)])
    return out


# ---------------------------------------------------------------- inspection

def has_block(clauses):
    return "$block" in json.dumps(clauses)


def _literals(clauses):
    for c in clauses:
        body = c.get("@logic")
        if not isinstance(body, list) or not body:
            continue
        lits = body if isinstance(body[0], list) else [body]
        for lit in lits:
            if isinstance(lit, list) and lit and isinstance(lit[0], str):
                yield lit




def cited_clause(raw_text, names):
    """The clause text gk shows for the first proof step citing one of `names`.

    A recovery is only creditable if the clause that actually fired is the one
    that was built, so the caller can check the guard in the CITED clause rather
    than in the clause it hoped was used.
    """
    try:
        d = json.loads(raw_text)
    except ValueError:
        return None
    for ans in d.get("answers") or []:
        for key in ("positive proof", "negative proof", "proof"):
            for step in ans.get(key) or []:
                if not isinstance(step, list) or len(step) < 3:
                    continue
                if any(n in json.dumps(step[1]) for n in names):
                    return {"step": step[0], "citation": step[1],
                            "clause": step[2]}
    return None


# ------------------------------------------------- dynamic world (WP1)

def hypothesis(hypothesis_id, package, weight, case_id=None, label=None,
               record=None):
    """One bridge hypothesis: a rule, a stable id, and a world weight.

    The id is what every clause the rule compiles to is labelled with, and what
    proof scoring charges.  Two clauses from one hypothesis are one hypothesis.
    """
    if not hypothesis_id or not isinstance(hypothesis_id, str):
        raise BridgeError("a hypothesis needs a non-empty string id")
    if not (0.0 < weight <= 1.0):
        raise BridgeError("weight must be in (0, 1], got %r" % weight)
    return {"hypothesis_id": hypothesis_id, "package": package,
            "weight": weight, "case_id": case_id, "label": label,
            "record": record or {}}


def world_weight(hypotheses):
    """Provisional: the product of the distinct hypotheses' weights.

    PROVISIONAL AND DOCUMENTED AS SUCH.  For a one-bridge world it is that
    bridge's weight, which is the only case the evidence so far covers.  For
    several bridges a product treats them as independent, which is a modelling
    choice nobody has yet argued for; it is implemented so the data model is
    complete, and it is not a policy decision.
    """
    w = 1.0
    for h in {h["hypothesis_id"]: h for h in hypotheses}.values():
        w *= h["weight"]
    return w


def build_dynamic_world(world_id, hypotheses, stage1, stage2, configuration,
                        base_clauses=None, bridge_evidence=RUNTIME_EVIDENCE):
    """-> the dynamic world: hypotheses, their clauses, provenance and weight.

    Runtime clauses are guarded, defeasible and FULL CONFIDENCE.  The world's
    uncertainty is not written into the clauses — it is applied to whatever
    proof comes back, by `dynamic_score`.  `bridge_evidence` is still accepted
    so the diagnostic behaviour stays reachable, and it is recorded.
    """
    if not hypotheses:
        raise BridgeError("a dynamic world needs at least one hypothesis")
    seen = set()
    clauses, provenance, entries = [], {}, []
    for h in hypotheses:
        hid = h["hypothesis_id"]
        if hid in seen:
            raise BridgeError("hypothesis id %s used twice" % hid)
        seen.add(hid)
        cl, rec = compile_bridge(h.get("case_id") or world_id, world_id,
                                 h["package"], stage1, stage2, configuration,
                                 bridge_evidence=bridge_evidence,
                                 package_id="A%d" % (len(entries) + 1),
                                 base_clauses=base_clauses,
                                 hypothesis_id=hid)
        clauses.extend(cl)
        provenance.update(rec["clause_provenance"])
        entries.append({"hypothesis_id": hid, "weight": h["weight"],
                        "label": h.get("label"),
                        "package": h["package"],
                        "clause_names": [c["@name"] for c in cl],
                        "rule_clause_names": rec["rule_clause_names"],
                        "has_block": rec["has_block"],
                        "guards": rec.get("guards"),
                        "bridge_evidence": rec["bridge_evidence"]})
    return {
        "world_id": world_id,
        "bridge_hypotheses": entries,
        "bridge_world_weight": world_weight(hypotheses),
        "compiled_bridge_clauses": clauses,
        "clause_provenance": provenance,
        "weights": {h["hypothesis_id"]: h["weight"] for h in hypotheses},
        "runtime_clause_policy": (
            "guarded, defeasible ($block), full confidence; the world weight is "
            "applied to the returned proof, not to the clause"),
        "weight_policy": "provisional: product over distinct cited hypotheses",
    }
