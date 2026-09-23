"""Action profile: restrictions, their checks, the constructor hooks, negative necessities.

The pass `restrictions` of the action compiler (A4.2).  A restriction is

  forall V.. ( [GUARD and ..] executable(ACTION)  ->  REQUIRED )

ACTION is the pattern: one constructor with variables and constants in its
slots.  REQUIRED is a conjunction of signed state literals.  A GUARD is a
signed static literal (isa, connected) over pattern variables; it narrows
the pattern to a class.  Every executability path requires the hook
ok_<constructor>(ACTION, C), and this pass writes the hook of every
restricted constructor from one check per restriction:

  match       REQUIRED                  -> restriction_<k>_<unit>(PATTERN, C)
  nonmatch    differ(P_j, constant_j)   -> restriction_<k>_<unit>(GENERAL, C)
              differ(P_j, P_k)          -> ...   a variable repeated in slots j, k
              complement of a GUARD     -> ...   stated, never read from absence
  hook        every check of the constructor -> ok_<constructor>(GENERAL, C)
  necessity   GUARDs and the complement of one REQUIRED literal -> not poss(PATTERN, C)

C is the law's context term $ctxt(present, ?:Sit, L, $obj), one location
variable per distinct atom (encoding v2).

GENERAL is the constructor with one fresh variable per slot.  The match
clause has no guard in its body: an action whose required condition holds
satisfies the restriction whatever its class.  The hook is one clause, so the
checks are conjoined; two hook clauses would make them alternatives.  A
nonmatch needs a differ fact or a stated negative class.  An unknown identity
proves no nonmatch, so such an action stays unproven.  No clause here has a
positive poss head, and no clause concludes a required condition.

A constant in a lexical slot (a means, a value, `unspecified`) has no
nonmatch branch: lexical values have no distinctness policy yet.  The
restriction is compiled and the note says which actions stay unproven.

unsupported_restriction_scope, with a detail:

  state_guard            a fluent guard: its complement is not known
  guard_form             a guard that is no signed static literal
  free_variable          a guard or required variable outside the pattern
  repeated_variable      a variable repeated in a lexical slot
  action_slot_constraint an equality on a slot (from structural validation)

An uncertain restriction is unsupported_confidence_form.  A constructor with
an unsupported restriction gets no hook, so none of its actions is executable
in a partial theory; the source is unsupported anyway.

Nothing here calls a prover.
"""

import lc_action as la
import lc_action_library as lib
import lc_action_situate as sit

PASS = "restrictions"
FORM = "restriction"
REASON = "unsupported_restriction_scope"


class Scope(Exception):
  """A restriction outside the matcher: (detail, message)."""

  def __init__(self, detail, message):
    Exception.__init__(self, message)
    self.detail = detail


def _variables(f, out):
  if isinstance(f, list):
    for x in f[1:]:
      _variables(x, out)
  elif la.is_var(f) and f not in out:
    out.append(f)
  return out


def _flat(f):
  return [y for x in f[1:] for y in _flat(x)] if f[0] == "and" else [f]


def _atom(lit):
  return lit[1] if lit[0] == "not" else lit


def _complement(lit):
  return lit[1] if lit[0] == "not" else ["not", lit]


def restrictions(f, scope=()):
  """(binders, guards, action pattern, required literals) of every restriction of a unit formula."""
  op = f[0]
  if op == "forall":
    return restrictions(f[2], tuple(v for v in scope if v != f[1]) + (f[1],))
  if op == "and":
    return [r for x in f[1:] for r in restrictions(x, scope)]
  if op == "implies":
    items = _flat(f[1])
    execs = [x for x in items if x[0] == "executable"]
    if len(execs) == 1:
      return [(scope, [x for x in items if x is not execs[0]], execs[0][1], _flat(f[2]))]
  return []


