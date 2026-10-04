"""Action route: source, query and result artifacts and the four operations.

  translate_source(source_text, profile, model_options) -> source artifact (action_pipeline.translate)
  compile_source(stage1, stage2_source, profile)         -> source artifact
  compile_query(query_logic, source_artifact, limits)    -> query artifact
  solve_query(source_artifact, query_artifact, options)  -> result (action_answer.solve: GK, replay, policy)

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
artifacts; `action_gk.run_query` runs every obligation of a query on the
registered GK build and returns the evidence; `solve_query` runs it and
decides the answer with the replay (`action_answer`).
`translate_source` translates English with an action prompt bundle
(`action_pipeline`); without the bundle's files it returns a
`not_implemented` result.  The pipeline's own run calls `action_pipeline.translate`
and `action_answer.solve` directly; `translate_source` and `solve_query` are
the library interface of the same operations, which the checks use.
docs/code/action-route.md lists the modules of each pass.

No operation here calls a model.  Only `solve_query` calls the prover, and
`compile_query` never changes its source artifact: it works on the
artifact's hashes and checks them again before it returns.
"""

import copy
import json

import action_prompt
from digests import canonical, digest
import action_repair as arep
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

# the typed outcomes of the route plus the two run-limit and ordinary-route names the
# reviewed fixtures use; `not_implemented` is not an outcome of the route
OUTCOMES = ("source_compiled", "plan_found", "goal_already_holds", "verification_result",
            "not_found", "candidate_not_validated", "inconsistent_action_state",
            "unsupported_backend_requirement", "unsupported_translation",
            "translation_invalid", "call_limit", "model_timeout", "prover_timeout",
            "prover_error", "backend_incompatible", "backend_unavailable", "model_error",
            "insufficient_search_allowance", "ordinary_result")
NOT_IMPLEMENTED = "not_implemented"

VIEWS = {"plan": "discovery", "reachable": "discovery", "verify": "verify",
         "question": "snapshot", "ask": "snapshot"}


class ArtifactError(Exception):
  """A caller error: a wrong container, a wrong version, a changed source."""


# ---------------------------------------------------------------------------
# deterministic serialization and hashes


def dumps(artifact):
  """A stored artifact: canonical key order, one trailing newline."""
  return json.dumps(artifact, sort_keys=True, indent=1, ensure_ascii=False) + "\n"


