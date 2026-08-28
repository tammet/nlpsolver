# Logic compilation

The deterministic path from a validated Stage-2 package to the clause list the
prover reads. No model call happens here.

The JSON formats themselves are defined in the
[encoding reference](../encodings/README.md): the Stage-2 package
grammar in [stage-2.md](../encodings/stage-2.md), and the clause
format, the `$ctxt` term, `$block` and the question encoding in
[gk-clauses.md](../encodings/gk-clauses.md). This page describes what
the compiler does between them.

The order of the passes, and which module owns each, is in
[code/logic-compilation.md](../code/logic-compilation.md).

## Package extraction

`_extract_package_ctx(package)` (in `logconvert.py`) unwraps a Stage-2 PACKAGE and returns
`(is_question, formula, confidence, world, location, knower, tense)`.

The PACKAGE shapes it handles:
- `["holds", W, F]` → `is_question=False`, `formula=F`, `world=W`
- `["question", F]` → `is_question=True`, `formula=F`
- `["ask", VAR, F]` → `is_question=True`, `formula=["ask",VAR,F]` (kept whole for wh-handling)
- `["and", PKG, ["@p","Sx",P], ["state time",W,T], ...]` → recurse into the main sub-package;
  collect confidence, tense, location, knower from siblings

After extraction, `_convert_id_package` overrides `tense`, `world`, and `location` with data
from the matching Stage-1 ASU (when `asu_index` is available).  Stage-1 data is authoritative
because it is produced closer to the English source.  The actual question/assertion logic is
delegated to `_process_question` (wh-/yes-no dispatch) and `_process_assertion` (confidence
handling + clausification).

## FOL to CNF clausification

`clausify(formula)` (in `lc_clausify.py`) converts a first-order formula into conjunctive normal
form through five passes:

1. **`_implies_to_or`** — eliminate `implies`, `equivalent`, `xor`:
   - `implies(A,B)` → `or(not(A), B)`
   - `equivalent(A,B)` → `and(implies(A,B), implies(B,A))`, then recurse
   - `xor(A,B)` → `and(or(A,B), or(not(A),not(B)))`
   - Does not recurse inside `_opaque_wrappers` (i.e. `normally`)

2. **`_push_neg`** — push negations inward to reach Negation Normal Form (NNF):
   - De Morgan: `not(and(...))` → `or(not(...),...)`, etc.
   - Quantifier duality: `not(forall X, P)` → `exists X, not(P)`
   - Atom negation: toggle the `"-"` prefix on the predicate name
   - `normally` treated as opaque: `not(normally(F))` → `"-normally"(F)`

3. **`_expand_normally` pass 1** — push `normally` inside complex bodies before Skolemisation:
   - `normally(exists X, B)` → `exists X, _push_normally_inside(B)`
   - `normally(and(A1,...,An))` → `and(A1,...,An-1, normally(An))`
   - Simple `normally(atom)` is left for pass 2

4. **`_skolemize(frm, universal_vars, varmap)`** — eliminate existential quantifiers:
   - `forall X, F` → recurse with `X` added to `universal_vars`
   - `exists X, F` → replace `X` with a Skolem term:
     - No universal vars in scope → Skolem constant `"sk0"`, `"sk1"`, …
     - Universal vars in scope → Skolem function `["sk0","?:X",...]` applied to those vars
   - `forall` is stripped (variables become free, i.e. implicitly universally quantified in GK)

5. **`_distribute`** — distribute `or` over `and` to reach CNF:
   - `or(and(A,B), C)` → `and(or(A,C), or(B,C))`
   - Recursive until no `or` wraps an `and`

6. **`_expand_normally` pass 2** — expand remaining `normally(atom)` into `$block` clauses:
   - See [logic compilation](logic-compilation.md) below

7. **`_extract_clauses`** — collect all flat clauses from the resulting `and` tree

## Defeasible expansion

After Skolemisation and CNF distribution, every `normally(atom)` appears inside an `or` clause
alongside conditions (negative literals `-isa bird ?:X`) and other conclusions.

`_expand_normally` pass 2 processes such an `or` clause:
1. Separate negative literals (conditions, start with `"-"`) from positive literals (conclusions).
2. Use the **last positive literal** as the head to be blocked.
3. Compute priority `["$", CLASS, N]`:
   - CLASS = class from the last `-isa` condition (e.g. `"bird"`), or `"$generic"` if no `-isa`
   - N = number of non-`isa` negative conditions + 1 (more specific rules get higher N)
4. Append `["$block", priority, ["$not", head]]` to the clause.

Result for `normally(["has part","?:X","wing"])` inside `["-isa","bird","?:X"]`:
```
["-isa","bird","?:X"], ["has part","?:X","wing"],
["$block",["$","bird",1],["$not",["has part","?:X","wing"]]]
```

