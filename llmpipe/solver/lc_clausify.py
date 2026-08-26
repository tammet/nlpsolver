# FOL-to-CNF clausification for the llm-based nlpsolver.
#
# Contains the core logical transformation pipeline used by logconvert.py:
#   clausify(formula)  -- main entry point: formula -> list of GK clauses
#
# Also exports shared constants and looks_like_var which are used by
# lc_questions.py and logconvert.py.
#
# Module-level counters reset by logconvert.rawlogic_convert():
#   _skolem_nr  -- Skolem function/constant numbering
#   _gobj_nr    -- generic-object expansion variable numbering
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

from globals import options as _g_options


# Logical connectives that are NOT predicates.
connectives = {"and", "or", "not", "implies", "equivalent", "xor", "forall", "exists"}

# Opaque wrappers: clausification does not recurse inside these.
# Variable renaming (outer varmap) is still applied to their contents.
_opaque_wrappers = {"normally", "-normally"}

# Predicates whose second positional argument (index 2) is an "object" entity
# that the LLM may express as a bare plural type name like "berries" or "carrots".
# These need expansion to a fresh variable + isa constraint so that the prover
# can match them against specific instances.
_GENERIC_OBJ_PREDS = frozenset({
  "has target", "has location", "has direction", "has instrument",
  "has destination", "has recipient", "has source",
  "has beneficiary", "has accompaniment", "has path", "has result",
  "has topic", "has cause",
})

# Bare type name: all lowercase letters (no digits, no uppercase, no suffix number).
_BARE_TYPE_RE = re.compile(r'^[a-z][a-z]*$')

# Skolem name pattern: matches sk0 (old/untyped), sk0_house (typed constant),
# sk0 in ["sk0", "?:X"] (function).
_SKOLEM_RE = re.compile(r'^sk\d+(_\w+)?$')

def is_skolem_const(val):
  """True if val is a Skolem constant string like 'sk0' or 'sk0_house'."""
  return isinstance(val, str) and _SKOLEM_RE.match(val) is not None

def is_skolem_fn(val):
  """True if val is a Skolem function term like ['sk0', '?:X']."""
  return (isinstance(val, list) and val
          and isinstance(val[0], str) and _SKOLEM_RE.match(val[0]) is not None)

def skolem_type_from_name(name):
  """Extract type from typed Skolem name. 'sk0_house' → 'house', 'sk0' → None."""
  if not isinstance(name, str):
    return None
  m = _SKOLEM_RE.match(name)
  if not m:
    return None
  suffix = m.group(1)  # '_house' or None
  if suffix:
    return suffix[1:]  # strip leading '_'
  return None

# Counter for Skolem function/constant names (reset per top-level call).
_skolem_nr = 0

# Counter for fresh variables introduced by _expand_generic_objects (reset per top-level call).
_gobj_nr = 0


# ======== variable detection ========

def is_world_constant(s):
  """Return True if s is a world state constant (W0, W1, W2, ...)."""
  return isinstance(s, str) and bool(re.match(r'^W\d+$', s))


def looks_like_var(s):
  """Return True if s looks like a stage-2 variable name (e.g. X, Y, S1).

  This is the pipeline's authoritative test for "is this token a Stage-2
  variable".  Every site that used to carry its own uppercase pattern calls
  it or its `broad` sibling below, so the world-constant exclusion holds
  everywhere: `lc_reference._free_vars`, `lc_rewrites._is_stage2_var`,
  `lc_questions._to_gk_var`.  A site that has the syntax tree should prefer
  the enclosing binders (forall/exists/ask) and use this only for tokens no
  binder explains.

  Variables in stage-2 LLM output are a single uppercase letter optionally
  followed by digits: X, Y, Z, E, S, W, S1, S2, X1.  Strings starting
  with '?:' are already in GK format and also count as variables.

  World state constants (W0, W1, ...) are NOT variables.
  Multi-letter capitalized words (English, French, German, Buddhist …) are
  proper-noun constants, not variables, and must NOT match.
  """
  if not isinstance(s, str) or ' ' in s:
    return False
  if s.startswith('?:'):
    return True
  if is_world_constant(s):
    return False
  return bool(re.match(r'^[A-Z][0-9]*$', s))


def looks_like_var_broad(s):
  """`looks_like_var`, widened to multi-letter names such as `Entity`.

  Stage 2 sometimes names a variable with a word (`Entity`, `Person`), and
  `lc_questions` converts those to GK variables.  The breadth is the only
  difference: a world constant is not a variable under either test, which is
  the whole point of routing both through one place.
  """
  if not isinstance(s, str) or ' ' in s:
    return False
  if s.startswith('?:'):
    return True
  if is_world_constant(s):
    return False
  return bool(re.match(r'^[A-Z][A-Za-z0-9_]*$', s))


# ======== pre-clausification normalization passes ========

def _singularize(word):
  """Very basic English singularization (plural → singular type name)."""
  if word.endswith("ies") and len(word) > 3:
    return word[:-3] + "y"          # berries→berry, activities→activity
  if word.endswith("ses") and len(word) > 3:
    return word[:-2]                # buses→bus
  if word.endswith("xes") and len(word) > 3:
    return word[:-2]                # foxes→fox
  if word.endswith("ches") and len(word) > 4:
    return word[:-2]                # matches→match
  if word.endswith("shes") and len(word) > 4:
    return word[:-2]                # wishes→wish
  if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
    return word[:-1]                # carrots→carrot, bears→bear
  return word


