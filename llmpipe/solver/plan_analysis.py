"""Action route: impossible and useless action-pair filters from a ground plan model.

The filters become `$planfilter` records of a discovery launch (GK strategy key
`plan_filters`; ../gk/Doc/planning.md).  Steps:

1. invariants: candidate groups of fluent families with at most one true atom
   per parameter instance, accepted by a balance check over every reachable
   action instance and a count check on the root state;
2. impossible pairs: a ground pair (a, b) is impossible when, for every rule
   instance of a and of b, some precondition p of b cannot hold after a: p is
   not added by a, and either a deletes p by a strict marker, p has no frame, or
   p would have to persist from before a and is mutex with a precondition of a;
3. impossible starts: b has no rule instance whose preconditions hold at the root;
4. useless pairs: every executable rule-instance combination of (a, b) leaves
   every fluent as it was before a (checked by case analysis);
5. lifting: each ground result is generalized into a pattern with variables and
   distinct constraints, and a pattern is kept only if it matches no ground pair
   that the analysis could not exclude.

Every step fails open: an unproved premise gives no filter.
"""

import itertools
from collections import defaultdict

import plan_model as pm
from plan_model import show, is_var, term_vars, subst, match, unify


# --- families and invariants -------------------------------------------------

ALL = "all"


class Invariants:
  def __init__(self, g, max_size=3):
    self.g = g
    self.m = g.m
    self.atoms = sorted(set(g.R.all()) | set(g.W.all()), key=show)
    self._families()
    self.groups = []
    self.rejected = 0
    self._search(max_size)
    self._index()

  def _families(self):
    m = self.m
    prefix = {}
    pats = list(self.atoms)
    for a in pats:
      n = 0
      while n < len(a) - 1 and not is_var(a[n + 1]) and not isinstance(a[n + 1], tuple) \
            and a[n + 1] not in m.objects:
        n += 1
      prefix[a[0]] = min(prefix.get(a[0], n), n)
    self.prefix = prefix
    fams = defaultdict(list)
    for a in self.atoms:
      fams[self.family(a)].append(a)
    self.families = dict(fams)

  def family(self, a):
    n = self.prefix.get(a[0], 0)
    return a[:1 + n]

  def args(self, a):
    return a[1 + self.prefix.get(a[0], 0):]

  def _members(self):
    out = []
    for fam, atoms in sorted(self.families.items(), key=lambda x: show(x[0])):
      n = len(self.args(atoms[0]))
      for k in range(0, min(n, 2) + 1):
        if n - k > 1:
          continue
        for params in itertools.permutations(range(n), k):
          out.append((fam, params))
    return out

  def _search(self, max_size):
    members = self._members()
    accepted = []
    for size in range(1, max_size + 1):
      for combo in itertools.combinations(members, size):
        fams = [c[0] for c in combo]
        if len(set(fams)) != size:
          continue
        if len({len(c[1]) for c in combo}) != 1:
          continue
        bad = self.check(combo)
        if bad is ALL:
          self.rejected += 1
          continue
        good = {self.keys(combo, a) for a in self.atoms} - {None} - bad
        if not good:
          self.rejected += 1
          continue
        accepted.append((combo, bad))
    # a group whose members are a subset of another group with no more bad
    # instances adds no mutex pair
    self.groups = []
    self.bad = []
    for gr, bad in accepted:
      if any(set(gr) < set(o) and ob <= bad for o, ob in accepted):
        continue
      self.groups.append(gr)
      self.bad.append(bad)

  def pi(self, member, a):
    fam, params = member
    if self.family(a) != fam:
      return None
    args = self.args(a)
    return tuple(args[i] for i in params)

  def keys(self, group, a):
    for mem in group:
      p = self.pi(mem, a)
      if p is not None:
        return p
    return None

  def check(self, group):
    """The parameter instances for which the group is not an invariant (ALL when
    no instance can be trusted).  The check is made per instance: the count of an
    instance depends only on its own atoms."""
    g = self.g
    bad = set()
    # open writers and unbounded adds that could write a member
    for pat in g.open_all + g.open_root:
      for fam, params in group:
        k = len(pat) - len(fam)
        if k < 0:
          continue
        probe = fam + tuple("?:x%d" % i for i in range(k))
        b = pm.unify(probe, pat, {})
        if b is None:
          continue
        p = tuple(subst("?:x%d" % i, b) for i in params)
        if any(term_vars(x) for x in p):
          return ALL
        bad.add(p)
    # root count
    count = defaultdict(int)
    for a in g.W.all():
      p = self.keys(group, a)
      if p is not None:
        count[p] += 1
        if count[p] > 1:
          bad.add(p)
    # balance
    for act in g.GA:
      effs = g.EFF.get(act, [])
      adds = [e for e in effs if e["kind"] == "add"]
      dels = [e for e in effs if e["kind"] == "del" and e["strict"]]
      add_atoms = {e["atom"] for e in adds}
      for _, pre in g.RI[act]:
        P = set(pre)
        need = defaultdict(list)
        for e in adds:
          p = self.keys(group, e["atom"])
          if p is None or e["atom"] in P or p in bad:
            continue
          need[p].append(e)
        for p, lst in need.items():
          used = set()
          seen_atoms = set()
          for e in lst:
            if e["atom"] in seen_atoms:
              continue
            seen_atoms.add(e["atom"])
            K = P | set(e["conds"])
            partner = None
            for d in sorted(K, key=show):
              if d in used or d == e["atom"] or d in add_atoms:
                continue
              if self.keys(group, d) != p:
                continue
              if deleted(d, dels, K):
                partner = d
                break
            if partner is None:
              bad.add(p)
              break
            used.add(partner)
    return bad

  def _index(self):
    self.idx = defaultdict(set)
    for gi, gr in enumerate(self.groups):
      for a in self.atoms:
        p = self.keys(gr, a)
        if p is not None and p not in self.bad[gi]:
          self.idx[a].add((gi, p))
    self._implications()

  # implication invariants: p(args) => q(a function of args) in every reachable state

  def _implications(self):
    self.implies = defaultdict(set)
    self.implied_by = defaultdict(set)
    self.impl_rules = []
    fams = sorted(self.families, key=show)
    for fp in fams:
      n = len(self.args(self.families[fp][0]))
      for fq in fams:
        if fq == fp:
          continue
        k = len(self.args(self.families[fq][0]))
        if k > n:
          continue
        for mp in itertools.permutations(range(n), k):
          pairs = []
          for pp in self.families[fp]:
            args = self.args(pp)
            pairs.append((pp, fq + tuple(args[i] for i in mp)))
          if self._implication_holds(pairs):
            self.impl_rules.append((fp, fq, mp))
            for pp, qq in pairs:
              self.implies[pp].add(qq)
              self.implied_by[qq].add(pp)

  def _implication_holds(self, pairs):
    g = self.g
    atoms = set(self.atoms)
    for pat in g.open_all + g.open_root:
      for pp, qq in pairs:
        if unify(qq, pat, {}) is not None or unify(pp, pat, {}) is not None:
          return False
    W = set(g.W.all())
    for pp, qq in pairs:
      if pp in W and qq not in W:
        return False
      if not g.has_frame(qq):
        return False
    for act in g.GA:
      effs = g.EFF.get(act, [])
      adds = [e for e in effs if e["kind"] == "add"]
      dels = [e for e in effs if e["kind"] == "del"]
      sdels = [e for e in dels if e["strict"]]
      for _, pre in g.RI[act]:
        P = set(pre)
        for pp, qq in pairs:
          # pp added by act: qq must be added under the same or guaranteed conditions,
          # or be true before and not possibly deleted
          for e in adds:
            if e["atom"] != pp:
              continue
            K = P | set(e["conds"])
            if any(f["atom"] == qq and all(c in K for c in f["conds"]) for f in adds):
              continue
            if (qq in K or any(x in K for x in self._pre_implying(qq, pairs))) \
               and not self._possibly_deleted(qq, dels, K, atoms):
              continue
            return False
          # pp persists: qq must not be possibly deleted unless pp is deleted too
          if pp in atoms and self._possibly_deleted(qq, dels, P, atoms):
            if any(f["atom"] == qq and all(c in P for c in f["conds"]) for f in adds):
              continue
            if deleted(pp, sdels, P):
              continue
            if any(self.mutex(pp, q) for q in P):
              continue
            return False
    return True

  def _pre_implying(self, qq, pairs):
    return [pp for pp, q in pairs if q == qq]

  def _possibly_deleted(self, x, dels, K, atoms):
    for e in dels:
      if match(e["atom"], x, {}) is not None and all(c in atoms for c in e["conds"]):
        return True
    return False

  def known_true(self, x, K):
    """x follows from the true atoms K by an implication invariant."""
    return any(p in K for p in self.implied_by.get(x, ()))

  def known_false(self, x, K):
    """x implies an atom that is mutex with K, or x is mutex with K."""
    if any(self.mutex(x, k) for k in K):
      return True
    for q in self.implies.get(x, ()):
      if any(self.mutex(q, k) for k in K):
        return True
    return False

  def describe_impl(self, i):
    fp, fq, mp = self.impl_rules[i]
    n = len(self.args(self.families[fp][0]))
    pv = ["A%d" % j for j in range(n)]
    return "%s implies %s" % (show(fp + tuple(pv)), show(fq + tuple(pv[j] for j in mp)))

  def mutex(self, a, b):
    if a == b:
      return False
    ka, kb = self.idx.get(a), self.idx.get(b)
    if not ka or not kb:
      return False
    return bool(ka & kb)

  def why_mutex(self, a, b):
    for gi, p in self.idx.get(a, ()):
      if (gi, p) in self.idx.get(b, ()):
        return gi
    return None

  def informative(self, gi):
    """Some trusted instance has atoms from two member families."""
    seen = defaultdict(set)
    for a in self.atoms:
      for mem in self.groups[gi]:
        p = self.pi(mem, a)
        if p is not None and p not in self.bad[gi]:
          seen[p].add(mem[0])
    return any(len(v) > 1 for v in seen.values())

  def describe(self, gi):
    out = []
    for fam, params in self.groups[gi]:
      n = len(self.args(self.families[fam][0]))
      slots = []
      for i in range(n):
        slots.append("P%d" % params.index(i) if i in params else "_")
      out.append(show(fam + tuple(slots)).replace("(", "(", 1))
    per = ",".join("P%d" % i for i in range(len(self.groups[gi][0][1]))) or "state"
    s = "at most one of {%s} per %s" % (", ".join(out), per)
    if self.bad[gi]:
      s += "; not for %s" % ", ".join(sorted(show(p if len(p) > 1 else p[0]) for p in self.bad[gi]))
    return s


