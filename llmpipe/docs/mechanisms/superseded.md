# Superseded mechanisms

Mechanisms rejected, removed or replaced, and why. The bridge-construction
research, the retry and normalization experiments, and the graph variants
that were not adopted.

## Superseded bridge-construction research

### Template/operator-based dynamic bridge construction

**Mechanism.** The first August bridge system extracted Stage-2 occurrences,
enumerated candidate rules from a library of structural operators, asked LLMs
to select or judge them, classified each candidate along semantic, passage,
attachment, direction, and provenance dimensions, and submitted selected
rules to GK. Operator families included relation reversal, category membership
to type, event-role projections, guarded variants, and other representation
connections.

**Experiments and lessons.** The experiments were initially small because they
were diagnosing the construction boundary.

- A seven-case selector comparison tested choosing from code-enumerated
  candidate interfaces against asking the model to construct pairs directly
  from producer and consumer occurrences. The enumerated configuration found 6/7 under
  strict formula-family scoring and 7/7 by content label; the direct configuration found
  4/7 and 5/7 and produced the only mechanically invalid self-pair. Candidate
  enumeration was therefore retained before model prioritization.
- A provenance audit found that 18 printed formulas represented 96 distinct
  derivation paths. Deduplicating by printed text had hidden risky paths and
  falsely attributed model choices. The repair retained every path and
  canonicalized only bound-variable names.
- A scalar admission class collapsed independent judgments and even made one
  desirable class unreachable. Replacing it with explicit semantic, passage,
  attachment, direction, variant, and submission fields made the records
  interpretable but did not by itself predict proof success.
- A paired direction judge correctly kept one-way relations such as
  `part of -> in` while rejecting their converses, and preserved genuinely
  equivalent paraphrases. It also showed that direction judgments could not be
  safely copied to guarded variants that had not been assessed.
- A transport smoke test submitted five admitted formulas and obtained three
  bridge-citing answers, showing that the compilation boundary and archive
  exclusion worked. The first unattended five-case end-to-end diagnostic then
  submitted 13 candidate theories and found zero proofs. The failures were
  traced to an interface absent from the candidate list, a useful interface
  cut by selection, an unavailable operator, and mechanical refusals—not to a
  GK malfunction.
- Selector prompts repaired hard enumeration caps. On EB2-0020 the exact
  reviewed rule reached GK after selection, but still produced no proof. A
  missing membership-to-type connection was also required. This distinguished
  candidate exposure from proof sufficiency.
- A combined submission over several candidate rules found an EB2-0020 proof,
  but the first proof used three false rules. Excluding one cited rule exposed a
  defensible three-rule proof. This led directly to the later literal-bridge
  minimization and exclusion procedure.
- The reserved five-case confirmation produced no proof. In one case 108
  relevant formulas were generated and none entered the submitted set because
  one operator family dominated the selection rounds; two cases had no matching
  rule anywhere. The system was still measuring candidate-family and selector
  design rather than a stable end-to-end abstraction mechanism.

**Decision.** Superseded by the literal-unifier bridge mechanism and the
open-relation graph mechanism. Some operator implementations and tests may
remain, but the old admission/selector pipeline is not a default route.

**Reason.** The work established important invariants—retain all provenance,
separate independent judgments, range-check rules, compare both directions,
submit several bridges together, minimize proofs, and search beyond the first
proof. Its own candidate space and selector stages were too elaborate and too
fragile for broad use. The successor mechanisms use simpler observable inputs:
actual GK literals or open graph names. The empirical progression supports the
replacement: a five-case unattended diagnostic found no proof, a later combined
submission found one proof first through false rules and then through a
defensible alternative, and the reserved five-case confirmation again found no
proof despite generating as many as 108 relevant formulas in one case.

Provenance: provenance admission (local archive: `memos/MEMO_2026_08_11_provenance_admission.md`),
six-axis admission (local archive: `memos/MEMO_2026_08_11_six_axis_admission.md`),
paired direction (local archive: `memos/MEMO_2026_08_11_paired_direction.md`),
alternative proof result (local archive: `memos/MEMO_2026_08_11_pooled_v2.md`), and
reserved confirmation (local archive: `memos/MEMO_2026_08_11_reserved_confirmation.md`).

