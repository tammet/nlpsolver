# Making a nice nlp answer from json answer
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
import json

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
import nlpglobals

# small utilities are in nlputils.py
from nlputils import *

# uncertainty analysis and encoding in nlpuncertain.py
from nlpuncertain import *

# ==== making a nice nlp result from the prover result ====

def make_nlp_result(doc,rawresult,logic_objects,question_type):
  #debug_print("doc",doc)       
  explain=options["prover_explain_flag"]
  show_logic=options["show_logic_flag"]
  if show_logic: show_logic_details="full"
  else: show_logic_details="partial" #False #"full"
  if not doc: return
  question_sentence=doc[-1]
  prefer_concrete=True
  for el in question_sentence: 
    if el["lemma"] in ["what","What"]: prefer_concrete=False

  if "objects" in logic_objects: objects=logic_objects["objects"]
  else: objects=None
  if "question_sentence" in logic_objects: question_sentence=logic_objects["question_sentence"]
  else: question_sentence=None
  if "logic_sentence_map" in logic_objects: logic_sentence_map=logic_objects["logic_sentence_map"]
  else: logic_sentence_map=None
 
  if explain or show_logic: print("Answer:")  
  data=None    
  try:
    data=json.loads(rawresult)
  except:
    if options["prover_print"] or options["debug_print_flag"]:
      sp=rawresult.split("\n")
      tmp=[]
      okline=False
      for line in sp:
        if line.startswith("= showing final result ="):
          okline=True
        elif line.startswith("{\"error\":"):
          res="Prover returned an error: "+line
          return res  
        elif okline: 
          tmp.append(line)
      if okline:
        s="\n".join(tmp)
        try:
          data=json.loads(s)
        except:  
          show_error("prover output is not a correct json")  
          sys.exit(-1)
      else:
        show_error("cannot find required parts of the prover output, using the given print level")    
    else:      
      show_error("prover output is not a correct json")  
      sys.exit(-1)
  if data and "error" in data:
    res="Prover returned an error: "+data["error"]
    return res
  elif not ("result" in data) or data["result"]!="answer found":
    return "Unknown." 
  # - - - now we have an answer - - - -
  answers=data["answers"]
  if len(answers)>1:
    #res="There are several answers: "
    res=""
  else:
    res=""
  answercount=0
  foundconcrete=False
  foundgeneric=False
  doublecount=0
  dummycount=0
  concretecount=0  
  genericcount=0 
  trivialcount=0
  explanations=[]
  answerset=[]
  if answers:
    answers=sorted(answers,key=lambda x: answer_goodness(x),reverse=True)
  for answer in answers:
    #debug_print("answer",(answer,answer_goodness(answer)))
    if answer["answer"] in answerset: 
      doublecount+=1
      continue
    answerset.append(answer["answer"])
    if type(answer["answer"])==list:
      istrivial=False
      isconcrete=False
      isgeneric=False
      isdummy=False
      for subanswer in answer["answer"]:       
        ansval=subanswer[1]
        if is_useless_answer(answer["answer"][0],question_sentence,question_type):
          istrivial=True  
        elif type(ansval)==str and dummy_name in ansval:
          isdummy=True 
        elif type(ansval)==str and ansval.startswith("some_"):
          isgeneric=True  
        elif type(ansval)==str and not ansval.startswith("some_"):
          isconcrete=True
                
      if isconcrete:    
        foundconcrete=True
        concretecount+=1     
      if isgeneric:    
        foundgeneric=True
        genericcount+=1   
      if istrivial:
        trivialcount+=1    
      if isdummy:
        dummycount+=1  
   
  #debug_print("len(answers)",len(answers))  
  #debug_print("prefer_concrete,foundconcrete,foundgeneric",(prefer_concrete,foundconcrete,foundgeneric))
  #debug_print("answercount,trivialcount,doublecount,concretecount,genericcount,foundconcrete",(answercount,trivialcount,doublecount,concretecount,genericcount,foundconcrete) )
  if prefer_concrete and foundconcrete: okanswercount=concretecount
  elif (not prefer_concrete) and foundgeneric: okanswercount=genericcount-trivialcount
  else: okanswercount=(len(answers)-trivialcount)-doublecount  
  if okanswercount-dummycount>0: 
    okanswercount=okanswercount-dummycount
    nodummies=True    
  else:
    nodummies=False  
  #debug_print("answercount,okanswercount,doublecount",(answercount,okanswercount,doublecount))  
  #debug_print("okanswercount",okanswercount)
  answerset=[]
  for answer in answers:
    if answer["answer"] in answerset: continue
    if nodummies and type(answer["answer"])==list:
      found=False
      for el in answer["answer"]:
        if type(el)==str and dummy_name in el:
          found=True
          break
      if found: continue      
    answerset.append(answer["answer"])
    explanation=None
    #debug_print("answer",answer)
    if answer["answer"] in [True,False]:
      if answer["answer"]==True:
        oneres="true"
      else:
        oneres="false"
      if "confidence" in answer and answer["confidence"]<0.99:
        qualifier=get_probability_text_qualifier(answer["confidence"],answer["answer"])
        oneres=qualifier+" "+oneres
        oneres=oneres+" (confidence "+str(round(100*answer["confidence"]))+"%)"
      if explain: explanation=make_nlp_explanation(doc,answer,logic_objects,answer["answer"],show_logic_details) #objects,logic_sentence_map,
    else:
      if "confidence" in answer and answer["confidence"]<0.99: 
        confidence=answer["confidence"]
      else:
        confidence=1  
      oneres=""
      #debug_print("answer['answer']",answer["answer"])
      #print(answer["answer"])
      if len(answer["answer"])==1:
        if is_useless_answer(answer["answer"][0],question_sentence,question_type):          
          #debug_print("not use cp3",answer["answer"])
          continue
        elif prefer_concrete and foundconcrete and type(answer["answer"][0][1])==str and answer["answer"][0][1].startswith("some_"):
          #debug_print("not use cp1",answer["answer"])
          continue
        elif (not prefer_concrete) and foundgeneric and type(answer["answer"][0][1])==str and not (answer["answer"][0][1].startswith("some_")):
          #debug_print("not use cp2",answer["answer"])
          continue
        elif is_useless_answer(answer["answer"][0],question_sentence,question_type):          
          #debug_print("not use cp3",answer["answer"])
          continue
        elif prefer_concrete and foundconcrete and type(answer["answer"][0][1])==list:          
          #debug_print("not use cp4",answer["answer"])
          continue
        else:  
          oneres+=make_nlp_subanswer(doc,answer["answer"][0],confidence,objects,False)   
          if explain: explanation=make_nlp_explanation(doc,answer,logic_objects,False,show_logic_details) # objects,logic_sentence_map   
      elif len(answer["answer"])>1:
        count=0
        for ans in answer["answer"]:
          if count==0:
            oneres+=make_nlp_subanswer(doc,ans,confidence,objects,False)
          else:
            oneres+=" or "+make_nlp_subanswer(doc,ans,confidence,objects,False)
          count+=1
        if explain: explanation=make_nlp_explanation(doc,answer,logic_objects,False,show_logic_details)   #,objects,logic_sentence_map
    #oneres=oneres.capitalize()
    #debug_print("oneres,answercount,okanswercount",(oneres,answercount,okanswercount))
    if explanation:
      full_explanation=[str(oneres).capitalize(),explanation]
      explanations.append(full_explanation)        
    if answercount<okanswercount-2 and not(answer["answer"] in [True,False]): # and not(oneres and answercount==0):
      res+=oneres+", "  
    elif answercount==okanswercount-2 and not(answer["answer"] in [True,False]):
      res+=oneres+" and "   
    else:
      res+=oneres+". "      
    answercount+=1
  if res and type(res)==str and res[0].islower():
    res=res[0].upper()+res[1:]
  elif not res:
    res="Could not find an answer."  
  if explanations:    
    exp="\n\nExplained:"           
    for el in explanations:
      if el[0] in ["True"]:
        s="\n\n"+el[0]+" (proof by contradiction):\n"
      elif el[0] in ["False"]:
        s="\n\n"+el[0]+":\n"  
      else:  
        s="\n\n"+el[0]+":\n"   
      s=s+str(el[1])
      exp+=s
    res=res+exp  
  return res

