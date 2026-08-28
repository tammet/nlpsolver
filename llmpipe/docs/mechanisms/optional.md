# Optional mechanisms

Higher-recall and specialist mechanisms kept in the pipeline but not
enabled by default.

## Optional high-recall mechanisms retained in the pipeline

### Graph bridges

**Mechanism.** After open-relation graph retranslation still returns Unknown,
the graph-bridge layer proposes directional implications or exclusions between
open relation names. Candidate pairs are generated mechanically, an LLM judges
their direction, the accepted implications are added to the graph theory, and
GK is run on that explicit theory. Proofs retain the exact bridge clauses they
used. This is enabled by `-graphbridge` or `-pipeline high-recall`.

**Experiments.** On the small EB and EB2 cohorts, the default candidate source
produced eight correct and zero wrong bridge-layer answers. Widening to three
candidate sources produced ten correct and one wrong. Literal bridges produced
17 correct and four wrong on the same material, with only two cases shared,
showing both lower graph-bridge recall and substantial complementarity.

In the later mixed-stack comparison, graph bridges were tested after critic
and graph retranslation on 1,138 paired model-case runs:

| Material | Bridge-layer correct | Wrong | Net effect |
|---|---:|---:|---:|
| Core challenging | 0 | 1 | -1 |
| Multi-LogiEval 100 | 6 | 0 | +5 |
| EntailmentBank 100 | 14 | 1 | +14 |
| EB2 partial | 2 | 0 | +2 |
| **Total** | **22** | **2** | **+20** |

The layer's value was therefore concentrated in open-world science material;
its only Core answer was wrong. Candidate-source experiments also showed that
larger enumeration was not uniformly better: one EB2/Gemini answer was lost
when the candidate set was widened.

**Decision.** Retained as the `high-recall` configuration, off in the balanced
default.

**Reason.** The mechanism provides a clear recall gain when ordinary
background knowledge is genuinely missing, but the pipeline does not know
that a new input belongs to such a set. On closed-world material, an invented
bridge changes a correct abstention into a false definite answer. The current
default therefore stops before this stage; users may explicitly choose higher
recall and accept the measured additional risk. Across 1,138 mixed model-case
runs after critic and graph retranslation, graph bridges added 22 correct and
two wrong answers: EB/EB2 and Multi-LogiEval supplied all 22 gains, while the
only Core answer was wrong.

Provenance: route precision and correction (local archive: `memos/MEMO_2026_08_23_experiments_overview.md`)
and mixed stack result (local archive: `memos/MEMO_2026_08_24_mixed_default_stack_result.md`).

### Literal bridges over canonical clause atoms

**Mechanism.** The literal-bridge route examines the actual clauses sent to
GK. It identifies content atoms from the question and atoms with few
opposite-sign unifiers, displays those atoms in a compact notation, and asks an
LLM for a small number of defeasible implication rules. Rules are parsed and
range-checked, compiled one at a time with the ordinary bridge compiler, and
submitted to GK at full clause confidence. Uncertainty is applied only after
proof search; a deliberately low clause confidence must not prevent GK from
using the rule. If the first submission finds no proof, a second call asks for
different rules and the procedure runs separate first-call-only,
second-call-only, and combined submissions. If the first submission already
proves an answer, the ordinary procedure skips the second LLM call; an
experimental option can still request independent alternatives. In either
case it minimizes cited bridge sets by deletion replay and can exclude a cited
bridge to look for a distinct proof among rules already generated. It is
enabled by `-litbridge` or `stack-open`.

**Development experiments.** Successive versions fixed genuine structural
problems: standardizing variables apart during unification, preserving sign,
showing exact compilable atom templates, retaining nested event and set terms,
using query position and unifier scarcity, compiling rules separately so one
bad rule cannot destroy a case, and carrying negative conclusions through the
parser and compiler. Coverage rose from 5 to 9 and then 22 proof cases on the
50-case pilot. Multi-bridge proofs first appeared, including a three-bridge
EntailmentBank proof whose every deletion destroyed the answer.

