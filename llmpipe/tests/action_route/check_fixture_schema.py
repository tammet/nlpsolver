"""Structural check of the WP02 gold fixtures. No model, no GK.

The check runs on the effective cases that `fixture_materialize` builds,
not on the record files' partial variant entries.  It verifies what a
reviewer should not have to count by hand:

  - every record has the schema fields in order and covers its C ids;
  - every effective unit is complete (text and a Stage-1 projection for a
    text record; a Stage-2 package for every record) and every concrete
    entity id it mentions is declared;
  - every Stage-2 formula is well formed: fixed arities for the connectives
    and quantifiers, the wrapped predicates with their arities, the five
    constructors with theirs, `can` with the actor equal to the action's
    actor slot, every variable bound, no Skolem term, a lexical property
    value; a supported unit uses only the action-profile vocabulary, an
    unsupported unit may also use the ordinary event form;
  - every text unit's Stage-1 projection holds what the route consumes: the
    concrete entities its formula names and, for an action unit, the action
    roots and roles; every unit sentence occurs in the case passage and every
    passage sentence belongs to a unit; the passage holds no question;
  - a view fits its package, a seed equals the bound and the search cap, an
    expectation does not forbid its own answer, a replay reference resolves
    to a query with a final goal;
  - every query is one of the A3.3 packages with a well-formed bound, has a
    view, a seed when it discovers, and an expectation with evidence and a
    known outcome or answer;
  - every candidate is ground and has a known verdict.

It does not check that an expectation is true; that is REVIEW.md's job.
The mutation check `check_fixture_mutations.py` proves that each of these
rejections is real.
"""

import glob
import json
import os
import re

import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fixture_materialize as fm

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "fixtures", "cases")

CONSTRUCTORS = {"move": 4, "take": 2, "put_on": 3, "put_in": 3, "change": 4}
FLUENTS = {"is rel2": 3, "has property": 2, "have": 2}
STATIC = {"isa": 2, "connected": 3}
RELS = {"located_at", "on", "in", "holding"}
# ordinary Davidsonian form: predicate -> allowed arities (event var first)
EVENT_PREDS = {"isa": {2}, "has type": {2}, "has actor": {2}, "has target": {2},
               "has source": {2}, "has destination": {2, 3}, "has instrument": {2},
               "has location": {2, 3}, "has recipient": {2}, "has result": {2},
               "has time": {2, 3}, "capability": {1}}
QUANTIFIERS = {"forall", "exists"}
QUERY_PACKAGES = {"plan", "reachable", "verify", "question", "ask"}
VIEWS = {"discovery", "snapshot", "verify", "adapter", "none", "ordinary"}
ASU_TYPES = {"real", "situation", "strict_rule", "normal_rule", "query"}
CATEGORIES = {"person", "animal", "plant", "place", "organization", "artifact",
              "substance", "event", "abstract"}
MODES = {"event", "habitual", "capability", "necessity", "obligation", "volition",
         "intention", "expectation", "speech_act"}
READINGS = {"availability", "restriction", "effect", "occurrence"}
SCOPES = {"initial", "static", "standing", "availability", "restriction", "effect",
          "denial", "occurrence", "availability+effect"}
# unsupported_translation reasons: A5.3 plus the names decided in REVIEW.md
REASONS = {"ambiguous_state_policy", "method_collision", "ambiguous_state_scope",
           "mixed_scope_rule", "unsupported_restriction_scope",
           "unsupported_capability_restriction", "unsupported_location_granularity",
           "unsupported_transport_dependency", "unexpressible_temporal_permission_scope",
           "unsupported_stored_state_law", "existential_state_law_head",
           "existential_availability_head", "unsupported_action_kind",
           "defeasible_text_effect", "occurrence", "unsupported_relation_policy",
           "unsupported_confidence_form", "unsupported_contextual_location"}
BACKEND_REASONS = {"negative_persistence_unavailable"}
OUTCOMES = {"source_compiled", "plan_found", "goal_already_holds", "verification_result",
            "not_found", "candidate_not_validated", "inconsistent_action_state",
            "unsupported_backend_requirement", "unsupported_translation",
            "translation_invalid", "call_limit", "model_timeout", "prover_timeout",
            "prover_error", "backend_incompatible", "insufficient_search_allowance",
            "ordinary_result"}
