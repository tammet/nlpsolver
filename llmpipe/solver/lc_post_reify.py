# Reification passes for the post-clausification clause list.
#
# These passes replace flat Stage-2 entity IDs with structured function
# terms so the prover can reason about them consistently across mentions.
# Each pass also emits the bridge axioms that connect the reified term
# back to the original predicates.
#
# Sections:
#   - $theof1 family   (definite functional descriptions)
#                      _deep_replace, _find_is_rel2_match,
#                      _find_have_isa_match, _clause_atoms,
#                      rewrite_definites
#   - $measure_of family (measurements with units)
#                      _UNIT_CONVERSIONS, _convert_to_canonical,
#                      _canonicalize_measure, rewrite_measure_terms,
#                      _is_measure_term, _rewrite_measures_in_tree
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
#-----------------------------------------------------------------

import re

from globals import options as _g_options

# ======== $theof1 definite function terms ========

def _deep_replace(obj, old_val, new_val):
  """Recursively replace old_val with new_val throughout a nested list structure.

  old_val can be a string or a list (Skolem function).  Comparison is by
  equality (== operator, which does deep structural comparison for lists).
  """
  if obj == old_val:
    return new_val
  if isinstance(obj, list):
    return [_deep_replace(el, old_val, new_val) for el in obj]
  return obj


def _find_is_rel2_match(result, rel_name, value_id=None):
  """Find an is_rel2 atom in the clause list matching the given relation name.

  Scans all @logic entries for an atom of the form:
    ["is rel2", rel_name, VALUE_TERM, ARG_TERM, CTXT]
  or inside a disjunction (multi-literal clause):
    [... ["is rel2", rel_name, VALUE_TERM, ARG_TERM, CTXT] ...]

  When value_id is given, prefer the atom whose VALUE_TERM is the definite
  placeholder entity (value_id) over any other subject of the same relation.
  Otherwise a different named subject ("Andrew is the script editor for X")
  would be picked and then deep-replaced away.  Falls back to the first
  non-$theof1 match.

  Returns (clause_index, VALUE_TERM, ARG_TERM, CTXT) or None.
  """
  fallback = None
  for i, obj in enumerate(result):
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    clause = obj["@logic"]
    atoms = _clause_atoms(clause)
    for atom in atoms:
      if (isinstance(atom, list) and len(atom) >= 4
          and atom[0] == "is rel2" and atom[1] == rel_name):
        value_term = atom[2]
        # Skip if value_term is already a $theof1 term — a previous definite
        # pass already reified this slot, and chain-rewriting would silently
        # overwrite the existing type label (case 79: sister/brother collapse).
        if (isinstance(value_term, list) and value_term
            and value_term[0] == "$theof1"):
          continue
        arg_term = atom[3]
        ctxt = atom[4] if len(atom) > 4 else None
        if value_id is not None:
          # Strict: only the placeholder entity may be reified.  Never fall
          # back to a different named subject ("Andrew is the script editor
          # for X") — and when the placeholder is already gone (a duplicate
          # definite processed twice), return None so the caller skips.
          if value_term == value_id:
            return (i, value_term, arg_term, ctxt)
          continue
        if fallback is None:
          fallback = (i, value_term, arg_term, ctxt)
  return fallback


def _find_have_isa_match(result, type_base):
  """Fallback: find have/has_part + isa pair matching a definite type.

  Looks for clauses containing:
    ["isa", type_base, VALUE_TERM]
  and:
    ["have", ARG_TERM, VALUE_TERM, CTXT]
    or ["has part", ARG_TERM, VALUE_TERM, CTXT]
  where VALUE_TERM is the same in both.

  Returns (VALUE_TERM, ARG_TERM, CTXT) or None.
  """
  # Collect all (VALUE_TERM -> True) from isa atoms matching type_base
  isa_values = set()
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    for atom in _clause_atoms(obj["@logic"]):
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "isa" and atom[1] == type_base):
        val = atom[2]
        # Hashable key: use str() for lists (Skolem functions)
        isa_values.add(str(val) if isinstance(val, list) else val)

  # Find have or has_part atom whose VALUE_TERM is in isa_values
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    for atom in _clause_atoms(obj["@logic"]):
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] in ("have", "has part")):
        arg_term = atom[1]
        value_term = atom[2]
        ctxt = atom[3] if len(atom) > 3 else None
        key = str(value_term) if isinstance(value_term, list) else value_term
        if key in isa_values:
          return (value_term, arg_term, ctxt)
  return None


