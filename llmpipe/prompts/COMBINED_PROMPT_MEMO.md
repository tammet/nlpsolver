# Combined single-stage prompt — design memo

## Goal

The current parser runs in two LLM calls:

- Stage 1: English → Atomic Semantic Units (ASUs), a normalized JSON analysis.
- Stage 2: ASU JSON → first-order logic JSON (the prover input).

We are testing whether a **single LLM call** can take English and emit the logic
directly. There are several ways to collapse the two stages; the first approach
we pursue keeps the Stage-1 ASU analysis **"in the head"** — the model is told to
work out the ASUs internally but to output only the Stage-2 logic, never the
ASUs themselves.

These are additive experiments. None of the existing `stage1_*` / `stage2_*`
prompt files are modified, and nothing is wired into `llmparse.py` yet — the
combined files are built so a runner can assemble and test them.

## The three independent dials

The combined-prompt design has three orthogonal choices. Each experiment fixes
all three.

| dial | options | meaning |
|---|---|---|
| prompt construction | **v1** / **v2** / **v3** (/ v4) | how aggressively the two instruction bodies are merged |
| example presentation | **pure** / **internal** | whether the few-shot examples show the hidden ASU step |
| where the analysis goes | **in-the-head** / **direct** / visible-CoT | ASU built mentally / no intermediate at all / emitted-then-stripped |

The **direct** variant (`combined_direct_*`) is a separate construction: it has no
ASU concept at all — see "## direct build notes" below.

Construction options: **v1** conservative concat, **v2** condensed (single schema,
hoisted contract), **v3** faithful topic-oriented restructure with continuous
renumbering, **v4** (deferred) aggressive paraphrase to actually shrink bytes,
**minimal** signature-only (~10 KB — no case rules; just the task + the logic
signature; the examples carry all the "how"). See "## minimal build notes".

So far built: **v1, v2, v3**, both example flavors, **in-the-head**. (Visible-CoT
— emit the ASU as chain-of-thought and strip it in post-processing — is the
natural next output strategy but is deliberately deferred.)

## The "in-the-head" principle

Formulated for low-thinking (`think=False`, no reasoning-token) LLMs, which follow
concrete "do X silently, output only Y" instructions better than abstract "reason
internally" language. The principle is stated **three times** — header, the
Part-1→Part-2 transition, and a final reminder — e.g.:

> Build this ASU structure IN YOUR HEAD. Do NOT write it down. Do NOT print it.
> ... Print ONLY the final logic list `["and", ...]`.

Caveat worth keeping in mind when reading results: for genuinely non-thinking
runs, "in the head but not emitted" means the model must do the analysis in a
single forward pass with no scratchpad. So in Variant B the shown ASU is a
**teaching signal in the few-shot**, not a runtime scratchpad.

## Example variants A and B

Both variants come from **one aligned source**, `stage2_examples.txt`, whose
`INPUT` blocks carry the original English (in the `raw` fields), the ASU, and the
`OUTPUT` logic. So the two variants are the *same example set*, differing only in
whether the intermediate ASU is shown.

| variant | file | example shape | tests |
|---|---|---|---|
| A — pure | `combined_examples_pure.txt` | `English → logic` | can the model learn the end-to-end map with no demonstration of the intermediate? Risk: a low-thinking model may shortcut to shallow logic without the forced analysis. |
| B — internal | `combined_examples_internal.txt` | `English → [internal ASU, "do NOT print"] → logic` | does demonstrating the analysis improve logic quality while keeping the ASU unemitted? Risk: leakage (model copies the ASU into output), countered by fencing + the final "output only the logic" reminder. |

How they were built (`/tmp/parse_examples.py`, `/tmp/gen_examples.py`):

- Split `stage2_examples.txt` on the dashed separators → 64 blocks → 61
  `INPUT`/`OUTPUT` pairs that parse cleanly; all 61 logic outputs are valid JSON.