ANSWERS = {"Yes", "No", "Unknown", "contested", "none"}
CAPABILITIES = {"negative_persistence", "shared_source_confidence"}
VERDICTS = {"valid", "invalid", "not_checked", "contested", "inconsistent_action_state"}
ROLES = {"initial_fact", "static", "standing_law", "availability",
         "restriction_check", "hook", "path_coverage", "denial_consequence",
         "necessity_restriction", "effect", "marker", "frame", "distinct", "denial",
         "derived_no_inertia", "query", "seed", "diagnostic"}
BODY_ABSENT = {"connected", "surface", "isa", "differ", "standard_mode"}
ACTION_SCOPES = {"availability", "restriction", "effect", "occurrence",
                 "availability+effect"}
ROLE_KEYS = {"actor", "target", "source", "destination", "instrument", "location",
             "recipient", "result"}
INSPECTIONS = {"situation_insertion_skolemization"}
PACKAGE_VIEWS = {"plan": {"discovery"}, "reachable": {"discovery"},
                 "verify": {"verify"}, "question": {"snapshot", "ordinary"},
                 "ask": {"snapshot", "ordinary"}}
DEFAULT_SEARCH_CAP = 4
SENTENCE = re.compile(r"(?<=[.?!])\s+")
SITUATIONS = {"named", "shared_current", "successor", "none", "free"}
TOP_FIELDS = ["id", "purpose", "contract", "family", "input_kind", "text",
              "profile", "entities", "units", "queries", "variants",
              "candidates", "support", "explain", "notes"]
# `worlds` is optional; when present it stands after `entities` (encoding v2, migration plan section 9)
TOP_FIELDS_WORLDS = TOP_FIELDS[:TOP_FIELDS.index("entities") + 1] + ["worlds"] + TOP_FIELDS[TOP_FIELDS.index("entities") + 1:]
WORLD = re.compile(r"^W\d+$")
DEFAULT_WORLDS = ["W0"]
TENSES = {"present", "past", "future"}
LOCATION_ROLES = {"provenance", "scope"}
CONTEXT_FIELDS = {"tense", "location", "location_role", "knower"}
VAR = re.compile(r"^[A-Z][A-Z0-9]?$")
CONCRETE = re.compile(r"^.+ \d+$")
LEXICAL = re.compile(r"^[a-z][a-z0-9_ ]*$")
WITNESS = re.compile(r"^sk_[A-Z][A-Z0-9]?$")


class Bad(Exception):
  pass


def is_var(x):
  return isinstance(x, str) and VAR.match(x) is not None


class Ctx(object):
  """What a formula check needs to know about its surroundings."""

  def __init__(self, entities=None, supported=True, witnesses=False, worlds=None):
    self.entities = entities
    self.supported = supported
    self.witnesses = witnesses
    self.worlds = worlds or DEFAULT_WORLDS


def check_term(t, bound, where, ctx):
  """An entity id, a bound variable, a lexical constant, or an action term."""
  if isinstance(t, str):
    if is_var(t):
      if t not in bound:
        raise Bad("%s: unbound variable %s" % (where, t))
      return
    if CONCRETE.match(t):
      if ctx.entities is not None and t not in ctx.entities:
        raise Bad("%s: undeclared entity id %r" % (where, t))
      return
    if WITNESS.match(t):
      if not ctx.witnesses:
        raise Bad("%s: witness constant %s outside a plan" % (where, t))
      return
    if LEXICAL.match(t):
      return
    raise Bad("%s: bad constant %r" % (where, t))
  if isinstance(t, list) and t and t[0] in CONSTRUCTORS:
    check_action(t, bound, where, ctx)
    return
  if isinstance(t, list) and t and t[0] == "sk":
    raise Bad("%s: Skolem terms do not occur in Stage 2" % where)
  raise Bad("%s: bad term %r" % (where, t))


def check_action(a, bound, where, ctx=None):
  ctx = ctx or Ctx()
  if not (isinstance(a, list) and a and a[0] in CONSTRUCTORS):
    raise Bad("%s: not an action term: %r" % (where, a))
  if len(a) - 1 != CONSTRUCTORS[a[0]]:
    raise Bad("%s: %s has arity %d, got %d" % (where, a[0], CONSTRUCTORS[a[0]], len(a) - 1))
  for x in a[1:]:
    if isinstance(x, list):
      raise Bad("%s: nested term in an action slot: %r" % (where, x))
    check_term(x, bound, where, ctx)


