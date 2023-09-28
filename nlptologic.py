# The core ud-to-logic converter parts of nlpsolver
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

# ==== standard libraries ====

import sys

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

# small utilities are in nlputils.py
from nlputils import *

# proper logic part is in nlpproperlogic
from nlpproperlogic import *

# question special handling is in nlpquestion
from nlpquestion import *

# logic simplification is in nlpsimplify
from nlpsimplify import *

# uncertainty analysis and encoding is in nlpuncertain
from nlpuncertain import *

from nlpanswer import *

from nlprewrite import *

#from nlpsolver import server_parse

# ======= globals used and changed during work ===

#constant_nr=0 # new constants created add a numeric suffic, incremented
#definition_nr=0 # new definitions created add a numeric suffic, incremented

# ========= parsing: convert ud to logic =========

# iterate over sentences and return the logic built as a python list

def parse_ud(doc,entities): 
  #debug_print("parse_ud doc",doc)
  logic=[]
  objects=[]
  question_sentence=[]
  ctxt={"logic_sentence_map":{},"dummy_nr":1,"skolem_nr":1, "confidences":True,"varnum":1, "addctxt": True, "framenr":1,
        "question_type": None, "question_dummification": True, "llm_sentence_map":[]} #, "passed_words":[]}
  if options["nocontext_flag"]:
    ctxt["addctxt"]=False
  else:
    ctxt["addctxt"]=True
  questionlogic=None
  question_definition=None
  sentencenr=1
  created_defs=[]
  for sentence in doc:
    origsentence=sentence
    sentencename="sent_"+str(sentencenr)
    sentencenr+=1
    if options["prover_explain_flag"] or options["show_logic_flag"]:
      sentencetext=doc_to_original_sentence(sentence)
      ctxt["logic_sentence_map"][sentencename]=sentencetext   
    sentence=fix_ner(ctxt,sentence)   
    #debug_print("sentence1",sentence)   
    sentence2=fix_lemma_capitalization(ctxt,sentence)
    #debug_print("sentence2",sentence2)
    sentence3=fix_capital_propn(ctxt,sentence2,entities)
    #debug_print("sentence3",sentence3)
    #print("replacement_text_rules",nlpglobals.replacement_text_rules)
    sentence4=rewrite_sentence(ctxt,sentence3)    
    #sentence4=fix_capital_propn(ctxt,sentence4)
    #debug_print("rewrite_sentence gave sentence4 1",sentence4)
    if sentence4!=sentence3:
      sentence4=fix_capital_propn(ctxt,sentence4,entities)
      sentence4=fix_lemma_capitalization(ctxt,sentence4)
    #debug_print("sentence4 2",sentence4)  
    sentence=sentence4
    for word in sentence:
      word["sentence_nr"]=sentencenr
    questionsentence=False
    directresult=None
    if is_question_sentence(sentence):
      # modify question sentence before processing
      # possibly by changing text and ud-parsing again
      questionsentence=True
      question_sentence=sentence
      #debug_print("question detected",sentence)
      sentence=prepare_question_sentence(ctxt,sentence,origsentence) 
      if sentence and type(sentence)==dict and "result" in sentence:
        #debug_print("sentence!!!",sentence)
        directresult=sentence
      else:  
        #debug_print("question sentence",sentence)
        sentence=fix_ner(ctxt,sentence) 
        sentence=fix_lemma_capitalization(ctxt,sentence)
        sentence=fix_capital_propn(ctxt,sentence,entities)
        for word in sentence:
          word["sentence_nr"]=sentencenr
      #debug_print("question sentence2",sentence) 
    # main processing starts
    if directresult: 
      # got early result
      break
    oldobjects=objects.copy()
    sentence_ctxt={"previous_logic":logic,"objects":objects,"varnum":ctxt["varnum"], "sentence_defs":[], # "varnum":ctxt["varnum"]
                   "sentence_extralogic":[],
                   "skolem_nr": ctxt["skolem_nr"],"varobjects":[], "addctxt":ctxt["addctxt"],
                   "framenr":ctxt["framenr"],
                   "isquestion": questionsentence, "confidences": ctxt["confidences"],
                   "question_type":ctxt["question_type"], "question_dummification":ctxt["question_dummification"] }
                   # "passed_words":ctxt["passed_words"]}
    if options["debug_print_flag"]:
      #print("before parse_sentence varnum",sentence_ctxt["varnum"])
      #print("before parse_sentence objects")
      #show_objects(ctxt)
      #debug_print("question sentence3",sentence) 
      sentenceres=parse_sentence(sentence_ctxt,sentence,dummy_name)
    else:
      try:
        #debug_print("question sentence3a",sentence)
        sentenceres=parse_sentence(sentence_ctxt,sentence,dummy_name)
      except:       
        return "Did not understand an input sentence: "+doc_to_original_sentence(sentence)   
    #debug_print("question_type",sentence_ctxt["question_type"])
    #debug_print("sentence result:")
    #debug_print("sentenceres",sentenceres)
    #debug_print("sentence_ctxt",sentence_ctxt)
    #debug_print("immediately after parse_sentence objects are")
    #show_objects(ctxt)
    if not sentenceres:
      debug_print("empty result")  
      if sentence_ctxt["isquestion"]:
        return {"result":"Did not understand the question: try to rephrase."}
    if "sentence_extralogic" in sentenceres:
      debug_print("sentence_extralogic",sentence_ctxt["sentence_extralogic"])  
    if "sentence_defs" in sentence_ctxt:
      created_defs=created_defs+sentence_ctxt["sentence_defs"]
      if sentence_ctxt["sentence_defs"]: debug_print("defs",sentence_ctxt["sentence_defs"])               
    if "objects" in sentenceres:  
      debug_print("objects",sentenceres["objects"])
    if "question" in sentenceres:  
      debug_print("question",sentenceres["question"])    

    # add new logic and objects to the logic and objects lists in this function
    if sentenceres:     
      if "sentence_defs" in sentence_ctxt:
        newlogic=sentence_ctxt["sentence_defs"]
        newlogic_mapped=make_logic_list_sentence_map(ctxt,newlogic,sentencename)
        logic=logic+newlogic_mapped
      if "sentence_extralogic" in sentence_ctxt:
        extralogic=sentence_ctxt["sentence_extralogic"]
        if extralogic: debug_print("extralogic",extralogic)
        extralogic_mapped=make_logic_list_sentence_map(ctxt,extralogic,sentencename)
        logic=logic+extralogic_mapped  
      if "logic" in sentenceres:
        if questionsentence:
          questionlogic=sentenceres["logic"]
          #debug_print("questionlogic first",questionlogic)
        else:  
          newlogic=sentenceres["logic"]         
          newlogic_mapped=make_logic_sentence_map(ctxt,newlogic,sentencename)          
          logic=logic+[newlogic_mapped]         

      oldmap=ctxt["logic_sentence_map"]
      oldnr=ctxt["dummy_nr"]
      latest_skolem_nr=sentence_ctxt["skolem_nr"]
      old_confidences=ctxt["confidences"]
      oldvarnum=sentence_ctxt["varnum"]
      oldvarobjects=sentence_ctxt["varobjects"]
      oldaddctxt=sentence_ctxt["addctxt"]
      oldframenr=sentence_ctxt["framenr"]
      oldquestiontype=sentence_ctxt["question_type"]
      # oldpassedwords=sentence_ctxt["passed_words"]
      ctxt={"logic":logic,"objects":objects,"populated":[],"varobjects":oldvarobjects,
        "logic_sentence_map":oldmap, "dummy_nr":oldnr, "skolem_nr":latest_skolem_nr, "addctxt":oldaddctxt,
        "confidences": old_confidences,"varnum":oldvarnum, "framenr":oldframenr,"varnum":oldvarnum,
        "question_type":oldquestiontype, "question_dummification":sentence_ctxt["question_dummification"] }
        # "passed_words":oldpassedwords}        
      #debug_print("sentenceres objects",objects) 
      #debug_print("sentenceres objects:\n")

      for object in objects:        
        #debug_print("object",object)
        if (type(object[0])==list and dummy_name in object[0]):
          continue
        if (not list_contains_posval(oldobjects,0,object[0])) and (not is_var(object[0])):   
          #debug_print("to make object_constant_logic_list for object",object)         
          objectlogiclist=make_object_constant_logic_list(ctxt,sentence,object)
          #debug_print("objectlogiclist",objectlogiclist)
          mapped_objectlogiclist=make_logic_list_sentence_map(ctxt,objectlogiclist,sentencename)
          if objectlogiclist:
            logic=logic+mapped_objectlogiclist
       
      #debug_print("mapped_objectlogiclist",mapped_objectlogiclist) 
      if not questionsentence:
        make_populated_logic_list(ctxt,None,logic,True)
      #debug_print("populated",ctxt["populated"])
      if ctxt and "populated" in ctxt and ctxt["populated"]:
        logic=ctxt["populated"]+logic
        ctxt["populated"]=[]
      #debug_print("populated",ctxt["populated"])

      if not questionsentence:
        clausified_logic=clausify_logic_list(ctxt,logic)
        logic=clausified_logic        

      if questionsentence:
        break

  # - - - - sentences have been looped over - - - - 

  debug_print("=== all sentences processed ===")
  #debug_print("logic",logic)
  if directresult:
    # simple result, no proof needed   
    #return result
    return {"result": directresult["result"],      
            "logic": logic, "objects": objects, 
            "question_sentence": question_sentence,
            "question_definition": question_definition,
            "question_type": ctxt["question_type"],
            "logic_sentence_map": ctxt["logic_sentence_map"]}
  elif questionlogic:
    simplified_question_data=build_simplified_logic_list(ctxt,sentence,logic+[questionlogic])
    questionlogic=simplified_question_data[-1]
    #debug_print("questionlogic1",questionlogic)  
    questionlogic=remove_confidence_annotations_top_logic(ctxt,questionlogic)
    #debug_print("questionlogic2",questionlogic)  
    #debug_print("question_type",ctxt["question_type"])

    if ctxt["question_type"] not in ["where_is","where_does"] and suitable_question_logic(ctxt,questionlogic):
      #debug_print("suitable_question_logic found",questionlogic)
      
      if ctxt["question_dummification"]:
        questionlogic=replace_dummies_with_vars(ctxt,questionlogic)
      else:  
        tmp=[]
        questionlogic=replace_with_question_vars(questionlogic,tmp)

      questionlogic_mapped=make_logic_sentence_map(ctxt,questionlogic,sentencename)
      if questionlogic_mapped and "@name" in questionlogic_mapped:
        question={"@question": questionlogic,"@name": questionlogic_mapped["@name"]}
      else:
        question={"@question": questionlogic}  
      mainparts=logic
      logic=mainparts+[question]       
    else:        
      # debug_print("not suitable_question_logic",questionlogic)
      var="?:U"
      negated=False
      #debug_print("questionlogic",questionlogic)  
      question_data=make_question_from_logic(ctxt,questionlogic,negated,dummy_name,[var])    
      #debug_print("question_data",question_data) 
      if type(question_data)==list and question_data[0]!=None:
        defn0=question_data[0]
        question0=question_data[1]
      elif type(question_data[1])==list and question_data[1][0]=="forall":
        question0=question_data[1]
        defn0=question0[2][0]
      else:
        question0=question_data[1]
        defn0=question0[0]
      #debug_print("defn0",defn0) 
      #debug_print("question0",question0) 
  
      mainparts=logic #[:-1] 
      if options["debug_print_flag"]:
        question1=make_question_from_prequestion(ctxt,sentence,questionlogic,dummy_name)
      else:
        try:
          question1=make_question_from_prequestion(ctxt,sentence,questionlogic,dummy_name)
        except:
          print("Did not understand the question sentence.")
          sys.exit(0)
      #debug_print("question1",question1) 
      if question0 and defn0:   
        #debug_print("question0",question0) 
        #debug_print("defn0",defn0) 
        #debug_print("question_type",ctxt["question_type"])
        if "question_type" in ctxt and ctxt["question_type"] in ["where_is","where_does"]:
          wherequestion=make_where_question(ctxt,defn0,question0)
          if wherequestion:
            defn0=[defn0[0],"?:Rel"]+defn0[1:]
            question0=wherequestion
        elif "question_type" in ctxt and ctxt["question_type"] in ["when_is","when_does"]:
          whenquestion=make_when_question(ctxt,defn0,question0)
          if whenquestion:
            defn0=[defn0[0],"?:Rel"]+defn0[1:]
            question0=whenquestion    
        question0_mapped=make_logic_sentence_map(ctxt,question0,sentencename)         
        defn0_mapped=make_logic_sentence_map(ctxt,defn0,sentencename)
        if defn0_mapped and "@name" in defn0_mapped:
          question={"@question": defn0,"@name": defn0_mapped["@name"]}
        else:
          question={"@question": defn0}
        question_definition=defn0

        if question0_mapped and type(question0_mapped)==list and type(question0_mapped[0])==dict:
          logic=mainparts+question0_mapped+[question]
        else:
          logic=mainparts+[question0_mapped,question]
      elif question1 and is_simple_clause(question1["@question"]):
        question1_mapped=make_logic_sentence_map(ctxt,question1,sentencename)          
        logic=mainparts+[question1_mapped]
      else:
        newdef=[["def0","dummy"],"<=>",questionlogic]
        newdef_mapped=make_logic_sentence_map(ctxt,newdef,sentencename)
        question={"@question": ["def0","dummy"]}
        logic=mainparts+[newdef_mapped,question]  
  
  if created_defs and (options["debug_print_flag"] or options["show_logic_flag"]):
    #print("\n=== definitions created: ===\n")
    print("\ndefinitions created:\n")
    for el in created_defs:
      el=remove_confidences_from_logic(el)
      if options["noexceptions_flag"]: el=remove_exceptions(el)
      if options["noproptypes_flag"]: el=remove_prop_extras(el)
      print(" ",make_classic_logic_str(el))

  debug_print("logic before simplification:\n")
  debug_print_logic_list(logic)
  simplified_logic=build_simplified_logic_list(ctxt,sentence,logic)
  #debug_print("simplified_logic")
  #debug_print_logic_list(simplified_logic)  

  clauses=clausify_logic_list(ctxt,simplified_logic)
  #debug_print("clauses 1",clauses)
  uncertain_clauses=encode_uncertainty_clause_list(ctxt,clauses)
  #debug_print("uncertain_clauses 1",uncertain_clauses)
  uncertain_clauses=remove_confidence_annotations_frm_list(ctxt,uncertain_clauses)
  #debug_print("uncertain_clauses 2",uncertain_clauses)
  if options["noexceptions_flag"]: uncertain_clauses=remove_exceptions(uncertain_clauses)
  if options["noproptypes_flag"]: uncertain_clauses=remove_prop_extras(uncertain_clauses)
  default_to_confidence_augmented_logic=default_to_confidence_augment_logic_list(ctxt,uncertain_clauses)
  uncertain_clauses=default_to_confidence_augmented_logic
  debug_print("clauses before subsume_simplify_clause_list")
  debug_print_logic_list(uncertain_clauses)
  #uncertain_clauses=generalize_logic_list(ctxt,uncertain_clauses)
  #debug_print("clauses after generalize_logic_list")
  #debug_print_logic_list(uncertain_clauses)
  uncertain_clauses=subsume_simplify_clause_list(ctxt,uncertain_clauses)
  #debug_print("clauses after subsume_simplify")
  #debug_print_logic_list(uncertain_clauses)
  uncertain_clauses=cut_simplify_clause_list(ctxt,uncertain_clauses)
  #debug_print("clauses")
  if not clauses:
    show_error("failed to parse any sentences. Try simpler sentences.")
    sys.exit(0)
  if options["debug_print_flag"]:
    print("\nclauses:\n")
    print(clause_list_to_json(uncertain_clauses).replace("\"",""))
  #debug_print_logic_list(uncertain_clauses)
  final_result=uncertain_clauses 
  final_result=check_logic(ctxt,final_result)
  return {"logic": final_result, "objects": objects, 
          "question_sentence": question_sentence,
          "question_definition": question_definition,
          "question_type": ctxt["question_type"],
          "logic_sentence_map": ctxt["logic_sentence_map"]}


