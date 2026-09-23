"""Action profile: text effects, change markers, state policy, dependencies.

The pass `effects_state_policy` of the action compiler (A2.5, A2.8, A4.4, A6.3).

Effects.  A strict text effect `P -> after(A, L1 and .. and Ln)` gives, for
every head literal L,

  P(C(S)) and poss(A, C(S))  ->  L(C($do(A, S)))

and, for a negative L, the change marker of that fluent instance under the
same body and in the same successor:

  P(C(S)) and poss(A, C(S))  ->  changed_*(..., C($do(A, S)))

C(S) is a law context $ctxt(present, S, L, $obj) with S in the world slot
(encoding v2); the successor literals have the location variable ?:Lh.

P is read in the old situation for every head, so the heads of one effect
are simultaneous.  An effect clause needs poss; it never concludes poss, so
an effect supplies no executability.  A conditional write gets a
conditional marker.  A positive write gets no marker clause, as in the
library; it is kept in the signed-write metadata, because a backend with
signed persistence must stop the opposite-sign frame there.  Text effects and
library effects stay distinct clauses; nothing is deduplicated.  A text write
whose opposite the library writes for a unifiable action is recorded as a
possible conflict.  Both clauses stay (A2.7).

State policy.  A property value in the head of a standing law is

  computed        no other source of it: `derived_property(V)`, so it has no frame
  by declaration  `profile.policy.computed` / `.stored` names it
  ambiguous       also asserted initially or written by an action, and not
                  declared: ambiguous_state_policy on the law unit

A standing law whose head is a stored physical relation, possession,
clear_top or empty is unsupported_stored_state_law.

Dependencies.  Per law unit: the action pattern, the signed reads and the
signed writes.  For the source: the dynamic negative reads (a negative fluent
literal that a condition, a required condition, a defeater or a law body
reads), the transport inventory (a holding that may arise, initially, by a
text effect or by take, whose holder may move), and the potential backend
requirements.  Whether a query needs one of them is decided per query: a
snapshot query crosses no transition, a verify sequence is scanned, a plan
goal uses the inventory.  This metadata is always computed; no option turns
it off.

Nothing here calls a prover.
"""

import copy

import lc_action as la
import lc_action_library as lib
import lc_action_situate as sit

PASS = "effects_state_policy"
FORM = "effect"
STORED_PROPERTIES = ("clear_top", "empty")


def effects(f, scope=(), conditions=()):
  """(binders, conditions, action, head literals) of every `after` of a unit formula."""
  op = f[0]
  if op == "forall":
    return effects(f[2], tuple(v for v in scope if v != f[1]) + (f[1],), conditions)
  if op == "and":
    return [e for x in f[1:] for e in effects(x, scope, conditions)]
  if op == "implies":
    return effects(f[2], scope, conditions + (f[1],))
  if op == "after":
    return [(scope, list(conditions), f[1], _flat(f[2]))]
  return []


def _flat(f):
  return [y for x in f[1:] for y in _flat(x)] if f[0] == "and" else [f]


def _atom(lit):
  return lit[1] if lit[0] == "not" else lit


def _sign(lit):
  return "-" if lit[0] == "not" else "+"


def marker_atom(atom):
  return [sit.MARKERS[atom[0]]] + list(atom[1:])


def _situated_effect(scope, conditions, action, heads):
  """forall V.. (P(S) and poss(A, S) -> heads and markers at $do(A, S)), without the situation binder."""
  succ = [sit.DO, action, sit.SIT]
  body = [sit._situate(c, sit.SIT) for c in conditions] + [["poss", action, sit.SIT]]
  out = []
  for h in heads:
    out.append(sit._situate(h, succ))
    if h[0] == "not":
      out.append(marker_atom(h[1]) + [succ])
  f = ["implies", body[0] if len(body) == 1 else ["and"] + body, out[0] if len(out) == 1 else ["and"] + out]
  for v in reversed(scope):
    f = ["forall", v, f]
  return f


def _role(lits):
  head = [x for x in lits if sit.situation_class(x) == "successor"]
  return "marker" if head and head[0][0] in sit.MARKERS.values() else "effect"


