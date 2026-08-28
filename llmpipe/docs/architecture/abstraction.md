# Abstraction

Representations and transformations that lose or add distinctions, and the
options that select them.

The default pipeline uses none of them. It uses the canonical
neo-Davidsonian encoding and the two reversible rewrites described in
[proof shortening](proof-shortening.md), which lose nothing.

Everything on this page is optional. The command-line keys are listed on the
[experimental options](../reference/experimental-options.md) page, which also
shows what each one does to the encoding. This page describes the machinery.

## The encoding resolver (`lc_encoding.py`)

Every encoding condition in the pipeline reads a single resolved config.
`lc_encoding.EncodingConfig`, built once from the option keys (`lc_encoding.current()`
reads the live `globals.options`), exposes the derived booleans the rest of the
pipeline consults: `flatten`, `eventprop`, `davidson`, `coarse`, `entitymerge`,
`guarddrop`, `bridges`, `dropdefinites`, `localantonyms`, `simpleprops`,
`collapse_degree`, `parse_canon`, `needs_coarsen`, `typeenrich`, `propclass`, `numtype`,
`compasym`, plus a `te(gate)` method for the per-gate type-enrichment test.  Every encoding read site in
`logconvert.py`, `lc_sets.py`, `lc_coarse.py`, `semnormalize.py`, `lc_post_reify.py`
and `solve.py` goes through this config, so the gating logic lives in exactly one place.

The compiler also attempts two reversible proof-shortening rewrites on the
ordinary canonical theory. They are resolved by the same config, in
`EncodingConfig.__init__`, after the whole command line is read.
[Proof shortening](proof-shortening.md) describes them and gives the table
of when each is attempted. Those two rewrites lose nothing; everything else
on this page can.

Population of the config:

- **Event base** — `-event MODE` sets `event_base` ∈ {`neodavidson` (default, reified
  neo-Davidsonian), `davidson` (compact `event(V,A,O,E)`), `flat` (bare positional
  `is_rel2` object), `flatroles` (`is_rel2` with eventprop-tagged object)}.  From it:
  `flatten = base in {flat, flatroles}`, `eventprop = base == flatroles`,
  `davidson = base == davidson`.  `coarse` is always `False`.
- **Additive primitives** — one option key each: `entitymerge_flag`, `guarddrop_flag`,
  `bridges_flag`, `dropdefinites_flag`, `localantonyms_flag`, `noproptypes_flag`
  (`simpleprops`), `propclass_flag` (`propclass`), `numtype_flag` (`numtype`), `compasym_flag`
  (`compasym`), and `typeenrich_flag` (+ optional `typeenrich_gates`).  `collapse_degree` rides
  with `simpleprops`; `parse_canon` rides with `entitymerge` (parse-level entity canonicalization
  is self-contained, driven by `-entitymerge`).  (`nominalretry_flag` is a parse-time Stage-2 retry,
  read from `globals.options` directly — not an `EncodingConfig` field; see [translation](translation.md).)
- **`needs_coarsen`** — true iff any of `davidson`/`flatten`/`entitymerge`/`guarddrop`
  is set, i.e. whether `coarsen_events` runs at all.
- **typeenrich gates** — `typeenrich_gates` is a frozenset over
  `{super, gender, nametype, compound, plural, gnoun}`; bare `-typeenrich` enables all
  six, `-typeenrich=GATES` enables the named subset, and `te(gate)` is the per-gate
  test.

The `-abstract*` presets ([abstraction](abstraction.md)) are pure CLI expansions into these primitive keys —
they are read nowhere in the pipeline, only at argument-parse time.

## The event folds (`lc_coarse.py`)

`coarsen_events(tree, flatten=, eventprop=, davidson=, coarse=, do_canon=, do_guard=,
collapse_degree=)` is called from `rawlogic_convert` (only when
`EncodingConfig.needs_coarsen`) after actuality injection and tense-`has_time`
stripping, so the eligibility test sees the final event shape.  All gating is resolved
by the caller; the params are the already-derived `EncodingConfig` booleans (the
`coarse` arg is vestigial, always `False`).  With `flatten` it applies the aggressive
flat folds (relational `is_rel2`, unary `has_property`, topic/passive/intransitive
variants, `typical` stripped) — see [experimental options](../reference/experimental-options.md) for the
rule list; with
`eventprop` the single object slot is role-tagged as
`is_rel2(V, subj, ["eventprop", $role, value])`.  With `davidson` it applies instead
the structure-preserving compact fold into `event(V,A,O,E)`.  `lc_ctxt` registers the
folded predicate in `CTXT_ELIGIBLE` and `DESC_PREDS`, so it receives `$ctxt` exactly
as reified roles would.

