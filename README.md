nlpsolver
=========

Nlpsolver is an experimental system for automated reasoning in natural language,
capable of performing both natural language inference (NLI) and question answering.
It contains two independent pipelines:

* **[llmpipe](llmpipe/README.md)** — the newer LLM-based pipeline (GPT,
  Claude, Gemini, or DeepSeek) that replaces the Stanza parser with a
  two-stage LLM semantic parser. This is the current pipeline.
  Test cases, recorded multi-LLM results, and analysis for this pipeline are published
  separately in [nlformtasks](https://github.com/tammet/nlformtasks).

* **udppipe** — the older Stanza/UD-based semantic parser pipeline, described in the paper
  [An Experimental Pipeline for Automated Reasoning in Natural Language](https://link.springer.com/chapter/10.1007/978-3-031-38499-8_29).
  Does not require LLMs. See the `udppipe/` folder and its README.

Both pipelines share the same `gk` theorem prover backend and have a similar core logic representation.

Each pipeline contains:
* A semantic parser from English to extended first order logic.
* A first-order logic commonsense reasoner solving the problem expressed in extended logic.
* A subsystem for converting the proof given by the reasoner to English.

The commonsense reasoner is built on top of
a [high-performance FOL reasoner](https://link.springer.com/chapter/10.1007/978-3-030-29436-6_32),
extended to use [numeric confidences](https://link.springer.com/chapter/10.1007/978-3-030-79876-5_29)
and [defeasible rules](https://link.springer.com/chapter/10.1007/978-3-031-10769-6_18).

Nlpsolver is developed with a goal to be (a) a backbone of our research in
combining machine learning and large language models with logic-based
symbolic reasoning, (b) using automated reasoner as an interface
between natural language and external tools like database systems and scientific
calculations.

Subfolders
------------

* llmpipe: the llm-based pipeline, needs secrets and gk folders.
* udppipe: the Stanza/UD-based pipeline, needs the gk folder.
* secrets: empty folder for files with LLM api secrets.
* gk: the gk commonsense reasoner used in both pipelines
* exparchive: archive of data from experiments


Installation
------------

**Requirements**

* Linux on x86-64 (the bundled `gk/gk` reasoner binary is a statically-linked
  Linux x86-64 ELF), **or** macOS on Apple Silicon (ARM64) — a macOS ARM64
  build of the reasoner is bundled as `gk/gk-macos-ARM64.zip`; unzip it and
  use the extracted `gk` binary in place of `gk/gk`.  Note that the
  `llmpipe` and `udppipe` pipelines have only been tested on Linux —
  running them on macOS has not been verified and may need small tweaks.
* Python 3.10 or later (tested up to 3.12). No `pip` packages are required at
  runtime — the pipeline uses only the Python standard library.
* For `udppipe`: the [Stanford Stanza](https://stanfordnlp.github.io/stanza/)
  NLP package. The Stanza install does require `pip` packages; see
  [`udppipe/README.md`](udppipe/README.md).
* For `llmpipe`: an API key for at least one LLM provider (GPT, Claude,
  Gemini or DeepSeek), placed in a plain-text file under `secrets/`.

**Quick start (llmpipe)**

```bash
git clone https://github.com/tammet/nlpsolver.git
cd nlpsolver

# Gemini is the default. Create its private key file, then use an editor to
# place the raw key in it. This avoids putting the key in shell history.
install -m 600 /dev/null secrets/gemini_secrets.txt
${EDITOR:-nano} secrets/gemini_secrets.txt

# Optional: a venv keeps everything self-contained (no system packages
# needed since the runtime uses only the Python stdlib).
python3 -m venv ../nlpsolver-venv
source ../nlpsolver-venv/bin/activate   # or use ../nlpsolver-venv/bin/python3 directly

# Smoke-test the install without spending any LLM credits:
python3 smoketest.py

# Run a real query (uses your API key):
cd llmpipe
python3 solver/solve.py -llm gemini \
  "Elephants are animals. John is an elephant. Is John an animal?"
# -> True.
```

To use GPT, Claude, or DeepSeek instead, create the corresponding file named
in [`secrets/README.md`](secrets/README.md) and give the same provider to
`-llm`.

Note: first calls make live LLM round-trips (~10–60 s); reruns are cache-served and
near-instant. Parses vary slightly by LLM, so a cold call may occasionally differ
(e.g. return `Unknown.`) — just rerun, or try `-llm claude`.

Note: the secrets/ folder is in `.gitignore`, so your key will not be
accidentally committed.

**Quick start (udppipe)**

```bash
# Continue from the same clone. udppipe needs Stanza + transformers (~1.3 GB
# of pip packages, plus a ~525 MB Stanza model on first download).
../nlpsolver-venv/bin/pip install -r udppipe/requirements.txt
../nlpsolver-venv/bin/python3 -c 'import stanza; stanza.download("en")'

# Start the parser server (loads Stanza into memory, ~10s on CPU):
cd udppipe
../../nlpsolver-venv/bin/python3 nlpserver.py &

# Run a query:
../../nlpsolver-venv/bin/python3 nlpsolver.py "Elephants are animals. John is an elephant. Is John an animal?"
# -> True.
```

The installation and use of both pipelines is described in the corresponding
separate READMEs: [`llmpipe/README.md`](llmpipe/README.md) and
[`udppipe/README.md`](udppipe/README.md).





