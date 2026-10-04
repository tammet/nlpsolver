# Action compilation

The action compiler turns an accepted Stage-2 translation into GK clauses. It
compiles the source once into a source artifact, then each question into a
query artifact against it. It is deterministic code and calls no model and no
prover. This page describes the order of its passes and the decisions in each.
The [action clauses](../encodings/action-clauses.md) define the clauses, and
the [action artifacts](../encodings/action-artifacts.md) the records.

```text
source packages ──► structural validation (lc_action)
                ──► situations and clauses of state units (lc_action_situate)
                ──► library selection (lc_action_library)
                ──► permissions, denials, identity (lc_action_avail)
                ──► restrictions (lc_action_restrict)
                ──► effects, state policy, dependencies (lc_action_effects)
                ──► source artifact

query package + source artifact
                ──► validation and selection (lc_action.validate_query, action_route.compile_query)
                ──► granularity and transport checks, search depth
                ──► backend requirements, views, obligations (lc_action_query)
                ──► query artifact
```

`action_route.compile_source` runs the source passes in this order. A pass
that finds a form outside the route's fragment marks the unit unsupported with
its reason. The unit keeps its formula, and the source becomes unsupported. A
source with an unsupported or invalid unit has no clause list, and its queries
are not answered.

## Structural validation

`lc_action` checks the form of each package and gives each unit its form:
`description_static`, `description_initial`, `state_law`, `availability`,
`denial`, `restriction`, `effect` or `ordinary_event`. The form comes from the
formula. The checks cover:

- the arity of each predicate and constructor;
- the variables: their names, their binders, no world name as a variable;
- the declared worlds of each `holds`;
- the context records: only on an initial description, naming declared
  entities;
