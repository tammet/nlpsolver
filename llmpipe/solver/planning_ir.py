"""planning_ir_v1: the versioned normalized action-theory IR (Stage 1A).

Contract module of the improvement plan
(memos/MEMO_2026_09_01_planpilot_improvement_plan.md, E10/E11, Stage 1A).
The layering (E11):

  model response format -> validator and normalizer -> THIS IR
                        -> world-indexed logic and search information

The JSON a model is asked for is a replaceable input format; this IR and the
compiler behind it are the stable contract.  Normalizers live in their own
modules (planning_normalize_pilot_v1.py is the marked legacy importer); the
compiler work (collision-safe internal symbols, E1/E2/E3 semantics) is
Stage 1B and does not live here.

The IR is one JSON object:

{
 "ir_version": "planning_ir_v1",
 "provenance": {"origin": "hand_authored" | "pilot_v1_import" | "model_normalized",
                "normalizer": str | None,
                "source_unknown": bool,       # true only for a legacy import
                "inferred_fields": [str, ...]},
 "source_units": [{"id": "S1", "text": "..."}, ...],
 "entities":  [{"name": "valve_a", "class": "valve" | None, "source": SRC}, ...],
 "fluents":   [{"fluent": "carries_water", "arity": 1, "gloss": str | None,
                "args": [{"role": str | None, "class": str | None}, ...],  # len == arity
                "functional_key": [int, ...] | None,   # declared functional key:
                # the argument positions that key the fluent; the remaining
                # positions hold at most one value per key (E2/E10).  Optional.
                "source": SRC}, ...],
 "roles":     [{"role": "circuit", "class": str | None, "source": SRC}, ...],
                # only roles beyond REGISTERED_ROLES; declared once, then usable
 "schemas":   [{"schema": "A1", "verb": "open_valve",
                "params": [{"name": "V", "role": "target", "class": "valve" | None,
                            "binding": "parameter"}, ...],
                "fixed":  [{"role": "actor", "value": "operator"}, ...],
                "source": SRC}, ...],
 "laws":      [{"law": "L1", "schema": "A1", "kind": "applicability",
                "direction": "sufficient" | "necessary" | "equivalent",
                "conditions": [LIT, ...],
                "witnesses": [{"var": "P", "binding": "witness", "class": ...}, ...],
                "source": SRC},
               {"law": "L2", "schema": "A1", "kind": "effect",
                "effects": [{"literal": LIT, "when": [LIT, ...],
                             "quantified": [{"var": "O", "binding": "universal"
                                             | "fresh_result", "class": ...}, ...]}],
                "source": SRC}, ...],
 "derived_rules": [{"rule": "R1", "head": LIT, "body": [LIT, ...],
                "variables": [{"var": "X", "class": str | None}, ...],
                "source": SRC}, ...],
                # E7 static/derived fragment: positive Horn rules (head and
                # body all sign=true); every head variable must occur in the
                # body.  Stage 1C compiles rules whose bodies touch only
                # never-written fluents; a rule over a dynamic fluent is a
                # certificate blocker, not silently ignored.
 "occurrences": [{"schema": "A1", "bindings": {"target": "valve_a"}, "source": SRC}, ...],
 "facts":     [{"literal": LIT, "source": SRC}, ...],          # ground
 "unsupported_units": [{"source": SRC, "reason": "static_rule_not_compiled"}, ...],
 "task": None | {"kind": "plan" | "reachability" | "narrative" | "verification" | "truth",
                 "goal": [LIT, ...],
                 "variables": [{"var": "X", "binding": "witness", "class": ...}, ...],
                 "user_bound": None | int >= 1,
                 "given_plan": [{"schema": "A1", "bindings": {...}}, ...],
                 "introduced_entities": [{"name": ..., "class": ..., "source": SRC}, ...],
                 "source": SRC},
 "completion_profile": {"name": str, "switches": {<each COMPLETION_SWITCH>: bool}}
}

LIT = {"pred": "on", "args": ["block_a", {"var": "B"}, ...], "sign": bool}.
A string argument is a constant and must be a declared entity (or a
task-introduced entity, inside the task); {"var": N} must resolve to a
declaration in scope: a schema parameter, a law witness, an effect-level
quantified variable, or a task variable.  SRC is a source-unit id, or the
string "source_unknown" (legacy imports only).  Every fact, law and
occurrence cites its source (acceptance condition 10); only a provenance
with source_unknown=true relaxes this.

validate(ir) returns a list of {"code", "path", "detail"} errors; an empty
list means the IR satisfies the contract.  ERROR_CODES lists every code.
"""

