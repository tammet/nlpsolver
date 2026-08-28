# Stage 1: atomic semantic units

This page defines the Stage-1 output format. Stage 1 turns English
into a list of units. Each unit carries its type, its entities, its
actions, and its time and world fields.

This page is normative. Architecture pages describe what the pipeline
does with these units; the format is defined here.

**Produced by:** Stage-1 LLM call (llmparse.py)
**Consumed by:** Stage-2 LLM call and logconvert.py

Stage 1 converts English text into a list of *sentence packages*.  Each sentence
produces one package containing one or more *Atomic Semantic Units* (ASUs) — minimal
propositions that can be independently true or false.

## Top-Level Structure

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

## ASU Types

Every ASU has a `"type"` field:

| Type | Meaning | Example |
|------|---------|---------|
| `real` | Timeless fact about a named entity | "Tallinn is a city." |
| `situation` | Concrete event or state in a narrative | "John drove a car." |
| `strict_rule` | Universal definition/law (forall/implies) | "Elephants are animals." |
| `normal_rule` | Defeasible default (normally/typically) | "Birds can fly." |
| `query` | A question | "Is John an animal?" |

## Entities

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

## Scope (Generic Entities)

Generic entities may carry a `"scope"` hint:

| Scope | Meaning | Example |
|-------|---------|---------|
| `dependent` | Per-subject existential (default) | "a tail" in "Dogs have a tail" |
| `global` | One shared instance | "a park" in "All children play in a park" |
| `kind` | Uncountable mass substance (constant) | "water", "gold", "air" |

## Actions

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
rather than the LLM — see [the pipeline](../architecture/pipeline.md) *Modal Classifiers* for the injection
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
The [abstraction](../architecture/abstraction.md) Mental Attitudes infrastructure (`mental_holder` /
`mental_attitude`) is reserved for pure epistemic `knows that` /
`believes that`; all hopes / wants / intends / tells migrate to
`actions[mode=…]`.

Stative verbs (have, own, like, love, fear, know, believe) are NOT
encoded as actions.

## Adjectives

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

## World States

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

## Time

### Relative tense

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
the GK clause list (see [the source map](../code/source-map.md)).

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

### Explicit time values (dated world states)

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

## Confidence

Float 0–1 representing logical strength.  Omitted when 1.0.

| Source | Confidence |
|--------|-----------|
| Explicit probability ("30%") | 0.3 |
| Usually/normally | 0.98 |
| Often/probably | 0.8 |
| Sometimes | 0.5 |
| Rarely | 0.2 |
| Some/a/an (existential) | 0.99 |

## Other Fields

- **`location`**: entity ID of the location — "John ran in the park" → `"location": "park 2"`
- **`mental_holder` / `mental_attitude`**: for propositional attitudes —
  "John knows that Mary is tall" → `"mental_holder": "John 1"`, `"mental_attitude": "knows"`
- **`epistemic_force`**: `"factive"` (knows), `"non_factive"` (believes), `"counterfactual"` (imagines)
- **`definites`**: for definite possessives — "John's sister" →
  `"definites": [["sister of", "sister 2", "John 1"]]`.
  This triggers the `$theof1` rewrite in lc_post_reify: the flat entity ID (`"sister 2"`)
  is replaced by a canonical function term `["$theof1", "sister", "John 1", CTXT]`
  so that all references to "John's sister" unify as the same object (see [the source map](../code/source-map.md)).
- **`wh_placeholder`**: `true` on the entity introduced for who/what/where questions —
  `{"id": "entity", "type": "generic", "wh_placeholder": true}`

## Complete Stage-1 Example

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

## Related documentation

- [Stage 2](stage-2.md)
- [Translation](../architecture/translation.md)
- [Encoding reference index](README.md)
