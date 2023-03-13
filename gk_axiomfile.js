// gk_axiomfile.js

[
  [["-isa", "thing", "?:Y"],["isa", "object", "?:Y"]],
  [["-isa", "object", "?:Y"],["isa", "thing", "?:Y"]],

  //[["-prop","abnormal","?:Y","?:Z","?:C"],["-prop","normal","?:Y","?:Z","?:C"]],
  //[["prop","abnormal","?:Y","?:Z","?:C"],["prop","normal","?:Y","?:Z","?:C"]],


  //[["-isa","?:X","?:Y"], ["-isa","?:Y","?:Z"], ["isa","?:X","?:Z"]], 

  [["-prop","?:W","?:X",3,"?:C", "?:CT"],["prop","?:W","?:X","$generic","?:C", "?:CT"]],
  [["-prop","?:W","?:X",1,"?:C", "?:CT"],["prop","?:W","?:X","$generic","?:C", "?:CT"]],
  [["-prop","?:W","?:X",1,"?:C", "?:CT"],["-prop","?:W","?:X",3,"?:C", "?:CT"]],

  [["-rel2_is_of","?:W","?:X","?:Y", "?:CT"], ["isa","?:W","?:X"]], 

  [["-isa","?:X","?:Y"], ["prop","?:X","?:Y","$generic","$generic", "?:CT"]], 
  [["-rel2_is_of","have","?:X",["of","?:Y","?:X"], "?:CT"], ["isa","?:Y",["of","?:Y","?:X"]]],

  [["-rel2_is_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-rel2_is_than","?:R","?:Y","?:Z","?:A2", "?:CT"],
   ["rel2_is_than","?:R","?:X","?:Z","?:A3", "?:CT"]],

  [["-rel2_is_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-rel2_is_than","?:R","?:Y","?:X","?:A2", "?:CT"]],

  [["-rel2_is_than","?:R","?:X","?:Y","?:A1", "?:CT"], ["-prop","?:R","?:Y","?:Z","?:C", "?:CT"],
   ["prop","?:R","?:X","?:Z","?:C", "?:CT"]],

  
  [["-rel2","is_in","?:X","?:Y", "?:CT"], ["-rel2","is_in","?:Y","?:Z", "?:CT"],
   ["rel2","is_in","?:X","?:Z", "?:CT"]], 

  [["-do1","?:W","?:X","?:Z", "?:CT"], ["can1","?:W","?:X","?:Z", "?:CT"]],  
  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["can2","?:W","?:X","?:Y","?:Z", "?:CT"]],
  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["can1","?:W","?:X","?:Z", "?:CT"]],

  [["-act2","?:W","?:X","?:Y","?:Z", "?:CT"], ["act1","?:W","?:X","?:Z", "?:CT"]],

  [["-do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["do1","?:W","?:X","?:Z", "?:CT"]],

  {"@logic": [["do1","?:W","?:X","?:Z", "?:CT"], ["-can1","?:W","?:X","?:Z", "?:CT"]], "@confidence": 0.15},  
  {"@logic": [["do2","?:W","?:X","?:Y","?:Z", "?:CT"], ["-can2","?:W","?:X","?:Y","?:Z", "?:CT"]], "@confidence": 0.15},

  //[["-rel2_is_of","make","?:X","?:Y","?:A"], ["isa","?:X","?:Y"]],
  [["-rel2_is_of","make","?:X","?:Y","?:I", "?:CT"], ["-do2","?:A","?:Y","?:Z","?:I2", "?:CT"], ["do2","?:A","?:X","?:Z","?:I2", "?:CT"]],
  [["-rel2_is_of","make","?:X","?:Y","?:I", "?:CT"], ["do2","?:A","?:Y","?:Z","?:I2", "?:CT"], ["-do2","?:A","?:X","?:Z","?:I2", "?:CT"]],
  
  /*
  {"@logic": [["-isa", "object", "?:X"], ["prop", "normal", "?:X", "?:Z", "$generic"],
                ["$block","object",["$not",["prop", "normal", "?:X", "?:Z", "$generic"]]]]},       
  */
 /*
  {"@logic": [["-isa", "object", "?:X"], ["prop", "normal", "?:X", "?:Z", "$generic"],
                ["$block","object",["prop", "abnormal", "?:X", "?:Z", "$generic"]]]},                     
  [["-prop", "normal", "?:X", "?:Z", "$generic"],["-prop", "abnormal", "?:X", "?:Z", "$generic"]],
  
  [["prop",  "normal", "?:X", "?:Z", "$generic"],["prop",  "abnormal", "?:X", "?:Z", "$generic"]],
  */

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
/*
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof","?:X1","?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof","?:X2","?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof","?:X1","?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof","?:X2","?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof","?:X3","?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof",["and","?:X1","?:X3"],"?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof",["and","?:X2","?:X3"],"?:Y1"]],"?:N"]],
  [ ["$greatereq",["$count",["$setof",["and","?:X1","?:X2","?:X3"],"?:Y1"]],"?:N"], "=>", ["$greatereq",["$count",["$setof",["and","?:X1","?:X2"],"?:Y1"]],"?:N"]]
*/
  /*
  [["-rel2_is_in","?:R","?:X","?:Y"], ["-rel2_is_","?:R","?:Y","?:Z"],
   ["rel2_is_than","?:R","?:X","?:Z"]]
  [["-rel2_is_than","?:R","?:X","?:Y"], ["-rel2_is_than","?:R","?:Y","?:Z"],
   ["rel2_is_than","?:R","?:X","?:Z"]] 
  [["-rel2_is_than","?:R","?:X","?:Y"], ["-rel2_is_than","?:R","?:Y","?:Z"],
   ["rel2_is_than","?:R","?:X","?:Z"]] 
  */ 
  //[["rel2","have","?:X",["of","?:Y","?:X"]], ["-isa","?:Y",["of","?:Y","?:X"]]]

  /*
  [["-isa", "?:X", "?:Y",  ["$ctxt", "?:T", 1]],["isa", "?:X", "?:Y", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["isa", "?:X", "?:Y", ["$ctxt", "?:T", 2]]]]],

  [["-isa", "?:X", "?:Y",  ["$ctxt", "Past", "?:F1"]],["isa", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2"]],
   ["$block",0,["$not",["isa", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2" ]]]]], 
  */

  {"@confidence":0.99, "@logic": [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 1]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]]]]]}, 
  
  {"@confidence":0.99,"@logic": [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 2]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 3]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", 3]]]]]}, 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 1]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]]]]], 

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 2]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 3]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "?:T", 3]]]]],  

  [["-prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Past", 1]],["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Pres", 2]],
   ["$block",0,["$not",["prop", "?:R", "?:X", "?:A", "?:B", ["$ctxt", "Pres", 2]]]]],  
  
  /*
  ["$less",1,2],
  [["-$less","?:X","?:Y"],["-$less","?:X",["$sum",1,"?:Y"]]],
  */
