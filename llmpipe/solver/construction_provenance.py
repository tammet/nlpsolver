"""What produced a formula: derivation classes, tiers, and path collection.

These four functions were written for the AL-73 provenance audit and lived in
`tools/replay_construction_v3.py` and `tools/audit_formula_provenance.py`.  The
runtime needs the same answers, and a runtime module must not import an analysis
program, so they live here.  `tools/test_dynamic_runtime.py` asserts this module
agrees with those two on the closed AL-71 construction runs, so the copy cannot
drift silently.

Nothing here reads a reviewed rule, an accepted answer or a scoring artifact,
and nothing calls a model or a prover.
"""

import json

import construction_forms as CF
import construction_operators as CO
import construction_slots as CS
import formula_hypothesis as FH
import operator_input as OI

VERSION = "construction_provenance/1.0"

MODEL_RUN = "model proposals"
ENUMERATED = "enumerated space"

CLASS_TIER = {"required_slot_completion": 1, "system_direction_variant": 2,
              "system_target_form_variant": 3, "system_guard_supplement": 4,
              "system_scope_variant": 5, "system_structural_supplement": 6}


def classes_of(rec, structural=False):
    """Which system-generated steps this alternative went through."""
    got = set()
    for c in rec.get("completions") or []:
        got.add("system_guard_supplement" if c["slot"] == "guards"
                else "required_slot_completion")
    if rec.get("direction") == "target_to_source":
        got.add("system_direction_variant")
    if rec.get("generalized"):
        got.add("system_scope_variant")
    if rec.get("target_form_origin") and \
            rec.get("target_form_origin") != CF.NAMED_GROUP and \
            (rec.get("target_form_variants_offered") or 1) > 1:
        got.add("system_target_form_variant")
    if structural:
        got.add("system_structural_supplement")
    return got


def tier_of(rec, structural=False):
    return max([CLASS_TIER[c] for c in classes_of(rec, structural)] or [0])


def sentences_of(case, oids):
    out, by = [], {}
    for oid, occ in case["by_oid"].items():
        by[oid] = occ
        by[occ["occurrence_id"]] = occ
    for oid in oids:
        occ = by.get(oid)
        if occ is not None:
            s = (occ.get("source_sentence") or "").strip()
            if s and s not in out:
                out.append(s)
    return out


def derivation_from(rec, source_run, source_alt, model_named, case):
    """One construction alternative -> one derivation path."""
    classes = classes_of(rec, structural=False)
    guards = [c["occurrence"] for c in (rec.get("completions") or [])
              if c["slot"] == "guards"]
    slots = [o for v in (rec.get("slots") or {}).values() for o in v]
    return FH.path(
        path_id="", source_run=source_run, source_alternative=source_alt,
        operator=rec["operator"],
        model_named_components=model_named,
        required_slot_completions=[c["occurrence"] for c in
                                   (rec.get("completions") or [])
                                   if c["slot"] != "guards"],
        system_guard_supplements=guards,
        system_direction_variant="system_direction_variant" in classes,
        system_target_form_variant="system_target_form_variant" in classes,
        system_scope_variant="system_scope_variant" in classes,
        system_structural_supplement=False,
        source_sentences=sentences_of(case, slots + guards),
        attachments=rec.get("attachments") or [],
        provenance_tier=FH.TIER_NAMES[tier_of(rec)],
        target=rec.get("target"), scope="generalised" if rec.get("generalized")
        else "as written", direction=rec.get("direction"))


def printed(rec):
    return "IF %s THEN normally %s" % (
        " AND ".join(OI._show(b) for b in rec["body"]), OI._show(rec["head"]))


