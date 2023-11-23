# The proper logic converter parts of nlpsolver, used by nlptologic
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

from nlpobjlogic import *

import nlptologic
#from nlptologic import build_property_logic

# ======= globals used and changed during work ===

#constant_nr=0 # new constants created add a numeric suffic, incremented
definition_nr=0 # new definitions created add a numeric suffic, incremented

noframes=False # set True for debugging: no new frames generated, no frame vars
noframevars=False # if true, instead of framevar we use number 1
nonewframes=False # if true, no new frames generated

# ===== tips for development =====


# =============== proper logic building ================================


def build_sentence_proper_logic(ctxt,sentence,tree,iscondition=False,isconsequence=False,confidence=1):
  #debug_print("build_sentence_proper_logic tree",tree)
  if not tree: return tree
  if type(tree)==str: return tree
  if type(tree)==dict: return tree
  if type(tree[0])==dict: return tree
  if tree[0] in ["svo","sv"]:
    treeroot=tree[1][0]
    parent=get_parent(sentence,treeroot)
    if parent:
      confidence=get_subsentence_confidence(ctxt,sentence,parent)
      #debug_print("build_sentence_proper_logic confidence",confidence) 
      if confidence==0:
        return None 
        
    sentlogic=build_single_subsentence_proper_logic(ctxt,sentence,tree,iscondition,isconsequence,confidence,None)  
    sentlogic=merge_framevars(sentlogic)  
    #debug_print("build_sentence_proper_logic sentlogic",sentlogic) 
    #debug_print("build_sentence_proper_logic ctxt",ctxt) 
    return sentlogic
   
  elif tree[0] in ["ref"]:
    ref=tree[1][1:]
    #debug_print("ref",ref)
    sys.exit(0) 
  elif tree[0] in ["if"]:
    res=[tree[0]]
    ctxt["isrule"]=True
    tmp1=build_sentence_proper_logic(ctxt,sentence,tree[1],True,False)
    tmp2=build_sentence_proper_logic(ctxt,sentence,tree[2],False,True)
    
    #debug_print("tmp1",tmp1)  
    #debug_print("tmp2",tmp2)      

    tmp1=remove_logic_annotations(tmp1)
    tmp1=prop_flatten_logic_term(tmp1)
    tmp2=remove_logic_annotations(tmp2)  
    tmp2=prop_flatten_logic_term(tmp2)

    tmp1vars=collect_free_vars(tmp1)
    tmp2vars=collect_free_vars(tmp2)
    if tmp2vars and not tmp1vars and tmp1 and tmp1[0] in ["exists","forall"]:
      # "if some red elephant is big, it is nice"
      # not tmp1vars in order to not fire for "if person has a nice car, he is happy"
      tmp1=tmp1[2]
    elif not(tmp2vars) and tmp1vars:
      # "if rabbits are big, elephants are strong"
      # "if person has a nice car, he is happy"
      tmp1=["forall",tmp1vars,tmp1]

    #debug_print("tmp1 +",tmp1)  
    #debug_print("tmp2 +",tmp2)

    res=[tmp1,"=>",tmp2]
    #debug_print("res",res)  
    vars=collect_free_vars(res)
    #debug_print("vars",vars)    
    if vars:
      res=["forall",vars,res]  
    res=["logic",tree,res]    
    return res   
  elif tree[0] in ["and","or","if","unless","nor","xor", "seq"]:
    if tree[0] in ["if","unless"]:
      ctxt["isrule"]=True
    res=[tree[0]]
    for el in tree[1:]:
      tmp=build_sentence_proper_logic(ctxt,sentence,el,iscondition,isconsequence)
      res.append(tmp)
    res=prop_flatten_logic_term(res)  
    return res
  else:
    #res=prop_flatten_logic_term(res) 
    return tree      


def get_subsentence_confidence(ctxt,sentence,parent):
  #debug_print("get_subsentence_confidence parent",parent)
  if not parent: return 1
  polarity=1
  if parent["upos"] in ["ADJ"] and parent["lemma"] in ["false"]:
    polarity=-1    
    confidence=get_word_confidence(ctxt,sentence,parent) 
    confidence=polarity*confidence     
    polarity2=get_word_polarity(ctxt,sentence,parent)
    if not polarity2: confidence=-1*confidence
  elif parent["upos"] in ["ADJ"] and parent["lemma"] in ["true"]:
    polarity=1   
    confidence=get_word_confidence(ctxt,sentence,parent)    
    confidence=polarity*confidence
    polarity2=get_word_polarity(ctxt,sentence,parent)
    if not polarity2: confidence=-1*confidence 
  else:
    #confidence=1
    confidence=get_lemma_confidence(sentence,parent["lemma"])  
    if confidence!=1:
      polarity=get_word_polarity(ctxt,sentence,parent)
      if not polarity: confidence=-1*confidence 

  #debug_print("get_subsentence_confidence polarity",polarity)
  #debug_print("get_subsentence_confidence confidence",confidence)
  return confidence



