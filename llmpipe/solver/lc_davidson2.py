# davidson2 — the exact event-spine compression (-event davidson2).
#
# A repaired second version of the compact Davidsonian fold.  Where the v1 fold
# (`lc_coarse._davidson_event`, -event davidson) rewrites an event group as
# best it can, davidson2 rewrites a group only when the rewrite is exactly
# reversible.  It removes four spine atoms
#
#     isa(activity,E)  has type(E,V)  has actor(E,A)  has target(E,T)
#
# and puts one atom in their place:
#
#     event(V,A,T,E)
#
# Everything else in the group is left as it stands.  The fold runs before
# context injection, so the normal context pass appends the context argument
# afterwards, exactly as it does for a reified role.
#
# Three v1 behaviours this module does NOT have:
#   * v1 replaces a typed existential participant by its class label, so
#     "eat a big fish" loses the fish and its modifier.  v2 keeps the variable
#     and its binder.
#   * v1 mints a fresh `Dava*` / `Davp*` value for a missing actor or target.
#     v2 refuses the fold instead, so no invented value can reach an answer.
#   * v1 accepts `has goal` and `has topic` in the compact object slot, which
#     relabels them `has target` through the bridge.  v2 accepts only a real
#     `has target` and leaves a goal or topic as an adjunct.
#
# Every fold is checked by expanding it back to the four spine atoms and
# comparing with the original group (`round_trip_ok`).  A group that fails the
# comparison stays reified.  Refusals are recorded with a reason so the
# comparison harness can report them.
#
# Selected by lc_encoding.EncodingConfig.davidson2 (-event davidson2 /
# -davidson2); the legacy -event davidson path never enters this module.

import json

from lc_clausify import looks_like_var_broad

# The four spine atoms, at their exact standard arity.  An atom carrying an
# extra argument (a context term already attached, say) is not compressed: the
# compact atom has one argument slot per participant and no room for four
# separate tails, so such a group cannot be expanded back exactly.
_SPINE_ARITY = 3

# Roles that stay adjuncts in v2 even though v1 accepted them in the object
# slot.  Named here only so the refusal reason can say which one was seen.
_NON_TARGET_OBJECT_ROLES = ("has goal", "has topic")

REFUSALS = ("missing_actor", "missing_target", "content_event", "multiple_role",
            "round_trip_mismatch", "no_event", "spine_arity", "abstract_verb",
            "binder_scope")

_report = []
_source = [None]        # the sentence id whose package is being folded


def reset():
  """Drop the decisions recorded for the previous conversion."""
  del _report[:]
  _source[0] = None


def report():
  """The fold decisions of the last conversion, in the order they were made.

  A recorded fold carries everything needed to reconstruct the transformation:
  the four spine atoms as they stood, the compact atom that replaced them, the
  verb, the context term if the atoms carried one, and the sentence the package
  came from.  This is audit provenance -- it is read from the report, never from
  the clauses, so it changes neither the logic nor the English.
  """
  return list(_report)


def set_source(name):
  """Name the sentence whose package is being folded, for the record."""
  _source[0] = name


def _note(decision, reason=None, verb=None, evar=None, spine=None, compact=None,
          context=None):
  _report.append({"decision": decision, "reason": reason,
                  "verb": verb, "event_var": evar,
                  "source": _source[0],
                  "spine_atoms": spine, "compact_atom": compact,
                  "context": context})


# ---- canonical form -------------------------------------------------------
#
# Two formulas count as equal for the round-trip check when they differ only in
# the order of conjuncts and in the names of bound variables.  `_canon` builds a
# form that is invariant under both: every bound variable becomes its de Bruijn
# level, so an alpha-variant canonicalises identically whatever the surrounding
# order, and the children of an `and` are sorted by their own canonical form.
# Nothing else is normalised — argument order, predicate sign, quantifier kind,
# constants and structured terms all survive into the canonical form and so are
# compared exactly.


def _mentions(node, v):
  if node == v:
    return True
  if isinstance(node, list):
    return any(_mentions(x, v) for x in node)
  return False


