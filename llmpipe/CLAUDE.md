# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Detailed reference lives in DOCUMENTATION.md; this file stays concise.

## Overview

`llmpipe` is an experimental pipeline for semantic parsing of natural language into first-order predicate logic using LLMs (OpenAI GPT, Anthropic Claude, Google Gemini, DeepSeek). It is part of the larger `nlpsolver` repository. Parsed logic is passed to the `gk` binary theorem prover which returns answers.

## Repository layout

**Tracked (committed):** `solver/` (pipeline code), `tests/` (canonical test sets + `FOLIO_yale/` source data), `prompts/` (Stage-1/2 + combined prompts), `mkdata/` (solver-data generators), `axioms_std.js`, the `*.md` docs, and the top-level runners `runtests.py` / `test.py` / `ask.py`.

**Untracked / gitignored (local working data):**
- `testresults/` — per-run batch results. Run folders are named `<benchmark>_<shape>_<date>` (e.g. `core_two-stage_2026-06-03`, `folio_two-stage-abstracted_2026-06-14`) and mirror the published `/opt/nlformtasks` package; also holds the experiment overviews/memos. See `testresults/README.md`.
- `fixlogs/` — `testfixlog_*.txt` fix logs (hand-maintained).
- `memos/` — dated session memos and notes.
- `debug/` — `examine.py` output + FOLIO scratch; `elogs/` — experiment logs.
- `prompts/archive/` — superseded prompt drafts.
- `ideas/`, `lparpaper/`, `nesypaper/` — research / paper material.
- `cache.db` — SQLite LLM+prover cache; `examine.py` / `compare_runtests_json.py` / `tools/` — local utility scripts.

`/opt/nlformtasks` is the standalone published release of the test sets and their results (renamed there: `tests_<x>` → `<x>_tests`).

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

Output format:
-json            Show logic as raw JSON instead of traditional syntax
-jsonlogic       Shortcut for -logic -json
-gkin FILE       Save GK prover input to FILE (with GK command as comment)

Logic conversion / representation (transform Stage-2 logic before the prover;
ENCODINGS.md §6, DOCUMENTATION.md §11). All resolved by one source of truth,
`lc_encoding.EncodingConfig`; the pipeline reads only that config, never a preset.

-event MODE      Event-encoding base (one mutually-exclusive selector; default
                 neodavidson): neodavidson (reified neo-Davidsonian) |
                 davidson (compact event(V,A,O,E)) | flat (is_rel2) |
                 flatroles (is_rel2 with eventprop-tagged object)
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
-abstract-max    As -abstract-roles + -prenorm (strongest; FOLIO ladder base)
-prenorm         Pre-Stage-1 LLM wording normalisation (composable)
-nocrossstage    Disable the cross-stage guard retry

Alternative parsing shapes (replace the default two-stage parse):
-s2split         One Stage-2 LLM call per Stage-1 sentence; outputs joined
                 (worlds renumbered; failed sentences skipped unless the question).
                 Includes the cross-sentence shape-unification repair (predicate
                 rename, shape bridges, compound composition, broad-supertype isa)
-combined-instr FILE   Single-stage parsing: ONE LLM call English → logic
                 (+ optional -combined-examples / -combined-checklist)
-directanswer FILE     ONE LLM call answers directly; no logic, no prover

Other:
-llm NAME        LLM provider: gpt, claude, gemini, or deepseek
-version VER     Model version string, e.g. claude-sonnet-4-6
-nollmcache      Disable LLM response caching for this run
-geminicache     Enable Gemini server-side context caching (off by default)
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

One line each; see DOCUMENTATION.md §5 for the full per-module reference.