def make_logic_list_sentence_map(ctxt,logic_list,sentencename):
  res=[]
  for logic in logic_list:
    mapped=make_logic_sentence_map(ctxt,logic,sentencename)
    res.append(mapped)
  return res
    

def make_logic_sentence_map(ctxt,logic,sentencename):
  if not logic: return logic
  if not (options["prover_explain_flag"] or options["show_logic_flag"]): return logic
  #debug_print("make_logic_sentence_map logic",logic) 
  if type(logic)==dict: 
    logic["@name"]=sentencename
  elif False: # logic[0]=="and":
    res=[]
    for el in logic[1:]:
      tmp={"@name": sentencename, "@logic": el}  
      res.append(tmp)
    logic=res
  else: 
    logic={"@name": sentencename, "@logic": logic}
  return logic


def fix_punctuation(ctxt,doc):
  debug_print("fix_punctuation doc",doc)
  if not doc: return doc
  if type(doc)!=list: return doc
  for word in doc:
    #debug_print("fix_ner word",word)
    if ((not ("ner" in word)) or (word["ner"] in [0,"0","O"])):
      children=get_children(doc,word)
      for child in children:
        #debug_print("fix_ner child",child)
        if ((child["deprel"] in ["flat"]) and
            ("ner" in child) and not (child["ner"] in [0,"0","O"])):
          nerval=child["ner"]
          v=nerval.replace("S-","S-")
          v=v.replace("B-","S-")
          word["ner"]=v          
          word["old_upos"]=word["upos"]
          word["upos"]="PROPN"
          break 
  return doc  

def fix_ner(ctxt,doc):
  #debug_print("fix_ner doc",doc)
  if not doc: return doc
  if type(doc)!=list: return doc
  for word in doc:
    #debug_print("fix_ner word",word)
    if ((not ("ner" in word)) or (word["ner"] in [0,"0","O"])):
      children=get_children(doc,word)
      for child in children:
        #debug_print("fix_ner child",child)
        if ((child["deprel"] in ["flat"]) and
            ("ner" in child) and not (child["ner"] in [0,"0","O"])):
          nerval=child["ner"]
          v=nerval.replace("S-","S-")
          v=v.replace("B-","S-")
          word["ner"]=v          
          word["old_upos"]=word["upos"]
          word["upos"]="PROPN"
          break 
  return doc  

def fix_lemma_capitalization(ctxt,doc):
  #debug_print("fix_lemma_capitalization doc",doc)
  if not doc: return doc
  if type(doc)!=list: return doc
  for word in doc:
    if word["lemma"] and not(word["upos"] in ["PROPN"]) and word["lemma"][0].isupper():
      word["lemma"]=word["lemma"].lower()
    if (word["lemma"] and word["upos"] in ["PROPN"] and 
        "ner" in word and (word["ner"] in ["S-NORP"] or word["ner"] in ["NORP"]) and
        word["ner"][0].isupper()):
      word["lemma"]=word["lemma"].lower()  
  #debug_print("fix_lemma_capitalization result doc",doc) 
  return doc

def fix_capital_propn(ctxt,doc,entities):
  #debug_print("fix_capital_propn doc",doc)
  if not doc: return doc
  if type(doc)!=list: return doc
  for word in doc:
    #debug_print("word",word)
    if (word["id"]==1 and word["upos"] in ["PROPN"] and word["lemma"][0].isupper() and
        #"ner" in word and word["ner"] in [0,"0","O"]):
        "ner" in word and word["ner"] in [0,"0"]):
      word["upos"]="NOUN"   
    elif (word["id"]==1 and word["upos"] in ["NOUN"] and word["text"][0].isupper() and
          word_has_feat(word,"Number","Plur") and word["lemma"][-1]=="s" and
          "ner" in word and word["ner"] in [0,"0","O"]):
      # Muggles cannot disappear
      for entity in entities:
        if word["text"]==entity["text"] or word["text"]==entity["text"]+"s":
          word["lemma"]=entity["text"].lower()
          break
  #debug_print("fix_capital_propn result doc",doc) 
  return doc



def is_simple_clause(term):
  #debug_print("is_simple_clause term",term)
  if not term: return False
  if type(term)!=list: return False
  if is_atom(term): return True
  if term[0]!="and": return False  
  for el in term[1:]:
    if not is_atom(el): return False
  return True

def is_atom(term):
  if not term: return False
  if type(term)!=list: return False
  for el in term:
    if el in logic_ops: 
      return False
  return True

# Datastructs below:
#
#  logic: implicitly anded list of logical statements
#  objects: list of triples of form [parse_result_of_source_word, constant_or_var_str, implicit_anded_list_of_statements_about_object]


# parse_sentence is the top processing function for one sentence
#
# parse one sentence and return the {"logic":..,"objects":...} dict
# where objects are new objects/constants built during sentence parsing
#
# parameters:
#  ctxt: {"logic":logic_so_far,"objects": objects_so_far}
#  sentence: ud tree of sentence
#  question_dummmy_name: global dummy name str a la "Dummyname" (not needed param?)
#
# return:
#    {"logic": new_logic_for_sentence,"objects": new_object_for_sentence}
#

def parse_sentence(ctxt,sentence,question_dummy_name=None): 
  debug_print("====== sentence ==========\n")  
  #debug_print("passed_words",ctxt["passed_words"])
  #debug_print_sentence_tree(sentence)
  #if options["debug_print_flag"] or options["show_logic_flag"]:
  #  if options["debug_print_flag"]:
  #    debug_print("sentence",sentence)
  #    debug_print("text",doc_to_original_sentence(sentence)+"\n")
  #  else:  
  #    print(doc_to_original_sentence(sentence))
  #debug_print("sentence",sentence)
  #debug_print("text",doc_to_original_sentence(sentence)+"\n")
  #debug_print("parse_sentence",sentence)
  #debug_print("")

  # First fix the PROPN issue for the first (capitalized) word
  min_id=10000000
  first_word=None
  for word in sentence: 
    if word["id"]<min_id:
      min_id=word["id"]
      first_word=word
  
  if (first_word and first_word["upos"] in ["PROPN","NOUN"] and 
      not first_word["text"].startswith(dummy_name) and
      (not is_question_sentence(sentence) or first_word["lemma"] not in question_words) and
      first_word["ner"] in ["O","0",0] and
      first_word["text"][0].isupper()):
    if (not(first_word["text"] in first_names) and 
        (not(len(first_word["text"])>2 and first_word["text"][-2:]=="'s"))):  
      first_word["upos"]="NOUN"
      first_word["lemma"]=first_word["lemma"][0].lower()+first_word["lemma"][1:]
    else:
      first_word["lemma"]=first_word["lemma"][0].upper()+first_word["lemma"][1:]  

  #debug_print_sentence_tree(sentence)
  # Fix PROPN for first names
  for word in sentence: 
    #debug_print("word",word)
    if word["upos"] in ["NOUN","PROPN"] and word["text"][0].isupper() and word["ner"] in ["O","0",0]:
      if word["text"] in first_names:
        word["upos"]="PROPN" 
        word["ner"]="S-PERSON"   

  debug_print_sentence_tree(sentence)
  root=get_root(sentence)           

  subsentence_logic_tree=build_subsentence_logic(ctxt,sentence,root)
  debug_print("subsentence_logic_tree") #,True,subsentence_logic_tree)
  debug_print_logical_sentence_tree(subsentence_logic_tree)
  subsentence_root_list=build_subsentence_root_list(ctxt,subsentence_logic_tree)
  
  object_logic_tree=build_subsentence_object_logic(ctxt,sentence,root,subsentence_logic_tree,subsentence_root_list)
  debug_print("object_logic_tree")#,object_logic_tree)
  debug_print_logical_sentence_tree(object_logic_tree)
  
  property_logic_tree=build_subsentence_property_logic(ctxt,sentence,root,object_logic_tree,subsentence_root_list)
  debug_print("property_logic_tree")#,property_logic_tree)
  debug_print_logical_sentence_tree(property_logic_tree)

  flat_logic_tree=flatten_object_logic(ctxt,property_logic_tree)
  debug_print("flat_logic_tree")#,flat_logic_tree)
  debug_print_logical_sentence_tree(flat_logic_tree)
  
  flat_props_tree=flat_logic_tree
  debug_print("flat_props_tree")#,flat_props_tree)
  debug_print_logical_sentence_tree(flat_props_tree)
  
  #if "passed_words" not in ctxt:
  #  ctxt["passed_words"]=[]
  ctxt["passed_words"]=[]

  sentence_proper_logic_tree=build_sentence_proper_logic(ctxt,sentence,flat_props_tree)

  if (sentence_proper_logic_tree and type(sentence_proper_logic_tree)==list 
      and sentence_proper_logic_tree[0]=="logic"):
    proper_logic_tree=sentence_proper_logic_tree[2]
  else:
    proper_logic_tree=sentence_proper_logic_tree  
  
  debug_print("main logic created:\n")
  debug_print_logic(proper_logic_tree)
  if options["debug_print_flag"]:
    print("\n")   
    show_objects(ctxt)
  #debug_print("logic",make_classic_clause_str(proper_logic_tree))
  debug_print("")
 
  res={}  
  if proper_logic_tree:
    res["logic"]=proper_logic_tree

  return res


