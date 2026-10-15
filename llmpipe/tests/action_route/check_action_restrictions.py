"""WP07 unit checks: restrictions, checks, hooks, negative necessities.

No model, no GK.  Two kinds of check:

  clause inspection   gold patterns (restriction_check, hook, path_coverage,
                      necessity_restriction), the coverage table, the
                      unsupported patterns and their details
  derivation          a small unit-resulting resolution over the compiled
                      clauses and the library's snapshot view, at W0.  It
                      derives signed literals only.  It reads a default
                      clause in its head direction, and only when the
                      strict clauses do not give the head's complement.
                      It is a test tool, not the route's prover, and says
                      nothing about what GK proves (WP10 measures that).

  gold answers   every ground `question executable(A)` of a supported gold
                 case that holds a restriction: Yes, No, Unknown, contested
  requirement    true, false, unknown and both, for one required condition
  conjunction    hand one needs red and dry; another known hand needs red;
                 an unknown hand stays unproven
  put_on         one restriction on both branches; a failed block branch
                 does not refute the surface branch
  movement       the public path and the stated-endpoint path under one
                 restriction
  no bypass      no clause concludes a positive poss or a required condition;
                 an unknown requirement derives neither poss nor the condition;
                 a restriction never yields the denial marker (encoding v2)
  unsupported    state guard, free variable, repeated lexical variable, slot
                 equality, can -> Q, an uncertain restriction
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_route as ar
import check_action_availability as cav
import fixture_materialize as fm
import lc_action as la
import lc_action_library as lib
import lc_action_query as lq
import lc_action_restrict as rs
import lc_action_situate as sit

need = cav.need
Bad = cav.Bad


# ---------------------------------------------------------------------------
# a small unit-resulting resolution, for tests only


def with_pending(a, name="a_later_pass"):
  """A copy of a source artifact that names one more pending pass, rehashed."""
  b = copy.deepcopy(a)
  b["pending_passes"].append(name)
  b["hashes"] = ar.source_hashes(b)
  return b


def _is_v(t):
  return isinstance(t, str) and t.startswith("?:")


def _walk(t, s):
  while _is_v(t) and t in s:
    t = s[t]
  return t


def _unify(a, b, s):
  a, b = _walk(a, s), _walk(b, s)
  if a == b:
    return s
  if _is_v(a):
    return dict(s, **{a: b})
  if _is_v(b):
    return dict(s, **{b: a})
  if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
    for x, y in zip(a, b):
      s = _unify(x, y, s)
      if s is None:
        return None
    return s
  return None


def _apply(t, s):
  t = _walk(t, s)
  return [_apply(x, s) for x in t] if isinstance(t, list) else t


def _rename(t, tag):
  if isinstance(t, list):
    return [_rename(x, tag) for x in t]
  return "%s~%s" % (t, tag) if _is_v(t) else t


def _freeze(t):
  if isinstance(t, list):
    return [_freeze(x) for x in t]
  return "!" + t if _is_v(t) else t


def _neg(lit):
  return [lit[0][1:] if lit[0].startswith("-") else "-" + lit[0]] + lit[1:]


def _known(facts, lit):
  """Some fact is at least as general as lit."""
  frozen = _freeze(lit)
  return any(_unify(_rename(f, "k"), frozen, {}) is not None for f in facts.get(lit[0], []))


def _canonical(lit):
  names = {}

  def go(t):
    if isinstance(t, list):
      return [go(x) for x in t]
    return names.setdefault(t, "?:%d" % len(names)) if _is_v(t) else t
  return go(lit)


def _depth(t):
  """The nesting of $do in a term."""
  if isinstance(t, list):
    return (1 if t and t[0] == "$do" else 0) + max([_depth(x) for x in t] + [0])
  return 0


def _derive(clause, facts, heads, counter, extra=None):
  """(derived literal, instance of `extra`) for every unit-resulting step of one clause."""
  out = []
  for i in heads:
    rest = [_neg(x) for j, x in enumerate(clause) if j != i]

    def join(k, s):
      if k == len(rest):
        out.append((_canonical(_apply(clause[i], s)), _apply(extra, s) if extra is not None else None))
        return
      for f in list(facts.get(rest[k][0], [])):
        counter[0] += 1
        s2 = _unify(rest[k], _rename(f, counter[0]), s)
        if s2 is not None:
          join(k + 1, s2)
    join(0, {})
  return out


def saturate(clauses, depth=0):
  """All signed literals that unit-resulting resolution derives.  {predicate: [literal]}.

  A default clause is read in its head direction only.  Its blocker is the
  literal of its $block: the default gives no conclusion where an earlier
  round derived that blocker instance.  Rounds repeat until the fact set is
  stable.  Literals with more than `depth` nested $do terms are dropped.
  """
  strict, defaults = [], []
  for c in clauses:
    block = [x for x in c if x[0] == "$block"]
    lits = [x for x in c if x[0] != "$block"]
    if block:
      b = block[0][2]
      blocker = _neg(b[1]) if b[0] == "$not" else b
      head = _neg(blocker) if _neg(blocker) in lits else [x for x in lits if not x[0].startswith("-")][0]
      defaults.append((lits, lits.index(head), blocker))
    else:
      strict.append(lits)

  def run(blocked):
    facts, counter = {}, [0]
    changed = True
    while changed:
      changed = False
      rules = [(c, range(len(c)), None) for c in strict] + [(c, [h], b) for c, h, b in defaults]
      for n, (lits, heads, blocker) in enumerate(rules):
        tag = "c%d" % n
        for d, b in _derive(_rename(lits, tag), facts, heads, counter, _rename(blocker, tag) if blocker else None):
          if _depth(d) > depth or _known(facts, d) or (b is not None and blocked is not None and _known(blocked, b)):
            continue
          facts.setdefault(d[0], []).append(d)
          changed = True
          need(sum(len(v) for v in facts.values()) < 20000, "the test derivation does not end")
    return facts

  # round 0: the strict clauses alone say what is blocked; then repeat until stable
  save, defaults = defaults, []
  blocked = run(None)
  defaults = save
  for i in range(8):
    facts = run(blocked)
    if json.dumps(facts, sort_keys=True) == json.dumps(blocked, sort_keys=True):
      return facts
    blocked = facts
  need(False, "the default rounds of the test derivation do not become stable")


def theory(a, qa=None):
  """The clauses of a snapshot derivation: every source clause and the library's snapshot view at W0, or, for a
  compiled query artifact `qa`, the query's own snapshot view (root, exclusions, knower)."""
  need(a["support"]["status"] == "supported", "the source is %s: %r" % (a["support"]["status"], a["support"]))
  if qa is not None:
    src, libc, ordc = lq.view_records(a, ar._library(), "snapshot", ar._selection(qa), qa["excluded"] or [])
    return [r["clause"] for r in src] + [lib.literals(r["clause"]) for r in libc] + [r["clause"] for r in ordc]
  restricted = sorted(a["restrictions"]["constructors"])
  return [r["clause"] for r in a["clauses"]] + [lib.literals(r["clause"]) for r in ar.library_view(a, "snapshot", restricted)]


