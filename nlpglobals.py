# Configuration and other globals for the nlpsolver.
#
#-----------------------------------------------------------------
# Copyright 2022 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------

import sys

replacement_text_rules=None
replacement_complex_rules=None


# ======= configuration globals ======

# global vars changed by command line options

options={
  "debug_print_flag":False, # if True, print a lot of details of the parsing process (turn on by -debug)
  "prover_print_flag":False, # if True, print prover logic input and output
  "prover_nosolve_flag":False, # if True, attempt to solve the question, if False, just output logic
  "prover_postprocess_flag":False, # if True, apply post_process_logic_list to the logic created
  "prover_rawresult_flag":False, # if True, give a raw json result
  "prover_explain_flag":False, # if True, output nlp explanation
  "show_logic_flag":False, # if True, output also conventional logic for sentences and nlp explanation
  "show_prover_flag":False, # if True, show prover input and output
  "usekb_flag": False, #if True, use shared memory kb
  "forward_flag":False, # if True, use forward search
  "backward_flag":False, # if True, use backward search
  "nocontext_flag":False, # if True, do not insert context information (time, situation) into logic
  "noexceptions_flag":False, # if True, do not insert exception information (blockers) into logic
  "noproptypes_flag":False,  # if True, remove prop strength and type information  
  "nokb_flag":True,  # if True, do not use the shared memory knowledge base
  "prover_axiomfiles":False,  # if not False, use these as axioms instead of the default prover_axiomfile below
  "prover_print":False,  # if not False, use the argument integer for gk printout level, instead of the default
  "prover_strategy":False,  # if not False, use the argument as a gk strategy file, instead of the default
  "prover_seconds":2,  # give the prover this many seconds, instead of the default 1
  "llm_flag": False, # perform LLM simplifications
  "amr_flag": False  # perform AMR parsing  
}

# connecting to llm etc with secret keys

secrets_file="secrets.js" # only needed for reading llm keys, if llm used

# connecting to nlpserver.py
server_name="localhost"
server_port=8080
server_timeout=2

# solving logic with a prover
prover_fname="./gk"
memkb_name="1000"  # in-memory knowledge base name (number)
prover_infile="gk_infile.js"
prover_axiomfile="axioms_std.js"
prover_params=["-defaults","-confidence","0.1","-keepconfidence","0.1"] # additional prover params, always appended
usekb_prover_params=["-usekb","-confidence","0.1","-keepconfidence","0.1"] # additional prover params, always appended

#prover_params=["-usekb", "-confidence","0.1","-keepconfidence","0.1"] # additional prover params, always appended

#prover_params=["-strategy", "bigkb.txt"] #["-print","20"] #[] #["-print","20"] #[] # "knowledge.js","-print","15"]
#prover_params=["quasi_50k.js"]
#prover_params=["quasi_50k.js","-confidence","0.1","-keepconfidence","0.1"]
"""
[
    "-usekb","-mbsize","100","-seconds","1","-mbnr","1001", 
    "-nonegative","-nocheck", "-strategy","strat_large_parts.js","-confidence","0"
    
]
"""

constant_prefix="c" # new constants start with this by default
det_constant_prefix="the_" # prefixed to determined (a, the, an, another) constants
skolem_constant_prefix="cs" # new skolem constants start with this
external_skolem_constant_prefix="sk" # external skolem constants are assumed to start with this (for answer printing)
typed_skolem_function_prefix="skt" # new typed skolem functions start with this
definition_prefix="$def" # new definitions start with this
var_prefix="?:X" # new vars start with this
confidence_function="$conf" # temporary encoding of confidence like ["$conf",0.9]
ctxt_function="$ctxt" # function name for the contextual data put into literals 
theof_function="$theof"
measure_function="$measure"

generic_value="$generic"
min_prop_intensity=1
max_prop_intensity=3
default_prop_intensity=generic_value
default_prop_class=generic_value
unknown_value="$unknown"
fully_free_variable="$free_variable"
count_function="$count"
lambda_firstarg="$arg1"
set_function="$setof"

#date_function="$date"
time_function="$time"
year_type_argument="$year"

dummysubject="$dummysubject"
dummypredicate="$dummy"
unknownsubject="$unknown"
#propclass_var="?:PC"

dummy_name="Dummyname" # new vars start with this
question_var="?:Q"
frame_var_prefix="?:Fv"
unit_var_prefix="?:Unit"

question_words=["who","what","where","when"]
simple_question_words=["who","what"]
complex_question_words=["who","what","which","who?","what?","which?"]

logic_ops=["forall","exists","and","or","not","&","|","=>","<=","then","if","<=>","nor","xor"]

comparison_preds=["=","!=","-=","$greater","$less","-$greater","-$less"]

# ========= setting some globals from other files ======

def set_globals(g1,g2,g3,g4,g5,g6,g7,g8,g9,g10,g11):
  global debug_print_flag, prover_print_flag, prover_nosolve_flag,prover_rawresult_flag
  global prover_explain_flag,show_logic_flag,show_prover_flag,usekb_flag,forward_flag,backward_flag
  global nocontext_flag,noexceptions_flag #,noproptypes_flag
  debug_print_flag=g1  
  prover_print_flag=g2
  prover_nosolve_flag=g3
  prover_rawresult_flag=g4
  prover_explain_flag=g5
  show_logic_flag=g6
  show_prover_flag=g7
  usekb_flag=g8
  forward_flag=g9
  backward_flag=g10
  nocontext_flag=g11
  noexceptions_flag=g12
  #options.noproptypes_flag=g12

def set_global_options(newoptions):
  global options
  for key in newoptions:
    if key in options:
      options[key]=newoptions[key]
    else:
      print("Error: option",key,"is not recognized.")  
      sys.exit(0)




# ========= data globals ==========

end_punctuation_lemmas=[".","?","!"]