def deleted(atom, dels, K):
  """A strict marker instance deletes atom and its conditions are in K."""
  for e in dels:
    if match(e["atom"], atom, {}) is not None and all(c in K for c in e["conds"]):
      return e["name"]
  return None


# --- pair analysis -----------------------------------------------------------


class Pairs:
  def __init__(self, g, inv):
    self.g = g
    self.m = g.m
    self.inv = inv
    self.Rset = set(g.R.all())
    self.reasons = {}

  def _consistent(self, atoms):
    atoms = set(atoms)
    for x in atoms:
      if self.inv.known_false(x, atoms - {x}):
        return False
    return True

  def after(self, p, a, P):
    """How p can hold after a, given a's preconditions P: ('add', name),
    ('persist', None), ('open', None), or (None, reason)."""
    g = self.g
    if g.is_open(p):
      return "open", None
    if p not in self.Rset:
      return None, "never reachable"
    effs = g.EFF.get(a, [])
    for e in effs:
      if e["kind"] == "add" and e["atom"] == p:
        conds = e["conds"]
        if all(c in self.Rset for c in conds) and self._consistent(list(P) + list(conds)):
          return "add", e["name"]
    if not g.has_frame(p):
      return None, "no frame"
    d = deleted(p, [e for e in effs if e["kind"] == "del" and e["strict"]], set(P))
    if d:
      return None, "deleted by %s" % d
    for q in P:
      if self.inv.mutex(p, q):
        return None, "persists only if true before; mutex with %s (invariant %d)" % (
          show(q), self.inv.why_mutex(p, q))
    if self.inv.known_false(p, set(P)):
      return None, "persists only if true before; implies an atom mutex with a precondition of a"
    return "persist", None

  def executable_combos(self, a, b):
    """Rule-instance combinations of (a, b) that the analysis cannot exclude,
    with the preconditions of b that must persist from before a."""
    out = []
    reasons = []
    for na, P in self.g.RI[a]:
      if not self._consistent(P):
        continue
      for nb, Q in self.g.RI[b]:
        persist = []
        fail = None
        for p in Q:
          how, why = self.after(p, a, P)
          if how is None:
            fail = (show(p), why)
            break
          if how == "persist":
            persist.append(p)
        if fail is None and not self._consistent(list(P) + persist):
          fail = ("+".join(show(p) for p in persist), "joint persistence is mutex")
        if fail is None and not self._consistent(Q):
          fail = ("+".join(show(p) for p in Q), "preconditions of b are mutex")
        if fail is None:
          out.append((na, P, nb, Q, persist))
        else:
          reasons.append((na, nb) + fail)
    return out, reasons

  def start_possible(self, b):
    g = self.g
    for r in self.m.perm_rules:
      bnd = unify(r["act"], b, {})
      if bnd is None:
        continue
      rr = dict(r)
      rr["act"] = b
      rr["pre"] = [subst(p, bnd) for p in r["pre"]]
      rr["guards"] = [subst(x, bnd) for x in r["guards"]]
      for act, pre in g.rule_instances(rr, g.W, at_root=True):
        if act == b:
          return True
    return False

  # useless ------------------------------------------------------------------

  def identity(self, a, P, b, Q, persist, max_unknown=8):
    """True if, in every case, the state after a;b equals the state before a."""
    g = self.g
    effa, effb = g.EFF.get(a, []), g.EFF.get(b, [])
    for e in effa + effb:
      if e["kind"] == "del" and not e["strict"]:
        return False
    K0 = set(P) | set(persist)
    touched = set()
    conds = set()
    for e in effa + effb:
      if e["kind"] == "add":
        touched.add(e["atom"])
        conds.update(e["conds"])
      elif e["kind"] == "del":
        for x in self.Rset:
          if match(e["atom"], x, {}) is not None:
            touched.add(x)
        conds.update(e["conds"])
    for x in self.Rset:
      if not g.has_frame(x):
        touched.add(x)
    touched |= K0
    touched |= set(Q)

    def v0(x):
      if x in K0 or self.inv.known_true(x, K0):
        return True
      if x not in self.Rset:
        return False
      if self.inv.known_false(x, K0):
        return False
      return None

    unknown = sorted({c for c in conds | set(Q) if v0(c) is None}, key=show)
    if len(unknown) > max_unknown:
      return False
    executable = 0
    for vals in itertools.product((True, False), repeat=len(unknown)):
      sig = dict(zip(unknown, vals))
      trues = [x for x in unknown if sig[x]] + list(K0)
      if not self._consistent(trues):
        continue

      def s0(x):
        v = v0(x)
        if v is None:
          return sig.get(x, ("X", x))
        return v

      def step(state, effs):
        def val(x):
          for e in effs:
            if e["kind"] == "add" and e["atom"] == x:
              cv = [state(c) for c in e["conds"]]
              if any(isinstance(c, tuple) for c in cv):
                raise _Unknown()
              if all(cv):
                return True
          for e in effs:
            if e["kind"] == "del" and match(e["atom"], x, {}) is not None:
              cv = [state(c) for c in e["conds"]]
              if any(isinstance(c, tuple) for c in cv):
                raise _Unknown()
              if all(cv):
                return False
          if not g.has_frame(x):
            return False
          return state(x)
        return val

      try:
        s1 = step(s0, effa)
        if not all(s1(q) is True for q in Q):
          continue
        executable += 1
        s2 = step(s1, effb)
        for x in touched:
          if s2(x) != s0(x):
            return False
      except _Unknown:
        return False
    # no executable case: the pair analysis found the pair executable, so the
    # case analysis is incomplete; fail open
    return executable > 0


