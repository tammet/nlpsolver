"""Action profile: executability paths of source rules, denials, identity, granularity.

The pass `availability_routes_identity` of the action compiler (encoding v2,
A2.3 and A2.4 with their Revision-4 notes).  It compiles

  availability   a source rule `... -> can(A, ACTION)`: one executability
                 path per applicability template of the action's constructor,
                 each holding every source condition, the template's physical
                 preconditions and the constructor's restriction hook, and
                 concluding poss(ACTION); strict or default as written
  denial         an explicit not can(A, ACTION): the marker
                 execution_denied(ACTION); the library gives -poss from it and
                 its defaults are blocked by it
  identity       differ facts, both orders, for the concrete entity ids the
                 source formulas use; never for a witness or a lexical value
  granularity    one actor at two places outside a declared flat set, or a
                 place located in a place, is unsupported_location_granularity:
                 for the unqualified facts of a world at the source level, for
                 facts a query selection can leave out per query

Templates (library file axioms_action.templates.json).  put_on has two paths
(onto a block, onto a surface); move takes tpl_move_stated when the unit
identifies the origin, the destination and the means (constants, or
variables that a supported positive condition dominating the head binds) and
its actor is not an unconditioned universal, else tpl_move_public, which
reads connected(F, T, M); take, put_in and change have one template.  The
stated-endpoint path concludes poss for the head's actor only and creates no
connected fact and no static fact.

Alternative sufficient rules stay alternatives.  An effect or a necessary
condition never becomes a path here.  A default path is blocked by the
denial marker of its action, as the library defaults are.

Evidence.  An uncertain unit (@p) has the evidence e = 2p - 1 on every path
it compiles to.  There is no helper clause: the paths of one unit are
alternatives for one application.  The counting rule (Sol's) counts an
uncertain rule once per action application.  GK counts the evidence once per
use in a proof, and one application reads `poss` several times (C29.Q2), so
a query that can apply an uncertain path declares shared_source_confidence
(`lc_action_query`).

Nothing here calls a prover.
"""

import copy

import lc_action as la
import lc_action_library as lib
import lc_action_situate as sit

PASS = "availability_routes_identity"
FORMS = ("availability", "denial")
MARKER = lib.MARKER          # the marker of an explicit denial; nothing else derives it
PUBLIC, STATED = "tpl_move_public", "tpl_move_stated"


def _map_heads(f, fn, bound=frozenset(), scope=()):
  """Rebuild a law formula with every can head replaced by fn(head, bound, scope).

  A head is can(...) or not(can(...)), possibly under normally.  `bound` and
  `scope` are branch-local: `scope` lists the universal binders on the path
  to this head, and `bound` holds the variables that a positive atom of an
  antecedent dominating this head binds.  A binder that reuses a name starts
  a new variable, so it leaves `bound`.  fn returns a replacement or None to
  drop the head.
  """
  op = f[0]
  if op == "forall":
    body = _map_heads(f[2], fn, bound - {f[1]}, tuple(v for v in scope if v != f[1]) + (f[1],))
    return None if body is None else [op, f[1], body]
  if op == "implies":
    body = _map_heads(f[2], fn, bound | _positive_variables(f[1], set()), scope)
    return None if body is None else [op, f[1], body]
  if op == "and":
    parts = [x for x in (_map_heads(x, fn, bound, scope) for x in f[1:]) if x is not None]
    return None if not parts else parts[0] if len(parts) == 1 else ["and"] + parts
  return fn(f, bound, scope)


def _can_of(head):
  """The can atom of a head subformula, and whether the head is default or denied."""
  default = negated = False
  while head[0] in ("normally", "not"):
    default = default or head[0] == "normally"
    negated = negated or head[0] == "not"
    head = head[1]
  return head, default, negated


def _positive_variables(f, out, positive=True):
  """Variables that a positive fluent or static atom of one antecedent binds."""
  op = f[0]
  if op == "exists":
    _positive_variables(f[2], out, positive)
  elif op == "not":
    _positive_variables(f[1], out, not positive)
  elif op in ("and", "or"):
    for x in f[1:]:
      _positive_variables(x, out, positive)
  elif positive and (op in la.FLUENTS or op in la.STATIC):
    out.update(t for t in f[1:] if la.is_var(t))
  return out


