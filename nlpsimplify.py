# Logic simplifiers for the nlpsolver.
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

# ========= logic simplification ====

combinations=[]


def build_simplified_logic_list(ctxt,sentence,logic_list):
  nameatoms=[]
  namedict={}  
  new_logic_list=[]
  for logic in logic_list:
    if not logic: continue
    #debug_print("logic",logic)
    if type(logic)==dict: 
      if "@question" in logic: purelogic=logic["@question"]
      else: purelogic=logic["@logic"]
    else: purelogic=logic
    if purelogic in [True]:
      continue
    elif purelogic[0]!="has_name": 
      new_logic_list.append(logic)
      continue
    else:
      name=purelogic[1]
      if name in namedict: continue
      nameatoms.append(purelogic)
      namedict[name]=purelogic
  #debug_print("nameatoms",nameatoms)
  #debug_print("namedict",namedict)

  res=[]
  for logic in new_logic_list:
    replaced=logic_replace_nameatoms(logic,nameatoms,namedict)
    flattened=prop_flatten_logic_term(replaced)
    if flattened!=True:
      res.append(flattened)
  return res

def logic_replace_nameatoms(lst,nameatoms,namedict):    
  if type(lst)==list:
    if lst[0] in ["has_name","-has_name"]:
      if lst[1] in namedict:
        if lst[0]=="has_name":
          return True
        else:
          return False
      else:
        return lst
    else:
      res=[]
      for lel in lst:
        tmp=logic_replace_nameatoms(lel,nameatoms,namedict)
        res.append(tmp)
      return res  
  elif type(lst)==dict:
    if "@logic" in lst:
      newlogic=logic_replace_nameatoms(lst["@logic"],nameatoms,namedict)    
      lst["@logic"]=newlogic
      return lst 
    elif "@question" in lst:
      newlogic=logic_replace_nameatoms(lst["@question"],nameatoms,namedict)    
      lst["@question"]=newlogic  
      return lst 
    else:
      return lst  
  else:
    return lst

# ========= logic clausification ====

def clausify_logic_list(ctxt,lst):     
  if not lst: return lst  
  if type(lst)!=list: return lst
  res=[]
  for frm in lst:
    newfrm=clausify_top_logic(ctxt,frm)
    if not newfrm: continue
    res.append(newfrm)
    #if type(newfrm)==list and newfrm[0]=="and":
    #  res=res+newfrm[1:]  
    #else:  
    #  res.append(newfrm)
  return res

def clausify_top_logic(ctxt,frm): 
  #debug_print("clausify_top_logic frm",frm)
  if type(frm)==dict:    
    newfrm=frm.copy()
    if "@logic" in newfrm:
      logic=newfrm["@logic"]
    elif "@question" in newfrm:
      logic=newfrm["@question"]
  else:
    newfrm=None
    logic=frm    
  isclause=False  
  #debug_print("clausify_top_logic logic",logic)
  if type(logic)==list and type(logic[0])==list:
    foundsimple=False
    for el in logic:
      if type(el)!=list:
        foundsimple=True
        break
    if not foundsimple:
      isclause=True
      logic=["or"]+logic   
  #debug_print("clausify_top_logic logic",logic)
  logic0=convert_logic_to_and_or(logic,True)
  #debug_print("convert_logic_to_and_or",logic0)
  if logic_contains_el(logic0,unknown_value): logic1=convert_logic_unknowns(ctxt,logic0)
  else: logic1=logic0  
  #debug_print("convert_logic_unknowns",logic1)
  #logic1a=convert_logic_fully_free_variables(ctxt,logic1)
  #debug_print("convert_logic_fully_free_variables",logic1a)
  logic2=push_negation_inside(logic1,True)
  #debug_print("negation pushed inside",logic2)
  logic2notvery=convert_logic_notvery(ctxt,logic2)
  #debug_print("pre-skolemize",logic2notvery)
  logic3=skolemize(ctxt,logic2notvery,[],{})
  #debug_print("post-skolemize",logic3)
  logic3a=convert_logic_fully_free_variables(ctxt,logic3)
  #debug_print("post-skolemize",logic3a)
  logic4=distribute_and_or(logic3a)
  logic5=prop_flatten_logic_term(logic4)
  if type(frm)==dict:
    if "@logic" in frm:
      newfrm["@logic"]=logic5
    elif "@question" in frm:
      newfrm["@question"]=logic5
    return newfrm  
  else:
    return logic5