def holds(facts, lit):
  return any(_unify(_rename(f, "q"), lit, {}) is not None for f in facts.get(lit[0], []))


def at(s):
  """A context term with the situation `s` in the world slot and every other slot open."""
  return ["$ctxt", "?:any_t", s, "?:any_l", "?:any_k"]


def executable(a, action, facts=None, root="W0"):
  """Yes | No | Unknown | contested, for a ground action at the planning root `root` (W0)."""
  facts = facts if facts is not None else saturate(theory(a))
  term = sit._term(action, set())
  yes = holds(facts, ["poss", term, at(root)])
  no = holds(facts, ["-poss", term, at(root)])
  return "contested" if yes and no else "Yes" if yes else "No" if no else "Unknown"


# ---------------------------------------------------------------------------
# gold


def _check_matches(p, rec):
  if rec["role"] != "restriction_check" or p.get("unit") not in (None, rec["unit"]):
    return False
  if "constructor" in p and p["constructor"] != rec["constructor"]:
    return False
  head = [x for x in rec["clause"] if x[0].startswith(sit.CHECK_PREFIX)]
  if len(head) != 1:
    return False
  binding = {}
  if "pattern" in p and not cav.term_matches(p["pattern"], head[0][1], binding):
    return False
  rest = [x for x in rec["clause"] if x is not head[0]]
  for c in p.get("condition", []):
    hit = [x for x in rest if cav.literal_matches(c, x, dict(binding), negate=True)]
    if not hit:
      return False
    cav.literal_matches(c, hit[0], binding, negate=True)
  return True


