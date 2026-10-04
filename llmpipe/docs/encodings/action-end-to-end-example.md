# Action end-to-end example

One text carried through every layer of the action route: English, Stage 1,
Stage 2, the source clauses, the query, the GK input, the GK answer, the replay
and the answer. The output comes from this command with the default provider
(`gemini`):

```bash
python3 solver/solve.py -details "Ann is in Haapsalu. There is a bus route from Haapsalu to Tallinn. How can Ann get to Tallinn?"
```

## The choice of route

The text has no `-actions` or `-noactions` key, so the classifier
`route_classify.classify` reads it. It finds two strong signs: a question
"How can ...?" and a route between two places. The text goes to the action
route:

```text
=== pipeline ===

  action route (chosen automatically: a question "How can ...?"; a route or service between places)
```

## Stage 1

Each sentence gets its units. The question has the reading `plan_question`.
The entities keep their Stage-1 categories.

```json
[{"raw": "Ann is in Haapsalu.",
  "units": [{"unit_id": "S1", "text": "Ann 1 is in Haapsalu 2.", "type": "situation",
             "entities": [{"id": "Ann 1", "type": "concrete", "category": "person"},
                          {"id": "Haapsalu 2", "type": "concrete", "category": "place"}],
             "pre_state": "W0"}]},
 {"raw": "There is a bus route from Haapsalu to Tallinn.",
  "units": [{"unit_id": "S2", "text": "There is a bus route from Haapsalu 2 to Tallinn 3.", "type": "real",
             "entities": [{"id": "bus route", "type": "generic"},
                          {"id": "Haapsalu 2", "type": "concrete", "category": "place"},
                          {"id": "Tallinn 3", "type": "concrete", "category": "place"}],
             "pre_state": "W0", "confidence": 0.99}]},
 {"raw": "How can Ann get to Tallinn?",
  "units": [{"unit_id": "S3", "text": "How can Ann 1 get to Tallinn 3?", "type": "query",
             "entities": [{"id": "Ann 1", "type": "concrete", "category": "person"},
                          {"id": "Tallinn 3", "type": "concrete", "category": "place"}],
             "action_reading": "plan_question"}]}]
```

The entities also carry `url` fields. The Stage-2 request leaves them out.

## Stage 2

The model returned the whole envelope, and the controller found nothing to
correct or derive. The `-details` output prints only the fields that are not
empty, here `{"worlds": ["W0"]}`. A person in a city is `located_at`; a public
route is a `connected` fact; the question is a `plan` package.

```json
{"worlds": ["W0"], "contexts": {}, "query_contexts": {},
 "logic": ["and",
   ["@id", "S1", ["holds", "W0", ["is rel2", "located_at", "Ann 1", "Haapsalu 2"]]],
   ["@id", "S2", ["holds", "W0", ["connected", "Haapsalu 2", "Tallinn 3", "bus"]]],
   ["@id", "S3", ["plan", ["is rel2", "located_at", "Ann 1", "Tallinn 3"]]]]}
```

The 0.99 of the article in S2 is the Stage-1 convention for "a". The action
route gives it no `@p`, because the text states no probability.

## The source clauses

`action_route.compile_source` compiles S1 and S2. The `-details` output shows
the clauses of each sentence with their role:

```text
Ann is in Haapsalu.
  initial fact           is_rel2(located_at,ann,haapsalu,$ctxt(present,w0))
  static type            isa(person,ann)
There is a bus route from Haapsalu to Tallinn.
  static                 connected(haapsalu,tallinn,bus)
[generated: distinct]
  distinct               differ(ann,haapsalu)
  ...
```

The type `isa(person, Ann 1)` comes from the person convention: Stage 1 gives
Ann the category `person`, and no sentence states otherwise. The `differ`
facts list the six ordered pairs of the three concrete ids.

## The query

`action_route.compile_query` compiles S3. The planning root is `W0`, the only
world. A plan question takes the discovery view. The search depth is the
default cap, four steps.

