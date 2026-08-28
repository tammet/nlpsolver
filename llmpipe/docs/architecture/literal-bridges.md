# Literal bridges

This page describes `-litbridge`. It is an explicit option. It belongs to no
named configuration.

It exists for passages whose answer needs a fact the passage never states: a
step of world knowledge that the reader supplies without noticing. Rather than
translating the case again, the mechanism keeps the ordinary translation and
asks the model for implication rules written in the case's own atoms, so that
every invented rule is visible in the proof that uses it.

The mechanism asks the model for implication rules over the case's own
displayed atoms, compiles them to clauses, appends them to the stored theory,
and calls GK again. It runs two rounds.

Rule assessment is experimental. `litbridge_grader.MODE` selects it and is a
module constant, not a command-line option.

Every mechanism in [abstraction](abstraction.md) and [abstraction](abstraction.md) changes how the *text* is converted.  This one changes
the *theory*: when the pipeline cannot answer, the model is asked for implication rules
connecting atoms the case already contains, and those rules become extra clauses.  It is
off by default, on under `-stack-open` and `-abstract-max`, and cancelled by
`-nolitbridge` wherever that
stands on the command line.

## Where it sits

`solve.py` runs the ordinary pipeline to an answer.  If `litbridge_flag` is set and the
answer is still open — `Unknown.`, empty, or an `Error:` string — the bridge rounds run.
The machinery **never calls gk and never produces an answer**: it returns clauses, and
`solve.py` appends them to the clause list it already has and calls the prover again.
A proof found then is an ordinary gk proof.

Two rounds, in `_english_to_answer_once`:

1. **Round 1.**  One LLM call for rules over the displayed atoms.  No rule accepted →
   nothing is added, gk is not called again, and the loop ends.
2. Clauses appended, `prover.call_prover`, `process_proof`.  A definite answer ends it.
3. **Round 2.**  Asked only when round 1's clauses reached gk and gk still proved
   nothing.  The prompt says so and lists what was tried, so the model is not handed
   back its own rejected rules.  No new rule → no gk call.
4. Round 2's clauses are appended to the same list, so gk sees **round 1 and round 2
   together**, then `process_proof` again.
5. Still unresolved → `answer` and the clause list are restored to what the ordinary
   pipeline produced, so the run ends exactly where it would have without the detour.

Cost per unresolved case: one LLM call and one gk run at minimum, five calls and two gk
runs at the maximum with `litbridge_procedure.EXTRAS` on ([literal bridges](literal-bridges.md)).

## Candidates: what the model may build a rule from

`litbridge_procedure.bridge_context` reads the case once, with no LLM call:

1. `litbridge_atoms.stage2_occurrences` reads the raw Stage-2 packages.  This is the only
   place the **semantic** sign of an atom is recorded — a rule premise is not a negative
   assertion just because clausification negated it.  Dropping that sign turns
   `not mean(X,Y) → not mean(X,Y)` into `mean(X,Y) → mean(X,Y)`.
2. Every such atom is converted **in isolation** through the real converter
   (`litbridge_converter._convert` → `logconvert.rawlogic_convert`) under the run's own
   options ([literal bridges](literal-bridges.md)), both signs.
3. The converted literal must **occur in the case's own theory**.  One that occurs
   nowhere is recorded in `mapping_diagnostics` and never shown.
4. What survives is displayed to the model as printed atoms, and each carries its
   converted literal.  **That literal is the template**, and it is what makes the
   compilation exact.

Caps: `MAIN_CAP` 80 main atoms, `SECONDARY_CAP` 24 helpers.

## Compiling a rule to clauses

`litbridge_compile.compile_one` has two routes and a check that ties them together:

- **the exact-template route** (`compile_rule_exact`) rebuilds every literal of the rule
  from the template of the candidate it matched;
- **the converter route** (`simple_rule_to_package` → `litbridge_converter.compile_bridge`)
  converts the rule as a spliced Stage-2 package, under the same options;
- `verify_against_templates` keeps the converter's output only when it equals the
  exact-template clause up to renaming.  Otherwise the template clause is used.

So for a rule the model wrote — `origin` `llm_general` or `system_ground_specialization`,
the two `EXACT_ORIGINS`, tested by `governs()` — the operative clause is template-equal
whichever route wins.  A **channel rule** ([literal bridges](literal-bridges.md)) is not `governs()`: it takes
`_compile_one_with_fallback`, the converter route with no template check and a
clause-native fallback, and there the option set reaches the clause directly.

Every bridge clause is defeasible: `A → normally(B)`, which clausifies with a `$block`
literal, so a later fact defeats it.  No `@confidence` is written — a low confidence
prunes proof search and compounds on repeated application
A rule whose compiled clause the theory
already contains is refused (`already_present`, exact up to literal order and variable
renaming, after the `$block` guard is removed).  Tautological auxiliaries are stripped.

## The two code-built channels (`litbridge_procedure.EXTRAS`)

Off.  `EXTRAS` is a module constant in `solver/litbridge_procedure.py`, with no CLI
flag and no option key; `solve._run_litbridge` reads it.  Each channel adds one LLM
call in round 1 in which the model does not write a rule — it only picks among pairs
the code enumerated.

