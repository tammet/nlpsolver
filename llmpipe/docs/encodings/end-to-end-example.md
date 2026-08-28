# End-to-end example

One passage carried through every layer: English, Stage 1, Stage 2,
the GK clause list, and the answer.

**Input:** "Elephants are animals. John is an elephant. Is John an animal?"

## Stage 1 Output

```json
[
  {"raw": "Elephants are animals.",
   "units": [{"unit_id": "S1", "text": "Elephants are animals.",
              "type": "strict_rule",
              "entities": [{"id":"elephants","type":"generic","category":"animal"},
                           {"id":"animals","type":"generic","category":"animal"}]}]},
  {"raw": "John is an elephant.",
   "units": [{"unit_id": "S2", "text": "John 1 is an elephant.",
              "type": "situation",
              "entities": [{"id":"John 1","type":"concrete","category":"person"}]}]},
  {"raw": "Is John an animal?",
   "units": [{"unit_id": "S3", "text": "Is John 1 an animal?",
              "type": "query",
              "entities": [{"id":"John 1","type":"concrete","category":"person"}]}]}
]
```

## Stage 2 Output

```json
["and",
  ["@id","S1", ["holds","W0",
    ["forall","X", ["implies", ["isa","elephant","X"], ["isa","animal","X"]]]]],
  ["@id","S2", ["holds","W0", ["isa","elephant","John 1"]]],
  ["@id","S3", ["question", ["isa","animal","John 1"]]]
]
```

## GK Input (after logconvert)

```json
[
// Elephants are animals.
{"@logic": [["-isa","elephant","?:X"], ["isa","animal","?:X"]],
 "@name": "sent_S1"},
// John 1 is an elephant.
{"@logic": ["isa","elephant","John 1"],
 "@name": "sent_S2"},
// Is John 1 an animal?
{"@logic": [["-$defq0"], ["isa","animal","John 1"]],
 "@name": "sent_S3"},
{"@logic": [["-isa","animal","John 1"], ["$defq0"]],
 "@name": "sent_S3"},
// [population facts]
{"@logic": ["-isa","elephant","$some_not_elephant"],
 "@name": "sent_S1"},
{"@logic": ["isa","animal","$some_animal"],
 "@name": "sent_S1"},
{"@logic": ["-isa","animal","$some_not_animal"],
 "@name": "sent_S1"},
// Is John 1 an animal?
{"@question": ["$defq0"],
 "@name": "sent_S3"}
]
```

## Answer

```
True.
```

The prover derives `isa(animal, John 1)` from the rule
(`isa(elephant,X) => isa(animal,X)`) and the fact (`isa(elephant, John 1)`),
which satisfies the `$defq0` biconditional, confirming the answer.

---

## Related documentation

- [Encoding reference index](README.md)
- [Getting started](../getting-started.md)
