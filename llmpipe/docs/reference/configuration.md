# Configuration

How options resolve, and which option keys the pipeline reads. The options
themselves are listed in the [command-line reference](command-line.md) and the
[experimental options](experimental-options.md).

## Named configurations

`-pipeline conservative|balanced|high-recall`, also `-pipeline=NAME`. It
selects retry stages only. An unknown name is an error in both command-line entry points.

`balanced` is the default. A command line with no options resolves to it and
records `pipeline_name: balanced`. `globals.PIPELINES[globals.DEFAULT_PIPELINE]`
holds the six stage defaults, so `solve.py` and `runtests.py` cannot differ.

There is one set of stage defaults, not two. Each of the six entries in
`globals.options` is filled from `globals.PIPELINES[globals.DEFAULT_PIPELINE]`
rather than written out again, so the raw option defaults are the `balanced`
vector: `fallback_norm_flag`, `fallback_hyp_flag`, `critic_flag` and
`graphtrans_flag` are `True`, and `litbridge_flag` and `graphbridge_flag` are
`False`. A run with no options therefore uses four retry stages.

Reading a single option default in isolation can still mislead. `critic_flag`
is `True` only because `balanced` is the default configuration; under
`-pipeline conservative` it resolves to `False`. The configuration decides, and
the option default follows it.

## Compatibility

| older form | resolves to |
|---|---|
| `-stack-closed` | `balanced` |
| `-stack` | `high-recall` |
| `-stack-open` | all six stages, literal bridge included |
| `-abstract-max` | all six stages, plus its converter preset |
| `-abstract`, `-abstract-roles` | converter presets; they select no retry stage |

## Resolution order

1. named configurations, presets and flag sets, left to right, a later one
   replacing an earlier one;
2. explicit stage switches, which turn their stage on from any position;
3. cancellations, which win over both from any position.

`pipeline_name` is derived from the final six-stage vector, after all three
rounds. A vector matching no named set records `custom`.

## Call bounds

`-llm-call-timeout N` is a per-call deadline covering provider attempts,
retries and the sleeps between them. It applies to the initial translation and
to every later stage. It does not enclose GK. The default is 240 seconds.
`-llm-call-timeout 0` disables it. An absent option and an explicit zero are
different.

`-llm-call-limit N` bounds the total logical LLM calls for one case, across
every role, counting local cache hits. 0 is unlimited and is the default. Call
N+1 is refused before the cache lookup and before any provider request.

## Settings that are not command-line options

**The default provider and model** are in `solver/llmcall.py`:

```python
use_llm          = "gemini"            # "gpt" | "claude" | "gemini" | "deepseek"
geminiversion    = "gemini-2.5-flash"
claudeversion    = "claude-sonnet-4-6"
deepseekversion  = "deepseek-v4-flash"
```

DeepSeek V4 models (`-v4-flash`, `-v4-pro`) reason by default, which the
pipeline does not ask for and which costs roughly 8x the latency; `llmcall.py`
therefore sends `reasoning_effort="none"` for any `-v4-` version unless
thinking was requested.

Gemini 3 models also think by default and take a `thinkingLevel` enum instead
of a token budget. None of them can turn thinking off. `gemini-3.0` to `3.5`
accept `MINIMAL`; `gemini-3.7-flash` rejects it with 400 and accepts only
`LOW`, `MEDIUM` and `HIGH`. `llmcall._gemini_cheapest_level` picks the floor
for the version, so a non-thinking call sends `LOW` on 3.7 and `MINIMAL` below
it. Gemini 2.5 keeps the older `thinkingBudget: 0` path.

**The gradable property whitelist** is `solver/gradables.txt`, one lowercase
property name per line.

**Prover defaults** (time limit, axioms, strategy) are in `globals.py`.

## The options dict

`english_to_answer(text, options)` takes the same settings as a dict, so a
caller does not have to build a command line.

```python
english_to_answer(text, {"prover_seconds": 5, "nocontext_flag": True})
english_to_answer(text, {"use_llm_cache_flag": False})
english_to_answer(text, {"use_gemini_cache_flag": False})
```

**Mode option keys**, with their defaults: `event_base` (default
`"neodavidson"`; else `davidson`/`flat`/`flatroles`); the abstraction
primitives `entitymerge_flag`, `typeenrich_flag` with `typeenrich_gates`,
`guarddrop_flag`, `bridges_flag`, `dropdefinites_flag`, `localantonyms_flag`,
`existfold_flag`, `noproptypes_flag`, `propclass_flag`, `numtype_flag` and
`compasym_flag`; `prenorm_flag`, `nominalretry_flag`, `negretry_flag`;
`crossstage_retry_flag` (default `True`, but inert unless an abstraction
encoding is active); `combined_flag` with `combined_instr_file`,
`combined_examples_file` and `combined_checklist_file`; `directanswer_flag`
with `directanswer_file`.

**The six stage keys**, each filled from the default configuration:
`fallback_norm_flag`, `fallback_hyp_flag`, `critic_flag` and `graphtrans_flag`
are `True`; `litbridge_flag` and `graphbridge_flag` are `False`.
`solve.STAGE_KEYS` lists them in stage order. A flag set (`-stack`, `-stack-closed`, `-stack-open`) and
`-abstract-max` assign all six; an explicit stage switch sets one to `True`; a
cancel key (`nofallback_norm_flag`, `nofallback_hyp_flag`, `nocritic_flag`,
`nographtrans_flag`, `nolitbridge_flag`, `nographbridge_flag`) is not read by
the pipeline at all. `_parse_cmd_line` resolves it after the whole command line
by forcing its stage key to `False`, so a cancel wins from any position.
`nographtrans_flag` clears `graphbridge_flag` as well, since bridge generation
searches the graph theory.

**Settings that are module constants.** Each is read where the option key used
to be. None has a command-line key or a `globals.options` entry.

- `litbridge_procedure.EXTRAS` — the two code-built literal-bridge channels.
- `litbridge_grader.MODE` — `None`, `"stated"` or `"any"`.
- `graph_procedure.LIFT`, `graph_procedure.EVIDENCE` and
  `graph_procedure.DEFAULT_SOURCES`.
- `globals.ABSTRACTION_ROUTES` — the order the three routes run in.

**Two converter keys the graph theory needs**, both default `False` and
therefore inert everywhere else. `noclassnumbernorm_flag` stops the final
clause list from singularizing the class argument of every `isa` atom.
`noopennamerewrite_flag` stops `lc_rewrites` from canonicalizing the relation
name of an `is rel2` atom (ownership to `have`, located-in to `in`,
preposition canonicalisation) and from turning a perspective verb into a
Davidsonian event. Each of those would connect two open names without a clause
a proof can show.

## Related documentation

- [Command-line reference](command-line.md)
- [Experimental options](experimental-options.md)
- [Pipeline](../architecture/pipeline.md)
- [Encoding reference](../encodings/README.md)
- [Runtime records](runtime-records.md)
