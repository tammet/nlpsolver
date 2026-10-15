# Planning summary

`-planning-summary` adds a planning summary to a plan answer of the action
route. This page describes the three formats: the profile that the compiler
writes, the answer that the summary build of GK prints, and the annotation in
the result record.

A summary of an action sequence has two parts.

- **World**: a sorted list of positive facts of selected families. A fact
  that is absent is not stated to be false.
- **Progress**: one integer. A larger value is better; 0 means that the score
  counts nothing as missing.

Both describe the sequence on the condition that it is executable. A summary
is no proof of executability and no proof that a state is reached. GK's
acceptance of an answer and the replay's verdict stay separate statements.

## During the proof search

The summaries exist while GK searches, not only in the final answer.

- GK loads the profile at the start of the run. It keeps one prefix tree for
  the run: one record per distinct ground action prefix of the planning root.
- A read-only hook inspects each clause that the search builds, after the
  clause is built and before GK weighs or queues it. The initial clauses are
  inspected too. The hook reads the literals at the registered situation
  positions (the `situation_positions` of the profile).
- For each ground rooted situation term, the hook looks the term up in the
  tree. A known prefix returns its record. A new prefix is calculated once,
  from the record of its parent. A term that is not ground gives the record
  of its longest ground rooted prefix and a reason.
- Each observation keeps the sign of the literal, its role, whether the
  clause is a unit, and the number of `$block` literals in the clause. The
  inspection of one clause is `complete`, `truncated` (more than 256
  positions) or `error` (the profile context failed); a truncated or failed
  result never stands for all situations of the clause.

A sign or a role is no executability statement. A positive `reachable`
literal in a clause whose other literals are `$block` literals is reachable
under outstanding default assumptions: it is no proved unit and no executed
state.

Nothing reads a record to select, weigh, keep or discard a clause. The
records are available during the search, but in this version only the final
answer printing uses them. The hook is in nine clause-building paths of GK.
In the tested build, the paths for instance generation, unit propagation and
similarity did not run: instance generation gave no hook call on two small
inputs, unit propagation is disabled in the build, and no similarity data
was given.

The option changes no clause, no index and no inference rule. The measured
controls: answers and proofs equal with the option on and off, and outputs
with the option off byte-equal to those of the unchanged build. The
calculation takes time, so a search that ends at its time limit can end at
another point. No statement beyond those controls is made.

## Who does what

| step | module | action |
|---|---|---|
| allow | `action_gk.summary_capability` | accepts a build only with the summary module and a validation record for its binary, library, strategy and summary contract |
| compile | `lc_action_summary.compile_profile` | reads the clauses of the query's view by role and writes the profile; no model call |
| stage | `action_gk.launch` | writes the profile beside the prover input in the launch's private directory; checks the bytes of both files inside the serial lock, immediately before each process |
| calculate | the summary build of GK | keeps one record per distinct plan prefix; each new prefix costs one update from its parent |
| render | the summary build of GK | prints World and Progress after the plan argument of a final `$ans` |
| decode | `action_gk.extract` | checks the layout and the payload of each entry, removes the two rendered positions, then decodes the answer as before |
| compare | `action_answer.summary_check` | compares the native values with `action_summary`, and the reference lists with the replay's exported states |

The update operations come from the effect, marker and frame clauses of the
selected theory. The only operation without a clause is the transport
erasure: when a holder moves, the location of an object it may hold is
forgotten.

## The profile

`{"schema": "planning_summary_profile/2", "profile_id", "semantic", "binding"}`.
`profile_id` is `sha256:` plus the SHA-256 of the canonical JSON of
`semantic` (sorted keys, compact separators, UTF-8). `binding` is provenance:
the SHA-256 of the prover input, the source, query and view hashes, the
question name, and one ledger entry per input clause. No calculation reads it.

`semantic` has exactly these fields:

| field | content |
|---|---|
| `contract` | `{summary: "planning_summary/1", normalizer: 1, transport}` |
| `root` | the planning root, a constant |
| `scope` | `{ambient: null, knower: null}` |
| `families` | sorted names: `rel:NAME`, `property:VALUE`, `have` |
| `initial` | `{facts, lossy}` |
| `static` | ground facts that a static guard reads |
| `constructors` | action name to arity |
| `operations` | see below |
| `score` | see below |
| `situation_constructor` | `{functor: "$do", arity: 2, action_arg: 1, parent_arg: 2}` |
| `situation_positions` | see below |

