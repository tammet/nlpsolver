# prompts/

The LLM system prompts the pipeline sends.  Every file here is either loaded
by the code or was named on the command line by a published experiment run.

Superseded drafts and pinned snapshots stay on the working copy but are not
committed; `.gitignore` lists them.  The prompt versions the two papers cite
are published elsewhere and are unaffected: the per-run `prompts/` snapshots in
the [nlformtasks](https://github.com/tammet/nlformtasks) release, and the
`nlpsolver` tags (`lpar-2026-06-23` for the LPAR paper).

## The two-stage parser

The default translation.  Stage 1 converts English into a JSON list of atomic
semantic units.  Stage 2 converts that JSON into the predicate-logic JSON the
converter clausifies.  Loaded by `solver/llmparse.py`.

| file | role |
|---|---|
| `stage1_instructions_full.txt` | Stage-1 specification: entity ids, unit types, scope and quantifier rules, the modal-mode table |
| `stage1_examples.txt` | worked Stage-1 examples, English to unit JSON |
| `stage1_checklist_full.txt` | short procedural checklist appended last |
| `stage2_instructions_full.txt` | Stage-2 specification: predicate inventory, quantifier mapping per unit type, modal classifiers, `$defq` encoding |
| `stage2_examples.txt` | worked Stage-2 examples, unit JSON to logic JSON |
| `stage2_checklist_full.txt` | short procedural checklist appended last |

The checklists are separate files so the most error-prone rules can be repeated
at the end of the prompt without enlarging the instructions.

### How a system prompt is assembled

`solver/llmparse.py::_compose_prompt` concatenates the three files in order:

```
<instructions_full.txt>

Examples:

<examples.txt>

<checklist_full.txt>
```

That string becomes the `system` prompt.  The `user` prompt is the input text
for Stage 1, or the Stage-1 JSON for Stage 2.  See `_compose_prompt` and
`parse_text` in `solver/llmparse.py`.

## Retry-stage prompts

The `balanced` default runs four stages after the initial attempt.  Two of them
call a model, and both have their own prompts.  See
[retries](../docs/architecture/retries.md).

### `critic/` — the critique pass (`-critic`)

| file | role |
|---|---|
| `critic_system.txt` | the critic reads the English, the Stage-1 units and the Stage-2 logic, and reports findings |
| `critic_system_v2.txt` | an alternative wording, selected by `critic_pass.use_prompt("v2")`; it lost its evaluation and is not the default |

### `graph/` — the graph representation (`-graphtrans`, `-graphbridge`)

Layer 1 retranslates the case into open triples; layer 2 invents implications
between the open names.  See
[graph representation](../docs/architecture/graph-representation.md).

| file | loaded by | role |
|---|---|---|
| `graph_stage2_instructions.txt` | `graph_stage2.py` | the second, open-triple Stage 2 |
| `graph_stage2_examples.txt` | `graph_stage2.py` | its worked examples |
| `graph_stage2_checklist.txt` | `graph_stage2.py` | its checklist |
| `graph_onestage_instructions.txt` | `graph_stage2.py` | the one-call variant that skips the unit JSON |
| `graph_onestage_examples.txt` | `graph_stage2.py` | its worked examples |
| `graph_judge_system_sentences.txt` | `graph_judge.py` | judge a candidate pair against the sentences |
| `graph_judge_system_names_only.txt` | `graph_judge.py` | judge from the open names alone |
| `graph_judge_system_lexical.txt` | `graph_judge.py` | judge on lexical grounds |
| `graph_holistic_system.txt` | `graph_judge.py` | propose pairs from the whole inventory at once |
| `graph_grader_system.txt` | `graph_search.py` | grade a found derivation |
| `graph_lift_system.txt` | `graph_lift.py` | lift a graph proof into the ordinary theory |
| `graph_retranslate_suffix.txt` | `graph_lift.py` | appended when the lift retranslates |

### `dynamic_alignment/` — the literal bridge (`-litbridge`)

Off by default; `-stack-open` and `-abstract-max` turn it on.  See
[literal bridges](../docs/architecture/literal-bridges.md).  The directory name
predates the mechanism and is kept because the modules address it by that path.

| file | named by | role |
|---|---|---|
| `unifier_rules_v6_1_signed_system.txt` | `litbridge_prompts.SYSTEM_PROMPT_NAME` | ask for implication rules over the case's own atoms |
| `unifier_rules_v6_signed_system.txt` | `litbridge_prompts.BASE_SYSTEM_PROMPT_NAME` | the v6 base the above revises |
| `unifier_distinctness_v5_3_system.txt` | `litbridge_rules.DISTINCT_SYSTEM_PROMPT_NAME` | decide which names denote distinct things |
| `negative_relation_v6_1_system.txt` | `litbridge_rules.NEGATIVE_SYSTEM_PROMPT_NAME` | propose negative relations |
| `litbridge_grader_v1_system.txt` | `litbridge_grader.PROMPT_NAME` | grade a proposed rule |

## Other command-line prompts

| file | switch | role |
|---|---|---|
| `prenorm_full.txt` | `-prenorm` | pre-Stage-1 normalization: reword the input so every distinct entity, property and relation is worded the same way throughout |
| `folio_directanswer_instructions.txt` | `-directanswer FILE` | one call answers True/False/Unknown from the premises and the conclusion, with no logic and no prover |

## Single-stage combined prompts

One call reads English and emits the Stage-2 logic JSON directly, with no
intermediate unit JSON:

```
-combined-instr FILE [-combined-examples FILE] [-combined-checklist FILE]
```

The same `_compose_prompt` assembles them; examples and checklist are optional.
The two kept here are the two the NeSy 2026 ablations ran:

| file | construction |
|---|---|
| `combined_minimal_instructions_full.txt` | `minimal` — output-format signature and core conventions only, about 10 KB, no per-case rules |
| `combined_v2_instructions_full.txt` | `v2` — the two-stage texts condensed into two sequential PART blocks, output rules first, rule wording unchanged |

`combined_examples_pure.txt` holds the 60 worked English-to-logic examples both
of them use, passed with `-combined-examples`.

Later constructions exist on the working copy but are not committed, because no
published run used them.  `outputs/core/ablations/` and `outputs/folio/` in the
nlformtasks release carry the exact prompt files each run used.
