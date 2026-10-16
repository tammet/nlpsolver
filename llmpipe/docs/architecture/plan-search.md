# The plan search

A plan or reachable question of the [action route](action-route.md) does not
go to GK as one search. The route first builds candidate plans in Python,
asks GK to prove each candidate, and searches with GK only when no candidate
passes. This page describes that procedure: `action_plan.solve`, the default
for every plan and reachable question.

Two keys select it: `-plan-builder` (on, the default) and `-noplan-builder`
(the single discovery launch only). `-planning-summary` also runs the single
launch, because a summary profile belongs to that launch's input.

## Who decides

A plan from the Python side is a proposal. Only two components decide an
answer, the same two as without the search:

- **GK** proves the question. A candidate is compiled as the question itself,
  with the plan in it, so GK proves exactly what it proves for a discovered
  plan.
- **The replay** (`action_replay`) executes the plan on the source units and
  checks every step and the goal.

The proposals can make the search faster or find a shorter plan. They cannot
make a wrong plan an answer: a proposal that GK does not prove, or that the
replay does not validate, is not used. The records the search adds to a GK
input only remove clauses from GK's search; they never add a premise to a
proof.

## The steps

```text
compiled discovery input
  -> 1. the model (plan_model)           no model: go to 4
  -> 2. the proposals (plan_builder)      dropped by the bound or the replay
  -> 3. a GK check per proposal           the first proved and validated plan is the answer
  -> 4. a discovery launch with filters   (when step 2 had a plan or the model is partial)
  -> 5. the single discovery launch       the result as without the search
```

### 1. The model

`plan_builder.Task` reads the compiled GK input of the discovery question and
builds a ground model from the shape of the clauses, not from their names
(`plan_model`):

- the ground actions: each permission rule `poss(ACT, ...)` with its
  conditions, for every combination of the input's constants;
- the effects of each action, as add and delete effects with their
  conditions; a strict marker deletes, a default effect is defeasible;
- the frames, which keep a fact across an action unless a marker changes it;
- the initial state, the static facts and the goal.

