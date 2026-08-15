# Reference-preserving repairs for Stage-1/Stage-2 mismatches.
#
# These passes do not use a word list.  They use explicit Stage-1 evidence:
# entity identity, generic/kind scope, action roles, and modifier attachment.
# Their purpose is to keep a participant as one logical object when Stage 2
# accidentally turns it into two existential objects or a literal kind name.

import re

from globals import options as _g_options
from lc_clausify import _safe_singularize_class


_VAR_RE = re.compile(r"^[A-Z][0-9]*$")
_ROLE_PREDS = frozenset({
  "has actor", "has target", "has recipient", "has beneficiary",
  "has source", "has destination", "has location", "has instrument",
  "has accompaniment", "has result", "has topic", "has goal",
})


def _units(s1_json):
  out = {}
  if not isinstance(s1_json, list):
    return out
  for package in s1_json:
    if not isinstance(package, dict):
      continue
    for unit in package.get("units", []) or []:
      if isinstance(unit, dict) and unit.get("unit_id") is not None:
        out[str(unit["unit_id"])] = unit
  return out


def _entity_class(entity_id):
  """Return the normalized class named by a Stage-1 generic entity id."""
  if not isinstance(entity_id, str):
    return entity_id
  base = re.sub(r"\s+\d+$", "", entity_id).strip()
  return _safe_singularize_class(base)


def _rewrite_atom_constant(node, old, new):
  """Replace an entity occurrence without rewriting lexical/type slots."""
  if not isinstance(node, list) or not node:
    return node
  op = node[0] if isinstance(node[0], str) else None
  if op in ("forall", "exists", "ask") and len(node) >= 3:
    return [op, node[1], _rewrite_atom_constant(node[2], old, new)] + [
      _rewrite_atom_constant(x, old, new) if isinstance(x, list) else x
      for x in node[3:]]
  if op in ("and", "or", "not", "implies", "equivalent", "xor", "normally",
            "holds", "question", "@id", "@time", "@p"):
    return [op] + [_rewrite_atom_constant(x, old, new) if isinstance(x, list) else x
                   for x in node[1:]]
  out = list(node)
  replace_positions = range(1, len(out))
  if op in ("isa", "-isa"):
    replace_positions = (2,) if len(out) > 2 else ()
  elif op in ("has property", "-has property", "has degree property",
              "-has degree property"):
    replace_positions = (2,) if len(out) > 2 else ()
  elif op in ("is rel2", "-is rel2", "has degree rel2", "-has degree rel2"):
    replace_positions = tuple(i for i in (2, 3) if i < len(out))
  elif op in ("has type", "-has type"):
    replace_positions = (1,) if len(out) > 1 else ()
  for i in replace_positions:
    if out[i] == old:
      out[i] = new
    elif isinstance(out[i], list):
      out[i] = _rewrite_atom_constant(out[i], old, new)
  return out


def normalize_stage1_kind_constants(logic, s1_json):
  """Normalize number on Stage-1 entities explicitly marked as kind names.

  This covers the construction class illustrated by eb-0016 ("minerals" as a
  kind constant versus "mineral"), without a per-word rewrite table.
  """
  if _g_options.get("nofix_kindnumber") or not isinstance(logic, list):
    return logic
  by_sid = _units(s1_json)
  changed = False
  out = []
  for item in logic:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      out.append(item)
      continue
    unit = by_sid.get(str(item[1]), {})
    body = item[2]
    for ent in unit.get("entities", []) or []:
      if not isinstance(ent, dict) or ent.get("type") != "generic" \
         or ent.get("scope") != "kind":
        continue
      old = ent.get("id")
      new = _entity_class(old)
      if isinstance(old, str) and old != new:
        rewritten = _rewrite_atom_constant(body, old, new)
        changed = changed or rewritten != body
        body = rewritten
    out.append([item[0], item[1], body] + list(item[3:]))
  return out if changed else logic


