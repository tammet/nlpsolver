# The question handling part of proper logic converter parts of nlpsolver, 
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

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

# small utilities are in nlputils.py
from nlputils import *

# uncertainty analysis and encoding is in nlpuncertain
from nlpuncertain import *

# pronoun guessing
from nlppronoun import *

# pronoun guessing
from nlpobjlogic import *

from nlpanswer import *

# ======= globals used and changed during work ===

def is_question_sentence(sentence): 
  #debug_print("is_question_sentence sentence",sentence) 
  end_punct=sentence[-1]
  if (end_punct and end_punct["lemma"]=="?"):
    #debug_print("is_question_sentence result",True) 
    return True
  else:
    return False
    
      
def prepare_question_sentence(ctxt,sentence,origsentence):
  #debug_print("prepare_question_sentence sentence",sentence)
  #debug_print("prepare_question_sentence origsentence",origsentence) 
  if simple_question(ctxt,sentence):
    #debug_print("prepare_question_sentence determined it is a simple question!")
    object=find_existing_name(ctxt,sentence[2:])
    if object:      
      #debug_print("object:",object)
      res=make_described_name_text(ctxt,sentence,object)
      return {"result": res}      
    else:
      return {"result": None}  
  #sys.exit(0)
  text=make_text_from_doc_sep(sentence) 
  #text=make_text_from_doc(sentence)
  #debug_print("prepare_question_sentence made text",text) 
  text2=text
  if which_question(ctxt,sentence):
    #debug_print("which-question")
    subjlist=[]
    for i in range(1,len(sentence)):
      word=sentence[i]
      verbpos=0
      if (word["upos"] in ["VERB"] or 
          (word["upos"] in ["AUX"] and word["lemma"] in ["be","can"])):
        verbpos=i
        break
      else:
        subjlist.append(word["text"])
    if verbpos==0:
      return {"result": "Cannot understand the question."}      
    restlst=[]
    for i in range(verbpos,len(sentence)): 
      word=sentence[i]
      restlst.append(word["text"])
    if subjlist:  
      newsentencelst=["Who","is"]+subjlist+["and"]+restlst
    else:
      newsentencelst=["Who"]+restlst  
    newsentence=" ".join(newsentencelst)
    #debug_print("newsentence",newsentence)
    text2=newsentence
   
  for el in sentence:
    if el["lemma"] in ["of"] and el["upos"] in ["ADP"]:
      ctxt["question_dummification"]=False
  ctxt["question_dummification"]=True    
  if len(sentence)>4:    
    # do not use for "What did eat?"
    if (sentence[0]["lemma"] in ["what"] and    
        sentence[1]["lemma"] in ["do"]):
      ctxt["question_dummification"]=False  

   
  #debug_print("text from question doc",text)
  newtext=dummify_text(ctxt,text2,origsentence)
  #debug_print("newtext from text",newtext)
  #if newtext!=text:
  #  debug_print("replacement text for question:",newtext)
  data = server_parse(newtext)
  sentence=data["doc"][0] 
  if newtext!=text:
    debug_print("====== modified question sentence ==========")
    debug_print("original text from question doc",text)
    debug_print("modified question sentence",newtext)
    #debug_print("modified question parse",sentence)  
  if not ctxt["question_dummification"]:
    for el in sentence:
      if el["upos"] in ["NOUN","PRON"] and el["lemma"] in question_words:
        el["upos"]="PROPN"
  #debug_print("prepare_question_sentence returns",sentence)      
  return sentence  

def simple_question(ctxt,sentence):
  if not sentence or len(sentence)<3: return False
  if (sentence[0]["lemma"] in simple_question_words and # who, what
      sentence[1]["lemma"] in ["be"] and
      sentence_is_name(ctxt,sentence[2:])):
    return True
  return False

def which_question(ctxt,sentence):
  if not sentence or len(sentence)<3: return False
  if sentence[0]["lemma"] not in ["which"]: return False
  return True