A plucked-bird exception would generate priority `["$","bird",2]` (higher specificity), which
GK uses to defeat the general bird default.

With `-noexceptions`, the `$block` is suppressed and `normally` becomes equivalent to a strict
implication.

## Context injection ($ctxt)

After clausification, `_inject_ctxt_into_objs` (in `logconvert.py`) appends a
`["$ctxt",T,W,L,K]` term to every eligible predicate atom in every `@logic` clause.

The four `$ctxt` components per ASU:

| Component | Rules | Situational facts | Questions |
|-----------|-------|-------------------|-----------|
| tense T | fresh free var | Stage-1 `time` or `"present"` | Stage-1 `time` or fresh var |
| world W | fresh free var | Stage-1 `pre_state` or W from `holds` | Stage-1 `pre_state` or fresh var |
| location L | fresh free var | Stage-1 `location` or fresh var | Stage-1 `location` or fresh var |
| knower K | fresh free var | mental holder or fresh var | mental holder or fresh var |

Rules use fresh free variables for all four components so they match facts from any time/world.
Situational facts use concrete world/tense values so they match only facts in the same context.

Context injection can be disabled globally with `nocontext_flag`.  In that mode the
constant `"$c"` is injected as the last argument of every eligible atom (instead of
a `$ctxt` term), so axioms with `?:Ctxt` still unify while axioms with explicit
`$ctxt(...)` patterns become inert.

### Question-specific past↔present tense bridges

For each question package, after `$ctxt` injection, `lc_ctxt.build_question_tense_bridges`
collects present-tense or past-tense stative literals from the question and emits one
specialized bridge axiom per unique (predicate, args) signature.  Two question shapes
are scanned: a `$defq`-wrapped question exposes the stative goal as a **negative**
literal in its body→defq `@logic` clauses, while a **direct** `["@question", FORMULA]`
(an unguarded question that never became a `$defq`) carries it as a **positive** literal
— scanned by `_collect_question_goal_signatures`, since the goal becomes
`-pred(present)` once the prover negates it for refutation.  Without the direct-question
scan, an unguarded stative question (e.g. "who does the backpack belong to?" →
`@question: have(X, present)`) would miss the persistence bridge a guarded one receives.
The emitted bridge:

```
[-pred(args, $ctxt(opposite_tense, ?:W, ...)),
  pred(args, $ctxt(question_tense, ?:W, ...)),
  $block(0, $not(pred(args, $ctxt(question_tense, ?:W, ...))))]
```

Entity arguments are pinned to the constants from the question; free variables in the
question literal become fresh variables in the bridge.  Confidence per predicate:
0.97 for `have`, 0.95 for `is rel2` and `has degree rel2`, 0.99 for the others
(`has property`, `has degree property`, `has part`, `can`).

This replaces the disabled global Section 6a same-world tense bridges in
`axioms_std.js`.  Pinning entities keeps the search space small (the bridge can only
apply to facts about those specific entities), avoiding the prover slowdown caused by
the global axioms while bridging the same set of tense mismatches between
past-tense assertions and present-tense questions (and vice versa).

Scope: bridges are generated for question goals only. A stative literal that
needs cross-tense matching in a rule premise or in a `$block` blocker is not
bridged. The general form, covering premises and blockers as well, is not
implemented.

#### Stable-adjective assertion-side persistence (`inject_stable_adjective_persistence`)

