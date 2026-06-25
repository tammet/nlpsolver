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


class EncodingConfig:
  __slots__ = (
    "flatten", "eventprop", "davidson", "coarse",
    "entitymerge", "guarddrop", "bridges", "dropdefinites",
    "collapse_degree", "parse_canon", "needs_coarsen",
  )

  def __init__(self, o):
    ultra  = o.get("ultracoarse_flag", False)
    ultra2 = o.get("ultracoarse2_flag", False)
    flatev = o.get("flatevents_flag", False)
    coarse = o.get("coarse_flag", False)
    em     = o.get("entitymerge_flag", False)
    gd     = o.get("guarddrop_flag", False)
    br     = o.get("bridges_flag", False)
    defl   = o.get("definites_flag", False)
    dav    = o.get("davidson_flag", False)

    # Event-base derived axes (the coarsen_events fold).
    self.flatten   = bool(ultra or flatev)     # aggressive flat is_rel2 fold
    self.eventprop = bool(ultra2 or flatev)    # role-tag the folded object
    self.davidson  = bool(dav)                 # compact event(V,A,O,E) fold
    self.coarse    = bool(coarse)              # conservative collapsible "do" fold

    # Additive buckets, each widened by the -ultracoarse master exactly as before.
    self.entitymerge   = bool(ultra or em)     # proper-noun canon + set coref
    self.guarddrop     = bool(ultra or gd)     # drop redundant antecedent guards
    self.bridges       = bool(ultra or br)     # frame/bridge axioms
    self.dropdefinites = bool(ultra or defl)   # SKIP $theof1 definite reification

    # -ultracoarse-only internals.
    self.collapse_degree = bool(ultra)         # degree nodes -> simple, in the fold
    self.parse_canon     = bool(ultra)         # parse-level entity canonicalization

    # Whether coarsen_events runs at all (raw-flag trigger; ultracoarse sets
    # coarse_flag at the CLI, so it is covered by `coarse`).
    self.needs_coarsen = bool(coarse or flatev or em or gd or dav)


def current():
  """Resolve the encoding config from the live global options."""
  return EncodingConfig(_g.options)
