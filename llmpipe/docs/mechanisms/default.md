# Default mechanisms

Mechanisms enabled in an ordinary run, with the evidence for each.

The status terms and the evaluation sets are defined in the
[mechanism index](README.md).

## Current default mechanisms

### Davidson2: reversible compact event representation

**Mechanism.** Davidson2 recognizes a complete neo-Davidsonian event spine:

```text
activity(E), type(E,V), actor(E,A), target(E,T)
```

and replaces it internally with the compact atom `event(V,A,T,E)`. The fold is
attempted only when expanding the compact atom reconstructs the same signed
four-part event, modulo safe quantifier normalization. Missing actors or
targets, content events, ambiguous participants, and other non-round-tripping
forms are refused. Bidirectional representation clauses allow ordinary
axioms and later knowledge bases to consume either the compact atom or the
original event roles. A one-way relation adapter supports existing flat
relation consumers. Proofs may use the compact atom directly; representation
steps are labelled as conversions rather than background knowledge, and the
compact form has a direct English rendering.

**Experiments.** The decisive comparison used all 1,600 Core cases and all 203
FOLIO cases with Claude Sonnet 4.6, GPT-5.1, Gemini 2.5 Flash, and DeepSeek V4
Flash. Stage 1 and Stage 2 were identical between conditions; only the logical
representation changed. The legacy compact event mechanism lost 18, 25, 26,
and 43 Core cases for the four models. Davidson2 together with Existfold2 lost
zero cases in all eight dataset/model cells and gained seven correct
model-case answers. The Davidson2-specific gains were one Core/Gemini case and
three FOLIO cases across Claude and GPT; another mixed-representation Core
case was repaired through the compact-to-flat adapter.

On correct proofs shared with the standard representation, Davidson2 shortened
189--250 Core proofs per model and lengthened 36--40. The Core median proof
length fell from four derived steps to three. It folded roughly 556--563 Core
cases and 95--109 FOLIO cases per model, so the zero-loss result was not caused
by rare activation.

An interoperability suite separately checked both directions of the strict
definition, stock `axioms_std.js` consumers, a later knowledge base that both
produces and consumes event forms, negative events, incomplete spines,
participant swaps, and context mismatches. These tests found and repaired an
initially conditional reverse adapter and a scan-view sign defect before
default adoption.

**Decision.** Default on the unnamed canonical neo-Davidsonian theory. It is
suppressed inside the separate graph representation and when an explicit
legacy or abstract event base is requested. `-nodavidson2` disables it;
`-noproofshort2` disables both version-2 proof shorteners.

**Reason.** It has broad activation, a mechanically checkable equivalence
condition, substantial proof shortening, useful representation
interoperability, and no observed loss in the full paired experiment. That
experiment comprised 21,636 runs: 1,600 Core and 203 FOLIO cases, four models,
and three representation settings. Davidson2/Existfold2 lost no answer in any
of the eight dataset/model cells, while Davidson2 shortened 189--250 shared
Core proofs per model and contributed four identified gains. The old Davidson
mechanism lost 18--43 Core answers per model. The adapters remain necessary:
Davidson2 is an internal proof-search representation, not a demand that all
external knowledge bases be rewritten.

Provenance: full comparison audit (local archive: `memos/MEMO_2026_08_26_full_proofshortener_comparison_audit.md`),
interoperability audit (local archive: `memos/MEMO_2026_08_26_proofshort2_interop_audit.md`),
default adoption (local archive: `memos/MEMO_2026_08_26_safe_canonical_default_result.md`).

### Existfold2: narrow repeated existential-part summary

**Mechanism.** Existfold2 summarizes only the repeated pattern

```text
exists Y: class(Y,C) and has_part(X,Y)
```

for a class that occurs at least four times. It creates a compact, class-specific
summary and three compatibility clauses. It does not fold general possession,
does not use a generic schema across all classes, and preserves an explicit
witness form when the detailed representation is needed.