The question-pinned bridges above cover the **question's** predicates.  They do **not**
cover an **assertion-side** property tensed at past whose value the question reaches only
through another axiom (e.g. a mutex).  Case 911 ("The man whom John saw **is** tall. Is the
man short?"): claude/gpt keep the sentence as one unit tagged `time=past`, so the present
copula "is tall" is contaminated by the embedded past relative ("whom John **saw**") →
`tall@past`.  The question is `short@present`; the tall/short mutex binds both literals to a
single shared `$ctxt` variable, so `tall@past` and `short@present` never contradict → Unknown.
The disabled §6a global bridge would have carried `tall@past → tall@present`, and the
question bridge only covers `short` (the question predicate), not the asserted `tall`.

`lc_post_inject.inject_stable_adjective_persistence` fills this gap.  For each
**individual-level (stable)** property present as a `has_property`/`has_degree_property`, it
injects a defeasible (0.95) same-world `past@W → present@W` persistence axiom with a
`$block($not present)` override, in both predicate forms — so a past stable property reaches
the present-tense reading.  `_STABLE_ADJS` is a curated 83-adjective list
(dimension/size/build, age, strength, mental/ability, character, beauty, value);
`_STABLE_PERSIST_PROPS` adds the **color/shape/material** value-sets (reused from the
attribute families / `data_exclusions`), 130 total.  **STAGE-LEVEL** (temporary) adjectives —
hot/cold, wet/dry, hungry/tired, open/closed, broken, full/empty, dirty/clean, sick, new —
and **taste** (gradable/perishable) are deliberately EXCLUDED: they should not persist.
Like the question bridges, it is dynamic (one pair of axioms per stable property present) and
conditional, so the search space stays small — but it is keyed on the **assertion-side** stable
property, the complementary half of the question-pinned bridges.  Closes case 911 (claude/gpt
2/4 → 4/4 via `tall@past → tall@present` + the tall/short mutex).

## Gradable property normalisation

`_normalize_gradable_predicates(result)` (in `logconvert.py`) iterates over all clauses and
applies `_norm_grad_frm` to every predicate atom:

- `has degree property PROP ...` where PROP is **not** in `_GRADABLE_PROPS`
  → convert to `has property PROP ENTITY` (drop degree/relclass)
- `has property PROP ...` where PROP **is** in `_GRADABLE_PROPS`
  → convert to `has degree property PROP ENTITY "none" RELCLASS` (add degree/relclass;
  RELCLASS = fresh free variable)
- `has degree property ... RELCLASS` where RELCLASS is `"entity"` or `"none"`
  → replace with a fresh free variable (neither carries a useful comparison-class constraint,
  and leaving them as constants would block unification against meaningful relclasses like
  `"person"`)

The same logic applies to `has degree rel2` vs `is rel2`.

After this normalisation, `_strip_isa_entity` removes any remaining `["isa","entity",X]` or
`["-isa","entity",X]` literals, since "entity" is universal:
- Positive `isa entity X` makes a clause a tautology → remove the entire clause
- Negative `-isa entity X` is always false → remove just the literal

## Population facts

`populate_clauses(items)` (in `lc_post_population.py`, using helpers from `lc_questions.py`) makes one
pass over all Stage-2 items before clausification and collects *population facts*: `isa TYPE
ENTITY` atoms for every concrete entity that appears as an argument of a `forall`-quantified
rule.  For example, if a rule says "all birds can fly" and a concrete entity `tweety 1` appears
as an `isa bird tweety 1` fact, that fact must be inserted before the question so the prover can
use it.

Population facts are tagged with `"@sourcetype": "populate"` internally (stripped before the
prover sees them) so that `_coerce_relclass` can treat them differently from question clauses.

**Compound witnesses.** When a rule's antecedent is a conjunction binding the same variable
to multiple atoms, `_scan_compound_antecedent` records a *compound witness* and the population
emits an intersection entity satisfying ALL the conjuncts simultaneously. Two flavors today:

- **Spatial**: `[isa, TYPE, X] ∧ [is_rel2/has_degree_rel2, prep, X, ground_target]` →
  `$some_<type>_<prep>_<location>` with both atoms.
- **Adjective**: `[isa, TYPE, X] ∧ [has_property, ATTR, X]` (or `has_degree_property` with
  intensity/relclass) → `$some_<attr>_<type>` with both atoms. Without this, defeasible
  rules of the form "ADJ TYPEs are not P" have no concrete witness for the prover to apply
  them to (case 74: "Red cars are not nice" was being closed via the more general
  "Cars are nice" rule alone, returning "Probably true" instead of the expected False).

## Rewrites and injected clauses

Between the passes above the compiler applies 45 named transformations: some
before clausification, on the Stage-2 formula, and some afterwards, on the
clause list. They repair inconsistent model output, apply pipeline conventions,
and add the clauses that connect one encoding of a fact to another.

Each is described in
[compilation transformations](compilation-transformations.md), which lists them
in the order their pass runs and gives each one a subsection.

## Typed Skolem constants

Skolem constants generated during clausification embed their type in the name when the type is known from the existential body:

- `["exists", "Y", ["and", ["isa","house","Y"], ...]]` → constant `"sk0_house"` (instead of `"sk0"`)
- Unknown type: plain `"sk0"` (backward compatible)
- Skolem functions (from rules with free variables) keep plain names: `["sk0", "?:X"]`

Helper functions in `lc_clausify.py`:
- `is_skolem_const(val)` — matches both `sk0` and `sk0_house` patterns
- `is_skolem_fn(val)` — matches list Skolem functions
- `skolem_type_from_name(name)` — extracts type: `"sk0_house"` → `"house"`, `"sk0"` → `None`

Skolem type resolution for rendering (`proof_answer_format._resolve_skolem_entity`):
1. **Fast path**: extract type from name via `skolem_type_from_name`
2. **Fallback**: look up type from `compute_skolem_types` clause-list scan (handles names without a type suffix and Skolem functions)

`compute_skolem_types(proof, logic=None)` in `proof_render.py` scans both the logic clause list (for types not used in the proof) and proof steps, populating `skolem_types` and `skolem_fn_types` tables.

---

## Entity UNA via `#:` prefix

The `gk` prover treats two distinct constants as definitely unequal **only when both are
prefixed with `#:`**.  Without UNA, a clause like `[¬is_rel2(on,X,Y1,C), ¬is_rel2(on,X,Y2,C),
=(Y1,Y2)]` (axioms_std.js §7g) cannot derive a contradiction from
`is_rel2(on, pizza, table)` plus the assumed-question `is_rel2(on, pizza, floor)` —
the prover would happily add `=(table, floor)` to its KB rather than detect the conflict.

`lc_post_una.py` runs at the end of `rawlogic_convert` and rewrites every Stage-1
numbered entity to its `#:`-prefixed form.  A string is wrapped iff **all three**
checks pass:

1. **Surface-form regex** — `^[A-Za-z][A-Za-z0-9_' -]* \d+$` (word + space + digits).
2. **Membership in the Stage-1 entity set** built from `s1_json -> packages -> units ->
   entities` — only ids that the LLM declared as concrete entities.
3. **Not Skolem-shaped** — `^sk\d+_…` excluded.

Skolem constants, function terms (`$theof1`, `$measure_of`), worlds (`W0`/`W1`), and
`$some_X` / `$some_not_X` constants are **not** wrapped.  These have their own
distinctness machinery (Skolems are pairwise distinct by construction; function terms
inherit equality from their arguments).  Broadening UNA to Skolems is intentionally
deferred — the conservative criterion is sufficient for the X2 case-148 closure on
LLMs whose Stage-2 produces concrete entity ids for definite descriptions.

The `#:` prefix is stripped at proof rendering time (`proof_utils.entity_name`,
`proof_logic._logic_name`) and at the top of `procproofs.process_proof` via
`_strip_una_prefix`, so user-facing answers are unaffected.

When deepseek emits a Skolem like `sk1_floor` for "the floor" (definite description),
UNA does NOT wrap it.  The closure path then runs through the noun-mutex axioms in
`axioms_std.js` §7g instead: `[¬isa(table, X), ¬isa(floor, X)]` (same-entity shortcut emitted by
`inject_exclusion_axioms` for NOUN_FURNITURE_FIXTURE) plus paramodulation through
the X2-derived equality.  See [generated data](../development/generated-data.md) for the mutex injector.

---

## Frame persistence and motion blocking

`axioms_std.js` [abstraction](abstraction.md) contains the **`is_rel2` tense-migration axiom**: a present-world `is_rel2(P, X, Y, ctx_present_W)` fact propagates to past worlds whenever `before(W_past, W_present)` holds.  This is what lets *"The cup is on the table. Was the cup on the table?"* close to True without an explicit past-tense fact.

The migration is **emitted only when two `$block`s**:
- `$block(0, moved(?:E1, ?:W_old))` — the entity moved AT the source world `W_old`.
- `$block(0, moved_between(?:E1, ?:W_old, ?:W_new))` — the entity moved at some
  INTERMEDIATE world strictly between `W_old` and `W_new`.

`moved(X, W)` is derived in `axioms_std.js` from `has_actor(E, X) + has_type(E, "go")` (the canonical movement event). `moved_between(X, W_old, W_new)` is derived from `moved(X, Wmid) + before(W_old, Wmid) + before(Wmid, W_new)`.

The source-world block alone is insufficient when the locatum's overriding move happens in a world *after* its present-location world but *before* the query world. In case 1327 ("Sandra travelled to the kitchen. Sandra travelled to the hallway. **Mary went to the bathroom.** Sandra moved to the garden. Where is Sandra?"), Sandra is at hallway at present-world W2, and her overriding move to garden is at W3 — an intermediate world. Because *Mary* (not Sandra) moved at W2, the source-world block didn't fire, so the stale hallway migrated to the W4 query and leaked into the answer ("At the garden **and at the hallway**"). The `moved_between` block catches the intermediate move (Sandra moved at W3, W2 < W3 < W4) and suppresses the migration. Non-movement relations (e.g. "afraid of") never derive `moved`, so they are unaffected.

**Known limitation:** with 4+ same-actor motion events in one problem (case 198), the prover's default strategy (`negative_pref` + `posunitpara`) struggles to enumerate the answer set within the 2-second budget.  The block is correct — the search blowup is a strategy issue, not an axiom issue.  Switching to `unit` or `query_focus` strategy can close such proofs but is not currently the default; see the *Prover-timeout suspected?* step in `CLAUDE.md` for diagnosis.

---

## Related documentation

- [Encoding reference](../encodings/README.md)
- [Questions, confidence and answers](questions-confidence-and-answers.md)
- [Reasoning and proofs](reasoning-and-proofs.md)
- [Translation](translation.md)
- [Abstraction](abstraction.md)
- [Compiler modules](../code/logic-compilation.md)
