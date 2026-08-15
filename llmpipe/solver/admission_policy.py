"""Two-axis semantic admission: is it true, and does the passage say it?

AL-71's probe asked one question — is this rule acceptable — and the answer
collapsed two different judgments into one. On eb2-0009 the judge admitted the
unguarded `organism -> organic matter` because organisms really are made of
organic matter, and it doubted the dead-guarded version because the guard is not
needed for that claim to be true. Both readings are right about their own
question. What was lost is that only the guarded rule says what the passage says.

So a candidate now carries two axes that never merge:

    semantic_status    could this be true at all
    passage_support    does THIS passage license it, and how narrowly

plus what the restriction and any invented attachment do to it. Nothing is
selected: a broader rule that is reliable background knowledge and a narrower
rule that is passage-faithful are both retained, in different confidence
classes, and the ordering says which world runs first — not which rule wins.

This module is pure. It reads no file, makes no call, and knows nothing about
proofs, answers or reviewed rules; it turns one recorded judgment into a
retention decision, and the reason each decision was reached is listed.
"""

VERSION = "admission_policy/1.0"

SEMANTIC_STATUS = ("SUPPORTED", "PLAUSIBLE", "SPECULATIVE", "UNSUPPORTED",
                   "INVALID")
EVIDENCE_BASIS = ("TEXTUAL_REPRESENTATION", "LEXICAL_TAXONOMY",
                  "CONVENTIONAL_NOMINALIZATION_OR_ROLE",
                  "STABLE_BACKGROUND_RELATION", "SPECULATIVE_CORRELATION",
                  "OPEN_WORLD_NEGATIVE", "NONE")
PASSAGE_SUPPORT = ("PASSAGE_GENERAL", "PASSAGE_RESTRICTED", "BACKGROUND_ONLY",
                   "NOT_SUPPORTED", "UNCLEAR")
RESTRICTION_STATUS = ("NO_RESTRICTION_NEEDED", "RELEVANT_RESTRICTION_PRESENT",
                      "RELEVANT_RESTRICTION_MISSING", "IRRELEVANT_RESTRICTION",
                      "UNCLEAR")
ATTACHMENT_STATUS = ("NO_INVENTED_ATTACHMENT", "ATTACHMENT_SUPPORTED",
                     "ATTACHMENT_UNCERTAIN", "ATTACHMENT_UNSUPPORTED")

SOURCE_FAITHFUL = "SOURCE_FAITHFUL"
STABLE_EXTERNAL = "STABLE_EXTERNAL"
SPECULATIVE_LOW = "SPECULATIVE_LOW"
REJECTED = "REJECTED"
CONFIDENCE_CLASSES = (SOURCE_FAITHFUL, STABLE_EXTERNAL, SPECULATIVE_LOW,
                      REJECTED)
LADDER = [SOURCE_FAITHFUL, STABLE_EXTERNAL, SPECULATIVE_LOW]
PRIORITY = {SOURCE_FAITHFUL: 1, STABLE_EXTERNAL: 2, SPECULATIVE_LOW: 3,
            REJECTED: None}

# A rejection is only ever a statement about the rule itself.  Neither a missing
# guard nor an invented attachment can cause one: both lower confidence, because
# the broad rule may still be reliable knowledge and the attachment may still be
# right.  Only the semantic axis rejects.
REJECTING_STATUS = ("INVALID", "UNSUPPORTED")

BASE_CLASS = {"SUPPORTED": SOURCE_FAITHFUL, "PLAUSIBLE": STABLE_EXTERNAL,
              "SPECULATIVE": SPECULATIVE_LOW}
# A rule can be true by ordinary meaning and still not be what this passage
# said; that is a demotion, never a rejection.  The confidence class is itself a
# combination of the two axes — SOURCE_FAITHFUL means "fine AND anchored in the
# passage", STABLE_EXTERNAL means "fine but from outside it" — so the passage
# axis belongs here.
UNANCHORED_PASSAGE = ("BACKGROUND_ONLY", "NOT_SUPPORTED", "UNCLEAR")

