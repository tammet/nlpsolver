"""Action profile: planning summaries, the reference interpreter (checkpoint P).

A planning summary describes an action sequence conditionally on its
executability: World, a list of positive relevant facts, and Progress, one
rough number computed from that list and fixed goal data.  This module reads
a compiled profile (`lc_action_summary.compile_profile`) and nothing else: no
source artifact, no clause, no replay, no prover and no model.

  profile     `planning_summary_profile/2`: {"schema", "profile_id", "semantic",
              "binding"}.  `profile_id` is the SHA-256 of the canonical JSON of
              `semantic`.  `binding` is provenance; the interpreter never reads it.
  terms       a string, an integer, or a nonempty list whose first element is
              its functor.  A pattern also admits {"var": NAME}, local to one
              operation, and {"wildcard": true}, an independent match-any
              position.  A GK variable (`?:X`) is never ground.
  operations  forget(pattern)           remove the old facts that match
              insert(fact, guards)      add a fact when its positive guards
                                        hold in the OLD list or the static facts
              negative_write(pattern)   veto a matching insertion of this step
              Each operation has its own action pattern and fresh bindings.
              All operations of a step are simultaneous.
  lossy       an inherited bit: a conservative operation may have removed or
              omitted a fact of the tracked families.  A forget with loss
              `if_removed` sets it when it removes a fact that no certain
              forget covers and no insertion restores; loss `always` sets it
              whenever the action matches.  An insertion sets it when its
              guards give no binding, when a guard binds a variable (a join
              over a positive list can miss a binding), or when a negative
              write vetoes it.  The bit is no statement about validity.
  cache       one prefix tree per loaded profile.  A node is keyed by the
              structural value of a ground action and has an immutable record
              (parent, action, world, progress, reasons, lossy).  A stored
              prefix costs no transition evaluation; `advance_calls` counts them.

  numbers     every integer of the semantic part and every score is within
              -(2**53-1) .. 2**53-1.  A profile outside the range is refused; a
              score outside it is undefined with reason `numeric_range`.
  reasons     the fixed codes of `REASONS`.  A situation term is inspected in
              one order: depth_limit, open_root, malformed_situation,
              wrong_root, then the defect of its oldest defective action.
  limits      one admission contract, shared with the native evaluator: at
              most MAX_DEPTH actions in a situation term; at most
              MAX_TERM_DEPTH levels in an action or a fact (the term itself
              is level 1, each nested compound term one more); integers of
              the portable range; at most MAX_VARIABLES variables in one
              operation; arities and indexes up to MAX_INDEX; no zero
              character in a string.  A ground action over a limit is
              `term_depth_limit` or `numeric_range`, and a value outside the
              term language is `unsupported_term`: neither is `not_ground`,
              which means a variable.

The context owns a copy of the semantic part: a later change of the caller's
profile object changes no calculation.  Nothing here checks executability,
and a record is no reachability claim.
"""

import hashlib
import json

SCHEMA = "planning_summary_profile/2"
CONTRACT = "planning_summary/1"
NORMALIZER = 1
MAX_DEPTH = 4096            # the defensive bound on the number of actions of one situation term
MAX_INT = 2 ** 53 - 1       # the portable integer range: exact also for a reader that holds numbers as doubles
MAX_TERM_DEPTH = 64         # levels of one action or fact term
MAX_VARIABLES = 64          # variables of one operation
MAX_INDEX = 1000000         # constructor and predicate arities, path indexes
DO = "$do"
ROLES = ("answer_plan", "query_plan", "reachable", "context")
# the defects of one action term, the most specific first: the defect of an action is the first of these that any
# part of it has
ACTION_DEFECTS = ("term_depth_limit", "numeric_range", "unsupported_term", "not_ground")
REASONS = {"situation": ("depth_limit", "open_root", "malformed_situation", "wrong_root") + ACTION_DEFECTS,
           "update": ("no_rule_for_action", "invalid_operation", "term_depth_limit"),
           "score": ("location_missing", "location_ambiguous", "support_conflict", "support_cycle", "witness_goal",
                     "unsupported_goal", "computed_goal", "goal_family_unavailable", "numeric_range")}
KINDS = ("forget", "insert", "negative_write")
LOSS = (None, "if_removed", "always")
UNITS = {"goal_count": "missing_goal_atoms", "blocks_links": "missing_goals_plus_obstructions",
         "route_distance": "remaining_route_legs", "route_milestones": "weighted_route_legs_minus_ready_milestones"}
