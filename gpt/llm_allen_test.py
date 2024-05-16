# Allen proofwriter inpired tests used by the nlptest.py
# see https://proofwriter.apps.allenai.org/ 

[
   # Nails examples from and inspired by https://proofwriter.apps.allenai.org/ 

  ["""Metals conduct electricity. Insulators do not conduct electricity. If something is made of iron then it is metal. 
      Nails are made of iron. Nails conduct electricity?""", True],
  ["""Metals conduct electricity. Insulators do not conduct electricity. If something is made of iron then it is metal. 
      Nails are made of plastic. Plastic is an insulator. Nails conduct electricity?""", False],

   # Harry Potter examples from and inspired by https://proofwriter.apps.allenai.org/         

  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. Harry can do magic?""",True],
  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. Harry can vanish?""",True],  
  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. Mr Dursley can do magic?""",False],
  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. Mr Dursley can vanish?""",False],  
  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. Muggles can vanish?""",None],
   ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Mr Dursley is a Muggle. 
     Muggles are persons. Muggles can vanish?""",False],  
  ["""Harry can do magic. Muggles cannot do magic. If a person can do magic then they can vanish.
    If a person cannot do magic then they cannot vanish. Harry can vanish. Harry is a Muggle?""",False],
  

  # UK tax law: original plus modified versions, from  https://proofwriter.apps.allenai.org/

  ["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
    If someone has a UK civil service pension then they pay pension tax in the UK. 
    If someone is a UK resident then they pay pension tax in the UK. 
    If someone's home country is UK then they are a UK resident. 
    If someone's home country is France then they are a French resident. 
    John's home country is UK. 
    Pierre's home country is France. 
    Alan's home country is France. 
    Alan has a UK civil service pension. 
    Alan pays UK pension tax?""", True],

  ["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
    If someone has a UK civil service pension then they pay pension tax in the UK. 
    If someone is a UK resident then they pay pension tax in the UK. 
    If someone's home country is UK then they are a UK resident. 
    If someone's home country is France then they are a French resident. 
    John's home country is UK. 
    Pierre's home country is France. 
    Alan's home country is France. 
    Alan has a UK civil service pension. 
    Alan pays UK pension tax?""", True],

   # new

   ["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
    If someone has a UK civil service pension then they pay pension tax in the UK. 
    If someone is a UK resident then they pay pension tax in the UK. 
    If someone's home country is UK then they are a UK resident. 
    If someone's home country is France then they are a French resident. 
    John's home country is UK. 
    Pierre's home country is France. 
    Pierre is not a UK resident.    
    Alan's home country is France. 
    Alan has a UK civil service pension. 
    Pierre pays UK pension tax?""", None],  

  ["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
    If someone has a UK civil service pension then they pay pension tax in the UK. 
    If someone is a UK resident then they pay pension tax in the UK. 
    If someone's home country is UK then they are a UK resident. 
    If someone's home country is France then they are a French resident. 
    John's home country is UK. 
    Pierre's home country is France. 
    Alan's home country is France. 
    Alan has a UK civil service pension. 
    Alan pays pension tax in France?""",None],  

  ["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
    If someone has a UK civil service pension then they pay pension tax in the UK. 
    If someone is a UK resident then they pay pension tax in the UK. 
    If someone's home country is UK then they are a UK resident. 
    If someone's home country is France then they are a French resident. 
    John's home country is UK. 
    Pierre's home country is France. 
    Alan's home country is France. 
    Alan has a UK civil service pension. 
    Alan pays UK beard tax?""",None],

  #["""If someone is not a UK resident and they do not have a UK civil service pension then they do not pay UK pension tax. 
  # If someone has a UK civil service pension then they pay pension tax in the UK. 
  # If someone is a UK resident then they pay pension tax in the UK. 
  # If someone's home country is UK then they are a UK resident. 
  # If someone's home country is France then they are a French resident. 
  # John's home country is UK. 
  # Pierre's home country is France. 
  # Alan's home country is France. 
  # Alan has a UK civil service pension. 
  # Who is a French resident?""","Alan and Pierre"] # gets wrong: interprets "they" in the rule as a "country"
  
  # Ethical rules from https://proofwriter.apps.allenai.org/ 
  # ["""If you take something you shouldn't, then you are stealing.
  #  If you are stealing, then you are doing a bad thing.
  #  If you take something that doesn't belong to you, then you are taking something you shouldn't.
  #  John took a book that didn't belong to him. 
  #  John was doing a bad thing?""",True], # parsing goes wrong (reparandum)

   # original birds version from and inspired by https://proofwriter.apps.allenai.org/ 

  ["""Arthur is a bird. Arthur is not wounded. Bill is an ostrich. Colin is a bird. Colin is wounded. Dave is not an ostrich.
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is an ostrich then they are abnormal.
      If someone is an ostrich then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Colin can fly?""",False],
  ["""Arthur is a bird. Arthur is not wounded. Bill is an ostrich. Colin is a bird. Colin is wounded. Dave is not an ostrich.
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is an ostrich then they are abnormal.
      If someone is an ostrich then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Bill can fly?""",False],
  ["""Arthur is a bird. Arthur is not wounded. Bill is an ostrich. Colin is a bird. Colin is wounded. Dave is not an ostrich.
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is an ostrich then they are abnormal.
      If someone is an ostrich then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Arthur can fly?""",True],    

  # Modified bird examples from and inspired by https://proofwriter.apps.allenai.org/  
  # using abnormality and penguins instead of ostriches

  [""""Arthur is a bird. Arthur is not wounded. Bill is a penguin. Colin is a bird. Colin is wounded. Dave is not a penguin. 
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is a penguin then they are abnormal.
      If someone is a penguin then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Most objects are not abnormal. Arthur can fly?""",True],
  [""""Arthur is a bird. Arthur is not wounded. Bill is a penguin. Colin is a bird. Colin is wounded. Dave is not a penguin. 
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is a penguin then they are abnormal.
      If someone is a penguin then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Most objects are not abnormal. Bill can fly?""",False], 
  [""""Arthur is a bird. Arthur is not wounded. Bill is a penguin. Colin is a bird. Colin is wounded. Dave is not a penguin. 
      Dave is wounded. If someone is an ostrich then they are a bird. If someone is a penguin then they are abnormal.
      If someone is a penguin then they cannot fly. If someone is a bird and wounded then they are abnormal.
      If someone is wounded then they cannot fly. If someone is a bird and not abnormal then they can fly.
      Most objects are not abnormal. Colin can fly?""",False],    
 

  # Circuit examples from and inspired by https://proofwriter.apps.allenai.org/

  ["""The circuit has a switch. The circuit has a bell. The switch is on. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",True],

  ["""The circuit has a switch. The circuit has a bell. The switch is off. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",None],
   
  ["""The circuit does not have a switch. The circuit has a bell. The switch is off. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",True],

  ["""The circuit does not have a switch. The circuit has a bell.
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",True],

  ["""The circuit has a bell. The switch is on. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",True], # nice! has switch / does not have switch cover cases OK

  ["""The circuit has a bell. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The bell is ringing?""",None], # different from previous: switch stuff not given

  ["""The circuit has a switch. The circuit has a bell. The switch is on. 
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The light bulb is glowing?""",None],    

  ["""The circuit has a switch. The circuit has a bell. The switch is on. 
      The circuit has a light bulb.
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The light bulb is glowing or the radio is playing?""",True],   

  ["""The circuit has a switch. The circuit has a bell. The switch is on. 
      The circuit has a light bulb and a radio.
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      The light bulb is glowing and the radio is playing?""",True],

  ["""The circuit has a switch. The circuit has a bell. The switch is on. 
      The circuit has a light bulb and a radio.
      If the circuit has the switch and the switch is on then the circuit is complete.
      If the circuit does not have the switch then the circuit is complete. 
      If the circuit is complete and the circuit has the light bulb then the light bulb is glowing.
      If the circuit is complete and the circuit has the bell then the bell is ringing.
      If the circuit is complete and the circuit has the radio then the radio is playing. 
      A radio is playing?""",True],              

 

   # Fiona examples from and inspired by https://proofwriter.apps.allenai.org/

  ["""Fiona is round.
    All green things are rough.
    White things are not cold.
    If Fiona is rough and Fiona is furry then Fiona is not big.
    If Fiona is cold and Fiona is rough then Fiona is not furry.
    Round things are green.
    If something is round and furry then it is not big.
    All furry things are big.
    If something is round and not green then it is not big.
    Fiona is not big.
    Fiona is cold.
    Fiona is not furry?""",True],

  ["""Fiona is round.
    All green things are rough.
    White things are not cold.
    If Fiona is rough and Fiona is furry then Fiona is not big.
    If Fiona is cold and Fiona is rough then Fiona is not furry.
 
    If something is round and furry then it is not big.
    All furry things are big.
    If something is round and not green then it is not big.
    Fiona is not big.
    Fiona is cold.
    Fiona is not furry?""",True],  

  ["""Fiona is round.
    All green things are rough.
    White things are not cold.
    If Fiona is rough and Fiona is furry then Fiona is not big.
    If Fiona is cold and Fiona is rough then Fiona is not furry.
    Round things are green.
    If something is round and furry then it is not big.
    All furry things are big.
    If something is round and not green then it is not big.
    
    Fiona is cold.
    Fiona is not furry?""",True],  

  ["""Fiona is round.
    All green things are rough.
    White things are not cold.
    If Fiona is rough and Fiona is furry then Fiona is not big.
    If Fiona is cold and Fiona is rough then Fiona is not furry.
 
    If something is round and furry then it is not big.
    All furry things are big.
    If something is round and not green then it is not big.
    
    Fiona is cold.
    Fiona is big?""",None],

  # Bald eagle examples from and inspired by https://proofwriter.apps.allenai.org/

  ["""The bald eagle chases the bear.
    The bear needs the bald eagle.
    If something chases the bald eagle then they do not chase the bear.
    If something needs the bald eagle then the bald eagle eats the bear.
    If something needs the bear then the bear is red.
    If something eats the bear then they are cold.
    If something is cold then they are not kind.
    If something eats the bear and they are not cold then the bear is not round.
    The bald eagle is not kind?""",True],  

  ["""The bald eagle chases the bear.
    The bear needs the bald eagle.
    If something chases the bald eagle then they do not chase the bear.
    If something needs the bald eagle then the bald eagle eats the bear.
    If something needs the bear then the bear is red.
    If something eats the bear then they are cold.
    If something is cold then they are not kind.
    If something eats the bear and they are not cold then the bear is not round.
    The bear is red?""",None],  

  ["""The bald eagle chases the bear.
    The bear needs the bald eagle.
    If something chases the bald eagle then they do not chase the bear.
    If something needs the bald eagle then the bald eagle eats the bear.
    If something needs the bear then the bear is red.
    If something eats the bear then they are cold.
    If something is cold then they are not kind.
    If something eats the bear and they are not cold then the bear is not round.
    The bear is round?""",None], 

  ["""The bald eagle chases the bear.
    The bear needs the bald eagle.
    If something chases the bald eagle then they do not chase the bear.
    If something needs the bald eagle then the bald eagle eats the bear.
    If something needs the bear then the bear is red.
    If something eats the bear then they are cold.
    If something is cold then they are not kind.
    If something eats the bear and they are not cold then the bear is not round.
    The bald eagle is cold?""",True]
]