def _contains_role_value(node, value):
  if not isinstance(node, list) or not node:
    return False
  if isinstance(node[0], str) and node[0] in _ROLE_PREDS \
     and len(node) >= 3 and node[2] == value:
    return True
  return any(_contains_role_value(x, value) for x in node if isinstance(x, list))


def _contains_modifier_bearer(node, value):
  if not isinstance(node, list) or not node:
    return False
  if isinstance(node[0], str) and node[0].lstrip("-") in (
      "has property", "has degree property") and len(node) >= 3 and node[2] == value:
    return True
  return any(_contains_modifier_bearer(x, value) for x in node if isinstance(x, list))


def _bind_modified_event_participant(node, constant, cls, fresh):
  """Bind a kind-name event participant at the smallest event scope."""
  if not isinstance(node, list) or not node:
    return node, False
  if node[0] == "exists" and len(node) >= 3 and isinstance(node[1], str):
    body = node[2]
    if _contains_role_value(body, constant) and _contains_modifier_bearer(body, constant):
      replaced = _rewrite_atom_constant(node, constant, fresh)
      # A flat event fold replaces the whole event existential with is_rel2.
      # Move participant modifiers outside that existential first, otherwise
      # the fold preserves the participant but still erases "dead", "red", etc.
      event_body = replaced[2]
      modifiers = []
      if isinstance(event_body, list) and event_body and event_body[0] == "and":
        kept = ["and"]
        for conjunct in event_body[1:]:
          if (isinstance(conjunct, list) and len(conjunct) >= 3
              and isinstance(conjunct[0], str)
              and conjunct[0].lstrip("-") in ("has property", "has degree property")
              and conjunct[2] == fresh):
            modifiers.append(conjunct)
          else:
            kept.append(conjunct)
        replaced = [replaced[0], replaced[1], kept] + list(replaced[3:])
      return ["exists", fresh,
              ["and", ["isa", cls, fresh]] + modifiers + [replaced]], True
  out = [node[0]]
  changed = False
  for child in node[1:]:
    if isinstance(child, list):
      new_child, did = _bind_modified_event_participant(child, constant, cls, fresh)
      out.append(new_child)
      changed = changed or did
    else:
      out.append(child)
  return out, changed


def introduce_modified_generic_participants(logic, s1_json):
  """Turn a modified generic event filler into a typed bound participant.

  Stage 1 must explicitly attach both an action role and an adjective to the
  same generic entity.  eb2-0009 is the fixture: the target "organic matter"
  and bearer of "dead" become one Y with isa(organic matter,Y).  The repair is
  construction-driven and cannot fire merely because a noun repeats.
  """
  if _g_options.get("nofix_genericparticipants") or not isinstance(logic, list):
    return logic
  by_sid = _units(s1_json)
  counter = [0]
  changed = False
  out = []
  for item in logic:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      out.append(item)
      continue
    unit = by_sid.get(str(item[1]), {})
    role_entities = set()
    for action in unit.get("actions", []) or []:
      if isinstance(action, dict):
        for value in (action.get("roles") or {}).values():
          if isinstance(value, str):
            role_entities.add(value)
    modified = {a[2] for a in (unit.get("adjectives", []) or [])
                if isinstance(a, list) and len(a) >= 3 and isinstance(a[2], str)}
    eligible = []
    for ent in unit.get("entities", []) or []:
      if not isinstance(ent, dict) or ent.get("type") != "generic":
        continue
      eid = ent.get("id")
      if eid in role_entities and eid in modified:
        eligible.append((eid, _entity_class(eid)))
    body = item[2]
    for constant, cls in eligible:
      counter[0] += 1
      body2, did = _bind_modified_event_participant(
          body, constant, cls, "Gref" + str(counter[0]))
      if did:
        body = body2
        changed = True
    out.append([item[0], item[1], body] + list(item[3:]))
  return out if changed else logic


