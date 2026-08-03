# How GK Works

GK uses first-order resolution to construct proofs. It then checks exceptions,
combines alternative evidence, and compares support for the answer and its
negation.

## 1. From input to answers

GK converts every supported input notation to the same internal clause form.

A query with variables is converted to an answer clause. A proof of
`flies(b)`, for example, derives `$ans(b)` and returns `b` as the substitution.
A ground query returns `true` when the query is proved and `false` when its
negation is proved. If neither polarity is proved, the result is
`no information`.

GK proves a query by adding its negation as a goal and deriving a contradiction.
It combines clauses whose complementary literals unify, applies the resulting
substitution, and continues until it derives an answer or contradiction clause.
Simplification, equality reasoning, rewriting, and arithmetic evaluation are
applied when enabled by the problem and strategy.

The proof printed with an answer records the input clauses and inference steps.
Common step labels are:

| Label | Meaning |
|---|---|
| `in` | input clause |
| `goal` | clause generated from the query |
| `mp` | resolution or multi-premise resolution |
| `simp` | simplification |
| `cumul` | combination of alternative proofs |
| `arithinst` | bounded arithmetic instantiation |

## 2. Input confidences

An input confidence is a value between 0 and 1. It is written with a numeric
prefix in GKP and with the `confidence` annotation in GK's other input formats.
Facts, source reports, and rules may be annotated with input confidences. The
confidence determines how much support the annotated input can contribute; it
need not be a calibrated probability that the formula is objectively true.

An unannotated statement has confidence 1. In GKP:

```prolog
0.8::bird(tweety).
flies(X) :- bird(X).
```

The confidence belongs to a ground use of the input clause. This is the
ground-instance activation semantics: each ground instance of an uncertain
input clause is an independent activation event whose probability is the
input confidence. Two uses of the same rule with different substitutions are
different activation events. Repeated use of the same ground instance within
one proof counts once.

When one annotated formula is clausified into several clauses, its confidence
is distributed by taking an appropriate root. If a formula with confidence `P`
becomes `N` clauses, each clause receives `P^(1/N)`. This preserves the input
confidence `P` for a proof that requires all `N` clauses. The distinction matters
mainly for non-clausal formulas such as equivalences.

## 3. One proof

The support contribution of one proof is the product of the confidences of its
distinct evidence instances. Consider:

```prolog
0.5::p(heads1).
0.6::p(heads2).
r(c) :- p(heads1), p(heads2).
query(r(X)).
```

The only proof uses both uncertain facts and a rule with confidence 1:

```text
0.5 * 0.6 * 1 = 0.3
```

The calculation replays reconstructed proof histories. When an
activation-event identifier stays non-ground after replay, the per-use
product is a lower bound for that proof. Across several proofs, treating an
unresolved identifier as proof-specific is an approximation without a bound
guarantee; the maximum of the individual proof lower bounds is the
guaranteed lower bound.

## 4. Several proofs of the same answer

Alternative proofs may be independent, identical, nested, or partly
overlapping. Treating every proof as independent would count shared facts and
rules more than once.

GK records each proof's activation-event set — its provenance set — and
combines the sets by inclusion-exclusion:

- identical sets are idempotent;
- if one proof's activation-event set is a subset of another's, the subset
  proof's availability event subsumes the other and determines the result;
- disjoint sets combine by noisy-or;
- partial overlap produces a value between those cases.

For two disjoint proofs with support contributions `a` and `b`, noisy-or gives:

```text
1 - (1 - a)(1 - b)
```

Thus two independent facts with confidences `0.5` and `0.6` supporting
the same answer combine to `0.8`. The `overlap*.js` examples show why the
provenance sets are required; final proof values alone are insufficient.

Exact inclusion-exclusion is used for up to 20 reduced activation-event
sets. Above that limit GK uses a deterministic greedy fold and prints a
warning. This bounds the cost of combining a large number of proofs.

When every reconstructed activation-event identifier is ground and replay
and inclusion-exclusion stay within their bounds, the result is the exact
union probability of the retained proof set. It equals the full
activation-model value when the retained set covers all minimal
explanations; otherwise it is a lower bound.

This provenance-aware retained-proof calculation measures overlap directly.
In a strategy file, `independence: 0` disables combination and retains the
best proof; any nonzero value enables the calculation. `-oldcumulate`
selects a different calculation: noisy-or with the weaker contribution
scaled by a dependency ratio estimated from the proof histories and by the
`independence` percentage.

