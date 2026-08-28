# Graph representation

The two graph mechanisms. They are distinct.

Both exist for the same reason: a faithful translation is sometimes too
detailed to prove anything with. The canonical encoding keeps modality, scope,
tense and roles, and a proof needs all of them to line up. Reading the passage
a second time into plain subject-relation-object triples throws most of that
away, and on material where the detail was not what the question turned on, the
simpler theory finds the proof the detailed one missed.

The price is that the simpler theory can also prove something the passage does
not support, so the graph stages run only after the canonical theory has
returned `Unknown`, and their output passes the structural safety checks below.

`-graphtrans` is a second translation of the case into open triples, compiled
and submitted to GK once. It invents no rules. It is part of the `balanced`
default and costs about 1.2 model calls per case. On closed-world material it
is the whole mechanism.

`-graphbridge` invents implications between the open names and searches the
graph theory with them. It implies `-graphtrans` and never translates the case
twice. It is not part of the default; `-pipeline high-recall` or `-stack`
selects it. It costs about 2.7 model calls per case and earns its keep on
open-world, EntailmentBank-like material.

Where the [literal bridge](literal-bridges.md) keeps the ordinary translation
and invents rules over the atoms that translation produced, the graph mechanism
translates the passage again into a simpler representation.

Graph retranslation runs before the literal bridge. It is cheaper and, on the
EntailmentBank negative controls, more exact: 0 definite answers on the Unknown
controls, where the literal bridge answered 21% of them.

## What the second translation carries

The open-triple grammar keeps fewer distinctions than the canonical encoding: one
world, no context term, no tense, no sets and no measurements. A distinction the
contract does not admit is not carried into the graph theory.
[Graph translation format](../encodings/graph-format.md) states exactly what the
grammar admits.

## Structural safety

Before compilation, the graph Stage 2 is checked. `check_operator_arity`
rejects a logical operator with the wrong number of items. One corrective
retry may repair it. If the retry is absent, fails, or is still malformed, the
stage stops before compilation and before GK.

After GK returns a definite answer, the proof's cited sources are read. If
every substantive source is a Stage-1 question unit, the answer is not used
and the stage reports unresolved. The raw result stays in the record.


## What it is and where it sits

`solve._english_to_answer_once` runs the abstraction routes in the order
`abstraction_order` names — by default `graphtrans,litbridge,graphbridge`.  Each route
runs only when the question is still unresolved and only when its own flag is on; a
route the order omits never runs, whatever its flag says.  `collect["answered_by"]`
records which route produced the run's answer.

Layer 1 (`solver/graph_p0.py`, `run_graph_p0`):

```
ordinary Stage 1  (cached, reused)
  -> graph Stage 2          open triples, one LLM call        graph_stage2.py
  -> the checks             one corrective retry, no second   graph_stage2.py
  -> graph theory           logconvert under GRAPH_OPTIONS    graph_compile.py
  -> variant rules          norm_<n>, only when both forms occur   graph_p0.py
  -> confidence cap         every defeasible rule <= 0.95     graph_p0.py
  -> one gk call            "Probably ..." when confidence < 1
```

Layer 2 adds, over the same theory:

```
ordinary Stage 1  (cached, reused)
  -> graph Stage 2          open triples, one LLM call        graph_stage2.py
  -> graph theory           logconvert under GRAPH_OPTIONS    graph_compile.py
  -> name inventory         concepts, relations, kinds        graph_inventory.py
  -> supply and demand      read from the clauses             graph_inventory.py
  -> candidate pairs        enumerated by code, filtered      graph_pairs.py
  -> direction labels       one LLM call per batch of 40      graph_judge.py
  -> bridges                serialized by code                graph_judge.py
  -> P0, P1, P2, P3         gk, minimal sets, exclusion       graph_search.py
  -> grades                 one LLM call, labels only         graph_search.py
  -> lifting                back into the ordinary theory     graph_lift.py
```

