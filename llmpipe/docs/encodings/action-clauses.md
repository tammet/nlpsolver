# Action clauses

This page defines the GK clauses that the experimental action route compiles.
The ordinary pipeline never produces them. The models of the route write
Stage 1 and Stage 2 ([action prompt interface](action-prompts.md)). The
compiler writes everything on this page. The clauses that do not depend on the
text are in the [action library](action-library.md). The records that hold the
clauses are in [action artifacts and records](action-artifacts.md).

## Processing layers

```text
English text and question
    │
    ▼  Stage 1, a model call
sentence packages with action readings     action-prompts.md
    │
    ▼  Stage 2, a model call
the Stage-2 envelope: worlds, contexts,    action-prompts.md
query_contexts, types, logic
    │
    ▼  the source and query compilers
source artifact, query artifact            action-artifacts.md
    │
    ▼  the view of one query obligation
GK input: source clauses, library          this page, action-library.md
clauses, ordinary view, query clauses
    │
    ▼  GK, one launch per question
evidence, then the answer policy and the replay
```

## Names and variables

| name | meaning |
|---|---|
| `#:Ann 1` | a concrete entity: its Stage-1 id with the prefix `#:` |
| `?:v_X` | the source variable `X` of a Stage-2 formula |
| `?:Sit` | the situation variable of a source law |
| `?:S` | the situation variable of a library clause |
| `?:L1`, `?:L2`, ... | a location variable of a law literal, one per distinct atom |
| `?:Lh` | the location variable of a successor literal (an effect or a marker) |
| `?:Fv1`, `?:Fv2` | the free location and knower variables of a source fact |
| `?:Qv1`, `?:Qv2` | the free location and knower variables of a query literal |
| `W0`, `W1`, ... | a world of the source. These names are reserved: a source variable called `W0` is invalid (`reserved_variable`) |
| `sk_X`, `sk_X_S2`, `sk_X_S2_2` | the Skolem witness of an existential binder of `X` (below) |
| `skq_<query>_<var>` | the Skolem symbol of a universal variable of a query body: a constant, or a function of the answer variables |
| `$obj` | the objective knower of a law |

A Stage-2 variable is one upper-case letter, followed by at most one
upper-case letter or digit (`X`, `B2`).

Each existential binder gets one Skolem symbol, counted after negation moves
inward. The name is `sk_<Var>` when the variable has one such binder in the
whole source. It is `sk_<Var>_<unit>` when the variable has one binder in this
unit and others elsewhere. It is `sk_<Var>_<unit>_<k>` for the k-th binder of
the variable in one unit. A witness of a standing law depends on the
situation: `[sk_<Var>, ?:Sit, universals...]`. A witness of an initial or
static description is a constant, or a term over the entity universals only.

## The five action constructors

An action is a term of one of five constructors. GK reports a plan as a chain
of these terms.

| term | meaning |
|---|---|
| `move(A, F, T, M)` | A moves itself from F to T by the means M |
| `take(H, X)` | H takes hold of X and gains possession of it |
| `put_on(H, X, Y)` | H puts the X that it holds on Y |
| `put_in(H, X, B)` | H puts the X that it holds inside B |
| `change(A, X, V, Tool)` | A gives X the property V, with Tool |

The means slot of `move` and the value slot of `change` usually hold words;
the structural check also accepts a declared id or a bound variable there. `unspecified` stands in a means or tool slot when the text names
none. The [action library](action-library.md) gives the conditions and the
results of each constructor.

## Predicates

| predicate | arguments | context term |
|---|---|---|
| `is rel2` | a relation (`located_at`, `on`, `in`, `holding`), two entities | yes |
| `has property` | a value word, an entity | yes |
| `have` | an owner, an entity | yes |
| `poss` | an action term: the action is executable | yes |
| `execution_denied` | an action term: the text denies the action | yes |
| `ok_<constructor>` | an action term: every restriction of the constructor is met | yes |
| `restriction_<k>_<unit>` | an action term: the k-th restriction of the unit is met | yes |
| `changed_rel2`, `changed_property`, `changed_have` | the arguments of the fluent: the action wrote this instance | yes |
| `reachable` | a situation, a step counter | no |
| `isa` | a class, an entity | no |
| `connected` | two places, a means | no |
| `differ` | two entities: they are different | no |
| `standard_mode` | a means | no |
| `surface` | an entity whose class is a surface | no |
| `derived_property` | a value word: the value is computed | no |
| `$defq0` | the answer variables of one question | no |

`is rel2`, `has property` and `have` are the stored fluents: an action changes
them. They have the signatures of the ordinary encoding
([Stage 2](stage-2.md)), so an ordinary clause in the law pattern applies to
them unchanged. `can`, `executable`, `after` and `state_law` are Stage-2
operators only. No clause holds them.

