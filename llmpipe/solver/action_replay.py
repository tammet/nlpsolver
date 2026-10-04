"""Action profile: the independent replay of a plan or a supplied sequence over the finite fragment.

The replay checks a supplied action sequence against a supported source
artifact, from the reviewed source laws and separately written transitions of
the five constructors.  It never reads the compiled clauses or the library
file: the shared parts are the identity map, the unit forms of the validator,
the source's type records (`action_route.TYPE_KINDS`: a stated class of a law
sentence's referent, the Stage-1 person convention, a lexical type of a past
description), the constructor arities and the query selection (planning
root, exclusions).

State.  Signed ground fluent facts, each sign with its provenance: the
initial unit, `library`, a text effect unit, or `persisted`.  An atom can hold
both signs (contested), one, or none (unknown).  Possession is per owner
(`have(A, X)`).  Static facts (`isa`, `connected`) and their stated negations
are kept apart; `surface` and `standard_mode` come from the library's lists,
and `differ(X, Y)` holds for two different concrete ids of the identity map.

Values.  A value is a pair of supports: positive and negative.  True has
positive support only, false negative only, both has both, unknown neither.
A missing fact is unknown: it satisfies neither a positive nor a negative
condition.  A conjunction has positive support when every conjunct has it and
negative support when some conjunct has it; a disjunction the other way round;
negation swaps the two; exists and forall are disjunction and conjunction over
the finite domain.  So both-and-unknown is false and both-or-unknown is true.

Rules.  A strict rule (a sufficient action rule, a denial, a restriction
check, a text effect, a standing law, a conditional description) applies when
its condition has positive support; its head then gets positive support.
Negative support of the condition licenses nothing.

Contested premises.  A support records the base atoms with both signs that it
rests on; a clean support rests on none.  A rule's head gets the support of
its condition; a sign keeps the best of its supports (a clean one when there
is one, else the one with the fewest premises, ties in sorted order).  A
recorded support is replaced only by one of lower rank in that order.  The
premise sets are finite, so a fixpoint over cyclic rules ends.  A candidate whose steps and goal
hold, but only through a contested premise, is not validated: it is
`not_checked` with the component `contested_premise`.  A failing step or a
false goal whose negative support rests on one keeps the verdict `invalid`,
and `verification` gives `not_checked`, not No.  A step with both positive and
negative support is `contested`.

A step.  The action is executable when some sufficient path holds and no
explicit negative support exists:

  paths     the library defaults (a person moves by a standard mode over a
            stated connection; a hand takes a block; a hand puts a held block
            on a block or on a surface), and each source availability rule
            completed with its constructor's template (move over a stated
            connection, or its stated endpoints when the rule identifies
            them; take; put_on onto a block or a surface; put_in; change)
  hook      every restriction of the constructor: satisfied when the action
            unifies with its pattern and its required condition has positive
            support, or when it provably does not apply (another concrete id
            in a constant slot or between two slots of one variable, a guard
            with negative support; a witness or a lexical value proves no
            nonmatch)
  defaults  a library default or a `normally` source rule is blocked by an
            explicit denial of the same action whose condition has positive
            support; nothing else defeats it
  negative  an explicit denial that applies, or a restriction whose action
            pattern matches, whose guards hold and whose required condition
            has negative support (the necessity)

The step has positive support when some path holds, negative support when a
denial or a necessity applies.  A step whose value is true is applied; false
(explicit negative support) or unknown (a condition not established) makes the
candidate invalid; both makes it contested.  The finding names the failing
path conditions, restrictions and denials.

Transition.  Conditions of text effects are evaluated in the old state.  The
library writes and the text writes of the step are applied together; two
strict writes of opposite signs are both kept.  A text effect writes when its
condition has positive support.  A text effect whose condition is unknown may
or may not write: its atoms become unknown in the successor.  A text effect
whose condition is false writes nothing.  Every other
stored fact keeps its signs (negative facts persist).
Computed properties (standing laws) are recomputed in every state and
never stored; a standing law whose head is declared stored adds stored facts.

Invariants, in the initial state and every successor: one hand holds
two known-distinct objects; holding and empty; a block with something on it
and clear-top; two known-distinct direct supports; self-support; a support
cycle of any length (the strongly connected parts of the support graph); one
entity at two places of the declared flat set.  Only established facts count:
nothing is inferred from a missing fact.

Not checked.  Replay coverage ends at: a `normally` or `or` in a description
or an effect, an unrestricted universal description, a text effect with a
variable its condition and action do not bind, a non-ground action, an
unknown constructor, and a holder that moves while it holds an object with a
stated location (no co-movement transition).  Such a candidate is
`not_checked` with the uncovered component, never valid.

Nothing here calls a prover or a model.
"""

import itertools
import re

import lc_action as la
import lc_action_query as lq

T, F, B, U = "true", "false", "both", "unknown"
LIBRARY = "library"
SURFACES = la.SURFACE_CLASSES
MODES = la.STANDARD_MODES
SHORT = re.compile(r" \d+$")


class NotChecked(Exception):
  """A part of the source or of the candidate outside the replay fragment: (component, message)."""

  def __init__(self, component, message):
    Exception.__init__(self, message)
    self.component = component


# ---------------------------------------------------------------------------
# four values


_PAIR = {T: (True, False), F: (False, True), B: (True, True), U: (False, False)}
_VALUE = {v: k for k, v in _PAIR.items()}


def from_pair(positive, negative):
  return _VALUE[(bool(positive), bool(negative))]


def pos(v):
  """Positive support: true or both."""
  return _PAIR[v][0]


def neg(v):
  """Negative support: false or both."""
  return _PAIR[v][1]


# ---------------------------------------------------------------------------
# supports and contested premises
#
# A support is None (no support) or a frozenset of the contested premises it rests on; the empty set is a clean
# support.  A formula has a pair of supports, positive and negative.  A premise is a base atom with both signs, so
# the sets are finite and a fixpoint over them ends.

CLEAN = frozenset()


def _rank(s):
  return (len(s), sorted(s))


def best(sups):
  """Alternative supports: a clean one when there is one, else the one with the fewest premises."""
  got = [s for s in sups if s is not None]
  return min(got, key=_rank) if got else None


def join(sups):
  """Required parts: no support when a part has none, else the premises of every part."""
  out = set()
  for s in sups:
    if s is None:
      return None
    out |= s
  return frozenset(out)


def better(new, old):
  """A new support improves a recorded one: there was none, or the new one ranks lower, in the order `best` uses."""
  return new is not None and (old is None or _rank(new) < _rank(old))


def s_value(s):
  return from_pair(s[0] is not None, s[1] is not None)


def s_const(v):
  return (CLEAN if pos(v) else None, CLEAN if neg(v) else None)


def s_not(s):
  return (s[1], s[0])


def s_and(ss):
  ss = list(ss)
  return (join(x[0] for x in ss), best(x[1] for x in ss))


def s_or(ss):
  ss = list(ss)
  return (best(x[0] for x in ss), join(x[1] for x in ss))