- English reconstructed by joining the `raw` fields across each example's
  packages, in order. One pair had empty English (a header-ish block) and was
  dropped → **60 usable examples**.
- Variant A prints `Input:` / `Output:`; Variant B inserts the ASU between them
  labeled "Internal analysis (build this in your head — do NOT print it)" and the
  logic as "Output (print ONLY this)".
- Verified: the pure file contains no `raw`/`units`/`unit_id` keys (no ASU leak).

## The four v1 files

| file | size | role |
|---|---|---|
| `combined_instructions_full.txt` | 109 KB | shared instructions — Step-1 (internal) + Step-2 (output) bodies, one merged document |
| `combined_checklist_full.txt` | 3.7 KB | merged checklist — Step-1 (internal) + Step-2 (output) sections |
| `combined_examples_pure.txt` | 32 KB | Variant A — 60 `English → logic` |
| `combined_examples_internal.txt` | 72 KB | Variant B — 60 `English → [internal ASU] → logic` |

A variant's system prompt = `combined_instructions_full.txt` + the chosen examples
file + `combined_checklist_full.txt` (same concatenation pattern the pipeline uses
for the stage prompts). The English is the user message; the logic is the only
output.

## How v1 is built

`/tmp/build_instructions.py`, `/tmp/build_checklist.py`:

- **Instruction bodies kept verbatim.** Only the I/O contract was re-stitched:
  Stage-1's "output format" became "the ASU structure you build in your head",
  Stage-2's "your input is ASU JSON" became "the ASUs you built in Step 1", and
  every `Stage 1/2` → `Step 1/2` (verified zero leftovers across all combined
  files).
- New unified header states the two-step "in-the-head" contract; a transition
  separates Part 1 (build ASUs silently) from Part 2 (emit logic); a final
  reminder repeats the output rule.
- Checklist: the two 12-item critical-rule lists merged under `STEP 1 — internal`
  and `STEP 2 — output` headings; `ENTITY IDS FROM STAGE 1` → `FROM STEP 1`.

## Sizes vs model limits

Original two-stage prompt total (all six source files): **224,327 B (~219 KB)**,
roughly **56K tokens** by the 4-bytes/token rule of thumb — likely **~65–80K real
tokens** because the text is dense JSON.

Assembled combined system prompts (smaller than the original, because the framing
was deduped and the pure variant drops ASUs from examples):

| variant | system prompt size |
|---|---|
| A (pure) | ~141 KB |
| B (internal) | ~180 KB |

Context windows of the four concrete models we use:

| model | input context | ~75K-token prompt fits? |
|---|---|---|
| gemini-2.5-flash | ~1,048,576 (1M) | yes, enormous headroom |
| gpt-5.1 | ~400K | yes |
| claude-sonnet-4-6 | ~200K | yes |
| deepseek-v4-flash | ~128K | yes, tightest but fine |

Verdict: ~200 KB is safe on all four. DeepSeek (128K) is the tightest and still
leaves ~50K tokens for the (tiny) English input plus the 8000-token output budget.
The output budget is unchanged — the single call emits only the Stage-2 logic,
which already fits `default_max_tokens = 8000`. At this size the prompt should be
sent as a stable *system* prompt so provider caching applies (Claude inline
`cache_control`, Gemini server-side `cachedContents`, GPT/DeepSeek automatic).

## v1 vs v2

Both use the same in-the-head approach and the same two example files; they differ
only in the instruction document.

**v1 — conservative merge (built).** The two instruction bodies are concatenated
essentially verbatim; only the I/O contract is re-stitched and `Stage`→`Step`
renamed. Nothing inside the bodies is reworded.

- Pro: cleanest experiment. The only change versus the working two-stage pipeline
  is the single-stage in-the-head merge itself, so a score shift is attributable
  to the merge, not to reworded instructions.
- Con: bulky and redundant. The ASU/entity schema is defined twice (Step-1
  "output format" ≈ Step-2 "input schema"); shared conventions are restated in
  both parts. Section numbers `§X.Y` also collide across Part 1 and Part 2.

