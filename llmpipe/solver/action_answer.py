"""Action route: the answer policy and the verification verdicts.

  solve(source, query, backend=None, limits=None, ledger=None) -> an action_result record (runs GK through action_gk)
  decide(source, query, evidence)                              -> the same record from a given evidence record

`decide` reads the adapter's evidence (`action_gk`) and the replay (`action_replay`).  It calls no prover and no
model, so every rule below is tested on fake and saved evidence.  The English of a result is in `action_english`;
docs/reference/experimental-options.md lists the answer forms.  A `-nonegative`
run gives candidates only: `solve` refuses the flag before any launch and
`decide` refuses evidence from such a run (`action_gk.run_query` stays
available for a diagnostic run).

One Boolean obligation (a snapshot question, a verify step, a verify final
formula) has a positive and a negative launch.  Its verdict:

  error       a launch did not complete (timeout, GK error, malformed output, a launch that could not start)
  contested   both launches have a candidate, or a launch has an entry with conflict mass and proofs in both
              directions (the conflict never becomes Yes or No)
  Yes / No    only the positive / only the negative launch has a candidate
  Unknown     neither; a launch that ended at GK's search limit, or whose diagnostic relaunch failed or differed,
              makes the Unknown inconclusive, with the reason recorded

Before any answer, the replay checks the initial state of the query's planning
root.  An established conflict gives `inconsistent_action_state` for every
query kind, including the empty plan.  A root the replay cannot check is noted.

Snapshot questions (question, ask, verify with no steps) answer from the paired
verdict; the replay is not required.  A snapshot view has no effect or frame
clause, so the known frame failure (M29.neg) cannot occur there.

A supplied sequence (verify with steps):

  Yes         every step and the final formula are Yes, the joint question has a candidate, and the replay
              validates the sequence and the final state
  No          the first step that is not Yes is No, every step before it is Yes and the replay validates that
              prefix; or every step is Yes and the final formula is No.  Every No needs the replay's own No at
              the same place, at the first step too: the M29.neg class (a negative through a frame after a
              conditional effect) is restricted by this rule, not by a fixture name, and the same frame negative
              arises at the root of a verify input that holds a conditional effect (GK says No at 0.99 where the
              replay finds the permission unknown)
  contested   the first step that is not Yes, or the final formula, is contested
  Unknown     the first step that is not Yes is Unknown (a later negative is not a No), or the final formula is
              Unknown, or a GK Yes or No that the replay does not confirm; the result names the disagreement

A verification whose final formula's negative obligation needs negative persistence, which the starting backend
refuses, keeps a Yes: its positive obligations need no carried negative.  Every other verification answer becomes
`unsupported_backend_requirement` (`negative_persistence_unavailable`), with the prover's reading in the diagnostic.

A discovery (plan, reachable): every candidate of the plan launch is replayed
in GK's order, with the goal's reported witnesses bound and the query's step
bound, until one is valid.  An invalid first candidate never hides a valid
later one.  A valid candidate gives `plan_found` (or `goal_already_holds` for the
empty plan); candidates that all fail give `candidate_not_validated` with each
verdict; no candidate gives `not_found`, never a proof that no plan exists.  A
below-cutoff answer is not a candidate, so a legal replay cannot promote it.

Confidence.  A result's confidence is the GK confidence of the answer it uses
(a Boolean candidate, the joint question of a Yes verification, the plan
candidate), with the adapter's label: `validated` or `experimental`.  `proof`
keeps that entry's raw answer, clause names, proof steps and its own label;
the candidate's reasons can be the union over entries of equal confidence.  C29.Q2's
0.1296 and c30 `overlap`'s 0.84 reach the result labelled experimental.

Answers.  question, verify: Yes, No, Unknown or contested.  ask: the first
candidate's term (all terms in `answers`), or Unknown.  plan: Yes when a plan
is found, `none` otherwise.  reachable: Yes when a plan is found, Unknown
otherwise.
"""


import action_english as aen
import action_gk as ag
import action_replay as rp
import action_route as ar
import lc_action_query as lq

