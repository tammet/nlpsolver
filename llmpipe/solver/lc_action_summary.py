"""Action profile: the planning-summary profile compiler.

`compile_profile` reads a supported source artifact and one discovery query
and builds a `planning_summary_profile/2` for `action_summary`.  No model and
no prover.  The update operations come from the clauses of the query's actual
view (`lc_action_query.view_records`), read by clause role:

  effect   -poss(ACT, C(S)) | guards | HEAD(C($do(ACT, S)))    library and source
           every signed head forgets its target; a negative head also vetoes
           a matching insertion; a positive head inserts when every guard is a
           positive literal of a tracked family in the old state or of the
           clean static data, else the insertion is left out and the forget
           is marked `always` lossy
  marker   guards | changed_*(TARGET, C($do(ACT, S)))           forgets its target
  frame    the reviewed persistence shape; a tracked family without a frame is
           forgotten at every step, and a fact removed in that way is a loss
  standing a standing law or a selected ordinary law: its head families are
           not stored families and are refused
  other    the roles that conclude no fluent in a successor (facts, paths,
           hooks, restrictions, denials, reachability); a clause of an
           unknown role, or of a known role outside its shape, that holds a
           fluent or a marker disables the families it names

A target variable that the action pattern does not bind is a wildcard in a
forget or a negative write.  A forget is certain (`loss` null) only when its
clause has no condition besides poss.  The one policy operation that follows
from no clause is the transport erasure: for each pair (holder, object) of
`lc_action_effects.transport`, a move of the holder forgets the object's
location.  `rel:located_at` is tracked only when the three coverage checks
on that inventory pass.

The initial list and the static facts come from the replay's read-only
export (`action_replay.State.export`, `Source.export_static`): the stored
atoms that are true only, clean and not stale.  The replay's successor is
never called here.

First fragment: one scope (no ambient, no knower), stored families only,
`property:clear_top` excluded.  A refused family or profile leaves the
ordinary query unchanged.
"""

import copy
import hashlib
import os

import action_replay as rp
import action_route as ar
import action_summary as asum
import lc_action as la
import lc_action_effects as ef
import lc_action_library as lib
import lc_action_query as lq
import lc_action_situate as sit

TRANSPORT_CONTRACT = "replay_transport_erasure/1"
CHOICE_SCHEMA = 1
EXCLUDED = {"property:clear_top": "coarse_conditional_target"}
STATIC_GUARDS = ("isa", "connected", "surface")
MARKER_OF = {v: k for k, v in sit.MARKERS.items()}
# roles whose clauses conclude no fluent in a successor situation
PLAIN_ROLES = {"static": "fixed-data", "static_type": "fixed-data", "distinct": "fixed-data", "static_helper": "fixed-data",
               "initial_fact": "initial", "availability": "executability", "denial": "executability",
               "restriction_check": "executability", "necessity_restriction": "executability", "hook": "executability",
               "applicability_default": "executability", "hook_default": "executability",
               "denial_consequence": "executability", "reachability": "search", "query": "query"}
IMPLEMENTATION = ("lc_action_summary.py", "action_summary.py", "action_replay.py", "lc_action_effects.py",
                  "lc_action_query.py", "lc_action_library.py")
HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# clause literals


def _base(lit):
  return lit[0].lstrip("-")


def _situation(lit):
  return sit.situation_of(lit)


def _kind(s):
  """none | var | world | succ | other, for the world slot of a literal."""
  if s is None:
    return "none"
  if isinstance(s, list):
    return "succ" if len(s) == 3 and s[0] == sit.DO else "other"
  return "var" if asum.is_gk_var(s) else "world" if sit.is_world(s) else "other"


def _atom(lit):
  """The fluent atom of a clause literal: no sign, no context term."""
  return [_base(lit)] + list(lit[1:-1])


def _families(atom):
  """The families an atom pattern can name; `rel:*` and `property:*` for a variable name slot."""
  if atom[0] == "have":
    return ["have"]
  kind = "rel" if atom[0] == "is rel2" else "property"
  return ["%s:%s" % (kind, "*" if asum.is_gk_var(atom[1]) or la.is_var(atom[1]) else atom[1])]


def _lits(rec):
  c = rec["clause"]
  return lib.literals(c) if isinstance(c, dict) else c


