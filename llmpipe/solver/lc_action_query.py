"""Action profile: query views, proof obligations and per-query backend requirements.

The last compiler pass (`query_views`).  It reads a supported source artifact
and one validated query and produces, without a model and without a prover:

  the input view     which source clauses and which library clauses a prover
                     input of this query holds (A3.3)
  the obligations    the prover questions of the query, each with its own
                     definition clauses; a Boolean obligation has a positive
                     and a negative question, because one GK launch answers
                     one polarity (A3.4)
  the requirements   the backend capabilities this query needs, decided from
                     the source dependencies and the query horizon (A6.3)

Selection (encoding v2).  A query names its planning root (a declared
world; default the last declared world), optionally an ambient location and
a knower.  The root's world name roots the seed, the snapshot view and every
action chain; a query literal's context is $ctxt(present, S, L, K) with S its
situation (the root, a chain from it, or the discovery variable) in the world
slot, L the ambient constant or a fresh variable and K the knower constant or
a fresh variable.  A fact unit leaves every view of the query, with its reason in the
query artifact's `excluded` list, when its tense is past or future
(underspecified_temporal_root), when its location is a scope other than the
ambient (scope_location_mismatch), or when it has a knower other than the
query's (knower_mismatch).  A knower-relative query gives every law the
knower in place of $obj.  The query's dependency checks (negative
persistence here, transport and location granularity in `action_route`) read
the same selection: the units that are not excluded, and the initial facts of
the root's world (`admitted`).

Views.  `snapshot` serves question, ask and verify([], Q): source clauses but
effects, markers and no-inertia facts, with `?:Sit` bound to the root's
world name, plus the library's snapshot roles bound the same way.  `verify`
holds every source clause and every library role but reachability.
`discovery` holds everything and the seed.  Every view holds the selected
ordinary families (V1-core, the plan's section 6), bound to the root in a
snapshot.  Clauses are selected by role and unit, never by their text.

Situations.  A question or ask formula gets the root's situation in every
situation-bearing atom, also `executable` and atoms under a quantifier or a
conditional.  A plan or reachable goal gets one shared variable `?:Sit`.  A
verify step i is asked at the root-based chain of the steps before it, and
the final formula at the whole chain.  `executable(A)` becomes
`poss(A, C)`, with the situation S in the world slot of C.  No obligation is asserted: a supplied sequence adds no poss
and no reachable fact.

Nothing here decides an answer.  A positive and a negative obligation are
related by their ids; the adapter (WP12) runs them and the answer policy
(WP13) combines them.
"""

import copy

import lc_action as la
import lc_action_effects as ef
import lc_action_library as lib
import lc_action_situate as sit

PASS = "query_views"
DEFQ = "$defq0"
QUERY_L, QUERY_K = "?:Qv1", "?:Qv2"
EXCLUSIONS = ("underspecified_temporal_root", "scope_location_mismatch", "knower_mismatch")
# the selected ordinary view (migration plan section 6): the reviewed V1-core family, in the law pattern; the
# layout experiment's family E (elogs/situation_context_experiment_2026_09_22/gen.py, FAMILY_E)
ORDINARY_FAMILIES = {"V1-core": (
  ("on_not_under", [["-is rel2", "on", "?:X", "?:Y"], ["-is rel2", "under", "?:X", "?:Y"]]),
  ("on_not_below", [["-is rel2", "on", "?:X", "?:Y"], ["-is rel2", "below", "?:X", "?:Y"]]))}
SELECTED_FAMILIES = ("V1-core",)
DEPTH_VARIABLE = "?:N"
# source clause roles a snapshot leaves out: they speak about a successor situation
SNAPSHOT_EXCLUDED = ("effect", "marker", "derived_no_inertia")
NEGATIVE_PERSISTENCE = "negative_persistence"
SHARED_CONFIDENCE = "shared_source_confidence"
UNAVAILABLE = {NEGATIVE_PERSISTENCE: "negative_persistence_unavailable"}


