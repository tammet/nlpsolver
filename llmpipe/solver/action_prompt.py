"""The action prompts and the checks of an action translation that read the prompts' annotation contract.

  validate_units(units)                    -> errors of the Stage-1 annotations (readings, actions, contexts)
  select_route(units)                      -> the route that Stage 1 asks for: actions, ordinary, diagnostic or invalid
  handoff_errors(units, envelope, packages, notes)  -> where Stage 2 does not carry what Stage 1 annotated
  derive_envelope, derived_fields, derived_probabilities, typing_cleanups, at_place_cleanup
                                           -> the normalizations of a Stage-2 response, each recorded
  class_condition_findings(units, packages) -> class conditions that a rule's own sentence does not state
  assemble(directory=PROMPTS)              -> the action prompt bundle: the two system prompts and their hashes

`action_pipeline` calls these from its controller.  A diagnostic route selection ends the translation with
`unsupported_translation`.  Each normalization is recorded by its kind (`types_relocated`, `derived_field`, ...;
docs/encodings/action-prompts.md, "What the controller normalizes").  This module does
not call a model or a prover.
"""
import json
import re
from pathlib import Path

import digests
import lc_action as la

ROOT = Path(__file__).resolve().parents[1]
# the action prompts: instructions, checklists, and the examples that the prompts show (the authored translations
# that no prompt shows are test material, in tests/action_route/unseen/)
PROMPTS = ROOT / "prompts/actions"
READINGS = {"availability", "restriction", "effect", "occurrence", "plan_question",
            "reachable_question", "executable_question", "verify_question"}
SELECTORS = {"planning_root", "ambient", "knower"}
TENSES = {"past", "present", "future"}
ENTITY_ROLES = ("actor", "target", "source", "destination", "location")
# the entity slots of each constructor (1-based argument positions); the means of move and the value of change are
# lexical
ENTITY_SLOTS = {"move": (1, 2, 3), "take": (1, 2), "put_on": (1, 2, 3), "put_in": (1, 2, 3), "change": (1, 2, 4)}
LAW_READINGS = {"availability", "restriction", "effect"}
# The ordinary role vocabulary, with the explicit actor used by this variant.
ROLES = {"actor", "target", "location", "location_prep", "instrument", "direction",
         "manner", "recipient", "destination", "source", "beneficiary", "accompaniment",
         "path", "result", "topic", "cause", "content"}


def contexts_for(units):
  """(contexts, selections) that Stage 1 decides: the context record of each source unit (its location, role,
  knower and the tense of an initial description), and the selection of the query unit (planning_root, ambient,
  knower).  The envelope of Stage 2 must carry the same values."""
  contexts, selections = {}, {}
  for u in units:
    uid = u["unit_id"]
    if u.get("type") == "query":
      sel = {k: u[k] for k in SELECTORS if k in u}
      if sel:
        selections[uid] = sel
    else:
      c = dict(u.get("context", {}))
      tense = u.get("time") if u.get("time") in TENSES else u.get("state_tense")
      # Law timing belongs in @time; occurrence time in its event formula.
      # The compiler accepts fact-context tense only on initial descriptions.
      if tense and not u.get("action_reading"):
        c["tense"] = tense
      if c:
        contexts[uid] = c
  return contexts, selections


def declared_worlds(units):
  """W0 and the snapshots that source units establish, in source order.

  A query selects a declared world with planning_root; it never establishes one.
  """
  out = ["W0"]
  for u in units:
    if u.get("type") == "query":
      continue
    for k in ("pre_state", "next_state"):
      if isinstance(u.get(k), str) and u[k] not in out:
        out.append(u[k])
  return out


def validate_units(units):
  """The errors of the Stage-1 action annotations: readings, actions and their roles, modes, contexts, the snapshot
  fields and the query selection.  [] when the annotations are valid."""
  errors = []
  ids = {e["id"] for u in units for e in (u.get("entities") or [])
         if isinstance(e, dict) and isinstance(e.get("id"), str)}
  worlds = set(declared_worlds(units))
  for u in units:
    uid = u["unit_id"]
    def bad(message):
      errors.append("unit %s: %s" % (uid, message))
    reading = u.get("action_reading")
    if reading is not None and (not isinstance(reading, str) or reading not in READINGS):
      bad("unknown action_reading")
      continue
    query = u.get("type") == "query"
    if query:
      for k in ("pre_state", "next_state"):
        if k in u:
          bad("a query selects its snapshot with planning_root, not %s" % k)
    if "location_role" in u:
      bad("location_role belongs inside context with its location; a query selects its scope location with ambient")
    if "actions" in u and (not isinstance(u["actions"], list) or
            any(not isinstance(a, dict) or not isinstance(a.get("roles"), dict) for a in u["actions"])):
      bad("actions must hold action objects with roles")
    elif "actions" in u:
      for i, action in enumerate(u["actions"]):
        unknown = set(action["roles"]) - ROLES
        if unknown:
          bad("actions[%d].roles: unknown roles %s; use instrument for travel means and "
              "location/location_prep for a support or container" % (i, ", ".join(sorted(unknown))))
    if reading and reading.endswith("_question") and not query:
      bad("question reading needs type query")
    if "step_bound" in u:
      b = u["step_bound"]
      if reading == "verify_question":
        bad("a verify_question has no step_bound; \"with no actions performed\" is an empty actions list")
      elif reading not in ("plan_question", "reachable_question"):
        bad("step_bound belongs to a plan_question or a reachable_question")
      elif (not isinstance(b, dict) or set(b) != {"comparison", "count"}
              or b.get("comparison") not in ("at_most", "exactly")
              or type(b.get("count")) is not int or b["count"] < 0):
        bad("invalid step_bound: {\"comparison\": \"at_most\" | \"exactly\", \"count\": N} with N >= 0")
    if "action_order" in u or reading == "verify_question":
      if (reading != "verify_question" or u.get("action_order") != "sequence"
              or not isinstance(u.get("actions"), list)):
        bad("verification needs action_order sequence and an actions list")
    for k in sorted(SELECTORS & u.keys()):
      v = u[k]
      if not query:
        bad("%s selects a view on the query unit; a source fact's viewpoint and scope location go inside context" % k)
      elif not isinstance(v, str):
        bad("%s must be a string" % k)
      elif k == "planning_root" and v not in worlds:
        bad("planning_root names a declared world: W0 or a snapshot that a source unit establishes")
      elif k == "ambient" and v not in ids:
        bad("ambient is a location entity; a snapshot goes in planning_root" if v in worlds or re.fullmatch(r"W\d+", v)
            else "ambient must be a location entity id of the passage")
      elif k == "knower" and v not in ids:
        bad("knower must be an entity id of the passage")
    if "context" in u:
      c = u["context"]
      if query:
        bad("a query selects with ambient and knower, not context")
      elif not isinstance(c, dict) or set(c) - {"location", "location_role", "knower"}:
        bad("invalid context: its entries are location, location_role and knower (tense uses time/state_tense)")
      else:
        if bool("location" in c) != bool("location_role" in c):
          bad("context location needs its role")
        if "location_role" in c and c["location_role"] not in ("provenance", "scope"):
          bad("invalid location_role")
        for k in ("location", "knower"):
          if k in c and (not isinstance(c[k], str) or c[k] not in ids):
            bad("unknown context %s" % k)
        if "location" in c and "location" in u and c["location"] != u["location"]:
          bad("conflicting location annotations")
    if "time" in u and not isinstance(u["time"], str):
      bad("time must be a string")
    if "state_tense" in u and (not isinstance(u["state_tense"], str) or u["state_tense"] not in TENSES):
      bad("invalid state_tense")
    if isinstance(u.get("time"), str) and u["time"] in TENSES and "state_tense" in u and u["state_tense"] != u["time"]:
      bad("conflicting tense annotations")
    if "action_issue" in u:
      x = u["action_issue"]
      if (not isinstance(x, dict) or set(x) != {"kind", "text", "detail"}
              or x.get("kind") not in ("ambiguous", "unsupported")
              or not all(isinstance(x.get(k), str) and x[k].strip() for k in ("text", "detail"))):
        bad("invalid action_issue")
  return errors