def _source_content(a):
  """What the source hash covers: what was given, not what was derived.  The worlds declaration and every unit
  context record are given input (encoding v2): two sources that differ only in a qualifier have different hashes.
  The given type records are input too; a source without them hashes as before."""
  out = {"profile": a["profile"], "library": a["library"], "source_text": a["source_text"],
         "identity": a["identity"], "worlds": a["worlds"],
         "units": [{"id": u["id"], "text": u["text"], "stage1": u["stage1"], "stage2": u["stage2"], "context": u["context"]}
                   for u in a["units"]]}
  given = [{k: t[k] for k in TYPE_FIELDS if k in t} for t in a.get("types") or [] if t["kind"] in GIVEN_TYPES]
  if given:
    out["types"] = given
  return out


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
  """`physical_v1`, `ordinary`, or {"name", "policy", "locations"}.

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


def _places(ident):
  """The ids that the identity map declares places: Stage-1 category place, or class place in a formal entity map."""
  return {i for i, v in ident.items() if "place" in (v.get("category"), v.get("class"))}


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

# Type records.  A type record is a static class
# fact of a concrete entity that stands apart from any unit formula:
#   stated                  the class of a referent that a law sentence introduces by a class noun, from the
#                           Stage-2 envelope field `types` of that unit (a law unit holds its rule only)
#   stage1_person           the documented person convention: an objective source unit lists the entity with the
#                           Stage-1 category person (`action_prompt.person_types`); an LLM interpretation, recorded
#                           with its units, never verified by the compiler
#   lexical_identification  derived here: an unconditional isa fact of a past or future description whose class noun
#                           names the entity ("Yesterday block b was on the table"); it stays when a query's
#                           selection leaves the description out for its tense, and only then enters a view
# The first two are given input (source hash); the third is derived (artifact hash).  Every record compiles to one
# static clause; the replay reads the records, never the clauses.
TYPE_KINDS = ("stated", "stage1_person", "lexical_identification")
GIVEN_TYPES = ("stated", "stage1_person")
TYPE_FIELDS = ("entity", "class", "kind", "unit", "units")
TYPE_ROLE = "static_type"
DESCRIPTIONS = ("description_static", "description_initial")


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
  """The unit-level diagnostics of a context record: where a context record may stand and what it holds.  The
  query decides which facts a context record leaves out (`lc_action_query.exclusions`)."""
  c = unit["context"]
  out = []
  if c is None:
    return out
  given = {k: v for k, v in c.items() if v is not None and not (k == "tense" and v == "present")}
  # a unit whose form the validator could not read has its own invalid diagnostic; its record is judged after the fix
  if given and unit["form"] is not None and unit["form"] != "description_initial":
    out.append(("invalid", "context_record_position", ["context"],
                "a context record qualifies the facts of an initial description; a %s unit has no fact context "
                "(the law pattern gives its literals their context)" % unit["form"]))
  if c["location"] is not None and c["location"] not in ident:
    out.append(("invalid", "undeclared_context_location", ["context", "location"],
                "context location %r names no location entity of the source" % c["location"]))
  if c["knower"] is not None and c["knower"] not in ident:
    out.append(("invalid", "undeclared_context_knower", ["context", "knower"],
                "context knower %r names no entity of the source" % c["knower"]))
  if c["location"] is not None and c["location_role"] is None:
    out.append(("unsupported", "unsupported_contextual_location", ["context", "location_role"],
                "a stated location without a location_role: provenance and scope compile differently"))
  return out


def normalize_types(types, ident, unit_ids):
  """Given type records: [{"entity", "class", "kind": stated | stage1_person, "unit", "units"?}].  None is []."""
  if types is None:
    return []
  if not isinstance(types, list):
    raise ArtifactError("types is a list of type records")
  out, seen = [], set()
  for t in types:
    if not isinstance(t, dict) or set(t) - set(TYPE_FIELDS) or t.get("kind") not in GIVEN_TYPES:
      raise ArtifactError("a given type record is {entity, class, kind: %s, unit, units?}, got %r" % (" | ".join(GIVEN_TYPES), t))
    if not (lc_action.is_concrete(t.get("entity")) and t["entity"] in ident):
      raise ArtifactError("a type record names a concrete entity of the source, got %r" % (t.get("entity"),))
    if not lc_action.is_lexical(t.get("class")):
      raise ArtifactError("a type record's class is a lexical constant, got %r" % (t.get("class"),))
    for uid in [t.get("unit")] + list(t.get("units") or []):
      if uid not in unit_ids:
        raise ArtifactError("a type record names %r, which is no unit of the source" % (uid,))
    k = (t["entity"], t["class"])
    if k in seen:
      continue
    seen.add(k)
    out.append({f: copy.deepcopy(t[f]) for f in TYPE_FIELDS if f in t})
  return out


def _lexical_types(units):
  """The lexical_identification records: the unconditional positive isa conjuncts of a supported past or future
  description, whose class noun names the entity in the unit's Stage-1 text.  A unit with a knower or a scope
  location keeps its qualification (no record); an uncertain unit gives no certain type; a class predication
  ("b 3 was a block") is no lexical identification; a type that an unqualified description also states needs none."""
  plain = set()
  for u in units:
    if u["status"] == "supported" and u["form"] in DESCRIPTIONS and not u.get("context"):
      f = lc_action_situate._unit_formula(u)
      plain.update(tuple(a) for a in lc_action.conjuncts(f) if action_prompt.is_class_atom(a))
  out = []
  for u in units:
    c = u.get("context") or {}
    if u["status"] != "supported" or u["form"] not in DESCRIPTIONS:
      continue
    if (c.get("tense") or "present") == "present" or c.get("knower") is not None or c.get("location_role") == "scope":
      continue
    if u.get("confidence") is not None and u["confidence"] < 1:
      continue
    for a in lc_action.conjuncts(lc_action_situate._unit_formula(u)):
      if (action_prompt.is_class_atom(a) and tuple(a) not in plain
          and action_prompt.names_class(u.get("text"), a[1], a[2])):
        out.append({"entity": a[2], "class": a[1], "kind": "lexical_identification", "unit": u["id"]})
  return out


def _type_clauses(types):
  return [{"role": TYPE_ROLE, "unit": None, "units": ["types"], "type_kind": t["kind"], "type_unit": t["unit"],
           "clause": [["isa", t["class"], "#:" + t["entity"]]], "pass": "types"} for t in types]


def type_facts(artifact):
  """(entity, class) of every type record of a source artifact: the classes the dependency analyses may assume."""
  return [(t["entity"], t["class"]) for t in artifact.get("types") or []]


def compile_source(stage1, stage2_source, profile, source_text=None, entities=None, provenance=None, worlds=None,
                   contexts=None, types=None, type_notes=None):
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
  types           optional given type records (stated, stage1_person); see TYPE_KINDS
  type_notes      optional notes of a type the caller suppressed (a conflicting category); kept as source
                  diagnostics of level note
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
  given_types = normalize_types(types, ident, {p[1] for p in packages if isinstance(p, list) and len(p) == 3})
  diagnostics = []
  for n in type_notes or []:
    diagnostics.append({"level": "note", "reason": n["reason"], "unit": None, "units": list(n.get("units") or []),
                        "path": "/", "subformula": None, "entity": n["entity"],
                        "message": "no %s type for %s: %s" % (n.get("class", "person"), n["entity"], json.dumps(
                          {k: v for k, v in n.items() if k in ("categories", "classes") and v}, sort_keys=True))})
  units = _validated_units(stage1, packages, ident, prof, worlds, contexts, diagnostics)
  _mark_method_collisions(units)
  namer = lc_action_situate.witness_namer(units)
  _situation_pass(units, namer)
  all_types = given_types + [t for t in _lexical_types(units)
                             if (t["entity"], t["class"]) not in {(g["entity"], g["class"]) for g in given_types}]
  compiled = {"identity_clauses": [], "restriction_clauses": [], "restrictions": {"constructors": {}, "paths": []},
              "policy_clauses": [], "dependencies": None, "backend_requirements": None}
  if prof["name"] == lc_action.PROFILE:
    compiled = _action_passes(units, namer, prof, ident, [(t["entity"], t["class"]) for t in all_types], diagnostics)
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
              "source_text": source_text, "identity": ident, "identity_clauses": compiled["identity_clauses"],
              "units": units,
              "restriction_clauses": compiled["restriction_clauses"], "restrictions": compiled["restrictions"],
              "policy_clauses": compiled["policy_clauses"],
              "provenance": copy.deepcopy(provenance) if provenance else {"kind": "supplied_translation", "model": None, "prompt": None},
              "diagnostics": diagnostics,
              "clauses": None, "dependencies": compiled["dependencies"],
              "backend_requirements": compiled["backend_requirements"],
              "passes": passes, "pending_passes": [x for x in lc_action.SOURCE_PASSES if x not in passes]}
  if all_types:
    # only a source with type records has the fields: every other artifact keeps its earlier hashes
    artifact["types"] = all_types
    artifact["type_clauses"] = _type_clauses(all_types)
  _refresh(artifact)
  return artifact


def _validated_units(stage1, packages, ident, prof, worlds, contexts, diagnostics):
  """The structural pass: one unit record per Stage-2 package, validated (`lc_action.validate_source_unit`), with its
  Stage-1 projection, its reading checked against its form and its context record.  Source-level findings go to
  `diagnostics`."""
  by_s1 = {}
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
  return units


def _first_by_id(units):
  """{unit id: unit}, the first unit of an id (a duplicate id has its own diagnostic)."""
  out = {}
  for u in units:
    out.setdefault(u["id"], u)
  return out


def _mark_method_collisions(units):
  """Two supported units whose action terms can name one action, one of them an effect or a restriction, are
  unsupported (`method_collision`)."""
  by_id = _first_by_id(units)
  for uid, hit in sorted(lc_action.method_collisions([u for u in units if u["status"] == "supported"]).items()):
    u = by_id[uid]
    for h in hit:
      u["diagnostics"].append({"level": "unsupported", "reason": "method_collision", "unit": uid, "path": "/",
                               "subformula": canonical(h["term"]), "with": h["with"],
                               "other_term": canonical(h["other_term"]),
                               "message": "the action term of this unit (source verb %s) and the term of unit %s "
                                          "(source verb %s) can name one action, and one of the two is an effect "
                                          "or a restriction" % (", ".join(h["roots"]), h["with"], ", ".join(h["other_roots"]))})
    u["status"] = "unsupported"


def _take(u, r, requirements=True):
  """A pass's compiled unit (`compile_unit` of a pass) into the unit record."""
  u.update({"situated": r["situated"], "situation": r["situation"], "clauses": r["clauses"],
            "witnesses": r["witnesses"], "compile_note": r["note"]})
  if requirements:
    u["requirements"] = r["requirements"]