def _fluent_literals(lits):
  """(literal, atom) of every fluent or marker literal of a clause, a blocked atom included."""
  out = []
  for x in lits:
    y = x[2] if x[0] == "$block" and isinstance(x[2], list) else x
    if _base(y) in la.FLUENTS:
      out.append((y, _atom(y)))
    elif _base(y) in MARKER_OF:
      out.append((y, [MARKER_OF[_base(y)]] + list(y[1:-1])))
  return out


def _transition(lits, effect):
  """(head, action, guards) of an effect or marker clause, or None for another shape."""
  succ = [x for x in lits if x[0] != "$block" and _kind(_situation(x)) == "succ"]
  if len(succ) != 1 or any(x[0] == "$block" for x in lits):
    return None
  head = succ[0]
  act, s0 = _situation(head)[1], _situation(head)[2]
  if not (isinstance(act, list) and act and act[0] in la.CONSTRUCTORS and len(act) - 1 == len(la.CONSTRUCTORS[act[0]])
          and asum.is_gk_var(s0) and all(isinstance(t, str) for t in act)):
    return None
  poss = [x for x in lits if x[0] == "-poss"]
  if len(poss) != (1 if effect else len(poss)) or len(poss) > 1 or any(x[1] != act or _situation(x) != s0 for x in poss):
    return None
  guards = [x for x in lits if x is not head and x not in poss]
  for g in guards:
    k = _kind(_situation(g))
    if not (k == "none" or (k == "var" and _situation(g) == s0)) or not all(isinstance(t, str) for t in g[1:-1 if k == "var" else None]):
      return None
  if effect and not (_base(head) in la.FLUENTS):
    return None
  if not effect and not (head[0] in MARKER_OF):
    return None
  return head, act, guards


def _frame(lits):
  """The fluent atom a frame clause keeps, or None when the clause is not the reviewed frame shape."""
  block = [x for x in lits if x[0] == "$block"]
  rest = [x for x in lits if x[0] != "$block"]
  if len(block) != 1 or len(rest) != 3:
    return None
  head = [x for x in rest if _kind(_situation(x)) == "succ" and _base(x) in la.FLUENTS and not x[0].startswith("-")]
  poss = [x for x in rest if x[0] == "-poss"]
  if len(head) != 1 or len(poss) != 1:
    return None
  h = head[0]
  act, s0 = _situation(h)[1], _situation(h)[2]
  prem = [x for x in rest if x is not h and x not in poss]
  if not (asum.is_gk_var(act) and asum.is_gk_var(s0) and poss[0][1] == act and _situation(poss[0]) == s0
          and len(prem) == 1 and prem[0][0] == "-" + h[0] and prem[0][1:-1] == h[1:-1] and _situation(prem[0]) == s0
          and prem[0][-1][3:] == h[-1][3:] and block[0][2] == [sit.MARKERS[h[0]]] + h[1:]):
    return None
  return _atom(h)


# ---------------------------------------------------------------------------
# patterns


def _pattern(t, bound=None):
  """A clause term as a profile pattern.  With `bound`, a variable outside it is a wildcard."""
  if isinstance(t, list):
    return [_pattern(x, bound) for x in t]
  if asum.is_gk_var(t):
    return {"var": t[2:]} if bound is None or t in bound else {"wildcard": True}
  return t


def _variables(t, out):
  if isinstance(t, list):
    for x in t:
      _variables(x, out)
  elif asum.is_gk_var(t):
    out.add(t)
  return out


def _substitute(t, env):
  if isinstance(t, list):
    return [_substitute(x, env) for x in t]
  return env.get(t, t)


def _specialize(target, family):
  """The substitution that puts a target atom into a family, or None."""
  if family == "have":
    return {} if target[0] == "have" else None
  kind, name = family.split(":", 1)
  if target[0] != ("is rel2" if kind == "rel" else "has property"):
    return None
  if asum.is_gk_var(target[1]):
    return {target[1]: name}
  return {} if target[1] == name else None


def _family_pattern(family):
  w = {"wildcard": True}
  if family == "have":
    return ["have", w, w]
  kind, name = family.split(":", 1)
  return ["is rel2", name, w, w] if kind == "rel" else ["has property", name, w]


def _gk(t):
  """A source-spelling term in clause spelling (`Ann 1` -> `#:Ann 1`), by the compiler's own conversion."""
  return sit._term(t, set())


# ---------------------------------------------------------------------------
# the clause-role audit


