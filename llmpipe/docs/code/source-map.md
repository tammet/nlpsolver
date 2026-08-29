# Source map

Every tracked runtime module, once, with the page that describes
its subsystem. The one-line summaries are generated from the
modules themselves by `tools/source_map.py`.

## Entry points

| file | what it does |
|---|---|
| `solve.py` | one passage to an answer; the library and command-line entry |
| `test.py` | small readable contributor checks with one provider |
| `runtests.py` | research evaluation and structured result records |
| `examine.py` | per-provider debug logs for one case id |

## Runtime modules

### Entry points and configuration

Described in [orchestration](orchestration.md).

| module | what it does |
|---|---|
| `solver/solve.py` | The pipeline: option resolution, stage scheduling, stopping and accounting |
| `solver/solve_display.py` | Terminal presentation of pipeline stages, summaries, logic and proofs |
| `solver/globals.py` | Configuration and other globals for the nlpsolver |
| `solver/utils.py` | Small utilities for the nlpsolver |
| `solver/pretty.py` | Pretty-printing for stage-1 ASU JSON, stage-2 logic JSON, and GK clause lists |
| `solver/cache.py` | The cache machine of nlpsolver |
| `solver/clause_trace.py` | Provenance for the clause list actually handed to the prover |

### Model calls, parsing and validation

Described in [translation and validation](translation-and-validation.md).

| module | what it does |
|---|---|
| `solver/llmcall.py` | LLM API call functions for the nlpsolver: GPT, Claude, Gemini, DeepSeek |
| `solver/llmparse.py` | Two-stage LLM parser: English -> Stage-1 ASUs -> Stage-2 logic |
| `solver/stage_sanity.py` | Sanity-check facade: it re-exports the Stage-1 and Stage-2 check API from the four modules below |
| `solver/stage_sanity_core.py` | Shared types/helpers for the Stage-1/Stage-2 sanity checks |
| `solver/stage_sanity_s1.py` | Stage-1 ASU-shape sanity checks (see stage_sanity.py facade) |
| `solver/stage_sanity_s2.py` | Stage-2 logic-shape sanity checks + dispatch (see stage_sanity.py facade) |
| `solver/stage_sanity_guards.py` | Cross-stage unsatisfiable-guard + split-mode id-coverage checks |
| `solver/directanswer.py` | Direct-answer mode for the llmpipe solver |

### Logic compilation

Described in [logic compilation](logic-compilation.md).

| module | what it does |
|---|---|
| `solver/logconvert.py` | Logic conversion for the llm-based nlpsolver |
| `solver/lc_encoding.py` | Single source of truth for encoding-flag resolution |
| `solver/lc_packages.py` | Per-ASU-package processing for the llm-based nlpsolver |
| `solver/lc_rewrites.py` | Pre-clausification formula rewrites for the llm-based nlpsolver |
| `solver/lc_repairs.py` | Pre-clausification structural repairs: id hoisting, misnested-implies repair, the self-defeating-conditional engine, the -s2split off-inventory predicate rename, and @definite tag stripping |
| `solver/lc_reference.py` | Reference-preserving repairs for Stage-1/Stage-2 mismatches |
| `solver/lc_clausify.py` | FOL-to-CNF clausification for the llm-based nlpsolver |
| `solver/lc_ctxt.py` | $ctxt context injection and time-wrapper stripping for the llm-based nlpsolver |
| `solver/lc_questions.py` | Question encoding and population fact injection for the llm-based nlpsolver |
| `solver/lc_query_guards.py` | Query-body simplification: phantom isa-guard stripping and "what"-question population-fact generation |
| `solver/lc_sets.py` | Set/counting programmatic conversion for the llm-based nlpsolver |
| `solver/lc_coarse.py` | The event folds that produce the flat and compact relational encodings |
| `solver/lc_entity_isa.py` | Taxonomy `isa` enrichment from Stage-1 entity annotations, and the typed-Skolem merge |
| `solver/lc_finalize.py` | Strict/abstract clause finalizer for the -abstract* presets |
| `solver/treewalk.py` | Shared formula-tree traversals for the clause list |

### Proof shortening

The two reversible rewrites the canonical theory attempts;
see [proof shortening](../architecture/proof-shortening.md) for
what each does and [logic compilation](logic-compilation.md) for
where they run in the compiler.

| module | what it does |
|---|---|
| `solver/lc_davidson2.py` | Reversible event compression: the exact event-spine rewrite, internal name davidson2 |
| `solver/lc_existfold_v2.py` | Repeated part-witness compression: the narrow existential collapse, internal name existfold2 |
| `solver/lc_existfold.py` | The legacy existential-attribute collapse, kept for reproduction |

### Post-clausification passes

Described in [logic compilation](logic-compilation.md).

| module | what it does |
|---|---|
| `solver/lc_post_normalize.py` | Normalising / repair passes for the post-clausification clause list |
| `solver/lc_post_have.py` | Possessive `have` inference and the `have` to `has part` bridges |
| `solver/lc_post_reify.py` | Reification passes for the post-clausification clause list |
| `solver/lc_post_inject.py` | Dynamic axiom injection passes for the post-clausification clause list |
| `solver/lc_inject_synonyms.py` | KB-driven soft-synonym + exclusion/mutex axiom injectors |
| `solver/lc_inject_scan.py` | Shared clause-scan helpers for the dynamic axiom injectors |
| `solver/lc_post_population.py` | Population-fact extraction and negative-witness polarity walks, split out of lc_post_normalize.py |
| `solver/lc_post_una.py` | Post-clausification UNA (unique-name assumption) wrapping |
| `solver/semnormalize.py` | Semantic normalisation of GK clause lists |
| `solver/axiom_vocab.py` | Axiom vocabulary extraction and caching |

