#!/usr/bin/env python3

# Separately run nplserver is used by the nlpsolver.
#
# This server speeds up nlp parsing by setting up the stanza parser pipeline
# and taking urlencoded queries like
# http://localhost:8080/Barack%20Obama%20was%20born%20in%20Hawaii.
# answering them with the stanza parser results represented
# as a json structure
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

# ======= imports =======

import sys
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import unquote

try: 
  import stanza # the only non-standard library dependency
except:
  print("""nlpserver needs stanza: to install stanza, do
pip install stanza
python -c 'import stanza; stanza.download("en")'""")
  sys.exit(0)

# see https://stanfordnlp.github.io/stanza/
# to install stanza, do 
#  pip install stanza
#  python -c 'import stanza; stanza.download("en")'

# ======= configuration globals ======

host_name="localhost"
server_port=8080
gk_path="./gk"
logfile="/dev/null" # here server logs the requests
axiomfiles=None # "wnet_10k.js cnet_50k.js quasi_50k.js" # set to None to read no axioms

# ====== globals used during work ========

nlp=None # at startup nlp is assigned the stanza pipeline

count=0
import time

# === request processing ===

class MyServer(BaseHTTPRequestHandler):
  def do_GET(self):
    #global count
    text=unquote(self.path) # urldecode 
    #print("count start",count)
    if text: text=text[1:]  # remove initial slash
    result=parse_text(text) # call stanza parser
    #print("count end",count)
    #for i in range(0,10):
    #  print("i",i)
    #  time.sleep(1)
    #print("count end",count)
    #count+=1
    self.send_response(200)
    self.send_header("Content-type", "text/json")
    self.end_headers()    
    self.wfile.write(bytes("%s\n" % result, "utf-8"))


def parse_text(text):
  global nlp
  #global count
  #print("start parse_text count",count)
  doc=nlp(text)
  docpy = doc.to_dict()
  entities=[]
  for el in doc.entities:
    entities.append(el.to_dict())
  wrapper={"doc": docpy, "entities": entities}    
  resjson=json.dumps(wrapper)
  #print("end parse_text count",count)
  #count+=1
  return resjson

# ====== starting ======

if __name__ == "__main__":   
  print("Starting to build the stanza pipeline.")     
  # no download_method for stanza 1.3
  # nlp = stanza.Pipeline(lang='en', processors='tokenize,ner,pos,lemma,depparse', download_method=stanza.DownloadMethod.REUSE_RESOURCES)
  # next one is for stanza 1.4
  nlp = stanza.Pipeline(lang='en', processors='tokenize,ner,pos,lemma,depparse', download_method=stanza.DownloadMethod.REUSE_RESOURCES)
  #webServer = HTTPServer((host_name, server_port), MyServer)  # does not do parallel requests
  webServer = ThreadingHTTPServer((host_name, server_port), MyServer) # requests run in parallel
  print("Server started http://%s:%s" % (host_name, server_port))
  try:
    print("Starting to read gk solver shared memory database.")
    gkcommand=gk_path+" "+"dummy.js -readkb -defaults -relatedwords -similarities -mbsize 3000"
    #gkcommand=gk_path+" "+"dummy.js -readkb -defaults -relatedwords -similarities -mbsize 3000 cnet_50k.js quasi_50k.js wnet_10k.js"
    #gkcommand=gk_path+" "+"wnet_10k.js -readkb -defaults -relatedwords -similarities -mbsize 3000 "
    if axiomfiles:
      gkcommand=gk_path+" "+axiomfiles+" -readkb -defaults -relatedwords -mbsize 3000"
      print("Reading axiom files "+axiomfiles+".")
    else:
      gkcommand=gk_path+" "+"dummy.js -readkb -defaults -relatedwords -similarities -mbsize 3000"  
      print("No axiomfiles are read.")
    os.system(gkcommand)
    print("gk solver shared memory database ready.")   
  except:
    print("Could not read gk solver shared memory database.")
  print("Server ready.")
  try:
      buffer = 1
      sys.stderr = open(logfile, 'w', buffer)
      webServer.serve_forever()     
  except KeyboardInterrupt:
      pass

  webServer.server_close()
  print("Server stopped.")

# ===== the end ======
