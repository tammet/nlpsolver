# Small utilities for the nlpsolver.
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
import pprint
import http.client
import urllib.parse

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
import nlpglobals

import nlpcache

# ========= calling the server ====

def server_parse(text):
  cached=nlpcache.get_parse_from_cache(None,text)
  if cached:
    return cached

  conn = http.client.HTTPConnection(nlpglobals.server_name,nlpglobals.server_port,timeout=nlpglobals.server_timeout)
  encoded=urllib.parse.quote(text)
  # -- check that the server gave a usable answer --
  try:
    conn.request("GET", "/"+encoded)
  except KeyboardInterrupt:
    raise
  except:
    show_error("could not connect to the nlpserver "+nlpglobals.server_name+":"+str(nlpglobals.server_port)+
      ".\nStart the nlpserver.py or check the configured server name and port in nlpglobals.py.")  
    sys.exit(0)
  try:  
    resp = conn.getresponse()   
  except KeyboardInterrupt:
    raise   
  except:
    show_error("did not get a usable response from nlpserver")     
    sys.exit(0)  
  if resp.status!=200:
    show_error("unexcpected response status from nlpserver:"+
      str(resp.status)+" reason "+str(resp.reason))          
  # -- looks ok, try to parse json --    
  rawdata = resp.read()  
  try:
    data=json.loads(rawdata)
  except KeyboardInterrupt:
    raise  
  except:
    show_error("nlpserver response is not a correct json: "+  str(rawdata))
    sys.exit(0)
  nlpcache.add_parse_to_cache(None,text,data)
  return data


# ==== useful utilities for data  =======

def list_contains_keyval(lst,key,val):
  for word in lst:
    if word[key]==val: return word
  return False  

def list_contains_key(lst,key):
  for word in lst:
    if type(word)==dict and key in word: return True
  return False 

def list_contains_posval(lst,pos,val):
  for el in lst:
    if el[pos]==val: return True
  return False    

def logic_contains_el(lst,el):  
  if not lst: return False
  if type(lst)!=list: return False
  for lel in lst:
    if lel==el: 
      return True   
    elif type(lel)==list:
      if logic_contains_el(lel,el):
        return True
  return False

def logic_contains_fully_free_variable(frm):  
  if type(frm)==str and ("?:Ignore" in frm):
    return True
  if type(frm)==str and ("?:Unit" in frm):
    return True  
  elif type(frm)==str and ("$free_variable" in frm):  
    return True
  elif type(frm)==list:
    for el in frm:
      if logic_contains_fully_free_variable(el):
        return True
    return False
  else:
    return False    

def logic_replace_el(lst,what,replacer):  
  if lst==what: return replacer
  if not lst: return lst
  if type(lst)!=list: return lst
  res=[]
  for lel in lst:
    tmp=logic_replace_el(lel,what,replacer)
    res.append(tmp)
  return res

def logic_replace_el_map(lst,map):   
  if not lst: return lst
  if type(lst)==str:
    if lst in map: return map[lst]
    return lst
  if type(lst)!=list: return lst
  res=[]
  for lel in lst:
    tmp=logic_replace_el_map(lel,map)
    res.append(tmp)
  return res  

def logic_replace_el_defs(lst,what,replacer,defs):  
  if lst==what: return replacer
  if not lst: return lst
  if type(lst)!=list: return lst
  if lst[0] in defs:
    lst=lst+[replacer]
  res=[]  
  for lel in lst:
    tmp=logic_replace_el(lel,what,replacer)
    res.append(tmp)
  return res  


def logic_remove_quantors(lst,vars,quantors):   
  if not lst: return lst  
  if type(lst)!=list: return lst
  if (lst[0] in quantors and
      lst[1][0] in vars):
    tmp=logic_remove_quantors(lst[2],vars,quantors)
    return tmp
  res=[]
  for lel in lst:
    tmp=logic_remove_quantors(lel,vars,quantors)
    res.append(tmp)  
  return res  

def logic_generalize_framevars(ctxt,frm):  
  #debug_print("frm",frm)
  if not frm: return frm
  if type(frm)!=list: return frm
  if frm[0]==nlpglobals.ctxt_function and not(is_var(frm[2])):
    newfrm=frm.copy()
    framenr=nlpglobals.frame_var_prefix+str(ctxt["varnum"])
    ctxt["varnum"]+=1
    newfrm[2]=framenr
    return newfrm  
  res=[]  
  for lel in frm:
    tmp=logic_generalize_framevars(ctxt,lel) 
    res.append(tmp)  
  return res  

def filter_containing_listels(lst,what):
  res=[]
  for lel in lst:
    if logic_contains_el(lel,what):
      res.append(lel)
  return res    

