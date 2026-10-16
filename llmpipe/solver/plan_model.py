"""Action route: a ground planning model of a compiled discovery input.

The plan builder, the plan filters and the known plan states read this model.  The model
comes from the clause structure, not from the clause names, so text clauses
(availability, effect, marker) and library clauses are read the same way:

- a permission rule has one positive `poss(ACT, ctxt(S))` literal;
- an effect has one fluent literal at `ctxt($do(ACT, S))`; a marker has one
  changed literal there;
- a frame has the shape `-F(S) | -poss(A,S) | F($do(A,S)) | $block(0, C($do(A,S)))`;
- an initial clause has positive fluent literals at a constant situation;
- a static clause has no situation argument.

Every other clause with a positive fluent literal is an open writer: an atom that
unifies with it is treated as possibly true everywhere, and no conclusion is drawn
from it.  The grounding uses the constants of the input only; `closed_functor`
says when that covers every instance of an action.
"""

import itertools
import json
from collections import defaultdict

# --- terms -------------------------------------------------------------------


def is_var(t):
  return isinstance(t, str) and t.startswith("?:")


def to_term(x):
  if isinstance(x, list):
    return tuple(to_term(y) for y in x)
  return x


def to_json(t):
  if isinstance(t, tuple):
    return [to_json(x) for x in t]
  return t


def term_vars(t, out=None):
  if out is None:
    out = []
  if is_var(t):
    if t not in out:
      out.append(t)
  elif isinstance(t, tuple):
    for x in t[1:] if t and isinstance(t[0], str) else t:
      term_vars(x, out)
  return out


def is_ground(t):
  return not term_vars(t)


def deref(t, b):
  while is_var(t) and t in b:
    t = b[t]
  return t


def subst(t, b):
  t = deref(t, b)
  if isinstance(t, tuple):
    return tuple(subst(x, b) for x in t)
  return t


def occurs(v, t, b):
  t = deref(t, b)
  if t == v:
    return True
  if isinstance(t, tuple):
    return any(occurs(v, x, b) for x in t)
  return False


def unify(x, y, b):
  """Return an extended copy of binding b, or None."""
  b = dict(b)
  stack = [(x, y)]
  while stack:
    s, t = stack.pop()
    s, t = deref(s, b), deref(t, b)
    if s == t:
      continue
    if is_var(s):
      if occurs(s, t, b):
        return None
      b[s] = t
    elif is_var(t):
      if occurs(t, s, b):
        return None
      b[t] = s
    elif isinstance(s, tuple) and isinstance(t, tuple) and len(s) == len(t):
      stack.extend(zip(s, t))
    else:
      return None
  return b


def match(pat, t, b):
  """One-way match: only the variables of pat are bound; t is read as ground."""
  b = dict(b)
  stack = [(pat, t)]
  while stack:
    p, s = stack.pop()
    if is_var(p):
      if p in b:
        if b[p] != s:
          return None
      else:
        b[p] = s
    elif isinstance(p, tuple):
      if not isinstance(s, tuple) or len(p) != len(s):
        return None
      stack.extend(zip(p, s))
    elif p != s:
      return None
  return b


def rename(t, suffix):
  if is_var(t):
    return t + suffix
  if isinstance(t, tuple):
    return tuple(rename(x, suffix) for x in t)
  return t


def show(t):
  if isinstance(t, tuple):
    if t and isinstance(t[0], str):
      return "%s(%s)" % (t[0], ",".join(show(x) for x in t[1:]))
    return "[%s]" % ",".join(show(x) for x in t)
  if is_var(t):
    return t[2:]
  return str(t).replace("#:", "")


# --- clause parsing ----------------------------------------------------------


