"""Checkpoint I checks: the planning-summary option through the adapter, the answer policy and the option routing.

No model and no GK: a fake executable prints saved outputs of the summary build (`summary/saved/`, from the
development binary's final batch) or changed copies of them.

  routing      -planning-summary is an action key: kept on the action route and for a formal input, dropped on an
               automatic ordinary call, an error with -noactions; it selects the summary build, and a named build
               without the module is refused before any launch
  launch       a discovery question gets its profile as a sidecar in the launch's private directory; the command
               names it; the saved profile bytes have the recorded SHA-256; another kind of question has none
  answer       with the summary the outcome, plan, confidence and proof equal the run without it; the annotation
               has the list and score of the reference interpreter; World and Progress are no witnesses
  binding      a profile of another query, another obligation, a stale input, and a staged file that changed
               after writing give planning_profile_error before any launch
  output       a changed score or list is a summary_mismatch: the annotation is disabled, the answer stays; a
               payload of another form disables the annotation; a missing or foreign metadata entry and an arity
               that does not fit are planning_profile_error, never a guessed answer; so is the build's own error
  layout       a malformed layout (core_arity 0 or not an integer, a short answer, slot indexes that are no
               integers, an unknown reason) is summary_output_error on accepted and rejected entries, never an
               exception; a malformed payload (lossy, progress, facts, order, reasons, template) disables the
               annotation and keeps the answer
  export       the replay comparison needs an exported state for every validated prefix: a missing, empty,
               truncated or malformed export disables the annotation; a root the replay did not validate too; a
               fact of the reference list missing from the replay is summary_mismatch; the answer stays
  capability   the summary build counts only with a validation record for its binary, library, strategy and
               summary contract; any other build is refused before a launch
  preflight    on the action route, a build that cannot run summaries is refused before any model call
  phases       a staged file missing or changed before the launch: no process; before the diagnostic relaunch: the
               completed launch is kept and counted; both checks run inside the serial lock; the recording holds
               the exact profile; the taxonomy files are fingerprinted
  unavailable  a query that the compiler cannot summarize runs unchanged, with the reason recorded
  isolation    two queries of one run get two profiles, each launch its own
  runner       runtests -actions -formal with fake builds, with and without the option: case records, manifest,
               launch counts, no model call
"""

import copy
import json
import os
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_answer as aa
import action_gk as ag
import action_pipeline as ap
import action_route as ar
import action_summary as asum
import check_action_summary as cs
import lc_action_summary as ls
import solve

need = cs.need
SAVED = os.path.join(HERE, "summary", "saved")
FAKES = []


def saved(name):
  with open(os.path.join(SAVED, name)) as f:
    return json.load(f)


def fake(tmp, response, summary=True, exit_code=0, validated=True):
  """A fake build that prints `response` (an object, or a function of the profile it was given) and logs its
  arguments.  The profile identifier of a saved output is replaced by that of the profile the launch passes."""
  n = len(FAKES)
  path, log, resp = [os.path.join(tmp, "fake_%d.%s" % (n, x)) for x in ("py", "log", "json")]
  with open(resp, "w") as f:
    json.dump(response, f)
  with open(path, "w") as f:
    f.write("#!%s\nimport json, sys\nargs = sys.argv[1:]\n" % sys.executable)
    f.write("open(%r, 'a').write(json.dumps(args) + '\\n')\n" % log)
    f.write("text = open(%r).read()\n" % resp)
    f.write("if '-planning-profile' in args:\n  pid = json.load(open(args[args.index('-planning-profile') + 1]))['profile_id']\n"
            "  text = text.replace('sha256:ECHO', pid)\n")
    f.write("sys.stdout.write(json.dumps(json.loads(text)))\nsys.exit(%d)\n" % exit_code)
  os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
  p = ag.backend_profile()
  name = "fake_summary_%d" % n
  p.update(name=name, path=path, sha256=ag.sha256_file(path), datafolder=tmp, summary=summary)
  if summary and validated:
    # the record of the summary build, for this fake binary
    p["validated"] = [dict(copy.deepcopy(ag.BACKENDS[ag.SUMMARY_BACKEND]["validated"][0]), binary_sha256=p["sha256"])]
  ag.BACKENDS[name] = p
  FAKES.append(name)
  return name, log


def calls(log):
  if not os.path.exists(log):
    return []
  with open(log) as f:
    return [json.loads(x) for x in f]


def echo(out):
  """A saved output with its profile identifier replaced by the marker the fake fills in."""
  out = copy.deepcopy(out)
  for k in ("answers", "rejected_answers"):
    for e in out.get(k) or []:
      if "planning_summary" in e:
        e["planning_summary"]["profile_id"] = "sha256:ECHO"
  return out


def unstack():
  fx, src, q, r = [x for x in cs.load_formal() if x[0]["id"] == "unstack"][0]
  return src, q


def check_routing():
  opts = {"formal_flag": True, "planning_summary_flag": True}
  c = solve.route_choice("{}", opts)
  need(c["route"] == "actions" and c["options"].get("planning_summary_flag") is True, "a formal input keeps the option: %r" % (c,))
  c = solve.route_choice("Ann is in Lund. A bus goes from Lund to Malmo. How can Ann get to Malmo?", {"planning_summary_flag": True})
  need(c["route"] == "actions" and c["options"].get("planning_summary_flag") is True, "an automatic action call keeps it: %r" % (c.get("verdict"),))
  c = solve.route_choice("Elephants are animals. John is an elephant. Is John an animal?", {"planning_summary_flag": True})
  need(c["route"] == "ordinary" and "planning_summary_flag" not in (c["options"] or {}), "an automatic ordinary call drops it")
  c = solve.route_choice("x", {"noactions_flag": True, "planning_summary_flag": True})
  need("error" in c and "-planning-summary" in c["error"], "with -noactions it is an error: %r" % (c,))
  need("planning_summary_flag" in ap.ACTION_KEYS and "planning_summary_flag" in solve._ACTION_KEYS, "the option is an action key in both lists")
  prof = ap.resolve({"actions_flag": True, "planning_summary_flag": True})
  need(prof["summary"] is True and prof["backend"] == ag.SUMMARY_BACKEND, "the option selects the summary build")
  prof = ap.resolve({"actions_flag": True})
  need(prof["summary"] is False and prof["backend"] == ag.DEFAULT_BACKEND == "gk", "without the option the default build is unchanged")
  try:
    ap.resolve({"actions_flag": True, "planning_summary_flag": True, "action_backend": "gk"})
    need(False, "a named build without the module is refused")
  except ap.OptionError as e:
    need("planning-summary" in str(e), "the refusal names the option")
  src, q = unstack()
  ev = ag.run_query(src, q, "gk", {"seconds": 5, "summary": True})
  need(ev["outcome"]["outcome"] == "unsupported_backend_requirement" and ev["outcome"]["reason"] == "planning_summary_unsupported"
       and ev["calls"]["gk"] == 0, "the adapter refuses a summary request on a build without the module, with no launch")
  need(ag.BACKENDS["gk"].get("summary") is None and ag.BACKENDS[ag.SUMMARY_BACKEND]["strategy"] == ag.BACKENDS["gk"]["strategy"]
       and ag.BACKENDS[ag.SUMMARY_BACKEND]["role_strategy"] == ag.BACKENDS["gk"]["role_strategy"]
       and ag.profile_strategy_sha256(ag.BACKENDS[ag.SUMMARY_BACKEND]) == ag.profile_strategy_sha256(ag.BACKENDS["gk"]),
       "the summary build has the same strategy and strategy hash; the default build is not changed")
  print("  routing: the option stays on a formal input and an automatic action call, is dropped on an automatic "
        "ordinary call, and is an error with -noactions; it selects the build gk_summary; the named build gk is "
        "refused by the options and by the adapter with 0 launches; the strategy hash is unchanged")


