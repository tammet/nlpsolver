"""WP15 checks: the formal-input route end to end, through the production entry `solve.english_to_answer`.

No model call and no GK launch: fake GK builds (registered for this check), a fake model provider and a fake
prompt bundle, labelled as such.  The live GK evidence is the WP15 manifest (elogs/wp15_task_b_2026_09_26/).

  examples     the formal examples are the fresh generation from gold (make_examples.py --check); each compiles
               once and takes all its queries, with the source hashes unchanged (source reuse)
  outcomes     every typed outcome of A5.3 that the route produces (and model_error), each from a gold or fake
               input: the outcome, the answer convention (`Cannot answer:` exactly for an unsupported outcome,
               `Error:` exactly for another non-answer), answered_by and run_outcome
  counters     per call: logical model calls equal the translation's requests, provider attempts equal the fake
               provider's requests, refused calls are counted; GK launches by role add up to the total, which
               equals the run collector's gk_calls
  llmcall      a provider that raises leaves one failed, logical entry in the call log (a WP15 repair)
"""

import contextlib
import copy
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_gk as ag
import action_pipeline as ap
import action_english as aen
import action_route as ar
import check_action_answer as caa
import check_action_availability as cav
import check_action_gk as cag
import check_action_pipeline as cap
import fixture_materialize as fm
import llmcall
import make_examples
import solve

need = cav.need
GOLD = {c["case"]: c for c in fm.load_all()}


def formal(case, qids=(), limits=None):
  """The formal record of a gold case with some of its queries."""
  c = GOLD[case]
  rec = {"text": c["text"], "entities": c["entities"],
         "units": [{k: u[k] for k in ("id", "text", "stage1", "stage2", "context") if u.get(k) is not None}
                   for u in c["units"]], "queries": []}
  if c.get("worlds"):
    rec["worlds"] = c["worlds"]
  for qid in qids:
    q = [x for x in c["queries"] if x["id"] == qid][0]
    e = {"stage2": q["stage2"]}
    e.update(fm.selection(q))
    if q.get("limits"):
      e["limits"] = {"search_cap": q["limits"]["search_cap"], "explicit": q["limits"].get("explicit", True)}
    rec["queries"].append(e)
  return rec


def through_route(world, text, options):
  """One call through english_to_answer; returns (answer, collect, the call-log entries of the call, the fake
  provider's action requests)."""
  mark, req = len(llmcall.call_log), len(world.requests)
  collect = {}
  with contextlib.redirect_stdout(io.StringIO()):
    ans = solve.english_to_answer(text, options, collect)
  return ans, collect, llmcall.call_log[mark:], [r for r in world.requests[req:] if r[0] in ("a1", "a2")]


def reconcile(what, collect, log, requests):
  rec = collect["action_route"]
  calls = rec["calls"]
  mine = [e for e in log if e.get("tag") == ap.TAG]
  need(calls["logical"] == sum(1 for e in mine if e.get("logical")), "%s: logical calls" % what)
  need(calls["provider_attempts"] == len(requests), "%s: provider attempts %d, fake requests %d"
       % (what, calls["provider_attempts"], len(requests)))
  need(calls["refused"] == sum(1 for e in mine if e.get("source") == "refused"), "%s: refused calls" % what)
  tr = rec.get("translation")
  if tr:
    need(calls["logical"] == len(tr["history"]), "%s: logical calls %d, translation requests %d"
         % (what, calls["logical"], len(tr["history"])))
  res = rec.get("result") or {}
  results = res.get("results") if res.get("outcome") == "several" else [res]
  gk = sum((r.get("calls") or {}).get("gk", 0) for r in results)
  by_role = sum(sum(((r.get("calls") or {}).get("gk_by_role") or {}).values()) for r in results)
  need(calls["gk"] == gk == by_role == len(collect.get("gk_calls") or []),
       "%s: GK launches %d, by the results %d, by role %d, in the collector %d"
       % (what, calls["gk"], gk, by_role, len(collect.get("gk_calls") or [])))


