"""Action profile: structural validation of Stage-2 source and query logic.

This module is the validator of the opt-in action route (`physical_v1`).
It reads Stage-2 packages, checks forms, positions, arities, variable
binding and actor agreement, recognizes which action-law form a source unit
has, and reports two kinds of diagnostic:

  invalid       the package is malformed; the outcome is `translation_invalid`
                and a correction can name the unit, the subformula and the
                structural error;
  unsupported   the package is well formed but outside the first executable
                fragment; the outcome is `unsupported_translation` with one
                of the reason names in REASONS.

It emits no clauses.  Situations, witnesses, the library, routes,
restrictions, effects and query views belong to the later passes of this
module; `PENDING_PASSES` names them.  Nothing here normalizes a lexical
value: `unspecified`, the means and the property values are kept verbatim.

Nothing in this module calls a model or a prover.
"""

import json
import re

PROFILE = "physical_v1"
ORDINARY = "ordinary"

# constructor -> slot names; the first slot is always the actor
CONSTRUCTORS = {
  "move": ("actor", "from", "to", "means"),
  "take": ("actor", "object"),
  "put_on": ("actor", "object", "support"),
  "put_in": ("actor", "object", "container"),
  "change": ("actor", "object", "value", "tool"),
}
# slots that hold a lexical value (or `unspecified`), not an entity
LEXICAL_SLOTS = {"means", "value"}
# slots where the reserved sentinel `unspecified` may stand
UNSPECIFIED_SLOTS = {"means", "tool"}
UNSPECIFIED = "unspecified"

FLUENTS = {"is rel2": 3, "has property": 2, "have": 2}
STATIC = {"isa": 2, "connected": 3}
RELATIONS = ("located_at", "on", "in", "holding")
ACTION_OPERATORS = {"can": 2, "executable": 1, "after": 2, "state_law": 1}
CONNECTIVES = {"and", "or", "not", "implies", "normally"}
QUANTIFIERS = {"forall", "exists"}
QUERY_PACKAGES = ("plan", "reachable", "verify", "question", "ask")
STEP_COMPARISONS = ("at_most", "exactly")
# the ordinary Davidsonian event form; a unit in this form is kept and
# reported as unsupported, never approximated by a constructor
EVENT_PREDICATES = {"has type": {2}, "has actor": {2}, "has target": {2},
                    "has source": {2}, "has destination": {2, 3},
                    "has instrument": {2}, "has location": {2, 3},
                    "has recipient": {2}, "has result": {2},
                    "has time": {2, 3}, "capability": {1}}
EVENT_CLASSES = {"activity", "event"}

# Reserved vocabulary the library reads (A2.2).  Kept for documentation and
# for later passes; the validator does not close any lexical slot.
RESERVED_PROPERTIES = ("clear_top", "empty")
RESERVED_CLASSES = ("person", "hand", "block")
SURFACE_CLASSES = ("table", "floor", "shelf", "counter")
STANDARD_MODES = ("bus", "train", "ship", "ferry", "plane", "taxi", "foot")

# unsupported_translation reasons: name -> the pass that detects it.
# "structural" reasons are detected here, from the form of one unit or from
# the units of one source.  The others are recorded by later passes through
# `action_route.add_diagnostic`; this module only knows their names.
REASONS = {
  "unsupported_capability_restriction": "structural",
  "unsupported_restriction_scope": "structural",
  "defeasible_text_effect": "structural",
  "existential_availability_head": "structural",
  "existential_state_law_head": "structural",
  "occurrence": "structural",
  "unsupported_action_kind": "structural",
  "unsupported_relation_policy": "structural",
  "unexpressible_temporal_permission_scope": "structural",
  "method_collision": "structural",
  "unsupported_goal_form": "structural",
  "unsupported_law_form": "structural",
  "unsupported_executability_assertion": "structural",
  "existential_effect_head": "structural",
  "unsupported_contextual_location": "structural",
  "mixed_scope_rule": "situation_compilation",
  "unsupported_default_form": "situation_compilation",
  "ambiguous_state_scope": "translation_reading",
  "unsupported_location_granularity": "availability_routes_identity",
  "unsupported_confidence_form": "availability_routes_identity",
  "ambiguous_state_policy": "effects_state_policy",
  "unsupported_stored_state_law": "effects_state_policy",
  "unsupported_transport_dependency": "effects_state_policy",
}
# the source passes after structural validation, in order.  `query_views` is
# a pass over one query and is recorded in the query artifact.
PENDING_PASSES = ("situation_compilation", "action_library",
                  "availability_routes_identity", "restrictions",
                  "effects_state_policy")

FORMS = ("description_static", "description_initial", "state_law",
         "availability", "denial", "restriction", "effect", "ordinary_event")

VAR = re.compile(r"^[A-Z][A-Z0-9]?$")
WORLD = re.compile(r"^W[0-9]+$")
DEFAULT_WORLDS = ("W0",)
TENSES = ("present", "past", "future")
LOCATION_ROLES = ("provenance", "scope")
CONCRETE = re.compile(r"^.+ \d+$")
LEXICAL = re.compile(r"^[a-z][a-z0-9_ ]*$")
WITNESS = re.compile(r"^sk_[A-Z][A-Z0-9]?$")
UNIT_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def is_var(t):
  return isinstance(t, str) and bool(VAR.match(t))


def is_concrete(t):
  return isinstance(t, str) and bool(CONCRETE.match(t))


