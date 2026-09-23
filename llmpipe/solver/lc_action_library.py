"""Action profile: the maintained action library, its roles, its templates and its views.

The library `axioms_action.js` is the authority for the physical laws.  This
module does not restate them.  It loads the file, checks it against the role
index `axioms_action.roles.json` (hash, version, one role per clause, role
fits the clause), loads the applicability templates of
`axioms_action.templates.json` (compiler data, never a GK input), and
selects the clauses of a query view:

  discovery   every role
  verify      every role but reachability: a supplied sequence is one fixed
              history, not a search
  snapshot    static helpers, executability defaults, default hooks and the
              denial consequence, bound to the query's planning root; no
              effect, marker, frame or reachability clause, so no
              hypothetical future state can reach an initial-state question
              (A3.3)

Contexts (library 2.0.1, encoding v2).  Every situation-bearing literal of
a clause ends with one context term $ctxt(present, S, L, $obj) and has no
other situation argument: S, in the world slot, is the clause's situation
variable ?:S or its successor $do(A, ?:S); L is a location variable per
distinct atom by the agreement rule (a frame's premise, conclusion and
blocker share one; a default's blocker and the denial consequence repeat the
context of the literal they follow); $obj is the objective knower.
`reachable(S, N)` has the situation in its first argument and no context.
`select` binds the snapshot view to the planning root (?:S to the root's
world name) and, for a knower-relative query, replaces $obj by the knower in
every view.

Encoding v2 (library 2.0.1): executability `poss` is the one planning
predicate.  The library's own permissions are four defaults concluding
`normally poss`, blocked by the marker `execution_denied` of an explicit
denial; one consequence clause gives -poss from the marker.  A source
availability is completed with the templates of its constructor by the
availability pass.  The template file's SHA-256 is part of the library
identity.

A default restriction hook is left out for a constructor the source
restricts; the restriction pass emits that hook from its checks.

Nothing here calls a prover.  Whether the selected clauses prove anything is
measured later, under a counted budget.
"""

import copy
import hashlib
import json
import os

import lc_action as la
import lc_action_situate as sit

HERE = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.normpath(os.path.join(HERE, "..", "axioms_action.js"))
INDEX = os.path.normpath(os.path.join(HERE, "..", "axioms_action.roles.json"))
TEMPLATES = os.path.normpath(os.path.join(HERE, "..", "axioms_action.templates.json"))
PASS = "action_library"

ROLES = ("static_helper", "applicability_default", "hook_default", "denial_consequence", "effect", "marker",
         "frame", "derived_no_inertia", "reachability")
SNAPSHOT_ROLES = ("static_helper", "applicability_default", "hook_default", "denial_consequence")
TEMPLATE_ROLE = "applicability_template"
SOURCE = "$source"          # the placeholder literal of a template: the conditions of one source unit
MARKER = "execution_denied"  # the marker of an explicit denial
TEMPLATE_NAMES = ("tpl_move_public", "tpl_move_stated", "tpl_take", "tpl_put_on_block", "tpl_put_on_surface",
                  "tpl_put_in", "tpl_change")
VIEW_ROLES = {"discovery": ROLES,
              "verify": tuple(r for r in ROLES if r != "reachability"),
              "snapshot": SNAPSHOT_ROLES}
SITUATION = "?:S"           # the situation variable of a clause, in the world slot of its context terms
OBJ = sit.OBJ               # the objective knower of a law
FLUENT_LIKE = set(la.FLUENTS) | {"poss", "reachable", "changed_rel2", "changed_property", "changed_have", MARKER, SOURCE} \
  | {"ok_" + c for c in la.CONSTRUCTORS}


# the length of a literal of each situation-bearing predicate: the name, the ordinary arguments, the context term
# (reachable: the name, the situation, the depth; no context)
ARITY = dict({"is rel2": 5, "has property": 4, "have": 4, "poss": 3, MARKER: 3, SOURCE: 3, "reachable": 3,
              "changed_rel2": 5, "changed_property": 4, "changed_have": 4}, **{"ok_" + c: 3 for c in la.CONSTRUCTORS})


def _arity_ok(x):
  p = predicate(x)
  return p not in ARITY or len(x) == ARITY[p]


class LibraryError(Exception):
  """The library file, its index or a selection request is wrong."""


def law_context(t):
  """$ctxt(present, S, L, $obj), S = ?:S or $do(A, ?:S), L a location variable: the context term of a library literal."""
  return isinstance(t, list) and len(t) == 5 and t[:2] == ["$ctxt", "present"] \
    and (t[2] == SITUATION or (_is_successor(t[2]) and t[2][2] == SITUATION)) \
    and isinstance(t[3], str) and t[3].startswith("?:L") and t[4] == OBJ


