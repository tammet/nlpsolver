#!/usr/bin/env python3

# The main file of the nlpsolver system.
#
# Solve questions posed in natural language:
# give an nlp text as input, get an answer as a result.
#
# Uses:
#  nlpserver.py running stanza (both with the Apache licence)
#  gk logic solver (free for research and experimentation)
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

# the core ud-to-logic converter parts are in nlptologic.py
from nlptologic import *

# prover calling and prover result conversion parts are in nlpprover.py
from nlpprover import *

# optional llm simplifications are in nlpllm
from nlpllm import *

# small utilities are in nlputils.py
from nlputils import *

# ====== main is used for calling on command line ======

# main is used for calling from command line: use like
#
# ./nlpsolver "Elephants are animals. John is an elephant. John is an animal?"
#
# or add keys like (see below for the full list)
#
# explain the result:   ./nlpsolver "Elephants are animals. John is an elephant. John is an animal?" -explain
# processing details:   ./nlpsolver "Elephants are animals. John is an elephant. John is an animal?" -debug

import datetime 
from datetime import timedelta 

helptext="""call nlpsolver with a natural language text like
"Elephants are big. John is an elephant. Who is big?"
and/or a filename as an argument, with optional keys:

basic keys:
 -explain   : give an English explanation/proof of the answer    
 -logic     : show logic  
 -usekb     : use background knowledge in a memory kb imported by the server
 -debug     : show the details of the whole process
 -simple    : use a very simplified representation: automatically switches on all the three following keys,
              which can be also switched on separately:
    -nocontext : use a simplified representation without context (time, situation) when creating logic 
    -noexceptions : use a simplified representation without exceptions (blockers) when creating logic
    -simpleproperties: use simplified properties without strength and type parameters; also turns on -noexceptions
 -nosolve   : convert to logic, show prover json input, but do not run the prover  
 -help      : output this helptext 

optional parsing helpers:
 -llm       : use a large language model (llm) to simplify the sentences
 -amr       : use an amr parser to gain additional information for words/sentences 

controlling the prover:
 -seconds N : give N seconds for proof search (default 1)
 -prover    : show prover json input/output
 -rawresult : output only the json result from the prover
 -axioms file1.js ... fileN.js   : use these files as axioms instead of the axioms_std.js
 -strategy file.js : use the given json strategy file instead of the default search strategy of the prover
 -nokb      : do not use a shared memory knowledge base (NOT implemented yet)      
 -printlevel N : use N>10 to see more of the search process of the prover (10 is default, try 12)
"""

def main():    
  # - - - parse cmd line - - -
  text,newoptions=parse_cmd_line(helptext) 
  if not text:
    show_error("No text given: \n"+helptext)
    sys.exit(0)  
  #debug_print("text",text)  
  result=answer_question(text,newoptions)
  #debug_print("Answer:")
  print(result)

# ====== answer_question carries out the whole process ======