def is_lexical(t):
  return isinstance(t, str) and bool(LEXICAL.match(t)) and not WITNESS.match(t)


def _show(f):
  s = json.dumps(f, ensure_ascii=False)
  return s if len(s) <= 200 else s[:197] + "..."


class Report(object):
  """Diagnostics of one package, in the order found."""

  def __init__(self, unit):
    self.unit = unit
    self.items = []

  def invalid(self, code, path, sub, message):
    self.items.append({"level": "invalid", "code": code, "unit": self.unit,
                       "path": "/" + "/".join(str(i) for i in path),
                       "subformula": _show(sub), "message": message})

  def unsupported(self, reason, path, sub, message, detail=None):
    if reason not in REASONS:
      raise ValueError("unknown unsupported reason %r" % reason)
    self.items.append({"level": "unsupported", "reason": reason, "unit": self.unit,
                       "path": "/" + "/".join(str(i) for i in path),
                       "subformula": _show(sub), "message": message})
    if detail is not None:
      self.items[-1]["detail"] = detail

  def has(self, level):
    return any(d["level"] == level for d in self.items)


# ---------------------------------------------------------------------------
# terms, action terms, atoms


def check_term(t, bound, rep, path, identity, slot=None, witnesses=False):
  """An entity slot holds a bound variable or a declared concrete id."""
  if not isinstance(t, str):
    rep.invalid("term", path, t, "a term is a string; Skolem and function terms do not occur in Stage 2")
    return
  if WITNESS.match(t):
    if not witnesses:
      rep.invalid("witness_constant", path, t, "a witness constant is compiler output and does not occur in Stage 2")
    return
  if is_var(t):
    if t not in bound:
      rep.invalid("unbound_variable", path, t, "variable %s is not bound by forall or exists" % t)
    return
  if t == UNSPECIFIED:
    if slot not in UNSPECIFIED_SLOTS:
      rep.invalid("unspecified_position", path, t,
                  "`unspecified` stands only in a means or tool slot; it is not an entity, a witness or a wildcard")
    return
  if is_concrete(t):
    if identity is not None and t not in identity:
      rep.invalid("unknown_entity", path, t, "entity id %r is not in the source identity map" % t)
    return
  if slot in LEXICAL_SLOTS and is_lexical(t):
    return
  if slot in LEXICAL_SLOTS:
    rep.invalid("lexical_value", path, t, "a %s slot holds a lexical constant, a variable or a declared id" % slot)
  else:
    rep.invalid("entity_slot", path, t,
                "an entity slot holds a bound variable or a declared entity id, not the lexical constant %r" % t)


def check_action(a, bound, rep, path, identity, witnesses=False):
  """One of the five action terms, with the right arity and slot kinds."""
  if not (isinstance(a, list) and a and isinstance(a[0], str) and a[0] in CONSTRUCTORS):
    rep.invalid("action_term", path, a, "expected one of the action terms %s" % ", ".join(sorted(CONSTRUCTORS)))
    return False
  slots = CONSTRUCTORS[a[0]]
  if len(a) != len(slots) + 1:
    rep.invalid("action_arity", path, a, "%s takes %d arguments (%s)" % (a[0], len(slots), ", ".join(slots)))
    return False
  for i, slot in enumerate(slots):
    check_term(a[i + 1], bound, rep, path + [i + 1], identity, slot, witnesses)
  return True


def _check_atom(f, bound, rep, path, identity):
  """A fluent, static or equality atom.  Returns its kind or None."""
  op = f[0]
  if op in FLUENTS or op in STATIC:
    n = FLUENTS.get(op) or STATIC[op]
    if len(f) != n + 1:
      rep.invalid("arity", path, f, "%s takes %d arguments" % (op, n))
      return None
    if op == "is rel2":
      if not is_lexical(f[1]):
        rep.invalid("relation_name", path + [1], f[1], "the relation of `is rel2` is a lexical constant")
      elif f[1] not in RELATIONS:
        rep.unsupported("unsupported_relation_policy", path, f,
                        "relation %r has no situation policy; the classified relations are %s"
                        % (f[1], ", ".join(RELATIONS)))
      for i in (2, 3):
        check_term(f[i], bound, rep, path + [i], identity)
    elif op == "has property":
      if not is_lexical(f[1]):
        rep.invalid("lexical_value", path + [1], f[1], "a property value is a lexical constant")
      check_term(f[2], bound, rep, path + [2], identity)
    elif op == "have":
      for i in (1, 2):
        check_term(f[i], bound, rep, path + [i], identity)
    elif op == "isa":
      if not is_lexical(f[1]):
        rep.invalid("lexical_value", path + [1], f[1], "a class name is a lexical constant")
      check_term(f[2], bound, rep, path + [2], identity)
    else:  # connected(F, T, M)
      for i in (1, 2):
        check_term(f[i], bound, rep, path + [i], identity)
      check_term(f[3], bound, rep, path + [3], identity, "means")
    return "fluent" if op in FLUENTS else "static"
  if op == "=":
    if len(f) != 3:
      rep.invalid("arity", path, f, "= takes two terms")
      return None
    for i in (1, 2):
      check_term(f[i], bound, rep, path + [i], identity, "means")
    return "equality"
  return None