def situation_of(lit):
  return sit.situation_of(lit)


def _location(x):
  return x[-1][3]


def hook_name(constructor):
  return "ok_" + constructor


def _strip_comments(text):
  return "\n".join(x for x in text.split("\n") if not x.strip().startswith("//"))


def literals(clause):
  """The literal list of a clause object; a unit clause is written bare."""
  logic = clause["@logic"]
  return logic if logic and isinstance(logic[0], list) else [logic]


def predicate(lit):
  return lit[0][1:] if lit[0].startswith("-") else lit[0]


def positive(lit):
  return not lit[0].startswith("-")


def head(clause, name):
  """The positive literal with this predicate, or None."""
  hit = [x for x in literals(clause) if positive(x) and predicate(x) == name]
  return hit[0] if hit else None


def load(library=LIBRARY, index=INDEX, templates=TEMPLATES):
  """The checked library: {"id", "version", "sha256", "roles_sha256", "templates_sha256", "derived_from",
  "clauses", "templates"}.

  Each clause is {"name", "role", "clause"} with the clause object as in the
  file; each template is {"name", "role", "constructor", "clause"}.  Raises
  LibraryError when the file, the index and the template file disagree.
  """
  try:
    with open(library, "rb") as f:
      raw = f.read()
    with open(index) as f:
      idx = json.load(f)
    with open(templates, "rb") as f:
      traw = f.read()
  except (OSError, ValueError) as e:
    raise LibraryError("the library, its role index or its template file cannot be read: %s" % e)
  check_index(idx, os.path.basename(library))
  digest = hashlib.sha256(raw).hexdigest()
  if idx.get("sha256") != digest:
    raise LibraryError("axioms_action.js has sha256 %s; the role index was checked against %s"
                       % (digest, idx.get("sha256")))
  try:
    items = json.loads(_strip_comments(raw.decode("utf-8")))
  except ValueError as e:
    raise LibraryError("axioms_action.js does not parse: %s" % e)
  roles = idx.get("roles", {})
  clauses, seen = [], set()
  for c in items:
    if not (isinstance(c, dict) and isinstance(c.get("@name"), str) and "@logic" in c):
      raise LibraryError("a library clause is an object with @name and @logic: %r" % (c,))
    name = c["@name"]
    if name in seen:
      raise LibraryError("two library clauses are named %s" % name)
    seen.add(name)
    if roles.get(name) not in ROLES:
      raise LibraryError("clause %s has no role in the index" % name)
    clauses.append({"name": name, "role": roles[name], "clause": c})
  extra = sorted(set(roles) - seen)
  if extra:
    raise LibraryError("the index names clauses the library lacks: %s" % extra)
  tpl = load_templates(traw, idx["version"])
  lib = {"id": os.path.basename(library), "version": idx["version"], "sha256": digest,
         "roles_sha256": index_digest(idx), "templates_sha256": hashlib.sha256(traw).hexdigest(),
         "derived_from": idx["derived_from"], "clauses": clauses, "templates": tpl}
  check_roles(lib)
  return lib


TEMPLATE_FIELDS = ("library", "version", "role", "placeholder", "note", "templates")
TEMPLATE_RECORD_FIELDS = ("name", "role", "constructor", "note", "clause")


def load_templates(raw, version):
  """The applicability templates, checked: one record per name, one $source literal each (A2.3, Revision 4)."""
  try:
    doc = json.loads(raw.decode("utf-8"))
  except ValueError as e:
    raise LibraryError("axioms_action.templates.json does not parse: %s" % e)
  if not isinstance(doc, dict) or sorted(doc) != sorted(TEMPLATE_FIELDS):
    raise LibraryError("the template file has the fields %s" % ", ".join(TEMPLATE_FIELDS))
  if doc["library"] != "axioms_action.js" or doc["version"] != version or doc["role"] != TEMPLATE_ROLE:
    raise LibraryError("the template file belongs to %r version %r, role %r" % (doc["library"], doc["version"], doc["role"]))
  out, seen = [], set()
  for t in doc["templates"]:
    if not isinstance(t, dict) or sorted(t) != sorted(TEMPLATE_RECORD_FIELDS) or t["role"] != TEMPLATE_ROLE:
      raise LibraryError("a template record has the fields %s and the role %s" % (", ".join(TEMPLATE_RECORD_FIELDS), TEMPLATE_ROLE))
    if t["name"] in seen:
      raise LibraryError("two templates are named %s" % t["name"])
    seen.add(t["name"])
    check_template(t)
    out.append({"name": t["name"], "role": t["role"], "constructor": t["constructor"], "clause": t["clause"]})
  if sorted(seen) != sorted(TEMPLATE_NAMES):
    raise LibraryError("the templates are %s, got %s" % (", ".join(TEMPLATE_NAMES), sorted(seen)))
  return out


