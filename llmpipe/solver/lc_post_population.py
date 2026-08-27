# Population-fact extraction and negative-witness polarity walks, split out
# of lc_post_normalize.py.  Re-exported from there.
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#-----------------------------------------------------------------

from lc_questions import scan_item_formula, build_population_facts
from globals import options as _g_options

# Lazy import to avoid a circular dependency (lc_packages imports this
# module transitively via logconvert).
def _getextract_package_ctx():
  from lc_packages import extract_package_ctx
  return extract_package_ctx


# ======== population fact scanning ========

def populate_clauses(items):
  """Scan all @id items in the raw stage-2 input and return population entries.

  This is the main entry point called from rawlogic_convert.  The underlying
  scanner (scan_item_formula) handles both raw stage-2 and clausified forms,
  so this function can also be applied to a clausified clause list.
  """
  classes   = {}   # CLASS -> {"name", "has_pos", "has_neg"}
  has_props = {}   # PROPERTY -> {"name", "has_pos", "has_neg"}
  deg_props = {}   # (PROPERTY, RELCLASS) -> {"name", "has_pos", "has_neg"}
  compound_witnesses = {}  # (type, pred, prep, target) -> info dict

  for item in items:
    if not isinstance(item, list) or len(item) < 3 or item[0] != "@id":
      continue
    name    = "sent_" + str(item[1])
    package = item[2]
    _is_q, formula, _conf, _, _, _, _ = _getextract_package_ctx()(package)
    if _is_q:
      continue   # never populate from the question sentence — circular by construction
    if formula is not None:
      scan_item_formula(formula, name, True, classes, has_props, deg_props,
                        compound_witnesses=compound_witnesses)

  # A variable used in isa's class slot (forall C. isa(C,X)) is not a named
  # population class.  The older scan minted isa(C,$some_C), turning the binder
  # into a constant even though clausification preserved it correctly (eb-0140).
  if not _g_options.get("nofix_boundtypevars"):
    from lc_clausify import looks_like_var
    classes = {k: v for k, v in classes.items() if not looks_like_var(k)}
    deg_props = {k: v for k, v in deg_props.items()
                 if not (isinstance(k, tuple) and len(k) > 1
                         and looks_like_var(k[1]))}

  # Track concrete intersections (entity X with both isa(TYPE,X) and adj atom)
  # so we can suppress redundant adjective-intersection witnesses.
  from lc_questions import collect_concrete_intersections
  concrete_intersections = collect_concrete_intersections(items)

  # Decide which negative witnesses ($some_not_X) are actually consumable.
  needed_neg = _collect_negative_witness_needs(items)

  return build_population_facts(classes, has_props, deg_props,
                                compound_witnesses=compound_witnesses,
                                concrete_intersections=concrete_intersections,
                                needed_neg=needed_neg)


def _collect_negative_witness_needs(items):
  """Return (cls_needed, prop_needed, degprop_needed) sets identifying the
  classes / properties whose synthetic negative witness ($some_not_*) might
  participate in a proof.

  Rule (i): the literal `-isa(CLASS, V)` (with V a variable) appears at
            negative polarity inside a question body.  Equivalently, a
            positive `isa(CLASS, V)` literal would end up negated in the
            CNF goal — the witness can then unify with it.
  Rule (ii): a positive `isa(CLASS, V)` literal (with V a variable) appears
             ANYWHERE in a non-question package.  This is over-inclusive on
             purpose (it ignores polarity inside the package): the cost is
             at most one dead clause per class that occurs in some rule.

  The same logic applies to `has property(PROP, V)` and
  `has degree property(PROP, V, _, RELCLASS)` — the latter is keyed by the
  (prop, relclass) pair to match `build_population_facts`.
  """
  cls_needed = set()
  prop_needed = set()
  degprop_needed = set()
  extract = _getextract_package_ctx()

  for item in items:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      continue
    is_q, formula, _, _, _, _, _ = extract(item[2])
    if formula is None:
      continue
    if is_q:
      _walk_question_for_neg(formula, +1, cls_needed, prop_needed, degprop_needed)
    else:
      _walk_assertion_for_pos(formula, cls_needed, prop_needed, degprop_needed)

  return (cls_needed, prop_needed, degprop_needed)


