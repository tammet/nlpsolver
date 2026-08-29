# Instructions for working on llmpipe

## Orientation and authoritative references

Run pipeline commands from this directory. Start with `README.md` and
`docs/README.md`.

- `docs/encodings/` is authoritative for Stage 1, Stage 2, compiled GK
  clauses, compact representations, and graph format.
- `docs/reference/command-line.md` is authoritative for public command-line
  options; `docs/reference/configuration.md` describes effective defaults.
- `docs/architecture/` explains processing order and subsystem boundaries.
- `docs/code/` maps source files and prompts to their roles.
- `docs/mechanisms/` records which experimental mechanisms were adopted,
  retained as options, or set aside and why.

If prose and implementation disagree, verify the behavior in production code
and tests, then correct the documentation as part of the same change.

## Pipeline invariants

- The target is extended first-order logic with defeasible formulas, numeric
  confidence, and contradiction-tolerant reasoning; do not describe it merely
  as first-order logic in overview documentation.
- The ordinary configuration is `balanced`. It attempts the initial
  translation and proof, deterministic normalization and conditional-question
  fallbacks, critic retranslation, and graph retranslation, stopping at the
  first definite answer.
- Reversible event compression and repeated part-witness compression are
  attempted on the canonical theory by default. Graph compilation uses its
  own representation and suppresses these rewrites.
- `Unknown.` is a logical outcome, not an execution error. Strings beginning
  with `Error:` must never be treated as answers.
- Keep model identity explicit in comparative experiments: when a run is
  assigned to one model, use that model for Stage 1, Stage 2, and later
  model-based stages unless the experiment explicitly studies mixed models.

## Model calls and evaluation

- Keep the LLM cache enabled. Never pass `-nollmcache` or clear the cache
  unless the user explicitly requests a fresh model response.
- A requested individual `solver/solve.py` query is normal work. Ask before a
  broad or potentially expensive live evaluation, and state the intended
  models, cases, call ceiling, and output location.
- Use `test.py` for small readable checks. Do not run it on more than five
  cases without explicit instruction; name the test file, provider, and a
  `-limit` or `-filter`.
- Use `runtests.py` for research evaluation and structured records. Preserve
  its configuration manifest, per-case provenance, scoring policy, and
  cross-model summary.
- Do not interpret a correct final answer as proof that Stage 1 and Stage 2 are
  faithful. When diagnosing a case, inspect the translations, compiled
  clauses, GK input, proof, and answer processing separately.
- Prefer stored records and cache-served replays for diagnosis. Distinguish a
  behavior change from old-record drift and timing-sensitive prover output.

## Changes and verification

- Keep the canonical English-to-logic route separate from optional and
  experimental representations. Do not silently enable research mechanisms.
- Prompt changes are behavior changes. Store exact prompt text or hashes in a
  measured experiment, and do not revise a frozen prompt after viewing live
  results without declaring a new version.
- Generated lexical modules in `solver/data_*.py` come from `mkdata/`; follow
  `mkdata/AGENTS.md` and `docs/development/generated-data.md` rather than
  editing them by hand.
- After code changes, run the narrowest relevant fixtures, Python compilation,
  and `git diff --check`. Use the larger evaluation runners only when the task
  is about measured model or benchmark behavior.
- `memos/`, `elogs/`, `testresults/`, `debug/`, most of `tools/`, paper
  folders, and `cache.db` are local working material. They may provide
  evidence, but committed documentation must remain understandable without
  them.
