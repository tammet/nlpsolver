# Action prompt interface and routing rules

Prompt revision I. This page specifies the English interface of the
experimental action route (`-actions`) to the implemented encoding v2. The
ordinary pipeline does not use it. The prompts and the examples that they show
are in `prompts/actions/`, the default bundle `actions` of the route.
`action_prompt.assemble` assembles them.

## Decisions

Keep the existing sentence packages and ASU `type`. Add a separate reading
annotation, rather than a new `instruction` type. A strict action rule, a
default rule, a restriction, an effect, an occurrence and a request have
different meanings even when they share a verb. Keep one `query` ASU for the
entire question, including a conjunctive goal or supplied action sequence.

Stage 1 identifies meaning in readable text. Stage 2 produces formulas.
Neither stage searches for a plan, adds missing physical preconditions, or
predicts the answer. The compiler supplies situations, library completion,
restriction checks, frames and markers.

The existing recipe convention remains explicit: a positive sufficient
property-change rule with a concrete instrument includes `have(actor, tool)`
as a source condition (as in the reviewed food pilot). This is a profile reading
of the instrument phrase, not an extra condition on all constructor uses.
Denials, restrictions and effect-only descriptions do not acquire that guard.

## Stage-1 fields

Existing fields keep their ordinary meaning, except for the explicit action
overrides below. Omit optional fields when absent; do not use null.

| field | contract |
|---|---|
| `type` | Existing `real`, `situation`, `strict_rule`, `normal_rule`, `query`. Initial descriptions can be quantified or conditional; this alone does not make them standing laws. |
| `action_reading` | One of `availability`, `restriction`, `effect`, `occurrence`, `plan_question`, `reachable_question`, `executable_question`, `verify_question`. Omit on ordinary readings and state descriptions. |
| `actions` | Existing natural verb roots, modes and roles. Include the actor explicitly when identified; reuse entity IDs. Means are lexical labels, tools are entity IDs. Keep polarity in the normalized text, never inside `roles`. |
| `step_bound` | Query only: `{"comparison":"at_most"|"exactly","count":N}` for a stated nonnegative integer. No default search cap appears here. |
| `action_order` | `"sequence"` only on a supplied-sequence query. Its `actions` list gives exactly the supplied steps in order. An unordered conjunction must not acquire an order. |
| `pre_state`, `next_state` | Existing world references, on source units only. A rule or hypothetical sequence creates no narrative successor. Explicitly named snapshots can use W0, W1, ... without asserting a transition between them. A query unit has neither: it selects a snapshot with `planning_root`, and it never declares a world. |
| `context` | On a fact description only: optional `location`, `location_role`, `knower`. Tense uses the existing `time` / `state_tense` fields, and is copied into the Stage-2 context record by a deterministic rule. This records the qualification of the assertion, not the location of its subject. |
| `planning_root`, `ambient`, `knower` | Query only, when explicitly selected or unambiguously referred to. Root is a world that W0 or a source unit declares; ambient and knower are entity IDs. A source fact's viewpoint and scope location go inside its `context`. Omit to use the compiler's documented defaults. |
| `action_issue` | Optional `{"kind":"ambiguous"|"unsupported","text":"source span","detail":"explanation"}`. A proposed translation/routing diagnostic, not a new logical predicate or compiler reason. It prevents a procedural directive or mixed scope that cannot be represented faithfully from silently becoming an ordinary statement. |

`availability` is the existing name for a sufficient source action rule,
including its explicit denial. It does not introduce a public capability
predicate in the prover. In a procedural source, a named actor's stated rule
is strict unless the source qualifies it. A class-level default keeps its
default reading. An effect gives no permission, and a restriction gives no
sufficient action rule.

The complete condition and consequent remain in ASU text with their original
scope and entity references. Do not add precondition/effect formula arrays,
logical variables, constructors, fluents, hooks or situation terms to Stage 1.
Keep a shared existential participant within one unit when splitting would
change its scope. If no faithful supported split exists, retain the sentence
and give an `action_issue`.

Use `actions.roles.source`, `destination`, `target`, `instrument`, `location`
and `result` where they fit, with an explicit `actor` when known. Travel means
uses `instrument`; a support/container uses `location` and `location_prep`.
Travel by a means is a move, whatever the verb: "take the bus" has the
instrument bus and no target.
The validator rejects new role names such as `means`, `support` or `container`.
A question requesting a goal may have no action
to annotate: "Find a plan with b on a" must not invent a put operation.
For a verification, `actions` contains the supplied sequence only; actions
mentioned inside the final question remain in its text, not extra steps.

