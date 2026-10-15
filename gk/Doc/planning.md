# Planning search

GK 1.1.0 adds search options for situation-calculus planning inputs. The
inputs come from the action route of the llmpipe pipeline: a plan is the
first argument of an `$ans` literal, a chain of `$do(Action, Situation)`
terms that ends in a root constant such as `W0`.

Every option on this page is experimental, and every option is off by
default. A run without these strategy keys, command-line options and input
records searches as GK 1.0.11 does.

| feature | switch | effect |
|---|---|---|
| literal selection | strategy keys `ground_contextfree_negative_first`, `permission_pair_first`, `action_actor_type_first`, `reachable_known_head_first` | choose which literal of a given clause GK resolves |
| blocker-unit cut | strategy keys `blocker_unit_cut`, `blocker_unit_cut_guards` | drop a clause whose answers would all get confidence 0 |
| eager condensation | strategy key `eager_condensation` | remove redundant literals from each new clause |
| plan filters | strategy key `plan_filters` and `$planfilter` input records | drop a clause whose plan contains an impossible or useless step |
| known plan states | strategy key `plan_state` and `$planstate` input records | drop a clause that needs a fact that is false in a known state |
| planning summaries | options `-planning-profile FILE`, `-planning-trace FILE` | print the facts and a progress score of each answer plan |

The strategy keys are in [`strategy_reference.md`](strategy_reference.md),
section "Planning search", and the options in
[`cli_reference.md`](cli_reference.md), section "Planning".

## Scope

The strategy keys on this page act only in the primary search: at depth 0,
outside a negative-evidence search. The searches for blockers and the
negative-evidence searches run as before.

GK cannot tell a search for a new plan from another positive search. The
caller gives these keys only to a launch that searches for a plan. The
pipeline's action route calls such a launch a discovery launch.

## Literal selection

Four keys choose the literal of a given clause that GK resolves. Each key is
the exact integer 0 or 1. A key works only under pure query focus: the
`query_focus` strategy without `negative_pref`, `positive_pref`,
`hyperres`, `knuthbendix_pref` or `hardness_pref`.

When a clause has an eligible literal, that literal becomes the only
resolvable ordinary literal of the clause. Special computation literals keep
their usual resolvability. Without an eligible literal, the usual rule
applies. The keys change neither the indexing of active clauses nor any
inference rule.

| key | eligible literal |
|---|---|
| `ground_contextfree_negative_first` | a negative ordinary literal that is ground and has no `$ctxt` term at any depth |
| `permission_pair_first` | a negative `poss(B, C)` where B is a known action term, and the situation of C is `$do(A, S)` with A a known action term; C is that situation or a `$ctxt` term whose second argument is that situation |
| `action_actor_type_first` | a negative `isa(C, X)` with a constant C and a variable X, where X is the actor (first) argument of a known action term in an action position of the same clause |
| `reachable_known_head_first` | a negative `reachable($do(A, S), N)` where A is a known action term |

A known action term is a compound term with one of these functors and
arities: `move/4`, `take/2`, `put_on/3`, `put_in/3`, `change/4`. These are
the action constructors of the pipeline's action library. The test reads
syntax only.

For `action_actor_type_first`, the action positions are the action argument
of `poss/2`, and the action of each `$do/2` step on the situation chain of
the first argument of `$ans`, of the first argument of `reachable`, and of
the world slot of a `$ctxt` argument. `$block` literals are not searched.

When several keys are on, the first rule that finds a literal wins, in this
order: ground context-free, permission pair, actor type, known-head
reachable.

## Blocker-unit cut

A blocker literal `$block(0, C)` makes a clause hold unless C is provable.
When a unit clause with confidence 1 proves C, every answer derived from the
clause gets confidence 0, because blockers are inherited and only
instantiated. With `blocker_unit_cut` 1, GK drops such a clause.

The match is one-way: the unit's variables are bound, and the clause's
variables act as constants. A positive C needs a positive unit. `$not(A)`
needs a negative unit.