def answer_question(text,newoptions=None):
  debug_print("answer_question text",text)    
  if newoptions: set_global_options(newoptions) 
  # --- read textual replacement rules ---
  global replacement_complex_rules
  rules=read_replacement_data()
  nlpglobals.replacement_text_rules=rules[0]
  nlpglobals.replacement_complex_rules=rules[1]
  #print(nlpglobals.replacement_text_rules)
  #return
  # - - - make optional llm simplifications - - - -
  llm_mapping=None
  if options["llm_flag"]:
    simpres=llm_simplify(text)
    text=simpres[0]
    llm_mapping=simpres[1]
  # - - - do basic text replacements - - - -
  text=prepare_text(text)     
  debug_print("answer_question prepared text",text)  
  # - - - call ud parser via server - - - 
  data = server_parse(text)
  doc=data["doc"]  
  entities=data["entities"] 
  debug_print("doc tree:")
  debug_print_sentence_trees(doc)     
  debug_print("entities",entities)  
  # - - - convert to logic and solve - - - 
  logic_objects=parse_ud(doc,entities)    
  #debug_print("logic_objects",logic_objects)

  if "logic" in logic_objects: logic=logic_objects["logic"]
  else: logic=None
  if "objects" in logic_objects: objects=logic_objects["objects"]
  else: objects=None
  if "question_sentence" in logic_objects: question_sentence=logic_objects["question_sentence"]
  else: question_sentence=None
  if "question_type" in logic_objects: question_type=logic_objects["question_type"]
  else: question_type=None
  if "logic_sentence_map" in logic_objects: logic_sentence_map=logic_objects["logic_sentence_map"]
  else: logic_sentence_map=None
  #debug_print("logic")
  #debug_print_logic_list(logic)
  #debug_print("objects",objects)
  #debug_print("question_sentence",question_sentence)
  #debug_print("logic_sentence_map",logic_sentence_map)
  #debug_print("")
  origlogic=logic
  if options["debug_print_flag"] or options["show_logic_flag"]:     
    print()
    show_objects(logic_objects) 
    print()
  if options["show_logic_flag"]: 
    print()    
    show_sentence_clauses(logic_objects)     
  if options["show_logic_flag"]:    
    print()
    print("=== result: ===\n")  
  
  if (not options["prover_nosolve_flag"] and origlogic and 
      (not list_contains_key(origlogic,"@question")) and 
      ("result" not in logic_objects)):
    return "No question given."   
    #print("No question given.")
    #sys.exit(0)
  if "result" not in logic_objects:
    rawresult=call_prover(logic)
  elif logic_objects["result"]: 
    if options["prover_explain_flag"]:
      print("Answer found without proof search:")   
    return logic_objects["result"]  
  else:
    if options["prover_explain_flag"]:
      print("Answer found without proof search:")
    return "Unknown."  

  # - - - show the result - - - 

  if options["prover_nosolve_flag"]:
    return rawresult
  elif options["prover_rawresult_flag"]:
    return rawresult  
  elif rawresult and rawresult.startswith("Error"):
    return rawresult  
 
  niceresult=make_nlp_result(doc,rawresult,logic_objects,question_type,llm_mapping)
  return niceresult

# detect input strings, filenames and optional keys