def check_answer(tmp):
  src, q = unstack()
  on, log = fake(tmp, echo(saved("unstack.on.out")))
  off, log_off = fake(tmp, saved("unstack.off.out"), summary=False)
  keep = os.path.join(tmp, "keep")
  with_s = aa.solve(src, q, on, {"seconds": 5, "summary": True, "keep": keep})
  without = aa.solve(src, q, off, {"seconds": 5})
  need(with_s["outcome"] == "plan_found" == without["outcome"], "both runs find the plan: %r %r" % (with_s["outcome"], without["outcome"]))
  for k in ("answer", "plan", "confidence", "confidence_status", "proof", "witnesses", "verdicts", "replay"):
    need(with_s.get(k) == without.get(k), "the field %s is the same with and without the summary" % k)
  need([{k: v for k, v in c.items() if k != "planning_summary"} for c in with_s["candidates"]] == without["candidates"], "the candidates are the same")
  ps = with_s["planning_summary"]
  ref = asum.load(ls.compile_profile(src, q)["profile"]).get_actions([ls._gk(a) for a in with_s["plan"]])
  need(ps["summary_check"] == "ok" and ps["world"] == ref.facts() and ps["progress"] == ref.progress == 0 and ps["calculation"] == "computed"
       and ps["lossy"] is False and ps["gk_disposition"] == "accepted" and ps["replay_verdict"] == "valid" and ps["template"] == "blocks_links"
       and ps["disabled"] is None, "the annotation: %r" % (ps,))
  need("planning_summary" not in without, "a run without the option has no annotation")
  args = calls(log)
  need(len(args) == 1 and args[0].count("-planning-profile") == 1 and "-planning-profile" not in calls(log_off)[0],
       "one launch with one sidecar; the other run has none")
  allowed = {"-strategytext", "-seconds", "-taxonomy", "-confidence", "-keepconfidence", "-datafolder", "-detail", "-outformat", "-planning-profile"}
  need({a for a in args[0] if a.startswith("-") and not a.lstrip("-").replace(".", "").isdigit()} == allowed, "the command has the registered flags and the sidecar only: %r" % args[0])
  prof_path = args[0][args[0].index("-planning-profile") + 1]
  need(os.path.dirname(prof_path) == os.path.dirname(args[0][4]) and not os.path.exists(prof_path), "the sidecar was beside the input in a private directory, removed after the launch")
  kept = [x for x in os.listdir(keep) if x.endswith(".profile.json")]
  need(len(kept) == 1, "the kept sidecar: %r" % os.listdir(keep))
  ev = ag.run_query(src, q, on, {"seconds": 5, "summary": True})
  l = ev["obligations"][0]["positive"]
  need(l["summary"]["profile_sha256"] == ag.sha256_file(os.path.join(keep, kept[0])) and l["summary"]["status"] == "ready"
       and l["command"].count("<profile>") == 1 and l["summary"]["profile"]["binding"]["input_sha256"] == l["input_sha256"],
       "the launch record has the profile's SHA-256 and identifier, and the binding names the input bytes")
  need(all(e["summary"] and e["summary"]["gk_disposition"] == "accepted" for e in l["accepted"]) and all(e["summary"]["gk_disposition"] == "rejected" for e in l["rejected"])
       and all(len(e["answer"][0]) == 2 for e in l["accepted"] + l["rejected"]), "every entry has its annotation and its answer without the two positions")
  # a witness answer: the list and score are not witnesses
  srcw, qw, rw = cs.build(cs.BLOCKS, ["exists", "X", cs.holding(cs.H, "X")])
  wname, wlog = fake(tmp, echo(saved("witness.on.out")))
  resw = aa.solve(srcw, qw, wname, {"seconds": 5, "summary": True})
  psw = resw["planning_summary"]
  need(resw["outcome"] == "plan_found" and list(resw["witnesses"]) == ["X"] and not str(resw["witnesses"]["X"]).startswith("[")
       and psw["summary_check"] == "ok" and psw["calculation"] == "partial" and psw["progress"] is None and psw["progress_reason"] == "witness_goal"
       and psw["world"] is not None, "a witness answer: %r %r" % (resw["witnesses"], psw))
  # another kind of question gets no sidecar
  qq = ar.compile_query(["@id", "Q2", ["question", cs.on(cs.C, cs.A)]], src)
  bname, blog = fake(tmp, {"result": "answer found", "answers": [{"answer": True, "confidence": 1.0}]})
  ag.run_query(src, qq, bname, {"seconds": 5, "summary": True, "termination": False})
  need(calls(blog) and all("-planning-profile" not in a for a in calls(blog)), "a snapshot question runs without a sidecar")
  print("  launch and answer: one launch with one sidecar beside its input; the kept profile has the recorded SHA-256; "
        "outcome, plan, confidence, proof, replay and candidates equal the run without the summary; the annotation "
        "equals the reference record (progress 0, computed, accepted, replay valid); a witness answer keeps its "
        "witness and has a list and no score; a snapshot question gets no sidecar")