def convert_logic_unknowns(ctxt,frm):  
  #debug_print("ctxt",ctxt)   
  if not frm: return frm  
  if type(frm)!=list: return frm  
  # here frm is a list 
  thisop=frm[0]
  if thisop in logic_ops:
    res=[]
    for el in frm:      
      tmp=convert_logic_unknowns(ctxt,el)
      res.append(tmp)
    return res
  # here frm is an atom
  if logic_contains_el(frm,unknown_value):
    newvar="?:U"+str(ctxt["varnum"])
    ctxt["varnum"]+=1
    tmp=logic_replace_el(frm,unknown_value,newvar)
    res=["exists",[newvar],tmp]
    return res
  else:
    return frm 

def convert_logic_fully_free_variables(ctxt,frm):  
  if not frm: return frm  
  if type(frm)==str:     
    if frm==fully_free_variable: 
      res="?:Ignore"+str(ctxt["varnum"])
      ctxt["varnum"]+=1
      return res
    else: 
      return frm
  elif type(frm)==list:
    res=[]
    for el in frm:
      res.append(convert_logic_fully_free_variables(ctxt,el))  
    return res 
  else:
    return frm  



def old_term_contains_logic_unknown(frm):
  if not frm: return False  
  if type(frm)!=list: 
    if frm==unknown_value: return True
    else: return False
  for el in frm:
    if term_contains_logic_unknown(el): return True
  return False   


def convert_logic_notvery(ctxt,frm):  
  #debug_print("convert_logic_notvery frm",frm)   
  if not frm: return frm  
  if type(frm)!=list: return frm  
  # here frm is a list 
  thisop=frm[0]
  if thisop in logic_ops:
    res=[]
    for el in frm:      
      tmp=convert_logic_notvery(ctxt,el)
      res.append(tmp)
    return res
  # here frm is an atom 
  if frm[0]=="-prop" and  frm[3]==max_prop_intensity:
    #debug_print("cp1 case")
    frm2=frm.copy()
    frm2[0]="prop"
    frm2[3]=default_prop_intensity
    #debug_print("cp1 case frm2",frm2)
    return ["and", frm, frm2]
  else:
    return frm  



# - - - - convert to and/or/not - - - - - 

"""
def convert_logic_list_to_and_or(lst):   
  if not lst: return lst  
  if type(lst)!=list: return lst
  res=[]
  for frm in lst:
    newfrm=convert_top_logic_to_and_or(frm)
    res.append(newfrm)
  return res
"""

"""
def convert_top_logic_to_and_or(frm):     
  if not frm: return frm  
  if type(frm)!=dict:
    return convert_logic_to_and_or(frm,True)
  # here frm is a dict   
  newfrm=frm.copy()
  if "@logic" in newfrm:
    newlogic=convert_logic_to_and_or(newfrm["@logic"],True)
    newfrm["@logic"]=newlogic
  elif "@question" in newfrm:
    newlogic=convert_logic_to_and_or(newfrm["@question"],True)
    newfrm["@question"]=newlogic
  return newfrm
"""