def s_atom(atom, has_pos, has_neg, p, n):
  """The supports of an atom from its signs: reading an atom that has both signs rests on that atom."""
  if has_pos and has_neg:
    me = frozenset([show_atom(atom)])
    p = p | me if p is not None else None
    n = n | me if n is not None else None
  return p, n


def premises_of(s):
  """The premises of a true value's positive support or of a false value's negative support."""
  v = s_value(s)
  return sorted(s[0]) if v == T else sorted(s[1]) if v == F else []


# ---------------------------------------------------------------------------
# terms and atoms


def is_var(t):
  return isinstance(t, str) and la.is_var(t)


def subst(x, env):
  if isinstance(x, list):
    return [subst(y, env) for y in x]
  return env.get(x, x) if isinstance(x, str) else x


def ground(x):
  if isinstance(x, list):
    return all(ground(y) for y in x)
  return not is_var(x)


def key(atom):
  return tuple(atom)


def short(t):
  return SHORT.sub("", t) if isinstance(t, str) else str(t)


def show_atom(a, sign=None, where=None):
  """on(a,table), clear_top(b), have(Ann,cup), isa(block,a); with a situation label and a sign when given."""
  if a[0] == "is rel2":
    name, args = a[1], a[2:]
  elif a[0] == "has property":
    name, args = a[1], a[2:]
  else:
    name, args = a[0], a[1:]
  args = [short(x) for x in args] + ([where] if where else [])
  text = "%s(%s)" % (name, ",".join(args))
  return ("-" if sign == "-" else "") + text if where else ((sign or "") + text)


# ---------------------------------------------------------------------------
# the source: units, rules, statics


def _formula(unit):
  """(formula, probability) of a unit's Stage-2 package."""
  pkg = unit["stage2"][2]
  p = None
  if pkg[0] == "and" and isinstance(pkg[-1], list) and pkg[-1][:1] == ["@p"]:
    p = pkg[-1][2]
    pkg = pkg[1]
  return pkg[2], p


def _strip(f):
  vs = []
  while isinstance(f, list) and f and f[0] == "forall":
    vs.append(f[1])
    f = f[2]
  return vs, f


def _laws(f, vs=()):
  """[(variables, condition or None, head)] of an action-law formula: the grammar `lc_action._law_shape` accepts.

    LAW  := forall(V, LAW) | and(LAW, ...) | implies(COND, HEAD) | HEAD
    HEAD := forall(V, HEAD) | and(HEAD, ...) | a head atom

  A variable bound inside the consequent does not occur in the condition (the validator refuses a rebound
  variable), so moving its quantifier out keeps the meaning.  Each head gets its own variable list."""
  if isinstance(f, list) and f[:1] == ["forall"] and len(f) == 3:
    return _laws(f[2], vs + (f[1],))
  if isinstance(f, list) and f[:1] == ["and"]:
    return [x for g in f[1:] for x in _laws(g, vs)]
  if isinstance(f, list) and f[:1] == ["implies"] and len(f) == 3:
    return [(list(vs + hv), f[1], h) for hv, h in _heads(f[2])]
  return [(list(vs + hv), None, h) for hv, h in _heads(f)]


def _heads(f, vs=()):
  if isinstance(f, list) and f[:1] == ["forall"] and len(f) == 3:
    return _heads(f[2], vs + (f[1],))
  if isinstance(f, list) and f[:1] == ["and"]:
    return [x for g in f[1:] for x in _heads(g, vs)]
  return [(vs, f)]


def _literal(f):
  """An atom of the fragment: a fluent or a static predicate over strings."""
  return (isinstance(f, list) and bool(f) and isinstance(f[0], str) and (f[0] in la.FLUENTS or f[0] in la.STATIC)
          and all(isinstance(x, str) for x in f[1:]))


def _conjuncts(f):
  if isinstance(f, list) and f and f[0] == "and":
    out = []
    for x in f[1:]:
      out.extend(_conjuncts(x))
    return out
  return [f]


def _positive_vars(f, out, positive=True):
  """Variables of the positive literals of a condition (not under negation)."""
  if not isinstance(f, list) or not f:
    return out
  if f[0] == "not":
    return _positive_vars(f[1], out, not positive)
  if f[0] in ("and", "exists", "forall"):
    for x in (f[1:] if f[0] == "and" else [f[2]]):
      _positive_vars(x, out, positive)
    return out
  if positive and (f[0] in la.FLUENTS or f[0] in la.STATIC):
    out.update(x for x in f[1:] if is_var(x))
  return out