**Experiments.** It was tested in the same 21,636-run Core/FOLIO comparison as
Davidson2. It did not activate on Core. In FOLIO it activated in only a few
stories, but those cases isolated its effect: Claude cases 196--198 changed
from three standard errors or wrong statuses to the correct Unknown, False,
and True answers, with no observed loss. A separate repeated-`has legs`
fixture reduced 164 clauses to 14 while retaining the answer. Compatibility
tests verified compact-to-detailed and detailed-to-compact use by later
clauses.

**Decision.** Default together with Davidson2, subject to the unchanged narrow
pattern and threshold. It can be disabled independently with
`-noexistfold2`.

**Reason.** Activation is much narrower than Davidson2, but when it applies it
can remove a large Skolem cross-product and materially shorten the theory. The
21,636-run paired experiment found three isolated FOLIO/Claude gains and no
loss in any dataset/model cell; the repeated-legs fixture reduced 164 clauses
to 14 without changing the answer. The evidence does not justify lowering the
threshold or extending the mechanism to general `have`; those would be new
experiments.

Provenance: full comparison result (local archive: `memos/MEMO_2026_08_26_full_proofshortener_comparison_result.md`)
and audit (local archive: `memos/MEMO_2026_08_26_full_proofshortener_comparison_audit.md`).

### Structural Stage-1, Stage-2, and conversion repairs

**Mechanism.** A first family of August repairs corrected recurring structural
translation defects without asking an LLM to invent a new rule. The principal
repairs were:

- complete a missing tense only when another source unit explicitly establishes
  that tense, while excluding passive participles;
- keep an event participant and its modifier on the same bound object;
- preserve identity across a rule when Stage 1 identifies a repeated dependent
  or unique definite participant;
- unify repeated proper-name identifiers only when the mentions cannot denote
  two distinct entities in the same unit;
- ground a definite rule participant only when the discourse contains exactly
  one compatible entity;
- preserve and validate binders, rejecting a conclusion variable that remains
  unbound;
- prevent a question's requested category from being incorrectly injected as
  a premise type;
- package malformed generic questions safely, normalize supported comparative
  forms through a lexicon, and reject the one malformed comparison form that
  GK cannot read;
- prevent a noun-sense synonym from manufacturing an adjective property with
  the same spelling.

These repairs use Stage-1 identity, scope, grammatical role, and uniqueness
information. They are not word-specific bridge rules.

**Experiments.** Offline replay over eight new-model Core and FOLIO result
trees initially found 23 recovered answers and no repair-caused loss. Audit
found a question self-matching bug and raised the total to 26 recoveries. A
sequential old-model control then exposed three overbroad rules: a generic
question rewrite triggered by its own class, a category filter matched by a
question word rather than the actual goal atom, and common nouns capitalized
at sentence start being treated as proper names. Narrowing those rules retained
the gains and removed the attributable regressions. A separate reference-repair
cohort recovered 9 of 15 targeted cases and broke none; 1,354-case replay
showed 23 raw gains and seven raw losses, of which six reproduced with every
new repair off and the seventh was repaired through a more general definite
reference rule. A full 1,600-case Gemini Core check found zero attributable
Core regression.

The repairs also changed the bridge problem itself. On Multi-LogiEval 2 case
49 a reference repair solved the case without its proposed bridge. On EB2 case
9 the repair made the intended interface expressible, after which the reviewed
bridge was cited in a proof. This showed that bridge generation should not be
used to conceal a broken object identity.

**Decision.** Adopted structural conversion behavior. Narrow kill switches and
fixtures remain for regression diagnosis, but these are not ordinary
high-recall options.

