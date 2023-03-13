# The object logic handling part of proper logic converter parts of nlpsolver, 
# used by nlpproperlogic
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

from multiprocessing import context
import sys

from requests import get

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

# small utilities are in nlputils.py
from nlputils import *

# uncertainty analysis and encoding is in nlpuncertain
from nlpuncertain import *

# pronoun guessing
from nlppronoun import *

from nlpanswer import *

import nlpsimplify

import nlptologic
#from nlptologic import build_property_logic

import nlpproperlogic

# ======= globals used and changed during work ===

#constant_nr=0 # new constants created add a numeric suffic, incremented
definition_nr=0 # new definitions created add a numeric suffic, incremented

# ===== tips for development =====


    
def update_ctxt_objects(ctxt,objrepr,word,logic):
  #debug_print("update_ctxt_objects objrepr",objrepr)
  #debug_print("update_ctxt_objects word",word)
  #debug_print("update_ctxt_objects logic",logic)
  if not logic: return
  if not objrepr: return
  if objrepr==dummysubject: return  
  flogic=apply_simple_defs(ctxt,logic)
  #debug_print("update_ctxt_objects flogic1",flogic)
  flogic=prop_flatten_logic_term(flogic)
  #debug_print("update_ctxt_objects flogic2",flogic)
  if not flogic: return  
  elif "objects" in ctxt:
    #debug_print("update_ctxt_objects flogic",flogic)
    found=False
    for el in ctxt["objects"]:
      if el[0]==objrepr:
        found=True
        newlogic=None
        if el[2]: # 
          filteredlogic=filter_new_logic(el[2],flogic)
          #debug_print("filteredlogic",filteredlogic)
          if filteredlogic:
            newlogic=["and",el[2],[dummypredicate], filteredlogic]
            newlogic=prop_flatten_logic_term(newlogic)
        else:
          newlogic=flogic  
        if newlogic:  
          el[2]=newlogic
    if not found:
      if True: #"argument" not in word:
        newel=[objrepr,word,flogic]
        ctxt["objects"].append(newel)
  else:
    newel=[objrepr,word,flogic]
    ctxt["objects"]=[newel]
    

def filter_new_logic(oldlogic,newlogic):
  if (not oldlogic) or (not newlogic): return newlogic
  if type(oldlogic)!=list or type(newlogic)!=list: return newlogic
  if newlogic in oldlogic: return None
  if newlogic[0] not in ["and","or"] or newlogic[0]!=oldlogic[0]: return newlogic
  res=[]
  for el in newlogic[1:]:
    if el not in oldlogic[1:]: res.append(el)
  if not res: return None
  else: return [newlogic[0]]+res


def verb_in_past(ctxt,sentence,verb):
  #debug_print("verb_in_past verb",verb)
  if not verb: return None
  if word_has_feat(verb,"Tense","Past"): return True
  children=get_children(sentence,verb)
  for child in children:
    #debug_print("verb_in_past child",child)
    # The man did not like the car?
    if child["deprel"] in ["aux"] and child["lemma"] in ["do"]:
      if word_has_feat(child,"Tense","Past"):
        return True
  #debug_print("verb_in_past gives False")      
  return False        


def make_object_data(ctxt,sentence,objpart):
  if not objpart: return objpart
  if type(objpart)==dict:
    data=make_object_data_single(ctxt,sentence,objpart)    
    return data
  elif objpart[0] in ["or","nor","xor","and"]:
    op=objpart[0]  
    res=[op]
    for el in objpart[1:]:
      data=make_object_data_single(ctxt,sentence,el)
      res.append(data)
    return res  
  else:
    data=make_object_data_single(ctxt,sentence,objpart)    
    return data 

def make_object_data_single(ctxt,sentence,objpart):
  #debug_print("make_object_data_single objpart",objpart)  
  #debug_print("make_object_data_single passed_words",ctxt["passed_words"])
  object=get_thing(objpart)
  objspecialvar=None
  objconst=None  
  objrepr=None   
  if pronoun(ctxt,object):
    tmp=resolve_pronoun(ctxt,sentence,object,None)
    if tmp:
      object=tmp[1]
      objrepr=tmp[0]
    else:
      print("error: cannot resolve pronoun, case 5",object)
      sys.exit(0)
      return None
  elif object and type(object)==dict and variable_shaped_lemma(object["lemma"]):
    svar="?:"+object["text"]
    objspecialvar=svar 
    objrepr=objspecialvar
  elif object and type(object)==dict and object["upos"] in ["PROPN"]:
    objconst=find_make_constant(ctxt,sentence,object)
    objrepr=objconst
  else:
    if "passed_words" in ctxt:
      for el in ctxt["passed_words"]:
        if el[1]==object:
          objrepr=el[0]
          break
    if not objrepr:    
      ovar="?:O"+str(ctxt["varnum"])
      ctxt["varnum"]+=1
      objrepr=ovar  
  object_quant=get_word_quant(ctxt,sentence,object)  
  object_det=get_word_det(ctxt,sentence,object)  
  #debug_print("object_quant",object_quant)
  #debug_print("object_det",object_det)
  res={"object":object,"objrepr": objrepr, "objspecialvar": objspecialvar, 
       "quant": object_quant, "det": object_det, 
       "objpart":  objpart}
  #debug_print("make_object_data_single res",res)
  return res     

def pronoun(ctxt,word):
  if not word: return False
  if type(word)!=dict: return False
  if word["upos"] in ["PRON"]:
    #debug_print("pronoun",word)
    #debug_print("ctxt",ctxt)
    #if (ctxt["isquestion"] and "question_type" in ctxt and ctxt["question_type"]=="who_is_of" and 
    #    word["lemma"] in ["whom","who"]):
    #  return False
    if (ctxt["isquestion"] and word["lemma"] in ["whom","who"] and word_has_feat(word,"PronType","Int")):
      return False  
    else:  
      return True
  elif word["deprel"] in ["mark"] and word["lemma"] in ["who","that","whom","which"]:
    #debug_print("pronoun",word)
    return True  
  return False