def _hooks(a, p):
  return [r for r in a["restriction_clauses"] if r["role"] == "hook" and p.get("constructor") in (None, r["constructor"])]


def check_gold():
  counts = {"restriction_check": 0, "hook": 0, "path_coverage": 0, "necessity_restriction": 0, "forbidden": 0}
  units = answers = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    w = case["case"]
    a = cav.gold_source(case)
    recs = cav.records_of(a)
    L = ar._library()
    for g in case["units"]:
      u = [x for x in a["units"] if x["id"] == g["id"]][0]
      if u["form"] == rs.FORM and "executable" in json.dumps(g["stage2"]):
        units += 1
        want = g.get("compile")
        if want == "supported":
          need(u["status"] == "supported" and u["clauses"], "%s/%s: a supported restriction has no clause: %r" % (w, g["id"], u["diagnostics"]))
          need(not sit.free_compiler_variables(u["situated"]) and not sit.free_source_variables(u["situated"]),
               "%s/%s: situated view" % (w, g["id"]))
        elif isinstance(want, dict):
          hit = [d for d in u["diagnostics"] if d.get("reason") == want["unsupported"]]
          need(hit and u["status"] == "unsupported" and not u["clauses"], "%s/%s: expected %s" % (w, g["id"], want))
          need("detail" not in want or any(d.get("detail") == want["detail"] for d in hit),
               "%s/%s: detail %s, got %r" % (w, g["id"], want.get("detail"), hit))
      cl = g.get("clauses") or {}
      for p in cl.get("must_have", []):
        role = p.get("role")
        if role == "restriction_check":
          need(any(_check_matches(p, r) for r in recs), "%s/%s: no check matches %s" % (w, g["id"], json.dumps(p)))
        elif role == "hook":
          hit = [r for r in _hooks(a, p) if sorted(r["units"]) == sorted(p["requires"])]
          need(len(hit) == 1 and len(_hooks(a, p)) == 1, "%s/%s: one hook of %s requiring %s" % (w, g["id"], p["constructor"], p["requires"]))
          names = [x[0][1:] for x in hit[0]["clause"] if x[0].startswith("-")]
          need(sorted(names) == sorted(hit[0]["requires"]) and len(names) >= len(p["requires"]),
               "%s/%s: the hook body is its checks" % (w, g["id"]))
        elif role == "path_coverage":
          rows = [r for r in a["restrictions"]["paths"] if r["constructor"] == p["constructor"]]
          need(rows and all(r["conjoined"] and r["hook_written"] and sorted(r["units"]) == sorted(p["requires"]) for r in rows),
               "%s/%s: path coverage of %s: %r" % (w, g["id"], p["constructor"], rows))
          view = ar.library_view(a, "discovery", sorted(a["restrictions"]["constructors"]))
          for r in view:
            ls = lib.literals(r["clause"])
            head = lib.head(r["clause"], "poss")
            if head is not None and head[1][0] == p["constructor"]:
              need(any(x[0] == "-" + lib.hook_name(p["constructor"]) and x[1:-1] == head[1:-1] for x in ls),
                   "%s: path %s lacks the hook" % (w, r["name"]))
            need(not (r["role"] == "hook_default" and ls[0][0] == lib.hook_name(p["constructor"])),
                 "%s: the default hook of a restricted constructor is in the view" % w)
        elif role == "necessity_restriction" and p.get("unit") != "library":
          need(any(cav.record_matches(p, r) for r in recs), "%s/%s: no necessity matches %s" % (w, g["id"], json.dumps(p)))
        else:
          continue
        counts[role] += 1
      for p in cl.get("must_not_have", []):
        role = p.get("role")
        if role == "restriction_check":
          need(not any(_check_matches(p, r) for r in recs), "%s/%s: forbidden check" % (w, g["id"]))
        elif role == "hook":
          need(not [r for r in _hooks(a, p) if set(p.get("requires", [])) <= set(r["units"])], "%s/%s: forbidden hook" % (w, g["id"]))
        elif role == "necessity_restriction" and p.get("unit") != "library":
          need(not any(cav.record_matches(p, r) for r in recs), "%s/%s: forbidden necessity %s" % (w, g["id"], json.dumps(p)))
        else:
          continue
        counts["forbidden"] += 1
    # the gold answers of ground executable questions, by derivation in each query's snapshot view
    if a["support"]["status"] != "supported" or not a["restrictions"]["constructors"]:
      continue
    for q in case["queries"]:
      body = q["stage2"][2] if q.get("stage2") else None
      e = q.get("expect") or {}
      if not (body and body[0] == "question" and body[1][0] == "executable" and "answer" in e):
        continue
      if any(la.is_var(t) for t in body[1][1][1:]):
        continue
      qa = ar.compile_query(q["stage2"], a, None, **fm.selection(q))
      facts = saturate(theory(a, qa))
      got = executable(a, body[1][1], facts, lq.root_situation(ar._selection(qa)))
      need(got == e["answer"], "%s/%s: derived %s, gold %s" % (w, q["id"], got, e["answer"]))
      answers += 1
  need(min(counts.values()) > 0 and answers > 0, "a gold pattern kind was never checked: %r" % counts)
  print("  gold: %d restriction units; patterns checked: %s; %d gold executable answers derived in their query views"
        % (units, ", ".join("%d %s" % (v, k) for k, v in sorted(counts.items())), answers))


