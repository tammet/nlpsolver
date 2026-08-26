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
import subprocess
import tempfile
import os
import pretty
#import json

# ==== import other source files ====

# configuration and other globals are in globals.py
import globals

# small utilities are in utils.py
from utils import *

from cache import *

# === strategy selection ===

import json as _json

# Function term prefixes that indicate equational/measurement reasoning.
_EQ_FUNCTION_PREFIXES = ("$measure_of", "$theof1", "$list", "$datetime")


def _has_eq_functions(logic):
  """Return True if the clause list contains equalities with function terms.

  Scans for ["=", ...] or ["-=", ...] atoms where at least one argument
  is a list starting with a known function prefix ($measure_of, $theof1,
  $list, $datetime).  Also detects less_measure atoms.
  """
  for obj in logic:
    if not isinstance(obj, dict):
      continue
    for key in ("@logic", "@question"):
      clause = obj.get(key)
      if clause is not None and _scan_for_eq_functions(clause):
        return True
  return False


def _scan_for_eq_functions(tree):
  """Recursively check if tree contains equality with function terms or less_measure."""
  if not isinstance(tree, list) or not tree:
    return False
  op = tree[0] if isinstance(tree[0], str) else None
  # Check for less_measure predicate
  if op == "less_measure":
    return True
  # Check for equality with function term arguments
  if op in ("=", "-=") and len(tree) == 3:
    for arg in (tree[1], tree[2]):
      if (isinstance(arg, list) and arg
          and isinstance(arg[0], str) and arg[0] in _EQ_FUNCTION_PREFIXES):
        return True
  # Recurse into sub-lists (multi-literal clauses)
  for el in tree:
    if isinstance(el, list) and _scan_for_eq_functions(el):
      return True
  return False


_MANY_WORLDS_THRESHOLD = 5


def _auto_strategy(logic, opts):
  """Build a strategy JSON string based on clause analysis.

  - When equalities with function terms are present, use the unit strategy
    (better at equational reasoning via paramodulation on unit clauses).
  - When the world-state count is large (>= _MANY_WORLDS_THRESHOLD), use
    the unit strategy.  The default negative_pref/posunitpara saturates on
    duplicated past-world migration / frame / bridge resolvents (see
    case 198 analysis) and fails to reach answers it can find with unit.
  - Otherwise return the default negative_pref/posunitpara strategy.
  """
  if not logic or not isinstance(logic, list):
    return None

  if _has_eq_functions(logic):
    strategy = {"strategy": ["unit"], "query_preference": 0}
    reason = "eq functions detected"
  elif _count_worlds(logic) >= _MANY_WORLDS_THRESHOLD:
    strategy = {"strategy": ["unit"], "query_preference": 1}
    reason = f">= {_MANY_WORLDS_THRESHOLD} worlds ({_count_worlds(logic)} present)"
  else:
    strategy = {"strategy": ["negative_pref", "posunitpara"],
                "query_preference": 1}
    reason = "default"

  strat_str = _json.dumps(strategy)

  if opts.get("debug_print_flag"):
    print(f"\n=== auto-selected strategy ({reason}) ===\n")
    print(strat_str)

  return strat_str


# === seconds estimation based on world state count ===

# Minimum seconds needed per world count (from empirical measurement).
# Key = number of distinct world constants; value = minimum seconds observed.
_WORLD_SECONDS_TABLE = {
    # worlds: min_seconds (empirical, with verb normalization)
    6: 1,
    7: 2,
    8: 5,
    9: 10,
    10: 30,
    11: 150,
}
# Multiplier applied to the table values for safety margin.
_SECONDS_MULTIPLIER = 2


def _count_worlds(logic):
  """Count distinct world constants (W0, W1, ...) in the clause list."""
  from lc_clausify import is_world_constant
  worlds = set()
  def _scan(tree):
    if isinstance(tree, str):
      if is_world_constant(tree):
        worlds.add(tree)
      return
    if isinstance(tree, list):
      for el in tree:
        _scan(el)
  for obj in logic:
    if isinstance(obj, dict):
      for key in ("@logic", "@question"):
        v = obj.get(key)
        if v is not None:
          _scan(v)
  return len(worlds)


def _estimate_seconds(logic, default_seconds):
  """Estimate prover seconds from world count.

  Returns max(default_seconds, table_estimate * multiplier).
  """
  n = _count_worlds(logic)
  # Find the best matching entry: highest key <= n
  estimate = 0
  for threshold, secs in sorted(_WORLD_SECONDS_TABLE.items()):
    if n >= threshold:
      estimate = secs
  if estimate == 0:
    return default_seconds
  return max(default_seconds, int(estimate * _SECONDS_MULTIPLIER))