class Unsupported(Exception):
  """A validated query this pass has no clauses for: (reason, message)."""

  def __init__(self, reason, message):
    Exception.__init__(self, message)
    self.reason = reason


# ---------------------------------------------------------------------------
# 0. the selection: planning root, ambient, knower


def selection(planning_root="W0", ambient=None, knower=None):
  return {"planning_root": planning_root, "ambient": ambient, "knower": knower}


DEFAULT = selection()


def root_situation(sel=None):
  """The situation of the planning root: its world name."""
  return (sel or DEFAULT)["planning_root"]


def query_context(sel=None):
  """The context term of a query literal: the root world, the ambient or a fresh L, the knower or a fresh K."""
  sel = sel or DEFAULT
  return ["$ctxt", "present", sel["planning_root"],
          sit.knower_term(sel["ambient"]) if sel.get("ambient") else QUERY_L,
          sit.knower_term(sel["knower"]) if sel.get("knower") else QUERY_K]


def exclusions(units, sel=None):
  """[{unit, reason}] of the fact units this query's views leave out (migration plan sections 2, 3 and 9).

  A unit's facts are kept in the source artifact with their qualifiers; the
  query decides.  Only a unit with a context record can be excluded.
  """
  sel = sel or DEFAULT
  out = []
  for u in units:
    c = u.get("context")
    if not c:
      continue
    reason = None
    if (c.get("tense") or "present") != "present":
      reason = "underspecified_temporal_root"
    elif c.get("location") is not None and c.get("location_role") == "scope" and c["location"] != sel.get("ambient"):
      reason = "scope_location_mismatch"
    elif c.get("knower") is not None and c["knower"] != sel.get("knower"):
      reason = "knower_mismatch"
    if reason:
      out.append({"unit": u["id"], "reason": reason})
  return out


def admitted(units, excluded=()):
  """The source units that a query's dependency and granularity checks read: every unit but the excluded ones.

  The checks read the facts the query's views keep (Astra's review R2).  An
  excluded unit leaves as a whole, as its clauses leave the views.  A
  description of another world stays: its static facts hold in every world,
  and each reader of initial fluent facts takes the facts of the planning
  root's world only.  Laws have no context record and always stay.
  """
  gone = {x["unit"] for x in excluded}
  return [u for u in units if u["id"] not in gone]


# ---------------------------------------------------------------------------
# 1. the input view


def selected_view(kind, sequence):
  """The clause view of a query kind.  An empty supplied sequence is an initial-state question."""
  if kind in ("plan", "reachable"):
    return "discovery"
  if kind == "verify" and sequence:
    return "verify"
  return "snapshot"


def clause_name(n, record):
  """The stable name of a source clause: its place in the artifact's clause list, its unit and its role."""
  who = record.get("unit") or "+".join(record.get("units") or ["source"])
  return "src:%s:%s:%d" % (who, record["role"], n)


def source_view(artifact, view, sel=None, excluded=()):
  """The source clause records of a view, each with its `name`.  The artifact is not changed.

  The clauses of an excluded unit are left out.  A snapshot binds `?:Sit` to
  the root's world name; a named knower replaces $obj in every view.
  """
  sel = sel or DEFAULT
  gone = {x["unit"] for x in excluded}
  out = []
  for n, r in enumerate(artifact["clauses"] or []):
    if view == "snapshot" and r["role"] in SNAPSHOT_EXCLUDED:
      continue
    if r.get("unit") in gone:
      continue
    rec = copy.deepcopy(r)
    rec["name"] = clause_name(n, r)
    if view == "snapshot":
      rec["clause"] = lib._substitute(rec["clause"], sit.SIT, root_situation(sel))
    if sel.get("knower"):
      rec["clause"] = lib._substitute(rec["clause"], sit.OBJ, sit.knower_term(sel["knower"]))
    out.append(rec)
  return out


