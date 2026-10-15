[
// tower.js -- a three-block tower with one robot hand.  Hand translation of:
//
//   S1  There is a robot hand.
//   S2  Blocks a, b and c are on the table.
//   S3  Nothing is on top of any block.
//   S4  The hand is empty.
//   Q   How can the hand get b on a and c on b?
//
// Blocks model (assumptions of the library's take/put_on fragment, not of the
// sentences): one hand holding one object, one direct support per block, at
// most one block directly on a block, the table takes any number.
// Expected plan: take b, put b on a, take c, put c on b (two grasps, two put-downs).

// S1  There is a robot hand.
{"@name": "sent_S1", "@logic": ["isa", "hand", "#:hand 1"]},
// S2  the blocks and the table, from the entity categories
{"@name": "entity_S2", "@logic": ["isa", "block", "#:a 2"]},
{"@name": "entity_S2", "@logic": ["isa", "block", "#:b 3"]},
{"@name": "entity_S2", "@logic": ["isa", "block", "#:c 4"]},
{"@name": "entity_S2", "@logic": ["isa", "table", "#:table 5"]},
// S2  Blocks a, b and c are on the table.
{"@name": "sent_S2", "@logic": ["is rel2", "on", "#:a 2", "#:table 5", "s0", ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]]},
{"@name": "sent_S2", "@logic": ["is rel2", "on", "#:b 3", "#:table 5", "s0", ["$ctxt", "present", "W0", "?:Fv3", "?:Fv4"]]},
{"@name": "sent_S2", "@logic": ["is rel2", "on", "#:c 4", "#:table 5", "s0", ["$ctxt", "present", "W0", "?:Fv5", "?:Fv6"]]},
// S3  Nothing is on top of any block.
{"@name": "sent_S3", "@logic": ["has property", "clear_top", "#:a 2", "s0", ["$ctxt", "present", "W0", "?:Fv7", "?:Fv8"]]},
{"@name": "sent_S3", "@logic": ["has property", "clear_top", "#:b 3", "s0", ["$ctxt", "present", "W0", "?:Fv9", "?:Fv10"]]},
{"@name": "sent_S3", "@logic": ["has property", "clear_top", "#:c 4", "s0", ["$ctxt", "present", "W0", "?:Fv11", "?:Fv12"]]},
// S4  The hand is empty.
{"@name": "sent_S4", "@logic": ["has property", "empty", "#:hand 1", "s0", ["$ctxt", "present", "W0", "?:Fv13", "?:Fv14"]]},

// distinct entities of the text (both orders; a compiler emits these from the "#:" ids)
{"@name": "differ", "@logic": ["differ", "#:hand 1", "#:a 2"]},
{"@name": "differ", "@logic": ["differ", "#:hand 1", "#:b 3"]},
{"@name": "differ", "@logic": ["differ", "#:hand 1", "#:c 4"]},
{"@name": "differ", "@logic": ["differ", "#:hand 1", "#:table 5"]},
{"@name": "differ", "@logic": ["differ", "#:a 2", "#:hand 1"]},
{"@name": "differ", "@logic": ["differ", "#:a 2", "#:b 3"]},
{"@name": "differ", "@logic": ["differ", "#:a 2", "#:c 4"]},
{"@name": "differ", "@logic": ["differ", "#:a 2", "#:table 5"]},
{"@name": "differ", "@logic": ["differ", "#:b 3", "#:hand 1"]},
{"@name": "differ", "@logic": ["differ", "#:b 3", "#:a 2"]},
{"@name": "differ", "@logic": ["differ", "#:b 3", "#:c 4"]},
{"@name": "differ", "@logic": ["differ", "#:b 3", "#:table 5"]},
{"@name": "differ", "@logic": ["differ", "#:c 4", "#:hand 1"]},
{"@name": "differ", "@logic": ["differ", "#:c 4", "#:a 2"]},
{"@name": "differ", "@logic": ["differ", "#:c 4", "#:b 3"]},
{"@name": "differ", "@logic": ["differ", "#:c 4", "#:table 5"]},
{"@name": "differ", "@logic": ["differ", "#:table 5", "#:hand 1"]},
{"@name": "differ", "@logic": ["differ", "#:table 5", "#:a 2"]},
{"@name": "differ", "@logic": ["differ", "#:table 5", "#:b 3"]},
{"@name": "differ", "@logic": ["differ", "#:table 5", "#:c 4"]},

// plan depth bound: up to 4 actions
{"@name": "reach0", "@logic": ["reachable", "s0", ["s", ["s", ["s", ["s", "0"]]]], ["$ctxt", "present", "W0", "?:Fv15", "?:Fv16"]]},

// Q   How can the hand get b on a and c on b?
{"@name": "sent_Q", "@logic": [
  ["-reachable", "?:S", "?:N", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["-is rel2", "on", "#:b 3", "#:a 2", "?:S", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["-is rel2", "on", "#:c 4", "#:b 3", "?:S", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["$defq0", "?:S"]]},
{"@name": "sent_Q", "@question": ["$defq0", "?:S"], "@askvars": 1}
]
