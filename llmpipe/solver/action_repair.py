"""The controller's repairs of a translation on the action route, and the readings the compiler adjusts.

The labels are those of the repair table in docs/encodings/action-prompts.md.  Each repair applies only when its
condition holds.  When the condition fails, nothing changes and the ordinary checks
decide.  Each applied repair returns a record: its kind, the repair id, the unit, the text before and the text after,
and the units that support it.  The controller keeps the records in the attempt's history.

  K9  one entity, one id: a later id with the index of an earlier id is the earlier entity when the text has a clear
      anaphor (the later name is the head noun of the first name, the later sentence says "the <name>", and no other
      entity has that head noun).  The same index and head noun without the anaphor is a question for Stage 1.
  K8  ["can", unspecified, ACTION] with `unspecified` as the action's actor is ["exists", A, ["can", A, ACTION]]:
      the compiler then gives its unsupported diagnosis; no usable actor is supplied.
  K7  ["take", X, MODE] with a standard travel mode as a bare word, in a travel law, is a move by that means.
  K6  in a travel law, an unstated endpoint of a move is a universally quantified variable, bound at the scope of
      its head.
  K5  a mention of an action in an effect, a supplied step or an executable question takes the tool of its one
      permission when the mention leaves the tool `unspecified`.
  K16 a dependency between states that Stage 1 types as a strict rule, without a time, a snapshot or a context, and
      that Stage 2 wrote as a description ("Whenever a block is on the table, the block is steady") becomes a
      standing rule, state_law, by the state-rule convention.  A normal rule keeps its form: a default is not a
      strict standing law.

  K13 `value_mismatches`: a later mention whose value differs from its one permission gets one message per unit.
  K15 `unstated_values`, `clarification_refusals`: what a clarification reply may change.
  K1, K2, K11  `adjusted_reading`: the readings the compiler adjusts (the last section).

A travel law is a source unit whose one Stage-1 action of mode capability travels by a standard means (the
instrument or the target) and states no source and no destination.  No repair changes a value that a unit states,
and none applies to a supplied step's endpoints.
"""

import copy
import json
import re

import action_english as aen
import lc_action as la
import linguistics

INDEX = re.compile(r"^(.*) (\d+)$")
UNSPEC = la.UNSPECIFIED


def _dump(x):
  return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def _record(kind, repair, unit, before, after, support):
  return {"kind": kind, "repair": repair, "unit": unit, "before": before, "after": after, "support": list(support)}


# ---------------------------------------------------------------------------
# K9: one entity, one id


def _head(name):
  words = name.split()
  return words[-1].lower() if words else ""


def _concrete(units):
  """[(id, name, index, unit)] of the concrete Stage-1 entities with an index, in first-mention order."""
  out, seen = [], set()
  for u in units:
    for e in u.get("entities") or []:
      if not (isinstance(e, dict) and e.get("type") == "concrete" and isinstance(e.get("id"), str)):
        continue
      m = INDEX.match(e["id"])
      if m and e["id"] not in seen:
        seen.add(e["id"])
        out.append((e["id"], m.group(1), m.group(2), u))
  return out


def id_findings(units):
  """(merges, questions) of the Stage-1 units.

  merges     [{"before": later id, "after": first id, "units": the units that name the later id, "first": the
             unit that names the first id}] for each clear anaphor
  questions  one correction message per later id with the index and the head noun of an earlier id and no clear
             anaphor
  Two ids with one index and different head nouns are two entities: neither a merge nor a question."""
  concrete = _concrete(units)
  first = {}
  for eid, name, idx, u in concrete:
    first.setdefault(idx, (eid, name, u))
  merges, questions = [], []
  for eid, name, idx, u in concrete:
    base_id, base, base_unit = first[idx]
    if eid == base_id or _head(name) != _head(base):
      continue
    others = [c for c in concrete if c[2] != idx and _head(c[1]) == _head(name)]
    anaphor = (name.lower() == _head(base) and len(base.split()) > 1 and not others
               and re.search(r"\bthe %s\b" % re.escape(name), u.get("text") or "", re.I) is not None)
    named = [x["unit_id"] for x in units if any(isinstance(e, dict) and e.get("id") == eid
                                                   for e in x.get("entities") or [])]
    if anaphor:
      merges.append({"before": eid, "after": base_id, "units": named, "first": base_unit["unit_id"]})
    else:
      questions.append("entities %r (unit %s) and %r (units %s) share the index %s and the head noun %s: one entity "
                       "keeps one id in every unit, and two different entities take two different indices"
                       % (base_id, base_unit["unit_id"], eid, ", ".join(named), idx, _head(name)))
  return merges, questions


def rename(x, mapping):
  """A copy of x with every string value equal to a key of mapping replaced; object keys stay."""
  if isinstance(x, list):
    return [rename(y, mapping) for y in x]
  if isinstance(x, dict):
    return {k: rename(v, mapping) for k, v in x.items()}
  if isinstance(x, str) and x in mapping:
    return mapping[x]
  return x


