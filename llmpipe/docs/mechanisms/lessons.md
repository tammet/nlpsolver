# Cross-cutting conclusions

Conclusions that hold across several experiments, and the limits of the
evidence behind them.

## Cross-cutting conclusions

### Preserve the faithful theory and add recall only after Unknown

The strongest repeated result is architectural. Always-on lossy abstraction
damaged Core and some FOLIO cases. The same kind of alternative representation
used only after Unknown cannot replace an earlier correct answer. Davidson2 and
Existfold2 are exceptions because they have explicit reversibility checks and
adapters; they are faithful internal representations, not merely coarser
readings.

### Full-confidence proof search, trust after proof

GK may postpone or discard a clause whose confidence is very low, and the
pipeline may suppress a final proof below its reporting threshold. Therefore a
bridge experiment must not encode deliberate uncertainty as a tiny clause
confidence before proof search. Bridge clauses are submitted at full search
confidence with their ordinary defeasibility blocker. Trust is calculated and
reported after GK returns a proof. This separation was verified by submitting
the same clause with several post-proof weights: the GK clause and native proof
were unchanged, while only the reported adjusted confidence changed.

### Several bridges must be searchable together

Single-bridge submissions cannot discover a proof that genuinely requires two
or three representation connections. The literal-bridge experiments produced
deletion-minimal proofs using up to seven bridges in later pilots, and the
EB2-0020 result required three defensible bridges. The pipeline therefore
submits explicit combined bridge theories as well as first-call-only and
second-call-only theories. This is not a license to mix every speculative rule:
the exact submitted rule set and every proof-used subset must remain recorded.

### Do not stop analysis at the first proof

GK may find one of several possible proofs. In EB2-0020 the first proof used
false bridges; only after excluding one cited bridge did a defensible proof
appear. Deletion minimization establishes which bridges a proof actually
needs, and exclusion search can expose alternatives hidden by the first result.
This is useful even when the runtime eventually returns only one answer.

### A proof is not evidence that its bridge is sound

FOLIO controls repeatedly demonstrated that a false or overbroad rule can close
a proof. Conversely, EntailmentBank demonstrated that a sound background rule
may be essential even though the passage does not state it. Proof existence,
semantic plausibility, passage licensing, benchmark agreement, and
representation equivalence are different measurements and should remain
separate in records and reports.

### Representation repair and knowledge addition should be distinguished

Graph retranslation and critic retranslation usually repair how the source was
encoded. Literal and graph bridges may add a new background implication. The
former mechanisms measured much higher precision on closed-passage sets; the
latter were most useful on EntailmentBank. A future trust policy should not
assign the same risk merely because both appear as additional clauses in a
proof.

### Search failures and translation failures require different remedies

Many unresolved cases cannot be repaired by another lexical implication. The
manual bridge audits identified missing existential witnesses, lost identity,
comparison or aggregation operators, temporal change, malformed questions, and
inexpressible relations. The action-planning study separately showed a search
strategy that could verify a supplied six-step plan but could not discover it.
Such cases should be recorded as translation, representation, or search gaps,
not used indiscriminately to tune bridge generation.

### Dataset-blind defaults require mixed-material evidence

The mechanism with the most proofs is not necessarily the best default.
Literal bridges were valuable on all-True EntailmentBank cases and harmful on
Core accepted-Unknown cases. Graph bridges showed the same pattern more mildly.
The default therefore reflects a mixed-material tradeoff: the canonical census
measured 111 correct additions against eight wrong additions for critic plus
graph retranslation, while stricter filters or lossy abstraction gave much
worse recall/precision exchanges. Optional configurations expose a different
choice without routing on a dataset label.

## Evidence limitations and future use

The results above are development evidence, not a claim that the default is
optimal on every distribution. Several studies reused cached translations;
this is desirable for paired converter comparisons but does not measure model
drift. Some mechanisms were designed on FOLIO and Multi-LogiEval cases before
being tested elsewhere. Claude was omitted or sampled in some long runs. The
canonical census supporting the balanced default has two complete model runs
and incomplete GPT and Claude runs. The full proof-shortener comparison is broader
and stronger because it includes four models and all Core/FOLIO cases.

For future papers or experiments, the most important comparisons to preserve
are:

1. faithful canonical theory versus each later retry on the same translation;
2. case-level correct additions and wrong additions, separated by dataset and
   expected Unknown versus definite answers;
3. exact stage attribution and LLM/GK cost;
4. proof-used bridge sets, not merely all generated candidates;
5. raw proof length and proof length excluding representation conversions;
6. first proof versus alternative minimal proofs;
7. representation repair versus newly asserted background knowledge;
8. activation count, so a zero result is not confused with a mechanism that
   never ran.

The current balanced default is a stable implementation choice based on the
best mixed evidence available at the end of August 2026. Optional and
experimental mechanisms remain useful because a future evaluation may justify
a different precision/recall setting or a more reliable selector. The negative
results are equally important: they identify apparently reasonable ideas that
changed many theories but did not improve answers, and safety checks that
removed more valid reasoning than errors.

## Related documentation

- [Mechanism index](README.md)
- [Default](default.md)
- [Optional](optional.md)
- [Experimental](experimental.md)
- [Superseded](superseded.md)
