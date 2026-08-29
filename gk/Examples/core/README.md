# Core reasoning examples

These problems exercise resolution, variable substitution, equality, function
terms, and explicit negation. Run commands from the repository root.

## Resolution and function terms

[`logic_chain.js`](logic_chain.js) encodes implication with function terms and
proves `p(i(a,i(b,a)))`. It contains no confidence annotations or defaults, so
the result is a classical proof with confidence 1.

[`algebra.js`](algebra.js) contains inverse, identity, and associativity axioms
and proves `m(e,c) = c` by equality reasoning.

## Support for explicit negation

[`negation.js`](negation.js) supplies several sources for a predicate and its
explicit negation. [`negation_conflict.js`](negation_conflict.js) places
conflicting support on `bird(a)` and propagates it through rules for `flies(a)`.

```sh
./bin/gk Examples/core/negation_conflict.js -detail
```

The returned verdict confidence is `0.252`. The detailed report names the
contested `bird(a)` premise as a conflict source; its `calculation` and
status fields are explained in
[`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md).

## Selected files

| File | Main feature |
|---|---|
| `algebra.js` | equational reasoning |
| `logic_chain.js` | Hilbert-style implication axioms with function terms |
| `negation.js` | positive and negative sources |
| `negation_conflict.js` | a contested premise propagated into a conclusion |

See [`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md) for the proof and
support-calculation algorithms.
