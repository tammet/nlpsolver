#!/usr/bin/env python3

# LLM-based English-to-answer pipeline.
#
# Primary entry point: english_to_answer(text, options=None)
# Can also be called from the command line.
#
# Pipeline:
#   English text
#     -> llmparse.parse_text()         [two-stage LLM: English -> ASUs -> logic JSON]
#     -> logconvert.rawlogic_convert() [improve/adjust the logic; currently pass-through]
#     -> prover.call_prover()          [gk theorem prover]
#     -> procproofs.process_proof()    [post-process proof result; currently pass-through]
#     -> answer string
#
# LLM calls are cached by default (keyed on provider, version, all call
# parameters, sysprompt and input text).  Use -nollmcache to disable.
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------

import sys
import re
import json
import signal
import threading
import pretty

# ==== import other source files ====

# configuration and globals (also puts 'options' into this module's namespace)
from globals import *
import globals

# two-stage LLM parser: English -> ASUs -> logic
import llmparse
import llmcall

# logic improvement (stub: pass-through until real logic-convert rules are added)
from logconvert import rawlogic_convert
import lc_encoding

# proof post-processing (stub: pass-through until answer extraction is implemented)
from procproofs import process_proof

# semantic normalisation of GK clauses
import semnormalize
import unicodedata

# gk theorem prover caller
import prover


def _ascii_fold_logic(obj):
  """Recursively transliterate every string in a parsed-logic structure to plain
  ASCII (NFKD decompose, drop combining marks, drop any remaining non-ASCII).
  Keeps the prover input pure ASCII so its ASCII-decoded output never crashes on
  accented entity names.  No-op for already-ASCII input; returns None unchanged."""
  if obj is None:
    return None
  if isinstance(obj, str):
    s = unicodedata.normalize("NFKD", obj)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.encode("ascii", "ignore").decode("ascii")
  if isinstance(obj, list):
    return [_ascii_fold_logic(x) for x in obj]
  if isinstance(obj, dict):
    return {_ascii_fold_logic(k): _ascii_fold_logic(v) for k, v in obj.items()}
  return obj

# cache utilities
import cache


# ======== configuration ========

# Print pipeline stages and intermediate results to stdout
debug = False

# LLM provider / version overrides passed through to llmparse / llmcall.
# None means use the defaults configured in llmparse.py / llmcall.py.
llm         = None   # "gpt" | "claude" | "gemini" | "deepseek" | None
llm_version = None   # model version string, or None for default
max_tokens  = None   # int, or None for default


# ======== main pipeline ========



def main(): 
  """
  logic=[
{"@logic": ["isa","car","car 2"],
 "@name": "sent_S1"},
{"@logic": ["have","John 1","car 2"],
 "@name": "sent_S2"},
{"@logic": ["isa","person","John 1"],
 "@name": "sent_S3"}, 
{"@question": ["exists",["?:X"],["and",["isa","person","?:X"],["isa","car","?:Y"],["have","?:X","?:Y"]],
 "@name": "sent_S4"}
  ]

  r=prover.call_prover(logic)
  print(r)
  sys.exit(0)
  """
  text, opts = _parse_cmd_line()
  if opts.get("clearcache_flag"):
    counts = cache.clear_all_caches()
    print("Cache cleared: {:d} LLM, {:d} proof, {:d} parse entries removed.".format(
      counts["llm"], counts["proof"], counts["parse"]))
    sys.exit(0)
  if not text:
    print("No text given.\n" + helptext)
    sys.exit(0)
  result = english_to_answer(text, opts)
  if opts.get("show_logic_flag"):
    print("\n=== result ===\n")
  print(result)


class _ApiTimeout(BaseException):
  """Raised by the SIGALRM handler when the LLM-parse-plus-clause-conversion
  phase exceeds the api_timeout cap.  The cap is disarmed before the prover
  (gk) runs, so it never interrupts the prover or proof post-processing.

  Subclasses BaseException (NOT Exception) on purpose: the LLM-call retry loops
  in llmcall.py catch `except Exception` (and used to catch bare `except:`) and
  would otherwise swallow the timeout and retry, defeating the cap. As a
  BaseException it propagates straight through those handlers to the
  `except _ApiTimeout` in english_to_answer."""


def _api_timeout_handler(signum, frame):
  raise _ApiTimeout()


def _english_to_answer_once(text, options=None, collect=None,
                            stage2_corrective="", stage1_corrective="",
                            stage1_json=None):
  """Full pipeline: English -> LLM parse -> logic convert -> prove -> answer.

  LLM calls within this pipeline are cached by default (controlled by
  use_llm_cache_flag in globals.options, default True).  Pass
  {"use_llm_cache_flag": False} in options, or use -nollmcache on the
  command line, to disable caching for a run.

  Arguments:
    text    -- English text containing statements and a question (string)
    options -- optional dict of option overrides (keys as in globals.options)
    collect -- optional dict that, if provided, is populated with pipeline
               artifacts for downstream analysis: stage1, stage2,
               stage_1_fixes, stage_2_fixes, stage_1_retries, stage_2_retries,
               clauses (list of clause dicts with @nl injected), gk_command,
               proof, answer, nl_proof.  Keys with empty/null values are
               omitted.  Setting collect forces the prover-explain pass on so
               the English proof explanation is captured.

  Returns the answer string.  On any error returns a string starting with
  "Error:" rather than raising an exception or calling sys.exit().
  """
  global _depth
  _depth += 1
  try:
    return _english_to_answer_body(text, options, collect, stage2_corrective,
                                   stage1_corrective, stage1_json)
  finally:
    _depth -= 1


# How deeply the pipeline is calling itself: the critique pass's rerun and the
# downstream-error retry run the whole thing again from inside it.
_depth = 0