def check_binding(tmp):
  src, q = unstack()
  objs = ar.query_input(src, q, "plan", "positive")
  good = ls.compile_profile(src, q)["profile"]
  need(ag.summary_binding_error(good, src, q, "plan", "positive", objs) is None, "the profile of the launch is accepted")
  fx2, src2, q2, r2 = [x for x in cs.load_formal() if x[0]["id"] == "two_leg_travel"][0]
  other = r2["profile"]
  why = ag.summary_binding_error(other, src, q, "plan", "positive", objs)
  need(why.startswith("binding_mismatch") and all(x in why for x in ("source", "query", "view", "input_bytes")), "a swapped profile: %s" % why)
  need("obligation" in ag.summary_binding_error(good, src, q, "plan", "negative", objs), "another polarity")
  # a stale profile: the same query text on a changed source
  src3, q3, r3 = cs.build(cs.BLOCKS + [cs.S("S9", ["isa", "block", "d 9"])], cs.holding(cs.H, cs.A))
  why = ag.summary_binding_error(good, src3, q3, "plan", "positive", ar.query_input(src3, q3, "plan", "positive"))
  need(why.startswith("binding_mismatch") and "input_bytes" in why and "source" in why, "a stale profile: %s" % why)
  bad = copy.deepcopy(good)
  bad["semantic"]["root"] = "W1"
  need(ag.summary_binding_error(bad, src, q, "plan", "positive", objs).startswith("profile_invalid"), "a profile with a changed semantic part")
  renamed = copy.deepcopy(good)
  renamed["binding"]["question"] = "query:Q9:plan:positive"
  need("question" in ag.summary_binding_error(renamed, src, q, "plan", "positive", objs), "another question name")
  # a staged file that changes after writing: no launch
  name, log = fake(tmp, echo(saved("unstack.on.out")))
  for what, tamper in (("profile", lambda inp, prof, phase: open(prof, "a").write(" ")), ("input", lambda inp, prof, phase: open(inp, "a").write("\n"))):
    ag._TAMPER.append(tamper)
    try:
      res = aa.solve(src, q, name, {"seconds": 5, "summary": True})
    finally:
      ag._TAMPER.pop()
    need(res["outcome"] == "planning_profile_error" and res["diagnostics"][0]["reason"] == "staged_%s_changed" % what and not calls(log)
         and res.get("answer") is None and res.get("plan") is None, "a changed staged %s: %r" % (what, res["outcome"]))
  print("  binding: the launch's own profile is accepted; a swapped profile, another polarity, a stale profile, a "
        "changed semantic part and another question name are refused; a staged profile or input that changes "
        "after writing gives planning_profile_error with 0 launches and no answer")


def check_output(tmp):
  src, q = unstack()
  base = echo(saved("unstack.on.out"))
  plain = aa.solve(src, q, fake(tmp, base)[0], {"seconds": 5, "summary": True})

  def run(change, exit_code=0):
    out = copy.deepcopy(base)
    out = change(out) or out
    return aa.solve(src, q, fake(tmp, out, exit_code=exit_code)[0], {"seconds": 5, "summary": True})

  def first(out):
    return out["answers"][0]

  def set_progress(out):
    first(out)["answer"][0][3] = -1

  def set_world(out):
    first(out)["answer"][0][2] = ["$list", ["is rel2", "on", "#:a 2", "#:c 4"], "$nil"]

  for what, change in (("a changed score", set_progress), ("a changed list", set_world)):
    res = run(change)
    ps = res["planning_summary"]
    need(res["outcome"] == "plan_found" and res["plan"] == plain["plan"] and res["confidence"] == plain["confidence"] and res["proof"] == plain["proof"],
         "%s leaves the answer unchanged" % what)
    need(ps["summary_check"] == "summary_mismatch" and ps["disabled"] == "summary_mismatch" and ps["world"] is None and ps["progress"] is None
         and ps["detail"][0]["kind"] == "native_differs_from_reference" and any("summary_mismatch" in d for d in res["diagnostics"] if isinstance(d, str)),
         "%s is a summary_mismatch with its evidence: %r" % (what, ps))

  def odd_world(out):
    first(out)["answer"][0][2] = "not a list"
  res = run(odd_world)
  need(res["outcome"] == "plan_found" and res["plan"] == plain["plan"] and res["planning_summary"]["summary_check"] == "annotation_disabled"
       and res["planning_summary"]["disabled"] == "malformed_payload", "a payload of another form disables the annotation: %r" % res["planning_summary"])
  for what, change in (("no metadata", lambda o: first(o).pop("planning_summary") and None),
                       ("another profile", lambda o: first(o)["planning_summary"].update(profile_id="sha256:" + "0" * 64)),
                       ("another schema", lambda o: first(o)["planning_summary"].update(schema="planning_summary_output/9")),
                       ("an arity that does not fit", lambda o: first(o)["planning_summary"].update(core_arity=2)),
                       ("another slot map", lambda o: first(o)["planning_summary"].update(slots={"plan": 1, "world": 3, "progress": 2})),
                       ("a rejected entry without metadata", lambda o: o["rejected_answers"][0].pop("planning_summary") and None)):
    res = run(change)
    need(res["outcome"] == "planning_profile_error" and res.get("answer") is None and res.get("plan") is None
         and res["diagnostics"][0]["reason"] == "summary_output_error", "%s is planning_profile_error, no answer: %r" % (what, res["outcome"]))
  res = run(lambda o: {"error": "planning_profile_error: operation 3: unknown term"}, exit_code=1)
  need(res["outcome"] == "planning_profile_error" and res["diagnostics"][0]["reason"] == "planning_profile_error" and res.get("plan") is None,
       "the build's own profile error: %r" % res["outcome"])
  # the same decoding, entry by entry
  prof = ls.compile_profile(src, q)["profile"]
  need(prof["profile_id"] == saved("unstack.on.out")["answers"][0]["planning_summary"]["profile_id"], "the saved output has the profile of today's compiler")
  ex = ag.extract(json.dumps(saved("unstack.on.out")), kind="discovery", askvars=1, root="W0", summary=prof)
  ex0 = ag.extract(json.dumps(saved("unstack.off.out")), kind="discovery", askvars=1, root="W0")
  drop = lambda es: [{k: v for k, v in e.items() if k != "summary"} for e in es]
  need(ex["status"] == "completed" and drop(ex["accepted"]) == drop(ex0["accepted"]) and drop(ex["rejected"]) == drop(ex0["rejected"]) and ex["candidates"] == ex0["candidates"],
       "after the two positions are removed the extraction equals that of the output without the option")
  print("  output: a changed score and a changed list are summary_mismatch (annotation disabled, evidence kept, answer "
        "unchanged); a payload of another form disables the annotation; no metadata, another profile, another schema, "
        "an arity that does not fit, another slot map and the build's own profile error are planning_profile_error "
        "with no answer; the extraction of the saved output equals that of the output without the option")


