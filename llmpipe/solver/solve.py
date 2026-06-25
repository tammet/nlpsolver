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


def english_to_answer(text, options=None, collect=None):
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
      text, llm=llm, version=llm_version, tokens=max_tokens, think=think_flag
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
                                  ("s2_retries", "stage_2_retries")):
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
    if not globals.options.get("nosemnormal_flag"):
      logic = semnormalize.sem_normalize_clauses(logic)
  except _ApiTimeout:
    return ("Error: LLM/parse phase exceeded the %ds api-timeout cap." % int(_api_to))
  finally:
    if _api_armed:
      signal.alarm(0)
      if _api_prev is not None:
        signal.signal(signal.SIGALRM, _api_prev)

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
    if isinstance(proof_result, str) and proof_result.strip():
      # gk returns JSON; store as parsed object so the dump doesn't drown
      # in \" escapes.  Fall back to the raw string if parsing fails (e.g.
      # error messages, "Error: ..." returns).
      try:
        collect["proof"] = json.loads(proof_result)
      except Exception:
        collect["proof"] = proof_result

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
    elif el in ["-geminicache", "--geminicache"]:
      # Gemini context caching (cachedContents API) is OFF by default;
      # this enables uploading the sysprompt once and referencing it on
      # each call, which dodges the per-request input-token cap on large
      # prompts that triggers instant 429s.
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
    elif el in ["-prenorm", "--prenorm"]:
      opts["prenorm_flag"] = True
    elif el in ["-s2split", "--s2split"]:
      opts["s2split_flag"] = True
    elif el in ["-slightcoarse", "--slightcoarse"]:
      opts["slightcoarse_flag"] = True
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

other:
 -nosolve   : parse to logic only, do not run the prover
 -rawresult : output only the raw JSON result from the prover
 -cache     : cache GK prover results (prover cache is OFF by default)
 -help      : output this helptext

LLM caching (ON by default — cached per provider, version, all parameters and input):
 -nollmcache  : disable LLM response caching for this run
 -clearcache  : clear all caches (LLM, proof, parse) and exit
 -geminicache : enable Gemini context caching (cachedContents) for large sysprompts

semantic normalisation (ON by default):
 -nosemnormal : disable antonym folding and canonical word substitution

LLM selection:
 -llm NAME    : LLM provider: gpt, claude, gemini, or deepseek (default: from llmcall.py config)
 -version VER : model version string, e.g. claude-sonnet-4-6, gpt-5.1

alternative parsing shapes (replace the default two-stage English->logic parse):
 -s2split     : one Stage-2 LLM call per Stage-1 sentence package; outputs joined
                into one logic (failed sentences skipped unless they hold the
                question; locally-invented worlds renumbered to fresh indices)
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
 simplification:
  -simple        : no context, no exceptions, simple properties (the three below)
  -nocontext     : no context (time, situation) information in logic
  -noexceptions  : no exception (blocker) information in logic
  -simpleprops   : simplified properties without strength/type parameters
 abstraction presets (pure expansions into the primitives above):
  -abstract       : -event flat + entitymerge + guarddrop + bridges + dropdefinites
                    + typeenrich + localantonyms + simpleprops
  -abstract-roles : as -abstract but -event flatroles (eventprop-tagged objects)
  -abstract-max   : as -abstract-roles + -prenorm (the strongest abstraction)
 -prenorm       : pre-Stage-1 LLM wording normalisation (composable; FOLIO base)
 -nocrossstage  : disable the cross-stage guard-retry
 -slightcoarse  : light shape unification (predicate rename, shape bridges,
                  compound composition, broad-supertype isa); built for -s2split

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
