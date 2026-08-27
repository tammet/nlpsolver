# existfold2 — the narrow, cost-aware existential-attribute collapse (-existfold2).
#
# One rewrite, and only this one:
#
#     exists Y. isa(C,Y) & has part(X,Y)     ->     has property([$has_part,C], X)
#
# The point is the Skolem witness the rewrite deletes.  A theory that says "an
# animal with legs jumps", "a terricolous animal has legs" and "KiKi is
# terricolous" mints one witness per occurrence and the prover pairs them all;
# collapsing the pattern to a unary property removes the pairing.
#
# Three differences from the legacy -existfold (`lc_existfold.py`), which stays
# exactly as it is:
#
#   * v1 also folds `have`.  v2 does not.  `have` covers ownership, kinship and
#     plain attribution, and those readings already interact with other axioms.
#   * v1 floats conjuncts that do not mention Y out of the existential, so a
#     pattern with extra material still folds.  v2 accepts the bare two-atom
#     pattern only.
#   * v1 injects six clauses quantified over the class, so every problem where
#     one fold fired pays for a general reconstruction schema.  v2 counts the
#     pattern first and rewrites a class only when it occurs often enough to pay
#     for its own three class-specific clauses.
#
# Each occurrence replaces a two-literal existential by one property literal, and
# exact bidirectional compatibility costs three clauses for that class.  Below
# four occurrences the clauses cost more than the rewrite saves, so
# MIN_OCCURRENCES is 4.  It is a starting value to be measured on the full
# suites, not a tuned one.
#
# Gated entirely on existfold2_flag; nothing here runs otherwise.  Runs as a
# pre-clausification tree pass after coarsen_events and before lc_ctxt, in the
# same place as the legacy fold.

import json

from lc_clausify import looks_like_var_broad

RELATION = "has part"
PROPERTY_TAG = "$has_part"
WITNESS_TAG = "$typed_partof"

MIN_OCCURRENCES = 4

_counts = {}        # class -> eligible occurrences
_activated = set()  # classes whose occurrences are rewritten
_rewrites = []      # one record per performed rewrite
_refusals = []      # one record per near miss
_source = [None]    # the sentence whose package is being rewritten


def reset():
  global _counts, _activated
  _counts = {}
  _activated = set()
  del _rewrites[:]
  del _refusals[:]
  _source[0] = None


def set_source(name):
  """Name the sentence being rewritten, for the record."""
  _source[0] = name


def any_fired():
  return bool(_rewrites)


def activated_classes():
  return sorted(_activated)


def report():
  """Per-class accounting, plus the individual rewrites and near misses."""
  keys = sorted(set(_counts) | set(_activated))
  per_key = []
  for c in keys:
    n = _counts.get(c, 0)
    active = c in _activated
    per_key.append({
      "key": [RELATION, c],
      "eligible_occurrences": n,
      "activated": active,
      "reason": ("at or above the threshold of %d" % MIN_OCCURRENCES) if active
                else ("below the threshold of %d" % MIN_OCCURRENCES),
      "source_atoms_removed": 2 * sum(1 for r in _rewrites if r["class"] == c),
      "bridge_clauses_added": 3 if active else 0,
    })
  return {"threshold": MIN_OCCURRENCES, "per_key": per_key,
          "rewrites": list(_rewrites), "refusals": list(_refusals)}


# ---- the accepted shape ---------------------------------------------------


def _occurs(term, v):
  if term == v:
    return True
  if isinstance(term, list):
    return any(_occurs(t, v) for t in term)
  return False


def _match(node):
  """Recognise the bare part pattern.

  Returns (C, X, tail) for
      ["exists", Y, ["and", ["isa", C, Y], ["has part", X, Y, *tail]]]
  when Y is the binder, C is a class label, Y occurs in exactly these two atoms
  and nowhere else, and the existential holds nothing else.  Otherwise None,
  with the near miss recorded.
  """
  if not (isinstance(node, list) and len(node) == 3 and node[0] == "exists"):
    return None
  Y = node[1]
  body = node[2]
  if not (isinstance(body, list) and body and body[0] == "and"):
    return None
  conj = body[1:]
  if len(conj) != 2:
    if any(_is_isa(c, Y) for c in conj) and any(_is_haspart(c, Y) for c in conj):
      _refusals.append({"reason": "extra_conjunct", "conjuncts": len(conj)})
    return None
  isa_atom = haslink = None
  for c in conj:
    if _is_isa(c, Y) and isa_atom is None:
      isa_atom = c
    elif _is_haspart(c, Y) and haslink is None:
      haslink = c
  if isa_atom is None or haslink is None:
    return None
  C = isa_atom[1]
  X = haslink[1]
  if (not isinstance(C, str) or not C or looks_like_var_broad(C)
      or C.startswith(("#:", "$"))):
    _refusals.append({"reason": "class_not_a_label"})
    return None
  if len(isa_atom) != 3:
    _refusals.append({"reason": "isa_arity", "class": C})
    return None
  if _occurs(C, Y) or _occurs(X, Y):
    _refusals.append({"reason": "witness_used_elsewhere", "class": C})
    return None
  return C, X, list(haslink[3:])


def _is_isa(c, Y):
  return (isinstance(c, list) and len(c) >= 3 and c[0] == "isa" and c[2] == Y)


