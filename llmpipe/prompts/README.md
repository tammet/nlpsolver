# prompts/

LLM system prompts used by the two-stage parser (`solver/llmparse.py`).
Stage 1 converts English text into a JSON list of "Atomic Semantic
Units" (ASUs); Stage 2 converts that ASU JSON into the predicate-logic
JSON that the rest of the pipeline clausifies and feeds to the prover.

## Files

Each stage uses three files, all loaded once per process and cached:

| File | Role |
|------|------|
| `stage1_instructions_full.txt` | Stage-1 specification (entity IDs, ASU types, scope/quantifier rules, modal-mode table, etc.) |
| `stage1_examples.txt`          | Worked Stage-1 examples (English → ASU JSON) |
| `stage1_checklist_full.txt`    | Short procedural checklist appended at the very end |
| `stage2_instructions_full.txt` | Stage-2 specification (predicate inventory, quantifier mapping per ASU type, modal classifiers, $defq encoding) |
| `stage2_examples.txt`          | Worked Stage-2 examples (ASU JSON → logic JSON) |
| `stage2_checklist_full.txt`    | Short procedural checklist appended at the very end |

The checklists are kept separate so the most error-prone rules can be
re-emphasised at the bottom of the prompt without bloating the main
instructions.

## How a system prompt is assembled

`solver/llmparse.py::_compose_prompt` concatenates the three files in
this order (with a single fixed separator between instructions and
examples, and a blank line before the checklist):

```
<instructions_full.txt>

Examples:

<examples.txt>

<checklist_full.txt>
```

The resulting string becomes the `system` prompt sent to the LLM.  The
`user` prompt is just the input text (Stage 1) or the Stage-1 JSON
(Stage 2).  See `_compose_prompt` and `parse_text` in
`solver/llmparse.py` for the exact wiring.

## Combined single-stage prompts

These drive the experimental ONE-call mode: the LLM reads English and
emits the Stage-2 logic JSON directly, working the ASU analysis out "in
the head" without printing it.  Selected explicitly on the command line
(`solve.py` / `runtests.py`):

```
-combined-instr FILE [-combined-examples FILE] [-combined-checklist FILE]
```

A combined system prompt is assembled by the same `_compose_prompt`
(instructions + examples + checklist); examples and checklist are
optional.

Instruction constructions (one per file, increasing rework of the
two-stage texts):

| File | Construction |
|------|--------------|
| `combined_minimal_instructions_full.txt` | `minimal` — cheapest: output-format signature and core conventions only (~10 KB), no per-case rules |
| `combined_v2_instructions_full.txt`      | `v2` — structural condensation into two sequential PART blocks with the output contract hoisted to the top; rule wording unchanged |
| `combined_v3_instructions_full.txt`      | `v3` — one continuously numbered spec (§0–§23) with the Step-1 ANALYSE and Step-2 ENCODE rules interleaved per phenomenon under shared topic banners |
| `combined_answerfirst_instructions_full.txt` | `answer-first` — the model first decides the answer, then encodes premises + question (~13 KB; FOLIO experiment F4) |

Earlier/alternate constructions that were never used in a shipped run
(`v1`, `direct`, and the ASU-showing examples) have been moved to `archive/`.

The matching examples file (`combined_examples_pure.txt` = 60 worked
English → logic examples) and per-construction checklists
(`combined_*_checklist_full.txt`) are passed via `-combined-examples` /
`-combined-checklist`.

## Other special-purpose prompts

| File | Role |
|------|------|
| `prenorm_full.txt` | pre-Stage-1 normalization (flag `-prenorm`): rewrites the input English so every distinct entity/property/relation is always worded identically before parsing |
| `folio_directanswer_instructions.txt` | direct-answer mode (`-directanswer FILE`): one LLM call answers True/False/Unknown from premises + conclusion, no logic and no prover; used for the FOLIO reference runs |
| `folio_directanswer_instructions_noworld.txt` | short variant of the above instructing the model to reason from the stated premises only, without world knowledge |