def select_route(units):
  """The route that the Stage-1 annotations ask for, with its reasons: `invalid` (annotation errors), `diagnostic` (an
  ambiguous or unsupported request, which ends the translation), `actions` (an action reading or a planning
  question), or `ordinary`."""
  errors = validate_units(units)
  if errors:
    return {"route_selected": "invalid", "route_reasons": errors}
  issues = [{"unit": u["unit_id"], "reason": "ambiguous_directive" if
             u["action_issue"]["kind"] == "ambiguous" else "unsupported_request",
             **u["action_issue"]} for u in units if "action_issue" in u]
  if issues:
    return {"route_selected": "diagnostic", "route_reasons": issues}
  triggers = [{"unit": u["unit_id"], "reading": u["action_reading"]} for u in units
              if u.get("action_reading") in READINGS - {"occurrence"}]
  return {"route_selected": "actions" if triggers else "ordinary",
          "route_reasons": triggers or ["no_action_request_or_law"]}


def handoff_errors(units, envelope, packages, notes=None):
  """Compare annotations with the logic handoff; never infer missing meaning.  `notes` receives the forms accepted
  with a note: an explicit planning root equal to the only declared world (`root_explicit_default`), and a class at a
  later mention whose text names the entity with that class noun (`later_class_accepted`, in `types_errors`)."""
  errors = []
  notes = [] if notes is None else notes
  byid = {u["unit_id"]: u for u in units}
  if len(packages) != len(byid) or {p[1] for p in packages} != set(byid):
    errors.append("unit coverage: every Stage-1 id needs exactly one Stage-2 package")
  wanted_contexts, wanted_selections = contexts_for(units)
  if (envelope.get("worlds") or ["W0"]) != declared_worlds(units):
    errors.append("worlds differ from Stage-1 source order: expected %s, got %s" % (
        json.dumps(declared_worlds(units)), json.dumps(envelope.get("worlds"))))
  actual_contexts = envelope.get("contexts", {})
  if not isinstance(actual_contexts, dict):
    errors.append("contexts must be an object")
  else:
    for uid in sorted(actual_contexts.keys() | wanted_contexts.keys()):
      if actual_contexts.get(uid) != wanted_contexts.get(uid):
        errors.append(_context_message(uid, byid.get(uid), wanted_contexts.get(uid), actual_contexts.get(uid)))
  got = envelope.get("query_contexts") or {}
  compared = dict(got) if isinstance(got, dict) else got
  if isinstance(got, dict) and declared_worlds(units) == ["W0"]:
    # an explicit root equal to the only declared world is the default root; the selection stays as given
    for uid, sel in got.items():
      if uid not in wanted_selections and sel == {"planning_root": "W0"}:
        del compared[uid]
        notes.append({"kind": "root_explicit_default", "unit": uid})
  if compared != wanted_selections:
    errors.append("query_contexts differ from Stage 1: expected %s, got %s" %
                  (json.dumps(wanted_selections, sort_keys=True), json.dumps(got, sort_keys=True)))
  errors.extend(_hand_class_errors(units, packages, envelope.get("types")))
  errors.extend(types_errors(units, envelope.get("types", {}), notes))
  first = first_mentions(units)
  concrete = _concrete_ids(units)
  for p in packages:
    u = byid.get(p[1])
    if not u:
      continue
    f, r = p[2], u.get("action_reading")
    capability = any(isinstance(a, dict) and a.get("mode") == "capability" for a in u.get("actions") or [])
    if (r in LAW_READINGS or r is None and capability) and u.get("type") != "query":
      law = _source_formula(f)
      errors.extend(_normally_errors(p[1], law))
      errors.extend(_law_class_errors(p[1], law, u, first, byid))
    if not isinstance(f, list) or not f or not isinstance(f[0], str):
      errors.append("unit %s: malformed package" % p[1])
      continue
    if u.get("type") == "query":
      kind = {"plan_question": "plan", "reachable_question": "reachable",
              "verify_question": "verify", "executable_question": "question"}.get(r)
      asked = ask_executable(f)
      if r == "executable_question" and asked:
        # K4: ["ask", V, ["executable", ACTION]] with V in one entity slot of ACTION
        notes.append({"kind": "ask_executable", "repair": "K4", "unit": p[1], "variable": f[1],
                      "slot": asked})
      elif kind and f[0] != kind or not kind and f[0] not in ("question", "ask"):
        errors.append("unit %s: query reading/package mismatch: %s" % (p[1], query_form(r)))
      elif r == "executable_question" and (len(f) < 2 or not isinstance(f[1], list)
                                           or f[1][:1] != ["executable"]):
        errors.append("unit %s: expected executable question: %s" % (p[1], query_form(r)))
      if f[0] == "question" and len(f) > 1 and isinstance(f[1], list) and f[1][:1] == ["executable"] and r != "executable_question":
        errors.append("unit %s: executable question needs its reading: [\"question\",[\"executable\","
                      "ACTION]] is the form of the reading executable_question; %s" % (p[1], query_form(r)))
      if f[0] in ("plan", "reachable") and (len(f) > 3 or len(f) < 2 or
                                           (len(f) == 3 and not (isinstance(f[2], list) and f[2][:1] == ["steps"]))):
        errors.append("unit %s: a %s package is [\"%s\",GOAL] or [\"%s\",GOAL,[\"steps\",COMPARISON,N]]; the goal "
                      "is one formula, a conjunction one [\"and\",...] list" % (p[1], f[0], f[0], f[0]))
      elif f[0] in ("plan", "reachable"):
        b = u.get("step_bound")
        expected = ["steps", b["comparison"], b["count"]] if b else None
        if (f[2] if len(f) > 2 else None) != expected:
          errors.append("unit %s: step_bound mismatch" % p[1])
      if f[0] == "verify" and (u.get("action_order") != "sequence" or
              len(f) < 2 or not isinstance(f[1], list) or len(f[1]) != len(u.get("actions", []))):
        errors.append("unit %s: supplied sequence mismatch" % p[1])
      elif f[0] == "verify":
        for natural, term in zip(u["actions"], f[1]):
          slots = {"move": {"actor": 1, "source": 2, "destination": 3, "instrument": 4},
                   "take": {"actor": 1, "target": 2},
                   "put_on": {"actor": 1, "target": 2, "location": 3},
                   "put_in": {"actor": 1, "target": 2, "location": 3},
                   "change": {"actor": 1, "target": 2, "result": 3, "instrument": 4}}
          if not isinstance(term, list) or not term or not isinstance(term[0], str):
            errors.append("unit %s: malformed sequence action" % p[1])
            continue
          roles = natural.get("roles", {})
          # Natural verb roots are open vocabulary. Participants and
          # sequence position are checkable without a synonym list.
          # Extra ordinary roles may describe a precondition or an
          # instrument phrase without a same-named constructor slot.
          # K3: an entity role (the tool is the instrument of change) is
          # compared only when it holds a declared concrete id; the
          # result, the travel means and the preposition stay compared.
          wrong = False
          for k, pos in slots.get(term[0], {}).items():
            if k not in roles:
              continue
            entity = k in ENTITY_ROLES or (k == "instrument" and term[0] == "change")
            differs = len(term) <= pos or roles[k] != term[pos]
            if differs and entity and roles[k] not in concrete:
              notes.append({"kind": "verify_role_not_compared", "repair": "K3", "unit": p[1],
                            "role": k, "stage1": roles[k],
                            "term": term[pos] if len(term) > pos else None})
            elif differs:
              wrong = True
          prep = roles.get("location_prep")
          if term[0] in ("put_on", "put_in") and prep in ("on", "in", "inside"):
            wrong = wrong or (term[0] == "put_on") != (prep == "on")
          if wrong:
            errors.append("unit %s: supplied action order/participants mismatch" % p[1])
    elif f[0] in ("question", "ask", "plan", "reachable", "verify"):
      errors.append("unit %s: source became a query" % p[1])
    else:
      body = f[1] if f[0] == "and" and len(f) > 1 else f
      if isinstance(body, list) and body[:1] == ["holds"] and len(body) > 1 and body[1] != u.get("pre_state", "W0"):
        errors.append("unit %s: source world differs from pre_state" % p[1])
      probability = f[2][2] if (f[0] == "and" and len(f) == 3 and isinstance(f[2], list)
                                 and f[2][:1] == ["@p"] and len(f[2]) == 3) else None
      expected = expected_probability(u)
      if probability != expected:
        errors.append(confidence_message(p[1], probability, expected, u.get("confidence")))
  return errors


