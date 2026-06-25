# Single source of truth for encoding-flag resolution.
#
# All encoding gates (event fold, entity canonicalization, guard drop, bridges,
# definite-reification skip, degree collapse) used to be inline boolean
# expressions scattered across logconvert.py / lc_sets.py / lc_coarse.py /
# solve.py, each re-deriving the "implied by -ultracoarse" relation its own way
# (see analysis/FLAG_INVENTORY.md). This module centralizes that into one
# resolver. The pipeline reads ONLY EncodingConfig fields; later flag renames /
# presets change how the config is POPULATED (in EncodingConfig.__init__) without
# touching any read site.
#
# Phase A note: __init__ reads the legacy option keys and reproduces the exact
# prior gate logic, so behaviour is byte-identical. Phase B repopulates from the
# new primitive keys + presets.

import globals as _g


_ALL_TE_GATES = frozenset(
  ("super", "gender", "nametype", "compound", "plural", "gnoun"))


class EncodingConfig:
  __slots__ = (
    "event_base", "flatten", "eventprop", "davidson",
    "entitymerge", "guarddrop", "bridges", "dropdefinites", "localantonyms",
    "simpleprops", "collapse_degree", "parse_canon", "needs_coarsen",
    "typeenrich", "typeenrich_gates",
  )

  def __init__(self, o):
    base = o.get("event_base", "neodavidson")
    self.event_base = base

    # Event-base derived axes (the coarsen_events fold).
    self.flatten   = base in ("flat", "flatroles")   # flat is_rel2 fold
    self.eventprop = base == "flatroles"             # role-tag the folded object
    self.davidson  = base == "davidson"              # compact event(V,A,O,E) fold

    # Additive abstraction primitives (one flag each; presets set a subset).
    self.entitymerge   = bool(o.get("entitymerge_flag"))   # proper-noun canon + set coref
    self.guarddrop     = bool(o.get("guarddrop_flag"))     # drop redundant antecedent guards
    self.bridges       = bool(o.get("bridges_flag"))       # frame/bridge axioms
    self.dropdefinites = bool(o.get("dropdefinites_flag")) # SKIP $theof1 definite reification
    self.localantonyms = bool(o.get("localantonyms_flag")) # restrict antonym-fold vocabulary
    self.simpleprops   = bool(o.get("noproptypes_flag"))   # degree predicates -> simple

    # Degree collapse inside the fold rides with simpleprops; parse-level entity
    # canonicalization rides with entitymerge (the primitive is self-contained).
    self.collapse_degree = self.simpleprops
    self.parse_canon     = self.entitymerge

    # typeenrich: a primitive carrying a set of enabled sub-gates (default all).
    self.typeenrich = bool(o.get("typeenrich_flag"))
    gates = o.get("typeenrich_gates")
    if not self.typeenrich:
      self.typeenrich_gates = frozenset()
    elif gates is None:
      self.typeenrich_gates = _ALL_TE_GATES
    else:
      self.typeenrich_gates = frozenset(gates)

    # Whether coarsen_events runs at all.
    self.needs_coarsen = bool(
      self.davidson or self.flatten or self.entitymerge or self.guarddrop)

  def te(self, gate):
    """True if the given typeenrich sub-gate is enabled."""
    return gate in self.typeenrich_gates


def current():
  """Resolve the encoding config from the live global options."""
  return EncodingConfig(_g.options)