def ordinary_view(view, sel=None, families=SELECTED_FAMILIES):
  """The selected ordinary laws of a view, as {"name", "role", "family", "clause"} records, in the law pattern.

  A snapshot binds their situation to the root; a named knower replaces $obj.
  """
  sel = sel or DEFAULT
  out = []
  for fam in families:
    for name, lits in ORDINARY_FAMILIES[fam]:
      make = sit.law_contexts()
      clause = []
      for x in lits:
        ctx = make(x + [sit.SIT])
        clause.append(list(x) + [ctx])
      if view == "snapshot":
        clause = lib._substitute(clause, sit.SIT, root_situation(sel))
      if sel.get("knower"):
        clause = lib._substitute(clause, sit.OBJ, sit.knower_term(sel["knower"]))
      out.append({"name": "ordinary:%s:%s" % (fam, name), "role": "ordinary", "family": fam, "clause": clause})
  return out


def view_records(artifact, library, view, sel=None, excluded=()):
  """(source records, library records, ordinary records) of a view.  The default hook of a restricted constructor
  is left out."""
  sel = sel or DEFAULT
  restricted = sorted((artifact.get("restrictions") or {}).get("constructors") or {})
  return (source_view(artifact, view, sel, excluded),
          lib.select(library, view, restricted, root=sel["planning_root"], knower=sel.get("knower")),
          ordinary_view(view, sel))


# ---------------------------------------------------------------------------
# 2. situated query formulas and their clauses


def chain(sequence, root="W0"):
  """The root-based situation of a ground action list, in source spelling."""
  s = root
  for act in sequence:
    s = [sit.DO, copy.deepcopy(act), s]
  return s


def _strip(f):
  """A question asks what holds, not what normally holds; `executable` is the library's poss."""
  if not isinstance(f, list) or not f:
    return f
  if f[0] == "normally":
    return _strip(f[1])
  if f[0] == "executable":
    return ["poss", f[1]]
  if f[0] in la.FLUENTS or f[0] in la.STATIC or f[0] in ("poss", "="):
    return list(f)
  return [f[0]] + [_strip(x) for x in f[1:]]


def situated(formula, situation):
  """The query formula with `situation` in every situation-bearing atom."""
  try:
    return sit._situate(_strip(formula), situation)
  except sit.NotCompiled as e:
    raise Unsupported("unsupported_goal_form", str(e))


def _namer(qid):
  seen = {}

  def name(v):
    seen[v] = seen.get(v, 0) + 1
    return "skq_%s_%s" % (qid, v) if seen[v] == 1 else "skq_%s_%s_%d" % (qid, v, seen[v])
  return name


def _clauses(formula, qid, context):
  """Clause literal lists of a situated formula, in the query context `context`."""
  try:
    nnf = sit._nnf(formula)
  except sit.Unsupported as e:
    raise Unsupported("unsupported_goal_form", str(e))
  universals = sit._collect_universals(nnf, [])
  matrix = sit._skolemize(nnf, [], qid, _namer(qid), [])
  out = []
  for clause in sit._cnf(matrix):
    lits = []
    for x in clause:
      y = sit._literal(x, set(universals), copy.deepcopy(context))
      if y not in lits:
        lits.append(y)
    out.append(lits)
  return out


def _is_ground_literal(f):
  atom = f[1] if f[0] == "not" else f
  return sit._is_literal(f) and not _variables(atom)


def _variables(t, out=None):
  out = set() if out is None else out
  if isinstance(t, list):
    for x in t:
      _variables(x, out)
  elif (la.is_var(t) and not sit.is_world(t)) or (isinstance(t, str) and t.startswith("?:")):
    out.add(t)
  return out