SEMANTIC_FIELDS = ("contract", "root", "scope", "families", "initial", "static", "constructors", "operations", "score",
                   "situation_constructor", "situation_positions")


class ProfileError(Exception):
  """A profile outside the closed profile language."""


# ---------------------------------------------------------------------------
# canonical JSON and identity


def _integers_only(x):
  if isinstance(x, float):
    raise ProfileError("a profile holds integers only, got %r" % x)
  if isinstance(x, int) and not -MAX_INT <= x <= MAX_INT:
    raise ProfileError("an integer outside -(2**53-1) .. 2**53-1: %r" % x)
  if isinstance(x, str) and "\x00" in x:
    raise ProfileError("a string with a zero character")
  if isinstance(x, dict):
    for k, v in x.items():
      if not isinstance(k, str) or "\x00" in k:
        raise ProfileError("an object key is a string without a zero character, got %r" % (k,))
      _integers_only(v)
  elif isinstance(x, (list, tuple)):
    for v in x:
      _integers_only(v)


def canonical(obj):
  """Sorted keys, compact separators, UTF-8 without ASCII escaping, integers only."""
  _integers_only(obj)
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
  return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def profile_id(semantic):
  return "sha256:" + digest(semantic)


def _no_duplicates(pairs):
  out = {}
  for k, v in pairs:
    if k in out:
      raise ProfileError("duplicate object key %r" % k)
    out[k] = v
  return out


def _no_constant(name):
  raise ProfileError("%s is no JSON number" % name)


def loads(text):
  """A profile from its JSON text.  A duplicate object key, NaN and Infinity are refused everywhere.  The semantic
  part holds integers of the portable range only; the binding is provenance and may hold another finite number."""
  try:
    obj = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
  except ValueError as e:
    raise ProfileError("the profile does not parse: %s" % e)
  if isinstance(obj, dict):
    _integers_only(obj.get("semantic"))
  return obj


# ---------------------------------------------------------------------------
# terms and patterns


def is_gk_var(t):
  return isinstance(t, str) and t.startswith("?:")


def term_defect(t):
  """None for a ground term of the term language, else its defect, one of ACTION_DEFECTS.

  term_depth_limit  a compound term below level MAX_TERM_DEPTH (it is not read further)
  numeric_range     an integer outside the portable range
  unsupported_term  an empty list, a zero character, or a value that is no string, integer or list
  not_ground        a GK variable
  """
  found = set()
  stack = [(t, 1)]
  while stack:
    x, level = stack.pop()
    if isinstance(x, (list, tuple)):
      if not x:
        found.add("unsupported_term")
      elif level > MAX_TERM_DEPTH:
        found.add("term_depth_limit")
      else:
        stack.extend((y, level + 1) for y in x)
    elif isinstance(x, bool) or not isinstance(x, (str, int)):
      found.add("unsupported_term")
    elif isinstance(x, int):
      if not -MAX_INT <= x <= MAX_INT:
        found.add("numeric_range")
    elif is_gk_var(x):
      found.add("not_ground")
    elif "\x00" in x:
      found.add("unsupported_term")
  for reason in ACTION_DEFECTS:
    if reason in found:
      return reason
  return None


def is_ground(t):
  """A ground term of the term language: no variable, no pattern object, inside every limit."""
  return term_defect(t) is None


def freeze(t):
  return tuple(freeze(x) for x in t) if isinstance(t, (list, tuple)) else t


def thaw(t):
  return [thaw(x) for x in t] if isinstance(t, tuple) else t


def order_key(t):
  """The canonical structural order: integers, then strings by their bytes, then compound terms by functor, arity and
  arguments."""
  if isinstance(t, (list, tuple)):
    return (2, order_key(t[0]), len(t) - 1, tuple(order_key(x) for x in t[1:]))
  if isinstance(t, int):
    return (0, t)
  return (1, t.encode("utf-8"))


def _is_var(p):
  return isinstance(p, dict) and list(p) == ["var"] and isinstance(p["var"], str)


def _is_wild(p):
  return isinstance(p, dict) and p == {"wildcard": True}


