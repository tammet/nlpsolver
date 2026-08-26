# Proof explanation formatter for the llm-based nlpsolver.
#
# Builds human-readable step-by-step proof explanations from the raw prover
# output.  Also builds the sentence map that links clause names to original
# input sentences.
#
# Public API used by procproofs.py:
#   build_sentence_map(s1_json)                   -- sent_SN_K -> raw text
#   format_explanation(answers, sentence_map, ...) -- full explanation string
#   ans_display_key(val)                           -- dedup key for an answer
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
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

import re

from proof_render import (
  compute_skolem_types,
  ans_atom_name,
  entity_name,
  clause_to_str,
  format_clause_logic,
  format_clause_traditional,
  block_to_english,
)
import globals as g


# ======== formatting helpers ========

def _fmt_pct(conf):
  """Format a confidence float as a percentage string, e.g. 0.81 -> '81%'."""
  return str(round(conf * 100)) + "%"


def _extract_step_conf(reason):
  """Return the trailing confidence value from a proof step reason, or 1.0."""
  if not isinstance(reason, list) or not reason:
    return 1.0
  last = reason[-1]
  if isinstance(last, float) or (isinstance(last, int) and not isinstance(last, bool)):
    return float(last)
  return 1.0


# ======== sentence map ========

def build_sentence_map(s1_json):
  """Build {"sent_S1": "raw text", "sent_S1_2": "raw text2", ...} from stage-1 output.

  s1_json is a list of sentence objects:
    [{"raw": "John is nice.", "units": [{"unit_id": "S1", ...}, ...]}, ...]

  Multiple raw sentences produce units with the same unit_id (e.g. "S1").
  We mirror the unique-name scheme used by logconvert: the Nth occurrence of
  unit_id "S1" maps to "sent_S1" (N=1) or "sent_S1_N" (N>1).
  Returns an empty dict if s1_json is None or malformed.
  """
  result = {}
  if not s1_json or not isinstance(s1_json, list):
    return result
  uid_count = {}
  for sent_obj in s1_json:
    if not isinstance(sent_obj, dict):
      continue
    raw = sent_obj.get("raw", "")
    for unit in sent_obj.get("units", []):
      if not isinstance(unit, dict):
        continue
      uid = unit.get("unit_id", "")
      if uid:
        uid_count[uid] = uid_count.get(uid, 0) + 1
        key = "sent_" + uid
        if uid_count[uid] > 1:
          key = key + "_" + str(uid_count[uid])
        result[key] = raw
  return result


# ======== proof-step rendering ========

def _collect_sent_names(proof):
  """Return the set of sent_* clause names referenced in a proof."""
  names = set()
  for step in proof:
    reason = step[1] if len(step) > 1 else []
    if isinstance(reason, list) and reason and reason[0] == "in":
      name = reason[1] if len(reason) > 1 else ""
      if isinstance(name, str) and name.startswith("sent_"):
        names.add(name)
  return names


def _sent_name_sort_key(name):
  """Sort key for sent_SN[_K] names: (primary_id, occurrence_suffix)."""
  # Primary: the S-number, e.g. S1 -> 1, S2 -> 2
  m_primary = re.search(r'S(\d+)', name)
  primary = int(m_primary.group(1)) if m_primary else 0
  # Suffix: the _K counter, e.g. sent_S1_3 -> 3; absent -> 0 (first occurrence)
  m_suffix = re.search(r'_(\d+)$', name)
  suffix = int(m_suffix.group(1)) if m_suffix else 0
  return (primary, suffix)


_LITBRIDGE_ROUND = re.compile(r"_r(\d+)::")


_GRAPH_ROUND = re.compile(r"_graph(?:lift)?::")


def _litbridge_label(source):
  """`added rule`, naming the round or the mechanism the clause name carries."""
  if _GRAPH_ROUND.search(source or ""):
    return ("added open-name rule (graph)" if "_graph::" in (source or "")
            else "added rule (lifted from the graph proof)")
  m = _LITBRIDGE_ROUND.search(source or "")
  return "added rule (round %s)" % m.group(1) if m else "added rule"


def _is_litbridge_source(source):
  """Return True if source is a clause a literal-bridge rule added.

  The prefix is written by litbridge_converter and shared through
  utils.LITBRIDGE_CLAUSE_PREFIX.  Such a clause is neither the passage nor a
  standing axiom: it is an invented, defeasible rule this run added, and the
  reader has to be told which one a step leans on.
  """
  from utils import is_litbridge_clause_name
  return is_litbridge_clause_name(source)


def _is_background_source(source):
  """Return True if source is a background-knowledge axiom (not a sentence)."""
  if not isinstance(source, str):
    return False
  if _is_litbridge_source(source):
    return False
  # frm_N comes from axioms_std.js; other non-sent_ sources are also background
  return bool(re.match(r'^frm_\d+', source)) or (
    source and not source.startswith("sent_") and not source.startswith("$"))