def make_obj_logic(ctxt,sentence,var,subjpart,verbpart,objpart,
         issubject=False,forcepositive=False,reversepolarity=False,confidence_data=1,subjrepr=None):
  #debug_print("make_obj_logic objpart",objpart)
  #debug_print("make_obj_logic ext_confidence",ext_confidence)
  #debug_print("make_obj_logic subjpart",subjpart)
  #debug_print("make_obj_logic verbpart",verbpart)
  #debug_print("make_obj_logic subjrepr",subjrepr)
  #debug_print("make_obj_logic issubject",issubject)
  #debug_print("make_obj_logic var",var)
  #debug_print("make_obj_logic reversepolarity",reversepolarity)
  #debug_print("make_obj_logic reversepolarity",reversepolarity)

  #if (type(objpart)==list and objpart[0]=="props" and is_number_str(objpart[1]["lemma"]) and
  #    len(objpart)>2 and nlpproperlogic.is_measure_unit(ctxt,objpart[2]["lemma"])):
  #  # "The length of the car is more than 5 meters."  
  #  return None

  proplogic=None
  if type(confidence_data)==list:
    ext_confidence=confidence_data[0]
    blocker_preferred=confidence_data[1]
  else:
    ext_confidence=confidence_data
    blocker_preferred=False
  #debug_print("make_obj_logic confidence_data",confidence_data)  
  sublistop="and"
  if (objpart and type(objpart)==list and objpart[0]=="props"):    
      object_props=objpart[1]
      #debug_print("object_props",object_props)
      if (type(object_props)==list and len(object_props)>1 and 
          object_props[0] in ["or","nor","xor"]):
        if object_props[0]=="or" and not issubject:
          sublistop="xor"
        else:        
          sublistop=object_props[0]   

  andlist=[]
  listop="and"
  if objpart and type(objpart)==list and objpart[0] in ["and","or","nor","xor"]: #"or","nor","xor"]
    listop=objpart[0]
    andlist=[listop]
    for el in objpart[1:]:
      tmp=make_obj_logic(ctxt,sentence,var,subjpart,verbpart,el,issubject,forcepositive,reversepolarity,confidence_data)
      andlist.append(tmp)
    if reversepolarity:
      andlist=["not",andlist]  
    #debug_print("make_obj_logic andlist",andlist)  
    return andlist  
  else:
    listop="and" 

  if issubject:
    if listop=="xor": listop="or"
  positive=True
  globalnegative=False
  top_confidence=1
  component_count=1
  if type(objpart)==list: 
    component_count=len(objpart)-1
    if component_count<1: component_count=1
  if component_count==1 or ext_confidence==1:  
    component_confidence=top_confidence*ext_confidence
  else:  
    #debug_print("comps ",[top_confidence,ext_confidence,component_count])
    component_confidence=top_confidence*ext_confidence ** (1. / float(component_count))

  thing=get_thing(objpart) 
  have_logic=make_have_logic(ctxt,sentence,var,subjpart,verbpart,objpart,None)
  if have_logic:
    #debug_print("inside make_obj_logic made have_logic",have_logic)
    if andlist: andlist.append(have_logic)
    else: andlist=[have_logic]

  #debug_print("make_obj_logic component_confidence",component_confidence)
  #debug_print("make_obj_logic thing",thing)
  #debug_print("make_obj_logic objpart",objpart)
  propslist=make_obj_props_list_of_thingpart(ctxt,objpart) 
  #debug_print("make_obj_logic propslist",propslist)
  propcount=0
  if var and type(var)==list and var[0]=="make_have_term":
    thisvar=make_have_term(ctxt,thing,var[1])
  else:  
    thisvar=var
  sublist=[sublistop]  
  for prop in propslist:
    #debug_print("prop in propslist 2",prop)
    if type(prop)==dict and prop["upos"] in ["PRON"]: continue
    if type(prop)==dict and prop["lemma"] in no_prop_words: continue
    propcount+=1
    if complex_property(prop):
      #debug_print("to build complex proplogic for thing",thing)
      proplogic=make_complex_property_atom(ctxt,sentence,thisvar,prop,thing)
      if proplogic:
        #debug_print("got complex proplogic",proplogic)
        #debug_print("for thing",thing)
        andlist.append(proplogic)
      continue
    if variable_shaped_word(prop):
      continue
    positive=get_word_polarity(ctxt,sentence,prop)
    #debug_print("prop",prop)
    #debug_print("positive for prop is",positive)
    #debug_print("propcount is",propcount)

    confidence=get_word_confidence(ctxt,sentence,prop)*component_confidence
    #debug_print("confidence1",confidence)
    #debug_print("component_confidence",component_confidence)
    confidence=confidence*component_confidence
    #debug_print("confidence2",confidence)
    if confidence==0: return None
    elif confidence<0:
      positive=not positive
      confidence=abs(confidence)

    if top_confidence!=1 and propcount==1: 
      top_confidence=confidence 
    #debug_print("top_confidence",top_confidence)  
    #debug_print("prop cp1 prop",prop)
    #debug_print("prop cp1 thing",thing)
    #debug_print("prop cp1 subjpart",subjpart)
    #debug_print("prop cp1 objpart",objpart)


    if thing and thing["upos"] in ["NOUN"]: propclass=thing
    elif thing and thing["lemma"] in ["who","which","that"]: propclass=thing
    else: propclass=None
    if issubject:   
      proplogic=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,prop,positive,thisvar,propclass=propclass)    
    elif prop["upos"]=="VERB" and word_has_feat(prop,"VerbForm","Part"):
      # John is a defeated politician    
      uvar="?:"+unknownsubject+str(ctxt["varnum"])
      ctxt["varnum"]+=1
      uactionrepr="?:A"+str(ctxt["varnum"])
      ctxt["varnum"]+=1
      proplogic=nlpproperlogic.make_atom_2(ctxt,sentence,verbpart,prop,positive,unknownsubject,thisvar,confidence,actionrepr=uactionrepr)
      proplogic=["exists",[uvar], proplogic]
    else:     
      proplogic=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,prop,positive,thisvar,confidence,
        propclass=propclass,blocker_preferred=blocker_preferred)
    
    if proplogic:      
      sublist.append(proplogic)
  
  #debug_print("make_obj_logic andlist1",andlist)  

  if sublist and len(sublist)>1:
    andlist.append(sublist)   

  #debug_print("make_obj_logic andlist2",andlist)   
  #debug_print("make_obj_logic thing",thing) 
  if not variable_shaped_word(thing):   
    if not forcepositive:
      positive=get_word_polarity(ctxt,sentence,thing)   
      confidence=get_word_confidence(ctxt,sentence,thing)*component_confidence
      if confidence==0: return None  
      elif confidence<0:
        positive=not positive
        confidence=abs(confidence)
      if not positive and thing["deprel"]!="conj":
        globalnegative=True
        positive=True 
      if thing and thing["deprel"]!="conj":
        top_confidence=confidence

    if (thing and thing["upos"] in ["ADJ"] and thing==objpart and subjpart and 
        type(subjpart)==dict and 
        subjpart["lemma"] in ["who","which","that"]):
      propclass=subjpart      
    else: propclass=None

    if issubject:
      thingatom=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,thing,
        positive,thisvar,propclass=propclass)
    else:        
      if not propclass and verbpart and type(verbpart)==dict and verbpart["lemma"] in ["be"]:         
        #"The stone was heavy."
        if subjpart:
          subjthing=get_thing(subjpart)
          if pronoun(ctxt,subjthing) and subjrepr and not is_var(subjrepr):
            for el in ctxt["objects"]:
              if el[0]==subjrepr:
                subjthing=el[1]
                break
          if (subjthing["upos"] in ["NOUN"] and (not thing["upos"] in ["NOUN"]) and
              (not word_has_feat(subjthing,"Number","Plur"))):
            propclass=subjthing          
      thingatom=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,thing,positive,thisvar,
        confidence,propclass=propclass,blocker_preferred=blocker_preferred) 
    if thingatom:
      #if deco:
      #  andlist.append(["logic",thing,thingatom])
      #else:
      #debug_print("thingatom",thingatom)
      andlist.append(thingatom)      

  top_confidence=top_confidence*ext_confidence 

  if issubject and subjpart and type(subjpart)==list and is_theof_or_measure_function(subjpart[0]):
    tmp_logic=["rel2","have",subjpart[2],subjpart]
    if ctxt["addctxt"]:
      ctxtargument=nlpproperlogic.make_ctxt_argument(ctxt,sentence,verbpart)
      tmp_logic.append(ctxtargument)
    andlist.append(tmp_logic)

  if not andlist:
    return True   
  elif len(andlist)==1:
    andlist=andlist[0]       
  else:
    andlist=[listop]+andlist
    if top_confidence!=1:
      #debug_print("interesting andlist",andlist)  
      andlist=spread_andlist_confidence(ctxt,andlist,confidence)  
  if reversepolarity: globalnegative=not globalnegative      
  if globalnegative: # and not deco:
    #debug_print("globalnegative",globalnegative)
    andlist=["not",andlist]     
  
  #debug_print("make_obj_logic returns andlist",andlist)  
  return andlist   

def spread_andlist_confidence(ctxt,lst,confidence):
  #debug_print("spread_andlist_confidence lst",lst)
  #debug_print("spread_andlist_confidence confidence",confidence)
  if not lst: return lst
  if type(lst)!=list: return lst
  res=[]
  nr=len(lst)-1
  if nr>1:
    splitconfidence=confidence ** (1. / float(nr))
  else:
    splitconfidence=confidence  
  for el in lst:
    if type(el)!=list: res.append(el)
    newel=el
    if not (el[0] in ["and","or","not"]):
      atomconfidence=get_atom_decorated_confidence(ctxt,el)
      if atomconfidence!=None:
        newel=el.copy()
        for elterm in newel:
          if elterm and type(elterm)==list and elterm[0]==confidence_function:
            elterm[1]=splitconfidence
       
    res.append(newel)   
  #debug_print("spread_andlist_confidence res",res)  
  return res   

def get_atom_decorated_confidence(ctxt,lst):
  if not lst: return None
  if type(lst)!=list: return None
  for el in lst:
    if el and type(el)==list and el[0]==confidence_function:
      return el[1]
  return None    