def convert_logic_to_and_or(frm,ispositive):     
  if not frm: return frm  
  if type(frm)!=list: return frm  
  # here frm is a list 
  thisop=frm[0]
  if thisop=="forall" or thisop=="exists":
    res=[thisop,frm[1]]   
    for el in frm[2:]:
      newel=convert_logic_to_and_or(el,ispositive)
      res.append(newel)
    return res
  elif thisop=="$block":
    return frm
    """
    res=[thisop,frm[1]]
    for el in frm[2:]:
      newel=convert_logic_to_and_or(el,ispositive)
      res.append(newel)
    return res  
    """
  elif thisop in ["and","or","not"]:
    if thisop=="not": ispositive=not ispositive
    res=[thisop]
    for el in frm[1:]:
      newel=convert_logic_to_and_or(el,ispositive)
      res.append(newel)
    return res
  # now check for simplifiable ops
  if len(frm)!=3 or not frm[1] in ["=>","<=","<=>","<~>"]:
    # here the formula seems to be atomic
    return frm
  # here we have a simplifiable op
  op=frm[1]
  left=frm[0]
  right=frm[2]
  if op=="=>":
    res=["or",
          ["not",convert_logic_to_and_or(left,not ispositive)],
          convert_logic_to_and_or(right,ispositive)]
    return res
  elif op=="<=":
    res=["or",
          ["not",convert_logic_to_and_or(right,not ispositive)],
          convert_logic_to_and_or(left,ispositive)]
    return res
  elif op=="<=>":
    newleft=convert_logic_to_and_or(left,ispositive)
    newright=convert_logic_to_and_or(right,ispositive)
    res=["and",
           ["or", ["not", newleft],newright],
           ["or", newleft,["not",newright]]]
    return res
  elif op=="<~>":
    newleft=convert_logic_to_and_or(left,ispositive)
    newright=convert_logic_to_and_or(right,ispositive)
    res=["and",
           ["or", newleft,newright],
           ["not",["and",newleft,newright]]]
    return res
  else:
    # should not happen
    print("Error: clausification encountered wrong op")
    sys.exit(0)


# - - - - push negation inside - - - - - 

def push_negation_inside(frm,ispositive):
  #debug_print("frm",frm)
  #debug_print("spaces",spaces)    
  if not frm: return frm  
  if type(frm)!=list: return frm
  # here frm is a list 
  thisop=frm[0]
  el=frm
  if thisop=="forall" or thisop=="exists":
    if not ispositive:
      if thisop=="forall": thisop="exists"
      else: thisop="forall"      
    res=[thisop,frm[1]]   
    for el in frm[2:]:
      newel=push_negation_inside(el,ispositive)
      res.append(newel)
    return res
  elif thisop=="$block":
    return frm
    """
    res=[thisop,frm[1]]
    for el in frm[2:]:
      newel=push_negation_inside(el,ispositive)
      res.append(newel)
    return res  
    """  
  elif thisop=="and" or thisop=="or":
    if not ispositive:
      if thisop=="and": thisop="or"
      else: thisop="and"  
    res=[thisop]
    for el in frm[1:]:
      newel=push_negation_inside(el,ispositive)
      res.append(newel)
    return res
  elif thisop=="not":
    if not ispositive:
      return push_negation_inside(el[1],True)
    else:
      return push_negation_inside(el[1],False)  
  elif type(thisop)!=str:
    res=[]
    for el in frm[1:]:
      newel=push_negation_inside(el,ispositive)
      res.append(newel)
    return res  
    #print("frm,thisop",frm,thisop)
    #print("Error: clausification negation push encountered complex head")
    #sys.exit(0)    
  else:
    # should be atomic here
    if ispositive:
      return frm
    elif thisop[0]=="-":
      return [thisop[1:]]+frm[1:]
    else:
      return ["-"+thisop]+frm[1:]

# - - - - - skolemize - - - - -