# Class names whose plural-looking form is singular or a distinct sense; do
# NOT strip the trailing 's' when singularizing isa class names.  (Prototype
# list — extend as real cases appear.)  The `-us` / `-is` / `-ss` / `-es` /
# `-cs` suffix guards below catch the regular latinate/non-plural and `-es`/
# `-cs` cases (bus, analysis, class, series, physics, potatoes); this set is
# for the irregulars they miss.
_SINGULARIZE_EXCEPTIONS = frozenset({
  "news", "means", "scissors", "pants", "trousers", "stairs", "goods",
  "lens", "pyjamas", "pajamas",
  # singular nouns ending in -ies, which the -ies -> -y rule would mangle
  "series", "species", "rabies", "caries",
})


def _safe_singularize_class(cls):
  """Singularize a class name for isa-class normalization, skipping forms the
  crude trailing-'s' heuristic would mangle: proper nouns (capitalized, e.g.
  "Paris"), latinate/non-plural `-us` / `-is` / `-ss` endings (bus, analysis,
  class), and a small irregular/mass-noun exception set.  Multi-word classes
  are gated on their head (last) word."""
  if not isinstance(cls, str) or not cls:
    return cls
  if cls in _SINGULARIZE_EXCEPTIONS:
    return cls
  if cls[:1].isupper():
    return cls                      # proper noun — leave intact
  head = cls.rsplit(" ", 1)[-1]     # last word carries the number
  if head in _SINGULARIZE_EXCEPTIONS:
    return cls
  if len(head) < 2:
    # a one-letter head ("person s", from the entity name "person S 4") would
    # lose its only letter and leave a token ending in a space, which then
    # never unifies with anything (held-out MLE 964, 965).
    return cls
  if head.endswith("ies") and len(head) > 4:
    # berries -> berry, activities -> activity: the -ies rule is safe for
    # every -ies plural; the singular -ies nouns (series, species, rabies,
    # caries) are caught by the exception set above.  This must precede the
    # -es guard below, which would otherwise leave "berries" plural (core
    # 1477).
    return _singularize(cls)
  if head.endswith(("us", "is", "ss", "es", "cs")):
    # bus / virus / analysis / class / potatoes / physics / roses — the crude
    # trailing-'s' strip mangles these (and "-es" needs proper -e/-o handling),
    # so leave them intact.
    return cls
  return _singularize(cls)


def singularize_isa_classes_in_node(node):
  """Recursively normalize the CLASS argument (index 1) of every `isa` / `-isa`
  atom to its singular form, so a bare-plural generic (`isa("animals", X)`)
  unifies with the singular form used elsewhere and with the injected
  population witness `isa("animal", $some_animal)`.  Leaves all other
  predicates and arguments untouched.

  `noclassnumbernorm_flag` turns the whole pass off.  The open-relation graph
  theory (`solver/graph_compile.py`) needs it off: there two class names that
  differ by a trailing `s` are two names, and a rule that connects them has to
  be a named clause the proof can show."""
  if not isinstance(node, list) or not node:
    return node
  if _g_options.get("noclassnumbernorm_flag", False):
    return node
  head = node[0]
  if (isinstance(head, str) and head in ("isa", "-isa")
      and len(node) >= 2 and isinstance(node[1], str)):
    cls = node[1] if (not _g_options.get("nofix_boundtypevars")
                      and looks_like_var(node[1])) else _safe_singularize_class(node[1])
    return [head, cls] + [
      singularize_isa_classes_in_node(x) for x in node[2:]]
  return [singularize_isa_classes_in_node(x) if isinstance(x, list) else x
          for x in node]


def singularize_role_values_in_node(node):
  """(singrole, a `fallback_norm` switch) Singularize bare plural noun string values inside
  ["eventprop", $role, VALUE] tags, so a rule consequent's role value
  ("promotions") unifies with the question's ("promotion").  Constants that are
  variables, meta tokens, skolems, entity constants (#:) or capitalized names
  are untouched."""
  if not isinstance(node, list) or not node:
    return node
  if (len(node) == 3 and node[0] == "eventprop" and isinstance(node[2], str)
      and node[2] and not node[2].startswith(("?", "$", "#", "sk"))
      and node[2][:1].islower()):
    return [node[0], node[1], _safe_singularize_class(node[2])]
  return [singularize_role_values_in_node(x) if isinstance(x, list) else x
          for x in node]


def lower_isa_classes_in_node(node):
  """Recursively lower-case the CLASS argument (index 1) of every `isa` / `-isa`
  atom, so capitalization variants of the same category ("American national" vs
  "american national") unify.  Only arg 1 (the class/type) is touched; the
  entity instance (arg 2) and every other position keep their case.  (Used under
  -typeenrich, where FOLIO's mixed-case nationality/proper-adjective classes
  otherwise split into distinct predicates.)"""
  if not isinstance(node, list) or not node:
    return node
  head = node[0]
  if (isinstance(head, str) and head in ("isa", "-isa")
      and len(node) >= 2 and isinstance(node[1], str)):
    cls = node[1] if (not _g_options.get("nofix_boundtypevars")
                      and looks_like_var(node[1])) else node[1].lower()
    return [head, cls] + [
      lower_isa_classes_in_node(x) for x in node[2:]]
  return [lower_isa_classes_in_node(x) if isinstance(x, list) else x
          for x in node]