Supporting passes inside `lc_coarse` (in order, when their condition is set):
- `_canonicalize_entities` (`do_canon`/`entitymerge`) — tree-level merge of split
  proper-noun constants (type-sharing + surface-similarity union-find);
- `_collapse_degree_node` (`collapse_degree`/`simpleprops`) — early degree→simple
  collapse, before guard analysis;
- `_fold_antecedent_events` (with a flat fold) — folds an event introduced as bare
  conjuncts in a rule antecedent (no `exists` wrapper), so rules and folded facts
  unify; uses `_rewrite_rel2_event_object` to free event variables that appear as
  `is_rel2` objects;
- `_drop_redundant_guards` (`do_guard`/`guarddrop`) — drops antecedent `isa` guards
  that are vacuous (near-universal types) or redundant (variable already bound by a
  folded literal); a no-op without a fold base.

`inject_verb_bridges` (per-verb bidirectional event↔relation bridges) is defined but
not wired; the generic `rel2_event_axiom_clauses()` equivalence ([abstraction](abstraction.md)) is used
instead.

## Compile-level passes outside `lc_coarse`

Each is applies only when the resolved `EncodingConfig` field shown:

| pass | where | condition | what |
|---|---|---|---|
| self-defeating-conditional repair | `lc_repairs.repair_self_defeating_conditional` | `flatten` | widens a mis-scoped `¬A ∧ B` antecedent to `¬(A∧B)` when a truth-table check shows the conditional can never produce its consequent |
| broad-supertype isa | `lc_entity_isa.build_entity_category_clauses` | `te("super")` | `isa(person/animal,E)` emitted even when Stage 2 already typed E |
| gender from first name | same | `te("gender")` | `isa(man/woman, E)` from `data_names.gender_of` |
| name-as-type isa | same | `te("nametype")` | a multiword proper name also typed by its lowercased name |
| gendered-noun axioms | `rawlogic_convert` tail | `te("gnoun")` | `isa(gentleman,X) → isa(man,X)` etc., for role nouns present in the clauses (`data_names.GENDERED_NOUN`) |
| compound suffix subsumption | `lc_post_normalize.build_compound_subsumption` | `te("compound")` | subsume to every attested intermediate suffix; also scans entity-category clauses |
| isa-class lowercasing | `lc_clausify.lower_isa_classes_in_node` | `flatten` | run after all injection, folds class-name case |
| definite handling | `rawlogic_convert` | `dropdefinites` | when `dropdefinites`, definite reification is skipped entirely (definites left as plain relations); otherwise `lc_post_reify` reifies `$theof1` with lenient first-match identities |
| antonym presence-gating | `semnormalize` | `localantonyms` | antonym folding applies only when the target word is in problem ∪ axiom vocab |
| `$setof` content labels | `lc_sets._content_label` | `entitymerge` | set ids become content-derived hashes so structurally identical sets unify |
| `$ctxt` decoupling | `rawlogic_convert` last pass | `flatten` | every `$ctxt` term replaced by a fresh variable |

## Dynamic bridge axioms (`lc_post_inject.py` + `lc_coarse.py`)

Appended to the clause list under `-bridges` (which needs a `flat`/`flatroles` base),
each applies only when both bridge sides being present in the problem: `rel2_event_axiom_clauses`
(relation ↔ reified event, Skolem `$ev_of(V,A,O)`), `inject_occasion_location_bridges`
(co-location through an occasion, typed on physical place classes),
`inject_in_haspart_bridge` (`in` → `has_part`), `inject_reflexive_property_bridge`
(`has_property(P,X) ↔ is_rel2(P,X,X)`).  Shapes in [experimental options](../reference/experimental-options.md).

## Entity unification at the parse level (`llmparse.py`, `-entitymerge`)