def check_atom(f, bound, where, ctx, inside_after):
  p = f[0]
  if not isinstance(p, str):
    raise Bad("%s: bad predicate %r" % (where, p))
  if p in FLUENTS:
    if len(f) - 1 != FLUENTS[p]:
      raise Bad("%s: %s arity" % (where, p))
    if p == "is rel2":
      if not (isinstance(f[1], str) and LEXICAL.match(f[1])):
        raise Bad("%s: bad relation %r" % (where, f[1]))
      if ctx.supported and f[1] not in RELS:
        raise Bad("%s: unclassified relation %s in a supported unit" % (where, f[1]))
      args = f[2:]
    elif p == "has property":
      if is_var(f[1]) or not (isinstance(f[1], str) and LEXICAL.match(f[1])):
        raise Bad("%s: property value must be a lexical constant, got %r" % (where, f[1]))
      args = f[2:]
    else:
      args = f[1:]
    for x in args:
      check_term(x, bound, where, ctx)
    return
  if p in STATIC:
    if len(f) - 1 != STATIC[p]:
      raise Bad("%s: %s arity" % (where, p))
    if p == "isa":
      if not (isinstance(f[1], str) and LEXICAL.match(f[1])):
        raise Bad("%s: bad class %r" % (where, f[1]))
      check_term(f[2], bound, where, ctx)
    else:
      check_term(f[1], bound, where, ctx)
      check_term(f[2], bound, where, ctx)
      if not (isinstance(f[3], str) and LEXICAL.match(f[3])):
        raise Bad("%s: bad means %r" % (where, f[3]))
    return
  if p == "can":
    if len(f) != 3:
      raise Bad("%s: can arity" % where)
    check_term(f[1], bound, where, ctx)
    check_action(f[2], bound, where, ctx)
    if f[1] != f[2][1]:
      raise Bad("%s: can actor %r differs from the action's actor %r" % (where, f[1], f[2][1]))
    return
  if p == "executable":
    if len(f) != 2:
      raise Bad("%s: executable arity" % where)
    check_action(f[1], bound, where, ctx)
    return
  if p == "after":
    if len(f) != 3:
      raise Bad("%s: after arity" % where)
    if inside_after:
      raise Bad("%s: nested after" % where)
    check_action(f[1], bound, where, ctx)
    check_formula(f[2], bound, where, ctx, inside_after=True)
    return
  if p == "state_law":
    if len(f) != 2:
      raise Bad("%s: state_law arity" % where)
    check_formula(f[1], bound, where, ctx, inside_after)
    return
  if p in EVENT_PREDS and not ctx.supported:
    if len(f) - 1 not in EVENT_PREDS[p]:
      raise Bad("%s: %s arity" % (where, p))
    for x in f[1:]:
      if isinstance(x, str) and LEXICAL.match(x) and not is_var(x):
        continue
      check_term(x, bound, where, ctx)
    return
  raise Bad("%s: unknown predicate %s" % (where, p))


def check_formula(f, bound, where, ctx=None, inside_after=False):
  ctx = ctx or Ctx()
  if not (isinstance(f, list) and f):
    raise Bad("%s: not a formula: %r" % (where, f))
  h = f[0]
  if h in QUANTIFIERS:
    if len(f) != 3 or not is_var(f[1]):
      raise Bad("%s: bad quantifier %r" % (where, f[:2]))
    if WORLD.match(f[1]):
      raise Bad("%s: %s is a world name; a variable has another name (reserved_variable)" % (where, f[1]))
    check_formula(f[2], bound | {f[1]}, where, ctx, inside_after)
    return
  if h in ("not", "normally"):
    if len(f) != 2:
      raise Bad("%s: %s takes one operand" % (where, h))
    check_formula(f[1], bound, where, ctx, inside_after)
    return
  if h == "implies":
    if len(f) != 3:
      raise Bad("%s: implies takes two operands" % where)
    for g in f[1:]:
      check_formula(g, bound, where, ctx, inside_after)
    return
  if h in ("and", "or"):
    if len(f) < 3:
      raise Bad("%s: %s needs at least two operands" % (where, h))
    for g in f[1:]:
      check_formula(g, bound, where, ctx, inside_after)
    return
  if h == "@time":
    if len(f) != 3 or not isinstance(f[1], str):
      raise Bad("%s: bad @time" % where)
    check_formula(f[2], bound, where, ctx, inside_after)
    return
  if h == "=":
    if len(f) != 3:
      raise Bad("%s: = takes two terms" % where)
    for x in f[1:]:
      check_term(x, bound, where, ctx)
    return
  check_atom(f, bound, where, ctx, inside_after)


