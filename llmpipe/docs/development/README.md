# Development

Changing the pipeline: how to add to it, how to test what you added, and how to
regenerate the data files that are built rather than written.

Read these pages when you are editing the repository. They assume you already
know what the pipeline does; if not, start with the
[architecture](../architecture/README.md) pages, and use the
[code guide](../code/README.md) to find the module you need.

The fixture suites this repository is developed against live in `tools/`, which
is not tracked here. The published runners are `test.py` and `runtests.py`, and
[testing](testing.md) says what can be checked with them.

Two conventions matter before any change. Conversion output depends on the hash
seed, so a test that compares clause lists runs with `PYTHONHASHSEED=0`. And the
local model-response cache is on by default: a repeated run answers from it and
makes no provider request, which is what makes repeated runs cheap and
reproducible.

## Pages

- [Extending the pipeline](extending.md) — where to add a predicate, an axiom,
  a converter pass or a retry stage, and which record fields a new stage must
  fill.
- [Testing](testing.md) — the hash-seed and cache conventions, running the test
  sets, checking a converter change, call accounting, and safe practice for an
  experiment.
- [Generated data](generated-data.md) — the five `data_*.py` modules, the
  `mkdata/` sources they are built from, and how to rebuild them.

## Related documentation

- [Code guide](../code/README.md) — where each subsystem lives
- [Architecture](../architecture/README.md) — what each subsystem does
- [Encoding reference](../encodings/README.md) — the forms a change must respect
- [Mechanism experiments](../mechanisms/README.md) — what has already been tried
