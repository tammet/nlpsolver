"""The command line of solve.py: the parser, the help text, and the resolution of the retry-stage configuration.

  parse_cmd_line()          sys.argv -> (text, options); sets solve.debug, solve.llm and solve.llm_version
  helptext                   the text of -help
  apply_pipeline(opts, name) the six stage keys of a named configuration (-pipeline NAME)
  finalize_pipeline_name(opts)  the configuration name a resolved option dict records

runtests.py parses the keys it does not define with `parse_cmd_line`, so the two entry points read a key the same
way.  `solve` re-exports every name here.
"""
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#-----------------------------------------------------------------

import sys

import globals
import llmcall
import llmparse
from solve_stages import CANCEL_KEYS, PIPELINES, PIPELINE_ORDER, STACK_OPEN_VECTOR, STAGE_KEYS


_TE_GATES = ("super", "gender", "nametype", "compound", "plural", "gnoun")


def parse_te_gates(spec):
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


def stage_vector(opts):
  """The six stage flags a resolved option dict holds, as a plain dict."""
  return {s: bool(opts.get(s + "_flag", globals.options.get(s + "_flag")))
          for s in PIPELINE_ORDER[1:]}


def names_a_configuration(opts, extra=False):
  """True when the command line said anything about the retry stages."""
  return bool(extra or opts.get("_pipeline_named")
              or (set(opts) & set(STAGE_KEYS))
              or (set(opts) & set(CANCEL_KEYS)))


def finalize_pipeline_name(opts, named=False):
  """The configuration name to record, derived from the FINAL stage vector.

  `-pipeline` used to stamp the name where it was parsed, so a later `-stack*`,
  an explicit stage switch or a cancel left it stale.  The name is now read
  back from what the run actually resolved to.

  A command line that says nothing about the retry stages still gets a name:
  since the adoption it is the default configuration's own name, so an
  ordinary run records `balanced` rather than nothing.
  """
  vec = stage_vector(opts)
  for name, want in PIPELINES.items():
    if vec == want:
      return name
  if vec == STACK_OPEN_VECTOR:
    return "stack-open"
  return "custom"


def apply_pipeline(opts, name):
  """Assign all six stage keys from a named configuration.

  Shared by `solve.py` and `runtests.py` so the two entry points cannot grow
  different meanings for the same word.  Round 1 of the resolution order.
  """
  key = (name or "").strip().lower()
  if key not in PIPELINES:
    raise ValueError(
      "unknown -pipeline value %r; expected one of %s"
      % (name, ", ".join(sorted(PIPELINES))))
  for stage, on in PIPELINES[key].items():
    opts[stage + "_flag"] = bool(on)
  opts["_pipeline_named"] = True
  return opts


def _set_stages(opts, litbridge, graphbridge):
  """Assign all six stage keys.  The fallbacks, the critic and the graph
  translation are on in every set; the two bridges are what the sets differ
  in.

  `-stack-closed` is `-pipeline balanced` and `-stack` is
  `-pipeline high-recall`; `-stack-open` keeps its documented meaning, which
  includes the literal bridge and so matches no named configuration.
  """
  opts["fallback_norm_flag"] = True
  opts["fallback_hyp_flag"] = True
  opts["critic_flag"] = True
  opts["graphtrans_flag"] = True
  opts["litbridge_flag"] = bool(litbridge)
  opts["graphbridge_flag"] = bool(graphbridge)