def check_layout_and_payload(tmp):
  """Malformed answer metadata: a layout that does not fit stops the decoding with a typed error, never an
  exception; a payload of another form disables the annotation and keeps the answer."""
  src, q = unstack()
  prof = ls.compile_profile(src, q)["profile"]
  base = echo(saved("unstack.on.out"))
  plain = aa.solve(src, q, fake(tmp, base)[0], {"seconds": 5, "summary": True})

  def decode(change, where="answers"):
    out = copy.deepcopy(saved("unstack.on.out"))
    change(out[where][0])
    try:
      return ag.extract(json.dumps(out), kind="discovery", askvars=1, root="W0", summary=prof)
    except Exception as e:                       # noqa: BLE001  an exception is the defect this check looks for
      return {"status": "exception: %s: %s" % (type(e).__name__, e)}

  def meta(**kw):
    return lambda e: e["planning_summary"].update(kw)

  def cut(n, **kw):
    def f(e):
      e["answer"][0] = e["answer"][0][:n]
      e["planning_summary"].update(kw)
    return f

  layouts = (("core_arity 0 with a three-element answer", cut(3, core_arity=0)),
             ("core_arity -1", cut(2, core_arity=-1)),
             ("core_arity true", meta(core_arity=True)),
             ("core_arity 1.0", meta(core_arity=1.0)),
             ("core_arity as a string", meta(core_arity="1")),
             ("a short answer", cut(2)),
             ("a slot index true", meta(slots={"plan": True, "world": 2, "progress": 3})),
             ("a slot index 1.0", meta(slots={"plan": 1.0, "world": 2, "progress": 3})),
             ("an extra slot", meta(slots={"plan": 1, "world": 2, "progress": 3, "x": 4})),
             ("decorated as a number", meta(decorated=1)),
             ("an undecorated entry with an unknown reason", meta(decorated=False, reason="other")))
  for what, change in layouts:
    for where in ("answers", "rejected_answers"):
      ex = decode(change, where)
      need(ex["status"] == "summary_output_error", "%s (%s): %r" % (what, where, ex["status"]))
  res = aa.solve(src, q, fake(tmp, _changed(base, cut(3, core_arity=0)))[0], {"seconds": 5, "summary": True})
  need(res["outcome"] == "planning_profile_error" and res.get("plan") is None and res["diagnostics"][0]["reason"] == "summary_output_error",
       "core_arity 0 through the route: %r" % res["outcome"])

  def world(*facts):
    chain = "$nil"
    for f in reversed(facts):
      chain = ["$list", f, chain]
    return lambda e: e["answer"][0].__setitem__(2, chain)

  hold, on_ct = ["is rel2", "holding", "#:hand 1", "#:a 2"], ["is rel2", "on", "#:c 4", "#:table 3"]
  payloads = (("lossy 0", meta(lossy=0)),
              ("lossy null with a list", meta(lossy=None)),
              ("progress true", lambda e: e["answer"][0].__setitem__(3, True)),
              ("progress 1.0", lambda e: e["answer"][0].__setitem__(3, 1.0)),
              ("progress 2**60", lambda e: e["answer"][0].__setitem__(3, 2 ** 60)),
              ("a fact with a variable", world(hold, ["is rel2", "on", "?:X", "#:table 3"])),
              ("a fact of another family", world(hold, ["is rel2", "color", "#:c 4", "#:red 9"], on_ct)),
              ("a negative fact", world(["-is rel2", "holding", "#:hand 1", "#:a 2"], on_ct)),
              ("facts out of order", world(on_ct, hold)),
              ("a repeated fact", world(hold, hold, on_ct)),
              ("a world reason beside a list", meta(world_reason="open_root")),
              ("a progress reason beside a score", meta(progress_reason="witness_goal")),
              ("an unknown calculation", meta(calculation="done")),
              ("another template", meta(template="goal_count", units="missing_goal_atoms")),
              ("a lone surrogate in a constant", world(["is rel2", "holding", "\ud800", "#:a 2"])),
              ("an integer functor", world(["is rel2", "holding", [3, "#:hand 1"], "#:a 2"])),
              ("a list functor", world(["is rel2", "holding", [["bad"], "#:hand 1"], "#:a 2"])))
  for what, change in payloads:
    ex = decode(change)
    e0 = ex.get("accepted", [{}])[0]
    need(ex["status"] == "completed" and e0["summary"]["disabled"] == "malformed_payload" and e0["answer"] == [e0["answer"][0][:2]]
         and len(e0["answer"][0]) == 2 and e0["summary"]["world"] is None and e0["summary"]["progress"] is None,
         "%s disables the annotation of an accepted entry and keeps no value: %r" % (what, ex["status"]))
    json.dumps(ex, ensure_ascii=False).encode("utf-8")
    ex = decode(change, "rejected_answers")
    r0 = ex.get("rejected", [{}])[0]
    need(ex["status"] == "completed" and r0["summary"]["disabled"] == "malformed_payload" and len(r0["answer"][0]) == 2
         and ex["candidates"] == decode(lambda e: None)["candidates"], "%s on a rejected entry" % what)
    res = aa.solve(src, q, fake(tmp, _changed(base, change))[0], {"seconds": 5, "summary": True})
    ps = res["planning_summary"]
    need(res["outcome"] == "plan_found" and res["plan"] == plain["plan"] and res["confidence"] == plain["confidence"]
         and res["replay"] == plain["replay"] and ps["summary_check"] == "annotation_disabled" and ps["disabled"] == "malformed_payload"
         and ps["world"] is None and ps["progress"] is None, "%s through the route: %r" % (what, ps))
  ex = decode(lambda e: None)
  need(all(e["summary"]["summary_check"] == "not_checked" for e in ex["accepted"] + ex["rejected"]),
       "an entry's annotation in the evidence says that it is not checked")
  # valid forms: a constant that is not ASCII and a nested compound term
  good = sorted([["is rel2", "holding", "#:hand 1", ["$sk1", ["f", "#:a 2"], 7]], ["is rel2", "on", "#:\u00c5sa 5", "#:table 3"]],
                key=asum.order_key)
  for where in ("answers", "rejected_answers"):
    ex = decode(world(*good), where)
    e0 = (ex["accepted"] if where == "answers" else ex["rejected"])[0]
    need(ex["status"] == "completed" and e0["summary"]["disabled"] is None and e0["summary"]["world"] == good,
         "a constant that is not ASCII and a nested compound are accepted (%s): %r" % (where, e0["summary"]))
  # the saved output of the instgen hook test is not valid JSON (GK's proof print): a typed result, no exception
  with open(os.path.join(SAVED, "instgen.malformed.out")) as f:
    text = f.read()
  ex = ag.extract(text, kind="boolean", summary=prof)
  need(ex["status"] == "malformed" and not ex["accepted"], "the saved instgen output is malformed: %r" % ex["status"])
  print("  layout and payload: %d malformed layouts (core_arity 0, -1, true, 1.0 or a string, a short answer, slot "
        "indexes true or 1.0, an extra slot, a numeric decorated, an unknown reason) give summary_output_error on "
        "accepted and rejected entries, never an exception; %d malformed payloads (lossy 0 or null, progress true, "
        "1.0 or 2**60, a variable, another family, a negative fact, wrong order, a repeated fact, a reason beside a "
        "value, an unknown calculation, another template, a lone surrogate, an integer or list functor) disable the "
        "annotation, keep no value, and keep plan, confidence and replay; an entry's annotation in the evidence is "
        "marked not_checked; a constant that is not ASCII and a nested compound are accepted; the saved instgen "
        "output is a typed malformed result" % (len(layouts), len(payloads)))


