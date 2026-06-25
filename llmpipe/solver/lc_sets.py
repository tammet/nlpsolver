# Set/counting programmatic conversion for the llm-based nlpsolver.
#
# Transforms Stage-2 ["$setof", VAR, CONDITIONS] terms into canonical
# form and generates membership axioms + element instantiation.
#
# Two canonical forms:
#
# 1. Predicate-anchored (when an anchor like "have" is found):
#    ["$setof","have","John 1",["$and",["$isa","car","$arg1"],["$prop","red","$arg1"]]]
#    - Anchor predicate extracted from conditions, remaining get $ prefix
#
# 2. Conditions-only (no anchor):
#    ["$setof","id","set_1",["$and",["isa","elephant","$arg1"],["prop","red","$arg1"]]]
#    - No $ prefix on predicates, unique set_id assigned
#
# Entry point: process_sets(formula)
#
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

import json
import copy
import re
import hashlib

from globals import options as _g_options
import lc_encoding as _lc_encoding


_SETLABEL_SK_RE = re.compile(r"^sk\d")


def _content_label(cond_term):
  """(abstraction) Stable short id keyed on a $setof body's predicate skeleton,
  with variables and skolems abstracted to one placeholder so two structurally-
  identical sets (a rule's "copies of E", a fact's "copies of sk1") share a
  label.  $arg1 and ordinary constants (class / relation names) are kept, so
  genuinely different sets ("copies" vs "reviews") still differ."""
  def _varlike(s):
    return (s.startswith("?:")
            or _SETLABEL_SK_RE.match(s) is not None
            or (len(s) <= 2 and s[:1].isupper()))   # Stage-2 vars: E, X, ...

  def norm(n):
    if isinstance(n, list):
      return [norm(e) for e in n]
    if isinstance(n, str):
      if n == "$arg1":
        return n
      return "#V" if _varlike(n) else n
    return n

  return hashlib.md5(
      json.dumps(norm(cond_term), sort_keys=True).encode()).hexdigest()[:8]


# Module-level counter for unique set identifiers (reset externally if needed).
_set_counter = 0

# Anchor predicates: maps predicate name to the index where VAR appears.
_ANCHOR_PREDS = {
  "have":               2,   # ["have", SUBJ, VAR]
  "has part":           2,   # ["has part", SUBJ, VAR]
  "is rel2":            3,   # ["is rel2", REL, SUBJ, VAR]
  "has degree rel2":    3,   # ["has degree rel2", REL, SUBJ, VAR, ...]
  "can":                1,   # ["can", VAR, WHAT]
}


class _SetofInfo:
  """Metadata for a single rewritten $setof term."""
  def __init__(self):
    self.canonical = None       # the rewritten $setof list
    self.anchor = None          # anchor predicate name or "id"
    self.subject = None         # anchor subject or set_id
    self.conditions = None      # the $and list (canonical form)
    self.bound_var = None       # original bound variable
    self.arg_name = None        # replacement variable ($arg1, $arg2, ...)
    self.anchored = False       # True if predicate-anchored
    self.depth = 0              # nesting depth


def process_sets(formula):
  """Rewrite $setof terms in formula to canonical form.

  Returns (rewritten_formula, axioms, element_clauses) where:
  - axioms: list of formula-level axioms (forall/biconditional) to clausify
  - element_clauses: list of ground clause dicts ready to add to clause list
  """
  if not isinstance(formula, list):
    return formula, [], []

  hits = _find_setof_terms(formula)
  if not hits:
    return formula, [], []

  axioms = []
  element_clauses = []
  seen_axiom_sigs = {}   # axiom pattern sig -> True (for axiom dedup)

  for node, parent, index, depth, bound_var in hits:
    info = _rewrite_setof(node, depth)

    # Build membership axiom clauses (deduplicate by generalized pattern)
    ax_clauses = _build_membership_axiom(info)
    if ax_clauses:
      ax_sig = json.dumps(ax_clauses, sort_keys=True)
      if ax_sig not in seen_axiom_sigs:
        seen_axiom_sigs[ax_sig] = True
        axioms.extend(ax_clauses)

    # Replace in parent
    if parent is not None:
      parent[index] = node

  # Element instantiation: only for assertion-side count assertions
  # (inside "holds"), not for queries. Deduplicate by setof signature.
  instantiated_sigs = set()
  _walk_for_count(formula, instantiated_sigs, element_clauses)

  return formula, axioms, element_clauses