def skolemize(ctxt,frm,freevars,varmap):
  #debug_print("skolemize",frm)
  if not frm: return frm  
  if type(frm)!=list: return frm
  # here frm is a list 
  thisop=frm[0]
  if thisop=="exists":
    if type(frm[1][0])==list:
      return skolemize(ctxt,frm[2],freevars,varmap)
    #debug_print("ctxt",ctxt)
    newvarmap={} #varmap.copy()
    for var in frm[1]:
      if no_skolem_var(var):
        continue
      if unknownsubject in var:
        fun=make_skolem_constant(ctxt,unknownsubject)
      else:
        fun=make_skolem_constant(ctxt)
      #ctxt["skolem_nr"]=ctxt["skolem_nr"]+1
      if freevars:
        term=[fun]+freevars
      else:
        term=fun
      newvarmap[var]=term
      if "objects" in ctxt:
        for el in ctxt["objects"]:
          #debug_print("var,term,el",[var,term,el])
          if el[0]==var:
            el[0]=term
            newprops=logic_replace_el(el[2],var,term)
            el[2]=newprops
    #debug_print("skolemize newvarmap",newvarmap)
    res=logic_replace_el_map(frm[2],newvarmap)
    #debug_print("skolemize replacement res",res)
    res=skolemize(ctxt,res,freevars,newvarmap)
    #debug_print("skolemize res after internal skolemization",res)
    return res
  elif thisop=="forall":
    if type(frm[1][0])==list:
      return skolemize(ctxt,frm[2],freevars,varmap)
    freevars=frm[1]+freevars
    res=skolemize(ctxt,frm[2],freevars,varmap)
    return res  
  elif thisop=="$block":
    return frm
    """
    res=[thisop,frm[1]]
    for el in frm[2:]:
      newel=convert_logic_to_and_or(el,ispositive)
      res.append(newel)
    return res  
    """
  elif thisop in ["and","or","not"]:    
    res=[thisop]
    for el in frm[1:]:
      newel=skolemize(ctxt,el,freevars,varmap)
      res.append(newel)
    return res 
  else:
    return frm

def no_skolem_var(var):
  if var.startswith("?:Tense"): return True
  else: return False

def make_skolem_constant(ctxt,specialprefix=None):
  if specialprefix:
    res=specialprefix+str(ctxt["skolem_nr"])  
  else:  
    res=skolem_constant_prefix+str(ctxt["skolem_nr"])  
  ctxt["skolem_nr"]=ctxt["skolem_nr"]+1
  #constant_nr+=1
  return res  


# - - - - push quantifier weakly inside:  - - - - - 

def push_quantifier_weakly_inside(frm,quantifier,var):
  #debug_print("frm",frm)
  if not frm: return frm  
  if type(frm)!=list: return frm
  # here frm is a list 
  thisop=frm[0]
  if thisop=="forall" or thisop=="exists":
    if var in frm[1]:
      return frm
    tmp=push_quantifier_weakly_inside(frm[2],quantifier,var)  
    return [frm[0],frm[1],tmp]
  elif thisop=="$block":
    return [quantifier,[var],frm]
  elif len(frm)==3 and frm[1]=="=>":
    if logic_contains_el(frm[0],var):
      return [quantifier,[var],frm]
    elif logic_contains_el(frm[2],var):  
      tmp=push_quantifier_weakly_inside(frm[2],quantifier,var)
      return [frm[0],"=>",frm[2]]
    else:
      return frm
  else:
    return [quantifier,[var],frm]        

# - - - - distribute and or - - - - - 

