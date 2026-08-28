# Translation and validation

Model calls, the response cache, the two parsing stages, the sanity checks
and the corrective retries.

[Architecture: translation](../architecture/translation.md) describes what the
stages do. This page describes the modules that do it.

## Modules

### llmcall.py

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
instant 429.  When `globals.options["use_gemini_cache_flag"]` is `True` (the default; disable with `-nogeminicache`;
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
deepseekversion  = "deepseek-v4-flash" # V4 models get reasoning_effort="none"; "deepseek-reasoner" for thinking
temperature      = 0
default_max_tokens = 8000
max_retries      = 3
```

API keys are read from plain-text files in `../secrets/` (relative to `llmpipe/`):
`gpt_secrets.txt`, `claude_secrets.txt`, `gemini_secrets.txt`, `deepseek_secrets.txt`.
The directory path is set once via `_secrets_dir` in `llmcall.py`.

### llmparse.py

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
  corrective-retry loop via `_maybe_sanity_retry` (see [translation](../architecture/translation.md) and [the source map](source-map.md) for details).
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
- `prenorm_enabled` — rewrite the input English first via `normalize_text` ([translation](../architecture/translation.md)).
- `combined_enabled` — make ONE LLM call (English → Stage-2 logic) with the explicitly
  named combined prompt files and return `(None, s2_json, stats)`; there is no Stage-1
  JSON in this mode ([translation](../architecture/translation.md)).
- `canon_entities_enabled` (set by `-entitymerge`) — aggressive Stage-1 entity-id
  canonicalization (`canonicalize_entity_ids`) and Stage-2 Wikipedia-URL folding
  (`canonicalize_entity_urls`) ([abstraction](../architecture/abstraction.md)).
- `crossstage_guard_retry` ∧ `canon_entities_enabled` — after Stage 2, re-run BOTH
  stages once with a corrective hint when a rule antecedent names a class/property/
  relation nothing can satisfy ([abstraction](../architecture/abstraction.md)).

### stage_sanity.py

**Role:** Structural sanity checks for Stage-1 ASU JSON and Stage-2 logic JSON, used by
`llmparse._maybe_sanity_retry` to detect LLM output errors that the Stage prompts explicitly
forbid (or that the downstream pipeline cannot handle) and trigger a corrective re-call of
the same LLM.  See [translation](../architecture/translation.md) for the retry-loop semantics and motivation.

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

Each check is named by its function and by the issue kind it reports.

**`_check_stage2_free_variables`** — reports `free_variable`.

Triggers on any atom-argument string that matches a binder name (`forall`/`exists`/`ask`) elsewhere in the formula but is outside the binder's scope.

Example: Case 259 — donkey anaphora

**`_check_stage2_misplaced_meta_tense`** — reports `state_time_in_body`.

Triggers on a `["state time", W, TENSE]` atom inside a `holds`/`question`/`ask` body.  Tense metadata belongs at package level, not as a body literal.

Example: Case 37

**`_check_stage2_dropped_specific_noun`** — reports `dropped_specific_noun`.

Triggers on query `exists VAR, (and ... isa(CAT, VAR) ...)` where Stage-1 has a unique generic entity with `category=CAT` and `id != CAT` — the query lost the specific noun.

Example: Case 136

**`_check_stage2_arities`** — reports `wrong_arity`.

Triggers on atom whose arity disagrees with the declared Stage-2 signature (whitelist of 27 predicates: `isa/2`, `has property/2`, `has type/2`, `has actor/2`, `has part/2`, `is rel2/3`, `has degree property/4`, `has degree rel2/5`, `typical/1`, etc.).

Example: Scattered

**`_check_stage2_event_shapes`** — reports `event_missing_activity_isa` or `event_missing_role`.

Triggers on event variable E used as first arg of `has_type(E, VERB)` must have `isa("activity", E)` AND at least one thematic-role atom (any of `has_actor`, `has_target`, `has_recipient`, `has_source`, `has_destination`, `has_location`, `has_instrument`, `has_manner`, `has_direction`, `has_time`, `has_beneficiary`, `has_accompaniment`, `has_path`, `has_result`, `has_topic`, `has_cause`, `typical`) in the same `and` conjunction.  Either missing item is its own issue.

**`_check_stage2_inner_content_event_time`** — reports `inner_content_event_missing_time`.

Triggers on 5-gate criterion: var V appears as 2nd arg of `["has content", E1, V]` AND has a `has_type` atom AND has no `has_time` atom AND has no modal classifier (capability/typical/necessity/obligation/volition/intention/expectation/speech_act) AND the Stage-1 unit containing this `@id` has `time` set to past/present/future.  Catches gemini's intermittent omission of `has_time` on inner content events of speech-act reifications, which would prevent the `axioms_std.js` [the source map](source-map.md) factive bridge from unifying the derived `actuality(E2)` with the question's tensed event.  Skips modal-classified and tenseless-unit cases.

Example: Case 159 — gemini

**`_check_stage2_missing_question`** — reports `missing_question`.

Triggers on a Stage-1 unit is a query (either `unit.type == "query"` or its parent package's `raw` text contains `?`) but the matching `@id` in Stage-2 has no `question`/`ask` wrapper anywhere in its body — covers both whole-package truncations and `holds`-where-`question`-was-expected.

Example: LLM truncation on multi-sentence inputs

**`_check_stage2_entity_id_typos`** — reports `entity_id_typo`.

Triggers on an entity ID `XYZ N` whose first word has a stray prefix that is itself a prefix of another ID's first word in the same problem (max 4 extra chars).  Catches gemini's "fr fridge 3" vs "fridge 3" pattern where one mention picks up a stray article/preposition fragment.

Example: Case 152

**`_check_stage2_possessive_without_ownership`** — reports `possessive_without_ownership`.

Triggers on a possessive cue (determiner `their`/`his`/`her`/`its`/`our`/`your`/`my` + noun, or genitive `'s` + noun) appears in the Stage-1 unit text, a `"Whose X?"` wh-question (`["ask", VAR, …]` with VAR in an ownership atom) solves for the owner, yet the assertion side carries **no** ownership atom at all (`have` / `has part` / ownership `is rel2` / relational genitive `is rel2 "… of"`).  The possessive was dropped, so the owner is never stated.  Retry asks for an explicit `have(OWNER, THING)`.  Tightly conditional — applies only on that exact shape.

Example: Case 154

**`_check_stage2_vacuous_tautology_assertion`** — reports `vacuous_tautology_assertion`.

Triggers on an assertion-side (non-`question`/`ask`) `["implies", A, B]` whose antecedent `A` is structurally identical to `B` — a vacuous "if P then P" — AND a `question`/`ask` package is also present.  Signals a conditional QUESTION mis-segmented (on its comma) into an asserted tautology plus a bare-consequent question.  Retry asks for a single `question(implies(A,B))`.  Never descends into `question`/`ask`, so the correct `question(implies(P,P))` is not flagged.

Example: Case 384 — gpt

**`_check_stage2_measure_vs_degree_rel2`** — reports `measure_degree_rel2_conflict`.

Triggers on the same property string is encoded BOTH as `$measure_of(P,…)` and `has_degree_rel2(P,…)` in one output — the equality/comparison split across two disconnected representations (no axiom bridges `has_degree_rel2` to `$measure_of`).  Retry asks to put the comparison on the measure scale (`=`/`>`/`<` on `$measure_of`).  Not measurability-gated (the LLM already chose `$measure_of`).

Example: Case 555 — claude

**`_check_stage2_comparative_as_degree_property`** — reports `comparative_as_degree_property` or
`comparative_as_degree_property_nonmeasurable`.

Triggers on a comparative cue in the Stage-1 text (`"as P as"` / `"P-er than"` / `"more\|less P than"`) where `P` is in a UNARY `has_degree_property` with no two-argument encoding — the binary comparison was lost.  Splits on `_MEASURABLE_ADJS`: a MEASURABLE dimension (tall/heavy/long/…) → retry to `$measure_of` `=`/`>`/`<` (case 555 gpt); a gradable but NON-measurable property (interesting/…) → retry to the binary `has_degree_rel2(P,A,B,…)` (case 559 gpt, refuted by the `has_degree_rel2` asymmetry axiom; asks to resolve an elliptical question's implicit referent).

Example: Cases 555 / 559 — gpt

**`_check_stage2_multiword_property`** — reports `multiword_property`.

Triggers on a `has property`/`has degree property` whose first argument (the property name) is a phrase of MORE THAN two words — e.g. `"filled with water"`, `"afraid of mice"` — collapsing a relation + its argument(s) into one opaque adjective.  Retry says to conceptually split it into meaning components and represent the input with more detail (embedded noun as its own entity, relation as the right predicate).  Two-word compounds ("dark blue") are left alone.

Example: Cases 673 / 1620 — gpt

**`_check_stage2_either_or_not_xor`** — reports `either_or_not_xor`.

Triggers on the source text uses "either" (detected in `s1_json` raw/unit text) AND the Stage-2 disjunction is NOT a bare strict `xor` — i.e. an inclusive `["or", A, B]` (loses exclusivity) or any `["or"\|"xor"]` nested under `["normally", …]` (a defeasible xor whose "not both" clause self-blocks).  Retry asks to encode "either A or B" as strict `["xor", A, B]` — never inclusive `or`, never wrapped in `normally`.  A bare top-level `xor` (claude/gpt) does not apply.

Example: Case 571 — gemini (inclusive or) / deepseek (`normally(xor)`)


**Registered Stage-1 checks:**

Each check is named by its function and by the issue kind it reports.

**`_check_stage1_missing_wh_placeholder`** — reports `missing_wh_placeholder`.

Triggers on a query unit whose text or parent raw begins with a wh-question word but has no entity flagged `wh_placeholder=true`.  The retry prompt asks the LLM to add the placeholder and apply the question-word transformation.

Example: Wh-questions in any LLM

**`_check_stage1_dropped_question`** — reports `dropped_question`.

Triggers on the input has a "?"-terminated sentence, no block's `raw` text carries a "?" and no unit is typed `query`: Stage 1 dropped the question outright.  FOLIO writes its conclusion as a declarative ending in "?" and deepseek read it as one more assertion on 19 of 203 cases (2026-08-19); with the sentence gone, `_check_stage2_missing_question` and the downstream `no question given` retry have nothing to key on.  `check_stage1` takes the input text for this check.  A question Stage 1 kept but mistyped still shows in a raw text and is left to the Stage-2 check.

Example: deepseek FOLIO 14/15/20/… (19 cases); `tools/test_dropped_question.py`

**`_check_stage1_entity_used_as_location`** — reports `entity_used_as_location`.

Triggers on a unit whose `location` field is a concrete-entity ID declared in the same unit's entities list.  The unit-level `location` field is the SCENE / place of the situation, NEVER a concrete object that participates in a spatial relation as the secondary argument.  The retry prompt explains the distinction and asks the LLM to either move the spatial info into the action's roles (with `location_prep`) or omit `location` entirely.

Example: Case 148 — gemini and gpt put `location: "table 3"` / `"floor 4"` at unit level, polluting `$ctxt` position 3

**`_check_stage1_pronoun_as_class`** — reports `pronoun_as_class`.

Triggers on a **query** unit declares an entity whose id is an indefinite person-pronoun (`someone`/`somebody`/`anyone`/`anybody`/`everyone`/`everybody`, trailing number stripped).  Stage-2 then emits a phantom `isa("someone", X)` class that nothing populates → the question is unprovable.  The retry asks for the common noun `person`.  **conditional to query units only** — in a rule/assertion ("If someone is X then Y") the pronoun is a universal bound variable and a retry damages the parse (regressed 1390/1608 before the gate).

Example: Case 626 — gpt

**`_check_stage1_spurious_wh_placeholder`** — reports `spurious_wh_placeholder`.

Triggers on a **query** unit carries a `wh_placeholder` entity but its text (a) leads with a yes/no auxiliary (`did`/`does`/`is`/`are`/`was`/`were`/`has`/`have`/`can`/`will`/…) AND (b) contains **no** wh-word anywhere.  The yes/no question was mis-flagged as wh, so Stage-2 emits an `ask X` (askvars) query that needs a determinate witness an indefinite/disjunctive subject cannot give.  The retry asks for a plain yes/no encoding (drop the placeholder, no "Which …" rewrite).  The two-part gate leaves genuine wh-questions phrased with a leading auxiliary alone, e.g. "Is Ellen afraid of whom?" (1343).

Example: Case 626 — claude

**`_check_stage1_split_conditional`** — reports `split_conditional_sentence`.

Triggers on a package whose `raw`, stripped, ENDS WITH a comma and whose first word is a subordinating conjunction (`if`/`when`/`while`/`unless`/…), with a FOLLOWING package holding the main clause — a single conditional/adverbial sentence wrongly split at its internal comma.  Stage-2 then encodes the fragment as a (vacuous) rule plus a separate query, so the whole conditional is never asked.  Retry asks to keep the comma-joined clauses in ONE package / one conditional query unit, which then lets Stage-2 emit `question(implies(…))` directly.

Example: Case 384 — gpt


**Conventions:**

- Checks are pure functions over the parsed JSON; they do not mutate or consult other
  pipeline state.
- When a check also has a downstream post-processing rescue (e.g., `strip_tense_has_time` for
  misplaced meta-tense, `inject_query_specific_noun_isas` for dropped specific nouns), the
  sanity check takes priority: a successful retry produces cleaner Stage-2 output, and the
  post-processor silently no-ops on the corrected formula.
- Checks that overlap with benign LLM-prompt examples are deliberately omitted.  For
  instance, `["has time", E, "past", "in"]` is labelled WRONG in the Stage-2 instructions
  but appears in the examples file; LLMs emit it consistently, so no check reports an issue —
  `strip_tense_has_time` handles it cheaply.

---

## Related documentation

- [Translation](../architecture/translation.md)
- [Prompt map](prompt-map.md)
- [Encoding reference](../encodings/README.md)
- [Source map](source-map.md)