class Clause:
  def __init__(self, idx, obj):
    self.idx = idx
    self.name = obj.get("@name", "c%d" % idx)
    self.conf = float(obj.get("@confidence", 1.0))
    self.obj = obj
    self.lits = []
    logic = obj.get("@logic")
    if logic is None:
      return
    if isinstance(logic, list) and logic and isinstance(logic[0], list):
      raw = logic
    else:
      raw = [logic]
    for lit in raw:
      t = to_term(lit)
      pos = True
      if isinstance(t[0], str) and t[0].startswith("-") and len(t[0]) > 1:
        pos = False
        t = (t[0][1:],) + t[1:]
      self.lits.append((pos, rename(t, "@%d" % idx)))


def ctxt_of(atom):
  if len(atom) > 1:
    last = atom[-1]
    if isinstance(last, tuple) and last and last[0] == "$ctxt":
      return last
  return None


def sit_of(atom):
  c = ctxt_of(atom)
  return c[2] if c else None


def fl(atom):
  """The fluent atom without its context argument."""
  return atom[:-1]


def is_do(t):
  return isinstance(t, tuple) and t and t[0] == "$do"


# --- static closure and joins ------------------------------------------------


class Index:
  """Ground atoms indexed by (predicate, arity)."""

  def __init__(self, atoms=()):
    self.by = defaultdict(set)
    for a in atoms:
      self.add(a)

  def add(self, a):
    k = (a[0], len(a))
    if a in self.by[k]:
      return False
    self.by[k].add(a)
    return True

  def __contains__(self, a):
    return a in self.by.get((a[0], len(a)), ())

  def candidates(self, pat):
    return self.by.get((pat[0], len(pat)), ())

  def all(self):
    for s in self.by.values():
      yield from s


def join(pats, sources, b):
  """Enumerate bindings that make every pattern a member of its source.

  pats is a list of (pattern, source) pairs; a source is an Index.  Patterns with
  the most bound arguments go first."""
  if not pats:
    yield b
    return

  def boundness(ps):
    p = subst(ps[0], b)
    return -sum(1 for x in p[1:] if not term_vars(x))

  order = sorted(range(len(pats)), key=lambda i: boundness(pats[i]))
  i = order[0]
  pat, src = pats[i]
  rest = pats[:i] + pats[i + 1:]
  p = subst(pat, b)
  if is_ground(p):
    if p in src:
      yield from join(rest, sources, b)
    return
  for a in list(src.candidates(p)):
    b2 = match(p, a, b)
    if b2 is not None:
      yield from join(rest, sources, b2)


# --- the model ---------------------------------------------------------------


