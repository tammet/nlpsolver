# Getting started

This page covers installation, model configuration, and the first commands.

## Requirements

Python 3, and the `gk` prover binary with its data files:

```text
llmpipe/axioms_std.js
../gk/gk
../gk/gk_name_number.txt
../gk/gk_taxonomy_packed.txt
```

The prover distribution is at <https://github.com/tammet/gkreasoner>. The
solver data archive is at <http://logictools.org/data/nlpsolver_data.tar.gz>.

## API keys

Keys are read from plain files, one key per file:

```text
../secrets/gpt_secrets.txt
../secrets/claude_secrets.txt
../secrets/gemini_secrets.txt
../secrets/deepseek_secrets.txt
```

## Selecting a model

`solver/llmcall.py` holds the defaults. Override per run:

```bash
python3 solver/solve.py -llm claude "Elephants are animals. John is an elephant. Is John an animal?"
python3 solver/solve.py -llm gpt -version gpt-5.1 "Elephants are animals. John is an elephant. Is John an animal?"
```

Responses are cached in `cache.db`. A repeated run answers from the cache.

## First commands

```bash
python3 solver/solve.py "Elephants are animals. John is an elephant. Is John an animal?"
python3 solver/solve.py -explain "Elephants are animals. John is an elephant. Is John an animal?"
python3 solver/solve.py -logic "Elephants are animals. John is an elephant. Is John an animal?"
python3 solver/solve.py -summary "Elephants are animals. John is an elephant. Is John an animal?"
```

`-explain` adds the English proof. `-logic` adds the simplified text and the
clauses. `-summary` prints the answering stage and the call counts.

## Reading the output

The last line is the answer. With `-summary`, the block above it names the
stage that answered, the answer the initial attempt reached, the enabled
stages, and the model calls made by each stage.

## Running a small test

```bash
python3 test.py tests/tests_core.py -limit 5
python3 runtests.py tests/tests_core.py -llms deepseek -limit 5
```

`runtests.py` writes one JSON per case and model under `testresults/`. See
[testing](development/testing.md).

## A few more commands

```bash
# Show every intermediate representation
python3 solver/solve.py -debug -logic -prover -explain "Elephants are animals. John is an elephant. Is John an animal?"

# Parse to logic only, do not call the prover
python3 solver/solve.py -nosolve "Elephants are animals. John is an elephant. Is John an animal?"
```

## Selecting a pipeline

Most users should keep the default `balanced` pipeline. For a deliberately
narrower or higher-recall run:

```bash
python3 solver/solve.py -pipeline conservative "Elephants are animals. John is an elephant. Is John an animal?"
python3 solver/solve.py -pipeline high-recall "Elephants are animals. John is an elephant. Is John an animal?"
```

See [configuration](reference/configuration.md) for what each pipeline enables.

## Calling a model without the logic pipeline

The separate `ask.py` utility sends a plain request directly to a model:

```bash
python3 ask.py "What is the capital of France?"

python3 ask.py -llm claude -p prompt.txt -f input.txt
```

The full option list is in the
[command-line reference](reference/command-line.md).

## Related documentation

- [Documentation overview](README.md)
- [Command-line reference](reference/command-line.md)
- [Configuration](reference/configuration.md)
- [Testing](development/testing.md)
