# Uncertainty analysis and encoding in the nlpsolver.
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

# ========= uncertainty adding ====

def encode_uncertainty_clause_list(ctxt,lst):
  if not lst: return lst  
  if type(lst)!=list: return lst
  res=[]
  for frm in lst:
    newfrm=encode_uncertainty_top_logic(ctxt,frm)
    if not newfrm: continue
    res=res+newfrm
  #debug_print("res",res)  
  return res


def encode_uncertainty_top_logic(ctxt,frm): 
  #debug_print("encode_uncertainty_top_logic frm",frm)
  if not frm: return frm
  name=None
  logicwrapper="@logic"
  frm_confidence=None
  if type(frm)==dict:    
    if "@name" in frm:
      name=frm["@name"]
    if "@confidence" in frm:
      frm_confidence=frm["@confidence"]  
      if frm_confidence==0:
        return [frm]
    newfrm=frm.copy()
    if "@logic" in newfrm:
      logic=newfrm["@logic"]
    elif "@question" in newfrm:
      return [frm]
  else:
    newfrm=None
    logic=frm   
  if not logic: return None
  if logic[0]=="or":
    clauses=[logic]
  elif logic[0]=="and":  
    clauses=logic[1:]
  else:
    clauses=[logic]  
  wrappedclauses=[]
  confidence_annotated_clauses=0
  certain_clauses=0
  for clause in clauses:
    annotation_confidence=clause_confidence_annotation_value(ctxt,clause)
    #debug_print("annotation_confidence1",annotation_confidence)
    if annotation_confidence and annotation_confidence!=1:
      #debug_print("annotation_confidence2",annotation_confidence)
      confidence_annotated_clauses+=1
    elif is_certain_clause(ctxt,clause):
      certain_clauses+=1

  #debug_print("encode_uncertainty_top_logic clauses",clauses)    
  #debug_print("encode_uncertainty_top_logic frm_confidence",frm_confidence)
  #debug_print("len(clauses)",len(clauses))
  #debug_print("certain_clauses",certain_clauses)

  if not frm_confidence:
    frm_confidence=1
    if (len(clauses)==1 and clauses[0][0]!="or"):
        frm_confidence=1
    else:    
      has_vars=False
      for clause in clauses:
        clausevars=collect_free_vars(clause)
        if clausevars:
          has_vars=True
          break
      if has_vars:
        frm_confidence=1

  #debug_print("encode_uncertainty_top_logic frm_confidence",frm_confidence)       
  if frm_confidence==1:
    clause_confidence=1 
  elif certain_clauses+confidence_annotated_clauses==len(clauses):    
    clause_confidence=1
  elif len(clauses)==1:
    clause_confidence=frm_confidence      
  else:  
    clause_confidence=frm_confidence **  (1. 
      / float(len(clauses)-(certain_clauses+confidence_annotated_clauses)))
  for clause in clauses:   
    is_certain=is_certain_clause(ctxt,clause)
    annotation_confidence=clause_confidence_annotation_value(ctxt,clause)
    blockers=make_clause_blockers(ctxt,clause,is_certain)
    if blockers:
      newclause=clause+blockers
    else:  
      newclause=clause
    if annotation_confidence and annotation_confidence!=1:
      confidence=annotation_confidence
    elif is_certain:
      confidence=1
    else:  
      confidence=clause_confidence
    wrappedclause={logicwrapper: newclause}
    if name: 
      wrappedclause["@name"]=name
    if confidence<1:
      wrappedclause["@confidence"]=confidence
    wrappedclauses.append(wrappedclause)
  #debug_print("wrappedclauses",wrappedclauses)  
  return wrappedclauses  


def clause_confidence_annotation_value(ctxt,clause):
  #debug_print("clause_confidence_annotation_value clause",clause)
  if not clause: return None
  if type(clause)!=list: return None
  for el in clause:
    if type(el)==list and el[0]==confidence_function:
      return el[1]
  minconf=1    
  for atom in clause:
    #debug_print("clause_confidence atom",atom)
    if type(atom)!=list: continue
    for el in atom:
      #debug_print("clause_confidence el",el)
      if type(el)==list and el[0]==confidence_function:
        if el[1]<minconf: minconf=el[1]
  if minconf<1: return minconf       
  else: return None