def _clause_atoms(clause):
  """Extract individual atoms from a clause (which may be a single atom or
  a multi-literal disjunction [lit1, lit2, ...] where each lit is a list)."""
  if not isinstance(clause, list) or not clause:
    return []
  # Multi-literal clause: list of lists (each element is an atom/literal)
  if isinstance(clause[0], list):
    return clause
  # Single-literal clause: the clause itself is the atom
  if isinstance(clause[0], str):
    return [clause]
  return []


def emit_definite_identities(result, asu_index):
  """Emit identities for "N is the R of B" constructions, before any $theof1
  reification runs.  A named subject N asserted in relation R to B IS the
  definite "the R of B", so N = $theof1(R, B).  rewrite_definites otherwise
  deep-replaces one is_rel2 subject with the $theof1 term and removes the
  clause, dropping the named entity's link (e.g. "Andrew Collins was the script
  editor for Badults" left Andrew connected to nothing).  Reads the pristine
  is_rel2 atoms, so it must run before rewrite_definites.  Additive: only adds
  equality clauses; the $theof1 terms it builds match those rewrite_definites
  will construct (same type_base, arg, ctxt), so the named entity and the
  definite term unify."""
  if not asu_index:
    return

  def _concrete(t):
    # a ground named entity: a plain string that is not a variable ("?:X"),
    # a Skolem ("sk..."), a world ("W0"/"w0"), or a $-term.
    return (isinstance(t, str) and not t.startswith("?:")
            and not t.startswith("sk") and not t.startswith("$")
            and not re.fullmatch(r"[Ww]\d+", t))

  seen = set()
  for asu in asu_index.values():
    for defn in (asu.get("definites") or []):
      if not (isinstance(defn, list) and len(defn) >= 3):
        continue
      rel_name = defn[0]
      value_id = defn[1]
      type_base = rel_name[:-3] if rel_name.endswith(" of") else rel_name
      for obj in list(result):
        if not (isinstance(obj, dict) and "@logic" in obj):
          continue
        for atom in _clause_atoms(obj["@logic"]):
          if (isinstance(atom, list) and len(atom) >= 4 and atom[0] == "is rel2"
              and atom[1] == rel_name):
            subj, arg = atom[2], atom[3]
            # only a concrete named subject that is NOT the placeholder being
            # reified, with a concrete arg (skip question/variable atoms).
            if not (_concrete(subj) and _concrete(arg) and subj != value_id):
              continue
            key = (rel_name, subj, arg)
            if key in seen:
              continue
            seen.add(key)
            ctxt = atom[4] if len(atom) > 4 else None
            fn = (["$theof1", type_base, arg, ctxt] if ctxt is not None
                  else ["$theof1", type_base, arg])
            result.append({"@name": "frm_theof", "@logic": ["=", subj, fn]})


def rewrite_definites(result, asu_index, sid, theof_relations):
  """Rewrite definite functional descriptions to $theof1 terms.

  For each definite in the ASU's Stage-1 data, find the corresponding
  is_rel2 (or have+isa fallback) in the clausified result, construct a
  $theof1 function term, and replace the entity throughout all clauses.

  theof_relations: set to collect (REL, TYPE) pairs for bridge axiom generation.
  """
  if not asu_index:
    return
  asu = asu_index.get(sid)
  if not asu:
    return
  definites = asu.get("definites")
  if not definites or not isinstance(definites, list):
    return

  for defn in definites:
    if not isinstance(defn, list) or len(defn) < 3:
      continue
    rel_name = defn[0]    # e.g., "father of", "head of"
    value_id = defn[1]    # e.g., "the father 2", "the head 1"
    # arg_id = defn[2]    # e.g., "John 1", "elephant 2" — may not appear in clauses

    # Compute base type: strip trailing " of" from relation name
    if rel_name.endswith(" of"):
      type_base = rel_name[:-3]
    else:
      type_base = rel_name

    # Primary: find is_rel2 match, lenient first-match (the core-2026-06-03
    # behaviour).  The old coarse strict placeholder-only mode is retired.
    strict_id = None
    match = _find_is_rel2_match(result, rel_name, strict_id)
    remove_clause_idx = None
    if match:
      clause_idx, value_term, arg_term, ctxt = match
      remove_clause_idx = clause_idx
    else:
      # Fallback: find have + isa match
      have_match = _find_have_isa_match(result, type_base)
      if have_match:
        value_term, arg_term, ctxt = have_match
      else:
        continue  # No matching pattern found — skip this definite

    # Construct $theof1 function term
    if ctxt is not None:
      fn_term = ["$theof1", type_base, arg_term, ctxt]
    else:
      fn_term = ["$theof1", type_base, arg_term]

    # Deep-replace value_term with fn_term throughout all clauses
    for obj in result:
      if "@logic" in obj:
        obj["@logic"] = _deep_replace(obj["@logic"], value_term, fn_term)
      if "@question" in obj:
        obj["@question"] = _deep_replace(obj["@question"], value_term, fn_term)

    # Remove the is_rel2 clause (now derivable from bridge axioms)
    if remove_clause_idx is not None:
      # Re-find it since indices may have shifted — match by content
      for i, obj in enumerate(result):
        if not isinstance(obj, dict) or "@logic" not in obj:
          continue
        clause = obj["@logic"]
        atoms = _clause_atoms(clause)
        has_is_rel2 = any(
          isinstance(a, list) and len(a) >= 4
          and a[0] == "is rel2" and a[1] == rel_name
          for a in atoms
        )
        if has_is_rel2:
          result.pop(i)
          break

    # Emit the grounded possession fact have(arg, fn_term, ctxt). The
    # matching is_rel2 fact was just consumed/removed, and the universal
    # have bridge formerly in axioms_std.js (removed because it generated
    # free-variable wh-answers) no longer fills the gap — so we explicitly
    # assert this grounded fact. Needed whenever arg_term is concrete
    # (e.g. "Mary 3") so "Mary had a brother?" resolves via a concrete have.
    if arg_term is not None:
      have_atom = ["have", arg_term, fn_term]
      if ctxt is not None:
        have_atom.append(list(ctxt) if isinstance(ctxt, list) else ctxt)
      result.append({"@name": "frm_theof", "@logic": have_atom})

    # Record for bridge axiom generation
    theof_relations.add((rel_name, type_base))