def _changed(out, change, where="answers"):
  out = copy.deepcopy(out)
  change(out[where][0])
  return out


def check_replay_export(tmp):
  """The replay comparison needs an exported state for each prefix the replay validated."""
  import action_replay as rp
  src, q = unstack()
  name, _ = fake(tmp, echo(saved("unstack.on.out")))
  ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True, "termination": False})
  launch = ev["obligations"][0]["positive"]
  cand = launch["candidates"][0]
  good = rp.replay(src, cand["plan"], goal=q["query"]["goal"], export=True)
  n = len(cand["plan"])
  ps = aa.summary_check(launch, cand, good)
  need(ps["summary_check"] == "ok" and ps["reference_check"] == "agrees" and ps["replay_check"] == "subset" and ps["replay_prefixes"] == n + 1 == 4,
       "a complete export: %r" % ({k: ps[k] for k in ("summary_check", "reference_check", "replay_check", "replay_prefixes")},))

  def changed(f):
    r = copy.deepcopy(good)
    f(r)
    return aa.summary_check(launch, cand, r)

  incomplete = (("no export field", lambda r: r.pop("export")),
                ("an empty export", lambda r: r.__setitem__("export", [])),
                ("the root only", lambda r: r.__setitem__("export", r["export"][:1])),
                ("a truncated export", lambda r: r.__setitem__("export", r["export"][:n])),
                ("a state that is no list", lambda r: r["export"].__setitem__(1, "x")),
                ("a state that is null", lambda r: r["export"].__setitem__(2, None)),
                ("an atom without a predicate", lambda r: r["export"].__setitem__(2, [[1, 2]])),
                ("an export that is an object", lambda r: r.__setitem__("export", {"0": []})),
                ("checked_prefix true", lambda r: r.__setitem__("checked_prefix", True)),
                ("checked_prefix -1", lambda r: r.__setitem__("checked_prefix", -1)),
                ("checked_prefix beyond the plan", lambda r: r.__setitem__("checked_prefix", n + 1)),
                ("a valid replay with a shorter prefix", lambda r: r.__setitem__("checked_prefix", n - 1)))
  for what, f in incomplete:
    ps = changed(f)
    need(ps["summary_check"] == "annotation_disabled" and ps["disabled"] == "replay_export_incomplete" and ps["replay_check"] == "export_incomplete"
         and ps["reference_check"] == "agrees" and ps["world"] is None and ps["progress"] is None, "%s: %r" % (what, ps["summary_check"]))
  ps = changed(lambda r: r.update(verdict="inconsistent_action_state", step=0, checked_prefix=0))
  need(ps["summary_check"] == "annotation_disabled" and ps["disabled"] == "replay_root_not_validated", "a root that the replay did not validate: %r" % ps)
  ps = changed(lambda r: r.update(verdict="not_checked", step=None, checked_prefix=0, uncovered="replay_error"))
  need(ps["disabled"] == "replay_root_not_validated", "a replay error before any validated step")
  # a correctly formed export without one tracked fact of the reference list
  ref = asum.load(launch["summary"]["profile"]).get_actions([ls._gk(a) for a in cand["plan"]])
  tracked = ref.facts()[0]
  ps = changed(lambda r: r["export"].__setitem__(n, [a for a in r["export"][n] if ls._gk(a) != tracked]))
  need(ps["summary_check"] == "summary_mismatch" and ps["replay_check"] == "not_subset" and ps["disabled"] == "summary_mismatch"
       and ps["detail"] == [{"kind": "not_a_subset_of_the_replay", "prefix": n, "facts": [tracked]}] and ps["world"] is None,
       "an export without a tracked fact: %r" % ps)
  # a genuinely empty state: a profile whose root list is empty
  empty = copy.deepcopy(launch["summary"]["profile"])
  empty["semantic"]["initial"]["facts"] = []
  empty["profile_id"] = asum.profile_id(empty["semantic"])
  rec0 = [asum.load(empty).get_actions([])]
  need(rec0[0].facts() == [], "the control profile has an empty root list")
  need(aa._replay_comparison(rec0, {"verdict": "valid", "step": None, "checked_prefix": 0, "export": [[]]}, 0) == ("subset", 1, []),
       "an empty exported state is a state")
  need(aa._replay_comparison(rec0, {"verdict": "valid", "step": None, "checked_prefix": 0, "export": []}, 0)[0] == "export_incomplete",
       "an absent state is not")
  # neither a disabled annotation nor a mismatch changes the answer
  plain = aa.solve(src, q, name, {"seconds": 5, "summary": True})
  real = aa.rp.replay
  for what, f, want in (("no export", lambda r: r.pop("export", None), "annotation_disabled"),
                        ("a missing fact", lambda r: "export" in r and r["export"][-1].clear(), "summary_mismatch")):
    def damaged(*a, **k):
      r = real(*a, **k)
      f(r)
      return r
    aa.rp.replay = damaged
    try:
      res = aa.solve(src, q, name, {"seconds": 5, "summary": True})
    finally:
      aa.rp.replay = real
    need(res["planning_summary"]["summary_check"] == want and all(res.get(k) == plain.get(k) for k in ("outcome", "answer", "plan", "confidence", "confidence_status", "proof", "replay")),
         "%s: %s, and outcome, plan, confidence, proof and replay verdict are unchanged" % (what, res["planning_summary"]["summary_check"]))
  print("  replay export: a complete export is ok (reference agrees, 4 states compared); %d incomplete or malformed "
        "exports or prefix counts are annotation_disabled (replay_export_incomplete); a root the replay did not "
        "validate is replay_root_not_validated; an export without a tracked fact of the reference is summary_mismatch; "
        "an empty exported state is a state, an absent one is not; neither result changes the answer" % len(incomplete))


