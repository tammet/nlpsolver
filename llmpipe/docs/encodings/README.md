# Encoding reference

These pages are the intended normative description of the logical forms the
pipeline uses. Where another documentation page disagrees with them, follow
these. Where the code disagrees with them, one of the two is wrong: check the
code, then correct whichever is at fault.

Architecture pages explain algorithms and decisions. These pages define exact
forms: what an atom looks like, what its arguments mean, and which of them a
model writes rather than the compiler.

## Processing layers

A question passes through three encoded forms after the English input.

```text
English passage and question
    │
    ▼  Stage 1, a model call
atomic semantic units                      stage-1.md
    │
    ▼  Stage 2, a model call
extended first-order logic in JSON         stage-2.md
    │
    ▼  the compiler, deterministic code
GK clause list                             gk-clauses.md
    │
    ▼  GK
answer and proof
```

The logic is first-order, extended. Besides ordinary quantifiers and
connectives it supports defeasible `normally` formulas
([defeasible expansion](../architecture/logic-compilation.md)), probabilistic
confidence annotations
([questions, confidence and answers](../architecture/questions-confidence-and-answers.md)),
a contextual term carrying tense, world and situation
([the `$ctxt` term](gk-clauses.md)), questions in three shapes, sets and
counting, measurements, and definite descriptions. Each is defined on the page
that owns it.

## The ordinary canonical representation

The controlled Stage-2 predicates and canonical clause predicates form the
stable interface between translation, compilation, `axioms_std.js`, and any
later knowledge base. The compiler may also use reversible internal forms, but
it emits clauses connecting them back to this interface.

## Equivalent compiler rewrites

The compiler attempts two rewrites on the canonical theory without being asked.
Each replaces a group of atoms by one shorter atom and emits clauses deriving
the original group back, so nothing is lost or added.

- **reversible compact event representation** — four spine atoms become
  `event(V,A,T,E,C)`;
- **repeated part-witness representation** — a repeated existential part
  pattern becomes a `[$has_part, C]` property with a shared witness.

**The ordinary Stage-2 model writes neither.** It never emits the `event(...)`
compact atom and never emits the `$has_part` summary. Both are compiler output.
[compiled-representations.md](compiled-representations.md) defines them, and
[proof shortening](../architecture/proof-shortening.md) says when each is
attempted.

## Alternative representations

Two kinds, both explicit.

**The open-relation graph translation** is a second model call with a different
atom contract: fixed logical structure, open content names, one world, no
context term. It is not a rewrite of the ordinary Stage 2, and its Stage-2
output is not valid ordinary Stage 2.
[graph-format.md](graph-format.md) defines it.

**The abstraction and legacy forms** are selected by option: other event bases,
the abstraction primitives, and the presets built from them. Each deliberately
loses or adds distinctions.
[compiled-representations.md](compiled-representations.md) compares them and
[abstraction](../architecture/abstraction.md) describes the machinery.

## Which page defines what

| form | written by | defined in |
|---|---|---|
| atomic semantic units | Stage 1, a model call | [stage-1.md](stage-1.md) |
| extended first-order logic JSON | Stage 2, a model call | [stage-2.md](stage-2.md) |
| GK clause list, `$ctxt`, `$block`, question clauses | the compiler | [gk-clauses.md](gk-clauses.md) |
| canonical event spine | the compiler | [compiled-representations.md](compiled-representations.md) |
| `event(V,A,T,E,C)` | the compiler | [compiled-representations.md](compiled-representations.md) |
| `[$has_part, C]` and `$typed_partof` | the compiler | [compiled-representations.md](compiled-representations.md) |
| other event bases and abstraction forms | the compiler, on request | [compiled-representations.md](compiled-representations.md) |
| open-relation graph triples | graph Stage 2, a separate model call | [graph-format.md](graph-format.md) |
| one worked case, end to end | — | [end-to-end-example.md](end-to-end-example.md) |

## Pages

- [Stage 1: atomic semantic units](stage-1.md) — unit types, entities,
  actions, worlds, time and confidence.
- [Stage 2: extended first-order logic JSON](stage-2.md) — the package
  grammar, the operators, the controlled predicates, quantifiers and variables.
- [GK clause list](gk-clauses.md) — clauses, signs, the context term,
  defaults, confidence, question and population clauses, background axioms.
- [Compiled representations](compiled-representations.md) — the canonical event
  spine, the two reversible rewrites, and the selectable alternatives.
- [Graph translation format](graph-format.md) — the open-triple contract, its
  structural checks, and its compilation.
- [End-to-end example](end-to-end-example.md) — one passage through every
  layer.

## Related documentation

- [Translation](../architecture/translation.md) — how the two model calls work
- [Logic compilation](../architecture/logic-compilation.md) — the compiler sequence
- [Command-line reference](../reference/command-line.md) — the options
- [Glossary](../reference/glossary.md)
