# Cross-stage unsatisfiable-guard + split-mode id-coverage checks.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from stage_sanity_core import Issue



# ======== unsatisfiable-guard check (cross-stage, Stage-2) ================
#
# A rule antecedent names a content predicate -- a class (isa), a property
# (has property) or a relation (is rel2) -- that nothing in the problem can
# ever satisfy: there is no fact of it and no rule whose consequent produces
# it.  Such a rule can never fire, which usually means a word was dropped at
# Stage 1 (case 15: "created the GAME the Legend of Zelda" -> the rule "if a
# game ..." has no game).  We flag the (kind, name) so parse_text can re-read
# Stage 1 and re-encode Stage 2 with a neutral corrective hint.

_GUARD_CONTENT = {"isa": "class", "has property": "property", "is rel2": "relation"}




def _walk_guard_atoms(node, antecedent, neg, guards, supported):
  """Collect content atoms by role.  guards = (kind,name) positive in a rule
  antecedent; supported = (kind,name) positive as a fact or a rule consequent.
  Question / ask formulas and @p metadata are skipped."""
  if not isinstance(node, list) or not node:
    return
  h = node[0]
  if isinstance(h, str):
    # Skip $-headed aggregation / construct nodes ($setof, $count, $measure,
    # $and inside them, $ctxt, ...): atoms there (e.g. isa(copy,$arg1) inside a
    # count's set-builder) are not rule guards that need a real instance.
    if h.startswith("$"):
      return
    base = h[1:] if h.startswith("-") else h
    hneg = neg ^ h.startswith("-")
    if base == "implies" and len(node) >= 3:
      _walk_guard_atoms(node[1], True, hneg, guards, supported)
      for c in node[2:]:
        _walk_guard_atoms(c, False, hneg, guards, supported)
      return
    if base == "not" and len(node) >= 2:
      for c in node[1:]:
        _walk_guard_atoms(c, antecedent, not hneg, guards, supported)
      return
    if base in ("forall", "exists") and len(node) >= 3:
      _walk_guard_atoms(node[2], antecedent, hneg, guards, supported)
      return
    if base in ("and", "or"):
      for c in node[1:]:
        _walk_guard_atoms(c, antecedent, hneg, guards, supported)
      return
    if base in ("holds", "@id"):
      for c in node[2:]:
        _walk_guard_atoms(c, antecedent, hneg, guards, supported)
      return
    if base in ("@p", "question", "ask"):
      return
    if base in _GUARD_CONTENT and len(node) >= 2 and isinstance(node[1], str):
      if not hneg:
        kn = (_GUARD_CONTENT[base], node[1])
        (guards if antecedent else supported).add(kn)
      return
  # unknown structure: recurse children, preserving mode
  for c in (node[1:] if isinstance(h, str) else node):
    _walk_guard_atoms(c, antecedent, neg, guards, supported)




def check_unsatisfiable_guards(s2_logic):
  """Return a sorted list of (kind, name) content guards that appear positively
  in a rule antecedent but are neither stated as a fact nor producible as a
  rule consequent.  kind in {"class","property","relation"}."""
  guards = set()
  supported = set()
  _walk_guard_atoms(s2_logic, False, False, guards, supported)
  sup_class = {n.lower() for (k, n) in supported if k == "class"}
  sup_prop = {n.lower() for (k, n) in supported if k == "property"}
  sup_rel = {n.lower() for (k, n) in supported if k == "relation"}

  def class_ok(name):
    nl = name.lower()
    if nl in sup_class:
      return True
    # compound-head subsumption: a "video game" fact satisfies a "game" guard.
    return any(c.split() and c.split()[-1] == nl for c in sup_class)

  issues = []
  for kind, name in guards:
    if kind == "class":
      if not class_ok(name):
        issues.append((kind, name))
    elif kind == "property":
      if name.lower() not in sup_prop:
        issues.append((kind, name))
    elif kind == "relation":
      if name.lower() not in sup_rel:
        issues.append((kind, name))
  return sorted(set(issues))




def format_guard_retry_suffix(guards):
  """Neutral corrective hint naming each unsatisfiable (kind, name) guard, asking
  the model to re-read and check whether any entity should be captured — without
  asserting the answer.  No "leave unchanged" closer: that wording made the model
  too conservative and suppressed genuine recoveries (case 15); the model is
  already sound and only adds an instance the text supports (so case 156's Greek
  is not invented)."""
  if not guards:
    return ""
  lines = ["", "[NOTE: re-read the sentences. Each item below names something a "
           "rule depends on, but which the current reading neither states "
           "directly nor obtains as the consequence of a rule. Check whether any "
           "entity should be captured accordingly:"]
  for kind, name in guards:
    if kind == "class":
      lines.append('- the class "%s": no entity is established to be a %s; '
                   'check whether any entity should be classified as a %s.'
                   % (name, name, name))
    elif kind == "property":
      lines.append('- the property "%s": no entity is established to have '
                   'property %s; check whether any entity should have it.'
                   % (name, name))
    elif kind == "relation":
      lines.append('- the relation "%s": no entities are established to stand '
                   'in %s; check whether any should.' % (name, name))
  lines.append("]")
  return "\n".join(lines)




# ======== split-mode @id coverage check (Stage-2, -s2split) ================

def check_stage2_id_coverage(logic, expected_ids):
  """For a single-sentence Stage-2 call (-s2split): the top-level ["@id", ...]
  packages must use exactly the unit_ids of the input slice.  The main split-
  mode failure is the LLM renumbering ids to S1.. when a sentence is shown in
  isolation; this check routes that into the normal corrective retry."""
  if not expected_ids:
    return []
  emitted = []
  if isinstance(logic, list) and logic and logic[0] == "and":
    for x in logic[1:]:
      if isinstance(x, list) and len(x) >= 2 and x[0] == "@id" and isinstance(x[1], str):
        emitted.append(x[1])
  elif isinstance(logic, list) and len(logic) >= 2 and logic[0] == "@id":
    emitted.append(logic[1])
  exp, got = set(expected_ids), set(emitted)
  if exp == got:
    return []
  missing = sorted(exp - got)
  extra = sorted(got - exp)
  desc = ('The input contains exactly the units with unit_id '
          + ", ".join(sorted(exp))
          + '. Output exactly one ["@id", ...] package per unit, using those '
            'exact unit ids (do NOT renumber them).')
  if missing:
    desc += " Missing: " + ", ".join(missing) + "."
  if extra:
    desc += " Unexpected ids: " + ", ".join(extra) + "."
  return [Issue(kind="split_id_mismatch",
                location=",".join(sorted(exp)),
                description=desc,
                evidence=",".join(sorted(got)) or "(no @id packages)")]
