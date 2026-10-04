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


## Terms of the action route

| term | meaning |
|---|---|
| action route | the experimental pipeline for texts about actions and plans: its own prompts, compiler, GK profile, replay and answer forms. See [the action route](../architecture/action-route.md). |
| route choice | the decision, before Stage 1, between the action route and the ordinary pipeline: `-actions`, `-noactions`, `-formal`, or the text classifier. |
| action reading | the Stage-1 annotation of a unit's role: `availability`, `restriction`, `effect`, `occurrence`, or one of the four question readings. |
| constructor | one of the five action terms: `move`, `take`, `put_on`, `put_in`, `change`. |
| permission | a sufficient rule that an action is executable: `can` in Stage 2, `poss` in the clauses. Its reading is `availability`. |
| denial | a rule that an action is not executable: `not can` in Stage 2, the marker `execution_denied` in the clauses. |
| restriction | a necessary condition of an action: "only if", "unless", "requires". |
| effect | what holds after an action: `after(ACTION, ...)` in Stage 2. An effect grants no permission. |
| standing rule | a rule between states that holds at every situation: `state_law` in Stage 2. |
| world | a named state of the text: `W0`, `W1`, ... |
| situation | a world, or `$do(ACTION, S)`: the state after an action. |
| planning root | the world that starts every action history of a question. |
| frame | a library clause that keeps a stored fact across an action that did not write it. |
| marker | a `changed_*` fact that an action writes; it blocks the frame of the fact it changed. |
| obligation | one prover question of a query, with a positive and usually a negative launch. |
| view | the clause set of a query kind: `snapshot`, `verify` or `discovery`. |
| candidate | an accepted GK answer that may support a verdict or a plan. |
| replay | the independent execution of a plan or a supplied sequence from the source units, without GK. |
| backend requirement | a prover capability that a query needs, such as `negative_persistence`. |
| `Cannot answer` | the answer for a text that the route reads but does not model. It is not an error. |

## Related documentation

- [Encoding reference](../encodings/README.md)
- [Pipeline](../architecture/pipeline.md)
- [Proof shortening](../architecture/proof-shortening.md)
- [Command-line reference](command-line.md)
