"""Stage-1B explorer: run a compiled planning model over explicit states.

Third layer of the E11 stack.  planning_compile.compile_ir builds the
schematic model; this module grounds it against each visited state, so
creation (`fresh_result`) and universal conditional effects work without a
fixed pre-grounding.

Semantics:

- A state is (positive atoms, explicit negative atoms, entities).  A
  positive condition holds when its atom is present.  A negative condition
  holds when the negative atom is explicit; under the
  `closed_world_negatives` switch it also holds when the positive atom is
  absent, and each distinct assumed atom counts one firing.
- Applicability: a route authorizes a ground action when some typed witness
  binding satisfies all its conditions (E3 already conjoined the necessary
  conditions into every route).
- Effects (E1): all effects of a step are evaluated against the source
  state and written into one successor.  A universal conditional effect
  writes once per matching typed binding — zero, one or many.  A
  `fresh_result` variable creates a new entity.  Universal variables never
  enter the action term.  Successors exist only under the `effect_closure`
  switch; with it off, any task that applies an action refuses as
  incomplete_action_model.
- Deletes (E2) always apply here; delete dropping belongs to delete-free
  backends via planning_compile.delete_redundancy.
- Search (A1): breadth-first by plan length, stopping at the first depth
  that reaches the goal.  Exhaustion is a separate continuation recording
  whether the reachable frontier emptied; only that, with no certificate
  blockers, supports proved_unreachable_in_finite_closed_model (E8).  The
  searched budget is the reported budget.
- Occurrences are asserted events: they apply even when no route is known
  to authorize them (with a diagnostic); a verification task's given plan
  instead requires every step to be authorized.

solve(model, report, maxdepth=8, node_budget=200000) -> outcome dict with
"result" (an E8 code) for plan/reachability tasks, or "holds" in
{"yes","no","unknown"} for narrative/truth tasks, plus "plan",
"plan_valid", "certificate", "depth", "states_seen", "exhausted".
"""

from planning_compile import fire, blocker

IMPLICIT_PREFIX = "an_unnamed_"


def _atom(d, binding):
  args = []
  for a in d["args"]:
    if isinstance(a, dict):
      v = binding.get(a["var"])
      if v is None:
        return None
      args.append(v)
    else:
      args.append(a)
  return (d["pred"], tuple(args))


def _lit_true(d, binding, state, model, report):
  """True / False / None (unknown under strict negatives)."""
  pos, neg, _ = state
  atom = _atom(d, binding)
  assert atom is not None, d
  cwa = model["profile"]["switches"]["closed_world_negatives"]
  if d["sign"]:
    if atom in pos:
      return True
    if atom in neg:
      return False
    if cwa:
      fire(report, "closed_world_negatives", repr(atom))
      return False
    return None
  if atom in neg:
    return True
  if atom in pos:
    return False
  if cwa:
    fire(report, "closed_world_negatives", repr(atom))
    return True
  return None


def _typed(state, cls):
  names = [n for n, c in sorted(state[2]) if cls is None or c == cls]
  return names


def _satisfy(conds, witnesses, binding, state, model, report):
  """First witness extension making every condition True, else None.
  ([], binding) when there are no witnesses and all conditions hold."""
  def rec(i, b):
    if i == len(witnesses):
      for c in conds:
        if _lit_true(c, b, state, model, report) is not True:
          return None
      return b
    w = witnesses[i]
    for v in _typed(state, w.get("class")):
      got = rec(i + 1, dict(b, **{w["var"]: v}))
      if got is not None:
        return got
    return None
  return rec(0, dict(binding))


def base_state(model, report):
  entities = dict(model["entities"])
  entities.update(model["task_entities"])
  needed = set()
  for sch in model["schemas"].values():
    for p in sch["params"]:
      needed.add(p["class"])
    for r in sch["routes"]:
      for w in r["witnesses"]:
        needed.add(w.get("class"))
    for e in sch["effects"]:
      for q in e["quantified"]:
        # a fresh_result class needs no pre-existing instance: the action
        # creates its members (found by Sol's gold review, case cook)
        if q["binding"] == "universal":
          needed.add(q.get("class"))
  needed.discard(None)
  for cls in sorted(needed):
    if not any(c == cls for c in entities.values()):
      if model["profile"]["switches"]["implicit_class_instances"]:
        entities[IMPLICIT_PREFIX + cls] = cls
        fire(report, "implicit_class_instances", cls)
      else:
        report["diagnostics"].append("class %s has no instance" % cls)
        blocker(report, "class %s has no instance" % cls)
  return (frozenset(model["facts_pos"] | model["derived_pos"]),
          frozenset(model["facts_neg"]), frozenset(entities.items()))


