"""Compiling a v3 rule: binder-aware quantification, and one rule at a time.

Two differences from the frozen v2 compiler, both required by WP4:

  * a variable a set binder declares — `["$setof", V, ID, BODY]` — is LOCAL to
    that term and must not be universally quantified at the rule level.  The v2
    compiler collected every variable it saw, so a copied set expression would
    have become a formula about all objects rather than about that set;
  * a world is built rule by rule, and a rule that converts to no clause is
    refused BY NAME with its reason rather than raising.

Everything else — the `holds/forall/implies/normally` shape, the conversion
through `bridge_world` under the case's own options, the full-confidence
defeasible clause with its `$block`, the clause-to-hypothesis provenance — is
the frozen path, imported and not re-implemented.
"""

import json

import bridge_world as BW
import simple_rule_compiler as SC
import unifier_candidates_v3 as CV

VERSION = "simple_rule_compiler_v3/1.0"

WORLD = SC.WORLD
CompileError = SC.CompileError


def free_variables(rule):
    """The rule's free variables, in first-appearance order over body, head."""
    out = []
    for lit in rule["body"] + [rule["head"]]:
        for v in CV.free_variables(lit["atom"]):
            if v not in out:
                out.append(v)
    return out


def simple_rule_to_package(rule, world=WORLD):
    """-> `["holds", W, forall V1 ... . BODY -> normally(HEAD)]`.

    Only the FREE variables are quantified.  A set binder's own variable stays
    inside its term, where the converter binds it.
    """
    if not rule.get("body") or not rule.get("head"):
        raise CompileError("a rule needs a body and one conclusion")
    lits = [SC._literal(l) for l in rule["body"]]
    body = lits[0] if len(lits) == 1 else ["and"] + lits
    inner = ["implies", body, ["normally", SC._literal(rule["head"])]]
    for v in reversed(free_variables(rule)):
        inner = ["forall", v, inner]
    pkg = ["holds", world, inner]
    if BW.to_defeasible_shape(pkg) != pkg:
        raise CompileError("the built package is not in defeasible shape")
    return pkg


def hypothesis(rule, case_id, weight=1.0):
    return {"hypothesis_id": "%s::%s" % (case_id, rule["rule_id"]),
            "label": rule["rule_id"], "weight": weight, "case_id": case_id,
            "package": simple_rule_to_package(rule),
            "printed_formula": rule["printed"], "rule_id": rule["rule_id"],
            "canonical": rule["canonical"],
            "origin": rule.get("origin"),
            "warnings": rule.get("warnings") or []}


def compile_one(rule, view, configuration, case_id=None, world_name="probe",
                package_id="A1"):
    """-> (clauses, record) for one rule, compiled alone."""
    case_id = case_id or view.get("case_id") or "case"
    h = hypothesis(rule, case_id)
    return BW.compile_bridge(case_id, world_name, h["package"],
                             view["stage1"], view["stage2"], configuration,
                             bridge_evidence=BW.RUNTIME_EVIDENCE,
                             package_id=package_id,
                             base_clauses=view.get("final_clauses"),
                             hypothesis_id=h["hypothesis_id"])


def build_world(world_id, rules, view, configuration, weight=1.0,
                redundancy=None):
    """Every rule of a pool, compiled separately into one dynamic world.

    `redundancy(rule, clauses) -> reason or None` is consulted after a rule
    compiles: a rule whose clause the theory already contains is refused with
    that reason instead of being added.
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
                            "why": str(e)[:200], "kind": "compiler_refusal"})
            continue
        if redundancy is not None:
            already = redundancy(r, cl)
            if already:
                refused.append({"rule_id": r["rule_id"],
                                "printed": r["printed"], "why": already,
                                "kind": "already_present"})
                continue
        clauses.extend(cl)
        provenance.update(rec["clause_provenance"])
        entries.append({"hypothesis_id": h["hypothesis_id"],
                        "rule_id": r["rule_id"],
                        "weight": h["weight"], "label": h["label"],
                        "origin": h["origin"], "warnings": h["warnings"],
                        "package": h["package"],
                        "compiled_clauses": cl,
                        "clause_names": [c["@name"] for c in cl],
                        "rule_clause_names": rec["rule_clause_names"],
                        "has_block": rec["has_block"],
                        "bridge_evidence": rec["bridge_evidence"],
                        "printed_formula": h["printed_formula"]})
        hyps.append(h)
    return {
        "world_id": world_id,
        "bridge_hypotheses": entries,
        "compiled_bridge_clauses": clauses,
        "clause_provenance": provenance,
        "weights": dict((h["hypothesis_id"], h["weight"]) for h in hyps),
        "rule_by_hypothesis_id": dict((h["hypothesis_id"], h["rule_id"])
                                      for h in hyps),
        "printed_by_hypothesis_id": dict((h["hypothesis_id"],
                                          h["printed_formula"])
                                         for h in hyps),
        "hypotheses_in_this_world": [h["hypothesis_id"] for h in hyps],
        "refused_by_the_compiler": refused,
        "nothing_compiled": not hyps,
        "runtime_clause_policy": (
            "guarded, defeasible ($block), full confidence; no weight is "
            "applied to a clause or to a proof"),
    }


def clause_facts(clauses):
    return SC.clause_facts(clauses)


def literals(clauses):
    return SC.literals(clauses)
