"""Six axes, kept six axes, all the way to the schedule.

`admission_policy` and its v2 both end in one scalar — a confidence class — and
the world order is that scalar's rank.  The scalar is computed from four of the
six axes at once: semantic status, passage support, attachment status and, in
v2, direction.  So by the time anything schedules a world, "this is reliable
background knowledge whose derivation is clean" and "this is passage-anchored but
code invented an identification" have been mapped onto the same symbol, and
nothing downstream can tell them apart or ask why.

That also produced the wrong pressure: because SOURCE_FAITHFUL required passage
anchoring, an honest BACKGROUND_ONLY abstraction could never reach the top class
however clean its direction and derivation were — and the last round then asked
whether the top class was "clean enough" to run, when the real question is
whether each axis is honest.

So this module keeps the axes apart and never blends them:

    semantic      could the rule be true
    passage       does THIS passage license it, and how narrowly
    direction     does the implication run this way
    restriction   what the guard does — facts from `guard_facts`, plus the
                  judge's reading, kept separate from each other
    attachment    was an identification invented, and was it assessed
    provenance    every derivation path, unchanged

Eligibility is decided by GATES on individual axes, not by a blended score, and
the order is an explicit tuple whose components stay readable.  The old class
names are still computed and reported, marked descriptive, so earlier records
remain comparable — but nothing is scheduled by them.

Pure: no file, no call, no gold.
"""

import admission_policy as V1
import admission_policy_v2 as V2

VERSION = "admission_record/1.0"

EXECUTABLE = "executable"
EXPLORATORY = "exploratory"
ARCHIVED = "archived"
REJECTED = "rejected"

# Each axis ranks only itself.  No rank is combined with another to make a
# score; they are the components of an ordering tuple, in a stated priority.
SEMANTIC_RANK = {"SUPPORTED": 0, "PLAUSIBLE": 1, "SPECULATIVE": 2,
                 "UNSUPPORTED": 3, "INVALID": 4}
DIRECTION_RANK = {"AFFIRMED": 0, "CONTEXT_ONLY": 1, "UNKNOWN": 2,
                  "COUNTEREXAMPLED": 3, "INCOHERENT": 4}
ATTACHMENT_RANK = {"NONE_INVENTED": 0, "SUPPORTED_IDENTIFICATION": 1,
                   "POSSIBLE_IDENTIFICATION": 2,
                   "UNSUPPORTED_IDENTIFICATION": 3, "NOT_ASSESSED": 2}
PASSAGE_RANK = {"PASSAGE_GENERAL": 0, "PASSAGE_RESTRICTED": 1,
                "BACKGROUND_ONLY": 2, "UNCLEAR": 3, "NOT_SUPPORTED": 4}

ATTACHMENT_RESULTS = ("NONE_INVENTED", "SUPPORTED_IDENTIFICATION",
                      "POSSIBLE_IDENTIFICATION", "UNSUPPORTED_IDENTIFICATION",
                      "NOT_ASSESSED")


class RecordError(ValueError):
    pass


def gates(semantic, direction, attachment, scope):
    """What kind of world this is, from individual axes only.

    Each clause names one axis.  Nothing here reads a blended score, and
    passage support is deliberately absent: a rule the passage does not assert
    is not thereby less runnable, only less passage-faithful, and that is what
    the passage axis is for.
    """
    why = []
    if semantic in ("INVALID", "UNSUPPORTED"):
        return REJECTED, ["semantic=%s" % semantic]
    if direction == "INCOHERENT":
        return REJECTED, ["direction=INCOHERENT"]
    if direction == "COUNTEREXAMPLED":
        return ARCHIVED, ["direction=COUNTEREXAMPLED: kept as a record with "
                          "its counterexample, never executed"]
    if attachment == "UNSUPPORTED_IDENTIFICATION":
        return EXPLORATORY, ["attachment=UNSUPPORTED_IDENTIFICATION: the rule "
                             "stands only on an identification that was "
                             "judged unsupported"]
    if direction == "UNKNOWN":
        why.append("direction=UNKNOWN: untested, not refuted")
    if attachment in ("POSSIBLE_IDENTIFICATION", "NOT_ASSESSED"):
        why.append("attachment=%s: an invented identification is unsettled"
                   % attachment)
    if direction == "CONTEXT_ONLY" and scope == V2.GENERALISED:
        why.append("direction=CONTEXT_ONLY on the generalised twin")
    if semantic == "SPECULATIVE":
        why.append("semantic=SPECULATIVE")
    if why:
        return EXPLORATORY, why
    return EXECUTABLE, ["every axis is clean"]


def order_key(rec):
    """The explicit ordering tuple.  Every component stays readable.

    Priority of the components, and why:

      1 world kind      executable before exploratory; archived and rejected
                        are not ordered because they are not run
      2 direction       whether the implication runs this way at all is the
                        first thing that makes a world worth trying
      3 attachment      an invented identification is the next largest risk,
                        and it is independent of whether the claim is true
      4 semantic        how strongly the claim itself stands
      5 passage         LAST of the substantive axes, on purpose: an honest
                        background abstraction must not sort below a
                        passage-anchored rule whose derivation is shaky
      6 variant id      to make the order total
    """
    a = rec["axes"]
    return (0 if rec["world_kind"] == EXECUTABLE else 1,
            DIRECTION_RANK.get(a["direction"]["value"], 9),
            ATTACHMENT_RANK.get(a["attachment"]["result"], 9),
            SEMANTIC_RANK.get(a["semantic"]["value"], 9),
            PASSAGE_RANK.get(a["passage"]["value"], 9),
            str(rec["variant_id"]))


