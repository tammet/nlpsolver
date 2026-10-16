"""Action route: the plan search of a plan or reachable query.

  solve(source, query_pkg, query_artifact, backend, limits, ledger, compile_limits, selection) -> result record

A plan of the ground planning model is a proposal; GK and the replay decide.  The steps:

1. The model.  `plan_builder.Task` reads the compiled discovery input.  An exception, or a model with an open action
   functor, an unbounded add effect or a frame clause it could not use, gives no proposal.
2. The proposals.  The builder's ways (`ehc`, `agenda`, `bfws`) each give at most one plan, strict effects first.
   Duplicates and plans outside the query's step bound are dropped; the route's replay drops a plan it finds invalid
   or inconsistent.  The kept plans are sorted by length, at most MAX_CANDIDATES.
3. The checks.  Each kept plan is compiled as the query with the plan's situation in the discovery question
   (`action_route.compile_query(plan_situation=...)`) and launched with the `$planstate` records of the families the
   model covers completely, under the role strategy `discovery:check` (one answer, no termination relaunch).  A check
   that finds no proof while a family was left out or the model has a note runs once more without the records.  The
   first check whose result is a plan the replay validates is the answer.
4. When no plan passed: if the model covers the text (no open atom, no ignored text clause) and the builder found
   no plan, today's discovery launch decides.  Otherwise a discovery launch with the plan filters runs first (role
   `discovery:filtered`), and today's launch only when it found no plan.

Every stage falls through to today's discovery launch, and the answer policy of each launch is unchanged.  The
result carries `plan_search`, the record of every stage.  docs/architecture/action-answers.md describes the
procedure.
"""

import copy
import time

import action_answer as aa
import action_gk as ag
import action_replay as rp
import action_route as ar
import lc_action_query as lq
import plan_analysis as pa
import plan_builder as pb
import plan_state as ps

VARIANTS = ("ehc", "agenda", "bfws")
MAX_CANDIDATES = 3
CHECK_SECONDS = 60
ACCEPTED = ("plan_found", "goal_already_holds")
DROPPED_VERDICTS = ("invalid", "inconsistent_action_state")
IMPOSSIBLE = ("impossible_pair", "impossible_start", "impossible_action")


def eligible(query_artifact):
  """True for a compiled plan or reachable query that the prover would run."""
  return (query_artifact["query"]["kind"] in ("plan", "reachable") and not query_artifact["outcome"]
          and bool(query_artifact["obligations"]))


def _model(source, query_artifact):
  """(task or None, the model record)"""
  rec = {"status": None, "reason": None, "notes": [], "ignored": [], "open_atoms": 0}
  try:
    objs = ar.query_input(source, query_artifact, "plan", "positive")
    task = pb.Task(objs, query_artifact["query"]["id"])
  except Exception as e:                                   # noqa: BLE001  a model failure only skips the proposals
    rec.update(status="model_error", reason="%s: %s" % (type(e).__name__, e))
    return None, rec
  rec.update(notes=list(task.notes), ignored=list(task.m.ignored), open_atoms=len(task.m.open_atoms),
             actions=len(task.acts))
  if not task.closed:
    rec.update(status="unusable", reason="the model has an open action functor, an unbounded add effect or a note")
  elif task.m.unused_frames:
    rec.update(status="unusable", reason="a frame clause the model could not use")
  else:
    rec["status"] = "usable"
  return task, rec


def _covers_text(task, model):
  """The model read every text clause: no open atom and no ignored text clause."""
  return model["status"] == "usable" and not task.m.open_atoms and not any(n.startswith("src:") for n in task.m.ignored)


def _within_bound(n, search):
  depth = search.get("depth")
  if depth is None:
    return True
  return n == depth if search.get("require_zero_remaining") else n <= depth


def _situation(plan_terms, root):
  s = root
  for a in plan_terms:
    s = ["$do", copy.deepcopy(a), s]
  return s


def _proposals(task, source, query_artifact):
  """(kept candidates, the builder record)"""
  rec = {"variants": [], "dropped": []}
  seen, found = set(), []
  for v in VARIANTS:
    t0 = time.process_time()
    try:
      r = pb.build(task, v)
    except Exception as e:                                 # noqa: BLE001  a builder failure only skips this way
      rec["variants"].append({"variant": v, "status": "builder_error", "reason": "%s: %s" % (type(e).__name__, e),
                              "cpu": round(time.process_time() - t0, 3)})
      continue
    rec["variants"].append({"variant": v, "status": r["status"], "plan": r.get("plan"), "cpu": r.get("cpu")})
    if r["status"] != "found":
      continue
    key = repr(r["plan_terms"])
    if key in seen:
      continue
    seen.add(key)
    found.append({"variant": v, "plan_terms": r["plan_terms"], "plan": r["plan"],
                  "defeasible": r.get("defeasible", False)})
  q, search = query_artifact["query"], query_artifact["search"] or {}
  sel = lq.selection_of(query_artifact)
  goal = q["goal"] if not q.get("witnesses") else None
  kept = []
  for c in sorted(found, key=lambda c: (len(c["plan_terms"]), c["defeasible"])):
    if not _within_bound(len(c["plan_terms"]), search):
      rec["dropped"].append({"plan": c["plan"], "reason": "outside the step bound %s" % search.get("depth")})
      continue
    r = rp.replay(source, [ag.source_term(a) for a in c["plan_terms"]], goal=goal, steps=q["steps"], **sel)
    c["replay"] = {"verdict": r["verdict"], "step": r["step"], "reason": r["reason"]}
    if r["verdict"] in DROPPED_VERDICTS:
      rec["dropped"].append({"plan": c["plan"], "reason": "replay %s at step %s" % (r["verdict"], r["step"])})
      continue
    kept.append(c)
  kept.sort(key=lambda c: c["replay"]["verdict"] != "valid")
  rec["kept"] = [{"plan": c["plan"], "variant": c["variant"], "replay": c["replay"]} for c in kept[:MAX_CANDIDATES]]
  return kept[:MAX_CANDIDATES], rec


