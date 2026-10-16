"""WP14 checks: the opt-in action route in the pipeline (`solver/action_pipeline.py`, `solve.py`, `runtests.py`).

No model call and no GK launch.  The ordinary route runs with a fake provider (it answers the ordinary Stage-1 and
Stage-2 prompts with the stored parse of the WP01 elephant case) and a fake prover (the stored GK result).  The
action route runs with a fake prompt bundle, the same fake provider (it answers the fake bundle's prompts from a
script) and a fake registered GK build.  They measure plumbing, never prompt fidelity.

  options      solve.py's parser and runtests.py's forwarding give the action keys; an explicit ordinary stage, a
               preset or a representation option with -actions is an error; an action option with -noactions
               is an error; an ordinary call with no action key keeps its own options object
  bundles      the ordinary assembled prompts keep their WP01 hashes; a bundle never touches llmparse's globals; the
               default bundle is the action prompts; without a bundle the English route is not_implemented
  isolation    ordinary, then action (success, validation failure, timeout, exception, call limit), then
               ordinary again in one process: the same ordinary requests, prompts, prover input, answer, options
               and llmparse state
  translation  at most two corrections per stage and six logical calls; a failed correction ends the
               translation and keeps every raw response; unsupported meaning is not corrected; logical calls and
               provider attempts are counted apart
  entries      solve.main, runtests' option path and case record, and the library call
  review       Sol's review: several queries with a failed one are an error; a formal run needs no provider key
"""

import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "solver"))
sys.path.insert(0, ROOT)
import action_gk as ag
import action_pipeline as ap
import check_action_answer as caa
import check_action_availability as cav
import fixture_materialize as fm
import globals as G
import llmcall
import llmparse
import prover
import solve
import solve_cli
import solve_stages

need = cav.need
# the WP01 baseline (MEMO_2026_09_10_wp01_baseline_opus5.md): the assembled ordinary prompts
ORDINARY_SHA256 = {"stage1": "0b52e526b170a602dea2b5195bc0936c242b437dfa5a8071eab0d6291fddf0ff",
                   "stage2": "e0ad4d350f16add184e4a0a8b3a67170c22524ec5829f0dd1bd865f7374488ca"}
ELEPHANT = "Elephants are animals. Elephants are animals?"
E_S1 = [{"raw": "Elephants are animals.", "units": [{"unit_id": "S1", "text": "Elephants are animals.", "type": "strict_rule",
         "entities": [{"id": "elephants", "type": "generic", "category": "animal"},
                      {"id": "animals", "type": "generic", "category": "animal"}]}]},
        {"raw": "Elephants are animals?", "units": [{"unit_id": "S2", "text": "Are all elephants animals?", "type": "query",
         "entities": [{"id": "elephants", "type": "generic", "category": "animal"},
                      {"id": "animals", "type": "generic", "category": "animal"}]}]}]
E_RULE = ["forall", "X", ["implies", ["isa", "elephant", "X"], ["isa", "animal", "X"]]]
E_S2 = ["and", ["@id", "S1", ["holds", "W0", E_RULE]], ["@id", "S2", ["question", E_RULE]]]
E_PROOF = {"result": "answer found", "answers": [{"answer": True, "confidence": 1, "positive proof": [
  [1, ["in", "sent_S1", "assumption", 1], [["-isa", "elephant", "?:X"], ["isa", "animal", "?:X"]]],
  [2, ["in", "sent_S2", "assumption", 1], [["isa", "elephant", "sk0_elephant"], ["$defq0"]]],
  [3, ["in", "sent_S2", "goal", 1], [["-$defq0"]]], [4, ["mp", 1, 2, 3, "fromga", 1], [["isa", "animal", "sk0_elephant"]]],
  [5, ["in", "sent_S2", "assumption", 1], [["-isa", "animal", "sk0_elephant"], ["$defq0"]]],
  [6, ["mp", 4, 5, 3, "fromga", 1], False]]}]}
FAKE1, FAKE2 = "FAKE ACTION STAGE-1 PROMPT (plumbing test)", "FAKE ACTION STAGE-2 PROMPT (plumbing test)"
TRAVEL = {c["case"]: c for c in fm.load_all()}["p01_travel:base"]


