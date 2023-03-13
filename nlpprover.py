# Prover calling and prover result conversion parts of nlpsolver
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
import pprint
import subprocess
import tempfile
import os
#import json

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
import nlpglobals

# making a nice nlp answer from json answer is in nlpanswer.py
from nlpanswer import *

# small utilities are in nlputils.py
from nlputils import *

# === calling the prover ===
 
def call_prover(logic):   
  #debug_print("solve logic",logic)
  #js=json.dumps(question,indent=2)
  #print("js:",js)  
  #pp = pprint.pformat(logic,width=80,indent=2,sort_dicts=False)   
  #instr=pp.replace("'","\"")
  instr=clause_list_to_json(logic)
  #debug_print("ppnice",ppnice)
  if (options["prover_print_flag"] or options["show_prover_flag"]) and not options["prover_nosolve_flag"]:
    print("\n=== prover input: === \n")
    print(instr)
  if options["prover_nosolve_flag"]:
    return(instr)    
  try:  
    infile,infilename=tempfile.mkstemp() 
  except:
    return("Error: failed to make a temporary file to write input to. ")  
  #print("infilename",infilename) 
  try:
    #infile=open(nlpglobals.prover_infile,"w")    
    #infile=open(infilename,"w")
    os.write(infile,str.encode(instr))
    os.close(infile)
    #infile.close()
  except KeyboardInterrupt:
    raise  
  except:
    os.remove(infilename)
    return("Error: failed to write prover infile "+infilename)     
  path=nlpglobals.prover_fname
  #decodedd=data.decode('ascii')
  #print("capi called with data",decodedd)
  params=[path]
  if not options["nokb_flag"]: 
    params=params+["-usekb",memkb_name]
  if options["prover_axiomfiles"]==False:
    params.append(nlpglobals.prover_axiomfile)
  else:
    for el in options["prover_axiomfiles"]:
      params.append(el)
  if options["prover_print"]:
    params=params+["-print",str(options["prover_print"])]
  if options["prover_strategy"]:
    params=params+["-strategy",options["prover_strategy"]]
  if options["prover_seconds"]:
    params=params+["-seconds",str(options["prover_seconds"])]    
  params.append(infilename)
  if options["usekb_flag"]: params=params+nlpglobals.usekb_prover_params
  else: params=params+nlpglobals.prover_params        
  if options["prover_print_flag"] or options["show_prover_flag"]:
    print("\n=== prover params: === \n\n"," ".join(params))
  try:  
    calc=subprocess.Popen(params, stdout=subprocess.PIPE).communicate()[0]
  except KeyboardInterrupt:
    raise  
  except:
    return "Error: prover gk is not available or crashed: check nlpgobals.py for gk path."  
  sres=calc.decode('ascii') 
  os.remove(infilename)
  if options["prover_print_flag"] or options["show_prover_flag"]:  
    print("\n=== prover output: === \n\n",sres)
    print("\n=== end of prover output === \n\n") 
  return sres


def get_relatedness(ctxt,lemma1,lemma2):   
  #debug_print("get_relatedness for lemma1, lemma2",[lemma1,lemma2])  
  #return 0
  key=lemma1+"#"+lemma2
  #debug_print("key",key)
  if "relatedness_cache" in ctxt and key in ctxt["relatedness_cache"]:
    #debug_print("key,val",key,ctxt["relatedness_cache"][key])
    #debug_print("get_relatedness gave from cache",ctxt["relatedness_cache"][key]) 
    return ctxt["relatedness_cache"][key]
  path=nlpglobals.prover_fname
  task="path,"+str(lemma1)+","+str(lemma2)
  params=[path,"-usekb","-task",task]
  res=0
  try:  
    calc=subprocess.Popen(params, stdout=subprocess.PIPE).communicate()[0]
  except KeyboardInterrupt:
    raise  
  except:
    #return "Error: prover gk is not available or crashed: check nlpgobals.py for gk path."  
    return 0    
  try:  
    sres=calc.decode('ascii') 
    parts=sres.split(" ")
    res=float(parts[0].strip())  
  except:
    #debug_print("err")
    res=0  
  if res==0 and """{"error":""" in sres:
    #debug_print("get_relatedness co-occurrence calculation gave",sres)
    None
  if not ("relatedness_cache" in ctxt): ctxt["relatedness_cache"]={} 
  ctxt["relatedness_cache"][key]=res
  #if options["prover_print_flag"]:  
  #  print("\n=== prover output: === \n\n",sres)
  #  print("\n=== end of prover output === \n\n") 
  #debug_print("get_relatedness gave",res) 
  return res


def is_subclass(ctxt,lemma1,lemma2):   
  #debug_print("is_subclass for lemma1, lemma2",[lemma1,lemma2])  
  #return 0
  key=lemma1+"#"+lemma2
  #debug_print("key",key)
  if "subclass_cache" in ctxt and key in ctxt["subclass_cache"]:
    #debug_print("key,val",key,ctxt["subclass_cache"][key])
    #debug_print("get_relatedness gave from cache",ctxt["subclass_cache"][key]) 
    return ctxt["subclass_cache"][key]
  path=nlpglobals.prover_fname
  task="taxcompare,"+str(lemma1)+","+str(lemma2)
  params=[path,"-usekb","-task",task]
  res=0
  try:  
    calc=subprocess.Popen(params, stdout=subprocess.PIPE).communicate()[0]
  except KeyboardInterrupt:
    raise  
  except:
    #return "Error: prover gk is not available or crashed: check nlpgobals.py for gk path."  
    return 0    
  try:  
    sres=calc.decode('ascii') 
    searchstr=lemma1+" is more general than "+lemma2
    if searchstr in sres:
      res=True
    else:
      res=False
  except:
    #debug_print("err")
    res=0  
  if res==0 and """{"error":""" in sres:
    None
    #debug_print("is_subclass calculation gave",sres)
  if not ("subclass_cache" in ctxt): ctxt["subclass_cache"]={} 
  ctxt["subclass_cache"][key]=res
  #if options["prover_print_flag"]:  
  #  print("\n=== prover output: === \n\n",sres)
  #  print("\n=== end of prover output === \n\n") 
  #debug_print("is_subclass gave",res) 
  return res




# =========== the end ==========