def prop_flatten_logic_term(term):
  #debug_print("flatten",term)
  if type(term)==dict: 
    if "@logic" in term:
      newlogic=prop_flatten_logic_term(term["@logic"])    
      term["@logic"]=newlogic
      return term 
    elif "@question" in term:
      newlogic=prop_flatten_logic_term(term["@question"])    
      term["@question"]=newlogic  
      return term
    else:
      return term   
  elif type(term)!=list: return term 

  thisop=term[0]
  if thisop in ["logic"]:
    res=prop_flatten_logic_term(term[2])
  elif not (thisop in nlpglobals.logic_ops) and len(term)>1 and term[1] in ["&","|"]:
    #debug_print("term",term)
    if term[1]=="&": op="and"
    else: op="or"
    lst=[op]
    for el in term:
      if not (el in nlpglobals.logic_ops):
        lst.append(prop_flatten_logic_term(el))
    #debug_print("lst",lst)
    #sys.exit(0)    
    res=prop_flatten_logic_term(lst)    
  elif (thisop in ["exists","forall"] and len(term)==3 and len(term[1])==1 and  # TODO
        not logic_contains_el(term[2],term[1][0])):  
    res=prop_flatten_logic_term(term[2])    
  elif thisop in ["not"] and type(term[1])==list and term[1][0]=="not":
    res=prop_flatten_logic_term(term[1][1])  
  elif thisop in ["xor"]:
    res=[]
    for el in term[1:]:
      res.append(prop_flatten_logic_term(el))
      res.append("<~>")
    res.pop()       
  elif thisop in ["nor"]:
    # a nor b = -a and -b
    res=["and"]
    for el in term[1:]:
      tmp=prop_flatten_logic_term(el)
      res.append(["not",tmp])
    res=prop_flatten_logic_term(res)
  elif thisop in ["and","seq"]:
    res=[thisop]
    onlytrue=True
    for el in term[1:]:
      tmp=prop_flatten_logic_term(el)
      if tmp!=True: onlytrue=False
      if tmp==True:
        continue
      elif tmp==False:
        res=False
        break
      elif tmp and type(tmp)==list and tmp[0]==thisop:
        res=list(res)
        res.extend(x for x in tmp[1:] if x not in res)
        #res=res+tmp[1:]
      elif tmp in res:
        None
      elif el==None:
        None    
      else:
        res.append(tmp) 
    if res in [True,False]:
      None
    elif onlytrue:
      res=True  
    elif res and len(res)==1:
      res=True    
    elif res and len(res)==2:
      res=res[1]         
  elif thisop in ["or"]:
    res=[thisop]
    onlyfalse=False
    for el in term[1:]:
      tmp=prop_flatten_logic_term(el)
      if tmp!=False: onlyfalse=False
      if tmp==False:
        continue
      elif tmp==True:
        res=True
        break
      elif tmp and type(tmp)==list and tmp[0]==thisop:
        res=list(res)
        res.extend(x for x in tmp[1:] if x not in res)
        #res=res+tmp[1:]
      elif tmp in res:
        None  
      else:
        res.append(tmp) 
    if res in [True,False]:
      None    
    elif onlyfalse:
      res=False 
    elif res and len(res)==1:
      res=False 
    elif len(res)==1:
      res=res[1]            
  else:
    res=[]
    for el in term:
      res.append(prop_flatten_logic_term(el))  
    if res and len(res)==3 and res[1]=="=>":
      if res[0]==True:
        res=res[2]
      elif res[2]==True:
        res=res[0]
  
  if (type(res)==list and res[0]=="not" and type(res[1])==list and type(res[1][0])==str):
    pred=res[1][0]
    if pred in nlpglobals.logic_ops or pred=="logic":
      return res
    elif pred[0]=="-":
      return [pred[1:]]+res[1][1:]
    else:
      return ["-"+pred]+res[1][1:] 
  return res


def flatten_seq_term(term,oplist=[]):    
  #debug_print("flatten_seq_term",term)
  if not term: return term
  if type(term)!=list: return term  
  thisop=term[0]
  if type(thisop)==list:
    thisop="seq"
    term=["seq"]+term
  if thisop in ["seq"] or thisop in [oplist]:
    res=["seq"]  
    for el in term[1:]:
      tmp=flatten_seq_term(el,oplist)
      if (tmp and type(tmp)==list and (tmp[0] in ["seq"] or tmp[0] in oplist)):
        res=res+tmp[1:]
      else:
        res.append(tmp)
  else:
    res=[]
    for el in term:
      res.append(flatten_seq_term(el,oplist))
  #debug_print("flatten_seq_term res",res)             
  return res



def simplify_quantors(term):  
  if not(term): return term
  if type(term)!=list: return term  
  thisop=term[0]
  if (thisop in ["exists","forall"] and
      len(term)>2 and type(term[1])==list):
    vars=[]
    for var in term[1]:
      if not is_constant(var): vars.append(var)
    if not vars:
      res=simplify_quantors(term[2])  
    else:
      tmp=simplify_quantors(term[2])
      res=[thisop,vars,tmp]
    return res                   
  else:
    res=[]
    for el in term:
      res.append(simplify_quantors(el))      
    return res