def _float_free(node):
  """Move a conjunct that does not mention the bound variable out of an
  existential:  exists Y (A & B(Y))  ==  A & exists Y B(Y)  when Y is not free
  in A.  The compression puts the compact atom inside the binder of a
  participant, so one side of the round-trip comparison has three spine atoms
  the other side has outside that binder.  The two are the same formula, and
  this is the rewrite that says so.  Applied to both sides alike.
  """
  if not isinstance(node, list) or not node:
    return node
  node = [_float_free(x) if isinstance(x, list) else x for x in node]
  if node[0] == "exists" and len(node) == 3 and isinstance(node[1], str):
    V, body = node[1], node[2]
    if isinstance(body, list) and body and body[0] == "and":
      inside = [c for c in body[1:] if _mentions(c, V)]
      outside = [c for c in body[1:] if not _mentions(c, V)]
      if outside and inside:
        return ["and"] + outside + [["exists", V, ["and"] + inside]]
  return node


def _canon(node, stack=()):
  if isinstance(node, str):
    if node in stack:
      # The innermost binder shadows an outer binder with the same spelling.
      # Search from the inside; using the first occurrence confuses the two
      # scopes in formulas that reuse a variable name.
      rev_index = tuple(reversed(stack)).index(node)
      return ["#b", rev_index]
    return node
  if not isinstance(node, list) or not node:
    return node
  head = node[0]
  if isinstance(head, str) and head in ("exists", "forall") and len(node) >= 3:
    inner = tuple(stack) + (node[1],)
    return [head, "#v", _canon(node[2], inner)] + [_canon(x, inner) for x in node[3:]]
  if head == "and":
    kids = []
    for x in node[1:]:                      # associativity: one flat conjunction
      c = _canon(x, stack)
      if isinstance(c, list) and c and c[0] == "and":
        kids.extend(c[1:])
      else:
        kids.append(c)
    if len(kids) == 1:            # a one-child `and` is the child itself
      return kids[0]
    return ["and"] + sorted(kids, key=lambda k: json.dumps(k, sort_keys=True))
  return [_canon(x, stack) for x in node]


def _equal(a, b):
  return (json.dumps(_canon(_float_free(a)), sort_keys=True)
          == json.dumps(_canon(_float_free(b)), sort_keys=True))


# ---- the event group ------------------------------------------------------


def _spine_of(block, E):
  """Collect every atom of the group attributed to event E.

  Returns (counts, values, arity_ok, has_content).  `counts` maps a role head to
  how many atoms carry it, so a second actor or target is visible rather than
  silently dropped; `values` keeps the first value of each.
  """
  counts = {}
  values = {}
  arity_ok = [True]
  has_content = [False]

  def see(head, value, atom):
    counts[head] = counts.get(head, 0) + 1
    values.setdefault(head, value)
    if len(atom) != _SPINE_ARITY:
      arity_ok[0] = False

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      h = n[0]
      if h == "isa" and len(n) >= 3 and n[1] == "activity" and n[2] == E:
        see("isa activity", "activity", n)
      elif len(n) >= 3 and n[1] == E:
        if h in ("has type", "has actor", "has target"):
          see(h, n[2], n)
        elif h == "has content":
          has_content[0] = True
        elif h in _NON_TARGET_OBJECT_ROLES:
          counts.setdefault(h, 0)
          counts[h] += 1
      for x in n[1:]:
        walk(x)
    elif isinstance(n, list):
      for x in n:
        walk(x)

  walk(block)
  return counts, values, arity_ok[0], has_content[0]


def _is_concrete_verb(v):
  """A verb label the compact atom may carry: a plain word, not a variable and
  not a structured term."""
  if not isinstance(v, str) or not v:
    return False
  return (not looks_like_var_broad(v)
          and not v.startswith(("#:", "$")))


def _occurs(node, name):
  if node == name:
    return True
  if isinstance(node, list):
    return any(_occurs(x, name) for x in node)
  return False


def _is_spine_atom(c, E):
  if not (isinstance(c, list) and c and isinstance(c[0], str)):
    return False
  h = c[0]
  if h == "isa" and len(c) >= 3 and c[1] == "activity" and c[2] == E:
    return True
  return len(c) >= 3 and c[1] == E and h in ("has type", "has actor", "has target")