def ask_executable(f):
  """K4: the slot position of V in ["ask", V, ["executable", ACTION]] when V is a variable that stands in exactly
  one argument of ACTION and that argument is an entity slot (the actor of a who-question, the object of a
  which-object question); else None."""
  if not (isinstance(f, list) and len(f) == 3 and f[0] == "ask" and isinstance(f[1], str) and VARIABLE.match(f[1])
          and isinstance(f[2], list) and len(f[2]) == 2 and f[2][0] == "executable" and isinstance(f[2][1], list)
          and f[2][1] and f[2][1][0] in ENTITY_SLOTS):
    return None
  action = f[2][1]
  where = [i for i, x in enumerate(action[1:], 1) if x == f[1]]
  if len(where) != 1 or where[0] not in ENTITY_SLOTS[action[0]]:
    return None
  return where[0]


# K13: the query form of each Stage-1 reading, named in a message about a query package
QUERY_FORMS = {
    "plan_question": "[\"plan\",GOAL], or [\"plan\",GOAL,[\"steps\",COMPARISON,N]] with a step bound",
    "reachable_question": "[\"reachable\",GOAL], or [\"reachable\",GOAL,[\"steps\",COMPARISON,N]] with a step bound",
    "verify_question": "[\"verify\",[ACTION,...],GOAL] with one action term per supplied step",
    "executable_question": "[\"question\",[\"executable\",ACTION]], or [\"ask\",V,[\"executable\",ACTION]] for a "
                           "who- or which-question, with V in the actor or the object slot",
}


