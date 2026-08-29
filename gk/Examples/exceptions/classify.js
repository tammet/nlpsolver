[
  {"@logic": ["has_part", "h1", "leg"]},

  {"@logic": ["has_part", "b1", "leg"]},
  {"@logic": ["has_part", "b1", "wing"]},
  {"@logic": ["has_part", "b1", "feathers"]},

  {"@logic": ["has_part", "a1", "engine"]},
  {"@logic": ["has_part", "a1", "wing"]},

  {"@logic": [
      ["has_part", "?:X", "leg"], "=>",
      [["isa", "?:X", "human"], "|",
       ["$block", ["$", "human"], ["$not", ["isa", "?:X", "human"]]]]
    ], "@confidence": 30},
  {"@logic": [
      ["has_part", "?:X", "leg"], "=>",
      [["isa", "?:X", "bird"], "|",
       ["$block", ["$", "bird"], ["$not", ["isa", "?:X", "bird"]]]]
    ], "@confidence": 20},
  {"@logic": [
      ["has_part", "?:X", "wing"], "=>",
      [["isa", "?:X", "bird"], "|",
       ["$block", ["$", "bird"], ["$not", ["isa", "?:X", "bird"]]]]
    ], "@confidence": 60},
  {"@logic": [
      ["has_part", "?:X", "feathers"], "=>",
      [["isa", "?:X", "bird"], "|",
       ["$block", ["$", "bird"], ["$not", ["isa", "?:X", "bird"]]]]
    ], "@confidence": 80},
  {"@logic": [
      ["has_part", "?:X", "wing"], "=>",
      [["isa", "?:X", "airplane"], "|",
       ["$block", ["$", "airplane"], ["$not", ["isa", "?:X", "airplane"]]]]
    ], "@confidence": 40},

  {"@logic": [["has_part", "?:X", "engine"], "=>",
               ["-isa", "?:X", "organism"]]},
  {"@logic": [["isa", "?:X", "human"], "=>",
               ["isa", "?:X", "organism"]]},
  {"@logic": [["isa", "?:X", "bird"], "=>",
               ["isa", "?:X", "organism"]]},
  {"@logic": [["isa", "?:X", "airplane"], "=>",
               ["-isa", "?:X", "organism"]]},

  {"@question": ["isa", "?:X", "organism"]}
]