def compile_unit(unit, namer, library=None):
  """Clauses and write metadata of one structurally supported effect unit."""
  out = {"situated": None, "situation": "successor", "clauses": None, "witnesses": [],
         "diagnostic": None, "requirements": [], "note": None, "writes": []}
  formula = sit._unit_formula(unit)
  found = effects(formula)
  views = [_situated_effect(*e) for e in found]
  out["situated"] = ["forall", sit.SIT, views[0] if len(views) == 1 else ["and"] + views]
  p = unit.get("confidence")
  if p is not None and p < 1:
    out["clauses"] = []
    out["diagnostic"] = ("unsupported_confidence_form", "a text effect with probability %s: only strict text effects "
                                                        "have a reviewed effect and marker compilation" % p, None)
    return out
  records = []
  try:
    for (scope, conditions, action, heads), view in zip(found, views):
      situated, clauses, witnesses = sit.clausify_situated(unit["id"], ["forall", sit.SIT, view], namer(unit["id"]))
      out["witnesses"].extend(witnesses)
      for c in clauses:
        rec = {"role": _role(c["clause"]), "unit": unit["id"], "clause": c["clause"], "pass": PASS,
               "provenance": unit["id"], "defeasible": False, "strict": True, "action": copy.deepcopy(action),
               "conditional": bool(conditions)}
        if rec not in records:
          records.append(rec)
      for h in heads:
        w = {"unit": unit["id"], "action": copy.deepcopy(action), "literal": copy.deepcopy(_atom(h)), "sign": _sign(h),
             "conditional": bool(conditions), "marker": h[0] == "not",
             "stops_opposite_frame": True, "library_conflicts": _conflicts(action, h, library)}
        out["writes"].append(w)
  except sit.Unsupported as ex:
    out["clauses"], out["writes"] = [], []
    out["diagnostic"] = (ex.reason, str(ex), None)
    return out
  out["clauses"] = records
  hits = sorted({c for w in out["writes"] for c in w["library_conflicts"]})
  if hits:
    out["note"] = ("a text write has the opposite sign of the library effect %s for a unifiable action; both clauses "
                   "stay, and the state validation reports an established conflict" % ", ".join(hits))
  return out


# ---------------------------------------------------------------------------
# a text write against the library's strict effects


def _is_v(t):
  return isinstance(t, str) and (t.startswith("?:") or la.is_var(t))


def _walk(t, s):
  while _is_v(t) and t in s:
    t = s[t]
  return t


def _unify(a, b, s):
  a, b = _walk(a, s), _walk(b, s)
  if a == b:
    return s
  if _is_v(a):
    return dict(s, **{a: b})
  if _is_v(b):
    return dict(s, **{b: a})
  if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
    for x, y in zip(a, b):
      s = _unify(x, y, s)
      if s is None:
        return None
    return s
  return None


def _plain(t):
  """A library term in source spelling: `#:id` is the id."""
  if isinstance(t, list):
    return [_plain(x) for x in t]
  return t[2:] if isinstance(t, str) and t.startswith("#:") else t


def _conflicts(action, head, library):
  """Names of the library effects that write the opposite sign of `head` for a unifiable action."""
  out = []
  atom, negative = _atom(head), head[0] == "not"
  for c in (library or {}).get("clauses", []):
    if c["role"] != "effect":
      continue
    lits = lib.literals(c["clause"])
    poss = [x for x in lits if x[0] == "-poss"]
    concl = [x for x in lits if lib.predicate(x) in la.FLUENTS and isinstance(sit.situation_of(x), list)]
    if not poss or not concl or lib.positive(concl[0]) != negative:
      continue
    s = _unify(_plain(poss[0][1]), action, {})
    if s is not None and _unify(_plain([lib.predicate(concl[0])] + concl[0][1:-1]), atom, s) is not None:
      out.append(c["name"])
  return out


def _standardize(t, tag):
  """Variables of two units are different variables."""
  if isinstance(t, list):
    return [_standardize(x, tag) for x in t]
  return "?:%s_%s" % (tag, t) if _is_v(t) else t


def _apply(t, s):
  t = _walk(t, s)
  return [_apply(x, s) for x in t] if isinstance(t, list) else t