def query_form(reading):
  """The sentence that names the query form of a Stage-1 reading (K13)."""
  if reading in QUERY_FORMS:
    return "the Stage-1 reading %s has the form %s" % (reading, QUERY_FORMS[reading])
  return ("a query unit without an action reading has the form [\"question\",FORMULA] or [\"ask\",V,FORMULA] "
          "over the state; a yes-no question about an action has the reading executable_question")


def expected_probability(u):
  """The @p of a source unit's package: the Stage-1 confidence, or None for no @p.

  The two ordinary conventions give no @p: 0.99 of an indefinite article and 0.98 of a normal rule.  Explicit
  probability words or numbers in the unit's text make the number a stated probability.
  """
  confidence = u.get("confidence")
  explicit = bool(re.search(r"probab|likely|chance|\d\s*%|0\.\d", u.get("text") or "", re.I))
  inherited = not explicit and (confidence == 0.99 or confidence == 0.98 and u.get("type") == "normal_rule")
  return None if confidence in (None, 1) or inherited else confidence


def confidence_message(uid, got, expected, confidence):
  """Name the confidence convention that applies to one unit, and the fix."""
  if expected is None and got is not None:
    if confidence == 0.99:
      return "unit %s: omit @p; 0.99 comes from the indefinite article and the text states no probability" % uid
    if confidence == 0.98:
      return "unit %s: normally produces no @p; drop %s" % (uid, got)
    return "unit %s: Stage 1 states no probability below 1; omit @p %s" % (uid, got)
  if got is None:
    return ("unit %s: the text states probability %s; write [\"and\",[\"holds\",WORLD,FORMULA],[\"@p\",\"%s\",%s]]"
            % (uid, expected, uid, expected))
  return "unit %s: @p must be %s as Stage 1 states, not %s" % (uid, expected, got)


def _context_message(uid, u, wanted, got):
  """A context mismatch, with the rule that decides where the record belongs."""
  message = "unit %s: context should be %s from Stage 1; got %s" % (
      uid, json.dumps(wanted, sort_keys=True), json.dumps(got, sort_keys=True))
  if u is None:
    return message + "; contexts names only Stage-1 units"
  reading = u.get("action_reading")
  extra = sorted(set(got or {}) - {"location", "location_role", "knower", "tense"})
  if extra:
    return message + ("; a context record holds only location, location_role, knower and tense (%s is not an "
                      "entry; the timing of an action rule goes in @time)" % ", ".join(extra))
  if reading and (got or {}).get("tense"):
    if reading == "occurrence":
      return message + "; an occurrence keeps its time as a has time atom in its event formula, not as a context tense"
    return message + "; the timing of an action rule goes in @time, not in contexts"
  if not reading and (wanted or {}).get("tense") and not (got or {}).get("tense"):
    return message + ("; an initial description takes its tense from Stage-1 time or state_tense: add \"tense\": \"%s\""
                      % wanted["tense"])
  return message


def head_noun(entity_id):
  words = re.sub(r"\s+\d+$", "", entity_id).split()
  return words[-1].lower() if words else ""


def _hand_class_errors(units, packages, types=None):
  """A concrete Stage-1 entity whose head noun is hand needs the reserved class hand in the Stage-2 source.

  The check reads the Stage-1 annotation and requests a correction; it adds no fact.  A hand first named in a
  law sentence states its class in the envelope field types.
  """
  hands = []
  for u in units:
    for e in u.get("entities") or []:
      if (isinstance(e, dict) and e.get("type") == "concrete" and isinstance(e.get("id"), str)
              and head_noun(e["id"]) == "hand" and e["id"] not in hands):
        hands.append(e["id"])
  if not hands:
    return []
  found = set()

  def walk(f):
    if isinstance(f, list):
      if len(f) == 3 and f[0] == "isa" and f[1] == "hand":
        found.add(f[2])
      for x in f:
        walk(x)
  for p in packages:
    if isinstance(p[2], list) and p[2][:1] and p[2][0] not in ("question", "ask", "plan", "reachable", "verify"):
      walk(p[2])
  if isinstance(types, dict):
    walk(list(types.values()))
  first = first_mentions(units)
  byid = {u["unit_id"]: u for u in units}
  out = []
  for h in hands:
    if h in found:
      continue
    where = first.get(h)
    law = where is not None and (byid[where].get("action_reading") in LAW_READINGS)
    out.append("entity %s: its head noun is hand, so state [\"isa\",\"hand\",\"%s\"] once%s; a compound class such "
               "as robot hand may stay beside it" % (
                   h, h, " in the envelope field types: {\"%s\": [[\"isa\",\"hand\",\"%s\"]]}" % (where, h) if law
                   else " in unit %s, where it is first named" % where if where else ""))
  return out


def _source_formula(body):
  """The formula of a source package: holds(W, F) or the confidence form and(holds(W, F), @p)."""
  if isinstance(body, list) and body[:1] == ["and"] and len(body) > 1 and isinstance(body[1], list):
    body = body[1]
  if isinstance(body, list) and body[:1] == ["holds"] and len(body) == 3:
    return body[2]
  return None


def is_class_atom(a):
  return (isinstance(a, list) and len(a) == 3 and a[0] == "isa" and isinstance(a[1], str) and isinstance(a[2], str)
          and CONCRETE.match(a[2]) is not None)


CONCRETE = la.CONCRETE
VARIABLE = la.VAR


def self_named(a):
  """["isa","Dock","Dock 3"]: a capitalized class equal to the name part of its id; it states nothing."""
  return (isinstance(a, list) and len(a) == 3 and a[0] == "isa" and isinstance(a[1], str) and isinstance(a[2], str)
          and a[1][:1].isupper() and re.fullmatch(re.escape(a[1]) + r" \d+", a[2]) is not None)


def _concrete_ids(units):
  return {e["id"] for u in units for e in u.get("entities") or []
          if isinstance(e, dict) and e.get("type") == "concrete" and isinstance(e.get("id"), str)}


