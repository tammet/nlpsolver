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

# ---------------------------------------------------------------------------
# The retry pipeline: what stages exist, in what order, and what each named
# configuration selects.
#
# This is the single source.  `solve.py` re-exports these names, `runtests.py`
# resolves through the same functions, and the six stage defaults below are
# filled from `PIPELINES[DEFAULT_PIPELINE]` rather than written out a second
# time -- two independent sets of defaults are exactly how the two front doors
# would drift apart.
# ---------------------------------------------------------------------------

PIPELINE_ORDER = ("front_door", "fallback_norm", "fallback_hyp", "critic",
                  "graphtrans", "litbridge", "graphbridge")

PIPELINES = {
  "conservative": {"fallback_norm": True, "fallback_hyp": True,
                   "critic": False, "graphtrans": False,
                   "litbridge": False, "graphbridge": False},
  "balanced":     {"fallback_norm": True, "fallback_hyp": True,
                   "critic": True, "graphtrans": True,
                   "litbridge": False, "graphbridge": False},
  "high-recall":  {"fallback_norm": True, "fallback_hyp": True,
                   "critic": True, "graphtrans": True,
                   "litbridge": False, "graphbridge": True},
}

# The historical `-stack-open` vector matches no named configuration: it is the
# only set that includes the literal bridge.  It keeps its own name.
STACK_OPEN_VECTOR = {"fallback_norm": True, "fallback_hyp": True,
                     "critic": True, "graphtrans": True,
                     "litbridge": True, "graphbridge": True}

# The ordinary no-option configuration, adopted 2026-08-27 on the evidence of
# the two complete Task 2A arms: 111 correct additions against 8 wrong ones.
DEFAULT_PIPELINE = "balanced"