def match(pattern, term, env):
  """The extension of `env` under which the pattern equals the ground term, or None.  `env` is not changed."""
  env = dict(env)
  stack = [(pattern, term)]
  while stack:
    p, t = stack.pop()
    if _is_wild(p):
      continue
    if _is_var(p):
      if p["var"] in env:
        if env[p["var"]] != t:
          return None
      else:
        env[p["var"]] = t
    elif isinstance(p, (list, tuple)):
      if not isinstance(t, tuple) or len(t) != len(p):
        return None
      stack.extend(zip(p, t))
    elif p != t:
      return None
  return env


def instantiate(pattern, env):
  """The pattern with its bound variables replaced; an unbound variable and a wildcard stay."""
  if _is_var(pattern):
    return env.get(pattern["var"], pattern)
  if isinstance(pattern, (list, tuple)):
    return tuple(instantiate(x, env) for x in pattern)
  return pattern


def _vars(p, out):
  if _is_var(p):
    if p["var"] not in out:
      out.append(p["var"])
  elif isinstance(p, (list, tuple)):
    for x in p:
      _vars(x, out)
  return out


def _has_wild(p):
  return _is_wild(p) or (isinstance(p, (list, tuple)) and any(_has_wild(x) for x in p))


def _rename(p, names):
  if _is_var(p):
    return {"var": names[p["var"]]}
  if isinstance(p, (list, tuple)):
    return [_rename(x, names) for x in p]
  return p


def normalize_operation(op):
  """Variables renamed V0, V1, ... by first occurrence in the action pattern, the target, then the guards in their
  emitted order; the renamed guards sorted and deduplicated.  Repeated variables stay repeated."""
  order = _vars(op["action"], [])
  _vars(op.get("pattern", op.get("fact")), order)
  for g in op.get("guards") or []:
    _vars(g["atom"], order)
  names = {v: "V%d" % n for n, v in enumerate(order)}
  out = {"kind": op["kind"], "action": _rename(op["action"], names)}
  if op["kind"] == "insert":
    out["fact"] = _rename(op["fact"], names)
    guards = [{"scope": g["scope"], "atom": _rename(g["atom"], names)} for g in op.get("guards") or []]
    out["guards"] = [json.loads(x) for x in sorted({canonical(g) for g in guards})]
  else:
    out["pattern"] = _rename(op["pattern"], names)
    if op["kind"] == "forget":
      out["loss"] = op.get("loss")
  return out


def normalize(semantic):
  """The semantic part in its normal form: operations, facts, families, positions and milestones sorted and deduplicated by
  canonical JSON.  The order of operations never controls an update."""
  def uniq(items):
    return [json.loads(x) for x in sorted({canonical(i) for i in items})]
  try:
    out = dict(semantic)
    out["operations"] = uniq(normalize_operation(o) for o in semantic["operations"])
    out["families"] = sorted(set(semantic["families"]))
    out["static"] = uniq(semantic["static"])
    out["initial"] = {"facts": uniq(semantic["initial"]["facts"]), "lossy": semantic["initial"]["lossy"]}
    out["situation_positions"] = uniq(semantic["situation_positions"])
    if isinstance(out["score"], dict) and "milestones" in out["score"]:
      out["score"] = dict(out["score"], milestones=uniq(out["score"]["milestones"]))
    return out
  except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
    raise ProfileError("a semantic part outside the profile language: %s: %s" % (type(e).__name__, e))


# ---------------------------------------------------------------------------
# families


def family_of(fact):
  """rel:<name>, property:<value> or have for a fact of a fluent shape, else None."""
  if not isinstance(fact, (list, tuple)) or not fact:
    return None
  if fact[0] == "is rel2" and len(fact) == 4 and isinstance(fact[1], str):
    return "rel:" + fact[1]
  if fact[0] == "has property" and len(fact) == 3 and isinstance(fact[1], str):
    return "property:" + fact[1]
  if fact[0] == "have" and len(fact) == 3:
    return "have"
  return None


def _family_ok(name):
  return isinstance(name, str) and (name == "have" or (name.startswith(("rel:", "property:")) and name.split(":", 1)[1] != ""))


# ---------------------------------------------------------------------------
# validation of the closed profile language


def _need(cond, message):
  if not cond:
    raise ProfileError(message)


def _is_int(x):
  return isinstance(x, int) and not isinstance(x, bool)


