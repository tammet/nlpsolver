# Command-line reference

Ordinary and advanced options for the three commands. Research, ablation and
legacy controls are on a separate page:
[experimental options](experimental-options.md).

All commands run from the `llmpipe/` directory.

- `solver/solve.py` answers one passage.
- `test.py` runs a test file against one provider.
- `runtests.py` runs a test file against several providers in parallel.

Every single-dash key is also accepted with two dashes.

`-help` prints the option list for `solve.py` and for `test.py`. Both also
accept the bare word `help`. `runtests.py` uses `-h` or `--help`.

An unrecognised key is an error: `solve.py` and `test.py` print their help and
stop, rather than reading the key as input.

## Input

`solve.py` takes the passage as arguments. Several arguments are joined with a
space.

```bash
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
```

An argument that looks like a file name is read as a file. It qualifies when
it is under 50 characters, contains no space, and contains exactly one dot with
at least two characters after it. The file's contents replace the argument. A
name that qualifies but cannot be opened stops the run.

```bash
python3 solver/solve.py passage.txt
```

Text arguments and file arguments can be mixed. Everything not recognised as an
option is treated as input.

## Provider and model

- `-llm NAME` — provider: `gpt`, `claude`, `gemini` or `deepseek`. Without it,
  the default in `solver/llmcall.py` applies.
- `-version VER` — model version string, for example `claude-sonnet-4-6` or
  `gpt-5.1`. It must match the provider.
- `-think` — ask for reasoning mode. The number is optional: `-think N` sets
  an integer budget where the provider takes one, and a bare `-think` selects
  the provider's ordinary reasoning setting. If the next argument is not a
  number it is left for the passage.

```bash
python3 solver/solve.py -llm claude -version claude-sonnet-4-6 "..."
```

## Choosing the retry configuration

`-pipeline NAME` selects which retry stages run after the initial translation
and proof attempt. It also accepts `-pipeline=NAME`. An unknown name is an
error.

| name | stages after the initial attempt |
|---|---|
| `conservative` | the two deterministic fallbacks only |
| `balanced` | the fallbacks, the critic and graph retranslation |
| `high-recall` | balanced plus graph bridge generation |

`balanced` is the default. A command line with no options resolves to it.

```bash
python3 solver/solve.py -pipeline conservative "..."
python3 solver/solve.py -pipeline high-recall "..."
```

Single stages can be turned on or off. A switch turns its stage on from any
position on the line. A cancel turns its stage off and wins over everything.

- on: `-fallback_norm`, `-fallback_hyp`, `-critic`, `-graphtrans`,
  `-litbridge`, `-graphbridge`
- off: `-nofallback_norm`, `-nofallback_hyp`, `-nofallback` (both),
  `-nocritic`, `-nographtrans`, `-nolitbridge`, `-nographbridge`

`-nographtrans` also cancels `-graphbridge`, because bridge generation searches
the graph theory.

The stages themselves are described in [retries](../architecture/retries.md).
The resolution rounds are in [configuration](configuration.md).

## Output

The output levels form a hierarchy. Each includes the ones above it.

- `-explain` — the answer and the English proof.
- `-logic` — adds the simplified unit texts, the sentence-to-clause map and
  the logic under each proof step.
- `-details` — adds the Stage-1 and Stage-2 JSON and the prover input and
  output.
- `-debug` — adds raw model responses, prover parameters and the full trace.

Each block appears for the stage that answered, under the same headers. A line
such as `--- stage: graphtrans ---` says which stage produced the block that
follows.

Format and summary:

- `-json` — logic as raw JSON instead of `pred(arg,...)` syntax.
- `-jsonlogic` — short for `-logic -json`.
- `-summary` — one block at the end: the answer, the stage that produced it,
  the answer the initial attempt reached on its own, the enabled stages and
  the call counts.
- `-summary-json` — the same block as one JSON line.
- `-gkin FILE` — write the prover input to `FILE`, with the command as a
  comment.
- `-rawresult` — print only the raw prover JSON.
- `-nosolve` — parse to logic and stop before the prover.

```bash
python3 solver/solve.py -explain "..."
python3 solver/solve.py -summary "..."
```

The record fields these options print are described in
[runtime records](runtime-records.md). The proof format is described in
[proof output](proof-output.md).

## Time and call bounds

- `-seconds N` — proof search time for one GK call. The default is 2.
- `-llm-call-timeout N` — deadline in seconds for one logical model call,
  covering provider attempts, retries and the waits between them. It does not
  enclose GK. The default is 240. `0` disables it.
- `-llm-call-limit N` — bound on the logical model calls for one case, across
  all stages, counting local cache hits. `0` means unlimited and is the
  default. Call N+1 is refused before the cache lookup.

## Caches

Model responses are cached in `cache.db`, keyed on provider, version,
parameters and input.

- `-nollmcache` — do not read or write the model cache for this run.
- `-nogeminicache` — do not use Gemini server-side context caching.
- `-cache` — cache GK results as well. Prover caching is off by default.
- `-clearcache` — clear the model, proof and parse caches, then exit.

## Prover input

- `-axioms FILE...` — use these files instead of `axioms_std.js`. Every
  following argument that does not begin with `-` is taken as a file name.
- `-strategy FILE` — a JSON strategy file instead of the default.
- `-printlevel N` — GK search verbosity. The default is 10; 12 shows more.
- `-prover` — print the prover parameters.
- `-nosemnormal` — do not apply antonym folding and canonical word
  substitution.

## Running a test file

`test.py` runs one or more test files against one provider. Any argument that
is not an option is taken as a test file. With no arguments it prints help,
rather than starting a potentially paid full-suite run. If options are given
without a file, the file defaults to `tests/tests_core.py`.