**Reason.** The final rules are tied to explicit identity, scope, or clause
safety evidence and were refined against both newer and older translations.
They improve the theory before proof search rather than assert new background
knowledge. The rejected early variants are important negative evidence:
surface head equality, capitalization, or a question word alone is not enough
to merge entities or drop types. Quantitatively, the successive audits found
26 recoveries in eight Core/FOLIO result trees, recovered 9 of 15 targeted
reference cases without a break, and found zero attributable regression in a
full 1,600-case Gemini Core replay; the apparent losses in a 1,354-case replay
were traced to older behavior or repaired by the narrowed rules.

Provenance: programmatic fixes (local archive: `memos/MEMO_2026_08_04_programmatic_fixes_results.md`)
and parse/reference repairs (local archive: `memos/MEMO_2026_08_09_parse_repair_results.md`).

### Safe normalization and question-presence repairs

**Mechanism.** Several deterministic repairs were adopted because they restore
the intended representation rather than introduce a new reading:

- one shared recognizer distinguishes Stage-2 variables from world constants
  such as `W0`, preventing valid clauses or questions from being discarded as
  range-unsafe;
- the safe singularizer avoids forms such as `roses -> ros`, preserves words
  such as `bus` and `physics`, and applies suffix rules in a safe order;
- harmless leading, trailing, and repeated whitespace inside content tokens is
  trimmed;
- a Stage-1 sanity retry detects a question-ending source sentence that the
  parse omitted entirely.

**Experiments.** The lost-question check was motivated by 19 of 203 DeepSeek
FOLIO cases that ended with `Error: no question given`. The corrective retry
restored a question in all 19 and produced 14 correct answers; 15 already-correct
controls were unchanged. The variable and singularizer fixes were checked on
Core and FOLIO. The singularizer repair preserved 299/300 correct Core-100
model-runs and changed only a benign multi-answer ordering while repairing its
target case. Later fallback and full-stack runs included these fixes without a
new default-path regression.

**Decision.** Default correctness behavior, not optional abstraction.

**Reason.** Each repair has a narrow structural trigger and restores source
content that should already have been present. Unlike semantic abstraction,
it does not add a new inference relation. The large lost-question gain also
showed that mechanical translation failures should be counted before adding
more reasoning machinery: on 203 DeepSeek FOLIO cases the retry found all 19
omitted questions and returned 14 correct answers, while 15 correct controls
did not change. The singularizer check covered 300 Core-100 model-runs and
changed no correctness result.

Provenance: experiment overview, section 6 (local archive: `memos/MEMO_2026_08_23_experiments_overview.md`)
and abstraction adoption result (local archive: `memos/MEMO_2026_08_25_abstraction_adoption_result.md`).

### Normalization fallback

**Mechanism.** When the canonical theory returns Unknown, `fallback_norm`
reconverts the same Stage-1 and Stage-2 parse with a small collection of
case-local normalizations and question readings. It can align case variants,
hyphenation, safe singular/plural role values, list prepositions, and
comparative names; preserve a universal generic question; interpret explicitly
inclusive disjunction cues; and materialize a clearly appositive question
presupposition. It skips the GK call if the resulting clauses are identical to
the canonical clauses. It makes no LLM call.

**Experiments.** On FOLIO 203 with Gemini, GPT, and DeepSeek, the two fallback
mechanisms together added 15 correct model-case answers over their own front
door. On Multi-LogiEval 100 they added seven, and on a held-out Multi-LogiEval
sample one. In the later full retry-stage sequence, removing the fallbacks lost nine
FOLIO and eight Multi-LogiEval correct answers; no correct later-stage answer
was blocked by a fallback. Named normalization cases included `Estonian` versus
`estonian`, plural role fillers, inclusive `or`, and generic questions.

The earlier three-stage retry had produced six additional correct answers from a
third, generated-hypothesis stage, but it also produced wrong definite answers
on FOLIO and Multi-LogiEval Unknown controls. Removing that stage returned those
controls to Unknown. The surviving normalization behavior reproduced the first
two stages one for one.