`graph_procedure.py` is the entry point for bridge generation: `graph_context` does
everything that costs no gk call, and `graph_run` adds the calls and returns one
record.

The graph theory is a separate clause set. Its clauses are never added to the
ordinary theory, and the ordinary theory's clauses are never added to it. The only
place a graph result reaches the ordinary theory is lifting, described below, where a
lifted rule is appended to the ordinary clauses and gk is asked again.

## Which stage may produce the run's answer

The three mechanisms differ, and one does not follow from another.

**Graph retranslation (`-graphtrans`).** A proof found in the graph theory becomes the
run's answer directly. No lifting is involved. `graph_p0.run_graph_p0` returns the
answer, `solve.py` adopts it like any other stage's, and the run's top-level `proof`
and `gk_command` are that gk call's. It is enabled by the `balanced` default.

Two checks stand between the proof and the answer. The question-only refusal is
unconditional: when every substantive source of the proof is the Stage-1 query unit,
the answer is dropped, `stopped_at` records `question_only_graph_proof`, and the raw
result is kept for audit. The `-accept` policy is optional and off unless named.

**Graph bridge generation (`-graphbridge`).** An answer comes from
`graph_procedure.credible_answer`, which reads the acceptance verdicts stored in the
record and returns the first credible minimal set. Lifting is not required for that,
and `credible_answer` does not consult it. A bridged answer therefore also becomes the
run's answer. The stage is not enabled by any named configuration below
`high-recall`.

**Lifting.** `graph_procedure.LIFT` is a module constant and is `False`. When it is
turned on, `graph_lift.lift` re-expresses a graph proof's used units and rules over the
ordinary atoms and records the result; it does not decide the answer either way. It
remains experimental.

An earlier design did require a lifted proof before a graph answer could be used. That
is not the current code.

## The atom contract, in brief

Every content atom is a JSON list of exactly three items: `["isa", CONCEPT,
ENTITY]` or `[RELATION, LEFT, RIGHT]`. Names are lowercase, joined by
underscores, and built from the words of the unit. A generic complement folds
into the name; a concrete participant stays an argument. Negation stays outside
the name and modality stays inside it. An event with three or more participants
is reified with fixed role names. The world is always `W0`.

[Graph translation format](../encodings/graph-format.md) is the normative
definition: the package structure, the operator table, the naming rules, the
fold decision, the event form, and every structural check with what it rejects.

The top level is the **ordinary Stage-2 shape**, `["and", ["@id","S1",PACKAGE],
…]`, so `llmparse._run_stage`, `fix_json`, `logconvert.rawlogic_convert`, the
question machinery and `procproofs` consume the output unchanged. The user
message is `json.dumps(s1_json)`, byte for byte what the ordinary Stage 2 sees,
so the cache key differs only by the system prompt.

`graph_stage2.check_graph` returns `stage_sanity_core` `Issue` records, so the
ordinary corrective-retry loop applies. A name with a space or a capital is
normalized in place rather than refused, and a name that is merely odd is never
refused.

## The graph converter configuration

The graph Stage 2 is rewritten to the ordinary controlled atoms and run through
`logconvert.rawlogic_convert` inside `litbridge_converter.scoped`, under one
frozen option set, `graph_compile.GRAPH_OPTION_TABLE`. The syntactic rewrite and
the option set are listed in
[graph translation format](../encodings/graph-format.md).

The point of the option set is that the graph theory must contain no connection
between two open names except a named clause a proof can show. So the axiom
file, the injectors, the semantic normalisation, both proof-shortening rewrites
and every abstraction primitive are off, and the context is the constant `$c`.
Two of its entries were added by this work and are inert everywhere else:
`noclassnumbernorm_flag`, because the ordinary pipeline singularizes every `isa`
class name, and `noopennamerewrite_flag`, because it canonicalizes ownership,
location and preposition relation names.

