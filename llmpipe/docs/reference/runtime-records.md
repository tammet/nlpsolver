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
| `gk_command`, `proof`, `nl_proof` | the answering stage's prover call; on the action route `nl_proof` is the route's explanation (sentences, laws, plan steps, replay) |
| `front_door_proof`, `front_door_gk_command` | the initial attempt's own call, kept when a later stage answered |
| `answered_by` | the stage that produced the final answer, or `none` |
| `pipeline_name` | the configuration the run resolved to |
| `route_choice` | which pipeline answered: `mode` (`auto`, `actions` or `noactions`), `route` (`actions` or `ordinary`), and in mode `auto` the classifier's `verdict` and `signals` |
| `action_route` | the action route's record: translation, source, query and result (below) |
| `grade`, `answer_check` | on a planning test file: the planning checker's grade and its detail, with the mode |
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

## The action route

A case that took the action route keeps the route's record under
`action_route`:

| field | content |
|---|---|
| `route`, `input` | `actions`, and `text` or `formal` |
| `profile` | the resolved options of the route: the prompt bundle, the backend, the plan depth and limits, the seconds per launch, `formal`, `nosolve`, and the ordinary stages it disables |
| `translation` | the translation record without its source artifact: the status, the accepted Stage 1 and Stage 2, every request with its errors and normalizations ([action translation](../architecture/action-translation.md#the-translation-record)) |
| `source` | the hashes and the support of the source artifact |
| `query` | the id, kind, hash and decided outcome of the query (the last query of a formal record with several) |
| `result` | the result record ([action artifacts](../encodings/action-artifacts.md#result-record)); `{"outcome": "not_solved"}` under `-nosolve`; `{"outcome": "several", "results", "failed"}` for a formal record with several queries |
| `error` | a failure of the route itself: options, or an exception |
| `calls` | the model calls (`logical`, `cached`, `live`, `provider_attempts`, `refused`, `timeouts`) and the GK launches (`gk`) |

On this route, `answered_by` is `actions` when the route answered,
`stages_enabled` marks every ordinary stage as not enabled, the case file has
no `stages` rows, and `run_outcome` is the result's outcome (`plan_found`,
`verification_result`, `several`, ...), or `error` for a failed run or a text
that the route does not model. `nl_proof` holds the
explanation that `-explain` prints. Each GK launch is one entry of `gk_calls`,
with the stage `actions` and its role.

On a planning test file, the runner grades each answer with
`planning_check.grade_row` and adds `grade` (`match`, `not_answered`,
`no_answer`, `mismatch` or `error`) and `answer_check`. The provider's
`summary.json` then has a `planning` block: the mode and the counts of
answers correct, rows correctly not answered, wrong rows and errors.

## Call accounting

One vocabulary is used for the whole run and for each stage row.

| term | meaning |
|---|---|
| `allowed` | logical calls the limit permitted |
| `cached` | allowed calls answered from the local cache |
| `live` | allowed calls sent to a provider, counted once each |
| `refused` | calls refused before the cache lookup and before dispatch |
| `attempted` | `allowed` + `refused` |
| `provider_requests` | outbound requests, including internal HTTP retries and Gemini context-cache creations |

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
