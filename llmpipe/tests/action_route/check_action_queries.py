"""WP09 unit checks: query views, obligations, seeds, per-query backend requirements.

No model, no GK.  Clause inspection of the query artifacts and of the prover
inputs `query_input` builds, plus the test-only derivation of
`check_action_restrictions` run on those inputs.  The derivation is a test
tool; it says nothing about what GK proves.

  gold          every supported gold query: view, backend requirements and
                the backend refusal; the pinned clause, obligation, view-role
                and hash expectations
  snapshot      question and ask bind the root (W0) everywhere; the view holds no
                successor clause, no free situation and no seed
  discovery     one shared goal situation, the reachability requirement, the
                seed of every bound form, reported witnesses, no padding
  verify        the root-based chain, paired and distinct obligations with
                prefix numbers, nothing asserted, the empty sequence
  reuse         four queries leave the source hashes unchanged; view and
                obligation hashes; the rebuilt input is checked
  backend       the horizon rule of negative persistence, the c01 / c02
                contrast, a validated backend, shared-source confidence
  derivation    the prover inputs give the gold answers and plans under the
                test-only derivation
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
import check_action_restrictions as crs
import check_action_validation as cv
import fixture_materialize as fm
import lc_action as la
import lc_action_library as lib
import lc_action_query as lq
import lc_action_situate as sit

need = cav.need
NOT = lambda f: ["not", f]
Q = lambda p, i="Q1": ["@id", i, p]
T = lambda x: sit._term(x, set())


def lits_of(obj):
  logic = obj["@logic"]
  return logic if logic and isinstance(logic[0], list) else [logic]


def query_objects(qa):
  """Every clause object the query itself adds: seed, definitions, questions."""
  out = [qa["seed"]] if qa["seed"] else []
  for o in qa["obligations"] + ([{"positive": qa["joint_positive"], "negative": None}] if qa["joint_positive"] else []):
    for pol in ("positive", "negative"):
      if o[pol]:
        out.extend(o[pol]["clauses"])
        out.append(o[pol]["question"])
  return out


def query_literals(qa):
  out = []
  for o in query_objects(qa):
    out.extend(lits_of(o) if "@logic" in o else [o["@question"]])
  return out


def situations(literals):
  return [sit.situation_of(x) for x in literals if sit.bears_situation(x[0].lstrip("-"))]


def qat(s, sel=None):
  """The query context term with the situation `s` in its world slot."""
  c = lq.query_context(sel)
  c[2] = s
  return c


def contains(t, what):
  return t == what or (isinstance(t, list) and any(contains(x, what) for x in t))


def supported_gold():
  for case in fm.load_all():
    if cv.profile_name(case["profile"]) != la.PROFILE or not case["units"]:
      continue
    a = cv.gold_source(case)
    if a["support"]["status"] != "supported":
      continue
    for q in case["queries"]:
      if q.get("stage2"):
        yield case, a, q, ar.compile_query(q["stage2"], a, cv.gold_limits(q), **fm.selection(q))


# ---------------------------------------------------------------------------
# gold

ROLE_NAMES = {"initial_fact": "initial_fact", "static": "static", "standing_law@root": "standing_law",
              "availability@root": "availability", "restriction_check@root": "restriction_check", "hook@root": "hook",
              "necessity@root": "necessity_restriction", "distinct": "distinct"}


def check_gold():
  n = refused = pinned = 0
  for case, a, q, qa in supported_gold():
    w = "%s/%s" % (case["case"], q["id"])
    e = q["expect"]
    out = (qa["outcome"] or {}).get("outcome")
    if out in ("translation_invalid", "unsupported_translation", "insufficient_search_allowance"):
      need(qa["obligations"] is None and qa["selected_clauses"] is None, "%s: a decided query has no view" % w)
      continue
    n += 1
    mine = sorted(r["capability"] for r in qa["backend_requirements"])
    need(mine == sorted(q["backend"]), "%s: backend requirements %s, gold %s" % (w, mine, q["backend"]))
    if e.get("outcome") == "unsupported_backend_requirement":
      refused += 1
      need(out == "unsupported_backend_requirement" and qa["outcome"]["reason"] == e["reason"]
           and qa["obligations"] is None and qa["view_hash"] is None, "%s: gold refusal, mine %r" % (w, qa["outcome"]))
      continue
    need(out is None and qa["pending_passes"] == [] and qa["passes"] == [lq.PASS], "%s: outcome %r" % (w, qa["outcome"]))
    need(qa["selected_clauses"]["view"] == lq.selected_view(qa["query"]["kind"], qa["query"]["sequence"]), "%s: view" % w)
    ql = query_literals(qa)
    for p in (e.get("clauses") or {}).get("must_have", []):
      pinned += 1
      if p["role"] == "query":
        want = T(p["lit"])
        need(any(x[:len(want)] == want and sit.situation_class(x) == p["situation"] for x in ql),
             "%s: no query literal %r at %s" % (w, want, p["situation"]))
    for p in (e.get("clauses") or {}).get("must_not_have", []):
      pinned += 1
      if p.get("role") == "seed":
        need(qa["seed"] is None and not any(x[0].lstrip("-") == "reachable" for x in ql), "%s: a seed in an immediate question" % w)
      elif p.get("situation") == "free":
        root = lq.root_situation(ar._selection(qa))
        need(all(s == root for s in situations(ql)), "%s: a free situation in an immediate question" % w)
    if "obligations" in e:
      pinned += 1
      need(len(qa["obligations"]) == len(e["obligations"]), "%s: %d obligations, gold %d" % (w, len(qa["obligations"]), len(e["obligations"])))
      for o, g in zip(qa["obligations"], e["obligations"]):
        need(o["text"].split("(")[0] == g.split("(")[0] and o["text"].rsplit(",", 1)[1] == g.rsplit(",", 1)[1],
             "%s: obligation %s, gold %s" % (w, o["text"], g))
    src, libc, ordc = lq.view_records(a, ar._library(), qa["selected_clauses"]["view"], ar._selection(qa), qa["excluded"] or [])
    roles = {r["role"] for r in src} | {r["role"] for r in libc}
    if "view_roles_excluded" in e:
      pinned += 1
      for g in e["view_roles_excluded"]:
        name = {"reach_step": "reachability", "seed": None}.get(g, g)
        need(name not in roles, "%s: the view holds role %s" % (w, g))
      need(qa["seed"] is None, "%s: a snapshot has no seed" % w)
    for g in e.get("view_roles_included", []):
      if g in ROLE_NAMES:      # the gold lists the roles a snapshot keeps; a source need not have every one of them
        pinned += 1
        have = [r for r in a["clauses"] if r["role"] == ROLE_NAMES[g]]
        need(len([r for r in src if r["role"] == ROLE_NAMES[g]]) == len(have), "%s: the view drops clauses of role %s" % (w, g))
        need(not g.endswith("@root") or all(s == qa["planning_root"] for r in src if r["role"] == ROLE_NAMES[g]
                                            for s in situations(r["clause"])),
             "%s: role %s is not bound to the root" % (w, g))
    if e.get("view_roles_included") == ["everything except seed and reach_step"]:
      pinned += 1
      need(len(src) == len(a["clauses"]) and "reachability" not in roles and qa["seed"] is None
           and {"effect", "marker", "frame"} <= roles, "%s: the verify view" % w)
    if e.get("view_hash") == "recorded":
      pinned += 1
      need(isinstance(qa["view_hash"], str) and len(qa["view_hash"]) == 64, "%s: the view hash is recorded" % w)
    if "source_hash_after" in e:
      pinned += 1
      need(qa["source"]["source_hash"] == a["hashes"]["source"] == ar.source_hashes(a)["source"], "%s: source hash" % w)
  print("  gold: %d supported queries agree on view and backend requirements; %d stop with the backend refusal; "
        "%d pinned clause, obligation, role and hash expectations hold" % (n, refused, pinned))


# ---------------------------------------------------------------------------
# small sources

ENTS = {"Ann 1": "person", "Haapsalu 2": "place", "Tallinn 3": "place", "Helsinki 4": "place", "cup 5": "artifact",
        "hand 6": "hand", "a 7": "block", "b 8": "block", "table 9": "table", "robot 10": "artifact",
        "chest 11": "artifact", "lock 12": "artifact", "egg 13": "food"}
AT = lambda who, where: ["is rel2", "located_at", who, where]
BUS = ["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"]
SHIP = ["move", "Ann 1", "Tallinn 3", "Helsinki 4", "ship"]
POLISH = ["change", "Ann 1", "cup 5", "polished", "unspecified"]
GRANT = ["change", "Ann 1", "Ann 1", "licensed", "unspecified"]
LICENSED = ["has property", "licensed", "Ann 1"]
DENIAL = ["forall", "X", ["forall", "F", ["forall", "T", ["implies", ["and", ["isa", "person", "X"], NOT(["has property", "licensed", "X"])],
                                                          NOT(["can", "X", ["move", "X", "F", "T", "bus"]])]]]]
TRAVEL = [["isa", "person", "Ann 1"], AT("Ann 1", "Haapsalu 2"), ["connected", "Haapsalu 2", "Tallinn 3", "bus"],
          ["connected", "Tallinn 3", "Helsinki 4", "ship"]]
TAKE, PUT = ["take", "hand 6", "a 7"], ["put_on", "hand 6", "a 7", "b 8"]
BLOCKS = [["and", ["isa", "hand", "hand 6"], ["isa", "block", "a 7"], ["isa", "block", "b 8"], ["isa", "table", "table 9"]],
          ["and", ["is rel2", "on", "a 7", "table 9"], ["is rel2", "on", "b 8", "table 9"], ["has property", "clear_top", "a 7"],
           ["has property", "clear_top", "b 8"], ["has property", "empty", "hand 6"]]]


def compiled(*units):
  pkgs = [cav.S(u, "S%d" % (i + 1)) if u[0] != "@id" else u for i, u in enumerate(units)]
  a = ar.compile_source(None, pkgs, la.PROFILE, None, ENTS)
  need(a["support"]["status"] == "supported", "test source: %r" % a["support"])
  return a


def outcome(qa):
  return (qa["outcome"] or {}).get("outcome")


# ---------------------------------------------------------------------------
# snapshot


def check_snapshot():
  a = compiled(*(TRAVEL + [["state_law", ["forall", "X", ["implies", ["has property", "washed", "X"], ["has property", "clean", "X"]]]],
                           ["implies", ["has property", "washed", "cup 5"], ["after", POLISH, ["has property", "shiny", "cup 5"]]]]))
  forms = [["question", ["and", ["executable", BUS], AT("Ann 1", "Haapsalu 2")]], ["question", ["executable", BUS]],
           ["question", ["has property", "clean", "cup 5"]],
           ["question", ["forall", "X", ["implies", ["isa", "place", "X"], NOT(AT("Ann 1", "X"))]]],
           ["question", ["implies", ["has property", "washed", "cup 5"], ["executable", POLISH]]],
           ["question", ["exists", "X", ["and", ["isa", "place", "X"], AT("Ann 1", "X")]]],
           ["ask", "X", AT("Ann 1", "X")], ["verify", [], AT("Ann 1", "Haapsalu 2")]]
  for p in forms:
    qa = ar.compile_query(Q(p), a)
    need(outcome(qa) is None and qa["selected_clauses"]["view"] == "snapshot" and qa["seed"] is None, "%r: %r" % (p, qa["outcome"]))
    ql = query_literals(qa)
    need(situations(ql) and all(s == "W0" for s in situations(ql)), "%r: a situation other than the root W0: %r" % (p, situations(ql)))
    need(not any(x[0].lstrip("-") == "reachable" for x in ql), "%r: reachability in an immediate question" % (p,))
    inp = ar.query_input(a, qa, qa["obligations"][0]["id"], "positive")
    body = [x for o in inp if "@logic" in o for x in lits_of(o)]
    need(not any(contains(x, sit.SIT) or contains(x, lib.SITUATION) or contains(x, sit.DO) for x in body),
         "%r: the snapshot input holds a free situation or a successor" % (p,))
    need(not any(x[0].lstrip("-").startswith("changed_") or x[0].lstrip("-") in ("reachable", "derived_property") for x in body),
         "%r: the snapshot input holds a marker, a seed or a no-inertia fact" % (p,))
  qa = ar.compile_query(Q(forms[1]), a)
  o = qa["obligations"][0]
  need(o["positive"]["question"]["@question"] == ["poss", T(BUS), qat("W0")]
       and o["negative"]["question"]["@question"] == ["-poss", T(BUS), qat("W0")], "executable becomes poss at W0: %r" % o)
  # the negation of a universal: a Skolem constant, never a free variable
  qa = ar.compile_query(Q(forms[3]), a)
  pos = [lits_of(c) for c in qa["obligations"][0]["positive"]["clauses"]]
  neg = [lits_of(c) for c in qa["obligations"][0]["negative"]["clauses"]]
  need(all(any(contains(x, "skq_Q1_X") for x in c) for c in pos) and not any(contains(c, "skq_Q1_X") for c in neg)
       and any(contains(c, "?:v_X") for c in neg), "polarity of a quantified question: %r / %r" % (pos, neg))
  # ask reports its variable and has no negative question
  qa = ar.compile_query(Q(forms[6]), a)
  o = qa["obligations"][0]
  need(o["negative"] is None and o["positive"]["question"] == {"@name": "query:Q1:q:positive", "@question": ["$defq0", "?:v_X"], "@askvars": 1},
       "ask: %r" % o)
  # a double negation is one literal again
  qa = ar.compile_query(Q(["question", NOT(LICENSED)]), a)
  need(qa["obligations"][0]["negative"]["question"]["@question"][0] == "has property"
       and qa["obligations"][0]["positive"]["question"]["@question"][0] == "-has property", "a negative literal question")
  print("  snapshot: %d question forms bind the root W0 in every atom; the input holds no successor, marker, seed or free situation; "
        "a universal question Skolemizes on the positive side only; ask reports its variable" % len(forms))


# ---------------------------------------------------------------------------
# discovery


def check_discovery():
  a = compiled(*TRAVEL)
  goal = AT("Ann 1", "Helsinki 4")
  rows = [(None, None, 4, False, "?:N"), (["steps", "exactly", 2], None, 2, True, "0"), (["steps", "at_most", 2], None, 2, False, "?:N"),
          (["steps", "at_most", 6], None, 6, False, "?:N"), (["steps", "at_most", 6], {"search_cap": 3}, 3, False, "?:N"),
          (["steps", "exactly", 0], None, 0, True, "0"), (None, {"search_cap": 1}, 1, False, "?:N"),
          (["steps", "exactly", 3], {"search_cap": 3}, 3, True, "0")]
  for steps, lim, depth, zero, remaining in rows:
    qa = ar.compile_query(Q(["plan", goal] + ([steps] if steps else [])), a, lim)
    need(outcome(qa) is None and qa["search"]["depth"] == depth and qa["search"]["require_zero_remaining"] == zero, "%r %r: %r" % (steps, lim, qa["search"]))
    need(qa["seed"]["@logic"] == ["reachable", "W0", lq.unary(depth)], "%r %r: seed %r" % (steps, lim, qa["seed"]))
    clause = lits_of(qa["obligations"][0]["positive"]["clauses"][0])
    need(clause[0] == ["-reachable", sit.SIT, remaining], "%r: reachability requirement %r" % (steps, clause[0]))
    need(qa["obligations"][0]["negative"] is None, "a discovery has no negative reachability question")
  need(lq.unary(2) == ["s", ["s", "0"]] and lq.unary(0) == "0", "unary depth")
  qa = ar.compile_query(Q(["plan", goal, ["steps", "exactly", 5]]), a, {"search_cap": 4})
  need(outcome(qa) == "insufficient_search_allowance" and qa["seed"] is None and qa["obligations"] is None,
       "an exact bound above an explicit cap is no shorter question: %r" % qa["outcome"])
  # a conjunctive goal with a shared witness: one situation, one witness variable, both reported
  g = ["exists", "X", ["and", ["isa", "place", "X"], AT("Ann 1", "X"), NOT(AT("cup 5", "X"))]]
  qa = ar.compile_query(Q(["reachable", g]), a)
  o = qa["obligations"][0]
  clause = lits_of(o["positive"]["clauses"][0])
  need(len(o["positive"]["clauses"]) == 1 and set(map(json.dumps, situations(clause))) == {json.dumps(sit.SIT)},
       "one shared goal situation: %r" % clause)
  need(clause[-1] == ["$defq0", sit.SIT, "?:v_X"] and o["positive"]["question"]["@askvars"] == 2 and o["witnesses"] == ["X"]
       and sum(1 for x in clause if contains(x, "?:v_X")) == 4, "the witness is one shared, reported variable: %r" % clause)
  need(["is rel2", "located_at", "#:cup 5", "?:v_X", qat(sit.SIT)] in clause, "a negative goal literal is proved negative: %r" % clause)
  # no padding: the query adds no action term, no poss and no positive reachable but the seed
  for p in (["plan", goal, ["steps", "exactly", 3]], ["reachable", g]):
    qa = ar.compile_query(Q(p), a)
    ql = query_literals(qa)
    need(not any(contains(x, c) for x in ql for c in la.CONSTRUCTORS) and not any(x[0].lstrip("-") == "poss" for x in ql)
         and [x for x in ql if x[0] == "reachable"] == [qa["seed"]["@logic"]], "%r: the query invents an action or a reachable fact" % (p,))
  print("  discovery: %d bound forms give the stated seed and remaining-depth requirement; an exact bound above the cap stops; "
        "a conjunctive goal shares one situation and one reported witness; no action is invented" % len(rows))


# ---------------------------------------------------------------------------
# verify


def check_verify():
  a = compiled(*BLOCKS)
  final = ["and", ["is rel2", "on", "a 7", "b 8"], ["has property", "empty", "hand 6"], ["executable", ["take", "hand 6", "b 8"]]]
  qa = ar.compile_query(Q(["verify", [TAKE, PUT], final]), a)
  obs = qa["obligations"]
  s1 = ["$do", T(TAKE), "W0"]
  s2 = ["$do", T(PUT), s1]
  need([o["id"] for o in obs] == ["step1", "step2", "final"] and [o["requires_prefix"] for o in obs] == [0, 1, 2]
       and [o["role"] for o in obs] == ["step", "step", "final"], "obligation list: %r" % [(o["id"], o["requires_prefix"]) for o in obs])
  need(obs[0]["positive"]["question"]["@question"] == ["poss", T(TAKE), qat("W0")]
       and obs[1]["positive"]["question"]["@question"] == ["poss", T(PUT), qat(s1)]
       and obs[1]["negative"]["question"]["@question"] == ["-poss", T(PUT), qat(s1)], "step obligations stand at the chain before them")
  need(all(o["positive"] != o["negative"] and o["positive"]["question"]["@name"] != o["negative"]["question"]["@name"] for o in obs),
       "the positive and the negative obligation are distinct")
  pos = [lits_of(c) for c in obs[2]["positive"]["clauses"]]
  neg = [lits_of(c) for c in obs[2]["negative"]["clauses"]]
  need(len(pos) == 1 and len(pos[0]) == 4 and all(s == s2 for s in situations(pos[0])), "the final formula stands at the whole chain: %r" % pos)
  need(len(neg) == 3 and all(len(c) == 2 and c[-1] == ["$defq0"] for c in neg)
       and ["poss", T(["take", "hand 6", "b 8"]), qat(s2)] in [c[0] for c in neg],
       "one explicitly false conjunct proves the negative final obligation (the clause `L or $defq0` reads `not L -> $defq0`): %r" % neg)
  joint = lits_of(qa["joint_positive"]["clauses"][0])
  need(len(qa["joint_positive"]["clauses"]) == 1 and len(joint) == 6 and joint[0][0] == "-poss" and sit.situation_of(joint[1]) == s1
       and len({json.dumps(x[-1][:2] + x[-1][3:]) for x in joint[:-1]}) == 1,
       "the joint positive obligation shares one tense, location and knower: %r" % joint)
  # nothing is asserted: the input has the same positive poss and reachable facts with and without the query
  for o in obs:
    for pol in ("positive", "negative"):
      inp = ar.query_input(a, qa, o["id"], pol)
      added = inp[len(qa["selected_clauses"]["source"]) + len(qa["selected_clauses"]["library"])
                  + len(qa["selected_clauses"]["ordinary"]):]
      for obj in added:
        for c in ([lits_of(obj)] if "@logic" in obj else []):
          # a definition clause concludes $defq0 from its body; it is never a fact about poss, reachable or a fluent
          need(len(c) >= 2 and c[-1] == ["$defq0"], "%s %s: the query asserts %r" % (o["id"], pol, c))
      need(not any(x.get("@logic") and lits_of(x)[0][0] == "reachable" for x in inp), "a supplied sequence gets no reachability")
  # the empty sequence is the initial-state question, in the snapshot view
  qa0 = ar.compile_query(Q(["verify", [], ["is rel2", "on", "a 7", "table 9"]]), a)
  need(qa0["view"] == "verify" and qa0["selected_clauses"]["view"] == "snapshot" and [o["id"] for o in qa0["obligations"]] == ["final"]
       and qa0["obligations"][0]["requires_prefix"] == 0 and qa0["joint_positive"] is None
       and sit.situation_of(qa0["obligations"][0]["positive"]["question"]["@question"]) == "W0", "verify([], Q): %r" % qa0["obligations"])
  # the discovery default does not truncate a supplied sequence; an explicit smaller allowance stops it
  five = [TAKE, PUT, ["take", "hand 6", "a 7"], ["put_on", "hand 6", "a 7", "table 9"], TAKE]
  # round 4 (R2): the final formula's negative obligation reads a negative across the steps; the allowance is the
  # point here, so the backend declares negative persistence validated
  need(len(ar.compile_query(Q(["verify", five, final]), a, None, {"validated": ["negative_persistence"]})["obligations"])
       == 6, "five supplied steps under the default cap")
  need(outcome(ar.compile_query(Q(["verify", five, final]), a, {"search_cap": 2})) == "insufficient_search_allowance", "an explicit allowance below the sequence")
  print("  verify: step and final obligations stand on the root-based chain, paired and distinct, with prefix numbers; "
        "a false conjunct proves the negative final; nothing is asserted; the empty sequence is a snapshot question")


# ---------------------------------------------------------------------------
# reuse and integrity


def check_reuse():
  a = compiled(*TRAVEL)
  stored = ar.dumps(a)
  packages = [["plan", AT("Ann 1", "Helsinki 4")], ["reachable", AT("Ann 1", "Tallinn 3"), ["steps", "at_most", 1]],
              ["question", ["executable", SHIP]], ["verify", [BUS, SHIP], AT("Ann 1", "Helsinki 4")], ["ask", "X", AT("Ann 1", "X")]]
  qs = [ar.compile_query(Q(p, "Q%d" % (i + 1)), a) for i, p in enumerate(packages)]
  need(ar.dumps(a) == stored and ar.source_hashes(a) == a["hashes"], "query compilation changed the source artifact")
  need(all(q["source"]["source_hash"] == a["hashes"]["source"] for q in qs), "every query names the one source")
  need(qs[0]["view_hash"] == qs[1]["view_hash"] and qs[2]["view_hash"] == qs[4]["view_hash"]
       and len({qs[0]["view_hash"], qs[2]["view_hash"], qs[3]["view_hash"]}) == 3, "one hash per view, three views")
  need(len({q["obligations_hash"] for q in qs}) == 5 and len({q["hash"] for q in qs}) == 5, "every query has its own obligation hash")
  again = ar.compile_query(Q(packages[0]), a)
  need(ar.dumps(again) == ar.dumps(qs[0]), "query compilation is deterministic")
  # the input: unique names, the recorded clause names in order, one question
  inp = ar.query_input(a, qs[0], "plan", "positive")
  names = [o["@name"] for o in inp]
  sel = qs[0]["selected_clauses"]
  need(names[:len(sel["source"])] == sel["source"] and names[len(sel["source"]):len(sel["source"]) + len(sel["library"])] == sel["library"],
       "the input follows the recorded clause names")
  need(len(set(names)) == len(names) and sum(1 for o in inp if "@question" in o) == 1 and "@question" in inp[-1], "unique names, one question, last")
  need(json.loads(json.dumps(inp)) == inp, "the input is plain JSON")
  # a changed record, another source, a decided query
  broken = copy.deepcopy(qs[0])
  broken["obligations"][0]["positive"]["clauses"][0]["@logic"].pop(0)
  cv.expect_error(lambda: ar.query_input(a, broken, "plan", "positive"), "a query artifact with a changed obligation")
  broken = copy.deepcopy(qs[0])
  broken["view_hash"] = "0" * 64
  broken["hash"] = ar.query_hash(broken)
  cv.expect_error(lambda: ar.query_input(a, broken, "plan", "positive"), "a rehashed query artifact with another view hash")
  cv.expect_error(lambda: ar.query_input(compiled(*TRAVEL[:3]), qs[0], "plan", "positive"), "a query against another source")
  cv.expect_error(lambda: ar.query_input(a, qs[0], "plan", "negative"), "a negative reachability question")
  cv.expect_error(lambda: ar.query_input(a, qs[3], "step9", "positive"), "an unknown obligation")
  bad = ar.compile_query(Q(["plan", AT("Ann 1", "Helsinki 4"), ["steps", "exactly", 9]]), a, {"search_cap": 2})
  cv.expect_error(lambda: ar.query_input(a, bad, "plan", "positive"), "a decided query has no input")
  r = ar.solve_query(a, qs[0], cv.absent_backend())
  need(r["outcome"] == "backend_unavailable" and r["calls"]["model"] == 0 and r["calls"]["gk"] == 0 and r["plan"] is None,
       "solve_query: %r" % r)
  # the ordinary profile gets no action view
  o = ar.compile_source(None, [cav.S(["isa", "person", "Ann 1"])], la.ORDINARY, None, {"Ann 1": "person"})
  qo = ar.compile_query(Q(["question", ["isa", "person", "Ann 1"]]), o)
  need(qo["obligations"] is None and qo["selected_clauses"] is None and qo["pending_passes"] == [lq.PASS], "the ordinary profile: %r" % qo["passes"])
  print("  reuse: five queries leave the source and its hashes unchanged; one hash per view; the rebuilt input follows the "
        "recorded names; a changed record, another source and a decided query give no input")


# ---------------------------------------------------------------------------
# backend requirements


def requirement(qa, name=lq.NEGATIVE_PERSISTENCE):
  hit = [r for r in qa["backend_requirements"] or [] if r["capability"] == name]
  return hit[0] if hit else None


def check_backend():
  world = TRAVEL[:3] + [NOT(LICENSED), DENIAL]
  c01 = compiled(*(world + [["can", "Ann 1", POLISH]]))
  c02 = compiled(*(world + [["can", "Ann 1", GRANT]]))
  goal = AT("Ann 1", "Tallinn 3")
  # the contrast of A6.3 on supplied sequences
  q = ar.compile_query(Q(["verify", [POLISH, BUS], goal]), c01)
  need(outcome(q) == "unsupported_backend_requirement" and q["outcome"]["reason"] == "negative_persistence_unavailable"
       and q["outcome"]["units"] == ["S4", "S5"] and q["obligations"] is None, "polish, then bus: %r" % q["outcome"])
  q = ar.compile_query(Q(["verify", [GRANT, BUS], goal]), c02)
  need(outcome(q) is None and requirement(q) is None and len(q["obligations"]) == 3, "grant, then bus is the positive control: %r" % q["outcome"])
  for seq, final, stops in (([BUS], goal, False), ([POLISH], NOT(LICENSED), True), ([POLISH], ["has property", "polished", "cup 5"], False),
                            ([POLISH], ["executable", BUS], True), ([], NOT(LICENSED), False)):
    q = ar.compile_query(Q(["verify", seq, final]), c01)
    need((outcome(q) == "unsupported_backend_requirement") == stops, "verify %r %r: %r" % (seq, final, q["outcome"]))
  q = ar.compile_query(Q(["verify", [GRANT, POLISH, BUS], goal]), compiled(*(world + [["can", "Ann 1", GRANT], ["can", "Ann 1", POLISH]])))
  need(outcome(q) is None, "a certain positive write ends the negative: %r" % q["outcome"])
  # discovery: the horizon table
  for steps, stops in ((None, True), (["steps", "at_most", 2], True), (["steps", "at_most", 1], False), (["steps", "exactly", 0], False)):
    for a in (c01, c02):
      q = ar.compile_query(Q(["plan", goal] + ([steps] if steps else [])), a)
      need((outcome(q) == "unsupported_backend_requirement") == stops, "plan %r: %r" % (steps, q["outcome"]))
  q = ar.compile_query(Q(["plan", NOT(LICENSED), ["steps", "at_most", 1]]), c01)
  need(outcome(q) == "unsupported_backend_requirement", "a negative goal read after one transition: %r" % q["outcome"])
  need(outcome(ar.compile_query(Q(["question", NOT(LICENSED)]), c01)) is None, "an immediate question needs nothing carried")
  # a validated backend lifts the refusal and keeps the requirement on record
  q = ar.compile_query(Q(["plan", goal]), c01, None, {"validated": [lq.NEGATIVE_PERSISTENCE]})
  need(outcome(q) is None and requirement(q) is not None and q["obligations"] and q["backend"] == {"validated": [lq.NEGATIVE_PERSISTENCE]},
       "a validated backend: %r" % q["outcome"])
  cv.expect_error(lambda: ar.compile_query(Q(["plan", goal]), c01, None, {"validated": ["time_travel"]}), "an unknown capability")
  # a written negative: read directly in the next step, or across another transition
  force = ["change", "Ann 1", "lock 12", "forced", "unspecified"]
  open_ = ["change", "Ann 1", "chest 11", "open", "unspecified"]
  chest = [["isa", "person", "Ann 1"], ["has property", "locked", "chest 11"], ["can", "Ann 1", force],
           ["after", force, NOT(["has property", "locked", "chest 11"])],
           ["forall", "B", ["forall", "U", ["implies", ["executable", ["change", "B", "chest 11", "open", "U"]], NOT(["has property", "locked", "chest 11"])]]]]
  permitted, unpermitted = compiled(*(chest + [["can", "Ann 1", open_]])), compiled(*chest)
  opened = ["has property", "open", "chest 11"]
  for steps, stops in ((["steps", "at_most", 2], False), (["steps", "at_most", 3], True), (None, True)):
    q = ar.compile_query(Q(["plan", opened] + ([steps] if steps else [])), permitted)
    need((outcome(q) == "unsupported_backend_requirement") == stops, "chest %r: %r" % (steps, q["outcome"]))
  need(outcome(ar.compile_query(Q(["plan", opened]), unpermitted)) is None, "a restriction on an action without any permission is irrelevant")
  need(outcome(ar.compile_query(Q(["verify", [force, open_], opened]), permitted)) is None, "a written negative read in the next step")
  need(outcome(ar.compile_query(Q(["verify", [force, POLISH, open_], opened]), compiled(*(chest + [["can", "Ann 1", open_], ["can", "Ann 1", POLISH]]))))
       == "unsupported_backend_requirement", "a written negative read across another transition")
  # an indirect read through a standing law
  law = ["state_law", ["forall", "X", ["implies", NOT(["has property", "licensed", "X"]), ["has property", "barred", "X"]]]]
  ind = compiled(*(TRAVEL[:3] + [NOT(LICENSED), law, ["can", "Ann 1", POLISH]]))
  need(outcome(ar.compile_query(Q(["verify", [POLISH], ["has property", "barred", "Ann 1"]]), ind)) == "unsupported_backend_requirement"
       and outcome(ar.compile_query(Q(["plan", ["has property", "barred", "Ann 1"], ["steps", "at_most", 1]]), ind)) == "unsupported_backend_requirement"
       and outcome(ar.compile_query(Q(["question", ["has property", "barred", "Ann 1"]]), ind)) is None, "a negative read through a standing law")
  # a restriction's necessity uses the negation of its required literal; an unconditional denial makes that read idle
  red = ["forall", "X", ["implies", ["executable", ["take", "hand 6", "X"]], ["has property", "red", "X"]]]
  notred = NOT(["has property", "red", "b 8"])
  take_b = ["take", "hand 6", "b 8"]
  r1 = compiled(*(BLOCKS + [red, notred, ["has property", "red", "a 7"]]))
  need(outcome(ar.compile_query(Q(["verify", [TAKE, PUT], ["executable", take_b]]), r1)) == "unsupported_backend_requirement"
       and outcome(ar.compile_query(Q(["verify", [TAKE, PUT], ["is rel2", "on", "a 7", "b 8"]]), r1)) is None
       and outcome(ar.compile_query(Q(["question", ["executable", take_b]]), r1)) is None, "a carried negative decides a No through a necessity")
  r2 = compiled(*(BLOCKS + [red, notred, NOT(["can", "hand 6", take_b])]))
  need(outcome(ar.compile_query(Q(["verify", [TAKE, take_b], ["is rel2", "holding", "hand 6", "b 8"]]), r2)) is None,
       "a timeless denial refutes the step without a carried negative")
  # shared-source confidence (checkpoint-2 decision): one action application reads poss in the reachability step, the
  # effects and the frames, and GK counts an uncertain path's evidence once per use; a query that can apply an uncertain
  # path more than once in one application records the requirement.  No unit records it; it never stops compilation.
  probably = ["@id", "S9", ["and", ["holds", "W0", ["can", "robot 10", ["move", "robot 10", "Haapsalu 2", "Tallinn 3", "bus"]]], ["@p", "S9", 0.8]]]
  rmove = ["move", "robot 10", "Haapsalu 2", "Tallinn 3", "bus"]
  put = ["@id", "S8", ["and", ["holds", "W0", ["can", "robot 10", ["put_on", "robot 10", "a 7", "b 8"]]], ["@p", "S8", 0.8]]]
  sh = compiled(AT("robot 10", "Haapsalu 2"), probably, put)
  need(all(u["requirements"] == [] for u in sh["units"]) and "shared_source_confidence" not in (sh["backend_requirements"] or {}),
       "no unit records shared_source_confidence: %r" % sh["backend_requirements"])
  rows = [(["question", ["executable", rmove]], None), (["plan", AT("robot 10", "Tallinn 3")], ["S8", "S9"]),
          (["verify", [rmove], AT("robot 10", "Tallinn 3")], ["S9"]), (["verify", [], AT("robot 10", "Haapsalu 2")], None),
          (["question", AT("robot 10", "Haapsalu 2")], None), (["question", ["executable", ["put_on", "robot 10", "a 7", "b 8"]]], None)]
  for p, units in rows:
    q = ar.compile_query(Q(p), sh)
    got = requirement(q, lq.SHARED_CONFIDENCE)
    need(outcome(q) is None and (got["units"] if got else None) == units, "shared confidence %r: %r" % (p, q["backend_requirements"]))
  # another rule for the same action does not remove the requirement (Astra's review R1, 2026-09-24): a rule whose
  # condition is unknown (the review's GK probe found the plan at 0.1296 with the requirement gone), a certain rule
  # that covers part of the uncertain rule's actions, and a certain rule for the same action
  anyroute = ["forall", "F", ["forall", "T", ["can", "robot 10", ["move", "robot 10", "F", "T", "bus"]]]]
  uncertain_any = ["@id", "S9", ["and", ["holds", "W0", anyroute], ["@p", "S9", 0.8]]]
  magic = ["forall", "F", ["forall", "T", ["implies", ["has property", "magic", "robot 10"],
                                            ["can", "robot 10", ["move", "robot 10", "F", "T", "bus"]]]]]
  for label, rule, base in (("an unknown condition", magic, probably), ("a partial overlap", ["can", "robot 10", rmove], uncertain_any),
                            ("a certain rule of the same action", ["can", "robot 10", rmove], probably)):
    other = compiled(AT("robot 10", "Haapsalu 2"), base, rule)
    for p in (["plan", AT("robot 10", "Tallinn 3")], ["verify", [rmove], AT("robot 10", "Tallinn 3")]):
      got = requirement(ar.compile_query(Q(p), other), lq.SHARED_CONFIDENCE)
      need(got is not None and got["units"] == ["S9"], "an uncertain path beside %s, %s: %r" % (label, p[0], got))
  print("  backend: polish-then-bus stops and grant-then-bus does not; the horizon table for initial and written negatives, "
        "law and goal reads; standing-law reads; necessity reads; a validated backend; shared_source_confidence for a discovery "
        "or verify that can apply an uncertain path, not for an immediate question, and kept beside another rule of the "
        "same action (unknown condition, partial overlap, certain)")


# ---------------------------------------------------------------------------
# derivation on the prover inputs


def one_context(t):
  """The test derivation reads every context as the one context of the text.

  The tool compares a default's blocker by subsumption.  A denial that rests
  on an initial fact has that fact's `$ctxt` term, and the library default has
  a context variable, so the blocker would not be found.  One constant for
  every context term and context variable removes that difference.  The
  constant keeps the world slot, so the situation (W0, W1, $do(A, S)) keeps
  the worlds apart, and the query's view has already left out the excluded
  units, so the collapse loses no world and no qualifier decision.
  """
  if isinstance(t, list):
    return ["$ctxt", "c0", one_context(t[2]), "c0", "c0"] if t and t[0] == "$ctxt" else [one_context(x) for x in t]
  return t


def derive(a, qa, oid, polarity, depth):
  """(facts, proved) of one obligation under the test derivation.

  The derivation is forward only.  When it does not reach a Boolean
  definition question, it runs once more with the negated goal as a fact: an
  implication is proved by refutation, and deriving `$defq0` from `-$defq0`
  proves `$defq0`.  The second run is used only after the first fails, because
  the assumed fact also takes part in the blocker checks of the defaults.
  """
  inp = ar.query_input(a, qa, oid, polarity)
  goal = one_context(inp[-1]["@question"])
  theory = [one_context(lits_of(o)) for o in inp if "@logic" in o]
  facts = crs.saturate(theory, depth=depth)
  if not crs.holds(facts, goal) and goal == ["$defq0"]:
    return facts, crs.holds(crs.saturate(theory + [[["-$defq0"]]], depth=depth), goal)
  return facts, crs.holds(facts, goal)


def plans_of(facts, root="W0"):
  out = []
  for f in facts.get("$defq0", []):
    s, acts = f[1], []
    while isinstance(s, list) and s[0] == sit.DO:
      acts.append(s[1])
      s = s[2]
    need(s == root, "a derived plan is not rooted at %s: %r" % (root, f))
    out.append(list(reversed(acts)))
  return out


def verdict(a, qa):
  """Yes | No | Unknown | contested from the paired obligations, by the prefix rule of A3.4.  No replay here."""
  depth = len(qa["query"]["sequence"] or [])
  for o in qa["obligations"]:
    yes = derive(a, qa, o["id"], "positive", depth)[1]
    no = derive(a, qa, o["id"], "negative", depth)[1]
    if yes and no:
      return "contested"
    if not yes:
      return "No" if no else "Unknown"
  return "Yes"


# left out of the derivation: the blocks cases whose forward derivation takes 10 to 60 seconds each (the gold
# tower plan is derived, in 58 seconds), and the inconsistent sources, whose outcome the replay decides (WP11)
SLOW = ("c15_", "p02_")
REPLAY_DECIDED = ("c09_",)
# The tool blocks a default when a derived blocker covers the whole conclusion.  In x06 base the normal permission
# concludes an availability with F and T open, and the strict denial names one route only, so the tool keeps the
# permission for the denied route as well.  GK checks the blocker on the instance a proof uses.
# These rows are left out; the availability check of WP06 covers the clauses themselves.
TOOL_LIMIT = {("x06_permission_strength:base", "Q1"), ("x06_permission_strength:base", "Q3")}
# Library 1.2.0: the derivation agrees with the gold on the inconsistent source c03 `both` as well (executable
# contested, can Yes), because a restriction-derived -poss no longer reaches can.  No known difference remains.
KNOWN_DIFFERENCE = {}


def check_derivation():
  answers = found = none = asked = 0
  for case, a, q, qa in supported_gold():
    if qa["outcome"] or case["case"].startswith(SLOW + REPLAY_DECIDED) or (case["case"], q["id"]) in TOOL_LIMIT:
      continue
    w = "%s/%s" % (case["case"], q["id"])
    e, kind = q["expect"], qa["query"]["kind"]
    if kind in ("plan", "reachable"):
      got = plans_of(derive(a, qa, "plan", "positive", qa["search"]["depth"])[0], lq.root_situation(ar._selection(qa)))
      for fp in e.get("forbidden_plans", []):
        need([T(x) for x in fp] not in got, "%s: a forbidden plan %r was derived" % (w, fp))
      if e.get("plan") is not None and e.get("outcome") in (None, "plan_found", "goal_already_holds"):
        need([T(x) for x in e["plan"]] in got, "%s: gold plan %r, derived %r" % (w, e["plan"], got))
        if qa["search"]["require_zero_remaining"]:
          need(all(len(p) == qa["search"]["depth"] for p in got), "%s: an exact bound admits another length: %r" % (w, got))
        need(all(len(p) <= qa["search"]["depth"] for p in got), "%s: a plan beyond the seed" % w)
        found += 1
      elif e.get("outcome") == "not_found":
        need(got == [], "%s: gold not_found, derived %r" % (w, got))
        none += 1
    elif kind == "ask":
      facts = derive(a, qa, "q", "positive", 0)[0]
      got = sorted({f[1] for f in facts.get("$defq0", [])})
      need(got == [T(e["answer"])], "%s: gold %s, derived %r" % (w, e["answer"], got))
      asked += 1
    elif e.get("answer") in ("Yes", "No", "Unknown", "contested"):
      got = verdict(a, qa)
      want = KNOWN_DIFFERENCE.get((case["case"], q["id"]), (e["answer"], e["answer"]))
      need(want[0] == e["answer"] and got == want[1], "%s: gold %s, derived %s" % (w, e["answer"], got))
      answers += 1
  print("  derivation: on the production inputs the test derivation gives %d gold answers (no documented difference), "
        "%d asked entities, %d gold plans and %d empty searches" % (answers, asked, found, none))


def check_selection():
  """Root selection, exclusions, the ambient and the knower (migration step 1b.5)."""
  by = {c["case"]: c for c in fm.load_all()}

  def compiled_gold(name, qid):
    case = by[name]
    a = cv.gold_source(case)
    q = [x for x in case["queries"] if x["id"] == qid][0]
    return a, ar.compile_query(q["stage2"], a, cv.gold_limits(q), **fm.selection(q))

  def body(a, qa, oid="q"):
    inp = ar.query_input(a, qa, oid, "positive")
    return inp, [x for o in inp if "@logic" in o for x in lits_of(o)]

  # one source, two roots: the seed, the question literals and the snapshot binding follow the root (c33)
  a, q1 = compiled_gold("c33_root_selection:base", "Q1")
  need(q1["planning_root"] == "W1" and q1["seed"]["@logic"] == ["reachable", "W1", lq.unary(2)],
       "the default root W1 roots the seed: %r" % q1["seed"])
  need(lq.query_context(lq.selection("W1"))[2] == "W1", "the root world in the query context")
  _, q2 = compiled_gold("c33_root_selection:base", "Q2")
  need(q2["seed"]["@logic"][1] == "W0" and q1["view_hash"] == q2["view_hash"],
       "the root W0 roots the seed; the discovery view is the same general view: %r" % q2["seed"])
  _, q4 = compiled_gold("c33_root_selection:base", "Q4")
  _, q5 = compiled_gold("c33_root_selection:base", "Q5")
  need(q4["view_hash"] != q5["view_hash"], "the snapshot view hash covers the root binding")
  for qa, root in ((q4, "W0"), (q5, "W1")):
    inp, lits = body(a, qa)
    laws = [x for o in inp if "@logic" in o and not o.get("@name", "").startswith(("src:S", "query:")) for x in lits_of(o)]
    need(all(sit.situation_of(x) == root for x in laws if lib.predicate(x) in lib.FLUENT_LIKE and lib.predicate(x) != "reachable"),
         "the library and ordinary snapshot is bound to %s" % root)
    need(all(s == root for s in situations(query_literals(qa))), "the question stands at %s" % root)
    need(not any(contains(x, lib.SITUATION) or contains(x, sit.SIT) for x in lits), "a free situation")
  # facts keep their own world in every view: the W1 fact reaches a W0-rooted input with its own world
  inp, lits = body(a, q4)
  need(["is rel2", "located_at", "#:Ann 1", "#:Tallinn 3", ["$ctxt", "present", "W1", sit.FACT_L, sit.FACT_K]] in lits,
       "the W1 fact keeps its world in a W0-rooted snapshot")
  # the qualifier policy: exclusions with their reasons, the ambient and the knower (c35)
  rows = (("scope", [{"unit": "S4", "reason": "scope_location_mismatch"}], "#:kitchen 5", lq.QUERY_K),
          ("knower_objective", [{"unit": "S4", "reason": "knower_mismatch"}], lq.QUERY_L, lq.QUERY_K),
          ("knower_selected", [], lq.QUERY_L, "#:Bob 7"),
          ("past_fact", [{"unit": "S4", "reason": "underspecified_temporal_root"}], lq.QUERY_L, lq.QUERY_K),
          ("provenance", [], lq.QUERY_L, lq.QUERY_K), ("objective_control", [], lq.QUERY_L, lq.QUERY_K))
  for variant, excluded, loc, knower in rows:
    a, qa = compiled_gold("c35_qualifier_policy:" + variant, "Q1")
    need(qa["excluded"] == excluded, "%s: excluded %r" % (variant, qa["excluded"]))
    ctx = qa["obligations"][0]["positive"]["question"]["@question"][-1]
    need(ctx == ["$ctxt", "present", "W0", loc, knower], "%s: the query context %r" % (variant, ctx))
    inp, lits = body(a, qa)
    need(not any(o.get("@name", "").startswith("src:S4:") for o in inp) == bool(excluded),
         "%s: the excluded unit's clauses in the input" % variant)
    if variant == "knower_selected":
      need(not any(contains(x, sit.OBJ) for x in lits) and any(contains(x, "#:Bob 7") for x in lits),
           "a knower-relative query gives every law the knower")
    else:
      need(not any(contains(x, "#:Bob 7") for o in inp if "@logic" in o and o.get("@name", "").startswith(("src:S6", "query:"))
                   for x in lits_of(o)), "%s: an objective query keeps $obj in the laws" % variant)
  a, qa = compiled_gold("c35_qualifier_policy:scope", "Q1")
  kept = [o for o in ar.query_input(a, qa) if o.get("@name", "").startswith("src:S3:")]
  need(kept and all(lits_of(o)[0][-1][3] == "#:kitchen 5" for o in kept), "the kitchen fact is kept with its scope constant")
  print("  selection: the root selects the seed, the question situation and the snapshot binding; facts keep their world; "
        "%d qualifier rows give the exclusions, the ambient and the knower of section 3" % len(rows))


def check_selected_dependencies():
  """Negative persistence, transport and granularity read the facts the query's selection admits (Astra's review R2).

  Each row has a control on which the same fact is admitted and the check
  still stops the query.  The exclusions stay recorded when a check stops it.
  """
  S = lambda uid, f, w="W0": ["@id", uid, ["holds", w, f]]
  ents = {"Robo 1": "robot", "cup 2": "artifact", "Bob 3": "person", "kitchen 4": "place", "hall 5": "place",
          "Ann 6": "person", "Haapsalu 7": "place", "Tallinn 8": "place", "key 9": "artifact", "Estonia 10": "place"}

  def source(units, contexts=None):
    return ar.compile_source(None, units, la.PROFILE, entities=ents, worlds=["W0", "W1"], contexts=contexts)

  def outcome_of(a, p, **sel):
    qa = ar.compile_query(Q(p), a, **dict({"planning_root": "W0"}, **sel))
    return (qa["outcome"] or {}).get("outcome"), qa

  # the qualifier test of the source level agrees with the default selection's exclusions
  for rec in (None, {"tense": "past"}, {"knower": "Bob 3"}, {"location": "kitchen 4", "location_role": "scope"},
              {"location": "kitchen 4", "location_role": "provenance"}, {"tense": "present"}):
    need(sit.qualified(rec) == bool(lq.exclusions([{"id": "S", "context": rec}])), "qualified %r" % (rec,))
  # negative persistence: an initial negative of the root's world only, of an admitted unit only
  negative = NOT(["has property", "red", "cup 2"])
  goal = ["plan", negative, ["steps", "at_most", 1]]
  scope = {"location": "kitchen 4", "location_role": "scope"}
  rows = (("the root's world", "W0", None, {}, True, []),
          ("another world", "W1", None, {"planning_root": "W0"}, False, []),
          ("that world as the root", "W1", None, {"planning_root": "W1"}, True, []),
          ("another knower", "W0", {"knower": "Bob 3"}, {}, False, [{"unit": "S2", "reason": "knower_mismatch"}]),
          ("that knower", "W0", {"knower": "Bob 3"}, {"knower": "Bob 3"}, True, []),
          ("the past", "W0", {"tense": "past"}, {}, False, [{"unit": "S2", "reason": "underspecified_temporal_root"}]),
          ("the ambient scope", "W0", scope, {"ambient": "kitchen 4"}, True, []),
          ("another ambient", "W0", scope, {"ambient": "hall 5"}, False, [{"unit": "S2", "reason": "scope_location_mismatch"}]))
  for label, world, rec, sel, stops, excluded in rows:
    a = source([S("S1", ["isa", "robot", "Robo 1"]), S("S2", negative, world)], {"S2": rec} if rec else None)
    got, qa = outcome_of(a, goal, **sel)
    need((got == "unsupported_backend_requirement") == stops and qa["excluded"] == excluded,
         "negative persistence, %s: %r, excluded %r" % (label, got, qa["excluded"]))
    need(stops or requirement(qa) is None, "negative persistence, %s: a requirement on record" % label)
  # a check that stops the query keeps the exclusions of its selection on record
  a = source([S("S1", ["isa", "robot", "Robo 1"]), S("S2", negative), S("S3", ["has property", "wet", "cup 2"])],
             {"S3": {"knower": "Bob 3"}})
  got, qa = outcome_of(a, goal)
  need(got == "unsupported_backend_requirement" and qa["excluded"] == [{"unit": "S3", "reason": "knower_mismatch"}],
       "the exclusions of a stopped query: %r, %r" % (got, qa["excluded"]))
  # transport: a holding of another knower is not admitted to an objective query
  travel = ["move", "Ann 6", "Haapsalu 7", "Tallinn 8", "bus"]
  held = source([S("S1", ["and", ["isa", "person", "Ann 6"], ["is rel2", "located_at", "Ann 6", "Haapsalu 7"]]),
                 S("S2", ["can", "Ann 6", travel]), S("S3", ["is rel2", "holding", "Ann 6", "key 9"])],
                {"S3": {"knower": "Bob 3"}})
  verify = ["verify", [travel], ["is rel2", "located_at", "key 9", "Tallinn 8"]]
  need(outcome_of(held, verify)[0] is None, "an objective verify beside Bob's holding")
  got, qa = outcome_of(held, verify, knower="Bob 3")
  need(got == "unsupported_translation" and qa["outcome"]["reasons"] == ["unsupported_transport_dependency"],
       "Bob's verify reads his holding: %r" % qa["outcome"])
  # granularity: two locations of one entity are compared only when one selection admits both
  at = lambda x, p: ["is rel2", "located_at", x, p]
  two = [S("S1", at("Ann 6", "Haapsalu 7")), S("S2", at("Ann 6", "Tallinn 8"))]
  need(source(two)["support"]["reasons"] == ["unsupported_location_granularity"], "two unqualified locations")
  plan = ["plan", at("Ann 6", "Tallinn 8")]
  for label, rec, sel, stops in (("a past location", {"tense": "past"}, {}, False),
                                 ("Bob's location, an objective query", {"knower": "Bob 3"}, {}, False),
                                 ("Bob's location, Bob's query", {"knower": "Bob 3"}, {"knower": "Bob 3"}, True)):
    a = source(two, {"S2": rec})
    got, qa = outcome_of(a, plan, **sel)
    need(a["support"]["status"] == "supported", "%s: the source level %r" % (label, a["support"]))
    need((got == "unsupported_translation") == stops, "%s: %r" % (label, qa["outcome"]))
    need(not stops or (qa["outcome"]["reasons"] == ["unsupported_location_granularity"] and qa["outcome"]["units"] == ["S1", "S2"]),
         "%s: %r" % (label, qa["outcome"]))
  nested = source([S("S1", at("Ann 6", "Tallinn 8")), S("S2", at("Tallinn 8", "Estonia 10"))], {"S2": {"knower": "Bob 3"}})
  need(nested["support"]["status"] == "supported" and outcome_of(nested, plan)[0] is None
       and outcome_of(nested, plan, knower="Bob 3")[1]["outcome"]["units"] == ["S2"], "a nesting that only Bob states")
  print("  selected dependencies: negative persistence reads the root's world and the admitted units (%d rows with their "
        "controls); a stopped query keeps its exclusions; transport and granularity read what the selection admits"
        % len(rows))


def run():
  check_gold()
  check_selection()
  check_selected_dependencies()
  check_snapshot()
  check_discovery()
  check_verify()
  check_reuse()
  check_backend()
  check_derivation()


if __name__ == "__main__":
  run()
