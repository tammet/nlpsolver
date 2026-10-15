"""WP12 checks: the GK adapter (`solver/action_gk.py`).

No model call and no GK launch.  Every check calls the production functions: the output records are the gold
records of c25 and ten saved GK outputs (`gk_output/`, compressed copies of archived launches; their sources and
SHA-256 are in SOURCES.sha256), and the launch path runs a fake executable that prints saved output.

  c25           the formal gold records: a rejected entry at 1.0 under 'answer found', a below-cutoff answer, an
                eligible answer, an unrooted non-ground answer, two eligible candidates in GK's order
  output        errors, a timeout, malformed and self-contradicting output, an ignored strategy setting
  answers       non-ground and unrecognized histories, the cutoff boundary, a contrary verdict, a disjunctive
                answer, a -nonegative run
  canonical     alpha-renamed Boolean duplicates are one answer; distinct histories and witnesses stay distinct
  provenance    the reuse guard on C30 overlap and C29.Q2, the shared-source requirement, a clean proof, use counts;
                the confidence status of the entry that supplies the confidence (Sol's review, repair 1)
  confidence    the cutoff 0.10 read literally; NaN, infinity and out-of-range values (Sol's review, repair 2)
  termination   proof, search limit, undetermined, timeout, error; a failed or differing relaunch (repair 3)
  dispatch      backend_unavailable (missing, another hash, not executable, no data folder), a refused requirement
                (also when compile_query was told it is validated), call_limit, a query's own outcome: no launch;
                a profile that is not a registered name is rejected
  launch        run_query on compiled gold queries through a fake executable: launch counts by role, the
                termination relaunch, the ledger, the command, a timeout, an ignored strategy setting, a launch
                that cannot start, one polarity failing while the other proves (`incomplete`)
  isolation     the adapter reads no ordinary pipeline option, prover module or cache
"""

import copy
import gzip
import json
import os
import re
import stat
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_gk as ag
import action_route as ar
import check_action_availability as cav
import check_action_validation as cv
import fixture_materialize as fm
import lc_action_query as lq

need = cav.need
OUT = os.path.join(HERE, "gk_output")
GOLD = {c["case"]: c for c in fm.load_all()}


def saved(name):
  with gzip.open(os.path.join(OUT, name + ".out.gz"), "rt") as f:
    return f.read()


def gold(case, qid, backend=None):
  c = GOLD[case]
  q = [x for x in c["queries"] if x["id"] == qid][0]
  a = cv.gold_source(c)
  qa = ar.compile_query(q["stage2"], a, cv.gold_limits(q), backend, **fm.selection(q))
  return a, qa


def result(answers=(), rejected=(), result="answer found"):
  d = {"result": result}
  if answers:
    d["answers"] = list(answers)
  if rejected:
    d["rejected_answers"] = list(rejected)
  return json.dumps(d)


def plan_answer(term, conf, proof=None):
  a = {"answer": [["$ans", term]], "confidence": conf}
  if proof is not None:
    a["positive proof"] = proof
  return a


PROOF = [[1, ["in", "query:Q:plan:positive", "goal", 1], [["-$defq0", "?:X"], ["$ans", "?:X"]]],
         [2, ["in", "src:S1:initial_fact:0", "axiom", 1], [["p"]]],
         [3, ["mp", 1, 2, "fromgoal", 1], [["$ans", "W0"]]]]


# ---------------------------------------------------------------------------