# ---------------------------------------------------------------------------

ENTS = {"hand one 1": "hand", "hand two 2": "hand", "a 3": "block", "b 4": "block", "table 5": "table",
        "Ann 6": "person", "Bob 7": "person", "Tallinn 8": "place", "Helsinki 9": "place", "Tartu 10": "place",
        "ticket 11": "artifact", "egg 12": "food"}
H1, H2, A, B, T = "hand one 1", "hand two 2", "a 3", "b 4", "table 5"
RED = lambda x: ["has property", "red", x]
DRY = lambda x: ["has property", "dry", x]
NOT = lambda f: ["not", f]
EXE = lambda act: ["executable", act]
ONLY_RED = ["forall", "H", ["forall", "X", ["implies", EXE(["take", "H", "X"]), RED("X")]]]
H1_DRY = ["forall", "X", ["implies", EXE(["take", H1, "X"]), DRY("X")]]
BLOCKS = [["and", ["isa", "hand", H1], ["isa", "hand", H2], ["isa", "block", A], ["isa", "block", B], ["isa", "table", T]],
          ["and", ["is rel2", "on", A, T], ["has property", "clear_top", A], ["has property", "empty", H1],
           ["has property", "empty", H2]]]


def compiled(*units):
  pkgs = [cav.S(u, "S%d" % (i + 1)) if u[0] != "@id" else u for i, u in enumerate(units)]
  return ar.compile_source(None, pkgs, la.PROFILE, None, ENTS)


def unit(a, i):
  return [u for u in a["units"] if u["id"] == i][0]


def check_requirement():
  got = {}
  for name, extra in (("true", [RED(A)]), ("false", [NOT(RED(A))]), ("unknown", []), ("both", [RED(A), NOT(RED(A))])):
    a = compiled(*(BLOCKS + [ONLY_RED] + extra))
    facts = saturate(theory(a))
    got[name] = executable(a, ["take", H1, A], facts)
    red = ["has property", "red", "#:" + A, at("W0")]
    if name == "unknown":
      need(not holds(facts, red) and not holds(facts, _neg(red)), "an unknown requirement was derived from executability")
    # encoding v2: a restriction gives -poss through its necessity clause and never the denial marker
    need(not holds(facts, [lib.MARKER, ["take", "#:" + H1, "#:" + A], at("W0")]), "%s: a restriction derived the denial marker" % name)
  need(got == {"true": "Yes", "false": "No", "unknown": "Unknown", "both": "contested"}, "one requirement: %r" % got)
  # a negative requirement, and a conjunction: explicit failure of one conjunct is enough
  heavy = ["forall", "X", ["implies", EXE(["take", H1, "X"]), ["and", RED("X"), NOT(["has property", "heavy", "X"])]]]
  res = [executable(compiled(*(BLOCKS + [heavy] + extra)), ["take", H1, A])
         for extra in ([RED(A), NOT(["has property", "heavy", A])], [RED(A)], [RED(A), ["has property", "heavy", A]],
                       [["has property", "heavy", A]], [NOT(RED(A))])]
  need(res == ["Yes", "Unknown", "No", "No", "No"], "a conjunctive requirement: %r" % res)
  a = compiled(*(BLOCKS + [heavy]))
  nec = [r["clause"] for r in unit(a, "S3")["clauses"] if r["role"] == "necessity_restriction"]
  need(len(nec) == 2 and all(len(c) == 2 for c in nec), "one necessity clause per required literal: %r" % nec)
  print("  requirement: true Yes, false No, unknown Unknown, both contested; a conjunction fails on one explicit conjunct; "
        "an unknown requirement is not derived from executability")


