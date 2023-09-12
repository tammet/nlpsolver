# Pattern matching rewriter for the nlpsolver.
#
#-----------------------------------------------------------------
# Copyright 2023 Tanel Tammet (tanel.tammet@gmail.com)
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
import json
import pprint
import http.client
import urllib.parse

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
import nlpglobals
from nlputils import *

# ===== configuration ==================

replacement_filename="replacements.txt"
replacement_splitter="==>"

# ===== text replacements ==================


def rewrite_sentence(ctxt,sentence):  
  #debug_print("new rewrite_sentence called on",sentence)
  wordlist=make_namified_replacement_wordlist(sentence)
  #debug_print("wordlist",wordlist)
  loopcount=0
  while True:
    newwordlist=rewrite_text_list(ctxt,wordlist)
    if newwordlist and newwordlist!=wordlist:
      wordlist=de_namify_replacement_wordlist(newwordlist)
      newtext=" ".join(wordlist)
      tmp=server_parse(newtext)
      if "doc" in tmp:
        sentence=tmp["doc"][0]
        #for word in sentence:
        #  print("word",word) 
      else:
        show_error("parsing the replaced sentence failed, exiting: "+str(newtext))
        sys.exit(0)   
      #debug_print("made new sentence by text replacements",sentence)

    newsentence=rewrite_with_complex_rules_once(ctxt,sentence)
    if newsentence==sentence:
      break    

    sentence=newsentence
    wordlist=make_namified_replacement_wordlist(sentence)   
    loopcount+=1
    if loopcount>10: break
  #debug_print("loopcount ",loopcount)  
  debug_print("rewrite_sentence gave wordlist"," ".join(wordlist))
  #debug_print("new rewrite_sentence gave sentence",sentence)
  #sys.exit(0)  
  return sentence

def make_namified_replacement_wordlist(sentence):
  wordlist=[]
  for el in sentence:
    if el["upos"]=="PROPN" and el["ner"]!='O':
      wordlist.append("#name#"+el["text"])
    else:  
      wordlist.append(el["text"].lower())  
  return wordlist

def de_namify_replacement_wordlist(wordlist):
  res=[]
  count=0
  for el in wordlist:
    if el.startswith("#name#"):
      res.append(el[len("#name#"):])
    elif count==0 and not el[0].isupper():
      res.append(el[0].upper()+el[1:])
    else:
      res.append(el)
    count+=1  
  return res      

def rewrite_text_list(ctxt,wordlist):
  count=0
  while True:
    made_changes=False
    # --- collect candidate rules ---
    text_rule_candidates=collect_rule_candidates(ctxt,wordlist,nlpglobals.replacement_text_rules)    
    if not text_rule_candidates:
      return wordlist  
    # --- run over candidate rules ---  
    for rule in text_rule_candidates:
      newlist = text_sentence_rewrite(ctxt,wordlist,rule[0],rule[1])
      if newlist:
        wordlist=newlist        
        made_changes=True
    if not made_changes:
      return wordlist   
    count+=1
    if count>100: 
      return wordlist
    

def rewrite_with_complex_rules_once(ctxt,sentence): 
  # --- collect candidate rules ---
  wordlist=[]
  for el in sentence:
    wordlist.append(el["text"])
    if "lemma" in el and el["lemma"]!=el["text"]:
      wordlist.append(el["lemma"])
  rule_candidates=collect_rule_candidates(ctxt,wordlist,nlpglobals.replacement_complex_rules)    
  if not rule_candidates:
    #debug_print("rewrite_with_complex_rules_once found no usable complex rules")
    return sentence
  # --- run over candidate rules --- 
  text=" ".join(wordlist)
  for rule in rule_candidates: 
    (newtext,newsentence)=parsed_sentence_rewrite(ctxt,text,sentence,rule[0],rule[1])  
    if newsentence!=sentence:
      text=newtext
      sentence=newsentence
  return sentence
    
def collect_rule_candidates(ctxt,wordlist,ruledict):
  #print("wordlist",wordlist)
  #print("ruledict",ruledict)
  text_rule_candidates=[]
  seenwords=[]
  count=0
  for word in wordlist:  
    if word in seenwords: continue
    if word in ruledict:
      text_rule_candidates=text_rule_candidates+ruledict[word]
    elif count==0 and word[0].isupper() and word.lower() in ruledict:
      text_rule_candidates=text_rule_candidates+ruledict[word.lower()]
    seenwords.append(word) 
    count+=1
  if not text_rule_candidates: return []
  text_rule_candidates.sort(key=lambda x: len(x[0]), reverse=True)
  return text_rule_candidates

def text_sentence_rewrite(ctxt,wordlist,left,right):
  if len(left)==1:
    try:
      start = wordlist.index(left[0], 0)
    except ValueError:
      return None
    res=wordlist[:start]+right+wordlist[start+1:] 
    return res 
  start = 0
  item=left[0]
  while True:    
    try:
      start = wordlist.index(item, start)      
    except ValueError:
      return None
    if len(left)+start>len(wordlist):
        return None
    j=1
    matched=True
    while j<len(left):
      if left[j]!=wordlist[start+j]:
        matched=False
        break
      j+=1
    if matched:  
      res=wordlist[:start]+right+wordlist[start+len(left):]
      return res    
    start+=1 