class _Walk(object):
  """One pass over a formula.  Records where the action operators stand.

  `where` is the tuple of (operator, argument index) pairs from the formula
  root down to the current node; the position rules read it afterwards.
  """

  def __init__(self, rep, identity, profile, query=False):
    self.rep = rep
    self.identity = identity
    self.profile = profile
    self.query = query
    self.found = []      # (operator, path, where, node)
    self.kinds = set()   # fluent | static | equality | event

  def formula(self, f, bound, path, where):
    rep = self.rep
    if not (isinstance(f, list) and f and isinstance(f[0], str)):
      rep.invalid("formula", path, f, "a formula is a non-empty list headed by an operator or a predicate")
      return
    op = f[0]
    if op in CONSTRUCTORS:
      rep.invalid("action_term_position", path, f,
                  "an action term is not a formula; it stands inside can, executable, after or a verify list")
      return
    if self.profile == ORDINARY and (op in ACTION_OPERATORS or op == "connected"):
      rep.invalid("action_syntax_in_ordinary_profile", path, f,
                  "%s belongs to the action profile; the ordinary profile does not accept it" % op)
      return
    if op in QUANTIFIERS:
      if len(f) != 3 or not is_var(f[1]):
        rep.invalid("quantifier", path, f, "%s takes a variable and a formula" % op)
        return
      if f[1] in bound:
        rep.invalid("rebound_variable", path, f, "variable %s is already bound in this scope" % f[1])
      if WORLD.match(f[1]):
        rep.invalid("reserved_variable", path, f, "%s is a world name; a source variable has another name" % f[1])
      self.found.append((op, path, where, f))
      self.formula(f[2], bound | {f[1]}, path + [2], where + ((op, 2),))
    elif op in ("not", "normally"):
      if len(f) != 2:
        rep.invalid("arity", path, f, "%s takes one operand" % op)
        return
      if op == "normally":
        self.found.append((op, path, where, f))
      self.formula(f[1], bound, path + [1], where + ((op, 1),))
    elif op == "implies":
      if len(f) != 3:
        rep.invalid("arity", path, f, "implies takes two operands")
        return
      self.found.append((op, path, where, f))
      self.formula(f[1], bound, path + [1], where + ((op, 1),))
      self.formula(f[2], bound, path + [2], where + ((op, 2),))
    elif op in ("and", "or"):
      if len(f) < 3:
        rep.invalid("arity", path, f, "%s takes at least two operands" % op)
        return
      for i in range(1, len(f)):
        self.formula(f[i], bound, path + [i], where + ((op, i),))
    elif op == "can":
      if len(f) != 3:
        rep.invalid("arity", path, f, "can takes an actor and an action term")
        return
      check_term(f[1], bound, rep, path + [1], self.identity)
      if check_action(f[2], bound, rep, path + [2], self.identity) and f[1] != f[2][1]:
        rep.invalid("actor_agreement", path, f,
                    "the actor of can (%s) differs from the actor slot of the action term (%s)" % (f[1], f[2][1]))
      self.found.append((op, path, where, f))
    elif op == "executable":
      if len(f) != 2:
        rep.invalid("arity", path, f, "executable takes one action term; the term supplies the actor")
        return
      check_action(f[1], bound, rep, path + [1], self.identity)
      self.found.append((op, path, where, f))
    elif op == "after":
      if len(f) != 3:
        rep.invalid("arity", path, f, "after takes an action term and an effect formula")
        return
      check_action(f[1], bound, rep, path + [1], self.identity)
      self.found.append((op, path, where, f))
      self.formula(f[2], bound, path + [2], where + ((op, 2),))
    elif op == "state_law":
      if len(f) != 2:
        rep.invalid("arity", path, f, "state_law takes one formula")
        return
      self.found.append((op, path, where, f))
      self.formula(f[1], bound, path + [1], where + ((op, 1),))
    elif op == "@time":
      if len(f) != 3:
        rep.invalid("arity", path, f, "@time takes a time expression and a formula")
        return
      self.found.append((op, path, where, f))
      self.formula(f[2], bound, path + [2], where + ((op, 2),))
    elif op in EVENT_PREDICATES:
      if len(f) - 1 not in EVENT_PREDICATES[op]:
        rep.invalid("arity", path, f, "%s arity" % op)
      else:
        self.event_arguments(f, bound, path)
      self.kinds.add("event")
    else:
      kind = _check_atom(f, bound, rep, path, self.identity)
      if kind is None and op not in FLUENTS and op not in STATIC and op != "=":
        rep.invalid("unknown_predicate", path, f,
                    "%r is not a predicate of the action profile" % op)
      elif kind:
        if kind == "static" and f[0] == "isa" and f[1] in EVENT_CLASSES:
          kind = "event"
        self.kinds.add(kind)