def check_conjunction():
  base = BLOCKS + [ONLY_RED, H1_DRY]
  a = compiled(*(base + [RED(A), NOT(DRY(A))]))
  need([executable(a, ["take", h, A]) for h in (H1, H2)] == ["No", "Yes"], "hand one needs red and dry; hand two needs red")
  hooks = [r for r in a["restriction_clauses"] if r["role"] == "hook"]
  need(len(hooks) == 1 and hooks[0]["requires"] == ["restriction_1_S3", "restriction_1_S4"] and hooks[0]["units"] == ["S3", "S4"],
       "one hook conjoins both checks: %r" % hooks)
  need(cav.erase(hooks[0]["clause"]) == [["-restriction_1_S3", ["take", "?:v_P1", "?:v_P2"], "?:Sit", "?:Ctx"],
                              ["-restriction_1_S4", ["take", "?:v_P1", "?:v_P2"], "?:Sit", "?:Ctx"],
                              ["ok_take", ["take", "?:v_P1", "?:v_P2"], "?:Sit", "?:Ctx"]], "the hook clause: %r" % hooks[0]["clause"])
  a = compiled(*(base + [NOT(RED(A)), DRY(A)]))
  need([executable(a, ["take", h, A]) for h in (H1, H2)] == ["No", "No"], "the general restriction holds for hand two")
  a = compiled(*(base + [RED(A), DRY(A)]))
  need([executable(a, ["take", h, A]) for h in (H1, H2)] == ["Yes", "Yes"], "red and dry")
  # an unknown hand: no differ fact, so the nonmatch is unknown and nothing is permitted or refuted
  anon = ["exists", "H", ["and", ["isa", "hand", "H"], ["has property", "empty", "H"]]]
  a = compiled(*(base + [RED(A), NOT(DRY(A)), anon]))
  need(executable(a, ["take", "sk_H", A]) == "Unknown", "an anonymous hand: %s" % executable(a, ["take", "sk_H", A]))
  # a class guard: a stated non-member is outside; an undeclared one is unknown
  guard = ["forall", "H", ["forall", "X", ["implies", ["and", ["isa", "hand", "H"], EXE(["take", "H", "X"])], RED("X")]]]
  robo = [["can", "Ann 6", ["take", "Ann 6", A]], ["has property", "empty", "Ann 6"]]
  a = compiled(*(BLOCKS + [guard, NOT(RED(A))] + robo))
  need([executable(a, ["take", x, A]) for x in (H1, "Ann 6")] == ["No", "Unknown"], "class guard, class not stated")
  a = compiled(*(BLOCKS + [guard, NOT(RED(A))] + robo + [NOT(["isa", "hand", "Ann 6"])]))
  need(executable(a, ["take", "Ann 6", A]) == "Yes", "class guard, stated non-member")
  g = [cav.erase(r["clause"]) for r in unit(a, "S3")["clauses"]]
  need([["isa", "hand", "?:v_P1"], ["restriction_1_S3", ["take", "?:v_P1", "?:v_P2"], "?:Sit", "?:Ctx"]] in g
       and [["-has property", "red", "?:v_X", "?:Sit", "?:Ctx"], ["restriction_1_S3", ["take", "?:v_H", "?:v_X"], "?:Sit", "?:Ctx"]] in g
       and [["-isa", "hand", "?:v_H"], ["has property", "red", "?:v_X", "?:Sit", "?:Ctx"],
            ["-poss", ["take", "?:v_H", "?:v_X"], "?:Sit", "?:Ctx"]] in g and len(g) == 3, "class-guard clauses: %r" % g)
  # check names are injective: the second restriction of unit R and the first of unit R_2 are two checks
  clean = lambda x: ["has property", "clean", x]
  two = cav.S(["forall", "X", ["and", ["implies", EXE(["take", H1, "X"]), RED("X")], ["implies", EXE(["take", H1, "X"]), DRY("X")]]], "R")
  third = cav.S(["forall", "X", ["implies", EXE(["take", H1, "X"]), clean("X")]], "R_2")
  world = [cav.S(f, "W%d" % i) for i, f in enumerate(BLOCKS + [RED(A), DRY(A)])]
  a = compiled(*(world + [two, third]))
  hook = [r for r in a["restriction_clauses"] if r["role"] == "hook"]
  need(len(hook) == 1 and hook[0]["requires"] == ["restriction_1_R", "restriction_2_R", "restriction_1_R_2"]
       and len(hook[0]["clause"]) == 4, "three restrictions, three checks: %r" % hook)
  need(executable(a, ["take", H1, A]) == "Unknown", "red and dry known, clean unknown: %s" % executable(a, ["take", H1, A]))
  a = compiled(*(world + [two, third, cav.S(clean(A), "W9")]))
  need(executable(a, ["take", H1, A]) == "Yes", "all three conditions hold")
  a = compiled(*(world + [two, third, cav.S(NOT(clean(A)), "W9")]))
  need(executable(a, ["take", H1, A]) == "No", "clean is false")
  seen = [rs.check_name(u, k) for u in ("R", "R_2", "2_R", "R_2_2", "1") for k in range(12)]
  need(len(seen) == len(set(seen)), "check names collide")
  try:
    rs.hooks([{"id": "A", "form": rs.FORM, "status": "supported", "action_terms": [["take", "H", "X"]]},
              {"id": "B", "form": rs.FORM, "status": "supported", "action_terms": [["take", "H", "X"]]}],
             {"A": [("restriction_x", "take")], "B": [("restriction_x", "take")]}, lambda u: None)
    need(False, "a shared check name reached a hook")
  except ValueError:
    pass
  print("  conjunction: one hook per constructor conjoins every check; an actor-specific restriction keeps the general one; "
        "an unknown hand and an undeclared class stay Unknown; a stated non-member is outside")


