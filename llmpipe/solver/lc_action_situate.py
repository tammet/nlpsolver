"""Action profile: scope, situations, witnesses and clauses of state formulas.

The second pass of the action compiler (`situation_compilation`).  It reads
a structurally supported source unit and handles the three state forms:

  description_static    wholly static knowledge; no situation is added
  description_initial   an initial description of world W; every fluent
                        occurrence gets W, also inside a quantified or
                        conditional formula
  state_law             an explicit standing law; one universally bound
                        situation, shared by all its fluent occurrences

Scope comes from the form of the unit, never from forall, implies or the
predicate of a conclusion.  Availability, restrictions and effects are left
to the later passes; this pass gives them no clauses.

Order (A4.1): situations are inserted first, at formula level, and the
situation of a standing law is bound by an explicit `forall ?:Sit` in the
situated view; the mixed-scope decision is taken on that view; then
implications are removed, negation is pushed inward, existentials are
Skolemized (one symbol per binder occurrence), the formula is distributed
into clauses, and a `normally` literal becomes a defeasible clause with a
`$block` literal, as in the ordinary encoding.  A witness of a
standing law therefore depends on the situation: sk(Sit, X).  A witness of an
initial or static description does not.

The situated formula of every unit is kept for inspection.  A clause that
concludes a static atom from a fluent is `mixed_scope_rule`: the unit is
reported and gets no clause; so is a negative static conclusion of an
implication with a fluent condition.  Nothing here runs the ordinary rewrite
sequence: no antonym or exclusion injection, no event compression, no
population, perspective, stative or narrative-transition pass.

Situations (encoding v2).  In the situated formula a fluent atom has its
situation as one more last argument: a world name (W0, W1, ...), `?:Sit`, or
`$do(ACTION, S)`.  In a clause the situation stands in the world slot of the
one context term and in no other argument (`situation_of` reads it):

  fact    P(args, $ctxt(T, W, L, K)): W the unit's world; T its tense (default
          present); L a fresh variable or the constant of a `scope` location;
          K a fresh variable (objective) or the knower constant (section 3)
  law     P(args, $ctxt(present, S, L_i, $obj)): S the law's situation
          variable `?:Sit`, or `$do(ACTION, ?:Sit)` in a successor literal;
          one location variable per distinct atom, `?:Lh` in a successor
          literal (the agreement rule of section 5); the objective knower

Compiler variables are `?:Sit`, `?:L<n>`, `?:Lh`, `?:Fv1`, `?:Fv2`; a source
variable becomes `?:v_<name>`, so a source variable called S or C cannot meet
a compiler variable.  A world name is reserved: no source variable is called
W0, W1, ... (`lc_action` rejects it).
"""

import copy

import lc_action as la
import lc_clausify
import lc_packages

SIT = "?:Sit"             # the situation variable of a law, in the world slot of its context terms
CTX = "?:Ctx"             # kept for readers of old records; no v2 clause holds it
OBJ = "$obj"              # the objective knower of a law
HEAD_L = "?:Lh"           # the location variable of a transition clause's successor literal
FACT_L, FACT_K = "?:Fv1", "?:Fv2"
WORLD_SLOT = 2            # the index of the situation in a $ctxt term


def is_world(t):
  """A world name: a situation constant of the source (W0, W1, ...)."""
  return isinstance(t, str) and bool(la.WORLD.match(t))


def is_context(t):
  return isinstance(t, list) and len(t) == 5 and t[0] == "$ctxt"


def situation_of(lit):
  """The situation of a clause literal: the world slot of its context term; None for a static literal."""
  if isinstance(lit, list) and lit and is_context(lit[-1]):
    return lit[-1][WORLD_SLOT]
  return None


def args_of(lit):
  """The ordinary arguments of a clause literal, without its context term."""
  return lit[1:-1] if is_context(lit[-1]) else lit[1:]


def knower_term(entity):
  """The clause term of a named knower or ambient location: the entity's concrete constant."""
  return "#:" + entity