def _audit(records):
  """Read every record of the view by its role.

  Returns {"bad": {family: reason}, "writes": [...], "frames": [atom], "ledger": {name: entry}}.  A family in
  `bad` (also `rel:*`, `property:*`) cannot be tracked.
  """
  bad, writes, frames, ledger, derived = {}, [], [], {}, set()

  def refuse(lits, reason):
    for lit, atom in _fluent_literals(lits):
      for fam in _families(atom):
        bad.setdefault(fam, reason)

  for rec in records:
    lits, role, name = _lits(rec), rec["role"], rec["name"]
    entry = ledger[name] = {"name": name, "role": role, "origin": rec["origin"], "digest": asum.digest(lits),
                            "disposition": None, "operations": 0}
    succ = [x for x in lits if x[0] != "$block" and _kind(_situation(x)) == "succ"
            and (_base(x) in la.FLUENTS or _base(x) in MARKER_OF)]
    if any(not x[0].startswith("-") and _base(x) == "derived_property" for x in lits) and not (
        role == "derived_no_inertia" and rec["origin"] == "source" and len(lits) == 1):
      bad.setdefault("property:*", "unsupported_writer")
    if role in PLAIN_ROLES:
      if succ:
        refuse(lits, "unsupported_writer")
        entry["disposition"] = "unsupported-writer"
      else:
        entry["disposition"] = PLAIN_ROLES[role]
    elif role in ("effect", "marker"):
      got = _transition(lits, role == "effect")
      if got is None:
        refuse(lits, "unsupported_writer")
        entry["disposition"] = "unsupported-writer"
        continue
      head, act, guards = got
      target = _atom(head) if role == "effect" else [MARKER_OF[head[0]]] + list(head[1:-1])
      writes.append({"clause": name, "kind": role, "sign": "-" if head[0].startswith("-") else "+", "action": act,
                     "target": target, "guards": guards})
      entry["disposition"] = "possible-write" if role == "effect" else "change-marker"
    elif role == "frame":
      atom = _frame(lits)
      if atom is None:
        refuse(lits, "unsupported_writer")
        entry["disposition"] = "unsupported-writer"
      else:
        frames.append(atom)
        entry["disposition"] = "frame"
    elif role == "derived_no_inertia" and rec["origin"] == "source":
      if len(lits) == 1 and lits[0][0] == "derived_property" and isinstance(lits[0][1], str) and len(lits[0]) == 2:
        derived.add(lits[0][1])
        bad.setdefault("property:" + lits[0][1], "computed_family")
        entry["disposition"] = "computed-family"
      else:
        bad.setdefault("property:*", "unsupported_writer")
        entry["disposition"] = "unsupported-writer"
    elif role == "derived_no_inertia":
      # the library's marker of a declared derived value: it applies to the values of `derived` only
      ok = len(lits) == 2 and lits[0][:1] == ["-derived_property"] and lits[1][0] == "changed_property" \
        and lits[1][1] == lits[0][1] and _kind(_situation(lits[1])) == "succ"
      if not ok:
        bad.setdefault("property:*", "unsupported_writer")
      entry["disposition"] = "change-marker" if ok else "unsupported-writer"
    elif role in ("standing_law", "ordinary"):
      heads = rec.get("heads")
      if heads is None:
        refuse(lits, "standing_writer")
      for atom in heads or []:
        for fam in _families(atom):
          bad.setdefault(fam, "standing_writer")
      entry["disposition"] = "standing-writer"
    else:
      refuse(lits, "unsupported_writer")
      entry["disposition"] = "unsupported-writer" if _fluent_literals(lits) else "no-fluent"
  return {"bad": bad, "writes": writes, "frames": frames, "ledger": ledger, "derived": derived}


def _view(source, query):
  """The records of the query's view, each with `origin`, and the prover input they give."""
  sel = ar._selection(query)
  objs = ar.query_input(source, query, "plan", "positive")       # checks the recorded view hash
  src, libc, ordc = lq.view_records(source, ar._library(), query["selected_clauses"]["view"], sel, query["excluded"] or [])
  units = {u["id"]: u for u in source["units"]}
  out = []
  for r in src:
    rec = dict(r, origin="source")
    if r["role"] == "standing_law" and r.get("unit") in units:
      rec["heads"] = [_gk(ef._atom(h)) for h in ef._law_heads(sit._unit_formula(units[r["unit"]]))]
    out.append(rec)
  out.extend(dict(r, origin="library") for r in libc)
  # an ordinary law is written body first: its last literal is its head
  out.extend(dict(r, origin="ordinary", heads=[_atom(r["clause"][-1])]) for r in ordc)
  named = {r["name"] for r in out}
  for o in objs:
    if o.get("@name") not in named:
      out.append({"name": o["@name"], "role": "query", "origin": "query",
                  "clause": {"@logic": o["@logic"]} if "@logic" in o else [o["@question"]]})
  return out, objs


