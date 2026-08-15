"""Admission policy v2: the direction question, asked instead of inferred.

AL-72 retained folio-0169's reversed rule `part of -> member of` as a
SPECULATIVE_LOW world.  The judge had described it correctly — "parts of wholes
need not be members" — but the only retainable words available for "not reliably
true" put it in a world that would run.  The failure was the vocabulary, not the
judgment: a converse that fails and an over-abstraction nobody has tested were
the same class.

So direction becomes its own field with five values, and the policy treats them
differently:

    AFFIRMED         positive support for the direction in general
    CONTEXT_ONLY     supported for these entities, not in general
    UNKNOWN          no positive support and no concrete counterexample
    COUNTEREXAMPLED  the judge can say why the direction fails in general
    INCOHERENT       swapped participants or a definite corruption

UNKNOWN still buys an exploratory world — an untested over-abstraction is worth
trying — while COUNTEREXAMPLED buys none: it is archived with its reason and
never executed.  That is the distinction AL-72 could not draw, and it is the
whole of this change.  CONTEXT_ONLY keeps the ground form and refuses to promote
its generalised twin on the same evidence.

Everything else is v1's, imported rather than restated.  Pure: no file, no call,
no gold.
"""

import re

import admission_policy as V1

VERSION = "admission_policy/2.0"

SEMANTIC_STATUS = V1.SEMANTIC_STATUS
EVIDENCE_BASIS = V1.EVIDENCE_BASIS
PASSAGE_SUPPORT = V1.PASSAGE_SUPPORT
RESTRICTION_STATUS = V1.RESTRICTION_STATUS
ATTACHMENT_STATUS = V1.ATTACHMENT_STATUS
SOURCE_FAITHFUL = V1.SOURCE_FAITHFUL
STABLE_EXTERNAL = V1.STABLE_EXTERNAL
SPECULATIVE_LOW = V1.SPECULATIVE_LOW
REJECTED = V1.REJECTED
PRIORITY = V1.PRIORITY

DIRECTION_SUPPORT = ("AFFIRMED", "CONTEXT_ONLY", "UNKNOWN", "COUNTEREXAMPLED",
                     "INCOHERENT")

EXECUTABLE = "executable"
EXPLORATORY = "exploratory"
ARCHIVE_ONLY = "archive_only"
NO_WORLD = "none"

GENERALISED = "generalised"


class PolicyError(V1.PolicyError):
    pass


def assess(variant_id, semantic_status, evidence_basis, passage_support,
           restriction_status, attachment_status, direction_support,
           scope="as written", supporting_paths=(), uncertain_paths=(),
           reason=""):
    """v1's judgment plus the direction question, and what world it buys."""
    if direction_support not in DIRECTION_SUPPORT:
        raise PolicyError("direction_support=%r is not one of %s"
                          % (direction_support, DIRECTION_SUPPORT))
    a = V1.assess(variant_id, semantic_status, evidence_basis, passage_support,
                  restriction_status, attachment_status, reason)
    trace = list(a["policy_trace"])
    cls = a["confidence_class"]
    world = EXECUTABLE if cls != REJECTED else NO_WORLD

    if direction_support == "INCOHERENT":
        cls, world = REJECTED, NO_WORLD
        trace.append("direction_support=INCOHERENT rejects")
    elif cls == REJECTED:
        trace.append("already rejected on the semantic axis")
    elif direction_support == "COUNTEREXAMPLED":
        world = ARCHIVE_ONLY
        trace.append("direction_support=COUNTEREXAMPLED: kept as a diagnostic "
                     "record, no executable world")
    elif direction_support == "UNKNOWN":
        if cls != SPECULATIVE_LOW:
            trace.append("direction_support=UNKNOWN: %s -> %s"
                         % (cls, SPECULATIVE_LOW))
            cls = SPECULATIVE_LOW
        world = EXPLORATORY
        trace.append("an untested direction is explored, not trusted")
    elif direction_support == "CONTEXT_ONLY":
        if scope == GENERALISED:
            if cls != SPECULATIVE_LOW:
                trace.append("direction_support=CONTEXT_ONLY on a generalised "
                             "formula: %s -> %s" % (cls, SPECULATIVE_LOW))
                cls = SPECULATIVE_LOW
            world = EXPLORATORY
            trace.append("context-only support never promotes the generalised "
                         "twin")
        else:
            trace.append("direction_support=CONTEXT_ONLY on the ground form: "
                         "retained as it stands")
    else:
        trace.append("direction_support=AFFIRMED: the ordinary axes decide")

    out = dict(a)
    out.update({
        "direction_support": direction_support,
        "scope": scope,
        "confidence_class": cls,
        "priority_class": PRIORITY[cls],
        "keep_as_hypothesis": cls != REJECTED,
        "world_status": world,
        "executable": world == EXECUTABLE,
        "supporting_paths": list(supporting_paths),
        "uncertain_paths": list(uncertain_paths),
        "policy_trace": trace,
        "policy_version": VERSION,
    })
    return out


