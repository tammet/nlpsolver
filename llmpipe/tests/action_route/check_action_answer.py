"""WP13 checks: the answer policy (`solver/action_answer.py`).

No model call and no GK launch.  A fake executable, registered as a build for this check, answers each prover
question from a table (the question's obligation and polarity -> a GK output), so `solve` runs the production
adapter, the replay and the policy on gold sources and queries.

  paired        the verdict of one Boolean obligation: Yes, No, contested (both accepted; conflict mass), Unknown,
                error; inconclusive terminations are recorded
  snapshot      c03 true/false/unknown/both through solve; c30 overlap keeps its experimental 0.84; an ask
  verify        C20: a valid sequence, a false first step, an unknown prefix with a later negative, a false final
                formula; a contested step; the M29.neg class (a negative after a step that the replay does not
                confirm); a GK Yes the replay rejects; a missing joint answer; a prefix the replay does not validate
  negative side a verification whose negative obligation alone needs negative persistence: a Yes stands; No,
                Unknown and contested become the typed refusal (x03 Q3, lamp_on Q2)
  discovery     invalid first, valid second (the raw term and proof kept); all invalid; below the cutoff; the empty
                plan; a witness checked by the replay; a step bound checked by the replay; the search-coverage record
  state         an inconsistent initial state (a plan and a question), even with an accepted empty plan
  failures      a GK error and a timeout are typed outcomes; decided queries need no launch; a query with `can` is
                rejected; evidence of another query is rejected; a -nonegative run decides nothing (Sol's review)
  render        the gold renderings of p01, p03 and x01, and the rule's wording for x02
  score         every answer-level gold key: outcome, alternative, not_outcome, answer, forbidden answers, outcomes
                and plans, a validated plan (another or a longer one is information), witness, conflict facts and
                step, reason and units, record, pinned and recorded confidences; render is information; keys of
                other layers and unchecked keys are listed; an unknown key fails (Sol's review)
"""

import copy
import gzip
import json
import os
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_answer as aa
import gold_score as gs
import action_english as aen
import action_gk as ag
import action_replay as rp
import action_route as ar
import check_action_availability as cav
import check_action_validation as cv
import fixture_materialize as fm

need = cav.need
GOLD = {c["case"]: c for c in fm.load_all()}
PROOF = [[1, ["in", "query:Q:q:positive", "goal", 1], [["-p"], ["$ans", "?:X", "$obj"]]],
         [2, ["in", "src:S1:initial_fact:0", "axiom", 1], [["p"]]],
         [3, ["mp", 1, 2, "fromgoal", 1], [["$ans", "?:X", "$obj"]]]]
BOOL = [["$ans", "?:X3", "$obj"]]
NONE = {"result": "no answers found"}


def yes(conf=1.0):
  return {"result": "answer found", "answers": [{"answer": BOOL, "confidence": conf, "positive proof": PROOF}]}


def conflict():
  e = {"answer": BOOL, "confidence": 0.0, "detail": {"support_for": 0.0, "support_against": 0.0, "conflict": 1.0},
       "positive proof": PROOF, "negative proof": PROOF}
  return {"result": "answer found", "rejected_answers": [e]}


def refuted():
  e = {"answer": BOOL, "confidence": 1.0, "detail": {"support_for": 0.0, "support_against": 1.0, "conflict": 0.0},
       "positive proof": PROOF, "negative proof": PROOF}
  return {"result": "answer found", "rejected_answers": [e]}


def answers(*pairs):
  """Accepted answers with reported terms: (terms, confidence) pairs; terms is a list of $ans arguments."""
  return {"result": "answer found" if any(c >= 0.1 for _, c in pairs) else "evidence below limit",
          "answers": [{"answer": [["$ans"] + list(t)], "confidence": c, "positive proof": PROOF} for t, c in pairs]}


def do(*actions, root="W0"):
  """A GK situation term: actions in execution order, entity ids with #:."""
  s = root
  for a in actions:
    s = ["$do", [a[0]] + [("#:" + x if " " in x else x) for x in a[1:]], s]
  return s


FAKES = []