def library_writes(action, library):
  """The signed writes the library's strict effects give for an action pattern."""
  out = []
  for c in (library or {}).get("clauses", []):
    if c["role"] != "effect":
      continue
    lits = lib.literals(c["clause"])
    poss = [x for x in lits if x[0] == "-poss"]
    concl = [x for x in lits if lib.predicate(x) in la.FLUENTS and isinstance(sit.situation_of(x), list)]
    s = _unify(_plain(poss[0][1]), action, {}) if poss and concl else None
    if s is not None:
      out.append({"literal": _apply(_plain([lib.predicate(concl[0])] + concl[0][1:-1]), s),
                  "sign": "+" if lib.positive(concl[0]) else "-", "clause": c["name"], "conditional": len(lits) > 2})
  return out


# ---------------------------------------------------------------------------
# stored and computed properties


def _law_heads(f):
  """The signed head literals of a standing law formula."""
  op = f[0]
  if op in ("state_law", "normally"):
    return _law_heads(f[1])
  if op == "forall":
    return _law_heads(f[2])
  if op == "implies":
    return _law_heads(f[2])
  if op == "and":
    return [h for x in f[1:] for h in _law_heads(x)]
  return [f]


def _asserted(f, out):
  """Atoms an initial description asserts: every atom outside an antecedent."""
  op = f[0]
  if op == "implies":
    _asserted(f[2], out)
  elif op in la.QUANTIFIERS:
    _asserted(f[2], out)
  elif op in ("and", "or", "not", "normally"):
    for x in f[1:]:
      _asserted(x, out)
  elif op in la.FLUENTS:
    out.append(f)
  return out


def _change_values(f, out):
  """The value slot of every change term of a formula; a variable value is `*`."""
  if isinstance(f, list) and f:
    if f[0] == "change" and len(f) == 5:
      out.add("*" if la.is_var(f[3]) else f[3])
    for x in f[1:]:
      _change_values(x, out)
  return out


def state_policy(units, policy):
  """(derived_property records, diagnostics, table) for the standing laws of a source.

  A diagnostic is (unit id, reason, message, detail).  The table has one row
  per property value in a standing-law head.
  """
  supported = [u for u in units if u["status"] == "supported"]
  asserted, written = {}, {}
  for u in supported:
    f = sit._unit_formula(u)
    if u["form"] == "description_initial":
      for a in _asserted(f, []):
        if a[0] == "has property":
          asserted.setdefault(a[1], []).append(u["id"])
    if u["form"] == FORM:
      for scope, conditions, action, heads in effects(f):
        for h in heads:
          if _atom(h)[0] == "has property":
            written.setdefault(_atom(h)[1], []).append(u["id"])
    for v in _change_values(f, set()):
      written.setdefault(v, []).append(u["id"])
  records, diagnostics, table = [], [], {}
  for u in supported:
    if u["form"] != "state_law":
      continue
    for h in _law_heads(sit._unit_formula(u)):
      a = _atom(h)
      if a[0] in ("is rel2", "have") or (a[0] == "has property" and a[1] in STORED_PROPERTIES):
        what = a[1] if a[0] != "have" else "have"
        diagnostics.append((u["id"], "unsupported_stored_state_law",
                            "a standing law that continuously asserts the stored physical state %s: it would compete "
                            "with the action effects and the frames; no tested policy exists (A2.8)" % what, "stored_head"))
        continue
      if a[0] != "has property":
        continue
      v = a[1]
      row = table.setdefault(v, {"law_units": [], "asserted_in": sorted(set(asserted.get(v, []))),
                                 "written_in": sorted(set(written.get(v, []) + written.get("*", []))), "policy": None})
      if u["id"] not in row["law_units"]:
        row["law_units"].append(u["id"])
  for v in sorted(table):
    row = table[v]
    mixed = bool(row["asserted_in"] or row["written_in"])
    if v in policy["computed"]:
      row["policy"] = "computed_declared"
    elif v in policy["stored"]:
      row["policy"] = "stored_declared"
    elif not mixed:
      row["policy"] = "computed"
    else:
      row["policy"] = "ambiguous"
      for uid in row["law_units"]:
        diagnostics.append((uid, "ambiguous_state_policy",
                            "%s is the head of a standing law (%s) and also %s; declare it under profile.policy.stored "
                            "or profile.policy.computed" % (v, ", ".join(row["law_units"]), " and ".join(
                              x for x in ("asserted initially (%s)" % ", ".join(row["asserted_in"]) if row["asserted_in"] else "",
                                          "written by an action (%s)" % ", ".join(row["written_in"]) if row["written_in"] else "") if x)),
                            "mixed_stored_computed"))
    if row["policy"] in ("computed", "computed_declared"):
      records.append({"role": "derived_no_inertia", "unit": None, "units": list(row["law_units"]),
                      "clause": [["derived_property", v]], "pass": PASS, "property": v, "policy": row["policy"]})
  return records, diagnostics, table