class Source(object):
  """The replay's reading of a supported source artifact under one query selection."""

  def __init__(self, artifact, planning_root=None, ambient=None, knower=None):
    if artifact["support"]["status"] != "supported":
      raise NotChecked("source", "the source is %s (%s); the replay reads supported sources only"
                       % (artifact["support"]["status"], ", ".join(artifact["support"]["reasons"] or artifact["support"]["errors"])))
    worlds = artifact.get("worlds") or ["W0"]
    self.root = planning_root or worlds[-1]
    sel = lq.selection(self.root, ambient, knower)
    self.excluded = lq.exclusions(artifact["units"], sel)
    gone = {x["unit"] for x in self.excluded}
    self.units = [u for u in artifact["units"] if u["id"] not in gone and u["status"] == "supported"]
    self.identity = set(artifact["identity"])
    # every type record is a static fact here; a lexical one repeats the fact of its own unit when that unit stays
    self.types = [t for t in artifact.get("types") or [] if t["entity"] in self.identity]
    prof = artifact["profile"]
    self.flat = set((prof.get("locations") or {}).get("flat") or [])
    policy = prof.get("policy") or {}
    self.declared_stored = set(policy.get("stored") or [])
    self.declared_computed = set(policy.get("computed") or [])
    self.witnesses = []
    self.static = {}             # key -> {sign: provenance}
    self.static_support = {}     # (key, sign) -> the contested premises of that sign's support
    self.availability, self.denials, self.restrictions, self.effects, self.laws = [], [], [], [], []
    self.notes = []
    self._names = self._witness_names()
    self._initial, self._pending = [], []
    for u in self.units:
      self._read(u)
    self.computed = self.declared_computed | {r["head"][1] for r in self.laws if r["head"][0] == "has property"} \
      - self.declared_stored

  # -- witnesses: sk_<Var>, sk_<Var>_<unit> when the variable is bound in several units, _<k> within one unit

  def _witness_names(self):
    per_unit = {}
    for u in self.units:
      if u["form"] in ("description_static", "description_initial"):
        per_unit[u["id"]] = self._binders(_formula(u)[0], [])
    total = {}
    for vs in per_unit.values():
      for v in vs:
        total[v] = total.get(v, 0) + 1
    names = {}
    for uid, vs in per_unit.items():
      seen = {}
      for v in vs:
        seen[v] = seen.get(v, 0) + 1
        if total[v] == 1:
          n = "sk_%s" % v
        elif vs.count(v) == 1:
          n = "sk_%s_%s" % (v, uid)
        else:
          n = "sk_%s_%s_%d" % (v, uid, seen[v])
        names.setdefault(uid, []).append(n)
    return names

  def _binders(self, f, out):
    if isinstance(f, list) and f:
      if f[0] == "exists":
        out.append(f[1])
        self._binders(f[2], out)
      elif f[0] in ("and", "or", "not", "implies", "forall", "normally"):
        for x in f[1:]:
          self._binders(x, out)
    return out

  @property
  def domain(self):
    return sorted(self.identity) + list(self.witnesses)

  # -- reading the units

  def _read(self, u):
    f, p = _formula(u)
    form = u["form"]
    if form in ("description_static", "description_initial"):
      return                     # read by initial_state
    if form == "state_law":
      vs, body = _strip(f[1])
      if body[0] != "implies" or body[2][0] not in la.FLUENTS:
        raise NotChecked(u["id"], "a standing law outside the safe rule form forall(implies(body, fluent))")
      self.laws.append({"unit": u["id"], "vars": vs, "body": body[1], "head": body[2]})
    elif form == "availability":
      for vs, cond, h in _laws(f):
        default = False
        if h[0] == "normally":
          default, h = True, h[1]
        if h[0] != "can":
          raise NotChecked(u["id"], "an availability head that is not can(actor, action)")
        self.availability.append({"unit": u["id"], "vars": vs, "cond": cond, "actor": h[1], "action": h[2],
                                  "default": default, "probability": p,
                                  "stated": self._stated(h[2], cond) if h[2][0] == "move" else None})
      if p is not None:
        self.notes.append("%s: an uncertain rule (p %s) is a permission here; the replay computes no confidence" % (u["id"], p))
    elif form == "denial":
      for vs, cond, h in _laws(f):
        if h[0] != "not" or h[1][0] != "can":
          raise NotChecked(u["id"], "a denial head that is not not(can(actor, action))")
        self.denials.append({"unit": u["id"], "vars": vs, "cond": cond, "action": h[1][2]})
    elif form == "restriction":
      for vs, cond, h in _laws(f):
        if cond is None:
          raise NotChecked(u["id"], "a restriction outside the form implies(guards and executable(action), required)")
        guards = [x for x in _conjuncts(cond) if x[0] != "executable"]
        exe = [x for x in _conjuncts(cond) if x[0] == "executable"]
        if len(exe) != 1:
          raise NotChecked(u["id"], "a restriction with %d executable atoms" % len(exe))
        self.restrictions.append({"unit": u["id"], "vars": vs, "guards": guards, "action": exe[0][1], "required": h})
    elif form == "effect":
      for vs, cond, h in _laws(f):
        if h[0] != "after":
          raise NotChecked(u["id"], "an effect outside the form after(action, heads)")
        heads = _conjuncts(h[2])
        for x in heads:
          lit = x[1] if x[0] == "not" else x
          if lit[0] not in la.FLUENTS:
            raise NotChecked(u["id"], "an effect head that is not a signed fluent literal (%s)" % x[0])
        self.effects.append({"unit": u["id"], "vars": vs, "cond": cond, "action": h[1], "heads": heads})
    else:
      raise NotChecked(u["id"], "a unit of form %s is outside the replay fragment" % form)

  def _stated(self, action, cond):
    """The stated-endpoint path: origin, destination and means are constants or bound by a positive condition, and
    the actor is not an unconditioned universal."""
    bound = _positive_vars(cond, set()) if cond is not None else set()
    ok = lambda t: not is_var(t) or t in bound
    return all(ok(t) for t in (action[1], action[2], action[3], action[4]))

  def _assert(self, uid, f, env, names, static_only, positive):
    """Assert the facts of a description: static atoms always, fluents only for the root's world."""
    op = f[0]
    if op == "and":
      for x in f[1:]:
        self._assert(uid, x, env, names, static_only, positive)
    elif op == "not":
      self._assert(uid, f[1], env, names, static_only, not positive)
    elif op == "exists":
      if not positive:
        raise NotChecked(uid, "a negated existential description")
      w = names.pop(0)
      if w not in self.witnesses:
        self.witnesses.append(w)
      self._assert(uid, f[2], dict(env, **{f[1]: w}), names, static_only, positive)
    elif op == "forall":
      vs, body = _strip(f)
      if body[0] != "implies" or not positive:
        raise NotChecked(uid, "an unrestricted universal description")
      self._pending.append({"unit": uid, "vars": vs, "env": env, "body": body, "static_only": static_only})
    elif op == "implies":
      if not positive:
        raise NotChecked(uid, "a negated conditional description")
      self._pending.append({"unit": uid, "vars": [], "env": env, "body": f, "static_only": static_only})
    elif op in ("or", "normally"):
      raise NotChecked(uid, "a description with %s is outside the replay fragment" % op)
    elif op in la.STATIC:
      self._static_add(subst(f, env), "+" if positive else "-", uid)
    elif op in la.FLUENTS:
      if not static_only:
        self._initial.append((subst(f, env), "+" if positive else "-", uid))
    else:
      raise NotChecked(uid, "a description atom %s outside the fragment" % op)

  def _static_add(self, atom, sign, prov):
    self.static.setdefault(key(atom), {}).setdefault(sign, prov)
    self.static_support[(key(atom), sign)] = CLEAN

  def _close_static(self):
    """Static conditional descriptions (forall(implies(static, static))) to a fixpoint: first the signs, then the
    supports over the fixed signs, as in State.derive."""
    rules = [r for r in self._pending if all(x[0] in la.STATIC for x in _conjuncts(r["body"][2]) + _conjuncts(r["body"][1]))]
    base = dict(self.static_support)
    changed = True
    while changed:
      changed = False
      for r in rules:
        for env in self._bindings(r["vars"], r["env"]):
          p = self.sup(r["body"][1], env, None)[0]
          if p is None:
            continue
          for h in _conjuncts(r["body"][2]):
            k = key(subst(h, env))
            if "+" not in self.static.get(k, {}):
              self.static.setdefault(k, {})["+"] = r["unit"]
              self.static_support[(k, "+")] = p      # provisional
              changed = True
    self.static_support = base
    changed = True
    while changed:
      changed = False
      for r in rules:
        for env in self._bindings(r["vars"], r["env"]):
          p = self.sup(r["body"][1], env, None)[0]
          for h in _conjuncts(r["body"][2]):
            kk = (key(subst(h, env)), "+")
            if better(p, self.static_support.get(kk)):
              self.static_support[kk] = p
              changed = True

  def _bindings(self, vs, env):
    free = [v for v in vs if v not in env]
    for combo in itertools.product(self.domain, repeat=len(free)):
      yield dict(env, **dict(zip(free, combo)))

  # -- evaluation

  def static_sup(self, atom):
    if atom[0] == "surface":
      return s_or(self.static_sup(["isa", c, atom[1]]) for c in SURFACES)
    if atom[0] == "standard_mode":
      return s_const(T if atom[1] in MODES else U)
    if atom[0] == "differ":
      return s_const(self.differ(atom[1], atom[2]))
    k = key(atom)
    signs = self.static.get(k, {})
    return s_atom(atom, "+" in signs, "-" in signs, self.static_support.get((k, "+")), self.static_support.get((k, "-")))

  def static_value(self, atom):
    return s_value(self.static_sup(atom))

  def differ(self, x, y):
    if x == y:
      return F
    if x in self.identity and y in self.identity and la.is_concrete(x) and la.is_concrete(y):
      return T
    return U

  def sup(self, f, env, state):
    """The (positive, negative) supports of a formula at a state (None: static atoms only)."""
    op = f[0]
    if op == "not":
      return s_not(self.sup(f[1], env, state))
    if op == "and":
      return s_and(self.sup(x, env, state) for x in f[1:])
    if op == "or":
      return s_or(self.sup(x, env, state) for x in f[1:])
    if op == "implies":
      return s_or([s_not(self.sup(f[1], env, state)), self.sup(f[2], env, state)])
    if op == "exists":
      return s_or(self.sup(f[2], dict(env, **{f[1]: d}), state) for d in self.domain)
    if op == "forall":
      return s_and(self.sup(f[2], dict(env, **{f[1]: d}), state) for d in self.domain)
    if op == "executable":
      if state is None:
        raise NotChecked("formula", "executable outside a state")
      return self.executability(subst(f[1], env), state)["support"]
    atom = subst(f, env)
    if not ground(atom):
      raise NotChecked("formula", "a non-ground atom %s" % atom)
    if op in la.STATIC or op in ("surface", "standard_mode", "differ"):
      return self.static_sup(atom)
    if op in la.FLUENTS:
      return (None, None) if state is None else state.sup(atom)
    raise NotChecked("formula", "an atom %s outside the fragment" % op)

  def export_static(self):
    """Read-only export for the planning summaries: the `isa` and `connected` atoms with positive support only and a
    clean support, and `surface` for each such entity of the domain.  Valid after `initial_state`."""
    out = [list(k) for k, signs in self.static.items() if list(signs) == ["+"] and self.static_support.get((k, "+")) == CLEAN]
    out.extend(["surface", d] for d in self.domain if self.static_sup(["surface", d]) == (CLEAN, None))
    return sorted(out)

  def ev(self, f, env, state):
    """The value of a formula at a state: true, false, both or unknown."""
    return s_value(self.sup(f, env, state))

  def sup_exists(self, f, vs, env, state):
    """A condition with variables the action does not bind: the disjunction over their bindings, with the
    environment of the binding whose positive support is best (a clean one first, else the first found)."""
    free = [v for v in vs if v not in env and la.mentions(f, v)]
    if not free:
      return self.sup(f, env, state), env
    sups, found, fs = [], None, None
    for e in self._bindings(free, env):
      x = self.sup(f, e, state)
      sups.append(x)
      if better(x[0], fs):
        found, fs = e, x[0]
    return s_or(sups), (found or env)

  # -- the initial state

  def initial_state(self):
    self._initial = []
    self._pending = []
    for u in self.units:
      if u["form"] in ("description_static", "description_initial"):
        f, p = _formula(u)
        if p is not None:
          self.notes.append("%s: an uncertain description (p %s) is read as stated" % (u["id"], p))
        self._assert(u["id"], f, {}, list(self._names.get(u["id"], [])),
                     u["form"] == "description_static" or (u.get("world") or "W0") != self.root, positive=True)
    for t in self.types:
      self._static_add(["isa", t["class"], t["entity"]], "+", "type:%s:%s" % (t["kind"], t["unit"]))
    self._close_static()
    s = State(self, 0)
    for atom, sign, uid in self._initial:
      s.add(atom, sign, uid)
    # conditional initial descriptions are evaluated at the root, together with the standing laws
    rules = []
    for r in self._pending:
      if r["static_only"] or all(x[0] in la.STATIC for x in _conjuncts(r["body"][2])):
        continue
      heads = []
      for h in _conjuncts(r["body"][2]):
        lit, sign = (h[1], "-") if h[0] == "not" else (h, "+")
        if not _literal(lit):
          # a default (normally), a disjunction or a quantifier in the consequent: never read as a strict rule
          raise NotChecked(r["unit"], "a conditional description whose consequent holds %s is outside the replay "
                                      "fragment" % (lit[0] if isinstance(lit, list) and lit else lit))
        if lit[0] not in la.STATIC:
          heads.append((lit, sign))
      rules.append({"unit": r["unit"], "vars": r["vars"], "env": r["env"], "body": r["body"][1], "heads": heads,
                    "law": False})
    s.derive(rules)
    return s

  # -- executability of one ground action

  def executability(self, action, state):
    if action[0] not in la.CONSTRUCTORS or len(action) != len(la.CONSTRUCTORS[action[0]]) + 1:
      raise NotChecked("action", "an action outside the five constructors: %s" % (action,))
    if not ground(action):
      raise NotChecked("action", "a non-ground action %s" % (action,))
    hook, restrictions, necessity = self._hook(action, state)
    denial, denials = self._denial(action, state)
    paths = []
    for p in self._library_paths(action) + self._source_paths(action):
      perm, penv = self.sup_exists(p["cond"], p["vars"], p["env"], state) if p["cond"] is not None else ((CLEAN, None), p["env"])
      sups = [self.sup(x, penv, state) for x in p["mechanics"]]
      if p["support_var"]:
        sups.append(s_or(self.sup(["is rel2", "on", action[2], d], penv, state) for d in self.domain))
      mech = s_and(sups)
      blocked = p["default"] and denial is not None
      support = None if blocked else join([perm[0], mech[0], hook])
      failing = ["%s=%s" % (_show(x, penv), s_value(v)) for x, v in zip(p["mechanics"], sups) if v[0] is None]
      paths.append({"path": p["name"], "default": p["default"], "holds": support is not None, "permission": s_value(perm),
                    "mechanics": s_value(mech), "failing": failing, "blocked": bool(blocked),
                    "premises": sorted(support or []), "support": support})
    positive = best(p["support"] for p in paths)
    negative = best([denial, necessity])
    return {"action": action, "value": s_value((positive, negative)), "positive": positive is not None,
            "negative": negative is not None, "paths": paths, "restrictions": restrictions, "denials": denials,
            "premises": sorted(positive or []), "negative_premises": sorted(negative or []),
            "support": (positive, negative)}

  def _library_paths(self, a):
    c = a[0]
    out = []
    if c == "move":
      out.append(_path("library:poss_move_person", True, ["A", "F", "T", "M"], a, None,
                       [["isa", "person", "A"], ["standard_mode", "M"]] + _tpl_move(public=True)))
    elif c == "take":
      out.append(_path("library:poss_take_hand", True, ["H", "X"], a, None, [["isa", "hand", "H"]] + _tpl_take(), support=True))
    elif c == "put_on":
      out.append(_path("library:poss_put_on_hand_block", True, ["H", "X", "Y"], a, None,
                       [["isa", "hand", "H"], ["isa", "block", "X"]] + _tpl_put_on(block=True)))
      out.append(_path("library:poss_put_on_hand_surface", True, ["H", "X", "Y"], a, None,
                       [["isa", "hand", "H"], ["isa", "block", "X"]] + _tpl_put_on(block=False)))
    return out

  def _source_paths(self, a):
    out = []
    for r in self.availability:
      env = _unify(r["action"], a, {}, r["vars"])
      if env is None or subst(r["actor"], env) != a[1]:
        continue
      names = {"move": ["A", "F", "T", "M"], "take": ["H", "X"], "put_on": ["H", "X", "Y"], "put_in": ["H", "X", "B"],
               "change": ["A", "X", "V", "W"]}[a[0]]
      tenv = dict(zip(names, a[1:]))
      if a[0] == "move":
        tpls = [("stated" if r["stated"] else "public", _tpl_move(public=not r["stated"]), False)]
      elif a[0] == "take":
        tpls = [("take", _tpl_take(), True)]
      elif a[0] == "put_on":
        tpls = [("put_on block", _tpl_put_on(block=True), False), ("put_on surface", _tpl_put_on(block=False), False)]
      elif a[0] == "put_in":
        tpls = [("put_in", [["is rel2", "holding", "H", "X"], ["differ", "X", "B"]], False)]
      else:
        tpls = [("change", [], False)]
      for name, mech, support in tpls:
        mech = [subst(x, tenv) for x in mech]
        out.append({"name": "%s (%s)" % (r["unit"], name), "default": r["default"], "vars": r["vars"], "env": env,
                    "cond": r["cond"], "mechanics": mech, "support_var": support})
    return out

  def _hook(self, action, state):
    """(hook support, details, necessity support) over the constructor's restrictions; a support is None when the
    hook fails or no necessity applies.

    One restriction is satisfied by its match check (the action unifies with its pattern and the required
    condition has positive support; the match check has no guard) or by a proved nonmatch (another concrete id in a
    constant slot or between two slots of one variable, or a guard with negative support).  A witness and a lexical
    value prove no nonmatch.  The necessity applies when the action unifies, the guards have positive
    support and the required condition has negative support."""
    parts, details, necessity = [], [], []
    for r in self.restrictions:
      if r["action"][0] != action[0]:
        continue
      env = _unify(r["action"], action, {}, r["vars"])
      slots = _slots(r["action"], action)
      nonmatch = CLEAN if _nonmatch(self, r["action"], action) else \
        best(self.sup(g, slots, state)[1] for g in r["guards"] if ground(subst(g, slots)))
      req, match = None, None
      if env is not None:
        rs, _ = self.sup_exists(r["required"], r["vars"], env, state)
        guards = s_and(self.sup(g, env, state) for g in r["guards"])
        req, match = s_value(rs), rs[0]
        necessity.append(join([guards[0], rs[1]]))
      sat = best([match, nonmatch])
      parts.append(sat)
      details.append({"unit": r["unit"], "unifies": env is not None, "nonmatch": nonmatch is not None, "required": req,
                      "satisfied": sat is not None, "literal": _show(r["required"], env or slots)})
    return join(parts), details, best(necessity)

  def _denial(self, action, state):
    """(the best support of a denial that applies, details): a denial applies when its action unifies and its
    condition has positive support."""
    sups, details = [], []
    for d in self.denials:
      env = _unify(d["action"], action, {}, d["vars"])
      if env is None:
        continue
      x = self.sup_exists(d["cond"], d["vars"], env, state)[0] if d["cond"] is not None else (CLEAN, None)
      sups.append(x[0])
      details.append({"unit": d["unit"], "value": s_value(x), "applies": x[0] is not None})
    return best(sups), details

  # -- one transition

  def successor(self, action, state):
    writes, uncertain, support = {}, set(), {}

    def write(atom, sign, prov, s=CLEAN):
      signs = writes.setdefault(key(atom), {})
      if sign not in signs or better(s, support[(key(atom), sign)]):
        signs[sign] = prov
        support[(key(atom), sign)] = s

    c = action[0]
    transport = []
    if c == "move":
      a, fr, to = action[1], action[2], action[3]
      held = [k for k, s in state.stored.items() if k[0] == "is rel2" and k[1] == "holding" and k[2] == a and "+" in s]
      for k in held:
        for x in state.stored:
          if x[0] == "is rel2" and x[1] == "located_at" and x[2] == k[3]:
            transport.append(x)
      write(["is rel2", "located_at", a, to], "+", LIBRARY)
      write(["is rel2", "located_at", a, fr], "-", LIBRARY)
    elif c == "take":
      h, x = action[1], action[2]
      write(["is rel2", "holding", h, x], "+", LIBRARY)
      write(["have", h, x], "+", LIBRARY)
      write(["has property", "empty", h], "-", LIBRARY)
      for k, s in list(state.stored.items()):
        if k[0] == "is rel2" and k[1] == "on" and k[2] == x and "+" in s:
          write(list(k), "-", LIBRARY)
          if self.static_value(["isa", "block", k[3]]) == T:
            write(["has property", "clear_top", k[3]], "+", LIBRARY)
    elif c == "put_on":
      h, x, y = action[1], action[2], action[3]
      write(["is rel2", "on", x, y], "+", LIBRARY)
      write(["is rel2", "holding", h, x], "-", LIBRARY)
      write(["has property", "empty", h], "+", LIBRARY)
      if self.static_value(["isa", "block", y]) == T:
        write(["has property", "clear_top", y], "-", LIBRARY)
    elif c == "put_in":
      h, x, b = action[1], action[2], action[3]
      write(["is rel2", "in", x, b], "+", LIBRARY)
      write(["is rel2", "holding", h, x], "-", LIBRARY)
      write(["has property", "empty", h], "+", LIBRARY)
    elif c == "change":
      write(["has property", action[3], action[2]], "+", LIBRARY)
    for e in self.effects:
      env = _unify(e["action"], action, {}, e["vars"])
      if env is None:
        continue
      for en, x in self._effect_bindings(e, env, state):
        for h in e["heads"]:
          lit, sign = (h[1], "-") if h[0] == "not" else (h, "+")
          atom = subst(lit, en)
          if not ground(atom):
            raise NotChecked(e["unit"], "an effect head with a variable its condition and action do not bind")
          if x[0] is not None:
            write(atom, sign, e["unit"], x[0])
          else:
            uncertain.add(key(atom))  # unknown: the effect may or may not write; a false condition writes nothing
    new = State(self, state.index + 1)
    for k, signs in state.stored.items():
      if k in writes or k in uncertain:
        continue
      if k[0] == "has property" and k[1] in self.computed:
        continue                 # a computed property has no inertia
      for sign in signs:
        new.stored.setdefault(k, {})[sign] = "persisted"
        new.support[(k, sign, "s")] = state.support[(k, sign, "s")]
    for k, signs in writes.items():
      new.stored[k] = dict(signs)
      for sign in signs:
        new.support[(k, sign, "s")] = support[(k, sign)]
    new.uncertain = sorted(uncertain - set(writes))
    new.written = writes
    # a held object's stated location is stale after its holder moved: reading it is outside the fragment
    new.stale = {k: v for k, v in state.stale.items() if k not in writes}
    for k in transport:
      if k not in writes:
        new.stale.setdefault(k, (new.index, "%s moved while it held %s, whose location is stated; the replay has no "
                                              "co-movement transition, so the location is stale"
                                              % (short(action[1]), short(k[2]))))
    new.derive()
    return new

  def _effect_bindings(self, e, env, state):
    """(env, condition supports) of every binding of an effect whose condition is not false."""
    out = []
    for en in self._bindings([v for v in e["vars"] if v not in env], env):
      x = self.sup(e["cond"], en, state) if e["cond"] is not None else (CLEAN, None)
      if s_value(x) != F:
        out.append((en, x))
    return out