def _event_arguments(self, f, bound, path):
  """Binding and term kinds in the ordinary event predicates.

  The first argument is the event; `has type` then holds a lexical verb; the
  other predicates hold a participant (a bound variable, a declared id or a
  lexical constant such as a bare noun or `past`) and, in the three-place
  forms, a lexical context word.  The unit is unsupported either way; a free
  variable, a Skolem term or an undeclared id makes it malformed first.
  """
  rep = self.rep
  for i in range(1, len(f)):
    t = f[i]
    lexical_only = (f[0] == "has type" and i == 2) or i == 3
    if not isinstance(t, str):
      rep.invalid("term", path + [i], t, "a term is a string; Skolem and function terms do not occur in Stage 2")
    elif WITNESS.match(t):
      rep.invalid("witness_constant", path + [i], t, "a witness constant is compiler output and does not occur in Stage 2")
    elif lexical_only:
      if not is_lexical(t):
        rep.invalid("lexical_value", path + [i], t, "this slot of %s holds a lexical constant" % f[0])
    elif is_var(t):
      if t not in bound:
        rep.invalid("unbound_variable", path + [i], t, "variable %s is not bound by forall or exists" % t)
    elif is_concrete(t):
      if self.identity is not None and t not in self.identity:
        rep.invalid("unknown_entity", path + [i], t, "entity id %r is not in the source identity map" % t)
    elif i == 1:
      rep.invalid("event_argument", path + [i], t, "the first argument of %s is the event: a bound variable or a declared id" % f[0])
    elif not is_lexical(t):
      rep.invalid("term", path + [i], t, "not a variable, a declared id or a lexical constant")


_Walk.event_arguments = _event_arguments


def _ops(where):
  return [w[0] for w in where]


def _signed_state_literals(f):
  """True when f is a conjunction of signed fluent literals (an effect head)."""
  if not isinstance(f, list) or not f:
    return False
  if f[0] == "and":
    return all(_signed_state_literals(x) for x in f[1:])
  if f[0] == "not" and len(f) == 2:
    f = f[1]
  return isinstance(f, list) and bool(f) and f[0] in FLUENTS


def _contains(f, names):
  if isinstance(f, list):
    if f and isinstance(f[0], str) and f[0] in names:
      return True
    return any(_contains(x, names) for x in f[1:])
  return False


# ---------------------------------------------------------------------------
# source units


def split_package(pkg):
  """(unit id, holds formula, confidence or None, error message or None)."""
  if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "@id" and isinstance(pkg[1], str)):
    return None, None, None, "a package is [\"@id\", id, PACKAGE]"
  uid, body, conf = pkg[1], pkg[2], None
  if not UNIT_ID.match(uid):
    return uid, None, None, "unit id %r" % uid
  if isinstance(body, list) and body and body[0] == "and" and len(body) == 3 \
     and isinstance(body[2], list) and body[2] and body[2][0] == "@p":
    p = body[2]
    if len(p) != 3 or p[1] != uid or isinstance(p[2], bool) or not isinstance(p[2], (int, float)) \
       or not 0 < p[2] <= 1:
      return uid, None, None, "a confidence package is [\"and\", PACKAGE, [\"@p\", id, p]] with the unit's id and 0 < p <= 1"
    conf, body = p[2], body[1]
  return uid, body, conf, None


def validate_source_unit(pkg, identity=None, profile=PROFILE, worlds=DEFAULT_WORLDS):
  """Validate one source package.  Returns a dict:

    id, formula, confidence, form, diagnostics, status, action_terms, world

  `status` is invalid, unsupported or supported; supported means that the
  structural pass found nothing, not that the later passes will accept it.
  A package is holds(W, F) for a world W of the source's `worlds` declaration
  (default W0); another world is `undeclared_world` (encoding v2, A3.2).
  """
  uid, body, conf, err = split_package(pkg)
  rep = Report(uid)
  out = {"id": uid, "formula": None, "confidence": conf, "form": None,
         "action_terms": [], "diagnostics": rep.items, "status": "invalid", "world": None}
  if err:
    rep.invalid("package", [], pkg, err)
    return out
  if isinstance(body, list) and body and body[0] in QUERY_PACKAGES:
    rep.invalid("query_in_source", [2], body, "a %s package is a query; a source holds only holds(W, F) packages" % body[0])
    return out
  if not (isinstance(body, list) and len(body) == 3 and body[0] == "holds" and isinstance(body[1], str)
          and WORLD.match(body[1])):
    rep.invalid("package", [2], body, "a source package is holds(W, F) with a world name W0, W1, ...")
    return out
  if body[1] not in worlds:
    where = [2, 1, 1] if pkg[2][0] == "and" else [2, 1]      # the world slot of the holds package
    rep.invalid("undeclared_world", where, body[1], "world %s is not in the source's worlds declaration %s" % (body[1], list(worlds)))
    return out
  out["world"] = body[1]
  f = body[2]
  out["formula"] = f
  walk = _Walk(rep, identity, profile)
  walk.formula(f, set(), [2, 2], ())
  if not rep.has("invalid"):
    out["form"] = _recognize(f, walk, rep)
    if out["form"] == "effect" and conf is not None and conf < 1 and not rep.has("unsupported"):
      rep.unsupported("defeasible_text_effect", [2], body,
                      "an uncertain text effect (@p = %s): only strict text effects have a reviewed effect and "
                      "marker contract; the confidence is kept and the effect is not read as strict" % conf)
    out["action_terms"] = [n[1] if op == "after" or op == "executable" else n[2]
                           for op, _, _, n in walk.found if op in ("can", "executable", "after")]
  out["status"] = "invalid" if rep.has("invalid") else "unsupported" if rep.has("unsupported") else "supported"
  return out