CUTOFF = ag.CUTOFF
INCONCLUSIVE = ("search_limit", "not_diagnosed", "diagnostic_error", "diagnostic_differs")
NONEGATIVE = ("a -nonegative run gives candidates only: GK skips its search for negative evidence, so the answer "
              "policy decides nothing from it; use action_gk.run_query for a diagnostic run")
PASS_THROUGH = ("translation_invalid", "unsupported_translation", "insufficient_search_allowance",
                "unsupported_backend_requirement", "backend_unavailable", "backend_incompatible", "call_limit")


# ---------------------------------------------------------------------------
# launches and obligation verdicts


def _conflict(ev):
  """The entries of a launch with explicit conflict mass and proofs in both directions."""
  return [e for e in ev["rejected"] + ev["accepted"]
          if isinstance(e.get("conflict"), (int, float)) and e["conflict"] > 0 and e.get("both_proofs")]


def _best(ev):
  cs = ev["candidates"]
  return max(cs, key=lambda c: c["confidence"]) if cs else None


def _issue(pol, ev):
  if ev is None:
    return {"launch": pol, "status": "not_launched"}
  if ev["status"] != "completed":
    return {"launch": pol, "status": ev["status"], "error": ev.get("error")}
  return None


def _inconclusive(pol, ev):
  if ev is not None and ev["status"] == "completed" and not ev["candidates"] and ev["termination"] in INCONCLUSIVE:
    return "%s: %s" % (pol, ev["termination"])
  return None


def proof_of(ev, c):
  """The raw answer and proof of the entry that supplies a candidate's confidence, kept with the result."""
  e = ev["accepted"][c["confidence_entry"]]
  return {"obligation": ev.get("obligation"), "polarity": ev.get("polarity"), "entry": c["confidence_entry"],
          "answer": e["answer"], "confidence": e["confidence"], "confidence_status": e.get("confidence_status"),
          "experimental_reasons": e.get("experimental_reasons"), "sources": e["sources"]["positive"],
          "proof": e["positive_proof"]}


def paired(pos, neg):
  """The verdict of one Boolean obligation from its positive and negative launch records."""
  out = {"verdict": None, "issues": [], "notes": [], "confidence": None, "confidence_status": None,
         "experimental_reasons": [], "proof": None}
  out["issues"] = [x for x in (_issue("positive", pos), _issue("negative", neg)) if x]
  if out["issues"]:
    out["verdict"] = "error"
    return out
  p, n = _best(pos), _best(neg)
  conflict = _conflict(pos) + _conflict(neg)
  if (p and n) or conflict:
    out["verdict"] = "contested"
    out["notes"].append("accepted support for both polarities" if p and n
                        else "an entry with conflict mass %s and proofs in both directions"
                        % max(e["conflict"] for e in conflict))
  elif p or n:
    c = p or n
    out["verdict"] = "Yes" if p else "No"
    out.update(confidence=c["confidence"], confidence_status=c["confidence_status"],
               experimental_reasons=list(c["experimental_reasons"]), proof=proof_of(pos if p else neg, c))
  else:
    out["verdict"] = "Unknown"
  out["notes"] += [x for x in (_inconclusive("positive", pos), _inconclusive("negative", neg)) if x]
  return out


def _obligations(evidence):
  return {o["id"]: o for o in evidence["obligations"]}


def _launch_summary(evidence):
  out = []
  for ev in ag.launches(evidence):
    out.append({"obligation": ev["obligation"], "polarity": ev["polarity"], "role": ev["role"], "status": ev["status"],
                "result": ev["result"], "accepted": len(ev["accepted"]), "rejected": len(ev["rejected"]),
                "candidates": len(ev["candidates"]), "termination": ev["termination"], "elapsed": ev["elapsed"]})
  return out


def _prover_failure(issues):
  status = [i["status"] for i in issues]
  if "prover_timeout" in status:
    return "prover_timeout"
  if "launch_failed" in status:
    return "backend_unavailable"
  return "prover_error"


# ---------------------------------------------------------------------------
# the result record