### Scalar admission and mechanical semantic relevance

**Mechanism.** Early variants attempted to assign one ordered class to a rule
by combining semantic plausibility, passage support, attachment reliability,
and later direction. Another proposed rule tried to decide mechanically
whether a guard was relevant by asking whether its variable appeared in the
conclusion.

**Experiments.** On the 18-formula admission cohort, the scalar policy collapsed
eight distinct axis profiles into three broad classes and made passage support
function as an unintended eligibility requirement. The mechanical guard rule
failed on the same cohort:
`animal(Y)` is essential to the meaning of `animal lover(X)` even though `Y`
does not occur in the conclusion, while a passage-local `pet owner(X)` guard
shares the conclusion variable but may be the wrong restriction.

**Decision.** Removed as decision logic. Guard shape and provenance may be
recorded, but relevance is not declared mechanically; independent axes remain
independent.

**Reason.** The proposed summaries discarded exactly the distinctions needed
to diagnose a bridge. In the 18-formula test, eight distinct evidence profiles
became only three scalar outcomes, and the proposed variable-overlap rule
misclassified both the essential `animal(Y)` restriction and the less faithful
`pet owner(X)` restriction. Variable overlap is a structural fact, not a
semantic relevance judgment.

### Critic--editor--verifier bridge repair chain

**Mechanism.** A selected representation mismatch was passed through three
LLM roles: a critic identified the real interface, an editor rewrote or added a
Stage-2 package, deterministic checks validated the package, and a verifier
judged whether the edit matched the source.

**Experiments.** On seven frozen development cases, the selector included the
intended interface in all seven and the critic named it in six. The critic also
rejected all 22 irrelevant selections. The editor emitted readable packages in
five of seven cases; deterministic structural checks accepted all five. The
verifier accepted only one, and direct audit found correct logical strength in
only two of seven edits. Failures included repeated malformed JSON, strict
rules where a defeasible bridge was intended, incorrect quantifier scope, a
question rewrite where a bridge was requested, and verifier explanations that
misread the formula.

**Decision.** Superseded as an end-to-end repair route. The useful critic idea
survives in critic-guided retranslation; deterministic construction and
validation survive in later bridge compilers.

**Reason.** The experiment located the mismatch well but asked LLMs to perform
too many fragile transformations: JSON generation, quantifier placement,
logical strength, and formal verification. Later mechanisms keep the model's
task smaller and let code own clause construction. On seven frozen cases the
critic found six intended interfaces and rejected 22 irrelevant selections,
but direct audit found correct logical strength in only two edited packages and
the verifier accepted only one.

Provenance: alignment-chain result (local archive: `memos/MEMO_2026_08_09_alignment_chain_result.md`).

## Superseded or removed retry and normalization experiments

### Three-stage question retry

**Mechanism.** The old `qretry` procedure reconverted the same parse after
Unknown in three cumulative stages: deterministic conversion repairs,
alternative question readings, and generated hypotheses. It also exposed many
small converter and policy flags.

**Experiments.** On the design sets it produced sizeable gains: FOLIO rose from
127/127/123 to 140/135/128 for GPT/Gemini/DeepSeek; Multi-LogiEval 100 gained
4/3/1. On Core, four of 1,323 answers changed, all Unknown to correct. On the
one held-out Multi-LogiEval set containing the relevant triggers, however, it
added zero correct answers and one wrong answer across 300 model-case runs.
ProofWriter and ProntoQA were uninformative because they contained none of the
question patterns that triggered the retry.

The third generated-hypothesis stage caused the important safety losses. After
it was removed, two wrong definite answers on Unknown controls disappeared,
while six correct answers that only the generated bridge had supplied were
also lost.

**Decision.** Superseded and deleted. Its useful deterministic behavior is now
split into `fallback_norm` and `fallback_hyp`; generated hypotheses are left to
the separately controlled bridge mechanisms.

