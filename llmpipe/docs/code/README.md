# Code guide

Where each part of the pipeline lives, and which page describes it.

Read these pages when you need to find or change code. They say which module
owns an operation and how the modules fit together; what the operation does is
in [architecture](../architecture/README.md), and the exact logical form it
produces is in the [encoding reference](../encodings/README.md).

One run passes through five subsystems in order. `solve.py` reads the command
line and decides which stages may run. `llmparse.py` makes the two model calls
that turn English into logic. `logconvert.py` and the `lc_*` modules compile
that logic into clauses. `prover.py` runs GK and the `proof_*` modules turn its
answer into text. When the answer is `Unknown.`, the retry modules build a
second attempt and the cycle repeats from wherever that attempt starts.

The table maps each of those subsystems to the page that describes it. Start
with the [source map](source-map.md) instead if you already know which module
you want.

| subsystem | page | what it covers |
|---|---|---|
| orchestration | [orchestration.md](orchestration.md) | entry points, option resolution, stage scheduling, stopping, the per-call deadline, call accounting, GK attribution |
| translation | [translation-and-validation.md](translation-and-validation.md) | provider calls, the response cache, Stage 1 and Stage 2, sanity checks, corrective retries |
| compilation | [logic-compilation.md](logic-compilation.md) | the compiler modules and the order of the passes |
| proofs | [proof-processing.md](proof-processing.md) | the GK call, answer selection, proof extraction, source tracing, English rendering |
| retries | [retries-and-abstraction.md](retries-and-abstraction.md) | the two fallbacks, the critic, the graph stages, the two bridge mechanisms, the acceptance checks |
| prompts | [prompt-map.md](prompt-map.md) | every prompt file and the loader that reads it |
| every module | [source-map.md](source-map.md) | one line per tracked module, with its owning page |

## What runs where

`solve.py` owns the run. It resolves the options, performs the initial
translation and proof attempt, and then walks the retry stages while the
question is unresolved.

The initial attempt uses `llmparse.parse_text` for the two model calls,
`logconvert.rawlogic_convert` for logic compilation, `prover.call_prover` for
the GK call, and `procproofs.process_proof` for the result.

Each retry stage builds its own clause set and makes its own GK call. None of
them adds clauses to the canonical theory.

## What is not shipped

`tools/` holds test fixtures, experiment harnesses and the documentation
checkers. `mkdata/` holds the generators for the five `data_*.py` modules.
Neither is part of the pipeline a user runs.

## Related documentation

- [Architecture](../architecture/README.md)
- [Encoding reference](../encodings/README.md)
- [Extending](../development/extending.md)
- [Testing](../development/testing.md)
- [Generated data](../development/generated-data.md)