def fact_context(world="W0", record=None):
  """The context term of a fact of `world` under its unit's context record (section 3); `world` in the world slot.

  A `scope` location stays as its constant; a `provenance` location or none is
  a fresh variable (the value stays in the unit record).  No knower is a
  fresh variable (objective); a stated knower is its constant.
  """
  c = record or {}
  tense = c.get("tense") or "present"
  loc = knower_term(c["location"]) if c.get("location") is not None and c.get("location_role") == "scope" else FACT_L
  kn = knower_term(c["knower"]) if c.get("knower") is not None else FACT_K
  return ["$ctxt", tense, world or "W0", loc, kn]


def qualified(record):
  """Whether a query selection can leave out the facts of a unit with this context record: a tense other than
  present, a `scope` location or a knower (section 3).  `lc_action_query.exclusions` decides it per query."""
  c = record or {}
  return (c.get("tense") or "present") != "present" \
    or (c.get("location") is not None and c.get("location_role") == "scope") or c.get("knower") is not None


def law_contexts():
  """A context maker for one law clause: one fresh location variable per distinct atom, ?:Lh for a successor literal.

  The maker reads an atom whose last argument is its situation and returns
  the context term with that situation in the world slot.
  """
  names = {}

  def make(atom):
    key = repr([atom[0].lstrip("-")] + list(atom[1:]))
    s = atom[-1]
    if key not in names:
      if isinstance(s, list) and s and s[0] == DO:
        names[key] = HEAD_L
      else:
        names[key] = "?:L%d" % (1 + sum(1 for v in names.values() if v != HEAD_L))
    return ["$ctxt", "present", s, names[key], OBJ]
  return make
PASS = "situation_compilation"
STATE_FORMS = ("description_static", "description_initial", "state_law")


LAW_ATOMS = ("can", "poss", "execution_denied")
CHECK_PREFIX = "restriction_"
HOOK_PREFIX = "ok_"
# static atoms that only the compiler writes (differ, derived_property) or that a library template reads
# (surface, standard_mode); a source formula never holds them
COMPILER_STATIC = ("differ", "derived_property", "surface", "standard_mode")
# the change marker of a stored fluent: it blocks the fluent's frame in the successor
MARKERS = {"has property": "changed_property", "is rel2": "changed_rel2", "have": "changed_have"}
DO = "$do"


def bears_situation(name):
  """Predicates whose atoms get the situation and the context: the fluents,
  poss, the denial marker execution_denied, the change markers, the
  per-restriction checks and the library's restriction hooks.  `can` is
  listed for the situated view of a source formula only; no compiled clause
  holds it (encoding v2)."""
  return name in la.FLUENTS or name in LAW_ATOMS or name in MARKERS.values() \
    or name.startswith((CHECK_PREFIX, HOOK_PREFIX))


class NotCompiled(Exception):
  """The formula is supported structurally but this pass has no rule for it."""


# ---------------------------------------------------------------------------
# 1. situations, at formula level


class Unsupported(Exception):
  """A well-formed state formula outside this pass's fragment: (reason, message)."""

  def __init__(self, reason, message):
    Exception.__init__(self, message)
    self.reason = reason


def situate(formula, form, world="W0"):
  """The situated view of a state formula.

  Returns (formula, situation).  Every fluent atom has one more argument, the
  situation term.  A standing law `state_law(F)` becomes
  `["forall", "?:Sit", F']`: the introduced situation is bound in the view
  itself, so the view has no free compiler variable.  `situation` is None for
  a static description, the unit's world name for an initial one and `?:Sit`
  for a standing law.  Static atoms and equalities are unchanged.
  `normally(F)` is moved inward by the ordinary rule until it qualifies one
  situated literal.
  """
  if form == "state_law":
    if not (isinstance(formula, list) and formula and formula[0] == "state_law"):
      raise NotCompiled("a standing law is state_law(F)")
    return ["forall", SIT, _situate(formula[1], SIT)], SIT
  if form == "description_initial":
    return _situate(formula, world), world
  if form == "description_static":
    return _situate(formula, None), None
  raise NotCompiled("form %s has no state scope" % form)


