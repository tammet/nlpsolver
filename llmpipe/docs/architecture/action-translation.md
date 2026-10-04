# Action translation

The action route translates a text with two model calls, as the ordinary
pipeline does, but with its own prompts and its own checks. A controller,
`action_pipeline.translate`, sends each stage, checks the response and asks
for a correction when it finds errors. This page describes the order of those
steps. The [action prompt interface](../encodings/action-prompts.md) defines
what the two stages write and lists each repair of the controller.

## The prompts

`action_prompt.assemble` builds one system prompt per stage. Each prompt is the
ordinary instructions, examples and checklist of its stage, then the action
instructions, the action examples and the action checklist
([prompt map](../code/prompt-map.md#used-by-the-action-route)). The user
message of a Stage-1 request is the text. The user message of a Stage-2
request is the accepted Stage-1 packages as JSON, without the entities' `url`
fields.

Every model call goes through `llmcall.call_llm` with the tag `actions`. The
shared LLM cache, the call limit, the per-call deadline and the call log
therefore apply. A response that the provider cut at its output limit stays
out of the cache.

## The budget

| limit | value | constant |
|---|---|---|
| corrections per stage | 2 | `MAX_CORRECTIONS` |
| logical calls per translation | 6 | `MAX_LOGICAL_CALLS` |
| extra calls for the class-condition request | 1 | `SEMANTIC_CORRECTIONS` |
| messages in a Stage-2 correction that joins check errors and compiler errors | 12 | `MAX_MESSAGES` |

A logical call is one request of the controller, from the cache or from the
provider. A correction that would repeat an earlier request of the same stage
is not sent: the cache would return the same response. The record then has
the stop reason `repeated_request`.

## Stage 1

1. The controller sends the text and reads the JSON response
   (`action_json.parse_response`, below).
2. `action_prompt.validate_units` checks the annotations: the readings, the
   actions and their roles, the step bound, the order of a supplied sequence,
   the context records and the query selections.
3. The `raw` sentences of the packages must cover the text exactly.
4. Two ids with the same index and head noun are one entity (repair K9) when
   all of these hold: the later name is exactly the head noun of the earlier
   name, the earlier name has more than one word, no entity with another index
   has that head noun, and the later sentence says "the <name>". Otherwise the
   controller asks for a correction.
5. `action_prompt.select_route` reads the annotations of the whole text and
   records `route_selected`: `actions`, `ordinary`, `diagnostic` or `invalid`.
   A `diagnostic` selection, from an `action_issue` of Stage 1, ends the
   translation with `unsupported_translation`. Any other valid selection goes
   on to the action Stage 2: the selection is a record, not a second choice of
   pipeline.

When a step finds errors, the controller sends the text again with a
correction: the previous response, its errors, and the errors of earlier
attempts that this response no longer has. After two failed corrections the
translation ends with `translation_invalid`.

## Stage 2

The controller checks each Stage-2 response in three steps
(`action_pipeline.stage2_attempt`):

1. **Normalization.** The controller parses the response, then derives or
   replaces what Stage 1 already decides: the envelope fields `worlds`,
   `contexts` and `query_contexts`, the `@p` of each source package, the
   typing cleanups, `located_at` for a person at a place, and the recorded
   repairs K5 to K10 and K16. Each change is recorded: a replaced value with
   the model's value, a derived envelope field by its name, a dropped wrapper
   by its unit.
2. **Checks.** Every Stage-1 unit must have its package. The handoff check
   compares each package with its Stage-1 unit: the query form against the
   reading, the step bound, and for a supplied sequence the order and the
   participants of each step against the Stage-1 actions and their roles. For
   a law it checks the placement of `normally` and of class atoms. A later
   mention of an action whose value differs from its one permission gets a
   message (K13).
3. **Compilation.** When every unit has its package, the compiler runs beside
   these checks, so one correction request names every independent error. The
   compiler checks that each law's reading fits its form, and it adjusts a
   reading that the sentence and the form decide (K1, K2, K11). A law reading
   that Stage 2 wrote as an ordinary event first gets one correction per unit
   (`reading_form_mismatch`). When the compiler reports a form that the route
   does not model and the response has no other error, the translation ends
   with `unsupported_translation` and the reason: unsupported meaning is
   reported, not corrected. A response with other errors gets a correction
   first.

A Stage-2 correction joins the check errors and the compiler's errors, at most
12 messages. A Stage-1 correction lists all its errors.

A response with errors gets a correction request, as in Stage 1. Two further
requests apply to Stage 2:

- **Focused request (K14).** When a correction returned the same response, the
  next request quotes only the failing packages. The packages of the reply
  replace the failing ones in the previous response.
- **Clarification (K15).** When every unsupported reason is
  `method_collision` or `unsupported_law_form`, and a correction attempt
  remains, the controller sends one request that explains the outcome. The
  reply is used only when it is a valid, supported translation that changes no
  more than the diagnosis allows: result labels that a sentence of the text
  states, in the units that the diagnosis names or in the query, or the
  arrangement of a law in a unit with `unsupported_law_form`. The worlds, the
  contexts, the selections, the types and the list of units must stay the
  same. Otherwise the unsupported outcome stands.

## After an accepted Stage 2

The controller compares each class condition on a concrete entity in a rule's
condition with the rule's own sentence
(`action_prompt.class_condition_findings`). A class word only inside an entity
id states nothing. A finding has the confidence `high` when the class word
does not occur in the rule's text outside entity ids, and `ambiguous`
otherwise; an ambiguous finding is recorded and not sent. For the high
findings the controller sends one more Stage-2 request that lists those
conditions. It asks to remove
each one, or to move it to the envelope field `types` when it is the class of
a referent that the sentence introduces. The controller uses the reply only
when it equals the accepted translation with exactly those changes. Otherwise
the accepted translation stands with its findings.

Each checked response is compiled while it is checked: the query packages
are kept apart from the source packages, and the source is compiled. The
translation record takes the source artifact of the accepted response. The
route then compiles the query against it again for the proof search
([action compilation](action-compilation.md)). The English route accepts at
most one question sentence.

## Reading a JSON response

`action_json.parse_response` reads a model response in this order, and records
each repair:

1. the text without a code fence;
2. a rebuilt final run of closing brackets, when the text before it is intact
   JSON that ends with a value (`terminal_delimiters`);
3. the ordinary `llmparse.fix_json`;
4. each `["@id", ID, PACKAGE]` package closed at its own end, with the surplus
   closing brackets between packages dropped (`package_delimiters`);
5. surplus closing brackets before a field of the envelope dropped
   (`envelope_delimiters`).

A response that the provider stopped at its output limit is not repaired. Nor
is a provider response without a stop reason, which may be cut off. A failure
reports the error position in the model's own JSON.

## The translation record

| field | content |
|---|---|
| `status` | `ok`, `call_limit`, `model_timeout`, `model_error`, `translation_invalid` or `unsupported_translation` |
| `bundle` | the name, status and prompt hashes of the prompt bundle |
| `stage1_units`, `stage1_packages` | the accepted Stage-1 units and packages |
| `route_selected`, `route_reasons` | the route selection; when the compiler adjusted a reading, computed again from the adjusted readings, with the Stage-1 selection kept in `route_selection_stage1` |
| `stage2` | the accepted packages, worlds, contexts and types |
| `history` | every request: stage, attempt, the SHA-256 of the user message, the raw response, the finish reason, whether it was cached, the parse steps, the errors and the normalizations |
| `normalizations` | what the controller derived, replaced or removed in the accepted Stage 2 |
| `class_condition_findings`, `semantic_correction` | the findings after Stage 2 and the result of the one request about them |
| `unsupported`, `errors` | the reasons of an unsupported translation, and the errors of a failed one |

## Formal input

With `-formal`, the input is a JSON record of units and queries in the field
names of the gold fixtures ([experimental options](../reference/experimental-options.md#the-action-route)).
No model is called. The record goes directly to the compiler.

## Related pages

- [The action route](action-route.md) — the steps after translation
- [Action prompt interface](../encodings/action-prompts.md) — the Stage-1 and Stage-2 formats and the repairs K1 to K16
- [Translation](translation.md) — the ordinary two-stage translation