string_replacements=[

  [" something ", " an object "],
  [" somebody ", " a person "],
  [" someone ", " a person "],

  [" everything ", " every object "],
  [" everybody ", " every person "],
  [" everyone ", " every person "],

  [" cannot "," can not "],
  [" isnt "," is not "], 
  [" wasnt "," was not "], 
  [" doesnt "," does not "],
  [" hasnt "," has not "],

  [" isn't "," is not "], 
  [" wasn't "," was not "], 
  [" haven't "," has not "], 
  [" hadn't "," had not "], 
  [" doesn't "," does not "],
  [" can't "," can not "],
  [" won't "," will not "],
  [" wouldn't "," would not "],
  [" couldn't "," could not "],

  [" is unable to "," can not "],
  [" is unable of "," can not "],
  [" is inable to "," can not "],
  [" is inable of "," can not "], 
  [" is incapable to "," can not "],
  [" is incapable of "," can not "],

  [" are unable to "," can not "],
  [" are unable of "," can not "],
  [" are inable to "," can not "],
  [" are inable of "," can not "], 
  [" are incapable to "," can not "],
  [" are incapable of "," can not "],

  [" were unable to "," could not "],
  [" were unable of "," could not "],
  [" were inable to "," could not "],
  [" were inable of "," could not "], 
  [" were incapable to "," could not "],
  [" were incapable of "," could not "],

  [" was unable to "," could not "],
  [" was unable of "," could not "],
  [" was inable to "," could not "],
  [" was inable of "," could not "], 
  [" was incapable to "," could not "],
  [" was incapable of "," could not "],

  
  [" unable "," can not "],
  [" incapable "," can not "],

  [" is capable of "," can "],
  [" are capable of "," can "],
  [" was capable of "," could "],
  [" were capable of "," could "],
  [" have been capable of "," could "],
  [" had been capable of "," could "],

  [" is able to "," can "],
  [" are able to "," can "],
  [" was able to "," could "],
  [" were able to "," could "],
  [" have been able to "," could "],
  [" had been able to "," could "],

  [" has a capability to "," can "],
  [" have a capability to "," can "],
  [" had a capability to "," could "],
  [" have had a capability to "," could "],

  [" has an ability to "," can "],
  [" have an ability to  "," can "],
  [" had an ability to  "," could "],
  [" have had an ability to  "," could "],

  [" has a capacity to "," can "],
  [" have a capacity to "," can "],
  [" had a capacity to "," could "],
  [" have had a capacity to "," could "],

  [" has the capability to "," can "],
  [" have the capability to "," can "],
  [" had the capability to "," could "],
  [" have had the capability to "," could "],

  [" has the ability to "," can "],
  [" have the ability to "," can "],
  [" had the ability to "," could "],
  [" have had the ability to "," could "],

  [" has the capacity to "," can "],
  [" have the capacity to "," can "],
  [" had the capacity to "," could "],
  [" have had the capacity to "," could "],

  [" a large number of "," many "],
  [" a great number of "," many "],
  [" a lot of "," many "],
  [" a majority of "," most "]


]

have_type_verbs={"have":1} # used to determine whether to use forall or exists for an object: for these prefer exists

# used to determine whether to use forall or exists for an object: for these prefer forall
like_type_verbs={
  "like":1, "love":1, "prefer":1, "adore":1, "want":1, "respect":1, "envy":1,
  "hate":1, "detest":1, "abhor":1, "dislike":1, "resent":1, "loathe":1
} 

probability_words=["confidence","probability","likelihood","plausibility","chance"]

measure_words={
  "weight": {"units": ["kilogram","kg","gram","ton","pound","ounze","oz"], "morenouns": ["heavy"], "lessnouns": ["light"]},
  "length": {"units": ["m","f","meter","millimeter","kilometer","centimeter","mile","foot","yard"],"morenouns": ["long"],"lessnouns": ["short"]},
  "height": {"units": ["meter","millimeter","kilometer","centimeter","mile","foot","yard"], "morenouns": ["tall"],"lessnouns": ["short"]},
  "width":  {"units": ["meter","millimeter","kilometer","centimeter","mile","foot","yard"], "morenouns": ["wide"],"lessnouns": ["narrow"]},
  "depth":  {"units": ["meter","millimeter","kilometer","centimeter","mile","foot","yard"], "morenouns": ["deep"], "lessnouns": ["shallow"]},
  "temperature": {"units": ["celsius","fahrenheit","c","f"], "morenouns":["warm","hot"],"lessnouns": ["cold"]},
  "price": {"units": ["eur","usd","euro","dollar"], "morenouns": ["cost"],"lessnouns": ["cheap"]},
  "duration": {"units":["s","m","h","second","minute","hour","day","week","month","year","century"]}
}

comparison_words={
  "less": {"less": True},
  "more": {"more": True},  
  "equal": {"equal": True}
}


lemma_confidences={
  "doubtless": 0.98,
  "certainly": 0.98,
  "obviously": 0.98,
  "certain": 0.98,
  "surely": 0.97,

  "sure": 0.97,
  "typically": 0.95,
  "typical": 0.95,
  "normally": 0.95,
  "normal": 0.95,
  "usually": 0.9,
  "usual": 0.9,
  "apparently": 0.92,
  "apparent": 0.92,
  "probably": 0.9,
  "probable": 0.9,
  "almost": 0.9,
  "probs": 0.9,
  "prob": 0.9,
  "commonly": 0.9,
  "common": 0.9,  
  "likely": 0.9,  
  "often": 0.8,
  "plausibly": 0.8,  
  "plausible": 0.8,
  "frequently": 0.8,
  "seemingly": 0.8,
  "hopefully": 0.8,
  "supposedly": 0.8,
  "perchance": 0.65,
  "possibly": 0.6,
  "possible": 0.6,
  "imaginably": 0.6,
  "imaginable": 0.6,
  "maybe": 0.5,
  "perhaps": 0.2,
  "sometimes": 0.2,
  "uncertain": -0.5,
  "doubtful": -0.8,  
  "questionable": -0.8,
  "seldom": -0.8,
  "hardly": -0.8,
  "unfrequently": -0.8,
  "infrequently": -0.8,
  "infrequent": -0.8,
  "uncommonly": -0.9,
  "uncommon": -0.9,
  "unusually": -0.9,
  "unlikely": -0.9,
  "rarely": -0.9,
  "rare": -0.9,  
  "improbably": -0.9,
  "improbable": -0.9,
  "inconceivably": -0.94,
  "inconceivable": -0.94,
  "unbelievable": -0.95,
  "unimaginable": -0.95
}


mistrust_confidences={
  "know": 1,
  "see": 0.99,
  "hear": 0.95,
  "believe": 0.85,
  "claim": 0.85,
  "think": 0.85,
  "say": 0.8,
  "assume": 0.8,
  "hope": 0.8,
  "suspect": 0.7
}


quantor_confidences={
  "most": 0.85,
  "many": 0.2,
  "several": -0.2,
  "few": -0.5,
}


maximize_prop_words={
  "super": True,
  "extremely": True,
  "incredibly": True,
  "massively": True,
  "hugely": True,
  "very": True,
  "really" : True, 
  "totally": True
}

minimize_prop_words={
  "slightly": True,
  "somewhat": True,
  "little": True,
  "moderately": True,
  "partially": True,
  "marginally": True
}  

no_prop_words={
  "never": True,
  #"hardly": True,
  "that": True,
  "also": True,
  "even": True,
  "additionally": True,
  "again": True,
  "besides": True,
  "further": True,
  "furthermore": True,
  "likewise": True
}


class_prop_words={
  "good": True,
  "bad": True,
  "poor": True,

  "competent": True,
  "incompetent": True,
  "substandard": True,

  "superior": True,
  "inferior": True,

  "capable": True,
  "incapable": True,

  "strong": True,
  "powerful": True,
  "weak": True,
  "feeble": True,
  "puny": True,

  "fast": True,
  "quick": True,
  "slow": True,

  "huge": True,
  "enormous": True,
  "colossal": True,
  "large": True,
  "big": True,
  "small": True,
  "little": True,
  "tiny": True,
  "mini": True,
  "minute": True,
  "miniscule": True,

  "massive": True,
  "heavy": True,
  "light": True,

  "long": True,
  "tall": True,
  "short": True,

  "high": True,
  "low": True,

  "deep": True,
  "shallow": True,

  "late": True,
  "early": True

  #"rich"
  #"poor"
}

#class_prop_words={}