What stays active, each emitting a named clause with provenance: entity
unique-name wrapping, the `$defq` question encoding with the bare-plural generic
hoist, Skolemization, and the structural repairs. Population witnesses and the
Stage-1 entity-category `isa` clauses were active in the pilot and are off in
this version (`nopopulate_flag`, `noentitycat_flag`), because each puts a name
into the theory that the translator never wrote.

`graph_compile.name_drift` checks the invariant after every conversion: a name
the translator never wrote, or a written name the clause list lost, is recorded
per case. The invisibility fixture in `tools/test_graph_compile.py` pins it — a
two-name theory compiles to exactly its own clauses, with no population witness,
no entity-category clause, no `compound_*`, `frm_*`, synonym or axiom clause and
no `$ctxt` term, and gk answers Unknown on it.

The option dict is captured once per case, before the first conversion, because
`scoped` replaces `globals.options` while a conversion runs.

## Names, frontier, candidate pairs

`graph_inventory.build` records every concept and relation occurrence with its
participants, sign, package and position (fact, rule body, rule head, question).  A
constant argument that names a kind rather than an entity or a value — `food`,
`labeled_data` — enters the concept inventory as a name, so `requires(X, labeled_data)`
can meet `isa(supervised, X)`.  Role names are recorded and never paired.

`graph_inventory.supply_demand` reads the **proof frontier** from the compiled clauses:
a question clause's content literals are demand; a rule clause's negative literals are
demand unless the same literal occurs positively somewhere; facts and rule conclusions
are supply.  A population witness is neither — counting it would make every rule
premise look satisfied and leave the frontier empty.

`graph_pairs.py` enumerates nine shapes, in three sources:

1. **frontier** (every pair judged): concept↔concept; relation↔relation straight and
   inverse; relation-with-constant to relation-with-constant on the same subject;
   argument-constant subsumption `R(X,k1) → R(X,k2)`, judged as the concept pair
   `(k1,k2)`; and the grounded cross-kind shape both ways, `R(X,k) ↔ isa(C,X)`, keyed
   first on a shared lexical root, plus the variant with the concept on the constant;
2. **exhaustive** same-kind pairs, up to `EXHAUSTIVE_LIMIT` (120), above which the
   budget is filled by token overlap and every unjudged pair is recorded;
3. **composition** for P2, `R1(X,Y) ∧ R2(Y,Z) → R3(X,Z)`, enumerated only where the
   theory holds the actual chain.

Seven filters refuse a pair before any judge call and again on the judge's output, each
refusal recorded with its reason: a **passage-related pair** (only the passage's own
direction and sign is admissible; the converse and any universal strengthening of a
particular are refused), a **question-only body name**, a **question restatement**,
**polarity against the passage**, a **gradable adjective across two comparison
classes**, a **class bridged to an adjective relative to it**, and an **entity-name
pseudo-class**.

Two of those need care about what exactly they refuse.  The question-only rule refuses
a **direction**, not a pair: a frontier pair's demand side is normally a name only the
question states, and concluding it is the whole point, so only the direction that would
put that name in the rule *body* is dropped, and the pair is refused outright only when
both its names are question-only.  The question-restatement rule applies only when the
body is the **sole** known class of a question subject that is a constant; reading a
bound variable as a subject would refuse the entire frontier of a generic question.
The entity-name rule applies only to a **concrete** entity whose name reads as a proper
name, so ordinary common-noun classes stay bridgeable.

`POLICY_STRICT` is the switch: when False only the sign and direction contradictions
are refused.  Batches hold at most 40 pairs in a frozen salted order.

## The direction judge and bridge serialization

The judge sees, per pair, the two names, their kind, one readable example atom each
with its sign, and the passage sentences each name occurs in.  It **never sees the
question sentence**: a name may occur in the question as well as the passage, and the
question's own units are excluded when the sentences are collected, for the grader as
well as the judge.  It returns one label per pair:

```
A_IMPLIES_B  B_IMPLIES_A  EQUIVALENT  A_IMPLIES_NOT_B  B_IMPLIES_NOT_A
EXCLUSIVE    INVERSE (relations only)  RELATED_BUT_NO_IMPLICATION
UNRELATED    UNCERTAIN
```

A missing line is `UNCERTAIN`; an unknown label is `UNCERTAIN` with the raw text
recorded.  The model writes no formula: `graph_judge.serialize` builds every clause
from the label and the exact atoms the pair was enumerated with, including the
contrapositive when a displayed occurrence was negated.  A holistic call over the whole
inventory is the recall backstop and takes the same parser and the same filters.

The bridge sets are cumulative, and each is submitted to gk under its own name.
`P1` holds the frontier pairs with a decided label. `P2` adds the exhaustive and
composition sources, and the frontier's `UNCERTAIN` pairs offered in both directions.
`P3` is defined but never populated. `P0`, `P1`, `P2` and `P3` are the stored names in
the `pool` field of each record row.

A `RELATED_BUT_NO_IMPLICATION` pair never becomes a bridge, and neither does an
`UNCERTAIN` pair from a source other than the frontier. At most 60 distinct bridge
formulas per case; every omission is recorded.

Every bridge carries the pair it came from: `pair_id`, and `pair_label`, the judge's
own label before `both_directions` rewrote an undecided pair into two directed rules.
A proof can therefore say how many of its bridges rest on a pair the judge did not
decide, which is what selects the bridges the grader sees.

Every bridge is compiled by `litbridge_compile.build_world` under the graph option set,
named `dynamic_bridge_<case>_graph::<id>_<n>`, defeasible with `$block`, at **full
confidence**.  A low `@confidence` is never written: it prunes the search and compounds
on repeated application.

## Proof search, grading and tiers

`graph_search.search` makes one gk submission per bridge set. `P0` is the graph
theory alone, with no generated bridge, so a proof there rests on the translation only.
`P1` and `P2` add their bridge sets cumulatively. Each submission has its own time
limit (5/5/8/12 seconds). gk searches both polarities in one call. A timeout is
recorded as a timeout, never as Unknown.

For every proof: the cited bridges are collected, the cited set is replayed, and each
bridge is deleted in turn while the answer survives, giving a deletion-minimal set.
Then, **unconditionally**, each member of the first minimal set is excluded and gk is
asked again, at most four times, to see whether a second route exists.  Only after that
pass does the search stop.  A bridge's own population witnesses are dropped before
submission: a witness a bridge introduced must never ground that bridge's body.

Grading runs after the search, for every bridge a minimal set cites and for no other.
Each graded bridge gets **its own message** — the rule, the program's English reading
of it, and the two names' sentences — so a bridge's grade is one cached call that does
not move when the rest of the cited set changes.  The message never carries the rule
id, which is minted per run.  A set cites at most two bridges, so a case that found a
proof costs at most two grader calls and a case that found none costs zero.

The grader returns `LIKELY / PLAUSIBLE / UNCERTAIN / UNLIKELY / FALSE`, whether the
formal polarity and argument order match the English reading code wrote, and for a
negative bridge an answer to "name one thing that is both".  **A grade never deletes a
proof and never turns an answer into Unknown.**

Restricting the grader to bridges from pairs the judge did not decide was measured and
rejected: it let through 8 wrong FOLIO proofs whose bridges came from decided pairs,
and saved one EB proof.  The judge's confidence (`HIGH`/`MEDIUM`/`LOW`) is recorded
beside every grade as a calibration feature, and reads as `LIKELY`/`PLAUSIBLE`/
`UNCERTAIN` when no grade was taken; on a pair the judge did **not** decide it is
confidence in saying "I do not know" and never stands in for a grade.

**Evidence.**  A bridge born from an undecided pair is `BACKGROUND` whatever tag the
judge's reply gave it: the judge read the same sentences and could not say which way
the implication runs, so the passage did not state it.  Under `--evidence stated` those
bridges are refused — which keeps them for the open-world family and drops them for the
closed-world ones, with no extra call.

