# GK clause list

This page defines the clause format submitted to the prover: clause
shape, signs, contexts, defaults, confidence, question clauses,
population clauses and background axioms.

This page is normative.

**Produced by:** logconvert.rawlogic_convert() + lc_post_normalize / lc_post_reify / lc_post_inject passes
**Consumed by:** prover.call_prover() → gk binary

The Stage-2 logic JSON is compiled into a flat list of clause dictionaries in
conjunctive normal form (CNF) suitable for the GK theorem prover.

## Structure

```json
[
  {"@name": "sent_S1", "@logic": ["isa", "elephant", "John 1"]},
  {"@name": "sent_S2", "@logic": [
    ["-isa", "elephant", "?:X"], ["isa", "animal", "?:X"]
  ]},
  {"@name": "sent_S3", "@question": ["isa", "animal", "John 1"]}
]
```

Each dict has exactly one content key:
- `"@logic"` for assertions (facts and rules)
- `"@question"` for the query

## Clause Formats

- **Single atom**: `["pred", arg1, arg2, ...]`
- **Disjunction**: `[["pred1",...], ["pred2",...]]` — represents `pred1 OR pred2`
- **Negated atom**: `["-pred", arg1, ...]` — the `-` prefix negates

A disjunctive clause with negative atoms encodes an implication:
`["-isa","elephant","?:X"], ["isa","animal","?:X"]` means
`isa(elephant,X) => isa(animal,X)`.

## Variables

Any string starting with `?:` is a variable (`"?:X"`, `"?:Fv3"`).  All free
variables in a clause are implicitly universally quantified.  Existential
quantifiers from Stage 2 are eliminated by Skolemization:

- No universal vars in scope → Skolem constant: `"sk0_house"`, `"sk1_car"`, ...
  (type suffix from `isa` in the existential body; plain `"sk0"` if no type found)
- Universal vars in scope → Skolem function: `["sk0", "?:X"]` (plain name, no type suffix)

## The $ctxt Context Term

Eligible predicate atoms are augmented with a trailing context term:

```json
["has property", "tall", "John 1", ["$ctxt", "past", "W0", "?:Fv1", "?:Fv2"]]
```

The four `$ctxt` components:

| Position | Meaning | Source |
|----------|---------|--------|
| 1 (tense) | `"past"`, `"present"`, `"future"`, `"timeless"` | ASU `time` field |
| 2 (world) | `"W0"`, `"W1"`, or free var | ASU `pre_state` |
| 3 (location) | Entity ID or free var | ASU `location` |
| 4 (knower) | Entity ID or free var | Mental holder |

### Tense is relative to the world state

The tense component is interpreted **relative to** the world state, not as an
absolute timestamp:

| $ctxt | Interpretation |
|-------|---------------|
| `$ctxt(present, W0, ...)` | The predicate holds **at** W0 |
| `$ctxt(past, W2, ...)` | The predicate held at some world state **before** W2 |
| `$ctxt(future, W0, ...)` | The predicate will hold at some world state **after** W0 |

Examples:

```json
["have","John 1","apple 2",["$ctxt","present","W0",...]]
```
John has the apple **at** world state W0.

```json
["have","John 1","apple 2",["$ctxt","past","W2",...]]
```
John had the apple at some world state **before** W2.

```json
["have","Mark 3","apple 2",["$ctxt","future","W0",...]]
```
Mark will have the apple at some world state **after** W0.

### World assignment by clause type

**Rules**: all four components are free variables (match any context).

**Assertions**: concrete world/tense from Stage 1.  A clause in a narrative
defaults to `present` at its own world state.

**Questions**: three-way dispatch for worlds:
- Descriptive atoms (isa, event predicates) → each gets its own independent free-var world
- Stative matrix predicates (have, can, has part) → free-var world
- Dynamic matrix predicates (is_rel2, properties as main query) → query's world

Tense for questions: if Stage 1 provides `"time"` (e.g. `"past"` for "Did he run?"),
that tense is used. Otherwise the question defaults to `"present"` — matching the
Stage 1 convention that bare present-tense is the unmarked default. This prevents
tense bridge axioms from leaking historical facts into present-tense queries
(e.g. "Where is John?" should not match a past location via present→past conversion).

### Eligible predicates