def distribute_and_or(frm):
  global combinations
  #debug_print("frm",frm)
  #debug_print("spaces",spaces)    
  if not frm: return frm  
  if type(frm)!=list: return frm
  # here frm is a list 
  thisop=frm[0]
  el=frm
  if thisop=="forall" or thisop=="exists":       
    res=[thisop,frm[1]]   
    for el in frm[2:]:
      newel=distribute_and_or(el)
      res.append(newel)
    return res
  elif thisop=="$block":
    return frm   
  elif thisop=="and":
    res=["and"]
    for el in frm[1:]:
      newel=distribute_and_or(el)
      res.append(newel)
    return res
  elif thisop=="or":
    #debug_print("frm2",frm)
    res=["and"]
    andterms=[]
    #simpters=[]
    haveand=False
    for el in frm[1:]: 
      #debug_print("el",el)  
      newel=distribute_and_or(el)
      newel=prop_flatten_logic_term(newel)
      #debug_print("newel",newel)
      if newel and type(newel)==list and newel[0]=="and":
        andterms.append(newel[1:])
        haveand=True
      else:
        andterms.append([newel])
    if haveand:    
      combinations=[]
      #debug_print("andterms",andterms)
      #print(andterms)
      combine(andterms, [])
      #debug_print("combinations",combinations)
      #print(combinations)
    else:
      frm=prop_flatten_logic_term(frm)
      return frm
    for el in combinations:
      if len(el)>1:
        newel=["or"]+el
      else:
        newel=el
      res.append(newel)
    return res
  else:
    return frm


    
def combine(terms, accum):
  global combinations
  last = (len(terms) == 1)
  n = len(terms[0])
  for i in range(n):
    #item = [accum] + [terms[0][i]]
    item = [terms[0][i]]+accum
    if last:
      combinations.append(item)
    else:
      combine(terms[1:], item)

# ==== logic augmentation ========

def default_to_confidence_augment_logic_list(ctxt,logic):
  if not logic: return logic
  if type(logic)!=list: return logic
  newlogic=[]
  for el in logic:
    #debug_print("el",el)
    newlogic.append(el)
    if type(el)==dict and ("@confidence" in el): 
      continue    
    if type(el)==dict and not ("@logic" in el): 
      continue 
    if type(el)==dict:
      ellogic=el["@logic"]
    else:
      ellogic=el  
    if not ellogic or type(ellogic)!=list:
      continue 
    foundblocker=False
    poscount=0
    negcount=0
    for atom in ellogic:
      if type(atom)!=list: continue
      if atom[0]=="$block":
        foundblocker=True
      elif atom[0][0]=="-":
        negcount+=1  
      else:
        poscount+=1  
    #debug_print("poscount,foundblocker",(poscount,foundblocker))    
    if foundblocker and poscount==0:
      newellogic=[]
      for atom in ellogic:
        if type(atom)!=list or atom[0]!="$block":
          newellogic.append(atom)
      if type(el)==dict:    
        newel=el.copy()
      else:
        newel={}  
      newel["@logic"]=newellogic
      newel["@confidence"]=0.3
      newlogic.append(newel)
  return newlogic        

# ==== logic unit derivation and subsumption ========

def subsume_simplify_clause_list(ctxt,logiclist):
  #return logiclist
  res=[]
  clauseres=[]
  for listel in logiclist:
    if not listel: continue
    if (type(listel)==dict and ("@logic" in listel) and
        not ("@confidence" in listel)):
      clause=listel["@logic"]
    elif type(listel)==list:
      clause=listel
    else:
      res.append(listel)
      continue        
    if is_tautology(clause):
      continue
    found=False
    for procclause in clauseres:
      if clause==procclause: 
        found=True
        break
      #if procclause in clause:
      #  found=True
      #  break      
    if not found:
      res.append(listel)
      clauseres.append(clause)
  res2=[]
  clauseres2=[]
  for listel in reversed(res):
    if not listel: continue
    if (type(listel)==dict and ("@logic" in listel) and
        not ("@confidence" in listel)):
      clause=listel["@logic"]
    elif type(listel)==list:
      clause=listel
    else:
      res2.append(listel)
      continue  
    found=False  
    for procclause in clauseres2:
      if clause==procclause: 
        found=True
        break
      #if procclause in clause:
      #  found=True
      #  break      
    if not found:
      res2.append(listel)
      clauseres2.append(clause)
  res2.reverse()    
  return res2      

def are_negated_preds(p1,p2):
  if type(p1)!=str or type(p2)!=str: return False
  if p1[0]=="-":
    if p1[1:]==p2: return True
  elif p2[0]=="-":
    if p2[1:]==p1: return True
  return False

