# Pipeline

The order of stages, when each runs, and what a run records. The default
configuration is `balanced`.

The pipeline translates English into logic, calls the GK prover and returns an
answer. When the prover returns `Unknown`, later stages try again with a
different translation. The first definite answer stops the remaining stages.

## The initial attempt

```text
English text
    │
    ▼
llmparse.parse_text()              [solver/llmparse.py]
    │   Stage 1: English → ASU JSON
    │   Stage 2: ASU JSON → logic JSON
    │   (model responses cached in cache.db)
    │
    ▼
logconvert.rawlogic_convert()      [solver/logconvert.py and the lc_* modules]
    │   logic JSON → GK clause list
    │   FOL → CNF, Skolemisation, defeasible expansion,
    │   context injection, gradable normalisation
    │
    ▼
prover.call_prover()               [solver/prover.py]
    │   writes the clause list to a temporary file
    │   runs the gk binary as a subprocess
    │
    ▼
procproofs.process_proof()         [solver/procproofs.py and the proof_* modules]
    │   reads the prover JSON, selects an answer,
    │   renders the English proof when asked
    │
    ▼
Answer string
```

`english_to_answer(text, options)` in `solve.py` is the entry point for library
use. `main()` in the same file is the command-line entry point.

## Stage order

`solve.PIPELINE_ORDER` is the single declaration of the order. Runtime records
use the identifiers in parentheses:

1. initial translation and proof attempt (`front_door`)
2. normalized compilation (`fallback_norm`)
3. conditional-question handling (`fallback_hyp`)
4. critic-guided retranslation (`critic`)
5. graph retranslation (`graphtrans`)
6. literal-bridge attempt (`litbridge`)
7. graph-bridge attempt (`graphbridge`)

`solve.STAGE_KEYS` is derived from it. Execution, the summary output and the
tests all read those two names, so a stage cannot be added to one and forgotten
in another.

The stages after the initial attempt are described in
[retries](retries.md). Two of them make no model call. The critic and the two
graph stages do.

## Named configurations

`-pipeline NAME` selects retry stages. It does not select an encoding, a
preset, a prompt, a model or a prover option.

| configuration | normalization | conditional question | critic | graph retranslation | graph bridges | literal bridges |
|---|---|---|---|---|---|---|
| `conservative` | on | on | off | off | off | off |
| `balanced` | on | on | on | on | off | off |
| `high-recall` | on | on | on | on | on | off |

`balanced` is the default, adopted 2026-08-27. A command line with no options
resolves to exactly the balanced stage vector and records
`pipeline_name: balanced`. Naming it explicitly changes nothing. The six stage
defaults in `globals.options` are filled from
`globals.PIPELINES[globals.DEFAULT_PIPELINE]`, so there is one source rather
than two sets that could drift.

The ordinary sequence is therefore:

```text
canonical theory, with the two reversible proof-shortening rewrites
  -> gk
  -> normalization fallback
  -> conditional-question fallback
  -> critic retranslation
  -> graph retranslation
  -> Unknown
```

The literal bridge belongs to no named configuration. Add it with `-litbridge`.
An unknown configuration name is an error, not a silent default.
`-stack-closed` resolves to `balanced` and `-stack` to `high-recall`. The
resolution rounds are in [configuration](../reference/configuration.md).

The evidence for the adopted configuration is the two complete Task 2A model runs:
111 correct additions against 8 wrong ones. Those eight remain visible in the
records, because no acceptance policy is enabled. See
[mechanisms](../mechanisms/README.md).

## Separate theories

Each stage is a separate attempt, not an addition to one growing theory. The
critic retranslation, the graph retranslation and each bridge build their own
clause sets. Only a mechanism that already merges deliberately does so.

## Errors and stopping

`None`, empty output, `Unknown`, `no answer` and any `Error:` value leave the
question unresolved. An error is never an answer, and never a correct
abstention.

A stage exception or timeout is recorded on that stage's row. The run then
continues with the next enabled stage. It never aborts the case. An earlier
definite answer is never replaced by a later one.

## What a run records

Every case record holds one row per stage, in the order above. Each row states
whether the stage was enabled, whether it ran, why it did not run, its answer
or error, whether the answer became final, the submitted theory hash, GK and
model-call counts and time, the provider and version, and any acceptance
record.

`run_outcome` separates four cases: a definite answer, `Unknown` after all
enabled stages ran, `Unknown` after a stage failed, and a translation failure
before a valid GK question existed.

Top-level `answer`, `answered_by`, `proof`, `final_clauses` and `gk_command`
always describe the same final attempt. A refused, timed-out or superseded
stage stays visible in its row and never fills them.

`stages_enabled` carries the stage keys the run had on, in stage order, next to
`abstraction_order`. `-summary` prints both. The field list is in
[runtime records](../reference/runtime-records.md).

## Related documentation

- [Retries and retranslation](retries.md)
- [Translation](translation.md)
- [Logic compilation](logic-compilation.md)
- [Reasoning and proofs](reasoning-and-proofs.md)
- [Configuration](../reference/configuration.md)
- [Command-line reference](../reference/command-line.md)
- [Runtime records](../reference/runtime-records.md)
- [Orchestration code](../code/orchestration.md)