# ---------------------------------------------------------------------------
# operations


def _insert_guards(guards, tracked, bound, target):
  """(profile guards, None) or (None, reason) for the conditions of a positive effect."""
  out, seen = [], set(bound)
  for g in guards:
    if not g[0].startswith("-"):
      return None, "negative_guard"
    if _base(g) in la.FLUENTS:
      atom = _atom(g)
      fams = _families(atom)
      if fams[0] not in tracked:
        return None, "guard_untracked_family"
      out.append({"scope": "old", "atom": _pattern(atom)})
    elif _base(g) in STATIC_GUARDS:
      atom = [_base(g)] + list(g[1:])
      out.append({"scope": "static", "atom": _pattern(atom)})
    else:
      return None, "guard_unsupported_predicate"
    _variables(atom, seen)
  if not _variables(target, set()) <= seen:
    return None, "unbound_head_variable"
  return out, None


def _operations(writes, frames, tracked):
  """(operations with provenance, omitted insertions).  An operation is (op, clause names, note)."""
  ops, omitted = [], []
  for w in writes:
    for fam in tracked:
      env = _specialize(w["target"], fam)
      if env is None:
        continue
      act, target = _substitute(w["action"], env), _substitute(w["target"], env)
      guards = _substitute(w["guards"], env)
      bound = _variables(act, set())
      action, loose = _pattern(act), _pattern(target, bound)
      loss = "if_removed" if guards else None
      if w["kind"] == "marker" or w["sign"] == "-":
        ops.append(({"kind": "forget", "action": action, "pattern": loose, "loss": loss}, w["clause"], None))
        if w["kind"] == "effect":
          ops.append(({"kind": "negative_write", "action": action, "pattern": loose}, w["clause"], None))
        continue
      found, why = _insert_guards(guards, tracked, bound, target)
      if why:
        ops.append(({"kind": "forget", "action": action, "pattern": loose, "loss": "always"}, w["clause"], "omitted_insertion:" + why))
        omitted.append({"clause": w["clause"], "family": fam, "reason": why})
      else:
        ops.append(({"kind": "forget", "action": action, "pattern": loose, "loss": loss}, w["clause"], None))
        ops.append(({"kind": "insert", "action": action, "fact": _pattern(target), "guards": found}, w["clause"], None))
  kept = set()
  for atom in frames:
    for fam in _families(atom):
      kept.update([f for f in tracked if f.startswith(fam[:-1])] if fam.endswith(":*") else [fam])
  for fam in tracked:
    if fam not in kept:
      # no persistence rule: the family is forgotten at every step, by every constructor.  The summary cannot keep
      # the fact; no clause says that it ends.  A removed fact is a loss.
      for c, slots in sorted(la.CONSTRUCTORS.items()):
        action = [c] + [{"var": "A%d" % i} for i in range(len(slots))]
        ops.append(({"kind": "forget", "action": action, "pattern": _family_pattern(fam), "loss": "if_removed"}, None,
                    "no_persistence_rule"))
  return ops, omitted


def _source_pattern(t, names):
  if la.is_var(t):
    return {"var": "T_" + t} if t in names else {"wildcard": True}
  return _gk(t)


