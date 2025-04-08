#!/usr/bin/env python3

# Collecting gpt results for tests of the nlpsolver system.
#
# Run the program and it will run all the tests
# here and return the results.
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

import time
import sys
import json
import http.client
#import anthropic

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
test_files=["llm_tests_core1.py"]
test_files=["llm_tests_core1_part.py"]
test_files=["llm_tests_allen.py"]
test_files=["tests_wiki1.py"]
test_files=["tests_wikipedia.py"]

test_files=["tests_hans.py"]
#test_files=["llm_core_test.py"]
#test_files=["try.py"]
test_files=["llm_core_test.py"]

show_tests=True # set to False to suppress printing of all tests during work
show_compact=True # if show_tests is False, set to True to get 0/1 char for each test

debug=False

#result_file_suffix="_o3_mini_parseresults.txt"
result_file_suffix="_prompt6_parseresults.txt"

linestart="|!!|"
separator=" |$$| "

sleepseconds=2

use_llm="claude"
#use_llm="gpt"

# =======specific llm configuration ===


secrets_file="secrets.js"
claude_secrets_file="claude_secrets.js"

gpt2="davinci-002"         # text-davinci-002 code-davinci-002 babbage-002 
gpt3="gpt-3.5-turbo-0125"  # 
#gpt4="gpt-4-0125-preview"  # gpt-4  gpt-4-32k 
gpt3_instruct="gpt-3.5-turbo-instruct-0914"  # "gpt-3.5-turbo-instruct" 
gpt4="gpt-4o-2024-05-13"
gpt4="o3-mini-2025-01-31"

temperature=0
seed=1234
max_tokens=20000

gptversion=gpt4
claudeversion="claude-3-7-sonnet-20250219"

syspromptfile="gpt/simplifyprompt1.txt"
syspromptfile="logifyprompt6.txt"


# ======== testing program ======


def main():
  global test_files
  options={}
  alltests=[]
  for testfile in test_files:
    try:
      f=open(testfile,"r")
      s=f.read()      
    except:
      print("Could not read test file",testfile)  
      return
    f.close()
    try:  
      tests=eval(s)
    except BaseException as err:
      print("Error parsing test file",testfile)
      print()
      raise(err)
      return
    alltests.append([testfile,tests])  
  allresults=[] 
  for test in alltests:  
    print("\n=== running test "+test[0]+" ===\n")
    results=single_run_tests(test[0],test[1],0,len(test[1]),options)
    allresults.append(results)

  if len(alltests)>1:
    sum_realtestcount=0
    sum_lenokresults=0
    sum_failedresults=[]
    for result in allresults:
      sum_realtestcount+=result[0]
      sum_lenokresults+=result[1]
      sum_failedresults+=result[2]
    print("\n=== Summary for all tests ===\n")
    print("Tests run:",sum_realtestcount)
    print("OK tests:",sum_lenokresults)
    print("Failed tests:",len(sum_failedresults))
    if len(sum_failedresults)>0:
      print()
      print("Tests which failed:")
      for result in sum_failedresults:
        print("Input:",result[0][0])
        print("Expected:",result[0][1])
        print("Received:",result[1])


def single_run_tests(testfile, tests, lower=0, upper=0, options={}):
  okresults=[]
  failedresults=[]
  testcount=0-1
  realtestcount=0
  print("Starting to run",len(tests),"tests")
  options["use_cache_flag"]=False
  if show_tests: print()
  if upper==0: 
    upper=len(tests)  
  start_time = time.time() 
  tmp=testfile.split(".")  
  outfilename=tmp[0]+"_"+use_llm+result_file_suffix
  outfile=open(outfilename,"w")
  for test in tests:    
    testcount+=1
    #if testcount>3: break
    if testcount<lower: continue
    if testcount>=upper: break
    #if testcount>100: break
    realtestcount+=1
    if show_tests: print("Input:",test[0])
    prompt=test[0]
    time.sleep(sleepseconds)
    try:
      if use_llm=="gpt":
        result=ask_gpt(syspromptfile,prompt)
      elif use_llm=="claude":
        result=ask_claude(syspromptfile,prompt)
      else:
        show_error("use_llm conf value not understood")   
    except KeyboardInterrupt:
      sys.exit(0)  
    except:
      result="Software error."  
 
    if show_tests: print("Received:",result) 
    if show_tests: print()   
    outtext=linestart+prompt+separator+str(test[1])+separator+str(result)+"\n"
    outfile.write(outtext)
    outfile.flush()
    #print("result:",result)
    
    if True:
      okresults.append([test,result])
      if not show_tests and show_compact: print("1",end="",flush=True)
    else:
      failedresults.append([test,result])
      if not show_tests and show_compact: print("0",end="",flush=True)
  outfile.close()  
  if not show_tests and show_compact: print()
  print("Testing finished in "+str(round(time.time() - start_time,3))+" seconds")
  print("Tests run:",realtestcount)
  print("OK tests:",len(okresults))
  print("Failed tests:",len(failedresults))
  if len(failedresults)>0:
    print()
    print("Tests which failed:")
    for result in failedresults:
      print("Input:",result[0][0])
      print("Expected:",result[0][1])
      print("Received:",result[1])
  results=[realtestcount,len(okresults),failedresults]
  return results


