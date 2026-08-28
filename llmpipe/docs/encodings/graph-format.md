# Graph translation format

The output format of the graph translator, and what the graph compiler turns it
into. This page defines the format. When the stage runs, how its output is
searched, and what is recorded are in
[graph representation](../architecture/graph-representation.md).

The graph translator is a second Stage 2. It reads the same Stage-1 units the
ordinary Stage 2 read, and writes a different logic: the logical structure is
fixed, and the content atoms are open. There is no predicate vocabulary. Every
content name is built from the words of the unit.

The format admits fewer distinctions than the
[ordinary Stage-2 format](stage-2.md): one world, no context term, no tense, no
sets and no measurements. What it keeps, it keeps in the name.

## Package structure

The whole output is one JSON list.

```json
["and", PACKAGE_1, PACKAGE_2, ..., PACKAGE_N]
```

Each Stage-1 unit `Sx` produces exactly one package, and every package is
wrapped in exactly one `@id`.

```json
["@id", "Sx", ["holds", "W0", FORMULA]]
["@id", "Sx", ["question", FORMULA]]
["@id", "Sx", ["ask", "X", FORMULA]]
```

A non-question unit uses `holds`. A yes/no question uses `question`. A question
whose Stage-1 unit carries a `wh_placeholder` entity uses `ask` with the
variable. A question package is never anchored with `holds`.

A confidence below 1.0 adds a second element:

```json
["@id", "Sx", ["and", ["holds", "W0", FORMULA], ["@p", "Sx", 0.7]]]
```

The world is always `"W0"`. Nothing else may appear inside a package: no
`next`, no `state time`, no `state location`, no `@definite`, no `@time`.

## Logical operators

Only these, each with a fixed number of items:

| operator | form |
|---|---|
| `and` | `["and", A, B, ...]` |
| `or` | `["or", A, B, ...]`, inclusive |
| `not` | `["not", A]` |
| `implies` | `["implies", A, B]` |
| `forall` | `["forall", X, A]` |
| `exists` | `["exists", X, A]` |
| `normally` | `["normally", A]` |
| `=` | `["=", A, B]`, between two entity terms only |
| `question` | `["question", A]` |
| `ask` | `["ask", X, A]` |
| `holds` | `["holds", W, A]` |
| `@p` | `["@p", UNIT_ID, CONFIDENCE]` |

`solver/graph_stage2.py` holds this table as `OPERATOR_ARITY`, and
`check_operator_arity` rejects any operator whose item count differs.

`xor`, `<`, `>`, `$setof`, `$count`, `$measure` and `$measure_of` are not part
of the format. An exclusive reading is written as plain `or`; a count or a
measurement is written as a value (see Values below).

## Content atoms

Every content atom is a JSON list of exactly three items. There are two kinds
and no others.

**Concept atom**, using the reserved name `isa`:

```json
["isa", CONCEPT_NAME, ENTITY]
```

**Open binary relation**:

```json
[RELATION_NAME, LEFT, RIGHT]
```

`LEFT` is the grammatical subject and `RIGHT` the object or complement, in
English reading order. The same relation keeps the same argument order
everywhere in one case.

```json
["isa", "bird", "Puffin 1"]
["isa", "bird_that_swims", "X"]
["isa", "can_cross_water", "X"]
["requires", "X", "labeled_data"]
["taller_than", "X", "Y"]
["member_of", "Schmidt 1", "Reichstag 1"]
```

Class nouns, adjectives, capabilities, habits, states, and verb phrases whose
object is generic or absent all take the concept form.

### Names

Names are lowercase, with words joined by underscores. No spaces, no capitals,
and no punctuation but the underscore.

A name is built from the words of its own unit and keeps the words that change
the meaning, including modifiers, prepositions and complements:
`cool_ocean_water`, `grow_large_leaves`, `has_higher_conductivity_than_nonmetals`.
Vague labels such as `related_to` or `property_1` are not used, and no name is
canonicalised toward a shared vocabulary. If one unit says "animal lover" and
another says "loves animals", the two names differ; connecting them is a later
step's work.