def _rename_text(text, old, new):
  """The id `old` replaced by `new` in a unit's text, except where it is already the end of `new`."""
  prefix = new[:-len(old)] if new.endswith(old) else None
  out, last = [], 0
  for m in re.finditer(r"(?<!\w)%s(?!\w)" % re.escape(old), text):
    if prefix and text[:m.start()].endswith(prefix):
      continue
    out.append(text[last:m.start()])
    out.append(new)
    last = m.end()
  out.append(text[last:])
  return "".join(out)


def merge_units(units, merges):
  """(units, records): the Stage-1 units with each merged id replaced by the first id, in the fields and the text.
  An entity listed twice in one unit is listed once."""
  mapping = {m["before"]: m["after"] for m in merges}
  out, records = [], []
  for u in units:
    v = {k: (val if k in ("unit_id", "text") else rename(val, mapping)) for k, val in u.items()}
    text = u.get("text") or ""
    for old, new in mapping.items():
      text = _rename_text(text, old, new)
    if isinstance(u.get("text"), str):
      v["text"] = text
    if isinstance(v.get("entities"), list):
      seen, ents = set(), []
      for e in v["entities"]:
        k = e.get("id") if isinstance(e, dict) else None
        if k is not None and k in seen:
          continue
        seen.add(k)
        ents.append(e)
      v["entities"] = ents
    if v != u:
      records.append(_record("entity_merged", "K9", u["unit_id"], u.get("text"), v.get("text"),
                             sorted({m["first"] for m in merges} | {u["unit_id"]})))
    out.append(v)
  return out, records


def merge_response(parsed, merges):
  """(parsed, records): a Stage-2 response with each merged id replaced by the first id."""
  if not merges:
    return parsed, []
  mapping = {m["before"]: m["after"] for m in merges}
  new = rename(parsed, mapping)
  if new == parsed:
    return parsed, []
  logic = new.get("logic") if isinstance(new, dict) else new
  old_logic = parsed.get("logic") if isinstance(parsed, dict) else parsed
  records = []
  if isinstance(logic, list) and isinstance(old_logic, list) and len(logic) == len(old_logic):
    for a, b in zip(old_logic, logic):
      if a != b and isinstance(a, list) and len(a) > 1:
        records.append(_record("entity_merged", "K9", a[1], _dump(a), _dump(b), sorted({m["first"] for m in merges})))
  if not records:
    records.append(_record("entity_merged", "K9", None, _dump(parsed), _dump(new), sorted({m["first"] for m in merges})))
  return new, records


# ---------------------------------------------------------------------------
# formula helpers


def _body(pkg):
  """(holder, index) of the formula of a source package: holds(W, F), or and(holds(W, F), @p); else None."""
  f = pkg[2]
  if isinstance(f, list) and f[:1] == ["and"] and len(f) >= 2 and isinstance(f[1], list) and f[1][:1] == ["holds"]:
    f = f[1]
  if isinstance(f, list) and f[:1] == ["holds"] and len(f) == 3:
    return f, 2
  return None


def _strings(f, out):
  if isinstance(f, list):
    for x in f:
      _strings(x, out)
  elif isinstance(f, str):
    out.add(f)
  return out


def _fresh(used, base):
  name, k = base, 1
  while name in used:
    k += 1
    name = "%s%d" % (base, k)
  used.add(name)
  return name


def _paths(f, pred, path=()):
  """[(path, node)] of the nodes of f that satisfy pred, top-down; a matching node is not searched further."""
  if not isinstance(f, list):
    return []
  if pred(f):
    return [(path, f)]
  return [x for i, g in enumerate(f) for x in _paths(g, pred, path + (i,))]


def _at(f, path):
  for i in path:
    f = f[i]
  return f


def _occurrences(f, v, out, path=()):
  if isinstance(f, list):
    for i, x in enumerate(f):
      if x == v:
        out.append(path + (i,))
      else:
        _occurrences(x, v, out, path + (i,))
  return out


def _capability_actions(u):
  return [a for a in u.get("actions") or [] if isinstance(a, dict) and a.get("mode") == "capability"]


def _travel(action):
  roles = action.get("roles") or {}
  return (not roles.get("source") and not roles.get("destination")
          and (roles.get("instrument") in la.STANDARD_MODES or roles.get("target") in la.STANDARD_MODES))


def _is_can(f):
  return f[:1] == ["can"] and len(f) == 3


def _law_terms(f):
  """[(path of the term, negated)] of the action terms of a law: can heads (also under not and normally) and the
  executable atom of a restriction.  A path is relative to f."""
  out = []
  for path, node in _paths(f, lambda n: (_is_can(n) or n[:1] == ["executable"] and len(n) == 2)):
    if isinstance(node[-1], list):
      negated = bool(path) and _at(f, path[:-1])[:1] == ["not"]
      out.append((path + (len(node) - 1,), negated))
  return out