def build_single_subsentence_proper_logic(ctxt,sentence,tree,
      iscondition=False,isconsequence=False,top_confidence=1,parent_object_pair=None):  
  #debug_print("build_single_subsentence_proper_logic tree",tree)
  #debug_print("parent_object_pair",parent_object_pair)
  #debug_print("ctxt[isquestion]",ctxt["isquestion"])
  #debug_print("build_single_subsentence_proper_logic parent_object_pair",parent_object_pair)
  #debug_print("ctxt[objects] at the beginning of build_single_subsentence_proper_logic",ctxt["objects"])
  #debug_print("-----------------------------------")
  #debug_print("build_single_subsentence_proper_logic top_confidence",top_confidence)
  #debug_print("build_single_subsentence_proper_logic iscondition",iscondition)

  svo=tree[1][1:]
  #debug_print("build_single_subsentence_proper_logic svo",svo)
  subjpart=svo[0]
  verbpart=svo[1]
  if len(svo)>2:  
    objpart=svo[2]
  else:
    objpart=None  
  #debug_print("verbpart",verbpart)
  verb=verbpart
  subj_logic=None
  if (type(verbpart)==dict and type(subjpart)==dict and 
      ("relatedobjects" in verbpart) and (subjpart["upos"] in ["PRON"]) and 
      subjpart["lemma"] in ["which","that","who","what"]):
    #John liked the forest which was bought by Mary.
    prev=get_previous_word(sentence,subjpart)
    if prev:
      for el in verbpart["relatedobjects"]:
        if (el["case"]["lemma"]=="by" and ("obj" in el)):
          # ... which was bought by Mary    
          #debug_print("reversed!")      
          objpart=prev
          subjpart=el["proplogic"]
          break

  object_data=None
  object=None
  object_quant=None
  svar=None
  subject_quantifier=None
  sentence_type=None
  relatedobject=None
  relation_word=None

  #debug_print("objpart",objpart)

  if (type(verb)==dict and verb["lemma"] in ["be"] and not "relation" in verb and
     "relatedobjects" in verb):     
    related=verb["relatedobjects"] 
    for el in related:
      if "case" in el and "proplogic" in el and el["case"]["lemma"] in ["of"]:
        # Elephants are afraid of mice
        sentence_type="is_of"
        relation_word=objpart
        relatedobject=el
        objpart=relatedobject["obj"]        
        break
  
  if objpart:
    #debug_print("build_single_subsentence_proper_logic objpart",objpart)
    object_data=make_object_data(ctxt,sentence,objpart)
    #debug_print("object_data",object_data)
    object=get_thing(objpart)
    objspecialvar=None
    objconst=None  
    object_det=get_word_det(ctxt,sentence,object)
    object_quant=get_word_quant(ctxt,sentence,object)

  #debug_print("object_quant",object_quant) 
  subject=get_thing(subjpart)
  subjspecialvar=None
  subjconst=None
  subjispronoun=False
  subjisparent=False
  subject_det=get_word_det(ctxt,sentence,subject)
  sargument=None

  if pronoun(ctxt,subject):
    #debug_print("subject is pronoun:",subject)
    if not subject["lemma"] in ["who","that","whom","which"]:
      tmp=resolve_pronoun(ctxt,sentence,subject,tree,verb,object)
    else:
      tmp=None  
    #debug_print("subject resolved to tmp:",tmp)
    if not tmp:
      if parent_object_pair:
        subjrepr=parent_object_pair[0]
        #subjispronoun=True # ??
        subjisparent=True
      else:  
        # She was in a room. She was in a room?
        # If she was cool, then she was nice.
        subjconst=find_make_constant(ctxt,sentence,subject)  
        subjrepr=subjconst
        subjispronoun=True
    else:    
      subject=tmp[1]
      subjrepr=tmp[0]
      subjispronoun=True
  elif subject and subject["lemma"]==unknownsubject:
    svar="?:"+subject["lemma"]
    subjspecialvar=svar   
    subjrepr=subjspecialvar
    subject_quantifier="exists"  
  elif subject and variable_shaped_lemma(subject["lemma"]):
    svar="?:"+subject["text"]
    subjspecialvar=svar   
    subjrepr=subjspecialvar  
  elif (subject and subject["upos"] in ["PROPN"] and 
        ("ner" not in subject or subject["ner"] not in ["NORP","S-NORP"])):
    #debug_print("subj is propn",subject)
    subjconst=find_make_constant(ctxt,sentence,subject)  
    subjrepr=subjconst
  elif is_concrete_thing(ctxt,sentence,subject,subject_det,verb,iscondition,isconsequence,isobject=False):
    if False:
      None
    else:      
      #ctxt["nosaveconstant"]=True
      if parent_object_pair:
        tmp_logic=make_obj_logic(ctxt,sentence,dummysubject,parent_object_pair[0],verbpart,subjpart,True) 
      else:
        tmp_logic=make_obj_logic(ctxt,sentence,dummysubject,dummysubject,verbpart,subjpart,True) 
      if tmp_logic and type(tmp_logic)==list and tmp_logic[0]=="not":
        tmp_logic=tmp_logic[1] 
      #debug_print("tmp_logic1",tmp_logic) 
      tmp_logic=prop_flatten_logic_term(tmp_logic)
      subjconst=make_determined_constant(ctxt,sentence,subject,subject_det,tmp_logic,verb)  
      subjrepr=subjconst   
      tmp_logic=logic_replace_el(tmp_logic,dummysubject,subjconst)
      #debug_print("tmp_logic 3",tmp_logic)  
      if subjconst:
        #debug_print("ctxt",ctxt)
        #debug_print("ctxt[objects]",ctxt["objects"])
        for el in ctxt["objects"]:
          if el[0]==subjconst:
            tmp=logic_replace_el(el[2],"?:X10",subjconst)
            el[2]=tmp
      #debug_print("tmp_logic 4",tmp_logic)      
      if ("argument" in subject) and type(subjrepr)==list and is_theof_or_measure_function(subjrepr[0]): 
        if tmp_logic:
          arg_logic=tmp_logic
          subj_logic=tmp_logic

        sargument=subject["argument"]
        #debug_print("subjrepr",subjrepr)        
        #debug_print("sargument",sargument)
             
  elif "argument" in subject:     
    svar=None
    sargument=subject["argument"]
    #debug_print("sargument 0",sargument)
    svar="?:S"+str(ctxt["varnum"])
    ctxt["varnum"]+=1

    #subjconst1=make_determined_constant(ctxt,sentence,subject,subject_det,None)
    #debug_print("subjconst1",subjconst1)    
    #subject_det=get_word_det(ctxt,sentence,subject)
    #debug_print("argument",sargument)
    #debug_print("subject_det",subject_det)       
    # assume a concrete argument and a concrete function
    #if (subject_det and subject_det["lemma"] in ["the"]):
      #debug_print("concrete argument-having object")
      #argconst=make_constant(ctxt,argument)
      #sargconst=find_make_constant(ctxt,sentence,sargument,False,True,None)
      #sterm=[theof_function+"1",subject["lemma"],sargconst] 
      #debug_print("created sterm",sterm)           
      #return term  

    tmp_logic=make_simple_obj_logic(ctxt,sentence,svar,subjpart,verbpart,subjpart,None) 
    if tmp_logic and type(tmp_logic)==list and tmp_logic[0]=="not":
      tmp_logic=tmp_logic[1] 
    #debug_print("tmp_logic1",tmp_logic) 
    tmp_logic=prop_flatten_logic_term(tmp_logic)  
    subjrepr=svar  
    subj_logic=tmp_logic
    #debug_print("subj_logic alternative",subj_logic)
    if subjrepr:
      #debug_print("ctxt",ctxt)
      #debug_print("ctxt[objects]",ctxt["objects"])
       if not ctxt["isquestion"] and not ("nosaveconstant" in ctxt and ctxt["nosaveconstant"]):       
        for el in ctxt["objects"]:
          if el[0]==subjrepr:
            tmp=logic_replace_el(el[2],"?:X10",subjrepr)
            el[2]=tmp          
  else:
    #debug_print("cpy default case subject",subject)
    svar="?:S"+str(ctxt["varnum"])
    ctxt["varnum"]+=1
    subjrepr=svar        
  subject_quant=get_word_quant(ctxt,sentence,subject)  
  #debug_print("subject_quant",subject_quant) 
  #debug_print("cp subjrepr",subjrepr) 

  # maybe the same subject already exists?
  if (subject and ("passed_words" in ctxt) and
     subject["upos"] in ["NOUN"]): 
    #debug_print("cpz subject",subject) 
    #debug_print("cpz ctxt[passed_words]",ctxt["passed_words"])
    for el in ctxt["passed_words"]:
      if el[1]==subject:
        subjrepr=el[0]
        break
 
  if is_var(subjrepr):
    if (subject_quant and subject_quant["lemma"] in ["every","all","no"]):
      if not word_has_child_in_deprel_upos(ctxt,sentence,subject,["advmod"],["ADV"]):
        if object and word_has_child_in_deprel_upos(ctxt,sentence,object,["advmod"],["ADV"]):
          None
        else:  
          subjrepr=subjrepr+"_every"
  
  #debug_print(" ----------- subj_logic 00 ----------",subj_logic)
  #debug_print("sargument",sargument)
  #debug_print("svar",svar)
  if subjispronoun or subjisparent:
    subj_logic=True
  elif sargument: # and svar:
    None
  else:  
    subj_logic=make_obj_logic(ctxt,sentence,subjrepr,subjrepr,verbpart,subjpart,True)
    if subj_logic and type(subj_logic)==list and subj_logic[0]=="not":
      subj_logic=subj_logic[1] 

  #debug_print("subj_logic 0",subj_logic)
  subj_logic=prop_flatten_logic_term(subj_logic)
  subjvars=collect_free_vars(subj_logic)   
  
  if ctxt["isquestion"] and subject_det and subject_det["lemma"] in ["a"]:
    # Change of "a" into "some" for question if the kind of object is present in ctxt
    # "The red square has a nail. The blue square has a hole. A square has a nail?"
    oldobject=find_existing_object(ctxt,sentence,subject,subj_logic)
    #debug_print("subj_logic",subj_logic)
    #debug_print("oldobject",oldobject)
    if oldobject:
      subject_quantifier="exists"

  #debug_print("subj_logic 1",subj_logic)
  #debug_print("subj_logic svar",svar)
  #debug_print("subj_logic subjrepr",subjrepr)
  #debug_print("verb",verb)
  #debug_print("subj_logic subjvars",subjvars)
  #debug_print("subj_logic subjconst",subjconst)
 
  update_ctxt_objects(ctxt,subjconst,subject,subj_logic)
  #debug_print("ctxt x ctxt[objects]",ctxt["objects"])  
  #debug_print("subjrepr",subjrepr)
  #debug_print("objpart 2",objpart)

  # - - - - - verb is be - - - - - -

  if type(verb)==dict and verb["lemma"] in ["be"] and not "relation" in verb and sentence_type!="is_of":
    #debug_print("be-sentence")
    var=subjrepr #"?:X"
    objrepr=subjrepr
    if subjspecialvar: var=subjspecialvar       
    if (subject_quant and subject_quant["lemma"] in ["no","zero"] and
        (not(object_quant) or not(object_quant["lemma"] in ["no","zero"]))): reversepolarity=True
    else: reversepolarity=False
    subj_quant_confidence=get_word_quantor_confidence(ctxt,sentence,subject)
    subj_confidence=top_confidence*subj_quant_confidence  
    if subj_confidence==0: return None
    elif subj_confidence<0: reversepolarity=not reversepolarity
    if subj_confidence==0:
      return None  
    #debug_print("checkpoint a subjrepr",subjrepr)  
    #debug_print("checkpoint a subj_logic",subj_logic)
    #debug_print("checkpoint a subj_confidence",subj_confidence)
    #debug_print("checkpoint a objpart",objpart)
    #debug_print("checkpoint a object_data",object_data)
    obj_logic=make_obj_data_logic(ctxt,sentence,var,subjpart,verbpart,objpart,object_data,False,False,reversepolarity,[abs(subj_confidence),True],subjrepr)
    #debug_print("checkpoint b obj_logic",obj_logic)
    framevars=collect_frame_vars(obj_logic)
    #debug_print("checkpoint b framevars",framevars)
    if framevars:
      obj_logic=merge_known_framevars(obj_logic,framevars)
      framevars=[framevars[0]]
      if type(obj_logic)==list and obj_logic[0]=="not": 
        obj_logic=["not",["exists",framevars,obj_logic[1]]]  
      else:
        obj_logic=["exists",framevars,obj_logic]  
    #debug_print("checkpoint c obj_logic",obj_logic)
    #debug_print("subject 0",subject)
    #debug_print("subject_det 0",subject_det)
    #debug_print("subject_quant 0",subject_quant)
    #debug_print("subject_quantifier subjrepr",[subject_quantifier,subjrepr])
    
    if not(subjispronoun) and subject_quant and subject_quant["lemma"] in ["some","exist"]:
      quantifier="exists"
      logic=["logic",tree,[quantifier,[var],["and",subj_logic,obj_logic]]]
    elif not(subjispronoun) and subject_quant and subject_quant["lemma"] in ["all","every"]:
      quantifier="forall"
      if subject_quant["lemma"] in ["all"] and type(obj_logic)==list and obj_logic[0]=="not":
        logic=["logic",tree,["exists",[var],[subj_logic,"&",obj_logic]]]
      else:
        logic=["logic",tree,[quantifier,[var],[subj_logic,"=>",obj_logic]]]          
    elif (ctxt["isquestion"] and not(subjispronoun) and (not sargument) and
          subject["upos"]=="NOUN" and
          not subject_quant and subject_det and 
         subject_det["lemma"] in["a"]):
      quantifier="exists"      
      
      #logic=["logic",tree,[quantifier,[var],[subj_logic,"=>",obj_logic]]]    
      logic=["logic",tree,[quantifier,[var],[subj_logic,"&",obj_logic]]]

    elif iscondition and is_var(subjrepr):
      # hard case: if a bear is nice, it has a tail
      # but: if bears are nice, cars are red
      # both cases can be wrong 
      #debug_print("subject",subject)
      #debug_print("subject_det",subject_det)
      #debug_print("subject_quant",subject_quant)
      if (subject and not(subjispronoun) and word_has_feat(subject,"Number","Plur") and
          ((not subject_quant and not subject_det) or
           (subject_quant and subject_quant["lemma"] in ["all","every","each"]))):      
        quantifier="forall"
        logic=["logic",tree,[quantifier,[var],[subj_logic,"=>",obj_logic]]]        
        #debug_print("logic x",logic)
      else:
        logic=["logic",tree,["and",subj_logic,obj_logic]]  
    elif subjispronoun:
      #debug_print("checkpoint subjispronoun",subjispronoun)
      logic=["logic",tree,obj_logic]
      #logic=["logic",tree,["and",subj_logic,obj_logic]]
    elif subjspecialvar:
      logic=["logic",tree,[subj_logic,"=>",obj_logic]]
    elif not(subjispronoun) and subject_quant and subject_quant["lemma"] in ["some","exist"]:
      quantifier="exists"
      logic=["logic",tree,[quantifier,[var],["and",subj_logic,obj_logic]]]
    elif subjconst:
      #debug_print("checkpoint subj_logic",subj_logic)
      obj_logic=make_obj_logic(ctxt,sentence,subjconst,subjpart,verbpart,objpart,False,False,reversepolarity,abs(subj_confidence))    
      #debug_print("checkpoint c obj_logic",obj_logic)
      framevars=collect_frame_vars(obj_logic)
      #debug_print("checkpoint d framevars",framevars)
      if framevars:
        obj_logic=merge_known_framevars(obj_logic,framevars)
        framevars=[framevars[0]]
        if type(obj_logic)==list and obj_logic[0]=="not": 
          obj_logic=["not",["exists",framevars,obj_logic[1]]]  
        else:
          obj_logic=["exists",framevars,obj_logic]  
      #debug_print("checkpoint d obj_logic",obj_logic)     
      logic=["and",subj_logic,obj_logic]
      for fvar in subjvars:
        if fvar!=subjrepr and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
          logic=["exists",[fvar],logic] 
      logic=["logic",tree,logic]
      #debug_print("logic end 1",logic[2]) 
    elif sargument:     
      #debug_print("subject",subject)
      #debug_print("sargument",sargument)
      #debug_print("svar",svar)
      #debug_print("subjvars",subjvars)
      #debug_print("subj_confidence",subj_confidence)
      if svar:
        #debug_print("svar",svar)
        if ctxt["isquestion"] or (sargument and type(sargument)==dict and (subjispronoun or sargument["upos"]=="PROPN")):
          quantifier="exists"  
          logic=["logic",tree,[quantifier,[svar],["and",subj_logic,obj_logic]]] 
        else:
          quantifier="forall"  
          logic=["logic",tree,[quantifier,[svar],[subj_logic,"=>",obj_logic]]]      
      else:
        obj_logic=make_obj_logic(ctxt,sentence,subjrepr,subjpart,verbpart,objpart,False,False,reversepolarity,[abs(subj_confidence),True])    
        #debug_print("checkpoint d obj_logic",obj_logic)
        framevars=collect_frame_vars(obj_logic)
        #debug_print("checkpoint e framevars",framevars)
        if framevars:
          obj_logic=merge_known_framevars(obj_logic,framevars)
          framevars=[framevars[0]]
          if type(obj_logic)==list and obj_logic[0]=="not": 
            obj_logic=["not",["exists",framevars,obj_logic[1]]]  
          else:
            obj_logic=["exists",framevars,obj_logic]  
        
        logic=["logic",tree,["and",subj_logic,obj_logic]] 
        #debug_print("logic end 2",logic[2]) 
    elif not objpart:
      #debug_print("CP1!")
      quantifier="exists"  
      if ctxt["isquestion"]:
        logic=["logic",tree,[quantifier,[var],subj_logic]]
      else: 
        obj_logic=["isreal",var]
        logic=["logic",tree,[quantifier,[var],[subj_logic,"&",obj_logic]]]    
    else:
      #debug_print("CP2!")
      quantifier="forall"  
      logic=["logic",tree,[quantifier,[var],[subj_logic,"=>",obj_logic]]]
  
    #debug_print("obj_logic y",obj_logic)
    #debug_print("logic y",logic)
    #debug_print("ctxt[objects] a",ctxt["objects"])

    if subjrepr!=dummysubject:
      ctxt["passed_words"].append([subjrepr,subject,"subject"])
    if objrepr!=dummysubject:  
      ctxt["passed_words"].append([objrepr,object,"object"])
    if ((not ctxt["isquestion"]) and (not iscondition) and (not isconsequence) and
         subjrepr and not is_var(subjrepr)):
      update_ctxt_objects(ctxt,subjrepr,subject,logic)

    logic=prop_flatten_logic_term(logic)
    logic=simplify_quantors(logic)
    if iscondition: 
      logic=remove_confidence_annotations(ctxt,logic)  
      
    return logic  

  # - - - - - general case - - - - -
     
  elif type(verb)==dict:    
    
    #debug_print("general case")
    #debug_print("sentence_type",sentence_type)
    if sentence_type=="is_of": 
      # Elephants are afraid of mice
      object_data=make_object_data(ctxt,sentence,relatedobject["obj"])
      #debug_print("object_data",object_data)
    elif verb["lemma"] in ["have"]: sentence_type="has"
    elif "relation" in verb and verb["relation"]: sentence_type="verb_relation"
    else:  sentence_type=None
    #debug_print("sentence_type",sentence_type)
    
    if sentence_type=="is_of":
      verb_is_positive=get_word_polarity(ctxt,sentence,relation_word)      
    elif sentence_type=="verb_relation":
      verb_is_positive=get_word_polarity(ctxt,sentence,verb)
    else:  
      verb_is_positive=get_word_polarity(ctxt,sentence,verb)
    
    verb_confidence=get_word_confidence(ctxt,sentence,verb) 
    orig_verb_confidence=verb_confidence 
    if verb_confidence==0: return None  
    elif verb_confidence<0: 
      verb_confidence=0-verb_confidence
      verb_is_positive=not verb_is_positive   
    #debug_print("verb_confidence abs",verb_confidence)     
    #debug_print("verb_is_positive",verb_is_positive)

    #debug_print("subject",subject)
    subj_quant_confidence=get_word_quantor_confidence(ctxt,sentence,subject)
    subj_confidence=top_confidence*subj_quant_confidence    
    if subj_confidence==0: return None  
    elif subj_confidence<0: verb_is_positive=not verb_is_positive  
    obj_quant_confidence=1

    if verb_in_past(ctxt,sentence,verb): # word_has_feat(verb,"Tense","Past"):
      verb_is_past=True
    else: 
      verb_is_past=False      
    
    #debug_print("subject_quant",subject_quant)
    #debug_print("subject_quantifier 1",subject_quantifier)
    if subject_quantifier:
      None
    elif subject_quant and subject_quant["lemma"] in ["some","exists"]:
      subject_quantifier="exists"
    elif subject_quant and subject_quant["lemma"] in ["no","zero"]:
      subject_quantifier="forall" 
      verb_is_positive=not verb_is_positive 
    elif ctxt["isquestion"] and verb_is_past and not ("?:" in subjrepr and "_every" in subjrepr):
      subject_quantifier="exists"
    elif iscondition:
      # "If a person needs John, they are nice." 
      if (subject and not(subjispronoun) and word_has_feat(subject,"Number","Plur") and
          ((not subject_quant and not subject_det) or
           (subject_quant and subject_quant["lemma"] in ["all","every","each"]))):      
        subject_quantifier="forall"
      else:
        subject_quantifier="exists"   
    elif (verb["lemma"]=="be" and
          word_has_child_in_deprel_lemma(ctxt,sentence,verb,"expl",["there"])):
      # "There is a ghost in the room?"
      subject_quantifier="exists" 
    elif (verb["lemma"]=="be" and ("relation" in verb) and
          (verb["relation"] in is_location_relations)):          
      # "A ghost is in the room?"
      subject_quantifier="exists"  
    elif sargument and not svar:
      subject_quantifier=None  
    else:
      subject_quantifier="forall"  

    #debug_print("subject",subject)  
    #debug_print("subj_logic",subj_logic)     
    #debug_print("verb_is_positive",verb_is_positive)  
    #debug_print("verb",verb)
    #debug_print("subject_quantifier 2",subject_quantifier)
    #debug_print("object",object)
    obj_logic=None
    #debug_print("object_quant",object_quant)
    if object:
      if not(type(object_data)==list and object_data[0] in ["and","or","nor","xor"]):
        object_data=["single",object_data]
      if object_quant and object_quant["lemma"] in ["some"]:
        object_quantifier="exists"
      elif object_quant and object_quant["lemma"] in ["all","every","each","most"]:
        object_quantifier="forall" 
        if object_quant["lemma"] in ["most"]: obj_quant_confidence=0.9  
      elif (verb["lemma"] in like_type_verbs and
            (verb["lemma"] not in have_type_verbs) and 
            word_has_feat(verb,"VerbForm","Fin") and
            word_has_feat(subject,"Number","Plur") and
            word_has_feat(object,"Number","Plur") and
            not is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,
                    isobject=True)):
        #People like dogs
        #debug_print("cp1")
        object_quantifier="forall"  
        if obj_quant_confidence==1: obj_quant_confidence=0.95
      elif sentence_type=="is_of":
        #debug_print("cp2 is_of")
        object_quantifier="forall"
        if not is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,isobject=True):
          #debug_print("cp3 is_of")
          if obj_quant_confidence==1: obj_quant_confidence=0.95   
      elif (verb and verb["lemma"] in nlpglobals.abstract_verbs and object and 
            word_has_feat(object,"Number","Plur")):
           #(word_has_feat(object,"Number","Plur") or 
           # not is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,isobject=True))):
        # Mary hates dogs    
        object_quantifier="forall" 
      elif (verb and object and 
            word_has_feat(object,"Number","Plur") and
            ("relation" in verb) and verb["relation"] and
            subject_quantifier=="forall"):
           #(word_has_feat(object,"Number","Plur") or 
           # not is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,isobject=True))):
        # Mary hates dogs    
        object_quantifier="forall"   
      else:
        #debug_print("cpx")
        # Animals have legs
        # Nails are made of iron.
        object_quantifier="exists"   
        
    else:
      object_data=["single","$dummy_act_object"]    
      object_quantifier=None
      obj_logic=None
      objrepr=None
    
    #debug_print("object_quantifier",object_quantifier)
    #debug_print("object_data2",object_data)       
    
    if subjrepr!=dummysubject:
      ctxt["passed_words"].append([subjrepr,subject,"subject"])

    if type(object_data)==list and object_data[0] in ["single","and","or","nor","xor"]:      
      #debug_print("cp4")
      mainop=object_data[0]
      all_objects_logic=[mainop]      
      
      #debug_print("object_data",object_data)      
      #debug_print("all_objects_logic 1",all_objects_logic)
      
      for thisobject in object_data[1:]:
        #debug_print("thisobject",thisobject)
        if thisobject=="$dummy_act_object":
          None
        else:          
          objpart=thisobject["objpart"]
          #debug_print("thisobject",thisobject)
          #debug_print("parent_object_pair",parent_object_pair)
          #debug_print("iscondition",iscondition)
          #debug_print("isconsequence",isconsequence)
          #debug_print("subjpart",subjpart)
          #debug_print("verbpart",verbpart)
          #debug_print("objpart",objpart) 
          #debug_print("verb_is_positive",verb_is_positive)
          #debug_print("all_objects_logic",all_objects_logic)
          #debug_print("objpart",objpart)
          object=get_thing(objpart)
          #debug_print("object",object)          
          objspecialvar=None
          objconst=None  
          object_det=get_word_det(ctxt,sentence,object)
          #objispronoun=False        
          # prerefence of concreteness for objects in case of negation, like needed in:
          # ["John does not eat a carrot. John eats a carrot?",False],
          # ["John is not in a cave. John is in a cave?",False]
          tmp_obj_logic=None
          if ctxt["isquestion"]: prefer_non_concrete=True
          elif not verb_is_positive: prefer_non_concrete=True
          else:
            tmp_obj_logic=make_obj_logic(ctxt,sentence,dummysubject,subjpart,verbpart,objpart)
            if tmp_obj_logic and type(tmp_obj_logic)==list and tmp_obj_logic[0] in ["not"]:
              prefer_non_concrete=True
            else:
              prefer_non_concrete=False
            #debug_print("tmp_obj_logic",tmp_obj_logic)

          if parent_object_pair and object==parent_object_pair[1]:
            #John had a car which Eve bought
            #Bears who eat fish are strong
            objrepr=parent_object_pair[0] 
          elif pronoun(ctxt,object):
            tmp=resolve_pronoun(ctxt,sentence,object,tree,verb,subject)
            #debug_print("ctxt[objects] after resolve_pronoun of general handling",ctxt["objects"])
            if not tmp:
              print("error: cannot resolve pronoun, case 4",object)
              sys.exit(0)
              return None
            object=tmp[1]
            objrepr=tmp[0]
          elif object and type(object)==dict and variable_shaped_lemma(object["lemma"]):
            ovar="?:"+object["text"]
            objspecialvar=ovar 
            objrepr=objspecialvar
          elif object and type(object)==dict and object["upos"] in ["PROPN"]:
            objconst=find_make_constant(ctxt,sentence,object)
            objrepr=objconst
          elif  is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,
                  isobject=True,prefer_non_concrete=prefer_non_concrete):
            #debug_print("in main object is concrete", object)             
            if tmp_obj_logic:       
              tmp_logic=tmp_obj_logic
            else:  
              tmp_logic=make_obj_logic(ctxt,sentence,dummysubject,subjpart,verbpart,objpart) 
            #debug_print("tmp_logic 2",tmp_logic)  
            tmp_logic=prop_flatten_logic_term(tmp_logic) 
            objconst=make_determined_constant(ctxt,sentence,object,object_det,tmp_logic,verb)                    
            objrepr=objconst   
            tmp_logic=logic_replace_el(tmp_logic,dummysubject,objrepr)
            obj_logic=tmp_logic
            #debug_print("obj_logic 2",obj_logic)
            object_quantifier=None                               
          elif object_data and object_data[0]=="single" and object_data[1] and "objrepr" in object_data[1]:
            objrepr=object_data[1]["objrepr"]  
          else:
            ovar="?:O"+str(ctxt["varnum"])
            ctxt["varnum"]+=1
            objrepr=ovar  
          if parent_object_pair and objrepr==parent_object_pair[0]:
            object_quantifier=None          

        objvars=collect_free_vars(obj_logic) 
        if objrepr and type(objrepr)==list and is_theof_or_measure_function(objrepr[0]):
          argvar=objrepr[2]
        else:
          argvar=None  
        
        #debug_print("objvars",objvars)
        #debug_print("subjrepr",subjrepr)
        #debug_print("objrepr",objrepr)  
        #debug_print("argvar",argvar)
        #debug_print("obj_logic 1",obj_logic)

        for fvar in objvars:
          if fvar!=objrepr and fvar!=subjrepr and fvar!=argvar and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
            obj_logic=["exists",[fvar],obj_logic] 
        actionrepr="?:A"+str(ctxt["varnum"])
        ctxt["varnum"]+=1
        #debug_print("obj_logic 1a",obj_logic)
      
        if not objrepr:
          object_is_positive=True
        else:
          #debug_print("main objrepr before",objrepr)
          #debug_print("main obj_logic before",obj_logic)
          if type(objrepr)!=list:
            obj_logic=make_simple_obj_logic(ctxt,sentence,objrepr,subjpart,verbpart,objpart,actionrepr,orig_verb_confidence==1)
            #debug_print("obj_logic 1x",obj_logic)
          #obj_logic=make_simple_obj_logic(ctxt,sentence,objrepr,subjpart,verbpart,objpart,actionrepr)  
          objvars=collect_free_vars(obj_logic) 

          #debug_print("obj_logic 3",obj_logic)
          #debug_print("objvars2",objvars)
          #debug_print("objrepr",objrepr)  
          #debug_print("argvar",argvar)

          for fvar in objvars:
            if fvar!=objrepr and fvar!=subjrepr and fvar!=argvar and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
              obj_logic=["exists",[fvar],obj_logic]          
          #debug_print("obj_logic 4",obj_logic)    
          #debug_print("main obj_logic of general handling",obj_logic) 
          #debug_print("main ctxt[objects] after make_simple_obj_logic of general handling",ctxt["objects"])
          if obj_logic and type(obj_logic)==list and obj_logic[0]=="not":
            object_is_positive=False
            obj_logic=obj_logic[1]
          else:
            object_is_positive=True 

          if ((not ctxt["isquestion"]) and (not iscondition) and (not isconsequence) and
               objrepr):
            #debug_print("about to update_ctxt_objects in main, objects are")   
            #show_objects(ctxt)
            update_ctxt_objects(ctxt,objrepr,object,obj_logic)
            #debug_print("after update_ctxt_objects in main, objects are")   
            #show_objects(ctxt) 

        #debug_print("obj_logic",obj_logic)
        #debug_print("objrepr",objrepr)
        #debug_print("object",object)
        #debug_print("objpart",objpart)
        #debug_print("original_objpart",original_objpart)
        #debug_print("verb",verb)
        #debug_print("actionrepr",actionrepr)
        #debug_print("relation_word",relation_word)
        
        if ((verb and verb["lemma"] in nlpglobals.abstract_verbs) or
            (relation_word and relation_word["lemma"] in nlpglobals.abstract_verbs)):
          # "Mary likes mice"
          # "Mary is afraid of mice"
          obj_logic_function=None
        else:  
          obj_logic_function=make_logic_counted_function(ctxt,sentence,obj_logic,objrepr,
            object,verb,subject,isobject=True,noplural=(iscondition or not verb_is_positive))      
        #debug_print("obj_logic_function",obj_logic_function)
        #debug_print("subjrepr",subjrepr)
        #debug_print("objrepr",objrepr)
        if (obj_logic_function and obj_logic_function[0] and 
            not (type(subjrepr)==list and type(subjrepr[0])==str and subjrepr[0].startswith(measure_function))):
          substituted_function=apply_simple_defs(ctxt,obj_logic_function[1])
          sorted_substituted_function=sort_logic(ctxt,substituted_function)
          #objsetrepr=[set_function,obj_logic_function[1],subjrepr]
          objsetrepr=[set_function,sorted_substituted_function,subjrepr]
          countatom=logic_replace_el(obj_logic_function[0],objrepr,objsetrepr)
          #debug_print("objsetrepr 1",objsetrepr)
          #debug_print("substituted_function",substituted_function)
          #debug_print("sorted_substituted_function",sorted_substituted_function)
          #debug_print("countatom",countatom)
        else:
          objsetrepr=None  

        #debug_print("verb2",verb)
        confidence=get_word_confidence(ctxt,sentence,verb)  
        #debug_print("verb confidence2",confidence)
        if (not confidence or confidence==1): # and verb["lemma"] in ["be"]:
          confidence=get_word_confidence(ctxt,sentence,get_parent(sentence,verb)) 
        if confidence==0: return None
        elif confidence<0: confidence=abs(confidence)
        if abs(subj_confidence)==1:
          confidence=confidence*obj_quant_confidence
        else:
          confidence=abs(subj_confidence)*obj_quant_confidence

        #debug_print("relation",relation)        
        #debug_print("subj_confidence",subj_confidence)
        #debug_print("obj_quant_confidence",obj_quant_confidence)
        #debug_print("confidence 3",confidence)
      
        act_maintype=determine_act_main_type(ctxt,sentence,subject,verb,object)
        if objrepr:
          act_type=act_maintype+"2"
        else:
          act_type=act_maintype+"1"  

        action_prop_logic=make_action_prop_logic(ctxt,sentence,verb,actionrepr,subject,subjrepr,tree,verb_is_positive,subjconst)  
        #debug_print("created action_prop_logic",action_prop_logic)
        #debug_print("objsetrepr",objsetrepr)
        if objsetrepr:
          setrelation=make_atom_2(ctxt,sentence,verb,verb,True,subjrepr,objsetrepr,confidence,act_type,actionrepr)
        else:
          setrelation=None

        if sentence_type=="is_of":
          # Elephants are afraid of mice
          thingparam=relation_word
        else:
          thingparam=verb          
        if objrepr:          
          if subjrepr and is_var(subjrepr):
            relation=make_atom_2(ctxt,sentence,verb,thingparam,True,subjrepr,objrepr,confidence,act_type,actionrepr,blocker_preferred=True)
          else:
            relation=make_atom_2(ctxt,sentence,verb,thingparam,True,subjrepr,objrepr,confidence,act_type,actionrepr)  
        else:
          relation=make_qualified_atom_1(ctxt,sentence,verb,thingparam,True,subjrepr,confidence,act_type,actionrepr,blocker_preferred=True)          
        #debug_print("relation after",relation)
        #debug_print("action_prop_logic",action_prop_logic)

        if action_prop_logic:
          relation=["exists",[actionrepr],["and",action_prop_logic,relation]]
        else:   
          relation=["exists",[actionrepr],relation]

        #debug_print("relation",relation)  
        #debug_print("verb_is_positive",verb_is_positive)
        #debug_print("object_is_positive",object_is_positive)
        #debug_print("objrepr",objrepr)  
        if not verb_is_positive:
          object_is_positive=not object_is_positive

        #debug_print("relation",relation)   
        framevars=collect_frame_vars(relation)
        relation=merge_known_framevars(relation,framevars)
        if framevars: framevars=[framevars[0]]
        if framevars and not ("isquestion" in ctxt and ctxt["isquestion"]):
          relation=["exists",framevars,relation]
        framevars=collect_frame_vars(setrelation)
        setrelation=merge_known_framevars(setrelation,framevars)
        if framevars: framevars=[framevars[0]]
        if framevars and not ("isquestion" in ctxt and ctxt["isquestion"]):
          setrelation=["exists",framevars,setrelation]  
 
        #debug_print("obj_logic",obj_logic)
        #debug_print("object_quantifier",object_quantifier)
        #debug_print("setrelation",setrelation)
        #if countatom: debug_print("countatom",countatom)

        if obj_logic==None:                   
          if setrelation:
            full_object_logic=["and",relation,setrelation]
          else:
            full_object_logic=relation          
        else:  
          if objsetrepr and countatom:
            obj_logic=["and",countatom,obj_logic]

          if object_quantifier=="exists":
            full_object_logic=[obj_logic,"&",relation]
          elif object_quantifier==None:
            full_object_logic=[obj_logic,"&",relation]  
          else:  
            full_object_logic=[obj_logic,"=>",relation]

          if not objspecialvar:
            if object_quantifier:              
              full_object_logic=[object_quantifier,[objrepr],full_object_logic]              
          if objrepr and type(objrepr)==list and is_theof_or_measure_function(objrepr[0]):
            quantvar=objrepr[2]             
            full_object_logic=["exists",[quantvar],full_object_logic]

          if objrepr!=dummysubject:     
            ctxt["passed_words"].append([objrepr,object,"object"])
        
        if subject_quantifier=="exists" and subjrepr and unknownsubject in subjrepr:
          # Colin is wounded
          #debug_print("subject_quantifier1 subjrepr",[subject_quantifier,subjrepr])              
          full_object_logic=["exists",[subjrepr],full_object_logic]
        if not object_is_positive:
          full_object_logic=["not",full_object_logic]            
        #debug_print("full_object_logic",full_object_logic)  
        all_objects_logic.append(full_object_logic)
        #debug_print("all_objects_logic 2",all_objects_logic)
        
    if all_objects_logic and all_objects_logic[0]=="single": 
      all_objects_logic=all_objects_logic[1]
     
    #debug_print("subj_logic",subj_logic)
    #debug_print("sargument",sargument)
    #debug_print("subjspecialvar",subjspecialvar)
    #debug_print("subjrepr",subjrepr)
    #debug_print("all_objects_logic 3",all_objects_logic)
    #debug_print("subject_quantifier subjrepr",[subject_quantifier,subjrepr])

    if sargument:
      if svar:
        #debug_print("is svar",svar)
        #quantifier="forall"  
        #res=["logic",tree,[quantifier,[svar],[subj_logic,"=>",all_objects_logic]]]     
        quantifier="exists"  
        logic=["and",subj_logic,all_objects_logic]
        for fvar in subjvars:
          if fvar!=subjrepr and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
            logic=["exists",[fvar],logic]
        res=["logic",tree,[quantifier,[svar],logic]] 
      else:
        #debug_print("not svar")
        reversepolarity=False
        obj_logic=make_obj_logic(ctxt,sentence,subjrepr,subjpart,verbpart,objpart,False,False,reversepolarity,abs(subj_confidence))    
        logic=["and",subj_logic,all_objects_logic]
        for fvar in subjvars:
          if fvar!=subjrepr and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
            logic=["exists",[fvar],logic]
        for fvar in subjvars:
          if fvar!=subjrepr and (not is_keep_free_var(ctxt,fvar)): # and (not svar or fvar!=svar):
            logic=["exists",[fvar],logic]     
        res=["logic",tree,logic]  
    elif not subjspecialvar: 
      if subject_quantifier=="exists": # and (not ctxt["isquestion"]):
        res=[subject_quantifier,[subjrepr],["and",subj_logic,all_objects_logic]]        
      elif iscondition or subjispronoun: # or ctxt["isquestion"]:          
        if (subject_quantifier=="forall" and subject and not(subjispronoun) and word_has_feat(subject,"Number","Plur") and
            ((not subject_quant and not subject_det) or
            (subject_quant and subject_quant["lemma"] in ["all","every","each"]))):
          quantifier="forall"
          res=[subj_logic,"=>",all_objects_logic]
        else:
          res=["and",subj_logic,all_objects_logic]
      elif subjconst: 
        res=["and",subj_logic,all_objects_logic]  
      else:  
        res=[subject_quantifier,[subjrepr],[subj_logic,"=>",all_objects_logic]]    
    elif subject_quantifier=="exists" and subjrepr and unknownsubject in subjrepr:
      # Colin is wounded
      quantifier="exists"   
      res=["logic",tree,all_objects_logic] 
    else:  
      res=[subj_logic,"=>",all_objects_logic]
   
    res=prop_flatten_logic_term(res)
    logic=simplify_quantors(res)
    if iscondition: 
      logic=remove_confidence_annotations(ctxt,res)
    #debug_print("general case returns logic",logic)  
    return logic