def _ground_typed_exists(node, typ, constant):
  """Replace every existential of exactly ``typ`` by a known constant."""
  if not isinstance(node, list) or not node:
    return node, False
  if node[0] == "exists" and len(node) >= 3 and isinstance(node[1], str) \
     and _safe_singularize_class(_find_isa_type(node[2], node[1])) == typ:
    return _substitute_var(node[2], node[1], constant), True
  out = [node[0]]
  changed = False
  for child in node[1:]:
    if isinstance(child, list):
      child, did = _ground_typed_exists(child, typ, constant)
      changed = changed or did
    out.append(child)
  return out, changed


def resolve_unique_definite_rule_entities(logic, s1_json):
  """Ground a rule's definite noun phrase to its unique discourse entity.

  Stage 1 sometimes calls ``the tiger`` inside a rule generic even though the
  document has exactly one concrete ``tiger N``.  Stage 2 then invents a fresh
  tiger for each occurrence.  If (and only if) the document has one concrete
  entity with that surface class, the rule uses the definite form, and the
  rule has no indefinite occurrence of the same class, replace its typed
  existentials by that concrete Stage-1 id.  This is document-level reference
  resolution, not a predicate- or word-specific bridge.
  """
  if _g_options.get("nofix_definiterefs") or not isinstance(logic, list):
    return logic
  by_sid = _units(s1_json)
  concrete = {}
  for unit in by_sid.values():
    for ent in unit.get("entities", []) or []:
      if isinstance(ent, dict) and ent.get("type") == "concrete" \
         and isinstance(ent.get("id"), str):
        concrete.setdefault(_entity_class(ent["id"]), set()).add(ent["id"])
  unique = {typ: next(iter(ids)) for typ, ids in concrete.items()
            if len(ids) == 1}
  changed = False
  out = []
  for item in logic:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      out.append(item)
      continue
    unit = by_sid.get(str(item[1]), {})
    if "rule" not in str(unit.get("type", "")):
      out.append(item)
      continue
    text = unit.get("text", "")
    body = item[2]
    for ent in unit.get("entities", []) or []:
      if not isinstance(ent, dict) or ent.get("type") != "generic" \
         or not isinstance(ent.get("id"), str):
        continue
      eid = ent["id"]
      typ = _entity_class(eid)
      if typ not in unique:
        continue
      definite = re.search(r"\bthe\s+" + re.escape(eid) + r"\b", text,
                           flags=re.IGNORECASE)
      indefinite = re.search(r"\b(?:a|an)\s+" + re.escape(eid) + r"\b", text,
                             flags=re.IGNORECASE)
      if definite and not indefinite:
        body2, did = _ground_typed_exists(body, typ, unique[typ])
        if did:
          body = body2
          changed = True
    out.append([item[0], item[1], body] + list(item[3:]))
  return out if changed else logic


def _find_isa_type(body, var):
  found = []
  def walk(node):
    if not isinstance(node, list) or not node:
      return
    if node[0] in ("isa", "-isa") and len(node) >= 3 and node[2] == var \
       and isinstance(node[1], str):
      found.append(node[1])
    for child in node[1:]:
      if isinstance(child, list):
        walk(child)
  walk(body)
  return found[0] if found and all(x == found[0] for x in found) else None


def _typed_exists(node):
  out = []
  def walk(cur):
    if not isinstance(cur, list) or not cur:
      return
    if cur[0] == "exists" and len(cur) >= 3 and isinstance(cur[1], str):
      typ = _find_isa_type(cur[2], cur[1])
      if typ is not None:
        out.append((cur, cur[1], typ))
    for child in cur[1:]:
      if isinstance(child, list):
        walk(child)
  walk(node)
  return out


def _strip_exact_exists(node, target, replacement_var=None):
  if node is target:
    body = node[2]
    if replacement_var is not None and node[1] != replacement_var:
      body = _substitute_var(body, node[1], replacement_var)
    return body
  if not isinstance(node, list):
    return node
  return [_strip_exact_exists(x, target, replacement_var) if isinstance(x, list) else x
          for x in node]