The controlled predicate names are reserved and may never be used as an open
name: `is rel2`, `has property`, `has degree property`, `has degree rel2`,
`have`, `has part`, `has type`, `has actor`, `has target`, `has recipient`,
`has location`, `has time`, and any name containing a space. A possessive or a
part relation is written as an open name instead: `["has_part", "car 1",
"wheel 2"]`, `["owns", "John 1", "car 1"]`.

## When a complement is folded into the name

For every verb or relational phrase, the complement is either an argument or
part of the name.

**Kept as an argument**, giving a relation atom, when the complement is a
concrete Stage-1 entity, a variable bound elsewhere in the same formula, or a
generic kind that another unit treats as a thing in its own right.

```json
["loves", "Mary 1", "Fido 2"]
["converts_into", "X", "electrical_energy"]
```

**Folded into the name**, giving a concept atom, when the complement is
generic, indefinite or absent and is not needed as a thing in its own right.

```json
["isa", "loves_animals", "X"]
["isa", "owns_a_pet", "X"]
["isa", "has_higher_conductivity_than_nonmetals", "X"]
```

A quantifier word that matters stays in the name: `loves_some_animal` and
`loves_every_animal` are different names.

Within one case the same verb takes one shape throughout. A rule may not use
`["isa", "swimming_bird", "X"]` while a fact about the same kind of thing uses
`["swims", "Puffin 1", "water"]`.

A definite or possessive noun phrase that appears only inside a question is
folded into the question subject's concept name rather than introduced as a
fresh entity.

## Negation

Plain logical negation stays outside the name.

```json
["not", ["isa", "paid", "invoice 1"]]
```

A lexical negative the text itself uses is a name: `flightless`, `absent`,
`unpaid`, `non_metal`. A name such as `not_paid` or `does_not_fly` is never
built when the text says "not". `check_lexical_negatives` reports one that is.

## Modality and aspect

A word that changes the truth conditions stays in the name. The Stage-1 mode
decides the prefix:

| Stage-1 mode | name prefix |
|---|---|
| `capability` | `can_` |
| `necessity` | `must_` |
| `obligation` | `should_` |
| `volition` | `wants_to_` |
| `intention` | `intends_to_` |
| `expectation` | `expects_to_` |
| `speech_act` | the reporting verb is folded, as in `told_to_leave` |
| `habitual`, `event` | no prefix |

A negated modality is written with `not` around the atom, never as
`cannot_swim`. The logic is timeless: "ate", "eats" and "will eat" may share
the root `eat` unless the unit contrasts them.

## Events with three or more participants

An event with a subject and exactly one object is a relation atom. An event
whose participants do not reduce to one subject and one object is reified with
an event variable and fixed role names.

```json
["exists", "E",
 ["and", ["isa", "give_event", "E"],
         ["agent", "E", "Alice 1"],
         ["theme", "E", "book 2"],
         ["recipient", "E", "Bob 3"]]]
```

The role names are fixed and are not open names:

```text
agent  theme  recipient  source  destination  location  instrument  time  manner
```

The event type is the open part and is a concept on the event variable. An
event with only a subject and one object is not reified, and a concrete
participant is never folded into a name.

## Values

A number, a date, a unit-bearing quantity or a literal value is a value string
in the second argument of an open relation.

```json
["has_length_km", "Nile 1", "80"]
["has_number_of_cars", "John 1", "3"]
```

## What the format does not represent

There is no event vocabulary beyond the fixed roles above, no context term, no
tense, no world change, no set or measurement term, and no mental structure. A
unit carrying such content is encoded with concept and relation atoms, and the
rest is left out.

This is a deliberate loss. The ordinary encoding keeps those distinctions; see
[GK clause list](gk-clauses.md) for what the canonical theory carries.

## Structural checks

