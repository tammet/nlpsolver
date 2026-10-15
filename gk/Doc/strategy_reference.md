# Strategy Reference

A strategy controls proof search: clause selection, inference restrictions,
resource limits, and answer limits. It does not change the input logic.

## Automatic strategy

When neither `-strategy` nor `-strategytext` is given, GK constructs a strategy
sequence from the parsed problem. Each strategy has an initial time in which to
find a proof. A strategy that finds none is stopped at that limit. The first
successful strategy receives the remaining search time and is then used for
the query's blocker checks and searches for explicit negation.

The first strategy depends on the problem size: negative-clause preference for
small problems and query-focused selection for large ones. Alternatives use
the other selection method, unit restriction, query focus with SINE filtering
for larger axiom sets, and hardness preference. By default the first strategy
gets half of the search budget before it is abandoned without a proof; the
alternatives share the rest. With `-explore`, or automatically when `-seconds`
exceeds 30, every strategy gets the same short initial limit.

Use an explicit strategy when the search configuration must remain fixed.

`-parallel <n>` uses `n` total processes (1 to 8, Unix) for automatic
selection. The default is 1, with no parallel search. If several strategies
succeed, GK uses the first one in the order above. Explicit strategies disable
parallel search.

```sh
gk Examples/exceptions/penguin.gkp
```

## Multi-run strategies

A strategy object may contain a `runs` array. Each element is a complete or
partial strategy. GK tries the runs in order and stops when a run answers the
query. Top-level values act as defaults for the individual runs.

```json
{
  "total_seconds": 20,
  "runs": [
    {"max_seconds": 1, "strategy": ["unit"],
     "query_preference": 0},
    {"max_seconds": 4, "strategy": ["negative_pref"],
     "query_preference": 1},
    {"max_seconds": 15, "strategy": ["query_focus"],
     "query_preference": 1, "sine": 1}
  ]
}
```

```sh
gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/runs.json
```

Short restricted searches belong first; broader searches belong later. A
restricted run such as unit resolution is incomplete, so failure in one run
does not imply that the problem has no proof.

## Single-run strategies

A single-run file is one JSON object:

```json
{
  "max_seconds": 10,
  "strategy": ["query_focus"],
  "query_preference": 1,
  "max_distinct_answers": 10
}
```

Pass the file with `-strategy`:

```sh
gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/query_focus.json
```

The same object can be supplied inline:

```sh
gk Examples/exceptions/penguin.gkp \
  -strategytext '{"strategy":["query_focus"],"query_preference":1}'
```

Strategy files contain configuration only; running one as a logic problem
produces a missing-question error.

## Time limits

### `max_seconds`

Maximum time for one run, in seconds. The command-line `-seconds` value is used
by the automatic strategy.

### `total_seconds`

Maximum cumulative time across all runs.

### `giveup_dseconds`

No-proof give-up limit for one run, in tenths of a second. The run ends at
this limit only while it has proved nothing; once any proof is found, the run
continues under the ordinary limits, collecting further proofs and answers.
The automatic strategy sequence uses this key. It can also be used in
hand-written multi-run strategies.

## Answer and proof limits

### `max_answers`

Maximum number of stored proofs in total. Several proofs of one answer each
count. The automatic strategy commonly sets this to 10.

### `max_total_proofs`

Synonym for `max_answers`.

### `max_distinct_answers`

Stop after this many distinct answer substitutions have been found. This
corresponds to command-line `-maxanswers`.

### `max_proofs`

Retain at most this many proofs per distinct answer. This corresponds to
command-line `-maxproofs` and does not stop search by itself.

## Selection methods

The `strategy` value is a string or an array of strings. Array entries enable
several compatible preferences.

```json
{"strategy": ["query_focus", "positive_pref"]}
```

| Name | Effect |
|---|---|
| `negative_pref` | Prefer clauses containing negative literals |
| `positive_pref` | Prefer clauses containing positive literals |
| `query_focus` | Prefer clauses in the query/goal queues |
| `hardness_pref` | Prefer clauses whose literals are estimated cheap to resolve away; the estimate uses literal size, new variables, and the number of complementary-polarity occurrences of the predicate |
| `knuthbendix_pref` | Use a Knuth-Bendix-oriented preference for equational problems |
| `hyper` | Enable hyperresolution |
| `unit` | Restrict resolution arguments to unit clauses |
| `double` | Allow resolution arguments of length at most 2 |
| `triple` | Allow resolution arguments of length at most 3 |

`unit`, `double`, and `triple` impose inference restrictions and can make the
search incomplete.

## Query and clause queues

Clauses have goal, assumption, or axiom roles. `query_preference` (integer
0 to 4; default 0) determines how those roles map to selection queues:

| Value | Treatment |
|---:|---|
| `0` | Put all clauses in one queue |
| `1` | Keep the queues as marked by their roles |
| `2` | Move positive goal units and non-included axioms to the assumption queue |
| `3` | Keep only fully negative goal clauses in the goal queue |
| `4` | Treat all clauses as axioms regardless of role |

