# core tests used by the nlptest.py

[
 
  # first basic test

  ["""Elephants are animals. Elephants are animals?""",True],

  # other nine basic tests

  ["""Elephants are animals. John is an elephant. John is an animal?""",True],
  ["""Elephants are not birds. John is an elephant. John is not a bird?""",True],
  ["""Elephants are animals. John is an elephant. Who is an animal?""","""John."""],
  ["""Elephants are not birds. John is an elephant. John is a bird?""",False],
  ["""Elephants are animals. Who is an animal?""","""An elephant."""],
  ["""Elephants are grey animals. John is an elephant. Who is grey?""","""John."""],
  ["""Elephants are big animals. John is an elephant. Who is nice?""",None],
  ["""Elephants have long trunks. John is an elephant. Who has a trunk?""","""John."""],
  
  ["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike. Who is a child of John?""","""Mike."""],

  # basic questions with no rules

  ["""John is a man or not a man?""",True],
  ["""John is a man and not a man?""",False],
  ["""John is tall or not tall?""",True],
  ["""John is tall and not tall?""",False],
  ["""John is a tall man and not a tall man?""",False],
  ["""John is a tall man or not a tall man?""",None],
  ["""John has a car or does not have a car?""",True],
  ["""John has a car and does not have a car?""",False],
  ["""John has a car?""",None],
  ["""John is in Estonia or is not in Estonia?""",True],
  ["""John is in Estonia and is not in Estonia?""",False],
  ["""John is in Estonia?""",None],

  # questions with basic combos of names and non-names

  ["John was yellow. John was yellow?",True],
  ["John was yellow. John was nice?",None],
  ["John was yellow. A man was nice?",None],
  ["A man was yellow. A man was yellow?",True],
  ["A man was yellow. A man was nice?",None],
  ["A man was yellow. John was nice?",None],
  
  # basic quantifiers

  ["""Elephants are animals. Elephants are animals?""",True],
  ["""Elephants are animals. Some elephant is an animal?""",True],
  ["""Elephants are animals. All elephants are animals?""",True],
  ["""Elephants are animals. John is an animal?""",None],
  ["""Elephants are animals. Elephants are not animals?""",False],
  ["""Elephants are animals. Some elephants are not animals?""",False],
  ["""Elephants are animals. All elephants are not animals?""",False],

  ["""All elephants are animals. Elephants are animals?""",True],
  ["""All elephants are animals. Some elephant is an animal?""",True],
  ["""All elephants are animals. All elephants are animals?""","""True"""],
  ["""All elephants are animals. John is an animal?""",None],
  ["""All elephants are animals. Elephants are not animals?""",False],
  ["""All elephants are animals. Some elephants are not animals?""",False],
  ["""All elephants are animals. All elephants are not animals?""",False],
  
  ["""Some elephants are animals. Elephants are animals?""",None],
  ["""Some elephants are animals. Some elephant is an animal?""",True],
  ["""Some elephants are animals. All elephants are animals?""",None],
  ["""Some elephants are animals. John is an animal?""",None],
  ["""Some elephants are animals. Elephants are not animals?""",None],
  ["""Some elephants are animals. Some elephants are not animals?""",None],
  ["""Some elephants are animals. All elephants are not animals?""",None],

  ["""Some elephants are not animals. All elephants are animals?""",False],
  ["""All elephants are not animals. No elephant is an animal?""",None],
  ["""No elephant is an animal. No elephant is an animal?""",True],
  ["""No elephant is an animal. Some elephant is an animal?""",False],

  # more complex quantifier uses

  ["It is not true that all big yellow cats are strong. Some yellow cats are not strong?",True],
  ["It is not true that all big yellow cats are strong. Some red cats are not strong?",None],
  ["It is not true that some big yellow cats are strong. All big yellow cats are not strong?",True],

  ["John likes all boxers. Mike is a boxer. John likes Mike?",True],
  #["Bears like all boxers. Mike is a boxer. Greg is a bear. Greg likes Mike?",True], stanza 1.4 err: thinks like is nmod
  ["Bears eat all boxers. Mike is a boxer. Greg is a bear. Greg eats Mike?",True],
  ["Bears eat most boxers. Mike is a boxer. Greg is a bear. Bears eats Mike?","Probably true."],
  ["Bears eat most boxers. Mike is a boxer. Greg is a bear. Bears eats Greg?",None],
  ["Bears eat all boxers. Mike is a boxer. Bears eat boxers?",True],
  ["Bears eat some boxers. Mike is a boxer. Bears eat Mike?",None],
  ["John likes some boxers. Mike is a boxer. John likes Mike?",None],

  # "A" in the question is interpreted as "some" in case this kind of object has been recently talked about

  ["The red square has a nail. A blue square has a hole. A square has a nail?",True],
  ["The red square has a nail. A blue square has a hole. A square has a hole?",True],
  ["The red square has a nail. A blue square has a hole. A square has a dot?",None],
  ["The red square has a nail. A blue square has a hole. A red square has a nail?",True],
  ["The red square has a nail. A blue square has a hole. A blue square has a hole?",True],
  ["The red square has a nail. A blue square has a hole. A red square has a hole?",None],
  ["The red square is nice. A blue square is cool. A square is cool?",True],
  ["The red square is nice. A blue square is cool. A square is nice?",True],
  ["The red square is nice. A blue square is cool. A square is empty?",None],
 
  
  #["""It is false that some cats are strong. Strong cats are not weak. Weak cats are not strong. 
  #    All cats are weak?""",True] # Err since "It is false" applied to strong, and not whole sentence


  # sentences with and-or-nor-xor combos

  ["""Elephants, foxes and rabbits are nice animals and good toys. John is an elephant. John is a toy?""",True],
  ["""Elephants, foxes and rabbits are nice animals and good toys. John is a fox. John is a good toy?""",True],
  ["""Elephants, foxes and rabbits are nice animals and good toys. John is a rabbit. John is an animal?""",True],
  ["""Elephants, foxes and rabbits are nice animals and good toys. John is a rabbit. John is an animal and a toy?""",True],
  ["""Elephants, foxes and rabbits are nice animals and good toys. John is a rabbit. John is an animal or a toy?""",True],
  ["""Elephants, foxes and rabbits are neither birds nor small fish. John is a rabbit. John is a bird?""",False],
  ["""Elephants, foxes and rabbits are neither birds nor small fish. John is a rabbit. John is not a bird?""",True],
  ["""Elephants, foxes and rabbits are neither birds nor small fish. John is a rabbit. John is a small fish?""",False],
  ["""Elephants, foxes and rabbits are neither birds nor small fish. John is a rabbit. John is a fish?""",None],
  ["""Elephants, foxes and rabbits are nice animals and good toys. John is an elephant. John is a red toy?""",None],
  ["""Elephants and sparrows are animals or birds. John is a sparrow. John is a bird. John is an animal?""",False],
  ["""Elephants and sparrows are animals or birds. John is a sparrow. Sparrows are birds. John is not an animal?""",True],
  ["""Elephants and sparrows are animals or birds. John is a sparrow. John is a bird. John is an animal or a bird?""",True],
  ["""Elephants and sparrows are animals or birds. John is a sparrow. John is a bird. John is an elephant?""",None],
  ["""Elephants or sparrows are animals. John is a sparrow. John is an animal?""",None],
  ["""Elephants or sparrows are animals. John is an elephant. Sparrows are not animals. John is an animal?""",True],

  ["""If animal or bird is nice and simple, it is cute. John is cute?""",None],
  ["""If animal or bird is nice and simple, it is cute. John is a nice and simple animal. John is cute?""",True],
  ["""If animal or bird is nice and simple, it is cute. John is a nice and simple bird. John is cute?""",True],
  ["""If animal or bird is nice and simple, it is cute. John is a nice and simple fox. John is cute?""",None],
  ["""If animal or bird is nice and simple, it is cute. John is a nice animal. John is cute?""",None],  

  ["Elephants are animals. Birds are animals?",None],
  ["Elephants are animals. Birds are not animals?",None],
  ["Elephants are animals. Birds are nice animals?",None],
  ["Elephants are animals. Birds are not nice animals?",None],

  ["John is a red or black elephant. John is an elephant. John is red. John is black?",False],

  # sentences with subject property logic

  ["""Big or strong elephants are nice. John is a big elephant. John is nice?""",True],
  ["""Big or strong elephants are nice. John is a big elephant. John is strong. John is nice?""",True],
  ["""Big or strong elephants are nice. John is an elephant. John is nice?""",None],
  #["""Big and strong elephants are nice. John is an elephant. John is big and strong. John is nice?""",True], # gives Likely true.
  ["""Big and strong elephants are nice. John is a big elephant. John is a strong elephant. John is nice?""",True],
  ["""Yellow and green elephants are nice. John is an elephant. John is yellow and green. John is nice?""",True],
  ["""Big and strong elephants are nice. John is a strong elephant. John is nice?""",None],
  #["""Big and not strong elephants are nice. John is a big elephant. John is not strong. John is nice?""",True],
  ["""Big and not strong elephants are nice. John is a big elephant. John is a not strong elephant. John is nice?""",True],

  # sentences with "have"

  ["""Elephants have trunks. Elephants have trunks?""",True],
  ["""No elephant has wings. No elephant has wings?""",True],
  ["""No elephants have wings. Some elephant has wings?""",False],
  ["""Elephants have no wings. Some elephant has wings?""",False],
  ["""Elephants have no wings. John has no wings?""",None],
  ["""All elephants have no wings. Some elephant has wings?""",False],
  ["""All elephants have no wings. John has no wings?""",None],
  ["""Some elephants have no wings. Some elephant has wings?""",None],
  ["""Some elephants have no wings. John has no wings?""",None],
  ["""No elephants have wings. All elephants do not have wings?""",True],
  ["""Elephants have trunks. John has a trunk?""",None],
  ["""All elephants have trunks. John has a trunk?""",None],
  ["""Some elephants have trunks. John has a trunk?""",None],

  ["Elephants have a trunk. Birds have a trunk?",None],
  ["Elephants have a trunk. Birds do not have a trunk?",None],

  ["""Elephants have long trunks and short tails. John is an elephant. Who has a trunk and a tail?""","""John."""],
  ["""Elephants have long trunks and short tails. John is an elephant. Who has a long trunk and a short tail?""","""John."""],
  ["""Elephants have long trunks and no wings. John is an elephant. John has a wing?""",False],
  ["""Elephants have long trunks and no wings. John is an elephant. John has no wing?""",True],
  ["""Elephants have long trunks and no wings. John is an elephant. John does not have a wing?""",True],
  ["""Elephants have long trunks and no wings. John is an elephant. John has a wing?""",False],
  ["""Elephants have long trunks and no wings. John is an elephant. Who does not have a wing?""","""John."""],
  ["""Elephants have long trunks and no wings. John is an elephant. John has a long trunk and no wing?""",True],

  ["""Elephants have long trunks. John is an elephant. John has a trunk?""",True],
  ["""Elephants have no trunks. John is an elephant. John has a trunk?""",False],
  ["""Elephants have long grey trunks. John is an elephant. Who has a trunk?""","""John."""],
  ["""Elephants have long and grey trunks. John is an elephant. Who has a trunk?""","""John."""],
  ["""Elephants have long grey trunks. John is an elephant. Who has a grey trunk?""","""John."""],
  ["""Elephants have long and grey trunks. John is an elephant. Who has a grey trunk?""","""John."""],
  ["""Elephants have trunks or tails. John is an elephant. John has no trunk. John has a tail?""",True],
  ["""Elephants have trunks or tails. John is an elephant. John has a tail and a trunk?""",False],
  ["""Elephants have trunks or tails. John is an elephant. John has a tail or a trunk?""",True],
  ["""Elephants have long or short trunks. John is an elephant. John does not have a long trunk. John has a short trunk?""",True],  
  #["""Elephants have long or short trunks. John is an elephant. John has a long trunk. John has a short trunk?""",False],
  ["""Elephants have long or short trunks. John is an elephant. John has a trunk?""",True],
  ["""Elephants have long or short trunks. John is an elephant. John has a long trunk?""",None],
  ["""Elephants have long grey trunks. John is an elephant. Who has a long red trunk?""",None],
  ["""Elephants have no long red trunks. John is an elephant. John has a long red trunk?""",False],
  ["""Elephants have no long red trunks. John is an elephant. John has a long trunk?""",None],
  [" Elephants have not red trunks. John is an elephant. John has a not red trunk?",True],
  [" Elephants have not red trunks. John is an elephant. John has a trunk?",True],
  [" Elephants have not red trunks. John is an elephant. John has a big trunk?",None],
  [" Elephants have long not red trunks. John is an elephant. John has a long not red trunk?",True],
  [" Elephants have long not red trunks. John is an elephant. John has a long trunk?",True],
  [" Elephants have long not red trunks. John is an elephant. John has a long black trunk?",None],
  [" Elephants have long not red trunks. John is an elephant. John has a not red trunk?",True],
  [" Elephants have long not big trunks. John is an elephant. John has a long not big trunk?",True],
  [" Elephants have long not big trunks. John is an elephant. John has a not big trunk?",True],
  [" Elephants have long not red trunks. John is an elephant. John has a long not small trunk?",None],
  [" Elephants have long not big trunks. John is an elephant. John has a long trunk?",True],
  ["""Elephants do not have long red trunks. John is an elephant. John has a long red trunk?""",False],
  ["""Elephants do not have wings. John is an elephant. John has wings?""",False],
  ["""Elephants do not have wings. John is an elephant. John has a wing?""",False],
  ["""Elephants do not have long red wings. John is an elephant. John has a wing?""",None],

  ["""If an animal has a trunk, it is an elephant. John has a long trunk. John is an animal. 
      John is an elephant?""",True],
  ["""If an animal has a trunk, it is an elephant. John has a long trunk.  
      John is an elephant?""",None],    

  ["""If an animal or bird has a tail, it is cute. John has a tail. John is cute?""",None],    
  ["""If an animal or bird has a tail, it is cute. John has a tail. John is a fox. John is cute?""",None],
  ["""If an animal or bird has a tail, it is cute. John is an animal. John has a tail. John is cute?""",True],
  ["""If an animal or bird has a tail, it is cute. John is a bird. John has a tail. John is cute?""",True],
  ["""If an animal or bird has a tail, it is cute. John is a bird or an animal. John has a tail. John is cute?""",True],

  ["""If a bear is nice, it has a tail. John is a nice bear. John has a tail?""", True], 
  ["""If a big bear is nice, it has a tail. John is a nice bear. John has a tail?""", None],
  ["""If a bear is nice and has a trunk, it has a tail. John is a nice bear. John has a trunk. John has a tail?""",True],

  # if-then rules with a general left side

  ["If cars are red, elephants are nice. Cars are red. Elephants are nice?",True],
  ["If cars are red, elephants are nice. Elephants are nice?",None],
  ["If some cars are red, elephants are nice. John is a red car. Elephants are nice?",True],
  ["If cars are red, elephants are nice. John is a red car. Elephants are nice?",None],
  ["If cars are green, elephants are nice. If elephants are nice, squirrels are red. Cars are green. Squirrels are red?",True],
  ["If cars have roofs, elephants are nice. Cars have roofs. Elephants are nice?",True],
  ["If cars have roofs, elephants are nice. John is a car. John has a roof. Elephants are nice?",None],
  ["If some cars have roofs, elephants are nice. John is a car. John has a roof. Elephants are nice?",True],
  ["If some car has a roof, elephants are nice. John is a car. John has a roof. Elephants are nice?",True],

  # simple if-then rules with variables

  ["If X is cool then X is red. John is cool. Mike is red?",None], 
  ["If X is cool then X is red. John is cool. John is red?",True],
  ["If X is cool and X is nice then X is red. John is nice and cool. John is red?",True],
  ["If X is cool and nice then X is red. John is nice and cool. John is red?",True],  
  ["If X is cool and X is nice then X is red. Mike is nice. Mike is red?",None], # before a fix used lemma of X, which could be lowercase
  ["If X is cool and X is nice then X is red. Mike is cool. Mike is red?",None],

  # if-then rules with variables and lists and or-s

  ["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike. Who is a child of John?""","""Mike."""],
  ["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike and Mary. 
      Who is a child of John?""","""Mike and Mary"""],
  ["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike, Mary and Eve. 
      Who is a child of John?""","""Mike, Mary and Eve"""],    
  ["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike or Mary. 
      Who is a child of John?""","""Mike or Mary"""],   
  #["""If X1 is a father of Y1, Y1 is a child of X1. John is a father of Eve and Mike or Mary. 
  #    Who is a child of John?""","""Eve and Mike or Mary"""],  

  # more complex if-then rules combos with variables 

  ["""If X1 is a grandfather of Y1, Y1 is not a child of X1. John is a grandfather of Mike. Who is not a child of John?""","""Mike."""],
  ["""If X1 is not a parent of Y1, Y1 is not a child of X1. John is not a parent of Mike. Who is not a child of John?""","""Mike."""],
  ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike. Luke is a father of John. Luke is a grandfather of Mike?""",True],
  ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike. Luke is a father of John. 
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1. Mike is a grandchild of Luke?""",True],
  ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike. Luke is a father of John. 
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1. 
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1. 
      Mike is male. Mike is a grandson of Luke?""",True],
  ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike and Mickey. Luke is a father of John. 
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1. 
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1. 
      Mike and Mickey are male. Who is a grandson of Luke?""","""Mike and Mickey."""],
  

   # comparisons

   ["""John is nicer than Mike. Mike is nicer than Eve. Who is nicer than Eve?""",
     """John and Mike."""],
   ["""John is nicer than Mike. Mike is nicer than Eve. Who is nicer than John?""",
     None], 


   # containment 

   ["""Tallinn is in Estonia. Estonia is not outside Europe. Earth contains Europe.  
       Estonia contains Tartu. Riga is not in Estonia. Tallinn is in what?""",
    """Earth, Europe and Estonia."""],
   ["""Tallinn is in Estonia. Estonia is not outside Europe. Earth contains Europe.  
       Estonia contains Tartu. Riga is not in Estonia. What is not in Estonia?""",
    """Riga."""], 
   ["""Tallinn is in Estonia. Estonia is not outside Europe. Earth contains Europe.  
       Estonia contains Tartu. Riga is not in Estonia. Riga is in Estonia?""",
    False], 
   [""""Riga is outside America. Riga is not in what?""","""America."""], 
   [""""Riga is not in America. What is not in America?""","""Riga."""],


   ["""If a city is in Estonia, it is an Estonian city. Tallinn is in Estonia. Tallinn is a city. 
     What is an Estonian city?""","""Tallinn."""],
   ["""Cities in Estonia are estonian. Tallinn is in Estonia. Tallinn is a city. 
    What is an Estonian city?""","""Tallinn."""],

   # Numeric uncertainty  

   ["""Elephants are probably animals. John is an elephant. John is an animal?""","""Probably true."""],
   ["""Elephants are rarely animals. John is an elephant. John is an animal?""","""Probably false."""],
   ["""Probably elephants are animals. John is an elephant. John is an animal?""","""Probably true."""],
   ["""Probably elephants are not animals. John is an elephant. John is an animal?""","""Probably false."""],
   ["""It is true that elephants are animals. John is an elephant. John is an animal?""",True],
   ["""It is false that elephants are animals. John is an elephant. John is an animal?""",False],               
   ["""It is not true that elephants are animals. John is an elephant. John is an animal?""",False],  
   ["""It is not false that elephants are animals. John is an elephant. John is an animal?""",True], 
   ["""It is probably true that elephants are animals. John is an elephant. John is an animal?""","""Probably true."""],
   ["""It is probably false that elephants are animals. John is an elephant. John is an animal?""","""Probably false."""],
   ["""It is probable that elephants are animals. John is an elephant. John is an animal?""","""Probably true."""],
   ["""It is not probable that elephants are animals. John is an elephant. John is an animal?""","""Probably false."""],
   ["""It is unlikely that elephants are animals. John is an elephant. John is an animal?""","""Probably false."""],

   ["""It is true that John is a child of Mike. John is a child of Mike?""",True],
   ["""It is false that John is a child of Mike. John is a child of Mike?""",False],
   ["""It is probable that John is a child of Mike. John is a child of Mike?""","""Probably true."""],
   ["""It is probably true that John is a child of Mike. John is a child of Mike?""","""Probably true."""],
   ["""It is improbable that John is a child of Mike. John is a child of Mike?""","""Probably false."""],
   ["""It is not probable that John is a child of Mike. John is a child of Mike?""","""Probably false."""],   
   ["""It is unlikely that John is a child of Mike. John is a child of Mike?""","""Probably false."""],
   ["""It is unlikely that John is a child of Mike. John is a child of Mike?""","""Probably false."""],
   ["""It is probably false that John is a child of Mike. John is a child of Mike?""","""Probably false."""],
   ["""John is maybe not a child of Mike. John is a child of Mike?""","""Likely false."""],
   ["""John is probably a child of Mike. John is a child of Mike?""","""Probably true."""],
   ["""Probably John is a child of Mike. John is a child of Mike?""","""Probably true."""],

  ["""Probably elephants have long trunks. John is an elephant. John has a trunk?""","""Probably true."""],
  ["""Probably elephants have no trunks. John is an elephant. John has a trunk?""","""Probably false."""],
  ["""Elephants have probably long trunks. John is an elephant. John has a long trunk?""","""Probably true."""],
  ["""Elephants have probably no trunks. John is an elephant. John has a trunk?""","""Probably false."""],
  ["""Elephants have rarely trunks. John is an elephant. John has a trunk?""","""Probably false."""],
  ["""It is true that elephants have long grey trunks. John is an elephant. Who has a trunk?""","""John."""],
  ["""It is false that elephants have long grey trunks. John is an elephant. Who has a trunk?""",None],
  ["""It is probably true that elephants have long grey trunks. John is an elephant. Who has a trunk?""","""Probably John."""],
 

   ["""It is probable that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike. 
       Mike is a child of John?""","""Probably true."""],
   ["""It is probable that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike. 
       Mike is a child of John?""","""Probably false."""],
   ["""It is probably true that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike. 
       Mike is a child of John?""","""Probably true."""],
   ["""It is probably false that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike.
       Mike is a child of John?""","""Probably true."""],
   ["""It is unlikely that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike.
       Mike is a child of John?""","""Probably false."""],    
   ["""It is unlikely that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike.
       Mike is a child of John?""","""Probably true."""],  
   ["""It is probable that if X1 is not a grandfather of Y1, Y1 is a child of X1. John is not a grandfather of Mike. 
       Mike is a child of John?""","""Probably true."""],
  
   ["""Tallinn is probably in Estonia. Tallinn is in Estonia?""", """Probably true."""],
   ["""Tallinn is hardly in Latvia. Tallinn is in Latvia?""", """Likely false."""],
   ["""It is true that Tallinn is in Estonia. Tallinn is in Estonia?""", True],
   ["""It is false that Tallinn is in Latvia. Tallinn is in Latvia?""", False],
   ["""It is probably true that Tallinn is in Estonia. Tallinn is in Estonia?""", """Probably true."""],
   ["""It is probably false that Tallinn is in Latvia. Tallinn is in Latvia?""", """Probably false."""],
   ["""Probably Tallinn is in Estonia. Tallinn is in Estonia?""", """Probably true."""],
   ["""It is not probable that Tallinn is in Latvia. Tallinn is in Latvia?""", """Probably false."""],

   ["""John is an elephant with a probability 100 percent. John is an elephant?""", True],
   ["""John is an elephant with a probability 0 percent. John is an elephant?""", False],
   ["""John is an elephant with a probability 10 percent. John is an elephant?""", """Likely false."""],
   ["""John is an elephant with a probability 90 percent . John is an elephant?""", """Likely true."""],   
   ["""John is an elephant with a probability 50 percent. John is an elephant?""", None],

   ["""Tallinn is in Estonia with a probability 90 percent. Tallinn is in Estonia?""", """Likely true."""],
   ["""Tallinn is in Latvia with a probability 10 percent. Tallinn is in Latvia?""", """Likely false."""],
   ["""Tallinn is in Latvia with a probability 50 percent. Tallinn is in Latvia?""", None],

   ["""Elephants have a trunk with a probability 90 percent. John is an elephant. John has a trunk?""","""Likely true."""],
   ["""Elephants have a trunk with a probability 10 percent. John is an elephant. John has a trunk?""","""Likely false."""],
   ["""Elephants have a trunk with a probability 50 percent. John is an elephant. John has a trunk?""",None], 
   
   ["""Elephants have a trunk with a probability 90 percent. John is an elephant. Who has a trunk?""","""Likely John."""],
   ["""Elephants probably do not have wings. John is an elephant. Who does not have wings?""","""Probably John."""],
   ["""Elephants probably do not have wings. John is maybe an elephant. Who does not have wings?""","""Maybe John."""], 

   ["John probably smokes. John smokes?","Probably true"],
   ["Probably John smokes. John smokes?","Probably true"],
   ["It is probably true that John smokes. John smokes?","Probably true"],
   ["John smokes with a probability 90%. John smokes?","Likely true"],
   ["John smokes with a probability 90 percent. John smokes?","Likely true"],
   ["John smokes with a probability 0.9. John smokes?","Likely true"],
   ["John smokes with a probability 0.1. John smokes?","Likely false"],
   ["John smokes tobacco with a probability 0.8. John smokes what?","Likely a tobacco"],
   ["John smokes tobacco with a probability 0.8. John smokes?","Likely true"],

   ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike and Mickey. Luke is a father of John. 
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1. 
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1. 
      Mike and Mickey are not female. Any person is male or female. 
      Who is a grandson of Luke?""","""Mickey and Mike."""],
  ["""If X1 is a father of Y1, Y1 is a child of X1. 
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1. 
      John is a father of Mike and Mickey. Luke is a father of John. 
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1. 
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1. 
      Mike or Mickey are not female. Any person is male or female. 
      Who is a grandson of Luke?""","""Mike or Mickey."""],

  # numerically uncertain quantors

  ["""Most bears are big. John is a bear. John is big?""","""Likely true."""],
  ["""Many bears are big. John is a bear. John is big?""","""Perhaps true."""],
  ["""Few bears are big. John is a bear. John is big?""","""Likely false."""],
  # ["""Not many bears are big. John is a bear. John is big?""","""Perhaps false."""], # fails with stanza 1.4

  # basic default rules
   
  ["""Elephants are big. Young elephants are not big. 
      Mike is an elephant. John is a young elephant. Mike is big?""",True],
  ["""Elephants are big. Young elephants are not big. 
      Mike is an elephant. John is a young elephant. John is big?""",False],    
  ["""Elephants are big. Young elephants are not big. 
      Mike is an elephant. John is a young elephant. Who is big?""","""Mike."""],
  ["""Elephants are big. Young elephants are not big. 
      Mike is an elephant. John is a young elephant. Who is not big?""","""John."""],   
  ["""Elephants are big. Young elephants are not big. 
      Who is big?""","""An elephant."""],      
  ["""Elephants are big. Young elephants are not big. 
      Who is not big?""","""A young elephant."""], 

  ["Penguins are birds who do not fly. Birds fly. John is a penguin. John flies?",False],
  ["Penguins are birds. Penguins do not fly. Birds fly. John is a penguin. John flies?",False],
  ["Penguins are birds who do not fly. Birds fly. John is a bird. John flies?",True],
  ["Penguins are birds. Penguins do not fly. Birds fly. John is a bird. John flies?",True],


  # default rules with a (mostly) general-noun question

  ["Cars are nice. Cars are nice?",True],      # no defaults here, just basic
  ["Cars are nice. Cars are not nice?",False], # no defaults here, just basic
  ["Red cars are not nice. Cars are nice. Cars are nice?",True],
  ["Red cars are not nice. Cars are nice. Cars are not nice?",False],
  ["Red cars are not nice. Cars are nice. Red cars are nice?",False],
  ["Red cars are not nice. Cars are nice. Red cars are not nice?",True],
  ["Red cars are not nice. Cars are nice. What are nice?","A car."],
  ["Red cars are not nice. Cars are nice. What are not nice?","A red car."],
  ["Red cars are not nice. Cars are nice. What are nice?","A car."],
  ["Red cars do not have trunks. Cars have trunks. Cars have trunks?",True],
  ["Red cars do not have trunks. Cars have trunks. Red cars have trunks?",False],
  ["Red cars do not have trunks. Cars have trunks. Cars have a trunk?",True],
  ["Red cars do not have trunks. Cars have trunks. Red cars have a trunk?",False],
  ["Red cars do not have trunks. Cars have a trunk. Cars have a trunk?",True],
  ["Red cars do not have trunks. Cars have a trunk. Red cars have a trunk?",False],
  ["Red cars do not have trunks. Cars have trunks. John is a car. John has a trunk?",True],
  ["Red cars do not have trunks. Cars have trunks. John is a red car. John has a trunk?",False],
  ["Penguins are birds. Penguins do not fly. Birds fly. Birds fly?",True],
  ["Penguins are birds. Penguins do not fly. Birds fly. Penguins fly?",False],
  ["Penguins are birds. Penguins do not fly. Birds fly. Who flies?","A bird."],
  ["Penguins are birds. Penguins do not fly. Birds fly. Who does not fly?","A penguin."],
  
  # do-actions

  ["""If a bear eats red berries, it is big. John eats berries. John is a bear. 
     John is big?""",None],
  ["""If a bear eats red berries, it is big. John eats red berries. John is a bear. 
     John is big?""",True],   
  ["""If X1 eats berries, it is a bear. John eats red berries. John is a bear?""",
     True],
  ["""Bears eat berries. John is a bear. John eats berries?""", True],   
  ["""Bears eat berries. John is a bear. John eats some berries?""", True],
  ["""Bears eat berries. John is a bear. John eats all berries?""", None],
  ["""Bears eat all berries. John is a bear. John eats all berries?""", True],
  ["""Some bears eat all berries. John is a bear. John eats berries?""", None],
  ["""Some bears eat all berries. Some bears eat berries?""", True], 
  ["""Birds fly or swim. John is a bird. John does not fly. John swims?""",True],
  ["""Birds fly or swim. John is a bird. John swims?""",None],
  ["""Birds fly or do not swim. John is a bird. John does not fly. John swims?""",False],
  ["""Birds fly or do not swim. John is a bird. John never flies. John swims?""",False],
  ["""Birds do not fly and swim. John is a bird. John swims?""",False],
  ["""Birds do not fly and swim. John is a bird. John swims or flies?""",False],
  ["""Birds fly and swim. John is a bird. John swims and flies?""",True],


  # default rules and do-actions 

  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike is a bird. 
    John does not fly?""",True],
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike is a bird. 
    Mike flies?""",True],  
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike is a bird. 
    John runs?""",None],  
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds. 
    Who does not fly?""","""John."""],
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds. 
    Who flies?""","""Mike and Eve."""],  
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds. 
    Who eats?""","""John, Mike and Eve."""],
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds. 
    Who flies and eats?""","""Mike and Eve."""],  
  ["""Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds. 
    Who flies or eats?""","""John, Mike and Eve."""],
  ["""Birds fly and eat. Baby birds do not fly. John is hardly a baby bird. 
     Mike and Eve and John are birds. Who flies and eats?""","""Mike, Eve and John"""],
  ["""Birds fly and eat. Baby birds do not fly. John is probably a baby bird. 
     Mike and Eve and John are birds. Who flies and eats?""","""Mike and Eve"""],     
  ["""Birds fly and eat. Baby birds do not fly. John is perhaps a baby. 
     Mike and Eve and John are birds. Who flies and eats?""","""Mike, Eve and likely John"""],
  ["""Bears eat berries. Baby bears do not eat berries. John is a bear. 
     John eats berries?""", True],
  ["""Bears eat berries. Baby bears do not eat berries. John is a baby bear. 
     John eats berries?""", False],
  ["""Bears eat berries. Baby bears eat no berries. John is a baby bear. 
     John eats berries?""", False],   
  ["""Bears eat berries. Baby bears do not eat berries. John and Mike are bears.
      John is a baby bear. 
      Who eats berries?""", """Mike."""],  

  # default rules and can-actions

  ["""Birds can fly. Baby birds can not fly. John is a baby bird. Mike and Eve are birds. 
      Who can fly?""","""Mike and Eve."""],
  ["""Birds can fly. Baby birds can not fly. John is a baby bird. Mike and Eve are birds. 
      Who can not fly?""","""John."""],    
  ["""Bears can eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who can eat berries?""", """Mike."""],
  ["""Bears can eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who can not eat berries?""", """John."""],

  # default rules and can-do mix-actions

  ["""Birds fly. No penguin can fly. Penguins are birds. John is a penguin. John can fly?""",False],
  ["""Birds fly. No penguin can fly. Penguins are birds. John is a penguin. John flies?""",False],
  ["""Birds can fly. No penguin can fly. Penguins are birds. John is a penguin. John can fly?""",False],
  ["""Birds fly. No penguin can fly. Penguins are birds. John is a bird. John can fly?""",True],
  ["""Birds fly. No penguin can fly. Penguins are birds. John is a bird. John flies?""",True],
  ["""Birds can fly. No penguin can fly. Penguins are birds. John is a bird. John can fly?""",True],

  ["""Birds fly. Baby birds can not fly. John is a baby bird. Mike is a bird. Who flies?""",
      """Mike"""],
  ["""Birds fly. Baby birds can not fly. John is a baby bird. Mike is a bird. Who does not fly?""",
      """John"""], 
  ["""Birds fly. Baby birds can not fly. John is a baby bird. Mike is a bird. Who can fly?""",
      """Mike"""],
  ["""Birds fly. Baby birds can not fly. John is a baby bird. Mike is a bird. Who can not fly?""",
      """John"""],              
  ["""Bears eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who eats berries?""", """Mike."""],
  ["""Bears eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who does not eat berries?""", """John."""],     
  ["""Birds can fly. Baby birds do not fly. John is a baby bird. Mike is a bird. Who can not fly?""",
      None],          
  ["""Bears can eat berries. Baby bears do not eat berries. John and Mike are bears.
      John is a baby bear.  Who can not eat berries?""", None],
  ["""Baby birds do not fly. John is a baby bird. Mike is a bird. Who can not fly?""","""Perhaps John."""],

  # action properties

  ["Bears eat berries in a forest. Bears eat berries in forest?",True],
  ["Bears eat berries in a forest. Bears do not eat berries in forest?",False],
  ["Bears eat berries in a forest. Bears eat berries in a field?",None],
  ["Bears eat berries in a forest. Bears eat berries?",True],
  ["Bears quickly eat berries in a forest. Bears eat berries?",True],
  ["Bears quickly eat berries in a forest. Bears quickly eat berries?",True],
  ["Bears quickly eat berries in a forest. Bears slowly eat berries?",None],
  ["Bears eat red berries in a forest. Bears eat red berries in forest?",True],
  ["Bears eat red berries in a forest. Bears eat berries in forest?",True],
  ["Bears eat red berries in a forest. Bears eat yellow berries in forest?",None],
  ["Bears do not eat red berries in a forest. Bears eat red berries in forest?",False],
  ["Bears eat berries in a deep forest. Bears eat berries?",True],
  ["Bears eat berries in a deep forest. Bears eat berries in a deep forest?",True],
  ["Bears eat berries in a deep forest. Bears eat berries in a forest?",True],
  ["Bears eat berries in a deep forest. Bears eat berries in a shallow forest?",None],
  ["Bears eat red berries in a deep forest. John is a bear. John eats red berries in a deep forest?",True],
  ["Bears eat red berries in a deep forest. John is a bear. John eats no berries?",False],
  ["Bears eat berries in a deep forest. John is a bear. John eats berries in a shallow forest?",None],
  ["Bears quickly eat berries in a deep forest. John is a bear. John quickly eats berries in a deep forest?",True],

   ["""If a bear quickly eats berries in a deep forest, it is hungry. John is a bear.
     John quickly eats berries in a deep forest. John is hungry?""",True],
  ["""If a bear quickly eats berries in a deep forest, it is hungry. John is a bear.
     John eats berries in a deep forest. John is hungry?""",None],
  ["""If a bear quickly eats berries in a deep forest, it is hungry. John is a fox.
     John quickly eats berries in a deep forest. John is hungry?""",None],   
  ["""If a bear eats berries in a forest, it is hungry. John is a brown bear. 
      John quickly eats berries in a deep forest. Who is hungry?""","""John."""],

  ["""If a bear eats berries in a forest, it is hungry. John is a brown bear. 
      John draws berries in a deep forest. Who is hungry?""",None],
  ["""If a bear eats, it is hungry. John is a brown bear. 
      John quickly eats berries in a deep forest. Who is hungry?""","""John."""],    

  # determinants a and the

  ["""A big bear was strong. The bear was nice. Who was nice and strong?""","""The big bear."""],  
  ["""A big bear was strong. The small bear was nice. Who was nice and strong?""",None],
  ["""A big bear was strong. The small bear was nice. Who was nice?""","""The small bear."""],
  ["""A big bear was strong. The small bear was nice. Who was strong?""","""The big bear."""],
  ["""A bear was strong. A bear was nice. Who was nice and strong?""",None],
  ["""A bear was strong. The bear was nice. Who was nice and strong?""","""The bear."""],
  ["""If the bear is strong, the fox is nice. The bear is strong. Who is nice?""","""The fox."""],
  ["""If the bear is strong, the fox is nice. The bear is strong. John is a fox. Who is nice?""","""The fox."""],
  ["""If bears are strong, foxes are nice. The bear is strong. John is a fox. Who is nice?""",None],
  ["John does not eat a carrot. John does not eat a carrot?",True],
  ["John does not eat a carrot. John eats a carrot?",False],
  ["John is not in a cave. John is not in a cave?",True],
  ["John is not in a cave. John is in a cave?",False],
  ["John does not eat a carrot. Mike eats carrots. Who eats carrots?","Mike"],
  ["John does not eat a carrot. Mike eats carrots. Who does not eat carrots?","John"],

  # using "who"

  ["""Big bears who have a trunk have a tail. John is a big bear. John has a trunk. John has a tail?""",True],
  ["""Big bears who have a trunk have a tail. John is a big bear. John has a nose. John has a tail?""",None],
  ["""Big bears who have a trunk have a tail. John is a bear. John has a trunk. John has a tail?""",None],
  ["""Big bears who are nice and have a trunk have a tail. John is a big bear. John has a trunk. John has a tail?""",None],
  ["""Big bears who are nice and have a trunk have a tail. John is a nice big bear. John has a trunk. John has a tail?""",True],
  ["""Big bears who are nice and who have a trunk have a tail. John is a big bear. John has a trunk. John has a tail?""",None],
  ["""Big bears who are nice and who have a trunk have a tail. John is a big bear. John is nice. John has a tail?""",None],
  ["""Big bears who are nice and who have a trunk have a tail. John is a nice big bear. John has a trunk. John has a tail?""",True],
  ["""Bears who are nice and have a long trunk have a tail. John is a nice big bear. John has a long trunk. John has a tail?""",True],
  ["""Bears who are nice and have a long trunk have a tail. John is a nice big bear. John has a trunk. John has a tail?""",None],
  ["""Bears who have a trunk are nice. John is a bear. John has a trunk. John is nice?""",True],
  ["""Bears who have a trunk are nice. John is a bear. John has a nose. John is nice?""",None],
  
  ["""Bears who are nice and eat berries have a tail. John is a nice big bear. John eats berries. John has a tail?""",True],
  ["""Bears who are nice and who eat berries have a tail. John is a nice big bear. John eats berries. John has a tail?""",True],
  ["""Bears who are nice and who eat berries have a tail. John is a nice big bear. John eats fish. John has a tail?""",None],

  ["Bears who are big are strong. John is a big nice bear. John is strong?",True],
  ["Bears who are big are strong. John is a bear. John is strong?",None],
  ["Bears who have tails are strong. John is a big nice bear. John has a tail. John is strong?",True],
  ["Bears who have tails are strong. John is a big nice bear.  John is strong?",None],
  ["Bears who eat fish are strong. John eats fish. John is a bear. John is strong?",True],
  ["Bears who eat fish are strong. John is a bear. John is strong?",None],
  ["Bears who eat fish are strong. John eats carrots. John is a bear. John is strong?",None],
  ["Nice bears who have tails are strong. John is a nice bear. John has a tail. John is strong?",True],
  ["Nice bears who have tails are strong. John is a bear. John has a tail. John is strong?",None], 
  ["Nice bears who have tails are strong. John is a nice bear. John has a head. John is strong?",None], 
  ["Nice bears who are big are strong. John is a big nice bear. John is strong?",True],
  ["Nice bears who are big are strong. John is a nice bear. John is strong?",None],
  ["Nice bears who eat fish are strong. John is a nice bear. John eats fish. John is strong?",True],
  ["Nice bears who eat big fish are strong. John is a nice bear. John eats big fish. John is strong?",True],
  ["Nice bears who eat big fish are strong. John is a nice bear. John eats big carrots. John is strong?",None],
  ["Nice bears who eat big fish are strong. John is a nice bear. John eats fish. John is strong?",None],

  ["If a bear who is big is strong, it is nice. John is a big strong bear. John is nice?",True],
  ["If a bear who is big is strong, it is nice. John is a big bear. John is strong. John is nice?","Likely true"],

  ["If a bear who eats fish is strong, it is nice. John is a bear. John eats fish. John is strong. John is nice?","Likely true"],
  ["If a bear who eats fish is strong, it is nice. John is a bear. John eats carrots. John is strong. John is nice?",None],
  ["If a bear who eats fish is strong, it is nice. John is a bear. John eats fish. John is nice?",None],

  # ["Bears who eat fish which are big are strong. John is a bear. John eats big fish. John is strong?", True],  # Fails with stanza 1.4
  #["Nice bears who eat fish which are big are strong. John is a nice bear. John eats big fish. John is strong?", True], # Fails with stanza 1.4
  ["Bears who eat fish which are big are strong. John is a bear. John eats fish. John is strong?", None],
  ["Bears who eat fish which are big are strong. John is a bear. John eats big apples. John is strong?", None],

  ["Bears eat fish who are strong. John is a bear. John eats strong fish?",True],
  ["Bears eat fish who are strong. John is a fox. John eats strong fish?",None],
  ["Bears eat fish who are strong. John is a bear. John eats red fish?",None],

  ["Bears eat red fish who are strong. John is a bear. John eats red strong fish?",True],
  ["Bears eat red fish who are strong. John is a bear. John eats yellow strong fish?",None],
  ["Bears eat red fish who are strong. John is a bear. John eats red fish?",True],
  ["Bears eat red fish who are strong. John is a bear. John eats yellow fish?",None],
  ["Bears eat red fish who are strong. John is a bear. John eats strong fish?",True],

  ["Bears who are nice eat fish who are strong. John is a nice bear. John eats strong fish?",True],
  ["Bears who are nice eat fish who are strong. John is a bear. John eats strong fish?",None],
  ["Bears who are nice eat fish who are strong. John is a nice bear. John eats yellow fish?",None],

  ["Bears who are nice and white eat fish who are strong and red. John is a nice white bear. John eats red strong fish?",True],
  ["Bears who are nice and white eat fish who are strong and red. John is a nice bear. John eats red strong fish?",None],
  ["Bears who are nice and white eat fish who are strong and red. John is a nice white bear. John eats yellow strong fish?",None],
  
  ["If a big bear who eats strong fish is white, it is nice. John is a big bear. John eats strong fish. John is white. John is nice?",True],
  ["If a big bear who eats strong fish is white, it is nice. John is a bear. John eats strong fish. John is white. John is nice?",None],
  ["If a big bear who eats strong fish is white, it is nice. John is a big bear. John eats strong fish. John is nice?",None],
  ["If a big bear who eats strong fish is white, it is nice. John is a big bear. John eats yellow fish. John is white. John is nice?",None],

  # The and who combinations

  ["The big bear is strong. The bear is big?",True],
  [" The white mouse is strong. The mouse is white?",True],
  [" The big mouse is strong. The mouse is big?",True],
  [" The big mouse is strong. The mouse is a big mouse?",True],
  ["The big bear is strong. The bear is strong?",True],
  ["The big bear is strong. The big bear is strong?",True],
  ["The big bear is strong. The big bear is white?",None],
  ["The big bear is strong. Who is strong?", "The big bear"],
  ["The bear who is big is strong. The bear is big?",True],
  [" The white mouse is strong. The mouse is white?",True], 
  [" The big mouse is strong. The mouse is a big mouse?",True],

  ["The bear who is big is strong. The bear is strong?",True],
  ["The bear who is big is strong. The big bear is strong?",True],
  ["The bear who is big is strong. The big bear is white?",None],
  ["The bear who is big is strong. Who is strong?","The big bear"],

  ["The bear who is big eats fish. The bear who is big eats fish?",True],  # was bad parse, ok with 1.4
  ["The bear who is white eats fish. The bear who is white eats fish?",True], # ok parse
  ["The bear who was white ate a fish. The bear who was white ate a fish?",True],  # ok parse
  ["The bear who was white ate a fish. The bear ate a fish?",True],  # ok parse
  ["The bear who was white ate a fish. The white bear ate a fish?",True],  # ok parse
  ["Bears who were nice ate. Nice bears ate?", True], # was bad parse, ok with 1.4: failed due to bad UD parse
  ["The bear who was nice ate. The bear ate?", True],

  ["Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat fish?",True], # before failed due to bad UD parse
  ["Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat tables?",None], # was bad parse, ok with 1.4: was bad UD parse
  ["Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice, eat tables?",None], # ok version of previous
  ["Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice, eat fish?",True], # ok UD parse
  ["Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat fish who are strong?",True],
  ["Bears who are nice eat fish who are strong. John is a nice bear. Nice bears eat strong fish?",True],

  ["The bear who was nice ate the fish who was strong. The bear who was nice ate the fish who was strong?",True],
  ["The bear who was nice ate the fish who was strong. The nice bear ate the strong fish?",True],
  ["The bear who was nice ate the fish who was strong. The bear who was nice ate the fish who was white?",None],

  ["The bear who was nice and white ate the fish who was big. The nice bear ate the big fish?",True],
  ["The bear who was white and ate a fish was cool. The white bear who ate a fish was cool?", True],
  ["The bear who was white and ate a fish was cool. The bear who ate a fish was cool?", True],
  ["The bear who was white and ate a fish was cool. The white bear who ate a fish was strong?", None],
  ["The bear who was white and ate a fish was cool. The black bear who ate a fish was cool?", None],
  ["The bear who was white and ate a big fish was cool. The white bear who ate a big fish was cool? ", True],
  ["The bear who was white and ate a big fish was cool. The white bear who ate a fish was cool? ", True],
  ["The bear who was white and ate a big fish was cool. The white bear who ate a strong fish was cool? ", None],
  ["The nice bear who was white and ate a big fish was cool. The white nice bear who ate a big fish was cool? ", True],

  ["The nice bear who was white and ate a big fish also ate berries. The white nice bear who ate a big fish also ate berries? ", True],
  ["The nice bear who was white and ate a big fish also ate blue berries. The white nice bear who ate a big fish also ate blue berries? ", True],
  ["The nice bear who was white and ate a big fish also ate blue berries. The white nice bear who ate a big fish also ate berries? ", True],
  ["The nice bear who was white and ate a big fish also ate blue berries. The bear ate berries? ", True],
  ["The nice bear who was white and ate a big fish also ate blue berries. The bear ate bread? ", None],

  ["The bear who ate a big fish ate blue berries. The bear who ate a fish also ate blue berries?", True], 
  ["The bear who ate a big fish ate blue berries. The bear who ate a fish ate big berries?", None],
  ["The bear who ate a big fish ate blue berries. John is big?", None],
  ["The bear who ate a big fish ate blue berries. John is blue?", None],
  ["The bear who ate a big fish ate blue berries. John is a fish?", None],

  # qualified property: very and somewhat
  
  ["John is very big. John is extremely big?",True],
  ["John is somewhat big. John is slightly big?",True],

  ["John is very big. John is very big?",True],
  ["John is very big. John is big?",True],
  ["John is very big. John is somewhat big?",False],
  ["John is big. John is very big?",None],
  ["John is big. John is big?",True],
  ["John is big. John is somewhat big?",None],
  ["John is somewhat big. John is very big?",False],
  ["John is somewhat big. John is big?",True],
  ["John is somewhat big. John is somewhat big?",True],

  ["John is big. John is not big?",False],
  ["John is very big. John is not very big?",False],
  ["John is very big. John is not big?",False],
  ["John is somewhat big. John is not somewhat big?",False],
  ["John is somewhat big. John is not big?",False],

  ["John is not very big. John is very big?",False],
  ["John is not very big. John is big?",True],

  ["A not very big bear is nice. The bear is a very big bear?",False],
  ["A not very big bear is nice. The bear is a big bear?",True],
  ["A not very big bear is nice. The bear is a somewhat big bear?",None],

  ["John is a not very big bear. John is a very big bear?",False],
  ["John is a not very big bear. John is a big bear?",True],
  
  ["John is not a very big bear. John is a bear?",None],
  ["John is not a very big bear. John is a big bear?",None],
  ["John is not a very big bear. John is a very big bear?",False],

  ["If John is not very big, John is nice. John is big. John is nice?",None],
  ["If John is not very big, John is nice. John is very big. John is nice?",None],  
  ["If John is not very big, John is nice. John is somewhat big. John is nice?",True],

  ["A very big mouse is nice. The mouse is a very big mouse?",True],
  ["A very big mouse is nice. The mouse is a big mouse?",True],
  ["A very big mouse is nice. The mouse is a somewhat big mouse?",False],

  # property and very and property classes (prop relative to a class)

  ["A very big mouse is nice. The mouse is very big?",True],
  ["A very big mouse is nice. The mouse is big?",True],
  ["A very big mouse is nice. The mouse is somewhat big?",False],

  ["If a bear is not very big, it is nice. John is a big bear. John is nice?",None],
  ["If a bear is not very big, it is nice. John is a very big bear. John is nice?",None],
  ["If a bear is not very big, it is nice. John is a bear. John is somewhat big. John is nice?","Likely true"],

  ["Frogs are small animals. John is a frog. John is a small animal?",True],
  ["Frogs are small animals. John is a frog. John is small?",True],
  ["Frogs are small. John is a frog. John is small?",True],
  ["Frogs are small. John is a frog. John is a small animal?",None],
  ["Frogs are small. Frogs are animals. John is a frog. John is a small animal?","Likely true"],
  ["John is a big mouse. John is big?", True],
  ["John is a big mouse. John is a big mouse?", True],
  ["John is a big mouse. John is a big thing?", None],

  # more subsentences

  ["John had a car which Eve bought. John had a car which Eve bought?",True],
  ["John had a car which Eve bought. John had a car which Eve saw?",None],
  ["John had a car which Eve bought. John had a car which Mike bought?",None],
  ["John had a car which Eve bought. John had a car Eve bought?",True],
  ["John had a car which Eve bought. John had a car Eve saw?",None],
  ["John had a car which Eve bought. John had a car Mike bought?",None],
  ["John had a car Eve bought. John had a car Eve bought?",True],
  ["John had a car Eve bought. John had a car Mike bought?",None],
  ["John had a car Eve bought. John had a car Eve saw?",None],
  ["John had a car Eve bought. John had a car which Eve bought?",True],
  ["John had a car Eve bought. John had a car which Eve saw?",None],
  ["John had a car Eve bought. John had a car which Mike bought?",None],

  ["John had a car Eve bought. Eve bought a car?",True], # had a problem with PROPN and not NER for Eve
  ["John had a car Mary bought. Mary bought a car?",True],
  ["John had a car Eve bought. John had a car?",True],
  ["John had a car Eve liked. Eve had a car?",None],
  ["John had a car Eve bought. John bought a car?",None],

  ["John had a car Eve bought. John had a car which Eve bought?",True],
  ["John had a car which Eve bought. John had a car Eve bought?",True],
  ["John had a red car Eve bought. John had a car which Eve bought?",True],
  ["John had a red car which Eve bought. John had a car Eve bought?",True],
  ["John had a red car Eve bought. John had a black car which Eve bought?",None],
  ["John had a red car which Eve bought. John had a black car Eve bought?",None],
  ["John had a car Eve bought. John had a car which Eve did not buy?",None],
  ["John had a car which Eve did not buy. John had a car Eve did not buy?",True],
  ["John did not have a red car which Eve bought. John did not have a red car which Eve bought?",True],

  ["John drove a car which Eve bought. John drove a car which Eve bought?",True],
  ["John drove a car which Eve bought. John drove a car which Eve saw?",None],
  ["John drove a car which Eve bought. John drove a car which Mike bought?",None],
  ["John drove a car which Eve bought. John drove a car Eve bought?",True],
  ["John drove a car which Eve bought. John drove a car Eve saw?",None],
  ["John drove a car which Eve bought. John drove a car Mike bought?",None],
  ["John drove a car Eve bought. John drove a car Eve bought?",True],
  ["John drove a car Eve bought. John drove a car Mike bought?",None],
  ["John drove a car Eve bought. John drove a car Eve saw?",None],
  ["John drove a car Eve bought. John drove a car which Eve bought?",True],
  ["John drove a car Eve bought. John drove a car which Eve saw?",None],
  ["John drove a car Eve bought. John drove a car which Mike bought?",None],

  ["John drove a car Eve bought. Eve drove a car?",None],
  ["John drove a car Eve bought. John drove a car?",True],
 
  ["John drove a car Eve bought. John drove a car which Eve bought?",True],
  ["John drove a car which Eve bought. John drove a car Eve bought?",True],
  ["John drove a red car Eve bought. John drove a car which Eve bought?",True],
  ["John drove a red car which Eve bought. John drove a car Eve bought?",True],
  ["John drove a red car Eve bought. John drove a black car which Eve bought?",None],
  ["John drove a red car which Eve bought. John drove a black car Eve bought?",None],
  ["John drove a car Eve bought. John drove a car which Eve did not buy?",None],
  ["John drove a car which Eve did not buy. John drove a car Eve did not buy?",True],
  ["John did not have a red car which Eve bought. John did not have a red car which Eve bought?",True],
  
  ["John is a man whom Eve liked. John is a man whom Eve liked?",True],
  ["John is a man whom Eve liked. John is a man whom Eve saw?",None],
  ["John is a man whom Eve liked. John is a man whom Mike liked?",None],
  ["John is a man whom Eve liked. John is a man Eve liked?",True],
  ["John is a man whom Eve liked. John is a man Eve saw?",None],
  ["John is a man whom Eve liked. John is a man Mike liked?",None],
  ["John is a man Eve liked. John is a man Eve liked?",True],
  ["John is a man Eve liked. John is a man Mike liked?",None],
  ["John is a man Eve liked. John is a man Eve saw?",None],
  ["John is a man Eve liked. John is a man whom Eve liked?",True],
  ["John is a man Eve liked. John is a man whom Eve saw?",None],
  ["John is a man Eve liked. John is a man whom Mike liked?",None],

  ["John is a man Eve liked. John is a man whom Eve liked?",True],
  ["John is a man whom Eve liked. John is a man Eve liked?",True],
  ["John is a strong man Eve liked. John is a strong man whom Eve liked?",True],
  ["John is a strong man whom Eve liked. John is a strong man Eve liked?",True],
  ["John is a strong man Eve liked. John saw a strong man whom Eve liked?",None],
  ["John is a strong man whom Eve liked. John saw a strong man Eve liked?",None],
  ["John is a man Eve liked. John is a man whom Eve did not like?",False],
  ["John is a man whom Eve did not like. John is a man Eve did not like?",True],
  ["John is not a man whom Eve liked. John is not a man whom Eve liked?",True],

  ["John is a man Eve liked. John is a man?",True],
  ["John is a man Eve liked. Eve liked John?",True], # had a problem with PROPN and not NER for Eve
  ["John is a man Mary liked. Mary liked John?",True],
  ["John is a man Mary liked. Mary liked a man?",True],
  ["John is a man Mary liked. Mary liked the man?",True], # "the man" object finding: cannot detect John is a man.

  ["A man had a car which a woman bought. A man had a car which a woman bought?",True],
  ["A man had a car a woman bought. A man had a car which a woman bought?",True],
  #["A man had a car which a woman bought. A man had a car a woman bought?",True], # wrong parse
  ["A man had a car which a woman bought. A man had a car which a woman liked?",None],
  ["A man had a car which a woman bought. A man had a car which a man bought?",None], 
  ["A man had a car a woman bought. A man had a car which a woman bought?",True],
  ["A man had a car a woman bought. A woman bought a car?",True],
  ["A man had a car a woman bought. The woman bought a car?",True],
  ["A man had a car a woman bought. The woman did not buy a car?",False],
  ["A man had a car a woman bought. A man had a bike?",None],
  ["A man had a car a woman bought. A woman bought a red car?",None],
  ["A man had a car a woman bought. A man bought a car?",None],
  ["A man had a car a woman bought. The man did not have a car?",False],


  ["A man drove a car which a woman bought. A man drove a car which a woman bought?",True],
  ["A man drove a car a woman bought. A man drove a car which a woman bought?",True],
  ["A man drove a car which a woman bought. A man drove a car a woman bought?",True], # ok with 1.4: was wrong parse
  ["A man drove a car which a woman bought. A man drove a car which a woman liked?",None],
  ["A man drove a car which a woman bought. A man drove a car?",True],
  ["A man drove a car which a woman bought. A man drove the car?",True],
  ["A man drove a car which a woman bought. A woman drove the car?",None],
  ["A man drove a car which a woman bought. A woman bought a car?",True],
  ["A man drove a car which a woman bought. A woman bought the car?",True],

  ["A man had a car which a woman bought. A man had a car?",True],
  ["A man had a car which a woman bought. A man had the car?",True],
  ["A man had a car which a woman bought. A woman had the car?",None],
  ["A man had a car which a woman bought. A woman bought a car?",True], 
  ["A man had a car which a woman bought. A woman bought the car?",True],
  ["A man had a car which a woman bought. A man bought the car?",None],


  # capitalization of first noun word

  ["Cars are old. Cars are old?",True], 

  # questions about several objects

  ["A red car is big. A new car is small. A car is red?",True],
  ["A red car is big. A new car is small. A car is new?",True],
  ["A red car is big. A new car is small. A car is old?",None],
  ["A red car is big. A new car is nice. A car is red and big?",True],
  ["A red car is big. A new car is nice. A car is red and nice?",None],

  ["A red car is big. A new car is nice. The car is new?",True],
  ["A red car is big. A new car is nice. The car is red?",None],
  ["A red car is big. A new car is nice. The red car is big?",True],
  ["A red car is big. A new car is nice. The new car is nice?",True],

  ["A red car is big. The red car is strong. The car is red and strong?",True],
  ["A red car is big. The car is strong. The car is red and strong?",True],
  ["A red car is big. The car is strong. The car is black?",None],
  ["A red car is big. The car is strong. A car is black?",None],

   # understanding and questions about non-subject objects

  ["A man had a car which a woman bought. The car was red. A man had a car?",True],
  ["A man had a car which a woman bought. The car was red. The man had the car?",True],
  ["A man had a car which a woman bought. The car was red. The man had a red car?",True],
  ["A man had a car which a woman bought. The car was red. The man had the bike?",None],
  ["A man had a car which a woman bought. The car was red. The man had a black car?",None],
  ["A man had a car which a woman bought. The car was red. The man had the red car?",True],
  ["A man had a car which a woman bought. The car was red. The man had the car which a woman bought?",True],
  ["A man had a car which a woman bought. The car was red. The man had the red car which a woman bought?",True],
  ["A man had a car which a woman bought. The car was red. The man had a car which a boy bought?",None],
  ["A man had a car which a woman bought. The car was red. A man had a red car which a woman bought?",True],
  ["A man had a car which a woman bought. The car was red. The man did not have the red car which a woman bought?",False],
  #["A man had a car which a woman bought. The car was red. A man did not have a red car which a woman bought?",None],  # ok, but what should be the correct interp?
  ["A man had a car which he bought. The car was red. The man bought the red car?",True],
  ["A man had a car which he bought. The car was red. A man bought a red car?",True],
  ["""A man who ate breakfast had a car which a woman bought. The car was red.
     A man who ate breakfast had a red car which a woman bought?""",True],
  ["""A man who ate breakfast had a car.
     The man ate breakfast?""",True],   
  ["""A man who ate breakfast had a car which a woman bought. The car was red. 
     The man who ate breakfast had the red car which the woman bought?""",True],   
  # previously had a problem finding "the car" due to def vs contents of def in object description
  ["""A man who ate breakfast had a car which a woman bought. The car was red.
     The man who ate breakfast had the red car which a woman bought?""",True],      
  ["A man had a car which a woman bought. The car was red. Who had a red car?","The man"],
  ["A man had a car which a nice woman bought. The car was red. Who bought the red car?","The nice woman"],
  ["A man had a car which a nice woman bought. The car was red. Who bought a car?","The nice woman"],
  ["A man had a car which a nice woman bought. The car was red. Who was nice?","The woman"],
  ["A man had a car which a nice woman bought. The car was red. Who was nice and bought a car?","The woman"],
  ["A man had a car which a nice woman bought. The car was red. Who bought the black car?",None],

  ["A man liked a car. The man did not like the car?",False],
  ["A man liked a car which a woman bought. The car was red. A man liked a car?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked the car?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked a red car?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked the bike?",None],
  ["A man liked a car which a woman bought. The car was red. The man liked a black car?",None],
  ["A man liked a car which a woman bought. The car was red. The man liked the red car?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked the car which a woman bought?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked the red car which a woman bought?",True],
  ["A man liked a car which a woman bought. The car was red. The man liked a car which a boy bought?",None],
  ["A man liked a car which a woman bought. The car was red. A man liked a red car which a woman bought?",True],
  ["A man liked a car which a woman bought. The car was red. The man did not like the red car which the woman bought?",False],
  ["A man liked a car which a woman bought. The car was red. The man did not like the red car which a woman bought?",False],
  ["A man liked a car which a woman bought. The car was red. A man did not like a red car which a woman bought?",None],
  ["A man liked a car which he bought. The car was red. The man bought the red car?",True],
  ["A man liked a car which he bought. The car was red. A man bought a red car?",True],
  ["""A man who ate breakfast liked a car which a woman bought. The car was red.
     A man who ate breakfast liked a red car which a woman bought?""",True],
  ["""A man who ate breakfast liked a car.
     The man ate breakfast?""",True],   
  ["""A man who ate breakfast liked a car which a woman bought. The car was red. 
     The man who ate breakfast liked the red car which the woman bought?""",True],   
  # had problem finding "the car" due to def vs contents of def in object description
  ["""A man who ate breakfast liked a car which a woman bought. The car was red.
     The man who ate breakfast liked the red car which a woman bought?""",True],      
  ["A man liked a car which a woman bought. The car was red. Who liked a red car?","The man"],
  ["A man liked a car which a nice woman bought. The car was red. Who bought the red car?","The nice woman"],
  ["A man liked a car which a nice woman bought. The car was red. Who bought a car?","The nice woman"],
  ["A man liked a car which a nice woman bought. The car was red. Who was nice?","The woman"],
  ["A man liked a car which a nice woman bought. The car was red. Who was nice and bought a car?","The woman"],
  ["A man liked a car which a nice woman bought. The car was red. Who bought the black car?",None],

  # Past with did+verb 

  ["A man did have a car. A man had a car?",True],
  ["A man had a car. A man did have a car?",True],
  ["The man has a car. The man does have a car?", True],
  ["A man had a car. A man has a car?",True], # suspicious whether should be true or unknown
  ["A man had a car. The man has a car?",True],  

  # Name gender tests
  ["Mary saw John. She was nice. Who was nice?","Mary"],
  ["Mary saw John. He was nice. Who was nice?","John"],
  ["John saw Mary. She was nice. Who was nice?","Mary"],
  ["John saw Mary. He was nice. Who was nice?","John"],
  # Word gender tests
  ["A mother saw a man. She was nice. Who was nice?","The mother"],
  ["A mother saw a man. He was nice. Who was nice?","The man"],
  ["A boy saw a girl. She was nice. Who was nice?","The girl"],
  ["A boy saw a girl. He was nice. Who was nice?","The boy"],
  # Single/plural tests
  ["The elephants saw a fox. They were nice. The elephants were nice?",True],
  ["The elephants saw a fox. They were nice. The fox was nice?",None],
  ["The elephants saw a fox. They were nice. Who were nice?","The elephants"],
  ["The elephants saw a fox. It was nice.  The fox was nice?",True],
  ["The elephants saw a fox. It was nice.  The elephants were nice?",None],
  ["The fox saw the elephants. They were nice. The elephants were nice?",True],
  ["The fox saw the elephants. They were nice. The fox was nice?",None],
  ["The fox saw the elephants. It was nice.  The fox was nice?",True],
  ["The fox saw the elephants. It was nice.  The elephants were nice?",None],
  ["The fox saw the elephants. It was nice.  What was nice?","The fox"],  
   # prefer the most recent words
  ["A gray elephant was nice. A white elephant was nice. The elephant was cool. The white elephant was cool?",True],
  ["A gray elephant was nice. A white elephant was nice. The elephant was cool. The gray elephant was cool?",None],
  ["A gray elephant was nice. A white elephant was nice. It was cool. The white elephant was cool?",True],
  ["A gray elephant was nice. A white elephant was nice. It was cool. The gray elephant was cool?",None],
  #["A gray elephant saw a fox. It was nice. Who was nice?","The fox."], # hard to determine what does it stand for
  # Animal/thing separation plus gender 
  ["A mother saw a fox. It was nice. Who was nice?","The fox"],
  ["A fox saw a mother. It was nice. Who was nice?","The fox"],
  ["A mother saw a fox. She was nice. Who was nice?","The mother"],
  ["A fox saw a mother. She was nice. Who was nice?","The mother"],
  ["A mother saw a fox. He was nice. Who was nice?","The fox"],
  ["A fox saw a mother. He was nice. Who was nice?","The fox"],
  # These/they
  ["The aunts saw shoes. These were nice. What was nice?","The shoes"],
  ["The aunts saw shoes. They were nice. What was nice?","The aunts"],
  ["The foxes saw aunts. These were nice. What was nice?","The foxes"],
  ["The foxes saw aunts. They were nice. What was nice?","The aunts"],
  # relatedness
  ["A car had a dent. This was deep. What was deep?","A dent"],
  ["A car had a dent. It was fast. What was fast?","The car"],

   # subclass tests
  ["An elephant was strong. The animal lifted a stone. Who lifted the stone?","The elephant"],
  ["An elephant was strong. An animal lifted a stone. Who lifted the stone?","The animal"],
  ["An elephant was strong. The nice animal lifted a stone. Who lifted the stone?","The nice animal"],
  ["A nice elephant was strong. The nice animal lifted a stone. Who lifted the stone?","The nice elephant"],
  ["A nice elephant was strong. A mouse was white. The white animal lifted the stone. Who lifted the stone?","The mouse"],
  ["A nice elephant was strong. A flower was white. The animal lifted the stone. Who lifted the stone?","The nice elephant"],
  ["An old nice grey elephant was strong. The nice animal lifted a stone. Who lifted the stone?","The old nice grey elephant"],
  ["A big old grey elephant was strong. The big animal lifted a stone. The stone was red. The old animal lifted a red stone?",True],
  ["A big old grey elephant was strong. The big animal lifted a stone. The stone was heavy. The old animal lifted a heavy stone?",True],
  ["A big old grey elephant was strong. The big animal lifted a stone. It was red. The grey animal lifted what?","The stone"],
  # ["A big old grey elephant was strong. The big animal lifted a stone. It was red. The grey animal lifted the red stone?",True], # hard to determine "it"

   # More pronoun tests

  ["Mary was in a room. She was in the room?",True], 
  ["Mary was in a room. She was in a room?",True], 
  ["Mary was in a room. She was not in the room?",False], 
  ["Mary was in a room. She was not in a room?",False],
  ["She was in a room. She was in the room?",True],  
  ["An apple was bad. She was in a room. She was in the room?",True],
  ["An apple was bad and she was in a room. She was in the room?",True],
  ["An apple was bad. She was in a room. An apple was in a room?",None],
  ["An apple was bad and she was in a room. An apple was in a room?",None],
  ["John was bad. She was in a room. John was in a room?",None],
  ["She was in a room. Who was in the room?","She"],

  # Set sizes

  # core set size
  ["John has three cars. John has three cars?",True],
  ["If John has three cars, John has three cars?",True],
  ["John has three cars. John has two cars?",False],
  ["If John has three cars, John has two cars?",None], # ?????
  ["John has three nice cars. John has three nice cars?",True],

  ["Animals have two legs. Animals have two legs?",True],
  ["Animals have two legs. Animals have three legs?",False],
  ["Animals have two nice legs. Animals have two nice legs?",True],
  ["Animals have two nice legs. Animals have two long legs?",None],

  ["An animal had two legs. The animal had two legs?",True],
  ["An animal had two legs. The animal had three legs?",False],
  ["An animal had two nice legs. The animal had two nice legs?",True],
  ["An animal had two nice legs. The animal had two long legs?",None],

  ["If John has three cars, John has three cars?",True],
  ["John has three cars. John has two cars?",False],
  ["If John has three cars, John has two cars?",None], # ?????
  ["John has three nice cars. John has three nice cars?",True],

  ["John has three cars which are nice. John has three nice cars?",True], #!!
  ["John has three nice cars. John has three cars?",None],
  ["John has three nice cars. John has three red cars?",None], 
  ["John has three nice big cars. John has three nice big cars?",True],
  ["John has three nice big cars. John has three big nice cars?",True],
 
   # superset size cannot be smaller
  ["John has three nice cars. John has two cars?",False],
  ["John has three big nice cars. John has two nice cars?",False],
  ["John has three big nice cars. John has two big cars?",False],

  # used in condition
  ["If John has three big nice cars, he is rich. John has three nice big cars. John is rich?",True],
  ["If John has three big nice cars, he is rich. John has three nice big cars. Who is rich?","John"],
  ["If John has three big nice cars, he is rich. John has three nice cars. John is rich?",None],
  ["If a person has three big nice cars, he is rich. John has three nice big cars. John is rich?",True],
  
  # member of a set
  ["John has three nice cars. John has a car?",True],
  ["John has three nice cars. John has a nice car?",True],
  ["An animal had two legs. The animal had legs?",True],
  ["An animal had two legs. The animal had a leg?",True],
  ["An animal had two strong legs. The animal had a strong leg?",True],

  # plurals 
  ["John has cars. John has cars?", True],
  ["John has blue cars. John has a car?", True],
  ["John has blue cars. John has a blue car?", True],
  ["John has blue cars. John has one blue car?", "Probably false"],
  ["John has blue cars. John has one car?", None],
  ["John has one car. John has cars?",True],

  ["Animals have legs. Animal has a leg?", True],
  ["Animals have legs. Animal has one leg?", None],

  # .. of .. and ... the ... of ... examples

  ["The head of Mary is clean. The head of Mary is clean?",True],
  ["The head of Mary is clean. A head of Mary is clean?",True],
  ["The head of Mary is clean. A head of Mike is clean?",None],
  ["The head of Mary is clean. The head is clean?",True],
  ["The head of Mary is clean. Mary has a clean head?",True],
  ["The car of Mary is clean. Mary has a car?",True],
  ["The car of Mary is clean. Mike has a car?",None],
  ["The car of Mary is clean. The car of Mike is clean?",None],
  ["The car of Mary is clean. Mary has a clean car?",True],
  ["The car of Mary is clean. Mary has a red car?",None],
  ["The car of Mary is clean. Mary has a clean bike?",None],
  ["A leg of Mary is clean. A leg of Mary is clean?",True],
  ["A leg of Mary is clean. A leg of Mary is long?",None],
  ["A leg of Mary is clean. A leg of Mike is clean?",None],
  ["Mary's head is clean. Mary's head is clean?",True],
  #["Mary's head is clean. The head of Mary is clean?",True],
  ["Mary's head is clean. A head of Mary is clean?",True],
  ["Mary's head is clean. A head of Mike is clean?",None],
  ["Mary's head is clean. The head is clean?",True],
  ["Mary's leg is clean. A leg of Mary is clean?",True],
  #["Mary's leg is clean. The leg of Mary is clean?",True],
  ["Mary's leg is clean. A leg of Mary is long?",None],
  ["Mary's leg is clean. A leg of Mike is clean?",None],
  ["Mary's car is clean. Mary has a car?",True],
  ["Mary's car is clean. Mary has a clean car?",True],
  ["Mary's car is clean. Mary has a red car?",None],
  ["Mary's car is clean. Mary has a clean bike?",None],

  ["Elephant's head is green. John is an elephant. John has a head. John has a green head?", True],
  ["Elephant's head is green. Elephant's head is green?","Maybe true"],
  ["Big elephant's head is green. John is a big elephant. John has a head. John has a green head?",True],
  ["Big elephant's head is green. John is an elephant. John has a head. John has a green head?",None],
  ["A head of an elephant is green. An elephant has a green head?", "Maybe true"],
  ["A head of an elephant is green. All elephants have a head. An elephant has a green head?",True], 
  ["A head of an elephant is green. Elephants have a head. An elephant has a green head?",True],
  ["A head of an elephant is green. Elephants have a head. John is an elephant. John has a green head?",True], 

  ["John saw the head of Mary. John saw the head of Mary?",True],
  ["John saw the head of Mary. John saw a head of Mary?",True],
  ["John saw the head of Mary. John saw the head of Mike?",None],
  ["John saw the head of Mary. John saw a head?",True],
  ["John saw the head of Mary. John saw the hands of Mary?",None],
  ["John saw the car of Mary. Mary had a car?",True],
  ["John saw the head of the elephant. John saw the head of the elephant?",True],
  ["John saw the head of the elephant. John saw the head?",True],
  ["John saw the head of the elephant. John saw a head?",True],
  ["John saw the head of the elephant. John saw the tail of the elephant?",None],
  ["John saw the head of the elephant. John saw a nice head?",None],
  ["John saw a head of an elephant. John saw a head of an elephant?",True],
  ["John saw a head of an elephant. John saw the head of the elephant?",None], # should not be true
  ["John saw a head of an elephant. John saw the head?",True],
  ["John saw a head of an elephant. John saw a head?",True],
  ["John saw a head of an elephant. John saw the tail of the elephant?",None],
  ["John saw a head of an elephant. John saw a tail of an elephant?",None],
  ["John saw a head of an elephant. John saw a nice head?",None],
  ["John saw Mary's head. John saw Mary's head?",True],
  ["John saw Mary's head. John saw a head of Mary?",True],
  ["John saw Mary's head. John saw Mike's head?",None],
  ["John saw Mary's head. John saw a head of Mary?",True],
  ["John saw Mary's head. John saw the head of Mike?",None],
  ["John saw Mary's head. John saw a head?",True],
  ["John saw Mary's head. John saw the hands of Mary?",None],
  ["John saw Mary's car. Mary had a car?",True],
  ["John saw Mary's clean car. Mary had a clean car?",True],
  ["John saw Mary's clean car. Mary had a red car?",None],
  ["John saw Mary's clean car. Mary had a clean bike?",None],
  ["John saw elephant's head. John saw elephant's head?",True],
  #["John saw elephant's head. John saw the head of the elephant?",True],
  ["John saw elephant's head. John saw the head?",True],
  ["John saw elephant's head. John saw a head of an elephant?",True],
  ["John saw elephant's head. John saw a head of a tiger?",None],
  ["John saw elephant's head. John saw a head?",True],
  ["John saw elephant's head. John saw the tail of the elephant?",None],
  ["John saw elephant's head. John saw a nice head?",None],
  ["John saw a head of an elephant. John saw a head of the elephant?",True],
  ["John saw a head of an elephant. John saw a head of an elephant?",True],
  ["John saw a head of the elephant. John saw a head of the elephant?",True],
  ["John saw a head of the elephant. John saw a head of an elephant?",True],
  ["John saw a head of an elephant. John saw a head of the bear?",None],
  ["John saw a head of an elephant. John saw a head of a bear?",None],
  ["John saw a head of the elephant. John saw a head of the bear?",None],
  ["John saw a head of the elephant. John saw a head of a bear?",None],
  ["John saw a head of an elephant. John saw a tail of the elephant?",None],
  ["John saw a head of an elephant. John saw a tail of an elephant?",None],
  ["John saw a head of the elephant. John saw a tail of the elephant?",None],
  ["John saw a head of the elephant. John saw a tail of an elephant?",None],
  ["John saw a twig of an elephant. The elephant had a twig?",True],
  ["John saw a twig of an elephant. The elephant had a spoon?",None],
  ["John saw a twig of an elephant. An elephant had a twig?",True],
  ["John saw a twig of an elephant. An elephant had a spoon?",None],
  ["John saw the twig of an elephant. The elephant had a twig?",True],
  ["John saw the twig of an elephant. The elephant had the twig?",True],
  ["John saw the twig of an elephant. The elephant had a spoon?",None],
  ["John saw a blue head of a red elephant. John saw a blue head of a red elephant?",True],
  ["John saw the blue head of the red elephant. John saw the blue head of the red elephant?",True],
  ["John saw the blue head of the red elephant. John saw the red head of the red elephant?",None],
  ["John saw the blue head of the red elephant. John saw the red head of the blue elephant?",None],
  ["John saw a blue head of a red elephant. John saw a blue head?",True],
  ["John saw a blue head of a red elephant. John saw the blue head?",True],
  ["John saw a blue head of a red elephant. John saw the head?",True],
  ["John saw a blue head of a red elephant. John saw a red head?",None],
  ["John saw a blue head of a red elephant. John saw a blue tail?",None],
  ["John saw a blue head of a red elephant. John saw the blue head?",True],
  ["John saw a blue head of a red elephant. John saw a head of an elephant?",True],
  ["John saw a blue head of a red elephant. John saw a head of the red elephant?",True],

  ["The hand of a man moved a wheel. The hand of a man moved a wheel?",True],
  ["The hand of a man moved a wheel. The man had a hand?",True],
  ["The hand of a man moved a wheel. A man had a hand?",True],
  ["The hand of a man moved a wheel. A man had a wheel?",None],
  ["The hand of a man moved a wheel. A man was a wheel?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A blue hand of a man moved a wheel of a large wheelbarrow?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A blue hand of an elephant moved a wheel of a large wheelbarrow?",None],
  ["The blue hand of a man moved a wheel of the large wheelbarrow. A blue hand of a man moved a wheel of a large wheelbarrow?",True],
  ["The blue hand of a man moved the wheel of the large wheelbarrow. The blue hand of a man moved the wheel of the large wheelbarrow?",True],
  ["The blue hand of a man moved the wheel of the large wheelbarrow. The blue hand of a man moved the large wheelbarrow?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A hand moved a wheel?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A hand moved a wheelbarrow?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A blue hand moved a wheel?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A right hand moved a wheel?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A leg moved a wheel?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A hand moved a wheel of a small wheelbarrow?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The man had a hand?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The man had a blue hand?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The man had a red hand?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The man had a wheel?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The wheelbarrow had a wheel?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A large wheelbarrow had the wheel?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. A small wheelbarrow had the wheel?",None],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The large wheelbarrow had a wheel?",True],
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The small wheelbarrow had a wheel?",None], 
  ["A blue hand of a man moved a wheel of a large wheelbarrow. The wheelbarrow had a hand?",None],

  ["The blue hand of a man moved the wheel of the large wheelbarrow. Mary is a man?",None],
  ["The blue hand of a man moved a wheel of the large wheelbarrow. Mary is a man?",None],
  ["The hand of a man is nice. Mary is a man?",None],
  ["A hand of a man moved a wheel. Mary is a man?",None],
  ["The hand of a man moved a wheel. Mary is a man?",None],

  ["John ate berries with the edge of a spoon. John ate berries with the edge of a spoon?",True],
  ["John ate berries with an edge of a spoon. John ate berries with an edge of a spoon?", True],
  ["John ate berries with the edge of a spoon. John ate berries with the edge of a fork?",None],
  ["John ate berries with the edge of a spoon. John ate berries with the tip of a spoon?",None],
  ["John ate berries with an edge of a spoon. John ate berries with an edge?",True],
  ["John ate berries with an edge of a spoon. John ate berries with a tip?",None],
  ["John ate berries with an edge of a spoon. A spoon had an edge?",True],
  ["John ate berries with an edge of a spoon. The spoon had the edge?",True],
  ["John ate berries with the edge of the spoon. The spoon had the edge?", True],
  ["John ate berries with the edge of the spoon. The spoon had the tip?", None],
  # ["John ate berries with the edge of a spoon. The spoon had the edge?", True], # parses smoewhat incorrectly
  ["John ate berries with the edge of a spoon. John is a spoon?",None],
  ["John ate berries with the edge of a spoon. John is an edge?",None],
  ["John ate berries with the edge of a spoon. Berries have an edge?",None],


  # obl and compound sentences
   
  ["Bears eat berries in a forest. Bears eat berries in a forest?",True],
  ["Bears eat berries in a forest. Bears eat berries in a big forest?",None],
  ["Bears eat berries in a forest. Bears eat berries in a field?",None],
  ["Bears do not eat berries in a forest. Bears eat berries in a forest?",False],
  ["Bears ate berries in a forest. Bears did not eat berries in a forest?",False],
  ["Bears ate berries in a forest. Bears did not eat berries in a field?",None],

  ["Bears ate nice berries in a big forest which was bought by Mary. Bears ate berries in the forest which was bought by her?",True],
  ["Bears ate nice berries in a big forest which was bought by Mary. Bears ate berries in the forest which was bought by a man?",None],
  ["Bears ate nice berries in a big forest which was bought by Mary. Bears ate berries in the forest?",True],
  ["Bears ate berries in the forest which was bought by Mary. The forest was bought by Mary?",True],
  
  ["Bears ate berries in a forest which was bought by Mary. Bears ate berries in the forest bought by Mary?",True],
  ["Bears ate berries in a forest which was bought by Mary. Bears ate berries in the forest bought by John?",None],
  ["Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears ate?", True],
  ["Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears drank?", None],
  ["Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears ate berries?", True],
  ["Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears ate honey?", None],

  ["John ate berries in a forest with a spoon. John ate berries in a forest with a spoon?",True],
  # ["John ate berries in a forest with a spoon. John ate berries with a spoon in a forest?",True], # indeed should not be true: spoon is in a forest?
  ["John ate berries in a forest with a spoon. John ate berries in a field?",None],
  ["John ate berries in a forest with a spoon. John ate berries in a nice forest with a spoon?",None],
  ["John ate berries in a forest with a spoon. John ate berries in a nice forest?",None],
  ["John ate berries in a forest with a spoon. John ate berries with a spoon in a nice forest?",None], # OK with version 1.4; was ud parsing wrong
  ["John ate berries with the help of a spoon. John ate berries with the help of a spoon?", True],
  ["John ate berries with the help of a spoon. John ate berries with the help of a spade?", None],

  ["John lives in a car which is red. The car is red?", True],
  ["John lives in a car which is red. The car is nice?", None],
  ["John lives in a car which is red. John lives in a red car?", True],
  ["John lives in a car which is red. John lives in a nice car?", None],
  # ["John lives in a car which is red and was bought by Mary. The red car was bought by Mary?", True], # wrong parse
  ["John lives in a car which is red and was bought by Mary. The nice car was bought by Mary?", None],
  ["John lives in a car which is red and was bought by Mary. The car was bought by John?", None],

  ["""John has a car which is nice and red. The car is red and nice?""", True],
  ["""John has a car which is nice and red. The red car is nice?""", True],
  ["""John has a car which is nice and red. The big car is nice?""", None],
  ["""John has a red car which is nice and big. The nice car is big and red?""", True],
  ["""John has a red car which is nice and big. The car is good?""", None],  
  ["John lives in a nice car which was red and was bought by Mary. John lives in a nice yellow car?",None],
  ["John lives in a nice car which was red and was bought by Mary. John lives in a car which was bought by Mary?",True],  
  ["John lives in a car which is red and was bought by Mary. The car was bought by John?",None],
  ["John lives in a red car bought by Mary. Mary bought the car?",True],
  ["John lives in a red car bought by Mary. Mary bought the car where John lives?",True],
  ["John lives in a red car bought by Mary. Mary bought the car where John ate?",None],
  ["John lives in a red car bought by Mary. Mary bought the car where Mike lives?",None],

  # ["John bought a painting in his house. The painting was in his house?",True],  # parsed as John bought in the house
  # ["John bought the painting in his house. The painting was in his house?",True], # parsed as John bought in the house
  # ["John bought the painting in his house. John was in his house?",True], # needs additional axioms and reasoning
  ["John shot an elephant in his pyjamas. The elephant was in his pyjamas?",None],
  ["John shot an elephant in his pyjamas. John shot in his pyjamas?",True],

  ["Mike ate berries in the forest bought by Mary. Mike ate berries in the forest bought by Mary?",True],
  ["Mike ate berries in the forest bought by Mary. Mike ate berries in the forest bought by John?",None],
  ["Mike ate berries in the forest which was bought by Mary. Mike ate berries in the forest which was bought by Mary?",True],
  ["Mike ate berries in the forest which was bought by Mary. Mike ate berries in the forest which was bought by John?",None],
  ["Mike ate berries in the forest which was bought by Mary. Mike ate berries in the forest bought by Mary?",True],
  ["Mike ate berries in the forest which was bought by Mary. Mike ate berries in the forest bought by John?",None],

  ["Bears ate berries in the forest bought by Mary. Bears ate berries in the forest bought by Mary?",True],
  ["Bears ate berries in the forest bought by Mary. Bears ate berries in the forest bought by John?",None],
  ["Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest which was bought by Mary?",True],
  ["Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest which was bought by John?",None],
  ["Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest bought by Mary?",True],
  ["Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest bought by John?",None],      

  # conjunction usage with can, have etc

  ["John and Eve can swim. Mark and John are animals. Who can swim and is an animal?","John"],
  ["John and Eve can swim. Mark and John are animals. Who is an animal and can swim?","John"],
  ["John and Eve can swim. Mark is an animal. Who can swim and is an animal?",None],

  # conjunction usage with have 

  ["Cars are nice. Cars have brakes. Cars are nice and have brakes?", True],
  ["Cars are nice. Cars are nice and have brakes?", None],
  ["Cars have brakes. Cars are nice and have brakes?", None],
  ["Cars are nice and cool and have brakes. Cars are nice and cool and have brakes?",True],
  ["Cars are nice and cool and have brakes. Cars have brakes and are nice and cool?",True],
  ["Cars are cool and have brakes. Cars are nice and cool and have brakes?",None],
  ["Cars are nice and cool. Cars have brakes and are nice and cool?",None],
  ["Cars have fenders. Cars have brakes. Cars have brakes and fenders?",True],
  ["Cars have fenders. Cars have brakes and fenders?",None],
  ["Cars have brakes. Cars have brakes and fenders?",None],

  # no subject cases; with nsubj:pass and VerbForm=Part 

  ["John is defeated. John defeated?",None],
  ["John is defeated. Mike is defeated?",None],
  ["John is defeated. John is defeated?",True],
  ["John is defeated. Who is defeated?","John"],
  ["John is defeated. John is not defeated?",False],
  ["John and Mike were defeated. Who defeated John?","Some unknown."],
  ["John and Mike were defeated. Who defeated John and Mike?",None],
  ["An apple was eaten. John ate a pear. What was eaten?","The apple and the pear."],
  ["An apple was eaten. John ate a pear. What did eat?","Some unknown and John."], 
  ["""If an animal is cool and defeated then it is green. 
   John is an animal. John is cool. 
   Mike is an animal. Mike is cool. John is defeated. John is green?""",True],
  ["""If an animal is cool and defeated then it is green. 
   John is an animal. John is cool. 
   Mike is an animal. Mike is cool. John is defeated. Who is green?""","John"], 
  ["""If an animal is cool and defeated then it is green. 
   John is an animal. John is cool. 
   Mike is an animal. Mike is cool. John is defeated. John is not green?""",False], 
  ["""If an animal is cool and defeated then it is green. 
   John is an animal. John is cool. 
   Mike is an animal. Mike is cool. John is defeated. Mike is green?""",None],
  ["""If an animal is cool and defeated then it is green. 
   John is a cool defeated animal. 
   Mike is an animal. Mike is cool. John is green?""",True],
  ["""If an animal is cool and defeated then it is green. 
   John is a cool defeated animal. 
   Mike is an animal. Mike is cool. John is not green?""",False],  
  ["""If an animal is cool and defeated then it is green. 
   John is a defeated animal. 
   Mike is an animal. Mike is cool. John is green?""",None],  
  ["If someone is a bird and wounded then they are abnormal. John is wounded. John is a bird. John is abnormal?",True],
  ["If someone is a bird and wounded then they are abnormal. John is a bird. John is abnormal?",None],
  # ["John was nice and defeated. John was defeated?",True], # Fails with stanza 1.4
  # ["John was nice and defeated. John was defeated and nice?",True], # first part of parse goes wrong: needs fixing: see next sentence
  #["John was nice and defeated. John was nice and defeated?",True], # Fails with stanza 1.4
  ["John was nice and defeated. John was nice?",True],
  ["John was defeated. John was defeated?",True],
  ["John is defeated. John was defeated?",None],
  ["John was defeated. John is defeated?",None],
  ["John is defeated. John is defeated?",True],
  ["""If someone is a nice animal and badly defeated then they are weak. John and Mike are nice animals. 
    John is badly defeated. John is weak?""",True],
  ["""If someone is a nice animal and badly defeated then they are weak. John and Mike are nice animals. 
    John is badly defeated. Mike is weak?""",None],  
  ["""If someone is a nice animal and badly defeated then they are weak. John is a nice animal. 
    Mike is badly defeated. Mike is weak?""",None],  

  # NER cases sometimes needing NER fixing
   
  ["Muggles cannot disappear. Mr Dursley is a Muggle. Mr Dursley can disappear?",False], 
  ["Muggles can not disappear. Mr Dursley is a Muggle. Mr Dursley can disappear?",False], 
  #["Americans cannot disappear. Mr Dursley is an american. Mr Dursley can disappear?",False], 
  ["Americans cannot disappear. Mr Dursley is an American. Mr Dursley can disappear?",False], 
  ["Americans can not disappear. Mr Dursley is an American. Mr Dursley can disappear?" ,False],  
  ["Catholics can not disappear. Mr Dursley is a catholic. Mr Dursley can disappear?",False], 

  # Tests inspired by UD web docs examples 

   # nsubj docs examples
  ["Clinton defeated Dole. Clinton defeated Dole?",True],
  ["Clinton defeated Dole. Clinton defeated Mike?",None],
  ["Dole was defeated by Clinton. Dole was defeated by Clinton?",True],
  ["Dole was defeated by Clinton. Dole was defeated by Mike?",None],
  ["Clinton defeated Dole. Dole was defeated by Clinton?",True],
  ["Clinton defeated Dole. Dole was defeated by Mike?",None],
  ["Dole was defeated by Clinton. Clinton defeated Dole?",True],
  ["Dole was defeated by Clinton. Mike defeated Dole?",None],
  ["The car is red. The car is red?",True],
  ["The car is red. The car is nice?",None],
  ["Sue is a true patriot. Sue is a true patriot?",True],
  ["Sue is a true patriot. Sue is a nice patriot?",None],
  ["Sue is a true patriot. Sue is a true driver?",None],
  ["We are in the barn. We are in the barn?",True],      
  ["We are in the barn. We are in the shop?",None],
  ["We are in the barn. We are on the barn?",None],
  ["Agatha is in trouble. Agatha is in trouble?",True],
  ["Agatha is in trouble. Agatha is in the barn?",None],
  ["Agatha is in trouble. Agatha is through trouble?",None],
  ["There is a ghost in the room. There is a ghost in the room?",True],
  ["There is a ghost in the room. A ghost is in the room?",True],  
  ["There is a ghost in the room. There is a lamp in the room?",None],
  ["There is a ghost in the room. There is a ghost in the barn?",None],
  # ["These links present the many viewpoints that existed. These links present the many viewpoints that existed?",True], # Fails around stanza 1.4 intro
  ["These links present the many viewpoints that existed. These links present the lemmas that existed?",None],
  #["These links present the many viewpoints that existed. These links present the many viewpoints?",True],  # Fails around stanza 1.4 intro

  # Different forms of questions

  # Is it / It is / true / false questions

  ["John is nice. Is it true that John is nice?",True],
  ["John is nice. Is it false that John is nice?",False],
  ["John is nice. It is true that John is nice?",True],
  ["John is nice. Is it false that John is nice?",False],

  # What does and related questions

  ["John smokes tobacco with a probability 0.8. What does John smoke?","Likely a tobacco"],
  ["John smokes tobacco with a probability 0.8. John smokes?","Likely true"],
  ["John smokes tobacco with a probability 80 percent. Does John smoke?","Likely true"],
  ["John smokes tobacco with a probability 10 percent. Does John smoke?",None],

  # Who is questions

  ["John Sweeney is a car. John Smith is bad. Who is John?","John Smith is bad."],
  ["John Sweeney is a car. John Smith is bad. Who is Sweeney?","John Sweeney is a car."],
  ["John Sweeney is a car. John Smith is bad. Who is John Sweeney?","John Sweeney is a car."],
  ["John is a car. John is bad. Who is John?","John is a bad car."],
  ["John is a man. John is probably not bad. Who is John?","John is a not bad man."],
  ["John is not a car. John is bad. Who is John?","John is bad."],
  ["John Sweeney is a car. Who is John?","John Sweeney is a car."],
  ["John Sweeney is not a car. John is not bad. Who is John?","John Sweeney is not bad."],
  ["John Sweeney is not a car. Who is John?",None],
  ["John Sweeney is a car. Who is Mary?",None],
  ["John Sweeney is cool and bought a car. John is a bad baby man. John is not big. Who is John?","John Sweeney is a not big cool bad baby man."],

  # Who/Whom is_of questions

  ["Ellen is afraid of John. What is Ellen afraid of?","John"],
  ["Ellen is afraid of John. Who is Ellen afraid of?","John"],
  ["Ellen is afraid of John. Whom is Ellen afraid of?","John"],
  ["Ellen is afraid of John. Ellen is afraid of whom?","John"],
  ["Ellen is afraid of John. Ellen is afraid of who?","John"],
  ["Ellen is fond of John. Who is Ellen afraid of?",None],
  ["Ellen is fond of John. Whom is Ellen afraid of?",None],
  ["Ellen is fond of John. Ellen is afraid of who?",None],

  # Which questions
   
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which man has an apple?""","John"],
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which has a pear?""","Mike"],    
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which is bad?""","Greg"],    
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which man has a potato?""",None],    
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which man is nice?""","John and Mike"],    
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which man is bad?""","Greg"], 
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which nice man has a pear?""","Mike"],         
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which bad man has a pear?""",None], 
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which nice man has an apple or a pear?""","John and Mike"],     
  ["""John is a nice man. John has an apple. Mike is a nice man. Greg is a bad man. Mike has a pear. 
      Which nice man has an apple and a pear?""",None],   
  ["""Squirrels can fly. Foxes cannot fly. Squirrels and foxes are animals. 
      Which animal can fly?""","A squirrel"],    
  ["""Squirrels can fly. Foxes cannot fly. Squirrels and foxes are animals. 
      Which animal cannot fly?""","A fox"],    
  ["""Squirrels can fly. Foxes cannot fly. Squirrels and foxes are animals. 
      Which can fly?""","A squirrel"], 
  ["""Squirrels can fly. Foxes cannot fly. Squirrels and foxes are animals. 
      Which table can fly?""",None],    
  
  # Where questions

  ["John is in a box. Mark is in a house. Where is John?","In the box."],
  ["John is in a box. Mark is in a house. Where is Mark?","In the house."],
  ["John is on a box. Mark is on a house. Where is John?","On the box."],
  ["John is on a box. Mark is on a house. Where is Mark?","On the house."],
  ["John is at a box. Mark is at a house. Where is John?","At the box."],
  ["John is at a box. Mark is at a house. Where is Mark?","At the house."],
  ["John is near a box. Mark is near a house. Where is John?","Near the box."],
  ["John is near a box. Mark is near a house. Where is Mark?","Near the house."],
  ["John is under a box. Mark is under a house. Where is John?","Under the box."],
  ["John is under a box. Mark is under a house. Where is Mark?","Under the house."],
  ["John is above a box. Mark is above a house. Where is John?","Above the box."],
  ["John is above a box. Mark is above a house. Where is Mark?","Above the house."],

  ["A car is in a box and in a house. Where is the car?","In the house and in the box."],
  ["A car was in a box and in a house. Where was the car?","In the house and in the box."],
  ["John is in the box and in the red house. Where is John?","In the box and in the red house."],
  ["John is in a box and house. Mark is near the house. Where is John?","In the house and in the box."],
  ["John is in a box and house. Mark is near the house. Where is Mark?","Near the house."],
  ["If John is in a box, he is in the house. John is in the box. Mark is not in the box. Where is John?","In the box and in the house."],
  ["If a car is in a box, the car is in the house. A red car is in the box. Where is a car?", "In the box and in the house."],

  ["John is not in the box. John is in the red house. Where is John?","In the red house."],
  ["The black car is not in the box. The car is in the red house. Where is the car?","In the red house."],

  ["John is in a box. John is near a spoon. John is on the floor. Where is John?","Near the spoon, in the box and on the floor."],
  ["John is in a box. John is near a spoon. John is on the floor. John is not in the box. Where is John?","On the floor and near the spoon."],
  ["John is in a box. John is near a spoon. John is on the floor. John is not in a box. Where is John?","On the floor and near the spoon."], # was a problem

  ["""John is in a red car. John is a man. The red car is in the house. The black car is in the street. 
      The street is in Tallinn. Where is the black car?""","In the street and in Tallinn."],
  ["""John is in a red car. John is a man. The red car is in the house. The black car is in the street. 
      The street is in Tallinn. Where is the red car?""","In the house."],    
  ["""John is in a red car. John is a man. The red car is in the house. The black car is in the street. 
      The street is in Tallinn. Where is a car?""","In the house, in the street and in Tallinn."],    
  ["""John is in a red car. John is a man. The red car is in the house. The black car is in the street. 
      The street is in Tallinn. Where is the man?""","In the red car and in the house."],
  
  # Complex location indication sentences plus where questions

  ["John is in the box which is in the red house. Where is John?","In the box and in the red house."],
  ["John is in the box which is in the red house. Where is the box?","In the red house."],
  ["John is in the box which is near the red house. Where is John?","In the box."],
  ["John is in the box which is near the red house. Where is the box?","Near the red house."],

  ["John is in the box near the red house. Where is John?","In the box."],
  ["John is in the box in the red house. Where is John?","In the box and in the red house."],
  ["John is in the box near the red house. Where is the box?", "Near the red house."],

  ["John is in the box at the red house. A box is at a house?",True],
  ["John is in the box at a red house. The box is at a house?",True],
  ["John is in the box at a red house. The red box is at a house?",None],
  ["John is in the box at a red house. The box is at a blue house?",None],
  ["John is in a box at the red house. A box is at a house?",True],
  ["John is in a box at the red house. A box is at a house?",True], 
  ["John is in a box at the red house. The box is at a house?",True],
  ["John is in a box at the red house. A box is at the red house?",True],

  # Location of general terms 
   
  # ["""Birds are in the box. Where are the birds?""","In the box."], # fails; maybe should fail? 
  ["""Birds are in the box. Where are birds?""","In the box."],
  ["""The birds are in the box. Where are the birds?""","In the box."],
  ["""The birds are in the box. Where are birds?""","In the box."],
  ["Birds near Tallinn are nice. John is near Tallinn. What is near Tallinn?","A bird near Tallinn"],
  ["Birds near Tallinn are nice. John is near Tallinn. Who is near Tallinn?","John"],
  ["Birds near Tallinn are nice. John is near Tallinn. What is nice?","A bird near Tallinn"],
  ["Birds near Tallinn are nice. John is near Tallinn. John is a bird. Who is nice?","John"],
  ["Birds near Tallinn are nice. John is a bird who is near Tallinn. Who is nice?","John"],

  # Simple confidences combined with the location

  ["Probably John is in a cave. Where is John?","Probably in the cave"],
  ["John is probably in a cave. Where is John?","Probably in the cave"],
  ["John is in a cave with a probability 90%. Where is John?","Likely in the cave"],
  ["John is in a cave with a probability 10%. Where is John?",None],
  ["John is in a cave with a probability 10%. John is in the cave?","Likely false"],
  ["John is in a cave with a probability 10%. John is in a cave?","Likely false"],

  # Location of actions

  ["""John ate candy in a house. John ate meat in a room. Where did John eat candy?""","In a house"],
  ["""John ate candy in a house. John ate meat in a room. Where did John eat meat?""","In a room"],
  ["""John ate candy in a house. John ate meat at a room. Where did John eat?""","At a room and in a house"],
  ["""John jumped high in a room. John jumped low near the garage. Where did John jump?""","In a room and near the garage"],
  ["""John jumped high in a room. John jumped low near the garage. Where did John jump high?""","In a room"],
  ["""John jumped high in a room. John jumped low near the garage. Where did John jump low?""","Near the garage"],  
  ["""John jumped high in a room. John jumped low near the garage. Where did John jump quickly?""",None],
  
  # Basic when questions
  
  ["During 1800, John jumped in a house. During 1800, John jumped?",True],
  ["During 1800, John jumped in a house. During 1801, John jumped?",None],
  ["During 1800, John jumped in a house. When did John jump?","During the year 1800"],
  ["During 1800, John jumped in a house. Where did John jump?","In a house"],
  ["Before 1900, John jumped in a house. When did John jump?","Before the year 1900"],
  ["Before 1900, John jumped in a house. After 1902, John ate in a house. When did John jump?","Before the year 1900"],
  ["Before 1900, John jumped in a house. After 1902, John sat in a house. When did John sat?","After the year 1902"],
  ["On Monday, John jumped in a house. Where did John jump?","In a house"],
  ["On Monday, John jumped in a house. When did John jump?","On Monday"],

  # Basic measures and what questions

  ["Nile's length is 80 kilometers. The length of Nile is 80 kilometers?",True],
  ["Nile's length is 80 kilometers. The length of Nile is 90 kilometers?",False],
  ["Nile's length is 80 kilometers. Amazon's length is 20 kilometers. What is 80 kilometers long?","Nile"],
  ["Nile's length is 80 kilometers. Amazon's length is 20 kilometers. What has the length 20 kilometers?","Amazon"],   
  ["Car's length is 80 kilometers. The length of the car is 80 kilometers?",True],
  ["Car's length is 80 kilometers. The length of the car is 90 kilometers?",False],
  ["Car's length is 80 kilometers. Bike's length is 10 kilometers. What is 80 kilometers long?","A car"],
  ["Car's length is 80 kilometers. Bike's length is 10 kilometers. What has the length 10 kilometers?","A bike"],
  ["The car's length is 80 kilometers. The length of the car is 80 kilometers?",True],
  ["The car's length is 80 kilometers. The length of the car is 90 kilometers?",False],
  ["The car's length is 80 kilometers. The bike's length is 10 kilometers. What is 80 kilometers long?","The car"],
  ["The car's length is 80 kilometers. The bike's length is 10 kilometers. What has the length 10 kilometers?","The bike"],
  ["The red car's length is 80 kilometers. The length of the blue car is 80 kilometers?",None],
  ["The red car's length is 80 kilometers. The length of the car is 90 kilometers?",False],
  ["Emajogi's length is 80 kilometers. Emajogi's length is 80 kilometers?",True],
  ["Emajogi's length is 80 kilometers. Emajogi's length is 90 kilometers?",False],
  ["Emajogi's length is 80 kilometers. The length of Emajogi is 80 kilometers?",True],
  ["Emajogi's length is 80 kilometers. The length of Emajogi is 90 kilometers?",False],
  ["Emajogi's length is 80 kilometers. What is 80 kilometers long?","Emajogi"],
  ["Emajogi's length is 80 kilometers. What is 200 kilometers long?",None],
  ["The length of Emajogi is 80 kilometers. Emajogi is 80 kilometers long?",True],
  ["The length of Emajogi is 80 kilometers. Emajogi is 90 kilometers long?",False],
  ["The nice Emajogi is 80 kilometers long. The nice Emajogi is 80 kilometers long?",True],
  ["The nice Emajogi is 80 kilometers long. The nice Emajogi is 90 kilometers long?",False],
  ["The length of Nile is 10 meters. What has the length 10 meters?","Nile"],
  ["Nile is 10 meters long. What is 10 meters long?","Nile"],
  ["Nile is 10 meters long. Emajogi is 20 meters long. The nice river is 100 meters long. What is 100 meters long?", "The nice river"],
  ["The red straw is 10 meters long. The red straw is 10 meters long?",True],
  ["The red straw is 10 meters long. The red straw is 20 meters long?",False], 
  ["The red straw is 10 meters long. The blue straw is 5 meters long. What is 5 meters long?","The blue straw"], 
  ["The red straw is 10 meters long. The blue straw is 5 meters long. What is 10 meters long?","The red straw"],
  ["John has the length 2 meters. John is 2 meters long?",True],
  ["John has the length 2 meters. John is 3 meters long?",False],
  ["John has length of 2 meters. John is 2 meters long?",True],
  ["John has length of 2 meters. John is 3 meters long?",False],
  ["John's length is 2 meters. John is 2 meters long?",True],
  ["The price of the red car is 2 dollars. The price of the red car is 2 dollars?",True],
  ["The price of the red car is 2 dollars. The price of the red car is 3 dollars?",False],
  ["The price of the red car is 2 dollars. The price of the red car is 2 euros?",None],
  ["The red car costs 2 dollars. The price of the red car is 2 dollars?",True],
  ["The red car costs 2 dollars. The price of the red car is 3 dollars?",False],
  ["The red car has a price of two dollars. The red car costs two dollars?",True],
  ["The red car has the price two dollars. The red car costs two dollars?",True],
  ["The red car has the price two dollars. The red car costs three dollars?",False],
  ["The red car has the price two dollars. The blue car costs three dollars. What costs 3 dollars?","The blue car"],
  ["The red car has the price two dollars. The blue car costs three dollars. What has the price 2 dollars?","The red car"]  

]