def _check_pattern(p, where, wild, level=1):
  if _is_var(p):
    return
  if _is_wild(p):
    _need(wild, "%s: a wildcard is not admitted here" % where)
    return
  if isinstance(p, list):
    _need(p and isinstance(p[0], str), "%s: a compound term starts with its functor" % where)
    _need(level <= MAX_TERM_DEPTH, "%s: a term nested deeper than %d" % (where, MAX_TERM_DEPTH))
    for x in p[1:]:
      _check_pattern(x, where, wild, level + 1)
    return
  _need((isinstance(p, str) or _is_int(p)) and not is_gk_var(p), "%s: unknown term %r" % (where, p))


def _check_operation(op, constructors, families, n):
  where = "operation %d" % n
  _need(isinstance(op, dict) and op.get("kind") in KINDS, "%s: kind is one of %s" % (where, ", ".join(KINDS)))
  act = op.get("action")
  _need(isinstance(act, list) and act and isinstance(act[0], str) and constructors.get(act[0]) == len(act) - 1,
        "%s: the action pattern names a constructor of the profile with its arity" % where)
  _check_pattern(act, where, False)
  bound = _vars(act, [])
  if op["kind"] == "insert":
    _need(sorted(op) == ["action", "fact", "guards", "kind"], "%s: an insert has action, fact and guards" % where)
    _check_pattern(op["fact"], where, False)
    _need(isinstance(op["guards"], list), "%s: guards is a list" % where)
    for g in op["guards"]:
      _need(isinstance(g, dict) and sorted(g) == ["atom", "scope"] and g["scope"] in ("old", "static"),
            "%s: a guard is {scope: old | static, atom}" % where)
      _check_pattern(g["atom"], where, False)
      _need(isinstance(g["atom"], list), "%s: a guard atom is a compound term" % where)
      _need(g["scope"] == "static" or family_of(g["atom"]) in families, "%s: an old guard reads a tracked family" % where)
      _vars(g["atom"], bound)
    _need(all(v in bound for v in _vars(op["fact"], [])), "%s: a variable of the fact is bound by no action slot and no guard" % where)
    fam = family_of(instantiate(op["fact"], {}))
    _need(fam in families, "%s: the fact belongs to no tracked family" % where)
    _need(len(bound) <= MAX_VARIABLES, "%s: more than %d variables" % (where, MAX_VARIABLES))
  else:
    keys = ["action", "kind", "loss", "pattern"] if op["kind"] == "forget" else ["action", "kind", "pattern"]
    _need(sorted(op) == keys, "%s: a %s has the fields %s" % (where, op["kind"], ", ".join(keys)))
    _need(op.get("loss") in LOSS, "%s: loss is null, if_removed or always" % where)
    _check_pattern(op["pattern"], where, True)
    _need(isinstance(op["pattern"], list) and family_of(op["pattern"]) in families,
          "%s: the pattern is a fact pattern of a tracked family" % where)
    _need(all(v in bound for v in _vars(op["pattern"], [])), "%s: a variable of the pattern is not in the action pattern" % where)
    _need(len(bound) <= MAX_VARIABLES, "%s: more than %d variables" % (where, MAX_VARIABLES))


def _check_score(score, families):
  _need(isinstance(score, dict) and "template" in score, "score is an object with a template")
  t = score["template"]
  if t is None:
    _need(sorted(score) == ["reason", "template"] and isinstance(score["reason"], str), "an undefined score has a reason")
    return
  _need(t in UNITS and score.get("units") == UNITS[t], "score.template is one of %s, with its units" % ", ".join(sorted(UNITS)))
  facts = lambda xs: isinstance(xs, list) and all(is_ground(x) and family_of(x) in families for x in xs)
  if t in ("goal_count", "blocks_links"):
    _need(facts(score.get("goal")) and score["goal"], "score.goal is a nonempty list of ground facts of tracked families")
  if t == "blocks_links":
    _need(sorted(score) == ["blocks", "goal", "template", "units"] and isinstance(score["blocks"], list)
          and all(isinstance(b, str) for b in score["blocks"]) and len(set(score["blocks"])) == len(score["blocks"]),
          "blocks_links has goal and blocks")
    _need(all(family_of(g) in ("rel:on", "rel:holding") for g in score["goal"]) and "rel:on" in families,
          "blocks_links reads on and holding goals and tracks rel:on")
  elif t == "goal_count":
    _need(sorted(score) == ["goal", "template", "units"], "goal_count has goal")
  else:
    keys = ["destination", "distance", "no_route_distance", "subject", "template", "units"]
    keys = sorted(keys + ["milestones"]) if t == "route_milestones" else keys
    _need(sorted(score) == keys, "%s has the fields %s" % (t, ", ".join(keys)))
    _need(isinstance(score["distance"], dict) and all(_is_int(v) and v >= 0 for v in score["distance"].values()),
          "score.distance maps a place to a number of legs")
    _need(_is_int(score["no_route_distance"]) and score["no_route_distance"] > 0, "score.no_route_distance is positive")
    _need(is_ground(score["subject"]) and is_ground(score["destination"]) and "rel:located_at" in families,
          "a route score has a ground subject and destination and tracks rel:located_at")
    if t == "route_milestones":
      ms = score["milestones"]
      _need(isinstance(ms, list) and ms and all(isinstance(m, dict) and sorted(m) == ["city", "fact"] and is_ground(m["city"])
                                                for m in ms) and facts([m["fact"] for m in ms]),
            "a milestone is {fact, city} with a ground fact of a tracked family")
      _need(len({canonical(m) for m in ms}) == len(ms), "a milestone is listed once for its city and fact")


