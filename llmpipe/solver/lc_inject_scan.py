# Shared clause-scan helpers for the dynamic axiom injectors.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

def collect_eligible_words(result):
  """Scan all clauses and collect eligible string arguments (skip pred names,
  URLs, variables, internal markers). Returns a dict mapping lowercase word
  to the original-case form (for use in generated axioms)."""
  words = {}  # lowercase → original case

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    first = frm[0]
    # GK disjunctive clause: first element is a list → recurse each atom.
    if isinstance(first, list):
      for atom in frm:
        _walk(atom)
      return
    # Regular atom: skip position 0 (predicate name), scan positions 1+.
    for i in range(1, len(frm)):
      arg = frm[i]
      if isinstance(arg, list):
        # Skip $ctxt terms — context markers, not semantic content.
        if arg and isinstance(arg[0], str) and arg[0].startswith("$ctxt"):
          pass
        else:
          _walk(arg)
      elif isinstance(arg, str) and eligible_word(arg):
        words[arg.lower()] = arg  # keep original case

  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      _walk(obj["@logic"])
    if "@question" in obj:
      _walk(obj["@question"])
  return words


def eligible_word(s):
  """True if s is a candidate for synonym/exclusion matching."""
  if not s:
    return False
  if s.startswith("http"):
    return False
  if s.startswith("?:"):
    return False
  if s.startswith("$"):
    return False
  if s.startswith("@"):
    return False
  return True


# Axiom templates by POS.
# Adjectives use "has property" — normalize_gradable_predicates() promotes
# to "has degree property" afterwards if the word is in GRADABLE_PROPS.
# A single free context variable "?:Ctxt" is used (not the expanded
# ["$ctxt",T,W,L,K] form) — it unifies with any context term.