**Decision.** Default first retry after an unresolved canonical proof.

**Reason.** It is cheap, deterministic, attributable, and cannot replace an
earlier canonical answer because it runs only after Unknown. Its changes are
mostly representational normalization rather than added world knowledge. Some
components were designed on FOLIO/Multi-LogiEval and gave little held-out gain,
so the stage should still be evaluated beyond those sets. On 609 FOLIO and 300
Multi-LogiEval model-case runs the two LLM-free fallbacks added 15 and seven
correct answers; removing them from the later stack lost nine and eight correct
answers respectively and blocked none of the later correct answers. That
measured benefit and low cost outweigh the present held-out limitation.

Provenance: fallback result (local archive: `memos/MEMO_2026_08_25_fallback_result.md`) and
fallback audit (local archive: `memos/MEMO_2026_08_25_fallback_audit.md`).

### Conditional-question fallback

**Mechanism.** If the previous attempts remain unresolved and the question is
conditional, `fallback_hyp` builds an isolated theory in which the antecedent
is assumed and the consequent is asked. It does not assert the antecedent in
the canonical theory. This gives a forward-chaining reading for questions whose
ordinary biconditional question wrapper makes the antecedent difficult to use.
It normally performs at most two GK calls and no LLM call.

**Experiments.** The mechanism recovered named FOLIO and Multi-LogiEval cases
that required reasoning from the question antecedent. Together with
`fallback_norm`, it contributed to the +15 combined FOLIO and +7 combined
Multi-LogiEval-100 gains described above. It also exposed two known
wrong-polarity cases: DeepSeek FOLIO 73 and held-out Multi-LogiEval 303. In
those cases the benchmark uses a vacuous-truth reading because the passage
refutes the antecedent, while the hypothetical reading derives the opposite
answer.

A preliminary refutation check attempted to suppress this failure. Across 300
Multi-LogiEval model-case runs, disabling the check changed no answer and
halved this fallback's GK calls from 126 to 63. The check could not prove the
antecedent false in the two motivating mistranslations, so it bought no safety.

**Decision.** Default after normalization fallback. The isolated construction
and attribution are retained; the expensive preliminary refutation check is
not relied upon as a safety result.

**Reason.** The mechanism recovers a distinct and recognizable question
shape at low cost, and running it only after Unknown avoids destroying a
canonical proof. Its residual risk is explicit: material-conditional and
hypothetical readings do not always match benchmark conventions. The stage is
therefore less conservative than normalization, but substantially safer than
an always-on hypothesis assertion. The 203-case FOLIO and two 100-case
Multi-LogiEval evaluations found useful conditional-question recoveries but
also two named wrong-polarity cases; a separate 300-model-case refutation-check
experiment halved GK calls from 126 to 63 without changing any answer or
catching those errors.

Provenance: fallback result (local archive: `memos/MEMO_2026_08_25_fallback_result.md`).

### Critic-guided retranslation

**Mechanism.** After deterministic fallbacks fail, one LLM call audits the
source text, Stage 1, Stage 2, and the unresolved outcome for translation
defects. It may identify a blocking omission, polarity error, quantifier or
scope problem, dropped condition, or representation mismatch. If it requests a
repair, Stage 2 is run once more with the previous translation and the findings.
The critic does not receive the accepted answer and does not directly write GK
clauses.

**Experiments.** In an early FOLIO comparison, the critic ran on 374
unresolved model-case runs, requested 115 retranslations, and produced 28
definite answers: 25 correct and 3 wrong. On definite-label cases its ratio was
25 correct to one wrong; on accepted-Unknown cases it produced two wrong
definite answers, about 2% of reruns. Placing it before graph retranslation
cost no case where a wrong critic answer displaced a graph answer that would
have been correct.