_NEG_OPS = frozenset({"not", "-", "~"})


def _walk_question_for_neg(frm, polarity, cls, prop, deg):
  """Walk question body tracking polarity; collect classes/props whose
  predicate appears at NEGATIVE polarity with a variable second arg."""
  from lc_clausify import looks_like_var
  if not isinstance(frm, list) or not frm:
    return
  op = frm[0]
  if not isinstance(op, str):
    return
  if op in _NEG_OPS and len(frm) == 2:
    _walk_question_for_neg(frm[1], -polarity, cls, prop, deg)
    return
  if op == "implies" and len(frm) == 3:
    _walk_question_for_neg(frm[1], -polarity, cls, prop, deg)
    _walk_question_for_neg(frm[2],  polarity, cls, prop, deg)
    return
  if op in ("forall", "exists") and len(frm) >= 3:
    _walk_question_for_neg(frm[-1], polarity, cls, prop, deg)
    return
  if op in ("and", "or", "normally", "ask", "question", "holds"):
    for a in frm[1:]:
      _walk_question_for_neg(a, polarity, cls, prop, deg)
    return
  # A structured term in the class or property slot -- ["$has_part", C] from an
  # existential-attribute fold, say -- names no population class, so it is
  # skipped.  This is the same policy `_walk_assertion_for_pos` states below,
  # and it is what keeps a list out of these sets: a list is unhashable, and
  # adding one raised TypeError on a negative question.
  if not _population_name(frm, 1):
    return
  if op == "isa" and len(frm) >= 3 and polarity < 0 and looks_like_var(frm[2]):
    cls.add(frm[1])
  elif op == "-isa" and len(frm) >= 3 and polarity > 0 and looks_like_var(frm[2]):
    cls.add(frm[1])
  elif op == "has property" and len(frm) >= 3 and polarity < 0 and looks_like_var(frm[2]):
    prop.add(frm[1])
  elif op == "-has property" and len(frm) >= 3 and polarity > 0 and looks_like_var(frm[2]):
    prop.add(frm[1])
  elif op == "has degree property" and len(frm) >= 5 and polarity < 0 and looks_like_var(frm[2]):
    if _population_name(frm, 4):
      deg.add((frm[1], frm[4]))
  elif op == "-has degree property" and len(frm) >= 5 and polarity > 0 and looks_like_var(frm[2]):
    if _population_name(frm, 4):
      deg.add((frm[1], frm[4]))


def _population_name(frm, pos):
  """True when argument `pos` of the literal can key a population class or
  property.  Only a structured term is rejected: it names no class, and it is
  the one shape these sets cannot hold, being unhashable."""
  return len(frm) > pos and not isinstance(frm[pos], (list, dict))


def _walk_assertion_for_pos(frm, cls, prop, deg):
  """Walk an assertion body without polarity tracking; collect every
  positive `isa(C,V)` / `has property(P,V)` / `has degree property(P,V,_,R)`
  literal where V is a variable.  Over-inclusive on purpose — extra
  witnesses are safer than missing ones."""
  from lc_clausify import looks_like_var
  if not isinstance(frm, list) or not frm:
    return
  op = frm[0]
  if not isinstance(op, str):
    return
  if op in ("and", "or", "not", "implies", "normally",
            "ask", "question", "holds"):
    for a in frm[1:]:
      _walk_assertion_for_pos(a, cls, prop, deg)
    return
  if op in ("forall", "exists") and len(frm) >= 3:
    _walk_assertion_for_pos(frm[-1], cls, prop, deg)
    return
  if op == "isa" and len(frm) >= 3 and looks_like_var(frm[2]) \
     and _population_name(frm, 1):
    cls.add(frm[1])
  elif op == "has property" and len(frm) >= 3 and looks_like_var(frm[2]) \
       and _population_name(frm, 1):
    prop.add(frm[1])                      # structured props ([$has_part,C]) skip: not population-relevant
  elif op == "has degree property" and len(frm) >= 5 and looks_like_var(frm[2]) \
       and _population_name(frm, 1) and _population_name(frm, 4):
    deg.add((frm[1], frm[4]))