def answer_goodness(ans):
  #debug_print("ans",ans)
  conf=ans["confidence"]
  length=0
  if "positive proof" in ans:
    length+=len(ans["positive proof"])
  if "negative proof" in ans:
    length+=len(ans["negative proof"]) 
  if "blockers" in ans:
    length+=5*len(ans["blockers"])     
  return conf*10000000-length  


def show_sentence_clauses(logic_objects):
  print("=== sentences mapped to clauses: === \n")
  if (list(filter(lambda x: "@name" in x, logic_objects["logic"])) and
      list(filter(lambda x: not ("@name" in x), logic_objects["logic"])) ):
    print("Non-sentence clauses:")  
  seen=[]
  for el in logic_objects["logic"]:
    if "@name" in el:
      #debug_print("el",el)
      if not(el["@name"] in seen):
        print(logic_objects["logic_sentence_map"][el["@name"]])
        seen.append(el["@name"])   
    if "@confidence" in el and el["@confidence"]<1:
      confidence=" Confidence "+str(round(el["@confidence"],3))
    else:
      confidence=""      
    if "@logic" in el:
      if el["@logic"][0]=="or":
        print("  "+make_classic_clause_str(el["@logic"][1:])+"."+confidence)
      else:
        print("  "+make_classic_clause_str(el["@logic"])+"."+confidence)     
    elif "@question" in el:
      if el["@question"][0]=="or":
        print("  question: "+make_classic_clause_str(el["@question"][1:])+".")
      else:
        print("  question: "+make_classic_clause_str(el["@question"])+".")

def show_objects(logic_objects):
  print("=== objects detected: === \n")  
  if not ("objects" in logic_objects): return
  objects=logic_objects["objects"]
  for object in objects:
    print(make_classic_clause_str(object[0]))
    if object[1]:
      print("  source:",object[1]["text"]+" (deprel: "+object[1]["deprel"]+", upos: "+object[1]["upos"]+")")
    logic=object[2]
    if logic and type(logic)==list:
      print("  logic:  ",end="")
      tmp=[]
      if (logic[0]=="and"):
        for el in logic[1:]:
          if el[0]==dummypredicate: continue
          el=list(filter(lambda x : type(x)!=list or x[0]!=confidence_function, el)) 
          if options["noproptypes_flag"]: el=remove_prop_extras_from_logic(el)
          s=make_classic_clause_str(remove_confidences_from_logic(el))
          tmp.append(s)
      else:
        logic=list(filter(lambda x: type(x)!=list or x[0]!=confidence_function, logic))
        if options["noproptypes_flag"]: logic=remove_prop_extras_from_logic(logic)
        tmp.append(make_classic_clause_str(remove_confidences_from_logic(logic)))
      print(" & ".join(tmp))              
    if len(object)>3 and object[3]:
      print("  names:  ",end="")
      tmp=[]
      for el in object[3]:
        tmp.append(el)
      print(", ".join(tmp))  
    if len(object)>4 and object[4]:
      print(object[4])
  

def is_useless_answer(answer,question_sentence,question_type):
  #debug_print("is_useless_answer answer",answer)
  #debug_print("is_useless_answer question_sentence",question_sentence)
  if not answer: return False
  if not question_sentence: return False
  if type(answer)!=list: return False
  #debug_print("is_useless_answer answer",answer)
  obj=answer[1]
  if len(answer)>2: obj2=answer[2]
  else: obj2=None
  if (question_type and "when" in question_type and obj2 and
      (type(obj2)!=list or obj2[0] not in [time_function])):
      return True
  if (question_type and "when" not in question_type and obj2 and
      (type(obj2)==list and obj2[0] in [time_function])):
      return True    
  if type(obj)!=str: return False
  if not obj.startswith("some_"): return False
  parts=obj.split("_")
  for part in parts[1:]:
    for word in question_sentence:
      if word["upos"]!="NOUN":
         continue
      if part==word["lemma"] or part==word["text"]:
        #debug_print("is_useless_answer returns True")
        return True
  return False

# takes an atom like ["$ans","Mike","John"]

def make_nlp_subanswer(doc,ans,confidence,objects,showobjid=True):
  #debug_print("make_nlp_subanswer ans",ans)
  res=""
  if len(ans)<3:    
    ansstr=make_answer_object_str(doc,ans[1],objects,showobjid)
    res+=ansstr
    if confidence<1:
      qualifier=get_probability_text_qualifier(confidence,None)
      res=qualifier+" "+res
    return res
  elif len(ans)==3 and (ans[1] in is_location_relations or ans[1] in is_time_relations):
    res=ans[1]+" "+make_answer_object_str(doc,ans[2],objects,showobjid) 
    if confidence<1:
      qualifier=get_probability_text_qualifier(confidence,None)
      res=qualifier+" "+res
    return res
  else:
    count=0    
    res="["
    for el in ans[1:]:      
      if count==len(ans)-2:
        ansstr=make_answer_object_str(doc,el,objects,showobjid)
        res+=", "
        res+=ansstr
      else:
        ansstr=make_answer_object_str(doc,el,objects,showobjid)
        res+=ansstr
      count+=1 
    res+="]"
    if confidence<1:
      qualifier=get_probability_text_qualifier(confidence,None)
      res=qualifier+" "+res  
  #debug_print(" make_nlp_subanswer res",res)     
  return res #.replace("_"," ")