class Model:
  def __init__(self, objs, name=""):
    self.name = name
    self.clauses = [Clause(i, o) for i, o in enumerate(objs)]
    self.question = [o for o in objs if "@question" in o]
    self.notes = []
    self.unused_frames = []       # the fluent atom of each frame clause the model could not use
    self._predicates()
    self._classify()
    self._statics()
    self._query()

  # predicates ---------------------------------------------------------------

  def _predicates(self):
    self.act_functors = set()
    for c in self.clauses:
      for _, a in c.lits:
        self._scan_actions(a)
    self.action_rel = set()
    self.changed = set()
    self.ctxt_preds = set()
    for c in self.clauses:
      for _, a in c.lits:
        if a[0] == "$block" and len(a) == 3 and isinstance(a[2], tuple):
          inner = a[2]
          if ctxt_of(inner) is not None:
            self.ctxt_preds.add(inner[0])
            if self._is_action(inner[1]):
              self.action_rel.add(inner[0])
        elif ctxt_of(a) is not None:
          self.ctxt_preds.add(a[0])
          if self._is_action(a[1]):
            self.action_rel.add(a[0])
    for c in self.clauses:
      for _, a in c.lits:
        if a[0] == "$block" and len(a) == 3 and isinstance(a[2], tuple):
          if a[2][0] not in self.action_rel and ctxt_of(a[2]) is not None:
            self.changed.add(a[2][0])
    self.fluents = self.ctxt_preds - self.action_rel - self.changed

  def _scan_actions(self, t):
    if not isinstance(t, tuple):
      return
    if t and t[0] in ("poss", "$do") and len(t) >= 3 and isinstance(t[1], tuple):
      self.act_functors.add((t[1][0], len(t[1]) - 1))
    for x in t[1:] if t and isinstance(t[0], str) else t:
      self._scan_actions(x)

  def _is_action(self, t):
    return isinstance(t, tuple) and (t[0], len(t) - 1) in self.act_functors

  def kind(self, atom):
    p = atom[0]
    if p == "$block":
      return "block"
    if p in self.fluents:
      return "fluent"
    if p in self.changed:
      return "changed"
    if p in self.action_rel:
      return "action_rel"
    if ctxt_of(atom) is not None:
      return "other_ctxt"
    if p.startswith("$") or p == "reachable" or self._has_do(atom):
      return "other"
    return "static"

  def _has_do(self, t):
    if is_do(t):
      return True
    if isinstance(t, tuple):
      return any(self._has_do(x) for x in t[1:])
    return False

  # clause classes -----------------------------------------------------------

  def _classify(self):
    self.perm_rules = []
    self.effects = []
    self.frames = []
    self.initial_rules = []
    self.static_rules = []
    self.open_atoms = []     # (scope, fluent atom pattern, clause name); scope None = everywhere
    self.ignored = []
    self.changed_map = {}
    for c in self.clauses:
      if not c.lits:
        continue
      if self._frame(c):
        continue
    for c in self.clauses:
      if not c.lits or getattr(c, "is_frame", False):
        continue
      kinds = [self.kind(a) for _, a in c.lits]
      if all(k == "static" for k in kinds):
        self.static_rules.append(c)
        continue
      poss_pos = [a for (pos, a) in c.lits if pos and a[0] == "poss"]
      do_lits = [(pos, a) for (pos, a) in c.lits
                 if self.kind(a) in ("fluent", "changed") and is_do(sit_of(a))]
      if len(poss_pos) == 1 and not do_lits:
        self._perm(c, poss_pos[0])
      elif len(do_lits) == 1 and not poss_pos:
        self._effect(c, do_lits[0])
      elif self._initial(c):
        pass
      else:
        self.ignored.append(c.name)
        for pos, a in c.lits:
          if pos and self.kind(a) == "fluent":
            self.open_atoms.append((None, fl(a), c.name))

  def _frame(self, c):
    if len(c.lits) != 4:
      return False
    neg_f = [a for pos, a in c.lits if not pos and self.kind(a) == "fluent"]
    pos_f = [a for pos, a in c.lits if pos and self.kind(a) == "fluent"]
    poss_n = [a for pos, a in c.lits if not pos and a[0] == "poss"]
    blocks = [a for pos, a in c.lits if pos and a[0] == "$block"]
    if not (len(neg_f) == len(pos_f) == len(poss_n) == len(blocks) == 1):
      return False
    f0, f1, pa, bl = neg_f[0], pos_f[0], poss_n[0], blocks[0]
    s0, s1 = sit_of(f0), sit_of(f1)
    if not (is_var(s0) and is_do(s1) and s1[2] == s0 and is_var(s1[1])):
      return False
    if not (pa[1] == s1[1] and sit_of(pa) == s0):
      return False
    inner = bl[2]
    if not (isinstance(inner, tuple) and inner[0] in self.changed and sit_of(inner) == s1):
      return False
    if fl(f0) != fl(f1):
      return False
    if inner[1:-1] != f0[1:-1]:
      self.notes.append("frame %s: changed arguments differ from the fluent; frame not used" % c.name)
      self.unused_frames.append(fl(f0))
      return False
    c.is_frame = True
    self.frames.append({"pattern": fl(f0), "conf": c.conf, "name": c.name})
    self.changed_map[(inner[0], len(inner))] = f0[0]
    return True

  def _split_conditions(self, c, skip, sit):
    """Conditions of a rule at situation sit: positive fluent conditions, negative
    fluent conditions, static guards, open literals (anything not understood)."""
    conds, negconds, guards, unknown = [], [], [], []
    for pos, a in c.lits:
      if a is skip:
        continue
      k = self.kind(a)
      if k == "fluent" and sit_of(a) == sit:
        (negconds if pos else conds).append(fl(a))
        if pos:
          self.open_atoms.append((None, fl(a), c.name))
      elif k == "static":
        if pos:
          unknown.append(a)
        else:
          guards.append(a)
      elif k in ("action_rel", "block"):
        if not pos and a[0] == "poss":
          unknown.append(a)
        elif a[0] in ("poss",):
          unknown.append(a)
        # hooks (ok_*), denial blocks and other action relations: ignored
      else:
        unknown.append(a)
        if pos and k == "fluent":
          self.open_atoms.append((None, fl(a), c.name))
    return conds, negconds, guards, unknown

  def _perm(self, c, head):
    act, sit = head[1], sit_of(head)
    conds, negconds, guards, unknown = self._split_conditions(c, head, sit)
    self.perm_rules.append({"name": c.name, "act": act, "pre": conds, "negpre": negconds,
                            "guards": guards, "unknown": unknown, "conf": c.conf})

  def _effect(self, c, lit):
    pos, a = lit
    s1 = sit_of(a)
    act, s0 = s1[1], s1[2]
    has_poss = False
    rest = []
    for p, x in c.lits:
      if x is a:
        continue
      if not p and x[0] == "poss" and x[1] == act and sit_of(x) == s0:
        has_poss = True
        continue
      rest.append((p, x))
    conds, negconds, guards, unknown = [], [], [], []
    for p, x in rest:
      k = self.kind(x)
      if k == "fluent" and sit_of(x) == s0:
        (negconds if p else conds).append(fl(x))
        if p:
          self.open_atoms.append((None, fl(x), c.name))
      elif k == "static" and not p:
        guards.append(x)
      else:
        unknown.append(x)
        if p and k == "fluent":
          self.open_atoms.append((None, fl(x), c.name))
    k = self.kind(a)
    if k == "changed":
      fpred = self.changed_map.get((a[0], len(a)))
      if fpred is None:
        self.notes.append("marker %s: no frame reads %s" % (c.name, a[0]))
        return
      kind, atom = "del", (fpred,) + a[1:-1]
    else:
      kind, atom = ("add" if pos else "neg"), fl(a)
    self.effects.append({"name": c.name, "act": act, "kind": kind, "atom": atom, "conds": conds,
                         "negconds": negconds, "guards": guards, "unknown": unknown,
                         "has_poss": has_poss, "conf": c.conf})

  def _initial(self, c):
    heads = [(p, a) for p, a in c.lits if p and self.kind(a) == "fluent"]
    if not heads:
      return False
    sits = {sit_of(a) for _, a in heads}
    if len(sits) != 1:
      return False
    s = sits.pop()
    if is_var(s) or is_do(s):
      return False
    if len(heads) > 1:
      for _, a in heads:
        self.open_atoms.append((s, fl(a), c.name))
      return True
    head = heads[0][1]
    conds, guards, ok = [], [], True
    for p, a in c.lits:
      if a is head:
        continue
      k = self.kind(a)
      if not p and k == "fluent" and sit_of(a) == s:
        conds.append(fl(a))
      elif not p and k == "static":
        guards.append(a)
      else:
        ok = False
    if not ok:
      self.open_atoms.append((s, fl(head), c.name))
      return True
    self.initial_rules.append({"name": c.name, "sit": s, "head": fl(head), "conds": conds,
                               "guards": guards, "conf": c.conf})
    return True

  # statics ------------------------------------------------------------------

  def _statics(self):
    self.consts = set()
    for c in self.clauses:
      for _, a in c.lits:
        self._scan_consts(a)
    self.static = Index()
    self.static_open = set()
    rules = []
    for c in self.static_rules:
      pos = [a for p, a in c.lits if p]
      neg = [a for p, a in c.lits if not p]
      if len(pos) != 1:
        for a in pos:
          self.static_open.add(a[0])
        continue
      head = pos[0]
      hv = set(term_vars(head))
      bv = set()
      for a in neg:
        bv.update(term_vars(a))
      if not hv <= bv:
        self.static_open.add(head[0])
        continue
      if not neg:
        self.static.add(head)
      else:
        rules.append((head, neg))
    changed = True
    while changed:
      changed = False
      for head, body in rules:
        for b in list(join([(x, self.static) for x in body], None, {})):
          if self.static.add(subst(head, b)):
            changed = True
    self.objects = set()
    for a in self.static.all():
      if a[0] == "isa" and len(a) == 3:
        self.objects.add(a[2])
      if a[0] == "differ":
        self.objects.update(a[1:])

  def _scan_consts(self, t):
    if isinstance(t, tuple):
      if t and t[0] == "$ctxt":
        return
      for x in t[1:]:
        self._scan_consts(x)
    elif isinstance(t, str) and not is_var(t) and not t.startswith("$"):
      self.consts.add(t)

  # query --------------------------------------------------------------------

  def _query(self):
    self.root, self.bound = None, None
    self.bound_kind = "unknown"
    self.goal = []
    defs = []
    for c in self.clauses:
      for p, a in c.lits:
        if p and a[0] == "reachable" and len(c.lits) == 1 and not term_vars(a[1]):
          self.root = a[1]
          n, t = 0, a[2]
          while isinstance(t, tuple) and t[0] == "s":
            n, t = n + 1, t[1]
          self.bound = n
        if p and a[0].startswith("$defq"):
          defs.append(c)
    final_only = True
    kinds = set()
    for c in defs:
      reach = [a for p, a in c.lits if not p and a[0] == "reachable"]
      if len(reach) != 1:
        final_only = False
        continue
      sit, n = reach[0][1], reach[0][2]
      kinds.add("at_most" if is_var(n) else "exact")
      goal = []
      for p, a in c.lits:
        if a is reach[0] or a[0].startswith("$defq"):
          continue
        if self.kind(a) == "fluent" and sit_of(a) == sit and not p:
          goal.append(fl(a))
        else:
          final_only = False
      self.goal.append(goal)
    if kinds == {"at_most"} and final_only and defs:
      self.bound_kind = "at_most"
    elif kinds:
      self.bound_kind = "exact" if "exact" in kinds else "other"
    self.useless_ok = self.bound_kind == "at_most"


