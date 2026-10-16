"""Action route: `$planstate` records for the GK check of a known ground plan.

For each prefix of the plan (the root, then the state after each action) one record lists the fluents that the
ground planning model makes true there.  The families say which fluents the lists cover completely.  With the GK
strategy key `plan_state` 1, GK drops a clause whose negative literal of a listed family, with ground arguments, at a
known situation, is not in that situation's list (../gk/Doc/planning.md).

A family is left out, and GK then never prunes on it, when an open writer, an unclassified clause or a frame clause
the model could not use can produce its atoms.  A wrong list could cut a real proof, so every doubt leaves the
family out.
"""

import plan_model as pm

REL = ("is rel2", "has property")


def family(atom):
  return (atom[0], atom[1]) if atom[0] in REL and len(atom) > 1 else (atom[0],)


def families(task):
  """(the fluent families the state lists cover completely, {family: the reason it is left out})"""
  m, g = task.m, task.g
  fams = {family(x) for x in task.atoms}
  unused = {family(a) for a in m.unused_frames}
  out, left = [], {}
  for f in sorted(fams):
    if f[0] not in m.fluents:
      left[f] = "not a fluent"
      continue
    opens = [a for a in g.open_all if a[0] == f[0] and (len(f) == 1 or len(a) < 2 or pm.is_var(a[1]) or a[1] == f[1])]
    if opens:
      left[f] = "open writer %s" % pm.show(opens[0])
      continue
    if f in unused or (f[0],) in unused:
      left[f] = "a frame clause the model could not use"
      continue
    out.append(f)
  if m.ignored:
    for f in list(out):
      for name in m.ignored:
        c = [c for c in m.clauses if c.name == name][0]
        if any(pos and family(a[:-1] if pm.ctxt_of(a) is not None else a) == f for pos, a in c.lits):
          out.remove(f)
          left[f] = "written by an unclassified clause %s" % name
          break
  return out, left


def states(task, plan):
  out = [task.root]
  for a in plan:
    out.append(task.step(out[-1], a))
  return out


def records(task, plan_terms, root):
  """(the `$planstate` clause objects of the plan, {"families", "left_out"}); `root` is the planning root"""
  plan = [pm.to_term(a) for a in plan_terms]
  fams, left = families(task)
  info = {"families": [list(f) for f in fams], "left_out": {" ".join(k): v for k, v in left.items()}}
  if not fams:
    return [], info
  fam_json = ["$families"] + [["$fam"] + list(f) for f in fams]
  sit = root
  out = []
  for i, st in enumerate(states(task, plan)):
    if i:
      sit = ["$do", plan_terms[i - 1], sit]
    atoms = sorted((x for x in st if family(x) in fams), key=pm.show)
    out.append({"@name": "planstate:s%d" % i,
                "@logic": [["$planstate", sit, ["$true"] + [pm.to_json(x) for x in atoms], fam_json]]})
  return out, info