def add_word_article_desc(doc,str,objects,isprop=False):
  #debug_print("add_word_article_desc str",str)
  #debug_print("add_word_article_desc objects",objects)
  if not str: return str     
  if str.startswith(det_constant_prefix): article="the"
  else: article=None
  if objects:
    for object in objects:
      if str==object[0] and object[1]:
        str=object[1]["text"]     
  if str[0].isupper(): return str

  if article:
    return "the "+str 
  elif (not isprop) and is_noun(doc,str): 
    #debug_print("is_noun str",str)
    if str[0] in ["a","e","i","o","u"]:
      return "an "+str
    else:
      return "a "+str
  elif str.startswith("some_"):
    strpart=str[len("some_"):]
    tmp=strpart  
    parts=tmp.split("_")
    kept=[]
    for i in range(0,len(parts)):
      part=parts[i]
      #debug_print("part",part)  
      if "person" in part and i<len(parts)-1:
        if parts[i+1]!="not":
          continue
      if part=="not":
        kept.append("which is")
      kept.append(part)
    tmp=" ".join(kept)  
    if tmp and tmp[0] in ["a","e","i","o","u"]:
      tmp="an "+tmp
    else:
      tmp="a "+tmp
    return tmp  
  else:
    return str.replace("_"," ")   

def make_answer_object_str(doc,el,objects,showobjid=True):
  #debug_print("make_answer_object_str el",el)
  #debug_print("make_answer_object_str objects",objects)  
  #debug_print("make_answer_object_str showobjid",showobjid)
  if not el: return "nothing"
  res=""
  if type(el)==str: 
    if el.startswith("some_"):
      res=add_word_article_desc(doc,el,objects)
      return res
    if unknownsubject in el: 
      return "Some unknown"   
    for obj in objects:
      if (el==obj[0] and len(obj)>3 and obj[3] and 
         ((not obj[2]) or (obj[1] and obj[1]["upos"] in ["PROPN"]))):
        res=obj[3][-1]
        return res #+" "+term_to_id(el)
      elif el==obj[0] and ((not obj[2]) or (obj[1] and obj[1]["upos"] in ["PROPN"])):
        res=obj[1]["text"]
        if showobjid:
          return res+" "+term_to_id(el)
        else:
          return res  
      elif el==obj[0] and obj[2]:
        #debug_print("el",el)
        res=make_name_from_logic(doc,el,obj[2],obj[1])
        #debug_print("res",res)
        origres=res    
        if el.startswith(det_constant_prefix): 
          res="the "+res 
        elif el.startswith(skolem_constant_prefix):
          res=add_word_article_desc(doc,res,objects) #"a "+res
        if showobjid:
          if " " in origres:
            return res
          else:
            return res+" "+term_to_id(el)
        else:
          return res        
    return el
  if type(el)==dict: 
    return str(dict)
  if el and type(el)==list and (el[0] in ["of"]):
    arg1=make_answer_object_str(doc,el[1],objects)
    arg2=make_answer_object_str(doc,el[2],objects)
    res=arg1+" of "+arg2
    res+=add_word_article_desc(doc,res,objects)
    if showobjid:
      return res+" "+term_to_id(el)
    else:
      return res  
  elif el and type(el)==list and el[0].startswith(typed_skolem_function_prefix):
    if showobjid:
      s=add_word_article_desc(doc,el[1],objects)+" "+el[0]+" of "+make_nice_nlp_term(doc,el[2],objects)
    else:
      s=add_word_article_desc(doc,el[1],objects)+" of "+make_nice_nlp_term(doc,el[2],objects)  
    for el in el[3:]:
      s=s+", "+make_nice_nlp_term(doc,el,objects)
    res=s    
    return res
  elif el and type(el)==list and el[0].startswith(external_skolem_constant_prefix):
    s=add_word_article_desc(doc,el[0],objects)+" of "+make_nice_nlp_term(doc,el[1],objects)
    for el in el[2:]:
      s=s+", "+make_nice_nlp_term(doc,el,objects)
    res=s     
    return res         
  elif el and type(el)==list and el[0].startswith(skolem_constant_prefix):    
    res=None
    for obj in objects:
      if (type(obj)==list and 
          (el==obj or (el[0]==obj[0][0] and is_var(el[1]) and is_var(obj[0][1]))) and   
          obj[1]):         
        res=obj[1]["text"]
        break
      elif el==obj[0] and obj[2]:
        res=make_name_from_logic(doc,el,obj[2],obj[1])      
        break
    if res:
      if res[0].isupper(): res=res.lower()
      res="the "+res
      if showobjid:
        return res+" "+term_to_id(el)
      else:
        return res        
        
    arg1="something "+el[0][len(skolem_constant_prefix):]
    #debug_print("res",res)
    #debug_print("objects",objects)

    res+=add_word_article_desc(doc,res,objects)
    if showobjid:
      return res+" "+term_to_id(el)
    else:
      return res  
  elif el and type(el)==list and el[0].startswith(theof_function):
    res+="the"+" "+el[1]+" of "+make_answer_object_str(doc,el[2],objects)
    for arg in el[3:]:
      res+=" and "+make_answer_object_str(doc,arg,objects)
    return str(res)
  elif el and type(el)==list and el[0] in [time_function]:  
    if el[1] in [generic_value]:
      return str(el[2])
    else:
      reslst=["the",el[1][1:],str(el[2])]
    res=" ".join(reslst)
    return res
  elif type(el)==list:
    return str(el)  
  else:
    #debug_print("el,res",(el,res))
    res+=add_word_article_desc(doc,res,objects)
    return str(res)+" "+str(el)

def make_name_from_logic(doc,obj,logic,word=None):
  #debug_print("make_name_from_logic obj",obj)
  #debug_print("make_name_from_logic logic",logic)
  if type(obj)==str and unknownsubject in obj: return "Some unknown" 
  elif not logic: return obj
  if logic==True and type(obj)==str:
    if obj.startswith(constant_prefix) and ("_" in obj):
      pos=obj.find("_")
      if obj[len(constant_prefix):pos].isnumeric():
        return obj[pos+1:]
      else:
        return obj  
  if type(logic)!=list: return obj
  if logic[0] in ["exists","forall"]:
    return make_name_from_logic(doc,obj,logic[2],word)
  elif logic[0]!="and":
    if word and word_has_feat(word,"Number","Plur"):
      return word["text"]
    else: 
      return str(logic[1])
  lst=[]
  question_adjectives=[]
  if doc:
    question=doc[-1]
    for el in question:
      if el["upos"] in ["ADJ"]:
        question_adjectives.append(el["lemma"])
  #debug_print("question_adjectives",question_adjectives)      
  isa1found=False
  for el in logic[1:]:    
    #debug_print("el",el)
    if el[0]==dummypredicate:
      break
    if el[0] in ["isa","-isa"] and el[2]==obj:
      isa1found=True
    if el[0] in ["prop"] and el[1] in question_adjectives:
      continue  
    if isa1found and el[0] in ["prop","-prop"]:
      continue
    #debug_print("el 2",el)
    if el[0] in ["and","or"]: 
      sublst=[]
      isa2found=False
      for subel in el[1:]:
        #debug_print("subel",subel)
        if subel[0] in ["isa","-isa"] and el[2]==obj:
          isa2found=True
        if isa2found and subel[0] in ["prop","-prop"]:
          continue  
        if subel[0][0]=="-": 
          sublst.append("not "+str(subel[1]))
        elif subel[0] in ["forall","exists"]:
          continue
        elif (subel[0] in ["prop"]) and subel[1] in question_adjectives:
          continue
        elif el[1] and word_has_feat(el[1],"Number","Plur"):
          sublst.append(el[1]["text"]) 
        else:
          sublst.append(str(subel[1]))
      if el[1] and word_has_feat(el[1],"Number","Plur"):
        subres=(" "+el[1]["text"]+" ").join(sublst)
      else:  
        subres=(" "+el[0]+" ").join(sublst)
      lst.append(subres) 
      continue 
    if el[0][0]=="-": lst.append("not")
    if not (el[0] in ["forall","exists","rel1","rel2","-rel1","-rel2"]):
      #debug_print("el,word",[el,word])
      if len(el)<3 or el[2]!=obj:
        continue
      elif el[1] and word and el[1]==word["lemma"] and word_has_feat(word,"Number","Plur"):
        lst.append(word["text"])
      else:  
        lst.append(str(el[1]))
  #debug_print("make_name_from_logic lst",lst)  
  res=" ".join(lst)
  #debug_print("make_name_from_logic res",res)
  return res     