def check_c25():
  c = GOLD["c25_rejected_answers:base"]
  n = 0
  for q in c["queries"]:
    out = json.dumps(q["gk_output"])
    kind = "boolean" if q["id"] == "Q1" else "discovery"
    # the saved records keep the old layout: s0 was the root.  The rootedness test takes the query's root.
    ex = ag.extract(out, kind=kind, askvars=0 if kind == "boolean" else 1, root="s0")
    want = q["expect"]["eligible_candidates"]
    got = [{"sequence": x["plan"], "confidence": x["confidence"]} for x in ex["candidates"]] if kind == "discovery" \
      else [x for x in ex["candidates"]]
    need(got == want, "c25 %s: candidates %r, gold %r" % (q["id"], got, want))
    need(len(ex["accepted"]) == len(q["gk_output"]["answers"]) and len(ex["rejected"]) == len(q["gk_output"]["rejected_answers"]),
         "c25 %s: every entry of both lists is kept" % q["id"])
    n += 1
  q1 = ag.extract(json.dumps(c["queries"][0]["gk_output"]))
  r = q1["rejected"][0]
  need(q1["result"] == "answer found" and not q1["candidates"] and r["confidence"] == 1.0 and not r["eligible"]
       and r["positive_proof"] == "(omitted)" and r["negative_proof"] == "(omitted)",
       "c25 Q1: the rejected entry at 1.0 is kept with its proofs and is not a candidate")
  q2 = ag.extract(json.dumps(c["queries"][1]["gk_output"]), kind="discovery", askvars=1, root="s0")
  need(q2["accepted"][0]["reasons"] == ["below_cutoff"] and q2["accepted"][0]["confidence"] == 0.05,
       "c25 Q2: the answer at 0.05 is kept, below the cutoff")
  q4 = ag.extract(json.dumps(c["queries"][3]["gk_output"]), kind="discovery", askvars=1, root="s0")
  need(q4["accepted"][0]["reasons"] == ["not_rooted", "not_ground"], "c25 Q4: %r" % q4["accepted"][0]["reasons"])
  # the same Q3 record under a v2 root: its situation is rooted in s0, not in the planning root W0
  q3 = ag.extract(json.dumps(c["queries"][2]["gk_output"]), kind="discovery", askvars=1, root="W0")
  need(not q3["candidates"] and q3["accepted"][0]["reasons"] == ["not_rooted"], "c25 Q3 under root W0: %r" % q3["accepted"])
  # C25 in real output: 'answer found', no accepted entry, three rejected entries at 1.0 with support_against 1.0
  real = ag.extract(saved("C02.Q2.step1.neg"))
  need(real["result"] == "answer found" and not real["accepted"] and not real["candidates"]
       and [e["confidence"] for e in real["rejected"]] == [1.0, 1.0, 1.0]
       and all(e["support_against"] == 1.0 and e["both_proofs"] for e in real["rejected"]),
       "WP10 C02.Q2.step1.neg: rejected entries at 1.0 are diagnostics only")
  print("  c25: %d gold records give their eligible candidates; a rejected entry at 1.0 (also in real output, WP10 "
        "C02.Q2.step1.neg) is never a candidate; the root is the query's" % n)


def check_output():
  good = result([{"answer": True, "confidence": 1.0}])
  cases = [
    ("an error object", dict(stdout='{"error": "json syntax error at line 2"}', exit_code=1), "prover_error"),
    ("a missing input", dict(stdout='{"error": "could not open x.json"}', exit_code=1), "prover_error"),
    ("the external time limit", dict(stdout=good, timed_out=True, exit_code=None), "prover_timeout"),
    ("no JSON", dict(stdout="Segmentation fault", exit_code=139), "prover_error"),
    ("truncated JSON", dict(stdout='{"result": "answer found", "answers": [', exit_code=0), "malformed"),
    ("an ignored strategy setting", dict(stdout="Warning: unknown setting in the strategy:  no_such_setting.\n" + good),
     "backend_incompatible"),
    ("no answers found with an answer", dict(stdout=result([{"answer": True, "confidence": 1.0}], result="no answers found")),
     "malformed"),
    ("no information with an answer", dict(stdout=result([{"answer": True, "confidence": 1.0}], result="no information")),
     "malformed"),
    ("answer found with no entry", dict(stdout=result()), "malformed"),
    ("an unknown result string", dict(stdout=result([{"answer": True, "confidence": 1.0}], result="proof maybe")), "malformed"),
    ("answers not a list", dict(stdout='{"result": "answer found", "answers": {"answer": true}}'), "malformed"),
    ("a nonzero exit", dict(stdout=good, exit_code=2), "prover_error"),
  ]
  for what, kw, status in cases:
    ex = ag.extract(**kw)
    need(ex["status"] == status and not ex["accepted"] and not ex["candidates"],
         "%s: status %s with %d accepted, expected %s with none" % (what, ex["status"], len(ex["accepted"]), status))
  ok = ag.extract(good)
  need(ok["status"] == "completed" and len(ok["candidates"]) == 1, "a clean output: one candidate")
  print("  output: %d error, timeout, malformed and incompatible outputs give no answer entry; a clean one gives one"
        % len(cases))