def _transport(units, root, extra, records, initial, static):
  """(operations, inventory, reason).  The reason is `transport_inventory_incomplete` when a coverage check fails."""
  inventory = ef.transport(units, root, extra=extra)
  known = set((h, o) for u, h, o in ef._initial_facts(units, "holding", root))
  classes = ef._classes(units, extra)
  why = None
  for rec in records:
    lits = _lits(rec)
    for x in lits:
      if x[0] == "is rel2" and x[1] == "holding" and not (
          rec["role"] in ("initial_fact", "frame") or (rec["role"] == "effect" and rec["origin"] == "source")
          or (rec["origin"] == "library" and rec["name"] == "eff_take_holding")):
        why = why or "holding producer %s (%s)" % (rec["name"], rec["role"])
      if x[0] == "is rel2" and asum.is_gk_var(x[1]):
        why = why or "relation variable in %s" % rec["name"]
      if x[0] == "is rel2" and x[1] == "holding" and rec["role"] == "initial_fact" and _situation(x) == root and not (
          len(lits) == 1 and all(isinstance(t, str) and t.startswith("#:") for t in x[2:4])):
        why = why or "initial holding outside the concrete pairs (%s)" % rec["name"]
      if x[0] == "poss" and isinstance(x[1], list) and x[1][0] in ("move", "take") and not (
          (rec["role"] == "availability" and rec["origin"] == "source")
          or (rec["role"] == "applicability_default" and rec["origin"] == "library")):
        why = why or "move or take path %s (%s)" % (rec["name"], rec["role"])
      if x[0] == "poss" and not isinstance(x[1], list):
        why = why or "generic path %s" % rec["name"]
  for f in initial:
    if f[0] == "is rel2" and f[1] == "holding" and (f[2], f[3]) not in known:
      why = why or "initial holding %s outside the inventory's facts" % rp.show_atom(f)
  for f in static:
    if f[0] == "isa" and f[1] in ("person", "hand", "block") and f[1] not in classes.get(f[2], []):
      why = why or "inferred type %s outside the inventory's classes" % rp.show_atom(f)
  if why:
    return [], inventory, "transport_inventory_incomplete: " + why
  ops = []
  for e in inventory:
    names = {e["holder"]} if la.is_var(e["holder"]) else set()
    action = ["move", _source_pattern(e["holder"], names), {"var": "F"}, {"var": "T"}, {"var": "M"}]
    pattern = ["is rel2", "located_at", _source_pattern(e["object"], names), {"wildcard": True}]
    ops.append(({"kind": "forget", "action": action, "pattern": pattern, "loss": "if_removed"}, None,
                "transport:%s:%s" % (e["through"], ",".join(e["laws"]))))
  return ops, inventory, None


# ---------------------------------------------------------------------------
# the goal, the default table and a model's choice


def _goal_atoms(goal):
  """(ground positive fluent atoms in clause spelling, reason)."""
  parts = rp._conjuncts(goal)
  out = []
  for a in parts:
    if not (isinstance(a, list) and a and a[0] in la.FLUENTS and len(a) == la.FLUENTS[a[0]] + 1
            and all(isinstance(t, str) and not la.is_var(t) for t in a[1:])):
      return None, "unsupported_goal"
    out.append(_gk(a))
  return out, None


def _goal_families(f, out):
  """The families of every fluent atom of a goal formula, also of a goal outside the scored forms."""
  if isinstance(f, list) and f:
    if f[0] in la.FLUENTS:
      out.update(x for x in _families(f) if not x.endswith(":*"))
    else:
      for x in f[1:]:
        _goal_families(x, out)
  return out


def _milestones(records, subject):
  """(catalog {id: {fact, city}}, aliases {id: catalog id}).  An entry is a positive requirement of a restriction on
  a move of `subject` from a stated place.  Two restrictions with the same place and fact are one entry: the
  smallest identifier names it and the other identifiers are aliases.  The catalog is a rough feature set of this
  narrow clause form; it is not a list of every precondition."""
  out = {}
  for rec in records:
    if rec["role"] != "restriction_check" or rec.get("branch") != "match" or rec.get("constructor") != "move":
      continue
    lits = _lits(rec)
    head = [x for x in lits if x[0] == rec.get("check")]
    need = [x for x in lits if x[0].startswith("-") and _base(x) in la.FLUENTS]
    if len(head) != 1 or len(need) != 1 or len(lits) != 2:
      continue
    act, fact = head[0][1], _atom(need[0])
    if act[1] == subject and asum.is_ground(act[2]) and asum.is_ground(fact):
      out["ms:" + rec["check"]] = {"fact": fact, "city": act[2]}
  first, catalog, aliases = {}, {}, {}
  for name in sorted(out):
    key = asum.canonical(out[name])
    if key in first:
      aliases[name] = first[key]
    else:
      first[key] = name
      catalog[name] = out[name]
  return catalog, aliases


