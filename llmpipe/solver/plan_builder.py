"""Action route: a ground plan from a compiled discovery input, with little or no search.

The task comes from the ground planning model (plan_model): ground actions, alternative precondition sets,
conditional effects and the state update of the model.  Ways to build a plan:
  ehc     enforced hill-climbing over helpful actions, then greedy best-first search (the fallback)
  agenda  a goal agenda from approximated reasonable orders, hill-climbing per goal group, then the fallback
  bfws    best-first width search: novelty 1 first, ties broken by the number of unmet goals
  regress goal regression with protected goals and backtracking over the goal order (diagnostic)
Each found plan is cleaned (redundant actions removed) and replayed in the model.  A plan of the model is a
proposal: the action route checks it with its own replay and with GK (docs/architecture/action-answers.md).
"""

import collections
import heapq
import itertools
import time

import plan_analysis as pa
import plan_model as pm

INF = float("inf")
EXPAND_LIMIT = 200000
REGRESS_CALLS = 20000
VARIANTS = ("ehc", "agenda", "bfws", "regress")


class Budget(Exception):
  pass


# ---------------------------------------------------------------------------
# the ground task

class Task:
  def __init__(self, objs, name="input"):
    self.name = name
    self.m = pm.Model(objs, name)
    self.g = pm.Ground(self.m)
    g = self.g
    self.root = frozenset(g.W.all())
    self.acts = list(g.GA)
    self.pre = {a: sorted({frozenset(p) for _, p in g.RI[a]}, key=lambda p: sorted(map(pm.show, p)))
                for a in self.acts}
    self.eff = {a: g.EFF.get(a, []) for a in self.acts}
    self.adds = {a: [(e["atom"], frozenset(e["conds"]), e["strict"]) for e in self.eff[a]
                     if e["kind"] == "add" and pm.is_ground(e["atom"])] for a in self.acts}
    self.dels = {a: [e for e in self.eff[a] if e["kind"] == "del" and e["strict"]] for a in self.acts}
    self.atoms = set(g.R.all()) | set(g.W.all())
    self.frame = {}
    self.goals = [self._ground_goal(alt) for alt in self.m.goal]
    notes = [x for x in g.functor_notes.values() if x != "no permission rule"]
    self.closed = all(g.closed.values()) and not g.unbounded_adds and not notes
    self.notes = list(self.m.notes) + notes + (["unbounded add effects"] if g.unbounded_adds else [])
    self.has_defeasible = any(not st for a in self.acts for _, _, st in self.adds[a])
    self._inv = None

  def _ground_goal(self, alt):
    """each goal pattern as the list of ground atoms that satisfy it"""
    out = []
    for gl in alt:
      if pm.is_ground(gl):
        out.append([gl])
      else:
        out.append(sorted((x for x in self.atoms if pm.match(gl, x, {}) is not None), key=pm.show))
    return out

  def has_frame(self, x):
    if x not in self.frame:
      self.frame[x] = self.g.has_frame(x)
    return self.frame[x]

  def inv(self):
    if self._inv is None:
      self._inv = pa.Invariants(self.g)
    return self._inv

  def applicable(self, s):
    return [a for a in self.acts if any(p <= s for p in self.pre[a])]

  def can(self, s, a):
    return any(p <= s for p in self.pre[a])

  def step(self, s, a, strict_only=False):
    """the state update of the model; strict_only drops the defeasible add effects"""
    out = set()
    dels = self.dels[a]
    for x in s:
      if not self.has_frame(x):
        continue
      if any(pm.match(e["atom"], x, {}) is not None and all(c in s for c in e["conds"]) for e in dels):
        continue
      out.add(x)
    for atom, conds, strict in self.adds[a]:
      if (strict or not strict_only) and conds <= s:
        out.add(atom)
    return frozenset(out)

  def sat(self, s, alt):
    return all(any(c in s for c in cands) for cands in alt)

  def replay(self, plan, alt):
    s = self.root
    for a in plan:
      if not self.can(s, a):
        return False
      s = self.step(s, a)
    return self.sat(s, alt)