def check_package(pkg, where, ctx=None):
  """["@id", id, PACKAGE] for a source unit."""
  ctx = ctx or Ctx()
  if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "@id" and isinstance(pkg[1], str)):
    raise Bad("%s: not an @id package" % where)
  body = pkg[2]
  if not (isinstance(body, list) and body):
    raise Bad("%s: empty package" % where)
  if body[0] == "and":
    if not (len(body) == 3 and isinstance(body[2], list) and len(body[2]) == 3
            and body[2][0] == "@p" and body[2][1] == pkg[1]
            and isinstance(body[2][2], (int, float)) and not isinstance(body[2][2], bool)
            and 0 <= body[2][2] <= 1):
      raise Bad("%s: a confidence package is [and, holds-package, [@p, id, p]]" % where)
    body = body[1]
  if not (isinstance(body, list) and len(body) == 3 and body[0] == "holds"):
    raise Bad("%s: source package must be holds(W, F)" % where)
  if body[1] not in ctx.worlds:
    raise Bad("%s: holds(%r, F) names no declared world (%s)" % (where, body[1], ", ".join(ctx.worlds)))
  check_formula(body[2], set(), where, ctx)


def check_steps(s, where):
  if not (isinstance(s, list) and len(s) == 3 and s[0] == "steps"
          and s[1] in ("at_most", "exactly")
          and isinstance(s[2], int) and not isinstance(s[2], bool) and s[2] >= 0):
    raise Bad("%s: bad steps item %r" % (where, s))


def _has_can(f):
  if isinstance(f, list):
    return (bool(f) and f[0] == "can") or any(_has_can(x) for x in f)
  return False


def check_query(pkg, where, ctx=None):
  ctx = ctx or Ctx()
  if not (isinstance(pkg, list) and len(pkg) == 3 and pkg[0] == "@id" and isinstance(pkg[1], str)):
    raise Bad("%s: not an @id package" % where)
  q = pkg[2]
  if not (isinstance(q, list) and q and q[0] in QUERY_PACKAGES):
    raise Bad("%s: unknown query package %r" % (where, q[:1] if isinstance(q, list) else q))
  if _has_can(q):
    raise Bad("%s: can is a source-only form; a query asks executable (encoding v2)" % where)
  if q[0] in ("plan", "reachable"):
    if len(q) not in (2, 3):
      raise Bad("%s: plan/reachable arity" % where)
    check_formula(q[1], set(), where, ctx)
    if len(q) == 3:
      check_steps(q[2], where)
  elif q[0] == "verify":
    if len(q) != 3 or not isinstance(q[1], list):
      raise Bad("%s: verify arity" % where)
    for a in q[1]:
      check_action(a, set(), where, ctx)
    check_formula(q[2], set(), where, ctx)
  elif q[0] == "question":
    if len(q) != 2:
      raise Bad("%s: question takes one formula" % where)
    check_formula(q[1], set(), where, ctx)
  elif q[0] == "ask":
    if len(q) != 3 or not is_var(q[1]):
      raise Bad("%s: ask takes a variable and a formula" % where)
    if WORLD.match(q[1]):
      raise Bad("%s: %s is a world name; an asked variable has another name (reserved_variable)" % (where, q[1]))
    check_formula(q[2], {q[1]}, where, ctx)


def concrete_ids(f, out=None):
  """The concrete entity ids (`name N`) a formula mentions."""
  out = set() if out is None else out
  if isinstance(f, list):
    for x in f[1:] if f and f[0] == "@id" else f:
      concrete_ids(x, out)
  elif isinstance(f, str) and CONCRETE.match(f):
    out.add(f)
  return out


def check_stage1_consumed(u, where):
  """A text unit's projection holds the identities and actions the route reads."""
  s1 = u["stage1"]
  have = {e["id"] for e in s1.get("entities", []) if e.get("type") == "concrete"}
  lost = sorted(concrete_ids(u["stage2"][2]) - have)
  if lost:
    raise Bad("%s: stage1 lacks the concrete entities %s of its formula" % (where, lost))
  action_unit = u["scope"] in ACTION_SCOPES or "action_reading" in s1
  if action_unit:
    if "action_reading" not in s1:
      raise Bad("%s: an action unit needs action_reading" % where)
    acts = s1.get("actions")
    if not acts:
      raise Bad("%s: an action unit needs its stage1 actions" % where)
    for a in acts:
      if not a.get("root", "").strip() or not isinstance(a.get("roles"), dict):
        raise Bad("%s: a stage1 action needs a root and roles" % where)
      extra = sorted(set(a["roles"]) - ROLE_KEYS)
      if extra:
        raise Bad("%s: %s is not a Stage-1 semantic role" % (where, extra))
      generic = {e["id"] for e in s1.get("entities", []) if e.get("type") == "generic"}
      fillers = [v for v in a["roles"].values() if v in generic]
      if len(fillers) != len(set(fillers)):
        raise Bad("%s: two roles name the same generic mention; number the mentions" % where)