def parse_cmd_line():
  """Parse sys.argv; return (text, options_dict)."""
  import solve

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
      solve.debug = True
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
        print("Error: -event requires a mode "
              "(neodavidson|davidson|davidson2|flat|flatroles)")
        sys.exit(2)
      mode = params[elpos + 1]
      if mode not in ("neodavidson", "davidson", "davidson2", "flat", "flatroles"):
        print("Error: unknown -event mode:", mode,
              "(expected neodavidson|davidson|davidson2|flat|flatroles)")
        sys.exit(2)
      opts["event_base"] = mode
      # Naming a base asks for that base's own historical theory, so the v2
      # defaults stand aside (lc_encoding.EncodingConfig).
      opts["event_base_explicit"] = True
      skippos = 1
    # --- Additive abstraction primitives (compose with any base). ---
    elif el in ["-existfold", "--existfold"]:
      opts["existfold_flag"] = True
    # --- The versioned proof shorteners (experimental, off by default). ---
    elif el in ["-davidson2", "--davidson2"]:
      opts["davidson2_flag"] = True
    elif el in ["-existfold2", "--existfold2"]:
      opts["existfold2_flag"] = True
    elif el in ["-proofshort2", "--proofshort2"]:
      opts["davidson2_flag"] = True
      opts["existfold2_flag"] = True
    # --- Cancellations.  Each wins from any position; -noproofshort2 is the
    # documented command for reproducing the pre-2026-08-26 ordinary theory. ---
    elif el in ["-nodavidson2", "--nodavidson2"]:
      opts["nodavidson2_flag"] = True
    elif el in ["-noexistfold2", "--noexistfold2"]:
      opts["noexistfold2_flag"] = True
    elif el in ["-noproofshort2", "--noproofshort2"]:
      opts["noproofshort2_flag"] = True
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
      opts["typeenrich_gates"] = parse_te_gates(el.split("=", 1)[1])
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
    elif el.startswith(("-accept=", "--accept=")):
      # EXPERIMENTAL (Task 2B): proof-local acceptance checks on the critic and
      # graph retranslations.  Off unless named.  `permissive` reproduces the
      # behaviour without the option.
      opts["accept_policy"] = el.split("=", 1)[1].strip()
    elif el in ["-accept", "--accept"]:
      # `-accept POLICY`, like `-llm NAME`: the value is the next argument.
      if elpos + 1 >= len(params):
        print("-accept requires a policy: permissive, balanced, or strict")
        sys.exit(2)
      opts["accept_policy"] = params[elpos + 1]
      skippos = 1
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
    elif el in ["-llm-call-limit", "--llm-call-limit"]:
      if elpos + 1 >= len(params):
        print("-llm-call-limit requires a number of calls (0 = unlimited)")
        sys.exit(2)
      opts["llm_call_limit"] = int(params[elpos + 1])
      skippos = 1
    elif el in ["-llm-call-timeout", "--llm-call-timeout"]:
      if elpos + 1 >= len(params):
        print("-llm-call-timeout requires a number of seconds")
        sys.exit(2)
      opts["llm_call_timeout"] = float(params[elpos + 1])
      skippos = 1
    elif el in ["-pipeline", "--pipeline"]:
      if elpos + 1 >= len(params):
        print("-pipeline requires a name: %s" % ", ".join(sorted(PIPELINES)))
        sys.exit(2)
      try:
        apply_pipeline(opts, params[elpos + 1])
      except ValueError as exc:
        print("Error: %s" % exc)
        sys.exit(2)
      skippos = 1
    elif el.startswith(("-pipeline=", "--pipeline=")):
      try:
        apply_pipeline(opts, el.split("=", 1)[1])
      except ValueError as exc:
        print("Error: %s" % exc)
        sys.exit(2)
    elif el in ["-stack", "--stack", "-stack-closed", "--stack-closed",
                "-stack-open", "--stack-open"]:
      # A flag set assigns all six stage keys, so it fully replaces whatever
      # an earlier set or preset put there.  Round 1 of the resolution order.
      _set_stages(opts, litbridge=("open" in el),
                  graphbridge=("closed" not in el))
      opts["_pipeline_named"] = True
    elif el in ["-abstract", "--abstract", "-abstract-roles", "--abstract-roles",
                "-abstract-max", "--abstract-max"]:
      opts["event_base"] = "flatroles" if ("roles" in el or "max" in el) else "flat"
      opts["abstract_preset_flag"] = True   # reproduce this preset's own theory
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
        sys.exit(2)
      solve.llm = params[elpos + 1]
      if solve.llm not in llmcall.SUPPORTED_PROVIDERS:
        print("Error: unknown LLM provider %r; expected one of %s"
              % (solve.llm, ", ".join(llmcall.SUPPORTED_PROVIDERS)))
        sys.exit(2)
      skippos = 1
    elif el in ["-version", "--version"]:
      if elpos + 1 >= len(params):
        print("-version requires a model version string")
        sys.exit(2)
      solve.llm_version = params[elpos + 1]
      skippos = 1
    elif el in ["-combined-instr", "--combined-instr"]:
      if elpos + 1 >= len(params):
        print("-combined-instr requires a path to a combined instructions prompt file")
        sys.exit(2)
      opts["combined_instr_file"] = params[elpos + 1]
      opts["combined_flag"] = True   # presence of -combined-instr turns single-stage mode on
      skippos = 1
    elif el in ["-combined-examples", "--combined-examples"]:
      if elpos + 1 >= len(params):
        print("-combined-examples requires a path to a combined examples prompt file")
        sys.exit(2)
      opts["combined_examples_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-combined-checklist", "--combined-checklist"]:
      if elpos + 1 >= len(params):
        print("-combined-checklist requires a path to a combined checklist prompt file")
        sys.exit(2)
      opts["combined_checklist_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-directanswer", "--directanswer"]:
      if elpos + 1 >= len(params):
        print("-directanswer requires a path to a direct-answer prompt file")
        sys.exit(2)
      opts["directanswer_file"] = params[elpos + 1]
      opts["directanswer_flag"] = True   # answer with one LLM call, no pipeline
      skippos = 1
    elif el in ["-seconds", "--seconds"]:
      if elpos + 1 >= len(params):
        print("-seconds takes an integer parameter")
        sys.exit(2)
      try:
        n = int(params[elpos + 1])
      except:
        print("-seconds takes an integer parameter")
        sys.exit(2)
      if n < 1:
        print("-seconds takes an integer parameter 1 or more")
        sys.exit(2)
      opts["prover_seconds"] = n
      opts["prover_seconds_cli"] = True
      skippos = 1
    elif el in ["-printlevel", "--printlevel"]:
      if elpos + 1 >= len(params):
        print("-printlevel takes an integer parameter")
        sys.exit(2)
      try:
        n = int(params[elpos + 1])
      except:
        print("-printlevel takes an integer parameter")
        sys.exit(2)
      if n < 10:
        print("-printlevel takes an integer parameter 10 or more")
        sys.exit(2)
      opts["prover_print"] = n
      skippos = 1
    elif el in ["-gkin", "--gkin"]:
      if elpos + 1 >= len(params):
        print("-gkin takes a file name as a parameter")
        sys.exit(2)
      opts["gkin_file"] = params[elpos + 1]
      skippos = 1
    elif el in ["-strategy", "--strategy"]:
      if elpos + 1 >= len(params):
        print("-strategy takes a file name as a parameter")
        sys.exit(2)
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
    elif el in ["-actions", "--actions"]:
      opts["actions_flag"] = True
    elif el in ["-noactions", "--noactions"]:
      opts["noactions_flag"] = True
    elif el in ["-formal", "--formal"]:
      opts["formal_flag"] = True
    elif el in ["-plan-depth", "--plan-depth"]:
      if elpos + 1 >= len(params) or not params[elpos + 1].isdigit():
        print("-plan-depth requires a non-negative whole number of steps")
        sys.exit(2)
      opts["plan_depth"] = int(params[elpos + 1])
      skippos = 1
    elif el in ["-action-backend", "--action-backend"]:
      if elpos + 1 >= len(params):
        print("-action-backend requires the name of a registered GK build")
        sys.exit(2)
      opts["action_backend"] = params[elpos + 1]
      skippos = 1
    elif el in ["help", "-help", "--help"]:
      print(helptext)
      sys.exit(0)
    elif el and el[0] == "-":
      print("Key " + el + " is not recognized.")
      print(helptext)
      sys.exit(2)
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
        sys.exit(2)
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

  # Round 4: the recorded name is read back from the final vector, so it can
  # never disagree with the stages the run will actually use.
  opts.pop("_pipeline_named", None)
  opts["pipeline_name"] = finalize_pipeline_name(opts)

  return (text, opts)