The cut applies only when all of these conditions hold:

- the unit is an input axiom or is derived from axioms only, with the
  maximal stored confidence; goals and assumptions never cut;
- the blocker priority is exactly the integer 0;
- no clause of the search's theory has a literal with the predicate of C and
  the opposite sign;
- the predicate of C is not one that GK evaluates itself (`=` and the
  `$`-names).

GK checks each selected given clause, and each answer clause before it
registers the answer.

With `blocker_unit_cut_guards` 1 as well, a strict axiom rule can also cut.
The rule has the form "head unless guards fail". It cuts when its head
matches C and each guard instance equals a ground strict unit.
`blocker_unit_cut_guards` has no effect without `blocker_unit_cut` 1.

The check switches itself off for a search with an attached knowledge base,
a variable predicate, a full predicate table (4096 predicates), a truncated
match length (`unify_maxuseterms`) or a failed allocation.

**Output on stderr.** With the key on, each primary search prints a line
`blocker unit cut: ...` with the state of the check, the indexed units and
the guarded rules. One line per check stage follows, with the counts and the
time, and one line `blocker unit cut by NAME: N` per cutting unit or rule.

## Eager condensation

With `eager_condensation` 1, GK condenses each resolvent, paramodulant,
similarity result and factor of the primary search before it builds the
clause. A literal is dropped when another literal of the same sign is an
instance of it by binding only variables that occur once in the clause.
`$block`, `$ans` and `$simblk` literals are dropped only as variants of each
other. Condensation is off when `unify_maxuseterms` truncates terms.

Stderr reports `eager condensation: clauses shortened N, literals removed M`.

## Plan filters

A plan filter names a pattern of plan steps that never leads to a useful
plan. The caller computes the filters from the action theory and adds them to
the input as unit clauses:

```json
{"@name": "planfilter:F5",
 "@logic": [["$planfilter", "impossible_pair",
             ["$do", ["put_on","?:Z","?:U","?:V"], ["$do", ["take","?:X","?:Y"], "?:S"]],
             ["$distinct", ["$pair","?:U","?:Y"]]]]}
```

- **Kinds:** `impossible_pair`, `impossible_start`, `impossible_action`,
  `useless_pair`.
- **Pattern:** a `$do` term. A pair kind needs the form `$do(B, $do(A, S))`.
- **`$distinct`:** a list of `$pair` terms. Each pair must be bound to two
  ground terms that are not equal. The list may be empty: `["$distinct"]`.

The JSON parser keeps `$planfilter` clauses out of the clause list. They are
never premises of a proof.

| `plan_filters` | effect |
|---|---|
| 0 (default) | the filter clauses stay out of the search; nothing is checked |
| 1 | GK checks the `$do` nodes on the chain of each `$ans` term |
| 2 | GK also checks every `$do` term in every literal |

GK checks each derived clause before it is stored, and each given clause. A
clause with a matching `$do` node is dropped. At a `$do` node whose action is
a compound term, GK tries the filters whose outer action has the same
functor. The match is one-way: the clause's variables act as constants. An
answer clause that matches is counted as an alarm and is not dropped.

A malformed filter switches the whole check off. Stderr then says
`plan filters: off: <reason> (filter N)`, and the search runs as without
filters. The check is also off with an attached knowledge base or with
`unify_maxuseterms`. With the key on, stderr reports
`plan filters: key K, loaded N (...), derived cut D of C, given cut G of C, answer alarms A of C, time T`
and one line per filter.

## Known plan states

The plan-state check speeds up the verification of a known ground plan. The
caller computes the true facts of each state of the plan and gives one unit
clause per state:

```json
{"@name": "planstate:s1",
 "@logic": [["$planstate", ["$do", ["take","hand","c"], "W0"],
             ["$true", ["has property","clear_top","b"], ["have","hand","c"],
                       ["is rel2","on","a","table"], ["is rel2","on","b","a"]],
             ["$families", ["$fam","has property","clear_top"], ["$fam","have"],
                           ["$fam","is rel2","on"]]]]}
```