Driven by `EncodingConfig.parse_canon` (i.e. `-entitymerge`).
`canonicalize_entity_ids(s1_json)` merges Stage-1 entity ids by normalized form,
suffix-stripped base, head-sharing token subset, and high-threshold Levenshtein —
proper nouns only, longest-id-first whole-id replacement (no substring corruption).
`canonicalize_entity_urls(s1_json, s2_json)` rewrites Stage-2 Wikipedia-URL constants
to the best-matching Stage-1 entity id (page-title similarity; ambiguous ties left
alone).  Both record their remaps in the parse stats.

## Cross-stage unsatisfiable-guard retry (`llmparse.py` + `stage_sanity.py`)

After Stage 2 (only with a flat fold base, at most once, disable with `-nocrossstage`):
`stage_sanity.check_unsatisfiable_guards` collects content guards — a class
(`isa`), property (`has property`) or relation (`is rel2`) appearing positively in a
rule antecedent that no fact states and no rule consequent produces.  Such a rule can
never apply, which usually means Stage 1 dropped a word.  If guards exist, BOTH stages
re-run on the ORIGINAL text (not the prenormed one — prenorm itself can be the
dropper) plus a neutral hint (`format_guard_retry_suffix`) naming each guard.  The
retry is kept only if it resolves ALL originally-flagged guards; otherwise the
original parse stands, so a genuinely-absent class is never invented.  The related
`_check_stage2_constant_vs_class` sanity check (a name used as both constant and
class; re-prompts Stage 2) is enabled on the same path via
`stage_sanity.aggressive_repair`.

## The abstraction primitives and proof-shortening folds

Each abstraction option is its own composable primitive, so it can be measured in
isolation (the per-mechanism tables in the LPAR paper).  The `-abstract*` presets set a
fixed subset of them; resolution is centralized in `EncodingConfig`.  The event-base
folds and entity/guard mods are handled in `lc_coarse.coarsen_events` ([abstraction](abstraction.md)); the
others are `lc_existfold` plus the type-enrichment gates.  Reference shapes:
See [experimental options](../reference/experimental-options.md).

- **Event base** (`-event flat` / `-event flatroles` / `-event davidson`): the fold
  shape, resolved to `flatten`/`eventprop`/`davidson` ([abstraction](abstraction.md)).  `-event flat` runs only
  the relational `_fold_event_flat` (no entity canon / degree collapse / guard-drop /
  Skolem merge / supertypes / defeasibility strip — those are separate primitives);
  `-guarddrop` and `-bridges` are no-ops without a flat base.  `-event flatroles`
  (`eventprop`) role-tags the single object slot as
  `is_rel2(V, subj, ["eventprop", $role, value])`.
- **`-typeenrich[=GATES]`**: gates the six `isa`-enrichment sub-injectors via the
  `logconvert._te(gate)` helper (which delegates to `EncodingConfig.te`).  Gates:
  `super, gender, nametype, compound, plural, gnoun`; bare `-typeenrich` enables all
  six.  A `TE_SKIP` env var can disable individual gates for diagnostics; the `plural`
  gate is the one that over-derives population witnesses on core.
- **`-entitymerge`, `-guarddrop`, `-bridges`, `-dropdefinites`, `-localantonyms`**: the
  remaining additive primitives, each described at its read site below and
  [abstraction](abstraction.md).
- **`-event davidson`** (`_davidson_event`, `_davidson_mode`): structure-preserving fold
  of the event spine into `event(V,A,O,E)`, keeping the handle and every adjunct.  The
  patient slot takes the first theme role in `_DAV_PATIENT_ROLES = ["has target","has
  goal","has topic"]`; datives/obliques stay as adjuncts; absent agent/patient become
  fresh existentials; the biconditional `frm_event` bridge (`event_axiom_clauses`)
  interderives with the reified roles and projects `is_rel2`.  A clausify guard
  (`lc_clausify`) drops any headless clause left when the fold strips a defeasibility
  marker, so a generic rule never collapses to a bare negated antecedent.
- **`-existfold`** (`lc_existfold.fold_existential_attributes` + `bridge_clauses`): folds
  `∃Y.isa(C,Y)∧has_part/have(X,Y)` to `has_property([$has_part/$have,C],X)` and emits a
  bidirectional bridge with the named witness `$typed_partof(X,C)` (forward, reverse, and
  the witness-isa clause).  Narrow and parse-dependent.