**The witness policy.**  The graph converter emits no population witnesses of its own,
but a proof can still cite one when the ordinary theory supplies it.  A witness is a
`$some_C` constant asserting that at least one `C` exists, which nothing in the English
said.  A proof that cites one is credible only when the question is a hoisted
bare-plural generic question and the answer is the positive one.  A witness used to
refute a universal question is an invented counterexample; every proof records
`cites_witness`, `witness_ok` and `witness_counterexample`, and the scored row counts
them separately.

Tiers, worst to best: `T0` an unassessed, unlikely or false bridge, or proofs of both
polarities; `T1` a graph proof from at most two bridges, each `LIKELY` or `PLAUSIBLE`;
`T1a` a graph proof that uses **no** generated bridge, so the two translations disagree
on provability; `T2` a detailed proof after unit retranslation; `T3` a lifted detailed
bridge proof.  Only T3 and T2 may become the run's answer.

## Lifting into the ordinary representation

A minimal graph proof is a record of what it used: the units, the atoms, the bridges, the
question literal.  `graph_lift.py` asks whether the same step holds over the case's own
detailed atoms.

The boundary is the literal bridge's own machinery.  Candidate atoms are the ones
`litbridge_atoms.build` displays, so each carries its exact compiled template; the
alignment is unit-local first, then by shared entity ids and rule variables, then by
token overlap.  The reply is parsed by `litbridge_rules.parse_response` against that
vocabulary and compiled by `litbridge_compile.compile_one`, whose exact-template route
governs a model-written rule — so a rule made only of displayed atoms compiles to those
atoms or is refused structurally.  Each coherent set is appended to the **ordinary**
clauses in its own gk world, at most six per case.

Outcomes: **lifted proof**, **source translation gap** (the model wrote nothing over
the ordinary atoms), **graph over-abstraction** (the lifted rules prove a different
answer), **incomplete lifting**, **ordinary proof still blocked**.

When a proof-used unit has no ordinary counterpart, that unit alone is retranslated
with the ordinary Stage-2 prompt plus its English, its Stage-1 unit and the graph atoms
the proof used, and the regenerated package is spliced into a **copy** of the ordinary
Stage 2.  The question package is protected; at most two units per case.

## Flags, record and output

```
-graphtrans           layer 1: the retranslation and one gk call
-nographtrans         force layers 1 and 2 off, wherever it stands
-graphbridge          layer 2; implies -graphtrans
-nographbridge        force layer 2 off; layer 1 unaffected
```

Option keys: `graphtrans_flag`, `nographtrans_flag`, `graphbridge_flag`,
`nographbridge_flag`.  Every `-stack*` set and `-abstract-max` turn layer 1 on;
`-stack`, `-stack-open` and `-abstract-max` turn layer 2 on as well ([configuration](../reference/configuration.md)).

Layer 2's three settings are **module constants in `graph_procedure.py`**, with no
CLI flag and no `globals.options` key:

| constant | default | what it decides |
|---|---|---|
| `LIFT` | `False` | lift a graph proof into the ordinary theory.  Measured at 0 net for 56 calls, so a graph proof stays a labelled experimental result |
| `EVIDENCE` | `"any"` | layer 2's acceptance evidence mode: `"any"` or `"stated"` |
| `DEFAULT_SOURCES` | `("frontier",)` | the candidate sources layer 2 enumerates; `FULL_SOURCES` adds `exhaustive` and `composition` |

`run_bridges` and `credible_answer` keep their `sources=`, `evidence=` and `lift=`
parameters, so the study harnesses in `tools/` pass their own values; `solve.py`
passes the constants.

**What the graph route shows, per output level.**  Whatever `solve.py` shows for an
ordinary answered case at a given level, the graph route shows for the gk call that
produced its answer — under the **ordinary headers**.  A stage after the initial attempt
parses, converts and calls gk again, so those headers appear twice in one run; what
says whose they are is the single line `--- stage: graphtrans ---` printed before the
stage runs, and the stages block at the end ([runtime records](../reference/runtime-records.md)).