def check_put_on():
  world = [["and", ["isa", "hand", H1], ["isa", "block", A], ["isa", "block", B], ["isa", "table", T]],
           ["and", ["is rel2", "holding", H1, A], ["is rel2", "on", B, T]]]
  law = ["forall", "X", ["forall", "Y", ["implies", EXE(["put_on", H1, "X", "Y"]), DRY("X")]]]
  rows = {}
  for name, extra in (("dry", [DRY(A), ["has property", "clear_top", B]]),
                      ("wet", [NOT(DRY(A)), ["has property", "clear_top", B]]),
                      ("occupied", [DRY(A), NOT(["has property", "clear_top", B])]),
                      ("unknown", [["has property", "clear_top", B]])):
    a = compiled(*(world + [law] + extra))
    rows[name] = [executable(a, ["put_on", H1, A, y]) for y in (B, T)]
  need(rows == {"dry": ["Yes", "Yes"], "wet": ["No", "No"], "occupied": ["Unknown", "Yes"], "unknown": ["Unknown", "Unknown"]},
       "put_on branches: %r" % rows)
  paths = [r["path"] for r in a["restrictions"]["paths"]]
  need(paths == ["poss_put_on_hand_block", "poss_put_on_hand_surface", "tpl_put_on_block", "tpl_put_on_surface"]
       and all(r["conjoined"] for r in a["restrictions"]["paths"]),
       "both put_on paths, defaults and templates, are in the coverage table: %r" % paths)
  print("  put_on: one restriction on the block path and the surface path; a failed block path does not refute the surface path")


