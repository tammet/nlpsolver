// Social-smoking network adapted from Buchman and Poole,
// "Negation Without Negation in Probabilistic Logic Programming".
[
  {"@confidence": 0.3, "@logic": ["smokes", "?:X"]},
  {"@confidence": 0.1, "@logic": ["friends", "?:X", "?:Y"]},
  {"@confidence": 0.9,
   "@logic": [["friends", "?:X", "?:Y"], "=>",
              ["friends", "?:Y", "?:X"]]},
  {"@confidence": 0.6, "@logic": ["susceptible", "?:X"]},
  {"@confidence": 0.2,
   "@logic": [[
      ["susceptible", "?:X"], "&",
      ["friends", "?:X", "?:Y"], "&",
      ["smokes", "?:Y"]
    ], "=>", ["smokes", "?:X"]]},
  {"@logic": ["friends", "chris", "sam"]},
  {"@logic": ["smokes", "chris"]},
  {"@question": ["smokes", "sam"]}
]
