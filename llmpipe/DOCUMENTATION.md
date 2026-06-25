# llmpipe — Developer Documentation

`llmpipe` is a pipeline that converts natural-language text into first-order predicate logic using
LLMs, then hands the logic to the `gk` theorem prover to answer questions.  This document explains
the pipeline end-to-end, describes every source file, and gives a thorough overview of the logic
representation so that a developer or LLM can quickly start extending or modifying the system.

---

## Table of Contents

1. [Quick start](#1-quick-start)
2. [Pipeline overview](#2-pipeline-overview)
3. [Repository layout](#3-repository-layout)
4. [Representation overview](#4-representation-overview)
   - 4.1 [Stage-1 ASU JSON](#41-stage-1-asu-json)
   - 4.2 [Stage-2 logic JSON](#42-stage-2-logic-json)
   - 4.3 [GK clause list](#43-gk-clause-list)
   - 4.4 [The adjectives field](#44-the-adjectives-field)
   - 4.5 [The $ctxt context term](#45-the-ctxt-context-term)
   - 4.6 [Defeasible reasoning and $block](#46-defeasible-reasoning-and-block)
5. [Source files](#5-source-files)
   - 5.1 [solve.py](#51-solvepy)
   - 5.2 [llmparse.py](#52-llmparsepy)
   - 5.3 [llmcall.py](#53-llmcallpy)
   - 5.4 [logconvert.py and supporting modules](#54-logconvertpy-and-supporting-modules)
   - 5.5 [lc_clausify.py](#55-lc_clausifypy)
   - 5.6 [lc_questions.py](#56-lc_questionspy)
   - 5.7 [lc_sets.py](#57-lc_setspy)
   - 5.8 [procproofs.py + proof_answer_select.py + proof_answer_format.py](#58-procproofspy--proof_answer_selectpy--proof_answer_formatpy)
   - 5.9 [Proof rendering modules](#59-proof-rendering-modules) — `proof_render`, `proof_utils`, `proof_english`, `proof_logic`
   - 5.10 [proof_explain.py](#510-proof_explainpy)
   - 5.11 [prover.py](#511-proverpy)
   - 5.12 [pretty.py](#512-prettypy)
   - 5.13 [cache.py](#513-cachepy)
   - 5.14 [globals.py](#514-globalspy)
   - 5.15 [utils.py](#515-utilspy)
   - 5.16 [linguistics.py](#516-linguisticspy)
   - 5.17 [stage_sanity.py](#517-stage_sanitypy)
6. [Prompt files](#6-prompt-files)
7. [Key algorithms in logconvert.py and lc_clausify.py](#7-key-algorithms-in-logconvertpy-and-lc_clausifypy)
   - 7.1 [Package extraction](#71-package-extraction)
   - 7.2 [FOL to CNF clausification](#72-fol-to-cnf-clausification)
   - 7.3 [Defeasible expansion](#73-defeasible-expansion)
   - 7.4 [Context injection ($ctxt)](#74-context-injection-ctxt)
   - 7.5 [Gradable property normalisation](#75-gradable-property-normalisation)
   - 7.6 [Population facts](#76-population-facts)
   - 7.7 [Stage-2 rewrites and modifications](#77-stage-2-rewrites-and-modifications)
   - 7.8 [Stage sanity checks and corrective retry loop](#78-stage-sanity-checks-and-corrective-retry-loop)
   - 7.9 [Confidence and uncertainty handling](#79-confidence-and-uncertainty-handling)
   - 7.10 [WH-question handling](#710-wh-question-handling)
   - 7.11 [Proof deduplication](#711-proof-deduplication)
   - 7.12 [Typed Skolem constants](#712-typed-skolem-constants)
   - 7.13 [Entity UNA via `#:` prefix](#713-entity-una-via--prefix)
   - 7.14 [Frame persistence and motion blocking](#714-frame-persistence-and-motion-blocking)
8. [Configuration and options](#8-configuration-and-options)
9. [The mkdata toolkit and solver integration](#9-the-mkdata-toolkit-and-solver-integration)
   - 9.1 [What mkdata produces](#91-what-mkdata-produces)
   - 9.2 [Solver runtime files](#92-solver-runtime-files)
   - 9.3 [Solver integration](#93-solver-integration)
   - 9.4 [Full build pipeline](#94-full-build-pipeline)
   - 9.5 [Spatial and temporal preposition handling](#95-spatial-and-temporal-preposition-handling)
10. [Extending and modifying the pipeline](#10-extending-and-modifying-the-pipeline)
11. [Event-encoding and abstraction machinery](#11-event-encoding-and-abstraction-machinery)
12. [Alternative parsing modes: prenorm, combined single-stage, direct answer, split Stage 2](#12-alternative-parsing-modes-prenorm-combined-single-stage-direct-answer-split-stage-2)

---

## 1. Quick start

All scripts are run from the `llmpipe/` directory.

```bash
# Answer a question
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"

# Show every intermediate representation
python3 solver/solve.py -debug -logic -prover -explain "..."

# Use a specific LLM
python3 solver/solve.py -llm claude -version claude-sonnet-4-6 "..."

# Parse to logic only, do not call the prover
python3 solver/solve.py -nosolve "..."

# Call an LLM directly (no pipeline)
python3 ask.py "What is the capital of France?"
python3 ask.py -llm claude -p prompt.txt -f input.txt

# Run the test suite
python3 test.py
python3 test.py tests/tests_core.py -llm claude
```

---

## 2. Pipeline overview

```
English text
    │
    ▼
llmparse.parse_text()              [solver/llmparse.py]
    │   Stage 1: English → ASU JSON
    │   Stage 2: ASU JSON → logic JSON
    │   (LLM responses cached in cache.db)
    │
    ▼
logconvert.rawlogic_convert()      [solver/logconvert.py + lc_clausify.py + lc_questions.py]
    │   Logic JSON → GK clause list
    │   FOL → CNF, Skolemisation, defeasible expansion,
    │   context injection, gradable normalisation
    │
    ▼
prover.call_prover()               [solver/prover.py]
    │   Writes clause list to a temp file
    │   Runs the gk binary as a subprocess
    │   Returns raw JSON result string
    │
    ▼
procproofs.process_proof()         [procproofs.py → proof_answer_select.py + proof_answer_format.py + proof_render.py + proof_explain.py]
    │   Parses prover JSON
    │   Selects best proof, formats answer
    │   Optionally renders step-by-step explanation
    │
    ▼
Answer string
```

The top-level entry point for library use is `english_to_answer(text, options)` in `solve.py`.
The command-line entry point is `main()` in the same file.

---

## 3. Repository layout

```
llmpipe/
├── solver/              Core pipeline modules
│   ├── solve.py         CLI entry point; english_to_answer() library function
│   ├── llmparse.py      Two-stage LLM parser
│   ├── stage_sanity.py  Stage-1/2 sanity checks + corrective-retry (façade over stage_sanity_{core,s1,s2,guards}.py)
│   ├── llmcall.py       LLM API wrapper (GPT / Claude / Gemini / DeepSeek, no SDK)
│   ├── logconvert.py    Stage-2 JSON → GK clause list (orchestration)
│   ├── lc_encoding.py   EncodingConfig resolver — the single source of truth for encoding gates
│   ├── lc_repairs.py    Pre-clausification structural repairs (id hoist, SDC engine, -s2split rename, @definite strip)
│   ├── lc_query_guards.py  Query-body simplification (phantom isa-guard strip, "what"-population)
│   ├── lc_entity_isa.py    Entity-category isa enrichment + typeonly-Skolem merge
│   ├── lc_finalize.py      Strict/abstract clause finaliser (finalize_strict_clauses)
│   ├── lc_coarse.py     Event folds (flat/flatroles/davidson); coarsen_events
│   ├── lc_existfold.py  Existential-attribute collapse (-existfold)
│   ├── lc_packages.py   Per-ASU-package processing (extract_package_ctx, convert_id_package, _process_question/_assertion)
│   ├── lc_rewrites.py   Pre-clausification formula rewrites
│   ├── lc_ctxt.py       $ctxt injection, time handling, fresh variables
│   ├── lc_post_normalize.py Post-clausification: fix Stage-2 errors and normalise predicate forms
│   ├── lc_post_have.py      Post-clausification: possessive have / have↔has_part bridges
│   ├── lc_post_population.py Post-clausification: population-fact extraction + neg-witness walks
│   ├── lc_post_reify.py     Post-clausification: $theof1 / $measure_of reification
│   ├── lc_post_inject.py    Post-clausification: bridge/verb/world axiom injectors (re-exports the synonym injectors)
│   ├── lc_inject_synonyms.py KB-driven soft-synonym + exclusion/mutex injectors
│   ├── lc_inject_scan.py    Shared clause-scan helpers for the injectors
│   ├── lc_post_una.py       Post-clausification: #: UNA wrapping of Stage-1 entities
│   ├── treewalk.py     Shared formula-tree traversal (walk_result_atoms)
│   ├── lc_clausify.py   FOL → CNF clausification
│   ├── lc_questions.py  Wh-question encoding and population facts
│   ├── lc_sets.py       Set/counting: $setof rewriting, membership axioms, element instantiation
│   ├── procproofs.py    Prover output → answer string (orchestrator)
│   ├── proof_answer_select.py  Answer selection/filtering: tiers, measure pref, dedup
│   ├── proof_answer_format.py  Answer rendering: who/what/where/when/bool formatters
│   ├── proof_render.py  Proof rendering facade (re-exports from proof_utils/english/logic)
│   ├── proof_utils.py   Entity naming, Skolem resolution, render context
│   ├── proof_english.py Atom/clause → English rendering (table-driven)
│   ├── proof_terms.py   Term rendering ($count/$setof/$theof1/$measure → English)
│   ├── proof_logic.py   Traditional/JSON logic syntax rendering
│   ├── proof_explain.py Step-by-step proof explanation formatter
│   ├── linguistics.py   Pure English heuristics (articles, conjugation, gerunds)
│   ├── prover.py        gk binary interface
│   ├── pretty.py        JSON pretty-printer (Style B)
│   ├── cache.py         SQLite cache for LLM responses and prover results
│   ├── semnormalize.py  Semantic normalization (antonym folding + canonical substitution)
│   ├── axiom_vocab.py   Axiom file vocabulary extraction and caching
│   ├── data_canonicals.py  (generated) Tier A rewrite dict (~752 entries)
│   ├── data_antonyms.py    (generated) ANTONYMS dict — directional `{word: antonym}` pairs (~311 entries)
│   ├── data_synonyms.py    (generated) Soft synonym index (~12K words)
│   ├── data_exclusions.py  (generated) Exclusion groups + index
│   ├── data_names.py       (generated) Proper-name gender / type lookup
│   ├── globals.py       Options dict and file paths
│   ├── utils.py         debug_print, clause_list_to_json
│   └── gradables.txt    Whitelist of gradable adjectives (~400 entries)
│
├── prompts/             LLM system prompts (loaded by llmparse.py)
│   ├── stage1_instructions_full.txt
│   ├── stage1_checklist_full.txt
│   ├── stage1_examples.txt
│   ├── stage2_instructions_full.txt
│   ├── stage2_checklist_full.txt
│   └── stage2_examples.txt
│
├── tests/               Test cases
│   ├── tests_core.py    Core test suite ([text, expected_answer] pairs)
│   ├── tests_medium_core.py
│   └── tests_small.py
│
├── mkdata/              Synonym/antonym data builder (standalone, own venv)
│   └── README.md        Full documentation for mkdata
│
├── axioms_std.js        Default background-knowledge axioms for gk (persistence,
│                        event-to-relation bridges, movement/transfer results,
│                        give/receive perspective bridges, transitivity, degree entailments)
├── cache.db             SQLite cache (auto-created; not committed)
│
├── ask.py               Direct LLM call tool (uses solver/llmcall.py)
├── test.py              Test runner (single-LLM, resumable text output)
├── runtests.py          Batch runner — every case × N LLMs in parallel, one JSON per (case, llm)
├── checkprompt.py       Validate JSON in prompt example files
├── README.md            User-facing overview and installation
├── DOCUMENTATION.md     Full developer documentation (this file)
├── ENCODINGS.md         Stage-1 / Stage-2 / GK clause-list encoding reference
├── DEBUGGING.md         Debugging workflow and failure taxonomy
├── PROOF_RENDERING.md   How proofs are rendered as English explanations
└── CLAUDE.md            Guidance for Claude Code agents working in this repo
```

The repo-root `smoketest.py` (one level above `llmpipe/`) sanity-checks the
install — see `README.md`.

---

## 4. Representation overview

The pipeline uses three successive JSON representations.  Understanding all three is essential for
any work on the system.  See `ENCODINGS.md` for a detailed encoding reference with examples.

### 4.1 Stage-1 ASU JSON

**Produced by:** Stage-1 LLM call
**Consumed by:** Stage-2 LLM call and `logconvert.py`

Stage 1 converts English into a list of *sentence packages*, each containing one or more *Atomic
Semantic Units* (ASUs).  Each ASU is one minimal proposition that can be true or false.

```json
[
  {
    "raw": "Birds can fly, but penguins cannot.",
    "units": [
      {
        "unit_id": "S1",
        "text": "Birds can fly.",
        "type": "normal_rule",
        "entities": [{"id":"birds","type":"generic"}],
        "confidence": 0.95
      },
      {
        "unit_id": "S2",
        "text": "Penguins cannot fly.",
        "type": "strict_rule",
        "entities": [{"id":"penguins","type":"generic"}]
      }
    ]
  }
]
```

**ASU `type` values:**

| type | Meaning |
|------|---------|
| `real` | Timeless encyclopedic fact about a specific named entity |
| `situation` | Concrete event or state in a narrative (has tense) |
| `strict_rule` | Definition or law that holds without exception (`forall`/`implies`) |
| `normal_rule` | Defeasible default behaviour (`normally`, `typically`) |
| `query` | A question to be answered |

**Entity object fields:**

| field | meaning |
|-------|---------|
| `id` | Primary symbol — used as-is in Stage 2 (never normalise) |
| `type` | `"concrete"` (specific instance) or `"generic"` (class/kind) |
| `url` | Wikipedia URL for named entities; Stage 2 uses this instead of `id` |
| `scope` | For generics: `"dependent"` (per-subject existential), `"global"` (shared existential), `"kind"` (substance constant — treated as a constant, not a variable) |
| `text` | Present only for relational-role nouns and attribute entities (e.g. `"weight"`, `"sister"`); used to identify the kind of role, not for naming |
| `wh_placeholder` | `true` for the fresh variable introduced for `who/what/where/when` questions |

**Key optional ASU fields:**

| field | meaning |
|-------|---------|
| `adjectives` | List of `[word, intensity, relclass]` for every adjective in the ASU; `intensity` is `"none"`, `"low"` (slightly), or `"high"` (very/extremely); `relclass` is the comparison class (`"person"`, `"car"`, `"entity"` if generic, `"none"` if non-gradable) |
| `pre_state` / `next_state` | World constants for state tracking (`"W0"`, `"W1"`, …) |
| `time` | `"past"`, `"present"`, `"future"`, a year string, or a structured list `["relative", offset, anchor]` |
| `time_prep` | Temporal preposition when `time` is an explicit value: `"during"`, `"on"`, `"before"`, etc. |
| `state_tense` | `"past"`, `"present"`, `"future"` — grammatical tense when `time` holds an explicit value instead of a tense.  Generates `is_past_world(W)` for `"past"`. |
| `location` | Entity id of the location |
| `confidence` | Float 0–1 (omit for 1.0); affects `@p` metadata in Stage 2 |
| `mental_holder` / `mental_attitude` / `epistemic_force` / `attitude_target` | For propositional attitudes (`knows that`, `believes that`) |
| `definites` | List of `[REL, VALUE_ID, ARG_ID]` for definite descriptions (`"the handle of the fork"`).  Triggers `$theof1` function term rewrite in logconvert (see §7 post-clausification table). |

### 4.2 Stage-2 logic JSON

**Produced by:** Stage-2 LLM call
**Consumed by:** `logconvert.rawlogic_convert()`

Stage 2 translates each ASU into first-order predicate logic encoded as nested JSON lists.  The
top-level structure is always:

```json
["and", ["@id","S1", PACKAGE], ["@id","S2", PACKAGE], ...]
```

Each `PACKAGE` is one of:

```
["holds", WORLD, FORMULA]          -- assertion anchored to a world constant
["question", FORMULA]              -- yes/no question
["ask", VAR, FORMULA]              -- wh-question; VAR is the answer variable
["and", PACKAGE, ["@p","Sx",P]]    -- package with confidence P (0–1 float)
```

`FORMULA` is a standard first-order formula in JSON:

```json
["forall","X", ["implies", ["isa","bird","X"],
  ["normally", ["exists","E", ["and",
    ["isa","activity","E"],
    ["has type","E","fly"],
    ["has actor","E","X"],
    ["capability","E"]]]]]]
```

**Predicate inventory** (closed whitelist — no invented predicates):

| Category | Predicates |
|----------|-----------|
| Logical | `and`, `or`, `xor`, `not`, `implies`, `forall`, `exists`, `=`, `<`, `>` |
| Core | `isa TYPE ENTITY`, `has property PROP ENTITY`, `have OWNER OWNED`, `has part WHOLE PART`, `is rel2 REL E1 E2` |
| Gradable | `has degree property PROP ENTITY DEGREE RELCLASS`, `has degree rel2 REL E1 E2 DEGREE RELCLASS` |
| Events | `isa "activity" E`, `has type E VERB`, `has actor E ENTITY`, `has target E ENTITY`, `has location E ENTITY PREP`, `has instrument E ENTITY`, `has manner E MANNER`, `has direction E DIR`, `has time E TIME PREP`, `has content E1 E2` (two-event reification) |
| Modal classifiers (arity 1, last conjunct of event "and") | `typical E` (habitual), `capability E`, `necessity E`, `obligation E`, `volition E`, `intention E`, `expectation E`, `speech_act E`; plus pipeline-injected `actuality E` for real events (Stage 2 never emits this) |
| World | `holds W F`, `next W1 W2`, `before W1 W2` (axiom-derived), `state time W T`, `state location W L` |
| Defeasible | `normally FORMULA` |
| Mental (epistemic only) | `kb K HOLDER ATTITUDE W`, `kb force K FORCE`, `kb holds K FORMULA`, `kb says K1 K2 FORMULA` — reserved for `knows that` / `believes that`; all hopes / wants / intends / tells migrate to `actions[mode=…]` |
| Sets | `$setof VAR [and CONDITIONS]`, `$setof VAR SET_ID [and CONDITIONS]`, `$count SETOF_TERM`, `member ENTITY SETOF_TERM`, `isa "set" S`, `is set of TYPE S` |
| Definite functions | `$theof1 TYPE SUBJECT CTXT` — canonical function term for "the TYPE of SUBJECT" (generated by logconvert from `definites`).  For measurements, Stage 2 outputs `$measure_of ATTR OBJ WORLD` (ground) with `$measure NUMBER UNIT`; pipeline converts to `$list NUM "#:UNIT"` in canonical units. |
| Traceability | `@id "Sx" FORMULA`, `@p "Sx" P`, `@definite "Sx" W REL ARG VALUE` |
| Questions | `question F`, `ask VAR F` |

Modal information is carried exclusively by the arity-1 classifier
predicates listed above.  Role / world / time information lives on the
event's other atoms (which do carry `$ctxt`).

The arity-1 `actuality E` marker for real events is **pipeline-injected**, not
emitted by Stage 2;
`lc_rewrites.inject_actuality` appends `["actuality", E]` to every
Davidsonian event lacking one of the eight Stage-2 modal classifiers
and not appearing as the inner argument of `has_content`.  The
`axioms_std.js` §5.1 capability bridge is gated on `actuality(E)` so it
fires only on real events.  `actuality` is hidden from English rendering.

`axioms_std.js` §5.2 — factive content bridges for assertive
speech-act verbs.  For each verb V in {say, claim, report, state,
announce}, a defeasible axiom `speech_act(E1) ∧ has_content(E1,E2) ∧
has_type(E1,V,Ct) → actuality(E2)` (confidence 0.9, with `$block`
guard on `¬actuality(E2)`) makes the inner content event actual.
Per-verb gating keeps directive (ask/order), commissive
(promise/threaten), and dual-sense `tell` out of scope.

**Predicate selection rule for adjectives** (mandatory):

- If a word appears in `ASU.adjectives` → use `has degree property` (or `has degree rel2` for
  binary relations).  Take DEGREE and RELCLASS from the matching adjectives entry.  Do NOT also
  emit `has property` / `is rel2`.
- If a word does NOT appear in `ASU.adjectives` → use `has property` / `is rel2`.  Never both.

**Variable naming conventions:**

| Role | Names |
|------|-------|
| Entity | `X`, `Y`, `Z`, `X1`, `Y1`, … |
| Event | `E`, `E1`, `E2`, … |
| Set | `S`, `S1`, `S2`, … |
| Knowledge base | `K_Sx` |
| Count | `N` |
| Scalar value | `V` |

### 4.3 GK clause list

**Produced by:** `logconvert.rawlogic_convert()`
**Consumed by:** `prover.call_prover()`

The GK prover expects a JSON array of clause dicts:

```json
[
  {"@name": "sent_S1", "@logic": ["isa","elephant","John 1"]},
  {"@name": "sent_S2", "@logic": [
    ["-isa","elephant","?:X"], ["isa","animal","?:X"]
  ]},
  {"@name": "sent_S3", "@question": ["isa","animal","John 1"]}
]
```

Each dict has exactly one content key: `@logic` for assertions, `@question` for the query.

**Clause formats:**

- Single atom: `["pred", arg1, arg2, ...]`
- Disjunction: `[["pred1",...], ["pred2",...], ...]` — represents `pred1 OR pred2 OR ...`
- Negated atom: `["-pred", arg1, ...]` — the `-` prefix negates the predicate

**Variables:** any string beginning with `?:` (e.g. `"?:X"`, `"?:Fv3"`).  In GK, all free
variables in a clause are implicitly universally quantified.  Existential quantifiers are
eliminated by Skolemisation during `rawlogic_convert`.

**Defeasible atoms:** `["$block", PRIORITY, ["$not", HEAD]]`
These appear alongside the rest of the clause literals.  The prover uses the priority to decide
which default conclusions can be blocked by more specific rules.  Priority has the form
`["$", CLASS, N]` where CLASS is the subject class (e.g. `"bird"`) and N is an integer.

**Context atom:** `["$ctxt", TENSE, WORLD, LOCATION, KNOWER]`
Appended to eligible predicate atoms (see §4.5).  All four components are either concrete
constants or fresh free variables.

**Confidence:** Some clause dicts also carry `"@confidence": 0.8` (from `@p` metadata or
Stage-1 `confidence`).  The value is an **evidence** score in [−1, 1] (probability `p`
mapped via `2p − 1`) and is distributed across the ASU's clauses using the three-tier
anchor scheme documented in §7.9.

### 4.4 The adjectives field

All adjectives/properties in Stage-1 output carry an `"adjectives"` field:

```json
"adjectives": [["tall","none","person"], ["fast","none","car"], ["red","none","none"]]
```

Each entry is `[word, intensity, relclass]`:

- **word** — the adjective or relational phrase (e.g. `"close to"`)
- **intensity** — `"none"` (plain), `"low"` (slightly/a bit), `"high"` (very/extremely)
- **relclass** — the comparison class; use `"none"` for non-gradable adjectives (colours,
  categorical) and `"entity"` when no specific class is known; the system replaces both
  `"entity"` and `"none"` with a fresh free variable during `logconvert` (since neither
  carries a useful comparison-class constraint)

Stage 2 then uses this field to decide which predicate to emit (`has degree property` vs
`has property`; `has degree rel2` vs `is rel2`).  `logconvert` additionally normalises based on
the whitelist in `solver/gradables.txt`: words not in the whitelist are downgraded from
`has degree property` to `has property` regardless of what Stage 2 produced.

### 4.5 The $ctxt context term

Every eligible predicate atom in the GK clause list is augmented with a trailing `$ctxt` term:

```
["has property","tall","John 1",  ["$ctxt","past","W0","?:Fv1","?:Fv2"]]
                                    ▲        ▲      ▲    ▲       ▲
                                    pred     tense  world loc     knower
```

The four `$ctxt` arguments are:

| Position | Source |
|----------|--------|
| tense | `ASU.time` from Stage 1, or a fresh free variable for rules |
| world | `ASU.pre_state` from Stage 1 (or `W` constant from `["holds",W,F]`) |
| location | `ASU.location` from Stage 1, or a fresh free variable |
| knower | holder of a mental attitude, or a fresh free variable |

Eligible predicates (`CTXT_ELIGIBLE` in `lc_ctxt.py`): `has property`,
`have`, `has part`, `is rel2`, `has degree property`, `has degree rel2`,
plus all event role predicates (`has type`, `has actor`, `has target`,
`has time`, `has location`, …).  Structural predicates (`isa`, `holds`,
`state *`, `next`, `kb *`, `@*`, `$*`, `=`, `<`, `>`) and the modal
classifiers (`actuality`, `capability`, `typical`, `necessity`, `obligation`,
`volition`, `intention`, `expectation`, `speech_act`) are NOT augmented.

Context injection can be disabled with `-nocontext` (or `-simple`).

### 4.6 Defeasible reasoning and $block

Normal rules (type `normal_rule` in Stage 1) produce defeasible clauses.  The pattern
for a default about birds having wings is:

```
Stage 2 (holds world / forall):
  ["forall","X",["implies",["isa","bird","X"],
    ["normally",["has part","X","wing"]]]]

GK clauses produced by logconvert:
  ["-isa","bird","?:X"], ["has part","?:X","wing", CTXT],
  ["$block",["$","bird",1],["$not",["has part","?:X","wing", CTXT]]]
```

The `$block` literal means: *"this conclusion (`has part X wing`) can be defeated by a rule
with priority higher than `["$","bird",1]` for the class `bird`"*.  A plucked-bird exception
would carry a higher priority and the same head atom, allowing GK to prefer the exception.

Defeasible expansion can be disabled with `-noexceptions` (or `-simple`).

When a defeasible rule also carries a Stage-1 `confidence` (e.g.
`"Elephants normally have trunks, probability 0.8"`), the `$block`-bearing clauses
are the preferred anchors for the uncertainty; see §7.9 for the full distribution
scheme.

---

## 5. Source files

All Python source lives in `solver/`.  All scripts are run from `llmpipe/`.

### 5.1 solve.py

**Role:** CLI entry point and library facade.

**Key function:** `english_to_answer(text, options=None, collect=None) -> str`
Orchestrates the complete pipeline.  Calls `llmparse.parse_text`, then `rawlogic_convert`,
then `prover.call_prover`, then `process_proof`.  Returns the answer string; on any error
returns a string starting with `"Error:"` rather than raising.

If `collect` is a dict, the pipeline fills it in place with the intermediate artifacts of
the run — `stage1`, `stage2`, `clauses`, `gk_command`, `proof`, `nl_proof`, `answer` (it is
stored as `globals.options["_collect"]` and populated as each stage completes).  This is the
hook `runtests.py` uses to capture per-case JSON without re-running the pipeline; ordinary CLI
and library callers leave it `None`.

`main()` parses `sys.argv`, builds an options dict, and calls `english_to_answer`.

**CLI flags** (all optional):

Output level (hierarchy — each level includes all previous levels):

```
-explain           Show English proof explanation
-logic             + simplified ASU text, sentences-to-clauses, logic in proof steps
-details           + stage-1/2 JSON, prover input/output JSON
-debug             + raw LLM responses, prover params, full pipeline trace
```

Output format and other flags:

```
-json              Show logic as raw JSON instead of traditional pred(arg,...) syntax
-jsonlogic         Shortcut for -logic -json
-gkin FILE         Save GK prover input to FILE (with the GK command as a comment)
-llm NAME          LLM provider: gpt, claude, gemini, deepseek
-version VER       Model version string
-nosolve           Parse only; do not call the prover
-nollmcache        Disable LLM response caching for this run
-clearcache        Clear all caches and exit
-geminicache       Enable Gemini server-side context caching (off by default; see §5.3)
-seconds N         Prover time limit (default 2)
-simple            No context, no exceptions, simple properties
-think [N]         Enable reasoning/thinking mode (optional token budget)
-event MODE        Event-encoding base: neodavidson|davidson|flat|flatroles (§11)
-abstract / -abstract-roles / -abstract-max   Abstraction presets (§11–12); expand
                   into -event + the abstraction primitives (+ -prenorm for -max)
-entitymerge -typeenrich[=GATES] -guarddrop -bridges -dropdefinites -localantonyms
                   -existfold   Additive abstraction primitives (§11)
-prenorm           Pre-Stage-1 LLM wording normalisation (§12.1)
-nocrossstage      Disable the cross-stage guard retry (§11.5)
-combined-instr F  Combined single-stage parsing: ONE LLM call English -> logic (§12.2);
                   optional -combined-examples F / -combined-checklist F
-directanswer F    Answer with ONE LLM call using prompt file F; no logic, no prover (§12.3)
```

Before clausification, `english_to_answer` ASCII-folds both parses
(`_ascii_fold_logic`): every string in the Stage-1/Stage-2 JSON is transliterated to
plain ASCII (NFKD decompose, drop combining marks — "Náutico" → "Nautico").  The gk
subprocess output is decoded as ASCII, so a non-ASCII constant would otherwise crash
proof reading (answer `None`).  This runs on every path, including the default one.

### 5.2 llmparse.py

**Role:** Two-stage LLM parser.

**Key function:** `parse_text(text, llm=None, version=None, tokens=None) -> (s1_json, s2_json, stats)`

The function:
1. Loads prompts from `prompts/` on first call (lazy, cached in module-level globals).
2. Calls `_run_stage(1, text, ...)` to produce Stage-1 ASU JSON.
3. Normalises entity IDs via `_normalize_entity_id_case`: merges IDs that differ only
   by first-character capitalisation (e.g., `"Car 1"` at sentence start vs `"car 1"`
   mid-sentence) when the ID has a number suffix and the capitalised form appears at
   sentence start.
4. Serialises Stage-1 output as JSON string; passes it as input to `_run_stage(2, ...)`.
5. Returns both parsed objects plus a stats dict.

**`_run_stage`** handles robustness:
- Calls `llmcall.call_llm`.
- Tries `json.loads` on the raw response.
- If that fails, applies `fix_json` (heuristic repairs: strip markdown fences, remove Python
  literals, balance brackets, strip trailing junk, etc.).
- If still invalid, makes one LLM retry with error feedback in the prompt.
- After a successful parse, invokes a per-stage **sanity checker** (`check_stage1` /
  `check_stage2` from `stage_sanity.py`) and, if it reports issues, enters a separate
  corrective-retry loop via `_maybe_sanity_retry` (see §7.8 and §5.17 for details).
- Tracks all events in the stats dict (`s1_calls`, `s1_json_errors`, `s1_json_fixes`,
  `s1_retry_calls`, `s1_sanity_retries`, `s1_sanity_ok`, `s1_sanity_fail`, etc.).

**`fix_json(s)`** applies up to 10 repair strategies in sequence, returning the first one that
produces valid JSON.  Repairs include: stripping ` ```json ``` ` fences, replacing Python
`True`/`False`/`None` with JSON equivalents, stripping non-JSON wrapper text, adding missing
commas, balancing brackets.

**Prompt composition:** `_compose_prompt(instructions_file, examples_file)` concatenates
instructions + `"\n\nExamples:\n\n"` + examples into a single system prompt string.

**Mode branches inside `parse_text`** (all off by default, set by `solve.py` from
`globals.options`):
- `prenorm_enabled` — rewrite the input English first via `normalize_text` (§12.1).
- `combined_enabled` — make ONE LLM call (English → Stage-2 logic) with the explicitly
  named combined prompt files and return `(None, s2_json, stats)`; there is no Stage-1
  JSON in this mode (§12.2).
- `canon_entities_enabled` (set by `-entitymerge`) — aggressive Stage-1 entity-id
  canonicalization (`canonicalize_entity_ids`) and Stage-2 Wikipedia-URL folding
  (`canonicalize_entity_urls`) (§11.4).
- `crossstage_guard_retry` ∧ `canon_entities_enabled` — after Stage 2, re-run BOTH
  stages once with a corrective hint when a rule antecedent names a class/property/
  relation nothing can satisfy (§11.5).

### 5.3 llmcall.py

**Role:** Low-level LLM API wrapper.

**Key function:** `call_llm(sysprompt, input_text, llm=None, version=None, max_tokens=None, think=False) -> str | None`

Dispatches to `call_gemini`, `call_claude`, `call_gpt`, or `call_deepseek` based on the
`use_llm` setting.  Two shared helpers keep the provider functions concise:
- `_read_api_key(filepath, provider)` — reads a plain-text API key file
- `_post_with_retry(host, url, body, headers, provider)` — HTTPS POST with retry loop,
  error handling, and JSON response parsing

**Retry on empty/None response:** `_post_with_retry` only retries HTTP-level failures.
Any provider can also return a 200-OK with a missing or empty text payload (transient
flake).  `call_llm` wraps the provider dispatch in an extra retry loop controlled by
`empty_response_retries = 2`, re-calling the provider when the result is `None` or a
whitespace-only string.  Empty results are NOT written to the cache (would otherwise
poison the entry permanently).

**Caching:** Before calling the LLM, `call_llm` checks the SQLite cache in `cache.db`.  The
cache key encodes: provider, version, temperature, seed, max_tokens, think, sysprompt, input_text.
If a match is found, the cached response is returned immediately.  The result of every new LLM
call is stored in the cache before returning.  Caching is controlled by
`globals.options["use_llm_cache_flag"]` (default `True`).

**Newer Claude models (Opus 4.8 / Fable 5 / Mythos 5):** `_claude_uses_effort_api`
detects these versions; for them `call_claude` omits `temperature` (deprecated) and
replaces `thinking.budget_tokens` with adaptive thinking plus `output_config.effort`
(a `-think` integer budget maps to low/medium/high via `_claude_effort`).  Older
models (sonnet-4-6 etc.) use the original request shape, byte-identical to before.

**Rate-limit (429) backoff:** In addition to the generic HTTP retry, `_post_with_retry`
gives 429 (Too Many Requests) responses their own exponential-backoff loop, capped at
`_rate_limit_max_retries = 7` attempts.  The delay doubles each attempt (2, 4, 8, … 128s)
with up to 25% random jitter, so a burst that exhausts a per-minute quota window waits long
enough for it to refill instead of hammering the endpoint.  429s do not count against the
ordinary `max_retries` budget.  This matters most for Gemini, whose free/low tiers have tight
per-minute request and token caps.

**Gemini context caching (opt-in):** Gemini's lower tiers also impose a per-request
input-token cap that the ~25–30K-token Stage-1/Stage-2 sysprompts can exceed, triggering an
instant 429.  When `globals.options["use_gemini_cache_flag"]` is `True` (set via `-geminicache`;
**default `False`**) and the sysprompt is at least `_GEMINI_CACHE_MIN_CHARS` (16K chars, ~4K
tokens), `call_gemini` uploads the sysprompt once to Google's `cachedContents` service and
references it by handle on each subsequent call, dodging the per-request cap.  Handles are kept
in the module-level `_gemini_cache_map` with a `_GEMINI_CACHE_TTL` of 1800s; an expired-handle
404 transparently recreates the cache, and a second failure falls back to inlining the prompt
as a normal `system_instruction`.  Caveat: cached tokens still count toward the per-minute TPM
budget, so this helps with large single prompts but not with sustained throughput — for that the
429 backoff above does the real work.  The cache is transport-only and does **not** affect the
SQLite cache key, so a cached and a non-cached Gemini call with identical parameters share the
same `cache.db` entry.

**Debug output:** Uses `utils.debug_print` with module-level `debug` and `calldebug` flags:
- `debug = True` logs each provider's raw response
- `calldebug = True` logs the full request body sent to the API

**Configuration** (edit at the top of `llmcall.py`):

```python
use_llm          = "gemini"            # "gpt" | "claude" | "gemini" | "deepseek"
claudeversion    = "claude-sonnet-4-6"
gptversion       = "gpt-5.1"
geminiversion    = "gemini-2.5-flash"
deepseekversion  = "deepseek-chat"     # V3.2; "deepseek-reasoner" for thinking
temperature      = 0
default_max_tokens = 8000
max_retries      = 3
```

API keys are read from plain-text files in `../secrets/` (relative to `llmpipe/`):
`gpt_secrets.txt`, `claude_secrets.txt`, `gemini_secrets.txt`, `deepseek_secrets.txt`.
The directory path is set once via `_secrets_dir` in `llmcall.py`.

### 5.4 logconvert.py and supporting modules

**Role:** Main driver for logic conversion — orchestrates the full Stage-2 JSON → GK clause
list pipeline.  The computation is split across several files:

| Module | Responsibility |
|--------|---------------|
| `logconvert.py` | Top-level orchestration: `rawlogic_convert` entry point, the per-`@id` package loop, post-processing pass sequencing, and Stage-1 entity bookkeeping. The structural repairs, query-body simplification, entity-category enrichment, and strict/abstract finalisation are split into the `lc_*` modules below |
| `lc_repairs.py` | Pre-clausification structural repairs: id hoisting (`hoist_nested_ids`), misnested-implies repair (`repair_misnested_normally_implies`), the self-defeating-conditional engine (`repair_self_defeating_conditional`), the `-s2split` off-inventory predicate rename (`rename_offinventory_preds`), and `@definite` tag stripping (`strip_definite_tags`) |
| `lc_query_guards.py` | Query-body simplification: phantom isa-guard stripping (`strip_phantom_query_guards`: drop an orphan `isa(C,E)` guard from a query body when E is a Stage-1 entity never asserted and used nowhere else in the query — a leaked definite-description referent that would otherwise make the whole conjunctive query unprovable) and `"what"`-question population-fact generation (`generate_what_population`) |
| `lc_entity_isa.py` | Entity-category / typeenrich `isa` enrichment (`build_entity_category_clauses`: supertype / gender / name-as-type / compound atoms, gated per `EncodingConfig.te(gate)`) and the typeonly-Skolem merge (`merge_typeonly_skolems`) |
| `lc_finalize.py` | The strict / abstract clause finaliser (`finalize_strict_clauses`) split out of `rawlogic_convert` |
| `lc_packages.py` | Per-`@id` package processing: `extract_package_ctx`, `convert_id_package`, `_process_question`/`_process_assertion`, raw wh-word probes, confidence distribution |
| `lc_rewrites.py` | Pre-clausification formula rewrites (meta-predicate normalization incl. `"time of"`→`has_time`, tense-valued `has_time` stripping, verb normalization: travel/journey/move→go, hand/pass/send→give, receive→give with actor↔recipient swap, perspective-relation lift `["is rel2", got/received/saw/heard, X, Y]` → Davidsonian event, existential hoisting, spurious `can` removal, polarity flip) |
| `lc_ctxt.py` | `$ctxt` injection, time-wrapper stripping, fresh variable generation |
| `lc_post_normalize.py` | Post-clausification normalising / repair passes: gradable normalization, RELCLASS coercion, `isa entity` stripping, degree stripping, compound subsumption extraction. Possessive-`have`/`has_part` bridges and population extraction are split out (next two rows) |
| `lc_post_have.py` | Possessive `have` / `have`↔`has_part` bridges: `add_possessive_have`, `add_haspart_for_typed_have`, `inject_have_to_haspart_axioms` |
| `lc_post_population.py` | Population-fact extraction and negative-witness walks: `populate_clauses` |
| `lc_post_reify.py` | Post-clausification reification of definite descriptions and measurements: `rewrite_definites` (`$theof1`), `rewrite_measure_terms` (`$measure_of`/`$measure`/`less_measure`) |
| `lc_post_inject.py` | Post-clausification dynamic axiom injection — the bridge/verb/world injectors: beneficiary↔`is rel2 "for"` bridge, carrier-vocabulary lift, verb-result-state bridges, acquire→have bridges, positional-preposition actor-location bridges (`inject_positional_actor_bridges`, case 670), `"filled with"`/`"full of"`→`in` containment bridges (`inject_containment_bridges`, case 673), attribute property↔relation bridges (color/shape/material/taste, `inject_attribute_relation_bridges`, case 901), stable-adjective past→present persistence (`inject_stable_adjective_persistence`, case 911 — see §7.14), world-graph geometry. The KB-driven synonym/exclusion injectors are split out (next row); all injectors traverse via `treewalk.walk_result_atoms` |
| `lc_inject_synonyms.py` | KB-driven soft-synonym + exclusion/mutex injectors: `inject_soft_synonyms`, `inject_exclusion_axioms` (incl. noun-mutex via `_ISA_EXCL_GROUPS`), `inject_isa_cross_group_axioms`, `inject_verb_mutex_axioms`, `inject_kinship_mutex_axioms`. Re-exported through `lc_post_inject` so importers are unchanged |
| `lc_inject_scan.py` | Shared clause-scan helpers used by the injectors: `collect_eligible_words`, `eligible_word` |
| `treewalk.py` | Shared formula-tree traversal: `walk_result_atoms(result, visit)` calls `visit(atom, base)` on each predicate atom of every `@logic`/`@question` body — the scan all injectors share |
| `lc_post_una.py` | Post-clausification UNA wrapping: prefix every Stage-1 numbered entity with `#:` so `gk` treats distinct entity constants as definitely unequal. Three-step criterion (regex + Stage-1 set + not-Skolem). Required by the X2 direct-support uniqueness axiom (axioms_std.js §7g) |
| `lc_clausify.py` | FOL→CNF compilation |
| `lc_questions.py` | Question encoding and population fact builders |
| `lc_sets.py` | Set/counting: `$setof` rewriting, membership axioms, element instantiation |

**Key function:** `rawlogic_convert(logic, s1_json=None) -> list | None`

Converts the Stage-2 nested JSON formula into a flat GK clause list:

```
["and", ["@id","S1",PACKAGE], ...] (Stage-2 input)
    │
    ├─ hoist_nested_ids(logic)            [lc_repairs] extract @id blocks nested by LLM bracket errors
    ├─ repair_misnested_normally_implies(logic)  [lc_repairs] ["normally",["implies",A],C] → ["normally",["implies",A,C]] (recover a consequent hung off `normally`; case 1418/1421 deepseek)
    ├─ _build_asu_index(s1_json)          build unit_id→ASU lookup from Stage 1
    ├─ rewrite_meta_predicates(logic)     [lc_rewrites] "located in"→"in", "is"→isa, "time of"→has_time, travel/journey/move→go, hand/pass/send→give
    ├─ rewrite_perspective_relations(logic) [lc_rewrites] lift ["is rel2", got/received/saw/heard, X, Y] into a Davidsonian event so the next pass can bridge it (covers gpt/deepseek relation-form encodings)
    ├─ normalize_receive_events(logic)   [lc_rewrites] receive→give with actor→recipient swap
    ├─ strip_tense_has_time(logic)       [lc_rewrites] remove has_time(E,"past",...) bogus atoms
    ├─ inject_actuality(logic)           [lc_rewrites] append ["actuality",E] to every Davidsonian event lacking a modal classifier ANYWHERE in the tree (tree-wide scan via _collect_classified_vars, not just direct siblings; skip inner content events) — case 1418: a `typical` nested in the event's own sub-block must still suppress actuality so a rule antecedent and its fact stay consistently marked
    ├─ inject_degree_presuppositions()    [lc_rewrites] "not very X" → X and not very X
    ├─ populate_clauses(items)            [lc_post_population] collect background facts
    │
    ├─ for each @id item:
    │    convert_id_package(item, asu_index)                   [lc_packages]
    │        extract_package_ctx()        unpack PACKAGE: formula, world, tense, etc. [lc_packages]
    │        override with Stage-1 ASU data (tense, world, location)
    │        compute latest world numerically for queries without pre_state
    │        default question tense to "present" when Stage 1 omits "time"
    │        generate $theof1/$datetime fact for explicit time values
    │        inject event has_time from Stage 1 if missing (repair for LLM omission)
    │        generate is_past_world(W) from state_tense="past"
    │        strip_spurious_can()          [lc_rewrites] remove non-modal "can"
    │        hoist_misnested_exists()      [lc_rewrites] fix variable scoping
    │        _process_question()           wh-/yes-no question dispatch [→ lc_questions]
    │        _process_assertion()          clausify + three-tier confidence distribution (§7.9) [→ lc_clausify]
    │        inject $ctxt into result      [lc_ctxt]
    │
    ├─ rewrite_definites() (global)        [lc_post_reify] $theof1 for all ASU definites
    ├─ rewrite_measure_terms()            [lc_post_reify] $measure→$list, less_measure rewrite, $theof1 unwrap in $measure_of
    ├─ insert population facts before first @question
    ├─ generate "what" population facts     for @what_query: isa(CLASS,$some_CLASS) from witnesses
    ├─ inject $ctxt into population facts  [lc_ctxt]
    ├─ inject_verb_result_state_axioms (extends `result` in place
    │    so the result-state property words become eligible for the
    │    exclusion injector below)                                       [lc_post_inject]
    ├─ inject_soft_synonyms / inject_exclusion_axioms /
    │    inject_isa_cross_group_axioms / inject_verb_mutex_axioms /
    │    inject_kinship_mutex_axioms                                     [lc_inject_synonyms]
    ├─ inject_beneficiary_for_bridge / inject_carrier_lifts             [lc_post_inject]
    ├─ add_possessive_have / add_haspart_for_typed_have /
    │    inject_have_to_haspart_axioms                                   [lc_post_have]
    ├─ normalize_gradable_predicates()    [lc_post_normalize]
    ├─ strip_isa_entity()                 [lc_post_normalize]
    ├─ coerce_relclass()                  [lc_post_normalize]
    ├─ strip_degree_predicates()          [lc_post_normalize] (only if -simpleprops)
    ├─ inject_world_geometry()            [lc_post_inject] minimal next chain over present worlds
    ├─ strip @sourcetype                  remove internal annotation before prover
    └─ apply_una(result, stage1_set)      [lc_post_una] wrap Stage-1 entities with #: prefix
```

**Counter globals** (reset at the start of each `rawlogic_convert` call):

- `lc_clausify._skolem_nr`, `lc_clausify._gobj_nr` — Skolem and generic-object counters
- `lc_questions._defq_nr` — `$defq` predicate name counter
- `lc_ctxt._fv_nr` — fresh free-variable counter (`?:Fv1`, `?:Fv2`, …)

See §7 for detailed discussion of the key algorithms.

### 5.5 lc_clausify.py

**Role:** FOL → CNF clausification compiler.

**Public API used by `logconvert.py`:**

- `clausify(formula) -> list` — converts a first-order formula to a list of CNF clauses
- `looks_like_var(s) -> bool` — true if `s` matches Stage-2 variable pattern (`?:`-prefixed or single uppercase letter + digits) but NOT world constants
- `is_world_constant(s) -> bool` — true if `s` matches `W0`, `W1`, etc. (excluded from variable detection)
- `apply_varmap(formula, varmap) -> formula` — substitute variables by name
- `connectives` — frozenset of logical connective names (not predicates)
- `singularize_isa_classes_in_node(node) -> node` — recursively normalize the class argument
  (index 1) of every `isa` / `-isa` atom to singular.  Run by `rawlogic_convert` as a **late
  pass** over the whole clause list (after all injection, before UNA), so LLM-emitted assertions,
  injected population facts (`isa(C, $some_C)`), and `$defq` question guards all use the same
  class name.  Without it a bare-plural generic (`isa("animals", X)` from one sentence, or a
  Stage-1 generic entity whose **id** is plural while its **category** is singular) never unifies
  with the singular form used elsewhere or with the population witness, so an existential generic
  question (`∃X isa(C,X) ∧ BODY`) finds no witness → Unknown (case 211, gpt/claude/gemini).
  `_safe_singularize_class` guards the crude trailing-`s` heuristic: it skips proper nouns
  (capitalized) and `-us` / `-is` / `-ss` / `-es` / `-cs` endings (bus, analysis, class, series,
  potatoes, physics), gating multi-word classes on their head word, plus a small irregular set.

**Clausification pipeline** (inside `clausify`):

```
_normalize_type_case
_strip_typical_from_antecedent
_expand_generic_objects
_normalize_quantifiers
_implies_to_or                 eliminate implies / equivalent / xor
_push_neg                      push negations in to reach NNF
_expand_normally (pass 1)      push normally inside exists/and
_skolemize                     eliminate existentials → Skolem terms
_distribute                    distribute or over and → CNF
_expand_normally (pass 2)      normally(atom) → $block clause
_extract_clauses               collect flat clause list
```

**Internal helpers** (extracted from `_expand_normally` and `_distribute`):

- `_flatten_or_elements(elements)` — flatten nested `or` wrappers in a list of formula elements
- `_classify_literals(lits)` — split literals into `(neg_lits, pos_lits)` by predicate polarity
- `_extract_isa_priority(neg_lits, blocker_class_tag, extra_neg)` — compute `$block` priority
  from negative literals and optional class tag

**Module-level counters** (reset externally by `rawlogic_convert`):

- `_skolem_nr` — next Skolem constant/function index
- `_gobj_nr` — generic-object counter for `_expand_generic_objects`

### 5.6 lc_questions.py

**Role:** Wh-question encoding and population-fact collection.

**Public API used by `logconvert.py`:**

- `build_defq_question(name, ask_var, body, where_prep=None) -> list` — encode a wh- or yes/no
  question as `$defq` biconditional GK clauses
- `hoist_generic_yn_subject(formula, name) -> (skq, hoisted_atom, rewritten_body) | (None, None, formula)`
  — bare-plural-generic yes/no rewrite. Matches `forall X, isa(C,X) → normally(BODY)` (the
  Stage-2 §7.4(a) shape), and on match returns a fresh skolem constant `skq_S<qid>_<C>`,
  a hoisted antecedent atom (or `["and", …]` when the antecedent had multiple atoms about
  X), and the consequent BODY with `X ← skq…` substituted in. `lc_packages._process_question`
  prepends the hoisted atom as a `@sourcetype: "question_subject"` fact and feeds the
  rewritten body to standard yes/no clausification, producing UDP-shaped `isa(C, skq) +
  $defq ↔ BODY[skq]` clauses (closes cases 213/214/215 across all four LLMs)
- `find_where_atom(body, ask_var) -> atom | None` — find the location atom in a where-question body
- `build_where_question(name, entity, ask_var, specific_prep=None) -> list` — encode a where-question
- `flatten_q_atoms(frm, varmap) -> list` — flatten an `ask` formula into a list of atoms
- `scan_item_formula(frm, name, polarity, classes, has_props, deg_props)` — scan a formula for
  isa / has-property / has-degree-property atoms, recording polarity in the provided dicts
- `build_population_facts(classes, has_props, deg_props) -> list` — build positive/negative
  synthetic population clauses from collected scan data
- `is_ground_term(t) -> bool` — true if `t` contains no variables
- `is_simple_question_formula(f) -> bool` — true if `f` is a single atom (not compound)
- `collect_body_free_vars(frm, bound=None) -> set` — free variables in a formula
- `find_haslocation_prep(body, ask_var) -> str | None` — return `"in"` if body contains
  `has_location` with the ask variable
- `simplify_contradictory_and(frm) -> formula` — simplify `["and", ["not", A], A]` to `["not", A]`
- `S2_VAR_RE` — regex matching Stage-2 variable names (uppercase-initial identifiers)
- `WHERE_SPATIAL_PREPS` — set of spatial prepositions handled as where-questions

### 5.7 lc_sets.py

**Role:** Programmatic conversion of Stage-2 `$setof` terms into canonical form,
generation of membership axioms, and element instantiation.

**Entry point:** `process_sets(formula)` — called before clausification.  Returns
`(rewritten_formula, axioms, element_clauses)`.

**Two $setof forms:**

| LLM output | Canonical form | When |
|------------|---------------|------|
| `["$setof","?:X",["and",...conds with have...]]` | `["$setof","have","John 1",["$and",...$-prefixed...]]` | Stative anchor found (have, is_rel2, can) |
| `["$setof","?:X","set 1",["and",...conds...]]` | `["$setof","id","set 1",["$and",...conds...]]` | No anchor, set_id from Stage-1 |

**Conversion steps** (inside-out for nested $setof):
1. Detect anchor predicate in conditions; extract it
2. Replace bound variable with `$arg1` (`$arg2` for nested)
3. `$`-prefix predicates in anchored form; no prefix for conditions-only
4. Sort `$and` entries: `$isa`/`isa` first, rest alphabetically
5. Mutate the $setof node in place

**Membership axiom generation:** For each unique $setof pattern, a
`forall/biconditional` axiom is generated:
```
member(?:M, $setof(have, ?:S, [$and, $isa(?:C,$arg1), $prop(?:P,$arg1)]))
  <=> isa(?:C, ?:M) & prop(?:P, ?:M) & have(?:S, ?:M)
```
Concrete values in conditions are generalized to forall variables.

**Element instantiation:** For each positive `["=", N, ["$count", $setof_term]]`
in an assertion context (inside `holds`, not in queries), creates
`min(N, set_element_limit)` concrete element constants (`$setK_elI`) with:
- All set properties (un-prefixed predicates)
- Anchor predicate (if anchored)
- `member` assertions
- Pairwise distinctness (`["-=", el1, el2]`)

Configurable via `globals.options["set_element_limit"]` (default 3).

**Key functions:**
- `_classify_setof(conditions, var)` — detect anchor predicate
- `_rewrite_setof(node, depth)` — rewrite one $setof to canonical form
- `_build_membership_axiom(info)` — generate the forall/biconditional
- `_instantiate_elements(info, source_name, count)` — create element clauses
- `_instantiate_distributive_events(formula, setof_term, elements, source_name)` —
  create per-element event instances from forall/implies/member blocks

### 5.8 procproofs.py + proof_answer_select.py + proof_answer_format.py

**Role:** Post-processing of raw prover output into a human-readable answer.

`procproofs.py` is the orchestrator; the two heavy halves live in sibling modules:

| Module | Role |
|--------|------|
| `procproofs.py` | `process_proof` — the pipeline: parse prover JSON, strip the `#:` UNA prefix, drive selection then formatting, dispatch explanation. Plus `_parse_result`, `_strip_una_prefix`. |
| `proof_answer_select.py` | Decides WHICH bindings survive: tier ranking, measure preference, unbound/leak/tautology filters, proof dedup. |
| `proof_answer_format.py` | Renders the surviving bindings into English: who/what/where/when/bool formatters + the `@…_query`/`@askvars` shape probes. |

The dependency graph is acyclic: `proof_answer_select` ← `proof_answer_format` ← `procproofs`.
`proof_answer_format` imports just `_extract_class_names` and `_ans_object_tier` from
`proof_answer_select`; selection imports nothing from formatting.

**Key function:** `process_proof(proof_result, text=None, s1_json=None, logic=None, options=None) -> str`

1. Parses the raw prover JSON string.
2. Checks for `"result": "answer found"`.  Returns `"Unknown."` if not found.
3. Sorts answers by `_answer_goodness` (confidence desc, proof length asc).
4. Filters to the best object-type tier: concrete entities > Skolem constants > population facts.
   For `@what_query` the population-vs-concrete preference is split by query shape
   (`_what_query_is_relational`, classifying by the answer variable's role and looking
   through any `$defq` wrapper):
   - **Relational** what-query — the answer variable is a relatum of an `is_rel2` /
     `has_degree_rel2` atom (e.g. "What is X afraid of?" → `is_rel2("afraid of", X, ?)`).
     The *kind* is the natural answer, so the population class beats a real concrete
     instance (`population_beats_concrete=True` in `_filter_by_best_tier`): "A cat.",
     not the incidental "Emily." (and not "Gertrude and Winona" when several instances
     exist).
   - **Classification** what-query — the answer variable is the entity of an `isa` atom
     ("What is an Estonian city?" → `isa(estonian_city, ?X)`).  A real concrete entity
     still wins: `Tallinn` beats "a city in Estonia" (cases 1258/1259).
   Resolves Skolem function answers to class names via `get_skolem_fn_type`.
4a. **Unbound-answer filter** (`_answer_all_unbound`): drops answers whose `$ans`
   answer-positions are entirely unbound `?:` variables.  These arise when a goal
   is proved without ever instantiating the answer variable — e.g. a relationally
   phrased query closed via a reflexive `$theof1` axiom, binding the definite
   description but leaving `$ans` free — and would otherwise leak the bare
   variable name (`"X3."`).  An unbound answer var is never a real binding.
4b. **`$list` value-preference** (`_prefer_measure_value_answers`): when any answer
   binds a measure value (`$list`, possibly nested in a `$get_world`/`$ctxt`
   wrapper), keep only the `$list` answers.  This collapses the two-answer set the
   `measure_of→"<noun> of"` bridge (§9.3) produces for a relational measure
   question — *"the length of car A and 80000 meters"* → *"80000 meters"*.  No-op
   when no answer carries a `$list`, so non-measure queries and reverse
   *"what is 80 km long?"* entity answers are untouched.
4c. **Tautological-population / class-name-leak filters**
   (`_filter_tautological_population_answers`, `_filter_class_name_leaks`): drop a
   `$some_*` population witness that merely restates the queried property/class.
   Two detection paths, both used:
   - *Proof-scan* (`_is_tautological_population_answer`): the witness is proved
     directly via the single-atom population clause that asserts the queried
     property/class (`some big elephant is big because some big elephant is big`).
   - *Clause-scan* (`_defined_property_witnesses`): collects every `$some_*`
     constant whose **defining** population clause `[PRED, PROP, const, …]` matches
     a question pop key, and drops ALL bindings to it **regardless of proof
     route**.  This catches a property witness reached by a second, non-circular
     route — `$some_nice_car` answering "what is nice?" not via its own clause but
     via "it is a car, and cars are nice" (cases 1434 / 1487).  The queried-CLASS
     witness (`$some_car`, defined by `isa`, not the property key) is never
     collected, so the correct generic answer ("A car.", "An elephant.") survives.
   Both fire even when no non-tautological alternative remains (→ "Unknown").
5. Formats the answer string via `_format_answers`:
   - Boolean `True`/`False` → `"True"` / `"False"`
   - Named entities → display name (strips numbering when unambiguous, strips URL when
     display name is unambiguous)
   - Confidence < 0.99 → appends `"(confidence X%)"`
6. Optionally renders a step-by-step proof explanation (via `proof_explain.format_explanation`)
   when `-explain` is used.

**Internal helpers** (in `proof_answer_format.py`):

- `_join_and_finish(parts)` — join a list of answer strings with "and", capitalise, add period;
  shared by `_format_prep_answers` and `_format_answers`

Steps 3–4b above (`_answer_goodness`, `_filter_by_best_tier`, `_what_query_is_relational`,
`_answer_all_unbound`, `_prefer_measure_value_answers`, the tautology/leak filters and
`_deduplicate_proofs`) live in `proof_answer_select.py`; the `_format_*` renderers and
query-shape probes (step 5) live in `proof_answer_format.py`.

**Ambiguity handling:** Before formatting, `compute_ambiguity` (from `proof_render.py`) scans
the full logic list to find entity names that appear with more than one number (e.g. `"John 1"`
and `"John 3"`).  Such names keep their distinguishing number in output.

**Imports:** `procproofs` imports `compute_ambiguity`/`compute_skolem_types`/`entity_name`/
`set_entity_map` from `proof_render.py`, `format_explanation`/`build_sentence_map` from
`proof_explain.py`, plus the selection/formatting entry points from the two sibling modules.
`proof_answer_format` additionally imports `ans_atom_name`/`get_skolem_type`/`get_skolem_fn_type`/
`get_entity_display` from `proof_render.py` and `ans_display_key` from `proof_explain.py`.

### 5.9 Proof rendering modules

Proof rendering is split across four files, with `proof_render.py` as a thin facade:

| Module | Role |
|--------|------|
| `proof_render.py` | Facade — re-exports public API from the implementation modules |
| `proof_utils.py` | Entity naming, Skolem type resolution, render context state, ambiguity detection |
| `proof_english.py` | Atom/clause → English rendering; table-driven via `_PRED_TABLE` |
| `proof_terms.py` | Term rendering sub-library (`render_term_english` + `$count`/`$setof`/`$theof1`/`$measure` and TPTP-arithmetic helpers), split out of `proof_english`; reached by both `proof_english` and `proof_utils` |
| `proof_logic.py` | Traditional `pred(arg,...)` and JSON logic syntax rendering |
| `entity_map.py` | `build_entity_map(s1,s2)` → `{entity_id/url: display_name}` from the user's original phrasing (article + pre-nominal qualifiers); consulted first by `proof_utils.get_entity_display` / `_location_entity_name` |

Per-proof mutable state (entity map, ambiguous names, Skolem type annotations) is bundled in a
`RenderContext` class (`_ctx` module-level instance) in `proof_utils.py`.

**Qualifier extraction (`entity_map.py`).** Display names reuse the user's wording by scanning
the source text backwards from each entity for pre-nominal adjective qualifiers ("the **red**
car"). Verbs must be excluded so they don't leak as qualifiers — `_collect_action_verbs` gathers
them from Stage-1 action roots and Stage-2 relation names, and a static `_STOP_WORDS` set stops
collection at auxiliaries/prepositions/conjunctions. A surface verb whose **canonical Stage-2
relation name differs** from its surface form is the trap: "Earth **contains** Europe" is encoded
`is_rel2("**in**", …)`, so the relation captured is "in" and the surface "contains" is never seen
as a verb → it would render `"the contains Europe"`. Such containment/spatial transitive verbs
(`contain(s)`, `include(s)`, `comprise(s)`, `surround(s)`, `hold(s)`) are therefore listed
explicitly in `_STOP_WORDS` (case 1253).

Atom-to-English rendering in `proof_english.py` is table-driven via `_PRED_TABLE`, a dict mapping
predicate names to `(arity, pos_renderer, neg_renderer)` tuples.

See `PROOF_RENDERING.md` for the original principles, entity naming rules,
and proof explanation structure with examples.

#### Per-clause rendering state (`_ClauseRenderCtx`)

`clause_to_str` installs a per-clause `_ClauseRenderCtx` (module-level
`_RENDER_CTX` slot, scoped via try/finally) that tracks:

- `seen` — raw arg names (and `"skfn:"+str(skfn)`) already introduced;
  consulted by `_intro` to decide between full and bare rendering.
- `event_vars` / `event_consts` — variables / Skolem constants identified
  as Davidsonian events (via `isa("activity", X)`, `has_type(X,V)`, or a
  modal classifier on X in the same clause).
- `world_vars` — variables identified as worlds (via `next`/`before`/
  `moved`/`is_past_world` positions, or the world slot of `$ctxt`).
- `has_type_vars` — event vars whose `has_type(X,V)` literal appears in
  the same clause; `_intro` drops the `"an event X"` prefix for these
  because the predicate already introduces the type.
- `isa_type_hint` — map `var → TYPE` from `isa(TYPE, var)` literals
  (skipping `"activity"` to avoid event-marker conflicts).
- `used_in_other` — variables that appear in some non-isa atom; the
  isa-bundling absorption only fires when this is true.
- `absorbed_isa_ids` — bookkeeping for the isa-bundling pass.

`_scan_clause_vars(clause, ctx)` populates these fields in a single pre-pass
before any rendering happens.

#### `_intro(arg, role_hint=None)`

Central helper that decides the article/prefix for an argument on its first
mention in the current clause.  In priority order:

1. Skolem fn list-term → first time full ("the flying event sk0 of Mike 1");
   on later mentions short ("sk0 of Mike 1").  Also marks any variable args
   of the Skolem fn as `seen`.
2. World constant (`W0`, `W1`, …) → `"the situation W0"` (always).
3. Event Skolem (`sk0_activity`) → `"the event act1"` first, `"the act1"` later.
4. Common-noun constant (`"head 2"` / `"box B"` — lowercase + suffix) → always
   `"the head 2"`.
5. Variable, world-typed → `"a situation V"` first, bare later.
6. Variable, event-typed → `"an event E"` first; SKIPPED when the variable
   is in `has_type_vars` (returns bare `X` so `"X is a fly event"` reads
   cleanly instead of `"an event X is a fly event"`).
7. Variable with `isa_type_hint` and `used_in_other` (isa-bundling) →
   `"some <TYPE> X"`.  The matching `isa(TYPE, X)` atom is suppressed from
   the clause rendering.
8. Variable with explicit `role_hint` → `"a/an <ROLE> X"` (currently unused
   from the per-predicate lambdas; reserved for future role-aware bundling).
9. Bare entity variable → `"some X"`.

All paths add the arg to `seen` so subsequent calls in the same clause
return bare.

#### Two-pass clause rendering (`_clause_to_str_body`)

Pass 1 classifies every literal into `neg_specs` (conditions), `pos_specs`
(consequents incl. `$ans`), or `block_atoms`.  Applies:

- R1 (drop tautological `isa(TYPE, "TYPE N")` in multi-literal clauses).
- isa-bundling absorption (negative form): gated on `bundling_active`,
  which is `True` only for pure-negative clauses (no positive literals
  to anchor an explicit if-then structure).
- Modal-classifier reorder: in pure-negative clauses, any literal whose
  predicate is in `_MODAL_CONSEQUENT_PREDS` (`capability` / `typical` /
  `necessity` / `obligation` / `volition` / `intention` / `expectation` /
  `speech_act` / `actuality`) is moved to the END of `neg_specs` so it
  becomes the consequent — the modal claim is usually the informative
  conclusion ("X is not a capability" reads better than "X is not a
  penguin").

Pass 2 renders conditions FIRST (in clause order), then consequents (in
clause order).  This places variable intros in the antecedent visually,
where readers expect them — without this re-ordering an `is_rel2`
consequent rendered first would consume the variable's first-mention
prefix and the antecedent would read with bare `X`.

After joining with " and " / " or " / "if … then …", a final pass
capitalises the first alpha character (skipping leading quotes/brackets)
to make each step read as a sentence — but it skips Skolem-fn identifiers
(`sk0`, `sk1_house`, …) which are not English words.

#### Custom per-predicate render helpers

Several `_PRED_TABLE` entries call dedicated helpers instead of inline lambdas:

- `_has_type_render` — when the first arg is a Skolem fn, uses the SHORT
  form (no "the flying event" prefix) because `has_type` already asserts
  the event type; would otherwise read "the flying event sk0 of X is a
  fly event" (redundant).  Also marks the Skolem fn's variable args as
  seen to avoid re-introducing them later in the same clause.
- `_has_time_render` — picks past/present/future verb form from the
  literal-tense slot (`"happened in the past"` instead of `"happens in
  past"`).  Falls back to the generic form when the tense slot is itself
  a variable.
- `_has_recipient_render`, `_has_destination_render` — pivot to
  `"<X> is the/a recipient/destination of <E>"`.  Article picked by
  whether the event arg is a Skolem (concrete → "the") or a variable
  (axiom → "a").  Drops the prep slot of `has_destination` since it's
  usually a noisy auxiliary variable.
- `_is_rel2_var_rel_render` — invoked from `_is_rel2_pos/_neg` when the
  relation arg is a variable.  Renders `"<Y> is/was/will-be in relation
  <X> to <Z>"` and surfaces the `$ctxt` tense + world ("in <world>" /
  "before <world>" / "after <world>") so two such atoms with different
  contexts in the same clause render distinguishably.
- `_prep_answer_phrase` — `$ans`/`$defq*` payloads of the form
  `[PREP, VALUE, …]` (from where/when-queries) render as `'in the box'`
  (single-quoted) instead of the bracket form `[in, the box]`.  Other
  multi-arg payloads keep the bracket form.

#### Helper-predicate templates

`_PRED_TABLE` includes situation-aware renderings for axiom helper
predicates that previously fell through to the fallback:

- `next(W, W2)` → `"the situation W is followed by the situation W2"`
- `before(W, W2)` → `"the situation W is earlier than the situation W2"`
- `moved(X, W)` → `"X moved in the situation W"`
- `transferred(O, W)` → `"O was transferred in the situation W"`
- `is_past_world(W)` → `"the situation W is in the past"`

#### Skolem function naming

`proof_utils._skolem_fn_to_name` always includes the function name and
ground args, prefixed by the verb-gerund (when known) or object type:

| Input | Output |
|---|---|
| `["sk0","Mike 1"]` + verb fly | `"the flying event sk0 of Mike 1"` |
| `["sk0","?:X"]` + verb fly | `"the flying event sk0 of X"` |
| `["sk0","Mike 1"]` (no verb, type roof) | `"the roof sk0 of Mike 1"` |
| `["sk0","Mike 1"]` (nothing known) | `"the event sk0 of Mike 1"` |

`_skolem_fn_short_name` returns just `"sk0 of Mike 1"` / `"sk0 of X"` /
`"sk0"`; used for subsequent mentions within a clause via the seen-tracker
in `_intro`.  `_skolem_fn_arg_display` keeps raw entity ids
(`"Mike 1"`, not `"Mike"`) so the Skolem-fn term displays the specific
instance unambiguously.

#### Extension guide

When adding a new predicate to `_PRED_TABLE`:

- Use `e(i)` (which calls `_intro`) for entity / variable args so that
  variable tracking, article injection, and isa-bundling all work.
- Use the raw `args[i]` (bypassing `_intro`) only when the predicate
  contributes the introduction itself (as `has_type` does) — and in that
  case manually mark relevant vars in `_RENDER_CTX.seen` to keep later
  mentions bare.
- For new modal classifiers, add the name to `_MODAL_CONSEQUENT_PREDS`
  to get the "preferred consequent" treatment in pure-negative clauses.

**Public API** (all importable from `proof_render.py`):

- `compute_ambiguity(logic)` — scan clause list for ambiguous entity names [`proof_utils`]
- `compute_skolem_types(proof, logic=None)` — populate Skolem type tables from logic + proof [`proof_utils`]
- `set_entity_map(entity_map)` — set entity display map [`proof_utils`]
- `get_entity_display(key)` — look up display name [`proof_utils`]
- `entity_name(val, with_url, proof_mode)` — format entity for display [`proof_utils`]
- `ans_atom_name(atom)` — format answer atom [`proof_english`]
- `clause_to_str(clause)` — clause → English string [`proof_english`]
- `block_to_english(blocker)` — `$block` → English exception string [`proof_english`]
- `format_clause_logic(clause)` — clause → compact JSON [`proof_logic`]
- `format_clause_traditional(clause)` — clause → traditional logic syntax [`proof_logic`]
- `formula_to_logic(formula)` — FOL formula → traditional syntax [`proof_logic`]

### 5.10 proof_explain.py

**Role:** Builds the full step-by-step proof explanation presented to the user.

**Public API:**

- `build_sentence_map(s1_json) -> dict` — builds `{"sent_S1": "raw text", ...}` from Stage-1
  output; maps each clause name back to the original English sentence it came from
- `format_explanation(answers, sentence_map, show_logic=False) -> str` — main entry point;
  produces the `"Explained:\n\n..."` block for all (non-duplicate) answers; groups proof steps
  under "Sentences used:", "Knowledge used:", and "Proof steps:"
- `ans_display_key(val, askvars=None) -> hashable` — canonical dedup key for an answer value;
  ignores auxiliary world-state arguments

### 5.11 prover.py

**Role:** Interface to the `gk` binary theorem prover.

**Key function:** `call_prover(logic) -> str`

1. Serialises the GK clause list to a JSON string using `clause_list_to_json` (from `utils.py`).
2. Writes the string to a temporary file.
3. Launches the `gk` binary via `subprocess.Popen` with the temp file plus flags built from
   `globals.options` (axiom files, strategy, time limit, print level, KB flags).
4. Reads stdout, decodes as ASCII, optionally caches the result, removes the temp file.
5. Returns the raw prover output string (JSON).

**Auto strategy selection** (`_auto_strategy`): when no `-strategy` flag is given,
analyses the clause list for equalities with function terms (`$measure_of`, `$theof1`,
`$list`, `$datetime`) or `less_measure` atoms.  When found, selects the `unit` strategy
(`-strategytext`) which handles equational reasoning better than the default
`negative_pref/posunitpara` strategy (empirically better than
`negative_pref/knuthbendix_pref` on complex multi-existential queries).
Printed with `-debug`.  Alternate strategies worth trying on timeout-suspected cases:
`{"strategy": ["unit"], "query_preference": 1}` and
`{"strategy": ["query_focus"], "query_preference": 1}`.

**Prover seconds auto-estimation** (`_estimate_seconds`): when no CLI `-seconds` is
given, counts distinct world constants (W0, W1, ...) in the clause list and scales
the time limit from an empirical table (2x safety multiplier).  Examples: ≤6 worlds →
2s (default), 7 → 4s, 8 → 10s, 9 → 20s, 10 → 60s, 11 → 300s.  CLI `-seconds N`
always overrides the estimate.

Key paths (from `globals.py`):

```
../gk/gk                      binary
llmpipe/axioms_std.js          default axiom file
../gk/gk_name_number.txt       name→number data
../gk/gk_taxonomy_packed.txt   taxonomy data
```

### 5.12 pretty.py

**Role:** Human-readable pretty-printing of JSON structures.

**Key functions:**
- `pp_logic(obj, file=None)` — print a GK clause list
- `pp_stage1(obj, file=None)` — print Stage-1 ASU JSON
- `pp_stage2(obj, file=None)` — print Stage-2 logic JSON
- `pp_str(obj) -> str` — return the formatted string (used by the three above)

**Layout (Style B):** Lists are kept on one line when they fit within 100 columns.  When
expanded, the first element follows the opening `[` immediately; subsequent elements are indented
to align with the first.  Consecutive closing-bracket-only lines are merged onto one line.

**`noquotes` mode** (`pretty.noquotes = True`): suppresses quotation marks and replaces spaces
in strings with underscores — more readable for debugging.

### 5.13 cache.py

**Role:** SQLite-backed cache for LLM responses and prover results.

Three separate tables in `cache.db`:
- `llm_cache` — keyed on `(provider, version, temperature, seed, max_tokens, sysprompt, input)`
- `proof_cache` — keyed on the prover parameter string
- `parse_cache` — for parsed results (future use)

Key functions: `get_llm_from_cache`, `add_llm_to_cache`, `get_proof_from_cache`,
`add_proof_to_cache`, `clear_all_caches`.  LLM caching is controlled by
`globals.options["use_llm_cache_flag"]`.  Proof caching is off by default and enabled with
`-cache`.

### 5.14 globals.py

**Role:** Global configuration, file paths, and the `options` dict.

Contains only what is actually used by the active pipeline:

**`options` dict** — runtime behaviour flags:

| Key | Default | Effect |
|-----|---------|--------|
| `use_llm_cache_flag` | `True` | Use SQLite LLM cache |
| `use_cache_flag` | `False` | Use prover result cache |
| `debug_print_flag` | `False` | Print debug info |
| `prover_print_flag` | `False` | Print prover I/O |
| `show_logic_flag` | `False` | Print parsed logic |
| `prover_explain_flag` | `False` | Print proof explanation |
| `prover_nosolve_flag` | `False` | Parse only, skip prover |
| `prover_seconds` | `2` | Prover time limit |
| `nocontext_flag` | `False` | Disable $ctxt injection |
| `noexceptions_flag` | `False` | Disable defeasible $block |
| `noproptypes_flag` | `False` | Strip degree predicates |
| `nokb_flag` | `True` | Skip shared-memory KB |

**File paths** (computed relative to `llmpipe/`):

```python
cache_db_name     = "cache.db"
prover_fname      = "../gk/gk"
prover_axiomfile  = "axioms_std.js"
prover_datafolder = "../gk"
prover_infile     = "gk_infile.js"
prover_params     = ["-defaults", "-confidence", "0.1", "-keepconfidence", "0.1"]
```

**`set_global_options(newoptions)`** — merge a dict into `options`; called by `solve.py` with
the parsed CLI flags.

### 5.15 utils.py

**Role:** Shared utility functions used across the pipeline.

- `debug_print(label, data=None, flag=None)` — prints a labelled debug message when `flag` is
  truthy.  If `flag` is `None` (default), falls back to `globals.options["debug_print_flag"]`.
  Pass an explicit boolean to use a different flag (e.g. `llmcall.py` passes its module-level
  `debug` and `calldebug` variables).  Formats `data` intelligently: lists are printed one
  element per line (nested lists indented), dicts show key/value pairs.

- `clause_list_to_json(logic) -> str` — converts the Python GK clause list to a JSON string
  suitable for passing to the `gk` binary.  Uses `json.dumps` with compact separators.

### 5.16 linguistics.py

**Role:** Pure English linguistic heuristics used by `proof_english.py` for human-readable output.
No dependency on proof state or any other pipeline module.

- `indef_article(word) -> str` — returns `"an"` before vowel sounds, `"a"` otherwise
- `conjugate_verb(v) -> str` — third-person singular present tense (`fly` → `flies`)
- `make_comparative(adj) -> str` — comparative form (`nice` → `nicer`, `beautiful` → `more beautiful`)
- `to_gerund(verb) -> str` — gerund form (`run` → `running`, `bite` → `biting`)

### 5.17 stage_sanity.py

**Role:** Structural sanity checks for Stage-1 ASU JSON and Stage-2 logic JSON, used by
`llmparse._maybe_sanity_retry` to detect LLM output errors that the Stage prompts explicitly
forbid (or that the downstream pipeline cannot handle) and trigger a corrective re-call of
the same LLM.  See §7.8 for the retry-loop semantics and motivation.

**Module layout:** `stage_sanity.py` is a thin façade re-exporting the public API from four
files — `stage_sanity_core.py` (`Issue`, `issue_fingerprints`, `safe_json`),
`stage_sanity_s1.py` (`check_stage1`), `stage_sanity_s2.py` (`check_stage2`,
`format_retry_suffix`, the `aggressive_repair` flag), and `stage_sanity_guards.py`
(`check_unsatisfiable_guards`, `check_stage2_id_coverage`).  Importers use `stage_sanity`
unchanged.

**Public API:**

- `Issue(kind, location, description, evidence)` — frozen dataclass representing a single
  detected problem.  `kind` is the category (e.g. `free_variable`); `(kind, location)` is the
  fingerprint used to detect persistence across retries; `description` and `evidence` are
  shown to the LLM in the corrective prompt.
- `check_stage1(s1_json) -> list[Issue]` — runs all registered Stage-1 checks
  (`missing_wh_placeholder`, `entity_used_as_location`, `pronoun_as_class`,
  `spurious_wh_placeholder`).
- `check_stage2(logic, s1_json=None) -> list[Issue]` — runs all registered Stage-2 checks
  (see table below).
- `format_retry_suffix(issues, flawed_parsed) -> str` — builds the text appended to the
  original stage input when re-calling the LLM.  Structure: shows the LLM's flawed output,
  lists the issues (kind + location + description), then asks for a corrected JSON.
- `issue_fingerprints(issues) -> frozenset[tuple[str,str]]` — persistence-comparison helper.

**Registered Stage-2 checks:**

| Check | Kind | Triggers on | Example case |
|---|---|---|---|
| `_check_stage2_free_variables` | `free_variable` | Any atom-argument string that matches a binder name (`forall`/`exists`/`ask`) elsewhere in the formula but is outside the binder's scope. | Case 259 — donkey anaphora |
| `_check_stage2_misplaced_meta_tense` | `state_time_in_body` | `["state time", W, TENSE]` atom inside a `holds`/`question`/`ask` body.  Tense metadata belongs at package level, not as a body literal. | Case 37 |
| `_check_stage2_dropped_specific_noun` | `dropped_specific_noun` | Query `exists VAR, (and ... isa(CAT, VAR) ...)` where Stage-1 has a unique generic entity with `category=CAT` and `id != CAT` — the query lost the specific noun. | Case 136 |
| `_check_stage2_arities` | `wrong_arity` | Atom whose arity disagrees with the declared Stage-2 signature (whitelist of 27 predicates: `isa/2`, `has property/2`, `has type/2`, `has actor/2`, `has part/2`, `is rel2/3`, `has degree property/4`, `has degree rel2/5`, `typical/1`, etc.). | Scattered |
| `_check_stage2_event_shapes` | `event_missing_activity_isa` / `event_missing_role` | Event variable E used as first arg of `has_type(E, VERB)` must have `isa("activity", E)` AND at least one thematic-role atom (any of `has_actor`, `has_target`, `has_recipient`, `has_source`, `has_destination`, `has_location`, `has_instrument`, `has_manner`, `has_direction`, `has_time`, `has_beneficiary`, `has_accompaniment`, `has_path`, `has_result`, `has_topic`, `has_cause`, `typical`) in the same `and` conjunction.  Either missing item is its own issue. | — |
| `_check_stage2_inner_content_event_time` | `inner_content_event_missing_time` | 5-gate criterion: var V appears as 2nd arg of `["has content", E1, V]` AND has a `has_type` atom AND has no `has_time` atom AND has no modal classifier (capability/typical/necessity/obligation/volition/intention/expectation/speech_act) AND the Stage-1 unit containing this `@id` has `time` set to past/present/future.  Catches gemini's intermittent omission of `has_time` on inner content events of speech-act reifications, which would prevent the `axioms_std.js` §5.2 factive bridge from unifying the derived `actuality(E2)` with the question's tensed event.  Skips modal-classified and tenseless-unit cases. | Case 159 — gemini |
| `_check_stage2_missing_question` | `missing_question` | A Stage-1 unit is a query (either `unit.type == "query"` or its parent package's `raw` text contains `?`) but the matching `@id` in Stage-2 has no `question`/`ask` wrapper anywhere in its body — covers both whole-package truncations and `holds`-where-`question`-was-expected. | LLM truncation on multi-sentence inputs |
| `_check_stage2_entity_id_typos` | `entity_id_typo` | An entity ID `XYZ N` whose first word has a stray prefix that is itself a prefix of another ID's first word in the same problem (max 4 extra chars).  Catches gemini's "fr fridge 3" vs "fridge 3" pattern where one mention picks up a stray article/preposition fragment. | Case 152 |
| `_check_stage2_possessive_without_ownership` | `possessive_without_ownership` | A possessive cue (determiner `their`/`his`/`her`/`its`/`our`/`your`/`my` + noun, or genitive `'s` + noun) appears in the Stage-1 unit text, a `"Whose X?"` wh-question (`["ask", VAR, …]` with VAR in an ownership atom) solves for the owner, yet the assertion side carries **no** ownership atom at all (`have` / `has part` / ownership `is rel2` / relational genitive `is rel2 "… of"`).  The possessive was dropped, so the owner is never stated.  Retry asks for an explicit `have(OWNER, THING)`.  Tightly gated — fires only on that exact shape. | Case 154 |
| `_check_stage2_vacuous_tautology_assertion` | `vacuous_tautology_assertion` | An assertion-side (non-`question`/`ask`) `["implies", A, B]` whose antecedent `A` is structurally identical to `B` — a vacuous "if P then P" — AND a `question`/`ask` package is also present.  Signals a conditional QUESTION mis-segmented (on its comma) into an asserted tautology plus a bare-consequent question.  Retry asks for a single `question(implies(A,B))`.  Never descends into `question`/`ask`, so the correct `question(implies(P,P))` is not flagged. | Case 384 — gpt |
| `_check_stage2_measure_vs_degree_rel2` | `measure_degree_rel2_conflict` | The same property string is encoded BOTH as `$measure_of(P,…)` and `has_degree_rel2(P,…)` in one output — the equality/comparison split across two disconnected representations (no axiom bridges `has_degree_rel2` to `$measure_of`).  Retry asks to put the comparison on the measure scale (`=`/`>`/`<` on `$measure_of`).  Not measurability-gated (the LLM already chose `$measure_of`). | Case 555 — claude |
| `_check_stage2_comparative_as_degree_property` | `comparative_as_degree_property` / `comparative_as_degree_property_nonmeasurable` | A comparative cue in the Stage-1 text (`"as P as"` / `"P-er than"` / `"more\|less P than"`) where `P` is in a UNARY `has_degree_property` with no two-argument encoding — the binary comparison was lost.  Splits on `_MEASURABLE_ADJS`: a MEASURABLE dimension (tall/heavy/long/…) → retry to `$measure_of` `=`/`>`/`<` (case 555 gpt); a gradable but NON-measurable property (interesting/…) → retry to the binary `has_degree_rel2(P,A,B,…)` (case 559 gpt, refuted by the `has_degree_rel2` asymmetry axiom; asks to resolve an elliptical question's implicit referent). | Cases 555 / 559 — gpt |
| `_check_stage2_multiword_property` | `multiword_property` | A `has property`/`has degree property` whose first argument (the property name) is a phrase of MORE THAN two words — e.g. `"filled with water"`, `"afraid of mice"` — collapsing a relation + its argument(s) into one opaque adjective.  Retry says to conceptually split it into meaning components and represent the input with more detail (embedded noun as its own entity, relation as the right predicate).  Two-word compounds ("dark blue") are left alone. | Cases 673 / 1620 — gpt |
| `_check_stage2_either_or_not_xor` | `either_or_not_xor` | The source text uses "either" (detected in `s1_json` raw/unit text) AND the Stage-2 disjunction is NOT a bare strict `xor` — i.e. an inclusive `["or", A, B]` (loses exclusivity) or any `["or"\|"xor"]` nested under `["normally", …]` (a defeasible xor whose "not both" clause self-blocks).  Retry asks to encode "either A or B" as strict `["xor", A, B]` — never inclusive `or`, never wrapped in `normally`.  A bare top-level `xor` (claude/gpt) does not fire. | Case 571 — gemini (inclusive or) / deepseek (`normally(xor)`) |

**Registered Stage-1 checks:**

| Check | Kind | Triggers on | Example case |
|---|---|---|---|
| `_check_stage1_missing_wh_placeholder` | `missing_wh_placeholder` | A query unit whose text or parent raw begins with a wh-question word but has no entity flagged `wh_placeholder=true`.  The retry prompt asks the LLM to add the placeholder and apply the question-word transformation. | Wh-questions in any LLM |
| `_check_stage1_entity_used_as_location` | `entity_used_as_location` | A unit whose `location` field is a concrete-entity ID declared in the same unit's entities list.  The unit-level `location` field is the SCENE / place of the situation, NEVER a concrete object that participates in a spatial relation as the secondary argument.  The retry prompt explains the distinction and asks the LLM to either move the spatial info into the action's roles (with `location_prep`) or omit `location` entirely. | Case 148 — gemini and gpt put `location: "table 3"` / `"floor 4"` at unit level, polluting `$ctxt` position 3 |
| `_check_stage1_pronoun_as_class` | `pronoun_as_class` | A **query** unit declares an entity whose id is an indefinite person-pronoun (`someone`/`somebody`/`anyone`/`anybody`/`everyone`/`everybody`, trailing number stripped).  Stage-2 then emits a phantom `isa("someone", X)` class that nothing populates → the question is unprovable.  The retry asks for the common noun `person`.  **Gated to query units only** — in a rule/assertion ("If someone is X then Y") the pronoun is a universal bound variable and a retry damages the parse (regressed 1390/1608 before the gate). | Case 626 — gpt |
| `_check_stage1_spurious_wh_placeholder` | `spurious_wh_placeholder` | A **query** unit carries a `wh_placeholder` entity but its text (a) leads with a yes/no auxiliary (`did`/`does`/`is`/`are`/`was`/`were`/`has`/`have`/`can`/`will`/…) AND (b) contains **no** wh-word anywhere.  The yes/no question was mis-flagged as wh, so Stage-2 emits an `ask X` (askvars) query that needs a determinate witness an indefinite/disjunctive subject cannot give.  The retry asks for a plain yes/no encoding (drop the placeholder, no "Which …" rewrite).  The two-part gate leaves genuine wh-questions phrased with a leading auxiliary alone, e.g. "Is Ellen afraid of whom?" (1343). | Case 626 — claude |
| `_check_stage1_split_conditional` | `split_conditional_sentence` | A package whose `raw`, stripped, ENDS WITH a comma and whose first word is a subordinating conjunction (`if`/`when`/`while`/`unless`/…), with a FOLLOWING package holding the main clause — a single conditional/adverbial sentence wrongly split at its internal comma.  Stage-2 then encodes the fragment as a (vacuous) rule plus a separate query, so the whole conditional is never asked.  Retry asks to keep the comma-joined clauses in ONE package / one conditional query unit, which then lets Stage-2 emit `question(implies(…))` directly. | Case 384 — gpt |

**Conventions:**

- Checks are pure functions over the parsed JSON; they do not mutate or consult other
  pipeline state.
- When a check also has a downstream post-processing rescue (e.g., `strip_tense_has_time` for
  misplaced meta-tense, `inject_query_specific_noun_isas` for dropped specific nouns), the
  sanity check takes priority: a successful retry produces cleaner Stage-2 output, and the
  post-processor silently no-ops on the corrected formula.
- Checks that overlap with benign LLM-prompt examples are deliberately omitted.  For
  instance, `["has time", E, "past", "in"]` is labelled WRONG in the Stage-2 instructions
  but appears in the examples file; LLMs emit it consistently, so no check fires —
  `strip_tense_has_time` handles it cheaply.

---

## 6. Prompt files

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
| `prenorm_full.txt` | Pre-Stage-1 wording-normalisation prompt (`-prenorm`, §12.1) |
| `combined_*_instructions_full.txt`, `combined_examples_*.txt`, `combined_*_checklist_full.txt` | Combined single-stage constructions (`-combined-*`, §12.2); per-file descriptions in `prompts/README.md` |
| `folio_directanswer_instructions[_noworld].txt` | Direct-answer prompts (`-directanswer`, §12.3) |
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

## 7. Key algorithms in logconvert.py and lc_clausify.py

### 7.1 Package extraction

`_extract_package_ctx(package)` (in `logconvert.py`) unwraps a Stage-2 PACKAGE and returns
`(is_question, formula, confidence, world, location, knower, tense)`.

The PACKAGE shapes it handles:
- `["holds", W, F]` → `is_question=False`, `formula=F`, `world=W`
- `["question", F]` → `is_question=True`, `formula=F`
- `["ask", VAR, F]` → `is_question=True`, `formula=["ask",VAR,F]` (kept whole for wh-handling)
- `["and", PKG, ["@p","Sx",P], ["state time",W,T], ...]` → recurse into the main sub-package;
  collect confidence, tense, location, knower from siblings

After extraction, `_convert_id_package` overrides `tense`, `world`, and `location` with data
from the matching Stage-1 ASU (when `asu_index` is available).  Stage-1 data is authoritative
because it is produced closer to the English source.  The actual question/assertion logic is
delegated to `_process_question` (wh-/yes-no dispatch) and `_process_assertion` (confidence
handling + clausification).

### 7.2 FOL to CNF clausification

`clausify(formula)` (in `lc_clausify.py`) converts a first-order formula into conjunctive normal
form through five passes:

1. **`_implies_to_or`** — eliminate `implies`, `equivalent`, `xor`:
   - `implies(A,B)` → `or(not(A), B)`
   - `equivalent(A,B)` → `and(implies(A,B), implies(B,A))`, then recurse
   - `xor(A,B)` → `and(or(A,B), or(not(A),not(B)))`
   - Does not recurse inside `_opaque_wrappers` (i.e. `normally`)

2. **`_push_neg`** — push negations inward to reach Negation Normal Form (NNF):
   - De Morgan: `not(and(...))` → `or(not(...),...)`, etc.
   - Quantifier duality: `not(forall X, P)` → `exists X, not(P)`
   - Atom negation: toggle the `"-"` prefix on the predicate name
   - `normally` treated as opaque: `not(normally(F))` → `"-normally"(F)`

3. **`_expand_normally` pass 1** — push `normally` inside complex bodies before Skolemisation:
   - `normally(exists X, B)` → `exists X, _push_normally_inside(B)`
   - `normally(and(A1,...,An))` → `and(A1,...,An-1, normally(An))`
   - Simple `normally(atom)` is left for pass 2

4. **`_skolemize(frm, universal_vars, varmap)`** — eliminate existential quantifiers:
   - `forall X, F` → recurse with `X` added to `universal_vars`
   - `exists X, F` → replace `X` with a Skolem term:
     - No universal vars in scope → Skolem constant `"sk0"`, `"sk1"`, …
     - Universal vars in scope → Skolem function `["sk0","?:X",...]` applied to those vars
   - `forall` is stripped (variables become free, i.e. implicitly universally quantified in GK)

5. **`_distribute`** — distribute `or` over `and` to reach CNF:
   - `or(and(A,B), C)` → `and(or(A,C), or(B,C))`
   - Recursive until no `or` wraps an `and`

6. **`_expand_normally` pass 2** — expand remaining `normally(atom)` into `$block` clauses:
   - See §7.3 below

7. **`_extract_clauses`** — collect all flat clauses from the resulting `and` tree

### 7.3 Defeasible expansion

After Skolemisation and CNF distribution, every `normally(atom)` appears inside an `or` clause
alongside conditions (negative literals `-isa bird ?:X`) and other conclusions.

`_expand_normally` pass 2 processes such an `or` clause:
1. Separate negative literals (conditions, start with `"-"`) from positive literals (conclusions).
2. Use the **last positive literal** as the head to be blocked.
3. Compute priority `["$", CLASS, N]`:
   - CLASS = class from the last `-isa` condition (e.g. `"bird"`), or `"$generic"` if no `-isa`
   - N = number of non-`isa` negative conditions + 1 (more specific rules get higher N)
4. Append `["$block", priority, ["$not", head]]` to the clause.

Result for `normally(["has part","?:X","wing"])` inside `["-isa","bird","?:X"]`:
```
["-isa","bird","?:X"], ["has part","?:X","wing"],
["$block",["$","bird",1],["$not",["has part","?:X","wing"]]]
```

A plucked-bird exception would generate priority `["$","bird",2]` (higher specificity), which
GK uses to defeat the general bird default.

With `-noexceptions`, the `$block` is suppressed and `normally` becomes equivalent to a strict
implication.

### 7.4 Context injection ($ctxt)

After clausification, `_inject_ctxt_into_objs` (in `logconvert.py`) appends a
`["$ctxt",T,W,L,K]` term to every eligible predicate atom in every `@logic` clause.

The four `$ctxt` components per ASU:

| Component | Rules | Situational facts | Questions |
|-----------|-------|-------------------|-----------|
| tense T | fresh free var | Stage-1 `time` or `"present"` | Stage-1 `time` or fresh var |
| world W | fresh free var | Stage-1 `pre_state` or W from `holds` | Stage-1 `pre_state` or fresh var |
| location L | fresh free var | Stage-1 `location` or fresh var | Stage-1 `location` or fresh var |
| knower K | fresh free var | mental holder or fresh var | mental holder or fresh var |

Rules use fresh free variables for all four components so they match facts from any time/world.
Situational facts use concrete world/tense values so they match only facts in the same context.

Context injection can be disabled globally with `nocontext_flag`.  In that mode the
constant `"$c"` is injected as the last argument of every eligible atom (instead of
a `$ctxt` term), so axioms with `?:Ctxt` still unify while axioms with explicit
`$ctxt(...)` patterns become inert.

#### Question-specific past↔present tense bridges

For each question package, after `$ctxt` injection, `lc_ctxt.build_question_tense_bridges`
collects present-tense or past-tense stative literals from the question and emits one
specialized bridge axiom per unique (predicate, args) signature.  Two question shapes
are scanned: a `$defq`-wrapped question exposes the stative goal as a **negative**
literal in its body→defq `@logic` clauses, while a **direct** `["@question", FORMULA]`
(an unguarded question that never became a `$defq`) carries it as a **positive** literal
— scanned by `_collect_question_goal_signatures`, since the goal becomes
`-pred(present)` once the prover negates it for refutation.  Without the direct-question
scan, an unguarded stative question (e.g. "who does the backpack belong to?" →
`@question: have(X, present)`) would miss the persistence bridge a guarded one receives.
The emitted bridge:

```
[-pred(args, $ctxt(opposite_tense, ?:W, ...)),
  pred(args, $ctxt(question_tense, ?:W, ...)),
  $block(0, $not(pred(args, $ctxt(question_tense, ?:W, ...))))]
```

Entity arguments are pinned to the constants from the question; free variables in the
question literal become fresh variables in the bridge.  Confidence per predicate:
0.97 for `have`, 0.95 for `is rel2` and `has degree rel2`, 0.99 for the others
(`has property`, `has degree property`, `has part`, `can`).

This replaces the disabled global Section 6a same-world tense bridges in
`axioms_std.js`.  Pinning entities keeps the search space small (the bridge can only
fire on facts about those specific entities), avoiding the prover slowdown caused by
the global axioms while bridging the same set of tense mismatches between
past-tense assertions and present-tense questions (and vice versa).

Scope: bridges are generated for **question goals only**.  A stative literal that needs
cross-tense matching in a **rule premise** or a `$block` blocker is not bridged — see
HARD_CASES_MEMO.md "Stative tense-persistence bridges" for the gap and the (unlanded)
generalisation.

##### Stable-adjective assertion-side persistence (`inject_stable_adjective_persistence`)

The question-pinned bridges above cover the **question's** predicates.  They do **not**
cover an **assertion-side** property tensed at past whose value the question reaches only
through another axiom (e.g. a mutex).  Case 911 ("The man whom John saw **is** tall. Is the
man short?"): claude/gpt keep the sentence as one unit tagged `time=past`, so the present
copula "is tall" is contaminated by the embedded past relative ("whom John **saw**") →
`tall@past`.  The question is `short@present`; the tall/short mutex binds both literals to a
single shared `$ctxt` variable, so `tall@past` and `short@present` never contradict → Unknown.
The disabled §6a global bridge would have carried `tall@past → tall@present`, and the
question bridge only covers `short` (the question predicate), not the asserted `tall`.

`lc_post_inject.inject_stable_adjective_persistence` fills this gap.  For each
**individual-level (stable)** property present as a `has_property`/`has_degree_property`, it
injects a defeasible (0.95) same-world `past@W → present@W` persistence axiom with a
`$block($not present)` override, in both predicate forms — so a past stable property reaches
the present-tense reading.  `_STABLE_ADJS` is a curated 83-adjective list
(dimension/size/build, age, strength, mental/ability, character, beauty, value);
`_STABLE_PERSIST_PROPS` adds the **color/shape/material** value-sets (reused from the
attribute families / `data_exclusions`), 130 total.  **STAGE-LEVEL** (temporary) adjectives —
hot/cold, wet/dry, hungry/tired, open/closed, broken, full/empty, dirty/clean, sick, new —
and **taste** (gradable/perishable) are deliberately EXCLUDED: they should not persist.
Like the question bridges, it is dynamic (one pair of axioms per stable property present) and
gated, so the search space stays small — but it is keyed on the **assertion-side** stable
property, the complementary half of the question-pinned bridges.  Closes case 911 (claude/gpt
2/4 → 4/4 via `tall@past → tall@present` + the tall/short mutex).

### 7.5 Gradable property normalisation

`_normalize_gradable_predicates(result)` (in `logconvert.py`) iterates over all clauses and
applies `_norm_grad_frm` to every predicate atom:

- `has degree property PROP ...` where PROP is **not** in `_GRADABLE_PROPS`
  → convert to `has property PROP ENTITY` (drop degree/relclass)
- `has property PROP ...` where PROP **is** in `_GRADABLE_PROPS`
  → convert to `has degree property PROP ENTITY "none" RELCLASS` (add degree/relclass;
  RELCLASS = fresh free variable)
- `has degree property ... RELCLASS` where RELCLASS is `"entity"` or `"none"`
  → replace with a fresh free variable (neither carries a useful comparison-class constraint,
  and leaving them as constants would block unification against meaningful relclasses like
  `"person"`)

The same logic applies to `has degree rel2` vs `is rel2`.

After this normalisation, `_strip_isa_entity` removes any remaining `["isa","entity",X]` or
`["-isa","entity",X]` literals, since "entity" is universal:
- Positive `isa entity X` makes a clause a tautology → remove the entire clause
- Negative `-isa entity X` is always false → remove just the literal

### 7.6 Population facts

`populate_clauses(items)` (in `lc_post_population.py`, using helpers from `lc_questions.py`) makes one
pass over all Stage-2 items before clausification and collects *population facts*: `isa TYPE
ENTITY` atoms for every concrete entity that appears as an argument of a `forall`-quantified
rule.  For example, if a rule says "all birds can fly" and a concrete entity `tweety 1` appears
as an `isa bird tweety 1` fact, that fact must be inserted before the question so the prover can
use it.

Population facts are tagged with `"@sourcetype": "populate"` internally (stripped before the
prover sees them) so that `_coerce_relclass` can treat them differently from question clauses.

**Compound witnesses.** When a rule's antecedent is a conjunction binding the same variable
to multiple atoms, `_scan_compound_antecedent` records a *compound witness* and the population
emits an intersection entity satisfying ALL the conjuncts simultaneously. Two flavors today:

- **Spatial**: `[isa, TYPE, X] ∧ [is_rel2/has_degree_rel2, prep, X, ground_target]` →
  `$some_<type>_<prep>_<location>` with both atoms.
- **Adjective**: `[isa, TYPE, X] ∧ [has_property, ATTR, X]` (or `has_degree_property` with
  intensity/relclass) → `$some_<attr>_<type>` with both atoms. Without this, defeasible
  rules of the form "ADJ TYPEs are not P" have no concrete witness for the prover to apply
  them to (case 74: "Red cars are not nice" was being closed via the more general
  "Cars are nice" rule alone, returning "Probably true" instead of the expected False).

### 7.7 Stage-2 rewrites and modifications

The pipeline applies several transformations to the raw Stage-2 LLM output before and after
clausification.  These compensate for LLM inconsistencies, enforce pipeline conventions, and
bridge representation gaps.

**Pre-clausification rewrites** (on the raw Stage-2 JSON formula, before `clausify`):

| Rewrite | Where | Example | What it does |
|---------|-------|---------|-------------|
| Degree presupposition injection | `lc_rewrites.inject_degree_presuppositions` | "John is not very big" → adds "John is big" (unmarked degree) alongside the negated "very big" | `["not",["has degree property",P,E,"high",C]]` → `["and",["has degree property",P,E,"none",C],["not",...]]` |
| Stative event rewriting | `semnormalize.rewrite_stative_events` | "John had a car" encoded as an event → rewritten to direct `have(john,car)` | Replaces Davidsonian event encoding of stative verbs (have, own, like, love, etc.) with direct predicates.  Safety: only rewrites when the event variable has no extra properties (has_location, etc.) |
| `@time` stripping | `lc_ctxt.strip_time_wrappers` | "John was tall" — the past-tense `@time` wrapper becomes a `$tense` sentinel controlling the tense slot in `$ctxt` | Converts `["@time","past",ATOM]` wrappers into `$tense` sentinels on the atom |
| Entity category injection | `lc_entity_isa.build_entity_category_clauses` | "John is an elephant" — Stage-1 says John's category is "person", so `isa(person, John 1)` is added even though Stage-2 only emits `isa(elephant, John 1)` | Adds `isa(CATEGORY, ENTITY)` facts from Stage-1 entity annotations.  Skipped when the entity already has a **positive-polarity** isa in Stage-2 (`collect_positive_isa_entities` tracks polarity through connectives, negation, implications, and low-confidence packages).  Entities in negated or low-confidence contexts are NOT skipped — they need the injection.  Exact duplicates with `sent_S*` clauses are removed by `_dedup_entity_clauses`. |
| Entity base-word isa | `lc_entity_isa.build_entity_category_clauses` | "A man had a car" — entity `man 1` has category "person", but the base word "man" is also a type; adds `isa(man, man 1)` alongside `isa(person, man 1)` | For concrete entities with a lowercase base word different from the category, injects `isa(BASE, ENTITY)` so queries using the descriptive type word can match |
| Compound subsumption | `lc_post_normalize.build_compound_subsumption` | "Baby birds do not fly" — adds a rule that baby birds are birds, so general bird rules can apply to them | Adds `isa(BASE, X) :- isa(COMPOUND, X)` rules for compound types |

**Post-clausification modifications** (on the GK clause list):

| Modification | Where | Example | What it does |
|-------------|-------|---------|-------------|
| `$ctxt` injection | `lc_ctxt.inject_ctxt_into_objs` / `inject_ctxt_question` | "John was tall" → atom gets `$ctxt(past,W0,?,?)` anchoring it to the past in world W0 | Appends `["$ctxt",T,W,L,K]` to eligible predicate atoms.  Rules: all-free-var.  Assertions: concrete world/tense.  Questions: see next row (§7.4) |
| Descriptive/stative/dynamic split | `lc_ctxt.inject_ctxt_question` | "Did the man have the red car which a woman bought?" — `bought` events and `red` property each get independent free-var worlds; stative `have` also gets free-var world; only dynamic event predicates (if matrix) keep the query's world | Three-way $ctxt world dispatch in `$defq` questions: (1) **descriptive** atoms (isa, event atoms, properties when a main relation is present) each get an independent free-var world; (2) **stative matrix** predicates (have, can, has part) get free-var world — persistent states don't need concrete world anchoring; (3) **dynamic matrix** predicates (is_rel2, properties when no main relation) keep the query's world.  `_question_has_main_relation` detects whether properties are restrictive modifiers.  Each descriptive/stative atom gets its OWN fresh world variable to avoid forced co-unification across different world states |
| Gradable normalisation | `lc_post_normalize.normalize_gradable_predicates` | "John is big" — LLM used `has property(big,...)` but "big" is in the gradable whitelist → upgraded to `has degree property` | Whitelist-based `has property` ↔ `has degree property` conversion; replaces `"entity"` and `"none"` relclass with free variables (§7.5) |
| `isa entity` stripping | `lc_post_normalize.strip_isa_entity` | "Every entity that is big is strong" — `isa(entity,X)` is always true, so the clause is a tautology → removed | Removes tautological `isa(entity,X)` literals (§7.5) |
| RELCLASS coercion | `lc_post_normalize.coerce_relclass` | (question) "Is John big?" — query uses relclass "person" (John's category) but the rule uses "bear" → relclass replaced with free variable; (assertion) "John is a nice big bear. John is nice." — stage-1 split loses the "bear" context and tags "nice" with relclass "animal" while the rule expects "bear" → assertion's "animal" replaced with a free variable | Fixes relclass mismatches. Question-side: `has degree rel2` always coerces to free var; `has degree property` coerces in two cases — case_a: the relclass IS one of the entity's isa classes but no rule uses it as a relclass for this property (spurious category); case_b (case 1418 gemini): the relclass is NOT one of the entity's isa classes but one of the entity's actual classes IS used as a relclass for this property by a rule (the question used a super/sibling category, e.g. "animal" while the rule's consequent uses "bear"). Assertion-side (new): coerces when the fact's relclass is either (a) one of the entity's multiple isa classes while another class of the entity also appears as a rule-side relclass for the same property, or (b) not in the entity's isa classes while some isa class of the entity appears as a rule-side relclass — both symptoms of stage-1 generic-category leakage. `prop_relclasses` is built from both positive and negated literals so rule bodies contribute. |
| `$theof1` definite rewrite | `lc_post_reify.rewrite_definites` | "The father of John is nice" — `"the father 2"` → `["$theof1","father","John 1",CTXT]` throughout all clauses; `is_rel2` clause removed; per-relation `isa`/`is_rel2` bridge axioms generated as `frm_theof`; grounded `have(arg,$theof1,ctxt)` fact emitted for the concrete owner | Replaces flat entity IDs for definite functional descriptions with canonical function terms so that "the father of John", "John's father", and wh-queries all refer to the same term.  Triggered by Stage-1 `definites` field.  Primary: matches `is_rel2` clause.  Fallback: matches `have` + `isa` pair.  The formerly-universal `have` bridge in `axioms_std.js` (`[have, ?:S, $theof1(?:R,?:S,?:C), ?:C]`) has been removed because its free `?:S` let the prover satisfy any wh-possession query with a free-variable witness; `rewrite_definites` now emits the needed grounded possession fact directly.  **Chain-rewrite guard:** `_find_is_rel2_match` skips any `is_rel2` atom whose value-slot already holds a `$theof1` term — a previous pass has already reified this slot, and a second pass with a different `type_base` would silently overwrite the existing type label.  This is the case-79 sister/brother trap: with two definites pointing to the same entity but using different relation types ("Sara, the sister of Mike" + "Sara is the brother of Mike?"), the second pass would otherwise rewrite `$theof1("sister",...)` → `$theof1("brother",...)` and break downstream mutex reasoning. |
| Possessive `have` inference | `lc_post_have.add_possessive_have` | "The handle of the fork" — `is_rel2(handle of, fork, handle)` + `isa(handle, handle)` → `have(fork, handle)` | Infers `have(Y,E,CT)` from possessive `is_rel2` patterns.  Handles ground entities, Skolem functions, and `$theof1` terms.  For rule clauses with guard literals (e.g., `[-isa,elephant,?:X]`), generates conditional `have` with the same guard.  Skips `@name=frm_theof` clauses (the universally-quantified per-relation schema axioms) because processing them would regenerate the universal have bridge that was removed for free-variable-witness reasons (see `$theof1` definite rewrite row above). |
| `have` → `has_part` bridge for typed body-part nouns | `lc_post_have.add_haspart_for_typed_have` | Rule "If an animal has a trunk, it is an elephant" Stage-2-encoded with `-has_part(?:X,?:Y,Ctxt)` and `-isa(trunk,?:Y)`; fact "John has a long trunk" Stage-2-encoded as `have(John 1, trunk 1, Ctxt)` + `isa(trunk, trunk 1)` → emit `has_part(John 1, trunk 1, Ctxt)` so the rule fires (case 207). | **Conservative, problem-local bridge.**  Stage-2 LLM is inconsistent: generic universal claims ("Elephants have trunks") use `has_part`, but specific instance claims with adjectives ("John has a long trunk") often use `have` for some LLMs (gemini, gpt) — which then fail to unify with has_part-using rules.  Pass 1 walks rule clauses and collects the set of types T paired with `-has_part(?:X,?:Y)` AND `-isa(T,?:Y)` for the same `?:Y`; if empty, the bridge does nothing.  Pass 2 collects explicit `isa(T, E)` facts for ground/Skolem entities.  Pass 3 walks single-atom positive `have(X, Y, Ctxt)` clauses; for each, looks up Y's type (explicit isa first; else `_parse_entity_name_type` fallback peels off Stage-2's naming convention "trunk 1" → "trunk", "sk0_trunk" → "trunk") and emits `has_part(X, Y, Ctxt)` only when the type intersects the rule-collected set.  Safe under the subtype rule in `axioms_std.js` because that rule requires `isa(Y1, Y2)` where Y1 is a class with subtypes; specific entities are not classes so the inheritance never propagates back to a class. |
| `have` → `has_part` axiom bridge | `lc_post_have.inject_have_to_haspart_axioms` | Rule "Elephants do not have wings" Stage-2-encoded with `-has_part(?:X,?:Y,Ctxt)` and `-isa(wing,?:Y)`; query "Who does not have a wing?" Stage-2-encoded with `-have(?:X,?:Y,Ctxt)` and `-isa(wing,?:Y)` → emit axiom `[-isa(wing,?:Y), -have(?:X,?:Y,?:Ctxt), has_part(?:X,?:Y,?:Ctxt)]` at confidence 0.9; the contrapositive `isa(wing,Y) ∧ -has_part(X,Y) → -have(X,Y)` lets the negative rule body refute the negative query (case 6). | **Axiom-shape counterpart to `add_haspart_for_typed_have`** — same rule-premise scan to collect the gated type set T (a type T qualifies when some rule clause contains both `-has_part(_,?:Y,_)` and `-isa(T,?:Y)` on the same variable), but emits a **universally-quantified axiom** per type rather than a per-fact derivation.  Needed because `add_haspart_for_typed_have` only walks single-atom positive `have` facts, while case 6's `have` atoms live inside multi-literal query clauses (`[have(?:X, sk1(?:X), Ctxt), $defq0(?:X)]`).  Complements `axioms_std.js` §2 which ships only the converse direction `has_part → have`.  **No `$block` guard.**  The standard `$block(0, $not(consequent))` pattern would self-block here: the proof chain requires combining the bridge's positive `has_part` with the rule's negative `has_part`, but that very negative `has_part` is independently derivable, so the block would suppress the bridge before it can fire.  Confidence weighting alone (0.9 × rule confidence) is enough to demote the bridged conclusion below a directly-asserted contradicting fact. |
| Misnested existential hoisting | `lc_rewrites.hoist_misnested_exists` | `[exists E, [and, has_actor(E,X), [exists X, isa(bear,X)]]]` → `[exists E, [exists X, [and, has_actor(E,X), isa(bear,X)]]]` | Pre-clausification fix for assertion formulas.  Detects existential variables used free in sibling conjuncts before their `exists` binding, hoists the binding to wrap the entire conjunction.  Only applies in assertion contexts (from `holds`), with collision checks against enclosing bindings. |
| Tense-valued `has_time` filter | `lc_rewrites.strip_tense_has_time` | `has_time(E, "past", "in")` survives when E is a Davidsonian event variable; same shape on a non-event variable is stripped; in-body `state_time(W, "past")` is always stripped (belongs at the package level) | Pre-clausification narrowing pass.  `["has time", E, "past"|"present"|"future", "in"]` is the canonical shape for grammatical tense on Davidsonian events (instructed by Stage-2 §8.1). The pass scans the tree once via `_collect_event_vars` to identify all variables `X` such that `isa(activity, X)` appears, then strips tense-valued `has_time` only when the first argument is NOT one of those event variables.  Strips misplaced `state_time(W, TENSE)` from formula bodies unconditionally. |
| Negative tense-agreement `has_time` strip | `lc_rewrites.strip_neg_tense_agreement_in_clause` | In a clause's literal disjunction, drops a NEGATIVE literal `["-has time", E, T, Prep, ["$ctxt", T, …]]` whose tense value `T` (past/present/future/timeless) **equals** the `$ctxt` tense slot.  Positive `has_time` literals and single-literal clauses are untouched; never empties a clause. | **CLAUSE-level** pass — runs post-clausification, invoked from `logconvert.rawlogic_convert` right after the isa-class singularize pass (not from the pre-clausification `strip_tense_has_time` tree pass).  Such a negative literal is a vacuous query escape: the event's grammatical tense is already carried by the `$ctxt` slot and normalised any-tense→past for past worlds by the axioms_std.js §D "Context Tense Normalization" block (which is value-preserving, so it never manufactures `has_time(E, "past")`).  Requiring the event-level tense over-constrains a yes/no question whose matching assertion expresses time via a temporal **modifier** instead — "The letter was written in June. Was the letter written?" gives the assertion event `has_time(E, "June", "in")`, which never unifies with the question's `has_time(E, "past", "in")`, so the proof fails on the value mismatch (case 709).  Dropping only the negative literal lets the question match via the surviving `has_type`/`has_target` atoms (bridged across the `$ctxt` tense by §D); the positive `has_time` fact is kept because it is redundant-but-true.  The `value == $ctxt-tense` gate is what makes it safe: a real modifier ("June") or a value/context mismatch (`has_time(E,"past",$ctxt("present"))`) never matches and is preserved. |
| `actuality(E)` injection | `lc_rewrites.inject_actuality` | An `and`-block containing `isa(activity, E)` plus any of `has_type`/`has_actor` and no modal classifier on E gets `["actuality", E]` appended.  Stage 2 does not emit this marker; the pipeline adds it post-Stage-2. | Pre-clausification injection.  Walks the formula tree; for every Davidsonian event variable introduced by `isa(activity, E)`, appends `["actuality", E]` to the same `and`-block unless one of the eight Stage-2 modal classifiers (`typical`, `capability`, `necessity`, `obligation`, `volition`, `intention`, `expectation`, `speech_act`) already attaches to E, OR E appears as the second argument of `has_content(E1, E)` whose OUTER event E1 is **non-factive** — i.e. E1's verb is NOT a causative in `_CAUSATIVE_CONTENT_VERBS` (`have`/`make`/`let`/`force`/`cause`/`get`).  The content of intention/speech reifications and non-factive verbs (`try`/`attempt`/…) is not actual, but a causative's embedded event really occurs, so `has_content` of a causative `have` still gets `actuality` (case 1616: "had the mechanic fix the car" → the mechanic really fixed it; a verb whitelist rather than a mode blacklist, because "try" carries no modal classifier yet "John tried to open the door" ⇏ opened — cf. cases 1592/1593).  Idempotent — guards against re-injection on a second pass.  Consumed by the `axioms_std.js` §5.1 actuality→capability bridge, which is gated on `actuality(E)` instead of "any Davidsonian event", letting the bridge dispatch positively on real events rather than negating eight other classifier predicates. |
| Spurious `can` cleanup | `lc_rewrites.strip_spurious_can` | Drops a stray `can(X,E)` literal from a Stage-2 formula.  Kept for compatibility with cached LLM responses that still contain the obsolete atomic `can` predicate; on current LLM output it is a no-op. |
| Meta-predicate normalization | `lc_rewrites.rewrite_meta_predicates` | `["is rel2","is",A,B]` → `["isa",A,B]`; `["is rel2","=",A,B]` → `["=",A,B]`; `["is rel2","located in",A,B]` → `["is rel2","in",A,B]`; `["is rel2","belonged to",THING,OWNER]` → `["have",OWNER,THING]` | Pre-clausification rewrite applied to all formulas.  Normalizes copula (`is` → `isa`), identity (`=`), spatial meta-predicates (`located in/at/on/near/above/under` → bare preposition), movement verbs (travel/journey/move → go), placement verbs (place/set/lay/position/deposit → put), transfer verb synonyms (hand/pass/send → give), and ownership relations to canonical `have(owner,thing)` — passive `belonged to`/`belongs to`/`owned by`/`possessed by` (owner at arg 3, swapped) and active `owns`/`own`/`owned`/`possess(es/ed)` (owner at arg 2) — so a possessive assertion and a "who owns / whose" query share the `have` predicate.  Also normalizes 3-arg `has_destination(E,Dest)` to 4-arg `has_destination(E,Dest,"at")` for backward compat with stale Stage-2 cache entries. |
| Perspective verb → dative head normalization | `lc_rewrites.normalize_receive_events` | `["has type",E,"receive"]` + `["has actor",E,X]` → `["has type",E,"give"]` + `["has recipient",E,X]`.  Same pattern for hear→tell, see→show, get→give. | Formula-level rewrite: in `and`-blocks containing a perspective-verb event (receive, get, hear, see), the verb is changed to its dative head (give, tell, show) and the actor role is swapped to recipient.  Single mapping table `_PERSPECTIVE_TO_DATIVE`; function name retained for back-compat.  Asymmetry preserved — the rewrite never adds an actor for events lacking an explicit dative agent, so "Did John receive a book?" still fails when John was the giver.  Allows the give-based transfer axioms in `axioms_std.js` to derive `have(Recipient, Object)` in the next world state, and lets queries about hear/see/get match facts about tell/show/give. |
| Set existence fact | `lc_sets._walk_for_count` | "Bears ate berries" with `forall/implies/member/$setof` in assertion context → `member("$some_bear", $setof(...))` | Generates a ground set membership fact for assertion-context `forall/member` patterns so the prover can bootstrap resolution through member-guarded clauses.  Skipped when the set already has element instantiation from a count assertion. |
| Degree stripping | `lc_post_normalize.strip_degree_predicates` | With `-simpleprops`: `has_degree_property(big,X,none,animal)` → `has_property(big,X)` | (Only with `-simpleprops`) Replaces degree predicates with simple property predicates |
| Semantic normalisation | `semnormalize.sem_normalize_clauses` | "The ball is outside the box" → `outside` is antonym of `inside` → flips polarity and substitutes: `-is_rel2(inside,ball,box)` | Antonym resolution (~311 directional pairs, adjective + noun only: flip polarity + swap word) and canonical substitution (~752 pairs: synonym → canonical form).  Skips `$ctxt` terms.  Polarity-flipping is applied ONLY at the top-level literal — inside nested function terms (`$theof1`, `$measure_of`, Skolem), only canonical substitution runs (flipping `$theof1` to `-$theof1` would produce invalid terms).  Data loaded from generated `data_antonyms.py` and `data_canonicals.py`.  Verb antonyms (`ant_v.txt`) are intentionally excluded from rewriting — most are perspective inversions (give/take, buy/sell), process complementarities (start/stop, come/go), or weak pairs where polarity-flip is wrong, and key verbs collide with axiom-vocab predicates (case 171).  Useful verb subsets (attitude pairs like like/dislike) are scheduled for re-introduction via a defeasible attitude-mutex injector.  `build_antonyms` also skips any pair whose canonical target is itself a CANONICALS key — such chain-through pairs are deferred to `build_exclusions` and emitted as synthetic `ANT_<W1>_<W2>` exclusion groups instead (prevents Pass 2 from chain-substituting the fold target to an unrelated sense, e.g. `open→close→near`). |
| Soft synonym injection | `lc_inject_synonyms.inject_soft_synonyms` | "The car is red" + axioms mention "crimson" → emits `red(X,Ct) <=> crimson(X,Ct)` biconditional | Dynamic injection of Tier B synonym axioms for words present in both input and axiom vocabulary.  Templates: `has property` (adj), `isa` (noun), `has type` (verb). |
| Exclusion injection | `lc_inject_synonyms.inject_exclusion_axioms` | "The car is blue. Was it red?" → emits `NOT blue(X,Ct) OR NOT red(X,Ct)` with `$block` | Dynamic injection of mutual-exclusion axioms from `excl_a.txt` and `excl_n.txt` groups.  `needs_blocker=True` groups use defeasible `$block`; `False` groups are hard exclusions. Five atom shapes: default `has_property` (adjective); `_IS_REL2_EXCL_GROUPS` (MONTH/DAY_OF_WEEK/SEASON) — `is_rel2` target at arg 3; `_IS_REL2_PREP_GROUPS` (SPATIAL_*, TEMPORAL_ORDER) — `is_rel2` preposition at arg 1 with two free entity variables; `_HAS_DEGREE_REL2_PREP_GROUPS` (PROXIMITY) — `has_degree_rel2` preposition at arg 1 with two asymmetric axioms per pair; `_ISA_EXCL_GROUPS` (NOUN_*) — concept name at `isa` arg 1, emits both same-entity shortcut `[-isa w1 ?:X, -isa w2 ?:X]` and cross-entity inequality `[-isa w1 ?:X, -isa w2 ?:Y, -=(?:X, ?:Y)]`. Also injects `MANUAL_ANTONYMS` adjective pairs as synthetic `MANUAL_ADJ_<W1>_<W2>` groups, and chain-rejected antonym pairs (from `build_antonyms`) as synthetic `ANT_<W1>_<W2>` defeasible adjective groups. See §9.5 for preposition handling. **Note**: the seven preposition groups in `_STATIC_PREP_EXCL_GROUPS` (SPATIAL_VERTICAL/_OVER_UNDER/_SAGITTAL/_CONTAINMENT/_LATERAL, TEMPORAL_ORDER, PROXIMITY) are skipped here — their mutual-exclusion axioms live statically in `axioms_std.js` §7e because both sides are first-class predicates in the standard ontology. |
| Cross-group noun mutex | `lc_inject_synonyms.inject_isa_cross_group_axioms` | "John is a car. Is the cat an animal?" → derives John ≠ cat | Layer 2 of noun mutex. For pairs `(w1, w2)` from different `_ISA_EXCL_GROUPS` groups (e.g. `car` in NOUN_VEHICLE, `animal` in NOUN_TOP_LEVEL), emits the same two shapes as the within-group injector. Same REQUIRE_BOTH_SIDES gating. |
| Carrier vocabulary lift | `lc_post_inject.inject_carrier_lifts` | "pizza on plate" present → emits `[¬isa(plate,X,Ct), isa(carrier,X,Ct)]` | Tags entities of carrier-noun categories so the static carrier-transparency axiom (axioms_std.js §7f) can fire. Carrier list: `_CARRIER_NOUNS = {plate, tray, saucer, dish, newspaper, napkin, tablecloth, mat, rug, carpet}`. |
| Entity UNA wrapping | `lc_post_una.apply_una` | After all post-processing: `is_rel2(on, "pizza 2", "table 3", …)` → `is_rel2(on, "#:pizza 2", "#:table 3", …)` | Wraps every Stage-1 numbered entity with `#:` prefix so `gk` treats distinct entity constants as definitely unequal. See §7.13 for the three-step criterion. Required by axioms_std.js §7g (X2 direct-support uniqueness). |
| World-graph geometry | `lc_post_inject.inject_world_geometry` | "Mary slept. Mary is awake. Was Mary awake?" → emits `next(W0,W1)` | Dynamic injection of the minimal `next(Wi,Wi+1)` chain spanning the concrete world constants actually present in the clause list. Replaces the static `W0..W12` chain that used to live in `axioms_std.js` §11. Skips emission entirely when ≤1 world is present (most single-tense problems); otherwise fills any gaps in `[min_idx, max_idx]` so `before` transitivity still closes. Keeps the `before` derivation graph small. |
| Verb mutex injection | `lc_inject_synonyms.inject_verb_mutex_axioms` | "Did everyone pass the exam? — No, Mary failed." → for each entity with both `pass` and `fail` events on it, emits a defeasible mutex preventing the same event from being both | Dynamic, cross-event mutex (distinct from `inject_exclusion_axioms`, which mutexes adjective properties on a single entity).  Pair table `_VERB_MUTEX_PAIRS` currently lists `(pass, fail)`.  Each pair emits a defeasible 0.85 axiom with `$block` so that an explicit positive can override.  Atom shape uses `has_type` event predicates plus shared `?:E` and `?:Ctxt`.  Does not fire unless both verbs of the pair appear in the input clauses. |
| Verb-result-state injection | `lc_post_inject.inject_verb_result_state_axioms` | "The city was destroyed" → emits bridges to `has property "destroyed" #:city @ present @ next-world` | For each `(verb, past_participle)` pair in `_VERB_RESULT_STATES = {(destroy, destroyed), (break, broken), (damage, damaged), (complete, completed), (kill, killed), (repair, repaired)}` whose verb appears in the input, emits TWO defeasible (0.9) bridge axioms covering both Stage-2 encodings. Bridge A (event-based, gemini/deepseek): `has type E V Ct + has target E X Ct + next W W2 → has property <pp> X [present W2 ...]`. Bridge B (stative property-name, claude): `has property V X [_ W _ _ _] + next W W2 → has property <pp> X [present W2 ...]`. Both target the same `present @ next-world` slot so mutex axioms fire on the question's present-tense reading regardless of LLM encoding. Wired into `rawlogic_convert` BEFORE `inject_exclusion_axioms` so the result-state words become eligible for the exclusion injector (e.g. enables `destroyed/intact` mutex when "destroy" is in the input). `(finish, finished)` is intentionally omitted because `axioms_std.js` covers it statically. |
| Acquire→have bridge | `lc_post_inject.inject_acquire_have_axioms` | "Susan bought herself a new car. Who owns a new car?" → emits `have(Susan, car) @ present @ next-world` from the buy event | Lexical inference "actor acquires X ⊢ actor has X", modeled on the static `axioms_std.js` §5b give→have and on `inject_verb_result_state_axioms` (fresh free-vars, next-world present result). **Bridge A** (`_ACQUIRE_VERBS = (buy, purchase, acquire, obtain)`, defeasible 0.9): `has type E V Ct + has actor E X Ct + has target E Obj Ct + next W W2 → have X Obj [present W2]`, with a `$block` escape. Keys on the **actor** (not the recipient) because the "for whom" role is encoded inconsistently across LLMs (`has_beneficiary` / `has_recipient` / dropped) while every parse carries `has_actor` — so Bridge A reaches all of them. `take`/`get` are excluded as too polysemous ("take a walk", "get tired"). **Bridge B** (`_ACQUIRE_BENEFACTIVE = (buy, get)`, 0.95): the `has_beneficiary` AND `has_recipient` own the target — the benefactive-ditransitive "X bought Y a Z" gift reading; narrower verb set (you cannot "obtain Bill a car"). Unlike give→have it needs **no** `transferred`-block (an acquisition has no named party that loses the object). Gated on verb presence; wired into the `sem_axioms` list. Closes case 1163 (1/4 → 4/4). Known limitation: "X bought Y a car. Does X have a car?" — Bridge A defeasibly over-emits `have(X,…)` (Bridge B gives the correct `have(Y,…)`); a guarded `$block` on beneficiary≠actor would close it. |
| Measure→relation bridge | `lc_post_inject.inject_measure_relation_bridges` | "The length of the car is 80 km. What is the length of the car?" (relational `is_rel2 "length of"` query) → emits `=($measure_of(length,S,W), V) → is_rel2("length of", V, S, Ct)` | Dynamic, per measure noun N. Emitted ONLY when the clause list contains BOTH a `$measure_of(N,...)` term AND an `is_rel2 "N of"` atom (so the bridge can connect a measure fact to a relational query, and only then). Generalises to any measure noun (length / price / weight / height / …) — N is read from the clauses, not a hard-coded list. Clause is `value=E1, subject=E2`, matching how Stage 2 emits `is_rel2 "<noun> of"`. Replaces a former static per-noun block in `axioms_std.js`. Lets a relationally-phrased measure question reach the `$list` value rather than only the definite description; the resulting two-answer set (description + value) is collapsed to the value by the `$list` answer-preference in `procproofs` (see §5.8, step 4b). |
| Negative-implicative bridge | `lc_post_inject.inject_negative_implicative_bridges` | "Tom refused to eat the soup. Tom ate the soup?" → emits `refuse(E1) ∧ has_content(E1,E2=V(X,Y)) → ¬(actual E3 = V(X,Y))` | Dynamic, one clause per verb in `refuse`/`decline`, emitted only when the verb appears. Mirror of the §5.2 factive bridge in the negative direction: a refused action did not actually happen. The refused inner content event carries no actuality (so it never matches an "actual event" query); this constraint additionally forbids any other actual event of the same verb/actor/target, so the query proves **False** (not just Unknown). Replaces a former static `axioms_std.js §5.2b` block. **`forget` (case 1599)** is added via `_NEG_IMPLICATIVE_CONTROL_VERBS`: the same clause plus an extra `has_actor(E1, X)` constraint tying the forgetter to the content's actor — "forget **to** V" (same-subject control) fires, but the factive "X forgot **that** [other] V'd" (→ P true) does not. refuse/decline need no such gate (always same-subject). |
| Perception-factive bridge | `lc_post_inject.inject_perception_factive_bridges` | "Mary was heard to sing. Mary sang?" → emits `perceive(E1) ∧ has_content(E1,E2) → actuality(E2)` | Direct perception is FACTIVE: "X was heard/seen to V" entails V actually happened. Positive counterpart of the §5.2 assertive factive bridge, keyed on the PERCEPTION verb (`hear`/`see`/`watch`/`observe`/`notice`/`witness`) — no `speech_act` classifier. Defeasible 0.95 with a `$block($not actuality)` escape, one clause per perception verb present. Fires only on perception OF AN EVENT (`has_content`), not of an object (`has_target`). **Requires** the companion guard in `lc_rewrites.normalize_receive_events`: the perspective→dative rewrite (hear→tell, see→show) skips any event holding a `has_content`, so "hear"/"see" survive for this bridge. Cases 1601/1603 (Unknown → True); 1602 stays Unknown (`actuality(enter)` ≠ leave). |
| Positional-preposition actor-location bridge | `lc_post_inject.inject_positional_actor_bridges` | "The car parked behind the house was blue. The car was behind the house?" → emits `has_location(E,L,behind) ∧ has_actor(E,X) → is_rel2(behind, X, L)` | Dynamic completion of the static in/at actor-location bridges (`axioms_std.js` §5e, whose positional siblings are commented out). For POSITIONAL prepositions `_POSITIONAL_PREPS = {behind, in_front_of, beside, next_to, near, by, left_of, right_of}` that locate the actor AT the landmark (unlike support preps on/under, which attach to the target). One defeasible-0.9 bridge (with `$block($not is_rel2)`) per positional preposition actually present in a `has_location` atom. Keys on `has_location` (event locale), not `has_destination`/`has_direction` (motion goal). Preposition canonicalisation (`lc_rewrites._PREP_CANONICAL`) makes both `has_location` and `is_rel2` use the underscored forms. Case 670 (2/4 → 4/4; bonuses 671/676/1298). |
| Containment bridge | `lc_post_inject.inject_containment_bridges` | "The cup filled with water fell. The cup contained water?" → emits `is_rel2("filled with", cup, water) → is_rel2("in", water, cup)` | "X filled with Y" / "X full of Y" entails Y is IN X. `_CONTAINMENT_RELS = {filled with, full of}`. When such a relation appears as `is_rel2`/`has_degree_rel2`, injects a STRICT one-way bridge `¬<rel>(X,Y) → is_rel2("in", Y, X)` per (relation, predicate-form) present — PRESERVING the original relation (an added entailment, NOT a rewrite; "Y in X" does not imply X full of Y), like the static `contains↔in` (axioms_std.js §1). The gpt variant that packs the content into the property NAME (`has_degree_property("filled with water", cup)`) is instead handled by `_check_stage2_multiword_property` (§5.17). Case 673. |
| Attribute property↔relation bridge | `lc_post_inject.inject_attribute_relation_bridges` | "The car which John drove was red. What color was the car?" → emits `has_property(red, X) → is_rel2("color of", red, X)` / `is_rel2("color", X, red)` | A property VALUE in an attribute family equals the attribute RELATION. `_ATTRIBUTE_FAMILIES` = color (`COLOR_BASIC`+`COLOR_EXTRA`), shape (`SHAPE_BASIC`), material (`MATERIAL_BASIC`), taste (`TASTE`) — value-sets reused from `data_exclusions`; each carries its relation names (`color of`/`color`, `shape of`/`shape`, `material of`/`made of`/…, `taste of`/`flavor`/…). For each family whose relation is QUERIED (an `is_rel2` relation) and whose value is PRESENT as a property, injects BOTH arg-orders from the post-normalize `has_property` form. Generalises and replaces the dead static "red→color of" stub (axioms_std.js §8), which covered one colour/arg-order and fatally expected `has_degree_property` (colours normalise to `has_property`). Case 901 (2/4 → 4/4; bonus 987). |
| Stable-adjective past→present persistence | `lc_post_inject.inject_stable_adjective_persistence` | "The man whom John saw is tall. Is the man short?" → emits `has_degree_property(tall, X, …, past@W) → has_degree_property(tall, X, …, present@W)` so the tall/short mutex meets the present query | See §7.14 — fills the assertion-side gap that the question-pinned tense bridges miss, for individual-level (stable) properties (`_STABLE_PERSIST_PROPS`: 83 stable adjectives + color/shape/material). Case 911. |
| Kinship mutex injection | `lc_inject_synonyms.inject_kinship_mutex_axioms` | "Sara is the sister of Mike. Is Sara the brother of Mike?" → emits `isa(sister,X) ∧ isa(brother,X) → false` (and the matching `is_rel2 "X of"` mutex) | Dynamic gender-paired role mutex covering 16 pairs: kinship (sister/brother, daughter/son, mother/father, wife/husband, aunt/uncle, niece/nephew), grand- (grandmother/grandfather, granddaughter/grandson), step- (step{mother,father,daughter,son,sister,brother}), god- (godmother/godfather), status (widow/widower, bride/groom), royalty (queen/king, princess/prince).  Each pair emits two atom shapes: `isa` 3-arg (no `$ctxt`) and `is rel2 "X of"` 5-arg with shared `$ctxt`.  Interacts with the `$theof1` chain-rewrite guard above — without that guard, two definites carrying both kinship roles for the same entity would chain-collapse and the mutex would never fire. |
| `@sourcetype` stripping | Serialisation (`clause_list_to_json`) | Population facts carry `@sourcetype:"populate"` internally for processing — stripped before the prover sees them | Internal `@sourcetype` tags are excluded from prover input |

---

### 7.8 Stage sanity checks and corrective retry loop

LLMs occasionally produce Stage-2 output that violates constraints the prompt explicitly
forbids — for example, free variables (case 259, "Every farmer who owns a donkey beats it"
where gemini leaves `Y` unbound in the consequent).  Rather than add a post-processing
rewrite for each such quirk, `llmparse.py` runs a **sanity checker** on every Stage-1 and
Stage-2 parse and, when issues are detected, re-calls the same LLM with the original prompt
plus the flawed output and a description of what went wrong.

**Mechanism** (in `llmparse._maybe_sanity_retry`):

1. After a Stage-N parse succeeds, call `check_stage<N>(parsed)`.  If the issue list is
   empty, return immediately.
2. Otherwise, fingerprint the issues by `(kind, location)` and enter the retry loop.
3. **Attempt 1 (corrective retry).**  Build a prompt = original input + `format_retry_suffix`
   (shows the flawed output and lists the issues).  Call the LLM.  Parse (with `fix_json`
   fallback) and re-check.  If clean, return.
4. **Attempt 2 (final retry).**  Only if attempt 1 produced issues that are **all new**
   (no fingerprint overlap with attempt 0).  Persistent issues → stop (retry not
   productive).  If cap reached, return best-effort output; downstream passes handle
   residual imperfections.
5. **Hard cap:** 2 corrective retries per stage.  The initial call plus 2 retries = 3 LLM
   calls max per stage.

**Cache interaction:** each retry input is a longer string (original + suffix describing the
flaw), so it hashes to a distinct cache key via `cache.make_llm_cache_key`.  Retries benefit
from the normal cache: a repeated run with the same input and flawed first response will
reuse the cached retry instead of re-calling the LLM.

**Canonical retry serialization:** `format_retry_suffix` dumps the flawed JSON with
`sort_keys=True` and sorts the issue list before formatting.  Checkers may collect
issues via sets/dicts whose iteration order varies across processes under hash
randomization; without the sorting, the corrective prompt — and hence its LLM-cache
key — would differ byte-for-byte between runs and miss the cache on every fresh run.
This applies on every path, including the default one.

**Entity-canon-gated check:** `_check_stage2_constant_vs_class` (enabled only when
`stage_sanity.aggressive_repair` is set when entity canonicalization is on, i.e.
under `-entitymerge` / the `-abstract*` presets) flags a name used
both as a specific entity (a constant) and as a class (an `isa` type) and re-prompts
Stage 2 to make the reading consistent; see §11.5.

**Stats tracked** (per stage, added to the `parse_text` stats dict):

- `sN_sanity_retries` — number of corrective LLM calls made.
- `sN_sanity_ok` — number of attempts that produced clean output (at most one per input).
- `sN_sanity_fail` — number of attempts that failed (returned None, JSON-invalid even after
  `fix_json`, or persisted with the same issues).

Visible in the `-debug` flag's Parse-stats block.

**Relationship to post-processing rescues:** some sanity-check kinds have overlapping
post-processing passes (e.g. `state_time_in_body` ↔ `lc_rewrites.strip_tense_has_time`;
`dropped_specific_noun` ↔ `lc_rewrites.inject_query_specific_noun_isas`).  The retry is
preferred when the LLM can plausibly fix the issue itself — the resulting Stage-2 is cleaner
and less reliant on rescue heuristics.  Post-processing remains as a belt-and-braces for
LLMs/inputs where the retry doesn't land.

**Design boundary — what is NOT checked:**

- Purely semantic calibration (confidence values, word choice between synonyms, tense
  accuracy on past/future verbs) is not flagged.
- Structural patterns that appear in the Stage-2 examples file are not flagged even if
  technically "wrong" per instructions (e.g. `has time E TENSE PREP`), because LLMs follow
  examples.  Post-processing handles these.
- Verb-frame decomposition (e.g. `has property "filled with water"`) is not flagged — the
  LLM cannot plausibly rewrite its own output that much on a retry.

The list of checks lives in `stage_sanity.py` (§5.17).  Adding a new check = one new
`_check_stage<N>_*` function plus a call inside `check_stage<N>`; no change to `llmparse.py`
is needed.

---

### 7.9 Confidence and uncertainty handling

Natural-language probabilistic hedging (`"John smokes tobacco with probability 0.8"`,
`"Elephants are rarely animals"`, `"It is false that X"`) is carried through the pipeline
as a numeric confidence value on Stage-1 ASUs and propagated into per-clause
`@confidence` annotations that the prover multiplies along resolution chains.  This
section describes every transform applied between Stage-1 and the prover.

#### Stage-1 captures probability as `confidence`

Stage-1 extracts probabilistic hedges from the input text and attaches them as a
`confidence` field on the ASU:

| Input phrase | Stage-1 `confidence` |
|---|---|
| (unmodified) | 1.0 (default) |
| `"with probability 0.8"` | 0.8 |
| `"probably"`, `"with probability 90%"` | 0.90 |
| `"likely"`, `"expected"` | ~0.80 |
| `"maybe"` | ~0.60 |
| `"unlikely"`, `"hardly"`, `"rarely"` | ~0.20 |
| `"probably not"`, `"not probable"` | ~0.20 |
| `"with probability 0%"` | 0.0 |
| `"it is false that X"`, `"it is not true that X"` | (omitted) — encoded as negation in `text` |

The field semantics: **probability** that the ASU's claim holds, in [0, 1].

**Explicit negation markers are NOT probability.**  Phrases like
`"it is false that X"`, `"it is not true that X"`, `"it is not the case that X"`
are full-confidence negated assertions.  Stage-1 PART 4 of the confidence
rules (`prompts/stage1_instructions_full.txt`) instructs the LLM to encode
the negation in the `text` field (`"X is not ..."`) and **omit** the
`confidence` field entirely.  When combined with a probability modifier
(`"it is probably false that X"`, `"with 0.8 probability it is false that X"`),
the probability goes in `confidence` and the negation stays in `text`:
`"it is likely false that John is nice"` → `text: "John 1 is not nice."`,
`confidence: 0.8`.  Without this rule, LLMs double-encode the negation
(`["not", F]` in the formula **plus** `confidence: 0.0`), which collapses to
a positive assertion after `_negate_consequent` fires.  See the "double-
encoding safety net" subsection below.

#### Stage-2 optionally reports confidence via `@p`

Stage-2 can carry the confidence forward as a package-level `@p` annotation:

```
["and", PACKAGE, ["@p", "S1", 0.8]]
```

`_process_assertion` uses the `@p` value as the input `confidence` to the clausification
step (`logconvert.py:916`).

#### Probability → evidence scale

The prover uses a symmetric evidence scale in `[-1, 1]`: **−1 = certainly false,
0 = no information, +1 = certainly true**.  `_process_assertion` maps probability `p` to
evidence `e`:

| Input `p` | Evidence `e` | Polarity flip? |
|---|---|---|
| `[0, 0.5)` | `1 − 2p` | **Yes** — consequent negated before clausification |
| `0.5` | `0` | — (all clauses dropped; prover returns "no information") |
| `(0.5, 1)` | `2p − 1` | No |
| `1` | `1.0` | No (unannotated = full confidence) |

Worked examples:

- `p = 0.8` → `e = 0.6`, no flip
- `p = 0.9` → `e = 0.8`, no flip
- `p = 0.1` → `e = 0.8`, **flip**: the assertion is negated, then asserted at `e = 0.8`
- `p = 0.0` → `e = 1.0`, **flip**: full-confidence negated assertion
- `p = 1.0` → no annotation (full confidence)

Polarity flip: `_negate_consequent(formula)` (see `lc_rewrites.py`) negates the
consequent of a rule body (or the whole formula for a bare assertion) so that low-p inputs
become high-evidence negated assertions.  This is done pre-clausification so the CNF is
structurally correct.

#### Double-encoding safety net (case 234)

When an LLM ignores PART 4 and double-encodes a negation (emits both
`["not", F]` in the formula **and** `confidence: 0.0` / `@p: 0.0`), the
`negate_consequent` step above would apply a second negation, collapsing
the claim back to positive (e.g. "It is false that X" would be asserted
as "X at full confidence" — case 234).

`_process_assertion` catches this in `logconvert.py`: if `@p == 0.0` **and**
the formula has an explicit `not` at a top-level position (root, direct
`and` conjunct, `implies` consequent, or `forall/exists` body root —
checked by `_has_explicit_negation_at_top`), the `@p` is dropped (treated
as absent/full-confidence).  The formula's own `not` then carries the
negation through clausification, producing the intended fully-confident
negated assertion.

Narrow to exactly `@p == 0.0`: a formula with `not F` paired with
`@p < 0.5` but > 0 can legitimately mean "I'm unsure about the negation"
(`"probably not X"` style), which the existing `negate_consequent` branch
handles correctly.  Broadening would regress that case.

#### Per-clause distribution of evidence

Clausification of a single ASU typically produces several clauses (event-role atoms, isa
facts, `typical/$block` defeasibility markers, etc.).  Naively stamping `@confidence = e`
on **every** clause causes the prover's chain multiplication to report `e^N` for an
N-step derivation — quickly dropping below the `0.1` keep-confidence threshold and
causing legitimate answers to be filtered out.

`_distribute_clause_confidence` (`logconvert.py`) distributes `e` across an **anchor
set** using a three-case priority:

1. **Clauses with a `$block` atom.**  These are defeasibility anchors — every derivation
   passing through the rule touches one of them.  If any $block-carrying clause exists,
   each gets `e^(1/k)` where `k` is the count of such clauses.  Non-$block clauses stay
   at confidence 1.0 (no annotation).

2. **Clauses referencing a Skolem constant or function.**  If no $block clauses exist
   but the ASU contains Skolems (e.g. `sk0_activity` from an `exists E, …` in the
   Stage-2 formula), these event-spine clauses receive `e^(1/k)`.  Non-Skolem clauses
   (plain ground isa facts like `isa(person, "John 1")`) stay at 1.0 — they are entity
   annotations unconnected to the probabilistic claim.

3. **Every clause.**  For pure class/relation assertions without events
   (e.g. `"John is an elephant with probability 0.8"` → single `isa` clause), all
   clauses receive `e^(1/k)` equally.

In every case, the **chain product over the anchor set equals `e` exactly**, so any
derivation that covers the full anchor set reports the intended confidence.

Edge cases:

- `e = 0`: all clauses dropped (line `if e == 0.0: return []`).  Input `p = 0.5` falls
  through this branch, producing no assertions at all — the prover returns
  "no information".
- `e = 1.0` (also `p = 1.0`): all clauses emitted without `@confidence` annotation.
  Prover treats as full confidence — no chain decay.
- `k = 0`: only possible for an empty clause list, which can happen when the formula
  is vacuous; the function returns `[]`.

#### Prover threshold

`globals.py:81` pins the prover to `-confidence 0.1 -keepconfidence 0.1`: any answer
whose derived confidence is below 0.1 is filtered out as noise.  Before the three-tier
distribution was introduced this threshold hid legitimate probabilistic answers (e.g.
case 235's 6-clause chain at `0.6^6 ≈ 0.047`); now the chain product equals `e`, well
above 0.1 for typical probability inputs (`p ≥ 0.6` maps to `e ≥ 0.2`).

#### Answer rendering with confidence

The reported answer string carries a verbal qualifier derived from the proved confidence
(`_format_bool_answer` in `proof_answer_format.py`):

| Boolean | `conf ≥` | Rendered |
|---|---|---|
| True | 0.95 | `True.` |
| True | 0.70 | `Probably true.` |
| True | 0.40 | `Likely true.` |
| True | 0.10 | `Possibly true (confidence X).` |
| True | <0.10 | `Unknown.` |
| False | 0.95 | `False.` |
| False | 0.85 | `Likely false (confidence X).` |
| False | 0.60 | `Probably false (confidence X).` |
| False | <0.60 | `Probably false.` |

The asymmetry is intentional: True is graduated finely because positive proof chains
vary in strength, while False is proved by contradiction and even weak negative evidence
is informative.

Generic wh-answers (what-queries, and who-queries that fall into the
`_format_answers` path) append `(confidence X)` to the answer entity name
when `conf < 0.99`.  The test-harness matcher strips the parenthetical by
default (non-strict mode), so `"The man (confidence 0.94)"` passes tests
expecting `"The man"`.

**Who-queries use a qualitative prefix instead of numeric suffix**
(`_format_who_answers`).  The prefix is derived from the **minimum
confidence** across the surviving answer set (the weakest link in the
claim):

| Min confidence | Prefix |
|---|---|
| `> 0.8` | (none) |
| `(0.4, 0.8]` | `"Probably "` |
| `[0.05, 0.4]` | `"Maybe "` |
| `< 0.05` | answer dropped |

Examples (cases 241, 242):
- `"Elephants probably do not have wings. John is an elephant. Who does
  not have wings?"` → John has confidence 0.6 → `"Probably John."`
- `"Elephants probably do not have wings. John is maybe an elephant.
  Who does not have wings?"` → John has confidence 0.12 (chained
  0.6 × 0.2) → `"Maybe John."`

The threshold values mirror the Stage-1 adverb mapping (`probably` → 0.8,
`maybe` → 0.6).  The prefix is capitalized; the following word retains
its original case, so `"Probably John."` keeps the proper-noun capital
and `"Probably a tobacco."` keeps the article lowercase.

#### Skolem-typed answer rendering for "what" queries

Questions starting or containing "what" / "which" get an `@what_query` marker set by
`_process_question` (via `_raw_has_what_word` which matches the wh-word as a whole
word anywhere in the query text, not only at the start — case 243's "John smokes
what?" is correctly detected).  For such queries, `_resolve_what_skolem_answers`
(`proof_answer_format.py`) replaces Skolem-typed answer values with population constants of the
corresponding class:

- Skolem **constant** like `"sk1_tobacco"` with an `isa(tobacco, sk1_tobacco)` fact
  → `$some_tobacco` → renders as `"a tobacco"`.
- Skolem **function** term like `["sk3", "Emily 1"]` typed as `wolf` → `$some_wolf`
  → renders as `"a wolf"`.

Without this remapping, the answer would leak the raw Skolem display name
(`"Tob1"`, `"Wol1"`) instead of the user's original noun.

#### Who-query formatting with Skolem-typed answers

`_format_who_answers` classifies each answer value into *types*, *properties*, or
*equalities*.  Before the fix, Skolem constants fell to the *equalities* bucket because
they contain digits (the skolem index).  Now if the Skolem has a known type from
`get_skolem_type` — derived from `isa(T, sk…)` facts during `compute_skolem_types` — the
**type** is promoted to the types list instead, so the who-answer renders as
`"a <type>"` consistently with what-queries.

#### Summary — files involved

| File | Role |
|---|---|
| `solver/logconvert.py` | `_process_assertion`, `_distribute_clause_confidence`, `_clause_has_block`, `_clause_has_skolem`, `_has_explicit_negation_at_top` (double-encoding safety net), `_raw_has_what_word`, `_raw_has_who_word`, `_has_what_query` |
| `solver/lc_rewrites.py` | `negate_consequent` (used by polarity flip) |
| `solver/lc_clausify.py` | `is_skolem_const`, `is_skolem_fn` (reused by the distribution) |
| `solver/proof_answer_format.py` | `_format_bool_answer`, `_format_answers`, `_format_who_answers` (qualitative prefix), `_resolve_what_skolem_answers` |
| `solver/proof_answer_select.py` | `_extract_class_names`, `_filter_class_name_leaks` |
| `solver/globals.py` | prover confidence thresholds (`-confidence 0.1`, `-keepconfidence 0.1`) |
| `prompts/stage1_instructions_full.txt` | PART 4 of `--- confidence ---`: explicit-negation-marker rule |

---

### 7.10 WH-question handling

The pipeline handles four types of WH-questions through specialized detection and encoding in `logconvert._process_question` (routing) and `lc_questions` (clause generation), with answer formatting in `procproofs`.

### Where questions ("Where is X?")

Detection: `find_where_atom(body, ask_var)` matches `["is rel2", spatial_pred, entity, ask_var]` where `spatial_pred` is a spatial preposition after meta-predicate normalization (e.g., `"located in"` is rewritten to `"in"` by `_rewrite_meta_predicates` before detection).  Also detected via `find_haslocation_prep` matching `["has location", event_var, ask_var, prep]` in activity-location queries (extracts the preposition for the answer).

Encoding depends on the entity and preposition:
- **Concrete entity** (e.g., `"John 1"`): `build_where_question` generates biconditional clauses for each spatial preposition — forward and backward — sharing a single `$defq` with 2-arg atoms `[$defq, prep, ?:Q1]`.  Generic prepositions (`in, on, at`) trigger expansion over ALL spatial preps; specific prepositions (`near, above, under`) restrict to just that preposition.
- **Variable entity** (e.g., `"Y"` for "a car"): uses `build_defq_question` which preserves all body constraints (e.g., `isa(car, Y)`) to avoid over-broad matching.

Sets `@where_query: True` and `@askvars: 2`.

Answer format: `_format_prep_answers` renders `["$ans", prep, entity]` as "In Paris.", "Near the house.", etc. with confidence prefixes.  Skolem entities (constants like `"sk0_house"` or functions like `["sk0", "box 2"]`) are resolved to their type via `_resolve_skolem_entity` (e.g., "the house").

### When questions ("When is X?")

Identical infrastructure to Where, parameterized via shared internal functions (`_find_prep_query_atom`, `_find_has_event_role`, `_build_prep_question`).

Detection: `find_when_atom` matches `_WHEN_META_PREDS` (`scheduled for, happens in, occurs at, ...`) or `WHEN_TEMPORAL_PREPS` (`in, at, on, during, before, after`). Also via `find_hastime_prep` matching `["has time", event_var, ask_var, prep]`.

Encoding: `build_when_question` generates biconditionals over temporal prepositions. Sets `@when_query: True`.

Answer format: Same `_format_prep_answers` — renders as "On Monday.", "During the summer.", etc.

### Who/What questions ("Who is X?" / "What is X?")

Detection: `_detect_who_query(body, ask_var)` matches:
- `["=", ask_var, ENTITY]` or `["=", ENTITY, ask_var]` — identity
- `["isa", ask_var, ENTITY]` — type query (ask_var in type position)
- `["is rel2", "is", ENTITY, ask_var]` or `["is rel2", "is", ask_var, ENTITY]` — copula (rewritten to `isa` by `_rewrite_is_rel2_is` but also detected directly)

Returns the concrete entity constant. The raw question text determines `who_kind` ("who" or "what") for answer ranking.

Encoding: `build_who_question` generates two biconditional sets sharing one `$defq`:
1. **isa types**: `isa(?:X, ENTITY) <=> $defq(?:X)` — what types does ENTITY belong to?
2. **equality**: `=(?:X, ENTITY) <=> $defq(?:X)` — what equals ENTITY?

Sets `@who_query: True`, `@who_entity: ENTITY`, `@who_kind: "who"|"what"`, `@askvars: 1`.

Answer formatting: `_format_who_answers` collects `$ans` values from the prover (isa types and equalities) and **injects properties directly** from a clause-list scan (`_classify_who_answers` finds `has_degree_property(PROP, ENTITY, ...)` and `has_property(PROP, ENTITY, ...)` ground facts).  Properties bypass the prover because property biconditionals with variable PROP cause search-space explosion.

Filtering: self-referential answers (answer = queried entity) are kept only as fallback when no other answers exist.  `$`-prefixed constants (population/metadata) are always filtered.  When direct properties exist, the self-referential fallback is suppressed.

Classification and ranking differs by kind:
- Who: equality > isa types > properties
- What: isa types > properties > equality

Noun phrase composition: when both types and properties exist, they are merged into a composed noun phrase — e.g., types=["car"], properties=["bad","red"] → "a bad red car".  The primary type gets all properties as adjectives; additional types are listed separately with articles.  Properties without a type are listed bare ("nice").  Equalities rendered via `entity_name()`.

Returns both the answer string and the set of surviving values (used to filter proof explanations to only show relevant proofs).

### Other WH-questions ("Who is an animal?", "What did John eat?")

WH-questions that don't match the who/what identity pattern or the where/when preposition pattern fall through to the general `build_defq_question` path, which wraps the full ask body in a `$defq` biconditional. These handle "Who is an animal?" (find entities of type animal), "What did John eat?" (find event targets), etc.

The defq path also injects wh-kind markers so answer formatting can route
through the right formatter:

- `_raw_has_what_word(raw_text)` detects `what`/`which` as whole words
  anywhere in the query text → sets `@what_query: True` on the question
  object.
- `_raw_has_who_word(raw_text)` detects `who`/`whom` → sets
  `@who_query: True`.  Without this, complex who-questions like
  `"Who does not have wings?"` (whose body doesn't match the simple
  identity patterns of `_detect_who_query`) would fall through to the
  generic `_format_answers` path and render with a numeric
  `(confidence X)` suffix instead of the qualitative `"Probably X."` /
  `"Maybe X."` prefix from `_format_who_answers` (cases 241, 242).

### Class-name leak filtering in who-queries

The background part-inheritance axiom
`has_part(X, Y, Z) ∧ isa(X, U) → has_part(U, Y, Z)` (an elephant's part
is a part of all elephants) can unify the answer variable with a **class
name string** (e.g. `"elephant"`) via a population fact like
`isa(elephant, $some_elephant)`.  The resulting `$ans("elephant")` is not
an entity answer — it's a leak from the meta-variable in the axiom.

`_filter_class_name_leaks` in `proof_answer_select.py` drops answers whose every
`$ans` atom binds to a class name (computed by `_extract_class_names`:
the set of first-arg strings from all `isa(CLASS, *)` atoms in the
problem's clause list).  The filter fires only for generic
wh-placeholder queries — when `@who_entity` is **unset**.  For queries
with an explicit `@who_entity` (like `"Who is John?"`), class names are
legitimate type descriptions of the queried entity and are kept.

### $ctxt injection for WH-questions

All question types use the query's concrete world from Stage 1 `pre_state` for matrix
predicates (is_rel2, have, etc.), and free-var worlds for descriptive atoms (isa, event
predicates).  Tense defaults to `"present"` when Stage 1 does not provide a `"time"`
field — matching the convention that bare present-tense is the unmarked default.
Stage 1 provides `"time": "past"` for explicitly past-tense questions ("Did he run?",
"Was the car red?"), which the pipeline uses directly.

This present-tense default prevents the tense bridge axioms (`present@W_old` →
`past@W_new` via `before(W_old,W_new)`) from leaking stale historical facts into
present-tense queries like "Where is John?" — the query's `$ctxt(present, W, ...)`
only matches present-tense results at the query world, not past-tense bridged facts.

---

### 7.11 Proof deduplication

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

### 7.12 Typed Skolem constants

Skolem constants generated during clausification embed their type in the name when the type is known from the existential body:

- `["exists", "Y", ["and", ["isa","house","Y"], ...]]` → constant `"sk0_house"` (instead of `"sk0"`)
- Unknown type: plain `"sk0"` (backward compatible)
- Skolem functions (from rules with free variables) keep plain names: `["sk0", "?:X"]`

Helper functions in `lc_clausify.py`:
- `is_skolem_const(val)` — matches both `sk0` and `sk0_house` patterns
- `is_skolem_fn(val)` — matches list Skolem functions
- `skolem_type_from_name(name)` — extracts type: `"sk0_house"` → `"house"`, `"sk0"` → `None`

Skolem type resolution for rendering (`proof_answer_format._resolve_skolem_entity`):
1. **Fast path**: extract type from name via `skolem_type_from_name`
2. **Fallback**: look up type from `compute_skolem_types` clause-list scan (handles old-format names and Skolem functions)

`compute_skolem_types(proof, logic=None)` in `proof_render.py` scans both the logic clause list (for types not used in the proof) and proof steps, populating `skolem_types` and `skolem_fn_types` tables.

---

### 7.13 Entity UNA via `#:` prefix

The `gk` prover treats two distinct constants as definitely unequal **only when both are
prefixed with `#:`**.  Without UNA, a clause like `[¬is_rel2(on,X,Y1,C), ¬is_rel2(on,X,Y2,C),
=(Y1,Y2)]` (axioms_std.js §7g) cannot derive a contradiction from
`is_rel2(on, pizza, table)` plus the assumed-question `is_rel2(on, pizza, floor)` —
the prover would happily add `=(table, floor)` to its KB rather than detect the conflict.

`lc_post_una.py` runs at the end of `rawlogic_convert` and rewrites every Stage-1
numbered entity to its `#:`-prefixed form.  A string is wrapped iff **all three**
checks pass:

1. **Surface-form regex** — `^[A-Za-z][A-Za-z0-9_' -]* \d+$` (word + space + digits).
2. **Membership in the Stage-1 entity set** built from `s1_json -> packages -> units ->
   entities` — only ids that the LLM declared as concrete entities.
3. **Not Skolem-shaped** — `^sk\d+_…` excluded.

Skolem constants, function terms (`$theof1`, `$measure_of`), worlds (`W0`/`W1`), and
`$some_X` / `$some_not_X` constants are **not** wrapped.  These have their own
distinctness machinery (Skolems are pairwise distinct by construction; function terms
inherit equality from their arguments).  Broadening UNA to Skolems is intentionally
deferred — the conservative criterion is sufficient for the X2 case-148 closure on
LLMs whose Stage-2 produces concrete entity ids for definite descriptions.

The `#:` prefix is stripped at proof rendering time (`proof_utils.entity_name`,
`proof_logic._logic_name`) and at the top of `procproofs.process_proof` via
`_strip_una_prefix`, so user-facing answers are unaffected.

When deepseek emits a Skolem like `sk1_floor` for "the floor" (definite description),
UNA does NOT wrap it.  The closure path then runs through the noun-mutex axioms in
§7g instead: `[¬isa(table, X), ¬isa(floor, X)]` (same-entity shortcut emitted by
`inject_exclusion_axioms` for NOUN_FURNITURE_FIXTURE) plus paramodulation through
the X2-derived equality.  See §9.3 for the mutex injector.

---

### 7.14 Frame persistence and motion blocking

`axioms_std.js` §12 contains the **`is_rel2` tense-migration axiom**: a present-world `is_rel2(P, X, Y, ctx_present_W)` fact propagates to past worlds whenever `before(W_past, W_present)` holds.  This is what lets *"The cup is on the table. Was the cup on the table?"* close to True without an explicit past-tense fact.

The migration is **gated by two `$block`s**:
- `$block(0, moved(?:E1, ?:W_old))` — the entity moved AT the source world `W_old`.
- `$block(0, moved_between(?:E1, ?:W_old, ?:W_new))` — the entity moved at some
  INTERMEDIATE world strictly between `W_old` and `W_new`.

`moved(X, W)` is derived in `axioms_std.js` from `has_actor(E, X) + has_type(E, "go")` (the canonical movement event). `moved_between(X, W_old, W_new)` is derived from `moved(X, Wmid) + before(W_old, Wmid) + before(Wmid, W_new)`.

The source-world block alone is insufficient when the locatum's overriding move happens at a world *after* its present-location world but *before* the query world. In case 1327 ("Sandra travelled to the kitchen. Sandra travelled to the hallway. **Mary went to the bathroom.** Sandra moved to the garden. Where is Sandra?"), Sandra is at hallway at present-world W2, and her overriding move to garden is at W3 — an intermediate world. Because *Mary* (not Sandra) moved at W2, the source-world block didn't fire, so the stale hallway migrated to the W4 query and leaked into the answer ("At the garden **and at the hallway**"). The `moved_between` block catches the intermediate move (Sandra moved at W3, W2 < W3 < W4) and suppresses the migration. Non-movement relations (e.g. "afraid of") never derive `moved`, so they are unaffected.

**Known limitation:** with 4+ same-actor motion events in one problem (case 198), the prover's default strategy (`negative_pref` + `posunitpara`) struggles to enumerate the answer set within the 2-second budget.  The block is correct — the search blowup is a strategy issue, not an axiom issue.  Switching to `unit` or `query_focus` strategy can close such proofs but is not currently the default; see the *Prover-timeout suspected?* step in `CLAUDE.md` for diagnosis.

---

## 8. Configuration and options

**To change the default LLM provider or model**, edit `solver/llmcall.py`:
```python
use_llm          = "gemini"            # "gpt" | "claude" | "gemini" | "deepseek"
geminiversion    = "gemini-2.5-flash"
claudeversion    = "claude-sonnet-4-6"
deepseekversion  = "deepseek-chat"
```

**To change the gradable property whitelist**, edit `solver/gradables.txt`.  One lowercase
property name per line.

**To change prover defaults** (time limit, axioms, strategy), edit `globals.py` or pass flags
to `english_to_answer` via the `options` dict:
```python
english_to_answer(text, {"prover_seconds": 5, "nocontext_flag": True})
```

**To disable LLM caching for a single call:**
```python
english_to_answer(text, {"use_llm_cache_flag": False})
```

**To enable Gemini server-side context caching** (off by default — only needed on Gemini
tiers with a tight per-request input-token cap; see §5.3):
```python
english_to_answer(text, {"use_gemini_cache_flag": True})   # or pass -geminicache on the CLI
```

**Mode option keys** (defaults as noted; see §11 and §12 for what they do):
`event_base` (default `"neodavidson"`; else `davidson`/`flat`/`flatroles`), the
abstraction primitives (`entitymerge_flag`, `typeenrich_flag` + `typeenrich_gates`,
`guarddrop_flag`, `bridges_flag`, `dropdefinites_flag`, `localantonyms_flag`,
`existfold_flag`, `noproptypes_flag`), `prenorm_flag`, `crossstage_retry_flag`
(default `True`, but inert unless an abstraction encoding is active), `combined_flag`
+ `combined_instr_file` / `combined_examples_file` / `combined_checklist_file`,
`directanswer_flag` + `directanswer_file`.

---

## 9. The mkdata toolkit and solver integration

`mkdata/` is a standalone toolkit (separate venv, no dependency on `solver/`) for building
synonym, antonym, and mutual-exclusion data files. The final step (`build_solver_data.py`)
generates Python dict files in `solver/` that are loaded at runtime.

### 9.1 What mkdata produces

| Output | Count | Purpose |
|--------|-------|---------|
| `syn_{a,n,v}_rewrite.txt` | 416 / 218 / 124 entries | Tier A hard rewrites (`member,canonical`) |
| `syn_{a,n,v}_soft_axioms.txt` | 2496 / 6218 / 4103 pairs | Tier B soft synonym pairs (`word_a,word_b,score`) |
| `ant_{a,n,v}.txt` | ~1500 / 380 / 300 entries | Antonym pairs (directional, polarity-flip).  Most are filtered out during `build_solver_data.py`; the runtime ANTONYMS dict ends up at ~311 entries. |
| `excl_a.txt` | ~60 groups (+ 4 synthetic from `MANUAL_ANTONYMS`, + 2 synthetic from `MANUAL_GRADABLE_ANTONYMS`, + ~60 synthetic `ANT_*` groups from chain-rejected antonym pairs) | Mutual-exclusion groups (colors, months, nationalities, kinship/gender pairs, spatial/temporal opposites) |
| `excl_n.txt` | 10 groups (`NOUN_TOP_LEVEL`, `NOUN_FURNITURE_FIXTURE`, `NOUN_VEHICLE`, `NOUN_ANIMAL_KIND`, `NOUN_BODY_OF_WATER`, `NOUN_TERRAIN`, `NOUN_CELESTIAL`, `NOUN_BUILDING`, `NOUN_GARMENT`, `NOUN_TOOL`) | Noun-mutex groups for `isa(category, X)` exclusion. Members curated to avoid hyponym overlap (person/animal, sun/star, desk/table excluded). |

### 9.2 Solver runtime files

Generated by `cd mkdata && python3 build_solver_data.py` (fast, ~1 sec):

| Generated file | Contents | Used by |
|----------------|----------|---------|
| `solver/data_canonicals.py` | `CANONICALS` dict (~752 entries, all POS merged) | `semnormalize.py` |
| `solver/data_antonyms.py` | `ANTONYMS` dict (~311 directional pairs) | `semnormalize.py` |
| `solver/data_synonyms.py` | `SOFT_SYNONYMS` dict (~12K words, bidirectional) | `lc_post_inject.py` |
| `solver/data_exclusions.py` | `EXCLUSION_GROUPS` + `EXCLUSION_INDEX` (~205 groups, 5 atom shapes — adjective `has_property`, `is_rel2` target, `is_rel2` preposition, `has_degree_rel2` preposition, `isa` noun-mutex) | `lc_post_inject.py` |

Must be regenerated whenever any mkdata `.txt` source changes.

### 9.3 Solver integration

The data files are integrated at two points in the pipeline:

**Post-clausification semantic normalization** (`semnormalize.py`, called from `solve.py`):
1. Antonym folding: if a word is in `ANTONYMS`, flip atom polarity and substitute the antonym
2. Canonical substitution: if a word is in `CANONICALS`, replace unconditionally

Both passes walk all atom arguments (positions 1+), skip predicate names (position 0),
skip `$ctxt` terms, and handle disjunctive clauses (list-of-lists). Controlled by
`-nosemnormal` flag.

**Dynamic axiom injection** (`lc_post_inject.py`, called from `logconvert.rawlogic_convert`):

*Soft synonym axioms* (`inject_soft_synonyms`):
- Scans the clause list for words appearing in `SOFT_SYNONYMS`
- Emits biconditional clauses: `NOT pred(W,X,Ct) OR pred(OTHER,X,Ct)` (both directions)
- Templates: `has property` for adjectives (gradable normalizer promotes later), `isa` for
  nouns, `has type` for verbs
- Uses a single free variable for context (unifies with any `$ctxt` term)
- Two-side restriction (`REQUIRE_BOTH_SIDES = True` in `lc_post_inject.py`): only emits if
  the other side also appears in the input clauses or axiom file vocabulary

*Verb soft-synonym taxonomy* (`_GENERAL_VERBS` / `_BLOCKED_VERB_PAIRS` in
`lc_post_inject.py`) — refinement of the verb (`has type`) template only:

- **Unidirectional general-verb pairs.** Verbs in `_GENERAL_VERBS =
  {go, give, have, put, present}` are hypernyms (less-specific superordinates).
  When a verb pair has EXACTLY ONE side in this set, only the
  specific→general implication is emitted (`fly→go`, `run→go`, `drive→go`,
  `swim→go`, `pass→go`, `hand→give`, `tip→give`, `pass→give`, `receive→have`,
  `park→put`, `introduce→present`) and the general→specific clause is dropped.
  A bidirectional pair let the prover chain two synonyms transitively —
  `run ↔ go ↔ fly` made "John runs" defeasibly imply "John flies", which tripped
  the baby-bird ¬fly rule and produced a spurious "Probably false" (case 1451).
  A fly/run/drive event IS a going event, but a going event is NOT a flying
  event, so the implication must be one-way. Pairs where neither or both sides
  are general stay bidirectional.
- **Blocked pairs.** `_BLOCKED_VERB_PAIRS` is a curated set of verb pairs that
  are simply wrong (polysemy / POS confusion) — `go↔live`, `go↔work`, `go↔sit`,
  `chase↔dog`, `dog↔tail`, `say↔have`, `be↔present`, `make↔pass`, `come↔near`,
  `break↔give`, `put↔sit`, `give↔leave`. No axiom is emitted in either
  direction for these.
- **Effect** (validated across the 254 cases whose axioms contain a modified
  verb pair, all four LLMs): fixes 1451 (×4) and 1498 (gpt/gemini, the spurious
  `swim→fly` negative removed). The unmasked "regressions" 1500/1501 and 1616
  (claude) were passing only because a bad chain coincidentally produced the
  expected answer — see DEBUGGING / testfixlog 1451.

*Exclusion axioms* (`inject_exclusion_axioms`):
- Scans the clause list for words appearing in `EXCLUSION_INDEX`
- For groups with 2+ members present, emits pairwise exclusion clauses
- `needs_blocker=False` (months, days, kinship, spatial opposites): hard exclusion
  `NOT w1(X,Ct) OR NOT w2(X,Ct)`
- `needs_blocker=True` (colors, nationalities): defeasible exclusion with `$block` on each
  side (two axioms per pair), allowing override when both are explicitly asserted
- Four atom shapes selected per group:
  - **Default** (`has_property`): adjective groups — `[-has property, w, ?:X, ct]`
  - **`_IS_REL2_EXCL_GROUPS`** (MONTH, DAY_OF_WEEK, SEASON): preposition-target at
    is_rel2 position 3 — `[-is rel2, ?:R, ?:X, w, ct]`
  - **`_IS_REL2_PREP_GROUPS`** (SPATIAL_*, TEMPORAL_ORDER): preposition itself at
    is_rel2 position 1, with two free entity variables —
    `[-is rel2, w, ?:X, ?:Y, ct]`
  - **`_HAS_DEGREE_REL2_PREP_GROUPS`** (PROXIMITY): preposition at has_degree_rel2
    position 1. Emitted as TWO asymmetric axioms per pair — positive side
    any-degree, antonym side `"none"` intensity, shared `?:RC`:
    `[-has degree rel2, W1, ?:X, ?:Y, ?:D, ?:RC, ct], [-has degree rel2, W2, ?:X, ?:Y, "none", ?:RC, ct]`
    (and the symmetric axiom with W1/W2 swapped). The existing high→none /
    low→none intensity bridges in axioms_std.js §9 propagate the "none"
    negation to all intensities via contrapositive.
  - **`_ISA_EXCL_GROUPS`** (NOUN_*): noun concept names at `isa` position 1.
    Per pair, emits BOTH shapes:
    `[-isa w1 ?:X, -isa w2 ?:X]` — same-entity strict mutex (shortcut)
    `[-isa w1 ?:X, -isa w2 ?:Y, -=(?:X, ?:Y)]` — cross-entity inequality
    The shortcut enables direct refutation (no equality reasoning needed);
    the cross-entity form provides distinctness for two distinct ids
    classified into different mutex categories. Subsumes the shortcut
    (collapses when X=Y), but the shortcut is kept for prover efficiency.

*Cross-group noun mutex* (`inject_isa_cross_group_axioms`):
- Layer 2 of the noun-mutex story (Layer 1 is the within-group `_ISA_EXCL_GROUPS`
  branch above). For every pair `(w1, w2)` where `w1` is in group `G1`, `w2` in
  `G2`, and `G1 != G2` (both groups in `_ISA_EXCL_GROUPS`), emit the same two
  shapes (same-entity shortcut + cross-entity inequality).
- Both gated by REQUIRE_BOTH_SIDES — pair only emitted when both nouns appear in
  input clauses or `axiom_vocab`. So for problems mentioning ~5 noun categories,
  emitted axioms are bounded to a handful per problem.

*Carrier vocabulary lift* (`inject_carrier_lifts`):
- Static list `_CARRIER_NOUNS = {plate, tray, saucer, dish, newspaper, napkin,
  tablecloth, mat, rug, carpet}`. For each present noun, emits one lifting
  clause `[-isa <noun> ?:X ?:Ctxt, isa "carrier" ?:X ?:Ctxt]`.
- Consumed by the static carrier-transparency axiom in `axioms_std.js` §7f:
  `isa(carrier, C) ∧ on(X, C) ∧ on(C, S) → on(X, S)` (defeasible 0.85).
  Handles "pizza on plate, plate on table → pizza on table".
- New nouns: append one line to `_CARRIER_NOUNS`.

*MANUAL_ANTONYMS → synthetic adjective exclusion groups*:
`MANUAL_ANTONYMS` in `build_solver_data.py` is a small hand-curated dict of adjective
antonym pairs (currently `broken/intact`, `unfinished/finished`, `incomplete/complete`,
`undone/done`). **It no longer feeds `ANTONYMS` for polarity-flip rewriting.** Instead,
`build_exclusions()` converts each pair into a 2-member `needs_blocker=False` exclusion
group named `MANUAL_ADJ_<W1>_<W2>`, emitted with the default has_property template.
Semantically this is cleaner: "X is broken" and "X is intact" are mutually exclusive, not
strictly complementary — the axiom form expresses that precisely without losing positive
atoms.

*MANUAL_GRADABLE_ANTONYMS → synthetic defeasible exclusion groups*:
A second hand-curated dict in `build_solver_data.py` for **gradable** adjective antonym
pairs where polarity-flip-and-substitute would actively defeat reasoning across worlds
(currently `expensive/cheap`, `destroyed/intact`).  Same code path as `MANUAL_ANTONYMS`
except `needs_blocker=True` (defeasible — gradable pairs admit a middle ground), and
`build_antonyms` is patched to filter these pairs out of `ANTONYMS` so the polarity-flip
path doesn't pre-empt the exclusion path. Group naming: `MANUAL_ADJ_GRAD_<W1>_<W2>`.

**Why two separate paths.** With strict mutex (`MANUAL_ADJ_*`) the assertion stays
positive (`broken X`), the cross-world frame axiom (axioms_std.js §6) propagates it,
and the mutex contradicts at the question's world.  With polarity-flip ANTONYMS, the
assertion becomes negative (`¬cheap X`) which the frame axiom does NOT propagate
(propagation is positive-atoms only).  So pairs where the question and assertion live
in different worlds **must** flow through the exclusion path or they fail.  Add new
gradable pairs to `MANUAL_GRADABLE_ANTONYMS` (not to ANTONYMS) when they exhibit this
cross-world failure mode — see case 55 (expensive/cheap) and 157 (destroyed/intact).

*Chain-rejected antonyms → synthetic `ANT_*` exclusion groups*:
`build_antonyms` applies two symmetric guards against chain-contamination with the
canonical-substitution pass:
1. `word in CANONICALS` — skip; Pass 2 would shadow the fold source.
2. `canonical in CANONICALS` — skip rewriting; Pass 2 would chain-substitute the target
   to an unrelated sense. Example: WordNet has `open ↔ close` (verb sense) and
   `CANONICALS["close"] = "near"` (adjective sense from syn_a rewrites). Without the
   guard, semnormalize would turn `has_property(open, door)` into
   `-has_property(near, door)` — a nonsense atom (door is not near).

Pairs rejected by guard (2) — about 65 pairs — are deferred to `build_exclusions` and
emitted as synthetic 2-member `needs_blocker=True` (defeasible) exclusion groups named
`ANT_<W1>_<W2>`. Same has_property template as `MANUAL_ADJ_*`, same two-side
restriction, same injection code path. This preserves the semantic link between
antonym pairs (so the prover can still derive contradictions) without the destructive
rewriting that caused the chain bug. `needs_blocker=True` is used because many of these
pairs are gradable (abundant/scarce, hot/cold) where a middle ground exists and a hard
exclusion would overshoot.

*Verb-result-state bridges* (`inject_verb_result_state_axioms`):
- Pair table `_VERB_RESULT_STATES = {(destroy, destroyed), (break, broken),
  (damage, damaged), (complete, completed), (kill, killed), (repair, repaired)}`.
  `(finish, finished)` is intentionally omitted — `axioms_std.js` covers it
  statically.
- For each pair whose verb appears in the input, emits two defeasible (0.9)
  bridges (event-based and stative property-name) targeting
  `present @ next-world` so mutex axioms fire on the question's present-tense
  reading.
- Run before `inject_exclusion_axioms` so result-state words become eligible
  for the exclusion injector.

*Verb mutex* (`inject_verb_mutex_axioms`):
- Pair table `_VERB_MUTEX_PAIRS` (currently `(pass, fail)`).  Emits a
  defeasible 0.85 axiom per pair with `$block`, mutex'ing the two `has_type`
  event predicates on a shared event variable.  Fires only when both verbs of
  the pair appear in input clauses.

*Kinship mutex* (`inject_kinship_mutex_axioms`):
- 16 gender-paired role pairs (sister/brother, mother/father, queen/king, …).
  Each pair emits two atom shapes: `isa` 3-arg (no `$ctxt`) and
  `is rel2 "X of"` 5-arg (with `$ctxt`).

*Beneficiary ↔ "for"* (`inject_beneficiary_for_bridge`):
- Bridge axiom unifying `has beneficiary E X` with the prepositional form
  `is rel2 "for" E X` so queries written either way match assertions written
  the other.

*Measure→relation bridge* (`inject_measure_relation_bridges`):
- Per measure noun N, emits `=($measure_of(N,S,W), V) → is_rel2("N of", V, S, Ct)`
  (value=E1, subject=E2) — only when the clauses contain BOTH a `$measure_of(N,…)`
  fact and an `is_rel2 "N of"` atom.  Surfaces the `$list` measure value as an
  answer to a relationally-phrased measure question (deepseek "what is the length
  of X?").  N is read from the clauses, so it generalises to any measure noun;
  replaces a former static per-noun block in `axioms_std.js`.  The resulting
  description+value double answer is collapsed to the value by the `$list`
  value-preference in `procproofs` (§5.8, step 4b).

*Carrier lift* — see *Carrier vocabulary lift* above.

*World-graph geometry* (`inject_world_geometry`):
- Emits the minimal `next(Wi, Wi+1)` chain spanning the concrete world
  constants actually present.  Skips emission entirely when ≤1 world is
  present; otherwise fills any gaps in `[min_idx, max_idx]` so `before`
  transitivity still closes.

*Axiom-vocab predicate-root blocklist* (`AXIOM_VOCAB_ROOTS`):
A frozenset of ~50 verb/noun roots used as predicate names in `axioms_std.js`
(e.g. `give`, `have`, `move`, `own`).  `build_antonyms` drops any pair where
either side's root is in this set, preventing semnormalize from rewriting
through axiom-vocab words and breaking proof chains.

*Axiom vocabulary cache* (`axiom_vocab.py`):
- Extracts content words from axiom files (e.g. `axioms_std.js`), caches in `.vocab` sibling file
- Auto-rebuilt when axiom file is newer than cache
- Used by both injection functions for the two-side restriction

### 9.4 Full build pipeline

```
Step 1: make_anto_synonyms.py --pos {a,n,v}  ->  syn_*_10.txt, ant_*.txt
Step 2: harvest_syn_{a,n,v}.py               ->  expands syn_*_10.txt
Step 3: pick_canonicals_{a,n,v}.py --apply --emit  ->  syn_*_rewrite.txt, syn_*_soft_axioms.txt
Step 4: build_exclusion_data.py              ->  excl_a.txt
Step 5: build_solver_data.py                 ->  solver/data_*.py
```

Steps 1-4 are heavy (fastText model, NLTK). Step 5 is fast and should be re-run after any
source .txt changes. See `mkdata/README.md` for full documentation.

### 9.5 Spatial and temporal preposition handling

Handled via three cooperating mechanisms. Each is used where it fits best — pure surface
variants get rewritten, mutual exclusions get dynamic axioms, near-synonyms with distinct
meaning get static subsumption axioms.

**(a) Canonical rewriting — form variants (pre-clausification)**

`_PREP_CANONICAL` in `solver/lc_rewrites.py` maps spaced / colloquial preposition forms to
their underscored canonical forms. Applied inside `rewrite_meta_predicates` to:
- `is_rel2` argument 1,
- `has_degree_rel2` argument 1 (for near/far_from/close_to),
- `has_location` / `has_time` / `has_destination` preposition slot (argument 3).

Examples:
```
"in front of"      → "in_front_of"
"to the left of"   → "left_of"
"in back of"       → "behind"        # colloquial collapse
"inside of"        → "inside"        # "of" drop
"out of"           → "outside"
"far away from"    → "far_from"
"far"              → "far_from"      # has_degree_rel2: LLM sometimes drops "from"
"close to"         → "near"          # collapse into near (no subsumption axiom needed)
"prior to"         → "prior_to"
"subsequent to"    → "after"
```

Used only when the source form is a pure surface variant of the target (same concept,
different spelling). True lexical synonyms with distinct connotations (under ≠ below
exactly) are not collapsed here.

**(b) Mutual-exclusion axioms — spatial/temporal opposites (dynamic injection)**

Groups in `mkdata/excl_a.txt` whose ids belong to `_IS_REL2_PREP_GROUPS` (in
`solver/lc_post_inject.py`) are emitted with the preposition-at-pos-1 template:
```
[-is_rel2(w1, ?:X, ?:Y, ct), -is_rel2(w2, ?:X, ?:Y, ct)]
```
Current groups (all `needs_blocker=False`, i.e. hard exclusion):
```
SPATIAL_SAGITTAL                 behind, in_front_of
SPATIAL_VERTICAL                 above, below
SPATIAL_VERTICAL_OVER_UNDER      over, under
SPATIAL_CONTAINMENT              inside, outside
SPATIAL_LATERAL                  left_of, right_of
TEMPORAL_ORDER                   before, after
```

A fourth shape, `_HAS_DEGREE_REL2_PREP_GROUPS`, handles binary relations that
use `has_degree_rel2` instead of `is_rel2` (6-arg predicate with DEGREE and
RELCLASS slots). Currently one group:
```
PROXIMITY                        near, far_from
```
Each such group emits **two asymmetric axioms per pair** — positive side at
any degree (`?:D`), antonym side at `"none"` intensity, shared `?:RC`:
```
[-has_degree_rel2(near,     ?:X, ?:Y, ?:D,   ?:RC, ct),
 -has_degree_rel2(far_from, ?:X, ?:Y, "none", ?:RC, ct)]
[-has_degree_rel2(far_from, ?:X, ?:Y, ?:D,   ?:RC, ct),
 -has_degree_rel2(near,     ?:X, ?:Y, "none", ?:RC, ct)]
```
The intensity bridges (high→none, low→none) in axioms_std.js §9 then
propagate the `"none"` negation to all intensities via contrapositive, so
"very near" correctly rules out "far_from" at every degree.
Axioms emitted only when ≥2 members of a group appear in the problem or axiom vocabulary
(two-side restriction via `REQUIRE_BOTH_SIDES`).

**(c) Subsumption axioms — near-synonyms (static, in axioms_std.js)**

A small set of universally-useful one-way implications, placed as static axioms in
`axioms_std.js` §7c (spatial) and §7d (temporal). Direction is always
specific → general (the more specific predicate implies the more general one):
```
underneath, beneath, under   →  below          [§7c]
over, on_top_of              →  above          [§7c]
prior_to, preceding          →  before         [§7d]
following                    →  after          [§7d]
```
These are static (always loaded) rather than dynamically injected because the set is
small (~8 axioms), universally relevant, and should chain cleanly with other static
axioms in the KB.

**(c') Asymmetric "on" mutex axioms (static, in axioms_std.js §7e)**

Two pairs that don't fit either the dynamic-mutex template (no group in `excl_a.txt`)
or the symmetric subsumption pattern: "on" excludes "under" and "below", because
"on" means top-surface contact:
```
[-is_rel2(on, ?:X, ?:Y, ?:C), -is_rel2(under, ?:X, ?:Y, ?:C)]
[-is_rel2(on, ?:X, ?:Y, ?:C), -is_rel2(below, ?:X, ?:Y, ?:C)]
```
Both static and strict.  Closes case 150 ("Mary found the key under the table.
Was the key on the table?" → False) via the existing X3 verb→relation bridge
(verb `find` produces `is_rel2(under, key, table, …)`) plus the new mutex.

**(d) Direct-support uniqueness — X2 (static, axioms_std.js §7g)**

Captures "an entity has at most one immediate `on` support" (with escapes for
stacked / part-of configurations):
```
[-is_rel2(on, ?:X, ?:Y1, ?:C),
 -is_rel2(on, ?:X, ?:Y2, ?:C),
 =(?:Y1, ?:Y2),
 $block(0, is_rel2(on,      ?:Y1, ?:Y2, ?:C)),
 $block(0, is_rel2(on,      ?:Y2, ?:Y1, ?:C)),
 $block(0, is_rel2(part of, ?:Y1, ?:Y2, ?:C)),
 $block(0, is_rel2(part of, ?:Y2, ?:Y1, ?:C))]
```
Strict in conclusion. Relies on entity UNA via `#:` (lc_post_una) so that the
forced equality `Y1 = Y2` between syntactically distinct Stage-1 entities yields
an immediate contradiction. Closes case 148 ("John ate the pizza on the table.
Was the pizza on the floor?" → False) via X3 bridge → X2 → UNA.

For LLMs that introduce a Skolem for the question's entity (e.g. deepseek's
`sk1_floor` for "the floor"), UNA does not directly contradict — but the
within-group noun-mutex axioms emitted by `inject_exclusion_axioms` for
`NOUN_FURNITURE_FIXTURE` (table, floor) provide an alternate refutation path
via paramodulation through the X2-derived equality.

**(e) Carrier transparency — defeasible (static, axioms_std.js §7f)**

```
{ "@confidence": 0.85,
  "@logic": [
    [-isa, "carrier", ?:C, ?:Ctxt],
    [-is_rel2, "on", ?:X, ?:C, ?:Ctxt],
    [-is_rel2, "on", ?:C, ?:S, ?:Ctxt],
    [is_rel2, "on", ?:X, ?:S, ?:Ctxt],
    [$block, 0, [$not, [is_rel2, "on", ?:X, ?:S, ?:Ctxt]]]
  ]
}
```
The carrier tag is supplied dynamically by `inject_carrier_lifts` (one lift per
carrier noun present in the problem). Handles "pizza on plate, plate on table →
pizza on table" while leaving non-carrier intermediates (table, chair, …) opaque
so case 148 stays False.

**Canonical rewriting adjustments for has_degree_rel2 forms:**
- `"far"` → `"far_from"` (LLM sometimes drops "from" in query form)
- `"close to"` / `"close_to"` → `"near"` (close_to collapsed into near; subsumption not needed)

**Out of scope for now:**
- `earlier_than` / `later_than` (also `has_degree_rel2`): no active exclusion partner in
  tests (temporal order is captured in `is_rel2(before/after)`). A subsumption like
  `earlier_than → before` would require crossing `has_degree_rel2 → is_rel2` — a
  different axiom shape.

**Interaction example.** For "The car parked behind the house was blue. Was the car in
front of the house?":

1. Stage 2 emits `is_rel2("behind", car, house, C)` and query
   `is_rel2("in_front_of", car, house, C)`.
2. `rewrite_meta_predicates` is a no-op here (both already canonical).
3. `inject_exclusion_axioms` sees both `behind` and `in_front_of` in `SPATIAL_SAGITTAL`
   and emits `[-is_rel2("behind",?:X,?:Y,ct), -is_rel2("in_front_of",?:X,?:Y,ct)]`.
4. Assertion + exclusion axiom derives `-is_rel2("in_front_of", car, house, C)`,
   contradicting the query → answer **False**.

---

## 10. Extending and modifying the pipeline

### Adding new predicates

1. Add the predicate to the whitelist table in `prompts/stage2_instructions_full.txt` (section
   `== 5. PREDICATE INVENTORY ==`).
2. Add examples to `prompts/stage2_examples.txt` showing the new predicate in context.
3. If the predicate should receive `$ctxt`, add it to `CTXT_ELIGIBLE` in `lc_ctxt.py`.
4. If the predicate needs to render in an explanation, add an entry to
   `_PRED_TABLE` in `proof_render.py` (or a special-case handler in `_render_atom`).

### Modifying Stage-1 parsing behaviour

Edit `prompts/stage1_instructions_full.txt` and add/update examples in `prompts/stage1_examples.txt`.
The most impactful sections are:
- `== 4. TYPE CLASSIFICATION ==` — when to use `real`/`situation`/`strict_rule`/`normal_rule`
- `== 12. ADJECTIVES ==` — the adjectives field format
- `== 8. SCOPE HINTS ==` — dependent/global/kind scope for generics

### Modifying Stage-2 compilation behaviour

Edit `prompts/stage2_instructions_full.txt` and `prompts/stage2_examples.txt`.  The most impactful
sections are:
- `== 4. QUANTIFICATION RULES ==` — how each ASU type is compiled to FOL
- The Property and Relation Predicate Selection Rule — `has degree property` vs `has property`

### Defeasible bridge axioms in `axioms_std.js`

A recurring pattern: bridge a surface verb to a canonical predicate **defeasibly** so other readings can override it.  Shape: `[-source(...), canonical(...), $block(0, $not canonical(...))]` at `@confidence` < 1.  Examples currently in the file: `pass → give` at 0.85 (most "pass" events are transfers, but exam-passing should not be); `keep ... in/at LOC → is_rel2` at 0.95 (two siblings — `has_location` and `has_destination`).  Use this pattern when a surface word has a dominant canonical reading but rare alternatives must remain reachable; use a hard rewrite (no `$block`) only when the equivalence is exceptionless.

### Adding a new LLM provider

In `llmcall.py`, add a `call_newprovider(sysprompt, input_text, version, max_tokens)` function
following the pattern of `call_claude`, `call_gpt`, or `call_deepseek`, then dispatch from
`call_llm` when `llm == "newprovider"`.

### Improving proof post-processing

`procproofs.py` orchestrates answer post-processing; selection lives in
`proof_answer_select.py` and rendering in `proof_answer_format.py`.  Key extension points:
- `proof_explain.format_explanation` — generates the step-by-step English proof
- `_answer_goodness` in `proof_answer_select.py` — the sorting key for ranking multiple candidate answers
- `_filter_by_best_tier` in `proof_answer_select.py` — selects among concrete, Skolem, and population answers

### Running tests

There are two runners.  Both read the same test files, but each test file is now a list of
`[id, input, expected]` triples (the leading integer `id` is required — it is the stable case
number used across the runners and `testfixlog_may.txt`).

**`test.py` — single LLM, human-readable, resumable.**  Writes a flat `test_output.txt`
and re-uses prior results unless `-restart` is passed.

```bash
python3 test.py                         # run all tests with the default LLM
python3 test.py tests/tests_core.py -llm claude
python3 test.py tests/tests_core.py -filter penguin -limit 20
```

**`runtests.py` — every case × N LLMs in parallel, machine-readable.**  For each case it
runs the requested LLMs concurrently (one worker per LLM) and writes one JSON file per
`(case, llm)` to `testresults/<testname>/<llm>/case_NNNN.json`, where `<testname>` is derived
from the test filename (`tests/tests_core.py` → `core`).  After every case it rebuilds each
LLM's `summary.json` (pass/fail/error counts plus a `failed_or_errored` list), so progress is
live and a run can be inspected or interrupted at any point.

```bash
# default: all four LLMs (gpt, claude, gemini, deepseek) over tests/tests_core.py
python3 runtests.py

# pick LLMs and a test file
python3 runtests.py -llms claude,gpt tests/tests_core.py
python3 runtests.py -llms gemini tests/tests_core_100.py -geminicache

# selection
python3 runtests.py -ids 11,15,18          # only these case ids
python3 runtests.py -limit 50              # first 50 cases
python3 runtests.py -filter penguin        # cases whose input contains "penguin"

# run sequentially in-process (best for cache-served reruns)
python3 runtests.py -sequential -llms claude tests/tests_folio_v2.py

# model/decoding overrides (apply to all -llms in the run)
python3 runtests.py -version claude-opus-4-8 -think 3000 -maxtokens 16000 ...

# pipeline-mode flags (mirror solve.py; see DOCUMENTATION §11/§12)
python3 runtests.py -abstract -prenorm [-nocrossstage] ...
python3 runtests.py -combined-instr prompts/combined_v2_instructions_full.txt \
                    -combined-examples prompts/combined_examples_pure.txt ...
python3 runtests.py -directanswer prompts/folio_directanswer_instructions.txt ...

# output-dir suffix: results go to testresults/<set>_<tag>/ instead of testresults/<set>/
python3 runtests.py -tag myexperiment ...
```

Variant modes auto-suffix the set name (`-combined-*` derives a tag from the prompt
filenames; `-directanswer` uses `directanswer`; `-tag` overrides), so variant results
live beside — never on top of — the plain two-stage `testresults/<set>/` data.

**Provenance stamp:** every `summary.json` carries a `pipeline_git` object —
`{"commit": ..., "dirty": ..., "tags": [...]}` — recorded at run start
(`pipeline_git_state()`; the dirty flag covers tracked files only).  This ties each
results dir to the exact pipeline state that produced it.

**Resumption:** a `(case, llm)` is skipped if its JSON already exists.  Re-running therefore
continues where a quota-exhausted or interrupted run stopped.  Pass `-redo-errors` to also
re-run cases whose JSON contains an `"error"` key, or `-redo` to overwrite everything.  A
solo-Gemini run (`-llms gemini`) inserts a small per-case throttle, since without other LLMs
sharing the loop its back-to-back Stage-1/Stage-2 calls hit per-minute rate limits easily;
pair it with `-geminicache` (and see §5.3) on tiers with a tight per-request input cap.

The per-case JSON holds the full collected artifact set — `stage1`, `stage2`, `clauses`,
`gk_command`, `proof`, `nl_proof`, `answer`, `correctness` — so failures can be triaged
without re-running the pipeline.

To regenerate the logconvert pretty-print check file after changes to `logconvert.py`:
```bash
python3 run_pretty_check.py > logconvert_check.txt
```

---

## 11. Event-encoding and abstraction machinery

The event base is selected by `-event MODE` and a set of additive abstraction
primitives; together they select progressively flatter event encodings, built for
deductive benchmarks (FOLIO) whose gold logic uses atomic n-ary relations.  What the
*encodings* look like is described in ENCODINGS.md §6; this chapter describes the
machinery.  All of it is post-LLM: the Stage-1/Stage-2 prompts and calls are unchanged
(and cache-shared with default runs); everything happens between Stage 2 and the
prover, plus one optional cross-stage LLM retry.

### 11.0 The encoding resolver (`lc_encoding.py`)

Every encoding gate in the pipeline reads a single resolved config.
`lc_encoding.EncodingConfig`, built once from the option keys (`lc_encoding.current()`
reads the live `globals.options`), exposes the derived booleans the rest of the
pipeline consults: `flatten`, `eventprop`, `davidson`, `coarse`, `entitymerge`,
`guarddrop`, `bridges`, `dropdefinites`, `localantonyms`, `simpleprops`,
`collapse_degree`, `parse_canon`, `needs_coarsen`, `typeenrich`, plus a `te(gate)`
method for the per-gate type-enrichment test.  Every encoding read site in
`logconvert.py`, `lc_sets.py`, `lc_coarse.py`, `semnormalize.py`, `lc_post_reify.py`
and `solve.py` goes through this config, so the gating logic lives in exactly one place.

Population of the config:

- **Event base** — `-event MODE` sets `event_base` ∈ {`neodavidson` (default, reified
  neo-Davidsonian), `davidson` (compact `event(V,A,O,E)`), `flat` (bare positional
  `is_rel2` object), `flatroles` (`is_rel2` with eventprop-tagged object)}.  From it:
  `flatten = base in {flat, flatroles}`, `eventprop = base == flatroles`,
  `davidson = base == davidson`.  `coarse` is always `False`.
- **Additive primitives** — one option key each: `entitymerge_flag`, `guarddrop_flag`,
  `bridges_flag`, `dropdefinites_flag`, `localantonyms_flag`, `noproptypes_flag`
  (`simpleprops`), and `typeenrich_flag` (+ optional `typeenrich_gates`).
  `collapse_degree` rides with `simpleprops`; `parse_canon` rides with `entitymerge`
  (parse-level entity canonicalization is self-contained, driven by `-entitymerge`).
- **`needs_coarsen`** — true iff any of `davidson`/`flatten`/`entitymerge`/`guarddrop`
  is set, i.e. whether `coarsen_events` runs at all.
- **typeenrich gates** — `typeenrich_gates` is a frozenset over
  `{super, gender, nametype, compound, plural, gnoun}`; bare `-typeenrich` enables all
  six, `-typeenrich=GATES` enables the named subset, and `te(gate)` is the per-gate
  test.

The `-abstract*` presets (§12.0) are pure CLI expansions into these primitive keys —
they are read nowhere in the pipeline, only at argument-parse time.

### 11.1 The event folds (`lc_coarse.py`)

`coarsen_events(tree, flatten=, eventprop=, davidson=, coarse=, do_canon=, do_guard=,
collapse_degree=)` is called from `rawlogic_convert` (only when
`EncodingConfig.needs_coarsen`) after actuality injection and tense-`has_time`
stripping, so the eligibility test sees the final event shape.  All gating is resolved
by the caller; the params are the already-derived `EncodingConfig` booleans (the
`coarse` arg is vestigial, always `False`).  With `flatten` it applies the aggressive
flat folds (relational `is_rel2`, unary `has_property`, topic/passive/intransitive
variants, `typical` stripped) — see ENCODINGS.md §6.2 for the rule list; with
`eventprop` the single object slot is role-tagged as
`is_rel2(V, subj, ["eventprop", $role, value])`.  With `davidson` it applies instead
the structure-preserving compact fold into `event(V,A,O,E)`.  `lc_ctxt` registers the
folded predicate in `CTXT_ELIGIBLE` and `DESC_PREDS`, so it receives `$ctxt` exactly
as reified roles would.

Supporting passes inside `lc_coarse` (in order, when their gate is set):
- `_canonicalize_entities` (`do_canon`/`entitymerge`) — tree-level merge of split
  proper-noun constants (type-sharing + surface-similarity union-find);
- `_collapse_degree_node` (`collapse_degree`/`simpleprops`) — early degree→simple
  collapse, before guard analysis;
- `_fold_antecedent_events` (with a flat fold) — folds an event introduced as bare
  conjuncts in a rule antecedent (no `exists` wrapper), so rules and folded facts
  unify; uses `_rewrite_rel2_event_object` to free event variables that appear as
  `is_rel2` objects;
- `_drop_redundant_guards` (`do_guard`/`guarddrop`) — drops antecedent `isa` guards
  that are vacuous (near-universal types) or redundant (variable already bound by a
  folded literal); a no-op without a fold base.

`inject_verb_bridges` (per-verb bidirectional event↔relation bridges) is defined but
not wired; the generic `rel2_event_axiom_clauses()` equivalence (§11.3) is used
instead.

### 11.2 Compile-level passes outside `lc_coarse`

Each is gated on the resolved `EncodingConfig` field shown:

| pass | where | gate | what |
|---|---|---|---|
| self-defeating-conditional repair | `lc_repairs.repair_self_defeating_conditional` | `flatten` | widens a mis-scoped `¬A ∧ B` antecedent to `¬(A∧B)` when a truth-table check shows the conditional can never produce its consequent |
| broad-supertype isa | `lc_entity_isa.build_entity_category_clauses` | `te("super")` | `isa(person/animal,E)` emitted even when Stage 2 already typed E |
| gender from first name | same | `te("gender")` | `isa(man/woman, E)` from `data_names.gender_of` |
| name-as-type isa | same | `te("nametype")` | a multiword proper name also typed by its lowercased name |
| gendered-noun axioms | `rawlogic_convert` tail | `te("gnoun")` | `isa(gentleman,X) → isa(man,X)` etc., for role nouns present in the clauses (`data_names.GENDERED_NOUN`) |
| compound suffix subsumption | `lc_post_normalize.build_compound_subsumption` | `te("compound")` | subsume to every attested intermediate suffix; also scans entity-category clauses |
| isa-class lowercasing | `lc_clausify.lower_isa_classes_in_node` | `flatten` | run after all injection, folds class-name case |
| definite handling | `rawlogic_convert` | `dropdefinites` | when `dropdefinites`, definite reification is skipped entirely (definites left as plain relations); otherwise `lc_post_reify` reifies `$theof1` with lenient first-match identities |
| antonym presence-gating | `semnormalize` | `localantonyms` | antonym folding fires only when the target word is in problem ∪ axiom vocab |
| `$setof` content labels | `lc_sets._content_label` | `entitymerge` | set ids become content-derived hashes so structurally identical sets unify |
| `$ctxt` decoupling | `rawlogic_convert` last pass | `flatten` | every `$ctxt` term replaced by a fresh variable |

### 11.3 Dynamic bridge axioms (`lc_post_inject.py` + `lc_coarse.py`)

Appended to the clause list under `-bridges` (which needs a `flat`/`flatroles` base),
each gated on both bridge sides being present in the problem: `rel2_event_axiom_clauses`
(relation ↔ reified event, Skolem `$ev_of(V,A,O)`), `inject_occasion_location_bridges`
(co-location through an occasion, typed on physical place classes),
`inject_in_haspart_bridge` (`in` → `has_part`), `inject_reflexive_property_bridge`
(`has_property(P,X) ↔ is_rel2(P,X,X)`).  Shapes in ENCODINGS.md §6.4.

### 11.4 Entity unification at the parse level (`llmparse.py`, `-entitymerge`)

Driven by `EncodingConfig.parse_canon` (i.e. `-entitymerge`).
`canonicalize_entity_ids(s1_json)` merges Stage-1 entity ids by normalized form,
suffix-stripped base, head-sharing token subset, and high-threshold Levenshtein —
proper nouns only, longest-id-first whole-id replacement (no substring corruption).
`canonicalize_entity_urls(s1_json, s2_json)` rewrites Stage-2 Wikipedia-URL constants
to the best-matching Stage-1 entity id (page-title similarity; ambiguous ties left
alone).  Both record their remaps in the parse stats.

### 11.5 Cross-stage unsatisfiable-guard retry (`llmparse.py` + `stage_sanity.py`)

After Stage 2 (only with a flat fold base, at most once, disable with `-nocrossstage`):
`stage_sanity.check_unsatisfiable_guards` collects content guards — a class
(`isa`), property (`has property`) or relation (`is rel2`) appearing positively in a
rule antecedent that no fact states and no rule consequent produces.  Such a rule can
never fire, which usually means Stage 1 dropped a word.  If guards exist, BOTH stages
re-run on the ORIGINAL text (not the prenormed one — prenorm itself can be the
dropper) plus a neutral hint (`format_guard_retry_suffix`) naming each guard.  The
retry is kept only if it resolves ALL originally-flagged guards; otherwise the
original parse stands, so a genuinely-absent class is never invented.  The related
`_check_stage2_constant_vs_class` sanity check (a name used as both constant and
class; re-prompts Stage 2) is enabled on the same path via
`stage_sanity.aggressive_repair`.

### 11.6 The abstraction primitives and proof-shortening folds

Each abstraction lever is its own composable primitive, so it can be measured in
isolation (the per-mechanism tables in the LPAR paper).  The `-abstract*` presets set a
fixed subset of them; resolution is centralized in `EncodingConfig`.  The event-base
folds and entity/guard mods are handled in `lc_coarse.coarsen_events` (§11.1); the
others are `lc_existfold` plus the type-enrichment gates.  Reference shapes:
ENCODINGS.md §6.6–6.10.

- **Event base** (`-event flat` / `-event flatroles` / `-event davidson`): the fold
  shape, resolved to `flatten`/`eventprop`/`davidson` (§11.0).  `-event flat` runs only
  the relational `_fold_event_flat` (no entity canon / degree collapse / guard-drop /
  Skolem merge / supertypes / defeasibility strip — those are separate primitives);
  `-guarddrop` and `-bridges` are no-ops without a flat base.  `-event flatroles`
  (`eventprop`) role-tags the single object slot as
  `is_rel2(V, subj, ["eventprop", $role, value])`.
- **`-typeenrich[=GATES]`**: gates the six `isa`-enrichment sub-injectors via the
  `logconvert._te(gate)` helper (which delegates to `EncodingConfig.te`).  Gates:
  `super, gender, nametype, compound, plural, gnoun`; bare `-typeenrich` enables all
  six.  A `TE_SKIP` env var can disable individual gates for diagnostics; the `plural`
  gate is the one that over-derives population witnesses on core.
- **`-entitymerge`, `-guarddrop`, `-bridges`, `-dropdefinites`, `-localantonyms`**: the
  remaining additive primitives, each described at its read site in §11.2–11.5 and
  §11.0.
- **`-event davidson`** (`_davidson_event`, `_davidson_mode`): structure-preserving fold
  of the event spine into `event(V,A,O,E)`, keeping the handle and every adjunct.  The
  patient slot takes the first theme role in `_DAV_PATIENT_ROLES = ["has target","has
  goal","has topic"]`; datives/obliques stay as adjuncts; absent agent/patient become
  fresh existentials; the biconditional `frm_event` bridge (`event_axiom_clauses`)
  interderives with the reified roles and projects `is_rel2`.  A clausify guard
  (`lc_clausify`) drops any headless clause left when the fold strips a defeasibility
  marker, so a generic rule never collapses to a bare negated antecedent.
- **`-existfold`** (`lc_existfold.fold_existential_attributes` + `bridge_clauses`): folds
  `∃Y.isa(C,Y)∧has_part/have(X,Y)` to `has_property([$has_part/$have,C],X)` and emits a
  bidirectional bridge with the named witness `$typed_partof(X,C)` (forward, reverse, and
  the witness-isa clause).  Narrow and parse-dependent.

Per-suite effect (LPAR runs): on the default representation `-event davidson` shortens
proofs and is accuracy-neutral on both suites; on the already-flat `-event flatroles`
FOLIO base it net-lengthens.  `-existfold` shortens only the few reified-existential
chains and never lengthens FOLIO; on core it matches almost nothing and its bridge
axioms lengthen more than they shorten.

### 11.7 Default-path footprint

The event-encoding work leaves exactly two behaviors on the default (`-event
neodavidson`, no primitives) path: the ASCII fold of parses (§5.1) and the canonical
sanity-retry serialization (§7.8).  Everything else in this chapter is flag-gated; with
no flags the pipeline is answer-equivalent to the `core-2026-06-03` checkpoint
(verified on a stratified 40-case × 4-LLM sample — byte-identical clauses modulo
set-iteration order and fresh-variable numbering).

---

## 12. Abstraction presets and alternative parsing modes

### 12.0 Abstraction presets (`-abstract` family)

The presets are pure CLI expansions into the §11 primitives — they are read nowhere in
the pipeline, only at argument-parse time (`solve.py`), where they set the primitive
option keys.  Three are defined:

- **`-abstract`** = `-event flat` + `-entitymerge` + `-guarddrop` + `-bridges` +
  `-dropdefinites` + `-typeenrich` + `-localantonyms` + `-simpleprops`.
- **`-abstract-roles`** = `-abstract` but with `-event flatroles`
  (eventprop-tagged objects).
- **`-abstract-max`** = `-abstract-roles` + `-prenorm` (the strongest abstraction; the
  FOLIO base configuration).

Because they expand into primitives, any preset composes with an explicit override
(e.g. drop one primitive by not letting the preset set it, or layer `-existfold`).

The alternative parsing modes below replace or augment the two-LLM-call parse.  All are
selected per run (CLI flags / option keys), share the LLM cache keyed on their own
prompts, and are available in `runtests.py` with auto-suffixed output dirs (§10).

### 12.1 `-prenorm` — pre-Stage-1 wording normalisation

`llmparse.normalize_text` makes one extra LLM call with
`prompts/prenorm_full.txt` to rewrite the input English so the same entity /
property / relation is always worded identically, then feeds the rewritten text to
Stage 1.  Returns the original text on any error.  Composable with every other mode;
part of the `-abstract-max` FOLIO configuration.

### 12.2 Combined single-stage parsing (`-combined-instr` etc.)

ONE LLM call converts English directly to Stage-2 logic; the ASU analysis is worked
out "in the head" and never printed.  Prompt = explicitly named files composed by the
same `_compose_prompt` (instructions required, examples/checklist optional;
constructions described in `prompts/README.md`).  `parse_text` returns
`(None, s2_json, stats)` — there is no Stage-1 JSON, so s1-derived processing
(entity-category `isa` injection, `$ctxt` tense from ASUs, richer NL rendering) is
absent by design; downstream code guards `s1_json=None` throughout.  The Stage-2
sanity checks and corrective retries run unchanged.  Batch scoring: `runtests`
passes `single_stage=True` to the matcher, enabling a conservative
rendering-artefact fallback (temporal-preposition, URL/diacritic, plural-coordination
and truncated-stem leniences in `test.py`); two-stage runs are scored strictly as
before.

### 12.3 Direct answer (`-directanswer FILE`)

`solver/directanswer.py` answers the question with ONE LLM call using FILE as the
system prompt — no logic, no prover, test-set agnostic.  The reply is normalised by
`_extract_verdict`: if it contains a True/False/Unknown/Uncertain token, the LAST one
wins (reasoning models often write a chain of thought ending in the verdict),
normalised to `"True." / "False." / "Unknown."`; otherwise the stripped reply is the
answer (phrase-style prompts).  `collect` gets `answer` and a `directanswer` metadata
field.  Used for the FOLIO direct-answer reference runs
(`prompts/folio_directanswer_instructions[_noworld].txt`).

### 12.4 Split Stage 2 (`-s2split`)

One Stage-2 LLM call **per Stage-1 sentence package** instead of one call for the
whole text.  Each call's input is `json.dumps([package])` — a single-element list,
exactly the input format the unchanged Stage-2 prompt specifies — and gets the full
JSON-fix + sanity-retry machinery, scoped to its own sentence, plus a split-only
sanity check (`check_stage2_id_coverage`): the emitted `["@id", ...]` ids must equal
the slice's `unit_id` set (the main isolated-sentence failure is the LLM renumbering
ids to S1…), routed through the normal corrective retry.  The per-sentence outputs
are joined in order into one `["and", pkg...]`, indistinguishable downstream.

**Failure policy:** a sentence whose Stage-2 call fails after retries is skipped
(recorded in `stats["s2_split_skipped"]`) — unless it contains the question
(a Stage-1 unit of type `query`, or `raw` ending in `?`), in which case the whole
Stage 2 fails.

**World renumbering (rule c′):** Stage-2 world constants (`W0, W1, …`) are numbered
globally across sentences in state-tracking narratives, so per-sentence outputs must
be re-aligned at join time.  Per split: worlds *anchored* by the slice itself — `W0`
(the shared initial world) plus any `pre_state`/`post_state` annotation on the
slice's Stage-1 units — keep their numbers; every other (locally-invented) world is
remapped, in ascending order, to the next free global index (starting at
max-seen-so-far + 1, skipping anchored indices).  Static text (everything in `W0`)
is therefore untouched, Stage-1-annotated state chains keep their global numbering,
and locally-invented result worlds never collide across splits.
`inject_world_geometry` chains whatever distinct worlds the join produces.

Mode interaction: incompatible with combined single-stage parsing (no Stage-1 to
split; `english_to_answer` returns an error if both are set); composes with
`-prenorm` and the event-base / `-abstract*` modes (the split runs inside
`_stage1_then_stage2`, so the flat-fold cross-stage retry re-splits).  Each slice
is its own LLM-cache key.  `runtests.py -s2split` writes to
`testresults/<set>_s2split/` unless `-tag` overrides.

**Cross-sentence shape-unification repair (part of `-s2split`).**  The dominant
`-s2split` failure is cross-sentence predicate-choice divergence: each isolated call
makes a locally-valid encoding choice that disagrees with the sibling sentence it must
unify with (`have` vs `has part` — covered by the static `has_part`→`have` axiom once
the rename below applies, `has location` vs `has destination`, a role on the target
entity vs on the event, `small fish` as a compound isa vs adjective + noun, a comparative
vs `less_measure` arithmetic, plus off-inventory predicate drift `has`/`has rel2`).  The
repair for these is applied automatically under `-s2split` (gated on `s2split_flag`); the
default joint and abstraction paths are untouched.  It enables:
- an off-inventory rename and form-normalization pass in `logconvert`:
  predicate renames (`has` → `have`, `has rel2` → `is rel2`, `has agent` →
  `has actor`), comparative-phrase relation names reduced to the base adjective
  (`has degree rel2("higher than", …)` → `"high"`, gated on the gradables
  whitelist so ordinary relation names are untouched), and adjective-as-dimension
  `$measure_of` slots mapped to the dimension noun (`$measure_of("tall", …)` →
  `"height"`);
- dynamic shape bridges (`lc_post_inject.inject_s2split_shape_bridges`, confidence
  0.99, each gated on both shapes being present): `has_destination` → `has_location`
  (axioms_std.js has only verb-specific location/destination siblings), beneficiary/recipient lift from the event to
  its target, and `less_measure($measure_of(D,…))` ↔ `has_degree_rel2(ADJ,…)` via a
  dimension→adjective table;
- compound composition in property shape (`build_compound_subsumption(degree_comp=True)`):
  the modifier may arrive as a degree/simple property instead of an `isa`;
- broad-supertype `isa(person/animal, E)` emission (the same `te("super")` enrichment);
- a participle-persistence variant (Bridge C) in `inject_verb_result_state_axioms`:
  when the result state arrives directly as the past participle
  (`has property("destroyed", X)` at past/W, no verb form in the clauses), persist
  it into the next world at present tense — the same target context Bridges A/B
  produce — so the result-state mutexes can fire on the question's present-tense
  reading.

On the curated 100-subset (joint two-stage baseline = 100/100 for all four LLMs by
construction), `-s2split` scores gpt 100/100, claude 100/100, deepseek 97/100 — the
three residual deepseek cases (541, 663, 1335: generic-question subject construction,
category-instead-of-noun typing, RELCLASS divergence) are diagnosed but deliberately
unfixed pending proof-level analysis.  (The repair is essential to this: without it the
isolated per-sentence parses diverge and gpt drops to ~93/100.)
