# llmpipe documentation

`llmpipe` answers questions about an English passage. It translates the
passage and question into extended first-order logic, including defeasible
rules and probabilistic confidence annotations. It then asks the GK reasoner
whether the answer or its explicit negation follows and can present the
resulting proof in English.

A result may be `True.`, `False.`, `Unknown.`, a qualified answer such as
`Probably true.`, or the name of an entity. `Unknown.` means that the pipeline
found no proof of either side. It is a normal result, not necessarily an
error.

## How a question is processed

The ordinary path is:

```text
English passage and question
    -> Stage 1: identify the statements and their parts
    -> Stage 2: translate them into extended first-order logic
    -> compile the logic into GK clauses
    -> search for a proof with GK
    -> return the answer and, when requested, its proof
```

Stage 1 and Stage 2 use the selected language model. Logic compilation and
proof search are deterministic.

Before proof search, the compiler may replace two recurring logical patterns
with shorter equivalent forms. The replacements are checked and remain
connected to the ordinary predicates. See
[Proof shortening](architecture/proof-shortening.md).

## What happens when the first attempt finds no proof

The default `balanced` pipeline tries several independent ways of recovering a
proof, stopping at the first definite answer:

1. **Normalization fallback:** compile the same translation again with
   additional token and representation normalization. This does not call a
   language model.
2. **Conditional-question fallback:** for a conditional question, assume its
   antecedent in a separate theory and ask whether the consequent follows.
   This does not call a language model.
3. **Critic retranslation:** ask a model to identify a blocking translation
   problem and, when necessary, retranslate the affected material.
4. **Graph retranslation:** translate the case separately into a simpler
   open-relation graph representation and submit that theory to GK.

If every attempt finds no proof, the final result is `Unknown.`. A later
attempt never replaces an earlier definite answer. See
[Pipeline architecture](architecture/pipeline.md) for the exact stage order,
stopping rules, and available configurations.

## Where to go next

- To install and run the system, see [Getting started](getting-started.md).
- To follow one passage through every representation, see the
  [end-to-end example](encodings/end-to-end-example.md).
- To understand the logic formats, see the
  [Encoding reference](encodings/README.md). It covers every representation
  the pipeline can submit to GK, not only the ordinary one.
- To find a command-line option, see the
  [Command-line reference](reference/command-line.md).
- To understand the implementation, start with
  [Pipeline architecture](architecture/pipeline.md) and the
  [Code guide](code/README.md).
- To examine optional and previously tested mechanisms, see
  [Mechanism experiments](mechanisms/README.md).

Each documentation area has its own README with an annotated list of its
pages:

- [Architecture](architecture/README.md) — algorithms and processing order
- [Encodings](encodings/README.md) — normative logical forms
- [Reference](reference/README.md) — commands, configuration, records, output
- [Code](code/README.md) — implementation map
- [Development](development/README.md) — extension, testing, generated data
- [Mechanisms](mechanisms/README.md) — experimental evidence and decisions
