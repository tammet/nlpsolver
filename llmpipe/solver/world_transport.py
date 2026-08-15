"""From a six-axis admission record to a GK world, and nothing else.

One canonical formula becomes one hypothesis, whatever number of derivations
produced it, and every derivation travels with it as metadata.  The clause GK
receives is determined by the formula alone: passage support, the old confidence
class and the world order have no effect on it whatsoever, and a test asserts
that by compiling the same formula under altered labels and comparing bytes.

Eligibility is read from the record's `world_kind` and from nothing else.
Archived, rejected and otherwise non-executable entries cannot reach the
transport: they are refused here as well as filtered upstream, because a single
gate is a single point of failure and this one has a hostile fixture aimed at it.

Every submission and every refusal is written to a log, so "it was never sent"
is a claim about a record rather than an inference from an answer that did not
appear.
"""

import json

import admission_record as AR
import bridge_world as BW

VERSION = "world_transport/1.0"

# No numeric calibration exists, and inventing one here would put a number on
# the schedule that nothing has measured.  Every hypothesis carries 1.0, so the
# adjusted confidence equals gk's own and is reported as unadjusted.
PLACEHOLDER_WEIGHT = 1.0
WEIGHT_POLICY = ("placeholder 1.0 for every hypothesis: no numeric calibration "
                 "exists, so the dynamic confidence equals gk's and is marked "
                 "unadjusted rather than being scaled by an invented number")

RUNNABLE = (AR.EXECUTABLE, AR.EXPLORATORY)

TRANSPORT_LOG = []


class TransportError(Exception):
    """A hypothesis that must not run reached the transport."""


def reset_log():
    del TRANSPORT_LOG[:]


def log():
    return list(TRANSPORT_LOG)


def _note(kind, **kw):
    row = dict(kw)
    row["event"] = kind
    TRANSPORT_LOG.append(row)
    return row


def eligible(record):
    """Runnable or not, from `world_kind` alone."""
    return record.get("world_kind") in RUNNABLE


def hypotheses_from_records(records, packages, case_id=None):
    """Records -> one hypothesis per canonical formula.  Refusals are logged.

    `packages` maps a printed formula to its Stage-2 package; the caller
    resolves it from the construction library, so nothing here re-derives a
    formula and nothing can silently substitute a different one.

    The hypothesis id is qualified by the case.  An admission record's own id
    is only unique within its case, and the first smoke run submitted three
    different formulas all called `H1` — which made the transport log unable to
    say which hypothesis had been sent.  The clause is unaffected; only the
    name is.
    """
    out, seen = [], {}
    for rec in records:
        printed = rec["printed_formula"]
        if not eligible(rec):
            _note("refused", hypothesis_id=rec.get("hypothesis_id"),
                  variant_id=rec.get("variant_id"), formula=printed,
                  world_kind=rec.get("world_kind"),
                  why="world_kind=%s is not runnable" % rec.get("world_kind"))
            continue
        pkg = packages.get(printed)
        if pkg is None:
            _note("refused", hypothesis_id=rec.get("hypothesis_id"),
                  variant_id=rec.get("variant_id"), formula=printed,
                  why="no package was resolved for this formula")
            continue
        if printed in seen:
            # the same canonical formula: one hypothesis, paths merged
            h = seen[printed]
            h["derivation_paths"].extend(
                rec["axes"]["provenance"]["derivation_paths"])
            h["merged_variants"].append(rec["variant_id"])
            _note("merged", hypothesis_id=h["hypothesis_id"],
                  variant_id=rec["variant_id"], formula=printed,
                  why="same canonical formula: charged once")
            continue
        cid = rec.get("case_id") or case_id
        h = {
            "hypothesis_id": ("%s::%s" % (cid, rec["hypothesis_id"])
                              if cid else rec["hypothesis_id"]),
            "record_hypothesis_id": rec["hypothesis_id"],
            "case_id": cid,
            "label": rec["variant_id"],
            "package": pkg,
            "weight": PLACEHOLDER_WEIGHT,
            "printed_formula": printed,
            "merged_variants": [rec["variant_id"]],
            "derivation_paths": list(
                rec["axes"]["provenance"]["derivation_paths"]),
            "admission": {k: rec["axes"][k] for k in
                          ("semantic", "passage", "direction", "restriction",
                           "attachment")},
            "world_kind": rec["world_kind"],
            "order_key": rec["order_key"],
        }
        seen[printed] = h
        out.append(h)
    return out


def build_world(world_id, hypothesis, stored, configuration):
    """One hypothesis -> one dynamic world.  The clause comes from the formula.

    Nothing about the admission labels is passed to the compiler: it receives
    the package, the case's own parse and its configuration, and that is all.
    """
    if hypothesis["world_kind"] not in RUNNABLE:
        raise TransportError("%s is %s and must not be built"
                             % (hypothesis["hypothesis_id"],
                                hypothesis["world_kind"]))
    world = BW.build_dynamic_world(
        world_id, [{"hypothesis_id": hypothesis["hypothesis_id"],
                    "weight": hypothesis["weight"],
                    "label": hypothesis["label"],
                    "package": hypothesis["package"],
                    "case_id": hypothesis.get("case_id")}],
        stored["stage1"], stored["stage2"], configuration,
        base_clauses=stored["final_clauses"])
    world["derivation_paths"] = hypothesis["derivation_paths"]
    world["derivation_path_count"] = len(hypothesis["derivation_paths"])
    world["admission"] = hypothesis["admission"]
    world["weight_policy"] = WEIGHT_POLICY
    return world


def submit(world, hypothesis, stored, run):
    """Hand a world to gk.  Every submission is logged before the call.

    `run(clauses)` performs the call; the transport does not import a prover,
    so a test can pass a spy and be sure nothing else reached one.
    """
    if hypothesis["world_kind"] not in RUNNABLE:
        _note("blocked", hypothesis_id=hypothesis["hypothesis_id"],
              formula=hypothesis["printed_formula"],
              world_kind=hypothesis["world_kind"],
              why="a non-runnable hypothesis reached submit()")
        raise TransportError("%s is %s and must not be submitted"
                             % (hypothesis["hypothesis_id"],
                                hypothesis["world_kind"]))
    clauses = list(stored["final_clauses"]) + [
        dict(c) for c in world["compiled_bridge_clauses"]]
    _note("submitted", hypothesis_id=hypothesis["hypothesis_id"],
          world_id=world["world_id"],
          formula=hypothesis["printed_formula"],
          clause_names=[c.get("@name") for c in
                        world["compiled_bridge_clauses"]],
          clause_count=len(clauses),
          package_sha=_sha(hypothesis["package"]))
    return run(clauses)


def _sha(obj):
    import hashlib
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()
                          ).hexdigest()[:16]


def submitted_hypothesis_ids():
    return sorted(set(r["hypothesis_id"] for r in TRANSPORT_LOG
                      if r["event"] == "submitted"))


def submitted_clause_names():
    out = set()
    for r in TRANSPORT_LOG:
        if r["event"] == "submitted":
            out.update(r.get("clause_names") or [])
    return sorted(out)