# ---------------------------------------------------------------------------
# relaxed planning graph, h_FF and helpful actions

class Relaxed:
  def __init__(self, task, alt, strict_only):
    self.t = task
    self.alt = alt
    self.strict_only = strict_only
    self.cache = {}

  def levels(self, s, stop=True):
    """first layer of each atom, the achievers at that layer, and whether the goal was reached"""
    t = self.t
    level = {x: 0 for x in s}
    ach = {}
    layer = set(s)
    k = 0             # the layer number; the root state may hold no fluent at all
    while True:
      if stop and t.sat(layer, self.alt):
        return level, ach, True
      new = {}
      for a in t.acts:
        for p in t.pre[a]:
          if not p <= layer:
            continue
          for atom, conds, strict in t.adds[a]:
            if (strict or not self.strict_only) and atom not in level and conds <= layer:
              new.setdefault(atom, []).append((a, p, conds))
      if not new:
        return level, ach, t.sat(layer, self.alt)
      k += 1
      for x, lst in new.items():
        level[x] = k
        ach[x] = lst
      layer |= set(new)

  def h(self, s):
    """(h_FF, helpful actions); h is None when the goal is unreachable even without deletes"""
    if s in self.cache:
      return self.cache[s]
    t = self.t
    level, ach, ok = self.levels(s)
    if not ok:
      self.cache[s] = (None, [])
      return self.cache[s]
    goals = collections.defaultdict(set)
    for cands in self.alt:
      x = min((c for c in cands if c in level), key=lambda c: (level[c], pm.show(c)))
      if level[x] > 0:
        goals[level[x]].add(x)
    chosen = set()
    true_at = collections.defaultdict(set)
    top = max(goals) if goals else 0
    for i in range(top, 0, -1):
      for x in sorted(goals[i], key=pm.show):
        if x in true_at[i]:
          continue
        a, p, conds = min(ach[x], key=lambda r: (sum(level[q] for q in r[1] | r[2]), pm.show(r[0])))
        chosen.add(a)
        for q in p | conds:
          if level[q] > 0 and q not in true_at[i - 1]:
            goals[level[q]].add(q)
        for atom, cds, strict in t.adds[a]:
          if (strict or not self.strict_only) and all(level.get(c, INF) <= i - 1 for c in cds):
            true_at[i].add(atom)
            true_at[i - 1].add(atom)
    first = goals.get(1, set())
    helpful = [a for a in t.acts if t.can(s, a) and
               any(atom in first and conds <= s and (strict or not self.strict_only)
                   for atom, conds, strict in t.adds[a])]
    self.cache[s] = (len(chosen), helpful)
    return self.cache[s]


# ---------------------------------------------------------------------------
# searches

class Stats:
  def __init__(self):
    self.expanded = 0
    self.ehc_steps = 0
    self.ehc_direct = 0
    self.fallback = False
    self.backtracks = 0
    self.calls = 0

  def tick(self, n=1):
    self.expanded += n
    if self.expanded > EXPAND_LIMIT:
      raise Budget()


def ehc(task, rel, start, st, strict_only):
  """enforced hill-climbing from start; the plan and the end state, or None"""
  s = start
  h, helpful = rel.h(s)
  if h is None:
    return None
  plan = []
  while h > 0:
    frontier = collections.deque([(s, [])])
    seen = {s}
    found = None
    while frontier and found is None:
      x, path = frontier.popleft()
      for a in rel.h(x)[1]:
        y = task.step(x, a, strict_only)
        if y in seen:
          continue
        seen.add(y)
        st.tick()
        hy = rel.h(y)[0]
        if hy is not None and hy < h:
          found = (y, path + [a], hy)
          break
        frontier.append((y, path + [a]))
    if found is None:
      return None
    st.ehc_steps += 1
    if len(found[1]) == 1 and found[1][0] == helpful[0]:
      st.ehc_direct += 1
    s, h = found[0], found[2]
    plan += found[1]
    helpful = rel.h(s)[1]
  return plan, s


