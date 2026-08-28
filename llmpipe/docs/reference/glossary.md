# Glossary

Terms used across this documentation, with the meaning they carry
here.

| term | meaning |
|---|---|
| Stage 1 | the first model call. It turns English into atomic semantic units. |
| Stage 2 | the second model call. It turns those units into extended first-order logic in JSON, including defeasible formulas and probabilistic confidence annotations. |
| canonical theory | the clause list produced from the ordinary Stage-2 output, with the two proof-shortening rewrites applied. |
| initial attempt | the first attempt: Stage 1, Stage 2, conversion, and one GK call. |
| fallback | a stage that reuses the same parse and calls GK again. It makes no model call. There are two: normalization and conditional question. |
| retranslation | a stage that builds a second translation of the same case. The critic and the graph route are the two. |
| abstraction | a converter setting that changes the logical form so that distinctions are lost or added, such as an event base or a preset. |
| proof shortening | a reversible converter rewrite that shortens the theory without changing what it says. There are two: reversible event compression (`davidson2`) and repeated part-witness compression (`existfold2`). |
| bridge | a mechanism that invents new clauses and adds them to a theory. The literal bridge and the graph bridge are the two. |
| definite answer | an answer other than `Unknown`, an empty value, or an `Error:` value. |
| Unknown | the prover found no proof within its limit. It is an answer the pipeline may return. |
| error | a run that produced no answer. It is never a definite answer and never a correct abstention. |
| proof source | a clause named by a proof step, written `["in", NAME, ...]`. |
| adapter | a clause connecting a compact representation to its canonical form, named `frm_*`. |
| package | one `@id` unit of a Stage-2 output. |
| unit | one atomic semantic unit from Stage 1, with an id such as `S3`. |
| checkpoint | a result read from one run's stage rows: initial attempt, conservative, or balanced. |


## Related documentation

- [Encoding reference](../encodings/README.md)
- [Pipeline](../architecture/pipeline.md)
- [Proof shortening](../architecture/proof-shortening.md)
- [Command-line reference](command-line.md)