## 5. Positive and negative support

GK searches separately for proofs of a conclusion and its explicit negation.
Suppose the aggregated positive support is `a` and the aggregated negative
support is `b`. The local opposition decomposition, applied where the two
pools oppose each other at one point, is:

```text
support_for     = max(a - b, 0)
support_against = max(b - a, 0)
conflict        = min(a, b)
ignorance       = 1 - max(a, b)
```

The four values sum to 1. With `0.7::flies(a)` and `0.4::-flies(a)`, they are:

```text
support_for      0.3
support_against  0.0
conflict         0.4
ignorance        0.3
```

The signed confidence of a proposition is

```text
confidence = support_for - support_against
```

Its sign gives the favored polarity and its magnitude is the confidence in
that verdict. Conflict and ignorance retain the information lost by this
single number: strong balanced conflict and complete ignorance both have
confidence zero, but very different four-component reports. In the example,
the signed confidence of `flies(a)` is `0.3`.

This division follows from a shared uniform threshold for each ground atom.
Below both support levels, the two polarities conflict and neither is usable.
Between the levels, only the polarity with stronger support is usable. Above
both levels, neither polarity is usable.

### Two reference calculations

GK has two reference calculations and selects between them automatically.
The direct retained-proof calculation combines the retained proofs of the
two polarities and applies the decomposition above at the query. The
dependency-aware calculation evaluates contested atoms recursively,
resolving opposition at the premise where it occurs, and corresponds to
shared-threshold semantics on its stated fragment. The two calculations
need not be marginals of one global probability distribution; each report
names the calculation that produced it.

With `-detail`, three fields state what kind of report was produced.

| `calculation` | Meaning |
|---|---|
| `flat` | direct retained-proof calculation on an uncontested answer |
| `canonical_atom` | completed dependency-aware evaluation; runs on the canonical positive form of the atom |
| `blocked_flat` | a blocked default combined with the direct calculation |
| `proof_fallback` | dependency-aware evaluation was declined or discarded; the retained proof pools were combined instead |

| `coverage_status` | Meaning |
|---|---|
| `complete` | no covered operational failure was detected |
| `incomplete` | a resource limit interrupted the evaluation |
| `unsupported_fragment` | the case is outside the supported fragment of the dependency-aware evaluator |

`complete` does not establish that the query lies in the exact-correspondence
fragment; the unflagged cases listed at the end of this section remain
possible.

| `polarity_status` | Meaning |
|---|---|
| `guaranteed` | the two query orientations are the same calculation by construction |
| `not_guaranteed` | a query-directed route was used; the orientations are not guaranteed to mirror |

`not_guaranteed` is not a claim that the orientations disagree.

### The searches behind the report

GK runs three kinds of search for one query Q(x). The answer-literal
search, with the overall time limit T, discovers candidate answer
substitutions σ<sub>1</sub>, …, σ<sub>n</sub>. For each candidate
σ<sub>i</sub>, proofs of the query instance Qσ<sub>i</sub> and proofs of
its explicit negation ¬Qσ<sub>i</sub> form two separate collections. A
blocker literal found in either collection starts a bounded subsidiary
search for its exception condition, with a smaller time limit
T<sub>1</sub> (Section 6). In the figure, E<sup>+</sup><sub>i,j</sub>
names the j-th exception check in the positive collection of candidate
σ<sub>i</sub>, and E<sup>−</sup><sub>i,k</sub> the k-th in the negative
collection; an exception E′ nested inside such a check is searched with a
still smaller limit T<sub>2</sub> < T<sub>1</sub>. Candidate and proof
searches continue after the first substitution and the first proof.

<img src="images/gk_proof_search.svg" width="760"
     alt="Two search trees, one per answer candidate. Solid branches are
proof searches for the query instance and its negation; dashed branches
are bounded exception searches, with further nested levels.">

Solid branches are proof searches; dashed branches are exception searches.

The negative-support search looks for the explicit negation of the question
or of each answer found for an open question. A separate search is needed
because such evidence cannot close the original refutation.

Opposition to an intermediate premise is handled by a separate report-time
backward search over the loaded input clauses; it is not part of the proof
search above and is not read off the retained answer proof. This search matches directed rule conclusions against
ground targets and recursively collects derivations of both polarities,
within explicit resource caps. The collected derivation graph is then
combined numerically. The retained proof is used to decide whether this
assessment is relevant and supported, and supplies the fallback proof pools
if the assessment cannot be completed.

