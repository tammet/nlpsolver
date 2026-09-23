"""Marked legacy importer: pilot-v1 response format -> planning_ir_v1.

The pilot-v1 sidecar (prompts/planning_pilot/domain_system.txt) and task
reply (task_system.txt) predate the IR contract: they carry no source-unit
ids, no fluent declarations, no binding modes.  This normalizer imports them
into planning_ir_v1 with provenance origin "pilot_v1_import" and
source_unknown=true, and records every inferred field.  Per Stage 1A of the
improvement plan, an import through this module never counts as a valid v2
prompt output; it exists for regression analysis of the stored 2026-09-01
records.

Source units: law and occurrence records carry a model-written "source"
sentence; distinct strings become reconstructed units P1..Pn.  The strings
are model-claimed, not verified segmentation.  Facts, objects and schemas
have no source in pilot v1 and get "source_unknown".

  import_pilot_v1(sidecar_json, task_json or None) -> (ir_dict, notes_list)
"""

import planning_ir as pir


def _norm(s):
  return str(s).strip().lower().replace(" ", "_")


def _term(a):
  a = str(a).strip()
  if a.startswith("?"):
    return {"var": a[1:].upper()}
  return _norm(a)


def _lit(raw):
  sign = True
  if isinstance(raw, list) and raw and raw[0] == "not":
    sign, raw = False, raw[1]
  if not isinstance(raw, list) or not raw:
    raise ValueError("bad pilot literal %r" % (raw,))
  return {"pred": _norm(raw[0]), "args": [_term(a) for a in raw[1:]], "sign": sign}


def _lit_vars(d):
  return {a["var"] for a in d["args"] if isinstance(a, dict)}


def _lit_consts(d):
  return {a for a in d["args"] if isinstance(a, str)}


