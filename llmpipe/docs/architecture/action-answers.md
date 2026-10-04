# Proof search and answers

After compilation, the action route runs GK once per question, decides the
answer from all launches together, and checks every plan with an independent
replay. Three modules do this work:

- `action_gk` runs the launches and reads their output into typed evidence.
  It decides no answer.
- `action_answer` decides the answer from the evidence and the replay.
- `action_replay` executes a plan or a supplied sequence step by step from the
  source units, without GK and without the compiled clauses.

`action_english` writes the answer text.

## Proof search

### The backend

The adapter runs only a registered GK build (`action_gk.BACKENDS`). The default
build `gk` is the installed prover `../gk/gk` (GK 1.0.11), with the planning
strategy and the pipeline's parameters. Like the ordinary pipeline, the adapter
does not check which binary is at the path. It records the binary's SHA-256 in
each evidence record:

| item | value |
|---|---|
| strategy | `{"strategy": ["query_focus"], "query_preference": 1, "equality": 0, "weight_select_ratio": 20, "weight_blocker_const": 2, "weight_ctxt_const": 1}` (`PLANNING_STRATEGY`) |
| parameters | `-taxonomy -confidence 0.1 -keepconfidence 0.1`, then `-datafolder`, `-detail`, `-outformat json` |
| time per launch | 30 seconds (`DEFAULT_SECONDS`), or `-seconds`; an external limit of 15 seconds more |
| validated capabilities | none |

The command holds the profile's strategy and parameters and nothing else. It
reads no ordinary pipeline option, no axiom file and no proof cache. Launches
run one at a time: a lock file serializes them across processes.

Before any launch, `run_query` checks, in this order, and launches nothing when
one applies:

| outcome | when |
|---|---|
| the query's own outcome | compilation decided it |
| `backend_unavailable` | the binary is missing or cannot be executed, or the data folder is missing |
| `unsupported_backend_requirement` | a requirement is unmet and its policy is to refuse |
| `call_limit` | the worst-case launch count exceeds the launch limit |

A capability counts as validated only through a record that names the hash of
the binary at the path, the library identity and the strategy's hash. The caller's own
declaration does not count.

### Launches

| query | questions |
|---|---|
| `question` | positive and negative |
| `ask` | positive |
| `verify` with no steps | the final formula, positive and negative, at the root |
| `verify` with steps | each step and the final formula, positive and negative; the joint positive question |
| `plan`, `reachable` | the discovery question, positive |

A launch that completed with an empty `answers` list runs once more with
`-printlevel 12`, to read GK's termination line. A timeout, an error or a
malformed output gets no relaunch. The termination reason of a launch is
`proof`, `search_limit`, `undetermined`, `timeout` or `error`; it is
`not_diagnosed` when relaunches are off, `diagnostic_error` when the relaunch
fails, and `diagnostic_differs` when the relaunch finds an answer that the
launch did not. `search_limit` and the three diagnostic reasons are
inconclusive. The relaunch never replaces the launch's result.

### Reading the output

| status | when |
|---|---|
| `completed` | a result object whose result string agrees with its lists |
| `launch_failed` | the process could not start |
| `prover_timeout` | the external limit expired |
| `prover_error` | an error object, or a nonzero exit without a result object |
| `backend_incompatible` | GK reports an unknown strategy setting: the build did not run the registered strategy |
| `malformed` | no result object with exit 0, truncated JSON, lists of the wrong type, an unknown result string, or a result string that contradicts its lists |

Only an entry of GK's `answers` list can support an answer. An entry of
`rejected_answers` never does, whatever its confidence. An accepted entry is a
candidate unless one of these holds:

| reason | the entry |
|---|---|
| `malformed_confidence` | has a confidence that is not a finite number in [0, 1] |
| `below_cutoff` | has a confidence below 0.10 |
| `contrary_verdict` | is `false`: GK proved the contrary of the question; the other polarity has its own question |
| `disjunctive_answer` | holds two or more `$ans` literals |
| `malformed_answer` | has no `$ans` literal or too few terms |
| `not_ground` | reports a variable |
| `not_rooted` | is a situation not built on the planning root |
| `unrecognized_action` | holds a term that is not one of the five constructors with its arity |
| `nonegative_run` | comes from a `-nonegative` launch, which gives candidates only |

A question without reported variables is a Boolean: every accepted entry is
the same answer, so it gives one candidate. A question with reported variables
gives one candidate per distinct binding. Distinct plans and distinct
witnesses stay distinct. A candidate's confidence is the largest confidence
of its entries.

### Experimental confidence