**Reason.** The split gives each later answer a clear cause, avoids enabling a
large bundle of unrelated transformations, and removes the unsafe hypothesis
stage. It also permits an identical-conversion check before spending a GK call.
Across 609 FOLIO, 300 Multi-LogiEval design, 300 held-out Multi-LogiEval, and
1,323 Core model-case runs, the safe stages produced useful design-set gains and
four correct Core changes, while the generated stage caused two wrong definite
answers on Unknown controls; the held-out set gained nothing.

Provenance: abstraction adoption result (local archive: `memos/MEMO_2026_08_25_abstraction_adoption_result.md`)
and fallback result (local archive: `memos/MEMO_2026_08_25_fallback_result.md`).

### Small normalization, bridge, and search flags with no measured answer benefit

Nine individually switchable mechanisms were implemented and measured on top
of the old retry procedure. They did the following:

- **Gerund normalization (`gerundnorm`)** reduced a gerundive event or property
  name to the corresponding base verb when both forms occurred in the case,
  so `jumping(X)` could unify with `jump(X)`. It changed 31 FOLIO and ten
  Multi-LogiEval model-case theories but changed no answer.
- **Variable-blind set keys (`setkeyvarblind`)** computed the identity of a
  `$setof` term modulo the spelling of its bound variables. Thus two set terms
  with the same body, restrictions, and constants would not remain different
  merely because one translator called the bound member `X` and another called
  it `Y`. It changed 12 FOLIO and three Multi-LogiEval theories and no answer.
- **Agentive compound bridges (`agentivebridge`)** tried to connect a class
  expressed by an agentive noun with its underlying relation—for example,
  `animal lover(X)` with a representation of `X loves animals`. The condition
  on the object class was retained; this was not the intersective and incorrect
  reading “X is an animal and a lover.” It changed 26 FOLIO and five
  Multi-LogiEval theories and no answer.
- **Event-role filler subsumption (`eventpropsub`)** used an in-case type link
  for a role filler. For example, if an event role was filled by something
  typed as a `friend`, a rule whose corresponding role required a `person`
  could use an available `friend -> person` relation instead of failing because
  the two role labels differed. It changed 12 FOLIO and four Multi-LogiEval
  theories and no answer.
- **Possessive-to-have bridges (`possessivehave`)** connected a possessive or
  part-like Stage-2 structure to the pipeline's ordinary `have(owner,item)`
  relation when the owner and possessed entity were already identified in the
  case. It was intended for mismatches such as “X's Y” versus “X has Y.” It
  changed 37 FOLIO and six Multi-LogiEval theories and no answer.
- **Agent-nominal typing (`agentnominal`)** tried to recover an actor class from
  a possessive action nominal—for example, interpreting “Windy's shooting” as
  evidence that Windy is a shooter when a rule explicitly required a shooter.
  It changed 21 FOLIO and four Multi-LogiEval theories and no answer.
- **Question unique-name exemption (`qunaexempt`)** withheld selected
  unique-name or forced-distinctness assumptions between a question term and a
  compatible passage witness. Its purpose was to leave equality or coreference
  possible when the question and passage used different identifiers, not to
  assert that the identifiers were equal. It changed 19 FOLIO and two
  Multi-LogiEval theories and no answer.
- **Alternative GK strategy (`strategyretry`)** did not change the theory. It
  reran an unresolved query with a stronger query-focused search strategy to
  recover a proof missed by the ordinary search order. It ran on 12 FOLIO
  model-cases, adding one correct answer and two wrong-polarity answers; it
  added nothing on Multi-LogiEval.
- **No-time policy (`qnotime`)** removed tense-valued `has_time` atoms from
  event representations during the question-side retry so otherwise matching
  event content could unify. No useful trigger occurred in either evaluation
  set, and no answer changed.

Each mechanism was compared separately on FOLIO 203 and Multi-LogiEval 100
with GPT-5.1, Gemini 2.5 Flash, and DeepSeek V4 Flash: 609 and 300 model-case
runs per mechanism. The activation counts above are model-case theories whose
submitted clauses actually differed from the baseline, not merely texts that
matched a preliminary trigger. Two harness defects initially made some runs
byte-identical or hid question demand; both were fixed before the reported
measurement.

**Decision.** Removed from active code paths.