"""
tense_words=["is","was","were"]
by_words=["by"]
uncertain_actions=["believed","suspected","thought","said","claimed","hoped","assumed"]
mistrust_words=["maybe","perhaps","possibly","supposedly","probably","hopefully"]
conditional_in_words=["if","unless"]
negative_conditional_in_words=["unless"]
cond_first_words=["in"]
cond_second_words=["case"]
nonconditional_in_words=["although","despite","before","after"]
useless_condition_phrases=["whether or not"]
"""

number_word_translate={
  "zero":0, "one":1, "two":2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, 
  "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14
}


relation_type_translate={
  "inside": "in",  
  "outside": "out"
}

relation_type_reverse_translate={ 
  "contain": "in"
}

relation_type_negative_translate={
  "out": "in"  
}

is_location_relations=[
  "in","on","at","near","above","under"
]

is_time_relations=[
  "in","at","on","during","before","after"
]


larger_words=[
  "more","over","above"
]

smaller_words=[
  "less","under","below"
]

"""
relation_type_translate={
  "is_inside": "is_in",  
  "is_outside": "is_out"
}

relation_type_reverse_translate={ 
  "contain": "is_in"
}

relation_type_negative_translate={
  "is_out": "is_in",  
}

is_location_relations=[
  "is_in","is_on","is_at","is_near","is_above","is_under"
]
"""

abstract_verbs={"afraid":True,"fond":True,"like":True,"dislike":True,"love":True,"hate":True,
 "prefer":True,"know":True,"think":True}

plural_to_singular={"mice":"mouse"}