def applicable(model, state, sid, values, report):
  sch = model["schemas"][sid]
  binding = {p["name"]: v for p, v in zip(sch["params"], values)}
  for r in sch["routes"]:
    if _satisfy(r["conditions"], r["witnesses"], binding, state, model,
                report) is not None:
      return True
  return False


def ground_steps(model, state, report):
  """Every authorized ground action term (sid, values) in this state."""
  out = []
  for sid in sorted(model["schemas"]):
    sch = model["schemas"][sid]
    if not sch["routes"]:
      continue
    def rec(i, values):
      if i == len(sch["params"]):
        if applicable(model, state, sid, tuple(values), report):
          out.append((sid, tuple(values)))
        return
      for v in _typed(state, sch["params"][i]["class"]):
        rec(i + 1, values + [v])
    rec(0, [])
  return out


def _fresh_name(entities, cls):
  base = (cls or "entity") + "_new"
  names = {n for n, _ in entities}
  i = 1
  while "%s%d" % (base, i) in names:
    i += 1
  return "%s%d" % (base, i)


def successor(model, state, sid, values, report):
  """Apply every effect of the step against the source state; one successor."""
  if not model["profile"]["switches"]["effect_closure"]:
    return None
  fire(report, "effect_closure", "in_force")
  sch = model["schemas"][sid]
  binding = {p["name"]: v for p, v in zip(sch["params"], values)}
  pos, neg, entities = state
  new_entities = set(entities)
  adds, dels = set(), set()
  for e in sch["effects"]:
    universals = [q for q in e["quantified"] if q["binding"] == "universal"]
    fresh = [q for q in e["quantified"] if q["binding"] == "fresh_result"]
    b0 = dict(binding)
    for q in fresh:
      name = _fresh_name(new_entities, q.get("class"))
      new_entities.add((name, q.get("class")))
      b0[q["var"]] = name
    def rec(i, b):
      if i == len(universals):
        for c in e["when"]:
          if _lit_true(c, b, state, model, report) is not True:
            return
        atom = _atom(e["literal"], b)
        (adds if e["literal"]["sign"] else dels).add(atom)
        return
      q = universals[i]
      for v in _typed(state, q.get("class")):
        rec(i + 1, dict(b, **{q["var"]: v}))
    rec(0, b0)
  both = adds & dels
  if both:
    report["diagnostics"].append(
      "step %s%r adds and deletes %s in one state; add wins"
      % (sid, tuple(values), sorted(both)))
  return (frozenset((pos - dels) | adds), frozenset((neg - adds) | dels),
          frozenset(new_entities))


def _occurrence_values(model, sid, bindings):
  sch = model["schemas"][sid]
  return tuple(bindings[p["role"]] for p in sch["params"])


def apply_occurrences(model, state, report):
  for o in model["occurrences"]:
    sid = o["schema"]
    values = _occurrence_values(model, sid, o["bindings"])
    if not applicable(model, state, sid, values, report):
      report["diagnostics"].append(
        "occurrence %s%r asserted but not known applicable" % (sid, values))
    nxt = successor(model, state, sid, values, report)
    if nxt is None:
      return None
    state = nxt
  return state


def goal_eval(model, state, report):
  """'yes' / 'no' / 'unknown' for the task goal, plus a witness binding."""
  task = model["task"]
  goal = task.get("goal") or []
  tvars = task.get("variables") or []
  best = "no"
  def rec(i, b):
    if i == len(tvars):
      vals = [_lit_true(g, b, state, model, report) for g in goal]
      if all(v is True for v in vals):
        return ("yes", b)
      return ("unknown", None) if any(v is None for v in vals) else ("no", None)
    out = ("no", None)
    for v in _typed(state, tvars[i].get("class")):
      got = rec(i + 1, dict(b, **{tvars[i]["var"]: v}))
      if got[0] == "yes":
        return got
      if got[0] == "unknown":
        out = got
    return out
  verdict, b = rec(0, {})
  return verdict, b


def replay(model, state, plan, report, require_routes=True):
  """A4: re-apply the plan; (ok, failing_step, reason)."""
  for i, (sid, values) in enumerate(plan):
    if require_routes and not applicable(model, state, sid, values, report):
      return False, i, "step %s%r not authorized" % (sid, tuple(values)), state
    nxt = successor(model, state, sid, values, report)
    if nxt is None:
      return False, i, "effect_closure off: successor undefined", state
    state = nxt
  return True, None, None, state


