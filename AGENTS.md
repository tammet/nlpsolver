# Repository instructions for Codex

## Repository scope

`nlpsolver` contains two natural-language reasoning pipelines and their shared
GK theorem prover:

- `llmpipe/` is the current LLM-based pipeline and the main development area.
- `udppipe/` is the older Stanza/UD-based pipeline with its own setup.
- `gk/` contains the bundled reasoning backend and data files. GK is developed
  separately in the `gkreasoner` repository.

Read the README in the relevant directory before changing that subsystem.
More specific `AGENTS.md` files below this one add instructions for their
directories.

## Working practices

- Preserve unrelated user changes and local research artifacts.
- Make the smallest change that satisfies the request. Do not alter another
  pipeline merely to keep its implementation visually similar.
- Do not make live model requests, run broad benchmark batches, bypass a model
  cache, or incur external cost unless the task calls for it. Small local and
  cache-served checks are appropriate when relevant.
- Treat API-key files and cache contents as private. Never print, commit, or
  copy their contents.
- Update the relevant tracked documentation when public commands, logical
  representations, defaults, or output formats change.
- Run focused checks for changed code before broader tests. The root
  `smoketest.py` performs local installation checks without an LLM request.
- Commit or push only when the user explicitly requests it. Stage named paths,
  not the entire working tree, when unrelated files may be present.

## Data and generated files

- Preserve third-party attribution and licence files when changing benchmark
  data.
- Do not edit generated files without also identifying and updating their
  authoritative source or generator.
- Large models, API keys, caches, experiment results, and local research notes
  are intentionally untracked; do not add them to commits.