def _recognize(f, walk, rep):
  """Position rules and the unit's law form (A3.2, A2.5, A7.3).

  Action-law recognition comes first: a unit with an effect, a restriction
  or an availability is that law, whatever its other atoms are.
  """
  found = walk.found
  ops = [x[0] for x in found]
  if "event" in walk.kinds:
    if _contains(f, set(ACTION_OPERATORS)):
      rep.invalid("mixed_event_form", [2, 2], f, "the ordinary event form and the action operators do not mix in one unit")
      return None
    actual = f[0] == "exists" and not _contains(f, {"capability", "implies", "forall"})
    if actual:
      rep.unsupported("occurrence", [2, 2], f, "an actual narrative occurrence; the action route has no occurrence semantics")
    else:
      rep.unsupported("unsupported_action_kind", [2, 2], f,
                      "an action in the ordinary event form: no constructor expresses it (creation, consumption, transport, transfer or another kind)")
    return "ordinary_event"
  for op, path, where, node in found:
    if op == "@time":
      if _contains(node, {"can", "executable", "after"}):
        rep.unsupported("unexpressible_temporal_permission_scope", path, node,
                        "a time-qualified permission; this grammar cannot express its validity interval")
      else:
        rep.invalid("time_wrapper", path, node, "@time is not part of the action profile")
  # state_law: directly under holds, once, with no action operator inside
  laws = [x for x in found if x[0] == "state_law"]
  for op, path, where, node in laws:
    if where:
      rep.invalid("state_law_position", path, node,
                  "state_law stands directly under holds(W, ...); it is not nested, negated, quantified over or placed in an antecedent")
    elif _contains(node[1], {"can", "executable", "after", "state_law"}):
      rep.invalid("state_law_content", path, node,
                  "a standing state law holds state formulas only; availability, restrictions and effects have their own forms")
  # after: under forall and at most one implies consequent
  for op, path, where, node in [x for x in found if x[0] == "after"]:
    allowed = all(w[0] in ("forall", "and") or w == ("implies", 2) for w in where) \
      and _ops(where).count("implies") <= 1
    default = "normally" in _ops(where) and "after" not in _ops(where) and ("implies", 1) not in where \
      and all(w[0] in ("forall", "and", "normally") or w == ("implies", 2) for w in where)
    if default:
      rep.unsupported("defeasible_text_effect", path, node,
                      "a default-qualified effect; only strict text effects are in the first fragment")
    elif "after" in _ops(where):
      rep.invalid("nested_after", path, node, "after does not nest")
    elif ("implies", 1) in where:
      rep.invalid("after_in_antecedent", path, node, "after does not stand in a precondition")
    elif not allowed:
      rep.invalid("after_position", path, node,
                  "after stands at the top of a unit, under forall and at most one implies consequent; it is not negated, defeasible or existential")
    head = node[2]
    if isinstance(head, list) and head and head[0] == "normally":
      rep.unsupported("defeasible_text_effect", path + [2], head,
                      "a defeasible text effect; only strict text effects are in the first fragment")
    elif isinstance(head, list) and head and head[0] == "exists":
      rep.unsupported("existential_effect_head", path + [2], head,
                      "an existential effect head: its witness and scope are outside the first executable fragment "
                      "(it may name a new object or an existing one)")
    elif _contains(head, {"after"}):
      pass  # reported above as nested_after at the inner node
    elif isinstance(head, list) and _contains(head, set(STATIC)) and not _contains(head, set(ACTION_OPERATORS)):
      rep.unsupported("mixed_scope_rule", path + [2], head,
                      "an effect head with a static atom: an action does not change stable types or stated routes")
    elif not _signed_state_literals(head):
      rep.invalid("after_head", path + [2], head, "an effect head is a conjunction of signed state literals")
  # executable: only in the antecedent of a necessary-condition law
  restriction = False
  for op, path, where, node in [x for x in found if x[0] == "executable"]:
    ok = ("implies", 1) in where and _ops(where).count("implies") == 1 \
      and all(w[0] in ("forall", "and") or w == ("implies", 1) for w in where)
    asserted = ("implies", 1) not in where \
      and all(w[0] in ("forall", "and", "normally") or w == ("implies", 2) for w in where)
    if ok:
      restriction = True
    elif asserted:
      rep.unsupported("unsupported_executability_assertion", path, node,
                      "a fact or a sufficient rule asserting executable; it would bypass the library's mechanical "
                      "checks. It is kept and not read as a permission")
    else:
      rep.invalid("executable_position", path, node,
                  "in a source, executable stands in the antecedent of a necessary-condition law, unnegated")
  if restriction:
    # each restriction's own implication: a valid first one does not hide a second
    for op, path, where, imp in [x for x in found if x[0] == "implies"]:
      ant = imp[1]
      items = ant[1:] if isinstance(ant, list) and ant and ant[0] == "and" else [ant]
      if not any(isinstance(x, list) and x and x[0] == "executable" for x in items):
        continue
      if _contains(imp[2], set(ACTION_OPERATORS)):
        rep.invalid("restriction_consequent", path + [2], imp[2], "the required condition of a restriction is a state formula")
      elif _contains(imp[2], {"="}):
        rep.unsupported("unsupported_restriction_scope", path, imp,
                        "a restriction on an action slot (an equality on the actor, the means or the tool), not a state condition",
                        detail="action_slot_constraint")
      elif not _required(imp[2]):
        rep.unsupported("unsupported_restriction_scope", path + [2], imp[2],
                        "the required condition of a restriction is a signed state literal or a conjunction of them, "
                        "with no quantifier, disjunction or implication (A4.2)")
  # can: a head (availability, denial) or, in an antecedent, a capability restriction
  heads, denials = 0, 0
  for op, path, where, node in [x for x in found if x[0] == "can"]:
    names = _ops(where)
    if "state_law" in names:
      continue  # reported as state_law_content
    if ("implies", 1) in where:
      rep.unsupported("unsupported_capability_restriction", path, node,
                      "a necessary condition on underlying capability (can in an antecedent); "
                      "it is not an operational restriction and is not compiled as a sufficient rule")
      continue
    if "exists" in names:
      rep.unsupported("existential_availability_head", path, node,
                      "an existential inside an availability: over situations its witness may depend on the situation")
      continue
    if "after" in names or "or" in names:
      rep.invalid("can_position", path, node, "can stands as the head of an availability or a denial")
      continue
    if names.count("not") > 1 or (names.count("not") == 1 and "normally" in names[names.index("not"):]):
      rep.invalid("can_position", path, node, "a denial is not(can(...)), not a negated default or a double negation")
      continue
    heads += 1
    denials += names.count("not")
  effects = ops.count("after")
  # existential head of a standing law
  for op, path, where, node in laws:
    body = node[1]
    while isinstance(body, list) and body and body[0] == "forall" and len(body) == 3:
      body = body[2]
    head = body[2] if isinstance(body, list) and body and body[0] == "implies" and len(body) == 3 else body
    if _contains(head, {"exists"}):
      rep.unsupported("existential_state_law_head", path, node,
                      "an existential head in a standing law is outside the first executable fragment")
  if not rep.has("invalid") and not rep.has("unsupported") and (effects or restriction or heads):
    if _law_shape(f) is None:
      rep.unsupported("unsupported_law_form", [2, 2], f,
                      "an action law is forall* over HEAD or implies(CONDITION, HEAD); CONDITION is a conjunction of "
                      "signed state literals under exists; this formula has another structure and is not normalized")
  if effects and (heads or restriction):
    rep.invalid("mixed_law_forms", [2, 2], f,
                "one unit holds one law form; give the permission and the effect of a joint sentence as two units")
  if restriction and heads:
    rep.invalid("mixed_law_forms", [2, 2], f, "one unit holds one law form")
  if effects:
    return "effect"
  if restriction:
    return "restriction"
  if heads:
    if denials and denials != heads:
      rep.invalid("mixed_law_forms", [2, 2], f, "a unit is an availability or a denial, not both")
    return "denial" if denials else "availability"
  cans = [x for x in found if x[0] == "can"]
  if cans and all(("implies", 1) in x[2] for x in cans):
    return "restriction"    # an unsupported capability restriction
  if cans:
    return "availability"   # an unsupported can form; the diagnostics say which
  if laws:
    return "state_law"
  return "description_initial" if "fluent" in walk.kinds else "description_static"