def _check_position(p, n):
  where = "situation position %d" % n
  _need(isinstance(p, dict) and set(p) <= {"predicate", "arity", "path", "role", "via"}
        and {"predicate", "arity", "path", "role"} <= set(p), "%s: the fields are predicate, arity, path, role and an optional via" % where)
  _need(isinstance(p["predicate"], str) and p["predicate"] and p["role"] in ROLES, "%s: a predicate name and a role of %s" % (where, ", ".join(ROLES)))
  arity, path, via = p["arity"], p["path"], p.get("via")
  _need(arity == "variable" or (_is_int(arity) and 0 < arity <= MAX_INDEX), "%s: arity is a positive integer or variable" % where)
  _need(isinstance(path, list) and path and all(_is_int(i) and 0 < i <= MAX_INDEX for i in path), "%s: path is a nonempty list of argument indexes" % where)
  _need(arity == "variable" or path[0] <= arity, "%s: the path starts inside the arity" % where)
  if p["role"] == "context":
    _need(via == "$ctxt" and _is_int(arity) and path == [arity, 2], "%s: a context position is the situation slot of the last argument" % where)
  else:
    _need("via" not in p and len(path) == 1, "%s: a %s position is one direct argument" % (where, p["role"]))
    _need((arity == "variable") == (p["role"] == "answer_plan"), "%s: only an answer position has a variable arity" % where)
    _need(p["role"] == "query_plan" or path == [1], "%s: a %s position is the first argument" % (where, p["role"]))


def _validate(profile):
  _need(isinstance(profile, dict) and sorted(profile) == ["binding", "profile_id", "schema", "semantic"],
        "a profile has schema, profile_id, semantic and binding")
  _need(profile["schema"] == SCHEMA, "schema is %s" % SCHEMA)
  _need(isinstance(profile["binding"], dict), "binding is an object")
  sem = profile["semantic"]
  _need(isinstance(sem, dict) and sorted(sem) == sorted(SEMANTIC_FIELDS), "semantic has the fields %s" % ", ".join(SEMANTIC_FIELDS))
  _integers_only(sem)
  c = sem["contract"]
  _need(isinstance(c, dict) and sorted(c) == ["normalizer", "summary", "transport"] and c["summary"] == CONTRACT
        and _is_int(c["normalizer"]) and c["normalizer"] == NORMALIZER and (c["transport"] is None or isinstance(c["transport"], str)),
        "contract is {summary: %s, normalizer: %d, transport}" % (CONTRACT, NORMALIZER))
  _need(isinstance(sem["root"], str) and sem["root"] and not is_gk_var(sem["root"]), "root is a situation constant")
  _need(isinstance(sem["scope"], dict) and sem["scope"] == {"ambient": None, "knower": None}, "scope is {ambient: null, knower: null}")
  fams = sem["families"]
  _need(isinstance(fams, list) and fams and all(_family_ok(f) for f in fams), "families is a nonempty list of family names")
  ini = sem["initial"]
  _need(isinstance(ini, dict) and sorted(ini) == ["facts", "lossy"] and isinstance(ini["lossy"], bool)
        and isinstance(ini["facts"], list), "initial is {facts, lossy}")
  for f in ini["facts"]:
    _need(is_ground(f) and family_of(f) in fams, "an initial fact is a ground fact of a tracked family: %r" % (f,))
  _need(isinstance(sem["static"], list) and all(isinstance(f, list) and is_ground(f) and isinstance(f[0], str) for f in sem["static"]),
        "static is a list of ground facts")
  cons = sem["constructors"]
  _need(isinstance(cons, dict) and all(k and _is_int(v) and 0 <= v <= MAX_INDEX for k, v in cons.items()), "constructors maps a name to its arity")
  _need(isinstance(sem["operations"], list), "operations is a list")
  for n, op in enumerate(sem["operations"]):
    _check_operation(op, cons, fams, n)
  _check_score(sem["score"], fams)
  sc = sem["situation_constructor"]
  _need(isinstance(sc, dict) and sorted(sc) == ["action_arg", "arity", "functor", "parent_arg"] and sc["functor"] == DO
        and all(_is_int(sc[k]) for k in ("arity", "action_arg", "parent_arg")) and (sc["arity"], sc["action_arg"], sc["parent_arg"]) == (2, 1, 2),
        "the situation constructor is $do(action, parent)")
  _need(isinstance(sem["situation_positions"], list), "situation_positions is a list")
  for n, p in enumerate(sem["situation_positions"]):
    _check_position(p, n)
  _need(canonical(normalize(sem)) == canonical(sem), "the semantic part is not in normal form")
  _need(profile["profile_id"] == profile_id(sem), "profile_id is not the digest of the semantic part")