def is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,isobject=False,prefer_non_concrete=False):
  #debug_print("is_concrete_thing object iscondition isconsequence",[object,iscondition,isconsequence])
  #debug_print("is_concrete_thing verb",verb)
  #debug_print("is_concrete_thing object_det",object_det)
  #debug_print("is_concrete_thing isobject",isobject)
  #debug_print("is_concrete_thing prefer_non_concrete",prefer_non_concrete)
  if not object: return False

  #if object["lemma"] in ["woman"]: return False

  if type(object)==dict and "argument" in object:
    argument=object["argument"]
    argument_det=get_word_det(ctxt,sentence,argument)
    #debug_print("argument",argument)
    #debug_print("argument_det",argument_det)
    is_concrete_argument=is_concrete_thing(ctxt,sentence,argument,argument_det,
      verb,iscondition,isconsequence,isobject,prefer_non_concrete=prefer_non_concrete) 
    #debug_print("is_concrete_argument", is_concrete_argument)    
    if is_concrete_argument and (object_det and object_det["lemma"] in ["the"]):
      #debug_print("concrete argument-having object v1")
      return True
    elif is_concrete_argument and (object["upos"] in ["NOUN"] and object["lemma"] in measure_words):
      #debug_print("concrete argument-having object v2")
      return True  
    elif ((object["lemma"] in measure_words) and
          "preposition" in argument and argument["preposition"] in ["'s"]):
      #debug_print("concrete argument-having object v3")
      return True  
    else:
      #debug_print("non-concrete argument-having object")
      return False
  if (type(object)==dict and 
        ((object["upos"] in ["PROPN"] and ("ner" not in object or object["ner"] not in ["NORP","S-NORP"])) or 
         (ctxt["isquestion"] and object["lemma"] in ["whom","who","what"]))):
      # also "Whom is Ellen afraid of?" where whom is pron, while "who" would be propn   
    return True
  #elif (type(object)==dict and         
  #       (ctxt["isquestion"] and object["lemma"] in ["whom","who","what"])):
  #    # also "Whom is Ellen afraid of?" where whom is pron, while "who" would be propn 
  #  debug_print("cpz object",object)   
  #  return False 
  elif (type(object)==dict and is_measure_unit(ctxt,object["lemma"]) and 
        word_has_child_in_deprel_upos(ctxt,sentence,object,["nummod"],["NUM"])):
     #debug_print("found measure object",object)   
     return True
  elif not object_det: 
    #debug_print("no object_det")    
    if object["upos"] in ["NOUN"] and verb and verb_in_past(ctxt,sentence,verb):
      # Nails are made of metal
      if ("be" in verb) and not verb_in_past(ctxt,sentence,verb["be"]):
        return False
      #elif prefer_non_concrete:
      #  return False  
      else:  
        return True
    #elif verb and verb["lemma"] in ["be"]:
    #  return     
    elif type(object)==dict and "ner" in object and object["ner"] in ["S-DATE"]:
      return True
    else: 
      return False  
  if ((iscondition or isconsequence or ctxt["isquestion"]) and object_det and object_det["lemma"] in ["the"]):      
     # the (iscondition or or ctxt["isquestion"]) prohibits OK answer to:  
     #  "John is a man Mary liked. Mary liked the man?"
     # initially for general case object we had: not ctxt["isquestion"]:
    return True
  else:
    if isobject and verb and verb["lemma"] in ["have"]:
      if ((not (iscondition or isconsequence or ctxt["isquestion"])) and object_det["lemma"] in ["the"]) :
        if find_existing_object(ctxt,sentence,object):
          return True 
        else:
          return False  
    elif ((not (iscondition or isconsequence or ctxt["isquestion"])) and object_det["lemma"] in ["a","an","another","the"]) :  
      if prefer_non_concrete:
        if object_det["lemma"] in ["a","an"]:
          return False
        else:
          return True     
      else:
        return True
  return False    