def _expand_generic_objects(frm):
  """Replace bare plural type names in object positions with fresh vars + isa.

  Transforms ["has target", event, "berries"] into:
    ["exists", "Gobj1", ["and", ["isa", "berry", "Gobj1"],
                                ["has target", event, "Gobj1"]]]

  This allows the prover to unify the generic type name with specific instances
  (e.g. sk0 where isa(berry, sk0)) via the isa constraint.  Recurses into all
  sub-formulas.
  """
  global _gobj_nr
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op in _GENERIC_OBJ_PREDS and len(frm) >= 3:
    obj = frm[2]
    if isinstance(obj, str) and _BARE_TYPE_RE.match(obj):
      # `_safe_singularize_class`, not the raw `_singularize`: the crude
      # trailing-'s' strip turns "roses" into "ros" and no premise then
      # unifies with it (FOLIO 166).  The safe form leaves the endings it
      # cannot handle intact.
      sing = _safe_singularize_class(obj)
      var  = "Gobj" + str(_gobj_nr)
      _gobj_nr += 1
      rest = [frm[0], frm[1], var] + list(frm[3:])
      return ["exists", var, ["and", ["isa", sing, var], rest]]
  # Recurse into sub-formulas (connectives, quantifiers, wrappers)
  if isinstance(op, str) and op in (connectives | _opaque_wrappers):
    return [op] + [_expand_generic_objects(el) for el in frm[1:]]
  return frm


def _strip_typical_from_antecedent(frm):
  """Remove ["typical", ...] atoms from conjunctions in implies-antecedents.

  The LLM adds typical(E) to activity descriptions in conditional antecedents
  (e.g. "if X eats berries" → exists E. isa(activity,E) ∧ typical(E) ∧ ...).
  Specific events never carry typical, so the conditional never fires.
  Strip typical from the antecedent only — it's a valid guard in consequents.

  Exception: §5.12 object-exclusivity rules of the exact shape
    implies(and(... has_target(E,V) ... typical(E) ...), isa(TYPE, V))
  preserve typical, since the rule body needs it to unify with habitual
  queries.  Detection is narrow: consequent must be a bare isa atom and
  its second-arg variable must appear in the antecedent's has_target slot.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op == "implies" and len(frm) == 3:
    if _is_object_exclusivity_shape(frm[1], frm[2]):
      ant = frm[1]
    else:
      ant = _drop_typical_conjuncts(frm[1])
    con = _strip_typical_from_antecedent(frm[2])
    return [op, ant, con]
  if op in connectives or op in _opaque_wrappers:
    return [op] + [_strip_typical_from_antecedent(el) for el in frm[1:]]
  return frm


def _is_object_exclusivity_shape(ant, con):
  """True if (ant, con) matches §5.12 object-exclusivity:
    consequent is a bare ["isa", TYPE, V] atom, and V appears as the
    second arg of ["has target", E, V] within the antecedent.
  """
  if (not isinstance(con, list) or len(con) != 3 or con[0] != "isa"
      or not isinstance(con[2], str)):
    return False
  v = con[2]
  if not isinstance(ant, list) or not ant or ant[0] != "and":
    return False
  for conj in ant[1:]:
    if (isinstance(conj, list) and len(conj) >= 3
        and conj[0] == "has target" and conj[2] == v):
      return True
  return False


def _drop_typical_conjuncts(frm):
  """Recursively remove ["typical", ...] atoms from "and" conjunctions.

  Only drops typical when it is one conjunct among others.  A standalone
  ["typical", ...] that is the entire antecedent is left unchanged.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op == "and":
    kept = []
    for el in frm[1:]:
      if isinstance(el, list) and el and el[0] == "typical":
        continue      # drop typical conjunct
      kept.append(_drop_typical_conjuncts(el))
    if len(kept) == 1:
      return kept[0]
    if not kept:
      return frm    # nothing left — leave original to avoid empty formula
    return ["and"] + kept
  if op in ("exists", "forall") and len(frm) == 3:
    return [op, frm[1], _drop_typical_conjuncts(frm[2])]
  return frm


def _normalize_type_case(frm, bound=None):
  """Lowercase the type-name argument in 'isa' atoms throughout a formula.

  The LLM sometimes capitalises type names in certain sentences (e.g. "Baby bird"
  from "Baby birds do not fly") while lowercasing them in others ("baby bird"
  from "John is a baby bird").  Normalising to lowercase ensures consistent
  unification inside the prover.
  Only the CLASS argument (frm[1]) of an 'isa' or '-isa' atom is lowercased;
  entity constants (frm[2]) keep their original casing.
  """
  if bound is None:
    bound = set()
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op in ("forall", "exists", "ask") and len(frm) >= 3 \
     and isinstance(frm[1], str):
    return [op, frm[1], _normalize_type_case(frm[2], bound | {frm[1]})] + [
      _normalize_type_case(a, bound) if isinstance(a, list) else a
      for a in frm[3:]]
  if op in ("isa", "-isa") and len(frm) >= 2 and isinstance(frm[1], str):
    protect = (not _g_options.get("nofix_boundtypevars") and frm[1] in bound)
    return [op, frm[1] if protect else frm[1].lower()] + [
      _normalize_type_case(a, bound) for a in frm[2:]]
  if isinstance(op, str):
    return [op] + [_normalize_type_case(el, bound) for el in frm[1:]]
  return frm


def _normalize_quantifiers(frm):
  """Normalize multi-body quantifiers into standard 3-element form.

  LLMs sometimes generate ["exists","X",f1,f2,...] without an explicit "and"
  wrapper.  Convert these to ["exists","X",["and",f1,f2,...]] so the rest of
  the pipeline can assume the standard 3-element ["exists", var, body] form.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op in ("exists", "forall"):
    if len(frm) > 3:
      body = ["and"] + [_normalize_quantifiers(f) for f in frm[2:]]
      return [op, frm[1], body]
    if len(frm) == 3:
      return [op, frm[1], _normalize_quantifiers(frm[2])]
    return frm
  if op in connectives:
    return [op] + [_normalize_quantifiers(el) for el in frm[1:]]
  return frm


# ======== main clausification entry point ========

def _strip_time_defensively(frm):
  """Strip any @time wrappers that survived into clausification (safety net).

  Normally @time is stripped by logconvert before clausification.  If any
  leak through, discard the wrapper and keep the body.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  if frm[0] == "@time" and len(frm) == 3:
    return _strip_time_defensively(frm[2])
  return [_strip_time_defensively(el) for el in frm]


