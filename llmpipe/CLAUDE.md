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

Grouped by role; **see DOCUMENTATION.md §5 for the full per-module reference** and
ENCODINGS.md for the representations they produce. Many concerns are split across
small cohesive files (façade re-exports keep importers stable), so reach for §5
rather than guessing from a name.

- **Entry / parsing** — `solve.py` (CLI + `english_to_answer`), `llmparse.py` (two-stage parser, entity-ID normalization, corrective-retry loop), `llmcall.py` (LLM API + SQLite cache), `stage_sanity.py` (Stage-1/2 sanity checks; façade over `stage_sanity_{core,s1,s2,guards}.py`), `directanswer.py`.
- **Logic conversion** (`logconvert.rawlogic_convert` orchestrates) — `lc_encoding.py` (the `EncodingConfig` gate resolver — single source of truth), `lc_packages.py` (per-`@id`), `lc_rewrites.py` (pre-clausification rewrites), `lc_repairs.py` (structural repairs), `lc_clausify.py` (FOL→CNF), `lc_ctxt.py` (`$ctxt`/time), `lc_questions.py` + `lc_query_guards.py` (questions, guard/what-population), `lc_sets.py` (sets/counting), `lc_coarse.py` + `lc_existfold.py` (event folds), `lc_entity_isa.py` (taxonomy `isa`), `lc_finalize.py` (strict/abstract finaliser).
- **Post-clausification passes** — `lc_post_normalize.py`, `lc_post_have.py`, `lc_post_reify.py`, `lc_post_inject.py` (+ `lc_inject_synonyms.py`, `lc_inject_scan.py`), `lc_post_population.py`, `lc_post_una.py`, `semnormalize.py`, `axiom_vocab.py`; shared traversal in `treewalk.py`. See "Semantic Normalization" below and DOCUMENTATION.md §7.7.
- **Proving + proofs** — `prover.py` (gk subprocess), `procproofs.py` → `proof_answer_select.py` / `proof_answer_format.py` / `proof_explain.py`; rendering via `proof_render.py` façade over `proof_utils.py` / `proof_english.py` / `proof_terms.py` / `proof_logic.py`, plus `entity_map.py` and `linguistics.py`. See DOCUMENTATION.md §5.9 and PROOF_RENDERING.md.
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