def is_measure_unit(ctxt,lemma):
  #debug_print("lemma",lemma)
  for el in measure_words:
    if "units" in measure_words[el] and lemma in measure_words[el]["units"]:
      return True
  #debug_print("False",False)    
  return False


def determine_act_main_type(ctxt,sentence,subject,verb,object):
  #debug_print("determine_act_main_type subject verb object",[subject,verb,object])
  if has_aux_from_list(sentence,verb,["can"]):
    res="can"
  else:   
    subject_det=get_word_det(ctxt,sentence,subject) 
    if subject_det in ["the","a","an","this","these"]:
      res="act"
    elif word_has_feat(verb,"VerbForm","Inf"):       
      if (verb_in_past(ctxt,sentence,verb) or
          (("be" in verb) and (verb["be"]["lemma"]=="be"))):
          # The radio is working
        res="act"
      else: 
        res="do"        
    elif verb_in_past(ctxt,sentence,verb):    
      res="act"
    elif not (word_has_feat(verb,"Tense","Pres")):      
      res="act"
    else:
      res="do"   
 # debug_print("determine_act_main_type res",res)
  return res


def make_action_prop_logic(ctxt,sentence,verb,actionvar,subject,subjrepr,tree,verb_is_positive,subject_is_concrete):
  #debug_print("make_action_prop_logic starts ------------------")
  #debug_print("make_action_prop_logic verb",verb)
  #debug_print("make_action_prop_logic actionrepr",actionvar)
  #debug_print("make_action_prop_logic subject",subject)
  #debug_print("make_action_prop_logic subjrepr",subjrepr) 
  #debug_print("make_action_prop_logic subject_is_concrete",subject_is_concrete)
  
  if ("relation" in verb) and verb["relation"]: return None
  if verb["lemma"] in ["be"]: return None

  orig_isquestion=ctxt["isquestion"]
  #ctxt["isquestion"]=False

  andlist=[]
  listop="and"
  verbchildren=get_children(sentence,verb)
  for child in verbchildren:
    # Bears eat quickly.
    sublist=[]
    sublistop="and"
    proplogic=None
    if (((child["deprel"] in ["advmod"] and child["upos"] in ["ADV"]) or
         (child["deprel"] in ["xcomp"] and child["upos"] in ["ADJ"]))
        and
        not child["lemma"] in ["then"]):
      positive=True
      proplogic=make_simple_conj_logic(ctxt,sentence,child,actionvar)
      #debug_print("make_action_prop_logic proplogic0",proplogic)   

    if proplogic:      
      sublist.append(proplogic)
    if sublist:  
      sublist=[sublistop]+sublist
      andlist.append(sublist)
  if andlist:
    andlist=[listop]+andlist      
  #debug_print("action_prop_logic andlist 1",andlist)    
  
  sublist2=[]
  if "relatedobjects" in verb:
    #debug_print("CPXXXX relatedobjects found")
    relatedobjects=verb["relatedobjects"]
    for el in relatedobjects:
      # Bears eat in a forest      
      # check if relatedobject should be used
      # eliminate with-probability
      #debug_print("el",el) 
      if ("case" in el and el["case"]["lemma"] in ["with"] and
          "obj" in el):
        if el["obj"]["lemma"] in probability_words: continue
        has_probability=False
        for child in verbchildren:
          if child["deprel"] in ["obl"] and child["lemma"] in probability_words:
            has_probability=True
            break
        if has_probability and el["obj"]["lemma"] in ["percent"]: 
          continue       

      # ok, should be used

      positive=True
      actionobjectvar="?:AO"+str(ctxt["varnum"])
      ctxt["varnum"]+=1

      objpart=el["proplogic"]
      #debug_print("objpart",objpart)
      object_data=make_object_data(ctxt,sentence,objpart)
      #debug_print("object_data",object_data)
      object=get_thing(objpart)
      objspecialvar=None
      objconst=None  
      object_det=get_word_det(ctxt,sentence,object)
      object_quant=get_word_quant(ctxt,sentence,object)

      parent_object_pair=None
      iscondition=False
      isconsequence=False
      subjpart=None
      verbpart=verb

      #debug_print("object",object)
      #debug_print("parent_object_pair",parent_object_pair)
      objspecialvar=None
      objconst=None  
      object_det=get_word_det(ctxt,sentence,object)

      if object:
        if not(type(object_data)==list and object_data[0] in ["and","or","nor","xor"]):
          object_data=["single",object_data]
        if object_quant and object_quant["lemma"] in ["some"]:
          object_quantifier="exists"
        elif object_quant and object_quant["lemma"] in ["all","every","each"]: #,"most"]:
          object_quantifier="forall"  
        else:  
          object_quantifier="exists"  
      else:
        object_data=["single","$dummy_act_object"]    
        object_quantifier=None
        obj_logic=None
        objrepr=None
      #debug_print("object_data2",object_data)   
    
      prefernonconcrete=True
      if subject_is_concrete: prefernonconcrete=False

      if parent_object_pair and object==parent_object_pair[1]:
        #John had a car which Eve bought
        #Bears who eat fish are strong
        objrepr=parent_object_pair[0]
      elif pronoun(ctxt,object):
        tmp=resolve_pronoun(ctxt,sentence,object,tree,verb,subject)
        #debug_print("ctxt[objects] after resolve_pronoun of general handling",ctxt["objects"])
        if not tmp:
          print("error: cannot resolve pronoun, case 4",object)
          sys.exit(0)
          return None
        object=tmp[1]
        objrepr=tmp[0]
        #objispronoun=True
      elif object and type(object)==dict and variable_shaped_lemma(object["lemma"]):
        ovar="?:"+object["text"]
        objspecialvar=ovar 
        objrepr=objspecialvar
      elif object and type(object)==dict and object["upos"] in ["PROPN"]:
        objconst=find_make_constant(ctxt,sentence,object)
        objrepr=objconst
      elif is_concrete_thing(ctxt,sentence,object,object_det,verb,iscondition,isconsequence,isobject=True,prefer_non_concrete=True):                                
        tmp_logic=make_obj_logic(ctxt,sentence,dummysubject,subjpart,verbpart,objpart) 
        #debug_print("tmp_logic 0",tmp_logic)
        tmp_logic=prop_flatten_logic_term(tmp_logic)  
        #debug_print("object",object)
        #debug_print("object_det",object_det)
        #debug_print("tmp_logic",tmp_logic)
        objconst=make_determined_constant(ctxt,sentence,object,object_det,tmp_logic,verb)
        #debug_print("objconst",objconst)
        objrepr=objconst   
        object_quantifier=None       
      else:
        #debug_print("object is not concrete")         
        ovar="?:O"+str(ctxt["varnum"])
        ctxt["varnum"]+=1
        objrepr=ovar  
      if parent_object_pair and objrepr==parent_object_pair[0]:
        object_quantifier=None               
         
      actionrepr="?:A"+str(ctxt["varnum"])
      ctxt["varnum"]+=1
    
      if not objrepr:
        object_is_positive=True
      else:
        #debug_print("obj_logic1",obj_logic) 
        #debug_print("about to call obj_logic") 

        obj_logic=make_simple_obj_logic(ctxt,sentence,objrepr,subjpart,verbpart,objpart,actionrepr)
        #debug_print("ctxt[objects] after make_simple_obj_logic of general handling",ctxt["objects"])
        #debug_print("obj_logic of general handling",obj_logic) 
        if obj_logic and type(obj_logic)==list and obj_logic[0]=="not":
          obj_logic=obj_logic[1]

        if ((not ctxt["isquestion"]) and (not iscondition) and (not isconsequence) and
              objrepr):
          update_ctxt_objects(ctxt,objrepr,object,obj_logic) 

      #debug_print("obj_logic2",obj_logic)
      obj_logic_function=make_logic_counted_function(ctxt,sentence,obj_logic,objrepr,
        object,verb,subject,isobject=True,noplural=(iscondition or not verb_is_positive))
      #debug_print("obj_logic_function",obj_logic_function)
      if obj_logic_function and obj_logic_function[0]:
        objsetrepr=[set_function,obj_logic_function[1],subjrepr]
        countatom=logic_replace_el(obj_logic_function[0],objrepr,objsetrepr)
        #debug_print("objsetrepr 2",objsetrepr)
        #debug_print("countatom",countatom)

      else:
        objsetrepr=None  

      #debug_print("new obj_logic",obj_logic)  
      #debug_print("new objrepr",objrepr) 
      #debug_print("new objsetrepr",objsetrepr) 

      proplogic=obj_logic

      #debug_print("child",child)
      #childchildren=get_children(sentence,child)
      relword=el["case"]
      actionobjectvar=objrepr     
       
      if relword:    
        if (relword["lemma"] in ["by"] and
            actionobjectvar==subjrepr):
          #  The car was bought by Mary?
          proplogic=None  
        elif (relword["lemma"] in ["by"]): 
          #  The car was bought by Mary?
          objrelation=make_atom_2(ctxt,sentence,verb,verb,positive,subjrepr,actionobjectvar,1)          
          proplogic=["and",proplogic,objrelation] 
        else:
          objrelation=make_atom_2(ctxt,sentence,verb,relword,positive,actionvar,actionobjectvar,1,"rel2")          
          #debug_print("objrelation",objrelation)
          proplogic=["and",proplogic,objrelation]

      if proplogic:  
        if not objspecialvar:
          if object_quantifier:
            proplogic=[object_quantifier,[objrepr],proplogic]
        sublist2.append(proplogic)

  #debug_print("action_prop_logic sublist2",sublist2)   
  if sublist2:
    andlist2=sublist2
    andlist2=[listop]+andlist2  
  else:
    andlist2=None  
  #debug_print("action_prop_logic andlist2",andlist2)  

  if andlist and andlist2:
    res=["and",andlist,andlist2]
  elif andlist:
    res=andlist
  elif andlist2:
    res=andlist2  
  else:
    #debug_print("make_action_prop_logic ends with None ------------------")
    ctxt["isquestion"]=orig_isquestion
    return None  
  
  res=prop_flatten_logic_term(res)
  freevars=collect_free_vars(res)
  bindvars=[]
  for var in freevars:
    if var[2:].startswith("O"):
      #debug_print("var",var)
      bindvars.append(var)
  if bindvars:
    res=["exists",bindvars,res]    
  ctxt["isquestion"]=orig_isquestion
  #debug_print("make_action_prop_logic res",res)
  #debug_print("make_action had actionvar,subject,subjrepr",(actionvar,subject,subjrepr))
  #debug_print("make_action_prop_logic ended ------------------")
  return res    



