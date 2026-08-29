// Stress and social influence provide two overlapping paths to smokes(carl).
// The expected confidence is 0.1376.
[
  {"@confidence": 0.8, "@logic": ["stress", "ann"]},
  {"@confidence": 0.4, "@logic": ["stress", "bob"]},
  {"@confidence": 0.6, "@logic": ["influences", "ann", "bob"]},
  {"@confidence": 0.2, "@logic": ["influences", "bob", "carl"]},
  {"@logic": [["stress", "?:X"], "=>", ["smokes", "?:X"]]},
  {"@logic": [[
      ["smokes", "?:Y"], "&",
      ["influences", "?:Y", "?:X"]
    ], "=>", ["smokes", "?:X"]]},
  {"@question": ["smokes", "carl"]}
]
