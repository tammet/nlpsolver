"""The retry stages after the initial attempt, one runner each: the critique pass and its retranslation, the graph
retranslation (`-graphtrans`), the literal bridge (`-litbridge`) and the graph bridge (`-graphbridge`).  The two
fallbacks have their own modules (`fallback_norm.py`, `fallback_hyp.py`).

  run_critic(...)        one critique of the initial translation and, when it finds a blocking error, one rerun
  run_graphtrans(...)    the case translated again into open triples, compiled and proved once
  run_litbridge(...)     invented implications over the case's own atoms, in two rounds
  run_graphbridge(...)   invented implications over the graph translation's names

Each runner returns {"answer", "logic", "proof"?, "gk_command"?}: the answer it reached or None, and the theory and
prover call behind it.  `solve_stages.run_stage` decides whether the answer is adopted.  The run state (the debug
switch, the critic flags) stays in `solve`, which the runners read at call time; the critic's rerun re-enters
`solve.ordinary_attempt`.  `solve` re-exports every name here.
"""
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#-----------------------------------------------------------------

import json

import globals
import llmcall
import prover
from procproofs import process_proof
from solve_display import (announce_stage, loud_enough, print_critic, print_graph_theory, print_graphbridge,
                           print_graphtrans, print_litbridge)
from solve_stages import unresolved


# ---- the critique pass ----

def should_critique_enabled():
  """Whether the critic stage may run at all.

  `run_stage` applies the `unresolved` rule itself, so this must not repeat it,
  but every other part of the old guard still belongs here:

  `critiqued` does double duty.  It is set before the critique runs, so the
  rerun cannot critique itself, and it survives the downstream-error retry loop
  in `english_to_answer`, which used to critique the same case once per
  attempt.  It is a module flag on purpose -- the earlier guard lived in
  `globals.options`, where the routes' own option resolvers deep-copied it and
  rejected it as an unknown key.
  """
  import solve
  if solve.in_critic_rerun or solve.critiqued:
    return False
  return bool(globals.options.get("critic_flag"))


def run_critic(text, s1_json, s2_json, logic, answer, llm, llm_version,
               max_tokens, options, collect=None, loud=False):
  """The critique pass and, when it is earned, one retranslation."""
  import critic_pass
  record = {"ran": True, "answer_before": answer}
  got = critic_pass.critique(text, s1_json, s2_json, llm=llm,
                             version=llm_version)
  report = got.get("report")
  if report is not None:
    # the quoted-fix rule needs the units' own text, so the report is read
    # again with it in hand
    report = critic_pass.parse_reply(got.get("raw"),
                                     critic_pass.unit_texts(s1_json))
    got["report"] = report
  record.update({"report": report, "parse_failure": got.get("parse_failure"),
                 "tokens_estimate": got.get("tokens_estimate"),
                 "system_prompt_sha256": got.get("system_prompt_sha256")})
  verdict, units, stage = critic_pass.decide(report)
  record["verdict"] = verdict
  record["units_to_redo"] = units
  record["stage"] = stage
  out = {"answer": None, "logic": None}
  if verdict != "RETRANSLATE":
    record["why"] = (got.get("parse_failure") or (report or {}).get("reason")
                     or "the critic kept the translation")
    if collect is not None:
      collect["critic"] = record
    if loud:
      print_critic(record)
    return out
  blocking = [f for f in report["findings"] if f["severity"] == "blocking"]
  wanted = blocking or report["findings"]
  wanted, empty = critic_pass.drop_empty_fixes(wanted)
  record["empty_fix"] = empty
  record["compact_fix"] = critic_pass.has_compact_fix(wanted)
  if not wanted:
    record["why"] = "every finding said no change was needed"
    if collect is not None:
      collect["critic"] = record
    if loud:
      print_critic(record)
    return out
  # Stage 1 lost a word: Stage 1 runs again and Stage 2 follows it plainly.
  # A Stage-2 corrective would name unit ids the new Stage 1 may not use.
  if stage == 1:
    s1_corr = critic_pass.corrective_stage1(wanted, s1_json)
    s2_corr = ""
  else:
    s1_corr = ""
    s2_corr = critic_pass.corrective_suffix(wanted, s2_json)
  record["corrective"] = s2_corr or s1_corr
  record["corrective_stage"] = stage
  import solve
  solve.in_critic_rerun = True
  try:
    inner = {}
    with llmcall.tagged(None, critic_rerun=True):
      again = solve.ordinary_attempt(text, options, inner,
                                      stage2_corrective=s2_corr,
                                      stage1_corrective=s1_corr)
    record["answer_after"] = again
    record["rerun_changed_units"] = changed_units(
        s2_json, inner.get("stage2"))
    touched = (set(record["rerun_changed_units"]["changed"])
               | set(record["rerun_changed_units"]["added"]))
    record["touched_units"] = sorted(touched)
    record["unasked_units"] = sorted(touched - set(units))
    record["corrective_call"] = corrective_call(inner, stage)
    if collect is not None:
      # `answered_by` and `fallback` say whether a fallback answered the
      # retranslation: the rerun re-enters the pipeline, so `fallback_norm`
      # and `fallback_hyp` run again on the new Stage 2 (the abstraction
      # routes do not — `route_enabled` refuses inside a rerun).
      record["rerun"] = {k: v for k, v in inner.items()
                         if k in ("stage1", "stage2", "answer",
                                  "answered_by", "fallback")}
    if not unresolved(again):
      out["answer"] = again
      out["rerun_answered_by"] = inner.get("answered_by")
      out["logic"] = inner.get("final_clauses") or logic
      # the rerun's own gk call, for the run's top-level record
      out["proof"] = inner.get("proof")
      out["gk_command"] = inner.get("gk_command")
  except Exception as e:                                        # noqa: BLE001
    record["rerun_error"] = "%s: %s" % (type(e).__name__, e)
  finally:
    solve.in_critic_rerun = False
  if collect is not None:
    collect["critic"] = record
  if loud:
    print_critic(record)
  return out


