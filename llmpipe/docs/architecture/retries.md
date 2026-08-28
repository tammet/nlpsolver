# Retries and retranslation

The six stages that can run after the canonical theory returns `Unknown`.

Two are deterministic and make no model call. The critic and the two graph
stages each make one or more. A stage runs only while the question is
unresolved, and the first definite answer stops the rest.

| stage | model calls | what it changes |
|---|---|---|
| `fallback_norm` | none | converts the same parse again with token and shape normalizations on |
| `fallback_hyp` | none | assumes a conditional question's antecedent in an isolated theory |
| `critic` | one, plus one rerun | audits the translation and may ask for one retranslation |
| `graphtrans` | about one per case | translates the case again into open triples |
| `litbridge` | two rounds | proposes implication rules over the case's own atoms |
| `graphbridge` | about 2.7 per case | invents implications between the open names |

`conservative` selects the first two, `balanced` adds the critic and graph
retranslation, and `high-recall` adds graph bridge generation. The literal
bridge is explicit only. The command-line keys are in the
[command-line reference](../reference/command-line.md).

## The two abstention fallbacks

Both are on by default, in every configuration, and neither makes a model call.
When the initial attempt leaves a question unresolved, each converts the same
Stage-1 and Stage-2 parse a second time and calls gk once more.


### Where they sit

`fallback_norm` runs first, then `fallback_hyp`, then the critique pass
then the graph and bridge stages, in the order `globals.ABSTRACTION_ROUTES`
gives.  Three rules
fix the order:

- A definite answer from the initial attempt is never disturbed.  Each fallback runs only
  while `solve._unresolved(answer)` holds, so a base win cannot be re-opened.
- The first definite fallback answer stops everything after it, including the
  second fallback.
- `fallback_hyp` converts with `fallback_norm`'s switches on.  A case that
  needs both a normalization and the hypothetical reading is answered there.

`answered_by` carries `fallback_norm` or `fallback_hyp`, and `-summary` prints
that name as the answering stage.

| fallback | what it changes | file |
|---|---|---|
| `fallback_norm` | token and shape normalizations, plus the question rewrites the text licenses | `solver/fallback_norm.py` |
| `fallback_hyp` | the hypothetical reading of a conditional question, in an isolated theory | `solver/fallback_hyp.py` |

### The normalizations

Six switches ride in `fallback_norm`'s conversion.  Each applies only on
evidence the case itself carries, so no lexical claim is made about a word the
case does not use.

| switch | what it folds | example |
|---|---|---|
| `DASHNORM` | hyphen and space spellings of one word, when both occur | "well-paid" onto "well paid" |
| `CASENORM` | letter-case variants of one token in one predicate position, when both occur | "Estonian city" onto "estonian city" |
| `COMPNORM` | a comparative relation name onto its base gradable adjective | "taller than" onto "tall" |
| `LISTPREP` | membership relations onto `on`, when the object names a list | `in(X, "Top 10 list")` onto `on(X, …)` |
| `SINGROLE` | a bare plural noun value inside an `eventprop` role tag | `[eventprop, $target, "dogs"]` onto `"dog"` |
| `QUNIV` | nothing; it keeps a universal generic yes/no question universal when the hoist is refused | "Elephants are not animals?" stays quantified |

`CASENORM` is the one pass this chapter owns; the other five are converter
passes described in [abstraction](abstraction.md) that only this fallback
turns on.  It collects every
string argument with its position, where a position is one of `("isa", 1)`,
`("has property", 1)`, `("is rel2", 1)` or an `eventprop` value.  Two tokens
fold only when they differ by letter case **and** share a position.  It never
folds across positions: "Ailton" as an `isa` instance sits in argument 2, so
it never folds onto "ailton" as an `isa` class in argument 1.  The position is
what protects an entity name, because the pass runs before `apply_una` marks
entities and a name is still bare there.  Variables (`?:`), meta tokens
(`$`), skolems and already-marked entity constants (`#:`) are skipped
outright.

### The question rewrites apply to triggers, not on formula shape

Two rewrites read the question differently, and each needs evidence from the
case's own words before it applies.

- The **cued `xor -> or` rewrite** reads an `xor` in a question body
  inclusively only when the question's wording carries an inclusive cue: "or
  both", "at least one", "one or both", "and/or", "either or both", "possibly
  both".