class _Unknown(Exception):
  pass


# --- lifting -----------------------------------------------------------------


def slots_of(acts):
  out = []
  for a in acts:
    out.extend(a[1:])
  return out


def pattern_matches(pat, dist, vals):
  b = {}
  for p, v in zip(pat, vals):
    if is_var(p):
      if p in b:
        if b[p] != v:
          return False
      else:
        b[p] = v
    elif p != v:
      return False
  for x, y in dist:
    vx = b.get(x, x)
    vy = b.get(y, y)
    if vx == vy:
      return False
  return True


def generalize(seed, positives, nvar):
  """Greedy generalization of a ground slot list against positive slot lists."""
  def valid(pat, dist):
    return not any(pattern_matches(pat, dist, v) for v in positives)

  pat, dist = list(seed), set()
  fresh = [0]

  def newvar():
    fresh[0] += 1
    return "?:V%d" % fresh[0]

  consts = []
  for x in seed:
    if x not in consts:
      consts.append(x)
  for c in consts:
    v = newvar()
    trial = [v if x == c else x for x in pat]
    others = sorted({x for x in trial if x != v})
    d2 = set(dist) | {tuple(sorted((v, o))) for o in others}
    if valid(trial, d2):
      pat, dist = trial, d2
  for d in sorted(dist):
    if valid(pat, dist - {d}):
      dist = dist - {d}
  for i in range(len(pat)):
    if is_var(pat[i]) and pat.count(pat[i]) > 1 and pat.index(pat[i]) != i:
      trial = list(pat)
      trial[i] = newvar()
      if valid(trial, dist):
        pat = trial
  for d in sorted(dist):
    if valid(pat, dist - {d}):
      dist = dist - {d}
  # drop distinct pairs that mention a variable used once and no constant
  return canonical(pat, dist)


