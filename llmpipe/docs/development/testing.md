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

Both runners validate the requested provider names and non-empty key files
before doing work. `test.py` does not reuse an execution error as a completed
case and exits nonzero when a selected test fails. `runtests.py` treats a
provider or credential problem as a command error rather than recording it as
many failed benchmark cases.

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

## The action route

The experimental action route has its own offline checks:

```bash
python3 tests/action_route/run_checks.py            # every check
python3 tests/action_route/run_checks.py -k prompts # the checks whose file name contains "prompts"
python3 tests/action_route/make_planning_tests.py --check
python3 tests/action_route/make_examples.py --check
```

The checks make no provider request: a provider request fails
(`tests/action_route/cache_guard.py`). The runner counts the GK launches;
the current checks make none. They test the controller with authored and saved model responses,
the compiler and the replay against the gold fixtures, the adapter on saved
GK outputs, and the answer policy with a fake prover.

**The test material:**

| path | content |
|---|---|
| `tests/action_route/fixtures/` | the reviewed gold fixtures: formal sources and queries with their expected outcomes, and the review ledger that records every gold change |
| `prompts/actions/examples.json`, `routing_cases.json` | the authored examples that the prompts show |
| `tests/action_route/unseen/` | the authored examples and routing contrasts that no prompt shows, in the same format |
| `tests/action_route/examples/` | formal records for `solve.py -actions -formal`, written from the fixtures by `make_examples.py` |
| `tests/action_route/regression/` | saved model responses of earlier runs, which the controller checks replay |
| `tests/action_route/gk_output/` | saved GK outputs, which the adapter check reads |

`tests/action_route/prompt_examples.py` compiles every authored example in
both locations through the real controller, with the record's own Stage 1
and Stage 2 as the model responses. It also checks that the four example files
are in the layout of `json_layout.py` and that `prompts/actions/manifest.json`
is current. After an edit of an example file, run
`python3 tests/action_route/json_layout.py`, then write the manifest again
(`prompts/actions/README.md`).

**The planning test set.** Four files hold English problems about actions and
plans, from simple to complex:

| file | rows | use |
|---|---|---|
| `tests/tests_planning_basic.py` | `[id, text, expected answer, expected actions]` | the test that `runtests.py` grades with `solver/planning_check.py` |
| `tests/tests_planning.py` | `[id, text, expected answer, reference]` with the gold translation | the detailed file, graded by `solver/action_check.py` with a replay of other plans |
| `tests/tests_planning_dev.py` | the texts that are prompt examples | development only, never a headline number |
| `tests/tests_planning_contrasts.py` | the contrast texts of the current prompt revision | development material |

`tests/action_route/make_planning_tests.py` generates the four files. Edit the
golds through the ledger, never the files by hand.
`tests/tests_planning_README.md` describes the expected-answer forms and the
grading rules.

```bash
python3 runtests.py tests/tests_planning_basic.py -actions -llms gemini -limit 5
python3 runtests.py tests/tests_planning_basic.py -actions -answer-check both -llms gemini -limit 5
```

With `-actions` every text goes to the action route, which measures the route
itself. Without it, the classifier routes each text, which measures the
routing too. A larger batch uses `-run-ceiling` with `-sequential` and
`-llm-call-limit` ([command-line reference](../reference/command-line.md)),
so it stops before it passes its ceiling of logical calls and outbound
requests.

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