def corrective_call(inner, stage):
  """Was the call carrying the corrective made, and by whom answered?

  A rerun whose corrective call never happened is the first call again, served
  from the cache; the measurement excludes it.  -> "api" | "cache" | "missing".
  """
  want = 1 if stage == 1 else 2
  rows = [r for r in (inner.get("parse_calls") or [])
          if r.get("stage") == want]
  if not rows:
    return "missing"
  return rows[0].get("source") or "unknown"


def changed_units(before, after):
  """Which `@id` packages the rerun rewrote, and which it touched unasked."""
  import json as _json

  def packages(s2):
    out = {}
    if isinstance(s2, list) and s2 and s2[0] == "and":
      for item in s2[1:]:
        if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
          out[str(item[1])] = _json.dumps(item[2], sort_keys=True,
                                          default=str)
    return out

  a, b = packages(before), packages(after)
  changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
  return {"changed": changed,
          "added": sorted(set(b) - set(a)),
          "removed": sorted(set(a) - set(b))}


# ---- the graph retranslation ----

def run_graphtrans(text, s1_json, s2_json, logic, answer, llm, llm_version,
                   max_tokens, options, loud=False, verbose=False,
                   collect=None, state=None):
  """Layer 1: the graph retranslation and one gk call (`-graphtrans`)."""
  import graph_p0
  announce_stage("graphtrans")
  got = graph_p0.run_graph_p0(text, s1_json, llm=llm, version=llm_version,
                              max_tokens=max_tokens, options=None)
  if state is not None:
    state["graphtrans"] = got
  if collect is not None:
    collect["graphtrans"] = graphtrans_record(got)
  if globals.options.get("debug_print_flag"):
    print_graphtrans(got, verbose=verbose)
  print_graph_theory(got, s1_json, llm)
  if got.get("answer") is None:
    return {"answer": None, "logic": None}
  return {"answer": got["answer_string"], "logic": got["clauses"],
          "proof": got.get("gk_result"), "gk_command": got.get("gk_command")}


def graphtrans_record(got):
  """What a runtests JSON keeps.

  The open-triple Stage 2 and the graph clause list stay: each is the size of
  an ordinary Stage 2 and clause list, and without them the record cannot say
  what was proved.  Only the compiler sidecar and the unparsed result string
  are dropped; `gk_result` carries the same result as JSON.
  """
  return {k: v for k, v in got.items() if k not in ("sidecar", "raw")}


def acceptance(view, collect):
  """EXPERIMENTAL (Task 2B).  Judge a later stage's answer with the proof-local
  acceptance checks and record the verdict.  Returns True when the answer may
  be adopted.  With the option off, every answer is adopted, as before."""
  policy = globals.options.get("accept_policy")
  if not policy:
    return True
  import retrans_accept as _ra
  if view.get("answered_by") not in _ra.JUDGED_STAGES:
    return True                       # only the two stages Task 2B measured
  try:
    import retrans_accept
    rec = retrans_accept.check(view, policy)
  except Exception as exc:                                       # pragma: no cover
    rec = {"decision": "CAUTION", "reasons": ["record_incomplete"],
           "answering_stage": view.get("answered_by"), "used_units": [],
           "changed_units": [], "policy": policy,
           "evidence": {"error": str(exc)[:200]}}
  if collect is not None:
    collect.setdefault("acceptance", []).append(rec)
  ok = rec["decision"] == "ACCEPT"
  if not ok and loud_enough():
    print("--- acceptance (%s): %s %s ---"
          % (policy, rec["decision"], ", ".join(rec["reasons"]) or "-"))
  return ok


