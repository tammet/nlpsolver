#!/usr/bin/env python3
"""The pipeline's entry point: English text in, an answer out, from the command line or as a library.

  english_to_answer(text, options=None, collect=None) -> the answer string

A call first chooses the pipeline (`route_choice`): the experimental action route for texts about actions and plans
(`action_pipeline.py`), or the ordinary pipeline.  One attempt of the ordinary pipeline:

  English text
    -> llmparse.parse_text()           Stage 1: English -> units; Stage 2: units -> logic JSON
    -> logconvert.rawlogic_convert()   logic JSON -> GK clauses
    -> semnormalize                    antonym folding and canonical words
    -> prover.call_prover()            the gk theorem prover: the initial attempt
    -> procproofs.process_proof()      the answer string and its English proof
    -> the retry stages, in order, while the question is open: the two fallbacks, the critic, the graph
       retranslation and the bridges

`ordinary_pipeline` repeats an attempt, at most twice, when it ends in a known downstream error.

The other solve_* files hold the rest: solve_cli.py the command line and the help text, solve_stages.py the stage
order, the rule that runs one stage, the stage rows and the summary record, solve_retries.py the runners of the
retry stages after the fallbacks, and solve_display.py the terminal output.  This module calls their functions
through the module name (`solve_stages.run_stage`), and so do the runners, the checks and the tools.  The run state
(the provider, the debug switch, the critic flags) stays in this module; the other files read it through
`import solve`.

LLM calls are cached (`cache.db`).  The options: docs/reference/command-line.md.
"""
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

if __name__ == "__main__":
  # Run as a script, this module is __main__.  The solve_* modules read the run state through `import solve`, which
  # must find this module and not load a second copy with empty state.
  sys.modules.setdefault("solve", sys.modules[__name__])

import contextlib
import re
import signal
import threading
import unicodedata

# configuration and globals (also puts 'options' into this module's namespace)
from globals import *                                           # noqa: F401,F403
import globals

import cache
import lc_encoding
import llmcall
import llmparse
import prover
import semnormalize
from logconvert import rawlogic_convert
from procproofs import process_proof

import solve_cli
import solve_display
import solve_retries
import solve_stages


# ======== the run state ========
#
# Module globals, because the runners set them per case (`solve.llm = ...`) and the solve_* modules read them.

# Print pipeline stages and intermediate results to stdout (-debug)
debug = False

# LLM provider / version overrides passed through to llmparse / llmcall.
# None means use the defaults configured in llmparse.py / llmcall.py.
llm         = None   # "gpt" | "claude" | "gemini" | "deepseek" | None
llm_version = None   # model version string, or None for default
max_tokens  = None   # int, or None for default

# How deeply the pipeline is calling itself: the critique pass's rerun and the
# downstream-error retry run the whole thing again from inside it.
_depth = 0

# Where the current attempt's calls begin in `llmcall.call_log`.  Set at the
# top of every attempt by `ordinary_attempt`.
call_log_mark = 0


# True once the critique pass has run for the case now being answered.  Reset
# by `english_to_answer`, which is where a case run begins.
critiqued = False

# True while the critique pass's rerun is running.  The rerun re-enters the
# whole pipeline, and without this the abstraction routes would run inside it
# and again in the outer run.
in_critic_rerun = False

# english_to_answer printed the input under -logic: the ordinary pipeline's first attempt does not print it again
_text_shown = False



def main():
  """The command line: answer the text of sys.argv and print the answer.  The exit status is 1 for an answer that
  starts with Error, 2 for a bad command line, 0 otherwise."""
  text, opts = solve_cli.parse_cmd_line()
  if opts.get("clearcache_flag"):
    counts = cache.clear_all_caches()
    print("Cache cleared: {:d} LLM, {:d} proof, {:d} parse entries removed.".format(
      counts["llm"], counts["proof"], counts["parse"]))
    return 0
  if not text:
    print("No text given.\n" + solve_cli.helptext)
    return 2
  try:
    # a formal action record calls no model: its provider name is checked, its key is not required
    llmcall.validate_provider_configuration(
      llm, llm_version, require_key=not (opts.get("formal_flag") and not opts.get("noactions_flag")))
  except (llmcall.InvalidProviderError, llmcall.MissingApiKeyError) as exc:
    print("Error: " + str(exc))
    return 2
  result = english_to_answer(text, opts)
  if opts.get("show_logic_flag"):
    print("\n=== result ===\n")
  print(result)
  return 1 if solve_stages.is_error(result) else 0


