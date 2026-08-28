# Orchestration

Entry points, option resolution, stage scheduling, stopping, the per-call
deadline and call accounting.

`solve.py` owns the run. It resolves the command line into the option dict,
fills the six stage keys from the named configuration, calls the initial attempt,
and then walks `PIPELINE_ORDER` while the question is unresolved.

## Stage scheduling

`solve.PIPELINE_ORDER` lists the initial attempt and the six retry stages in the
order they run. `solve.STAGE_KEYS` is derived from it. A stage runs when its
key is on and the question is still unresolved. The first definite answer stops
the rest, and an earlier definite answer is never replaced.

Each stage's outcome is written to its own row in the run record, whether it
ran, was skipped, failed or timed out.

## The per-call deadline

`llmcall.Deadline` bounds one logical model call: every provider attempt, the
retries and the waits between them. It is cooperative. The deadline is checked
before each attempt and passed to the socket, so no thread is left running
after the bound is reached. It never encloses GK. A cached response never times
out.

`-llm-call-timeout N` sets it, and the default is 240 seconds. `runtests.py`
also has `-api-timeout`, which covers only the parse and conversion phase.

## Call accounting

One vocabulary is used globally and per stage:

- `attempted = allowed + refused`;
- `allowed = cached + live`;
- a live call is counted once, however many provider attempts it makes;
- `provider_requests` counts outbound requests, including internal retries.

`-llm-call-limit N` bounds `allowed` for one case across every stage. Call N+1
is refused before the cache lookup and before any provider request, and the
refused stage is left unresolved.

## Model identity

One run uses one provider and one version for every call. `llmcall.locked_model`
pins them for the case. A call naming anything else raises `ModelMismatch`
immediately, including when a response for that other model sits in the cache.
The check runs before the cache lookup.

## GK attribution

`prover.stage()` marks the stage that owns the current GK call, and
`prover.collector()` gathers the calls for one case. The run-scoped collector
is what `gk_calls` reports, so a nested stage cannot overwrite the count of the
stage that contains it.

## Modules

### solve.py

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
-nogeminicache     Disable Gemini server-side context caching (on by default; see [the source map](source-map.md))
-seconds N         Prover time limit (default 2)
-simple            No context, no exceptions, simple properties
-think [N]         Enable reasoning/thinking mode (optional token budget)
-event MODE        Event-encoding base: neodavidson|davidson|flat|flatroles ([abstraction](../architecture/abstraction.md))
-abstract / -abstract-roles / -abstract-max   Abstraction presets ([abstraction](../architecture/abstraction.md)); expand
                   into -event + the abstraction primitives (+ -prenorm for -max)
-entitymerge -typeenrich[=GATES] -guarddrop -bridges -dropdefinites -localantonyms
                   -existfold   Additive abstraction primitives ([abstraction](../architecture/abstraction.md))
-prenorm           Pre-Stage-1 LLM wording normalisation ([translation](../architecture/translation.md))
-nocrossstage      Disable the cross-stage guard retry ([abstraction](../architecture/abstraction.md))
-combined-instr F  Combined single-stage parsing: ONE LLM call English -> logic ([translation](../architecture/translation.md));
                   optional -combined-examples F / -combined-checklist F
-directanswer F    Answer with ONE LLM call using prompt file F; no logic, no prover ([translation](../architecture/translation.md))
```

Before clausification, `english_to_answer` ASCII-folds both parses
(`_ascii_fold_logic`): every string in the Stage-1/Stage-2 JSON is transliterated to
plain ASCII (NFKD decompose, drop combining marks — "Náutico" → "Nautico").  The gk
subprocess output is decoded as ASCII, so a non-ASCII constant would otherwise crash
proof reading (answer `None`).  This runs on every path, including the default one.

### globals.py

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
prover_params     = ["-taxonomy", "-confidence", "0.1", "-keepconfidence", "0.1"]
```

**`set_global_options(newoptions)`** — merge a dict into `options`; called by `solve.py` with
the parsed CLI flags.

### cache.py

**Role:** SQLite-backed cache for LLM responses and prover results.

Three separate tables in `cache.db`:
- `llm_cache` — keyed on `(provider, version, temperature, seed, max_tokens, sysprompt, input)`
- `proof_cache` — keyed on the prover parameter string
- `parse_cache` — for parsed results (future use)

Key functions: `get_llm_from_cache`, `add_llm_to_cache`, `get_proof_from_cache`,
`add_proof_to_cache`, `clear_all_caches`.  LLM caching is controlled by
`globals.options["use_llm_cache_flag"]`.  Proof caching is off by default and enabled with
`-cache`.

### pretty.py

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

### utils.py

**Role:** Shared utility functions used across the pipeline.

- `debug_print(label, data=None, flag=None)` — prints a labelled debug message when `flag` is
  truthy.  If `flag` is `None` (default), falls back to `globals.options["debug_print_flag"]`.
  Pass an explicit boolean to use a different flag (e.g. `llmcall.py` passes its module-level
  `debug` and `calldebug` variables).  Formats `data` intelligently: lists are printed one
  element per line (nested lists indented), dicts show key/value pairs.

- `clause_list_to_json(logic) -> str` — converts the Python GK clause list to a JSON string
  suitable for passing to the `gk` binary.  Uses `json.dumps` with compact separators.

## Related documentation

- [Pipeline](../architecture/pipeline.md)
- [Configuration](../reference/configuration.md)
- [Runtime records](../reference/runtime-records.md)
- [Source map](source-map.md)
