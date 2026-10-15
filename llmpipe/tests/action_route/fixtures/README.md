# Gold fixtures for the action route (WP02)

Hand-written and reviewed. No model call produced any of them, and none is
copied from a stored run. They are the oracle the compiler (WP03–WP10), the
replay (WP11) and the runtime (WP12–WP15) are checked against. The contract
they encode is Appendix A of
`memos/PLAN_2026_09_09_action_planning_work_packages_astra.md`; section
numbers below (A2.3, A4.2, ...) refer to it.

| file | content |
|---|---|
| `COVERAGE.md` | the C01–C28 coverage index, the A8.1 family index, and the pilot regressions |
| `REVIEW.md` | the fixture-review record: author, reviewer, dispositions, status and every amendment |
| `PILOTS.md` | why the old hand GK clauses of travel, tower and food change under the contract |
| `cases/*.json` | one record per case; the schema is below |
| `gk/` | the three pilot hand inputs, copied with provenance; not oracles |

The tools that read the records live one directory up:

| tool | what it does |
|---|---|
| `../fixture_materialize.py` | builds the effective cases from a record (rules below); every consumer reads effective cases, never a variant entry |
| `../check_fixture_schema.py` | validates every effective case: fields, Stage-1 projection, Stage-2 grammar and vocabulary, query packages, expectations, candidates; run by `../run_checks.py` |
| `../check_fixture_mutations.py` | proves each rejection of the two modules above on a deliberately invalid input |

## Record schema

One JSON object per file. Field order is fixed so diffs stay readable.

```
id            stable, equals the file name without .json
purpose       one line
contract      the C identifiers and A sections the case exercises
family        the A8.1 family name(s)
input_kind    "text" | "formal_only"
text          the English source, every sentence of it (input_kind text).
              Source-only: no question and no editorial note. A query's
              sentence is in the query's own `text`. A consumer that needs one
              input string (the ordinary pipeline in x07) submits the passage
              followed by one query text; it never submits a question twice.
profile       "physical_v1" | "ordinary", or an object {"name": ..., "policy":
              {...}, "locations": {"flat": [...]}}: the A2.5 stored/computed
              policy and the declared flat location set (A2.7); nothing else
entities      every concrete entity id any effective case of the record uses,
              with its profile class; every "distinct" pair the compiler may
              assume comes from these ids (A4.3)
worlds        optional, after `entities`: the source's worlds in narrative
              order, e.g. ["W0", "W1"]; names W<n>, no repeat. Absent: the one
              world W0. Every holds(W, F) names a declared world. The order
              comes from this list only (encoding v2, migration plan section 9)
units         the base source units, in order (schema below)
queries       the base query units, each with its own expectation
variants      named source variants with their own queries (rules below)
candidates    supplied action sequences with per-step states and verdicts;
              a candidate names the variant it belongs to (default: base)
support       case-level syntax/compile/backend/replay summary
explain       the English explanation of every subtle expected result
notes         why the fixture exists; amendments
```

A unit:

```
id            S1, S2, ... : matches the @id in stage2; a derived unit (a
              sentence split into two readings) has an id like S3a and a
              derived_from field naming the parent
text          the sentence, or the sentences the unit covers. Every unit
              sentence occurs in the case passage and every passage sentence
              belongs to a unit (checked). The derived units of one sentence
              all hold the whole parent sentence as `text`; `scope` and `note`
              say which clause each unit is.
stage1        the action-relevant projection of the Stage-1 gold (input_kind
              text): type (real | situation | strict_rule | normal_rule),
              entities [{id, type: concrete | generic, category}],
              actions [{root, mode, roles}], action_reading (availability |
              restriction | effect | occurrence; absent = ordinary reading),
              confidence, time. Categories are the Stage-1 enum (person,
              place, artifact, animal, substance, ...); the profile classes
              hand / block / table are Stage-2 typing, not categories. The
              projection contains every field the route reads: identity needs
              concrete/generic, method-collision detection needs roots and
              roles. Fields the route does not read are not pinned.
              Checked for a text record: the projection is an object; its
              concrete entities include every concrete id of the unit's
              formula; a unit with an action scope (availability, restriction,
              effect, occurrence) or an action_reading has both
              action_reading and a non-empty actions list with root and
              roles. Roots come from the sentence's verb. Categories are
              optional. A formal-only record has no projections.
              Role keys are actor, target, source, destination, instrument,
              location, recipient, result. Negation is not a role: it stays
              in the sentence and in the Stage-2 formula. Two generic mentions
              of one noun in a unit are numbered ("block 9", "block 10") and
              stay generic; two roles never name the same generic mention.
              Stage 2 alone fixes which variables are equal.
stage2        the exact Stage-2 package: ["@id", id, PACKAGE]; the world of
              holds(W, F) is a declared world
context       optional, on an initial unit only: {tense, location,
              location_role, knower}. tense present | past | future (default
              present); location an entity of the case; location_role
              provenance | scope (a location without a role makes the source
              unsupported, unsupported_contextual_location); knower an entity
              of the case (absent: objective). The compiler builds the unit's
              fact context from it (migration plan section 3)
scope         "initial" | "static" | "standing" | "availability" |
              "restriction" | "effect" | "denial" | "occurrence"
              The unit's dominant scope. Static atoms inside an initial unit
              (isa, connected) stay static; the label does not push them into
              a situation.
syntax        "supported" | {"unsupported": reason}
compile       "supported" | {"unsupported": reason, "detail": ...}, reason
              from the decided list (REVIEW.md disposition 1)
confidence    for an uncertain unit: source_probability (the Stage-2 @p),
              compiled_evidence (2p - 1, the pipeline convention), and the
              convention's source; the backend reports evidence
clauses       expected properties of the clauses `compile_source` emits for
              the unit (vocabulary below). An unsupported unit is kept in the
              artifact with its diagnostic and yields no clause, so it may
              hold `must_not_have` entries only.
inspection    expected properties of a lower-level operation called on the
              unit's Stage-2 formula directly, never of `compile_source`
              output: {"operation": "situation_insertion_skolemization",
              "must_have": [...], "must_not_have": [...]}. Used by x04 to pin
              the witness dependency of an unsupported existential head.
```