def make_qualified_atom_1(ctxt,sentence,verb,thing,positive,var,confidence=1,
                           act_type=None,actionrepr=None,propclass=None,blocker_preferred=None,subjpart=None): 
  res1=make_atom_1(ctxt,sentence,verb,thing,positive,var,confidence,act_type,actionrepr,propclass,blocker_preferred,subjpart)
  return res1


def make_atom_1(ctxt,sentence,verb,thing,positive,var,confidence=1,act_type=None,actionrepr=None,propclass=None,blocker_preferred=None,subjpart=None):
  #debug_print("make_atom_1 thing",thing)
  #debug_print("make_atom_1 var",var)
  #debug_print("make_atom_1 type(var)",type(var))
  #debug_print("make_atom_1 thing",thing)
  #debug_print("make_atom_1 type(thing)",type(thing))
  #debug_print("make_atom_1 propclass",propclass)
  #debug_print("make_atom_1 verb",verb)
  #debug_print("make_atom_1 ctxt",ctxt)
  #debug_print("make_atom_1 blocker_preferred",blocker_preferred)
  #debug_print("make_atom_1 sentence",sentence)

  if not thing: return None   
  if type(thing)==list:
    # John has three nice or big cars.
    # not OK!!! Just a temporary hack for or!!
    thing=thing[1]
    lemma=thing["lemma"] 
  else:    
    lemma=thing["lemma"]

  if lemma in ["where"]:
    return None  

  if ("isquestion" in ctxt and ctxt["isquestion"] and 
      thing["lemma"] in question_words or (propclass and propclass["lemma"] in question_words)):
    question_thing=True
  else:
    question_thing=False  
  #debug_print("make_atom_1 question_thing",question_thing)

  if act_type:  
    pred=act_type  
  elif thing["upos"] in ["VERB"]:
    pred="act1"  
  elif ((thing["upos"] in ["PROPN"]) and
        ((not ("ner" in thing )) or not (thing["ner"] in ["S-NORP"]))):
    pred="has_name"
    return None
  elif ((thing["upos"] in ["NOUN"]) or
        ((thing["upos"] in ["PROPN"]) and ("ner" in thing ) and (thing["ner"] in ["S-NORP"]))):
    pred="isa"  
  elif ( (thing["upos"] in ["ADJ"]) and ("ner" in thing ) and (thing["ner"] in ["S-NORP"]) and 
          subjpart and type(subjpart)==dict and "ner" in subjpart and subjpart["upos"]=="PROPN" and subjpart["ner"] in ["S-PERSON","PERSON"] ):
    # Mr Dursley is an American. # for version 1.5
    pred="isa"   
  elif thing["upos"] in ["NUM"]:
    pred="count"      
  else:
    pred="prop"
    degree=2     
  
  #debug_print("pred",pred)
  if type(lemma)==str and pred=="prop":
    lemma=lemma.lower()    
  elif pred=="count":
    lemma=make_number_from_str(lemma)  
    var=["$count",var]    
    comp=get_comparison_indicator(ctxt,sentence,thing)
    #debug_print("comp",comp)
    #comp="$greater"
    if comp=="$greater":
      pred=comp
    elif comp=="$less":
      pred=comp
    else: 
      pred="="

  if not positive:
    pred="-"+pred 

  prop_intensity=default_prop_intensity
  #debug_print("propclass",propclass)
  prop_class=default_prop_class 
  if ("isquestion" in ctxt and ctxt["isquestion"] and 
      (not propclass or question_thing)):
    prop_class=fully_free_variable #unknown_value 
  elif not propclass:
    None
  elif propclass and type(propclass)!=dict:
    None  
  elif (not (propclass["lemma"] in ["who","that","which"]) and
    lemma in class_prop_words): 
    prop_class=propclass["lemma"]
  elif (propclass["lemma"] in ["who","that","which"] and
        lemma in class_prop_words):           
    previous=get_previous_word(sentence,propclass)
    if previous and previous["upos"] in ["NOUN"]: 
      prop_class=previous["lemma"]     
 
  children=get_children(sentence,thing)
  if children:
    for child in children:
      if child["deprel"] in ["advmod"] and child["upos"] in ["ADV"]:
        if child["lemma"] in maximize_prop_words:
          prop_intensity=max_prop_intensity
        elif child["lemma"] in minimize_prop_words:
          prop_intensity=min_prop_intensity 
  if pred in ["$greater","$less","-$greater","-$less"]:
    res=[pred,var,lemma]
  else:         
    res=[pred,lemma,var]
  if pred in ["prop","-prop"]:
    res.append(prop_intensity)
    res.append(prop_class)  
  if blocker_preferred==None: blocker_preferred=False
  if confidence!=None and ctxt["confidences"]:
    res.append([confidence_function,confidence,blocker_preferred])
  elif blocker_preferred:
    res.append([confidence_function,1,blocker_preferred])

  if actionrepr:
    res.append(actionrepr)  
  #debug_print("make_atom_1 res",res)   
 
  if not (pred in ["=","!=","isa","-isa","$greater","$less","-$greater","-$less"]) and ctxt["addctxt"]:
    ctxtargument=make_ctxt_argument(ctxt,sentence,verb,thing)
    res.append(ctxtargument)
  #debug_print("make_atom_1 res",res)     
  #print("make_atom_1 res",res) 
  return res

