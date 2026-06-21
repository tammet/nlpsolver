# llmpipe — Encoding Reference

This document describes the three main data representations used in the `llmpipe`
pipeline: Stage-1 ASU JSON, Stage-2 logic JSON, and GK prover input.  Each section
explains the encoding, its purpose, and the key features with small examples.

For implementation details see `DOCUMENTATION.md`.

---

## Table of Contents

1. [Stage-1: Atomic Semantic Units (ASU JSON)](#1-stage-1-atomic-semantic-units)
2. [Stage-2: First-Order Logic JSON](#2-stage-2-first-order-logic-json)
3. [GK Prover Input: Clause List](#3-gk-prover-input-clause-list)
4. [End-to-End Example](#4-end-to-end-example)
5. [Simplification Flags](#5-simplification-flags)
6. [Coarse and Ultracoarse Encodings](#6-coarse-and-ultracoarse-encodings)

---

## 1. Stage-1: Atomic Semantic Units

**Produced by:** Stage-1 LLM call (llmparse.py)
**Consumed by:** Stage-2 LLM call and logconvert.py

Stage 1 converts English text into a list of *sentence packages*.  Each sentence
produces one package containing one or more *Atomic Semantic Units* (ASUs) — minimal
propositions that can be independently true or false.

### 1.1 Top-Level Structure

```json
[
  {
    "raw": "Birds can fly, but penguins cannot.",
    "units": [
      { "unit_id": "S1", "text": "Birds can fly.", ... },
      { "unit_id": "S2", "text": "Penguins cannot fly.", ... }
    ]
  }
]
```

Each `"raw"` field contains one original sentence.  The `"units"` array contains
the ASUs derived from it.  Unit IDs are globally unique (`S1`, `S2`, `S3`, ...).

### 1.2 ASU Types

Every ASU has a `"type"` field:

| Type | Meaning | Example |
|------|---------|---------|
| `real` | Timeless fact about a named entity | "Tallinn is a city." |
| `situation` | Concrete event or state in a narrative | "John drove a car." |
| `strict_rule` | Universal definition/law (forall/implies) | "Elephants are animals." |
| `normal_rule` | Defeasible default (normally/typically) | "Birds can fly." |
| `query` | A question | "Is John an animal?" |

### 1.3 Entities

Each ASU lists its entities with type and optional metadata:

```json
"entities": [
  {"id": "John 1", "type": "concrete", "category": "person"},
  {"id": "car 2", "type": "concrete", "category": "artifact"},
  {"id": "animals", "type": "generic"}
]
```

**Concrete** entities are specific instances (numbered: `"John 1"`, `"car 2"`).
**Generic** entities represent classes or kinds (`"animals"`, `"forest"`).

**Entity IDs** follow these rules:
- Famous names: `"John 1"` + optional `"url"` field for Wikipedia disambiguation
- Concrete common nouns: numbered (`"car 2"`, `"dog 1"`)
- Generic: surface phrase without determiners (`"animals"`, `"forest"`)
- Consistency: the same entity keeps the same ID across all ASUs

**Category** (optional): ontological type — `person`, `animal`, `plant`, `place`,
`organization`, `artifact`, `substance`, `event`, `abstract`.

### 1.4 Scope (Generic Entities)

Generic entities may carry a `"scope"` hint:

| Scope | Meaning | Example |
|-------|---------|---------|
| `dependent` | Per-subject existential (default) | "a tail" in "Dogs have a tail" |
| `global` | One shared instance | "a park" in "All children play in a park" |
| `kind` | Uncountable mass substance (constant) | "water", "gold", "air" |

### 1.5 Actions

Physical acts, capabilities, propositional attitudes, and speech acts are
annotated with the `"actions"` field:

```json
"actions": [{"root": "eat", "mode": "habitual", "roles": {"target": "berries"}}]
```

- **root**: base verb in infinitive form (`"eat"` not `"ate"`)
- **mode**: one of nine values — `event` (one-time), `habitual` (regular
  tendency), `capability` (ability: can/could/able), `necessity`
  (must/need/have to), `obligation` (should/ought/supposed to),
  `volition` (want/wish/desire), `intention` (plan/intend/aim/mean to),
  `expectation` (hope/expect/anticipate), `speech_act`
  (tell/say/ask/order/promise)
- **roles** (optional): `target`, `location`, `instrument`, `direction`,
  `manner`, `recipient`, plus `content` for two-event reification (see
  below)

**Mode → Stage-2 classifier.**  Stage-2 attaches an arity-1 classifier
to every Davidsonian event.  The mapping is:

| Stage-1 `mode` | Stage-2 classifier predicate | Source |
|----------------|------------------------------|--------|
| `event` | `actuality` | injected by the pipeline (not Stage 2) |
| `habitual` | `typical` | Stage 2 |
| `capability` | `capability` | Stage 2 |
| `necessity` | `necessity` | Stage 2 |
| `obligation` | `obligation` | Stage 2 |
| `volition` | `volition` | Stage 2 (outer event of two-event reification) |
| `intention` | `intention` | Stage 2 (outer event) |
| `expectation` | `expectation` | Stage 2 (outer event) |
| `speech_act` | `speech_act` | Stage 2 (outer event) |

`event` is the only mode whose classifier is supplied by the pipeline
rather than the LLM — see §2.4 *Modal Classifiers* for the injection
rule.  Inner content events (E2 in a two-event reification) carry no
classifier at all.

**Two-event reification (volition / intention / expectation / speech_act).**
These four modes describe an EXPERIENCER (or speaker) related to an
EMBEDDED event.  Stage-1 emits this as a nested action object in
`roles.content` — option-b inline nesting:

```json
{
  "root": "want",
  "mode": "volition",
  "roles": {
    "actor": "Tom 1",
    "content": {
      "root": "leave",
      "mode": "event",
      "roles": {"actor": "Tom 1"}
    }
  }
}
```

Subject control sets `content.roles.actor` to the experiencer; object
control sets it to the recipient (e.g., "John told Mary to leave" → inner
`actor` is Mary).  Speech-act content events typically take an inner
mode of `obligation` (tell/order/promise) or `event` (say-that-clauses).
The §12 Mental Attitudes infrastructure (`mental_holder` /
`mental_attitude`) is reserved for pure epistemic `knows that` /
`believes that`; all hopes / wants / intends / tells migrate to
`actions[mode=…]`.

Stative verbs (have, own, like, love, fear, know, believe) are NOT
encoded as actions.

### 1.6 Adjectives

All property words are listed in the `"adjectives"` field:

```json
"adjectives": [["tall", "none", "person"], ["red", "none", "none"]]
```

Each entry is `[word, intensity, relclass]`:
- **word**: the adjective (`"tall"`, `"red"`, `"close to"`)
- **intensity**: `"none"` (plain), `"low"` (slightly), `"high"` (very/extremely)
- **relclass**: comparison class (`"person"`, `"car"`) or `"entity"` (generic) or `"none"` (non-gradable like colours)

This field is critical: Stage 2 uses it to decide between `has degree property` and
`has property`.

### 1.7 World States

World states (W0, W1, W2, ...) represent successive states of the world as the
story or situation evolves.  A state change occurs when an event modifies the
situation:

```json
{"unit_id": "S1", "text": "John 1 had an apple 2.",
 "pre_state": "W0", "next_state": "W1"}
{"unit_id": "S2", "text": "John 1 gave the apple 2 to Mike 3.",
 "pre_state": "W1", "next_state": "W2"}
{"unit_id": "S3", "text": "Mike 3 ate the apple 2.",
 "pre_state": "W2", "next_state": "W3"}
```

W0 = before the apple is given, W1 = after the apple is given, W2 = after
the apple is eaten.  World states represent different **versions of the world**,
not merely timestamps.

State changes are triggered by:
- Possession changes (give, buy, sell)
- Location changes (go, arrive, leave, move)
- Physical changes (break, eat, open, close)
- Narrative events that must occur in sequence

Descriptive information (adjectives, relative clauses) does NOT create new states
— "The car is red and expensive" stays in the same world.

### 1.8 Time

#### Relative tense

The `"time"` field on an ASU marks tense **relative to the ASU's world state**:

| Value | Meaning |
|-------|---------|
| `"past"` | The predicate held at some **earlier** world state |
| `"present"` | The predicate holds **at** the current world state |
| `"future"` | The predicate will hold at some **later** world state |
| Omitted | Unmarked present (default for plain present-tense statements and rules) |

For example, if an ASU has `"pre_state": "W2"` and `"time": "past"`, its
predicates describe something that was true before W2 — possibly at W0 or W1.

This relative interpretation is carried through to the `$ctxt` context term in
the GK clause list (see §3.4).

For **Davidsonian events** specifically, when an event's tense diverges from
the ambient ASU tense (most commonly: a past assertion inside an otherwise
present-tense formula), Stage-2 encodes it directly on the event:

```
["has time", "E", "past",    "in"]
["has time", "E", "present", "in"]
["has time", "E", "future",  "in"]
```

The preposition is literally `"in"` for grammatical tenses.  This is the
canonical shape and is preserved through clausification.  Non-Davidsonian
predicates (`have`, `is rel2`, `has part`, `has property`, …) receive
tense through the `$ctxt` mechanism or via the `["@time", TENSE, ATOM]`
wrapper.  See `strip_tense_has_time` in `solver/lc_rewrites.py`.

#### Explicit time values (dated world states)

When the `"time"` field contains an explicit time value like `"1800"` or `"Monday"`
(rather than a grammatical tense), the pipeline treats it as a **dated world state**:

1. Stage 1 produces `"time": "1800"`, `"time_prep": "during"`, `"state_tense": "past"`.
2. `logconvert.py` recognizes the non-grammatical value and:
   - Keeps `$ctxt` tense as `"present"` (facts are current at that time)
   - Generates a world-time equality: `["=", ["$theof1","time","W0","?:C"], ["$datetime", 1800]]`
   - Preserves the event-level `has_time(E, 1800, "during", ...)` from Stage 2
   - Generates `is_past_world(W0)` from `"state_tense": "past"`
3. For numeric values, bridge axioms in `axioms_std.js` also derive `is_past_world(W0)`
   via `$less(1800, 2026)` (redundant backup).  For non-numeric values like `"Monday"`,
   `state_tense` is the only source.
4. Tense normalization axioms promote `$ctxt(present, W0, ...)` to `$ctxt(past, W0, ...)`
   for all predicates, allowing past-tense questions to match.

The `"state_tense"` field carries the grammatical tense (past/present/future) that
`"time"` cannot hold when it contains an explicit value.  It is only set when `"time"`
is a value, never when `"time"` is already a grammatical tense.

### 1.9 Confidence

Float 0–1 representing logical strength.  Omitted when 1.0.

| Source | Confidence |
|--------|-----------|
| Explicit probability ("30%") | 0.3 |
| Usually/normally | 0.98 |
| Often/probably | 0.8 |
| Sometimes | 0.5 |
| Rarely | 0.2 |
| Some/a/an (existential) | 0.99 |

### 1.10 Other Fields

- **`location`**: entity ID of the location — "John ran in the park" → `"location": "park 2"`
- **`mental_holder` / `mental_attitude`**: for propositional attitudes —
  "John knows that Mary is tall" → `"mental_holder": "John 1"`, `"mental_attitude": "knows"`
- **`epistemic_force`**: `"factive"` (knows), `"non_factive"` (believes), `"counterfactual"` (imagines)
- **`definites`**: for definite possessives — "John's sister" →
  `"definites": [["sister of", "sister 2", "John 1"]]`.
  This triggers the `$theof1` rewrite in lc_post_reify: the flat entity ID (`"sister 2"`)
  is replaced by a canonical function term `["$theof1", "sister", "John 1", CTXT]`
  so that all references to "John's sister" unify as the same object (see §3.7).
- **`wh_placeholder`**: `true` on the entity introduced for who/what/where questions —
  `{"id": "entity", "type": "generic", "wh_placeholder": true}`

### 1.11 Complete Stage-1 Example

**Input:** "Bears eat red berries in a forest. John is a bear. Who eats berries?"

```json
[
  {"raw": "Bears eat red berries in a forest.",
   "units": [
     {"unit_id": "S1",
      "text": "Bears eat red berries in a forest.",
      "type": "normal_rule",
      "entities": [
        {"id": "bears", "type": "generic", "category": "animal"},
        {"id": "berries", "type": "generic", "scope": "dependent"},
        {"id": "forest", "type": "generic", "scope": "dependent", "category": "place"}
      ],
      "actions": [{"root": "eat", "mode": "habitual",
                   "roles": {"target": "berries", "location": "forest"}}],
      "adjectives": [["red", "none", "berry"]],
      "confidence": 0.95}
   ]},
  {"raw": "John is a bear.",
   "units": [
     {"unit_id": "S2",
      "text": "John 1 is a bear.",
      "type": "situation",
      "entities": [{"id": "John 1", "type": "concrete", "category": "person"}]}
   ]},
  {"raw": "Who eats berries?",
   "units": [
     {"unit_id": "S3",
      "text": "Which entity eats berries?",
      "type": "query",
      "entities": [
        {"id": "entity", "type": "generic", "wh_placeholder": true},
        {"id": "berries", "type": "generic"}
      ],
      "actions": [{"root": "eat", "mode": "habitual",
                   "roles": {"target": "berries"}}]}
   ]}
]
```

---

## 2. Stage-2: First-Order Logic JSON

**Produced by:** Stage-2 LLM call (llmparse.py)
**Consumed by:** logconvert.rawlogic_convert()

Stage 2 converts each ASU into first-order predicate logic encoded as nested JSON
lists.

### 2.1 Top-Level Structure

```json
["and",
  ["@id", "S1", PACKAGE],
  ["@id", "S2", PACKAGE],
  ...
]
```

Each ASU produces one `["@id", "Sx", PACKAGE]`.

### 2.2 Package Shapes

```
["holds", W, FORMULA]          — assertion anchored to a world constant
["question", FORMULA]           — yes/no question
["ask", VAR, FORMULA]           — wh-question; VAR is the answer variable
["and", PACKAGE, ["@p","Sx",P]] — package with confidence P (0–1)
```

### 2.3 Logical Connectives

```
["and", A, B, ...]     ["or", A, B, ...]      ["xor", A, B]
["not", A]              ["implies", A, B]       ["=", A, B]
["<", A, B]             [">", A, B]
["forall", "X", A]      ["exists", "X", A]
["question", A]         ["ask", "X", A]
```

### 2.4 Predicates

The predicate inventory is a closed whitelist — no invented predicates.

#### Core Predicates

| Predicate | Arguments | Example |
|-----------|-----------|---------|
| `isa` | TYPE, ENTITY | `["isa", "bird", "John 1"]` |
| `has property` | PROP, ENTITY | `["has property", "red", "car 2"]` |
| `have` | OWNER, OWNED | `["have", "John 1", "car 2"]` |
| `has part` | WHOLE, PART | `["has part", "bird 1", "tail 2"]` |
| `is rel2` | REL, E1, E2 | `["is rel2", "near", "A", "B"]` |

Modal information (ability, obligation, intention, …) is NOT a top-level
predicate.  It is carried by arity-1 classifier predicates attached to the
event variable — see the *Event Reification* and *Modal Classifiers* sections
below.

#### Gradable Predicates

Used when the word appears in the ASU's `adjectives` field:

| Predicate | Arguments | Example |
|-----------|-----------|---------|
| `has degree property` | PROP, ENTITY, DEGREE, RELCLASS | `["has degree property", "tall", "John 1", "none", "person"]` |
| `has degree rel2` | REL, E1, E2, DEGREE, RELCLASS | `["has degree rel2", "close to", "A", "B", "high", "city"]` |

DEGREE values: `"none"`, `"high"` (very), `"low"` (slightly), `"more"`, `"most"`, `"less"`, `"least"`.

#### Event Reification Predicates

Dynamic verbs are encoded as Davidsonian events:

```json
["exists", "E", ["and",
  ["isa", "activity", "E"],
  ["has type", "E", "eat"],
  ["has actor", "E", "John 1"],
  ["has target", "E", "berries"],
  ["has time", "E", "past", "in"]
]]
```

| Predicate | Meaning |
|-----------|---------|
| `isa "activity" E` | E is an event |
| `has type E VERB` | Event type (verb root) |
| `has actor E ENTITY` | Who performs the event |
| `has target E ENTITY` | What the event acts on (direct object) |
| `has recipient E ENTITY` | Person receiving (dative: "gave book to Mary") |
| `has destination E ENTITY PREP` | Movement/placement endpoint with preposition. Use "at" for plain motion ("went to the kitchen"); use the spatial preposition for placement ("put on the chair" → "on") |
| `has source E ENTITY` | Movement origin ("came from the office") |
| `has location E ENTITY PREP` | Where the event occurs; PREP is the spatial preposition (`"in"`, `"at"`, `"near"`, etc.) |
| `has instrument E ENTITY` | What tool is used |
| `has manner E MANNER` | How the event is done |
| `has direction E DIR` | Compass or abstract direction ("north", "left") |
| `has time E TIME PREP` | When the event occurs; PREP is the temporal preposition (`"in"`, `"on"`, `"during"`, etc.) |
| `has beneficiary E ENTITY` | Person benefiting ("cooked for Mary") |
| `has accompaniment E ENTITY` | Entity accompanying ("walked with the dog") |
| `has path E ENTITY` | Route taken ("walked through the forest") |
| `has result E ENTITY` | Resulting state ("painted the wall green") |
| `has topic E ENTITY` | Subject matter ("talked about the news") |
| `has cause E ENTITY` | Entity or event causing ("fell because of ice") |
| `has content E1 E2` | Inner event E2 is the content of outer event E1 (two-event reification for volition / intention / expectation / speech_act). World-invariant. |
| `actuality E` | Actuality classifier (arity 1) — marks E as a real / actually-occurring event.  **Pipeline-injected** by `lc_rewrites.inject_actuality`; Stage 2 never emits it.  Hidden from English rendering. |
| `typical E` | Habitual classifier (arity 1) — marks E as a typical/normally-occurring event |
| `capability E` | Capability classifier — marks E as the actor's ability |
| `necessity E` | Necessity classifier (must / need / have to) |
| `obligation E` | Obligation classifier (should / ought / supposed to) |
| `volition E` | Volition classifier (want / wish / desire) — used on outer event of two-event reification |
| `intention E` | Intention classifier (plan / intend / aim) — outer event of two-event reification |
| `expectation E` | Expectation classifier (hope / expect / anticipate) — outer event of two-event reification |
| `speech_act E` | Speech-act classifier (tell / say / ask / order / promise) — outer event of two-event reification |

All nine modal classifiers are **arity 1**: they mark the event variable
intrinsically.  World, tense, location, and KB information lives on the
event's role atoms (`has_time`, `has_location`, etc.) which do carry a
`$ctxt` term.  Exactly one classifier attaches to each Davidsonian event:
Stage 2 emits one of the eight modal classifiers when the event is
non-actual; for actual events Stage 2 emits nothing and the pipeline
injects `actuality`.  Inner content events (E2 in two-event reification)
carry no classifier.  See `axioms_std.js` §5.1 for the defeasible
actuality→capability bridge.


#### Structural Predicates

```
["holds", W, F]                — anchor formula F to world state W
["next", W1, W2]               — W2 is the immediate successor of W1
["before", W1, W2]             — W1 is an earlier world state than W2
["=", ["$theof1","time",W,C], ["$datetime",N]]  — world W anchored to time N (numeric)
["=", ["$measure_of",ATTR,OBJ,W], ["$measure",N,UNIT]]  — measurement (see §3.13)
["state location", W, L]       — location in world state
["normally", F]                — defeasible wrapper
["@time", TIME, ATOM]          — per-predicate time override
["@id", "Sx", F]               — ASU traceability
["@p", "Sx", P]                — confidence annotation
```

Note: `next` is generated by Stage 2 from `next_state` annotations.  `before` is
NOT generated by Stage 2 — it is derived by background axioms in `axioms_std.js`
(e.g., `next(W0,W1) => before(W0,W1)` and transitivity of `before`).

#### Set and Counting Predicates

Stage-2 uses `$setof` to define sets and `$count` for cardinality:

**Stage-2 lambda forms** (what the LLM produces):

```
// Anchored (set owned by a subject — no set id needed):
["$setof", "?:X", ["and", ["isa","car","?:X"], ["prop","red","?:X"], ["have","John 1","?:X"]]]

// Conditions-only (no subject — set id from Stage-1):
["$setof", "?:X", "set 1", ["and", ["isa","elephant","?:X"], ["prop","red","?:X"]]]
```

**Count assertion**: `["=", 3, ["$count", SETOF_TERM]]`

**Distributive actions** over set members:
```
["forall", "?:M",
  ["implies", ["member", "?:M", SETOF_TERM],
    ["exists", "E", [...event body using ?:M...]]]]
```

**Canonical forms** (after programmatic conversion by `lc_sets.py`):

```
// Anchored: anchor predicate extracted, conditions $-prefixed, $arg1 replaces VAR
["$setof", "have", "John 1", ["$and", ["$isa","car","$arg1"], ["$prop","red","$arg1"]]]

// Conditions-only: "id" marker, set_id preserved, no $ prefix
["$setof", "id", "set 1", ["$and", ["isa","elephant","$arg1"], ["prop","red","$arg1"]]]
```

The `$and` arguments are always sorted: `$isa`/`isa` entries first, then
remaining sorted alphabetically.

The conversion also generates:
- **Membership axioms**: `member(M, $setof(...)) <=> conditions(M)` (one per unique pattern)
- **Element instantiation**: concrete individuals `$setK_elI` with all
  set properties, membership, and pairwise distinctness (up to configurable limit)

### 2.5 Quantification Patterns

**Strict rules** use `forall` + `implies`:

```json
["forall", "X", ["implies", ["isa", "elephant", "X"], ["isa", "animal", "X"]]]
```

"Elephants are animals."

**Normal rules** wrap the consequent in `normally`:

```json
["forall", "X", ["implies", ["isa", "bird", "X"],
  ["normally",
    ["exists", "E", ["and",
      ["isa", "activity", "E"],
      ["has type", "E", "fly"],
      ["has actor", "E", "X"],
      ["capability", "E"]]]]]]
```

"Birds can fly." — capability events are reified with the arity-1
`capability` classifier.

**Situations** use concrete constants:

```json
["holds", "W0", ["isa", "person", "John 1"]]
```

"John is a person."

**Yes/no questions** use `question`:

```json
["question", ["isa", "animal", "John 1"]]
```

"Is John an animal?"

**Wh-questions** use `ask`:

```json
["ask", "X", ["and", ["isa", "animal", "X"], ["has property", "big", "X"]]]
```

"Who is a big animal?"

### 2.6 Variable Conventions

| Role | Names |
|------|-------|
| Entity | X, Y, Z, X1, Y1 |
| Event | E, E1, E2 |
| Set | S, S1, S2 |
| Count | N |
| Scalar | V |

Variables must always be introduced by a quantifier (`forall` or `exists`) and
used within its scope.

### 2.7 Complete Stage-2 Examples

**"Birds can fly."** (normal_rule, capability — the `capability`
classifier marks the event as an ability rather than an actuality):

```json
["and",
  ["@id","S1",
    ["holds","W0",
      ["forall","X",
        ["implies", ["isa","bird","X"],
          ["normally",
            ["exists","E", ["and",
              ["isa","activity","E"],
              ["has type","E","fly"],
              ["has actor","E","X"],
              ["capability","E"]]]]]]]]]
```

**"John smiled."** (situation, event):

```json
["and",
  ["@id","S1",
    ["and",
      ["holds","W0",
        ["exists","E", ["and",
          ["isa","activity","E"],
          ["has type","E","smile"],
          ["has actor","E","John 1"],
          ["has time","E","past","in"]]]],
      ["next","W0","W1"]]]]
```

(The pipeline injects `["actuality", "E"]` as the last conjunct here —
see §2.4 *Modal Classifiers* — so Stage 2 does not emit it.)

**"Bears eat red berries in a forest."** (normal_rule, habitual, Track 2 with roles):

```json
["and",
  ["@id","S1",
    ["and",
      ["holds","W0",
        ["forall","X",
          ["implies", ["isa","bear","X"],
            ["normally",
              ["exists","E", ["and",
                ["isa","activity","E"],
                ["has type","E","eat"],
                ["has actor","E","X"],
                ["exists","Y", ["and",
                  ["isa","berry","Y"],
                  ["has degree property","red","Y","none","berry"],
                  ["has target","E","Y"]]],
                ["exists","Z", ["and",
                  ["isa","forest","Z"],
                  ["has location","E","Z","in"]]],
                ["typical","E"]]]]]]],
      ["@p","S1",0.95]]]]
```

**"Who is tall?"** (query, wh-question):

```json
["and",
  ["@id","S1",
    ["ask","X",
      ["has degree property","tall","X","none","entity"]]]]
```

**"The man had the car. The car was red."** (two situations with state):

```json
["and",
  ["@id","S1",
    ["holds","W0",
      ["and",
        ["isa","man","man 1"],
        ["isa","car","car 2"],
        ["have","man 1","car 2"]]]],
  ["@id","S2",
    ["holds","W0",
      ["and",
        ["isa","car","car 2"],
        ["has property","red","car 2"]]]]]
```

---

## 3. GK Prover Input: Clause List

**Produced by:** logconvert.rawlogic_convert() + lc_post_normalize / lc_post_reify / lc_post_inject passes
**Consumed by:** prover.call_prover() → gk binary

The Stage-2 logic JSON is compiled into a flat list of clause dictionaries in
conjunctive normal form (CNF) suitable for the GK theorem prover.

### 3.1 Structure

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

### 3.2 Clause Formats

- **Single atom**: `["pred", arg1, arg2, ...]`
- **Disjunction**: `[["pred1",...], ["pred2",...]]` — represents `pred1 OR pred2`
- **Negated atom**: `["-pred", arg1, ...]` — the `-` prefix negates

A disjunctive clause with negative atoms encodes an implication:
`["-isa","elephant","?:X"], ["isa","animal","?:X"]` means
`isa(elephant,X) => isa(animal,X)`.

### 3.3 Variables

Any string starting with `?:` is a variable (`"?:X"`, `"?:Fv3"`).  All free
variables in a clause are implicitly universally quantified.  Existential
quantifiers from Stage 2 are eliminated by Skolemization:

- No universal vars in scope → Skolem constant: `"sk0_house"`, `"sk1_car"`, ...
  (type suffix from `isa` in the existential body; plain `"sk0"` if no type found)
- Universal vars in scope → Skolem function: `["sk0", "?:X"]` (plain name, no type suffix)

### 3.4 The $ctxt Context Term

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

#### Tense is relative to the world state

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

#### World assignment by clause type

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

#### Eligible predicates

Receive `$ctxt`: `has property`, `have`, `has part`, `is rel2`,
`has degree property`, `has degree rel2`, all event role predicates
(`has type`, `has actor`, `has target`, `has time`, `has location`, …).

Do NOT receive `$ctxt`: `isa`, `holds`, `next`, `state *`, `kb *`,
the modal classifiers (`actuality`, `capability`, `typical`,
`necessity`, `obligation`, `volition`, `intention`, `expectation`,
`speech_act`), `@*`, `$*`, `=`, `<`, `>`.

### 3.5 Defeasible Reasoning ($block)

Normal rules produce defeasible clauses with a `$block` literal.  For
example, "Birds have wings" — a default that admits exceptions — becomes:

```json
["-isa","bird","?:X"], ["has part","?:X","wing", CTXT],
  ["$block", ["$","bird",1], ["$not", ["has part","?:X","wing", CTXT]]]
```

This means: "birds have wings, but this conclusion can be defeated by a more
specific rule."

**Priority mechanism:** The priority `["$","bird",1]` has the form `["$", CLASS, N]`
where CLASS is the subject class and N is a specificity count.  A rule with more
conditions gets a higher N.  For example:

- "Birds have wings" → priority `["$","bird",1]` (1 isa condition)
- "Plucked birds do not have wings" → priority `["$","bird",2]`
  (isa plucked bird + isa bird = more specific)

When the prover finds conflicting conclusions for the same head atom, the rule
with higher N wins — the exception overrides the general default.  This implements
the specificity preference in defeasible reasoning.

GK extends the [GKC theorem prover](https://logictools.org/gk/) with
[numeric confidences](https://link.springer.com/chapter/10.1007/978-3-030-79876-5_29)
and [defeasible rules](https://link.springer.com/chapter/10.1007/978-3-031-10769-6_18).
See also:
- [Confidence and defeasible reasoning examples](http://logictools.org/confer/)
- [GK tutorial](https://logictools.org/gk/tutorial.html)

### 3.6 Confidence

Some clause dicts carry `"@confidence": 0.8` (from `@p` metadata).  The prover
uses this to rank answers by certainty.

### 3.7 Transformations Applied

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
  (lc_post_reify.py) — see §3.13 for details.
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

### 3.8 Entity ISA Injection

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

### 3.9 Population Facts

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

### 3.10 Question Encoding ($defq)

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

#### `@what_query` — class-preferred answers

General "what" questions (not who/where/when) get `@what_query: true` on the
question object.  This triggers: (1) extra population facts `isa(CLASS, $some_CLASS)`
for classes with concrete witnesses, (2) tier preference inversion (population
over concrete), (3) Skolem function answers resolved to class via `get_skolem_fn_type`.
Result: "What is Emily afraid of?" → "A wolf" instead of "Gertrude".

#### Bare-plural-generic yes/no questions — named-Skolem rewrite

For yes/no queries with a bare-plural generic subject ("Cars have trunks?",
"Are cars red?"), Stage-2 §7.4(a) instructs the LLM to wrap the consequent
in `["normally", ...]`:

```json
["question",
 ["forall","X",
  ["implies", ["isa","car","X"],
   ["normally", ["exists","Y", ["and", ["isa","trunk","Y"], ["has part","X","Y"]]]]]]]
```

`lc_questions.hoist_generic_yn_subject` detects this shape before the standard
yes/no encoding fires and rewrites it to a UDP-shaped pair:

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

For explicit "all" subjects ("Are all cars red?"), Stage-2 §7.4(b) keeps the
strict `forall` shape (no `normally` wrapper), the rewrite does not fire, and
the prover handles it as a true universal.

### 3.11 GK Input File Format

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
- [JSON-LD Logic specification and examples](https://logictools.org/json.html)
- Tammet, T. and Sutcliffe, G., 2021. Combining JSON-LD with First Order Logic.
  In *2021 IEEE 15th International Conference on Semantic Computing (ICSC)*
  (pp. 256–261). IEEE.

### 3.12 Background Axioms (axioms_std.js)

The prover also loads `axioms_std.js` containing background knowledge:

- **Taxonomy**: subtype transitivity
- **Part-whole & possession**: has part → have inference
- **Definite function terms**: `$theof1` bridges — generic `have(?:S, $theof1(?:R, ?:S, ?:C), ?:C)`
  plus per-relation `isa` and `is rel2` bridges (generated by lc_post_reify)
- **Degree intensity**: high → none entailment, high/low contradiction
- **Gradable transitivity**: comparative relation chaining
- **Event bridges**: activity + has type + has actor → is rel2 / have
- **Spatial transitivity**: in/inside/located-in chaining (note: `on` is non-transitive — `on(X,Y) ∧ on(Y,Z) → on(X,Z)` is intentionally commented out in axioms_std.js:161; transparent stacking is handled by carrier transparency below)
- **Preposition mutex (§7e)**: opposite preposition pairs are mutually exclusive at `is_rel2` arg 1: (above,below), (over,under), (behind,in_front_of), (inside,outside), (left_of,right_of), (before,after), and asymmetrically (on,under) / (on,below). All strict.
- **Carrier transparency (§7f)**: defeasible (0.85) — `isa(carrier, C) ∧ on(X, C) ∧ on(C, S) → on(X, S)`. Carrier tag injected dynamically per-noun by `inject_carrier_lifts` for nouns in `_CARRIER_NOUNS = {plate, tray, saucer, dish, newspaper, napkin, tablecloth, mat, rug, carpet}`. Handles "pizza on plate, plate on table → pizza on table".
- **Direct-support uniqueness — X2 (§7g)**: strict — `on(X,Y1) ∧ on(X,Y2) → Y1=Y2`, with four `$block` escapes for stacked / part-of configurations. Combined with entity UNA via `#:` (lc_post_una.py), forces contradiction when two distinct Stage-1 entities are claimed as `on`-targets of the same X. Closes case 148 ("pizza on table, ask pizza on floor?" → False).
- **Persistence (frame problem)**: facts persist across world states unless blocked
  (defeasible for `have`, `has property`, `has degree property`, `has part`,
  `is rel2`; variable worlds via `next(?:W, ?:W2)`).  Modal capability is carried
  by the arity-1 `capability(E)` classifier, so its frame propagation lives on
  the event's role atoms, which already participate in the per-predicate frame.
- **Modal classifier bridge (§5.1)**: defeasible actuality→capability — for any
  real Davidsonian event `actuality(E) + has_type(E,V,Ctxt) + has_actor(E,X,Ctxt)`,
  derive `capability(E)` on the SAME event variable, gated by one `$block`
  for strict `¬capability(E)` overrides (e.g., "Penguins cannot fly" blocks
  the inferred capability for a penguin event).  Modal events (typical /
  capability / necessity / ...) and inner content events of two-event
  reifications carry no `actuality` marker, so the bridge cannot fire on
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
  in the question become fresh variables in the bridge), so the bridge only fires
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

### 3.13 Definite Functions and Measurements

#### `$theof1` — definite descriptions

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

#### `$measure_of` and `$measure` — measurement encoding

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

#### `less_measure` — measurement comparison

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

## 4. End-to-End Example

**Input:** "Elephants are animals. John is an elephant. Is John an animal?"

### Stage 1 Output

```json
[
  {"raw": "Elephants are animals.",
   "units": [{"unit_id": "S1", "text": "Elephants are animals.",
              "type": "strict_rule",
              "entities": [{"id":"elephants","type":"generic","category":"animal"},
                           {"id":"animals","type":"generic","category":"animal"}]}]},
  {"raw": "John is an elephant.",
   "units": [{"unit_id": "S2", "text": "John 1 is an elephant.",
              "type": "situation",
              "entities": [{"id":"John 1","type":"concrete","category":"person"}]}]},
  {"raw": "Is John an animal?",
   "units": [{"unit_id": "S3", "text": "Is John 1 an animal?",
              "type": "query",
              "entities": [{"id":"John 1","type":"concrete","category":"person"}]}]}
]
```

### Stage 2 Output

```json
["and",
  ["@id","S1", ["holds","W0",
    ["forall","X", ["implies", ["isa","elephant","X"], ["isa","animal","X"]]]]],
  ["@id","S2", ["holds","W0", ["isa","elephant","John 1"]]],
  ["@id","S3", ["question", ["isa","animal","John 1"]]]
]
```

### GK Input (after logconvert)

```json
[
// Elephants are animals.
{"@logic": [["-isa","elephant","?:X"], ["isa","animal","?:X"]],
 "@name": "sent_S1"},
// John 1 is an elephant.
{"@logic": ["isa","elephant","John 1"],
 "@name": "sent_S2"},
// Is John 1 an animal?
{"@logic": [["-$defq0"], ["isa","animal","John 1"]],
 "@name": "sent_S3"},
{"@logic": [["-isa","animal","John 1"], ["$defq0"]],
 "@name": "sent_S3"},
// [population facts]
{"@logic": ["-isa","elephant","$some_not_elephant"],
 "@name": "sent_S1"},
{"@logic": ["isa","animal","$some_animal"],
 "@name": "sent_S1"},
{"@logic": ["-isa","animal","$some_not_animal"],
 "@name": "sent_S1"},
// Is John 1 an animal?
{"@question": ["$defq0"],
 "@name": "sent_S3"}
]
```

### Answer

```
True.
```

The prover derives `isa(animal, John 1)` from the rule
(`isa(elephant,X) => isa(animal,X)`) and the fact (`isa(elephant, John 1)`),
which satisfies the `$defq0` biconditional, confirming the answer.

---

## 5. Simplification Flags

The flags `-nocontext`, `-noexceptions`, `-simpleproperties`, and `-simple` produce
progressively simplified encodings.  `-simple` enables all three.

### 5.1 `-nocontext`

Replaces the `$ctxt(tense, world, loc, know)` term with a constant `"$c"` in every
predicate atom that normally receives context (§3.4).

```
Default:    has_degree_property(big, cat_1, none, cat, $ctxt(present, W0, ?:Fv1, ?:Fv2))
-nocontext: has_degree_property(big, cat_1, none, cat, "$c")
```

Axioms in `axioms_std.js` that use `?:Ctxt` as a pass-through variable still unify
(binding `?:Ctxt` to `"$c"`).  Axioms that destructure the context — frame axioms,
tense bridges, movement/transfer results — do not unify with `"$c"` and become inert.
This means world-state persistence and tense reasoning are disabled, but all
context-agnostic axioms (taxonomy, transitivity, bridges, synonyms) remain active.

### 5.2 `-noexceptions`

Strips `$block` literals from defeasible rules produced by `normally` quantifiers
during clausification.  Rules that were defeasible become strict universal rules.

```
Default:      [-isa(bird,X), can(X,fly,CTXT), $block(["$",bird,1], $not(can(X,fly,CTXT)))]
-noexceptions: [-isa(bird,X), can(X,fly,CTXT)]
```

Only affects clauses derived from the input text.  Axiom-side `$block` literals
(in `axioms_std.js` frame axioms, etc.) are unaffected.  The `@confidence` field
is preserved.

### 5.3 `-simpleproperties`

Converts degree predicates to their non-gradable equivalents, dropping degree and
relclass arguments while preserving the context argument:

```
has_degree_property(big, cat_1, none, cat, CTX) → has_property(big, cat_1, CTX)
has_degree_rel2(taller, John, Mary, none, person, CTX) → is_rel2(taller, John, Mary, CTX)
```

Also implies `-noexceptions`.

### 5.4 `-simple`

Combines all three: `-nocontext` + `-noexceptions` + `-simpleproperties`.

```
Default: has_degree_property(big, cat_1, none, cat, $ctxt(present, W0, ?:Fv1, ?:Fv2))
-simple: has_property(big, cat_1, "$c")
```

---

## 6. Coarse and Ultracoarse Encodings

The flags `-coarse` and `-ultracoarse` produce progressively flatter event encodings,
built for deductive benchmarks (FOLIO) whose gold logic uses atomic n-ary relations
rather than reified Davidsonian events.  `-ultracoarse` implies `-coarse` and
`-simpleproperties`.  Both are post-LLM: Stage 1 and Stage 2 are unchanged; the folds
run inside `logconvert` (machinery reference: DOCUMENTATION.md §11).

### 6.1 `-coarse`: the flat `do` literal

A *collapsible* Davidsonian event is replaced by one combined literal

```
do(TYPE, ACTOR, TARGET, RECIPIENT)
```

with `"none"` filling absent roles.  The event variable and its `exists` wrapper
disappear; `$ctxt` is attached to `do` exactly as it would be to the reified roles, so
tense survives:

```
Default:  exists E. isa(activity,E) ∧ has_type(E,feed) ∧ has_actor(E,"John 1")
                  ∧ has_target(E,"dog 2") ∧ has_time(E,past,in) ∧ actuality(E)
-coarse:  do(feed, "John 1", "dog 2", none, $ctxt(past, W0, ?:Fv1, ?:Fv2))
```

Collapsible means: no modal classifier (`capability`, `necessity`, …, including
`typical`), not part of a `has_content` two-event reification, and only template
roles `{type, actor, target, recipient}` (a tense-valued `has_time` is tolerated and
moved to `$ctxt`).  Anything else — an instrument, a location, an explicit time, a
modal — keeps the event reified, so the two shapes coexist in one clause set.

### 6.2 `-ultracoarse`: relational folds

Everything `-coarse` does, plus aggressive folds that produce FOLIO-style binary
atoms.  An event with an actor and exactly one object role
(`target`/`beneficiary`/`source`/`recipient`) becomes a binary relation; an event
with an actor and no object becomes a unary property:

```
"Real Madrid signed Mbappe":   is_rel2(sign, "Real Madrid 1", "Mbappe 2", CTX)
"The good guys always win":    has_property(win, ?:X, CTX)
```

Further fold rules:
- **Habituals fold.**  The `typical` classifier no longer blocks folding; it is
  stripped, so "X plays for Y" in a rule and in the question reduce to the same
  `is_rel2(play, X, Y)` literal.  Other modal classifiers still block.
- **Topic fold:** actor + `has_topic`, no object role → `is_rel2(verb, actor, topic)`
  ("jokes about caffeine").
- **Passive fold:** target but no actor → `has_property(verb, target)`, dropping a
  `from`/`at` adjunct ("X was suspended from Y" → `has_property(suspend, X)`).
- **Two-event reifications** fold the inner content event to its verb:
  "X wants to fly" → `is_rel2(want, X, fly)`.
- **Rule antecedents** fold too: an event introduced as bare conjuncts under `forall`
  (no `exists` wrapper) is folded in place, so the rule's literal unifies with the
  folded fact.
- **Degree collapse:** `has_degree_*` literals collapse to `is_rel2`/`has_property`
  early (the `-simpleproperties` transformation, applied pre-clausification).

### 6.3 `-ultracoarse`: guard dropping and predicate unification

- **Redundant guards:** in a rule antecedent, an `isa(T,V)` guard is dropped when `V`
  is already bound by a folded `is_rel2`/`do` literal in the same antecedent, or when
  `T` is a near-universal type (`thing`, `object`, `entity`, …).  A lone
  universal-type antecedent (`"a thing is either A or B"`) drops entirely.
- **Class-name case folding:** the class argument of every `isa` is lowercased
  ("American national" and "american national" become one predicate).
- **Entity-constant canonicalization:** proper-noun entities whose ids differ by
  wording variants ("Summer Olympics" / "2008 Summer Olympics", typo-level edits)
  are merged to one constant — both at the Stage-1 level (id remapping) and at the
  tree level; Stage-2 Wikipedia-URL constants are folded into the matching Stage-1
  entity id.  Indefinites (`bear 1` / `bear 2`) are never merged.
- **Name-as-type:** a multiword proper name is also typed by its own lowercased name
  (`isa("winter olympics", "Winter Olympics 1")`), so a generic existential can bind
  to the named constant.
- **Extra typing facts:** broad supertypes `isa(person/animal, E)` are emitted even
  when Stage 2 already typed the entity with a subtype; gendered role nouns
  (gentleman, actress, …) get `isa(noun,X) → isa(man/woman,X)` axioms; a known first
  name adds `isa(man/woman, E)` directly.
- **Compound suffix subsumption** extends to every attested intermediate word-suffix
  ("American professional basketball player" → "professional basketball player",
  not just → "player"), and also scans entity-category clauses.
- **Antonym folding** (semantic normalisation) only fires when the target word occurs
  in the problem ∪ axiom vocabulary, so it never rewrites into a predicate nothing
  else mentions.
- **`$theof1` reification is skipped** — definites stay plain relations, matching
  FOLIO's atomic style (under plain `-coarse`, reification runs, with named-subject
  identity clauses `= (N, $theof1(R,B))` added and strict placeholder-only matching).
- **`$ctxt` decoupling:** as the LAST pass, every `$ctxt` term is replaced by its own
  fresh variable, so no two atoms are forced to share tense/world (FOLIO is
  timeless).  This makes `-ultracoarse` strictly more permissive than the default
  shared-context encoding.
- **`$setof` labels** become content-derived hashes (`set_3fa2c1d0`) instead of
  per-occurrence counters, so structurally identical sets in a rule and a fact unify.

### 6.4 `-ultracoarse`: dynamic bridge axioms

Emitted into the clause list when (and only when) both sides of the bridge occur in
the problem:

| axiom | shape |
|---|---|
| relation ↔ event | `is_rel2(V,A,O) ↔ ∃E. isa(activity,E) ∧ has_type(E,V) ∧ has_actor(E,A) ∧ has_target(E,O)` (Skolem `$ev_of(V,A,O)`) — a folded relation and a still-reified event of the same verb interderive |
| occasion co-location | `is_rel2(P,Occ,Place) ∧ has_location(E,Place,P) ∧ isa(place-class,Place) → has_location(E,Occ,P)` for P ∈ {in,on,at,near} ("won medals IN Tokyo" + "Olympics IN Tokyo" → "won medals IN the Olympics") |
| containment → part | `is_rel2("in",X,Y) → has_part(Y,X)` |
| reflexive ↔ property | `has_property(P,X) ↔ is_rel2(P,X,X)` for predicates appearing in both shapes |

### 6.5 What stays shared with the default encoding

Two recent changes apply on every path, not just the coarse ones: Stage-1/Stage-2
parses are transliterated to plain ASCII before clausification (accented entity names
otherwise crash the prover-output decoding), and corrective sanity-retry prompts are
serialized canonically (sorted keys and issue order) so their LLM-cache keys are
byte-stable across runs.

### 6.6 Separable abstraction buckets

`-ultracoarse` bundles several independent modifications.  Each is also available on its
own — composable, and each is implied by `-ultracoarse` — so an experiment can isolate one
lever and measure it (this is how the per-mechanism tables in the LPAR paper are produced):

| flag | isolates |
|---|---|
| `-flatevents` | only the relational event flattening (event → `is_rel2`/`has_property`, eventprop-tagged), with none of the other ultracoarse mods |
| `-entitymerge` | proper-noun entity canonicalization + set-label coreference (§6.3) |
| `-typeenrich` | taxonomy/`isa` enrichment: broad supertypes, gender-from-name, name-as-type, gendered-noun bridges, compound subsumption, plural→singular class normalization |
| `-guarddrop` | drop redundant antecedent `isa` type guards (no-op without `-flatevents`) |
| `-bridges` | the dynamic frame/bridge axioms of §6.4 (use with `-flatevents`) |
| `-definites` | ultracoarse definite-description handling (`$theof1` identities) |

`-flatevents` is the lossy relational fold (the same one `-ultracoarse2` uses, §6.9) in
isolation; it drops the event variable and keeps only subject + one (role-tagged) object,
so secondary roles and adjuncts are lost.  `-guarddrop` and `-bridges` are no-ops without it.

### 6.7 `-davidson`: structure-preserving compact Davidsonian fold

Unlike the lossy `-flatevents`/`-ultracoarse` fold, `-davidson` keeps the event handle and
every adjunct.  It collapses only the event *spine* —
`isa(activity,E) ∧ has_type(E,V) ∧ has_actor(E,A) ∧ has_<patient>(E,O)` — into one atom

```
event(V, A, O, E)
```

and leaves all other roles, adjuncts, classifiers and context literals on `E`.

- **Patient (object) slot.**  Only theme roles fill the third argument: the first present of
  `has target`, `has goal`, `has topic`.  Datives (`has recipient`, `has beneficiary`) and
  obliques (location, source, direction, instrument, accompaniment, destination) are never
  placed there — they stay as `has_<role>(E,…)` adjuncts.  The slot carries no functional
  tag; it is purely positional, and the bridge reads it back as `has target` (which is why
  only themes may fill it — a recipient there would be mislabelled and collide with a kept
  `has target`).
- **Missing arguments.**  An absent agent (passive) or patient (intransitive/omitted) becomes
  a fresh existential wrapped in `exists`.
- **Bridge (`frm_event`).**  A biconditional interderives the folded atom with the
  neo-Davidsonian role literals the rest of the pipeline reads:
  `event(V,A,O,E) ↔ isa(activity,E) ∧ has_type(E,V) ∧ has_actor(E,A) ∧ has_target(E,O)`,
  plus a forward projection `event(V,A,O,E) → is_rel2(V,A,O)` for same-verb interop.

Because the spine fold removes role literals from the verbose default representation,
`-davidson` typically **shortens** proofs on the standard encoding (both nlft and default
FOLIO); stacked on the already-flat `-ultracoarse2` baseline it instead **lengthens** them,
since that baseline is more compact than `event(...) + handle + adjuncts + bridge`.

### 6.8 `-existfold`: existential-attribute collapse

Folds a bare existential attribute pattern

```
∃Y. isa(C,Y) ∧ has_part(X,Y)        (or have(X,Y))
```

into one unary attribute `has_property([$has_part, C], X)` (or `[$have, C]`), deleting the
Skolem witness and the cross-product it would create when the pattern recurs.  A generic
**bidirectional** bridge restores the existential on demand, using a named canonical witness
`$typed_partof(X,C)` — one per `(X,C)`, shared by all consumers, so no branching:

- reverse: `isa(C,Y) ∧ has_part(X,Y) → has_property([$has_part,C], X)` — any witness feeds the property;
- forward: `has_property([$has_part,C], X) → isa(C, $typed_partof(X,C)) ∧ has_part(X, $typed_partof(X,C))`.

It is narrow and parse-dependent: it matches only the bare `has-a` shape and is not a default
setting.  Its main effect is on chains where a `has legs → jumps → …` existential would
otherwise be carried (with a fresh Skolem) through several rules.

### 6.9 `-ultracoarse2`: role-tagged relational fold

Identical to `-ultracoarse` except the relational event fold tags the object with its role,
so a target is never confused with an instrument or location:

```
is_rel2(V, subj, ["eventprop", $role, value])
```

The `$role` label is `$`-prefixed so it is a meta-token (content-word extractors skip it,
keeping the role from leaking into the vocabulary as a spurious noun).  This is the baseline
used for the maximally-abstracted FOLIO runs.

### 6.10 `-prenorm` and `-nocrossstage`

`-prenorm` adds an optional LLM pass that rewrites the English input before the two-stage
translation, normalising surface wording; it composes with any of the above and is the base
of the FOLIO abstraction ladder.  `-nocrossstage` disables the ultracoarse cross-stage
guard-retry used alongside it.