def _is_atom(f, extra=()):
  return isinstance(f, list) and bool(f) and (f[0] in FLUENTS or f[0] in STATIC or f[0] == "=" or f[0] in extra)


def in_fragment(f, extra=()):
  """The positive grammar of goals and law conditions.

    G := ATOM | not(ATOM) | and(G, ...) | exists(V, G)

  ATOM is a fluent, static or equality atom, plus the operators in `extra`
  (executable in a verify final formula).  Negation reaches atoms
  only: not(and(...)) is a disjunction and not(exists ...) is a universal.
  """
  if not (isinstance(f, list) and f):
    return False
  if f[0] == "and":
    return all(in_fragment(x, extra) for x in f[1:])
  if f[0] == "exists" and len(f) == 3:
    return in_fragment(f[2], extra)
  if f[0] == "not" and len(f) == 2:
    return _is_atom(f[1], extra)
  return _is_atom(f, extra)


def _required(f):
  """REQUIRED := LITERAL | and(REQUIRED, ...); LITERAL := ATOM | not(ATOM).

  The required condition of a restriction (A4.2).  No exists: a required
  condition introduces no fresh witness.  ATOM is a fluent or static atom.
  """
  if not (isinstance(f, list) and f):
    return False
  if f[0] == "and":
    return all(_required(x) for x in f[1:])
  if f[0] == "not" and len(f) == 2:
    f = f[1]
  return isinstance(f, list) and bool(f) and (f[0] in FLUENTS or f[0] in STATIC)


def _law_shape(f):
  """The supported law grammar; the head kind, or None.

    LAW  := forall(V, LAW) | and(LAW, ...) | implies(COND, HEAD) | HEAD
          | implies(ANTECEDENT, REQUIRED)            a restriction
    HEAD := forall(V, HEAD) | and(HEAD, ...) | can | normally(can) | not(can) | after(A, EFFECT)
    ANTECEDENT := executable | and(executable, signed state literals ...)

  COND is `in_fragment`.  REQUIRED is `_required` and EFFECT is
  `_signed_state_literals`; `_recognize` checks both for every law.
  """
  if not (isinstance(f, list) and f):
    return None
  if f[0] == "forall" and len(f) == 3:
    return _law_shape(f[2])
  if f[0] == "and":
    kinds = {_law_shape(x) for x in f[1:]}
    return kinds.pop() if len(kinds) == 1 and None not in kinds else None
  if f[0] == "implies" and len(f) == 3:
    ant = f[1]
    items = ant[1:] if isinstance(ant, list) and ant and ant[0] == "and" else [ant]
    execs = [x for x in items if isinstance(x, list) and x and x[0] == "executable"]
    if execs:
      rest = [x for x in items if x not in execs]
      return "restriction" if len(execs) == 1 and all(in_fragment(x) for x in rest) else None
    return _head_shape(f[2]) if in_fragment(ant) else None
  return _head_shape(f)