def _unsupported(u, reason, message, pass_name, **fields):
  """An unsupported diagnostic of a later pass on a unit; the unit becomes unsupported."""
  d = {"level": "unsupported", "reason": reason, "unit": u["id"], "path": "/", "subformula": None,
       "message": message, "pass": pass_name}
  d.update(fields)
  u["diagnostics"].append(d)
  u["status"] = "unsupported"


def _situation_pass(units, namer):
  """The situation pass (`lc_action_situate`): situations, witnesses and the clauses of the state units."""
  for u in units:
    u.update({"situated": None, "situation": None, "clauses": None, "witnesses": [], "compile_note": None})
    if u["status"] != "supported":
      continue
    r = lc_action_situate.compile_unit(u, namer)
    _take(u, r, requirements=False)
    if r["diagnostic"]:
      sub = r["diagnostic"][2]
      _unsupported(u, r["diagnostic"][0], r["diagnostic"][1], lc_action_situate.PASS,
                   subformula=canonical(sub) if sub is not None else None)
    elif u["form"] in lc_action_situate.STATE_FORMS and u["clauses"] is None:
      raise ArtifactError("unit %s: the situation pass left a supported state unit without clauses" % u["id"])


def _action_passes(units, namer, prof, ident, classes, diagnostics):
  """The passes of the physical profile, in order: availability and denials, location granularity, the identity
  clauses, restrictions and their hooks, effects, the state policy and the dependencies.  Returns the source-level
  results: identity_clauses, restriction_clauses, restrictions, policy_clauses, dependencies, backend_requirements."""
  by_id = _first_by_id(units)
  for u in units:
    u["requirements"] = []
    if u["status"] != "supported" or u["form"] not in lc_action_avail.FORMS:
      continue
    r = lc_action_avail.compile_unit(u, namer, _library())
    _take(u, r)
    if r["diagnostic"]:
      _unsupported(u, r["diagnostic"][0], r["diagnostic"][1], lc_action_avail.PASS)
  for g in lc_action_avail.location_granularity(units, prof["locations"]["flat"], _places(ident)):
    d = {"level": "unsupported", "reason": "unsupported_location_granularity", "path": "/", "subformula": None,
         "message": g["message"], "pass": lc_action_avail.PASS}
    if g["unit_level"]:
      u = by_id[g["units"][0]]
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
    _take(u, r)
    checks[u["id"]] = r["checks"]
    if r["diagnostic"]:
      extra = {"detail": r["diagnostic"][2]} if r["diagnostic"][2] else {}
      _unsupported(u, r["diagnostic"][0], r["diagnostic"][1], lc_action_restrict.PASS, **extra)
  restriction_clauses, table = lc_action_restrict.hooks(units, checks, namer)
  restrictions = {"constructors": table, "paths": lc_action_restrict.path_coverage(_library(), table)}
  writes = []
  for u in units:
    if u["status"] != "supported" or u["form"] != lc_action_effects.FORM:
      continue
    r = lc_action_effects.compile_unit(u, namer, _library())
    _take(u, r)
    writes.extend(r["writes"])
    if r["diagnostic"]:
      _unsupported(u, r["diagnostic"][0], r["diagnostic"][1], lc_action_effects.PASS)
  policy_clauses, found, properties = lc_action_effects.state_policy(units, prof["policy"])
  for uid, reason, message, detail in found:
    u = by_id[uid]
    _unsupported(u, reason, message, lc_action_effects.PASS, detail=detail)
    u["clauses"] = []
  dependencies, backend_requirements = lc_action_effects.dependencies(units, _library(), classes)
  dependencies["writes"] = writes
  dependencies["properties"] = properties
  return {"identity_clauses": identity_clauses, "restriction_clauses": restriction_clauses,
          "restrictions": restrictions, "policy_clauses": policy_clauses, "dependencies": dependencies,
          "backend_requirements": backend_requirements}