first_names={
"Liam":"m","Noah":"m","Oliver":"m","Elijah":"m","James":"m","William":"m",
"Benjamin":"m","Lucas":"m","Henry":"m","Theodore":"m","Jack":"m",
"Levi":"m","Alexander":"m","Jackson":"m","Mateo":"m","Daniel":"m",
"Michael":"m","Mason":"m","Sebastian":"m","Ethan":"m","Logan":"m",
"Owen":"m","Samuel":"m","Jacob":"m","Asher":"m","Aiden":"m",
"John":"m","Joseph":"m","Wyatt":"m","David":"m","Leo":"m",
"Luke":"m","Julian":"m","Hudson":"m","Grayson":"m","Matthew":"m",
"Ezra":"m","Gabriel":"m","Carter":"m","Isaac":"m","Jayden":"m",
"Luca":"m","Anthony":"m","Dylan":"m","Lincoln":"m","Thomas":"m",
"Maverick":"m","Elias":"m","Josiah":"m","Charles":"m","Caleb":"m",
"Christopher":"m","Ezekiel":"m","Miles":"m","Jaxon":"m","Isaiah":"m",
"Andrew":"m","Joshua":"m","Nathan":"m","Nolan":"m","Adrian":"m",
"Cameron":"m","Santiago":"m","Eli":"m","Aaron":"m","Ryan":"m",
"Angel":"m","Cooper":"m","Waylon":"m","Easton":"m","Kai":"m",
"Christian":"m","Landon":"m","Colton":"m","Roman":"m","Axel":"m",
"Brooks":"m","Jonathan":"m","Robert":"m","Jameson":"m","Ian":"m",
"Everett":"m","Greyson":"m","Wesley":"m","Jeremiah":"m","Hunter":"m",
"Leonardo":"m","Jordan":"m","Jose":"m","Bennett":"m","Silas":"m",
"Nicholas":"m","Parker":"m","Beau":"m","Weston":"m","Austin":"m",
"Connor":"m","Carson":"m","Dominic":"m","Xavier":"m","Jaxson":"m",
"Jace":"m","Emmett":"m","Adam":"m","Declan":"m","Rowan":"m",
"Micah":"m","Kayden":"m","Gael":"m","River":"m","Ryder":"m",
"Kingston":"m","Damian":"m","Sawyer":"m","Luka":"m","Evan":"m",
"Vincent":"m","Legend":"m","Myles":"m","Harrison":"m","August":"m",
"Bryson":"m","Amir":"m","Giovanni":"m","Chase":"m","Diego":"m",
"Milo":"m","Jasper":"m","Walker":"m","Jason":"m","Brayden":"m",
"Cole":"m","Nathaniel":"m","George":"m","Lorenzo":"m","Zion":"m",
"Luis":"m","Archer":"m","Enzo":"m","Jonah":"m","Thiago":"m",
"Theo":"m","Ayden":"m","Zachary":"m","Calvin":"m","Braxton":"m",
"Ashton":"m","Rhett":"m","Atlas":"m","Jude":"m","Bentley":"m",
"Carlos":"m","Ryker":"m","Adriel":"m","Arthur":"m","Ace":"m",
"Tyler":"m","Jayce":"m","Max":"m","Elliot":"m","Graham":"m",
"Kaiden":"m","Maxwell":"m","Juan":"m","Dean":"m","Matteo":"m",
"Malachi":"m","Ivan":"m","Elliott":"m","Jesus":"m","Emiliano":"m",
"Messiah":"m","Gavin":"m","Maddox":"m","Camden":"m","Hayden":"m",
"Leon":"m","Antonio":"m","Justin":"m","Tucker":"m","Brandon":"m",
"Kevin":"m","Judah":"m","Finn":"m","King":"m","Brody":"m",
"Xander":"m","Nicolas":"m","Charlie":"m","Arlo":"m","Emmanuel":"m",
"Barrett":"m","Felix":"m","Alex":"m","Miguel":"m","Abel":"m",
"Alan":"m","Beckett":"m","Amari":"m","Karter":"m","Timothy":"m",
"Abraham":"m","Jesse":"m","Zayden":"m","Blake":"m","Alejandro":"m",
"Dawson":"m","Tristan":"m","Victor":"m","Avery":"m","Joel":"m",
"Grant":"m","Eric":"m","Patrick":"m","Peter":"m","Richard":"m",
"Edward":"m","Andres":"m","Emilio":"m","Colt":"m","Knox":"m",
"Beckham":"m","Adonis":"m","Kyrie":"m","Matias":"m","Oscar":"m",
"Lukas":"m","Marcus":"m","Hayes":"m","Caden":"m","Remington":"m",
"Griffin":"m","Nash":"m","Israel":"m","Steven":"m","Holden":"m",
"Rafael":"m","Zane":"m","Jeremy":"m","Kash":"m","PrestonRowan":"m",
"Kyler":"m","Jax":"m","Jett":"m","Kaleb":"m","Riley":"m",
"Simon":"m","Phoenix":"m","Javier":"m","Bryce":"m","Louis":"m",
"Mark":"m","Cash":"m","Lennox":"m","Paxton":"m","Malakai":"m",
"Paul":"m","Kenneth":"m","Nico":"m","Kaden":"m","Lane":"m",
"Kairo":"m","Maximus":"m","Omar":"m","Finley":"m","Atticus":"m",
"Crew":"m","Brantley":"m","Colin":"m","Dallas":"m","Walter":"m",
"Brady":"m","Callum":"m","Ronan":"m","Hendrix":"m","Jorge":"m",
"Tobias":"m","Clayton":"m","Emerson":"m","Damien":"m","Zayn":"m",
"Malcolm":"m","Kayson":"m","Bodhi":"m","Bryan":"m","Aidan":"m",
"Cohen":"m","Brian":"m","Cayden":"m","Andre":"m","Niko":"m",
"Maximiliano":"m","Zander":"m","Khalil":"m","Rory":"m","Francisco":"m",
"Cruz":"m","Kobe":"m","Reid":"m","Daxton":"m","Derek":"m",
"Martin":"m","Jensen":"m","Karson":"m","Tate":"m","Muhammad":"m",
"Jaden":"m","Joaquin":"m","Josue":"m","Gideon":"m","Dante":"m",
"Cody":"m","Bradley":"m","Orion":"m","Spencer":"m","Angelo":"m",
"Erick":"m","Jaylen":"m","Julius":"m","Manuel":"m","Ellis":"m",
"Colson":"m","Cairo":"m","Gunner":"m","Wade":"m","Chance":"m",
"Odin":"m","Anderson":"m","Kane":"m","Raymond":"m","Cristian":"m",
"Aziel":"m","Prince":"m","Ezequiel":"m","Jake":"m","Otto":"m",
"Eduardo":"m","Rylan":"m","Ali":"m","Cade":"m","Stephen":"m",
"Ari":"m","Kameron":"m","Dakota":"m","Warren":"m","Ricardo":"m",
"Killian":"m","Mario":"m","Romeo":"m","Cyrus":"m","Ismael":"m",
"Russell":"m","Tyson":"m","Edwin":"m","Desmond":"m","Nasir":"m",
"Remy":"m","Tanner":"m","Fernando":"m","Hector":"m","Titus":"m",
"Lawson":"m","Sean":"m","Kyle":"m","Elian":"m","Corbin":"m",
"Bowen":"m","Wilder":"m","Armani":"m","Royal":"m","Stetson":"m",
"Briggs":"m","Sullivan":"m","Leonel":"m","Callan":"m","Finnegan":"m",
"Jay":"m","Zayne":"m","Marshall":"m","Kade":"m","Travis":"m",
"Sterling":"m","Raiden":"m","Sergio":"m","Tatum":"m","Cesar":"m",
"Zyaire":"m","Milan":"m","Devin":"m","Gianni":"m","Kamari":"m",
"Royce":"m","Malik":"m","Jared":"m","Franklin":"m","Clark":"m",
"Noel":"m","Marco":"m","Archie":"m","Apollo":"m","Pablo":"m",
"Garrett":"m","Oakley":"m","Memphis":"m","Quinn":"m","Onyx":"m",
"Alijah":"m","Baylor":"m","Edgar":"m","Nehemiah":"m","Winston":"m",
"Major":"m","Rhys":"m","Forrest":"m","Jaiden":"m","Reed":"m",
"Santino":"m","Troy":"m","Caiden":"m","Harvey":"m","Collin":"m",
"Solomon":"m","Donovan":"m","Damon":"m","Jeffrey":"m","Kason":"m",
"Sage":"m","Grady":"m","Kendrick":"m","Leland":"m","Luciano":"m",
"Pedro":"m","Hank":"m","Hugo":"m","Esteban":"m","Johnny":"m",
"Kashton":"m","Ronin":"m","Ford":"m","Mathias":"m","Porter":"m",
"Erik":"m","Johnathan":"m","Frank":"m","Tripp":"m","Casey":"m",
"Fabian":"m","Leonidas":"m","Baker":"m","Matthias":"m","Philip":"m",
"Jayceon":"m","Kian":"m","Saint":"m","Ibrahim":"m","Jaxton":"m",
"Augustus":"m","Callen":"m","Trevor":"m","Ruben":"m","Adan":"m",
"Conor":"m","Dax":"m","Braylen":"m","Kaison":"m","Francis":"m",
"Kyson":"m","Andy":"m","Lucca":"m","Mack":"m","Peyton":"m",
"Alexis":"m","Deacon":"m","Kasen":"m","Kamden":"m","Frederick":"m",
"Princeton":"m","Braylon":"m","Wells":"m","Nikolai":"m","Iker":"m",
"Bo":"m","Dominick":"m","Moshe":"m","Cassius":"m","Gregory":"m",
"Lewis":"m","Kieran":"m","Isaias":"m","Seth":"m","Marcos":"m",
"Omari":"m","Shane":"m","Keegan":"m","Jase":"m","Asa":"m",
"Sonny":"m","Uriel":"m","Pierce":"m","Jasiah":"m","Barack":"m",
"Mike":"m","Pete":"m","Ants":"m","Jaan":"m","Juhan":"m",
"Konstantin":"m","Aleksei":"m","Tanel":"m","Mihkel":"m","Ott":"m",
"Peeter":"m","Sander":"m","Aleksander":"m","Kristjan":"m","Kevin,":"m",
"Nikita":"m","Markus":"m","Artur":"m","Maksim":"m","Karl":"m",
"Dmitri":"m","Daniil":"m","Siim":"m","Rasmus":"m","Andrei":"m",
"Artjom":"m","Ilja":"m","Uku":"m","Jaanus":"m","Jan":"m",
"Mattias":"m","Joonas":"m","Jonas":"m","Anton":"m","Nils":"m",
"Svante":"m","Per":"m","Olle":"m","Gustav":"m","Hjalmar":"m",
"Carl":"m","Alfred":"m","Ben":"m","Jakob":"m","Maximilian":"m",
"Niklas":"m","Hannes":"m","Jules":"m","Mohamed":"m","Mohammed":"m",
"Marius":"m","Robin":"m","Bjorn":"m","Olivia":"f","Emma":"f",
"Charlotte":"f","Amelia":"f","Ava":"f","Sophia":"f","Isabella":"f",
"Mia":"f","Evelyn":"f","Harper":"f","Luna":"f","Camila":"f",
"Gianna":"f","Elizabeth":"f","Eleanor":"f","Ella":"f","Abigail":"f",
"Sofia":"f","Scarlett":"f","Emily":"f","Aria":"f","Penelope":"f",
"Chloe":"f","Layla":"f","Mila":"f","Nora":"f","Hazel":"f",
"Madison":"f","Ellie":"f","Lily":"f","Nova":"f","Isla":"f",
"Grace":"f","Violet":"f","Aurora":"f","Zoey":"f","Willow":"f",
"Emilia":"f","Stella":"f","Zoe":"f","Victoria":"f","Hannah":"f",
"Addison":"f","Leah":"f","Lucy":"f","Eliana":"f","Ivy":"f",
"Everly":"f","Lillian":"f","Paisley":"f","Elena":"f","Naomi":"f",
"Maya":"f","Natalie":"f","Kinsley":"f","Delilah":"f","Claire":"f",
"Audrey":"f","Aaliyah":"f","Ruby":"f","Brooklyn":"f","Alice":"f",
"Aubrey":"f","Autumn":"f","Leilani":"f","Savannah":"f","Valentina":"f",
"Kennedy":"f","Madelyn":"f","Josephine":"f","Bella":"f","Skylar":"f",
"Genesis":"f","Sophie":"f","Hailey":"f","Sadie":"f","Natalia":"f",
"Caroline":"f","Allison":"f","Gabriella":"f","Anna":"f","Serenity":"f",
"Nevaeh":"f","Cora":"f","Ariana":"f","Emery":"f","Lydia":"f",
"Jade":"f","Sarah":"f","Eva":"f","Adeline":"f","Madeline":"f",
"Piper":"f","Rylee":"f","Athena":"f","Everleigh":"f","Vivian":"f",
"Clara":"f","Raelynn":"f","Liliana":"f","Samantha":"f","Maria":"f",
"Iris":"f","Ayla":"f","Eloise":"f","Lyla":"f","Eliza":"f",
"Hadley":"f","Melody":"f","Julia":"f","Rose":"f","Isabelle":"f",
"Brielle":"f","Adalynn":"f","Arya":"f","Eden":"f","Remi":"f",
"Mackenzie":"f","Maeve":"f","Margaret":"f","Reagan":"f","Alaia":"f",
"Melanie":"f","Josie":"f","Elliana":"f","Cecilia":"f","Mary":"f",
"Daisy":"f","Alina":"f","Lucia":"f","Ximena":"f","Juniper":"f",
"Kaylee":"f","Magnolia":"f","Summer":"f","Adalyn":"f","Sloane":"f",
"Amara":"f","Arianna":"f","Isabel":"f","Reese":"f","Emersyn":"f",
"Sienna":"f","Kehlani":"f","Freya":"f","Valerie":"f","Blakely":"f",
"Genevieve":"f","Esther":"f","Valeria":"f","Katherine":"f","Kylie":"f",
"Norah":"f","Amaya":"f","Bailey":"f","Ember":"f","Ryleigh":"f",
"Georgia":"f","Catalina":"f","Alexandra":"f","Faith":"f","Jasmine":"f",
"Ariella":"f","Ashley":"f","Andrea":"f","Millie":"f","June":"f",
"Khloe":"f","Callie":"f","Juliette":"f","Ada":"f","Anastasia":"f",
"Olive":"f","Alani":"f","Brianna":"f","Rosalie":"f","Molly":"f",
"Brynlee":"f","Amy":"f","Ruth":"f","Aubree":"f","Gemma":"f",
"Taylor":"f","Margot":"f","Arabella":"f","Sara":"f","Journee":"f",
"Harmony":"f","Alaina":"f","Aspen":"f","Noelle":"f","Selena":"f",
"Oaklynn":"f","Morgan":"f","Londyn":"f","Zuri":"f","Aliyah":"f",
"Jordyn":"f","Juliana":"f","Presley":"f","Zara":"f","Leila":"f",
"Marley":"f","Amira":"f","Lilly":"f","London":"f","Kimberly":"f",
"Elsie":"f","Ariel":"f","Lila":"f","Alana":"f","Diana":"f",
"Kamila":"f","Nyla":"f","Vera":"f","Hope":"f","Annie":"f",
"Kaia":"f","Myla":"f","Alyssa":"f","Angela":"f","Ana":"f",
"Lennon":"f","Evangeline":"f","Harlow":"f","Rachel":"f","Gracie":"f",
"Laila":"f","Elise":"f","Sutton":"f","Lilah":"f","Adelyn":"f",
"Phoebe":"f","Octavia":"f","Sydney":"f","Mariana":"f","Wren":"f",
"Lainey":"f","Vanessa":"f","Teagan":"f","Kayla":"f","Malia":"f",
"Elaina":"f","Saylor":"f","Brooke":"f","Lola":"f","Miriam":"f",
"Alayna":"f","Adelaide":"f","Daniela":"f","Jane":"f","Payton":"f",
"Journey":"f","Lilith":"f","Delaney":"f","Mya":"f","Charlee":"f",
"Alivia":"f","Annabelle":"f","Kailani":"f","Lucille":"f","Trinity":"f",
"Gia":"f","Raegan":"f","Camille":"f","Kaylani":"f","Kali":"f",
"Stevie":"f","Maggie":"f","Haven":"f","Tessa":"f","Daphne":"f",
"Adaline":"f","Joanna":"f","Jocelyn":"f","Lena":"f","Evie":"f",
"Juliet":"f","Fiona":"f","Cataleya":"f","Angelina":"f","Leia":"f",
"Paige":"f","Julianna":"f","Milani":"f","Talia":"f","Rebecca":"f",
"Kendall":"f","Harley":"f","Lia":"f","Dahlia":"f","Camilla":"f",
"Thea":"f","Jayla":"f","Brooklynn":"f","Blair":"f","Vivienne":"f",
"Hallie":"f","Madilyn":"f","Mckenna":"f","Evelynn":"f","Ophelia":"f",
"Celeste":"f","Alayah":"f","Winter":"f","Catherine":"f","Collins":"f",
"Nina":"f","Briella":"f","Palmer":"f","Noa":"f","Mckenzie":"f",
"Kiara":"f","Adriana":"f","Gracelynn":"f","Lauren":"f","Cali":"f",
"Kalani":"f","Aniyah":"f","Nicole":"f","Mariah":"f","Gabriela":"f",
"Wynter":"f","Amina":"f","Ariyah":"f","Adelynn":"f","Reign":"f",
"Alaya":"f","Dream":"f","Alexandria":"f","Willa":"f","Avianna":"f",
"Makayla":"f","Gracelyn":"f","Elle":"f","Amiyah":"f","Arielle":"f",
"Elianna":"f","Giselle":"f","Brynn":"f","Ainsley":"f","Aitana":"f",
"Charli":"f","Demi":"f","Makenna":"f","Rosemary":"f","Danna":"f",
"Izabella":"f","Lilliana":"f","Melissa":"f","Samara":"f","Lana":"f",
"Mabel":"f","Everlee":"f","Fatima":"f","Leighton":"f","Esme":"f",
"Raelyn":"f","Madeleine":"f","Nayeli":"f","Camryn":"f","Kira":"f",
"Annalise":"f","Selah":"f","Serena":"f","Royalty":"f","Rylie":"f",
"Celine":"f","Laura":"f","Brinley":"f","Frances":"f","Michelle":"f",
"Heidi":"f","Sabrina":"f","Destiny":"f","Gwendolyn":"f","Alessandra":"f",
"Poppy":"f","Amora":"f","Nylah":"f","Luciana":"f","Maisie":"f",
"Miracle":"f","Joy":"f","Liana":"f","Raven":"f","Shiloh":"f",
"Allie":"f","Daleyza":"f","Kate":"f","Lyric":"f","Alicia":"f",
"Lexi":"f","Addilyn":"f","Anaya":"f","Malani":"f","Paislee":"f",
"Elisa":"f","Kayleigh":"f","Azalea":"f","Francesca":"f","Regina":"f",
"Viviana":"f","Aylin":"f","Skye":"f","Daniella":"f","Makenzie":"f",
"Veronica":"f","Legacy":"f","Maia":"f","Ariah":"f","Alessia":"f",
"Carmen":"f","Astrid":"f","Maren":"f","Helen":"f","Felicity":"f",
"Alexa":"f","Danielle":"f","Lorelei":"f","Paris":"f","Adelina":"f",
"Bianca":"f","Gabrielle":"f","Jazlyn":"f","Scarlet":"f","Bristol":"f",
"Navy":"f","Esmeralda":"f","Colette":"f","Stephanie":"f","Jolene":"f",
"Marlee":"f","Sarai":"f","Hattie":"f","Nadia":"f","Rosie":"f",
"Kamryn":"f","Kenzie":"f","Alora":"f","Holly":"f","Matilda":"f",
"Sylvia":"f","Emelia":"f","Keira":"f","Braelynn":"f","Jacqueline":"f",
"Alison":"f","Amanda":"f","Cassidy":"f","Emory":"f","Haisley":"f",
"Jimena":"f","Jessica":"f","Elaine":"f","Dorothy":"f","Mira":"f",
"Eve":"f","Oaklee":"f","Averie":"f","Charleigh":"f","Lyra":"f",
"Madelynn":"f","Edith":"f","Jennifer":"f","Raya":"f","Heaven":"f",
"Kyla":"f","Wrenley":"f","Meadow":"f","Pia":"f","Piia":"f",
"Mari":"f","Kristiina":"f","Kristi":"f","Liisi":"f","Liis":"f",
"Liisu":"f","Leena":"f","Kristina":"f","Sandra":"f","Anastassia":"f",
"Jekaterina":"f","Karina":"f","Aleksandra":"f","Viktoria":"f","Darja":"f",
"Triin":"f","Moa":"f","Ingrid":"f","Rutt":"f","Signe":"f",
"Elsa":"f","Brit":"f","Britta":"f","Alma":"f","Selma":"f",
"Elina":"f","Elin":"f","Lina":"f","Marie":"f","Leni":"f",
"Mathilda":"f","Frieda":"f","Frida":"f","Nele":"f","Marlene":"f",
"Merle":"f","Agathe":"f","Ambre":"f","Ines":"f",
"Harry":"m","Imelia":"f","Mickey":"m","Minnie":"f",
"Dave": "m","Colin": "m", "Bill":"m",
"Winona": "f", "Jessica":"f", "Gertrude":"f"
}