def _is_literal(f):
  if isinstance(f, list) and len(f) == 2 and f[0] == "not":
    f = f[1]
  return isinstance(f, list) and bool(f) and (bears_situation(f[0]) or f[0] in la.STATIC or f[0] == "=")


def _situate(f, sit):
  op = f[0]
  if bears_situation(op):
    return list(f) + [sit]
  if op in la.STATIC or op == "=" or op in COMPILER_STATIC:
    return list(f)
  if op in la.QUANTIFIERS:
    return [op, f[1], _situate(f[2], sit)]
  if op in ("and", "or", "not", "implies"):
    return [op] + [_situate(x, sit) for x in f[1:]]
  if op == "normally":
    # Situation insertion is a pure walk: it never rejects.  `clausify` checks
    # the default forms afterwards, so a rejected unit keeps its situated view.
    # The ordinary rule, reused: normally moves inward through implies, exists,
    # forall and and (to the last conjunct) until it qualifies one formula.
    # It runs on the situated body, so witnesses and situations are already right.
    return lc_clausify._push_normally_inside(_situate(f[1], sit))
  raise NotCompiled("operator %s in a state formula" % op)


def _check_default_leaves(f):
  """After the push every normally qualifies one literal; a disjunctive default does not."""
  if not (isinstance(f, list) and f):
    return
  if f[0] == "normally":
    if _has(f[1], {"normally"}):
      raise Unsupported("unsupported_default_form", "a default inside a default has no expansion here; the unit is kept")
    if not _is_literal(f[1]):
      raise Unsupported("unsupported_default_form",
                        "a default over a disjunction (or another formula that is not a literal after normally is "
                        "moved inward) has no expansion here; the unit is kept")
    return
  for x in f[1:]:
    _check_default_leaves(x)


def free_compiler_variables(f, bound=()):
  """The `?:` terms of a situated view that no enclosing quantifier binds."""
  if not isinstance(f, list) or not f:
    return {f} if isinstance(f, str) and f.startswith("?:") and f not in bound else set()
  if f[0] in la.QUANTIFIERS and len(f) == 3:
    return free_compiler_variables(f[2], bound + (f[1],))
  out = set()
  for x in f[1:]:
    out |= free_compiler_variables(x, bound)
  return out


def free_source_variables(f, bound=()):
  """The source variables of a situated view that no enclosing quantifier binds (a world name is no variable)."""
  if not isinstance(f, list) or not f:
    return {f} if la.is_var(f) and not is_world(f) and f not in bound else set()
  if f[0] in la.QUANTIFIERS and len(f) == 3:
    return free_source_variables(f[2], bound + (f[1],))
  out = set()
  for x in f[1:]:
    out |= free_source_variables(x, bound)
  return out


def _has(f, names):
  if isinstance(f, list) and f:
    return (isinstance(f[0], str) and f[0] in names) or any(_has(x, names) for x in f[1:])
  return False