def stated_endpoints(can, bound):
  """Whether a movement head qualifies for the stated-endpoint path (migration plan section 4).

  The origin, the destination and the means are each a constant, or a source
  variable that a positive condition dominating this head binds; the actor
  is a constant or such a bound variable (an unconditioned universal actor,
  "anyone can go ...", takes the public path).  Fresh universal endpoints do
  not qualify, also when another branch of the unit binds a variable of that
  name.
  """
  act = can[2]
  if act[0] != "move":
    return False
  return all(not la.is_var(t) or t in bound for t in act[1:5])


def template_names(can, bound):
  """The templates of one can head, in file order."""
  k = can[2][0]
  if k == "move":
    return [STATED if stated_endpoints(can, bound) else PUBLIC]
  return {"take": ["tpl_take"], "put_on": ["tpl_put_on_block", "tpl_put_on_surface"],
          "put_in": ["tpl_put_in"], "change": ["tpl_change"]}[k]


def _vars(f, out):
  if isinstance(f, list):
    for x in f:
      _vars(x, out)
  elif la.is_var(f):
    out.add(f)
  return out


def _fresh_names(used):
  """Source-variable names Z1, Z2, ... that the unit does not use."""
  n = 0
  while True:
    n += 1
    v = "Z%d" % n
    if v not in used:
      used.add(v)
      yield v


def instantiate(template, act, default, names):
  """The path formula of one template for one action term: forall fresh (preconditions & hook -> poss(act)).

  The template's action variables take the head's terms; a template variable
  outside the action (the support of take) becomes a fresh universal.  The
  $source literal is dropped: the unit's own conditions stand around the head.
  """
  lits = lib.literals(template["clause"])
  poss = [x for x in lits if lib.positive(x)][0]
  subst = dict(zip(poss[1][1:], act[1:]))
  fresh = []

  def term(t):
    if isinstance(t, str) and t.startswith("?:"):
      if t not in subst:
        subst[t] = next(names)
        fresh.append(subst[t])
      return subst[t]
    return t

  body = []
  for x in lits:
    p = lib.predicate(x)
    if p in (lib.SOURCE, "poss"):
      continue
    args = x[1:-1] if sit.bears_situation(p) else x[1:]    # the situation pass adds the context and its situation
    body.append([p] + [term(t) if not isinstance(t, list) else [t[0]] + [term(y) for y in t[1:]] for t in args])
  head = ["poss", list(act)]
  if default:
    head = ["normally", head]
  f = ["implies", body[0] if len(body) == 1 else ["and"] + body, head]
  for v in reversed(fresh):
    f = ["forall", v, f]
  return f


def evidence(p):
  """The pipeline convention: Stage-2 probability p to evidence 2p - 1 (lc_packages)."""
  return round(2.0 * p - 1.0, 4)


def _role(lits):
  heads = [x[0] for x in lits if not x[0].startswith("-") and x[0] != "$block"]
  return "availability" if "poss" in heads else "denial"


def _denial(head, bound=None, scope=None):
  """A denial head as the library reads it: the marker execution_denied(ACTION); normally is kept."""
  can, default, negated = _can_of(head)
  if not negated:
    return None
  atom = [MARKER, can[2]]
  return ["normally", atom] if default else atom


def _marker_blocker(clause, priority):
  """A default path is blocked by the denial marker of its action, as a library default is.

  The blocker priority is the one the rule's own conditions give (the
  template's physical preconditions do not make a rule more specific).
  """
  out = []
  for x in clause:
    if x[0] == "$block" and isinstance(x[2], list) and x[2][0] == "$not" and x[2][1][0] == "poss":
      x = ["$block", priority if priority is not None else x[1], [MARKER] + x[2][1][1:]]
    out.append(x)
  return out