- The **apposition presupposition** asserts a ground typing of a question body
  only when Stage 1's question text shows that class in an apposition: "X, a
  Y", "for X, a Y", "X (a Y)".  A class that is a plain conjunct of the
  question is part of what is being asked.  "Is Ted a student and employed?"
  asserts nothing.

`fallback_norm._question_text` supplies the wording.  It reads the raw text of
each Stage-1 unit marked `type: "query"`, and of any raw sentence ending in
"?".  When it finds neither, it returns the empty string and every trigger
reads as absent.

### Exclusive before inclusive

`fallback_norm` submits at most two theories.

1. The first carries the normalizations and the cued rewrite, and reads any
   `xor` exclusively.  Its clause set is compared with the initial attempt's, on
   the clause keys without `@nl`.  An identical set means nothing this
   fallback enables applies to this case, and no gk call is made.
2. The second runs only when the first ended unresolved **and** the question
   body holds an `xor` with no inclusive cue.  It converts
   `inclusive_theory(s2_json)` with the same switches and calls gk once.

The exclusive reading always goes first.  A question where both disjuncts hold
is `False.` under the exclusive reading, and letting the inclusive reading run
first would override that with `True.`.  The record's `answered_by_reading`
names the reading that answered.

When step 1's conversion comes out identical to the initial attempt's and the
question carries an uncued `xor`, the initial attempt's own Unknown stands as the
exclusive reading's answer and only the inclusive submission is made.

### The isolated theory

`fallback_hyp` triggers on `["question", ["implies", A, B]]` and takes the
first such question only.  Without that shape it stops before any gk call.

`hypothetical_theory` builds a copy of the premise packages, plus
`hyp_<sid>` holding A in W0, plus B as the question.  The original question
package is dropped, so the material reading is not also present.  Nothing is
inserted into the ordinary premise set: the answer the initial attempt produced is
undisturbed, and no later stage inherits the assumption.

```
["and",
 ["@id", "S1", ["holds", "W0", <premise>]],        ← unchanged
 ...
 ["@id", "hyp_S2", ["holds", "W0", A]],            ← the local assumption
 ["@id", "S2",     ["question", B]]]               ← the consequent is asked
```

`_strip_normally` removes a `normally` wrapper from A before it is assumed.

### The ex falso hazard, and where the reading disagrees with FOLIO

gk searches for a proof of the question and for a proof of its negation.  It
does not conclude ex falso from an inconsistent premise set.  Assuming an
antecedent the premises refute therefore answers nothing rather than
everything.

`REFUTATION_CHECK` (off by default) makes `refutation_theory` ask first
whether the premises refute A: the premise packages with A as the question,
one gk call.  A `False.` there stops the fallback and the record says
`skipped: "the premises refute the antecedent"`.

The hypothetical reading disagrees with FOLIO's vacuous-truth convention.
FOLIO calls a conditional question `True.` when the premises refute its
antecedent; this reading answers whatever B follows from A.  The check exists
for exactly that case, and it only catches the case when gk can prove the
refutation.  A refutation gk can prove already makes the initial attempt's
material reading answer `True.`, so the fallback is not reached; that is why
the check is off.  FOLIO 73 is the other side: gk cannot prove the
refutation there, the reading runs, and the answer comes out `False.`
against a gold `True.`, with the check on or off.

### Configuration, not flags

Each fallback names its own configuration as module-level booleans, all
`True`:

```python
# solver/fallback_norm.py
QUNIV = True      # keep a generic universal question universal
DASHNORM = True   # hyphen/space fold when both variants occur
COMPNORM = True   # comparative relation name -> base form
LISTPREP = True   # in/include -> on for list-naming objects
SINGROLE = True   # singularize bare plural eventprop values
CASENORM = True   # letter-case fold, same predicate position, both variants present
QOR_CUED = True   # question-body xor -> or when the text carries an inclusive cue
QPRESUP = True    # assert an apposed typing from the question text
INCLUSIVE_SECOND = True  # after an Unknown, retry an uncued xor question inclusively

# solver/fallback_hyp.py
REFUTATION_CHECK = False  # ask first whether the premises refute the antecedent
```

Each boolean maps to an internal option key that a converter pass already
reads: `quniv_flag`, `dashnorm_flag`, `casenorm_flag`, `compnorm_flag`,
`listprep_flag`, `singrole_flag`, `qor_flag`, `qpresup_flag`.  `run` saves
those keys, sets the ones its booleans enable, converts, and restores them in
a `finally` block.

