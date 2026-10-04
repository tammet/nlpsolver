# Action artifacts and records

The action route keeps its intermediate results in JSON records. The compiler
writes a source artifact for the text and a query artifact for each question.
The GK adapter writes an evidence record, and the answer policy writes a result
record. This page defines their fields and the diagnostics that they hold. The
[runtime records](../reference/runtime-records.md#the-action-route) say which
of them a case file keeps.

All four records are plain JSON objects with the fields `artifact` and
`version`. The source, query and result records have the version string `"2"`
(`action_route.ARTIFACT_VERSION`); the evidence record has `"1"`
(`action_gk.EVIDENCE_VERSION`). `action_route.check_artifact` rejects a source
or query artifact with another version.

## Operations

| function | result | model or GK calls |
|---|---|---|
| `action_route.compile_source(stage1, stage2_source, profile, source_text, entities, provenance, worlds, contexts, types, type_notes)` | a source artifact | none |
| `action_route.compile_query(query_logic, source_artifact, limits, backend, planning_root, ambient, knower)` | a query artifact | none |
| `action_route.query_input(source_artifact, query_artifact, obligation, polarity)` | the GK clause objects of one question | none |
| `action_gk.run_query(source, query, backend, limits, ledger)` | an evidence record | GK |
| `action_answer.decide(source, query, evidence)` | a result record | none |
| `action_answer.solve(source, query, backend, limits, ledger)` | `run_query`, then `decide` | GK |
| `action_route.translate_source(source_text, profile, model_options)`, `action_route.solve_query(source, query, options)` | the same operations as a library interface for the checks | as above |

`compile_query` checks the source artifact against its hashes before it uses
it. `query_input` rebuilds the view and checks it against the recorded view
hash. A query artifact belongs to one revision of its source artifact: after a
later pass or a new diagnostic, the query must be compiled again.

## Source artifact

`artifact: "action_source"`.

| field | content |
|---|---|
| `profile` | `{name, policy: {stored, computed}, locations: {flat}}`; the name is `physical_v1` |
| `library` | the [library identity](action-library.md#files), status `selected` |
| `worlds` | the declared worlds in narrative order; `["W0"]` when the caller gives none |
| `source_text` | the text, as given |
| `identity` | entity id → `{type, class?, category?}`: the caller's entity map, with the Stage-1 concrete entities and their categories added, or the concrete ids of a formal source. A query never extends it |
| `units` | one record per source unit (below) |
| `restriction_clauses` | the hook clause of every restricted constructor, role `hook` |
| `restrictions` | per restricted constructor: its units, checks and hook, and the units that withheld a hook; one row per `poss` path of the constructor |
| `policy_clauses` | the `derived_property(V)` facts, role `derived_no_inertia`, with the policy `computed` or `computed_declared` |
| `identity_clauses` | the `differ` facts, role `distinct` |
| `types`, `type_clauses` | the type records `{entity, class, kind, unit, units?}` and one `isa` clause per record, role `static_type`. Kinds: `stated` (the Stage-2 field `types`), `stage1_person` (the person convention), `lexical_identification` (the class noun of a past or future description) |
| `diagnostics` | the diagnostics of the whole source (`unit_coverage`, `duplicate_unit`, `context_unit`, and notes such as a suppressed person type) |
| `support` | `status` (`supported`, `unsupported`, `invalid`), `reasons`, `errors`, `units`, `unsupported_units`, `invalid_units` |
| `provenance` | the caller's provenance record: `{"kind": "formal_input"}` for `-formal`; the default `{"kind": "supplied_translation", "model": null, "prompt": null}` otherwise, also for an English translation |
| `clauses` | the clause records of a source with no unsupported or invalid unit; else `null` |
| `dependencies` | the reads and writes of every law unit, the text writes, the dynamic negative reads, the transport inventory and the stored and computed property table; `null` under the ordinary profile |
| `backend_requirements` | the potential requirements: `negative_persistence` (the units with a dynamic negative read) and `shared_source_confidence` (the uncertain permissions). Each query decides which it needs |
| `passes`, `pending_passes` | the source passes that ran and those that did not |
| `hashes` | `source` (profile, library, text, identity, worlds, units with their context records, given type records), `formulas`, `identity`, `artifact` (everything but `hashes`) |

A unit record:

| field | content |
|---|---|
| `id`, `text`, `stage1`, `stage2` | as given |
| `form` | `description_static`, `description_initial`, `state_law`, `availability`, `denial`, `restriction`, `effect` or `ordinary_event`, read from the formula |
| `confidence` | the `@p` value |
| `action_terms`, `roots` | the action terms of the formula and the Stage-1 verb roots |
| `status` | `supported`, `unsupported` or `invalid` |
| `diagnostics` | the unit's diagnostics |
| `world`, `context` | the world of its `holds`, and its context record or `null` |
| `situated` | the formula with situation terms, for inspection |
| `situation` | `named`, `shared_current`, `successor` (an effect) or `none`; `null` for a unit that the passes did not reach |
| `clauses` | the unit's clause records, written by the pass of its form; `[]` for a unit that a pass refused (a mixed-scope rule, a probability of 0.5 or less, a granularity or state-policy finding); `null` for an unsupported or invalid unit and under the ordinary profile |
| `witnesses` | the Skolem witnesses of the unit |
| `compile_note`, `requirements` | notes of the passes, and the backend capabilities that the unit's clauses need |

A clause record is `{role, unit, clause, pass}`, plus `source_probability` and
`confidence` for an uncertain unit, `defeasible` for a default, and the fields
of its pass (`template` for a permission path, `constructor`, `check` and
`branch` for a restriction, `action` and `conditional` for an effect).

Every unit stays in the artifact. An unsupported unit keeps its formula and
its diagnostic.

## Query artifact

`artifact: "action_query"`.

| field | content |
|---|---|
| `source` | the `source_hash` and `artifact_hash` of the source artifact |
| `query` | `id`, the package as given, `kind` (`plan`, `reachable`, `verify`, `question`, `ask`), `goal`, `steps`, `sequence`, `variable`, `witnesses` |
| `planning_root` | a declared world: the given one, else the last declared world |
| `ambient`, `knower` | the entity ids given, else `null` |
| `excluded` | `[{unit, reason}]`: the fact units that the views leave out (below) |
| `families` | the selected ordinary families: `["V1-core"]` |
| `limits` | `{search_cap, explicit}`; the default cap is 4 |
| `backend` | `{validated: [...]}`, the capabilities that the caller declares |
| `view` | `snapshot`, `verify` or `discovery` |
| `search` | `depth`, `seed`, `require_zero_remaining`, `covers_bound`, `insufficient` |
| `diagnostics` | the query's validation diagnostics |
| `outcome` | `null`, or `{outcome, ...}` with an outcome that compilation decided (`translation_invalid`, `unsupported_translation`, `insufficient_search_allowance`, `unsupported_backend_requirement`) and its errors, reasons, units or detail |
| `backend_requirements` | the capabilities this query needs: `{capability, units, detail, evidence}`, and `polarities` when only one polarity needs it |
| `selected_clauses` | the clause names of the view, in input order: `{view, source, library, ordinary}` |
| `view_hash` | the hash of the selected clauses after the root binding, the knower substitution and the exclusions |
| `obligations` | the prover questions (below) |
| `seed` | the reachability seed of a discovery, else `null` |
| `joint_positive` | the joint question of a verify query with steps |
| `obligations_hash`, `hash` | the hash of the obligations, seed and joint question; the hash of the artifact |
| `passes`, `pending_passes` | `query_views` in one of the two |

An exclusion reason is one of:

- `underspecified_temporal_root`: the fact has the tense past or future;
- `scope_location_mismatch`: the fact has a scope location other than the
  query's ambient location;
- `knower_mismatch`: the fact has a knower other than the query's.

An objective fact stays in a query with a knower.

An obligation has `id`, `role` (`snapshot`, `step`, `final`, `discovery`),
`formula`, `text`, `situation`, and the questions `positive` and `negative`.
A question is `{form, clauses, question}` with the form `literal` or
`definition` ([query clauses](action-clauses.md#query-clauses)). A verify
obligation has `requires_prefix`: the number of steps that must be
established and validated before its negative answer may give No. It is
`i - 1` for step i, and the sequence length for the final formula.

## Diagnostics

A diagnostic is `{level, code or reason, unit, path, subformula, message}`,
with `detail` where a reason has named cases. `path` is the index path into
the package.

- `level: invalid` gives the outcome `translation_invalid`.
- `level: unsupported` gives `unsupported_translation` with a reason.
- `level: note` records a decision, such as a suppressed person type
  (`conflicting_category`, `stated_not_person`) or an adjusted reading
  (`reading_adjusted`).

### Validation codes

The table lists the codes of the action encoding; the structural checks of
`lc_action` and `action_route` have more, such as `duplicate_unit`,
`unit_coverage` and `sequence_not_ground`.

| code | what it marks |
|---|---|
| `undeclared_world` | `holds(W, F)` with W outside `worlds` |
| `reserved_variable` | a source or asked variable called like a world |
| `can_in_query` | `can` in any query: a question, an ask, or a plan, reachable or verify goal |
| `context_record_position` | a context record on a unit that is not an initial description |
| `undeclared_context_location`, `undeclared_context_knower` | a context record that names no entity |
| `context_unit` | a context record for no unit |
| `unknown_planning_root`, `unknown_ambient`, `unknown_knower` | a query selection that names no declared world or no entity |
| `reading_form_mismatch` | a Stage-1 reading that does not fit the unit's form |
| `stage1_projection` | a malformed Stage-1 projection of a unit |

### Unsupported reasons

The route reports these forms and does not approximate them
(`lc_action.REASONS`):

| reason | what the text has |
|---|---|
| `occurrence` | an action that happened, as a narrative event |
| `unsupported_action_kind` | an operation outside the five constructors: a creation, a consumption, a transfer |
| `unsupported_capability_restriction` | `can` in the condition of a restriction |
| `unsupported_restriction_scope` | a restriction outside the restriction form: a state guard, a guard that is not a literal, a variable outside the pattern, a repeated variable in a word slot, an equality on a slot |
| `unexpressible_temporal_permission_scope` | a permission valid for a stated time ("until noon") |
| `defeasible_text_effect` | an effect under `normally`, or with a probability below 1 |
| `existential_availability_head`, `existential_state_law_head`, `existential_effect_head` | an existential in the head of a permission, a standing law or an effect |
| `unsupported_relation_policy` | a relation that the profile does not store |
| `method_collision` | two units whose action terms unify but whose verbs differ |
| `unsupported_goal_form`, `unsupported_law_form` | a goal or a law outside the [supported fragment](action-clauses.md#the-supported-fragment) |
| `unsupported_executability_assertion` | a fact or a sufficient rule that asserts `executable` |
| `unsupported_contextual_location` | a context location without a role |
| `mixed_scope_rule` | a dynamic condition with a static conclusion |
| `unsupported_default_form` | a default that is negated, disjunctive, nested, or one of two in a clause |
| `ambiguous_state_scope` | a state rule whose scope the translation leaves open |
| `unsupported_location_granularity` | a place inside a place, or one entity at two places of one world outside the declared flat set |
| `unsupported_confidence_form` | a unit with p ≤ 0.5, an uncertain unit with several `can` heads, an uncertain restriction or effect |
| `ambiguous_state_policy` | a property value that is both stored and computed, with no declared policy |
| `unsupported_stored_state_law` | a standing law whose head is `is rel2`, `have`, `clear_top` or `empty` |
| `unsupported_transport_dependency` | a question that reads the location of an object after its holder moved |

Two further reasons come from the query and the backend:
`insufficient_search_allowance` (an explicit search cap below an exact step bound or below the length of a supplied sequence)
and `negative_persistence_unavailable` (a query that needs a negative fact
kept across an action).

## Evidence record

`action_gk.run_query` writes `artifact: "action_evidence"`.

| field | content |
|---|---|
| `source`, `query` | the source and query hashes, the query kind, view hash, obligations hash and planning root |
| `backend` | name, path, SHA-256, strategy and its hash, parameters, the library identity |
| `requirements` | each requirement with `validated`, `reason`, `policy` and units |
| `outcome` | an outcome that stopped the query before a launch, or at a launch (`backend_incompatible`, `backend_unavailable` with `launch_failed`), or `null` |
| `planned`, `limits` | the launch count and its worst case; the limits used |
| `obligations` | per obligation: id, role, text, step, `requires_prefix`, and the positive and negative launch records |
| `joint` | the launch record of the joint question |
| `incomplete` | the launches that did not complete, with their status and error |
| `calls` | the GK launches in total and by role, and their time |

A launch record holds the command (the input path as `<input>`), the input's
SHA-256 and clause count, the elapsed time, the exit status, the output, the
status, the result string, the accepted and rejected entries, the candidates
and the termination reason. [Proof search](../architecture/action-answers.md#proof-search)
defines the status, the eligibility of an entry and the candidates.

## Result record

`action_answer.decide` writes `artifact: "action_result"`.

| field | content |
|---|---|
| `outcome` | one of the outcomes below |
| `operation`, `query`, `source` | `solve_query`; the query's id, kind, hash and planning root; the source hashes |
| `answer` | `Yes`, `No`, `Unknown`, `contested`, `none`, an entity term, or `null` |
| `plan`, `witnesses` | the validated plan as action terms, and the witnesses of the goal |
| `confidence`, `confidence_status`, `experimental_reasons` | the GK confidence of the answer used, `validated` or `experimental`, and the reasons for `experimental` |
| `confidence_parts` | `frame_uses`, `frame_product`, `other_uncertain_uses`, `other_product`: the frame part and the stated part of the confidence |
| `proof` | the raw answer, clause names and proof steps of the entry used |
| `verdicts`, `candidates` | the verdict of each obligation; the candidates of a discovery with the replay's verdict on each, or the answers of an ask |
| `failing_step` | the first step of a supplied sequence that is not Yes |
| `replay`, `validation` | a summary of the replay, and the name of a disagreement between the replay and GK (`replay_disagrees`, `replay_not_checked`, `prefix_not_validated`) |
| `render`, `plan_steps`, `plan_named`, `plan_verbs` | the English plan, one sentence per step, the plan terms with names, and the source verb of each `change` step (`null` for the other steps) |
| `answers`, `answer_names` | all answers of an ask, and their names |
| `conflicts`, `facts`, `facts_english`, `step` | the conflicts of an inconsistent state, its facts and their English, and the step after which it arose |
| `evidence` | the backend identity of the launches, the requirements, the incomplete launches, and a summary of each launch |
| `diagnostics` | further findings. An outcome that the route passes through from compilation or from the adapter keeps its record (reasons, units, detail) here as the first diagnostic |
| `calls` | `{model, gk, gk_by_role}` |

The outcomes:

| outcome | meaning |
|---|---|
| `verification_result` | a question, an ask or a verify query answered |
| `plan_found` | a plan was found and validated by the replay |
| `goal_already_holds` | the goal holds at the planning root: the empty plan |
| `not_found` | no candidate plan within the search |
| `candidate_not_validated` | the replay validated none of GK's candidate plans |
| `inconsistent_action_state` | the starting state, or a state after a supplied step, has conflicting facts |
| `unsupported_translation`, `unsupported_backend_requirement` | the route does not model the text or the question |
| `translation_invalid` | no valid translation within the correction budget, an invalid formal record, or an invalid query selection |
| `insufficient_search_allowance` | an explicit search cap below the exact step bound or below the length of the supplied sequence |
| `source_compiled` | a text without a question was compiled |
| `call_limit`, `model_timeout`, `model_error` | a model call failed or was refused; `call_limit` also when the worst-case GK launch count exceeds the launch limit |
| `prover_timeout`, `prover_error`, `backend_unavailable`, `backend_incompatible` | a GK launch failed, or the registered build is missing or did not run its strategy |

`not_implemented` is no outcome of the route. It marks a missing prompt bundle,
or a query without obligations.

A result for a text that the route does not model has `reasons`, `units` and
`diagnostics` at its top level, from the translation record.

A result never claims more than its evidence. A query artifact that holds a
solved result raises `ArtifactError`, with or without a correct hash.

## Hashes

The artifact hashes use `digests.canonical(obj)`: JSON with sorted keys, the
separators `,` and `:`, no ASCII escaping, in UTF-8. `digests.digest` is the
SHA-256 of that text. The order of a dictionary never changes such a hash.
The order of a list does. Two hashes of the adapter differ: a launch's
`input_sha256` is the SHA-256 of the input file as GK reads it, and the
strategy hash reads ASCII-escaped JSON.

## Related pages

- [Action clauses](action-clauses.md) — the clauses that the artifacts hold
- [Action compilation](../architecture/action-compilation.md) — the passes that fill the source and query artifacts
- [Proof search and answers](../architecture/action-answers.md) — the adapter, the answer policy and the replay
- [Runtime records](../reference/runtime-records.md) — what a case file keeps
