# Proof processing

The GK call, answer selection, proof extraction, source tracing and English
rendering.

[Architecture: reasoning and proofs](../architecture/reasoning-and-proofs.md)
describes what happens. This page describes the modules.

## Modules

### prover.py

**Role:** Interface to the `gk` binary theorem prover.

**Key function:** `call_prover(logic) -> str`

1. Serialises the GK clause list to a JSON string using `clause_list_to_json` (from `utils.py`).
2. Writes the string to a temporary file.
3. Launches the `gk` binary via `subprocess.Popen` with the temp file plus flags built from
   `globals.options` (axiom files, strategy, time limit, print level, KB flags).
4. Reads stdout, decodes as ASCII, optionally caches the result, removes the temp file.
5. Returns the raw prover output string (JSON).

**Auto strategy selection** (`_auto_strategy`): when no `-strategy` flag is given,
analyses the clause list for equalities with function terms (`$measure_of`, `$theof1`,
`$list`, `$datetime`) or `less_measure` atoms.  When found, selects the `unit` strategy
(`-strategytext`) which handles equational reasoning better than the default
`negative_pref/posunitpara` strategy (empirically better than
`negative_pref/knuthbendix_pref` on complex multi-existential queries).
Printed with `-debug`.  Alternate strategies worth trying on timeout-suspected cases:
`{"strategy": ["unit"], "query_preference": 1}` and
`{"strategy": ["query_focus"], "query_preference": 1}`.

**Prover seconds auto-estimation** (`_estimate_seconds`): when no CLI `-seconds` is
given, counts distinct world constants (W0, W1, ...) in the clause list and scales
the time limit from an empirical table (2x safety multiplier).  Examples: ≤6 worlds →
2s (default), 7 → 4s, 8 → 10s, 9 → 20s, 10 → 60s, 11 → 300s.  CLI `-seconds N`
always overrides the estimate.

Key paths (from `globals.py`):

```
../gk/gk                      binary
llmpipe/axioms_std.js          default axiom file
../gk/gk_name_number.txt       name→number data
../gk/gk_taxonomy_packed.txt   taxonomy data
```

The `../gk` folder is a local installation of the GK reasoner; the
authoritative GK distribution (all-platform binaries, reference docs,
examples) is https://github.com/tammet/gkreasoner. `../gk/README.md`
summarises the installation and the exact invocation.

### procproofs.py + proof_answer_select.py + proof_answer_format.py

**Role:** Post-processing of raw prover output into a human-readable answer.

`procproofs.py` is the orchestrator; the two heavy halves live in sibling modules:

| Module | Role |
|--------|------|
| `procproofs.py` | `process_proof` — the pipeline: parse prover JSON, strip the `#:` UNA prefix, drive selection then formatting, dispatch explanation. Plus `_parse_result`, `_strip_una_prefix`. |
| `proof_answer_select.py` | Decides WHICH bindings survive: tier ranking, measure preference, unbound/leak/tautology filters, proof dedup. |
| `proof_answer_format.py` | Renders the surviving bindings into English: who/what/where/when/bool formatters + the `@…_query`/`@askvars` shape probes. |

The dependency graph is acyclic: `proof_answer_select` ← `proof_answer_format` ← `procproofs`.
`proof_answer_format` imports just `_extract_class_names` and `_ans_object_tier` from
`proof_answer_select`; selection imports nothing from formatting.

**Key function:** `process_proof(proof_result, text=None, s1_json=None, logic=None, options=None) -> str`

1. Parses the raw prover JSON string.
2. Checks for `"result": "answer found"`.  Returns `"Unknown."` if not found.
3. Sorts answers by `_answer_goodness` (confidence desc, proof length asc).
4. Filters to the best object-type tier: concrete entities > Skolem constants > population facts.
   For `@what_query` the population-vs-concrete preference is split by query shape
   (`_what_query_is_relational`, classifying by the answer variable's role and looking
   through any `$defq` wrapper):
   - **Relational** what-query — the answer variable is a relatum of an `is_rel2` /
     `has_degree_rel2` atom (e.g. "What is X afraid of?" → `is_rel2("afraid of", X, ?)`).
     The *kind* is the natural answer, so the population class beats a real concrete
     instance (`population_beats_concrete=True` in `_filter_by_best_tier`): "A cat.",
     not the incidental "Emily." (and not "Gertrude and Winona" when several instances
     exist).
   - **Classification** what-query — the answer variable is the entity of an `isa` atom
     ("What is an Estonian city?" → `isa(estonian_city, ?X)`).  A real concrete entity
     still wins: `Tallinn` beats "a city in Estonia" (cases 1258/1259).
   Resolves Skolem function answers to class names via `get_skolem_fn_type`.