def _show(f, env):
  return show_atom(subst(f, env)) if f and f[0] not in ("and", "or", "not", "exists", "forall", "implies") \
    else str(subst(f, env))


def _path(name, default, names, action, cond, mechanics, support=False):
  env = dict(zip(names, action[1:]))
  return {"name": name, "default": default, "vars": [], "env": env, "cond": cond,
          "mechanics": [subst(x, env) for x in mechanics], "support_var": support}


def _tpl_move(public):
  return [["is rel2", "located_at", "A", "F"]] + ([["connected", "F", "T", "M"]] if public else []) + [["differ", "F", "T"]]


def _tpl_take():
  return [["isa", "block", "X"], ["has property", "empty", "H"], ["has property", "clear_top", "X"]]


def _tpl_put_on(block):
  return [["is rel2", "holding", "H", "X"], ["differ", "X", "Y"]] + \
    ([["isa", "block", "Y"], ["has property", "clear_top", "Y"]] if block else [["surface", "Y"]])


def _unify(pattern, action, env, vs):
  if len(pattern) != len(action) or pattern[0] != action[0]:
    return None
  env = dict(env)
  for p, a in zip(pattern[1:], action[1:]):
    if is_var(p):
      if p in env and env[p] != a:
        return None
      env[p] = a
    elif p != a:
      return None
  return env