def _spine_sites(node, E, stack=(), out=None):
  """Every spine atom of E, with the set of variables bound around it."""
  out = [] if out is None else out
  if isinstance(node, list) and node and isinstance(node[0], str):
    if _is_spine_atom(node, E):
      out.append((node, frozenset(stack)))
      return out
    op = node[0]
    if op in ("exists", "forall") and len(node) >= 3:
      inner = tuple(stack) + (node[1],)
      for x in node[2:]:
        _spine_sites(x, E, inner, out)
      return out
    for x in node[1:]:
      _spine_sites(x, E, stack, out)
    return out
  if isinstance(node, list):
    for x in node:
      _spine_sites(x, E, stack, out)
  return out


def _bound_vars(node, out=None):
  out = set() if out is None else out
  if isinstance(node, list) and node:
    if (isinstance(node[0], str) and node[0] in ("exists", "forall")
        and len(node) >= 3 and isinstance(node[1], str)):
      out.add(node[1])
    for x in node:
      if isinstance(x, list):
        _bound_vars(x, out)
  return out


def _strip_spine(node, E, place_at=None, ev=None):
  """Drop E's four spine atoms wherever they sit, keeping every other atom and
  the surrounding structure.  The atom `place_at` (compared by identity) is
  replaced by `ev` instead of being dropped, so the compact atom lands inside
  exactly the binders that atom stood in.  None means the node itself went."""
  if isinstance(node, list) and node and isinstance(node[0], str):
    if _is_spine_atom(node, E):
      return ev if (place_at is not None and node is place_at) else None
    op = node[0]
    if op in ("and", "or"):
      kept = [_strip_spine(x, E, place_at, ev) for x in node[1:]]
      kept = [k for k in kept if k is not None]
      return [op] + kept
    if op in ("exists", "forall") and len(node) >= 3:
      inner = _strip_spine(node[2], E, place_at, ev)
      if inner is None:
        return None
      return [op, node[1], inner] + node[3:]
  return node


def _expand(node, E, verb, actor, target):
  """Put the four spine atoms back where the compact atom stands."""
  if isinstance(node, list) and node and isinstance(node[0], str):
    op = node[0]
    if (op == "event" and len(node) == 5 and node[1] == verb
        and node[2] == actor and node[3] == target and node[4] == E):
      return ["and",
              ["isa", "activity", E],
              ["has type", E, verb],
              ["has actor", E, actor],
              ["has target", E, target]]
    if op in ("and", "or"):
      out = []
      for x in node[1:]:
        got = _expand(x, E, verb, actor, target)
        # an expanded event contributes its four atoms to the enclosing `and`
        if (op == "and" and isinstance(got, list) and got and got[0] == "and"
            and isinstance(x, list) and x and x[0] == "event"):
          out.extend(got[1:])
        else:
          out.append(got)
      return [op] + out
    if op in ("exists", "forall") and len(node) >= 3:
      return ([op, node[1], _expand(node[2], E, verb, actor, target)]
              + node[3:])
  return node


def round_trip_ok(original, folded, E, verb, actor, target):
  """True when expanding the fold reproduces the original group exactly."""
  return _equal(original, _expand(folded, E, verb, actor, target))


def introduced_symbols(original, folded):
  """Names present in the fold but not in the source group.  davidson2 must
  create no participant value at all, so this is expected to be empty except
  for the `event` head itself."""
  def names(node, out):
    if isinstance(node, str):
      out.add(node)
    elif isinstance(node, list):
      for x in node:
        names(x, out)
    return out
  before, after = names(original, set()), names(folded, set())
  return after - before - {"event"}