# ---------------------------------------------------------------------------
# K8, K7, K6


def _agentless(f, used, parent_not=False):
  """K8 on one formula: (formula, count)."""
  if not isinstance(f, list) or not f:
    return f, 0
  if (_is_can(f) and f[1] == UNSPEC and isinstance(f[2], list) and len(f[2]) > 1 and f[2][1] == UNSPEC
      and not parent_not):
    v = _fresh(used, "A")
    return ["exists", v, ["can", v, [f[2][0], v] + copy.deepcopy(f[2][2:])]], 1
  out, n = [], 0
  for x in f:
    y, k = _agentless(x, used, f[0] == "not")
    out.append(y)
    n += k
  return out, n


def _bind(box, tpath, names):
  """Bind names by forall at the scope of the head whose term is at tpath in box[0]: below the formula's leading
  quantifiers and the conjunctions that lead to the head, above the implication or the head itself."""
  f, path = box[0], ()
  while len(path) < len(tpath):
    node, nxt = _at(f, path), tpath[len(path)]
    if (node[:1] in (["forall"], ["exists"]) and len(node) == 3 and nxt == 2) or node[:1] == ["and"]:
      path += (nxt,)
      continue
    break
  target = _at(f, path)
  for v in reversed(names):
    target = ["forall", v, target]
  if path:
    _at(f, path[:-1])[path[-1]] = target
  else:
    box[0] = target


def _travel_law(u):
  acts = _capability_actions(u)
  return (u.get("type") != "query" and len(acts) == 1 and _travel(acts[0])
          and u.get("action_reading") in ("availability", "restriction", None))


def _path_binders(f, path):
  """The variables that forall, exists or ask bind on the way from the root of f to the node at path."""
  out, node = set(), f
  for i in path:
    if isinstance(node, list) and node[:1] in (["forall"], ["exists"], ["ask"]) and len(node) == 3 \
        and isinstance(node[1], str):
      out.add(node[1])
    node = node[i]
  return out


def _endpoints(holder, i):
  """K7 and K6 on the formula holder[i] of a travel law, in place.  Returns the repairs applied.  The terms are found
  again after each binding, since a new binder changes the paths below it.  A variable counts as bound only when a
  binder on the head's own path binds it."""
  applied = []
  box = [holder[i]]
  used = _strings(box[0], set())
  changed = True
  while changed:
    changed = False
    for tpath, _ in _law_terms(box[0]):
      term = _at(box[0], tpath)
      if not isinstance(term, list):
        continue
      if term[:1] == ["take"] and len(term) == 3 and term[2] in la.STANDARD_MODES:
        term[:] = ["move", term[1], UNSPEC, UNSPEC, term[2]]
        applied.append("K7")
      if not (term[:1] == ["move"] and len(term) == 5):
        continue
      names = []
      bound = _path_binders(box[0], tpath)
      for slot, base in ((2, "F"), (3, "T")):
        x = term[slot]
        if x == UNSPEC:
          term[slot] = _fresh(used, base)
          names.append(term[slot])
        elif la.is_var(x) and x not in bound and x not in names:
          where = _occurrences(box[0], x, [])
          if all(p[:-1] == tpath and p[-1] in (2, 3) for p in where):
            names.append(x)
      if names:
        _bind(box, tpath, names)
        applied.append("K6")
        changed = True
        break
  holder[i] = box[0]
  return applied


# ---------------------------------------------------------------------------
# K5


def _key(action):
  roles = action.get("roles") or {}
  return (action.get("root"), roles.get("actor"), roles.get("target"))


def _permissions(units, packages):
  """{Stage-1 key: [(term, unit)]}: the positive can terms of the availability units with one capability action."""
  byid = {u["unit_id"]: u for u in units}
  out = {}
  for p in packages:
    u = byid.get(p[1])
    if not u or u.get("type") == "query" or u.get("action_reading") != "availability":
      continue
    acts = _capability_actions(u)
    if len(acts) != 1:
      continue
    for tpath, negated in _law_terms(p[2]):
      term = _at(p[2], tpath)
      if not negated and isinstance(term, list) and _at(p[2], tpath[:-1])[:1] == ["can"]:
        out.setdefault(_key(acts[0]), []).append((term, p[1]))
  return out


