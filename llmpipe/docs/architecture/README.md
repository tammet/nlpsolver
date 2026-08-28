# Architecture

How the pipeline operates: what each stage does, when it runs, what it hands to
the next one, and why the order is what it is.

Read these pages when you want to understand the system's behaviour. They
explain algorithms and the decisions behind them. They do not define exact
logical forms — that is the [encoding reference](../encodings/README.md) — and
they do not say which module holds which function, which is the
[code guide](../code/README.md). The evidence behind a design choice is in
[mechanism experiments](../mechanisms/README.md).

A run does four things in order: translate the passage into logic, compile that
logic into clauses, search for a proof, and, when no proof is found, try again
with a different translation. The pages below follow that order.

## Reading order

New to the system: [Pipeline](pipeline.md), then [Translation](translation.md),
then [Logic compilation](logic-compilation.md), then
[Reasoning and proofs](reasoning-and-proofs.md). Those four cover an ordinary
successful run.

Then [Retries and retranslation](retries.md) for what happens after `Unknown.`,
and [Proof shortening](proof-shortening.md) for the two rewrites the canonical
theory applies by default.

Proof shortening and graph retranslation are part of the default pipeline.
The broader abstraction forms, graph bridges, and literal bridges are optional;
skip those sections until you need to study or enable them.

## Pages

**The ordinary path**

- [Pipeline](pipeline.md) — the stage order, the named configurations, the
  stopping rules, and what a run records.
- [Translation](translation.md) — the two model calls, the prompts, the sanity
  checks, the corrective retries, and the alternative parsing shapes.
- [Logic compilation](logic-compilation.md) — the deterministic sequence from a
  validated Stage-2 package to the clause list.
- [Compilation transformations](compilation-transformations.md) — the catalogue
  of the 45 named rewrites and injected clause families.
- [Questions, confidence, and answers](questions-confidence-and-answers.md) —
  how a question becomes a query, how confidence travels, how an answer is
  rendered.
- [Reasoning and proofs](reasoning-and-proofs.md) — the GK call, answer
  selection, proof sources, and English rendering.

**After `Unknown.`**

- [Retries and retranslation](retries.md) — the six stages that may run, in
  order, and what each costs.

**Representations**

- [Proof shortening](proof-shortening.md) — the two reversible rewrites the
  canonical theory attempts by default.
- [Abstraction](abstraction.md) — the optional representations that lose or add
  distinctions, and the machinery that resolves them.
- [Graph representation](graph-representation.md) — the second, open-triple
  translation and the bridge generation built on it.
- [Literal bridges](literal-bridges.md) — the optional mechanism that invents
  rules over the case's own atoms.

## Related documentation

- [Encoding reference](../encodings/README.md) — the exact logical forms
- [Code guide](../code/README.md) — where each of these is implemented
- [Reference](../reference/README.md) — options, configuration, records
- [Mechanism experiments](../mechanisms/README.md) — the evidence
