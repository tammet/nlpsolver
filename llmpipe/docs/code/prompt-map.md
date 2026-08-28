# Prompt map

This page classifies every tracked prompt file. Active use was
derived from source references, not from filenames.

The repository tracks 107 prompt files. 29 are referenced from `solver/` or
`runtests.py`. The rest are historical or development material kept for
comparison.

## Used by the ordinary default

| path | loader | stage | role | inserted at run time | expected response |
|---|---|---|---|---|---|
| `prompts/stage1_instructions_full.txt` | `llmparse.load_prompts` | Stage 1 | translator | the input text | Stage-1 JSON units |
| `prompts/stage1_checklist_full.txt` | `llmparse.load_prompts` | Stage 1 | translator | none | part of the system prompt |
| `prompts/stage1_examples.txt` | `llmparse.load_prompts` | Stage 1 | translator | none | part of the system prompt |
| `prompts/stage2_instructions_full.txt` | `llmparse.load_prompts` | Stage 2 | translator | the Stage-1 units | Stage-2 logic JSON |
| `prompts/stage2_checklist_full.txt` | `llmparse.load_prompts` | Stage 2 | translator | none | part of the system prompt |
| `prompts/stage2_examples.txt` | `llmparse.load_prompts` | Stage 2 | translator | none | part of the system prompt |
| `prompts/critic/critic_system.txt` | `critic_pass.system_prompt` | critic | reviewer | English, Stage 1, Stage-2 logic | a verdict and findings |
| `prompts/graph/graph_stage2_instructions.txt` | `graph_stage2.sysprompt` | graph retranslation | translator | Stage-1 units | open-triple Stage-2 JSON |
| `prompts/graph/graph_stage2_checklist.txt` | `graph_stage2.sysprompt` | graph retranslation | translator | none | part of the system prompt |
| `prompts/graph/graph_stage2_examples.txt` | `graph_stage2.sysprompt` | graph retranslation | translator | none | part of the system prompt |

`stage_sanity_s2.py` also reads the Stage-2 instructions when it reports a
finding.

## Used by an explicit optional mode

| path | loader | selected by |
|---|---|---|
| `prompts/prenorm_full.txt` | `llmparse` | `-prenorm` |
| `prompts/graph/graph_onestage_instructions.txt` | `graph_stage2` | the one-stage graph configuration |
| `prompts/graph/graph_onestage_examples.txt` | `graph_stage2` | the one-stage graph configuration |
| `prompts/graph/graph_judge_system_sentences.txt` | `graph_judge` | `-graphbridge` |
| `prompts/graph/graph_judge_system_names_only.txt` | `graph_judge` | `-graphbridge` |
| `prompts/graph/graph_judge_system_lexical.txt` | `graph_judge` | `-graphbridge` |
| `prompts/graph/graph_holistic_system.txt` | `graph_judge` | `-graphbridge` |
| `prompts/graph/graph_grader_system.txt` | `graph_search` | `-graphbridge` |
| `prompts/graph/graph_lift_system.txt` | `graph_lift` | `-graphbridge` with lifting |
| `prompts/graph/graph_retranslate_suffix.txt` | `graph_lift` | `-graphbridge` |
| `prompts/dynamic_alignment/unifier_rules_v6_1_signed_system.txt` | `litbridge_prompts` | `-litbridge` |
| `prompts/combined_v3_instructions_full.txt` | `llmparse` | `-combined-instr` |
| `prompts/combined_v3_checklist_full.txt` | `llmparse` | `-combined-checklist` |
| `prompts/combined_v2_instructions_full.txt` | `llmparse` | `-combined-instr` |
| `prompts/combined_minimal_instructions_full.txt` | `llmparse` | `-combined-instr` |
| `prompts/combined_answerfirst_instructions_full.txt` | `llmparse` | `-combined-instr` |
| `prompts/combined_examples_pure.txt` | `llmparse` | `-combined-examples` |
| `prompts/combined_empty_examples.txt` | `llmparse` | `-combined-examples` |
| `prompts/combined_empty_checklist.txt` | `llmparse` | `-combined-checklist` |
| `prompts/folio_directanswer_instructions.txt` | `directanswer` | `-directanswer` |
| `prompts/folio_directanswer_instructions_noworld.txt` | `directanswer` | `-directanswer` |

## Experimental or development only

`prompts/critic/critic_system_v2.txt` is an alternative critic prompt. It was
measured and not adopted.

## Historical

`prompts/graph/v1/` holds a pinned earlier version of the graph prompt set.
`graph_stage2.PROMPT_DIR` points at `prompts/graph`, so the `v1` copies are not
loaded. The remaining `prompts/dynamic_alignment/` files belong to earlier
experiments and are kept for comparison.

`prompts/README.md` and `prompts/COMBINED_PROMPT_MEMO.md` are notes, not
prompts.

All four prompt files live in `prompts/`.  They are concatenated into system prompts by
`llmparse._compose_prompt`:

```
<instructions>

Examples:

<examples>
```

| File | Purpose |
|------|---------|
| `stage1_instructions_full.txt` | Full specification of Stage-1 output format; entity rules, type classification, splitting rules, adjective format, scope hints, state tracking, etc. |
| `stage1_checklist_full.txt` | Short procedural checklist appended to the Stage-1 system prompt |
| `stage1_examples.txt` | ~30 worked input→output examples for Stage 1; one per `---` separator |
| `stage2_instructions_full.txt` | Full specification of Stage-2 output format; entity handling (concrete/generic/kind/wh), quantification rules by ASU type, predicate inventory, property/relation selection rule |
| `stage2_checklist_full.txt` | Short procedural checklist appended to the Stage-2 system prompt |
| `prenorm_full.txt` | Pre-Stage-1 wording-normalisation prompt (`-prenorm`, [translation](../architecture/translation.md)) |
| `combined_*_instructions_full.txt`, `combined_examples_*.txt`, `combined_*_checklist_full.txt` | Combined single-stage constructions (`-combined-*`, [translation](../architecture/translation.md)); per-file descriptions in `prompts/README.md` |
| `folio_directanswer_instructions[_noworld].txt` | Direct-answer prompts (`-directanswer`, [translation](../architecture/translation.md)) |
| `stage2_examples.txt` | ~40 worked input→output examples for Stage 2; one per `----` separator |

**Editing the prompts** is the primary way to improve Stage-1 and Stage-2 accuracy.  Both
instruction files have version-pinned sections (`== 1. ... ==`, `== 2. ... ==`, etc.) that can be
updated independently.  The examples in both files follow the same section separator (`---` or
`----`) and can be added, removed or corrected freely.

An important constraint: **examples must be consistent with instructions**.  In particular:
- Every adjective/property that appears in an ASU text must appear in `"adjectives"` in Stage-1
  examples (including queries and rules).
- Stage-2 examples must use `has degree property` (not `has property`) when the word is in
  `adjectives`, and vice versa; never both.

---

## Related documentation

- [Translation](../architecture/translation.md)
- [Translation and compilation code](translation-and-validation.md)