def _filled(term, action, perms):
  """(the permission's term, its units) when the mention leaves only the tool unstated; else None.  A mention whose
  Stage-1 action names a tool (instrument or location) other than the permission's tool is kept as written."""
  roles = action.get("roles") or {}
  stated = [roles[k] for k in ("instrument", "location") if roles.get(k)]
  cands = perms.get(_key(action)) or []
  terms = []
  for t, _ in cands:
    if t not in terms:
      terms.append(t)
  if len(terms) != 1 or not (isinstance(term, list) and term[:1] == ["change"] and len(term) == 5):
    return None
  c = terms[0]
  if c[:1] != ["change"] or len(c) != 5 or term[4] != UNSPEC or c[4] == UNSPEC or term[1:4] != c[1:4]:
    return None
  if any(x != c[4] for x in stated):
    return None
  return copy.deepcopy(c), sorted({uid for t, uid in cands})


def _fill_tools(units, packages):
  records = []
  perms = _permissions(units, packages)
  if not perms:
    return records
  byid = {u["unit_id"]: u for u in units}
  for p in packages:
    u = byid.get(p[1])
    if not u:
      continue
    acts = [a for a in u.get("actions") or [] if isinstance(a, dict)]
    f = p[2]
    sites = []                                 # (container, index, Stage-1 action)
    if u.get("type") == "query":
      if isinstance(f, list) and f[:1] == ["verify"] and len(f) == 3 and isinstance(f[1], list) \
          and len(f[1]) == len(acts):
        sites = [(f[1], k, a) for k, a in enumerate(acts)]
      elif len(acts) == 1:
        sites = [(n, 1, acts[0]) for _, n in _paths(f, lambda n: n[:1] == ["executable"] and len(n) == 2)]
    elif u.get("action_reading") == "effect" and len(acts) == 1:
      sites = [(n, 1, acts[0]) for _, n in _paths(f, lambda n: n[:1] == ["after"] and len(n) == 3)]
    for container, k, action in sites:
      got = _filled(container[k], action, perms)
      if got is None:
        continue
      before = _dump(container[k])
      container[k] = got[0]
      records.append(_record("tool_filled", "K5", p[1], before, _dump(got[0]), got[1]))
  return records


def action_clause(u, action):
  """The part of a unit's text that names its action: the first clause (between commas or semicolons) that holds a
  form of the Stage-1 verb root ("after Nia 1 cooks egg 2 with pan 3" in "If egg 2 is raw, after Nia 1 cooks ...");
  the whole text when no clause holds one."""
  text = u.get("text") or ""
  root = (action.get("root") or "").lower()
  if not root:
    return text
  forms = {root, linguistics.third_person(root), root + "ing", root[:-1] + "ing"} | aen.participles(root)
  for clause in re.split(r"[,;]", text):
    if any(re.search(r"\b%s\b" % re.escape(f), clause.lower()) for f in forms):
      return clause
  return text


def value_mismatches(units, packages, asked=()):
  """K13: a mention of an action (an effect, a supplied step, an executable question) whose term has the verb, actor
  and object of exactly one permission term, another value, and a value that the mention's own clause does not state.
  One message per unit, naming the permission's unit and term; a unit in `asked` got the message before and is not
  asked again, so a translation that keeps a value after the message stands.  Returns [(unit, message)]."""
  perms = _permissions(units, packages)
  byid = {u["unit_id"]: u for u in units}
  out = []
  for p in packages:
    u = byid.get(p[1])
    if not u or p[1] in asked:
      continue
    acts = [a for a in u.get("actions") or [] if isinstance(a, dict)]
    f = p[2]
    sites = []
    if u.get("type") == "query":
      if isinstance(f, list) and f[:1] == ["verify"] and len(f) == 3 and isinstance(f[1], list) \
          and len(f[1]) == len(acts):
        sites = list(zip(f[1], acts))
      elif len(acts) == 1:
        sites = [(n[1], acts[0]) for _, n in _paths(f, lambda n: n[:1] == ["executable"] and len(n) == 2)]
    elif u.get("action_reading") == "effect" and len(acts) == 1:
      sites = [(n[1], acts[0]) for _, n in _paths(f, lambda n: n[:1] == ["after"] and len(n) == 3)]
    for term, action in sites:
      clause = action_clause(u, action).lower()
      cands = perms.get(_key(action)) or []
      terms = []
      for t, _ in cands:
        if t not in terms:
          terms.append(t)
      if len(terms) != 1 or not (isinstance(term, list) and term[:1] == ["change"] and len(term) == 5):
        continue
      c = terms[0]
      if (c[:1] != ["change"] or len(c) != 5 or term[1:3] != c[1:3] or term[3] in (c[3], UNSPEC)
          or c[3] == UNSPEC or term[4] not in (c[4], UNSPEC)):
        continue
      if re.search(r"\b%s\b" % re.escape(str(term[3]).replace("_", " ").lower()), clause):
        continue
      out.append((p[1], "unit %s: this sentence names the action of the permission in unit %s, %s, with another value "
                        "(%s): one action has one term in every sentence; write the permission's term, unless this "
                        "sentence states another result of the action itself"
                        % (p[1], ", ".join(sorted({uid for _, uid in cands})), _dump(c), term[3])))
      break
  return out


