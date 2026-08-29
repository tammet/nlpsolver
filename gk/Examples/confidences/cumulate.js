// Two distinct sources support the same ground fact. Their disjoint evidence
// combines by noisy-or: 1 - (1 - 0.5)(1 - 0.6) = 0.8.
[
  {"@name": "a1", "@confidence": 0.5,
   "@logic": ["bird", "a"]},
  {"@name": "a2", "@confidence": 0.6,
   "@logic": ["bird", "a"]},
  {"@name": "q", "@question": ["bird", "a"]}
]