def _check(guards, action, required):
  slots = la.CONSTRUCTORS[action[0]]
  for g in guards:
    a = _atom(g)
    if a[0] in la.FLUENTS:
      raise Scope("state_guard", "a restriction under a state condition (%s): the complement of a state guard is not "
                                 "known, so the actions outside it cannot be established" % a[0])
    if a[0] not in la.STATIC or (g[0] == "not" and g[1][0] == "not"):
      raise Scope("action_slot_constraint" if a[0] == "=" else "guard_form",
                  "a restriction guard is a signed isa or connected literal over the pattern's variables")
  pattern = _variables(action, [])
  free = [v for v in _variables(["and"] + guards + required, []) if v not in pattern]
  if free:
    raise Scope("free_variable", "variable %s stands in the guard or the required condition and not in the action "
                                 "pattern; the restriction would quantify over it" % ", ".join(free))
  for v in pattern:
    hits = [slots[i] for i, t in enumerate(action[1:]) if t == v]
    if len(hits) > 1 and any(s in la.LEXICAL_SLOTS for s in hits):
      raise Scope("repeated_variable", "variable %s repeats in a lexical slot; lexical values have no distinctness "
                                       "policy, so the nonmatching actions cannot be established" % v)


def _forall(variables, body):
  for v in reversed(variables):
    body = ["forall", v, body]
  return body


def _implies(body, head):
  return head if not body else ["implies", body[0] if len(body) == 1 else ["and"] + body, head]


def check_name(unit_id, k):
  """restriction_<occurrence>_<unit id>, occurrence counted from 1.

  The occurrence is digits only and stands first, so the name splits back
  into (occurrence, unit id) in one way: two restrictions never share a name,
  also when a unit id ends in `_2`.
  """
  return "%s%d_%s" % (sit.CHECK_PREFIX, k + 1, unit_id)


def general(constructor):
  """The constructor with one fresh variable per slot, and those variables."""
  names = ["P%d" % (i + 1) for i in range(len(la.CONSTRUCTORS[constructor]))]
  return [constructor] + names, names


def _formulas(name, guards, action, required):
  """(role, formula, row) for the match, nonmatch and necessity clauses of one restriction."""
  pattern = _variables(action, [])
  gen, names = general(action[0])
  slots = la.CONSTRUCTORS[action[0]]
  out, first, unproven = [], {}, []
  out.append(("restriction_check", _forall(pattern, _implies(list(required), [name, action])), "match"))
  for i, t in enumerate(action[1:]):
    if la.is_var(t):
      if t in first:
        out.append(("restriction_check", _forall(names, _implies([["differ", names[first[t]], names[i]]], [name, gen])),
                    "nonmatch: slots %s and %s differ" % (slots[first[t]], slots[i])))
      else:
        first[t] = i
    elif la.is_concrete(t):
      out.append(("restriction_check", _forall(names, _implies([["differ", names[i], t]], [name, gen])),
                  "nonmatch: %s is not %s" % (slots[i], t)))
    else:
      unproven.append("%s other than %s" % (slots[i], t))
  rename = {v: names[i] for v, i in first.items()}
  for g in guards:
    c = _complement(g)
    a = _atom(c)
    a2 = [a[0]] + [rename.get(x, x) for x in a[1:]]
    out.append(("restriction_check", _forall(names, _implies([a2 if c[0] != "not" else ["not", a2]], [name, gen])),
                "nonmatch: stated %s%s" % ("not " if c[0] == "not" else "", a[0])))
  for r in required:
    out.append(("necessity_restriction", _forall(pattern, _implies(list(guards) + [_complement(r)], ["not", ["poss", action]])),
                "necessity"))
  return out, unproven