def _slots(pattern, action):
  """The pattern's variables bound to the action's terms slot by slot (the first occurrence of a variable)."""
  env = {}
  for p, a in zip(pattern[1:], action[1:]):
    if is_var(p):
      env.setdefault(p, a)
  return env


def _nonmatch(src, pattern, action):
  """A proved nonmatch: another concrete id in a constant slot, or two different concrete ids in the slots of one
  variable.  A witness or a lexical value proves none."""
  seen = {}
  for p, a in zip(pattern[1:], action[1:]):
    if is_var(p):
      if p in seen and src.differ(seen[p], a) == T:
        return True
      seen.setdefault(p, a)
    elif p != a and src.differ(p, a) == T:
      return True
  return False


# ---------------------------------------------------------------------------
# states


class State(object):
  """One state of a replay: the stored fluent facts with their sign and provenance, the facts the standing laws
  derive, and the uncertain facts.  `index` is the number of steps from the planning root."""

  def __init__(self, source, index):
    self.source = source
    self.index = index
    self.stored = {}          # key -> {sign: provenance}
    self.derived = {}         # key -> {sign: law unit}
    self.uncertain = []
    self.written = {}
    self.stale = {}           # key -> (step, why): a location that a holder's move left stale
    self.support = {}         # (key, sign, "s" stored or "d" derived) -> the contested premises of that sign's support

  def add(self, atom, sign, prov):
    self.stored.setdefault(key(atom), {}).setdefault(sign, prov)
    self.support[(key(atom), sign, "s")] = CLEAN

  def sup(self, atom):
    k = key(atom)
    if k in self.stale:
      raise NotChecked("transport", "reads %s: %s" % (show_atom(atom), self.stale[k][1]))
    st, dv = self.stored.get(k, {}), self.derived.get(k, {})
    p = best([self.support.get((k, "+", "s")), self.support.get((k, "+", "d"))])
    n = best([self.support.get((k, "-", "s")), self.support.get((k, "-", "d"))])
    return s_atom(atom, "+" in st or "+" in dv, "-" in st or "-" in dv, p, n)

  def value(self, atom):
    return s_value(self.sup(atom))

  def export(self):
    """Read-only export for the planning summaries: the stored atoms that are true only (no negative sign), have a
    clean support and are not stale.  No rule of the replay reads this."""
    return sorted(list(k) for k, signs in self.stored.items()
                  if list(signs) == ["+"] and self.support.get((k, "+", "s")) == CLEAN and k not in self.stale)

  def derive(self, descriptions=()):
    """The standing laws, and at the root the conditional initial descriptions, to a fixpoint.  Computed heads go
    to `derived`, stored heads to `stored`.

    First the signs: a rule adds its head's sign when its condition has positive support.  Then, over those fixed
    signs, the support of each sign: its base support (a stated, persisted or written sign) or the best support a
    rule gives it, improved until nothing changes.  A support is a set of base contested atoms and only shrinks, so
    both loops end; a clean support is used when one exists."""
    src = self.source
    rules = [{"unit": r["unit"], "vars": r["vars"], "env": {}, "body": r["body"], "heads": [(r["head"], "+")], "law": True}
             for r in src.laws] + list(descriptions)

    def heads(r, env):
      for lit, sign in r["heads"]:
        atom = subst(lit, env)
        if ground(atom):
          yield key(atom), sign, "d" if r["law"] and atom[0] == "has property" and atom[1] in src.computed else "s"

    base = {kk: x for kk, x in self.support.items() if kk[2] == "s"}
    self.derived = {}
    changed = True
    while changed:
      changed = False
      for r in rules:
        for env in src._bindings(r["vars"], r["env"]):
          p = src.sup(r["body"], env, self)[0]
          if p is None:
            continue
          for k, sign, where in heads(r, env):
            target = self.derived if where == "d" else self.stored
            if sign not in target.get(k, {}):
              target.setdefault(k, {})[sign] = r["unit"]
              self.support[(k, sign, where)] = p      # provisional
              changed = True
    self.support = base
    changed = True
    while changed:
      changed = False
      for r in rules:
        for env in src._bindings(r["vars"], r["env"]):
          p = src.sup(r["body"], env, self)[0]
          for k, sign, where in heads(r, env):
            if better(p, self.support.get((k, sign, where))):
              self.support[(k, sign, where)] = p
              changed = True

  def label(self):
    return self.source.root if self.index == 0 else "%s+%d" % (self.source.root, self.index)

  def render(self):
    """+on(a,table), -empty(hand), ...; the derived computed properties; the static facts."""
    facts = sorted(show_atom(list(k), s) for k, signs in self.stored.items() for s in signs)
    derived = sorted(show_atom(list(k)) for k, signs in self.derived.items() if "+" in signs)
    static = sorted(show_atom(list(k), None if s == "+" else "-") for k, signs in self.source.static.items() for s in signs)
    return {"after": self.index, "facts": facts, "derived": derived, "static": static}

  # -- the invariants

  def conflicts(self):
    src, out = self.source, []
    positive = [k for k, s in list(self.stored.items()) + list(self.derived.items()) if "+" in s]
    rel = lambda r: [k for k in positive if k[0] == "is rel2" and k[1] == r]
    lab = self.label()

    def fact(k, sign="+"):
      signs = self.stored.get(k, {})
      prov = signs.get(sign)
      tag = " [%s]" % prov if self.index > 0 and prov not in (None, "persisted") and k in self.written else ""
      return show_atom(list(k), sign, lab) + tag

    def both(k):
      return [fact(k, "-")] if "-" in self.stored.get(k, {}) else []

    def atoms(*ks):
      """The positive atoms of a conflict, for the English of `Inconsistent:`."""
      return [list(k) for k in ks]

    holding = rel("holding")
    for a, b in itertools.combinations(holding, 2):
      if a[2] == b[2] and src.differ(a[3], b[3]) == T:
        out.append({"rule": "one hand holds two distinct objects", "atoms": atoms(a, b),
                    "facts": [fact(a), fact(b), "differ(%s,%s)" % (short(a[3]), short(b[3]))]})
    for h in holding:
      e = ("has property", "empty", h[2])
      if e in positive:
        out.append({"rule": "holding and empty", "atoms": atoms(e, h),
                    "facts": [fact(e)] + both(e) + [fact(h)] + both(h)})
    on = rel("on")
    for k in on:
      c = ("has property", "clear_top", k[3])
      if c in positive and src.static_value(["isa", "block", k[3]]) == T:
        out.append({"rule": "a block with something on it is clear-top", "atoms": atoms(k, c),
                    "facts": [fact(k), fact(c), "isa(block,%s)" % short(k[3])]})
    for a, b in itertools.combinations(on, 2):
      if a[2] == b[2] and src.differ(a[3], b[3]) == T:
        out.append({"rule": "two direct supports", "atoms": atoms(a, b),
                    "facts": [fact(a), fact(b), "differ(%s,%s)" % (short(a[3]), short(b[3]))]})
    for k in on:
      if k[2] == k[3]:
        out.append({"rule": "self-support", "atoms": atoms(k), "facts": [fact(k)]})
    for part in _cycles([k for k in on if k[2] != k[3]]):
      out.append({"rule": "a support cycle", "atoms": atoms(*part), "facts": [fact(k) for k in part]})
    loc = [k for k in rel("located_at") if k not in self.stale]
    for a, b in itertools.combinations(loc, 2):
      if a[2] == b[2] and a[3] != b[3] and a[3] in src.flat and b[3] in src.flat:
        out.append({"rule": "two places of the declared flat set", "atoms": atoms(a, b), "facts": [fact(a), fact(b)]})
    return out


