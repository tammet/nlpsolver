"""Encoding v2 layout check (migration step 2.10): the situation stands in the world slot of the context term.

No model, no GK.  On every clause of every gold source artifact, of every
gold query input and of the library, the shape is asserted by clause role
and argument position (the plan's table, Sol's review a):

  role                                  world slot of the head     body              blocker
  fact (initial_fact)                   the unit's world           the same world    that world (a defeasible fact)
  standing law, availability path,      the law's variable S       S                 the marker over S (defaults)
  denial law, restriction check, hook,
  necessity, library default and hook
  denial consequence                    S                          S                 none
  effect                                $do(A, S), A the action    S                 none
                                        of the poss premise
  marker                                $do(A, S)                  S (or no body)    none
  frame                                 $do(A, S)                  S                 the marker over $do(A, S), the
                                                                                     head's location variable
  no-inertia                            $do(A, S)                  static            none
  reachability                          reachable($do(A, S), N)    reachable(S, s(N)), poss(A, C(S))
  seed                                  reachable(WROOT, s^k(0))
  snapshot query literal                WROOT
  verify obligation i                   the chain $do(A_{i-1}, ... WROOT)
  plan definition                       the discovery variable

Further: no situation term outside the context term; one situation variable
per law; `present` in every law literal; $obj or the query's knower in K;
the agreement rule of section 5 on every transition law; no Skolem term
depends on a situation; in a snapshot view every law's world slot is the
root; the executable library file has no $source literal.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_route as ar  # noqa: E402
import check_action_validation as cv  # noqa: E402
import fixture_materialize as fm  # noqa: E402
import lc_action as la  # noqa: E402
import lc_action_library as lib  # noqa: E402
import lc_action_query as lq  # noqa: E402
import lc_action_situate as sit  # noqa: E402

DO = sit.DO
LAW_ROLES = ("standing_law", "availability", "denial", "restriction_check", "hook", "necessity_restriction",
             "applicability_default", "hook_default", "ordinary")


class Bad(Exception):
  pass


def need(cond, message):
  if not cond:
    raise Bad(message)


def pred(x):
  return x[0].lstrip("-")


def bears(x):
  """A situation-bearing literal (the template placeholder $source included)."""
  return isinstance(x, list) and x and isinstance(x[0], str) and (sit.bears_situation(pred(x)) or pred(x) == lib.SOURCE)


def situation(x):
  if pred(x) == "reachable":
    return x[1]
  return sit.situation_of(x)


def successor_of(s, var):
  return isinstance(s, list) and len(s) == 3 and s[0] == DO and s[2] == var


def situation_terms(t, out=None):
  """Every situation-like term: a law variable, a world name or a $do term."""
  out = [] if out is None else out
  if isinstance(t, list):
    if t and t[0] == DO:
      out.append(t)
      return out
    for x in t:
      situation_terms(x, out)
  elif t in (sit.SIT, lib.SITUATION) or sit.is_world(t):
    out.append(t)
  return out


def no_stray_situation(where, x):
  """The situation stands in the context's world slot and nowhere else (reachable: argument 1; the answer
  literal $defq0 reports the plan situation)."""
  if pred(x) == lq.DEFQ:
    return
  if pred(x) == "reachable":
    need(len(x) == 3 and not situation_terms(x[2]), "%s: reachable(S, N) with a situation elsewhere: %r" % (where, x))
    return
  if not bears(x):
    need(not situation_terms(x[1:]), "%s: a static literal holds a situation: %r" % (where, x))
    return
  need(sit.is_context(x[-1]), "%s: a situation-bearing literal without its context term: %r" % (where, x))
  need(not situation_terms(x[1:-1]), "%s: a situation argument outside the context term: %r" % (where, x))
  need(not situation_terms(x[-1][:2] + x[-1][3:]), "%s: a situation in another slot of the context: %r" % (where, x))


def skolem_free(where, x):
  """No Skolem term depends on a situation (section 6)."""
  def walk(t):
    if isinstance(t, list):
      if t and isinstance(t[0], str) and t[0].startswith("sk_"):
        need(not situation_terms(t[1:]), "%s: a Skolem term depends on a situation: %r" % (where, t))
      for y in t:
        walk(y)
  walk(x)


def literals_and_blocks(clause):
  lits = [x for x in clause if x[0] != "$block"]
  blocks = [b[2][1] if b[2][0] == "$not" else b[2] for b in clause if b[0] == "$block"]
  return lits, blocks


def check_law(where, role, clause, var, knower=sit.OBJ):
  """One transition or state law: the table above plus the pattern of sections 3 and 5."""
  lits, blocks = literals_and_blocks(clause)
  for x in lits + blocks:
    no_stray_situation(where, x)
    skolem_free(where, x)
  sb = [x for x in lits + blocks if bears(x)]
  for x in sb:
    c = x[-1]
    need(c[1] == "present" and isinstance(c[3], str) and c[3].startswith("?:L") and c[4] == knower,
         "%s: a law literal's context is not $ctxt(present, S, L, %s): %r" % (where, knower, x))
  vars_ = {situation(x) if not isinstance(situation(x), list) else situation(x)[2] for x in sb + [y for y in lits if pred(y) == "reachable"]}
  need(len(vars_) <= 1 and vars_ <= {var}, "%s: one situation variable %s per law, got %r" % (where, var, sorted(map(str, vars_))))
  poss = [x for x in lits if pred(x) == "poss" and x[0].startswith("-")]
  heads = [x for x in lits if not x[0].startswith("-") and bears(x)]
  succ = [x for x in sb if successor_of(situation(x), var)]
  if role in ("effect", "marker", "frame", "derived_no_inertia"):
    heads = [x for x in lits if bears(x) and successor_of(situation(x), var)]
    need(len(heads) == 1, "%s: a %s concludes one literal at $do(A, S): %r" % (where, role, clause))
    need(all(situation(x) == var for x in lits if bears(x) and x is not heads[0]), "%s: a body literal not at S: %r" % (where, clause))
    if poss:
      need(situation(heads[0])[1] == poss[0][1], "%s: the successor's action is not the poss premise's action: %r" % (where, clause))
    need(heads[0][-1][3] == sit.HEAD_L or role == "frame" or heads[0][-1][3] not in [x[-1][3] for x in lits if x is not heads[0] and bears(x)],
         "%s: the successor literal's location variable is shared: %r" % (where, clause))
    if role == "frame":
      premise = [x for x in lits if bears(x) and x[0].startswith("-") and pred(x) != "poss"]
      need(len(premise) == 1 and len(blocks) == 1 and premise[0][-1][3] == heads[0][-1][3] == blocks[0][-1][3]
           and successor_of(situation(blocks[0]), var) and poss and poss[0][-1][3] != heads[0][-1][3],
           "%s: a frame's premise, conclusion and blocker share one location; poss another: %r" % (where, clause))
  elif role == "reachability":
    reach = [x for x in lits if pred(x) == "reachable"]
    need(len(reach) == 2 and reach[0][1] == var and reach[1][1] == [DO, "?:A", var] and poss and situation(poss[0]) == var,
         "%s: reachable(S, s(N)) & poss(A, C(S)) -> reachable($do(A, S), N): %r" % (where, clause))
  else:
    need(not succ, "%s: a %s law holds a successor: %r" % (where, role, clause))
    need(all(situation(x) == var for x in sb), "%s: a %s literal not at S: %r" % (where, role, clause))
    if role != "denial_consequence":
      keys = {}
      for x in [y for y in lits if bears(y)]:
        k = json.dumps([pred(x)] + x[1:-1])
        need(keys.setdefault(x[-1][3], k) == k, "%s: two atoms share a location variable: %r" % (where, clause))
    for b in blocks:
      head = ["poss"] + b[1:] if b[0] == lib.MARKER else None
      need(b[-1][2] == var and (head is None or head in lits) and (b[0] != lib.MARKER or head in lits),
           "%s: a blocker not over S or not repeating its head's context: %r" % (where, clause))


def check_fact(where, clause, world):
  lits, blocks = literals_and_blocks(clause)
  for x in lits + blocks:
    no_stray_situation(where, x)
    skolem_free(where, x)
    if bears(x):
      need(situation(x) == world, "%s: a fact of %s at %r" % (where, world, situation(x)))


def check_library(L):
  n = 0
  for c in L["clauses"]:
    lits = lib.literals(c["clause"])
    need(not any(pred(x) == lib.SOURCE for x in lits), "%s: a $source literal in the executable file" % c["name"])
    if c["role"] == "static_helper":
      for x in lits:
        no_stray_situation(c["name"], x)
    else:
      check_law(c["name"], c["role"], lits, lib.SITUATION)
    n += 1
  for t in L["templates"]:
    for x in lib.literals(t["clause"]):
      no_stray_situation(t["name"], x)
  return n


def chain(seq, root):
  s = root
  for a in seq:
    s = [DO, sit._term(a, set()), s]
  return s


def check_query(where, a, qa, q):
  """The seed, the question literals and the snapshot binding of one query artifact."""
  root = qa["planning_root"]
  kind = qa["query"]["kind"]
  knower = sit.knower_term(qa["knower"]) if qa["knower"] else sit.OBJ
  if qa["seed"]:
    need(qa["seed"]["@logic"] == ["reachable", root, lq.unary(qa["search"]["depth"])], "%s: seed %r" % (where, qa["seed"]))
  for o in qa["obligations"]:
    for pol in ("positive", "negative"):
      part = o[pol]
      if not part:
        continue
      qlits = [part["question"]["@question"]] + [x for c in part["clauses"] for x in lib.literals(c)]
      for x in qlits:
        if not (isinstance(x, list) and x and isinstance(x[0], str)):
          continue
        no_stray_situation(where, x)
        if bears(x):
          s = situation(x)
          if kind in ("plan", "reachable"):
            need(s == sit.SIT, "%s: a plan definition literal not at the discovery variable: %r" % (where, x))
          elif kind == "verify" and o["role"] == "step":
            need(s == chain(qa["query"]["sequence"][:o["step"] - 1], root), "%s: step %s at %r" % (where, o["id"], s))
          elif kind == "verify":
            need(s == chain(qa["query"]["sequence"], root), "%s: the final obligation at %r" % (where, s))
          else:
            need(s == root, "%s: a snapshot question literal at %r, root %s" % (where, s, root))
  inp = ar.query_input(a, qa, qa["obligations"][0]["id"], "positive")
  view = qa["selected_clauses"]["view"]
  for o in inp:
    if "@logic" not in o or str(o.get("@name", "")).startswith("query:"):
      continue
    lits = lib.literals(o)
    name = str(o.get("@name", ""))
    fact = name.startswith("src:") and name.split(":")[-2] == "initial_fact"
    if view == "snapshot" and not fact:
      # a law of a snapshot view: every world slot is the root; a fact keeps its own world
      need(all(situation(x) == root for x in lits if bears(x)), "%s: a snapshot law not bound to the root %s: %r" % (where, root, o))
    if qa["knower"] and not str(o.get("@name", "")).startswith("src:"):
      need(sit.OBJ not in json.dumps(o["@logic"]), "%s: a knower-relative input keeps $obj: %r" % (where, o))


def check_rejections():
  """Clauses in another shape are rejected: each entry must raise Bad."""
  C = lambda s, l="?:L1", k=sit.OBJ: ["$ctxt", "present", s, l, k]
  succ = [DO, ["take", "?:H", "?:X"], sit.SIT]
  bad = [
    ("a separate situation argument", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", sit.SIT, C(sit.SIT)],
                                                                             ["has property", "big", "?:X", C(sit.SIT, "?:L2")]], sit.SIT)),
    ("two situation variables", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", C(sit.SIT)],
                                                                       ["has property", "big", "?:X", C("?:S2", "?:L2")]], sit.SIT)),
    ("a world constant in a law", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", C("W0")],
                                                                          ["has property", "big", "?:X", C(sit.SIT, "?:L2")]], sit.SIT)),
    ("a past tense in a law", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", ["$ctxt", "past", sit.SIT, "?:L1", sit.OBJ]],
                                                                      ["has property", "big", "?:X", C(sit.SIT, "?:L2")]], sit.SIT)),
    ("two atoms sharing one location", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", C(sit.SIT)],
                                                                              ["has property", "big", "?:X", C(sit.SIT)]], sit.SIT)),
    ("an effect at the current situation", lambda: check_law("m", "effect", [["-poss", ["take", "?:H", "?:X"], C(sit.SIT)],
                                                                           ["has property", "held", "?:X", C(sit.SIT, "?:Lh")]], sit.SIT)),
    ("an effect of another action", lambda: check_law("m", "effect", [["-poss", ["take", "?:H", "?:X"], C(sit.SIT)],
                                                                    ["has property", "held", "?:X", C([DO, ["take", "?:H", "?:Y"], sit.SIT], "?:Lh")]], sit.SIT)),
    ("a Skolem term on a situation", lambda: check_law("m", "standing_law", [["-has property", "red", "?:X", C(sit.SIT)],
                                                                            ["have", "?:X", ["sk_U", sit.SIT], C(sit.SIT, "?:L2")]], sit.SIT)),
    ("a fact at another world", lambda: check_fact("m", [["has property", "red", "#:a 1", C("W1", "?:Fv1", "?:Fv2")]], "W0")),
    ("a reachability literal with a context", lambda: no_stray_situation("m", ["reachable", sit.SIT, "?:N", C(sit.SIT)])),
    ("a frame whose blocker has another location", lambda: check_law("m", "frame", [
      ["-has property", "?:V", "?:X", C(lib.SITUATION, "?:L")], ["-poss", "?:A", C(lib.SITUATION, "?:L1")],
      ["has property", "?:V", "?:X", C([DO, "?:A", lib.SITUATION], "?:L")],
      ["$block", 0, ["changed_property", "?:V", "?:X", C([DO, "?:A", lib.SITUATION], "?:L2")]]], lib.SITUATION)),
  ]
  for name, fn in bad:
    try:
      fn()
    except Bad:
      continue
    raise Bad("the layout check accepted %s" % name)
  del succ
  return len(bad)


def run():
  n_bad = check_rejections()
  L = ar._library()
  n_lib = check_library(L)
  facts = laws = queries = 0
  for case in fm.load_all():
    if cv.profile_name(case["profile"]) != la.PROFILE or not case["units"]:
      continue
    a = cv.gold_source(case)
    for u in a["units"]:
      for r in u["clauses"] or []:
        w = "%s/%s/%s" % (case["case"], u["id"], r["role"])
        if r["role"] == "initial_fact":
          check_fact(w, r["clause"], u["world"])
          facts += 1
        elif r["role"] in ("static", "distinct"):
          for x in r["clause"]:
            no_stray_situation(w, x)
        else:
          check_law(w, r["role"], r["clause"], sit.SIT)
          laws += 1
    for r in (a["restriction_clauses"] or []) + (a["policy_clauses"] or []):
      if any(bears(x) for x in r["clause"]):
        check_law("%s/%s" % (case["case"], r["role"]), r["role"], r["clause"], sit.SIT)
        laws += 1
    if a["support"]["status"] != "supported":
      continue
    for q in case["queries"]:
      if not q.get("stage2"):
        continue
      qa = ar.compile_query(q["stage2"], a, cv.gold_limits(q), **fm.selection(q))
      if qa["outcome"] or not qa["obligations"]:
        continue
      check_query("%s/%s" % (case["case"], q["id"]), a, qa, q)
      queries += 1
  # the ordinary view is in the law pattern too
  for view in ("snapshot", "verify", "discovery"):
    for r in lq.ordinary_view(view, lq.selection("W1")):
      if view == "snapshot":
        need(all(situation(x) == "W1" for x in r["clause"]), "ordinary snapshot binding: %r" % r)
      else:
        check_law(r["name"], "ordinary", r["clause"], sit.SIT)
  print("  layout: %d library clauses, %d source law clauses, %d facts and %d gold query inputs have the situation in the "
        "world slot and nowhere else, by role and argument position; the agreement rule holds; %d clauses in another "
        "shape are rejected" % (n_lib, laws, facts, queries, n_bad))


if __name__ == "__main__":
  run()
