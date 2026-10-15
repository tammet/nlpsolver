# summary : formal controls of the planning summaries (checkpoint P)

The specification is `memos/PLAN_2026_10_04_planning_summary_implementation_v2_astra.md`,
revision 2.1 (a local memo). This directory holds the four formal source
records that the specification names. `../check_action_summary.py` reads them.

Run the check with `python3 tests/action_route/check_action_summary.py`, or
with every other check through `python3 tests/action_route/run_checks.py`.
The check calls no model and no prover.

## The four records

| file | goal | sequence | frozen scores |
|---|---|---|---|
| `unstack.json` | the hand holds a | take c, put c on the table, take a | -2, -1, -1, 0 |
| `reverse_tower.json` | a on c | take c, put c on the table, take a, put a on c | -2, -1, -1, -1, 0 |
| `two_leg_travel.json` | Ann in Oslo | bus, train | -2, -1, 0 |
| `ticket_travel.json` | Ann in Oslo | issue the ticket, bus, train | -4, -3, -2, 0 |

Each record has the format of a formal input of the action route (`units`,
`entities`, `queries`), so `solve.py -formal FILE` reads it too. The field
`summary` holds the expectation:

```text
choice     null (the default table), or a selection {schema, tracked, score, milestones}
families   the tracked families of the compiled profile
template   the score template of the compiled profile
sequence   the supplied actions, in source spelling
prefixes   one entry per prefix, the root first: {world, progress, lossy}
```

`world` is the list in clause spelling (`#:a 2`) and in the canonical order
of `action_summary.order_key`. The expectations were written by hand from
the tables of the specification before the first comparison.

The check requires, at every prefix: the frozen list, score and lossy bit;
and equality of the list with the replay's export
(`action_replay.State.export`) for the tracked families.

## The modules

| module | content |
|---|---|
| `solver/lc_action_summary.py` | the profile compiler: clause-role audit, operations, transport coverage, default table, identity and binding |
| `solver/action_summary.py` | the profile language, the interpreter, the four scores, the prefix tree |
| `solver/action_replay.py` | two read-only exports: `State.export`, `Source.export_static`; `replay(..., export=True)` |

## The profile language (the fixed reference for the native evaluator)

A profile is `{"schema": "planning_summary_profile/2", "profile_id",
"semantic", "binding"}`. `profile_id` is `sha256:` plus the SHA-256 of the
canonical JSON of `semantic` (sorted keys, compact separators, UTF-8).
`binding` is an object of provenance. No calculation reads it.

`semantic` has exactly these fields:

| field | content |
|---|---|
| `contract` | `{summary: "planning_summary/1", normalizer: 1, transport: null or a contract name}` |
| `root` | the planning root, a constant |
| `scope` | `{ambient: null, knower: null}` |
| `families` | sorted names: `rel:NAME`, `property:VALUE`, `have` |
| `initial` | `{facts: [ground fact of a tracked family], lossy: true or false}` |
| `static` | ground facts that a static guard reads |
| `constructors` | action name to arity |
| `operations` | see below |
| `score` | see below |
| `situation_constructor` | `{functor: "$do", arity: 2, action_arg: 1, parent_arg: 2}` |
| `situation_positions` | see below |

A term is a string, an integer, or a nonempty list that starts with its
functor. A pattern also admits `{"var": NAME}` and `{"wildcard": true}`.
A wildcard is legal in a forget and in a negative write only.

Operations. Each has a `kind` and an `action` pattern of a known constructor.

```text
forget          {kind, action, pattern, loss}   loss: null | "if_removed" | "always"
negative_write  {kind, action, pattern}
insert          {kind, action, fact, guards}    guard: {scope: "old" | "static", atom}
```

A `pattern`, a `fact` and an old guard are fact patterns of a tracked family.
Every variable of a pattern is in the action pattern. Every variable of an
inserted fact is in the action pattern or in a guard.

Score. `{template: null, reason}` or one of:

```text
goal_count        {template, units, goal}
blocks_links      {template, units, goal, blocks}
route_distance    {template, units, subject, destination, distance, no_route_distance}
route_milestones  the route fields and milestones: [{city, fact}], each pair once
```