def term_to_id(term):
  if type(term)==str:
    if term.startswith(det_constant_prefix):
      spl=term.split("_")
      return spl[1]
    else:
      return term  
  else:
    return str(term)

def is_noun(doc,str):
  for sentence in doc:
    for word in sentence:
      if word["lemma"]==str and word["upos"]=="NOUN":
        return True
  return False      

def make_nlp_proof(doc,rawresult):
  try:
    data=json.loads(rawresult)
  except:
    return ""
  if "error" in data:    
    return ""
  elif not ("result" in data) or data["result"]!="answer found":
    return "" 
  # - - - now we have an answer - - - -
  answers=data["answers"]
  if len(answers)>1:
    res="Explanations:\n"
  else:
    res="Explanation:\n"
  answercount=0
  for answer in answers:
    if "positive proof" in answer:
      proofstr=make_nice_proof(doc,answer["positive proof"])
      res+=proofstr+"\n"
      answercount+=1
  return res    

def make_nice_proof(doc,proof):
  #debug_print("proof",proof)
  res=""  
  inputs=[]
  named_objects={} 
  for clause in proof:    
    if clause[1][0]=="in":
      inputs.append(clause[2])
      if clause[2] and clause[2][0][0]=="has_name":
        const=clause[2][0][2]
        name=clause[2][0][1]
        named_objects[const]=name
  for clause in inputs:
    #debug_print("clause",clause)
    s=proof_clause_to_nlp(doc,named_objects,clause)
    if not s: continue
    if res: res+=" "+s+"\n"
    else: res+=s+"\n"  
  return res

def proof_clause_to_nlp(doc,named_objects,clause):
  for atom in clause:
    if atom[0] in ["$needans","$ans"]: return None
  if len(clause)==1 and clause[0][0]=="has_name": return None  
  return str(clause)

# ==== explanation from proof ====

def make_nlp_explanation(doc,answer,logic_objects,boolanswer=False,show_logic_details=False):

  if "objects" in logic_objects: objects=logic_objects["objects"]
  else: objects=None
  if "logic_sentence_map" in logic_objects: logic_sentence_map=logic_objects["logic_sentence_map"]
  else: logic_sentence_map=None
  posproof=None
  negproof=None  
  posusednames=[]
  negusednames=[]

  if "positive proof" in answer:
    posproof=answer["positive proof"]  
    posproof=fix_extrainfo_proof(posproof)   
    posusednames=get_proof_names(posproof,logic_sentence_map)
    poslogic_sentence_map=make_logicname_nr_map(posusednames)    
    posres=make_nlp_explanation_for_polarity(doc,posproof,logic_objects,poslogic_sentence_map,True,boolanswer,show_logic_details)
    if show_logic_details=="full" and "blockers" in answer and answer["blockers"]:
      blockertext=make_nlp_blockers(doc,answer["blockers"],{"objects":objects})
      posblockers="\nExceptions checked and not holding:\n "+blockertext+"\n"
    else:
      posblockers=""  
    if answer["confidence"]==1: posconf=""
    else: posconf="Confidence "+make_nlp_confidence(answer["confidence"])+".\n"
  if "negative proof" in answer:
    negproof=answer["negative proof"]
    negproof=fix_extrainfo_proof(negproof) 
    negusednames=get_proof_names(negproof,logic_sentence_map) 
    neglogic_sentence_map=make_logicname_nr_map(negusednames)
    negres=make_nlp_explanation_for_polarity(doc,negproof,logic_objects,neglogic_sentence_map,False,boolanswer,show_logic_details)
    if show_logic_details=="full" and "blockers" in answer and answer["blockers"]:
      blockertext=make_nlp_blockers(doc,answer["blockers"],{"objects":objects})
      negblockers="\nExceptions checked and not holding:\n "+blockertext+"\n"
    else:
      negblockers=""  
    if answer["confidence"]==1: negconf=""
    else: negconf="Confidence "+make_nlp_confidence(answer["confidence"])+".\n"  
  possentences=make_numbered_sentence_list(posusednames,logic_sentence_map)
  posknowledge=make_used_knowledge_list(doc,posusednames,logic_sentence_map,posproof,show_logic_details)  
  possentences+=posknowledge
  if possentences:
    if not boolanswer:
      possentences+="Statements inferred:\n" 
    else:
      possentences+="Statements inferred (proof by contradiction):\n"   
  negsentences=make_numbered_sentence_list(negusednames,logic_sentence_map)
  negknowledge=make_used_knowledge_list(doc,posusednames,logic_sentence_map,negproof,show_logic_details)
  negsentences+=negknowledge
  if negsentences:
    if not boolanswer:
      negsentences+="Statements inferred:\n" 
    else:
      negsentences+="Statements inferred (proof by contradiction):\n"
  if posproof:
    fullposproof=possentences+posres+posblockers
  if negproof:
    fullnegproof=negsentences+negres+negblockers
  if posproof and negproof:
    return "\nPositive arguments:\n"+fullposproof+"\n\nNegative arguments:\n"+fullnegproof
  elif posproof:
    return posconf+fullposproof
  elif negproof:
    return negconf+fullnegproof 

def fix_extrainfo_proof(proof):
  if options["prover_print"] and options["prover_print"]>10:
    tmp=[]
    for el in proof:
      tmp.append([el[0],el[2][:-1]]+el[3:])
    proof=tmp
  #debug_print("proof",proof) 
  return proof


def get_proof_names(proof,logic_sentence_map): 
  used={}
  for step in proof:
    if type(step[1])==list and step[1][0]=="in":
      if not step[1][1] in used:
        used[step[1][1]]=True
  allkeys=[]
  for key in logic_sentence_map:
    sp=key.split("_")
    if len(sp)>1: allkeys.append([int(sp[1]),key])
    else: allkeys.append([0,key])
  allkeys.sort(key=lambda x: x[0])  
  res=[]
  for key in allkeys:
    if key[1] in used:
      res.append(key[1])
  #debug_print("get_proof_names gives",res)    
  return res