def gbfs(task, rel, start, st, strict_only):
  """greedy best-first search by h_FF with a preferred queue for helpful successors (LAMA)"""
  tie = itertools.count()
  h0 = rel.h(start)[0]
  if h0 is None:
    return None
  queues = [[(h0, next(tie), start)], [(h0, next(tie), start)]]
  parent = {start: None}
  closed = set()
  best, boost, turn = h0, 0, 0
  while queues[0] or queues[1]:
    if boost > 0 and queues[1]:
      q = queues[1]
      boost -= 1
    else:
      q = queues[turn] if queues[turn] else queues[1 - turn]
      turn = 1 - turn
    h, _, s = heapq.heappop(q)
    if s in closed:
      continue
    closed.add(s)
    st.tick()
    if task.sat(s, rel.alt):
      plan = []
      while parent[s] is not None:
        s, a = parent[s]
        plan.append(a)
      return list(reversed(plan)), None
    if h < best:
      best, boost = h, boost + 1000
    helpful = set(rel.h(s)[1])
    for a in task.applicable(s):
      y = task.step(s, a, strict_only)
      if y in parent:
        continue
      hy = rel.h(y)[0]
      if hy is None:
        continue
      parent[y] = (s, a)
      heapq.heappush(queues[0], (hy, next(tie), y))
      if a in helpful:
        heapq.heappush(queues[1], (hy, next(tie), y))
  return None


def bfws(task, alt, st, strict_only):
  """best-first width search: (novelty, unmet goals); novelty 1 when the state has an atom not seen before
  among states with the same number of unmet goals"""
  tie = itertools.count()
  seen_atoms = collections.defaultdict(set)

  def unmet(s):
    return sum(1 for cands in alt if not any(c in s for c in cands))

  def novelty(s, u):
    new = any(x not in seen_atoms[u] for x in s)
    seen_atoms[u].update(s)
    return 1 if new else 2

  u0 = unmet(task.root)
  q = [(novelty(task.root, u0), u0, next(tie), task.root)]
  parent = {task.root: None}
  while q:
    _, u, _, s = heapq.heappop(q)
    st.tick()
    if u == 0:
      plan = []
      while parent[s] is not None:
        s, a = parent[s]
        plan.append(a)
      return list(reversed(plan))
    for a in task.applicable(s):
      y = task.step(s, a, strict_only)
      if y in parent:
        continue
      parent[y] = (s, a)
      uy = unmet(y)
      heapq.heappush(q, (novelty(y, uy), uy, next(tie), y))
  return None


# ---------------------------------------------------------------------------
# goal agenda: approximated reasonable orders (Koehler & Hoffmann 2000)

def before(task, b, a, strict_only):
  """True when b should be achieved before a: b is not reachable, ignoring deletes, from the initial atoms
  that are consistent with a, by actions that neither delete a nor need an atom inconsistent with a"""
  inv = task.inv()
  layer = {x for x in task.root if not inv.mutex(x, a)} | {a}
  ok = []
  for act in task.acts:
    if any(pm.match(e["atom"], a, {}) is not None for e in task.dels[act]):
      continue
    for p in task.pre[act]:
      if not any(inv.mutex(x, a) for x in p):
        ok.append((act, p))
  while b not in layer:
    new = set()
    for act, p in ok:
      if p <= layer:
        for atom, conds, strict in task.adds[act]:
          if (strict or not strict_only) and conds <= layer and atom not in layer and \
              not any(inv.mutex(c, a) for c in conds):
            new.add(atom)
    if not new:
      return True
    layer |= new
  return False