def _find_setof_terms(formula, depth=0, parent=None, index=None, outer_vars=None):
  """Walk formula tree, return list of (node, parent, index, depth, bound_var)
  for each $setof term, ordered inside-out (deepest first)."""
  if outer_vars is None:
    outer_vars = []
  results = []
  if not isinstance(formula, list) or len(formula) == 0:
    return results

  if len(formula) >= 3 and formula[0] == "$setof":
    bound_var = formula[1]
    # Rename if this var shadows an outer one
    if bound_var in outer_vars:
      _rename_shadowed_vars(formula, outer_vars)
      bound_var = formula[1]
    # Recurse into conditions first (inside-out)
    # Lambda forms:
    #   3-element: ["$setof", VAR, CONDITIONS] — anchor detected from conditions
    #   4-element: ["$setof", VAR, SET_ID, CONDITIONS] — conditions-only with set id
    new_outer = outer_vars + [bound_var]
    conds_idx = 3 if len(formula) == 4 else 2
    conds = formula[conds_idx] if conds_idx < len(formula) else formula
    inner = _find_setof_terms(conds, depth + 1, formula, conds_idx, new_outer)
    results.extend(inner)
    results.append((formula, parent, index, depth, bound_var))
    return results

  # Recurse into all sub-lists
  for i, child in enumerate(formula):
    if isinstance(child, list):
      inner = _find_setof_terms(child, depth, formula, i, outer_vars)
      results.extend(inner)

  return results


def _rename_shadowed_vars(formula, outer_vars):
  """If a $setof inside formula uses a VAR that's in outer_vars, rename it."""
  if not isinstance(formula, list) or len(formula) < 3:
    return
  if formula[0] != "$setof":
    return
  old_var = formula[1]
  if old_var not in outer_vars:
    return
  # Generate a fresh variable name
  suffix = 1
  while True:
    new_var = old_var.rstrip("0123456789") + str(suffix)
    if new_var not in outer_vars:
      break
    suffix += 1
  formula[1] = new_var
  # Replace in conditions (index 2 for 3-element, index 3 for 4-element)
  conds_idx = 3 if len(formula) == 4 else 2
  if conds_idx < len(formula):
    formula[conds_idx] = _replace_var(formula[conds_idx], old_var, new_var)


def _classify_setof(conditions, var):
  """Determine if conditions contain an anchoring predicate.
  Returns (anchor_pred, anchor_subject, remaining_conditions) or
  (None, None, conditions)."""
  if not isinstance(conditions, list):
    return None, None, conditions

  # Flatten: get the list of condition atoms
  cond_list = []
  if conditions[0] == "and" and len(conditions) > 1:
    cond_list = conditions[1:]
  else:
    cond_list = [conditions]

  anchor_pred = None
  anchor_subject = None
  remaining = []

  for cond in cond_list:
    if not isinstance(cond, list) or len(cond) < 2:
      remaining.append(cond)
      continue
    pred = cond[0]
    if pred in _ANCHOR_PREDS and not anchor_pred:
      var_idx = _ANCHOR_PREDS[pred]
      if var_idx < len(cond) and cond[var_idx] == var:
        anchor_pred = pred
        # Subject: for "can" there is no separate subject
        if pred == "can":
          anchor_subject = None
        elif pred in ("have", "has part"):
          anchor_subject = cond[1]
        elif pred in ("is rel2", "has degree rel2"):
          anchor_subject = cond[2]
        continue
    remaining.append(cond)

  if anchor_pred:
    return anchor_pred, anchor_subject, remaining
  return None, None, cond_list