def question(body, qid, tag, answer=(), extra=(), context=None):
  """One prover question for `body`.

  A ground literal is asked directly.  Any other body gets the definition
  `body -> $defq0(answer...)`, one direction, and the question `$defq0(...)`;
  an existential of the body is then a clause variable and a universal of the
  body a Skolem constant, as the negated goal needs.  `answer` names the
  variables the prover reports; `extra` are literals every definition clause
  also needs (the reachability requirement of a discovery).  `context` is
  the query context term (`query_context`).
  """
  context = context or query_context()
  name = "query:%s:%s" % (qid, tag)
  if not answer and not extra and _is_ground_literal(body):
    lit = sit._literal(body, set(), copy.deepcopy(context))
    return {"form": "literal", "clauses": [], "question": {"@name": name, "@question": lit}}
  head = [DEFQ] + list(answer)
  f = ["implies", body, head]
  for v in reversed([x for x in answer if x != sit.SIT]):
    f = ["forall", v, f]
  if sit.SIT in _variables(body):
    f = ["forall", sit.SIT, f]
  clauses = [[copy.deepcopy(x) for x in extra] + c for c in _clauses(f, qid, context)]
  q = {"@name": name, "@question": [DEFQ] + [x if x == sit.SIT else "?:v_" + x for x in answer]}
  if answer:
    q["@askvars"] = len(answer)
  return {"form": "definition",
          "clauses": [{"@name": "%s:definition:%d" % (name, n), "@sourcetype": "question", "@logic": c}
                      for n, c in enumerate(clauses)],
          "question": q}


def render(f):
  """A short text of a situated formula, for a reader: on(a 2,b 3,S2)."""
  if not isinstance(f, list):
    return str(f)
  if f[0] == sit.DO:
    n, s = 0, f
    while isinstance(s, list) and s and s[0] == sit.DO:
      n, s = n + 1, s[2]
    return "%s+%d" % (s, n) if sit.is_world(s) else "do^%d(%s)" % (n, render(s))
  if f[0] in ("is rel2", "has property"):
    return "%s(%s)" % (f[1], ",".join(render(x) for x in f[2:]))
  return "%s(%s)" % (f[0], ",".join(render(x) for x in f[1:]))


# ---------------------------------------------------------------------------
# 3. obligations


def unary(depth):
  t = "0"
  for _ in range(depth):
    t = ["s", t]
  return t


def _paired(oid, role, body, qid, context, **fields):
  """A Boolean obligation: the positive question and the question of its explicit negation."""
  out = {"id": oid, "role": role, "formula": body, "text": render(body),
         "positive": question(body, qid, oid + ":positive", context=context),
         "negative": question(body[1] if body[0] == "not" else ["not", body], qid, oid + ":negative", context=context)}
  out.update(fields)
  return out


def _outer_witnesses(goal, names):
  """The goal with its existential binders removed, when their names are distinct: each is then reported."""
  if len(set(names)) != len(names):
    return goal, []

  def drop(f):
    if isinstance(f, list) and f and f[0] == "exists":
      return drop(f[2])
    if isinstance(f, list) and f and f[0] == "and":
      return ["and"] + [drop(x) for x in f[1:]]
    return f
  return drop(goal), list(names)


def obligations(query, search, sel=None):
  """The obligations of a validated, supported query under the selection `sel`.

  snapshot    one paired obligation at the root; an `ask` has the positive question
              only, with its variable reported
  verify      one paired obligation per step, `poss(A_i)` at the chain of the
              steps before it, and one for the final formula at the whole
              chain.  A negative step obligation licenses No only after the
              `requires_prefix` steps before it are established and validated;
              a negative final obligation needs the whole sequence.
  discovery   one positive question for a reachable situation with the goal;
              the seed is a query clause.  No negative reachability question.

  Returns {"obligations", "seed", "joint_positive"}.
  """
  kind, goal, qid = query["kind"], query["goal"], query["id"]
  ctx, root = query_context(sel), root_situation(sel)
  out = {"obligations": [], "seed": None, "joint_positive": None}
  if kind == "question":
    out["obligations"].append(_paired("q", "snapshot", situated(goal, root), qid, ctx, situation=root))
  elif kind == "ask":
    body = situated(goal, root)
    out["obligations"].append({"id": "q", "role": "snapshot", "formula": body, "text": render(body), "situation": root,
                               "positive": question(body, qid, "q:positive", answer=[query["variable"]], context=ctx),
                               "negative": None})
  elif kind == "verify":
    seq = query["sequence"]
    parts = []
    for i, act in enumerate(seq):
      body = situated(["executable", act], chain(seq[:i], root))
      parts.append(body)
      out["obligations"].append(_paired("step%d" % (i + 1), "step", body, qid, ctx, step=i + 1,
                                        situation=chain(seq[:i], root), requires_prefix=i))
    final = situated(goal, chain(seq, root))
    parts.append(final)
    out["obligations"].append(_paired("final", "final" if seq else "snapshot", final, qid, ctx,
                                      situation=chain(seq, root), requires_prefix=len(seq)))
    if seq:
      # the one positive proof obligation of A3.4, with one shared context; the paired list above is what a verdict needs
      out["joint_positive"] = question(["and"] + parts, qid, "joint:positive", context=ctx)
  else:
    body, witnesses = _outer_witnesses(situated(goal, sit.SIT), query.get("witnesses") or [])
    remaining = "0" if search["require_zero_remaining"] else DEPTH_VARIABLE
    reach = ["-reachable", sit.SIT, remaining]
    out["seed"] = {"@name": "query:%s:seed" % qid, "@logic": ["reachable", root, unary(search["depth"])]}
    out["obligations"].append({"id": "plan", "role": "discovery", "formula": body, "text": render(body),
                               "situation": sit.SIT, "remaining": remaining, "witnesses": witnesses,
                               "positive": question(body, qid, "plan:positive", answer=[sit.SIT] + witnesses, extra=[reach],
                                                    context=ctx),
                               "negative": None})
  return out