- `solve.py` — CLI entry point and `english_to_answer(text, options)`
- `llmparse.py` — two-stage LLM parser; `parse_text(text)` → `(s1_json, s2_json, stats)`; entity-ID case normalization between stages; runs `stage_sanity.check_stage{1,2}` and re-calls the LLM with a corrective prompt (max 2 retries per stage) on issues
- `llmcall.py` — LLM API wrapper (GPT/Claude/Gemini/DeepSeek) with retries and SQLite caching; `call_llm(sysprompt, input_text)`
- `logconvert.py` — top-level orchestrator for stage-2 JSON → GK clause list; `rawlogic_convert(logic, s1_json, fixes)`; structural repair (`_hoist_nested_ids`, `_repair_misnested_normally_implies`, `_strip_phantom_query_guards`), what-question population, Stage-1 entity bookkeeping; dispatches per-package work to `lc_packages`
- `lc_packages.py` — per-`@id` package processing: `extract_package_ctx`, `convert_id_package`, `_process_question`/`_process_assertion`, raw wh-word probes, confidence distribution
- `lc_rewrites.py` — pre-clausification formula rewrites: meta-predicate normalization, tense-valued `has_time` filtering, `inject_actuality` (marks real Davidsonian events; skips events carrying a Stage-2 modal classifier or that are the inner arg of a non-factive `has_content`), degree presuppositions, existential hoisting, polarity flip
- `lc_ctxt.py` — `$ctxt` context injection, time-wrapper stripping, fresh-variable generation, predicate classification constants
- `lc_post_normalize.py` — post-clausification normalising/repair: gradable predicate normalization, RELCLASS coercion, isa-entity stripping, possessive `have` inference, `have`→`has_part` bridges, degree stripping, population-fact extraction, compound subsumption
- `lc_post_reify.py` — reification of definite descriptions and measurements: `$theof1` rewrites, `$measure`→`$list` unit conversion, `less_measure` rewriting
- `lc_post_inject.py` — post-clausification dynamic axiom injection (soft synonyms, mutual-exclusion, noun-mutex, verb-result-state, acquire→have, positional/containment/attribute bridges, stable-adjective persistence, world-graph geometry). See "Semantic Normalization" below and DOCUMENTATION.md §7.7
- `lc_post_una.py` — entity UNA wrapping: prefix every Stage-1 numbered entity with `#:` so the prover treats distinct entity constants as unequal (required by axioms_std.js §7g). Render-time strip in `proof_utils`/`proof_logic`/`procproofs`
- `lc_clausify.py` — FOL-to-CNF compiler (implies/xor/equivalent elimination, NNF, normally expansion, Skolemization, distribution); Skolem helpers, `is_world_constant`, `singularize_isa_classes_in_node`
- `lc_questions.py` — question wrapping (`ask`/`question` → `@question`/`@askvars`), population-fact injection, WH-builders (`build_where/when/who/defq_question`), `hoist_generic_yn_subject` (bare-plural-generic yes/no rewrite)
- `lc_sets.py` — set/counting: `$setof` rewriting, membership axioms, element instantiation, set-existence facts
- `procproofs.py` — orchestrates prover-output post-processing; parses JSON, strips `#:`, drives answer selection (`proof_answer_select`) + formatting (`proof_answer_format`) + explanation (`proof_explain`)
- `proof_answer_select.py` — which bindings survive: tier ranking (concrete > Skolem > population), `$list` measure-value preference, unbound-var drop, class-name-leak and tautological-population filters (proof-scan `_is_tautological_population_answer` + clause-scan `_defined_property_witnesses`), proof dedup; `@what_query` preference split by `_what_query_is_relational`
- `proof_answer_format.py` — renders bindings to English: bool, who/what, where/when, generic join, confidence labels, Skolem-to-class resolution, plus query-shape probes
- `proof_explain.py` — English proof explanations from prover steps
- `proof_render.py` — facade re-exporting `proof_utils`, `proof_english`, `proof_logic`
- `proof_utils.py` — entity naming, Skolem type resolution, render context state, ambiguity detection
- `proof_english.py` — atom/clause → English; table-driven dispatch (`_PRED_TABLE`) + per-clause `_ClauseRenderCtx`. See DOCUMENTATION.md §5.9
- `proof_logic.py` — `pred(arg,...)` and JSON logic rendering
- `linguistics.py` — pure English heuristics (articles, conjugation, comparatives, gerunds)
- `prover.py` — invokes the `gk` binary subprocess; `call_prover(logic)`; auto-selects unit strategy on equalities with function terms
- `cache.py` — SQLite cache for LLM responses and prover results
- `globals.py` — global `options` dict and file paths
- `pretty.py` — JSON pretty-printer; `pp_str/pp_logic/pp_stage1/pp_stage2`
- `utils.py` — `debug_print`, `clause_list_to_json`
- `semnormalize.py` — post-clausification semantic normalization: antonym folding + canonical substitution (skips `$ctxt`, handles disjunctions)
- `data_canonicals.py` / `data_antonyms.py` / `data_synonyms.py` / `data_exclusions.py` — (generated) `CANONICALS` / `ANTONYMS` / `SOFT_SYNONYMS` / `EXCLUSION_GROUPS`+`EXCLUSION_INDEX` dicts from `mkdata/*.txt`
- `axiom_vocab.py` — extracts/caches axiom-file content words; restricts synonym/exclusion injection to pairs present in problem ∪ axioms
- `stage_sanity.py` — structural sanity checks for Stage-1/2 LLM output + corrective-retry kinds. Full check table: DOCUMENTATION.md §5.17 and §7.8

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

