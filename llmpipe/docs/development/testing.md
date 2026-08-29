# Testing

How to check a change to the pipeline, and the two conventions a test has to
respect.

## Two conventions

`PYTHONHASHSEED=0`. Conversion output depends on the hash seed, so a check that
compares clause lists sets it:

```bash
PYTHONHASHSEED=0 python3 solver/solve.py -jsonlogic "TEXT"
```

The local response cache is on by default. A repeated run answers from it and
makes no provider request. Do not disable it to force fresh calls unless that
is the point of the run: the cache is the reason repeated runs are cheap and
reproducible.

## Running the test sets

Two runners drive the files in `tests/`:

```bash
# one provider, readable pass/fail, resumable
python3 test.py tests/tests_core.py -llm gemini -limit 5

# several providers, one JSON record per case and provider under testresults/
python3 runtests.py tests/tests_core.py -llms gemini,deepseek -limit 5
```

`tests/README.md` describes the test-file format, the two runners and how they
resume. [Runtime records](../reference/runtime-records.md) describes the fields
of a stored record.

Both commands print help when called with no arguments. `test.py` resumes only
from an exact key containing the test source, case, provider, version, solver
configuration, scoring policy, and pipeline source state. `runtests.py` writes
a configuration manifest and refuses to mix incompatible runs in one result
directory; it also writes per-provider summaries and a combined cross-provider
summary.

The answer matcher is permissive by design. It normalizes presentation details
including case, punctuation, coordinated-answer order, confidence wording,
selected prepositions, and equivalent units. Every batch case record includes
the machine-readable policy used for its `correctness` field.

Start small. A full pass over `tests_core.py` is 1600 cases per provider and
makes a provider request for every case the cache does not already hold.

## Checking a converter change

A converter change is easiest to judge on the clause list rather than the
answer, because an answer can stay right while the theory changes:

```bash
PYTHONHASHSEED=0 python3 solver/solve.py -jsonlogic -nosolve "TEXT"
```

`-nosolve` stops before the prover. Compare the output before and after the
change. `tests/tests_core_abstregress.py` collects 314 core cases that the
abstraction encodings regressed, and is the quickest broad check that a
converter change has not reintroduced one.

## Call accounting

A check that counts model calls reads `llmcall.call_counts()` and the per-stage
rows. Two identities hold in both: `allowed == cached + live` and
`attempted == allowed + refused`. A local cache hit counts as a call, and
`provider_requests` counts outbound requests separately.

## Safe practice for an experiment

Record the commit and the worktree state before a run. Keep a run's inputs and
its accepted answers in separate files, and score only after the record is
closed.

Prover load is worth controlling when answers matter, though the effect is
smaller than it looks: rerunning the unresolved cases of a four-provider batch
one prover process at a time changed no answer and no prover time
(2026-08-29, 61 cases whose prover call reached 0.5 seconds). Where a case sits
at its time limit, the limit decides it, not the load.

## What is not here

The fixture and harness suites this repository is developed against live in
`tools/`, a local working directory that is not tracked here, as are the
experiment memos cited from the
[mechanism experiments](../mechanisms/README.md) pages. The mechanisms and
their measured results are described in those pages and do not depend on the
harnesses.

## Related documentation

- [Extending the pipeline](extending.md)
- [Command-line reference](../reference/command-line.md)
- [Runtime records](../reference/runtime-records.md)
- [Graph representation](../architecture/graph-representation.md)