# === calling the prover ===

"""
Example logic argument:

[
    {"@logic": ["p","a"]},
    {"@logic": ["r","b"]},
    {"@logic": ["or",["-p","?:X"],["r","?:X"]]},
    {"@question": ["r","?:X"]}
]
"""

def call_prover(logic, s1_json=None):
  # Build GK input JSON with // comment lines between ASU groups.
  instr=clause_list_to_json_commented(logic, s1_json=s1_json)
  show_details = options.get("show_details_flag") or options["debug_print_flag"] or options["show_prover_flag"]
  if show_details:
    print("\n=== prover input (JSON) ===\n")
    print(instr)
  if options["prover_nosolve_flag"]:
    return(instr)    
  try:  
    infile,infilename=tempfile.mkstemp() 
  except:
    return("Error: failed to make a temporary file to write input to. ")  
  #print("infilename",infilename) 
  try:
    #infile=open(globals.prover_infile,"w")    
    #infile=open(infilename,"w")
    os.write(infile,str.encode(instr))
    os.close(infile)
    #infile.close()
  except KeyboardInterrupt:
    raise  
  except:
    os.remove(infilename)
    return("Error: failed to write prover infile "+infilename)     
  path=globals.prover_fname
  #decodedd=data.decode('ascii')
  #print("capi called with data",decodedd)
  params=[path]
  if options["prover_axiomfiles"]==False:
    params.append(globals.prover_axiomfile)
  else:
    for el in options["prover_axiomfiles"]:
      params.append(el)
  if options["prover_print"]:
    params=params+["-print",str(options["prover_print"])]
  if options["prover_strategy"]:
    params=params+["-strategy",options["prover_strategy"]]
  else:
    # Auto-select strategy based on clause analysis.
    auto_strat = _auto_strategy(logic, options)
    if auto_strat:
      params=params+["-strategytext", auto_strat]
  if options.get("prover_seconds_cli"):
    # CLI -seconds: use exactly what the user asked for
    params=params+["-seconds",str(options["prover_seconds"])]
  elif options["prover_seconds"]:
    # No CLI override: estimate from world count, never below default
    secs = _estimate_seconds(logic, options["prover_seconds"])
    if options.get("debug_print_flag") and secs > options["prover_seconds"]:
      print(f"\n=== auto-estimated prover seconds: {secs} (worlds: {_count_worlds(logic)}) ===\n")
    params=params+["-seconds",str(secs)]
  params.append(infilename)
  params=params+globals.prover_params
  params=params+["-datafolder",prover_datafolder]
  if options["prover_print_flag"] or options["show_prover_flag"]:
    print("\n=== prover params ===\n")
    print(" ".join(params))

  # -gkin FILENAME: save the GK input to a file for standalone experimentation.
  gkin_file = options.get("gkin_file")
  if gkin_file:
    try:
      # Build the command line with the user's filename instead of the temp file.
      cmd_params = [p if p != infilename else gkin_file for p in params]
      with open(gkin_file, "w") as f:
        f.write("// " + " ".join(cmd_params) + "\n")
        f.write(instr)
    except Exception as e:
      print("Warning: could not write GK input file " + gkin_file + ": " + str(e))

  # runtests collector: capture the gk command line with a placeholder for
  # the temp infile so it stays reproducible.
  collect = options.get("_collect")
  if collect is not None:
    cmd_params = [p if p != infilename else "<gk-input>" for p in params]
    collect["gk_command"] = " ".join(cmd_params)

  def _run_gk(run_params):
    cached = get_proof_from_cache(None, run_params)
    if cached:
      return cached
    try:
      calc = subprocess.Popen(run_params, stdout=subprocess.PIPE).communicate()[0]
    except KeyboardInterrupt:
      raise
    except:
      return "Error: prover gk is not available or crashed: check globals.py for the gk path."
    out = calc.decode('ascii')
    # High printlevel produces debug output before the result JSON.
    # The final result is preceded by "= showing final result =".
    marker = "= showing final result ="
    idx = out.find(marker)
    if idx >= 0:
      out = out[idx + len(marker):].lstrip("\n\r")
    add_proof_to_cache(run_params, out)
    return out

  sres = _run_gk(params)
  os.remove(infilename)
  # Prover result is displayed by solve.py (with -details+), not here,
  # to avoid duplicate output.
  return sres


# =========== the end ==========