def _priorities(unit_id, formula, applies, namer):
  """The blocker priority of each clause of the bare rule (poss head, no template), in clause order."""
  def bare(head, bound, scope):
    can, default, negated = _can_of(head)
    if negated or not applies(can, bound):
      return None
    return ["normally", ["poss", can[2]]] if default else ["poss", can[2]]
  f = _map_heads(copy.deepcopy(formula), bare)
  if f is None:
    return []
  situated, clauses, witnesses = sit.clausify_law(unit_id, f, namer(unit_id))
  return [([x[1] for x in c["clause"] if x[0] == "$block"] or [None])[0] for c in clauses]


def compile_unit(unit, namer, library):
  """Clauses of one structurally supported availability or denial unit.

  Returns {"situated", "situation", "clauses", "witnesses", "diagnostic", "requirements", "note", "paths"};
  `paths` lists (head constructor, template name) per compiled path.
  """
  out = {"situated": None, "situation": "shared_current", "clauses": None, "witnesses": [],
         "diagnostic": None, "requirements": [], "note": None, "paths": []}
  formula = sit._unit_formula(unit)
  p = unit.get("confidence")
  if p is not None and p <= 0.5:
    out["clauses"] = []
    out["diagnostic"] = ("unsupported_confidence_form",
                         "an availability or a denial with probability %s: a probably-false or uninformative action law "
                         "has no reviewed compilation; the unit is kept and not read as its negation" % p, None)
    return out
  e = evidence(p) if p is not None and p < 1 else None
  heads = []
  _map_heads(copy.deepcopy(formula), lambda head, bound, scope: heads.append((head, scope)) or head)
  if e is not None and len(heads) > 1:
    out["clauses"] = []
    out["diagnostic"] = ("unsupported_confidence_form",
                         "one uncertain unit with %d can heads: how one source probability divides over several claims "
                         "is not defined here; the unit is kept" % len(heads), None)
    return out
  names = _fresh_names(_vars(formula, set()))
  formulas = []               # (template name or None, formula, blocker priorities)
  try:
    if unit["form"] == "denial":
      formulas.append((None, _map_heads(copy.deepcopy(formula), _denial), []))
    else:
      for tname in lib.TEMPLATE_NAMES:
        tpl = lib.template(library, tname)
        applies = lambda can, bound, tname=tname: tname in template_names(can, bound)

        def path(head, bound, scope, tpl=tpl, applies=applies):
          can, default, negated = _can_of(head)
          if negated or not applies(can, bound):
            return None
          return instantiate(tpl, can[2], default, names)
        f = _map_heads(copy.deepcopy(formula), path)
        if f is not None:
          formulas.append((tname, f, _priorities(unit["id"], formula, applies, namer)))
  except sit.Unsupported as ex:
    out["situated"] = getattr(ex, "situated", None)
    out["clauses"] = []
    out["diagnostic"] = (ex.reason, str(ex), None)
    return out
  records, views = [], []
  try:
    for tname, f, priorities in formulas:
      situated, clauses, witnesses = sit.clausify_law(unit["id"], f, namer(unit["id"]))
      views.append(situated)
      out["witnesses"].extend(witnesses)
      for n, c in enumerate(clauses):
        prio = priorities[n] if n < len(priorities) else None
        rec = {"role": _role(c["clause"]), "unit": unit["id"], "clause": _marker_blocker(c["clause"], prio), "pass": PASS,
               "provenance": unit["id"], "defeasible": c["defeasible"], "strict": not c["defeasible"]}
        if tname:
          rec["template"] = tname
        if p is not None:
          rec["source_probability"] = p
        if e is not None:
          rec["confidence"] = e
        if rec not in records:
          records.append(rec)
      if tname:
        out["paths"].append(tname)
  except sit.Unsupported as ex:
    out["situated"] = getattr(ex, "situated", None)
    out["clauses"] = []
    out["diagnostic"] = (ex.reason, str(ex), None)
    return out
  # one situation binder over all generated formulas of the unit
  out["situated"] = views[0] if len(views) == 1 else ["forall", sit.SIT, ["and"] + [v[2] for v in views]]
  out["clauses"] = records
  return out