def check_stage1(s1, where, entities):
  if not isinstance(s1, dict):
    raise Bad("%s: stage1 must be an object" % where)
  if s1.get("type") not in ASU_TYPES:
    raise Bad("%s: stage1 type %r" % (where, s1.get("type")))
  for e in s1.get("entities", []):
    if not (isinstance(e, dict) and isinstance(e.get("id"), str)):
      raise Bad("%s: bad stage1 entity %r" % (where, e))
    if e.get("type") not in ("concrete", "generic"):
      raise Bad("%s: stage1 entity %s needs type concrete|generic" % (where, e["id"]))
    if e["type"] == "concrete" and e["id"] not in entities:
      raise Bad("%s: stage1 concrete entity %r not declared" % (where, e["id"]))
    if "category" in e and e["category"] not in CATEGORIES:
      raise Bad("%s: stage1 category %r" % (where, e["category"]))
  for a in s1.get("actions", []):
    if not (isinstance(a, dict) and isinstance(a.get("root"), str)):
      raise Bad("%s: bad stage1 action %r" % (where, a))
    if a.get("mode") not in MODES:
      raise Bad("%s: stage1 action mode %r" % (where, a.get("mode")))
    if "roles" in a and not isinstance(a["roles"], dict):
      raise Bad("%s: stage1 roles must be an object" % where)
  if "action_reading" in s1 and s1["action_reading"] not in READINGS:
    raise Bad("%s: action_reading %r" % (where, s1["action_reading"]))


def check_clauses(cl, where):
  if not isinstance(cl, dict):
    raise Bad("%s: clauses must be an object" % where)
  for key in ("must_have", "must_not_have"):
    for p in cl.get(key, []):
      if p.get("role") not in ROLES and p.get("role") != "*":
        raise Bad("%s: clause role %r" % (where, p.get("role")))
      if "situation" in p and p["situation"] not in SITUATIONS:
        raise Bad("%s: clause situation %r" % (where, p["situation"]))
      if "sign" in p and p["sign"] not in ("+", "-"):
        raise Bad("%s: clause sign %r" % (where, p["sign"]))
      if "body_absent" in p and not (isinstance(p["body_absent"], list) and p["body_absent"]
                                     and set(p["body_absent"]) <= BODY_ABSENT):
        raise Bad("%s: body_absent is a list of static predicate names from %s" % (where, sorted(BODY_ABSENT)))
      if "confidence" in p and (isinstance(p["confidence"], bool) or not isinstance(p["confidence"], (int, float))
                                or not 0 < p["confidence"] <= 1):
        raise Bad("%s: a pattern confidence is a number in (0, 1]" % where)


def check_worlds(worlds, where):
  """None (the one world W0) or a non-empty list of distinct world names, in narrative order."""
  if worlds is None:
    return DEFAULT_WORLDS
  if not (isinstance(worlds, list) and worlds and all(isinstance(w, str) and WORLD.match(w) for w in worlds)):
    raise Bad("%s: worlds is a non-empty list of world names W0, W1, ..., got %r" % (where, worlds))
  if len(set(worlds)) != len(worlds):
    raise Bad("%s: worlds repeats a name: %r" % (where, worlds))
  return worlds


def check_context(c, w, scope, entities):
  """A unit's context record (migration plan section 9): only on an initial description."""
  if not isinstance(c, dict) or not c or set(c) - CONTEXT_FIELDS:
    raise Bad("%s: a context record has some of the fields %s, got %r" % (w, sorted(CONTEXT_FIELDS), c))
  if scope != "initial":
    raise Bad("%s: a context record qualifies an initial description, not a %s unit" % (w, scope))
  if "tense" in c and c["tense"] not in TENSES:
    raise Bad("%s: context tense %r" % (w, c["tense"]))
  if "location_role" in c and c["location_role"] not in LOCATION_ROLES:
    raise Bad("%s: context location_role %r is not one of %s" % (w, c["location_role"], sorted(LOCATION_ROLES)))
  if "location_role" in c and "location" not in c:
    raise Bad("%s: a location_role without a location" % w)
  for k in ("location", "knower"):
    if k in c and (not isinstance(c[k], str) or c[k] not in (entities or {})):
      raise Bad("%s: context %s %r names no entity of the case" % (w, k, c[k]))