def check_capability(tmp):
  """The summary capability counts only for the binary, library, strategy and contract of a validation record."""
  src, q = unstack()
  lib = src["library"]
  real = ag.backend_profile(ag.SUMMARY_BACKEND)
  rec = real["validated"][0]
  need(rec["capability"] == ag.SUMMARY_CAPABILITY and rec["library"] == lib and rec["strategy_sha256"] == ag.profile_strategy_sha256(real)
       and rec["contract"] == ag.summary_contract() and real["unmet"] == ag.BACKENDS["gk"]["unmet"]
       and real["known_failures"] == ag.BACKENDS["gk"]["known_failures"], "the record names today's library, strategy and contract; the limits of gk stay")
  if real["sha256"] is not None:
    need((ag.summary_capability(real, lib) is None) == (real["sha256"] == rec["binary_sha256"]),
         "the summary binary is validated exactly when its hash is the recorded one")
  echo_out = echo(saved("unstack.on.out"))
  cases = (("no record", dict(validated=False), "planning_summary_not_validated"),
           ("no module", dict(summary=False), "planning_summary_unsupported"))
  for what, kw, reason in cases:
    name, log = fake(tmp, echo_out, **kw)
    ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True})
    need(ev["outcome"]["outcome"] == "unsupported_backend_requirement" and ev["outcome"]["reason"] == reason and ev["calls"]["gk"] == 0 and not calls(log),
         "%s: %r" % (what, ev["outcome"]))
  for what, change in (("another binary at the path", lambda v: v.update(binary_sha256=rec["binary_sha256"])),
                       ("another library", lambda v: v["library"].update(hash="0" * 64)),
                       ("another strategy", lambda v: v.update(strategy_sha256="0" * 64)),
                       ("another output contract", lambda v: v["contract"].update(output="planning_summary_output/2")),
                       ("no contract", lambda v: v.pop("contract"))):
    name, log = fake(tmp, echo_out)
    change(ag.BACKENDS[name]["validated"][0])
    ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True})
    need(ev["outcome"]["reason"] == "planning_summary_not_validated" and ev["calls"]["gk"] == 0 and not calls(log), "%s: %r" % (what, ev["outcome"]))
  name, log = fake(tmp, echo_out)
  ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True})
  sc = ev["backend"]["summary_capability"]
  need(ev["outcome"] is None and sc["validated"] is True and sc["contract"] == ag.summary_contract() and "4 of 4" in sc["evidence"], "the validated fake: %r" % sc)
  plain = ag.run_query(src, q, name, {"seconds": 5})
  need("summary_capability" not in plain["backend"], "a run without the option records no summary capability")
  print("  capability: the record names today's library, strategy and summary contract and keeps the limits of gk; "
        "a build without the module and a build without a record are refused with 0 launches; so are a record of "
        "another binary, library, strategy or output contract and one without a contract; the validated record is "
        "in the evidence")


def check_preflight(tmp):
  """A summary request on a build that cannot run it is refused before any model call."""
  import contextlib
  import io
  import llmcall
  text = "Ann is in Lund. A bus goes from Lund to Malmo. How can Ann get to Malmo?"
  asked = []

  def provider(*a, **k):
    asked.append("provider")
    raise AssertionError("the provider was called")

  def cached(*a, **k):
    asked.append("cache")
    raise AssertionError("the model cache was read")

  names = ("call_claude", "call_gemini", "call_deepseek", "call_gpt", "_get_llm_cached", "sleepseconds")
  original = {n: getattr(llmcall, n) for n in names}

  def route(backend, formal=None):
    del asked[:]
    col = {}
    opts = {"actions_flag": True, "planning_summary_flag": True, "action_backend": backend}
    if formal is not None:
      opts["formal_flag"] = True
    with contextlib.redirect_stdout(io.StringIO()):
      answer = ap.run(formal if formal is not None else text, opts, col)
    return answer, col["action_route"], list(asked)

  echo_out = echo(saved("unstack.on.out"))
  for n in names[:4]:
    setattr(llmcall, n, provider)
  llmcall._get_llm_cached = cached
  llmcall.sleepseconds = 0
  try:
    unvalidated, _ = fake(tmp, echo_out, validated=False)
    answer, rec, got = route(unvalidated)
    need((rec["result"] or {}).get("outcome") == "unsupported_backend_requirement" and "planning_summary_not_validated" in answer
         and answer.startswith("Cannot answer:") and not got and rec["calls"]["gk"] == 0 and rec["calls"]["logical"] == 0
         and rec["translation"] is None, "an unvalidated binary is refused before translation: %r %r" % (answer, got))
    missing, _ = fake(tmp, echo_out)
    os.remove(ag.BACKENDS[missing]["path"])
    answer, rec, got = route(missing)
    need((rec["result"] or {}).get("outcome") == "backend_unavailable" and answer.startswith("Error: backend_unavailable") and not got,
         "a missing binary is refused before translation: %r" % answer)
    nomodule, _ = fake(tmp, echo_out, summary=False)
    answer, rec, got = route(nomodule)
    need(answer.startswith("Error: incompatible options") and "planning-summary" in answer and not got, "a build without the module: %r" % answer)
    valid, _ = fake(tmp, echo_out)
    held = {m: sys.modules.get(m) for m in ("action_summary", "lc_action_summary")}
    sys.modules["action_summary"] = None
    try:
      answer, rec, got = route(valid)
    finally:
      for m, mod in held.items():
        sys.modules[m] = mod
    need((rec["result"] or {}).get("outcome") == "unsupported_backend_requirement" and "planning_summary_unsupported" in answer and not got,
         "the summary modules missing: %r" % answer)
    # a valid build passes: the translation starts and reaches the (failing) model cache
    answer, rec, got = route(valid)
    need(got and (rec["result"] or {}).get("outcome") not in ("unsupported_backend_requirement", "backend_unavailable"),
         "a validated build passes the early check and reaches the translation: %r %r" % (answer, got))
  finally:
    for n, f in original.items():
      setattr(llmcall, n, f)
  # a record of another library passes the early check and is refused before the launch
  fx = [x for x in cs.load_formal() if x[0]["id"] == "unstack"][0][0]
  record = json.dumps({"entities": fx["entities"], "units": fx["units"], "queries": fx["queries"]})
  other, log = fake(tmp, echo_out)
  ag.BACKENDS[other]["validated"][0]["library"] = dict(ag.BACKENDS[other]["validated"][0]["library"], hash="0" * 64)
  need(ag.summary_preflight(other) is None, "the early check reads no library")
  answer, rec, got = route(other, formal=record)
  need((rec["result"] or {}).get("outcome") == "unsupported_backend_requirement" and "planning_summary_not_validated" in answer
       and rec["calls"]["gk"] == 0 and not calls(log), "another library: refused before the launch: %r" % answer)
  answer, rec, got = route(valid, formal=record)
  need((rec["result"] or {}).get("outcome") == "plan_found" and rec["result"]["planning_summary"]["summary_check"] == "ok", "the valid build runs: %r" % answer)
  print("  preflight: with -planning-summary an unvalidated binary, a missing binary, a build without the module and "
        "missing summary modules are refused before translation (no model cache read, no provider call, 0 GK "
        "calls); a validated build reaches the translation; a record of another library passes the early check "
        "and is refused before the launch")