def check_template(t):
  """One -$source(ACTION, C), the physical preconditions, the hook, one positive poss(ACTION, C)."""
  name, lits = t["name"], literals(t["clause"])
  src = [x for x in lits if predicate(x) == SOURCE]
  poss = [x for x in lits if positive(x)]
  if len(src) != 1 or positive(src[0]):
    raise LibraryError("%s: a template has exactly one negative $source literal" % name)
  if len(poss) != 1 or predicate(poss[0]) != "poss":
    raise LibraryError("%s: a template concludes one positive poss" % name)
  act = poss[0][1]
  k = _constructor_of(act)
  if k is None or k != t["constructor"] or src[0][1:-1] != poss[0][1:-1] or situation_of(src[0]) != situation_of(poss[0]):
    raise LibraryError("%s: the $source literal names the concluded action and situation" % name)
  hook = [x for x in lits if predicate(x) == hook_name(k)]
  if len(hook) != 1 or hook[0][1:-1] != poss[0][1:-1] or situation_of(hook[0]) != situation_of(poss[0]):
    raise LibraryError("%s: a template needs the restriction hook %s on the same action and situation" % (name, hook_name(k)))
  if any(predicate(x) in (MARKER, "can", "action_available", "route_for") or predicate(x) == "$block" for x in lits):
    raise LibraryError("%s: a template reads no marker, capability or route and has no blocker" % name)
  for x in lits:
    p = predicate(x)
    if p in FLUENT_LIKE and (len(x) < 3 or not law_context(x[-1]) or situation_of(x) != SITUATION or not _arity_ok(x)):
      raise LibraryError("%s: %s must end with the context $ctxt(present, ?:S, L, $obj) and have no other situation" % (name, p))
  _check_locations(name, "template", lits)


def template(lib, name):
  hit = [t for t in lib["templates"] if t["name"] == name]
  if not hit:
    raise LibraryError("no template %s" % name)
  return hit[0]


def templates_of(lib, constructor):
  """The templates of a constructor, in file order."""
  return [t for t in lib["templates"] if t["constructor"] == constructor]


INDEX_FIELDS = ("library", "version", "sha256", "derived_from", "roles")
PROVENANCE_FIELDS = ("path", "sha256", "date")
HEX64 = "0123456789abcdef"


def _is_sha256(x):
  return isinstance(x, str) and len(x) == 64 and all(c in HEX64 for c in x)


def check_index(idx, library_name):
  """The role index has exactly the documented fields, with the documented types."""
  if not isinstance(idx, dict):
    raise LibraryError("the role index is a JSON object")
  if sorted(idx) != sorted(INDEX_FIELDS):
    raise LibraryError("the role index has the fields %s, got %s" % (", ".join(INDEX_FIELDS), sorted(idx)))
  if idx["library"] != library_name:
    raise LibraryError("the role index is for %r, not for %s" % (idx["library"], library_name))
  if not (isinstance(idx["version"], str) and idx["version"].strip()):
    raise LibraryError("the library version is a non-empty string")
  if not _is_sha256(idx["sha256"]):
    raise LibraryError("sha256 is 64 lower-case hex digits")
  prov = idx["derived_from"]
  if not isinstance(prov, dict) or sorted(prov) != sorted(PROVENANCE_FIELDS) or not _is_sha256(prov["sha256"]) \
     or not all(isinstance(prov[k], str) and prov[k].strip() for k in ("path", "date")):
    raise LibraryError("derived_from is {path, sha256, date} with a 64-hex source hash")
  roles = idx["roles"]
  if not isinstance(roles, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in roles.items()):
    raise LibraryError("roles is an object {clause name: role}")