### Prover and proofs

Described in [proof processing](proof-processing.md).

| module | what it does |
|---|---|
| `solver/prover.py` | Prover calling and prover result conversion parts of nlpsolver ----------------------------------------------------------------- Copyright 2022 Tanel Tammet (tanel.tammet@gmail.com) Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with the License |
| `solver/procproofs.py` | Proof result processing for the llm-based nlpsolver |
| `solver/proof_answer_select.py` | Answer selection and filtering for the llm-based nlpsolver |
| `solver/proof_answer_format.py` | Answer formatting for the llm-based nlpsolver |
| `solver/proof_explain.py` | Proof explanation formatter for the llm-based nlpsolver |
| `solver/proof_render.py` | Proof rendering facade — re-exports from proof_utils, proof_english, proof_logic |
| `solver/proof_utils.py` | Shared proof-rendering helpers: entity naming, Skolem resolution and clause labelling |
| `solver/proof_english.py` | Atom-to-English rendering for proof explanations |
| `solver/proof_terms.py` | Term rendering for proof explanations: counts, sets, definite descriptions and measurements |
| `solver/proof_logic.py` | Traditional and JSON logic syntax rendering for proof display |
| `solver/entity_map.py` | Entity display-name map built from stage-1 JSON. Entry point: build_entity_map(s1_json) Returns a flat dict {entity_id: display_name, url: display_name} that maps every entity identifier (local id string or Wikipedia URL) to the best human-readable display name for that entity |
| `solver/linguistics.py` | Pure linguistic utility functions for English rendering |

### Fallbacks, critic and acceptance

Described in [retries and abstraction](retries-and-abstraction.md).

| module | what it does |
|---|---|
| `solver/fallback_norm.py` | The normalization fallback (`-fallback_norm`) |
| `solver/fallback_hyp.py` | The hypothetical-reading fallback (`-fallback_hyp`) |
| `solver/critic_pass.py` | The critique pass: one LLM call that audits the initial attempt's translation |
| `solver/critic_render.py` | What the critic reads: the case, its Stage 1 and its Stage 2, compacted |
| `solver/retrans_accept.py` | Proof-local acceptance checks for critic and graph retranslations |

### Graph retranslation and graph bridges

Described in [retries and abstraction](retries-and-abstraction.md).

| module | what it does |
|---|---|
| `solver/graph_p0.py` | Layer 1 of the graph mechanism: the retranslation, and one gk call |
| `solver/graph_stage2.py` | The graph Stage 2: a Stage-1-driven Stage 2 whose content atoms are triples |
| `solver/graph_compile.py` | Open triples to GK clauses, under one frozen converter configuration |
| `solver/graph_inventory.py` | What names the graph theory holds, where each occurs, and what it needs |
| `solver/graph_pairs.py` | Which name pairs are worth judging, and which code refuses outright |
| `solver/graph_judge.py` | Ask for a direction, then let code write the bridge |
| `solver/graph_search.py` | One gk submission per bridge set over the graph theory, the minimal sets, and the grading that follows |
| `solver/graph_lift.py` | Re-expressing a graph proof's used units and rules over the ordinary atoms |
| `solver/graph_procedure.py` | One case through the open-relation graph route, end to end |
| `solver/graph_ablation.py` | One switch per v2 fix, so a fix can be reverted alone and measured alone |

### Literal bridges

Described in [retries and abstraction](retries-and-abstraction.md).

| module | what it does |
|---|---|
| `solver/litbridge_atoms.py` | The atoms a bridge may be built from, and how they are displayed |
| `solver/litbridge_rules.py` | The rule grammar, and the two channels that build rules in code |
| `solver/litbridge_compile.py` | A rule becomes gk clauses, built from the atoms that were displayed |
| `solver/litbridge_chain.py` | Which rules can start, on what, and in what order they are offered |
| `solver/litbridge_prompts.py` | What the model is asked: the system prompts and the case messages |
| `solver/litbridge_procedure.py` | One case, from a translation to a minimal set of bridges that prove it |
| `solver/litbridge_converter.py` | The converter route: a proposed rule becomes clauses beside the theory |
| `solver/litbridge_grader.py` | The per-cited-rule grader for the literal bridge (`MODE`, below) |

### Generated lexical data

Described in [generated data](../development/generated-data.md).

| module | what it does |
|---|---|
| `solver/data_canonicals.py` | Canonical word forms for semantic normalisation |
| `solver/data_antonyms.py` | Directional antonym pairs for semantic normalisation |
| `solver/data_synonyms.py` | Soft synonym pairs for dynamic axiom injection |
| `solver/data_exclusions.py` | Mutual-exclusion groups for dynamic axiom injection |
| `solver/data_names.py` | First-name and gendered-noun gender tables, generated from `mkdata/` |

## Supporting files

| file | what it holds |
|---|---|
| `axioms_std.js` | the standard background axioms handed to GK |
| `solver/gradables.txt` | the gradable-property whitelist |
| `solver/comparable_adjectives.txt` | adjectives that admit a comparative |

`mkdata/` holds the generators for the five `data_*.py` modules;
see [generated data](../development/generated-data.md).
`tools/` holds test fixtures, experiment harnesses and the
documentation checkers. They are development scripts, not part of
the shipped pipeline.

## Related documentation

- [Code guide](README.md)
- [Prompt map](prompt-map.md)
- [Pipeline](../architecture/pipeline.md)
- [Extending](../development/extending.md)