# ======== the entry point: which pipeline answers ========

def english_to_answer(text, options=None, collect=None):
  """Full pipeline, with the downstream-error corrective retry around it.

  The retry loop runs the whole pipeline again on a downstream error, so the
  summary block is held back until the loop is done and only the last one is
  printed: a case run reports once, whatever it took to answer it.
  """
  global critiqued, _text_shown
  critiqued = False
  solve_display.suppress(True)
  # This is the case entry: the critic's rerun re-enters
  # `ordinary_attempt`, not this function, so resetting here cannot
  # discard the outer stage or the running call count.
  prover.reset_stages()
  llmcall.reset_call_limit()
  try:

    # Every call this case makes -- parse, critic, critic rerun, graph, bridges
    # -- is pinned to the run's own provider and version.  A call that names
    # another model raises instead of quietly answering.
    with llmcall.locked_model(llm, llm_version):
      route = route_choice(text, options)
      if collect is not None:
        collect["route_choice"] = {k: v for k, v in route.items() if k != "options"}
      if route.get("error"):
        if collect is not None:
          collect["answer"] = route["error"]
        return route["error"]
      if _shows_logic(options):
        # -logic and up: the input, then which pipeline answers it; the ordinary pipeline does not print the input
        # again for its first attempt
        solve_display.print_input(text, bool((route["options"] or {}).get("formal_flag")))
        solve_display.print_route(route)
        _text_shown = True
      if route["route"] == "actions":
        # the action route: its own translation, compiler and prover profile; it enters no ordinary stage and
        # writes nothing into globals.options
        import action_pipeline
        answer = action_pipeline.run(text, route["options"], collect, llm=llm, version=llm_version,
                                     max_tokens=max_tokens)
      else:
        answer = ordinary_pipeline(text, route["options"], collect)
        if collect is not None:
          # the ordinary pipeline rebuilds the collector; the choice is kept
          collect["route_choice"] = {k: v for k, v in route.items() if k != "options"}
      solve_display.set_route(route)
      return answer
  finally:
    _text_shown = False
    solve_display.suppress(False)
    solve_display.flush()


def _shows_logic(options):
  o = options or {}
  return bool(o.get("show_logic_flag") or o.get("show_details_flag") or o.get("debug_print_flag"))


_ACTION_KEYS = ("actions_flag", "plan_depth", "action_backend", "formal_flag")
_ROUTE_KEYS = _ACTION_KEYS + ("noactions_flag",)


def _key_names(keys):
  return ", ".join("-" + k.replace("_flag", "").replace("_", "-") for k in keys)