def validate(profile):
  """Raise ProfileError unless `profile` is a profile of the closed language whose identifier is that of its semantic
  part in normal form.  Malformed data of any kind gives ProfileError."""
  try:
    _validate(profile)
  except (KeyError, IndexError, TypeError, AttributeError, ValueError) as e:
    raise ProfileError("a profile outside the profile language: %s: %s" % (type(e).__name__, e))


# ---------------------------------------------------------------------------
# one transition


class _Index(object):
  def __init__(self, sem):
    sem = json.loads(canonical(sem))        # an owned copy: the caller's object is never read again
    self.root = sem["root"]
    self.families = set(sem["families"])
    self.constructors = dict(sem["constructors"])
    self.ops = {}
    for op in sem["operations"]:
      self.ops.setdefault(op["action"][0], []).append(op)
    self.static = {}
    for f in sem["static"]:
      self.static.setdefault(f[0], []).append(freeze(f))
    self.score = sem["score"]
    self.initial = sem["initial"]


def _join(guards, env, world, static):
  """The bindings under which every guard is in the old list or the static facts."""
  envs = [env]
  for g in guards:
    pool = world if g["scope"] == "old" else static.get(g["atom"][0], ())
    envs = [e2 for e in envs for f in pool for e2 in [match(g["atom"], f, e)] if e2 is not None]
    if not envs:
      break
  return envs


def advance(index, world, action):
  """(new world or None, reason, lossy) of one ground action on a world (a tuple of frozen facts).

  An action whose constructor the profile does not know gives None and
  `no_rule_for_action`, never the old world.  Executability is not checked.
  """
  if not (isinstance(action, tuple) and action and isinstance(action[0], str)
          and index.constructors.get(action[0]) == len(action) - 1):
    return None, "no_rule_for_action", False
  forgets, vetoes, proposals, lossy = [], [], [], False
  for op in index.ops.get(action[0], ()):
    env = match(op["action"], action, {})
    if env is None:
      continue
    if op["kind"] == "forget":
      forgets.append((instantiate(op["pattern"], env), op["loss"]))
      lossy = lossy or op["loss"] == "always"
    elif op["kind"] == "negative_write":
      vetoes.append(instantiate(op["pattern"], env))
    else:
      proposals.append((op, env))
  kept, uncertain = [], []
  for f in world:
    hits = [loss for p, loss in forgets if match(p, f, {}) is not None]
    if not hits:
      kept.append(f)
    elif all(loss is not None for loss in hits):
      uncertain.append(f)
  added = set()
  for op, env in proposals:
    found = _join(op["guards"], env, world, index.static)
    if not found or any(len(e) != len(env) for e in found):
      lossy = True            # a guard not established, or bound by a join that a positive list can leave incomplete
    for e in found:
      f = instantiate(op["fact"], e)
      why = term_defect(f)
      if why == "term_depth_limit":
        return None, "term_depth_limit", False      # a deep action argument put inside the fact's own structure
      if why or family_of(f) not in index.families:
        return None, "invalid_operation", False
      if any(match(p, f, {}) is not None for p in vetoes):
        lossy = True          # an opposite write is possible: the fact is not inserted
      else:
        added.add(f)
  if any(f not in added for f in uncertain):
    lossy = True
  return tuple(sorted(set(kept) | added, key=order_key)), None, lossy


