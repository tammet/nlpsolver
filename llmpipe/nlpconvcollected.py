#!/usr/bin/env python3

# Collecting gpt results for tests of the nlpsolver system.
#
# Run the program and it will run all the tests
# here and return the results.
#
#-----------------------------------------------------------------
# Copyright 2024 Tanel Tammet (tanel.tammet@gmail.com)
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

import time
import sys
import json
import http.client


# ======== configuration ======


show_tests=False # set to False to suppress printing of all tests during work
show_compact=True # if show_tests is False, set to True to get 0/1 char for each test

debug=False

# test_files=["tests_hans_claude_parseresults.txt"]
# converted_file_name="tests_hans_claude_parseresults_converted.py"

#test_files=["tests_hans_gpt_o3_mini_parseresults.txt"]
#converted_file_name="tests_hans_gpt_o3_mini_parseresults_converted.txt"

#test_files=["tests_hans_claude_prompt6_parseresults.txt"]
#converted_file_name="tests_hans_claude_prompt6_parseresults_converted.txt"

test_files=["llm_core_test_claude_prompt6_parseresults.txt"]
converted_file_name="llm_core_test_claude_prompt6_parseresults_converted.txt"



linestart="|!!|"
separator=" |$$| "

# ======== testing program ======


def main():
  """
  print(fix_internal('[as"]]"baa]'))
  print(fix_internal("[xasbaa]"))
  print(fix_internal("[as[[d]]baa]"))
  print(fix_internal("[as]br]a]"))
  print(fix_internal("[asbaa]]"))
  print(fix_internal("[asbaa]]]"))
  print(fix_internal("[asbaa]]] "))
  print(fix_internal("[asbaa] "))
  """
 
  global test_files
  options={}
  alltests=[]
  for testfile in test_files:
    #split=testfile.split(".")
    #result_file_name=split[0]+result_file_suffix
    #converted_file_name=split[0]+converted_result_file_suffix
    result_file_name=testfile
    try:
      f=open(result_file_name,"r")
      s=f.read()      
    except:
      print("Could not read test file",result_file_name)  
      return
    f.close()
    print(result_file_name, converted_file_name)
    split=s.split(linestart)
    enderrcount=0
    harderrcount=0
    fullcount=0
    converted=[]
    for el in split:
      el=el.strip()
      if not el: continue
      fullcount+=1
      parts=el.split(separator)
      if len(parts)!=3: 
        print("error, weird line",parts)
        sys.exit(0)
      #print(parts)
      expected=None
      if parts[1]=='True': expected=True
      elif parts[1]=='False': expected=False
      s=parts[2]
      if "null" in s:
        s=s.replace(", null]","]").replace(",null]","]")
      try:
        logic=json.loads(s)
      except:
        opennr=logic.count("[")
        closenr=logic.count("]")
        #print("enderr",parts[2]) 
        enderrcount+=1 
        newlogicstr=s.strip()       
        if newlogicstr.startswith("```json") and newlogicstr[-3:]=="```":
          newlogicstr=newlogicstr[7:-3]
        elif ("] [\"question\"" in newlogicstr) and newlogicstr.startswith("[\"and\","):
          newlogicstr=newlogicstr.replace("] [\"question\"", "], [\"question\"")
          newlogicstr="[\"and\","+newlogicstr+"]"
          #print("**** ",newlogicstr)
        elif closenr<opennr:        
          newlogicstr=newlogicstr=newlogicstr+"]"    
        try:
          logic=json.loads(newlogicstr)
        except:         
          opennr=newlogicstr.count("[")
          closenr=newlogicstr.count("]")
          if closenr<opennr:
            extras="]"*(opennr-closenr)
            newlogicstr=newlogicstr+extras
          elif closenr>opennr and newlogicstr[-1]=="]":
            newlogicstr=newlogicstr[:-1]  
          try:
            logic=json.loads(newlogicstr)
          except:  
            #print("newlogicstr",newlogicstr)
            newlogicstr=fix_internal(newlogicstr)
            opennr=newlogicstr.count("[")
            closenr=newlogicstr.count("]")
            if closenr<opennr:
              extras="]"*(opennr-closenr)
              newlogicstr=newlogicstr+extras
              #print("fixed      ",newlogicstr)
            try:
               logic=json.loads(newlogicstr)               
            except:  
              if ']"]' in newlogicstr:
                newlogicstr=newlogicstr.replace(']"]',']]')
                newlogicstr=fix_internal(newlogicstr)
                opennr=newlogicstr.count("[")
                closenr=newlogicstr.count("]")
                if closenr<opennr:
                  extras="]"*(opennr-closenr)
                  newlogicstr=newlogicstr+extras
              try:
               logic=json.loads(newlogicstr)               
              except:  
                print("harderr",parts) 
                #print("harderr2",newlogicstr)
                #print("parts[2]",parts[2])
                #print("el",el)
                harderrcount+=1
                enderrcount-=1             
                continue
          #sys.exit(0)
      newitem=[parts[0].strip(),expected,logic]
      converted.append(newitem)
    print("fullcount",fullcount,"enderrcount",enderrcount,"harderrcount",harderrcount)    
    try:
      f=open(converted_file_name,"w")            
    except:
      print("Could not open output file",converted_file_name)  
      return
    f.write("[\n")
    count=0
    for el in converted:
      count+=1
      #print("el",el)
      #print("[\""+el[0]+"\""+","+str(el[1])+","+str(json.dumps(el[2]))+"]",end="")
      s="[\"\"\""+el[0]+"\"\"\""+","+str(el[1])+","+str(json.dumps(el[2]))+"]"
      f.write(s)
      if count<len(converted):
        #print(",")
        f.write(",\n")
      else:
        #print()  
        f.write("\n")
    f.write("]\n")
    f.close()

def fix_internal(s):
  inquotes=False
  opens=0
  for i in range(0,len(s)):
    c=s[i]
    if c=='"' and inquotes: 
      inquotes=False
      continue
    elif c=='"' and not inquotes: 
      inquotes=True
      continue
    if inquotes: continue
    if c=="[": 
      opens=opens+1
    elif c=="]": 
      opens=opens-1
      if opens==0:
        if i<len(s)-1 and s[i+1:].strip():
          ns=s[:i]+s[i+1:]
          ns=fix_internal(ns)
          return ns
  return s
      






# ========= run the program ======

if __name__ == "__main__":        
  main()  


# ========= the end =============