def dummify_text(ctxt,text,orig_parsed_text):
  #debug_print("dummify_text",text) 
  #ctxt["question_dummification"]=True
  if not ctxt["question_dummification"]: return text 
  #if orig_parsed_text[0]["lemma"] in ["what","who","which"]:
  #  what_who_which_question=True
  #else:
  #  what_who_which_question=False
  sp=text.split(" ")
  sp=list(filter(lambda x: x,sp))
  tmp=split_sentence_startswith_pos(sp,["where",["is","was","are","were"]])
  tmp2=split_sentence_startswith_pos(sp,["where",["does","did"]])
  tmp3=split_sentence_startswith_pos(sp,["when",["is","was","are","were"]])
  tmp4=split_sentence_startswith_pos(sp,["when",["does","did"]])  
  #debug_print("tmp",tmp)
  #debug_print("tmp2",tmp2)
  #debug_print("firstpart",sp[:tmp2])
  if tmp>0:
    dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
    ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
    newsp=split_sentence_remove_trailingchar(sp[tmp:],"?")
    newsp=newsp+[make_question_beword(sp,tmp,["is","was","are","were"]),"on","a",dummy+"?"]
    #print("newsp",newsp)
    ctxt["question_type"]="where_is"
    #debug_print("dummify sets question_type")
  elif tmp2>0:
    dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
    ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
    newsp=split_sentence_remove_trailingchar(sp[tmp2:],"?")+["on","a",dummy+"?"]
    newsp=[make_question_beword(sp,tmp2,["does","did"])]+newsp
    #print("newsp",newsp)
    ctxt["question_type"]="where_does"
    #debug_print("dummify sets question_type")  
  elif tmp3>0:
    dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
    ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
    newsp=split_sentence_remove_trailingchar(sp[tmp3:],"?")
    newsp=newsp+[make_question_beword(sp,tmp3,["is","was","are","were"]),"during","a",dummy+"?"]
    #print("newsp",newsp)
    ctxt["question_type"]="when_is"
    #debug_print("dummify sets question_type")
  elif tmp4>0:
    dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
    ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
    newsp=split_sentence_remove_trailingchar(sp[tmp4:],"?")+["during","a",dummy+"?"]
    newsp=[make_question_beword(sp,tmp4,["does","did"])]+newsp
    #print("newsp",newsp)
    ctxt["question_type"]="when_does"
    #debug_print("dummify sets question_type") 
  #elif (("who" in sp or "whom" in sp) and 
  #      ("is" in sp or "are" in sp or "was" in sp or "were" in sp) and 
  #      ("of" in sp)):
  #  ctxt["question_type"]="who_is_of"   
  elif ((sp[0] in ["who","whom","what","which"] or sp[0].lower() in ["who","whom","what","which"]) and 
        sp[1].lower() in ["is","was","where"] and
        sp[-2] in ["of","about"]):
    #debug_print("ckpt0")
    dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
    ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
    newsp=[sp[1].capitalize()]+sp[2:-1]+[dummy+"?"]
  else:
    #debug_print("ckpt1")
    newsp=[]
    count=0
    #replaced=False   
    for el in sp:  
      #debug_print("el",el)
      count+=1  
      if ((count==1 and (el in ["who","whom","what","which"] or el.lower() in ["who","whom","what","which"])) or
          (((el in ["who","what","which"] or el.lower() in ["who","what","which"]) and 
            # What has the length 10 meters?" 
            el.lower()==orig_parsed_text[0]["lemma"].lower() )) or
          el in ["who?","whom?","what?","which?"] or el.lower() in ["who?","whom?","what?","which?"] or
          ((el.lower() in ["who","whom","what","which"]) and len(sp)==count+1 and sp[count]=="?") ):
        dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
        ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
        newsp.append(dummy)  
        ctxt["question_type"]=el.lower().strip("?")
        #replaced=True
      else:
        newsp.append(el)
    """
    if not replaced:
      newsp=[]
      count=0
      for el in sp:  
        count+=1
        if ((el["deprel"] in ["nmod"] and word_has_feat(el,"PronType","Rel") and 
            (el in ["who","what","which"] or el.lower() in ["who","what","which"])) or       
            el in ["who?","what?","which?"] or el.lower() in ["who?","what?","which?"]):
          dummy=nlpglobals.dummy_name+"_"+str(ctxt["dummy_nr"])
          ctxt["dummy_nr"]=ctxt["dummy_nr"]+1
          newsp.append(dummy)  
          ctxt["question_type"]=el.lower().strip("?")
          replaced=True
        else:
          newsp.append(el)    
    """      
  res=" ".join(newsp)      
  #debug_print("dummify_text returns",res)
  return res