def is_constant(term):
  if not(term): return False
  if type(term)!=str: return False
  if term[0]!="?": return True
  return False 


def collect_free_vars(term,bound=[],collected=[]):
  if not term: return collected
  if type(term)==str:
    if is_var(term):
      if not(term in bound) and not(term in collected):
        return [term]+collected
    return collected
  if type(term)!=list: 
    return collected
  if term[0] in ["forall","exists"]:
    tmp=collect_free_vars(term[2],term[1]+bound,collected)
    return tmp
  for el in term:
    collected=collect_free_vars(el,bound,collected)
    #debug_print("term",term)
    #debug_print("collected",collected)    
  return collected  

def collect_frame_vars(term):
  candidates=collect_free_vars(term)  
  res=[]
  for var in candidates:
    if var.startswith(nlpglobals.frame_var_prefix):
      res.append(var)
    #if var.startswith(nlpglobals.unit_var_prefix):
    #  res.append(var)  
  return res    

def merge_framevars(term):
  #debug_print("* term",term)
  vars=collect_frame_vars_lex(term)
  #debug_print("* vars",vars)
  if not vars or len(vars)<2: return term
  for var in vars[1:]:
    term=logic_replace_el(term,var,vars[0])
  return term  

def collect_frame_vars_lex(term,vars=[]):
  if not term: return vars
  if type(term)!=list:
    if type(term)==str:
      if term.startswith(nlpglobals.frame_var_prefix):
        if term not in vars:
          vars.append(term)
          return vars
    return vars      
  if term[0]=="logic": 
    return collect_frame_vars_lex(term[2])
  for el in term:
    collect_frame_vars_lex(el)
  return vars  

def merge_known_framevars(term,vars):
  #debug_print("term",term)
  #debug_print("vars",vars)
  if not term or not vars or len(vars)<2: return term
  for var in vars[1:]:
    term=logic_replace_el(term,var,vars[0])
  debug_print("result",term)  
  return term    


def is_var(x):
  if not type(x)==str: return False
  if len(x)<3: return False
  if x[0]=="?" and x[1]==":": return True
  return False    

def remove_logic_annotations(term):
  if not term: return term
  if type(term)!=list: return term
  if term[0]=="logic": 
    return remove_logic_annotations(term[2])
  res=[]
  for el in term:
    tmp=remove_logic_annotations(el)
    res.append(tmp)
  return res  

def logic_connective(x):
  if type(x)==str and (x in ["and","or","not","&","|","<=","=>","<=>","exists","forall"]):
    return True
  else:
    return False  

def is_number_str(s):
  try:
    float(s)
    return True
  except ValueError:
    return False


# ==== pre-logic replacements ======

def replace_property_objects(ctxt,sentence,tree,thing,var):
  if not tree: return tree  
  if type(tree)==dict: 
    if tree==thing:
      return var
    else:
      return tree
  if not type(tree)==list: return tree    
  if tree[0] in ["svo","sv","ref"]:
    #newtree=[tree[0],[tree[1][0]]
    newlist=[tree[1][0]]
    for el in tree[1][1:]:
      newel=replace_property_objects(ctxt,sentence,el,thing,var)
      newlist.append(newel)
    return [tree[0],newlist] 
  elif tree[0] in ["props"]:   
    treething=tree[-1]
    if treething==thing:
      return var
    else:
      return tree
  else:
    newtree=[]
    for el in tree:
      newel=replace_property_objects(ctxt,sentence,el,thing,var)
      newtree.append(newel)
    return newtree


# ======= linguistic helpers =======


# ====== linguistic helpers ========

def get_root(sentence):
  return get_word_by_keyval(sentence,"deprel","root")
  

def get_word_by_keyval(sentence,key,val):
  if not sentence: return None
  for word in sentence:
    if word[key]==val:
      return word
  return None  

def get_children(sentence,parent):
  res=[]
  if not parent: return []
  parent_id=parent['id']
  for word in sentence:
    if word['head']==parent_id:
      if not end_punct_word(word):
        res.append(word)
  return res 

def get_parent(sentence,child):
  res=None
  if not child: return None
  head_id=child["head"]
  if head_id==0: return None  
  for word in sentence:
    if word['id']==head_id:
      if not end_punct_word(word):
        return word
  return None     

def get_previous_word(sentence,word):
  if not word: return None
  word_id=word["id"]    
  for el in sentence:
    if el['id']==word_id-1:
      return el
  return None        

def get_next_word(sentence,word):
  if not word: return None
  word_id=word["id"]    
  for el in sentence:
    if el['id']==word_id+1:
      return el
  return None     

def end_punct_word(word):
  lemma=word["lemma"]
  if lemma in nlpglobals.end_punctuation_lemmas:
    return True
  else:
    return False

def word_has_feat(word,feat,val):
  if not word: return False
  if not ("feats" in word): return False
  tmp=word["feats"]
  if not tmp: return False
  tmplst=tmp.split("|")
  for el in tmplst:
    tmpel=el.split("=")
    if tmpel and tmpel[0]==feat and tmpel[1]==val:
      return True
  return False    