def _drop_type_atom(node, typ, var):
  """Remove isa(typ,var) from conjunction structure; return (tree, removed)."""
  if not isinstance(node, list) or not node:
    return node, False
  if node[0] in ("isa", "-isa") and len(node) >= 3 \
     and node[1] == typ and node[2] == var:
    return None, True
  out = [node[0]]
  removed = False
  for child in node[1:]:
    if isinstance(child, list):
      child, did = _drop_type_atom(child, typ, var)
      removed = removed or did
      if child is None:
        continue
    out.append(child)
  if out[0] == "and":
    if len(out) == 1:
      return None, removed
    if len(out) == 2:
      return out[1], removed
  return out, removed


def _factor_rule_participant_type(node, typ, var):
  """Move a carried participant's type outside the event existential."""
  if not isinstance(node, list) or not node:
    return node, False
  if node[0] == "exists" and len(node) >= 3 \
     and _contains_role_value(node[2], var):
    body, removed = _drop_type_atom(node[2], typ, var)
    if removed and body is not None:
      event = [node[0], node[1], body] + list(node[3:])
      return ["and", ["isa", typ, var], event], True
  out = [node[0]]
  changed = False
  for child in node[1:]:
    if isinstance(child, list):
      child, did = _factor_rule_participant_type(child, typ, var)
      changed = changed or did
    out.append(child)
  return out, changed


def _substitute_var(node, old, new):
  if not isinstance(node, list) or not node:
    return new if node == old else node
  if node[0] in ("forall", "exists", "ask") and len(node) >= 3 and node[1] == old:
    return node                         # shadowing binder: do not cross it
  return [_substitute_var(x, old, new) if isinstance(x, list)
          else (new if x == old else x) for x in node]


def _coindex_rule(node, allowed_classes):
  if not isinstance(node, list) or not node:
    return node, False
  out = [node[0]]
  changed = False
  for child in node[1:]:
    if isinstance(child, list):
      child, did = _coindex_rule(child, allowed_classes)
      changed = changed or did
    out.append(child)
  node = out
  if node[0] != "implies" or len(node) != 3:
    return node, changed
  ant, con = node[1], node[2]
  pairs = []
  for ae, av, at in _typed_exists(ant):
    if _safe_singularize_class(at) not in allowed_classes:
      continue
    for ce, cv, ct in _typed_exists(con):
      if _safe_singularize_class(ct) == _safe_singularize_class(at):
        pairs.append((ae, av, ce, cv))
  if len(pairs) != 1:
    return node, changed
  ae, av, ce, cv = pairs[0]
  ant = _strip_exact_exists(ant, ae)
  at = _find_isa_type(ae[2], av)
  if at is not None:
    ant, _ = _factor_rule_participant_type(ant, at, av)
  con = _strip_exact_exists(con, ce, av)
  return ["forall", av, ["implies", ant, con]], True


def coindex_dependent_rule_participants(logic, s1_json):
  """Join two Stage-2 existentials only when Stage 1 says they are one object.

  The evidence may be either a Stage-1 ``scope: dependent`` annotation or the
  same definite noun phrase (``the <entity>``) occurring twice.  The entity
  must also occur in an action role.  This repairs the general constructions
  illustrated by mle2-0049 ("a seed ... the seed") and PW case 83 ("the tiger
  ... the tiger"), while refusing "owns a dog -> buys a dog", where repeated
  type alone is no evidence that the two dogs are identical.
  """
  if _g_options.get("nofix_rulecoref") or not isinstance(logic, list):
    return logic
  by_sid = _units(s1_json)
  changed = False
  out = []
  for item in logic:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      out.append(item)
      continue
    unit = by_sid.get(str(item[1]), {})
    text = unit.get("text", "")
    role_entities = set()
    for action in unit.get("actions", []) or []:
      if isinstance(action, dict):
        role_entities.update(v for v in (action.get("roles") or {}).values()
                             if isinstance(v, str))
    allowed = set()
    for ent in unit.get("entities", []) or []:
      if not isinstance(ent, dict) or ent.get("type") != "generic":
        continue
      eid = ent.get("id")
      if not (eid in role_entities and isinstance(eid, str)):
        continue
      dependent = ent.get("scope") == "dependent" and text.count(eid) >= 2
      definite_pattern = r"\bthe\s+" + re.escape(eid) + r"\b"
      repeated_definite = len(re.findall(definite_pattern, text,
                                         flags=re.IGNORECASE)) >= 2
      if dependent or repeated_definite:
        allowed.add(_entity_class(eid))
    body, did = _coindex_rule(item[2], allowed) if allowed else (item[2], False)
    changed = changed or did
    out.append([item[0], item[1], body] + list(item[3:]))
  return out if changed else logic