# ---------------------------------------------------------------------------
# the four scores


def _goal_count(score, facts):
  return -sum(1 for g in score["goal"] if freeze(g) not in facts), None


def _blocks_links(score, facts):
  below, above = {}, {}
  for f in facts:
    if f[0] == "is rel2" and f[1] == "on":
      if f[2] in below and below[f[2]] != f[3]:
        return None, "support_conflict"
      below[f[2]] = f[3]
      above.setdefault(f[3], set()).add(f[2])
  for x in below:
    seen, y = {x}, below[x]
    while y in below:
      if y in seen:
        return None, "support_cycle"
      seen.add(y)
      y = below[y]
    if y in seen:
      return None, "support_cycle"

  def over(x):
    out, todo = set(), [x]
    while todo:
      for z in above.get(todo.pop(), ()):
        if z not in out:
          out.add(z)
          todo.append(z)
    return out
  blocks, missing, obstructors = set(score["blocks"]), 0, set()
  for g in score["goal"]:
    if freeze(g) in facts:
      continue
    missing += 1
    obstructors |= over(g[3] if g[1] == "holding" else g[2])
    if g[1] == "on" and g[3] in blocks:
      obstructors |= over(g[3])
  return -missing - len(obstructors), None


def _route(score, facts):
  here = [f[3] for f in facts if f[0] == "is rel2" and f[1] == "located_at" and f[2] == freeze(score["subject"])]
  if len(here) != 1:
    return None, "location_missing" if not here else "location_ambiguous"
  city = here[0]
  if city == freeze(score["destination"]):
    return 0, None
  d = score["distance"].get(city, score["no_route_distance"]) if isinstance(city, str) else score["no_route_distance"]
  if score["template"] == "route_distance":
    return -d, None
  ms = score["milestones"]
  ready = sum(1 for m in ms if freeze(m["city"]) == city and freeze(m["fact"]) in facts)
  return -(len(ms) + 1) * d + ready, None       # Python integers do not overflow; `score_or_reason` checks the range


_SCORES = {"goal_count": _goal_count, "blocks_links": _blocks_links, "route_distance": _route, "route_milestones": _route}


def score_or_reason(index, world):
  """(Progress, reason): a number, larger is better, or None with the reason."""
  s = index.score
  if s["template"] is None:
    return None, s["reason"]
  value, why = _SCORES[s["template"]](s, set(world))
  if value is not None and not -MAX_INT <= value <= MAX_INT:
    return None, "numeric_range"
  return value, why


# ---------------------------------------------------------------------------
# the prefix tree


class Record(object):
  """One immutable calculation record: a prefix's World and Progress, conditional on its executability."""
  __slots__ = ("parent", "action", "world", "progress", "world_reason", "progress_reason", "lossy", "depth")

  def __init__(self, parent, action, world, progress, world_reason, progress_reason, lossy):
    object.__setattr__(self, "parent", parent)
    object.__setattr__(self, "action", action)
    object.__setattr__(self, "world", world)
    object.__setattr__(self, "progress", progress)
    object.__setattr__(self, "world_reason", world_reason)
    object.__setattr__(self, "progress_reason", progress_reason)
    object.__setattr__(self, "lossy", lossy)
    object.__setattr__(self, "depth", 0 if parent is None else parent.depth + 1)

  def __setattr__(self, name, value):
    raise AttributeError("a calculation record is immutable")

  @property
  def calculation(self):
    return "unavailable" if self.world is None else "partial" if self.progress is None else "computed"

  def facts(self):
    """World as a JSON array, or None."""
    return None if self.world is None else [thaw(f) for f in self.world]

  def as_json(self):
    return {"world": self.facts(), "progress": self.progress, "calculation": self.calculation, "lossy": self.lossy,
            "world_reason": self.world_reason, "progress_reason": self.progress_reason}


