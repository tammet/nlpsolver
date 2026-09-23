"""Stage-1C gk emission: compiled v2 model -> ground plan_footprints domain.

Bridges the E11 stack to the gk backend.  The schematic model from
planning_compile is grounded at a prepared state (base facts, derived atoms,
occurrences already applied), so the witness and universal binding modes
never reach a gk action term:

- every typed parameter binding of a route-bearing schema becomes one ground
  action; witness bindings are enumerated and each surviving combination
  becomes one pre-variant;
- conditions on never-written fluents are evaluated here once (they cannot
  change) and folded away — a false one kills the variant, and any
  closed-world reading is counted through the shared firing counter;
- universal conditional effects ground-expand per matching binding into
  conditional effects, evaluated by gk in the source world (E1);
- deletes are kept; plan_footprints drops only the delete a simultaneous
  functional assignment implies, which is the checked E2 redundancy;
- creation (`fresh_result`) refuses the gk backend — the explorer answers
  and is attributed.

ground_theory(model, state, report) -> (pf_domain, name_map) on success,
(None, reason) otherwise.  name_map: ground action name -> (schema id,
parameter values), for mapping gk plan terms back.
"""

import planning_explore as px

MAX_GROUND_ACTIONS = 5000


def _term(a, binding):
  return binding[a["var"]] if isinstance(a, dict) else a


def _atom(d, binding):
  return [("" if d["sign"] else "-") + d["pred"]] + \
      [_term(a, binding) for a in d["args"]]


def ground_theory(model, state, report):
  for sid, sch in model["schemas"].items():
    for e in sch["effects"]:
      if any(q["binding"] == "fresh_result" for q in e["quantified"]):
        return None, "schema %s creates entities; gk ground emission refused" % sid

  written = model["written_fluents"]

  def static_verdict(cond, binding):
    """None: keep (dynamic).  True: fold away.  False: kill the variant."""
    if cond["pred"] in written:
      return None
    return px._lit_true(cond, binding, state, model, report) is True

  def enum(decls, binding):
    """All extensions of `binding` over the typed declarations."""
    outs = [binding]
    for q in decls:
      outs = [dict(b, **{q["var"]: v})
              for b in outs for v in px._typed(state, q.get("class"))]
    return outs

  actions, name_map = {}, {}
  used_preds = {p for p, _ in state[0]}
  for sid in sorted(model["schemas"]):
    sch = model["schemas"][sid]
    if not sch["routes"]:
      continue
    for values_binding in enum(
        [{"var": p["name"], "class": p["class"]} for p in sch["params"]], {}):
      values = tuple(values_binding[p["name"]] for p in sch["params"])
      variants = set()
      for route in sch["routes"]:
        for b in enum(route["witnesses"], values_binding):
          pre, dead = [], False
          for c in route["conditions"]:
            v = static_verdict(c, b)
            if v is None:
              pre.append(tuple(_atom(c, b)))
            elif v is False:
              dead = True
              break
          if not dead:
            variants.add(tuple(sorted(pre)))
      effects = []
      for e in sch["effects"]:
        universals = [q for q in e["quantified"] if q["binding"] == "universal"]
        for b in enum(universals, values_binding):
          cond, dead = [], False
          for c in e["when"]:
            v = static_verdict(c, b)
            if v is None:
              cond.append(list(_atom(c, b)))
            elif v is False:
              dead = True
              break
          if dead:
            continue
          d = e["literal"]
          effects.append({"atom": [d["pred"]] + [_term(a, b) for a in d["args"]],
                          "pos": d["sign"], "cond": cond,
                          "provenance": "passage"})
      for vi, pre in enumerate(sorted(variants)):
        gname = "%s_g%d" % (sch["verb"] or sid.lower(), len(name_map) + 1)
        name_map[gname] = (sid, values)
        actions[gname] = {"params": [], "pre": [list(a) for a in pre],
                          "effects": [dict(e, cond=[list(c) for c in e["cond"]])
                                      for e in effects],
                          "closure": {}, "closure_default": "closed",
                          "applicability": "stated"}
        for a in pre:
          used_preds.add(a[0].lstrip("-"))
        for e in effects:
          used_preds.add(e["atom"][0])
          for c in e["cond"]:
            used_preds.add(c[0])
        if len(name_map) > MAX_GROUND_ACTIONS:
          return None, "ground action budget exceeded (%d)" % MAX_GROUND_ACTIONS

  fluents = {}
  for p in sorted(used_preds):
    spec = model["fluents"].get(p)
    arity = spec["arity"] if spec else 1
    if p not in written:
      fluents[p] = {"kind": "static", "arity": arity}
    elif spec and spec.get("functional_key") == list(range(arity - 1)):
      fluents[p] = {"kind": "functional", "arity": arity,
                    "key": list(range(arity - 1))}
    else:
      fluents[p] = {"kind": "boolean", "arity": arity}

  init = [[p] + list(args) for p, args in sorted(state[0])]
  domain = {"fluents": fluents, "actions": actions, "init": init,
            "constants": sorted(n for n, _ in state[2]),
            "types": {}, "identity": [], "identity_default": "distinct"}
  return domain, name_map


def goal_atoms(model):
  """The task goal in the plan_footprints atom form (variables upper-case)."""
  task = model["task"] or {}
  out = []
  for g in task.get("goal") or []:
    out.append([("" if g["sign"] else "-") + g["pred"]] +
               [a["var"] if isinstance(a, dict) else a for a in g["args"]])
  return out


def plan_from_term(name_map, steps):
  """gk $do step terms -> [(schema, values), ...], or None if any unmapped."""
  out = []
  for s in steps:
    key = s[0] if isinstance(s, list) and s else s
    if key not in name_map:
      return None
    out.append(name_map[key])
  return out