def parsed_sentence_rewrite(ctxt,text,sentence,chunk,matched):
  #print("text",text)
  #print("sentence",sentence)
  #print("chunk",chunk)
  matchdata=parsed_sentence_match_sequence(sentence,chunk)
  #print("matchdata",matchdata)
  if not matchdata: return (text,sentence)
  firstpos=matchdata[0]
  lastpos=matchdata[1]
  match=matchdata[2]
  newmatched=[]
  #print("matched",matched)
  for el in matched:
    #print("el",el)
    if type(el)==str and el[0]=="$" and el[1:].isnumeric():
      newmatched.append(match[int(el[1:])])
    elif type(el)!=list: newmatched.append(el)
    #elif el[0]=="$none": continue
    elif el[0]=="$": newmatched.append(match[el[1]])
    elif el[0]=="$makepercentage": newmatched.append(int(float(match[el[1]]["text"])*100))
    elif el[0]=="$measure_adv_to_noun": 
      #debug_print("match",match)
      #debug_print("el",el)
      #debug_print("type el 1",type(el[1]))
      newmatched.append(measure_adv_to_noun(match[el[1]]["lemma"]))  
  newtext=make_sentence_from_sequence_match(sentence,firstpos,lastpos,newmatched)  
  data = server_parse(newtext)
  newsentence=data["doc"][0] 
  return (newtext,newsentence)

def parsed_sentence_match_sequence(sp,chunk):
  if not sp or not chunk: return None
  spx=0
  while spx<len(sp):        
    reslst=[]
    found=True
    sptmp=spx
    firstpos=None
    lastpos=None
    for chunkx in range(0,len(chunk)):
      if len(sp)<=sptmp: return False
      chunkel=chunk[chunkx]
      spel=sp[sptmp]
      optdrop=False
      opt=False
      onematch=False
      if type(chunkel)==list and chunkel[0]=="$optdrop":
        chunkel=chunkel[1]
        optdrop=True
      if type(chunkel)==list and chunkel[0]=="$opt":
        chunkel=chunkel[1]
        opt=True  
      if type(chunkel)==list:
        if spel["lemma"] in chunkel:
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):  
          found=False
          break
        elif opt: reslst.append(None)
      elif chunkel=="$number":
        if spel["upos"]=="NUM":
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):
          found=False
          break
        elif opt: reslst.append(None)
      elif chunkel=="$probnumber":
        if spel["upos"]=="NUM" and probfloat_str(spel["text"]):
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):
          found=False
          break
        elif opt: reslst.append(None)  
      elif chunkel=="$unitword":
        if is_unitword(spel["lemma"]): # in ["kilometer","meter"]:
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):
          found=False
          break
        elif opt: reslst.append(None)
      elif chunkel=="$article":
        if spel["lemma"] in ["a","the","an"]:
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):
          found=False
          break  
        elif opt: reslst.append(None)
      elif chunkel=="$certaintyphrase":
        if spel["lemma"] in nlpglobals.lemma_confidences:
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):
          found=False
          break   
        elif opt: reslst.append(None)
      elif chunkel=="$nounphrase":    
        phraselst=[]               
        for i in range(sptmp,len(sp)):
          word=sp[i]
          if (word["upos"] in ["NOUN","PROPN","ADJ","DET"] or
              word["lemma"] in nlpglobals.complex_question_words):
            phraselst.append(word)
            if firstpos==None: firstpos=i
          else:            
            break  
        if phraselst:
          onematch=True
          if not optdrop: reslst.append(phraselst)
          sptmp+=len(phraselst)-1
        elif not (optdrop or opt):
          found=False          
          break               
        elif opt: reslst.append(None)
      elif type(chunkel)!=list:
        if spel["lemma"] in chunkel:
          onematch=True
          if not optdrop: reslst.append(spel)
        elif not (optdrop or opt):  
          found=False
          break
        elif opt: reslst.append(None)  
      # last actions inside chunkel loop:  
      if onematch:
        if firstpos==None: firstpos=sptmp
        if chunkx==len(chunk)-1: lastpos=sptmp
        sptmp+=1     

    # all chunkels have been looped over
      
    if found:
      return [firstpos,lastpos,reslst]
    else:
      spx+=1      
  return None

def probfloat_str(s):
  try:
    n=float(s)
    if n<1 and n>0: return True
    else: return False
  except:
    return False  

