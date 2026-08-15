"""Compiling a v4 rule: the same boundary, and no exception can kill a pool.

The v3 world builder caught `BridgeError` and let everything else through.  A
rule whose atom carries a nested argument in a position the converter reads as a
string reaches `lc_questions.collect_generic_rule_classes` and raises
`TypeError: unhashable type: 'list'` — which ended `folio-0001` in the first v4
run and would have ended any case where the model copies a displayed nested
term into the wrong slot.

`logconvert` is off limits for this iteration, and it is not the place for the
fix in any case: a rule the converter refuses, however it refuses, is a rule
this pipeline must NAME and step over.  So the guard here is total, and it
records the exception type.

Everything else is `simple_rule_compiler_v3`, imported: the package shape, the
binder-aware quantification, the conversion under the case's own options, the
full-confidence defeasible clause with its `$block`, and the clause-to-
hypothesis provenance.
"""

import bridge_world as BW
import simple_rule_compiler_v3 as C3

VERSION = "simple_rule_compiler_v4/1.0"

WORLD = C3.WORLD
CompileError = C3.CompileError

free_variables = C3.free_variables
simple_rule_to_package = C3.simple_rule_to_package
hypothesis = C3.hypothesis
compile_one = C3.compile_one
clause_facts = C3.clause_facts
literals = C3.literals


def build_world(world_id, rules, view, configuration, weight=1.0,
                redundancy=None):
    """Every rule of a pool, compiled separately into one dynamic world."""
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
        except Exception as e:                                  # noqa: BLE001
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": "the converter raised %s: %s"
                                   % (type(e).__name__, str(e)[:160]),
                            "kind": "converter_error"})
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