# The default per-logical-LLM-call deadline, in seconds.  It covers provider
# attempts, retries and the sleeps between them, for the initial translation
# and every later stage; it never encloses gk.  `-llm-call-timeout N` overrides
# it and `-llm-call-timeout 0` disables it.
DEFAULT_LLM_CALL_TIMEOUT = 240


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
  #   "davidson2" (the exact event-spine compression, solver/lc_davidson2.py) |
  #   "flat" (flat is_rel2, bare positional) | "flatroles" (flat is_rel2, eventprop-tagged).
  # The -abstract* presets set "flat"/"flatroles". See analysis/FLAG_RESTRUCTURE_PLAN.md.
  "event_base":"neodavidson",
  "existfold_flag":False,  # (L2) if True, fold a bare existential attribute "exists Y. isa(C,Y) & has_part/have(X,Y)" into a unary has_property([$has_part/$have, C], X), deleting the Skolem cross-product; a generic bidirectional bridge with a named witness $typed_partof(X,C) reconstructs the existential on demand. See memos/L2_EXISTFOLD_PLAN.md
  # --- The versioned proof shorteners (attempted by default on the unnamed
  # canonical base; -proofshort2 requests both explicitly).  Each sits beside
  # its v1 and never changes it. ---
  "event_base_explicit":False,  # True when the command line named -event MODE itself. The v2 defaults apply only to the unnamed canonical base, so naming any base -- including neodavidson -- reproduces that base's pre-2026-08-26 theory
  "abstract_preset_flag":False, # True when -abstract / -abstract-roles / -abstract-max was used. Those presets reproduce their historical theories, so they suppress the v2 defaults unless a v2 fold is requested outright
  "nodavidson2_flag":False,     # -nodavidson2: davidson2 off from any position, beating the default and any request
  "noexistfold2_flag":False,    # -noexistfold2: the same for existfold2
  "noproofshort2_flag":False,   # -noproofshort2: both off. This is the documented command for reproducing the pre-2026-08-26 ordinary theory
  "davidson2_flag":False,  # -davidson2: request the exact event-spine compression without naming a base. On the neo-Davidsonian base it selects davidson2; on a flat base (-abstract*) it declines and the config records davidson2_not_applicable, so the flat theory is left alone. `-event davidson2` selects it as the base outright. See solver/lc_davidson2.py
  "existfold2_flag":False,  # -existfold2: fold the bare "exists Y. isa(C,Y) & has part(X,Y)" pattern only, and only for a class with at least lc_existfold_v2.MIN_OCCURRENCES occurrences, emitting three class-specific compatibility clauses. No `have`, no generic schema. See solver/lc_existfold_v2.py
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
  # --- Internal switches for the two abstention fallbacks (solver/fallback_norm.py,
  # solver/fallback_hyp.py).  None of these has a CLI flag: the front door runs with
  # every one of them False, and only `fallback_norm.run` / `fallback_hyp.run` turn
  # them on, for their own conversion, restoring them afterwards. ---
  "qor_flag":False,        # rewrite xor->or inside question bodies (inclusive either-or reading)
  "qpresup_flag":False,    # assert ground appositive isa typing found in a yes/no question body as presupposition facts (body unchanged)
  "singrole_flag":False,   # singularize bare plural noun values inside eventprop role tags
  "listprep_flag":False,     # canonicalize membership relations (in/include/include in) to "on" when the object names a list
  "dashnorm_flag":False,   # fold hyphen/space variants of one property/relation word when both occur in the problem
  "casenorm_flag":False,   # fold letter-case variants of one token inside one predicate position when both spellings occur in the problem
  "quniv_flag":False,        # keep a universal generic yes/no question universal when the hoist is refused (no existential rewrite)
  "compnorm_flag":False,     # normalize comparative relation names (taller/shorter/higher than) to the base gradable adjective outside -s2split too
  # --- The two abstention fallbacks themselves (CLI: -fallback_norm / -fallback_hyp,
  # -nofallback_norm / -nofallback_hyp / -nofallback; both on under -abstract-max) ---
  "fallback_norm_flag":PIPELINES[DEFAULT_PIPELINE]["fallback_norm"],    # from PIPELINES[DEFAULT_PIPELINE]. When the front door ends unresolved, convert the same parse again with the normalizations on and call gk once more (no LLM call). -nofallback_norm / -nofallback turn it off. See solver/fallback_norm.py
  "fallback_hyp_flag":PIPELINES[DEFAULT_PIPELINE]["fallback_hyp"],     # from PIPELINES[DEFAULT_PIPELINE]. When the front door and fallback_norm end unresolved and the question is a conditional, ask the consequent in an isolated theory that assumes the antecedent (no LLM call). -nofallback_hyp / -nofallback turn it off. See solver/fallback_hyp.py
  "nofallback_norm_flag":False, # -nofallback_norm: forces fallback_norm_flag False after the whole command line is read, so it beats the default and every preset whatever their order
  "nofallback_hyp_flag":False,  # -nofallback_hyp: the same for fallback_hyp_flag
  # Per-LLM-call deadline (seconds), covering provider attempts, retries and
  # the sleeps between them, for the initial translation AND every later stage
  # (critic, graph, bridges).  It never encloses gk.  0 disables it.
  "llm_call_timeout":DEFAULT_LLM_CALL_TIMEOUT,
  # Total logical LLM calls allowed for one case, counted across every role
  # (Stage 1, Stage 2 and its format corrections, critic, critic rerun, graph
  # retranslation, graph bridges, literal bridges) and including local cache
  # hits.  0 disables the limit.
  "llm_call_limit":0,
  "api_timeout":0,  # hard wall-clock cap (seconds) on the LLM-parse + clause-conversion phase (disarmed before the prover); 0 disables
  "prenorm_flag":False,  # if True, run an experimental pre-Stage-1 LLM phase that unifies repeated entity/property/relation wordings
  "s2split_flag":False,  # if True, run Stage 2 sentence-by-sentence (one LLM call per Stage-1 sentence package, outputs joined, worlds renumbered per rule c'), and apply the cross-sentence shape-unification repair (off-inventory predicate rename, shape bridges, compound composition, broad-supertype isa) that reconciles the divergent per-sentence parses
  "crossstage_retry_flag":True,  # if False, disable the abstraction cross-stage unsatisfiable-guard retry (avoids live corrective LLM calls)
  "nominalretry_flag":False,  # (experimental) if True, a Stage-2 sanity check flags a Stage-1 copular "ENT is a NOUN" predication whose NOUN is dropped from ENT in Stage-2 (but used elsewhere), triggering a corrective Stage-2 retry. See analysis/P3_TIER_A_PLAN.md (case 126)
  "negretry_flag":False,      # (experimental) prenorm-negation-fallback: if True and prenorm dropped a sentential negation from the conclusion question ("X is not a Y?" rewritten to the positive "Is X a Y?"), re-parse from the original (pre-prenorm) text so the negation survives. General correctness fix (not encoding-specific); currently gated so it can later be promoted to default. See analysis/FOLIO_GPT_FAILURES.md G2 (cases 80/127/189/200)
  "litbridge_flag":PIPELINES[DEFAULT_PIPELINE]["litbridge"],     # from PIPELINES[DEFAULT_PIPELINE]; explicit only. literal-bridge abstraction: when the ordinary pipeline leaves the question unresolved, propose implication rules over the case's own displayed atoms, compile them beside the stored theory and resubmit to gk. Off by default because it costs extra LLM calls per unresolved case and is net-harmful on closed-world material; -litbridge, -stack-open and -abstract-max turn it on, -nolitbridge forces it off. See solver/litbridge_procedure.py and memos/MEMO_2026_08_15_litbridge_merge.md
  "graphbridge_flag":PIPELINES[DEFAULT_PIPELINE]["graphbridge"],    # from PIPELINES[DEFAULT_PIPELINE]; outside the ordinary default. open-relation graph abstraction: when the ordinary pipeline (and the literal bridge, if on) leaves the question unresolved, translate the case a second time into three-item open triples, invent implications between the open names, and search that theory separately. Off by default; -graphbridge, -stack, -stack-open and -abstract-max turn it on, -nographbridge forces it off. See solver/graph_procedure.py and DOCUMENTATION.md §14
  "nographbridge_flag":False,  # if True, graphbridge_flag is forced False after the whole command line is read, so -nographbridge beats -graphbridge whatever their order
  "summary_flag":False,    # -summary: one block at the end saying which stage answered and what the run cost in LLM calls
  "summary_json_flag":False, # -summary-json: the same block as one JSON line, for scripts
  "critic_flag":PIPELINES[DEFAULT_PIPELINE]["critic"],     # from PIPELINES[DEFAULT_PIPELINE] (ON in balanced). -critic: one LLM call audits the front door's translation when it ends Unknown, and may ask for one retranslation. -critic, every -stack* set and -abstract-max turn it on; -nocritic forces it off
  "nocritic_flag":False,   # -nocritic: forces critic_flag False after the whole command line is read
  # EXPERIMENTAL (Task 2B, off by default): proof-local acceptance checks on the
  # critic and graph retranslations.  None or "" disables them entirely;
  # "permissive" | "balanced" | "strict" select a trust setting.
  "accept_policy":None,
  # The retry configuration this run FINALLY resolved to, derived from the six
  # stage flags after the whole command line and all three precedence rounds.
  # An ordinary run records the default, `balanced`; naming a configuration or
  # a flag set records that one (`conservative`, `high-recall`, `stack-open`);
  # any other explicit combination records `custom`.  Recorded in the case JSON.
  "pipeline_name":None,
  "graphtrans_flag":PIPELINES[DEFAULT_PIPELINE]["graphtrans"],   # from PIPELINES[DEFAULT_PIPELINE] (ON in balanced). -graphtrans: layer 1, the graph retranslation and one gk call; no judge, no bridge. -graphtrans, -graphbridge, every -stack* set and -abstract-max turn it on; -nographtrans forces it off
  "nographtrans_flag":False, # -nographtrans: forces graphtrans_flag AND graphbridge_flag False after the whole command line is read
  "nolitbridge_flag":False,   # if True, litbridge_flag is forced False after the whole command line is read, so -nolitbridge beats both -litbridge and the -abstract-max default whatever their order
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
  # Gemini context caching: ON by default.
  # Sysprompts >= 16K chars are uploaded once to Google's cachedContents
  # service and referenced by handle on each call, which dodges the
  # per-request input-token cap that triggers instant 429s.  Our stage
  # prompts are ~103K chars = ~30.8K tokens, resent on every call without
  # this; measured 2026-08-07, a cached call reports 30709 of 30831 prompt
  # tokens as cached.
  # It is a billing lever, not a latency one: measured median 12.2s cached
  # vs 11.2s uncached on the same prompt, and cached tokens still count
  # against per-minute TPM, so it does not unblock sustained throughput.
  # Set to False or pass -nogeminicache to disable.
  "use_gemini_cache_flag": True,
  # Semantic normalisation: ON by default.
  # Applies antonym folding and canonical word substitution to GK clauses
  # before they are passed to the prover.  Set to True or pass -nosemnormal
  # to disable.
  "nosemnormal_flag": False,
  "noclassnumbernorm_flag": False,  # if True, do not singularize the class argument of isa atoms in the final clause list. Off everywhere except the open-relation graph theory (solver/graph_compile.py), where two names differing by a trailing "s" must stay two names
  "noopennamerewrite_flag": False,  # if True, do not rewrite or canonicalize the relation name of an is-rel2 atom (ownership -> have, located-in -> in, preposition canonicalisation, perspective verbs -> Davidsonian events). Off everywhere except the open-relation graph theory, where each relation name is the translator's own and only a named clause may connect two of them
  "open_names_flag":False,   # the proof being rendered is the graph theory's: class and relation names are the case's own words, so the English renderer folds underscores to spaces and renders a relation verbatim instead of conjugating it. Set only by the graph route, for its own rendering. See DOCUMENTATION.md §14.8
  "nopopulate_flag": False,     # if True, emit no population witnesses ($some_C / $some_not_C) at all. Off everywhere except the open-relation graph theory, where a witness the theory minted for a quantified class can ground an invented bridge's own body and prove a question the passage never settles (MEMO_2026_08_17 C1)
  "noentitycat_flag": False,    # if True, emit no Stage-1 entity-category isa clauses (entity_S*) and no base-word entity isa. Off everywhere except the open-relation graph theory, where a name the translator never wrote must not enter supply (MEMO_2026_08_17 C2)
  # Per-fix kill switches for the 2026-08 programmatic repairs
  # (memos/PLAN_2026_08_04_programmatic_fixes.md).  Development/measurement
  # aids: set one True to replay a tree with that repair disabled and attribute
  # a recovery or a breakage to it.  All default False (every repair active).
  "nofix_tense": False,        # fix 1  ASU tense completion
  "nofix_entityids": False,    # fix 2a/2c entity id repairs
  "nofix_categoryisa": False,  # fix 3  category-isa filter
  "nofix_skqguard": False,     # fix 4  bare-plural-generic hoist guard
  "nofix_questionpkg": False,  # fix 5  question packaging repair
  "nofix_casefold": False,     # fix 7c class-name case folding
  "nofix_comparative": False,  # fix 7d comparative canonicalisation
  "nofix_containment": False,  # fix 8a unparseable-clause containment
  "nofix_downstream": False,   # N1    downstream-error corrective retry
  # Reference/scope repairs (2026-08-09 parse-repair campaign).  Each switch
  # disables one independently measurable mechanism.
  "nofix_kindnumber": False,          # generic kind constants: minerals -> mineral
  "nofix_genericparticipants": False, # bind a modified generic event participant
  "nofix_rulecoref": False,           # Stage-1-backed dependent participant coindexing
  "nofix_definiterefs": False,        # unique discourse entity for definite rule NP
  "nofix_rulescope": False,           # lift misplaced antecedent binders over rules
  "nofix_freeconclusion": False,      # reject unrepaired free conclusion variables
  "nofix_boundtypevars": False,       # never lowercase/singularize bound isa class vars
  "nofix_blockorigin": False,         # keep $block on pipeline-generated clauses
  "nofix_propclasspos": False,        # do not cross noun-syn isa into adjective property
  # Kill switch for the final-clause provenance sidecar (M1.1): when True,
  # collect["final_clauses"]/["final_clause_trace"] are not built.
  "nofinaltrace": False,
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

# the abstraction routes the pipeline knows, in their default order.  `solve.py`
# reads `options["abstraction_order"]` and dispatches by these names.
ABSTRACTION_ROUTES = ("graphtrans", "litbridge", "graphbridge")
