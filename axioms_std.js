// gk_axiomfile.js
// 
// a tiny world model used for regression testing

[
 
  [["-isa", "thing", "?:Y"],["isa", "object", "?:Y"]],
  [["-isa", "object", "?:Y"],["isa", "thing", "?:Y"]],

  [["-sclass","?:Y1","?:Y2"],["-rel2_of","part","?:X","?:Y1","?:CT"],["-rel2_of","part","?:X","?:Y2","?:CT"]],
  [["-isa","?:Y1","?:Y2"],["-rel2_of","part","?:X","?:Y1","?:CT"],["-rel2_of","part","?:X","?:Y2","?:CT"]],

  [["-rel2_of","part","?:X","?:Y","?:CT"],["rel2","have","?:Y","?:X","?:CT"]],

  [["-prop","?:W","?:X",3,"?:C", "?:CT"],["prop","?:W","?:X","$generic","?:C", "?:CT"]],
  [["-prop","?:W","?:X",1,"?:C", "?:CT"],["prop","?:W","?:X","$generic","?:C", "?:CT"]],
  [["-prop","?:W","?:X",1,"?:C", "?:CT"],["-prop","?:W","?:X",3,"?:C", "?:CT"]],

  [["-rel2_of","?:W","?:X","?:Y", "?:CT"], ["isa","?:W","?:X"]], 

  [["-isa","?:X","?:Y"], ["prop","?:X","?:Y","$generic","$generic", "?:CT"]], 
  [["-rel2_of","have","?:X",["of","?:Y","?:X"], "?:CT"], ["isa","?:Y",["of","?:Y","?:X"]]],

  [["-rel2_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-rel2_than","?:R","?:Y","?:Z","?:A2", "?:CT"],
   ["rel2_than","?:R","?:X","?:Z","?:A3", "?:CT"]],

  [["-rel2_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-rel2_than","?:R","?:Y","?:X","?:A2", "?:CT"]],

  [["-rel2_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-prop","?:R","?:Y","?:Z","?:C", "?:CT"],
   ["prop","?:R","?:X","?:Z","?:C", "?:CT"]],

  
  [["-rel2","in","?:X","?:Y", "?:CT"], ["-rel2","in","?:Y","?:Z", "?:CT"],
   ["rel2","in","?:X","?:Z", "?:CT"]], 


  [["-do1","?:W","?:X","?:Z", "?:CT"], ["can1","?:W","?:X","?:Z", "?:CT"]],  
  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["can2","?:W","?:X","?:Y","?:Z", "?:CT"]],
  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["can1","?:W","?:X","?:Z", "?:CT"]],

  [["-act2","?:W","?:X","?:Y","?:Z", "?:CT"], ["act1","?:W","?:X","?:Z", "?:CT"]],

  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["do1","?:W","?:X","?:Z", "?:CT"]],

  {"@logic": [["do1","?:W","?:X","?:Z", "?:CT"], ["-can1","?:W","?:X","?:Z", "?:CT"]], "@confidence": 0.15},  
  {"@logic": [["do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["-can2","?:W","?:X","?:Y","?:Z", "?:CT"]], "@confidence": 0.15},

  [["-rel2_of","make","?:X","?:Y","?:I", "?:CT"], ["-do2","?:A","?:Y","?:Z","?:I2", "?:CT"], ["do2","?:A","?:X","?:Z","?:I2", "?:CT"]],
  [["-rel2_of","make","?:X","?:Y","?:I", "?:CT"], ["do2","?:A","?:Y","?:Z","?:I2", "?:CT"], ["-do2","?:A","?:X","?:Z","?:I2", "?:CT"]],
  

  {"@logic": [["-prop", "?:X", "?:Y", "?:Z", "$generic", "?:CT"],["-isa", "?:U", "?:Y"],["prop", "?:X", "?:Y", "?:Z", "?:U", "?:CT"],
              ["$block",0,["$not",["prop", "?:X", "?:Y", "?:Z", "?:U", "?:CT"]]]],
   "@confidence": 0.8},

  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof","?:X1","?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof","?:X2","?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof","?:X1","?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof","?:X2","?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof","?:X3","?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof",["and","?:X1","?:X3"],"?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof",["and","?:X2","?:X3"],"?:Y1"]],"?:N"]],
  [ ["=","?:N",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]]], "=>", ["$greatereq",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]],"?:N"]],


  {"@confidence":0.99, "@logic": [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 1]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]]]]]}, 
  
  {"@confidence":0.99,"@logic": [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 3]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 3]]]]]}, 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 1]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]]]]], 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 3]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 3]]]]],  
  
  // added two new persistence

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 1]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 1]]]]], 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 3]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]]]]], 

  // end of added persistence 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Past", 1]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Pres", 2]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Pres", 2]]]]],  
  
  
  [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 1]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 1]],
   ["$block",1,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 1]]]]], 

  [["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 2]],["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]],
   ["$block",2,["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]]]], 

  [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 2]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]],
   ["$block",1,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]]]]], 

  [["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 3]],["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 3]],
   ["$block",2,["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 3]]]],  

  [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 4]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 4]],
   ["$block",1,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 4]]]]], 

  [["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 4]],["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 4]],
   ["$block",2,["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 4]]]],   
  
  
  [["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 1]],
   ["-act2","eat","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 2]] ],

  [
   ["-act2","take","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 2]] ], 

  [["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 2]],
   ["-act2","eat","?:Z","?:X","?:I",["$ctxt", "?:T", 2]],
   ["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 3]] ],

  [
   ["-act2","take","?:Z","?:X","?:I",["$ctxt", "?:T", 2]],
   ["-rel2","on","?:X","?:Y",["$ctxt", "?:T", 3]] ],  

  [
   ["-act2","put","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","on","?:I","?:N",["$ctxt", "?:T", 1]],
   ["rel2","on","?:X","?:N",["$ctxt", "?:T", 2]] ], 


  {"@logic": ["or", ["rel2","where","?:X","?:Y","?:Z"], ["-rel2","in","?:X","?:Y","?:Z"]]},  
  {"@logic": ["or", ["rel2","where","?:X","?:Y","?:Z"], ["-rel2","on","?:X","?:Y","?:Z"]]},   
  {"@logic": ["or", ["rel2","where","?:X","?:Y","?:Z"], ["-rel2","at","?:X","?:Y","?:Z"]]},  
  {"@logic": ["or", ["rel2","where","?:X","?:Y","?:Z"], ["-rel2","under","?:X","?:Y","?:Z"]]},  
  {"@logic": ["or", ["rel2","where","?:X","?:Y","?:Z"], ["-rel2","over","?:X","?:Y","?:Z"]]},

  ["isa","meter",["$measure1","?:W","?:O","meter","?:C"]], // the unit X of the measure is X
  ["isa","dollar",["$measure1","?:W","?:O","dollar","?:C"]],
  ["isa","ton",["$measure1","?:W","?:O","ton","?:C"]],
  ["isa","color",["$theof1","color","?:O","?:C"]], // the color of an object is a color
  ["isa","weight",["$theof1","weight","?:O","?:C"]],
  ["isa","price",["$theof1","price","?:O","?:C"]],

  //  axioms for babi

  [
  ["-act1","go","?:S","?:A",["$ctxt","?:T","?:F"]], 
  ["-rel2","to","?:A","?:D",["$ctxt","?:T","?:F"]], 
  ["rel2","at","?:S","?:D",["$ctxt","?:T",["$afteract",["act1","go","?:S","?:A","?:F"],"?:F"]]]
  ],

  [
  ["-act1","go","?:S","?:A",["$ctxt","?:T","?:F"]], 
  ["-rel2","from","?:A","?:D",["$ctxt","?:T","?:F"]], 
  ["-rel2","at","?:S","?:D",["$ctxt","?:T",["$afteract",["act1","go","?:S","?:A","?:F"],"?:F"]]]
  ],

  {"@logic":  [
      ["-rel2", "at", "?:S","?:D", ["$ctxt", "Past", "?:F1"]],
      ["rel2", "at", "?:S","?:D", ["$ctxt", "Pres", "?:F2"]],
      ["$block",0,["$not",["rel2", "at", "?:S","?:D", ["$ctxt", "Pres", "?:F2"]]]]
    ],
    "@confidence": 0.85},

  {"@logic":  [
      ["rel2", "at", "?:S","?:D", ["$ctxt", "Past", "?:F1"]],
      ["-rel2", "at", "?:S","?:D", ["$ctxt", "Pres", "?:F2"]],
      ["$block",0,["rel2", "at", "?:S","?:D", ["$ctxt", "Pres", "?:F2"]]]
    ],
    "@confidence": 0.85},  

    [
      ["-act1","travel","?:S","?:A",["$ctxt","?:T","?:F"]], 
      ["act1","go","?:S","?:A",["$ctxt","?:T","?:F"]]      
    ],
    [
      ["-act1","journey","?:S","?:A",["$ctxt","?:T","?:F"]], 
      ["act1","go","?:S","?:A",["$ctxt","?:T","?:F"]]      
    ],
    [
      ["-act1","move","?:S","?:A",["$ctxt","?:T","?:F"]], 
      ["act1","go","?:S","?:A",["$ctxt","?:T","?:F"]]      
    ],

  // taking and putting stuff away
  /*
  {"@logic":  ["or",
    ["-act2", "take", "?:S","?:O","?:A",["$ctxt", "Past", "?:F1"]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Past", ["$afteract",["act2","take","?:S","?:O","?:A","?:F1"],"?:F1"]]] //,
    //["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F2"]]]]
  ],
  "@confidence": 0.85},

  {"@logic":  ["or",
    ["-act2", "discard", "?:S","?:O","?:A",["$ctxt", "Past", "?:F1"]],
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "Past", ["$afteract",["act2","discard","?:S","?:O","?:A","?:F1"],"?:F1"]]] //,
    //["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F2"]]]]
  ],
  "@confidence": 0.85},
 */
  {"@logic":  ["or",   
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F1"]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]], //,
    ["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]]]]
  ],
  "@confidence": 0.85},

  // - nrs
  
  {"@logic":  ["or",
    ["-act2", "take", "?:S","?:O","?:A",["$ctxt", "Past", 1]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Past", 2]], //,
    ["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", 2]]]]
  ],
  "@confidence": 0.85},
  
  {"@logic":  ["or",
    ["-act2", "take", "?:S","?:O","?:A",["$ctxt", "Past", 2]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Past", 3]], //,
    ["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", 3]]]]
  ],
  "@confidence": 0.85},
 
  {"@logic":  ["or",
    ["-act2", "discard", "?:S","?:O","?:A",["$ctxt", "?:T", 1]],
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "?:T", 2]] //,
    //["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F2"]]]]
  ],
  "@confidence": 0.85},

  {"@logic":  ["or",
    ["-act2", "discard", "?:S","?:O","?:A",["$ctxt", "?:T", 2]],
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "?:T", 3]] //,
    //["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F2"]]]]
  ],
  "@confidence": 0.85},

  {"@logic":  ["or",   
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F1"]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]], //,
    ["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]]]]
  ],
  "@confidence": 0.85},

  {"@logic":  ["or",   
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F1"]],
    ["-rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]], //,
    ["$block",0,["rel2", "have", "?:S","?:O", ["$ctxt", "Pres", "?:F2"]]]
  ],
  "@confidence": 0.85}
  

  /*
  {"@logic":  ["or",
    ["-act2", "take", "?:S","?:O","?:A",["$ctxt", "Past", 1]],
    ["rel2", "have", "?:S","?:O", ["$ctxt", "Past", 2]] //,
    //["$block",0,["$not",["rel2", "have", "?:S","?:O", ["$ctxt", "Past", "?:F2"]]]]
  ],
  "@confidence": 0.85}
  */
  // if smth has the color property (like the color of smth is red) X, then it has a property X (like is red)  
  //[["-prop","?:X",["$theof1","color","?:O","?:C"],"?:U","?:W","?:C"],
  // ["prop","?:X","?:O","$generic","$generic","?:C"]]
  // inverse holds for real colors  ???
  // [["prop","red",["$theof1","color","?:O","?:C"],"?:U","?:W","?:C"],
  //  ["-prop","red","?:O","$generic","$generic","?:C"]] 

  /* 
  {"@logic": ["or",  ["-$greater","?:X","?:Y"], ["-$greater","?:Y","?:Z"], ["$greater","?:X","?:Z"]]},
  {"@logic": ["or",  ["-$less","?:X","?:Y"], ["-$less","?:Y","?:Z"], ["$less","?:X","?:Z"]]},  
  
  {"@logic": ["or",  ["-$greater","?:X","?:Y"], ["$less","?:Z","?:Y"]]},
  {"@logic": ["or",  ["$greater","?:X","?:Y"], ["-$less","?:Z","?:Y"]]}
  */
]