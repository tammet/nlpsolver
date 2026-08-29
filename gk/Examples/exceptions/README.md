# Default and exception examples

A default rule has an exception condition, encoded in GK as a blocker
literal. Two operations are involved. During search, GK derives a candidate
conclusion and checks the exception condition in a bounded subsidiary
search; this decides proof acceptance. At report time, the support for the
exception condition and for its explicit negation is calculated
recursively; this produces the numbers. Numeric or taxonomy priorities
determine which defaults may defeat other defaults.

Run commands from the repository root. `-detail` prints positive support,
negative support, conflict, ignorance, conflict sources, and report flags.

## An unopposed default

[`bird_default.gkp`](bird_default.gkp) and [`bird_default.js`](bird_default.js)
contain:

```prolog
bird(a).
bird(b).
flies(X) :- bird(X), unless(-flies(X), 2).
query(flies(X)).
```

```sh
./bin/gk Examples/exceptions/bird_default.gkp
```

Both `a` and `b` are returned with confidence 1. Their proofs retain
`unless(-flies(a), 2)` and `unless(-flies(b), 2)`, recording the exceptions on
which the answers depend.

## Uncertain support for an exception condition

[`bird_exception.gkp`](bird_exception.gkp) and
[`bird_exception.js`](bird_exception.js) add:

```prolog
0.9::-flies(a).
```

The fact with confidence 0.9 plays two roles: it supports the exception
condition and undercuts the default application, and, because the
exception condition is the explicit negation of the conclusion, it also
rebuts the conclusion. GK reports the surviving positive support and the
stronger negative support:

```text
b  accepted with confidence 1.0
a  rejected with confidence 0.8
   (detail: support_for 0.1, support_against 0.9)
```

[`bird_hierarchy.js`](bird_hierarchy.js) uses an ordinary rule without a
blocker, providing a control case for the same support calculation.

## Evidence against an exception

GK evaluates the exception condition and its explicit negation
recursively; opposition is resolved within the relevant predecessor
configuration. Evidence against the exception may be a fact or may be
derived by a rule; both count.
In [`bird_counter.gkp`](bird_counter.gkp) a rule with confidence 0.58
derives evidence against the exception:

```prolog
bird(a).
0.6::injured(a).
vet(a).
0.58::-injured(X) :- vet(X).
flies(X) :- bird(X), unless(injured(X), 2).
query(flies(a)).
```

The exception `injured(a)` has positive support 0.6 and, through the rule,
negative support 0.58. In this share-free case the recursive calculation
reduces to a difference: the usable support for the exception is
0.6 − 0.58 = 0.02, the default is blocked with strength 0.02, and
`flies(a)` is reported with confidence 0.98 — the value the fact
`0.58::-injured(a)` would also give.

[`bird_counter_premise.gkp`](bird_counter_premise.gkp) moves the 0.58 from
the rule to its premise (`0.58::vet(a)` with a certain rule). The result is
0.748. The two placements mean different things: a rule confidence lowers
the strength of what the rule derives, so `-injured(a)` gets negative
support 0.58 as above. A premise confidence means that the premise
instance is active in that fraction of activation worlds: with 0.58 the
rule derives a certain `-injured(a)` and the exception is cancelled
completely; with 0.42 the rule does not apply and the exception keeps its
full 0.6. The average is 0.58 · 1 + 0.42 · (1 − 0.6) = 0.748.

Evidence against an exception is itself checked: if its own derivation is
blocked by a certain exception, it contributes nothing.

## Equal defaults

[`nixon.gkp`](nixon.gkp) and [`nixon.js`](nixon.js) encode the Nixon diamond:

```prolog
quaker(n).
republican(n).
pacifist(X)  :- quaker(X),     unless(-pacifist(X), 2).
-pacifist(X) :- republican(X), unless(pacifist(X), 2).
dislikeswar(X) :- pacifist(X).
query(dislikeswar(X)).
```

The two defaults have equal priority and block each other. The audited
detail report for `dislikeswar(n)` is pure ignorance: positive support 0,
negative support 0, conflict 0, ignorance 1, with a `CONTESTED` flag and a
zero margin. No rule-order tie breaker is used.
[`nixon_taxonomy.js`](nixon_taxonomy.js) asks the direct pacifism question with
taxonomy-style priorities.

## Numeric and taxonomy priorities

The `penguin*.js` files build a hierarchy from organism to bird, penguin, and
flying penguin, with opposing flight defaults at different priorities.
[`penguin2.js`](penguin2.js) uses numeric priorities.
[`penguin3.js`](penguin3.js) uses taxonomy priorities and therefore requires:

```sh
./bin/gk Examples/exceptions/penguin3.js \
  -taxonomy -datafolder data
```

Here the taxonomy supplies the order: `penguin` is below `bird` and
`organism` in the loaded hierarchy, so the penguin defaults defeat the
bird and organism defaults without hand-assigned numbers.

The taxonomy data files are in [`../../data/`](https://github.com/tammet/gkreasoner/blob/master/../data/README.md); a
taxonomy-form priority without `-taxonomy` (synonym `-defaults`) is an
error. [`penguin4.js`](penguin4.js) applies the same pattern to nested
function terms. [`taxonomy.js`](taxonomy.js) is a compact
taxonomy-priority case:

```sh
./bin/gk Examples/exceptions/taxonomy.js -taxonomy -datafolder data
```

[`penguin.gkp`](penguin.gkp) and [`penguin.js`](penguin.js) are compact cases
with a strict penguin exception and two opposed defaults. The stronger flight
default prevails for the ordinary bird; the penguin has full negative support.

## Classification from parts

[`classify.gkp`](classify.gkp) and [`classify.js`](classify.js) classify three
objects from observed parts. Several uncertain defaults may support the same
class, while strict engine evidence supports `-isa(X, organism)`.

```sh
./bin/gk Examples/exceptions/classify.gkp \
  -taxonomy -datafolder data
```

Main results:

```text
h1  accepted, confidence 0.44
b1  accepted through the bird path, confidence 0.5552
a1  rejected with negative support 1
```

The `b1` assessment also contains an opposed airplane path. The detailed proof
shows which classification defaults were pooled and which supplied negative
evidence.

## Persistence across situations

[`people_room.js`](people_room.js) represents entry and exit events across
three situations. Frame rules use blockers to carry `in` and `-in` forward
unless an event changes them. The example contains contested states; use
`-detail -confidence 0` to inspect the positive- and negative-support
paths:

```sh
./bin/gk Examples/exceptions/people_room.js \
  -detail -confidence 0 -taxonomy -datafolder data
```

The named markers in its frame rules are taxonomy-form priorities, so the
tables must be loaded; they do not change this example's result.

## Equivalent input notations

[`bird_penguin.gkp`](bird_penguin.gkp),
[`bird_penguin.js`](bird_penguin.js), and
[`bird_penguin.p`](bird_penguin.p) encode one problem in GKP,
JSON-LD-LOGIC, and TPTP. They are useful for inspecting conversion and output
format differences.

## Additional cases

| Files | Main feature |
|---|---|
| `hierarchy.js`, `taxonomy.js` | compact specificity and hierarchy cases (`taxonomy.js` needs `-taxonomy`) |
| `gbirds.js` | bird/penguin default with an ASP comparison in comments |
| `gbirds_funsymbs.js` | the same pattern with function symbols |
| `trivial.js` | plain facts and one closed query, with no defaults |

The blocker and support-calculation algorithms are described in
[`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md).
