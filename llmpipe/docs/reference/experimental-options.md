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

## The action route

An experimental route for texts about actions and plans. Without `-actions`
or `-noactions`, each text is routed by a cheap classifier
(`solver/route_classify.py`, no model call), the same way in a one-example
call of `solve.py` and in a test run:

- a strong sign of actions or plans sends the text to the action route: a
  question "How can ...?", a request for a plan, a question "After X does
  ..., ...?" or with "eventually", blocks named by a letter with a hand, a
  route or service between places, a permission to travel from one place to
  another by a means, a permission for an operation with an instrument;
- every other text goes to the ordinary pipeline. This includes an unclear
  text, one with a weak sign that ordinary texts also show, such as "can"
  before an operation verb or a question "Who can ...?".

The choice is kept in the case record (`route_choice`: mode, route, verdict
and signals). On the tracked ordinary test sets the classifier sends no text
to the action route.

**`-actions`** — always run the action route instead of the ordinary pipeline:
- its own two-stage translation;
- the action compiler;
- the independent replay;
- a registered GK build with the action library.

No ordinary retry stage, critic, graph or literal bridge runs. A `-pipeline`
preset, a stage switch or an ordinary representation option given with it is
an error, never a mixed theory. The route leaves the ordinary option state as
it found it: it sets the model-call keys for the length of its call and then
restores them. Model-call bounds (`-llm-call-limit`, `-llm-call-timeout`) and
the caches apply to its calls. English input uses the measured action prompts
(`prompts/actions/`, assembled by `action_prompt.assemble`; see
[the action prompt interface](../encodings/action-prompts.md)).
Status: experimental.

The answer text has one form per question kind and outcome:

| question | answer text |
|---|---|
| a plan (`How can ...`, `Find a plan ...`) | `Plan: <steps>.`, `No action is needed.` or `No plan found.` |
| a reachable goal (`Can X eventually ...`) | `Yes. Plan: <steps>.`, `Yes. No action is needed.` or `Unknown.` |
| a yes-no, verify or executable question | `Yes.`, `No.`, `Unknown.` or `Contested.` |
| a wh-question | the entity by name: `The key.`, `The key and the cup.` |
| any, with conflicting facts in the starting state | `Inconsistent: <facts>.` |
| any, when the replay validates no candidate plan | `Unknown: no candidate plan was validated.` |
| any, for a text the route does not model | `Cannot answer: <sentence>. [<reason codes>; <units>]` |
| any, after a failed run | `Error: <outcome>: <detail>` |

The `Cannot answer` sentence says what the route read and why it gives no
answer. `Error` marks a run that gave no answer: an invalid translation, a
call limit, a model error, a timeout, a prover error, a missing or
incompatible backend, or an insufficient search allowance. `runtests.py -redo-errors`
repeats an `Error` case and keeps a `Cannot answer` case. When the confidence
from the probabilities that the text states is below 0.95, the answer says
`Probably`: `Probably yes.`, `Probably no.`, `Probably yes. Plan: ...` or
`Probable plan: ...`. The threshold is a display convention, not a calibrated
probability. The number stays in the result record, and the frame axioms'
part of the confidence does not count.

**`-noactions`** — always run the ordinary pipeline. An action option given
with it is an error. Status: experimental.

**`-formal`** — the input is a formal JSON record for the action route, or the
path of a file holding one, compiled and solved with no model call. The record uses the field names of the gold
fixtures:
- `units`: each unit has an `id` and a Stage-2 package `stage2`;
  `text`, `stage1` and `context` are optional;
- `queries`: each query has a `stage2` package, and optional
  `planning_root`, `ambient`, `knower` and `limits`;
- `entities`, `worlds` and `text` are optional.

**`-plan-depth N`** — on the action route: the search cap of a plan or reachable
question. The default cap is four. A stated step bound in the question is
kept apart from this cap.

**`-action-backend NAME`** — on the action route: a registered GK build (default
`gk`, the installed prover with the action route's planning strategy). `-seconds` sets its time per launch (default 30 on this
route).

### Output of the action route

The route follows the output levels of the ordinary pipeline. Each level
includes the ones above it.

| level | what the action route prints |
|---|---|
| none | the answer |
| `-explain` | the explanation after the answer: the sentences and the library laws that the deciding proof used, then the plan steps and the replay verdict, the checks of a supplied sequence, or the reason for no answer |
| `-logic` | the input and the pipeline block, the Stage-1 unit texts, the source clauses of each sentence with their role, the query and its obligations, the stages block, the action term under each plan step and the GK proof steps |
| `-details` | the accepted action Stage-1 and Stage-2 JSON, the controller's findings for each model response (errors, parse repairs, normalizations), and the input and result of each GK launch; the input names the library laws in one comment line |
| `-debug` | each model request and its raw response as the route sends it, the library laws in full, the GK command of each launch and the termination relaunch |

The other output options:

- `-json` shows the clauses and the proof steps in JSON.
- `-prover` shows the input, command and result of each GK launch at any
  level.
- `-summary` prints one block: the answer, the pipeline and why, the outcome,
  the replay verdict, the confidence, the model calls per stage and the GK
  launches. `-summary-json` prints the same record as one JSON line.
- `-nosolve` translates the text and compiles the query, then stops before
  GK. The answer is empty.
- `-rawresult` answers with GK's raw output. With several launches, a comment
  line names each launch.
- `-gkin FILE` writes the GK input to `FILE`, with the command as the first
  comment line. With several launches, each launch has its own file: the
  launch label stands before the file extension.

`-printlevel`, `-axioms` and `-strategy` change the prover run, so they are
errors with `-actions`. A runner's case record keeps the explanation as
`nl_proof`.

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