# --- grounding ---------------------------------------------------------------


class Ground:
  """Ground actions, rule instances and effect instances, from the root state.

  R is the relaxed reachable set: the root state, closed under every effect of
  every action instance whose fluent preconditions are in R."""

  def __init__(self, m, max_rounds=50):
    self.m = m
    self.open_all = [a for s, a, _ in m.open_atoms if s is None]
    self.open_root = [a for s, a, _ in m.open_atoms if s is None or s == m.root]
    self.W = self._initial_state()
    self.R = Index(self.W.all())
    self.unbounded_adds = []
    self.functor_notes = {}
    self.closed = {f: True for f in m.act_functors}
    self._relaxed(max_rounds)

  def is_open(self, atom, at_root=False):
    pats = self.open_root if at_root else self.open_all
    return any(unify(p, atom, {}) is not None for p in pats)

  def _initial_state(self):
    m = self.m
    W = Index()
    rules = [r for r in m.initial_rules if r["sit"] == m.root]
    changed = True
    while changed:
      changed = False
      for r in rules:
        pats = [(g, m.static) for g in r["guards"]] + [(x, W) for x in r["conds"]]
        for b in list(join(pats, None, {})):
          h = subst(r["head"], b)
          if not is_ground(h):
            self.m.notes.append("initial %s has an unbound head; read as open" % r["name"])
            m.open_atoms.append((m.root, r["head"], r["name"]))
            continue
          if W.add(h):
            changed = True
    return W

  def _sat_pre(self, pre, at_root=False):
    """Split preconditions into the ones checked against R and the open ones."""
    keep, dropped = [], []
    for p in pre:
      (dropped if self.is_open(p, at_root) else keep).append(p)
    return keep, dropped

  def rule_instances(self, rule, state, at_root=False):
    m = self.m
    pre, _ = self._sat_pre(rule["pre"], at_root)
    pats = [(g, m.static) for g in rule["guards"] if g[0] not in m.static_open]
    pats += [(p, state) for p in pre]
    out = []
    for b in join(pats, None, {}):
      act = subst(rule["act"], b)
      free = term_vars(act)
      if free:
        for vals in itertools.product(sorted(m.consts), repeat=len(free)):
          b2 = dict(b)
          b2.update(zip(free, vals))
          out.append((subst(rule["act"], b2), tuple(subst(p, b2) for p in pre)))
      else:
        out.append((act, tuple(subst(p, b) for p in pre)))
    return out

  def _relaxed(self, max_rounds):
    m = self.m
    for f in m.act_functors:
      for r in m.perm_rules:
        if (r["act"][0], len(r["act"]) - 1) != f:
          continue
        if not self._guarded(r):
          self.closed[f] = False
          self.functor_notes[f] = "rule %s has an unguarded action argument" % r["name"]
    for f in m.act_functors:
      if not any((r["act"][0], len(r["act"]) - 1) == f for r in m.perm_rules):
        self.functor_notes[f] = "no permission rule"
    rounds = 0
    while True:
      rounds += 1
      self.RI = defaultdict(set)
      for r in m.perm_rules:
        for act, pre in self.rule_instances(r, self.R):
          if all(is_ground(p) for p in pre):
            self.RI[act].add((r["name"], pre))
      grew = False
      self.EFF = {}
      for act in self.RI:
        effs = self.effect_instances(act, self.R)
        self.EFF[act] = effs
        for e in effs:
          if e["kind"] == "add":
            if is_ground(e["atom"]):
              if self.R.add(e["atom"]):
                grew = True
            elif e["atom"] not in self.unbounded_adds:
              self.unbounded_adds.append(e["atom"])
              self.open_all.append(e["atom"])
              self.open_root.append(e["atom"])
              grew = True
      if not grew or rounds >= max_rounds:
        break
    self.GA = sorted(self.RI, key=show)
    self.RI = {a: sorted(v) for a, v in self.RI.items()}

  def _guarded(self, r):
    m = self.m
    hv = set(term_vars(r["act"]))
    gv = set()
    for g in r["guards"]:
      if g[0] not in m.static_open:
        gv.update(term_vars(g))
    for p in r["pre"]:
      if not self.is_open(p):
        gv.update(term_vars(p))
    return hv <= gv

  def effect_instances(self, act, state):
    """Effect instances of a ground action.  Conditions are ground fluent atoms
    that must be in state for the instance to be possible; markers may keep
    variables (they delete every matching atom)."""
    m = self.m
    out = []
    for e in m.effects:
      b = unify(e["act"], act, {})
      if b is None:
        continue
      strict = e["conf"] >= 1.0 and not e["unknown"] and not e["negconds"]
      conds, open_conds = [], []
      for cnd in e["conds"]:
        (open_conds if self.is_open(subst(cnd, b)) else conds).append(cnd)
      if open_conds:
        strict = False
      pats = [(g, m.static) for g in e["guards"] if g[0] not in m.static_open]
      if any(g[0] in m.static_open for g in e["guards"]):
        strict = False
      pats += [(c, state) for c in conds]
      for b2 in join(pats, None, b):
        out.append({"name": e["name"], "kind": e["kind"], "atom": subst(e["atom"], b2),
                    "conds": tuple(subst(c, b2) for c in conds), "strict": strict,
                    "conf": e["conf"]})
    return out

  def has_frame(self, atom):
    cache = self.__dict__.setdefault("_frame_cache", {})
    if atom not in cache:
      cache[atom] = any(match(f["pattern"], atom, {}) is not None for f in self.m.frames)
    return cache[atom]


def load(path):
  with open(path) as f:
    objs = json.load(f)
  return objs