# ---------------------------------------------------------------------------
# dependencies


def _literals(f, out, positive=True):
  """(atom, sign) of every fluent or static literal of a condition."""
  op = f[0]
  if op == "not":
    _literals(f[1], out, not positive)
  elif op in la.QUANTIFIERS:
    _literals(f[2], out, positive)
  elif op in ("and", "or", "normally"):
    for x in f[1:]:
      _literals(x, out, positive)
  elif op in la.FLUENTS or op in la.STATIC:
    out.append((f, "+" if positive else "-"))
  return out


def _law_parts(f, conditions=()):
  """(conditions, head) pairs of a law formula; the head is can, not can, after, executable's REQUIRED or a state head."""
  op = f[0]
  if op in ("forall", "state_law"):
    return _law_parts(f[2] if op == "forall" else f[1], conditions)
  if op == "and":
    return [p for x in f[1:] for p in _law_parts(x, conditions)]
  if op == "implies":
    return _law_parts(f[2], conditions + (f[1],))
  return [(list(conditions), f)]


def unit_dependencies(unit, library=None):
  """{unit, form, actions, reads, writes, defeater} of one supported law unit."""
  f = sit._unit_formula(unit)
  reads, writes, defeater = [], [], False
  for conditions, head in _law_parts(f):
    execs = [x for c in conditions for x in _flat(c) if x[0] == "executable"]
    for c in conditions:
      for x in _flat(c):
        if x[0] != "executable":
          reads.extend(_literals(x, []))
    if unit["form"] == "restriction" and execs:
      reads.extend(_literals(head, []))
    elif head[0] == "after":
      writes.extend((_atom(h), _sign(h)) for h in _flat(head[2]))
    elif unit["form"] == "state_law":
      writes.extend((_atom(h), _sign(h)) for h in _law_heads(head))
    elif unit["form"] == "denial":
      defeater = True
  show = lambda pairs: [{"literal": copy.deepcopy(a), "sign": s, "dynamic": a[0] in la.FLUENTS} for a, s in pairs]
  by_library = [dict(w, action=copy.deepcopy(t)) for t in (unit.get("action_terms") or []) if unit["form"] == "availability"
                for w in library_writes(t, library)]
  return {"unit": unit["id"], "form": unit["form"], "actions": copy.deepcopy(unit.get("action_terms") or []),
          "reads": show(reads), "writes": show(writes), "library_writes": by_library, "defeater": defeater}


def _positive_facts(f, out, positive=True):
  """The positive atoms an initial description states.  The sign is kept: `not holding` is no holding."""
  op = f[0]
  if op == "not":
    _positive_facts(f[1], out, not positive)
  elif op == "and" and positive:
    for x in f[1:]:
      _positive_facts(x, out, positive)
  elif op in la.QUANTIFIERS and positive:
    _positive_facts(f[2], out, positive)
  elif op == "implies" and positive:
    _positive_facts(f[2], out, positive)
  elif op == "normally":
    _positive_facts(f[1], out, positive)
  elif positive and (op in la.FLUENTS or op in la.STATIC):
    out.append(f)
  return out


def _initial_facts(units, relation, root=None):
  """(unit id, X, Y) of every positive ground `relation` fact of a supported initial description.

  With `root` (a world name) only the facts of that world: a fact of another
  world never reaches a view rooted there (migration step 1b.6).
  """
  out = []
  for u in units:
    if u["form"] != "description_initial" or u["status"] != "supported":
      continue
    if root is not None and (u.get("world") or "W0") != root:
      continue
    for a in _positive_facts(sit._unit_formula(u), []):
      if a[0] == "is rel2" and a[1] == relation and la.is_concrete(a[2]) and la.is_concrete(a[3]):
        out.append((u["id"], a[2], a[3]))
  return out