None of the eight keys has a CLI flag.  The initial attempt runs with every one of
them `False`, and its behaviour under always-on normalizations is not
measured.  An experiment that wants one switch off edits the boolean for one
configuration; `tools/test_fallback.py` asserts that the initial attempt leaves all eight
off.

### The fallback record

`collect["fallback"]` holds `{"norm": …, "hyp": …, "answered_by": …}`.  Each
fallback's record names itself, lists the switches that were on, and carries
one entry per submission:

| field | what it holds |
|---|---|
| `reading` | `exclusive`, `inclusive`, `refutation` or `hypothetical` |
| `clauses` | the submitted clause list, with `@nl` source English |
| `clause_diff` | added and removed clauses against the initial attempt's submission |
| `gk_result` | the raw gk result string |
| `answer` | the processed answer, first line |

Alongside the submissions the record carries `answered`,
`answered_by_reading`, and one of `stopped_at`, `skipped` or `note` when the
fallback made no gk call.  `runtests.py` copies the whole record into every
case JSON, so a recovery can be read back without re-running anything.  When a
fallback answers, its submission's gk call becomes the run's top-level `proof`
and `gk_command`; when one runs without answering, the top level stays the
initial attempt's ([runtime records](../reference/runtime-records.md)).

### Cost, measured

At most two gk calls for `fallback_norm`, one for `fallback_hyp` (two with
`REFUTATION_CHECK` on), and no LLM call ever.  The bounds are measured
rather than asserted.  On FOLIO (203 cases × 3 models) and MLE-100, with the
check on:

| set | `fallback_norm` runs | its gk calls | max | `fallback_hyp` runs | its gk calls | max |
|---|---|---|---|---|---|---|
| FOLIO | 379 | 82 | 2 | 368 | 36 | 2 |
| MLE-100 | 218 | 50 | 2 | 212 | 126 | 2 |

Most runs cost nothing.  On FOLIO 300 of 379 `fallback_norm` runs made no gk
call, because the conversion came out identical to the initial attempt's, and 350
of 368 `fallback_hyp` runs made none, because the question was not a
conditional.

Effect, against the same configuration with `-nofallback`:

| set | initial attempt alone | with both fallbacks |
|---|---|---|
| FOLIO, no critic and no graph or bridge stage | 376 | 391 |
| MLE-100, the same | 122 | 129 |
| FOLIO, all stages enabled | 436 | 445 |
| MLE-100, all stages enabled | 137 | 145 |

With every stage enabled, 8 of the 16 FOLIO recoveries and 7 of the 12 MLE-100
recoveries are cases no later stage answers on its own.  No fallback answer
stopped a later stage that had the case right without it.

`REFUTATION_CHECK` accounts for half of `fallback_hyp`'s gk calls: MLE-100
falls from 126 calls to 63 with it off, and no answer changes.  It has not
returned `False` on any measured set, which is why it is off.

### Fixtures

`tools/test_fallback.py` holds 90 checks and calls neither an LLM nor gk.
Every mechanism with a trigger is written as an applies / must-not-apply pair: the
cued rewrite against a plain "either … or", the apposition against "Is Ted a
student and employed?", `casenorm`'s fold against its refusal to cross
positions, `fallback_hyp`'s trigger against a plain question.  The
exclusive-before-inclusive order is checked by standing in for the converter
and gk and reading back which submissions the record holds.

`tools/check_fallback.py` runs named cases through the shipped path and prints
which fallback answered each.  `tools/score_fallback.py` scores one configuration and
`tools/score_fallback_stack.py` pairs the enabled stages against the same set with
`-nofallback`.

Enabled by the `balanced` default, and by every `-stack*` set and
`-abstract-max`; `-nocritic` turns it off.  When the initial attempt ends
Unknown after its own checks and retries, one model call reads the case and
says what is wrong with the translation the pipeline just made.

## The critic

One model call audits the translation the initial attempt produced and
reports what is wrong with it. A blocking finding on its own chain
makes Stage 2 run once more with the findings appended. One critique,
one rerun.

### What the critic reads

`critic_render.critic_user_message` builds four sections — TEXT, STAGE 1,
STAGE 2, RESULT.  Stage 1 is compacted to one block per unit (id, type, text,
entities as `id [c|g,category]`, actions, definites, adjectives, confidence).
Stage 2 is, per `@id` package, one compact logic line and one **program-made**
English paraphrase of that same line.  The raw JSON never appears, and the
paraphrase is built by template rather than by a model: the critic has to be
reading our logic, not a second model's summary of it.