def davidson2_event(and_block, E, content_inner):
  """Compress one event group, or return None to leave it reified.

  `and_block` is the body under `exists E`; `content_inner` is the set of event
  variables that are the inner content event of a two-event reification.
  """
  if E in content_inner:
    _note("refused", "content_event", evar=E)
    return None

  counts, values, arity_ok, has_content = _spine_of(and_block, E)
  verb = values.get("has type")

  if has_content:
    _note("refused", "content_event", verb=verb, evar=E)
    return None
  if "has type" not in counts or "isa activity" not in counts:
    _note("refused", "no_event", verb=verb, evar=E)
    return None
  for head in ("isa activity", "has type", "has actor", "has target"):
    if counts.get(head, 0) > 1:
      _note("refused", "multiple_role", verb=verb, evar=E)
      return None
  if "has actor" not in counts:
    _note("refused", "missing_actor", verb=verb, evar=E)
    return None
  if "has target" not in counts:
    _note("refused", "missing_target", verb=verb, evar=E)
    return None
  if not _is_concrete_verb(verb):
    _note("refused", "abstract_verb", verb=verb, evar=E)
    return None
  if not arity_ok:
    _note("refused", "spine_arity", verb=verb, evar=E)
    return None

  actor = values["has actor"]
  target = values["has target"]
  # The participants must already be in the source.  They always are — they came
  # out of its own atoms — but the check states the rule the fold must obey.
  if not (_occurs(and_block, actor) and _occurs(and_block, target)):
    _note("refused", "missing_actor" if not _occurs(and_block, actor)
          else "missing_target", verb=verb, evar=E)
    return None

  # Where the compact atom goes.  A participant whose binder sits inside the
  # group ("eat a fish" = exists Y. isa(fish,Y) & has target(E,Y)) must keep that
  # binder around the compact atom too, or the fold leaves the variable free.
  # So the atom replaces one spine atom in place: the one standing inside every
  # binder the participants need.
  bound = _bound_vars(and_block)
  need = {v for v in (actor, target) if isinstance(v, str) and v in bound}
  sites = _spine_sites(and_block, E)
  usable = [(atom, scope) for atom, scope in sites if need <= scope]
  if not usable:
    _note("refused", "binder_scope", verb=verb, evar=E)
    return None
  place_at = max(usable, key=lambda s: len(s[1]))[0]

  ev = ["event", verb, actor, target, E]
  stripped = _strip_spine(and_block, E, place_at, ev)
  if stripped is None:
    _note("refused", "round_trip_mismatch", verb=verb, evar=E)
    return None
  folded = stripped
  if not (isinstance(folded, list) and folded and folded[0] == "and"):
    folded = ["and", folded]

  if not round_trip_ok(and_block, folded, E, verb, actor, target):
    _note("refused", "round_trip_mismatch", verb=verb, evar=E)
    return None
  extra = introduced_symbols(and_block, folded)
  if extra:
    _note("refused", "round_trip_mismatch", verb=verb, evar=E)
    return None

  spine = [a for a, _scope in sites]
  ctx = None
  for a in spine:                       # a context term, if the atoms carry one
    if len(a) > _SPINE_ARITY:
      ctx = a[_SPINE_ARITY]
      break
  _note("folded", None, verb=verb, evar=E, spine=spine, compact=ev, context=ctx)
  return folded


# ---- what the rest of the pipeline needs ----------------------------------


def adapter_crossings(proof):
  """Which directions of the compact definition a finished proof used.

  Reads the proof's own step justifications, so it reports what happened rather
  than what was available.  `forward` is event -> canonical roles, `reverse` is
  canonical roles -> event, `projection` is the one-way event -> is_rel2.
  """
  counts = {"forward": 0, "reverse": 0, "projection": 0}
  for step in proof or []:
    reason = step[1] if isinstance(step, list) and len(step) > 1 else None
    if not (isinstance(reason, list) and len(reason) > 1 and reason[0] == "in"):
      continue
    src = reason[1]
    if src == DEF_NAME:
      counts["forward"] += 1
    elif src == DEF_REV_NAME:
      counts["reverse"] += 1
    elif src == PROJ_NAME:
      counts["projection"] += 1
  return counts


def _atoms(node, out):
  if isinstance(node, list) and node and isinstance(node[0], str):
    out.append(node)
    for x in node[1:]:
      _atoms(x, out)
  elif isinstance(node, list):
    for x in node:
      _atoms(x, out)
  return out