# ---------------------------------------------------------------------------
# 4. backend requirements of one query


def _negative_facts(f, out, positive=True):
  """The dynamic atoms an initial description states negatively.  A conditional negative counts: it may hold."""
  op = f[0]
  if op == "not":
    _negative_facts(f[1], out, not positive)
  elif op in ("and", "or", "normally"):
    for x in f[1:]:
      if isinstance(x, list):
        _negative_facts(x, out, positive)
  elif op in la.QUANTIFIERS:
    _negative_facts(f[2], out, positive)
  elif op == "implies":
    _negative_facts(f[2], out, positive)
  elif op in la.FLUENTS and not positive:
    out.append(f)
  return out


def _initial_negatives(units, root):
  """(unit, atom) of the negative fluent facts that the root world's initial descriptions state."""
  return [(u["id"], a) for u in units if u["status"] == "supported" and u["form"] == "description_initial"
          and (u.get("world") or "W0") == root for a in _negative_facts(sit._unit_formula(u), [])]


def _effect_writes(units):
  """(unit, action pattern, atom, sign, conditional) of every text effect head."""
  out = []
  for u in units:
    if u["status"] != "supported" or u["form"] != ef.FORM:
      continue
    for scope, conditions, action, heads in ef.effects(sit._unit_formula(u)):
      for h in heads:
        out.append((u["id"], action, ef._atom(h), ef._sign(h), bool(conditions)))
  return out


def _library_negative_writes(library):
  """(clause name, action pattern, atom pattern) of every negative library effect."""
  out = []
  for c in (library or {}).get("clauses", []):
    if c["role"] != "effect":
      continue
    lits = lib.literals(c["clause"])
    concl = [x for x in lits if lib.predicate(x) in la.FLUENTS and isinstance(sit.situation_of(x), list)]
    poss = [x for x in lits if x[0] == "-poss"]
    if concl and poss and not lib.positive(concl[0]):
      out.append((c["name"], ef._plain(poss[0][1]), ef._plain([lib.predicate(concl[0])] + concl[0][1:-1])))
  return out


def _meets(a, b):
  return ef._unify(ef._standardize(a, "a"), ef._standardize(b, "b"), {}) is not None


def _class_may_hold(entity, cls, units, classes):
  """False only for a stated entity whose class facts lack `cls` while no source rule concludes that class."""
  if not la.is_concrete(entity) or cls in classes.get(entity, []):
    return True
  for u in units:
    if u["status"] == "supported" and u["form"] in ("description_initial", "description_static"):
      if any(a[0] == "isa" and a[1] == cls and not la.is_concrete(a[2]) for a in ef._positive_facts(sit._unit_formula(u), [])):
        return True
  return False