def mixed_scope(f, positive=True, dynamic=False):
  """A timeless conclusion from a dynamic condition, read on the situated formula (A2.8).

  The implication direction of the source is kept.  The view already has
  normally moved inward, so a default conclusion is read where it stands.  Under `implies(A, B)`
  with a fluent in A, any static atom in B is such a conclusion, positive or
  negative: `red(egg) -> not isa(food, egg)` makes a stable type depend on a
  situation as `on(X, table) -> isa(base, X)` does.  A static condition on a
  fluent conclusion is the ordinary quantified description and is fine, also
  with a negative static antecedent.  A disjunction gives no direction; there
  a positive static disjunct beside a fluent disjunct is the defect.
  Returns the offending subformula or None.
  """
  op = f[0]
  if op == "not":
    return mixed_scope(f[1], not positive, dynamic)
  if op in la.QUANTIFIERS:
    return mixed_scope(f[2], positive, dynamic)
  if op == "normally":
    return mixed_scope(f[1], positive, dynamic)
  if op == "implies" and positive:
    hit = mixed_scope(f[1], False, False)
    return hit or mixed_scope(f[2], True, dynamic or _has(f[1], set(la.FLUENTS)))
  if op == "implies":            # not(A -> B) is A and not B: two facts, no direction
    return mixed_scope(f[1], True, dynamic) or mixed_scope(f[2], False, dynamic)
  if (op == "or") == positive and op in ("and", "or"):   # a disjunction, after polarity
    parts = f[1:]
    fluent = any(_has(x, set(la.FLUENTS)) for x in parts)
    for x in parts:
      atom = x[1] if x[0] == "not" else x
      asserted = (x[0] != "not") == positive
      if atom[0] in la.STATIC and asserted and fluent:
        return f
    for x in parts:
      hit = mixed_scope(x, positive, dynamic)
      if hit:
        return hit
    return None
  if op in ("and", "or"):
    for x in f[1:]:
      hit = mixed_scope(x, positive, dynamic)
      if hit:
        return hit
    return None
  if op in la.STATIC and dynamic:
    return f
  return None


# ---------------------------------------------------------------------------
# 2. clausification of a situated formula


def _nnf(f, positive=True):
  op = f[0]
  if op == "not":
    return _nnf(f[1], not positive)
  if op == "implies":
    return _nnf(["or", ["not", f[1]], f[2]], positive)
  if op in ("and", "or"):
    flip = {"and": "or", "or": "and"}
    return [op if positive else flip[op]] + [_nnf(x, positive) for x in f[1:]]
  if op in la.QUANTIFIERS:
    flip = {"forall": "exists", "exists": "forall"}
    return [op if positive else flip[op], f[1], _nnf(f[2], positive)]
  if op == "normally":
    if not positive:
      raise Unsupported("unsupported_default_form", "a negated default has no expansion here")
    return ["normally", _nnf(f[1], True)] + f[2:]      # f[2], when present, is the blocker class tag
  return f if positive else ["not", f]


def _substitute(f, var, term):
  if isinstance(f, list):
    return [_substitute(x, var, term) for x in f]
  return term if f == var else f


def _skolemize(f, universals, unit, names, witnesses, bound=()):
  """Replace existentials.  `universals` are the variables in scope, outermost first."""
  op = f[0]
  if op == "forall":
    v = _fresh(f[1], bound)
    body = _substitute(f[2], f[1], v) if v != f[1] else f[2]
    return _skolemize(body, universals + [v], unit, names, witnesses, bound + (v,))
  if op == "exists":
    name = names(f[1])
    term = [name] + list(universals) if universals else name
    witnesses.append({"variable": f[1], "term": copy.deepcopy(term), "depends_on": list(universals)})
    return _skolemize(_substitute(f[2], f[1], term), universals, unit, names, witnesses, bound)
  if op in ("and", "or"):
    return [op] + [_skolemize(x, universals, unit, names, witnesses, bound) for x in f[1:]]
  return f


def _fresh(v, bound):
  """A universal bound again under another binder of the same name gets a new name."""
  if v not in bound:
    return v
  n = 2
  while "%s_%d" % (v, n) in bound:
    n += 1
  return "%s_%d" % (v, n)


def _cnf(f):
  """A list of clauses; a clause is a list of literals (atom or [not, atom])."""
  op = f[0]
  if op == "and":
    out = []
    for x in f[1:]:
      out.extend(_cnf(x))
    return out
  if op == "or":
    parts = [_cnf(x) for x in f[1:]]
    out = [[]]
    for p in parts:
      out = [a + b for a in out for b in p]
    return out
  return [[f]]