def _strip_time_wrappers(frm):
  """Strip @time wrappers from a formula, replacing ["@time", T, body] with body.

  Applied to $setof bodies before set rewriting so that LLM-generated @time
  annotations inside $setof don't crash the membership axiom builder.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  if isinstance(frm[0], str) and frm[0] == "@time" and len(frm) == 3:
    return _strip_time_wrappers(frm[2])
  return [_strip_time_wrappers(child) for child in frm]


def _rewrite_setof(node, depth):
  """Rewrite a Stage-2 $setof lambda form to canonical form.

  Lambda forms:
    3-element: ["$setof", VAR, CONDITIONS] — anchor detected from conditions
    4-element: ["$setof", VAR, SET_ID, CONDITIONS] — conditions-only, set_id from Stage-1

  Canonical forms:
    anchored:  ["$setof", PRED, SUBJECT, ["$and", ...]]  (no id needed)
    cond-only: ["$setof", "id", SET_ID, ["$and", ...]]   (set_id from Stage-1)

  Returns SetofInfo with all metadata.
  """
  info = _SetofInfo()
  info.depth = depth
  info.bound_var = node[1]
  info.arg_name = "$arg" + str(depth + 1)

  var = info.bound_var

  # Parse lambda form: extract set_id (if present) and conditions
  if len(node) == 4:
    # 4-element: ["$setof", VAR, SET_ID, CONDITIONS]
    explicit_set_id = node[2]
    conditions = node[3]
  else:
    # 3-element: ["$setof", VAR, CONDITIONS]
    explicit_set_id = None
    conditions = node[2] if len(node) >= 3 else node[1]

  conditions = _strip_time_wrappers(conditions)

  anchor, subject, remaining = _classify_setof(conditions, var)

  if anchor:
    info.anchored = True
    info.anchor = anchor
    info.subject = subject
    # Prefix remaining predicates with $
    prefixed = [_prefix_condition(c) for c in remaining]
    # Replace var with $arg
    prefixed = [_replace_var(c, var, info.arg_name) for c in prefixed]
    sorted_conds = _sort_and_conditions(prefixed)
    cond_term = ["$and"] + sorted_conds
    if subject is not None:
      info.canonical = ["$setof", anchor, subject, cond_term]
    else:
      info.canonical = ["$setof", anchor, cond_term]
  else:
    info.anchored = False
    info.anchor = "id"
    # No $ prefix for conditions-only form
    conds_replaced = [_replace_var(c, var, info.arg_name) for c in remaining]
    sorted_conds = _sort_and_conditions(conds_replaced)
    cond_term = ["$and"] + sorted_conds
    # Set label.  Default: a per-occurrence counter.  Under the abstraction encodings: a
    # CONTENT-derived label keyed on the body's predicate skeleton (variables
    # and skolems abstracted), so two structurally-identical sets -- a rule's
    # "copies of E" and a fact's "copies of sk1" -- get the SAME label and their
    # $count terms unify (the bodies still disambiguate via normal unification).
    # The per-occurrence counter otherwise makes them set_1 vs set_2, which
    # never unify even when the bodies match (case 15).
    if explicit_set_id is not None:
      set_id = explicit_set_id
    elif _lc_encoding.current().entitymerge:
      set_id = "set_" + _content_label(cond_term)
    else:
      global _set_counter
      _set_counter += 1
      set_id = "set_" + str(_set_counter)
    info.subject = set_id
    info.canonical = ["$setof", "id", set_id, cond_term]

  info.conditions = info.canonical[-1]

  # Mutate node in place so all references update
  node.clear()
  node.extend(info.canonical)

  return info


def _prefix_condition(cond):
  """Add $ prefix to the predicate of a condition atom."""
  if not isinstance(cond, list) or len(cond) < 2:
    return cond
  cond = copy.deepcopy(cond)
  cond[0] = _prefix_pred(cond[0])
  return cond


def _sort_and_conditions(conds):
  """Sort $and entries: $isa/isa first (sorted among themselves),
  then rest sorted alphabetically by json.dumps."""
  isa_conds = []
  other_conds = []
  for c in conds:
    if isinstance(c, list) and len(c) >= 1 and c[0] in ("$isa", "isa"):
      isa_conds.append(c)
    else:
      other_conds.append(c)
  isa_conds.sort(key=lambda x: json.dumps(x, sort_keys=True))
  other_conds.sort(key=lambda x: json.dumps(x, sort_keys=True))
  return isa_conds + other_conds


def _prefix_pred(pred_name):
  """Add $ prefix: 'isa' -> '$isa', 'prop' -> '$prop',
  'has property' -> '$has_property', 'has degree property' -> '$has_degree_property'."""
  if pred_name.startswith("$"):
    return pred_name
  return "$" + pred_name.replace(" ", "_")


def _unprefix_pred(pred_name):
  """Remove $ prefix: '$isa' -> 'isa', '$prop' -> 'prop',
  '$has_property' -> 'has property'."""
  if not pred_name.startswith("$"):
    return pred_name
  return pred_name[1:].replace("_", " ")


def _negate_atom(atom):
  """Negate an atom by toggling the - prefix on the predicate."""
  if not isinstance(atom, list) or not atom:
    return atom
  pred = atom[0]
  if isinstance(pred, str) and pred.startswith("-"):
    return [pred[1:]] + atom[1:]
  elif isinstance(pred, str):
    return ["-" + pred] + atom[1:]
  return atom


def _prefix_vars_in_atom(atom, var_map):
  """Add ?: prefix to forall variable values in an atom for GK format."""
  bare_vars = set(var_map.values()) | {"M", "S"}
  return _prefix_vars_deep(atom, bare_vars)


def _prefix_vars_deep(term, bare_vars):
  """Add ?: prefix to all bare variable names in a term."""
  if not isinstance(term, list):
    if isinstance(term, str) and term in bare_vars:
      return "?:" + term
    return term
  return [_prefix_vars_deep(el, bare_vars) for el in term]


def _replace_var(formula, old_var, new_var):
  """Replace all occurrences of old_var with new_var in formula (deep copy)."""
  if formula == old_var:
    return new_var
  if not isinstance(formula, list):
    return formula
  return [_replace_var(el, old_var, new_var) for el in formula]


def _build_membership_axiom(setof_info):
  """Build forall/biconditional membership axiom for a $setof pattern.

  For anchored (sets2.txt style):
    forall ?:M, ?:S, ?:P, ?:C:
      member(?:M, $setof(have, ?:S, [$and, $isa(?:C,$arg1), $prop(?:P,$arg1)]))
      <=>
      isa(?:C, ?:M) & prop(?:P, ?:M) & have(?:S, ?:M)

  For conditions-only (sets1.txt style):
    forall ?:M, ?:S, ?:P, ?:C:
      member(?:M, $setof(id, ?:S, [$and, isa(?:C,$arg1), prop(?:P,$arg1)]))
      <=>
      isa(?:C, ?:M) & prop(?:P, ?:M)
  """
  conds = setof_info.conditions
  arg_name = setof_info.arg_name

  # Collect the condition atoms
  cond_list = []
  if isinstance(conds, list) and len(conds) > 0 and conds[0] in ("$and", "and"):
    cond_list = conds[1:]
  elif isinstance(conds, list) and len(conds) > 0:
    cond_list = [conds]

  if not cond_list:
    return None

  # For each condition atom, find non-$arg arguments and assign forall vars.
  # Also build the generalized setof pattern and the rhs conjuncts.
  var_counter = [0]
  arg_to_var = {}  # maps concrete arg value -> forall var name
  var_names_used = set()

  def _fresh_var():
    """Generate fresh forall variable names: C, D, E, ... skipping M, S.
    Uses bare names (no ?: prefix) — the clausifier adds ?: during clausification."""
    skip = {"M", "S"}
    letters = "CDEFGHIJKLNOPQRTUVWXYZ"
    idx = var_counter[0]
    var_counter[0] += 1
    if idx < len(letters):
      ch = letters[idx]
    else:
      ch = "V" + str(idx)
    return ch

  # Generalize each condition: replace non-$arg arguments with forall variables
  gen_conds = []
  rhs_atoms = []

  _LOGICAL_OPS = {"exists", "forall", "and", "or", "not", "implies",
                  "normally", "$and", "$or", "$not"}

  for cond in cond_list:
    if not isinstance(cond, list) or len(cond) < 2:
      gen_conds.append(copy.deepcopy(cond))
      continue
    # Skip logical operators (LLM-emitted nested quantifiers / connectives
    # inside $setof conditions). Stage-2 §9.4 says events go OUTSIDE as a
    # distributive forall/member block, but LLMs sometimes nest exists/and.
    if cond[0] in _LOGICAL_OPS:
      continue
    # Skip atoms whose args contain compound terms — the membership-axiom
    # builder only handles atoms with scalar (string/number) args.
    if any(isinstance(a, list) for a in cond[1:]):
      continue
    gen_cond = [cond[0]]
    rhs_atom_pred = _unprefix_pred(cond[0])
    rhs_atom = [rhs_atom_pred]

    for i in range(1, len(cond)):
      arg = cond[i]
      if arg == arg_name:
        # In generalized pattern, keep $arg1
        gen_cond.append(arg_name)
        # In rhs, replace with M (bare — clausifier adds ?:)
        rhs_atom.append("M")
      else:
        # Generalize to a forall variable
        if arg not in arg_to_var:
          arg_to_var[arg] = _fresh_var()
        fvar = arg_to_var[arg]
        gen_cond.append(fvar)
        rhs_atom.append(fvar)
    gen_conds.append(gen_cond)
    rhs_atoms.append(rhs_atom)

  # Add anchor predicate to rhs if anchored
  if setof_info.anchored:
    anchor_pred = setof_info.anchor
    if setof_info.subject is not None:
      # subject -> forall var
      subj = setof_info.subject
      if subj not in arg_to_var:
        arg_to_var[subj] = "S"
      subj_var = arg_to_var[subj]
      rhs_atoms.append([anchor_pred, subj_var, "M"])
    else:
      # anchor like "can" with no subject
      rhs_atoms.append([anchor_pred, "M"])

  # Build generalized $and term — always wrap in $and to match canonical form
  and_marker = "$and"
  if isinstance(setof_info.conditions, list) and setof_info.conditions[0] in ("$and", "and"):
    and_marker = setof_info.conditions[0]
  gen_and_term = [and_marker] + gen_conds

  # Build generalized $setof term
  if setof_info.anchored:
    subj = setof_info.subject
    subj_var = arg_to_var.get(subj, "S")
    if setof_info.subject is not None:
      gen_setof = ["$setof", setof_info.anchor, subj_var, gen_and_term]
    else:
      gen_setof = ["$setof", setof_info.anchor, gen_and_term]
  else:
    # For conditions-only: set_id -> forall var S
    gen_setof = ["$setof", "id", "S", gen_and_term]

  # Build member atom
  # Use ?:-prefixed variables for GK clause format.
  # Build a var_set including M and S for the prefix function.
  all_bare_vars = set(arg_to_var.values()) | {"M", "S"}
  gen_setof_prefixed = _prefix_vars_deep(gen_setof, all_bare_vars)
  member_atom = ["member", "?:M", gen_setof_prefixed]
  rhs_atoms_prefixed = []
  for atom in rhs_atoms:
    rhs_atoms_prefixed.append(_prefix_vars_in_atom(atom, arg_to_var))

  if not rhs_atoms_prefixed:
    return None

  # Build pre-clausified clauses directly (biconditional A <=> B1 & B2 & ...).
  # Forward: [-B1, -B2, ..., A] (conditions => member)
  # Backward: [-A, Bi] for each condition (member => each condition)
  clauses = []

  # Forward clause: negate all rhs atoms, add member
  forward = []
  for atom in rhs_atoms_prefixed:
    forward.append(_negate_atom(atom))
  forward.append(member_atom)
  clauses.append(forward)

  # Backward clauses: negate member, add each rhs atom
  neg_member = _negate_atom(member_atom)
  for atom in rhs_atoms_prefixed:
    clauses.append([neg_member, atom])

  return clauses


def _walk_for_count(formula, seen_sigs, clauses, source_name="S0", in_assertion=False):
  """Recursively find count assertions in assertion contexts and instantiate elements.
  Only instantiates inside holds (assertions), not inside question/ask (queries).
  Deduplicates by $setof signature."""
  if not isinstance(formula, list) or len(formula) == 0:
    return
  # Track @id for source name
  if len(formula) >= 3 and formula[0] == "@id":
    source_name = formula[1]
    _walk_for_count(formula[2], seen_sigs, clauses, source_name, in_assertion)
    return
  # Entering a holds block = assertion context
  if len(formula) >= 3 and formula[0] == "holds":
    for child in formula[1:]:
      if isinstance(child, list):
        _walk_for_count(child, seen_sigs, clauses, source_name, True)
    return
  # question/ask blocks are NOT assertion context — skip instantiation
  if len(formula) >= 2 and formula[0] in ("question", "ask"):
    return
  # Check for ["=", N, ["$count", SETOF_TERM]]
  if (len(formula) == 3 and formula[0] == "=" and
      isinstance(formula[1], (int, float)) and
      isinstance(formula[2], list) and len(formula[2]) == 2 and
      formula[2][0] == "$count" and in_assertion):
    count_setof = formula[2][1]
    sig = json.dumps(count_setof, sort_keys=True)
    if sig not in seen_sigs:
      seen_sigs.add(sig)
      count = int(formula[1])
      # Build a SetofInfo from the canonical setof term
      info = _info_from_canonical(count_setof)
      if info:
        el_clauses = _instantiate_elements(info, source_name, count)
        clauses.extend(el_clauses)
        # Also instantiate distributive events
        # (need to search in parent formula for forall/member blocks)
  # Check for forall/implies/member pattern in assertion context:
  # ["forall", VAR, ["implies", ["member", VAR, SETOF_TERM], CONSEQUENT]]
  # Generate a single existence fact: member("$some_TYPE", SETOF_TERM)
  if (in_assertion and len(formula) == 3 and formula[0] == "forall"
      and isinstance(formula[2], list) and len(formula[2]) == 3
      and formula[2][0] == "implies"):
    antecedent = formula[2][1]
    if (isinstance(antecedent, list) and len(antecedent) >= 3
        and antecedent[0] == "member"
        and isinstance(antecedent[2], list) and len(antecedent[2]) >= 3
        and antecedent[2][0] == "$setof"):
      setof_term = antecedent[2]
      sig = json.dumps(setof_term, sort_keys=True)
      if sig not in seen_sigs:
        seen_sigs.add(sig)
        # Extract type from conditions for naming
        type_name = _extract_type_from_setof(setof_term)
        el_name = "$some_" + type_name if type_name else "$some_set_member"
        member_fact = ["member", el_name, setof_term]
        clauses.append({"@name": "sent_" + str(source_name) + "_exist",
                        "@logic": member_fact})

  # Recurse
  for child in formula:
    if isinstance(child, list):
      _walk_for_count(child, seen_sigs, clauses, source_name, in_assertion)


def _extract_type_from_setof(setof_term):
  """Extract the primary type name from a $setof term's conditions.
  E.g. ["$setof","id","set 1",["$and",["isa","bear","$arg1"]]] -> "bear"
  """
  conds = setof_term[-1] if len(setof_term) >= 3 else None
  if not isinstance(conds, list):
    return None
  cond_list = conds[1:] if conds[0] in ("$and", "and") else [conds]
  for cond in cond_list:
    if (isinstance(cond, list) and len(cond) >= 3
        and isinstance(cond[0], str) and cond[0] in ("isa", "$isa")
        and isinstance(cond[1], str)):
      return cond[1]
  return None


def _info_from_canonical(setof_term):
  """Reconstruct a _SetofInfo from an already-rewritten canonical $setof term."""
  if not isinstance(setof_term, list) or len(setof_term) < 3 or setof_term[0] != "$setof":
    return None
  info = _SetofInfo()
  info.canonical = setof_term
  if setof_term[1] == "id":
    # Conditions-only: ["$setof", "id", SET_ID, CONDITIONS]
    info.anchored = False
    info.anchor = "id"
    info.subject = setof_term[2]
    info.conditions = setof_term[3] if len(setof_term) > 3 else None
    info.arg_name = "$arg1"
  else:
    # Predicate-anchored: ["$setof", PRED, SUBJ, CONDITIONS]
    # or ["$setof", PRED, CONDITIONS] (no subject, e.g. can)
    info.anchored = True
    info.anchor = setof_term[1]
    if len(setof_term) == 4:
      info.subject = setof_term[2]
      info.conditions = setof_term[3]
    else:
      info.subject = None
      info.conditions = setof_term[2]
    info.arg_name = "$arg1"
  return info


def _instantiate_elements(setof_info, source_name, count, tense=None, world=None):
  """Generate element constants for a positive set-count assertion.

  Creates min(count, set_element_limit) elements.
  For each element $setK_elI:
  - Properties from $setof conditions (with $ removed)
  - Anchor predicate (if anchored)
  - member($setK_elI, setof_term)
  - Pairwise distinctness

  Returns list of clause dicts with @name and @logic.
  """
  # Skip instantiation if subject is a variable (rule context, not concrete set).
  # Variables may appear as "?:X" (pre-clausification) or bare "X" (post-clausification).
  if setof_info.subject is not None and isinstance(setof_info.subject, str):
    s = setof_info.subject
    if s.startswith("?:") or (len(s) <= 2 and s[0].isupper()):
      return []

  limit = _g_options.get("set_element_limit", 3)
  n = min(count, limit)
  if n <= 0:
    return []

  # Determine set number for element naming
  global _set_counter
  _set_counter += 1
  set_num = str(_set_counter)

  elements = []
  for i in range(1, n + 1):
    elements.append("$set" + set_num + "_el" + str(i))

  clauses = []

  # Get condition atoms
  conds = setof_info.conditions
  cond_list = []
  if isinstance(conds, list) and len(conds) > 0 and conds[0] in ("$and", "and"):
    cond_list = conds[1:]
  elif isinstance(conds, list) and len(conds) > 0:
    cond_list = [conds]

  for i, el in enumerate(elements):
    el_name = source_name + "_el" + str(i + 1)

    # Instantiate each condition for this element
    for cond in cond_list:
      if not isinstance(cond, list) or len(cond) < 2:
        continue
      # Remove $ prefix from predicate and replace $arg with element
      atom = [_unprefix_pred(cond[0])]
      for j in range(1, len(cond)):
        arg = cond[j]
        if isinstance(arg, str) and arg.startswith("$arg"):
          atom.append(el)
        else:
          atom.append(arg)
      clauses.append({"@name": "sent_" + el_name, "@logic": atom})

    # Anchor predicate
    if setof_info.anchored and setof_info.subject is not None:
      anchor_atom = [setof_info.anchor, setof_info.subject, el]
      clauses.append({"@name": "sent_" + el_name, "@logic": anchor_atom})

    # Membership
    member_atom = ["member", el, setof_info.canonical]
    clauses.append({"@name": "sent_" + el_name, "@logic": member_atom})

  # Pairwise distinctness
  for i in range(len(elements)):
    for j in range(i + 1, len(elements)):
      dist_atom = ["-=", elements[i], elements[j]]
      clauses.append({"@name": "sent_" + source_name + "_dist", "@logic": dist_atom})

  return clauses


def _instantiate_distributive_events(formula, setof_term, elements, source_name):
  """Find forall/implies/member blocks that distribute events over the set.
  For each element, instantiate the event body with fresh event constants.
  Returns list of clause dicts."""
  results = []
  blocks = _find_distributive_blocks(formula, setof_term)

  for block in blocks:
    # block is the body of the implies (the exists part)
    member_var = block["member_var"]
    body = block["body"]

    for i, el in enumerate(elements):
      # Fresh event constant
      ev_name = "$set" + source_name + "_ev" + str(i + 1)

      # Replace member var with element, existential var with event constant
      instantiated = _replace_var(body, member_var, el)

      # Find and replace existential variables
      if (isinstance(instantiated, list) and len(instantiated) >= 3 and
          instantiated[0] == "exists"):
        ex_var = instantiated[1]
        ex_body = instantiated[2]
        instantiated = _replace_var(ex_body, ex_var, ev_name)

      # Flatten and conjuncts into individual clauses
      if isinstance(instantiated, list) and instantiated[0] == "and":
        for atom in instantiated[1:]:
          results.append({
            "@name": "sent_" + source_name + "_ev" + str(i + 1),
            "@logic": atom
          })
      else:
        results.append({
          "@name": "sent_" + source_name + "_ev" + str(i + 1),
          "@logic": instantiated
        })

  return results


def _find_distributive_blocks(formula, setof_term):
  """Find forall/implies/member patterns that distribute over a $setof."""
  results = []
  if not isinstance(formula, list) or len(formula) == 0:
    return results

  # Check for ["forall", VAR, ["implies", ["member", VAR, setof], BODY]]
  if (len(formula) == 3 and formula[0] == "forall"):
    fvar = formula[1]
    inner = formula[2]
    if (isinstance(inner, list) and len(inner) == 3 and inner[0] == "implies"):
      cond = inner[1]
      body = inner[2]
      if (isinstance(cond, list) and len(cond) == 3 and cond[0] == "member" and
          cond[1] == fvar):
        member_setof = cond[2]
        if json.dumps(member_setof, sort_keys=True) == json.dumps(setof_term, sort_keys=True):
          results.append({"member_var": fvar, "body": body})
          return results

  # Recurse
  for child in formula:
    if isinstance(child, list):
      results.extend(_find_distributive_blocks(child, setof_term))

  return results


# =========== the end ==========