- the supported fragment of laws and goals
  ([action clauses](../encodings/action-clauses.md#the-supported-fragment)).

The Stage-1 reading of a unit must fit its form. When it does not, the unit is
invalid (`reading_form_mismatch`), unless the sentence and the form decide the
reading. The compiler then adjusts the reading and records a note:

- a plain denial under the reading `restriction` is `availability` (K1). A
  plain denial has a denial word ("cannot", "can't", "may not", "no X can") and
  no necessary-condition word ("unless", "only", "except", "requires",
  "must"). Because "must" counts as a necessary-condition word, a "must not"
  sentence is never a plain denial;
- a rule between two states under the reading `effect`, with no effect word,
  no actor and no action term, has no reading (K2);
- a unit without a reading whose Stage-1 action has the mode `capability` gets
  its law reading (K11): a permission with a permission word and no denial or
  necessary-condition word, and a plain denial, are `availability`; a
  restriction with a necessary-condition word is `restriction`.

An effect or a restriction whose action term unifies with the term of another
unit with different Stage-1 verbs is a `method_collision`: the law would apply
to the other verb's action. Two permissions with different verbs for one
action are alternatives, not a collision.

## Situations

`lc_action_situate` gives every state unit its situations and compiles it to
clauses:

- a static description gets no situation;
- an initial description gets its world in every fluent atom, also under a
  quantifier, an implication or a negation;
- a standing law (`state_law`) gets one universally bound situation `?:Sit`
  that all its fluent atoms share.

The order of the steps is: situations, then the mixed-scope check on the
situated formula, then the removal of implications, negation moved inward,
Skolemization, distribution into clauses, and the expansion of defaults.

The mixed-scope check reads the situated formula with the source's
implications. Under `implies(A, B)` with a fluent in A, an `isa` or
`connected` atom in B is a timeless conclusion from a dynamic condition: the
unit is `mixed_scope_rule` and gets no clauses. A static condition on a fluent
conclusion stays supported.

A default (`normally`) keeps the scope of its unit and becomes a blocked
clause, as in the ordinary clausifier ([action clauses](../encodings/action-clauses.md#descriptions-and-standing-laws)).

Action laws (permissions, denials, restrictions, effects) get their clauses
from the later passes.

## The library

`lc_action_library` loads the [action library](../encodings/action-library.md)
and checks its identity. The source artifact records the identity, and every
query view later takes its library clauses by role.

## Permissions, denials and identity

`lc_action_avail` compiles each permission at the shared situation `?:Sit`:
one path per applicability template of the action's constructor. A `move`
permission takes the stated-endpoint template when the rule identifies its
origin, destination and means and its actor is not a universal without a
condition, and the public template otherwise. Only a
positive condition above the head, under the head's own binders, binds an
endpoint. A denial compiles to the marker `execution_denied`.

A unit with a probability p gives the evidence 2p − 1 to each of its paths.
The paths of one unit are alternatives for one application of the rule, so no
helper clause joins them.

The pass also writes the `differ` facts for the concrete ids that the formulas
use. It checks the location granularity of the source: a place that is itself
in a place, or one entity at two places of one world that are not all in the
profile's flat set, is `unsupported_location_granularity`. At the source level
it compares only the facts that every query keeps together: present tense, no
scope location, no knower. Each query compares its own facts later.

## Restrictions

`lc_action_restrict` compiles each restriction to checks: a match check when
the required condition holds, and nonmatch checks when the action differs
from the pattern. Each restricted constructor gets one hook that requires all
its checks. A necessity clause gives `not poss` for an action that matches the
pattern while a required literal is false. No check reads `poss` or `can`.

A nonmatch needs evidence: a `differ` fact or a stated negative class. The
absence of a class proves nothing. A word slot (a means, a value) has no
nonmatch, so the compile note names the actions that stay unproven. A
constructor with an unsupported restriction unit gets no hook, so no action of
that constructor is executable.

## Effects and the state policy

`lc_action_effects` compiles each strict effect to one clause per head literal,
and a marker clause for each negative head literal. The condition stands in
the old situation for every head literal. An effect never concludes `poss`:
an effect grants no permission.

**State policy.** A property value in the head of a standing law is computed
when no initial description asserts it and no action writes it. The profile
may declare a value stored or computed. A value that is both, with no
declaration, makes its law units `ambiguous_state_policy`. A computed value
gets `derived_property(V)`, so no frame carries it. A standing law whose head
is a stored relation, `have`, `clear_top` or `empty` is
`unsupported_stored_state_law`.

**Dependencies.** The pass records, for each law unit, the signed fluents that
it reads and writes, the library effects of its actions, and which text write
stops the frame of an opposite fact. It lists the dynamic negative reads: a
negative fact that a law reads and an action may need to keep. It lists the
possible holdings whose holder may move (the transport inventory). The query
compiler reads these records.

## Query compilation

`action_route.compile_query` first validates the query package and its
selection: the planning root, the ambient location and the knower must name a
declared world or entity. It then:

1. **excludes** the fact units that the query cannot use: a fact in the past
   or the future, a fact with another scope location, a fact with another
   knower;
2. **checks the location granularity** of the facts that the query keeps;
3. **checks transport.** The library moves no held object with its holder. A
   query whose answer reads the location of an object after its holder moved
   stops with `unsupported_transport_dependency`. For a supplied sequence the
   compiler scans the steps: a take adds a holding, a put releases it, a move
   of the holder carries what it holds. For a plan question any goal that
   reads the location of a listed object stops;
4. **computes the search depth**: the stated step bound, else the search cap
   (4, or `-plan-depth`). An explicit cap below an exact bound or below the
   length of a supplied sequence is `insufficient_search_allowance`. An
   explicit cap below an at-most bound becomes the depth; the query records
   that the search does not cover the bound;
5. runs the query pass of `lc_action_query`: backend requirements, the view,
   and the obligations.

### Backend requirements

A query may need a prover capability that the registered build does not have.
`lc_action_query` decides two:

- **`negative_persistence`**: the answer needs a negative fact kept across an
  action. The library has no frame for a negative fact. For a discovery the
  depth decides: a negative initial fact that a law reads needs a depth of 2 or
  more, one that the goal reads a depth of 1 or more; a negative fact that an
  action writes needs one step more. For a supplied sequence the compiler
  scans the steps: a read after step i needs the negative fact when it was
  established before step i and no step since then certainly wrote the fact.
  A final literal is read in both polarities, because the negative question
  proves its complement. A snapshot question never needs the capability.
- **`shared_source_confidence`**: a discovery, or a supplied sequence whose
  steps meet the action, when the source has an uncertain permission. One
  application of the rule reads `poss` several times in a proof, and GK counts
  the evidence once per use.

A query that needs `negative_persistence` on a backend that has not validated
it stops with `unsupported_backend_requirement` and the reason
`negative_persistence_unavailable`. When only the negative question of a
verification's final formula needs it, the query runs: a Yes needs no carried
negative, and the answer policy refuses every other answer. A query that needs
`shared_source_confidence` runs, and the adapter labels the confidence of an
affected answer experimental.

### Views

Each query kind takes one view:

| view | query | source clauses | library roles |
|---|---|---|---|
| `snapshot` | `question`, `ask`, `verify` with no steps | all but effects, markers and the computed-property facts; `?:Sit` replaced by the planning root | static helpers, defaults, default hooks, the denial consequence, bound to the root |
| `verify` | `verify` with steps | all | all but the search step |
| `discovery` | `plan`, `reachable` | all | all |

Every view also holds the ordinary family `V1-core`. The clauses of an
excluded unit leave every view. A query with a knower puts the knower in place
of `$obj` in every law. The default hook of a restricted constructor leaves
every view.

### Obligations

The query pass writes the prover questions
([query clauses](../encodings/action-clauses.md#query-clauses)):

| query | obligations |
|---|---|
| `question` | one snapshot obligation, positive and negative |
| `ask` | one snapshot obligation, positive only |
| `verify` with no steps | the final formula at the root, positive and negative |
| `verify` with steps | one obligation per step and one for the final formula, positive and negative; the joint positive question |
| `plan`, `reachable` | one discovery obligation, positive only, and the seed |

A verify step must be executable at the chain of the steps before it, from the
planning root. Its negative answer counts only after the steps before it are
established.

## Related pages

- [Action clauses](../encodings/action-clauses.md) — the clauses that these passes write
- [Action artifacts and records](../encodings/action-artifacts.md) — the source and query artifacts
- [Proof search and answers](action-answers.md) — what happens to the obligations
- [Action route modules](../code/action-route.md) — the module of each pass