def _base(source, query, evidence, outcome, **fields):
  r = ar.result(outcome, operation="solve_query",
                query={"id": query["query"]["id"], "kind": query["query"]["kind"], "hash": query["hash"],
                       "planning_root": query["planning_root"]},
                source={"source_hash": source["hashes"]["source"], "artifact_hash": source["hashes"]["artifact"]},
                confidence=None, confidence_status=None, experimental_reasons=[], proof=None, render=None, witnesses=None,
                verdicts=[], replay=None, candidates=[], evidence=None)
  r.update(fields)
  if evidence is not None:
    r["calls"]["gk"] = evidence["calls"]["gk"]
    r["calls"]["gk_by_role"] = dict(evidence["calls"]["by_role"])
    r["evidence"] = {"backend": {k: evidence["backend"][k] for k in ("name", "sha256", "strategy_sha256", "status")},
                     "requirements": evidence["requirements"], "incomplete": evidence.get("incomplete") or [],
                     "launches": _launch_summary(evidence)}
  return r


def _replay_summary(r, reading=None):
  if r is None:
    return None
  out = {"verdict": r["verdict"], "step": r["step"], "reason": r["reason"], "checked_prefix": r["checked_prefix"],
         "uncovered": r["uncovered"]}
  if r["goal"] is not None:
    out["goal"] = {"value": r["goal"]["value"], "witness": r["goal"]["witness"]}
  if reading is not None:
    out["reading"] = reading
  return out


def _conflict_facts(r):
  return sorted({f for c in r["conflicts"] for f in c["facts"]})


def _inconsistent(source, query, evidence, r, where):
  english = []
  for c in r["conflicts"]:
    for a in c.get("atoms") or []:
      e = aen.fact_english(source, a)
      if e not in english:
        english.append(e)
  return _base(source, query, evidence, "inconsistent_action_state", step=r["step"], facts=_conflict_facts(r),
               facts_english=english, conflicts=r["conflicts"], replay=_replay_summary(r),
               diagnostics=["%s: %s" % (where, r["reason"])])


def confidence_parts(proof):
  """The parts of a proof's confidence: the uses of the library's frame axioms (`frame_*`, confidence
  0.99 each) and of every other input clause below 1 (an uncertain source rule), each counted by reading the proof as
  a tree (`action_gk.use_counts`), with their products.  The frame part is the library's persistence convention, not
  an uncertainty the text states.  None without proof steps."""
  steps = ag.proof_steps(proof)
  if not steps:
    return None
  uses = ag.use_counts(proof)
  frames, others = {}, {}
  frame_product = other_product = 1.0
  for st in steps:
    meta = st[1]
    if not (isinstance(meta, list) and len(meta) > 3 and meta[0] == "in" and isinstance(meta[3], (int, float))
            and not isinstance(meta[3], bool) and meta[3] < 1):
      continue
    n = uses.get(st[0], 0)
    if str(meta[1]).startswith("frame_"):
      frames[meta[1]] = frames.get(meta[1], 0) + n
      frame_product *= meta[3] ** n
    else:
      others[meta[1]] = others.get(meta[1], 0) + n
      other_product *= meta[3] ** n
  return {"frame_uses": frames, "frame_product": round(frame_product, 4),
          "other_uncertain_uses": others, "other_product": round(other_product, 4)}


def _with_confidence(res, c, proof=None):
  res["confidence"], res["confidence_status"] = c["confidence"], c["confidence_status"]
  res["experimental_reasons"] = list(c["experimental_reasons"])
  res["proof"] = proof if proof is not None else c.get("proof")
  parts = confidence_parts((res["proof"] or {}).get("proof")) if isinstance(res["proof"], dict) else None
  if parts is not None:
    res["confidence_parts"] = parts
  return res


# ---------------------------------------------------------------------------
# decide