def fake(table):
  """A registered fake build that answers from `table`: {"step1:positive": output, ...}; a missing key is no
  answer.  An output is a GK result object, "error", "sleep" or {"raw": text}.  Under -printlevel it prints GK's
  search-limit line first."""
  tmp = tempfile.mkdtemp()
  with open(os.path.join(tmp, "table.json"), "w") as f:
    json.dump(table, f)
  path = os.path.join(tmp, "fake_answer_prover")
  with open(path, "w") as f:
    f.write('''#!%s
import json, os, sys, time
args = sys.argv[1:]
table = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "table.json")))
q = json.load(open(args[4]))[-1]["@name"]
out = table.get(q.split(":", 2)[2], {"result": "no answers found"})
if out == "sleep":
  time.sleep(5)
if out == "error":
  print(json.dumps({"error": "a fake failure"}))
  sys.exit(1)
if "-printlevel" in args:
  print("<- nothing proved (search limit reached)")
print(out["raw"] if "raw" in out else json.dumps(out))
''' % sys.executable)
  os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
  name = "fake_answer_%d" % len(FAKES)
  ag.BACKENDS[name] = dict(ag.backend_profile(), name=name, path=path, sha256=ag.sha256_file(path), datafolder=tmp)
  FAKES.append(name)
  return name


def compiled(case, qid=None, package=None):
  c = GOLD[case]
  a = cv.gold_source(c)
  if package is not None:
    return a, ar.compile_query(package, a), None
  q = [x for x in c["queries"] if x["id"] == qid][0]
  return a, ar.compile_query(q["stage2"], a, cv.gold_limits(q), None, **fm.selection(q)), q


def solve(case, qid, table, package=None, limits=None):
  a, qa, q = compiled(case, qid, package)
  return ar.solve_query(a, qa, {"backend": fake(table), "limits": dict({"seconds": 5}, **(limits or {}))})


def ev(out, termination=None):
  x = ag.extract(json.dumps(out) if isinstance(out, dict) else out)
  x["termination"] = termination or ("proof" if x["accepted"] else "undetermined")
  return x


# ---------------------------------------------------------------------------


def check_paired():
  rows = [(yes(), NONE, "Yes"), (NONE, yes(), "No"), (yes(), yes(), "contested"), (NONE, NONE, "Unknown"),
          (conflict(), NONE, "contested"), (yes(), conflict(), "contested"), (refuted(), NONE, "Unknown"),
          (yes(0.05), NONE, "Unknown")]
  for pos, neg, want in rows:
    v = aa.paired(ev(pos), ev(neg))
    need(v["verdict"] == want, "paired %s / %s: %s, expected %s" % (pos, neg, v["verdict"], want))
  v = aa.paired(ev(NONE, "search_limit"), ev(NONE, "diagnostic_error"))
  need(v["verdict"] == "Unknown" and v["notes"] == ["positive: search_limit", "negative: diagnostic_error"],
       "inconclusive notes: %r" % v)
  bad = ev(NONE)
  bad["status"] = "prover_timeout"
  v = aa.paired(ev(yes()), bad)
  need(v["verdict"] == "error" and v["issues"][0]["status"] == "prover_timeout", "a failed polarity: %r" % v)
  need(aa.paired(ev(yes()), None)["verdict"] == "error", "a missing negative launch is an error")
  print("  paired: %d verdicts (a rejected entry at 1.0 without conflict mass is no No; conflict mass makes "
        "contested even beside an accepted answer); inconclusive terminations noted; a failed polarity is an error"
        % len(rows))