On Core challenging, Multi-LogiEval 100, EntailmentBank 100, and an 80-case
EB2 subset, the critic produced 55 correct and 5 wrong additions. In the later
canonical-base census over FOLIO 203, Multi-LogiEval 100, EB 100, and EB2 100,
the combined critic-plus-graph checkpoint added 111 correct answers and 8 wrong
answers for the two complete model runs, DeepSeek and Gemini. Of these, 44
correct and four wrong additions were attributed to critic retranslation.

The observed wrong cases were genuine translation changes rather than GK
errors: unsupported exclusivity, a changed negation scope, and a dropped
condition or quantifier. A prompt revision aimed at preserving hedges fixed its
target wording but did not fix the resulting answer, changed nothing on the
small Multi-LogiEval test, and lost four FOLIO/Gemini correct answers. It was
reverted.

**Decision.** Default after the two LLM-free fallbacks.

**Reason.** It has high measured precision, repairs cases different from those
repaired by graph translation, and changes an existing detailed translation
rather than inventing an arbitrary rule. It is not perfectly safe; the default
accepts the measured error rate because deterministic attempts have already
failed. In the 503-case canonical census with two complete model runs, the
critic contributed 44 correct and four wrong additions; in the earlier mixed
Core/MLE/EB/EB2 study it contributed 55 correct and five wrong. The later
119-addition acceptance-policy replay showed that stricter post-hoc checks
discarded far more correct than wrong answers.

Provenance: critic pipeline result (local archive: `memos/MEMO_2026_08_20_critic_in_pipeline_result.md`),
mixed stack result (local archive: `memos/MEMO_2026_08_24_mixed_default_stack_result.md`), and
canonical census (local archive: `memos/MEMO_2026_08_27_canonical_stack_census_closed.md`).

### Open-relation graph retranslation without invented bridges

**Mechanism.** The graph stage translates the source independently into a
simpler formula language built mainly from open subject--relation--object names.
It then compiles that theory and asks GK once. This is a second reading of the
source, not an implication generator: no new bridge between relation names is
added in this stage. The simpler vocabulary can align formulations that the
detailed representation separates, but it also cannot express every modal,
scope, or event distinction.

**Experiments.** In the direct graph-versus-literal-bridge comparison:

| Set | Graph answers | Correct | Wrong | Literal-bridge correct/wrong |
|---|---:|---:|---:|---:|
| Core 100 | 1 | 1 | 0 | 0 / 9 |
| Core challenging | 17 | 16 | 1 | 7 / 11 |
| FOLIO | 56 | 48 | 8 | 37 / 25 |
| EB + EB2 small cohorts | 2 | 2 | 0 | 17 / 4 |
| Multi-LogiEval 19 | 3 | 1 | 2 | 4 / 3 |

Thus graph retranslation was markedly safer than literal bridges on Core and
FOLIO, while plain graph retranslation did not supply the missing background
knowledge needed by EntailmentBank.

In the mixed stack, graph retranslation added 33 correct and 3 wrong answers
after the critic across Core challenging, Multi-LogiEval, EB, and EB2. In the
later canonical-base census, graph retranslation accounted for 67 correct and
four wrong additions. The four wrong graph additions were traced to information
the graph representation omitted: modality, negation scope, or a contested
open-name reading.

**Decision.** Default after critic retranslation. The graph compiler remains
separate from the canonical Davidson2/Existfold2 representation.

**Reason.** It is complementary to the critic and substantially more precise
than unrestricted implication generation on closed-passage material. Its
coarseness is useful when the detailed translation chose incompatible shapes,
but the same coarseness is the source of its known errors. Keeping it as a
separate late attempt preserves the canonical result and makes its provenance
visible. In the canonical census it added 67 correct and four wrong answers;
in the direct comparison it returned 48 correct and eight wrong FOLIO answers
and 16 correct and one wrong Core-challenging answer, while literal bridges
were materially less precise on those sets.