def travel_stage1():
  q = TRAVEL["queries"][0]
  units = [dict({"unit_id": u["id"], "text": u["text"]}, **u["stage1"]) for u in TRAVEL["units"]]
  units.append({"unit_id": "Q1", "text": q["text"], "type": "query", "action_reading": "plan_question",
                "entities": [{"id": "Ann 1", "type": "concrete", "category": "person"},
                             {"id": "Helsinki 4", "type": "concrete", "category": "place"}]})
  return [{"raw": TRAVEL["text"] + " " + q["text"], "units": units}]


def travel_stage2():
  return ["and"] + [u["stage2"] for u in TRAVEL["units"]] + [TRAVEL["queries"][0]["stage2"]]


TRAVEL_TEXT = TRAVEL["text"] + " " + TRAVEL["queries"][0]["text"]
PLAN = caa.do(["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"], ["move", "Ann 1", "Tallinn 3", "Helsinki 4", "ship"])


class World(object):
  """The fake provider and the fake prover, with what they received."""

  def __init__(self):
    self.script = {"a1": [], "a2": []}
    self.requests, self.prover_inputs, self.saved = [], [], {}

  def provider(self, version, text, sysprompt, max_tokens, think=False, deadline=None):
    who = ("o1" if sysprompt == llmparse._stage1_sysprompt else "o2" if sysprompt == llmparse._stage2_sysprompt
           else "a1" if sysprompt == FAKE1 else "a2" if sysprompt == FAKE2 else "?")
    self.requests.append((who, hashlib.sha256(sysprompt.encode()).hexdigest(), hashlib.sha256(text.encode()).hexdigest()))
    if who == "o1":
      return json.dumps(E_S1)
    if who == "o2":
      return json.dumps(E_S2)
    step = self.script[who].pop(0) if self.script.get(who) else ""
    if isinstance(step, Exception):
      raise step
    return step if isinstance(step, str) else json.dumps(step)

  def call_prover(self, logic, s1_json=None):
    self.prover_inputs.append(hashlib.sha256(json.dumps(logic, sort_keys=True, default=str).encode()).hexdigest())
    return json.dumps(E_PROOF)

  def __enter__(self):
    for n in ("call_claude", "call_gemini", "call_deepseek", "call_gpt"):
      self.saved[n] = getattr(llmcall, n)
      setattr(llmcall, n, self.provider)
    for n in ("_get_llm_cached", "_store_llm_cached", "sleepseconds"):
      self.saved[n] = getattr(llmcall, n)
    llmcall._get_llm_cached = lambda *a, **k: None
    llmcall._store_llm_cached = lambda *a, **k: None
    llmcall.sleepseconds = 0
    self.saved["call_prover"] = prover.call_prover
    prover.call_prover = self.call_prover
    self.saved["llm"] = solve.llm
    solve.llm = "gemini"
    self.saved["bundle"] = ap.DEFAULT_BUNDLE
    ap.BUNDLES["fake-plumbing"] = {"status": "fake, for plumbing tests", "text": {"stage1": FAKE1, "stage2": FAKE2}}
    ap.DEFAULT_BUNDLE = "fake-plumbing"
    return self

  def __exit__(self, *e):
    for n in ("call_claude", "call_gemini", "call_deepseek", "call_gpt", "_get_llm_cached", "_store_llm_cached",
              "sleepseconds"):
      setattr(llmcall, n, self.saved[n])
    prover.call_prover = self.saved["call_prover"]
    solve.llm = self.saved["llm"]
    ap.DEFAULT_BUNDLE = self.saved["bundle"]
    ap.BUNDLES.pop("fake-plumbing", None)
    return False


def llmparse_state():
  return {k: v for k, v in vars(llmparse).items()
          if not k.startswith("__") and isinstance(v, (str, bool, int, float, type(None)))}


def quiet(fn, *a, **k):
  with contextlib.redirect_stdout(io.StringIO()):
    return fn(*a, **k)


def ordinary(world, tag):
  llmcall.reset_call_log()          # once per case, as the runners do (solve_stages.call_counts counts the whole log)
  n0, p0 = len(world.requests), len(world.prover_inputs)
  collect = {}
  ans = quiet(solve.english_to_answer, ELEPHANT, {}, collect)
  return {"answer": ans, "requests": world.requests[n0:], "prover": world.prover_inputs[p0:],
          "options": {k: v for k, v in G.options.items() if k != "_collect"}, "llmparse": llmparse_state(),
          "collect": {k: collect.get(k) for k in ("answered_by", "pipeline_name", "stages_enabled", "run_outcome",
                                                  "llm_calls_total")}}