| level | the graph route shows |
|---|---|
| `-explain` | the English proof of the graph gk call, rendered under `open_names_flag` ([the source map](../code/source-map.md)).  Nothing else: an answer the graph route found looks like an answer the initial attempt found |
| `-logic` | `--- stage: graphtrans ---`, then `=== sentences mapped to clauses: ===` for the graph theory, the formal clause under each proof step, and the `=== stages ===` block |
| `-details` | `=== stage 2 (logic JSON, <model>) ===` (the open triples), `=== prover input (JSON) ===` and `=== prover result (JSON) ===` for the graph call |
| `-debug` | the graph Stage-2 LLM call's raw response, `=== prover params ===` for the graph call, and the route's own step-by-step trace (`=== the second translation, step by step ===`) |

No header carries a route name and no key in the JSON output is graph-specific: a
reader who wants to know which stages ran, and which produced the answer, reads the
stages block.

**The record.**  `collect["graphtrans"]` keeps the whole layer-1 record: the
open-triple `stage2_graph`, the graph `clauses`, the `variant_rules`, `proof` (the
steps), `gk_result` (the whole gk result as JSON), `gk_verdict` (its one-word
verdict), `gk_command` and the translation's own measurements.  Only the compiler
sidecar and the unparsed result string are dropped.  `collect["graphbridge"]` keeps
the search record; the minimal set `credible_answer` accepted carries `gk_input`,
`gk_command`, `gk_result`, `answer_string` and `explanation` — the replay call the
answer rests on — and the verdict carries `set_index`, which is how `solve.py` finds
that row.  The run's own top-level `proof` and `gk_command` are the graph call's
([runtime records](../reference/runtime-records.md)).  `globals.ABSTRACTION_ROUTES` — also a constant, not a key —
names the routes `solve.py` can dispatch and the order it runs them in:
`graphtrans`, `litbridge`, `graphbridge`.  A route the list omits never runs,
whatever its own flag says.

**What layer 1 does that nothing else does.**  Every defeasible rule of the graph
theory carries at most confidence 0.95, so a proof that used one comes back as
"Probably True." / "Probably false." and is scored in its own column.  Variant rules
bridge a marked form to its base form — plural to singular, past to present — but only
when BOTH forms occur in the case, one direction only, at confidence 0.9, named
`norm_<n>` so the proof shows them; nothing is written for `will_`, `would_`,
`gets_to_` or another auxiliary, where the tense is the meaning.  Names are never
rewritten or collapsed: hyphen to underscore is the only rewrite, and lemmatization
only finds the pairs.

`collect["graph"]` holds the translation and its issues, the option dict and its hash,
the inventory sizes, the pairs enumerated and refused with reasons, the labels, the
bridges per candidate group, the per-group gk outcome, the minimal sets, the grades, the lifting
record, the tier and the stopping reason.

`record["acceptance"]` holds one verdict per minimal set: whether the set is credible,
why not when it is not, `graded_by` per bridge (`grader`, `judge confidence` or `judge
label`), how many of its bridges came from an undecided pair, and the three witness
fields.  `tools/graph_grade_drift.py` reads two runs and prints the agreement matrix
for the bridges graded in both, keyed on the printed formula rather than the rule id.

`-logic` prints a per-step trace, `-details` adds the pairs and labels, `-debug` the
raw replies.  In a rendered proof a graph bridge is **"added open-name rule (graph)"**
and a lifted one **"added rule (lifted from the graph proof)"** — never "background
knowledge", which is reserved for the axiom file.

## Related documentation

- [Retries and retranslation](retries.md)
- [Literal bridges](literal-bridges.md)
- [Pipeline](pipeline.md)
- [Retry and abstraction code](../code/retries-and-abstraction.md)
- [Testing](../development/testing.md)