def clause_labels(logic):
  """`@name` -> what the proof should say about that clause.

  Two kinds of clause say more about themselves than their name does:

    * a wording-variant rule of the graph translation (`norm_<n>`), whose
      `@variant` records which marked form it bridges to which base form;
    * an invented rule carrying `@nl`, the program's own English reading of
      it, which the "Added rules" section prints instead of nothing.
  """
  out = {}
  for c in (logic or []):
    if not isinstance(c, dict):
      continue
    name = c.get("@name")
    if not isinstance(name, str) or not name:
      continue
    var = c.get("@variant")
    if isinstance(var, dict) and var.get("marked") and var.get("base"):
      out.setdefault(name, {})["why"] = ("wording variant: %s -> %s"
                                         % (var["marked"], var["base"]))
    nl = c.get("@nl")
    if isinstance(nl, str) and nl.strip():
      out.setdefault(name, {})["english"] = nl.strip()
  return out


def _format_why(reason, sent_nr, clause=None, labels=None):
  """Format the 'why' part of a proof step reason."""
  if not isinstance(reason, list) or not reason:
    return "unknown"
  kind = reason[0]
  if kind == "in":
    source   = reason[1] if len(reason) > 1 else ""
    polarity = reason[2] if len(reason) > 2 else ""
    named = (labels or {}).get(source) or {}
    if named.get("why") and polarity != "goal":
      return named["why"]
    if polarity == "goal":
      # $auto_negated_question is the refutation assumption (assumed for contradiction)
      if source == "$auto_negated_question":
        return "assumption"
      # Other goal-sourced clauses (backward chaining from the question)
      return "from question"
    if source in sent_nr:
      return "sentence " + str(sent_nr[source])
    if _is_litbridge_source(source):
      return _litbridge_label(source)
    if _is_background_source(source):
      return "background knowledge"
    return source
  else:
    # Collect integer step references; stop at the first string label
    # ("fromaxiom" / "fromgoal") which precedes the trailing confidence int.
    step_refs = []
    for el in reason[1:]:
      if isinstance(el, str):
        break
      if isinstance(el, int):
        step_refs.append(str(el))
      elif isinstance(el, list) and el and isinstance(el[0], int):
        step_refs.append(str(el[0]))
    if step_refs:
      return "from steps " + ", ".join(step_refs)
    return kind


def _format_step(step, sent_nr, show_logic=False, labels=None):
  """Render one proof step as a readable line."""
  nr     = step[0] if len(step) > 0 else "?"
  reason = step[1] if len(step) > 1 else []
  clause = step[2] if len(step) > 2 else []

  clause_str = clause_to_str(clause)
  why_str    = _format_why(reason, sent_nr, clause, labels)
  conf       = _extract_step_conf(reason)
  if conf < 0.9999:
    why_str = why_str + ", confidence " + _fmt_pct(conf)
  line = "  (" + str(nr) + ") " + clause_str + "  [" + why_str + "]"
  if show_logic:
    if g.options.get("json_flag"):
      line += "\n        " + format_clause_logic(clause)
    else:
      conf = _extract_step_conf(reason)
      c = conf if conf < 0.9999 else None
      logic_str = format_clause_traditional(clause, confidence=c)
      # Re-indent continuation lines to align with the 8-space proof prefix.
      logic_str = logic_str.replace("\n", "\n        ")
      line += "\n        " + logic_str
  return line


def _answer_label(val):
  """Short label for use in answer headings, e.g. '[in, Estonia]:'."""
  if val is True:  return "True"
  if val is False: return "False"
  if isinstance(val, list) and val:
    atom = val[0]
    if isinstance(atom, list) and len(atom) == 3:
      # Where-query atom ["$ans", prep, entity]: bracket notation [prep, entity]
      return "[" + ", ".join(entity_name(a) for a in atom[1:]) + "]"
    # Regular answer: use first arg only (ignores context args like W0, present, ...)
    return ans_atom_name(atom)
  return str(val)


# ======== answer dedup helpers ========

def ans_display_key(val):
  """Canonical dedup key for an answer value.

  Order-independent (frozenset) so that disjunctive residuals like
  [[$ans,A,...],[$ans,B,...]] and [[$ans,B,...],[$ans,A,...]] are treated
  as the same answer.  Context args (world state, time, ...) beyond the
  primary entity are ignored for regular answers; where-query atoms
  (exactly 3 elements: [$ans, prep, entity]) keep both args.
  """
  if val is True or val is False or val is None:
    return val
  if isinstance(val, list) and val:
    def _atom_key(atom):
      if not isinstance(atom, list) or len(atom) < 2:
        return str(atom)
      if len(atom) == 3:               # where-query: [$ans, prep, entity]
        return tuple(entity_name(a) for a in atom[1:3])
      return entity_name(atom[1])      # regular: ignore context args
    return frozenset(_atom_key(a) for a in val)
  return str(val)