def clausify(formula):
  """Convert a formula to a list of GK clauses (CNF).

  Returns a list of clauses, where each clause is either:
    - a single atom: ["pred", arg, ...]
    - a list of atoms (disjunction): [["pred1",...], ["pred2",...], ...]
  """
  # Defensive: strip any @time wrappers that survived to clausification.
  formula = _strip_time_defensively(formula)
  # Normalise type-name casing in isa/−isa atoms (LLM may capitalise inconsistently).
  fn = _normalize_type_case(formula)
  # Strip typical() from implies-antecedents (LLM adds it even in conditionals
  # where it shouldn't be required, causing rules to miss specific events).
  fa = _strip_typical_from_antecedent(fn)
  # Expand bare plural type names in object positions to fresh vars + isa.
  fe = _expand_generic_objects(fa)
  f0 = _normalize_quantifiers(fe)
  f1 = _implies_to_or(f0)
  f2 = _push_neg(f1, True)
  # Pass 1: push normally(...) inside exists/and until it wraps a single atom.
  f3 = _expand_normally(f2)
  f4 = _skolemize(f3, [], {})
  f4b = _strip_forall(f4)
  f5 = _distribute(f4b)
  # Pass 2: expand normally(atom) -> $block now that clauses are flat and
  # Skolem terms have replaced existential variables.
  f6 = _expand_normally(f5)
  return _extract_clauses(f6)


# ======== connective elimination ========

def _implies_to_or(frm):
  """Eliminate non-primitive connectives, recursively.

  Transformations applied (does not recurse inside opaque wrappers):
    implies(A,B)    -> or(not(A), B)
    equivalent(A,B) -> and(implies(A,B), implies(B,A))  then recurse
    xor(A,B)        -> and(or(A,B), or(not(A),not(B)))
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]

  if op in _opaque_wrappers:
    return frm  # opaque: keep as-is

  if op == "implies":
    if len(frm) == 3:
      a = _implies_to_or(frm[1])
      b = _implies_to_or(frm[2])
      return ["or", ["not", a], b]
    return frm

  if op == "equivalent":
    # equivalent(A,B) = (A=>B) and (B=>A); expand then recurse so implies gets eliminated too
    if len(frm) == 3:
      a = frm[1]
      b = frm[2]
      return _implies_to_or(["and", ["implies", a, b], ["implies", b, a]])
    return frm

  if op == "xor":
    # xor(A,B) = (A or B) and (not(A) or not(B))
    if len(frm) == 3:
      a = _implies_to_or(frm[1])
      b = _implies_to_or(frm[2])
      return ["and", ["or", a, b], ["or", ["not", a], ["not", b]]]
    return frm

  if op in ("and", "or", "not"):
    return [op] + [_implies_to_or(el) for el in frm[1:]]

  if op in ("forall", "exists"):
    # frm[1] is the variable name (string), frm[2] is the body
    return [op, frm[1], _implies_to_or(frm[2])]

  # Atomic formula — no subformulas
  return frm


# ======== NNF push ========

def _push_neg(frm, pos):
  """Push negation inside to reach NNF.
  pos=True means the current context is positive (no enclosing negation).
  'normally' and similar wrappers are treated as opaque atoms.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]

  if op in _opaque_wrappers:
    # Negate the wrapper name if needed, but don't recurse inside.
    if not pos:
      neg_op = op[1:] if op.startswith("-") else "-" + op
      return [neg_op] + frm[1:]
    return frm

  if op in ("forall", "exists"):
    new_op = op
    if not pos:
      new_op = "exists" if op == "forall" else "forall"
    return [new_op, frm[1], _push_neg(frm[2], pos)]

  if op in ("and", "or"):
    new_op = op
    if not pos:
      new_op = "or" if op == "and" else "and"
    return [new_op] + [_push_neg(el, pos) for el in frm[1:]]

  if op == "not":
    return _push_neg(frm[1], not pos)

  # Atomic formula
  if pos:
    return frm
  # Negate by toggling "-" prefix on predicate name
  pred = op
  if isinstance(pred, str):
    if pred.startswith("-"):
      return [pred[1:]] + frm[1:]
    else:
      return ["-" + pred] + frm[1:]
  return frm


# ======== normally expansion ========

def _forall_to_freevars(frm):
  """Expand ["forall", var, body] into a flat list of GK literals.

  Treats var as a free (implicitly universally quantified) GK variable "?:var".
  Recursively flattens nested foralls (from negated nested existentials in
  antecedents): ∀E(∀Y f(E,Y) ∨ g(E)) becomes [f(?:E,?:Y), g(?:E)].
  """
  if not (isinstance(frm, list) and len(frm) == 3 and frm[0] == "forall"):
    return [frm]
  var  = frm[1]
  body = frm[2]
  gk_var = var if var.startswith("?:") else "?:" + var
  # Substitute var -> gk_var throughout body
  body_renamed = apply_varmap(body, {var: gk_var})
  if isinstance(body_renamed, list) and body_renamed and body_renamed[0] == "or":
    lits = list(body_renamed[1:])
  else:
    lits = [body_renamed]
  # Recursively flatten any nested forall children.
  result = []
  for lit in lits:
    if isinstance(lit, list) and lit and lit[0] == "forall":
      result.extend(_forall_to_freevars(lit))
    else:
      result.append(lit)
  return result


