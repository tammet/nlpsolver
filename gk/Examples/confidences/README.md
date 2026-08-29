# Confidence and support examples

The examples in this directory show how input confidences produce answer
support and confidences. Each ground instance of an uncertain input clause
is an independent activation event whose probability is the input
confidence: the ground-instance activation semantics.

GK selects between calculations automatically:

- same-polarity retained proofs are combined through their
  activation-event sets (the provenance-aware retained-proof calculation);
- an answer with contested atoms may get a dependency-aware
  shared-threshold calculation;
- direct retained-proof and fallback results also carry the four report
  fields, as proof-pool decompositions rather than completed atom-level
  partitions.

With `-detail`, the `calculation`, `coverage_status`, and
`polarity_status` fields identify the selected calculation and its status
([`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md)).

Run commands from the repository root. `-confidence 0` retains results
below the default acceptance threshold.

## Product along a proof

[`coin1.gkp`](coin1.gkp) and [`coin1.js`](coin1.js) contain:

```prolog
0.5::p(heads1).
0.6::p(heads2).
r(c) :- p(heads1), p(heads2).
query(r(X)).
```

The proof of `r(c)` uses both uncertain facts. Its support contribution is
`0.5 * 0.6 = 0.3`. In this one-sided case the verdict confidence equals
the proof contribution, and GK reports it in the `confidence` field.

[`rulemult.js`](rulemult.js) gives the same calculation to a conjunctive rule.
[`rules4.js`](rules4.js) and [`rules5.js`](rules5.js) use a rule with confidence
`0.8` three times after a fact with confidence `0.9`, producing
`0.9 * 0.8^3 = 0.4608`.

## Alternative proofs

[`cumulate.gkp`](cumulate.gkp) and [`cumulate.js`](cumulate.js) give one atom
two distinct sources:

```prolog
0.5::bird(a).
0.6::bird(a).
query(bird(a)).
```

```sh
./bin/gk Examples/confidences/cumulate.gkp
```

The evidence sources are disjoint, so noisy-or gives
`1 - (1 - 0.5)(1 - 0.6) = 0.8`.

[`overlap1.js`](overlap1.js) and [`overlap3.js`](overlap3.js) contain proofs
with shared premises. GK reconstructs each proof's ground activation events
and uses the shared events only once. The reported `confidence` values are
`0.846` and `0.959`, respectively.

The retained-proof value is the exact union probability of the retained
proof set when the activation-event identifiers are ground, replay
succeeds, and the proof-union calculation stays within its bounds. Retained
proofs need not cover every possible proof; the value is then a lower
bound of the full activation-model value.

## Positive and negative support

[`net_direct.gkp`](net_direct.gkp) and [`net_direct.js`](net_direct.js) contain:

```prolog
0.7::flies(a).
0.4::-flies(a).
query(flies(a)).
```

```sh
./bin/gk Examples/confidences/net_direct.gkp -detail
```

Expected assessment:

```text
confidence: 0.3
support: 0.3 for, 0 against
conflict: 0.4   ignorance: 0.3
```

The `net_*.js` files vary which polarity dominates. `net_premise.js` places
the conflict on a premise and then derives a conclusion from it.

## Chains and networks

[`near.js`](near.js) and [`near2.js`](near2.js) apply a transitivity rule with
confidence `0.9` eight times, producing `0.9^8 = 0.4305`.

[`smokes.gkp`](smokes.gkp) and [`smokes.js`](smokes.js) contain several proofs
of `smokes(sam)`. GK multiplies within each proof and combines the provenance
sets, returning `0.3764`. The `alarm*.js` and `socialsmoking*.js` files
provide larger networks and retain comparison material in their comments.

## Acceptance threshold

The default `-confidence` threshold is `0.1`. A derivation at or below the
effective limit may be printed with `result: evidence below limit`. This occurs
in `n3.js`, `rules3.js`, and `equality3.js`. Lowering the threshold changes
the acceptance label; the derivation stays the same:

```sh
./bin/gk Examples/confidences/n3.js -confidence 0
```

## File index

| Files | Calculation or feature |
|---|---|
| `cumulate.gkp`, `cumulate.js` | two disjoint sources, noisy-or, result `0.8` |
| `coin1.gkp`, `coin1.js` | product of two facts, result `0.3` |
| `coin2.js` | two-coin disjunction, result `0.8` |
| `coin3.js`, `coin4.js` | four sources with confidence `0.6`, result `0.9744` |
| `coin4_err.js` | four sources plus an inequality constraint |
| `coin4_err1.js`, `coin4_err2.js` | smaller constrained variants |
| `overlap1.js`, `overlap3.js` | overlap between the proofs' provenance sets |
| `near.js`, `near2.js` | repeated rule confidence along a transitive chain |
| `rulemult.js` | confidence product for a conjunctive rule |
| `rules1.js`, `rules2.js` | positive and negative rule evidence, open and ground query forms |
| `rules3.js` | disjunctive evidence at the acceptance boundary |
| `rules4.js`, `rules5.js` | repeated rule instances, open and ground query forms |
| `net_direct.gkp`, `net_direct.js` | direct support and opposition |
| `net_lone.js` | single-polarity baseline |
| `net_fought.js`, `net_against.js`, `net_strong.js` | positive- and negative-dominant cases |
| `net_premise.js` | contested premise propagated through a rule |
| `n1.js`, `n2.js`, `n2a.js`, `n2c.js`, `n2plus.js`, `n3.js` | progressively larger combinations of pro and con evidence |
| `conf1.js` through `conf4.js` | compact pooling and opposition-resolution cases |
| `alarm.js`, `alarm_v1.js`, `alarm_v2.js` | alarm network variants |
| `smokes.gkp`, `smokes.js`, `smokes2.js` | smoking-network variants |
| `socialsmoking.js`, `socialsmoking2.js` | larger social-influence networks |
| `smokes_alchemy.js` | a smokes/cancer rule set adapted from an MLN example |
| `equality1.js`, `equality2.js`, `equality3.js` | support propagated and opposed through equality |

The algorithms are described in
[`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md).