def ask_gpt(syspromptfile,prompt): 
  pfile=syspromptfile          
  # make a sysprompt
  sysprompt=""    
  if pfile:
    try:
      f=open(pfile, "r")
      sysprompt=f.read().strip()
      f.close()
    except:
      show_error("could not read sysprompt file "+pfile)   
  if not prompt:
    show_error("no prompt given")    
  #debug_print("gpt:",gptversion)
  #debug_print("sysprompt:",sysprompt)
  debug_print("prompt:",prompt)
  # actual call
  #print("to call:",gptversion,prompt,sysprompt,max_tokens)
  result=call_gpt(gptversion,prompt,sysprompt,max_tokens)  
  if not result:
    # try again with more tokens
    print("Repeating gpt call with 2*max_tokens due to empty result with max_tokens",max_tokens)
    result=call_gpt(gptversion,prompt,sysprompt,max_tokens*2) 
  return result


def ask_claude(syspromptfile,prompt): 
  pfile=syspromptfile          
  # make a sysprompt
  sysprompt=""    
  if pfile:
    try:
      f=open(pfile, "r")
      sysprompt=f.read().strip()
      f.close()
    except:
      show_error("could not read sysprompt file "+pfile)   
  if not prompt:
    show_error("no prompt given")    
  #debug_print("gpt:",gptversion)
  #debug_print("sysprompt:",sysprompt)
  debug_print("prompt:",prompt)
  # actual call
  #print("to call:",gptversion,prompt,sysprompt,max_tokens)
  result=call_claude(claudeversion,prompt,sysprompt,max_tokens)  
  return result  

# ========= llm connection =========


def call_gpt(gptversion,sentences,sysprompt,max_tokens):
  try:
    sf=open(secrets_file,"r")
    txt=sf.read()
  except:
    show_error("Could not read file containing gpt api key: "+str(secrets_file))
  try:  
    data=json.loads(txt)
  except:
    show_error("Could not parse json text containing gpt api key in: "+str(secrets_file))  
  if "gpt_key" not in data or not (data["gpt_key"]):
    show_error("Could not find gpt api key in: "+str(secrets_file))
  else:    
    key=data["gpt_key"]
  # key found ok    
  #sentences="A fork is a tool you use in the kitchen or when you eat."
  messages=[]
  if sysprompt:
    message1={"role": "system", "content": sysprompt}
    messages.append(message1)   
  message2={"role": "user", "content": sentences}
  messages.append(message2)  

  if gptversion in [gpt3_instruct, gpt2]:
    prompt=""
    if sysprompt: 
      prompt+=sysprompt+"\nInput sentences: "+sentences
    if sentences: 
      prompt+=sentences
    baseurl="/v1/completions"  
    call={
     "model": gptversion,
     "prompt": prompt,
     #"seed": seed,
     #"logprobs": True,
     "temperature": temperature
    }
  else:  
    baseurl="/v1/chat/completions"
    call={
       "model": gptversion,
       "messages": messages,
       "seed": seed,
       #"logprobs": True,
       "logprobs": False
    }
  if max_tokens:
    if "o3" in gptversion:
      call["max_completion_tokens"]=max_tokens
    else:  
      call["max_tokens"]=max_tokens
  if "o3" in gptversion:
    call["reasoning_effort"]="medium" # low, medium, high
    #call["response_format"]={ "type": "json_object" }
  else:
    call["temperature"]=temperature

  debug_print("\ngpt call",call)
  calltxt=json.dumps(call) 
  #debug_print("gpt call:",calltxt)

  trycount=0
  while True:
    host = "api.openai.com"
    conn = http.client.HTTPSConnection(host)
    conn.request("POST", baseurl, calltxt,
                headers={
      "Host": host, "Content-Type": "application/json", "Authorization": "Bearer "+key 
    })   

    response = conn.getresponse()
    if response.status!=200 or response.reason!="OK":
      try:
        data=json.loads(response.read())    
        if "error" in data and "message" in data["error"]:
          message=": "+data["error"]["message"]
      except:
        message=""      
      print("api failure, trying again: ",str(response.status),str(response.reason)+message)  
      trycount+=1
      if conn: conn.close()
      time.sleep(sleepseconds*(trycount+1))
    else:
      break  
    if trycount>3:
      show_error("after several tries gpt responded with error "+str(response.status)+" "+str(response.reason)+message)
  rawdata = response.read()
  try:
    data=json.loads(rawdata)
  except KeyboardInterrupt:
    raise  
  except:
    show_error("gpt response is not a correct json: "+  str(rawdata))
  if "choices" not in data:
    show_error("gpt response does not contain choices")

  # OK answer received  
  debug_print("\ngpt response:",data)  
  part=data["choices"]  
  res=""
  for el in part:
    if "message" in el:
      msg=el["message"]
      if "content" in msg:
        tmp=msg["content"]
        if len(tmp)>2 and tmp[0] in ["\"","'"] and tmp[-1] in ["\"","'"]:
          tmp=tmp[1:-1]
        tmp2=tmp.split("\n")
        if len(tmp2)>1:
          tmp3=""
          for line in tmp2:
            if len(line)>3 and (line[0].isnumeric() or line[0] in ["*","-"]) and line[1] in [".",":"," "]:
              tmp3+=line[2:]+" "
            else:
              tmp3+=line+" "  
          tmp=tmp3    
        res+=tmp
    elif "text" in el:
      if res: res+="\n"
      res+=el["text"].strip()      
              
  conn.close()
  #debug_print("res",res)  
  return res