def check_movement():
  go = lambda t, m: ["move", "Ann 6", "Tallinn 8", t, m]
  world = [["and", ["isa", "person", "Ann 6"], ["isa", "person", "Bob 7"], ["is rel2", "located_at", "Ann 6", "Tallinn 8"],
            ["is rel2", "located_at", "Bob 7", "Tallinn 8"], ["connected", "Tallinn 8", "Helsinki 9", "ship"]],
           ["can", "Ann 6", go("Tartu 10", "bus")]]
  law = ["forall", "F", ["forall", "T", ["forall", "M", ["implies", EXE(["move", "Ann 6", "F", "T", "M"]), ["have", "Ann 6", "ticket 11"]]]]]
  rows = {}
  for name, extra in (("ticket", [["have", "Ann 6", "ticket 11"]]), ("none", []), ("denied", [NOT(["have", "Ann 6", "ticket 11"])])):
    a = compiled(*(world + [law] + extra))
    rows[name] = [executable(a, go("Helsinki 9", "ship")), executable(a, go("Tartu 10", "bus")),
                  executable(a, ["move", "Bob 7", "Tallinn 8", "Helsinki 9", "ship"])]
  need(rows == {"ticket": ["Yes", "Yes", "Yes"], "none": ["Unknown", "Unknown", "Yes"], "denied": ["No", "No", "Yes"]},
       "public and stated-endpoint movement under one restriction: %r" % rows)
  paths = [r["path"] for r in a["restrictions"]["paths"]]
  need(paths == ["poss_move_person", "tpl_move_public", "tpl_move_stated"], "every movement path is in the coverage table: %r" % paths)
  stated = [cav.erase(r["clause"]) for r in unit(a, "S2")["clauses"] if r.get("template") == "tpl_move_stated"]
  need(len(stated) == 1 and ["-ok_move", ["move", "#:Ann 6", "#:Tallinn 8", "#:Tartu 10", "bus"], "?:Sit", "?:Ctx"] in stated[0],
       "the stated-endpoint path of S2 holds the move hook: %r" % stated)
  # a restriction on one destination leaves another destination alone, by differ
  to = ["forall", "F", ["forall", "M", ["implies", EXE(["move", "Ann 6", "F", "Helsinki 9", "M"]), ["have", "Ann 6", "ticket 11"]]]]
  a = compiled(*(world + [to]))
  need([executable(a, go("Helsinki 9", "ship")), executable(a, go("Tartu 10", "bus"))] == ["Unknown", "Yes"], "a restricted destination")
  non = [r["branch"] for r in unit(a, "S3")["clauses"]]
  need(non == ["match", "nonmatch: actor is not Ann 6", "nonmatch: to is not Helsinki 9", "necessity"], "branches: %r" % non)
  print("  movement: the public path and the stated-endpoint path need the same check; another actor and another destination "
        "are outside by differ")


def check_no_bypass():
  n = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    a = cav.gold_source(case)
    for r in cav.records_of(a) + a["restriction_clauses"]:
      if r.get("pass") != rs.PASS:
        continue
      n += 1
      pos = [x for x in r["clause"] if not x[0].startswith("-")]
      need(not any(x[0] == "poss" or x[0] == "can" for x in pos), "%s: a restriction clause concludes %r" % (case["case"], pos))
      if r["role"] in ("restriction_check", "hook"):
        need(not any(x[0].lstrip("-") in ("poss", "can") for x in r["clause"]), "%s: a check reads poss or can: %r" % (case["case"], r["clause"]))
        need(len(pos) >= 1 and sum(1 for x in pos if x[0].startswith((sit.CHECK_PREFIX, sit.HOOK_PREFIX))) == 1
             and all(x[0].startswith((sit.CHECK_PREFIX, sit.HOOK_PREFIX)) or x[0] in la.STATIC or x[0] in la.FLUENTS for x in pos),
             "%s: %r" % (case["case"], r["clause"]))
      if r["role"] == "necessity_restriction":
        need([x[0] for x in r["clause"]].count("-poss") == 1, "%s: a necessity concludes one -poss" % case["case"])
  need(n > 0, "no restriction clause was seen")
  print("  no bypass: %d restriction clauses; none concludes poss or can; a check concludes its own predicate only" % n)