def _default_may_apply(action, units, library):
  """Whether a library executability default can license an action of this pattern (its class guards may hold)."""
  classes = ef._classes(units)
  for c in (library or {}).get("clauses", []):
    if c["role"] != "applicability_default":
      continue
    s = ef._unify(ef._standardize(ef._plain(lib.head(c["clause"], "poss")[1]), "d"), ef._standardize(action, "a"), {})
    if s is None:
      continue
    guards = [(g[1], ef._apply(ef._standardize(ef._plain(g[2]), "d"), s)) for g in lib.literals(c["clause"]) if g[0] == "-isa"]
    if all(_class_may_hold(t[5:] if isinstance(t, str) and t.startswith("?:a_") else t, cls, units, classes) for cls, t in guards):
      return True
  return False


def _may_be_available(actions, units, library):
  """Whether an action of these patterns can have a sufficient rule: a source availability or a library default.

  An action without any permission is never executable, so a law about it is
  irrelevant to every plan.  This is the one relevance test of v1.
  """
  given = [t for u in units if u["status"] == "supported" and u["form"] == "availability" for t in u.get("action_terms") or []]
  return any(_meets(a, t) for a in actions for t in given) or any(_default_may_apply(a, units, library) for a in actions)


def _instance(pattern, atom, lit):
  """The action pattern of a write, narrowed by the fact that its atom is the read literal."""
  s = ef._unify(ef._standardize(atom, "w"), ef._standardize(lit, "r"), {})
  return None if s is None else ef._apply(ef._standardize(pattern, "w"), s)


def _closure(reads, deps):
  """Reads plus the body reads of every standing law whose head a read meets (A6.3: indirect dependencies)."""
  laws = [d for d in deps["units"] if d["form"] == "state_law"]
  out, todo = [], list(reads)
  while todo:
    lit, sign = todo.pop()
    if (lit, sign) in out:
      continue
    out.append((lit, sign))
    for d in laws:
      if any(_meets(w["literal"], lit) for w in d["writes"]):
        todo.extend((r["literal"], r["sign"]) for r in d["reads"] if r["dynamic"])
  return out


def _goal_reads(goal):
  """(atom, sign) of the fluent literals and the actions of the `executable` atoms of a goal."""
  reads, actions = [], []

  def walk(f, positive):
    if not (isinstance(f, list) and f):
      return
    if f[0] == "not":
      walk(f[1], not positive)
    elif f[0] in la.QUANTIFIERS:
      walk(f[2], positive)
    elif f[0] in ("and", "or", "implies", "normally"):
      for x in f[1:]:
        walk(x, positive)
    elif f[0] in la.FLUENTS:
      reads.append((f, "+" if positive else "-"))
    elif f[0] == "executable":
      actions.append(f[1])
  walk(goal, True)
  return reads, actions


def _discovery_persistence(goal, depth, units, deps, library, root):
  """The negative-persistence dependency of a discovery, or None.

  An established negative is an initial negative fact of the root's world or
  a negative write.  A law reads the situation before its action, the goal reads the final one.
  The requirement applies when a transition can lie between the two
  (REVIEW.md disposition 8):

                      read by a law      read by the goal
    initial negative    depth >= 2          depth >= 1
    written negative    depth >= 3          depth >= 2

  A law about an action without any permission is left out.  No other
  relevance is ruled out: a positive writer does not lift the requirement,
  because a plan may still pass an unrelated action first (c02).
  """
  initial = _initial_negatives(units, root)
  written = [(uid, action, atom) for uid, action, atom, sign, cond in _effect_writes(units) if sign == "-"] \
    + _library_negative_writes(library)
  law_reads = []
  for d in deps["units"]:
    if d["form"] in ("availability", "denial", "restriction", "effect") and _may_be_available(d["actions"], units, library):
      law_reads.extend((d["unit"], r["literal"], r["sign"]) for r in d["reads"] if r["dynamic"])
  goal_reads = [("goal", a, s) for a, s in _goal_reads(goal)[0]]
  hits = []
  for level, reads, need_initial, need_written in (("law", law_reads, 2, 3), ("goal", goal_reads, 1, 2)):
    by = {}
    for who, lit, sign in reads:
      for l2, s2 in _closure([(lit, sign)], deps):
        if s2 == "-":
          by.setdefault(repr(l2), (who, l2))
    for who, lit in by.values():
      for src, atom in initial:
        if depth >= need_initial and _meets(atom, lit):
          hits.append({"read_by": who, "level": level, "literal": copy.deepcopy(lit), "established": "initial",
                       "established_by": src, "needs_depth": need_initial})
      for src, action, atom in written:
        # a write counts when its action, narrowed to this fact, can have a permission
        act = _instance(action, atom, lit) if depth >= need_written else None
        if act is not None and _may_be_available([_unstandardize(act)], units, library):
          hits.append({"read_by": who, "level": level, "literal": copy.deepcopy(lit), "established": "written",
                       "established_by": src, "needs_depth": need_written})
  return hits or None