def _clause_atoms(result):
  out = []
  for obj in result:
    if isinstance(obj, dict):
      body = obj.get("@logic")
      if body is None:
        body = obj.get("@question")
      if body is not None:
        _atoms(body, out)
  return out


def _compact_atoms(result):
  found = []
  for a in _clause_atoms(result):
    base = a[0][1:] if a[0].startswith("-") else a[0]
    if base == "event" and len(a) >= 5 and _is_concrete_verb(a[1]):
      found.append(a)
  return found


def _expand_compact_in(node, seen):
  """Replace every compact atom in one clause body by its four role atoms,
  keeping the atom's sign.  `seen` collects the compact atoms replaced."""
  if isinstance(node, list) and node and isinstance(node[0], str):
    base = node[0][1:] if node[0].startswith("-") else node[0]
    neg = node[0].startswith("-")
    if base == "event" and len(node) >= 5 and _is_concrete_verb(node[1]):
      V, A, T, E = node[1], node[2], node[3], node[4]
      tail = [node[5]] if len(node) >= 6 else []
      sign = "-" if neg else ""
      seen.append(node)
      return [[sign + "isa", "activity", E],
              [sign + "has type", E, V] + tail,
              [sign + "has actor", E, A] + tail,
              [sign + "has target", E, T] + tail]
    return [[node[0]] + [_expand_one(x, seen) for x in node[1:]]]
  if isinstance(node, list):
    return [[_expand_one(x, seen) for x in node]]
  return [node]


def _expand_one(node, seen):
  """The same walk for a nested argument, which is a term, never a clause."""
  if isinstance(node, list):
    return [_expand_one(x, seen) for x in node]
  return node


def scan_expand(result):
  """SCAN-ONLY view for the compile-time injectors.

  The injectors read the static clause list for a verb, a role or a relation.
  The compact atom hides all four, so this view shows each one as the four role
  atoms it replaced, with the same context and the same sign, inside a copy of
  the clause the compact atom came from.  The copy keeps `@name`,
  `@sourcetype`, `@question` status and every other `@` key, so an injector that
  looks at where an atom came from sees the truth.

  The view is never submitted to gk: the real theory keeps the compact atom and
  the definitional clauses supply the roles at prove time.  No scan marker is
  stored in the copy: the value exists only as the local argument passed to the
  injectors, so the ordinary clause serializer needs no special-case policy.
  """
  extra = []
  for obj in result:
    if not isinstance(obj, dict):
      continue
    for key in ("@logic", "@question"):
      body = obj.get(key)
      if body is None:
        continue
      seen = []
      variants = _expand_clause_variants(body, seen)
      if not seen:
        continue
      for atoms in variants:
        copy = dict(obj)
        copy[key] = atoms
        extra.append(copy)
  return list(result) + extra


def _expand_clause_variants(body, seen):
  """Reconstruct the clause shapes hidden by compact event literals.

  In CNF, a negative compact literal stands for the four negative role
  literals in the *same* clause::

      -event(V,A,T,E) | H
        == -isa(activity,E) | -has_type(E,V) | -has_actor(E,A)
           | -has_target(E,T) | H

  A positive compact literal stands for four separate clauses, because the
  compact event entails every role atom::

      B | event(V,A,T,E)
        == (B | isa(activity,E)) & (B | has_type(E,V))
           & (B | has_actor(E,A)) & (B | has_target(E,T))

  This is a scan-only view.  It is never submitted to GK, but preserving the
  clause structure prevents a future clause-sensitive injector from treating
  a disjunction of roles as if it were the original representation.
  """
  if not isinstance(body, list):
    return [body]
  single = bool(body and isinstance(body[0], str))
  literals = [body] if single else list(body)
  variants = [[]]
  for lit in literals:
    if (isinstance(lit, list) and lit and isinstance(lit[0], str)
        and (lit[0][1:] if lit[0].startswith("-") else lit[0]) == "event"
        and len(lit) >= 5 and _is_concrete_verb(lit[1])):
      expanded = _expand_compact_in(lit, seen)
      if lit[0].startswith("-"):
        for v in variants:
          v.extend(expanded)
      else:
        variants = [v + [role] for v in variants for role in expanded]
    else:
      for v in variants:
        v.append(lit)
  # A one-literal source is conventionally represented as the literal itself;
  # keep that shape for each one-literal positive branch.
  if single:
    return [v[0] if len(v) == 1 else v for v in variants]
  return variants


