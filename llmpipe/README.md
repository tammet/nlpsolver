llmpipe
=======

`llmpipe` answers questions about an English passage.  An LLM converts the
passage and question into first-order logic.  The GK reasoner checks whether
the proposed answer or its explicit negation follows and can return the
proof.  The pipeline supports quantified rules, uncertain statements,
defaults, exceptions, and contradictions.

GK has its own distribution: the
[gkreasoner repository](https://github.com/tammet/gkreasoner) contains
binaries for all platforms, documentation, and examples.

Installation and quick start
----------------------------

Prerequisites:
- Linux on x86-64 (the bundled `../gk/gk` binary is a static Linux x86-64
  ELF), or macOS on Apple Silicon — download `bin/gk-macos-arm64` from the
  [gkreasoner repository](https://github.com/tammet/gkreasoner) and use it in
  place of `../gk/gk` (the llmpipe pipeline itself is only tested on Linux)
- Python 3.10+ (only the standard library is required; no `pip install`)
- An LLM API key from at least one of: Gemini, OpenAI, Anthropic, or DeepSeek

```bash
git clone https://github.com/tammet/nlpsolver.git
cd nlpsolver

# Store one API key in a plain-text file (pick any one provider):
#   secrets/gemini_secrets.txt    secrets/gpt_secrets.txt
#   secrets/claude_secrets.txt    secrets/deepseek_secrets.txt
echo "YOUR_API_KEY" > secrets/gemini_secrets.txt

# Check the install without making an API request.  Verifies Python,
# imports, the gk binary, a sample proof, and the key file.
python3 smoketest.py

# Run a query.  This command makes an API request.
cd llmpipe
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
# -> True.

# Run a query with a step-by-step English proof:
python3 solver/solve.py -explain "Mary is taller than John. Who is tall?"
# -> Mary.
```

The first call makes an LLM API request.  Later calls with the same input
and settings use the cached response in `llmpipe/cache.db` (SQLite,
auto-created).  Use `-nollmcache` only when a new LLM response is required.

See `../udppipe/README.md` for the optional Stanza/UD-based pipeline (no
LLM, separate venv).

How it works
------------

```
English passage and question
  -> LLM translation
  -> first-order logic
  -> GK proof search
  -> answer and optional proof
```

The default translation uses two LLM stages: the first rewrites the passage
into simplified units, the second converts those units into logic.  `-llm`
accepts `gpt`, `claude`, `gemini`, and `deepseek`, selecting the OpenAI,
Anthropic, Google, and DeepSeek services.

Repository layout
-----------------

```
llmpipe/
├── solver/             Core pipeline modules (solve.py, logconvert.py, llmparse.py, …)
├── prompts/            LLM system prompts for Stage 1 and Stage 2
├── tests/              Test cases ([id, text, expected_answer] triples)
├── mkdata/             Synonym/antonym data builder (standalone, own venv)
├── axioms_std.js       Default background-knowledge axioms loaded by the gk prover
├── ask.py              Direct LLM call tool (uses solver/llmcall.py)
├── test.py             Test runner
├── runtests.py         Batch runner: full test sets × several LLMs in parallel,
│                       one JSON result file per (case, llm)
├── DOCUMENTATION.md    Developer documentation (full pipeline reference)
├── ENCODINGS.md        Stage-1 / Stage-2 / GK clause-list encoding reference
├── PROOF_RENDERING.md  How proofs are rendered as English explanations
└── CLAUDE.md           Guidance for Claude Code agents working in this repo
```

The top-level `smoketest.py` (at the repo root, not inside `llmpipe/`) checks
the install — see *Installation and quick start* above.

Running
-------

```bash
# Run from the llmpipe/ directory
python3 solver/solve.py "TEXT"
```

Output options:

```
-explain    show the answer with an English proof
-logic      -explain plus the simplified text, the clauses derived from
            each sentence, and the logic of each proof step
-details    -logic plus the stage-1/stage-2 JSON and the prover input
            and output
-debug      -details plus raw LLM responses and the full trace
```

Other options:

```
-llm NAME       LLM service: gpt, claude, gemini, or deepseek
-version VER    model version string, e.g. claude-sonnet-4-6
-gkin FILE      save the GK input and command to FILE for a separate GK run
-nosolve        parse to logic only, skip the prover
-seconds N      prover time limit (default 2)
```

Advanced translation and abstraction options are described in
[`ENCODINGS.md`](ENCODINGS.md) and listed by `python3 solver/solve.py -help`.

Test runners:

```bash
python3 test.py                                  # default: tests/tests_core.py
python3 test.py tests/tests_core.py -llm claude
python3 runtests.py tests/tests_core.py -llms claude,gpt   # batch, JSON output
```

`test.py` resumes from `test_output.txt`: rerunning executes only tests not
yet recorded; `-restart` wipes the log.  See `tests/README.md`.

Direct LLM calls without the pipeline:

```bash
python3 ask.py "What is the capital of France?"
python3 ask.py -llm claude -p prompt.txt "input text"
```

Configuration
-------------

Use `-llm NAME` and `-version MODEL` to override the configured service and
model.  Defaults are defined in `solver/llmcall.py`.  API keys are read from
`../secrets/`.

Troubleshooting
---------------

- **Missing API key** — store a one-line key file at
  `../secrets/<provider>_secrets.txt` (the `secrets/` directory is not
  committed).
- **Cached responses** — `solve.py` reuses cached LLM responses from
  `cache.db`.  `-nollmcache` requests a new LLM response for one run;
  `-clearcache` empties the cache.
- **GK reaches its time limit** — the default prover budget is 2 seconds;
  increase it with `-seconds 10`.
- **Wrong answer** — first determine whether the translation or the proof
  search is at fault.  Inspect the translation and GK input with `-details`
  and the proof with `-explain`.  Change the LLM service with `-llm` when
  the translation is wrong; increase `-seconds` when the proof search
  times out.

Documentation
-------------

- [`ENCODINGS.md`](ENCODINGS.md) — the two LLM representations and the GK input.
- [`DOCUMENTATION.md`](DOCUMENTATION.md) — modules, configuration, and extension points.
- [`PROOF_RENDERING.md`](PROOF_RENDERING.md) — answer and proof rendering.
- [`prompts/README.md`](prompts/README.md) — prompt assembly and alternative parsing modes.
- [`tests/README.md`](tests/README.md) — test formats and runners.
- [gkreasoner](https://github.com/tammet/gkreasoner) — GK documentation and examples.
