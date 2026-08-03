# Configuration and other globals for the nlpsolver.
#
#-----------------------------------------------------------------
# Copyright 2022 Tanel Tammet (tanel.tammet@gmail.com)
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
import os

# Absolute path to llmpipe/ (parent of this file's directory), so that all
# data-file paths work regardless of the working directory at runtime.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ======= configuration globals ======

# global vars changed by command line options

options={
  "debug_print_flag":False, # if True, print a lot of details of the parsing process (turn on by -debug)
  "prover_print_flag":False, # if True, print prover logic input and output
  "prover_nosolve_flag":False, # if True, attempt to solve the question, if False, just output logic
  "use_cache_flag":False, # if True, use cache for GK, if False, do not use cache
  "prover_rawresult_flag":False, # if True, give a raw json result (handled by procproofs.py)
  "prover_explain_flag":False, # if True, output nlp explanation
  "show_logic_flag":False, # if True, output also conventional logic for sentences and nlp explanation
  "show_prover_flag":False, # if True, show prover input and output
  "nocontext_flag":False, # if True, do not insert context information (time, situation) into logic
  "noexceptions_flag":False, # if True, do not insert exception information (blockers) into logic
  "noproptypes_flag":False,  # if True, remove prop strength and type information (set by -simpleprops / -simple / -abstract*)
  # Event-encoding base. One mutually-exclusive selector, set by -event MODE:
  #   "neodavidson" (default) | "davidson" (compact event(V,A,O,E)) |
  #   "flat" (flat is_rel2, bare positional) | "flatroles" (flat is_rel2, eventprop-tagged).
  # The -abstract* presets set "flat"/"flatroles". See analysis/FLAG_RESTRUCTURE_PLAN.md.
  "event_base":"neodavidson",
  "existfold_flag":False,  # (L2) if True, fold a bare existential attribute "exists Y. isa(C,Y) & has_part/have(X,Y)" into a unary has_property([$has_part/$have, C], X), deleting the Skolem cross-product; a generic bidirectional bridge with a named witness $typed_partof(X,C) reconstructs the existential on demand. See memos/L2_EXISTFOLD_PLAN.md
  # Additive abstraction primitives (each also set by the -abstract* presets).
  "entitymerge_flag":False,  # proper-noun entity canonicalization + content-keyed set-label coreference (+ parse-level canon)
  "typeenrich_flag":False,   # taxonomy/isa enrichment: broad supertypes, gender-from-name, name-as-type, gendered-noun bridges, compound subsumption over entity cats, plural->singular norm
  "typeenrich_gates":None,   # None = all six sub-gates; or a set/list subset of {super,gender,nametype,compound,plural,gnoun}
  "guarddrop_flag":False,    # drop redundant antecedent isa type guards (+ self-defeating-conditional repair)
  "bridges_flag":False,      # frame/bridge axioms: rel2<->event equivalence, occasion-location, in-haspart, reflexive-property
  "dropdefinites_flag":False, # skip $theof1 definite reification -> leave definites as plain relations
  "localantonyms_flag":False, # restrict antonym folding to pairs whose words occur in the problem + axiom vocabulary
  "propclass_flag":False,    # property<->class canonicalization (P1): bridge isa(W,X)<->has_property(W,X) for one concept that the flat fold left in both shapes. SAFE isa->has_property always; PROMOTE has_property->isa only for a nominal compound (compound_sub) demanded as -isa. See analysis/P1_DESIGN.md
  "numtype_flag":False,      # numeric-literal typing (P3): parse pure-numeral string args ("34") to int/float, and materialize a ground isa(TYPE,N) (TYPE in number/integer/float/...) when -isa(TYPE,N) is demanded but never supplied. See analysis/P3_TIER_A_PLAN.md
  "compasym_flag":False,     # comparative asymmetry (P3): for a relation R that occurs as binary is_rel2(R,X,Y) and is a strict-scalar dimensional adjective (solver/comparable_adjectives.txt), emit asymmetry is_rel2(R,X,Y)->-is_rel2(R,Y,X) (+ flat property bridge). Restores the §3.1 comparative-order axioms the flat/simpleprops fold drops. See analysis/P3_TIER_A_PLAN.md
  "api_timeout":0,  # hard wall-clock cap (seconds) on the LLM-parse + clause-conversion phase (disarmed before the prover); 0 disables
  "prenorm_flag":False,  # if True, run an experimental pre-Stage-1 LLM phase that unifies repeated entity/property/relation wordings
  "s2split_flag":False,  # if True, run Stage 2 sentence-by-sentence (one LLM call per Stage-1 sentence package, outputs joined, worlds renumbered per rule c'), and apply the cross-sentence shape-unification repair (off-inventory predicate rename, shape bridges, compound composition, broad-supertype isa) that reconciles the divergent per-sentence parses
  "crossstage_retry_flag":True,  # if False, disable the abstraction cross-stage unsatisfiable-guard retry (avoids live corrective LLM calls)
  "nominalretry_flag":False,  # (experimental) if True, a Stage-2 sanity check flags a Stage-1 copular "ENT is a NOUN" predication whose NOUN is dropped from ENT in Stage-2 (but used elsewhere), triggering a corrective Stage-2 retry. See analysis/P3_TIER_A_PLAN.md (case 126)
  "negretry_flag":False,      # (experimental) prenorm-negation-fallback: if True and prenorm dropped a sentential negation from the conclusion question ("X is not a Y?" rewritten to the positive "Is X a Y?"), re-parse from the original (pre-prenorm) text so the negation survives. General correctness fix (not encoding-specific); currently gated so it can later be promoted to default. See analysis/FOLIO_GPT_FAILURES.md G2 (cases 80/127/189/200)
  "prover_axiomfiles":False,  # if not False, use these as axioms instead of the default prover_axiomfile below
  "prover_print":False,  # if not False, use the argument integer for gk printout level, instead of the default
  "prover_strategy":False,  # if not False, use the argument as a gk strategy file, instead of the default
  "prover_seconds":2,  # give the prover this many seconds, instead of the default 1
  "prover_seconds_cli":False,  # True when -seconds was given on CLI (disables auto-estimation)
  # LLM response caching: ON by default.
  # The cache key covers provider, version, temperature, seed, max_tokens,
  # sysprompt and input text, so a cached result is only reused when every
  # call parameter is identical.  Set to False or pass -nollmcache to disable.
  "use_llm_cache_flag": True,
  # Gemini context caching: OFF by default.
  # When enabled, sysprompts >= 16K chars are uploaded once to Google's
  # cachedContents service and referenced by handle on each call, which
  # dodges the per-request input-token cap that triggers instant 429s.
  # Note: cached tokens still count against per-minute TPM, so caching
  # helps with large-prompt bursts but doesn't unblock sustained throughput.
  # Set to True or pass -geminicache to enable.
  "use_gemini_cache_flag": False,
  # Semantic normalisation: ON by default.
  # Applies antonym folding and canonical word substitution to GK clauses
  # before they are passed to the prover.  Set to True or pass -nosemnormal
  # to disable.
  "nosemnormal_flag": False,
  # LLM reasoning/thinking mode: OFF by default.
  # When True, enables medium reasoning effort (GPT: reasoning_effort=medium;
  # Claude: extended thinking; Gemini: thinkingConfig, requires 2.5+ model).
  "think_flag": False,
  "json_flag": False,   # if True, show logic in raw JSON; if False, use traditional syntax
  "show_details_flag": False, # if True, show stage-1/2 JSON and prover input/output
  "gkin_file": None,          # if set, save GK input to this file
  # Combined single-stage parsing: OFF by default.
  # When combined_flag is True, the parser makes ONE LLM call (English -> logic)
  # using the explicitly named combined prompt files below, instead of the
  # two-stage stage1/stage2 calls.  There is no Stage-1 JSON in this mode.
  # Set by -combined-instr (which also names the instructions file).
  "combined_flag": False,
  "combined_instr_file": None,      # path to combined instructions prompt file
  "combined_examples_file": None,   # path to combined examples prompt file (optional)
  "combined_checklist_file": None,  # path to combined checklist prompt file (optional)
  # Direct-answer mode: OFF by default.
  # When directanswer_flag is True, the solver answers the question with ONE LLM
  # call using directanswer_file as the system prompt and the input text as the
  # user message, bypassing the parse->logic->prover pipeline entirely.  Works
  # for any test set.  Set by -directanswer FILE.
  "directanswer_flag": False,
  "directanswer_file": None,        # path to the direct-answer prompt file
  # runtests artifact collector: when set, populated with gk_command etc.
  # Not user-facing; set by english_to_answer(collect=...).
  "_collect": None,
}

# cache

cache_db_name=os.path.join(_root, "cache.db")

# solving logic with a prover
prover_fname=os.path.join(_root, "../gk/gk")  # gk binary
prover_datafolder=os.path.join(_root, "../gk")  # where gk_name_number.txt etc are located
prover_infile="gk_infile.js"
prover_axiomfile=os.path.join(_root, "axioms_std.js")
prover_params=["-taxonomy","-confidence","0.1","-keepconfidence","0.1"] # additional prover params, always appended


def set_global_options(newoptions):
  global options
  for key in newoptions:
    if key in options:
      options[key]=newoptions[key]
    else:
      print("Error: option",key,"is not recognized.")
      sys.exit(0)


# =========== the end ==========