def index_digest(idx):
  """SHA-256 of the validated index content in canonical form, not of its whitespace."""
  text = json.dumps({k: idx[k] for k in INDEX_FIELDS}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _constructor_of(term):
  return term[0] if isinstance(term, list) and term and term[0] in la.CONSTRUCTORS else None


def check_roles(lib):
  """Every role fits its clause.  The role index is explicit; this keeps it true."""
  for c in lib["clauses"]:
    name, role, lits = c["name"], c["role"], literals(c["clause"])
    heads = [x for x in lits if positive(x) and predicate(x) != "$block"]
    preds = [predicate(x) for x in heads]
    poss = head(c["clause"], "poss")
    if (poss is not None) != (role == "applicability_default"):
      raise LibraryError("%s: a positive poss head belongs to role applicability_default and to no other" % name)
    if any(predicate(x) == SOURCE for x in lits):
      raise LibraryError("%s: the executable library holds no $source literal; templates live in the template file" % name)
    if head(c["clause"], MARKER) is not None:
      raise LibraryError("%s: no library clause concludes %s; an explicit source denial does" % (name, MARKER))
    if any(predicate(x) in ("can", "action_available", "capability_denied", "route_for") for x in lits):
      raise LibraryError("%s: library 2.0 has no can, action_available, capability_denied or route_for" % name)
    if role == "applicability_default":
      _check_default(lib, name, lits, poss)
    elif role == "hook_default":
      if len(lits) != 1 or not preds or not preds[0].startswith("ok_") or preds[0] != hook_name(_constructor_of(lits[0][1])):
        raise LibraryError("%s: a default hook is the unit clause ok_<constructor>(ACTION, C)" % name)
    elif role == "denial_consequence":
      neg = [x for x in lits if not positive(x)]
      if len(lits) != 2 or len(neg) != 2 or predicate(neg[0]) != MARKER or predicate(neg[1]) != "poss":
        raise LibraryError("%s: the denial consequence is -%s v -poss" % (name, MARKER))
      if neg[1][1:] != neg[0][1:] or len(neg[0]) != 3:
        raise LibraryError("%s: the consequence must repeat the denied action, situation and context" % name)
      act = neg[0][1]
      if isinstance(act, list) and act and _constructor_of(act) is None:
        raise LibraryError("%s: the denied action term is not a recognized constructor" % name)
    elif role == "effect":
      if len(heads) > 1 or not any(predicate(x) == "poss" and not positive(x) for x in lits):
        raise LibraryError("%s: an effect needs -poss and concludes one signed fluent" % name)
      concl = [x for x in lits if predicate(x) in la.FLUENTS and _is_successor(situation_of(x))]
      if len(concl) != 1:
        raise LibraryError("%s: an effect concludes one fluent in the successor situation" % name)
    elif role in ("marker", "derived_no_inertia"):
      if len(heads) != 1 or not preds[0].startswith("changed_") or not _is_successor(situation_of(heads[0])):
        raise LibraryError("%s: a marker concludes changed_* in the successor situation" % name)
    elif role == "frame":
      block = [x for x in lits if predicate(x) == "$block"]
      if len(heads) != 1 or preds[0] not in la.FLUENTS or not _is_successor(situation_of(heads[0])) or len(block) != 1 \
         or not block[0][2][0].startswith("changed_"):
        raise LibraryError("%s: a frame carries one fluent into the successor unless its marker blocks it" % name)
    elif role == "reachability":
      if preds != ["reachable"] or any(predicate(x) == "reachable" and len(x) != 3 for x in lits):
        raise LibraryError("%s: reachability concludes reachable(S, N), with no context term" % name)
    elif role == "static_helper":
      if any(predicate(x) in FLUENT_LIKE for x in lits):
        raise LibraryError("%s: a static helper holds no situation" % name)
    for x in lits + [b[2] for b in lits if predicate(b) == "$block"]:
      p = predicate(x)
      if p in FLUENT_LIKE and p != "reachable" and (len(x) < 3 or not law_context(x[-1])):
        raise LibraryError("%s: %s must end with the context $ctxt(present, S, L, $obj), S the clause's situation" % (name, p))
      if not _arity_ok(x):
        raise LibraryError("%s: %s has %d arguments; the 2.0 layout gives it %d (no situation outside the context)"
                           % (name, p, len(x) - 1, ARITY[p] - 1))
    _check_locations(name, role, lits)


def _check_locations(name, role, lits):
  """The agreement rule of the migration plan (section 5) on the location variables of one clause.

  frame                premise, conclusion and blocker share one variable; the poss premise has another
  denial consequence   both literals have one context term (checked with the role)
  default              the blocker repeats the head's context term (checked with the role)
  every other clause   one variable per distinct atom: two literals share a variable only when their atoms
                       are equal but for the sign
  """
  body = [x for x in lits if predicate(x) != "$block" and predicate(x) in FLUENT_LIKE and predicate(x) != "reachable"]
  if role == "frame":
    persist = [x for x in body if predicate(x) != "poss"]
    block = [b[2] for b in lits if predicate(b) == "$block"]
    poss = [x for x in body if predicate(x) == "poss"]
    if len({_location(x) for x in persist + block}) != 1 or len(poss) != 1 or _location(poss[0]) == _location(persist[0]):
      raise LibraryError("%s: a frame's premise, conclusion and blocker share one location variable; its poss premise "
                         "has another" % name)
    return
  if role == "denial_consequence":
    return
  seen = {}
  for x in body:
    key = json.dumps([predicate(x)] + x[1:-1])
    loc = _location(x)
    if seen.get(loc, key) != key:
      raise LibraryError("%s: two different atoms share the location variable %s; each atom has its own" % (name, loc))
    seen[loc] = key


# the class conditions of each default and the template it completes
DEFAULTS = {"poss_move_person": ("tpl_move_public", [["-isa", "person", "?:A"], ["-standard_mode", "?:M"]]),
            "poss_take_hand": ("tpl_take", [["-isa", "hand", "?:H"], ["-isa", "block", "?:X"]]),
            "poss_put_on_hand_block": ("tpl_put_on_block", [["-isa", "hand", "?:H"], ["-isa", "block", "?:X"]]),
            "poss_put_on_hand_surface": ("tpl_put_on_surface", [["-isa", "hand", "?:H"], ["-isa", "block", "?:X"]])}


def _check_default(lib, name, lits, poss):
  """A default is its template with the class conditions in place of $source (a literal once), and the marker blocker."""
  if name not in DEFAULTS:
    raise LibraryError("%s: an applicability default is one of %s" % (name, ", ".join(sorted(DEFAULTS))))
  tname, classes = DEFAULTS[name]
  tpl = literals(template(lib, tname)["clause"])
  want = classes + [x for x in tpl if predicate(x) != SOURCE and x not in classes]
  block = [x for x in lits if predicate(x) == "$block"]
  rest = [x for x in lits if predicate(x) != "$block"]
  if rest != want:
    raise LibraryError("%s: a default is the template %s with its class conditions; got %r" % (name, tname, rest))
  if len(block) != 1 or block[0][2] != [MARKER] + poss[1:]:
    raise LibraryError("%s: a default is blocked by %s of the same action, situation and context" % (name, MARKER))


def _is_successor(t):
  return isinstance(t, list) and len(t) == 3 and t[0] == "$do"


def _substitute(x, var, term):
  if isinstance(x, list):
    return [_substitute(y, var, term) for y in x]
  return term if x == var else x


def select(lib, view, restricted=(), root="W0", knower=None):
  """The library clauses of a query view, as {"name", "role", "clause"} records.

  `restricted` names the constructors the source restricts: their default
  hooks are left out.  A snapshot clause is bound to the planning root
  `root`: `?:S` becomes the root's world name.  A `knower` (an entity id)
  replaces the objective knower $obj in every view.
  """
  if view not in VIEW_ROLES:
    raise LibraryError("unknown view %r" % view)
  bad = sorted(set(restricted) - set(la.CONSTRUCTORS))
  if bad:
    raise LibraryError("unknown constructors %s" % bad)
  if not (isinstance(root, str) and la.WORLD.match(root)):
    raise LibraryError("the planning root is a world name, got %r" % (root,))
  out = []
  for c in lib["clauses"]:
    if c["role"] not in VIEW_ROLES[view]:
      continue
    if c["role"] == "hook_default" and _constructor_of(literals(c["clause"])[0][1]) in restricted:
      continue
    rec = copy.deepcopy(c)
    if view == "snapshot":
      rec["clause"]["@logic"] = _substitute(rec["clause"]["@logic"], SITUATION, root)
    if knower is not None:
      rec["clause"]["@logic"] = _substitute(rec["clause"]["@logic"], OBJ, sit.knower_term(knower))
    out.append(rec)
  return out


def view_hash(records):
  """The hash of a view: the name, the role and the clause of every selected record, in order."""
  text = json.dumps([{"name": r["name"], "role": r["role"], "clause": r["clause"]} for r in records],
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False)
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def identity(lib):
  """What an artifact records about the library it was compiled against: the clause file, its role index and
  the template file (A4.3, Revision 4)."""
  return {"id": lib["id"], "version": lib["version"], "hash": lib["sha256"],
          "roles_hash": lib["roles_sha256"], "templates_hash": lib["templates_sha256"], "status": "selected"}