def make_atom_2(ctxt,sentence,verb,thing,positive,var1,var2,confidence=1,act_type=None,actionrepr=None,blocker_preferred=None):  
  #debug_print("make_atom_2 verb",verb)
  #debug_print("make_atom_2 thing",thing)
  #debug_print("make_atom_2 act_type",act_type)
  #debug_print("make_atom_2 positive",positive)
  #debug_print("make_atom_2 var1 var2",[var1,var2])
  reversepos=False
  lemma=thing["lemma"]
  origverb=verb
  targetverblemma=None
  if "relation" in thing:
    relation_type=thing["relation"]
  elif (verb["lemma"]=="be" and "relatedobjects" in verb and 
        verb["relatedobjects"][0]["case"]["lemma"]=="of"):
    # Elephants are afraid of mice    
    relation_type="of"    
    lemma=thing["lemma"] #"afraid" #verb["relatedobjects"][0]["case"]["lemma"] 
  else:
    relation_type=""    

  if (verb["lemma"]!="be" and "relatedverbs" in verb and 
        verb["relatedverbs"][0]["case"]["lemma"]=="to" and
        "obj" in verb["relatedverbs"][0]):
    # "Snails want to eat plants. "      
    targetverblemma=verb["relatedverbs"][0]["obj"]["lemma"] #"afraid" #verb["relatedobjects"][0]["case"]["lemma"]    
  
  #debug_print("make_atom_2 targetverblemma",targetverblemma)
  #debug_print("make_atom_2 thing",thing)
  #debug_print("make_atom_2 lemma",lemma)  
  #debug_print("make_atom_2 raw relation_type", relation_type) 
  
  if relation_type and relation_type in nlpglobals.relation_type_translate:
    relation_type=nlpglobals.relation_type_translate[relation_type]
  elif not relation_type:
    if lemma in nlpglobals.relation_type_translate:
      relation_type=nlpglobals.relation_type_translate[lemma]
      act_type=None
      actionrepr=None
    elif lemma in nlpglobals.relation_type_reverse_translate:  
      reversepos=True
      relation_type=nlpglobals.relation_type_reverse_translate[lemma] 
      act_type=None
      actionrepr=None

  if relation_type in nlpglobals.relation_type_negative_translate:
    relation_type=nlpglobals.relation_type_negative_translate[relation_type]
    positive=not positive

  #debug_print("make_atom_2 translated relation_type", relation_type)   

  if targetverblemma:
    if (relation_type or lemma in ["have"] or
       (targetverblemma in nlpglobals.abstract_verbs)):
      pred="rel2"
    elif act_type:
      pred=act_type  
    else:
      pred="act2"  
  elif (relation_type or lemma in ["have"] or
       (verb and verb["lemma"] in nlpglobals.abstract_verbs)):
    pred="rel2"
  elif act_type:
    pred=act_type  
  else:
    pred="act2"  

  if targetverblemma:
    pred="attitude_"+pred

  if positive:
    None #pred="rel2"
  else:
    pred="-"+pred #"-rel2"  

  if relation_type in ["of","than","for"]:  
    pred=pred+"_"+relation_type    
  elif relation_type:
    lemma=relation_type  

  #debug_print("make_atom_2 pred",pred)  

  if blocker_preferred==None: blocker_preferred=False

  if reversepos:    
    res=[pred,lemma,var2,var1]  
  else:       
    res=[pred,lemma,var1,var2]  
  #("res2",res)

  if targetverblemma:
    res=[res[0],res[1],targetverblemma]+res[2:]
  comparison_pred=False

  comp=get_comparison_indicator(ctxt,sentence,thing)
  #debug_print("comp",comp)

  #debug_print("pred",pred)
  #debug_print("var1",var1)
  #debug_print("var2",var2)
  #debug_print("res",res)
  
  if (pred in ["rel2_than"] and comp and
       (type(var1)==list and var1[0] in [measure_function+"1"] or
        type(var2)==list and var2[0] in [measure_function+"1"])):
    #debug_print("comparison measure detected, res",res)
    if var1[1] in ["length"]:
      #debug_print("length detected")
      newpred=comp
      res=[newpred,[count_function,res[2]],[count_function,res[3]]] 
      return res

  if (pred in ["rel2_than","do2","act2"] and  
      type(var1)==list and var1[0] in [measure_function+"1"] and
      type(var2)==list and var2[0] in [measure_function+"1"]):
    newpred=None
    for el in measure_words:
      if "morenouns" in el and lemma in el["morenouns"]:
        newpred="$greater"
        break
      elif "lessnouns" in el and lemma in el["lessnouns"]:
        newpred="$less"
        break  
    if lemma in comparison_words:
      if "less" in comparison_words[lemma] and  comparison_words[lemma]["less"]:
        newpred="$less"
      elif "more" in comparison_words[lemma] and  comparison_words[lemma]["more"]:
        newpred="$greater"
      elif "equal" in comparison_words[lemma] and  comparison_words[lemma]["equal"]:
        newpred="="  
    if newpred:         
      comparison_pred=newpred   
      res=[newpred,[count_function,res[2]],[count_function,res[3]]] 
  #debug_print("res3",res)

  if confidence!=None and ctxt["confidences"]:
    res.append([confidence_function,confidence,blocker_preferred])
  elif blocker_preferred:
    res.append([confidence_function,1,blocker_preferred])

  if actionrepr and not comparison_pred and not (pred in ["rel2","-rel2"]): #,"rel2_of","-rel2_of","rel2_than","-rel2_than"]):
    res.append(actionrepr)

  #debug_print("res4",res)  
  if ctxt["addctxt"] and not comparison_pred:
    if not (pred in ["isa","-isa"]):
      if thing["upos"]=="VERB" and word_has_feat(verb,"VerbForm","Part"):
        ctxtargument=make_ctxt_argument(ctxt,sentence,verb,thing)
      else:  
        ctxtargument=make_ctxt_argument(ctxt,sentence,verb,thing)
      res.append(ctxtargument)  
  if (pred=="act2" and positive and confidence>0.9 and 
      (not noframes) and (not nonewframes) and (not noframevars)):
    if var2!=dummysubject:
      ctxt["framenr"]=ctxt["framenr"]+1
      #debug_print("CP framenr increased to !!!",ctxt["framenr"])
      #debug_print("res was ",res)
      #debug_print("thing was ",thing)
      #debug_print("pred",pred)
      #debug_print("var1",var1)
      #debug_print("var2",var2)

  return res  