/*
   [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", "?:N1"]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", "?:N2"]],
   ["-$less", "?:N1",  "?:N2"],
   ["$block",2,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "?:T", "?:N2"]]]]], 
*/
  /*  
  [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", "?:F1"]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2"]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2"]]]]],  
  */
  /*
  [["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", 2]],["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", 2]]]]],  
  */

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
  
  /* 
  [["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Past", "?:F1"]],["-rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2"]],
   ["$block",0,["$not",["rel2", "?:R", "?:X", "?:Y", ["$ctxt", "Pres", "?:F2"]]]]],   
  */
  [["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 1]],
   ["-act2","eat","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 2]] ],

  [
   ["-act2","take","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 2]] ], 

  [["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 2]],
   ["-act2","eat","?:Z","?:X","?:I",["$ctxt", "?:T", 2]],
   ["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 3]] ],

  [
   ["-act2","take","?:Z","?:X","?:I",["$ctxt", "?:T", 2]],
   ["-rel2","is_on","?:X","?:Y",["$ctxt", "?:T", 3]] ],  

  [
   ["-act2","put","?:Z","?:X","?:I",["$ctxt", "?:T", 1]],
   ["-rel2","on","?:I","?:N",["$ctxt", "?:T", 1]],
   ["rel2","is_on","?:X","?:N",["$ctxt", "?:T", 2]] ] 


]