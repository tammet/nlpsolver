# Logic compilation code

The compiler modules and the order of the passes.

[Architecture: logic compilation](../architecture/logic-compilation.md)
describes the transformations. This page describes the modules and the order
they run in.

## Pass order

`logconvert.rawlogic_convert` drives the compilation:

1. `lc_encoding.EncodingConfig` resolves the representation once, from the
   whole command line.
2. `lc_packages` splits the Stage-2 tree into one package per `@id`.
3. `lc_rewrites` and `lc_repairs` rewrite and repair the formula tree, and
   `lc_reference` restores references the two stages disagreed about.
4. `lc_coarse` runs the event folds, but only when the config asks for one.
5. `lc_davidson2` and `lc_existfold_v2` apply the two reversible
   proof-shortening rewrites, each declining per occurrence.
6. `lc_ctxt` injects the `$ctxt` term and strips the time wrappers.
7. `lc_clausify` turns FOL into CNF, Skolemising and expanding defaults.
8. `lc_questions` and `lc_query_guards` build the question clauses.
9. `lc_sets` handles sets and counting; `lc_entity_isa` adds taxonomy `isa`.
10. The post-clausification passes run over the clause list, and
    `lc_finalize` produces the final list.

`treewalk` holds the traversals the passes share.

## Modules

### logconvert.py and supporting modules

**Role:** Main driver for logic conversion — orchestrates the full Stage-2 JSON → GK clause
list pipeline.  The computation is split across these modules. Each entry
names what the module owns; the identifiers in it are its entry points.