IR_VERSION = "planning_ir_v1"
ORIGINS = ("hand_authored", "pilot_v1_import", "model_normalized")
BINDING_MODES = ("parameter", "witness", "universal", "fresh_result")
DIRECTIONS = ("sufficient", "necessary", "equivalent")
LAW_KINDS = ("applicability", "effect")
TASK_KINDS = ("plan", "reachability", "narrative", "verification", "truth")
REGISTERED_ROLES = ("actor", "target", "source", "destination", "means",
                    "instrument", "material", "recipient")

# E8 result codes: what a run may report about a task.
RESULT_CODES = ("plan_found",
                "proved_unreachable_in_finite_closed_model",
                "no_plan_within_user_bound",
                "search_budget_exhausted",
                "incomplete_action_model",
                "translation_failed")

# E6 completion switches; every profile assigns all of them explicitly.
# unconditional_applicability (Stage 1B): a schema with effect laws but no
# applicability law is read as always applicable.  The pilot converter made
# that reading silently; here it is a named, counted assumption.
COMPLETION_SWITCHES = ("implicit_class_instances", "unique_names",
                       "closed_world_negatives", "effect_closure",
                       "only_if_complete", "lexical_movement",
                       "unconditional_applicability")
PROFILES = {
  "source_strict": {s: False for s in COMPLETION_SWITCHES},
  "classical_planning": dict({s: True for s in COMPLETION_SWITCHES},
                             lexical_movement=False),
}

ERROR_CODES = (
  "unknown_ir_version", "bad_origin", "bad_source_unit", "missing_source",
  "unknown_source_unit", "bad_entity", "duplicate_entity", "bad_fluent",
  "duplicate_fluent", "bad_role_decl", "undeclared_role", "duplicate_schema",
  "bad_param", "duplicate_role", "bad_direction", "bad_law_kind",
  "duplicate_law", "unknown_schema", "undeclared_fluent", "arity_mismatch",
  "undeclared_constant", "undeclared_variable", "bad_binding_mode",
  "nonground_fact", "bad_unsupported_unit", "bad_task_kind", "empty_goal",
  "bad_user_bound", "unknown_goal_fluent", "unbound_parameter",
  "extra_binding", "nonground_binding", "fixed_role_conflict",
  "class_mismatch", "bad_completion_profile", "bad_functional_decl",
  "bad_derived_rule",
)


def lit(pred, *args, **kw):
  """Fixture helper: lit("on", "block_a", var("B"), sign=False)."""
  return {"pred": pred, "args": list(args), "sign": kw.get("sign", True)}


def var(name):
  return {"var": name}


