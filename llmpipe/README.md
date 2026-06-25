llmpipe
=======

`llmpipe` is a natural-language question-answering pipeline built on LLMs and a first-order
theorem prover.  It converts English text into predicate logic using a two-stage LLM parser,
then passes the logic to the [`gk`](../gk/) prover to produce answers.

Installation
------------

**Prerequisites:**
- Linux on x86-64 (the bundled `../gk/gk` binary is a static Linux x86-64 ELF), or macOS on
  Apple Silicon — unzip `../gk/gk-macos-ARM64.zip` and use the extracted `gk` in its place
  (the llmpipe pipeline itself is only tested on Linux)
- Python 3.10+ (only the standard library is required for llmpipe itself; no `pip install`)
- An LLM API key from at least one of: Gemini, OpenAI, Anthropic, or DeepSeek

**Steps:**
```bash
git clone https://github.com/tammet/nlpsolver.git
cd nlpsolver

# Drop your API key into one of these plain-text files (pick any one provider):
#   secrets/gemini_secrets.txt    secrets/gpt_secrets.txt
#   secrets/claude_secrets.txt    secrets/deepseek_secrets.txt
echo "YOUR_API_KEY" > secrets/gemini_secrets.txt

# Smoke-test the install without spending any API credits.  Verifies Python,
# imports, the gk binary, a sample proof, the key file, and (optionally) the
# udppipe stanza venv.  Run from the repo root:
python3 smoketest.py

# First real query (this one DOES call the LLM and use a credit):
cd llmpipe
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
# → True.
```

LLM responses are cached in `llmpipe/cache.db` (SQLite, auto-created); rerunning the same
query is free.  See `../udppipe/README.md` for the optional Stanza/UD-based pipeline (no
LLM, separate venv).

Quick start
-----------

```bash
# Run from the llmpipe/ directory
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
# → True.

python3 solver/solve.py "Mary is taller than John. Who is tall?" -explain
# → Mary. (with step-by-step proof)
```

How it works
------------

```
English text
  → Stage-1 LLM parse   (English → Atomic Semantic Units)
  → Stage-2 LLM parse   (ASUs → first-order logic JSON)
  → logconvert          (FOL JSON → GK clause list, CNF, Skolemisation)
  → gk prover           (theorem prover binary)
  → procproofs          (answer extraction + proof explanation)
  → Answer string
```

The pipeline supports GPT, Claude, Gemini, and DeepSeek as the parsing LLM.  LLM responses are
cached in `cache.db` (SQLite) so repeated queries are free.

Repository layout
-----------------

```
llmpipe/
├── solver/             Core pipeline modules (solve.py, logconvert.py, llmparse.py, …)
├── prompts/            LLM system prompts for Stage 1 and Stage 2
├── tests/              Test cases ([text, expected_answer] pairs)
├── mkdata/             Synonym/antonym data builder (standalone, own venv)
├── axioms_std.js       Default background-knowledge axioms loaded by the gk prover
├── ask.py              Direct LLM call tool (uses solver/llmcall.py)
├── test.py             Test runner
├── DOCUMENTATION.md    Developer documentation (full pipeline reference)
├── ENCODINGS.md        Stage-1 / Stage-2 / GK clause-list encoding reference
├── DEBUGGING.md        Debugging workflow + failure taxonomy
├── PROOF_RENDERING.md  How proofs are rendered as English explanations
└── CLAUDE.md           Guidance for Claude Code agents working in this repo
```

The top-level `smoketest.py` (at the repo root, not inside `llmpipe/`) sanity-checks
the install — see *Installation* above.

Running
-------

```bash
# Basic usage
python3 solver/solve.py "TEXT"

# Output level (hierarchy: each includes previous levels)
-explain                          Show English proof
-logic                            + simplified text, clauses, logic in proofs
-details                          + stage-1/2 JSON, prover input/output
-debug                            + raw LLM responses, full trace

# Useful flags
-llm claude|gpt|gemini|deepseek   LLM provider (default set in llmcall.py)
-version MODEL                    Model version string
-json                             Show logic as raw JSON instead of traditional syntax
-gkin FILE                        Save GK prover input to FILE
-nosolve                          Parse to logic only, skip prover
-nollmcache                       Disable LLM cache for this run
-seconds N                        Prover time limit (default 2)

# Logic-conversion / representation flags (composable; see ENCODINGS.md §6, -help):
-event MODE                       Event-encoding base: neodavidson (default) |
                                  davidson | flat | flatroles
-abstract -abstract-roles -abstract-max   Abstraction presets (FOLIO ladder; expand
                                  into the primitives below + -prenorm for -max)
-entitymerge -typeenrich -guarddrop -bridges -dropdefinites -localantonyms   Buckets
-existfold                        Existential-attribute collapse

# Run tests (default file: tests/tests_core.py; see -help for full options)
python3 test.py
python3 test.py tests/tests_core.py -llm claude
python3 test.py -help               # all flags: -limit, -filter, -restart, ...

# test.py auto-resumes from test_output.txt: re-running re-uses previous
# results and only executes tests not yet recorded. Use -restart to wipe
# the log and start fresh.


# Call an LLM directly (no pipeline)
python3 ask.py "What is the capital of France?"
python3 ask.py -llm claude -p prompt.txt "input text"

```

Configuration
-------------

**LLM provider and model:** edit `solver/llmcall.py`:
```python
use_llm       = "gemini"            # "gpt" | "claude" | "gemini" | "deepseek"
claudeversion = "claude-sonnet-4-6"
geminiversion = "gemini-2.5-flash"
gptversion    = "gpt-5.1"
```

**API keys:** plain-text files in `../secrets/` (`gpt_secrets.txt`, `claude_secrets.txt`, `gemini_secrets.txt`,
`deepseek_secrets.txt`).


Troubleshooting
---------------

- **"No API key file"** — drop a one-line file with your key at `../secrets/<provider>_secrets.txt`
  (the `secrets/` directory is `.gitignore`d).
- **Same query much slower the second time?** — `solver/solve.py` always uses `cache.db` by
  default; if you changed the prompts or want a fresh call, run `python3 solver/solve.py -clearcache`
  or delete `cache.db`.  Do NOT pass `-nollmcache` casually — it wastes credits and bypasses the
  cache only for that one call.
- **`gk` says "answer not found" but the question looks easy** — the prover's default budget is
  2 seconds; try `-seconds 10`.  For tense/world mismatches, try `-nocontext`.  For full
  debug, run with `-debug` (or `-explain` for a step-by-step English proof).
- **Wrong answer** — try a different LLM with `-llm claude|gpt|deepseek`; LLMs disagree on
  edge cases.  Use `-debug` to see Stage-1/2 JSON and the GK clause list.

Documentation
-------------

See  [`ENCODINGS.md`](ENCODINGS.md) for the three data representations (Stage-1, Stage-2, GK input) with examples.

See  [`DOCUMENTATION.md`](DOCUMENTATION.md) for a full developer guide covering:
- Every source file with its public API
- Key algorithms: FOL→CNF clausification, defeasible reasoning, context injection,
  gradable property normalisation, wh-question encoding
- How to extend the pipeline (new predicates, new LLM providers, improved prompts)

See [`PROOF_RENDERING.md`](PROOF_RENDERING.md) for how proofs are rendered as English explanations.

See [`DEBUGGING.md`](DEBUGGING.md) for the debugging workflow, failure taxonomy, and world/tense system.