def make_simple_obj_logic(ctxt,sentence,var,subjpart,verbpart,objpart,actionvar,getconfidence=True):
  #debug_print("make_simple_obj_logic objpart",objpart)
  #debug_print("make_simple_obj_logic verbpart",verbpart)
  #debug_print("make_simple_obj_logic var",var)
  #debug_print("make_simple_obj_logic actionvar",actionvar)

  #if (type(objpart)==list and  len(objpart)>2 and objpart[0]=="props" and 
  #    type(objpart[1])==dict and
  #    is_number_str(objpart[1]["lemma"]) and nlpproperlogic.is_measure_unit(ctxt,objpart[2]["lemma"])):
  #  # "The length of the car is more than 5 meters."  
  #  return None

  andlist=[]
  listop="and"
  sublistop="and"
  if (objpart and type(objpart)==list and objpart[0]=="props"):    
      object_props=objpart[1]
      #debug_print("object_props",object_props)
      if (type(object_props)==list and len(object_props)>1 and 
          object_props[0] in ["or","nor","xor"]):
        if object_props[0]=="or":
          sublistop="xor"
        else:        
          sublistop=object_props[0]      

  positive=True
  thing=get_thing(objpart) 
  #debug_print("thing",thing)
  propslist=make_obj_props_list_of_thingpart(ctxt,objpart) 
  propcount=0
  if var and type(var)==list and var[0]=="make_have_term":
    thisvar=make_have_term(ctxt,thing,var[1])
  else:  
    thisvar=var
  #debug_print("thisvar",thisvar)  
  top_positive=True  
  sublist=[sublistop]
 
  #debug_print("before make_have_logic var",var)
  #debug_print("before make_have_logic objpart",objpart)
  have_logic=make_have_logic(ctxt,sentence,var,subjpart,verbpart,objpart,actionvar)
  #debug_print("after make_have_logic have_logic",have_logic)

  if have_logic:
    #debug_print("have_logic",have_logic)
    if andlist: andlist.append(have_logic)
    else: andlist=[have_logic]  

  for prop in propslist:
    #debug_print("prop in propslist 1",prop)
    if type(prop)==dict and prop["upos"] in ["PRON"]: continue
    if type(prop)==dict and prop["lemma"] in no_prop_words: continue
    propcount+=1
    if complex_property(prop):
      proplogic=make_complex_property_atom(ctxt,sentence,thisvar,prop,thing)
      if proplogic:
        andlist.append(proplogic)
      continue
    if variable_shaped_word(prop):
      continue

    localpositive=get_word_polarity(ctxt,sentence,prop,True)
    globalpositive=get_word_polarity(ctxt,sentence,prop)
    if not localpositive or not globalpositive: positive=False
    else: positive=True    

    if getconfidence:
      confidence=get_word_confidence(ctxt,sentence,prop)
      #debug_print("confidence1",confidence)
      if confidence==0: return None
      elif confidence<0: 
        positive=not positive
        confidence=abs(confidence)
    else:
      confidence=1    
 
    if thing and thing["upos"] in ["NOUN"]: propclass=thing
    elif thing and thing["lemma"] in ["who","which","that"]: propclass=thing
    else: propclass=None 
    #proplogic=make_qualified_atom_1(ctxt,sentence,prop,positive,thisvar,confidence,None,None,propclass)
    proplogic=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,prop,positive,thisvar,confidence,propclass=propclass)    
    if proplogic:      
      sublist.append(proplogic)

  if sublist: # and len(sublist)>1:
    andlist.append(sublist)    
  if not variable_shaped_word(thing):
    #debug_print("cpx thing",thing)
    can_make_global_negative=True
    localpositive=get_word_polarity(ctxt,sentence,thing,True)
    globalpositive=get_word_polarity(ctxt,sentence,thing)
    if not localpositive or not globalpositive: positive=False
    else: positive=True  
    if globalpositive:
      can_make_global_negative=False
    
    if getconfidence:
      confidence=get_word_confidence(ctxt,sentence,thing)
    else:
      confidence=1  
    if confidence==0: return None
    if not positive and can_make_global_negative:
      top_positive=False
    if confidence<0:
      positive=not positive
      top_positive=not top_positive 
      confidence=abs(confidence)   
    
    thingatom=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,thing,True,thisvar,confidence) 

    if (thingatom and 
        not(thing["lemma"] in no_prop_words) and
        not(type(thing)==dict and thing["upos"] in ["PRON"])):
      andlist.append(thingatom)      
  #debug_print("make_obj_logic andlist2",andlist)       
  if not andlist:
    return True   
  elif len(andlist)==1:
    andlist=andlist[0]       
  else:
    andlist=[listop]+andlist 
  if not top_positive:
    andlist=["not",andlist]   
  #debug_print("make_simple_obj_logic returns andlist",andlist)  
  #debug_print("make_simple_obj_logic builds objects")
  return andlist   

