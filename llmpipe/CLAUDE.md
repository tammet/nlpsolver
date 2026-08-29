# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Detailed reference lives in `docs/`; this file stays concise and defers to it.

| where | what |
|---|---|
| `docs/getting-started.md` | installation, model selection, first commands |
| `docs/architecture/` | what each subsystem does and in what order |
| `docs/encodings/` | the normative Stage-1, Stage-2 and GK clause formats |
| `docs/reference/` | command line, configuration, runtime records, proof output, glossary |
| `docs/code/` | the per-module source map |
| `docs/development/` | extending, testing, regenerating the generated data |
| `docs/mechanisms/` | which mechanisms were adopted, kept optional, or set aside, and the evidence |

When this file and `docs/` disagree about a format, `docs/encodings/` is
normative. When they disagree about an option, `docs/reference/command-line.md`
is.

## Overview

`llmpipe` is an experimental pipeline for semantic parsing of natural language into extended first-order predicate logic using LLMs (OpenAI GPT, Anthropic Claude, Google Gemini, DeepSeek). The logic includes defeasible formulas and probabilistic confidence annotations. It is part of the larger `nlpsolver` repository. Parsed logic is passed to the `gk` binary theorem prover, which returns answers.

## Repository layout

**Tracked (committed):** `solver/` (pipeline code), `tests/` (the test sets, their
third-party attribution and licence texts, and the FOLIO validation source),
`prompts/` (the prompts the pipeline loads, plus the four the published paper runs
named), `docs/` (the reference documentation), `mkdata/` (solver-data generators),
`axioms_std.js`, `README.md`, this file, and the top-level runners `runtests.py` /
`test.py` / `ask.py`.

Anything named below is **local only**: it is on this machine and not in the
repository, so a statement that cites it is provenance, not something a reader
elsewhere can open.