def _unstandardize(t):
  """Standardized variables back to plain variable names; the term is used for one unification only."""
  if isinstance(t, list):
    return [_unstandardize(x) for x in t]
  return "?:" + t[4:] if isinstance(t, str) and t.startswith(("?:w_", "?:r_")) else t


def _step_writes(action, units, library):
  """(atom, sign, certain) of what one ground action writes: text effects and library effects."""
  out = []
  for uid, pattern, atom, sign, conditional in _effect_writes(units):
    s = ef._unify(ef._standardize(pattern, "e"), action, {})
    if s is not None:
      out.append((ef._apply(ef._standardize(atom, "e"), s), sign, not conditional))
  for w in ef.library_writes(action, library):
    out.append((w["literal"], w["sign"], not w["conditional"]))
  return out


def _action_reads(action, deps):
  """(unit, atom, sign, necessity) of the dynamic reads of every law unit whose action pattern meets `action`.

  A restriction reads its required literal positively, and its necessity
  clause uses the negation: `not REQUIRED -> not poss`.  A carried negative
  then decides a No, so that read counts as well (c20 a_red Q7).
  """
  out = []
  # an unconditional denial of this action refutes it at every situation; a carried negative adds nothing to that No
  denied = any(d["form"] == "denial" and not d["reads"] and any(ef._unify(ef._standardize(p, "u"), action, {}) is not None
                                                                for p in d["actions"]) for d in deps["units"])
  for d in deps["units"]:
    if d["form"] not in ("availability", "denial", "restriction", "effect"):
      continue
    for pattern in d["actions"]:
      s = ef._unify(ef._standardize(pattern, "u"), action, {})
      if s is None:
        continue
      for r in d["reads"]:
        necessity = d["form"] == "restriction" and r["sign"] == "+"
        if r["dynamic"] and not (necessity and denied):
          out.append((d["unit"], ef._apply(ef._standardize(r["literal"], "u"), s), r["sign"], necessity))
  return out


def _verify_persistence(goal, sequence, units, deps, library, root):
  """The negative-persistence dependency of a supplied sequence, or None.

  The scan is structural and decides no executability.  A read at the
  situation after step i needs a carried negative when the negative was
  established before step i (initially or by an earlier step), no certain
  positive write came after it, and step i itself does not certainly write
  the fact.  A certain write is an unconditional effect on exactly that fact.
  """
  if not sequence:
    return None
  initial = _initial_negatives(units, root)
  writes = [_step_writes(a, units, library) for a in sequence]
  points = []
  for i, act in enumerate(sequence):
    if i:
      points.append((i, "step %d" % (i + 1), _action_reads(act, deps)))
  freads, factions = _goal_reads(goal)
  final = [("final formula", a, s, False) for a, s in freads]
  for act in factions:
    final.extend(_action_reads(act, deps))
  points.append((len(sequence), "final formula", final))
  hits = []
  for i, where, reads in points:
    for who, lit, sign, necessity in reads:
      for l2, s2 in _closure([(lit, sign)], deps):
        if s2 != "-" and not (necessity and l2 == lit):
          continue
        direct = any(certain and atom == l2 for atom, sg, certain in writes[i - 1])
        if direct:
          continue
        cleared = max([j + 1 for j in range(i) for atom, sg, certain in writes[j] if certain and sg == "+" and atom == l2] or [-1])
        stated = sorted({u for u, a in initial if _meets(a, l2)}) if cleared < 0 else []
        established = ([0] if stated else []) \
          + [j + 1 for j in range(i) for atom, sg, certain in writes[j] if sg == "-" and j + 1 > cleared and _meets(atom, l2)]
        if any(e < i for e in established):
          hits.append({"read_by": who, "level": where, "literal": copy.deepcopy(l2), "situation": i,
                       "established": "initial" if stated else "written", "established_by": stated or None,
                       "established_at": min(established)})
  return hits or None


