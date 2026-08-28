"""The converter route: a proposed rule becomes clauses beside the theory.

This is the one file of the litbridge line that calls the main pipeline.  It
runs `logconvert.rawlogic_convert` on a Stage-2 package spliced into the case's
own Stage 2, keeps only the clauses that package produced, and hands them back
to `litbridge_compile`.  The option state that conversion runs under is scoped
here too, at the bottom of the file, because a partial option dict written into
`globals.options` leaks into the next conversion.

A bridge is not an abstraction of the problem.  It is a small, invented,
defeasible rule added beside an already converted theory, and it needs a
`$block` literal, so a later fact can defeat it.  That is lost if the bridge is
converted the way the base theory was.
`tools/bridge_conversion_matrix.py` measures where it survives:

  * `normally` must sit inside a quantifier.  The unquantified
    `normally(implies(A,B))` produces no rule clause at all.  All three
    quantified placements produce a `$block`; this module uses
    `forall vars . BODY -> normally(HEAD)`, the shape the converter's own
    rewrite normalises toward.
  * the strict finaliser (`logconvert`'s `_ultra`, gated by the `typeenrich`
    `plural` sub-gate and therefore on under every `-abstract*` preset) unwraps
    `normally` and drops `$block`.  That is correct for its documented purpose —
    classical, strict abstraction — and is not changed here.  The bridge is
    converted with it off instead.

So the bridge is compiled **separately**, under its own options, and only its
own clauses are kept and appended to the stored base theory.  The base theory is
never reconverted; abstract-max keeps its global meaning.

A bridge clause carries no `@confidence`.  Writing a low confidence onto the
clause prunes proof search and compounds on repeated application, which
measured during the bridge study (the memo is a local archive).
"""

import contextlib
import copy
import json

import utils

# The isolated conversion configuration.  Everything the base preset does for
# vocabulary and shape is kept; only what destroys defeasibility or deletes a
# selected condition is turned off.
BRIDGE_OPTION_OVERRIDES = {
    "typeenrich_flag": False,   # off: its `plural` sub-gate gates the strict
                                # finaliser, which unwraps `normally` and drops
                                # `$block`
    "guarddrop_flag": False,    # off: it deleted isa(animal, ?V2) from both
                                # animal-lover bridges in the 08-10 gk pilot
    "noexceptions_flag": False,  # explicit: blockers are the point
}

# `utils.LITBRIDGE_CLAUSE_PREFIX` is the same string; the proof renderer reads
# it back off a clause name to say "added rule" instead of "background
# knowledge", so the two must not drift apart.
PROVENANCE = utils.LITBRIDGE_CLAUSE_PREFIX + "%s_%s_%d"
HYPOTHESIS_PROVENANCE = utils.LITBRIDGE_CLAUSE_PREFIX + "%s_%d"


class BridgeError(Exception):
  """The bridge cannot be built.  Never worked around."""


# ---------------------------------------------------------------- shape

def _split_prefix(pkg):
  """-> (world, [bound vars], inner formula) for a compiled rule package."""
  if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "holds"):
    raise BridgeError("not a holds package: %s" % json.dumps(pkg)[:80])
  world, f = pkg[1], pkg[2]
  bound = []
  while isinstance(f, list) and f and f[0] == "forall" and len(f) >= 3:
    bound.append(f[1])
    f = f[2]
  return world, bound, f


def _rebuild(world, bound, inner):
  out = inner
  for v in reversed(bound):
    out = ["forall", v, out]
  return ["holds", world, out]


def to_defeasible_shape(pkg):
  """`forall vars . normally(A -> B)`  ->  `forall vars . A -> normally(B)`.

  Idempotent, and it refuses anything that is not a quantified implication
  rather than guessing.
  """
  world, bound, f = _split_prefix(pkg)
  if isinstance(f, list) and f and f[0] == "normally" and len(f) == 2:
    f = f[1]
  if not (isinstance(f, list) and len(f) == 3 and f[0] == "implies"):
    raise BridgeError("not a quantified implication: %s"
                      % json.dumps(pkg)[:80])
  head = f[2]
  if not (isinstance(head, list) and head and head[0] == "normally"):
    head = ["normally", head]
  return _rebuild(world, bound, ["implies", f[1], head])


# ---------------------------------------------------------------- conversion