def check_examples():
  need(make_examples.main(["--check"]) == 0, "the examples drift from the gold")
  n = 0
  for name in sorted(make_examples.EXAMPLES):
    rec = json.load(open(os.path.join(make_examples.OUT, name + ".json")))
    units = rec["units"]
    s1 = [{"id": u["id"], "text": u.get("text"), "stage1": u["stage1"]} for u in units] if all(u.get("stage1") for u in units) else None
    a = ar.compile_source(s1, [u["stage2"] for u in units], "physical_v1", rec["text"], rec["entities"],
                          worlds=rec.get("worlds"), contexts={u["id"]: u["context"] for u in units if u.get("context")} or None)
    need(a["support"]["status"] == "supported", "%s: %s" % (name, a["support"]))
    before = ar.canonical(a)
    for q in rec["queries"]:
      qa = ar.compile_query(q["stage2"], a, q.get("limits"), None,
                            **{k: q[k] for k in ("planning_root", "ambient", "knower") if k in q})
      need(qa["source"]["source_hash"] == a["hashes"]["source"] and (qa["obligations"] or qa["outcome"]),
           "%s %s: %r" % (name, q["stage2"][1], qa["outcome"]))
      n += 1
    need(ar.canonical(a) == before, "%s: attaching the queries changed the source artifact" % name)
  print("  examples: %d formal examples are the fresh generation from gold; each source compiles once and takes its "
        "%d queries with its hashes unchanged" % (len(make_examples.EXAMPLES), n))


def check_outcomes():
  rows = []
  with cap.World() as w:
    tmp_names = []
    plan = caa.answers(([cap.PLAN], 1.0))
    good = caa.fake({"plan:positive": plan})
    empty = caa.fake({})
    yes_all = caa.fake({k: caa.yes() for k in ("step1:positive", "step2:positive", "final:positive", "joint:positive")})
    w.backend = good
    take = ["take", "hand 1", "a 2"]
    bad_plan = caa.fake({"plan:positive": caa.answers(([caa.do(take, ["put_on", "hand 1", "a 2", "a 2"])], 0.98))})
    root = caa.fake({"plan:positive": caa.answers((["W0"], 1.0))})
    failing = caa.fake({"plan:positive": "error"})
    import tempfile
    tmp = tempfile.mkdtemp()
    warn = cag.fake_backend(tmp, "warn")
    sleep = cag.fake_backend(tmp, "sleep")
    absent = cag.fake_backend(tmp, "proved", path=os.path.join(tmp, "absent_binary"))
    import check_action_summary_route as csr
    profile_error = csr.fake(tmp, {"error": "planning_profile_error: operation 3: unknown term"}, exit_code=1)[0]
    F = lambda backend, **k: dict({"actions_flag": True, "formal_flag": True, "action_backend": backend}, **k)
    travel = json.dumps(formal("p01_travel:base", ["Q1"]))
    cases = [
      ("source_compiled", json.dumps(formal("p01_travel:base")), F(good), True),
      ("plan_found", travel, F(good), True),
      ("goal_already_holds", json.dumps(formal("c12_step_bounds:base", ["Q3"])), F(root), True),
      ("verification_result", json.dumps(formal("c20_verify:a_red", ["Q1"])), F(yes_all), True),
      ("not_found", travel, F(empty), True),
      ("candidate_not_validated", json.dumps(dict(formal("c20_verify:a_red"), queries=[
        {"stage2": ["@id", "QP", ["plan", ["is rel2", "on", "a 2", "b 3"]]]}])), F(bad_plan), True),
      ("inconsistent_action_state", json.dumps(formal("c09_inconsistent_states:empty_and_holding", ["Q1"])), F(root), True),
      ("unsupported_backend_requirement", json.dumps(formal("c01_unlicensed_polish:base", ["Q1"])), F(good), False),
      ("unsupported_translation", json.dumps(formal("c07_clean_bowl:base", ["Q1"])), F(good), False),
      ("translation_invalid", json.dumps(formal("c14_source_reuse:base", ["Q5"])), F(good), False),
      ("insufficient_search_allowance", json.dumps(formal("c20_verify:a_red", ["Q6"])), F(good), False),
      ("backend_unavailable", travel, F(absent), False),
      ("backend_incompatible", travel, F(warn), False),
      ("prover_timeout", travel, F(sleep, prover_seconds=1, prover_seconds_cli=True), False),
      ("prover_error", travel, F(failing), False),
      # -planning-summary on a build that refuses the profile: a typed error, no answer
      ("planning_profile_error", travel, F(profile_error, planning_summary_flag=True), False),
    ]
    saved_extra = ag.EXTRA
    ag.EXTRA = 0
    try:
      for want, text, opts, answered in cases:
        ans, col, log, req = through_route(w, text, opts)
        rec = col["action_route"]
        got = rec["result"]["outcome"]
        need(got == want, "%s: the route gives %s (%r)" % (want, got, ans[:120]))
        # a non-answer is `Cannot answer:` for a text the route does not model, `Error:` for a failed run
        cannot = want in aen.CANNOT_ANSWER
        need(ans.startswith("Cannot answer: ") == cannot and ans.startswith("Error:") == (not answered and not cannot)
             and (col["answered_by"] == ap.TAG) == answered
             and col["run_outcome"] == (want if answered else "error"), "%s: answer convention %r / %r / %r"
             % (want, ans[:80], col["answered_by"], col["run_outcome"]))
        reconcile(want, col, log, req)
        rows.append(want)
    finally:
      ag.EXTRA = saved_extra
    # the English route with the fake bundle: typed model outcomes, and not_implemented without a bundle
    english = [("call_limit", [cap.travel_stage1()], [cap.travel_stage2()], {"llm_call_limit": 1}),
               ("model_timeout", [llmcall.LlmDeadlineExceeded("provider wait")], [], {}),
               ("model_error", [RuntimeError("a provider fault")], [], {})]
    for want, a1, a2, extra in english:
      w.script = {"a1": list(a1), "a2": list(a2)}
      ans, col, log, req = through_route(w, cap.TRAVEL_TEXT, dict({"actions_flag": True, "action_backend": good}, **extra))
      need(col["action_route"]["result"]["outcome"] == want and ans.startswith("Error: " + want)
           and col["answered_by"] is None, "%s: %r" % (want, ans[:120]))
      reconcile(want, col, log, req)
      rows.append(want)
    w.script = {"a1": [cap.travel_stage1()], "a2": [cap.travel_stage2()]}
    ans, col, log, req = through_route(w, cap.TRAVEL_TEXT, {"actions_flag": True, "action_backend": good})
    need(col["action_route"]["result"]["outcome"] == "plan_found" and col["action_route"]["calls"]["logical"] == 2,
         "the English route with the fake bundle: %r" % ans)
    reconcile("English plan", col, log, req)
    real = ap.DEFAULT_BUNDLE
    ap.DEFAULT_BUNDLE = "no-such-bundle"
    try:
      ans, col, log, req = through_route(w, cap.TRAVEL_TEXT, {"actions_flag": True, "action_backend": good})
    finally:
      ap.DEFAULT_BUNDLE = real
    need(col["action_route"]["result"]["outcome"] == ar.NOT_IMPLEMENTED and ans.startswith("Error: not_implemented")
         and not req, "not_implemented: %r" % ans)
    rows.append(ar.NOT_IMPLEMENTED)
    # several queries in one record: the verification sub-launches are counted by role and reconcile
    rec = formal("c20_verify:a_red", ["Q1", "Q4"])
    ans, col, log, req = through_route(w, json.dumps(rec), F(yes_all))
    need(col["action_route"]["result"]["outcome"] == "several" and col["action_route"]["calls"]["gk"] > 7,
         "several verifications: %r" % col["action_route"]["calls"])
    reconcile("several verifications", col, log, req)
  missing = [o for o in ar.OUTCOMES if o not in rows and o != "ordinary_result"]
  need(not missing, "outcomes the check does not reach: %s" % missing)
  print("  outcomes: %d typed outcomes through english_to_answer (formal records, the fake bundle, fake GK builds); "
        "`Cannot answer:` exactly for an unsupported outcome and `Error:` for another non-answer; answered_by and "
        "run_outcome follow; ordinary_result is the ordinary "
        "route's (x07, in the WP15 manifest)" % len(rows))
  print("  counters: in every call, logical model calls equal the translation's requests, provider attempts equal "
        "the fake provider's requests, refused calls are counted, and GK launches by role add up to the total and "
        "to the collector's gk_calls")


