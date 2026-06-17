# Core test suite — CHALLENGING split (>=2 total errors across 4 experiments x 4 LLMs;
# formerly "not-easy"). Union of the MEDIUM (2-3 errors) and HARD (>=4 errors) splits.
# Auto-generated from tests_core.py via difficulty_matrix.json; do not edit by hand.

[
[14, 'John is tall and not tall?', False],

[15, 'John is a tall man and not a tall man?', False],

[17, 'John has a car and does not have a car?', False],

[26, 'Big or strong elephants are nice. John is an elephant. John is nice?', None],

[71, 'Elephants have either trunks or tails. John is an elephant. John has a tail and a trunk?', False],

[79, 'A man was yellow. A man was yellow?', True],

[82, 'An elephant was strong. An animal lifted a stone. Who lifted the stone?', ['The animal', 'The strong elephant', 'The elephant']],

[103, 'John saw Mary. He was nice. Who was nice?', 'John'],

[105, 'A mother saw a man. He was nice. Who was nice?', ['The man', 'The nice man']],

[106, 'A boy saw a girl. She was nice. Who was nice?', ['The girl', 'The nice girl']],

[107, 'A boy saw a girl. He was nice. Who was nice?', ['The boy', 'The nice boy']],

[113, 'A fox saw a mother. It was nice. Who was nice?', ['The fox', 'The mother.', 'The nice mother']],

[122, 'The elephants saw a fox. They were nice. The elephants were nice?', True],

[124, 'The elephants saw a fox. They were nice. Who were nice?', 'The elephants'],

[127, 'The fox saw the elephants. They were nice. The elephants were nice?', True],

[136, 'An apple was bad. She was in a room. An apple was in a room?', None],

[137, 'An apple was bad and she was in a room. An apple was in a room?', None],

[138, 'John was bad. She was in a room. John was in a room?', None],

[139, 'She was in a room. Who was in the room?', 'She'],

[140, 'The aunts saw shoes. These were nice. What was nice?', 'The shoes'],

[144, 'A gray elephant was nice. A white elephant was nice. The elephant was cool. The gray elephant was cool?', None],

[146, 'A gray elephant was nice. A white elephant was nice. It was cool. The gray elephant was cool?', None],

[149, 'Bears ate berries in the forest bought by Mary. Bears ate berries in the forest bought by Mary?', True],

[150, 'Bears ate berries in the forest bought by Mary. Bears ate berries in the forest bought by John?', None],

[153, 'The boy lost his backpack. Who does the backpack belong to?', 'The boy.'],

[155, 'The students brought their books. Whose books were they?', ["The students'.", 'The students.']],

[167, 'Tom and Eve greeted each other. Eve greeted Tom?', True],

[169, 'The boys helped themselves. The boys helped the boys?', True],

[170, 'The girls admired themselves. The girls admired the girls?', True],

[196, ' Elephants have not red trunks. John is an elephant. John has a trunk?', True],

[222, 'John ate berries with an edge of a spoon. A spoon had an edge?', True],

[223, 'John ate berries with an edge of a spoon. The spoon had the edge?', True],

[229, "Mary's sister owns a house. Who owns a house?", "Mary's sister."],

[235, "The handle of Mary's suitcase broke. Mary had a suitcase?", True],

[242, 'The owner of the horse of Mike smiled. Mike had a horse?', True],

[243, 'The brother of the friend of Eve arrived. Eve had a friend?', True],

[245, "John saw the mother of the boy. John saw a boy's mother?", True],

[248, "Mary's uncle arrived. Who has an uncle?", 'Mary.'],

[252, 'The toy of the child was broken. Was the toy intact?', False],

[275, "Elephant's head is green. John is an elephant. John has a head. John has a green head?", True],

[276, 'The head of every elephant is green. John is an elephant. John has a green head?', True],

[278, 'A head of an elephant is green. An elephant has a green head?', True],

[294, 'John saw the head of the elephant. John saw the head of the elephant?', True],

[306, "John saw Mary's head. John saw a head of Mary?", True],

[311, "John saw Mary's car. Mary had a car?", True],

[317, "John saw elephant's head. John saw a head of an elephant?", True],

[322, 'John saw a head of an elephant. John saw a head of the elephant?', True],

[324, 'John saw a head of the elephant. John saw a head of an elephant?', True],

[337, 'John saw the twig of an elephant. The elephant had the twig?', True],

[346, 'The hand of a man moved a wheel. The hand of a man moved a wheel?', True],

[348, 'The hand of a man moved a wheel. A man had a hand?', True],

[350, 'A blue hand of a man moved a wheel of a large wheelbarrow. A blue hand of a man moved a wheel of a large wheelbarrow?', True],

[352, 'The blue hand of a man moved a wheel of the large wheelbarrow. A blue hand of a man moved a wheel of a large wheelbarrow?', True],

[376, 'John does not eat a carrot. Mike eats carrots. Who does not eat carrots?', 'John'],

[384, 'If John has three cars, John has three cars?', True],

[387, 'Animals have two legs. Animals have three legs?', False],

[391, 'An animal had two legs. The animal had three legs?', False],

[392, 'An animal had two nice legs. The animal had two nice legs?', True],

[400, 'If John has three big nice cars, he is rich. John has three nice big cars. Who is rich?', 'John'],

[401, 'If John has three big nice cars, he is rich. John has three nice cars. John is rich?', None],

[407, 'An animal had two strong legs. The animal had a strong leg?', True],

[445, 'The red car has the price two dollars. The blue car costs three dollars. The car costs three dollars?', True],

[486, 'The weight of the car is 3 tons. The bike weighs as much as the car. The bike weighs more than 2 tons?', True],

[489, "Nile's length is 80 kilometers. Amazon's length is 20 kilometers. What has the length 20 kilometers?", 'Amazon'],

[503, 'The red car has the price two dollars. The blue car costs three dollars. What has the price 3 dollars?', 'The blue car'],

[504, 'The bicycle repaired by Mike was expensive. Mike repaired the bicycle?', True],

[506, 'The bicycle repaired by Mike was expensive. The bicycle was cheap?', False],

[518, 'Some elephants are animals. Elephants are not animals?', False],

[520, 'Some elephants are animals. All elephants are not animals?', False],

[521, 'Some elephants are not animals. All elephants are animals?', False],

[526, 'Bears eat most boxers. Mike is a boxer. Greg is a bear. Bears eats Mike?', 'Probably true.'],

[537, 'The red square has a nail. A blue square has a hole. A square has a nail?', True],

[538, 'The red square has a nail. A blue square has a hole. A square has a hole?', True],

[549, 'The red car is faster than the blue car. Is the blue car faster than the red car?', False],

[551, 'John is as tall as Bill. Is John taller than Bill?', False],

[553, 'The mountain is higher than the hill. Is the hill higher than the mountain?', False],

[554, "This book is more interesting than that one. Is 'that one' more interesting?", False],

[563, 'Elephants, foxes and rabbits are neither birds nor small fish. John is a rabbit. John is a fish?', None],

[565, 'Elephants and sparrows are either animals or birds. John is a sparrow. John is a bird. John is an animal?', False],

[566, 'Elephants and sparrows are either animals or birds. John is a sparrow. Sparrows are birds. John is not an animal?', True],

[569, 'Elephants or sparrows are animals. John is an elephant. Sparrows are not animals. John is an animal?', True],

[587, 'A tall and quiet man entered. A man entered?', True],

[591, 'A tall and quiet man entered. The man was short?', False],

[592, 'A red and blue flag waved. The flag was red?', True],

[593, 'A red and blue flag waved. The flag was blue?', True],

[605, 'The students studied hard and passed the exam. Did the students fail the exam?', False],

[611, 'Tom opened the door and the window. Tom did not open the door?', False],

[616, 'John and Eve can swim. Mark and John are animals. Who is an animal and can swim?', 'John'],

[618, 'Either John or Bill went to the store. Did someone go to the store?', True],

[621, 'Red cars are not nice. Cars are nice. Cars are nice?', True],

[622, 'Red cars are not nice. Cars are nice. Red cars are nice?', False],

[631, 'The manager, Anna, called Eve. Anna is the manager?', True],

[633, 'My neighbor, John, owns a bicycle. Who is my neighbor?', 'John.'],

[639, 'Sara, the sister of Mike, left. Sara is the sister of Mike?', True],

[640, 'Sara, the sister of Mike, left. Sara is the brother of Mike?', False],

[645, 'A stone wall collapsed. A wall collapsed?', True],

[646, 'A kitchen door was open. A door was open?', True],

[647, 'A village road was narrow. A road was narrow?', True],

[648, 'A coffee cup broke. A cup broke?', True],

[650, 'A garden wall was high. Some wall was high?', True],

[652, 'The man carrying a bag waved. The man carried a bag?', True],

[654, 'The woman holding a lamp sang. The woman held a lamp?', True],

[662, 'The car parked behind the house was blue. The car was in front of the house?', False],

[663, 'The children playing in the garden laughed. The children were in the garden?', True],

[664, 'The cup filled with water fell. The cup contained water?', True],

[665, 'The road leading to the village was narrow. The road led to the village?', True],

[666, 'The road leading to the village was narrow. The road was wide?', False],

[667, 'The tree growing near the river was tall. The tree grew near the river?', True],

[669, 'The man carrying a red bag waved. The bag was blue?', False],

[671, 'The woman holding a heavy lamp sang. The lamp was light?', False],

[679, 'The cake baked by John was sweet. John baked the cake?', True],

[681, 'The song sung by Eve was sad. Eve sang the song?', True],

[691, "John's friend from Paris bought a camera. John had a friend?", True],

[694, "Mary's brother carrying a box entered. Mary had a brother?", True],

[697, 'The student carrying the books greeted the teacher. The student carried the books?', True],

[700, 'The letter was written in June. Was the letter written?', True],

[701, 'Bears ate berries in a forest. Bears did not eat berries in a forest?', False],

[703, 'Big bears who have a trunk have a tail. John is a big bear. John has a trunk. John has a tail?', True],

[705, 'Big bears who have a trunk have a tail. John is a bear. John has a trunk. John has a tail?', None],

[717, 'Bears who are nice and who eat berries have a tail. John is a nice big bear. John eats fish. John has a tail?', None],

[742, 'The bear who was white ate a fish. The white bear ate a fish?', True],

[743, 'Bears who were nice ate. Nice bears ate?', True],

[745, 'Bears who are nice eat fish who are strong. John is a nice bear. Bears who are nice eat fish?', True],

[760, 'The nice bear who was white and ate a big fish was cool. The white nice bear who ate a big fish was cool? ', True],

[761, 'The nice bear who was white and ate a big fish also ate berries. The white nice bear who ate a big fish also ate berries? ', True],

[772, 'The woman who sang and danced smiled. The woman danced?', True],

[774, 'The boy with a red hat and a blue coat ran. The boy had a red hat?', True],

[775, 'The boy with a red hat and a blue coat ran. The boy had a blue coat?', True],

[779, 'Bears eat red fish who are strong. John is a bear. John eats red strong fish?', True],

[785, 'Bears who are nice and white eat fish who are strong and red. John is a nice white bear. John eats red strong fish?', True],

[789, 'A man liked a car which a woman bought. The car was red. The man liked the red car which a woman bought?', True],

[791, 'A man liked a car which a woman bought. The car was red. A man liked a red car which a woman bought?', True],

[792, 'A man liked a car which a woman bought. The car was red. The man did not like the red car which the woman bought?', False],

[793, 'A man liked a car which a woman bought. The car was red. The man did not like the red car which a woman bought?', False],

[794, 'A man liked a car which he bought. The car was red. The man bought the red car?', True],

[795, 'A man liked a car which he bought. The car was red. A man bought a red car?', True],

[797, 'Bears ate berries in a forest which was bought by Mary. Bears ate berries in the forest bought by Mary?', True],

[798, 'Bears ate berries in a forest which was seen by Mary. Bears ate berries in the forest seen by Mary?', True],

[801, 'John lives in a red car bought by Mary. Mary bought the car?', True],

[802, 'Mike ate berries in the forest which was bought by Mary. Mike ate berries in the forest which was bought by Mary?', True],

[805, 'Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest which was bought by Mary?', True],

[807, 'Bears ate berries in the forest which was bought by Mary. Bears ate berries in the forest bought by Mary?', True],

[809, 'A man had a car which a woman bought. The car was red. Who had a red car?', ['The man', 'The man and the woman.', 'The woman.']],

[810, 'Bears ate nice berries in a big forest which was bought by Mary. Bears ate berries in the forest which was bought by her?', True],

[811, 'Bears ate nice berries in a big forest which was seen by Mary. Bears ate berries in the forest which was seen by her?', True],

[813, 'Bears ate nice berries in a big forest which was bought by Mary. Bears ate berries in the forest which was bought by a man?', None],

[820, 'John lives in a car which is red and was bought by Mary. The nice car was bought by Mary?', None],

[823, 'John has a car which is nice and red. The big car is nice?', None],

[824, 'John had a car which Eve bought. John had a car which Eve bought?', True],

[831, 'John had a car Eve bought. John had a car Mike bought?', None],

[833, 'John had a car Eve bought. John had a car which Eve bought?', True],

[848, 'John drove a car which Eve bought. John drove a car Eve bought?', True],

[860, 'John drove a red car which Eve bought. John drove a car Eve bought?', True],

[890, 'The car which John drove was red. What color was the car?', 'Red.'],

[901, 'A man had a car which a nice woman bought. The car was red. Who bought the red car?', 'The nice woman'],

[904, 'A man had a car which a nice woman bought. The car was red. Who was nice and bought a car?', ['The woman', 'The nice woman.']],

[907, 'A big bear was strong. The small bear was nice. Who was nice and strong?', None],

[913, 'A man liked a car which a woman bought. The car was red. A man liked a car?', True],

[914, 'A man liked a car which a woman bought. The car was red. The man liked the car?', True],

[915, 'A man liked a car which a woman bought. The car was red. The man liked a red car?', True],

[918, 'A man liked a car which a woman bought. The car was red. The man liked the red car?', True],

[919, 'A man had a car which a woman bought. A man had a car which a woman bought?', True],

[920, 'A man had a car a woman bought. A man had a car which a woman bought?', True],

[923, 'A man had a car a woman bought. A woman bought a car?', True],

[929, 'A man had a car a woman bought. The man did not have a car?', False],

[934, 'A man drove a car which a woman bought. A man drove a car?', True],

[938, 'A man drove a car which a woman bought. A woman bought the car?', True],

[941, 'A man had a car which a woman bought. A woman bought a car?', True],

[942, 'A man had a car which a woman bought. A woman bought the car?', True],

[945, 'A man had a car which a woman bought. The car was red. The man had a red car?', True],

[952, 'A man had a car which a woman bought. The car was red. A man had a red car which a woman bought?', True],

[953, 'A man had a car which a woman bought. The car was red. The man did not have the red car which a woman bought?', False],

[955, 'A man had a car which he bought. The car was red. A man bought a red car?', True],

[957, 'Bears who eat fish which are big are strong. John is a bear. John eats big apples. John is strong?', None],

[958, """A man who ate breakfast liked a car which a woman bought. The car was red.
     A man who ate breakfast liked a red car which a woman bought?""", True],

[959, """A man who ate breakfast liked a car.
     The man ate breakfast?""", True],

[960, """A man who ate breakfast liked a car which a woman bought. The car was red.
     The man who ate breakfast liked the red car which the woman bought?""", True],

[961, """A man who ate breakfast liked a car which a woman bought. The car was red.
     The man who ate breakfast liked the red car which a woman bought?""", True],

[962, 'A man liked a car which a woman bought. The car was red. Who liked a red car?', 'The man'],

[963, 'A man liked a car which a nice woman bought. The car was red. Who bought the red car?', 'The nice woman'],

[965, 'A man liked a car which a nice woman bought. The car was red. Who was nice?', 'The woman'],

[966, 'A man liked a car which a nice woman bought. The car was red. Who was nice and bought a car?', 'The woman'],

[968, """A man who ate breakfast had a car which a woman bought. The car was red.
     A man who ate breakfast had a red car which a woman bought?""", True],

[970, """A man who ate breakfast had a car which a woman bought. The car was red.
     The man who ate breakfast had the red car which the woman bought?""", True],

[971, """A man who ate breakfast had a car which a woman bought. The car was red.
     The man who ate breakfast had the red car which a woman bought?""", True],

[974, 'Mary visited London in September. When did Mary visit London?', 'In September.'],

[979, 'John works at the hospital every day. Where does John work?', 'At the hospital.'],

[988, 'John ate the pizza on the table. Was the pizza on the floor?', False],

[990, 'The cat in the hat sat on the mat. Where was the cat?', ['In the hat.', 'On the mat.']],

[991, 'Mary put the book on the shelf in the library. Where is the shelf?', 'In the library.'],

[994, 'Mary found the key under the table. The key was under the table?', True],

[995, 'Mary found the key under the table. Was the key on the table?', False],

[1013, 'John and Mike were defeated. Who defeated John and Mike?', None],

[1047, 'The room was cleaned. Who cleaned the room?', None],

[1050, 'A promotion was given to Mary. What did Mary get?', 'A promotion.'],

[1052, 'The city was destroyed. Is the city intact?', False],

[1057, 'John said that Mary left. Did Mary stay?', None],

[1058, 'Eve reported that Tom arrived. Tom arrived?', True],

[1060, 'Anna announced that the show started. The show started?', True],

[1061, 'The guide explained that the road was closed. Was the road open?', False],

[1062, 'John went to the shop to buy bread. John went to the shop?', True],

[1063, 'John went to the shop to buy bread. John bought bread?', None],

[1065, 'Mary opened the window to let in air. Mary opened the window?', True],

[1066, 'Mary opened the window to let in air. Mary did not open the window?', False],

[1067, 'Mary opened the window to let in air. Air came in?', None],

[1083, 'Mary said that she was tired. Who was tired?', 'Mary.'],

[1095, 'If John wrote a report, then Bill did too. John wrote a report. Did Bill write a report?', True],

[1104, 'Bears do not eat red berries in a forest. Bears eat red berries in forest?', False],

[1118, """If a bear eats, it is hungry. John is a brown bear.
      John quickly eats berries in a deep forest. Who is hungry?""", 'John.'],

[1134, 'John gave a book to Mary. What did Mary receive?', ['A book.', 'The book.']],

[1142, 'John told Mary a story. Mary heard a story?', True],

[1144, 'John told a story to Mary. Who heard a story?', 'Mary.'],

[1158, 'The teacher showed a map to the students. Who saw a map?', ['The students.', 'The teacher and the students.']],

[1161, 'Eve sent Tom a long letter. Tom got a short letter?', None],

[1167, 'A man did have a car. A man had a car?', True],

[1168, 'A man had a car. A man did have a car?', True],

[1173, 'John has finished his homework. Is the homework unfinished?', False],

[1184, 'When Eve entered the house, she smiled. Eve did not enter the house?', False],

[1188, 'While John was cooking, Mary read a book. Mary read a book?', True],

[1205, 'John stopped smoking. Did John smoke in the past?', True],

[1206, 'John stopped smoking. Does John smoke now?', False],

[1207, 'Mary started the car. Was the car running before?', False],

[1222, 'John is on a box. Mark is on a house. Where is John?', ['On the box.', 'On a box.']],

[1224, 'John is at a box. Mark is at a house. Where is John?', ['At the box.', 'At a box.']],

[1225, 'John is at a box. Mark is at a house. Where is Mark?', ['At the house.', 'At a house.']],

[1233, 'A car was in a box and in a house. Where was the car?', ['In the house and in the box.', 'In a box and in a house.', 'In a box.', 'In a house.']],

[1240, '"Riga is outside America. Riga is not in what?', 'America.'],

[1242, """If a city is in Estonia, it is an Estonian city. Tallinn is in Estonia. Tallinn is a city.
     What is an Estonian city?""", 'Tallinn.'],

[1249, 'John is in a box. John is near a spoon. John is on the floor. John is not in the box. Where is John?', ['On the floor and near the spoon.', 'On the floor.']],

[1250, 'John is in a box. John is near a spoon. John is on the floor. John is not in the box. Where is John?', ['On the floor and near the spoon.', 'On the floor.', 'Near a spoon.']],

[1253, """John is in a red car. John is a man. The red car is in the house. The black car is in the street.
      The street is in Tallinn. Where is a car?""", ['In the house, in the street and in Tallinn.', 'In the house.', 'In the street.', 'In the house and in the street.', 'In Tallinn.']],

[1262, 'John is in the box at the red house. A box is at a house?', True],

[1263, 'John is in the box at a red house. The box is at a house?', True],

[1274, 'Birds near Tallinn are nice. John is near Tallinn. What is nice?', 'A bird near Tallinn'],

[1282, 'John jumped high in a room. John jumped low near the garage. Where did John jump low?', 'Near the garage'],

[1284, 'Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears ate?', True],

[1285, 'Bears ate berries in a forest which was seen by Mary. Mary saw the forest where the bears ate?', True],

[1286, 'Bears ate berries in a forest which was bought by Mary. Mary bought the forest where the bears drank?', None],

[1294, 'During 1800, John jumped in a house. Where did John jump?', 'In a house'],

[1295, 'Before 1900, John jumped in a house. When did John jump?', ['Before the year 1900', 'Before 1900.']],

[1296, 'Before 1900, John jumped in a house. After 1902, John ate in a house. When did John jump?', ['Before the year 1900', 'Before 1900.']],

[1297, 'Before 1900, John jumped in a house. After 1902, John sat in a house. When did John sat?', ['After the year 1902', 'After 1902.']],

[1298, 'On Monday, John jumped in a house. Where did John jump?', 'In a house'],

[1302, 'The cake that was on the counter has disappeared. Where was the cake?', 'On the counter.'],

[1305, 'John travelled to the hallway. Mary journeyed to the bathroom. Daniel went back to the bathroom. John moved to the bedroom. Where is Mary?', ['bathroom', 'In the bathroom.', 'At the bathroom.']],

[1307, 'John travelled to the hallway. Mary journeyed to the bathroom. Daniel went back to the bathroom. John moved to the bedroom. John went to the hallway. Sandra journeyed to the kitchen. Sandra travelled to the hallway. John went to the garden. Where is Sandra?', ['hallway', 'In the hallway.', 'At the hallway.']],

[1308, 'John travelled to the hallway. Mary journeyed to the bathroom. Daniel went back to the bathroom. John moved to the bedroom. John went to the hallway. Sandra journeyed to the kitchen. Sandra travelled to the hallway. John went to the garden. Sandra went back to the bathroom. Sandra moved to the kitchen. Where is Sandra?', ['kitchen', 'In the kitchen.', 'At the kitchen.']],

[1309, 'Sandra travelled to the kitchen. Sandra travelled to the hallway. Where is Sandra?', ['hallway', 'In the hallway.', 'At the hallway.']],

[1310, 'Sandra travelled to the kitchen. Sandra travelled to the hallway. Mary went to the bathroom. Sandra moved to the garden. Where is Sandra?', ['garden', 'In the garden.', 'At the garden.']],

[1311, 'Sandra travelled to the kitchen. Sandra travelled to the hallway. Mary went to the bathroom. Sandra moved to the garden. Sandra travelled to the office. Daniel journeyed to the hallway. Where is Daniel?', ['hallway', 'In the hallway.', 'At the hallway.']],

[1312, 'Sandra travelled to the kitchen. Sandra travelled to the hallway. Mary went to the bathroom. Sandra moved to the garden. Sandra travelled to the office. Daniel journeyed to the hallway. Daniel journeyed to the office. John moved to the hallway. Where is Sandra?', ['office', 'In the office.', 'At the office.']],

[1313, 'Sandra travelled to the kitchen. Sandra travelled to the hallway. Mary went to the bathroom. Sandra moved to the garden. Sandra travelled to the office. Daniel journeyed to the hallway. Daniel journeyed to the office. John moved to the hallway. John travelled to the bathroom. John journeyed to the office. Where is Daniel?', ['office', 'In the office.', 'At the office.']],

[1342, 'If cars are red, elephants are nice. Cars are red. Elephants are nice?', True],

[1345, 'If cars are green, elephants are nice. If elephants are nice, squirrels are red. Cars are green. Squirrels are red?', True],

[1346, 'If cars have roofs, elephants are nice. Cars have roofs. Elephants are nice?', True],

[1348, 'If some car has a roof, elephants are nice. John is a car. John has a roof. Elephants are nice?', True],

[1364, """If X1 is a father of Y1, Y1 is a child of X1.
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1.
      John is a father of Mike and Mickey. Luke is a father of John.
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1.
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1.
      Mike and Mickey are not female. Any person is male or female.
      Who is a grandson of Luke?""", ['Mickey and Mike.', 'Mike and Mickey.']],

[1365, """If X1 is a father of Y1, Y1 is a child of X1.
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1.
      John is a father of Mike and Mickey. Luke is a father of John.
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1.
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1.
      Mike or Mickey is not female. Any person is male or female.
      Who is a grandson of Luke?""", 'Mike or Mickey.'],

[1366, """If X1 is a father of Y1, Y1 is a child of X1.
      If X1 is a father of Y1 and Y1 is a father of Z1, X1 is a grandfather of Z1.
      John is a father of Mike and Mickey. Luke is a father of John.
      If X1 is a grandfather of Y1, Y1 is a grandchild of X1.
      If X1 is male and X1 is a grandchild of Y1, X1 is a grandson of Y1.
      Mike or Mickey are not female. Any person is male or female.
      Who is a grandson of Luke?""", 'Mike or Mickey.'],

[1387, 'If the bear is strong, the fox is nice. The bear is strong. Who is nice?', 'The fox.'],

[1388, 'If the bear is strong, the fox is nice. The bear is strong. John is a fox. Who is nice?', ['The fox.', 'John.']],

[1395, 'If a bear who eats fish is strong, it is nice. John is a bear. John eats fish. John is strong. John is nice?', 'Likely true'],

[1398, 'If a big bear who eats strong fish is white, it is nice. John is a big bear. John eats strong fish. John is white. John is nice?', True],

[1413, 'Red cars are not nice. Cars are nice. Red cars are not nice?', True],

[1415, 'Red cars are not nice. Cars are nice. What are not nice?', 'A red car.'],

[1418, 'Red cars do not have trunks. Cars have trunks. Cars have a trunk?', True],

[1422, 'Red cars do not have trunks. Cars have trunks. John is a red car. John has a trunk?', False],

[1429, """Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike is a bird.
    John does not fly?""", True],

[1432, """Birds fly and eat. Baby birds do not fly. John is a baby bird. Mike and Eve are birds.
    Who does not fly?""", 'John.'],

[1440, """Bears eat berries. Baby bears eat no berries. John is a baby bear.
     John eats berries?""", False],

[1443, """Birds can fly. Baby birds can not fly. John is a baby bird. Mike and Eve are birds.
      Who can not fly?""", 'John.'],

[1445, """Bears can eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who can not eat berries?""", 'John.'],

[1448, 'Birds can fly. No penguin can fly. Penguins are birds. John is a penguin. John can fly?', False],

[1456, """Bears eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who eats berries?""", 'Mike.'],

[1457, """Bears eat berries. Baby bears can not eat berries. John and Mike are bears.
      John is a baby bear.  Who does not eat berries?""", 'John.'],

[1458, 'Birds can fly. Baby birds do not fly. John is a baby bird. Mike is a bird. Who can not fly?', 'John.'],

[1459, """Bears can eat berries. Baby bears do not eat berries. John and Mike are bears.
      John is a baby bear.  Who can not eat berries?""", 'John.'],

[1464, """Elephants are big. Young elephants are not big.
      Mike is an elephant. John is a young elephant. John is big?""", False],

[1466, """Elephants are big. Young elephants are not big.
      Mike is an elephant. John is a young elephant. Who is not big?""", 'John.'],

[1468, """Elephants are big. Young elephants are not big.
      Who is not big?""", 'A young elephant.'],

[1473, 'Some bears eat all berries. John is a bear. John eats berries?', None],

[1477, 'If X1 eats berries, it is a bear. John eats red berries. John is a bear?', True],

[1481, 'Elephants are rarely animals. John is an elephant. John is an animal?', 'Probably false.'],

[1483, 'Probably elephants are not animals. John is an elephant. John is an animal?', 'Probably false.'],

[1485, 'Probably elephants have no trunks. John is an elephant. John has a trunk?', 'Probably false.'],

[1486, 'Elephants have probably long trunks. John is an elephant. John has a long trunk?', 'Probably true.'],

[1487, 'Elephants have probably no trunks. John is an elephant. John has a trunk?', 'Probably false.'],

[1492, """It is probable that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably true.'],

[1493, """It is probable that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably false.'],

[1494, """It is probably true that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably true.'],

[1495, """It is probably false that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably true.'],

[1496, """It is unlikely that if X1 is a grandfather of Y1, Y1 is a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably false.'],

[1497, """It is unlikely that if X1 is a grandfather of Y1, Y1 is not a child of X1. John is grandfather of Mike.
       Mike is a child of John?""", 'Probably true.'],

[1498, """It is probable that if X1 is not a grandfather of Y1, Y1 is a child of X1. John is not a grandfather of Mike.
       Mike is a child of John?""", 'Probably true.'],

[1500, 'Tallinn is hardly in Latvia. Tallinn is in Latvia?', 'Likely false.'],

[1504, 'It is probably false that Tallinn is in Latvia. Tallinn is in Latvia?', 'Probably false.'],

[1508, 'It is false that elephants are animals. John is an elephant. John is an animal?', False],

[1509, 'It is not true that elephants are animals. John is an elephant. John is an animal?', False],

[1512, 'It is probably false that elephants are animals. John is an elephant. John is an animal?', 'Probably false.'],

[1514, 'It is not probable that elephants are animals. John is an elephant. John is an animal?', 'Probably false.'],

[1515, 'It is unlikely that elephants are animals. John is an elephant. John is an animal?', 'Probably false.'],

[1521, 'It is not probable that John is a child of Mike. John is a child of Mike?', 'Probably false.'],

[1522, 'It is unlikely that John is a child of Mike. John is a child of Mike?', 'Probably false.'],

[1523, 'It is probably false that John is a child of Mike. John is a child of Mike?', 'Probably false.'],

[1531, 'John smokes tobacco with a probability 80 percent. Does John smoke?', 'Likely true'],

[1533, """Birds fly and eat. Baby birds do not fly. John is hardly a baby bird.
     Mike and Eve and John are birds. Who flies and eats?""", ['Mike, Eve and John', 'Mike, Eve, and John.']],

[1534, """Birds fly and eat. Baby birds do not fly. John is probably a baby bird.
     Mike and Eve and John are birds. Who flies and eats?""", 'Mike and Eve'],

[1541, 'Tallinn is in Latvia with a probability 10 percent. Tallinn is in Latvia?', 'Likely false.'],

[1543, 'Elephants have a trunk with a probability 90 percent. John is an elephant. John has a trunk?', 'Likely true.'],

[1544, 'Elephants have a trunk with a probability 10 percent. John is an elephant. John has a trunk?', 'Likely false.'],

[1547, 'Elephants probably do not have wings. John is an elephant. Who does not have wings?', ['Probably John.', 'John.']],

[1548, 'Elephants probably do not have wings. John is maybe an elephant. Who does not have wings?', 'Maybe John.'],

[1549, 'John probably smokes. John smokes?', 'Probably true'],

[1550, 'Probably John smokes. John smokes?', 'Probably true'],

[1562, 'John is in a cave with a probability 10%. John is in a cave?', 'Likely false'],

[1563, 'John managed to open the door. John opened the door?', True],

[1564, 'John managed to open the door. John did not open the door?', False],

[1565, 'Mary managed to solve the puzzle. Mary solved the puzzle?', True],

[1566, 'Tom failed to catch the bus. Tom caught the bus?', False],

[1567, 'Eve failed to finish the report. Eve finished the report?', False],

[1573, 'Tom refused to eat the soup. Tom ate the soup?', False],

[1575, 'Eve forgot to lock the door. Eve locked the door?', False],

[1577, 'John was seen to enter the room. John entered the room?', True],

[1579, 'Mary was heard to sing. Mary sang?', True],

[1581, 'Only John bought a car. Did Mary buy a car?', False],

[1583, 'John only eats apples. Does John eat bananas?', False],

[1584, 'Everyone except John arrived. Did John arrive?', False],

[1585, 'All the boxes are red except for the small one. Is the small box red?', False],

[1587, 'John made Mary cry. Did Mary cry?', True],

[1588, 'Tom had the mechanic fix his car. Who fixed the car?', 'The mechanic.'],

[1589, 'It was John who ate the cake. Who ate the cake?', 'John.'],

[1590, 'Wolves are afraid of mice. Sheep are afraid of mice. Winona is a sheep. Mice are afraid of cats. Cats are afraid of wolves. Jessica is a mouse. Emily is a cat. Gertrude is a wolf. What is emily afraid of?', ['A wolf.', 'wolf', 'Wolves.', 'wolves']],

[1591, 'Wolves are afraid of mice. Sheep are afraid of mice. Winona is a sheep. Mice are afraid of cats. Cats are afraid of wolves. Jessica is a mouse. Emily is a cat. Gertrude is a wolf. What is winona afraid of?', ['A mouse.', 'mouse', 'Mice.', 'mice']],

[1592, 'Wolves are afraid of mice. Sheep are afraid of mice. Winona is a sheep. Mice are afraid of cats. Cats are afraid of wolves. Jessica is a mouse. Emily is a cat. Gertrude is a wolf. What is gertrude afraid of?', ['mouse', 'Jessica.']],

[1593, 'Wolves are afraid of mice. Sheep are afraid of mice. Winona is a sheep. Mice are afraid of cats. Cats are afraid of wolves. Jessica is a mouse. Emily is a cat. Gertrude is a wolf. What is jessica afraid of?', ['A cat.', 'cat', 'Cats.', 'cats']],

[1595, 'Cats are afraid of wolves. Mice are afraid of cats. Sheep are afraid of mice. Gertrude is a cat. Wolves are afraid of sheep. Jessica is a mouse. Emily is a wolf. Winona is a cat. What is jessica afraid of?', ['A cat.', 'cat', 'Cats.', 'cats']],

[1596, 'Cats are afraid of wolves. Mice are afraid of cats. Sheep are afraid of mice. Gertrude is a cat. Wolves are afraid of sheep. Jessica is a mouse. Emily is a wolf. Winona is a cat. What is gertrude afraid of?', ['A wolf.', 'wolf', 'Wolves.', 'wolves']],

[1597, """Wolves are afraid of mice.
    Sheep are afraid of mice.
    Winona is a sheep.
    Mice are afraid of cats.
    Cats are afraid of wolves.
    Jessica is a mouse.
    Emily is a cat.
    Gertrude is a wolf.
    What is Emily afraid of?""", ['Probably a wolf', 'Wolves.', 'Gertrude.']],

[1598, """Wolves are afraid of mice.
    Sheep are afraid of mice.
    Winona is a sheep.
    Mice are afraid of cats.
    Cats are afraid of wolves.
    Jessica is a mouse.
    Emily is a cat.
    Gertrude is a wolf.
    Who is Emily afraid of?""", ['Probably Gertrude', 'Gertrude.', 'Wolves.']],

[1599, """Wolves are afraid of mice.
    Sheep are afraid of mice.
    Winona is a sheep.
    Mice are afraid of cats.
    Cats are afraid of wolves.
    Jessica is a mouse.
    Emily is a cat.
    Gertrude is a wolf.
    What are cats afraid of?""", ['A wolf.', 'wolf', 'Wolves.', 'wolves']],

[1600, """Wolves are afraid of mice.
    Sheep are afraid of mice.
    Winona is a sheep.
    Mice are afraid of cats.
    Cats are afraid of wolves.
    Jessica is a mouse.
    Emily is a cat.
    Gertrude is a wolf.
    What is Winona afraid of?""", ['A mouse.', 'mouse', 'Mice.', 'mice']],

]