def _cycles(edges):
  """The edges of every strongly connected part of the support graph with more than one node: each such edge lies
  on a cycle.  Tarjan's algorithm, iterative, with no depth or size limit."""
  graph = {}
  for k in edges:
    graph.setdefault(k[2], []).append(k[3])
    graph.setdefault(k[3], [])
  index, low, on_stack, stack, parts, counter = {}, {}, set(), [], [], [0]
  for root in sorted(graph):
    if root in index:
      continue
    work = [(root, iter(graph[root]))]
    index[root] = low[root] = counter[0]
    counter[0] += 1
    stack.append(root)
    on_stack.add(root)
    while work:
      node, it = work[-1]
      nxt = next(it, None)
      if nxt is not None:
        if nxt not in index:
          index[nxt] = low[nxt] = counter[0]
          counter[0] += 1
          stack.append(nxt)
          on_stack.add(nxt)
          work.append((nxt, iter(graph[nxt])))
        elif nxt in on_stack:
          low[node] = min(low[node], index[nxt])
        continue
      work.pop()
      if work:
        low[work[-1][0]] = min(low[work[-1][0]], low[node])
      if low[node] == index[node]:
        part = set()
        while True:
          x = stack.pop()
          on_stack.discard(x)
          part.add(x)
          if x == node:
            break
        if len(part) > 1:
          parts.append(part)
  return [sorted((k for k in edges if k[2] in part and k[3] in part), key=lambda k: (k[2], k[3])) for part in parts]