def get_comparison_indicator(ctxt,sentence,thing):
  #debug_print("get_comparison_indicator thing",thing)
  if not thing: return None
  if thing["upos"] in ["ADJ"] and is_larger_word(ctxt,sentence,thing):
    return "$greater"
  elif thing["upos"] in ["ADJ"] and is_smaller_word(ctxt,sentence,thing):
    return "$less"  
  children=get_children(sentence,thing)
  for child in children:
    if (child["deprel"] in ["advmod"] and is_larger_word(ctxt,sentence,child)):
      return "$greater"
    if (child["deprel"] in ["advmod"] and is_smaller_word(ctxt,sentence,child)):
      return "$less"  
  parent=get_parent(sentence,thing)    
  if not parent: return None
  children=get_children(sentence,parent)
  for child in children:
    if (child["deprel"] in ["advmod"] and is_larger_word(ctxt,sentence,child)):
      return "$greater"
    if (child["deprel"] in ["advmod"] and is_smaller_word(ctxt,sentence,child)):
      return "$less"  
  return None

def is_larger_word(ctxt,sentence,word):
  if not word: return False
  if word["lemma"] in larger_words: return True
  return False

def is_smaller_word(ctxt,sentence,word):
  if not word: return False
  if word["lemma"] in smaller_words: return True
  return False  



