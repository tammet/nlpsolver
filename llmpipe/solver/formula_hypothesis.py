"""One formula, every way it was derived.

AL-71 built its challenge set by walking the construction space, keying
alternatives on their printed text and keeping the first record that produced
each key.  Two things went wrong and neither was visible in the artifact.

The kept record was whichever path the enumerator reached first, so eb2-0009's
dead-guarded rule was shown as a `typed_taxonomy` from S1's own atoms with no
invented attachment — while the path the MODEL actually produced, an
`argument_label_promotion` whose guard was attached across sentences by an
unverified identification, was dropped.  The judge assessed a formula whose
riskiest derivation it never saw.

And the kept record's `roles` were labelled "named in the proposal" whether they
came from a model reply or from the enumerator, so every candidate claimed
model-named components that no model had named.

So a formula is no longer a record.  It is a canonical formula plus every
derivation path that produced it, each path saying where it came from and what
was named by whom.  Paths accumulate; none overwrites another; a favourable path
never erases one carrying an unverified attachment, and an unfavourable one never
invalidates the rest.

Canonicalisation renames bound variables and nothing else.  Sign, predicate,
label, constants, argument order and premise order are all significant: two
formulas that differ in any of them are two formulas.

This module is pure — no file, no call, no gold.
"""

import json
import re

VERSION = "formula_hypothesis/1.0"

_VAR = re.compile(r"^V\d+$")

TIER_NAMES = ["model_named_only", "after_required_slot_completion",
              "after_direction_alternatives", "after_target_form_variant",
              "after_guard_supplementation", "after_scope_or_generalisation",
              "after_structural_supplement"]


def _is_var(t):
    return isinstance(t, str) and bool(_VAR.match(t))


def canonical(body, head):
    """Rename bound variables by first appearance; change nothing else.

    Premise ORDER is preserved on purpose: reordering is a different formula
    for this purpose, and merging on a sorted body would quietly join rules the
    operators built differently.
    """
    mapping, n = {}, [0]

    def walk(node):
        if isinstance(node, list):
            return [walk(x) for x in node]
        if _is_var(node):
            if node not in mapping:
                n[0] += 1
                mapping[node] = "?%d" % n[0]
            return mapping[node]
        return node
    return json.dumps({"body": [walk(b) for b in body], "head": walk(head)},
                      sort_keys=False)


def path(path_id, source_run, source_alternative, operator,
         model_named_components, required_slot_completions,
         system_guard_supplements, system_direction_variant,
         system_target_form_variant, system_scope_variant,
         system_structural_supplement, source_sentences, attachments,
         provenance_tier, target=None, scope=None, direction=None):
    """One derivation path.  `model_named_components` means exactly that."""
    return {
        "path_id": path_id,
        "source_run": source_run,
        "source_alternative": source_alternative,
        "operator": operator,
        "target": target,
        "direction": direction,
        "scope": scope,
        "model_named_components": list(model_named_components),
        "required_slot_completions": list(required_slot_completions),
        "system_guard_supplements": list(system_guard_supplements),
        "system_direction_variant": bool(system_direction_variant),
        "system_target_form_variant": bool(system_target_form_variant),
        "system_scope_variant": bool(system_scope_variant),
        "system_structural_supplement": bool(system_structural_supplement),
        "source_sentences": list(source_sentences),
        "attachments": list(attachments),
        "has_unverified_attachment": any(
            a.get("status") == "unverified_attachment" for a in attachments),
        "provenance_tier": provenance_tier,
    }


def _path_key(p):
    """What makes two derivation paths the same path.

    Deliberately not the path id and not the source run: the same construction
    reached twice is one path, and reaching it from two different runs is still
    one way of building the formula.  Everything that describes HOW it was built
    is in the key.
    """
    return json.dumps({k: p[k] for k in
                       ("operator", "target", "direction", "scope",
                        "model_named_components", "required_slot_completions",
                        "system_guard_supplements", "system_direction_variant",
                        "system_target_form_variant", "system_scope_variant",
                        "system_structural_supplement", "attachments")},
                      sort_keys=True)


class Hypotheses(object):
    """A formula-keyed accumulator.  Adding never overwrites."""

    def __init__(self):
        self.by_formula = {}
        self.order = []

    def add(self, body, head, printed, derivation, case_id=None):
        key = canonical(body, head)
        row = self.by_formula.get(key)
        if row is None:
            row = {"hypothesis_id": "H%d" % (len(self.order) + 1),
                   "case_id": case_id,
                   "canonical_formula": key,
                   "printed_formula": printed,
                   "body": list(body), "head": head,
                   "derivation_paths": [], "_seen": set()}
            self.by_formula[key] = row
            self.order.append(key)
        k = _path_key(derivation)
        if k in row["_seen"]:
            for existing in row["derivation_paths"]:
                if _path_key(existing) == k:
                    if derivation["source_run"] not in \
                            existing.setdefault("also_reached_by", []):
                        if derivation["source_run"] != existing["source_run"]:
                            existing["also_reached_by"].append(
                                derivation["source_run"])
                    break
            return row, False
        row["_seen"].add(k)
        d = dict(derivation)
        d["path_id"] = "P%d" % (len(row["derivation_paths"]) + 1)
        row["derivation_paths"].append(d)
        return row, True

    def rows(self):
        out = []
        for key in self.order:
            r = dict(self.by_formula[key])
            r.pop("_seen", None)
            out.append(r)
        return out


def summarise(row):
    """What a reader needs about a formula's provenance, across all paths."""
    paths = row["derivation_paths"]
    return {
        "paths": len(paths),
        "any_model_named": any(p["model_named_components"] for p in paths),
        "all_paths_model_named": all(p["model_named_components"]
                                     for p in paths) if paths else False,
        "any_unverified_attachment": any(p["has_unverified_attachment"]
                                         for p in paths),
        "all_paths_unverified": all(p["has_unverified_attachment"]
                                    for p in paths) if paths else False,
        "operators": sorted(set(p["operator"] for p in paths)),
        "best_tier": min([TIER_NAMES.index(p["provenance_tier"])
                          for p in paths] or [0]),
        "source_runs": sorted(set(p["source_run"] for p in paths)),
    }