def _route_parameters(subject, destination, static):
  edges = [(f[1], f[2]) for f in static if f[0] == "connected"]
  if not edges:
    return None
  places = {destination} | {x for e in edges for x in e}
  distance, todo = {destination: 0}, [destination]
  while todo:
    here = todo.pop(0)
    for a, b in edges:
      if b == here and a not in distance:
        distance[a] = distance[here] + 1
        todo.append(a)
  return {"subject": subject, "destination": destination, "distance": distance, "no_route_distance": len(places) + 1}


def _choose(goal, witnesses, reason_of, static, catalog, aliases, choice):
  """(tracked families, score, choice record).  `reason_of(family)` is None for an admissible family."""
  atoms, why = _goal_atoms(goal)
  if witnesses:
    atoms, why = None, "witness_goal"
  fams = [asum.family_of(a) for a in atoms or []]
  ok = lambda fs: all(reason_of(f) is None for f in fs)
  blocks = sorted(f[2] for f in static if f[:2] == ["isa", "block"])
  surfaces = {f[1] for f in static if f[0] == "surface"}
  rows = {}
  if atoms and all(f in ("rel:on", "rel:holding") for f in fams) and ok(fams + ["rel:on"]) and all(
      a[3] in blocks if a[1] == "holding" else a[2] in blocks and (a[3] in blocks) != (a[3] in surfaces) for a in atoms):
    rows["blocks_links"] = (sorted(set(fams) | {"rel:on"}), {"template": "blocks_links", "goal": atoms, "blocks": blocks})
  route = None
  if atoms and len(atoms) == 1 and fams[0] == "rel:located_at" and ok(fams):
    route = _route_parameters(atoms[0][2], atoms[0][3], static)
  if route:
    rows["route_distance"] = (["rel:located_at"], dict(route, template="route_distance"))
  if atoms and ok(fams):
    rows["goal_count"] = (sorted(set(fams)), {"template": "goal_count", "goal": atoms})
  # places of the finite penalty: the endpoints of the static connected facts and the destination; a place outside
  # them, and one without a route, has the distance places + 1
  record = {"raw": copy.deepcopy(choice), "invalid": None, "additions": [], "origin": "default"}
  if choice is not None:
    bad = _choice_error(choice, rows, route, catalog, aliases, reason_of)
    if bad:
      record["invalid"] = bad
    else:
      if choice["score"] == "route_milestones":
        ms = [catalog[m] for m in sorted({aliases.get(m, m) for m in choice["milestones"]})]
        need, score = ["rel:located_at"] + [asum.family_of(m["fact"]) for m in ms], dict(route, template="route_milestones", milestones=ms)
      else:
        need, score = rows[choice["score"]]
      tracked = sorted(set(choice["tracked"]) | set(need))
      record.update(additions=sorted(set(tracked) - set(choice["tracked"])), origin="choice")
      return tracked, dict(score, units=asum.UNITS[score["template"]]), record
  for name in ("blocks_links", "route_distance", "goal_count"):
    if name in rows:
      tracked, score = rows[name]
      return tracked, dict(score, units=asum.UNITS[name]), record
  named = sorted(_goal_families(goal, set()))
  bad = [reason_of(f) for f in named if reason_of(f)]
  why = why or ("computed_goal" if bad and bad[0] in ("computed_family", "standing_writer") else "goal_family_unavailable")
  return [f for f in named if reason_of(f) is None], {"template": None, "reason": why}, record


def _choice_error(choice, rows, route, catalog, aliases, reason_of):
  """None for a valid choice, else the reason.  Every field's type is checked before a set or dictionary reads it."""
  strings = lambda xs: isinstance(xs, list) and all(isinstance(x, str) for x in xs) and len(set(xs)) == len(xs)
  if not (isinstance(choice, dict) and sorted(choice) == ["milestones", "schema", "score", "tracked"]
          and type(choice["schema"]) is int and choice["schema"] == CHOICE_SCHEMA):
    return "choice_schema"
  t, ms, score = choice["tracked"], choice["milestones"], choice["score"]
  if not (strings(t) and t and all(asum._family_ok(f) for f in t)):
    return "choice_tracked"
  if any(reason_of(f) for f in t):
    return "choice_unavailable_family"
  if not (isinstance(score, str) and score in asum.UNITS and strings(ms)):
    return "choice_score"
  if score == "route_milestones":
    ms = [aliases.get(m, m) for m in ms]
    if not ms or not route or any(m not in catalog for m in ms) or any(reason_of(asum.family_of(catalog[m]["fact"])) for m in ms):
      return "choice_milestones"
  elif ms or score not in rows:
    return "choice_score_not_applicable"
  return None