def typing_cleanups(units, envelope):
  """The narrow typing cleanups, applied to a parsed Stage-2 envelope in place.  Returns notes, each with its kind:

    types_relocated     a types entry keyed by a description unit (no action reading, no probability package) is
                        conjoined into that unit's formula when the atom is ["isa", lowercase class, ID], the unit's
                        Stage-1 entities list ID and the class noun names ID in the unit's text
    types_dropped       a types entry whose third argument is no concrete Stage-1 entity (a variable, a generic id,
                        another string) is dropped: it denotes nothing
    self_class_dropped  ["isa", C, "C n"] with a capitalized C equal to the id's name part is dropped from types and
                        from the top-level conjunction of a description; it states nothing
  Every other form is left for the validator, whose correction then runs: an entry for a concrete entity of another
  unit, a class the unit's text does not name, a unit with a probability, the same atom inside a rule antecedent.
  """
  notes = []
  byid = {u["unit_id"]: u for u in units}
  concrete = _concrete_ids(units)
  logic = envelope.get("logic")
  packages = logic[1:] if isinstance(logic, list) and logic[:1] == ["and"] else logic if isinstance(logic, list) else []
  by_package = {p[1]: p for p in packages if isinstance(p, list) and len(p) == 3 and p[0] == "@id"}

  def description(uid):
    u = byid.get(uid)
    return u is not None and u.get("type") != "query" and not u.get("action_reading")
  for uid, p in by_package.items():
    body = p[2]
    if description(uid) and isinstance(body, list) and body[:1] == ["holds"] and len(body) == 3 \
            and isinstance(body[2], list) and body[2][:1] == ["and"]:
      kept = [x for x in body[2][1:] if not self_named(x)]
      if kept and len(kept) < len(body[2]) - 1:
        for x in body[2][1:]:
          if self_named(x):
            notes.append({"kind": "self_class_dropped", "unit": uid, "atom": x})
        body[2] = kept[0] if len(kept) == 1 else ["and"] + kept
  types = envelope.get("types")
  if not isinstance(types, dict):
    return notes
  keep, placed = {}, {}
  for uid, atoms in types.items():
    u = byid.get(uid)
    if u is None or not isinstance(atoms, list):
      keep[uid] = atoms
      continue
    for a in atoms:
      if not (isinstance(a, list) and len(a) == 3 and a[0] == "isa" and isinstance(a[1], str)
              and isinstance(a[2], str)):
        keep.setdefault(uid, []).append(a)
      elif self_named(a):
        notes.append({"kind": "self_class_dropped", "unit": uid, "atom": a, "in": "types"})
      elif a[2] not in concrete:
        notes.append({"kind": "types_dropped", "unit": uid, "atom": a})
      elif (description(uid) and uid in by_package and isinstance(by_package[uid][2], list)
            and by_package[uid][2][:1] == ["holds"] and len(by_package[uid][2]) == 3
            and re.fullmatch(r"[a-z][a-z0-9_ ]*", a[1])
            and a[2] in {e["id"] for e in u.get("entities") or [] if isinstance(e, dict)}
            and names_class(u.get("text"), a[1], a[2])):
        body = by_package[uid][2]
        f = body[2]
        if a not in la.conjuncts(f):
          # the relocated atoms lead the conjunction, in their order in types
          items = f[1:] if isinstance(f, list) and f[:1] == ["and"] else [f]
          n = placed.get(uid, 0)
          body[2] = ["and"] + items[:n] + [a] + items[n:]
          placed[uid] = n + 1
        notes.append({"kind": "types_relocated", "unit": uid, "atom": a})
      else:
        keep.setdefault(uid, []).append(a)
  if keep:
    envelope["types"] = keep
  else:
    envelope.pop("types", None)
  return notes


def first_mentions(units):
  """{entity id: the source unit that first lists it among its Stage-1 concrete entities}.  A query is no source."""
  out = {}
  for u in units:
    if u.get("type") == "query":
      continue
    for e in u.get("entities") or []:
      if isinstance(e, dict) and e.get("type") == "concrete" and isinstance(e.get("id"), str):
        out.setdefault(e["id"], u["unit_id"])
  return out


def names_class(text, cls, entity):
  """Whether the class noun `cls` names `entity` in a unit's normalized text, as in "the table 5", "the robot hand 1"
  or "Block b 3", and the text does not predicate the class of it ("b 3 was a block" is a class statement)."""
  if not isinstance(text, str) or not isinstance(cls, str) or not isinstance(entity, str):
    return False
  low, e, c = " ".join(text.lower().split()), re.escape(entity.lower()), re.escape(cls.lower())
  if re.search(r"(?<!\w)%s (?:is|are|was|were|becomes|became|remains|remained) (?:not )?(?:a |an |the )?%s(?!\w)"
               % (e, c), low):
    return False
  return head_noun(entity) == cls.lower() or re.search(r"(?<!\w)%s %s(?!\w)" % (c, e), low) is not None


def _normally_errors(uid, formula):
  """normally above a quantifier or an implication (as in "normally, every cook can boil an egg unless ..."): the
  grammar reads a default only on the can head.  Reported for correction; nothing is rewritten."""
  out = []

  def walk(f):
    if not isinstance(f, list) or not f:
      return
    if (f[0] == "normally" and len(f) == 2 and isinstance(f[1], list) and f[1][:1]
            and f[1][0] in ("forall", "exists", "implies", "and") and la.contains(f[1], {"can"})):
      out.append("unit %s: normally wraps the can head only: [\"forall\",V,[\"implies\",CONDITION,[\"normally\","
                 "[\"can\",ACTOR,ACTION]]]]; it does not stand above %s" % (uid, f[1][0]))
      return
    for x in f[1:]:
      walk(x)
  walk(formula)
  return out