def make_ctxt_argument(ctxt,sentence,verb,thing=None):
  #debug_print("make_ctxt_argument thing",thing)
  #debug_print("make_ctxt_argument verb",verb)
  beword=find_related_be_word(ctxt,sentence,verb)
  #debug_print("make_ctxt_argument beword",beword)
  #debug_print("ctxt[framenr]",ctxt["framenr"])
  #debug_print("make_ctxt_argument ctxt",ctxt)
  if (thing and verb==thing and type(verb)==dict and beword and
      word_has_feat(verb,"VerbForm","Part")): # and word_has_feat(verb,"Voice","Pass")):
    #debug_print("cp be case 1")
    # John is defeated
    # John is nice and defeated
    #beword=find_related_be_word(ctxt,sentence,verb)
    #debug_print("cp be",beword)
    #if beword:
    verb=beword 
  elif type(verb)==dict and beword and word_has_feat(verb,"Degree","Cmp"):
    verb=beword
  elif verb and type(verb)==dict and verb["upos"] in ["VERB","AUX"]: #,"ADJ"
    #2debug_print("cp be case 2")
    if "be" in verb:
      verb=verb["be"]
  #debug_print("make_ctxt_argument verb 2",verb)    
  if verb and type(verb)==dict and verb["upos"] in ["VERB","AUX"]:    
    tensevalue=get_word_feat(verb,"Tense")
    #debug_print("make_ctxt_argument tensevalue",tensevalue)
    if not tensevalue: 
      if word_has_feat(verb,"VerbForm","Inf"):
        children=get_children(sentence,verb)
        for child in children: 
          if child["deprel"]=="aux" and child["lemma"]=="do" and get_word_feat(child,"Tense"):
            tensevalue=get_word_feat(child,"Tense")
            break
    if not tensevalue:             
      tvar="?:Tense"+str(ctxt["varnum"])     
      ctxt["varnum"]+=1
      tensevalue=tvar
  else:
    tvar="?:Tense"+str(ctxt["varnum"])
    ctxt["varnum"]+=1
    tensevalue=tvar

  #debug_print("tensevalue",tensevalue)
  #debug_print("thing",thing)

  framenr=ctxt["framenr"]
  if noframes or noframevars:    
    None    
  elif tensevalue=="Past" and ("isquestion" in ctxt) and ctxt["isquestion"]:
    framenr=frame_var_prefix+str(ctxt["varnum"])
    ctxt["varnum"]+=1
  elif "isrule" in ctxt and ctxt["isrule"]:
    #framenr=frame_var_prefix+str(ctxt["varnum"])
    #ctxt["varnum"]+=1
    framenr=frame_var_prefix
    framenr="$free_variable"
  elif thing and thing["deprel"] in ["case"]:    
    framenr=ctxt["framenr"]
    #debug_print("CP framenr in case!!!",framenr)
  ctargument=[ctxt_function,tensevalue,framenr]
  #debug_print("ctargument",ctargument)
  return ctargument

def find_related_be_word(ctxt,sentence,word):
  #debug_print("word",word)
  if not word or type(word)!=dict: return None
  children=get_children(sentence,word)
  for el in children:
    if el["lemma"]=="be" and el["upos"]=="AUX":
      return el
  parent=get_parent(sentence,word)
  if parent:
    children=get_children(sentence,parent)
    for el in children:
      if el["lemma"]=="be" and el["upos"]=="AUX":
        return el
  return None      

def is_keep_free_var(ctxt,var):
  if is_var(var):
     if var.startswith("?:Tense"): return True
     if var.startswith("?:Unit"): return True
     else: return False
  else: return False


# =========== the end ==========
