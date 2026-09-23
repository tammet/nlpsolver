"""Stage-1B compiler: planning_ir_v1 -> checked schematic action model.

Second layer of the E11 stack: the validated IR (planning_ir.py) compiles
into a schematic action model that planning_explore.py runs directly.  The
compiler owns the E3/E5/E10 semantics; the explorer owns E1/E2 application
semantics and the A1/E8 result codes.

Semantics implemented here:

- E3 directions.  Every `sufficient` (and `equivalent`) applicability law
  produces one authorization route; the conditions of every `necessary`
  (and `equivalent`) law are conjoined into each route before it can
  authorize a step.  A necessary-only schema has no route in strict mode;
  the `only_if_complete` switch turns its necessary conditions into the
  complete condition, and the firing is counted.  A schema with effect laws
  but no applicability law gets one unconditional route only under the
  `unconditional_applicability` switch, also counted.
- E5 identity.  Schemas never merge; ids are the identity.  Two schemas
  that share a verb and have alpha-equivalent typed role signatures are
  reported as candidate duplicates and kept distinct.  A schema whose laws
  cover only one of applicability/effect is reported as unjoined.
- E10.  No branch tests a predicate, verb or role name against a built-in
  list.  Movement semantics comes only from declared effect laws; the
  functional-family property comes only from a declared `functional_key`.
- Variables.  Law witnesses and effect-level quantified variables are
  renamed to law-local internal names, so two laws may reuse a variable
  name without capture.  A witness or quantified variable that shadows a
  schema parameter is renamed too, with a diagnostic; inside that law the
  name then means the local variable.
- E2 checker.  `delete_redundancy(model)` names every delete of a schema
  that a simultaneous functional assignment makes redundant: same declared
  functional key values, and the assignment fires under conditions at most
  as strong as the delete's (`when` subset).  The proof is recorded; the
  model itself keeps every delete.  A delete-free backend may drop exactly
  the deletes this checker names, and nothing else (acceptance condition 2).

compile_ir(ir, profile=None) -> (model, report); model is None when the IR
fails validation (report["result"] == "translation_failed").  `profile` may
be None (use the IR's own), a name from planning_ir.PROFILES, or a switches
dict assigning every COMPLETION_SWITCH.
"""

import json

import planning_ir as pir


def fire(report, name, detail=None):
  """Count a completion-assumption firing; one count per distinct detail."""
  key = (name, detail)
  seen = report.setdefault("_fired", set())
  if detail is not None and key in seen:
    return
  seen.add(key)
  report["assumptions"][name] = report["assumptions"].get(name, 0) + 1


def blocker(report, text):
  if text not in report["certificate_blockers"]:
    report["certificate_blockers"].append(text)


def _resolve_profile(ir, profile):
  if profile is None:
    cp = ir.get("completion_profile") or {}
    return {"name": cp.get("name", "ir_profile"), "switches": dict(cp["switches"])}
  if isinstance(profile, str):
    return {"name": profile, "switches": dict(pir.PROFILES[profile])}
  assert set(profile) == set(pir.COMPLETION_SWITCHES), sorted(profile)
  return {"name": "explicit", "switches": dict(profile)}


def _rename_lit(d, ren):
  args = [dict(a, var=ren.get(a["var"], a["var"])) if isinstance(a, dict) else a
          for a in d["args"]]
  return {"pred": d["pred"], "args": args, "sign": d["sign"]}


def _lit_key(d):
  return json.dumps(d, sort_keys=True)


def _local_vars(decls, law_id, params, report, sid):
  """Rename declared local variables to law-local internal names."""
  ren, out = {}, []
  for q in decls or []:
    v = q["var"]
    if v in params:
      report["diagnostics"].append(
        "variable %s of law %s shadows a parameter of schema %s; renamed"
        % (v, law_id, sid))
    ren[v] = "%s__%s" % (v, law_id)
    out.append({"var": ren[v], "binding": q["binding"], "class": q.get("class")})
  return ren, out