def check_units(units, where, kind="text", entities=None, worlds=None):
  seen = set()
  for u in units:
    if not isinstance(u, dict) or not isinstance(u.get("id"), str):
      raise Bad("%s: a unit without id" % where)
    w = "%s/%s" % (where, u["id"])
    if u["id"] in seen:
      raise Bad("%s: duplicate unit id" % w)
    seen.add(u["id"])
    for k in ("stage2", "scope", "syntax", "compile"):
      if k not in u:
        raise Bad("%s: missing %s" % (w, k))
    if kind == "text":
      if not isinstance(u.get("text"), str) or not u["text"].strip():
        raise Bad("%s: missing text" % w)
      if not isinstance(u.get("stage1"), dict):
        raise Bad("%s: missing stage1 projection" % w)
    if "stage1" in u:
      check_stage1(u["stage1"], w, entities if entities is not None else {})
    if u["scope"] not in SCOPES:
      raise Bad("%s: scope %r" % (w, u["scope"]))
    if u["syntax"] != "supported" and not (isinstance(u["syntax"], dict) and "unsupported" in u["syntax"]):
      raise Bad("%s: syntax must be 'supported' or {'unsupported': reason}" % w)
    c = u["compile"]
    supported = c == "supported"
    if not supported:
      if not (isinstance(c, dict) and c.get("unsupported") in REASONS):
        raise Bad("%s: compile must be 'supported' or {'unsupported': <known reason>}, got %r" % (w, c))
    ctx = Ctx(entities=entities, supported=supported, worlds=worlds)
    check_package(u["stage2"], w, ctx)
    if "context" in u:
      check_context(u["context"], w, u["scope"], entities)
    if u["stage2"][1] != u["id"]:
      raise Bad("%s: @id does not match unit id" % w)
    if kind == "text":
      check_stage1_consumed(u, w)
    if "clauses" in u:
      if not supported and u["clauses"].get("must_have"):
        raise Bad("%s: an unsupported unit compiles to no clauses; use `inspection`" % w)
      check_clauses(u["clauses"], w)
    if "inspection" in u:
      ins = u["inspection"]
      if not isinstance(ins, dict) or ins.get("operation") not in INSPECTIONS:
        raise Bad("%s: inspection needs a known operation" % w)
      check_clauses(ins, w + "/inspection")


def check_expect(e, where):
  if not isinstance(e, dict):
    raise Bad("%s: expect must be an object" % where)
  if not isinstance(e.get("evidence"), str) or not e["evidence"].strip():
    raise Bad("%s: expect needs evidence" % where)
  if not any(k in e for k in ("answer", "outcome", "eligible_candidates")):
    raise Bad("%s: expect needs answer or outcome" % where)
  if "outcome" in e and e["outcome"] not in OUTCOMES:
    raise Bad("%s: outcome %r" % (where, e["outcome"]))
  if "reason" in e and e["reason"] not in REASONS | BACKEND_REASONS:
    raise Bad("%s: reason %r" % (where, e["reason"]))
  if "answer" in e and e["answer"] not in ANSWERS and not CONCRETE.match(str(e["answer"])):
    raise Bad("%s: answer %r" % (where, e["answer"]))
  for k in ("forbidden_answers", "forbidden_outcomes"):
    if k in e and not isinstance(e[k], list):
      raise Bad("%s: %s must be a list" % (where, k))
  if "answer" in e and e["answer"] in e.get("forbidden_answers", []):
    raise Bad("%s: the expectation forbids its own answer" % where)
  if "outcome" in e and e["outcome"] in e.get("forbidden_outcomes", []):
    raise Bad("%s: the expectation forbids its own outcome" % where)
  if "on_validated_backend" in e:
    check_expect(dict(e["on_validated_backend"], evidence=e["evidence"]), where + "/on_validated_backend")
  for a in e.get("plan", []):
    check_action(a, set(), where + "/plan", Ctx(witnesses=True))


