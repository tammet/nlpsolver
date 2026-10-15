[
// food.js -- a three-step recipe on one ingredient.  Hand translation of:
//
//   S1  Ann has an egg, a whisk and a pan.
//   S2  Ann can break the egg.
//   S3  If the egg is broken, Ann can whisk it with the whisk.
//   S4  If the egg is whisked, Ann can cook it in the pan.
//   Q   How can Ann get the egg cooked?
//
// Verbs map to change(A, X, RESULT, TOOL): break -> broken with no named
// tool, whisk with the whisk -> whisked, cook in the pan -> cooked.  "With
// the whisk" and "in the pan" name the instrument; the recipe reading adds
// possession of the instrument to the capability's conditions (the same
// instrument-to-possession bridge as axioms_std.js section 5e).  S2 is about
// a named subject and compiles as stated (strict); S3 and S4 are rules whose
// condition and conclusion share the situation.  Model: the egg's properties
// change; nothing is created, consumed or heated.
// Expected plan: break, whisk, cook.

// S1  Ann has an egg, a whisk and a pan.
{"@name": "entity_S1", "@logic": ["isa", "person", "#:Ann 1"]},
{"@name": "entity_S1", "@logic": ["isa", "egg", "#:egg 2"]},
{"@name": "entity_S1", "@logic": ["isa", "whisk", "#:whisk 3"]},
{"@name": "entity_S1", "@logic": ["isa", "pan", "#:pan 4"]},
{"@name": "sent_S1", "@logic": ["have", "#:Ann 1", "#:egg 2", "s0", ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]]},
{"@name": "sent_S1", "@logic": ["have", "#:Ann 1", "#:whisk 3", "s0", ["$ctxt", "present", "W0", "?:Fv3", "?:Fv4"]]},
{"@name": "sent_S1", "@logic": ["have", "#:Ann 1", "#:pan 4", "s0", ["$ctxt", "present", "W0", "?:Fv5", "?:Fv6"]]},
// S2  Ann can break the egg.
{"@name": "sent_S2", "@logic": ["can", "#:Ann 1", ["change", "#:Ann 1", "#:egg 2", "broken", "unspecified"], "?:S", "?:C"]},
// S3  If the egg is broken, Ann can whisk it with the whisk.
{"@name": "sent_S3", "@logic": [["-has property", "broken", "#:egg 2", "?:S", "?:C"], ["-have", "#:Ann 1", "#:whisk 3", "?:S", "?:C"],
  ["can", "#:Ann 1", ["change", "#:Ann 1", "#:egg 2", "whisked", "#:whisk 3"], "?:S", "?:C"]]},
// S4  If the egg is whisked, Ann can cook it in the pan.
{"@name": "sent_S4", "@logic": [["-has property", "whisked", "#:egg 2", "?:S", "?:C"], ["-have", "#:Ann 1", "#:pan 4", "?:S", "?:C"],
  ["can", "#:Ann 1", ["change", "#:Ann 1", "#:egg 2", "cooked", "#:pan 4"], "?:S", "?:C"]]},

// plan depth bound: up to three actions
{"@name": "reach0", "@logic": ["reachable", "s0", ["s", ["s", ["s", "0"]]], ["$ctxt", "present", "W0", "?:Fv7", "?:Fv8"]]},

// Q   How can Ann get the egg cooked?
{"@name": "sent_Q", "@logic": [
  ["-reachable", "?:S", "?:N", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["-has property", "cooked", "#:egg 2", "?:S", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["$defq0", "?:S"]]},
{"@name": "sent_Q", "@question": ["$defq0", "?:S"], "@askvars": 1}
]