def make_logicname_nr_map(usednames):
  #usednames.sort()
  nr=0
  res={}
  for el in usednames:
    nr+=1
    res[el]=nr
  return res

def make_numbered_sentence_list(usednames,logic_sentence_map):
  if (not options["prover_explain_flag"]) or (not logic_sentence_map):
    sentences=""  
  else:
    sentences="Sentences used:\n" 
    sentencenr=0  
    name_nr_map={}
    for key in usednames:
      if not (key in logic_sentence_map): continue
      sentencenr+=1
      name_nr_map[key]=sentencenr
      sentences+=" ("+str(sentencenr)+") "+logic_sentence_map[key]+"\n"
  return sentences

def make_used_knowledge_list(doc,posusednames,logic_sentence_map,proof,show_logic_details=False):
  if not proof: return ""
  if (not options["prover_explain_flag"]) or (not logic_sentence_map):
    sentences=""  
  else:
    #debug_print("proof",proof)
    sentences="" 
    for step in proof:
      if (step[1][0]=="in" and not step[1][1].startswith("sent_") and
          not step[1][1].startswith("$auto_negated_question")):
        # skip atomic statements like ['isa', 'brake', ['skt100103', 'brake', '?:X']]
        if trivial_knowledge_clause(step[2]):
          continue           
        if step[1][-1]==1:
          nlpconf=""
        else:
          nlpconf=" Confidence "+make_nlp_confidence(step[1][-1])+"."
        nlpwhy=make_nlp_why([],step,[],{},proof)
        sentence=" "+make_nlp_clause(doc,step[2],[],False,show_logic_details)+nlpconf+" Why: "+nlpwhy+".\n"
        sentences+=sentence
    if sentences:
      sentences="Knowledge used:\n" + sentences
  return sentences

def trivial_knowledge_clause(clause):
  # skip atomic statements like ['isa', 'brake', ['skt100103', 'brake', '?:X']]
  if len(clause)<3:
    for atom in clause:
      if (atom[0]=="isa" and type(atom[2])==list and
          atom[2][0].startswith(typed_skolem_function_prefix) and len(atom[2])>2 and
          atom[2][1]==atom[1]):
        return True
  if len(clause)==1:
    atom=clause[0]
    if (atom[0]=="isa" and type(atom[1])==str and  type(atom[2])==str and
        atom[2]=="some_"+atom[1]):
      return True      
  return False


def make_nlp_confidence(conf):
  if conf==1:
    return ""
  rconf=round(conf*100)
  if rconf==100 or rconf==0:
    rconf=round(conf*1000)/10
  if rconf==100 or rconf==0:
    rconf=round(conf*10000)/100
  res=str(rconf)+"%" 
  return res 


def make_nlp_explanation_for_polarity(doc,proof,logic_objects,logic_sentence_map,
                                      positive_proof=True,boolanswer=False,show_logic_details=False):   
  #debug_print("make_nlp_explanation_for_polarity boolanswer",boolanswer)
  nlpsteps=[]
  if show_logic_details=="full": show_logic=True
  else: show_logic=False
  for step in proof:
    #debug_print("step",step)
    nlpnr="("+str(step[0])+")"
    nlpclause=make_nlp_clause(doc,step[2],logic_objects,False,show_logic_details)
    if step[1][-1]==1:
      nlpconf=""
    else:
      nlpconf=" Confidence "+make_nlp_confidence(step[1][-1])+"."
    nlpwhy=make_nlp_why(doc,step,logic_objects,logic_sentence_map,positive_proof)
    nlpstep=" "+nlpnr+" "+nlpclause+nlpconf+" Why: "+nlpwhy+"."
    nlpsteps.append(nlpstep)
    if show_logic: nlpsteps.append("     "+make_classic_clause_str(step[2]))
    
  res="\n".join(nlpsteps) 
  return res

def make_nlp_clause(doc,clause,logic_objects,noif=False,show_logic_details="full"):
  #debug_print("make_nlp_clause clause",clause)
  #debug_print("make_nlp_clause show_logic_details",show_logic_details)
  if "objects" in logic_objects: objects=logic_objects["objects"]
  else: objects=None
  if clause==False:
    return "Contradiction."
  if type(clause)!=list:
    return str(clause)
  posatoms=[]
  negatoms=[]
  neg_isa_atoms=[]
  neg_act_atoms=[]
  blockers=[]
  for atom in clause:
    if type(atom)!=list: posatoms.append(atom)
    if atom[0]=="$block": 
      blockers.append(atom)
    elif atom[0][0]=="-" and not noif:  
      negatoms.append(atom)
      if atom[0]=="-isa":
        neg_isa_atoms.append(atom)
      elif atom[0] in ["-act1","-act2"]:  
        neg_act_atoms.append(atom)
    else:
      posatoms.append(atom)        
  
  condlist=[]
  conseqlist=[]

  for atom in negatoms:
    nlpatom=make_nlp_atom(doc,atom,logic_objects,False,show_logic_details)
    condlist.append(nlpatom)
  for atom in posatoms:
    nlpatom=make_nlp_atom(doc,atom,logic_objects,True,show_logic_details)
    conseqlist.append(nlpatom)  
  condstr=" and ".join(condlist)
  conseqstr=" or ".join(conseqlist)
  if blockers and len(blockers)==len(clause):
    res="Contradiction"# except when "+make_nlp_blockers(doc,blockers,objects)
  elif negatoms and posatoms:
    res="If "+condstr+", then "+conseqstr
  elif posatoms:
    res=conseqstr
  elif neg_isa_atoms and len(neg_isa_atoms)!=len(negatoms):
    condlist=[]
    conseqlist=[]
    for atom in neg_isa_atoms:
      nlpatom=make_nlp_atom(doc,atom,logic_objects,False,show_logic_details)
      condlist.append(nlpatom)
    condstr=" and ".join(condlist)  
    neglist=[]
    for atom in negatoms:
      if atom in neg_isa_atoms: continue
      nlpatom=make_nlp_atom(doc,atom,logic_objects,True,show_logic_details)
      conseqlist.append(nlpatom)
    conseqstr=" or ".join(conseqlist) 
    res="If "+condstr+", then "+conseqstr 
  elif neg_act_atoms and len(neg_act_atoms)!=len(negatoms):
    condlist=[]
    conseqlist=[]
    for atom in neg_act_atoms:
      nlpatom=make_nlp_atom(doc,atom,logic_objects,False,show_logic_details)
      condlist.append(nlpatom)
    condstr=" and ".join(condlist)  
    neglist=[]
    for atom in negatoms:
      if atom in neg_act_atoms: continue
      nlpatom=make_nlp_atom(doc,atom,logic_objects,True,show_logic_details)
      conseqlist.append(nlpatom)
    conseqstr=" or ".join(conseqlist) 
    res="If "+condstr+", then "+conseqstr   
  else:
    neglist=[]
    for atom in negatoms:
      nlpatom=make_nlp_atom(doc,atom,logic_objects,True,show_logic_details)
      neglist.append(nlpatom)
    res=" or ".join(neglist)
  if blockers and show_logic_details=="full":
    blockertext=make_nlp_blockers(doc,blockers,{"objects":objects})
    #debug_print("clause",clause)
    #debug_print("blockertext",blockertext)
    if blockertext.startswith("The "): blockertext="the "+blockertext[4:]
    elif blockertext.startswith("A "): blockertext="a "+blockertext[2:]
    elif blockertext.startswith("An "): blockertext="an "+blockertext[3:]
    elif blockertext.startswith("Arbitrary "): blockertext="a"+blockertext[1:]
    res+=", except when "+blockertext
  else:
    res+="."
  if res and res[0].islower():
    res=res[0].upper()+res[1:]
  #debug_print("make_nlp_clause res",res)  
  return res
    