helptext = """call solve.py with a natural language text like
"Elephants are big. John is an elephant. Who is big?"
and/or a filename as an argument, with optional keys.

Every -x key is also accepted as --x.  Full reference:
docs/reference/command-line.md, and docs/reference/experimental-options.md for
everything under EXPERIMENTAL AND LEGACY below.

=== COMMON ===

model:
 -llm NAME    : provider: gpt, claude, gemini or deepseek (default: gemini)
 -version VER : model version string, e.g. claude-sonnet-4-6, gpt-5.1

retry configuration (which stages run when the initial attempt answers Unknown):
 -pipeline NAME : conservative | balanced | high-recall.  Also -pipeline=NAME.
                  balanced is the default: the two fallbacks, the critic and
                  the graph retranslation.  conservative is the two fallbacks
                  only.  high-recall adds graph bridges.

output level (a hierarchy; each level includes everything above it; the
action route follows the same levels):
 -explain   : show the English proof explanation
 -logic     : + the pipeline chosen and why, simplified ASU texts, sentences
              mapped to clauses, step logic
 -details   : + stage-1/2 JSON, prover input/output JSON
 -debug     : + raw LLM responses, prover params, full pipeline trace

output format:
 -json      : show all logic in raw JSON instead of pred(arg,...) syntax
 -jsonlogic : shortcut for -logic -json
 -summary   : one block at the end, whatever the output level: the answer, the
              pipeline chosen, the stage that produced it, the answer the
              initial attempt reached, the enabled stages and the LLM calls
              per stage
 -summary-json : the same block as one JSON line, for scripts
 -gkin FILE : save the GK prover input to FILE (with the GK command as comment)

time and call bounds:
 -seconds N          : proof search time for one gk call (default 2)
 -llm-call-timeout N : deadline in seconds for one logical LLM call, covering
                       provider attempts, retries and the waits between them.
                       It never encloses gk.  Default 240; 0 disables it.
 -llm-call-limit N   : bound on the logical LLM calls for one case, across all
                       stages, counting cache hits.  0 is unlimited (default).

 -help      : output this helptext

=== ADVANCED ===

caching (LLM responses are cached by default, per provider, version, all
parameters and input):
 -nollmcache    : disable LLM response caching for this run
 -clearcache    : clear all caches (LLM, proof, parse) and exit
 -nogeminicache : disable Gemini context caching (on by default)
 -cache         : cache GK prover results as well (off by default)

single retry stages, on top of the chosen configuration.  A switch turns its
stage on from any position on the command line; a cancel turns it off from any
position and wins over everything:
 -fallback_norm  : the normalization fallback (on by default; this confirms it).
                   Converts the same parse again with the token and shape
                   normalizations on, and calls gk once more.  No LLM call.
 -fallback_hyp   : the conditional-question fallback (on by default).  Assumes
                   the antecedent in an isolated theory and asks the consequent.
                   No LLM call.
 -critic         : one LLM call audits the initial attempt's translation; a blocking
                   finding on its own chain makes Stage 2 run once more with the
                   findings appended.  One critique, one rerun.
 -graphtrans     : translate the case a second time into open triples, compile
                   it and call gk once.  No judge, no bridge.
 -graphbridge    : invent implications between the open names and search the
                   graph theory with them.  Turns -graphtrans on as well.
 -litbridge      : propose implication rules over the case's own displayed
                   atoms, compile them beside the stored theory and resubmit to
                   gk, in two rounds.  In no named configuration.
 cancels: -nofallback_norm  -nofallback_hyp  -nofallback (both)
          -nocritic  -nographtrans (cancels graphbridge too)
          -nolitbridge  -nographbridge

the prover:
 -prover       : show prover params (also included in -debug)
 -axioms file1.js ... fileN.js : use these files instead of axioms_std.js
 -strategy file.js : use the given JSON strategy file instead of the default
 -printlevel N : N>10 shows more of the search process (10 is default, try 12)
 -nosolve      : parse to logic only, do not run the prover
 -rawresult    : output only the raw JSON result from the prover

other:
 -think        : reasoning mode (GPT: reasoning_effort=medium; Claude: extended
                 thinking; Gemini: needs a 2.5+ model; DeepSeek: reasoner).
                 -think N sets an integer budget.
 -nosemnormal  : disable antonym folding and canonical word substitution

settings that are module constants, not flags:
 litbridge_procedure.EXTRAS      the two code-built litbridge channels
 litbridge_grader.MODE           None / "stated" / "any"
 graph_procedure.LIFT            lift a graph proof into the ordinary theory
 graph_procedure.EVIDENCE        "any" / "stated"
 graph_procedure.DEFAULT_SOURCES the candidate sources layer 2 enumerates
 globals.ABSTRACTION_ROUTES      the order the three routes run in

=== EXPERIMENTAL AND LEGACY ===

None of the following is needed for ordinary use.  Each is described in
docs/reference/experimental-options.md.

the safe proof-shortening rewrites.  Two guarded, exactly reversible rewrites
are ATTEMPTED BY DEFAULT on the ordinary canonical theory.  Each checks its own
conditions per occurrence and, when one fails, leaves that source form
unchanged.  Each keeps bidirectional adapters to the canonical neo-Davidsonian
predicates, which remain the language of axioms_std.js and of any later
knowledge base.  A compact atom may appear in the formal proof and is the basis
of the English proof; a step that converts between the two spellings is
labelled "representation conversion" and is not presented as knowledge.  The
internal names are davidson2 and existfold2:
 -nodavidson2   : reversible event compression off; the canonical
                  neo-Davidsonian spine is restored.  davidson2 compresses
                  {isa(activity,E), has type(E,V), has actor(E,A),
                  has target(E,T)} to event(V,A,T,E), and only when expanding
                  it back reproduces the group.  It never replaces a participant
                  by its class, never invents a missing actor or target, and
                  never puts a goal or topic in the object slot.
 -noexistfold2  : repeated part-witness compression off.  existfold2 folds only
                  the bare "exists Y. isa(C,Y) & has part(X,Y)" pattern, and
                  only for a class with at least four occurrences, emitting
                  three class-specific compatibility clauses.
 -noproofshort2 : both off.  THIS IS THE COMMAND that reproduces the ordinary
                  theory and answers as they stood before 2026-08-26.
 -davidson2 / -existfold2 / -proofshort2 : request one or both from any
                  position, including on top of an -abstract* preset (the event
                  compression declines on a flat base and leaves it alone).
 -event davidson2 : select the event compression as the base outright.
 Naming a base or a preset asks for that base's own historical theory, so the
 defaults stand aside for -event neodavidson / davidson / flat / flatroles, the
 legacy -existfold, and every -abstract* preset.

acceptance policy:
 -accept NAME  : permissive | balanced | strict.  Also -accept=NAME.  Applies
                 proof-local checks to a critic or graph answer.  Off unless
                 given.  balanced and strict discarded more correct answers than
                 wrong ones in measurement.

alternative parsing shapes (replace the default two-stage English->logic parse):
 -s2split     : one Stage-2 LLM call per Stage-1 sentence package; outputs
                joined (failed sentences skipped unless they hold the question;
                locally-invented worlds renumbered).  Also applies the
                cross-sentence shape-unification repair.
 -combined-instr FILE     : single-stage parsing -- one LLM call, English ->
                            logic, no Stage-1 JSON
 -combined-examples FILE  : combined examples prompt file (optional)
 -combined-checklist FILE : combined checklist prompt file (optional)
 -directanswer FILE       : answer the question directly with one LLM call (no
                            logic, no prover)
 -prenorm      : pre-Stage-1 LLM wording normalisation (composable)
 -noprenorm    : force prenorm off after a preset
 -nocrossstage : disable the cross-stage guard-retry

event-encoding bases -- one selector, default neodavidson:
 -event MODE   neodavidson : reified neo-Davidsonian events (default)
               davidson    : compact event(V,A,O,E), keep handle + adjuncts
               davidson2   : the exact spine compression (see above)
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
 -existfold     : (legacy) fold "exists Y. isa(C,Y) & has_part/have(X,Y)" into
                  has_property([$has_part/$have,C], X) + named-witness bridge
 -propclass     : property<->class canonicalization: bridge
                  isa(W,X)<->has_property(W,X) for a concept the flat fold left
                  in both shapes
 -numtype       : numeric-literal typing: parse numeral strings ("34") to
                  int/float and materialize isa(number/integer/...,N) on demand
 -compasym      : comparative asymmetry: for a strict-scalar adjective R used as
                  is_rel2(R,X,Y), emit is_rel2(R,X,Y)->-is_rel2(R,Y,X)

simplification:
 -simple        : no context, no exceptions, simple properties (the three below)
 -nocontext     : no context (time, situation) information in logic
 -noexceptions  : no exception (blocker) information in logic
 -simpleprops   : simplified properties without strength/type parameters

abstraction presets (pure expansions into the primitives above):
 -abstract       : -event flat + entitymerge + guarddrop + bridges
                   + dropdefinites + typeenrich + localantonyms + simpleprops
 -abstract-roles : as -abstract but -event flatroles
 -abstract-max   : as -abstract-roles + prenorm + propclass + numtype + compasym
                   + nominalretry + negretry, plus all six retry stages.
                   prenorm, nominalretry and negretry can make live LLM calls,
                   and so does every stage but the two fallbacks.

older spellings, kept so existing scripts keep working:
 -stack         : same as -pipeline high-recall
 -stack-closed  : same as -pipeline balanced
 -stack-open    : all six stages, literal bridge included
 -geminicache   : accepted and ignored; Gemini context caching is the default

resolution order for every stage selection:
 1. named configurations, presets and flag sets, left to right; a later one
    overwrites an earlier one
 2. an explicit stage switch turns its stage on from any position
 3. a cancel wins over both, wherever it stands

experimental action route (reads action and planning texts):
 Without -actions or -noactions, a cheap classifier (solver/route_classify.py,
 no model call) reads the text: a strong sign of actions or plans ("How can
 ...?", "Find a plan ...", a route between places) sends it to the action
 route; any other text, also an unclear one, goes to the ordinary pipeline.
 -actions       : always run the action route: its own two-stage
                  translation, the action compiler, the replay and the
                  registered GK build.  No ordinary retry stage runs; a stage
                  switch, a -pipeline preset or an ordinary representation
                  option given with it is an error.  English input uses the
                  measured action prompts (prompts/actions).  The answer
                  forms are in docs/reference/experimental-options.md.
 -noactions     : always run the ordinary pipeline; an action option given
                  with it is an error.
 -formal        : the input is a formal JSON record, or its file (Stage-2
                  source units and queries), compiled and solved by the action
                  route with no model call.
 -plan-depth N  : on the action route: the search cap of a plan question
                  (default 4).
 -action-backend NAME : on the action route: a registered GK build (default
                  gk, the installed prover).  -seconds sets its per-launch time (default 30).
 On the action route the output levels show: -explain the sentences and
 library laws the deciding proof used, the plan steps and the replay verdict;
 -logic the source clauses of each sentence, the query and its obligations,
 the stages block, and the proof steps; -details the action Stage-1/2 JSON,
 the controller's checks and each GK launch's input and result; -debug every
 model request and raw response, the library clauses and each GK command.
 -prover, -nosolve, -rawresult, -gkin, -json and -summary work as on the
 ordinary pipeline; with several GK launches -gkin writes one file per launch.
 -printlevel, -axioms and -strategy are errors with -actions.
"""