**Reason.** A mechanism that changes many theories but no answer adds
complexity and a future regression surface without evidence of benefit. The
seven conversion mechanisms collectively produced 192 mechanism-by-model-case
activations without changing one answer in the 909 comparisons per run. The
no-time policy never found a useful trigger. The query-focused strategy retry
was worse: its one correct FOLIO addition came with two
wrong-polarity additions and no Multi-LogiEval gain.

Provenance: abstraction-adoption result, item F (local archive: `memos/MEMO_2026_08_25_abstraction_adoption_result.md`)
and removal record (local archive: `memos/MEMO_2026_08_25_fallback_result.md`).

### Confidence, witness, modality, and time policies

**Mechanisms and evidence.** Four proof or conversion policies were measured
separately:

- `strictconf`, which removed sub-1 confidence annotations from selected
  sentence clauses, added five combined FOLIO and three Multi-LogiEval correct
  answers with no measured loss in its design experiment;
- `modalfold`, which preserved a distinction between `can V` and `V`, added
  four FOLIO correct answers but lost seven Multi-LogiEval answers because the
  two benchmarks apply different conventions;
- `qnowitness`, which rejected answers depending on injected population
  witnesses, lost two FOLIO answers and gained none;
- `qnotime` changed no answer.

The apparent `qnowitness` effect was initially much larger because the first
implementation rejected any proof citing a population clause, even when the
witness did not support the query. Structural term inspection corrected the
measurement.

**Decision.** These standalone flags were removed when `qretry` was replaced.
`modalfold`, witness filtering, and time stripping are not defaults.
`strictconf` had a positive design-set result but was not independently
promoted before the old framework was deleted.

**Reason.** The policies either had no benefit, lost more than they gained, or
encoded benchmark-dependent semantics that cannot be selected safely from an
unknown input. The positive `strictconf` result remains a useful future
hypothesis, but it is not evidence that the current default silently contains
that policy. The separate configurations covered 609 FOLIO and 300 Multi-LogiEval
model-case runs: `modalfold` gained four on FOLIO but lost seven on MLE,
`qnowitness` lost two and gained none, `qnotime` changed nothing, and
`strictconf` gained five and three only on these design sets.

Provenance: abstraction-adoption result, policy configurations (local archive: `memos/MEMO_2026_08_25_abstraction_adoption_result.md`).

### Always-on question reinterpretation

**Mechanism.** Always-on variants rewrote exclusive disjunction questions as
inclusive, asserted conditional antecedents, or asserted appositive types
before the first GK call.

**Experiments.** They sometimes repaired a wrong definite answer that an
Unknown-only fallback can never revisit. On Multi-LogiEval 100, the combined
question transforms raised accuracy to 47/45/39 for GPT/Gemini/DeepSeek and
reduced several wrong definite answers. On FOLIO, however, asserting an
antecedent that the premises refuted destroyed correct material-conditional
proofs, and appositive assertions similarly removed refutation paths. Modal
folding repaired a FOLIO distinction while breaking Multi-LogiEval cases that
treated capability as sufficient.

**Decision.** Not used globally. Safer forms are attempted only after Unknown
inside the two fallback stages.

**Reason.** Reinterpreting a question before the canonical attempt can destroy
a proof that depends on the original scope or on refuting the antecedent. The
same transformation after Unknown cannot lose an earlier answer. This
experiment is the main empirical basis for the pipeline's ordered-retry
architecture. The comparison covered 203 FOLIO and 100 Multi-LogiEval cases
with three models (609 and 300 model-case runs): always-on question transforms
improved several MLE answers but destroyed FOLIO proofs through asserted
antecedents or appositions, whereas the Unknown-only fallbacks preserved those
earlier answers.

## Graph-mechanism variants not adopted

### Candidate-source expansion and holistic proposals

**Mechanism.** Graph bridge candidates were obtained from a narrow proof
frontier, exhaustive same-kind name pairs, bounded composition paths, or a
holistic LLM proposal over the case.