`graph_stage2.check_graph` runs every check in one list, arity first, because a
malformed logical structure must be seen before anything normalises it.

| check | what it rejects |
|---|---|
| `check_operator_arity` | an operator whose item count differs from `OPERATOR_ARITY` |
| `check_atoms` | a content atom that is not exactly three items, a reserved name, an entity id in the concept slot |
| `check_packages` | a missing or duplicated `@id`, a nested wrapper, a package that is not `holds`, `question` or `ask` |
| `check_free_variables` | a variable used outside its binder |
| `check_lexical_negatives` | a negation folded into a name |
| `check_shape_consistency` | one verb used as a concept in one unit and a relation in another |
| `check_question_restatement` | the question's content repeated as a `holds` package |
| `check_question_entity`, `check_question_reuse` | a question that introduces a fresh entity or a fresh name instead of reusing the passage's |
| `check_kind_class_consistency` | a generic entity used as both a class and a constant |
| `check_monolith_names`, `check_near_duplicate_names` | one name carrying a whole sentence, and two names differing trivially |
| `check_existential_units`, `check_hedge_rule`, `check_rule_tautology` | a scope, hedge or tautology error in a rule |

A failed check produces one corrective retry with the findings appended. If the
retry is absent, fails, or is still malformed, the stage stops before
compilation and before GK, recording `graph_translation_structurally_invalid`.

## Compilation into clauses

`graph_compile.to_stage2` is a purely syntactic pass into the controlled
Stage-2 vocabulary:

- `["isa", C, X]` passes through unchanged;
- `["=", A, B]` passes through unchanged;
- every other content atom `[R, X, Y]` becomes `["is rel2", R, X, Y]`, a fixed
  event role included;
- the formula structure is copied.

So the open relation name becomes the first argument of the controlled
`is rel2` predicate, and the open concept name stays the first argument of
`isa`. `graph_compile.compile` then runs the ordinary
`logconvert.rawlogic_convert` over that Stage 2, under one frozen option set.

### The frozen option set

The graph theory must contain no connection between two open names except a
named clause. `graph_compile.GRAPH_OPTION_TABLE` therefore turns off:

- `axioms_std.js` — no background axioms at all;
- semantic normalisation, the synonym, exclusion and mutex injectors, and every
  dynamic bridge;
- every abstraction primitive and preset;
- both proof-shortening rewrites, `noproofshort2_flag`, so the canonical
  default does not reach this theory;
- the class-number normalisation, so `swims` and `swim` stay two names;
- the open-name rewrites, so `owns` does not become the pipeline's `have` and a
  perspective verb does not become a Davidsonian event;
- population witnesses and Stage-1 entity-category `isa` clauses, each of which
  would put a name into the theory that the translator never wrote.

The context is the constant `$c`.

What stays active: entity unique-name wrapping with the `#:` prefix, the
`$defq` question encoding with the bare-plural generic hoist, Skolemization,
and the structural repairs.

## The three graph mechanisms

They are distinct, and their answer policies differ.

| mechanism | what it does | can it produce the run's answer |
|---|---|---|
| graph retranslation, `-graphtrans` | translate, compile, one GK call, no invented rules | yes; it is enabled by the `balanced` default |
| graph bridge generation, `-graphbridge` | invent implications between the open names and search that theory | yes, when a minimal set passes the credibility check; not enabled by default |
| lifting | re-express a graph proof over the ordinary atoms | no; it is off (`graph_procedure.LIFT`) and records a result rather than deciding one |

[Graph representation](../architecture/graph-representation.md) describes each
in full. [Mechanism experiments](../mechanisms/README.md) gives their
evaluation.

## Related documentation

- [Encoding reference](README.md)
- [Stage 2](stage-2.md) — the ordinary format this one replaces
- [GK clause list](gk-clauses.md) — what compilation produces
- [Graph representation](../architecture/graph-representation.md) — execution
- [Mechanism experiments](../mechanisms/README.md) — evaluation