- `logconvert.py` — top-level orchestration: `rawlogic_convert` entry point, the per-`@id` package loop, post-processing pass sequencing, and Stage-1 entity bookkeeping. The structural repairs, query-body simplification, entity-category enrichment, and strict/abstract finalisation are split into the `lc_*` modules below
- `lc_repairs.py` — pre-clausification structural repairs: id hoisting (`hoist_nested_ids`), misnested-implies repair (`repair_misnested_normally_implies`), the self-defeating-conditional engine (`repair_self_defeating_conditional`), the `-s2split` off-inventory predicate rename (`rename_offinventory_preds`), and `@definite` tag stripping (`strip_definite_tags`)
- `lc_query_guards.py` — query-body simplification: phantom isa-guard stripping (`strip_phantom_query_guards`: drop an orphan `isa(C,E)` guard from a query body when E is a Stage-1 entity never asserted and used nowhere else in the query — a leaked definite-description referent that would otherwise make the whole conjunctive query unprovable) and `"what"`-question population-fact generation (`generate_what_population`)
- `lc_entity_isa.py` — entity-category / typeenrich `isa` enrichment (`build_entity_category_clauses`: supertype / gender / name-as-type / compound atoms, conditional per `EncodingConfig.te(gate)`) and the typeonly-Skolem merge (`merge_typeonly_skolems`)
- `lc_finalize.py` — the strict / abstract clause finaliser (`finalize_strict_clauses`) split out of `rawlogic_convert`
- `lc_packages.py` — per-`@id` package processing: `extract_package_ctx`, `convert_id_package`, `_process_question`/`_process_assertion`, raw wh-word probes, confidence distribution
- `lc_rewrites.py` — pre-clausification formula rewrites (meta-predicate normalization incl. `"time of"`→`has_time`, tense-valued `has_time` stripping, verb normalization: travel/journey/move→go, hand/pass/send→give, receive→give with actor↔recipient swap, perspective-relation lift `["is rel2", got/received/saw/heard, X, Y]` → Davidsonian event, existential hoisting, spurious `can` removal, polarity flip)
- `lc_ctxt.py` — `$ctxt` injection, time-wrapper stripping, fresh variable generation
- `lc_post_normalize.py` — post-clausification normalising / repair passes: gradable normalization, RELCLASS coercion, `isa entity` stripping, degree stripping, compound subsumption extraction. Possessive-`have`/`has_part` bridges and population extraction are split out (next two rows)
- `lc_post_have.py` — possessive `have` / `have`↔`has_part` bridges: `add_possessive_have`, `add_haspart_for_typed_have`, `inject_have_to_haspart_axioms`
- `lc_post_population.py` — population-fact extraction and negative-witness walks: `populate_clauses`
- `lc_post_reify.py` — post-clausification reification of definite descriptions and measurements: `rewrite_definites` (`$theof1`), `rewrite_measure_terms` (`$measure_of`/`$measure`/`less_measure`)
- `lc_post_inject.py` — post-clausification dynamic axiom injection — the bridge/verb/world injectors: beneficiary↔`is rel2 "for"` bridge, carrier-vocabulary lift, verb-result-state bridges, acquire→have bridges, positional-preposition actor-location bridges (`inject_positional_actor_bridges`, case 670), `"filled with"`/`"full of"`→`in` containment bridges (`inject_containment_bridges`, case 673), attribute property↔relation bridges (color/shape/material/taste, `inject_attribute_relation_bridges`, case 901), stable-adjective past→present persistence (`inject_stable_adjective_persistence`, case 911 — see [logic compilation](../architecture/logic-compilation.md)), property↔class canonicalization (`inject_propclass_bridges`, `-propclass`/`-abstract-max` — see [logic compilation](../architecture/logic-compilation.md)), numeric-literal typing (`parse_numeric_literals` + `inject_number_typing`, `-numtype`), comparative antisymmetry (`inject_comparative_axioms`, `-compasym`), world-graph geometry. The KB-driven synonym/exclusion injectors are split out (next row); all injectors traverse via `treewalk.walk_result_atoms`
- `lc_inject_synonyms.py` — kB-driven soft-synonym + exclusion/mutex injectors: `inject_soft_synonyms`, `inject_exclusion_axioms` (incl. noun-mutex via `_ISA_EXCL_GROUPS`), `inject_isa_cross_group_axioms`, `inject_verb_mutex_axioms`, `inject_kinship_mutex_axioms`. Re-exported through `lc_post_inject` so importers are unchanged
- `lc_inject_scan.py` — shared clause-scan helpers used by the injectors: `collect_eligible_words`, `eligible_word`
- `treewalk.py` — shared formula-tree traversal: `walk_result_atoms(result, visit)` calls `visit(atom, base)` on each predicate atom of every `@logic`/`@question` body — the scan all injectors share
- `lc_post_una.py` — post-clausification UNA wrapping: prefix every Stage-1 numbered entity with `#:` so `gk` treats distinct entity constants as definitely unequal. Three-step criterion (regex + Stage-1 set + not-Skolem). Required by the X2 direct-support uniqueness axiom (axioms_std.js §7g)
- `lc_clausify.py` — fOL→CNF compilation
- `lc_questions.py` — question encoding and population fact builders
- `lc_sets.py` — set/counting: `$setof` rewriting, membership axioms, element instantiation


**Key function:** `rawlogic_convert(logic, s1_json=None) -> list | None`

Converts the Stage-2 nested JSON formula into a flat GK clause list:

```
["and", ["@id","S1",PACKAGE], ...] (Stage-2 input)
    │
    ├─ hoist_nested_ids(logic)            [lc_repairs] extract @id blocks nested by LLM bracket errors
    ├─ repair_misnested_normally_implies(logic)  [lc_repairs] ["normally",["implies",A],C] → ["normally",["implies",A,C]] (recover a consequent hung off `normally`; case 1418/1421 deepseek)
    ├─ _build_asu_index(s1_json)          build unit_id→ASU lookup from Stage 1
    ├─ rewrite_meta_predicates(logic)     [lc_rewrites] "located in"→"in", "is"→isa, "time of"→has_time, travel/journey/move→go, hand/pass/send→give
    ├─ rewrite_perspective_relations(logic) [lc_rewrites] lift ["is rel2", got/received/saw/heard, X, Y] into a Davidsonian event so the next pass can bridge it (covers gpt/deepseek relation-form encodings)
    ├─ normalize_receive_events(logic)   [lc_rewrites] receive→give with actor→recipient swap
    ├─ strip_tense_has_time(logic)       [lc_rewrites] remove has_time(E,"past",...) bogus atoms
    ├─ inject_actuality(logic)           [lc_rewrites] append ["actuality",E] to every Davidsonian event lacking a modal classifier ANYWHERE in the tree (tree-wide scan via _collect_classified_vars, not just direct siblings; skip inner content events) — case 1418: a `typical` nested in the event's own sub-block must still suppress actuality so a rule antecedent and its fact stay consistently marked
    ├─ inject_degree_presuppositions()    [lc_rewrites] "not very X" → X and not very X
    ├─ populate_clauses(items)            [lc_post_population] collect background facts
    │
    ├─ for each @id item:
    │    convert_id_package(item, asu_index)                   [lc_packages]
    │        extract_package_ctx()        unpack PACKAGE: formula, world, tense, etc. [lc_packages]
    │        override with Stage-1 ASU data (tense, world, location)
    │        compute latest world numerically for queries without pre_state
    │        default question tense to "present" when Stage 1 omits "time"
    │        generate $theof1/$datetime fact for explicit time values
    │        inject event has_time from Stage 1 if missing (repair for LLM omission)
    │        generate is_past_world(W) from state_tense="past"
    │        strip_spurious_can()          [lc_rewrites] remove non-modal "can"
    │        hoist_misnested_exists()      [lc_rewrites] fix variable scoping
    │        _process_question()           wh-/yes-no question dispatch [→ lc_questions]
    │        _process_assertion()          clausify + three-tier confidence distribution ([questions, confidence and answers](../architecture/questions-confidence-and-answers.md)) [→ lc_clausify]
    │        inject $ctxt into result      [lc_ctxt]
    │
    ├─ rewrite_definites() (global)        [lc_post_reify] $theof1 for all ASU definites
    ├─ rewrite_measure_terms()            [lc_post_reify] $measure→$list, less_measure rewrite, $theof1 unwrap in $measure_of
    ├─ insert population facts before first @question
    ├─ generate "what" population facts     for @what_query: isa(CLASS,$some_CLASS) from witnesses
    ├─ inject $ctxt into population facts  [lc_ctxt]
    ├─ inject_verb_result_state_axioms (extends `result` in place
    │    so the result-state property words become eligible for the
    │    exclusion injector below)                                       [lc_post_inject]
    ├─ inject_soft_synonyms / inject_exclusion_axioms /
    │    inject_isa_cross_group_axioms / inject_verb_mutex_axioms /
    │    inject_kinship_mutex_axioms                                     [lc_inject_synonyms]
    ├─ inject_beneficiary_for_bridge / inject_carrier_lifts             [lc_post_inject]
    ├─ add_possessive_have / add_haspart_for_typed_have /
    │    inject_have_to_haspart_axioms                                   [lc_post_have]
    ├─ normalize_gradable_predicates()    [lc_post_normalize]
    ├─ strip_isa_entity()                 [lc_post_normalize]
    ├─ coerce_relclass()                  [lc_post_normalize]
    ├─ strip_degree_predicates()          [lc_post_normalize] (only if -simpleprops)
    ├─ inject_world_geometry()            [lc_post_inject] minimal next chain over present worlds
    ├─ strip @sourcetype                  remove internal annotation before prover
    └─ apply_una(result, stage1_set)      [lc_post_una] wrap Stage-1 entities with #: prefix
```

**Counter globals** (reset at the start of each `rawlogic_convert` call):

- `lc_clausify._skolem_nr`, `lc_clausify._gobj_nr` — Skolem and generic-object counters
- `lc_questions._defq_nr` — `$defq` predicate name counter
- `lc_ctxt._fv_nr` — fresh free-variable counter (`?:Fv1`, `?:Fv2`, …)

See [logic compilation](../architecture/logic-compilation.md) for detailed discussion of the key algorithms.

### lc_clausify.py

**Role:** FOL → CNF clausification compiler.

**Public API used by `logconvert.py`:**