def agenda(task, alt, strict_only):
  """goal groups in order; atoms on a cycle of the order share a group"""
  goals = [cands[0] for cands in alt if len(cands) == 1]
  if len(goals) != len(alt) or len(goals) < 2:
    return [alt]
  edges = {x: {y for y in goals if y != x and before(task, x, y, strict_only)} for x in goals}
  # strongly connected parts, then a topological order of the parts
  reach = {x: {x} for x in goals}
  changed = True
  while changed:
    changed = False
    for x in goals:
      for y in list(reach[x]):
        for z in edges[y]:
          if z not in reach[x]:
            reach[x].add(z)
            changed = True
  groups, done = [], set()
  while len(done) < len(goals):
    for x in goals:
      if x in done:
        continue
      comp = {y for y in goals if y in reach[x] and x in reach[y]}
      preds = {y for y in goals if y not in comp and y not in done and comp & reach[y]}
      if not preds:
        groups.append(sorted(comp, key=pm.show))
        done |= comp
        break
  out, acc = [], []
  for gr in groups:
    acc = acc + [[x] for x in gr]
    out.append(list(acc))
  return out


# ---------------------------------------------------------------------------
# goal regression with protection (diagnostic)

def regress(task, alt, st, strict_only):
  rel = Relaxed(task, alt, strict_only)
  achievers = collections.defaultdict(list)
  for a in task.acts:
    for p in task.pre[a]:
      for atom, conds, strict in task.adds[a]:
        if strict or not strict_only:
          achievers[atom].append((a, p, conds))

  def levels(s):
    return rel.levels(s, stop=False)[0]

  def achieve_atom(s, x, protected, stack, depth):
    st.calls += 1
    if st.calls > REGRESS_CALLS:
      raise Budget()
    if x in s:
      return s, []
    if x in stack or depth > 12:
      return None
    lv = levels(s)
    cands = []
    for a, p, conds in achievers.get(x, []):
      need = p | conds
      cost = max([lv.get(q, INF) for q in need] or [0])
      if cost < INF:
        cands.append((cost, sum(lv[q] for q in need), pm.show(a), a, p, conds))
    for _, _, _, a, p, conds in sorted(cands, key=lambda r: r[:3]):
      r = achieve_set(s, sorted(p | conds, key=lambda q: (lv.get(q, INF), pm.show(q))), protected,
                      stack + [x], depth + 1)
      if r is None:
        continue
      s1, plan1 = r
      if not (p <= s1 and conds <= s1):
        continue
      s2 = task.step(s1, a, strict_only)
      if protected <= s2 and x in s2:
        return s2, plan1 + [a]
    return None

  def achieve_set(s, atoms, protected, stack, depth):
    todo = [q for q in atoms if q not in s]
    if not todo:
      return s, []
    for k, order in enumerate(itertools.permutations(todo)):
      if k >= 24:
        break
      if k:
        st.backtracks += 1
      cur, plan, got, ok = s, [], set(), True
      for q in order:
        r = achieve_atom(cur, q, protected | got, stack, depth)
        if r is None:
          ok = False
          break
        cur, p1 = r
        plan += p1
        got.add(q)
      if ok and all(q in cur for q in atoms):
        return cur, plan
    return None

  goals = [min(cands, key=pm.show) for cands in alt] if all(alt) else None
  if goals is None:
    return None

  def top(s, protected, rounds):
    if all(x in s for x in goals):
      return []
    if rounds > 2 * len(goals) + 2:
      return None
    lv = levels(s)
    for x in sorted((x for x in goals if x not in s), key=lambda x: (lv.get(x, INF), pm.show(x))):
      r = achieve_atom(s, x, protected, [], 0)
      if r is not None:
        rest = top(r[0], protected | {x}, rounds + 1)
        if rest is not None:
          return r[1] + rest
      st.backtracks += 1
    return None

  initial = frozenset(x for x in goals if x in task.root)
  plan = top(task.root, initial, 0)
  if plan is None and initial:
    plan = top(task.root, frozenset(), 0)
  return plan


