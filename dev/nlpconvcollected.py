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

test_files=["tests_core.py","tests_hans.py","tests_allen.py"]
#test_files=["tests_allen.py"]
#test_files=["tests_dev.py"]

#test_files=["problems/babi/ajut.txt"]

#test_files=["problems/babi/ajut2.py"]

test_files=["ajut.py"]
test_files=["tests_hans.py","tests_allen.py"]
test_files=["tests_hans.py"]
test_files=["llm_tests_core1.py"]
test_files=["tests_hans.py"]
#test_files=["tmp_tst.py"]
test_files=["llm_tests_core1_resultsa.py"]
test_files=["tests_wiki1_results.txt"]

show_tests=False # set to False to suppress printing of all tests during work
show_compact=True # if show_tests is False, set to True to get 0/1 char for each test

debug=False

result_file_suffix="_results.txt"

converted_result_file_suffix="_results.py"

#test_files=["llm_tests_core1_results.txt"]
#converted_file_name="llm_tests_core1_results_converted.py"

#test_files=["llm_tests_allen_results.txt"]
#converted_file_name="llm_tests_allen_results_converted.py"

#test_files=["llm_tests_hans_results.txt"]
#converted_file_name="llm_tests_hans_results_converted.py"

#test_files=["llm_tests_hans_resultsa.txt"]
#converted_file_name="llm_tests_hans_resultsa_converted.py"

test_files=["tests_wiki1_results.txt"]
converted_file_name="tests_wiki1_results_converted.txt"

linestart="|!!|"
separator=" |$$| "

# ======== testing program ======


def main():
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
      try:
        logic=json.loads(parts[2])
      except:
        #print("enderr",parts[2]) 
        enderrcount+=1 
        newlogicstr=parts[2].strip()
        if newlogicstr.startswith("```json") and newlogicstr[-3:]=="```":
          newlogicstr=newlogicstr[7:-3]
        elif ("] [\"question\"" in newlogicstr) and newlogicstr.startswith("[\"and\","):
          newlogicstr=newlogicstr.replace("] [\"question\"", "], [\"question\"")
          newlogicstr="[\"and\","+newlogicstr+"]"
          print("**** ",newlogicstr)
        else:        
          newlogicstr=newlogicstr=newlogicstr+"]"
        try:
          logic=json.loads(newlogicstr)
        except:         
          newlogicstr=newlogicstr=newlogicstr+"]"
          try:
            logic=json.loads(newlogicstr)
          except:  
            print("harderr",parts[2]) 
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



# ========= run the program ======

if __name__ == "__main__":        
  main()  


# ========= the end =============