- **Situation:** a ground situation term.
- **`$true`:** the ground fluents that are true there, without their `$ctxt`
  argument.
- **`$families`:** the fluent families that the `$true` lists cover
  completely. `["$fam", P]` names a predicate. `["$fam", P, A]` names a
  predicate with the first argument A.

The parser keeps these clauses in the plan-filter list, out of the clause
list.

With `plan_state` 1, GK drops a derived or given clause of the primary search
when it has a negative literal that meets all of these conditions:

- its family is listed;
- its `$ctxt` situation is a known situation;
- its other arguments are ground;
- it is not in the `$true` list of that situation.

Such a literal needs a fact that is false in a known state, so the clause
cannot contribute to a proof of the known plan. A malformed clause switches
the check off, with a message on stderr. With the key on, stderr reports
`plan state: key K, situations N, true fluents M, derived cut ..., given cut ..., literals compared ..., time ...`.

## Planning summaries

`-planning-profile FILE` loads a profile in the format
`planning_summary_profile/2`. The pipeline's compiler writes it from the
action theory of the question. The profile fixes three things:

- the initial positive facts;
- the update operations of each action;
- one progress score.

For a ground situation term `$do(An, ... $do(A1, Root))`, GK computes
**World**, a sorted list of positive facts, and **Progress**, one integer. A
larger Progress is better. Both describe the plan on the condition that it is
executable. Neither one is a proof of executability.

GK keeps one prefix tree per run: one record for each distinct ground action
prefix. A new prefix is computed once, from the record of its parent. A
read-only hook inspects each built clause and each input clause at the
situation positions that the profile names. No record selects, weighs, keeps
or drops a clause. The option changes no clause, index or inference rule.

With a profile, GK prints World and Progress after the plan argument of each
plan answer in `answers` and `rejected_answers`. A `planning_summary` object
describes the layout:

```json
{"answer": [["$ans", PLAN, ["$list", FACT, ["$list", FACT, "$nil"]], 0, WITNESS]],
 "planning_summary": {"schema": "planning_summary_output/1", "profile_id": "sha256:...",
   "decorated": true, "core_arity": 2, "slots": {"plan": 1, "world": 2, "progress": 3},
   "calculation": "computed", "lossy": false, "world_reason": null, "progress_reason": null,
   "template": "blocks_links", "units": "missing_goals_plus_obstructions"}}
```

World and Progress are not arguments of the stored answer, and no proof line
changes. `core_arity` is the number of answer arguments without them. A
Boolean entry, or an answer that is not a single plan answer, keeps its
`answer` and gets `{"decorated": false, "reason": "not_applicable"}`.

A profile that does not load gives
`{"error": "planning_profile_error: ..."}` and exit code 1 before any search.

**The profile.** It is the JSON object
`{"schema": "planning_summary_profile/2", "profile_id", "semantic", "binding"}`.
`profile_id` is `sha256:` plus the SHA-256 of the canonical JSON of
`semantic`: sorted keys, compact separators, UTF-8. `binding` holds
provenance only, and no calculation reads it. `semantic` has these fields:

| field | content |
|---|---|
| `contract` | `{summary: "planning_summary/1", normalizer: 1, transport}` |
| `root` | the root constant of the plan |
| `scope` | `{ambient: null, knower: null}` |
| `families` | sorted family names: `rel:NAME`, `property:VALUE`, `have` |
| `initial` | `{facts, lossy}` |
| `static` | ground facts that a static guard reads |
| `constructors` | action name to arity |
| `operations` | per action: `forget`, `negative_write` and `insert` operations |
| `score` | the score template and its parameters |
| `situation_constructor` | `{functor: "$do", arity: 2, action_arg: 1, parent_arg: 2}` |
| `situation_positions` | the predicates and argument paths that hold a situation term |