def make_question_beword(sp,index,candidates):
  if index<1: return ""
  if not sp: return ""
  if index>=len(sp): return ""
  part=sp[:index]
  for el in candidates:
    if el in part:
      return el
  return ""


def sentence_is_name(ctxt,sentence):
  for el in sentence:
    if el["upos"] in ["PUNCT"]: continue
    if el["ner"] in ["O"]: return False
  return True


def find_existing_name(ctxt,namesentence):
  #debug_print("find_existing_object word",word)
  #debug_print("find_existing_object ctxt",ctxt)
  #debug_print("find_existing_object logic",logic)
  if not ("objects" in ctxt): return None
  ctxtobjects=ctxt["objects"]
  # first try to find an exact same word in sentence
  word=namesentence[0]
  results=[]
  pos=0
  for object in reversed(ctxtobjects):
    #print("object 0 ",object)
    if len(object)>3 and object[3]:
      objnames=object[3]
      score=0
      for word in namesentence:      
        if word["lemma"] in objnames:
          score+=1
      if score>0:
        pos+=1
        score=(4*score)-pos          
        results.append([score,object])
  if results:        
    res=sorted(results,key=lambda x: x[0],reverse=True)
    if res: return res[0][1]
  else: return None


def make_described_name_text(ctxt,sentence,object):
  objid=object[0]
  #debug_print("object ",object)
  txtlst=[object[3][-1]]
  classlst=[]
  proplst=[]
  negclasslst=[]
  negproplst=[]
  if len(object)>2 and object[2] and type(object[2])==list:
    for el in object[2]:
      #debug_print("el",el)
      if type(el)!=list: continue
      if len(el)<3 or el[2]!=objid: continue
      if el[0] in ["isa"]:
        classlst.append(el[1])
      elif el[0] in ["prop"]:
        proplst.append(el[1])  
      elif el[0] in ["-isa"]:
        negclasslst.append(el[1])
      elif el[0] in ["-prop"]:
        negproplst.append("not "+el[1])       
  if proplst or negproplst or classlst:
    txtlst.append("is")
  tmplst=negproplst+proplst+classlst
  if tmplst and classlst:
    firstword=tmplst[0]  
    if firstword[0] in ["a","e","i","o","u"]: tmplst=["an"]+tmplst     
    else: tmplst=["a"]+tmplst 
    reslst=txtlst+tmplst
    #debug_print("reslst",reslst)
    return " ".join(reslst)+"."
  elif tmplst and not classlst:
    reslst=txtlst
    #debug_print("reslst",reslst)
    return " ".join(txtlst)+" "+" and ".join(negproplst+proplst)+"."

