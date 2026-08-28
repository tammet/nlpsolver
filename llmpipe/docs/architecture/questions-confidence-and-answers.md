# Questions, confidence and answers

How a question becomes a query, how confidence travels from Stage 1 to the
answer, and how an answer is rendered.

The question clause format itself is defined in
[gk-clauses.md](../encodings/gk-clauses.md). This page describes the
compilation and the answer handling.

## Confidence and uncertainty handling

Natural-language probabilistic hedging (`"John smokes tobacco with probability 0.8"`,
`"Elephants are rarely animals"`, `"It is false that X"`) is carried through the pipeline
as a numeric confidence value on Stage-1 ASUs and propagated into per-clause
`@confidence` annotations that the prover multiplies along resolution chains.  This
section describes every transform applied between Stage-1 and the prover.

### Stage-1 captures probability as `confidence`

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
a positive assertion after `_negate_consequent` applies.  See the "double-
encoding safety net" subsection below.

### Stage-2 optionally reports confidence via `@p`

Stage-2 can carry the confidence forward as a package-level `@p` annotation:

```
["and", PACKAGE, ["@p", "S1", 0.8]]
```

`_process_assertion` uses the `@p` value as the input `confidence` to the clausification
step (`logconvert.py:916`).

### Probability → evidence scale

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

### Double-encoding safety net (case 234)

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

### Per-clause distribution of evidence

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

### Prover threshold

`globals.py:81` pins the prover to `-confidence 0.1 -keepconfidence 0.1`: any answer
whose derived confidence is below 0.1 is filtered out as noise.  Before the three-tier
distribution was introduced this threshold hid legitimate probabilistic answers (e.g.
case 235's 6-clause chain at `0.6^6 ≈ 0.047`); now the chain product equals `e`, well
above 0.1 for typical probability inputs (`p ≥ 0.6` maps to `e ≥ 0.2`).

### Answer rendering with confidence

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

### Skolem-typed answer rendering for "what" queries

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

### Who-query formatting with Skolem-typed answers

`_format_who_answers` classifies each answer value into *types*, *properties*, or
*equalities*.  Before the fix, Skolem constants fell to the *equalities* bucket because
they contain digits (the skolem index).  Now if the Skolem has a known type from
`get_skolem_type` — derived from `isa(T, sk…)` facts during `compute_skolem_types` — the
**type** is promoted to the types list instead, so the who-answer renders as
`"a <type>"` consistently with what-queries.

### Summary — files involved

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

## WH-question handling

The pipeline handles four types of WH-questions through specialized detection and encoding in `logconvert._process_question` (routing) and `lc_questions` (clause generation), with answer formatting in `procproofs`.

## Related documentation

- [Logic compilation](logic-compilation.md)
- [Reasoning and proofs](reasoning-and-proofs.md)
- [Proof output](../reference/proof-output.md)
- [GK clause list](../encodings/gk-clauses.md)