def _term(t, universals):
  if isinstance(t, list):
    return [t[0]] + [_term(x, universals) for x in t[1:]]
  if t == SIT or is_world(t):
    return t
  if t in universals:
    return "?:v_" + t
  if la.is_concrete(t):
    return "#:" + t
  return t


def _literal(lit, universals, context):
  """One clause literal.  `context` is a context term (a fact, a query) or a maker (a law: law_contexts()).

  The situated atom's last argument, its situation, goes into the world slot
  of the context term; the clause literal has no separate situation argument.
  """
  neg = lit[0] == "not"
  atom = lit[1] if neg else lit
  out = [("-" if neg else "") + atom[0]] + [_term(x, universals) for x in atom[1:]]
  if bears_situation(atom[0]):
    ctx = copy.deepcopy(context(out) if callable(context) else context)
    ctx[WORLD_SLOT] = out.pop()
    out.append(ctx)
  return out


def _collect_universals(f, out, bound=()):
  """The universal variables of an NNF formula, renamed as _skolemize renames them."""
  op = f[0]
  if op == "forall":
    v = _fresh(f[1], bound)
    out.append(v)
    _collect_universals(_substitute(f[2], f[1], v) if v != f[1] else f[2], out, bound + (v,))
  elif op in ("exists", "and", "or"):
    for x in f[1:]:
      if isinstance(x, list):
        _collect_universals(x, out, bound)
  return out


def situation_class(lit):
  """named | shared_current | successor | none | free, read from the world slot of a clause literal.

  `named` is a world name (a fact of that world); `shared_current` the law's
  situation variable; `successor` `$do(A, ?:Sit)`.
  """
  name = lit[0].lstrip("-")
  if not bears_situation(name):
    return "none"   # a static atom, an equality or a $block literal
  sit = situation_of(lit)
  if isinstance(sit, list):
    return "successor" if len(sit) == 3 and sit[0] == DO and sit[2] == SIT else "free"
  return "named" if is_world(sit) else "shared_current" if sit == SIT else "free"


def _priority(lits, tag=None):
  """The ordinary blocker priority: ["$", CLASS, N].

  CLASS is the subject class the push tagged (the first isa of the rule's
  antecedent), else the class of the last negative isa condition, else
  `$generic`; N is the number of other negative conditions plus one
  (`lc_clausify._expand_normally`).
  """
  cls, n = "$generic", 1
  for x in lits:
    if x[0] == "-isa":
      cls = x[1]
    elif x[0].startswith("-"):
      n += 1
  return ["$", tag or cls, n]


def clausify(unit_id, formula, form, names, world="W0", record=None):
  """(situated formula, clause records, witnesses) of one state formula.

  `world` and `record` give an initial description its situation constant and
  its fact context.  Raises Unsupported for a mixed-scope formula or a default
  outside the literal form; the situated view is then in the exception's
  `situated`.
  """
  situated, sit = situate(formula, form, world or "W0")
  try:
    _check_default_leaves(situated)
  except Unsupported as e:
    e.situated = situated
    raise
  bad = mixed_scope(situated)
  if bad is not None:
    e = Unsupported("mixed_scope_rule",
                    "a timeless isa or connected conclusion from a fluent condition: a stable type or a stated route "
                    "would depend on a situation; no clause is emitted for this unit")
    e.situated, e.subformula = situated, bad
    raise e
  body = situated[2] if sit == SIT else situated        # the situation binder is the outermost universal
  try:
    nnf = _nnf(body)
  except Unsupported as e:
    e.situated = situated
    raise
  universals = ([SIT] if sit == SIT else []) + _collect_universals(nnf, [])
  witnesses = []
  matrix = _skolemize(nnf, [SIT] if sit == SIT else [], unit_id, names, witnesses)
  records = []
  for clause in _cnf(matrix):
    context = law_contexts() if sit == SIT else fact_context(world, record)
    lits, defaults, tag = [], [], None
    for lit in clause:
      default = lit[0] == "normally"
      if default and len(lit) > 2:
        tag = lit[2]
      x = _literal(lit[1] if default else lit, set(universals) - {SIT}, context)
      if x not in lits:
        lits.append(x)
        if default:
          defaults.append(x)
    if len(defaults) > 1:
      e = Unsupported("unsupported_default_form", "one clause with two default literals has no expansion here")
      e.situated = situated
      raise e
    classes = {situation_class(x) for x in lits}
    role = "standing_law" if "shared_current" in classes else "initial_fact" if "named" in classes else "static"
    rec = {"role": role, "unit": unit_id, "clause": lits, "pass": PASS}
    if defaults:
      head = defaults[0]
      conditions = [x for x in lits if x is not head]
      blocked = [head[0][1:]] + head[1:] if head[0].startswith("-") else ["$not", head]
      rec["clause"] = lits + [["$block", _priority(conditions, tag), blocked]]
      rec["defeasible"] = True
    records.append(rec)
  return situated, records, witnesses


