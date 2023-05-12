#!/usr/bin/env python3

import sys
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import unquote,parse_qs

import amrlib
import penman
import pickle
import amr_clausifier


try: 
  import amrlib
  import penman
  import pickle
  import amr_clausifier
except:
  print("""Install the requirements by running 'pip install -r requirements.txt'""")
  sys.exit(0)


host_name="localhost"
server_port=9000
logfile="/dev/null"

# ====== globals used during work ========

stog=None # at startup nlp is assigned the stanza pipeline

count=0
import time

# === request processing ===

class MyServer(BaseHTTPRequestHandler):
  def do_GET(self):
    #global count



    path =unquote(self.path) # urldecode
    if path: path=path[2:]  # remove initial slash

    # Parsing query string to dict
    qsvars = parse_qs(path)

    result = ""
    if "text" in qsvars.keys():
      text = qsvars["text"]
      if text:
        result = parse_text(text)
        print(result)

    self.send_response(200)
    self.send_header("Content-type", "text/json")
    self.end_headers()    
    self.wfile.write(bytes("%s\n" % json.dumps(result), "utf-8"))





# ====== starting ======

def parse_text(text):

  print("Starting to parse:", text)

  g = stog.parse_sents(text)
  amr = g[0]

  print("AMR", amr)

  g = penman.decode(amr)
  triples = [list(el) for el in g.triples]
  print("Triples", triples)

  clauses = amr_clausifier.extract_clauses(amr)
  print("Clauses", clauses)

  result = {
    "text": text,
    "amr": pickle.dumps(amr),
    "amr_triples": triples,
    "clauses": clauses
  }

  return result


if __name__ == "__main__":   
  print("Loading the model")

  stog = amrlib.load_stog_model(model_dir="models/model_stog")

  #webServer = HTTPServer((host_name, server_port), MyServer)  # does not do parallel requests
  webServer = ThreadingHTTPServer((host_name, server_port), MyServer) # requests run in parallel
  print("Server started http://%s:%s" % (host_name, server_port))
  try:
      buffer = 1
      sys.stderr = open(logfile, 'w', buffer)
      webServer.serve_forever()     
  except KeyboardInterrupt:
      pass

  webServer.server_close()
  print("Server stopped.")

# ===== the end ======