# ---------------------------------------------------------------------------
# the public operations


def replay(artifact, sequence, goal=None, steps=None, planning_root=None, ambient=None, knower=None, export=False):
  """Replay a supplied action sequence.  Never raises: a part of the source outside the replay fragment, or a failure
  of the replay itself (the component `replay_error`), gives `not_checked`.  Returns a record:

    verdict         valid | invalid | not_checked | contested | inconsistent_action_state
    step            the first failing step (1-based; 0 for the initial state), or None
    reason          one line
    checked_prefix  the number of leading steps that are executable with every invariant intact
    steps           per step: the executability value (true / false / both / unknown), its paths,
                    restrictions and denials
    states          the rendered state after each step (0 = the root)
    conflicts       the invariant conflicts of the first inconsistent state, with their facts
    goal            the final formula's value and its witnesses (goal given)
    uncovered       the component outside the replay fragment (not_checked), or contested_premise
    premises        the contested premises a validated step or the goal rests on, or the negative support of the
                    failing step or of a false goal
    notes           what the replay does not compute (uncertain rules: no confidence)
    export          with `export`: `State.export()` of each state of `states`, for the planning summaries
  """
  rec = {"verdict": None, "step": None, "reason": None, "checked_prefix": 0, "steps": [], "states": [], "conflicts": [],
         "goal": None, "uncovered": None, "notes": [], "excluded": [], "premises": []}
  try:
    if export:
      rec["export"] = []
    return _replay(rec, artifact, sequence, goal, steps, planning_root, ambient, knower)
  except Exception as e:                                        # noqa: BLE001  K12: the replay never raises
    return _finish(rec, "not_checked", rec["step"], "replay_error: %s: %s" % (type(e).__name__, e),
                   uncovered="replay_error")