def get_word_feat(word,feat):
  if not word: return None
  if not ("feats" in word): return None
  tmp=word["feats"]
  if not tmp: return None
  tmplst=tmp.split("|")
  for el in tmplst:
    tmpel=el.split("=")
    if tmpel and tmpel[0]==feat:
      return tmpel[1]      
  return None  

def word_has_article(ctxt,sentence,word,deforindef):
  #debug_print("word_has_article word",word)
  if not word: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:    
    if (child["deprel"]=="det" and
        word_has_feat(child,"PronType","Art")): #       
      if deforindef=="indefinite":
        if word_has_feat(child,"Definite","Ind"):
          return True 
      elif deforindef=="definite":
        if word_has_feat(child,"Definite","Def"):
          return True     
  return False

def word_has_quantor(ctxt,sentence,word,existorforall):
  debug_print("word_has_quantor word ",word)
  debug_print("word_has_quantor existorforall ",existorforall)
  if not word: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:    
    if (child["deprel"]=="det"):
      if existorforall=="exist":
        if child["lemma"] in ["some"]:
          return True
      elif existorforall=="forall":
        if child["lemma"] in ["all"]:
          return True
  return False  

def word_has_child_in_deprel_upos(ctxt,sentence,word,deprel,upos):
  #debug_print("word_has_child_in_deprel_upos word ",word)  
  if not word: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:    
    if (child["deprel"] in deprel) and (child["upos"] in upos):
      return child
  return False   

def word_has_child_in_deprel_lemma(ctxt,sentence,word,deprel,lemmas):   
  if not word: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:    
    if (child["deprel"] in deprel) and (child["lemma"] in lemmas):
      return child
  return False 

def word_has_child_in_lemma(ctxt,sentence,word,lemmas):   
  if not word: return False
  children=get_children(sentence,word)
  if not children: return False
  for child in children:    
    if (child["lemma"] in lemmas):
      return child
  return False   

def adjective_lemma(s):
  return s.lower()


def passive_verb(ctxt,word):
  if not word: return False
  if word["lemma"] in ["have"]:
    return True
  return False

def variable_shaped_word(word):
  if (type(word)==dict and word["upos"] in ["NOUN","PROPN","PRON"] 
      and variable_shaped_lemma(word["lemma"])):
    return True
  else:
    return False

def variable_shaped_lemma(lemma):
  if type(lemma)!=str: return False
  if len(lemma)==0: return False
  if (lemma[0] in ["x","y","z","X","Y","Z"]):
    if len(lemma)==1: return True
    if lemma[1:].isnumeric(): return True
    if len(lemma)<3: return False
    if lemma[1]=="_" and lemma[2:].isnumeric(): return True
  return False  


# ====== small linguistic helpers ===============

def process_lemma(lemma):
  if type(lemma)!=str: 
    return lemma
  else:
    return lemma.lower()  

# ====== print ud list as a tree ===================

def debug_print_sentence_trees(sentences):
  if not nlpglobals.options["debug_print_flag"]: return
  nr=0
  for sentence in sentences:
    print("\nsentence "+str(nr)+":"+"\n============")
    debug_print_sentence_tree(sentence)
    nr+=1

def debug_print_sentence_tree(sentence,rootid=0,spaces="",printedids=[]):
  if not nlpglobals.options["debug_print_flag"]: return
  if not sentence: return 
  #print("sentence:",sentence)
  printedids=printedids[::-1] # copy
  for word in sentence:
    #print("word",word)
    #debug_print("word:",word)
    if word["head"]==rootid:
      deprel=word["deprel"]
      #if deprel=="root": deprel=""            
      if word["id"] in printedids: 
        print(spaces+deprel+": id "+str(word["id"]))
      else:  
        print(spaces+deprel+": "+nice_word_strrep(word))
        printedids.append(word["id"])
        debug_print_sentence_tree(sentence,word["id"],spaces+"  ",printedids)
        

def nice_word_strrep(word):
  if not nlpglobals.options["debug_print_flag"]: return
  s=word["lemma"]
  s+=" [id:"+str(word["id"])
  s+=" text:"+word["text"]
  s+=" upos:"+word["upos"]
  s+=" xpos:"+word["xpos"]
  if "feats" in word:
    s+=" feats:"+word["feats"]
  if "ner" in word:  
    s+=" ner:"+word["ner"]
  s+="]"  
  return s


