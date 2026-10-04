# Action route modules

Which module does each step of the [action route](../architecture/action-route.md),
and where to change what.

## Entry and routing

`solve.english_to_answer` calls `solve.route_choice` first. With `-actions`
or `-noactions` the key decides, and `-formal` alone selects the action route.
Otherwise `route_classify.classify` reads the text with no model call and
returns a verdict (`actions`, `ordinary`, `unclear`) with its signals. The action route starts at
`action_pipeline.run`; every other verdict takes the ordinary pipeline.

| module | role | main functions |
|---|---|---|
| `route_classify` | the text classifier: the strong and weak signs of actions or plans | `classify` |
| `action_pipeline` | the route for one call: options, prompt bundle, translation controller, formal input, the run record | `run`, `resolve`, `load_bundle`, `translate`, `stage2_attempt`, `compile_translation`, `solve_one_query` |

`action_pipeline.resolve` checks the options. An ordinary stage switch, a
`-pipeline` preset, or a prover option such as `-axioms` with `-actions` is an
error. The route sets only the model-call keys in `globals.options`, for the
length of the call (`action_pipeline.call_settings`), and then restores them.

## The steps

| step | module | main functions | what it does |
|---|---|---|---|
| prompts | `action_prompt` | `assemble`, `render_examples` | the two system prompts and their hashes |
| translation checks | `action_prompt` | `validate_units`, `select_route`, `handoff_errors`, `derive_envelope`, `derived_fields`, `derived_probabilities`, `typing_cleanups`, `at_place_cleanup`, `class_condition_findings` | the Stage-1 annotation checks, the route selection, the handoff check, the normalizations of a Stage-2 response |
| repairs | `action_repair` | `repair_packages`, `id_findings`, `merge_units`, `value_mismatches`, `adjusted_reading`, `clarification_refusals` | the recorded repairs K5 to K9, K13, K15 and K16, and the reading adjustments K1, K2 and K11 |
| JSON reading | `action_json` | `parse_response`, `repair_packages` | the fence, the three bracket repairs, the misplaced `@p` (K10) |
| source compilation | `action_route` | `compile_source`, `add_diagnostic`, `source_outcome` | the source artifact through the passes below |
| structure | `lc_action` | `validate_source_unit`, `validate_query`, `law_shape`, `method_collisions` | the form of each unit, the supported fragment; formula helpers (`conjuncts`, `contains`, `mentions`) that the other modules share |
| situations | `lc_action_situate` | `compile_unit`, `situate_in`, `skolemize`, `clausify`, `mixed_scope` | situations, Skolem witnesses, the clauses of state units, the context terms |
| library | `lc_action_library` | `load`, `load_templates`, `select`, `identity` | `axioms_action.js`, its roles and templates, the library clauses of a view |
| permissions | `lc_action_avail` | `compile_unit`, `instantiate`, `differ_clauses`, `location_granularity`, `query_granularity` | permission paths, denial markers, `differ` facts, location granularity |
| restrictions | `lc_action_restrict` | `compile_unit`, `hooks` | restriction checks, hooks and necessity clauses |
| effects | `lc_action_effects` | `compile_unit`, `state_policy`, `dependencies`, `query_transport` | effects and markers, the state policy, the dependency record, transport |
| query compilation | `action_route`, `lc_action_query` | `compile_query`, `query_input`; `selection_of`, `exclusions`, `backend_requirements`, `selected_view`, `obligations` | the selection, the exclusions, the views, the obligations, the backend requirements |
| proof search | `action_gk` | `run_query`, `extract`, `planned_launches`, `check_prerequisites`, `recording` | one GK launch per question; the typed evidence |
| decision | `action_answer` | `solve`, `decide`, `paired`, `confidence_parts` | the answer policy over the evidence |
| replay | `action_replay` | `replay`, `verification`, `evaluate` | the independent check of a plan or a supplied sequence |
| answer text | `action_english` | `answer_text`, `render`, `plan_steps`, `plan_named`, `answered` | the answer forms, the English of plans and facts |
| output | `action_display` | `show`, `explanation`, `summary_record`, `write_gkin`, `raw_result` | what `solve.py` prints at each output level |
| hashes | `digests` | `canonical`, `digest`, `sha256_text`, `sha256_file` | the canonical JSON and SHA-256 of the artifacts |

`action_route.translate_source` and `action_route.solve_query` are the same
operations as a library interface; the checks use them.

## Data files

| file | content | read by |
|---|---|---|
| `axioms_action.js` | the action library, version 2.0.1 | `lc_action_library`, then GK |
| `axioms_action.roles.json` | the role of each library clause and the library's hash | `lc_action_library.load` |
| `axioms_action.templates.json` | the applicability templates | `lc_action_library.load_templates` |
| `prompts/actions/` | the action instructions and checklists and the examples they show; `manifest.json` records their hashes and those of the assembled prompts | `action_prompt.assemble`, with the ordinary prompt files |

## Constants that change behaviour

| constant | value | meaning |
|---|---|---|
| `action_pipeline.MAX_CORRECTIONS` | 2 | corrections per stage |
| `action_pipeline.MAX_LOGICAL_CALLS` | 6 | logical model calls per translation |
| `action_pipeline.SEMANTIC_CORRECTIONS` | 1 | the extra call about invented class conditions |
| `action_pipeline.MAX_MESSAGES` | 12 | messages in one correction request |
| `action_route.DEFAULT_SEARCH_CAP` | 4 | the default depth of a plan search (`-plan-depth`) |
| `action_gk.DEFAULT_SECONDS` | 30 | seconds per GK launch (`-seconds`) |
| `action_gk.EXTRA` | 15 | the external margin over `-seconds` |
| `action_gk.CUTOFF` | 0.10 | the smallest confidence of a candidate |
| `action_gk.PLANNING_STRATEGY` | query focus | the GK strategy of the registered build |
| `action_gk.BACKENDS` | `gk` | the registered GK builds |
| `action_english.PROBABLY` | 0.95 | below this stated confidence the answer says "Probably" |

## Where to change what

- **A new reading or Stage-1 field:** `action_prompt.validate_units`, the
  handoff check, the prompts in `prompts/actions/`, and the
  [action prompt interface](../encodings/action-prompts.md).
- **A new repair of the controller:** `action_repair` or `action_prompt`, with
  a record kind and a row in the repair table of the prompt interface.
- **A new physical law:** `axioms_action.js` with a new version, the role
  index and its hash, and the replay's transitions in `action_replay`, which
  must agree with the library.
- **A new unsupported form:** a reason in `lc_action.REASONS`, the pass that
  detects it, and a sentence in `action_english.REASON_SENTENCES`.
- **A new answer form:** `action_english.answer_text`, and the answer table of
  the [experimental options](../reference/experimental-options.md#the-action-route).

## The planning checker

`planning_check` grades an answer of a planning test file by its text, its
action list or both (`runtests.py -answer-check`). Its docstring lists the
comparison rules.

## Related pages

- [The action route](../architecture/action-route.md) and its pages — what each step does
- [Action clauses](../encodings/action-clauses.md), [action library](../encodings/action-library.md),
  [action artifacts](../encodings/action-artifacts.md) — the formats
- [Source map](source-map.md) — one line per module
