# Reasoning and proofs

The prover call, the answer it returns, and what the pipeline does with the
proof.

This is the last step of every attempt. The compiler has produced a clause
list; GK searches it for a proof of the question or of its negation. What comes
back is a raw result, not an answer: this page describes how the pipeline turns
one into the other, and how it keeps track of which clauses a proof used.

A reader debugging a wrong or missing answer usually starts here, because the
proof names the clauses it used and those names lead back to the source
sentence, the injected axiom, or the retry stage that supplied them.

## Calling GK

`prover.call_prover` writes the clause list to a temporary file and runs the
`gk` binary as a subprocess. `-seconds N` sets the search time; the default is
2 seconds. `-strategy FILE` replaces the default JSON strategy, and
`-axioms FILE...` replaces `axioms_std.js`.

Every call is recorded against the stage that made it. `prover.stage()` marks
the current stage and `prover.collector()` gathers the calls for one case, so
the run record can say how many GK calls each stage made. The fields are listed
in [runtime records](../reference/runtime-records.md).

A stage can make more than one GK call. `fallback_norm` submits the exclusive
reading before the inclusive one, so it makes at most two. Literal bridge
generation runs two rounds.

## Reading the result

`procproofs.process_proof` reads the prover output. It selects an answer,
applies the confidence threshold, and collects the proof steps.
`proof_answer_select.py` chooses among several answers.
`proof_answer_format.py` formats the answer string.

`Unknown.` means no proof was found within the time limit. It is a definite
statement about the search, not about the question.

## Confidence

A proof carries a confidence. A value below 1.0 produces a hedged answer such
as `Probably true.` How confidence enters the clauses and reaches the answer is
described in
[questions, confidence and answers](questions-confidence-and-answers.md).

## Proof source clauses

Each proof step names the clause it came from, as `["in", NAME, ...]`. The
names identify source units (`sent_Sx`), injected axioms, and representation
adapters (`frm_*`). Several checks read these names: the graph question-only
rule, the optional acceptance checks, and the English renderer, which labels an
adapter step "representation conversion" rather than knowledge.

## Proof deduplication

The prover often returns multiple proofs for the same answer that differ only in temporal/world-navigation paths (e.g., 10 proofs for "in the house" using different world-state axiom routes W0→W1, W0→W1→W2, etc.).

`_deduplicate_proofs(answers)` in `proof_answer_select.py` eliminates redundant shadow proofs:

1. **Group** answers by conclusion value (deep-equal) AND content fingerprint (frozenset of `sent_*` sources used in the proof).
2. **Within each group** (same answer + same content sentences), proof A dominates proof B if ALL of:
   - `len(A.blockers) <= len(B.blockers)`
   - `A.confidence >= B.confidence - 0.15` (configurable threshold)
   - `len(A.steps) <= len(B.steps)`
3. **Remove dominated proofs**, keeping the simplest non-dominated proof per group.

Runs after `_filter_by_best_tier` and `_filter_tautological_population_answers`, before answer formatting.

---

## English rendering

`proof_render.py` turns proof steps into English. The
[proof output reference](../reference/proof-output.md) describes the renderer,
entity naming and the display modes.

## Related documentation

- [Proof output reference](../reference/proof-output.md)
- [Questions, confidence and answers](questions-confidence-and-answers.md)
- [Proof processing code](../code/proof-processing.md)
- [GK clause list](../encodings/gk-clauses.md)