def clausify_law(unit_id, formula, names):
  """Clauses of an action-law formula: every situation-bearing atom shares `?:Sit`.

  Used by the availability pass for executability paths and denials.  The
  situated view is `["forall", "?:Sit", F]`.  Returns (situated, clause lists
  with a `defeasible` flag, witnesses); the caller assigns roles.
  """
  return clausify_situated(unit_id, ["forall", SIT, _situate(formula, SIT)], names)


def clausify_situated(unit_id, situated, names):
  """Clauses of `["forall", "?:Sit", F]` whose atoms already hold their situation terms.

  The effect pass uses it: an effect head stands at `$do(ACTION, ?:Sit)`.
  """
  try:
    _check_default_leaves(situated)
    nnf = _nnf(situated[2])
  except Unsupported as e:
    e.situated = situated
    raise
  universals = [SIT] + _collect_universals(nnf, [])
  witnesses = []
  matrix = _skolemize(nnf, [SIT], unit_id, names, witnesses)
  out = []
  for clause in _cnf(matrix):
    context = law_contexts()
    lits, defaults, tag = [], [], None
    for lit in clause:
      default = lit[0] == "normally"
      if default and len(lit) > 2:
        tag = lit[2]
      x = _literal(lit[1] if default else lit, set(universals) - {SIT}, context)
      if x not in lits:
        lits.append(x)
        if default:
          defaults.append(x)
    if len(defaults) > 1:
      e = Unsupported("unsupported_default_form", "one clause with two default literals has no expansion here")
      e.situated = situated
      raise e
    if defaults:
      head = defaults[0]
      blocked = [head[0][1:]] + head[1:] if head[0].startswith("-") else ["$not", head]
      lits = lits + [["$block", _priority([x for x in lits if x is not head], tag), blocked]]
    out.append({"clause": lits, "defeasible": bool(defaults)})
  return situated, out, witnesses


# ---------------------------------------------------------------------------
# the pass over a source


def _unit_formula(unit):
  f = unit["stage2"][2]
  return f[1][2] if f[0] == "and" else f[2]       # a confidence package wraps holds


def _existential_binders(f, out):
  """The existential binder occurrences of an NNF formula, in Skolemization order."""
  op = f[0]
  if op == "exists":
    out.append(f[1])
    _existential_binders(f[2], out)
  elif op == "forall":
    _existential_binders(f[2], out)
  elif op in ("and", "or"):
    for x in f[1:]:
      _existential_binders(x, out)
  return out