```bash
python3 test.py tests/tests_core.py -llm claude -limit 5
```

Case selection:

- `-limit N` — run at most N cases per file. N is required.
- `-skip N` — skip the first N cases in each file. N is required.
- `-filter PATTERN` — run only cases whose input contains `PATTERN`. The match
  is case-sensitive and is a plain substring test, not a regular expression.

Output volume, one setting at a time; the last one on the line wins:

- `-verbose` / `-v` — print input, expected and received for every case. This
  is the default.
- `-compact` / `-c` — one character per case: `.` for a pass, `F` for a
  failure.
- `-quiet` / `-q` — no per-case output, only the final summary.
- `-failonly` / `-f` — print only the cases that failed. It takes no argument.

Flow and logging:

- `-stopfail` — stop after the first failure.
- `-logfile PATH` — write the log to `PATH` instead of `test_output.txt`.
- `-restart` — start fresh. It takes no argument. Without it the run appends
  to the readable log and consults an adjacent `.resume.jsonl` file. A result
  is reused only when the test source, pipeline source state, case, provider,
  version, solver options, and scoring policy agree. With `-restart`, both
  files are truncated and every selected case runs again.

Answer comparison:

- `-strict` — compare confidence strictly. `Probably true.` and `Likely true.`
  then match each other but not plain `True.`. Without it the qualifier is
  stripped and every certainty level compares equal.
- `-strictprep` — compare prepositions strictly, so `in Estonia` and `Estonia`
  are different answers. Without it a leading spatial preposition on one side
  only is ignored.

The default matcher is intentionally not an exact string comparison. It also
normalizes case, punctuation, articles, coordinated-answer order, confidence
qualifiers, and equivalent length or mass units. A narrowly input-licensed
adjective difference may also be accepted. One-stage translation experiments
enable several additional entity-rendering tolerances. `runtests.py` stores the
complete named policy in every case record and in its summaries.

Model and cache: `-llm NAME`, `-version VER`, `-think` (with an optional
number), `-cache` and `-nollmcache`, all as for `solve.py`.

## Running a batch

`runtests.py` records one test file against one or more providers. With no
arguments it prints help. It writes one JSON per case and provider to

```text
<out>/<set name>[_<tag>]/<provider>/case_NNNN.json
```

The set name comes from the test file: `tests/tests_core.py` gives `core`.

```bash
python3 runtests.py tests/tests_core.py -llms gemini,deepseek -limit 5
```

Selecting the work:

- the test file, `testfile`, is a positional argument. Its default is
  `tests/tests_core.py`.
- `-llms LIST` — comma-separated providers. The default is
  `gpt,claude,gemini,deepseek`.
- `-version VER` — model version, applied to every provider named.
- `-ids LIST` — comma-separated case ids.
- `-filter PATTERN` — keep cases whose input contains `PATTERN`.
- `-limit N` — keep the first N cases after `-ids` and `-filter` have applied.

Where results go:

- `-out ROOT` — the output root directory itself. The default is
  `testresults`. The run creates `<ROOT>/<set name>/` beneath it, so
  `-out runs/june` writes to `runs/june/core/`.
- `-tag TEXT` — append `_TEXT` to the set-name directory, with anything other
  than a letter or digit folded to `_`. `-tag "my run"` gives `core_my_run`.
  Use it to keep a variant beside the ordinary results. `-directanswer`,
  `-s2split` and combined parsing set a tag of their own when none is given.

Resuming:

- without either switch the run skips a case that already has a result file.
- `-redo` — recompute every case.
- `-redo-errors` — recompute only the cases whose stored file records an
  error, including an answer beginning `Error`.
- `-sequential` — run the providers one at a time in this process, instead of
  one worker process per provider.

Before any case runs, `run_manifest.json` identifies the test-file hash, source
state, resolved pipeline options, scoring policy, and provider versions. If an
existing result directory has a different identity, the runner stops and asks
for a new `-tag` or `-out` instead of mixing the records. The top-level
`summary.json` compares all providers currently recorded in that directory;
each provider directory retains its own `summary.json`.

Bounds:

- `-api-timeout N` — wall-clock limit in seconds on the model parse and clause
  conversion phase of one case. It is disarmed before GK and proof processing
  run, so it never cuts those short. A case that exceeds it is recorded as an
  error and the run continues. The default is 120; `0` disables it.
- `-llm-call-timeout N` and `-llm-call-limit N` — as for `solve.py`. They are
  a different bound from `-api-timeout`: one logical model call against the
  whole parse phase.
- `-maxtokens N` — override the output-token limit.
- `-think N` — a numeric budget. Unlike `solve.py` and `test.py`, the runner
  requires the number; a bare `-think` is rejected.
- `-nogeminicache` — as for `solve.py`.

Any key `runtests.py` does not define itself is forwarded to `solve.py`'s
parser, so `-pipeline`, the single stage switches and their cancels work here
too. `runtests.py` rejects a key that `solve.py` also rejects, rather than
reading it as a file name.

```bash
python3 runtests.py tests/tests_core.py -llms gemini -pipeline conservative
```

The representation options are forwarded the same way. They are listed on the
[experimental options](experimental-options.md) page.

## Everything else

Alternative parsing shapes, abstraction presets, event bases, acceptance
policies, proof-shortening overrides and simplification switches are on the
[experimental options](experimental-options.md) page.

## Related documentation

- [Getting started](../getting-started.md)
- [Configuration](configuration.md)
- [Experimental options](experimental-options.md)
- [Pipeline](../architecture/pipeline.md)
- [Runtime records](runtime-records.md)