def _extract_subject_class(frm):
  """Extract the subject class from a rule antecedent.

  Looks for the first isa(CLASS, VAR) atom in the formula tree,
  searching through and/exists wrappers.  Returns the class name
  string, or None if not found.
  """
  if not isinstance(frm, list) or not frm:
    return None
  op = frm[0]
  if op == "isa" and len(frm) >= 3:
    return str(frm[1])
  if op == "and":
    for el in frm[1:]:
      cls = _extract_subject_class(el)
      if cls:
        return cls
  if op == "exists" and len(frm) >= 3:
    return _extract_subject_class(frm[2])
  return None


def _push_normally_inside(frm, blocker_class=None):
  """Push normally inward through implies/exists/and until it wraps a single atom.

  Called from _expand_normally (pass 1) when normally wraps a complex body.

    normally(implies(A, B))    -> implies(A, _push_normally_inside(B))
    normally(exists var, body) -> exists var, _push_normally_inside(body)
    normally(and(A1,...,An))   -> and(A1,...,An-1, normally(An))
    normally(atom)             -> normally(atom)  [base case]

  The result is passed to _skolemize, which eliminates the exists and
  substitutes Skolem terms.  The remaining normally(atom) wrappers are
  then expanded into $block clauses by _expand_normally pass 2.

  blocker_class: if provided, tags the resulting normally(atom, CLASS) so
  that pass 2 can use the correct subject class in the $block priority
  instead of relying on the last -isa heuristic.
  """
  if not isinstance(frm, list) or not frm:
    tag = ["normally", frm, blocker_class] if blocker_class else ["normally", frm]
    return tag
  op = frm[0]
  # Length guards: a malformed binder/implication from the LLM (e.g.
  # deepseek dropping a rule's consequent -> ["implies", ANTECEDENT] with no
  # consequent, case 1418) must NOT crash on frm[2]; it falls through to the
  # default wrap below and is treated as an opaque atom.
  if op == "implies" and len(frm) >= 3:
    # normally(A -> B) -> A -> normally(B)  (recursively into consequent)
    # Extract subject class from the antecedent before pushing deeper.
    if blocker_class is None:
      blocker_class = _extract_subject_class(frm[1])
    return ["implies", frm[1], _push_normally_inside(frm[2], blocker_class)]
  if op == "exists" and len(frm) >= 3:
    return ["exists", frm[1], _push_normally_inside(frm[2], blocker_class)]
  if op == "forall" and len(frm) >= 3:
    return ["forall", frm[1], _push_normally_inside(frm[2], blocker_class)]
  if op == "and":
    if len(frm) > 2:
      # and(A1,...,An) -> and(A1,...,An-1, push_normally(An))
      return ["and"] + list(frm[1:-1]) + [_push_normally_inside(frm[-1], blocker_class)]
    if len(frm) == 2:
      # and(A1) -> push_normally(A1)
      return _push_normally_inside(frm[1], blocker_class)
  # Atom or other: wrap with normally (and optional class tag)
  tag = ["normally", frm, blocker_class] if blocker_class else ["normally", frm]
  return tag


# ---- helpers shared by _expand_normally and _distribute ----

def _flatten_or_elements(elements):
  """Flatten nested 'or' wrappers in a list of formula elements."""
  flat = []
  for el in elements:
    if isinstance(el, list) and el and el[0] == "or":
      flat.extend(el[1:])
    else:
      flat.append(el)
  return flat


def _classify_literals(lits):
  """Split literals into (neg_lits, pos_lits) by predicate polarity."""
  neg = [l for l in lits
         if isinstance(l, list) and l and
         isinstance(l[0], str) and l[0].startswith("-")]
  pos = [l for l in lits
         if not (isinstance(l, list) and l and
                 isinstance(l[0], str) and l[0].startswith("-"))]
  return neg, pos


def _extract_isa_priority(neg_lits, blocker_class_tag, extra_neg=None):
  """Compute $block priority from negative literals and optional class tag.

  Returns (cls, priority) where:
    cls      = class string for the $block priority
    priority = ["$", cls, N] with N = (non-isa negative conditions) + 1

  extra_neg: optional additional negative literals to search for -isa
             (e.g. regular_lits + pushed_lits for negative-head rules).
  """
  isa_conds   = [l for l in neg_lits if isinstance(l, list) and l and l[0] == "-isa"]
  non_isa_neg = [l for l in neg_lits if not (isinstance(l, list) and l and l[0] == "-isa")]
  priornr = len(non_isa_neg) + 1
  if blocker_class_tag:
    cls = blocker_class_tag
  elif extra_neg is not None:
    # Prefer -isa from extra_neg (subject class) over existential constraints.
    isa_from_extra = [l for l in extra_neg
                      if isinstance(l, list) and l and l[0] == "-isa"]
    if isa_from_extra and len(isa_from_extra[-1]) >= 2:
      cls = str(isa_from_extra[-1][1])
    elif isa_conds and len(isa_conds[-1]) >= 2:
      cls = str(isa_conds[-1][1])
    else:
      cls = "$generic"
  elif isa_conds and len(isa_conds[-1]) >= 2:
    cls = str(isa_conds[-1][1])
  else:
    cls = "$generic"
  return cls, ["$", cls, priornr]


