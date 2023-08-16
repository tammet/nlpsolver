# The llm connections parts of nlpsolver
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
import http.client

# ==== import other source files ====

# configuration and other globals are in nlpglobals.py
from nlpglobals import *

# small utilities are in nlputils.py
from nlputils import *

# proper logic part is in nlpproperlogic
#from nlpproperlogic import *

# question special handling is in nlpquestion
from nlpquestion import *

# logic simplification is in nlpsimplify
#from nlpsimplify import *

# uncertainty analysis and encoding is in nlpuncertain
#from nlpuncertain import *

#from nlpanswer import *

#from nlpsolver import server_parse

# ======= llm configuration ===


gpt_model="gpt-4"
gpt_prompt="""Simplify, maximally shorten and split the sentence after colon to shortest possible separate subsentences, to make it understandable for children. 
Replace pronouns like 'they','it','he' etc in the result with nouns and proper nouns present in the result, like 'Birds can fly. Birds have feathers' instead of 
'Birds can fly. They have feathers.'. Prepend the character star * to concrete objects and the character plus + to general nouns, 
like 'Birds+ can fly. A stork* ate a frog*.':  """

#gpt_model="gpt-3.5-turbo"
gpt_prompt="""Simplify, maximally shorten and split the sentence after colon to shortest possible separate subsentences, to make it understandable for children. 
Replace pronouns like 'they','it','he','she' in the result with nouns and proper nouns present in the result, 
like 'Birds can fly. Birds have feathers' instead of 
'Birds can fly. They have feathers':  """

gpt_prompt="""Simplify, maximally shorten and split the sentence after colon to shortest possible separate subsentences, to make it understandable for children. 
Replace pronouns like 'they','it','he','she' in the result with nouns and proper nouns present in the result. For example,
instead of 'Birds can fly. They have feathers.' say 'Birds can fly. Birds have feathers.' : """

temperature=0
min_simplification_length = 6

# ======= globals used and changed during work ===


#constant_nr=0 # new constants created add a numeric suffic, incremented
#definition_nr=0 # new definitions created add a numeric suffic, incremented

# ========= llm connection =========

def llm_simplify(text):
  debug_print("=== llm simplification ===")  
  parsed = server_parse(text)
  if not parsed or "doc" not in parsed:
    show_error("ud parsing failed")
    sys.exit(0)
  doc=parsed["doc"]  
  sentlist=[]
  for sentence in doc: 
    sentencetext=doc_to_original_sentence(sentence) 
    if is_question_sentence(sentence):
      sentlist.append([sentencetext,sentencetext])
      debug_print("not simplified",sentencetext)
    elif len(sentence)<min_simplification_length:
      sentlist.append([sentencetext,sentencetext])
      debug_print("not simplified",sentencetext)  
    else:         
      debug_print("original sentence",sentencetext)
      newtext=call_gpt(sentencetext,gpt_prompt)
      sentlist.append([sentencetext,newtext])
      debug_print("simplified sentence",newtext)  
  res=""
  for el in sentlist:
    res+=el[1]+" "
  debug_print("final simplification result",res)  
  return [res,sentlist]


def call_gpt(sentences,prompt):
  try:
    sf=open(secrets_file,"r")
    txt=sf.read()
  except:
    return "Could not read file containing gpt api key: "+str(secrets_file)
  try:  
    data=json.loads(txt)
  except:
    return "Could not parse json text containing gpt api key in: "+str(secrets_file)  
  if "gpt_key" not in data or not (data["gpt_key"]):
    return "Could not find gpt api key in: "+str(secrets_file)
  else:    
    key=data["gpt_key"]
  # key found ok    
  #sentences="A fork is a tool you use in the kitchen or when you eat."
  #message1={"role": "system", "content": "You are a helpful assistant. Answer as concisely as possible."}
  message2={"role": "user", "content": prompt+"""'"""+sentences+"""'"""}
  call={
     "model": gpt_model,
     "messages": [message2], #[message1,message2],
     "temperature": temperature
  }
  debug_print("gpt call",call)
  calltxt=json.dumps(call) 
  host = "api.openai.com"
  conn = http.client.HTTPSConnection(host)
  conn.request("POST", "/v1/chat/completions", calltxt,
               headers={
    "Host": host, "Content-Type": "application/json", "Authorization": "Bearer "+key 
  })
  response = conn.getresponse()
  if response.status!=200 or response.reason!="OK":
    show_error("gpt responded with error "+str(response.status)+" "+str(response.reason))
    sys.exit(0)
  rawdata = response.read()
  try:
    data=json.loads(rawdata)
  except KeyboardInterrupt:
    raise  
  except:
    show_error("gpt response is not a correct json: "+  str(rawdata))
    sys.exit(0)
  if "choices" not in data:
    show_error("gpt response does not contain choices")
    sys.exit(0)
  debug_print("gpt response",data)  
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
  conn.close()
  #debug_print("res",res)  
  return res
  
  


# =========== the end ==========