**Experiments.** The main candidate-source comparison used the 165-case graph
pilot over FOLIO, Core, EntailmentBank, and Multi-LogiEval, with four stored
translation runs. Frontier-only judged 1,913 pairs and reached 37 cited
credible proofs; adding exhaustive pairs judged 3,031 and reached 38; adding
composition and a holistic call judged 3,322 and reached 40, at 1.85 times the
frontier-only LLM cost. All three behaved identically on the twelve named
design probes. In the later small EB/EB2 comparison, widening the sources moved
from eight correct/zero wrong to ten correct/one wrong, but one model/set cell
lost an answer. Holistic and `RELATED`-based variants sometimes worsened
precision. Enumeration was already complete on small relation inventories;
the real question was which pairs to judge within the call budget.

**Decision.** Keep bounded source options for research, but do not treat more
candidates as automatically better. The default graph retranslation adds no
bridges; optional graph-bridge behavior uses its measured bounded selection.

**Reason.** Candidate count is not the main limiting factor once common pairs are
covered. Wider candidate sets consume judgment calls and can displace a useful
pair under a fixed limit. In the measured EB/EB2 comparison, widening the
candidate sources moved the result from eight correct/zero wrong to ten
correct/one wrong, while also losing one answer in a model/set cell; the wider
set was therefore not a monotone improvement.

### Evidence-tag and cross-arm agreement policies

**Mechanism.** Proposed bridge filters required a relation to be stated in the
passage, supported by particular retrieval evidence, or independently proposed
by multiple candidate sources or models.

**Experiments.** On the 165-case graph pilot, a bridge tagged `STATED` initially
gave seven correct and five wrong proof cases; audit found that all of those
bridges actually joined different sentences, so the corrected tag classified
them as `BACKGROUND`. The remaining lexical class contained one correct and
one wrong proof. Cross-arm agreement did not discriminate either: cases with
the same credible answer in at least two stored translation runs were 20
correct/10 wrong, compared with 23/13 when only one run produced it. These were
not independent-model votes—the same Sonnet model handled the graph roles in
all four runs—but they directly refuted agreement as a useful filter in that
experiment. Correct open-world bridges also often expressed ordinary
background knowledge rather than a passage statement.

**Decision.** Not used as a default acceptance rule. Evidence remains recorded
for analysis.

**Reason.** Provenance describes why a candidate was considered; it does not
establish that its implication is valid or useful in the direction required by
the proof. In the 165-case pilot, the `STATED` class was 7/5 before its faulty
definition was corrected, the lexical class was 1/1, and cross-arm agreement
was 20/10 versus 23/13 without agreement. None supplied a useful answer-quality
separation.

### Typed-filler and role-shape projections considered but not built

**Mechanism.** Two proposed deterministic projections were intended to connect
canonical representations before invoking more expensive LLM stages. A
typed-filler projection would replace a class-like relation filler with an
entity already typed as that class. A role-shape projection would connect a
complete reified event role to a flat relation carrying the same verb and
participants. Both proposals required one consistent unifier, exact sign and
argument order, and definite in-case suppliers.

**Experiments.** An initial permissive census over 674 model-specific records
unresolved after critic and graph retranslation reported 72 typed-filler and
two role-shape opportunities. Audit found five matcher defects: it had not
actually unified all structures, allowed rule bodies and question literals to
act as producers, failed to standardize variables from different clauses
apart, allowed duplicate clause names to create self-suppliers, and inverted a
demand sign. Under the corrected definition, only 12 records had a typed
filler with both a definite producer and a definite supplier. Role-shape fell
to zero because its apparent producers were variable-headed adapter rules, not
concrete events.

**Decision.** Not implemented as pipeline stages.

**Reason.** Twelve opportunities in 674 residual records is an opportunity
rate of 1.8%, not a proof yield. The concurrent abstract retry had only 74%
precision, so the likely gain was single digits across more than a thousand
model-case runs. This did not justify adding a general inference path to every
relation filler. The corrected negative result also illustrates why an
opportunity counter must run real unification and exclude question assumptions
and self-matches.

Provenance: canonical census (local archive: `memos/MEMO_2026_08_27_canonical_stack_census_closed.md`).

## Related documentation

- [Mechanism index](README.md)
- [Default](default.md)
- [Optional](optional.md)
- [Experimental](experimental.md)
- [Lessons](lessons.md)