A term is a string, an integer, or a nonempty list that starts with its
functor. A pattern also admits `{"var": NAME}` and `{"wildcard": true}`.

```text
forget          {kind, action, pattern, loss}   loss: null | "if_removed" | "always"
negative_write  {kind, action, pattern}
insert          {kind, action, fact, guards}    guard: {scope: "old" | "static", atom}
```

All operations of one action apply at once. A guard reads the list before
the action or the static facts. `lossy` is an inherited bit: a conservative
operation may have removed or omitted a fact. One action sets it in four
cases:

- the action has a matching forget with `always`;
- a fact is removed only by forgets with a loss (`if_removed` or `always`),
  and no insertion of the action restores it; a matching forget with
  `loss: null` makes the removal of that fact certain, and then the fact
  costs nothing;
- an insertion has guards that give no binding, or a join that leaves a
  variable of the insertion unbound;
- a negative write vetoes an insertion.

Scores:

```text
goal_count        {template, units, goal}                 minus the goal facts that are absent
blocks_links      {template, units, goal, blocks}         minus the absent goals and the blocks above their objects
route_distance    {template, units, subject, destination, distance, no_route_distance}
route_milestones  the route fields and milestones: [{city, fact}]
{template: null, reason}                                  no score
```

Situation positions name where a clause holds a situation term:

| role | predicate | arity | path |
|---|---|---|---|
| `answer_plan` | `$ans` | `"variable"` | `[1]` |
| `query_plan` | the definition helper of the plan question | its arity | `[k]` |
| `reachable` | `reachable` | its arity | `[1]` |
| `context` | a predicate with a context term | its arity n | `[n, 2]`, with `via: "$ctxt"` |

## Limits and reasons

| limit | value | over the limit |
|---|---|---|
| actions in one situation term | 4096 | `depth_limit` |
| levels of one action or fact term | 64 | `term_depth_limit`; in a profile: refused |
| integers | `-(2**53-1) .. 2**53-1` | `numeric_range`; in a profile: refused |
| variables of one operation | 64 | profile refused |
| arities and path indexes | 1000000 | profile refused |
| zero character in a semantic string | none | profile refused |

| layer | reason codes |
|---|---|
| situation term | `depth_limit`, `open_root`, `malformed_situation`, `wrong_root`, then the defect of the oldest defective action: `term_depth_limit`, `numeric_range`, `unsupported_term`, `not_ground` |
| update | `no_rule_for_action`, `invalid_operation`, `term_depth_limit` |
| score | `location_missing`, `location_ambiguous`, `support_conflict`, `support_cycle`, `witness_goal`, `unsupported_goal`, `computed_goal`, `goal_family_unavailable`, `numeric_range` |
| native only | `allocation_failed` |

`not_ground` means a variable. An update that fails gives no list, and every
later prefix inherits the reason.

## The rendered answer

With `-planning-profile FILE` the summary build prints, for each entry of
`answers` and `rejected_answers`:

```json
{"answer": [["$ans", PLAN, ["$list", FACT, ["$list", FACT, "$nil"]], 0, WITNESS]],
 "planning_summary": {"schema": "planning_summary_output/1", "profile_id": "sha256:...",
   "decorated": true, "core_arity": 2, "slots": {"plan": 1, "world": 2, "progress": 3},
   "calculation": "computed", "lossy": false, "world_reason": null, "progress_reason": null,
   "template": "blocks_links", "units": "missing_goals_plus_obstructions"}}
```

World and Progress are printed after the plan. They are no arguments of the
stored answer, and no proof line changes. `core_arity` is the number of
arguments the answer has without them. `calculation` is `computed`, `partial`
(a list, no score) or `unavailable` (both null, with a reason). A Boolean
entry and an answer that is no single plan answer keep their `answer` and get
`{"decorated": false, "reason": "not_applicable"}`; after an allocation
failure the reason is `allocation_failed`.

The adapter checks two things before it decodes an entry.