# ---- the literal bridge ----

def run_litbridge(text, s1_json, s2_json, logic, answer, llm, llm_version,
                  max_tokens, options, loud=False, verbose=False,
                  collect=None, state=None):
  """The literal bridge, exactly as it ran before the route loop existed.

  The body is the block that used to sit inline in `ordinary_attempt`;
  only its wrapper changed.  It returns the answer it reached, or None when it
  reached none, and the theory that answer rests on.
  """
  debug = globals.options.get("debug_print_flag")
  show_details = globals.options.get("show_details_flag")
  show_logic = globals.options.get("show_logic_flag")
  show_prover = globals.options.get("show_prover_flag")
  import litbridge_procedure
  base_answer, base_logic = answer, logic
  loud = debug or show_details or show_logic
  view = _litbridge_view(text, s1_json, s2_json, logic)
  respond = _litbridge_responder(llm, llm_version, max_tokens)
  extras = bool(litbridge_procedure.EXTRAS)
  records = []
  # the round that answered, for the run's top-level record
  answering_proof, answering_command = None, None
  # accumulated across the rounds, so a round-2 proof can name a round-1 rule
  provenance, rules_by_id = {}, {}
  try:
    ctx, refused = litbridge_procedure.bridge_context(view)
  except Exception as e:                                      # noqa: BLE001
    ctx, refused = None, "%s: %s" % (type(e).__name__, str(e)[:160])
  if ctx is None:
    records.append({"round": 0, "stopped_at": refused, "asked": False,
                    "rules": 0, "clauses": 0, "printed_rules": []})
  for number in (1, 2):
    if ctx is None:
      break
    try:
      extra, rec = litbridge_procedure.bridge_round(
          ctx, view, respond, number, extras=extras)
    except Exception as e:                                    # noqa: BLE001
      rec = {"round": number, "asked": False, "rules": 0, "clauses": 0,
             "printed_rules": [],
             "stopped_at": "%s: %s" % (type(e).__name__, str(e)[:160])}
      extra = []
    records.append(rec)
    # no new rule: nothing is added and gk is not called again
    if not extra:
      break
    logic = list(logic) + extra
    try:
      proof_result = prover.call_prover(logic, s1_json=s1_json)
    except KeyboardInterrupt:
      raise
    except Exception as e:
      return "Error: prover raised an exception: " + str(e)
    if proof_result is None:
      return "Error: prover returned None."
    if show_details or show_prover:
      print("\n=== prover result with the round-%d bridge clauses (JSON) "
            "===\n" % number)
      print(proof_result)
    answer = process_proof(proof_result, text=text, s1_json=s1_json,
                           s2_json=s2_json, logic=logic, options=options)
    rec["gk_called"] = True
    rec["resolved"] = not unresolved(answer)
    provenance.update(rec.get("clause_provenance") or {})
    rules_by_id.update(rec.get("rules_by_id") or {})
    if rec["resolved"] and _litbridge_grader_mode():
      grade = grade_litbridge(text, proof_result, provenance, rules_by_id,
                               respond)
      rec["grading"] = grade
      if grade.get("withdrawn"):
        # the proof rests on a rule the grader failed: the bridge answers
        # nothing and the initial attempt's answer stands
        answer = base_answer
        rec["resolved"] = False
        rec["withdrawn"] = True
        break
    if rec["resolved"]:
      answering_proof = proof_result
      answering_command = (collect or {}).get("gk_command")
      break
  # nothing was proved: the run ends exactly where it would have without
  # litbridge, with the answer and the theory the ordinary pipeline produced
  if unresolved(answer):
    answer, logic = base_answer, base_logic
  if collect is not None:
    collect["litbridge"] = {"extras": extras, "rounds": records,
                            "proved": not unresolved(answer),
                            "grader": _litbridge_grader_mode(),
                            "options": view["configuration"]}
    if not globals.options.get("nofinaltrace"):
      collect["final_clauses"] = logic
  if loud:
    print_litbridge(records, verbose=debug or show_details,
                     options=view["configuration"])
  return {"answer": None if unresolved(answer) else answer, "logic": logic,
          "proof": answering_proof, "gk_command": answering_command}