# ---------------------------------------------------------------------------
# situation positions


def _positions(objs):
  """The places of a situation term in the prover input of one discovery query: the first argument of the answer,
  the situation argument of the query's own definition helper, the first argument of `reachable`, and the situation
  slot of a context term.  The helper's place is read from the discovery question; a helper of another kind of query
  has an entity there and gets no selector."""
  out = [{"predicate": "$ans", "arity": "variable", "path": [1], "role": "answer_plan"}]
  for o in objs:
    q = o.get("@question")
    if q and q[0] == lq.DEFQ and q.count(sit.SIT) == 1 and o.get("@askvars") == len(q) - 1:
      out.append({"predicate": lq.DEFQ, "arity": len(q) - 1, "path": [q.index(sit.SIT)], "role": "query_plan"})
  for o in objs:
    for x in (lib.literals(o) if "@logic" in o else [o["@question"]]):
      if x[0] == "$block":
        continue
      name, n = _base(x), len(x) - 1
      if name == "reachable":
        out.append({"predicate": name, "arity": n, "path": [1], "role": "reachable"})
      elif sit.is_context(x[-1]):
        out.append({"predicate": name, "arity": n, "path": [n, 2], "via": "$ctxt", "role": "context"})
  return out


# ---------------------------------------------------------------------------
# the compiler


def _initial(initial, tracked, witnesses, mapped):
  """(initial facts in clause spelling, lossy).  A fact of an untracked family is left out by selection and is no
  loss.  A fact of a tracked family that names a replay witness outside `mapped`, the constant witness terms of the
  compiler's own witness records, is left out and sets lossy: the clauses have no name for that individual."""
  facts, lossy = [], False
  for f in initial:
    if asum.family_of(_gk(f)) not in tracked:
      continue
    if any(t in witnesses and t not in mapped for t in f[1:]):
      lossy = True
    else:
      facts.append(_gk(f))
  return facts, lossy


def _unavailable(reason, **fields):
  return dict({"status": "unavailable", "reason": reason, "profile": None}, **fields)


def _file_hash(name):
  with open(os.path.join(HERE, name), "rb") as f:
    return hashlib.sha256(f.read()).hexdigest()