def parse_cmd_line(helptext):  
  text=""  
  if len(sys.argv)<2: 
    print(helptext)
    sys.exit(0)
  axiomfiles=False  
  params=sys.argv[1:]
  elpos=0-1
  skippos=0
  for el in params:
    elpos+=1
    if skippos>0:
      skippos=skippos-1
      continue
    textpart="" # will be become the text from this element
    if el in ["-debug","--debug"]: 
      options["debug_print_flag"]=True
      options["prover_print_flag"]=True
    elif el in ["-showlogic","--showlogic"]: 
      options["prover_print_flag"]=True
    elif el in ["-nosolve","--nosolve"]: 
      options["prover_nosolve_flag"]=True      
      options["prover_rawresult_flag"]
    elif el in ["-postprocess","--postprocess"]: 
      options["prover_postprocess_flag"]=True  
    elif el in ["-rawresult","--rawresult"]: 
      options["prover_rawresult_flag"]=True  
    elif el in ["-explain","--explain"]: 
      options["prover_explain_flag"]=True   
    elif el in ["-logic","--logic"]: 
      options["show_logic_flag"]=True  
    elif el in ["-simple","--simple"]: 
      options["nocontext_flag"]=True
      options["noexceptions_flag"]=True      
      #noproptypes_flag"]=True
      options["noproptypes_flag"]=True
    elif el in ["-nocontext","--nocontext"]: 
      options["nocontext_flag"]=True   
    elif el in ["-noexceptions","--noexceptions"]: 
      options["noexceptions_flag"]=True
    elif el in ["-simpleproperties","--simpleproperties"]: 
      #noproptypes_flag"]=True
      options["noproptypes_flag"]=True
      options["noexceptions_flag"]=True           
    elif el in ["-prover","--prover"]: 
      options["show_prover_flag"]=True
    elif el in ["-usekb","--usekb"]: 
      options["usekb_flag"]=True  
    elif el in ["-forward","--forward"]: 
      options["forward_flag"]=True
    elif el in ["-backward","--backward"]: 
      options["backward_flag"]=True    
    elif el in ["-nokb","--nokb"]: 
      options["nokb_flag"]=True   
    elif el in ["-llm","--llm"]: 
      options["llm_flag"]=True   
    elif el in ["-amr","--amr"]: 
      options["amr_flag"]=True     
    elif el in ["-axioms","--axioms"]: 
      axiomfiles=[]
      fpos=1
      while elpos+fpos<len(params):
        if not params[elpos+fpos] or params[elpos+fpos].startswith("-"): break
        axiomfiles.append(params[elpos+fpos])
        fpos+=1
      skippos=fpos-1      
      options["prover_axiomfiles"]=axiomfiles
    elif el in ["-printlevel","--printlevel"]:  
      if elpos+1 >= len(params):
        print("-printlevel takes an integer parameter")
        sys.exit(0)  
      try:
        n=int(params[1+elpos])  
      except:
        print("-printlevel takes an integer parameter")
        sys.exit(0)
      if n<10:  
        print("-printlevel takes an integer parameter 10 or more")
        sys.exit(0)    
      options["prover_print"]=n
      skippos=1      
    elif el in ["-seconds","--seconds"]:  
      if elpos+1 >= len(params):
        print("-seconds takes an integer parameter")
        sys.exit(0)  
      try:
        n=int(params[1+elpos])  
      except:
        print("-seconds takes an integer parameter")
        sys.exit(0)
      if n<1:  
        print("-seconds takes an integer parameter 1 or more")
        sys.exit(0)    
      options["prover_seconds"]=n
      skippos=1     
    elif el in ["-strategy","--strategy"]:  
      if elpos+1 >= len(params):
        print("-strategy takes a file name as a parameter")
        sys.exit(0)         
      options["prover_strategy"]=params[1+elpos]
      skippos=1        
    elif el in ["help","-help","--help"]:  
      print(helptext)
      sys.exit(0)
    elif el and el[0]=="-": 
      show_error("Key "+el+" is not recognized.")
      print(helptext)
      sys.exit() 
    elif (len(el)<50 and 
          len(el.split("."))==2 and
          len(el.split(".")[1])>1 and
          len(el.split(" "))==1):
      # a filename      
      try:
        f=open(el,"r")
        textpart=f.read()
        f.close()
      except:
        show_error("Could not read from the file "+el)        
        sys.exit()      
    else:
      # normal text
      textpart=el
    # at the end of the loop: add this part to the text  
    if text and textpart: text=text+" "+textpart
    elif textpart: text=textpart  
  return (text,options)

def prepare_text(text):
  #print("orig text",text)
  if not text: return ""
  text=text.replace("%"," percent")
  # --- put whitespace in front of periods for variable. name ---
  newspln=[]
  spln=text.split(" ")
  for el in spln:
    if el and el[-1]=="." and variable_shaped_lemma(el[:-1]):
      newspln.append(el[:-1])
      newspln.append(".")
    else:
      newspln.append(el)  
  text=" ".join(newspln)

  # --- put missing commas in front of then in if-sentences 
  spln=text.split("\n")
  newspl=[]
  for line in spln:    
    splp=line.split(".")
    newsplp=[]
    for sentence in splp:
      pos=None
      if sentence.startswith("If "): pos=0
      if not pos: 
        pos=sentence.find(" If ")
        if pos<0: pos=sentence.find(" if ")
        if pos<0: pos=sentence.find(" IF ")
      commapos=None  
      if pos!=None:
        tpos=sentence.find(" then ",pos)
        if tpos:
          i=tpos
          while i>0:
            if sentence[i]==" ": 
              i=i-1              
            elif sentence[i].isalnum(): 
              commapos=i
              break
            else:
              break
           
      if commapos!=None:
        newsentence=sentence[:commapos+1]+","+sentence[commapos+1:]
      else:        
        newsentence=sentence
      newsplp.append(newsentence)

    sentres=".".join(newsplp)
    newspl.append(sentres)

  text="\n".join(newspl)
  return text


# =========== main caller ==========

if __name__ == "__main__":        
  main()  







