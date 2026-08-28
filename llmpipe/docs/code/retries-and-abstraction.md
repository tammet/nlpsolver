# Retries and abstraction code

The two fallbacks, the critic, the graph route, the two bridge mechanisms
and the optional acceptance checks.

[Architecture: retries](../architecture/retries.md) describes what each stage
does. This page describes the modules.

## Modules

### fallback_norm.py and fallback_hyp.py

**Role:** The two abstention fallbacks — a second conversion of the same
Stage-1/Stage-2 parse when the initial attempt ends unresolved, and one more gk
call.  Described in full in [retries](../architecture/retries.md).  Neither makes an LLM call.

**`fallback_norm.py`** owns the nine configuration booleans and the internal option keys they switch on; the `casenorm` pass (`logconvert` calls it beside `dashnorm`); the inclusive-cue and apposition tests and the question rewrites they license (`apply_question_transforms`, which `logconvert` calls and which is inert while both keys are off); `inclusive_theory`; and `run`, the exclusive-before-inclusive submitter

**`fallback_hyp.py`** owns `REFUTATION_CHECK`; `conditional_questions`, the trigger; `hypothetical_theory` and `refutation_theory`; and `run`


`fallback_hyp` imports `fallback_norm` for its option switching and its
submitter, so its conversions carry the normalizations too.  Both reach
`logconvert`, `prover` and `procproofs` through imports inside `run`, so
`logconvert` can import `fallback_norm` at the point of use without a cycle.
`solve.py` reaches them only inside the `fallback_norm_flag` /
`fallback_hyp_flag` branch.

### The litbridge_* modules

**Role:** Literal-bridge abstraction — inventing implication rules over a case's own
atoms when the pipeline cannot answer, and compiling them to clauses.  Seven modules,
described together in [literal bridges](../architecture/literal-bridges.md) rather than one subsection each, because they are only ever
used as one stack:

| module | owns |
|---|---|
| `litbridge_atoms.py` | the atoms a bridge may be built from, how they are displayed, and the raw Stage-2 reading that records their semantic sign |
| `litbridge_rules.py` | the rule grammar, and the distinctness and negative-relation channels |
| `litbridge_compile.py` | rule → clauses: the converter route, the exact-template route, tautology removal, the redundancy check |
| `litbridge_chain.py` | reading a compiled bridge back: suppliers, chain status, and which hypotheses a proof cites |
| `litbridge_prompts.py` | the system prompt, the case message and the candidate lists |
| `litbridge_procedure.py` | `bridge_context` and `bridge_round`: one case, one round, no gk call |
| `litbridge_converter.py` | the one call into `logconvert`, under a scoped option state |

The import graph is acyclic; `litbridge_atoms` imports only `litbridge_converter`.  Nothing in
the ordinary pipeline imports any of them — `solve.py` reaches them only inside the
`litbridge_flag` branch.

### The graph_* modules

**Role:** Open-relation graph abstraction — translating a case a second time into
three-item open triples, inventing implications between the open names, searching that
theory, and lifting a proof back.  Eight modules, described together in [graph representation](../architecture/graph-representation.md):

| module | owns |
|---|---|
| `graph_stage2.py` | the graph Stage-2 call, the structural checks of the atom contract, the corrective retry, the per-case measurements |
| `graph_compile.py` | open triples → clauses under the frozen graph option set; the sidecar and the name-drift check |
| `graph_inventory.py` | the concept and relation inventories, the comparison view, and supply/demand read from the clauses |
| `graph_pairs.py` | the nine candidate shapes and the seven mechanical filters |
| `graph_judge.py` | the judge prompts and parser, and the serialization of a label into bridge rules |
| `graph_search.py` | one gk submission per bridge set (P0–P3), minimal sets, the exclusion pass, grading, tiers |
| `graph_lift.py` | the proof-used units and rules, the alignment, the lifting call, the lifted worlds, unit retranslation |
| `graph_procedure.py` | `graph_context` and `graph_run`: one case, and the record |

The graph modules import the `litbridge_*` modules and never the other way round: the literal
bridge's compiler is the graph route's lifting boundary, and its `scoped` is the option
state every graph conversion runs inside.  Nothing in the ordinary pipeline imports a
`graph_*` module — `solve.py` reaches them only inside the `graphbridge_flag`
branch.

### critic_pass.py and critic_render.py

`critic_render` builds what the critic reads: the case, its Stage 1 and its
Stage 2, compacted. `critic_pass` makes the call, parses the report, decides
whether a finding blocks, and runs the corrective. One critique, one rerun.

### graph_p0.py

Layer 1 of the graph mechanism: the retranslation, the structural checks and
one GK call. `arity_issues` reads the operator-arity report from
`graph_stage2.check_operator_arity` and stops before compilation when a
translation is still malformed after the corrective retry.
`question_only_proof` reads the proof's cited sources and leaves the stage
unresolved when every substantive source is a question unit.

### graph_ablation.py

One switch per repair, so a repair can be reverted alone and measured alone.
It is a research module and no default reads it.

### retrans_accept.py

The optional proof-local acceptance checks for critic and graph answers,
selected by `-accept`. Off unless the option is given.

## Related documentation

- [Retries and retranslation](../architecture/retries.md)
- [Graph representation](../architecture/graph-representation.md)
- [Literal bridges](../architecture/literal-bridges.md)
- [Source map](source-map.md)