def _rel2_verbs(result):
  """Verbs occurring as a plain three-argument is_rel2 relation, whose argument
  order matches the compact atom's (verb, actor, object)."""
  verbs = set()
  for a in _clause_atoms(result):
    base = a[0][1:] if a[0].startswith("-") else a[0]
    if base == "is rel2" and len(a) >= 4 and _is_concrete_verb(a[1]):
      obj = a[3]
      if isinstance(obj, list) and obj and obj[0] == "eventprop":
        continue                       # role-tagged object: a different order
      verbs.add(a[1])
  return verbs


# The two clause families, kept apart by name so proof rendering can tell a
# definition from a claim about the world:
#
#   DEF_NAME / DEF_REV_NAME  the strict definition of the compact atom.  It says
#     only that one atom and four canonical role atoms are the same fact written
#     two ways.  It is not knowledge about events.
#   PROJ_NAME  a one-way semantic projection to the flat relation.  It IS a
#     claim -- that an event of V by A on T means the relation V holds between A
#     and T -- so it is never presented as a definition, and its converse is
#     never emitted: a relation does not establish that an event happened.
DEF_NAME = "frm_event2_def"
DEF_REV_NAME = "frm_event2_def_rev"
PROJ_NAME = "frm_event2_rel2"
DEFINITION_NAMES = (DEF_NAME, DEF_REV_NAME)


def interop_clauses(result):
  """The compact atom's definition, plus the one-way relation projection.

  For every concrete verb V that has a compact atom in the case, both
  directions of the strict definition, one reverse clause per verb:

    event(V,A,T,E,C) -> isa(activity,E)
                     -> has type(E,V,C)
                     -> has actor(E,A,C)
                     -> has target(E,T,C)

    isa(activity,E) & has type(E,V,C) & has actor(E,A,C) & has target(E,T,C)
                     -> event(V,A,T,E,C)

  The reverse clause needs the complete four-atom spine on the same event with
  the same context and the actor and target in their own places, so an
  incomplete or swapped role set mints no compact atom.  The verb is fixed in
  every clause: there is no schema quantified over the verb.

  The projection event -> is_rel2 is emitted for a verb the case also uses as a
  plain three-argument relation, and only in that direction.
  """
  compact = _compact_atoms(result)
  if not compact:
    return []
  verbs = sorted({a[1] for a in compact})
  rel2 = _rel2_verbs(result)
  A, T, E, Ct = "?:Ad2", "?:Td2", "?:Ed2", "?:Cd2"
  out = []
  for V in verbs:
    ev = ["event", V, A, T, E, Ct]
    nev = ["-event", V, A, T, E, Ct]
    out.append({"@name": DEF_NAME, "@logic": [nev, ["isa", "activity", E]]})
    out.append({"@name": DEF_NAME, "@logic": [nev, ["has type", E, V, Ct]]})
    out.append({"@name": DEF_NAME, "@logic": [nev, ["has actor", E, A, Ct]]})
    out.append({"@name": DEF_NAME, "@logic": [nev, ["has target", E, T, Ct]]})
    out.append({"@name": DEF_REV_NAME, "@logic": [
      ["-isa", "activity", E],
      ["-has type", E, V, Ct],
      ["-has actor", E, A, Ct],
      ["-has target", E, T, Ct],
      ev]})
    if V in rel2:
      out.append({"@name": PROJ_NAME, "@logic": [
        nev, ["is rel2", V, A, T, Ct]]})
  seen = set()
  uniq = []
  for c in out:
    key = json.dumps([c["@name"], c["@logic"]], sort_keys=True)
    if key not in seen:
      seen.add(key)
      uniq.append(c)
  return uniq