def _free_vars(node, bound):
  if not isinstance(node, list) or not node:
    return set()
  op = node[0] if isinstance(node[0], str) else None
  if op in ("forall", "exists", "ask") and len(node) >= 3:
    return _free_vars(node[2], bound | {node[1]})
  if op in ("and", "or", "not", "implies", "equivalent", "xor", "normally",
            "holds", "question", "@id", "@time", "@p"):
    result = set()
    for child in node[1:]:
      if isinstance(child, list):
        result |= _free_vars(child, bound)
    return result
  result = set()
  for arg in node[1:]:
    if isinstance(arg, str) and _VAR_RE.match(arg) and arg not in bound:
      result.add(arg)
    elif isinstance(arg, list):
      result |= _free_vars(arg, bound)
  return result


def _exists_for_var(node, var):
  found = []
  def walk(cur):
    if not isinstance(cur, list) or not cur:
      return
    if cur[0] == "exists" and len(cur) >= 3 and cur[1] == var:
      found.append(cur)
    for child in cur[1:]:
      if isinstance(child, list):
        walk(child)
  walk(node)
  return found


def repair_rule_variable_scope(formula, bound=None):
  """Lift an antecedent participant binder over a rule that concludes about it.

  For `implies(exists Y A(Y), B(Y))`, Stage 2 has placed Y's binder too low.
  The intended rule construction is `forall Y implies(A(Y), B(Y))`.  The pass
  fires only when the same variable has exactly one antecedent existential;
  all remaining free conclusion variables are rejected by the validator below.
  """
  if _g_options.get("nofix_rulescope"):
    return formula
  if bound is None:
    bound = set()
  if not isinstance(formula, list) or not formula:
    return formula
  op = formula[0] if isinstance(formula[0], str) else None
  if op in ("forall", "exists", "ask") and len(formula) >= 3:
    return [op, formula[1], repair_rule_variable_scope(
        formula[2], bound | {formula[1]})] + list(formula[3:])
  children = [repair_rule_variable_scope(x, bound) if isinstance(x, list) else x
              for x in formula[1:]]
  node = [formula[0]] + children
  if op != "implies" or len(node) != 3:
    return node
  ant, con = node[1], node[2]
  lifted = []
  for var in sorted(_free_vars(con, bound)):
    candidates = _exists_for_var(ant, var)
    if len(candidates) == 1:
      ant = _strip_exact_exists(ant, candidates[0])
      lifted.append(var)
  node = ["implies", ant, con]
  for var in reversed(lifted):
    node = ["forall", var, node]
  return node


def free_rule_conclusion_vars(formula, bound=None):
  """Return Stage-2 variables used free in any rule conclusion."""
  if bound is None:
    bound = set()
  if not isinstance(formula, list) or not formula:
    return set()
  op = formula[0] if isinstance(formula[0], str) else None
  if op in ("forall", "exists", "ask") and len(formula) >= 3:
    return free_rule_conclusion_vars(formula[2], bound | {formula[1]})
  result = set()
  if op == "implies" and len(formula) == 3:
    result |= _free_vars(formula[2], bound)
  for child in formula[1:]:
    if isinstance(child, list):
      result |= free_rule_conclusion_vars(child, bound)
  return result