def _english_to_answer_body(text, options=None, collect=None,
                            stage2_corrective="", stage1_corrective="",
                            stage1_json=None):
  if options is None:
    options = {}
  if collect is not None:
    options["_collect"] = collect
    options["prover_explain_flag"] = True
  if options:
    globals.set_global_options(options)

  show_details = options and options.get("show_details_flag")
  show_logic   = options and options.get("show_logic_flag")

  # Resolve which LLM is being used (for display in headers).
  actual_llm = llm or llmcall.use_llm

  # -logic+: show input text at the top
  if show_logic:
    print(text)

  think_flag = globals.options.get("think_flag", False)

  # Direct-answer mode: answer with ONE LLM call using the given prompt, skipping
  # the parse -> logic -> prover pipeline.  Works for any test set.
  if globals.options.get("directanswer_flag"):
    import directanswer
    prompt_file = globals.options.get("directanswer_file")
    answer = directanswer.answer_directly(
      text, prompt_file, llm=llm, version=llm_version, tokens=max_tokens, think=think_flag)
    if collect is not None:
      collect["answer"] = answer
      collect["directanswer"] = {"prompt": prompt_file}
    if show_logic or show_details:
      print(answer)
    return answer

  llmparse.prenorm_enabled = globals.options.get("prenorm_flag", False)
  llmparse.negretry_enabled = globals.options.get("negretry_flag", False)
  llmparse.canon_entities_enabled = lc_encoding.current().parse_canon
  llmparse.crossstage_guard_retry = globals.options.get("crossstage_retry_flag", True)
  llmparse.combined_enabled        = globals.options.get("combined_flag", False)
  llmparse.combined_instr_file     = globals.options.get("combined_instr_file")
  llmparse.combined_examples_file  = globals.options.get("combined_examples_file")
  llmparse.combined_checklist_file = globals.options.get("combined_checklist_file")
  llmparse.s2split_enabled         = globals.options.get("s2split_flag", False)
  if llmparse.s2split_enabled and llmparse.combined_enabled:
    return "Error: -s2split is incompatible with combined single-stage parsing (-combined-instr)"
  # --- hard wall-clock cap on the API-parse + clause-conversion phase ---
  # Arm a SIGALRM that interrupts a wedged LLM call (blocking socket read) or a
  # runaway conversion.  The cap is DISARMED right before the prover runs, so it
  # never interrupts gk or proof post-processing (those have their own limits).
  # Disabled when api_timeout is 0 or when not on the main thread (signal needs
  # the main thread; multiprocessing Pool workers and the sequential runner both
  # call this from their process's main thread, so the cap is active there).
  _api_to = globals.options.get("api_timeout", 0)
  _api_armed = bool(_api_to and _api_to > 0
                    and threading.current_thread() is threading.main_thread())
  _api_prev = signal.signal(signal.SIGALRM, _api_timeout_handler) if _api_armed else None
  if _api_armed:
    signal.alarm(int(_api_to))
  try:
    s1_json, s2_json, parse_stats = llmparse.parse_text(
      text, llm=llm, version=llm_version, tokens=max_tokens, think=think_flag,
      stage2_corrective=stage2_corrective,
      stage1_corrective=stage1_corrective, stage1_json=stage1_json
    )

    # ASCII-fold the parsed logic before clausification so accented entity names
    # (e.g. "Náutico", "Świątek", "Oñate") become plain ASCII ("Nautico",
    # "Swiatek", "Onate").  The prover reads the gk subprocess output as ASCII
    # (prover.py), so a non-ASCII byte otherwise crashes the proof step (answer
    # None).  Folding both stages keeps entity names consistent between them.
    s1_json = _ascii_fold_logic(s1_json)
    s2_json = _ascii_fold_logic(s2_json)

    if collect is not None:
      if s1_json is not None:
        collect["stage1"] = s1_json
      if s2_json is not None:
        collect["stage2"] = s2_json
      for stage_key, out_key in (("s1_fixes", "stage_1_fixes"),
                                  ("s2_fixes", "stage_2_fixes"),
                                  ("s1_retries", "stage_1_retries"),
                                  ("s2_retries", "stage_2_retries"),
                                  ("calls", "parse_calls")):
        val = parse_stats.get(stage_key) or []
        if val:
          collect[out_key] = list(val)

    if debug:
      llmparse.print_stats(parse_stats)

    # -details (not -debug): show parsed stage-1 and stage-2 JSON.
    # -debug already shows these via llmparse._debug_write.
    if show_details and not debug:
      import pretty as _pretty
      if s1_json is not None:
        print("\n=== stage 1 (ASU JSON, " + actual_llm + ") ===\n")
        _pretty.pp_stage1(s1_json)
      if s2_json is not None:
        print("\n=== stage 2 (logic JSON, " + actual_llm + ") ===\n")
        _pretty.pp_stage2(s2_json)

    if s2_json is None:
      return "Error: LLM parsing failed (stage 2 produced no output)."

    # -logic+: show "simplified to" block if ASU texts differ from input
    if show_logic and s1_json:
      _show_simplified_to(text, s1_json)

    # --- rawlogic_convert: improve / adjust the parsed logic (logconvert.py) ---

    lc_fixes = []
    logic = rawlogic_convert(s2_json, s1_json, fixes=lc_fixes)

    if logic is None:
      return "Error: rawlogic_convert returned None."

    if collect is not None:
      # Surface logconvert structural clause-repairs alongside the Stage-2 JSON
      # fixes (they repair the same Stage-2 output, just later in the pipeline).
      if lc_fixes:
        collect["stage_2_fixes"] = list(collect.get("stage_2_fixes", [])) + lc_fixes
      collect["clauses"] = _build_clauses_with_nl(logic, s1_json)

    # --- show "sentences mapped to clauses" block ---
    if show_logic or debug:
      from proof_render import compute_ambiguity as _compute_ambiguity
      _compute_ambiguity(logic)   # populate ambiguous_bases before rendering
      from utils import format_sentences_to_clauses
      json_mode = options.get("json_flag", False) if options else False
      print("\n" + format_sentences_to_clauses(logic, s1_json, json_mode=json_mode) + "\n")

    # --- semantic normalisation: antonym folding + canonical substitution ---
    # Snapshot first when collecting: sem_normalize_clauses rewrites in place,
    # so the clause list gk receives can differ from collect["clauses"] above.
    # clause_trace uses the snapshot to mark and keep the pre-rewrite form.
    _pre_norm_logic = None
    if collect is not None and not globals.options.get("nofinaltrace"):
      import copy as _copy
      _pre_norm_logic = _copy.deepcopy(logic)
    if not globals.options.get("nosemnormal_flag"):
      logic = semnormalize.sem_normalize_clauses(logic)
  except _ApiTimeout:
    msg = "Error: LLM/parse phase exceeded the %ds api-timeout cap." % int(_api_to)
    # `_english_to_answer` records this in `collect`, as it does for every
    # early return: a batch runner otherwise stores a case file with no answer
    # and no error, which is indistinguishable from a case that ran.
    return msg
  finally:
    if _api_armed:
      signal.alarm(0)
      if _api_prev is not None:
        signal.signal(signal.SIGALRM, _api_prev)

  # --- record the clause list actually handed to the prover, plus provenance ---
  # collect["clauses"] above is the pre-semnormalize list and stays as it is;
  # these two fields are what the proof audit and the break-point locator read.
  if collect is not None and not globals.options.get("nofinaltrace"):
    try:
      import clause_trace
      collect["final_clauses"] = logic
      collect["final_clause_trace"] = clause_trace.build_final_clause_trace(
          logic, s1_json, pre_clauses=_pre_norm_logic)
    except Exception as e:
      collect["final_clause_trace_error"] = str(e)

  # --- call the theorem prover (uncapped: gk has its own -seconds limit) ---
  try:
    proof_result = prover.call_prover(logic, s1_json=s1_json)
  except KeyboardInterrupt:
    raise
  except Exception as e:
    return "Error: prover raised an exception: " + str(e)

  if proof_result is None:
    return "Error: prover returned None."

  # -nosolve: prover was not run; logic JSON was already shown by prover.py
  if options and options.get("prover_nosolve_flag"):
    return ""

  # -rawresult: caller wants the raw prover JSON, skip post-processing
  if options and options.get("prover_rawresult_flag"):
    return proof_result

  # -details+ or -prover: show prover result JSON
  show_prover = options and options.get("show_prover_flag")
  if show_details or show_prover:
    print("\n=== prover result (JSON) ===\n")
    print(proof_result)

  # --- process_proof: post-process prover output into final answer (procproofs.py) ---
  answer = process_proof(proof_result, text=text, s1_json=s1_json, s2_json=s2_json, logic=logic, options=options)

  # --- the critique pass (-critic), before any abstraction route ---
  # One call audits the translation the front door produced.  On RETRANSLATE
  # Stage 2 (or Stage 1 and 2) runs once more with the findings appended, and
  # the ordinary converter and gk follow.  One critique, one rerun, then stop.
  answered_by = "front_door" if not _unresolved(answer) else "none"
  front_door_answer = answer
  # which stage answered the critic's retranslation, when the critic answered
  rerun_answered_by = None
  # The front door's own gk call, snapshot here.  Every later `call_prover`
  # overwrites `collect["gk_command"]`, so a stage that RAN without answering
  # would otherwise leave its command at the top level.  `answering` holds the
  # gk call that produced the final answer; the top-level `proof` and
  # `gk_command` are set from it at the end of the run.
  front_door_proof = proof_result
  front_door_gk_command = (collect or {}).get("gk_command")
  answering = None
  # What each stage did: one row per stage, in stage order.  A separate
  # information block, printed by `-summary` and by `-logic` and above, and
  # written to the case record as `stages`.  No ordinary key changes shape
  # because a later stage answered.
  stage_rows = []
  _announced.clear()
  _note_stage(stage_rows, "front_door", True, answer)

  # --- the two abstention fallbacks, before the critic and the abstraction
  # routes.  Each converts the SAME Stage-1/Stage-2 parse a second time and
  # calls gk again; neither makes an LLM call.  They run only when the front
  # door left the question unresolved, so a definite front-door answer is
  # never disturbed, and the first definite fallback answer stops the rest.
  _fb_records = {}
  for _fb_name, _fb_key in (("fallback_norm", "fallback_norm_flag"),
                            ("fallback_hyp", "fallback_hyp_flag")):
    if not globals.options.get(_fb_key):
      _note_stage(stage_rows, _fb_name, False, why="off")
      continue
    if not _unresolved(answer):
      _note_stage(stage_rows, _fb_name, False,
                  why="not needed: the question was already answered")
      continue
    _announce_stage(_fb_name)
    try:
      if _fb_name == "fallback_norm":
        import fallback_norm as _fb_mod
      else:
        import fallback_hyp as _fb_mod
      got = _fb_mod.run(s1_json, s2_json, text, logic, options)
      _fb_records[_fb_name.split("_", 1)[1]] = got["record"]
      _note_stage(stage_rows, _fb_name, True, got.get("answer"))
      if got["answered"]:
        answer = got["answer"]
        logic = got["logic"]
        proof_result = got["proof"]
        answered_by = _fb_name
        answering = {"proof": got["proof"],
                     "gk_command": (collect or {}).get("gk_command")}
        if collect is not None and not globals.options.get("nofinaltrace"):
          collect["final_clauses"] = got["logic"]
    except KeyboardInterrupt:
      raise
    except Exception as _fb_e:                                  # noqa: BLE001
      _fb_records[_fb_name.split("_", 1)[1] + "_error"] = (
          "%s: %s" % (type(_fb_e).__name__, str(_fb_e)[:200]))
  if _fb_records and collect is not None:
    _fb_records["answered_by"] = (answered_by if answered_by
                                  in ("fallback_norm", "fallback_hyp")
                                  else None)
    collect["fallback"] = _fb_records

  global _critiqued
  if not _should_critique(answer):
    _note_stage(stage_rows, "critic", False,
                why=("off" if not globals.options.get("critic_flag")
                     else "not needed: the question was already answered"))
  if _should_critique(answer):
    _critiqued = True
    _announce_stage("critic")
    with llmcall.tagged("critic"):
      got = _run_critic(text, s1_json, s2_json, logic, answer, llm,
                        llm_version, max_tokens, options, collect=collect,
                        loud=debug or show_details or show_logic
                        or globals.options.get("prover_explain_flag"))
    _note_stage(stage_rows, "critic", True,
                (got or {}).get("answer"))
    if got and got.get("answer") is not None:
      answer = got["answer"]
      answered_by = "critic"
      rerun_answered_by = got.get("rerun_answered_by")
      answering = {"proof": got.get("proof"),
                   "gk_command": got.get("gk_command")}
      if got.get("logic") is not None:
        logic = got["logic"]
      if collect is not None and not globals.options.get("nofinaltrace"):
        collect["final_clauses"] = logic

  # --- the abstraction routes, in the order `abstraction_order` gives ---
  # Each route runs only when the question is still unresolved, and only when
  # its own flag is on.  A route not named in the order never runs, whatever
  # its flag says: the order is the list of routes this run may use.
  # the graph blocks appear from `-explain` up, the literal bridge's from
  # `-logic` up, as before
  loud = (debug or show_details or show_logic
          or globals.options.get("prover_explain_flag"))
  routes = {"graphtrans": _run_graphtrans,
            "litbridge": _run_litbridge,
            "graphbridge": _run_graphbridge}
  state = {"graphtrans": None}          # layer 1's record, reused by layer 2
  for name in _abstraction_order():
    if not _route_enabled(name):
      _note_stage(stage_rows, name, False, why="off")
      continue
    if not _unresolved(answer):
      _note_stage(stage_rows, name, False,
                  why="not needed: the question was already answered")
      continue
    with llmcall.tagged(name):
      got = routes[name](text, s1_json, s2_json, logic, answer, llm,
                         llm_version, max_tokens, options, loud=loud,
                         verbose=debug or show_details, collect=collect,
                         state=state)
    _note_stage(stage_rows, name, True, (got or {}).get("answer"))
    if got is None:
      continue
    if got.get("answer") is not None:
      answer = got["answer"]
      if got.get("logic") is not None:
        logic = got["logic"]
      answered_by = name
      answering = {"proof": got.get("proof"),
                   "gk_command": got.get("gk_command")}
      if collect is not None and not globals.options.get("nofinaltrace"):
        collect["final_clauses"] = logic
  for _row in stage_rows:
    _row["answered"] = (_row["stage"] == answered_by and _row["ran"])
  if collect is not None:
    collect["abstraction_order"] = _abstraction_order()
    collect["stages_enabled"] = _stages_enabled()
    collect["stages"] = stage_rows
    collect["answered_by"] = answered_by
    # the first line only: the explanation, when there is one, is `nl_proof`
    collect["front_door_answer"] = str(
        front_door_answer or "").split("\n")[0] or None
    collect["llm_call_counts"] = _call_counts()
    collect["llm_calls_total"] = sum(
        v["calls"] for v in collect["llm_call_counts"].values())
  if _depth == 1:
    _print_stages(stage_rows)
  if (globals.options.get("summary_flag")
      or globals.options.get("summary_json_flag")) and _depth == 1:
    # only the outermost pipeline run reports: the critique pass's rerun calls
    # this function again from inside it, and that inner run is not a case run
    _print_summary(answer, answered_by, front_door_answer, state,
                   rerun_answered_by=rerun_answered_by, stages=stage_rows)

  if collect is not None:
    # process_proof appends "\n\n<explanation>" when prover_explain_flag is on.
    # Split so the JSON output has separate `answer` and `nl_proof` fields.
    if isinstance(answer, str) and "\n\n" in answer:
      short, expl = answer.split("\n\n", 1)
      collect["answer"] = short
      if expl.strip():
        collect["nl_proof"] = expl
    else:
      collect["answer"] = answer
    _set_answering_call(collect, answering, front_door_proof,
                        front_door_gk_command)

  return answer