**v2 — structural condensation (to be built next).** Same rules, stated once.

- One shared `COMMON: ASU & ENTITY SCHEMA` section instead of the two near-
  duplicate definitions.
- The logic output contract hoisted to the top, stated once.
- Tighter unified framing (no per-stage preambles, deduped "process every ASU /
  output only JSON" restatements).
- `§` ambiguity resolved by qualifying cross-part and checklist refs as
  `Step 1 §X` / `Step 2 §X` — but **each part's internal section numbers are kept
  intact**, because a global renumber would break the bodies' own `(see §5.11)`
  cross-refs (an error-prone, behavior-risking churn). Confirmed safe to hoist the
  schema/contract: neither body references `§0` or `§1` internally (only the
  headers do).

Explicitly NOT in v2: rewriting rule semantics. If v2 also reworded rules, a
v1-vs-v2 difference would be confounded (compactness vs changed instructions). v2
keeps every rule.

Intended sequence: run **v1** to isolate the effect of single-stage merging; if it
holds up, run **v2** to make it lean. If v1 underperforms badly, that says the
merge concept itself is the problem and condensing would not have rescued it.

v2 files (planned): `combined_v2_instructions_full.txt`,
`combined_v2_checklist_full.txt`. Examples are shared (no new example files).

## v2 build notes

Built (`/tmp/build_v2.py`, `/tmp/build_v2_checklist.py`):

| file | size | note |
|---|---|---|
| `combined_v2_instructions_full.txt` | 108 KB | condensed instructions |
| `combined_v2_checklist_full.txt` | 3.8 KB | merged checklist, refs qualified `Step 1/2 §X` |

What changed from v1, structurally:

- **Output contract hoisted** to the top as a standalone `OUTPUT CONTRACT`
  section (was Step-2 §0), so the target format is stated once, up front.
- **Single `COMMON: ASU & ENTITY SCHEMA` section** — the duplicate Step-2 input
  schema (stage2 §1.1) was dropped; the schema is now stated once (from stage1
  §0) plus the Step-2-only usage notes (entity.text rule, opaque-ids, flatten).
- **Unified header** lists the four parts and states the `§` convention
  ("Step 1 §X" → PART 1, "Step 2 §X" → PART 2). Checklist refs qualified to match.
- Confirmed safe: neither body references `§0`/`§1` internally, so hoisting the
  contract and merging the schema broke no cross-refs. Each part keeps its own
  internal section numbering and `(see §N.M)` refs intact.

Size reality: v2 is **107.7 KB vs v1's 109 KB — only ~1.3 KB smaller**. That is
expected and by design. v2 removes exactly one duplicated block (the second
schema) and reshuffles framing; it does **not** compress the rule prose, because
rewriting rules would confound a v1-vs-v2 comparison. So v2's value is structural
(one schema, no `§` collision, contract stated once), not byte count.

Assembled v2 system prompts (instructions + examples + checklist):
- v2 + pure ≈ 143 KB; v2 + internal ≈ 183 KB. (Essentially the same as v1, since
  the instructions are nearly the same size and the example files are shared.)

If a genuinely smaller prompt is wanted later, that is a heavier, higher-risk pass
("v3"): actually compress verbose rule prose, reconcile overlapping rules between
the two parts, and renumber into one continuous scheme. That changes rule wording,
so it must be measured against v1/v2 as its own variable, not folded into v2.

Not done: no LLM run yet. The merge's correctness is by construction + inspection
(no leftover `Stage` refs, schema stated once, boundaries read clean), not by
testing on the models.

## v3 build notes

Built (`/tmp/build_v3.py`, `/tmp/build_v3_checklist.py`):

| file | size | note |
|---|---|---|
| `combined_v3_instructions_full.txt` | 108 KB | topic-oriented, one continuous scheme §0..§23 |
| `combined_v3_checklist_full.txt` | 3.7 KB | same rules; `§` refs remapped to v3 numbers |

What v3 is (the "faithful restructure", Option 1 of the v3 discussion):

- **One topic-oriented spec.** The two stage bodies are interleaved by phenomenon
  under topic banners, each pairing an ANALYSE section (Step 1) with an ENCODE
  section (Step 2): Entities (§6/§7), Type+Quantification (§8/§9/§10), Actions
  (§11/§12), Questions (§14/§15), World+Time (§16/§17/§18), Mental (§21/§22), plus
  segmentation/normalisation (§3–5, analyse-only), adjectives (§13), relational
  nouns (§19), sets (§20), and a merged validation (§23). Output contract is §0,
  the single shared schema is §1, the predicate inventory is §2.
- **Continuous renumbering §0..§23**, fixing the `§` collision that v1/v2 had.
- **Built by deterministic relocation, not re-authoring.** A script slices both
  source files at their section headers and re-emits the blocks **verbatim** in
  topic order, renumbering headers and every `§`/`section` cross-reference via a
  per-part old→new map (cross-references to the other part are sentinel-protected
  so they map through the correct map, not double-mapped). So **no rule wording
  was changed or dropped** — only relocated and renumbered.
- Validated: every `§` reference in the instructions and the checklist resolves to
  an existing section (0..23, zero dangling); cross-refs land on the right topic
  (e.g. an action-compilation rule's "Step 1 §11.2.2" points at the actions
  ANALYSE subsection; "§5.11"→"§10.11"); no leftover `Stage` references.

Size reality: v3 is **108 KB — essentially the same as v1 (109 KB) and v2
(108 KB)**. That is expected: Option 1 preserves rule wording, so v3 is *organised*
better (one coherent topic-oriented spec, continuous numbering, single schema) but
not *smaller*. The win is navigability and the removal of the structural
analysis/encode split, not byte count.

Assembled v3 system prompts: v3+pure ≈ 140 KB; v3+internal ≈ 179 KB.

If a genuinely smaller prompt is wanted, that is **v4** = the aggressive paraphrase
(Option 2): reword rule prose tersely, reconcile/trim overlapping rules. It
changes rule wording, so it must be measured as its own variable on top of v3.

Not done: no LLM run yet. v3's faithfulness is by construction (verbatim block
relocation) + validation (all refs resolve, no leftover `Stage` refs), not by
testing on the models.