def compile_ir(ir, profile=None):
  report = {"result": None, "errors": [], "diagnostics": [],
            "assumptions": {}, "certificate_blockers": [], "profile": None}
  errs = pir.validate(ir)
  if errs:
    report["result"] = "translation_failed"
    report["errors"] = errs
    return None, report
  prof = _resolve_profile(ir, profile)
  report["profile"] = prof
  sw = prof["switches"]

  entities = {e["name"]: e.get("class") for e in ir.get("entities") or []}
  task = ir.get("task")
  task_entities = {}
  if isinstance(task, dict):
    task_entities = {e["name"]: e.get("class")
                     for e in task.get("introduced_entities") or []}

  fluents = {f["fluent"]: {"arity": f["arity"],
                           "functional_key": f.get("functional_key")}
             for f in ir.get("fluents") or []}

  laws_of = {}
  for l in ir.get("laws") or []:
    laws_of.setdefault(l["schema"], []).append(l)

  schemas = {}
  for s in ir.get("schemas") or []:
    sid = s["schema"]
    params = [{"name": p["name"], "role": p["role"], "class": p.get("class")}
              for p in s.get("params") or []]
    pnames = {p["name"] for p in params}
    fixed = {fx["role"]: fx["value"] for fx in s.get("fixed") or []}

    suff, nec, effects, has_eff = [], [], [], False
    for l in laws_of.get(sid, ()):
      if l["kind"] == "applicability":
        ren, wit = _local_vars(l.get("witnesses"), l["law"], pnames, report, sid)
        conds = [_rename_lit(c, ren) for c in l.get("conditions") or []]
        row = {"conditions": conds, "witnesses": wit, "law": l["law"]}
        if l["direction"] in ("sufficient", "equivalent"):
          suff.append(row)
        if l["direction"] in ("necessary", "equivalent"):
          nec.append(row)
      else:
        has_eff = True
        for e in l.get("effects") or []:
          ren, qs = _local_vars(e.get("quantified"), l["law"], pnames, report, sid)
          effects.append({"literal": _rename_lit(e["literal"], ren),
                          "when": [_rename_lit(c, ren) for c in e.get("when") or []],
                          "quantified": qs, "law": l["law"]})

    nec_conds = [c for row in nec for c in row["conditions"]]
    nec_wits = [w for row in nec for w in row["witnesses"]]
    nec_laws = [row["law"] for row in nec]
    routes, route_gap = [], None
    if suff:
      for row in suff:
        seen = {_lit_key(c) for c in row["conditions"]}
        conds = row["conditions"] + [c for c in nec_conds if _lit_key(c) not in seen]
        routes.append({"conditions": conds,
                       "witnesses": row["witnesses"] + nec_wits,
                       "laws": [row["law"]] + [x for x in nec_laws
                                               if x != row["law"]]})
    elif nec:
      if sw["only_if_complete"]:
        routes.append({"conditions": list(nec_conds), "witnesses": list(nec_wits),
                       "laws": list(nec_laws)})
        fire(report, "only_if_complete", sid)
      else:
        route_gap = "necessary_only"
        report["diagnostics"].append(
          "schema %s has only necessary conditions: no authorization route "
          "in strict mode" % sid)
    elif has_eff:
      if sw["unconditional_applicability"]:
        routes.append({"conditions": [], "witnesses": [], "laws": []})
        fire(report, "unconditional_applicability", sid)
      else:
        route_gap = "no_applicability_law"
        report["diagnostics"].append(
          "schema %s states effects but no applicability law: no route "
          "in strict mode" % sid)
    else:
      report["diagnostics"].append("schema %s has no laws" % sid)

    if routes and not has_eff and laws_of.get(sid):
      report["diagnostics"].append(
        "unjoined schema %s: applicability laws but no effect law" % sid)
    if route_gap:
      blocker(report, "schema %s: %s" % (sid, route_gap))

    schemas[sid] = {"verb": s.get("verb"), "params": params, "fixed": fixed,
                    "routes": routes, "route_gap": route_gap,
                    "effects": effects, "has_effect_law": has_eff}

  sigs = {}
  for sid, sch in schemas.items():
    sig = (sch["verb"],
           frozenset((p["role"], p["class"]) for p in sch["params"]),
           frozenset(sch["fixed"].items()))
    if sig in sigs:
      report["diagnostics"].append(
        "schemas %s and %s share verb %s with alpha-equivalent typed "
        "signatures: candidate duplicates, kept distinct"
        % (sigs[sig], sid, sch["verb"]))
    else:
      sigs[sig] = sid

  if ir.get("unsupported_units"):
    for u in ir["unsupported_units"]:
      blocker(report, "unsupported unit: %s (%s)" % (u.get("source"), u["reason"]))

  facts_pos, facts_neg = set(), set()
  for f in ir.get("facts") or []:
    d = f["literal"]
    atom = (d["pred"], tuple(d["args"]))
    (facts_pos if d["sign"] else facts_neg).add(atom)

  # E7: the static/derived fragment.  Only rules whose head and body touch
  # never-written fluents compile; they close into ground atoms here, once,
  # since nothing an action does can change them.  A rule over a dynamic
  # fluent, or a derived head an effect writes, is a certificate blocker.
  written = {e["literal"]["pred"] for sch in schemas.values()
             for e in sch["effects"]}
  derived_pos = set()
  usable_rules = []
  for r in ir.get("derived_rules") or []:
    head_pred = r["head"]["pred"]
    dyn = sorted({p for p in [head_pred] + [b["pred"] for b in r["body"]]
                  if p in written})
    if head_pred in written:
      report["diagnostics"].append(
        "derived rule %s: head %s is also written by effects" % (r["rule"], head_pred))
      blocker(report, "derived rule %s over written fluent %s" % (r["rule"], head_pred))
    elif dyn:
      report["diagnostics"].append(
        "derived rule %s reads dynamic fluents %s: not compiled" % (r["rule"], dyn))
      blocker(report, "derived rule %s over dynamic fluents" % r["rule"])
    else:
      usable_rules.append(r)
  if usable_rules:
    all_entities = dict(entities, **task_entities)
    def rule_matches(rule, known):
      names = sorted(all_entities)
      rvars = [v["var"] for v in rule.get("variables") or []]
      classes = {v["var"]: v.get("class") for v in rule.get("variables") or []}
      def ground(d, b):
        return (d["pred"], tuple(b.get(a["var"]) if isinstance(a, dict) else a
                                 for a in d["args"]))
      def rec(i, b):
        if i == len(rvars):
          if all(ground(c, b) in known for c in rule["body"]):
            yield ground(rule["head"], b)
          return
        for n in names:
          if classes[rvars[i]] in (None, all_entities.get(n)):
            yield from rec(i + 1, dict(b, **{rvars[i]: n}))
      yield from rec(0, {})
    changed = True
    while changed:
      changed = False
      known = facts_pos | derived_pos
      for r in usable_rules:
        for atom in rule_matches(r, known):
          if atom not in facts_pos and atom not in derived_pos:
            derived_pos.add(atom)
            changed = True

  if sw["unique_names"] and len(entities) + len(task_entities) >= 2:
    fire(report, "unique_names", "in_force")
  if not sw["unique_names"]:
    blocker(report, "unique_names off: named objects not known distinct")
  if not sw["closed_world_negatives"]:
    blocker(report, "closed_world_negatives off: initial state not closed")

  model = {"profile": prof,
           "entities": dict(entities), "task_entities": dict(task_entities),
           "fluents": fluents, "schemas": schemas,
           "facts_pos": facts_pos, "facts_neg": facts_neg,
           "derived_pos": derived_pos, "written_fluents": written,
           "occurrences": [{"schema": o["schema"], "bindings": dict(o["bindings"])}
                           for o in ir.get("occurrences") or []],
           "task": task}
  return model, report