def make_object_constant_logic_list(ctxt,sentence,object):
  #debug_print("make_object_constant_logic",object)
  word=object[1]
  constant=object[0]

  logic=object[2]
  if type(logic)==list and logic[0]=="and":
    logiclist=logic[1:]
  else:
    logiclist=[logic]   
  result=[]     
  for el in logiclist:
    #debug_print("el",el)
    if type(el)==list and el[0] in ["has_name"]:
      result=[el]
    elif type(el)==list and el[0]==dummypredicate:
      continue
    elif el:
      if type(constant)==str and dummy_name in constant:
        result=[el]
      else:
        result=[]    
    else:
      namefact=["has_name",word["lemma"],constant]
      result=[namefact]

  if "ner" in word:
    nervalue=word["ner"]
    if nervalue and not (nervalue in [0,"0","O"]): # (nervalue.startswith("S-") or nervalue.startswith("B-") or nervalue.startswith("X-")):
      #debug_print("cp1 nervalue",[nervalue,type(nervalue),nervalue=="O",nervalue=="0"])
      # S: John, B: John Smith, X: Mr Smith
      typestr=nervalue[2:]
      typemap={"PERSON":"person","GPE":"place"}
      if typestr in typemap:       
        nerfact=[["isa",typemap[typestr],constant],["$block",0,["$not",["isa",typemap[typestr],constant]]]]  
        fact=["isa","object",constant]
        if typestr=="PERSON" and word["text"] in person_names:
          nerlogic={"@logic":nerfact}
        else:  
          nerlogic={"@logic":nerfact,"@confidence":0.9}        
        result.append(nerlogic) 
      else:
        fact=["isa","object",constant]
    else:
      fact=["isa","object",constant]      
  else:
    fact=["isa","object",constant]
  
  objfact=["isa","object",constant]     
  result.append(objfact)
  #debug_print("make_object_constant_logic result",result)       
  return result

def make_populated_logic_list(ctxt,sentence,logic,positive=True):
  #debug_print("make_populated_logic_list",logic)
  if not logic: return logic
  if type(logic)==dict:
    logic=logic["@logic"]
  if type(logic)!=list: return []  
  if logic[0] in ["isa"] and not positive:
    if is_var(logic[2]):
      atoms=[logic]
      const=make_population_constant(ctxt,atoms)      
      atom=[logic[0],logic[1],const,[confidence_function,1]]           
      thingrule=[["-isa",logic[1],"?:X"],["isa","object","?:X"]]  
      if not is_in_population_list(ctxt,atom):        
        ctxt["populated"].append(atom)
      if logic[1]!="object" and not (thingrule in logic) and not (thingrule in ctxt["populated"]):        
        ctxt["populated"].append(thingrule)  
  elif logic[0] in ["forall","exists"] and len(logic)==3:
    make_populated_logic_list(ctxt,sentence,logic[2],positive)
  elif logic[0] in ["and","or"]:
    for el in logic[1:]: 
      make_populated_logic_list(ctxt,sentence,el,positive)
    if logic[0] in ["and"] and not positive:
      #debug_print("populate logic",logic)
      atoms=[]
      var=None
      for el in logic[1:]:
        if type(el)==list and el[0] in ["prop","-prop","isa"]:
          arg2=el[2] 
          if is_var(arg2):
            if not var: 
              var=arg2              
              atoms.append(el)
            elif var==arg2:            
              atoms.append(el)  
        elif (type(el)==list and el[0] in ["rel2","-rel2"] and 
              el[1] in is_location_relations and
              type(el[3])==str and not(is_var(el[3]))):
          arg2=el[2] 
          if is_var(arg2):
            if not var: 
              var=arg2              
              atoms.append(el)
            elif var==arg2:            
              atoms.append(el)      
      if atoms:
        #debug_print("atoms 1",atoms)
        atoms2=[]
        const=make_population_constant(ctxt,atoms)
        for el in atoms:
          if el[0] in ["prop","-prop"]:
            atom=[el[0],el[1],const,default_prop_intensity,default_prop_class]
          elif el[0] in ["rel2","-rel2"]:
            atom=[el[0],el[1],const]+el[3:]  
          else:  
            atom=[el[0],el[1],const]
          if not (atom[0] in ["isa","-isa","rel2","-rel2"]) and ctxt["addctxt"]:
            ctxtterm=make_ctxt_argument(ctxt,sentence,None)
            atom.append(ctxtterm)  

          if not is_in_population_list(ctxt,atom):
            ctxt["populated"].append(atom)

  elif len(logic)==3 and logic[1] in ["=>"]: 
    make_populated_logic_list(ctxt,sentence,logic[0],not positive)
    make_populated_logic_list(ctxt,sentence,logic[2],positive)
  elif len(logic)==3 and logic[1] in ["<=>"]:   
    make_populated_logic_list(ctxt,sentence,logic[2],not positive)  
  elif len(logic)==2 and logic[0] in ["not"]: 
    make_populated_logic_list(ctxt,sentence,logic[1],not positive)  
  else:
    for el in logic: 
      if type(el)!=str:
        make_populated_logic_list(ctxt,sentence,el,positive)

def is_in_population_list(ctxt,atom):
  lst=ctxt["populated"]
  for el in lst:
    if el==atom:
      return True
  return False


# transitive verbs require objects "Juan threw the ball."
# intransitive verbs do not require objects "They jumped."
# some intransitive verbs may / or not take an object
#
# Phrasal verbs "Cindy has decided to give up sweets while she diets."