def check_llmcall_failures():
  """A provider function that raises is one logical call with one failed attempt in the call log, so the log
  agrees with llmcall's counters (a WP15 repair in the shared accounting; the ordinary route benefits alike)."""
  with cap.World() as w:
    for exc, source, reason in ((RuntimeError("a provider fault"), "api", "provider_exception"),
                                (llmcall.MissingApiKeyError("no key"), "error", "missing_api_key")):
      llmcall.reset_call_log()
      llmcall.reset_call_limit()
      w.script = {"a1": [exc]}
      out = llmcall.call_llm(cap.FAKE1, "text", llm="gemini")
      log = list(llmcall.call_log)
      counts = llmcall.call_counts()
      need(out is None and len(log) == 1 and log[0]["source"] == source and log[0]["reason"] == reason
           and log[0]["logical"] and log[0]["failed"] and counts["live"] == 1 and counts["allowed"] == counts["live"]
           + counts["cached"], "a raising provider (%s): %r %r" % (reason, log, counts))
  print("  llmcall: a provider that raises is one logical call with one failed entry (provider_exception; a missing "
        "key is missing_api_key with no request); the log agrees with the counters")


def run():
  try:
    check_examples()
    check_outcomes()
    check_llmcall_failures()
  finally:
    while caa.FAKES:
      ag.BACKENDS.pop(caa.FAKES.pop(), None)
    while cag.FAKES:
      ag.BACKENDS.pop(cag.FAKES.pop(), None)


if __name__ == "__main__":
  run()