`distance` maps a place to its number of legs to the destination. The places
are the endpoints of the static `connected` facts and the destination.
`no_route_distance` is the number of those places plus 1. A place without a
route and a place outside that set both get it.

Situation positions. `{predicate, arity, path, role}` and, for the role
`context` only, `via: "$ctxt"`.

| role | predicate | arity | path |
|---|---|---|---|
| `answer_plan` | `$ans` | `"variable"` | `[1]` |
| `query_plan` | the definition helper of the discovery question (`$defq0`) | its arity | `[k]`, the situation argument |
| `reachable` | `reachable` | its arity | `[1]` |
| `context` | a predicate with a context term | its arity n | `[n, 2]` |

Numbers. Every integer of `semantic` and every score is within
`-(2**53-1) .. 2**53-1`. A profile outside the range is refused. A score
outside it is undefined with reason `numeric_range`, and the list is kept. A
Boolean is never an integer. A profile that breaks any rule above gives
`ProfileError` before a context exists.

Limits. One admission contract for the reference and the native evaluator.

| limit | value | over the limit |
|---|---|---|
| actions in one situation term | 4096 | `depth_limit` |
| levels of one action or fact term | 64 | `term_depth_limit`; in a profile: refused |
| integers | `-(2**53-1) .. 2**53-1` | `numeric_range`; in a profile: refused |
| variables of one operation | 64 | profile refused |
| arities and path indexes | 1000000 | profile refused |
| zero character in a semantic string or key | none | profile refused |

A level: the action or fact itself is level 1, and each compound term inside
another is one level more. A constant has no level of its own.

Reason codes (`action_summary.REASONS`), 18 codes.

| layer | codes |
|---|---|
| situation term | `depth_limit`, `open_root`, `malformed_situation`, `wrong_root`, then the defect of the oldest defective action: `term_depth_limit`, `numeric_range`, `unsupported_term`, `not_ground` |
| update | `no_rule_for_action`, `invalid_operation`, `term_depth_limit` (an inserted fact over the level limit) |
| score | `location_missing`, `location_ambiguous`, `support_conflict`, `support_cycle`, `witness_goal`, `unsupported_goal`, `computed_goal`, `goal_family_unavailable`, `numeric_range` |

A term with several defects gets the first code of the situation row, in
that order. An action with several defects gets the first of its four codes.
`not_ground` means a variable and nothing else. `unsupported_term` is a value
outside the term language: a fraction, null, a Boolean, an empty list. The
limit is 4096 actions: a term of 4096 actions has a record, a term of 4097
gives `depth_limit`. `witness_goal`, `unsupported_goal`, `computed_goal` and
`goal_family_unavailable` come from the compiler in a score with
`template: null`; the evaluator copies them. The native evaluator has one
more code, `allocation_failed`.

`Context.get(term)` returns `(record, reason)`. With a record, the reason is
the record's `world_reason`: null, or the code of the update that failed at
that prefix or before it. `Context.observe(term)` returns `{whole, record,
reason}`; under a defective action it gives the record of the prefix below
the oldest defective action with `whole: false` and that action's defect.

The docstrings of the two modules describe the update rules.

## Saved outputs

`saved/` holds outputs of the summary build of GK (binary `7f8b42ca...`) that
`../check_action_summary_route.py` reads through fake builds:
`unstack.on.out`, `unstack.off.out` and `witness.on.out`.
`instgen.malformed.out` is the output of the instance-generation hook test;
GK's proof print in it is not valid JSON, and the adapter must read it as a
typed `malformed` result.

## Dependencies

`../check_action_summary.py` and `../check_action_summary_route.py` need
`solver/`, `runtests.py`, this folder, and the GK data folder `../gk`
beside `llmpipe/`. They make no model call and no GK proof search. When a
binary is at the registered path of the development build, the capability
group checks its hash against the validation record.

`../check_action_summary_sweep.py` compares the summaries with the replay on
every gold plan of `../fixtures/cases/` and of the planning test rows. It
needs the wider action-route test data and `solver/action_check.py`.