def solve(model, report, maxdepth=8, node_budget=200000, base=None):
  """`base` (optional): a prepared post-occurrence state from base_state /
  apply_occurrences, so a caller can share it with another backend."""
  out = {"result": None, "holds": None, "plan": None, "plan_valid": None,
         "witness": None, "depth": None, "states_seen": 0,
         "exhausted": False, "certificate": None}
  task = model["task"] or {}
  kind = task.get("kind")

  if base is None:
    base = base_state(model, report)
    if model["occurrences"]:
      base = apply_occurrences(model, base, report)
      if base is None:
        out["result"] = "incomplete_action_model"
        report["diagnostics"].append("effect_closure off: occurrences not applied")
        return out

  if kind in ("narrative", "truth"):
    out["holds"], out["witness"] = goal_eval(model, base, report)
    return out

  if kind == "verification":
    plan = [(st["schema"], _occurrence_values(model, st["schema"], st["bindings"]))
            for st in task.get("given_plan") or []]
    ok, step, reason, final = replay(model, base, plan, report)
    out["plan"], out["plan_valid"] = plan, ok
    if not ok:
      report["diagnostics"].append("given plan fails at step %s: %s" % (step, reason))
      out["holds"] = "no"
      return out
    out["holds"], out["witness"] = goal_eval(model, final, report)
    return out

  if kind not in ("plan", "reachability"):
    report["diagnostics"].append("no plan task (kind %r); nothing to solve" % kind)
    return out

  # plan / reachability: breadth-first by plan length (A1).  The searched
  # depth cap is computed from the declared inputs and reported; there is
  # no hidden larger budget.
  user_bound = task.get("user_bound")
  bound = user_bound or maxdepth
  depth_cap = max(maxdepth, bound)
  out["searched_depth_cap"] = depth_cap

  verdict, wit = goal_eval(model, base, report)
  if verdict == "yes":
    out.update(result="plan_found", plan=[], plan_valid=True, witness=wit,
               depth=0)
    return out

  seen = {base}
  frontier = [(base, [])]
  completed_layers = 0        # all states at plan length <= this are known
  budget_hit = False
  reachable_at = None         # shortest goal depth, when one is found
  found = None
  while frontier and completed_layers < depth_cap and not budget_hit \
      and found is None and reachable_at is None:
    nxt = []
    for state, path in frontier:
      for sid, values in ground_steps(model, state, report):
        s2 = successor(model, state, sid, values, report)
        if s2 is None:
          out["result"] = "incomplete_action_model"
          report["diagnostics"].append("effect_closure off: no successor states")
          return out
        if s2 in seen:
          continue
        seen.add(s2)
        path2 = path + [(sid, values)]
        verdict, wit = goal_eval(model, s2, report)
        if verdict == "yes" and reachable_at is None:
          reachable_at = len(path2)
          if len(path2) <= bound:
            found = (path2, wit)
        nxt.append((s2, path2))
        if len(seen) > node_budget:
          budget_hit = True
          break
      if budget_hit:
        break
    if not budget_hit:
      completed_layers += 1
    frontier = nxt

  out["states_seen"] = len(seen)
  if found:
    plan, wit = found
    ok, step, reason, _ = replay(model, base, plan, report)
    out.update(result="plan_found", plan=plan, plan_valid=ok, witness=wit,
               depth=len(plan))
    if not ok:
      report["diagnostics"].append(
        "replay of the found plan fails at step %s: %s" % (step, reason))
      out["result"] = "translation_failed"
    return out

  out["exhausted"] = not frontier and not budget_hit and reachable_at is None
  blockers = report["certificate_blockers"]
  bound_complete = not budget_hit and (out["exhausted"] or completed_layers >= bound
                                       or reachable_at is not None)
  if reachable_at is not None:
    # the goal is reachable, only beyond the asked bound; sound bounded no
    report["diagnostics"].append(
      "goal reachable at depth %d, beyond the bound %d" % (reachable_at, bound))
    out["result"] = ("no_plan_within_user_bound" if user_bound
                     else "search_budget_exhausted")
    out["depth"] = bound
  elif blockers:
    # the searched model under-approximates reachability; no bounded or
    # unreachability claim is sound (E8)
    out["result"] = "incomplete_action_model"
    report["diagnostics"].append(
      "no plan found and the model is incomplete: " + "; ".join(blockers))
  elif out["exhausted"]:
    out["result"] = "proved_unreachable_in_finite_closed_model"
    out["certificate"] = {
      "entities": sorted(n for n, _ in base[2]),
      "schemas": sorted(model["schemas"]),
      "states": len(seen), "frontier_exhausted_at_depth": completed_layers,
      "switches": dict(model["profile"]["switches"]),
      "creation_occurred": any(len(s[2]) > len(base[2]) for s in seen)}
  elif user_bound and bound_complete:
    out["result"] = "no_plan_within_user_bound"
    out["depth"] = bound
  else:
    out["result"] = "search_budget_exhausted"
  return out