Per-suite effect (LPAR runs): on the default representation `-event davidson` shortens
proofs and is accuracy-neutral on both suites; on the already-flat `-event flatroles`
FOLIO base it net-lengthens.  `-existfold` shortens only the few reified-existential
chains and never lengthens FOLIO; on core it matches almost nothing and its bridge
axioms lengthen more than they shorten.

## Simplification: what each switch removes

The flags `-nocontext`, `-noexceptions`, `-simpleprops`, and `-simple` produce
progressively simplified encodings.  `-simple` enables all three.

### `-nocontext`

Replaces the `$ctxt(tense, world, loc, know)` term with a constant `"$c"` in every
predicate atom that normally receives context ([the source map](../code/source-map.md)).

```
Default:    has_degree_property(big, cat_1, none, cat, $ctxt(present, W0, ?:Fv1, ?:Fv2))
-nocontext: has_degree_property(big, cat_1, none, cat, "$c")
```

Axioms in `axioms_std.js` that use `?:Ctxt` as a pass-through variable still unify
(binding `?:Ctxt` to `"$c"`).  Axioms that destructure the context — frame axioms,
tense bridges, movement/transfer results — do not unify with `"$c"` and become inert.
This means world-state persistence and tense reasoning are disabled, but all
context-agnostic axioms (taxonomy, transitivity, bridges, synonyms) remain active.

### `-noexceptions`

Strips `$block` literals from defeasible rules produced by `normally` quantifiers
during clausification.  Rules that were defeasible become strict universal rules.

```
Default:      [-isa(bird,X), can(X,fly,CTXT), $block(["$",bird,1], $not(can(X,fly,CTXT)))]
-noexceptions: [-isa(bird,X), can(X,fly,CTXT)]
```

Only affects clauses derived from the input text.  Axiom-side `$block` literals
(in `axioms_std.js` frame axioms, etc.) are unaffected.  The `@confidence` field
is preserved.

### `-simpleprops`

Converts degree predicates to their non-gradable equivalents, dropping degree and
relclass arguments while preserving the context argument:

```
has_degree_property(big, cat_1, none, cat, CTX) → has_property(big, cat_1, CTX)
has_degree_rel2(taller, John, Mary, none, person, CTX) → is_rel2(taller, John, Mary, CTX)
```

Also implies `-noexceptions`.

### `-simple`

Combines all three: `-nocontext` + `-noexceptions` + `-simpleprops`.

```
Default: has_degree_property(big, cat_1, none, cat, $ctxt(present, W0, ?:Fv1, ?:Fv2))
-simple: has_property(big, cat_1, "$c")
```

---

## Event bases and primitives: what each one produces

The event-encoding base is chosen by a single mutually-exclusive selector `-event MODE`,
and a set of additive abstraction primitives compose on top of any base.  These are built
for deductive benchmarks (FOLIO) whose gold logic uses atomic n-ary relations rather than
reified Davidsonian events.  All are post-LLM: Stage 1 and Stage 2 are unchanged; the folds
run inside `logconvert` (machinery reference: [abstraction](abstraction.md)).

`-event MODE` selects one of:

| MODE | event shape |
|---|---|
| `neodavidson` (default) | reified neo-Davidsonian events (`isa(activity,E) ∧ has_type(E,V) ∧ has_actor(E,A) ∧ …`) |
| `davidson` | compact `event(V,A,O,E)`, keeping the handle and all adjuncts ([the prompt map](../code/prompt-map.md)) |
| `flat` | flat relational fold `is_rel2(V, subj, obj)` with a bare positional object ([the prompt map](../code/prompt-map.md)) |
| `flatroles` | flat relational fold with an eventprop-tagged object `is_rel2(V, subj, ["eventprop", role, value])` ([the prompt map](../code/prompt-map.md)) |

The additive primitives are `-entitymerge`, `-typeenrich[=GATES]`, `-guarddrop`, `-bridges`,
`-dropdefinites`, `-localantonyms`, `-existfold`, `-propclass`, `-numtype`, and `-compasym`
(described in the sections above); plus the parse-time nominal-retry Stage-2
retry.
Convenience presets
(`-abstract`, `-abstract-roles`, `-abstract-max`) are pure CLI expansions into a fixed subset
of these primitives ([the prompt map](../code/prompt-map.md)); they are never read in pipeline code.  Every gate is resolved once
in `solver/lc_encoding.py` `EncodingConfig`, and the pipeline reads only that config.

