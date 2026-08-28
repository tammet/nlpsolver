# Testing

This page describes the test suites and how to run them safely.

## Running a suite

Test scripts live in `tools/` and run directly:

```bash
PYTHONHASHSEED=0 python3 tools/test_davidson2.py
```

`PYTHONHASHSEED=0` matters. Conversion output depends on the hash seed.

## Kinds of suite

| kind | example | what it needs |
|---|---|---|
| unit and fixture | `test_davidson2.py`, `test_existfold2.py` | nothing external |
| option resolution | `test_pipeline_options.py`, `test_stack_flags.py` | nothing external |
| stage orchestration | `test_pipeline_stages.py` | nothing external |
| call accounting and limits | `test_llm_accounting.py`, `test_llm_call_limit.py` | a fake provider |
| prover interoperation | `test_proofshort2_interop.py` | the `gk` binary |
| graph and critic | `test_graph_*.py`, `test_critic_*.py` | stored fixtures |

## Dataset runners

`runtests.py` runs a test file over one or more models and writes one JSON per
case and model under `testresults/`. `test.py` runs a smaller check.
`examine.py` writes per-model debug logs for one case.

## Caches

The local response cache is on by default. A repeated run answers from it and
makes no provider request. Do not disable it to force fresh calls unless that
is the point of the run: the cache is the reason repeated runs are cheap and
reproducible.

## Call accounting in tests

A test that counts calls should read `llmcall.call_counts()` and the stage
rows. The two identities `allowed == cached + live` and
`attempted == allowed + refused` hold in both.

## The graph study harness

`tools/run_graph_bridge.py` freezes, translates, runs and closes a phase;
`tools/graph_cases.py` derives the case sets from the stored four-model literal-bridge
artifact; `tools/score_graph_bridge.py` reads the accepted answers only after a record is
closed and hashed, and puts the graph route beside the stored literal-bridge outcome;
`tools/report_graph_bridge.py` writes per-case side-by-side reports.  Each solver
module has a focused fixture file, `tools/test_graph_*.py`, and
`tools/graph_fixtures.py` holds the synthetic material they run on.

The design, the implementation plan and the pilot results were written up in
local memos that this repository does not track. The mechanism itself is
described in [graph representation](../architecture/graph-representation.md)
and its evidence in [mechanism experiments](../mechanisms/README.md); neither
depends on those files.

## Safe practice for experiments

Record the commit and the worktree state before a run. Keep a run's inputs and
its accepted answers in separate files. Run one prover-heavy worker at a time
where answers matter: concurrent prover load has changed a recorded answer.


## Related documentation

- [Extending the pipeline](extending.md)
- [Command-line reference](../reference/command-line.md)
- [Graph representation](../architecture/graph-representation.md)
- [Runtime records](../reference/runtime-records.md)