def make_have_logic(ctxt,sentence,var,subjpart,verbpart,objpart,actionvar):
  #debug_print("------ make_have_logic objpart",objpart)
  #debug_print("make_have_logic var",var)
  #debug_print("make_have_logic subjpart",subjpart)
  #debug_print("make_have_logic verbpart",verbpart)
  #debug_print("make_have_logic actionvar",actionvar)
  #debug_print("make_obj_logic reversepolarity",reversepolarity)
  
  if not objpart: return None
  thing=get_thing(objpart) 
  #debug_print("make_have_logic thing",thing)
  tmp_isquestion=ctxt["isquestion"]
  ctxt["isquestion"]=False  
  if not ("argument") in thing:
    #debug_print("------ make_have_logic returns with None")
    ctxt["isquestion"]=tmp_isquestion
    return None
  origvar=var 
  have_logic=None
  oarg_logic=None
  object=thing
  oargvar=None
  oargument=object["argument"]
  if "argprops" in thing:
    oargprops=object["argprops"]
  else:
    oargprops=oargument  
  object_det=get_word_det(ctxt,sentence,object)  
  oargument_det=get_word_det(ctxt,sentence,oargument)               
  iscondition=False
  isconsequence=False
  if verbpart:
    verb=get_thing(verbpart)
  else:
    verb=None  
  if oargument["upos"] in ["PROPN"]:
    oargumentconst=find_make_constant(ctxt,sentence,oargument)  
    #debug_print("make_have_logic oargumentconst",oargumentconst)
    oargrepr=oargumentconst
  elif nlpproperlogic.is_concrete_thing(ctxt,sentence,oargument,oargument_det,verb,iscondition,isconsequence,
          isobject=True,prefer_non_concrete=True):
    #debug_print("is concrete!!! oargument",oargument)
    tmp_logic=make_simple_obj_logic(ctxt,sentence,dummysubject,subjpart,verbpart,oargprops,actionvar)
    tmp_logic=prop_flatten_logic_term(tmp_logic)
    oargrepr=make_determined_constant(ctxt,sentence,oargument,oargument_det,tmp_logic,verb) 
    #debug_print("make_determined_constant in make_have_logic gave oargrepr",oargrepr)   
    tmp_logic=logic_replace_el(tmp_logic,dummysubject,oargrepr)
    oarg_logic=tmp_logic
    if ("objects" in ctxt):
      for el in ctxt["objects"]:
        if el[0]==oargrepr:
          el[2]=logic_replace_el(el[2],dummysubject,oargrepr)
    if not ctxt["isquestion"]:
      update_ctxt_objects(ctxt,oargrepr,oargument,tmp_logic)      
  else:  
    #debug_print("is not oconcrete!!! oargument origvar",(oargument,origvar))
    if origvar and type(origvar)==list and is_theof_or_measure_function(origvar[0]):
      tmp=origvar
      oargvar=origvar[2]
      oargrepr=tmp
    elif False: #origvar and is_var(origvar):
      oargvar=origvar
      oargrepr=origvar  
    else:
      oargvar="?:O"+str(ctxt["varnum"])
      ctxt["varnum"]+=1  
      oargrepr=oargvar    
    oarg_logic=make_simple_obj_logic(ctxt,sentence,oargvar,subjpart,verbpart,oargprops,actionvar)
    #oarg_logic=["exists",[oargvar],oarg_logic]
    if not ctxt["isquestion"]:
      update_ctxt_objects(ctxt,oargrepr,oargument,oarg_logic)

  #debug_print("oargrepr 1",oargrepr)
  #debug_print("var 1",var)

  if type(var)==list and is_theof_or_measure_function(var[0]):
    #term=var
    #debug_print("CPX oargrepr",oargrepr)
    #debug_print("CPX var",var)
    term=var[2]
    #term=oargrepr
  elif (object_det and object_det["lemma"] in ["the"]):
    #debug_print("concrete argument-having object")
    term=make_the_or_measure_term(ctxt,sentence,object,oargrepr,verb,tmp_isquestion)
    #debug_print("make_have_logic created theof-term 1",term) 
    #term=[theof_function+"1",object["lemma"],oargrepr]   
    #debug_print("make_have_logic created theof-term 2",term) 
    #debug_print("object",object)
    #debug_print("object term 1",term)      
    tmp=term
    term=var
    var=tmp
    #oargrepr=term  
    if not ctxt["isquestion"]:
      tmp_logic=["rel2","have",oargrepr,term]
      if ctxt["addctxt"]:
        ctxtargument=nlpproperlogic.make_ctxt_argument(ctxt,sentence,verbpart)
        tmp_logic.append(ctxtargument)
      #ctxt["sentence_extralogic"].append(tmp_logic)
      if ("nosaveconstant" in ctxt and ctxt["nosaveconstant"]):
        None
      else:                  
        if "objects" in ctxt:      
          ctxt["objects"].append([term,object,tmp_logic])
        else:
          ctxt["objects"]=[[term,object,tmp_logic]]
  else: #if ctxt["isquestion"]:
    #debug_print("not a concrete argument-having object")
    term=oargrepr
    if var and (not ctxt["isquestion"]) and (not  ("nosaveconstant" in ctxt and ctxt["nosaveconstant"])):                     
      tmp_logic=None
      if True: #"argument" not in object:
        if "objects" in ctxt:      
          ctxt["objects"].append([var,object,tmp_logic])
        else:
          ctxt["objects"]=[[var,object,tmp_logic]]

  #debug_print("before arglogic oargrepr oargument",(oargrepr,oargument))
  arglogic=make_simple_obj_logic(ctxt,sentence,oargrepr,subjpart,verbpart,oargument,None)
  arglogic=prop_flatten_logic_term(arglogic)
  #if arglogic:
  #  freevars=def collect_free_vars(term,bound=[],collected=[]):

  #debug_print("arglogic",arglogic)
  #debug_print("oarg_logic",oarg_logic)
  #debug_print("term",term)
  #debug_print("var",var)
  #debug_print("origvar",origvar)
  #debug_print("oargrepr",oargrepr)

  #if False and origvar==dummysubject and type(var)==list and is_theof_or_measure_function(var[0]):   
  #  have_logic_atom=["rel2","have",var[2],term] 
  if type(var)==list and is_theof_or_measure_function(var[0]):
    #debug_print("cp1")
    #have_logic_atom=["rel2","have",var[2],term] 
    #have_logic_atom=["rel2","have",term,var] 
    have_logic_atom=["rel2","have",var[2],var] 
  else:  
    #debug_print("cp2")
    have_logic_atom=["rel2","have",term,var]

  #debug_print("cp3 have_logic_atom",have_logic_atom)  
  
  if ctxt["addctxt"]:
    ctxtargument=nlpproperlogic.make_ctxt_argument(ctxt,sentence,verbpart)
    have_logic_atom.append(ctxtargument)  
  if oarg_logic:
    have_logic=["and",oarg_logic,have_logic_atom]  
  else:
    have_logic=have_logic_atom    
  if is_var(term):
    #have_logic=["exists",[term],have_logic]   
    #having_atom=["exists",[ovar],]
    if not(ctxt["isquestion"]) and not(object_det and object_det["lemma"] in ["the"]):
      tmp_atom=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,verbpart,thing,True,var)
      blocker=["$block",0,["$not",have_logic_atom]]
      extra_have_logic=["forall",[term],[arglogic,"=>",["or",blocker,["exists",[var],["and",tmp_atom,have_logic_atom]]]]]
      extra_have_logic=["forall",[term],[arglogic,"=>",["exists",[var],["and",tmp_atom,["or",blocker,have_logic_atom]]]]]
      extra_have_logic=["forall",[term],[arglogic,"=>",["exists",[var],["and",tmp_atom,have_logic_atom]]]]
      if is_var(term):
        newtermvar="?:O"+str(ctxt["varnum"])
        ctxt["varnum"]+=1    
        extra_have_logic=logic_replace_el(extra_have_logic,term,newtermvar)       
      if is_var(var):
        newvar="?:O"+str(ctxt["varnum"])
        ctxt["varnum"]+=1        
        extra_have_logic=logic_replace_el(extra_have_logic,var,newvar)
      extra_have_logic={"@logic": extra_have_logic, "@confidence":0.7}
      #debug_print("extra_have_logic",extra_have_logic)
      #debug_print("ctxt[sentence_extralogic]",ctxt["sentence_extralogic"])
      ctxt["sentence_extralogic"].append(extra_have_logic)  
 
  res=have_logic
  ctxt["isquestion"]=tmp_isquestion
  #debug_print("---- have_logic res",res)
  return res


def make_obj_data_logic(ctxt,sentence,var,subjpart,verbpart,objpart,object_data,
      specialvar=False,forcepositive=False,reversepolarity=False,confidence_data=1,subjrepr=None):
  #debug_print("make_obj_data_logic object_data",object_data)
  #debug_print("make_obj_data_logic top_confidence",top_confidence)
  #debug_print("make_obj_data_logic subjpart",subjpart)
  #debug_print("make_obj_data_logic reversepolarity",reversepolarity)
  if type(confidence_data)==list:
    top_confidence=confidence_data[0]
  else:
    top_confidence=confidence_data
  if not object_data: return object_data
  if type(objpart)==dict and not("objpart" in object_data): 
    res=make_obj_logic(ctxt,sentence,var,subjpart,verbpart,object_data,specialvar,forcepositive,False,confidence_data,subjrepr)
  elif type(object_data)==dict and "objpart" in object_data: 
    res=make_obj_logic(ctxt,sentence,var,subjpart,verbpart,object_data["objpart"],specialvar,forcepositive,False,confidence_data,subjrepr)
  elif type(object_data)==list:
    op=object_data[0]
    res=[op]
    for el in object_data[1:]:
      tmp=make_obj_data_logic(ctxt,sentence,var,subjpart,verbpart,el["objpart"],el,specialvar,forcepositive,False,confidence_data,subjrepr)  
      res.append(tmp)
  #debug_print("make_obj_data_logic reversepolarity",reversepolarity)
  if top_confidence==0: return None  
  elif top_confidence<0: reversepolarity=not reversepolarity  
  if reversepolarity:
    res=["not",res]    
  #debug_print("make_obj_data_logic res",res)    
  return res

def complex_property(prop):
  #debug_print("complex_property prop",prop)
  if not prop: return False
  if type(prop)==list and prop[0] in ["svo","sv","ref"]:
    return True
  else:
    return False


def make_simple_conj_logic(ctxt,sentence,word,var):
  #debug_print("make_simple_conj_logic word",word)
  toplist=[]
  toplistop="and"
  positive=True
  confidence=1
  if type(word)==dict and word["lemma"] in no_prop_words:
    None
  elif type(word)==dict and word["lemma"] in lemma_confidences:   
    None
  else:  
    toplogic=nlpproperlogic.make_qualified_atom_1(ctxt,sentence,word,word,positive,var,confidence)
    toplist.append(toplogic)
  children=get_children(sentence,word)
  for child in children:
    if child["deprel"] in ["advmod","conj"] and child["upos"] in ["ADV"]:
      sublogic=make_simple_conj_logic(ctxt,sentence,child,var)
      if sublogic:
        toplist.append(sublogic)
        if child["deprel"] in ["conj"]:
          childchildren=get_children(sentence,child)
          for childchild in childchildren:
            #debug_print("make_simple_conj_logic childchild",childchild)
            if childchild["deprel"] in ["cc"] and childchild["upos"] in ["CCONJ"]:
              #debug_print("make_simple_conj_logic childchild lemma",childchild["lemma"])
              if childchild["lemma"] in ["or"]: toplistop="or"
              elif childchild["lemma"] in ["and"]: toplistop="and"
  res=[toplistop]+toplist
  #debug_print("make_simple_conj_logic res",res)
  return res    


def has_aux_from_list(sentence,word,auxwords):
  if not word: return None
  if type(word)==dict:
    wordchildren=get_children(sentence,word)
    for child in wordchildren:
      if child["deprel"] in ["aux"] and child["upos"] in ["AUX"]:
        if child["lemma"] in auxwords:
          return True  
    if has_parent_aux_from_list(sentence,word,auxwords):
      return True   
  return False