The critic is never shown an accepted answer.

### What it returns

JSON: `answer_by_reading` (true / false / unknown), `chain` (the units its
reading rests on), `derivation`, up to six `findings`, and a `verdict`.  A
finding carries the units, a `kind` from a fixed vocabulary (quantifier,
direction, negation_scope, guard_unproducible, shape_mismatch, name_mismatch,
entity_split, missing_participant, dropped_condition, modality, definite,
question_form, stage1_unit, other), a severity (blocking or note), the English
and the logic it quotes, the problem, and a fix.

`critic_pass.parse_reply` validates all of it: a reply whose reading or
verdict is not in the vocabulary is a parse failure and counts as KEEP; a
finding whose fix quotes no word of its own unit's text is dropped and counted
as `unquoted_fix`.

### What the pipeline does with it

`critic_pass.decide` returns RETRANSLATE only when the reading is definite AND
a blocking finding lies on the chain (a `question_form` finding counts as on
the chain).  Everything else is KEEP.  The stage is 1 only when a retained
finding has kind `stage1_unit`.

On RETRANSLATE the findings — and only the findings, never the reading, the
chain or the derivation — are appended to the Stage-2 input as a corrective,
and the ordinary converter and gk follow.  Whatever the outcome, there is no
second critique.  A rerun that changes a unit nobody asked about is recorded.

### The critic record

The critic runs after the two fallbacks and before every graph or
bridge stage, so a repaired translation is what those stages see. The
fallbacks run first because they cost no model call.

`collect["critic"]` holds the report, the retained and dropped findings, the
verdict, the units asked for, the corrective, the answer before and after, and
which units the rerun changed.  `-explain` prints the reading, the chain, the
findings, the verdict and what the rerun changed.

**Who answered the rerun.**  The rerun re-enters `_english_to_answer_body`, so
the two fallbacks run again on the retranslated Stage 2 (the graph and bridge
stages
do not: `_route_enabled` refuses inside a rerun).  `record["rerun"]` therefore
carries the inner run's `answered_by` and its `fallback` record beside
`stage1`, `stage2` and `answer`.  The case's own `answered_by` stays `critic` —
the retranslation is what made the answer reachable — and `-summary` names the
stage that closed it:

```
answered_by: critic (rerun answered by fallback_norm)   (front door: Unknown.)
```

`_summary_record` carries the same value as `rerun_answered_by`, `None` when
the critic did not answer.  When the critic answers, the rerun's own gk call —
its `proof`, `gk_command`, `nl_proof` and `final_clauses` — becomes the run's
top-level record ([runtime records](../reference/runtime-records.md)).

The harness is `tools/run_critic_pass.py` and `tools/score_critic_pass.py`;
fixtures are `tools/test_critic_pass.py`.

---

## Graph retranslation

`graphtrans` translates the case a second time into open triples, compiles that
translation under a frozen option set and calls gk once. There is no judge and
no bridge. It is the whole mechanism on closed-world material.
[Graph representation](graph-representation.md) describes the translation, its
structural safety rules and the compiler configuration.

## Graph bridge generation

`graphbridge` invents implications between the open names and searches the
graph theory with them. It implies `graphtrans` and never translates twice. A
graph proof is lifted back into the ordinary representation, and only a lifted
proof becomes the run's answer. See
[graph representation](graph-representation.md).

## Literal bridge generation

`litbridge` asks the model for implication rules over the case's own displayed
atoms, compiles them beside the stored theory and resubmits to gk, in two
rounds. A proof found then is an ordinary gk proof; only the rendering names
the invented rules, as `[added rule (round N)]`. See
[literal bridges](literal-bridges.md). It was measured net-harmful on
closed-world material, so no named configuration turns it on.

## Optional acceptance checks

`-accept` applies proof-local checks to a critic or graph answer before that
answer is taken. It is off by default. See
[experimental options](../reference/experimental-options.md).


## Related documentation

- [Pipeline](pipeline.md)
- [Graph representation](graph-representation.md)
- [Literal bridges](literal-bridges.md)
- [Command-line reference](../reference/command-line.md)
- [Retry and abstraction code](../code/retries-and-abstraction.md)
- [Runtime records](../reference/runtime-records.md)