A query:

```
id            Q1, Q2, ...
text          the English question, or "(formal: ...)" for a formal-only query
stage1_reading  plan_question | reachable_question | executable_question |
                verify_question | absent (ordinary question / ask)
stage2        ["@id", id, PACKAGE] with one of the A3.3 packages; null only
              for a source-only query (view none), an adapter fixture (view
              adapter) or the ordinary pipeline (view ordinary)
view          "discovery" | "snapshot" | "verify" | "adapter" | "none" |
              "ordinary"
seed          the expected reachability seed of a plan or reachable query,
              checked: n = min(bound, cap), cap = limits.search_cap or 4;
              "0" for n = 0, else "s^n(0)"; "none" when an exact bound exceeds
              the cap (no search; the insufficient_search_allowance case).
              No other query has a seed. require_zero_remaining for exactly-N.
limits        an explicit search cap when the query tests one
search_note   a remark on expected search time; not an expectation
expect        see below
backend       required backend capabilities beyond the starting backend
              (A6.3): negative_persistence, shared_source_confidence. A
              listed capability that the starting backend lacks makes the
              expected outcome unsupported_backend_requirement before search,
              except negative_persistence that only a verification's No needs:
              that query runs, keeps a Yes and refuses every other answer.
backend_note  what a fuller backend must additionally validate for this
              query, without changing the starting-backend expectation
replay        "covered" | "not_checked: reason" | "n/a"
undeclared_entities  only with a translation_invalid expectation: the ids the
              query deliberately names without declaring them
planning_root  a declared world: the query's root (seed, question situation,
              snapshot binding). Absent: the last declared world
ambient       an entity of the case: the location whose `scope` facts the
              query's views keep. Absent: no scope fact enters
knower        an entity of the case: the knower whose facts the views keep and
              whose constant replaces $obj in the laws. Absent: objective
replay_context  for an adapter fixture: {"case", "variant", "query"} naming
              the effective case the candidates are replayed against and the
              query whose final goal the replay validates. Checked: the case
              and the query exist among the materialized cases and the query
              is a plan, reachable or verify package.
```

A package runs only in its view: plan and reachable in discovery, verify in
verify, question and ask in snapshot (or ordinary for the ordinary profile).
These are all the query fields; any other field raises.

An expectation (`expect`):

```
answer        Yes | No | Unknown | contested | none, or an entity id for ask.
              A snapshot query records answer only; the outcome name for an
              immediate question is decided for the runtime adapter
              (`snapshot_result`, WP12) and is not written in the golds.
outcome       one A5.3 outcome, or insufficient_search_allowance (a run
              limit) or ordinary_result (the ordinary pipeline answered)
reason        the unsupported_translation or backend reason
plan          innermost-first list of ground action terms; a witness of a
              source existential appears as sk_<Var>
evidence      required: which clause, fact, rule or saved output decides it,
              in the terms of encoding v2: W0 for the planning root, W0+1,
              W0+2 for its successors, `poss`, the templates and the library
              clauses. A citation of a saved historical output keeps its
              names and says its date and layout. It records why the answer
              holds and is not the compiled term layout. The c25
              `gk_output` records are saved outputs of the old layout (`s0`
              for the root)
forbidden_answers, forbidden_outcomes
              exact baselines are pinned above; these list what a defect
              would produce (a 'not Yes' is written as Unknown plus a
              forbidden Yes)
alternative   {"outcome", "when"}: the outcome on a backend whose raw output
              differs in a named way (e.g. an eligible candidate the replay
              rejects makes not_found into candidate_not_validated)
confidence    a number for a strict result or a single 0.99 frame; otherwise
              an object naming the layer ("backend"), the value or the query
              it must equal, a tolerance, and the forbidden value
on_validated_backend  the expectation once a listed backend capability is
              validated
```