**Distinctness**, `isa(C,A) ∧ isa(C,B) → ¬(A=B)`.  Eligible when a question clause holds
a negative equality between two ground names; the English question carries a difference
cue (`different`, `distinct`, `differ`, `not the same`, `unlike`, `separate`); the
passage gives both names a class in common through single-literal positive `isa` facts;
and both class atoms are displayed.  Nearly always silent.

**Negative relation**, `A → ¬B`.  A question clause holds the negation of the goal, so an
atom appearing *positively* there is one whose negation would close the question.
Eligible when `B` is asked that way; `A` is stated by the passage (a fact states its
literal, a rule its positive conclusion; question and population clauses state nothing);
they are different atoms naming the same participants in the same order; and the passage
does not already state the rule.  At most 6 pairs each, sorted by cost.

## The encoding the bridge is converted under

A bridge clause has to unify with the theory it is appended to, so it must be converted
the way the theory was.  `solve.py` captures the run's own `globals.options` **once**,
before the first bridge conversion, clears every `nofix_*`, drops `prenorm_flag` (a
pre-Stage-1 phase; the bridge starts at Stage 2) and applies `BRIDGE_OPTION_OVERRIDES` —
`typeenrich` off, `guarddrop` off, `noexceptions` off, the three passes that would strip
the `$block`.  That dict travels as `configuration` and `bridge_options` returns it as it
stands.

Capturing it once matters: `litbridge_converter.scoped` replaces `globals.options` while
a conversion runs, so a call made inside one would read the scope rather than the run.

A **string** `configuration` still selects the older behaviour — the label a stored case
carries, rebuilt through `replay_case._abstract_max_options`.  That path is for replays,
where the live options are the runner's and not the case's; `solve.py` never uses it.
Measured sensitivity of the candidate set to a wrong option set, and the reasoning
behind the design, were recorded in a local memo that this repository does
not track.

## What the output shows

A bridge clause is named with `utils.LITBRIDGE_CLAUSE_PREFIX` (`dynamic_bridge_`) and
carries its round, so `proof_explain` can tell it from the passage and from a standing
axiom.  It is not counted as background knowledge:

```
Added rules (invented for this question, defeasible):
  If some X is a budgie then normally X is a parakeet.
    Why: a rule this run added (round 1), held unless something contradicts it.
Proof steps:
  (1) If some X is a budgie then normally X is a parakeet  [added rule (round 1)]
  (2) Tweety is a budgie  [sentence 2]
```

`-logic` and above print a per-round trace: the option set the bridge was converted
under, the candidate count, the rules written, the clauses added, whether gk was called
again and whether it proved anything, and for each channel whether it called and why not.
`-details` and `-debug` add the signed conclusion counts, every rule the compiler refused
with its reason, the parser's rejection categories and anything over the hypothesis
limit.  A batch run gets the whole record as `collect["litbridge"]`, and the round
that proved the question is the run's top-level `proof` and `gk_command` ([runtime records](../reference/runtime-records.md)) — the
initial attempt's own call is kept beside them as `front_door_proof` and
`front_door_gk_command`.

## Origin and further reading

The machinery is the experiment line of 2026-08, merged from forty modules into seven
`litbridge_*` files.  A local memo records that merge, the
seven defect classes a version-chain collapse hides, and the oracles that check it:
`tools/litbridge_replay_oracle.py` recompiles every archived rule of the finalized runs and
hashes the outcome, and `tools/test_litbridge_converter.py` covers the option scope and
the citation reading.  `tools/run_unifier_v6_1.py` is the experiment harness, which runs
the same rounds plus the parts a pipeline does not need: separate submissions per round,
minimisation of the proving set, and a bounded search for a different proof.

---

## The per-cited-rule grader (`litbridge_grader.MODE`)

Off.  `MODE` is a module constant in `solver/litbridge_grader.py` — `None` off,
else `"stated"` or `"any"` — with no CLI flag and no option key.  When a bridge round
proves the question and `MODE` is set,
`solve._grade_litbridge` asks the model about every invented rule the proof cites
(`litbridge_procedure.proofs_of` → `cited_hypothesis_ids`), one call per rule,
capped at `litbridge_grader.MAX_GRADED_RULES` (4) in citation order.  The grader
(`solver/litbridge_grader.py`, prompt
`prompts/dynamic_alignment/litbridge_grader_v1_system.txt`) sees the passage and
that one rule — never the answer, never the question: `litbridge_grader.passage_only`
drops every "?"-terminated sentence, so FOLIO's declarative conclusions
("Beethoven is not a conductor?") cannot be read as passage facts.  Two evidence
modes: `"stated"` — the rule must restate or be forced by the passage; `"any"` — the
rule must be true as general knowledge.  `normalise_mode` reads anything else, `None`
included, as `"stated"`.  One `FAIL` withdraws that
proof; a case whose graded proofs are all withdrawn keeps the initial attempt's answer,
with no new rule search and no further gk round.  The round record carries
`grading` (mode, per-rule verdict and reason, `withdrawn`), recorded also when
everything passes.  The call goes through the litbridge responder with role
`grader`.  Fixtures: `tools/test_litbridge_grader.py`.  Measured 2026-08-20
([mechanism experiments](../mechanisms/optional.md)).

## Related documentation

- [Graph representation](graph-representation.md)
- [Retries and abstraction code](../code/retries-and-abstraction.md)