def import_pilot_v1(sidecar, task=None):
  sidecar = sidecar or {}
  notes, inferred = [], set()
  units, unit_of = [], {}

  def unit_for(text):
    text = str(text or "").strip()
    if not text:
      return "source_unknown"
    if text not in unit_of:
      uid = "P%d" % (len(units) + 1)
      unit_of[text] = uid
      units.append({"id": uid, "text": text})
    return unit_of[text]

  entities, ent_order = {}, []
  for o in sidecar.get("objects") or []:
    name = _norm((o or {}).get("name", ""))
    if not name:
      continue
    cls = (o or {}).get("class")
    if name not in entities:
      ent_order.append(name)
    entities[name] = _norm(cls) if cls else None

  fluent_use = {}          # pred -> set of arities
  consts_used = set()

  def see(d):
    fluent_use.setdefault(d["pred"], set()).add(len(d["args"]))
    consts_used.update(_lit_consts(d))
    return d

  facts = []
  for raw in sidecar.get("facts") or []:
    try:
      facts.append({"literal": see(_lit(raw)), "source": "source_unknown"})
    except ValueError as e:
      notes.append("fact skipped: %s" % e)
      inferred.add("skipped_malformed_fact")

  schemas, roles_used = [], set()
  params_of = {}           # schema id -> {var name: class}
  for s in sidecar.get("schemas") or []:
    sid = (s or {}).get("id")
    if not sid:
      notes.append("schema without id skipped")
      inferred.add("skipped_schema_without_id")
      continue
    params, fixed = [], []
    pmap = {}
    for a in s.get("args") or []:
      role = _norm((a or {}).get("role", "arg"))
      roles_used.add(role)
      t = _term((a or {}).get("term", ""))
      cls = (a or {}).get("class")
      cls = _norm(cls) if cls else None
      if isinstance(t, dict):
        params.append({"name": t["var"], "role": role, "class": cls,
                       "binding": "parameter"})
        pmap[t["var"]] = cls
      else:
        fixed.append({"role": role, "value": t})
        consts_used.add(t)
    schemas.append({"schema": str(sid), "verb": _norm(s.get("verb", sid)),
                    "params": params, "fixed": fixed, "source": "source_unknown"})
    params_of[str(sid)] = pmap
  inferred.add("schema_sources_unknown")

  laws = []
  for raw in sidecar.get("laws") or []:
    raw = raw or {}
    sid = str(raw.get("schema") or "")
    lid = "L%d" % (len(laws) + 1)
    src = unit_for(raw.get("source"))
    pvars = set(params_of.get(sid, ()))
    kind = raw.get("kind")
    try:
      if kind == "applicability":
        direction = raw.get("direction")
        if direction not in pir.DIRECTIONS:
          direction = "sufficient"
          inferred.add("direction_defaulted_sufficient")
        conds = [see(_lit(c)) for c in raw.get("conditions") or []]
        extra = sorted(set().union(*[_lit_vars(c) for c in conds]) - pvars) \
            if conds else []
        if extra:
          inferred.add("condition_witness_binding_assumed")
        laws.append({"law": lid, "schema": sid, "kind": "applicability",
                     "direction": direction, "conditions": conds,
                     "witnesses": [{"var": v, "binding": "witness", "class": None}
                                   for v in extra],
                     "source": src})
      elif kind == "effect":
        effects = []
        for e in raw.get("effects") or []:
          d = see(_lit((e or {}).get("literal")))
          when = [see(_lit(c)) for c in (e or {}).get("when") or []]
          evars = _lit_vars(d).union(*[_lit_vars(c) for c in when]) if when \
              else _lit_vars(d)
          extra = sorted(evars - pvars)
          if extra:
            # prompt example 4 states the universal reading ("everything in
            # the box"); the pilot compiler treated these as parameters
            inferred.add("effect_variable_binding_assumed_universal")
          effects.append({"literal": d, "when": when,
                          "quantified": [{"var": v, "binding": "universal",
                                          "class": None} for v in extra]})
        laws.append({"law": lid, "schema": sid, "kind": "effect",
                     "effects": effects, "source": src})
      else:
        notes.append("law with kind %r skipped" % (kind,))
        inferred.add("skipped_law_bad_kind")
    except ValueError as e:
      notes.append("law %s skipped: %s" % (lid, e))
      inferred.add("skipped_malformed_law")

  occurrences = []
  for raw in sidecar.get("occurrences") or []:
    raw = raw or {}
    bindings = {}
    for r, v in (raw.get("args") or {}).items():
      t = _term(v)
      bindings[_norm(r)] = t
      if isinstance(t, str):
        consts_used.add(t)
    occurrences.append({"schema": str(raw.get("schema") or ""),
                        "bindings": bindings, "source": unit_for(raw.get("source"))})

  unsupported = []
  for s in sidecar.get("static_rules") or []:
    unsupported.append({"source": unit_for(s), "reason": "static_rule_not_compiled"})

  # declare domain-used constants before the task section, so a goal or plan
  # constant that the domain already uses is not marked task-introduced
  for c in sorted(consts_used):
    if c not in entities:
      entities[c] = None
      ent_order.append(c)
      inferred.add("entity_declared_from_use")

  tsec = None
  if task is not None:
    task = task or {}
    goal, tvars, introduced = [], set(), []
    for raw in task.get("goal") or []:
      try:
        d = _lit(raw)
      except ValueError as e:
        notes.append("goal literal skipped: %s" % e)
        inferred.add("skipped_malformed_goal")
        continue
      fluent_use.setdefault(d["pred"], set()).add(len(d["args"]))
      tvars |= _lit_vars(d)
      goal.append(d)
    given = []
    for st in task.get("given_plan") or []:
      st = st or {}
      bindings = {_norm(r): _term(v) for r, v in (st.get("args") or {}).items()}
      given.append({"schema": str(st.get("schema") or ""), "bindings": bindings})
    seen_intro = set()
    for d in goal:
      for c in _lit_consts(d):
        if c not in entities and c not in seen_intro:
          seen_intro.add(c)
          introduced.append({"name": c, "class": None, "source": "source_unknown"})
          inferred.add("task_introduced_entity_assumed")
    for st in given:
      for v in st["bindings"].values():
        if isinstance(v, str) and v not in entities and v not in seen_intro:
          seen_intro.add(v)
          introduced.append({"name": v, "class": None, "source": "source_unknown"})
          inferred.add("task_introduced_entity_assumed")
    ub = task.get("user_bound")
    tsec = {"kind": task.get("kind"), "goal": goal,
            "variables": [{"var": v, "binding": "witness", "class": None}
                          for v in sorted(tvars)],
            "user_bound": int(ub) if isinstance(ub, (int, float)) and ub else None,
            "given_plan": given, "introduced_entities": introduced,
            "source": "source_unknown"}

  inferred.add("fluent_signatures_inferred_from_use")

  ir = {
    "ir_version": pir.IR_VERSION,
    "provenance": {"origin": "pilot_v1_import",
                   "normalizer": "planning_normalize_pilot_v1",
                   "source_unknown": True,
                   "inferred_fields": sorted(inferred)},
    "source_units": units,
    "entities": [{"name": n, "class": entities[n], "source": "source_unknown"}
                 for n in ent_order],
    "fluents": [{"fluent": p, "arity": a, "gloss": None,
                 "args": [{"role": None, "class": None}] * a,
                 "source": "source_unknown"}
                for p in sorted(fluent_use) for a in sorted(fluent_use[p])],
    "roles": [{"role": r, "class": None, "source": "source_unknown"}
              for r in sorted(roles_used - set(pir.REGISTERED_ROLES))],
    "schemas": schemas,
    "laws": laws,
    "derived_rules": [],
    "occurrences": occurrences,
    "facts": facts,
    "unsupported_units": unsupported,
    "task": tsec,
    # the pilot's implicit policy: every completion on, except that an
    # effects-only schema was never authorized in its search (observed on
    # the stored effect_only records: explorer reachable=1, no plan)
    "completion_profile": {"name": "pilot_v1_defaults",
                           "switches": dict({s: True for s in pir.COMPLETION_SWITCHES},
                                            unconditional_applicability=False)},
  }
  return ir, notes