passage_fidelity = V1.passage_fidelity
more_passage_faithful = V1.more_passage_faithful


# ------------------------------------------------------------------ worlds

def world_specifications(rows):
    """Retained hypotheses -> ordered worlds, with archives kept apart.

    One FORMULA per world, charged once however many derivation paths it has,
    and every path travels with it.  A counterexampled direction produces an
    archive entry instead of a world; an unknown one produces an exploratory
    world; nothing rejected produces anything.
    """
    keep = [r for r in rows if r["assessment"]["keep_as_hypothesis"]
            and r["assessment"]["world_status"] in (EXECUTABLE, EXPLORATORY)]
    archive = [r for r in rows if r["assessment"]["keep_as_hypothesis"]
               and r["assessment"]["world_status"] == ARCHIVE_ONLY]
    dropped = [r for r in rows if not r["assessment"]["keep_as_hypothesis"]]
    keep.sort(key=lambda r: (r["assessment"]["priority_class"],
                             0 if r["assessment"]["world_status"] == EXECUTABLE
                             else 1, str(r["assessment"]["variant_id"])))
    worlds = []
    for n, r in enumerate(keep, start=1):
        a = r["assessment"]
        worlds.append({
            "world": "W%d" % n, "order": n,
            "variant_id": a["variant_id"],
            "hypothesis_id": r.get("hypothesis_id"),
            "formula": r.get("rule"),
            "formulas_in_this_world": 1,
            "confidence_class": a["confidence_class"],
            "priority_class": a["priority_class"],
            "world_status": a["world_status"],
            "direction_support": a["direction_support"],
            "scope": a["scope"],
            "passage_fidelity": passage_fidelity(a),
            "derivation_paths": r.get("derivation_paths"),
            "derivation_path_count": len(r.get("derivation_paths") or []),
            "supporting_paths": a["supporting_paths"],
            "uncertain_paths": a["uncertain_paths"],
            "admission": {k: a[k] for k in
                          ("semantic_status", "evidence_basis",
                           "passage_support", "restriction_status",
                           "attachment_status", "direction_support",
                           "reason", "policy_trace")},
            "numeric_weight": None, "answer": None,
        })
    return {
        "worlds": worlds,
        "archived": [{"variant_id": r["assessment"]["variant_id"],
                      "formula": r.get("rule"),
                      "direction_support":
                          r["assessment"]["direction_support"],
                      "why": "counterexampled direction: kept as a diagnostic, "
                             "never executed",
                      "reason": r["assessment"]["reason"],
                      "derivation_path_count":
                          len(r.get("derivation_paths") or [])}
                     for r in archive],
        "rejected": [{"variant_id": r["assessment"]["variant_id"],
                      "why": r["assessment"]["policy_trace"][-1]}
                     for r in dropped],
        "ordering": ["SOURCE_FAITHFUL", "STABLE_EXTERNAL", "SPECULATIVE_LOW",
                     "executable before exploratory within a class"],
        "note": "one formula per world, charged once however many derivation "
                "paths it has; no weight, no answer, no gk",
        "policy_version": VERSION,
    }