4a. **Unbound-answer filter** (`_answer_all_unbound`): drops answers whose `$ans`
   answer-positions are entirely unbound `?:` variables.  These arise when a goal
   is proved without ever instantiating the answer variable — e.g. a relationally
   phrased query closed via a reflexive `$theof1` axiom, binding the definite
   description but leaving `$ans` free — and would otherwise leak the bare
   variable name (`"X3."`).  An unbound answer var is never a real binding.
4b. **`$list` value-preference** (`_prefer_measure_value_answers`): when any answer
   binds a measure value (`$list`, possibly nested in a `$get_world`/`$ctxt`
   wrapper), keep only the `$list` answers.  This collapses the two-answer set the
   `measure_of→"<noun> of"` bridge ([generated data](../development/generated-data.md)) produces for a relational measure
   question — *"the length of car A and 80000 meters"* → *"80000 meters"*.  No-op
   when no answer carries a `$list`, so non-measure queries and reverse
   *"what is 80 km long?"* entity answers are untouched.
4c. **Tautological-population / class-name-leak filters**
   (`_filter_tautological_population_answers`, `_filter_class_name_leaks`): drop a
   `$some_*` population witness that merely restates the queried property/class.
   Two detection paths, both used:
   - *Proof-scan* (`_is_tautological_population_answer`): the witness is proved
     directly via the single-atom population clause that asserts the queried
     property/class (`some big elephant is big because some big elephant is big`).
   - *Clause-scan* (`_defined_property_witnesses`): collects every `$some_*`
     constant whose **defining** population clause `[PRED, PROP, const, …]` matches
     a question pop key, and drops ALL bindings to it **regardless of proof
     route**.  This catches a property witness reached by a second, non-circular
     route — `$some_nice_car` answering "what is nice?" not via its own clause but
     via "it is a car, and cars are nice" (cases 1434 / 1487).  The queried-CLASS
     witness (`$some_car`, defined by `isa`, not the property key) is never
     collected, so the correct generic answer ("A car.", "An elephant.") survives.
   Both apply even when no non-tautological alternative remains (→ "Unknown").
5. Formats the answer string via `_format_answers`:
   - Boolean `True`/`False` → `"True"` / `"False"`
   - Named entities → display name (strips numbering when unambiguous, strips URL when
     display name is unambiguous)
   - Confidence < 0.99 → appends `"(confidence X%)"`
6. Optionally renders a step-by-step proof explanation (via `proof_explain.format_explanation`)
   when `-explain` is used.

**Internal helpers** (in `proof_answer_format.py`):

- `_join_and_finish(parts)` — join a list of answer strings with "and", capitalise, add period;
  shared by `_format_prep_answers` and `_format_answers`

Steps 3–4b above (`_answer_goodness`, `_filter_by_best_tier`, `_what_query_is_relational`,
`_answer_all_unbound`, `_prefer_measure_value_answers`, the tautology/leak filters and
`_deduplicate_proofs`) live in `proof_answer_select.py`; the `_format_*` renderers and
query-shape probes (step 5) live in `proof_answer_format.py`.

**Ambiguity handling:** Before formatting, `compute_ambiguity` (from `proof_render.py`) scans
the full logic list to find entity names that appear with more than one number (e.g. `"John 1"`
and `"John 3"`).  Such names keep their distinguishing number in output.

**Imports:** `procproofs` imports `compute_ambiguity`/`compute_skolem_types`/`entity_name`/
`set_entity_map` from `proof_render.py`, `format_explanation`/`build_sentence_map` from
`proof_explain.py`, plus the selection/formatting entry points from the two sibling modules.
`proof_answer_format` additionally imports `ans_atom_name`/`get_skolem_type`/`get_skolem_fn_type`/
`get_entity_display` from `proof_render.py` and `ans_display_key` from `proof_explain.py`.

### Proof rendering modules

Proof rendering is split across four files, with `proof_render.py` as a thin facade:

| Module | Role |
|--------|------|
| `proof_render.py` | Facade — re-exports public API from the implementation modules |
| `proof_utils.py` | Entity naming, Skolem type resolution, render context state, ambiguity detection |
| `proof_english.py` | Atom/clause → English rendering; table-driven via `_PRED_TABLE` |
| `proof_terms.py` | Term rendering sub-library (`render_term_english` + `$count`/`$setof`/`$theof1`/`$measure` and TPTP-arithmetic helpers), split out of `proof_english`; reached by both `proof_english` and `proof_utils` |
| `proof_logic.py` | Traditional `pred(arg,...)` and JSON logic syntax rendering |
| `entity_map.py` | `build_entity_map(s1,s2)` → `{entity_id/url: display_name}` from the user's original phrasing (article + pre-nominal qualifiers); consulted first by `proof_utils.get_entity_display` / `_location_entity_name` |