def decide(source, query, evidence):
  """The answer of a compiled query from its evidence record.  No prover and no model call."""
  ar.check_artifact(source, ar.SOURCE)
  ar.check_artifact(query, ar.QUERY)
  ar.same_revision(source, query)
  if evidence["query"]["hash"] != query["hash"] or evidence["source"]["artifact_hash"] != source["hashes"]["artifact"]:
    raise ar.ArtifactError("the evidence record belongs to another query or source revision")
  if "-nonegative" in (evidence.get("limits") or {}).get("flags", []):
    raise ar.ArtifactError(NONEGATIVE)
  if evidence["outcome"]:
    o = dict(evidence["outcome"])
    name = o.pop("outcome")
    if name not in PASS_THROUGH:
      raise ar.ArtifactError("unexpected evidence outcome %r" % name)
    return _base(source, query, evidence, name, diagnostics=[o])
  sel = lq.selection_of(query)
  root = rp.replay(source, [], **sel)
  if root["verdict"] == "inconsistent_action_state":
    return _inconsistent(source, query, evidence, root, "the initial state")
  notes = []
  if root["verdict"] == "not_checked":
    notes.append("the initial state was not checked by the replay: %s" % root["reason"])
  kind = query["query"]["kind"]
  if kind in ("plan", "reachable"):
    res = _discovery(source, query, evidence, sel)
  elif kind == "ask":
    res = _ask(source, query, evidence)
  elif kind == "verify" and query["query"]["sequence"]:
    res = _verify(source, query, evidence, sel)
  else:
    res = _snapshot(source, query, evidence)
  res["diagnostics"] = notes + res["diagnostics"]
  if query.get("search") and query["search"].get("covers_bound") is False:
    res["diagnostics"].append("the search covered less than the stated bound (%s < %s)"
                              % (query["search"]["depth"], query["query"]["steps"]["n"]))
  return _negative_side_refusal(source, query, evidence, res)


def _negative_side_refusal(source, query, evidence, res):
  """A verification whose negative obligation needs a requirement that the backend refuses (`polarities`
  ["negative"]): a Yes stands, since it needs no carried negative; No, Unknown and contested become the typed refusal,
  with the prover's reading kept in the diagnostic.  A prover failure and an inconsistent state stay as they are."""
  unmet = [r for r in evidence["requirements"] or [] if r.get("polarities") == ["negative"] and not r["validated"]
           and r["policy"] == "refuse"]
  if not unmet or res["outcome"] != "verification_result" or res["answer"] == "Yes":
    return res
  r = unmet[0]
  refusal = {"reason": r["reason"], "capabilities": [x["capability"] for x in unmet], "units": r["units"],
             "detail": r["detail"], "backend": evidence["backend"]["name"], "polarities": ["negative"],
             "answer_before_refusal": res["answer"]}
  return _base(source, query, evidence, "unsupported_backend_requirement", verdicts=res["verdicts"],
               replay=res["replay"], diagnostics=[refusal] + res["diagnostics"])


def _snapshot(source, query, evidence):
  ob = _obligations(evidence)["q" if "q" in _obligations(evidence) else "final"]
  v = paired(ob["positive"], ob["negative"])
  verdicts = [dict(v, id=ob["id"], role=ob["role"])]
  if v["verdict"] == "error":
    return _base(source, query, evidence, _prover_failure(v["issues"]), verdicts=verdicts, diagnostics=v["issues"])
  res = _base(source, query, evidence, "verification_result", answer=v["verdict"], verdicts=verdicts,
              diagnostics=list(v["notes"]))
  if v["verdict"] in ("Yes", "No"):
    _with_confidence(res, v)
  return res


def _ask(source, query, evidence):
  ob = _obligations(evidence)["q"]
  ev = ob["positive"]
  issue = _issue("positive", ev)
  if issue:
    return _base(source, query, evidence, _prover_failure([issue]), diagnostics=[issue])
  cs = ev["candidates"]
  notes = [x for x in (_inconclusive("positive", ev),) if x]
  if not cs:
    return _base(source, query, evidence, "verification_result", answer="Unknown", diagnostics=notes)
  terms = [c["answer"][0] if len(c["answer"]) == 1 else c["answer"] for c in cs]
  # the entities as a plan names them (T6): "the key", "Ann", "block a"
  named = [aen.name(source, t) if isinstance(t, str) else ", ".join(aen.name(source, x) for x in t) for t in terms]
  res = _base(source, query, evidence, "verification_result", answer=terms[0], answers=terms, answer_names=named,
              candidates=[{"answer": t, "confidence": c["confidence"], "confidence_status": c["confidence_status"]}
                          for t, c in zip(terms, cs)], diagnostics=notes)
  return _with_confidence(res, cs[0], proof_of(ev, cs[0]))