def make_clause_blockers(ctxt,clause,is_certain):
  #debug_print("make_clause_blocker clause",clause)
  #debug_print("make_clause_blocker is_certain",is_certain)  
  if not clause: return None
  if type(clause)!=list: return None
  if clause[0]!="or": return None
  if is_certain: return None
  vars=collect_free_vars(clause)
  if not vars: return None 
  classes=[]
  subjclasses=[]
  classprops=[]
  props=[]
  blocker_preferred=[]
  blockers=[]
  others=[]
  #debug_print("clause",clause)
  for atom in clause[1:]:
    #debug_print("atom",atom)
    if atom[0] in ["-isa"]:
      classes.append(atom)
      if "?:S" in atom[2]:
        subjclasses.append(atom)
    elif atom[0] in ["prop","-prop",
                     "do1","-do1","do2","-do2",
                     "act1","-act1","act2","-act2",
                     "can1","-can1","can2","-can2",
                     "rel2","-rel2",
                     "isa","-isa",
                     "rel2_of","-rel2_of",
                     "rel2_than","-rel2_than",
                     "rel2_is_of","-rel2_is_of"]:
      if contains_confidence_annotation(ctxt,atom):
        #debug_print("atom",atom)
        props.append(atom) 
        ispreferred=False
        for el in atom:
          if type(el)!=list: continue
          if el[0]==confidence_function:
            if len(el)>2 and el[2]:
              blocker_preferred.append(atom)
              ispreferred=True
              break
        if not ispreferred:
          classprops.append(atom)    
      else:
        classprops.append(atom)    
    elif atom[0] in ["$block"]:
      blockers.append(atom)  
    else:
      others.append(atom)
  if blockers: return None 
  #debug_print("classes",classes)
  #debug_print("props",props)
  #debug_print("others",others)
  #debug_print("subjclasses",subjclasses)
  #debug_print("classprops",classprops)
  #debug_print("blocker_preferred",blocker_preferred) 

  if len(classes)>=1 and len(props)==1 and len(others)==0 and blocker_preferred:
    if subjclasses:
      blocker=make_blocker_atom(ctxt,props[0],subjclasses[-1],classprops+classes[:-1])
    else:
      blocker=make_blocker_atom(ctxt,props[0],classes[-1],classprops+classes[:-1])  
    #debug_print("make_clause_exception blocker",blocker)    
    return  [blocker]    
  elif len(blocker_preferred)==1:
    #debug_print("blocker_preferred 2",blocker_preferred)  
    blockers=[]
    for el in blocker_preferred:      
      if not classes:
        blocker=make_blocker_atom(ctxt,el,None,classprops+classes[:-1]) 
      else:  
        blocker=make_blocker_atom(ctxt,el,classes[-1],classprops+classes[:-1])  
      blockers.append(blocker)
    return blockers  
  return None

def make_blocker_atom(ctxt,propatom,classatom,classprops):
  if classatom:
    classword=classatom[1]
  else:
    classword="$generic"  
  ispositive=True
  if propatom[0][0]=="-": ispositive=False
  priornr=len(classprops)+1
  priority=["$",classword,priornr]
  if ispositive:
    tmp=remove_confidence_annotations(ctxt,propatom)
    mainelement=["$not",tmp]
  else:
    tmp=remove_confidence_annotations(ctxt,propatom)
    tmp=[tmp[0][1:]]+tmp[1:]
    mainelement=tmp  
  res=["$block",priority,mainelement]
  return res

def is_certain_clause(ctxt,clause):
  list_atoms=0
  isa_atoms=0
  if type(clause)!=list: return True
  for atom in clause:
    if type(atom)==list:
      list_atoms+=1
    if is_definition_atom(atom):
      return True
    if contains_variable_every(atom):
      return True  
    if is_isa_atom(atom):
      isa_atoms+=1  
  if isa_atoms==list_atoms:
    return True
  return False       

def contains_variable_every(term):
  if type(term)==str: 
    if is_var(term) and "_every" in term:
      return True
  elif type(term)==list:
    for el in term:
      if contains_variable_every(el): return True
  return False  

def is_definition_atom(atom):  
  if type(atom)!=list: return False
  defsymb=atom[0]
  if (defsymb.startswith(definition_prefix) or
      defsymb[0]=="-" and
      defsymb[1:].startswith(definition_prefix)):
     return True
  else:    
      return False


def is_isa_atom(atom):  
  if type(atom)!=list: return False
  leadsymb=atom[0]
  if (leadsymb.startswith("isa") or
      leadsymb[0]=="-" and
      leadsymb[1:].startswith("isa")):
     return True
  else:    
      return False      


def remove_confidence_annotations_frm_list(ctxt,lst):
  if not lst: return lst  
  if type(lst)!=list: return lst
  res=[]
  for frm in lst:
    newfrm=remove_confidence_annotations_top_logic(ctxt,frm)
    if not newfrm: continue
    res.append(newfrm)   
  return res

def remove_confidence_annotations_top_logic(ctxt,frm):     
  if not frm: return frm 
  if type(frm)==dict:        
    if "@logic" in frm:
      logic=frm["@logic"]
    if "@question" in frm:
      logic=frm["@question"]
    newlogic=remove_confidence_annotations(ctxt,logic)
    newfrm=frm.copy()
    if "@logic" in frm:
      newfrm["@logic"]=newlogic
    if "@question" in frm:
      newfrm["@question"]=newlogic  
    return newfrm
  else:
    newlogic=remove_confidence_annotations(ctxt,frm)
    return newlogic