def has_parent_aux_from_list(sentence,word,auxwords):
  if not word: return None
  if type(word)==dict:      
    if word["deprel"] in ["conj"]:
      parent=get_parent(sentence,word)
      wordchildren=get_children(sentence,parent)
      for child in wordchildren:
        if child["deprel"] in ["aux"] and child["upos"] in ["AUX"]:
          if child["lemma"] in auxwords:
            return True        
  return False


def make_complex_property_atom(ctxt,sentence,origvar,prop,thing,parent_object=None):
  #debug_print("make_complex_property_atom origvar",origvar)
  #debug_print("make_complex_property_atom prop",prop)
  #debug_print("make_complex_property_atom thing",thing)
  #debug_print("make_complex_property_atom parent_object",parent_object)
  replaced=prop
  if parent_object:
    prelogic=nlpproperlogic.build_single_subsentence_proper_logic(ctxt,sentence,replaced,False,False,1,parent_object)    
  elif origvar:
    prelogic=nlpproperlogic.build_single_subsentence_proper_logic(ctxt,sentence,replaced,False,False,1,[origvar,thing])  
  else:
    prelogic=nlpproperlogic.build_single_subsentence_proper_logic(ctxt,sentence,replaced,False,False,1,["?:X10",thing])   
 
  top_bound_vars=[]
  if prelogic and type(prelogic)==list:
    freevars=collect_free_vars(prelogic)
    #debug_print("freevars",freevars)
    quants=filter_containing_listels(prelogic,["forall","exists"])
    if (not freevars) and (not quants) and prelogic[0] in ["isa","-isa","prop","-prop","and"]:
      return prelogic

    if prelogic[0] in ["forall","exists"]:
      purelogic=prelogic[2]
      top_bound_vars=prelogic[1]
    else:
      purelogic=prelogic  
  else:
    purelogic=prelogic

  if (top_bound_vars and is_var(origvar) and origvar not in top_bound_vars and
      origvar not in freevars):
    purevar=top_bound_vars[0]
  else:
    purevar=origvar

  defn=make_definition(ctxt,purelogic,[purevar])
  #debug_print("make_complex_property_atom built defn",defn)
  if origvar and type(defn)==list and defn[0]=="forall":  
    defatom=[defn[2][0][0], origvar]
  elif type(defn)==list and defn[0]=="forall":
    defatom=defn[2][0]
  else:
    defatom=defn[0]
  #debug_print("make_complex_property_atom defatom",defatom)  
  #debug_print("make_complex_property_atom ctxt1",ctxt)
  if "sentence_defs" in ctxt:
    ctxt["sentence_defs"].append(defn)
  else:
    ctxt["sentence_defs"]=[defn]
  defatom=logic_replace_el(defatom,"?:X10",origvar)
  #debug_print("ctxt[objects] at the end of make_complex_property_atom",ctxt["objects"])
  #debug_print("make_complex_property_atom built defatom",defatom) 
  return defatom


def get_thing(thingdata):
  #debug_print("get_thing thingdata",thingdata)
  if not thingdata: return None
  if type(thingdata)==dict:
    return thingdata
  elif (type(thingdata)==list and type(thingdata[-1])==list and  
        thingdata[-1][0] in ["props"]):
    return thingdata[-1][-1]
  else:
    return thingdata[-1] 

def get_props_list(thingdata):
  if type(thingdata)==dict:
    return []
  props=thingdata[1]  
  if type(props)==list:
    return props[1:]  
  else:
    return [props]       

def make_props_list_of_thingpart(ctxt,subjpart):
  #debug_print("make_props_list_of_thingpart subjpart",subjpart)
  if type(subjpart)!=list:
    return []
  if type(subjpart[1])==dict:
    return [subjpart[1]]
  elif complex_property(subjpart[1]):
    return [subjpart[1]]
  else:
    return subjpart[1][1:]  

def make_obj_props_list_of_thingpart(ctxt,objpart):
  #debug_print("make_obj_props_list_of_thingpart objpart",objpart)
  if type(objpart)!=list:
    return []
  elif objpart[0] in ["and","seq","or","nor","xor"]:
    tmp=objpart[1:-1]    
    if type(objpart[-1])==list and objpart[-1][0] in ["props"]:
      tmp=tmp+objpart[-1][1:-1]
    #debug_print("tmp",tmp)
    return tmp
  elif not objpart[1]:
    return []  
  elif type(objpart[1])==dict:
    return [objpart[1]]   
  elif complex_property(objpart[1]):
    return [objpart[1]]
  else:
    return objpart[1][1:]     

def make_number_from_str(lemma):
  if not lemma: return ""
  if type(lemma)==int or type(lemma)==float: return lemma
  if "." in lemma:
    try:
      res=float(lemma)
      return res
    except:
      return lemma  
  else:  
    res=parse_int(lemma)
  if res==None: return lemma
  else: return res

def make_have_term(ctxt,object,var):
  lemma=object["lemma"]
  fun="fun"
  res=["of",lemma,var]
  return res

def get_word_quant(ctxt,sentence,word):
  if not word: return None
  if not(type(word)==dict): return None
  children=get_children(sentence,word)
  if children:
    for child in children:
      if child["deprel"]=="det" and child["upos"]=="DET":
        if child["lemma"] in ["a","an","the"]:
          return None
        else:
          return child
      elif child["deprel"]=="amod" and child["upos"]=="ADJ":
        if child["lemma"] in ["most","every","each"]:
          return child         
    for child in children:
      if not (child["deprel"] in ["amod"]): continue
      #debug_print("child in get_word_quant",child)
      childchildren=get_children(sentence,child)
      for childchild in childchildren:
        #debug_print("childchild in get_word_quant",childchild)
        if childchild["deprel"]=="advmod" and childchild["upos"]=="ADV":
          if childchild["lemma"] in ["some","most","few"]:
            return childchild         
  parent=get_parent(sentence,word)
  if parent:
    res2=get_word_quant(ctxt,sentence,parent)
    if res2:
      return res2
  return None  

def get_word_det(ctxt,sentence,word):
  if not word: return None
  if not(type(word)==dict): return None
  children=get_children(sentence,word)
  if children:
    for child in children:
      if child["deprel"]=="det" and child["upos"]=="DET":
        if child["lemma"] in ["a","an","the"]:
          return child
        else:
          return None
  parent=get_parent(sentence,word)
  if parent and not (word["deprel"] in ["obj"]):
    if ((word["deprel"] in ["nsubj"]) and (parent["deprel"] in ["root"]) and
        parent["upos"] in ["NOUN"]):
      # Plastic is an insulator
      None
    else:  
      res2=get_word_det(ctxt,sentence,parent)
      if res2:
        return res2
  return None        

def get_word_polarity(ctxt,sentence,word,localonly=False):
  #debug_print("get_word_polarity word",word)
  #debug_print("get_word_polarity localonly",localonly)
  if not word: return True
  if not(type(word)==dict): return True
  children=get_children(sentence,word)
  res1=None
  if children and not localonly:    
    for child in children:
      #debug_print("get_word_polarity child",child)
      next=get_next_word(sentence,child)
      if (next and next!=word and next["deprel"]=="amod" and 
          next["upos"]=="ADJ"): notused=True # "Elephants have long not red trunks."        
      else: notused=False  
      #debug_print("get_word_polarity notused",notused)  
      if child["deprel"]=="advmod" and child["upos"] in ["PART","ADV"]:
        if  ((child["lemma"] in ["not"] and not notused) or
             (child["lemma"] in ["no","never","zero"])):
          return False
      elif child["deprel"]=="nummod" and child["upos"] in ["NUM"]:
        if child["lemma"] in [0,"0","zero"]:
          return False    
      elif child["deprel"]=="det" and child["upos"] in ["DET"]:
        if child["lemma"] in ["not","no","never","zero"]:
          return False   
  # special case for verbs
  if word["upos"] in ["VERB"] and word["deprel"] in ["conj"] and not localonly:
    # Birds do not fly and swim
    parent=get_parent(sentence,word)
    if parent["upos"] in ["VERB"]:
      parentchildren=get_children(sentence,parent)
      for parentchild in parentchildren:
        if (parentchild["deprel"] in ["advmod"]) and parentchild["lemma"] in ["not"]:
          return False
  if word["upos"] in ["ADJ"] and localonly:
    prev=get_previous_word(sentence,word)
    #debug_print("word",word)
    #debug_print("prev",prev)
    if prev and prev["deprel"]=="advmod" and prev["upos"]=="PART" and prev["lemma"] in ["not"]:
      #Elephants have long not red trunks.
      return False
  
  return True    


