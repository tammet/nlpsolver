# Term rendering for proof explanations: $count/$setof/$theof1/$measure and
# TPTP arithmetic -> English.  Split out of proof_english.py; the proof_render
# facade and proof_utils reach render_term_english through here.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from proof_utils import entity_name


def _is_var_raw(args, i):
  """True if args[i] is a raw variable string (starts with '?:')."""
  return (len(args) > i and isinstance(args[i], str) and args[i].startswith("?:"))

# Measure-unit promotion table for rendering. When a $list value is exactly
# divisible by the divisor (and has no fractional part), promote to the next
# unit. Cascades naturally: 80000 mm → 80 m → 0.08 km not triggered (80 m %
# 1000 ≠ 0). 1000000 mm → 1000 m → 1 km (cascade fires).
_MEASURE_PROMOTE = {
  "meter":      ("kilometer", 1000),
  "millimeter": ("meter",     1000),
  "centimeter": ("meter",      100),
  "gram":       ("kilogram",  1000),
  "milligram":  ("gram",      1000),
}


def _normalize_measure(val, unit_name):
  """Promote (val, unit_name) to a larger unit when val is integer-valued
  and exactly divisible by the unit's promotion factor.

  Cascades while a promotion still applies. Returns (val, unit_name)
  unchanged when no promotion is possible (e.g. 100 meters stays "100
  meters" because 100 % 1000 ≠ 0).
  """
  if isinstance(val, float) and val.is_integer():
    val = int(val)
  if not isinstance(val, int):
    return val, unit_name
  while unit_name in _MEASURE_PROMOTE:
    bigger, divisor = _MEASURE_PROMOTE[unit_name]
    if val % divisor != 0:
      break
    val //= divisor
    unit_name = bigger
  return val, unit_name


def _measure_phrase(val, unit_name):
  """Render "<val> <unit>" with a pluralised unit for numeric val != 1.

  "80000", "meter" -> "80000 meters";  1, "dollar" -> "1 dollar".
  Leaves an already-plural unit untouched.
  """
  unit_name = str(unit_name)
  num = val
  if isinstance(num, float) and num.is_integer():
    num = int(num)
  pluralise = (not isinstance(num, (int, float))) or num != 1
  if pluralise and unit_name and not unit_name.endswith("s"):
    unit_name = unit_name + "s"
  return str(num) + " " + unit_name


def render_term_english(term, proof_mode=True):
  """Render a complex list term (nested function/predicate) as English.

  Handles $count, $setof, TPTP arithmetic ($sum, $difference, $product,
  $quotient), and infix arithmetic (+, -, *, /).
  Falls back to str() for unrecognized terms.

  proof_mode controls how nested entity names are rendered: True (default,
  used for proof explanation) keeps raw IDs in JSON mode for traceability;
  False (used for the user-facing answer line) consults entity_map to get
  cosmetic names like "Mary" instead of "Mary 1".
  """
  if not isinstance(term, list) or not term:
    return str(term)

  op = term[0]

  # $datetime -> just the value
  if op == "$datetime" and len(term) >= 2:
    return str(term[1])

  # $theof1 -> "SUBJECT's TYPE" for named entities, else "the TYPE of SUBJECT"
  if op == "$theof1" and len(term) >= 3:
    type_name = term[1] if isinstance(term[1], str) else str(term[1])
    subj = entity_name(term[2], proof_mode=proof_mode)
    if subj and subj[0:1].isupper() and not subj.lower().startswith(("the ", "a ", "an ")):
      suffix = "'" if subj.endswith("s") else "'s"
      return subj + suffix + " " + type_name
    return "the " + type_name + " of " + subj

  # $typed_partof / $typed_have -> "a C of SUBJECT".  The witness an
  # existential-attribute fold reconstructs is not a named object: the theory
  # says only that SUBJECT has some C, so the reading stays existential.  Its
  # arguments are (possessor, class), the reverse of $theof1's order.
  if op in ("$typed_partof", "$typed_have") and len(term) >= 3:
    cls = term[2] if isinstance(term[2], str) else str(term[2])
    subj = entity_name(term[1], proof_mode=proof_mode)
    article = "an " if cls[:1].lower() in "aeiou" else "a "
    return article + cls + " of " + subj

  # $measure_of -> "the TYPE of SUBJECT"
  if op == "$measure_of" and len(term) >= 3:
    type_name = term[1] if isinstance(term[1], str) else str(term[1])
    subj = entity_name(term[2], proof_mode=True)
    return "the " + type_name + " of " + subj

  # $measure -> "80 kilometers" (original form, before canonicalization)
  if op == "$measure" and len(term) == 3:
    return _measure_phrase(term[1], term[2])

  # $list with number + unit -> "80000 meters".  The unit may carry the UNA
  # `#:` prefix (proof-step path) or not (answer path, where the prover echoes
  # the constant with `#:` already stripped).  Handle both: pluralise the unit
  # for numeric values either way.  Promotion to a larger unit is only applied
  # when the canonical `#:`-prefixed form is present.
  if op == "$list" and len(term) == 3:
    val = term[1]
    unit = term[2]
    if isinstance(unit, str) and unit.startswith("#:"):
      unit_name = unit[2:]  # strip #: prefix
      val, unit_name = _normalize_measure(val, unit_name)
      return _measure_phrase(val, unit_name)
    if isinstance(unit, str):
      return _measure_phrase(val, unit)
    return str(val) + " " + str(unit)

  # $count -> "the number of ..."
  if op == "$count" and len(term) >= 2:
    inner = render_setof_english(term[1])
    return "the number of " + inner

  # $setof -> delegate
  if op == "$setof":
    return render_setof_english(term)

  # TPTP prefix arithmetic functions
  _ARITH_PREFIX = {
    "$sum": "+", "$difference": "-", "$product": "*", "$quotient": "/",
    "$quotient_e": "/", "$remainder_e": "mod", "$remainder_t": "mod",
    "$remainder_f": "mod", "$uminus": "-",
    "$floor": "floor", "$ceiling": "ceiling",
    "$truncate": "truncate", "$round": "round",
    "$to_int": "int", "$to_real": "real",
  }
  if op in _ARITH_PREFIX and len(term) >= 2:
    if op == "$uminus":
      return "-" + entity_name(term[1], proof_mode=True)
    if len(term) == 2:
      # Unary: $floor(X) etc
      return _ARITH_PREFIX[op] + "(" + entity_name(term[1], proof_mode=True) + ")"
    a = entity_name(term[1], proof_mode=True)
    b = entity_name(term[2], proof_mode=True)
    return a + " " + _ARITH_PREFIX[op] + " " + b

  # Infix arithmetic: [A, "+", B] etc
  if len(term) == 3 and isinstance(term[1], str) and term[1] in ("+", "-", "*", "/"):
    a = entity_name(term[0], proof_mode=True)
    b = entity_name(term[2], proof_mode=True)
    return a + " " + term[1] + " " + b

  return str(term)


