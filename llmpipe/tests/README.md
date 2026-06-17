# tests/

Test files for the llmpipe pipeline.  Each file is a Python literal — a
list of `[id, input, expected]` triples.  The leading `id` is an integer
case number (required, and stable across runs) used by `test.py`,
`runtests.py`, `examine.py`, and `testfixlog_may.txt`.  `input` is the
English text and `expected` is the expected answer.  Run with
`python3 test.py <file>` (single LLM) or `python3 runtests.py <file>`
(all LLMs in parallel) from the parent directory.

These test sets and their recorded multi-LLM results are also published, with
analysis, in the [nlformtasks](https://github.com/tammet/nlformtasks) repository.
The files are **renamed there** (same content, flipped naming convention —
`tests_<x>` here becomes `<x>_tests` under `core/`/`folio/` in the release):

| here (`tests/`) | nlformtasks (`tests/`) | content |
|---|---|---|
| `tests_core.py` | `core/core_tests.py` | identical |
| `tests_core_100.py` | `core/core_tests_100.py` | identical |
| `tests_folio_v2.py` | `folio/folio_tests.py` | identical |
| `tests_core_challenging.py` | `core/core_tests_challenging.py` | same 341 cases; differs only in header/blank lines |

The names here are canonical (wired into `runtests.py`/`test.py`); the release
renamed them for publication only.

## Files

### Core

- **`tests_core.py`** — the current main test suite (~1600 cases).
  This is what `python3 test.py` runs by default.

- **`tests_core_100.py`** — a 100-case representative subset of
  `tests_core.py`, for fast smoke runs across all LLMs.

- **`tests_core_challenging.py`** — the 341 hardest core cases (≥2 total
  errors across the 4 core experiments × 4 LLMs; the union of the medium
  and hard difficulty tiers). Auto-generated from `tests_core.py` via
  `difficulty_matrix.json`; published as `core/core_tests_challenging.py`.

### FOLIO

- **`tests_folio_v2.py`** — the FOLIO v2 validation split, all 203 items,
  original gold labels. The canonical FOLIO set.

- **`tests_folio_v2_refined.py`** — identical inputs to `tests_folio_v2.py`,
  but with 3 prover-verified corrected labels (cases 980, 981, 754). A
  re-score variant, not a separate run.

- **`FOLIO_yale/`** — upstream FOLIO source data (`folio_v2_{train,validation}.jsonl`
  + a readable dump) the two FOLIO sets are built from.

### Other benchmarks

- **`tests_hans.py`** — a HANS benchmark selection (subject/object-swap
  entailment templates); each case carries its HANS template-pattern label.

### Notes

- **`HARD_CASES_MEMO.md`** — running notes on hard/unsolved cases and proposed
  encodings.

## Running

Two runners drive these files, both from the parent (`llmpipe/`) directory.

### `test.py` — quick single-LLM runs

Best for iterating on one LLM and eyeballing failures.

```bash
# default — tests_core.py
python3 test.py

# explicit file + LLM
python3 test.py tests/tests_core.py -llm claude

# subset
python3 test.py tests/tests_core_100.py -limit 20
python3 test.py tests/tests_core.py -filter "penguin"
```

`test.py` auto-resumes from `test_output.txt` — re-running re-uses previous
results unless `-restart` is passed.  See `python3 test.py -help` for all flags.

### `runtests.py` — full multi-LLM batch runs (recommended)

The batch runner: every case × the requested LLMs, writing one JSON file per
case+LLM under `testresults/<name>/<llm>/case_NNNN.json` (with stage-1/2 JSON,
clauses, prover command and proof) plus a live `summary.json`.  This is how the
recorded results published in [nlformtasks](https://github.com/tammet/nlformtasks)
are produced, and the right tool for a complete pass across all four LLMs.

```bash
# all four LLMs (claude, gpt, gemini, deepseek), full suite
python3 runtests.py tests/tests_core.py

# the 100-case subset, run sequentially (good for cache-served reruns)
python3 runtests.py tests/tests_core_100.py -sequential

# pick LLMs / re-run failures
python3 runtests.py tests/tests_core.py -llms claude,gpt -redo-errors
```

It resumes by skipping cases whose JSON already exists (`-redo` / `-redo-errors`
override).  See DOCUMENTATION.md §10 "Running tests" for the full flag list.