# ---------------------------------------------------------------------------
# identity


def _concrete_ids(f, out):
  if isinstance(f, list):
    for x in f:
      _concrete_ids(x, out)
  elif la.is_concrete(f):
    out.append(f)
  return out


def differ_clauses(artifact_units, identity):
  """differ(X, Y), both orders, for the declared concrete ids the source formulas use.

  The restricted unique-name policy: two ids of the identity map are two
  entities, because aliases were normalized to one id before.  A witness, a
  lexical value and an id the source never uses get no fact.
  """
  used = []
  for u in artifact_units:
    for i in _concrete_ids(u["stage2"], []):
      if i in identity and i not in used:
        used.append(i)
  out = []
  for a in used:
    for b in used:
      if a != b:
        out.append({"role": "distinct", "unit": None, "clause": [["differ", "#:" + a, "#:" + b]], "pass": PASS})
  return out


def _ground_locations(units, root=None):
  """(unit id, entity, place, world, qualified) of every ground positive located_at fact of an initial description.

  With `root` only the facts of that world.
  """
  out = []

  def walk(f, uid, world, q, positive=True):
    if not isinstance(f, list) or not f:
      return
    if f[0] == "not":
      walk(f[1], uid, world, q, not positive)
    elif f[0] == "and":
      for x in f[1:]:
        walk(x, uid, world, q, positive)
    elif f[0] == "is rel2" and f[1] == "located_at" and positive and la.is_concrete(f[2]) and la.is_concrete(f[3]):
      out.append((uid, f[2], f[3], world, q))

  for u in units:
    if u["form"] == "description_initial" and u["status"] == "supported":
      world = u.get("world") or "W0"
      if root is None or world == root:
        walk(sit._unit_formula(u), u["id"], world, sit.qualified(u.get("context")))
  return out


def _granularity(facts, flat):
  """{"units", "unit_level", "message"} for each unsupported location structure among facts that hold together."""
  places = {p for _, _, p, _, _ in facts}
  out = []
  for uid, x, p, w, q in facts:
    if x in places:
      out.append({"units": [uid], "unit_level": True,
                  "message": "%s is a location and is itself located in %s: nested places need hierarchical "
                             "location updates, which this route does not have" % (x, p)})
  by_entity = {}
  for uid, x, p, w, q in facts:
    by_entity.setdefault((x, w), []).append((uid, p))
  for (x, w), hits in sorted(by_entity.items()):
    ps = sorted({p for _, p in hits})
    if len(ps) > 1 and not all(p in flat for p in ps):
      out.append({"units": sorted({uid for uid, _ in hits}), "unit_level": False,
                  "message": "%s is at %s in %s, and these places are not all in the declared flat location set: they "
                             "may contain each other, so this is neither a conflict nor a supported state"
                             % (x, " and ".join(ps), w)})
  return out


def location_granularity(units, flat):
  """Source-level diagnostics: {"units", "unit_level", "message"} for each unsupported location structure.

  Location uniqueness holds only inside the declared flat set (A2.7).  One
  entity at two places that are not both in that set may be nested places, so
  it is neither a conflict nor two facts to keep: the route has no
  hierarchical location update.  A place that is itself located in a place
  states the nesting outright.  Facts are grouped by entity and world: one
  entity at one place in W0 and at another in W1 is two facts of two worlds
  (migration step 1b.6).  The source level reads the unqualified facts only
  (present, no scope location, no knower): every query rooted in their world
  keeps them together.  Facts that a query selection can leave out are
  checked per query (`query_granularity`; Astra's review R2).
  """
  return _granularity([f for f in _ground_locations(units) if not f[4]], flat)


def query_granularity(units, flat, root):
  """The location structures of one query: the root world's facts of the units its selection admits.

  A past fact, a fact of another knower or of another scope location is not
  admitted and is never compared.  An objective fact is admitted beside a
  named knower's.  An issue among unqualified facts alone has already made
  the source unsupported, so every issue found here involves a qualified fact.
  """
  return _granularity(_ground_locations(units, root), flat)