Receive `$ctxt`: `has property`, `have`, `has part`, `is rel2`,
`has degree property`, `has degree rel2`, all event role predicates
(`has type`, `has actor`, `has target`, `has time`, `has location`, …).

Do NOT receive `$ctxt`: `isa`, `holds`, `next`, `state *`, `kb *`,
the modal classifiers (`actuality`, `capability`, `typical`,
`necessity`, `obligation`, `volition`, `intention`, `expectation`,
`speech_act`), `@*`, `$*`, `=`, `<`, `>`.

## Defeasible Reasoning ($block)

Normal rules produce defeasible clauses with a `$block` literal.  For
example, "Birds have wings" — a default that admits exceptions — becomes:

```json
["-isa","bird","?:X"], ["has part","?:X","wing", CTXT],
  ["$block", ["$","bird",1], ["$not", ["has part","?:X","wing", CTXT]]]
```

This means: "birds have wings, but this conclusion can be defeated by a more
specific rule."

**Priority mechanism:** The priority `["$","bird",1]` has the form `["$", CLASS, N]`.
GK compares conflicting defaults in two steps:

1. **Taxonomy class specificity.** CLASS names a class in the loaded WordNet
   taxonomy.  A priority naming a more specific class — a descendant in the
   taxonomy — defeats one naming a more general class: `["$","penguin",1]`
   defeats `["$","bird",1]`.
2. **Numeric tie-breaker.** When neither class is a descendant of the other,
   or a name is not in the taxonomy, the numeric components N are compared as
   plain priorities: the larger N defeats the strictly smaller one.  Equal
   values do not defeat each other.

llmpipe derives N as a condition count: a rule with more isa conditions gets a
higher N.  For example:

- "Birds have wings" → priority `["$","bird",1]` (1 isa condition)
- "Plucked birds do not have wings" → priority `["$","bird",2]`
  (isa plucked bird + isa bird)