# ======== N1: downstream-error corrective retry ========
#
# Origin: the /opt/logictools/nl weak-model pilot (Doc/NANO_PROMPT.md), adapted.
#
# The Stage-1/Stage-2 sanity retries only ever see the STRUCTURE of the parsed
# JSON.  Errors that surface later — in rawlogic_convert, in clausification, in
# gk, or at question handling — arrive after that retry window has closed and
# were never re-prompted.  This loop matches the resulting error against a table
# of known failure shapes and re-calls Stage 2 with the actual error plus a
# targeted, imperative hint.
#
# It can only improve correctness: it fires exclusively on results that are
# already errors.  Stage 1 is not re-run — the corrective text is appended to
# the Stage-2 input, so the Stage-1 call is served from cache unchanged.

_MAX_DOWNSTREAM_RETRIES = 2

_DOWNSTREAM_HINTS = [
  (re.compile(r"first argument of (exists|a quantifier)|connective not a variable"
              r"|error in formula"),
   "A connective or quantifier was FLATTENED. Each is ONE nested list passed as a "
   "SINGLE argument: [\"question\", [\"exists\", \"X\", FORMULA]], never "
   "[\"question\", \"exists\", \"X\", FORMULA]. Likewise [\"and\", A, B], "
   "[\"or\", A, B], [\"not\", A] where A and B are THEMSELVES lists such as "
   "[\"isa\", \"house\", \"X\"], never bare strings spread into the parent list. "
   "Comparisons must use the named predicates, not operator symbols."),
  (re.compile(r"unhashable type|abnormal var found"),
   "Your nesting is malformed — a list appeared where a single element was expected, "
   "usually a DOUBLE-WRAPPED body, or a variable was used outside the quantifier that "
   "binds it. Each package is [\"@id\", \"Sx\", BODY] with BODY a SINGLE list: "
   "[\"@id\",\"S1\",[\"holds\",\"W0\", F]], not [\"@id\",\"S1\",[[\"holds\",\"W0\", F]]]. "
   "Every variable must appear inside the exists/forall that introduces it."),
  (re.compile(r"several questions|multiple question"),
   "You marked more than one package as a question. Output EXACTLY ONE query package, "
   "for the single sentence that ends in '?': [\"question\", F] for yes/no or "
   "[\"ask\", \"X\", F] for who/what/where/when. EVERY premise is an assertion "
   "[\"holds\", W, F] — never a question."),
  (re.compile(r"rawlogic_convert returned None"),
   "Your output could not be converted. Use nested JSON ARRAYS only — never objects "
   "with named keys. The WHOLE output is ONE list starting with \"and\": "
   "[\"and\", [\"@id\",\"S1\", BODY], [\"@id\",\"S2\", BODY], ...]. Each BODY is a "
   "SINGLE list and must not be wrapped in an extra pair of brackets. Output ONLY the "
   "JSON, with no code fences."),
  (re.compile(r"produced no output|parsing failed|prover returned empty"),
   "You returned no usable JSON. Output ONLY the JSON list [\"and\", ...] and nothing "
   "else — no explanation, no prose, no code fences."),
  (re.compile(r"no question given"),
   "You did not encode the question. Add exactly ONE query package for the sentence "
   "that asks the question (it ends with '?'): yes/no -> [\"question\", FORMULA]; "
   "who/what/where/when -> [\"ask\", \"X\", FORMULA]. Keep the facts as separate "
   "packages."),
]


def _downstream_hint(answer):
  """Return a corrective hint when the answer is a known downstream failure."""
  if not isinstance(answer, str) or not answer:
    return None
  first = answer.split("\n", 1)[0]
  # gk formula errors do not start with "Error"; scan the first line as well.
  if not answer.startswith("Error") and not any(p.search(first)
                                                for p, _ in _DOWNSTREAM_HINTS):
    return None
  for pat, hint in _DOWNSTREAM_HINTS:
    if pat.search(answer) or pat.search(first):
      return hint
  return None