The model is usable when every action functor is closed (its instances are
the combinations of the input's constants), no add effect is unbounded, and
the model used every frame clause. An exception while building it, or a model
that is not usable, gives no proposal.

The model does not read every clause. It ignores the library's hooks, the
denial rule, the reachability step and the question clauses, and it ignores a
text clause it cannot classify, such as a denial or a restriction check. Each
of these makes the model more permissive than the text: it can propose a plan
that the text forbids, which the replay and GK then reject, but it cannot miss
a plan because of them. A clause that writes a fluent in a form the model
cannot read (an open writer) makes the model unsure of that fluent; the
model records an open atom.

### 2. The proposals

The builder (`plan_builder.build`) finds at most one plan in each of three
ways, in this order:

| way | method |
|---|---|
| `ehc` | hill-climbing toward the goal: at each state it takes an action that a relaxed plan (one that ignores delete effects) needs first, until the goal holds; a greedy best-first search continues where the climb stops |
| `agenda` | the goals in an order that does not undo an achieved goal (a reasonable order, approximated from the model's invariants), each reached by hill-climbing |
| `bfws` | best-first width search: states that make a new fact true first, ties broken by the number of unmet goals |

Each way first uses the strict effects only, then all effects when the model
has defeasible ones. A found plan is cleaned: a step whose removal keeps the
plan valid in the model is removed. Most plans of the planning test set need
no search at all.

The plans are then filtered:

- a duplicate is dropped;
- a plan outside the question's step bound is dropped (longer than an
  at-most bound, or another length than an exact bound);
- the replay runs on each plan, and a plan it finds invalid or inconsistent
  is dropped. A plan it cannot decide (`not_checked`, `contested`) stays.

At most three plans remain (`action_plan.MAX_CANDIDATES`), the shortest and
the replay-valid ones first.

### 3. The GK checks

A proposal is checked by the question itself. `action_route.compile_query`
with `plan_situation` compiles the same plan or reachable question, but the
definition clauses of its discovery question hold the plan's situation term
in place of the situation variable. The question still asks for the
situation, so GK reports the plan in its answer binding exactly as for a
discovered plan, and the [answer policy](action-answers.md#discovery) reads it
unchanged: the root, the step bound, the witnesses and the confidence cutoff
are the question's.

The check launch adds the known states of the plan (`plan_state.records`):
one `$planstate` record for the root and one for the state after each step,
each with the facts that the model makes true there. With the GK key
`plan_state` 1, GK drops a clause that needs a fact which is false in one of
these states. Such a clause cannot belong to a proof of this plan, so GK finds
the proof after few clauses.

A wrong list could cut the real proof, so a fact family is listed only when
the model covers it completely. `plan_state.families` leaves out a family
that an open writer, an unclassified clause, or a frame clause the model could
not use can write; GK never prunes on a family that is left out.

The check runs under the role strategy `discovery:check`: the discovery keys,
`plan_state` 1, and `max_answers` 1, so GK stops at the proof. It has no
termination relaunch. When a check finds no proof and the model left a family
out or recorded a note, the same plan is checked once more without the
`$planstate` records.

The first check whose result is a plan that the replay validates is the
answer (stage `builder_check`).

### 4. The discovery with filters

When no proposal passed, the search falls back to GK's own search.

If the model is usable, has no open atom and ignored no text clause, and the
builder found no plan at all, step 5 runs directly: a model that read the
whole text and found no plan gives no reason to expect one from the filters
(stage `discovery_model_no_plan`). The answer still comes from GK.

Otherwise the plan filters run first. `plan_analysis.Analysis` derives them
from the model:

- an impossible pair: two adjacent actions where the second can never be
  executable after the first;
- an impossible start: an action that is never executable at the root;
- an impossible action: an argument pattern that no permitted instance has,
  such as two equal arguments of one action;
- a useless pair: two adjacent actions that return every fact to its state
  before them; used only for an at-most bound, with no open writer and no
  permission rule with a negative precondition.

Each step of the analysis gives no filter when a premise is not proved. Each
filter is a `$planfilter` record with a pattern of `$do` terms. The launch
runs under the role strategy `discovery:filtered` (the discovery keys and
`plan_filters` 1): GK drops a clause whose plan contains a pattern. A plan it
finds is the answer (stage `filtered_discovery`).

### 5. The single discovery launch

When the filtered launch finds no plan, or when no filter was derived, the
single discovery launch of the question runs, as without the plan search
(stage `discovery`).

## Time

Every launch of the search has the question's per-launch seconds (`-seconds`,
default 30). The extra stages (the model, the proposals, the checks and the
filtered launch) together get at most three times that
(`action_plan.BUDGET_FACTOR`), counted from the start of the search. A launch
starts only when it fits in what is left; a skipped launch is recorded. The
single discovery launch is not counted and always runs when no earlier step
gave a plan, so no question gets less search than without the plan search.

On the planning test set a check takes about 0.1 seconds of GK. The 39 plan
rows that a check answered took 4 seconds of GK time together, against 173
seconds with the single launch
([mechanism experiments](../mechanisms/experimental.md#the-action-route-for-texts-about-actions-and-plans)).

## Launch labels

Each launch has its own label, which names its files under `-gkin` and in a
kept launch folder:

| label | launch |
|---|---|
| `QUERY.plan.check<n>` | the check of the n-th proposal |
| `QUERY.plan.check<n>_nostates` | its retry without the `$planstate` records |
| `QUERY.plan.filtered` | the discovery launch with the plan filters |
| `QUERY.plan.discovery` | the single discovery launch |

## The record

The result of the question keeps the original query's identity and the GK
calls of every stage, and adds `plan_search`
([result record](../encodings/action-artifacts.md#result-record)):

| field | content |
|---|---|
| `stage` | `builder_check`, `discovery_model_no_plan`, `filtered_discovery` or `discovery`: the step that gave the result |
| `model` | the model's status (`usable`, `unusable`, `model_error`), the reason, its notes, the ignored clauses, the number of open atoms and of actions |
| `builder` | each way's status and plan, the dropped plans with the reason, the kept plans with the replay's verdict |
| `checks` | per proposal: the plan, the hash of its candidate query, and each attempt with its label, outcome, the number of `$planstate` records, and the families listed and left out |
| `filters` | the number of derived filters, and whether useless filters were allowed |
| `launches` | the filtered and the single discovery launch, with their label, outcome and plan |
| `budget` | the per-launch seconds, the total, the time spent, and the skipped launches |
| `answered_query` | the identity of the query whose launch gave the result (a candidate query for `builder_check`) |
| `earlier_launches` | the launch summaries of the other stages; `-summary` counts them |

## Related pages

- [Proof search and answers](action-answers.md) — the launches, the answer
  policy, the replay.
- [Action compilation](action-compilation.md) — the discovery question and its
  obligations.
- `../gk/Doc/planning.md` in the nlpsolver repository — the GK keys
  `plan_state`, `plan_filters` and `max_answers`, and the `$planstate` and
  `$planfilter` records.
- [Action route modules](../code/action-route.md) — `action_plan`,
  `plan_model`, `plan_builder`, `plan_state`, `plan_analysis`.