def live_options():
  """The options this run converted its theory under, minus what kills a bridge.

  Call this BEFORE the first conversion.  `scoped` replaces `globals.options`
  for the duration of a conversion, so a call made inside one would read the
  scope rather than the run.  The result is a complete option dict and is
  meant to be captured once per case and passed down as `configuration`.
  """
  import globals as g
  opts = copy.deepcopy(g.options)
  for k in opts:
    if str(k).startswith("nofix_"):
      opts[k] = False
  # prenorm is a pre-Stage-1 wording phase; a bridge starts from stored Stage 2
  if "prenorm_flag" in opts:
    opts["prenorm_flag"] = False
  opts.update(BRIDGE_OPTION_OVERRIDES)
  return opts


def bridge_options(base_configuration):
  """The option set the bridge is converted under.

  A dict is a complete option set the caller already resolved — the run's own,
  from `live_options`.  It is returned as it is.

  A string is the label a stored case carries, for a replay whose live options
  are the runner's and not the case's.  Then the set is rebuilt from the base
  theory's configuration, so predicate canonicalization, entity merging and the
  event encoding stay compatible with the clauses the bridge has to unify with,
  and exactly the passes that would destroy it are turned off.
  """
  if isinstance(base_configuration, dict):
    return dict(base_configuration)
  import os
  import sys
  tools = os.path.join(os.path.dirname(os.path.dirname(
      os.path.abspath(__file__))), "tools")
  if tools not in sys.path:                  # a replay may run with solver/ alone
    sys.path.append(tools)
  import replay_case
  overrides = {}
  if base_configuration == "abstracted":
    overrides.update(replay_case._abstract_max_options(noprenorm=True))
  overrides.update(BRIDGE_OPTION_OVERRIDES)
  return full_options(overrides)


def _convert(stage2, stage1, opts):
  """One conversion inside a complete, isolated option scope."""
  import globals as g
  import llmparse
  import logconvert
  import semnormalize
  with scoped(opts):
    s1, s2 = copy.deepcopy(stage1), copy.deepcopy(stage2)
    stats = llmparse._make_stats()
    llmparse._fill_missing_asu_time(s1, stats)
    s2 = llmparse._repair_entity_ids(s1, s2, stats)
    fixes = []
    logic = logconvert.rawlogic_convert(s2, s1, fixes)
    if logic is None:
      raise BridgeError("rawlogic_convert returned None")
    if not g.options.get("nosemnormal_flag"):
      logic = semnormalize.sem_normalize_clauses(logic)
  return logic, fixes


def _base_uses_ctxt_terms(base_clauses):
  return "$ctxt" in json.dumps(base_clauses or [])


def _share_ctxt(clauses, counter):
  """Collapse each clause's `$ctxt` terms to one shared fresh `?:Cu` variable.

  This is step 1 of the strict finaliser, and only that step.  The finaliser
  itself cannot be used because it also unwraps `normally` and drops
  `$block`, which is the whole point of a bridge; but its context handling is
  what the base theory went through, so a bridge appended to such a theory has
  to match it or the context slots will not line up.
  """
  out = []
  for c in clauses:
    c = copy.deepcopy(c)
    counter[0] += 1
    var = "?:Cub%d" % counter[0]

    def walk(node):
      if isinstance(node, list):
        if node and node[0] == "$ctxt":
          return var
        return [walk(x) for x in node]
      return node
    for k in ("@logic", "@question"):
      if k in c:
        c[k] = walk(c[k])
    out.append(c)
  return out