# ---------------------------------------------------------------------------
# clean-up, variants, one input

def cleanup(task, plan, alt):
  """remove an action, skip the later actions that are no longer applicable, keep the result if the goal
  still holds; repeat until no change"""
  changed = True
  while changed:
    changed = False
    for i in range(len(plan)):
      s, out = task.root, []
      for j, a in enumerate(plan):
        if j == i or not task.can(s, a):
          continue
        s = task.step(s, a)
        out.append(a)
      if len(out) < len(plan) and task.sat(s, alt):
        plan, changed = out, True
        break
  return plan


def run_variant(task, alt, variant, strict_only):
  st = Stats()
  rel = Relaxed(task, alt, strict_only)
  plan = None
  try:
    if variant == "ehc":
      r = ehc(task, rel, task.root, st, strict_only)
      if r is None:
        st.fallback = True
        r = gbfs(task, rel, task.root, st, strict_only)
      plan = r and r[0]
    elif variant == "agenda":
      s, plan = task.root, []
      for sub in agenda(task, alt, strict_only):
        r = ehc(task, Relaxed(task, sub, strict_only), s, st, strict_only)
        if r is None:
          plan = None
          break
        plan += r[0]
        s = r[1]
      if plan is None or not task.sat(s, alt):
        st.fallback = True
        r = gbfs(task, rel, task.root, st, strict_only)
        plan = r and r[0]
    elif variant == "bfws":
      plan = bfws(task, alt, st, strict_only)
    elif variant == "regress":
      plan = regress(task, alt, st, strict_only)
  except Budget:
    return None, st, "search budget"
  return plan, st, None


def build(task, variant):
  """the plan of one variant over the goal alternatives; strict effects first, then all effects"""
  if not task.goals:
    return {"status": "no goal", "plan": None}
  passes = [True, False] if task.has_defeasible else [True]
  t0 = time.process_time()
  last = None
  for strict_only in passes:
    for gi, alt in enumerate(task.goals):
      if not all(alt):
        continue
      plan, st, err = run_variant(task, alt, variant, strict_only)
      last = (st, err)
      if plan is None:
        continue
      raw = len(plan)
      plan = cleanup(task, plan, alt)
      return {"status": "found", "goal_alternative": gi, "defeasible": not strict_only,
              "plan": [pm.show(a) for a in plan], "plan_terms": [pm.to_json(a) for a in plan],
              "length": len(plan), "raw_length": raw, "valid": task.replay(plan, alt),
              "expanded": st.expanded, "ehc_steps": st.ehc_steps, "ehc_direct": st.ehc_direct,
              "fallback": st.fallback, "backtracks": st.backtracks, "calls": st.calls,
              "cpu": round(time.process_time() - t0, 3)}
  st, err = last if last else (Stats(), "no reachable goal atom")
  return {"status": err or "no plan", "plan": None, "expanded": st.expanded, "fallback": st.fallback,
          "backtracks": st.backtracks, "calls": st.calls, "cpu": round(time.process_time() - t0, 3)}


def kind(task):
  """the task kind, from the action names that have permission rules"""
  fun = collections.Counter(a[0] for a in task.acts)
  if not fun:
    return "no permitted action"
  agents = lambda f: len({a[1] for a in task.acts if a[0] == f})
  if "put_on" in fun:
    return "blocks, several hands" if agents("take") > 1 else "blocks"
  if "move" in fun:
    ticket = any(x[0] == "have" for a in task.acts if a[0] == "move" for p in task.pre[a] for x in p)
    many = ", several agents" if agents("move") > 1 else ""
    if ticket:
      return "tickets" + many
    return ("transport" if "take" in fun else "travel") + many
  if "change" in fun:
    destroy = any(task.dels[a] for a in task.acts if a[0] == "change")
    return "recipe or state change" + (", with destruction" if destroy else "")
  return "other"
