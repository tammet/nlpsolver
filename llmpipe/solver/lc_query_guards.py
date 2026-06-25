# Query-body simplification: phantom isa-guard stripping and "what"-question
# population-fact generation.  Split out of logconvert.py.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from lc_post_una import is_stage1_entity as _is_stage1_entity
from lc_packages import raw_has_what_word


# ======== phantom isa-guard stripping (query bodies) ========

def _gather_entities(node, acc, stage1_set):
  """Collect Stage-1 numbered-entity constants ("car 1", "price 4") in node."""
  if isinstance(node, str):
    if _is_stage1_entity(node, stage1_set):
      acc.add(node)
  elif isinstance(node, list):
    for child in node:
      _gather_entities(child, acc, stage1_set)


def _count_entity(entity, node):
  """Count occurrences of the constant `entity` anywhere in node."""
  if node == entity:
    return 1
  if isinstance(node, list):
    return sum(_count_entity(entity, child) for child in node)
  return 0


def strip_phantom_query_guards(logic, stage1_set):
  """Drop isa(C, E) guards from question/ask bodies when E is an ORPHAN
  Stage-1 entity: never asserted anywhere, and used nowhere else in the query
  body (only in the guard itself).

  Such a guard is *guaranteed unsatisfiable* — a query type-guard on a concrete
  constant that has no asserted type can only ever block the query, never
  contribute to a proof.  These leak in when Stage 2 drops a definite
  description's presupposition scaffolding (isa on the definite's referent)
  into the question body — e.g. gpt case 466 emitted `isa(price, price 4)` in
  the ask, where `price 4` only existed via a (since-stripped) @definite, so
  the whole conjunctive query became unprovable -> Unknown.

  The "used nowhere else in the body" condition is essential: it distinguishes
  a leaked presupposition (price 4, typed but never used) from the query's own
  SUBJECT (e.g. `isa(person, John)` in "John is tall?", where John also appears
  in the actual predication and the guard is load-bearing).  Without it the
  filter would strip ~100+ legitimate query-subject guards.

  Safety: removing a provably-unsatisfiable, otherwise-unused conjunct is a
  sound query simplification — it never turns a correct answer wrong.  Caveat
  (the unmasking risk): it converts a guaranteed-Unknown into whatever the rest
  of the now guard-free query proves; if that remainder is itself malformed, a
  previously-masked wrong answer may surface.  It removes a false Unknown; it
  does not validate the remaining query.

  Operates on the Stage-2 logic tree (after @definite stripping).  Returns the
  (possibly rewritten) tree.
  """
  if not isinstance(logic, list) or not logic:
    return logic

  # Pass 1: entities mentioned anywhere inside assertion (holds) packages.
  asserted = set()
  def collect_asserted(node):
    if not isinstance(node, list) or not node:
      return
    if node[0] == "holds":
      _gather_entities(node, asserted, stage1_set)
      return  # don't double-walk; holds bodies aren't queries
    for child in node:
      collect_asserted(child)
  collect_asserted(logic)

  # Pass 2: inside query (question/ask) bodies, drop orphan isa guards.
  def walk(node, in_query):
    if not isinstance(node, list) or not node:
      return node
    head = node[0]
    if head in ("question", "ask"):
      in_query = True
    if head == "and" and in_query:
      conjuncts = node[1:]
      kept = []
      for child in conjuncts:
        if (isinstance(child, list) and len(child) == 3 and child[0] == "isa"
            and isinstance(child[2], str)
            and _is_stage1_entity(child[2], stage1_set)
            and child[2] not in asserted
            # orphan: used nowhere else in this query body
            and sum(_count_entity(child[2], o) for o in conjuncts if o is not child) == 0):
          continue  # drop the dead orphan guard
        kept.append(walk(child, in_query) if isinstance(child, list) else child)
      if not kept:
        return ["and"]  # degenerate; leave an empty conjunction
      if len(kept) == 1:
        return kept[0]
      return ["and"] + kept
    return [walk(child, in_query) if isinstance(child, list) else child
            for child in node]

  return walk(logic, False)


# ======== "what" question population facts ========

def has_what_query(s1_json):
  """Return True if any query ASU text contains 'what' or 'which' as a
  wh-word (anywhere in the text)."""
  if not s1_json or not isinstance(s1_json, list):
    return False
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []):
      if not isinstance(unit, dict):
        continue
      if unit.get("type") == "query":
        if raw_has_what_word(unit.get("text", "")):
          return True
  return False


# Classes to skip when generating "what" population facts.
_WHAT_POP_SKIP = frozenset({
  "activity", "entity", "object", "thing", "event",
})


def generate_what_population(result):
  """Generate population isa facts for classes with concrete witnesses.

  Scans the clause list for unconditional isa(CLASS, ENTITY) facts where
  ENTITY is a concrete entity (not $some_*, not a variable).  For each
  such CLASS, generates isa(CLASS, $some_CLASS) if not already present.

  Returns a list of new clause dicts.
  """
  # Collect classes with concrete witnesses and existing population constants.
  witnessed_classes = set()
  existing_pop = set()
  for obj in result:
    if not isinstance(obj, dict):
      continue
    logic = obj.get("@logic")
    if not isinstance(logic, list) or not logic:
      continue
    # Single-literal positive clause: ["isa", CLASS, ENTITY]
    if (len(logic) == 3 and isinstance(logic[0], str) and logic[0] == "isa"
        and isinstance(logic[1], str) and isinstance(logic[2], str)):
      cls = logic[1]
      ent = logic[2]
      if cls.lower() in _WHAT_POP_SKIP:
        continue
      if ent.startswith("$some_"):
        existing_pop.add(cls)
      elif not ent.startswith("?:"):
        witnessed_classes.add(cls)

  # Generate population facts for witnessed classes without existing $some_
  new_facts = []
  for cls in witnessed_classes:
    if cls in existing_pop:
      continue
    pop_name = "$some_" + cls.replace(" ", "_")
    new_facts.append({"@name": "pop_what",
                      "@logic": ["isa", cls, pop_name]})
  return new_facts