- `clausify(formula) -> list` — converts a first-order formula to a list of CNF clauses
- `looks_like_var(s) -> bool` — true if `s` matches Stage-2 variable pattern (`?:`-prefixed or single uppercase letter + digits) but NOT world constants
- `is_world_constant(s) -> bool` — true if `s` matches `W0`, `W1`, etc. (excluded from variable detection)
- `apply_varmap(formula, varmap) -> formula` — substitute variables by name
- `connectives` — frozenset of logical connective names (not predicates)
- `singularize_isa_classes_in_node(node) -> node` — recursively normalize the class argument
  (index 1) of every `isa` / `-isa` atom to singular.  Run by `rawlogic_convert` as a **late
  pass** over the whole clause list (after all injection, before UNA), so LLM-emitted assertions,
  injected population facts (`isa(C, $some_C)`), and `$defq` question guards all use the same
  class name.  Without it a bare-plural generic (`isa("animals", X)` from one sentence, or a
  Stage-1 generic entity whose **id** is plural while its **category** is singular) never unifies
  with the singular form used elsewhere or with the population witness, so an existential generic
  question (`∃X isa(C,X) ∧ BODY`) finds no witness → Unknown (case 211, gpt/claude/gemini).
  `_safe_singularize_class` guards the crude trailing-`s` heuristic, gating multi-word
  classes on their head (last) word.  It tests, in this order: a small irregular / mass-noun
  exception set (`news`, `scissors`, `series`, `species`, `rabies`, `caries`, …); a
  capitalized head, left intact as a proper noun; a one-letter head, left intact because
  stripping its only letter would leave a token ending in a space; the `-ies` rule, which
  gives berries → berry and activities → activity; and only then the `-us` / `-is` / `-ss` /
  `-es` / `-cs` guard (bus, analysis, class, potatoes, physics, roses), which leaves those
  intact.  The `-ies` rule must precede that guard, since every `-ies` plural also ends in
  `-es`; the singular `-ies` nouns are what the exception set is for.

**Clausification pipeline** (inside `clausify`):

```
_normalize_type_case
_strip_typical_from_antecedent
_expand_generic_objects
_normalize_quantifiers
_implies_to_or                 eliminate implies / equivalent / xor
_push_neg                      push negations in to reach NNF
_expand_normally (pass 1)      push normally inside exists/and
_skolemize                     eliminate existentials → Skolem terms
_distribute                    distribute or over and → CNF
_expand_normally (pass 2)      normally(atom) → $block clause
_extract_clauses               collect flat clause list
```

**Internal helpers** (extracted from `_expand_normally` and `_distribute`):

- `_flatten_or_elements(elements)` — flatten nested `or` wrappers in a list of formula elements
- `_classify_literals(lits)` — split literals into `(neg_lits, pos_lits)` by predicate polarity
- `_extract_isa_priority(neg_lits, blocker_class_tag, extra_neg)` — compute `$block` priority
  from negative literals and optional class tag

**Module-level counters** (reset externally by `rawlogic_convert`):

- `_skolem_nr` — next Skolem constant/function index
- `_gobj_nr` — generic-object counter for `_expand_generic_objects`

### lc_questions.py

**Role:** Wh-question encoding and population-fact collection.

**Public API used by `logconvert.py`:**

- `build_defq_question(name, ask_var, body, where_prep=None) -> list` — encode a wh- or yes/no
  question as `$defq` biconditional GK clauses
- `hoist_generic_yn_subject(formula, name) -> (skq, hoisted_atom, rewritten_body) | (None, None, formula)`
  — bare-plural-generic yes/no rewrite. Matches `forall X, isa(C,X) → normally(BODY)` (the
  Stage-2 [logic compilation](../architecture/logic-compilation.md)(a) shape), and on match returns a fresh skolem constant `skq_S<qid>_<C>`,
  a hoisted antecedent atom (or `["and", …]` when the antecedent had multiple atoms about
  X), and the consequent BODY with `X ← skq…` substituted in. `lc_packages._process_question`
  prepends the hoisted atom as a `@sourcetype: "question_subject"` fact and feeds the
  rewritten body to standard yes/no clausification, producing UDP-shaped `isa(C, skq) +
  $defq ↔ BODY[skq]` clauses (closes cases 213/214/215 across all four LLMs)