def action(world, a1, a2, options=None, text=TRAVEL_TEXT, collect=None):
  world.script = {"a1": list(a1), "a2": list(a2)}
  # the single discovery launch: the fake build answers every launch alike; check_action_plan covers the plan search
  opts = dict({"actions_flag": True, "action_backend": world.backend, "noplan_builder_flag": True}, **(options or {}))
  collect = {} if collect is None else collect
  ans = quiet(solve.english_to_answer, text, opts, collect)
  return ans, collect


# ---------------------------------------------------------------------------


def check_options():
  def parse(*args):
    saved = sys.argv
    sys.argv = ["solve.py"] + list(args)
    try:
      with contextlib.redirect_stdout(io.StringIO()):
        return solve_cli.parse_cmd_line()
    finally:
      sys.argv = saved
  text, o = parse("-actions", "-plan-depth", "3", "-action-backend", "gk", "Ann", "walks.")
  need(o["actions_flag"] and o["plan_depth"] == 3 and o["action_backend"] == "gk" and text == "Ann walks.",
       "solve.py -actions: %r" % o)
  need(parse("--actions", "--formal", "x")[1].get("formal_flag"), "--formal")
  for bad in (("-plan-depth", "x", "t"), ("-plan-depth",), ("-action-backend",)):
    try:
      parse(*bad)
      need(False, "%s accepted" % (bad,))
    except SystemExit as e:
      need(e.code == 2, "%s exits 2" % (bad,))
  import runtests
  args, extra = runtests.parse_args(["tests/tests_core.py", "-actions", "-plan-depth", "2"])
  ro = runtests.build_run_options(args, extra)
  need(ro.get("actions_flag") is True and ro.get("plan_depth") == 2, "runtests forwards the action keys: %r" % ro)
  need(ap.resolve(ro)["limits"] == {"search_cap": 2, "explicit": True}, "runtests' default keys are accepted")
  rows = [({"critic_flag": True}, "critic"), (parse("-actions", "-pipeline", "conservative", "x")[1], "fallback"),
          ({"graphtrans_flag": True}, "graphtrans"), ({"nocontext_flag": True}, "-nocontext"),
          ({"prover_axiomfiles": ["a.js"]}, "-axioms"), ({"plan_depth": -1}, "non-negative"),
          ({"action_backend": "no_such_build"}, "registered")]
  for extra_opts, word in rows:
    try:
      ap.resolve(dict({"actions_flag": True}, **extra_opts))
      need(False, "%r accepted with -actions" % extra_opts)
    except ap.OptionError as e:
      need(word in str(e), "%r: %s" % (extra_opts, e))
  ok = ap.resolve(parse("-actions", "-nocritic", "-nographtrans", "-seconds", "40", "-llm-call-limit", "5", "x")[1])
  need(ok["seconds"] == 40 and ok["disabled_stages"] == ["fallback_norm", "fallback_hyp", "critic", "graphtrans",
                                                         "litbridge", "graphbridge"], "cancels and shared keys: %r" % ok)
  plain = {"llm_call_limit": 3}
  need(solve.route_choice(ELEPHANT, plain)["options"] is plain and solve.route_choice(ELEPHANT, None)["options"] is None,
       "an ordinary call keeps its own options object")
  need(solve.route_choice(ELEPHANT, {"actions_flag": False, "x": 1})["options"] == {"x": 1},
       "actions_flag False is dropped")
  need(solve.route_choice(ELEPHANT, {"noactions_flag": True, "plan_depth": 2}) ==
       {"error": "Error: -plan-depth cannot be combined with -noactions"}, "an action key with -noactions")
  print("  options: solve.py and runtests.py give the action keys; stages, presets, representation options, a bad "
        "depth and an unknown build are refused with -actions; cancels and shared keys pass; an action key with "
        "-noactions is an error; an ordinary call keeps its options object")