def _expand_normally(frm):
  """Expand normally(...) wrappers into defeasible clauses with $block atoms.

  Called twice in clausify:
    Pass 1 (before _skolemize): pushes normally inside complex bodies
      (exists / and) so that after Skolemization each normally wraps a
      single concrete atom.
    Pass 2 (after _distribute): expands normally(atom) into $block clauses.

  The body inside normally is still in raw stage-2 form (not NNF) when
  encountered in pass 1, so _implies_to_or and _push_neg are applied first.

  If options["noexceptions_flag"] is True, strips normally without blockers.

  For each clause (or-disjunction) that contains normally(atom):
    - Classifies literals: negative conditions (start with "-") vs positive heads.
    - Uses the last positive literal as the head (the conclusion to be blocked).
    - Builds priority ["$", CLASS, N] where CLASS is the class from the last
      -isa condition (or "$generic"), and N = len(non-isa conditions) + 1.
    - Returns the clause with ["$block", priority, ["$not", head]] appended.

  A lone normally(body) not inside an or is normalised to a 1-element
  disjunction before processing.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]

  if op == "and":
    return ["and"] + [_expand_normally(el) for el in frm[1:]]

  if op in ("forall", "exists"):
    return [op, frm[1], _expand_normally(frm[2])]

  if op in _opaque_wrappers or op == "or":
    # Normalise: a lone normally(...) is treated as a one-element disjunction.
    elements_raw = [frm] if op in _opaque_wrappers else frm[1:]
    elements = _flatten_or_elements(elements_raw)

    # Separate normally-wrappers from regular literals.
    regular_lits = []
    pushed_lits  = []  # from _push_normally_inside; must NOT be re-expanded here
    body_lits    = []  # literals extracted from normally-body formulas
    normally_disjunctive = False  # True when normally body was an "or"
    blocker_class_tag = None      # subject class from _push_normally_inside tag

    for el in elements:
      if isinstance(el, list) and el and el[0] in _opaque_wrappers:
        body = el[1] if len(el) >= 2 else None
        if body is None:
          continue
        is_pos = not el[0].startswith("-")
        # Tagged blocker class from _push_normally_inside (pass 1).
        if len(el) >= 3 and isinstance(el[2], str) and blocker_class_tag is None:
          blocker_class_tag = el[2]
        # Push normally inside the raw body BEFORE implies-to-or / NNF.
        # This rewrites normally(implies(A,B)) → implies(A, normally(B)),
        # normally(exists(V, B)) → exists(V, ...), normally(and(...)) → and(...),
        # recursively until normally wraps only atoms.  The result no longer has
        # normally around any complex structure, so _implies_to_or / _push_neg
        # can then safely transform the antecedent (preserving exists, etc.).
        # The result goes into pushed_lits (not regular_lits) so it is NOT
        # re-expanded in pass 1.  The remaining normally(atom) wrappers will be
        # expanded into $block clauses by pass 2 after Skolemization.
        if is_pos and isinstance(body, list) and body and body[0] in ("implies", "exists", "and"):
          pushed = _push_normally_inside(body)
          converted = _push_neg(_implies_to_or(pushed), True)
          pushed_lits.append(converted)
          continue
        # Check whether the raw body is a genuine disjunction (not an implies
        # that will become an or after conversion).  Only a raw "or" body means
        # the normally wrapped a true disjunction — skip $block for those.
        if (isinstance(body, list) and body and body[0] == "or"):
          normally_disjunctive = True
        # Process body: implies elimination then NNF push.
        processed = _push_neg(_implies_to_or(body), is_pos)
        # Flatten processed body into a flat list of literals.
        # _push_neg may produce nested ors (e.g. from de Morgan on conjunctive
        # conditions), so flatten one level before collecting.
        if isinstance(processed, list) and processed and processed[0] == "or":
          for lit in processed[1:]:
            if isinstance(lit, list) and lit and lit[0] == "or":
              body_lits.extend(lit[1:])   # one-level flatten of nested or
            elif isinstance(lit, list) and lit and lit[0] == "forall":
              # Expand ∀Y body(Y) as free-variable literals.
              # Justification: (∀Y f(Y)) ∨ (∀Z g(Z)) ≡ ∀Y∀Z(f(Y) ∨ g(Z)),
              # so treating Y and Z as implicitly-universally-quantified free
              # variables in GK gives exactly the right semantics.
              # This arises from xor's exclusivity constraint:
              # ¬∃Y P(Y) ∨ ¬∃Z Q(Z) (after push_neg) becomes
              # ∀Y¬P(Y) ∨ ∀Z¬Q(Z), which is safely flattened this way.
              body_lits.extend(_forall_to_freevars(lit))
            elif isinstance(lit, list) and lit and lit[0] == "and":
              # "and" in an or-child arises from de-Morgan on a disjunctive
              # antecedent: normally(implies(or(A1,A2), B)) → or(and(¬A1,¬A2), B).
              # These are conditions, not $block candidates — move to regular_lits
              # so they end up as clause conditions without triggering a pass-1 $block.
              regular_lits.extend(lit[1:])
            elif isinstance(lit, list) and lit and lit[0] == "exists":
              # "exists" in an or-child is the existential consequent of an implies.
              # Push normally inside so that after Skolemization the $block will
              # wrap a flat atom (handled in pass 2), not the whole exists formula.
              if is_pos:
                pushed_lits.append(_push_normally_inside(lit))
              else:
                body_lits.append(lit)
            else:
              body_lits.append(lit)
        elif isinstance(processed, list) and processed and processed[0] in ("and", "exists"):
          # Complex body (conjunction or existential): push normally inward so
          # that after Skolemization it wraps a single atom (pass 2 handles it).
          # Use pushed_lits (not regular_lits) to prevent pass-1 re-expansion of
          # the normally(atom) we just placed deep inside — it has no outer -isa
          # context yet and would generate a $block with wrong priority.
          if is_pos:
            pushed_lits.append(_push_normally_inside(processed))
          else:
            # -normally with complex body: expand as certain (negated).
            regular_lits.append(_expand_normally(processed))
        elif isinstance(processed, list) and processed and processed[0] == "forall":
          # normally(not(exists Y. P)) → push_neg → forall Y. not(P).
          # Expand ∀Y as free-variable literals; avoids Skolemization so all
          # conditions end up in a single clause (no Skolem companion split).
          if is_pos:
            body_lits.extend(_forall_to_freevars(processed))
          else:
            body_lits.append(processed)
        elif isinstance(processed, list) and processed:
          body_lits.append(processed)
        # else: empty body — skip
      else:
        regular_lits.append(el)

    # Recurse into regular literals (may contain nested normally, and/or, …).
    # pushed_lits are intentionally excluded from this recursion.
    regular_lits = [_expand_normally(el) for el in regular_lits]

    # Flatten forall elements in regular_lits into free-variable literals.
    # These arise from negated existentials in implies-antecedents
    # (not(exists(E,...)) → forall(E,...)) and must be flat for $block
    # classification to correctly identify them as negative conditions.
    flat_regular = []
    for lit in regular_lits:
      if isinstance(lit, list) and lit and lit[0] == "forall":
        flat_regular.extend(_forall_to_freevars(lit))
      else:
        flat_regular.append(lit)
    regular_lits = flat_regular

    all_lits = regular_lits + pushed_lits + body_lits
    if not all_lits:
      return frm

    # If no normally bodies were extracted (all were complex conjunctions or
    # pushed inside exists/and for pass 2), return as a plain or-clause.
    if not body_lits:
      if len(all_lits) == 1:
        return all_lits[0]
      return ["or"] + all_lits

    # Check noexceptions flag: treat normally as certain, no $block.
    if _g_options.get("noexceptions_flag", False):
      if len(all_lits) == 1:
        return all_lits[0]
      return ["or"] + all_lits

    # Classify literals: negative conditions vs positive heads.
    neg_lits, pos_lits = _classify_literals(all_lits)

    if not pos_lits:
      # All literals are negative — this is a negative-head normally rule
      # (produced by _negate_consequent before clausify).
      # Create a $block pointing to the POSITIVE form of the head so the
      # prover can restore it via an exception. No $not wrapper needed.
      if _g_options.get("noexceptions_flag", False) or not body_lits:
        if len(all_lits) == 1:
          return all_lits[0]
        return ["or"] + all_lits
      neg_head = body_lits[-1]
      if not (isinstance(neg_head, list) and neg_head
              and isinstance(neg_head[0], str) and neg_head[0].startswith("-")):
        # Not a clean negated literal; fall back to certain.
        if len(all_lits) == 1:
          return all_lits[0]
        return ["or"] + all_lits
      pos_form = [neg_head[0][1:]] + list(neg_head[1:])   # strip "-" prefix
      cond_lits = regular_lits + pushed_lits + body_lits[:-1]
      cls, priority = _extract_isa_priority(
          cond_lits, None, extra_neg=regular_lits + pushed_lits)
      blocker  = ["$block", priority, pos_form]   # no "$not" wrapper
      result_lits = cond_lits + [neg_head, blocker]
      if len(result_lits) == 1:
        return result_lits[0]
      return ["or"] + result_lits

    # Disjunctive normally body: normally(or(A, B)) should not get a $block
    # because there is no single head to defeat. Matches UDP behaviour where
    # make_clause_blockers returns None for clauses with multiple disjuncts.
    if normally_disjunctive:
      result_lits = neg_lits + pos_lits
      if len(result_lits) == 1:
        return result_lits[0]
      return ["or"] + result_lits

    # Use the last positive literal as the head (the conclusion to be blocked).
    head     = pos_lits[-1]

    # Compute priority: [$, CLASS, N]
    #   CLASS = subject class from tagged normally (if available), else from
    #   the last -isa condition, else "$generic".
    #   N     = (number of non-isa negative conditions) + 1.
    cls, priority = _extract_isa_priority(neg_lits, blocker_class_tag)
    blocker  = ["$block", priority, ["$not", head]]

    other_pos = [l for l in pos_lits if l is not head]
    result_lits = neg_lits + other_pos + [head, blocker]
    if len(result_lits) == 1:
      return result_lits[0]
    return ["or"] + result_lits

  # Atomic formula — no expansion needed.
  return frm


# ======== Skolemization ========

def _skolemize(frm, freevars, varmap):
  """Skolemize existential quantifiers; rename forall vars to ?:VAR.

  freevars: list of current free (universally quantified) ?:X variable names
  varmap:   dict mapping stage-2 var names (e.g. "X") to GK forms ("?:X")

  After skolemization, forall quantifiers are eliminated (var renamed to ?:X,
  quantifier wrapper dropped). Exists quantifiers are eliminated by
  substituting the variable with a Skolem constant or function.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]

  if op in _opaque_wrappers:
    # Recurse to Skolemize any existential trapped inside the wrapper (and rename
    # outer vars), keeping the wrapper itself for pass-2 $block expansion.
    # _push_normally_inside reduces normally() to wrap a single atom BEFORE this
    # pass -- but it does NOT push through `or`, so normally(or(..., exists Y ...))
    # reaches here with a live exists.  The old code returned apply_varmap(frm)
    # WITHOUT recursing, leaving that exists un-Skolemized -> it survived to gk
    # ("first argument of exists connective not a variable list", e.g. FOLIO c198
    # S8).  For a plain normally(atom) this is equivalent to the old apply_varmap.
    return [op] + [_skolemize(el, freevars, varmap) for el in frm[1:]]

  if op == "forall":
    var = frm[1]
    body = frm[2]
    gk_var = var if var.startswith("?:") else "?:" + var
    new_varmap = dict(varmap)
    new_varmap[var] = gk_var
    new_freevars = freevars + [gk_var]
    # Drop the quantifier — the renamed free var is implicitly universally quantified in GK
    return _skolemize(body, new_freevars, new_varmap)

  if op == "exists":
    var = frm[1]
    body = frm[2]
    isa_type = _extract_skolem_type(body, var) if not freevars else None
    skolem = _make_skolem(freevars, isa_type)
    new_varmap = dict(varmap)
    new_varmap[var] = skolem
    return _skolemize(body, freevars, new_varmap)

  if op in ("and", "or", "not"):
    return [op] + [_skolemize(el, freevars, varmap) for el in frm[1:]]

  # Atomic formula: apply varmap to rename any stage-2 vars in arguments
  return apply_varmap(frm, varmap)