def compile_unit(unit, namer):
  """Clauses of one structurally supported restriction unit.

  Returns {"situated", "situation", "clauses", "witnesses", "diagnostic",
  "requirements", "note", "checks"}; `checks` lists (check name, constructor).
  """
  out = {"situated": None, "situation": "shared_current", "clauses": None, "witnesses": [],
         "diagnostic": None, "requirements": [], "note": None, "checks": []}
  formula = sit._unit_formula(unit)
  out["situated"] = ["forall", sit.SIT, sit._situate(_as_state(formula), sit.SIT)]
  p = unit.get("confidence")
  if p is not None and p < 1:
    out["clauses"] = []
    out["diagnostic"] = ("unsupported_confidence_form",
                         "a restriction with probability %s: an uncertain necessary condition has no reviewed "
                         "compilation; the unit is kept and the action is not left unrestricted" % p, None)
    return out
  found = restrictions(formula)
  records, notes = [], []
  try:
    for scope, guards, action, required in found:
      _check(guards, action, required)
    for k, (scope, guards, action, required) in enumerate(found):
      name = check_name(unit["id"], k)
      formulas, unproven = _formulas(name, guards, action, required)
      for role, f, row in formulas:
        situated, clauses, witnesses = sit.clausify_law(unit["id"], f, namer(unit["id"]))
        for c in clauses:
          rec = {"role": role, "unit": unit["id"], "clause": c["clause"], "pass": PASS, "provenance": unit["id"],
                 "defeasible": False, "strict": True, "constructor": action[0], "check": name, "branch": row}
          if rec not in records:
            records.append(rec)
      out["checks"].append((name, action[0]))
      if unproven:
        notes.append("%s: no nonmatch branch for a lexical slot (%s); such actions stay unproven, never permitted"
                     % (name, "; ".join(unproven)))
  except Scope as e:
    out["clauses"], out["checks"] = [], []
    out["diagnostic"] = (REASON, str(e), e.detail)
    return out
  out["clauses"] = records
  out["note"] = " ".join(notes) or None
  return out


def _as_state(f):
  """The source formula with executable(A) written as poss(A), for the situated view only."""
  if isinstance(f, list) and f:
    if f[0] == "executable":
      return ["poss", f[1]]
    if f[0] in la.CONSTRUCTORS:
      return f
    return [f[0]] + [_as_state(x) for x in f[1:]]
  return f


def constructors_of(unit):
  """The constructors a restriction unit names, also when the unit is unsupported."""
  out = []
  for t in unit.get("action_terms") or []:
    if isinstance(t, list) and t and t[0] in la.CONSTRUCTORS and t[0] not in out:
      out.append(t[0])
  return out


def hooks(units, compiled, namer):
  """The hook clause of every restricted constructor, and the restriction table.

  `compiled` maps a unit id to its `checks`.  Returns (hook records, table).
  The table has one row per restricted constructor: its restriction units,
  its checks, whether the hook was written, and why not.
  """
  table = {}
  for u in units:
    if u["form"] != FORM:
      continue
    for k in constructors_of(u):
      row = table.setdefault(k, {"units": [], "checks": [], "hook": True, "withheld_for": []})
      row["units"].append(u["id"])
      if u["status"] != "supported":
        row["hook"] = False
        row["withheld_for"].append(u["id"])
    for name, k in compiled.get(u["id"], []):
      table[k]["checks"].append(name)
  names = [name for u in units for name, k in compiled.get(u["id"], [])]
  if len(names) != len(set(names)):
    raise ValueError("two restrictions share a check predicate: %s" % sorted(n for n in set(names) if names.count(n) > 1))
  records = []
  for k in sorted(table):
    row = table[k]
    if not row["hook"] or not row["checks"]:
      row["hook"] = False
      continue
    gen, names = general(k)
    f = _forall(names, _implies([[c, gen] for c in row["checks"]], [lib.hook_name(k), gen]))
    situated, clauses, witnesses = sit.clausify_law("hook_" + k, f, namer("hook_" + k))
    for c in clauses:
      records.append({"role": "hook", "unit": None, "units": list(row["units"]), "clause": c["clause"], "pass": PASS,
                      "constructor": k, "requires": list(row["checks"]), "defeasible": False, "strict": True})
  return records, table


def path_coverage(library, table):
  """One row per library path of a restricted constructor: every executability default and every applicability
  template (the source paths are instantiated from the templates), with its hook and what the hook requires."""
  rows = []
  paths = [c for c in library["clauses"] if c["role"] == "applicability_default"] + list(library["templates"])
  for c in paths:
    k = lib.head(c["clause"], "poss")[1][0]
    if k not in table:
      continue
    hook = [x for x in lib.literals(c["clause"]) if not lib.positive(x) and lib.predicate(x) == lib.hook_name(k)]
    rows.append({"constructor": k, "path": c["name"], "hook": lib.hook_name(k), "conjoined": len(hook) == 1,
                 "requires": list(table[k]["checks"]), "units": list(table[k]["units"]),
                 "hook_written": table[k]["hook"], "default_hook": "left out"})
  return rows