def render_setof_english(term):
  """Render a $setof term as English.

  Fully concrete (anchor + subject + $isa in conditions):
    $setof(have, John 1, [$and, $isa(car,$arg1)]) -> "cars John has"
    $setof(have, John 1, [$and, $isa(car,$arg1), $has_degree_property(nice,...)]) -> "nice cars John has"

  Partially concrete (anchor + subject concrete, some variable conditions):
    $setof(have, John 1, [$and, $isa(car,$arg1), ?:Y]) -> "cars John has that satisfy Y"

  All variables (generic axiom):
    $setof(?:Y, ?:Z, [$and, ?:U, ?:V]) -> "a set of things satisfying conditions U and V"
  """
  if not isinstance(term, list) or not term or term[0] != "$setof" or len(term) < 3:
    return str(term)

  # Parse canonical $setof form
  if term[1] == "id":
    # Conditions-only: ["$setof", "id", SET_ID, ["$and", ...]]
    set_id = term[2]
    conds = term[3] if len(term) > 3 else []
    type_name = _extract_type_from_conds(conds)
    return type_name + " in " + str(set_id)

  # Anchored: ["$setof", PRED, SUBJ, ["$and", ...]]
  pred = term[1]
  subj = term[2] if len(term) > 2 else "?"
  conds = term[3] if len(term) > 3 else term[2]

  pred_is_var = isinstance(pred, str) and pred.startswith("?:")
  subj_is_var = isinstance(subj, str) and subj.startswith("?:")

  # All variables -> generic description
  if pred_is_var and subj_is_var:
    cond_str = _render_and_conditions(conds)
    return "a set of things satisfying " + cond_str

  # Concrete anchor/subject -> try to produce natural English
  type_name, props, extra_vars = _extract_type_and_props(conds)
  subj_name = entity_name(subj, proof_mode=True)

  # Build the base: "nice cars John has"
  if props:
    desc = " ".join(props) + " " + type_name
  else:
    desc = type_name

  if pred == "have":
    base = desc + " " + subj_name + " has"
  elif pred == "can":
    base = desc + " that can " + str(conds)
  else:
    base = desc + " " + pred + " " + subj_name

  # Append unresolved variable conditions
  if extra_vars:
    var_str = " and ".join(entity_name(v, proof_mode=True) for v in extra_vars)
    base += " that satisfy " + var_str

  return base


def _extract_type_and_props(conds):
  """Extract type name, property adjectives, and unresolved variable conditions.

  Returns (type_name, props_list, extra_vars_list).
  """
  if not isinstance(conds, list) or not conds:
    return "things", [], []
  items = conds[1:] if conds[0] in ("$and", "and") else [conds]

  type_name = "things"
  props = []
  extra_vars = []

  for item in items:
    if isinstance(item, str) and item.startswith("?:"):
      extra_vars.append(item)
      continue
    if not isinstance(item, list) or len(item) < 2:
      continue
    pred = item[0]
    if pred in ("$isa", "isa") and isinstance(item[1], str):
      type_name = item[1] + "s"
    elif pred in ("$has_degree_property", "has degree property") and len(item) >= 3:
      # Extract the adjective name
      adj = item[1] if isinstance(item[1], str) and not item[1].startswith("?:") else None
      if adj:
        props.append(adj)
      else:
        extra_vars.append(item)
    else:
      # Skip $arg1-only predicates (like $have which duplicates the anchor)
      pass

  return type_name, props, extra_vars


def _render_and_conditions(conds):
  """Render $and conditions as a readable string.

  Variable conditions: "conditions U and V"
  Mixed: "conditions $isa(car, ...) and V"
  """
  if not isinstance(conds, list) or not conds:
    return "conditions " + str(conds)
  items = conds[1:] if conds[0] in ("$and", "and") else [conds]

  parts = []
  for item in items:
    if isinstance(item, str) and item.startswith("?:"):
      parts.append(entity_name(item, proof_mode=True))
    elif isinstance(item, str):
      parts.append(item)
    else:
      parts.append(str(item))

  if len(parts) == 1:
    return "condition " + parts[0]
  return "conditions " + " and ".join(parts)


def _extract_type_from_conds(conds):
  """Extract the type name from a $and conditions list."""
  type_name, _, _ = _extract_type_and_props(conds)
  return type_name
