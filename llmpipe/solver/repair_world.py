"""Dynamic worlds whose hypothesis is a translation repair, not a bridge.

A bridge adds a rule beside a theory that is assumed correct.  A repair says the
theory is not correct: one sentence was written down in a way that does not
carry what the English said, and the fix is to write it differently.  The two
are different operations and they get different worlds — never the same one.

A hypothesis is now:

    kind: "bridge" | "translation_repair"
    hypothesis_id
    source_unit_ids
    original_packages
    replacement_packages
    clause_provenance
    world_weight

The original theory is never modified.  A repair world is a separate conversion
of an edited copy of Stage 2, and the stored baseline stays exactly where it is.

Every clause produced by any replacement package of one repair carries that
repair's single hypothesis id, so `dynamic_score` charges the repair once
however many sentences it touched and however often the proof uses them.

The weight is the same 0.1 a bridge gets.  A repair is better motivated than an
invented rule — it claims to follow the source rather than to add knowledge —
but nothing has yet measured that, so it is not given more confidence.
"""

import collections
import copy
import json

import alignment_edit as AE
import bridge_world as BW
import option_scope

REPAIR_WEIGHT = 0.1
KINDS = ("bridge", "translation_repair")


class RepairError(Exception):
    """The repair world cannot be built.  Never worked around."""


def repair_hypothesis(hypothesis_id, replacement_packages, stage2, weight=None,
                      case_id=None, label=None, critic_reason=None):
    """One repair hypothesis, with the packages it replaces recorded."""
    if not hypothesis_id or not isinstance(hypothesis_id, str):
        raise RepairError("a hypothesis needs a non-empty string id")
    if not replacement_packages:
        raise RepairError("a repair with no replacement package is not a repair")
    weight = REPAIR_WEIGHT if weight is None else weight
    if not (0.0 < weight <= 1.0):
        raise RepairError("weight must be in (0, 1], got %r" % weight)
    before = dict(_packages(stage2))
    units, originals = [], {}
    for item in replacement_packages:
        if (not isinstance(item, list) or len(item) != 3 or item[0] != "@id"
                or not isinstance(item[1], str)):
            raise RepairError("not a complete [\"@id\", id, package]: %s"
                              % json.dumps(item)[:100])
        pid = item[1]
        units.append(pid)
        if pid in before:
            originals[pid] = copy.deepcopy(before[pid])
    return {
        "kind": "translation_repair",
        "hypothesis_id": hypothesis_id,
        "source_unit_ids": sorted(set(units)),
        "original_packages": originals,
        "replacement_packages": copy.deepcopy(replacement_packages),
        "weight": weight,
        "case_id": case_id,
        "label": label,
        "critic_reason": critic_reason,
    }


def _packages(stage2):
    import alignment_occurrences as AO
    return AO.packages(stage2)


def case_options(configuration):
    """A repair is converted the way the case itself was.

    Not the bridge options: a repair is part of the translation, so it must go
    through the same passes the rest of the theory went through or the edited
    sentence would be encoded on different terms from its neighbours.
    """
    import replay_case
    overrides = {}
    if configuration == "abstracted":
        overrides.update(replay_case._abstract_max_options(noprenorm=True))
    return option_scope.full_options(overrides)


def _convert(stage2, stage1, configuration):
    return BW._convert(stage2, stage1, case_options(configuration))


def _key(c):
    return json.dumps({k: v for k, v in c.items() if k != "@name"},
                      sort_keys=True)