pseudo_names={"Mr":"m","Mrs":"f","Ms":"f"}

person_names=z = {**first_names, **pseudo_names}

gendered_words={
"abbess":"f","abbot":"m","able_seaman":"m","actress":"f","adonis":"m","adulteress":"f",
"adventuress":"f","aircraftsman":"m","aircrewman":"m","alderman":"m","altar_boy":"m",
"amazon":"f","ambassadress":"f","ancestress":"f","ape-man":"m","apostle":"m",
"archbishop":"m","archdeacon":"m","archduchess":"f","archpriest":"m","armiger":"m",
"artilleryman":"m","assemblyman":"m","assemblywoman":"f","au_pair_girl":"f","augustinian":"m",
"aunt":"f","austin_friar":"m","authoress":"f","aviatrix":"f","ayah":"f",
"b-girl":"f","babu":"m","bacchant":"m","bacchante":"f","bachelor":"m",
"bachelor_girl":"f","backroom_boy":"m","bag":"f","bag_lady":"f","baggage":"f",
"baggageman":"m","bagman":"m","ball_boy":"m","ball-buster":"f","ballerina":"f",
"ballet_master":"m","ballet_mistress":"f","bandsman":"m","baritone":"m","barmaid":"f",
"baron":"m","baroness":"f","basileus":"m","bass":"m","bat_boy":"m",
"batman":"m","beadsman":"m","beard":"f","beggarman":"m","beggarwoman":"f",
"beguine":"f","begum":"f","beldam":"f","bellboy":"m","belle":"f",
"belly_dancer":"f","benedick":"m","benefactress":"f","best_man":"m","bey":"m",
"big_brother":"m","big_sister":"f","black_man":"m","black_woman":"f","blade":"m",
"blood_brother":"m","bluestocking":"f","boatman":"m","bobbysoxer":"f","bondman":"m",
"bondsman":"m","bondwoman":"f","border_patrolman":"m","boy":"m","boy_scout":"m",
"boy_wonder":"m","boyfriend":"m","brahman":"m","brakeman":"m","bride":"f",
"bridesmaid":"f","broad":"f","broth_of_a_boy":"m","brother":"m","brother-in-law":"m",
"brownie":"f","brunet":"m","buddy":"m","bull":"m","bullyboy":"m",
"burgrave":"m","busboy":"m","bushman":"m","businessman":"m","businesswoman":"f",
"butch":"f","butler":"m","cabin_boy":"m","call_girl":"f","cameraman":"m",
"campfire_girl":"f","canary":"f","capo":"m","career_girl":"f","career_man":"m",
"casanova":"m","castrato":"m","cat":"f","catamite":"m","cattleman":"m",
"cavalier":"m","cavalryman":"m","caveman":"m","centurion":"m","chachka":"f",
"chairman_of_the_board":"m","chambermaid":"f","chapman":"m","charon":"m","charwoman":"f",
"chatelaine":"f","check_girl":"f","choirboy":"m","chorus_girl":"f","church_father":"m",
"cinderella":"f","circe":"f","city_man":"m","clansman":"m","clergyman":"m",
"cleric":"m","closet_queen":"m","co-ed":"f","coachman":"m","coalman":"m",
"coastguardsman":"m","codger":"m","coiffeur":"m","coiffeuse":"f","colleen":"f",
"coloratura":"f","comedienne":"f","comfort_woman":"f","committeeman":"m","committeewoman":"f",
"company_man":"m","concubine":"f","conductress":"f","confidante":"f","confidence_man":"m",
"congressman":"m","contralto":"f","coquette":"f","cornishman":"m","cornishwoman":"f",
"councilman":"m","councilwoman":"f","count":"m","countertenor":"m","countess":"f",
"countryman":"m","countrywoman":"f","cover_girl":"f","cow":"f","cowboy":"m",
"cowgirl":"f","craftsman":"m","crewman":"m","crown_prince":"m","crown_princess":"f",
"cub":"m","cub_scout":"m","cuckold":"m","curandera":"f","curandero":"m",
"cyril":"m","czar":"m","czarina":"f","dad":"m","dairymaid":"f",
"dairyman":"m","dalesman":"m","dame":"f","damsel":"f","dandy":"m",
"danseur":"m","daughter":"f","daughter-in-law":"f","dauphin":"m","dayboy":"m",
"daygirl":"f","deacon":"m","deaconess":"f","deadbeat_dad":"m","dean":"m",
"debutante":"f","deliveryman":"m","demimondaine":"f","den_mother":"f","dirty_old_man":"m",
"divorcee":"f","dog":"m","doge":"m","domestic_prelate":"m","don":"m",
"don_juan":"m","donna":"f","doorkeeper":"m","doughboy":"m","doyenne":"f",
"draftsman":"m","dragoman":"m","dragon":"f","drum_majorette":"f","duchess":"f",
"duenna":"f","duke":"m","dutch_uncle":"m","eagle_scout":"m","earl":"m",
"earl_marshal":"m","ejaculator":"m","elder_statesman":"m","elector":"m","embroideress":"f",
"emir":"m","emperor":"m","empress":"f","enchantress":"f","end_man":"m",
"englishman":"m","englishwoman":"f","enlisted_man":"m","enlisted_woman":"f","ent_man":"m",
"eparch":"m","esquire":"m","ethnarch":"m","everyman":"m","ex-boyfriend":"m",
"ex-husband":"m","ex-wife":"f","exarch":"m","excavator":"m","executrix":"f",
"eyeful":"f","fairy_godmother":"f","family_man":"m","fancy_man":"m","farm_boy":"m",
"farm_girl":"f","farmerette":"f","fathead":"m","father":"m","father_figure":"m",
"father-figure":"m","father-in-law":"m","fauntleroy":"m","favorite_son":"m","fellow":"m",
"female":"f","female_aristocrat":"f","female_child":"f","female_offspring":"f","female_sibling":"f",
"ferryman":"m","feudal_lord":"m","fiancee":"f","fireman":"m","first_baseman":"m",
"first_lady":"f","fisherman":"m","flamen":"m","flapper":"f","flibbertigibbet":"f",
"flower_girl":"f","footman":"m","forefather":"m","foreman":"m","foremother":"f",
"forewoman":"f","foster-brother":"m","foster-daughter":"f","foster-father":"m","foster-mother":"f",
"foster-nurse":"f","foster-sister":"f","foster-son":"m","foundress":"f","four-minute_man":"m",
"franklin":"m","freedman":"m","freeman":"m","frenchman":"m","friar":"m",
"front_man":"m","frontiersman":"m","frontierswoman":"f","frump":"f","fugleman":"m",
"g-man":"m","gagman":"m","gal":"f","galoot":"m","gamine":"f",
"ganger":"m","garbage_man":"m","gasman":"m","gaucho":"m","gay_man":"m",
"geezer":"m","geisha":"f","gent":"m","gentleman":"m","gentlemen":"m",
"gibson_girl":"f","gillie":"m","girl":"f","girl_friday":"f","girl_scout":"f",
"girl_wonder":"f","girlfriend":"f","gitana":"f","gitano":"m","goddaughter":"f",
"godfather":"m","godmother":"f","godson":"m","gold_digger":"f","golf_widow":"f",
"goliard":"m","good_old_boy":"m","governess":"f","grand_duchess":"f","grand_duke":"m",
"granddaughter":"f","grande_dame":"f","grandee":"m","grandfather":"m","grandson":"m",
"granny":"f","grass_widower":"m","gravida":"f","great_granddaughter":"f","great_grandfather":"m",
"great_grandmother":"f","great_grandson":"m","great-aunt":"f","great-nephew":"m","great-niece":"f",
"great-uncle":"m","grocery_boy":"m","groom":"m","groomsman":"m","groundsman":"m",
"groupie":"f","guardsman":"m","gunman":"m","guy":"m","hag":"f",
"half_sister":"f","handmaid":"f","handyman":"m","hangman":"m","harridan":"f",
"hatchet_man":"m","he":"m","head_linesman":"m","headman":"m","headmistress":"f",
"headsman":"m","heidelberg_man":"m","heiress":"f","helmsman":"m","her":"f",
"heroine":"f","herr":"m","hers":"f","herself":"f","him":"m",
"himself":"m","his":"m","hobbledehoy":"m","holdup_man":"m","holy_roman_emperor":"m",
"homeboy":"m","homegirl":"f","honest_woman":"f","hooray_henry":"m","horseman":"m",
"horsewoman":"f","hostess":"f","housefather":"m","housemother":"f","housewife":"f",
"huntress":"f","husband":"m","iceman":"m","idolatress":"f","imam":"m",
"inamorata":"f","inamorato":"m","indiana":"m","infantryman":"m","ingenue":"f",
"instructress":"f","irishman":"m","irishwoman":"f","iron_man":"m","ironside":"m",
"jacob":"m","jane_doe":"f","jawan":"m","jewess":"f","jezebel":"f",
"jilt":"f","jimdandy":"m","john_doe":"m","jute":"m","kaiser":"m",
"kennan":"m","king":"m","king_of_england":"m","king_of_france":"m","king_of_the_germans":"m",
"kinsman":"m","kinswoman":"f","klansman":"m","knight_of_the_round_table":"m","knight_templar":"m",
"knight-errant":"m","lackey":"m","ladies":"f","lady":"f","lady's_maid":"f",
"ladylove":"f","landlady":"f","lass":"f","lawman":"m","layman":"m",
"leading_lady":"f","leading_man":"m","letterman":"m","libertine":"m","liege":"m",
"life_peer":"m","light-o'-love":"f","lighterman":"m","limey":"m","lineman":"m",
"linesman":"m","linkboy":"m","little_brother":"m","little_sister":"f","liveryman":"m",
"lobsterman":"m","lollipop_lady":"f","longbowman":"m","loon":"m","lord":"m",
"lord_chancellor":"m","lothario":"m","lounge_lizard":"m","lowerclassman":"m","lumberman":"m",
"ma":"f","ma'am":"f","macaroni":"m","macho":"m","madam":"f",
"madame":"f","madwoman":"f","maenad":"f","mafioso":"m","maharaja":"m",
"maharani":"f","maid":"f","maiden_aunt":"f","mailman":"m","male":"m",
"male_aristocrat":"m","male_chauvinist":"m","male_child":"m","male_offspring":"m","male_sibling":"m",
"malik":"m","mamma":"f","mammy":"f","man":"m","man_jack":"m",
"man_of_letters":"m","man_of_means":"m","man-at-arms":"m","manageress":"f","mannequin":"f",
"manservant":"m","marchioness":"f","margrave":"m","marksman":"m","marquess":"m",
"marquis":"m","masseur":"m","matriarch":"f","matron":"f","matron_of_honor":"f",
"may_queen":"f","mayoress":"f","mediatrix":"f","medicine_man":"m","memsahib":"f",
"men":"m","mesne_lord":"m","messenger_boy":"m","mestiza":"f","mestizo":"m",
"meter_maid":"f","middle-aged_man":"m","midshipman":"m","midwife":"f","mikado":"m",
"milady":"f","miles_gloriosus":"m","military_policeman":"m","militiaman":"m","milkman":"m",
"mill-girl":"f","millionairess":"f","milord":"m","minuteman":"m","miracle_man":"m",
"misogynist":"m","miss":"f","missus":"f","mistress":"f","mollycoddle":"m",
"monk":"m","monsieur":"m","monsignor":"m","mother":"f","mother_figure":"f",
"mother_hen":"f","mother-in-law":"f","mother's_boy":"m","mother's_daughter":"f","mother's_son":"m",
"mover":"m","mr.":"m","mrs.":"f","ms.":"f","muffin_man":"m",
"mullah":"m","murderess":"f","muscleman":"m","muslimah":"f","nabob":"m",
"nan":"f","nanny":"f","nautch_girl":"f","negotiatress":"f","negress":"f",
"nephew":"m","newswoman":"f","niece":"f","night_watchman":"m","niqaabi":"f",
"novillero":"m","nullipara":"f","nun":"f","nuncio":"m","nymph":"f",
"nymphet":"f","nymphomaniac":"f","oarsman":"m","oarswoman":"f","odalisque":"f",
"office_boy":"m","oilman":"m","oklahoman":"m","old_boy":"m","old_lady":"f",
"old_man":"m","old_woman":"f","one_of_the_boys":"m","orangeman":"m","ordinary":"m",
"organization_man":"m","ottoman":"m","outdoorsman":"m","outdoorswoman":"f","pachuco":"m",
"page":"m","palatine":"m","paperboy":"m","parisienne":"f","parlormaid":"f",
"party_girl":"f","party_man":"m","pater":"m","patriarch":"m","patroness":"f",
"pederast":"m","peer":"m","peer_of_the_realm":"m","pendragon":"m","peri":"f",
"peter_pan":"m","pharaoh":"m","pilate":"m","piltdown_man":"m","pitchman":"m",
"placeman":"m","plainclothesman":"m","plainsman":"m","plowboy":"m","plowman":"m",
"poetess":"f","point_man":"m","point_woman":"f","pointsman":"m","police_matron":"f",
"policeman":"m","polyandrist":"f","polycarp":"m","polygynist":"m","ponce":"m",
"ponce_de_leon":"m","pope":"m","popper":"m","poseuse":"f","posseman":"m",
"poster_boy":"m","poster_girl":"f","postmistress":"f","potboy":"m","poultryman":"m",
"praetor":"m","priest":"m","priestess":"f","prima_ballerina":"f","prima_donna":"f",
"primigravida":"f","primipara":"f","prince_consort":"f","prince_of_wales":"m","princeling":"m",
"princess":"f","princess_royal":"f","proconsul":"m","procuress":"f","property_man":"m",
"prophetess":"f","proprietress":"f","protegee":"f","puerpera":"f","quadripara":"f",
"quarryman":"m","queen":"f","queen_consort":"f","queen_dowager":"f","queen_mother":"f",
"queen_of_england":"f","queen_regent":"f","quintipara":"f","raftsman":"m","raja":"m",
"rake":"m","rani":"f","remittance_man":"m","renaissance_man":"m","repairman":"m",
"rhea_silvia":"f","rifleman":"m","right-hand_man":"m","ring_girl":"f","roadman":"m",
"roman":"m","roman_emperor":"m","romeo":"m","rosebud":"f","roundsman":"m",
"sadhu":"m","salesgirl":"f","salesman":"m","samurai":"m","sandboy":"m",
"sandwichman":"m","sannup":"m","satyr":"m","schoolboy":"m","schoolgirl":"f",
"schoolman":"m","schoolmarm":"f","scold":"f","scotswoman":"f","sculptress":"f",
"sea_scout":"m","second_baseman":"m","section_man":"m","secundigravida":"f","seducer":"m",
"seductress":"f","seedsman":"m","selectman":"m","selectwoman":"f","senhor":"m",
"servant_girl":"f","serviceman":"m","sex_kitten":"f","shah":"m","shaheed":"m",
"shaver":"m","she":"f","she-devil":"f","sheepman":"m","sheik":"m",
"sheika":"f","shepherdess":"f","shiksa":"f","shop_boy":"m","shop_girl":"f",
"showman":"m","shrew":"f","sibyl":"f","sidesman":"m","signalman":"m",
"signor":"m","signora":"f","signore":"m","signorina":"f","simeon":"m",
"sir":"m","sire":"m","sirrah":"m","sister":"f","sister-in-law":"f",
"skivvy":"f","slattern":"f","small_businessman":"m","smasher":"f","sod":"m",
"sodomite":"m","son":"m","son-in-law":"m","songstress":"f","soprano":"f",
"sorceress":"f","soubrette":"f","soul_brother":"m","soundman":"m","spinster":"f",
"spitfire":"f","spokesman":"m","spokeswoman":"f","sporting_man":"m","squaw":"f",
"squaw_man":"m","squire":"m","stableman":"m","starlet":"f","statesman":"m",
"stateswoman":"f","stepbrother":"m","stepdaughter":"f","stepfather":"m","stepmother":"f",
"stepson":"m","stewardess":"f","stiff":"m","stockman":"m","straight_man":"m",
"street_arab":"m","strongman":"m","stud":"m","stuffed_shirt":"m","subdeacon":"m",
"suffragette":"f","sugar_daddy":"m","suitor":"m","sultan":"m","sumo_wrestler":"m",
"supermom":"f","surrogate_mother":"f","swagman":"m","sweater_girl":"f","sylph":"f",
"t-man":"m","tallyman":"m","tarzan":"m","taskmistress":"f","taxi_dancer":"f",
"tenor":"m","tertigravida":"f","test-tube_baby":"f","testatrix":"f","thane":"m",
"third_baseman":"m","thrush":"f","timberman":"m","toast_mistress":"f","tom":"m",
"tomboy":"f","torch_singer":"f","town":"m","townee":"m","townes":"m",
"townsman":"m","trainbandsman":"m","trainman":"m","traitress":"f","trappist":"m",
"traveling_salesman":"m","tribesman":"m","trophy_wife":"f","uncle":"m","undoer":"f",
"unmarried_woman":"f","unpleasant_woman":"f","uriah":"m","usherette":"f","utility_man":"m",
"uxor":"f","uxoricide":"m","valley_girl":"f","vaquero":"m","vestal":"f",
"vestal_virgin":"f","vestryman":"m","vestrywoman":"f","vicar":"m","vicar_apostolic":"m",
"vicar-general":"m","vice_chairman":"m","villainess":"f","virago":"f","viscount":"m",
"viscountess":"f","visiting_fireman":"m","vizier":"m","wac":"f","waitress":"f",
"wanton":"f","war_bride":"f","war_widow":"f","wardress":"f","warlord":"m",
"washerman":"m","washwoman":"f","watchman":"m","water_boy":"m","weatherman":"m",
"welshman":"m","wencher":"m","wet_nurse":"f","white_man":"m","white_slave":"f",
"white_woman":"f","widow":"f","widower":"m","wife":"f","wild_man":"m",
"wingman":"m","wireman":"m","wittol":"m","wolf":"m","wolf_boy":"m",
"woman":"f","womanizer":"m","women":"f","wonder_boy":"m","wonder_woman":"f",
"woodsman":"m","working_girl":"f","workman":"m","yachtsman":"m","yardman":"m",
"yellow_man":"m","yellow_woman":"f","yenta":"f","yeoman":"m"}