def _litbridge_grader_mode():
  """The grader's mode, or None when it is off (`litbridge_grader.MODE`)."""
  import litbridge_grader
  return litbridge_grader.MODE


def grade_litbridge(text, proof_result, provenance, rules_by_id, respond):
  """Grade the rules the proof cites, one call each.  -> the grading record.

  Every proof gk returned is graded, and the answer stands only if some proof
  survives.  A proof citing no invented rule is not the bridge's doing and is
  left alone.
  """
  import litbridge_grader as grader
  import litbridge_procedure

  mode = grader.normalise_mode(grader.MODE)

  def ask(rule_id, message):
    got, _note = respond("grader", str(rule_id), message)
    return got

  proofs = litbridge_procedure.proofs_of(proof_result, provenance)
  dynamic = [p for p in proofs if not p["cites_no_dynamic_hypothesis"]]
  if not dynamic:
    return {"asked": False, "mode": mode, "proofs": [],
            "why": "no returned proof cites an invented rule",
            "withdrawn": False}
  rows = []
  for p in dynamic:
    got = grader.grade_proof(text, p["cited_hypothesis_ids"], rules_by_id,
                             ask, mode)
    got["answer"] = p.get("answer")
    rows.append(got)
  graded = [r for r in rows if r["graded"]]
  return {"asked": True, "mode": mode, "proofs": rows,
          "version": grader.VERSION,
          # every proof that cited a rule was withdrawn, so nothing invented
          # is left holding the answer up
          "withdrawn": bool(graded) and all(r["withdrawn"] for r in graded)}


def _litbridge_view(text, s1_json, s2_json, logic):
  """The case as the bridge machinery reads it.

  `configuration` is the run's own option dict, not a label: the theory was
  converted in this process under `globals.options`, so the bridge is
  converted the same way, minus the passes that would strip its `$block`.
  It is captured here, before the first bridge conversion, because a
  conversion scopes `globals.options` while it runs.
  """
  import litbridge_converter
  return {"case_id": "solve", "input_text": text, "stage1": s1_json,
          "stage2": s2_json, "final_clauses": logic,
          "configuration": litbridge_converter.live_options()}


def _litbridge_responder(llm, llm_version, max_tokens):
  """-> respond(role, key, message) -> (text, note), one LLM call per call."""
  import litbridge_procedure

  def respond(role, key, prompt, retry=False):
    sysprompt = litbridge_procedure.prompts.system_prompt()
    if role == "distinct":
      sysprompt = litbridge_procedure.rules.distinct_system_prompt()
    elif role == "negative":
      sysprompt = litbridge_procedure.rules.negative_system_prompt()
    elif role == "grader":
      import litbridge_grader
      sysprompt = litbridge_grader.system_prompt(litbridge_grader.MODE)
    with llmcall.tagged(None, role=role):
      return llmcall.call_llm(sysprompt, prompt, llm=llm, version=llm_version,
                              max_tokens=max_tokens), None
  return respond


# ---- the graph bridge ----

def run_graphbridge(text, s1_json, s2_json, logic, answer, llm, llm_version,
                    max_tokens, options, loud=False, verbose=False,
                    collect=None, state=None):
  """Layer 2: bridges over layer 1's translation (`-graphbridge`).

  Layer 1 must have run: layer 2 searches its theory and never translates the
  case a second time.  When the route order puts `graphbridge` first, layer 1
  is run here, once, and its record is kept for the loop.
  """
  import graph_compile
  import graph_procedure
  import litbridge_converter
  state = state if state is not None else {}
  p0 = state.get("graphtrans")
  if p0 is None:
    got = run_graphtrans(text, s1_json, s2_json, logic, answer, llm,
                          llm_version, max_tokens, options, loud=loud,
                          verbose=verbose, collect=collect, state=state)
    p0 = state.get("graphtrans")
    if got and got.get("answer") is not None:
      return got
  if not p0 or p0.get("stage2_graph") is None:
    return {"answer": None, "logic": None}
  announce_stage("graphbridge")
  base_options = graph_compile.graph_options(litbridge_converter.live_options())
  respond = graphbridge_responder(llm, llm_version, max_tokens)
  gk_log = []
  gk = graph_compile.gk_runner(s1_json, seconds=5, options=base_options,
                               log=gk_log)
  ordinary = None
  if graph_procedure.LIFT:
    ordinary = {"view": _litbridge_view(text, s1_json, s2_json, logic),
                "options": litbridge_converter.live_options(),
                "gk": _graphbridge_ordinary_gk(s1_json, s2_json, text)}
  evidence = str(graph_procedure.EVIDENCE or "any")
  try:
    record = graph_procedure.run_bridges(
        p0["stage2_graph"], s1_json, respond, gk, case_id="solve",
        options=base_options, input_text=text, sources=graphbridge_sources(),
        evidence=evidence, lift=bool(ordinary), ordinary=ordinary)
  except Exception as e:                                        # noqa: BLE001
    record = {"stopped_at": "%s: %s" % (type(e).__name__, str(e)[:200])}
  record["gk_calls"] = gk_log
  record["evidence_mode"] = evidence
  if collect is not None:
    collect["graphbridge"] = record   # the key runtests.py copies
  out = {"answer": None, "logic": None}
  value, verdict = graph_procedure.credible_answer(record, evidence)
  if value is not None:
    row = _graphbridge_minimal_set(record, verdict)
    out["answer"] = _graph_answer_string(value, row)
    out["logic"] = p0.get("clauses")
    out["proof"] = (row or {}).get("gk_result")
    out["gk_command"] = (row or {}).get("gk_command")
    record["answer_label"] = "bridged"
  if globals.options.get("debug_print_flag"):
    print_graphbridge(record, verbose=verbose)
  return out