The score templates are `goal_count`, `blocks_links`, `route_distance` and
`route_milestones`. `{template: null, reason}` means no score.

**Limits.**

| limit | value | over the limit |
|---|---|---|
| actions in one situation term | 4096 | reason `depth_limit` |
| levels of one action or fact term | 64 | reason `term_depth_limit`; in a profile: the profile is rejected |
| integers | `-(2**53-1)` to `2**53-1` | reason `numeric_range`; in a profile: the profile is rejected |
| variables of one operation | 64 | the profile is rejected |
| arities and path indexes | 1000000 | the profile is rejected |
| zero character in a semantic string or key | none allowed | the profile is rejected |
| observations returned for one clause | 256 | status `truncated` |

A value that is not an integer, a plain constant, a `#:` constant or a
compound term gets the reason `unsupported_term`. A variable gets
`not_ground`. After a failed allocation the context answers no more lookups,
and an answer is printed unchanged with `"decorated": false`.

`-planning-trace FILE` writes one JSON line per observation of the hook and a
last line of counters. Two options exist for tests: `-planning-inspect`
inspects the input clauses and ends before any search, and
`-planning-test-fail-after N` makes the allocation after N more allocations
fail.

The summary module was built and tested on Linux with gcc only.

## Diagnostic environment variables

These variables change only the output on stderr, never the search.

| variable | output |
|---|---|
| `GK_BLOCKCUT_TRACE=1` | the cut's predicate table, each indexed unit and guarded rule, each cut, and the reports of nested searches |
| `GK_BLOCKCUT_ANSWER_TIMES=1` | each registered answer of the primary search, with its time and given count, in the cut's report |
| `GK_ANSWER_TIMES=1` | `answer registered: cpu T s, given N: <answer>` for each registered answer of the primary search |
| `GK_COND_TRACE=1` | `condensed: [before] -> [after]` for each eager condensation |
| `GK_DEPTH_TRACE=1` | `D k <actions> <given>` for each kept derived clause and `D g <actions>` for each given clause of the primary search; `<actions>` counts the `$do` steps of the `$ans` term, -1 without one. `2` adds the `$ans` term, `3` the whole clause |
| `GK_PLANFILTER_TRACE=1` | `PF <stage> <filter name> <$ans term>` for each filter match; `2` also prints each loaded pattern |
| `GK_PLANSTATE_TRACE=1` | `PS <stage> <literal>` for each plan-state drop |
| `GK_REPORT_LOOP_EXIT=1` | the exit of the primary positive loop and the selection counts; printed also when a selection key is on |
| `GK_SEARCH_STATS=1` | after the primary search, why the derived-clause weight check refused clauses |
| `GK_GCFN_INSPECT=1` | test mode: the selection of each input clause under each selection setting, then exit before any search |

## Compile-time switches

| macro | effect |
|---|---|
| `-DBLOCKER_UNIT_CUT_OFF` | build without the blocker-unit cut |
| `-DBLOCKER_UNIT_CUT_NOANSWERS` | leave out the check of answer clauses |
| `-DBLOCKER_UNIT_CUT_NOGUARDS` | leave out the guarded rules |
| `-DBLOCKER_UNIT_CUT_DERIVED` | experimental: also check each derived clause before it is stored |
| `-DBLOCKER_UNIT_CUT_CACHE` | experimental: cache the lookup result of each signed blocker atom |
| `-DBLOCKER_UNIT_CUT_VARCHECK` | test builds: verify that each match restores every variable binding |
| `-DBLOCKER_UNIT_CUT_FAILTEST` | test builds: `GK_BLOCKCUT_FAILAT=N` fails allocation point N once |
| `-DBLOCKER_UNIT_CUT_MAXPREDS=N` | the size of the cut's predicate table (default 4096) |
| `-DPLAN_FILTERS_OFF` | build without plan filters and plan states |