def _law_class_errors(uid, formula, unit, first, byid):
  """Class atoms of concrete entities conjoined with a law: a law unit holds its rule only.  The message names where the class fact belongs; it drops nothing by itself."""
  f = formula
  while isinstance(f, list) and f[:1] == ["forall"] and len(f) == 3:
    f = f[2]
  if not (isinstance(f, list) and f[:1] == ["and"]):
    return []
  parts = f[1:]
  laws = [x for x in parts if la.contains(x, {"can", "after", "executable"})]
  atoms = [x for x in parts if is_class_atom(x)]
  if not laws or not atoms or len(laws) + len(atoms) != len(parts):
    return []
  out = []
  for a in atoms:
    where = first.get(a[2])
    text = "unit %s: a law unit holds its rule only; %s" % (uid, json.dumps(a))
    if where == uid and names_class(unit.get("text"), a[1], a[2]):
      out.append(text + " is the class of a referent this sentence introduces: state it in the envelope field "
                 "types: {\"%s\": [%s]}" % (uid, json.dumps(a)))
    elif where and where != uid:
      out.append(text + " belongs once to %s, where %s is first named, if that sentence names its class" % (
          "the envelope field types of unit %s" % where if byid[where].get("action_reading") else "unit %s" % where,
          a[2]))
    else:
      out.append(text + " states a class that this sentence does not name; remove it (a person's class that no "
                 "sentence states comes from Stage 1)")
  return out


def types_errors(units, types, notes=None):
  """The envelope field types: {law unit id: [["isa", CLASS, ID], ...]}, the classes of the referents that a law
  sentence introduces.  A class of an entity first named in an earlier unit is accepted when this unit's text names
  the entity with that class noun (the note `later_class_accepted`, no error)."""
  if types in (None, {}):
    return []
  if not isinstance(types, dict):
    return ["types must be an object {unit id: [[\"isa\",CLASS,ID], ...]}"]
  notes = [] if notes is None else notes
  byid = {u["unit_id"]: u for u in units}
  first = first_mentions(units)
  concrete = _concrete_ids(units)
  out = []
  for uid, atoms in types.items():
    u = byid.get(uid)
    if u is None or u.get("type") == "query":
      out.append("types names %s, which is no source unit" % uid)
      continue
    if u.get("action_reading") not in LAW_READINGS:
      out.append("unit %s: a description states its class facts in its own formula; types holds the classes of "
                 "referents that a law sentence introduces" % uid)
      continue
    if not isinstance(atoms, list) or not atoms:
      out.append("unit %s: types holds a non-empty list of [\"isa\",CLASS,ID] atoms" % uid)
      continue
    mentioned = {e["id"] for e in u.get("entities") or [] if isinstance(e, dict) and e.get("type") == "concrete"}
    for a in atoms:
      if not (isinstance(a, list) and len(a) == 3 and a[0] == "isa" and isinstance(a[1], str)
              and isinstance(a[2], str)):
        out.append("unit %s: types holds [\"isa\",CLASS,ID] atoms, got %s" % (uid, json.dumps(a)))
      elif VARIABLE.match(a[2]):
        out.append("unit %s: %s is a variable of the rule; its class stays in the rule's guard; remove it from "
                   "types" % (uid, a[2]))
      elif self_named(a):
        out.append("unit %s: %s is a proper name; a proper name gets no class unless a sentence states one; "
                   "remove this atom" % (uid, a[2]))
      elif a[2] not in concrete:
        out.append("unit %s: %s is no entity of Stage 1%s; write no class for it" % (
            uid, a[2], "; a service or a route is a connected fact" if re.search(r"service|route|line", a[2])
            else ""))
      elif not re.fullmatch(r"[a-z][a-z0-9_ ]*", a[1]):
        out.append("unit %s: a class is a lowercase word, got %s" % (uid, json.dumps(a[1])))
      elif a[2] not in mentioned:
        out.append("unit %s: types names %s, which this unit does not mention" % (uid, a[2]))
      elif first.get(a[2]) != uid:
        if names_class(u.get("text"), a[1], a[2]):
          notes.append({"kind": "later_class_accepted", "unit": uid, "atom": a})
        else:
          out.append("unit %s: %s is first named in unit %s; its class is stated there, once"
                     % (uid, a[2], first.get(a[2])))
  return out


def derive_envelope(units, parsed):
  """The Stage-2 envelope with every field the model left out derived from the validated Stage-1 units.

  Returns (envelope, derived field names), or (None, []) when `parsed` is neither a logic list nor an object.
  A supplied field is kept as given: handoff_errors checks it against Stage 1 without relaxation.  The derivation
  reads the same Stage-1 functions as that check, so a root, a past tense or a knower that validated Stage 1 states
  cannot be lost; it cannot supply one that Stage 1 omitted.  `types` is model content and is never derived.
  """
  if isinstance(parsed, dict):
    env = dict(parsed)
  elif isinstance(parsed, list):
    env = {"logic": parsed}
  else:
    return None, []
  contexts, selections = contexts_for(units)
  wanted = {"worlds": declared_worlds(units), "contexts": contexts, "query_contexts": selections}
  derived = [k for k in ("worlds", "contexts", "query_contexts") if k not in env]
  for k in derived:
    env[k] = json.loads(json.dumps(wanted[k]))
  return env, derived


# the value an absent or empty envelope field stands for
FIELD_DEFAULTS = {"worlds": ["W0"], "contexts": {}, "query_contexts": {}}


def derived_fields(units, envelope):
  """The envelope fields worlds, contexts and query_contexts take the values derived from the validated Stage-1
  units, in place.  Stage 1 decides them, so the model's copy adds no information.  Returns one note per field whose
  supplied value differs, with the model's value and the derived one.  An empty value that stands for the derived
  default (no worlds for ["W0"], null for {}) takes the derived value without a note.
  """
  contexts, selections = contexts_for(units)
  wanted = {"worlds": declared_worlds(units), "contexts": contexts, "query_contexts": selections}
  notes = []
  for k, v in wanted.items():
    given = envelope.get(k)
    if given == v:
      continue
    if (given or FIELD_DEFAULTS[k]) != v:
      notes.append({"kind": "derived_field", "field": k, "model": given, "derived": v})
    envelope[k] = json.loads(json.dumps(v))
  return notes