def _head_shape(f):
  if not (isinstance(f, list) and f):
    return None
  if f[0] == "forall" and len(f) == 3:
    return _head_shape(f[2])
  if f[0] == "and":
    kinds = {_head_shape(x) for x in f[1:]}
    return kinds.pop() if len(kinds) == 1 and None not in kinds else None
  if f[0] == "can":
    return "availability"
  if f[0] == "normally" and len(f) == 2 and isinstance(f[1], list) and f[1] and f[1][0] == "can":
    return "availability"
  if f[0] == "not" and len(f) == 2 and isinstance(f[1], list) and f[1] and f[1][0] == "can":
    return "denial"
  if f[0] == "after":
    return "effect"
  return None


# ---------------------------------------------------------------------------
# queries


def _check_steps(s, rep, path):
  ok = isinstance(s, list) and len(s) == 3 and s[0] == "steps" and s[1] in STEP_COMPARISONS \
    and isinstance(s[2], int) and not isinstance(s[2], bool) and s[2] >= 0
  if not ok:
    rep.invalid("step_constraint", path, s,
                "a step constraint is [\"steps\", \"at_most\" | \"exactly\", N] with a non-negative integer N")
  return ok


def _split_witnesses(f, rep, path):
  """An existential shared by goal conjuncts has one surrounding exists (A3.3)."""
  if not (isinstance(f, list) and f):
    return
  if f[0] == "and":
    seen = {}
    for i in range(1, len(f)):
      x = f[i]
      if isinstance(x, list) and len(x) == 3 and x[0] == "exists" and is_var(x[1]):
        if x[1] in seen:
          rep.invalid("split_goal_witness", path + [i], x,
                      "variable %s is bound by two separate exists in one conjunction; an object shared by "
                      "goal conjuncts has one surrounding exists, and different objects have different variables" % x[1])
        seen[x[1]] = i
  for i in range(1, len(f)):
    _split_witnesses(f[i], rep, path + [i])


def _witnesses(f, out=None):
  out = [] if out is None else out
  if isinstance(f, list) and f:
    if f[0] == "exists" and len(f) == 3:
      out.append(f[1])
    for x in f[1:]:
      _witnesses(x, out)
  return out


def validate_query(pkg, identity=None, profile=PROFILE, worlds=None, planning_root=None, ambient=None, knower=None):
  """Validate one query package and its selection fields.  Returns a dict:

    id, kind, goal, steps, sequence, variable, witnesses, planning_root, diagnostics, status

  `planning_root` names a declared world of `worlds` (default ["W0"]); none
  given is the last declared world.  `ambient` and `knower` name entities of
  the source identity map.
  """
  rep = Report(pkg[1] if isinstance(pkg, list) and len(pkg) > 1 and isinstance(pkg[1], str) else None)
  worlds = list(worlds or DEFAULT_WORLDS)
  out = {"id": rep.unit, "kind": None, "goal": None, "steps": None, "sequence": None,
         "variable": None, "witnesses": [], "planning_root": planning_root if planning_root is not None else worlds[-1],
         "diagnostics": rep.items, "status": "invalid"}
  if planning_root is not None and planning_root not in worlds:
    rep.invalid("unknown_planning_root", ["planning_root"], planning_root,
                "planning_root %r names no declared world of the source (%s)" % (planning_root, ", ".join(worlds)))
  if ambient is not None and (identity is None or ambient not in identity):
    rep.invalid("unknown_ambient", ["ambient"], ambient, "ambient %r names no location entity of the source" % ambient)
  if knower is not None and (identity is None or knower not in identity):
    rep.invalid("unknown_knower", ["knower"], knower, "knower %r names no entity of the source" % knower)
  if isinstance(pkg, list) and pkg and pkg[0] == "and":
    rep.invalid("query_count", [], pkg, "compile_query takes one query package")
    return out
  if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "@id" and isinstance(pkg[1], str)
          and UNIT_ID.match(pkg[1])):
    rep.invalid("package", [], pkg, "a package is [\"@id\", id, PACKAGE]")
    return out
  q = pkg[2]
  if not (isinstance(q, list) and q and isinstance(q[0], str)):
    rep.invalid("package", [2], q, "a query package is one of %s" % ", ".join(QUERY_PACKAGES))
    return out
  if q[0] == "holds":
    rep.invalid("source_in_query", [2], q, "holds(W, F) is a source package; a query never adds to the source")
    return out
  if q[0] not in QUERY_PACKAGES:
    rep.invalid("package", [2], q, "a query package is one of %s" % ", ".join(QUERY_PACKAGES))
    return out
  kind = q[0]
  if profile == ORDINARY and kind in ("plan", "reachable", "verify"):
    rep.invalid("action_syntax_in_ordinary_profile", [2], q,
                "%s belongs to the action profile; the ordinary profile does not accept it" % kind)
    return out
  out["kind"] = kind
  walk = _Walk(rep, identity, profile, query=True)
  goal, bound = None, set()
  if kind in ("plan", "reachable"):
    if len(q) not in (2, 3):
      rep.invalid("arity", [2], q, "%s takes a goal and an optional step constraint" % kind)
      return out
    goal = q[1]
    if len(q) == 3 and _check_steps(q[2], rep, [2, 2]):
      out["steps"] = {"comparison": q[2][1], "n": q[2][2]}
  elif kind == "verify":
    if len(q) != 3 or not isinstance(q[1], list):
      rep.invalid("arity", [2], q, "verify takes a list of action terms and a final formula")
      return out
    for i, a in enumerate(q[1]):
      r = Report(rep.unit)
      if check_action(a, set(), r, [2, 1, i], identity):
        pass
      for d in r.items:
        if d.get("code") == "unbound_variable":
          d["code"] = "sequence_not_ground"
          d["message"] = "a supplied action sequence is ground: " + d["message"]
      rep.items.extend(r.items)
    out["sequence"] = q[1]
    goal = q[2]
  elif kind == "question":
    if len(q) != 2:
      rep.invalid("arity", [2], q, "question takes one formula")
      return out
    goal = q[1]
  else:  # ask
    if len(q) != 3 or not is_var(q[1]):
      rep.invalid("arity", [2], q, "ask takes a variable and a formula")
      return out
    out["variable"], goal, bound = q[1], q[2], {q[1]}
    if WORLD.match(q[1]):
      rep.invalid("reserved_variable", [2, 1], q[1], "%s is a world name; an asked variable has another name" % q[1])
  gpath = [2, 1] if kind in ("plan", "reachable", "question") else [2, 2]
  walk.formula(goal, bound, gpath, ())
  for op, path, where, node in walk.found:
    if op == "can":
      rep.invalid("can_in_query", path, node,
                  "can is a source-only form (the head of a source action rule or of a denial); a query asks executable")
    elif op == "after":
      rep.invalid("after_in_query", path, node, "after does not stand in a query; verify asks about a supplied sequence")
    elif op == "state_law":
      rep.invalid("state_law_position", path, node, "state_law does not stand in a query")
    elif op == "@time":
      rep.invalid("time_wrapper", path, node, "@time is not part of the action profile")
  if "event" in walk.kinds:
    rep.invalid("event_form_in_query", gpath, goal, "a query of the action profile uses the state predicates, not the event form")
  if kind == "ask" and not _mentions(goal, out["variable"]):
    rep.invalid("ask_variable", gpath, goal, "the asked variable %s does not occur in the formula" % out["variable"])
  if not rep.has("invalid"):
    if kind in ("plan", "reachable", "verify"):
      _split_witnesses(goal, rep, gpath)
      extra = ("executable",) if kind == "verify" else ()
      if not in_fragment(goal, extra):
        rep.unsupported("unsupported_goal_form", gpath, goal,
                        "the goal fragment is G := ATOM | not(ATOM) | and(G, ...) | exists(V, G)%s; negation reaches "
                        "atoms only, so a negated conjunction (a disjunction) and a negated exists (a universal) are outside it"
                        % ("" if kind != "verify" else ", where ATOM includes executable"))
  out["goal"] = goal
  out["witnesses"] = _witnesses(goal)
  out["status"] = "invalid" if rep.has("invalid") else "unsupported" if rep.has("unsupported") else "supported"
  return out