def validate(ir):
  errs = []
  def err(code, path, detail=""):
    assert code in ERROR_CODES, code
    errs.append({"code": code, "path": path, "detail": str(detail)})

  if not isinstance(ir, dict) or ir.get("ir_version") != IR_VERSION:
    v = ir.get("ir_version") if isinstance(ir, dict) else type(ir).__name__
    return [{"code": "unknown_ir_version", "path": "ir_version", "detail": str(v)}]
  prov = ir.get("provenance") or {}
  legacy = bool(prov.get("source_unknown"))
  if prov.get("origin") not in ORIGINS:
    err("bad_origin", "provenance.origin", prov.get("origin"))

  units = {}
  for i, u in enumerate(ir.get("source_units") or []):
    uid = (u or {}).get("id")
    if not isinstance(uid, str) or not uid or uid in units \
        or not isinstance(u.get("text"), str):
      err("bad_source_unit", "source_units[%d]" % i, uid)
    else:
      units[uid] = u["text"]

  def check_source(src, path):
    if src == "source_unknown":
      if not legacy:
        err("missing_source", path, "source_unknown outside a legacy import")
    elif src is None:
      err("missing_source", path)
    elif src not in units:
      err("unknown_source_unit", path, src)

  entities = {}
  for i, e in enumerate(ir.get("entities") or []):
    path = "entities[%d]" % i
    name, cls = (e or {}).get("name"), (e or {}).get("class")
    if not isinstance(name, str) or not name or \
        not (cls is None or isinstance(cls, str)):
      err("bad_entity", path, name)
      continue
    if name in entities:
      err("duplicate_entity", path, name)
    entities[name] = cls
    check_source(e.get("source"), path + ".source")

  task = ir.get("task")
  introduced = {}
  if isinstance(task, dict):
    for i, e in enumerate(task.get("introduced_entities") or []):
      path = "task.introduced_entities[%d]" % i
      name = (e or {}).get("name")
      if not isinstance(name, str) or not name:
        err("bad_entity", path, name)
        continue
      if name in entities or name in introduced:
        err("duplicate_entity", path, name)
      introduced[name] = (e or {}).get("class")

  fluents = {}
  for i, f in enumerate(ir.get("fluents") or []):
    path = "fluents[%d]" % i
    name, arity, args = (f or {}).get("fluent"), (f or {}).get("arity"), (f or {}).get("args")
    if not isinstance(name, str) or not name or not isinstance(arity, int) \
        or arity < 0 or not isinstance(args, list) or len(args) != arity:
      err("bad_fluent", path, name)
      continue
    if name in fluents:
      err("duplicate_fluent", path, "%s declared with arity %d and %d"
          % (name, fluents[name], arity))
      continue
    fluents[name] = arity
    fk = (f or {}).get("functional_key")
    if fk is not None:
      if not isinstance(fk, list) or not fk or len(fk) >= arity \
          or len(set(fk)) != len(fk) \
          or not all(isinstance(k, int) and 0 <= k < arity for k in fk):
        err("bad_functional_decl", path, "%s functional_key %r" % (name, fk))

  declared_roles = set()
  for i, r in enumerate(ir.get("roles") or []):
    path = "roles[%d]" % i
    role = (r or {}).get("role")
    if not isinstance(role, str) or not role or role in REGISTERED_ROLES \
        or role in declared_roles:
      err("bad_role_decl", path, role)
      continue
    declared_roles.add(role)

  def role_ok(role):
    return role in REGISTERED_ROLES or role in declared_roles

  schemas = {}
  for i, s in enumerate(ir.get("schemas") or []):
    path = "schemas[%d]" % i
    sid = (s or {}).get("schema")
    if not isinstance(sid, str) or not sid:
      err("bad_param", path, "missing schema id")
      continue
    if sid in schemas:
      err("duplicate_schema", path, sid)
      continue
    params, fixed, roles_seen = {}, {}, set()
    for j, p in enumerate(s.get("params") or []):
      ppath = "%s.params[%d]" % (path, j)
      pname, prole = (p or {}).get("name"), (p or {}).get("role")
      if not isinstance(pname, str) or not pname or pname in params \
          or (p or {}).get("binding") != "parameter":
        err("bad_param", ppath, pname)
        continue
      if not role_ok(prole):
        err("undeclared_role", ppath, prole)
      if prole in roles_seen:
        err("duplicate_role", ppath, prole)
      roles_seen.add(prole)
      params[pname] = {"role": prole, "class": p.get("class")}
    for j, fx in enumerate(s.get("fixed") or []):
      fpath = "%s.fixed[%d]" % (path, j)
      frole, fval = (fx or {}).get("role"), (fx or {}).get("value")
      if not role_ok(frole):
        err("undeclared_role", fpath, frole)
      if frole in roles_seen:
        err("duplicate_role", fpath, frole)
      roles_seen.add(frole)
      if not isinstance(fval, str) or not fval:
        err("nonground_binding", fpath, fval)
      elif fval not in entities:
        err("undeclared_constant", fpath, fval)
      fixed[frole] = fval
    check_source(s.get("source"), path + ".source")
    schemas[sid] = {"params": params, "fixed": fixed}

  def check_literal(d, path, scope, extra_consts=(), fluent_code="undeclared_fluent"):
    pred, args = (d or {}).get("pred"), (d or {}).get("args")
    if not isinstance(pred, str) or not pred or not isinstance(args, list) \
        or not isinstance((d or {}).get("sign"), bool):
      err(fluent_code, path, "malformed literal %r" % (d,))
      return
    if pred not in fluents:
      err(fluent_code, path, pred)
    elif fluents[pred] != len(args):
      err("arity_mismatch", path, "%s/%d used with %d args"
          % (pred, fluents[pred], len(args)))
    for k, a in enumerate(args):
      apath = "%s.args[%d]" % (path, k)
      if isinstance(a, str):
        if a not in entities and a not in extra_consts:
          err("undeclared_constant", apath, a)
      elif isinstance(a, dict) and isinstance(a.get("var"), str):
        if a["var"] not in scope:
          err("undeclared_variable", apath, a["var"])
      else:
        err("undeclared_constant", apath, repr(a))

  law_ids = set()
  for i, l in enumerate(ir.get("laws") or []):
    path = "laws[%d]" % i
    lid, sid, kind = (l or {}).get("law"), (l or {}).get("schema"), (l or {}).get("kind")
    if isinstance(lid, str) and lid:
      if lid in law_ids:
        err("duplicate_law", path, lid)
      law_ids.add(lid)
    else:
      err("duplicate_law", path, "missing law id")
    if sid not in schemas:
      err("unknown_schema", path, sid)
      continue
    scope = set(schemas[sid]["params"])
    for j, w in enumerate(l.get("witnesses") or []):
      wpath = "%s.witnesses[%d]" % (path, j)
      if (w or {}).get("binding") != "witness" or not isinstance((w or {}).get("var"), str):
        err("bad_binding_mode", wpath, (w or {}).get("binding"))
        continue
      scope.add(w["var"])
    if kind == "applicability":
      if l.get("direction") not in DIRECTIONS:
        err("bad_direction", path, l.get("direction"))
      for j, c in enumerate(l.get("conditions") or []):
        check_literal(c, "%s.conditions[%d]" % (path, j), scope)
    elif kind == "effect":
      for j, e in enumerate(l.get("effects") or []):
        epath = "%s.effects[%d]" % (path, j)
        escope = set(scope)
        for k, q in enumerate(e.get("quantified") or []):
          qpath = "%s.quantified[%d]" % (epath, k)
          if (q or {}).get("binding") not in ("universal", "fresh_result") \
              or not isinstance((q or {}).get("var"), str):
            err("bad_binding_mode", qpath, (q or {}).get("binding"))
            continue
          escope.add(q["var"])
        check_literal(e.get("literal"), epath + ".literal", escope)
        for k, c in enumerate(e.get("when") or []):
          check_literal(c, "%s.when[%d]" % (epath, k), escope)
    else:
      err("bad_law_kind", path, kind)
    check_source(l.get("source"), path + ".source")

  rule_ids = set()
  for i, r in enumerate(ir.get("derived_rules") or []):
    path = "derived_rules[%d]" % i
    rid = (r or {}).get("rule")
    if not isinstance(rid, str) or not rid or rid in rule_ids:
      err("bad_derived_rule", path, "missing or duplicate rule id %r" % (rid,))
    rule_ids.add(rid)
    scope = set()
    for j, v in enumerate((r or {}).get("variables") or []):
      if not isinstance((v or {}).get("var"), str):
        err("bad_derived_rule", "%s.variables[%d]" % (path, j), v)
        continue
      scope.add(v["var"])
    head, body = (r or {}).get("head") or {}, (r or {}).get("body") or []
    if head.get("sign") is not True or not body \
        or any((b or {}).get("sign") is not True for b in body):
      err("bad_derived_rule", path,
          "only positive Horn rules with a nonempty body are supported")
    check_literal(head, path + ".head", scope)
    for j, b in enumerate(body):
      check_literal(b, "%s.body[%d]" % (path, j), scope)
    body_vars = {a["var"] for b in body for a in ((b or {}).get("args") or [])
                 if isinstance(a, dict) and "var" in a}
    head_vars = {a["var"] for a in (head.get("args") or [])
                 if isinstance(a, dict) and "var" in a}
    if head_vars - body_vars:
      err("bad_derived_rule", path + ".head", "head variables %s not in the body"
          % sorted(head_vars - body_vars))
    check_source((r or {}).get("source"), path + ".source")

  def check_bindings(sid, bindings, path, extra_consts=()):
    if sid not in schemas:
      err("unknown_schema", path, sid)
      return
    sch = schemas[sid]
    role_of_param = {p["role"]: (n, p) for n, p in sch["params"].items()}
    for role, val in (bindings or {}).items():
      bpath = "%s.bindings[%s]" % (path, role)
      if not isinstance(val, str) or not val:
        err("nonground_binding", bpath, repr(val))
        continue
      if role in sch["fixed"]:
        if val != sch["fixed"][role]:
          err("fixed_role_conflict", bpath, "%s is fixed to %s, bound to %s"
              % (role, sch["fixed"][role], val))
        continue
      if role not in role_of_param:
        err("extra_binding", bpath, role)
        continue
      if val not in entities and val not in extra_consts:
        err("undeclared_constant", bpath, val)
      pcls = role_of_param[role][1].get("class")
      vcls = entities.get(val, introduced.get(val) if val in extra_consts else None)
      if pcls and vcls and pcls != vcls:
        err("class_mismatch", bpath, "%s expects %s, %s is %s"
            % (role, pcls, val, vcls))
    for role in role_of_param:
      if role not in (bindings or {}):
        err("unbound_parameter", path, role)

  for i, o in enumerate(ir.get("occurrences") or []):
    path = "occurrences[%d]" % i
    check_bindings((o or {}).get("schema"), (o or {}).get("bindings"), path)
    check_source((o or {}).get("source"), path + ".source")

  for i, f in enumerate(ir.get("facts") or []):
    path = "facts[%d]" % i
    d = (f or {}).get("literal") or {}
    if any(isinstance(a, dict) for a in (d.get("args") or [])):
      err("nonground_fact", path, d.get("pred"))
    check_literal(d, path + ".literal", set())
    check_source((f or {}).get("source"), path + ".source")

  for i, u in enumerate(ir.get("unsupported_units") or []):
    path = "unsupported_units[%d]" % i
    if not isinstance((u or {}).get("reason"), str) or not u.get("reason"):
      err("bad_unsupported_unit", path, (u or {}).get("reason"))
    check_source((u or {}).get("source"), path + ".source")

  if task is not None:
    if not isinstance(task, dict) or task.get("kind") not in TASK_KINDS:
      err("bad_task_kind", "task.kind",
          task.get("kind") if isinstance(task, dict) else type(task).__name__)
    else:
      tscope = set()
      for j, v in enumerate(task.get("variables") or []):
        vpath = "task.variables[%d]" % j
        if (v or {}).get("binding") != "witness" or not isinstance((v or {}).get("var"), str):
          err("bad_binding_mode", vpath, (v or {}).get("binding"))
          continue
        tscope.add(v["var"])
      goal = task.get("goal") or []
      if task.get("kind") != "truth" and not goal:
        err("empty_goal", "task.goal", task.get("kind"))
      for j, g in enumerate(goal):
        check_literal(g, "task.goal[%d]" % j, tscope,
                      extra_consts=introduced, fluent_code="unknown_goal_fluent")
      ub = task.get("user_bound")
      if not (ub is None or (isinstance(ub, int) and ub >= 1)):
        err("bad_user_bound", "task.user_bound", ub)
      for j, st in enumerate(task.get("given_plan") or []):
        check_bindings((st or {}).get("schema"), (st or {}).get("bindings"),
                       "task.given_plan[%d]" % j, extra_consts=introduced)

  cp = ir.get("completion_profile") or {}
  sw = cp.get("switches")
  if not isinstance(cp.get("name"), str) or not isinstance(sw, dict) \
      or set(sw) != set(COMPLETION_SWITCHES) \
      or not all(isinstance(v, bool) for v in sw.values()):
    err("bad_completion_profile", "completion_profile",
        sorted(sw) if isinstance(sw, dict) else sw)
  return errs