def debug_print_logical_sentence_tree(tree,spaces=""):
  if not nlpglobals.options["debug_print_flag"]: return
  if not tree: return 
  #debug_print("print",tree)
  if type(tree)==dict:
    print(spaces+str(tree))
  elif type(tree)!=list:
    print(spaces+str(tree))
  elif tree[0] in ["svo"]:
    svo=tree[1][1:]
    print(spaces+tree[0]+" [",object_list_to_str(svo[0]),object_list_to_str(svo[1]),object_list_to_str(svo[2])+" ]")
  elif tree[0] in ["sv"]:
    svo=tree[1][1:]
    print(spaces+tree[0]+" [",object_list_to_str(svo[0]),object_list_to_str(svo[1])+" ]")  
  elif tree[0] in ["ref"]:
    ref=tree[1][1:]
    print(spaces+tree[0]+"  ",object_list_to_str(ref[0]),object_list_to_str(ref[1]))
    debug_print_logical_sentence_tree(ref[2],spaces+"      ")
  elif tree[0] in ["logic"]:  
    print(spaces+"logic"+"  ",str(tree[2]).replace(", ",",").replace("'",""))
  elif type(tree[0])==list:
    print(spaces)
    for el in tree:
      debug_print_logical_sentence_tree(el,spaces+"  ")  
  else:
    print(spaces+tree[0])
    for el in tree[1:]:
      debug_print_logical_sentence_tree(el,spaces+"  ")

def object_list_to_str(obj,commas=True):
  #debug_print("obj",obj)
  if not obj and obj!=0: return ""
  if type(obj)==str: return obj
  elif type(obj)==int or type(obj)==float: return str(obj)
  elif type(obj)==bool: return str(obj)
  if type(obj)==dict: 
    if "relation" in obj:
      parts=obj["relation"].split("_")
      return obj["lemma"]+":"+str(obj["relation"])
    elif "argument" in obj:
      if "argprops" in obj and obj["argprops"][1]:
        return obj["lemma"]+"("+object_list_to_str(obj["argprops"])+")"
      else:
        return obj["lemma"]+"("+object_list_to_str(obj["argument"])+")"      
    elif "relatedobjects" in obj:
      objs=obj["relatedobjects"]
      slst=[]      
      for sobj in objs:
        #debug_print("sobj",sobj)
        oslst=[]        
        objs=sobj["case"]["lemma"]+"_"+sobj["obj"]["lemma"]
        oslst.append(str(sobj["case"]["lemma"]))
        if "proplogic" in sobj and sobj["proplogic"]:
          logic=sobj["proplogic"]
          slogic=object_list_to_str(logic)         
          oslst.append(slogic)   
        else:
          oslst.append(str(sobj["obj"]["lemma"]))      
        ostr=",".join(oslst)
        ostr="{"+ostr+"}"
        slst.append(ostr)
      res=",".join(slst)      
      res="("+res+")"  
      res=obj["lemma"]+res
      return res 
    elif "relatedverbs" in obj:
      objs=obj["relatedverbs"]
      slst=[]      
      for sobj in objs:
        #debug_print("sobj",sobj)
        oslst=[]        
        objs=sobj["case"]["lemma"]+"_"+sobj["obj"]["lemma"]
        oslst.append(str(sobj["case"]["lemma"]))
        if "proplogic" in sobj and sobj["proplogic"]:
          logic=sobj["proplogic"]
          slogic=object_list_to_str(logic)         
          oslst.append(slogic)   
        else:
          oslst.append(str(sobj["obj"]["lemma"]))      
        ostr="_".join(oslst)
        ostr="_"+ostr+"_"
        slst.append(ostr)
      res=",".join(slst)      
      res="("+res+")"  
      res=obj["lemma"]+res
      return res   
    else:
      return obj["lemma"]  

  # here obj is list
  #debug_print("obj",obj)
  if obj[0] in ["svo","sv","ref"]:
    res="["+obj[0]+" "+object_list_to_str(obj[1][1:],False)+"]"
    return res
  if obj and type(obj[0])==str:   
    s="["+str(obj[0])
    for el in obj[1:]:
      if commas:
        s+=","+object_list_to_str(el)
      else:
        s+=" "+object_list_to_str(el)  
    s+="]"  
  else:
    s="["+object_list_to_str(obj[0])
    for el in obj[1:]:
      if commas:
        s+=","+object_list_to_str(el)
      else:
        s+=" "+object_list_to_str(el)         
    s+="]" 
  return s  

def debug_print_logic_list(lst,spaces=""):
  if not nlpglobals.options["debug_print_flag"]: return
  #debug_print("lst",lst)
  #debug_print("spaces",len(spaces))
  if lst==0: print(lst)
  elif not lst: return
  count=0
  for el in lst:    
    count+=1
    if not el: debug_print_logic(el,spaces+"  ")
    if type(el)==dict:
      s=spaces+" {"
      for key in el:
        if not (key in ["@logic","@question","@confidence"]):
          s+=key+":"+str(el[key])+", "
      print(" "+s,end="")
      s=""
      for key in el:
        if key in ["@logic","@question","@confidence"]:
          s+=" "+key+": "           
          print(s,end="")    
          debug_print_logic(el[key],"",newline=False)
          break
      if count<len(lst): 
        print(" "+"}")  
      else:
        print(" "+"}")
    else:
      #debug_print("el",el)
      debug_print_logic(el,spaces+"  ",newline=False)
      print() 
      #debug_print(spaces+"b}",end="")   
      