def check_snapshot():
  for variant, table, want in (("true", {"q:positive": yes()}, "Yes"), ("false", {"q:negative": yes()}, "No"),
                               ("unknown", {}, "Unknown"),
                               ("both", {"q:positive": conflict(), "q:negative": conflict()}, "contested")):
    r = solve("c03_only_if_red:" + variant, "Q1", table)
    need(r["outcome"] == "verification_result" and r["answer"] == want, "c03 %s: %s %s" % (variant, r["outcome"], r["answer"]))
    need(gs.score(r, [q for q in GOLD["c03_only_if_red:" + variant]["queries"] if q["id"] == "Q1"][0]["expect"])["ok"],
         "c03 %s scores against gold" % variant)
  with gzip.open(os.path.join(HERE, "gk_output", "C30.overlap.pos.out.gz"), "rt") as f:
    overlap = f.read()
  r = solve("c30_uncertain_put_on:overlap", "Q1", {"q:positive": {"raw": overlap}})
  need(r["answer"] == "Yes" and r["confidence"] == 0.84 and r["confidence_status"] == "experimental"
       and r["experimental_reasons"] == ["uncertain_evidence_reused"], "c30 overlap: %r" % {k: r[k] for k in ("answer", "confidence")})
  r = solve("c18_initial_binding:base", "Q5", {"q:positive": answers((["#:Ann 1"], 1.0))})
  need(r["answer"] == "Ann 1" and r["answers"] == ["Ann 1"] and r["confidence_status"] == "validated", "ask: %r" % r["answer"])
  r = solve("c18_initial_binding:base", "Q5", {})
  need(r["answer"] == "Unknown", "an ask without a candidate is Unknown")
  r = solve("c20_verify:base", "Q5", {"final:positive": yes()})
  need(r["answer"] == "Yes" and r["calls"]["gk"] == 3, "verify([], Q) is a snapshot question: %r" % r["calls"])
  print("  snapshot: c03 true/false/unknown/both give Yes/No/Unknown/contested as gold; c30 overlap keeps an "
        "experimental 0.84; an ask reports its entity; verify([], Q) is a snapshot question")


def check_verify():
  S = lambda *ids: {"%s:positive" % i: yes() for i in ids}
  rows = [
    ("c20_verify:a_red", "Q1", S("step1", "step2", "final", "joint"), "Yes", None, None),
    ("c20_verify:base", "Q2", {"step1:negative": yes()}, "No", 1, None),
    ("c20_verify:a_red", "Q4", dict(S("step1", "joint"), **{"final:negative": yes()}), "No", None, None),
    ("c20_verify:unknown_prefix", "Q3", {"step2:negative": yes()}, "Unknown", 1, None),
    ("c20_verify:a_red", "Q1", dict(S("step1", "step2", "final", "joint"), **{"step2:negative": yes()}), "contested", 2, None),
    ("x03_partial_effects:lamp_unknown", "Q1", dict(S("step1"), **{"final:negative": yes()}), "Unknown", None,
     "replay_disagrees"),
    ("x01_identity:self_placement", "Q1", S("step1", "final", "joint"), "Unknown", None, "replay_disagrees"),
    ("c20_verify:unknown_prefix", "Q3", dict(S("step1"), **{"step2:negative": yes()}), "Unknown", None,
     "prefix_not_validated"),
  ]
  for case, qid, table, want, step, validation in rows:
    r = solve(case, qid, table)
    need(r["outcome"] == "verification_result" and r["answer"] == want and r.get("failing_step") == step
         and r.get("validation") == validation,
         "%s %s: %s %s step %s validation %s" % (case, qid, r["outcome"], r["answer"], r.get("failing_step"),
                                                  r.get("validation")))
  r = solve("c20_verify:a_red", "Q1", S("step1", "step2", "final"))
  need(r["answer"] == "Unknown" and any("joint question" in d for d in r["diagnostics"]), "no joint answer: %r" % r["diagnostics"])
  r = solve("c20_verify:a_red", "Q1", S("step1", "step2", "final", "joint"))
  need(r["proof"]["obligation"] == "joint" and r["proof"]["proof"] == PROOF and gs.score(r, {})["category"] == "supplied_sequence",
       "the joint proof is kept with a Yes verification: %r" % r["proof"])
  need(r["confidence"] == 1.0 and r["replay"]["verdict"] == "valid" and len(r["verdicts"]) == 3
       and r["calls"]["gk_by_role"] == {"step:positive": 2, "step:negative": 2, "final:positive": 1, "final:negative": 1,
                                        "joint:positive": 1, "termination": 3}, "c20 Q1 record: %r" % r["calls"])
  print("  verify: C20's valid sequence, false first step, unknown prefix with a later negative and false final "
        "formula; a contested step; a negative after a step that the replay does not confirm (the M29.neg class) "
        "and a Yes the replay rejects are Unknown; no joint answer and an unvalidated prefix are Unknown")