def witness_namer(units):
  """One Skolem symbol per existential binder occurrence.

  Counted after negation is pushed inward, so `not(forall X ...)` counts.
  `sk_<Var>` when the variable has one such binder in the whole source;
  `sk_<Var>_<unit>` when it has one in this unit and others elsewhere;
  `sk_<Var>_<unit>_<k>` for the k-th binder of that variable in one unit.
  Two sibling binders that reuse a name are two objects.
  """
  per_unit = {}
  for u in units:
    if u.get("form") not in STATE_FORMS or u.get("status") != "supported":
      continue
    try:
      situated, sit = situate(_unit_formula(u), u["form"])
      binders = _existential_binders(_nnf(situated[2] if sit == SIT else situated), [])
    except (NotCompiled, Unsupported):
      continue
    per_unit[u["id"]] = binders
  total = {}
  for binders in per_unit.values():
    for v in binders:
      total[v] = total.get(v, 0) + 1

  def for_unit(unit_id):
    mine = per_unit.get(unit_id, [])
    seen = {}

    def name(v):
      seen[v] = seen.get(v, 0) + 1
      if total.get(v, 0) <= 1:
        return "sk_%s" % v
      if mine.count(v) <= 1:
        return "sk_%s_%s" % (v, unit_id)
      return "sk_%s_%s_%d" % (v, unit_id, seen[v])
    return name
  return for_unit


def compile_unit(unit, namer):
  """Situated view and clauses of one structurally supported unit.

  Returns {"situated", "situation", "clauses", "witnesses", "diagnostic", "note"}.
  An action law gets `clauses: None` and a note: a later pass compiles it.
  A state unit gets clauses, or a `diagnostic` (reason, message, subformula)
  and `clauses: []`.  A state unit is never left without one of the two.
  """
  out = {"situated": None, "situation": None, "clauses": None, "witnesses": [], "diagnostic": None, "note": None}
  if unit["form"] not in STATE_FORMS:
    out["note"] = "an action law; compiled by a later pass"
    return out
  world = unit.get("world") or "W0"
  out["situation"] = {"state_law": "shared_current", "description_initial": "named",
                      "description_static": "none"}[unit["form"]]
  try:
    situated, records, witnesses = clausify(unit["id"], _unit_formula(unit), unit["form"], namer(unit["id"]),
                                            world, unit.get("context"))
  except Unsupported as e:
    out["situated"] = getattr(e, "situated", None)
    out["clauses"] = []
    out["diagnostic"] = (e.reason, str(e), getattr(e, "subformula", None))
    return out
  out["situated"], out["witnesses"] = situated, witnesses
  p = unit.get("confidence")
  if p is not None and p <= 0.5:
    out["clauses"] = []
    out["diagnostic"] = ("unsupported_confidence_form",
                         "a state description with probability %s: the ordinary route negates its consequent; this route "
                         "keeps the unit and does not read it as its negation" % p, None)
    return out
  if p is not None:
    for r in records:
      r["source_probability"] = p
    if p < 1:
      # the ordinary convention and distribution (lc_packages): evidence 2p - 1 on the anchor clauses
      spread = lc_packages._distribute_clause_confidence([r["clause"] for r in records], round(2.0 * p - 1.0, 4), unit["id"])
      for r, c in zip(records, spread):
        if "@confidence" in c:
          r["confidence"] = c["@confidence"]
  out["clauses"] = records
  return out


def inspect(package):
  """The lower-level operation `situation_insertion_skolemization`.

  Runs situation insertion, Skolemization and clausification on one Stage-2
  source package, whatever its support status.  The result is for
  inspection: `usable` is always False, and no artifact takes these clauses.
  """
  uid, body, conf, err = la.split_package(package)
  if err:
    raise NotCompiled(err)
  formula = body[2]
  form = "state_law" if formula[0] == "state_law" else \
    "description_initial" if _has_fluent(formula) else "description_static"
  counter = {}

  def name(v):
    counter[v] = counter.get(v, 0) + 1
    return "sk_%s" % v if counter[v] == 1 else "sk_%s_%d" % (v, counter[v])
  situated, records, witnesses = clausify(uid, formula, form, name)
  return {"operation": "situation_insertion_skolemization", "usable": False, "unit": uid,
          "situated": situated, "clauses": records, "witnesses": witnesses}


def _has_fluent(f):
  if isinstance(f, list) and f:
    return f[0] in la.FLUENTS or any(_has_fluent(x) for x in f[1:])
  return False