def make_question_from_logic(ctxt,logic,isnegative,constant=False,keepvars=[]): 
  #debug_print("make_question_from logic input clauses",logic)
  #debug_print("make_question_from logic constant",constant)
  dummies=collect_dummy_constants(ctxt,logic,[])
  varmap={}
  vars=[]
  i=1
  for dummy in dummies:
    var="?:Q"+str(i)
    varmap[dummy]=var
    vars.append(var)
    i+=1
  
  if ctxt["question_dummification"]:
    replaced=logic_replace_el_map(logic,varmap)
  else:  
    replacements=[]
    replaced=replace_with_question_vars(logic,replacements)
    vars=[x[1] for x in replacements]
    #debug_print("make_question_from logic replaced",replaced)
    #debug_print("make_question_from logic replacements",replacements)
    #debug_print("make_question_from logic vars",vars)

  defn=make_definition(ctxt,replaced,vars)  
  #debug_print("make_question_from_logic makes initial defn 0",defn)
  defn=simplify_quantors(defn)
  #debug_print("make_question_from_logic makes initial defn 1",defn)
  convert=False
  if (defn and type(defn)==list and len(defn)>2 and defn[1]=="<=>" and
      defn[0][0].startswith(definition_prefix) and type(defn[2])==list and
      defn[2][0] in ["and","forall"]):
    # normal definition  like
    #['$def0']
    #<=>
    #['forall', ['?:S7'], [['isa', 'car', '?:S7'], '=>', ['prop', 'nice', '?:S7', '$generic', '$free_variable', ['$ctxt', 'Pres', '?:Fv8']]]]
    convert=True
    defatom=defn[0]
    rightside=defn[2]
    if rightside[0]=="and":
      formulas=rightside[1:]
    elif rightside[0]=="forall":  
      formulas=[rightside]
    newformulas=[]  
    for formula in formulas:
      if formula[0] in ["forall"] and all(map(not_every_var,formula[1])):
        # formula starts with an ordinary forall
        if len(formulas)==1 and type(formula[2])==list and len(formula[2])==3 and formula[2][1]=="=>":
          # formula is an implication
          newformula=["not",[formula[0],formula[1],[formula[2][0],"=>",[["not",defatom],"<=>",formula[2][2]]]]]  
          newformulas.append(newformula)
        else:
          convert=False
          break  
      else:
        # do not use conversion
        convert=False
        break   
  if convert:
    if len(newformulas)>1: newformulas=["and"]+newformulas
    else: newformulas=newformulas[0]
    defn=newformulas
    result=[defatom,defn]
  else:
    result=[None,defn]    
  #debug_print("make_question_from logic result",result)
  return result


def not_every_var(x):
  if not is_var(x): return True
  if x.endswith("_every"): return False
  return True 

def replace_dummies_with_vars(ctxt,logic):  
  dummies=collect_dummy_constants(ctxt,logic,[])
  #debug_print("res",dummies)
  varmap={}
  vars=[]
  i=1
  for dummy in dummies:
    var="?:Q"+str(i)
    varmap[dummy]=var
    vars.append(var)
    i+=1 
  replaced=logic_replace_el_map(logic,varmap)
  return replaced


def suitable_question_logic(ctxt,logic):
  #debug_print("suitable_question_logic logic",logic)
  if not logic: return False
  if type(logic)!=list: return False
  head=logic[0]
  if logic_contains_el(logic,unknown_value): return False
  if logic_contains_fully_free_variable(logic): return False
  if type(head)!=list and not logic_connective(head):
    return True   
  if collect_frame_vars(logic): return False  
  for el in logic:
    if not el: return False
    if logic_connective(el) and not el in ["and","&"]:
      return False
    if type(el)==list and logic_connective(el[0]):
      return False  
    if type(el)==list and len(el)>2 and logic_connective(el[1]):
      return False      
  return True


def collect_dummy_constants(ctxt,term,found=[]):
  if not term: return []
  if type(term)!=list: return []
  res=[]
  for lel in term:
    if dummyname_constant(ctxt,lel):
      if not (lel in found):
        found.append(lel)   
    else:
      res=collect_dummy_constants(ctxt,lel,found)      
  return found

def dummyname_constant(ctxt,constant):
  if type(constant)==str and dummy_name in constant:
    if "_" in constant:
      return True
    else:
      return False  
  else:
    return False  