Per-proof mutable state (entity map, ambiguous names, Skolem type annotations) is bundled in a
`RenderContext` class (`_ctx` module-level instance) in `proof_utils.py`.

**Qualifier extraction (`entity_map.py`).** Display names reuse the user's wording by scanning
the source text backwards from each entity for pre-nominal adjective qualifiers ("the **red**
car"). Verbs must be excluded so they don't leak as qualifiers — `_collect_action_verbs` gathers
them from Stage-1 action roots and Stage-2 relation names, and a static `_STOP_WORDS` set stops
collection at auxiliaries/prepositions/conjunctions. A surface verb whose **canonical Stage-2
relation name differs** from its surface form is the trap: "Earth **contains** Europe" is encoded
`is_rel2("**in**", …)`, so the relation captured is "in" and the surface "contains" is never seen
as a verb → it would render `"the contains Europe"`. Such containment/spatial transitive verbs
(`contain(s)`, `include(s)`, `comprise(s)`, `surround(s)`, `hold(s)`) are therefore listed
explicitly in `_STOP_WORDS` (case 1253).

Atom-to-English rendering in `proof_english.py` is table-driven via `_PRED_TABLE`, a dict mapping
predicate names to `(arity, pos_renderer, neg_renderer)` tuples.

**Open names (`open_names_flag`).**  The graph theory's class and relation names are the
case's own words (`premiered`, `music_piece`, `sells_greater_than_copies`), so the verb and
preposition heuristics of the table misfire on them: `looks_like_verb("premiered")` is true
and `conjugate_verb` makes "premiereds".  Under the flag `proof_english` folds underscores to
spaces and prints the name as the translator wrote it — `is rel2("premiered", X, Y)` → "X
premiered Y", negated "it is not the case that X premiered Y" — reads one of the nine fixed
roles of `graph_stage2.ROLES` as a role ("the agent of E is X"), and keeps the copula only for
a name that is itself a preposition ("X is on the list").  `isa` folds the underscores and is
otherwise unchanged.  The flag is off everywhere but the graph route's own rendering, which
sets it through `graph_compile.GRAPH_OPTION_TABLE` and `graph_compile.open_names()`.
[Proof output](../reference/proof-output.md) has the table.

**Clause labels (`proof_explain.clause_labels`).**  Two kinds of clause say more about
themselves than their name does, and the label map is built from the submitted clause list:
a graph wording-variant rule (`norm_<n>`, carrying `@variant`) shows as
`[wording variant: games -> game]` instead of `[background knowledge]`, and an invented rule
carrying `@nl` — the program's own English reading of it — gets a `Reads:` line before its
`Why:` line in the "Added rules" section.  `graph_search` puts `english_of(rule)` on each
compiled bridge clause.

See [proof output](../reference/proof-output.md) for the principles, the
entity naming rules and the proof explanation structure, with examples.

#### Per-clause rendering state (`_ClauseRenderCtx`)

`clause_to_str` installs a per-clause `_ClauseRenderCtx` (module-level
`_RENDER_CTX` slot, scoped via try/finally) that tracks:

- `seen` — raw arg names (and `"skfn:"+str(skfn)`) already introduced;
  consulted by `_intro` to decide between full and bare rendering.
- `event_vars` / `event_consts` — variables / Skolem constants identified
  as Davidsonian events (via `isa("activity", X)`, `has_type(X,V)`, or a
  modal classifier on X in the same clause).
- `world_vars` — variables identified as worlds (via `next`/`before`/
  `moved`/`is_past_world` positions, or the world slot of `$ctxt`).
- `has_type_vars` — event vars whose `has_type(X,V)` literal appears in
  the same clause; `_intro` drops the `"an event X"` prefix for these
  because the predicate already introduces the type.
- `isa_type_hint` — map `var → TYPE` from `isa(TYPE, var)` literals
  (skipping `"activity"` to avoid event-marker conflicts).
- `used_in_other` — variables that appear in some non-isa atom; the
  isa-bundling absorption applies only when this is true.
- `absorbed_isa_ids` — bookkeeping for the isa-bundling pass.

`_scan_clause_vars(clause, ctx)` populates these fields in a single pre-pass
before any rendering happens.

#### `_intro(arg, role_hint=None)`

Central helper that decides the article/prefix for an argument on its first
mention in the current clause.  In priority order:

1. Skolem fn list-term → first time full ("the flying event sk0 of Mike 1");
   on later mentions short ("sk0 of Mike 1").  Also marks any variable args
   of the Skolem fn as `seen`.
2. World constant (`W0`, `W1`, …) → `"the situation W0"` (always).
3. Event Skolem (`sk0_activity`) → `"the event act1"` first, `"the act1"` later.
4. Common-noun constant (`"head 2"` / `"box B"` — lowercase + suffix) → always
   `"the head 2"`.
5. Variable, world-typed → `"a situation V"` first, bare later.
6. Variable, event-typed → `"an event E"` first; SKIPPED when the variable
   is in `has_type_vars` (returns bare `X` so `"X is a fly event"` reads
   cleanly instead of `"an event X is a fly event"`).
7. Variable with `isa_type_hint` and `used_in_other` (isa-bundling) →
   `"some <TYPE> X"`.  The matching `isa(TYPE, X)` atom is suppressed from
   the clause rendering.
8. Variable with explicit `role_hint` → `"a/an <ROLE> X"` (currently unused
   from the per-predicate lambdas; reserved for future role-aware bundling).
9. Bare entity variable → `"some X"`.

All paths add the arg to `seen` so subsequent calls in the same clause
return bare.

#### Two-pass clause rendering (`_clause_to_str_body`)

Pass 1 classifies every literal into `neg_specs` (conditions), `pos_specs`
(consequents incl. `$ans`), or `block_atoms`.  Applies:

- R1 (drop tautological `isa(TYPE, "TYPE N")` in multi-literal clauses).
- isa-bundling absorption (negative form): applies only when `bundling_active`,
  which is `True` only for pure-negative clauses (no positive literals
  to anchor an explicit if-then structure).
- Modal-classifier reorder: in pure-negative clauses, any literal whose
  predicate is in `_MODAL_CONSEQUENT_PREDS` (`capability` / `typical` /
  `necessity` / `obligation` / `volition` / `intention` / `expectation` /
  `speech_act` / `actuality`) is moved to the END of `neg_specs` so it
  becomes the consequent — the modal claim is usually the informative
  conclusion ("X is not a capability" reads better than "X is not a
  penguin").

Pass 2 renders conditions FIRST (in clause order), then consequents (in
clause order).  This places variable intros in the antecedent visually,
where readers expect them — without this re-ordering an `is_rel2`
consequent rendered first would consume the variable's first-mention
prefix and the antecedent would read with bare `X`.

After joining with " and " / " or " / "if … then …", a final pass
capitalises the first alpha character (skipping leading quotes/brackets)
to make each step read as a sentence — but it skips Skolem-fn identifiers
(`sk0`, `sk1_house`, …) which are not English words.

#### Custom per-predicate render helpers

Several `_PRED_TABLE` entries call dedicated helpers instead of inline lambdas:

- `_has_type_render` — when the first arg is a Skolem fn, uses the SHORT
  form (no "the flying event" prefix) because `has_type` already asserts
  the event type; would otherwise read "the flying event sk0 of X is a
  fly event" (redundant).  Also marks the Skolem fn's variable args as
  seen to avoid re-introducing them later in the same clause.
- `_has_time_render` — picks past/present/future verb form from the
  literal-tense slot (`"happened in the past"` instead of `"happens in
  past"`).  Falls back to the generic form when the tense slot is itself
  a variable.
- `_has_recipient_render`, `_has_destination_render` — pivot to
  `"<X> is the/a recipient/destination of <E>"`.  Article picked by
  whether the event arg is a Skolem (concrete → "the") or a variable
  (axiom → "a").  Drops the prep slot of `has_destination` since it's
  usually a noisy auxiliary variable.
- `_is_rel2_var_rel_render` — invoked from `_is_rel2_pos/_neg` when the
  relation arg is a variable.  Renders `"<Y> is/was/will-be in relation
  <X> to <Z>"` and surfaces the `$ctxt` tense + world ("in <world>" /
  "before <world>" / "after <world>") so two such atoms with different
  contexts in the same clause render distinguishably.
- `_prep_answer_phrase` — `$ans`/`$defq*` payloads of the form
  `[PREP, VALUE, …]` (from where/when-queries) render as `'in the box'`
  (single-quoted) instead of the bracket form `[in, the box]`.  Other
  multi-arg payloads keep the bracket form.

#### Helper-predicate templates

`_PRED_TABLE` includes situation-aware renderings for axiom helper
predicates:

- `next(W, W2)` → `"the situation W is followed by the situation W2"`
- `before(W, W2)` → `"the situation W is earlier than the situation W2"`
- `moved(X, W)` → `"X moved in the situation W"`
- `transferred(O, W)` → `"O was transferred in the situation W"`
- `is_past_world(W)` → `"the situation W is in the past"`

#### Skolem function naming

`proof_utils._skolem_fn_to_name` always includes the function name and
ground args, prefixed by the verb-gerund (when known) or object type:

| Input | Output |
|---|---|
| `["sk0","Mike 1"]` + verb fly | `"the flying event sk0 of Mike 1"` |
| `["sk0","?:X"]` + verb fly | `"the flying event sk0 of X"` |
| `["sk0","Mike 1"]` (no verb, type roof) | `"the roof sk0 of Mike 1"` |
| `["sk0","Mike 1"]` (nothing known) | `"the event sk0 of Mike 1"` |

`_skolem_fn_short_name` returns just `"sk0 of Mike 1"` / `"sk0 of X"` /
`"sk0"`; used for subsequent mentions within a clause via the seen-tracker
in `_intro`.  `_skolem_fn_arg_display` keeps raw entity ids
(`"Mike 1"`, not `"Mike"`) so the Skolem-fn term displays the specific
instance unambiguously.

#### Extension guide

When adding a new predicate to `_PRED_TABLE`:

- Use `e(i)` (which calls `_intro`) for entity / variable args so that
  variable tracking, article injection, and isa-bundling all work.
- Use the raw `args[i]` (bypassing `_intro`) only when the predicate
  contributes the introduction itself (as `has_type` does) — and in that
  case manually mark relevant vars in `_RENDER_CTX.seen` to keep later
  mentions bare.
- For new modal classifiers, add the name to `_MODAL_CONSEQUENT_PREDS`
  to get the "preferred consequent" treatment in pure-negative clauses.

**Public API** (all importable from `proof_render.py`):

- `compute_ambiguity(logic)` — scan clause list for ambiguous entity names [`proof_utils`]
- `compute_skolem_types(proof, logic=None)` — populate Skolem type tables from logic + proof [`proof_utils`]
- `set_entity_map(entity_map)` — set entity display map [`proof_utils`]
- `get_entity_display(key)` — look up display name [`proof_utils`]
- `entity_name(val, with_url, proof_mode)` — format entity for display [`proof_utils`]
- `ans_atom_name(atom)` — format answer atom [`proof_english`]
- `clause_to_str(clause)` — clause → English string [`proof_english`]
- `block_to_english(blocker)` — `$block` → English exception string [`proof_english`]
- `format_clause_logic(clause)` — clause → compact JSON [`proof_logic`]
- `format_clause_traditional(clause)` — clause → traditional logic syntax [`proof_logic`]
- `formula_to_logic(formula)` — FOL formula → traditional syntax [`proof_logic`]

### proof_explain.py

**Role:** Builds the full step-by-step proof explanation presented to the user.

A clause added by the literal-bridge machinery is neither the passage nor a standing
axiom.  `_is_litbridge_source` recognises it by the `utils.LITBRIDGE_CLAUSE_PREFIX`
name, `_litbridge_label` reads the round out of the name, and such a step is rendered
`[added rule (round N)]` and listed under its own **Added rules** heading rather than
folded into *Knowledge used* ([literal bridges](../architecture/literal-bridges.md)).

**Public API:**

- `build_sentence_map(s1_json) -> dict` — builds `{"sent_S1": "raw text", ...}` from Stage-1
  output; maps each clause name back to the original English sentence it came from
- `format_explanation(answers, sentence_map, show_logic=False) -> str` — main entry point;
  produces the `"Explained:\n\n..."` block for all (non-duplicate) answers; groups proof steps
  under "Sentences used:", "Knowledge used:", and "Proof steps:"
- `ans_display_key(val, askvars=None) -> hashable` — canonical dedup key for an answer value;
  ignores auxiliary world-state arguments

### linguistics.py

**Role:** Pure English linguistic heuristics used by `proof_english.py` for human-readable output.
No dependency on proof state or any other pipeline module.

- `indef_article(word) -> str` — returns `"an"` before vowel sounds, `"a"` otherwise
- `conjugate_verb(v) -> str` — third-person singular present tense (`fly` → `flies`)
- `make_comparative(adj) -> str` — comparative form (`nice` → `nicer`, `beautiful` → `more beautiful`)
- `to_gerund(verb) -> str` — gerund form (`run` → `running`, `bite` → `biting`)

## Related documentation

- [Reasoning and proofs](../architecture/reasoning-and-proofs.md)
- [Questions, confidence and answers](../architecture/questions-confidence-and-answers.md)
- [Proof output](../reference/proof-output.md)
- [Source map](source-map.md)