def _source_diag(level, code, unit, message):
  d = {"level": level, "unit": unit, "path": "/", "subformula": None, "message": message}
  d["code" if level == "invalid" else "reason"] = code
  return d


READING_FORMS = {"availability": ("availability", "denial"), "restriction": ("restriction",),
                 "effect": ("effect",), "occurrence": ("ordinary_event",)}


def _check_reading(unit):
  """The Stage-1 action reading agrees with the recognized Stage-2 form.

  Checked only for a structurally supported unit: an unsupported form has its
  own diagnostic, and the reading of a mistranslation is part of that case.
  A reading that the sentence itself contradicts is adjusted (`action_repair.adjusted_reading`): the note `reading_adjusted`
  records the repair, the reading before and the reading after, and the unit is kept.
  """
  if unit["status"] != "supported" or unit["stage1"] is None:
    return
  reading = unit["stage1"].get("action_reading")
  law = unit["form"] in ("availability", "denial", "restriction", "effect")
  if reading is None and not law:
    return
  if reading is None or unit["form"] not in READING_FORMS.get(reading, ()):
    adjusted = arep.adjusted_reading(unit)
    if adjusted is not None:
      repair, after = adjusted
      unit["diagnostics"].append({"level": "note", "reason": "reading_adjusted", "unit": unit["id"], "path": "/",
                                  "subformula": None, "repair": repair, "before": reading, "after": after,
                                  "message": "Stage-1 action_reading %r is read as %r: the sentence and the Stage-2 "
                                             "form %s establish it (%s)" % (reading, after, unit["form"], repair)})
      return
    if arep.public_route_under_availability(unit):
      # A public service or route that Stage 1 labelled availability without an actor, compiled to the connected
      # fact the sentence states: the fact is kept and the label recorded.  A correction cannot change Stage 1, and
      # a correction request made the models invent a personal permission instead.
      unit["diagnostics"].append({"level": "note", "reason": "reading_adjusted", "unit": unit["id"], "path": "/",
                                  "subformula": None,
                                  "message": "Stage-1 action_reading 'availability' names no actor and the formula is the "
                                             "stated public route: the connected fact is kept as a static description"})
      return
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
      + list(artifact.get("identity_clauses") or []) + list(artifact.get("type_clauses") or [])
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

  `source_compiled` needs a supported source and no pending compiler pass.  A profile whose passes do not run
  (the `ordinary` profile) gives `not_implemented`, with the names of the pending passes.
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
  """The reachability seed depth of a discovery and the step allowance of a verification.

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
  backend profile decides it for the selected binary (`action_gk`).
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
  turn a partly supported source into a planning problem.

  A supported query of the action profile gets its input view (clause names
  and a view hash), its proof obligations and its backend requirements.  A
  query that needs an unvalidated capability stops with
  `unsupported_backend_requirement` and gets no view, unless only the
  negative obligation of a verification's final formula needs it: that query
  runs, and the answer policy refuses every answer but Yes.

  `planning_root` names a declared world (default: the last declared world);
  `ambient` a location entity whose scope facts the query's views keep;
  `knower` an entity whose knower-scoped facts they keep and whose constant
  replaces the objective knower of the laws.
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
  units and the root's world.
  """
  units = source_artifact["units"]
  action = source_artifact["profile"]["name"] == lc_action.PROFILE
  if action:
    q["excluded"] = lc_action_query.exclusions(units, sel)
    units = lc_action_query.admitted(units, q["excluded"])
  root = sel["planning_root"]
  grain = lc_action_avail.query_granularity(units, source_artifact["profile"]["locations"]["flat"], root,
                                            _places(source_artifact["identity"])) if action else []
  hit = lc_action_effects.query_transport(v["kind"], v["goal"], v["sequence"], units, source_artifact.get("dependencies"), root,
                                          type_facts(source_artifact))
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
  return lc_action_query.selection_of(query_artifact)


