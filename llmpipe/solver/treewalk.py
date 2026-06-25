# Shared formula-tree traversals for the clause list.
#
# The dynamic-axiom injectors each re-implemented the same recursive scan of a
# clause-dict list's @logic/@question formulas.  walk_result_atoms factors that
# skeleton out: the caller passes a per-atom visitor and keeps its own captured
# state.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------


def walk_result_atoms(result, visit):
  """Walk the @logic/@question formula of each clause dict in `result`, calling
  visit(atom, base) on every predicate atom — a list whose head atom[0] is a str.
  `base` is atom[0] with any leading '-' (negation marker) stripped.  Disjunctive
  clauses (lists of lists) and nested list arguments are descended; non-list nodes
  are ignored.  A clause dict carries either @logic or @question, never both."""
  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      h = n[0]
      visit(n, h[1:] if h.startswith("-") else h)
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)
