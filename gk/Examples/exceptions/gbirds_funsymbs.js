// The two recursive rules generate an unbounded sequence of function terms.
// GK can answer the ground query without constructing the complete sequence.
[
  ["bird", "b1"],
  ["penguin", "p1"],
  [["penguin", "?:X"], "=>", ["bird", "?:X"]],
  [["-bird", "?:X"], ["flies", "?:X"],
   ["$block", 3, ["$not", ["flies", "?:X"]]]],
  [["penguin", "?:X"], "=>", ["-flies", "?:X"]],
  [["penguin", "?:X"], "=>", ["penguin", ["f", "?:X"]]],
  [["bird", "?:X"], "=>", ["bird", ["f", "?:X"]]],
  {"@question": ["flies", "b1"]}
]