## The context term

Every literal of a fluent, of `poss` and of the other action predicates ends
with one context term, `$ctxt(T, S, L, K)`. The situation is in the second
slot and in no other argument.

| slot | in a fact of the text | in a law |
|---|---|---|
| T, tense | `present`, `past` or `future`, from the unit's context record | `present` |
| S, situation | the unit's world: `W0`, `W1`, ... | `?:Sit` in a source law, `?:S` in the library; `$do(A, S)` in a successor literal |
| L, location | the constant of a `scope` location, else `?:Fv1` | one variable per distinct atom |
| K, knower | the knower's constant, else `?:Fv2` | `$obj`; a query with a knower puts the knower here |

Within one law the location variables follow one rule:

- a frame's premise, conclusion and blocker share one location variable;
- the `poss` premise of a frame has another;
- a successor literal of an effect or a marker has `?:Lh`;
- a default's blocker repeats the context of the literal that it follows.

A query literal has `$ctxt(present, S, L, K)`. S is the literal's situation. L
is the query's ambient location, else `?:Qv1`. K is the query's knower, else
`?:Qv2`.

## Situations

A situation is a world of the text (`W0`, `W1`, ...) or
`$do(Action, Situation)`. A source lists its worlds in narrative order. Every
`holds(W, F)` of Stage 2 names one of them. A query has a planning root: a
world that starts every action history of the query and binds its questions.
The root is the last world of the source unless the question selects another.

Each source unit gets its scope from its form:

| unit form | scope | example |
|---|---|---|
| `description_static` | none: only `isa` and `connected` atoms | "Ann is a person." |
| `description_initial` | the unit's world in every fluent, also under a quantifier or a condition | "Nothing is on any block." |
| `state_law`, `holds(W, ["state_law", F])` | one shared situation variable `?:Sit` | "If the bowl has been washed, it is clean." |
| `availability`, `denial`: `... -> can(A, ACTION)`, `not can(...)` | a rule at every situation; its conditions stand at that situation | "If the egg is broken, Ann can whisk it." |
| `restriction`: `executable(ACTION) -> Q` | a check on every path of a matching action | "The hand can take a block only if it is red." |
| `effect`: `P -> after(ACTION, Q)` | P at the situation, Q at its successor | "After Ann cooks the egg, it is not raw." |
| `ordinary_event` | none: the compiler reports it as unsupported | "Ann travelled to Tallinn." |

