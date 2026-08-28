# L2 "existfold" — existential-attribute folding.
#
# Collapse a referentially-inert existential attribute
#     exists Y. isa(C,Y) & has_part(X,Y)      (or `have`)
# into a unary property
#     has_property([$has_part, C], X)          (or [$have, C])
# deleting the per-occurrence Skolem cross-product that blows up proofs
# (HARD_PROOFS.md §1: c198 = 179 steps for ~8-step logic).  A generic
# bidirectional bridge with a NAMED canonical witness $typed_partof(X,C)
# reconstructs the existential on demand for un-rewritten / external consumers.
#
# Gated entirely on -existfold (option existfold_flag); nothing here runs
# otherwise.  Pre-clausification TREE pass: run after coarsen_events, before
# lc_ctxt.  See docs/encodings/compiled-representations.md.

# relation -> (property functor, named-witness functor)
_HAS_RELS = {"has part": ("$has_part", "$typed_partof"),
             "have":     ("$have",     "$typed_have")}

_fired = False


def reset():
  global _fired
  _fired = False


def any_fired():
  return _fired


def _contains(term, v):
  if term == v:
    return True
  if isinstance(term, list):
    return any(_contains(t, v) for t in term)
  return False


def _match_attr_exists(node):
  """If ``node`` is the bare attribute pattern
     ["exists", V, ["and", isa(C,V), has_part|have(X,V) (,ctxt), EXTRA...]]
  with V bare (appears ONLY in the isa-typed atom and the has-link object),
  return the rewritten ["has property", [tag, C], X (, ctxt)].  Any further
  conjuncts that do NOT mention V are floated out of the existential scope
  (sound: exists V.(A(V) & B) == (exists V.A(V)) & B) and kept alongside the
  property -- this is what lets the measure form
     exists R. isa(rating,R) & have(X,R) & ~less_measure(4, measure_of(rating,X))
  fold (the comparison is keyed on X, not R, so R is still bare).  Returns the
  property atom, or ["and", property, EXTRA...] when extras float out; else None."""
  if not (isinstance(node, list) and len(node) == 3 and node[0] == "exists"):
    return None
  V = node[1]
  body = node[2]
  if not (isinstance(body, list) and len(body) >= 3 and body[0] == "and"):
    return None
  isa_atom = haslink = None
  extra = []
  for c in body[1:]:
    if not (isinstance(c, list) and c and isinstance(c[0], str)):
      return None
    h = c[0]
    if isa_atom is None and h == "isa" and len(c) == 3 and c[2] == V:
      isa_atom = c
    elif haslink is None and h in _HAS_RELS and len(c) >= 3 and c[2] == V:
      haslink = c
    elif _contains(c, V):
      return None                       # V occurs outside the two bare atoms -> not bare
    else:
      extra.append(c)                   # V-free conjunct -> float out of the existential
  if isa_atom is None or haslink is None:
    return None
  C = isa_atom[1]
  X = haslink[1]
  # V must be bare: it is the witness in exactly these two atoms; also guard that
  # V does not occur inside C or X (e.g. a function term mentioning V).
  if _contains(C, V) or _contains(X, V):
    return None
  tag = _HAS_RELS[haslink[0]][0]
  out = ["has property", [tag, C], X]
  if len(haslink) >= 4:                  # carry $ctxt if the has-link already has it
    out.append(haslink[3])
  global _fired
  _fired = True
  if extra:                              # keep floated conjuncts (recurse for nested folds)
    return ["and", out] + [fold_existential_attributes(e) for e in extra]
  return out


def fold_existential_attributes(tree):
  """Recursively rewrite every bare attribute existential in the tree."""
  if not isinstance(tree, list):
    return tree
  rew = _match_attr_exists(tree)
  if rew is not None:
    return rew
  return [fold_existential_attributes(x) if isinstance(x, list) else x for x in tree]


def bridge_clauses():
  """Generic bidirectional bridge per relation, with a NAMED canonical witness:
       has property($has_part(C), X, Ct) <-> exists Y. isa(C,Y) & has_part(X,Y,Ct)
     forward witness = $typed_partof(X,C) (one per (X,C), so all consumers share it
     -> no cross-product); reverse keeps Y universal so un-rewritten / external
     existentials feed the property.  C,X,Y,Ct are variables -> one schema per
     relation covers all types.  $-meta names so vocab extraction skips them."""
  import os
  if os.environ.get("EXISTFOLD_NOBRIDGE"):       # diagnostic toggle
    return []
  if os.environ.get("EXISTFOLD_REVONLY"):        # diagnostic: reverse-only (no forward witness noise)
    C, X, Y, Ct = "?:Cef", "?:Xef", "?:Yef", "?:Ctef"
    return [{"@name": "frm_existfold_rev", "@logic": [
              ["-isa", C, Y], ["-" + rel, X, Y, Ct], ["has property", [tag, C], X, Ct]]}
            for rel, (tag, wit) in _HAS_RELS.items()]
  C, X, Y, Ct = "?:Cef", "?:Xef", "?:Yef", "?:Ctef"
  out = []
  for rel, (tag, wit) in _HAS_RELS.items():
    prop = [tag, C]
    w = [wit, X, C]
    nhp = ["-has property", prop, X, Ct]
    out += [
      {"@name": "frm_existfold", "@logic": [nhp, ["isa", C, w]]},
      {"@name": "frm_existfold", "@logic": [nhp, [rel, X, w, Ct]]},
      {"@name": "frm_existfold_rev", "@logic": [
        ["-isa", C, Y], ["-" + rel, X, Y, Ct],
        ["has property", prop, X, Ct]]},
    ]
  return out