Each accepted entry has the status `validated` unless its proof shows one of
these, and then `experimental`:

| reason | the proof |
|---|---|
| `uncertain_evidence_reused` | uses two or more clauses of one uncertain source unit, or one such clause more than once |
| `shared_source_confidence_unmet` | uses a clause of a unit that the query's unmet `shared_source_confidence` requirement lists |
| `provenance_unchecked` | has no proof steps |

GK counts the evidence of an uncertain clause once per use in a proof, while
one application of a rule should count once. The label marks such a number.
The answer itself stays a candidate.

## The answer policy

`action_answer.decide` reads the evidence record. Before any answer, the
replay checks the starting state at the planning root. A conflict there gives
`inconsistent_action_state`, for every query kind.

### One Boolean obligation

| verdict | when |
|---|---|
| `error` | a launch did not complete |
| `contested` | both launches have a candidate, or a launch has an entry with conflict mass and proofs in both directions |
| `Yes` / `No` | only the positive / only the negative launch has a candidate |
| `Unknown` | neither; the record names an inconclusive termination of a launch |

### Snapshot questions

A `question` and a `verify` with no steps answer from the paired verdict,
with the outcome `verification_result`. An `ask` has only a positive launch:
it answers with the entities of its candidates, or Unknown when it has none. A snapshot view has no effect or frame clause, so the
replay is not needed.

### A supplied sequence

| answer | when |
|---|---|
| Yes | every step and the final formula are Yes, the joint question has a candidate, and the replay validates the sequence and the final state |
| No | the first step that is not Yes is No, or every step is Yes and the final formula is No; the replay validates the steps before it and reads No at the same place |
| contested | the first step that is not Yes, or the final formula, is contested |
| Unknown | the first step that is not Yes is Unknown; every step is Yes and the final formula is Unknown; every step and the final formula are Yes but the joint question has no candidate; or a Yes or No that the replay does not confirm |

The replay must confirm a No. GK can prove a wrong negative through a frame
after a conditional effect (below), and the replay computes that state without
frames. A result that the replay does not confirm names the disagreement:
`replay_disagrees`, `replay_not_checked` or `prefix_not_validated`.

When only the negative question of the final formula needs a negative fact
kept across an action, a Yes stands. Every other answer becomes
`unsupported_backend_requirement`, and the prover's reading stays in the
diagnostics.

### Discovery

The policy replays the candidates of the plan launch in GK's order, with the
goal's reported witnesses and the step bound, until one is valid:

- a valid candidate gives `plan_found`, or `goal_already_holds` for the empty
  plan;
- candidates that all fail give `candidate_not_validated`, with each verdict;
- no candidate gives `not_found`.

`not_found` is a bounded result: GK found no plan within its search limit and
the depth. It never shows that no plan exists. A plan question then answers
`No plan found.`, and a reachable question `Unknown.`.

### Confidence

The result's confidence is the GK confidence of the answer used: the Boolean
candidate, the joint question of a Yes verification, or the plan candidate,
with the adapter's label. The record also splits the confidence into the part
of the frame clauses (0.99 per use) and the part of the probabilities that the
text states.

## The replay

`action_replay.replay` executes a sequence of actions from the planning root.
It reads the source units: the initial facts, the permissions, the denials, the
restrictions, the effects and the standing laws. It has its own transitions of
the five constructors. It does not read the compiled clauses or the library
file, so it checks the compiler and GK independently.

### State and values

A state is a set of signed ground facts: `is rel2`, `has property` and `have`.
An atom holds a positive sign, a negative sign, both, or none. A value is a
pair of supports, positive and negative:

| connective | positive support | negative support |
|---|---|---|
| `not A` | negative of A | positive of A |
| `A and B` | both positive | either negative |
| `A or B` | either positive | both negative |
| `A implies B` | as `not A or B` | as `not A or B` |
| `exists X` | some binding positive | every binding negative |
| `forall X` | every binding positive | some binding negative |

A missing fact is unknown: it satisfies neither a positive nor a negative
condition. A rule applies when its condition has positive support. An atom
with both signs is a contested premise. Each support records the contested
premises that it rests on. A plan whose steps and goal rest on a contested
premise is not validated (`not_checked`).

### A step

An action is executable when some sufficient path holds and no explicit
negative support exists:

- **paths:** the library defaults, and each permission of the text whose
  action unifies, completed with its constructor's template;
- **restrictions:** every restriction of the constructor must be met, by a
  match whose required condition holds, or by a proved nonmatch;
- **defaults:** a library default and a `normally` permission are blocked by
  an explicit denial of the same action whose condition holds;
