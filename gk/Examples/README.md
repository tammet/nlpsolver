# Tutorial

Commands in this document are run from the repository root. On Linux, `gk`
below is `./bin/gk`.

Most introductory problems are supplied in GKP (`.gkp`) and native
JSON-LD-LOGIC (`.js`) forms. The logic is the same; only the surface notation
and output format differ.

## 1. Defaults and answer substitutions

[`exceptions/penguin.gkp`](exceptions/penguin.gkp) asks which objects fly:

```prolog
bird(b).
penguin(p).
bird(X)   :- penguin(X).
object(X) :- bird(X).
-flies(X) :- penguin(X).
flies(X)  :- bird(X),   unless(-flies(X), 3).
-flies(X) :- object(X), unless(flies(X), 2).
query(flies(X)).
```

```sh
./bin/gk Examples/exceptions/penguin.gkp
```

The ordinary bird default has priority 3 and the opposing object default has
priority 2. The strict penguin rule supplies the exception:

```text
answer: b
confidence: 1

rejected answer: p
confidence against: 1
```

[`core/logic_chain.js`](core/logic_chain.js) shows a longer implication chain.
[`core/algebra.js`](core/algebra.js) introduces equality reasoning.

## 2. Several proofs for one answer

[`confidences/cumulate.gkp`](confidences/cumulate.gkp) states the same fact
from two distinct uncertain sources:

```prolog
0.5::bird(a).
0.6::bird(a).
query(bird(a)).
```

```text
confidence: 0.8
```

The two statements are separate activation events, and GK combines the
proofs' activation-event sets. For disjoint sets the combination is
noisy-or: `1 - (1 - 0.5)(1 - 0.6) = 0.8`. When proofs share activation
events, GK counts the shared events once.
The overlap cases are in [`confidences/overlap1.js`](confidences/overlap1.js)
and [`confidences/overlap3.js`](confidences/overlap3.js).

## 3. Evidence on both sides

[`confidences/net_direct.gkp`](confidences/net_direct.gkp) contains direct
evidence for and against one atom:

```prolog
0.7::flies(a).
0.4::-flies(a).
query(flies(a)).
```

```sh
./bin/gk Examples/confidences/net_direct.gkp -detail
```

The result has confidence `0.3`. The detailed report splits the total of 1
as follows:

```text
support: 0.3 for, 0 against
conflict: 0.4   ignorance: 0.3
```

The signed confidence is positive support minus negative support. GK places
the result in the accepted or rejected list according to the sign and prints
its magnitude as the verdict confidence.

Conflict records the part supported in both polarities. Ignorance records the
part supported in neither polarity. This direct-opposition case has a
completed shared-threshold report: with `-detail`, its `calculation` field
is `canonical_atom`. Reports from the direct retained-proof calculation or
from a fallback carry the same four fields as proof-pool decompositions;
the `calculation` field identifies which calculation produced the report
(see [`../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/Doc/how_gk_works.md)).
[`confidences/net_premise.js`](confidences/net_premise.js)
shows how a contested premise affects a downstream conclusion.

## 4. Defaults and exceptions

[`exceptions/bird_default.gkp`](exceptions/bird_default.gkp) defines a rule
that applies unless its exception can be established:

```prolog
bird(a).
bird(b).
flies(X) :- bird(X), unless(-flies(X), 2).
query(flies(X)).
```

With no evidence for either exception, both answers have confidence 1 and
record their blocker. [`exceptions/bird_exception.gkp`](exceptions/bird_exception.gkp)
adds `0.9::-flies(a).`; `flies(a)` has 0.1 positive support and 0.9 negative
support, so it is rejected with confidence 0.8, while `flies(b)` remains at 1.

[`exceptions/nixon.gkp`](exceptions/nixon.gkp) is the Nixon diamond. The
equal-priority defaults block each other, so neither polarity keeps usable
support and the report is ignorance; the downstream candidate is reported
with a zero margin and a `CONTESTED` flag.
[`exceptions/penguin.gkp`](exceptions/penguin.gkp) adds priorities and a strict
exception. [`exceptions/classify.gkp`](exceptions/classify.gkp) uses taxonomy
priorities:

```sh
./bin/gk Examples/exceptions/classify.gkp \
  -taxonomy -datafolder data
```

## 5. Search strategies

GK constructs a strategy automatically when none is supplied. An explicit
strategy is useful for reproducing a search or changing clause selection:

```sh
./bin/gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/query_focus.json
```

A strategy may also contain a sequence of runs. GK tries the runs in order
until one produces an answer or the total time limit is reached:

```sh
./bin/gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/runs.json
```

See [`../Doc/strategy_reference.md`](https://github.com/tammet/gkreasoner/blob/master/Doc/strategy_reference.md) for the
selection methods and limits.

## 6. Arithmetic instantiation

Ground arithmetic is evaluated during proof search. Finding a value for a
variable inside an arithmetic condition requires bounded instantiation.
[`arithmetic/apples_answer.gkp`](arithmetic/apples_answer.gkp) asks for `X` in
`X + 2 = 10`:

```sh
./bin/gk Examples/arithmetic/apples_answer.gkp -seconds 5 \
  -strategytext '{"strategy":["unit"],"query_preference":0,"arith_instantiation":1}'
```

The answer is `8` with confidence `0.8`. Mode `1` instantiates one
arithmetic unknown from a bounded candidate range; mode `2` also considers
selected two-variable cases. The mode is bounded enumeration; it does not
solve general equations.

## Categories

| Directory | Contents |
|---|---|
| [`core/`](core/README.md) | Resolution, substitutions, equality, and negation |
| [`confidences/`](confidences/README.md) | Proof products, pooling, overlap, negative support, conflict, and ignorance |
| [`exceptions/`](exceptions/README.md) | Defaults, blockers, priorities, taxonomies, and persistence |
| [`strategy/`](strategy/README.md) | Strategy files used with `-strategy` |
| [`arithmetic/`](arithmetic/README.md) | Ground evaluation and bounded numeric instantiation |
| [`language/`](language/README.md) | GK encodings of English reasoning problems, run against a shared knowledge base |
| [`asp_comparison/`](asp_comparison/README.md) | Bird-default inputs for gk, [clingo](https://potassco.org/clingo/), [DLV](https://dlv.demacs.unical.it/), [I-DLV](https://github.com/DeMaCS-UNICAL/I-DLV), and [s(CASP)](https://gitlab.software.imdea.org/ciao-lang/sCASP), with a scaling workload |
| [`fol_comparison/`](fol_comparison/README.md) | Non-Horn first-order clause problems with equality and function terms, with runs of other reasoners on the same inputs |
| [`system_comparison/`](system_comparison/README.md) | Executable semantic comparisons with [TweetyProject](https://tweetyproject.org/), [PASTA](https://github.com/damianoazzolini/pasta), and I-DLV |

The comparison cases, with captured outputs from the external systems, are
in [`../comparisons/`](https://github.com/tammet/gkreasoner/blob/master/comparisons/README.md); their per-case
descriptions are in [`../comparisons/CASES.md`](https://github.com/tammet/gkreasoner/blob/master/comparisons/CASES.md).

Input notation is covered in [`../Doc/input_languages.md`](https://github.com/tammet/gkreasoner/blob/master/Doc/input_languages.md).
The algorithms behind the examples are described in
[`../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/Doc/how_gk_works.md).
