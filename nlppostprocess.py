# Optional post-processing of the logic created by the nlpsolver.
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
import nlpglobals

rdfstyle=True # set this to False for no changes

# ==== post-processing code  =======

def post_process_logic_list(lst):   
  if not lst: return lst  
  if type(lst)!=list: return lst
  res=[]
  for frm in lst:
    newfrm=post_process_logic_formula(frm)
    res.append(newfrm)
  return res

def post_process_logic_formula(frm,boundvars=[]):     
  if not frm: return frm  
  if type(frm)==dict: 
    newfrm=frm.copy()
    if "@logic" in newfrm:
      newlogic=post_process_logic_formula(newfrm["@logic"],boundvars)
      newfrm["@logic"]=newlogic
    elif "@question" in newfrm:
      newlogic=post_process_logic_formula(newfrm["@question"],boundvars)
      newfrm["@question"]=newlogic
    return newfrm
  if type(frm)!=list: return frm
  # here frm is a list
  if type(frm[0])==list:
    res=[]
    for el in frm:
      newel=post_process_logic_formula(el,boundvars)
      res.append(newel)
    return res
  thisop=frm[0]
  if thisop in ["forall","exists"]: #,"$block"]:
    res=[thisop,frm[1]]
    boundvars=boundvars+frm[1]
    for el in frm[2:]:
      newel=post_process_logic_formula(el,boundvars)
      res.append(newel)
    return res
  elif thisop in ["$block"]:
    res=[thisop,frm[1]]
    for el in frm[2:]:
      newel=post_process_logic_formula(el,boundvars)
      res.append(newel)
    return res  
  elif thisop in ["and","or","not","$not","=>","<=","<=>"]:
    res=[]
    for el in frm:
      newel=post_process_logic_formula(el,boundvars)
      res.append(newel)
    return res
  # here the formula seems to be atomic
  res=post_process_logic_atom(frm,boundvars)
  return res

def post_process_logic_atom(atom,boundvars):
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


def post_process_logic_term(term,pos,boundvars):
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