def delete_redundancy(model):
  """E2: name each delete a simultaneous functional assignment makes redundant.

  Returns (redundant, kept): `redundant` rows carry the proof; `kept` lists
  every other delete with the reason no proof exists.  Quantified effects
  are never proved redundant.
  """
  redundant, kept = [], []
  for sid, sch in model["schemas"].items():
    dels = [e for e in sch["effects"] if not e["literal"]["sign"]]
    adds = [e for e in sch["effects"] if e["literal"]["sign"]]
    for d in dels:
      pred = d["literal"]["pred"]
      fk = model["fluents"].get(pred, {}).get("functional_key")
      row = {"schema": sid, "delete": d["literal"], "law": d["law"]}
      if d["quantified"]:
        kept.append(dict(row, reason="quantified delete"))
        continue
      if not fk:
        kept.append(dict(row, reason="no declared functional_key for %s" % pred))
        continue
      dwhen = {_lit_key(c) for c in d["when"]}
      proof = None
      for a in adds:
        if a["literal"]["pred"] != pred or a["quantified"]:
          continue
        if any(a["literal"]["args"][k] != d["literal"]["args"][k] for k in fk):
          continue
        if a["literal"]["args"] == d["literal"]["args"]:
          continue
        if not all(_lit_key(c) in dwhen for c in a["when"]):
          continue
        proof = {"replaced_by": a["literal"], "add_law": a["law"],
                 "functional_key": list(fk), "when_subset": True}
        break
      if proof:
        redundant.append(dict(row, proof=proof))
      else:
        kept.append(dict(row, reason="no functional assignment replaces the key"))
  return redundant, kept


# E9 rendering: a controlled-language step display derived from the typed
# roles.  Displayed arguments are exactly the schema parameters (the planner
# choices); fixed fillers and compiler-local variables are internal.  The
# attachment is structural (role -> phrase), so a value can never migrate to
# another argument's slot.
_ROLE_PHRASE = {"target": "%s", "source": "from %s", "destination": "to %s",
                "means": "via %s", "instrument": "with %s",
                "material": "of %s", "recipient": "to %s"}


def render_step(model, sid, values):
  sch = model["schemas"][sid]
  verb = (sch["verb"] or sid).replace("_", " ")
  bits, actor = [verb], None
  for p, v in zip(sch["params"], values):
    if p["role"] == "actor":
      actor = v
    else:
      bits.append(_ROLE_PHRASE.get(p["role"], p["role"] + " %s") % v)
  if actor is not None:
    bits.append("by " + actor)
  return " ".join(bits)