def collect(case, case_id, proposals, enumerate_space=True,
            max_alternatives=400, packages=None):
    """Every alternative from both sources, accumulated per canonical formula.

    `proposals` are the model's own PROPOSE lines.  The enumerated space is
    walked too, not to invent hypotheses but so that a formula the model reached
    carries every derivation that also reaches it — the provenance AL-73 found
    had been discarded by deduplication.

    Pass a dict as `packages` to receive `printed formula -> Stage-2 package`
    alongside; the first alternative to produce a formula supplies its package,
    so nothing downstream has to rebuild it and no substitution can creep in.
    """
    acc = FH.Hypotheses()
    if packages is None:
        packages = {}
    for prop in proposals or []:
        named = sorted(set(o for v in (prop.get("roles") or {}).values()
                           for o in v) | set(prop.get("sources") or []))
        try:
            got = CF.build(case, prop, max_alternatives=10 ** 6,
                           slot_cap=10 ** 6)
        except CO.ConstructionError:
            continue
        for i, alt in enumerate(got["alternatives"]):
            rec = alt["record"]
            acc.add(rec["body"], rec["head"], printed(rec),
                    derivation_from(rec, MODEL_RUN, "alt%d" % (i + 1), named,
                                    case), case_id)
            packages.setdefault(printed(rec), alt["package"])
    if not enumerate_space:
        return acc, packages
    props = list(CS.enumerate_proposals(case)) + extra_proposals(case)
    sup, _c = CF.structural_supplements(case)
    structural = set()
    for s in sup:
        p = {k: s[k] for k in ("operator", "target", "roles", "sources")}
        structural.add(json.dumps(p, sort_keys=True))
        props.append(p)
    for prop in props:
        is_sup = json.dumps(prop, sort_keys=True) in structural
        for guards in (False, True):
            try:
                got = CF.build(case, prop, complete_guards=guards,
                               max_alternatives=max_alternatives,
                               slot_cap=max_alternatives,
                               guard_cap=max_alternatives)
            except CO.ConstructionError:
                continue
            for i, alt in enumerate(got["alternatives"]):
                rec = alt["record"]
                d = derivation_from(rec, ENUMERATED, "alt%d" % (i + 1), [],
                                    case)
                d["system_structural_supplement"] = is_sup
                if is_sup:
                    d["provenance_tier"] = "after_structural_supplement"
                acc.add(rec["body"], rec["head"], printed(rec), d, case_id)
                packages.setdefault(printed(rec), alt["package"])
    return acc, packages


# The operators `construction_slots.enumerate_proposals` knows how to propose,
# snapshotted when this module is imported — before any later operator can
# register.  Nothing below is a hand-written list: it is what the frozen
# enumeration function covered at import time, and everything outside it must
# bring its own enumerator.
BASE_EMITTERS = frozenset(CS.EMITTERS)

ENUMERATORS = {}


class EnumerationGap(RuntimeError):
    """An operator the frozen enumeration cannot reach and that brought no
    enumerator of its own — the defect that kept a whole family out of every
    pool while appearing to be available."""


def register_enumerator(name, fn):
    """An operator declares how its own proposals are enumerated."""
    ENUMERATORS[name] = fn
    return True


def unregister_enumerator(name):
    return ENUMERATORS.pop(name, None) is not None


def operators_without_an_enumerator():
    """Registered operators the frozen enumeration cannot reach."""
    return sorted(n for n in CS.EMITTERS
                  if n not in BASE_EMITTERS and n not in ENUMERATORS)


def assert_enumerators():
    """Every operator is reachable without a model naming it.  Or it raises."""
    missing = operators_without_an_enumerator()
    if missing:
        raise EnumerationGap(
            "these operators are registered but nothing enumerates them: %s"
            % ", ".join(missing))
    return True


def extra_proposals(case):
    """Proposals from operators the frozen enumeration does not name.

    `construction_slots.enumerate_proposals` writes out its operators one by
    one, so an operator added later was reachable only when a model named it —
    which is how a whole family stayed out of every pool while appearing to be
    available.  Each such operator now registers its own enumerator, and
    `assert_enumerators` refuses a runtime where one has not.
    """
    out = []
    for name in sorted(ENUMERATORS):
        try:
            out.extend(ENUMERATORS[name](case) or [])
        except Exception:                                    # noqa: BLE001
            continue
    return out


def model_reached(row):
    """True when at least one derivation path is a model proposal."""
    return any(p["source_run"] == MODEL_RUN
               for p in row.get("derivation_paths") or [])
