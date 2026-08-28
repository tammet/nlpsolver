# Experimental mechanisms

Mechanisms kept for research or diagnosis. None of them is part of a
named configuration.

## Experimental mechanisms retained mainly for research

### Post-proof bridge grading

**Mechanism.** After a bridge-dependent proof is found, an LLM assesses each
cited bridge. Several versions separated passage licensing, ordinary
background plausibility, missing restrictions, direction, and interaction
between bridges. Later prompts graded all bridges in one minimal proof set with
the simpler categories SOUND, PLAUSIBLE, NEEDS_CONDITION, UNSOUND, and
UNCERTAIN. The accepted answer and proof result were hidden from the assessor.

**Experiments.** The first widened Sonnet run assessed 164 used bridges: 40
were reasonable as written, 36 were possible passage repairs, 83 were
incomplete without repair, and 114 had a reported counterexample or wrong
direction. A revised grader fixed several notation and context errors but was
too generous with unguarded implications. A rule-only two-call grader then
classified 68 bridges as 20 ACCEPT, 47 NEEDS_CONDITION, and one REJECT; asking
for a missing condition encouraged the model to invent one even for clean
negative examples.

The simplified proof-set assessor produced 14 SOUND, 19 PLAUSIBLE, 14
NEEDS_CONDITION, and 36 UNSOUND grades over 83 bridge slots. Its proof-set
decision was nearly orthogonal to benchmark agreement:

| Set assessment | Agreed with accepted answer | Disagreed |
|---|---:|---:|
| PASS | 11 | 9 |
| FAIL | 37 | 6 |

Using the assessor as an answer filter reduced expected-True performance far
more than it improved Unknown controls. Earlier passage-only bridge graders
showed the same pattern: on FOLIO they removed 88--100% of wrong bridge answers
but retained only 19--38% of right bridge answers. Manual reading found that
about half of the removed right answers were right by luck through an unsound
bridge, while the other half used legitimate representation conversions the
grader did not recognize.

**Decision.** Do not use bridge grades as the ordinary answer decision. Keep
grading as diagnostic evidence and as a way to describe the trust cost of an
optional bridge proof.

**Reason.** Semantic quality and benchmark agreement are different: a sound
background implication may be disallowed by a closed-passage benchmark, while
an unsound implication may happen to derive its correct label. The graders
also failed to distinguish semantic invention from representation conversion
reliably. A single threshold cannot resolve these objectives. In the simplified
83-slot assessment, PASS proof sets agreed with the accepted answer only 11/20
times, while FAIL sets agreed 37/43 times; using the grade as a filter therefore
reduced expected-True correctness more than it protected Unknown controls.

Provenance: wrong-proof audit (local archive: `memos/MEMO_2026_08_14_wrong_proof_bridge_and_grader_audit.md`),
bridge-set result (local archive: `memos/MEMO_2026_08_14_bridge_set_assessor_v6_result.md`), and
route precision result (local archive: `memos/MEMO_2026_08_21_route_precision_result.md`).

### Repairing bridges marked NEEDS_CONDITION

**Mechanism.** For a used bridge judged incomplete, one LLM diagnoses the
missing condition. Code constructs a menu of conditions that existing case
facts or rule conclusions can supply. A second LLM selects a condition, code
adds it to the bridge premise, checks unification and range safety, recompiles
the bridge, and reruns GK. This prevents a grader from adding a condition that
can never apply.

**Experiments.** Among 104 incomplete bridges, the system built 83 candidate
menus; 59 repaired variants passed all mechanical checks. A blind reassessment
accepted eight, rejected two, and still found an ordinary counterexample for
49. Of 105 affected proof-set rows, 55 could not be reconstructed because some
bridge had no valid variant. Of the remaining 50, 22 still proved and 28 no
longer proved. The repair removed seven wrong-answer proofs but also removed 21
correct-answer proofs. Only one survivor met the most conservative policy.

**Decision.** Experimental record only; not integrated into the runtime.

**Reason.** Grounding the condition in existing atoms was mechanically sound,
but the original bridge was often wrong in direction or concept, not merely
missing a premise. Adding a condition cannot repair that. The cost and recall
loss do not justify a separate repair conversation before better initial rule
generation exists. Of 104 bridges examined, only 59 obtained a mechanically
valid repair; 49 of those still had an ordinary counterexample. Rebuilding the
affected proofs removed seven wrong-answer proofs but also 21 correct-answer
proofs.

Provenance: condition-repair result (local archive: `memos/MEMO_2026_08_14_needs_condition_repair_result.md`).

### Open-graph proof lifting back to detailed logic

**Mechanism.** When the simple graph representation finds a proof, lifting
tries to reconstruct its graph bridges or its proof-used units and
implications as rules over the
detailed canonical atoms, then reruns GK. A successful lift would turn an
easy-to-find graph proof into a proof over the richer representation.

**Experiments.** Early graph pilots demonstrated that lifting is possible in
some cases, but the controlled v2 comparison found no net answer gain for its
additional calls. It attempted lifting on 71 cases, produced six lifted proofs
and zero successful one-unit retranslations, and spent 56 extra LLM calls. All
six lifted answers had already been reached by the graph theory, so the final
case score did not change. Alignment depended heavily on shared Stage-1 entity
identifiers and was weakest when the graph translator chose a different
argument shape.

**Decision.** Retained as a research path where available, not in the default
stage sequence.

**Reason.** Lifting remains conceptually useful for producing a richer proof
or a candidate detailed bridge, but current measured answer value does not pay
for its cost and failure surface. A graph proof can still be reported with its
graph clauses and provenance; lifting should not be required for the default
answer path until it has a clear held-out benefit. In the controlled run it
attempted 71 cases and spent 56 extra LLM calls, producing six lifted proofs
but no new final answer because all six cases were already solved in the graph
representation.