def _count_distinct_answers(answers):
  seen = set()
  for ans in answers:
    k = ans_display_key(ans.get("answer"))
    if k not in seen:
      seen.add(k)
  return len(seen)


# ======== explanation formatter ========

def format_explanation(answers, sentence_map, show_logic=False, logic=None):
  """Build a step-by-step proof explanation for all (non-duplicate) answers."""
  blocks    = []
  seen_keys = set()
  multi     = _count_distinct_answers(answers) > 1

  for ans in answers:
    val = ans.get("answer")
    key = ans_display_key(val)
    if key in seen_keys:
      continue
    seen_keys.add(key)

    proof = ans.get("positive proof") or ans.get("negative proof")
    if not proof:
      continue

    # Which sent_* names appear in this proof?
    used_names   = _collect_sent_names(proof)
    sorted_names = sorted(used_names, key=_sent_name_sort_key)

    # Each sentence_map key now maps to exactly one raw string (unique names).
    # Deduplicate by raw text so a sentence cited multiple times shows once.
    sent_nr    = {}   # sent_SN[_K] -> display number
    seen_raws  = {}   # raw text -> display number (first assigned)
    sent_lines = ["Sentences used:"]
    for name in sorted_names:
      raw = sentence_map.get(name)
      if raw is None:
        raw = name              # fallback: show the clause name itself
      if raw not in seen_raws:
        nr = len(seen_raws) + 1
        seen_raws[raw] = nr
        sent_lines.append("  (" + str(nr) + ") " + raw)
      sent_nr.setdefault(name, seen_raws[raw])

    # Collect background-knowledge steps (sourced from frm_* axioms) for a
    # separate "Knowledge used:" section, mirroring the old UDP-pipeline style.
    compute_skolem_types(proof, logic=logic)
    labels = clause_labels(logic)
    bk_seen  = {}   # clause_str -> already listed flag
    bk_lines = []
    lb_seen  = {}   # the same, for the rules this run added
    lb_lines = []
    for step in proof:
      reason = step[1] if len(step) > 1 else []
      if not (isinstance(reason, list) and len(reason) > 1 and reason[0] == "in"):
        continue
      source = reason[1]
      added = isinstance(source, str) and _is_litbridge_source(source)
      if not (added or (isinstance(source, str)
                        and _is_background_source(source))):
        continue
      clause = step[2] if len(step) > 2 else []
      cstr = clause_to_str(clause)
      seen, lines = (lb_seen, lb_lines) if added else (bk_seen, bk_lines)
      if cstr not in seen:
        seen[cstr] = True
        if added:
          why = ("Why: %s, held unless something contradicts it."
                 % _litbridge_label(source).replace("added rule",
                                                    "a rule this run added"))
          english = (labels.get(source) or {}).get("english")
          if english:
            why = "Reads: %s.  %s" % (english.rstrip("."), why)
        else:
          why = "Why: assumed basic knowledge."
        lines.append("  " + cstr + ". " + why)
        if show_logic:
          if g.options.get("json_flag"):
            lines.append("    " + format_clause_logic(clause))
          else:
            logic_str = format_clause_traditional(clause)
            logic_str = logic_str.replace("\n", "\n    ")
            lines.append("    " + logic_str)

    # Proof step list — use "by contradiction" header when proof ends in Contradiction.
    is_contradiction = any(len(s) > 2 and s[2] is False for s in proof)
    proof_header = "Proof steps (by contradiction):" if is_contradiction else "Proof steps:"
    step_lines = [proof_header]
    for step in proof:
      step_lines.append(_format_step(step, sent_nr, show_logic=show_logic,
                                     labels=labels))

    # Append exceptions section from answer-level blockers (grounded constants).
    blockers = ans.get("blockers", [])
    if blockers:
      blocker_strs = [block_to_english(blk) for blk in blockers]
      blocker_strs = [s for s in blocker_strs if s]
      if blocker_strs:
        step_lines.append("Exceptions checked and not holding:")
        for bs in blocker_strs:
          step_lines.append("  " + bs)

    parts_block = ["\n".join(sent_lines)]
    if lb_lines:
      parts_block.append("Added rules (invented for this question, "
                         "defeasible):\n" + "\n".join(lb_lines))
    if bk_lines:
      parts_block.append("Knowledge used:\n" + "\n".join(bk_lines))
    parts_block.append("\n".join(step_lines))
    block = "\n".join(parts_block)

    conf = ans.get("confidence", 1)
    if conf < 0.9999:
      block = "Confidence " + _fmt_pct(conf) + ".\n" + block

    if multi:
      label = _answer_label(val)
      block = label + ":\n" + block

    blocks.append(block)

  if not blocks:
    return ""
  return "Explained:\n\n" + "\n\n".join(blocks)


# =========== the end ==========