[`net_premise.js`](https://github.com/tammet/gkreasoner/blob/main/Examples/confidences/net_premise.js) is equivalent to:

```prolog
0.5::bird(a).
0.2::-bird(a).
0.9::flies(X) :- bird(X).
query(flies(a)).
```

The usable support for `bird(a)` — the support that remains once opposition
and exception conditions have been evaluated, and is therefore available for
propagation through a rule — is 0.3, so `flies(a)` receives
`0.3 * 0.9 = 0.27`. The `-bird(a)` evidence contests the premise; it does not
prove `-flies(a)`. With `-detail`, `bird(a)` is listed as a conflict source.

A reading of input confidences as independent clause-activation probabilities
gives a different number for this example (0.45: the premise is provable in
half the sampled worlds, and nothing derives the negated conclusion). The
[Monte Carlo checks](https://github.com/tammet/gkreasoner/blob/main/montecarlo/README.md) compare both readings with
GK's on the repository examples; the Differences section of
[`../montecarlo/comparison.md`](https://github.com/tammet/gkreasoner/blob/main/montecarlo/comparison.md) works through
this example, the uncertain-exception case, and the recursive-rule case, and
identifies the modelling decision each disagreement turns on.

For conclusions reached through rules, assessment proceeds from premises to
conclusions. A rule contributes support only when its body is usable and its
blockers do not fire.

The premise search is not memoized: the same atom reached through different
branches is evaluated again. Dependence is handled by enumerating
configurations of the shared predecessor ground atoms and, within the
joint-enumeration cap, conditioning the affected branches together within
each configuration. The search has depth, derivation-count, body-width,
joint-width, and time limits.

A flagged incomplete assessment is discarded as a whole and GK falls back to
proof-level assessment, where opposition to an intermediate premise has no
channel. `-detail` reports `PROOF_FALLBACK` together with cause flags such
as `DEPTH_CUTOFF`, `DERIVATION_CAP`, or `SCRUTINY_INCOMPLETE`.

Some limitations are not flagged: a non-ground answer can prevent the
report-time traversal from starting; an index or head-selection miss can
prevent the dependency-evaluation trigger; dependency-set overflow selects
the retained-proof calculation; the coarse dependency index can merge
distinct ground predecessors with the same predicate and arity; and a proof
that uses classical factoring is outside the stated fragment without being
detected. The directed premise search also excludes contraposition.

For compact output, GK routes a positive signed confidence to `answers` and a
negative one to `rejected_answers`. The ordinary `confidence` field is
therefore non-negative: it is the absolute value of the signed confidence, or
the confidence in the verdict as printed. Ties are reported as zero. `-detail`
adds the four components, conflict sources, and flags.

The optional `-envelope` report varies the resolution of identified conflicts
and returns minimum and maximum support. The bounds are support values;
they have no probability reading. `-stake F` compares that interval with a
decision threshold and reports `ACCEPT`, `DEFER`, or `REJECT`.

## 6. Defaults and blockers

A default rule has an exception condition. In GKP:

```prolog
flies(X) :- bird(X), unless(-flies(X), 2).
```

Two separate operations are involved: a search-time blocker check that
decides whether a candidate proof is accepted, and a report-time calculation
of the support for the exception condition.

The blocker check belongs to proof acceptance. The rule first derives a
candidate conclusion containing a blocker literal. GK then starts a bounded
subsidiary proof search for the exception condition, with diminishing
budgets for nested checks. The candidate survives when no blocking argument
with sufficient priority is found. An exception proof must also reach
confidence 0.5 to count; `-blockerconfidence` changes that threshold. The
blocker literal is retained in the printed proof, so the defeasible
assumption is visible.

The numeric report is calculated separately, by the dependency-aware
evaluation of Section 5. An exception undercuts the default application;
when the exception condition is the explicit negation of the conclusion, its
evidence also rebuts the conclusion. When support for the exception
condition is itself uncertain, the report divides accordingly. In the
isolated case of one certain default whose exception condition has support
0.9, the conclusion keeps 0.1 positive support. The remaining 0.9 depends on
the form of the exception condition: when it is the negated conclusion, the
0.9 is negative support and the answer is rejected; when it is a separate
atom, the 0.9 is ignorance.

Opposition to an exception condition — a fact or a derived conclusion — is
resolved recursively, within the relevant predecessor configuration, before
the exception can block. The `bird_counter*` examples in
[`../Examples/exceptions/README.md`](https://github.com/tammet/gkreasoner/blob/main/Examples/exceptions/README.md) show
the calculation.

Blockers have priorities. A blocking proof may itself depend on defaults, and
priorities prevent a lower-priority default from defeating a higher-priority
one. Priorities may be numbers or taxonomy terms such as `tax(penguin)`.
The comparison rules:

- A numeric priority defeats a strictly smaller numeric priority. Equal
  priorities do not defeat each other.
- `tax(name)` names a class in the loaded taxonomy. A priority naming a
  more specific class — a descendant in the taxonomy — defeats one naming
  a more general class: `tax(penguin)` defeats `tax(bird)`. This is the
  specificity principle for defaults, without hand-assigned numbers.
- When neither class is a descendant of the other, or a name is not in
  the taxonomy, the optional tie-breakers of `tax(name, nr)` are compared
  as numeric priorities. Without tie-breakers, neither side defeats the
  other.
- A numeric priority and a taxonomy priority are also compared through
  the tie-breaker: the number against the `nr` of `tax(name, nr)`.
  Against a bare `tax(name)`, a number makes no claim.

Taxonomy terms require `-taxonomy` (synonym `-defaults`) and the data
files in [`../data/`](https://github.com/tammet/gkreasoner/blob/main/data/README.md), which encode the WordNet noun
hierarchy; class names are WordNet-style names such as `penguin` or
`bird.n.01`. An input using taxonomy terms without the flag is an error.
Taxonomy priorities are compared by the blocker-priority check; the
dependency-aware evaluator does not process them.

Opposed defaults need not have a forced winner. In the Nixon diamond,

```prolog
pacifist(X)  :- quaker(X),     unless(-pacifist(X), 1).
-pacifist(X) :- republican(X), unless(pacifist(X), 1).
```

equal-priority arguments support both polarities. GK reports the opposition and
a zero margin rather than choosing one conclusion by rule order. When two such
opposed defaults have rule confidences `a` and `b`, each polarity counts only
where the other is absent: positive support `a(1-b)` and negative support
`b(1-a)`, no conflict component, and the remainder is ignorance. With two
certain defaults the entire four-component report is ignorance.

The explicit priorities matter here. With the priority omitted, an exception
reference makes no priority claim, and two such rules about opposite
polarities of one atom are treated as ordinary opposing evidence instead of
mutually blocking defaults: the region where both supports hold is then
reported in the conflict component.

## 7. Arithmetic

Ground arithmetic is simplified during proof search. For example, `2 + 3` is
evaluated to `5` when all operands are known.

Arithmetic conditions containing variables require bounded instantiation.
With `arith_instantiation: 1`, GK considers selected one-variable conditions;
mode `2` also considers selected conditions with two variables. Candidate and
probe limits keep the procedure finite. It is intended for small integer
problems and is not a general constraint solver.

## 8. Search control

Resolution is complete only when it runs without restrictive strategy limits.
Practical searches use time, clause-size, and selection controls. GK generates
an ordered sequence of strategies from the input. Each strategy gets an initial
time in which to find a proof. The first successful strategy gets the remaining
budget and is reused for the query's later searches (see
[`strategy_reference.md`](strategy_reference.md)). A strategy file can instead
specify:

- clause selection preferences such as `negative_pref` or `query_focus`;
- goal, assumption, and axiom queue treatment;
- limits on time, answers, clause size, depth, length, and weight;
- equality, rewriting, and SINE relevance filtering;
- several runs attempted in sequence.

A fixed set of axioms can be parsed once into shared memory (`-readkb`) and
reused across many queries (`-usekb`). `-parallel` runs automatically selected
strategies concurrently. Both options are described in
[`cli_reference.md`](cli_reference.md).

Unit resolution and other short-argument restrictions can be fast but are
incomplete. A timeout or a restrictive strategy therefore means only that no
proof was found under those limits.

## 9. Result states

Common result strings are:

| Result | Meaning |
|---|---|
| `answer found` | at least one answer met the confidence threshold |
| `evidence below limit` | a derivation was found but its margin was below `-confidence` |
| `no answers found` | no substitution was found for an open query |
| `no information` | neither polarity of a ground query was proved |
| `time limit, proof not found` | the search time expired before finding a proof |

The command-line options are listed in [`cli_reference.md`](cli_reference.md).
Input examples are in [`input_languages.md`](input_languages.md), and runnable
algorithm examples are indexed by [`../Examples/README.md`](https://github.com/tammet/gkreasoner/blob/main/Examples/README.md).