### `-event flat`: relational folds

A flat relational base produces FOLIO-style binary atoms.  An event with an actor and exactly
one object role (`target`/`beneficiary`/`source`/`recipient`) becomes a binary relation; an
event with an actor and no object becomes a unary property:

```
"Real Madrid signed Mbappe":   is_rel2(sign, "Real Madrid 1", "Mbappe 2", CTX)
"The good guys always win":    has_property(win, ?:X, CTX)
```

The event variable and its `exists` wrapper disappear; `$ctxt` is attached to the relational
atom exactly as it would be to the reified roles, so tense survives.  The fold is lossy: it
drops the event variable and keeps only the subject + one object, so secondary roles and
adjuncts are lost.

Further fold rules:
- **Habituals fold.**  The `typical` classifier does not block folding; it is
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
  early (the `-simpleprops` transformation, applied pre-clausification).

Two further passes come with a flat base:
- **Class-name case folding:** the class argument of every `isa` is lowercased
  ("American national" and "american national" become one predicate).
- **`$ctxt` decoupling:** as the LAST pass, every `$ctxt` term is replaced by its own
  fresh variable, so no two atoms are forced to share tense/world (FOLIO is
  timeless).  This makes a flat fold strictly more permissive than the default
  shared-context encoding.
- **`$setof` labels** become content-derived hashes (`set_3fa2c1d0`) instead of
  per-occurrence counters, so structurally identical sets in a rule and a fact unify.

### `-guarddrop`: guard dropping

`-guarddrop` needs a flat fold base (`-event flat`/`flatroles`); it is a no-op without one.

- **Redundant guards:** in a rule antecedent, an `isa(T,V)` guard is dropped when `V`
  is already bound by a folded `is_rel2` literal in the same antecedent, or when
  `T` is a near-universal type (`thing`, `object`, `entity`, …).  A lone
  universal-type antecedent (`"a thing is either A or B"`) drops entirely.

### `-entitymerge` and `-typeenrich`: entity and taxonomy abstraction

`-entitymerge` canonicalizes proper-noun entities and set labels:

- **Entity-constant canonicalization:** proper-noun entities whose ids differ by
  wording variants ("Summer Olympics" / "2008 Summer Olympics", typo-level edits)
  are merged to one constant — both at the Stage-1 level (id remapping) and at the
  tree level; Stage-2 Wikipedia-URL constants are folded into the matching Stage-1
  entity id.  Indefinites (`bear 1` / `bear 2`) are never merged.

`-typeenrich[=GATES]` enriches the `isa`/taxonomy structure.  `GATES` is a comma list of
`super,gender,nametype,compound,plural,gnoun`; a `-` before a gate name excludes it; the keyword
`all` (and bare `-typeenrich`) selects all six:

- **Broad supertypes** (`super`): `isa(person/animal, E)` are emitted even when Stage 2
  already typed the entity with a subtype.
- **Gender-from-name** (`gender`): a known first name adds `isa(man/woman, E)` directly.
- **Gendered role nouns** (`gnoun`): gentleman, actress, … get `isa(noun,X) → isa(man/woman,X)`
  axioms.
- **Name-as-type** (`nametype`): a multiword proper name is also typed by its own lowercased
  name (`isa("winter olympics", "Winter Olympics 1")`), so a generic existential can bind to
  the named constant.
- **Compound suffix subsumption** (`compound`) extends to every attested intermediate
  word-suffix ("American professional basketball player" → "professional basketball player",
  not just → "player"), and also scans entity-category clauses.
- **Plural→singular** (`plural`): class names are normalized to their singular form.

### `-localantonyms` and `-dropdefinites`

- **`-localantonyms`** restricts antonym folding (semantic normalisation) to apply only when
  the target word occurs in the problem ∪ axiom vocabulary, so it never rewrites into a
  predicate nothing else mentions.