def make_sentence_from_sequence_match(sentence,firstpos,lastpos,matched):
  lst=[]
  firstword=None
  lastword=None
  lm=len(matched)
  for i in range(0,lm):
    el=matched[i]
    if not el: 
      continue
    elif el=="$none":
      continue
    elif type(el)==str:
      lst.append(el)
    elif type(el)==int:
      lst.append(str(el))
    elif type(el)==dict:
      lst.append(el["text"])  
      if not firstword: firstword=el
      if i==lm-1: lastword=el
    #elif type(el)==list and el[0]=="$drop":
    #  
    elif type(el)==list:
      for subel in el:
        lst.append(subel["text"])
        if not firstword: firstword=subel
        if i==lm-1 and subel==el[-1]: lastword=subel
  prelist=list(map(lambda x: x["text"],sentence[0:firstpos]))
  postlist=list(map(lambda x: x["text"],sentence[lastpos+1:]))
  res=" ".join(prelist+lst+postlist)     
  return res     


# -------------- parsing datafile and preparing the dataset -----------------



def read_replacement_data():
  try:
    f=open(replacement_filename,"r")
  except:
    show_error("failed to read the replacement file "+str(replacement_filename)+", exiting")
    sys.exit(0)  
  lines=f.readlines()
  textpatterns={}
  complexpatterns={}
  for line in lines:
    #print(line)
    line=line.strip()
    if not line: continue
    if line.startswith("#"): continue
    parts=line.split(replacement_splitter)
    #print(parts)
    if not parts or len(parts)!=2:
      show_error("no separator in the replacement file "+str(replacement_filename)+
                 ": "+line+", exiting")
      sys.exit(0)
    leftpattern=process_replacement_pattern(parts[0].strip(), line, True)
    rightpattern=process_replacement_pattern(parts[1].strip(), line, False)
    if not leftpattern or not rightpattern or not leftpattern[0] or not rightpattern[0]:
      show_error("misunderstood patterns in the replacement file "+str(replacement_filename)+
                 ": "+line+", exiting")
      sys.exit(0)
    rule=[leftpattern[0],rightpattern[0]]  
    if leftpattern[2] and rightpattern[2]:
      for el in leftpattern[1]:
        if el in textpatterns: textpatterns[el].append(rule)         
        else: textpatterns[el]=[rule]
    else:
      for el in leftpattern[1]:
        if el in complexpatterns: complexpatterns[el].append(rule)
        else: complexpatterns[el]=[rule]   
  #print("textpatterns",textpatterns)      
  #print("complexpatterns",complexpatterns)
  #sys.exit(0)         
  return [textpatterns,complexpatterns]


def process_replacement_pattern(pattern,line,makeindex):
  #print("pattern",pattern)
  indexword=None
  puretext=True
  newpattern=[]
  origpattern=pattern
  pattern=pattern.split(" ")
  #print("pattern",pattern)
  i=0
  while i<len(pattern):
    el=pattern[i]
    el=el.strip()
    #print("el",el)
    if not el: 
      i+=1
      continue
    if el.startswith("["):
      puretext=False
      endfound=False
      newel=el[1:].strip()
      if newel.endswith("]"): 
        newel=newel[:-1].strip()
        if makeindex:
          if indexable_pattern_element(newel):
            if not indexword: indexword=newel
            elif len(indexword)<len(newel): indexword=newel
        endfound=True
      if newel:
        part=[convert_pattern_element(newel)]
      else:
        part=[]      
      if not endfound: i+=1
      while i<len(pattern) and not endfound:
        el=pattern[i]
        el=el.strip() 
        if not el: 
          i+=1
          continue       
        if el.endswith("]"):
          endfound=True
          newel=el[:-1].strip()
          if newel:
            part.append(convert_pattern_element(newel))
          break
        else:
          part.append(convert_pattern_element(el))
        i+=1  
      if not endfound:
        show_error("misunderstood pattern in the replacement file "+str(replacement_filename)+
                 ": "+line+", exiting")
        sys.exit(0)
      newpattern.append(part)
    elif el.startswith("$"):
      puretext=False
      newpattern.append(el)
    else:
      newpattern.append(el) 
      if makeindex and indexable_pattern_element(el):
        if not indexword: indexword=el
        elif len(indexword)<len(el): indexword=el
    i+=1  

  if indexword: indexword=[indexword]
  elif makeindex and not indexword:    
    lst=[]
    for el in newpattern:
      if type(el)==list:        
        for elel in el:
          if indexable_pattern_element(elel):
            lst.append(elel)
        if lst: break    
    if not lst:
      show_error("underrepresented pattern in the replacement file "+str(replacement_filename)+
                 ": "+line+", exiting")
      sys.exit(0)
    else:
      indexword=lst  
  #print("newpattern",newpattern)    
  #print("indexword",indexword)  
  #print("puretext",puretext)  
  return [newpattern,indexword,puretext]

def indexable_pattern_element(x):
  if not x: return False
  if x.isnumeric(): return False
  elif x[0]=="-" and x[1:].isnumeric(): return False
  elif x[0]=="$": return False
  else: return True

def convert_pattern_element(x):
  if not x: return x
  if x.isnumeric(): return int(x)
  elif x[0]=="-" and x[1:].isnumeric(): return int(x)
  else: return x 