def derived_probabilities(units, packages):
  """The @p of each source package is the one that Stage 1 and the unit's text decide (`expected_probability`), in
  place.  A package ["holds", W, F] or ["and", ["holds", W, F], ["@p", ID, P]] whose annotation differs from
  ["@p", its unit id, the expected value] gets that annotation, or none.  Returns one note per replaced annotation,
  with the model's annotation.  Another package form is left for the validator.
  """
  byid = {u["unit_id"]: u for u in units}
  notes = []
  for p in packages:
    u, f = byid.get(p[1]), p[2]
    if u is None or u.get("type") == "query" or not isinstance(f, list):
      continue
    if f[:1] == ["holds"]:
      base, given = f, None
    elif (f[:1] == ["and"] and len(f) == 3 and isinstance(f[1], list) and f[1][:1] == ["holds"]
          and isinstance(f[2], list) and f[2][:1] == ["@p"] and len(f[2]) == 3):
      base, given = f[1], f[2]
    else:
      continue
    want = expected_probability(u)
    annotation = None if want is None else ["@p", p[1], want]
    if given != annotation:
      p[2] = base if annotation is None else ["and", base, annotation]
      notes.append({"kind": "derived_probability", "unit": p[1], "model": given, "derived": want})
  return notes


def at_place_cleanup(units, envelope):
  """["is rel2", "in", A, B] becomes ["is rel2", "located_at", A, B] when Stage 1 gives A only the category person
  and gives B the category place: a person in a city is at that place, in the encoding's relation.  In place, in every
  package.  An object in a container and a place in a place keep "in".  Returns one note per rewritten atom."""
  categories = {}
  for u in units:
    for e in u.get("entities") or []:
      if isinstance(e, dict) and isinstance(e.get("id"), str) and e.get("category"):
        categories.setdefault(e["id"], set()).add(e["category"])
  logic = envelope.get("logic")
  packages = logic[1:] if isinstance(logic, list) and logic[:1] == ["and"] else logic if isinstance(logic, list) else []
  notes = []

  def rewrite(f, uid):
    if not isinstance(f, list):
      return f
    if (len(f) == 4 and f[:2] == ["is rel2", "in"] and isinstance(f[2], str) and isinstance(f[3], str)
            and categories.get(f[2]) == {"person"} and "place" in categories.get(f[3], ())):
      notes.append({"kind": "person_at_place", "unit": uid, "atom": f})
      return ["is rel2", "located_at", f[2], f[3]]
    return [rewrite(x, uid) for x in f]
  for p in packages:
    if isinstance(p, list) and len(p) == 3 and p[0] == "@id":
      p[2] = rewrite(p[2], p[1])
  return notes


# classes a Stage-2 fact can state of a concrete entity that exclude the person reading (the reviewed list of the
# round-3 person convention); an unlisted class is no evidence either way
NON_PERSON_CLASSES = ("robot", "machine", "vehicle", "animal")


def person_types(units, packages, types=None):
  """The source-derived person classifications of the action profile.

  A concrete entity gets one static person type when an objective source unit (no knower, no scope location; a
  query is no source) lists it with the Stage-1 category person, and nothing states otherwise.  The record keeps the
  supporting units: it is an LLM's Stage-1 interpretation, which the compiler does not verify.  No type comes from
  being an actor, from a name, or from a query-only mention.  Returns (records, notes): a note reports a conflicting
  Stage-1 category, a stated class of NON_PERSON_CLASSES or a stated negative person fact, and suppresses the type.
  An entity whose source already states isa person needs no record.
  """
  stated, negative = {}, {}
  for p in packages:
    u = next((x for x in units if x["unit_id"] == p[1]), None)
    if u is None or u.get("type") == "query" or u.get("action_reading"):
      continue
    for a in la.conjuncts(_source_formula(p[2])):
      if is_class_atom(a):
        stated.setdefault(a[2], set()).add(a[1])
      elif isinstance(a, list) and len(a) == 2 and a[0] == "not" and is_class_atom(a[1]):
        negative.setdefault(a[1][2], set()).add(a[1][1])
  for atoms in (types or {}).values() if isinstance(types, dict) else []:
    for a in atoms if isinstance(atoms, list) else []:
      if is_class_atom(a):
        stated.setdefault(a[2], set()).add(a[1])
  categories, support = {}, {}
  for u in units:
    if u.get("type") == "query":
      continue
    c = u.get("context") or {}
    objective = c.get("knower") is None and c.get("location_role") != "scope"
    for e in u.get("entities") or []:
      if not (isinstance(e, dict) and e.get("type") == "concrete" and isinstance(e.get("id"), str)):
        continue
      if isinstance(e.get("category"), str):
        categories.setdefault(e["id"], {}).setdefault(e["category"], []).append(u["unit_id"])
        if e["category"] == "person" and objective and u["unit_id"] not in support.get(e["id"], []):
          support.setdefault(e["id"], []).append(u["unit_id"])
  records, notes = [], []
  for ent in sorted(support):
    if "person" in stated.get(ent, ()):
      continue
    others = sorted(k for k in categories[ent] if k != "person")
    blocked = sorted(stated.get(ent, set()) & set(NON_PERSON_CLASSES))
    if "person" in negative.get(ent, ()):
      notes.append({"entity": ent, "class": "person", "reason": "stated_not_person", "units": support[ent]})
    elif others or blocked:
      notes.append({"entity": ent, "class": "person", "reason": "conflicting_category", "units": support[ent],
                    "categories": others, "classes": blocked})
    else:
      records.append({"entity": ent, "class": "person", "kind": "stage1_person", "unit": support[ent][0],
                      "units": support[ent]})
  return records, notes


def stated_types(types):
  """The type records of the envelope field types, in unit order as given."""
  out = []
  for uid, atoms in (types or {}).items():
    for a in atoms:
      out.append({"entity": a[2], "class": a[1], "kind": "stated", "unit": uid})
  return out


