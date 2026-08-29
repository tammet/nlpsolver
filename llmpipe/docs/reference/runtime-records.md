# Runtime records

This page lists the fields a run records. `runtests.py` writes one
JSON file per case and model under `testresults/`.

## Case fields

| field | meaning |
|---|---|
| `input_text`, `expected_answer` | the case as given to the runner |
| `scoring_policy` | the named and versioned answer-matching policy used for `correctness` |
| `stage1`, `stage2` | the two translation outputs |
| `clauses`, `final_clauses` | the canonical clause list, and the list the answering stage submitted |
| `gk_command`, `proof`, `nl_proof` | the answering stage's prover call |
| `front_door_proof`, `front_door_gk_command` | the initial attempt's own call, kept when a later stage answered |
| `answered_by` | the stage that produced the final answer, or `none` |
| `pipeline_name` | the configuration the run resolved to |
| `run_outcome` | one of four outcomes, see below |
| `stages` | one row per stage, in `PIPELINE_ORDER` |
| `llm_accounting`, `llm_accounting_stages` | whole case, and final attempt |
| `gk_calls` | one entry per prover call, with its stage |
| `acceptance` | present only when `-accept` was named |

## Run manifest and summaries

At the top of each result directory, `run_manifest.json` records the test-file
hash, source state, resolved solver options, scoring policy, provider versions,
and each invocation's selected case ids. The runner refuses to add records when
the existing manifest identifies an incompatible test, source state,
configuration, scoring policy, or provider version.

Each provider directory has a `summary.json`. The result directory also has a
combined `summary.json` with one row per provider and case-level counts for all,
some, or no providers answering correctly.

## Stage rows

Each row holds `stage`, `enabled`, `ran`, `answered`, `why`, `answer`,
`error`, `theory_sha256`, `gk_calls`, `gk_seconds`, `llm_calls`,
`llm_seconds`, `llm_allowed`, `llm_cached`, `llm_live`, `llm_refused`,
`llm_provider_requests`, `provider` and `version`.

## Run outcomes

`answered`, `unknown_all_stages_ran`, `unknown_after_stage_failure`, and
`translation_failure`.

## Call accounting

One vocabulary is used for the whole run and for each stage row.

| term | meaning |
|---|---|
| `allowed` | logical calls the limit permitted |
| `cached` | allowed calls answered from the local cache |
| `live` | allowed calls sent to a provider, counted once each |
| `refused` | calls refused before the cache lookup and before dispatch |
| `attempted` | `allowed` + `refused` |
| `provider_requests` | outbound requests, including internal HTTP retries |

Two identities hold: `allowed == cached + live` and
`attempted == allowed + refused`.

`llm_accounting` covers the whole case, including the downstream-error retry.
`llm_accounting_stages` covers the final attempt, which is what the stage rows
describe. They differ when the retry ran more than once.

## Caches

The local SQLite cache in `cache.db` stores model responses. Its key includes
the provider, version, temperature, seed, token limit, system prompt and input,
so no entry is shared between models. `-nollmcache` disables it. A separate
prover cache stores GK results and is off unless `-cache` is given.

## Model identity

One run uses one provider and one version for every call. A call naming
another model raises before the cache lookup.


## Related documentation

- [Pipeline](../architecture/pipeline.md)
- [Configuration](configuration.md)
- [Orchestration code](../code/orchestration.md)