`query_focus` is the selection method that gives direct preference to the goal
queue.

### `weight_select_ratio`

Integer, 1 or greater; default 5. Ratio of priority-queue picks to
simple-order picks when the given clause is selected from a queue. The
accepted synonym is `given_queue_ratio`.

## Derived-clause limits

Each key takes an integer, 0 or greater; 0 disables the corresponding
limit, and 0 is the default.

| Key | Limit |
|---|---|
| `max_size` | number of literals in a retained clause |
| `max_depth` | term nesting depth in a retained clause |
| `max_length` | number of arguments (the length) of a term in a retained clause |
| `max_weight` | calculated clause weight |

Restrictive values reduce memory use but may remove all proofs of an answer.

## Equality and relevance filtering

### `equality`

Use `1` to enable equality reasoning and paramodulation, or `0` to disable it.
The automatic strategy enables it when required by the input.

### `rewrite`

Use `1` to rewrite terms with oriented equalities, or `0` to disable rewriting.

### `sine`

Apply SINE relevance filtering to the initial axioms:

| Value | Meaning |
|---:|---|
| `0` | no SINE filtering |
| `1` | weak filtering |
| `2` | strong filtering |

SINE is mainly useful for a small query against a large axiom set.

## Confidence-related keys

### `independence`

Integer, 0 to 100. In the provenance-aware retained-proof calculation, `0`
disables the combination of alternative proofs and any nonzero value
enables it; the overlap is measured from activation-event sets. With
`-oldcumulate`, the percentage scales the dependency-ratio discounting of
that option's noisy-or calculation.

### `keepconfidence`

Minimum confidence for retained derived clauses, as an integer percentage from
0 to 100.

### `raw_proofs`

Set to `1` for raw-proof collection. The command-line form is `-rawproofs`.

## Arithmetic instantiation

### `arith_instantiation`

| Value | Meaning |
|---:|---|
| `0` | disabled |
| `1` | conservative one-variable instantiation |
| `2` | extended mode, including selected two-variable conditions |

The arithmetic README gives complete commands and examples. Additional
`arith_inst_*` limit keys exist for controlled experiments, but the three modes
above are the stable public interface.

## Planning search

These keys are experimental and act only in the primary search (depth 0,
outside a negative-evidence search). Each one is an exact integer; another
value is rejected. All are 0 by default, and with all of them 0 the search is
the same as without the keys. [`planning.md`](planning.md) describes each
key, its conditions, its input records and its output.

| Key | Values | Effect when on |
|---|---|---|
| `ground_contextfree_negative_first` | 0, 1 | resolve first a negative ground literal with no `$ctxt` term |
| `permission_pair_first` | 0, 1 | resolve first a negative `poss(B, ... $do(A, S))` with two known action terms |
| `action_actor_type_first` | 0, 1 | resolve first a negative `isa(C, X)` where X is the actor of an action in the clause |
| `reachable_known_head_first` | 0, 1 | resolve first a negative `reachable($do(A, S), N)` with a known action term A |
| `blocker_unit_cut` | 0, 1 | drop a given or answer clause when a strict unit proves the content of one of its blockers |
| `blocker_unit_cut_guards` | 0, 1 | with `blocker_unit_cut` 1: guarded strict rules can cut too |
| `eager_condensation` | 0, 1 | condense each new clause before it is built |
| `plan_filters` | 0, 1, 2 | drop a clause whose plan matches a `$planfilter` record; 2 also checks every `$do` term |
| `plan_state` | 0, 1 | drop a clause with a subgoal that is false in a `$planstate` record |

The four selection keys need pure query focus: the `query_focus` strategy
without `negative_pref`, `positive_pref`, `hyperres`, `knuthbendix_pref` or
`hardness_pref`.

Example of a plan search:

```json
{"strategy": ["query_focus"], "query_preference": 1, "equality": 0,
 "ground_contextfree_negative_first": 1, "reachable_known_head_first": 1,
 "permission_pair_first": 1, "eager_condensation": 1,
 "blocker_unit_cut": 1, "blocker_unit_cut_guards": 1}
```

## Supplied strategy files

| File | Contents |
|---|---|
| [`query_focus.json`](https://github.com/tammet/gkreasoner/blob/master/Examples/strategy/query_focus.json) | query-focused single run |
| [`negative_pref.json`](https://github.com/tammet/gkreasoner/blob/master/Examples/strategy/negative_pref.json) | negative-clause-preference single run |
| [`runs.json`](https://github.com/tammet/gkreasoner/blob/master/Examples/strategy/runs.json) | three runs from restricted to broader search |

The files are described and exercised in
[`../Examples/strategy/README.md`](https://github.com/tammet/gkreasoner/blob/master/Examples/strategy/README.md).