## direct build notes

A separate construction on the **"where the analysis goes"** dial: **no internal
representation at all.** v1/v2/v3 all tell the model to build the ASU in its head;
the direct prompt removes the ASU concept entirely and phrases every rule as
"English construction -> logic". It keeps a single one-line nudge ("work out the
structure of each sentence as you go") but names no intermediate artifact.

| file | size | note |
|---|---|---|
| `combined_direct_instructions_full.txt` | 107 KB | English -> logic, no ASU |
| `combined_direct_checklist_full.txt` | 3.7 KB | reading checks + logic checks (no Step-1/2 split) |
| `combined_direct_examples.txt` | 32 KB | independent copy of the pure examples (original English -> logic) |

How it was built (`/tmp/build_direct.py` + hand edits):

- **Derived from v3**, keeping v3's section structure and §0..§23 numbering so the
  `§` cross-references stay valid (no third renumber).
- New header/footer (read English, write logic, no intermediate); the ASU-schema
  section (v3 §1) replaced by a short **§1 "Reading the English"** orientation;
  topic banners and section headers stripped of the ANALYSE/ENCODE tags.
- **Every ASU-field reference reformulated into an English cue**, e.g.
  `entity.type == generic` -> "the entity is generic (indefinite / bare plural /
  in a rule or question)"; `if word in ASU.adjectives` -> "if the word is a
  gradable adjective"; `the mode field set by Step 1` -> "the verb's mode (from
  its markers)"; `{raw, units}` package -> "emit one ["@id","Sx",...] package per
  statement"; the action-object and adjective-triple JSON softened to "work out
  root/mode/roles" and "work out word/intensity/class". "ASU" -> "statement"
  throughout; "Step 1/2", "in your head", `unit_id`, `wh_placeholder`,
  `entity.*`, `simplified text` all removed.
