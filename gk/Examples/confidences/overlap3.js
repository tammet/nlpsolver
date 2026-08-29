[
{"@name":"fa", "@confidence": 0.9, "@logic": ["fa","x"]},
{"@name":"fb", "@confidence": 0.8, "@logic": ["fb","x"]},
{"@name":"f1", "@confidence": 0.95, "@logic": ["f1","x"]},
{"@name":"f3", "@confidence": 0.85, "@logic": ["f3","x"]},
{"@name":"ra", "@logic": ["forall", ["X"], [[["fa","X"], "&", ["f1","X"]], "=>", ["g","X"]]]},
{"@name":"rb", "@logic": ["forall", ["X"], [[["fa","X"], "&", ["fb","X"]], "=>", ["g","X"]]]},
{"@name":"rc", "@logic": ["forall", ["X"], [[["fb","X"], "&", ["f3","X"]], "=>", ["g","X"]]]},
{"@question": ["g","x"]}
]