def check_negative_side():
  """x03 Q3 and lamp_on Q2: only the negative obligation of the final formula needs negative persistence, which the
  starting backend refuses.  The query runs; a Yes stands; No, Unknown and contested become the typed refusal, with the
  prover's reading and the verdicts kept."""
  S = lambda *ids: {"%s:positive" % i: yes() for i in ids}
  n = 0
  for case, qid, steps in (("x03_partial_effects:base", "Q3", ("step1", "step2")),
                           ("x03_partial_effects:lamp_on", "Q2", ("step1",))):
    expect = [q for q in GOLD[case]["queries"] if q["id"] == qid][0]["expect"]
    r = solve(case, qid, S(*(steps + ("final", "joint"))))
    need(r["outcome"] == "verification_result" and r["answer"] == "Yes" and gs.score(r, expect)["ok"],
         "%s %s: %s %s" % (case, qid, r["outcome"], r.get("answer")))
    need([x["polarities"] for x in r["evidence"]["requirements"] if x["capability"] == "negative_persistence"]
         == [["negative"]], "%s %s: the requirement: %r" % (case, qid, r["evidence"]["requirements"]))
    for table, before in (({}, "Unknown"),
                          (dict(S(*steps), **{"final:positive": yes(), "final:negative": yes()}), "contested"),
                          (dict(S(*(steps + ("joint",))), **{"final:negative": yes()}), None)):
      r = solve(case, qid, table)
      d = r["diagnostics"][0]
      need(r["outcome"] == "unsupported_backend_requirement" and d["reason"] == "negative_persistence_unavailable"
           and d["polarities"] == ["negative"] and (before is None or d["answer_before_refusal"] == before)
           and d["answer_before_refusal"] != "Yes" and len(r["verdicts"]) == len(steps) + 1 and r["calls"]["gk"] > 0,
           "%s %s %s: %s %r" % (case, qid, before, r["outcome"], d))
      need(not gs.score(r, expect)["ok"] and gs.score(r, expect)["category"] == "backend_limit", "%s: score" % case)
      n += 1
  print("  negative side: x03 Q3 and lamp_on Q2 run with a requirement of polarities [negative]; their Yes stands and "
        "scores against the gold; %d Unknown, contested and refuted readings become negative_persistence_unavailable "
        "with the reading and the verdicts kept" % n)


def check_discovery():
  pkg = ["@id", "QP", ["plan", ["is rel2", "on", "a 2", "b 3"]]]
  take = ["take", "hand 1", "a 2"]
  bad, good = do(take, ["put_on", "hand 1", "a 2", "a 2"]), do(take, ["put_on", "hand 1", "a 2", "b 3"])
  r = solve("c20_verify:a_red", None, {"plan:positive": answers(([bad], 0.98), ([good], 0.98))}, package=pkg)
  need(r["proof"]["answer"] == [["$ans", good]] and r["candidates"][1]["term"] == good
       and gs.score(r, {})["category"] == "validated_plan", "the raw term and proof are kept with the plan")
  need(r["outcome"] == "plan_found" and r["plan"] == [take, ["put_on", "hand 1", "a 2", "b 3"]]
       and [c["verdict"] for c in r["candidates"]] == ["invalid", "valid"] and r["candidates"][0]["step"] == 2,
       "invalid first, valid second: %r" % r["candidates"])
  r = solve("c20_verify:a_red", None, {"plan:positive": answers(([bad], 0.98))}, package=pkg)
  need(r["outcome"] == "candidate_not_validated" and r["answer"] == "none" and r["plan"] is None, "all invalid: %r" % r["outcome"])
  r = solve("c20_verify:a_red", None, {"plan:positive": answers(([good], 0.05))}, package=pkg)
  need(r["outcome"] == "not_found" and "below_cutoff" in r["diagnostics"][-1], "below the cutoff: %r" % r["diagnostics"])
  r = solve("c12_step_bounds:base", "Q3", {"plan:positive": answers((["W0"], 1.0))})
  need(r["outcome"] == "goal_already_holds" and r["plan"] == [] and r["answer"] == "Yes", "the empty plan: %r" % r["outcome"])
  bus, ship = ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "bus"], ["move", "Ann 1", "Tallinn 4", "Helsinki 5", "ship"]
  r = solve("x04_witness_scope:without_s1", "Q1", {"plan:positive": answers(([do(bus, ship), "#:Tallinn 4"], 1.0),
                                                                            ([do(bus, ship), "#:Helsinki 5"], 1.0))})
  need(r["outcome"] == "plan_found" and r["witnesses"] == {"X": "Helsinki 5"} and r["candidates"][0]["verdict"] == "invalid",
       "a witness the replay rejects, then the right one: %r" % r["candidates"])
  need(gs.score(r, [q for q in GOLD["x04_witness_scope:without_s1"]["queries"] if q["id"] == "Q1"][0]["expect"])["ok"],
       "x04 Q1 scores against gold with its witness")
  r = solve("c12_step_bounds:base", "Q9", {"plan:positive": answers(([do(["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"])], 1.0))})
  need(r["outcome"] == "candidate_not_validated" and "against the bound" in r["candidates"][0]["reason"],
       "a step bound: %r" % r["candidates"])
  two = do(["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"], ["move", "Ann 1", "Tallinn 3", "Helsinki 4", "ship"])
  a, qa, q = compiled("c12_step_bounds:base", "Q7")
  r = ar.solve_query(a, qa, {"backend": fake({"plan:positive": answers(([two], 1.0))}), "limits": {"seconds": 5}})
  need(r["outcome"] == "plan_found" and "the search covered less than the stated bound (2 < 3)" in r["diagnostics"]
       and gs.score(r, q["expect"])["ok"], "c12 Q7: %r" % r["diagnostics"])
  r = solve("c06_scoped_route:base", "Q2", {})
  need(r["outcome"] == "not_found" and r["answer"] == "none" and "bounded non-discovery" in r["diagnostics"][0],
       "no candidate: %r" % r["diagnostics"])
  print("  discovery: an invalid first candidate does not hide a valid second; all invalid is candidate_not_validated; "
        "a below-cutoff plan is not_found; the empty plan; a wrong witness and a step bound are checked by the replay; "
        "the search-coverage record; no candidate is a bounded non-discovery")