def _classes(units):
  """{entity: [class]} from the positive ground isa facts of the supported descriptions."""
  out = {}
  for u in units:
    if u["status"] == "supported" and u["form"] in ("description_initial", "description_static"):
      for a in _positive_facts(sit._unit_formula(u), []):
        if a[0] == "isa" and la.is_concrete(a[2]):
          out.setdefault(a[2], []).append(a[1])
  return out


def _terms(units, constructor, forms=("availability",)):
  return [(u["id"], t) for u in units if u["status"] == "supported" and u["form"] in forms
          for t in (u.get("action_terms") or []) if t[0] == constructor]


def _may(a, b):
  """Two slot terms can name one entity: equal, or one is a variable."""
  return a == b or la.is_var(a) or la.is_var(b)


def _movers(units, holder, classes):
  """How `holder` may move: the source permissions, else the library default for a person, else nothing."""
  own = sorted({uid for uid, t in _terms(units, "move") if _may(t[1], holder)})
  if own:
    return own
  if la.is_var(holder) or "person" in classes.get(holder, []):
    return ["library:poss_move_person"]
  return []


def transport(units, root=None):
  """Holdings that a holder's movement would carry: the library has no co-movement transition.

  After the holder moves, the frame keeps the object's old location, and no
  clause gives the new one.  A holding can arise from

    initial_holding   a positive `holding` fact of an initial description
    text_effect       a positive text effect that writes `holding`
    source_take       a `take` permission of the source
    library_take      the library's default `take` of a hand, for a block

  An entry is listed only when its holder may move (a source `move`
  permission, or the library default for a person).  The list is a
  conservative inventory of possible dependencies.  It is not complete
  reachability: it does not prove that the holding or the movement is
  executable.  A query decides with `query_transport`.  Possession (`have`)
  states no physical accompaniment and is never listed; a negative `holding`
  fact is no holding.  With `root` the initial holdings and locations are
  those of that world only; the source-level inventory (no root) lists every
  world's.
  """
  classes = _classes(units)
  located = _initial_facts(units, "located_at", root)
  out = []

  def add(holder, obj, through, laws):
    movers = _movers(units, holder, classes)
    if not movers:
      return
    where = sorted({u for u, x, p in located if _may(x, obj)})
    entry = {"object": obj, "holder": holder, "through": through, "laws": sorted(laws),
             "holder_moves_by": movers, "location_units": where,
             "units": sorted(set([x for x in laws + movers if not x.startswith("library:")] + where))}
    if entry not in out:
      out.append(entry)

  for uid, holder, obj in _initial_facts(units, "holding", root):
    add(holder, obj, "initial_holding", [uid])
  for u in units:
    if u["status"] == "supported" and u["form"] == FORM:
      for scope, conditions, action, heads in effects(sit._unit_formula(u)):
        for h in heads:
          if h[0] == "is rel2" and h[1] == "holding":
            add(h[2], h[3], "text_effect", [u["id"]])
  for uid, t in _terms(units, "take"):
    add(t[1], t[2], "source_take", [uid])
  hands = sorted(x for x, cs in classes.items() if "hand" in cs)
  for obj in sorted(x for x, cs in classes.items() if "block" in cs):
    for h in hands:
      if h != obj:
        add(h, obj, "library_take", ["library:poss_take_hand"])
  return out


def _reads_location(goal, objects):
  """The objects of `objects` whose `located_at` the formula reads; a variable reads all of them."""
  hits = []

  def walk(f):
    if isinstance(f, list) and f:
      if f[0] == "is rel2" and len(f) == 4 and f[1] == "located_at":
        hits.extend(o for o in objects if _may(f[2], o) and o not in hits)
      for x in f[1:]:
        walk(x)
  walk(goal or [])
  return hits