def class_condition_findings(units, packages):
  """Class conditions on concrete entities in the antecedents of source rules, compared with the rule's own Stage-1
  text.  Returns [{"unit", "path", "atom", "confidence", "reason"}]:

    no finding   the rule's text predicates the class of the entity ("If Nia 1 is a doctor ..."), or the guard
                 is quantified (a variable); a negative guard is never flagged
    high         the class word does not occur in the rule's text outside its entity ids ("pan" of "pan 3"
                 states nothing), so no sentence of the rule states the condition
    ambiguous    the class word occurs in the rule's text in another construction; a reader decides

  A fact elsewhere in the source that satisfies the condition does not make it stated: an invented condition stays
  invented.  `path` is the list of indices into the package ["@id", ID, PACKAGE].  `repair` is "move_to_types" when
  the atom is the class of a referent that this law sentence introduces by its class noun (the unit is the entity's
  first mention, and the noun names it): its place is the envelope field types, not the antecedent.  Otherwise it is
  "remove".
  """
  byid = {u["unit_id"]: u for u in units}
  first = first_mentions(units)
  out = []
  for p in packages:
    u = byid.get(p[1])
    if u is None or u.get("type") == "query" or not isinstance(p[2], list):
      continue
    text = u.get("text") or ""
    ids = sorted({e["id"] for x in units for e in x.get("entities") or []
                  if isinstance(e, dict) and isinstance(e.get("id"), str) and CONCRETE.match(e["id"])},
                 key=len, reverse=True)
    masked = " ".join(text.lower().split())
    for i in ids:
      masked = re.sub(r"(?<!\w)%s(?!\w)" % re.escape(i.lower()), " ", masked)
    words = set(re.findall(r"[a-z]+", masked))

    def finding(a, path):
      if not is_class_atom(a):
        return
      low = " ".join(text.lower().split())
      if re.search(r"(?<!\w)%s (?:is|are|was|were) (?:not )?(?:a |an |the )?%s(?!\w)"
                   % (re.escape(a[2].lower()), re.escape(a[1].lower())), low):
        return
      cls = a[1].lower()
      seen = cls in words or cls + "s" in words or (cls.endswith("s") and cls[:-1] in words)
      own = (u.get("action_reading") in LAW_READINGS and first.get(a[2]) == p[1]
             and names_class(text, a[1], a[2]))
      out.append({"unit": p[1], "path": list(path), "atom": a,
                  "confidence": "ambiguous" if seen else "high",
                  "repair": "move_to_types" if own else "remove",
                  "reason": ("the class word %r occurs in the rule's text in another construction" % a[1]) if seen
                  else "no sentence of the rule states that %s is a %s" % (a[2], a[1])})

    def walk(f, path):
      if not isinstance(f, list) or not f:
        return
      if f[0] == "implies" and len(f) == 3:
        ant = f[1]
        if isinstance(ant, list) and ant[:1] == ["and"]:
          for i in range(1, len(ant)):
            finding(ant[i], path + [1, i])
        else:
          finding(ant, path + [1])
        walk(f[2], path + [2])
        return
      for i in range(1, len(f)):
        walk(f[i], path + [i])
    walk(p[2], [2])
  return out


def drop_conjuncts(package, paths):
  """The package with the conjuncts at `paths` removed from their rule antecedents, and an emptied or singleton
  conjunction collapsed: [and, A] is A, and implies with an empty antecedent is its consequent.  Nothing else
  changes.  The paths are those of class_condition_findings."""
  gone = {tuple(p) for p in paths}

  def rebuild(f, path):
    if not isinstance(f, list) or not f:
      return f
    if f[0] == "implies" and len(f) == 3:
      ant = f[1]
      if tuple(path + [1]) in gone:
        return rebuild(f[2], path + [2])
      if isinstance(ant, list) and ant[:1] == ["and"]:
        kept = [ant[i] for i in range(1, len(ant)) if tuple(path + [1, i]) not in gone]
        if not kept:
          return rebuild(f[2], path + [2])
        ant = kept[0] if len(kept) == 1 else ["and"] + kept
      return ["implies", ant, rebuild(f[2], path + [2])]
    return [f[0]] + [rebuild(f[i], path + [i]) for i in range(1, len(f))]
  return rebuild(package, [])


def render_examples(stage, examples):
  """The examples of a stage as prompt text: one block per example, its input and its output.  Every example goes
  into the Stage-1 prompt, and an example with a `stage2` field also into the Stage-2 prompt."""
  blocks = []
  for e in examples:
    if stage == "stage2" and "stage2" not in e:
      continue
    source = e["text"] if stage == "stage1" else json.dumps(e["stage1"], ensure_ascii=False)
    target = json.dumps(e[stage], ensure_ascii=False)
    blocks.append("Example %s\nInput:\n%s\nOutput:\n%s" % (e["id"], source, target))
  return "\n\n".join(blocks) + "\n"


def assemble(directory=PROMPTS):
  """The action prompt bundle: for each stage, the ordinary instructions, examples and checklist, then the action
  instructions, the rendered action examples and the action checklist, with the SHA-256 of every file and of each
  assembled prompt.  A missing file raises FileNotFoundError."""
  directory = Path(directory)
  examples = json.loads((directory / "examples.json").read_text())
  routing = json.loads((directory / "routing_cases.json").read_text())
  files, texts, rendered = {}, {}, {}
  for stage in ("stage1", "stage2"):
    parts = []
    for path in (ROOT / "prompts" / (stage + "_instructions_full.txt"),
                 ROOT / "prompts" / (stage + "_examples.txt"),
                 ROOT / "prompts" / (stage + "_checklist_full.txt"),
                 directory / (stage + "_instructions.txt")):
      raw = path.read_bytes()
      files[str(path.relative_to(ROOT))] = digests.sha256_bytes(raw)
      parts.append(raw.decode())
    rendered[stage] = render_examples(stage, examples + routing)
    parts.append(rendered[stage])
    path = directory / (stage + "_checklist.txt")
    raw = path.read_bytes()
    files[str(path.relative_to(ROOT))] = digests.sha256_bytes(raw)
    parts.append(raw.decode())
    texts[stage] = "\n\n".join(parts)
  for name in ("examples.json", "routing_cases.json"):
    path = directory / name
    files[str(path.relative_to(ROOT))] = digests.sha256_file(path)
  return {"name": "actions", "status": "prompt revision I",
          **texts, "rendered_examples": rendered, "files": files, "annotation_contract": 1,
          "sha256": {k: digests.sha256_text(v) for k, v in texts.items()}}