def _mentions(f, v):
  if isinstance(f, list):
    return any(_mentions(x, v) for x in f)
  return f == v


# ---------------------------------------------------------------------------
# checks over the units of one source


def _unify(a, ua, b, ub):
  """Whether two flat action terms of different source scopes can name one action.

  Variables are standardized apart by their unit (the same letter in two
  units is two variables); a variable repeated inside one term keeps its
  constraint.  Terms are flat, so a union-find over the slots is complete.
  """
  if a[0] != b[0] or len(a) != len(b):
    return False
  parent = {}

  def find(x):
    parent.setdefault(x, x)
    while parent[x] != x:
      parent[x] = parent[parent[x]]
      x = parent[x]
    return x

  def node(t, unit):
    return ("var", unit, t) if is_var(t) else ("const", t)

  for x, y in zip(a[1:], b[1:]):
    rx, ry = find(node(x, ua)), find(node(y, ub))
    if rx == ry:
      continue
    if rx[0] == "const" and ry[0] == "const":
      return False
    if rx[0] == "const":
      parent[ry] = rx
    else:
      parent[rx] = ry
  return True


def method_collisions(units):
  """Source units whose verbs differ but whose action terms can name one action.

  `units` are dicts with id, form, action_terms and roots (the Stage-1 action
  roots of the unit).  A collision needs an effect or a restriction (a law),
  another unit with a different set of source verbs, and action terms of the
  two that unify: the law would then apply to the other verb's action (A2.6).
  Different sufficient permissions for one action are alternatives, not a
  collision.  Terms that do not unify (another tool, means or participant)
  are safe.  No disjointness is inferred from differing source conditions.

  Returns {unit id: [{"with", "term", "other_term", "roots", "other_roots"}]}.
  """
  out = {}
  laws = [u for u in units if u.get("form") in ("effect", "restriction") and u.get("roots")]
  for law in laws:
    for u in units:
      if u is law or not u.get("roots") or sorted(u["roots"]) == sorted(law["roots"]):
        continue
      for t in law.get("action_terms") or []:
        for o in u.get("action_terms") or []:
          if _unify(t, "law", o, "other"):
            for x, y, tx, ty in ((law, u, t, o), (u, law, o, t)):
              hit = {"with": y["id"], "term": tx, "other_term": ty,
                     "roots": sorted(x["roots"]), "other_roots": sorted(y["roots"])}
              if hit not in out.setdefault(x["id"], []):
                out[x["id"]].append(hit)
  return out
