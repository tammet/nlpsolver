# Experimental options

A lookup page for the research, ablation, diagnostic, legacy and compatibility
controls. None of them is needed for ordinary use, and the ordinary default
uses none of them. The everyday and advanced options are on the
[command-line reference](command-line.md).

Each entry gives the exact syntax, what changes, the current status and the
page that explains the mechanism. Status has five values.

- **research** — kept because it is still being investigated.
- **diagnostic** — kept to isolate one behaviour when reading a result.
- **ablation** — kept to reproduce a measurement with one part removed.
- **legacy** — an older representation, kept so earlier runs reproduce.
- **compatibility** — an older spelling of a current option.

Every single-dash key is also accepted with two dashes.

## Acceptance policy

**`-accept permissive|balanced|strict`**, also `-accept=NAME`.
Applies proof-local checks to a critic or graph answer before that answer is
taken. Absent, no check runs. `runtests.py` accepts the same key.
Status: research.
Risk: measured over 119 additions, `balanced` and `strict` discarded more
correct answers than wrong ones.
See [retries](../architecture/retries.md) and
[mechanism experiments](../mechanisms/optional.md).

## Proof-shortening overrides

The compiler attempts two guarded, reversible rewrites on the ordinary
canonical theory: reversible event compression and repeated part-witness
compression. [Proof shortening](../architecture/proof-shortening.md) describes
both, states when each declines, and gives the table of which command lines
attempt which.

**`-nodavidson2`** — reversible event compression off. Status: diagnostic.

**`-noexistfold2`** — repeated part-witness compression off.
Status: diagnostic.

**`-noproofshort2`** — both off. This reproduces the theory and the answers as
they stood before 2026-08-26. Status: ablation.

**`-davidson2`**, **`-existfold2`**, **`-proofshort2`** — ask for one or both
where they are not attempted, for example on top of an `-abstract*` preset.
Reversible event compression declines on a flat base and leaves it unchanged.
Status: diagnostic.

Each of the six wins from any position on the command line; a cancellation
beats a request.

## Simplification

Each removes information from the compiled theory, so a proof that needed it is
lost. [Abstraction](../architecture/abstraction.md) shows the clause each
produces.

**`-nocontext`** — replace the `$ctxt(tense, world, loc, know)` term with the
constant `"$c"`. Axioms that read the context stop applying, so world
persistence and tense reasoning are gone. Status: diagnostic.

**`-noexceptions`** — strip `$block` from the defeasible rules built from the
input, making them strict. Axiom-side blockers are untouched.
Status: diagnostic.

**`-simpleprops`** — replace the degree predicates by their plain counterparts,
dropping the degree and comparison-class arguments. It implies
`-noexceptions`. Status: diagnostic.

**`-simple`** — the three above together. Status: diagnostic.

## Event-encoding bases

**`-event neodavidson|davidson|davidson2|flat|flatroles`** — one selector, and
the only way to change the event surface. The default is `neodavidson`, the
reified encoding the ordinary pipeline uses.

| value | what an event becomes |
|---|---|
| `neodavidson` | reified roles: `isa(activity,E)`, `has type(E,V)`, `has actor(E,A)`, … |
| `davidson` | compact `event(V,A,O,E)`, keeping the handle and the adjuncts |
| `davidson2` | reversible event compression, selected as the base |
| `flat` | `is_rel2(V, subject, object)` with a bare positional object |
| `flatroles` | `is_rel2(V, subject, ["eventprop", role, value])` |

Status: `davidson`, `flat` and `flatroles` are legacy; `davidson2` is the
reader-facing reversible compression, described under proof shortening.
Risk: every base but `neodavidson` and `davidson2` loses distinctions, so an
answer found under one is not evidence about another.
See [abstraction](../architecture/abstraction.md).

## Abstraction primitives

Each composes with any base. All are post-translation: Stage 1 and Stage 2 do
not change. [Abstraction](../architecture/abstraction.md) describes what each
produces and where it runs.

**`-entitymerge`** — merge proper-noun constants that name one entity, and
resolve set labels to the same identifier. Status: research.

**`-typeenrich`**, also **`-typeenrich=GATES`** — add taxonomy `isa` facts. The
bare form enables all six sub-options; the equals form takes a comma list of
`super,gender,nametype,compound,plural,gnoun`, where a leading `-` excludes one
and `all` selects all. Status: research.
Risk: the `plural` sub-option over-derives population witnesses on core-like
material.

**`-guarddrop`** — drop antecedent `isa` guards that are vacuous or already
implied. It does nothing without a fold base. Status: research.

**`-bridges`** — add frame and bridge axioms: relation to event, occasion to
location, containment to part, reflexive property. It needs `-event flat` or
`-event flatroles`. Status: research.

**`-dropdefinites`** — skip `$theof1` reification and leave a definite
description as a plain relation. Status: research.

**`-localantonyms`** — fold an antonym only when the word occurs in the problem
or the axiom vocabulary. Status: research.

**`-existfold`** — the legacy existential-attribute collapse:
`∃Y. isa(C,Y) ∧ has_part/have(X,Y)` becomes
`has_property([$has_part,C], X)`, with a named-witness bridge. It also folds
`have` and injects clauses quantified over the class, which the current
repeated part-witness compression does not. Status: legacy.