- `find_where_atom(body, ask_var) -> atom | None` — find the location atom in a where-question body
- `build_where_question(name, entity, ask_var, specific_prep=None) -> list` — encode a where-question
- `flatten_q_atoms(frm, varmap) -> list` — flatten an `ask` formula into a list of atoms
- `scan_item_formula(frm, name, polarity, classes, has_props, deg_props)` — scan a formula for
  isa / has-property / has-degree-property atoms, recording polarity in the provided dicts
- `build_population_facts(classes, has_props, deg_props) -> list` — build positive/negative
  synthetic population clauses from collected scan data
- `is_ground_term(t) -> bool` — true if `t` contains no variables
- `is_simple_question_formula(f) -> bool` — true if `f` is a single atom (not compound)
- `collect_body_free_vars(frm, bound=None) -> set` — free variables in a formula
- `find_haslocation_prep(body, ask_var) -> str | None` — return `"in"` if body contains
  `has_location` with the ask variable
- `simplify_contradictory_and(frm) -> formula` — simplify `["and", ["not", A], A]` to `["not", A]`
- `S2_VAR_RE` — regex matching Stage-2 variable names (uppercase-initial identifiers)
- `WHERE_SPATIAL_PREPS` — set of spatial prepositions handled as where-questions

### lc_sets.py

**Role:** Programmatic conversion of Stage-2 `$setof` terms into canonical form,
generation of membership axioms, and element instantiation.

**Entry point:** `process_sets(formula)` — called before clausification.  Returns
`(rewritten_formula, axioms, element_clauses)`.

**Two $setof forms:**

| LLM output | Canonical form | When |
|------------|---------------|------|
| `["$setof","?:X",["and",...conds with have...]]` | `["$setof","have","John 1",["$and",...$-prefixed...]]` | Stative anchor found (have, is_rel2, can) |
| `["$setof","?:X","set 1",["and",...conds...]]` | `["$setof","id","set 1",["$and",...conds...]]` | No anchor, set_id from Stage-1 |

**Conversion steps** (inside-out for nested $setof):
1. Detect anchor predicate in conditions; extract it
2. Replace bound variable with `$arg1` (`$arg2` for nested)
3. `$`-prefix predicates in anchored form; no prefix for conditions-only
4. Sort `$and` entries: `$isa`/`isa` first, rest alphabetically
5. Mutate the $setof node in place

**Membership axiom generation:** For each unique $setof pattern, a
`forall/biconditional` axiom is generated:
```
member(?:M, $setof(have, ?:S, [$and, $isa(?:C,$arg1), $prop(?:P,$arg1)]))
  <=> isa(?:C, ?:M) & prop(?:P, ?:M) & have(?:S, ?:M)
```
Concrete values in conditions are generalized to forall variables.

**Element instantiation:** For each positive `["=", N, ["$count", $setof_term]]`
in an assertion context (inside `holds`, not in queries), creates
`min(N, set_element_limit)` concrete element constants (`$setK_elI`) with:
- All set properties (un-prefixed predicates)
- Anchor predicate (if anchored)
- `member` assertions
- Pairwise distinctness (`["-=", el1, el2]`)

Configurable via `globals.options["set_element_limit"]` (default 3).

**Key functions:**
- `_classify_setof(conditions, var)` — detect anchor predicate
- `_rewrite_setof(node, depth)` — rewrite one $setof to canonical form
- `_build_membership_axiom(info)` — generate the forall/biconditional
- `_instantiate_elements(info, source_name, count)` — create element clauses
- `_instantiate_distributive_events(formula, setof_term, elements, source_name)` —
  create per-element event instances from forall/implies/member blocks

## Related documentation

- [Logic compilation](../architecture/logic-compilation.md)
- [Proof shortening](../architecture/proof-shortening.md)
- [Abstraction](../architecture/abstraction.md)
- [Encoding reference](../encodings/README.md)
- [Source map](source-map.md)
