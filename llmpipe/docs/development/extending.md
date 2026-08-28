# Extending the pipeline

This page describes how to add a provider, a predicate, an encoding,
a stage, a retry, a proof renderer or a benchmark.

Adding a retry stage takes four steps. Add the stage name to
`globals.PIPELINE_ORDER`. Add its flag to `globals.options`. Add an entry to
each configuration in `globals.PIPELINES`. Call `solve.run_stage` with the
stage body.

Adding a provider takes three steps. Add a `call_<name>` function in
`llmcall.py`. Add its version variable and price. Add the name to the
dispatch in `call_llm` and to the model tables used by the test runners.

## Adding new predicates

1. Add the predicate to the whitelist table in `prompts/stage2_instructions_full.txt` (section
   `== 5. PREDICATE INVENTORY ==`).
2. Add examples to `prompts/stage2_examples.txt` showing the new predicate in context.
3. If the predicate should receive `$ctxt`, add it to `CTXT_ELIGIBLE` in `lc_ctxt.py`.
4. If the predicate needs to render in an explanation, add an entry to
   `_PRED_TABLE` in `proof_render.py` (or a special-case handler in `_render_atom`).

## Modifying Stage-1 parsing behaviour

Edit `prompts/stage1_instructions_full.txt` and add/update examples in `prompts/stage1_examples.txt`.
The most impactful sections are:
- `== 4. TYPE CLASSIFICATION ==` — when to use `real`/`situation`/`strict_rule`/`normal_rule`
- `== 12. ADJECTIVES ==` — the adjectives field format
- `== 8. SCOPE HINTS ==` — dependent/global/kind scope for generics

## Modifying Stage-2 compilation behaviour

Edit `prompts/stage2_instructions_full.txt` and `prompts/stage2_examples.txt`.  The most impactful
sections are:
- `== 4. QUANTIFICATION RULES ==` — how each ASU type is compiled to FOL
- The Property and Relation Predicate Selection Rule — `has degree property` vs `has property`

## Defeasible bridge axioms in `axioms_std.js`

A recurring pattern: bridge a surface verb to a canonical predicate **defeasibly** so other readings can override it.  Shape: `[-source(...), canonical(...), $block(0, $not canonical(...))]` at `@confidence` < 1.  Examples currently in the file: `pass → give` at 0.85 (most "pass" events are transfers, but exam-passing should not be); `keep ... in/at LOC → is_rel2` at 0.95 (two siblings — `has_location` and `has_destination`).  Use this pattern when a surface word has a dominant canonical reading but rare alternatives must remain reachable; use a hard rewrite (no `$block`) only when the equivalence is exceptionless.

## Adding a new LLM provider

In `llmcall.py`, add a `call_newprovider(sysprompt, input_text, version, max_tokens)` function
following the pattern of `call_claude`, `call_gpt`, or `call_deepseek`, then dispatch from
`call_llm` when `llm == "newprovider"`.

## Improving proof post-processing

`procproofs.py` orchestrates answer post-processing; selection lives in
`proof_answer_select.py` and rendering in `proof_answer_format.py`.  Key extension points:
- `proof_explain.format_explanation` — generates the step-by-step English proof
- `_answer_goodness` in `proof_answer_select.py` — the sorting key for ranking multiple candidate answers
- `_filter_by_best_tier` in `proof_answer_select.py` — selects among concrete, Skolem, and population answers

## Running tests

There are two runners.  Both read the same test files, but each test file is now a list of
`[id, input, expected]` triples (the leading integer `id` is required — it is the stable case
number used across the runners and the result folders).

**`test.py` — single LLM, human-readable, resumable.**  Writes a flat `test_output.txt`
and re-uses prior results unless `-restart` is passed.

```bash
python3 test.py                         # run all tests with the default LLM
python3 test.py tests/tests_core.py -llm claude
python3 test.py tests/tests_core.py -filter penguin -limit 20
```

**`runtests.py` — every case × N LLMs in parallel, machine-readable.**  For each case it
runs the requested LLMs concurrently (one worker per LLM) and writes one JSON file per
`(case, llm)` to `testresults/<testname>/<llm>/case_NNNN.json`, where `<testname>` is derived
from the test filename (`tests/tests_core.py` → `core`).  After every case it rebuilds each
LLM's `summary.json` (pass/fail/error counts plus a `failed_or_errored` list), so progress is
live and a run can be inspected or interrupted at any point.

```bash
# default: all four LLMs (gpt, claude, gemini, deepseek) over tests/tests_core.py
python3 runtests.py

# pick LLMs and a test file
python3 runtests.py -llms claude,gpt tests/tests_core.py
python3 runtests.py -llms gemini tests/tests_core_100.py

# selection
python3 runtests.py -ids 11,15,18          # only these case ids
python3 runtests.py -limit 50              # first 50 cases
python3 runtests.py -filter penguin        # cases whose input contains "penguin"

# run sequentially in-process (best for cache-served reruns)
python3 runtests.py -sequential -llms claude tests/tests_folio_v2.py

# model/decoding overrides (apply to all -llms in the run)
python3 runtests.py -version claude-opus-4-8 -think 3000 -maxtokens 16000 ...

# pipeline-mode flags (they mirror solve.py; see the abstraction page)
python3 runtests.py -abstract -prenorm [-nocrossstage] ...

# any other solve.py flag: the runner parses its own arguments and hands the
# rest to solve.py's parser, so -stack, -stack-closed, -stack-open,
# -graphtrans, -litbridge, -nolitbridge, -critic and the rest work here
# unchanged.  A flag solve.py does not know is an error, not a silent skip.
python3 runtests.py -abstract-max -noprenorm -nolitbridge -graphtrans -critic ...
python3 runtests.py -combined-instr prompts/combined_v2_instructions_full.txt \
                    -combined-examples prompts/combined_examples_pure.txt ...
python3 runtests.py -directanswer prompts/folio_directanswer_instructions.txt ...

# output-dir suffix: results go to testresults/<set>_<tag>/ instead of testresults/<set>/
python3 runtests.py -tag myexperiment ...
```