The full comparison rules, including mixed numeric/taxonomy priorities, are in
the [gkreasoner how_gk_works.md](https://github.com/tammet/gkreasoner/blob/master/Doc/how_gk_works.md).

GK extends the [GKC theorem prover](https://github.com/tammet/gkc) with
[numeric confidences](https://link.springer.com/chapter/10.1007/978-3-030-79876-5_29)
and [defeasible rules](https://link.springer.com/chapter/10.1007/978-3-031-10769-6_18).
See also:
- [GK documentation and examples](https://github.com/tammet/gkreasoner)

## Confidence

Some clause dicts carry `"@confidence": 0.8` (from `@p` metadata).  GK uses
input confidences in its proof-support calculation: derived clauses carry
combined confidences, and positive and negative support for a conclusion are
computed from the retained proofs.  The confidence reported for an answer is
derived from that calculation; ranking answers by it is a later use of the
result.

## Transformations Applied

The pipeline applies several transformations between Stage-2 output and GK input:

**Pre-clausification** (on the raw formula):
- Degree presupposition injection: "not very big" → adds "big" (unmarked)
- Stative event rewriting: event-encoded have/like/own → direct predicates
- `@time` stripping: time wrappers → `$tense` sentinels
- Entity category/base-word isa injection from Stage-1 metadata
- Meta-predicate normalization (lc_rewrites.py): `is_rel2("is",A,B)` → `isa(A,B)`;
  `is_rel2("=",A,B)` → `=(A,B)`;
  `is_rel2("located in/at/on/near/above/under",A,B)` → `is_rel2("in/at/on/near/above/under",A,B)`
- Misnested existential hoisting (lc_rewrites.py, assertion formulas only)
- Spurious `can` removal (lc_rewrites.py, event queries without modal language)

**During clausification** (lc_clausify.py):
- Connective elimination (implies → or, equivalent → and)
- Negation Normal Form (push negations inward)
- Defeasible expansion (normally → $block)
- Skolemization (exists → typed Skolem constants `sk0_house`, plain functions `["sk0","?:X"]`)
- CNF distribution (or over and)

**Post-clausification** (lc_ctxt.py + lc_post_normalize.py + lc_post_reify.py + lc_post_inject.py + lc_post_una.py, on the clause list):
- $ctxt injection with world dispatch (lc_ctxt.py)
- `$theof1` definite function terms and `$measure_of` measurement encoding
  (lc_post_reify.py) — see [the source map](../code/source-map.md) for details.
- Gradable property normalization (lc_post_normalize.py, whitelist-based has property ↔ has degree property)
- isa(entity,X) stripping (lc_post_normalize.py, tautological)
- RELCLASS coercion for question atoms (lc_post_normalize.py)
- Population fact generation (lc_post_normalize.py, synthetic witnesses for rule variables)
- Dynamic axiom injection — verb-result-state bridges (run first so result-
  state words become eligible for the exclusion injector), then soft synonyms,
  exclusions (incl. noun-mutex via `_ISA_EXCL_GROUPS` and gradable adjective
  antonyms via `MANUAL_ADJ_GRAD_*`), cross-group isa-mutex, verb mutex,
  kinship mutex, containment bridge, carrier vocabulary lift, world geometry
  (lc_post_inject.py)
- Set existence fact generation (lc_sets.py, assertion-context `forall/member` patterns)
- Semantic normalization (semnormalize.py, antonym resolution, canonical substitution)
- **Entity UNA wrapping** (lc_post_una.py, last pass): every Stage-1 numbered
  entity (e.g. `"John 1"`, `"table 3"`) gets a `#:` prefix — required by the
  X2 direct-support uniqueness axiom (axioms_std.js §7g) so `gk` treats
  distinct entity constants as definitely unequal. Three-step criterion:
  regex match `^.+ \d+$` AND in Stage-1 entity set AND not Skolem-shaped.
  Skolems, function terms, worlds, and `$some_X` constants are NOT wrapped.
  The `#:` prefix is stripped at proof rendering time.

**Post-prover** (procproofs.py):
- Answer tier filtering (concrete > Skolem > population)
- Tautological population answer filtering
- Proof deduplication (eliminate shadow proofs with same answer + same content sources)

## Entity ISA Injection

The pipeline injects `isa` facts from Stage-1 metadata that Stage-2 may not
have emitted:

**Category isa:** For each concrete entity with a `"category"` field,
`isa(CATEGORY, ENTITY)` is added unless Stage-2 already has a
**positive-polarity** `isa` for that entity (polarity tracked through
connectives, negation, implications, and low-confidence packages).
Entities in negated or low-confidence contexts are not skipped — they
need the injection.  Exact duplicates with content-derived clauses are
removed.  Example: `"John 1"` with `category: "person"` →
`["isa", "person", "John 1"]`.

**Base-word isa:** When a concrete entity's ID has a lowercase base word
different from the category, an additional `isa(BASE, ENTITY)` is injected.
Example: `"man 1"` with `category: "person"` → both
`["isa", "person", "man 1"]` and `["isa", "man", "man 1"]`.
This ensures queries using the descriptive type word ("Who is a man?") can
match even when Stage-2 only emitted `isa(person, ...)`.

**Compound subsumption:** For compound entity types like "baby bird",
a subsumption rule `isa(bird, X) :- isa(baby bird, X)` is generated
so that general bird rules can apply to baby birds.

## Population Facts

For each class mentioned in a forall-quantified rule, synthetic "population"
facts are generated so the prover has witnesses to instantiate:

```json
{"@name": "sent_S1", "@logic": ["isa", "bird", "$some_bird"]}
{"@name": "sent_S1", "@logic": ["-isa", "bird", "$some_not_bird"]}
```

`$some_bird` witnesses that at least one bird exists.
`$some_not_bird` witnesses that at least one non-bird exists.

Population facts are also generated for property predicates:
`["has property", "red", "$some_red_berry"]` witnesses that at least one
red berry exists.

## Question Encoding ($defq)

Complex questions are encoded as biconditional formulas using `$defq` predicates:

```json
{"@name": "sent_S3", "@logic": [
  ["-isa","animal","John 1"],
  ["-has property","red","John 1", ...],
  ["$defq0"]
]}
{"@name": "sent_S3", "@question": ["$defq0"]}
```

The prover derives `$defq0` when all conditions are met, then matches it against
the `@question` entry to produce the answer.

For wh-questions, `$defq` carries the answer variable:
```json
{"@name": "sent_S3", "@question": ["$defq0", "?:X"], "@askvars": 1}
```

**Where/When queries** use 2-arg `$defq` atoms to encode the preposition in the answer:
```json
{"@logic": [["-is rel2","in","John 1","?:Q1",CTXT], ["$defq0","in","?:Q1"]]}
{"@logic": [["-$defq0","in","?:Q1"], ["is rel2","in","John 1","?:Q1",CTXT]]}
...biconditionals for each preposition (in, on, at, near, above, under)...
{"@question": ["$defq0","?:Rel","?:Q1"], "@askvars": 2, "@where_query": true}
```
The prover returns `["$ans", "in", "Paris 1"]` → formatted as "In Paris."
`@when_query` works identically with temporal prepositions.

**Who/What queries** use isa + equality biconditionals sharing one `$defq`:
```json
{"@logic": [["-isa","?:X","John 1"], ["$defq0","?:X"]]}
{"@logic": [["-$defq0","?:X"], ["isa","?:X","John 1"]]}
{"@logic": [["-=","?:X","John 1"], ["$defq0","?:X"]]}
{"@logic": [["-$defq0","?:X"], ["=","?:X","John 1"]]}
{"@question": ["$defq0","?:X"], "@askvars": 1, "@who_query": true,
 "@who_entity": "John 1", "@who_kind": "who"}
```
The prover returns types (`$ans("car")`) and equalities (`$ans("king 2")`).

### `@what_query` — class-preferred answers

General "what" questions (not who/where/when) get `@what_query: true` on the
question object.  This triggers: (1) extra population facts `isa(CLASS, $some_CLASS)`
for classes with concrete witnesses, (2) tier preference inversion (population
over concrete), (3) Skolem function answers resolved to class via `get_skolem_fn_type`.
Result: "What is Emily afraid of?" → "A wolf" instead of "Gertrude".

### Bare-plural-generic yes/no questions — named-Skolem rewrite

For yes/no queries with a bare-plural generic subject ("Cars have trunks?",
"Are cars red?"), Stage-2 [logic compilation](../architecture/logic-compilation.md)(a) instructs the LLM to wrap the consequent
in `["normally", ...]`:

```json
["question",
 ["forall","X",
  ["implies", ["isa","car","X"],
   ["normally", ["exists","Y", ["and", ["isa","trunk","Y"], ["has part","X","Y"]]]]]]]
```

`lc_questions.hoist_generic_yn_subject` detects this shape before the standard
yes/no encoding applies and rewrites it to a UDP-shaped pair:

```json
{"@name": "sent_S3", "@sourcetype": "question_subject",
 "@logic": ["isa","car","skq_S3_car"]}
{"@logic": [["-isa","trunk","?:Y"], ["-has part","skq_S3_car","?:Y", ...],
            ["$defq0"]]}
{"@logic": [["-$defq0"], ["isa","trunk","sk0"]]}
{"@logic": [["-$defq0"], ["has part","skq_S3_car","sk0", ...]]}
{"@question": ["$defq0"]}
```

The skolem constant name is `skq_S<qid>_<class>` (extracted from the question's
`@name` and the antecedent `isa` class), so multiple bare-plural questions in a
problem get distinct constants.  Three-way distinction on the consequent shape
during clausification (no normally → strict universal; existential → John-shortcut;
this rewrite → defeasible-on-fresh-witness) closes cases like 213/214/215
("Red cars do not have trunks. Cars have trunks. Cars have trunks?" → True)
that fail under either of the simpler encodings.

For explicit "all" subjects ("Are all cars red?"), Stage-2 [logic compilation](../architecture/logic-compilation.md)(b) keeps the
strict `forall` shape (no `normally` wrapper), the rewrite does not apply, and
the prover handles it as a true universal.

## GK Input File Format

The clause list is serialized as JSON with `//` comment lines between ASU groups:

```
// Elephants are animals.
{"@logic": [["-isa","elephant","?:X"], ["isa","animal","?:X"]],
 "@name": "sent_S1"},
// John 1 is an elephant.
{"@logic": ["isa","elephant","John 1"],
 "@name": "sent_S2"},
// Is John 1 an animal?
{"@logic": [["-$defq0"], ["isa","animal","John 1"]],
 "@name": "sent_S3"},
...
// [population facts]
{"@logic": ["-isa","elephant","$some_not_elephant"],
 "@name": "sent_S1"},
```

The GK input format is based on
[JSON-LD Logic](https://github.com/tammet/json-ld-logic), a JSON encoding
of first-order logic clauses.  See also:
- [GK input languages by example](https://github.com/tammet/gkreasoner/blob/master/Doc/input_languages.md)
- Tammet, T. and Sutcliffe, G., 2021. Combining JSON-LD with First Order Logic.
  In *2021 IEEE 15th International Conference on Semantic Computing (ICSC)*
  (pp. 256–261). IEEE.

## Background Axioms (axioms_std.js)

The prover also loads `axioms_std.js` containing background knowledge:

- **Taxonomy**: subtype transitivity
- **Part-whole & possession**: has part → have inference
- **Definite function terms**: `$theof1` bridges — generic `have(?:S, $theof1(?:R, ?:S, ?:C), ?:C)`
  plus per-relation `isa` and `is rel2` bridges (generated by lc_post_reify)
- **Degree intensity**: high → none entailment, high/low contradiction
- **Gradable transitivity**: comparative relation chaining
- **Event bridges**: activity + has type + has actor → is rel2 / have
- **Spatial transitivity**: in/inside/located-in chaining (note: `on` is non-transitive — `on(X,Y) ∧ on(Y,Z) → on(X,Z)` is intentionally commented out in axioms_std.js:161; transparent stacking is handled by carrier transparency below)
- **Preposition mutex (`axioms_std.js` §7e)**: opposite preposition pairs are mutually exclusive at `is_rel2` arg 1: (above,below), (over,under), (behind,in_front_of), (inside,outside), (left_of,right_of), (before,after), and asymmetrically (on,under) / (on,below). All strict.
- **Carrier transparency (`axioms_std.js` §7f)**: defeasible (0.85) — `isa(carrier, C) ∧ on(X, C) ∧ on(C, S) → on(X, S)`. Carrier tag injected dynamically per-noun by `inject_carrier_lifts` for nouns in `_CARRIER_NOUNS = {plate, tray, saucer, dish, newspaper, napkin, tablecloth, mat, rug, carpet}`. Handles "pizza on plate, plate on table → pizza on table".
- **Direct-support uniqueness — X2 (`axioms_std.js` §7g)**: strict — `on(X,Y1) ∧ on(X,Y2) → Y1=Y2`, with four `$block` escapes for stacked / part-of configurations. Combined with entity UNA via `#:` (lc_post_una.py), forces contradiction when two distinct Stage-1 entities are claimed as `on`-targets of the same X. Closes case 148 ("pizza on table, ask pizza on floor?" → False).
- **Persistence (frame problem)**: facts persist across world states unless blocked
  (defeasible for `have`, `has property`, `has degree property`, `has part`,
  `is rel2`; variable worlds via `next(?:W, ?:W2)`).  Modal capability is carried
  by the arity-1 `capability(E)` classifier, so its frame propagation lives on
  the event's role atoms, which already participate in the per-predicate frame.
- **Modal classifier bridge ([the source map](../code/source-map.md))**: defeasible actuality→capability — for any
  real Davidsonian event `actuality(E) + has_type(E,V,Ctxt) + has_actor(E,X,Ctxt)`,
  derive `capability(E)` on the SAME event variable, emitted only when one `$block`
  for strict `¬capability(E)` overrides (e.g., "Penguins cannot fly" blocks
  the inferred capability for a penguin event).  Modal events (typical /
  capability / necessity / ...) and inner content events of two-event
  reifications carry no `actuality` marker, so the bridge cannot apply to
  them by construction.
- **Movement axioms**: `has_actor(E,X) + has_type(E,go) + has_destination(E,Dest,Prep) +
  next(W,W2) → is_rel2(at, X, Dest, $ctxt(present, W2, ...))`.  Result tense is
  always "present" at the new world.  The `has_destination` predicate is 4-arg
  with a preposition slot (use `"at"` for plain motion).
- **Placement axioms**: `has_actor(E,X) + has_type(E,put) + has_target(E,Obj) +
  has_destination(E,Dest,Prep) + next(W,W2) → is_rel2(Prep, Obj, Dest,
  $ctxt(present, W2, ...))`.  Mirrors movement results but the **target** ends up
  at the destination (with the spatial preposition preserved from `has_destination`).
- **Movement & placement verb normalization**: the pipeline normalizes
  travel/journey/move → go and place/set/lay/position/deposit → put in
  `lc_rewrites.py` before clausification, avoiding synonym axiom chains in the
  prover that cause combinatorial explosion with many world states.
- **`moved(X,W)` helper**: derived from go-events; blocks `is_rel2` frame axiom
  persistence for entities that moved at world W.
- **Frame axiom blocking**: `is_rel2` persistence uses `$block(moved(X,W))` — if X
  performed a go-event at world W, the old location does not persist to W+1.
  `have` persistence uses `$block(transferred(Obj,W))` — if the object was given
  away at world W, the old owner's possession does not persist to W+1.
  Other predicates (has_property, etc.) use `$block($not(...))` as a general blocker.
- **Transfer axioms**: `has_actor(E,X) + has_type(E,give) + has_recipient(E,Recip) +
  has_target(E,Obj) + next(W,W2) → have(Recip, Obj, $ctxt(present, W2, ...))`.
  Parallels movement axioms: give-event produces `have` in the next world state.
- **`transferred(Obj,W)` helper**: derived from give + target; blocks `have` frame
  axiom persistence for the transferred object, preventing the giver from keeping
  possession after giving it away.
- **Give/receive perspective bridge**: a give-event is also a receive-event
  (`has_type(E,give) → has_type(E,receive)`), and the recipient of the give is the
  actor of the receive.  The reverse direction (receive→give) is handled by pipeline
  normalization in `lc_rewrites.py:normalize_receive_events()` which rewrites
  `has_type(E,"receive")` to `has_type(E,"give")` and swaps actor→recipient.
- **Transfer verb synonyms**: hand/pass/send → give (both axiom-level and pipeline
  normalization in `lc_rewrites.py`).
- **Tense bridge axioms**: convert `present@W_old` → `past@W_new` when
  `before(W_old, W_new)`.  These correctly encode historical facts but must not
  interfere with present-tense queries (ensured by the question tense default).
- **Dynamic question tense bridges**: for each present-tense (or past-tense)
  stative literal in a question's body→defq clause, `logconvert.py` emits a
  per-question bridge axiom of shape:
    ```
    [-pred(args, $ctxt(opposite_tense, ?:W, ...)),
      pred(args, $ctxt(question_tense, ?:W, ...)),
      $block(0, $not(pred(args, $ctxt(question_tense, ?:W, ...))))]
    ```
  Entity arguments are pinned to those mentioned in the question (free variables
  in the question become fresh variables in the bridge), so the bridge only applies
  on past-tense (or present-tense) facts about those specific entities.  This
  avoids the search-space explosion that a global same-world tense bridge would
  cause.  Stative predicates covered: `have`, `has part`, `has property`,
  `has degree property`, `is rel2`, `has degree rel2`.  Built by
  `lc_ctxt.build_question_tense_bridges`.  Capability questions are answered
  via the event's role atoms (which already use these bridges), so the modal
  classifier `capability(E)` does not participate directly.
- **Prover seconds auto-estimation**: `prover.py` counts distinct world constants
  in the clause list and scales the prover time limit accordingly (empirical table
  with 2x safety multiplier).  CLI `-seconds N` overrides the estimate.

## Definite Functions and Measurements

### `$theof1` — definite descriptions

When a Stage-1 ASU has a `definites` entry like `["father of", "father 2", "John 1"]`,
the pipeline replaces the flat entity ID (`"father 2"`) with a canonical function
term throughout all clauses:

```
["$theof1", TYPE, SUBJECT, CTXT]
```

- `TYPE` — attribute name derived from the relation (strip trailing " of")
- `SUBJECT` — the entity the attribute belongs to (e.g., `"John 1"` or a URL)
- `CTXT` — the `$ctxt` term from the clause context (may contain free variables)

Example: "The father of John" → `["$theof1", "father", "John 1", ["$ctxt", ...]]`

Bridge axioms are generated per relation:
```
is_rel2("father of", $theof1("father", ?:S, ?:C), ?:S, ?:C)
isa("father", $theof1("father", ?:S, ?:C))
```

The rewrite runs as a **global pass** (after all packages are collected) so that
question packages can find `is_rel2` matches from assertion packages.

### `$measure_of` and `$measure` — measurement encoding

Stage 2 encodes measurement attributes directly using `$measure_of` and `$measure`:

```
["=", ["$measure_of", ATTR, OBJ, WORLD], ["$measure", NUMBER, UNIT]]
```

- `ATTR` — measurement attribute: `"length"`, `"weight"`, `"height"`, etc.
- `OBJ` — the entity (URL or id)
- `WORLD` — world constant: `"W0"`, `"W1"` — ground, no `$ctxt` wrapper
- `NUMBER` — the numeric value as a JSON number
- `UNIT` — the unit as a string: `"kilometer"`, `"kilogram"`, etc.

The pipeline converts `$measure` to canonical `$list` form for the prover:

```
["$measure", 80, "kilometer"]  →  ["$list", 80000, "#:meter"]
```

**Why `$measure_of` is ground**: The gk prover can decompose `$list` terms for
equality contradiction only when the enclosing function term is fully ground.
`$measure_of` uses the world constant directly (not a `$ctxt` list with free
variables). World constants (`W0`, `W1`, ...) are recognized by `is_world_constant()`
in `lc_clausify.py` and excluded from variable detection.

**Why `$list` with `#:` prefix?**  In gk, integers have the unique name
assumption (UNA): `80000 ≠ 90000`.  Distinct symbols (prefixed with `#:`)
also have UNA: `"#:meter" ≠ "#:kilogram"`.  The `$list` wrapper combines both,
so `["$list", 80000, "#:meter"] ≠ ["$list", 90000, "#:meter"]` (different number)
and `["$list", 80000, "#:meter"] ≠ ["$list", 80000, "#:kilogram"]` (different unit).
Plain strings like `"80 kilometers"` do NOT have UNA in gk.

**Canonical unit conversion**: Values are converted to a base unit so that
different surface forms compare correctly:

| Dimension | Canonical unit | Example conversions |
|-----------|---------------|---------------------|
| Length | `#:meter` | km×1000, mile×1609, foot×0.3048 |
| Mass | `#:kilogram` | g÷1000, pound×0.4536, ton×1000 |
| Time | `#:second` | minute×60, hour×3600, day×86400 |
| Volume | `#:liter` | ml÷1000, gallon×3.785 |
| Temperature | `#:celsius` | fahrenheit→(F-32)×5/9 |

Results are rounded to integer.

**Example 1** — boolean: "Nile's length is 80 km. The length of Nile is 90 km?"

```
Stage 2 assertion: ["=", ["$measure_of","length","Nile","W0"], ["$measure",80,"kilometer"]]
Stage 2 question:  ["question", ["=", ["$measure_of","length","Nile","W0"], ["$measure",90,"kilometer"]]]
GK assertion:      ["=", ["$measure_of","length","Nile","W0"], ["$list",80000,"#:meter"]]
GK question:       ["=", ["$measure_of","length","Nile","W0"], ["$list",90000,"#:meter"]]
```

The `$measure_of` terms unify (ground), `80000 ≠ 90000` → **False**.

**Example 2** — wh-query: "What has the length 20 km?"

```
Stage 2: ["ask","X", ["=", ["$measure_of","length","X","W0"], ["$measure",20,"kilometer"]]]
GK:      ["ask","X", ["=", ["$measure_of","length","X","W0"], ["$list",20000,"#:meter"]]]
```

Cross-unit comparison: "80 kilometers" and "80000 meters" both produce
`["$list", 80000, "#:meter"]` → **True**.

**Bridge axioms** for `$measure_of`:
```
have(?:S, $measure_of(ATTR, ?:S, ?:W), $ctxt(?:T, ?:W, ?:L, ?:K))
isa(ATTR, $measure_of(ATTR, ?:S, ?:W))
```

### `less_measure` — measurement comparison

Comparison operators (`<`, `>`, `<=`, `>=`, `$less`, `$greater`, etc.) on
measurement terms are rewritten to `less_measure` by the pipeline:

| Stage 2 | GK input |
|---------|----------|
| `["<", A, B]` | `["less_measure", A, B]` |
| `[">", A, B]` | `["less_measure", B, A]` |
| `["<=", A, B]` | `["not", ["less_measure", B, A]]` |
| `[">=", A, B]` | `["not", ["less_measure", A, B]]` |

Axioms in `axioms_std.js` bridge between `less_measure` and `$less` on the
numeric components of `$list` values (same unit required).

The prover uses the **unit strategy** (auto-selected) when equalities with
function terms are detected, enabling the equational reasoning needed
for `less_measure` via `$measure_of` equality facts.

---

## Related documentation

- [Stage 2](stage-2.md)
- [Reasoning and proofs](../architecture/reasoning-and-proofs.md)
- [Proof output](../reference/proof-output.md)