def is_tautology(logiclist):
  for pos in range(0,len(logiclist)):
    a1=logiclist[pos]
    if type(a1)!=list: continue
    for a2 in logiclist[pos+1:]:
      if type(a2)!=list: continue
      if are_negated_preds(a1[0],a2[0]) and a1[1:]==a2[1:]:
        return True
  return False

# ==== logic unit cuts ========


def cut_simplify_clause_list(ctxt,logiclist):
  #return logiclist    
  cutters=[]
  for listel in logiclist:
    if not listel: continue
    if (type(listel)==dict and ("@logic" in listel) and
        not ("@confidence" in listel)):
      clause=listel["@logic"]
    elif type(listel)==list:
      clause=listel
    else:        
      continue  
    if (clause[0] in ["isa","-isa"] and type(clause[2])==str and 
        clause[2].startswith(det_constant_prefix) and 
        clause[1] in clause[2]):
      negclause=clause.copy()
      if clause[0][0]=="-":
        negclause[0]==clause[0][1:]
      else:
        negclause[0]="-"+clause[0]      
      cutters.append(negclause)
  res=[]
  #debug_print("cutters",cutters)
  for listel in logiclist:
    #debug_print("listel",listel)
    if not listel: continue
    if (type(listel)==dict and ("@logic" in listel)):
      clause=listel["@logic"]
    elif type(listel)==list:
      clause=listel
    else:       
      res.append(listel) 
      continue
    if (not clause) or clause[0]!="or" or len(clause)<3:
      res.append(listel)
      continue
    newclause=[]
    cuts=0
    for literal in clause:
      if type(literal)==str:
        newclause.append(literal)
      elif not(literal in cutters):
        newclause.append(literal)        
      elif len(clause)-cuts<3:
        newclause.append(literal)
      else:
        cuts+=1    
    #debug_print("cuts",cuts)    
    if cuts>0:
      newlistel=listel.copy()
      newlistel["@logic"]=newclause
      res.append(newlistel)
    else:
      res.append(listel)  
  #debug_print("res",res)
  #sys.exit(0)      
  return res




# ==================

def xpost_process_logic_atom(atom,boundvars):
  if not atom: return atom
  if type(atom)!=list: return atom
  res=[]
  i=0

  leading=atom[0]  
  isneg=False
  if leading[0]=="-": 
    isneg=True
    leading=leading[1:]

  if rdfstyle and leading in ["isa","prop","has","has_name"]:   
    if isneg: newleading="-$arc"
    else: newleading="$arc"    
    label=leading
    if leading=="isa": label="rdf:type"
    elif leading=="has_name": label="rdf:label"
    if leading in ["has_name"]: value=atom[1]
    else: value=post_process_logic_term(atom[1],1,boundvars)
    res=[newleading,
          post_process_logic_term(atom[2],2,boundvars),
          label,
          value]
    return res
  elif rdfstyle and leading in ["rel2"]:   
    if isneg: newleading="-$arc"
    else: newleading="$arc"    
    label=atom[1]
    res=[newleading,
          post_process_logic_term(atom[2],2,boundvars),
          label,
          post_process_logic_term(atom[3],3,boundvars)]
    return res    
  else:  
    for term in atom:
      newterm=post_process_logic_term(term,i,boundvars)
      res.append(newterm)
      i+=1
    return res


def xpost_process_logic_term(term,pos,boundvars):
  if not term: return term
  i=0
  if type(term)==list:
    res=[]
    for el in term:
      newel=post_process_logic_term(el,i,boundvars)
      res.append(newel)
      i+=1
    return res  
  # here term is not a list
  if term in boundvars:
    return term  
  elif term in nlpglobals.logic_ops or term in ["$not"]: #["and","or","not","$not","&","<=","=>","<=>"]:
    return term
  if rdfstyle and pos>0:
    if not term[0] in ["?","$"]:
      return "<"+term+">"
  else:  
    return term




# =========== the end ==========
