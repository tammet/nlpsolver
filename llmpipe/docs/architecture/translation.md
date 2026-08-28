# Translation

The two model calls that turn English into logic, the prompts they use, the
checks on their output, and the alternative parsing shapes.

Stage 1 turns English into atomic semantic units. Stage 2 turns those units
into extended first-order logic in JSON, including defeasible formulas and
probabilistic confidence annotations. Each stage makes one model call, with a
system prompt built from an instruction file, a checklist and examples.

The [encoding reference](../encodings/README.md) defines the exact
formats: [stage-1.md](../encodings/stage-1.md) and
[stage-2.md](../encodings/stage-2.md). This page does not repeat
those grammars.

Two later stages can make further model calls. The critic audits the front
door's translation, and graph retranslation parses the case a second time. Both
are described in [retries](retries.md).

## Prompts

Stage 1 reads `stage1_instructions_full.txt`, `stage1_checklist_full.txt` and
`stage1_examples.txt`. Stage 2 reads the matching `stage2_*` files.
`llmparse.py` loads them and assembles the system prompt. The
[prompt map](../code/prompt-map.md) lists every prompt file and its loader.

The instruction file states the format and the rules. The checklist is a
procedural list the model works through. The examples file carries worked
cases. A run can replace the pair of stages with a single combined prompt; see
Alternative parsing shapes below.

## Entity identifiers

Stage 1 names each entity. `llmparse.py` normalizes those identifiers before
Stage 2 sees them, so that one thing keeps one name across units. Stage 2 then
uses the normalized names as logical constants.

## Checks and corrective retries

`stage_sanity.py` checks every Stage-1 and Stage-2 parse. A failed check can
produce one corrective retry: the same model receives the original prompt, its
own flawed output and a description of what went wrong.


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
Stage 2 to make the reading consistent; see [abstraction](abstraction.md).

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

The list of checks lives in `stage_sanity.py` ([the source map](../code/source-map.md)).  Adding a new check = one new
`_check_stage<N>_*` function plus a call inside `check_stage<N>`; no change to `llmparse.py`
is needed.

**`nominalretry_flag`: dropped predicate-nominal retry (experimental).**
`_check_stage2_dropped_predicate_nominal` (applies only when `globals.options["nominalretry_flag"]`,
set by `-abstract-max`, with no flag of its own) addresses a Stage-2 failure where a
Stage-1 copular predication "ENT is a NOUN" loses its type.  `_extract_s1_copular_nominals`
pulls `(entity, noun)` pairs from concrete fact units (`situation`/`real`), handling a subject
with an `of …`/`'s …` postmodifier (the definite-description case) and multi-word nouns, and
conservatively skipping negated / modal / disjunctive / quantified sentences.  The check applies
when the `NOUN` appears elsewhere in the Stage-2 logic but is never asserted of `ENT` (no
`isa/has property(NOUN, ENT)`), and emits a `dropped_predicate_nominal` issue that drives the
corrective retry to add `isa(NOUN, ENT)`.  It covers two LLM failure modes: substituting the
entity **category** for the predicate nominal (`isa(animal,Rock)+have(Peter,Rock)` for "Rock is
Peter's pet", case 126), and binding the property to a **dangling existential**
(`exists Z. isa(text sequence, Z)` for "The output of MT is a text sequence", case 91).
Validated live: 91, 126 → gold, 0 regressions on the 14-case firing surface; cost ~14 live
Stage-2 retries per full FOLIO run.  Unlike the encoding primitives, this is a parse-time retry,
not resolved by `EncodingConfig`, so it can make live model calls.

---

## Alternative parsing shapes

Each of these replaces the default two-stage parse. The options are
listed on the
[experimental options](../reference/experimental-options.md) page.

### `-prenorm` — pre-Stage-1 wording normalisation

`llmparse.normalize_text` makes one extra LLM call with
`prompts/prenorm_full.txt` to rewrite the input English so the same entity /
property / relation is always worded identically, then feeds the rewritten text to
Stage 1.  Returns the original text on any error.  Composable with every other mode;
part of the `-abstract-max` FOLIO configuration.

### Combined single-stage parsing (`-combined-instr` etc.)

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

### Direct answer (`-directanswer FILE`)

`solver/directanswer.py` answers the question with ONE LLM call using FILE as the
system prompt — no logic, no prover, test-set agnostic.  The reply is normalised by
`_extract_verdict`: if it contains a True/False/Unknown/Uncertain token, the LAST one
wins (reasoning models often write a chain of thought ending in the verdict),
normalised to `"True." / "False." / "Unknown."`; otherwise the stripped reply is the
answer (phrase-style prompts).  `collect` gets `answer` and a `directanswer` metadata
field.  Used for the FOLIO direct-answer reference runs
(`prompts/folio_directanswer_instructions[_noworld].txt`).

### Split Stage 2 (`-s2split`)

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
repair for these is applied automatically under `-s2split` (applies only when `s2split_flag`); the
default joint and abstraction paths are untouched.  It enables:
- an off-inventory rename and form-normalization pass in `logconvert`:
  predicate renames (`has` → `have`, `has rel2` → `is rel2`, `has agent` →
  `has actor`), comparative-phrase relation names reduced to the base adjective
  (`has degree rel2("higher than", …)` → `"high"`, applies only when the gradables
  whitelist so ordinary relation names are untouched), and adjective-as-dimension
  `$measure_of` slots mapped to the dimension noun (`$measure_of("tall", …)` →
  `"height"`);
- dynamic shape bridges (`lc_post_inject.inject_s2split_shape_bridges`, confidence
  0.99, each applies only when both shapes being present): `has_destination` → `has_location`
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
  produce — so the result-state mutexes can apply to the question's present-tense
  reading.

On the curated 100-subset (joint two-stage baseline = 100/100 for all four LLMs by
construction), `-s2split` scores gpt 100/100, claude 100/100, deepseek 97/100 — the
three residual deepseek cases (541, 663, 1335: generic-question subject construction,
category-instead-of-noun typing, RELCLASS divergence) are diagnosed but deliberately
unfixed pending proof-level analysis.  (The repair is essential to this: without it the
isolated per-sentence parses diverge and gpt drops to ~93/100.)

---

## Related documentation

- [Encoding reference](../encodings/README.md)
- [Prompt map](../code/prompt-map.md)
- [Translation and validation code](../code/translation-and-validation.md)
- [Logic compilation](logic-compilation.md)
- [Retries](retries.md)
- [Experimental options](../reference/experimental-options.md)