**`-propclass`** — bridge `isa(W,X)` and `has property(W,X)` for a concept the
flat fold left in both shapes. Status: research.

**`-numtype`** — read a pure numeral string as a number, and add
`isa(number,N)` where a rule demands the typing but nothing supplies it.
Status: research.

**`-compasym`** — for a strict-scalar adjective used as `is_rel2(R,X,Y)`, add
the antisymmetry `is_rel2(R,X,Y) ∧ is_rel2(R,Y,X) → X=Y`. The adjectives come
from `solver/comparable_adjectives.txt`. Status: research.

## Abstraction presets

Each expands into the primitives above at parse time and is read nowhere else.

**`-abstract`** — `-event flat` with `entitymerge`, `guarddrop`, `bridges`,
`dropdefinites`, `typeenrich`, `localantonyms` and `simpleprops`.
Status: legacy.

**`-abstract-roles`** — the same on `-event flatroles`. Status: legacy.

**`-abstract-max`** — `-abstract-roles` plus `prenorm`, `propclass`, `numtype`,
`compasym`, the nominal retry and the negation retry, and it enables all six
retry stages. Status: legacy.
Risk: it makes model calls on every unresolved case, and on a 314-case core
regression set it turned 124 to 147 answers per model from correct to wrong or
`Unknown`, against 0 to 4 gains
([mechanism experiments](../mechanisms/optional.md)).

## Alternative parsing shapes

Each replaces the default two-stage parse.
[Translation](../architecture/translation.md) describes them.

**`-s2split`** — one Stage-2 call per Stage-1 sentence package, with the
outputs joined and locally invented worlds renumbered. A failed sentence is
skipped unless it holds the question. The cross-sentence shape-unification
repair runs with it. Status: research.

**`-combined-instr FILE`** — single-stage parsing: one call from English to
logic, with no Stage-1 JSON. **`-combined-examples FILE`** and
**`-combined-checklist FILE`** add the optional prompt parts.
Status: research.

**`-directanswer FILE`** — answer the question with one model call. No logic
and no prover, so there is no proof. Status: research.

**`-prenorm`** — a wording-normalisation model call before Stage 1. It composes
with any base. **`-noprenorm`** forces it off after a preset that set it.
Status: research.

**`-nocrossstage`** — disable the cross-stage guard retry. The retry is inert
unless an abstraction encoding is active, so this changes nothing on the
ordinary path. Status: ablation.

## Compatibility spellings

| older key | resolves to |
|---|---|
| `-stack-closed` | `-pipeline balanced` |
| `-stack` | `-pipeline high-recall` |
| `-stack-open` | all six retry stages, literal bridge included |
| `-geminicache` | accepted and ignored; Gemini context caching is the default |

`runtests.py` defines two keys of its own that belong here.
**`-combined-tag TEXT`** names the output directory of a combined-parse run.
**`-typeenrich-gates LIST`** passes the sub-option list that
`-typeenrich=GATES` carries on `solve.py`.

## How a key reaches the compiler

Each representation key sets one entry in `globals.options`. No pipeline pass
reads those entries or the presets directly. `lc_encoding.EncodingConfig`
resolves them once, after the whole command line, and every pass reads that
object.

| CLI key | option key | `EncodingConfig` field |
|---|---|---|
| `-event MODE` | `event_base` | `flatten`, `eventprop`, `davidson` |
| `-entitymerge` | `entitymerge_flag` | `entitymerge`, `parse_canon` |
| `-typeenrich[=GATES]` | `typeenrich_flag`, `typeenrich_gates` | `typeenrich`, `te(name)` |
| `-guarddrop` | `guarddrop_flag` | `guarddrop` |
| `-bridges` | `bridges_flag` | `bridges` |
| `-dropdefinites` | `dropdefinites_flag` | `dropdefinites` |
| `-localantonyms` | `localantonyms_flag` | `localantonyms` |
| `-existfold` | `existfold_flag` | read from the options |
| `-propclass` | `propclass_flag` | `propclass` |
| `-numtype` | `numtype_flag` | `numtype` |
| `-compasym` | `compasym_flag` | `compasym` |
| `-simpleprops`, `-simple` | `noproptypes_flag` | `simpleprops`, `collapse_degree` |
| `-nocontext` | `nocontext_flag` | read from the options |
| `-noexceptions` | `noexceptions_flag` | read from the options |
| `-prenorm` | `prenorm_flag` | resolved in the parser, before Stage 1 |
| `-s2split` | `s2split_flag` | resolved in the parser |

`needs_coarsen` is true when any of `davidson`, `flatten`, `entitymerge` or
`guarddrop` is set; it decides whether `coarsen_events` runs at all.
`collapse_degree` follows `simpleprops` and `parse_canon` follows
`entitymerge`. The `coarse` field is unused and always `False`.

The nominal retry that `-abstract-max` enables is a Stage-2 check and
corrective retry, not an `EncodingConfig` field, so it has no row here. See
[translation](../architecture/translation.md).

## Related documentation

- [Command-line reference](command-line.md)
- [Abstraction](../architecture/abstraction.md)
- [Proof shortening](../architecture/proof-shortening.md)
- [Translation](../architecture/translation.md)
- [Encoding reference](../encodings/README.md)
- [Mechanism experiments](../mechanisms/README.md)