def make_nlp_blockers(doc,blockers,objects):
  newclause=[]
  for el in blockers:
    atom=el[2]
    if atom[0]=="$not":
      newatom=["-"+str(atom[1][0])]+atom[1][1:]
    else:
      newatom=atom
    newclause.append(newatom)
  #debug_print("blockers newclause",newclause)  
  #debug_print("blockers objects",objects)
  s=make_nlp_clause(doc,newclause,objects,True) 
  #debug_print("blockers s",s)   
  return s

def make_nlp_atom(doc,atom,logic_objects,positive,show_logic_details=None):
  #debug_print("make_nlp_atom atom positive",[atom,positive])
  origpositive=positive
  atom_time=get_ctxt_time(get_atom_ctxt(atom))
  situation_nr=get_ctxt_situation_nr(get_atom_ctxt(atom)) 
  action_suffix=""
  if (atom[0] in ["act1","act2","do1","do2","-act1","-act2","-do1","-do2"]): # and 
      #show_logic_details in ["full","time","situation"]):
    action_id=None  
    if atom[0] in ["act1","do1","-act1","-do1"]: action_id=atom[3]  
    elif atom[0] in ["act2","do2","-act2","-do2"]: action_id=atom[4] 
    if action_id: 
      tmp=make_nice_nlp_term(doc,action_id,None)
      action_suffix=" (action "+tmp+")"
  if situation_nr and show_logic_details in ["full","time","situation"]: 
    if atom_time=="Pres":
      situation_suffix=" in a present situation "+str(situation_nr)
    elif atom_time=="Past":
      situation_suffix=" in a past situation "+str(situation_nr)  
    else:
      situation_suffix=" in situation "+str(situation_nr)
  else: situation_suffix=""
  if atom_time in ["Past"]: 
    isverb="was"
    doesverb="did"
    canverb="could"
    hasverb="had"
  else: 
    isverb="is"
    doesverb="does"
    canverb="can"
    hasverb="has"

  if "objects" in logic_objects: objects=logic_objects["objects"]
  else: objects=None
  if "question_definition" in logic_objects: 
    question_definition=logic_objects["question_definition"]
    if type(question_definition)==list: question_definition=question_definition[0]
    else: question_definition=None
    #debug_print("question_definition",question_definition)
  else: question_definition=None
  if type(atom)!=list:
    return str(atom)+situation_suffix 
  head=atom[0]
  if head[0]=="-": 
    positive=not positive
    headstr=head[1:]
  else: 
    headstr=head
  purerelation=False  

  if len(atom)>1 and headstr=="$ans":
    nicehead=make_nice_nlp_head(headstr,positive,atom)
    if len(atom)>2: s="["
    else: s=""
    for el in atom[1:]:
      if len(s)>1: s+=", "
      s+=make_nice_nlp_term(doc,el,objects)
    if len(atom)>2: s+="]"  
    s+=" is an answer"
    return s+situation_suffix     

  elif (len(atom)==3 and head=="-isa" and not origpositive and
        type(atom[1])==str and type(atom[2])==str and
        atom[1] in atom[2]):
    s=term_to_id(atom[2])+" is "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix     
  elif (len(atom)==3 and head=="isa" and 
        type(atom[1])==str and type(atom[2])==str and
        atom[1] in atom[2]):   
    s=make_nice_nlp_term(doc,atom[2],objects)+" is "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix   
  elif (len(atom)==3 and head=="-isa" and not positive and
        type(atom[1])==str and type(atom[2])==str and
        atom[1] in atom[2]):     
    s=make_nice_nlp_term(doc,atom[2],objects)+" is not "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix   
  elif (len(atom)==3 and head=="isa" and positive and
        type(atom[1])==str and type(atom[2])==str): 
    if not ("_" in atom[2]) and atom[2].startswith(skolem_constant_prefix):
      s=term_to_id(atom[2])+" is "+make_nice_nlp_term(doc,atom[1],objects)
    else:  
      s=make_nice_nlp_term(doc,atom[2],objects)+" is "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix     
  elif (len(atom)==3 and head=="-isa" and not origpositive and
        type(atom[1])==str and type(atom[2])==str):     
    if not ("_" in atom[2]) and atom[2].startswith(skolem_constant_prefix):
      s=term_to_id(atom[2])+" is "+make_nice_nlp_term(doc,atom[1],objects)
    else:  
      s=make_nice_nlp_term(doc,atom[2],objects)+" is "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix   
  elif headstr.startswith("rel2"):   
    #debug_print("atom",atom)     
    relation_type=headstr[len("rel2"):]
    if not relation_type:
      purerelation=True
      if type(atom[1])==str and atom[1].startswith("is_"):
        type_word=atom[1][len("is_"):]
      else:  
        type_word="of"
    elif relation_type in ["_is_of"]:
      type_word="of"
    elif relation_type in ["_is_in"]:
      type_word="in"  
    elif relation_type in ["_is_than"]:
      type_word="than"
    else:
      type_word="of" 

    #debug_print("purerelation",purerelation)   
    if purerelation:  
      nicehead=make_nice_nlp_head(type_word,positive,atom,None)
    else:
      nicehead=make_nice_nlp_head(atom[1],positive,atom,type_word)  
    if atom[1]=="have":
      #if type(atom[3])==list and atom[2] in atom[3][1:]:
        #debug_print("atom",atom)
      if not positive:
        if atom_time in ["Past"]: 
          s=make_nice_nlp_term(doc,atom[2],objects)+" did not have "
        else:
          s=make_nice_nlp_term(doc,atom[2],objects)+" does not have "
      else:
        s=make_nice_nlp_term(doc,atom[2],objects)+" "+hasverb+" "
      s+=make_nice_nlp_term(doc,atom[3],objects,noof=True)
      #debug_print("s",s)
    elif is_var(atom[1]):
      if not positive:
        nicehead=make_nice_nlp_head(atom[1],True,atom,type_word)
        s=make_nice_nlp_term(doc,atom[2],objects)+" "+hasverb+" not a relation "
      else:
        nicehead=make_nice_nlp_head(atom[1],True,atom,type_word)
        s=make_nice_nlp_term(doc,atom[2],objects)+" "+hasverb+" a relation "  
      s+=nicehead+" with "+make_nice_nlp_term(doc,atom[3],objects) 
    elif type_word in ["of"]:    
      if atom[1] in preposition_words: article=" "
      else: article=" a "
      if not positive:
        nicehead=make_nice_nlp_head(atom[1],True,atom,type_word)
        s=make_nice_nlp_term(doc,atom[2],objects)+" "+isverb+" not"+article
      else:
        nicehead=make_nice_nlp_head(atom[1],True,atom,type_word)
        s=make_nice_nlp_term(doc,atom[2],objects)+" "+isverb+article 
      if atom[1] in preposition_words:
        s+=nicehead+" "+make_nice_nlp_term(doc,atom[3],objects) 
      else:     
        s+=nicehead+" "+type_word+" "+make_nice_nlp_term(doc,atom[3],objects) 
    elif purerelation:   
      s=make_nice_nlp_term(doc,atom[2],objects)+" "+isverb+" "
      s+=nicehead+" "+make_nice_nlp_term(doc,atom[3],objects)       
    else:            
      s=make_nice_nlp_term(doc,atom[2],objects)+" "+isverb+" "
      s+=nicehead+" "+type_word+" "+make_nice_nlp_term(doc,atom[3],objects)
    return s+situation_suffix 
  elif headstr.startswith("act1"):
    s=make_nice_nlp_term(doc,atom[2],objects)
    s+=" "+make_nice_nlp_term(doc,atom[1],objects)+"s"
    return s+situation_suffix+action_suffix   
  elif headstr.startswith("act2"):
    s=make_nice_nlp_term(doc,atom[2],objects)
    s+=" "+make_nice_nlp_term(doc,atom[1],objects)+"s"
    s+=" "+make_nice_nlp_term(doc,atom[3],objects)
    return s+situation_suffix+action_suffix  
  elif headstr.startswith("do1") or headstr.startswith("can1"):
    s=make_nice_nlp_term(doc,atom[2],objects)
    if headstr.startswith("do1"):
      s+=" "+doesverb+" "
    else:
      s+=" "+canverb+" "  
    if not positive:
      s+="not "
    s+=make_nice_nlp_term(doc,atom[1],objects)     
    return s+situation_suffix+action_suffix      
  elif headstr.startswith("do2") or headstr.startswith("can2"):
    s=make_nice_nlp_term(doc,atom[2],objects)
    if headstr.startswith("do2"): 
      s+=" "+doesverb+" "
    else:
      s+=" "+canverb+" "  
    if not positive:
      s+="not "
    s+=make_nice_nlp_term(doc,atom[1],objects)   
    s+=" "+make_nice_nlp_term(doc,atom[3],objects)
    return s+situation_suffix+action_suffix    
  elif headstr=="prop":
    nicehead=make_nice_nlp_head(headstr,positive,atom)
    s=make_nice_nlp_term(doc,atom[2],objects)+" "
    strengthword=" "
    if len(atom)>3 and atom[3]==3: strengthword=" very "
    elif len(atom)>3 and atom[3]==1: strengthword=" somewhat "
    if len(atom)>4 and atom[4]==generic_value: typeword=""
    elif len(atom)>4: 
      typeword=make_nice_nlp_term(doc,atom[4],objects)
      #debug_print("typeword 1",typeword)
      if typeword.startswith("a "): typeword=typeword[2:]
      elif typeword.startswith("an "): typeword=typeword[3:]
      elif typeword.startswith("the "): typeword=typeword[4:] 
    else:
      typeword=""
    #debug_print("nicehead",nicehead)   
    #debug_print("typeword 2",typeword)  
    #debug_print("strengthword",strengthword) 
    #debug_print("make_nice_nlp_term(doc,atom[1],objects)",make_nice_nlp_term(doc,atom[1],objects))
    if typeword:
      s+=nicehead+" a"+strengthword+make_nice_nlp_term(doc,atom[1],objects,True)+" "+typeword
    else:
      s+=nicehead+strengthword+make_nice_nlp_term(doc,atom[1],objects,True)  
    return s+situation_suffix   
  elif len(atom)>2:
    if headstr=="$greatereq":
      nicehead=make_nice_nlp_head(headstr,positive,atom)    
      s=make_nice_nlp_term(doc,atom[1],objects)+" "
      s+=nicehead+" "+make_nice_nlp_term(doc,atom[2],objects)
    elif headstr in ["$greater","$less"]:
      nicehead=make_nice_nlp_head(headstr[1:],positive,atom) 
      debug_print("nicehead",nicehead)   
      s=make_nice_nlp_term(doc,atom[1],objects)+" "
      s+=nicehead+" than "+make_nice_nlp_term(doc,atom[2],objects)  
    else:  
      nicehead=make_nice_nlp_head(headstr,positive,atom)    
      s=make_nice_nlp_term(doc,atom[2],objects)+" "
      s+=nicehead+" "+make_nice_nlp_term(doc,atom[1],objects)
    return s+situation_suffix 
  elif len(atom)==2 and headstr[0:4] in ["$def"]: 
    s=make_nice_nlp_term(doc,atom[1],objects)+" "  
    if headstr==question_definition:
      if positive:
        return s+"matches the query"
      else:
        return s+"does not match the query"
    else:
      if positive:
        return s+hasverb+" a property "+headstr[1:]+situation_suffix 
      else:
        return s+doesverb+" not have a property "+headstr[1:]+situation_suffix    
  elif len(atom)==1 and headstr[0:4] in ["$def"]:  
    if headstr==question_definition:
      headstr="$"+"the question"
    if positive:
      return headstr[1:]+" is true"
    else:
      return headstr[1:]+" is not true"  
  else:    
    return str(atom)   