def _run_critic(text, s1_json, s2_json, logic, answer, llm, llm_version,
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
      _print_critic(record)
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
      _print_critic(record)
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
  global _in_critic_rerun
  _in_critic_rerun = True
  try:
    inner = {}
    with llmcall.tagged(None, critic_rerun=True):
      again = _english_to_answer_once(text, options, inner,
                                      stage2_corrective=s2_corr,
                                      stage1_corrective=s1_corr)
    record["answer_after"] = again
    record["rerun_changed_units"] = _changed_units(
        s2_json, inner.get("stage2"))
    touched = (set(record["rerun_changed_units"]["changed"])
               | set(record["rerun_changed_units"]["added"]))
    record["touched_units"] = sorted(touched)
    record["unasked_units"] = sorted(touched - set(units))
    record["corrective_call"] = _corrective_call(inner, stage)
    if collect is not None:
      # `answered_by` and `fallback` say whether a fallback answered the
      # retranslation: the rerun re-enters the pipeline, so `fallback_norm`
      # and `fallback_hyp` run again on the new Stage 2 (the abstraction
      # routes do not — `_route_enabled` refuses inside a rerun).
      record["rerun"] = {k: v for k, v in inner.items()
                         if k in ("stage1", "stage2", "answer",
                                  "answered_by", "fallback")}
    if not _unresolved(again):
      out["answer"] = again
      out["rerun_answered_by"] = inner.get("answered_by")
      out["logic"] = inner.get("final_clauses") or logic
      # the rerun's own gk call, for the run's top-level record
      out["proof"] = inner.get("proof")
      out["gk_command"] = inner.get("gk_command")
  except Exception as e:                                        # noqa: BLE001
    record["rerun_error"] = "%s: %s" % (type(e).__name__, e)
  finally:
    _in_critic_rerun = False
  if collect is not None:
    collect["critic"] = record
  if loud:
    _print_critic(record)
  return out


def _call_counts():
  """Per stage tag: how many LLM calls, how many live, how many were retries.

  `llmcall.call_log` is reset once per case by the runners, so this counts
  this case alone.  The tag is set by `llmcall.tagged` at each call site.
  """
  out = {}
  for row in llmcall.call_log:
    tag = row.get("tag") or "untagged"
    cell = out.setdefault(tag, {"calls": 0, "live": 0, "retries": 0})
    cell["calls"] += 1
    if row.get("source") == "api":
      cell["live"] += 1
    if row.get("retry"):
      cell["retries"] += 1
  return out


def _summary_record(answer, answered_by, front_door_answer, state=None,
                    rerun_answered_by=None, stages=None):
  """The one block `-summary` prints, as a dict."""
  counts = _call_counts()
  routes = []
  for name in _abstraction_order():
    if name == answered_by:
      routes.append("%s (answer found)" % name)
    elif not _route_enabled(name):
      routes.append("%s off" % name)
    elif counts.get(name):
      routes.append("%s ran, no answer" % name)
    else:
      routes.append("%s not run" % name)
  return {"answer": str(answer or "").split("\n")[0],
          "answered_by": answered_by,
          "front_door_answer": str(front_door_answer or "").split("\n")[0],
          "abstraction_order": ",".join(_abstraction_order()),
          "stages_enabled": _stages_enabled(),
          "stages": stages or [],
          "rerun_answered_by": rerun_answered_by,
          "llm_call_counts": counts,
          "llm_calls_total": sum(v["calls"] for v in counts.values()),
          "llm_calls_live": sum(v["live"] for v in counts.values()),
          "routes": routes}


# The summary of the attempt now finishing, and whether to hold it back until
# `english_to_answer`'s retry loop has settled on an answer.
_last_summary = None
_suppress_summary = False


def _print_summary(answer, answered_by, front_door_answer, state=None,
                   rerun_answered_by=None, stages=None):
  """`-summary`: who answered and what it cost, whatever the output level."""
  global _last_summary
  rec = _summary_record(answer, answered_by, front_door_answer, state,
                        rerun_answered_by=rerun_answered_by, stages=stages)
  _last_summary = rec
  if _suppress_summary:
    return
  _show_summary(rec)


def _show_summary(rec):
  if globals.options.get("summary_json_flag"):
    print(json.dumps(rec, default=str))
    if not globals.options.get("summary_flag"):
      return
  print("\n=== summary ===")
  print("answer: %s" % rec["answer"])
  by = rec["answered_by"]
  if rec.get("rerun_answered_by") in ("fallback_norm", "fallback_hyp"):
    by = "%s (rerun answered by %s)" % (by, rec["rerun_answered_by"])
  print("answered_by: %s   (front door: %s)"
        % (by, rec["front_door_answer"]))
  print("stages_enabled: %s" % (", ".join(rec["stages_enabled"]) or "none"))
  print("abstraction_order: %s" % rec["abstraction_order"])
  parts = []
  for tag in sorted(rec["llm_call_counts"]):
    cell = rec["llm_call_counts"][tag]
    bits = "live %d" % cell["live"]
    if cell["retries"]:
      bits += ", retries %d" % cell["retries"]
    parts.append("%s %d (%s)" % (tag, cell["calls"], bits))
  print("llm calls: %s; total %d, live %d"
        % ("; ".join(parts) or "none", rec["llm_calls_total"],
           rec["llm_calls_live"]))
  print("routes run: %s" % "; ".join(rec["routes"]))


def _corrective_call(inner, stage):
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


def _changed_units(before, after):
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


def _print_critic(record):
  """The `-explain` block of the critique pass."""
  print("\n=== critic (one reading of the front door's translation) ===")
  report = record.get("report")
  if not report:
    print("  no usable reply: %s" % (record.get("parse_failure") or "?"))
    return
  print("  reading: %s   chain: %s"
        % (report["answer_by_reading"], ", ".join(report["chain"]) or "-"))
  for f in report["findings"]:
    print("  [%s, %s] %s: %s"
          % (f["kind"], f["severity"], ", ".join(f["units"]),
             f["problem"][:110]))
  if report.get("dropped_findings"):
    print("  dropped %d finding(s) (unquoted or malformed)"
          % len(report["dropped_findings"]))
  print("  verdict: %s%s" % (record["verdict"],
                             ("" if record["verdict"] == "KEEP"
                              else " (stage %s, units %s)"
                              % (record["stage"],
                                 ", ".join(record["units_to_redo"])))))
  if record.get("rerun_changed_units"):
    got = record["rerun_changed_units"]
    print("  corrective call: %s (stage %s)"
          % (record.get("corrective_call") or "?",
             record.get("corrective_stage") or 2))
    print("  rerun changed units %s%s; answer after rerun: %s"
          % (", ".join(got["changed"]) or "none",
             ("; unasked %s" % ", ".join(record["unasked_units"])
              if record.get("unasked_units") else ""),
             str(record.get("answer_after") or "").split("\n")[0]))


def _stages_enabled():
  """The stage keys this run has on, in stage order.

  Written into the case record next to `abstraction_order`, so a results
  folder says what ran without its command line.
  """
  import globals
  return [k[:-5] for k in STAGE_KEYS if globals.options.get(k)]


def _abstraction_order():
  """The routes this run may use, in order.  Unknown names are an error.

  A route the list omits never runs, whatever its own flag says: the list is
  what this run is allowed to try, and the flags say which of those are on.
  """
  import globals
  return list(globals.ABSTRACTION_ROUTES)


def _route_enabled(name):
  import globals
  if _in_critic_rerun:
    # The rerun is a retranslation: Stage 2 again, the converter, gk.  Running
    # the routes inside it would run them twice per case — once on the
    # repaired translation and once on the original, in the outer run.
    return False
  if name == "graphtrans":
    return bool(globals.options.get("graphtrans_flag")
                or globals.options.get("graphbridge_flag"))
  if name == "litbridge":
    return bool(globals.options.get("litbridge_flag"))
  if name == "graphbridge":
    return bool(globals.options.get("graphbridge_flag"))
  return False


def _run_graphtrans(text, s1_json, s2_json, logic, answer, llm, llm_version,
                    max_tokens, options, loud=False, verbose=False,
                    collect=None, state=None):
  """Layer 1: the graph retranslation and one gk call (`-graphtrans`)."""
  import graph_p0
  _announce_stage("graphtrans")
  got = graph_p0.run_graph_p0(text, s1_json, llm=llm, version=llm_version,
                              max_tokens=max_tokens, options=None)
  if state is not None:
    state["graphtrans"] = got
  if collect is not None:
    collect["graphtrans"] = _graphtrans_record(got)
  if debug:
    _print_graphtrans(got, verbose=verbose)
  _print_graph_theory(got, s1_json, llm)
  if got.get("answer") is None:
    return {"answer": None, "logic": None}
  return {"answer": got["answer_string"], "logic": got["clauses"],
          "proof": got.get("gk_result"), "gk_command": got.get("gk_command")}


def _graphtrans_record(got):
  """What a runtests JSON keeps.

  The open-triple Stage 2 and the graph clause list stay: each is the size of
  an ordinary Stage 2 and clause list, and without them the record cannot say
  what was proved.  Only the compiler sidecar and the unparsed result string
  are dropped; `gk_result` carries the same result as JSON.
  """
  return {k: v for k, v in got.items() if k not in ("sidecar", "raw")}


def _loud_enough():
  """True from `-logic` up: the level at which the pipeline shows its blocks."""
  return bool(globals.options.get("show_logic_flag")
              or globals.options.get("show_details_flag")
              or globals.options.get("debug_print_flag"))


_announced = set()


def _announce_stage(name, late=False):
  """One line naming the stage whose blocks follow.

  A stage after the front door parses, converts and calls gk again, and its
  blocks carry the ordinary headers — `=== stage 2 (logic JSON, …) ===`,
  `=== prover input (JSON) ===` and the rest.  This line is what says whose
  they are, so it is printed only at the levels where those headers actually
  repeat: `-details` and above, and `-logic` for a stage that prints a clause
  block there (`late=True`, printed by the block itself).  At most one line
  per stage per run.  `-explain` prints none: it shows the answer and its
  proof, as it does for an answer the front door found.
  """
  loud = bool(globals.options.get("show_details_flag")
              or globals.options.get("debug_print_flag"))
  if late:
    loud = loud or bool(globals.options.get("show_logic_flag"))
  if not loud or name in _announced:
    return
  _announced.add(name)
  print("\n--- stage: %s ---" % name)


def _print_stages(rows):
  """The stages block: which stages ran, and which one produced the answer."""
  if not (rows and _loud_enough()):
    return
  print("\n=== stages ===\n")
  for row in rows:
    mark = "  <- the answer" if row.get("answered") else ""
    if not row.get("ran"):
      print("  %-14s %s%s" % (row["stage"], row.get("why") or "not run", mark))
      continue
    print("  %-14s ran   %s%s"
          % (row["stage"], row.get("answer") or "no answer", mark))


def _note_stage(rows, name, ran, answer=None, why=None):
  """Record what one stage did, for the stages block and the case record."""
  row = {"stage": name, "ran": bool(ran), "answered": False}
  head = str(answer or "").split("\n")[0].strip()
  if ran:
    row["answer"] = head or None
  elif why:
    row["why"] = why
  rows.append(row)
  return row


def _print_graph_theory(got, s1_json=None, llm=None):
  """The second translation's own copies of the ordinary output blocks.

  The headers are the ordinary ones: what marks the blocks as the second
  translation's is the `--- stage: … ---` line printed before the route ran,
  not a different vocabulary in every header.  `-logic` adds
  the clause list with its source comments, `-details` the Stage-2 JSON and
  the prover result.  The prover input and params are printed by
  `prover.call_prover` itself, as for any call.
  """
  show_logic = globals.options.get("show_logic_flag")
  show_details = globals.options.get("show_details_flag")
  if not (show_logic or show_details or debug):
    return
  clauses = got.get("clauses")
  if show_details or debug:
    if got.get("stage2_graph") is not None:
      print("\n=== stage 2 (logic JSON, %s) ===\n" % (llm or ""))
      print(json.dumps(got["stage2_graph"], indent=2))
  if (show_logic or debug) and clauses:
    # the same renderer the front door's block uses, so the two read alike
    from proof_render import compute_ambiguity as _compute_ambiguity
    from utils import format_sentences_to_clauses
    _announce_stage("graphtrans", late=True)
    try:
      _compute_ambiguity(clauses)
      print("\n" + format_sentences_to_clauses(
          clauses, s1_json,
          json_mode=bool(globals.options.get("json_flag"))) + "\n")
    except Exception as e:                                      # noqa: BLE001
      print("  (clause block not renderable: %s)" % e)
  if show_details or debug:
    if got.get("gk_result") is not None:
      print("\n=== prover result (JSON) ===\n")
      print(json.dumps(got["gk_result"], indent=2))


def _print_graphtrans(got, verbose=False):
  """The layer-1 block of `-explain` and above."""
  print("\n=== the second translation, step by step ===")
  tr = got.get("translation") or {}
  m = (tr.get("measurements") or {})
  before = got.get("issues_before") or {}
  after = got.get("issues_after") or {}
  line = "  translation: %s units, %s atoms" % (m.get("units", "?"),
                                                m.get("atoms", "?"))
  if before:
    line += "; checks fired: %s" % ", ".join(
        "%s x%d" % (k, v) for k, v in sorted(before.items()))
    line += " -> retried once" if got.get("retries") else " -> not retried"
    line += "; after retry: %s" % ("clean" if not after else ", ".join(
        "%s x%d" % (k, v) for k, v in sorted(after.items())))
  else:
    line += "; checks: clean"
  print(line)
  for rule in got.get("variant_rules") or []:
    print("  variant rule %s: %s -> normally %s @%s"
          % (rule["name"], rule["marked"], rule["base"], rule["confidence"]))
  if got.get("dropped_invented_clauses"):
    print("  dropped %d clause(s) using a name the converter invented"
          % len(got["dropped_invented_clauses"]))
  if got.get("stopped_at"):
    print("  stopped: %s" % got["stopped_at"])
    return
  if got.get("answer") is None:
    print("  gk: no answer")
    return
  # the first line only: the explanation, when there is one, is printed with
  # the answer at the end of the run
  print("  gk: answer found, confidence %s -> %s"
        % (got.get("confidence"),
           str(got.get("answer_string") or "").split("\n")[0]))
  if verbose and got.get("proof"):
    for line in _graph_proof_lines(got["proof"]):
      print("    %s" % line)


def _graph_proof_lines(proof):
  """A graph proof as plain atoms: `pred(arg, …)  [name]`, negation spelled.

  The open names are the case's own words, not the ordinary vocabulary, so
  they are never routed through the English renderer.
  """
  out = []
  for block in (proof or []):
    for step in (block or []):
      text = _graph_step_line(step)
      if text:
        out.append(text)
  return out[:40]


def _graph_step_line(step):
  import json as _json
  blob = step if isinstance(step, (list, dict)) else None
  if blob is None:
    return str(step)[:120]
  name = ""
  if isinstance(blob, list) and blob and isinstance(blob[0], str):
    name = blob[0]
  literals = []
  for atom in _graph_atoms(blob):
    pred = str(atom[0])
    sign = "not " if pred.startswith("-") else ""
    pred = pred[1:] if pred.startswith("-") else pred
    literals.append("%s%s(%s)" % (sign, pred,
                                  ", ".join(str(x) for x in atom[1:])))
  if not literals:
    return _json.dumps(blob, default=str)[:120]
  return "%s%s" % (" or ".join(literals), ("  [%s]" % name) if name else "")


def _graph_atoms(node, out=None):
  out = [] if out is None else out
  if not isinstance(node, list) or not node:
    return out
  if all(not isinstance(x, list) for x in node) and isinstance(node[0], str):
    if node[0] not in ("or", "and", "$block", "$"):
      out.append(node)
    return out
  for sub in node:
    if isinstance(sub, list):
      _graph_atoms(sub, out)
  return out


def _run_litbridge(text, s1_json, s2_json, logic, answer, llm, llm_version,
                   max_tokens, options, loud=False, verbose=False,
                   collect=None, state=None):
  """The literal bridge, exactly as it ran before the route loop existed.

  The body is the block that used to sit inline in `_english_to_answer_once`;
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
    rec["resolved"] = not _unresolved(answer)
    provenance.update(rec.get("clause_provenance") or {})
    rules_by_id.update(rec.get("rules_by_id") or {})
    if rec["resolved"] and _litbridge_grader_mode():
      grade = _grade_litbridge(text, proof_result, provenance, rules_by_id,
                               respond)
      rec["grading"] = grade
      if grade.get("withdrawn"):
        # the proof rests on a rule the grader failed: the bridge answers
        # nothing and the front door's answer stands
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
  if _unresolved(answer):
    answer, logic = base_answer, base_logic
  if collect is not None:
    collect["litbridge"] = {"extras": extras, "rounds": records,
                            "proved": not _unresolved(answer),
                            "grader": _litbridge_grader_mode(),
                            "options": view["configuration"]}
    if not globals.options.get("nofinaltrace"):
      collect["final_clauses"] = logic
  if loud:
    _print_litbridge(records, verbose=debug or show_details,
                     options=view["configuration"])
  return {"answer": None if _unresolved(answer) else answer, "logic": logic,
          "proof": answering_proof, "gk_command": answering_command}


def _litbridge_grader_mode():
  """The grader's mode, or None when it is off (`litbridge_grader.MODE`)."""
  import litbridge_grader
  return litbridge_grader.MODE


def _grade_litbridge(text, proof_result, provenance, rules_by_id, respond):
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


def _set_answering_call(collect, answering, front_door_proof,
                        front_door_gk_command):
  """Put the gk call that produced the answer at the top level of the record.

  `proof` and `gk_command` describe the ANSWERING stage's call, whichever
  stage that was.  When a stage after the front door answered, the front
  door's own call is kept beside them as `front_door_proof` and
  `front_door_gk_command`.  When nothing after the front door answered, the
  front door's call is the top-level one — every `call_prover` writes
  `collect["gk_command"]`, so a stage that RAN without answering would
  otherwise leave its own command there.  `clauses` is untouched: it is the
  front door's clause list at every level.
  """
  if collect is None:
    return
  if answering is not None:
    collect["front_door_proof"] = _as_json(front_door_proof)
    collect["front_door_gk_command"] = front_door_gk_command
    collect["proof"] = _as_json(answering.get("proof"))
    if answering.get("gk_command"):
      collect["gk_command"] = answering["gk_command"]
  else:
    collect["proof"] = _as_json(front_door_proof)
    if front_door_gk_command:
      collect["gk_command"] = front_door_gk_command
  if collect.get("proof") is None:
    collect.pop("proof", None)


def _as_json(proof_result):
  """A gk result as a JSON object, so a dump does not drown in escapes.

  Falls back to the raw string when it does not parse (an "Error: …" return),
  and to None when there is nothing.
  """
  if proof_result is None:
    return None
  if isinstance(proof_result, (dict, list)):
    return proof_result
  if not (isinstance(proof_result, str) and proof_result.strip()):
    return None
  try:
    return json.loads(proof_result)
  except Exception:                                             # noqa: BLE001
    return proof_result


def _unresolved(answer):
  """The question is still open, so invented rules are worth a second gk run.

  `Unknown.`, nothing at all, or an `Error:` string.  The error case follows
  litbridge_procedure.FRONT_DOOR_POLICY: an error is not a definite answer.
  """
  if answer is None:
    return True
  head = str(answer).split("\n", 1)[0].strip()
  return (not head) or head == "Unknown." or head.lower().startswith("error")


def _print_litbridge(records, verbose=False, options=None):
  """Show what each bridge round did, for -logic and above."""
  print("\n=== litbridge (the ordinary run left the question unresolved) ===\n")
  if options is not None:
    print("  converted as the theory was: %s" % _litbridge_encoding(options))
  for rec in records:
    number = rec.get("round", 0)
    if not number:
      print("  not started: %s" % rec.get("stopped_at"))
      continue
    print("  round %d:" % number)
    if rec.get("stopped_at"):
      print("    stopped at: %s" % rec["stopped_at"])
    if not rec.get("asked"):
      print("    no LLM call")
    print("    candidate atoms shown to the model: %s"
          % rec.get("candidate_atoms", 0))
    print("    rules written: %d, clauses added: %d"
          % (rec.get("rules", 0), rec.get("clauses", 0)))
    for label, key in (("distinctness", "distinctness"),
                       ("negative relation", "negative_relation")):
      got = rec.get(key)
      if got is None:
        continue
      if got.get("asked"):
        print("      %s channel: asked, %d eligible pair(s), %d rule(s)"
              % (label, got.get("eligible_pairs", 0), got.get("rules", 0)))
      else:
        print("      %s channel: no call (%s)"
              % (label, got.get("why_not_asked") or "no eligible pair"))
    for printed in rec.get("printed_rules") or []:
      print("      " + printed)
    if rec.get("gk_called"):
      print("    gk called again: %s"
            % ("a proof was found" if rec.get("resolved")
               else "still no proof"))
    else:
      print("    gk not called again (no clause to add)")
    if not verbose:
      continue
    counts = rec.get("signed_counts") or {}
    if counts:
      print("      conclusions: %d positive, %d negative"
            % (counts.get("positive_conclusion", 0),
               counts.get("negative_conclusion", 0)))
    for row in rec.get("refused_by_the_compiler") or []:
      print("      refused: %s  (%s)" % (row.get("printed"), row.get("why")))
    rejected = rec.get("rejections_by_category") or {}
    if rejected:
      print("      rules the parser rejected: %s"
            % ", ".join("%s %s" % (k, v) for k, v in sorted(rejected.items())))
    for row in rec.get("omitted_by_the_hypothesis_limit") or []:
      print("      over the hypothesis limit: %s" % row)


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


def _litbridge_encoding(options):
  """The part of the bridge's option set worth showing: what it encodes to.

  Only the axes `lc_encoding.EncodingConfig` reads, so the line says what the
  clauses look like and not which flags the run happened to carry.
  """
  if not isinstance(options, dict):
    return str(options)
  axes = [name for name in lc_encoding.EncodingConfig.__slots__
          if options.get(name + "_flag") is True]
  return "event %s; %s" % (options.get("event_base"),
                           ", ".join(axes) if axes
                           else "no abstraction primitive")


def _run_graphbridge(text, s1_json, s2_json, logic, answer, llm, llm_version,
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
    got = _run_graphtrans(text, s1_json, s2_json, logic, answer, llm,
                          llm_version, max_tokens, options, loud=loud,
                          verbose=verbose, collect=collect, state=state)
    p0 = state.get("graphtrans")
    if got and got.get("answer") is not None:
      return got
  if not p0 or p0.get("stage2_graph") is None:
    return {"answer": None, "logic": None}
  _announce_stage("graphbridge")
  base_options = graph_compile.graph_options(litbridge_converter.live_options())
  respond = _graphbridge_responder(llm, llm_version, max_tokens)
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
        options=base_options, input_text=text, sources=_graphbridge_sources(),
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
    _print_graphbridge(record, verbose=verbose)
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


def _graphbridge_sources():
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


def _graphbridge_lifted_answer(record, text, s1_json, s2_json, logic, options):
  """The answer a lifted world reached, read back through process_proof."""
  for row in (record.get("lifting") or {}).get("rows") or []:
    for world in row.get("worlds") or []:
      if world.get("answers"):
        return world.get("conservative_formatter_answer")
  for row in (record.get("retranslation") or {}).get("rows") or []:
    got = row.get("gk") or {}
    if got.get("outcome") == "proof":
      return got.get("answer")
  return None


def _print_graphbridge(record, verbose=False):
  """Show what the graph route did, for -logic and above."""
  print("\n=== the second translation and its invented rules, step by "
        "step ===\n")
  if record.get("stopped_at"):
    print("  stopped at: %s" % record["stopped_at"])
  translation = record.get("translation") or {}
  if translation:
    m = translation.get("measurements") or {}
    print("  translation: %d package(s), %d atom(s), %d name(s); %s"
          % (m.get("packages", 0), m.get("atoms", 0),
             m.get("distinct_names", 0),
             "no structural issue" if translation.get("valid")
             else "issues: %s" % ", ".join(translation.get("issue_kinds")
                                           or [])))
  theory = record.get("graph_theory") or {}
  if theory:
    print("  graph theory: %d clauses" % theory.get("clauses", 0))
  inv = record.get("inventory") or {}
  if inv:
    print("  names: %d concept, %d relation, %d kind constant; "
          "%d supplied, %d demanded"
          % (inv.get("concept_names", 0), inv.get("relation_names", 0),
             inv.get("kind_constants", 0), inv.get("supply_names", 0),
             inv.get("demand_names", 0)))
  print("  pairs: %d enumerated, %d refused"
        % (record.get("pairs_enumerated", 0),
           len(record.get("pairs_refused") or [])))
  labels = record.get("labels") or {}
  if labels:
    print("  labels: %s" % ", ".join("%s %d" % (k, v)
                                     for k, v in sorted(labels.items())))
  per_pool = record.get("bridges_per_pool") or {}
  if per_pool:
    print("  bridges: %s" % ", ".join("%s %d" % (k, v)
                                      for k, v in sorted(per_pool.items())))
  for row in record.get("pools") or []:
    if row.get("skipped"):
      print("    %s: %s" % (row["pool"], row["skipped"]))
      continue
    print("    %s: %d bridge(s), %s, %s"
          % (row["pool"], row.get("bridges_offered", 0), row.get("outcome"),
             ", ".join(str(a) for a in row.get("answers") or [])
             or "no answer"))
  for row in record.get("minimal_sets") or []:
    print("    minimal set (%s): %s -> %s"
          % (row.get("pool"), ", ".join(row.get("minimal_rules") or [])
             or "no bridge", row.get("answer")))
  grades = (record.get("grades") or {}).get("distribution")
  if grades:
    print("  grades of the cited bridges: %s"
          % ", ".join("%s %d" % (k, v) for k, v in sorted(grades.items())))
  lifting = record.get("lifting") or {}
  if lifting.get("attempted"):
    print("  lifting: %s" % (lifting.get("outcome") or "nothing to lift"))
  elif lifting:
    print("  lifting: not attempted (%s)" % lifting.get("why"))
  if record.get("tier"):
    print("  tier %s: %s" % (record["tier"], record.get("tier_reason")))
  if not verbose:
    return
  for row in record.get("judged") or []:
    print("      %-24s %-24s %s" % (row["a"], row["b"], row["judge_label"]))
  for row in record.get("pairs_refused") or []:
    print("      refused %-20s %-20s %s" % (row["a"], row["b"], row["why"]))
  for row in record.get("bridges") or []:
    print("      %s  %s" % (row["rule_id"], row["printed"]))
  for row in record.get("bridge_omissions") or []:
    print("      omitted: %s" % row.get("why"))


def _graphbridge_responder(llm, llm_version, max_tokens):
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


# True once the critique pass has run for the case now being answered.  Reset
# by `english_to_answer`, which is where a case run begins.
_critiqued = False

# True while the critique pass's rerun is running.  The rerun re-enters the
# whole pipeline, and without this the abstraction routes would run inside it
# and again in the outer run.
_in_critic_rerun = False


def _should_critique(answer):
  """One critique per case run, and never inside the rerun it asked for.

  `_critiqued` does both: it is set before the critique runs, so the rerun
  cannot critique itself, and it survives the downstream-error retry loop in
  `english_to_answer`, which used to critique the same case once per attempt.
  It is a module flag on purpose — the earlier guard lived in
  `globals.options`, where the routes' own option resolvers deep-copied it and
  rejected it as an unknown key.
  """
  return bool(globals.options.get("critic_flag")
              and _unresolved(answer)
              and not _critiqued)


def english_to_answer(text, options=None, collect=None):
  """Full pipeline, with the N1 downstream-error corrective retry around it.

  The retry loop runs the whole pipeline again on a downstream error, so the
  summary block is held back until the loop is done and only the last one is
  printed: a case run reports once, whatever it took to answer it.
  """
  global _critiqued, _suppress_summary, _last_summary
  _critiqued = False
  _last_summary = None
  _suppress_summary = True
  try:
    return _english_to_answer(text, options, collect)
  finally:
    _suppress_summary = False
    if _last_summary is not None:
      _show_summary(_last_summary)


def _english_to_answer(text, options=None, collect=None):
  correction = ""
  fired = []
  answer = None
  for attempt in range(_MAX_DOWNSTREAM_RETRIES + 1):
    inner = {} if collect is not None else None
    answer = _english_to_answer_once(text, options, inner,
                                     stage2_corrective=correction)
    if collect is not None:
      collect.clear()
      collect.update(inner)
    hint = None if globals.options.get("nofix_downstream") \
           else _downstream_hint(answer)
    if hint is None or attempt == _MAX_DOWNSTREAM_RETRIES:
      break
    fired.append(str(answer).split("\n", 1)[0][:90])
    correction = ("\n\nYour previous answer FAILED downstream with:\n"
                  + str(answer).split("\n", 1)[0][:200] + "\n" + hint
                  + "\nReturn only the corrected JSON.")
  if fired and collect is not None:
    collect["downstream_retries"] = fired
  if collect is not None and collect.get("answer") is None:
    # The body returned early — a parse that produced nothing, a converter or
    # prover error — so the block that writes `answer`, `answered_by` and the
    # stage keys never ran.  Without this the case lands in `testresults/`
    # with no answer and no error at all, which is indistinguishable from a
    # case that ran, and invisible to an error count.  The `_ApiTimeout` path
    # inside the body already did this for itself; every other early return
    # is covered here.
    if answer is not None:
      collect["answer"] = answer
    collect.setdefault("stages_enabled", _stages_enabled())
  return answer


def _build_clauses_with_nl(logic, s1_json):
  """Return a copy of the clause list with an @nl key on each clause whose
  value is the source English (from build_asu_text_map), or a synthetic
  bracket-tag for population / generated clauses.  Used only for the
  runtests JSON output — the gk-bound serializer keeps its own // comments.
  """
  from utils import build_asu_text_map, _name_base
  asu_map = build_asu_text_map(s1_json) if s1_json else {}
  out = []
  for clause in logic:
    if not isinstance(clause, dict):
      out.append(clause)
      continue
    name = clause.get("@name", "")
    base = _name_base(name)
    is_pop = clause.get("@sourcetype") == "populate"
    if is_pop:
      nl = "[population: from input]"
    elif base in asu_map:
      nl = asu_map[base]
    elif base == "pop_what":
      nl = "[population: class witnesses for what-query]"
    else:
      nl = "[generated: " + base + "]"
    c = dict(clause)
    c["@nl"] = nl
    out.append(c)
  return out


def _show_simplified_to(text, s1_json):
  """Show the 'simplified to' block if ASU texts differ from the input."""
  asu_texts = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []):
      if isinstance(unit, dict) and unit.get("text"):
        asu_texts.append(unit["text"])
  if not asu_texts:
    return
  simplified = "\n".join(asu_texts)
  if simplified.strip() == text.strip():
    return
  print("\n=== simplified to ===\n")
  for t in asu_texts:
    print(t)


# ======== command-line interface ========


_TE_GATES = ("super", "gender", "nametype", "compound", "plural", "gnoun")


def _parse_te_gates(spec):
  """Parse a -typeenrich=<list> spec into a set of enabled sub-gates.

  Tokens are gate names (include), `-name` (exclude), or `all`. A spec made up
  entirely of excludes starts from the full set (e.g. `-plural` == all but plural).
  """
  toks = [t.strip() for t in spec.split(",") if t.strip()]
  if toks and all(t.startswith("-") for t in toks):
    gates = set(_TE_GATES)
    for t in toks:
      gates.discard(t[1:])
  else:
    gates = set()
    for t in toks:
      if t == "all":
        gates |= set(_TE_GATES)
      elif t.startswith("-"):
        gates.discard(t[1:])
      else:
        gates.add(t)
  return gates


# The six stage keys, in the order the stages run.  A flag set assigns every
# one of them, so a set fully replaces whatever an earlier set left behind.
STAGE_KEYS = ("fallback_norm_flag", "fallback_hyp_flag", "critic_flag",
              "graphtrans_flag", "litbridge_flag", "graphbridge_flag")


def _set_stages(opts, litbridge, graphbridge):
  """Assign all six stage keys.  The fallbacks, the critic and the graph
  translation are on in every set; the two bridges are what the sets differ
  in."""
  opts["fallback_norm_flag"] = True
  opts["fallback_hyp_flag"] = True
  opts["critic_flag"] = True
  opts["graphtrans_flag"] = True
  opts["litbridge_flag"] = bool(litbridge)
  opts["graphbridge_flag"] = bool(graphbridge)


def _parse_cmd_line():
  """Parse sys.argv; return (text, options_dict)."""
  global debug, llm, llm_version

  if len(sys.argv) < 2:
    print(helptext)
    sys.exit(0)

  text = ""
  opts = {}
  params = sys.argv[1:]
  elpos = -1
  skippos = 0
  # Stage-key resolution, in three rounds (§12.0):
  #   1. presets and flag sets (-abstract-max, -stack*) assign ALL SIX stage
  #      keys, left to right, so a later one overwrites an earlier one;
  #   2. explicit stage switches (-critic, -graphtrans, -graphbridge,
  #      -litbridge, -fallback_norm, -fallback_hyp) set their key True
  #      whatever their position relative to a preset — they are collected
  #      here and applied after the loop;
  #   3. the cancels (-nocritic, -nographtrans, -nographbridge, -nolitbridge,
  #      -nofallback*) are applied last and win over 1 and 2.
  explicit_on = set()

  for el in params:
    elpos += 1
    if skippos > 0:
      skippos -= 1
      continue
    textpart = ""
    if el in ["-debug", "--debug"]:
      debug = True
      opts["debug_print_flag"] = True
      opts["prover_print_flag"] = True
      opts["show_details_flag"] = True
      opts["show_logic_flag"] = True
      opts["prover_explain_flag"] = True
      opts["json_flag"] = True
      llmparse.debug = True
      llmcall.debug = True
    elif el in ["-details", "--details"]:
      opts["show_details_flag"] = True
      opts["show_logic_flag"] = True
      opts["prover_explain_flag"] = True
    elif el in ["-logic", "--logic"]:
      opts["show_logic_flag"] = True
      opts["prover_explain_flag"] = True
    elif el in ["-explain", "--explain"]:
      opts["prover_explain_flag"] = True
    elif el in ["-json", "--json"]:
      opts["json_flag"] = True
    elif el in ["-jsonlogic", "--jsonlogic"]:
      opts["show_logic_flag"] = True
      opts["prover_explain_flag"] = True
      opts["json_flag"] = True
    elif el in ["-cache", "--cache"]:
      opts["use_cache_flag"] = True
    elif el in ["-clearcache", "--clearcache"]:
      opts["clearcache_flag"] = True
    elif el in ["-think", "--think"]:
      # -think alone → True; -think N → integer budget
      if elpos + 1 < len(params):
        try:
          opts["think_flag"] = int(params[elpos + 1])
          skippos = 1
        except ValueError:
          opts["think_flag"] = True
      else:
        opts["think_flag"] = True
    elif el in ["-nollmcache", "--nollmcache"]:
      # LLM response caching is ON by default; this disables it for this run
      opts["use_llm_cache_flag"] = False
    elif el in ["-nogeminicache", "--nogeminicache"]:
      # Gemini context caching (cachedContents API) is ON by default; this
      # disables it, so the sysprompt is sent inline on every call.
      opts["use_gemini_cache_flag"] = False
    elif el in ["-geminicache", "--geminicache"]:
      # Accepted and ignored: caching is now the default.  Kept so older
      # command lines and scripts keep working.
      opts["use_gemini_cache_flag"] = True
    elif el in ["-nosemnormal", "--nosemnormal"]:
      opts["nosemnormal_flag"] = True
    elif el in ["-nosolve", "--nosolve"]:
      opts["prover_nosolve_flag"] = True
    elif el in ["-rawresult", "--rawresult"]:
      opts["prover_rawresult_flag"] = True
    elif el in ["-prover", "--prover"]:
      opts["show_prover_flag"] = True
    elif el in ["-simple", "--simple"]:
      opts["nocontext_flag"] = True
      opts["noexceptions_flag"] = True
      opts["noproptypes_flag"] = True
    elif el in ["-nocontext", "--nocontext"]:
      opts["nocontext_flag"] = True
    elif el in ["-noexceptions", "--noexceptions"]:
      opts["noexceptions_flag"] = True
    elif el in ["-simpleprops", "--simpleprops"]:
      opts["noproptypes_flag"] = True
      opts["noexceptions_flag"] = True
    # --- Event-encoding base: one mutually-exclusive selector. ---
    elif el in ["-event", "--event"]:
      if elpos + 1 >= len(params):
        print("Error: -event requires a mode (neodavidson|davidson|flat|flatroles)")
        sys.exit(0)
      mode = params[elpos + 1]
      if mode not in ("neodavidson", "davidson", "flat", "flatroles"):
        print("Error: unknown -event mode:", mode,
              "(expected neodavidson|davidson|flat|flatroles)")
        sys.exit(0)
      opts["event_base"] = mode
      skippos = 1
    # --- Additive abstraction primitives (compose with any base). ---
    elif el in ["-existfold", "--existfold"]:
      opts["existfold_flag"] = True
    elif el in ["-entitymerge", "--entitymerge"]:
      opts["entitymerge_flag"] = True
    elif el in ["-guarddrop", "--guarddrop"]:
      opts["guarddrop_flag"] = True
    elif el in ["-bridges", "--bridges"]:
      opts["bridges_flag"] = True
    elif el in ["-dropdefinites", "--dropdefinites"]:
      opts["dropdefinites_flag"] = True
    elif el in ["-localantonyms", "--localantonyms"]:
      opts["localantonyms_flag"] = True
    elif el in ["-typeenrich", "--typeenrich"]:
      opts["typeenrich_flag"] = True
    elif el.startswith("-typeenrich=") or el.startswith("--typeenrich="):
      opts["typeenrich_flag"] = True
      opts["typeenrich_gates"] = _parse_te_gates(el.split("=", 1)[1])
    # --- Abstraction presets: pure expansions into primitives (read nowhere
    #     else in the pipeline). -abstract / -abstract-roles / -abstract-max. ---
    elif el in ["-litbridge", "--litbridge"]:
      explicit_on.add("litbridge_flag")
    elif el in ["-nolitbridge", "--nolitbridge"]:
      opts["nolitbridge_flag"] = True
    elif el in ["-summary", "--summary"]:
      opts["summary_flag"] = True
    elif el in ["-summary-json", "--summary-json"]:
      opts["summary_json_flag"] = True
    elif el in ["-critic", "--critic"]:
      explicit_on.add("critic_flag")
    elif el in ["-nocritic", "--nocritic"]:
      opts["nocritic_flag"] = True
    elif el in ["-graphtrans", "--graphtrans"]:
      explicit_on.add("graphtrans_flag")
    elif el in ["-nographtrans", "--nographtrans"]:
      opts["nographtrans_flag"] = True
    elif el in ["-graphbridge", "--graphbridge"]:
      # layer 2 searches layer 1's theory, so it turns layer 1 on as well
      explicit_on.add("graphbridge_flag")
      explicit_on.add("graphtrans_flag")
    elif el in ["-nographbridge", "--nographbridge"]:
      opts["nographbridge_flag"] = True
    elif el in ["-stack", "--stack", "-stack-closed", "--stack-closed",
                "-stack-open", "--stack-open"]:
      # A flag set assigns all six stage keys, so it fully replaces whatever
      # an earlier set or preset put there.  Round 1 of the resolution order.
      _set_stages(opts, litbridge=("open" in el),
                  graphbridge=("closed" not in el))
    elif el in ["-abstract", "--abstract", "-abstract-roles", "--abstract-roles",
                "-abstract-max", "--abstract-max"]:
      opts["event_base"] = "flatroles" if ("roles" in el or "max" in el) else "flat"
      opts["entitymerge_flag"] = True
      opts["guarddrop_flag"] = True
      opts["bridges_flag"] = True
      opts["dropdefinites_flag"] = True
      opts["typeenrich_flag"] = True
      opts["localantonyms_flag"] = True
      opts["noproptypes_flag"] = True
      if "max" in el:
        opts["prenorm_flag"] = True
        opts["propclass_flag"] = True
        opts["numtype_flag"] = True
        opts["compasym_flag"] = True
        opts["nominalretry_flag"] = True
        opts["negretry_flag"] = True
        # the converter preset plus the open-world stack
        _set_stages(opts, litbridge=True, graphbridge=True)
    elif el in ["-propclass", "--propclass"]:
      opts["propclass_flag"] = True
    elif el in ["-fallback_norm", "--fallback_norm"]:
      explicit_on.add("fallback_norm_flag")
    elif el in ["-fallback_hyp", "--fallback_hyp"]:
      explicit_on.add("fallback_hyp_flag")
    elif el in ["-nofallback_norm", "--nofallback_norm"]:
      opts["nofallback_norm_flag"] = True
    elif el in ["-nofallback_hyp", "--nofallback_hyp"]:
      opts["nofallback_hyp_flag"] = True
    elif el in ["-nofallback", "--nofallback"]:
      opts["nofallback_norm_flag"] = True
      opts["nofallback_hyp_flag"] = True
    elif el in ["-numtype", "--numtype"]:
      opts["numtype_flag"] = True
    elif el in ["-compasym", "--compasym"]:
      opts["compasym_flag"] = True
    elif el in ["-prenorm", "--prenorm"]:
      opts["prenorm_flag"] = True
    elif el in ["-noprenorm", "--noprenorm"]:
      opts["prenorm_flag"] = False
    elif el in ["-s2split", "--s2split"]:
      opts["s2split_flag"] = True
    elif el in ["-nocrossstage", "--nocrossstage"]:
      opts["crossstage_retry_flag"] = False
    elif el in ["-llm", "--llm"]:
      if elpos + 1 >= len(params):
        print("-llm requires a provider name: gpt, claude, gemini, or deepseek")
        sys.exit(0)
      llm = params[elpos + 1]
      skippos = 1
    elif el in ["-version", "--version"]:
      if elpos + 1 >= len(params):
        print("-version requires a model version string")
        sys.exit(0)
      llm_version = params[elpos + 1]
      skippos = 1
    elif el in ["-combined-instr", "--combined-instr"]:
      if elpos + 1 >= len(params):
        print("-combined-instr requires a path to a combined instructions prompt file")
        sys.exit(0)
      opts["combined_instr_file"] = params[elpos + 1]
      opts["combined_flag"] = True   # presence of -combined-instr turns single-stage mode on
      skippos = 1
    elif el in ["-combined-examples", "--combined-examples"]:
      if elpos + 1 >= len(params):
        print("-combined-examples requires a path to a combined examples prompt file")
        sys.exit(0)
      opts["combined_examples_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-combined-checklist", "--combined-checklist"]:
      if elpos + 1 >= len(params):
        print("-combined-checklist requires a path to a combined checklist prompt file")
        sys.exit(0)
      opts["combined_checklist_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-directanswer", "--directanswer"]:
      if elpos + 1 >= len(params):
        print("-directanswer requires a path to a direct-answer prompt file")
        sys.exit(0)
      opts["directanswer_file"] = params[elpos + 1]
      opts["directanswer_flag"] = True   # answer with one LLM call, no pipeline
      skippos = 1
    elif el in ["-seconds", "--seconds"]:
      if elpos + 1 >= len(params):
        print("-seconds takes an integer parameter")
        sys.exit(0)
      try:
        n = int(params[elpos + 1])
      except:
        print("-seconds takes an integer parameter")
        sys.exit(0)
      if n < 1:
        print("-seconds takes an integer parameter 1 or more")
        sys.exit(0)
      opts["prover_seconds"] = n
      opts["prover_seconds_cli"] = True
      skippos = 1
    elif el in ["-printlevel", "--printlevel"]:
      if elpos + 1 >= len(params):
        print("-printlevel takes an integer parameter")
        sys.exit(0)
      try:
        n = int(params[elpos + 1])
      except:
        print("-printlevel takes an integer parameter")
        sys.exit(0)
      if n < 10:
        print("-printlevel takes an integer parameter 10 or more")
        sys.exit(0)
      opts["prover_print"] = n
      skippos = 1
    elif el in ["-gkin", "--gkin"]:
      if elpos + 1 >= len(params):
        print("-gkin takes a file name as a parameter")
        sys.exit(0)
      opts["gkin_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-strategy", "--strategy"]:
      if elpos + 1 >= len(params):
        print("-strategy takes a file name as a parameter")
        sys.exit(0)
      opts["prover_strategy"] = params[elpos + 1]
      skippos = 1
    elif el in ["-axioms", "--axioms"]:
      axiomfiles = []
      fpos = 1
      while elpos + fpos < len(params):
        if not params[elpos + fpos] or params[elpos + fpos].startswith("-"):
          break
        axiomfiles.append(params[elpos + fpos])
        fpos += 1
      skippos = fpos - 1
      opts["prover_axiomfiles"] = axiomfiles
    elif el in ["help", "-help", "--help"]:
      print(helptext)
      sys.exit(0)
    elif el and el[0] == "-":
      print("Key " + el + " is not recognized.")
      print(helptext)
      sys.exit(0)
    elif (len(el) < 50 and
          len(el.split(".")) == 2 and
          len(el.split(".")[1]) > 1 and
          len(el.split(" ")) == 1):
      # a filename
      try:
        f = open(el, "r")
        textpart = f.read()
        f.close()
      except:
        print("Could not read from the file " + el)
        sys.exit(0)
    else:
      # normal text
      textpart = el

    if text and textpart:
      text = text + " " + textpart
    elif textpart:
      text = textpart

  # Round 2 of the resolution order: an explicit stage switch sets its key
  # True whatever its position relative to a preset or a flag set, so
  # `-stack-closed -litbridge` and `-litbridge -stack-closed` mean the same.
  for _key in explicit_on:
    opts[_key] = True

  # Round 3: the cancels are applied after the whole line and win over both
  # rounds above, so `-nolitbridge` beats `-litbridge`, `-stack-open` and the
  # `-abstract-max` that turns the literal bridge on, wherever each stands.
  if opts.get("nolitbridge_flag"):
    opts["litbridge_flag"] = False
  if opts.get("nographbridge_flag"):
    opts["graphbridge_flag"] = False
  if opts.get("nocritic_flag"):
    opts["critic_flag"] = False
  if opts.get("nographtrans_flag"):
    # layer 2 searches layer 1's theory, so cancelling layer 1 cancels both
    opts["graphtrans_flag"] = False
    opts["graphbridge_flag"] = False
  if opts.get("nofallback_norm_flag"):
    opts["fallback_norm_flag"] = False
  if opts.get("nofallback_hyp_flag"):
    opts["fallback_hyp_flag"] = False

  return (text, opts)

helptext = """call solve.py with a natural language text like
"Elephants are big. John is an elephant. Who is big?"
and/or a filename as an argument, with optional keys:

output level (hierarchy — each level includes everything from previous levels):
 -explain   : show English proof explanation
 -logic     : show simplified ASU texts, sentences-mapped-to-clauses, logic under proof steps
 -details   : show stage-1/2 JSON, prover input/output JSON
 -debug     : show raw LLM responses, prover params, full pipeline trace

output format:
 -json      : show all logic in raw JSON instead of traditional pred(arg,...) syntax
 -jsonlogic : shortcut for -logic -json
 -gkin FILE : save the GK prover input to FILE (with the GK command as a comment)
 -summary   : one block at the end, whatever the output level: the answer, which
              stage produced it (front door / graphtrans / litbridge / graphbridge
              / critic), the front door's own answer, and the LLM calls per stage
 -summary-json : the same block as one JSON line, for scripts

other:
 -nosolve   : parse to logic only, do not run the prover
 -rawresult : output only the raw JSON result from the prover
 -cache     : cache GK prover results (prover cache is OFF by default)
 -help      : output this helptext

LLM caching (ON by default — cached per provider, version, all parameters and input):
 -nollmcache  : disable LLM response caching for this run
 -clearcache  : clear all caches (LLM, proof, parse) and exit
 -nogeminicache : disable Gemini context caching (on by default for large sysprompts)

semantic normalisation (ON by default):
 -nosemnormal : disable antonym folding and canonical word substitution

LLM selection:
 -llm NAME    : LLM provider: gpt, claude, gemini, or deepseek (default: from llmcall.py config)
 -version VER : model version string, e.g. claude-sonnet-4-6, gpt-5.1

alternative parsing shapes (replace the default two-stage English->logic parse):
 -s2split     : one Stage-2 LLM call per Stage-1 sentence package; outputs joined
                into one logic (failed sentences skipped unless they hold the
                question; locally-invented worlds renumbered to fresh indices).
                Also applies the cross-sentence shape-unification repair
                (predicate rename, shape bridges, compound composition,
                broad-supertype isa) that reconciles the divergent per-sentence
                parses
 -combined-instr FILE     : single-stage parsing -- one LLM call, English -> logic,
                            no Stage-1 JSON (enables single-stage mode)
 -combined-examples FILE  : combined examples prompt file (optional)
 -combined-checklist FILE : combined checklist prompt file (optional)
 -directanswer FILE       : answer the question directly with one LLM call (no
                            logic, no prover); test-set agnostic

logic conversion / representation (transform the Stage-2 logic before the prover):
 event-encoding base -- one selector, default neodavidson:
  -event MODE   neodavidson : reified neo-Davidsonian events (default)
                davidson    : compact event(V,A,O,E), keep handle + adjuncts
                flat        : flat relational is_rel2(V,subj,obj)
                flatroles   : flat relational, eventprop-tagged object
 additive abstraction primitives (compose with any -event base):
  -entitymerge   : proper-noun entity canonicalization + set-label coreference
  -typeenrich[=GATES] : taxonomy/isa enrichment; bare = all six sub-gates, or a
                  comma list of super,gender,nametype,compound,plural,gnoun (use
                  -name to exclude, `all` for all; e.g. -typeenrich=all,-plural)
  -guarddrop     : drop redundant antecedent isa type guards (needs a fold base)
  -bridges       : frame/bridge axioms: rel2<->event, occasion-location,
                   in-haspart, reflexive-property (needs -event flat/flatroles)
  -dropdefinites : skip $theof1 definite reification; leave definites as relations
  -localantonyms : restrict antonym folding to the problem + axiom vocabulary
  -existfold     : (L2) fold "exists Y. isa(C,Y) & has_part/have(X,Y)" into
                   has_property([$has_part/$have,C], X) + named-witness bridge
  -propclass     : property<->class canonicalization: bridge isa(W,X)<->has_property(W,X)
                   for a concept the flat fold left in both shapes (safe isa->has_property;
                   promote has_property->isa only for a nominal compound). (in -abstract-max)
  -numtype       : numeric-literal typing: parse numeral strings ("34") to int/float and
                   materialize isa(number/integer/...,N) when -isa(...,N) is demanded. (in -abstract-max)
  -compasym      : comparative asymmetry: for a strict-scalar adjective R used as
                   is_rel2(R,X,Y), emit is_rel2(R,X,Y)->-is_rel2(R,Y,X). (in -abstract-max)
 simplification:
  -simple        : no context, no exceptions, simple properties (the three below)
  -nocontext     : no context (time, situation) information in logic
  -noexceptions  : no exception (blocker) information in logic
  -simpleprops   : simplified properties without strength/type parameters
 abstraction presets (pure expansions into the primitives above):
  -abstract       : -event flat + entitymerge + guarddrop + bridges + dropdefinites
                    + typeenrich + localantonyms + simpleprops
  -abstract-roles : as -abstract but -event flatroles (eventprop-tagged objects)
  -abstract-max   : as -abstract-roles + prenorm + propclass + numtype + compasym
                    + nominalretry + negretry, plus the open-world repair stack
                    (all six stages below). prenorm, nominalretry and negretry can
                    make live LLM calls, and so does every stage but the two
                    fallbacks.
 -prenorm       : pre-Stage-1 LLM wording normalisation (composable; FOLIO base)
 -noprenorm     : force prenorm off after a preset
 -nocrossstage  : disable the cross-stage guard-retry

the repair stack: six stages, run in this order when the front door leaves the
question unresolved, each stopping the rest once it answers definitely --
 fallback_norm, fallback_hyp, critic, graphtrans, litbridge, graphbridge.
`-summary` prints stages_enabled, and every case JSON carries it.

 flag sets (each assigns all six stage keys, so it replaces an earlier set):
  -stack         : fallbacks + critic + graphtrans + graphbridge, no literal
                   bridge. Material of unknown origin: the general default.
  -stack-closed  : fallbacks + critic + graphtrans. Known closed-world material
                   (core-like, FOLIO-like), where neither bridge pays.
  -stack-open    : all six. Known open-world material (EntailmentBank-like).
 resolution order:
  1. presets and flag sets, left to right; a later one overwrites an earlier one
  2. an explicit stage switch turns its stage on from any position on the line
  3. a cancel wins over both, wherever it stands

 the stages:
  -fallback_norm : ON BY DEFAULT. When the front door ends unresolved, convert the
                   same parse again with the token and shape normalizations on,
                   plus the question rewrites the text licenses, and call gk once
                   more. No LLM call, at most two gk calls (DOCUMENTATION.md 16).
  -fallback_hyp  : ON BY DEFAULT. When the question is a conditional and both the
                   front door and fallback_norm ended unresolved, assume the
                   antecedent in an isolated theory and ask the consequent. Nothing
                   is inserted into the ordinary premise set. No LLM call, one gk
                   call (DOCUMENTATION.md 16).
  -critic        : one LLM call audits the translation the front door produced; a
                   blocking finding on its own chain makes Stage 2 run once more
                   with the findings appended. One critique, one rerun
                   (DOCUMENTATION.md 15).
  -graphtrans    : translate the case a second time into open triples, compile it
                   and call gk once. No judge, no bridge (DOCUMENTATION.md 14).
  -litbridge     : propose implication rules over the case's own displayed atoms,
                   compile them beside the stored theory and resubmit to gk. Two
                   rounds (DOCUMENTATION.md 13). Net-harmful on closed-world
                   material, so only -stack-open and -abstract-max turn it on.
  -graphbridge   : invent implications between the open names and search layer 1's
                   theory with them. Turns -graphtrans on as well, since layer 2
                   searches layer 1's theory (DOCUMENTATION.md 14).
 the cancels, each winning from any position:
  -nofallback_norm  -nofallback_hyp  -nofallback (both)
  -nocritic  -nographtrans (cancels graphbridge too)  -nolitbridge  -nographbridge

 settings that are module constants, not flags:
  litbridge_procedure.EXTRAS         the two code-built litbridge channels
  litbridge_grader.MODE              None / "stated" / "any"
  graph_procedure.LIFT               lift a graph proof into the ordinary theory
  graph_procedure.EVIDENCE           "any" / "stated"
  graph_procedure.DEFAULT_SOURCES    the candidate sources layer 2 enumerates
  globals.ABSTRACTION_ROUTES         the order the three routes run in

LLM reasoning:
 -think       : enable medium reasoning/thinking mode (GPT: reasoning_effort=medium;
                Claude: extended thinking; Gemini: requires 2.5+ model;
                DeepSeek: switches to deepseek-reasoner)

controlling the prover:
 -seconds N    : give N seconds for proof search (default 2)
 -prover       : show prover params (also included in -debug)
 -axioms file1.js ... fileN.js : use these files as axioms instead of axioms_std.js
 -strategy file.js : use the given JSON strategy file instead of the default
 -printlevel N : use N>10 to see more of the search process (10 is default, try 12)
"""




# ========= main caller =========

if __name__ == "__main__":
  main()


# =========== the end ==========