def route_choice(text, options):
  """Which pipeline a call goes to, and with which options: {"mode", "route", "verdict", "signals", "options"} or
  {"error"}.

  -actions sends every text to the action route and -noactions every text to the ordinary pipeline; giving both is
  an error, and so is an action option with -noactions.  Without either (mode `auto`), a formal input goes to the
  action route, and otherwise the cheap classifier decides (`route_classify.classify`): `actions` goes to the action
  route; `ordinary` and `unclear` go to the ordinary pipeline.  An automatic call to the action route gets the action
  keys and the shared keys (model calls, caches, the GK time, output) only, so an ordinary preset or stage switch
  applies to the ordinary pipeline alone; an automatic ordinary call drops the action keys."""
  opts = options or {}
  if opts.get("actions_flag") and opts.get("noactions_flag"):
    return {"error": "Error: -actions and -noactions exclude each other"}
  if opts.get("actions_flag"):
    return {"mode": "actions", "route": "actions", "options": options}
  if opts.get("noactions_flag"):
    extra = [k for k in _ACTION_KEYS if opts.get(k) is not None and opts.get(k) is not False]
    if extra:
      return {"error": "Error: %s cannot be combined with -noactions" % _key_names(extra)}
    return {"mode": "noactions", "route": "ordinary", "options": _without(options, _ROUTE_KEYS)}
  if opts.get("formal_flag"):
    choice = {"verdict": "actions", "signals": ["formal_input"]}
  else:
    import route_classify
    choice = route_classify.classify(text)
  if choice["verdict"] == "actions":
    import action_pipeline
    keep = set(action_pipeline.ACTION_KEYS) | set(action_pipeline.SHARED_KEYS)
    action_opts = {k: v for k, v in opts.items() if k in keep or k.startswith("_")}
    action_opts["actions_flag"] = True
    return dict(choice, mode="auto", route="actions", options=action_opts)
  return dict(choice, mode="auto", route="ordinary", options=_without(options, _ROUTE_KEYS))


def _without(options, keys):
  """`options` itself when it holds none of `keys`, else a copy without them."""
  if not options or not any(k in options for k in keys):
    return options
  return {k: v for k, v in options.items() if k not in keys}


# ======== the downstream-error corrective retry ========
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

MAX_DOWNSTREAM_RETRIES = 2

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


def downstream_hint(answer):
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


def ordinary_pipeline(text, options=None, collect=None):
  """The ordinary pipeline, with the downstream-error retry around it."""
  correction = ""
  fired = []
  answer = None
  for attempt in range(MAX_DOWNSTREAM_RETRIES + 1):
    inner = {} if collect is not None else None
    # The prover records into this attempt's own collector.  A stage that runs
    # gk without one to hand -- the graph route calls the prover directly --
    # is recorded here too, and `prover.stage` says which stage owns it.
    with (prover.collector(inner) if inner is not None
          else contextlib.nullcontext()):
      answer = ordinary_attempt(text, options, inner,
                                       stage2_corrective=correction)
    if collect is not None:
      collect.clear()
      collect.update(inner)
    hint = None if globals.options.get("nofix_downstream") \
           else downstream_hint(answer)
    if hint is None or attempt == MAX_DOWNSTREAM_RETRIES:
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
    collect.setdefault("stages_enabled", solve_stages.stages_enabled())
  return answer


# ======== one attempt of the ordinary pipeline ========
#
# An attempt translates and converts the text, proves the question once (the initial attempt, `front_door` in the
# records), then runs the retry stages in PIPELINE_ORDER while the question is open.  The phases share one record,
# `run`: the attempt's inputs, the answer so far, the stage that gave it, the theory and the gk call behind it, and
# the stage rows.

