"""An accepted `RULE:` line becomes a real, defeasible GK bridge (WP5).

The whole compilation is deterministic and goes through the tested bridge
boundary rather than around it:

    RULE line
      -> Stage-2 variables (the parser)
      -> ["holds","W0", forall V1 .. . BODY -> normally(HEAD)]
      -> bridge_world.compile_bridge / build_dynamic_world

`bridge_world` converts the package under the CASE'S OWN options with the two
passes that would destroy a bridge turned off, keeps its guards, aligns the
generated context arguments with the stored theory, and labels every clause with
the hypothesis it came from.  Hand-writing final clauses would lose all four.

Occurrence-id compilation — the route the earlier construction library takes —
is deliberately not used: the model may join two literal templates no candidate
pair ever represented, and there is no occurrence pair to name for such a rule.

A compiled bridge clause is FULL CONFIDENCE and carries a `$block`.  Low trust
is a property of the returned proof and is worked out after gk, never written
into a clause.
"""

import json

import bridge_world as BW

VERSION = "simple_rule_compiler/1.0"

WORLD = "W0"


class CompileError(Exception):
    """The rule cannot be compiled.  Never worked around."""


# ------------------------------------------------------------------ package

def _literal(lit):
    atom = list(lit["atom"])
    return ["not", atom] if lit["sign"] == "-" else atom


def _variables(rule):
    """Bound variables in first-appearance order over the body then the head."""
    import alignment_occurrences as AO
    out = []

    def go(t):
        if isinstance(t, str):
            if AO._is_var(t) and t not in out:
                out.append(t)
        elif isinstance(t, list):
            for x in t[1:]:
                go(x)
    for lit in rule["body"] + [rule["head"]]:
        for a in lit["atom"][1:]:
            go(a)
    return out


def simple_rule_to_package(rule, world=WORLD):
    """-> `["holds", W, forall V1 ... . BODY -> normally(HEAD)]`.

    The shape is the one `bridge_world` documents as the only placement of
    `normally` that survives conversion with its `$block` intact.
    """
    if not rule.get("body") or not rule.get("head"):
        raise CompileError("a rule needs a body and one conclusion")
    lits = [_literal(l) for l in rule["body"]]
    body = lits[0] if len(lits) == 1 else ["and"] + lits
    inner = ["implies", body, ["normally", _literal(rule["head"])]]
    for v in reversed(_variables(rule)):
        inner = ["forall", v, inner]
    pkg = ["holds", world, inner]
    # idempotence: the shape must already be the one the bridge compiler wants
    if BW.to_defeasible_shape(pkg) != pkg:
        raise CompileError("the built package is not in defeasible shape")
    return pkg


def hypothesis(rule, case_id, weight):
    """One dynamic hypothesis, ready for `bridge_world.build_dynamic_world`."""
    return {"hypothesis_id": "%s::%s" % (case_id, rule["rule_id"]),
            "label": rule["rule_id"],
            "weight": weight,
            "case_id": case_id,
            "package": simple_rule_to_package(rule),
            "printed_formula": rule["printed"],
            "rule_id": rule["rule_id"],
            "canonical": rule["canonical"]}


# ------------------------------------------------------------------ compile

def compile_one(rule, view, configuration, case_id=None, weight=1.0,
                world_name="probe"):
    """Compile a single rule alone, for a fixture or a check.  -> (clauses, rec)."""
    case_id = case_id or view.get("case_id") or "case"
    pkg = simple_rule_to_package(rule)
    return BW.compile_bridge(case_id, world_name, pkg, view["stage1"],
                             view["stage2"], configuration,
                             bridge_evidence=BW.RUNTIME_EVIDENCE,
                             package_id="A1",
                             base_clauses=view.get("final_clauses"),
                             hypothesis_id="%s::%s" % (case_id,
                                                       rule["rule_id"]))