# The restriction deliberately does NOT move the confidence class.  A missing
# guard makes a rule less faithful to the passage, not less likely to be true,
# and letting it demote confidence as well would count the passage axis twice —
# which is the collapse this whole round exists to undo.  It is reported on the
# fidelity axis instead, where it belongs.


class PolicyError(ValueError):
    """A value outside the declared vocabulary.  Never coerced."""


def _check(name, value, allowed):
    if value not in allowed:
        raise PolicyError("%s=%r is not one of %s" % (name, value, allowed))
    return value


def _demote(cls, why, trace):
    if cls == REJECTED:
        return cls
    i = LADDER.index(cls)
    if i + 1 < len(LADDER):
        trace.append("%s: %s -> %s" % (why, cls, LADDER[i + 1]))
        return LADDER[i + 1]
    trace.append("%s: already at %s" % (why, cls))
    return cls


def assess(variant_id, semantic_status, evidence_basis, passage_support,
           restriction_status, attachment_status, reason=""):
    """One recorded judgment -> one retention decision, with its reasons."""
    _check("semantic_status", semantic_status, SEMANTIC_STATUS)
    _check("evidence_basis", evidence_basis, EVIDENCE_BASIS)
    _check("passage_support", passage_support, PASSAGE_SUPPORT)
    _check("restriction_status", restriction_status, RESTRICTION_STATUS)
    _check("attachment_status", attachment_status, ATTACHMENT_STATUS)

    trace = []
    if semantic_status in REJECTING_STATUS:
        cls = REJECTED
        trace.append("semantic_status=%s rejects" % semantic_status)
    else:
        cls = BASE_CLASS[semantic_status]
        trace.append("semantic_status=%s -> %s" % (semantic_status, cls))
        if cls == SOURCE_FAITHFUL and passage_support in UNANCHORED_PASSAGE:
            cls = _demote(cls, "passage_support=%s" % passage_support, trace)
        trace.append("restriction_status=%s affects passage fidelity only"
                     % restriction_status)
        if attachment_status == "ATTACHMENT_UNCERTAIN":
            cls = _demote(cls, "attachment_status=ATTACHMENT_UNCERTAIN", trace)
        elif attachment_status == "ATTACHMENT_UNSUPPORTED":
            if cls != SPECULATIVE_LOW:
                trace.append("attachment_status=ATTACHMENT_UNSUPPORTED: %s -> %s"
                             % (cls, SPECULATIVE_LOW))
            cls = SPECULATIVE_LOW
    return {
        "variant_id": variant_id,
        "semantic_status": semantic_status,
        "evidence_basis": evidence_basis,
        "passage_support": passage_support,
        "restriction_status": restriction_status,
        "attachment_status": attachment_status,
        "keep_as_hypothesis": cls != REJECTED,
        "confidence_class": cls,
        "priority_class": PRIORITY[cls],
        "reason": reason,
        "policy_trace": trace,
        "policy_version": VERSION,
    }


def passage_fidelity(a):
    """How narrowly this passage licenses the rule, independent of truth.

    Kept apart from confidence on purpose: a rule can be more passage-faithful
    and less confident (an uncertain attachment), or less passage-faithful and
    more confident (reliable background knowledge).
    """
    if a["passage_support"] in ("PASSAGE_GENERAL", "PASSAGE_RESTRICTED"):
        base = "passage_licensed"
    elif a["passage_support"] == "BACKGROUND_ONLY":
        base = "background_only"
    else:
        base = "not_licensed"
    if base == "passage_licensed" and \
            a["restriction_status"] == "RELEVANT_RESTRICTION_PRESENT":
        return "passage_licensed_and_restricted"
    if base == "passage_licensed" and \
            a["restriction_status"] == "RELEVANT_RESTRICTION_MISSING":
        return "passage_licensed_but_unrestricted"
    return base


