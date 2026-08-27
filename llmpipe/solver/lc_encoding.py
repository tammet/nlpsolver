# Single source of truth for encoding-flag resolution.
#
# All encoding gates (event fold, entity canonicalization, guard drop, bridges,
# definite-reification skip, degree collapse) resolve here in one place instead
# of as inline boolean expressions in logconvert.py / lc_sets.py / lc_coarse.py /
# semnormalize.py / lc_post_reify.py / solve.py. The pipeline reads ONLY
# EncodingConfig fields; the CLI flags and the -abstract* presets only change how
# the config is POPULATED (in EncodingConfig.__init__), never how it is read.
# See analysis/FLAG_INVENTORY.md.

import globals as _g


_ALL_TE_GATES = frozenset(
  ("super", "gender", "nametype", "compound", "plural", "gnoun"))


class EncodingConfig:
  __slots__ = (
    "event_base", "flatten", "eventprop", "davidson", "davidson2",
    "davidson2_not_applicable", "existfold2",
    "entitymerge", "guarddrop", "bridges", "dropdefinites", "localantonyms",
    "simpleprops", "collapse_degree", "parse_canon", "needs_coarsen",
    "typeenrich", "typeenrich_gates", "propclass", "numtype", "compasym",
  )

  def __init__(self, o):
    base = o.get("event_base", "neodavidson")
    self.event_base = base

    # Event-base derived axes (the coarsen_events fold).
    self.flatten   = base in ("flat", "flatroles")   # flat is_rel2 fold
    self.eventprop = base == "flatroles"             # role-tag the folded object
    self.davidson  = base == "davidson"              # compact event(V,A,O,E) fold

    # ---- the two safe proof-shortening transformations -------------------
    #
    # Both are ATTEMPTED by default on the ordinary canonical theory, and each
    # refuses locally when its own conditions fail, leaving that source form as
    # it was.  The default reaches exactly one configuration: the canonical
    # neo-Davidsonian base that the command line did not name.  Anything the
    # command line names for itself -- an explicit -event MODE, an -abstract*
    # preset, the legacy -existfold -- keeps that base's own historical theory,
    # so every earlier run reproduces.  An explicit request turns a
    # transformation on from any position; a cancellation turns it off from any
    # position and beats both.
    explicit_base = bool(o.get("event_base_explicit"))
    preset = bool(o.get("abstract_preset_flag"))
    legacy_existfold = bool(o.get("existfold_flag"))
    no_short = bool(o.get("noproofshort2_flag"))
    cancel_d2 = bool(o.get("nodavidson2_flag")) or no_short
    cancel_e2 = bool(o.get("noexistfold2_flag")) or no_short
    # the command line asked for the historical behaviour of some other base
    historical = explicit_base or preset or legacy_existfold

    self.davidson2 = False
    self.davidson2_not_applicable = False
    if cancel_d2:
      pass                                    # cancelled: nothing else matters
    elif base == "davidson2":
      self.davidson2 = True                   # named as the base outright
    elif o.get("davidson2_flag"):
      if base == "neodavidson":
        self.davidson2 = True                 # requested, and there is a spine
      else:
        self.davidson2_not_applicable = True  # requested on a base without one
    elif not historical and base == "neodavidson":
      self.davidson2 = True                   # the default

    self.existfold2 = False
    if cancel_e2:
      pass
    elif o.get("existfold2_flag"):
      self.existfold2 = True                  # requested outright
    elif not historical:
      self.existfold2 = True                  # the default

    # Additive abstraction primitives (one flag each; presets set a subset).
    self.entitymerge   = bool(o.get("entitymerge_flag"))   # proper-noun canon + set coref
    self.guarddrop     = bool(o.get("guarddrop_flag"))     # drop redundant antecedent guards
    self.bridges       = bool(o.get("bridges_flag"))       # frame/bridge axioms
    self.dropdefinites = bool(o.get("dropdefinites_flag")) # SKIP $theof1 definite reification
    self.localantonyms = bool(o.get("localantonyms_flag")) # restrict antonym-fold vocabulary
    self.simpleprops   = bool(o.get("noproptypes_flag"))   # degree predicates -> simple
    self.propclass     = bool(o.get("propclass_flag"))     # property<->class canonicalization (P1)
    self.numtype       = bool(o.get("numtype_flag"))       # numeric-literal parse + isa(number,N) typing (P3)
    self.compasym      = bool(o.get("compasym_flag"))      # comparative asymmetry for binary is_rel2(R,X,Y) (P3)

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
      self.davidson or self.davidson2 or self.flatten
      or self.entitymerge or self.guarddrop)

  def te(self, gate):
    """True if the given typeenrich sub-gate is enabled."""
    return gate in self.typeenrich_gates


def current():
  """Resolve the encoding config from the live global options."""
  return EncodingConfig(_g.options)


# ======== abstraction experiments (2026-08-26 core-regression study) ========
#
# `LLMPIPE_ABSEXP` is a comma list of experiment names.  Each name switches one
# augmentation of the -abstract* encoding on; unset (the default) leaves every
# encoding exactly as it was.  Read once per process.  Names in use:
#   keepdef    the strict finaliser keeps `normally`, `$block` and `typical`
#   keepctxt   the strict finaliser keeps every $ctxt term (tense and world)
#   strictfold the flat fold folds only actor + exactly one core object role
#              (target/recipient/beneficiary/goal/topic) with no adjunct and
#              no modified typed-existential filler; every other event stays
#              reified
#   objbridge  is_rel2(V,A,[R,X]) & isa(K,X) -> is_rel2(V,A,[R,K]) for each
#              bare-class-token object atom (V,R,K) in the clause list
import os as _os

_EXPERIMENTS = frozenset(
  x.strip() for x in _os.environ.get("LLMPIPE_ABSEXP", "").split(",") if x.strip())


def experiment(name):
  """True iff `name` is listed in LLMPIPE_ABSEXP."""
  return name in _EXPERIMENTS
