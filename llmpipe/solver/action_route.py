"""Action route: source, query and result artifacts and the four operations.

  translate_source(source_text, profile, model_options) -> result (not implemented)
  compile_source(stage1, stage2_source, profile)         -> source artifact
  compile_query(query_logic, source_artifact, limits)    -> query artifact
  solve_query(source_artifact, query_artifact, options)  -> result (not implemented)

The artifacts are plain JSON dictionaries with an `artifact` name and a
`version`.  A source artifact is a persisted translation result: the source
text, the Stage-1 and Stage-2 units as given, the identity map, the profile,
the structural status of every unit and the diagnostics.  It is not a planning
schema written by a model.

`compile_source` validates the source and runs the source passes: structural
validation, situation compilation, the library check, availability,
restrictions, and effects with the state policy.  `source_outcome` reports
`source_compiled` only for a supported source with no pending pass, so a
caller cannot take a validated source for a compiled one.  `compile_query`
first records the units the query's selection excludes, then runs the
query-specific checks (location granularity, transport) on the admitted units
and the root's world, then the query pass (`query_views`): it selects the
input view, writes the proof obligations and decides the backend
requirements of that query.
`query_input` builds the prover input of one obligation from the two
artifacts.  `translate_source` and `solve_query` return a `not_implemented`
result; they never return an A5.3 outcome.

No operation here calls a model or a prover, and `compile_query` never
changes its source artifact: it works on the artifact's hashes and checks
them again before it returns.
"""

import copy
import hashlib
import json

import lc_action
import lc_action_avail
import lc_action_effects
import lc_action_library
import lc_action_query
import lc_action_restrict
import lc_action_situate

ARTIFACT_VERSION = "2"
SOURCE = "action_source"
QUERY = "action_query"
RESULT = "action_result"
DEFAULT_SEARCH_CAP = 4

# typed outcomes (A5.3) plus the two run-limit and ordinary-route names the
# reviewed fixtures use; `not_implemented` is not an outcome of the route
OUTCOMES = ("source_compiled", "plan_found", "goal_already_holds", "verification_result",
            "not_found", "candidate_not_validated", "inconsistent_action_state",
            "unsupported_backend_requirement", "unsupported_translation",
            "translation_invalid", "call_limit", "model_timeout", "prover_timeout",
            "prover_error", "backend_incompatible", "insufficient_search_allowance",
            "ordinary_result")
NOT_IMPLEMENTED = "not_implemented"

VIEWS = {"plan": "discovery", "reachable": "discovery", "verify": "verify",
         "question": "snapshot", "ask": "snapshot"}


class ArtifactError(Exception):
  """A caller error: a wrong container, a wrong version, a changed source."""


# ---------------------------------------------------------------------------
# deterministic serialization and hashes


def canonical(obj):
  """The one serialization every hash and every stored artifact uses."""
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
  return hashlib.sha256(canonical(obj).encode("utf-8")).hexdigest()