A candidate:

```
id            K1, K2, ...
variant       the variant whose effective source it replays (default base)
sequence      ground action terms in execution order
states        the finite signed state after each step (facts that matter)
verdict       "valid" | "invalid" | "not_checked" | "contested" |
              "inconsistent_action_state"
step          the first failing step (1-based) for a non-valid verdict
reason        one line
```

## Variants and effective cases

A record file is not a test input. `fixture_materialize.py` turns it into
effective cases, one per source, and the checks and the compiler tests read
those:

```
<record>:base        the record's units and queries (absent when both are empty)
<record>:<variant>   one per entry of variants
```

Building a variant case, in this order:

1. `text`, `profile`, `entities`, `worlds` replace the record's value as a
   whole when given. In a text record a variant that changes a sentence or a formula
   (`units`, `units_remove`, `units_replace`, `units_add`, or a `units_patch`
   of `text`, `stage1` or `stage2`) must give its own `text`. An edited
   source never inherits the base passage.
2. `units` (a full list) replaces the whole unit list. Otherwise start from
   the base units and apply `units_remove` (ids must exist), then
   `units_replace` (complete units; ids must exist), then `units_patch`
   (fields merged into an existing unit; id must exist), then `units_add`
   (ids must be new).
3. `queries_keep` names base queries copied unchanged. Every other base query
   is dropped: a variant lists what it tests. An entry of `queries` whose id
   is a base query overrides it: `expect` replaces the base `expect` as a
   whole, every other query field inherits unless the override gives it. Any
   other entry is a complete new query. A variant query that is a different
   question takes an id the base does not use, so it inherits nothing.
4. A query never changes the source (no `units_add` / `units_remove` on a
   query) and a candidate never adds units. A source change is a variant.

An effective case is `{case, record, variant, input_kind, text, profile,
entities, worlds, units, queries, candidates}`; `candidates` holds the record's
candidates that name this case. A consumer needs no other lookup.

Duplicate ids, dangling references, unknown variant fields and unknown query
fields are errors.
The materializer is the definition; this section describes it.

## Action terms and fluents in the golds

Stage 2 uses the source-level forms of A2.2 with entity ids as in Stage 1
(no `#:` prefix; the clause converter adds it):

```
["move", A, F, T, M]  ["take", H, X]  ["put_on", H, X, Y]  ["put_in", H, X, B]
["change", A, X, V, Tool]
["is rel2", "located_at"|"on"|"in"|"holding", X, Y]   ["has property", V, X]
["have", A, X]   ["can", A, ACTION]   ["executable", ACTION]
["after", ACTION, Q]   ["state_law", F]   ["connected", F, T, M]   ["isa", C, X]
```

Variables are upper-case single letters or letter+digit, bound by `forall` /
`exists` exactly as the ordinary Stage 2 requires. `"unspecified"` is the
sentinel of A2.2. The actor of `can` equals the action's actor slot. A
property value is a lexical constant. No Skolem term occurs in Stage 2. An
unsupported unit may use the ordinary Davidsonian event form (`isa activity`,
`has type`, `has actor`, ...); a supported unit uses only the list above.

## Clause-property vocabulary

`clauses.must_have` and `clauses.must_not_have` list patterns. A pattern is
matched against the compiler's emitted clauses by role and structure, never
by clause name or by textual equality with the old hand files (A4.5). A
pattern names an atom without its situation and context arguments: the
context term (a fact's record context, a law's per-literal
`$ctxt(present, ?:Wld, L, $obj)`) is not part of any pattern and is checked
by `check_action_situations` and `check_action_library`.