Provenance: graph versus literal bridge (local archive: `memos/MEMO_2026_08_20_graph_vs_litbridge_result.md`),
mixed stack (local archive: `memos/MEMO_2026_08_24_mixed_default_stack_result.md`), and
canonical census (local archive: `memos/MEMO_2026_08_27_canonical_stack_census_closed.md`).

#### Implemented graph-retranslation safety checks

These are narrow correctness checks around graph retranslation, not additional
abstraction mechanisms. They matter experimentally because a result obtained
after adding them is not directly comparable with an older graph run that
accepted the corresponding malformed or circular proof.

**Logical-operator shape validation.** The open-graph validator checks that
every content atom has the required three-item form. It also requires the fixed
shapes of the logical operators, including `["implies", A, B]`,
`["forall", X, A]`, `["exists", X, A]`, `["not", A]` and `["normally", A]`.
`graph_stage2.check_operator_arity` performs the check and
`graph_stage2.OPERATOR_ARITY` holds the shapes. A malformed operator goes to
the single corrective translation retry the graph translator already provides.
If it is still malformed, `graph_p0` stops the stage before compilation and
before GK, recording `graph_translation_structurally_invalid`.

This check addresses a concrete compilation failure rather than judging the
meaning of a well-formed formula. In `gpt/ebn-0016`, the graph output put the
consequent outside a malformed `implies` nested in a four-item `forall`. The
compiler consequently emitted `isa(inherited_characteristic, X)` without its
antecedent and GK returned a wrong definite answer. An offline scan of the
1,877 case-model runs in the wider balanced-default evaluation found 12 graph
translations with malformed fixed-arity operators. Eleven already remained
unresolved; `ebn-0016` was the only one that produced a definite graph answer.

Across the earlier 119 stored additions, the check also identifies one FOLIO
178 translation that matched the accepted answer but did not provide a valid
proof. It encoded `normally` with two formula arguments, after which the
compiler retained “won the most medals” while losing the required location.
The corrective retry repairs this form when it can; when it cannot, the stage
abstains rather than keep an answer obtained after dropping a condition.

**Question-only graph-proof refusal.** After GK returns a graph answer, the
pipeline inspects the proof's cited units. If every substantive source is the
Stage-1 query unit, and the proof uses no passage unit, declared knowledge
clause or substantive axiom, the answer is not used and the stage records
`question_only_graph_proof`. Artificial question goals and
representation-conversion clauses do not count as independent support.
`graph_p0.question_clause_names` identifies question units from the Stage-1
`type: query` record rather than only from clause annotations, because a
generated question clause can lose its `@sourcetype` field.

This check found one case among the 85 additions in the wider evaluation:
`gpt/ebn-0031`. Its six-step proof cited only the question unit; existential
witness clauses generated from the question supplied the same facts that the
question required. The check rejected that wrong answer and no correct answer.
It found no occurrence among the earlier 119 additions.

**Decision.** Both are graph-stage safety checks, implemented 2026-08-28 in
`solver/graph_stage2.py` and `solver/graph_p0.py`. They require no extra LLM or
GK call during a successful ordinary run. Only malformed graph
output uses the corrective retry that the graph translator already provides.
They are deliberately narrower than the optional post-retranslation acceptance
policies, which rejected many correct answers along with wrong ones.

Provenance: wider balanced-default evaluation (local archive: `memos/MEMO_2026_08_27_wider_balanced_default_result.md`)
and the subsequent offline audit of its 85 additions and the earlier
119-addition acceptance-policy corpus. The production implementation and replay
are described in
the graph structural-safety repair memo (local archive: `memos/MEMO_2026_08_28_graph_structural_safety_repairs.md`).
The replay found exactly the two wrong additions targeted in the wider run and
affected none of its 73 answer-matching additions. In the earlier 119-addition
corpus it found no question-only proof and refused one answer-matching but
structurally invalid proof whose malformed `normally` operator had discarded a
location condition.

### Ordered execution, model identity, time limits, and attribution