The exact-template compiler was later replayed over 4,875 archived rules from
eight model runs. Of these, 4,358 compiled both before and after; 238 rules that
the old isolated conversion had wrongly refused now compiled; 203 formerly
compiled rules were correctly refused for an undisplayed constant, an
unsupported nested term, or an exact tautology; and 76 remained refused. This
change is important because it makes the prompt contract real: a rule composed
from displayed atoms is assembled from the retained literal templates rather
than translated again into a possibly different shape. The same revision added
one bounded correction for a missing or unusable translated question; if that
fails, the case is recorded as a translation failure and makes no bridge or
dynamic GK call.

The most instructive early case was EB2-0020. A combined bridge submission
first found a proof using three counterexampled rules. Excluding one bridge
revealed a different, defensible three-rule proof. This established two design
points: GK must be allowed to combine several bridges in one submitted theory,
and the first proof is not necessarily the best proof. Deletion minimization
and exclusion search are therefore retained.

**Wider experiments.** With the broad Sonnet prompt on the 165-case cohort,
the route produced proofs on 76 cases and 130 minimal bridge sets. All 46
EntailmentBank sets agreed with the accepted answer, but 11 of 20 FOLIO
accepted-Unknown controls received True proofs and 3 of 20 accepted-False
controls received True proofs. Only 40 of 164 used bridges were reasonable as
written.

A later soundness-first prompt required an English meaning and made `NO_RULE`
a normal response. It reduced proof cases from 76 to 44 and minimal sets from
130 to 63, but improved agreement from 58.5% to 76%; definite answers on
accepted-Unknown controls fell from 19 sets to two, and True proofs on
accepted-False controls fell from five to zero. The cost was real:
EntailmentBank agreeing sets fell from 46 to 32 and Multi-LogiEval from 12 to
five.

The same prompt changed the second call most strongly. Proof-used rules from
the no-proof call fell from 69 in the broad run to eight; 34 of 92 such calls
returned `NO_RULE`. Across the later eight model and version runs, the second call
first recovered only zero to seven correct cases per run, compared with four
to 22 from the first call. This is why the current procedure does not make a
second generation call after the first submission already proves something,
unless the explicit alternative-proof diagnostic is requested.

Four-model runs showed large model dependence. Under the same bridge prompt,
Claude, GPT-5.1, Gemini 2.5, and DeepSeek produced bridge-dependent proofs on
44, 6, 21, and 39 cases respectively. GPT mostly returned `NO_RULE`; Gemini
wrote many mechanically invalid rules; DeepSeek found many proofs and many
wrong ones; Claude had the best agreement. In a later end-to-end run where
each model also produced its own Stage 1 and Stage 2, the translation varied as
much as the bridge generation, so cross-model results could not be interpreted
as a bridge-writer comparison alone.

**Decision.** Retained, but off by default and not included in the named
`high-recall` configuration. It is available in `stack-open` and through the
explicit option.

**Reason.** Literal bridges are useful on open-world problems and can construct
multi-step connections that graph retranslation alone cannot find. They are
also the most direct source of false definite answers on closed-world and
accepted-Unknown material. Prompt changes produced a clear precision/recall
tradeoff but no setting suitable as a dataset-blind default. The mechanism is
therefore valuable experimental machinery and an explicit high-risk option,
not ordinary behavior. On the same 165-case cohort, the broad prompt found 76
proof cases but gave definite proofs to 11/20 accepted-Unknown and 3/20
accepted-False FOLIO controls; the soundness-first prompt reduced this to 44
proof cases and removed most control failures, but EntailmentBank agreeing
proof sets fell from 46 to 32 and Multi-LogiEval from 12 to five.

Provenance: widened Sonnet result (local archive: `memos/MEMO_2026_08_14_unifier_widened_sonnet_result.md`),
soundness-prompt result (local archive: `memos/MEMO_2026_08_14_unifier_v5_9_revised_prompt_result.md`),
and graph comparison (local archive: `memos/MEMO_2026_08_20_graph_vs_litbridge_result.md`).