# ============ some definition stuff ==================


def make_definition(ctxt,clause,keepvars):
  #debug_print("make_definition clause",clause)
  #debug_print("make_definition keepvars",keepvars)
  global definition_nr
  vars=keepvars 
  freevars=collect_free_vars(clause)
  pred=definition_prefix+str(definition_nr)
  definition_nr+=1   
  conseq=[pred]+keepvars #vars
  premiss=clause
  forallvars=[]
  for el in freevars:
    if not (el in keepvars):
      forallvars.append(el)
  existvars=[]
  for el in vars:
    if not (el in forallvars):
      existvars.append(el)
  if existvars:
    leftside=premiss #["exists",existvars,premiss] 
  else:
    leftside=premiss  
  #debug_print("make_definition leftside 1",leftside)  
  leftside=logic_remove_quantors(leftside,keepvars,["exists"]) 
  #debug_print("make_definition leftside 2",leftside)
  if (not(("isquestion" in ctxt) and ctxt["isquestion"]) and
      (not nlpproperlogic.noframes) and (not nlpproperlogic.noframevars)):
    leftside=logic_generalize_framevars(ctxt,leftside)
  #debug_print("make_definition leftside 3",leftside)  
  makeexistvars=[]
  for el in forallvars:
    if not (el.startswith(frame_var_prefix) or el.startswith(unit_var_prefix)):
    #if not el.startswith(frame_var_prefix):  
      makeexistvars.append(el)
  #debug_print("leftside",leftside)
  #debug_print("conseq",conseq)
  #debug_print("mainbody",mainbody)    
  #debug_print("forallvars",forallvars)  
  #debug_print("makeexistvars",makeexistvars)
  if forallvars:    
    if (makeexistvars and len(makeexistvars)==1 and
         nlpproperlogic.is_keep_free_var(ctxt,makeexistvars[0])):
        #(makeexistvars[0].startswith("?:Tense") or makeexistvars[0].startswith("?:Unit"))):
      leftside=nlpsimplify.push_quantifier_weakly_inside(leftside,"exists",makeexistvars[0])  
    else:
      leftside=["exists", makeexistvars, leftside]    
  mainbody=[conseq,"<=>",leftside]
  if keepvars:
    mainbody=["forall", keepvars, mainbody]
  res=mainbody
  #debug_print("make_definition res 1",res)
  res=simplify_quantors(res)
  #debug_print("make_definition res",res)
  return res
  
def simple_definition(ctxt,logic):
  #debug_print("simple_definition logic",logic)
  if type(logic)!=list: return False
  if logic[0]!="forall": return False
  boundvars=logic[1]
  if (not boundvars) or len(boundvars)>1: return False
  logic=logic[2]
  if len(logic)!=3: return False
  if logic[1]!="<=>": return False
  head=logic[0]
  body=logic[2]
  if type(body)!=list: return False
  if len(head)!=2: return False
  var=head[1]
  if boundvars[0]!=var: return False
  bvars=collect_free_vars(body)
  importantvars=[]
  for el in bvars:
    if not (el.startswith(frame_var_prefix) or el.startswith(unit_var_prefix)): 
      importantvars.append(el)
  if len(importantvars)>1: return False
  if importantvars and not (var in importantvars): return False
  if body[0]!="and": tmpbody=[body]
  else: tmpbody=body[1:]
  for el in tmpbody:
    if type(el)!=list: return False
    if el[0] in logic_ops: return False
  #debug_print("simple_definition result is True")  
  return True  


def apply_simple_defs(ctxt,logic):
  defs=ctxt["sentence_defs"]
  #debug_print("apply_simple_defs defs",defs)
  if not defs: return logic
  simpledefs={}
  for el in defs:
    if simple_definition(ctxt,el):
      tmp=el[2][0][0]
      simpledefs[tmp]=el
  if not simpledefs: return logic
  res=apply_simple_defs_aux(ctxt,simpledefs,logic)
  #debug_print("apply_simple_defs res",res)
  return res

def apply_simple_defs_aux(ctxt,simpledefs,lst):
  if not lst: return lst
  if type(lst)!=list: return lst
  if type(lst[0])==str and lst[0] in simpledefs:
    term=apply_simple_definition(ctxt,simpledefs[lst[0]],lst[1])
    return term
  res=[]
  for lel in lst:
    tmp=apply_simple_defs_aux(ctxt,simpledefs,lel)
    res.append(tmp)
  return res

def apply_simple_definition(ctxt,logic,arg):
  logic=logic[2]
  head=logic[0]
  body=logic[2]
  res=logic_replace_el(body,head[1],arg)
  return res

# ===== sort logic expression ======

def sort_logic(ctxt,logic):
  if not logic: return logic
  if type(logic)!=list: return logic
  if logic[0]!="and": return logic
  tmp=sorted(logic[1:])
  res=["and"]+tmp
  return res


# === finding an existing object to match a word ===

def make_determined_constant(ctxt,sentence,word,det,tmp_logic,verb=None):  
  #debug_print("*** make_determined_constant word",word)
  #debug_print("make_determined_constant det",det)
  #debug_print("make_determined_constant objects",ctxt["objects"])
  #debug_print("make_determined_constant tmp_logic",tmp_logic)
  #debug_print("make_determined_constant sentence_defs",ctxt["sentence_defs"])  
  const=None
  if (type(word)==dict and nlpproperlogic.is_measure_unit(ctxt,word["lemma"]) and 
        word_has_child_in_deprel_upos(ctxt,sentence,word,["nummod"],["NUM"])):
    #debug_print("to create a measure word",word)
    #if ctxt["addctxt"]:
    #  ctxtargument=nlpproperlogic.make_ctxt_argument(ctxt,sentence,verb)
    #else:
    #  ctxtargument=None   
    value=word_has_child_in_deprel_upos(ctxt,sentence,word,["nummod"],["NUM"])       
    term=value["lemma"] #[measure_function+"1",word["lemma"],value,word["lemma"]]   
    try:
      num=int(term)
    except:
      try: num=float(term)  
      except: num=term  
    #debug_print("measure object num",num)    
    return num
  elif type(word)==dict and "argument" in word:
    argument=word["argument"]
    argument_det=get_word_det(ctxt,sentence,argument)
    #debug_print("argument",argument)
    #debug_print("argument_det",argument_det)       
    # assume a concrete argument and a concrete function
    if (det and det["lemma"] in ["the"]):
      #debug_print("concrete argument-having object argument",argument)
      argument_logic=make_argument_logic(ctxt,word,argument,tmp_logic)
      #debug_print("concrete argument-having object argument_logic",argument_logic)      
      argconst_tst=find_make_constant(ctxt,sentence,argument,False,True,argument_logic,word)
      #debug_print("make_determined_constant created theof-term argconst_tst",argconst_tst)
      argconst=argconst_tst
      term=make_the_or_measure_term(ctxt,sentence,word,argconst,verb) 
      #debug_print("term",term)  
      return term 
    elif word["lemma"] in measure_words:
      argconst=find_make_constant(ctxt,sentence,argument,False,True,None)
      #argconst=find_make_constant(ctxt,sentence,argument,False,True,tmp_logic)
      term=make_the_or_measure_term(ctxt,sentence,word,argconst,verb)
      return term
    else:
      #debug_print("Error: calling make_determined_constant on a non-concrete function")
      return False   
  if type(word)==dict and "ner" in word and word["ner"] in ["S-DATE"]:
    argconst=find_make_constant(ctxt,sentence,word,True,True,None)
    return argconst
  if det and det["lemma"] in ["a","an","another"]:    
    #debug_print("cpz")
    oldconst=word_ctxt_object_const(ctxt,sentence,word,tmp_logic)
    #debug_print("oldconst")
    if oldconst:
      const=oldconst
    else:
      const=make_constant(ctxt,word)      
      if det: const=det_constant_prefix+const 

    if tmp_logic: 
      tmp_logic=logic_replace_el(tmp_logic,dummysubject,const)
      tmp_logic=apply_simple_defs(ctxt,tmp_logic)
      #debug_print("update_ctxt_objects flogic1",flogic)
      tmp_logic=prop_flatten_logic_term(tmp_logic)

    if ("nosaveconstant" in ctxt and ctxt["nosaveconstant"]):
      None
    elif oldconst:
      update_ctxt_objects(ctxt,oldconst,word,tmp_logic)
    else:
      if True: #"argument" not in word:
        if "objects" in ctxt:      
          ctxt["objects"].append([const,word,tmp_logic])
        else:
          ctxt["objects"]=[[const,word,tmp_logic]]            
  elif det and det["lemma"] in ["the"]:
    const=find_make_constant(ctxt,sentence,word,False,True,tmp_logic) 
  else:
    const=find_make_constant(ctxt,sentence,word,False,True,tmp_logic)    
  if not const:
    print("Error: make_determined_constant got unknown det: "+str(det))
    sys.exit(0)  
  return const  