def more_passage_faithful(a, b):
    """Is `a` more passage-faithful than `b`?  A total order on fidelity only."""
    rank = {"passage_licensed_and_restricted": 0, "passage_licensed": 1,
            "passage_licensed_but_unrestricted": 2, "background_only": 3,
            "not_licensed": 4}
    return rank[passage_fidelity(a)] < rank[passage_fidelity(b)]


# ------------------------------------------------------------------ worlds

def world_specifications(rows):
    """Retained hypotheses -> ordered world specifications.  Pure.

    One hypothesis per world.  Nothing is merged, nothing is suppressed for
    being less preferred, and no weight or answer is invented: the order says
    which world would be tried first, and that is all it says.
    """
    keep = [r for r in rows if r["assessment"]["keep_as_hypothesis"]]
    dropped = [{"variant_id": r["assessment"]["variant_id"],
                "confidence_class": r["assessment"]["confidence_class"],
                "why": r["assessment"]["policy_trace"][0]}
               for r in rows if not r["assessment"]["keep_as_hypothesis"]]
    keep.sort(key=lambda r: (r["assessment"]["priority_class"],
                             str(r["assessment"]["variant_id"])))
    worlds = []
    for n, r in enumerate(keep, start=1):
        a = r["assessment"]
        worlds.append({
            "world": "W%d" % n,
            "order": n,
            "variant_id": a["variant_id"],
            "confidence_class": a["confidence_class"],
            "priority_class": a["priority_class"],
            "passage_fidelity": passage_fidelity(a),
            "rule": r.get("rule"),
            "hypotheses_in_this_world": 1,
            "construction_provenance": r.get("construction"),
            "admission": {k: a[k] for k in
                          ("semantic_status", "evidence_basis",
                           "passage_support", "restriction_status",
                           "attachment_status", "reason", "policy_trace")},
            "numeric_weight": None,
            "answer": None,
        })
    return {"worlds": worlds, "rejected": dropped,
            "ordering": ["SOURCE_FAITHFUL", "STABLE_EXTERNAL",
                         "SPECULATIVE_LOW"],
            "note": "one hypothesis per world; no variant suppresses another; "
                    "no weight and no answer is assigned here",
            "policy_version": VERSION}


# ------------------------------------------------------------------ parsing

import re                                              # noqa: E402

_FIELD = re.compile(r"([A-Za-z_]+)\s*=\s*([^;]*)")
FIELDS = {"semantic": ("semantic_status", SEMANTIC_STATUS),
          "evidence": ("evidence_basis", EVIDENCE_BASIS),
          "passage": ("passage_support", PASSAGE_SUPPORT),
          "restriction": ("restriction_status", RESTRICTION_STATUS),
          "attachment": ("attachment_status", ATTACHMENT_STATUS)}


def parse_assessments(text, ids):
    """Read only `ASSESS:` lines.  Strict: nothing is inferred or corrected.

    An unknown value is rejected and reported rather than snapped to the
    nearest legal one; an unknown candidate letter is dropped rather than
    guessed at; a missing candidate stays missing, because a judgment nobody
    made is not one to invent.
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
        head = body.split(";", 1)[0].strip()
        vid = head.strip().strip(".")
        if vid not in ids:
            bad.append({"line": line[:200], "why": "unknown candidate %r"
                        % vid[:20]})
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
                why = "%s=%r is not one of the allowed values" % (key, value[:40])
                break
            row[name] = value
        if why:
            bad.append({"line": line[:200], "why": why})
            continue
        reason = fields.get("reason", "")
        try:
            got[vid] = assess(vid, row["semantic_status"],
                              row["evidence_basis"], row["passage_support"],
                              row["restriction_status"],
                              row["attachment_status"], reason[:400])
        except PolicyError as e:
            bad.append({"line": line[:200], "why": str(e)[:120]})
    missing = [i for i in ids if i not in got]
    return {"readable": bool(got), "assessments": got, "rejected": bad,
            "missing": missing, "complete": not missing}