def check_answers():
  mv = lambda a, b: ["move", "#:Ann 1", a, b, "bus"]
  rows = [
    ("a variable action argument", plan_answer(["$do", ["move", "#:Ann 1", "?:X", "#:Tallinn 3", "bus"], "W0"], 0.9),
     ["not_ground"]),
    ("an unbound predecessor", plan_answer(["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "?:S"], 0.9), ["not_rooted", "not_ground"]),
    ("another root", plan_answer(["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "W1"], 0.9), ["not_rooted"]),
    ("an unknown constructor", plan_answer(["$do", ["fly", "#:Ann 1", "#:Tallinn 3"], "W0"], 0.9), ["unrecognized_action"]),
    ("a wrong arity", plan_answer(["$do", ["take", "#:Ann 1"], "W0"], 0.9), ["unrecognized_action"]),
    ("below the cutoff", plan_answer(["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "W0"], 0.0999), ["below_cutoff"]),
    ("at the cutoff", plan_answer(["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "W0"], 0.1, PROOF), []),
    ("a disjunctive answer", {"answer": [["$ans", "W0"], ["$ans", ["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "W0"]]],
                              "confidence": 0.9}, ["disjunctive_answer"]),
    ("the empty plan", plan_answer("W0", 1.0, PROOF), []),
  ]
  for what, a, reasons in rows:
    ex = ag.extract(result([a]), kind="discovery", askvars=1, root="W0")
    e = ex["accepted"][0]
    need(e["reasons"] == reasons and e["eligible"] == (not reasons) and len(ex["candidates"]) == (0 if reasons else 1),
         "%s: reasons %r, expected %r" % (what, e["reasons"], reasons))
  empty = ag.extract(result([plan_answer("W0", 1.0, PROOF)]), kind="discovery", askvars=1, root="W0")
  need(empty["candidates"][0]["plan"] == [], "the empty plan is a candidate of length zero")
  at = ag.extract(result([plan_answer(["$do", mv("#:Haapsalu 2", "#:Tallinn 3"), "W0"], 0.1, PROOF)]),
                  kind="discovery", askvars=1, root="W0")
  need(at["candidates"][0]["plan"] == [["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"]], "source spelling")
  contrary = ag.extract(result([{"answer": False, "confidence": 1.0}]))
  need(contrary["accepted"][0]["reasons"] == ["contrary_verdict"] and not contrary["candidates"],
       "a contrary verdict on the question asked is not a candidate for it")
  ask = ag.extract(result([{"answer": [["$ans", "?:X"]], "confidence": 1.0}]), kind="ask", askvars=1)
  need(ask["accepted"][0]["reasons"] == ["not_ground"], "an ask answer with a variable: %r" % ask["accepted"][0]["reasons"])
  noneg = ag.extract(saved("X04.Q1"), kind="discovery", askvars=2, root="W0", candidates_only=True)
  need(not noneg["candidates"] and noneg["accepted"][0]["reasons"] == ["nonegative_run"], "a -nonegative run gives no candidate")
  print("  answers: %d answer shapes classified (non-ground, unrooted, unknown action, cutoff 0.10 inclusive, "
        "disjunctive, empty plan); a contrary verdict, a variable ask answer and a -nonegative run are not candidates"
        % len(rows))


def check_canonical():
  dup = ag.extract(saved("C02.Q2.pos"))
  need(len(dup["accepted"]) == 2 and len(dup["candidates"]) == 1 and dup["candidates"][0]["entries"] == [0, 1]
       and dup["candidates"][0]["confidences"] == [1.0, 0.99] and dup["candidates"][0]["confidence"] == 1.0,
       "C02.Q2.pos: two alpha-renamed Boolean answers are one candidate with both entries")
  need([e["answer"] for e in dup["accepted"]] == [[["$ans", "?:X3", "$obj"]], [["$ans", "?:Z3", "$obj"]]],
       "the raw answers stay as GK gave them")
  food = ag.extract(saved("D.food"), kind="discovery", askvars=1, root="W0")
  plans = [c["plan"] for c in food["candidates"]]
  need(len(food["accepted"]) == 6 and len(plans) == 6 and len({json.dumps(p) for p in plans}) == 6,
       "D.food: six distinct action histories are six candidates")
  need([c["confidence"] for c in food["candidates"]] == [0.9703, 0.951, 0.9606, 0.951, 0.9227, 0.9321],
       "D.food: candidates keep GK's order and confidences")
  x04 = ag.extract(saved("X04.Q1"), kind="discovery", askvars=2, root="W0")
  need(len(x04["candidates"]) == 1 and x04["candidates"][0]["witnesses"] == ["Helsinki 5"]
       and len(x04["candidates"][0]["plan"]) == 2, "X04.Q1: the plan with its reported witness")
  two = ag.extract(result([{"answer": [["$ans", "#:a 2"]], "confidence": 1.0, "positive proof": PROOF},
                           {"answer": [["$ans", "#:b 3"]], "confidence": 0.9, "positive proof": PROOF},
                           {"answer": [["$ans", "#:a 2"]], "confidence": 0.8, "positive proof": PROOF}]),
                   kind="ask", askvars=1)
  need([c["answer"] for c in two["candidates"]] == [["a 2"], ["b 3"]] and two["candidates"][0]["entries"] == [0, 2],
       "an ask: distinct witnesses stay distinct, a repeated one joins its candidate")
  alpha = ag.extract(result([plan_answer(["$do", ["take", "#:h 1", "#:a 2"], "W0"], 0.9, PROOF),
                             plan_answer(["$do", ["take", "#:h 1", "#:a 2"], "W0"], 0.7, PROOF)]),
                     kind="discovery", askvars=1, root="W0")
  need(len(alpha["candidates"]) == 1 and alpha["candidates"][0]["confidence"] == 0.9, "one history twice is one candidate")
  need(ag.canonical_term(["f", "?:X3", ["g", "?:Y1", "?:X3"]]) == ["f", "?:_1", ["g", "?:_2", "?:_1"]], "canonical_term")
  print("  canonical: alpha-renamed Boolean answers are one candidate (C02.Q2.pos); six food histories stay six; "
        "a witness is reported; repeated asks and histories join")


def check_provenance():
  ov = ag.extract(saved("C30.overlap.pos"))
  c = ov["candidates"][0]
  need(c["confidence"] == 0.84 and c["confidence_status"] == "experimental"
       and c["experimental_reasons"] == ["uncertain_evidence_reused"]
       and ov["accepted"][0]["reuse"] == [{"unit": "S3", "clauses": {"src:S3:availability:6": 1, "src:S3:availability:5": 1}}],
       "C30 overlap: two paths of one uncertain unit give an experimental 0.84: %r" % c)
  c29 = ag.extract(saved("C29.Q2"), kind="discovery", askvars=1, root="W0",
                   experimental_units=[("shared_source_confidence_unmet", ["S4"])])
  c = c29["candidates"][0]
  need(c["confidence"] == 0.1296 and c["experimental_reasons"] == ["shared_source_confidence_unmet", "uncertain_evidence_reused"]
       and c29["accepted"][0]["reuse"] == [{"unit": "S4", "clauses": {"src:S4:availability:4": 4}}],
       "C29.Q2: one path used four times, and the recorded requirement: %r" % c)
  clean = ag.extract(saved("C30.Q1.pos"))
  need(clean["candidates"][0]["confidence"] == 0.6 and clean["candidates"][0]["confidence_status"] == "validated",
       "C30 Q1: one path used once gives a validated 0.6")
  other = ag.extract(saved("C30.Q1.pos"), experimental_units=[("shared_source_confidence_unmet", ["S9"])])
  need(other["candidates"][0]["confidence_status"] == "validated", "a requirement on another unit does not mark this proof")
  omitted = ag.extract(result([{"answer": True, "confidence": 1.0, "positive proof": "(omitted)"}]))
  need(omitted["candidates"][0]["experimental_reasons"] == ["provenance_unchecked"], "no proof steps: provenance unchecked")
  # use counts: step 2 feeds step 3, which two children use; the final step reaches step 2 twice
  dag = [[1, ["in", "src:S1:availability:0", "axiom", 0.6], [["p"]]], [2, ["in", "g", "goal", 1], [["-p"]]],
         [3, ["mp", 2, 1, "fromgoal", 0.6], [["q"]]], [4, ["mp", 3, 3, "fromgoal", 0.36], [["r"]]],
         [5, ["simp", 4, [3, 1], "fromgoal", 0.36], [["$ans"]]]]
  need(ag.use_counts(dag) == {5: 1, 4: 1, 3: 3, 2: 3, 1: 3}, "use counts: %r" % ag.use_counts(dag))
  need(ag.evidence_reuse(dag) == [{"unit": "S1", "clauses": {"src:S1:availability:0": 3}}], "reuse through a shared child")
  names = {"src:S1:availability:0": {"unit": "S1", "units": None, "role": "availability", "confidence": None}}
  need(ag.evidence_reuse(dag, names) == [], "a certain clause is never reused evidence")
  # repair 1: the confidence and its status come from the same proof
  bool_entry = lambda conf, proof: {"answer": [["$ans", "?:X%d" % int(conf * 100), "$obj"]], "confidence": conf,
                                    "positive proof": proof}
  rows = [("a clean 1.0 and a reused 0.36", [bool_entry(1.0, PROOF), bool_entry(0.36, dag)], 1.0, "validated", 0, []),
          ("a reused 1.0 and a clean 0.36", [bool_entry(1.0, dag), bool_entry(0.36, PROOF)], 1.0, "experimental", 0,
           ["uncertain_evidence_reused"]),
          ("0.9 reused, 0.9 clean", [bool_entry(0.9, dag), bool_entry(0.9, PROOF)], 0.9, "validated", 1, []),
          ("0.9 reused twice", [bool_entry(0.9, dag), bool_entry(0.9, dag)], 0.9, "experimental", 0,
           ["uncertain_evidence_reused"])]
  for what, entries, conf, status, entry, reasons in rows:
    c = ag.extract(result(entries))["candidates"]
    need(len(c) == 1 and c[0]["confidence"] == conf and c[0]["confidence_status"] == status
         and c[0]["confidence_entry"] == entry and c[0]["experimental_reasons"] == reasons
         and [x["confidence_status"] for x in c[0]["entry_status"]] == [
           "experimental" if e["positive proof"] is dag else "validated" for e in entries],
         "%s: %r" % (what, c))
  print("  provenance: C30 overlap 0.84 and C29.Q2 0.1296 are experimental; C30 Q1 0.6 is validated; a tree reading "
        "counts a clause used through a shared child; a candidate's confidence status is that of the entry that "
        "supplies its confidence (%d cases)" % len(rows))


def check_confidence():
  """Sol's review, repair 2: the cutoff is 0.10 exactly; a confidence that is not a finite number in [0, 1] is
  malformed, never a candidate."""
  rows = [(0.0999999995, ["below_cutoff"]), (0.1, []), (0.10000001, []), (1.0, []), (0.0, ["below_cutoff"]),
          (float("nan"), ["malformed_confidence"]), (float("inf"), ["malformed_confidence"]),
          (float("-inf"), ["malformed_confidence"]), (-0.2, ["malformed_confidence"]), (1.5, ["malformed_confidence"]),
          ("0.9", ["malformed_confidence"]), (True, ["malformed_confidence"]), (None, ["malformed_confidence"])]
  for conf, reasons in rows:
    ex = ag.extract(result([{"answer": True, "confidence": conf, "positive proof": PROOF}]))
    e = ex["accepted"][0]
    need(e["reasons"] == reasons and len(ex["candidates"]) == (0 if reasons else 1),
         "confidence %r: reasons %r, expected %r" % (conf, e["reasons"], reasons))
  # the JSON text GK would print: NaN and Infinity parse, and are still not candidates
  for text in ('{"result": "answer found", "answers": [{"answer": true, "confidence": NaN}]}',
               '{"result": "answer found", "answers": [{"answer": true, "confidence": Infinity}]}'):
    ex = ag.extract(text)
    need(not ex["candidates"] and ex["accepted"][0]["reasons"] == ["malformed_confidence"], "%s: %r" % (text, ex["accepted"]))
  print("  confidence: %d values: below 0.10 by any margin is below the cutoff, 0.10 is eligible; NaN, infinity, "
        "values outside [0, 1], strings, Booleans and null are malformed" % (len(rows) + 2))


def check_termination():
  base = {"timed_out": False, "relaunch": None}
  proof = ag.extract(result([{"answer": True, "confidence": 1.0}]))
  none = ag.extract(result(result="no answers found"))
  bad = ag.extract('{"error": "x"}', exit_code=1)
  limit = "= phase 1: searching for positive evidence =\n<- nothing proved (search limit reached)\n" \
          '{"result": "no answers found"}'
  finished = "= phase 1: searching for positive evidence =\n<- nothing proved\n" + '{"result": "no answers found"}'
  found = '= phase 1 =\n<- found: p\n{"result": "answer found",\n"answers": [\n{\n"answer": true, "confidence": 1.0}\n]}'
  relaunch = lambda *a, **k: dict(base, relaunch=ag.relaunch_record(*a, **k))
  rows = [(base, proof, "proof"),
          (relaunch(limit, "", 0, False), none, "search_limit"),
          (relaunch(finished, "", 0, False), none, "undetermined"),
          (relaunch(limit, "", 2, False), none, "diagnostic_error"),
          (relaunch(limit, "", None, True), none, "diagnostic_error"),
          (relaunch("", "", None, False, "PermissionError: denied"), none, "diagnostic_error"),
          (relaunch("<- nothing proved (search limit reached)\nSegmentation fault", "", 139, False), none, "diagnostic_error"),
          (relaunch(found, "", 0, False), none, "diagnostic_differs"),
          (base, none, "not_diagnosed"),
          (dict(base, timed_out=True), ag.extract("", timed_out=True), "timeout"),
          (base, bad, "error")]
  for rec, ex, want in rows:
    need(ag.termination(rec, ex) == want, "termination %r, expected %s" % (ag.termination(rec, ex), want))
  below = ag.extract(saved("P_cyclic_small_control"))
  need(below["result"] == "evidence below limit" and below["accepted"][0]["reasons"] == ["below_cutoff"]
       and ag.termination(base, below) == "proof" and ag.prerequisite_status(below) == "contested",
       "the prerequisite control: an accepted entry at 0.0 is below the cutoff; its status is contested")
  need(ag.relaunch_record(found, "", 0, False)["accepted"] == 1, "a -printlevel output: the result object after the "
       "search lines, with lines inside it that open with {")
  print("  termination: proof, search_limit, undetermined, timeout, not_diagnosed and error; a relaunch that fails "
        "(exit, timeout, no start, no result) is diagnostic_error, one that finds an answer is diagnostic_differs; an "
        "accepted entry below the cutoff still ends the search")


FAKES = []


def fake_backend(tmp, mode, **overrides):
  """A fake executable, registered as a build for this check; returns its name.  `mode` picks its output: the saved
  output of a proved Boolean, no answer (with the search-limit line under -printlevel), a sleep, an ignored strategy
  setting, or an error for a negative question.  `overrides` change the profile after the file is written."""
  path = os.path.join(tmp, "fake_prover_%s" % mode)
  proved = saved("C30.Q1.pos").replace("\\", "\\\\").replace("'", "\\'")
  with open(path, "w") as f:
    f.write("#!%s\nimport sys, time\n" % sys.executable)
    f.write("mode = %r\nargs = sys.argv[1:]\n" % mode)
    f.write("if mode == 'sleep':\n  time.sleep(5)\n")
    f.write("if mode == 'negfail' and ':negative' in open(args[4]).read():\n"
            "  print('{\"error\": \"a failure of the negative question\"}')\n  sys.exit(1)\n")
    f.write("if mode == 'none':\n")
    f.write("  if '-printlevel' in args:\n    print('= phase 1: searching =')\n    print('<- nothing proved (search limit reached)')\n")
    f.write("  print('{\"result\": \"no answers found\"}')\n")
    f.write("elif mode == 'warn':\n  print('Warning: unknown setting in the strategy:  no_such_setting.')\n"
            "  sys.stdout.write('''%s''')\n" % proved)
    f.write("else:\n  sys.stdout.write('''%s''')\n" % proved)
  os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
  p = ag.backend_profile()
  name = "fake_%s_%d" % (mode, len(FAKES))
  p.update(name=name, path=path, sha256=ag.sha256_file(path), datafolder=tmp)
  p.update(overrides)
  ag.BACKENDS[name] = p
  FAKES.append(name)
  return name


def forget_fakes():
  while FAKES:
    ag.BACKENDS.pop(FAKES.pop(), None)


def check_dispatch():
  a, qa = gold("c20_verify:a_red", "Q1")
  tmp = tempfile.mkdtemp()
  # no hash check: a registered build runs whatever binary is at its path, and its profile names that binary's hash
  other = fake_backend(tmp, "proved", sha256="0" * 64)
  need(ag.backend_profile(other)["sha256"] == ag.sha256_file(ag.BACKENDS[other]["path"]),
       "the profile records the hash of the binary at the path")
  need(ag.availability(ag.backend_profile(other)) is None, "a binary with another hash is available")
  for over, reason in (({"path": os.path.join(tmp, "nothing")}, "binary_missing"),
                       ({"datafolder": os.path.join(tmp, "no_folder")}, "datafolder_missing")):
    e = ag.run_query(a, qa, fake_backend(tmp, "proved", **over))
    need(e["outcome"]["outcome"] == "backend_unavailable" and e["outcome"]["reason"] == reason and e["calls"]["gk"] == 0,
         "%s: %r" % (reason, e["outcome"]))
  locked = fake_backend(tmp, "locked")
  os.chmod(ag.BACKENDS[locked]["path"], 0o644)
  e = ag.run_query(a, qa, locked)
  need(e["outcome"]["reason"] == "binary_not_executable" and e["calls"]["gk"] == 0, "not executable: %r" % e["outcome"])
  for bad in (dict(ag.BACKENDS[locked]), "no_such_build", 3):
    try:
      ag.run_query(a, qa, bad)
      need(False, "a backend %r that is not a registered name was accepted" % type(bad).__name__)
    except ag.AdapterError:
      pass
  name = fake_backend(tmp, "proved")
  fake = ag.BACKENDS[name]
  e = ag.run_query(a, qa, name, {"max_launches": 13})
  need(e["outcome"]["outcome"] == "call_limit" and e["planned"] == {"main": 7, "worst": 14} and e["calls"]["gk"] == 0,
       "call_limit before any launch: %r" % e["outcome"])
  # c01 Q1 needs negative persistence.  compile_query stops it; told that the capability is validated, it compiles,
  # and the adapter still refuses it for a build that does not validate it
  c01 = GOLD["c01_unlicensed_polish:base"]
  q = [x for x in c01["queries"] if x["id"] == "Q1"][0]
  src = cv.gold_source(c01)
  stopped = ar.compile_query(q["stage2"], src, cv.gold_limits(q))
  need(stopped["outcome"]["outcome"] == "unsupported_backend_requirement", "compile_query stops c01 Q1")
  e = ag.run_query(src, stopped, name)
  need(e["outcome"]["outcome"] == "unsupported_backend_requirement" and e["calls"]["gk"] == 0, "the query's outcome passes")
  claimed = ar.compile_query(q["stage2"], src, cv.gold_limits(q), {"validated": [lq.NEGATIVE_PERSISTENCE]})
  need(claimed["outcome"] is None, "a caller's claim lets compile_query write the obligations")
  e = ag.run_query(src, claimed, name)
  need(e["outcome"]["outcome"] == "unsupported_backend_requirement"
       and e["outcome"]["reason"] == "negative_persistence_unavailable" and e["calls"]["gk"] == 0,
       "the adapter checks the build, not the caller's claim: %r" % e["outcome"])
  # a capability counts only for the build, the library identity and the strategy it was validated with
  lib = src["library"]
  rec = {"capability": lq.NEGATIVE_PERSISTENCE, "binary_sha256": fake["sha256"], "library": lib,
         "strategy_sha256": ag.profile_strategy_sha256(fake), "evidence": "test"}
  need(ag.capability(dict(fake, validated=[rec]), lq.NEGATIVE_PERSISTENCE, lib)["validated"], "a matching record")
  for k, v in (("binary_sha256", "1" * 64), ("library", dict(lib, version="9")), ("strategy_sha256", "2" * 64)):
    need(not ag.capability(dict(fake, validated=[dict(rec, **{k: v})]), lq.NEGATIVE_PERSISTENCE, lib)["validated"],
         "a record for another %s does not count" % k)
  need(ag.capability(fake, "some_new_capability", lib)["policy"] == "refuse", "an unknown capability is refused")
  for o in ("backend_unavailable", "backend_incompatible", "unsupported_backend_requirement", "call_limit",
            "prover_error", "prover_timeout"):
    need(o in ar.OUTCOMES, "%s is a route outcome" % o)
  print("  dispatch: backend_unavailable (missing, another hash, not executable, no data folder), call_limit, the "
        "query's own outcome and a refused requirement (also after a caller's claim) launch nothing; only a registered "
        "name selects a build; a capability is keyed to build, library and strategy")


def check_launch():
  tmp = tempfile.mkdtemp()
  ledger = {}
  # a verify query with two steps: steps, final and joint, each polarity a launch
  a, qa = gold("c20_verify:a_red", "Q1")
  e = ag.run_query(a, qa, fake_backend(tmp, "proved"), {"seconds": 5}, ledger)
  need(e["outcome"] is None and e["calls"]["gk"] == 7
       and e["calls"]["by_role"] == {"step:positive": 2, "step:negative": 2, "final:positive": 1, "final:negative": 1,
                                     "joint:positive": 1},
       "c20 Q1 through the fake: %r" % e["calls"])
  need([len(x["candidates"]) for x in ag.launches(e)] == [1] * 7 and all(x["termination"] == "proof" for x in ag.launches(e)),
       "every launch of the fake proves its question")
  need(e["obligations"][1]["requires_prefix"] == 1 and e["joint"]["obligation"] == "joint", "prefix fields kept")
  need(len(ledger["gk_calls"]) == 7 and all(c["stage"] == "actions" for c in ledger["gk_calls"]), "the ledger has 7 calls")
  cmd = e["obligations"][0]["positive"]["command"]
  need(cmd[1:3] == ["-strategytext", json.dumps(ag.PLANNING_STRATEGY)] and cmd[3:6] == ["-seconds", "5", "<input>"]
       and cmd[6:11] == ag.PIPELINE_PARAMS and "axioms_std.js" not in " ".join(cmd) and cmd.count("-strategytext") == 1
       and "-strategy" not in cmd, "the command: %r" % cmd)
  # the keys of the plan search go only to the positive discovery launch
  prof = ag.backend_profile()
  for role, want in (("discovery:positive", dict(ag.PLANNING_STRATEGY, **ag.DISCOVERY_KEYS)),
                     ("discovery:negative", ag.PLANNING_STRATEGY), ("snapshot:positive", ag.PLANNING_STRATEGY),
                     ("step:negative", ag.PLANNING_STRATEGY), (None, ag.PLANNING_STRATEGY)):
    c = ag.command(prof, "<input>", 5, role=role)
    need(json.loads(c[2]) == want, "the strategy of the role %s: %r" % (role, c[2]))
  # the input bytes are the query_input objects in the archive serialization
  objs = ar.query_input(a, qa, "step1", "positive")
  import hashlib
  need(e["obligations"][0]["positive"]["input_sha256"] == hashlib.sha256(ag.input_text(objs).encode()).hexdigest(),
       "the launch's input hash")
  # no answer: one termination relaunch per launch, counted under its own role
  a2, qa2 = gold("c18_initial_binding:base", "Q1")
  e = ag.run_query(a2, qa2, fake_backend(tmp, "none"), {"seconds": 5}, ledger)
  need(e["calls"]["by_role"] == {"snapshot:positive": 1, "snapshot:negative": 1, "termination": 2}
       and all(x["termination"] == "search_limit" for x in ag.launches(e)), "c18 Q1 without answers: %r" % e["calls"])
  e = ag.run_query(a2, qa2, fake_backend(tmp, "none"), {"seconds": 5, "termination": False})
  need(e["calls"]["gk"] == 2 and all(x["termination"] == "not_diagnosed" for x in ag.launches(e)), "no relaunch when off")
  # an ask and a discovery run the positive question only
  a3, qa3 = gold("c18_initial_binding:base", "Q5")
  need([(x[0], x[1]) for x in ag.planned_launches(qa3)] == [("q", "positive")], "an ask: one launch")
  a4, qa4 = gold("x04_witness_scope:without_s1", "Q1")
  need([(x[0], x[1], x[3].get("@askvars")) for x in ag.planned_launches(qa4)] == [("plan", "positive", 2)],
       "a discovery: one launch with the plan and the witness reported")
  a5, qa5 = gold("c20_verify:base", "Q5")
  need([(x[0], x[1], x[2]) for x in ag.planned_launches(qa5)] == [("final", "positive", "snapshot"),
                                                                   ("final", "negative", "snapshot")],
       "an empty supplied sequence: the final question at the root, both polarities, no joint question")
  # an ignored strategy setting stops the query after its first launch
  e = ag.run_query(a, qa, fake_backend(tmp, "warn"), {"seconds": 5})
  need(e["outcome"]["outcome"] == "backend_incompatible" and e["calls"]["gk"] == 1, "backend_incompatible: %r" % e["outcome"])
  # the external limit
  saved_extra = ag.EXTRA
  ag.EXTRA = 0
  try:
    e = ag.run_query(a2, qa2, fake_backend(tmp, "sleep"), {"seconds": 1})
  finally:
    ag.EXTRA = saved_extra
  need(all(x["status"] == "prover_timeout" and x["termination"] == "timeout" and not x["candidates"] for x in ag.launches(e)),
       "a timeout gives no answer")
  # kept files
  keep = os.path.join(tmp, "keep")
  ag.run_query(a2, qa2, fake_backend(tmp, "proved"), {"seconds": 5, "keep": keep})
  need(sorted(os.listdir(keep)) == ["Q1.q.negative.err", "Q1.q.negative.input.json", "Q1.q.negative.out",
                                    "Q1.q.positive.err", "Q1.q.positive.input.json", "Q1.q.positive.out"],
       "kept inputs and outputs: %r" % sorted(os.listdir(keep)))
  # a launch that cannot start: availability passed, then the data folder went away
  gone = os.path.join(tmp, "gone")
  os.makedirs(gone)
  late = fake_backend(tmp, "proved", datafolder=gone)
  os.rmdir(gone)
  real_availability = ag.availability
  ag.availability = lambda profile: None
  try:
    e = ag.run_query(a2, qa2, late, {"seconds": 5})
  finally:
    ag.availability = real_availability
  need(e["outcome"]["outcome"] == "backend_unavailable" and e["outcome"]["reason"] == "launch_failed"
       and e["incomplete"][0]["status"] == "launch_failed", "a launch that cannot start: %r" % e["outcome"])
  # one polarity fails while the other proves: the record lists the failed launch; the outcome stays for the policy
  e = ag.run_query(a2, qa2, fake_backend(tmp, "negfail"), {"seconds": 5})
  q = e["obligations"][0]
  need(e["outcome"] is None and q["positive"]["candidates"] and q["negative"]["status"] == "prover_error"
       and q["negative"]["termination"] == "error"
       and e["incomplete"] == [{"launch": "q:negative", "status": "prover_error", "error": "a failure of the negative question"}],
       "one failed polarity: %r" % e["incomplete"])
  print("  launch: a two-step verify is 7 launches by role; no answer adds one counted termination relaunch; asks and "
        "discoveries are positive only; an ignored setting stops the query; a timeout gives no answer; a launch that "
        "cannot start is backend_unavailable; a failed polarity is listed as incomplete")


def check_isolation():
  text = open(os.path.join(HERE, "..", "..", "solver", "action_gk.py")).read()
  code = re.sub(r'"""[\s\S]*?"""', "", text)
  names = {a or b for a, b in re.findall(r"^import (\S+)|^from (\S+)", code, re.M)}
  # contextlib and fcntl: the lock that keeps the route's GK launches serial across processes; digests: the hashes
  need(names <= {"contextlib", "copy", "fcntl", "hashlib", "json", "math", "os", "re", "shutil", "subprocess",
                 "tempfile", "time", "action_route", "digests", "lc_action",
                 "lc_action_query", "lc_action_situate"}, "the adapter imports %s" % sorted(names))
  need("options" not in code and "axioms_std" not in code and "cache" not in code.replace("no cache", ""),
       "the adapter reads no pipeline option, standard axioms or cache")
  print("  isolation: the adapter imports no prover, globals or cache module and reads no pipeline option")


def run():
  try:
    check_c25()
    check_output()
    check_answers()
    check_canonical()
    check_provenance()
    check_confidence()
    check_termination()
    check_dispatch()
    check_launch()
    check_isolation()
  finally:
    forget_fakes()


if __name__ == "__main__":
  run()