### Signed negative bridge conclusions

**Mechanism.** The literal-bridge grammar and compiler can represent rules such
as:

```text
bee(X) -> normally not vertebrate(X)
```

The prompt explains that a negative English conclusion must use explicit
`NOT` in the formal conclusion. Code also supports a separate distinctness
channel that constructs negative equality conclusions.

**Experiments.** Across the first four-model run, the bridge-generation calls
wrote 2,464 rules and not one explicit negative conclusion. More seriously, 29
rules described a negative conclusion in English but wrote a positive formal
conclusion. A second four-version run likewise produced no ordinary negative
bridge; six negative inequality rules on one case came from the code-guided
distinctness channel. The compiler preserved their sign correctly and GK used
them, proving that the mechanical path worked.

A subsequent ten-case v6.1 diagnostic added a focused polarity explanation and
a mechanical check that refuses an English-negative/formal-positive mismatch.
DeepSeek then wrote 13 ordinary negative conclusions. One of them alone carried
a proof in FOLIO case 18:
`turtle(X) -> normally not rabbit(X)`. Thus general negative generation is
possible, but it appeared only after a targeted prompt and validation change
and has not yet been measured broadly.

**Decision.** Retained as supported syntax, a specialized distinctness
facility, and a validated general bridge form. Its broad precision and recall
remain experimental.

**Reason.** Negative conclusions are necessary for False answers and for
ordinary exclusions, so removing the capability would be wrong. The evidence
shows that a single example was insufficient, while an explicit polarity check
made at least one model use the form. Specialized candidate selection followed
by code construction remains more reliable for inequality and other narrowly
defined exclusions. In the first broad run, 2,464 generated rules contained
zero ordinary negative conclusions and 29 English/formal polarity mismatches;
after focused instructions and validation, DeepSeek wrote 13 negative rules in
a ten-case diagnostic and one carried a proof. That is evidence of capability,
not yet a broad precision estimate.

Provenance: four-model archive (local archive: `elogs/unifier_v6_archive_2026_08_15/README.md`)
and targeted signed-rule result (local archive: `memos/MEMO_2026_08_15_unifier_v6_1_mechanical_fixes.md`).

### Legacy abstract representations and presets

**Mechanism.** The `-abstract`, `-abstract-roles`, and `-abstract-max` presets
replace or simplify parts of the canonical representation. Their operations
include flat event relations, type enrichment, guard removal, property/class
alignment, context or definite-description simplification, entity merging,
and supporting bridge axioms. These mechanisms remove distinctions so that
more expressions unify.

**Experiments.** Earlier FOLIO work found substantial gains from abstract
representations, especially type enrichment, guard removal, and flatter event
forms. The corresponding Core regression study showed the cost: on a targeted
314-case Core set, maximal abstraction often changed an expected Unknown into
a definite answer or lost a proof that depended on role, context, modality, or
default structure. Legacy maximal abstraction lost roughly 40% of the standard
answers on that regression set. In the all-Core/FOLIO proof-shortener
comparison, the legacy Davidson/Existfold condition alone lost 18--43 Core
cases per model.

The later same-parse abstract retry probe was more controlled. On 674
model-specific records still unresolved after critic and graph retranslation,
the whole abstract bundle produced 23 new definite answers: 17 correct and six
wrong, 74% precision, compared with 93% for the critic-plus-graph stages.
Ablation attributed recoveries to the flat relational base, type enrichment,
guard removal, and degree collapse. Entity merge was necessary for three wrong
answers and no correct answer; object/class bridges, definite handling, and a
strict modifier rule were necessary for none. Three apparent event-fold wins
were obtained precisely by discarding content-event structure or missing
participants that Davidson2 correctly refused to erase.

**Decision.** Preserved as explicit legacy/research presets. They are not part
of the canonical default, and a new abstract-retry stage was not adopted.