Variant modes auto-suffix the set name (`-combined-*` derives a tag from the prompt
filenames; `-directanswer` uses `directanswer`; `-tag` overrides), so variant results
live beside — never on top of — the plain two-stage `testresults/<set>/` data.

**The runner's `-abstract-max`.**  The runner parses `-abstract-max` itself, so its
expansion must assign the same six stage keys `solve.py`'s does: all six on, the
converter preset plus the open-world stack.  A `-stack*` set, an explicit stage
switch and every cancel reach `solve.py`'s parser through `_solve_options` and are
merged after that block, so they still override it.  An experiment that names the
stage flags explicitly is unambiguous whatever the preset does, and naming them is
the safer habit — a stored folder's `stages_enabled` says what actually ran.

**Per-case reporting.**  Every case JSON carries `answered_by` (`front_door`,
`fallback_norm`, `fallback_hyp`, `critic`, `graphtrans`, `litbridge`, `graphbridge`
or `none`), `front_door_answer`, `abstraction_order`, `stages_enabled` (the six
stage keys this run had on, in stage order, so the folder says what ran without its
command line), `llm_call_counts` (per stage tag: calls, live calls, retries),
`llm_calls_total`, and the stage records (`fallback`, `critic`, `graphtrans`,
`litbridge`, `graphbridge`).  `summary.json` totals
`answered_by` and the calls over the whole run.  The same block is printed by
`solve.py -summary` / `-summary-json`.

**The top-level fields describe the ANSWERING stage's gk call.**  `answer`,
`nl_proof`, `proof` (the gk result as JSON), `gk_command`, `final_clauses` and
`final_clause_trace` all describe the one gk call that produced the final answer,
whichever stage made it — the initial attempt, a fallback, the critic's rerun, or a
graph or literal bridge.  Two fields are new beside them:

| field | what it holds |
|---|---|
| `front_door_proof` | the initial attempt's own gk result, kept when a later stage answered |
| `front_door_gk_command` | the initial attempt's own command, likewise |
| `stages` | one row per stage, in stage order: `stage`, `ran`, `answered`, and either the stage's own `answer` (first line, `null` when it found none) or `why` it did not run |

`stages` is a separate information block, so a reader can see which stages ran and
which produced the result without any ordinary key changing shape.

**A run that returned early** — a truncated Stage-1 reply whose Stage 2 comes back
empty, or the api-timeout cap — never reaches the block that writes `answered_by`
and the stage rows.  `solve._english_to_answer` records its `Error: …` message as
the `answer` and writes `stages_enabled` anyway, and `runtests.py` gives it an
`error` payload when the run has neither `answered_by` nor `stage2`, so it is
counted rather than stored as a file indistinguishable from a case that ran.  A run
that DID parse and then hit a converter or prover error keeps its message as a
scored answer.  `-summary` and
`-summary-json` carry the same list, and `-logic` and above print it as an
`=== stages ===` block:

```
=== stages ===

  front_door     ran   Unknown.
  fallback_norm  ran   no answer
  fallback_hyp   ran   no answer
  critic         off
  graphtrans     ran   True.  <- the answer
  litbridge      off
  graphbridge    off
```

`clauses` is the initial attempt's clause list at every level; `final_clauses` is the
theory the answer rests on, so the two differ whenever a later stage answered.
When nothing after the initial attempt answers, the top-level fields are the front
door's and the two `front_door_*` fields are absent.  This matters because every
`prover.call_prover` writes `collect["gk_command"]`: without the snapshot a stage
that RAN without answering would leave its own command at the top level.
`solve._set_answering_call` is the one place that decides it.

**Provenance stamp:** every `summary.json` carries a `pipeline_git` object —
`{"commit": ..., "dirty": ..., "tags": [...]}` — recorded at run start
(`pipeline_git_state()`; the dirty flag covers tracked files only).  This ties each
results dir to the exact pipeline state that produced it.

**Resumption:** a `(case, llm)` is skipped if its JSON already exists.  Re-running therefore
continues where a quota-exhausted or interrupted run stopped.  Pass `-redo-errors` to also
re-run cases whose JSON contains an `"error"` key, or `-redo` to overwrite everything.  A
solo-Gemini run (`-llms gemini`) inserts a small per-case throttle, since without other LLMs
sharing the loop its back-to-back Stage-1/Stage-2 calls hit per-minute rate limits easily;
context caching is on by default (see [the source map](../code/source-map.md)), which matters most on tiers with a tight per-request input cap.

The per-case JSON holds the full collected artifact set — `stage1`, `stage2`, `clauses`,
`gk_command`, `proof`, `nl_proof`, `answer`, `correctness` — so failures can be triaged
without re-running the pipeline.

To regenerate the logconvert pretty-print check file after changes to `logconvert.py`:
```bash
python3 run_pretty_check.py > logconvert_check.txt
```

---

## Related documentation

- [Testing](testing.md)
- [Orchestration code](../code/orchestration.md)
- [Source map](../code/source-map.md)