- **Layout**: the schema and profile identifier, a Boolean `decorated`, a
  known reason for an entry that is not decorated, an integer `core_arity`
  of at least 1, the slot map with integer indexes 1, 2 and 3, and an answer
  of `core_arity` + 3 elements. A layout that does not fit gives
  `planning_profile_error`: the adapter cannot tell which positions are
  witnesses.
- **Payload**: World a strictly ordered list of ground facts of the
  profile's families, Progress an integer in the portable range, and a
  calculation, lossy bit, reasons, template and units that agree with them.
  In a fact, every compound term has a string functor, and every string can
  be encoded as UTF-8. A payload of another form keeps the answer and
  disables the annotation of that entry (`malformed_payload`); the
  annotation then keeps no values.

Each launch record of a summary request names the profile (`profile_id`,
`profile_sha256`) and the fingerprints of the two taxonomy files that GK
reads with `-taxonomy` (`data_files`: `present` with a SHA-256, `absent`,
`unreadable` or `not_used`). The fingerprints are provenance and not part of
the profile identifier. A recording of the launch (`action_gk.recording`)
holds the exact profile text.

## The build

`action_gk.BACKENDS["gk_summary"]` runs the installed GK 1.1.0, the same
binary, strategies and parameters as the default build `gk`, with the summary
request. Its validation record names the binary's SHA-256, the action library, the
strategy hash and the summary contract (`planning_summary_profile/2`,
`planning_summary/1`, `planning_summary_output/1`). A summary request runs
only when the binary at the path has that hash. Another binary at the same
path gets `unsupported_backend_requirement` with the reason
`planning_summary_not_validated` before any launch; a build without the
module gets `planning_summary_unsupported`; a missing binary gets
`backend_unavailable`. On the action route these checks run before the
translation, so a refused request makes no model call
(`action_gk.summary_preflight`). The library is checked again before the
launch, when the source exists. The build keeps the unmet requirements and known
failures of `gk`: negative persistence and the per-application confidence
are not validated.

## The annotation in the result

A replayed plan candidate gets `planning_summary` in its candidate row, and
the result record gets that of the validated plan:

| field | content |
|---|---|
| `world`, `progress`, `calculation`, `lossy`, `world_reason`, `progress_reason`, `template`, `units` | the decoded native values; `world` is a JSON array |
| `gk_disposition` | `accepted` or `rejected`: the list of the GK entry |
| `replay_verdict` | the replay's verdict on the plan |
| `reference_check` | `agrees` or `differs`: the native values against the reference interpreter |
| `replay_check` | `subset`, `not_subset`, `export_incomplete` or `root_not_validated` |
| `replay_prefixes` | the number of replay states compared |
| `summary_check` | `ok`, `summary_mismatch`, `annotation_disabled` or `unavailable` |
| `disabled`, `detail` | why the annotation has no values, and the evidence of a mismatch |

The replay validates the root and its first `checked_prefix` steps, all
steps for a valid plan. The replay comparison needs an exported state for
each of those prefixes. An empty state is a state; a missing or malformed
one is not. The replay is not run a second time.

- `ok`: the reference check agrees and the reference list of each validated
  prefix is a subset of the replay's state.
- `summary_mismatch`: a difference in either comparison. The values are
  removed and the evidence stays in `detail`.
- `annotation_disabled`: no usable annotation (`malformed_payload`, an entry
  that is not decorated), or the replay comparison could not be made
  (`replay_export_incomplete`, `replay_root_not_validated`).

None of these changes the answer, the plan, the confidence or the replay
verdict.

The annotations of GK's entries in the evidence record have
`summary_check: "not_checked"`. A rejected entry, and an accepted candidate
that the answer policy did not replay, keep this unvalidated annotation;
they never take the check of another candidate.

## Errors

The outcome `planning_profile_error` means that the summary request failed.
It has no logical verdict. The reason and `phase` say where:

- before any launch: the profile did not belong to its input;
- phase `launch`: a staged file was missing or changed before the launch, and
  that launch did not run;
- after the launch: the build refused the profile, or the output's layout did
  not fit its metadata (`summary_output_error`); no answer was decoded;
- phase `relaunch`: a staged file was missing or changed before the
  diagnostic relaunch. The completed launch stays in the evidence record,
  with its output, exit status and counted call. The relaunch was not made
  (`termination`: `diagnostic_not_launched`).
