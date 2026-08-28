# Stage 2: extended first-order logic JSON

This page defines the Stage-2 output format: the package grammar, the
formula operators, the predicates, and the treatment of quantifiers
and variables.

This page is normative.

**Produced by:** Stage-2 LLM call (llmparse.py)
**Consumed by:** logconvert.rawlogic_convert()

Stage 2 converts each ASU into extended first-order predicate logic encoded as
nested JSON lists. In addition to ordinary quantifiers and connectives, the
format supports defeasible `normally` formulas, probabilistic confidence
annotations, contextual terms, and question operators.

## Top-Level Structure

```json
["and",
  ["@id", "S1", PACKAGE],
  ["@id", "S2", PACKAGE],
  ...
]
```

Each ASU produces one `["@id", "Sx", PACKAGE]`.

## Package Shapes

```
["holds", W, FORMULA]          — assertion anchored to a world constant
["question", FORMULA]           — yes/no question
["ask", VAR, FORMULA]           — wh-question; VAR is the answer variable
["and", PACKAGE, ["@p","Sx",P]] — package with confidence P (0–1)
```

## Logical Connectives

```
["and", A, B, ...]     ["or", A, B, ...]      ["xor", A, B]
["not", A]              ["implies", A, B]       ["=", A, B]
["<", A, B]             [">", A, B]
["forall", "X", A]      ["exists", "X", A]
["question", A]         ["ask", "X", A]
```

## Predicates

The predicate inventory is a closed whitelist — no invented predicates.

### Core Predicates

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

### Gradable Predicates

Used when the word appears in the ASU's `adjectives` field:

| Predicate | Arguments | Example |
|-----------|-----------|---------|
| `has degree property` | PROP, ENTITY, DEGREE, RELCLASS | `["has degree property", "tall", "John 1", "none", "person"]` |
| `has degree rel2` | REL, E1, E2, DEGREE, RELCLASS | `["has degree rel2", "close to", "A", "B", "high", "city"]` |

DEGREE values: `"none"`, `"high"` (very), `"low"` (slightly), `"more"`, `"most"`, `"less"`, `"least"`.

### Event Reification Predicates

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
carry no classifier.  See `axioms_std.js` [the source map](../code/source-map.md) for the defeasible
actuality→capability bridge.


### Structural Predicates

```
["holds", W, F]                — anchor formula F to world state W
["next", W1, W2]               — W2 is the immediate successor of W1
["before", W1, W2]             — W1 is an earlier world state than W2
["=", ["$theof1","time",W,C], ["$datetime",N]]  — world W anchored to time N (numeric)
["=", ["$measure_of",ATTR,OBJ,W], ["$measure",N,UNIT]]  — measurement (see [the source map](../code/source-map.md))
["state location", W, L]       — location in world state
["normally", F]                — defeasible wrapper
["@time", TIME, ATOM]          — per-predicate time override
["@id", "Sx", F]               — ASU traceability
["@p", "Sx", P]                — confidence annotation
```

Note: `next` is generated by Stage 2 from `next_state` annotations.  `before` is
NOT generated by Stage 2 — it is derived by background axioms in `axioms_std.js`
(e.g., `next(W0,W1) => before(W0,W1)` and transitivity of `before`).

### Set and Counting Predicates

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

## Quantification Patterns

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

## Variable Conventions

| Role | Names |
|------|-------|
| Entity | X, Y, Z, X1, Y1 |
| Event | E, E1, E2 |
| Set | S, S1, S2 |
| Count | N |
| Scalar | V |

Variables must always be introduced by a quantifier (`forall` or `exists`) and
used within its scope.

## Complete Stage-2 Examples

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
see [the pipeline](../architecture/pipeline.md) *Modal Classifiers* — so Stage 2 does not emit it.)

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

## Related documentation

- [Stage 1](stage-1.md)
- [GK clauses](gk-clauses.md)
- [Logic compilation](../architecture/logic-compilation.md)