# ------------------------------------------------------------------ parsing

_FIELD = re.compile(r"([A-Za-z_]+)\s*=\s*([^;]*)")
FIELDS = {"semantic": ("semantic_status", SEMANTIC_STATUS),
          "evidence": ("evidence_basis", EVIDENCE_BASIS),
          "passage": ("passage_support", PASSAGE_SUPPORT),
          "restriction": ("restriction_status", RESTRICTION_STATUS),
          "direction": ("direction_support", DIRECTION_SUPPORT)}
_NONEISH = ("none", "-", "n/a", "na", "nothing", "", "[]", "()")


def _paths(field, known):
    """Path ids, validated.  An unknown id is rejected, never repaired."""
    raw = (field or "").strip()
    if raw.strip().strip(".").lower() in _NONEISH:
        return [], []
    ids = re.findall(r"\bP\d+\b", raw.upper())
    good = [i for i in ids if i in known]
    bad = [i for i in ids if i not in known]
    return good, bad


def parse_assessments(text, ids, paths_by_variant, attachment_by_variant=None,
                      scope_by_variant=None):
    """Read only `ASSESS:` lines.  Strict; nothing inferred from prose.

    `attachment` is not asked of the model here — the challenge states which
    paths carry an unverified attachment, and the model says which paths it
    relies on.  The attachment status is DERIVED from that: relying only on
    paths that invented an identification is what makes an attachment uncertain,
    and deriving it removes a field the model was previously asked to restate.
    """
    got, bad = {}, []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() != "ASSESS":
            continue
        body = v.strip()
        vid = body.split(";", 1)[0].strip().strip(".")
        if vid not in ids:
            bad.append({"line": line[:200],
                        "why": "unknown candidate %r" % vid[:20]})
            continue
        fields = dict((m.group(1).lower(), m.group(2).strip())
                      for m in _FIELD.finditer(body))
        row, why = {}, None
        for key, (name, allowed) in FIELDS.items():
            if key not in fields:
                why = "no %s" % key
                break
            value = fields[key].strip().strip(".").upper().replace(" ", "_")
            if value not in allowed:
                why = "%s=%r is not one of the allowed values" % (key,
                                                                  value[:40])
                break
            row[name] = value
        if why:
            bad.append({"line": line[:200], "why": why})
            continue
        known = set(paths_by_variant.get(vid, []))
        sup, bad_sup = _paths(fields.get("supporting_paths"), known)
        unc, bad_unc = _paths(fields.get("uncertain_paths"), known)
        if bad_sup or bad_unc:
            bad.append({"line": line[:200],
                        "why": "unknown path id(s) %s"
                               % ", ".join(bad_sup + bad_unc)})
            continue
        unverified = set((attachment_by_variant or {}).get(vid, []))
        relied = set(sup)
        if not relied:
            attachment = "NO_INVENTED_ATTACHMENT" if not unverified \
                else "ATTACHMENT_UNCERTAIN"
        elif relied & unverified and relied - unverified:
            attachment = "ATTACHMENT_UNCERTAIN"
        elif relied and relied <= unverified:
            attachment = "ATTACHMENT_UNSUPPORTED"
        else:
            attachment = "NO_INVENTED_ATTACHMENT"
        try:
            got[vid] = assess(
                vid, row["semantic_status"], row["evidence_basis"],
                row["passage_support"], row["restriction_status"],
                attachment, row["direction_support"],
                scope=(scope_by_variant or {}).get(vid, "as written"),
                supporting_paths=sup, uncertain_paths=unc,
                reason=fields.get("reason", "")[:400])
            got[vid]["unsupported_paths"] = sorted(known - set(sup) - set(unc))
            got[vid]["attachment_derived_from_paths"] = True
        except V1.PolicyError as e:
            bad.append({"line": line[:200], "why": str(e)[:120]})
    missing = [i for i in ids if i not in got]
    return {"readable": bool(got), "assessments": got, "rejected": bad,
            "missing": missing, "complete": not missing}