def ordinary_attempt(text, options=None, collect=None,
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
  global call_log_mark
  # This attempt's calls start here; the downstream-error retry keeps the log
  # growing.  Only the outermost attempt marks it: the critic's rerun re-enters
  # this function, and marking there would drop the critic's own call out of
  # the window the stage rows are computed from.
  if not in_critic_rerun:
    call_log_mark = len(llmcall.call_log)
  global _depth
  _depth += 1
  try:
    return _attempt_body(text, options, collect, stage2_corrective,
                                   stage1_corrective, stage1_json)
  finally:
    _depth -= 1


def _attempt_body(text, options=None, collect=None,
                            stage2_corrective="", stage1_corrective="",
                            stage1_json=None):
  """One attempt: translate and convert, prove, then the retry stages while the question is open.  Returns the answer
  string; an early failure returns a string that starts with Error."""
  global _text_shown
  if options is None:
    options = {}
  if collect is not None:
    options["_collect"] = collect
    options["prover_explain_flag"] = True
  if options:
    globals.set_global_options(options)

  show_details = options and options.get("show_details_flag")
  show_logic   = options and options.get("show_logic_flag")

  # -logic+: show input text at the top, unless english_to_answer just printed it
  if show_logic and not _text_shown:
    print(text)
  _text_shown = False

  if globals.options.get("directanswer_flag"):
    return _direct_answer(text, collect, show_logic or show_details)

  got = _translate_and_convert(text, options, collect, stage2_corrective, stage1_corrective, stage1_json)
  if isinstance(got, str):
    return got
  s1_json, s2_json, logic = got

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

  run = {"text": text, "s1_json": s1_json, "s2_json": s2_json, "options": options, "collect": collect,
         # the answer so far, and the stage that gave it ("none" while the question is open)
         "answer": answer, "answered_by": "front_door" if not solve_stages.unresolved(answer) else "none",
         # the theory behind the answer so far, and the last proof result
         "logic": logic, "proof_result": proof_result,
         # the gk call that produced the final answer when a later stage answered.  Every later `call_prover`
         # overwrites `collect["gk_command"]`, so a stage that RAN without answering would otherwise leave its
         # command at the top level; the top-level `proof` and `gk_command` are set from this at the end.
         "answering": None,
         # which stage answered the critic's retranslation, when the critic answered
         "rerun_answered_by": None,
         # the initial attempt's own answer and gk call, kept beside a later stage's
         "front_door_answer": answer, "front_door_proof": proof_result,
         "front_door_gk_command": (collect or {}).get("gk_command"),
         # What each stage did: one row per stage, in stage order.  A separate information block, printed by
         # `-summary` and by `-logic` and above, and written to the case record as `stages`.
         "stage_rows": [],
         # the graph retranslation's record, which the graph bridge reuses
         "graph": {"graphtrans": None}}
  solve_display.reset_announced()
  solve_stages.note_stage(run["stage_rows"], "front_door", True, answer, theory=logic,
              provider=llm, version=llm_version)
  _run_fallbacks(run)
  _run_critic_stage(run, show_logic, show_details)
  _run_abstraction_routes(run, show_logic, show_details)
  return _finish_attempt(run)


def _direct_answer(text, collect, show):
  """-directanswer: ONE LLM call with the given prompt answers the text, skipping the parse -> logic -> prover
  pipeline.  Works for any test set."""
  import directanswer
  prompt_file = globals.options.get("directanswer_file")
  answer = directanswer.answer_directly(
    text, prompt_file, llm=llm, version=llm_version, tokens=max_tokens,
    think=globals.options.get("think_flag", False))
  if collect is not None:
    collect["answer"] = answer
    collect["directanswer"] = {"prompt": prompt_file}
  if show:
    print(answer)
  return answer


def _translate_and_convert(text, options, collect, stage2_corrective, stage1_corrective, stage1_json):
  """Stage 1 and Stage 2, the conversion to clauses and the semantic normalization.  Returns (s1_json, s2_json,
  logic), or an error string."""
  show_details = options and options.get("show_details_flag")
  show_logic   = options and options.get("show_logic_flag")
  # Resolve which LLM is being used (for display in headers).
  actual_llm = llm or llmcall.use_llm
  think_flag = globals.options.get("think_flag", False)

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
      solve_display.show_simplified_to(text, s1_json)

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
      collect["clauses"] = build_clauses_with_nl(logic, s1_json)

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
    # `ordinary_pipeline` records this in `collect`, as it does for every
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
  return s1_json, s2_json, logic


def _run_fallbacks(run):
  """The two abstention fallbacks, before the critic and the abstraction routes.  Each converts the SAME
  Stage-1/Stage-2 parse a second time and calls gk again; neither makes an LLM call.  They run only while the
  question is open, so a definite answer of the initial attempt is never disturbed, and the first definite fallback
  answer stops the rest."""
  collect = run["collect"]
  records = {}
  for name, key in (("fallback_norm", "fallback_norm_flag"),
                    ("fallback_hyp", "fallback_hyp_flag")):
    def run_fallback(_n=name):
      if _n == "fallback_norm":
        import fallback_norm as _m
      else:
        import fallback_hyp as _m
      got = _m.run(run["s1_json"], run["s2_json"], run["text"], run["logic"], run["options"])
      records[_n.split("_", 1)[1]] = got["record"]
      # a fallback reports `answered` itself; the driver reads `answer`
      return got if got.get("answered") else {"answer": None}

    def adopt(got):
      run["logic"] = got["logic"]
      run["proof_result"] = got["proof"]
      run["answering"] = {"proof": got["proof"], "gk_command": (collect or {}).get("gk_command")}
      if collect is not None and not globals.options.get("nofinaltrace"):
        collect["final_clauses"] = got["logic"]

    def note_error(msg, _n=name):
      records[_n.split("_", 1)[1] + "_error"] = msg

    run["answer"], by = solve_stages.run_stage(name, globals.options.get(key), run["answer"], run["stage_rows"],
                                               run_fallback,
                                  adopt=adopt, announce=solve_display.announce_stage, on_error=note_error)
    if by:
      run["answered_by"] = by
  if records and collect is not None:
    records["answered_by"] = (run["answered_by"] if run["answered_by"] in ("fallback_norm", "fallback_hyp")
                              else None)
    collect["fallback"] = records


def _run_critic_stage(run, show_logic, show_details):
  """The critique pass (-critic), before any abstraction route.  One call audits the translation the initial attempt
  produced.  On RETRANSLATE, Stage 2 (or Stage 1 and 2) runs once more with the findings appended, and the ordinary
  converter and gk follow.  One critique, one rerun, then stop."""
  collect = run["collect"]

  def critique():
    global critiqued
    critiqued = True
    got = solve_retries.run_critic(run["text"], run["s1_json"], run["s2_json"], run["logic"], run["answer"], llm,
                                   llm_version, max_tokens, run["options"], collect=collect,
                                   loud=debug or show_details or show_logic
                                   or globals.options.get("prover_explain_flag"))
    # The experimental acceptance check refuses an answer by making the stage look unresolved, so the ordinary
    # rules carry the run on to the next stage.
    if got and got.get("answer") is not None and not solve_retries.acceptance(
        {"answered_by": "critic", "stage1": run["s1_json"], "stage2": run["s2_json"], "proof": got.get("proof"),
         "critic": ((collect or {}).get("critic") or got.get("critic_record") or {})}, collect):
      got = dict(got)
      got["answer"] = None
    return got

  def adopt(got):
    run["rerun_answered_by"] = got.get("rerun_answered_by")
    run["answering"] = {"proof": got.get("proof"), "gk_command": got.get("gk_command")}
    if got.get("logic") is not None:
      run["logic"] = got["logic"]
      if collect is not None and not globals.options.get("nofinaltrace"):
        collect["final_clauses"] = got["logic"]

  run["answer"], by = solve_stages.run_stage(
    "critic", solve_retries.should_critique_enabled(), run["answer"], run["stage_rows"], critique, adopt=adopt,
    announce=solve_display.announce_stage, tag="critic",
    disabled_why=("off" if not globals.options.get("critic_flag")
                  else "not needed: the critique already ran in this run"))
  if by:
    run["answered_by"] = "critic"


def _run_abstraction_routes(run, show_logic, show_details):
  """The abstraction routes, in the order `solve_stages.abstraction_order` gives.  Each route runs only while the
  question is open, and only when its own flag is on.  A route not named in the order never runs, whatever its flag
  says: the order is the list of routes this run may use."""
  collect = run["collect"]
  # the graph blocks appear from `-explain` up, the literal bridge's from `-logic` up
  loud = debug or show_details or show_logic or globals.options.get("prover_explain_flag")
  routes = {"graphtrans": solve_retries.run_graphtrans,
            "litbridge": solve_retries.run_litbridge,
            "graphbridge": solve_retries.run_graphbridge}
  for name in solve_stages.abstraction_order():
    def run_route(_n=name):
      got = routes[_n](run["text"], run["s1_json"], run["s2_json"], run["logic"], run["answer"], llm, llm_version,
                       max_tokens, run["options"], loud=loud, verbose=debug or show_details, collect=collect,
                       state=run["graph"])
      if got and got.get("answer") is not None and _n == "graphtrans" and not solve_retries.acceptance(
          {"answered_by": _n, "stage1": run["s1_json"], "stage2": run["s2_json"],
           "graphtrans": ((collect or {}).get(_n) or solve_retries.graphtrans_record(got))}, collect):
        got = dict(got)
        got["answer"] = None
      return got

    def adopt(got):
      run["answering"] = {"proof": got.get("proof"), "gk_command": got.get("gk_command")}
      if got.get("logic") is not None:
        run["logic"] = got["logic"]
        if collect is not None and not globals.options.get("nofinaltrace"):
          collect["final_clauses"] = got["logic"]

    run["answer"], by = solve_stages.run_stage(name, solve_stages.route_enabled(name), run["answer"],
                                               run["stage_rows"], run_route,
                                  adopt=adopt, announce=solve_display.announce_stage, tag=name)
    if by:
      run["answered_by"] = name


def _finish_attempt(run):
  """Complete the stage rows, write the attempt's record into the collector, print the stages block and the
  summary.  Returns the answer."""
  collect = run["collect"]
  answer, answered_by = run["answer"], run["answered_by"]
  stage_rows = solve_stages.complete_stage_rows(run["stage_rows"], answered_by, collect)
  if collect is not None:
    collect["abstraction_order"] = solve_stages.abstraction_order()
    collect["stages_enabled"] = solve_stages.stages_enabled()
    collect["encoding_experiments"] = lc_encoding.active_experiments()
    collect["stages"] = stage_rows
    collect["pipeline_name"] = globals.options.get("pipeline_name")
    collect["run_outcome"] = solve_stages.run_outcome(answer, stage_rows, answered_by)
    collect["answered_by"] = answered_by
    # the first line only: the explanation, when there is one, is `nl_proof`
    collect["front_door_answer"] = str(
        run["front_door_answer"] or "").split("\n")[0] or None
    collect["llm_call_counts"] = solve_stages.call_counts()
    # Two figures, because they answer two questions.  `llm_accounting` is the
    # whole case, retries included: that is the true cost and what the
    # `-llm-call-limit` counter bounds.  `llm_accounting_stages` is the final
    # attempt only, which is what the stage rows describe, so the rows sum to
    # it exactly.  They differ only when the downstream-error retry ran the
    # pipeline more than once; `downstream_retries` says when.
    collect["llm_accounting"] = llmcall.call_counts()
    collect["llm_accounting_stages"] = {
      "attempted": sum(r["llm_calls"] for r in stage_rows),
      "allowed": sum(r.get("llm_allowed") or 0 for r in stage_rows),
      "cached": sum(r.get("llm_cached") or 0 for r in stage_rows),
      "live": sum(r.get("llm_live") or 0 for r in stage_rows),
      "refused": sum(r.get("llm_refused") or 0 for r in stage_rows),
      "provider_requests": sum(r.get("llm_provider_requests") or 0
                               for r in stage_rows),
    }
    collect["llm_calls_total"] = sum(
        v["calls"] for v in collect["llm_call_counts"].values())
  if _depth == 1:
    solve_display.print_stages(stage_rows)
  if (globals.options.get("summary_flag")
      or globals.options.get("summary_json_flag")) and _depth == 1:
    # only the outermost pipeline run reports: the critique pass's rerun calls
    # this function again from inside it, and that inner run is not a case run
    solve_display.print_summary(answer, answered_by, run["front_door_answer"], run["graph"],
                   rerun_answered_by=run["rerun_answered_by"], stages=stage_rows)

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
    solve_stages.set_answering_call(collect, run["answering"], run["front_door_proof"],
                        run["front_door_gk_command"])
  return answer


# ======== helpers ========

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


def build_clauses_with_nl(logic, s1_json):
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


# ========= main caller =========

if __name__ == "__main__":
  sys.exit(main())


# =========== the end ==========