**Injectors** (`lc_post_inject.py`) — each emits dynamic axioms gated on input ∪ axiom-vocab presence:

| Injector | What it does |
|---|---|
| `inject_soft_synonyms` | biconditional synonym clauses (`has property`/`isa`/`has type`). Verb taxonomy: `_GENERAL_VERBS` emits only specific→general (`fly→go`, not reverse); `_BLOCKED_VERB_PAIRS` drops wrong pairs. `REQUIRE_BOTH_SIDES` |
| `inject_exclusion_axioms` | pairwise mutual-exclusion clauses; five atom shapes by group id (adjective `has_property`, `is_rel2` target/prep, `has_degree_rel2` proximity, `_ISA_EXCL_GROUPS` noun-mutex shortcut + cross-entity inequality) |
| `inject_isa_cross_group_axioms` | Layer-2 noun-mutex across different `_ISA_EXCL_GROUPS`; subsumption-aware (`_TOP_LEVEL_SUBSUMES`) |
| `inject_carrier_lifts` | plate/tray/etc. → `isa(carrier,X)` (feeds axioms_std.js §7f) |
| `inject_verb_result_state_axioms` | destroy/break/… → has property "destroyed"/… (Bridge A event-based, Bridge B stative); runs before `inject_exclusion_axioms` |
| `inject_acquire_have_axioms` | buy/purchase/acquire/obtain → `have(actor, obj)`; benefactive Bridge B for buy/get (case 1163) |
| `inject_positional_actor_bridges` | `has_location(E,L,PREP) + has_actor(E,X) → is_rel2(PREP,X,L)` for positional preps (case 670) |
| `inject_containment_bridges` | "filled with"/"full of" → `is_rel2("in", content, container)` (case 673) |
| `inject_attribute_relation_bridges` | color/shape/material/taste value ↔ `is_rel2("color of"/…)` (case 901) |
| `inject_stable_adjective_persistence` | same-world past→present for stable individual-level adjectives (case 911, §7.14) |

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
deepseekversion  = "deepseek-chat"       # V3.2; "deepseek-reasoner" for thinking
temperature      = 0
default_max_tokens = 8000
```

API keys are read from JSON files at `../secrets/{gpt,claude,gemini,deepseek}_secrets.txt`.
LLM responses are cached by default in `cache.db` (SQLite), keyed on provider, version, temperature, max_tokens, sysprompt and input. Use `-nollmcache` to disable.

### Dependencies

The `gk` binary and its data files must be present:
```
llmpipe/axioms_std.js
../gk/gk                    (binary)
../gk/gk_name_number.txt
../gk/gk_taxonomy_packed.txt
```
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
