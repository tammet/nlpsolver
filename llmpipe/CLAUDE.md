# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Detailed reference lives in DOCUMENTATION.md; this file stays concise.

## Overview

`llmpipe` is an experimental pipeline for semantic parsing of natural language into first-order predicate logic using LLMs (OpenAI GPT, Anthropic Claude, Google Gemini, DeepSeek). It is part of the larger `nlpsolver` repository. Parsed logic is passed to the `gk` binary theorem prover which returns answers.

## Repository layout

**Tracked (committed):** `solver/` (pipeline code), `tests/` (canonical test sets + `FOLIO_yale/` source data), `prompts/` (Stage-1/2 + combined prompts), `mkdata/` (solver-data generators), `axioms_std.js`, the `*.md` docs, and the top-level runners `runtests.py` / `test.py` / `ask.py`.

**Untracked / gitignored (local working data):**
- `testresults/` — per-run batch results. Run folders are named `<benchmark>_<shape>_<date>` (e.g. `core_two-stage_2026-06-03`, `folio_two-stage-abstracted_2026-06-14`) and mirror the published [nlformtasks](https://github.com/tammet/nlformtasks) package; also holds the experiment overviews/memos. See `testresults/README.md`.
- `fixlogs/` — `testfixlog_*.txt` fix logs (hand-maintained).
- `memos/` — dated session memos and notes.
- `debug/` — `examine.py` output + FOLIO scratch; `elogs/` — experiment logs.
- `prompts/archive/` — superseded prompt drafts.
- `ideas/`, `lparpaper/`, `nesypaper/` — research / paper material.
- `cache.db` — SQLite LLM+prover cache; `examine.py` / `compare_runtests_json.py` / `tools/` — local utility scripts.

[nlformtasks](https://github.com/tammet/nlformtasks) (locally `/opt/nlformtasks`) is the standalone published release of the test sets and their results (renamed there: `tests_<x>` → `<x>_tests`).

## Running the Pipeline

All scripts are run from the `llmpipe/` directory.

```bash
# Run the full pipeline on a natural language query
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"

# Run the test suite (default: tests/tests_core.py)
python3 test.py
python3 test.py tests/tests_core.py -llm claude
```

### solve.py flags

```
Output level (hierarchy — each includes previous levels):
-explain         Show English proof explanation
-logic           + simplified text, sentences-to-clauses, logic in proof steps
-details         + stage-1/2 JSON, prover input/output JSON
-debug           + raw LLM responses, prover params, full trace
Every block appears for the stage that ANSWERED, not only for the front door,
and under the SAME headers — a stage after the front door parses, converts and
calls gk again, so `=== prover input (JSON) ===` and the rest appear twice.
What says whose they are is one line, `--- stage: graphtrans ---`, printed
before the stage runs, plus the `=== stages ===` block at the end (which stages
ran, and which produced the answer).  No header carries a route name.
-explain shows the answer and its proof and nothing else, whichever stage found
it.  The case JSON's `answer`, `nl_proof`, `proof`, `gk_command` and
`final_clauses` describe the answering stage's gk call; the front door's own
call is kept as `front_door_proof` / `front_door_gk_command`, and `stages` is a
separate information block with the normal keys unchanged (DOCUMENTATION.md
§10, §14.8).

Output format:
-json            Show logic as raw JSON instead of traditional syntax
-jsonlogic       Shortcut for -logic -json
-gkin FILE       Save GK prover input to FILE (with GK command as comment)

Logic conversion / representation (transform Stage-2 logic before the prover;
ENCODINGS.md §6, DOCUMENTATION.md §11). All resolved by one source of truth,
`lc_encoding.EncodingConfig`; the pipeline reads only that config, never a preset.

-event MODE      Event-encoding base (one mutually-exclusive selector; default
                 neodavidson): neodavidson (reified neo-Davidsonian) |
                 davidson (compact event(V,A,O,E)) | davidson2 (the exact
                 spine compression) | flat (is_rel2) |
                 flatroles (is_rel2 with eventprop-tagged object)

The safe proof shorteners, ATTEMPTED BY DEFAULT (2026-08-26) on the ordinary
canonical theory.  `davidson2` compresses a complete event spine to
event(V,A,T,E) only when expanding it back reproduces the group; `existfold2`
folds the bare "exists Y. isa(C,Y) & has part(X,Y)" pattern for a class with at
least four occurrences.  Either refuses locally and leaves that source form
unchanged.  Bidirectional adapters keep the canonical role predicates as the KB
interface; a compact atom may appear in a proof and drive its English, and an
adapter step reads "representation conversion", never "Knowledge used".
-nodavidson2     davidson2 off, canonical spine restored (wins from any position)
-noexistfold2    existfold2 off
-noproofshort2   both off -- the command that reproduces the pre-2026-08-26
                 ordinary theory and answers
-davidson2 / -existfold2 / -proofshort2   request them where they are not the
                 default (e.g. on top of an -abstract* preset)
Naming a base or a preset asks for that base's historical theory, so the
defaults stand aside for -event <any mode>, legacy -existfold, and -abstract*.
Additive abstraction primitives (compose with any -event base):
-entitymerge     Proper-noun entity canonicalization + set-label coreference
-typeenrich[=GATES]  Taxonomy/isa enrichment; bare = all six sub-gates, or a comma
                 list of super,gender,nametype,compound,plural,gnoun (-name excludes; all)
-guarddrop       Drop redundant antecedent isa guards (needs a fold base)
-bridges         Dynamic frame/bridge axioms (needs -event flat/flatroles)
-dropdefinites   Skip $theof1 definite reification (leave definites as relations)
-localantonyms   Restrict antonym folding to problem + axiom vocabulary
-existfold       Existential-attribute collapse: ∃Y.isa(C,Y)∧has_part(X,Y) →
                 has_property([$has_part,C],X) + named-witness ($typed_partof) bridge
Simplification (ENCODINGS.md §5):
-nocontext       Context → constant "$c" (no worlds/tense)
-noexceptions    Strip $block from defeasible rules
-simpleprops     Degree predicates → simple (+ -noexceptions)
-simple          The three above combined
Abstraction presets (pure CLI expansions into the primitives above):
-abstract        -event flat + entitymerge + guarddrop + bridges + dropdefinites
                 + typeenrich + localantonyms + simpleprops
-abstract-roles  As -abstract but -event flatroles (eventprop-tagged objects)
-abstract-max    As -abstract-roles + prenorm + propclass + numtype + compasym
                 + nominalretry + negretry, PLUS the open-world repair stack
                 (all six stages below).  Strongest; FOLIO ladder base.  It
                 makes LLM calls on every unresolved case.
-prenorm         Pre-Stage-1 LLM wording normalisation (composable)
-nocrossstage    Disable the cross-stage guard retry

The repair stack (DOCUMENTATION.md §12.0b): six stages after the front door,
in this order, the first definite answer stopping the rest —
  fallback_norm, fallback_hyp, critic, graphtrans, litbridge, graphbridge.
`solve.PIPELINE_ORDER` is the one declaration of that order; execution, the
summary and the tests all read it.

Each stage is a separate attempt.  The critic theory, the graph theory and a
bridge theory are their own clause sets, not additions to the canonical one,
except where a mechanism already merges deliberately.

Named configurations (`-pipeline NAME`, also `-pipeline=NAME`), which select
retry stages and nothing else — no encoding, preset, prompt, model or prover
option:
                 norm  cond  critic  graph  gbridge  litbridge
conservative      on    on     off     off     off       off
balanced          on    on     on      on      off       off
high-recall       on    on     on      on      on        off
The literal bridge belongs to no named configuration; add it with -litbridge.

**`balanced` is the ordinary default (adopted 2026-08-27).**  A bare command
line and `-pipeline balanced` resolve identically, and both record
`pipeline_name: balanced`.  `globals.PIPELINES[globals.DEFAULT_PIPELINE]` is
where the six stage defaults come from, so the two front doors cannot drift.
The evidence is the two complete Task 2A arms: 111 correct additions against 8
wrong ones (MEMO_2026_08_27_canonical_stack_census_closed.md).  Wider
evaluation follows the audit of this implementation.

`-pipeline conservative` is the lower-cost retry sequence: the two
deterministic fallbacks, no LLM call after the front door.

Flag sets, each assigning all six stage keys.  `-stack-closed` resolves
identically to `-pipeline balanced` and `-stack` to `-pipeline high-recall`:
-stack           fallbacks + critic + graphtrans + graphbridge (no literal
                 bridge).  Material of unknown origin: the general default.
-stack-closed    fallbacks + critic + graphtrans.  Known closed-world material
                 (core-like, FOLIO-like), where neither bridge pays.
-stack-open      All six.  Known open-world material (EntailmentBank-like).
Resolution order: (1) named configurations, presets and flag sets, left to
right, a later one overwriting an earlier one; (2) an explicit stage switch
turns its stage on from any position; (3) a cancel wins over both from any
position.  An unknown -pipeline name is an error in both front doors.
`-summary` prints stages_enabled and every case JSON carries it, plus
`pipeline_name`, `run_outcome` and one `stages` row per stage.

Errors and timeouts: `None`, empty output, `Unknown`, `no answer` and every
`Error:` value are unresolved, never answers and never correct abstentions.  A
stage exception or timeout is recorded on that stage's row and the run
continues with the next enabled stage.  An earlier definite answer is never
replaced.  `run_outcome` separates a definite answer, `Unknown` after every
enabled stage ran, `Unknown` because a later stage failed, and a translation
failure before a valid gk question existed.

-llm-call-timeout N   Per-LLM-call deadline in seconds, covering provider
                 attempts, retries and the sleeps between them, for the initial
                 translation AND every later stage (critic, graph, bridges).
                 It never encloses gk.  **The default is 240 seconds**;
                 `-llm-call-timeout 0` disables it, and any other number
                 replaces it.  Absence of the option and an explicit zero are
                 different things.  This is the bound `api_timeout` did not
                 give: that one covered only the parse and conversion phase.
-llm-call-limit N     Total logical LLM calls one case may make, counting every
                 role and counting a local cache hit as a call.  0 (the
                 default) is unlimited.  Call N+1 is refused before the cache
                 lookup and before any provider request, leaving that stage
                 unresolved.  Per-case accounting uses one vocabulary:
                 attempted = allowed + refused, allowed = cached + live, and
                 `provider_requests` counts outbound requests separately.
-accept POLICY   EXPERIMENTAL, off by default: proof-local acceptance checks on
                 critic and graph-retranslation answers
                 (permissive|balanced|strict).  `balanced` and `strict`
                 discarded far more correct answers than wrong ones
                 (MEMO_2026_08_27_retranslation_acceptance_result.md), so they
                 are a diagnostic, not a candidate default.  Graph bridges and
                 literal bridges are never judged by it.

The stages:
-fallback_norm   ON BY DEFAULT (DOCUMENTATION.md §16).  When the front door ends
                 unresolved, convert the SAME parse again with the token and
                 shape normalizations on (quniv, dashnorm, casenorm, compnorm,
                 listprep, singrole) plus the question rewrites the text
                 licenses (a cued xor -> or, an apposed typing), and call gk
                 once more.  No LLM call.  The exclusive reading is submitted
                 before the inclusive one.  At most two gk calls.
-fallback_hyp    ON BY DEFAULT.  When the question is a conditional and both the
                 front door and fallback_norm ended unresolved, assume the
                 antecedent in an isolated theory (`hyp_<sid>`) and ask the
                 consequent.  Nothing is inserted into the ordinary premise set.
                 Runs with fallback_norm's normalizations on.  No LLM call, one
                 gk call.
-critic          One LLM call audits the translation the front door produced —
                 the English, the compacted Stage 1 and the Stage-2 logic — and
                 reports findings.  On a blocking finding that lies on its own
                 chain, Stage 2 (or Stage 1 and 2) runs once more with the
                 findings appended.  One critique, one rerun, then stop.  The
                 translator never sees the critic's reading of the answer.  The
                 rerun's own `answered_by` is recorded, so `-summary` can say
                 "critic (rerun answered by fallback_norm)".
-graphtrans      Layer 1: translate the case a second time into open triples,
                 compile it and call gk once.  No judge, no bridge, no extra
                 model role.  About 1.2 LLM calls per case.  This is the whole
                 mechanism on closed-world material.
-litbridge       Ask the LLM for implication rules over the case's own displayed
                 atoms, compile them to clauses, append them and call gk again
                 (two rounds).  Net-harmful on closed-world material, so only
                 -stack-open and -abstract-max turn it on.
-graphbridge     Layer 2: invent implications between the open names and search
                 layer 1's theory with them.  Implies -graphtrans and never
                 translates twice.  For open-world (EntailmentBank-like)
                 material; about 2.7 LLM calls per case.
The cancels, each winning from any position:
-nofallback_norm -nofallback_hyp -nofallback (both)
-nocritic  -nographtrans (cancels graphbridge too)  -nolitbridge  -nographbridge

Settings that are module constants, not flags:
litbridge_procedure.EXTRAS         the two code-built litbridge channels
litbridge_grader.MODE              None / "stated" / "any" (DOCUMENTATION.md §13.8)
graph_procedure.LIFT               lift a graph proof into the ordinary theory
graph_procedure.EVIDENCE           "any" / "stated"
graph_procedure.DEFAULT_SOURCES    layer 2's candidate sources
globals.ABSTRACTION_ROUTES         the order the three routes run in
Each fallback's own configuration is module-level booleans in
solver/fallback_norm.py and solver/fallback_hyp.py; none of them is a CLI flag,
and the front door runs with every one of them off.

Alternative parsing shapes (replace the default two-stage parse):
-s2split         One Stage-2 LLM call per Stage-1 sentence; outputs joined
                 (worlds renumbered; failed sentences skipped unless the question).
                 Includes the cross-sentence shape-unification repair (predicate
                 rename, shape bridges, compound composition, broad-supertype isa)
-combined-instr FILE   Single-stage parsing: ONE LLM call English → logic
                 (+ optional -combined-examples / -combined-checklist)
-directanswer FILE     ONE LLM call answers directly; no logic, no prover

Reporting:
-summary         One block at the end, whatever the output level: the answer,
                 which stage produced it (front_door / fallback_norm /
                 fallback_hyp / critic / graphtrans / litbridge / graphbridge),
                 the front door's own answer, stages_enabled, the abstraction
                 order, and the LLM calls per stage (total / live / retries).
                 `runtests.py` writes the same fields into every case JSON
                 (`answered_by`, `front_door_answer`, `stages_enabled`,
                 `abstraction_order`, `llm_call_counts`, and the `fallback`
                 record).
-summary-json    The same block as one JSON line

Other:
-llm NAME        LLM provider: gpt, claude, gemini, or deepseek
-version VER     Model version string, e.g. claude-sonnet-4-6
-nollmcache      Disable LLM response caching for this run
-nogeminicache   Disable Gemini server-side context caching (on by default)
-cache           Enable GK prover result caching (off by default)
-nosolve         Parse to logic only, do not run the prover
-seconds N       Give the prover N seconds (default 2)
```

## Architecture

### Pipeline (`solver/solve.py` → `english_to_answer()`)

```
English text
  -> llmparse.parse_text()      [Stage 1: English -> ASUs; Stage 2: ASUs -> logic JSON]
  -> logconvert.rawlogic_convert()  [logic JSON -> GK clause list (FOL to CNF)]
  -> prover.call_prover()       [calls gk binary]
  -> procproofs.process_proof() [post-process prover output]
  -> answer string
```

### Solver Modules (`solver/`)

Grouped by role; **see DOCUMENTATION.md §5 for the full per-module reference** and
ENCODINGS.md for the representations they produce. Many concerns are split across
small cohesive files (façade re-exports keep importers stable), so reach for §5
rather than guessing from a name.

- **Entry / parsing** — `solve.py` (CLI + `english_to_answer`), `llmparse.py` (two-stage parser, entity-ID normalization, corrective-retry loop), `llmcall.py` (LLM API + SQLite cache), `stage_sanity.py` (Stage-1/2 sanity checks; façade over `stage_sanity_{core,s1,s2,guards}.py`), `directanswer.py`.
- **Logic conversion** (`logconvert.rawlogic_convert` orchestrates) — `lc_encoding.py` (the `EncodingConfig` gate resolver — single source of truth), `lc_packages.py` (per-`@id`), `lc_rewrites.py` (pre-clausification rewrites), `lc_repairs.py` (structural repairs), `lc_clausify.py` (FOL→CNF), `lc_ctxt.py` (`$ctxt`/time), `lc_questions.py` + `lc_query_guards.py` (questions, guard/what-population), `lc_sets.py` (sets/counting), `lc_coarse.py` + `lc_existfold.py` (event folds), `lc_entity_isa.py` (taxonomy `isa`), `lc_finalize.py` (strict/abstract finaliser).
- **Post-clausification passes** — `lc_post_normalize.py`, `lc_post_have.py`, `lc_post_reify.py`, `lc_post_inject.py` (+ `lc_inject_synonyms.py`, `lc_inject_scan.py`), `lc_post_population.py`, `lc_post_una.py`, `semnormalize.py`, `axiom_vocab.py`; shared traversal in `treewalk.py`. See "Semantic Normalization" below and DOCUMENTATION.md §7.7.
- **Proving + proofs** — `prover.py` (gk subprocess), `procproofs.py` → `proof_answer_select.py` / `proof_answer_format.py` / `proof_explain.py`; rendering via `proof_render.py` façade over `proof_utils.py` / `proof_english.py` / `proof_terms.py` / `proof_logic.py`, plus `entity_map.py` and `linguistics.py`. See DOCUMENTATION.md §5.9 and PROOF_RENDERING.md.
- **Abstention fallbacks** (`-fallback_norm` / `-fallback_hyp`, DOCUMENTATION.md §16) — `fallback_norm.py` (the normalizations, the `casenorm` pass, the text-licensed question rewrites, the exclusive-before-inclusive runner) and `fallback_hyp.py` (the conditional trigger, the refutation pre-check, the isolated theory).  Neither makes an LLM call.
- **Literal-bridge abstraction** (`-litbridge`, DOCUMENTATION.md §13) — seven `litbridge_*` modules used as one stack: `litbridge_atoms/rules/compile/chain/prompts/procedure/converter.py`.
- **Critique pass** (`-critic`, DOCUMENTATION.md §15) — `critic_pass.py` (the call, the parser, the decision, the corrective) and `critic_render.py` (what the critic reads); prompt `prompts/critic/critic_system.txt`.
- **Graph abstraction** (`-graphtrans` / `-graphbridge`, DOCUMENTATION.md §14) — `graph_p0.py` is layer 1 (retranslate, compile, one gk call) and the eight `graph_*` modules are layer 2: `graph_stage2.py` (the second, open-triple Stage 2), `graph_compile.py` (its frozen converter configuration), `graph_inventory.py`, `graph_pairs.py`, `graph_judge.py`, `graph_search.py`, `graph_lift.py`, `graph_procedure.py`. Prompts in `prompts/graph/`; harness `tools/run_graph_bridge.py` + `score_graph_bridge.py` + `report_graph_bridge.py`; fixtures `tools/test_graph_*.py`.
- **Infra / data** — `globals.py` (options dict), `cache.py` (SQLite), `pretty.py`, `utils.py`; generated `data_{canonicals,antonyms,synonyms,exclusions,names}.py` from `mkdata/*.txt`.

### Semantic Normalization Pipeline

Applied after clausification, before the prover (`-nosemnormal` disables). Full reference: DOCUMENTATION.md §7.7 (injection table), §9.5 (preposition subsumption).

```
rawlogic_convert() produces clause list
  -> semnormalize.sem_normalize_clauses(clauses)     [solve.py]
       Pass 1: Antonym folding — word in ANTONYMS → flip polarity + replace
       Pass 2: Canonical substitution — word in CANONICALS → replace
       (both skip $ctxt terms, handle disjunctive clauses)
```

Soft-synonym and exclusion axioms are injected earlier, inside `rawlogic_convert()`, appended after all `sent_*` clauses.

**Injectors** — emit dynamic axioms gated on input ∪ axiom-vocab presence, all
traversing the clause list via `treewalk.walk_result_atoms`. The KB-driven
synonym / exclusion / mutex injectors live in `lc_inject_synonyms.py` (shared
scan helpers in `lc_inject_scan.py`); the bridge / verb / world injectors (carrier
lift, verb-result-state, acquire→have, positional / containment / attribute
bridges, stable-adjective persistence, world geometry) live in `lc_post_inject.py`,
which re-exports the synonym injectors. **Full per-injector table: DOCUMENTATION.md §7.7.**

Static counterparts and curated data:
- `MANUAL_ANTONYMS` / `MANUAL_GRADABLE_ANTONYMS` (`mkdata/build_solver_data.py`) → synthetic `MANUAL_ADJ_*` exclusion groups; gradable pairs flow through exclusion path only (case 55). Chain-rejected antonyms → synthetic `ANT_*` groups.
- Spatial/temporal preposition subsumption + `(on,under)`/`(on,below)` mutex live statically in `axioms_std.js` §7c/7d/7e. Surface-form canonicalisation ("in front of" → "in_front_of") in `lc_rewrites._PREP_CANONICAL`.
- X2 direct-support uniqueness (axioms_std.js §7g) + entity UNA (`#:`) force contradiction when two distinct entities are `on`-targets of the same X (case 148).

**Regenerating data files** after changing `mkdata/*.txt`:
```bash
cd mkdata && python3 build_solver_data.py
```

### Logic Representation

Stage-2 LLM output format:
```
["and", ["@id","S1", PACKAGE], ["@id","S2", PACKAGE], ...]
```
where PACKAGE is `["holds",world,F]`, `["question",F]`, `["ask",var,F]`, or `["and",PKG,["@p","Sx",p]]`.

GK clause list format (output of `logconvert`):
```
[{"@name":"sent_S1", "@logic": CLAUSE}, ...]   -- assertion
{"@name":"sent_S1", "@question": FORMULA}       -- query
```
Variables: `"?:X"` prefix. Negation: `"-"` prefix on predicate name.

### Modal Classifiers (2026-05-14 rework)

Modality is encoded by **arity-1 classifier predicates on Davidsonian event variables**, attached as the last conjunct of the event's outer `and` block:

```
["isa","activity","E"], ["has type","E","fly"], ["has actor","E","X"], ["capability","E"]
```

Eight Stage-2 classifiers map 1:1 with the Stage-1 `mode` enum: `typical`, `capability`, `necessity`, `obligation`, `volition`, `intention`, `expectation`, `speech_act`. The four mental/speech modes use **two-event reification**: outer event E1 with the classifier, nested inner event E2 linked by `["has content","E1","E2"]`.

A ninth classifier, `actuality(E)`, marks real events and is **injected by the pipeline** (`lc_rewrites.inject_actuality`) — not by Stage 2. Every `and`-block introducing `isa(activity, E)` gets `["actuality", E]` unless (a) one of the eight classifiers already applies to E (checked tree-wide) or (b) E is the inner content event of a two-event reification. `actuality` is hidden from English rendering. A defeasible bridge in axioms_std.js §5.1 derives `capability(E)` from `actuality(E)`, gated by a `$block` for `¬capability(E)` overrides.

Grammatical tense on Davidsonian events lives on the event via `["has time", E, "past"|"present"|"future", "in"]`. Non-Davidsonian atoms get tense via `$ctxt.Time` or `@time` wrappers.

### Prompt Files (`prompts/`)

```
prompts/stage1_instructions_full.txt   -- Stage 1 system prompt instructions
prompts/stage1_checklist_full.txt      -- Stage 1 procedural checklist
prompts/stage1_examples.txt            -- Stage 1 few-shot examples
prompts/stage2_instructions_full.txt   -- Stage 2 system prompt instructions
prompts/stage2_checklist_full.txt      -- Stage 2 procedural checklist
prompts/stage2_examples.txt            -- Stage 2 few-shot examples
```
`prompts/archive/` (gitignored) holds historical/superseded prompt versions; `prompts/COMBINED_PROMPT_MEMO.md` documents the combined single-stage prompt family.

### LLM Configuration (`solver/llmcall.py`)

```python
use_llm          = "gemini"              # "gpt" | "claude" | "gemini" | "deepseek"
claudeversion    = "claude-sonnet-4-6"
gptversion       = "gpt-5.1"
geminiversion    = "gemini-2.5-flash"
deepseekversion  = "deepseek-v4-flash"   # V4 models get reasoning_effort="none"; "deepseek-reasoner" for thinking
temperature      = 0
default_max_tokens = 8000
```

API keys are read from plain-text files at `../secrets/{gpt,claude,gemini,deepseek}_secrets.txt` (each file holds just the raw key string).
LLM responses are cached by default in `cache.db` (SQLite), keyed on provider, version, temperature, max_tokens, sysprompt and input. Use `-nollmcache` to disable.

### Dependencies

The `gk` binary and its data files must be present:
```
llmpipe/axioms_std.js
../gk/gk                    (binary)
../gk/gk_name_number.txt
../gk/gk_taxonomy_packed.txt
```
The authoritative GK distribution (binaries, docs, examples) is
https://github.com/tammet/gkreasoner; `../gk/README.md` summarises the
local installation.
Full solver data: http://logictools.org/data/nlpsolver_data.tar.gz

### Test Data

- `tests/tests_core.py` — list of `[id, input, expected]` triples for the core pipeline
- `testresults/core_two-stage_2026-06-03/<llm>/case_NNNN.json` — latest core batch results per LLM (input, expected, answer, correctness, stage1/stage2/clauses/gk_command/proof); the primary debug input. (`testresults/` is gitignored; run folders follow `<benchmark>_<shape>_<date>`.)
- `testresults/core_two-stage_2026-06-03/multi_failed.{txt,json}` — triage list of cases any LLM failed

## Debug Case Workflow

When the user says **"Debug case N"** (N is a case id in `fixlogs/testfixlog_june.txt` or the `testresults/core_two-stage_2026-06-03/multi_failed.txt` list):

1. **Read the four batch result files** for Case N — `testresults/core_two-stage_2026-06-03/{claude,gpt,gemini,deepseek}/case_NNNN.json` (zero-padded to 4 digits). Each JSON contains `input_text`, `expected_answer`, `answer`, `correctness`, plus `stage1`, `stage2`, `clauses`, `gk_command`, `proof` — no need to re-run the solver to inspect parse/proof (they come from the SQLite cache and match a fresh run). For fuller `-debug -explain -logic` logs, run `python3 examine.py N` → writes `debug/eN_{gemini,claude,gpt,deepseek}.txt`.
2. **Note the `Input:` text and `Expected:` value** — from the JSON and/or the `fixlogs/testfixlog_june.txt` entry.
3. **Compare across all four LLMs** — read the JSONs/logs fully. For a UDP-pipeline reference answer (not in the batch, not run by `examine.py`), run the udppipe solver manually and include it when informative.
4. **Examine Stage 1 and Stage 2** — a correct final answer is not sufficient. Report major conceptual differences (wrong entity types, missing isa guards, flat vs nested quantifiers, dropped conditions). Both stages must be correct.
5. **Assess the Expected value** — form an independent opinion on whether it is correct under a normal reading, or should change. A UDP answer is correct in most but not all cases.
6. **Analyze errors** — find the root cause (stage-1 parse, stage-2 logic, logconvert, prover input, proof post-processing).
7. **Test with -nocontext if $ctxt suspected** — `python3 solver/solve.py -nocontext "..."`. Succeeds without context but fails with → the issue is `$ctxt` injection.
8. **Simplify if uncertain** — construct a minimal version isolating the suspected issue and run it.
9. **Prover-timeout suspected?** — try in order: (a) run without `axioms_std.js`; (b) swap strategy to `{"strategy":["unit"]}` or `{"strategy":["query_focus"]}` with `query_preference:1`; (c) last resort, raise `-seconds`. If an alternate strategy is much faster, the default may need to change.
10. **Write analysis and fix plan** — summarize root cause(s) and propose a concrete plan. Do **not** write code or modify files at this stage.

**Fix scope (current campaign):** fixes go into **pipeline code, axioms, or test criteria** (including removing/correcting a bad test case). **Leave the prompt files unchanged.** If a case needs a `prompts/` change, postpone it — record the diagnosis in `fixlogs/testfixlog_june.txt` and move on.

## Register Fix Workflow

When the user says **"Register fix for case N"** (analysis done, fix implemented and verified):

1. **Read the Case N entry in `fixlogs/testfixlog_june.txt`**. If none exists, create one (Case / Input / Expected / Received, matching the file's style).
2. **Add brief `Conclusion:`, `Cause:`, `Fixes:` fields** — one or two short lines each, matching existing entries.
3. **Do not rewrite or remove existing fields** — only add what is missing.

## Work Process Rules

- **NEVER pass `-nollmcache` or `--nollmcache` to any command.** It bypasses the LLM cache and wastes API credits. NO exceptions — even on "recheck"/"rerun". If prompts changed, the user runs the solver themselves or tells you to disable the cache.
- **Always trust the LLM cache.** Cache entries may be newer than what you last saw. Always use cache and trust its results.
- **Never run `test.py` with more than 5 examples** without explicit instruction. Use `-limit 5` or `-filter PATTERN`. For quick checks run `python3 solver/solve.py ...` on individual examples.
- **Run `python3 solver/solve.py ...`** directly without asking for consent.
- **Grep and read-only bash** (grep, sed without -i, cat, head, tail, echo) inside llmpipe may run without consent, as long as nothing is written/modified/deleted.
- **Prefer the built-in Grep/Read/Glob tools** over bash equivalents.
- **Compound read-only commands** using `|` with grep/head/tail/cat are allowed.
- **Avoid `$()` syntax** when alternatives exist.

### Other Top-Level Scripts

- `runtests.py` — batch runner: every `[id,input,expected]` case × N LLMs in parallel, one JSON per (case, llm) under `testresults/<name>/<llm>/case_NNNN.json`, with a live `summary.json`. Resumes by skipping existing files; `-redo`/`-redo-errors` override; `-sequential` runs serially. See DOCUMENTATION.md §10.
- `examine.py` — write per-LLM `-debug -explain -logic` logs for a case id to `debug/eN_{gemini,claude,gpt,deepseek}.txt` (used by the Debug Case Workflow).
- `compare_runtests_json.py` — diff two `runtests.py` result trees.
- Collection / comparison / prompt-check helpers (`collectmultillmconv.py`, `comparellmconv.py`, `checkprompt.py`, …) now live in `tools/`.