def debug_print_logic(tree,spaces="",newline=True):
  if not nlpglobals.options["debug_print_flag"]: return
  if (not tree) and tree!=0: return 
  if type(tree)!=list:
    print(spaces+str(tree).replace(", ",",").replace("'",""))
  elif tree[0] in ["or","if","unless","nor","xor"]:  
    print(spaces,end="")
    tmp=object_list_to_str(tree)
    print(tmp,end="")
    if newline: print()
    #for el in tree[1:]:
    #  debug_print_logic(el,end="")      
    #print(spaces+"]",end="")  
  elif tree[0] in ["and"]:  
    count=0
    print(spaces+"["+str(tree[0]),end="")
    for el in tree[1:]:      
      #debug_print_logic(el)
      if count<len(tree[1:]): 
        print("\n"+spaces+"   ",end="")
        debug_print_logic(el,"",newline=False)
        #print("daa",end="")
      else: 
        debug_print_logic(el,"",newline=False)
        print("]",end="")
      count+=1  
    print("]",end="") 
  else:
    print(spaces+str(tree).replace(", ",",").replace("'",""),end="")



def make_classic_logic_str(tree,spaces=""):
  if (not tree) and tree!=0: return 
  if type(tree)!=list:
    return(spaces+str(tree).replace(", ",",").replace("'",""))
  if type(tree[0])==list:
    tmp=[]
    for el in tree:
      tmp.append(make_classic_logic_str(el))
    return " ".join(tmp)
  else:
    return make_classic_clause_str(tree)   


def make_classic_clause_str(tree):  
  if (not tree) and tree!=0: return ""
  elif type(tree)==str:
    if tree.startswith("?:"): return "?"+tree[2:]
    else: return tree
  elif type(tree)!=list:
    return(str(tree)) #.replace(", ",",").replace("'",""))
  elif type(tree[0])==list:
    sl=[]
    for atom in tree:
      sl.append(make_classic_clause_str(atom))
    if len(sl)>2:
      if sl[1]=="<=>":
        return " ".join(sl)
      else:
        return " | ".join(sl)  
    else:    
      return " | ".join(sl)    
  elif tree[0] in ["exists","forall"]:
    v=list(map(lambda x: make_classic_clause_str(x), tree[1]))
    sl=[tree[0],"["+" ".join(v)+"]",make_classic_clause_str(tree[2])]   
    return "("+" ".join(sl)+")"      
  elif tree[0] in ["and","or","=>","<=>"]:  
    sl=list(map(lambda x: make_classic_clause_str(x), tree[1:]))
    if tree[0]=="and": s=" & "
    elif tree[0]=="or": s=" | "
    elif tree[0]=="=>": s="=>"
    elif tree[0]=="<=>": s="<=>"
    else: s=" "+tree[0]+" "
    return s.join(sl)
  else:
    s=make_classic_clause_str(tree[0])+"("
    sl=[]   
    for atom in tree[1:]:
      sl.append(make_classic_clause_str(atom)) 
    s+=",".join(sl)
    s=s+")"
    return s


# remove exceptions from a list of clauses

def remove_exceptions(lst):
  #debug_print("remove_exceptions lst",lst)
  if not lst: return lst
  res=[]
  for el in lst:
    if (not el) or type(el)!=dict: 
      res.append(el)
      continue
    if "@logic" in el:
      logic=el["@logic"]
    elif "@question" in el:
      logic=el["@question"]  
    else:
      res.append(el)
      continue  
    newlogic=[]
    for atom in logic:
      if (not atom) or type(atom)!=list:
        newlogic.append(atom)
        continue
      if atom[0]!="$block":
        newlogic.append(atom)
    #debug_print("newlogic",newlogic)    
    newel=el.copy()
    if "@logic" in el:
      newel["@logic"]=newlogic
    elif "@question" in el:
      newel["@question"]=newlogic       
    res.append(newel)    
  return res

def remove_prop_extras(lst):
  #debug_print("remove_prop_extras lst",lst)
  if not lst: return lst
  res=[]
  for el in lst:
    #debug_print("el",el)
    if (not el) or type(el)!=dict: 
      res.append(el)
      continue
    if "@logic" in el:
      logic=el["@logic"]
    elif "@question" in el:
      logic=el["@question"]  
    else:
      res.append(el)
      continue  
    newlogic=[]
    if not logic[0] in ["and","or"]:
      atom=logic
      if atom[0] in ["prop","-prop"]:
        newatom=[atom[0],atom[1],atom[2]]
        if len(atom)>5: newatom=newatom+atom[5:]
        newlogic=newatom
      else:
        newlogic=atom  
    else:  
      for atom in logic:
        #debug_print("atom",atom)
        if (not atom) or type(atom)!=list:
          newlogic.append(atom)
          continue
        if atom[0] in ["prop","-prop"]:
          newatom=[atom[0],atom[1],atom[2]]
          if len(atom)>5: newatom=newatom+atom[5:]
          newlogic.append(newatom)
        else:
          newlogic.append(atom)
    #debug_print("newlogic",newlogic)    
    newel=el.copy()
    if "@logic" in el:
      newel["@logic"]=newlogic
    elif "@question" in el:
      newel["@question"]=newlogic       
    res.append(newel) 
  #debug_print("remove_prop_extras res",res)     
  return res  
  