def get_atom_ctxt(atom):
  if not atom or type(atom)!=list: return None
  for el in atom:
    if type(el)==list and el[0]==ctxt_function:
      return el
  return None

def get_ctxt_time(ctxt):
  if not ctxt: return None
  return ctxt[1]

def get_ctxt_situation_nr(ctxt):
  if not ctxt: return None
  tmp=ctxt[2]  
  if type(tmp)==int: return tmp
  else: return None

def make_nice_nlp_head(headstr,positive,atom,type_word=None):
  debug_print("headstr",headstr)
  #debug_print("type_word",type_word)
  atom_time=get_ctxt_time(get_atom_ctxt(atom))
  if atom_time in ["Past"]: 
    isverb="was"
    doesverb="did"
    canverb="can"
    hasverb="had"
  else: 
    isverb="is"
    doesverb="does"
    canverb="could"
    hasverb="has"

  if headstr in ["isa","prop"]:
    if positive:
      return isverb
    else:
      return isverb+" not"  
  elif headstr in ["$ans"]:
    if positive:
      return "is"
    else:
      return "is not"  
  elif headstr[0:4] in ["$def"]:
    if positive:
      return hasverb+" a defined property "+headstr[1:]
    else:
      return doesverb+" not have a defined property"+headstr[1:]
  elif headstr in ["="]:
    if positive:    
      return "is"
    else:
      return "is not"
  elif headstr in ["$greatereq"]:
    if positive:    
      return "is at least"
    else:
      return "is less than"    
  elif headstr in ["greater","less"]:
    if positive:    
      return isverb+" "+headstr
    else:
      return isverb+" not "+headstr
  if headstr.startswith("?:"): headstr=headstr[2:]            
  headstr=headstr.replace("_"," ")    
  if type_word in ["than"]:
    if headstr[-1]=="e": headstr+="r"
    else: headstr+="er"
  if positive:    
    return str(headstr)
  else:
    return "not "+str(headstr)  