def compile_profile(source, query, choice=None):
  """The planning-summary profile of one discovery query.

  Returns {"status", "reason", "profile", "families", "choice"}:

    ready        a profile with a score template
    partial      a profile whose score is undefined (World is still calculated)
    unavailable  no profile; `reason` says why.  The ordinary query is unchanged.

  `choice` is an optional selection {"schema": 1, "tracked", "score", "milestones"}; an invalid one is recorded
  and the default table is used.  `families` maps every family the goal, the choice or the initial state names
  to "tracked" or to the reason it is not.
  """
  if query.get("outcome") or not query.get("obligations") or query["query"]["kind"] not in ("plan", "reachable"):
    return _unavailable("not_a_runnable_discovery_query: %s" % ((query.get("outcome") or {}).get("outcome") or query["query"]["kind"]))
  if query.get("ambient") is not None or query.get("knower") is not None:
    return _unavailable("context_projection")
  root = query["planning_root"]
  records, objs = _view(source, query)
  if any(_kind(_situation(y)) != "none" and not (asum.is_gk_var(y[-1][3]) and (asum.is_gk_var(y[-1][4]) or y[-1][4] == sit.OBJ)
                                                 and y[-1][1] == "present")
         for r in records for y, a in _fluent_literals(_lits(r))):
    return _unavailable("context_projection")
  try:
    rsrc = rp.Source(source, root, None, None)
    state = rsrc.initial_state()
  except rp.NotChecked as e:
    return _unavailable("initial_not_covered: %s" % e.component)
  initial, static = state.export(), rsrc.export_static()
  audit = _audit(records)
  units = lq.admitted(source["units"], query["excluded"] or [])
  t_ops, inventory, t_why = _transport(units, root, ar.type_facts(source), records, initial, static)
  bad = dict(audit["bad"])
  if t_why:
    bad["rel:located_at"] = t_why

  def reason_of(fam):
    if not asum._family_ok(fam):
      return "unknown_family"
    if fam in EXCLUDED:
      return EXCLUDED[fam]
    why = bad.get(fam) or bad.get(fam.split(":")[0] + ":*")
    return why.split(":")[0] if why else None

  gk_static = [_gk(f) for f in static]
  goal = query["query"]["goal"]
  goal_atoms = _goal_atoms(goal)[0] or []
  catalog, aliases = _milestones(records, goal_atoms[0][2] if len(goal_atoms) == 1 and goal_atoms[0][:2] == ["is rel2", "located_at"] else None)
  tracked, score, chosen = _choose(goal, query["query"].get("witnesses") or [], reason_of, gk_static, catalog, aliases, choice)
  chosen.update(milestone_catalog=catalog, milestone_aliases=aliases)
  named = set(tracked) | _goal_families(goal, set())
  if isinstance(choice, dict) and isinstance(choice.get("tracked"), list):
    named |= {f for f in choice["tracked"] if isinstance(f, str)}
  families = {f: "tracked" if f in tracked else bad.get(f) or reason_of(f) or "not_selected" for f in sorted(named)}
  if not tracked:
    return _unavailable(score.get("reason") or "no_admissible_family", families=families, choice=chosen)
  ops, omitted = _operations(audit["writes"], audit["frames"], tracked)
  if "rel:located_at" in tracked:
    ops += t_ops
  mapped = {w["term"] for u in units for w in u.get("witnesses") or [] if isinstance(w["term"], str)}
  facts, lossy = _initial(initial, tracked, rsrc.witnesses, mapped)
  guard_predicates = {g["atom"][0] for op, c, n in ops for g in op.get("guards") or [] if g["scope"] == "static"}
  semantic = asum.normalize({
    "contract": {"summary": asum.CONTRACT, "normalizer": asum.NORMALIZER,
                 "transport": TRANSPORT_CONTRACT if "rel:located_at" in tracked else None},
    "root": root, "scope": {"ambient": None, "knower": None},
    "families": tracked, "initial": {"facts": facts, "lossy": lossy},
    "static": [f for f in gk_static if f[0] in guard_predicates],
    "constructors": {c: len(slots) for c, slots in la.CONSTRUCTORS.items()},
    "operations": [op for op, c, n in ops], "score": score,
    "situation_constructor": {"functor": sit.DO, "arity": 2, "action_arg": 1, "parent_arg": 2},
    "situation_positions": _positions(objs)})
  provenance = {}
  for op, clause, note in ops:
    p = provenance.setdefault(asum.digest(asum.normalize_operation(op)), {"clauses": [], "notes": []})
    if clause and clause not in p["clauses"]:
      p["clauses"].append(clause)
      audit["ledger"][clause]["operations"] += 1
    if note and note not in p["notes"]:
      p["notes"].append(note)
  for w in audit["writes"]:
    e = audit["ledger"][w["clause"]]
    if not e["operations"]:
      e["disposition"] = "excluded-family"
  import action_gk
  question = [o for o in objs if "@question" in o][0]
  binding = {
    "input_sha256": hashlib.sha256(action_gk.input_text(objs).encode()).hexdigest(), "input_clauses": len(objs),
    "source_hashes": source["hashes"], "query_hash": query["hash"], "view_hash": query["view_hash"],
    "view": query["selected_clauses"]["view"], "obligation": "plan", "polarity": "positive",
    "question": question["@name"], "answer_roles": ["plan"] + ["witness:%s" % w for w in query["query"].get("witnesses") or []],
    "selection": {"planning_root": root, "ambient": None, "knower": None, "excluded": query["excluded"] or []},
    "library": source["library"], "implementation": {n: _file_hash(n) for n in IMPLEMENTATION},
    "choice": chosen, "families": families, "transport_inventory": inventory if "rel:located_at" in tracked else None,
    "coverage": [audit["ledger"][r["name"]] for r in records],
    "operations": [dict(v, operation=k) for k, v in sorted(provenance.items())],
    "omitted_insertions": omitted}
  profile = {"schema": asum.SCHEMA, "profile_id": asum.profile_id(semantic), "semantic": semantic, "binding": binding}
  asum.validate(profile)
  return {"status": "ready" if score["template"] else "partial", "reason": score.get("reason"), "profile": profile,
          "families": families, "choice": chosen}
