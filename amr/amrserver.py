#!/usr/bin/env python3

import sys
import json
import bottle
from bottle import run, request
import amrconfig as cfg

try: 
  import amrlib
  import penman
  import pickle
  import amr_clausifier
except:
  print("""Install the requirements by running 'pip install -r requirements.txt'""")
  sys.exit(0)


host_name="localhost"
server_port=cfg.amr_server_port
logfile="/dev/null"

# ====== globals used during work ========

stog=None # at startup nlp is assigned the stanza pipeline

port = 9000
app = bottle.Bottle()


count=0

# === request processing ===

def index():
  text = request.query.get("text", "")
  result = []
  if text:
      result = parse_text(text)
      print(result)
  return json.dumps(result)




# ====== starting ======

def parse_text(text):
  global stog

  if stog is None:
    stog = amrlib.load_stog_model(model_dir="models/model_stog")

  g = stog.parse_sents([text])
  amr = g[0]


  g = penman.decode(amr)
  triples = [list(el) for el in g.triples]

  clauses = amr_clausifier.extract_clauses(amr)

  result = {
    "text": text,
    "amr": amr,
    "amr_triples": triples,
    "clauses": clauses
  }

  return result

def setup_routing(app):
    app.route("/", "GET", index)


setup_routing(app)

if __name__ == "__main__":
  run(host="localhost", port=port, app=app, debug=True, reloader=True)