def canonical(pat, dist):
  ren = {}
  for x in pat:
    if is_var(x) and x not in ren:
      ren[x] = "?:%s" % "XYZUVWABCDEFGHIJKLMNOPQRST"[len(ren)] if len(ren) < 26 else "?:V%d" % len(ren)
  pat2 = tuple(ren.get(x, x) for x in pat)
  dist2 = tuple(sorted(tuple(sorted((ren.get(x, x), ren.get(y, y)))) for x, y in dist))
  return pat2, dist2


def subsumes(p1, d1, p2, d2):
  """Pattern 1 matches every instance of pattern 2."""
  b = {}
  for x, y in zip(p1, p2):
    if is_var(x):
      if x in b and b[x] != y:
        return False
      b[x] = y
    elif x != y:
      return False
  dd2 = {tuple(sorted(d)) for d in d2}
  for x, y in d1:
    vx, vy = b.get(x, x), b.get(y, y)
    if vx == vy:
      return False
    if is_var(vx) or is_var(vy):
      if tuple(sorted((vx, vy))) not in dd2:
        return False
    # two different constants are always distinct
  return True


def build(slots, functors):
  """Rebuild action terms from a slot list."""
  out, i = [], 0
  for f, n in functors:
    out.append((f,) + tuple(slots[i:i + n]))
    i += n
  return out