def make_nice_nlp_term(doc,term,objects,isprop=False,noof=False):
  #debug_print("make_nice_nlp_term term",term)
  #if type(term)==list: debug_print("make_nice_nlp_term term",term)
  #debug_print("make_nice_nlp_term objects",objects)
  if not term: return str(term)
  if type(term)==int: 
    return str(term)
  elif type(term)!=str:
    if term[0]=="of":
      res=term[1]
      res=make_nice_nlp_term(doc,term[1],objects,isprop)
      res+=" of "+make_nice_nlp_term(doc,term[2],objects,isprop)
    elif type(term)==list:
      if term[0]==count_function:
        if type(term[1])==list and term[1][0].startswith(measure_function):
          units=make_nice_nlp_term(doc,term[1][3],objects)
          if units.startswith("a "): units=units[2:]
          res="the "+term[1][1]+" of "+make_nice_nlp_term(doc,term[1][2],objects,isprop)+" in "+units+"s"
        else:  
          res="the size of "+make_nice_nlp_term(doc,term[1],objects,isprop)
      elif term[0]==set_function:
        res="the set of "+make_nice_nlp_set_term(doc,term[1],objects,isprop)+" of "+make_nice_nlp_term(doc,term[2],objects,isprop) 
      elif term[0].startswith(measure_function):
        units=make_nice_nlp_term(doc,term[3],objects)        
        if units.startswith("a "): units=units[2:]
        res="the "+term[1]+" of "+make_nice_nlp_term(doc,term[2],objects,isprop)+" in "+units+"s"
      elif term[0].startswith(typed_skolem_function_prefix):
        s=add_word_article_desc(doc,term[1],objects)
        #debug_print("article-added s",s)
        s+=" of "+make_nice_nlp_term(doc,term[2],objects,isprop)
        for el in term[3:]:
          s=s+", "+make_nice_nlp_term(doc,el,objects,isprop)
        res=s    
      elif term[0].startswith(skolem_constant_prefix) or term[0].startswith(external_skolem_constant_prefix):
        s=add_word_article_desc(doc,term[0],objects)
        #if not noof: s+=" of "+make_nice_nlp_term(doc,term[1],objects,isprop)
        s+=" of "+make_nice_nlp_term(doc,term[1],objects,isprop)
        for el in term[2:]:
          s=s+", "+make_nice_nlp_term(doc,el,objects,isprop)
        res=s      
      elif term[0].startswith(theof_function):
        s="the "+term[1]+" of "+make_nice_nlp_term(doc,term[2],objects,isprop)
        for el in term[3:]:
          s=s+", "+make_nice_nlp_term(doc,el,objects,isprop)
        res=s  
      elif term[0] in [time_function]:  
        if term[1] in [generic_value]:
          return str(term[2])
        else:
          reslst=["the",term[1][1:],str(term[2])]
        res=" ".join(reslst)
      else:
        res=str(term)    
    else:
      res=str(term)  

  elif unknownsubject in term:
    res="Some unknown"
    return res

  elif const_in_objects(term,objects):
    #debug_print("term",term)
    res=make_answer_object_str(doc,term,objects)
    return res

  elif len(term)>2 and term.startswith("?:"):
    if term[2:].isnumeric():
      res="?:V"+term[2:]
    else:
      res=term[2:]  
  elif len(term)>2 and term[0]=="c" and term[2]=="_":   
    res=term[3:]
  elif term.startswith("some_"):
    res="arbitrary "+term[len("some_"):]
  elif term.startswith("$sk"):
    res="arbitrary c"+term[len("$sk"):]  
  else:
    #debug_print("make_nice_nlp_term term",term)  
    res=str(term)   
  res=add_word_article_desc(doc,res,objects,isprop) 
  #if type(term)==list: debug_print("make_nice_nlp_term res2",res) 
  return res

def make_nice_nlp_set_term(doc,term,objects,isprop=False):
  if type(term)!=list: return make_nice_nlp_term(doc,term,objects,isprop)
  if not(term[0]) in ["and","or"]:
    term=["and",term]
  if term[0] in ["and","or"]:
    mainisa=None
    props=[]
    for atom in term[1:]:
      #debug_print("atom in term",atom)
      if atom[0][0]=="-":
        polarity=False
        headstr=atom[0][1:]
      else:
        polarity=True
        headstr=atom[0]  
      #debug_print("headstr",headstr)  
      if headstr=="isa" and not mainisa:
        mainisa=str(atom[1])+"s"
        if not polarity: mainisa="not "+mainisa
      elif headstr=="prop" or (mainisa and headstr=="isa"):
        tmp=make_nice_nlp_term(doc,atom[1],objects,True)
        if not polarity: tmp="not "+tmp
        props.append(tmp)
      else:
        tmp=make_nice_nlp_term(doc,atom,objects,True)  
    if mainisa: props.append(mainisa)
    s=" ".join(props)
    return s


def const_in_objects(const,objects):
  if not objects: return False
  for el in objects:
    if el[0]==const: return True  
  return False

def make_nlp_why(doc,step,logic_objects,logic_sentence_map,positive_proof):
  reason=step[1]
  clause=step[2]
  if reason[0] in ["in"]:
    if reason[-2]=="goal":
      hasans=False
      for atom in clause:
        if atom[0]=="$ans":
          hasans=True
          break        
      if hasans:
        res="the question"
      elif not positive_proof:
        res="the question"  
      else:
        res="a negated question"  
    elif logic_sentence_map and reason[1] in logic_sentence_map:
      res="sentence "+str(logic_sentence_map[reason[1]])
    elif not reason[1].startswith("frm_"):
      res=reason[1]
    else:
      res="assumed basic knowledge"
  else:
    nrs=reason[1:-2]
    strnrs=[]
    for el in nrs:
      if type(el)==list: strnrs.append(str(el[0]))
      else: strnrs.append(str(el))
    s=", ".join(strnrs)
    if reason[0]=="cumul":
      res="cumulated confidence of statements "+s
    else:
      res="statements "+s
  return res  


# =========== the end ==========