def check_state():
  r = solve("c09_inconsistent_states:empty_and_holding", "Q1", {"plan:positive": answers((["W0"], 1.0))})
  e = [q for q in GOLD["c09_inconsistent_states:empty_and_holding"]["queries"] if q["id"] == "Q1"][0]["expect"]
  need(r["outcome"] == "inconsistent_action_state" and gs.score(r, e)["ok"], "c09 empty and holding: %r" % r["outcome"])
  r = solve("c09_inconsistent_states:two_held", "Q1", {"q:positive": yes()})
  e = [q for q in GOLD["c09_inconsistent_states:two_held"]["queries"] if q["id"] == "Q1"][0]["expect"]
  need(r["outcome"] == "inconsistent_action_state" and gs.score(r, e)["ok"], "c09 two held: %r" % r)
  r = solve("c09_inconsistent_states:replayed_conflict", "Q1",
            {"step1:positive": yes(), "joint:positive": yes(), "final:positive": conflict(), "final:negative": conflict()})
  need(r["outcome"] == "inconsistent_action_state" and r["step"] == 1, "c09 replayed conflict: %r" % r["outcome"])
  print("  state: an inconsistent initial state stops a plan (even an accepted empty plan) and a question; a "
        "conflict after a supplied step stops a verification, whatever the joint answer says")