def _summary(res):
  return {"outcome": res["outcome"], "answer": res.get("answer"), "plan": res.get("plan"),
          "confidence": res.get("confidence"), "gk": (res.get("calls") or {}).get("gk"),
          "diagnostics": res.get("diagnostics") or []}


def _check(source, query_pkg, task, c, query_artifact, backend, ledger, compile_limits, selection, model, results):
  """(the accepted result or None, the check record); every launch result is appended to `results`"""
  root = query_artifact["planning_root"]
  cq = ar.compile_query(query_pkg, source, compile_limits, plan_situation=_situation(c["plan_terms"], root),
                        **(selection or {}))
  rec = {"plan": c["plan"], "variant": c["variant"], "query_hash": cq["hash"], "attempts": []}
  if cq["outcome"]:
    rec["attempts"].append({"states": None, "outcome": cq["outcome"]["outcome"]})
    return None, rec
  recs, info = ps.records(task, c["plan_terms"], root) if model["status"] == "usable" else ([], None)
  tries = [recs] if recs else [[]]
  if recs and (info["left_out"] or task.notes):
    tries.append([])
  for extra in tries:
    lim = {"seconds": CHECK_SECONDS, "termination": False, "strategy_role": "discovery:check", "extra_clauses": extra}
    res = aa.solve(source, cq, backend, lim, ledger)
    results.append(res)
    rec["attempts"].append(dict(_summary(res), states=len(extra), families=info and info["families"],
                                left_out=info and info["left_out"]))
    if res["outcome"] in ACCEPTED:
      return res, rec
  return None, rec


def _filter_records(task):
  """(the `$planfilter` clause objects, the filter record)"""
  try:
    doc = pa.Analysis(task.m, task.g).to_json()
  except Exception as e:                                   # noqa: BLE001  no filters on an analysis failure
    return [], {"status": "analysis_error", "reason": "%s: %s" % (type(e).__name__, e)}
  out = []
  for f in doc["filters"]:
    if f["kind"] not in IMPOSSIBLE and doc["useless_filters"] != "enabled":
      continue
    dist = ["$distinct"] + [["$pair", x, y] for x, y in f.get("distinct", [])]
    out.append({"@name": "planfilter:%s" % f["id"], "@logic": [["$planfilter", f["kind"], f["pattern"], dist]]})
  return out, {"status": "generated", "filters": len(out), "useless_filters": doc["useless_filters"]}


def _with_search(res, query_artifact, record, results):
  """The result of the original query: `res` with the original query's identity, the total GK calls of every
  stage and the plan-search record."""
  # the launches of the other stages; the evidence of `res` holds only its own query's launches
  earlier = [x for r in results if r is not res for x in ((r.get("evidence") or {}).get("launches") or [])]
  res = dict(res)
  checked = res.get("query")
  res["query"] = {"id": query_artifact["query"]["id"], "kind": query_artifact["query"]["kind"],
                  "hash": query_artifact["hash"], "planning_root": query_artifact["planning_root"]}
  calls = dict(res.get("calls") or {})
  calls["gk"] = sum((r.get("calls") or {}).get("gk") or 0 for r in results)
  by_role = {}
  for r in results:
    for k, v in ((r.get("calls") or {}).get("gk_by_role") or {}).items():
      by_role[k] = by_role.get(k, 0) + v
  calls["gk_by_role"] = by_role
  res["calls"] = calls
  record["answered_query"] = checked
  record["earlier_launches"] = earlier
  res["plan_search"] = record
  return res


def solve(source, query_pkg, query_artifact, backend, limits, ledger, compile_limits=None, selection=None):
  """The result of one eligible plan or reachable query, by the steps of the module docstring."""
  record = {"version": 1, "stage": None, "model": None, "builder": None, "checks": [], "filters": None,
            "launches": []}
  results = []
  task, model = _model(source, query_artifact)
  record["model"] = model
  kept = []
  if task is not None and model["status"] == "usable":
    kept, record["builder"] = _proposals(task, source, query_artifact)
  for c in kept:
    res, rec = _check(source, query_pkg, task, c, query_artifact, backend, ledger, compile_limits, selection, model,
                      results)
    record["checks"].append(rec)
    if res is not None:
      record["stage"] = "builder_check"
      return _with_search(res, query_artifact, record, results)
  if task is not None and _covers_text(task, model) and record["builder"] is not None and not kept \
     and not record["builder"]["dropped"]:
    res = aa.solve(source, query_artifact, backend, limits, ledger)
    results.append(res)
    record["launches"].append(dict(_summary(res), kind="discovery"))
    record["stage"] = "discovery_model_no_plan"
    return _with_search(res, query_artifact, record, results)
  if task is not None:
    filters, record["filters"] = _filter_records(task)
    if filters:
      lim = dict(limits or {}, strategy_role="discovery:filtered", extra_clauses=filters, termination=False)
      res = aa.solve(source, query_artifact, backend, lim, ledger)
      results.append(res)
      record["launches"].append(dict(_summary(res), kind="filtered"))
      if res["outcome"] in ACCEPTED:
        record["stage"] = "filtered_discovery"
        return _with_search(res, query_artifact, record, results)
  res = aa.solve(source, query_artifact, backend, limits, ledger)
  results.append(res)
  record["launches"].append(dict(_summary(res), kind="discovery"))
  record["stage"] = "discovery"
  return _with_search(res, query_artifact, record, results)