def call_claude(version,sentences,sysprompt,max_tokens):
  try:
    sf=open(claude_secrets_file,"r")
    txt=sf.read()
  except:
    show_error("Could not read file containing claude api key: "+str(secrets_file))
  try:  
    data=json.loads(txt)
  except:
    show_error("Could not parse json text containing claude api key in: "+str(secrets_file))  
  if "claude_key" not in data or not (data["claude_key"]):
    show_error("Could not find claude api key in: "+str(secrets_file))
  else:    
    key=data["claude_key"]
  # key found ok    
  #sentences="A fork is a tool you use in the kitchen or when you eat."
  messages=[]  
  message={"role": "user", "content": sentences}
  messages.append(message)  
 
  baseurl="/v1/messages"
  call={
       "model": version,
       "messages": messages,
       #"seed": seed,
       #"logprobs": True,
       #"logprobs": False,
       "temperature": temperature
    }
  if sysprompt:
    call["system"]=[{"type":"text", "text":sysprompt, "cache_control": {"type": "ephemeral"}}]
  if max_tokens:
    call["max_tokens"]=max_tokens

  debug_print("claude call",call)
  calltxt=json.dumps(call) 
  debug_print("claude calltxt:",calltxt)

  trycount=0
  while True:
    host = "api.anthropic.com"
    conn = http.client.HTTPSConnection(host)
    conn.request("POST", baseurl, calltxt,
                headers={
      "content-Type": "application/json", 
      "anthropic-version": "2023-06-01",
      "x-api-key": key
    })    
    response = conn.getresponse()
    if response.status!=200 or response.reason!="OK":
      try:
        data=json.loads(response.read())    
        if "error" in data and "message" in data["error"]:
          message=": "+data["error"]["message"]
      except:
        message=""      
      print("api failure, trying again: ",str(response.status),str(response.reason)+message)  
      trycount+=1
      if conn: conn.close()
      time.sleep(sleepseconds*(trycount+1))
    else:
      break  
    if trycount>3:
      show_error("after several tries claude responded with error "+str(response.status)+" "+str(response.reason)+message)
  rawdata = response.read()
  try:
    data=json.loads(rawdata)
  except KeyboardInterrupt:
    raise  
  except:
    show_error("claude response is not a correct json: "+  str(rawdata))
  if "content" not in data:
    show_error("claude response does not contain content:"+ str(rawdata))

  # OK answer received  
  debug_print("claude response:",data)  
  part=data["content"]  
  res=""
  for el in part:
    if "text" in el:    
      res+=el["text"].strip()      
              
  conn.close()
  #debug_print("res",res)  
  return res

def debug_print(a,b):  
  if debug:
    print(a,b)

def show_error(a):
  print("Error:",a)
  sys.exit(0)  



# ========= run the program ======

if __name__ == "__main__":        
  main()  


# ========= the end =============
