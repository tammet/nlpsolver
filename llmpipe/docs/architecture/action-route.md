# The action route

The action route answers texts about actions and plans: "How can Ann get to
Tallinn?", "After the hand takes block b, is block a clear?". It is
experimental. It has its own translation, compiler and prover profile. It
shares the model calls, the LLM cache and the output levels with the ordinary
pipeline, and it runs none of the ordinary retry stages.

## When it runs

Each call chooses its pipeline first. `-actions` sends every text to the action
route and `-noactions` sends every text to the ordinary pipeline. Without
either key, a classifier reads the text, with no model call. A strong sign of
actions or plans, such as a question "How can ...?" or a bus route between two
places, sends the text to the action route. Every other text goes to the
ordinary pipeline. The [experimental options](../reference/experimental-options.md#the-action-route)
list the signs.

## The steps

**1. Translation.** Two model calls translate the text: Stage 1 marks each
sentence with its action reading (a permission, a restriction, an effect, a
plan question, ...), and Stage 2 writes the logic. The prompts are the action
prompts (`prompts/actions/`). A controller checks each response. When it finds
errors, it sends the response back with the errors, at most twice per stage.
A translation makes at most six logical model calls, and one more when the
accepted Stage 2 holds class conditions that the text does not state. The
controller also normalizes and repairs what the text itself decides, and
records each change; the [action prompt interface](../encodings/action-prompts.md)
lists these repairs (K1 to K16). A request that the route does not model ends
here with `Cannot answer`. [Action translation](action-translation.md)
describes the controller.

**2. Source compilation.** The source sentences become a source artifact. The
compiler checks the structure and the law form of each unit, gives every state
fact its situation, and then runs the passes of the physical profile:
permissions and denials, restrictions, effects, and the policy for computed
properties. A unit outside the supported fragment makes the source
unsupported, with its reason. [Action compilation](action-compilation.md)
describes the passes, and the [action clauses](../encodings/action-clauses.md)
and the [action library](../encodings/action-library.md) define their
output.

**3. Query compilation.** The question becomes a query artifact. It holds the
clauses the prover input needs (the view), the prover questions (the
obligations), and the prover capabilities the question needs. A yes-no
obligation has a positive and a negative question, because one prover launch
answers one polarity.

**4. Proof search.** GK runs once per obligation and polarity, with the
action library and the planning strategy. A plan question asks for a
reachable situation; GK reports the action sequence as an answer term.

**5. Decision and replay.** The answer policy reads every launch. An
independent replay checks each candidate plan and each supplied sequence
against the source laws, without the compiled clauses. A plan is accepted only
when the replay validates it. GK's yes or no on a sequence also needs the
replay's own verdict at the same place.

**6. Answer text.** Each question kind and outcome has one fixed answer form,
for example `Plan: Ann goes from Haapsalu to Tallinn by bus.`, `No plan found.`
or `Cannot answer: <reason>`. The
[experimental options](../reference/experimental-options.md#the-action-route)
list the forms.

[Proof search and answers](action-answers.md) describes steps 4 to 6.
The [action end-to-end example](../encodings/action-end-to-end-example.md)
follows one plan question through all six steps.

The output levels (`-explain`, `-logic`, `-details`, `-debug`) show these
steps; the [experimental options](../reference/experimental-options.md#output-of-the-action-route)
describe what each level prints.

## Limits

The route stops with a typed outcome when a question needs a capability the
prover does not have: a negative fact kept across an action, an object that
moves with its holder, or places inside places. Two prover behaviours give
wrong results that the route cannot detect yet. A frame axiom can block a
negative answer only under the hypothesis of the question, so GK may accept a
wrong negative answer after a conditional effect. GK also counts the evidence
of one uncertain rule once per use in a proof, so a plan can get too low a
confidence. A plan search that ends at GK's time limit is inconclusive: `No
plan found.` never means that no plan exists.

## Related pages

- [Action translation](action-translation.md) — the controller of the two model calls
- [Action compilation](action-compilation.md) — the source passes and the query compilation
- [Proof search and answers](action-answers.md) — the GK launches, the answer policy, the replay and the answer text
- [Action route modules](../code/action-route.md) — which module does each step
- [Action prompt interface](../encodings/action-prompts.md) — the readings, the
  Stage-2 envelope and the controller's repairs
- [Action clauses](../encodings/action-clauses.md),
  [action library](../encodings/action-library.md) and
  [action artifacts](../encodings/action-artifacts.md) — the formats
- [Experimental options](../reference/experimental-options.md#the-action-route)
  — the keys, the answer forms and the output levels