def _change_terms(f, out):
  if isinstance(f, list):
    if f[:1] == ["change"] and len(f) == 5:
      out.append(f)
    else:
      for x in f:
        _change_terms(x, out)
  return out


NEGATED = re.compile(r"\b(?:not|no longer|never|no)\s+(?:\w+\s+)?$")


def _states(text, value):
  """Whether a text states the value positively: the word occurs, and not right after not, no longer or never."""
  if not isinstance(value, str):
    return False
  low = (text or "").lower()
  for m in re.finditer(r"\b%s\b" % re.escape(value.replace("_", " ").lower()), low):
    if not NEGATED.search(low[max(0, m.start() - 20):m.start()]):
      return True
  return False


def _positive_properties(f, out, negated=False):
  """The ["has property", V, O] atoms of a formula that stand under no negation."""
  if isinstance(f, list) and f:
    if f[0] == "not":
      for x in f[1:]:
        _positive_properties(x, out, not negated)
    elif f[0] == "has property" and len(f) == 3:
      if not negated:
        out.append(f)
    else:
      for x in f[1:]:
        _positive_properties(x, out, negated)
  return out


def _root_of(u, term):
  """The Stage-1 verb root of a unit's action that the change term translates: the action whose target is the
  term's object, else the unit's only action."""
  acts = [a for a in u.get("actions") or [] if isinstance(a, dict)]
  hit = [a for a in acts if (a.get("roles") or {}).get("target") == term[2]]
  if len(hit) == 1:
    return hit[0].get("root")
  return acts[0].get("root") if len(acts) == 1 else None


def _effects_of(packages):
  """[(unit, condition or None, action term, head)] of the after-laws of the packages."""
  out = []

  def walk(f, uid, cond):
    if not isinstance(f, list) or not f:
      return
    if f[0] == "forall" and len(f) == 3:
      walk(f[2], uid, cond)
    elif f[0] == "and":
      for x in f[1:]:
        walk(x, uid, cond)
    elif f[0] == "implies" and len(f) == 3:
      walk(f[2], uid, f[1])
    elif f[0] == "after" and len(f) == 3:
      out.append((uid, cond, f[1], f[2]))
    elif f[0] == "holds" and len(f) == 3:
      walk(f[2], uid, cond)
  for p in packages:
    if isinstance(p, list) and len(p) == 3:
      walk(p[2], p[1], None)
  return out


def _permission_conditions(packages, term):
  """The antecedent conjuncts of each permission whose can head has the term's constructor, actor and object; None
  for a permission without a condition."""
  out = []

  def walk(f, cond):
    if not isinstance(f, list) or not f:
      return
    if f[0] in ("forall", "holds") and len(f) == 3:
      walk(f[2], cond)
    elif f[0] == "and":
      for x in f[1:]:
        walk(x, cond)
    elif f[0] == "implies" and len(f) == 3:
      walk(f[2], f[1])
    elif f[0] == "normally" and len(f) == 2:
      walk(f[1], cond)
    elif f[0] == "can" and len(f) == 3 and isinstance(f[2], list) and f[2][:3] == term[:3]:
      out.append(None if cond is None else la.conjuncts(cond))
  for p in packages:
    if isinstance(p, list) and len(p) == 3:
      walk(p[2], None)
  return out


def _stated_result(units, packages, uid, term):
  """Whether the text states the value of a change term as a positive result of that operation on that object: the
  unit's own sentence, when its Stage-1 action of that object has the value as its result and the text
  states it positively; or an effect of the same verb root, actor and object whose head makes the value true of the
  object and whose sentence states it positively.  A conditional effect counts only when every permission of the
  action has each of its conditions."""
  byid = {u["unit_id"]: u for u in units}
  u = byid.get(uid)
  value, obj = term[3], term[2]
  if u is not None:
    for a in u.get("actions") or []:
      roles = (a.get("roles") or {}) if isinstance(a, dict) else {}
      if roles.get("target") == obj and roles.get("result") == value and _states(u.get("text"), value):
        return True
  root = _root_of(u, term) if u is not None else None
  for eid, cond, action, head in _effects_of(packages):
    e = byid.get(eid)
    if e is None or e.get("action_reading") != "effect" or root is None or _root_of(e, action) != root:
      continue
    if not (isinstance(action, list) and action[:1] == ["change"] and len(action) == 5
            and action[1] == term[1] and action[2] == obj):
      continue
    if ["has property", value, obj] not in _positive_properties(head, []) or not _states(e.get("text"), value):
      continue
    if cond is not None:
      needed = la.conjuncts(cond)
      perms = _permission_conditions(packages, term)
      if not perms or any(c is None or any(x not in c for x in needed) for c in perms):
        continue
    return True
  return False


