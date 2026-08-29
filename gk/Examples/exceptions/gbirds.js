// A bird flies by default; penguins are explicitly non-flying birds.
[
  ["bird", "b1"],
  ["penguin", "p1"],
  [["penguin", "?:X"], "=>", ["bird", "?:X"]],
  [["-bird", "?:X"], ["flies", "?:X"],
   ["$block", 3, ["$not", ["flies", "?:X"]]]],
  [["penguin", "?:X"], "=>", ["-flies", "?:X"]],
  {"@question": ["flies", "b1"]}
]

/*
Equivalent ASP rules for comparison:

bird(b1).
penguin(p1).
bird(X) :- penguin(X).
flies(X) :- bird(X), not -flies(X).
-flies(X) :- penguin(X).
*/
