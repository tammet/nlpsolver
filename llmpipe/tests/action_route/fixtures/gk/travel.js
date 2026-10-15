[
// travel.js -- two-leg travel.  Hand translation of:
//
//   S1  Ann is in Haapsalu.
//   S2  There is a bus service from Haapsalu to Tallinn.
//   S3  There is a ship service from Tallinn to Helsinki.
//   Q   How can Ann get to Helsinki?
//
// Stage 1 gives Ann the category person and the three cities the category
// place; "in" with a place-category object is read as located_at; a service
// is a usable directed route.  Model: one spatial scale, no tickets, no clock.
// Expected plan: bus Haapsalu -> Tallinn, then ship Tallinn -> Helsinki.

// S1  Ann is in Haapsalu.
{"@name": "entity_S1", "@logic": ["isa", "person", "#:Ann 1"]},
{"@name": "entity_S1", "@logic": ["isa", "place", "#:Haapsalu 2"]},
{"@name": "sent_S1", "@logic": ["is rel2", "located_at", "#:Ann 1", "#:Haapsalu 2", "s0", ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]]},
// S2  There is a bus service from Haapsalu to Tallinn.
{"@name": "entity_S2", "@logic": ["isa", "place", "#:Tallinn 3"]},
{"@name": "sent_S2", "@logic": ["connected", "#:Haapsalu 2", "#:Tallinn 3", "bus"]},
// S3  There is a ship service from Tallinn to Helsinki.
{"@name": "entity_S3", "@logic": ["isa", "place", "#:Helsinki 4"]},
{"@name": "sent_S3", "@logic": ["connected", "#:Tallinn 3", "#:Helsinki 4", "ship"]},

// distinct entities of the text (both orders; a compiler emits these from the "#:" ids)
{"@name": "differ", "@logic": ["differ", "#:Haapsalu 2", "#:Tallinn 3"]},
{"@name": "differ", "@logic": ["differ", "#:Haapsalu 2", "#:Helsinki 4"]},
{"@name": "differ", "@logic": ["differ", "#:Tallinn 3", "#:Haapsalu 2"]},
{"@name": "differ", "@logic": ["differ", "#:Tallinn 3", "#:Helsinki 4"]},
{"@name": "differ", "@logic": ["differ", "#:Helsinki 4", "#:Haapsalu 2"]},
{"@name": "differ", "@logic": ["differ", "#:Helsinki 4", "#:Tallinn 3"]},

// plan depth bound: up to three actions, in the text's context
{"@name": "reach0", "@logic": ["reachable", "s0", ["s", ["s", ["s", "0"]]], ["$ctxt", "present", "W0", "?:Fv3", "?:Fv4"]]},

// Q   How can Ann get to Helsinki?
{"@name": "sent_Q", "@logic": [
  ["-reachable", "?:S", "?:N", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["-is rel2", "located_at", "#:Ann 1", "#:Helsinki 4", "?:S", ["$ctxt", "present", "W0", "?:L", "?:K"]],
  ["$defq0", "?:S"]]},
{"@name": "sent_Q", "@question": ["$defq0", "?:S"], "@askvars": 1}
]