def unstated_values(units, before, after):
  """K15: the values that a clarification reply changes and that the text does not state
  as a positive result of that operation on that object (`_stated_result`).  A change term of the reply whose value
  differs from the term at the same place of the earlier response, or that is new, is checked.  Returns
  [(unit, value)]; a relabelled real collision is refused."""
  byid = {u["unit_id"]: u for u in units}
  old = {p[1]: _change_terms(p[2], []) for p in before if isinstance(p, list) and len(p) == 3}
  out = []
  for p in after:
    if not (isinstance(p, list) and len(p) == 3) or p[1] not in byid:
      continue
    earlier = old.get(p[1], [])
    for i, t in enumerate(_change_terms(p[2], [])):
      if i < len(earlier) and earlier[i][3] == t[3]:
        continue
      if la.is_var(t[3]) or t[3] == UNSPEC:
        continue
      if not _stated_result(units, after, p[1], t):
        out.append((p[1], t[3]))
  return out


def _masked(f):
  """A formula with the value of every change term replaced by *: two translations that differ only in result
  labels are equal masked."""
  if isinstance(f, list):
    if f[:1] == ["change"] and len(f) == 5:
      return [f[0], _masked(f[1]), _masked(f[2]), "*", _masked(f[4])]
    return [_masked(x) for x in f]
  return f


def _law_signature(pkg):
  """The parts of a law package that a rearrangement keeps: its world, its probability, its quantified variables, the
  multiset of its conditions (antecedent conjuncts and the conjuncts beside a can head) and of its heads."""
  body = pkg[2]
  prob = None
  if isinstance(body, list) and body[:1] == ["and"] and len(body) == 3 and isinstance(body[2], list) \
      and body[2][:1] == ["@p"]:
    prob, body = body[2], body[1]
  if not (isinstance(body, list) and body[:1] == ["holds"] and len(body) == 3):
    return None
  quants, conds, heads = [], [], []

  def split(parts):
    if any(la.contains(x, {"can"}) for x in parts):
      for x in parts:
        (heads if la.contains(x, {"can"}) else conds).append(x)
    else:
      heads.append(["and"] + parts if len(parts) > 1 else parts[0])

  def walk(f):
    if isinstance(f, list) and f[:1] in (["forall"], ["exists"]) and len(f) == 3:
      quants.append([f[0], f[1]])
      walk(f[2])
    elif isinstance(f, list) and f[:1] == ["implies"] and len(f) == 3:
      conds.extend(la.conjuncts(f[1]))
      split(la.conjuncts(f[2]))
    elif isinstance(f, list) and f[:1] == ["and"]:
      split(la.conjuncts(f))
    else:
      heads.append(f)
  walk(_masked(body[2]))
  key = lambda xs: sorted(json.dumps(x, sort_keys=True) for x in xs)
  return [prob, body[1], key(quants), key(conds), key(heads)]


def types_key(types):
  """The type records of a translation in a form that compares equal when the records are equal in any order."""
  return {uid: sorted(json.dumps(a, sort_keys=True) for a in atoms) for uid, atoms in (types or {}).items()}


def clarification_refusals(before, after, named, law_units):
  """K15: the changes of a clarification reply beyond the permitted ones, as reasons.  Permitted: a
  change term's value (a result label; `unstated_values` checks the value) in a unit that the unsupported diagnosis
  names or in the query, and, in a unit with unsupported_law_form, the rearrangement that moves conditions beside a
  can head into the antecedent (`_law_signature` unchanged).  Everything else stays: the units, the worlds, contexts,
  query selections and types, and every other formula, condition, effect, quantifier, probability and the goal.
  `before` and `after` are Stage-2 attempts ({"packages", "worlds", "contexts", "selections", "types"})."""
  out = []
  for field in ("worlds", "contexts", "selections"):
    if (before.get(field) or None) != (after.get(field) or None):
      out.append("the reply changes the %s" % field)
  if types_key(before.get("types")) != types_key(after.get("types")):
    out.append("the reply changes the types")
  old = {p[1]: p for p in before.get("packages") or []}
  new = {p[1]: p for p in after.get("packages") or []}
  if list(old) != list(new):
    out.append("the reply adds, removes or reorders units")
    return out
  queries = {p[1] for p in after["packages"] if isinstance(p[2], list) and p[2]
             and p[2][0] in ("plan", "reachable", "verify", "question", "ask")}
  for uid, p in new.items():
    q = old[uid]
    if p == q:
      continue
    if _masked(p) == _masked(q):
      if uid not in named and uid not in queries:
        out.append("unit %s: a result label changed in a unit that the diagnosis does not name" % uid)
      continue
    if uid in law_units and _law_signature(p) is not None and _law_signature(p) == _law_signature(q):
      continue
    out.append("unit %s: the reply changes more than a result label or the arrangement of a law" % uid)
  return out


# ---------------------------------------------------------------------------
# the entry