def check_bundles():
  llmparse.load_prompts()
  got = {st: hashlib.sha256(getattr(llmparse, "_%s_sysprompt" % st).encode()).hexdigest() for st in ("stage1", "stage2")}
  need(got == ORDINARY_SHA256, "the ordinary assembled prompts keep their WP01 hashes: %r" % got)
  before = llmparse_state()
  need(ap.load_bundle("no-such-bundle") is None, "an unknown bundle loads as None")
  ap.BUNDLES["text-test"] = {"status": "test", "text": {"stage1": "one", "stage2": "two"}}
  try:
    b = ap.load_bundle("text-test")
  finally:
    ap.BUNDLES.pop("text-test")
  need(b["stage1"] == "one" and b["sha256"]["stage2"] == hashlib.sha256(b"two").hexdigest(), "a fake bundle: %r" % b)
  need(llmparse_state() == before, "loading a bundle leaves llmparse's globals as they were")
  need(ap.DEFAULT_BUNDLE == "actions" and ap.load_bundle()["name"] == "actions", "the default bundle is the action prompts")
  real_default = ap.DEFAULT_BUNDLE
  ap.DEFAULT_BUNDLE = "no-such-bundle"
  try:
    r = quiet(solve.english_to_answer, "Ann walks. Where is Ann?", {"actions_flag": True})
  finally:
    ap.DEFAULT_BUNDLE = real_default
  need(r.startswith("Error: not_implemented: the action prompt bundle"), "no bundle: %r" % r)
  print("  bundles: the ordinary assembled prompts keep their WP01 hashes; a fake bundle keeps its own record; "
        "llmparse's globals are untouched; the default bundle is the action prompts, and without a bundle English "
        "input is not_implemented")


def check_isolation():
  with World() as w:
    w.backend = caa.fake({"plan:positive": caa.answers(([PLAN], 1.0))})
    first = ordinary(w, "first")
    need(first["answer"].startswith("True.") and [r[0] for r in first["requests"]] == ["o1", "o2"]
         and first["requests"][0][1] == ORDINARY_SHA256["stage1"] and first["requests"][1][1] == ORDINARY_SHA256["stage2"],
         "the ordinary run: %r" % ((first["answer"][:30], first["requests"]),))
    runs = []
    # success: a plan through the fake bundle, the compiler, the replay and the fake GK build
    ans, col = action(w, [travel_stage1()], [travel_stage2()])
    need(ans == "Plan: Ann goes from Haapsalu to Tallinn by bus, then from Tallinn to Helsinki by ship.",
         "action success: %r" % ans)
    rec = col["action_route"]
    need(rec["result"]["outcome"] == "plan_found" and rec["calls"]["logical"] == 2 and rec["calls"]["gk"] == 1
         and col["stages_enabled"] == {k: False for k in ("fallback_norm", "fallback_hyp", "critic", "graphtrans",
                                                          "litbridge", "graphbridge")}
         and rec["translation"]["bundle"]["name"] == "fake-plumbing", "the success record: %r" % rec["calls"])
    runs.append(("success", ans))
    # a validation failure: Stage 2 names a unit Stage 1 does not have, twice with the same errors; the second
    # correction would repeat the first request, so it is recorded and not sent
    bad2 = ["and"] + [u["stage2"] for u in TRAVEL["units"]] + [["@id", "Q9", TRAVEL["queries"][0]["stage2"][2]]]
    ans, col = action(w, [travel_stage1()], [bad2, bad2, bad2])
    tr = col["action_route"]["translation"]
    need(ans.startswith("Error: translation_invalid") and [h["stage"] for h in tr["history"]] == [1, 2, 2, 2]
         and all(h["raw"] for h in tr["history"][:3]) and all(h["errors"] for h in tr["history"][1:3])
         and tr["history"][3].get("skipped") == "repeated_request" and tr.get("stop_reason") == "repeated_request"
         and col["action_route"]["calls"]["logical"] == 3 and col["action_route"]["result"]["plan"] is None,
         "a validation failure: %r" % ((ans[:80], [h["stage"] for h in tr["history"]]),))
    runs.append(("validation failure", ans))
    # a timeout: the provider's deadline expires
    ans, col = action(w, [llmcall.LlmDeadlineExceeded("provider wait")], [])
    need(ans.startswith("Error: model_timeout") and col["action_route"]["result"]["outcome"] == "model_timeout",
         "a timeout: %r" % ans)
    runs.append(("timeout", ans))
    # an exception inside the route
    real = ap.compile_translation
    ap.compile_translation = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("a compiler fault"))
    try:
      ans, col = action(w, [travel_stage1()], [travel_stage2()])
    finally:
      ap.compile_translation = real
    need(ans.startswith("Error: the action route failed: RuntimeError") and col["action_route"]["error"]["kind"]
         == "RuntimeError" and col["answered_by"] is None, "an exception: %r" % ans)
    runs.append(("exception", ans))
    # the shared call limit, set for this call only
    limit_before = G.options.get("llm_call_limit")
    ans, col = action(w, [travel_stage1()], [travel_stage2()], {"llm_call_limit": 1})
    need(ans.startswith("Error: call_limit") and G.options.get("llm_call_limit") == limit_before,
         "the call limit applies to the action call and is restored: %r" % ans)
    runs.append(("call limit", ans))
    second = ordinary(w, "second")
    for k in ("answer", "prover", "options", "llmparse", "collect"):
      need(first[k] == second[k], "ordinary before and after the action calls differ in %s:\n%r\n%r"
           % (k, first[k], second[k]))
    need([r[1:] for r in first["requests"]] == [r[1:] for r in second["requests"]],
         "the ordinary requests (prompt and input hashes) differ after the action calls")
  print("  isolation: ordinary, then the action route (%s), then ordinary again: the same ordinary prompts and "
        "inputs (WP01 hashes), prover input, answer, options, collect keys and llmparse state"
        % ", ".join(k for k, _ in runs))