def _query_views(q, source_artifact, sel, units):
  """The query pass: backend requirements on the admitted `units`, then the input view and the obligations."""
  if source_artifact["pending_passes"]:
    return
  query = q["query"]
  needs = lc_action_query.backend_requirements(query, q["search"], units, source_artifact.get("dependencies"), _library(),
                                               sel["planning_root"], type_facts(source_artifact))
  q["backend_requirements"] = needs
  q["passes"], q["pending_passes"] = [lc_action_query.PASS], []
  # a requirement that only the negative polarity reads lets the query run; the answer policy decides at answer time
  missing = [n for n in needs if n["capability"] in lc_action_query.UNAVAILABLE
             and n["capability"] not in q["backend"]["validated"] and "positive" in n.get("polarities", ["positive"])]
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
  same_revision(source_artifact, query_artifact)
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


def same_revision(source_artifact, query_artifact):
  if query_artifact["source"]["source_hash"] != source_artifact["hashes"]["source"]:
    raise ArtifactError("the query artifact belongs to another source")
  if query_artifact["source"]["artifact_hash"] != source_artifact["hashes"]["artifact"]:
    raise ArtifactError("the query artifact was compiled against another revision of this source artifact "
                        "(a later pass or diagnostic changed it); compile the query again")


# ---------------------------------------------------------------------------
# results and the two operations


