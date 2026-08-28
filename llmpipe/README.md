llmpipe
=======

`llmpipe` answers questions about an English passage by separating translation
from reasoning. The selected language model structures the English and
translates it into extended first-order logic. Deterministic code compiles that
logic, and the GK reasoner proves the answer or its explicit negation. If
neither can be proved, the result is `Unknown.`.

The logic supports quantifiers, defeasible rules, probabilistic confidence,
exceptions, and contradictions. With `-explain`, the system also presents the
proof in English.

Example
-------

```bash
cd llmpipe
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
```

```text
True.
```

Add `-explain` for the English proof, `-logic` for the clauses, and
`-summary` for the stage that answered and the call counts.

Installation
------------

Prerequisites:

- Linux on x86-64 (the bundled `../gk/gk` binary is a static Linux x86-64
  ELF), or macOS on Apple Silicon — download `bin/gk-macos-arm64` from the
  [gkreasoner repository](https://github.com/tammet/gkreasoner) and use it in
  place of `../gk/gk` (the llmpipe pipeline itself is only tested on Linux)
- Python 3.10+ (only the standard library is required; no `pip install`)
- An LLM API key from at least one of Gemini, OpenAI, Anthropic, or DeepSeek

```bash
git clone https://github.com/tammet/nlpsolver.git
cd nlpsolver

# Store one API key in a plain-text file (pick any one provider):
#   secrets/gemini_secrets.txt    secrets/gpt_secrets.txt
#   secrets/claude_secrets.txt    secrets/deepseek_secrets.txt
echo "YOUR_API_KEY" > secrets/gemini_secrets.txt

# Check the install without making an API request.
python3 smoketest.py
```

GK has its own distribution. The
[gkreasoner repository](https://github.com/tammet/gkreasoner) contains its
binaries, documentation, and examples. See
[Getting started](docs/getting-started.md) for model selection and further
commands.

What a run does
---------------

Stage 1 turns the English into atomic semantic units. Stage 2 turns those into
extended first-order logic. The converter produces a clause list. GK searches
for a proof.

When GK returns `Unknown`, the default configuration tries four more stages:
two that reuse the same parse without a model call, then the critic
retranslation, then the graph retranslation. The first definite answer stops
the rest.

During compilation, two checked reversible transformations may replace
repeated logical patterns with shorter equivalent forms. This can make proofs
easier to find and read. See
[proof shortening](docs/architecture/proof-shortening.md).

Documentation
-------------

Start with the [documentation overview](docs/README.md), or go directly to:

- [Getting started](docs/getting-started.md) — configuration and first commands
- [Encoding reference](docs/encodings/README.md) — the exact logical forms
- [Architecture](docs/architecture/README.md) — how the pipeline operates
- [Command-line reference](docs/reference/command-line.md) — available options
- [Code guide](docs/code/README.md) — where the implementation lives

For deeper lookup and maintenance, see the [Reference](docs/reference/README.md),
[Development guide](docs/development/README.md), and
[Mechanism experiments](docs/mechanisms/README.md).

`CLAUDE.md` at the repository root is guidance for coding agents working in
this repository.