**Mechanism.** One configuration table defines the stage order and the three
named retry configurations. The first definite answer stops all later stages;
errors, timeouts, empty results, and Unknown remain unresolved. Every LLM role
must use the selected model, including cache hits. One cooperative per-call
deadline covers provider attempts, correction retries, and backoff for every
translation and abstraction stage, but not GK. Records separate whole-case
cost from the final attempt's per-stage cost and attribute every GK call to its
stage.

**Experiments.** The integration replay used 26 DeepSeek/Gemini cases from the
canonical census. Explicit `balanced` and the no-option default reproduced all
answers, stages, translation hashes, clause hashes, proof sources, and 57 GK
calls with zero live LLM calls. Option resolution agreed in both entry points on
55 command lines. Earlier experiments had exposed several operational defects:
an `Error: no question given` string was once treated as a definite answer;
stack-stage calls once escaped the timeout; one command-line initial attempt
resolved `-pipeline` differently; and nested reruns hid GK calls from their
true stage. Each received a production-path regression test.

**Decision.** Default infrastructure for all pipeline configurations.

**Reason.** The measured contribution of a retry stage is meaningless unless
the same model is used end to end, later stages cannot replace earlier answers,
errors cannot masquerade as answers, and costs are assigned to the stage that
incurred them. These controls do not improve reasoning directly, but they make
the mechanism comparisons reproducible and prevent silent operational
failures. The production-path replay covered 26 cases and 57 GK calls with no
answer, stage, translation-hash, clause-hash, proof-source, or attribution
difference; the two entry points also agreed on all 55 tested option lines.

Provenance: coherent stack result (local archive: `memos/MEMO_2026_08_27_coherent_retry_stack_result.md`),
repairs (local archive: `memos/MEMO_2026_08_27_coherent_retry_stack_repairs.md`), and
default adoption (local archive: `memos/MEMO_2026_08_27_balanced_default_adoption.md`).

### Uniform proof rendering for later-stage answers

**Mechanism.** An answer found by graph retranslation or graph bridges now
passes through the same proof processor as a canonical answer. Open relation
names receive a controlled English rendering; source sentences, proof steps,
confidence, invented rules, wording variants, and representation conversions
are labelled. The case record contains one ordered stage list, while detailed
output uses the ordinary Stage-2, clause, prover-input, and prover-result
blocks. Davidson2 and Existfold2 compact terms likewise have direct English
renderings, and their adapters are labelled as representation conversion
rather than knowledge.

**Experiments.** The graph-render implementation replayed 2,127 case runs with
zero live LLM calls and added four focused record tests. Named FOLIO proofs
were checked line by line, including a strict True proof and a hedged False
proof. A graph-bridge case showed its invented rule under “Added rules” with a
readable formal meaning. Tests also caught an overgeneral rendering rule:
prepositions such as `on` need a copula, while an open name such as
`works_for` must not become “is works for.” The compact-event comparison and
interoperability audits separately verified that compact atoms may appear in
formal and English proofs without exposing raw witness terms.

**Decision.** Adopted presentation and recording behavior.

**Reason.** A later-stage answer is not auditable if it lacks the proof and
provenance available for the initial attempt. Uniform output also prevents graph or
compact representations from appearing as unexplained background axioms. The
renderer does not change the clauses or answer. This was checked by replaying
2,127 stored case runs with zero live LLM calls, plus focused strict, hedged,
graph-bridge, and compact-representation proof fixtures.

Provenance: graph rendering result (local archive: `memos/MEMO_2026_08_26_graph_render_result.md`)
and proof-shortener audit (local archive: `memos/MEMO_2026_08_26_full_proofshortener_comparison_audit.md`).

## Related documentation

- [Mechanism index](README.md)
- [Optional](optional.md)
- [Experimental](experimental.md)
- [Superseded](superseded.md)
- [Lessons](lessons.md)