def result(outcome, **fields):
  """A result record.  `outcome` is a name of OUTCOMES or `not_implemented`."""
  if outcome not in OUTCOMES and outcome != NOT_IMPLEMENTED:
    raise ArtifactError("unknown outcome %r" % outcome)
  r = {"artifact": RESULT, "version": ARTIFACT_VERSION, "outcome": outcome,
       "answer": None, "plan": None, "diagnostics": [], "calls": {"model": 0, "gk": 0}}
  r.update(fields)
  return r


def translate_source(source_text, profile, model_options=None):
  """English to a source artifact with an action prompt bundle (`action_pipeline.translate`).

  `model_options`: {"bundle", "llm", "version", "max_tokens", "think"}; the default bundle is the measured one
  (`action_pipeline.DEFAULT_BUNDLE`).  Without the bundle's files the result is `not_implemented`.  A translation that holds a query package is
  `translation_invalid`: a source-only operation takes no question.  A failed translation is a result record
  with its typed outcome; a supported or unsupported translation is the source artifact.
  """
  prof = normalize_profile(profile)
  import action_pipeline
  opts = dict(model_options or {})
  bundle = action_pipeline.load_bundle(opts.get("bundle"))
  if bundle is None or prof["name"] != lc_action.PROFILE:
    return result(NOT_IMPLEMENTED, operation="translate_source",
                  detail="the action prompt bundle has missing files; use compile_source with a gold or replayed "
                         "translation" if bundle is None else "only the action profile has a translation")
  tr = action_pipeline.translate(source_text, bundle, opts.get("llm"), opts.get("version"), opts.get("max_tokens"),
                                 bool(opts.get("think")))
  if tr["status"] == "ok" and tr["queries"]:
    return result("translation_invalid", operation="translate_source",
                  errors=["a source-only translation holds the query package %s" % tr["queries"][0][1]])
  if tr["status"] == "ok" or (tr["status"] == "unsupported_translation" and tr["source"] is not None
                              and tr["source"]["support"]["status"] == "unsupported"):
    return tr["source"]
  if tr["status"] == "unsupported_translation":
    return result("unsupported_translation", operation="translate_source", **tr["unsupported"])
  return result(tr["status"], operation="translate_source", diagnostics=tr["errors"])


def solve_query(source_artifact, query_artifact, options=None):
  """Run a compiled query on the registered GK build and decide its answer (`action_answer.solve`).

  `options`: {"backend": a registered build name, "limits": the adapter's limits, "ledger": a run collector}.
  A query artifact that already has an outcome (invalid, unsupported, insufficient allowance) returns that
  outcome without a prover.  Artifact errors are raised before any launch.
  """
  import action_answer
  opts = dict(options or {})
  bad = sorted(set(opts) - {"backend", "limits", "ledger"})
  if bad:
    raise ArtifactError("unknown solve_query options %s" % bad)
  return action_answer.solve(source_artifact, query_artifact, opts.get("backend"), opts.get("limits"), opts.get("ledger"))