def make_argument_logic(ctxt,word,argument,logic):
  if not logic or type(logic)!=list: return logic
  res1=[]
  obj=None
  for el in logic:
    if type(el)!=list: res1.append(el)
    if el[0] not in ["isa","-isa","prop","-prop"]: continue
    if word["lemma"] in el[1:]: continue
    res1.append(el)
    if el[0] in ["isa"]: obj=el[2]
  if not obj or not res1:
    return res1  
  # "John saw the blue head of the red elephant. John saw the blue head of the red elephant?"
  res2=[]
  for el in res1:
    if type(el)!=list: res2.append(el)
    if el[0] in ["prop","-prop"]:
      if el[2]!=obj: continue
    res2.append(el)
  return res2


def make_the_or_measure_term(ctxt,sentence,word,argrepr,verb,tmp_isquestion=False):
  #debug_print("*** make_the_or_measure_term object",word)
  #debug_print("make_the_or_measure_term verb",verb)
  #debug_print("make_the_or_measure_term argrepr",argrepr)
  #debug_print("make_the_or_measure_term ctxt",ctxt)
  parent=get_parent(sentence,word)
  if ctxt["addctxt"]:
    ctxtargument=nlpproperlogic.make_ctxt_argument(ctxt,sentence,verb)
  else:
    ctxtargument=None       
  if word["lemma"] not in measure_words or not parent:
    term=[theof_function+"1",word["lemma"],argrepr]
    if ctxtargument: term.append(ctxtargument)
    return term
  if tmp_isquestion or ("isquestion" in ctxt and ctxt["isquestion"]):
    unit=unit_var_prefix
  else:        
    unit=generic_value
  mword=measure_words[word["lemma"]]  
  if parent["upos"] in ["NOUN"] and parent["lemma"] in mword["units"]:
    unit=parent["lemma"]
  term=[measure_function+"1",word["lemma"],argrepr,unit]  
  if ctxtargument: term.append(ctxtargument)
  #debug_print("+++ make_the_or_measure_term resulting term",term)
  return term

def is_theof_or_measure_function(s):
  if type(s)==str and (s.startswith(theof_function) or s.startswith(measure_function)):
    return True
  else:
    return False

def word_ctxt_object_const(ctxt,sentence,word,logic):
  #debug_print("word",word)
  if "objects" not in ctxt: return None
  ctxtobjects=ctxt["objects"]
  # first try to find an exact same word in sentence
  for object in ctxtobjects:
    #debug_print("object",object)
    if object[1]==word: return object[0]
  return None  

# Given: Big Mick is a furry red cat. Small Mick is a mouse. 
# Determine: It likes cheese / Mick likes cheese / Big Mick likes fish.

# ctxt is {"logic":..., "objects": ...} from previous sentences
# sentence is the ud of the current sentence
# noun is the ud representation of the investigated word in the current sentence
#
# return a constant if a good match is found, None otherwise


def find_make_constant(ctxt,sentence,word,strictness=False,det=False,logic=None,functionword=None):
  #debug_print("find_make_constant ctxt ",ctxt)
  #debug_print("find_make_constant word ",word)
  #debug_print("find_make_constant logic ",logic)
  #debug_print("find_make_constant functionword ",functionword)
  object=find_existing_object(ctxt,sentence,word,logic,functionword)
  #debug_print("find_make_constant got existing object ",object)
  if object:
    return object[0]  
  else:
    names=[word["lemma"]]    
    compoundlst=[word["lemma"]]
    children=get_children(sentence,word)
    for el in children:
      if el["deprel"] in ["flat"] and "ner" in el:
        names.append(el["lemma"])
        compoundlst.append(el["lemma"])
    if len(compoundlst)>1:
      names.append(" ".join(compoundlst))
    if "ner" in word and word["ner"] in ["S-DATE"]:
      const=make_datetime_constant(ctxt,word)
    else:
      const=make_constant(ctxt,word)
    if det and type(const)!=list: 
      const=det_constant_prefix+const
    if logic: 
      logic=logic_replace_el(logic,dummysubject,const)
      logic=apply_simple_defs(ctxt,logic)
      #debug_print("update_ctxt_objects flogic1",flogic)
      logic=prop_flatten_logic_term(logic)
      #debug_print("const",const)

    occurrences=[]  
    if ("nosaveconstant" in ctxt and ctxt["nosaveconstant"]):
      None
    else:  
      if "objects" in ctxt:      
        ctxt["objects"].append([const,word,logic,names,occurrences])
      else:
        ctxt["objects"]=[[const,word,logic,names,occurrences]]  
  return const

def make_datetime_constant(ctxt,word):
  #debug_print("word",word)
  if word["lemma"].isnumeric():
    const=[time_function,year_type_argument,word["lemma"]]
  else:
    const=[time_function,generic_value,word["lemma"]]  
  return const



def find_existing_object(ctxt,sentence,word,logic=None,functionword=None):
  #debug_print("find_existing_object word",word)
  #debug_print("find_existing_object ctxt",ctxt)
  #debug_print("find_existing_object logic",logic)
  #debug_print("find_existing_object functionword",functionword)
  if not ("objects" in ctxt): return None
  ctxtobjects=ctxt["objects"]
  # first try to find an exact same word in sentence
  for object in reversed(ctxtobjects):
    if (object[1]==word and 
        (not("ner" in word) or word["ner"] in [0,"0","O"])):
      #debug_print("find_existing_object direct found",object)
      return object   
  # next try to find a match
  children=get_children(sentence,word)  
  for object in reversed(ctxtobjects):
    #debug_print("object",object)
    if not logic:
      if word_matches_object(ctxt,sentence,word,object,children):          
        return object    
    elif not object[2]:
       if word_matches_object(ctxt,sentence,word,object,children): 
        return object 
    elif (type(object[0])==list or type(object[0])==str) and dummysubject in object[0]:
      continue
    #elif dummysubject in object[0]:
    #  continue
    elif ((not is_var(object[0])) or 
          (object[1]["sentence_nr"]==word["sentence_nr"])):
      if (functionword and type(object[0])==list and object[0][0] in ["$theof1"] and 
          object[0][0]!=word["lemma"]): 
        continue
      if is_subset_of_context_logic(ctxt,logic,object[0],object[2]):   
        return object        
  return None    

def word_matches_object(ctxt,sentence,word,object,wordchildren): 
  #debug_print("word_matches_object word",word)
  #debug_print("word_matches_object object",object)
  #debug_print("word_matches_object wordchildren",wordchildren)
  if len(object)<4: 
    if word["lemma"]==object[1]["lemma"]: return True
    else: return False  
  foundone=False  
  for name in object[3]:
    if name==word["lemma"]: 
      foundone=True
      break
  if not foundone: return False
  for child in wordchildren:     
    if child["deprel"] in ["flat"]:
      if not child["lemma"] in object[3]:
        return False        
  return True      
            

