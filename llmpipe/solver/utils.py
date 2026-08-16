# Small utilities for the nlpsolver.
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

import json
import globals

# Every clause a literal-bridge rule compiles to carries this name prefix
# (litbridge_converter writes it, proof_explain reads it back), so a proof step
# citing an invented rule can be told apart from the passage and from the
# standing axioms.
LITBRIDGE_CLAUSE_PREFIX = "dynamic_bridge_"


def is_litbridge_clause_name(name):
  """Was this clause added by the literal-bridge machinery?"""
  return isinstance(name, str) and name.startswith(LITBRIDGE_CLAUSE_PREFIX)


def debug_print(label, data=None, flag=None):
  """Print a labelled debug message when the relevant flag is set.

  flag defaults to globals.options["debug_print_flag"].  Pass an explicit
  boolean (e.g. a module-level debug variable) to use a different flag.
  """
  if flag is None:
    flag = globals.options["debug_print_flag"]
  if not flag:
    return
  print()
  print(label, end='')
  if data is None:
    print()
    return
  if type(data) == list:
    print(":")
    for el in data:
      if el and type(el) == list:
        print("  [")
        for subel in el:
          print("   ", subel)
        print("  ]")
      else:
        print(" ", el)
  elif type(data) == dict:
    print(":")
    for key in data:
      print(" ", key, ":", data[key])
  else:
    print(" :", data)


def clause_list_to_json(clauselist):
  reslst = []
  for clause in clauselist:
    clauserep = []
    if "@logic" in clause: logic = clause["@logic"]
    if "@question" in clause: logic = clause["@question"]
    if not logic: continue
    if logic[0] in ["or", "and"]:
      newlogic = []
      for atom in logic:
        newatom = json.dumps(atom, separators=(',', ':'))
        newlogic.append(newatom)
      if len(logic) > 3:
        logicstr = ",\n    ".join(newlogic)
      else:
        logicstr = ", ".join(newlogic)
      logicstr = ("[" + logicstr + "]")
    else:
      newlogic = json.dumps(logic, separators=(',', ':'))
      logicstr = newlogic
    clauserep.append("{")
    count = 0
    if "@logic" in clause: clauserep.append("\"@logic\": " + logicstr)
    if "@question" in clause: clauserep.append("\"@question\": " + logicstr)
    for key in clause:
      if not (key in ["@logic", "@question", "@askvars", "@where_query", "@when_query", "@who_query", "@who_entity", "@who_kind", "@what_query", "@sourcetype"]):
        clauserep.append(",\n " + json.dumps(key) + ": " + json.dumps(clause[key]))
        count += 1
    clauserep.append("}")
    clausestr = "".join(clauserep)
    reslst.append(clausestr)
  res = "[\n" + ",\n".join(reslst) + "\n]"
  return res


def build_asu_text_map(s1_json):
  """Build a map from @name base → ASU text for clause grouping.

  Returns {"sent_S1": "John 1 is a man.", "sent_S2": "Eve 2 liked John 1.", ...}.
  Also includes "entity_S1" entries (entity category clauses share the ASU's text).
  Uses the ASU 'text' field (normalized), falling back to 'raw' if no text.
  """
  result = {}
  if not s1_json or not isinstance(s1_json, list):
    return result
  uid_count = {}
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "")
    for unit in pkg.get("units", []):
      if not isinstance(unit, dict):
        continue
      uid = unit.get("unit_id", "")
      if not uid:
        continue
      text = unit.get("text", "") or raw
      uid_count[uid] = uid_count.get(uid, 0) + 1
      key = "sent_" + uid
      if uid_count[uid] > 1:
        key = key + "_" + str(uid_count[uid])
      result[key] = text
      # Entity category clauses use "entity_SN" naming
      entity_key = "entity_" + uid
      if entity_key not in result:
        result[entity_key] = text
  return result


def _name_base(name):
  """Extract the grouping key from a clause @name.

  Strips trailing _N suffixes and normalizes entity_ to sent_ so entity
  category clauses group with their ASU's main clauses.
  'sent_S1_2' -> 'sent_S1', 'entity_S1' -> 'sent_S1', 'sent_S3' -> 'sent_S3'.
  """
  import re
  m = re.match(r'^(?:sent|entity)_(S\d+)(?:_\d+)?$', name)
  return "sent_" + m.group(1) if m else name