def dumps(artifact):
  """A stored artifact: canonical key order, one trailing newline."""
  return json.dumps(artifact, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def _source_content(a):
  """What the source hash covers: what was given, not what was derived.  The worlds declaration and every unit
  context record are given input (encoding v2): two sources that differ only in a qualifier have different hashes."""
  return {"profile": a["profile"], "library": a["library"], "source_text": a["source_text"],
          "identity": a["identity"], "worlds": a["worlds"],
          "units": [{"id": u["id"], "text": u["text"], "stage1": u["stage1"], "stage2": u["stage2"], "context": u["context"]}
                    for u in a["units"]]}


def source_hashes(a):
  return {"source": digest(_source_content(a)),
          "formulas": digest([u["stage2"] for u in a["units"]]),
          "identity": digest(a["identity"]),
          "artifact": digest({k: v for k, v in a.items() if k != "hashes"})}


# ---------------------------------------------------------------------------
# profile


def _names(value, what):
  """A list of distinct lexical names.  A string is not a list of characters."""
  if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
    raise ArtifactError("%s is a list of non-empty strings, got %r" % (what, value))
  if len(set(value)) != len(value):
    raise ArtifactError("%s repeats a name: %r" % (what, value))
  return sorted(value)


def normalize_profile(profile):
  """`physical_v1`, `ordinary`, or {"name", "policy", "locations"} (A2.5, A2.7).

  A caller configuration error raises ArtifactError; nothing is coerced.
  """
  if isinstance(profile, str):
    profile = {"name": profile}
  if not isinstance(profile, dict) or profile.get("name") not in (lc_action.PROFILE, lc_action.ORDINARY):
    raise ArtifactError("profile must be %s or %s" % (lc_action.PROFILE, lc_action.ORDINARY))
  extra = set(profile) - {"name", "policy", "locations"}
  if extra:
    raise ArtifactError("unknown profile fields %s" % sorted(extra))
  policy = profile.get("policy", {})
  if not isinstance(policy, dict) or set(policy) - {"stored", "computed"}:
    raise ArtifactError("policy is an object naming stored and computed properties only, got %r" % (policy,))
  stored = _names(policy.get("stored", []), "policy.stored")
  computed = _names(policy.get("computed", []), "policy.computed")
  both = sorted(set(stored) & set(computed))
  if both:
    raise ArtifactError("a property is stored or computed, not both: %s" % both)
  locations = profile.get("locations", {})
  if not isinstance(locations, dict) or set(locations) - {"flat"}:
    raise ArtifactError("locations is an object declaring the flat set only, got %r" % (locations,))
  flat = _names(locations.get("flat", []), "locations.flat")
  return {"name": profile["name"], "policy": {"stored": stored, "computed": computed},
          "locations": {"flat": flat}}


# ---------------------------------------------------------------------------
# compile_source


def _packages(stage2_source):
  """The source packages of a Stage-2 output, in order."""
  if isinstance(stage2_source, list) and stage2_source and stage2_source[0] == "and" \
     and all(isinstance(x, list) and x and x[0] == "@id" for x in stage2_source[1:]):
    return list(stage2_source[1:])
  if isinstance(stage2_source, list) and stage2_source and stage2_source[0] == "@id":
    return [stage2_source]
  if isinstance(stage2_source, list) and all(isinstance(x, list) for x in stage2_source):
    return list(stage2_source)
  raise ArtifactError("stage2_source is [\"and\", PACKAGE, ...], one package, or a list of packages")


def _concrete_ids(f, out):
  if isinstance(f, list):
    for x in f:
      _concrete_ids(x, out)
  elif lc_action.is_concrete(f):
    out.add(f)
  return out


def _projection_errors(proj):
  """Type errors in the Stage-1 fields the route reads.  Optional fields stay optional."""
  if not isinstance(proj, dict):
    return ["the Stage-1 projection is an object; a formal source passes stage1=None for the whole source"]
  out = []
  ents = proj.get("entities", [])
  if not isinstance(ents, list) or not all(isinstance(e, dict) and isinstance(e.get("id"), str)
                                           and e.get("type") in ("concrete", "generic") for e in ents):
    out.append("entities is a list of {id, type: concrete | generic}")
  acts = proj.get("actions", [])
  if not isinstance(acts, list) or not all(isinstance(a, dict) and isinstance(a.get("root"), str) and a["root"].strip()
                                           and isinstance(a.get("roles", {}), dict) for a in acts):
    out.append("actions is a list of {root, mode, roles}")
  if "action_reading" in proj and not (isinstance(proj["action_reading"], str) and proj["action_reading"] in READING_FORMS):
    out.append("action_reading is one of %s" % ", ".join(sorted(READING_FORMS)))
  return out


def _identity(stage1, packages, entities):
  """The source identity map: id -> {type, category?, class?}.

  Taken from the caller's entity map when given, else from the concrete
  entities of the Stage-1 units, else (a formal source with neither) from the
  concrete ids of the source formulas.  A query id outside this map is an
  unknown entity; a query never extends it.
  """
  ident = {}
  if entities:
    for i, cls in entities.items():
      ident[i] = {"type": "concrete", "class": cls}
  for s in stage1 or []:
    proj = s.get("stage1")
    if _projection_errors(proj):
      continue
    for e in proj.get("entities", []):
      if e.get("type") == "concrete":
        ident.setdefault(e["id"], {"type": "concrete"})
        if "category" in e:
          ident[e["id"]]["category"] = e["category"]
  if not entities and not ident:
    for i in sorted(_concrete_ids([p[2] for p in packages if len(p) == 3], set())):
      ident[i] = {"type": "concrete"}
  return ident


_LIBRARY = []


def _library():
  if not _LIBRARY:
    try:
      _LIBRARY.append(lc_action_library.load())
    except (lc_action_library.LibraryError, OSError) as e:
      raise ArtifactError("the action library is not usable: %s" % e)
  return _LIBRARY[0]


def library_view(source_artifact, view, restricted=()):
  """The library clauses of a query view for this source's library revision."""
  check_artifact(source_artifact, SOURCE)
  lib = _library()
  if source_artifact["library"] != lc_action_library.identity(lib):
    raise ArtifactError("the source artifact was compiled against another library revision "
                        "(id, version, clause-file hash or role-index hash differs)")
  return lc_action_library.select(lib, view, restricted)


CONTEXT_FIELDS = ("tense", "location", "location_role", "knower")


def normalize_worlds(worlds):
  """The source's worlds in narrative order; None is ["W0"].  The order comes from the declaration only."""
  if worlds is None:
    return list(lc_action.DEFAULT_WORLDS)
  if not isinstance(worlds, list) or not worlds or not all(isinstance(w, str) and lc_action.WORLD.match(w) for w in worlds):
    raise ArtifactError("worlds is a non-empty list of world names W0, W1, ..., got %r" % (worlds,))
  if len(set(worlds)) != len(worlds):
    raise ArtifactError("worlds repeats a name: %r" % (worlds,))
  return list(worlds)


def normalize_contexts(contexts):
  """{unit id: context record}; a record is {tense?, location?, location_role?, knower?}, checked for types only."""
  if contexts is None:
    return {}
  if not isinstance(contexts, dict):
    raise ArtifactError("contexts is an object {unit id: context record}")
  out = {}
  for uid, c in contexts.items():
    if c is None:
      continue
    if not isinstance(c, dict) or set(c) - set(CONTEXT_FIELDS):
      raise ArtifactError("a context record has the fields %s, got %r" % (", ".join(CONTEXT_FIELDS), c))
    if "tense" in c and c["tense"] not in lc_action.TENSES:
      raise ArtifactError("context tense is one of %s, got %r" % (", ".join(lc_action.TENSES), c["tense"]))
    if "location_role" in c and c["location_role"] not in lc_action.LOCATION_ROLES:
      raise ArtifactError("context location_role is one of %s, got %r" % (", ".join(lc_action.LOCATION_ROLES), c["location_role"]))
    for k in ("location", "knower"):
      if k in c and not (isinstance(c[k], str) and c[k].strip()):
        raise ArtifactError("context %s is an entity id, got %r" % (k, c[k]))
    out[uid] = {k: c.get(k) for k in CONTEXT_FIELDS}
    if out[uid]["tense"] is None:
      out[uid]["tense"] = "present"
  return out


def _context_diagnostics(unit, ident):
  """The unit-level diagnostics of a context record (migration plan section 9)."""
  c = unit["context"]
  out = []
  if c is None:
    return out
  given = {k: v for k, v in c.items() if v is not None and not (k == "tense" and v == "present")}
  if given and unit["form"] != "description_initial":
    out.append(("invalid", "context_record_position", ["context"],
                "a context record qualifies the facts of an initial description; a %s unit has no fact context "
                "(the law pattern of section 3 gives its literals their context)" % unit["form"]))
  if c["location"] is not None and c["location"] not in ident:
    out.append(("invalid", "undeclared_context_location", ["context", "location"],
                "context location %r names no location entity of the source" % c["location"]))
  if c["knower"] is not None and c["knower"] not in ident:
    out.append(("invalid", "undeclared_context_knower", ["context", "knower"],
                "context knower %r names no entity of the source" % c["knower"]))
  if c["location"] is not None and c["location_role"] is None:
    out.append(("unsupported", "unsupported_contextual_location", ["context", "location_role"],
                "a stated location without a location_role: provenance and scope compile differently (section 3)"))
  return out


def compile_source(stage1, stage2_source, profile, source_text=None, entities=None, provenance=None, worlds=None,
                   contexts=None):
  """Build a source artifact from a gold or replayed translation.  No model.

  stage1          list of {"id", "text", "stage1": projection}, or None for a
                  formal source
  stage2_source   the Stage-2 source packages
  profile         see normalize_profile
  entities        optional {id: class}; the identity map when given
  provenance      optional {"prompt", "model", ...}; recorded, never read
  worlds          optional list of the source's worlds in narrative order;
                  default ["W0"]
  contexts        optional {unit id: {tense, location, location_role, knower}}
  """
  prof = normalize_profile(profile)
  worlds = normalize_worlds(worlds)
  contexts = normalize_contexts(contexts)
  packages = copy.deepcopy(_packages(stage2_source))
  stage1 = copy.deepcopy(stage1) if stage1 is not None else None
  if stage1 is not None:
    if not isinstance(stage1, list) or not all(isinstance(x, dict) and isinstance(x.get("id"), str) for x in stage1):
      raise ArtifactError("stage1 is None (a formal source) or a list of {\"id\", \"text\", \"stage1\"} objects")
  if entities is not None and not (isinstance(entities, dict)
                                   and all(isinstance(k, str) and isinstance(v, str) for k, v in entities.items())):
    raise ArtifactError("entities is an object {id: class}")
  if source_text is not None and not isinstance(source_text, str):
    raise ArtifactError("source_text is a string")
  ident = _identity(stage1, packages, entities)
  by_s1 = {}
  diagnostics = []
  for s in stage1 or []:
    if s.get("id") in by_s1:
      diagnostics.append(_source_diag("invalid", "duplicate_unit", s.get("id"), "Stage 1 has two units with this id"))
    by_s1[s.get("id")] = s
  units, seen = [], set()
  for pkg in packages:
    v = lc_action.validate_source_unit(pkg, ident, prof["name"], worlds)
    uid = v["id"]
    if uid in seen:
      diagnostics.append(_source_diag("invalid", "duplicate_unit", uid, "Stage 2 has two packages with this id"))
    seen.add(uid)
    s1 = by_s1.get(uid)
    if stage1 is not None and s1 is None:
      diagnostics.append(_source_diag("invalid", "unit_coverage", uid, "a Stage-2 package without a Stage-1 unit"))
    proj = (s1 or {}).get("stage1")
    proj_errors = _projection_errors(proj) if s1 is not None else []
    if proj_errors:
      v["diagnostics"].extend({"level": "invalid", "code": "stage1_projection", "unit": uid, "path": "/",
                               "subformula": None, "message": m} for m in proj_errors)
      v["status"] = "invalid"
      proj_read = {}
    else:
      proj_read = proj or {}
    unit = {"id": uid, "text": (s1 or {}).get("text"), "stage1": proj, "stage2": pkg,
            "form": v["form"], "confidence": v["confidence"], "action_terms": v["action_terms"],
            "roots": sorted({a["root"] for a in proj_read.get("actions", [])}),
            "status": v["status"], "diagnostics": v["diagnostics"], "world": v["world"],
            "context": contexts.get(uid), "provenance_location": None}
    _check_reading(unit)
    for level, code, path, message in _context_diagnostics(unit, ident):
      d = {"level": level, "unit": uid, "path": "/" + "/".join(path), "subformula": None, "message": message}
      d["code" if level == "invalid" else "reason"] = code
      unit["diagnostics"].append(d)
      if level == "invalid" or unit["status"] == "supported":
        unit["status"] = level if level == "invalid" else "unsupported"
    c = unit["context"]
    if c and c["location"] is not None and c["location_role"] == "provenance":
      unit["provenance_location"] = c["location"]
    units.append(unit)
  for uid in sorted(set(contexts) - seen):
    diagnostics.append(_source_diag("invalid", "context_unit", uid, "a context record names no unit of the source"))
  for uid in by_s1:
    if uid not in seen:
      diagnostics.append(_source_diag("invalid", "unit_coverage", uid, "a Stage-1 unit without a Stage-2 package"))
  for uid, hit in sorted(lc_action.method_collisions([u for u in units if u["status"] == "supported"]).items()):
    u = [x for x in units if x["id"] == uid][0]
    for h in hit:
      u["diagnostics"].append({"level": "unsupported", "reason": "method_collision", "unit": uid, "path": "/",
                               "subformula": canonical(h["term"]), "with": h["with"],
                               "other_term": canonical(h["other_term"]),
                               "message": "the action term of this unit (source verb %s) and the term of unit %s "
                                          "(source verb %s) can name one action, and one of the two is an effect "
                                          "or a restriction" % (", ".join(h["roots"]), h["with"], ", ".join(h["other_roots"]))})
    u["status"] = "unsupported"
  namer = lc_action_situate.witness_namer(units)
  for u in units:
    u.update({"situated": None, "situation": None, "clauses": None, "witnesses": [], "compile_note": None})
    if u["status"] != "supported":
      continue
    r = lc_action_situate.compile_unit(u, namer)
    u.update({"situated": r["situated"], "situation": r["situation"], "clauses": r["clauses"],
              "witnesses": r["witnesses"], "compile_note": r["note"]})
    if r["diagnostic"]:
      sub = r["diagnostic"][2]
      u["diagnostics"].append({"level": "unsupported", "reason": r["diagnostic"][0], "unit": u["id"], "path": "/",
                               "subformula": canonical(sub) if sub is not None else None,
                               "message": r["diagnostic"][1], "pass": lc_action_situate.PASS})
      u["status"] = "unsupported"
    elif u["form"] in lc_action_situate.STATE_FORMS and u["clauses"] is None:
      raise ArtifactError("unit %s: the situation pass left a supported state unit without clauses" % u["id"])
  identity_clauses, restriction_clauses, restrictions = [], [], {"constructors": {}, "paths": []}
  policy_clauses, writes, dependencies, backend_requirements = [], [], None, None
  if prof["name"] == lc_action.PROFILE:
    for u in units:
      u["requirements"] = []
      if u["status"] != "supported" or u["form"] not in lc_action_avail.FORMS:
        continue
      r = lc_action_avail.compile_unit(u, namer, _library())
      u.update({"situated": r["situated"], "situation": r["situation"], "clauses": r["clauses"],
                "witnesses": r["witnesses"], "compile_note": r["note"], "requirements": r["requirements"]})
      if r["diagnostic"]:
        u["diagnostics"].append({"level": "unsupported", "reason": r["diagnostic"][0], "unit": u["id"], "path": "/",
                                 "subformula": None, "message": r["diagnostic"][1], "pass": lc_action_avail.PASS})
        u["status"] = "unsupported"
    for g in lc_action_avail.location_granularity(units, prof["locations"]["flat"]):
      d = {"level": "unsupported", "reason": "unsupported_location_granularity", "path": "/", "subformula": None,
           "message": g["message"], "pass": lc_action_avail.PASS}
      if g["unit_level"]:
        u = [x for x in units if x["id"] == g["units"][0]][0]
        u["diagnostics"].append(dict(d, unit=u["id"]))
        u["status"] = "unsupported"
        u["clauses"] = []
      else:
        diagnostics.append(dict(d, unit=None, units=g["units"]))
    identity_clauses = lc_action_avail.differ_clauses(units, ident)
    checks = {}
    for u in units:
      if u["status"] != "supported" or u["form"] != lc_action_restrict.FORM:
        continue
      r = lc_action_restrict.compile_unit(u, namer)
      u.update({"situated": r["situated"], "situation": r["situation"], "clauses": r["clauses"],
                "witnesses": r["witnesses"], "compile_note": r["note"], "requirements": r["requirements"]})
      checks[u["id"]] = r["checks"]
      if r["diagnostic"]:
        d = {"level": "unsupported", "reason": r["diagnostic"][0], "unit": u["id"], "path": "/",
             "subformula": None, "message": r["diagnostic"][1], "pass": lc_action_restrict.PASS}
        if r["diagnostic"][2]:
          d["detail"] = r["diagnostic"][2]
        u["diagnostics"].append(d)
        u["status"] = "unsupported"
    restriction_clauses, table = lc_action_restrict.hooks(units, checks, namer)
    restrictions = {"constructors": table, "paths": lc_action_restrict.path_coverage(_library(), table)}
    for u in units:
      if u["status"] != "supported" or u["form"] != lc_action_effects.FORM:
        continue
      r = lc_action_effects.compile_unit(u, namer, _library())
      u.update({"situated": r["situated"], "situation": r["situation"], "clauses": r["clauses"],
                "witnesses": r["witnesses"], "compile_note": r["note"], "requirements": r["requirements"]})
      writes.extend(r["writes"])
      if r["diagnostic"]:
        u["diagnostics"].append({"level": "unsupported", "reason": r["diagnostic"][0], "unit": u["id"], "path": "/",
                                 "subformula": None, "message": r["diagnostic"][1], "pass": lc_action_effects.PASS})
        u["status"] = "unsupported"
    policy_clauses, found, properties = lc_action_effects.state_policy(units, prof["policy"])
    for uid, reason, message, detail in found:
      u = [x for x in units if x["id"] == uid][0]
      u["diagnostics"].append({"level": "unsupported", "reason": reason, "unit": uid, "path": "/", "subformula": None,
                               "message": message, "detail": detail, "pass": lc_action_effects.PASS})
      u["status"] = "unsupported"
      u["clauses"] = []
    dependencies, backend_requirements = lc_action_effects.dependencies(units, _library())
    dependencies["writes"] = writes
    dependencies["properties"] = properties
  passes = ["structural_validation", lc_action_situate.PASS]
  library = {"id": None, "hash": None, "status": "not_selected"}
  if prof["name"] == lc_action.PROFILE:
    # the maintained library, checked against its role index; its identity is part of the source hash
    library = lc_action_library.identity(_library())
    passes.append(lc_action_library.PASS)
    passes.append(lc_action_avail.PASS)
    passes.append(lc_action_restrict.PASS)
    passes.append(lc_action_effects.PASS)
  artifact = {"artifact": SOURCE, "version": ARTIFACT_VERSION, "profile": prof,
              "library": library, "worlds": worlds,
              "source_text": source_text, "identity": ident, "identity_clauses": identity_clauses, "units": units,
              "restriction_clauses": restriction_clauses, "restrictions": restrictions,
              "policy_clauses": policy_clauses,
              "provenance": copy.deepcopy(provenance) if provenance else {"kind": "supplied_translation", "model": None, "prompt": None},
              "diagnostics": diagnostics,
              "clauses": None, "dependencies": dependencies, "backend_requirements": backend_requirements,
              "passes": passes, "pending_passes": [x for x in lc_action.PENDING_PASSES if x not in passes]}
  _refresh(artifact)
  return artifact


def _source_diag(level, code, unit, message):
  d = {"level": level, "unit": unit, "path": "/", "subformula": None, "message": message}
  d["code" if level == "invalid" else "reason"] = code
  return d


READING_FORMS = {"availability": ("availability", "denial"), "restriction": ("restriction",),
                 "effect": ("effect",), "occurrence": ("ordinary_event",)}


def _check_reading(unit):
  """The Stage-1 action reading agrees with the recognized Stage-2 form (A7.3).

  Checked only for a structurally supported unit: an unsupported form has its
  own diagnostic, and the reading of a mistranslation is part of that case.
  """
  if unit["status"] != "supported" or unit["stage1"] is None:
    return
  reading = unit["stage1"].get("action_reading")
  law = unit["form"] in ("availability", "denial", "restriction", "effect")
  if reading is None and not law:
    return
  if reading is None or unit["form"] not in READING_FORMS.get(reading, ()):
    unit["diagnostics"].append({"level": "invalid", "code": "reading_form_mismatch", "unit": unit["id"], "path": "/",
                                "subformula": None,
                                "message": "Stage-1 action_reading %r does not fit the Stage-2 form %s" % (reading, unit["form"])})
    unit["status"] = "invalid"


def _refresh(artifact):
  """Recompute the support summary, the clause list and the hashes after a diagnostic change.

  `clauses` is the list of the clauses compiled so far, and only for a source
  with no unsupported or invalid unit: an unsupported source yields no usable
  theory.  While `pending_passes` is not empty the list is partial.
  """
  diags = list(artifact["diagnostics"]) + [d for u in artifact["units"] for d in u["diagnostics"]]
  invalid = [d for d in diags if d["level"] == "invalid"]
  unsupported = [d for d in diags if d["level"] == "unsupported"]
  status = "invalid" if invalid else "unsupported" if unsupported else "supported"
  artifact["support"] = {
    "status": status,
    "reasons": sorted({d["reason"] for d in unsupported}),
    "errors": sorted({d["code"] for d in invalid}),
    "units": sorted({x for d in (invalid or unsupported) for x in ([d["unit"]] if d.get("unit") else d.get("units", []))}),
    "unsupported_units": sorted(u["id"] for u in artifact["units"] if u["status"] == "unsupported"),
    "invalid_units": sorted(u["id"] for u in artifact["units"] if u["status"] == "invalid")}
  artifact["clauses"] = None
  if status == "supported":
    artifact["clauses"] = [c for u in artifact["units"] for c in (u.get("clauses") or [])] \
      + list(artifact.get("restriction_clauses") or []) + list(artifact.get("policy_clauses") or []) \
      + list(artifact.get("identity_clauses") or [])
  artifact["hashes"] = source_hashes(artifact)


def add_diagnostic(artifact, unit, reason, message, pass_name):
  """A later compiler pass records an unsupported unit.  Returns a new artifact.

  The unit and its formula stay in the artifact.  The source hash does not
  change, because the source content did not; the artifact hash does.
  """
  check_artifact(artifact, SOURCE)
  if reason not in lc_action.REASONS:
    raise ArtifactError("unknown unsupported reason %r" % reason)
  new = copy.deepcopy(artifact)
  hit = [u for u in new["units"] if u["id"] == unit]
  if not hit:
    raise ArtifactError("no unit %r" % unit)
  hit[0]["diagnostics"].append({"level": "unsupported", "reason": reason, "unit": unit, "path": "/",
                                "subformula": None, "message": message, "pass": pass_name})
  if hit[0]["status"] == "supported":
    hit[0]["status"] = "unsupported"
  _refresh(new)
  return new


SOURCE_FIELDS = ("profile", "library", "worlds", "source_text", "identity", "identity_clauses", "restriction_clauses",
                 "restrictions", "policy_clauses", "units", "provenance", "diagnostics",
                 "clauses", "dependencies", "backend_requirements", "passes", "pending_passes", "support", "hashes")
QUERY_FIELDS = ("source", "query", "planning_root", "ambient", "knower", "excluded", "families", "limits", "backend", "view",
                "search",
                "diagnostics", "outcome",
                "backend_requirements", "selected_clauses", "view_hash", "obligations", "seed", "joint_positive",
                "obligations_hash", "passes", "pending_passes", "hash")
# the outcomes query compilation can decide without a prover
QUERY_DECIDED = ("translation_invalid", "unsupported_translation", "insufficient_search_allowance",
                 "unsupported_backend_requirement")
CAPABILITIES = (lc_action_query.NEGATIVE_PERSISTENCE, lc_action_query.SHARED_CONFIDENCE)


def query_hash(q):
  return digest({k: x for k, x in q.items() if k != "hash"})


def check_artifact(artifact, name):
  """Container name, version, required fields and hashes.  Raises ArtifactError.

  A hash shows that a record was not changed after it was written.  It does
  not show that the record is true; `solve_query` has its own rule for that.
  """
  if not isinstance(artifact, dict) or artifact.get("artifact") != name:
    raise ArtifactError("expected an %s artifact" % name)
  if artifact.get("version") != ARTIFACT_VERSION:
    raise ArtifactError("%s version %r; this code reads version %s" % (name, artifact.get("version"), ARTIFACT_VERSION))
  fields = SOURCE_FIELDS if name == SOURCE else QUERY_FIELDS if name == QUERY else ()
  missing = [k for k in fields if k not in artifact]
  if missing:
    raise ArtifactError("the %s artifact lacks %s" % (name, missing))
  try:
    if name == SOURCE:
      ok = artifact["hashes"] == source_hashes(artifact)
    elif name == QUERY:
      ok = artifact["hash"] == query_hash(artifact)
      src = artifact["source"]
      if not (isinstance(src, dict) and isinstance(src.get("source_hash"), str) and isinstance(src.get("artifact_hash"), str)):
        raise ArtifactError("the query artifact does not name its source revision")
      o = artifact["outcome"]
      if o is not None and not (isinstance(o, dict) and o.get("outcome") in QUERY_DECIDED):
        raise ArtifactError("a query artifact holds no outcome or one of %s, got %r; a query record cannot claim a solved result"
                            % (", ".join(QUERY_DECIDED), o))
    else:
      ok = True
  except (KeyError, TypeError, AttributeError) as e:
    raise ArtifactError("malformed %s artifact: %s" % (name, e))
  if not ok:
    raise ArtifactError("the %s artifact does not match its hash" % name)


def source_outcome(artifact):
  """The typed outcome of a source-only operation.

  `source_compiled` needs a supported source and no pending compiler pass.
  Until the passes exist the answer is `not_implemented`, with their names.
  """
  check_artifact(artifact, SOURCE)
  s = artifact["support"]
  if s["status"] == "invalid":
    return {"outcome": "translation_invalid", "errors": s["errors"], "units": s["units"]}
  if s["status"] == "unsupported":
    return {"outcome": "unsupported_translation", "reasons": s["reasons"], "units": s["units"]}
  if artifact["pending_passes"]:
    return {"outcome": NOT_IMPLEMENTED, "pending_passes": list(artifact["pending_passes"]),
            "detail": "the source passed the passes in `passes`; its clause list is partial"}
  return {"outcome": "source_compiled"}


# ---------------------------------------------------------------------------
# compile_query


def normalize_limits(limits):
  """{"search_cap": K, "explicit": bool}.  No limits = the default cap, not explicit."""
  if limits is None:
    return {"search_cap": DEFAULT_SEARCH_CAP, "explicit": False}
  if not isinstance(limits, dict) or set(limits) - {"search_cap", "explicit"}:
    raise ArtifactError("limits is {\"search_cap\": K, \"explicit\": bool}")
  cap = limits.get("search_cap", DEFAULT_SEARCH_CAP)
  if isinstance(cap, bool) or not isinstance(cap, int) or cap < 0:
    raise ArtifactError("search_cap is a non-negative integer")
  explicit = limits.get("explicit", "search_cap" in limits)
  if not isinstance(explicit, bool):
    raise ArtifactError("explicit is a Boolean, got %r" % (explicit,))
  return {"search_cap": cap, "explicit": explicit}


def search_depth(kind, steps, sequence, limits):
  """The reachability seed depth of A3.3 and the verify allowance of A3.4.

  Returns {"depth", "require_zero_remaining", "covers_bound", "insufficient"}.
  The semantic bound N and the search cap K stay separate: an exact bound is
  never shortened, an at-most bound may be searched to min(N, K).
  """
  cap, explicit = limits["search_cap"], limits["explicit"]
  out = {"depth": None, "require_zero_remaining": False, "covers_bound": True, "insufficient": False}
  if kind == "verify":
    if explicit and len(sequence) > cap:
      out["insufficient"] = True
    return out
  if kind not in ("plan", "reachable"):
    return out
  if steps is None:
    out["depth"] = cap
  elif steps["comparison"] == "exactly":
    if explicit and cap < steps["n"]:
      out["insufficient"] = True
    else:
      out["depth"], out["require_zero_remaining"] = steps["n"], True
  else:
    out["depth"] = min(steps["n"], cap) if explicit else steps["n"]
    out["covers_bound"] = out["depth"] >= steps["n"]
  return out


def seed_text(depth):
  """The seed as the fixtures write it: `0`, `s^N(0)`, or `none` (no search)."""
  if depth is None:
    return "none"
  return "0" if depth == 0 else "s^%d(0)" % depth


def normalize_backend(backend):
  """{"validated": [capability, ...]}.  No backend = the starting backend, which has validated none.

  A capability in `lc_action_query.UNAVAILABLE` stops a query that needs it
  until the caller names it as validated.  `shared_source_confidence` is
  recorded as a requirement and never stops compilation: the runtime's
  backend profile decides it for the selected binary (WP12).
  """
  if backend is None:
    return {"validated": []}
  if not isinstance(backend, dict) or set(backend) - {"validated"}:
    raise ArtifactError("backend is {\"validated\": [capability, ...]}")
  names = _names(backend.get("validated", []), "backend.validated")
  bad = sorted(set(names) - set(CAPABILITIES))
  if bad:
    raise ArtifactError("unknown backend capabilities %s; known: %s" % (bad, ", ".join(CAPABILITIES)))
  return {"validated": names}


def compile_query(query_logic, source_artifact, limits=None, backend=None, planning_root=None, ambient=None, knower=None):
  """Attach one formal query to a source artifact.  No model, no prover.

  The source artifact is read, never changed.  An unsupported or invalid
  source gives a query artifact with that outcome: attaching a query does not
  turn a partly supported source into a planning problem (A3.1).

  A supported query of the action profile gets its input view (clause names
  and a view hash), its proof obligations and its backend requirements.  A
  query that needs an unvalidated capability stops with
  `unsupported_backend_requirement` and gets no view.

  `planning_root` names a declared world (default: the last declared world);
  `ambient` a location entity whose scope facts the query's views keep;
  `knower` an entity whose knower-scoped facts they keep and whose constant
  replaces the objective knower of the laws (migration step 1b.5).
  """
  check_artifact(source_artifact, SOURCE)
  before = canonical(source_artifact)
  lim = normalize_limits(limits)
  back = normalize_backend(backend)
  pkg = copy.deepcopy(query_logic)
  v = lc_action.validate_query(pkg, source_artifact["identity"], source_artifact["profile"]["name"],
                               source_artifact.get("worlds"), planning_root, ambient, knower)
  root = v["planning_root"]
  sel = lc_action_query.selection(root, ambient, knower)
  q = {"artifact": QUERY, "version": ARTIFACT_VERSION,
       "source": {"source_hash": source_artifact["hashes"]["source"],
                  "artifact_hash": source_artifact["hashes"]["artifact"]},
       "query": {"id": v["id"], "package": pkg, "kind": v["kind"], "goal": v["goal"],
                 "steps": v["steps"], "sequence": v["sequence"], "variable": v["variable"],
                 "witnesses": v["witnesses"]},
       "planning_root": root, "ambient": ambient, "knower": knower, "excluded": None, "families": None,
       "limits": lim, "backend": back, "view": VIEWS.get(v["kind"]), "search": None,
       "diagnostics": v["diagnostics"], "outcome": None,
       "backend_requirements": None, "selected_clauses": None, "view_hash": None,
       "obligations": None, "seed": None, "joint_positive": None, "obligations_hash": None,
       "passes": [], "pending_passes": [lc_action_query.PASS]}
  src = source_artifact["support"]
  if v["status"] == "invalid":
    q["outcome"] = {"outcome": "translation_invalid", "errors": sorted({d["code"] for d in v["diagnostics"] if d["level"] == "invalid"})}
  elif src["status"] == "invalid":
    q["outcome"] = {"outcome": "translation_invalid", "errors": src["errors"], "units": src["units"]}
  elif src["status"] == "unsupported":
    q["outcome"] = {"outcome": "unsupported_translation", "reasons": src["reasons"], "units": src["units"]}
  elif v["status"] == "unsupported":
    q["outcome"] = {"outcome": "unsupported_translation",
                    "reasons": sorted({d["reason"] for d in v["diagnostics"] if d["level"] == "unsupported"}), "units": [v["id"]]}
  else:
    _attach(q, v, source_artifact, sel, lim)
  q["hash"] = query_hash(q)
  if canonical(source_artifact) != before:
    raise ArtifactError("compile_query changed its source artifact")
  return q


def _attach(q, v, source_artifact, sel, lim):
  """The checks of a supported query on the facts its selection admits, then the query pass.

  The exclusions come first and stay recorded when a later check stops the
  query.  Granularity, transport and negative persistence read the admitted
  units and the root's world (Astra's review R2).
  """
  units = source_artifact["units"]
  action = source_artifact["profile"]["name"] == lc_action.PROFILE
  if action:
    q["excluded"] = lc_action_query.exclusions(units, sel)
    units = lc_action_query.admitted(units, q["excluded"])
  root = sel["planning_root"]
  grain = lc_action_avail.query_granularity(units, source_artifact["profile"]["locations"]["flat"], root) if action else []
  hit = lc_action_effects.query_transport(v["kind"], v["goal"], v["sequence"], units, source_artifact.get("dependencies"), root)
  if grain:
    q["outcome"] = {"outcome": "unsupported_translation", "reasons": ["unsupported_location_granularity"],
                    "units": sorted({x for g in grain for x in g["units"]}), "pass": lc_action_avail.PASS,
                    "detail": "the query's selection keeps location facts that may contain each other: %s"
                              % "; ".join(g["message"] for g in grain)}
  elif hit:
    q["outcome"] = {"outcome": "unsupported_translation", "reasons": ["unsupported_transport_dependency"],
                    "units": hit["units"], "pass": lc_action_effects.PASS,
                    "detail": "the query reads the location of %s after a transition that may carry it; the library has no "
                              "co-movement transition, so the frame would keep a stale location: %s"
                              % (", ".join(hit["objects"]), hit["detail"])}
  else:
    s = search_depth(v["kind"], v["steps"], v["sequence"], lim)
    s["seed"] = seed_text(s["depth"]) if v["kind"] in ("plan", "reachable") else None
    q["search"] = s
    if s["insufficient"]:
      q["outcome"] = {"outcome": "insufficient_search_allowance",
                      "detail": "the explicit search cap %d is below the %s" % (
                        lim["search_cap"], "exact step bound" if v["kind"] != "verify" else "length of the supplied sequence")}
    elif action:
      _query_views(q, source_artifact, sel, units)


def _selection(query_artifact):
  return lc_action_query.selection(query_artifact["planning_root"], query_artifact["ambient"], query_artifact["knower"])


def _query_views(q, source_artifact, sel, units):
  """The query pass: backend requirements on the admitted `units`, then the input view and the obligations."""
  if source_artifact["pending_passes"]:
    return
  query = q["query"]
  needs = lc_action_query.backend_requirements(query, q["search"], units, source_artifact.get("dependencies"), _library(),
                                               sel["planning_root"])
  q["backend_requirements"] = needs
  q["passes"], q["pending_passes"] = [lc_action_query.PASS], []
  missing = [n for n in needs if n["capability"] in lc_action_query.UNAVAILABLE
             and n["capability"] not in q["backend"]["validated"]]
  if missing:
    q["outcome"] = {"outcome": "unsupported_backend_requirement",
                    "reason": lc_action_query.UNAVAILABLE[missing[0]["capability"]],
                    "capabilities": [n["capability"] for n in missing], "units": missing[0]["units"],
                    "pass": lc_action_query.PASS, "detail": missing[0]["detail"]}
    return
  try:
    ob = lc_action_query.obligations(query, q["search"], sel)
  except lc_action_query.Unsupported as e:
    q["outcome"] = {"outcome": "unsupported_translation", "reasons": [e.reason], "units": [query["id"]],
                    "pass": lc_action_query.PASS, "detail": str(e)}
    return
  q["families"] = list(lc_action_query.SELECTED_FAMILIES)
  view = lc_action_query.selected_view(query["kind"], query["sequence"])
  src, libc, ordc = lc_action_query.view_records(source_artifact, _library(), view, sel, q["excluded"])
  q["selected_clauses"] = {"view": view, "source": [r["name"] for r in src], "library": [r["name"] for r in libc],
                           "ordinary": [r["name"] for r in ordc]}
  q["view_hash"] = _view_digest(src, libc, ordc)
  q["obligations"], q["seed"], q["joint_positive"] = ob["obligations"], ob["seed"], ob["joint_positive"]
  q["obligations_hash"] = digest({"obligations": ob["obligations"], "seed": ob["seed"], "joint_positive": ob["joint_positive"]})


def _view_digest(src, libc, ordc):
  return digest({"source": [{"name": r["name"], "role": r["role"], "clause": r["clause"], "confidence": r.get("confidence")} for r in src],
                 "library": lc_action_library.view_hash(libc),
                 "ordinary": [{"name": r["name"], "clause": r["clause"]} for r in ordc]})


def query_input(source_artifact, query_artifact, obligation="q", polarity="positive"):
  """The prover input of one obligation: a list of GK clause objects.  No prover is called.

  The view is rebuilt from the source artifact and the library and must have
  the hash the query artifact recorded.  `obligation` is an obligation id or
  `joint`; `polarity` is `positive` or `negative`.
  """
  check_artifact(source_artifact, SOURCE)
  check_artifact(query_artifact, QUERY)
  _same_revision(source_artifact, query_artifact)
  if query_artifact["outcome"] or not query_artifact["obligations"]:
    raise ArtifactError("the query artifact has no runnable view: %r" % (query_artifact["outcome"] or query_artifact["pending_passes"],))
  src, libc, ordc = lc_action_query.view_records(source_artifact, _library(), query_artifact["selected_clauses"]["view"],
                                                 _selection(query_artifact), query_artifact["excluded"] or [])
  if _view_digest(src, libc, ordc) != query_artifact["view_hash"]:
    raise ArtifactError("the rebuilt view does not match the recorded view hash")
  if obligation == "joint":
    part = query_artifact["joint_positive"] if polarity == "positive" else None
  else:
    hit = [o for o in query_artifact["obligations"] if o["id"] == obligation]
    if not hit or polarity not in ("positive", "negative"):
      raise ArtifactError("no obligation %r with polarity %r" % (obligation, polarity))
    part = hit[0][polarity]
  if part is None:
    raise ArtifactError("obligation %r has no %s question" % (obligation, polarity))
  out = []
  for r in src:
    o = {"@name": r["name"], "@logic": copy.deepcopy(r["clause"])}
    if r.get("confidence") is not None:
      o["@confidence"] = r["confidence"]
    out.append(o)
  out.extend(copy.deepcopy(r["clause"]) for r in libc)
  out.extend({"@name": r["name"], "@logic": copy.deepcopy(r["clause"])} for r in ordc)
  if query_artifact["seed"]:
    out.append(copy.deepcopy(query_artifact["seed"]))
  out.extend(copy.deepcopy(part["clauses"]))
  out.append(copy.deepcopy(part["question"]))
  return out


def _same_revision(source_artifact, query_artifact):
  if query_artifact["source"]["source_hash"] != source_artifact["hashes"]["source"]:
    raise ArtifactError("the query artifact belongs to another source")
  if query_artifact["source"]["artifact_hash"] != source_artifact["hashes"]["artifact"]:
    raise ArtifactError("the query artifact was compiled against another revision of this source artifact "
                        "(a later pass or diagnostic changed it); compile the query again")


# ---------------------------------------------------------------------------
# operations that do not exist yet


def result(outcome, **fields):
  """A result record.  `outcome` is an A5.3 name or `not_implemented`."""
  if outcome not in OUTCOMES and outcome != NOT_IMPLEMENTED:
    raise ArtifactError("unknown outcome %r" % outcome)
  r = {"artifact": RESULT, "version": ARTIFACT_VERSION, "outcome": outcome,
       "answer": None, "plan": None, "diagnostics": [], "calls": {"model": 0, "gk": 0}}
  r.update(fields)
  return r


def translate_source(source_text, profile, model_options=None):
  """English to a source artifact.  Not implemented: no prompt variant exists."""
  normalize_profile(profile)
  return result(NOT_IMPLEMENTED, operation="translate_source",
                detail="the action-aware Stage-1 and Stage-2 prompt variants do not exist; "
                       "use compile_source with a gold or replayed translation")


def solve_query(source_artifact, query_artifact, options=None):
  """Run a compiled query on the prover.  Not implemented: no prover adapter exists.

  A query artifact that already has an outcome (invalid, unsupported,
  insufficient allowance) returns that outcome; it needs no prover.
  """
  check_artifact(source_artifact, SOURCE)
  check_artifact(query_artifact, QUERY)
  _same_revision(source_artifact, query_artifact)
  if query_artifact["outcome"]:
    o = dict(query_artifact["outcome"])
    return result(o.pop("outcome"), operation="solve_query", **o)
  return result(NOT_IMPLEMENTED, operation="solve_query",
                pending_passes=list(source_artifact["pending_passes"]) + list(query_artifact["pending_passes"]),
                detail="the prover adapter, the replay and the answer policy do not exist; the query artifact holds "
                       "the input view and the obligations; no prover was called")