def check_launch_phases(tmp):
  """A staged file that is missing or changed: before the launch no process runs; before the diagnostic relaunch
  the completed launch, its output and its count stay."""
  import fcntl
  from unittest import mock
  src, q = unstack()
  name, log = fake(tmp, {"result": "no answers found"})
  label = "Q1.plan.positive"

  def tampered(phase, act, keep=None):
    held = []

    def tamper(inp, prof, at):
      if at == phase:
        with open(ag.SERIAL_LOCK, "a") as f:
          try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            held.append(False)
          except BlockingIOError:
            held.append(True)
        act(inp, prof)
    ag._TAMPER.append(tamper)
    before = len(calls(log))
    try:
      with ag.recording() as got:
        ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True, "keep": keep})
    finally:
      ag._TAMPER.pop()
    return ev, got, len(calls(log)) - before, held

  for what, act in (("a changed profile", lambda i, p: open(p, "a").write(" ")), ("a missing profile", lambda i, p: os.remove(p)),
                    ("a missing input", lambda i, p: os.remove(i))):
    ev, got, ran, held = tampered("launch", act)
    o = ev["outcome"]
    need(o["outcome"] == "planning_profile_error" and o["phase"] == "launch" and o["reason"].startswith("staged_") and ran == 0
         and ev["calls"]["gk"] == 0 and ev["obligations"][0]["positive"] is None and not got and held == [True],
         "%s before the launch: %r, %d processes" % (what, o, ran))
    keep = os.path.join(tmp, "keep_%d" % len(os.listdir(tmp)))
    ev, got, ran, held = tampered("relaunch", act, keep)
    o, l = ev["outcome"], ev["obligations"][0]["positive"]
    need(o["outcome"] == "planning_profile_error" and o["phase"] == "relaunch" and o["reason"].startswith("staged_") and ran == 1
         and ev["calls"]["gk"] == 1 and ev["calls"]["by_role"] == {"discovery:positive": 1} and held == [True],
         "%s before the relaunch: %r, %d processes" % (what, o, ran))
    need(l is not None and l["status"] == "completed" and l["exit"] == 0 and l["stdout"] and l["result"] == "no answers found"
         and l["relaunch"]["status"] == "not_launched" and l["relaunch"]["staged_error"] == o["reason"] and l["termination"] == "diagnostic_not_launched"
         and ev["incomplete"] == [], "%s: the completed launch is kept and not incomplete" % what)
    need(len(got) == 1 and got[0]["stdout"] == l["stdout"] and got[0]["profile_sha256"] == l["summary"]["profile_sha256"]
         and ag.sha256_text(got[0]["profile"]) == l["summary"]["profile_sha256"] and got[0]["relaunch"]["status"] == "not_launched",
         "%s: the recording has the launch, its profile bytes and the relaunch that was not made" % what)
    kept = sorted(os.listdir(keep))
    need(kept == [label + x for x in (".err", ".input.json", ".out", ".profile.json")], "%s: the kept files %r" % (what, kept))
  # a verification that raises an OSError of its own is a typed error too
  with mock.patch.object(ag, "_verify_staged", side_effect=FileNotFoundError("gone")):
    ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True})
  need(ev["outcome"]["outcome"] == "planning_profile_error" and ev["outcome"]["reason"].startswith("staged_file_unreadable") and ev["calls"]["gk"] == 0,
       "an OSError of the verification: %r" % ev["outcome"])
  res = aa.decide(src, q, ev)
  need(res["outcome"] == "planning_profile_error" and res.get("plan") is None, "the route outcome")
  # an ordinary launch: the recording names the exact profile; the data files are fingerprinted
  ok_name, _ = fake(tmp, echo(saved("unstack.on.out")))
  with ag.recording() as got:
    ev = ag.run_query(src, q, ok_name, {"seconds": 5, "summary": True})
  l = ev["obligations"][0]["positive"]
  need(len(got) == 1 and ag.sha256_text(got[0]["profile"]) == l["summary"]["profile_sha256"] and json.loads(got[0]["profile"]) == l["summary"]["profile"],
       "the recording holds the exact profile bytes")
  need(l["summary"]["data_files"] == {n: {"status": "absent", "sha256": None} for n in ag.TAXONOMY_FILES}, "a data folder without the files: %r" % l["summary"]["data_files"])
  with ag.recording() as got:
    ag.run_query(src, q, ok_name, {"seconds": 5})
  need(got[0]["profile"] is None and got[0]["profile_sha256"] is None, "a launch without the option has no profile")
  real = ag.data_fingerprints(ag.backend_profile(ag.SUMMARY_BACKEND))
  need(all(v["status"] == "present" and len(v["sha256"]) == 64 for v in real.values()) or not os.path.isdir(ag.DATAFOLDER), "the real data folder: %r" % real)
  nouse = ag.backend_profile(ag.SUMMARY_BACKEND)
  nouse["params"] = [x for x in nouse["params"] if x != "-taxonomy"]
  need(all(v["status"] == "not_used" for v in ag.data_fingerprints(nouse).values()), "parameters without -taxonomy")
  print("  launch phases: a changed or missing profile and a missing input before the launch give "
        "planning_profile_error (phase launch) with 0 processes; before the diagnostic relaunch they give phase "
        "relaunch with the completed launch kept (output, exit, 1 counted call, recording, kept files, not "
        "incomplete); both checks run while the serial lock is held; an OSError of the verification is typed; the "
        "recording holds the exact profile; the taxonomy files are fingerprinted (present, absent or not_used)")