**Untracked / gitignored (local working data):**
- `testresults/` — per-run batch results, grouped into five directories: `milestones/` (reference runs kept for later comparison — the paper baselines and the 2026-08-29 full run of the `balanced` default, each with its own `tests/`, `SUMMARY.md` and README), `nesy_2026/` and `lpar_2026/` (the two paper releases), `old/` (every other run), and `analysis/` (write-ups about the runs). No run folders and no loose files sit at the top level. Run folders are named `<benchmark>_<shape>_<date>` and mirror the published [nlformtasks](https://github.com/tammet/nlformtasks) package. See `testresults/README.md` and `testresults/milestones/README.md`.
- `fixlogs/` — `testfixlog_*.txt` fix logs (hand-maintained).
- `memos/` — dated session memos and notes.
- `debug/` — `examine.py` output + FOLIO scratch; `elogs/` — experiment logs.
- `prompts/archive/` and the superseded drafts and snapshots listed in `.gitignore` — `prompts/README.md` says which prompts the repository tracks and why.
- `ideas/`, `lparpaper/`, `nesypaper/` — research / paper material.
- `cache.db` — SQLite LLM+prover cache.
- `tools/` — the fixture suites, experiment harnesses and documentation checks this repository is developed against; `examine.py` and `compare_runtests_json.py` are local top-level helpers. The docs cite these by name as provenance; a reader outside this machine does not have them.
- `external_data/`, `tests/external/`, `tests/tests_external_*.py` — raw corpora and converted external cases, with a local lock file recording each source's licence and a pinned URL.

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

`docs/reference/command-line.md` is the full list, `experimental-options.md`
the research options, and `configuration.md` how they resolve.  What matters
here is what a bare command line already does.

**A bare command line resolves to `-pipeline balanced`.**  It runs the initial
attempt and then, while the answer is unresolved, four retry stages in order:
`fallback_norm`, `fallback_hyp` (deterministic, no model call), `critic`, then
`graphtrans` (one model call each).  The first definite answer stops the rest.
`globals.PIPELINES[globals.DEFAULT_PIPELINE]` is the one declaration of those
defaults, so `solve.py` and `runtests.py` cannot drift.  `-pipeline
conservative` is the two deterministic fallbacks only; `high-recall` adds the
graph bridge.  `docs/architecture/retries.md` describes each stage.

**The two safe proof shorteners are attempted by default** on the ordinary
canonical theory: `davidson2` compresses a complete event spine, `existfold2`
folds a repeated existential part-whole pattern.  Either refuses locally and
leaves the source form unchanged.  `-noproofshort2` reproduces the older
theory.  See `docs/architecture/proof-shortening.md`.

Other defaults: provider `gemini`, prover limit 2 seconds, LLM cache on,
per-call LLM deadline 240 seconds, no call-count limit.

```
Output level, each including the previous:
-explain  answer + English proof   -logic  + clauses and per-step logic
-details  + stage-1/2 JSON and prover input/output   -debug  + raw responses
Every block is printed for the stage that ANSWERED, under the same headers, so
a run with a retry prints them twice; `--- stage: NAME ---` says whose they are.

Common:
-llm NAME / -version VER   provider and model     -seconds N   prover limit
-summary                   which stage answered, and the call counts
-json / -jsonlogic         logic as raw JSON      -nosolve     parse only
-gkin FILE                 save the GK input      -nollmcache  see the rules below

Diagnosis (used by the Debug Case Workflow below):
-axioms FILE ...  other axiom files, or none at all   -strategy FILE
-prover  prover parameters    -rawresult  unprocessed prover output
-printlevel N                 -clearcache  empty the LLM cache (asks first)
-nocontext                    drop $ctxt worlds and tense, to test its effect
```

Settings that are module constants rather than flags — `litbridge_grader.MODE`,
`graph_procedure.LIFT` / `EVIDENCE` / `DEFAULT_SOURCES`,
`globals.ABSTRACTION_ROUTES`, and each fallback's own booleans — are listed in
`docs/reference/configuration.md`.

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

**`docs/code/source-map.md` is the per-module reference**, generated from the
modules themselves; `docs/encodings/README.md` describes what they produce.
Concerns are split across small files with façade re-exports, so reach for the
source map rather than guessing from a name.  The groups:

| role | entry points |
|---|---|
| entry and parsing | `solve.py`, `llmparse.py`, `llmcall.py`, `stage_sanity.py`, `directanswer.py` |
| logic conversion | `logconvert.py` orchestrates the `lc_*` modules; `lc_encoding.py` resolves the encoding and is the single source of truth |
| post-clausification | `lc_post_*.py`, `semnormalize.py`, `axiom_vocab.py`, traversal in `treewalk.py` |
| proving and proofs | `prover.py`, `procproofs.py`, the `proof_*` modules, `entity_map.py`, `linguistics.py` |
| retry stages | `fallback_norm.py`, `fallback_hyp.py` (no model call), `critic_pass.py` + `critic_render.py`, `graph_p0.py` + the eight `graph_*` modules, the seven `litbridge_*` modules |
| infra and data | `globals.py`, `cache.py`, `pretty.py`, `utils.py`, generated `data_*.py` |

Each retry stage has an architecture page: `docs/architecture/retries.md`,
`graph-representation.md`, `literal-bridges.md`.

### Semantic Normalization

After clausification, before the prover (`-nosemnormal` disables).
`semnormalize.sem_normalize_clauses` runs two passes over the clause list:
antonym folding (a word in `ANTONYMS` flips the atom's polarity and is
replaced) and canonical substitution (a word in `CANONICALS` is replaced).
Both skip `$ctxt` terms.  Soft-synonym and exclusion axioms are injected
earlier, inside `rawlogic_convert`.

The injectors, the polarity rules, the curated data and the reasons verb
antonyms are excluded are in `docs/architecture/compilation-transformations.md`
and `docs/development/generated-data.md`.  Regenerate the data files with
`cd mkdata && python3 build_solver_data.py` after editing `mkdata/*.txt`.

### Logic Representation

Stage-2 output, and the clause list `logconvert` produces from it:

```
["and", ["@id","S1", PACKAGE], ...]      PACKAGE = ["holds",world,F] | ["question",F]
                                                 | ["ask",var,F] | ["and",PKG,["@p","Sx",p]]
[{"@name":"sent_S1", "@logic": CLAUSE}, ...]      assertion
{"@name":"sent_S1", "@question": FORMULA}         query
```

Variables carry a `?:` prefix, negation a `-` prefix on the predicate name.
`docs/encodings/` is normative for all three layers.

### Modal Classifiers

Modality is an arity-1 predicate on the Davidsonian event variable, the last
conjunct of the event's `and` block:

```
["isa","activity","E"], ["has type","E","fly"], ["has actor","E","X"], ["capability","E"]
```

Eight Stage-2 classifiers map 1:1 with the Stage-1 `mode` enum; the four
mental and speech modes reify two events linked by `has content`.  A ninth,
`actuality(E)`, is injected by the pipeline (`lc_rewrites.inject_actuality`),
never by Stage 2, and is hidden from English rendering.  The enum, the
conditions on the injection and the axioms it feeds are in
`docs/encodings/stage-2.md`.

### Prompt Files (`prompts/`)

The two-stage parser reads six files; `llmparse._compose_prompt` concatenates
instructions, then examples, then checklist:

```
prompts/stage{1,2}_instructions_full.txt   prompts/stage{1,2}_examples.txt
prompts/stage{1,2}_checklist_full.txt
```

The retry stages have their own directories — `prompts/critic/`,
`prompts/graph/`, and `prompts/dynamic_alignment/` for the literal bridge,
whose name predates the mechanism.  `prenorm_full.txt`,
`folio_directanswer_instructions.txt` and the two `combined_*` files serve
their own switches.  `prompts/README.md` says which prompts the repository
tracks and why; `docs/code/prompt-map.md` maps each file to the module and
switch that reach it.  Superseded drafts are kept locally and listed in
`.gitignore`.

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

`tests/README.md` describes the file format and the runners.  Several sets are
**not our data**: FOLIO, Multi-LogiEval, HANS and EntailmentBank are
redistributed under their own licences, which the root Apache-2.0 `LICENSE`
does not replace.  `tests/THIRD_PARTY.md` records the authors, paper, source
and what we changed for each; `tests/licenses/` holds the licence texts; the
root `NOTICE` carries the short form.  **Adding a test set derived from an
outside corpus means adding its row to `tests/THIRD_PARTY.md` and its licence
to `tests/licenses/` in the same change.**

- `tests/tests_core.py` — list of `[id, input, expected]` triples for the core pipeline
- `testresults/milestones/core_two-stage_2026-06-03/<llm>/case_NNNN.json` — latest core batch results per LLM (input, expected, answer, correctness, stage1/stage2/clauses/gk_command/proof); the primary debug input. (`testresults/` is gitignored; run folders follow `<benchmark>_<shape>_<date>`.)
- `testresults/milestones/core_two-stage_2026-06-03/multi_failed.{txt,json}` — triage list of cases any LLM failed

## Debug Case Workflow

Every file this workflow reads is local only — `fixlogs/`, `testresults/` and
`debug/` are not in the repository, so the workflow runs on this machine and
nowhere else.

When the user says **"Debug case N"** (N is a case id in `fixlogs/testfixlog_june.txt` or the `testresults/milestones/core_two-stage_2026-06-03/multi_failed.txt` list):

1. **Read the four batch result files** for Case N — `testresults/milestones/core_two-stage_2026-06-03/{claude,gpt,gemini,deepseek}/case_NNNN.json` (zero-padded to 4 digits). Each JSON contains `input_text`, `expected_answer`, `answer`, `correctness`, plus `stage1`, `stage2`, `clauses`, `gk_command`, `proof` — no need to re-run the solver to inspect parse/proof (they come from the SQLite cache and match a fresh run). For fuller `-debug -explain -logic` logs, run `python3 examine.py N` → writes `debug/eN_{gemini,claude,gpt,deepseek}.txt`.
2. **Note the `Input:` text and `Expected:` value** — from the JSON and/or the `fixlogs/testfixlog_june.txt` entry.
3. **Compare across all four LLMs** — read the JSONs/logs fully. For a UDP-pipeline reference answer (not in the batch, not run by `examine.py`), run the udppipe solver manually and include it when informative.
4. **Examine Stage 1 and Stage 2** — a correct final answer is not sufficient. Report major conceptual differences (wrong entity types, missing isa guards, flat vs nested quantifiers, dropped conditions). Both stages must be correct.
5. **Assess the Expected value** — form an independent opinion on whether it is correct under a normal reading, or should change. A UDP answer is correct in most but not all cases.
6. **Analyze errors** — find the root cause (stage-1 parse, stage-2 logic, logconvert, prover input, proof post-processing).
7. **Test with -nocontext if $ctxt suspected** — `python3 solver/solve.py -nocontext "..."`. Succeeds without context but fails with → the issue is `$ctxt` injection.
8. **Simplify if uncertain** — construct a minimal version isolating the suspected issue and run it.
9. **Prover-timeout suspected?** — try in order: (a) run without `axioms_std.js`; (b) swap strategy to `{"strategy":["unit"]}` or `{"strategy":["query_focus"]}` with `query_preference:1`; (c) last resort, raise `-seconds`. If an alternate strategy is much faster, the default may need to change.
10. **Write analysis and fix plan** — summarize root cause(s) and propose a concrete plan. Do **not** write code or modify files at this stage.

**Fix scope.** This restricts the June 2026 debugging campaign and holds while
that campaign is the work: fixes go into **pipeline code, axioms, or test
criteria** (including removing or correcting a bad test case), and the prompt
files stay unchanged.  If a case needs a `prompts/` change, postpone it —
record the diagnosis in `fixlogs/testfixlog_june.txt` (local) and move on.  Ask
before applying this rule to work outside that campaign.

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

- `runtests.py` — batch runner: every `[id,input,expected]` case × N LLMs in parallel, one JSON per (case, llm) under `testresults/<name>/<llm>/case_NNNN.json`, with a live `summary.json`. Resumes by skipping existing files; `-redo`/`-redo-errors` override; `-sequential` runs serially. See docs/reference/runtime-records.md.
- `test.py` — quick single-LLM runner; resumes from `test_output.txt`, `-restart` wipes it.
- `ask.py` — one direct LLM call, no logic and no prover.

Local only, not committed: `examine.py` (per-LLM `-debug -explain -logic` logs
for one case id, written to `debug/eN_{gemini,claude,gpt,deepseek}.txt`, used by
the Debug Case Workflow), `compare_runtests_json.py` (diffs two `runtests.py`
result trees), and the collection / comparison / prompt-check helpers under
`tools/`.