# ======== $measure_of / $measure canonical rewriting ========

# Unit → (canonical_unit, multiplier)
_UNIT_CONVERSIONS = {
  # Length → meter
  "kilometer":  ("meter", 1000),
  "km":         ("meter", 1000),
  "centimeter": ("meter", 0.01),
  "cm":         ("meter", 0.01),
  "millimeter": ("meter", 0.001),
  "mm":         ("meter", 0.001),
  "meter":      ("meter", 1),
  "m":          ("meter", 1),
  "mile":       ("meter", 1609),
  "foot":       ("meter", 0.3048),
  "feet":       ("meter", 0.3048),
  "inch":       ("meter", 0.0254),
  "yard":       ("meter", 0.9144),
  # Mass → kilogram
  "kilogram":   ("kilogram", 1),
  "kg":         ("kilogram", 1),
  "gram":       ("kilogram", 0.001),
  "g":          ("kilogram", 0.001),
  "milligram":  ("kilogram", 0.000001),
  "mg":         ("kilogram", 0.000001),
  "ton":        ("kilogram", 1000),
  "tonne":      ("kilogram", 1000),
  "pound":      ("kilogram", 0.4536),
  "ounce":      ("kilogram", 0.02835),
  # Time → second
  "second":     ("second", 1),
  "minute":     ("second", 60),
  "hour":       ("second", 3600),
  "day":        ("second", 86400),
  # Volume → liter
  "liter":      ("liter", 1),
  "litre":      ("liter", 1),
  "milliliter": ("liter", 0.001),
  "ml":         ("liter", 0.001),
  "gallon":     ("liter", 3.785),
}


def _convert_to_canonical(number, unit):
  """Convert (80, 'kilometer') → (80000, 'meter') or None."""
  conv = _UNIT_CONVERSIONS.get(unit.lower() if isinstance(unit, str) else unit)
  if conv is None:
    return None
  canonical_unit, multiplier = conv
  return (round(number * multiplier), canonical_unit)


def _canonicalize_measure(term):
  """Convert ["$measure", NUM, UNIT] → ["$list", CANON_NUM, "#:CANON_UNIT"].

  If NUM is a numeric literal, the value is converted to canonical units
  (e.g. (80, kilometer) → (80000, meter)).

  If NUM is a variable (e.g. "X" pre-clausification or "?:X" after), the
  $measure wrapper is dropped entirely and the bare variable is returned.
  Rationale: in question-side encodings like
    ["=", $measure_of(...), $measure("?:X", "kilometer")]
  some LLMs (claude/deepseek) put the variable inside $measure's number
  slot. Rewriting to ["$list", "?:X", "#:meter"] would unify against an
  assertion's $list(80000, "#:meter") with ?:X bound to just the number
  80000 — losing the unit when rendered. Returning bare "?:X" instead
  yields the same shape gemini emits ("=", $measure_of(...), "X"), so the
  variable binds to the assertion's full $list term and the renderer can
  show "80000 meters" → "80 kilometers" via _normalize_measure.

  Unknown units in the literal branch fall back to ["$list", NUM, "#:UNIT"]
  — preserves the number, prefixes the unit with #: for UNA.
  """
  if (not isinstance(term, list) or len(term) != 3
      or term[0] != "$measure"):
    return term
  number = term[1]
  unit = term[2]
  if isinstance(number, str):
    return number
  if not isinstance(number, (int, float)):
    return term
  converted = _convert_to_canonical(number, unit)
  if converted:
    canon_num, canon_unit = converted
    return ["$list", canon_num, "#:" + canon_unit]
  # Unknown unit: keep number, prefix unit with #:
  unit_str = unit if isinstance(unit, str) else str(unit)
  if not unit_str.startswith("#:"):
    unit_str = "#:" + unit_str
  return ["$list", round(number), unit_str]