def check_runner(tmp):
  """A formal-input runtests smoke with fake builds: no model call, no GK."""
  import contextlib
  import io
  top = os.path.join(HERE, "..", "..")
  if top not in sys.path:
    sys.path.insert(0, top)
  import runtests
  fx = [x for x in cs.load_formal() if x[0]["id"] == "unstack"][0][0]
  record = {"entities": fx["entities"], "units": fx["units"], "queries": fx["queries"]}
  testfile = os.path.join(tmp, "tests_summary_smoke.py")
  with open(testfile, "w") as f:
    f.write(repr([[1, json.dumps(record), "plan"], [2, json.dumps(record), "plan"]]))
  on, log_on = fake(tmp, echo(saved("unstack.on.out")))
  off, log_off = fake(tmp, saved("unstack.off.out"), summary=False)
  cases = {}
  for tag, extra in (("on", ["-planning-summary", "-action-backend", on]), ("off", ["-action-backend", off])):
    out = os.path.join(tmp, "runs_" + tag)
    argv = sys.argv
    sys.argv = ["runtests.py", testfile, "-llms", "gemini", "-out", out, "-actions", "-formal"] + extra
    said = io.StringIO()
    try:
      with contextlib.redirect_stdout(said):
        code = runtests.main()
    finally:
      sys.argv = argv
    need(code in (0, None), "runtests %s: exit %r: %s" % (tag, code, said.getvalue()[-500:]))
    folder = os.path.join(out, "summary_smoke")
    cases[tag] = [json.load(open(os.path.join(folder, "gemini", "case_%04d.json" % i))) for i in (1, 2)]
    manifest = json.load(open(os.path.join(folder, "run_manifest.json")))
    need(("planning_summary_flag" in json.dumps(manifest)) == (tag == "on"), "the %s manifest records the option exactly when it is given" % tag)
  for i in range(2):
    a, b = cases["on"][i], cases["off"][i]
    ra, rb = a["action_route"]["result"], b["action_route"]["result"]
    need(ra["outcome"] == rb["outcome"] == "plan_found" and a["answer"] == b["answer"] and ra["plan"] == rb["plan"] and ra["confidence"] == rb["confidence"],
         "case %d: the same answer with and without the option" % (i + 1))
    need(ra["planning_summary"]["summary_check"] == "ok" and ra["planning_summary"]["replay_check"] == "subset" and "planning_summary" not in rb,
         "case %d: the annotation only with the option" % (i + 1))
    need(a["action_route"]["calls"]["gk"] == b["action_route"]["calls"]["gk"] == 1, "case %d: one GK call each: %r" % (i + 1, a["action_route"]["calls"]))
    need(all(c["action_route"]["calls"][k] == 0 for c in (a, b) for k in ("logical", "live", "provider_attempts")),
         "case %d: no model call: %r" % (i + 1, a["action_route"]["calls"]))
  need(len(calls(log_on)) == 2 and all(x.count("-planning-profile") == 1 for x in calls(log_on))
       and len(calls(log_off)) == 2 and all("-planning-profile" not in x for x in calls(log_off)), "two launches per run; the sidecar only with the option")
  print("  runner: runtests -actions -formal with fake builds writes two case records per run; with -planning-summary "
        "each has the checked annotation and one GK call, without it none; answers are equal; the manifest records "
        "the option only when given; no model call")


def check_unavailable_and_isolation(tmp):
  # a computed goal: no profile, the query runs unchanged
  b = "b 5"
  S, on, H, A, T = cs.S, cs.on, cs.H, cs.A, cs.T
  quant = [S("S1", ["isa", "hand", H]), S("S2", ["and", ["isa", "block", A], ["isa", "block", b], ["isa", "table", T]]),
           S("S3", ["forall", "X", ["implies", ["isa", "block", "X"], on("X", T)]]),
           S("S4", ["state_law", ["forall", "X", ["implies", ["and", ["isa", "block", "X"], on("X", T)], ["has property", "stable", "X"]]]]),
           S("S5", ["has property", "empty", H]), S("S6", ["has property", "clear_top", A]), S("S7", ["has property", "clear_top", b])]
  src, q, r = cs.build(quant, ["has property", "stable", A])
  need(r["status"] == "unavailable", "the control has no profile")
  name, log = fake(tmp, {"result": "no answers found"})
  ev = ag.run_query(src, q, name, {"seconds": 5, "summary": True, "termination": False})
  l = ev["obligations"][0]["positive"]
  need(ev["outcome"] is None and l["summary"]["status"] == "unavailable" and l["summary"]["reason"] == "computed_goal" and l["summary"]["profile"] is None
       and all("-planning-profile" not in a for a in calls(log)) and len(calls(log)) == 1, "an unavailable summary: the query runs unchanged: %r" % l["summary"])
  res = aa.decide(src, q, ev)
  need(res["outcome"] == "not_found" and "planning_summary" not in res, "the ordinary answer of that query")
  # two queries of one source: each launch gets the profile of its own query
  srcu, qu = unstack()
  q2 = ar.compile_query(["@id", "Q2", ["plan", cs.on(cs.C, cs.T)]], srcu)
  none, log2 = fake(tmp, {"result": "no answers found"})
  ids = []
  for query in (qu, q2):
    ev = ag.run_query(srcu, query, none, {"seconds": 5, "summary": True, "termination": False})
    ids.append(ev["obligations"][0]["positive"]["summary"]["profile_id"])
  want = [ls.compile_profile(srcu, x)["profile"]["profile_id"] for x in (qu, q2)]
  need(ids == want and ids[0] != ids[1] and len(calls(log2)) == 2, "two queries, two profiles: %r" % ids)
  print("  unavailable and isolation: a query with a computed goal runs unchanged and records computed_goal; two "
        "queries of one source get two profiles, each launch its own")


def run():
  tmp = tempfile.mkdtemp(prefix="summary_route_")
  try:
    check_routing()
    check_answer(tmp)
    check_binding(tmp)
    check_output(tmp)
    check_layout_and_payload(tmp)
    check_replay_export(tmp)
    check_capability(tmp)
    check_preflight(tmp)
    check_launch_phases(tmp)
    check_unavailable_and_isolation(tmp)
    check_runner(tmp)
  finally:
    for name in FAKES:
      ag.BACKENDS.pop(name, None)
    del FAKES[:]


if __name__ == "__main__":
  run()