def expected_seed(pk, limits):
  """The seed the bound and the search cap give (A3.3); `none` = no search.

  A stated bound supplies the depth; the default cap of four is for a query
  without a bound.  The same rule as `action_route.search_depth`.
  """
  cap = (limits or {}).get("search_cap", DEFAULT_SEARCH_CAP)
  explicit = bool(limits) and limits.get("explicit", True)
  if len(pk) == 3:
    kind, n = pk[2][1], pk[2][2]
    if explicit and kind == "exactly" and n > cap:
      return "none"
    if explicit:
      n = min(n, cap)   # only a cap the caller imposed shortens a stated bound
  else:
    n = cap
  return "0" if n == 0 else "s^%d(0)" % n


def check_seed(q, pk, where):
  if pk[0] not in ("plan", "reachable"):
    if "seed" in q:
      raise Bad("%s: only a discovery query has a seed" % where)
    return
  limits = q.get("limits")
  if limits is not None:
    cap = limits.get("search_cap") if isinstance(limits, dict) else None
    if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
      raise Bad("%s: limits.search_cap must be a non-negative integer" % where)
  if "seed" not in q:
    raise Bad("%s: a discovery query needs a seed" % where)
  want = expected_seed(pk, limits)
  if q["seed"] != want:
    raise Bad("%s: seed %r; the bound and the cap give %r" % (where, q["seed"], want))


_ALL = {}


def all_effective_cases():
  if not _ALL:
    _ALL.update({c["case"]: c for c in fm.load_all(CASES)})
  return _ALL


def check_replay_context(rc, where, all_cases=None):
  """`{case, variant, query}` names one materialized query with a final goal."""
  if not isinstance(rc, dict) or set(rc) != {"case", "variant", "query"}:
    raise Bad("%s: replay_context is {case, variant, query}" % where)
  cases = dict(all_effective_cases(), **(all_cases or {}))
  target = "%s:%s" % (rc["case"], rc["variant"])
  if target not in cases:
    raise Bad("%s: replay_context names unknown case %s" % (where, target))
  qs = [x for x in cases[target]["queries"] if x["id"] == rc["query"]]
  if not qs:
    raise Bad("%s: replay_context names unknown query %s/%s" % (where, target, rc["query"]))
  pk = (qs[0].get("stage2") or [None, None, [None]])[2]
  if pk[0] not in ("plan", "reachable", "verify"):
    raise Bad("%s: replay_context query %s/%s has no final goal" % (where, target, rc["query"]))


def check_queries(queries, where, entities=None, all_cases=None, worlds=None):
  seen = set()
  for q in queries:
    if not isinstance(q, dict) or not isinstance(q.get("id"), str):
      raise Bad("%s: a query without id" % where)
    w = "%s/%s" % (where, q["id"])
    if q["id"] in seen:
      raise Bad("%s: duplicate query id" % w)
    seen.add(q["id"])
    if any(k in q for k in ("units_add", "units_remove")):
      raise Bad("%s: a query may not change the source" % w)
    if "planning_root" in q and q["planning_root"] not in (worlds or DEFAULT_WORLDS):
      raise Bad("%s: planning_root %r names no declared world" % (w, q["planning_root"]))
    for k in ("ambient", "knower"):
      if k in q and (not isinstance(q[k], str) or q[k] not in (entities or {})):
        raise Bad("%s: %s %r names no entity of the case" % (w, k, q[k]))
    if q.get("view") not in VIEWS:
      raise Bad("%s: view %r" % (w, q.get("view")))
    if q.get("stage2") is None:
      if q["view"] not in ("none", "ordinary", "adapter"):
        raise Bad("%s: a query without stage2 needs view none|ordinary|adapter" % w)
    else:
      ents = entities
      if q.get("undeclared_entities"):
        # a query that deliberately names an unknown entity (c14 Q5) declares
        # it here so the dangling-id check knows the omission is the test
        if q.get("expect", {}).get("outcome") != "translation_invalid":
          raise Bad("%s: undeclared_entities is only for a translation_invalid expectation" % w)
        ents = dict(entities or {}, **{e: "undeclared" for e in q["undeclared_entities"]})
      check_query(q["stage2"], w, Ctx(entities=ents))
      if q["stage2"][1] != q["id"]:
        raise Bad("%s: @id does not match query id" % w)
      pk = q["stage2"][2]
      if q["view"] not in PACKAGE_VIEWS[pk[0]]:
        raise Bad("%s: a %s package does not run in the %s view" % (w, pk[0], q["view"]))
      check_seed(q, pk, w)
    if "replay_context" in q:
      check_replay_context(q["replay_context"], w, all_cases)
    if "expect" not in q:
      raise Bad("%s: no expect" % w)
    check_expect(q["expect"], w)
    for b in q.get("backend", []):
      if b not in CAPABILITIES:
        raise Bad("%s: backend capability %r" % (w, b))
    r = q.get("replay")
    if r not in ("covered", "n/a") and not (isinstance(r, str) and r.startswith("not_checked")):
      raise Bad("%s: replay %r" % (w, r))