def build_world(world_id, rules, view, configuration, weight=1.0):
    """Every accepted rule of a pool, compiled into one dynamic world.

    The world's clauses are appended to the STORED base theory; nothing about
    the base theory is recomputed.

    Rules are compiled ONE AT A TIME.  Some grammatical rules convert to no
    clause at all — a rule about `has time`, the Davidsonian tense slot, is the
    case this was written for — and compiling the pool in one call made one such
    rule destroy every other rule in the same case.  A rule that yields no clause
    is refused with its reason and listed in `refused_by_the_compiler`; the rest
    of the pool still reaches gk.
    """
    if not rules:
        raise CompileError("a world needs at least one rule")
    hyps, clauses, provenance, entries, refused = [], [], {}, [], []
    for r in rules:
        h = hypothesis(r, view["case_id"], weight)
        try:
            cl, rec = BW.compile_bridge(
                view["case_id"], world_id, h["package"], view["stage1"],
                view["stage2"], configuration,
                bridge_evidence=BW.RUNTIME_EVIDENCE,
                package_id="A%d" % (len(entries) + 1),
                base_clauses=view.get("final_clauses"),
                hypothesis_id=h["hypothesis_id"])
        except BW.BridgeError as e:
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": str(e)[:200]})
            continue
        clauses.extend(cl)
        provenance.update(rec["clause_provenance"])
        entries.append({"hypothesis_id": h["hypothesis_id"],
                        "weight": h["weight"], "label": h["label"],
                        "package": h["package"],
                        "clause_names": [c["@name"] for c in cl],
                        "rule_clause_names": rec["rule_clause_names"],
                        "has_block": rec["has_block"],
                        "bridge_evidence": rec["bridge_evidence"]})
        hyps.append(h)
    return {
        "world_id": world_id,
        "bridge_hypotheses": entries,
        "bridge_world_weight": BW.world_weight(hyps) if hyps else None,
        "compiled_bridge_clauses": clauses,
        "clause_provenance": provenance,
        "weights": dict((h["hypothesis_id"], h["weight"]) for h in hyps),
        "rule_by_hypothesis_id": dict((h["hypothesis_id"], h["rule_id"])
                                      for h in hyps),
        "printed_by_hypothesis_id": dict((h["hypothesis_id"],
                                          h["printed_formula"]) for h in hyps),
        "hypotheses_in_this_world": [h["hypothesis_id"] for h in hyps],
        "refused_by_the_compiler": refused,
        "nothing_compiled": not hyps,
        "runtime_clause_policy": (
            "guarded, defeasible ($block), full confidence; no weight is "
            "applied to a clause or to a proof"),
    }


# ------------------------------------------------------------------ checks

def clause_facts(clauses):
    """What a caller must be able to assert about a compiled bridge."""
    blob = json.dumps(clauses)
    rule_clauses = [c for c in clauses if c.get("@sourcetype") != "populate"]
    return {
        "clause_count": len(clauses),
        "rule_clause_count": len(rule_clauses),
        "has_block": "$block" in blob,
        "confidence_annotations": [c.get("@confidence") for c in clauses],
        "any_confidence_annotation": any(c.get("@confidence") is not None
                                         for c in clauses),
        "names": [c.get("@name") for c in clauses],
    }


def literals(clauses):
    """Every literal of a compiled clause list, flattened."""
    out = []
    for c in clauses:
        body = c.get("@logic")
        if not isinstance(body, list) or not body:
            continue
        lits = body if isinstance(body[0], list) else [body]
        for lit in lits:
            if isinstance(lit, list) and lit and isinstance(lit[0], str):
                out.append(lit)
    return out


def signed_predicates(clauses):
    """-> {(sign, predicate)} over the compiled clauses, `$block` excluded."""
    out = set()
    for lit in literals(clauses):
        pred = lit[0]
        bare = pred[1:] if pred.startswith("-") else pred
        if bare.startswith("$"):
            continue
        out.add(("-" if pred.startswith("-") else "+", bare))
    return out