START_MARKER = re.compile(r"\b(?:initially|at the start|now)\b", re.I)
SCOPE_OPS = {"can", "after", "executable", "state_law", "@time", "normally"}


def _standing(u, p):
  """K16: the formula of a dependency between states that Stage 1 types as a strict
  rule becomes a standing rule, holds(W0, state_law(F)), by the state-rule convention: Stage 1 decides the scope, as
  it decides the derived fields.  The condition on the unit: type strict_rule, no action reading, no actions, no
  time or state_tense other than present, no snapshot (pre_state other than W0, next_state), no context (a knower or
  a location), no marker of a description of the start in the text.  A normal_rule is left alone, with or without
  normally: a default is not a strict standing law.  The condition on the package: no stated probability,
  ["holds", "W0", F] with F an implication under forall at most, no action operator and no normally, and a changing
  state (a fluent) in its condition and in its consequent.  Returns True when it wrapped F."""
  if (u.get("type") != "strict_rule" or u.get("action_reading") or u.get("actions") or u.get("context")
      or any(u.get(k) not in (None, "present") for k in ("time", "state_tense"))
      or u.get("pre_state") not in (None, "W0") or u.get("next_state") is not None
      or START_MARKER.search(u.get("text") or "")):
    return False
  body = p[2]
  if not (isinstance(body, list) and body[:1] == ["holds"] and len(body) == 3 and body[1] == "W0"):
    return False
  f = body[2]
  core = f
  while isinstance(core, list) and core[:1] == ["forall"] and len(core) == 3:
    core = core[2]
  if not (isinstance(core, list) and core[:1] == ["implies"] and len(core) == 3) or la.contains(f, SCOPE_OPS):
    return False
  if not la.contains(core[2], set(la.FLUENTS)) or not la.contains(core[1], set(la.FLUENTS)):
    # a dependency between states has a changing state among its conditions too; a universal with a class guard only
    # ("Nothing is on top of any block") is a description of the scene
    return False
  body[2] = ["state_law", f]
  return True


def repair_packages(units, packages):
  """K16, K8, K7 and K6, then K5, on the packages of one Stage-2 response, in place.  Returns the records."""
  byid = {u["unit_id"]: u for u in units}
  records = []
  for p in packages:
    u = byid.get(p[1])
    if not u or u.get("type") == "query":
      continue
    holder = _body(p)
    if holder is None:
      continue
    h, i = holder
    before = _dump(p)
    if _standing(u, p):
      records.append(_record("standing_rule_from_stage1", "K16", p[1], before, _dump(p), [p[1]]))
      continue
    h[i], n = _agentless(h[i], _strings(h[i], set()))
    if n:
      records.append(_record("agentless_permission", "K8", p[1], before, _dump(p), [p[1]]))
    if _travel_law(u):
      before = _dump(p)
      applied = _endpoints(h, i)
      for repair in sorted(set(applied), reverse=True):
        kind = "travel_take_as_move" if repair == "K7" else "travel_endpoints_bound"
        records.append(_record(kind, repair, p[1], before, _dump(p), [p[1]]))
  records.extend(_fill_tools(units, packages))
  return records


# ---------------------------------------------------------------------------
# the readings that the compiler adjusts (K1, K2, K11)
#
# `action_route` checks that a unit's Stage-1 action reading fits its Stage-2 form.  When it does not, the unit's own
# sentence may establish the reading: these functions read the sentence and the formula.


def public_route_under_availability(unit):
  """A unit labelled availability whose Stage-1 action names no actor and whose formula is one or more positive
  connected facts (with class atoms at most), each agreeing with the Stage-1 source, destination and means."""
  s1 = unit.get("stage1") or {}
  if s1.get("action_reading") != "availability" or unit.get("form") != "description_static":
    return False
  actions = s1.get("actions") or []
  if not actions or any(not isinstance(a, dict) or "actor" in (a.get("roles") or {}) for a in actions):
    return False
  pkg = unit.get("stage2")
  body = pkg[2] if isinstance(pkg, list) and len(pkg) == 3 else None
  f = body[2] if isinstance(body, list) and len(body) == 3 and body[0] == "holds" else None
  atoms = f[1:] if isinstance(f, list) and f[:1] == ["and"] else [f]
  routes = [a for a in atoms if isinstance(a, list) and a[:1] == ["connected"] and len(a) == 4]
  if not routes or any(not (isinstance(a, list) and a[:1] in (["connected"], ["isa"])) for a in atoms):
    return False
  for a in actions:
    roles = a.get("roles") or {}
    for r in routes:
      if any(roles.get(k) not in (None, v) for k, v in (("source", r[1]), ("destination", r[2]), ("instrument", r[3]))):
        return False
  return True