def record(variant_id, hypothesis_id, printed_formula, semantic, evidence,
           passage, direction, restriction, attachment_result,
           attachment_detail, guard_facts_rows, derivation_paths, scope,
           reason="", supporting_paths=(), uncertain_paths=(),
           attachment_reason=""):
    """One hypothesis, described on six axes that never merge."""
    for name, value, allowed in (
            ("semantic", semantic, V1.SEMANTIC_STATUS),
            ("evidence", evidence, V1.EVIDENCE_BASIS),
            ("passage", passage, V1.PASSAGE_SUPPORT),
            ("direction", direction, V2.DIRECTION_SUPPORT),
            ("restriction", restriction, V1.RESTRICTION_STATUS),
            ("attachment", attachment_result, ATTACHMENT_RESULTS)):
        if value not in allowed:
            raise RecordError("%s=%r is not one of %s" % (name, value, allowed))
    kind, why = gates(semantic, direction, attachment_result, scope)
    rec = {
        "variant_id": variant_id,
        "hypothesis_id": hypothesis_id,
        "printed_formula": printed_formula,
        "scope": scope,
        "axes": {
            "semantic": {"value": semantic, "evidence_basis": evidence,
                         "reason": reason},
            "passage": {"value": passage,
                        "fidelity": V1.passage_fidelity(
                            {"passage_support": passage,
                             "restriction_status": restriction})},
            "direction": {"value": direction},
            "restriction": {"judged": restriction,
                            "mechanical_facts": guard_facts_rows,
                            "note": "the judge's reading and the mechanical "
                                    "facts are kept apart; neither is derived "
                                    "from the other"},
            "attachment": {"result": attachment_result,
                           "reason": attachment_reason,
                           "detail": attachment_detail,
                           "assessed_directly": attachment_result !=
                           "NOT_ASSESSED"},
            "provenance": {"derivation_paths": derivation_paths,
                           "path_count": len(derivation_paths or []),
                           "supporting_paths": list(supporting_paths),
                           "uncertain_paths": list(uncertain_paths),
                           "any_path_model_named": any(
                               p.get("model_named_components")
                               for p in derivation_paths or []),
                           "any_path_unverified": any(
                               p.get("has_unverified_attachment")
                               for p in derivation_paths or [])},
        },
        "world_kind": kind,
        "gate_reasons": why,
        "executable": kind == EXECUTABLE,
        "record_version": VERSION,
    }
    # Descriptive only.  Reported so earlier records stay comparable; nothing
    # is scheduled by it, and an honest BACKGROUND_ONLY abstraction is not
    # demoted for failing to be passage-anchored.
    rec["descriptive_class"] = _descriptive_class(rec)
    rec["order_key"] = order_key(rec)
    return rec


def _descriptive_class(rec):
    a = rec["axes"]
    if rec["world_kind"] == REJECTED:
        return V1.REJECTED
    if a["passage"]["value"] in ("PASSAGE_GENERAL", "PASSAGE_RESTRICTED") \
            and a["semantic"]["value"] == "SUPPORTED":
        return V1.SOURCE_FAITHFUL
    if a["semantic"]["value"] in ("SUPPORTED", "PLAUSIBLE"):
        return V1.STABLE_EXTERNAL
    return V1.SPECULATIVE_LOW


def world_specifications(records):
    """Ordered worlds, one formula each, ordered by the explicit tuple."""
    runnable = [r for r in records
                if r["world_kind"] in (EXECUTABLE, EXPLORATORY)]
    runnable.sort(key=lambda r: r["order_key"])
    worlds = []
    for n, r in enumerate(runnable, start=1):
        a = r["axes"]
        worlds.append({
            "world": "W%d" % n, "order": n,
            "variant_id": r["variant_id"],
            "hypothesis_id": r["hypothesis_id"],
            "formula": r["printed_formula"],
            "formulas_in_this_world": 1,
            "world_kind": r["world_kind"],
            "order_key": r["order_key"],
            "order_key_fields": ["world_kind", "direction", "attachment",
                                 "semantic", "passage", "variant_id"],
            "axes": {"semantic": a["semantic"]["value"],
                     "evidence": a["semantic"]["evidence_basis"],
                     "passage": a["passage"]["value"],
                     "passage_fidelity": a["passage"]["fidelity"],
                     "direction": a["direction"]["value"],
                     "restriction_judged": a["restriction"]["judged"],
                     "attachment": a["attachment"]["result"],
                     "attachment_assessed_directly":
                         a["attachment"]["assessed_directly"]},
            "guard_facts": a["restriction"]["mechanical_facts"],
            "derivation_paths": a["provenance"]["derivation_paths"],
            "derivation_path_count": a["provenance"]["path_count"],
            "descriptive_class": r["descriptive_class"],
            "gate_reasons": r["gate_reasons"],
            "numeric_weight": None, "answer": None,
        })
    return {
        "worlds": worlds,
        "archived": [{"variant_id": r["variant_id"],
                      "formula": r["printed_formula"],
                      "direction": r["axes"]["direction"]["value"],
                      "why": r["gate_reasons"],
                      "reason": r["axes"]["semantic"]["reason"],
                      "derivation_path_count":
                          r["axes"]["provenance"]["path_count"]}
                     for r in records if r["world_kind"] == ARCHIVED],
        "rejected": [{"variant_id": r["variant_id"],
                      "why": r["gate_reasons"]}
                     for r in records if r["world_kind"] == REJECTED],
        "ordering": "explicit tuple: world kind, direction, attachment, "
                    "semantic, passage, variant id — no scalar score, no "
                    "numeric weight",
        "note": "one formula per world, charged once however many derivation "
                "paths it has; passage support ranks LAST so an honest "
                "background abstraction is not scheduled below a "
                "passage-anchored rule with a shakier derivation",
        "record_version": VERSION,
    }
