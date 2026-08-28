# Reference

Lookup pages. Each answers a specific question about how to run the system or
about what a run leaves behind.

Use this area when you know what you want and need the exact name, value or
field. It is not the place to learn how something works: the
[architecture](../architecture/README.md) pages explain behaviour, and the
[encoding reference](../encodings/README.md) defines the logical forms. This
area owns options, configuration, records and output formats, and nothing else.

The three commands run from the `llmpipe/` directory: `solver/solve.py` answers
one passage, `test.py` runs a test file against one provider, and `runtests.py`
runs one against several in parallel.

## Pages

- [Command-line reference](command-line.md) — the ordinary and advanced options
  of all three commands, with the exact argument form of each. Start here.
- [Experimental options](experimental-options.md) — the research, ablation,
  diagnostic, legacy and compatibility controls, each with its status and its
  principal risk. None is needed for ordinary use.
- [Configuration](configuration.md) — how options resolve into the six stage
  keys, what the defaults are, and the settings that are module constants
  rather than command-line keys.
- [Runtime records](runtime-records.md) — the fields a run writes into its case
  JSON, including the per-stage rows.
- [Proof output](proof-output.md) — the English proof renderer, entity naming,
  and the display modes.
- [Glossary](glossary.md) — the terms these pages use, with the meaning they
  carry here.

## Related documentation

- [Getting started](../getting-started.md) — the first commands
- [Encoding reference](../encodings/README.md) — the logical formats
- [Architecture](../architecture/README.md) — how the pipeline behaves
- [Development](../development/README.md) — extending and testing