# the words of a unit's sentence that decide an adjusted reading
DENIAL_WORDS = re.compile(r"\b(?:cannot|can not|can't|may not|must not)\b|\bno(?: \w+){1,3} can\b", re.I)
NECESSARY_WORDS = re.compile(r"\b(?:unless|only|except|requires?|required|must)\b", re.I)
EFFECT_WORDS = re.compile(r"\b(?:after|once|when|then|becomes?|became|makes?|made)\b", re.I)
PERMISSION_WORDS = re.compile(r"\b(?:can|may|able|allowed)\b", re.I)
CONDITION_WORDS = re.compile(r"\b(?:if|when|whenever|while|as long as)\b(.*)$", re.I)
NEGATION_WORDS = re.compile(r"\b(?:not|no|never|without)\b|n't\b", re.I)
ACTION_HEADS = ("move", "take", "put_on", "put_in", "change", "after", "can", "executable")
_STOP = set("a an the who which that whose is are was were be been being not no never without any every all each of "
            "to in on at by with for from it its they them their he she his her has have had does do did if when "
            "whenever while as long someone anyone somebody anybody nobody one ones".split())
_IRREGULAR = {"people": "person", "persons": "person", "children": "child", "men": "man", "women": "woman"}


def _lemma(w):
  w = w.lower()
  if w in _IRREGULAR:
    return _IRREGULAR[w]
  if len(w) > 4 and w.endswith("ies"):
    return w[:-3] + "y"
  if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
    return w[:-1]
  return w


def _words(f, out):
  """The lemmas of the words of every string in a formula."""
  if isinstance(f, list):
    for x in f:
      _words(x, out)
  elif isinstance(f, str):
    out.update(_lemma(w) for w in re.findall(r"[A-Za-z]+", f))
  return out


def _count(f, name):
  return (f[:1] == [name]) + sum(_count(x, name) for x in f) if isinstance(f, list) else 0


def _has_head(f, names):
  return isinstance(f, list) and bool(f) and ((isinstance(f[0], str) and f[0] in names) or any(_has_head(x, names) for x in f))


def _plain_denial(unit):
  """The unit's sentence is a plain denial ("cannot", "no X can") without a necessary condition, and the Stage-2
  formula keeps every condition the sentence states: each content word of the subject phrase and of an if- or
  when-clause occurs in the formula, and a negated condition keeps a negation beside the denied head."""
  text = unit.get("text") or ""
  m = DENIAL_WORDS.search(text)
  if m is None or NECESSARY_WORDS.search(text):
    return False
  subject = text[:m.start()]
  if m.group(0).lower().startswith("no "):
    subject = m.group(0)[3:-4]
  clause = CONDITION_WORDS.search(text[m.end():])
  conditions = subject + " " + (clause.group(1) if clause else "")
  formula = (unit.get("stage2") or [None, None, None])[2]
  have = _words(formula, set())
  needed = {_lemma(w) for w in re.findall(r"[A-Za-z]+", conditions) if w.lower() not in _STOP and len(w) > 1}
  if needed - have:
    return False
  return not NEGATION_WORDS.search(conditions) or _count(formula, "not") >= 2


def _state_rule_under_effect(unit):
  """K2: a rule between two states that Stage 1 labelled effect: no effect marker in the sentence, no actor in the
  Stage-1 actions and no action term in the Stage-2 formula."""
  s1 = unit["stage1"]
  return (unit["form"] in ("description_initial", "description_static", "state_law")
          and not EFFECT_WORDS.search(unit.get("text") or "")
          and not any("actor" in (a.get("roles") or {}) for a in s1.get("actions") or [] if isinstance(a, dict))
          and not _has_head(unit.get("stage2"), ACTION_HEADS))


def adjusted_reading(unit):
  """(repair, reading) when the unit's sentence establishes another reading than Stage 1 gives, else None.

    K1   a plain denial under the reading restriction: the denial's reading availability
    K2   a rule between two states under the reading effect: no reading
    K11  no reading, a Stage-1 action of mode capability, and a law form the sentence establishes: availability for a
         permission or a plain denial, restriction for a sentence with a necessary condition
  """
  s1 = unit["stage1"]
  reading, form = s1.get("action_reading"), unit["form"]
  if reading == "restriction" and form == "denial" and _plain_denial(unit):
    return "K1", "availability"
  if reading == "effect" and _state_rule_under_effect(unit):
    return "K2", None
  capability = any(isinstance(a, dict) and a.get("mode") == "capability" for a in s1.get("actions") or [])
  if reading is None and capability:
    text = unit.get("text") or ""
    if form == "availability" and PERMISSION_WORDS.search(text) and not DENIAL_WORDS.search(text) \
        and not NECESSARY_WORDS.search(text):
      return "K11", "availability"
    if form == "denial" and _plain_denial(unit):
      return "K11", "availability"
    if form == "restriction" and NECESSARY_WORDS.search(text):
      return "K11", "restriction"
  return None