def build_subsentence_logic(ctxt,sentence,root,parentsubj=None,prefer_parentsubj=False):
  #debug_print("build_subsentence_logic root",root)
  #debug_print("build_subsentence_logic parentsubj",parentsubj)
  #debug_print("build_subsentence_logic prefer_parentsubj",prefer_parentsubj)
  children=get_children(sentence,root)   
  subj=None
  verb=None
  obj=None
  op=None
  subsentences=[]
  ops=[]
  oldsubjects=[]
  words=[root]+children
  has_relcl_verb=False
  obl_list=[]
  # run over all words
  for word in words:
    #debug_print("word in loop",word)
    deprel=word["deprel"] 
    upos=word["upos"]
    lemma=word["lemma"]

    if word!=root:
      wordchildren=get_children(sentence,word)  
    else:
      wordchildren=None  

    # -- try to fill op subj verb obj slots --

    if deprel in ["cc"] and upos in ["CCONJ"]:
      op=lemma
    if (deprel in ["nsubj","nsubj:pass"]) and (not subj) and (not (parentsubj and prefer_parentsubj)) :
      if subj:
        oldsubjects.append(subj)
      subj=word    
    elif word==root and (upos in ["VERB"]):
      verb=word     
    elif (deprel in ["obl:agent"]) and not (parentsubj and subj and (not obj) and (subj["upos"] in ["PRON"])):
      # not-condition for eliminating obl:agent Mary in "Bears slept in a forest which was bought by Mary"
      #debug_print("cp11 obj",obj)
      #debug_print("cp11 subj",subj)
      #debug_print("cp11 parentsubj",parentsubj)
      #debug_print("cp11 word",word)
      #debug_print("cp1 subj",subj)
      if (subj or parentsubj) and not obj:
        if ((not subj) and parentsubj):
          # John lives in a red car bought by Mary.  : car in subsentence comes from parent
          #oldsubjects.append(parentsubj)
          obj=parentsubj
          subj=word     
        elif "deprel" in subj and subj["upos"] in ["PRON"] and subj["deprel"]=="nsubj:pass": # 
          #debug_print("cp2 subj",subj)
          pass
        else:  
          #debug_print("cp1 word",word)
          #debug_print("cp1 subj",subj)
          #debug_print("cp1 parentsubj",parentsubj)
          oldsubjects.append(subj) #??
          obj=subj
          subj=word
      else:
        subj=word
    elif deprel in ["nsubj:pass"] and not obj:
      obj=word  
    elif (deprel in ["cop","aux"]) and (lemma in ["be"]):
      #debug_print("root for be",root)
      nmodtmp=nmod_case_child(ctxt,sentence,root,["of"],False)
      if root["upos"] in ["NOUN"] and nmodtmp:
        verb=root               
        root["relation"]="of"
        root["be"]=word
        obj=nmodtmp           
      elif root["upos"] in ["VERB"] and word_has_feat(root,"VerbForm","Part"):
        # The radio is working       
        verb=root               
        root["be"]=word
        #obj=nmodtmp 
      elif root["deprel"] in ["advcl"] and root["upos"] in ["ADP"]:
        # If the switch is on then the lamp is shining.    
        verb=word      
        obj=root  #                
      else:  
        verb=word    
    elif (deprel in ["aux"]) and (lemma in ["have"]): 
      #  Elephants have not red trunks
      verb=word
    elif (not subj) and (deprel in ["xcomp"]) and (upos in ["VERB"]):
      # "John eats cabbage and goes to sleep."
      verb=word
    elif (not verb) and (deprel in ["acl:relcl"]) and (upos in ["VERB"]):      #???
      #"Elephants who are adult eat meat"
      has_relcl_verb=True 
      verb=word  
    elif (not verb) and (deprel in ["acl"]) and (upos in ["VERB"]):      #???
      # The scientist presented in the school ?
      verb=word    
    elif (not verb) and (deprel in ["csubj"]) and (upos in ["VERB"]):     
      # "It is false that John has a trunk"
      verb=word   
    elif word==root and (upos in ["ADJ","NOUN","PROPN","PRON"]):
      obj=word
    elif (deprel in ["obj"] and upos in ["PRON"] and lemma in ["which","what","who","whom"] and
          (not word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP") or
            word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP")["lemma"]!="of")): 
      # John had a car which Eve bought: subsentence "which Eve bought"
      # but not "Whom is Eve afraid of?"
      if parentsubj:
        obj=parentsubj 
      else:
        obj=word      
    elif word==root and (upos in ["ADV"]):
      obj=word     
    elif (deprel in ["obj"] and 
          (not word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP") or 
           not word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP")["lemma"]=="of")):
      #debug_print("cpx")
      obj=word
    elif (not obj) and (deprel in ["parataxis"]) and (upos in ["ADJ","NOUN","PROPN","PRON"]):
      obj=word  
    elif ((not obj) and (deprel in ["mark"]) and (lemma in ["that","which"]) and
          get_previous_word(sentence,word) and 
          get_previous_word(sentence,word)["upos"] in ["NOUN","PROPN"]):
      obj=word  
    elif ((not obj) and (deprel in ["obl"]) and (upos in ["ADJ","NOUN","PROPN"]) and
          (verb==root) and word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP") and
          word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP")["lemma"]!="by" and
          ((verb and verb["lemma"]=="be") or word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP")["lemma"]=="of")):
      # "John walks towards home."
      # "Spoons are made of iron."
      # but not "The authors were supported by the tourist"
      obj=word    
    elif (deprel in ["obl","obl:agent"] or
          (deprel in ["obj"] and word["lemma"] in ["who","whom"] and 
           word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP") and
           word_has_child_in_deprel_upos(ctxt,sentence,word,"case","ADP")["lemma"]=="of")):
      # John eats in Tallinn with a fork
      # Who is Ellen afraid of?
      #debug_print("cpx to obl_list word",word) 
      obl_list.append(word)
    elif (not obj) and (deprel in ["xcomp"]) and (upos in ["VERB"]):
      # "John drives home and he goes to sleep."
      obj=word   
    elif (not obj) and (deprel in ["csubj"]) and (upos in ["NOUN","ADJ"]):     
      # "It is likely that John is an animal and nice"
      obj=word    
    elif (not obj) and (deprel in ["discourse"]) and (upos in ["INTJ"]) and variable_shaped_lemma(lemma):
      # "If x is y, then y is x."
      obj=word   
    elif verb and (not obj) and (deprel in ["ccomp"]) and (upos in ["ADJ","NOUN","PROPN","PRON"]): 
      # "John thought Mike is nice."
      op="reflection"
      obj="DUMMY"
    elif (not obj) and (deprel in ["root"]) and (upos in ["ADP"]):    
       # the switch is on   
      obj=word
    elif obj and (not subj) and (not verb) and (deprel in ["acl:relcl"]) and upos in ["ADJ"]:
      # "Nice bears who are big are strong"
      maybeobj=True
      oldobj=obj
      for el in wordchildren:
        if el["deprel"] in ["nsubj"]:
          maybeobj=False
          break
        if el["deprel"] in ["cop"] and el["upos"] in ["AUX"] and el["lemma"] in ["be"]:
          subj=obj
          obj=word
          verb=el
          break
      if not maybeobj:
        obj=oldobj
        verb=None
    elif ((deprel in ["case"]) and obj and parentsubj and not verb and not subj
          and obj["lemma"] not in ["percent"] and 
              obj["lemma"] not in probability_words): # TODO
      # "John is in a box at the red house. A box is at the house?" here in is case
      # but not "An apple was bad and she was in a room.
      #debug_print("case found for word",word)
      #debug_print("case found for obj",obj)
      #debug_print("case found for verb",verb)
      #debug_print("case found for subj",subj)
      #debug_print("case found for parentsubj",parentsubj)
      objparent=get_parent(sentence,obj)
      if objparent: 
        parentchildren=get_children(sentence,objparent)
      else:
        parentchildren=[]
      feats='Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin'  
      for el in parentchildren:
        if el["deprel"] in ["cop"] and el["lemma"] in ["be"]:
          feats=el["feats"]
          break
      subj=parentsubj
      verb={'id': 100000, 'text': 'is', 'lemma': 'be', 'upos': 'AUX', 'xpos': 'VBZ', 
        'feats': feats, 
        'head': 100000, 'deprel': 'cop', 'start_char': 100000, 'end_char': 100000, 
        'ner': 'O', 'sentence_nr': root["sentence_nr"], 'relation': word["lemma"]}

    # - - - try to find a subsentence

    word_subsentence=False
    if ((deprel in ["conj","advcl","parataxis"] or
         (deprel in ["discourse"] and variable_shaped_lemma(lemma))) and 
         wordchildren):   
      if deprel in ["conj"] and parentsubj:        
        # "A car bought by Mike and painted by Eve is nice."
        subsentence=build_subsentence_logic(ctxt,sentence,word,parentsubj,True)
      else:
        subsentence=build_subsentence_logic(ctxt,sentence,word,subj)  
      if subsentence:
        #debug_print("subs try2 subsentence",subsentence) 
        word_subsentence=True
        subsentences.append(subsentence)
        # find a logical op for combining subsentence ---
        oldop=op        
        op=get_op_from_subsentence(ctxt,sentence,wordchildren)
        if not op: op=oldop
        ops.append(op)      
    elif (deprel in ["acl:relcl"] and (upos in ["VERB"]) and has_relcl_verb): 
      #debug_print("CPX 2")             
      subsentence=build_subsentence_logic(ctxt,sentence,word,obj,True)      
      if subsentence:
        subsentence_copy=[subsentence[0],subsentence[1].copy()]
        word_subsentence=True
        if (len(subsentence[1])>3 and subsentence[1][2] and subsentence[1][3] and 
            subsentence[1][3]["upos"] in ["PRON"]):          
          # "The tourists who the lawyer helped encouraged the judges" : the first part of sentence
          verbchildren=get_children(sentence,subsentence[1][2])
          for el in verbchildren:
            if el["deprel"] in ["nsubj"] and el["upos"] in ["NOUN"]:
              # reverse subj and obj, new el becomes subj
              subsentence[1][3]=subsentence[1][1]
              subsentence[1][1]=el
              break
            elif el["deprel"] in ["obj"] and el["upos"] in ["NOUN"]:             
              subsentence[1][3]=el             
              break
        subsentences.append(subsentence)
        # find a logical op for combining subsentence ---
        oldop=op        
        op=get_op_from_subsentence(ctxt,sentence,wordchildren)
        if not op: op=oldop
        ops.append(op)    
      # try to make another sentence: the second part of 
      # "The tourists who the lawyer helped encouraged the judges"
      if subsentence_copy:
        if (len(subsentence_copy[1])>3 and subsentence_copy[1][2] and subsentence_copy[1][3] and 
            subsentence_copy[1][3]["upos"] in ["PRON"]):
          found=False
          verbchildren=get_children(sentence,subsentence[1][2])
          for el in verbchildren:
            #debug_print("cpx2 el",el)
            if el["deprel"] in ["ccomp","xcomp"] and el["upos"] in ["VERB"]:
              # The judges who the tourist stopped thanked the banker # second part
              # new el becomes verb
              subsentence_copy[1][0]=el # ??
              subsentence_copy[1][2]=el 
              elchildren=get_children(sentence,el)
              
              if elchildren:
                for elchild in elchildren:
                  if elchild["deprel"] in ["obj"] and elchild["upos"] in ["NOUN"]:                    
                    # new elchild becomes obj 
                    subsentence_copy[1][3]=elchild
                    found=True                   
            if not found:
              # The judges who the tourist stopped thanked the banker # first part
              elchildren=get_children(sentence,word)                 
              if elchildren:
                for elchild in elchildren:
                  if elchild["deprel"] in ["nsubj"] and elchild["upos"] in ["NOUN"]:
                    # reverse subj and obj, new el becomes subj, verb changed to word
                    subsentence_copy[1][3]=subsentence_copy[1][1]
                    subsentence_copy[1][2]=word
                    subsentence_copy[1][1]=elchild
                    break                                    
          if (subsentence_copy and len(subsentence_copy[1])>3 and subsentence_copy[1][1] and 
              subsentence_copy[1][2] and subsentence_copy[1][3]):  
            subsentences.append(subsentence_copy)
            # find a logical op for combining subsentence ---
            oldop=op        
            op=get_op_from_subsentence(ctxt,sentence,verbchildren)
            if not op: op=oldop
            ops.append(op)    
    
    elif (deprel in ["ccomp"]) and wordchildren:
      # "John thought Mike is nice."
      subsentence=build_subsentence_logic(ctxt,sentence,word,subj)
      if subsentence:
        word_subsentence=True
        subsentences.append(subsentence)
        ops.append(None)

    # - - - - alternatively construct a subsentence 
    
    if ( ((not word_subsentence) and (deprel in ["conj"]) and (upos in ["VERB"]) and
          verb==root and wordchildren) or
        
         ((not subj) and (deprel in ["csubj"]) and (upos in ["NOUN","ADJ","VERB"]) and
          wordchildren) or 

         ((not word_subsentence) and (deprel in ["csubj"]) and (upos in ["NOUN"]) and
          wordchildren)):
      # "John awakes and drives."
      # "It is false that John is an animal and it is true that John is nice"
      # "It is likely that John is an animal and nice"
           
      subsentence=build_subsentence_logic(ctxt,sentence,word,subj)
      if subsentence:
        thisop=get_op_from_subsentence(ctxt,sentence,wordchildren)
        if (not thisop) and (deprel in ["csubj"]):
          parent=get_parent(sentence,word)
          parentchildren=get_children(sentence,parent)
          thisop=get_op_from_subsentence(ctxt,sentence,parentchildren)
        word_subsentence=True
        subsentences.append(subsentence)
        ops.append(thisop)
      else:  
        thisop=get_op_from_subsentence(ctxt,sentence,wordchildren)
        if thisop and subj:
          oldop=op
          op=thisop
          ops.append(op)
          subsentence=["sv",[root,subj,word]]
          subsentences.append(subsentence)     

  #debug_print("cp0 subj verb obj",[subj,verb,obj])  
  #debug_print("cp0 word",word)
  #debug_print("cp0 subsentences",subsentences)
  #debug_print("cp0 oldsubjects",oldsubjects)
  #debug_print("cp0 obl_list",obl_list)

  # - - - - - use old subjects for building additional sentences - - - - 

  if subj and verb and obj and oldsubjects:
    for oldsubject in oldsubjects:
      ops.append("and")
      subsentence=["svo",[verb,oldsubject,verb,obj]] 
      subsentences.append(subsentence)
  elif subj and verb and oldsubjects:
    for oldsubject in oldsubjects:
      ops.append("and")
      subsentence=["sv",[verb,oldsubject,verb]]
      subsentences.append(subsentence)    

  #debug_print("cp0a subsentences",subsentences)

  # - - - - parts / subsentences have been collected, construct logic
  
  if (not subj) and parentsubj and verb and verb["deprel"]!="acl": # and has_xcomp:
    # "John eats cabbage and goes to sleep."
    # but not (!=acl) for "The scientist presented in the school stopped the artists. 
    # use parent subject as subject
    subj=parentsubj  
  elif  ((not obj) and parentsubj and verb and verb["deprel"]!="acl" and
         word["deprel"] in ["obj"]): # and has_xcomp:     
    # use parent "subject" as object
    obj=parentsubj  
  elif ((not obj) and (not subj) and parentsubj and verb and obl_list and len(obl_list)==1 and obl_list[0]["upos"] in ["NOUN","PROPN"]):   
    # use parent "subject" as object
    #"Mike ate berries in the forest bought by Mary. Mike ate berries in the forest bought by John?"
    obj=parentsubj 
    subj=obl_list[0] 
    obl_list=None
  elif verb and obj and (not subj) and verb!=root and root["upos"] in ["NOUN"]:
    # try to use noun root as a subject or object
    if obj==root:
      subj=obj
      obj=None
    else:
      subj=root
  elif  (subj and verb and
         (not obj) and parentsubj and verb and verb["deprel"]!="acl" and
         not (subj["lemma"] in ["who","that","which","what"]) and        
         ((parentsubj["deprel"] in ["obj"]) or 
          ((parentsubj["deprel"] in ["root"]) and (parentsubj["upos"] in ["NOUN","PROPN"])) )):
    if word_has_child_in_deprel_lemma(ctxt,sentence,verb,["advmod"],["where"]):
      # "Mary bought the forest where the bears ate?"
      obl_list.append(parentsubj)
    else:
      # John had a car Eve bought   
      # John is a man Eve liked
      # use parent "subject" as object
      obj=parentsubj      

  """
  elif  (subj and verb and
         (not obj) and parentsubj and verb and verb["deprel"]!="acl" and
         not (subj["lemma"] in ["who","that","which","what"]) and
         word_has_child_in_deprel_lemma(ctxt,sentence,verb,["advmod"],["where"]) and
         ((parentsubj["deprel"] in ["obj"]) or 
          ((parentsubj["deprel"] in ["root"]) and (parentsubj["upos"] in ["NOUN","PROPN"])) )):
    # "Mary bought the forest where the bears ate?"
    obl_list.append(parentsubj)
  elif  (subj and verb and
         (not obj) and parentsubj and verb and verb["deprel"]!="acl" and
         not (subj["lemma"] in ["who","that","which","what"]) and
         not word_has_child_in_deprel_lemma(ctxt,sentence,verb,["advmod"],["where"]) and
         ((parentsubj["deprel"] in ["obj"]) or 
          ((parentsubj["deprel"] in ["root"]) and (parentsubj["upos"] in ["NOUN","PROPN"])) )):
    # John had a car Eve bought   
    # John is a man Eve liked
    # use parent "subject" as object
    obj=parentsubj  
  
  """
    
  #debug_print("cp1 subj verb obj",[subj,verb,obj])  
  #debug_print("cp1 subsentences",subsentences)
  #debug_print("cp1 obl_list",obl_list)

  # -- if subj or obj is a function, find its argument - - - - 

  if subj and subj["upos"] in ["NOUN","PROPN"]:
    argtmp=nmod_case_child(ctxt,sentence,subj,["'s"],True)        
    if argtmp:
      subj["argument"]=argtmp 
      argtmp["preposition"]="'s" 
    #elif verb["lemma"]=="have" and is_measure_subtree(ctxt,obj):
    #  measureword=measure_subtree_measureword(ctxt,obj)
    #  measureword["argument"]=subj
    #  subj=measureword
    #  verb={'id': 100000, 'text': 'is', 'lemma': 'be', 'upos': 'AUX', 'xpos': 'VBZ', 
    #    'feats': 'Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin', 
    #    'head': 100000, 'deprel': 'cop', 'start_char': 100000, 'end_char': 100000, 
    #    'ner': 'O', 'sentence_nr': root["sentence_nr"]} # 'relation': word["lemma"]}
    #
    elif is_measure_subtree(ctxt,sentence,subj):            
      argtmp=is_measure_subtree(ctxt,sentence,subj)
      debug_print("measure subj",subj)
      debug_print("measure measured",argtmp)
      argtmp["deprel"]="nmod:poss"
      subj["argument"]=argtmp
      if argtmp["lemma"][-1]=="'":
        argtmp["lemma"]=argtmp["lemma"][:-1]
        argtmp["preposition"]="'s"
      else:
        argtmp["preposition"]="of" 
    else:
      argtmp=nmod_case_child(ctxt,sentence,subj,["of"],False)    
      if argtmp:
        subj["argument"]=argtmp
        argtmp["preposition"]="of"   
      elif not obj:
        argtmp=obl_case_child(ctxt,sentence,verb,["by"]) 
        #debug_print("cp",argtmp)
        if argtmp:
          # reverse obj and subj
          obj=subj
          subj=argtmp
        elif not obj:
          #"The senator that waited introduced the president ." 
          tmpchild=get_children(sentence,verb)
          if tmpchild:
            for el in tmpchild:
              if el["deprel"] in ["obj"] and el["upos"] in ["NOUN","PROPN"]:
                obj=el
                break
    # - - - if 


  #debug_print("cp2 subj verb obj",[subj,verb,obj])
  """
  debug_print("cp2 subj verb obj",[subj,verb,obj])
  if verb["lemma"] in ["be"] and obj["lemma"] in ["long"]:
    for el in get_children(sentence,obj):
      tmpchild=get_children(sentence,el)
      found=False
      for tmpel in tmpchild:
        if (el["deprel"] in ["obl:tmod"] and el["lemma"] in ["kilometer"] and
            tmpel["deprel"] in ["nummod"]):
          debug_print("found!!")
          found=True
          break
      if found:
        debug_print("found2!!")
  #debug_print("cp2 subsentences",subsentences)
  """

  if obj and obj["upos"] in ["ADJ"]:
    argtmp=obl_case_child(ctxt,sentence,obj,["than"])
    if argtmp: 
      # John is stronger than Mike.
      obj["be"]=verb                             
      obj["relation"]="than"
      verb=root        
      obj=argtmp   
  elif (obj and obj["upos"] in ["NOUN","PROPN"] and
        (obj["deprel"] in ["obl"]) and
        word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP") and
        #word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP")!="by"
        word_has_child_in_deprel_lemma(ctxt,sentence,root,"aux:pass",["be"])):
    # John is made of metal.
    # Spoon is made by Mike.
    # but not for "bought" in "John lives in a nice car which was red and was bought by Mary."
    argtmp=word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP") 
    beverb=word_has_child_in_deprel_lemma(ctxt,sentence,root,"aux:pass",["be"])  
    if argtmp and beverb and ((not verb) or (verb["deprel"]!="conj")):      
      verb["be"]=beverb                       
      #verb["relation"]="is_"+argtmp["lemma"]
      verb["relation"]=argtmp["lemma"]
      #debug_print("cp2 subj verb obj",[subj,verb,obj])
      #debug_print("argtmp",argtmp)
      #debug_print("beverb",beverb)
  elif (obj and obj["upos"] in ["NOUN","PROPN"] and
        (obj["deprel"] in ["obl"]) and
        word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP") and
        #word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP")!="by"
        not word_has_child_in_deprel_lemma(ctxt,sentence,root,"aux:pass",["be"]) and
        not parentsubj):    
    # John eats food in Tallinn.
    # John eats food with a fork.
    # parentsubj case:
    #"Mike ate berries in the forest bought by Mary. Mike ate berries in the forest bought by John?"
    #debug_print("cpy")  
    argtmp=word_has_child_in_deprel_upos(ctxt,sentence,obj,"case","ADP") 
    if (argtmp and 
        (not obj["lemma"] in probability_words)): # and 
        #(not word_has_child_in_lemma(ctxt,sentence,oblword,probability_words))):
      thisrelation={"case": argtmp, "obj": obj}
      if "relatedobjects" in verb:
        verb["relatedobjects"]=verb["relatedobjects"]+[thisrelation]
      else:
        verb["relatedobjects"]=[thisrelation]    
      obj=None  
      #debug_print("cp2 subj verb obj",[subj,verb,obj])    
  elif obj and verb and verb["lemma"] in ["be"]:
    casetmp=case_child(ctxt,sentence,obj)
    if casetmp:     
      verb["relation"]=casetmp["lemma"]
  if (subj and verb and (not obj) and
      (verb["lemma"] in ["be"])):
     nmodtmp=nmod_case_child(ctxt,sentence,subj,["in"],False)  
     if subj["upos"] in ["NOUN"] and nmodtmp:       
      verb["relation"]="in" 
      obj=nmodtmp 

  if obj and obj["upos"] in ["NOUN","PROPN"]:
    argtmp=nmod_case_child(ctxt,sentence,obj,["'s"],True)        
    if argtmp:
      obj["argument"]=argtmp 
      argtmp["preposition"]="'s" 
    else:
      argtmp=nmod_case_child(ctxt,sentence,obj,["of"],False)    
      if argtmp:
        obj["argument"]=argtmp
        argtmp["preposition"]="of"   
      elif not obj:
        argtmp=obl_case_child(ctxt,sentence,verb,["by"]) 
        if argtmp:
          #debug_print("CPreverse")
          # reverse obj and obj
          obj=obj
          obj=argtmp
        elif not obj:
          #"The senator that waited introduced the president ." 
          tmpchild=get_children(sentence,verb)
          if tmpchild:
            for el in tmpchild:
              if el["deprel"] in ["obj"] and el["upos"] in ["NOUN","PROPN"]:
                obj=el
                break
    
  # - - - build result - - - -
  
  if verb and subj and obl_list:
    for oblword in obl_list:
      argtmp=word_has_child_in_deprel_upos(ctxt,sentence,oblword,"case","ADP") ## should be word_has_child_in_deprel_upos(ctxt,sentence,oblword,["case"],["ADP"])  ??
      # "John eats in Tallinn with a fork."
      argtmp2=word_has_child_in_deprel_lemma(ctxt,sentence,verb,["advmod"],["where"])
      # "Mike saw the forest where the bears ate?"  
      if word_has_child_in_lemma(ctxt,sentence,oblword,probability_words): continue
      if argtmp:
        thisrelation={"case": argtmp, "obj": oblword}
        if "relatedobjects" in verb:
          verb["relatedobjects"]=verb["relatedobjects"]+[thisrelation]
        else:
          verb["relatedobjects"]=[thisrelation] 
      if argtmp2:
        thisrelation={"case": argtmp2, "obj": oblword}
        if "relatedobjects" in verb:
          verb["relatedobjects"]=verb["relatedobjects"]+[thisrelation]
        else:
          verb["relatedobjects"]=[thisrelation]    

  """
  if verb and subj and obl_list:
    for oblword in obl_list:
      argtmp=word_has_child_in_deprel_upos(ctxt,sentence,oblword,"case","ADP") ## should be word_has_child_in_deprel_upos(ctxt,sentence,oblword,["case"],["ADP"])  ??
      # "John eats in Tallinn with a fork."
      if argtmp and not word_has_child_in_lemma(ctxt,sentence,oblword,probability_words):
        thisrelation={"case": argtmp, "obj": oblword}
        if "relatedobjects" in verb:
          verb["relatedobjects"]=verb["relatedobjects"]+[thisrelation]
        else:
          verb["relatedobjects"]=[thisrelation]    
  if verb and subj and obl_list:
    for oblword in obl_list:   
      argtmp=word_has_child_in_deprel_lemma(ctxt,sentence,verb,["advmod"],["where"]) 
      # "Mike saw the forest where the bears ate?"  
      if argtmp and not word_has_child_in_lemma(ctxt,sentence,oblword,probability_words):        
        thisrelation={"case": argtmp, "obj": oblword}
        if "relatedobjects" in verb:
          verb["relatedobjects"]=verb["relatedobjects"]+[thisrelation]
        else:
          verb["relatedobjects"]=[thisrelation]     
  """

  #debug_print("cp3 subj verb obj",[subj,verb,obj]) 
  #debug_print("subsentences",subsentences)

  if (verb and subj and (not obj) and 
       (subj["deprel"]=="nsubj:pass" or 
        subj==parentsubj and word_has_feat(verb,"VerbForm","Part") and word_has_feat(verb,"Tense","Past"))) :
    # Clinton was defeated"
    # Clinton was nice and defeated"
    if "relatedobjects" not in verb or not verb["relatedobjects"]:
      obj=subj
      subj={"id": 0, "head": 0, "upos": "", "deprel": "", "lemma": unknownsubject, "text": "something"}

  if verb and subj: # and obj:
    if obj:
      mainsentence=["svo",[root,subj,verb,obj]]
    else:
      mainsentence=["sv",[root,subj,verb]] 

    if subsentences and op:
      if op in ["if","unless","because"]:
        res=[op,subsentences[0],mainsentence] 
      elif op in ["reflection"]:
        res=["ref",[root,subj,verb,subsentences[0]]]
      elif op in ["ignore"]:
        res=mainsentence
      elif ops and len(ops)>1 and len(ops)==len(subsentences):
        tmp=mainsentence
        i=0
        while i<len(subsentences):
          if not ops[i]: opi=op
          else: opi=ops[i]
          tmp=[opi,tmp,subsentences[i]]
          i+=1
        res=tmp           
      else:  
        res=[op,mainsentence]+subsentences
        res=compact_subsentences(res)
    elif subsentences and not op:            
      res=["and",mainsentence]+subsentences
      res=compact_subsentences(res)
    else:
      res=mainsentence
  elif subsentences:
    if ops and len(ops)>1 and len(ops)==len(subsentences):
        tmp=subsentences[0]
        i=1
        while i<len(subsentences):
          if not ops[i]: opi=op
          else: opi=ops[i]
          tmp=[opi,tmp,subsentences[i]]
          i+=1
        res=tmp
        res=compact_subsentences(res)
    else:    
      res=subsentences[0]    
  else:
    # not (verb and subj)
    res=None
  
  if res and len(res)>2 and (not res[0]) and type(res[1])==list and res[1][0] in ["svo","sv"]:
    res=["and"]+res[1:]

  #debug_print("build_subsentence_logic calced res",res)
  return res

def is_measure_subtree(ctxt,sentence,word):
  if not word: return False
  if word["lemma"] not in measure_words: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:
    if (child["deprel"] in ["compound"] and child["upos"] in ["NOUN","PROPN"] and
        child["lemma"][-1]=="'"):
      return child
    if (child["deprel"] in ["nmod:poss"] and child["upos"] in ["NOUN","PROPN"] and
        word_has_child_in_deprel_lemma(ctxt,sentence,word,["case"],["'"])):
      return child  
  return False    

def compact_subsentences(subsentences):
  if not subsentences: return subsentences
  if subsentences[0] not in ["and","or"]: return subsentences
  lst=subsentences[1:]
  res=[]
  for i in range(0,len(lst)):
    el1=lst[i]
    found=False
    for j in range(i+1,len(lst)):
      el2=lst[j]
      if el1[0]==el2[0] and el1[1][1:]==el2[1][1:]:
        found=True
        break
    if not found: res.append(el1)
  if len(res)>1: return [subsentences[0]]+res
  else: return res[0]  
  return res    

# find a logical op for combining subsentence 

def get_op_from_subsentence(ctxt,sentence,wordchildren):
  #debug_print("get_op_from_subsentence",wordchildren)
  op=None
  for subword in wordchildren:
    #debug_print("subword",subword)
    if ((subword["deprel"] in ["cc"]) and 
        (subword["upos"] in ["CCONJ"])):
      if subword["lemma"] in ["and","or"]:
        op=subword["lemma"]            
    elif ((subword["deprel"] in ["mark"]) and 
          (subword["upos"] in ["SCONJ"])):
      if subword["lemma"] in ["if","unless","because"]:
        op=subword["lemma"]
      elif subword["lemma"] in ["since","before","while"]:
        op="and"  
      elif subword["lemma"] in ["whether"]:
        op="ignore"           
      #debug_print("get_op_from_subsentence op1",op)  
      subwordwordchildren=get_children(sentence,subword) 
      tmp=list_contains_keyval(subwordwordchildren,"deprel","case")  
      if op in ["because"]:
        op="and"
      elif (subwordwordchildren and tmp and
          (tmp["upos"] in ["ADP"]) and (tmp["lemma"] in ["unless"])):
        op=tmp["lemma"]               
    elif ((subword["deprel"] in ["mark"]) and 
          (subword["upos"] in ["ADP"]) and
          subword["lemma"] in ["in"]):
      if subword["lemma"] in ["in"]:
        subwordwordchildren=get_children(sentence,subword) 
        tmp=list_contains_keyval(subwordwordchildren,"deprel","fixed")  
        if (subwordwordchildren and tmp and
            (tmp["upos"] in ["NOUN"]) and (tmp["lemma"] in ["case"])):
          op="if"       
    elif ((subword["deprel"] in ["advmod"]) and 
          (subword["upos"] in ["ADV"])):
      #debug_print("subword",subword)        
      if subword["lemma"] in ["thus","therefore","hence"]:
        op="therefore"  

    elif ((subword["deprel"] in ["nsubj"]) and 
          (subword["upos"] in ["NOUN"])):    
      subwordwordchildren=get_children(sentence,subword) 
      tmp=list_contains_keyval(subwordwordchildren,"deprel","cc")  
      if (subwordwordchildren and tmp and
          (tmp["upos"] in ["CCONJ"]) and (tmp["lemma"] in ["and","or","nor"])):          
        op=tmp["lemma"]    
  #debug_print("get_op_from_subsentence op",op)
  return op

def nmod_case_child(ctxt,sentence,word,nmodlemmas,ispossessive=False):
  children=get_children(sentence,word)
  if not children: return None
  if ispossessive: 
    okrel=["nmod:poss"]
  else:
    okrel=["nmod"]  
  #debug_print("nmod_case_child children",children)  
  #debug_print("nmod_case_child okrel",okrel)
  for child in children:
    if child["deprel"] in okrel:
      subchildren=get_children(sentence,child)
      for subchild in subchildren:
        if (subchild["deprel"] in ["case"]):
          if ispossessive: 
            if subchild["lemma"] in nmodlemmas: #["'s"]:
              return child
          elif subchild["lemma"] in nmodlemmas: #["of"]
            return child
  return None      

def obl_case_child(ctxt,sentence,word,okcases):
  children=get_children(sentence,word)
  if not children: return None  
  okrel=["obl"]  
  for child in children:
    if child["deprel"] in okrel:
      subchildren=get_children(sentence,child)
      for subchild in subchildren:
        if (subchild["deprel"] in ["case"]):                     
          if subchild["lemma"] in okcases:
            return child         
  return None    

def case_child(ctxt,sentence,word):
  children=get_children(sentence,word)
  if not children: return None    
  for child in children:
    if child["deprel"] in ["case"]:
      return child          
  return None       

def build_subsentence_root_list(ctxt,tree,lst=[]):
  if not tree: return 
  #print(tree)
  if tree[0] in ["svo","sv"]:   
    thisroot=tree[1][0]    
    return lst+[thisroot]
  elif tree[0] in ["ref"]:
    thisroot=tree[1][0]  
    lst=lst+[thisroot]
    ref=tree[1][1:]
    res=build_subsentence_root_list(ctxt,ref[2],lst)
    return res
  else:
    res=lst    
    for el in tree[1:]:
      res=build_subsentence_root_list(ctxt,el,res)
    return res  

# Build an extended logical sentence tree from a simpler logical sentence tree:
# replace complex objects (John and Mike, animals or plants, ...) with a
# a logical representation of a complex object. 
#
# This is done for both the subject and the object.
#
# Single objects remain unchanged


def build_subsentence_object_logic(ctxt,sentence,root,tree,rootlist):
  if not tree: return None  
  #debug_print("build_subsentence_object_logic tree",tree)
  #debug_print("build_subsentence_object_logic rootlist",rootlist)
  op=tree[0]
  if type(tree)==str:
    res=tree
  elif type(tree)==dict:
    res=tree
  elif op in ["svo"]:
    thisroot=tree[1][0]
    svo=tree[1][1:]
    subjlogic=build_object_logic(ctxt,sentence,tree,svo[0],rootlist,True)
    verb=svo[1]
    objlogic=build_object_logic(ctxt,sentence,tree,svo[2],rootlist,False)
    res=[op,[thisroot, subjlogic, verb, objlogic]]
  elif op in ["sv"]:
    thisroot=tree[1][0]
    sv=tree[1][1:]
    subjlogic=build_object_logic(ctxt,sentence,tree,sv[0],rootlist,True)
    verb=sv[1]   
    res=[op,[thisroot, subjlogic, verb]] 
  elif op in ["ref"]:
    ref=tree[1][1:]   
    subroot=tree[1][0]
    subj=tree[1][1]
    act=tree[1][2]
    subtree=tree[1][3]        
    newtree=build_subsentence_object_logic(ctxt,sentence,root,subtree,rootlist)
    res=[op,[subroot,subj,act,newtree]]   
  else:
    res=[op]    
    for el in tree[1:]:
      newtree=build_subsentence_object_logic(ctxt,sentence,root,el,rootlist)
      res.append(newtree)      
  return res

# Takes a word used as object, detects if it has and/or additional object words attached
# (John and Mike, animals or plants, ...) and if yes, builds a logical
# tree from these words

def build_object_logic(ctxt,sentence,tree,objectword,rootlist,issubject=False):
  if not objectword: return objectword
  children=get_children(sentence,objectword)
  attachedwords=[]
  ops=[]
  oppos=0
  opreplaceposes=[]
  lastop=None

  if issubject:
    allowed_upos=["NOUN","PROPN"]
  else:
    allowed_upos=["NOUN","PROPN","ADJ"]   

  for word in children:    
    if word in rootlist:
      continue
    deprel=word["deprel"] 
    upos=word["upos"]
    lemma=word["lemma"]
    op=None

    subobject=None
    if deprel in ["conj"] and upos in allowed_upos: #,"ADJ"]:
      # check if has child like cc: and [id:2 text:and upos:CCONJ xpos:CC]
      wordchildren=get_children(sentence,word)
      if wordchildren:
        for wordchild in wordchildren:
          if (wordchild["deprel"] in ["cc"]) and (wordchild["upos"] in ["CCONJ"]):
            op=wordchild["lemma"]
            lastop=op
          elif (wordchild["deprel"] in ["punct"]) and (wordchild["lemma"] in [","]):
            op="and" # ??
            opreplaceposes.append(oppos)
        subobject=build_object_logic(ctxt,sentence,tree,word,rootlist,issubject)    
    if not op:
      continue
    # - - detected a logically connected object word - - 
    ops.append(op)
    oppos+=1
    if subobject:
      attachedwords.append(subobject)
    else:  
      attachedwords.append(word)

  # replace comma-ops for "dogs, cats or rabbits are animals."
  if opreplaceposes and lastop:
    for i in opreplaceposes:
      ops[i]=lastop

  if attachedwords:
    if len(set(ops))==1:
      # all ops are same
      res=[op,objectword]+attachedwords
    else: 
      # different ops
      tmp=objectword
      i=0
      while i<len(attachedwords):
        opi=ops[i]
        tmp=[opi,tmp,attachedwords[i]]
        i+=1
      res=tmp   
    return res
  else:
    # nothing attached
    return objectword  

# Build an extended logical sentence tree from a logical sentence tree 
# where all objects are present
#
# Single objects remain unchanged

def build_subsentence_property_logic(ctxt,sentence,root,tree,rootlist,preferseq=False,isobject=False):
  #debug_print("build_subsentence_property_logic root",root)
  #debug_print("build_subsentence_property_logic tree",tree)
  #debug_print("build_subsentence_property_logic rootlist",rootlist)
  #debug_print("build_subsentence_property_logic preferseq",preferseq)
  if not tree: 
    return None  
  elif type(tree)==str:
    res=tree
    return res
  elif type(tree)==dict:
    # tree is a single word
    # the only real action is here
    if preferseq and tree["upos"]=="ADV": # the tree is an adverb object word      
      # do not add properties to an adverb obj (like in birds are black or white)
      return tree
    else:
      tmpres=build_property_logic(ctxt,sentence,tree,tree,rootlist,preferseq)  
    if "argument" in tree:
      argument=tree["argument"]
      argres=build_property_logic(ctxt,sentence,argument,argument,rootlist,preferseq)        
      argres=["props",argres,argument]
      tree["argprops"]=argres
      #debug_print("argres",argres)
    if tmpres:
      res=["props",tmpres,tree]
      #debug_print("propres",res)
    else:
      res=tree
    res=flatten_props_seq(res)  
    #debug_print("res",res)
    return res

  op=tree[0]
  if op in ["svo"]:
    thisroot=tree[1][0]
    svo=tree[1][1:]
    #subjprefseq=False
    #if 
    subjlogic=build_subsentence_property_logic(ctxt,sentence,tree,svo[0],rootlist,False)
    verb=svo[1]
    verblogic=build_subsentence_property_logic(ctxt,sentence,tree,svo[1],rootlist,True)
    if "relatedobjects" in svo[1]:
      for el in svo[1]["relatedobjects"]:
        #print("el",el)
        relatedobj=el["obj"]        

        if relatedobj and relatedobj["upos"] in ["NOUN","PROPN"]:
          argtmp=nmod_case_child(ctxt,sentence,relatedobj,["'s"],True)        
          if argtmp:
            relatedobj["argument"]=argtmp 
            argtmp["preposition"]="'s" 
          else:
            argtmp=nmod_case_child(ctxt,sentence,relatedobj,["of"],False)    
            if argtmp:
              relatedobj["argument"]=argtmp
              argtmp["preposition"]="of"             

        relatedobjlogic=build_subsentence_property_logic(ctxt,sentence,tree,relatedobj,rootlist,False,False)
        el["proplogic"]=relatedobjlogic

    objlogic=build_subsentence_property_logic(ctxt,sentence,tree,svo[2],rootlist,True,True)
    #debug_print("objlogic",objlogic)
    res=[op,[thisroot, subjlogic, verblogic, objlogic]]
  elif op in ["sv"]:
    thisroot=tree[1][0]
    sv=tree[1][1:]
    subjlogic=build_subsentence_property_logic(ctxt,sentence,tree,sv[0],rootlist,False)
    verb=sv[1]   
    #print("sv op verb",verb)
    if "relatedobjects" in sv[1]:
      for el in sv[1]["relatedobjects"]:
        relatedobj=el["obj"] 

        if relatedobj and relatedobj["upos"] in ["NOUN","PROPN"]:
          argtmp=nmod_case_child(ctxt,sentence,relatedobj,["'s"],True)        
          if argtmp:
            relatedobj["argument"]=argtmp 
            argtmp["preposition"]="'s" 
          else:
            argtmp=nmod_case_child(ctxt,sentence,relatedobj,["of"],False)    
            if argtmp:
              relatedobj["argument"]=argtmp
              argtmp["preposition"]="of"   

        relatedobjlogic=build_subsentence_property_logic(ctxt,sentence,tree,relatedobj,rootlist,False,False)
        el["proplogic"]=relatedobjlogic
    res=[op,[thisroot, subjlogic, verb]] 
  elif op in ["ref"]:
    ref=tree[1][1:]   
    subroot=tree[1][0]
    subj=tree[1][1]
    act=tree[1][2]
    subtree=tree[1][3]        
    newtree=build_subsentence_property_logic(ctxt,sentence,root,subtree,rootlist,preferseq)
    res=[op,[subroot,subj,act,newtree]]   
  else:
    if op in ["or"] and isobject: 
      if "isquestion" in ctxt and ctxt["isquestion"]:
        res=["or"]
      else:
        res=["xor"]  
    else: res=[op]    
    if op in ["and","or","nor"]:
      local_rootlist=object_tree_words(tree)     
      local_rootlist=local_rootlist+rootlist
    else:
      local_rootlist=rootlist  
    for el in tree[1:]:
      newtree=build_subsentence_property_logic(ctxt,sentence,root,el,local_rootlist,preferseq)
      res.append(newtree)      
  return res

def object_tree_words(tree):
  if not tree: return []
  if type(tree)==dict: return [tree]
  else:
    lst=[]
    for el in tree[1:]:   
      tmp=object_tree_words(el)
      lst=lst+tmp
    return lst


def build_property_logic(ctxt,sentence,tree,objectword,rootlist,preferseq=False):
  #debug_print("!!! build_property_logic objectword",objectword)
  #debug_print("!!! build_property_logic tree",tree)
  #debug_print("build_property_logic preferseq",preferseq)
  if not objectword: return objectword  
  children=get_children(sentence,objectword)
  attachedwords=[]
  attachedsentences=[]
  op=None
  detcount=0
  sentsubobjectcount=0
  for word in children:
    if word in rootlist:
      continue
    #debug_print("build_property_logic word",word)
    deprel=word["deprel"] 
    upos=word["upos"]
    lemma=word["lemma"]
    det=None    
    subobject=None
    if (deprel in ["det"]) and (upos in ["DET"]):      
      det=lemma
      detcount+=1
    elif (deprel in ["cc"] and upos in ["CCONJ"] and lemma in ["and","or","nor"]):
      op=lemma 
    elif (deprel in ["amod"]) and (upos in ["ADJ"]) and (word["lemma"] in quantor_confidences):
      None  
    elif ((deprel in ["amod"] and upos in ["ADJ","VERB"]) or
          (deprel in ["advmod"] and upos in ["ADV"] and objectword["upos"]!="VERB" and word_has_feat(word,"Degree","Pos")) or
          # Elephants have long not red trunks.
          (deprel in ["conj"] and upos in ["ADJ"]) or
          (deprel in ["nummod"] and upos in ["NUM"]) or
          (deprel in ["compound"] and upos in ["NOUN"]) ): 
      #debug_print("deprel",deprel)             
      #debug_print("build_property_logic1 objectword",objectword)
      #debug_print("build_property_logic1 word",word)
      if (deprel in ["amod"]) and (upos in ["ADJ"]):
        # check if has child like cc: and [id:2 text:and upos:CCONJ xpos:CC]       
        wordchildren=get_children(sentence,word)
        if wordchildren:
          for wordchild in wordchildren:
            #debug_print("build_property_logic2 wordchild",wordchild)
            #debug_print("build_property_logic2 word",word)
            if (wordchild["deprel"] in ["advmod"] and wordchild["upos"] in ["ADV"] and 
                word["upos"] != "VERB" and
                word_has_feat(wordchild,"Degree","Pos")):
              # Elephants have long not big trunks.            
              subobject=build_nested_properties(ctxt,sentence,tree,wordchild,rootlist,preferseq)
              if subobject:
                attachedwords.append(subobject)             
            if (wordchild["deprel"] in ["cc"]) and (wordchild["upos"] in ["CCONJ"]):
              op=wordchild["lemma"]
            if (wordchild["deprel"] in ["det","conj"]) and (wordchild["upos"] in ["DET"]):
              det=wordchild["lemma"]
              detcount+=1
            wordchildchildren=get_children(sentence,wordchild)
            for subword in wordchildchildren:
              if (subword["deprel"] in ["cc"]) and (subword["upos"] in ["CCONJ"]):
                op=subword["lemma"]
              if (subword["deprel"] in ["det","conj"]) and (subword["upos"] in ["DET"]):
                det=subword["lemma"]
                detcount+=1  

      subobject=build_nested_properties(ctxt,sentence,tree,word,rootlist,preferseq) #,False) 
      #debug_print("subobject",subobject)
      if subobject:
        attachedwords.append(subobject)
    elif ((deprel in ["acl"] and upos in ["VERB"]) or
          (deprel in ["acl:relcl"] and upos in ["ADJ","ADV","VERB"])):  
      wordchildren=get_children(sentence,word)
      markfound=False
      if wordchildren:
        # Mary bought the forest where the bears ate? : "where" has deprel mark
        for wordchild in wordchildren:  
          if wordchild["deprel"] in ["mark"] and wordchild["upos"] in ["SCONJ"]:
            markfound=True
      if not markfound:
        subobject=build_sentence_shaped_prop(ctxt,sentence,tree,objectword,word,rootlist,preferseq=False)
      else:
        subobject=build_sentence_shaped_prop(ctxt,sentence,tree,None,word,rootlist,preferseq=False)  
      #debug_print("markfound1",markfound)  
      #debug_print("deprel1",deprel) 
      #debug_print("objectword1",objectword)
      #debug_print("word1",word)
      #debug_print("children1",children)
      #debug_print("subobject1",subobject) 
      if subobject:
        sentsubobjectcount+=1
        attachedsentences.append(subobject)
    elif ((deprel in ["acl:relcl"] and upos in ["NOUN","PROPN"])):
      #debug_print("acl:relcl NOUN/PROPN word",word)    
      subobject=build_sentence_shaped_prop(ctxt,sentence,tree,objectword,word,rootlist,preferseq=False)
      #debug_print("subobject built",subobject) 
      if subobject:
        sentsubobjectcount+=1
        attachedsentences.append(subobject)  
    elif (deprel in ["nmod"] and upos in ["NOUN","PROPN"] and 
          "relation" not in objectword and "argument" not in objectword): # TODO
      # "John is in a box at the red house. A box is at the house?" here box is nmod 
      # but not "If X1 is a father of Y1, Y1 is a child of X1. John is a father of Mike. Who is a child of John?" 
      # and not "A head of Mary is clean?""
      subobject=build_sentence_shaped_prop(ctxt,sentence,tree,objectword,word,rootlist,preferseq=False)
      #debug_print("subobject2",subobject) 
      if subobject:
        sentsubobjectcount+=1
        attachedsentences.append(subobject)      

  if (attachedwords and type(attachedwords)==list and len(attachedwords)==1
      and type(attachedwords[0])==list and attachedwords[0][0] in ["and","or","nor"]): 
    op=attachedwords[0][0]  
    attachedwords=attachedwords[0][1:]+attachedwords[1:]
    if (attachedwords and type(attachedwords)==list and len(attachedwords)>1
        and type(attachedwords[0])==list and attachedwords[0][0] in ["seq"]): 
      # "bad, strong and red elephant are nice"
      attachedwords=attachedwords[0][1:] + attachedwords[1:]
      if op=="and": op="seq"

  if detcount==1:
    attachedwords=flatten_seq_term(attachedwords,["and"])
    attachedwords=flatten_seq_term(attachedwords)
  elif op:  
    attachedwords=flatten_seq_term(attachedwords,[op])   
  else:  
    attachedwords=flatten_seq_term(attachedwords)

  if attachedwords and type(attachedwords)==list and attachedwords[0]=="seq":
    attachedwords=attachedwords[1:]

  countwords=len(attachedwords)-sentsubobjectcount

  tmpres=None
  if attachedwords:
    if len(attachedwords)==1:
      tmpres=attachedwords[0]
    elif len(attachedwords)==2 and not op and detcount==1:
      tmpres=["seq"]+attachedwords  
    elif len(attachedwords)==2 and op and op=="and" and detcount==1:
      tmpres=["seq"]+attachedwords  
    elif len(attachedwords)==2 and op and detcount==2:
      tmpres=[op]+attachedwords
    elif op=="and" and len(attachedwords)==detcount:
      tmpres=[op]+attachedwords 
    elif op=="or":
      tmpres=[op]+attachedwords  
    elif preferseq and op=="and":
      tmpres=["seq"]+attachedwords 
    elif op:
      tmpres=[op]+attachedwords   
    else:
      tmpres=["seq"]+attachedwords  
  else:  
    tmpres=None 

  if (attachedsentences and len(attachedsentences)==1 and 
     type(attachedsentences[0])==list and
     attachedsentences[0][0]=="and"):
    attachedsentences=attachedsentences[0][1:]

  if not attachedsentences:
    return tmpres
  elif not tmpres and len(attachedsentences)==1:  
    return attachedsentences[0]
  elif not tmpres and len(attachedsentences)>1:
    return ["seq"]+attachedsentences
  else:
    return ["seq",tmpres]+attachedsentences  
     

def build_sentence_shaped_prop(ctxt,sentence,tree,objectword,word,rootlist,preferseq=False):
  #debug_print("build_sentence_shaped_prop tree",tree)
  #debug_print("build_sentence_shaped_prop objectword",objectword)
  #debug_print("build_sentence_shaped_prop word",word)
  #debug_print("build_sentence_shaped_prop parentsubj",word)
  if not tree: return None
  if type(word)!=dict: return None
  subject="$thing"
  verb=word
  object=objectword
  tmp1=build_subsentence_logic(ctxt,sentence,word,parentsubj=objectword)
  #debug_print("build_sentence_shaped_prop tmp1",tmp1)
  if tmp1:
    subsentence_root_list=[word]
    tmp2=build_subsentence_object_logic(ctxt,sentence,word,tmp1,subsentence_root_list)
    #debug_print("tmp2",tmp2)
    if tmp2:
      tmp3=build_subsentence_property_logic(ctxt,sentence,word,tmp2,subsentence_root_list)
      #debug_print("tmp3",tmp3)
      return tmp3
  else:
    return None
  res=["svo",[word,subject,verb,object]]
  return res

def build_nested_properties(ctxt,sentence,tree,objectword,rootlist,preferseq=False): #,adjroot=False):
  #debug_print("build_nested_properties objectword",objectword)
  #debug_print("build_nested_properties preferseq",preferseq)
  #debug_print("build_nested_properties adjroot",adjroot)
  if not objectword: return objectword
  children=get_children(sentence,objectword) 
  builtterm=objectword
  det=None
  for word in children:   
    if word in rootlist: continue
    deprel=word["deprel"] 
    upos=word["upos"]
    if ((deprel in ["amod"] and upos in ["ADJ"]) or
        (deprel in ["compound"] and upos in ["NOUN"]) or 
        (deprel in ["conj"] and upos in ["ADJ"]) ):        
      op="seq"
      subobject=word   
      # check if has child like cc: and [id:2 text:and upos:CCONJ xpos:CC]       
      wordchildren=get_children(sentence,word)
      if wordchildren:
        for wordchild in wordchildren:
          if (wordchild["deprel"] in ["cc"]) and (wordchild["upos"] in ["CCONJ"]):
            op=wordchild["lemma"]                            
          if (wordchild["deprel"] in ["det"]) and (wordchild["upos"] in ["DET"]):
            det=wordchild["lemma"]  
      if preferseq and op=="and" and not det:
        op="seq"
      subobject=build_nested_properties(ctxt,sentence,tree,word,rootlist,preferseq) #,adjroot)                
      builtterm=[op,builtterm,subobject]  
  #debug_print("builtterm",builtterm)
  return builtterm


def flatten_logic(ctxt,sentence,tree,iscondition=False):
  #debug_print("flatten_logic tree")
  #debug_print_logical_sentence_tree(tree)
  if not tree: return tree
  if type(tree)==str: return tree
  if type(tree)==dict: return tree
  if tree[0] in ["svo"]:
    res=flatten_object_logic(ctxt,tree,False,iscondition)    
    #debug_print("flatten_logic flat res")
    #debug_print_logical_sentence_tree(res)
    sys.exit(0)
  elif tree[0] in ["ref"]:
    ref=tree[1][1:]
    debug_print("ref",ref)
    sys.exit(0)
  else:
    if tree[0]=="if":
      iscondition=True
    res=[tree[0]]
    for el in tree[1:]:
      tmp=flatten_logic(ctxt,sentence,el,iscondition)
      res.append(tmp)
    return res    


def flatten_object_logic(ctxt,tree,isobject=False,iscondition=False):
  #debug_print("flatten_object_logic tree",tree)
  if not tree: return tree
  if type(tree)==str: return tree
  if type(tree)==dict: return tree
  if type(tree[0])==dict: return tree
  if tree[0] in ["svo","sv"]:
    root=tree[1][0]
    svo=tree[1][1:]        
    subj=svo[0]
    verb=svo[1]
    if tree[0] in ["svo"]:
      obj=svo[2]
    else:
      obj=None  
    subtree=subj       
    
    if type(subj)!=list or subj[0] in ["props"]:
      if (tree[0] in ["sv"] or type(obj)!=list or obj[0] in ["props"]):  
        newtree=tree
      else:
        newtree=tree      
    else:        
      flat=[subtree[0]]
      for el in subtree[1:]:
        if tree[0] in ["svo"]:
          nsvo=[tree[0],[root,el,verb,obj]]
        else:
          nsvo=[tree[0],[root,el,verb]]  
        flat.append(nsvo)
      #debug_print("subjflat",flat)
      #debug_print_logical_sentence_tree(flat)
      nflat=flatten_object_logic(ctxt,flat,False,iscondition) 
      #debug_print("nflat",nflat)
      #debug_print_logical_sentence_tree(nflat)     
      newtree=nflat    
   
    return newtree
   
  elif tree[0] in ["ref"]:
    ref=tree[1][1:]
    print("error: found ref",ref)
    sys.exit(0)  
  elif tree[0] in ["and","or","if","unless","nor","xor"]:
    
    if tree[0]=="if":
      iscondition=True
      return tree

    res=[tree[0]]
    for el in tree[1:]:
      tmp=flatten_object_logic(ctxt,el,False,iscondition)
      res.append(tmp)
    return res
  else:
    return tree  


def flatten_props_logic_aux(ctxt,tree,root,subtree,verb,obj,isobj=False):
  #debug_print("flatten_props_logic_aux subtree",subtree)
  #debug_print("flatten_props_logic_aux isobj",isobj)
  if type(subtree)!=list or type(subtree[1])!=list or subtree[1][0] in ["svo","sv","ref"]:
    newtree=tree
  elif isobj and subtree[0] in ["or","nor","xor","and"]:
    #return subtree
    if subtree[0]=="or":
      res=["xor"]
    else:      
      res=[subtree[0]] #"and"]
    for el in subtree[1:]:
      tmp=flatten_props_logic_aux(ctxt,tree,root,el,verb,el,isobj)
      res.append(tmp)
    return res
  else:  
    subseqfound=False
    oldprops=subtree[1]
    if not(oldprops[0] in ["seq"]):
      propslogic=oldprops
    else:              
      tmpprops=[]
      for prop in oldprops:
        if type(prop)==list and prop[0]=="seq":
          subseqfound=True
          tmpprops=tmpprops+prop[1:]
        else:
          tmpprops.append(prop)
      #debug_print("flatten_props_logic_aux tmpprops",tmpprops)      
      oldprops=tmpprops
      propslogic=None
      i=1
      while i<len(oldprops):
        if type(oldprops[i])==list and not (oldprops[i][0] in ["svo","sv","ref","or","nor","xor"]):
           # "A nice car bought by Mike is red." is a case for ["svo","sv","ref"] check above
          propslogic=oldprops[i]
          break
        i+=1  
    #debug_print("flatten_props_logic_aux propslogic",propslogic)    
    if not propslogic:    
      newtree=tree       
    else:        
      flat=[]                
      if type(propslogic)==list and propslogic[0] in ["svo","sv","ref"]: 
        # "John has a red car bought by Mike."
        flat.append(propslogic)
      elif type(propslogic)==list and propslogic[0] in ["and","or"]:
        flat.append(propslogic)
        # "John has a red or black car"
        # the thing commented out creates a too complex formula,
        # but is conceptually similar to correct!      
        flat.append(propslogic[0])   
        for el in propslogic[1:]:
          if (oldprops[0] in ["seq"]) and len(oldprops)>2:
            nprops=oldprops.copy()
            nprops[i]=el  
          else:  
            nprops=el  
          nprops=flatten_props_seq(nprops)
          nsubtree=["props",nprops,subtree[2]]
          if tree[0] in ["svo"]:       
            if isobj:       
              nsvo=[tree[0],[root,obj,verb,nsubtree]]
            else:
              nsvo=[tree[0],[root,nsubtree,verb,obj]]  
          else:
            nsvo=[tree[0],[root,nsubtree,verb]]  
          flat.append(nsvo)               
      nflat=flat
      newtree=nflat          
  return newtree

def flatten_props_seq(props):
  #debug_print("flatten_props_seq props",props)
  if not props: return props
  if type(props)!=list: return props
  if type(props[1])!=list: return props
  propslst=props[1]
  if propslst[0]!="seq": return props

  newpropslst=[propslst[0]]
  for seqel in propslst[1:]:
    if type(seqel)!=list or seqel[0]!="seq": 
      newpropslst.append(seqel)
    else:
      for subel in seqel[1:]:
        newpropslst.append(subel)  
  res=[props[0],newpropslst,props[2]]
  return res  


def check_logic(ctxt,logic):
  #debug_print("logic",logic)
  #debug_print("ctxt",ctxt)
  good_clauses=[]
  bad_clauses=[]
  bad_sentences=[]
  for clause in logic:
    if type(clause)==dict:
      if "@logic" in clause: pureclause=clause["@logic"]
      if "@question" in clause: pureclause=clause["@question"]
    else:
      pureclause=clause
    if bad_clause(pureclause):
      bad_clauses.append(clause)
      if "@name" in clause: 
        if clause["@name"] not in  bad_sentences:
          bad_sentences.append(clause["@name"])
      else:
          bad_sentences.append("some_sentence")
    else:
      good_clauses.append(clause)      
  #debug_print("bad_sentences",bad_sentences) 
  if bad_clauses:
    debug_print("NB! Some clauses were deemed suspicious and removed",bad_clauses)
  return good_clauses          

def bad_clause(cl):
  #debug_print("cl",cl)
  if None in cl: return True
  collected=collect_count_suspicious_free_vars(cl,[],{})
  okvars=["Fv","A","Q","Ignore","Tense","Rel","$unknown","Unit"]
  isbad=False
  for el in collected:
    if collected[el]==1:
      part=el[2:]
      isbad=True
      for okvar in okvars:
        if part.startswith(okvar):
          isbad=False
          break
      if isbad:
        if cl[0] not in ["or","and"]: tmpcl=[cl]
        else: tmpcl=cl
        for atom in tmpcl:
          #debug_print("el,atom",(el,atom))
          if (type(atom)==list and (atom[0].startswith("$def") or atom[0].startswith("-$def")) and 
              el in atom):
            isbad=False
            break
          #if (type(atom)==list and (atom[0].startswith("$def") or atom[0].startswith("-$def")) and 
          #    el in atom):
          #  isbad=False
          #  break
          if (type(atom)==list and atom[0] in ["isa","-isa"] and
              type(atom[2])==list and is_theof_or_measure_function(atom[2][0]) and
              el in atom[2][2:]):
            isbad=False
            break  
      if isbad:
        #None
        #print(cl,el)        
        return True
  return isbad


def collect_count_suspicious_free_vars(term,bound=[],collected={}):
  if not term: return collected
  if type(term)==str:
    if is_var(term):
      if not(term in bound) and not(term in collected):
        collected[term]=1
      elif not(term in bound) and (term in collected):
        collected[term]+=1
    return collected
  if type(term)!=list: 
    return collected
  if term[0] in ["forall","exists"]:
    tmp=collect_count_suspicious_free_vars(term[2],term[1]+bound,collected)
    return tmp
  for el in term:
    collected=collect_count_suspicious_free_vars(el,bound,collected)
    #debug_print("term",term)
    #debug_print("collected",collected)    
  return collected    
        


# =========== the end ==========