def check_unsupported():
  take = lambda h, x: EXE(["take", h, x])
  cases = [
    ("state_guard", ["forall", "X", ["implies", ["and", ["has property", "wet", "X"], take(H1, "X")], RED("X")]]),
    ("free_variable", ["forall", "X", ["forall", "Y", ["implies", take(H1, "X"), ["is rel2", "on", "X", "Y"]]]]),
    ("repeated_variable", ["forall", "M", ["implies", EXE(["move", "M", "Tallinn 8", "Helsinki 9", "M"]), ["have", "M", "ticket 11"]]]),
    ("action_slot_constraint", ["forall", "H", ["forall", "X", ["implies", take("H", "X"), ["=", "H", H1]]]]),
  ]
  for detail, f in cases:
    a = compiled(*(BLOCKS + [f]))
    u = unit(a, "S3")
    hit = [d for d in u["diagnostics"] if d.get("reason") == "unsupported_restriction_scope"]
    need(hit and hit[0].get("detail") == detail and u["status"] == "unsupported" and not u["clauses"],
         "%s: %r" % (detail, u["diagnostics"]))
    need(u["stage2"][2][2] == f, "%s: the source formula is kept" % detail)
    rows = a["restrictions"]["constructors"]
    need(a["clauses"] is None and not a["restriction_clauses"] and len(rows) == 1
         and list(rows.values())[0] == {"units": ["S3"], "checks": [], "hook": False, "withheld_for": ["S3"]},
         "%s: a partially constrained theory: %r" % (detail, rows))
  # a repeated variable over two entity slots is supported, by differ
  same = ["forall", "X", ["implies", EXE(["put_on", H1, "X", "X"]), RED("X")]]
  a = compiled(*(BLOCKS + [same]))
  br = [r["branch"] for r in unit(a, "S3")["clauses"]]
  need(unit(a, "S3")["status"] == "supported" and "nonmatch: slots object and support differ" in br, "repeated entity variable: %r" % br)
  # can -> Q is not an operational restriction
  a = compiled(*(BLOCKS + [["forall", "X", ["implies", ["can", H1, ["take", H1, "X"]], RED("X")]]]))
  need(a["support"]["reasons"] == ["unsupported_capability_restriction"] and not unit(a, "S3")["clauses"]
       and not a["restriction_clauses"], "can -> Q: %r" % a["support"])
  # an uncertain restriction
  a = compiled(*(BLOCKS + [cav.S(H1_DRY, "S3", 0.8)]))
  need(a["support"]["reasons"] == ["unsupported_confidence_form"] and not unit(a, "S3")["clauses"], "an uncertain restriction: %r" % a["support"])
  # a lexical constant has no nonmatch branch and the note says so
  a = compiled(["isa", "person", "Ann 6"],
               ["forall", "A", ["forall", "T", ["implies", EXE(["change", "A", "egg 12", "open", "T"]), NOT(["has property", "locked", "egg 12"])]]])
  u = unit(a, "S2")
  need(u["status"] == "supported" and "value other than open" in (u["compile_note"] or "")
       and [r["branch"] for r in u["clauses"]] == ["match", "nonmatch: object is not egg 12", "necessity"], "a lexical slot: %r" % u["compile_note"])
  print("  unsupported: state guard, free variable, a variable repeated in a lexical slot, slot equality, can -> Q and an uncertain restriction emit no clause and "
        "no hook; a repeated entity variable and a lexical constant are compiled as documented")


def check_bookkeeping():
  f = BLOCKS + [ONLY_RED, H1_DRY, RED(A)]
  before = copy.deepcopy(f)
  a, b = compiled(*f), compiled(*f)
  need(ar.dumps(a) == ar.dumps(b) and f == before, "two runs differ or the input changed")
  need(rs.PASS in a["passes"] and a["pending_passes"] == [] and ar.source_outcome(a)["outcome"] == "source_compiled"
       and ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED,
       "pass bookkeeping: %r" % a["pending_passes"])
  ar.check_artifact(a, ar.SOURCE)
  none = compiled(*BLOCKS)
  need(none["restriction_clauses"] == [] and none["restrictions"] == {"constructors": {}, "paths": []}
       and len(ar.library_view(none, "snapshot")) == len(ar.library_view(a, "snapshot", ["take"])) + 1,
       "a source without restrictions keeps every default hook")
  need(executable(none, ["take", H1, A]) == "Yes", "the default hook")
  print("  bookkeeping: deterministic; the pass is recorded; a source without restrictions has no hook clause and keeps the default hooks")


def run():
  check_gold()
  check_requirement()
  check_conjunction()
  check_put_on()
  check_movement()
  check_no_bypass()
  check_unsupported()
  check_bookkeeping()


if __name__ == "__main__":
  run()