- **`-dropdefinites`** skips `$theof1` reification — definites stay plain relations, matching
  FOLIO's atomic style.  Definites have exactly two modes: the default reifies to `$theof1`
  using lenient first-match and emits no identity clauses; `-dropdefinites` skips reification
  entirely.

### `-bridges`: dynamic bridge axioms

`-bridges` (use with `-event flat`/`flatroles`) emits these into the clause list when (and
only when) both sides of the bridge occur in the problem:

| axiom | shape |
|---|---|
| relation ↔ event | `is_rel2(V,A,O) ↔ ∃E. isa(activity,E) ∧ has_type(E,V) ∧ has_actor(E,A) ∧ has_target(E,O)` (Skolem `$ev_of(V,A,O)`) — a folded relation and a still-reified event of the same verb interderive |
| occasion co-location | `is_rel2(P,Occ,Place) ∧ has_location(E,Place,P) ∧ isa(place-class,Place) → has_location(E,Occ,P)` for P ∈ {in,on,at,near} ("won medals IN Tokyo" + "Olympics IN Tokyo" → "won medals IN the Olympics") |
| containment → part | `is_rel2("in",X,Y) → has_part(Y,X)` |
| reflexive ↔ property | `has_property(P,X) ↔ is_rel2(P,X,X)` for predicates appearing in both shapes |

### What stays shared across all bases

Two passes apply on every path, regardless of `-event` base or primitives: Stage-1/Stage-2
parses are transliterated to plain ASCII before clausification (accented entity names
otherwise crash the prover-output decoding), and corrective sanity-retry prompts are
serialized canonically (sorted keys and issue order) so their LLM-cache keys are
byte-stable across runs.

### `-event flatroles`: role-tagged relational fold

Identical to `-event flat` except the relational event fold tags the object with its role,
so a target is never confused with an instrument or location:

```
is_rel2(V, subj, ["eventprop", $role, value])
```

The `$role` label is `$`-prefixed so it is a meta-token (content-word extractors skip it,
keeping the role from leaking into the vocabulary as a spurious noun).  This is the base
used for the maximally-abstracted FOLIO runs.

### `-event davidson`: compact Davidsonian fold

Unlike the lossy `-event flat`/`flatroles` fold, `-event davidson` keeps the event handle and
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
`-event davidson` typically **shortens** proofs on the default neo-Davidsonian encoding (both
nlft and default FOLIO); stacked on the already-flat `-event flatroles` base it instead
**lengthens** them, since that base is more compact than `event(...) + handle + adjuncts +
bridge`.

### `-existfold`: existential-attribute collapse

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

### Abstraction presets

The `-abstract*` presets are pure CLI expansions into the `-event` base and the additive
primitives above — they are never read in pipeline code; the CLI rewrites each to its
constituent flags before `EncodingConfig` resolves the gates.  Each primitive is independent
and composable, so an experiment can also set any subset directly to isolate one lever (this
is how the per-mechanism tables in the LPAR paper are produced).

| preset | expands to |
|---|---|
| `-abstract` | `-event flat` + `-entitymerge` + `-guarddrop` + `-bridges` + `-dropdefinites` + `-typeenrich` + `-localantonyms` + `-simpleprops` |
| `-abstract-roles` | as `-abstract` but `-event flatroles` |
| `-abstract-max` | as `-abstract-roles` + `-prenorm` + `-propclass` + `-numtype` + `-compasym` + nominal retry (the strongest preset; the base of the FOLIO experiments) |

### `-prenorm` and `-nocrossstage`

`-prenorm` adds an optional LLM pass that rewrites the English input before the two-stage
translation, normalising surface wording. It composes with any base or
primitive, and it is the last option added in the sequence of FOLIO abstraction
configurations. `-nocrossstage` disables the cross-stage guard retry used
alongside the flat bases.

(The light shape-unification repair — predicate rename, shape bridges, compound composition,
broad-supertype `isa` — is part of `-s2split`, not a separate flag; see [translation](translation.md).)

### `-propclass`: property↔class canonicalization

The flat fold sometimes leaves **one concept in both predicate shapes** — a class atom
`isa(W,X)` and a property atom `has property(W,X,C)` — so a rule guard and the query (or two
premises) silently fail to unify.  `-propclass` injects bridge axioms (named `frm_propclass`)
that reconcile them, problem-locally, when both shapes occur:

- **SAFE — `isa(W,X) → has property(W,X,?:C)`** (class ⇒ property).  Sound for *any* `W`
  (a class member has the property in every context — hence the free context variable `?:C`),
  so it is **unconditional**.  Two trigger shapes:
  - *same word* — `W` appears as both `isa(W,·)` and `has property(W,·)` (e.g. the adjective
    `vertebrate` used as `isa` in one premise and `has property` in another);
  - *adjective-compound-modifier* — `isa("A N",X) → has property(A,X,?:C)`, where the compound
    class `"A N"` is present and its modifier `A` is used as a property (e.g. `isa("analog
    media") → has property("analog")`).  Noun modifiers never appear as `has property`, so
    noun-noun compounds (`music piece`) are excluded automatically.
- **PROMOTE — `has property(W,X,C) → isa(W,X)`** (property ⇒ class).  This asserts *permanent
  class membership*, so it is **conditional**: emitted only when `W` is a kind-naming **nominal
  compound** (it already has a `compound_sub` head, e.g. `animal lover → lover`) **and** is
  demanded as a guard (`-isa(W,·)` occurs).  Gradable/stage-level properties never qualify
  (they have no `compound_sub`, and gradables sit in `has degree property`, not `has property`),
  so a time/location-dependent property is never promoted to a stable class.

A single implication clause resolves both ways (modus ponens and modus tollens), so the SAFE
form also refutes; the bridges are strict (predicate identity is not defeasible).  Mechanism
reference: [logic compilation](logic-compilation.md).  Enabled by `-abstract-max`.

### `-numtype`: numeric-literal typing

A problem may reason about a number-type guard (`isa(number, N)`) without ever asserting the
typing fact, because gk has **no built-in `isa(number,·)`** — it is an ordinary predicate.
`-numtype` does two things:

- **parse** — rewrites pure-numeral string arguments (`"34"`, `"5.5"`, `"-3"`) to int/float
  across all clauses, so numbers are numbers (consistent unification; usable by gk
  arithmetically).  Entity names that merely *contain* digits ("Symphony No. 9 1") are not
  pure numerals and are untouched.
- **materialize** — emits a ground `isa(TYPE, N)` (named `frm_numtype`) when a number-like
  `TYPE` (`number`, `integer`, `float`, `real`, `decimal`, `natural number`, …) is **demanded**
  as a guard but never supplied.  The demand is read both directly (`-isa(TYPE,N)`) and through
  an equality binding in the same clause (`-isa(TYPE,V)` with `-=(V,N)`, the
  `isa(number,Y) ∧ Y=N → …` rule shape).  Always sound (`N` is a number); demand-conditioned, so it
  applies only where a rule needs the typing.

Fixes the FOLIO "begins-with-34" case where one plate's `isa(number,"35")` was asserted but
the other's `isa(number,"34")` was only ever a guard.  Injector reference: [logic compilation](logic-compilation.md).  Enabled by `-abstract-max`.

### `-compasym`: comparative antisymmetry

The flat / `-simpleprops` fold collapses a degree comparative `has_degree_rel2(R,X,Y,high)`
into a plain `is_rel2(R,X,Y)`, which bypasses the comparative-order axioms in `axioms_std.js`
the comparative-order axioms in `axioms_std.js` §5.2, which key on
`has_degree_rel2` with degree `high`.  `-compasym` re-emits the order
axiom for the flat form: for a relation `R` that occurs as a binary `is_rel2(R,X,Y)` and is a
**strict-scalar dimensional adjective**, it injects (named `frm_compasym`)

- **antisymmetry** `is_rel2(R,X,Y) ∧ is_rel2(R,Y,X) → X=Y` — two *distinct* entities cannot each
  be more-`R` than the other (refutes comparison cycles via entity UNA), while a reflexive
  self-comparison `is_rel2(R,A,A)` stays consistent.  (Antisymmetry, **not** strict asymmetry:
  abstraction sometimes collapses a "more-`R` than before" temporal comparison onto one constant
  — "Harry is smarter than before" → `is_rel2(smart,Harry,Harry)` — which strict asymmetry would
  wrongly make self-contradictory.)