**Reason.** These encodings can recover proofs by removing representational
distinctions, but the same operation creates false proofs when the distinction
matters. Applying them only after Unknown protects earlier answers, yet the
measured residual precision still remained substantially below the current
retry-stage sequence. The presets remain valuable for reproduction, ablation studies,
and deliberately high-recall experiments. On 674 records unresolved after the
current stack, the same-parse abstract bundle added 17 correct and six wrong
answers (74% precision), versus 111 correct and eight wrong additions (93%)
for critic plus graph retranslation; on the targeted 314-case Core regression
set, maximal abstraction lost roughly 40% of standard answers.

Provenance: LPAR abstraction summary (local archive: `memos/MEMO_2026_08_24_lpar_abstraction_summary.md`),
Core regression memo (local archive: `memos/MEMO_2026_08_26_absmax_core_regressions.md`), and
canonical census (local archive: `memos/MEMO_2026_08_27_canonical_stack_census_closed.md`).

### Legacy Davidson and legacy Existfold

**Mechanism.** The older Davidson fold compacted event information without an
exact round-trip requirement. The older existential fold applied more broadly
and used generic witness machinery.

**Experiments.** In the full 1,600-Core/203-FOLIO comparison, the legacy pair
reduced median proof length but lost 18--43 Core cases per model. Earlier
audits also found invented or misplaced participants and unreadable witness
terms. These were not isolated search fluctuations: the new version-2 pair was
run on identical cached translations and had zero losses.

**Decision.** Kept only for historical reproduction and explicit experiments;
superseded as an ordinary choice by Davidson2 and Existfold2.

**Reason.** Proof shortening is not sufficient if the compact representation
does not preserve the original theory. The version-2 mechanisms retain the
useful compression while refusing transformations that cannot be reversed. In
the 1,600-Core/203-FOLIO, four-model paired study, the legacy pair lost 18--43
Core cases per model, whereas the version-2 pair lost none in any of the eight
dataset/model cells.

### Post-retranslation acceptance policies

**Mechanism.** Deterministic checks inspect a critic or graph proof and the
translation difference before accepting the later-stage answer. Checks look
for such patterns as an unlicensed exclusion, foreign imported content,
changed logical skeleton, lost modality, lost quantifier or negation scope,
omitted participant roles, and a proof that uses a contested graph literal.
The experimental `-accept permissive|balanced|strict` option assigns different
severities.

**Experiments.** The policies were replayed over all 119 stored additions from
the two complete canonical-configuration runs:

| Policy | Correct accepted / cautioned / refused | Wrong accepted / cautioned / refused |
|---|---:|---:|
| permissive | 111 / 0 / 0 | 8 / 0 / 0 |
| balanced | 47 / 0 / 64 | 1 / 0 / 7 |
| strict | 27 / 20 / 64 | 0 / 1 / 7 |

Balanced removed seven wrong answers but also 64 correct answers. Strict
prevented all eight wrong answers from becoming final but accepted only 27 of
111 correct additions. Exhaustive subsets of the checks found only one
net-positive rule: refusing a proof that uses one specifically contested
literal removed one wrong and zero correct additions. Even apparently sensible
rules were too broad; for example, a rule refusing graph answers after a critic
`KEEP` verdict would lose 36 correct answers to catch two wrong ones.

**Decision.** Experimental option, off by default.

**Reason.** The structural warnings describe real risks but are poor decision
rules. The same representational difference occurs in many correct repairs, so
a strict filter trades much more recall than the error reduction justifies.
The records remain useful for research, explanation, and future calibration.
On all 119 stored critic/graph additions, the balanced policy refused seven of
eight wrong additions but also 64 of 111 correct ones; the strict policy caught
the eighth wrong addition but accepted only 27 correct additions without
caution.

Provenance: acceptance-policy result (local archive: `memos/MEMO_2026_08_27_retranslation_acceptance_result.md`).

## Related documentation

- [Mechanism index](README.md)
- [Default](default.md)
- [Experimental](experimental.md)
- [Superseded](superseded.md)
- [Lessons](lessons.md)