def remove_confidences_from_logic(lst):
  #debug_print("remove_confidences_from_logic lst",lst)
  if not lst: return lst  
  if type(lst)==list:
    res=list(filter(lambda x: type(x)!=list or x[0]!=nlpglobals.confidence_function,lst))
    res=list(map(lambda x: remove_confidences_from_logic(x), res))
  else:
    res=lst
  return res

def remove_prop_extras_from_logic(lst):
  #debug_print("remove_prop_extras_from_logic lst",lst)
  if not lst: return lst  
  if type(lst)==list:
    if lst[0] in ["prop","-prop"]:
      atom=lst
      newatom=[atom[0],atom[1],atom[2]]
      if len(atom)>5: newatom=newatom+atom[5:]
      res=newatom
    else:
      res=list(map(lambda x: remove_prop_extras_from_logic(x), lst))
  else:
    res=lst
  return res


# ======= convert doc to an original sentence =====

def doc_to_original_sentence(doc):
  lastpos=0 
  for word in doc:       
    if word["end_char"]>lastpos: lastpos=word["end_char"]
  res=' '*lastpos+' '*lastpos
  for word in doc:
    start=word["start_char"]
    end=word["end_char"]
    res = res[:start] + word["text"] + res[end + 1:]   
  res=res.strip()  
  return res  


# ===== composing a text from the parse tree ===

def make_text_from_doc(doc):
  if not doc: return ""
  lastpos=0
  firstpos=100000000
  for word in doc:
    if ("end_char" in word) and word["end_char"]>lastpos:
      lastpos=word["end_char"]
    if ("start_char" in word) and word["start_char"]<firstpos:
      firstpos=word["start_char"]  
  s=' ' * ((lastpos-firstpos)+1)
  for word in doc:
    s=s[0:(word["start_char"]-firstpos)] + word["text"] + s[(word["end_char"]-firstpos) :]
  return s.strip()  

def make_text_from_doc_sep(doc):
  if not doc: return ""
  lst=[]
  for word in doc:
    lst.append(word["text"])
  res=" ".join(lst)
  return res.strip()


# ===== split sentence utils used by nlpquestion ===

def split_sentence_startswith_pos(sp,chunk):
  if not sp or not chunk: return 0
  for x in range(0,len(chunk)):
    if type(chunk[x])==str:
      if (sp[x]!=chunk[x] and sp[x].upper()!=chunk[x].upper()):
        return 0
    elif type(chunk[x])==list:
      found=False
      for chunkel in chunk[x]:
        if (sp[x]==chunkel or sp[x].upper()==chunkel.upper()):
          found=True
          break
      if not found:
        return 0  
  return len(chunk)   

def split_sentence_remove_trailingchar(sp,c):
  if not sp or not c: return sp
  if sp[-1]==c: return sp[:-1]
  if sp[-1][-1]==c: return sp[:-1]+[sp[-1][:-1]]
  return sp


# ======== text conversions ======================

def measure_adv_to_noun(s):
  #debug_print("s",s)
  for el in nlpglobals.measure_words:
    val=nlpglobals.measure_words[el]
    if "morenouns" in val:
      if s in val["morenouns"]: return el
    elif "lessnouns" in val:
      if s in val["lessnouns"]: return el  
  return s

def is_unitword(s):
  #debug_print("s",s)
  for el in nlpglobals.measure_words:
    val=nlpglobals.measure_words[el]
    if "units" in val:
      if s in val["units"]: return el
  return False  

def parse_int(string):
  if not string: return string
  if type(string)==int: return string
  try:
    res=int(string)
    return res
  except:
    None  
  ONES = {
    'zero': 0,
    'one': 1,
    'two': 2,
    'three': 3,
    'four': 4,
    'five': 5,
    'six': 6,
    'seven': 7,
    'eight': 8,
    'nine': 9,
    'ten': 10,
    'eleven': 11,
    'twelve': 12,
    'thirteen': 13,
    'fourteen': 14,
    'fifteen': 15,
    'sixteen': 16,
    'seventeen': 17,
    'eighteen': 18,
    'nineteen': 19,
    'twenty': 20,
    'thirty': 30,
    'forty': 40,
    'fifty': 50,
    'sixty': 60,
    'seventy': 70,
    'eighty': 80,
    'ninety': 90,
  }

  numbers = []
  for token in string.replace('-', ' ').split(' '):
    if token in ONES:
      numbers.append(ONES[token])
    elif token == 'hundred':
      numbers[-1] *= 100
    elif token == 'thousand':
      numbers = [x * 1000 for x in numbers]
    elif token == 'million':
      numbers = [x * 1000000 for x in numbers]
  if not numbers: return None    
  return sum(numbers)