def sentences(t):
  return [x.strip() for x in SENTENCE.split(t.strip()) if x.strip()]


def check_passage(case, where):
  """The passage is source-only and agrees with the units, both ways."""
  text = case["text"]
  if "?" in text:
    raise Bad("%s: the passage is source-only; a question belongs to its query" % where)
  if "[" in text:
    raise Bad("%s: the passage holds an editorial note" % where)
  unit_sentences = set()
  for u in case["units"]:
    for x in sentences(u["text"]):
      unit_sentences.add(x)
      if x not in text:
        raise Bad("%s/%s: the unit sentence %r is not in the passage" % (where, u["id"], x))
  if case["units"]:
    for x in sentences(text):
      if x not in unit_sentences:
        raise Bad("%s: the passage sentence %r belongs to no unit" % (where, x))


def check_case(case, kind, all_cases=None):
  where = case["case"]
  ents = case.get("entities", {})
  if not isinstance(ents, dict):
    raise Bad("%s: entities must be an object" % where)
  if kind == "text" and (not isinstance(case.get("text"), str) or not case["text"].strip()):
    raise Bad("%s: a text case needs its text" % where)
  worlds = check_worlds(case.get("worlds"), where)
  check_units(case["units"], where, kind, ents, worlds)
  check_queries(case["queries"], where, ents, all_cases, worlds)
  if kind == "text":
    check_passage(case, where)
  if (kind == "text" and not case["units"] and not any(q.get("stage2") for q in case["queries"])
      and not any(q.get("view") == "ordinary" for q in case["queries"])):
    raise Bad("%s: an empty case" % where)


def check_record(path):
  with open(path) as f:
    d = json.load(f)
  name = os.path.basename(path)[:-5]
  if d.get("id") != name:
    raise Bad("%s: id != file name" % name)
  if list(d.keys()) not in (TOP_FIELDS, TOP_FIELDS_WORLDS):
    raise Bad("%s: field order %r" % (name, list(d.keys())))
  if d["input_kind"] not in ("text", "formal_only"):
    raise Bad("%s: input_kind" % name)
  prof = d["profile"]
  if not (prof in ("physical_v1", "ordinary") or (isinstance(prof, dict) and prof.get("name") in ("physical_v1", "ordinary"))):
    raise Bad("%s: profile %r" % (name, prof))
  try:
    cases = fm.materialize(d)
  except fm.Bad as e:
    raise Bad(str(e))
  by_case = {c["case"]: c for c in cases}
  for c in cases:
    check_case(c, d["input_kind"], by_case)
  for k in d["candidates"]:
    w = "%s/%s" % (name, k["id"])
    target = "%s:%s" % (name, k.get("variant", "base"))
    ents = by_case[target]["entities"]
    for a in k["sequence"]:
      check_action(a, set(), w, Ctx(entities=ents, witnesses=True))
    if k["verdict"] not in VERDICTS:
      raise Bad("%s: verdict" % w)
    if k["verdict"] != "valid" and "step" not in k and k["sequence"]:
      raise Bad("%s: a non-valid verdict names its step" % w)
  return d, cases


def run():
  files = sorted(glob.glob(os.path.join(CASES, "*.json")))
  if not files:
    raise Bad("no case files")
  covered = set()
  n_cases = 0
  for f in files:
    d, cases = check_record(f)
    n_cases += len(cases)
    for c in d["contract"]:
      m = re.match(r"^C(\d\d)$", c)
      if m:
        covered.add(int(m.group(1)))
  missing = sorted(set(range(1, 29)) - covered)
  if missing:
    raise Bad("uncovered contract identifiers: %s" % missing)
  print("  %d case files, %d effective cases; C01-C28 all covered" % (len(files), n_cases))


if __name__ == "__main__":
  run()