def _replay(rec, artifact, sequence, goal, steps, planning_root, ambient, knower):
  try:
    src = Source(artifact, planning_root, ambient, knower)
    rec["excluded"] = src.excluded
    state = src.initial_state()
    rec["notes"] = src.notes
  except NotChecked as e:
    return _finish(rec, "not_checked", 0, "%s: %s" % (e.component, e), uncovered=e.component)
  rec["states"].append(state.render())
  if "export" in rec:
    rec["export"].append(state.export())
  premises = []
  bad = state.conflicts()
  if bad:
    rec["conflicts"] = bad
    return _finish(rec, "inconsistent_action_state", 0, "the initial state at %s is inconsistent: %s"
                   % (state.label(), "; ".join(c["rule"] for c in bad)))
  for i, action in enumerate(sequence or []):
    n = i + 1
    try:
      ex = src.executability(action, state)
    except NotChecked as e:
      return _finish(rec, "not_checked", n, "%s: %s" % (e.component, e), uncovered=e.component)
    rec["steps"].append(_step_record(n, ex))
    premises.extend(ex["premises"])
    if ex["value"] != T:
      verdict = "contested" if ex["value"] == B else "invalid"
      if ex["value"] == F and ex["negative_premises"]:
        rec["premises"] = ex["negative_premises"]
      return _finish(rec, verdict, n, "step %d %s: %s%s" % (n, _show_action(action), _why(ex), _resting(rec)))
    try:
      state = src.successor(action, state)
    except NotChecked as e:
      return _finish(rec, "not_checked", n, "%s: %s" % (e.component, e), uncovered=e.component)
    rec["states"].append(state.render())
    if "export" in rec:
      rec["export"].append(state.export())
    if state.uncertain:
      rec["steps"][-1]["uncertain_writes"] = [show_atom(list(k)) for k in state.uncertain]

    bad = state.conflicts()
    if bad:
      rec["conflicts"] = bad
      return _finish(rec, "inconsistent_action_state", n, "the state after step %d is inconsistent: %s"
                     % (n, "; ".join(c["rule"] for c in bad)))
    rec["checked_prefix"] = n
  if steps is not None:
    k, cmp_ = len(sequence or []), steps["comparison"]
    if (cmp_ == "exactly" and k != steps["n"]) or (cmp_ == "at_most" and k > steps["n"]):
      return _finish(rec, "invalid", None, "%d steps against the bound %s %d" % (k, cmp_, steps["n"]))
  if goal is None and state.stale:
    step, why = min(state.stale.values())
    return _finish(rec, "not_checked", step, "transport: the final state holds a stale location: %s" % why,
                   uncovered="transport")
  if goal is not None:
    try:
      value, witness, found = evaluate_with_witness(src, goal, state)
    except NotChecked as e:
      return _finish(rec, "not_checked", None, "%s: %s" % (e.component, e), uncovered=e.component)
    rec["goal"] = {"value": value, "witness": witness, "premises": found}
    if value != T:
      verdict = "contested" if value == B else "invalid"
      if value == F and found:
        rec["premises"] = found
      return _finish(rec, verdict, None, "the final formula is %s at %s%s" % (value, state.label(), _resting(rec)))
    premises.extend(found)
  if premises:
    rec["premises"] = sorted(set(premises))
    return _finish(rec, "not_checked", None, "contested_premise: the candidate rests on a premise with both signs (%s); "
                   "a strict rule gives its head from the positive support, but a contested prerequisite is not "
                   "validated" % ", ".join(rec["premises"]), uncovered="contested_premise")
  return _finish(rec, "valid", None, "every step executable, every state consistent%s" % (", the goal holds" if goal else ""))


def _resting(rec):
  if not rec["premises"]:
    return ""
  return "; the negative support rests on a premise with both signs (%s)" % ", ".join(rec["premises"])


def _finish(rec, verdict, step, reason, uncovered=None):
  rec.update(verdict=verdict, step=step, reason=reason)
  if uncovered:
    rec["uncovered"] = uncovered
  return rec


def _show_action(a):
  return "%s(%s)" % (a[0], ",".join(short(x) for x in a[1:]))


def _why(ex):
  parts = []
  for d in ex["denials"]:
    if d["applies"]:
      parts.append("denial %s applies" % d["unit"])
  for r in ex["restrictions"]:
    if not r["satisfied"]:
      parts.append("restriction %s: %s is %s" % (r["unit"], r.get("literal"), r["required"] or "not matched"))
    elif r["required"] is not None and neg(r["required"]):
      parts.append("restriction %s: %s is %s" % (r["unit"], r.get("literal"), r["required"]))
  if not ex["positive"]:
    for p in ex["paths"]:
      if p["blocked"]:
        parts.append("path %s: blocked by the denial" % p["path"])
      elif not pos(p["permission"]):
        parts.append("path %s: permission %s" % (p["path"], p["permission"]))
      elif p["failing"]:
        parts.append("path %s: %s" % (p["path"], ", ".join(p["failing"])))
    if not ex["paths"]:
      parts.append("no permission for this action")
  return "; ".join(parts) or "executability %s" % ex["value"]


def _step_record(n, ex):
  return {"step": n, "action": ex["action"], "value": ex["value"], "positive": ex["positive"], "negative": ex["negative"],
          "paths": [{k: p[k] for k in ("path", "default", "holds", "permission", "mechanics", "failing", "blocked", "premises")}
                    for p in ex["paths"]],
          "restrictions": ex["restrictions"], "denials": ex["denials"], "premises": ex["premises"],
          "negative_premises": ex["negative_premises"]}


def evaluate_with_witness(src, goal, state):
  """(value, witnesses, premises) of a final formula.  For an outer existential the value is the disjunction over
  all bindings, and the witnesses are those of a true binding with the best positive support.  The premises are
  the contested atoms that a true value's positive support or a false value's negative support rests on."""
  vs, body = [], goal
  while isinstance(body, list) and body and body[0] == "exists":
    vs.append(body[1])
    body = body[2]
  if not vs:
    x = src.sup(goal, {}, state)
    return s_value(x), None, premises_of(x)
  sups, witness, ws = [], None, None
  for env in src._bindings(vs, {}):
    x = src.sup(body, env, state)
    sups.append(x)
    if s_value(x) == T and better(x[0], ws):
      witness, ws = {k: env[k] for k in vs}, x[0]
  x = s_or(sups)
  if witness is not None:
    x = (ws, x[1])
  return s_value(x), witness, premises_of(x)


def evaluate(artifact, formula, planning_root=None, ambient=None, knower=None):
  """(value, witnesses, premises) of a formula at the planning root: the replay's reading of an immediate
  question."""
  src = Source(artifact, planning_root, ambient, knower)
  state = src.initial_state()
  return evaluate_with_witness(src, formula, state)


def verification(record):
  """The replay's reading of a supplied-sequence verification: Yes, No, Unknown or contested, with the
  checked prefix.  No from a step needs explicit negative support and a checked prefix before it; a step that is
  merely not established gives Unknown.  A No whose negative support rests on a premise with both signs is
  not_checked with the component contested_premise.  `action_answer` combines this with the prover's paired
  obligations."""
  if record["verdict"] == "inconsistent_action_state":
    return {"answer": "inconsistent_action_state", "prefix": record["checked_prefix"]}
  if record["verdict"] == "not_checked":
    return {"answer": "not_checked", "prefix": record["checked_prefix"], "uncovered": record["uncovered"]}
  if record["verdict"] == "valid":
    return {"answer": "Yes", "prefix": record["checked_prefix"]}
  resting = {"answer": "not_checked", "prefix": record["checked_prefix"], "uncovered": "contested_premise",
             "premises": record["premises"]}
  if record["step"] is not None and record["steps"]:
    last = record["steps"][-1]
    answer = {B: "contested", F: "No"}.get(last["value"], "Unknown")
    if answer == "No" and last["negative_premises"]:
      return dict(resting, failing_step=record["step"])
    return {"answer": answer, "prefix": record["checked_prefix"], "failing_step": record["step"]}
  if record["goal"] is not None:
    answer = {F: "No", B: "contested"}.get(record["goal"]["value"], "Unknown")
    if answer == "No" and record["goal"]["premises"]:
      return resting
    return {"answer": answer, "prefix": record["checked_prefix"]}
  return {"answer": "Unknown", "prefix": record["checked_prefix"]}