preposition_words={
  "of":1,
	"with":1, 
	"at":1, 
	"from":1, 
	"into":1, 
	"during":1, 
	"including":1, 	
	"until":1, 	
	"against":1, 
	"among":1, 
	"throughout":1, 
	"despite":1, 
	"towards":1, 	
	"upon":1, 
	"concerning":1, 
	"to":1, 
	"in":1, 	
	"for":1, 
	"on":1, 	
	"by":1, 
	"about":1,
	"like":1, 
	"through":1, 
	"over":1, 
	"before":1, 
	"between":1, 
	"after":1,
	"since":1,
	"without":1,
	"under":1, 
	"within":1,
	"along":1,
	"following":1,
	"across":1,
	"behind":1,
	"beyond":1,
	"plus":1,
	"except":1,
	"but":1, 
	"up":1, 
	"out":1,
	"around":1,
	"down":1,
	"off":1, 
	"above":1, 
	"near":1
}
  
# =========== the end ==========
"""
verbnet 

https://www.gingersoftware.com/content/grammar-rules/verbs/list-of-phrasal-verbs/

https://www.perfect-english-grammar.com/stative-verbs.html

https://www.englishwithashish.com/stative-verbs-guide/

https://engdic.org/list-of-stative-verbs-in-english/

https://engdic.org/contraction-grammar/

https://7esl.com/english-verbs/#List_of_Verbs_by_Grammatical_Functions

https://www.worldclasslearning.com/english/4000-most-common-english-words.html
"""