Provenance: graph v2 result (local archive: `memos/MEMO_2026_08_17_graph_v2_result.md`) and
graph pipeline result (local archive: `memos/MEMO_2026_08_17_graph_pipeline_result.md`).

### Specialized action-planning translation

**Mechanism.** This isolated pilot extends English-to-logic translation with
actions and state changes. Stage 1 identifies entities, action roles, whether a
sentence states applicability, an effect, or an actual occurrence, and whether
the question asks about the actual state or a reachable state. Stage 2
translates each sentence separately as an initial fact, applicability rule,
effect rule, occurrence, or question. Code, not the LLM, constructs action
terms, hypothetical successors, reachability counters, frame clauses, and GK
syntax.

Hypothetical applicability uses `succ(W,$do(A,W))`; `next` is reserved for an
action that actually occurs in the narrative. Effects are separate clauses,
including explicit negative effects. Persistence is keyed to the successor so
one hypothetical action does not alter a sibling successor. Actual-state
questions require an `actual(W)` condition; plan questions require
`reachable(W,N)`. Separate partial effect laws are not merged into a single
STRIPS schema.

**Experiments.** A hand-written pipeline-form GK suite ran 24 fixtures: 20
passed and four remained expected search failures. It covered two alternative
travel plans, bounded route depth, sibling persistence, explicit deletion,
possession transfer, a two-step blocks plan, a supplied six-step Sussman plan,
partial effects, actual versus merely possible actions, and the ordinary
0.10 reporting threshold. The unresolved Sussman cases were search-strategy
give-ups, not representation failures.

The 20-case LLM translation pilot used Gemini 3.7 Flash, DeepSeek V4 Flash, and
GPT-5.4. Frozen-run outcome accuracy was 15/20, 7/20, and 8/20; an adapter-only
repair raised DeepSeek and GPT to 8/20 and 9/20. No compiled negative control
produced an unexpected plan. The dominant failure was missing entity typing:
rules required `person(Alice)` or `block(A)`, while the translation supplied
only possession or location. Adding only human-identified entity types to the
stored translations recovered five missed Gemini cases and ten each for
DeepSeek and GPT. This was a diagnosis, not a corrected pipeline score.

**Decision.** Retained as a separate experimental planning pipeline. It does
not modify the normal English-to-logic path.

**Reason.** The representation successfully separates ability from actuality,
supports partial and negative effects, and allows GK to extract plan terms.
The LLM interface is not mature enough for wider adoption: case-wide entity
typing, population witnesses, action-role aliases, and planning-oriented
search still need work. Isolation prevents these temporal assumptions from
changing ordinary static reasoning. The hand-written suite passed 20/24
fixtures, with four declared search failures; the 20-case, three-model LLM
pilot scored 15/20, 7/20, and 8/20 before a small adapter repair. Its dominant
missing-type failures show that the representation evidence is stronger than
the translation evidence.

Provenance: pipeline-form GK suite (local archive: `memos/MEMO_2026_08_23_action_planning_gk_x1b_result.md`)
and LLM pilot (local archive: `memos/MEMO_2026_08_23_action_planning_x2_result.md`).

### Multiple-model portfolios and voting

**Mechanism.** Several experiments ran the same pipeline with different LLMs
and considered whether their definite answers or generated bridges should be
combined. A committing-only vote treats Unknown as abstention; a proposal
union would combine rules written by different models before GK.

**Experiments.** On the 165-case signed literal-bridge run, eight model/version
configurations ranged from 86 to 113 correct cases under corrected case-level scoring.
Claude Sonnet 4.6 was best at 113, followed by Gemini 3.7 low at 102; the other
six configurations ranged from 86 to 99. The sources of the difference were not limited
to bridge writing: each model translated the source itself, and Stage 1 and
Stage 2 were byte-identical across all four main model runs on only two of 165 cases.
The best configuration obtained 40 correct initial-attempt answers, 22 from first-call
bridges, three from later bridge search, and 48 correct abstentions. DeepSeek
found more bridge proofs than several models but also more wrong definite
answers.

Generated rules were highly complementary—only a small fraction of formulas
were shared by all models—but the oracle union is not an implementable policy.
It counts a case as solved whenever hindsight can choose the correct model and
ignores cases where another model produced a conflicting or wrong definite
answer. Raw proposal union also increases the chance that one overbroad bridge
closes a false proof. Earlier FOLIO voting results showed that a
committing-only vote can beat ordinary majority voting, but those results used
different translations and do not establish a general default.

**Decision.** Keep multi-model runs as an evaluation and proposal-diversity
tool. The ordinary pipeline uses one selected model consistently for Stage 1,
Stage 2, critic, graph, and bridge calls; no runtime ensemble is integrated.

**Reason.** Model diversity clearly increases the set of potentially solvable
cases, but no tested rule selects the trustworthy answer without access to the
benchmark label. A valid ensemble experiment must score conflicts, wrong
definite answers, and cost, not only the union of successes. Across eight configurations
on the same 165 cases, corrected totals ranged from 86 to 113 and the best configuration
combined 40 initial-attempt answers, 25 bridge-search answers, and 48 correct
abstentions; formula overlap was small, but raw unions also accumulated wrong
definite answers.

Provenance: eight-arm archive (local archive: `elogs/unifier_v6_archive_2026_08_15/README.md`)
and four-model bridge audit (local archive: `memos/MEMO_2026_08_14_four_model_bridge_generation_audit.md`).

## Related documentation

- [Mechanism index](README.md)
- [Default](default.md)
- [Optional](optional.md)
- [Superseded](superseded.md)
- [Lessons](lessons.md)