```text
=== query S3 (plan) ===

  goal: is_rel2(located_at,ann,tallinn)
  root W0; view discovery; search depth 4
  obligation plan (discovery, positive): located_at(Ann 1,Tallinn 3,?:Sit)
```

## The GK input

One launch answers the discovery question. Its input holds the source clauses,
the library clauses of the discovery view, the ordinary view, the seed and the
question:

```json
{"@name": "src:S1:initial_fact:0", "@logic": [["is rel2", "located_at", "#:Ann 1", "#:Haapsalu 2", ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]]]}
{"@name": "src:S2:static:1", "@logic": [["connected", "#:Haapsalu 2", "#:Tallinn 3", "bus"]]}
{"@name": "src:source:distinct:2", "@logic": [["differ", "#:Ann 1", "#:Haapsalu 2"]]}
...
{"@name": "src:types:static_type:8", "@logic": [["isa", "person", "#:Ann 1"]]}
{"@name": "query:S3:seed", "@logic": ["reachable", "W0", ["s", ["s", ["s", ["s", "0"]]]]]}
{"@name": "query:S3:plan:positive:definition:0", "@sourcetype": "question", "@logic": [["-reachable", "?:Sit", "?:N"], ["-is rel2", "located_at", "#:Ann 1", "#:Tallinn 3", ["$ctxt", "present", "?:Sit", "?:Qv1", "?:Qv2"]], ["$defq0", "?:Sit"]]}
{"@name": "query:S3:plan:positive", "@question": ["$defq0", "?:Sit"], "@askvars": 1}
```

The 50 library clauses and the two `V1-core` clauses complete the input. The
`-details` output replaces them with one comment line that counts them as 52
laws, and `-debug` prints them.

## The GK answer

GK accepts one answer. Its `$ans` term is the plan: one move from the root
`W0`. GK also lists six rejected answers, longer move chains with confidence
0, which never support a plan.

```json
"answer": [["$ans", ["$do", ["move", "#:Ann 1", "#:Haapsalu 2", "#:Tallinn 3", "bus"], "W0"]]],
"confidence": 1.0000
```

The proof uses the effect `eff_move_at`, the default `poss_move_person`, the
default hook `ok_move_default`, the search step `reach_step` and the helper
`standard_mode_bus`. The default is blocked if the text denies the move
(`$block` on `execution_denied`); the text has no denial. The plan applies no
frame, so the confidence is 1.0.

## The replay and the answer

The answer policy replays the candidate from the source units. Ann is a
person at Haapsalu, a bus connects Haapsalu and Tallinn, and the bus is a
standard means, so the move is executable. After it, Ann is at Tallinn: the
goal holds.

This is the output with `-explain`; `-details` adds the action term under
each plan step and the GK proof steps:

```text
Plan: Ann goes from Haapsalu to Tallinn by bus.

Explained:

Sentences used:
  (1) Ann is in Haapsalu.
  (2) There is a bus route from Haapsalu to Tallinn.
  (3) How can Ann get to Tallinn?
Laws used:
  eff_move_at (effect)
  poss_move_person (applicability default)
  ok_move_default (hook default)
  reach_step (reachability)
  standard_mode_bus (static helper)
Plan steps (each checked by replay):
  (1) Ann goes from Haapsalu to Tallinn by bus.
Replay: valid: every step executable, every state consistent, the goal holds.
```

With `-summary`, the run reports one block:

```text
answer: Plan: Ann goes from Haapsalu to Tallinn by bus.
pipeline: action route (chosen automatically: a question "How can ...?"; a route or service between places)
outcome: plan_found   replay: valid   confidence: 1.0
llm calls: stage1 1 (live 0); stage2 1 (live 0); total 2, live 0
gk launches: 1 (discovery:positive 1); 0.31 s
```

## Related pages

- [Action prompt interface](action-prompts.md) — Stage 1 and Stage 2
- [Action clauses](action-clauses.md) — the clauses and the query questions
- [Action library](action-library.md) — the laws that the proof used
- [Proof search and answers](../architecture/action-answers.md) — the launch, the policy and the replay
- [End-to-end example](end-to-end-example.md) — the same walk through the ordinary pipeline
