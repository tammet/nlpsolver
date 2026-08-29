llmpipe
=======

`llmpipe` answers questions about English passages by translating the text into
logic and asking the [GK reasoner](https://github.com/tammet/gkreasoner) to find
a proof. The language model performs the semantic translation; deterministic
code checks and compiles it; GK derives the answer or its explicit negation.
When neither can be proved, the system returns `Unknown.`.

The target language is extended first-order logic with quantifiers, defeasible
rules, numeric confidence, exceptions, and contradiction-tolerant reasoning.
The system can answer true/false questions and questions whose answer is an
entity, and it can render a prover-produced proof in English.

Quick start
-----------

Requirements:

- Python 3.10 or later; the runtime uses only the standard library
- Linux on x86-64 with the bundled GK binary, or macOS on Apple Silicon with
  the ARM64 binary from the [gkreasoner repository](https://github.com/tammet/gkreasoner)
  substituted for it; the pipeline itself is currently tested on Linux
- an API key for Gemini, OpenAI, Anthropic, or DeepSeek

```bash
git clone https://github.com/tammet/nlpsolver.git
cd nlpsolver

# Choose one provider. Secret files are ignored by Git.
echo "YOUR_API_KEY" > secrets/gemini_secrets.txt

# Check Python, imports, GK, a sample proof, and API-key presence.
# This does not make an LLM request.
python3 smoketest.py

cd llmpipe

# This command makes an LLM request.
python3 solver/solve.py -llm gemini \
  "Elephants are animals. John is an elephant. Is John an animal?"
# -> True.

# Ask for the proof in English.
python3 solver/solve.py -llm gemini -explain \
  "Elephants are animals. John is an elephant. Is John an animal?"
```

LLM responses are cached in `cache.db`, so an identical later request normally
does not call the provider again. Use `-nollmcache` when a fresh response is
required.

See [Getting started](docs/getting-started.md) for model selection, output
levels, test commands, and further installation details.

How it works
------------

```text
English passage and question
    -> Stage 1: identify source-linked semantic units
    -> Stage 2: translate the units into extended first-order logic
    -> validate, normalize, extend, and compile the logic
    -> GK proof search
    -> answer and optional English proof
```

Stage 1 and Stage 2 use the selected language model. Compilation, proof search,
answer selection, and proof rendering are programmatic.

If the initial proof attempt returns `Unknown.`, the default `balanced`
configuration tries several further approaches in order. Two reuse the same
translation without another model call. A critic can request a corrected
translation, and a graph route can translate the case into a simpler logical
representation. Processing stops at the first definite answer. The narrower
`conservative` and broader `high-recall` configurations are also available.

The compiler also attempts two checked, reversible rewrites of recurring event
and part-whole patterns. They shorten some theories and proofs while retaining
connections to the ordinary predicates used by the axioms and other knowledge
bases.

For the full workflow and the exact retry order, see
[Pipeline architecture](docs/architecture/pipeline.md). For the logical forms,
start with the [Encoding reference](docs/encodings/README.md).

Useful commands
---------------

Run these from `llmpipe/`:

```bash
# Select a provider or an exact model version.
python3 solver/solve.py -llm claude "TEXT"
python3 solver/solve.py -llm gpt -version gpt-5.1 "TEXT"

# Inspect progressively more of the run.
python3 solver/solve.py -explain "TEXT"
python3 solver/solve.py -logic "TEXT"
python3 solver/solve.py -details "TEXT"
python3 solver/solve.py -debug "TEXT"

# Show which stage answered and how many model/prover calls were made.
python3 solver/solve.py -summary "TEXT"

# Use a narrower or higher-recall retry configuration.
python3 solver/solve.py -pipeline conservative "TEXT"
python3 solver/solve.py -pipeline high-recall "TEXT"
```

Evaluation and development
--------------------------

Ordinary use starts with `solver/solve.py`; the two top-level runners are for
contributors and research evaluation:

- `test.py` is a contributor convenience tool for small single-model checks.
- `runtests.py` is a research evaluation and record-generation tool.

Running either script without arguments prints its help instead of starting an
evaluation or making model calls.

```bash
# Quickly inspect five cases with one provider.
python3 test.py tests/tests_core.py -llm gemini -limit 5

# Record the same five cases for two providers as structured experiment data.
python3 runtests.py tests/tests_core.py -llms gemini,deepseek -limit 5
```

[`tests/README.md`](tests/README.md) describes the test-file format and how the
two runners resume. [Testing](docs/development/testing.md) covers the hash-seed
and cache conventions, checking a converter change, and safe practice for a
full-suite run; [runtime records](docs/reference/runtime-records.md) describes
the fields of a stored record.

The complete everyday option list is in the
[command-line reference](docs/reference/command-line.md). Less stable research
options are listed separately under
[experimental options](docs/reference/experimental-options.md).

Repository guide
----------------

```text
llmpipe/
|-- solver/          translation, compilation, retry, prover, and output code
|-- prompts/         Stage-1, Stage-2, critic, and graph prompts
|-- tests/           test cases and benchmark adapters
|-- docs/            user, architecture, encoding, code, and development docs
|-- mkdata/          builders for generated lexical and taxonomy data
|-- axioms_std.js    default background knowledge for GK
|-- test.py          quick, readable single-provider regression runner
|-- runtests.py      resumable multi-provider experiment and JSON-record runner
|-- ask.py           direct LLM-call utility, without logic or GK
```

The repository root also contains `udppipe`, an older Stanza/UD-based pipeline
that does not use an LLM. It has a separate README and installation procedure.
The root-level `gk/` directory contains the bundled GK reasoning backend and
its required data files. It also has a separate README; GK is developed in the
[gkreasoner repository](https://github.com/tammet/gkreasoner).

This is research software. A formal proof establishes what follows from the
generated logical theory; it does not by itself guarantee that the model's
translation fully captured the English. The code is distributed under the
[Apache License 2.0](../LICENSE).

Documentation
-------------

Start with the [documentation overview](docs/README.md). Common destinations
are:

- [Getting started](docs/getting-started.md) — installation and first commands
- [Encoding reference](docs/encodings/README.md) — Stage 1, Stage 2, compiled
  representations, graph format, and GK clauses
- [Architecture](docs/architecture/README.md) — algorithms and processing order
- [Command-line reference](docs/reference/command-line.md) — supported options
- [Reference documentation](docs/reference/README.md) — command-line,
  configuration, runtime-record, and proof-output references
- [Code guide](docs/code/README.md) — implementation map
- [Development guide](docs/development/README.md) — extending and testing
- [Mechanism experiments](docs/mechanisms/README.md) — mechanisms tried,
  measurements, and resulting design decisions

Paper snapshots
---------------

The current code is newer than the reported experiments. The LPAR 2026
pipeline is preserved at the `nlpsolver` tag
[`lpar-2026-06-23`](https://github.com/tammet/nlpsolver/tree/lpar-2026-06-23/llmpipe),
with experiment data on the [`lpar` branch of
`nlformtasks`](https://github.com/tammet/nlformtasks/tree/lpar). The NeSy 2026
data and recorded results are at the [`nesy-2026` tag of
`nlformtasks`](https://github.com/tammet/nlformtasks/tree/nesy-2026).

Troubleshooting
---------------

- **Missing API key:** create `../secrets/<provider>_secrets.txt` containing
  one key. The directory is ignored by Git.
- **A translation appears wrong:** use `-details` to inspect Stage 1, Stage 2,
  and the clauses, and try another provider with `-llm`.
- **Proof search reaches its time limit:** increase the per-call limit, for
  example with `-seconds 10`.
- **A cached answer is unwanted:** use `-nollmcache` for a fresh model call.

GK itself is maintained in the
[gkreasoner repository](https://github.com/tammet/gkreasoner), with binaries,
documentation, and prover examples.