def _is_haspart(c, Y):
  return (isinstance(c, list) and len(c) >= 3 and c[0] == RELATION and c[2] == Y)


def _rebuild(Y, C, X, tail):
  """The two source atoms, rebuilt from what the match captured."""
  return ["exists", Y, ["and", ["isa", C, Y], [RELATION, X, Y] + list(tail)]]


def equivalence_ok(node, Y, C, X, tail):
  """True when the captured parts rebuild the source exactly.

  A structural check of the representation: relation, class, possessor, the
  context tail, the quantifier and its variable all have to come back.  No
  prover call is involved.
  """
  rebuilt = _rebuild(Y, C, X, tail)
  if not (isinstance(node, list) and len(node) == 3
          and node[0] == "exists" and node[1] == Y):
    return False
  left = node[2]
  right = rebuilt[2]
  if not (isinstance(left, list) and left and left[0] == "and"
          and isinstance(right, list) and right and right[0] == "and"):
    return False
  # Conjunction order is immaterial.  Everything else remains exact: the
  # quantifier, binder, signs, arguments, relation and context tail.
  def canon(conjunction):
    return sorted(json.dumps(x, sort_keys=True) for x in conjunction[1:])
  return canon(left) == canon(right)


# ---- pass 1: count --------------------------------------------------------


def scan(tree):
  """Count eligible occurrences per class and decide which classes activate."""
  global _activated
  counts = {}

  def walk(n):
    if not isinstance(n, list):
      return
    got = _match(n)
    if got is not None:
      C = got[0]
      counts[C] = counts.get(C, 0) + 1
      return                      # the pattern holds nothing to recurse into
    for x in n:
      walk(x)

  walk(tree)
  _counts.update(counts)
  _activated = {c for c, n in counts.items() if n >= MIN_OCCURRENCES}
  return dict(counts)


# ---- pass 2: rewrite ------------------------------------------------------


def fold(tree):
  """Rewrite every occurrence of an activated class.  Call `scan` first."""
  if not isinstance(tree, list):
    return tree
  got = _match(tree)
  if got is not None:
    C, X, tail = got
    Y = tree[1]
    if C in _activated and equivalence_ok(tree, Y, C, X, tail):
      summary = ["has property", [PROPERTY_TAG, C], X] + list(tail)
      # Audit provenance: the existential as it stood, and what replaced it.
      # The witness the compatibility clauses reconstruct is not recorded as an
      # entity -- it is a term the theory makes, not one the passage introduced.
      _rewrites.append({"class": C, "possessor": X, "context_tail": len(tail),
                        "source": _source[0],
                        "original": _rebuild(Y, C, X, tail),
                        "summary": summary,
                        "context": tail[0] if tail else None})
      return summary
    if C in _activated:
      _refusals.append({"reason": "equivalence_mismatch", "class": C})
    return tree
  return [fold(x) if isinstance(x, list) else x for x in tree]


def fold_existential_attributes(tree):
  """Count, then rewrite.  The single entry point for the converter."""
  scan(tree)
  if not _activated:
    return tree
  # Rewrite package by package where the tree has packages, so each record can
  # name the sentence it came from.  The result is the same either way.
  if (isinstance(tree, list) and tree and tree[0] == "and"
      and any(isinstance(c, list) and len(c) >= 2 and c[0] == "@id"
              for c in tree[1:])):
    out = [tree[0]]
    for child in tree[1:]:
      if isinstance(child, list) and len(child) >= 2 and child[0] == "@id":
        set_source("sent_" + str(child[1]))
      else:
        set_source(None)
      out.append(fold(child) if isinstance(child, list) else child)
    set_source(None)
    return out
  return fold(tree)


# ---- the compatibility clauses -------------------------------------------


def bridge_clauses():
  """Exactly three clauses per activated class, with the class fixed.

      has property([$has_part,C],X)  ->  isa(C, $typed_partof(X,C))
      has property([$has_part,C],X)  ->  has part(X, $typed_partof(X,C))
      isa(C,Y) & has part(X,Y)       ->  has property([$has_part,C],X)

  The witness is a function of the possessor and the class, so every consumer
  of the same (X,C) shares one witness and no cross-product returns.  Its
  `$` name keeps it out of vocabulary extraction and out of ordinary answers.
  """
  X, Y, Ct = "?:Xe2", "?:Ye2", "?:Cte2"
  out = []
  for C in sorted(_activated):
    if not any(r["class"] == C for r in _rewrites):
      continue                        # nothing was rewritten for this class
    prop = [PROPERTY_TAG, C]
    w = [WITNESS_TAG, X, C]
    nhp = ["-has property", prop, X, Ct]
    out += [
      {"@name": "frm_existfold2", "@logic": [nhp, ["isa", C, w]]},
      {"@name": "frm_existfold2", "@logic": [nhp, [RELATION, X, w, Ct]]},
      {"@name": "frm_existfold2_rev", "@logic": [
        ["-isa", C, Y], ["-" + RELATION, X, Y, Ct],
        ["has property", prop, X, Ct]]},
    ]
  seen = set()
  uniq = []
  for c in out:
    key = json.dumps([c["@name"], c["@logic"]], sort_keys=True)
    if key not in seen:
      seen.add(key)
      uniq.append(c)
  return uniq