def _graphbridge_minimal_set(record, verdict):
  """The minimal-set row the accepted verdict was computed from."""
  rows = record.get("minimal_sets") or []
  i = (verdict or {}).get("set_index")
  if isinstance(i, int) and 0 <= i < len(rows):
    return rows[i]
  return None


def _graph_answer_string(value, row):
  """The pipeline's answer string for a bridged answer.

  The replay of the accepted minimal set is an ordinary gk call read by
  `process_proof`, so its answer already carries the hedge and, at `-explain`
  and above, the English proof.  It is used whenever its polarity agrees with
  the accepted verdict's; otherwise the bare polarity stands and the record
  says both.
  """
  bare = "True." if value else "False."
  got = (row or {}).get("answer_string")
  if not isinstance(got, str) or not got.strip():
    return bare
  head = got.split("\n")[0].strip().rstrip(".").lower()
  for hedge in ("probably ", "likely ", "possibly "):
    head = head.replace(hedge, "")
  if head in ("true", "false") and (head == "true") == bool(value):
    return got
  return bare


def graphbridge_sources():
  """The candidate sources this run enumerates."""
  import graph_procedure
  return tuple(graph_procedure.DEFAULT_SOURCES)


def _graphbridge_ordinary_gk(s1_json, s2_json, text):
  """-> a gk callable over the ORDINARY theory, for a lifted world."""
  def call(clauses, stored, tag, seconds=None, dynamic=False):
    import hashlib
    import utils
    try:
      raw = prover.call_prover(clauses, s1_json=s1_json)
    except Exception as e:                                      # noqa: BLE001
      return {"answer": None, "raw": "{}", "gk_input": None,
              "error": "%s: %s" % (type(e).__name__, e),
              "gk_input_sha256": "", "seconds": 0}
    got = process_proof(raw, text=text, s1_json=s1_json, s2_json=s2_json,
                        logic=clauses)
    if isinstance(got, tuple):
      got = got[0]
    try:
      shown = utils.clause_list_to_json_commented(clauses, s1_json=s1_json)
    except Exception:                                           # noqa: BLE001
      shown = None
    return {"answer": got, "raw": raw if isinstance(raw, str)
            else json.dumps(raw), "gk_input": shown,
            "gk_input_sha256": hashlib.sha256(
                (shown or "").encode()).hexdigest(), "seconds": 0}
  return call


def graphbridge_responder(llm, llm_version, max_tokens):
  """-> respond(role, key, message) -> (text, note), one LLM call per call."""
  import graph_judge
  import graph_lift
  import graph_search
  import litbridge_prompts

  def respond(role, key, prompt, retry=False):
    if role == "graph_judge":
      sysprompt = graph_judge.judge_system_prompt(True)
    elif role == "graph_judge_lexical":
      sysprompt = graph_judge.lexical_system_prompt()
    elif role == "graph_holistic":
      sysprompt = graph_judge.holistic_system_prompt()
    elif role == "graph_grader":
      sysprompt = graph_search.grader_system_prompt()
    elif role == "graph_lift":
      sysprompt = litbridge_prompts.system_prompt()
    elif role == "graph_retranslate":
      import llmparse
      if not llmparse._stage2_sysprompt:
        llmparse.load_prompts()
      sysprompt = llmparse._stage2_sysprompt
    else:
      return None, "unknown graph role %r" % role
    with llmcall.tagged(None, role=role):
      return llmcall.call_llm(sysprompt, prompt, llm=llm, version=llm_version,
                              max_tokens=max_tokens), None
  return respond