def compile_bridge(case_id, world_name, pkg, stage1, stage2, configuration,
                   package_id="A1", base_clauses=None, hypothesis_id=None):
  """-> (clauses, record).  The clauses the bridge alone contributes.

  The case is converted only to obtain them in the case's own vocabulary and
  context conventions; everything else the conversion produces is discarded
  and the caller appends these to the STORED base theory.  Nothing about the
  base theory is recomputed.

  The population clauses a conversion emits alongside a rule are reported
  separately: they are not the rule.
  """
  edited = _splice(stage2, package_id, pkg)
  clauses, fixes = _convert(edited, stage1, bridge_options(configuration))
  mine = [c for c in clauses
          if str(c.get("@name", "")).startswith("sent_%s" % package_id)]
  if not mine:
    raise BridgeError("conversion produced no clause for the bridge")
  # context compatibility: match whatever the base theory did
  collapsed = base_clauses is not None and not _base_uses_ctxt_terms(
      base_clauses)
  if collapsed:
    mine = _share_ctxt(mine, [0])
  out, rule_idx, pop_idx, provenance = [], [], [], {}
  for i, c in enumerate(mine, start=1):
    c = copy.deepcopy(c)
    c["@name"] = (HYPOTHESIS_PROVENANCE % (hypothesis_id, i)
                  if hypothesis_id else
                  PROVENANCE % (case_id, world_name, i))
    if hypothesis_id:
      provenance[c["@name"]] = hypothesis_id
    if c.get("@sourcetype") == "populate":
      pop_idx.append(c["@name"])
    else:
      rule_idx.append(c["@name"])
    out.append(c)
  blob = json.dumps(out)
  rec = {
      "case_id": case_id, "world": world_name,
      "hypothesis_id": hypothesis_id,
      "clause_provenance": provenance,
      "options": {k: bridge_options(configuration)[k]
                  for k in sorted(BRIDGE_OPTION_OVERRIDES)},
      "base_configuration": configuration,
      "rule_clause_names": rule_idx,
      "population_clause_names": pop_idx,
      "has_block": "$block" in blob,
      "clause_count": len(out),
      "context_terms_collapsed_to_variables": collapsed,
      "context_policy": ("the base theory holds no $ctxt term, so the "
                         "bridge's were collapsed to one shared variable per "
                         "clause, as the base's were"
                         if collapsed else
                         "the base theory holds $ctxt terms, so the bridge's "
                         "were left as they are" if base_clauses is not None
                         else "no base theory given; context left as "
                              "converted"),
      "converter_notes": fixes,
  }
  return out, rec


def _splice(stage2, pid, pkg):
  if not (isinstance(stage2, list) and stage2 and stage2[0] == "and"):
    raise BridgeError("stage2 is not an [\"and\", ...] list")
  out = copy.deepcopy(stage2)
  for item in out[1:]:
    if isinstance(item, list) and len(item) >= 2 and item[0] == "@id" \
            and item[1] == pid:
      raise BridgeError("%s already exists in this Stage 2" % pid)
  out.append(["@id", pid, copy.deepcopy(pkg)])
  return out


# ---------------------------------------------------------------- inspection

def has_block(clauses):
  return "$block" in json.dumps(clauses)


# ---------------------------------------------------------------- option scope

# `globals.set_global_options` MERGES: it writes the keys it is given and leaves
# every other key at whatever the previous caller set.  That is fine for a run
# configured once, and wrong for a bridge, whose conversion runs between two
# conversions of the base theory.  It has already produced one false finding: a
# `standard` conversion that had inherited `abstract-max` flags and was reported
# as evidence about `normally` placement.

_PRISTINE = [None]


def defaults():
  """A copy of `globals.options` as the module defines it.

  Captured the first time it is asked for.  Import this module before any
  conversion runs if the process configures options at start-up and you want
  the shipped defaults rather than that configuration.
  """
  import globals as g
  if _PRISTINE[0] is None:
    if not g.options:
      raise RuntimeError("globals.options is empty; the defaults cannot "
                         "be captured from it")
    _PRISTINE[0] = copy.deepcopy(g.options)
  return copy.deepcopy(_PRISTINE[0])


def full_options(overrides=None):
  """The complete option dict for a conversion: defaults + overrides."""
  opts = defaults()
  for k in opts:
    if k.startswith("nofix_"):
      opts[k] = False
  for k, v in (overrides or {}).items():
    if k not in opts:
      raise KeyError("option %r is not recognized" % k)
    opts[k] = v
  return opts


@contextlib.contextmanager
def scoped(overrides=None, **kw):
  """Run a block with a complete, isolated option state."""
  import globals as g
  merged = dict(overrides or {})
  merged.update(kw)
  # build the new state BEFORE touching the live dict: `full_options` reads
  # the defaults, and the defaults are captured lazily from that same dict, so
  # clearing first would snapshot an empty one
  new = full_options(merged)
  before = copy.deepcopy(g.options)
  try:
    g.options.clear()
    g.options.update(new)
    yield g.options
  finally:
    g.options.clear()
    g.options.update(before)


def is_pristine_for(names):
  """True if every named option currently equals its shipped default."""
  import globals as g
  d = defaults()
  return all(g.options.get(n) == d.get(n) for n in names)