- **Entity IDs still appear in the output** (`"John 1"`, `"car 2"`, urls) — the
  pipeline needs them — so a "Naming entities" responsibility is inlined; only the
  *input* is raw English.
- **Examples need no new content**: the pure examples are already original-English
  -> logic (the `raw` fields are the original sentences), so the direct example
  file is an independent copy of them.

Validated: zero residual ASU-structure language (`ASU`, `Step 1/2`, `raw`/`units`,
`wh_placeholder`, `unit_id`, `entity.*`, `simplified text`, `in your head`); every
`§` reference resolves (0..23, no dangling). Caught and fixed a substring bug
(`ASU`->`statement` had corrupted `MEASUREMENT`) and a wrong cross-reference for
Global Action Synchronization (now `§11.3`). Assembled direct system prompt:
~139 KB (instructions + pure examples + checklist).

Known caveats:
- **This is reauthored**, not relocated — rule *meaning* preserved, but wording of
  every field-reference changed. So like v4 it is its own variable; measure it
  against v1/v2/v3, and it MUST be validated by running on the four LLMs.

### A source-prompt typo (fixed in v3 and direct)

The query-mode rule pointed at "Global Action Synchronization, §5.3" — but in the
source `stage2_instructions_full.txt` itself, §5.3 is the *Two-Entity Interaction
Rule*; Global Action Synchronization is stage1 §6.3. So the **source prompt** had
the wrong section number. v3 faithfully renumbered the wrong ref (`§5.3`->`§10.3`);
the renumber script did not err. The ref is now corrected to point at Global
Action Synchronization (`§11.3`) in both `combined_v3_*` and `combined_direct_*`.
(The original `stage2_instructions_full.txt` still has the `§5.3` typo — left
unchanged, since we don't edit the source prompts.)

## minimal build notes

A radically smaller construction (`combined_minimal_instructions_full.txt`,
**~10 KB** vs ~107 KB for v1/v2/v3/direct). It drops ALL case rules and shapes and
gives only:

- the task (read English, simplify, convert to logic, use only what's listed),
- the output shape (`["and", ["@id","Sx",BODY], ...]`, the holds/question/ask
  bodies, the optional wrappers, the variable/entity/world conventions),
- the **full logic signature** — every allowed connective, quantifier, predicate,
  modal classifier, world/mental predicate and set/measure function-term, each
  with its arguments and a one-line meaning,
- "use ONLY these; the examples show how to combine them".

The idea: the signature is stated precisely; the **examples are the sole source of
patterns** (quantifier scope, event shapes, defaults, worlds, measures). Pairs
with the **unchanged** pure example file (`combined_examples_pure.txt`). No
checklist.

Sourcing & validation:
- Signature taken from the instruction file's own predicate inventory (stage2 §2)
  plus the set/measure terms (stage2 §9) and the output contract (stage2 §0) —
  the same signature the big prompts already carry. Verified: all **61** signature
  heads (inventory + set/measure) are present in the minimal prompt; none missing.
- **`$ctxt` deliberately excluded.** It is pipeline-injected (`lc_ctxt.py`); the
  LLM never emits it (0 occurrences in every examples file). It appears in the
  *original* stage2 prompt only as 5 stray occurrences (4 inside the §5.6
  conditional example, 1 prose), a pre-existing inconsistency. (Checked: each of
  v1/v2/v3/direct carries exactly those same 5 — nothing crept in during the
  builds; the §2 predicate-inventory signature is intact, 55 heads, in all of
  them.)

Assembled minimal system prompt ≈ 10 KB + the pure examples (32 KB) ≈ 42 KB.

Caveat: with no case guidance, this leans entirely on the examples; whether the
signature + 60 examples is enough for correct subtle encodings (quantifier scope,
defeasible rules, world/tense, measures) is exactly what the experiment measures.
Must be validated by running.