def make_question_from_prequestion(ctxt,sentence,prequestion,question_dummy_name):  
  #debug_print("make_question_from_prequestion",prequestion)
  #debug_print("make_question_from_prequestion",sentence)
  if ctxt["question_dummification"]: 
    return make_question_from_prequestion_aux(ctxt,sentence,prequestion,question_dummy_name)
  if not prequestion: return prequestion
  result=replace_with_question_vars(sentence,prequestion)
  question={"@question":result}  
  #debug_print("make_question_from_prequestion result",result)
  return question


def make_question_from_prequestion_aux(ctxt,sentence,prequestion,question_dummy_name):
  #debug_print("make_question_from_prequestion_aux",prequestion)
  if not prequestion: return prequestion
  replacements={}
  atom=[]  
  if question_dummy_name:
    replacements["_"+question_dummy_name]=question_var  
  for preterm in prequestion:
    if type(preterm)==dict:
      atom.append(preterm['lemma'])
    else:      
      atom.append(make_term_from_preterm(sentence,preterm,replacements))     
  question={"@question":atom}  
  #debug_print("make_question_from_prequestion_aux result atom",atom)
  return question


def replace_with_question_vars(frm,replacements):
  if not frm: return frm
  if type(frm)==list:
    res=[]
    for el in frm:
      res.append(replace_with_question_vars(el,replacements))
    return res  
  elif type(frm)==dict:
    return frm["lemma"] 
  elif type(frm)==str and is_question_constant(frm):
    var="?:Q_"+frm
    if not any(item[0]==frm for item in replacements):
      replacements.append([frm,var])
    return var
  else:
    return frm

def is_question_constant(term):
  if not term: return term
  if type(term)!=str: return term
  for el in question_words: 
    if "_"+el in term: return True
  return False



def make_where_question(ctxt,defn,logic):
  #debug_print("make_where_question logic",logic)
  if not defn or type(defn)!=list or not logic or type(logic)!=list: return None
  if len(defn)!=2: return None
  defvar=defn[1]
  if not is_var(defvar): return None
  results=[]
  for rel in is_location_relations: #["in","on"]:
    newdefn=[defn[0],rel,defvar]
    newlogic=logic_replace_el(logic,defn,newdefn)
    newlogic=replace_location_relation(newlogic,rel,defvar)
    #debug_print("newdefn",newdefn)
    #debug_print("newlogic",newlogic)
    results.append(newlogic)
  if results: results=["and"]+results  
  #debug_print("results",results)  
  return results

def make_when_question(ctxt,defn,logic):
  #debug_print("make_when_question logic",logic)
  if not defn or type(defn)!=list or not logic or type(logic)!=list: return None
  if len(defn)!=2: return None
  defvar=defn[1]
  if not is_var(defvar): return None
  results=[]
  for rel in is_time_relations: #["in","during"]:
    newdefn=[defn[0],rel,defvar]
    newlogic=logic_replace_el(logic,defn,newdefn)
    newlogic=replace_location_relation(newlogic,rel,defvar)
    #debug_print("newdefn",newdefn)
    #debug_print("newlogic",newlogic)
    results.append(newlogic)
  if results: results=["and"]+results  
  #debug_print("results",results)  
  return results  


def replace_location_relation(logic,newrel,specterm):
  if not logic: return logic
  if type(logic)!=list: return logic  
  if logic[0] in ["rel2","-rel2"] and logic[1]=="on" and specterm in logic: 
    return [logic[0],newrel]+logic[2:] 
  elif logic[0] in ["rel2","-rel2"] and logic[1]=="during" and specterm in logic: 
    return [logic[0],newrel]+logic[2:]   
  res=[]
  for lel in logic:
    tmp=replace_location_relation(lel,newrel,specterm)
    res.append(tmp)
  return res

# =========== the end ==========
