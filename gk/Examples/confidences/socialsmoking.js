// Expanded form of the first social-smoking network. The expected confidence
// of smokes(sam) is 0.3764 under the provenance-aware retained-proof calculation.
[
  {"@confidence": 0.3, "@logic": ["smokes", "?:X"]},
  {"@confidence": 0.1, "@logic": ["friends", "?:X", "?:Y"]},
  {"@confidence": 0.9,
   "@logic": [["friends", "?:X", "?:Y"], "=>",
              ["friends", "?:Y", "?:X"]]},
  {"@confidence": 0.6, "@logic": ["susceptible", "?:X"]},
  {"@confidence": 0.2,
   "@logic": [[
      ["smokes", "?:Y"], "&",
      ["friends", "?:X", "?:Y"], "&",
      ["susceptible", "?:X"]
    ], "=>", ["smokes", "?:X"]]},
  {"@logic": ["friends", "chris", "sam"]},
  {"@logic": ["smokes", "chris"]},
  {"@question": ["smokes", "sam"]}
]