def lift(negatives, positives, functors):
  """negatives, positives: lists of ground slot lists for one functor tuple."""
  pats = []
  covered = set()
  for seed in negatives:
    if seed in covered:
      continue
    if any(pattern_matches(p, d, seed) for p, d in pats):
      covered.add(seed)
      continue
    p, d = generalize(seed, positives, None)
    pats.append((p, d))
    covered.add(seed)
  # remove subsumed patterns
  keep = []
  for i, (p, d) in enumerate(pats):
    if any(j != i and subsumes(q, e, p, d) and not (subsumes(p, d, q, e) and j > i)
           for j, (q, e) in enumerate(pats)):
      continue
    keep.append((p, d))
  return keep


# --- the whole analysis ------------------------------------------------------


class Analysis:
  def __init__(self, model, ground):
    self.m = model
    self.g = ground
    self.inv = Invariants(ground)
    self.pairs = Pairs(ground, self.inv)
    self._ground_pairs()
    self._lift()

  def _ground_pairs(self):
    g = self.g
    self.imp, self.pos, self.useless = {}, {}, {}
    self.pair_reason = {}
    why = []
    if not self.m.useless_ok:
      why.append("the query is not an at-most bound on the final situation (%s)" % self.m.bound_kind)
    if g.open_all:
      why.append("open writers")
    if any(r["negpre"] for r in self.m.perm_rules):
      why.append("a permission rule has a negative precondition")
    self.useless_why = why
    self.useless_ok = not why
    for a in g.GA:
      for b in g.GA:
        combos, reasons = self.pairs.executable_combos(a, b)
        if not combos:
          self.imp[(a, b)] = True
          self.pair_reason[(a, b)] = reasons
          continue
        self.pos[(a, b)] = True
        if self.useless_ok and all(self.pairs.identity(a, P, b, Q, per)
                                   for _, P, _, Q, per in combos):
          self.useless[(a, b)] = True
    self.start_imp = [b for b in g.GA if not self.pairs.start_possible(b)]
    self.start_pos = [b for b in g.GA if b not in self.start_imp]

  def _lift(self):
    g = self.g
    self.filters = []
    self.skipped = []
    by_fun = defaultdict(lambda: {"neg": [], "pos": [], "useless": [], "notuseless": []})
    for (a, b) in list(self.imp) + list(self.pos):
      key = ((a[0], len(a) - 1), (b[0], len(b) - 1))
      s = tuple(slots_of([a, b]))
      if (a, b) in self.imp:
        by_fun[key]["neg"].append(s)
      else:
        by_fun[key]["pos"].append(s)
        if (a, b) in self.useless:
          by_fun[key]["useless"].append(s)
        else:
          by_fun[key]["notuseless"].append(s)
    for key in sorted(by_fun):
      d = by_fun[key]
      if not (self.g.closed.get(key[0], False) and self.g.closed.get(key[1], False)):
        self.skipped.append("%s/%s: action arguments not guarded" % key)
        continue
      for p, dist in lift(sorted(d["neg"]), d["pos"], key):
        acts = build(p, key)
        self.filters.append(self._filter("impossible_pair", acts, dist, d["neg"], d["pos"]))
      if d["useless"]:
        for p, dist in lift(sorted(d["useless"]), d["notuseless"], key):
          acts = build(p, key)
          self.filters.append(self._filter("useless_pair", acts, dist, d["useless"], d["notuseless"]))
    self._never()
    by_f = defaultdict(lambda: {"neg": [], "pos": []})
    for b in self.start_imp:
      by_f[(b[0], len(b) - 1)]["neg"].append(tuple(b[1:]))
    for b in self.start_pos:
      by_f[(b[0], len(b) - 1)]["pos"].append(tuple(b[1:]))
    for key in sorted(by_f):
      d = by_f[key]
      if not d["neg"]:
        continue
      if not self.g.closed.get(key, False):
        self.skipped.append("%s start: action arguments not guarded" % (key,))
        continue
      for p, dist in lift(sorted(d["neg"]), d["pos"], (key,)):
        acts = build(p, (key,))
        self.filters.append(self._filter("impossible_start", acts, dist, d["neg"], d["pos"]))

  def _never(self):
    """Single actions that no rule instance allows anywhere: argument-equality
    patterns of a closed functor that match no reachable ground action."""
    GA = self.g.GA
    for f, n in sorted(self.m.act_functors):
      if not self.g.closed.get((f, n), False) or n < 2:
        continue
      inst = [a[1:] for a in GA if (a[0], len(a) - 1) == (f, n)]
      if not inst:
        continue
      for i, j in itertools.combinations(range(n), 2):
        if any(x[i] == x[j] for x in inst):
          continue
        args = ["?:V%d" % k for k in range(n)]
        args[j] = args[i]
        p, _ = canonical(args, set())
        self.filters.append({"kind": "impossible_action", "dist": (), "acts": [(f,) + p],
                             "covers": 0, "example": [],
                             "reasons": ["no reachable instance has argument %d equal to argument %d" %
                                         (i + 1, j + 1)]})

  def _filter(self, kind, acts, dist, negs, poss):
    slots = slots_of(acts)
    cov = [s for s in negs if pattern_matches(slots, dist, s)]
    f = {"kind": kind, "dist": dist, "acts": acts, "covers": len(cov)}
    if kind == "impossible_pair":
      ex = cov[0]
      key = tuple(build(list(ex), [(a[0], len(a) - 1) for a in acts]))
      f["example"] = [show(x) for x in key]
      f["reasons"] = sorted({"%s: %s" % (r[2], r[3]) for r in self.pair_reason.get(key, [])})[:6]
    elif kind == "useless_pair":
      ex = cov[0]
      f["example"] = [show(x) for x in build(list(ex), [(a[0], len(a) - 1) for a in acts])]
      f["reasons"] = ["every executable case returns every fluent to its value before the pair"]
    else:
      f["example"] = [show(build(list(cov[0]), [(acts[0][0], len(acts[0]) - 1)])[0])]
      f["reasons"] = ["no permission rule instance holds at %s" % self.m.root]
    return f

  # output -------------------------------------------------------------------

  def to_json(self):
    out = []
    for i, f in enumerate(self.filters):
      d = {"id": "F%d" % (i + 1), "kind": f["kind"]}
      if f["kind"] == "impossible_start":
        d["pattern"] = pm.to_json(("$do", f["acts"][0], self.m.root))
      elif f["kind"] == "impossible_action":
        d["pattern"] = pm.to_json(("$do", f["acts"][0], "?:S"))
      else:
        d["pattern"] = pm.to_json(("$do", f["acts"][1], ("$do", f["acts"][0], "?:S")))
      if f["dist"]:
        d["distinct"] = [list(x) for x in f["dist"]]
      if f["kind"] == "useless_pair":
        d["scope"] = "discovery_at_most"
      d["covers_ground"] = f["covers"]
      d["example"] = f["example"]
      d["reasons"] = f["reasons"]
      out.append(d)
    return {
      "format": "plan-filters/1",
      "input": self.m.name,
      "root": self.m.root,
      "bound": self.m.bound,
      "bound_kind": self.m.bound_kind,
      "match": "a clause is dropped when one of its terms contains an instance of a "
               "pattern (one-way match; the clause's variables are read as constants) "
               "and each distinct pair is bound to two non-unifiable terms",
      "useless_filters": "enabled" if self.useless_ok else "disabled: " + "; ".join(self.useless_why),
      "invariants": [self.inv.describe(i) for i in range(len(self.inv.groups))
                     if self.inv.informative(i)],
      "implications": [self.inv.describe_impl(i) for i in range(len(self.inv.impl_rules))],
      "filters": out,
      "skipped": self.skipped,
      "open_atoms": sorted({"%s %s" % (s or "*", show(a)) for s, a, _ in self.m.open_atoms}),
      "notes": self.m.notes,
    }

  def stats(self):
    n = len(self.g.GA)
    return {
      "ground_actions": n,
      "pairs": n * n,
      "impossible": len(self.imp),
      "executable": len(self.pos),
      "useless": len(self.useless),
      "start_impossible": len(self.start_imp),
      "invariants": len(self.inv.groups),
      "filters": len(self.filters),
    }