def check_failures():
  r = solve("c20_verify:a_red", "Q1", {"step1:positive": yes(), "step1:negative": "error"})
  need(r["outcome"] == "prover_error" and r["answer"] is None and r["diagnostics"][0]["launch"] == "negative",
       "a GK error: %r" % r["outcome"])
  saved = ag.EXTRA
  ag.EXTRA = 0
  try:
    r = solve("c18_initial_binding:base", "Q1", {"q:positive": "sleep"}, limits={"seconds": 1})
  finally:
    ag.EXTRA = saved
  need(r["outcome"] == "prover_timeout" and r["answer"] is None, "a timeout: %r" % r["outcome"])
  for case, qid, want in (("c20_verify:a_red", "Q6", "insufficient_search_allowance"),
                          ("c01_unlicensed_polish:base", "Q1", "unsupported_backend_requirement")):
    a, qa, q = compiled(case, qid)
    r = ar.solve_query(a, qa)
    need(r["outcome"] == want and r["calls"]["gk"] == 0 and gs.score(r, q["expect"])["ok"], "%s %s: %r" % (case, qid, r["outcome"]))
  a, qa, _ = compiled("c20_verify:a_red", "Q1")
  a2, qa2, _ = compiled("c20_verify:a_red", "Q4")
  other = ag.run_query(a2, qa2, fake({}), {"seconds": 5})
  try:
    aa.decide(a, qa, other)
    need(False, "evidence of another query was accepted")
  except ar.ArtifactError:
    pass
  a, _, _ = compiled("c03_only_if_red:true", "Q1")
  qc = ar.compile_query(["@id", "QC", ["question", ["can", "hand 1", ["take", "hand 1", "a 2"]]]], a)
  r = ar.solve_query(a, qc)
  need(r["outcome"] == "translation_invalid" and "can_in_query" in r["diagnostics"][0]["errors"] and r["calls"]["gk"] == 0,
       "a query with can: %r" % r["diagnostics"])
  # a -nonegative run decides nothing: refused before a launch, and its evidence is refused (snapshot and discovery)
  for case, qid, table, pkg in (("c03_only_if_red:true", "Q1", {"q:positive": yes()}, None),
                                ("c20_verify:a_red", None, {"plan:positive": answers(([do(["take", "hand 1", "a 2"],
                                  ["put_on", "hand 1", "a 2", "b 3"])], 0.98))}, ["@id", "QP", ["plan", ["is rel2", "on", "a 2", "b 3"]]])):
    a, qa, _ = compiled(case, qid, pkg)
    name = fake(table)
    ledger = {}
    try:
      ar.solve_query(a, qa, {"backend": name, "limits": {"seconds": 5, "flags": ["-nonegative"]}, "ledger": ledger})
      need(False, "%s: solve_query accepted -nonegative" % case)
    except ar.ArtifactError:
      pass
    need(not ledger.get("gk_calls"), "%s: a launch before the refusal" % case)
    flagged = ag.run_query(a, qa, name, {"seconds": 5, "flags": ["-nonegative"]})
    need(any(ev["accepted"] for ev in ag.launches(flagged)), "%s: the diagnostic run found an answer" % case)
    try:
      aa.decide(a, qa, flagged)
      need(False, "%s: decide used -nonegative evidence" % case)
    except ar.ArtifactError:
      pass
  print("  failures: a GK error and a timeout are typed outcomes with no answer; decided queries launch nothing and "
        "score against gold; evidence of another query is rejected; a -nonegative run is refused before a launch and its "
        "evidence is refused, for a snapshot and a discovery")


def check_render():
  for case, qid in (("p01_travel:base", "Q1"), ("p03_food:base", "Q1"), ("x01_identity:introduced_actor", "Q1"),
                    ("x02_open_values:base", "Q1")):
    a, qa, q = compiled(case, qid)
    e = q["expect"]
    r = rp.replay(a, e["plan"], goal=qa["query"]["goal"], **fm.selection(q))
    text = aen.render(a, e["plan"], r["steps"])
    need(text == e["render"], "%s: %r, expected %r" % (case, text, e["render"]))
  need(aen.render(cv.gold_source(GOLD["p01_travel:base"]), []) == "No action is needed: the goal already holds",
       "the empty plan")
  a = cv.gold_source(GOLD["c20_verify:a_red"])
  need(aen.render(a, [["take", "hand 1", "a 2"], ["put_on", "hand 1", "a 2", "b 3"]])
       == "The hand takes block a, then puts block a on block b", "blocks: %r" % aen.render(a, [["take", "hand 1", "a 2"]]))
  print("  render: p01, p03, x01 and x02 give their gold sentences, with a capital first letter and a repeated actor "
        "left out")


