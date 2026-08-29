# Strategy examples

Strategy files are JSON configuration objects passed with `-strategy`. They
contain no logic and cannot be run as proof problems.

GK normally creates a strategy automatically:

```sh
./bin/gk Examples/exceptions/penguin.gkp
```

The supplied files demonstrate the two main explicit selection styles and a
sequence of runs.

## Query-focused search

[`query_focus.json`](query_focus.json) contains:

```json
{
  "max_seconds": 10,
  "strategy": ["query_focus"],
  "query_preference": 1,
  "max_distinct_answers": 10
}
```

`query_preference: 1` preserves the goal, assumption, and axiom queues;
`query_focus` gives preference to the goal queue.

```sh
./bin/gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/query_focus.json
```

Expected result: `b` is accepted and `p` is rejected, both with confidence 1.

## Negative-clause preference

[`negative_pref.json`](negative_pref.json) selects clauses containing negative
literals. It is a useful baseline for small resolution problems:

```sh
./bin/gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/negative_pref.json
```

This strategy returns the same accepted and rejected answers.

## Several runs

[`runs.json`](runs.json) attempts three searches in order:

1. one second of unit resolution;
2. four seconds with negative-clause preference;
3. fifteen seconds of query-focused search with weak SINE filtering.

```sh
./bin/gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/runs.json
```

The first run is sufficient for this problem.

## Confidence combination

`independence: 0` disables same-polarity aggregation. A nonzero value
selects provenance-aware aggregation from the proofs' activation-event
sets. `-oldcumulate` selects the calculation controlled by intermediate
percentage values.

[`../../Doc/strategy_reference.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/strategy_reference.md) lists the
strategy keys. [`../../Doc/how_gk_works.md`](https://github.com/tammet/gkreasoner/blob/master/../Doc/how_gk_works.md)
describes proof combination.