def _verify(source, query, evidence, sel):
  q = query["query"]
  seq, obs = q["sequence"], _obligations(evidence)
  verdicts = []
  for i in range(1, len(seq) + 1):
    o = obs["step%d" % i]
    verdicts.append(dict(paired(o["positive"], o["negative"]), id=o["id"], role="step", step=i))
  o = obs["final"]
  verdicts.append(dict(paired(o["positive"], o["negative"]), id="final", role="final", step=None))
  joint = evidence["joint"]
  issues = [x for v in verdicts for x in v["issues"]]
  ji = _issue("joint", joint)
  if ji:
    issues.append(ji)
  if issues:
    return _base(source, query, evidence, _prover_failure(issues), verdicts=verdicts, diagnostics=issues)
  r = rp.replay(source, seq, goal=q["goal"], **sel)
  reading = rp.verification(r)
  if r["verdict"] == "inconsistent_action_state":
    res = _inconsistent(source, query, evidence, r, "the replayed sequence")
    res["verdicts"] = verdicts
    return res
  # the prover's reading: the first step that is not Yes decides, else the final formula
  gk, place = None, None
  for v in verdicts[:-1]:
    if v["verdict"] != "Yes":
      gk, place = v["verdict"], v["step"]
      break
  if gk is None:
    gk, place = verdicts[-1]["verdict"], "final"
  notes = [n for v in verdicts for n in v["notes"]]
  base = dict(verdicts=verdicts, replay=_replay_summary(r, reading))
  if gk == "Yes":
    jc = _best(joint)
    if jc is None:
      notes.append("every step and the final formula are proved, but the joint question has no candidate")
      return _base(source, query, evidence, "verification_result", answer="Unknown", diagnostics=notes, **base)
    if reading["answer"] != "Yes":
      notes.append("the prover proves the sequence and the goal; the replay does not validate them: %s" % r["reason"])
      return _base(source, query, evidence, "verification_result", answer="Unknown",
                   validation="replay_not_checked" if reading["answer"] == "not_checked" else "replay_disagrees",
                   diagnostics=notes, **base)
    res = _base(source, query, evidence, "verification_result", answer="Yes", diagnostics=notes, **base)
    _with_confidence(res, jc, proof_of(joint, jc))
    if any(v["confidence_status"] == "experimental" for v in verdicts):
      res["confidence_status"] = "experimental"
      res["experimental_reasons"] = sorted(set(res["experimental_reasons"])
                                           | {x for v in verdicts for x in v["experimental_reasons"]})
    return res
  if gk == "No":
    at = place if place != "final" else None
    k = (place - 1) if at is not None else len(seq)
    if r["checked_prefix"] < k:
      notes.append("the prover refutes %s, but the replay does not validate the %d steps before it: %s"
                   % ("step %d" % place if at else "the final formula", k, r["reason"]))
      return _base(source, query, evidence, "verification_result", answer="Unknown", validation="prefix_not_validated",
                   diagnostics=notes, **base)
    # A No needs the replay's own No at the same place, at the first step too: a negative that GK derives
    # through a frame axiom at the root (the blocker-under-hypothesis defect) is not corroborated by a replay that
    # finds the permission unknown.
    same = reading["answer"] == "No" and reading.get("failing_step") == at
    if not same:
      notes.append("the prover refutes %s after %d step(s); the replay reads %s there, so the negative is not "
                   "confirmed" % ("step %d" % place if at else "the final formula", k, reading["answer"]))
      return _base(source, query, evidence, "verification_result", answer="Unknown", validation="replay_disagrees",
                   diagnostics=notes, **base)
    v = verdicts[place - 1] if at else verdicts[-1]
    res = _base(source, query, evidence, "verification_result", answer="No", failing_step=at, diagnostics=notes, **base)
    return _with_confidence(res, v)
  return _base(source, query, evidence, "verification_result", answer=gk,
               failing_step=place if place != "final" else None, diagnostics=notes, **base)