def check_score():
  base = {"outcome": "plan_found", "answer": "Yes", "plan": [["take", "h 1", "a 2"]], "diagnostics": [],
          "witnesses": {"X": "b 3"}, "facts": None, "step": None, "confidence": 1.0, "render": "the hand takes block a"}
  rows = [({"outcome": "plan_found"}, True), ({"outcome": "not_found"}, False), ({"not_outcome": ["plan_found"]}, False),
          ({"outcome": "not_found", "alternative": {"outcome": "plan_found"}}, True),
          ({"outcome": "plan_found", "forbidden_outcomes": ["plan_found"]}, False),
          ({"plan": [["take", "h 1", "a 2"]], "reference_shortest_length": 1}, True),
          ({"plan": [["take", "h 1", "b 3"]]}, True), ({"answer": "Yes", "forbidden_answers": ["No"]}, True),
          ({"witness": {"X": "b 3"}}, True), ({"witness": {"X": "c 4"}}, False),
          ({"forbidden_plans": [[["take", "h 1", "a 2"]]]}, False), ({"forbidden_plans": [[["take", "h 1", "c 4"]]]}, True),
          ({"confidence": 0.99}, False), ({"confidence": 1.0}, True),
          ({"confidence": {"layer": "backend", "value": 0.36, "tolerance": 0.005}}, False),
          ({"confidence": {"layer": "backend", "value": 1.0, "tolerance": 0.005, "forbidden": {"value": 1.0}}}, False),
          ({"confidence": {"layer": "backend", "frames_crossed": 1, "per_frame": 0.99}}, False),
          ({"confidence": {"layer": "backend", "frames_crossed": 2, "per_frame": 0.99}}, True),
          ({"confidence": {"layer": "backend", "recorded": True}}, True),
          ({"render": "something else"}, True), ({"entity": "Tartu 5"}, True), ({"no_such_key": 1}, False)]
  for e, ok in rows:
    need(gs.score(base, e)["ok"] == ok, "score %r: %r" % (e, gs.score(base, e)))
  inc = dict(base, outcome="inconsistent_action_state", facts=["empty(hand,W0)", "holding(hand,a,W0)", "isa(block,a)"], step=0)
  need(gs.score(inc, {"outcome": "inconsistent_action_state", "facts": ["empty(hand,W0)", "holding(hand,a,W0)"]})["ok"],
       "conflict facts are a subset")
  sc = gs.score(dict(base, plan=[["take", "h 1", "a 2"]] * 3), {"plan": base["plan"], "reference_shortest_length": 1})
  need(sc["ok"] and sc["info"] == {"same_as_gold_plan": False, "extra_length": 2}, "a longer valid plan: %r" % sc)
  sc = gs.score(base, {"plan": [["take", "h 1", "b 3"]]})
  need(sc["ok"] and sc["info"] == {"same_as_gold_plan": False, "extra_length": 0}, "another valid plan: %r" % sc)
  none = dict(base, outcome="not_found", plan=None, answer="none", witnesses=None)
  need(not gs.score(none, {"plan": base["plan"]})["ok"], "a gold plan needs a found plan")
  need(gs.score(base, {"render": "x"})["info"]["render_exact"] is False and gs.score(base, {"entity": "x"})["not_checked"]["unchecked"]
       == ["entity"] and gs.score(base, {"clauses": {}})["not_checked"]["other_layer"] == {"clauses": "check_action_queries"},
       "render is information; unchecked and other-layer keys are listed")
  refused = dict(base, outcome="unsupported_translation", plan=None,
                 diagnostics=[{"reasons": ["mixed_scope_rule"], "units": ["S2", "S3"]}])
  need(gs.score(refused, {"reason": "mixed_scope_rule", "unit": "S2", "units": ["S2", "S3"]})["ok"]
       and not gs.score(refused, {"unit": "S4"})["ok"], "reason and units of an unsupported result")
  need(gs.score(dict(base, diagnostics=["the search covered less than the stated bound (2 < 3)"]),
                {"record": "search covered less than the stated bound (2 < 3)"})["ok"], "a record")
  print("  score: %d expectation shapes: pinned, forbidden and recorded confidences, forbidden plans, a gold plan "
        "without a found plan, reason, units and record; render, other-layer and unchecked keys reported; an unknown "
        "key fails; another or a longer valid plan is reported, not failed" % (len(rows) + 8))


def run():
  try:
    check_paired()
    check_snapshot()
    check_verify()
    check_negative_side()
    check_discovery()
    check_state()
    check_failures()
    check_render()
    check_score()
  finally:
    while FAKES:
      ag.BACKENDS.pop(FAKES.pop(), None)


if __name__ == "__main__":
  run()