```
role          initial_fact | static | standing_law | availability (a compiled
              executability path poss(ACT)) | restriction_check | hook |
              path_coverage | denial_consequence (the library's one) |
              necessity_restriction | effect | marker | frame | distinct |
              denial (the marker execution_denied(ACT)) | derived_no_inertia |
              query | seed | diagnostic | "*" (any role)
unit          the source unit the clause comes from (or "library")
lit           the head literal as a source-level atom (entity ids, variables)
sign          "+" | "-"
situation     "named" | "shared_current" | "successor" | "none" | "free"
              (the situation in the world slot of the literal's context term:
              named: a declared world, W0, W1, ...; shared_current: one
              universally bound S shared by body and head; successor: head at
              $do(A,S); free: a situation term that is neither a world, nor
              the law's variable, nor its successor : always forbidden)
body          the antecedent literals, each with sign and situation
body_exact    true: the body must be exactly the listed literals, no more
constructor   for hook / path_coverage / necessity / restriction_check
pattern       the action pattern of a restriction_check
condition     its conjunctive signed condition literals
requires      for a hook: the restriction checks it conjoins; for
              path_coverage: every clause with a positive poss head of the
              constructor conjoins the hook, and the hook requires these
provenance    the unit the clause is attributed to
marker        true when a negative or positive write must carry its
              changed_* marker in the same successor
body_absent   static predicate names (connected, surface, isa, differ,
              standard_mode) that the matched clause must not hold: a
              stated-endpoint path is `availability` of poss(move(...)) with
              body_absent [connected]
confidence    the confidence the matched clause record must carry (the
              evidence 2p - 1 on every path of an uncertain unit)
```

Encoding v2 (2026-09-23): `scoped_route` and `necessity_capability` are
gone with `route_for` and the capability necessities; the patterns that used
them are recorded in `REVIEW.md` (encoding v2 rows).

Pattern terms: an entity id matches that constant; an upper-case letter
matches a clause variable in that slot (any variable, not the source's
letter); a lexical constant matches itself; `["sk", ...]` matches a Skolem
term with exactly those argument slots. So `["route_for", "X", "Haapsalu 3",
"Tallinn 4", "bus"]` under `must_not_have` forbids a route whose actor slot
is a variable and does not match the correct route for `Ann 1`.

`must_not_have` uses the same fields; a pattern there is a defect if any
emitted clause matches it.

## What the expectations are, and are not

- An `expect` on a query is the contract's expected result. It is not a
  claim that any implementation produces it yet (WP02 completion condition).
- A `verdict` on a candidate is the replay's expected result under the
  declared signed stored-state semantics (A2.5, A5.1), not what the starting
  backend does.
- `backend` lists what a backend must have validated before the query may be
  solved. On a backend without it, the expected outcome is
  `unsupported_backend_requirement` with the listed reason, before search.
  The requirement is decided by dependency analysis within the query's
  horizon (REVIEW.md disposition 8): an established negative fact, or a
  negative an action writes, that a later step reads across at least one
  other transition. A negative that is never established, or one read
  directly in the next step, requires nothing.
- `not_found` never means impossible (A5.3). Where a case says `not_found`
  it also says what the replay finds for the false-plan candidate, and names
  `candidate_not_validated` as the alternative when a backend does return
  an eligible candidate.

## Which layer checks what

| property | layer |
|---|---|
| field order, ids, coverage of C01–C28 | `check_fixture_schema.check_record` |
| variant rules, duplicate and dangling ids, query/candidate source changes | `fixture_materialize` |
| completeness of an effective unit (text, Stage-1 projection, Stage-2, scope, syntax, compile) and of an expectation (evidence, answer or outcome) | `check_fixture_schema.check_case` on effective cases |
| Stage-2 grammar (arities, binding, actor agreement, lexical values, no Skolem terms), vocabulary per support status, declared entity ids | `check_fixture_schema.check_formula` and callers |
| query packages, bounds, seeds, views, outcome and reason names, backend names, verdicts | `check_fixture_schema.check_query`, `check_expect`, `check_record` |
| an edited source has its own passage; an override keeps every documented query field; unknown query fields | `fixture_materialize` |
| passage and units agree in both directions; the passage is source-only | `check_fixture_schema.check_passage` |
| the Stage-1 projection holds the concrete entities of the formula and, for an action unit, action_reading and actions | `check_fixture_schema.check_stage1_consumed` |
| a package runs in its view; the seed equals the bound and the cap; an expectation does not forbid its own answer or outcome; a replay reference resolves to a query with a final goal | `check_fixture_schema.check_queries`, `check_seed`, `check_expect`, `check_replay_context` |
| no `clauses.must_have` on an unsupported unit; `inspection` names a known operation | `check_fixture_schema.check_units` |
| that each rejection above is real, and raised by the intended rule (each entry names a fragment of its message) | `check_fixture_mutations` |
| truth of an expectation | a reviewer, recorded in `REVIEW.md` |

## Amending a gold

Only through a row in `REVIEW.md` with the reason. Never because an
implementation produced a different answer (WP02 work item 7).
