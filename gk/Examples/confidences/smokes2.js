// Variant of the social-smoking network using explicit negative smoking in
// the rule body.
[
  {"@confidence": 0.3, "@logic": ["smokes", "?:X"]},
  {"@confidence": 0.1, "@logic": ["friends", "?:X", "?:Y"]},
  {"@confidence": 0.9,
   "@logic": [["friends", "?:X", "?:Y"], "=>",
              ["friends", "?:Y", "?:X"]]},
  {"@confidence": 0.6, "@logic": ["nonconformist", "?:X"]},
  {"@confidence": 0.2,
   "@logic": [[
      ["nonconformist", "?:X"], "&",
      ["friends", "?:X", "?:Y"], "&",
      ["-smokes", "?:Y"]
    ], "=>", ["smokes", "?:X"]]},
  {"@logic": ["friends", "chris", "sam"]},
  {"@logic": ["smokes", "chris"]},
  {"@question": ["smokes", "sam"]}
]
