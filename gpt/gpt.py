#!/usr/bin/env python3
#
# Experimenting with the gpt api
# Run without arguments to get instructions.
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
import http.client

# ==== import other source files ====


# ======= llm configuration ===

secrets_file="secrets.js"

gpt2="davinci-002"         # text-davinci-002 code-davinci-002 babbage-002 
gpt3="gpt-3.5-turbo-0125"  # 
gpt4="gpt-4-0125-preview"  # gpt-4  gpt-4-32k 
gpt4="gpt-4o-2024-05-13"
gpt3_instruct="gpt-3.5-turbo-instruct-0914"  # "gpt-3.5-turbo-instruct" 

temperature=0
seed=1234
max_tokens=2000

# ======= other configuration globals ===

gpt_model=gpt4 # default

debug=False # set to True to get a printout of data, call and result

helptext="""Usage example: ./gpt.py 4 -s logifyprompt3.txt "John is a nice person."
Use 4 for gpt4, 3 for gpt3, 2 for gpt and instruct for gpt3 instruct version.
You may skip the -s key along with the (system)prompt file parameter.

NB! you must have a file secrets.js with the content {"gpt_key": keystring} in the folder."""

# ========= code ===================

def main():
  if len(sys.argv)<2:
    print(helptext)
    return
  gptversion=gpt3
  pfile=""
  texts=[]  
  nextprompt=False
  max_tokens=None
  # parse command line
  for el in sys.argv[1:]:
    if el in ["-sys","-s","--sys","--s"]:
      nextprompt=True
    else:
      if nextprompt:
        pfile=el
        nextprompt=False
      else:  
        if el=="3" or el=="3.5":
          gptversion=gpt3
        elif el=="2":
          gptversion=gpt2  
        elif el=="4":
          gptversion=gpt4  
        elif el=="instruct":
          gptversion=gpt3_instruct
        elif el.strip().isnumeric():
          max_tokens=int(el.strip())
        elif len(el)<20 and " " not in el:
          try:
            f=open(el, "r")
            onetext=f.read().strip()
            f.close()
            texts.append(onetext)
          except:
            show_error("could not read prompt file "+el)  
        else:
          texts.append(el)  
  # make a prompt         
  prompt=" ".join(texts).strip()    
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
  debug_print("gpt:",gptversion)
  debug_print("sysprompt:",sysprompt)
  debug_print("prompt:",prompt)
  # actual call
  result=call_gpt(gptversion,prompt,sysprompt,max_tokens)
  print("result:",result)
  

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
       "logprobs": False,
       "temperature": temperature
    }
  if max_tokens:
    call["max_tokens"]=max_tokens

  debug_print("gpt call",call)
  calltxt=json.dumps(call) 
  debug_print("gpt call:",calltxt)

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
    show_error("gpt responded with error "+str(response.status)+" "+str(response.reason)+message)
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
  debug_print("gpt response:",data)  
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

def debug_print(a,b):  
  if debug:
    print(a,b)

def show_error(a):
  print("Error:",a)
  exit(0)  

if __name__ == "__main__":
  main()

# =========== the end ==========