- **negative support:** a denial whose condition holds, or a restriction whose
  required condition is false.

A false or unknown step makes the sequence invalid. A step with both supports
makes it contested.

The transition applies the library writes of the constructor and the writes
of the text's effects together, from the old state. An effect writes when its
condition has positive support. An unknown condition leaves the atoms that
the effect may write unknown. Every other stored fact keeps its signs, so a
negative fact persists. A computed property is computed again in every state.

### Invariants

The replay checks the starting state and the state after every step:

- a hand holds two different objects;
- a hand is holding something and is empty;
- a block with something on it has a clear top;
- an object has two different direct supports;
- an object supports itself, or the supports form a cycle;
- one entity is at two places of the declared flat set.

A violation is `inconsistent_action_state`, with its facts.

### Outside the replay

The replay gives `not_checked` for a source outside its fragment: a `normally`
or an `or` in a description, a standing law that is not
`forall(implies(body, fluent))`, an action term outside the five constructors,
or a location that a holder's move left stale. It never raises: an internal
failure gives `not_checked` with the uncovered component `replay_error`
(K12). It computes no confidence and does not
check the English.

## Answer text

`action_english.answer_text` gives one form per question kind and outcome:

| question | outcome | answer text |
|---|---|---|
| plan | `plan_found` | `Plan: <plan sentence>.` |
| plan | `goal_already_holds` | `No action is needed.` |
| plan | `not_found` | `No plan found.` |
| reachable | `plan_found` | `Yes. Plan: <plan sentence>.` |
| reachable | `goal_already_holds` | `Yes. No action is needed.` |
| reachable | `not_found` | `Unknown.` |
| question, verify | `verification_result` | `Yes.`, `No.`, `Unknown.` or `Contested.` |
| ask | `verification_result` | the entities by name: `The key.`, `The key and the cup.`; `Unknown.` without a candidate |
| any | `inconsistent_action_state` | `Inconsistent: <facts in English>.` |
| any | `candidate_not_validated` | `Unknown: no candidate plan was validated.` |
| any | `unsupported_translation`, `unsupported_backend_requirement` | `Cannot answer: <sentence>. [<reason codes>; <units>]` |
| any | a failed run | `Error: <outcome>: <detail>` |

`Cannot answer` means that the route read the text and does not model it. Its
sentence comes from `action_english.REASON_SENTENCES`: one sentence per reason
code, which says what the route read. `Error` means that the run gave no
answer: every outcome outside the answered outcomes and the two `Cannot
answer` outcomes, such as an invalid translation, a call limit, a model
error, a timeout, a prover error, a missing or incompatible backend, or an
insufficient search allowance.

When the part of the confidence that comes from the text's own probabilities
is below 0.95 (`PROBABLY`), the answer says "Probably": `Probably yes.`,
`Probably no.`, `Probably yes. Plan: ...` or `Probable plan: ...`. The
threshold is a display convention, not a calibrated probability. The frame
part of the confidence does not count.

**The plan sentence.** The steps stand in execution order, joined by
", then". An entity keeps its proper name (`Ann`). A one-letter id gets its
class (`block a`), a witness its class (`the cook`), and any other name `the`
(`the egg`). A step leaves out its actor when the previous step has the same
actor. A move after a move by the same actor keeps only its endpoints and
means: `Ann goes from Haapsalu to Tallinn by bus, then from Tallinn to
Helsinki by ship`. A change step uses the verb of the permission that allows
it: `paints the cabin red`, `cooks the egg in the pan`. Without one such verb,
it says `X makes Y value`. `-explain` also prints the plan with one full
sentence per step.

## Known limits

| limit | what happens |
|---|---|
| a frame blocker under the question's hypothesis | after a conditional effect, GK can prove a negative fact by a reductio, because the frame's change marker needs the hypothesized state. The policy accepts a negative after a step only when the replay agrees |
| evidence counted per use | GK counts an uncertain rule once per use in a proof: a plan that applies a 0.6 rule twice gets 0.1296 where 0.36 is right. The confidence is labelled experimental |
| negative persistence | the library has no frame for a negative fact; such a query stops |
| transport | a held object does not move with its holder; such a query stops |
| nested places | places inside places need hierarchical updates; such a query stops |
| long plans | a four-step tower plan is not found within GK's search limit. The supplied tower sequence is verified |

## Related pages

- [The action route](action-route.md) — the steps and where they run
- [Action compilation](action-compilation.md) — the obligations that the launches answer
- [Action artifacts and records](../encodings/action-artifacts.md) — the evidence and result records
- [Experimental options](../reference/experimental-options.md#the-action-route) — the keys and the output levels