class _Node(object):
  __slots__ = ("record", "children")

  def __init__(self, record):
    self.record = record
    self.children = {}


def split_situation(term, root):
  """(actions in execution order as frozen terms, reason) of a situation term; the actions are None on a failure.

  One fixed order for a term with several defects: depth_limit (more than MAX_DEPTH actions), open_root (the chain
  ends in a variable), malformed_situation (it ends in no constant), wrong_root, then the defect of the oldest
  defective action (`term_defect`).  The walk is iterative.
  """
  acts, s = [], term
  while isinstance(s, (list, tuple)) and len(s) == 3 and s[0] == DO:
    acts.append(s[1])
    s = s[2]
    if len(acts) > MAX_DEPTH:
      return None, "depth_limit"
  if is_gk_var(s):
    return None, "open_root"
  if not isinstance(s, str):
    return None, "malformed_situation"
  if s != root:
    return None, "wrong_root"
  acts.reverse()
  for a in acts:
    why = term_defect(a)
    if why:
      return None, why
  return [freeze(a) for a in acts], None


class Context(object):
  """A loaded profile with its prefix tree.  The cache belongs to this object and to no clause."""

  def __init__(self, profile):
    validate(profile)
    sem = profile["semantic"]
    self.profile_id = profile["profile_id"]
    self.template = sem["score"]["template"]
    self.units = sem["score"].get("units")
    self.index = _Index(sem)
    self.advance_calls = 0
    world = tuple(sorted({freeze(f) for f in self.index.initial["facts"]}, key=order_key))
    progress, why = score_or_reason(self.index, world)
    self.root_node = _Node(Record(None, None, world, progress, None, why, self.index.initial["lossy"]))

  def get(self, situation):
    """(record, reason).  The record of a ground rooted situation, each new prefix calculated once from its parent;
    (None, reason) for a term that is no ground rooted situation.  With a record, the reason is its `world_reason`:
    None, or the reason of the update that failed at this prefix or before it."""
    actions, reason = split_situation(situation, self.index.root)
    if actions is None:
      return None, reason
    rec = self._walk(actions)
    return rec, rec.world_reason

  def get_actions(self, actions):
    """The record after a list of ground actions (oldest first) from the root.  ValueError with `depth_limit` or
    the defect of the oldest defective action for another input; no record is stored for it."""
    actions = list(actions)
    if len(actions) > MAX_DEPTH:
      raise ValueError("depth_limit")
    for a in actions:
      if term_defect(a):
        raise ValueError(term_defect(a))
    return self._walk([freeze(a) for a in actions])

  def _walk(self, actions):
    """The traversal behind `get` and `get_actions`: frozen ground actions only."""
    node = self.root_node
    for action in actions:
      child = node.children.get(action)
      if child is None:
        parent = node.record
        if parent.world is None:
          rec = Record(parent, action, None, None, parent.world_reason, parent.world_reason, parent.lossy)
        else:
          self.advance_calls += 1
          world, reason, lossy = advance(self.index, parent.world, action)
          progress, why = score_or_reason(self.index, world) if world is not None else (None, reason)
          rec = Record(parent, action, world, progress, reason, why, parent.lossy or lossy)
        child = node.children[action] = _Node(rec)
      node = child
    return node.record

  def observe(self, situation):
    """The reference of the clause lookup for one situation term: {whole, record, reason}.

    A ground rooted situation gives its record with whole true; the reason is the record's `world_reason` (None
    unless an update failed).  A rooted term with a defective action gives the record of the prefix below its oldest
    defective action with whole false and that action's defect as the reason (`not_ground` for a variable); a failed
    update of that prefix is in the record's `world_reason`.  Any other term gives no record and its reason.
    """
    actions, reason = split_situation(situation, self.index.root)
    if actions is not None:
      rec = self._walk(actions)
      return {"whole": True, "record": rec, "reason": rec.world_reason}
    if reason not in ACTION_DEFECTS:
      return {"whole": False, "record": None, "reason": reason}
    chain, s = [], situation
    while isinstance(s, (list, tuple)) and len(s) == 3 and s[0] == DO:
      chain.append(s[1])
      s = s[2]
    chain.reverse()
    cut = min(i for i, a in enumerate(chain) if term_defect(a))
    return {"whole": False, "record": self._walk([freeze(a) for a in chain[:cut]]), "reason": reason}


def load(profile):
  return Context(profile)