def bind_witnesses(goal, names, values):
  """The goal with the outer existentials `names` removed and their variables replaced by `values`."""
  env = dict(zip(names, values))

  def sub(f):
    if isinstance(f, list):
      return [sub(x) for x in f]
    return env.get(f, f)

  def drop(f):
    if isinstance(f, list) and f and f[0] == "exists" and f[1] in env:
      return drop(f[2])
    if isinstance(f, list) and f and f[0] == "and":
      return ["and"] + [drop(x) for x in f[1:]]
    return f
  return sub(drop(goal))


def _discovery(source, query, evidence, sel):
  q = query["query"]
  ob = _obligations(evidence)["plan"]
  ev = ob["positive"]
  none = "none" if q["kind"] == "plan" else "Unknown"
  issue = _issue("positive", ev)
  if issue:
    return _base(source, query, evidence, _prover_failure([issue]), diagnostics=[issue])
  notes = []
  if not ev["candidates"]:
    if ev["termination"] in INCONCLUSIVE:
      notes.append("no accepted plan within the search (%s): a bounded non-discovery, not evidence that no plan "
                   "exists" % ev["termination"])
    if ev["accepted"]:
      notes.append("accepted answers that are not candidates: %s"
                   % "; ".join(",".join(e["reasons"]) for e in ev["accepted"]))
    return _base(source, query, evidence, "not_found", answer=none, diagnostics=notes)
  names = [o for o in query["obligations"] if o["id"] == "plan"][0].get("witnesses") or []
  tried, found = [], None
  for c in ev["candidates"]:
    goal = bind_witnesses(q["goal"], names, c["witnesses"]) if names else q["goal"]
    r = rp.replay(source, c["plan"], goal=goal, steps=q["steps"], **sel)
    row = {"plan": c["plan"], "witnesses": c["witnesses"], "term": c["term"], "confidence": c["confidence"],
           "confidence_status": c["confidence_status"], "verdict": r["verdict"], "step": r["step"],
           "reason": r["reason"], "uncovered": r["uncovered"]}
    tried.append(row)
    if r["verdict"] == "valid":
      found = (c, r)
      break
  if found is None:
    return _base(source, query, evidence, "candidate_not_validated", answer=none, candidates=tried,
                 diagnostics=["no candidate is validated by the replay: %s"
                              % "; ".join("%s at step %s" % (t["verdict"], t["step"]) for t in tried)])
  c, r = found
  outcome = "plan_found" if c["plan"] else "goal_already_holds"
  res = _base(source, query, evidence, outcome, answer="Yes", plan=c["plan"], candidates=tried,
              witnesses=dict(zip(names, c["witnesses"])) if names else None,
              replay=_replay_summary(r), diagnostics=notes, **aen.plan_fields(source, c["plan"], r["steps"]))
  return _with_confidence(res, c, proof_of(ev, c))


# ---------------------------------------------------------------------------
# solve


def solve(source, query, backend=None, limits=None, ledger=None):
  """Run a compiled query on the registered backend and decide its answer."""
  ar.check_artifact(source, ar.SOURCE)
  ar.check_artifact(query, ar.QUERY)
  ar.same_revision(source, query)
  if query["outcome"]:
    o = dict(query["outcome"])
    return _base(source, query, None, o.pop("outcome"), diagnostics=[o])
  if not query["obligations"]:
    return ar.result(ar.NOT_IMPLEMENTED, operation="solve_query",
                     detail="the query has no obligations (pending passes %s)" % query["pending_passes"])
  if "-nonegative" in ag.normalize_limits(limits)["flags"]:
    raise ar.ArtifactError(NONEGATIVE)
  evidence = ag.run_query(source, query, backend, limits, ledger)
  return decide(source, query, evidence)