### Readings

- A sentence that says who cannot do an operation is `availability`, a
  denial, also with a condition on who: "Minors cannot take the plane", "A
  driver who is not insured cannot travel by taxi". "Cannot unless P", "only
  if P" and "requires P" are restrictions.
- A sentence that gives a permission and then its result is two units: the
  permission (`availability`) and the effect.
- A rule between two states has no `action_reading` and no `actions` array.
  An effect needs an operation that an actor performs.
- An if-rule without normally, usually or a probability word is a strict rule
  with no confidence.
- One entity keeps one id: after "There is a robot hand", "the hand" is
  `robot hand 1`.

### Scope and qualifications

- A state rule follows one convention. A marker decides: "initially", "at the
  start" and "now" give a description of the start; "always", "at all times",
  "at every state" and "whenever" give a standing rule. Without a marker, a
  dependency between states is a standing rule ("If a block is on the table,
  the block is stable"), and a description of the scene is a description of
  the start ("Every block on the table is red", "Nothing is on any block").
  The words if and every do not decide alone. A standing rule is a
  `strict_rule` (a `normal_rule` with normally), and Stage 2 writes it
  `holds(W, ["state_law", F])`; a description of the start is a `situation`.
  The compiler reads only `state_law`: the translation applies the
  convention.
- Tense is relative to the named snapshot. Stage 1 retains ordinary `time`
  and `state_tense`. For initial descriptions without an action reading,
  Stage 2 takes context tense from `time` when it is present/past/future,
  otherwise from `state_tense`, without dropping an explicit date from the text.
  Availability, restriction and effect qualifications stay in `@time`; an
  occurrence's time stays in its event formula as `has time`. Neither puts tense
  in a fact context. `@time` wraps only the stated validity phrase of a rule or
  a permission ("until noon"). A description never takes `@time`: its date stays
  in the Stage-1 `time` field and its tense goes to the context record; a tense
  word is never a `@time` text. The validator names both mistakes. The compiler accepts occurrence formulas only to preserve
  their meaning and report them unsupported.
  Preserve unresolved
  past/future qualifications; the action compiler records their exclusion.
  Do not turn yesterday into a current fact, or invent a resolved past world.
- In "Ann is in Tallinn", Tallinn is the value of `located_at`, not a context
  location. A location qualifying where an assertion applies has role
  `scope`; a location describing where the report was made has role
  `provenance`. If that distinction is genuinely unresolved, report an issue.
- A named knower scopes a report; do not convert wishes, orders or beliefs
  into objective state facts. General nested belief reasoning is outside
  this first action fragment.
- If old `location` or `mental_holder` fields are also present, conflicting
  assertions need correction. A mental holder is not automatically a knower;
  wishes, obligations and nested beliefs cannot be flattened into that field.
- The Stage-2 `worlds` list follows the order in which source snapshots are
  established, never numeric sorting or the requested goal. A query may
  select an earlier world without rewriting the source.

### Local action readings override verb synchronization

The two ordinary Stage-1 instructions that synchronize a verb's mode across
units do not apply in this variant. "Can press", "pressed", "did not press",
"intends to press", and "pressing changes ..." retain their local readings.
Ordinary capabilities such as "Birds can fly" remain ordinary unless the
source actually presents them as available operations in a physical task.
The requested destination or desired answer never strengthens a source rule.

Keep ordinary Stage-1 confidence conventions, including the article-derived
0.99. Only the action Stage-2 variant removes that annotation when the raw
sentence has no uncertainty marker and it came solely from the article rule.
An explicit probability, including 0.99, survives. This avoids changing ordinary
confidences before routing. The checks and future bridge must distinguish these
cases. Likewise, normally becomes a default without an extra numeric probability
unless the text states one separately.

Override the ordinary command normalization for "Find/Give/Show a plan ...":
these remain queries. The first English action route accepts zero or one question
sentence. Multiple independent questions get a diagnostic; the existing formal
route still accepts multiple query records. One goal's conjunction is never split.

## Routing after Stage 1

The selector reads the whole passage's annotations once. Its priority is:

1. A malformed annotation or a contradiction between metadata and text is a
   validation error, eligible for a bounded correction.
2. An `action_issue` is a translation diagnostic: preserve the affected units
   and stop. Do not pass an unresolved procedural reading to ordinary Stage 2.
3. Any `availability`, `restriction`, `effect`, `plan_question`,
   `reachable_question`, `executable_question` or `verify_question` selects
   augmented Stage 2 and the action compiler for the whole passage.
4. Otherwise select the ordinary Stage-2 prompt and ordinary compiler.

`occurrence` alone does not select planning. "Ann travelled to Tallinn.
Where is Ann?" remains ordinary narrative reasoning. If the same passage
also asks for a plan, all units go to action Stage 2; occurrence remains
unsupported there. It must not become a permission or disappear.

A generic skill question or a manner/explanation question does not select
planning. An explicitly procedural theory selects the action route even
when its question asks a state fact, or when there is no question (compile
the source and stop). A plan request can select it with no source action
rules: the physical profile may supply the documented defaults.

Directives require their discourse role. "Find a plan to put b on a" is a
plan query. "Put b on a" alone does not specify whether a plan, execution,
or a procedure step is wanted: preserve it with an ambiguous issue. An
instruction embedded in "Lea told Ann to put b on a" is a speech act,
not an available operator. A supplied procedure without a request to check
it is not silently converted into universally applicable action laws.

The choice of pipeline happens before Stage 1: `-actions` and `-noactions`
decide it, and without them the text classifier `route_classify.classify`
does ([the action route](../architecture/action-route.md#when-it-runs)). The
selector after Stage 1 records the route that the annotations ask for, but it
does not dispatch to the ordinary pipeline. A recorded `ordinary` selection
still proceeds through the action Stage 2 and compiler; an `action_issue`
stops translation. The routing contrasts in
`prompts/actions/routing_cases.json` show the selector's decisions.

## Stage-2 output and precedence

The action prompt is assembled from the existing Stage-2 material followed
by explicit action overrides, action examples and a final checklist. The
overrides replace ordinary event reification only for the identified action
readings. Initial facts elsewhere in the passage use the action profile's
stored-fluent vocabulary. All source and query units remain represented.

The action Stage 2 uses this envelope:

```json
{"worlds":["W0"], "contexts":{}, "query_contexts":{}, "types":{}, "logic":[]}
```

`types` is present only when a law sentence introduces a referent (below).

`logic` is a list of existing `[@id, ID, PACKAGE]` records. Source records
are `holds(W,F)`; queries use the existing plan/reachable/verify/question/ask
grammar. `contexts` copies source-unit context records and the relative tense
derived from `time` / `state_tense` as above. Explicit time-qualified action rules
retain their temporal condition for the compiler's unsupported-scope diagnostic.
`query_contexts` maps a query ID to its explicit `planning_root`, `ambient`
and `knower`. It copies Stage 1, not a guess made to obtain a proof. Omit
empty selections. A stated step bound belongs in the query package, not
`query_contexts`.

### Class facts and types

A concrete referent that the text first introduces by a class noun gets one
class fact, whatever its article: "the key", "a pan", "Block b", "the table",
"the robot hand" (class `hand`). The fact stands in the first unit that names
the referent. In a description it is a conjunct of that unit's fact, never in
`types`. The envelope field `types` holds only concrete Stage-1 entities that a
law sentence (availability, restriction or effect) names first, keyed by that
unit: `{"S4": [["isa","box","box 3"]]}`; the law formula holds its rule only. A
variable's class stays in its rule's guard. A proper name gets no class unless
a sentence states one ("Robo is a robot"); `["isa","Dock","Dock 3"]` states
nothing. A class fact is never repeated, never uses a Stage-1 category word,
and never comes from a referent that only the question names. A type is a
fact, never an added rule condition; a class condition that the rule's
sentence states stays in its antecedent, and a quantified class guard stays.

A movement rule that states no origin or destination ("Every rover can travel
by taxi") binds both with `forall`, outside any condition, and so selects the
public template, which reads a stated connection:
`["forall","A",["forall","F",["forall","T",["implies",["isa","rover","A"],["can","A",["move","A","F","T","taxi"]]]]]]`.
`unspecified` stands only for a missing means or tool, never for an endpoint.

### Action terms

- Travel by a means is `["move", A, F, T, MEANS]`, never the take
  constructor. A denial without endpoints binds them like the permission.
- A supported property change whose result the text does not state takes the
  verb's past participle as its value: polish, `polished`. A stated result
  takes precedence. The value is never `unspecified`, and this rule never
  turns a creation, a transfer or a movement into `change`.
- One action has one term in every sentence: after "Ola can steam the rice in
  the pot", a later "After Ola steams the rice, ..." uses the permission's
  term, with the pot.
- A condition of a permission stands in the antecedent; the consequent is the
  `can` head alone.
- A who-question about an operation is `["ask", V, ["executable", ACTION]]`.
  A permission that names no actor is `["exists", A, ["can", A, ACTION]]`.

The compiler turns `types` into static type records of the source artifact
(`action_route.TYPE_KINDS`, kind `stated`), beside two other kinds:

- `stage1_person`: the documented person convention. An objective source unit
  (no knower, no scope location; a query is no source) lists the entity with
  the Stage-1 category `person`, and nothing states otherwise. A stated class
  in `action_prompt.NON_PERSON_CLASSES` (robot, machine, vehicle, animal), a
  conflicting Stage-1 category or a stated negative person fact suppresses the
  type and leaves a source diagnostic of level `note` (`conflicting_category`,
  `stated_not_person`). An unlisted class is no evidence either way. The type
  records the units it rests on: it is the model's Stage-1 interpretation,
  which the compiler does not verify. No type comes from being an actor, from
  a name, or from a query-only mention. A formal record gets no derived type.
- `lexical_identification`: an unconditional isa conjunct of a past or future
  description whose class noun names the entity in the unit's text
  ("Yesterday block b was on the table"). When a query leaves that description
  out for its tense, the type record stands in for the class fact. A unit with a
  knower or a scope location keeps its qualification, an uncertain unit gives no
  certain type, and a class predication ("b was a block") is no lexical
  identification.

Every type record compiles to one static clause. The query views keep a
`stated` or `stage1_person` record always, and a `lexical_identification`
record only when its unit is excluded. The replay reads the type records, never
the compiled clauses, so the compiler and the replay agree.

### What the controller normalizes

With the reviewed bundle, the controller records every normalization in the
translation's history and never changes meaning:

- an envelope field that the response leaves out (a bare logic list, or an
  object without `worlds`, `contexts` or `query_contexts`) is derived from the
  validated Stage 1 with the same functions the handoff check uses
  (`envelope_derived`); a supplied field that differs from the derived value
  is replaced by it, and the record keeps the model's value
  (`derived_field`). Stage 1 decides these fields, so the model's copy adds no
  information;
- the `@p` of a source package is the one that Stage 1 and the unit's text
  decide: the Stage-1 confidence, with no `@p` for the 0.99 of an indefinite
  article and the 0.98 of a normal rule unless the text states a
  probability. A package whose annotation differs gets that annotation, or
  none, and the record keeps the model's (`derived_probability`);
- a source package `["and", ["holds", W, F]]` with that one conjunct is
  `["holds", W, F]` (`wrapper_dropped`); this step never removes a
  confidence conjunct;
- a response that is not JSON is parsed after unfencing first; when that
  fails, the final run of closing brackets is rebuilt from the open
  containers, only when the text before it is intact JSON and ends with a
  value (`terminal_delimiters`); otherwise the ordinary `fix_json` runs; when
  that fails too, each `["@id", ID, PACKAGE]` package is closed at its own
  balanced end and the surplus closing brackets between packages are dropped
  (`package_delimiters`, with the dropped brackets recorded), only when
  nothing but closing brackets and a comma stands between packages and every
  rebuilt package has three elements; when that fails too, a run of surplus
  closing brackets before a field of the envelope (`..."Ann 1"]]]]], "types"`)
  is dropped (`envelope_delimiters`), only when the first refused token is a
  `]` while only the envelope object is open, after a complete field value,
  and the repaired text parses. A failure reports the error position in
  the model's own JSON. A response the provider stopped at its output limit
  is not repaired, and neither is a provider response without a stop reason,
  which may be cut off. A response from the LLM cache is repaired: the
  controller keeps a response cut at the output limit out of the cache;
- five typing cleanups, each with a guard; when its guard fails, the ordinary
  correction runs. N1 (`types_relocated`): a `types` entry of a description unit
  without a probability, whose atom is `["isa", lowercase class, ID]` with ID
  among the unit's Stage-1 entities and the class noun naming ID in the unit's
  text, becomes the leading conjunct of that unit's formula, in its order in
  `types`. N2 (`types_dropped`): a `types` entry whose third argument is no
  concrete Stage-1 entity (a variable, a generic id, another string) is
  dropped. N3 (`self_class_dropped`): `["isa", C, "C n"]` with a capitalized C
  equal to the id's name part is dropped from `types` and from the top-level
  conjunction of a description. N4 (`root_explicit_default`) is covered by
  the derived fields: an explicit `planning_root` equal to the only declared
  world, where Stage 1 selects no root, is replaced by the derived selection
  and recorded as `derived_field`. N5 (`later_class_accepted`):
  a class at a later mention is accepted when the later unit's text names the
  entity with that class noun;
- `["is rel2", "in", A, B]` becomes `["is rel2", "located_at", A, B]` when
  Stage 1 gives A only the category person and gives B the category place
  (`person_at_place`); an object in a container and a place in a place keep
  `in`;
- the recorded repairs of `action_repair`, each with its repair id, unit, text
  before and after, and supporting units, and each only when its condition
  holds: K5 fills the omitted tool of a later mention of an action from its
  one permission; K6 and K7 make travel by a standard means a move and bind
  its unstated endpoints at the head's scope; K8 makes a permission that names
  no actor existential; K9 merges a later id with the index and head noun of
  an earlier id when the later unit says "the <name>" (without that anaphor,
  Stage 1 gets a correction); K10 drops a misplaced
  `@p` equal to the unit's derived probability; K16 makes a strict-rule
  dependency between present states of W0 a `state_law`;
- the readings the compiler adjusts (`reading_adjusted`): K1 reads a plain
  denial under the reading restriction as availability; K2 reads a rule
  between two states under the reading effect as no reading; K11 gives a
  permission or a denial without a reading its law reading, and the route
  selection is computed again. The handoff check accepts two forms with a
  note: a verify step whose entity role holds no declared concrete id (K3),
  and `["ask", V, ["executable", ACTION]]` with V in one entity slot (K4).

The controller also sends Stage 2 the Stage-1 packages without their entity
`url` fields; the accepted Stage 1 keeps them. When the Stage-1 coverage is
complete, the compiler runs beside the handoff errors, so a correction request
names every independent error at once (at most twelve messages, recorded as
`merged_compiler_messages`).

After a valid Stage 2, a class condition on a concrete entity in a rule's
antecedent is compared with that rule's own sentence. When the sentence does
not state it (a class word only inside an entity id states nothing), the
controller sends one more Stage-2 request that lists the conjuncts by unit and
path. When the conjunct is the class of a referent that the rule's own sentence
first names (repair `move_to_types`), the request asks to move it to `types`;
otherwise to remove it. The reply is used only when it equals the accepted
translation with exactly those conjuncts removed, an emptied or singleton
conjunction collapsed, and the moved classes added to `types`; otherwise the
accepted translation stands with its finding. A class
word that occurs elsewhere in the sentence makes the finding ambiguous: it is
reported and not sent. A gold-Stage-1 diagnostic row gets no such request.

The correction messages name the form that fits: the value slot names the
stated result or the past participle, the actor slot says that an effect
names its actor, and each query message names the form of its reading. A
later mention whose value differs from its one permission gets one message
per unit. After a correction that returned the same response, one focused
request quotes only the failing packages, and the reply's packages replace
them. The outcomes `method_collision` and `unsupported_law_form` get one
clarification. Its reply is used only when it is a valid supported
translation whose changed values a sentence of the text states; otherwise the
unsupported outcome stands with its reason.

### The labels of the controller's repairs

The code names each repair by its label. N1 to N5 are the typing cleanups
above.

| label | what it does | code |
|---|---|---|
| K1 | a plain denial under the reading restriction is read as availability | `action_repair.adjusted_reading` |
| K2 | a rule between two states under the reading effect gets no reading | `action_repair.adjusted_reading` |
| K3 | the handoff check accepts a verify step whose entity role holds no declared concrete id, with a note | `action_prompt.handoff_errors` |
| K4 | the handoff check accepts `["ask", V, ["executable", ACTION]]` with V in one entity slot, with a note | `action_prompt.handoff_errors` |
| K5 | a later mention of an action takes the tool of its one permission | `action_repair.repair_packages` |
| K6 | in a travel law, an unstated endpoint of a move is a universal variable at the head's scope | `action_repair.repair_packages` |
| K7 | `["take", X, MODE]` with a standard travel mode, in a travel law, is a move by that means | `action_repair.repair_packages` |
| K8 | a permission whose actor is `unspecified` becomes existential; the compiler then reports it | `action_repair.repair_packages` |
| K9 | a later id with an earlier id's index and head noun is the earlier entity when the text has a clear anaphor | `action_repair.id_findings`, `merge_units` |
| K10 | a misplaced `@p` equal to the unit's derived probability is dropped | `action_json.repair_packages`, `action_pipeline.misplaced_values` |
| K11 | a permission or a denial without a reading gets its law reading | `action_repair.adjusted_reading` |
| K12 | the replay never raises: a default state rule gives `not_checked`, an internal failure `replay_error` | `action_replay` |
| K13 | a later mention whose value differs from its one permission gets one message, once per unit | `action_repair.value_mismatches`, `action_prompt.query_form` |
| K14 | after a correction that returned the same response, one focused request quotes only the failing packages | `action_pipeline` (`_focused_request`, `_spliced`) |
| K15 | `method_collision` and `unsupported_law_form` get one clarification request | `action_pipeline` (`_clarification`), `action_repair.clarification_refusals` |
| K16 | a strict-rule dependency between present states of W0 becomes a `state_law` | `action_repair.repair_packages` |

The formulas, annotation checks and `query_contexts` handoff are implemented.

## What is implemented and checked

The bundle lives in `prompts/actions`; it is the default bundle of
the action route. The following are implemented and checked:

- closed-field validation, annotation/text consistency where deterministic,
  query reading versus package, step-bound and sequence preservation;
- action_issue handling, duplicate IDs and complete source coverage;
- an explicit query_contexts handoff, rejecting unknown or dropped fields;
- preservation of the raw sentence packages before Stage 2, and the explicit
  context/world order;
- recorded routing decisions after Stage 1;
- a correction request that quotes the previous response, then the errors;
  the validator's and the compiler's messages name the unit, the field or the
  argument slot, the offending term and the rule that applies. A correction
  that would repeat the previous request (the same response and the same
  errors) is recorded and not sent, because the cache would return the same
  response;
- a handoff check that a Stage-1 entity whose head noun is hand gets the
  class `hand` in Stage 2; it requests a correction and adds no fact;
- messages that name the fix for the observed misplacements: `normally` above
  a quantifier or an implication, a class atom conjoined with a law head, a
  `step_bound` on a verification, `@time` on a description;
- messages for a `types` entry of a variable, of a proper name or of no
  Stage-1 entity, and for `unspecified` as a movement endpoint;
- deterministic assembly, with the hashes of every source file and of each
  assembled prompt in `prompts/actions/manifest.json`.

The sequence handoff checks order, explicit participants, and placement
prepositions. Natural verbs remain open vocabulary; it does not claim to prove
the English-to-constructor interpretation. It compares only roles with a
corresponding constructor position. Extra roles such as a take's source or a
change's instrumental location do not invalidate the term. Reordered steps
whose mapped participants are identical require semantic translation review;
the positional check alone cannot distinguish their verbs. An action reading emitted as an
ordinary event receives one bounded clarification per unit. If a valid event
remains after clarification, it receives the compiler's unsupported diagnosis.
Malformed formulas still require correction. This lets an unfamiliar verb such
as zap use a stated property result without forcing creation or transport into
the same constructor.

No model quality claim follows from authored examples or fake responses.
The compiler's unsupported outcomes are legitimate example expectations.

The selector is a pure function recording `route_selected` and
`route_reasons`. It checks annotations, not the correctness of an English
reading. Snapshot and viewpoint examples written with explicit W0/W1 names test
the interface; they do not show that a model can recover worlds from natural
narrative.

## Related pages

- [Action translation](../architecture/action-translation.md) — the order of the controller's steps
- [Action clauses](action-clauses.md) — what the compiler makes of the Stage-2 envelope
- [Prompt map](../code/prompt-map.md#used-by-the-action-route) — the action prompt files
- [`prompts/actions/README.md`](../../prompts/actions/README.md) — the assembly and the example records