def clause_list_to_json(clauselist):
  reslst=[]
  for clause in clauselist:
    clauserep=[]
    if "@logic" in clause: logic=clause["@logic"]
    if "@question" in clause: logic=clause["@question"]
    if not logic: continue
    if logic[0] in ["or","and"]:
      newlogic=[]
      for atom in logic:
        newatom=json.dumps(atom,separators=(',', ':')) #pprint.pformat(atom,width=80,indent=0,sort_dicts=False)
        newlogic.append(newatom)        
      if len(logic)>3:
        logicstr=",\n    ".join(newlogic)  
      else:
        logicstr=", ".join(newlogic)  
      logicstr=("["+logicstr+"]")      
    else:
      newlogic=json.dumps(logic,separators=(',', ':'))    
      logicstr=newlogic
    clauserep.append("{")  
    count=0    
    if "@logic" in clause: clauserep.append("\"@logic\": "+logicstr)
    if "@question" in clause: clauserep.append("\"@question\": "+logicstr)
    for key in clause:
      if not (key in ["@logic","@question"]):
        #if count>0: reslst.append("   ")
        clauserep.append(",\n "+json.dumps(key)+": "+json.dumps(clause[key]))
        count+=1
    clauserep.append("}")    
    clausestr="".join(clauserep)    
    reslst.append(clausestr)
  res="[\n"+",\n".join(reslst)+"\n]"
  #print(res)
  return res  

# ====== debug printing and error handling ==========

def debug_print(label,format="placeholder1",data="placeholder2"):
  if not nlpglobals.options["debug_print_flag"]: return
  print()
  print(label,end='') 
  if format!="placeholder1" and data=="placeholder2":
    data=format
    format="placeholder1"
  if data=="placeholder2":     
    print()
    return
  if format and type(data)==list:
    print(":")    
    for el in data:
      if el and type(el)==list:
        print("  [")
        for subel in el:
          print("   ",subel)
        print("  ]")  
      else:
        print(" ",el)        
  elif type(data)==list:
    print(":")
    for el in data:
      print(" ",el)  
  elif type(data)==dict:
    print(":")
    for key in data:
      print(" ",key,":",data[key])     
  else: 
    print(" :",data)

def debug_pprint(label,data="placeholder"):
  if not nlpglobals.options["debug_print_flag"]: return
  print()
  print(label,end='')
  if data=="placeholder": 
    print()
    return
  if type(data)==list:
    print(":")
    pprint.pprint(data)   
  elif type(data)==dict:
    print(":")
    pprint.pprint(data)     
  else: 
    print(" :",data)  

# print a direct answer, typically when a critical part is misunderstood:

def print_answer(str):
  print(str)

# show an actual error (no server, prover error or smth like that)

def show_error(errstr):
  print("Error:",errstr)

def errhandle(errstr):
  print("Error, exiting:",errstr)
  sys.exit(-1)

# =========== the end ==========

"""
import functools

def debug(func):
    #Print the function signature and return value
    @functools.wraps(func)
    def wrapper_debug(*args, **kwargs):
        args_repr = [repr(a) for a in args]                      # 1
        kwargs_repr = [f"{k}={v!r}" for k, v in kwargs.items()]  # 2
        signature = ", ".join(args_repr + kwargs_repr)           # 3
        print(f"Calling {func.__name__}({signature})")
        value = func(*args, **kwargs)
        print(f"{func.__name__!r} returned {value!r}")           # 4
        return value
    return wrapper_debug

@debug
def make_greeting(name, age=None):
    if age is None:
        return f"Howdy {name}!"
    else:
        return f"Whoa {name}! {age} already, you are growing up!"

# --------------

import functools
from decorators import count_calls

def cache(func):
    #Keep a cache of previous function calls
    @functools.wraps(func)
    def wrapper_cache(*args, **kwargs):
        cache_key = args + tuple(kwargs.items())
        if cache_key not in wrapper_cache.cache:
            wrapper_cache.cache[cache_key] = func(*args, **kwargs)
        return wrapper_cache.cache[cache_key]
    wrapper_cache.cache = dict()
    return wrapper_cache

@cache
@count_calls
def fibonacci(num):
    if num < 2:
        return num
    return fibonacci(num - 1) + fibonacci(num - 2)


@count_calls
def fibonacci(num):
    if num < 2:
        return num
    return fibonacci(num - 1) + fibonacci(num - 2)

# ---------


import functools

@functools.lru_cache(maxsize=4)
def fibonacci(num):
    print(f"Calculating fibonacci({num})")
    if num < 2:
        return num
    return fibonacci(num - 1) + fibonacci(num - 2)



"""