def _extract_skolem_type(body, var):
  """Extract isa type for var from existential body, or None."""
  if not isinstance(body, list) or not body:
    return None
  if body[0] == "isa" and len(body) >= 3 and body[2] == var and isinstance(body[1], str):
    return body[1]
  if body[0] == "and":
    for item in body[1:]:
      if (isinstance(item, list) and len(item) >= 3
          and item[0] == "isa" and item[2] == var
          and isinstance(item[1], str)):
        return item[1]
  return None


def _make_skolem(freevars, isa_type=None):
  """Create a Skolem constant (no free vars) or function (with free vars).

  For constants, if isa_type is known, appends it: sk0_house.
  Functions keep plain names: ["sk0", "?:X"].
  """
  global _skolem_nr
  name = "sk" + str(_skolem_nr)
  _skolem_nr += 1
  if freevars:
    return [name] + freevars
  if isa_type:
    return name + "_" + isa_type
  return name


def apply_varmap(frm, varmap):
  """Recursively substitute stage-2 variable names in frm using varmap."""
  if isinstance(frm, str):
    return varmap.get(frm, frm)
  if not isinstance(frm, list):
    return frm
  return [apply_varmap(el, varmap) for el in frm]


# ======== forall stripping ========

def _strip_forall(frm):
  """Convert remaining forall(X, body) to body with X→?:X, recursively.

  After _skolemize removes existentials, any remaining forall nodes
  (from generic-class conditionals) are expanded to free variables.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  if frm[0] == "forall" and len(frm) == 3:
    var = frm[1]
    body = frm[2]
    gk_var = var if var.startswith("?:") else "?:" + var
    body = apply_varmap(body, {var: gk_var})
    return _strip_forall(body)
  return [_strip_forall(el) for el in frm]


# ======== CNF distribution ========

def _distribute(frm):
  """Distribute OR over AND (CNF transformation).
  Input must be in NNF with no quantifiers (after _skolemize).
  Opaque wrappers are treated as atoms.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]

  if op in _opaque_wrappers:
    return frm  # opaque atom

  if op == "and":
    # Distribute each child and flatten any nested ANDs that result.
    result = []
    for el in frm[1:]:
      d = _distribute(el)
      if isinstance(d, list) and d and d[0] == "and":
        result.extend(d[1:])
      else:
        result.append(d)
    return ["and"] + result

  if op == "or":
    # Recursively distribute each sub-formula first
    parts = [_distribute(el) for el in frm[1:]]

    # Flatten nested "or"s into a single disjunction
    flat = _flatten_or_elements(parts)

    # Check if any element is an "and" (requires distribution)
    has_and = any(isinstance(p, list) and p and p[0] == "and" for p in flat)
    if not has_and:
      if len(flat) == 1:
        return flat[0]
      return ["or"] + flat

    # Build groups: each "and" element contributes its children; others wrap in [...]
    groups = []
    for p in flat:
      if isinstance(p, list) and p and p[0] == "and":
        groups.append(p[1:])
      else:
        groups.append([p])

    # Cartesian product of groups (each combo is one clause)
    combos = _cartesian(groups)
    if len(combos) == 1:
      combo = combos[0]
      return combo[0] if len(combo) == 1 else ["or"] + combo

    clauses = []
    for combo in combos:
      clauses.append(combo[0] if len(combo) == 1 else ["or"] + combo)
    return ["and"] + clauses

  # Atomic
  return frm


def _cartesian(groups):
  """Compute cartesian product of groups (list of lists)."""
  result = [[]]
  for group in groups:
    new_result = []
    for existing in result:
      for item in group:
        new_result.append(existing + [item])
    result = new_result
  return result


# ======== clause extraction ========

def _extract_clauses(frm):
  """Extract a flat list of GK clauses from a CNF formula.

  A GK clause is:
    - single atom:  ["pred", arg, ...]           (a plain list)
    - disjunction:  [["pred1",...], ["pred2",...]] (list of lists)

  The input is in CNF (output of _distribute), so:
    - top-level "and": each child is a separate clause
    - top-level "or":  its children are atoms, forming one multi-literal clause
    - anything else:   one single-literal clause
  """
  if not isinstance(frm, list) or not frm:
    return []
  op = frm[0]

  if op == "and":
    clauses = []
    for el in frm[1:]:
      clauses.extend(_extract_clauses(el))
    return clauses

  if op == "or":
    # Each child should be an atom at this point
    atoms = frm[1:]
    return [atoms]  # one clause = list of atom-lists

  # Single atom (predicate or opaque wrapper)
  return [frm]


# =========== the end ==========