def carried_in_sequence(sequence, units, root=None):
  """Structural scan of a supplied sequence: (object, holder, step) for every object a moving holder carries.

  Holdings start from the positive initial `holding` facts.  `take(H, X)`
  and a positive text effect on `holding` add one; `put_on(H, X, _)`,
  `put_in(H, X, _)` and a negative text effect on `holding` release it.  The
  scan does not decide whether the sequence is executable.  With `root` the
  initial holdings are those of that world.
  """
  held = [(h, x) for u, h, x in _initial_facts(units, "holding", root)]
  writes = [(action, h) for u in units if u["status"] == "supported" and u["form"] == FORM
            for scope, conditions, action, heads in effects(sit._unit_formula(u))
            for h in heads if _atom(h)[0] == "is rel2" and _atom(h)[1] == "holding"]
  out = []
  for n, act in enumerate(sequence or []):
    if act[0] == "move":
      out.extend((x, h, n + 1) for h, x in held if h == act[1] and (x, h, n + 1) not in out)
    if act[0] == "take" and (act[1], act[2]) not in held:
      held.append((act[1], act[2]))
    if act[0] in ("put_on", "put_in"):
      held = [p for p in held if p != (act[1], act[2])]
    for pattern, h in writes:
      s = _unify(_standardize(pattern, "e"), act, {})
      if s is None:
        continue
      pair = tuple(_apply(_standardize(t, "e"), s) for t in _atom(h)[2:4])
      if h[0] == "not":
        held = [p for p in held if p != pair]
      elif pair not in held and all(la.is_concrete(t) for t in pair):
        held.append(pair)
  return out


def query_transport(kind, goal, sequence, units, deps, root=None):
  """The transport dependency of one query at the planning root `root`, or None.

  question / ask   bound to the root: no transition, never affected
  verify           the supplied sequence is scanned from the root's holdings;
                   an empty sequence is the root
  plan / reachable the conservative inventory of `transport`, computed from
                   the root's facts only (migration step 1b.6); without a root,
                   the source-level inventory `deps["transport"]`
  """
  if kind in ("question", "ask") or not deps:
    return None
  if kind == "verify":
    carried = carried_in_sequence(sequence, units, root)
    objects = _reads_location(goal, [x for x, h, n in carried])
    hits = [(x, h, n) for x, h, n in carried if x in objects]
    if not hits:
      return None
    where = sorted({u for u, x, p in _initial_facts(units, "located_at", root) if x in objects}
                   | {u for u, h, x in _initial_facts(units, "holding", root) if x in objects})
    return {"objects": sorted(objects), "units": where,
            "detail": "; ".join("step %d moves %s while it holds %s" % (n, h, x) for x, h, n in hits)}
  inventory = transport(units, root) if root is not None else deps.get("transport", [])
  entries = [t for t in inventory if _reads_location(goal, [t["object"]])]
  if not entries:
    return None
  return {"objects": sorted({t["object"] for t in entries}), "units": sorted({u for t in entries for u in t["units"]}),
          "detail": "; ".join("%s may hold %s (%s) and may move (%s)" % (t["holder"], t["object"], t["through"],
                                                                        ", ".join(t["holder_moves_by"])) for t in entries)}


def dependencies(units, library=None):
  """The source-level dependency record and the potential backend requirements."""
  per_unit = [unit_dependencies(u, library) for u in units
              if u["status"] == "supported" and u["form"] in ("availability", "denial", "restriction", "effect", "state_law")]
  negative = [{"unit": d["unit"], "form": d["form"], "literal": r["literal"], "through": "defeater" if d["defeater"] else "condition"}
              for d in per_unit for r in d["reads"] if r["dynamic"] and r["sign"] == "-"]
  # who can make a read negative fact positive: a real write, as opposed to a backend that forgets the negative
  # The list holds the writers found through the source units and their action terms.  An action that only
  # a library default permits is not listed, so an empty list is no proof that no writer exists.
  for n in negative:
    n["positive_writers_complete"] = False
    n["positive_writers"] = sorted({d["unit"] for d in per_unit
                                    for w in [x for x in d["writes"] if d["form"] == "effect"] + d["library_writes"]
                                    if w["sign"] == "+" and _unify(_standardize(w["literal"], "w"), _standardize(n["literal"], "r"), {}) is not None})
  deps = {"units": per_unit, "dynamic_negative_reads": negative, "transport": transport(units)}
  shared = sorted(u["id"] for u in units if "shared_source_confidence" in (u.get("requirements") or []))
  req = {}
  if negative:
    req["negative_persistence"] = {"status": "potential", "units": sorted({n["unit"] for n in negative}),
                                   "decided": "per query, by its horizon"}
  if shared:
    req["shared_source_confidence"] = {"status": "potential", "units": shared, "decided": "per query, by the consequences it uses"}
  return deps, req