def compile_repair(hyp, stage1, stage2, configuration, stored_baseline=None):
    """-> (theory, record).  The repaired theory, and what the repair did to it.

    Both the unedited and the edited Stage 2 are converted under the same
    options, so the difference between the two clause lists is the edit's and
    nothing else.  Whether the unedited conversion reproduces the stored
    baseline is reported, not assumed.
    """
    try:
        edited, changed, added, renamed = AE.splice(
            stage2, hyp["replacement_packages"])
    except AE.EditError as e:
        raise RepairError("splice refused the repair: %s" % e)
    before, _ = _convert(stage2, stage1, configuration)
    after, fixes = _convert(edited, stage1, configuration)

    touched = set(changed) | set(added)
    names = set("sent_%s" % u for u in touched)
    before_keys = collections.Counter(_key(c) for c in before
                                      if c.get("@name") in names)
    provenance, changed_clauses, unchanged_of_touched = {}, [], []
    for c in after:
        if c.get("@name") not in names:
            continue
        k = _key(c)
        if before_keys.get(k):
            before_keys[k] -= 1
            unchanged_of_touched.append(c["@name"])
        else:
            changed_clauses.append(c)

    # a repair must not move anything outside the sentences it names
    out_before = collections.Counter(_key(c) for c in before
                                     if c.get("@name") not in names)
    out_after = collections.Counter(_key(c) for c in after
                                    if c.get("@name") not in names)
    outside = {"only_before": sum((out_before - out_after).values()),
               "only_after": sum((out_after - out_before).values())}

    # provenance is built from the renamed clauses only, below
    named = []
    used = {}
    for c in after:
        c = copy.deepcopy(c)
        if c.get("@name") in names and _key(c) in set(_key(x) for x
                                                      in changed_clauses):
            n = used.get(c["@name"], 0)
            used[c["@name"]] = n + 1
            tag = "%s::%s::%d" % (c["@name"], hyp["hypothesis_id"], n + 1)
            c["@repair_of"] = c["@name"]
            c["@name"] = tag
            provenance[tag] = hyp["hypothesis_id"]
        named.append(c)

    record = {
        "kind": "translation_repair",
        "hypothesis_id": hyp["hypothesis_id"],
        "source_unit_ids": hyp["source_unit_ids"],
        "changed_packages": changed,
        "added_packages": added,
        "renamed": renamed,
        "clause_provenance": provenance,
        "changed_clause_count": len(provenance),
        "unchanged_clauses_of_touched_units": unchanged_of_touched,
        "clauses_outside_the_touched_units_that_moved": outside,
        "repair_is_local_to_its_units": outside["only_before"] == 0
        and outside["only_after"] == 0,
        "conversion_fixes": fixes,
        "weight": hyp["weight"],
        "baseline_reconversion_matches_stored": (
            None if stored_baseline is None else
            collections.Counter(_key(c) for c in before)
            == collections.Counter(_key(c) for c in stored_baseline)),
        "clause_counts": {"before": len(before), "after": len(after)},
    }
    return named, record


def build_repair_world(world_id, hyp, stage1, stage2, configuration,
                       stored_baseline=None):
    """The world, in the same shape `bridge_world.build_dynamic_world` returns."""
    theory, rec = compile_repair(hyp, stage1, stage2, configuration,
                                 stored_baseline)
    return {
        "world_id": world_id,
        "world_kind": "translation_repair",
        "bridge_hypotheses": [{
            "kind": "translation_repair",
            "hypothesis_id": hyp["hypothesis_id"],
            "weight": hyp["weight"],
            "label": hyp.get("label"),
            "source_unit_ids": hyp["source_unit_ids"],
            "original_packages": hyp["original_packages"],
            "replacement_packages": hyp["replacement_packages"],
            "clause_names": sorted(rec["clause_provenance"]),
        }],
        "bridge_world_weight": hyp["weight"],
        "theory": theory,
        "compiled_bridge_clauses": [c for c in theory
                                    if c.get("@name")
                                    in rec["clause_provenance"]],
        "clause_provenance": rec["clause_provenance"],
        "weights": {hyp["hypothesis_id"]: hyp["weight"]},
        "record": rec,
        "runtime_clause_policy": (
            "the repaired sentence is converted the way the case was; the "
            "world's weight is applied to the returned proof, not to a clause"),
        "note": "the original theory is untouched; this is a separate world",
    }