def rewrite_measure_terms(result):
  """Convert $measure terms to canonical $list form throughout all clauses.

  Finds ["$measure", NUMBER, UNIT] anywhere in the clause list and replaces
  with ["$list", CANON_NUMBER, "#:CANON_UNIT"].

  Also collects $measure_of attributes for bridge axiom generation.
  Returns set of attribute names found in $measure_of terms.
  """
  measure_attrs = set()

  for obj in result:
    for key in ("@logic", "@question"):
      if key not in obj:
        continue
      obj[key] = _rewrite_measures_in_tree(obj[key], measure_attrs)

  return measure_attrs


def _is_measure_term(term):
  """Return True if term is a measurement: $measure_of, $measure, or $list with #: unit."""
  if not isinstance(term, list) or len(term) < 2:
    return False
  op = term[0]
  if op in ("$measure_of", "$measure"):
    return True
  if op == "$list" and len(term) == 3:
    unit = term[2]
    return isinstance(unit, str) and unit.startswith("#:")
  return False


# Comparison operators that should be rewritten to less_measure when
# both operands are measurement terms.
_MEASURE_LESS_OPS = frozenset({"<", "$less", "->=", "-$greatereq"})
_MEASURE_GREATER_OPS = frozenset({">", "$greater", "-<=", "-$lesseq"})
_MEASURE_LEQ_OPS = frozenset({"<=", "$lesseq", "->" , "-$greater"})
_MEASURE_GEQ_OPS = frozenset({">=", "$greatereq", "-<", "-$less"})


def _rewrite_measures_in_tree(tree, measure_attrs):
  """Recursively rewrite $measure terms, collect $measure_of attrs,
  and convert comparison operators on measures to less_measure."""
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None

  # Convert $measure to canonical $list
  if op == "$measure" and len(tree) == 3:
    return _canonicalize_measure(tree)

  # Collect $measure_of attributes; unwrap nested $theof1 in entity arg.
  # rewrite_definites may have replaced an entity ID inside $measure_of with
  # $theof1, e.g. $measure_of(price, $theof1(price, car_A, ...), w0).
  # Unwrap to $measure_of(price, car_A, w0).
  if op == "$measure_of" and len(tree) >= 3:
    attr = tree[1]
    if isinstance(attr, str):
      measure_attrs.add(attr)
    entity = tree[2]
    if (isinstance(entity, list) and len(entity) >= 3
        and entity[0] == "$theof1"):
      tree = list(tree)
      tree[2] = entity[2]

  # Rewrite comparison operators on measure terms to less_measure.
  # Must recurse into operands first so $measure is canonicalized.
  if op is not None and len(tree) == 3:
    if op in _MEASURE_LESS_OPS or op in _MEASURE_GREATER_OPS or \
       op in _MEASURE_LEQ_OPS or op in _MEASURE_GEQ_OPS:
      lhs = _rewrite_measures_in_tree(tree[1], measure_attrs)
      rhs = _rewrite_measures_in_tree(tree[2], measure_attrs)
      if _is_measure_term(lhs) or _is_measure_term(rhs):
        if op in _MEASURE_LESS_OPS:
          # A < B  →  less_measure(A, B)
          return ["less_measure", lhs, rhs]
        if op in _MEASURE_GREATER_OPS:
          # A > B  →  less_measure(B, A)
          return ["less_measure", rhs, lhs]
        if op in _MEASURE_LEQ_OPS:
          # A <= B  →  not(less_measure(B, A))
          return ["not", ["less_measure", rhs, lhs]]
        if op in _MEASURE_GEQ_OPS:
          # A >= B  →  not(less_measure(A, B))
          return ["not", ["less_measure", lhs, rhs]]

  # Recurse
  return [_rewrite_measures_in_tree(el, measure_attrs)
          if isinstance(el, list) else el
          for el in tree]