def is_subset_of_context_logic(ctxt,logic,context_constant,context_logic):
  #debug_print("!!is_subset_of_context_logic logic",logic)
  #debug_print("!!is_subset_of_context_logic context_constant",context_constant)
  #debug_print("is_subset_of_context_logic context_logic",context_logic)
  if not logic: return False
  if not context_logic: return False
  if type(logic)!=list or type(context_logic)!=list: return False

  #if type(context_constant)==list and context_constant[0] in ["$measure1","$theof1"]: return False
  if type(context_constant)==list and context_constant[0] in ["$measure1"]: return False

  #if (type(context_constant)==list and context_constant[0] in ["$theof1"] and
  #    context_constant[0][1]!=word
  #  return False

  if not (logic[0] in ["and","or"]): logic=["and",logic]
  if context_logic[0] in ["exists"] and type(context_logic[2])==list and context_logic[2][0]=="and":
    context_logic=context_logic[2]
  elif not (context_logic[0] in ["and","or"]): 
    context_logic=["and",context_logic]
  common=[] 
  for logel in logic:
    if logel in context_logic:   
      common.append(logel)
  l1=[]
  l2=[]
  #debug_print("common",common)
  for el in logic: 
    if el in common: None
    elif type(el)==list: l1.append(el)
    else: l1.append([el])
  for el in context_logic: 
    if el in common: None
    #elif el==dummypredicate: None
    elif type(el)==list: 
      if el[0]==dummypredicate: None  
      elif el[0] in ["isa","-isa","prop","-prop"] and el[2]!=context_constant:
        None
      else:
        l2.append(el)
    else: l2.append([el])  
  #debug_print("c1 l1",l1)
  #debug_print("c1 l2",l2)
  newl1=[]
  for el in l1:
    if el[0] in ["-isa"]:
      tmp=["isa"]+el[1:]
    else:
      tmp=el
    newl1.append(tmp)  
  newl2=[]
  for el in l2:
    if el[0] in ["-isa"]:
      tmp=["isa"]+el[1:]
    else:
      tmp=el
    newl2.append(tmp)   
  l1=newl1  
  l2=newl2
  
  #if False and common and len(common)>1 and (not l2) and l1:
  #  notfound=False
  #  for l1el in l1:
  #    if l1el not in logic:
  #      notfound=True
  #      break
  #  debug_print("notfound",notfound)  
  #  if not notfound: return True    
      
  l1=sorted(l1,key=lambda x: str(x))
  #debug_print("!! l2",l2)
  l2=sorted(l2,key=lambda x: str(x))
  #debug_print("c2 l1",l1)
  #debug_print("c2 l2",l2)
  for l1el in l1:
    if l1el[0].startswith(definition_prefix): continue
    found=False
    #debug_print("l1el",l1el)
    # first try to find without subclass check
    for l2el in l2:     
      #debug_print("l2el",l2el)            
      if l1el[0]!=l2el[0]: continue
      if len(l1el)<2: 
        found=True
        break
      #debug_print("l2el a",l2el)
      if len(l2el)>=2 and l1el[1]==l2el[1]:
        if (l2el[0]=="rel2" and l2el[1]=="have" and
            l2el[0]==l1el[0] and l2el[1]==l1el[1] and
            l2el[2]!=l1el[2]):
          pass
        else:
          found=True
          break     
    if not found:
      # try to find a subclass
      for l2el in l2:           
        if l1el[0]!=l2el[0]: continue        
        #debug_print("l2el b",l2el)
        if l2el[0]=="isa" and l1el[0]=="isa":
          if nlpprover.is_subclass(ctxt,l1el[1],l2el[1]):
            found=True
            break
      if not found:    
        return False
  #debug_print("True")      
  return True


def word_has_count(ctxt,sentence,word):
  children=get_children(sentence,word)
  for child in children:
    if child["deprel"]=="nummod":
      return True
  return False    
  
# ===== logic functions ========================

def make_logic_counted_function(ctxt,sentence,logic,objrepr,object,verb,subject,isobject=True,noplural=False):
  #debug_print("make_logic_counted_function logic",logic)
  #debug_print("make_logic_counted_function object",object)
  #debug_print("make_logic_counted_function subject",subject)
  if (not logic) or type(logic)!=list: 
    return None
  #if type(objrepr) in [int,float]:
  #  return None

  #object_det=get_word_det(ctxt,sentence,object) 
  children=get_children(sentence,object)
  if children:
    for child in children:
      if child["deprel"] in ["det","amod"] and child["upos"] in ["DET","ADJ"]:
        if child["lemma"] in ["all","every","each","any","some","few","most"]: return None
  logic=prop_flatten_logic_term(logic)
  if (not logic) or type(logic)!=list: 
    return None  
  if logic[0]=="and":
    loglst=logic[1:]
  elif logic[0] in ["or","xor"]:
    return None
  else:
    loglst=[logic]

  countatom=None
  res=["and"]
  term=None
  for el in loglst:
    if (not el) or len(el)<2: continue
    if type(el)!=list: continue
    if (el[0] in ["="]) and logic_contains_el(el,count_function):
      countatom=el
    elif type(el[0])==list:
      if len(el)==3 and el[1] in ["<~>","|","&","=>","<=>"]:
        newel=[el[1],el[0],el[2]]
        res.append(newel)
    else:
      res.append(el)
  if len(res)==1: 
    return None
  elif len(res)==2:
    term=res[1]
  else:
    term=res    
  term=logic_replace_el(term,objrepr,lambda_firstarg) 
  #debug_print("term",term)
  if term and term[0]=="and":
    term=["and"]+sorted(term[1:])

  #debug_print("countatom",countatom)
  if not countatom:
    if (verb and word_has_feat(verb,"Number","Sing") and
        object and object["upos"] in ["NOUN"] and word_has_feat(object,"Number","Plur")
        and not word_has_feat(subject,"Number","Plur")):
      #countatom=["$greatereq", ["$count",objrepr],2, ["$conf",0.9]]  
      children=get_children(sentence,object)
      for child in children:
        if (child["deprel"] in ["amod"] and child["upos"] in ["ADJ"]):
          if child["lemma"] in ["many"]:
            countatom1=["$greatereq", ["$count",objrepr],2]
            countatom2=["$greatereq", ["$count",objrepr],3, [confidence_function,0.9]]            
            #countatom3=["$greatereq", ["$count",objrepr],10, ["$conf",0.5]]
            countatom=["and",countatom1,countatom2]
            break
          if child["lemma"] in ["some","several"]: 
            countatom=["$greatereq", ["$count",objrepr],2]
            break
          if child["lemma"] in ["single"]: 
            countatom=["=", ["$count",objrepr],1]
            break
      if countatom:    
        None
      elif "isquestion" in ctxt and ctxt["isquestion"]:
        countatom=None
      elif not noplural:
        countatom=["$greatereq", ["$count",objrepr],2, [confidence_function,0.9]]

  return [countatom,term] 
  

# ====== logic building and conversion helpers ========

def make_constant(ctxt,word):
  res=constant_prefix+str(ctxt["skolem_nr"])+"_"+word["lemma"]
  ctxt["skolem_nr"]=ctxt["skolem_nr"]+1
  #constant_nr+=1
  return res

def make_constant_from_name(ctxt,name):
  res=constant_prefix+str(ctxt["skolem_nr"])+"_"+name
  ctxt["skolem_nr"]=ctxt["skolem_nr"]+1
  #constant_nr+=1
  return res

def make_population_constant(ctxt,atoms):
  #global constant_nr
  #debug_print("make_population_constant",atoms)
  res=""
  l=len(atoms)
  i=0
  for el in atoms:
    if el[0][0]=="-":
      res=res+"not_"+el[1]
    else:  
      res=res+el[1] 
    if el[0] in ["rel2","-rel2"]:
      tmp=el[3].split("_")
      if len(tmp)>1: tmp="_".join(tmp[1:])
      else: tmp=el[3]
      res=res+"_"+tmp
    i+=1
    if i<l: res+="_"
  res="some_"+res #str(constant_nr)
  #constant_nr+=1
  return res

def make_var(nr):
  res=var_prefix+str(nr)
  return res  

def is_negative_literal(lit):
  if type(lit)!=list: return False
  if type(lit[0])!=str: return False
  s=lit[0]
  if s[0]=="-": return True
  else: return False


def negate_literal(lit):
  if type(lit)!=list:
    show_error("literal "+str(lit)+" is not a list")
    sys.exit(0)
  if type(lit[0])!=str:
    show_error("predicate of a literal "+str(lit)+" is not a string")
    sys.exit(0)  
  s=lit[0]
  if s[0]=="-": s=s[1:]
  else: s="-"+s
  return [s]+lit[1:]


def make_term_from_preterm(sentence,preterm,replacements=None):
  if not preterm: return preterm
  if type(preterm)==list:
    res=[]
    for el in preterm:
      res.append(make_term_from_preterm(sentence,el,replacements))
    return res  
  elif type(preterm)==dict:
    return preterm["lemma"] 
  elif type(preterm)==str and replacements:
    for key in replacements:
      if key in preterm:
        return replacements[key]     
    return preterm    
  else:
    return preterm



# =========== the end ==========
