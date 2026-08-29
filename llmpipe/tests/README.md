# tests/

Test files for the llmpipe pipeline.  Each file is a Python literal — a
list of `[id, input, expected]` triples.  The leading `id` is an integer
case number (required, and stable across runs) used by `test.py`,
`runtests.py`, and the result folders.  `input` is the
English text and `expected` is the expected answer.  Run with
`python3 test.py <file>` (single LLM) or `python3 runtests.py <file>`
(all LLMs in parallel) from the parent directory.

**Not every set here is ours.** FOLIO, Multi-LogiEval, HANS and EntailmentBank
are third-party benchmarks redistributed under their own licenses, which the
root Apache-2.0 `LICENSE` does not replace. Attribution, provenance and what we
changed are in [`THIRD_PARTY.md`](THIRD_PARTY.md); the license texts are in
[`licenses/`](licenses/); the short form is in the repository root `NOTICE`.

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

- **`tests_core_abstregress.py`** — 314 core cases that the abstraction
  encodings regressed; used to test converter changes.

- **`tests_core_challenging.py`** — the 341 hardest core cases (≥2 total
  errors across the 4 core experiments × 4 LLMs; the union of the medium
  and hard difficulty tiers). Auto-generated from `tests_core.py` via
  `difficulty_matrix.json`; published as `core/core_tests_challenging.py`.

### FOLIO

- **`tests_folio_v2.py`** — the FOLIO v2 validation split, all 203 items,
  original gold labels. The canonical FOLIO set.

- **`FOLIO_yale/`** — the upstream FOLIO validation split
  (`folio_v2_validation.jsonl` plus a readable dump) that `tests_folio_v2.py`
  is built from, with its attribution.

### Other benchmarks

All of these are third-party data; see [`THIRD_PARTY.md`](THIRD_PARTY.md).

- **`tests_multilogieval.py`** — the full Multi-LogiEval import (1651 cases:
  propositional, first-order and non-monotonic logic, depths 1–5). Per-case
  depth and logic metadata in `tests_multilogieval_meta.json`, keyed by id.
- **`tests_multilogieval_sample.py`** — a 20-case sample of the above, with
  `tests_multilogieval_sample_meta.json`.
- **`tests_multilogieval_100.py`**, **`tests_multilogieval_heldout100.py`** —
  two disjoint 100-case seeded samples, used for the mixed-benchmark runs.
- **`tests_eb_100.py`**, **`tests_eb2_100.py`** — 100-case seeded samples of
  the EntailmentBank task-1 sets.
- **`tests_eb_negatives_2026_08.py`**, **`tests_arc_negatives_2026_08.py`** —
  negative controls built from EntailmentBank passages, giving the family its
  `False.` and `Unknown.` answers.
- **`tests_cohort165_eb.py`**, **`tests_cohort165_eb2.py`**,
  **`tests_cohort165_mle2.py`** — the per-family slices of the 165-case cohort.
- **`tests_hans.py`** — a HANS benchmark selection (subject/object-swap
  entailment templates); each case carries its HANS template-pattern label.

The sample files are generated, not hand-edited; each header records the tool
and the seed that produced it.

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
override).  See ../docs/reference/command-line.md for the full flag list.