def format_sentences_to_clauses(logic, s1_json, json_mode=False):
  """Format the 'sentences mapped to clauses' display block.

  Groups clauses by their ASU source and shows each ASU's text as a header
  followed by the clauses derived from it, in traditional or JSON syntax.
  Population facts (@sourcetype:"populate") are grouped separately at the end.
  """
  asu_map = build_asu_text_map(s1_json)

  # Separate population facts from ASU-derived clauses, then group by @name base.
  from collections import OrderedDict
  groups = OrderedDict()
  pop_clauses = []
  for obj in logic:
    if not isinstance(obj, dict):
      continue
    if obj.get("@sourcetype") == "populate":
      pop_clauses.append(obj)
      continue
    name = obj.get("@name", "")
    base = _name_base(name)
    if base not in groups:
      groups[base] = []
    groups[base].append(obj)

  lines = ["=== sentences mapped to clauses: ===", ""]

  for base, clauses in groups.items():
    # Determine header text
    if base in asu_map:
      header = asu_map[base]
    elif base == "pop_what":
      header = "[population: class witnesses for what-query]"
    else:
      header = "[generated: " + base + "]"
    lines.append(header)
    _append_clause_lines(lines, clauses, json_mode)

  if pop_clauses:
    lines.append("[population: from input]")
    _append_clause_lines(lines, pop_clauses, json_mode)

  return "\n".join(lines)


def _append_clause_lines(lines, clauses, json_mode):
  """Append formatted clause lines to the output list."""
  for obj in clauses:
    clause = obj.get("@logic") or obj.get("@question")
    if clause is None:
      continue
    is_question = "@question" in obj
    conf = obj.get("@confidence")
    if json_mode:
      # Strip @sourcetype from the display copy
      display = {k: v for k, v in obj.items() if k != "@sourcetype"}
      clause_str = json.dumps(display, separators=(',', ':'), ensure_ascii=False)
    else:
      from proof_render import format_clause_traditional
      if is_question:
        clause_str = "question: " + format_clause_traditional(clause)
      else:
        c = conf if conf is not None and conf < 0.9999 else None
        clause_str = format_clause_traditional(clause, confidence=c)
      # Re-indent continuation lines
      clause_str = clause_str.replace("\n", "\n    ")
    lines.append("  " + clause_str)


def clause_list_to_json_commented(clauselist, s1_json=None):
  """Like clause_list_to_json but inserts // comment lines between ASU groups."""
  asu_map = build_asu_text_map(s1_json) if s1_json else {}

  reslst = []
  prev_base = None
  prev_is_pop = None
  for clause in clauselist:
    name = clause.get("@name", "") if isinstance(clause, dict) else ""
    is_pop = (isinstance(clause, dict) and clause.get("@sourcetype") == "populate")
    base = _name_base(name)

    # Insert comment when the group or population status changes
    if base != prev_base or is_pop != prev_is_pop:
      if is_pop and not prev_is_pop:
        reslst.append("// [population: from input]")
      elif base in asu_map:
        reslst.append("// " + asu_map[base])
      elif base == "pop_what":
        reslst.append("// [population: class witnesses for what-query]")
      elif base:
        reslst.append("// [generated: " + base + "]")
      prev_base = base
      prev_is_pop = is_pop

    # Build the clause JSON (same logic as clause_list_to_json)
    logic = None
    if "@logic" in clause: logic = clause["@logic"]
    if "@question" in clause: logic = clause["@question"]
    if not logic: continue
    if isinstance(logic, list) and logic and isinstance(logic[0], list):
      newlogic = [json.dumps(atom, separators=(',', ':')) for atom in logic]
      if len(logic) > 3:
        logicstr = "[" + ",\n    ".join(newlogic) + "]"
      else:
        logicstr = "[" + ", ".join(newlogic) + "]"
    else:
      logicstr = json.dumps(logic, separators=(',', ':'))
    clauserep = ["{"]
    if "@logic" in clause: clauserep.append("\"@logic\": " + logicstr)
    if "@question" in clause: clauserep.append("\"@question\": " + logicstr)
    # Emit @role: "assumption" on every non-@question clause.
    # @question and @role are mutually exclusive at the gk parser — the
    # @question shorthand already sets role="question" internally.
    if "@question" not in clause:
      clauserep.append(",\n \"@role\": \"assumption\"")
    for key in clause:
      if key not in ("@logic", "@question", "@askvars", "@where_query", "@when_query", "@who_query", "@who_entity", "@who_kind", "@what_query", "@sourcetype", "@role"):
        clauserep.append(",\n " + json.dumps(key) + ": " + json.dumps(clause[key]))
    clauserep.append("}")
    reslst.append("".join(clauserep))

  return "[\n" + ",\n".join(reslst) + "\n]"


# =========== the end ==========