def check_translation():
  with World() as w:
    w.backend = caa.fake({"plan:positive": caa.answers(([PLAN], 1.0))})
    # Stage 1 fails three times: two corrections, then translation_invalid; no Stage-2 call
    ans, col = action(w, ["not json", [{"units": []}], "[]"], [])
    tr = col["action_route"]["translation"]
    need(ans.startswith("Error: translation_invalid") and [h["stage"] for h in tr["history"]] == [1, 1, 1]
         and "CORRECTION" not in tr["history"][0]["raw"], "Stage 1 fails: %r" % [h["errors"] for h in tr["history"]])
    corrected = [r for r in w.requests if r[0] == "a1"][-3:]
    need(len({r[2] for r in corrected}) == 3, "each correction is a new request")
    # the first Stage-2 answer is invalid, the corrected one is used
    bad2 = ["and"] + [u["stage2"] for u in TRAVEL["units"]]
    ans, col = action(w, [travel_stage1()], [bad2, travel_stage2()])
    tr = col["action_route"]["translation"]
    need(ans.startswith("Plan: ") and [h["stage"] for h in tr["history"]] == [1, 2, 2]
         and "no Stage-2 package for the Stage-1 units Q1" in tr["history"][1]["errors"][0], "a corrected Stage 2: %r" % ans)
    # the compiler's own error is a correction: a query with can
    canq = ["@id", "Q1", ["question", ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"]]]]
    s2 = ["and"] + [u["stage2"] for u in TRAVEL["units"]] + [canq]
    ans, col = action(w, [travel_stage1()], [s2, s2, s2])
    need(ans.startswith("Error: translation_invalid") and "can_in_query" in col["action_route"]["translation"]["history"][1]
         ["errors"][0], "a compiler error is corrected, then reported: %r" % col["action_route"]["translation"]["errors"])
    # unsupported meaning is reported, not corrected
    uns = ["and", ["@id", "S1", ["holds", "W0", ["and", ["isa", "person", "Ann 1"],
                                                 ["is rel2", "located_at", "Ann 1", "Haapsalu 2"]]]],
           ["@id", "S2", ["holds", "W0", ["forall", "X", ["implies", ["is rel2", "located_at", "X", "Haapsalu 2"],
                                                               ["isa", "person", "X"]]]]],
           TRAVEL["units"][2]["stage2"], TRAVEL["queries"][0]["stage2"]]
    ans, col = action(w, [travel_stage1()], [uns])
    need(ans.startswith("Cannot answer: ") and "[mixed_scope_rule" in ans
         and len(col["action_route"]["translation"]["history"]) == 2,
         "unsupported meaning: %r" % ans)
    # an empty response then a valid one: two provider attempts, one logical call
    ans, col = action(w, ["", travel_stage1()], [travel_stage2()])
    c = col["action_route"]["calls"]
    need(ans.startswith("Plan: ") and c["logical"] == 2 and c["provider_attempts"] == 3, "attempts vs logical: %r" % c)
    # at most six logical calls: Stage 1 corrected twice and Stage 2 corrected twice, each correction a new request
    bad2b = bad2[:-1] + [["@id", "Q8", TRAVEL["queries"][0]["stage2"][2]]]
    ans, col = action(w, ["x", "y", travel_stage1()], [bad2, bad2b, travel_stage2()])
    need(ans.startswith("Plan: ") and col["action_route"]["calls"]["logical"] == 6, "six calls: %r" % ans)
    # a correction that would repeat the previous request is recorded and not sent
    ans, col = action(w, ["x", "x", travel_stage1()], [travel_stage2()])
    tr = col["action_route"]["translation"]
    need(ans.startswith("Error: translation_invalid") and col["action_route"]["calls"]["logical"] == 2
         and tr["history"][-1].get("skipped") == "repeated_request", "a repeated request: %r" % ans)
    ap.MAX_LOGICAL_CALLS, saved = 3, ap.MAX_LOGICAL_CALLS
    try:
      ans, col = action(w, ["x", travel_stage1()], [bad2, travel_stage2()])
    finally:
      ap.MAX_LOGICAL_CALLS = saved
    need(ans.startswith("Error: call_limit") and col["action_route"]["calls"]["logical"] == 3, "the cap: %r" % ans)
  print("  translation: two corrections per stage, then translation_invalid with every raw response; a correction "
        "that would repeat the previous request is recorded and not sent; a corrected "
        "response replaces an invalid one; compiler errors are corrected, unsupported meaning is not; provider "
        "attempts and logical calls are counted apart; the logical-call cap stops the translation")


def check_entries():
  with World() as w:
    w.backend = caa.fake({"plan:positive": caa.answers(([PLAN], 1.0))})
    record = {"text": TRAVEL["text"], "entities": TRAVEL["entities"],
              "units": [{"id": u["id"], "text": u["text"], "stage1": u["stage1"], "stage2": u["stage2"]} for u in TRAVEL["units"]],
              "queries": [{"stage2": TRAVEL["queries"][0]["stage2"]}]}
    saved = sys.argv
    sys.argv = ["solve.py", "-actions", "-formal", "-action-backend", w.backend, json.dumps(record)]
    out = io.StringIO()
    try:
      with contextlib.redirect_stdout(out):
        code = solve.main()
    finally:
      sys.argv = saved
    need(code == 0 and out.getvalue().strip().endswith("by ship.") and not w.requests, "solve.main -formal: %r" % out.getvalue())
    import runtests
    args, extra = runtests.parse_args(["tests/tests_core.py", "-actions", "-action-backend", w.backend])
    ro = runtests.build_run_options(args, extra)
    ans, col = action(w, [travel_stage1()], [travel_stage2()], {k: v for k, v in ro.items() if k != "actions_flag"})
    case = runtests.build_case_json("t", 1, TRAVEL_TEXT, "plan", "gemini", col, lambda *a, **k: False)
    need(case.get("action_route", {}).get("result", {}).get("outcome") == "plan_found" and case["answer"] == ans,
         "the runtests case record keeps the action record")
    lib = quiet(solve.english_to_answer, json.dumps(record), {"actions_flag": True, "formal_flag": True,
                                                              "action_backend": w.backend})
    need(lib.startswith("Plan: "), "the library call: %r" % lib)
    bad = quiet(solve.english_to_answer, "{not json", {"actions_flag": True, "formal_flag": True})
    need(bad.startswith("Error: incompatible options: -formal needs a JSON record"), "bad formal input: %r" % bad)
    tmp = os.path.join(tempfile.mkdtemp(), "a_long_directory_name_for_the_formal_record_file", "record.json")
    os.makedirs(os.path.dirname(tmp))
    with open(tmp, "w") as f:
      json.dump(record, f)
    by_path = quiet(solve.english_to_answer, tmp, {"actions_flag": True, "formal_flag": True, "action_backend": w.backend})
    need(len(tmp) > 50 and by_path == lib, "a long record path: %r" % by_path)
  print("  entries: solve.main with -formal (no model call), runtests' options and case record, and the library call "
        "reach the route; a bad formal record is an error")


def check_review_repairs():
  """Sol's review of WP14: (1) several queries: the call answers only when every query answers, decided from the
  result records; (2) a formal run calls no model and needs no provider key."""
  import action_route as ar
  record = {"entities": TRAVEL["entities"],
            "units": [{"id": u["id"], "text": u["text"], "stage2": u["stage2"]} for u in TRAVEL["units"]],
            "queries": [{"stage2": ["@id", "Q1", TRAVEL["queries"][0]["stage2"][2]]},
                        {"stage2": ["@id", "Q2", TRAVEL["queries"][0]["stage2"][2]]}]}
  ok = ar.result("verification_result", answer="Yes")
  bad = ar.result("translation_invalid", diagnostics=["bad query"])

  def main_with(argv):
    saved, out = sys.argv, io.StringIO()
    sys.argv = ["solve.py"] + argv
    try:
      with contextlib.redirect_stdout(out):
        return solve.main(), out.getvalue().strip()
    finally:
      sys.argv = saved

  real = ap.solve_one_query
  try:
    for script, fails in (([ok, ok], []), ([ok, bad], ["Q2"]), ([bad, ok], ["Q1"]), ([bad, bad], ["Q1", "Q2"])):
      it = iter(script)
      ap.solve_one_query = lambda *a, **k: next(it)
      collect = {}
      ans = quiet(solve.english_to_answer, json.dumps(record), {"actions_flag": True, "formal_flag": True}, collect)
      rec = collect["action_route"]["result"]
      need(rec["outcome"] == "several" and rec["failed"] == fails
           and ans.startswith("Error:") == bool(fails) and (collect["answered_by"] == "actions") == (not fails)
           and collect["run_outcome"] == ("error" if fails else "several")
           and all(("Q%d: " % n) in ans for n in (1, 2)), "several queries %s: %r / %r" % (fails, ans, collect["answered_by"]))
      it = iter(script)
      code, text = main_with(["-actions", "-formal", json.dumps(record)])
      need(code == (1 if fails else 0), "solve.main exit %s for failed %s" % (code, fails))
  finally:
    ap.solve_one_query = real
  # a formal run needs no provider key; the ordinary and the English action preflights still do
  import runtests
  real_key = llmcall.provider_key_file
  llmcall.provider_key_file = lambda provider: os.path.join(tempfile.mkdtemp(), "no_key_here.txt")
  try:
    with World() as w:
      w.backend = caa.fake({"plan:positive": caa.answers(([PLAN], 1.0))})
      one = dict(record, queries=record["queries"][:1])
      code, text = main_with(["-actions", "-formal", "-action-backend", w.backend, json.dumps(one)])
      need(code == 0 and text.startswith("Plan: ") and not w.requests, "a formal run without a key: %s %r" % (code, text))
      code, text = main_with(["Elephants are animals. Is Dumbo an animal?"])
      need(code == 2 and text.startswith("Error:"), "the ordinary preflight still needs the key: %s %r" % (code, text))
      code, text = main_with(["-actions", "Ann walks. Where is Ann?"])
      need(code == 2 and text.startswith("Error:"), "the English action preflight still needs the key: %s %r" % (code, text))
      need(runtests.validate_run_providers(["gemini"], None, require_key=False) == {"gemini": llmcall.geminiversion},
           "runtests' preflight without a key for a formal run")
      try:
        runtests.validate_run_providers(["gemini"], None)
        need(False, "runtests' ordinary preflight passed without a key")
      except runtests.RunConfigurationError:
        pass
  finally:
    llmcall.provider_key_file = real_key
  print("  review repairs: with several queries the call answers only when every query does (success/error, "
        "error/success, error/error, success/success), in the text, answered_by, run_outcome and solve.main's exit "
        "status; a formal run needs no provider key and calls no model, while the ordinary and English-action "
        "preflights still need one, in solve.py and runtests.py")


def run():
  try:
    check_options()
    check_bundles()
    check_isolation()
    check_translation()
    check_entries()
    check_review_repairs()
  finally:
    while caa.FAKES:
      ag.BACKENDS.pop(caa.FAKES.pop(), None)


if __name__ == "__main__":
  run()