A conditional initial description is a fact of its world, never a law. Among
the state units, only `state_law` makes a rule hold at every situation; the
action laws hold at every situation by their form. The translation decides
which sentences are standing rules ([the state-rule convention](action-prompts.md#scope-and-qualifications)).

## Clauses of the text

Each source unit compiles to clauses with a role. The first part of a clause
name says where it comes from:

| name | clause |
|---|---|
| `src:<unit>:<role>:<n>` | a clause of the unit; `n` is its place in the source's clause list, so one clause has one name in every view. A hook or a computed-property fact names all its units, joined by `+` (`src:S7+S8:hook:12`) |
| `src:source:distinct:<n>` | a `differ` fact |
| `src:types:static_type:<n>` | a type fact |
| `ordinary:V1-core:<name>` | a clause of the selected ordinary view |
| `query:<query>:<question>` | a question of the query; its definition clauses add `:definition:<k>` |
| `query:<query>:seed` | the reachability seed of a discovery |
| other names | a library clause ([action library](action-library.md)) |

### Descriptions and standing laws

| role | clause |
|---|---|
| `static` | a static atom, no context term: `isa(robot, #:Robo 1)` |
| `initial_fact` | a fluent at the unit's world: `is rel2(located_at, #:Ann 1, #:Haapsalu 2, $ctxt(present, W0, ?:Fv1, ?:Fv2))` |
| `standing_law` | a clause over `?:Sit`, which every fluent of the law shares |
| `static_type` | `isa(class, #:entity)` from a type record of the source |
| `distinct` | `differ(X, Y)`, both orders, for the concrete ids that the source formulas use; a witness, a word value and an unused id get none |
| `derived_no_inertia` | `derived_property(V)` for a value that the state policy computes |

A `normally` formula keeps the scope of its unit. The compiler moves
`normally` inward, as the ordinary clausifier does, until it qualifies one
literal L. The clause with L then gets the blocker
`["$block", ["$", CLASS, N], ["$not", L]]`, or the positive atom for a
negative L. CLASS is the subject class, else the class of the last negative
`isa` condition, else `$generic`. N is the number of other negative conditions
plus one. A negated default, a disjunctive default, a default inside a default
and two defaults in one clause are unsupported (`unsupported_default_form`).

A state unit with a probability p below 1 gets the evidence 2p − 1, spread
over its clauses by the ordinary distribution (`lc_packages`): only the anchor
clauses get an `@confidence`, and with k anchors each gets
(2p − 1)^(1/k). A permission with one `can` head puts 2p − 1 on each of its
paths. A unit with p ≤ 0.5, an uncertain permission with several `can` heads,
and an uncertain restriction or effect compile to no clause and make the
source unsupported.

### Permissions and denials

A permission `can(A, ACTION)` is a sufficient rule. It compiles to one path per
applicability template of the action's constructor
([templates](action-library.md#templates)). A path holds the unit's
conditions, the template's physical preconditions and the restriction hook,
and concludes `poss(ACTION, C)`, strict or under `normally` as the text says:

```json
{"@name": "src:S4:availability:4", "@logic": [
  ["-is rel2", "holding", "#:Robo 1", "#:key 2", ["$ctxt", "present", "W0", "?:L1", "$obj"]],
  ["-differ", "#:key 2", "#:box 3"],
  ["-ok_put_in", ["put_in", "#:Robo 1", "#:key 2", "#:box 3"], ["$ctxt", "present", "W0", "?:L2", "$obj"]],
  ["poss", ["put_in", "#:Robo 1", "#:key 2", "#:box 3"], ["$ctxt", "present", "W0", "?:L3", "$obj"]]]}
```

This path is from a snapshot view, so the situation is the root `W0`. In the
other views it is `?:Sit`.

`put_on` has two paths: onto a block and onto a surface. A `move` permission
takes the stated-endpoint path, with no `connected` literal, when three
conditions hold:

- the unit identifies the origin, the destination and the means, as constants
  or as variables that a positive condition above the head binds;
- that condition binds them under the head's own binders;
- the actor is not a universal without a condition.

Otherwise it takes the public path, which needs a stated connection. A template
variable that the action does not hold, such as the support of `take`, becomes
a fresh universal `?:v_Z<n>`.

A denial `not can(A, ACTION)` compiles to the marker
`execution_denied(ACTION, C)`. The library's clause `denied_not_poss` then gives
`-poss`, and the marker blocks every default of the same action.

### Restrictions

A restriction has the form
`forall V.. ([GUARD and ..] executable(PATTERN) -> REQUIRED)`. PATTERN is one
constructor with variables and constants in its slots. A GUARD is a signed
`isa` or `connected` literal over pattern variables. REQUIRED is a
conjunction of signed state literals over pattern variables.

| role | clause |
|---|---|
| `restriction_check`, match | `REQUIRED -> restriction_<k>_<unit>(PATTERN, C(S))`, with no guard in the body |
| `restriction_check`, nonmatch | `differ(P_j, constant_j) -> restriction_<k>_<unit>(GENERAL, C(S))` for each constant of the pattern; `differ(P_j, P_k)` for each repeated variable; the stated complement of each GUARD |
| `necessity_restriction` | `GUARDs and complement(one REQUIRED literal) -> not poss(PATTERN, C(S))`, one clause per required literal |
| `hook` | all checks of the constructor `-> ok_<constructor>(GENERAL, C(S))`, one clause per constructor |

GENERAL is the constructor with the slot variables `P1..Pn`. `k` counts the
restrictions of one unit from 1. A nonmatch needs a `differ` fact or a stated
negative class: the absence of a class proves nothing. A constant in a word
slot (a means, a value, `unspecified`) has no nonmatch clause. No clause of
this pass holds a positive `poss` or `can` literal.

The hook of a restricted constructor replaces the library's default hook in
every view.

### Effects

A strict effect `P -> after(A, L1 and .. and Ln)` gives one clause per head
literal, and one marker clause per negative head literal:

| role | clause |
|---|---|
| `effect` | `P(C(S)) and poss(A, C(S)) -> L(C($do(A, S)))` |
| `marker` | `P(C(S)) and poss(A, C(S)) -> changed_*(..., C($do(A, S)))` |

P stands in the old situation for every head literal. The effect and marker
clauses of the text hold two situations: S and `$do(A, S)`, as the library's
effects, markers, frames and search step do. No effect concludes `can` or `poss`, so
an effect grants no permission. A text effect and a library effect stay
separate clauses, also when they write opposite signs; the source artifact
names the conflict.

## Query clauses

A query has obligations, and each obligation has a positive and a negative
question. One GK launch answers one question. An ask and a discovery have no
negative question.

A question has one of two forms:

- **literal.** A ground literal is asked directly. The negative question asks
  the complementary literal.
- **definition.** The clauses of `BODY -> $defq0(ANSWER...)`, in one direction,
  and the question `$defq0(...)`, with `@askvars` (the number of reported
  variables) when it reports variables. A yes-no question is the bare
  `["$defq0"]`. An existential of the body is a clause variable. A universal of
  the body is a Skolem term `skq_<query>_<var>`, a function of the answer
  variables when there are any. The negative question
  defines `$defq0` from the negated body, so one false conjunct proves the
  negation of a conjunction.

The situations of a query:

| query | situation of its atoms |
|---|---|
| `question`, `ask` | the planning root, in every atom, also under a quantifier or a condition |
| `verify` | a step at the chain of the steps before it, from the root; the final formula at the whole chain |
| `plan`, `reachable` | one shared `?:Sit` |

`executable(A)` in a query becomes `poss(A, C)`. A `can` in a query is
invalid (`can_in_query`).

A discovery (`plan`, `reachable`) has a seed and one definition clause:

```json
{"@name": "query:S3:seed", "@logic": ["reachable", "W0", ["s", ["s", ["s", ["s", "0"]]]]]}
{"@name": "query:S3:plan:positive:definition:0", "@sourcetype": "question", "@logic": [
  ["-reachable", "?:Sit", "?:N"],
  ["-is rel2", "located_at", "#:Ann 1", "#:Tallinn 3", ["$ctxt", "present", "?:Sit", "?:Qv1", "?:Qv2"]],
  ["$defq0", "?:Sit"]]}
{"@name": "query:S3:plan:positive", "@question": ["$defq0", "?:Sit"], "@askvars": 1}
```

The seed gives the search depth as a unary number from the planning root. The
counter of the definition clause is `0` for an exact step bound and a variable
otherwise. A plan answer is a `$do` chain that ends in the root:
`$do(move(#:Ann 1, #:Haapsalu 2, #:Tallinn 3, bus), W0)`. The outer
existential variables of the goal follow `?:Sit` as further answer variables.

A verify query with steps also has a joint positive question:
`poss(A1, C(W)) & ... & Q(C(S_n))`, with one shared tense, location and
knower. A query asserts nothing: it adds no `poss`, no fluent and, for a
supplied sequence, no `reachable` fact.

## The supported fragment

The compiler checks the action laws and the goals of `plan`, `reachable` and
`verify` queries against these forms. A well-formed law or goal outside them
is reported unsupported and is never rewritten. Descriptions and standing laws
are clausified in full, with disjunctions and negations.

```
goal, law condition   G := ATOM | not(ATOM) | and(G, ...) | exists(V, G)
law                   LAW := forall(V, LAW) | and(LAW, ...) | implies(G, HEAD) | HEAD
                           | implies(ANTECEDENT, REQUIRED)
                      HEAD := forall(V, HEAD) | and(HEAD, ...) | can | normally(can)
                           | not(can) | after(A, EFFECT)
                      ANTECEDENT := executable | and(executable, GUARD, ...)
                      GUARD := a signed isa or connected literal
                      REQUIRED := LITERAL | and(REQUIRED, ...)      LITERAL := ATOM | not(ATOM)
                      EFFECT := a conjunction of signed fluent literals
```

ATOM is a fluent, static or equality atom. In the final formula of a `verify`
query, ATOM also includes `executable`. Negation reaches atoms only. A
`question` or `ask` formula is ordinary snapshot logic and is not limited to
G. An unsupported goal is `unsupported_goal_form`, an unsupported law
`unsupported_law_form`.

The profile `physical_v1` reserves this vocabulary:

- the property `clear_top` ("clear", "nothing is on X") and the property
  `empty` (a hand that holds nothing);
- the classes `person`, `hand` and `block`, and the surface classes `table`,
  `floor`, `shelf` and `counter`;
- the standard means `bus`, `train`, `ship`, `ferry`, `plane`, `taxi` and
  `foot`;
- `unspecified` for a means or a tool that the text does not name.

Every other property, class and means is an open word with no library
behaviour. The [action artifacts](action-artifacts.md#diagnostics) list the
forms that the route reports and does not approximate.

## Related pages

- [Action prompt interface](action-prompts.md) — what the two model calls write
- [Action library](action-library.md) — the clauses that do not depend on the text
- [Action artifacts and records](action-artifacts.md) — the compiled records and their diagnostics
- [Action end-to-end example](action-end-to-end-example.md) — one text through every layer
- [Action compilation](../architecture/action-compilation.md) — how the compiler builds these clauses
- [GK clause list](gk-clauses.md) — the clause format, `$block` and the ordinary `$ctxt` term
