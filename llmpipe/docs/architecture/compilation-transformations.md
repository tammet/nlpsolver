# Compilation transformations

The catalogue of the named rewrites and injected clause families the compiler
applies. [Logic compilation](logic-compilation.md) describes the sequence they
run in; this page describes each one.

A transformation exists for one of three reasons. Some repair model output that
breaks a rule the prompt states. Some apply a pipeline convention that Stage 2
is not asked to know about. Some add clauses that connect two encodings of the
same fact, so that a rule written in one shape can reach a premise written in
the other.

None of them is optional and none is selected by a command-line key. The
optional representations are on the
[abstraction](abstraction.md) page, and the exact clause shapes they produce
are in the [encoding reference](../encodings/README.md).

## The transformations, in pass order

The table lists every transformation in the order its pass runs. `pre` means it
rewrites the Stage-2 JSON formula before `clausify`; `post` means it changes the
GK clause list afterwards. Every name links to its subsection below.

| pass | transformation | implementation | purpose |
|---|---|---|---|
| pre | [Degree presupposition injection](#degree-presupposition-injection) | `lc_rewrites.inject_degree_presuppositions` | Keep the unmarked reading when a graded property is negated. |
| pre | [Stative event rewriting](#stative-event-rewriting) | `semnormalize.rewrite_stative_events` | Encode a stative verb as a direct relation instead of an event. |
| pre | [`@time` stripping](#time-stripping) | `lc_ctxt.strip_time_wrappers` | Move a tense wrapper onto the atom as a `$tense` sentinel. |
| pre | [Entity category injection](#entity-category-injection) | `lc_entity_isa.build_entity_category_clauses` | Add the Stage-1 category of an entity that Stage 2 typed differently. |
| pre | [Entity base-word isa](#entity-base-word-isa) | `lc_entity_isa.build_entity_category_clauses` | Also type an entity by its own base word, not only its category. |
| pre | [Compound subsumption](#compound-subsumption) | `lc_post_normalize.build_compound_subsumption` | Let a rule about the base type reach a compound type. |
| post | [`$ctxt` injection](#ctxt-injection) | `lc_ctxt.inject_ctxt_into_objs` / `inject_ctxt_question` | Give each eligible atom its world, tense and situation term. |
| post | [Descriptive/stative/dynamic split](#descriptivestativedynamic-split) | `lc_ctxt.inject_ctxt_question` | Choose the world a question atom is asked in, by atom kind. |
| post | [Gradable normalisation](#gradable-normalisation) | `lc_post_normalize.normalize_gradable_predicates` | Convert between plain and graded property predicates. |
| post | [`isa entity` stripping](#isa-entity-stripping) | `lc_post_normalize.strip_isa_entity` | Drop the tautological `isa(entity,X)` literal. |
| post | [RELCLASS coercion](#relclass-coercion) | `lc_post_normalize.coerce_relclass` | Free a comparison class that the question and the rule disagree on. |
| post | [`$theof1` definite rewrite](#theof1-definite-rewrite) | `lc_post_reify.rewrite_definites` | Make the several spellings of one definite description the same term. |
| post | [Possessive `have` inference](#possessive-have-inference) | `lc_post_have.add_possessive_have` | Derive `have` from a possessive relation. |
| post | [`have` → `has_part` bridge for typed body-part nouns](#have--has_part-bridge-for-typed-body-part-nouns) | `lc_post_have.add_haspart_for_typed_have` | Connect the two spellings Stage 2 uses for body parts, per problem. |
| post | [`have` → `has_part` axiom bridge](#have--has_part-axiom-bridge) | `lc_post_have.inject_have_to_haspart_axioms` | The same connection as a rule, for the types a rule quantifies over. |
| post | [Misnested existential hoisting](#misnested-existential-hoisting) | `lc_rewrites.hoist_misnested_exists` | Bind an existential variable that Stage 2 left free in a sibling. |
| post | [Tense-valued `has_time` filter](#tense-valued-has_time-filter) | `lc_rewrites.strip_tense_has_time` | Remove a `has_time` atom that repeats the tense already in `$ctxt`. |
| post | [Negative tense-agreement `has_time` strip](#negative-tense-agreement-has_time-strip) | `lc_rewrites.strip_neg_tense_agreement_in_clause` | The same removal inside a negated literal. |
| post | [`actuality(E)` injection](#actualitye-injection) | `lc_rewrites.inject_actuality` | Mark an event as real when no other modal classifier applies. |
| post | [Meta-predicate normalization](#meta-predicate-normalization) | `lc_rewrites.rewrite_meta_predicates` | Rewrite a meta-level predicate into the ordinary form. |
| post | [Perspective verb → dative head normalization](#perspective-verb--dative-head-normalization) | `lc_rewrites.normalize_receive_events` | Give a perspective verb the same roles as its dative counterpart. |
| post | [Set existence fact](#set-existence-fact) | `lc_sets._walk_for_count` | State that a counted set exists. |
| post | [Degree stripping](#degree-stripping) | `lc_post_normalize.strip_degree_predicates` | Drop the degree arguments under `-simpleprops`. |
| post | [Semantic normalisation](#semantic-normalisation) | `semnormalize.sem_normalize_clauses` | Fold antonyms and substitute canonical words. |
| post | [Soft synonym injection](#soft-synonym-injection) | `lc_inject_synonyms.inject_soft_synonyms` | Add the synonym axioms the case's own vocabulary needs. |
| post | [Exclusion injection](#exclusion-injection) | `lc_inject_synonyms.inject_exclusion_axioms` | Add mutual-exclusion axioms for words that cannot both hold. |
| post | [Cross-group noun mutex](#cross-group-noun-mutex) | `lc_inject_synonyms.inject_isa_cross_group_axioms` | Separate nouns from different exclusion groups. |
| post | [Carrier vocabulary lift](#carrier-vocabulary-lift) | `lc_post_inject.inject_carrier_lifts` | Tag plates, trays and similar objects as carriers. |
| post | [Entity UNA wrapping](#entity-una-wrapping) | `lc_post_una.apply_una` | Make two distinct named entities unequal. |
| post | [World-graph geometry](#world-graph-geometry) | `lc_post_inject.inject_world_geometry` | State how the world states of the case relate. |
| post | [Verb mutex injection](#verb-mutex-injection) | `lc_inject_synonyms.inject_verb_mutex_axioms` | Separate verbs that cannot describe the same event. |
| post | [Verb-result-state injection](#verb-result-state-injection) | `lc_post_inject.inject_verb_result_state_axioms` | Derive the state a verb leaves behind. |
| post | [Acquire→have bridge](#acquirehave-bridge) | `lc_post_inject.inject_acquire_have_axioms` | Derive possession from an acquisition event. |
| post | [Measure→relation bridge](#measurerelation-bridge) | `lc_post_inject.inject_measure_relation_bridges` | Turn a measurement into the comparison relation it supports. |
| post | [Negative-implicative bridge](#negative-implicative-bridge) | `lc_post_inject.inject_negative_implicative_bridges` | Derive that a refused action did not happen. |
| post | [Perception-factive bridge](#perception-factive-bridge) | `lc_post_inject.inject_perception_factive_bridges` | Derive that a perceived event happened. |
| post | [Positional-preposition actor-location bridge](#positional-preposition-actor-location-bridge) | `lc_post_inject.inject_positional_actor_bridges` | Give an event's actor the event's location. |
| post | [Containment bridge](#containment-bridge) | `lc_post_inject.inject_containment_bridges` | Derive that the contents of a full container are in it. |
| post | [Attribute property↔relation bridge](#attribute-propertyrelation-bridge) | `lc_post_inject.inject_attribute_relation_bridges` | Connect an attribute value to the attribute relation. |
| post | [Stable-adjective past→present persistence](#stable-adjective-pastpresent-persistence) | `lc_post_inject.inject_stable_adjective_persistence` | Carry a stable adjective from a past world into the present. |
| post | [Property↔class canonicalization (`-propclass`)](#propertyclass-canonicalization--propclass) | `lc_post_inject.inject_propclass_bridges` | Connect the two shapes a flat fold leaves one concept in. |
| post | [Numeric-literal typing (`-numtype`)](#numeric-literal-typing--numtype) | `lc_post_inject.parse_numeric_literals` + `inject_number_typing` | Read a numeral string as a number and type it on demand. |
| post | [Comparative antisymmetry (`-compasym`)](#comparative-antisymmetry--compasym) | `lc_post_inject.inject_comparative_axioms` | State that a strict comparison cannot hold both ways. |
| post | [Kinship mutex injection](#kinship-mutex-injection) | `lc_inject_synonyms.inject_kinship_mutex_axioms` | Separate kinship relations that cannot both hold. |
| post | [`@sourcetype` stripping](#sourcetype-stripping) | Serialisation (`clause_list_to_json`) | Keep internal tags out of the prover input. |

Each transformation has a subsection below.

### Degree presupposition injection

**Purpose.** Keep the unmarked reading when a graded property is negated.

**Example.** "John is not very big" → adds "John is big" (unmarked degree) alongside the negated "very big"

**Transformation.** `["not",["has degree property",P,E,"high",C]]` → `["and",["has degree property",P,E,"none",C],["not",...]]`

**Implementation.** `lc_rewrites.inject_degree_presuppositions`

### Stative event rewriting

**Purpose.** Encode a stative verb as a direct relation instead of an event.

**Example.** "John had a car" encoded as an event → rewritten to direct `have(john,car)`

**Transformation.** Replaces Davidsonian event encoding of stative verbs (have, own, like, love, etc.) with direct predicates.  Safety: only rewrites when the event variable has no extra properties (has_location, etc.)

**Implementation.** `semnormalize.rewrite_stative_events`

### `@time` stripping

**Purpose.** Move a tense wrapper onto the atom as a `$tense` sentinel.

**Example.** "John was tall" — the past-tense `@time` wrapper becomes a `$tense` sentinel controlling the tense slot in `$ctxt`

**Transformation.** Converts `["@time","past",ATOM]` wrappers into `$tense` sentinels on the atom

**Implementation.** `lc_ctxt.strip_time_wrappers`

### Entity category injection

**Purpose.** Add the Stage-1 category of an entity that Stage 2 typed differently.

**Transformation.** Adds `isa(CATEGORY, ENTITY)` facts from Stage-1 entity annotations.  Skipped when the entity already has a **positive-polarity** isa in Stage-2 (`collect_positive_isa_entities` tracks polarity through connectives, negation, implications, and low-confidence packages).  Entities in negated or low-confidence contexts are NOT skipped — they need the injection.  Exact duplicates with `sent_S*` clauses are removed by `_dedup_entity_clauses`.

**Example.** "John is an elephant" — Stage-1 says John's category is "person", so `isa(person, John 1)` is added even though Stage-2 only emits `isa(elephant, John 1)`

**Implementation.** `lc_entity_isa.build_entity_category_clauses`

### Entity base-word isa

**Purpose.** Also type an entity by its own base word, not only its category.

**Example.** "A man had a car" — entity `man 1` has category "person", but the base word "man" is also a type; adds `isa(man, man 1)` alongside `isa(person, man 1)`

**Transformation.** For concrete entities with a lowercase base word different from the category, injects `isa(BASE, ENTITY)` so queries using the descriptive type word can match

**Implementation.** `lc_entity_isa.build_entity_category_clauses`

### Compound subsumption

**Purpose.** Let a rule about the base type reach a compound type.

**Example.** "Baby birds do not fly" — adds a rule that baby birds are birds, so general bird rules can apply to them

**Transformation.** Adds `isa(BASE, X) :- isa(COMPOUND, X)` rules for compound types

**Implementation.** `lc_post_normalize.build_compound_subsumption`

### `$ctxt` injection

**Purpose.** Give each eligible atom its world, tense and situation term.

**Example.** "John was tall" → atom gets `$ctxt(past,W0,?,?)` anchoring it to the past in world W0

**Transformation.** Appends `["$ctxt",T,W,L,K]` to eligible predicate atoms.  Rules: all-free-var.  Assertions: concrete world/tense.  Questions: see next row ([logic compilation](logic-compilation.md))

**Implementation.** `lc_ctxt.inject_ctxt_into_objs` / `inject_ctxt_question`

### Descriptive/stative/dynamic split

**Purpose.** Choose the world a question atom is asked in, by atom kind.

**Transformation.** Three-way $ctxt world dispatch in `$defq` questions: (1) **descriptive** atoms (isa, event atoms, properties when a main relation is present) each get an independent free-var world; (2) **stative matrix** predicates (have, can, has part) get free-var world — persistent states don't need concrete world anchoring; (3) **dynamic matrix** predicates (is_rel2, properties when no main relation) keep the query's world.  `_question_has_main_relation` detects whether properties are restrictive modifiers.  Each descriptive/stative atom gets its OWN fresh world variable to avoid forced co-unification across different world states

**Example.** "Did the man have the red car which a woman bought?" — `bought` events and `red` property each get independent free-var worlds; stative `have` also gets free-var world; only dynamic event predicates (if matrix) keep the query's world

**Implementation.** `lc_ctxt.inject_ctxt_question`

### Gradable normalisation

**Purpose.** Convert between plain and graded property predicates.

**Example.** "John is big" — LLM used `has property(big,...)` but "big" is in the gradable whitelist → upgraded to `has degree property`

**Transformation.** Whitelist-based `has property` ↔ `has degree property` conversion; replaces `"entity"` and `"none"` relclass with free variables ([logic compilation](logic-compilation.md))

**Implementation.** `lc_post_normalize.normalize_gradable_predicates`

### `isa entity` stripping

**Purpose.** Drop the tautological `isa(entity,X)` literal.

**Example.** "Every entity that is big is strong" — `isa(entity,X)` is always true, so the clause is a tautology → removed

**Transformation.** Removes tautological `isa(entity,X)` literals ([logic compilation](logic-compilation.md))

**Implementation.** `lc_post_normalize.strip_isa_entity`

### RELCLASS coercion

**Purpose.** Free a comparison class that the question and the rule disagree on.

**Transformation.** Fixes relclass mismatches. Question-side: `has degree rel2` always coerces to free var; `has degree property` coerces in two cases — case_a: the relclass IS one of the entity's isa classes but no rule uses it as a relclass for this property (spurious category); case_b (case 1418 gemini): the relclass is NOT one of the entity's isa classes but one of the entity's actual classes IS used as a relclass for this property by a rule (the question used a super/sibling category, e.g. "animal" while the rule's consequent uses "bear"). Assertion-side (new): coerces when the fact's relclass is either (a) one of the entity's multiple isa classes while another class of the entity also appears as a rule-side relclass for the same property, or (b) not in the entity's isa classes while some isa class of the entity appears as a rule-side relclass — both symptoms of stage-1 generic-category leakage. `prop_relclasses` is built from both positive and negated literals so rule bodies contribute.

**Example.** (question) "Is John big?" — query uses relclass "person" (John's category) but the rule uses "bear" → relclass replaced with free variable; (assertion) "John is a nice big bear. John is nice." — stage-1 split loses the "bear" context and tags "nice" with relclass "animal" while the rule expects "bear" → assertion's "animal" replaced with a free variable

**Implementation.** `lc_post_normalize.coerce_relclass`

### `$theof1` definite rewrite

**Purpose.** Make the several spellings of one definite description the same term.

**Transformation.** Replaces flat entity IDs for definite functional descriptions with canonical function terms so that "the father of John", "John's father", and wh-queries all refer to the same term.  Triggered by Stage-1 `definites` field.  Primary: matches `is_rel2` clause.  Fallback: matches `have` + `isa` pair.  The formerly-universal `have` bridge in `axioms_std.js` (`[have, ?:S, $theof1(?:R,?:S,?:C), ?:C]`) has been removed because its free `?:S` let the prover satisfy any wh-possession query with a free-variable witness; `rewrite_definites` now emits the needed grounded possession fact directly.  **Chain-rewrite guard:** `_find_is_rel2_match` skips any `is_rel2` atom whose value-slot already holds a `$theof1` term — a previous pass has already reified this slot, and a second pass with a different `type_base` would silently overwrite the existing type label.  This is the case-79 sister/brother trap: with two definites pointing to the same entity but using different relation types ("Sara, the sister of Mike" + "Sara is the brother of Mike?"), the second pass would otherwise rewrite `$theof1("sister",...)` → `$theof1("brother",...)` and break downstream mutex reasoning.

**Example.** "The father of John is nice" — `"the father 2"` → `["$theof1","father","John 1",CTXT]` throughout all clauses; `is_rel2` clause removed; per-relation `isa`/`is_rel2` bridge axioms generated as `frm_theof`; grounded `have(arg,$theof1,ctxt)` fact emitted for the concrete owner

**Implementation.** `lc_post_reify.rewrite_definites`

### Possessive `have` inference

**Purpose.** Derive `have` from a possessive relation.

**Transformation.** Infers `have(Y,E,CT)` from possessive `is_rel2` patterns.  Handles ground entities, Skolem functions, and `$theof1` terms.  For rule clauses with guard literals (e.g., `[-isa,elephant,?:X]`), generates conditional `have` with the same guard.  Skips `@name=frm_theof` clauses (the universally-quantified per-relation schema axioms) because processing them would regenerate the universal have bridge that was removed for free-variable-witness reasons (see `$theof1` definite rewrite row above).

**Example.** "The handle of the fork" — `is_rel2(handle of, fork, handle)` + `isa(handle, handle)` → `have(fork, handle)`

**Implementation.** `lc_post_have.add_possessive_have`

### `have` → `has_part` bridge for typed body-part nouns

**Purpose.** Connect the two spellings Stage 2 uses for body parts, per problem.

**Transformation.** **Conservative, problem-local bridge.**  Stage-2 LLM is inconsistent: generic universal claims ("Elephants have trunks") use `has_part`, but specific instance claims with adjectives ("John has a long trunk") often use `have` for some LLMs (gemini, gpt) — which then fail to unify with has_part-using rules.  Pass 1 walks rule clauses and collects the set of types T paired with `-has_part(?:X,?:Y)` AND `-isa(T,?:Y)` for the same `?:Y`; if empty, the bridge does nothing.  Pass 2 collects explicit `isa(T, E)` facts for ground/Skolem entities.  Pass 3 walks single-atom positive `have(X, Y, Ctxt)` clauses; for each, looks up Y's type (explicit isa first; else `_parse_entity_name_type` fallback peels off Stage-2's naming convention "trunk 1" → "trunk", "sk0_trunk" → "trunk") and emits `has_part(X, Y, Ctxt)` only when the type intersects the rule-collected set.  Safe under the subtype rule in `axioms_std.js` because that rule requires `isa(Y1, Y2)` where Y1 is a class with subtypes; specific entities are not classes so the inheritance never propagates back to a class.

**Example.** Rule "If an animal has a trunk, it is an elephant" Stage-2-encoded with `-has_part(?:X,?:Y,Ctxt)` and `-isa(trunk,?:Y)`; fact "John has a long trunk" Stage-2-encoded as `have(John 1, trunk 1, Ctxt)` + `isa(trunk, trunk 1)` → emit `has_part(John 1, trunk 1, Ctxt)` so the rule applies (case 207).

**Implementation.** `lc_post_have.add_haspart_for_typed_have`

### `have` → `has_part` axiom bridge

**Purpose.** The same connection as a rule, for the types a rule quantifies over.

**Transformation.** **Axiom-shape counterpart to `add_haspart_for_typed_have`** — same rule-premise scan to collect the conditional type set T (a type T qualifies when some rule clause contains both `-has_part(_,?:Y,_)` and `-isa(T,?:Y)` on the same variable), but emits a **universally-quantified axiom** per type rather than a per-fact derivation.  Needed because `add_haspart_for_typed_have` only walks single-atom positive `have` facts, while case 6's `have` atoms live inside multi-literal query clauses (`[have(?:X, sk1(?:X), Ctxt), $defq0(?:X)]`).  Complements `axioms_std.js` [the pipeline](pipeline.md) which ships only the converse direction `has_part → have`.  **No `$block` guard.**  The standard `$block(0, $not(consequent))` pattern would self-block here: the proof chain requires combining the bridge's positive `has_part` with the rule's negative `has_part`, but that very negative `has_part` is independently derivable, so the block would suppress the bridge before it can fire.  Confidence weighting alone (0.9 × rule confidence) is enough to demote the bridged conclusion below a directly-asserted contradicting fact.

**Example.** Rule "Elephants do not have wings" Stage-2-encoded with `-has_part(?:X,?:Y,Ctxt)` and `-isa(wing,?:Y)`; query "Who does not have a wing?" Stage-2-encoded with `-have(?:X,?:Y,Ctxt)` and `-isa(wing,?:Y)` → emit axiom `[-isa(wing,?:Y), -have(?:X,?:Y,?:Ctxt), has_part(?:X,?:Y,?:Ctxt)]` at confidence 0.9; the contrapositive `isa(wing,Y) ∧ -has_part(X,Y) → -have(X,Y)` lets the negative rule body refute the negative query (case 6).

**Implementation.** `lc_post_have.inject_have_to_haspart_axioms`

### Misnested existential hoisting

**Purpose.** Bind an existential variable that Stage 2 left free in a sibling.

**Transformation.** Pre-clausification fix for assertion formulas.  Detects existential variables used free in sibling conjuncts before their `exists` binding, hoists the binding to wrap the entire conjunction.  Only applies in assertion contexts (from `holds`), with collision checks against enclosing bindings.

**Example.** `[exists E, [and, has_actor(E,X), [exists X, isa(bear,X)]]]` → `[exists E, [exists X, [and, has_actor(E,X), isa(bear,X)]]]`

**Implementation.** `lc_rewrites.hoist_misnested_exists`

### Tense-valued `has_time` filter

**Purpose.** Remove a `has_time` atom that repeats the tense already in `$ctxt`.

**Transformation.** Pre-clausification narrowing pass.  `["has time", E, "past"|"present"|"future", "in"]` is the canonical shape for grammatical tense on Davidsonian events (instructed by Stage-2 [configuration](../reference/configuration.md)). The pass scans the tree once via `_collect_event_vars` to identify all variables `X` such that `isa(activity, X)` appears, then strips tense-valued `has_time` only when the first argument is NOT one of those event variables.  Strips misplaced `state_time(W, TENSE)` from formula bodies unconditionally.

**Example.** `has_time(E, "past", "in")` survives when E is a Davidsonian event variable; same shape on a non-event variable is stripped; in-body `state_time(W, "past")` is always stripped (belongs at the package level)

**Implementation.** `lc_rewrites.strip_tense_has_time`

### Negative tense-agreement `has_time` strip

**Purpose.** The same removal inside a negated literal.

**Transformation.** **CLAUSE-level** pass — runs post-clausification, invoked from `logconvert.rawlogic_convert` right after the isa-class singularize pass (not from the pre-clausification `strip_tense_has_time` tree pass).  Such a negative literal is a vacuous query escape: the event's grammatical tense is already carried by the `$ctxt` slot and normalised any-tense→past for past worlds by the axioms_std.js §D "Context Tense Normalization" block (which is value-preserving, so it never manufactures `has_time(E, "past")`).  Requiring the event-level tense over-constrains a yes/no question whose matching assertion expresses time via a temporal **modifier** instead — "The letter was written in June. Was the letter written?" gives the assertion event `has_time(E, "June", "in")`, which never unifies with the question's `has_time(E, "past", "in")`, so the proof fails on the value mismatch (case 709).  Dropping only the negative literal lets the question match via the surviving `has_type`/`has_target` atoms (bridged across the `$ctxt` tense by §D); the positive `has_time` fact is kept because it is redundant-but-true.  The `value == $ctxt-tense` gate is what makes it safe: a real modifier ("June") or a value/context mismatch (`has_time(E,"past",$ctxt("present"))`) never matches and is preserved.

**Example.** In a clause's literal disjunction, drops a NEGATIVE literal `["-has time", E, T, Prep, ["$ctxt", T, …]]` whose tense value `T` (past/present/future/timeless) **equals** the `$ctxt` tense slot.  Positive `has_time` literals and single-literal clauses are untouched; never empties a clause.

**Implementation.** `lc_rewrites.strip_neg_tense_agreement_in_clause`

### `actuality(E)` injection

**Purpose.** Mark an event as real when no other modal classifier applies.

**Transformation.** Pre-clausification injection.  Walks the formula tree; for every Davidsonian event variable introduced by `isa(activity, E)`, appends `["actuality", E]` to the same `and`-block unless one of the eight Stage-2 modal classifiers (`typical`, `capability`, `necessity`, `obligation`, `volition`, `intention`, `expectation`, `speech_act`) already attaches to E, OR E appears as the second argument of `has_content(E1, E)` whose OUTER event E1 is **non-factive** — i.e. E1's verb is NOT a causative in `_CAUSATIVE_CONTENT_VERBS` (`have`/`make`/`let`/`force`/`cause`/`get`).  The content of intention/speech reifications and non-factive verbs (`try`/`attempt`/…) is not actual, but a causative's embedded event really occurs, so `has_content` of a causative `have` still gets `actuality` (case 1616: "had the mechanic fix the car" → the mechanic really fixed it; a verb whitelist rather than a mode blacklist, because "try" carries no modal classifier yet "John tried to open the door" ⇏ opened — cf. cases 1592/1593).  Idempotent — guards against re-injection on a second pass.  Consumed by the `axioms_std.js` [the source map](../code/source-map.md) actuality→capability bridge, which is applies only when `actuality(E)` instead of "any Davidsonian event", letting the bridge dispatch positively on real events rather than negating eight other classifier predicates.

**Example.** An `and`-block containing `isa(activity, E)` plus any of `has_type`/`has_actor` and no modal classifier on E gets `["actuality", E]` appended.  Stage 2 does not emit this marker; the pipeline adds it post-Stage-2.

**Implementation.** `lc_rewrites.inject_actuality`

### Meta-predicate normalization

**Purpose.** Rewrite a meta-level predicate into the ordinary form.

**Transformation.** Pre-clausification rewrite applied to all formulas.  Normalizes copula (`is` → `isa`), identity (`=`), spatial meta-predicates (`located in/at/on/near/above/under` → bare preposition), movement verbs (travel/journey/move → go), placement verbs (place/set/lay/position/deposit → put), transfer verb synonyms (hand/pass/send → give), and ownership relations to canonical `have(owner,thing)` — passive `belonged to`/`belongs to`/`owned by`/`possessed by` (owner at arg 3, swapped) and active `owns`/`own`/`owned`/`possess(es/ed)` (owner at arg 2) — so a possessive assertion and a "who owns / whose" query share the `have` predicate.  Also normalizes 3-arg `has_destination(E,Dest)` to 4-arg `has_destination(E,Dest,"at")` for backward compat with stale Stage-2 cache entries.

**Example.** `["is rel2","is",A,B]` → `["isa",A,B]`; `["is rel2","=",A,B]` → `["=",A,B]`; `["is rel2","located in",A,B]` → `["is rel2","in",A,B]`; `["is rel2","belonged to",THING,OWNER]` → `["have",OWNER,THING]`

**Implementation.** `lc_rewrites.rewrite_meta_predicates`

### Perspective verb → dative head normalization

**Purpose.** Give a perspective verb the same roles as its dative counterpart.

**Transformation.** Formula-level rewrite: in `and`-blocks containing a perspective-verb event (receive, get, hear, see), the verb is changed to its dative head (give, tell, show) and the actor role is swapped to recipient.  Single mapping table `_PERSPECTIVE_TO_DATIVE`; function name retained for back-compat.  Asymmetry preserved — the rewrite never adds an actor for events lacking an explicit dative agent, so "Did John receive a book?" still fails when John was the giver.  Allows the give-based transfer axioms in `axioms_std.js` to derive `have(Recipient, Object)` in the next world state, and lets queries about hear/see/get match facts about tell/show/give.

**Example.** `["has type",E,"receive"]` + `["has actor",E,X]` → `["has type",E,"give"]` + `["has recipient",E,X]`.  Same pattern for hear→tell, see→show, get→give.

**Implementation.** `lc_rewrites.normalize_receive_events`

### Set existence fact

**Purpose.** State that a counted set exists.

**Transformation.** Generates a ground set membership fact for assertion-context `forall/member` patterns so the prover can bootstrap resolution through member-guarded clauses.  Skipped when the set already has element instantiation from a count assertion.

**Example.** "Bears ate berries" with `forall/implies/member/$setof` in assertion context → `member("$some_bear", $setof(...))`

**Implementation.** `lc_sets._walk_for_count`

### Degree stripping

**Purpose.** Drop the degree arguments under `-simpleprops`.

**Example.** With `-simpleprops`: `has_degree_property(big,X,none,animal)` → `has_property(big,X)`

**Transformation.** (Only with `-simpleprops`) Replaces degree predicates with simple property predicates

**Implementation.** `lc_post_normalize.strip_degree_predicates`

### Semantic normalisation

**Purpose.** Fold antonyms and substitute canonical words.

**Transformation.** Antonym resolution (~311 directional pairs, adjective + noun only: flip polarity + swap word) and canonical substitution (~752 pairs: synonym → canonical form).  Skips `$ctxt` terms.  Polarity-flipping is applied ONLY at the top-level literal — inside nested function terms (`$theof1`, `$measure_of`, Skolem), only canonical substitution runs (flipping `$theof1` to `-$theof1` would produce invalid terms).  Data loaded from generated `data_antonyms.py` and `data_canonicals.py`.  Verb antonyms (`ant_v.txt`) are intentionally excluded from rewriting — most are perspective inversions (give/take, buy/sell), process complementarities (start/stop, come/go), or weak pairs where polarity-flip is wrong, and key verbs collide with axiom-vocab predicates (case 171).  Useful verb subsets (attitude pairs like like/dislike) are scheduled for re-introduction via a defeasible attitude-mutex injector.  `build_antonyms` also skips any pair whose canonical target is itself a CANONICALS key — such chain-through pairs are deferred to `build_exclusions` and emitted as synthetic `ANT_<W1>_<W2>` exclusion groups instead (prevents Pass 2 from chain-substituting the fold target to an unrelated sense, e.g. `open→close→near`).

**Example.** "The ball is outside the box" → `outside` is antonym of `inside` → flips polarity and substitutes: `-is_rel2(inside,ball,box)`

**Implementation.** `semnormalize.sem_normalize_clauses`

### Soft synonym injection

**Purpose.** Add the synonym axioms the case's own vocabulary needs.

**Example.** "The car is red" + axioms mention "crimson" → emits `red(X,Ct) <=> crimson(X,Ct)` biconditional

**Transformation.** Dynamic injection of Tier B synonym axioms for words present in both input and axiom vocabulary.  Templates: `has property` (adj), `isa` (noun), `has type` (verb).

**Implementation.** `lc_inject_synonyms.inject_soft_synonyms`

### Exclusion injection

**Purpose.** Add mutual-exclusion axioms for words that cannot both hold.

**Transformation.** Dynamic injection of mutual-exclusion axioms from `excl_a.txt` and `excl_n.txt` groups.  `needs_blocker=True` groups use defeasible `$block`; `False` groups are hard exclusions. Five atom shapes: default `has_property` (adjective); `_IS_REL2_EXCL_GROUPS` (MONTH/DAY_OF_WEEK/SEASON) — `is_rel2` target at arg 3; `_IS_REL2_PREP_GROUPS` (SPATIAL_*, TEMPORAL_ORDER) — `is_rel2` preposition at arg 1 with two free entity variables; `_HAS_DEGREE_REL2_PREP_GROUPS` (PROXIMITY) — `has_degree_rel2` preposition at arg 1 with two asymmetric axioms per pair; `_ISA_EXCL_GROUPS` (NOUN_*) — concept name at `isa` arg 1, emits both same-entity shortcut `[-isa w1 ?:X, -isa w2 ?:X]` and cross-entity inequality `[-isa w1 ?:X, -isa w2 ?:Y, -=(?:X, ?:Y)]`. Also injects `MANUAL_ANTONYMS` adjective pairs as synthetic `MANUAL_ADJ_<W1>_<W2>` groups, and chain-rejected antonym pairs (from `build_antonyms`) as synthetic `ANT_<W1>_<W2>` defeasible adjective groups. See [generated data](../development/generated-data.md) for preposition handling. **Note**: the seven preposition groups in `_STATIC_PREP_EXCL_GROUPS` (SPATIAL_VERTICAL/_OVER_UNDER/_SAGITTAL/_CONTAINMENT/_LATERAL, TEMPORAL_ORDER, PROXIMITY) are skipped here — their mutual-exclusion axioms live statically in `axioms_std.js` §7e because both sides are first-class predicates in the standard ontology.

**Example.** "The car is blue. Was it red?" → emits `NOT blue(X,Ct) OR NOT red(X,Ct)` with `$block`

**Implementation.** `lc_inject_synonyms.inject_exclusion_axioms`

### Cross-group noun mutex

**Purpose.** Separate nouns from different exclusion groups.

**Example.** "John is a car. Is the cat an animal?" → derives John ≠ cat

**Transformation.** Layer 2 of noun mutex. For pairs `(w1, w2)` from different `_ISA_EXCL_GROUPS` groups (e.g. `car` in NOUN_VEHICLE, `animal` in NOUN_TOP_LEVEL), emits the same two shapes as the within-group injector. Same REQUIRE_BOTH_SIDES gating.

**Implementation.** `lc_inject_synonyms.inject_isa_cross_group_axioms`

### Carrier vocabulary lift

**Purpose.** Tag plates, trays and similar objects as carriers.

**Example.** "pizza on plate" present → emits `[¬isa(plate,X,Ct), isa(carrier,X,Ct)]`

**Transformation.** Tags entities of carrier-noun categories so the static carrier-transparency axiom (`axioms_std.js` §7f) can apply. Carrier list: `_CARRIER_NOUNS = {plate, tray, saucer, dish, newspaper, napkin, tablecloth, mat, rug, carpet}`.

**Implementation.** `lc_post_inject.inject_carrier_lifts`

### Entity UNA wrapping

**Purpose.** Make two distinct named entities unequal.

**Transformation.** Wraps every Stage-1 numbered entity with `#:` prefix so `gk` treats distinct entity constants as definitely unequal. See [logic compilation](logic-compilation.md) for the three-step criterion. Required by axioms_std.js §7g (X2 direct-support uniqueness).

**Example.** After all post-processing: `is_rel2(on, "pizza 2", "table 3", …)` → `is_rel2(on, "#:pizza 2", "#:table 3", …)`

**Implementation.** `lc_post_una.apply_una`

### World-graph geometry

**Purpose.** State how the world states of the case relate.

**Transformation.** Dynamic injection of the minimal `next(Wi,Wi+1)` chain spanning the concrete world constants actually present in the clause list. Replaces the static `W0..W12` chain that used to live in `axioms_std.js` [abstraction](abstraction.md). Skips emission entirely when ≤1 world is present (most single-tense problems); otherwise fills any gaps in `[min_idx, max_idx]` so `before` transitivity still closes. Keeps the `before` derivation graph small.

**Example.** "Mary slept. Mary is awake. Was Mary awake?" → emits `next(W0,W1)`

**Implementation.** `lc_post_inject.inject_world_geometry`

### Verb mutex injection

**Purpose.** Separate verbs that cannot describe the same event.

**Transformation.** Dynamic, cross-event mutex (distinct from `inject_exclusion_axioms`, which mutexes adjective properties on a single entity).  Pair table `_VERB_MUTEX_PAIRS` currently lists `(pass, fail)`.  Each pair emits a defeasible 0.85 axiom with `$block` so that an explicit positive can override.  Atom shape uses `has_type` event predicates plus shared `?:E` and `?:Ctxt`.  Does not fire unless both verbs of the pair appear in the input clauses.

**Example.** "Did everyone pass the exam? — No, Mary failed." → for each entity with both `pass` and `fail` events on it, emits a defeasible mutex preventing the same event from being both

**Implementation.** `lc_inject_synonyms.inject_verb_mutex_axioms`

### Verb-result-state injection

**Purpose.** Derive the state a verb leaves behind.

**Transformation.** For each `(verb, past_participle)` pair in `_VERB_RESULT_STATES = {(destroy, destroyed), (break, broken), (damage, damaged), (complete, completed), (kill, killed), (repair, repaired)}` whose verb appears in the input, emits TWO defeasible (0.9) bridge axioms covering both Stage-2 encodings. Bridge A (event-based, gemini/deepseek): `has type E V Ct + has target E X Ct + next W W2 → has property <pp> X [present W2 ...]`. Bridge B (stative property-name, claude): `has property V X [_ W _ _ _] + next W W2 → has property <pp> X [present W2 ...]`. Both target the same `present @ next-world` slot so mutex axioms apply on the question's present-tense reading regardless of LLM encoding. Wired into `rawlogic_convert` BEFORE `inject_exclusion_axioms` so the result-state words become eligible for the exclusion injector (e.g. enables `destroyed/intact` mutex when "destroy" is in the input). `(finish, finished)` is intentionally omitted because `axioms_std.js` covers it statically.

**Example.** "The city was destroyed" → emits bridges to `has property "destroyed" #:city @ present @ next-world`

**Implementation.** `lc_post_inject.inject_verb_result_state_axioms`

### Acquire→have bridge

**Purpose.** Derive possession from an acquisition event.

**Transformation.** Lexical inference "actor acquires X ⊢ actor has X", modeled on the static `axioms_std.js` §5b give→have and on `inject_verb_result_state_axioms` (fresh free-vars, next-world present result). **Bridge A** (`_ACQUIRE_VERBS = (buy, purchase, acquire, obtain)`, defeasible 0.9): `has type E V Ct + has actor E X Ct + has target E Obj Ct + next W W2 → have X Obj [present W2]`, with a `$block` escape. Keys on the **actor** (not the recipient) because the "for whom" role is encoded inconsistently across LLMs (`has_beneficiary` / `has_recipient` / dropped) while every parse carries `has_actor` — so Bridge A reaches all of them. `take`/`get` are excluded as too polysemous ("take a walk", "get tired"). **Bridge B** (`_ACQUIRE_BENEFACTIVE = (buy, get)`, 0.95): the `has_beneficiary` AND `has_recipient` own the target — the benefactive-ditransitive "X bought Y a Z" gift reading; narrower verb set (you cannot "obtain Bill a car"). Unlike give→have it needs **no** `transferred`-block (an acquisition has no named party that loses the object). Closes case 1163 (1/4 → 4/4). Known limitation: "X bought Y a car. Does X have a car?" — Bridge A defeasibly over-emits `have(X,…)` (Bridge B gives the correct `have(Y,…)`); a guarded `$block` on beneficiary≠actor would close it.

**Example.** "Susan bought herself a new car. Who owns a new car?" → emits `have(Susan, car) @ present @ next-world` from the buy event

**When it applies.** applies only when verb presence; wired into the `sem_axioms` list.

**Implementation.** `lc_post_inject.inject_acquire_have_axioms`

### Measure→relation bridge

**Purpose.** Turn a measurement into the comparison relation it supports.

**Transformation.** Dynamic, per measure noun N. Emitted ONLY when the clause list contains BOTH a `$measure_of(N,...)` term AND an `is_rel2 "N of"` atom (so the bridge can connect a measure fact to a relational query, and only then). Generalises to any measure noun (length / price / weight / height / …) — N is read from the clauses, not a hard-coded list. Clause is `value=E1, subject=E2`, matching how Stage 2 emits `is_rel2 "<noun> of"`. Replaces a former static per-noun block in `axioms_std.js`. Lets a relationally-phrased measure question reach the `$list` value rather than only the definite description; the resulting two-answer set (description + value) is collapsed to the value by the `$list` answer-preference in `procproofs` (see [the source map](../code/source-map.md), step 4b).

**Example.** "The length of the car is 80 km. What is the length of the car?" (relational `is_rel2 "length of"` query) → emits `=($measure_of(length,S,W), V) → is_rel2("length of", V, S, Ct)`

**Implementation.** `lc_post_inject.inject_measure_relation_bridges`

### Negative-implicative bridge

**Purpose.** Derive that a refused action did not happen.

**Transformation.** Dynamic, one clause per verb in `refuse`/`decline`, emitted only when the verb appears. Mirror of the [source map](../code/source-map.md) factive bridge in the negative direction: a refused action did not actually happen. The refused inner content event carries no actuality (so it never matches an "actual event" query); this constraint additionally forbids any other actual event of the same verb/actor/target, so the query proves **False** (not just Unknown). Replaces a former static `axioms_std.js §5` block. **`forget` (case 1599)** is added via `_NEG_IMPLICATIVE_CONTROL_VERBS`: the same clause plus an extra `has_actor(E1, X)` constraint tying the forgetter to the content's actor — "forget **to** V" (same-subject control) applies, but the factive "X forgot **that** [other] V'd" (→ P true) does not. refuse/decline need no such gate (always same-subject).

**Example.** "Tom refused to eat the soup. Tom ate the soup?" → emits `refuse(E1) ∧ has_content(E1,E2=V(X,Y)) → ¬(actual E3 = V(X,Y))`

**Implementation.** `lc_post_inject.inject_negative_implicative_bridges`

### Perception-factive bridge

**Purpose.** Derive that a perceived event happened.

**Transformation.** Direct perception is FACTIVE: "X was heard/seen to V" entails V actually happened. Positive counterpart of the [source map](../code/source-map.md) assertive factive bridge, keyed on the PERCEPTION verb (`hear`/`see`/`watch`/`observe`/`notice`/`witness`) — no `speech_act` classifier. Defeasible 0.95 with a `$block($not actuality)` escape, one clause per perception verb present. Cases 1601/1603 (Unknown → True); 1602 stays Unknown (`actuality(enter)` ≠ leave).

**Example.** "Mary was heard to sing. Mary sang?" → emits `perceive(E1) ∧ has_content(E1,E2) → actuality(E2)`

**When it applies.** Applies only to perception of an event (`has_content`), not of an object (`has_target`). **Requires** the companion guard in `lc_rewrites.normalize_receive_events`: the perspective→dative rewrite (hear→tell, see→show) skips any event holding a `has_content`, so "hear"/"see" survive for this bridge.

**Implementation.** `lc_post_inject.inject_perception_factive_bridges`

### Positional-preposition actor-location bridge

**Purpose.** Give an event's actor the event's location.

**Transformation.** Dynamic completion of the static in/at actor-location bridges (`axioms_std.js` §5e, whose positional siblings are commented out). For POSITIONAL prepositions `_POSITIONAL_PREPS = {behind, in_front_of, beside, next_to, near, by, left_of, right_of}` that locate the actor AT the landmark (unlike support preps on/under, which attach to the target). One defeasible-0.9 bridge (with `$block($not is_rel2)`) per positional preposition actually present in a `has_location` atom. Keys on `has_location` (event locale), not `has_destination`/`has_direction` (motion goal). Preposition canonicalisation (`lc_rewrites._PREP_CANONICAL`) makes both `has_location` and `is_rel2` use the underscored forms. Case 670 (2/4 → 4/4; bonuses 671/676/1298).

**Example.** "The car parked behind the house was blue. The car was behind the house?" → emits `has_location(E,L,behind) ∧ has_actor(E,X) → is_rel2(behind, X, L)`

**Implementation.** `lc_post_inject.inject_positional_actor_bridges`

### Containment bridge

**Purpose.** Derive that the contents of a full container are in it.

**Transformation.** "X filled with Y" / "X full of Y" entails Y is IN X. `_CONTAINMENT_RELS = {filled with, full of}`. The gpt variant that packs the content into the property NAME (`has_degree_property("filled with water", cup)`) is instead handled by `_check_stage2_multiword_property` ([the source map](../code/source-map.md)). Case 673.

**Example.** "The cup filled with water fell. The cup contained water?" → emits `is_rel2("filled with", cup, water) → is_rel2("in", water, cup)`

**When it applies.** When such a relation appears as `is_rel2`/`has_degree_rel2`, injects a STRICT one-way bridge `¬<rel>(X,Y) → is_rel2("in", Y, X)` per (relation, predicate-form) present — PRESERVING the original relation (an added entailment, NOT a rewrite; "Y in X" does not imply X full of Y), like the static `contains↔in` (axioms_std.js §1).

**Implementation.** `lc_post_inject.inject_containment_bridges`

### Attribute property↔relation bridge

**Purpose.** Connect an attribute value to the attribute relation.

**Transformation.** A property VALUE in an attribute family equals the attribute RELATION. `_ATTRIBUTE_FAMILIES` = color (`COLOR_BASIC`+`COLOR_EXTRA`), shape (`SHAPE_BASIC`), material (`MATERIAL_BASIC`), taste (`TASTE`) — value-sets reused from `data_exclusions`; each carries its relation names (`color of`/`color`, `shape of`/`shape`, `material of`/`made of`/…, `taste of`/`flavor`/…). For each family whose relation is QUERIED (an `is_rel2` relation) and whose value is PRESENT as a property, injects BOTH arg-orders from the post-normalize `has_property` form. Generalises and replaces the dead static "red→color of" stub (axioms_std.js §8), which covered one colour/arg-order and fatally expected `has_degree_property` (colours normalise to `has_property`). Case 901 (2/4 → 4/4; bonus 987).

**Example.** "The car which John drove was red. What color was the car?" → emits `has_property(red, X) → is_rel2("color of", red, X)` / `is_rel2("color", X, red)`

**Implementation.** `lc_post_inject.inject_attribute_relation_bridges`

### Stable-adjective past→present persistence

**Purpose.** Carry a stable adjective from a past world into the present.

**Transformation.** See [logic compilation](logic-compilation.md) — fills the assertion-side gap that the question-pinned tense bridges miss, for individual-level (stable) properties (`_STABLE_PERSIST_PROPS`: 83 stable adjectives + color/shape/material). Case 911.

**Example.** "The man whom John saw is tall. Is the man short?" → emits `has_degree_property(tall, X, …, past@W) → has_degree_property(tall, X, …, present@W)` so the tall/short mutex meets the present query

**Implementation.** `lc_post_inject.inject_stable_adjective_persistence`

### Property↔class canonicalization (`-propclass`)

**Purpose.** Connect the two shapes a flat fold leaves one concept in.

**Transformation.** Reconciles one concept the flat fold left in **both** shapes (`isa(W,·)` class atom and `has_property(W,·,·)` property atom), so a rule guard and the query/fact unify. **SAFE** `isa(W,X)→has_property(W,X,?:C)` (class⇒property, sound for any W → unconditional, free context var): applies to a *same word* `W` in both shapes, or for an *adjective-compound-modifier* `isa("A N")→has_property(A)` where modifier `A` is used as a property (noun modifiers never are, so noun-noun compounds like "music piece" are excluded). **PROMOTE** `has_property(W,X,C)→isa(W,X)` (property⇒class, asserts permanent membership → conditional): only when `W` is a kind-naming **nominal compound** (it already has a `compound_sub` head, e.g. animal lover→lover) AND is demanded as a guard (`-isa(W,·)` present); gradable/stage-level properties never qualify (no `compound_sub`; gradables sit in `has_degree_property`). A single implication clause refutes too (modus tollens). Strict clauses, `@name="frm_propclass"`, applies only when `EncodingConfig.propclass`. In `-abstract-max`. Fixes FOLIO 50/51/100/101/184, 0 regressions.

**Example.** "No digital media are analog. Printed text is analog media." → `has_property(analog,X)` vs `isa("analog media",X)` never unify; emits `isa("analog media",X) → has_property(analog,X,?:C)`. "Pet owners love animals" (→`has_property(animal lover,X)`) vs "Animal lovers are nice" (→`isa(animal lover,X)`) → emits the promote `has_property(animal lover,X,C) → isa(animal lover,X)`

**Implementation.** `lc_post_inject.inject_propclass_bridges`

### Numeric-literal typing (`-numtype`)

**Purpose.** Read a numeral string as a number and type it on demand.

**Transformation.** Two steps: **parse** rewrites pure-numeral string args (`"34"`, `"5.5"`) to int/float across all clauses (entity names with digits like "Symphony No. 9 1" are untouched); **materialize** emits a ground `isa(TYPE, N)` (`@name="frm_numtype"`) for a number-like `TYPE` (number/integer/float/real/decimal/…) **demanded** but unsupplied. gk has no built-in `isa(number,·)`, so the fact must be asserted. The demand is read directly (`-isa(TYPE,N)`) and through an in-clause equality binding (`-isa(TYPE,V)` with `-=(V,N)`). Sound (N is a number); demand-conditioned. In `-abstract-max`. Fixes FOLIO 75, 0 regressions (17 numeric cases).

**Example.** "…begins with 34" with `isa(number,"35")` asserted but `isa(number,"34")` only a guard → materializes `isa(number, 34)`

**When it applies.** applies only when `EncodingConfig.numtype`.

**Implementation.** `lc_post_inject.parse_numeric_literals` + `inject_number_typing`

### Comparative antisymmetry (`-compasym`)

**Purpose.** State that a strict comparison cannot hold both ways.

**Transformation.** The flat/`-simpleprops` fold collapses `has_degree_rel2(R,X,Y,high)` to plain `is_rel2(R,X,Y)`, bypassing the comparative-order axioms of `axioms_std.js`, which key on `has_degree_rel2`. For a relation R used as binary `is_rel2(R,X,Y)` and listed in `solver/comparable_adjectives.txt` (curated strict-scalar dimensional adjectives — excludes symmetric relations similar/near/equal/… and attitude verbs love/need/…), emit **antisymmetry** `is_rel2(R,X,Y)∧is_rel2(R,Y,X)→X=Y` (NOT strict asymmetry: a reflexive "smarter than before" → `is_rel2(smart,Harry,Harry)` must stay consistent, case 89) + the flat property bridge `is_rel2(R,X,Y)→has_property(R,X)` when a `has_property(R,·)` consumer exists. `@name="frm_compasym"`, applies only when `EncodingConfig.compasym`. In `-abstract-max`. Fixes FOLIO 115, 0 regressions.

**Example.** "Peter is taller than Michael … is Peter shorter than a man in the class?" → emits `is_rel2(tall,X,Y)∧is_rel2(tall,Y,X)→X=Y` so the Peter↔man comparison cycle refutes via UNA

**Important restrictions.** No transitivity (problems supply it).

**Implementation.** `lc_post_inject.inject_comparative_axioms`

### Kinship mutex injection

**Purpose.** Separate kinship relations that cannot both hold.

**Transformation.** Dynamic gender-paired role mutex covering 16 pairs: kinship (sister/brother, daughter/son, mother/father, wife/husband, aunt/uncle, niece/nephew), grand- (grandmother/grandfather, granddaughter/grandson), step- (step{mother,father,daughter,son,sister,brother}), god- (godmother/godfather), status (widow/widower, bride/groom), royalty (queen/king, princess/prince).  Each pair emits two atom shapes: `isa` 3-arg (no `$ctxt`) and `is rel2 "X of"` 5-arg with shared `$ctxt`.  Interacts with the `$theof1` chain-rewrite guard above — without that guard, two definites carrying both kinship roles for the same entity would chain-collapse and the mutex would never apply.

**Example.** "Sara is the sister of Mike. Is Sara the brother of Mike?" → emits `isa(sister,X) ∧ isa(brother,X) → false` (and the matching `is_rel2 "X of"` mutex)

**Implementation.** `lc_inject_synonyms.inject_kinship_mutex_axioms`

### `@sourcetype` stripping

**Purpose.** Keep internal tags out of the prover input.

**Example.** Population facts carry `@sourcetype:"populate"` internally for processing — stripped before the prover sees them

**Transformation.** Internal `@sourcetype` tags are excluded from prover input

**Implementation.** Serialisation (`clause_list_to_json`)

## Related documentation

- [Logic compilation](logic-compilation.md)
- [Encoding reference](../encodings/README.md)
- [Abstraction](abstraction.md)
- [Compiler modules](../code/logic-compilation.md)