- the flat **property bridge** `is_rel2(R,X,Y) → has_property(R,X)` when a `has_property(R,·)`
  consumer exists (the "X taller than Y → X is tall" analogue of [the source map](../code/source-map.md) for the flat form).

`R` is restricted to a curated positive list, `solver/comparable_adjectives.txt`, because
`gradables.txt` is contaminated for this purpose with **symmetric relations** (similar, near,
close, far, equal, different, adjacent, parallel — asymmetry is false) and **relational/attitude
verbs** (love, need, want, like — mutual).  No transitivity is emitted (problems that need it
supply it; a blanket transitive `is_rel2` risks blow-ups).  Injector reference:
[logic compilation](logic-compilation.md).  Enabled by `-abstract-max`.

### The nominal retry: dropped predicate-nominal Stage-2 retry

Unlike the primitives above, this is **not an encoding gate** (no `EncodingConfig` field) — it is
a parse-time **Stage-2 sanity check + corrective retry**.  Stage 1 may state a copular "ENT is a
NOUN" predication ("Rock 2 is a pet of Peter 1"; "The output 2 of MT is a text sequence"), but
Stage 2 sometimes drops the type — encoding only the entity category plus a relation
(`isa(animal,Rock)+have(Peter,Rock)`), or binding the property to a fresh dangling existential
(`exists Z. isa(text sequence, Z)`) instead of the named entity.  When the dropped `NOUN` is used
elsewhere in the logic but never asserted of `ENT`, the check emits an issue that drives the
existing corrective Stage-2 retry, which re-prompts the LLM to attach `isa(NOUN, ENT)`.  Full
mechanism: [translation](translation.md).  Enabled by `-abstract-max` (note: it can make live LLM retries).

---

## Default-path footprint

The event-encoding work leaves exactly two behaviors on the default (`-event
neodavidson`, no primitives) path: the ASCII fold of parses ([the source map](../code/source-map.md)) and the canonical
sanity-retry serialization ([translation](translation.md)).  Everything else in this chapter is enabled only by its option; with
no flags the pipeline is answer-equivalent to the `core-2026-06-03` checkpoint
(verified on a stratified 40-case × 4-LLM sample — byte-identical clauses modulo
set-iteration order and fresh-variable numbering).

---

## Abstraction presets (`-abstract` family)

The presets are pure CLI expansions into the [abstraction](abstraction.md) primitives — they are read nowhere in
the pipeline, only at argument-parse time (`solve.py`), where they set the primitive
option keys.  Three are defined:

- **`-abstract`** = `-event flat` + `-entitymerge` + `-guarddrop` + `-bridges` +
  `-dropdefinites` + `-typeenrich` + `-localantonyms` + `-simpleprops`.
- **`-abstract-roles`** = `-abstract` but with `-event flatroles`
  (eventprop-tagged objects).
- **`-abstract-max`** = `-abstract-roles` + `-prenorm` + `-propclass` + `-numtype` +
  `-compasym` + `nominalretry` + `negretry`, **plus the open-world repair stack** —
  all six stage keys of [configuration](../reference/configuration.md) on.  It is the strongest configuration and the FOLIO
  base.  `nominalretry_flag` and `negretry_flag` have no flag of their own; this
  preset is what sets them.

**`-abstract-max` makes LLM calls on every unresolved case.**  `-prenorm` adds one
call before Stage 1 ([translation](translation.md)); `nominalretry` and `negretry` can each trigger a
corrective Stage-2 re-parse ([translation](translation.md)); and of the six stages only the two fallbacks are
free — the critic adds one call, the graph translation about three and the graph
bridges about two more, the literal bridge one to five ([retries](retries.md)).  A replay of a stored result folder must therefore name the cancels
that folder ran with, and its `stages_enabled` field says which those were.

Because they expand into primitives, any preset composes with an explicit override
(e.g. drop one primitive by not letting the preset set it, or layer `-existfold`).

## The two abstention fallbacks

Both fallbacks convert the same parse a second time with some of the
switches on this page turned on, and call gk once more.
[Retries](retries.md) describes them.

## Related documentation

- [Proof shortening](proof-shortening.md)
- [Experimental options](../reference/experimental-options.md)
- [Logic compilation](logic-compilation.md)
- [Translation](translation.md)
- [Configuration](../reference/configuration.md)
- [Encoding reference](../encodings/README.md)