def remove_confidence_annotations(ctxt,frm):
  if type(frm)!=list: return frm
  newfrm=[]
  for el in frm:
    if type(el)!=list:
      newfrm.append(el)
    elif el[0]==confidence_function:
      None
    else:
      newel=remove_confidence_annotations(ctxt,el)
      newfrm.append(newel)
  return newfrm


def contains_confidence_annotation(ctxt,frm):
  if type(frm)!=list: return None
  for el in frm:
    if type(el)!=list: continue
    elif el[0]==confidence_function:
      return True    
  return False


# ----------- linguistic functions ----------------------


def get_word_confidence(ctxt,sentence,word):
  #debug_print("get_word_confidence word",word)
  if not word: return 1
  if not(type(word)==dict): return 1
  children=get_children(sentence,word)
  res1=None
  topconfidence=1

  # First check a ccomp verb for reflection trust, like
  # The lawyers believed that the tourists shouted
  if word["deprel"] in ["ccomp"] and word["upos"] in ["VERB"]:
    parent=get_parent(sentence,word)
    if parent and parent["upos"] in ["VERB"]:
      plemma=parent["lemma"]
      if plemma in mistrust_confidences:
        topconfidence=mistrust_confidences[plemma]

  # next check children for concrete confidence indications
  if children:    
    for child in children:
      #debug_print("get_word_confidence child",child)
      if (child["deprel"]=="advmod" and child["upos"] in ["PART","ADV"] and
          get_lemma_confidence(ctxt,child["lemma"])!=1):
        confidence=get_lemma_confidence(ctxt,child["lemma"])
        #debug_print("returning confidence 2",topconfidence*confidence)
        #debug_print("returning confidence 2 topconfidence",topconfidence)
        #debug_print("returning confidence 2 confidence",confidence)
        return topconfidence*confidence
      elif (child["deprel"]=="det" and child["upos"] in ["DET"] and
            not (child["lemma"] in ["a","the"])):
        confidence=get_lemma_confidence(ctxt,child["lemma"])
        #debug_print("returning confidence 2",topconfidence*confidence)
        return topconfidence*confidence      
    prob_word=get_deepchild(ctxt,sentence,word,probability_words)
    prob_num=get_deepchild(ctxt,sentence,word,[],["nummod"])
    #debug_print("prob_word",prob_word)
    #debug_print("prob_num",prob_num)

    if prob_word and prob_num:
      try:
        rawconfidence=float(prob_num["lemma"])
      except:
        show_error("non-numeric confidence "+prob_num["lemma"])
        sys.exit(0)              
        # should give an error! 
      if rawconfidence<0:
        show_error("negative confidence "+prob_num["lemma"])
        sys.exit(0)   
      if rawconfidence>1:
        confidence=rawconfidence/100
      else:
        confidence=rawconfidence  
      if confidence>1:
        show_error("too large confidence value"+prob_num["lemma"])
        sys.exit(0)
      # 0:    -1  
      # 0.1:  -0.8
      # 0.4:  -0.2
      # 0.5:  0
      # 0.6:  0.2
      # 0.9:  0.8
      # 1:    1  
      confidence=round((2*confidence)-1,4)  
      #debug_print("returning confidence 3",topconfidence*confidence)          
      return topconfidence*confidence 
  #debug_print("topconfidence",topconfidence)        
  return topconfidence
  

def get_deepchild(ctxt,sentence,word,lemmas=[],deprels=[]):
  children=get_children(sentence,word)
  for child in children:
    if child["lemma"] in lemmas: return child
    if child["deprel"] in deprels: return child
    tmp=get_deepchild(ctxt,sentence,child,lemmas,deprels)
    if tmp: return tmp
  return False

def get_lemma_confidence(ctxt,lemma):
  debug_print("get_lemma_confidence lemma",lemma)
  if lemma in lemma_confidences:
    return lemma_confidences[lemma]
  else:
    return 1

def get_probability_text_qualifier(confidence,istrue):
  if confidence==1:
    return ""
  elif confidence>=0.9:
    return "probably"
  elif confidence>=0.5:
    return "likely" 
  elif confidence>=0.25:
    return "maybe"   
  else:
    return "perhaps"

def get_word_quantor_confidence(ctxt,sentence,word):
  if not word: return 1
  children=get_children(sentence,word)
  if not children: return 1
  confidence=1
  for child in children:
    if (child["deprel"] in ["amod"]) and (child["upos"] in ["ADJ"]):
      if child["lemma"] in quantor_confidences:
        confidence=quantor_confidences[child["lemma"]]
        childchildren=get_children(sentence,child)
        if confidence>0 and childchildren:
          for childchild in childchildren:
            if ((childchild["deprel"] in ["advmod"]) and (childchild["upos"] in ["ADV"]) and
                 childchild["lemma"] in ["no","not"]):
              confidence=0-confidence    
  return confidence      


# =========== the end ==========
