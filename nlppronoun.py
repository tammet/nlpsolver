# Pronoun guesser for the nlpsolver.
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
import math

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

# small utilities are in nlputils.py
from nlputils import *

from nlpglobals import *

import nlpproperlogic
import nlptologic
import nlpprover

# =========== code ==========

pronoun_debug=False

def resolve_pronoun(ctxt,sentence,word,tree,verb=None,otherword=None):
  #debug_print("resolve pronoun word",word)
  #debug_print("resolve pronoun tree",tree)
  #debug_print("resolve pronoun ctxt[passed_words]",ctxt["passed_words"]) 
  #debug_print("resolve pronoun ctxt[objects]",ctxt["objects"])
  if not word: return None
 
  if pronoun_debug:
    print("resolve pronoun word",word)

  if word["lemma"] in ["who","that","whom","which"]:
    parent=get_parent(sentence,word)
    #debug_print("resolve pronoun parent",parent)
    # go up through parent
    if parent and parent["deprel"] in ["acl:relcl"]:
      parentparent=get_parent(sentence,parent)
      if (parentparent and 
          parentparent["deprel"] in ["obj","subj","nsubj"]):       
        #debug_print("  word",word)
        #debug_print("  parentparent",parentparent)
        #debug_print("  ctxt[passed_words]",ctxt["passed_words"])
        #debug_print("  ctxt[objects]",ctxt["objects"])
        #debug_print("resolve pronoun parentparent",parentparent)
        object_det=nlpproperlogic.get_word_det(ctxt,sentence,parentparent)  
        #debug_print("  object_det",object_det)
        if object_det:
          objconst=nlpproperlogic.make_determined_constant(ctxt,sentence,parentparent,object_det,None)
        else:  
          objconst=nlpproperlogic.find_make_constant(ctxt,sentence,parentparent)
        return [objconst,parentparent]
    # get previous word
    previous=nlptologic.get_previous_word(sentence,word)
    if previous and previous["upos"] in ["NOUN","PROPN"]:
      objconst=nlpproperlogic.find_make_constant(ctxt,sentence,previous)
      return [objconst,previous]

  locals=ctxt["passed_words"]  
  #debug_print("resolve pronoun locals",locals)

  if verb: verb=nlpproperlogic.get_thing(verb)
  if type(verb)==dict: verblemma=verb["lemma"] 
  else: verblemma=None   
  if otherword: otherword=nlpproperlogic.get_thing(otherword)
  if type(otherword)==dict:otherwordlemma=otherword["lemma"]
  else: otherwordlemma=None

  candidate_objects=ctxt["objects"]
  candidate_objects=candidate_objects+locals
  i=0
  candidate_results=[]
  #debug_print("candidate_objects",candidate_objects)
  if pronoun_debug:
    print("candidate_objects")
    for el in candidate_objects:
      print(el)
  for object in reversed(candidate_objects):
    #debug_print("candidate object",object)
    if unknownsubject in object[0]: continue
    i+=1
    score=0
    if (word["lemma"]==object[1]["lemma"] and
        word["upos"] in ["PRON"] and 
        object[1]["upos"] in ["PRON"]):
      score+=10
    if object in locals:
      #debug_print("in locals")
      objword=object[1]
      if not(objword["upos"] in ["NOUN","PROPN"]):
        score-=1
      if object[2] in ["subject"]:
        score+=1 
      if objword["lemma"] in ["person","thing"]:
        score+=3
      #debug_print("in locals, score 1",score)   
    else:  
      score=score-math.log(i) # older words are worse
      #debug_print("not in locals, score 1",score)
    objword=object[1]
    if word["lemma"] in ["he","she","it","this","they","these","those"]:
      if objword["lemma"] in person_names:
        gender=person_names[objword["lemma"]]
      elif objword["lemma"] in gendered_words:   
        gender=gendered_words[objword["lemma"]]
      else:
        gender=None

      #debug_print("objword",objword)
      #debug_print("gender",gender)  
      #debug_print("is_subclass(ctxt,lemma1,lemma2)",nlpprover.is_subclass(ctxt,"animal",objword["lemma"]))
      #debug_print("is_subclass(ctxt,lemma1,lemma2)",nlpprover.is_subclass(ctxt,"person",objword["lemma"]))      

      if word["lemma"] in ["he"]:
        if gender=="m": score+=10
        elif gender=="f":  score-=20
      elif word["lemma"] in ["she"]:
        if gender=="m": score-=20
        elif gender=="f":  score+=10      
      elif word["lemma"] in ["it","this"]:
        if gender=="m": score-=5
        elif gender=="f":  score-=5
        elif objword["lemma"] in ["thing","object"]: score+=5          
      elif word["lemma"] in ["they"]:
        if gender=="m": score+=5
        elif gender=="f":  score+=5  
      elif word["lemma"] in ["these","those","this"]:
        if gender=="m": score-=2
        elif gender=="f":  score-=2

      if word["lemma"] in ["he","she","it","this"] and word_has_feat(word,"Number","Sing"): 
        if word_has_feat(objword,"Number","Sing"):
          score+=10
        elif word_has_feat(objword,"Number","Plur"):
          score-=10  
      elif ((word["text"] in ["they","these","those","They","These","Those"]) or
            (word["lemma"] in ["this"] and word_has_feat(word,"Number","Plur"))):   
        if word_has_feat(objword,"Number","Sing"):
          if "ner" in objword and "PERSON" in objword["ner"]:
            score-=10
          else:
            score-=5
        elif word_has_feat(objword,"Number","Plur"):
          score+=10

      if word["lemma"] in ["he","she"]:
        if gender:
          None
        elif "ner" in objword and "PERSON" in objword["ner"]:
          score+=5
        elif objword["lemma"] in ["person","human"]:
          score+=5  
        elif word["lemma"] in ["they"] and "ner" in objword and "ORG" in objword["ner"]:
          score+=5  
        else:  
          isperson=nlpprover.is_subclass(ctxt,"person",objword["lemma"])
          if isperson:
            score+=5
          else:          
            isanimal=nlpprover.is_subclass(ctxt,"animal",objword["lemma"])
            if isanimal: 
              score+=3
            else:
              score-=20        

      if word["lemma"] in ["this","these"]:
        if objword["deprel"] in ["obj"]:
          score+=1
      elif objword["deprel"] in ["subj","nsubj"]:
        score+=1 
    #debug_print("object score",score)
    if pronoun_debug:
      print("object, lemma, score",[object[0],object[1]["lemma"],score])
    if score>0-4:
      candidate_results.append([score,object])

  if not candidate_results: return None

  sortedres=sorted(candidate_results,key=lambda x : x[0],reverse=True)
  #debug_print("sortedres",sortedres)
  filtered=[]
  for el in sortedres:
    if not filtered:
      filtered.append(el)
      continue
    score=el[0]
    foundbetter=False
    for oldels in filtered:
      if oldels[0]-score > 1.5: 
        foundbetter=True
        break
    if not foundbetter:
      filtered.append(el)

  #debug_print("filtered",filtered)
  if len(filtered)<2:
    return [filtered[0][1][0],filtered[0][1][1]]
  
  newlist=[]
  for el in filtered:
    if verblemma:
      if verblemma in ["be"]:
        if tree and type(tree)==list and tree[0] in ["sv","svo"]:
          useword=tree[1][0]["lemma"]
          related1=complex_relatedness(ctxt,el[1][1]["lemma"],useword)
        else: 
          useword=None
          related1=0  
      else:
        related1=complex_relatedness(ctxt,el[1][1]["lemma"],verblemma)      
    else: related1=0
    if otherwordlemma: related2=complex_relatedness(ctxt,el[1][1]["lemma"],otherwordlemma)      
    else: related2=0
    #debug_print("word,verb,related1,otherword,related2",[el[1][1]["lemma"],verblemma,related1,otherwordlemma,related2])
    newscore=0
    if related1>0.05:
      newscore+=related1
    if related2>0.05:
      newscore+=related1
    newlist.append([newscore,el[1]])
  sortedres=sorted(newlist,key=lambda x : x[0],reverse=True)
  #debug_print("sortedres2",sortedres)  
  if pronoun_debug:
    print("sortedres")
    for el in sortedres:
      print(el)      
  return [sortedres[0][1][0],sortedres[0][1][1]]

def complex_relatedness(ctxt,word1,word2):
  related1=nlpprover.get_relatedness(ctxt,word1,word2)
  related2=nlpprover.get_relatedness(ctxt,word2,word1)
  if related1>related2: related=related1
  else: related=related2
  return related


# =========== code ==========
 