def _uncertain_paths(units):
  """The supported availability units with a source probability below 1: their paths hold the evidence 2p - 1."""
  return [u for u in units if u["status"] == "supported" and u["form"] == "availability"
          and u.get("confidence") is not None and u["confidence"] < 1]


def _shared_units(kind, sequence, units):
  """The uncertain availability units whose path a proof of this query can use more than once in one application.

  One action application reads `poss` several times: the reachability step,
  every effect of the action and every frame across it.  GK counts the
  evidence of an uncertain path once per use in a proof, so one application
  can count the source twice (checkpoint-2 decision, C29.Q2).  The backend
  then has to count one application once: `shared_source_confidence`.
  Discovery: every uncertain path.  Verify with steps: a path whose action
  meets a step.  The declaration is conservative.  Another sufficient rule for
  the same action does not remove it: unifying action patterns does not show
  that the other rule applies, or that it covers every application a proof
  uses (Astra's review R1, 2026-09-24).  A snapshot query is not analysed; a
  conjunction of `executable` atoms and overlapping paths have no provenance
  test yet.
  """
  paths = _uncertain_paths(units)
  if not paths:
    return []
  if kind in ("plan", "reachable"):
    return sorted(u["id"] for u in paths)
  if kind == "verify" and sequence:
    return sorted(u["id"] for u in paths if any(_meets(t, a) for t in u.get("action_terms") or [] for a in sequence))
  return []


def _executables(f, out=None):
  out = [] if out is None else out
  if isinstance(f, list) and f:
    if f[0] == "executable":
      out.append(f)
    else:
      for x in f[1:]:
        _executables(x, out)
  return out


def _hit_units(hits, units):
  """The source units of a dependency: who reads the negative and who states or writes it.  Library clauses are left out."""
  ids = {u["id"] for u in units}
  named = set()
  for h in hits:
    by = h.get("established_by")
    named.update([h["read_by"]] + (by if isinstance(by, list) else [by]))
  return sorted(x for x in named if x in ids)


def backend_requirements(query, search, units, deps, library, root="W0"):
  """The backend capabilities this query needs: a list of {capability, units, detail, evidence}.

  `units` are the units the query's selection admits (`admitted`), `root` its
  planning root: an initial negative of another world, or of an excluded
  unit, is no initial fact of this query.
  """
  out = []
  kind = query["kind"]
  if deps:
    hits = None
    if kind in ("plan", "reachable") and search and search["depth"] is not None:
      hits = _discovery_persistence(query["goal"], search["depth"], units, deps, library, root)
    elif kind == "verify":
      hits = _verify_persistence(query["goal"], query["sequence"], units, deps, library, root)
    if hits:
      out.append({"capability": NEGATIVE_PERSISTENCE,
                  "units": _hit_units(hits, units),
                  "detail": "a negative fact is read after a transition that does not write it; the starting backend has no "
                            "negative frame, so it would lose the fact",
                  "evidence": hits})
  shared = _shared_units(kind, query["sequence"], units)
  if shared:
    out.append({"capability": SHARED_CONFIDENCE, "units": shared,
                "detail": "a proof can use the path of an uncertain source rule more than once in one action application "
                          "(the reachability step, an effect and a frame each read poss); the backend must count that "
                          "application once",
                "evidence": None})
  return out
