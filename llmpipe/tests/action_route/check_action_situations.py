"""WP04 unit checks: scope, situations, witnesses and clauses of state formulas.

No model, no GK.  The checks inspect the compiler's actual output:

  gold        every gold clause pattern with a role this pass produces
              (initial_fact, static, standing_law) is matched against the
              emitted clauses; patterns of later roles are counted as deferred
  scope       C15-C18 and C28: the world inside quantified and conditional initial
              descriptions, one shared situation in a standing law, no free
              situation anywhere, static atoms without a situation
  witnesses   situations are bound before Skolemization: sk(Sit) and
              sk(Sit, X) in standing laws, constants in initial and static
              descriptions; the x04 `inspection` expectations
  defaults    normally compiles to a defeasible clause in its scope, or is a
              named unsupported form; it is never dropped or made a predicate
  mixed       a timeless conclusion from a fluent, positive or negative, is
              mixed_scope_rule, also behind a computed helper; no clause
  names       source variables called S and C do not meet compiler variables
  passes      no ordinary rewrite ran: the clause vocabulary is the source's
  contexts    every law literal has the per-literal context
              $ctxt(present, S, L, $obj), S the law's situation in the world
              slot, under the agreement rule; every fact has the context of
              its unit's record with its world in the world slot; the source
              hash covers worlds and context records

The exact clause expectations below write a law literal in the form they had
before the world-slot layout, the situation and then ?:Ctx (`erase`);
`check_contexts` asserts the law pattern itself on every gold clause.
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_route as ar
import fixture_materialize as fm
import lc_action as la
import lc_action_situate as sit

ROLES = ("initial_fact", "static", "standing_law")


class Bad(Exception):
  pass


def with_pending(a, name="a_later_pass"):
  """A copy of a source artifact that names one more pending pass, rehashed."""
  b = copy.deepcopy(a)
  b["pending_passes"].append(name)
  b["hashes"] = ar.source_hashes(b)
  return b


def need(cond, message):
  if not cond:
    raise Bad(message)


def law_situation(t):
  return t == sit.SIT or (isinstance(t, list) and len(t) == 3 and t[0] == sit.DO and t[2] == sit.SIT)


def law_context(t):
  """$ctxt(present, S, L, $obj), S = ?:Sit or $do(A, ?:Sit), L a location variable: a compiled law literal's context."""
  return isinstance(t, list) and len(t) == 5 and t[:2] == ["$ctxt", "present"] and law_situation(t[2]) \
    and isinstance(t[3], str) and t[3].startswith("?:L") and t[4] == sit.OBJ


def erase(x):
  """`x` with every law literal written as before the world-slot layout: [P, args..., S, ?:Ctx].
  A literal with a context term of another form stays, so an expectation that writes ?:Ctx does not match it."""
  if isinstance(x, list):
    if x and isinstance(x[0], str) and law_context(x[-1]):
      return [erase(y) for y in x[:-1]] + [erase(x[-1][2]), "?:Ctx"]
    return [erase(y) for y in x]
  if isinstance(x, dict):
    return {k: erase(v) for k, v in x.items()}
  return x


# ---------------------------------------------------------------------------
# the pattern matcher of fixtures/README.md, for the roles of this pass


def term_matches(pattern, term):
  if isinstance(pattern, list):
    if not pattern or pattern[0] != "sk":
      return False
    if not (isinstance(term, list) and isinstance(term[0], str) and term[0].startswith("sk_")):
      return False
    if len(term) != len(pattern):
      return False
    for p, t in zip(pattern[1:], term[1:]):
      if not (isinstance(t, str) and t.startswith("?:")):
        return False
      if (p == "S") != (t == sit.SIT):
        return False
    return True
  if not isinstance(term, str):
    return False
  if la.is_var(pattern):
    return term.startswith("?:") and term != sit.SIT
  if la.is_concrete(pattern):
    return term == "#:" + pattern
  return term == pattern      # a lexical constant or a witness constant


def literal_matches(p, lit, negate=False):
  """`p` is {"lit", "sign", "situation"}; a body literal is matched negated."""
  name = lit[0].lstrip("-")
  positive = not lit[0].startswith("-")
  args = lit[1:]
  if sit.bears_situation(name):
    args = args[:-1]
  if "lit" in p:
    if p["lit"][0] != name or len(p["lit"]) - 1 != len(args):
      return False
    if not all(term_matches(a, b) for a, b in zip(p["lit"][1:], args)):
      return False
  if "sign" in p and (p["sign"] == "+") != (positive != negate):
    return False
  if "situation" in p and p["situation"] != sit.situation_class(lit):
    return False
  return True


def record_matches(p, rec):
  if p.get("role") not in ("*", rec["role"]):
    return False
  if "unit" in p and p["unit"] != rec["unit"]:
    return False
  heads = [x for x in rec["clause"] if literal_matches(p, x)]
  if not heads:
    return False
  if "body" not in p:
    return True
  for head in heads:
    rest = [x for x in rec["clause"] if x is not head]
    used = []
    ok = True
    for b in p["body"]:
      hit = [x for x in rest if x not in used and literal_matches(b, x, negate=True)]
      if not hit:
        ok = False
        break
      used.append(hit[0])
    if ok and (not p.get("body_exact") or len(used) == len(rest)):
      return True
  return False


def gold_source(case):
  s1 = None
  if case["input_kind"] == "text":
    s1 = [{"id": u["id"], "text": u.get("text"), "stage1": u.get("stage1")} for u in case["units"]]
  return ar.compile_source(s1, [u["stage2"] for u in case["units"]], case["profile"], case["text"], case["entities"],
                           worlds=case.get("worlds"), contexts=fm.contexts(case))


def records_of(a):
  return [c for u in a["units"] for c in (u["clauses"] or [])]


def check_gold():
  have = have_not = deferred = state_units = pending_notes = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    w = case["case"]
    a = gold_source(case)
    recs = records_of(a)
    for u in a["units"]:
      if u["situated"] is not None:
        free = sit.free_compiler_variables(u["situated"])
        need(not free, "%s/%s: the situated view leaves %s unbound" % (w, u["id"], sorted(free)))
        need((u["situation"] in ("shared_current", "successor")) == (u["situated"][:2] == ["forall", sit.SIT]),
             "%s/%s: the situation binder of a standing law" % (w, u["id"]))
      if u["form"] in sit.STATE_FORMS and u["status"] == "supported":
        state_units += 1
        if u["clauses"] is None:
          pending_notes += 1
      for r in u["clauses"] or []:
        for lit in r["clause"]:
          cls = sit.situation_class(lit)
          need(cls != "free", "%s/%s: a free situation in %r" % (w, u["id"], lit))
          need(sit.bears_situation(lit[0].lstrip("-")) == (cls != "none"), "%s/%s: %r" % (w, u["id"], lit))
        classes = {sit.situation_class(x) for x in r["clause"]} - {"none"}
        # an effect clause reads the shared situation and writes its successor; nothing else mixes
        need(len(classes) <= 1 or (classes == {"shared_current", "successor"} and r["role"] in ("effect", "marker")),
             "%s/%s: one clause mixes situations: %r" % (w, u["id"], r["clause"]))
    for g in case["units"]:
      cl = g.get("clauses") or {}
      for p in cl.get("must_have", []):
        if p.get("role") in ROLES:
          need(any(record_matches(p, r) for r in recs), "%s/%s: no clause matches %s" % (w, g["id"], json.dumps(p)))
          have += 1
        else:
          deferred += 1
      for p in cl.get("must_not_have", []):
        if p.get("role") in ROLES + ("*",):
          hit = [r for r in recs if record_matches(p, r)]
          need(not hit, "%s/%s: forbidden %s matches %r" % (w, g["id"], json.dumps(p), hit[:1]))
          have_not += 1
        else:
          deferred += 1
    if a["support"]["status"] != "supported":
      need(a["clauses"] is None, "%s: an unsupported source must not expose a clause list" % w)
    else:
      need(a["clauses"] == recs + a["restriction_clauses"] + a["policy_clauses"] + a["identity_clauses"], "%s: the artifact clause list" % w)
  need(pending_notes == 0, "%d supported state units were not compiled" % pending_notes)
  print("  gold: %d required and %d forbidden clause patterns checked on the output of %d state units; "
        "%d patterns of later roles deferred" % (have, have_not, state_units, deferred))


# ---------------------------------------------------------------------------

ENTS = {"Ann 1": "person", "egg 2": "food", "a 3": "block", "b 4": "block", "table 5": "table",
        "bridge 6": "artifact", "Haapsalu 7": "place", "Tallinn 8": "place"}


def S(f, i="S1"):
  return ["@id", i, ["holds", "W0", f]]


def compiled(*formulas):
  pkgs = [S(f, "S%d" % (i + 1)) for i, f in enumerate(formulas)]
  return ar.compile_source(None, pkgs, la.PROFILE, None, ENTS)


def lits(a, unit):
  """The clauses of one unit, law contexts erased (`erase`)."""
  u = [x for x in a["units"] if x["id"] == unit][0]
  return [erase(r["clause"]) for r in u["clauses"] or []]


def check_scope():
  initial = ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]
  # a quantified initial description: W0 in the conclusion (C15)
  a = compiled(["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "clear_top", "X"]]])
  need(lits(a, "S1") == [[["-isa", "block", "?:v_X"], ["has property", "clear_top", "?:v_X", initial]]], "C15: %r" % lits(a, "S1"))
  # a conditional initial description: W0 in the condition and in the conclusion (C16)
  a = compiled(["forall", "X", ["implies", ["and", ["isa", "block", "X"], ["is rel2", "on", "X", "table 5"]], ["has property", "red", "X"]]],
               ["state_law", ["forall", "X", ["implies", ["has property", "whisked", "X"], ["has property", "ready", "X"]]]])
  need(lits(a, "S1") == [[["-isa", "block", "?:v_X"], ["-is rel2", "on", "?:v_X", "#:table 5", initial],
                          ["has property", "red", "?:v_X", initial]]], "C16 initial: %r" % lits(a, "S1"))
  need(lits(a, "S2") == [[["-has property", "whisked", "?:v_X", "?:Sit", "?:Ctx"], ["has property", "ready", "?:v_X", "?:Sit", "?:Ctx"]]],
       "C16 standing: %r" % lits(a, "S2"))
  need([u["situation"] for u in a["units"]] == ["named", "shared_current"], "situation labels")
  need(a["units"][1]["situated"] == ["forall", "?:Sit", ["forall", "X", ["implies", ["has property", "whisked", "X", "?:Sit"],
                                                                                ["has property", "ready", "X", "?:Sit"]]]],
       "the situated view keeps quantifiers, signs and conditions: %r" % a["units"][1]["situated"])
  # the same implication without state_law is a description of W0, not a law
  a = compiled(["forall", "X", ["implies", ["has property", "whisked", "X"], ["has property", "ready", "X"]]])
  need(all(sit.situation_class(x) == "named" and sit.situation_of(x) == "W0" for c in lits(a, "S1") for x in c),
       "scope is not inferred from forall or implies")
  # static knowledge has no situation; static atoms inside an initial unit stay static
  a = compiled(["and", ["isa", "person", "Ann 1"], ["connected", "Haapsalu 7", "Tallinn 8", "bus"]],
               ["and", ["isa", "block", "a 3"], ["is rel2", "on", "a 3", "table 5"]])
  need(lits(a, "S1") == [[["isa", "person", "#:Ann 1"]], [["connected", "#:Haapsalu 7", "#:Tallinn 8", "bus"]]], "static: %r" % lits(a, "S1"))
  need([r["role"] for r in a["units"][1]["clauses"]] == ["static", "initial_fact"], "roles inside an initial unit")
  # negation: an explicit negative fact, and "nothing is on a"
  a = compiled(["not", ["has property", "dry", "a 3"]], ["not", ["exists", "X", ["is rel2", "on", "X", "a 3"]]])
  need(lits(a, "S1") == [[["-has property", "dry", "#:a 3", initial]]], "negative fact")
  need(lits(a, "S2") == [[["-is rel2", "on", "?:v_X", "#:a 3", initial]]], "negated existential: %r" % lits(a, "S2"))
  # the situation pass itself gives an effect law no clause; the effect pass does, and the query views stay pending
  a = compiled(["after", ["change", "Ann 1", "egg 2", "broken", "unspecified"], ["has property", "broken", "egg 2"]])
  need(sit.compile_unit(a["units"][0], sit.witness_namer(a["units"]))["clauses"] is None and a["pending_passes"] == [],
       "action laws stay outside the situation pass")
  need(sit.PASS in a["passes"] and sit.PASS not in a["pending_passes"], "pass bookkeeping")
  need(ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED, "a partly compiled source is not source_compiled")
  # the binder is in the view itself; a view with the binder removed is caught
  view = compiled(["state_law", ["has property", "red", "a 3"]])["units"][0]["situated"]
  need(view == ["forall", "?:Sit", ["has property", "red", "a 3", "?:Sit"]] and not sit.free_compiler_variables(view)
       and sit.free_compiler_variables(view[2]) == {"?:Sit"}, "situation binder: %r" % view)
  print("  scope: W0 in quantified and conditional descriptions; one shared situation in a standing law; static atoms unchanged")


def check_witnesses():
  law = ["state_law", ["implies", ["has property", "ready", "egg 2"],
                       ["exists", "U", ["and", ["have", "Ann 1", "U"], ["has property", "clean", "U"]]]]]
  r = sit.inspect(S(law))
  need(r["usable"] is False and r["witnesses"] == [{"variable": "U", "term": ["sk_U", "?:Sit"], "depends_on": ["?:Sit"]}], "sk(Sit): %r" % r["witnesses"])
  law2 = ["state_law", ["forall", "X", ["implies", ["and", ["isa", "block", "X"], ["has property", "ready", "X"]],
                                        ["exists", "U", ["and", ["have", "Ann 1", "U"], ["has property", "clean", "U"]]]]]]
  r = sit.inspect(S(law2))
  need(r["witnesses"][0]["term"] == ["sk_U", "?:Sit", "X"], "sk(Sit, X): %r" % r["witnesses"])
  need(["have", "#:Ann 1", ["sk_U", "?:Sit", "?:v_X"], "?:Sit", "?:Ctx"] in [erase(x) for c in r["clauses"] for x in c["clause"]], "the witness term in the clause")
  # the gold inspection expectations of x04, and no clause from compile_source for that unit
  n = 0
  for case in fm.load_all():
    for g in case["units"]:
      if "inspection" not in g:
        continue
      r = sit.inspect(g["stage2"])
      need(g["inspection"]["operation"] == r["operation"], "operation name")
      for p in g["inspection"].get("must_have", []):
        need(any(record_matches(p, x) for x in r["clauses"]), "%s/%s: inspection lacks %s" % (case["case"], g["id"], json.dumps(p)))
        n += 1
      for p in g["inspection"].get("must_not_have", []):
        need(not any(record_matches(p, x) for x in r["clauses"]), "%s/%s: inspection has %s" % (case["case"], g["id"], json.dumps(p)))
        n += 1
      a = gold_source(case)
      u = [x for x in a["units"] if x["id"] == g["id"]][0]
      need(u["status"] == "unsupported" and not u["clauses"] and a["clauses"] is None, "%s: an unsupported unit yields no usable clause" % case["case"])
  need(n >= 6, "the x04 inspection patterns were not found")
  # initial and static witnesses do not depend on a situation
  a = compiled(["exists", "W", ["and", ["isa", "whisk", "W"], ["have", "Ann 1", "W"]]], ["exists", "A", ["isa", "cook", "A"]],
               ["forall", "X", ["implies", ["isa", "block", "X"], ["exists", "Y", ["is rel2", "on", "X", "Y"]]]])
  need(a["units"][0]["witnesses"][0]["term"] == "sk_W" and a["units"][1]["witnesses"][0]["term"] == "sk_A", "constants")
  need(a["units"][2]["witnesses"][0]["term"] == ["sk_Y", "X"], "an initial witness under forall depends on X only: %r" % a["units"][2]["witnesses"])
  need(all(sit.SIT not in json.dumps(u["clauses"]) for u in a["units"]), "no situation variable in an initial description")
  # one variable name existential in two units: the witnesses differ
  a = compiled(["exists", "W", ["have", "Ann 1", "W"]], ["exists", "W", ["isa", "whisk", "W"]])
  need([u["witnesses"][0]["term"] for u in a["units"]] == ["sk_W_S1", "sk_W_S2"], "two witnesses must not share a name")
  # two sibling binders of one name in one unit are two objects (review R3)
  a = compiled(["and", ["exists", "X", ["has property", "red", "X"]], ["exists", "X", ["has property", "blue", "X"]]])
  terms = [w["term"] for w in a["units"][0]["witnesses"]]
  need(terms == ["sk_X_S1_1", "sk_X_S1_2"], "sibling binders: %r" % terms)
  need([c[0][2] for c in lits(a, "S1")] == terms, "each literal keeps its own witness: %r" % lits(a, "S1"))
  a = compiled(["and", ["exists", "X", ["has property", "red", "X"]], ["exists", "Y", ["has property", "blue", "Y"]]])
  need([w["term"] for w in a["units"][0]["witnesses"]] == ["sk_X", "sk_Y"], "different names keep the readable form")
  # a binder that negation turns existential is counted too
  a = compiled(["not", ["forall", "X", ["has property", "red", "X"]]], ["exists", "X", ["has property", "blue", "X"]])
  need([u["witnesses"][0]["term"] for u in a["units"]] == ["sk_X_S1", "sk_X_S2"], "not(forall) is an existential binder")
  # in a standing law (an unsupported head, so through the inspection operation) siblings differ and keep sk(Sit, X)
  r = sit.inspect(S(["state_law", ["forall", "X", ["implies", ["isa", "block", "X"],
                                                    ["and", ["exists", "U", ["have", "X", "U"]], ["exists", "U", ["is rel2", "on", "U", "X"]]]]]]))
  need([w["term"] for w in r["witnesses"]] == [["sk_U", "?:Sit", "X"], ["sk_U_2", "?:Sit", "X"]], "sibling standing witnesses: %r" % r["witnesses"])
  print("  witnesses: situations bound before Skolemization; %d gold inspection patterns; constants for initial and static existentials" % n)


def check_defaults():
  """normally is defeasibility; the scope still comes from the form (A3.2, review R1)."""
  initial = ["$ctxt", "present", "W0", "?:Fv1", "?:Fv2"]
  red0 = ["has property", "red", "#:egg 2", initial]
  red = ["has property", "red", "#:egg 2", "?:Sit", "?:Ctx"]
  cases = [
    ("a static default", ["normally", ["isa", "person", "Ann 1"]],
     [["isa", "person", "#:Ann 1"], ["$block", ["$", "$generic", 1], ["$not", ["isa", "person", "#:Ann 1"]]]], "static"),
    ("an initial default", ["normally", ["has property", "red", "egg 2"]],
     [red0, ["$block", ["$", "$generic", 1], ["$not", red0]]], "initial_fact"),
    ("a standing default", ["state_law", ["normally", ["has property", "red", "egg 2"]]],
     [red, ["$block", ["$", "$generic", 1], ["$not", red]]], "standing_law"),
    ("a negative initial default", ["normally", ["not", ["has property", "red", "egg 2"]]],
     [["-has property", "red", "#:egg 2", initial], ["$block", ["$", "$generic", 1], red0]], "initial_fact"),
    ("a conditional standing default",
     ["state_law", ["forall", "X", ["implies", ["and", ["isa", "block", "X"], ["has property", "whisked", "X"]], ["normally", ["has property", "ready", "X"]]]]],
     [["-isa", "block", "?:v_X"], ["-has property", "whisked", "?:v_X", "?:Sit", "?:Ctx"], ["has property", "ready", "?:v_X", "?:Sit", "?:Ctx"],
      ["$block", ["$", "block", 2], ["$not", ["has property", "ready", "?:v_X", "?:Sit", "?:Ctx"]]]], "standing_law"),
  ]
  for name, f, clause, role in cases:
    a = compiled(f)
    u = a["units"][0]
    need(u["status"] == "supported" and u["situated"] is not None and len(u["clauses"]) == 1, "%s: %s %r" % (name, u["status"], u["diagnostics"]))
    r = u["clauses"][0]
    need(erase(r["clause"]) == clause and r["role"] == role and r.get("defeasible") is True, "%s: %r" % (name, r))
    need("normally" not in json.dumps(r["clause"]), "%s: normally must not become a predicate" % name)
  # the ordinary clausifier gives the same blocker for the same default
  import lc_clausify
  ordinary = lc_clausify.clausify(["forall", "X", ["implies", ["isa", "bird", "X"], ["normally", ["isa", "flyer", "X"]]]])
  mine = lits(compiled(["forall", "X", ["implies", ["isa", "bird", "X"], ["normally", ["isa", "flyer", "X"]]]]), "S1")
  need(json.dumps(mine).replace("?:v_X", "?:X") == json.dumps(ordinary), "blocker encoding differs from the ordinary one: %r %r" % (mine, ordinary))
  # complex defaults: the ordinary push-inside rule, applied to the situated formula (review completion)
  X = "X"
  same = [["forall", X, ["normally", ["implies", ["isa", "bird", X], ["isa", "flyer", X]]]],
          ["forall", X, ["implies", ["isa", "bird", X], ["normally", ["exists", "Y", ["and", ["isa", "wing", "Y"], ["connected", X, "Y", "joint"]]]]]],
          ["forall", X, ["implies", ["and", ["isa", "bird", X], ["connected", X, X, "air"]], ["normally", ["isa", "flyer", X]]]],
          ["normally", ["and", ["isa", "person", "Ann 1"], ["isa", "cook", "Ann 1"]]],
          ["normally", ["exists", "Y", ["and", ["isa", "wing", "Y"], ["connected", "Ann 1", "Y", "joint"]]]],
          ["forall", X, ["implies", ["isa", "penguin", X], ["normally", ["not", ["isa", "flyer", X]]]]]]
  for f in same:
    a = compiled(f)
    need(a["units"][0]["status"] == "supported", "complex default %r: %r" % (f, a["units"][0]["diagnostics"]))
    import re
    skolem = lambda t: re.sub(r'"sk[0-9A-Za-z_]*"', '"SK"', t)      # Skolem symbols are named differently; nothing else may differ
    mine = skolem(json.dumps(lits(a, "S1")).replace("?:v_", "?:").replace("#:", ""))
    ordinary = [c if isinstance(c[0], list) else [c] for c in lc_clausify.clausify(f)]    # the ordinary output writes a unit clause bare
    need(mine == skolem(json.dumps(ordinary)), "complex default differs from the ordinary encoding:\n  %s\n  %s" % (mine, json.dumps(ordinary)))
  # the same rule in initial and standing scope: strict type conjunct, default last conjunct, witness before the default
  a = compiled(["normally", ["exists", "W", ["and", ["isa", "whisk", "W"], ["have", "Ann 1", "W"]]]],
               ["state_law", ["normally", ["forall", X, ["implies", ["and", ["isa", "block", X], ["has property", "whisked", X]],
                                                          ["and", ["has property", "ready", X], ["has property", "fine", X]]]]]])
  have = ["have", "#:Ann 1", "sk_W", initial]
  need(lits(a, "S1") == [[["isa", "whisk", "sk_W"]], [have, ["$block", ["$", "$generic", 1], ["$not", have]]]], "initial complex default: %r" % lits(a, "S1"))
  fine = ["has property", "fine", "?:v_X", "?:Sit", "?:Ctx"]
  cond = [["-isa", "block", "?:v_X"], ["-has property", "whisked", "?:v_X", "?:Sit", "?:Ctx"]]
  need(lits(a, "S2") == [cond + [["has property", "ready", "?:v_X", "?:Sit", "?:Ctx"]], cond + [fine, ["$block", ["$", "block", 2], ["$not", fine]]]],
       "standing complex default: %r" % lits(a, "S2"))
  need(not sit.free_compiler_variables(a["units"][1]["situated"]), "the situated view of a standing default binds ?:Sit")
  # these default forms stay unsupported: kept, named, blocking; never dropped
  bad = (("a negated default", ["not", ["normally", ["has property", "red", "egg 2"]]]),
         ("a disjunctive default", ["normally", ["or", ["has property", "red", "egg 2"], ["has property", "raw", "egg 2"]]]),
         ("a disjunctive default in a conclusion", ["implies", ["has property", "raw", "egg 2"], ["normally", ["or", ["has property", "red", "egg 2"], ["has property", "soft", "egg 2"]]]]),
         ("two defaults in one clause", ["or", ["normally", ["has property", "red", "egg 2"]], ["normally", ["has property", "raw", "egg 2"]]]),
         ("a default inside a default", ["normally", ["implies", ["has property", "raw", "egg 2"], ["normally", ["has property", "red", "egg 2"]]]]),
         ("a standing disjunctive default", ["state_law", ["normally", ["or", ["has property", "red", "egg 2"], ["has property", "raw", "egg 2"]]]]),
         ("a standing default inside a default", ["state_law", ["normally", ["implies", ["has property", "raw", "egg 2"], ["normally", ["has property", "red", "egg 2"]]]]]))
  for name, f in bad:
    a = compiled(f)
    u = a["units"][0]
    need(u["status"] == "unsupported" and [d["reason"] for d in u["diagnostics"]] == ["unsupported_default_form"]
         and u["clauses"] == [] and a["clauses"] is None and u["stage2"][2][2] == f, "%s: %s %r" % (name, u["status"], u["diagnostics"]))
    view = u["situated"]
    need(view is not None and not sit.free_compiler_variables(view) and "normally" in json.dumps(view)
         and ('"W0"' in json.dumps(view) or view[:2] == ["forall", sit.SIT]), "%s: the rejected unit must keep its situated view: %r" % (name, view))
  print("  defaults: literal and complex defaults (implies, and, exists, forall) compile in static, initial and standing scope with the "
        "ordinary $block encoding; %d other default forms are unsupported_default_form" % len(bad))


def check_mixed():
  on_table = ["is rel2", "on", "X", "table 5"]
  bad = [("a direct standing rule", ["state_law", ["forall", "X", ["implies", ["and", ["isa", "block", "X"], on_table], ["isa", "base", "X"]]]]),
         ("a direct initial rule", ["forall", "X", ["implies", on_table, ["isa", "base", "X"]]]),
         ("a route from a fluent", ["implies", ["has property", "open", "bridge 6"], ["connected", "Haapsalu 7", "Tallinn 8", "road"]]),
         ("a disjunction of a static atom and a fluent", ["or", ["isa", "base", "a 3"], ["has property", "red", "a 3"]]),
         ("a static atom from a negated fluent", ["forall", "X", ["implies", ["not", on_table], ["isa", "loose", "X"]]]),
         ("a negative type from a fluent", ["implies", ["has property", "red", "a 3"], ["not", ["isa", "food", "a 3"]]]),
         ("a negative route from a fluent", ["implies", ["has property", "open", "bridge 6"], ["not", ["connected", "Haapsalu 7", "Tallinn 8", "ferry"]]]),
         ("a negative type inside a conjunctive conclusion",
          ["forall", "X", ["implies", on_table, ["and", ["has property", "grounded", "X"], ["not", ["isa", "loose", "X"]]]]]),
         ("a default timeless conclusion", ["forall", "X", ["implies", on_table, ["normally", ["isa", "base", "X"]]]]),
         ("a nested implication", ["forall", "X", ["implies", on_table, ["implies", ["isa", "block", "X"], ["isa", "base", "X"]]]])]
  for name, f in bad:
    a = compiled(f)
    u = a["units"][0]
    need(u["status"] == "unsupported" and [d["reason"] for d in u["diagnostics"]] == ["mixed_scope_rule"] and u["clauses"] == []
         and u["situated"] is not None and a["clauses"] is None, "%s: %s %r" % (name, u["status"], u["diagnostics"]))
    q = ar.compile_query(["@id", "Q1", ["plan", ["has property", "red", "a 3"]]], a)
    need(q["outcome"]["reasons"] == ["mixed_scope_rule"], "%s: an attached query is unsupported" % name)
  # behind a computed helper: the helper law is fine, its static consumer is not
  a = compiled(["state_law", ["forall", "X", ["implies", on_table, ["has property", "grounded", "X"]]]],
               ["forall", "X", ["implies", ["has property", "grounded", "X"], ["isa", "base", "X"]]])
  need([u["status"] for u in a["units"]] == ["supported", "unsupported"], "helper path: %r" % [u["status"] for u in a["units"]])
  good = [("static to static", ["forall", "X", ["implies", ["isa", "block", "X"], ["isa", "solid", "X"]]]),
          ("fluent to fluent", ["state_law", ["forall", "X", ["implies", on_table, ["has property", "grounded", "X"]]]]),
          ("a static condition on a fluent", ["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "clear_top", "X"]]]),
          ("a negative static fact", ["not", ["isa", "hand", "Ann 1"]]),
          ("a negative static condition on a fluent", ["forall", "X", ["implies", ["not", ["isa", "block", "X"]], ["has property", "soft", "X"]]]),
          ("a static condition on a negative fluent", ["forall", "X", ["implies", ["isa", "block", "X"], ["not", ["has property", "soft", "X"]]]]),
          ("a static condition written as a disjunction", ["forall", "X", ["or", ["not", ["isa", "block", "X"]], ["has property", "clear_top", "X"]]]),
          ("negated implication: two facts", ["not", ["implies", ["has property", "red", "a 3"], ["isa", "food", "a 3"]]])]
  for name, f in good:
    need(compiled(f)["support"]["status"] == "supported", "%s must stay supported" % name)
  print("  mixed: %d dynamic-to-static forms and the helper path are mixed_scope_rule with no clause; %d controls stay supported" % (len(bad), len(good)))


def check_names():
  law = ["state_law", ["forall", "S", ["forall", "C", ["implies", ["and", ["isa", "block", "S"], ["is rel2", "on", "S", "C"]], ["has property", "held_up", "S"]]]]]
  a = compiled(law)
  need(lits(a, "S1") == [[["-isa", "block", "?:v_S"], ["-is rel2", "on", "?:v_S", "?:v_C", "?:Sit", "?:Ctx"],
                          ["has property", "held_up", "?:v_S", "?:Sit", "?:Ctx"]]], "source variables S and C: %r" % lits(a, "S1"))
  before = copy.deepcopy(law)
  sit.inspect(S(law))
  need(law == before, "the pass changed its input formula")
  a, b = compiled(law), compiled(law)
  need(ar.dumps(a) == ar.dumps(b), "two runs differ")
  print("  names: source variables S and C stay apart from ?:Sit and ?:Ctx; the input is unchanged; output is deterministic")


def check_vocabulary():
  """No ordinary rewrite ran: every clause predicate and value comes from the source unit or, in an executability
  path, from the applicability template the compiler instantiated (encoding v2)."""
  import re
  template_words = {w.lstrip("-") for t in ar._library()["templates"] for w in _strings(t["clause"]["@logic"])
                    if not w.startswith("?:")}
  fresh = re.compile(r"^\?:v_Z\d+$")
  n = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    a = gold_source(case)
    for u in a["units"]:
      words = set(_strings(u["stage2"])) | {v for v in (u.get("context") or {}).values() if v}
      for r in u["clauses"] or []:
        for lit in r["clause"]:
          name = lit[0].lstrip("-")
          internal = name in ("$block", "poss", "differ", "execution_denied") \
            or name in sit.MARKERS.values() \
            or name.startswith(sit.CHECK_PREFIX) \
            or (r.get("template") and name in template_words)     # compiler-internal names, template preconditions
          need(name in words or internal, "%s/%s: predicate %s is not in the source" % (case["case"], u["id"], name))
          for t in lit[1:]:
            for x in _strings(t):
              base = x[2:] if x.startswith("#:") else x[4:] if x.startswith("?:v_") else x
              ok = base in words or x in (sit.SIT, "$ctxt", "present", "past", "future", sit.FACT_L, sit.FACT_K,
                                          sit.OBJ, "$", "$not", "$generic", sit.DO) \
                or re.match(r"^\?:L(\d+|h)$", x) or (u.get("world") and x == u["world"]) \
                or x.startswith("sk_") or x.lstrip("-") in words \
                or (r.get("template") and (x in template_words or fresh.match(x) or x == "execution_denied")) \
                or x in ("?:v_P1", "?:v_P2", "?:v_P3", "?:v_P4")      # the slot variables of a general action pattern
              need(ok, "%s/%s: term %s is not in the source" % (case["case"], u["id"], x))
          n += 1
  a = compiled(["and", ["has property", "raw", "egg 2"], ["not", ["has property", "cooked", "egg 2"]]])
  need(lits(a, "S1")[1][0][:2] == ["-has property", "cooked"], "a result value was rewritten by an antonym rule")
  print("  passes: %d emitted literals use only their source unit's predicates and values" % n)


# ---------------------------------------------------------------------------
# contexts (migration steps 1b.2-1b.4)


def _atom_key(lit):
  return json.dumps([lit[0].lstrip("-")] + lit[1:-1])


def check_law_clause(where, rec):
  """The per-literal pattern and the agreement rule (migration plan sections 3 and 5) on one compiled law clause."""
  lits_ = [x for x in rec["clause"] if x[0] != "$block"]
  blocks = [x for x in rec["clause"] if x[0] == "$block"]
  seen = {}
  for x in lits_:
    if not sit.bears_situation(x[0].lstrip("-")):
      continue
    need(law_context(x[-1]), "%s: a law literal without the context $ctxt(present, ?:Wld, L, $obj): %r" % (where, x))
    loc = x[-1][3]
    successor = isinstance(sit.situation_of(x), list) and sit.situation_of(x)[:1] == [sit.DO]
    need((loc == sit.HEAD_L) == successor, "%s: ?:Lh marks exactly the successor literals: %r" % (where, x))
    need(seen.get(loc, _atom_key(x)) == _atom_key(x) or loc == sit.HEAD_L,
         "%s: two different atoms share the location variable %s: %r" % (where, loc, rec["clause"]))
    seen[loc] = _atom_key(x)
  for b in blocks:
    t = b[2][1] if b[2][0] == "$not" else b[2]
    if not sit.bears_situation(t[0].lstrip("-")):
      continue
    # a blocker repeats the literal it blocks, context included: the positive default head ($not), the negative
    # default head, or the concluded poss of a denial-marker blocker
    head = t if b[2][0] == "$not" else ["poss"] + t[1:] if t[0] == "execution_denied" else ["-" + t[0]] + t[1:]
    need(law_context(t[-1]) and head in lits_, "%s: a blocker does not repeat its head's context: %r" % (where, rec["clause"]))


def check_contexts():
  laws = facts = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    a = gold_source(case)
    for u in a["units"]:
      for r in u["clauses"] or []:
        w = "%s/%s" % (case["case"], u["id"])
        if r["role"] == "initial_fact":
          want = sit.fact_context(u["world"], u["context"])
          for x in r["clause"]:
            if sit.bears_situation(x[0].lstrip("-")):
              need(x[-1] == want and sit.situation_of(x) == u["world"],
                   "%s: a fact of %s has the context %r, want %r" % (w, u["world"], x[-1], want))
          facts += 1
        elif r["role"] not in ("static", "distinct"):
          check_law_clause(w, r)
          laws += 1
    for r in (a["restriction_clauses"] or []) + (a["policy_clauses"] or []):
      if any(sit.bears_situation(x[0].lstrip("-")) for x in r["clause"]):
        check_law_clause("%s/%s" % (case["case"], r["role"]), r)
        laws += 1
  # the qualifier policy on c35's variants (section 3): scope keeps the constant, provenance a variable, a knower its constant
  by = {c["case"]: c for c in fm.load_all()}
  def fact(case, unit):
    a = gold_source(by[case])
    u = [x for x in a["units"] if x["id"] == unit][0]
    return u, u["clauses"][0]["clause"][0]
  u, x = fact("c35_qualifier_policy:scope", "S4")
  need(x[-1] == ["$ctxt", "present", "W0", "#:hall 6", sit.FACT_K] and u["context"]["location_role"] == "scope", "scope: %r" % x)
  u, x = fact("c35_qualifier_policy:provenance", "S4")
  need(x[-1] == ["$ctxt", "present", "W0", sit.FACT_L, sit.FACT_K] and u["provenance_location"] == "hall 6",
       "provenance: the location leaves the term and stays in the unit record: %r %r" % (x, u["provenance_location"]))
  u, x = fact("c35_qualifier_policy:knower_objective", "S4")
  need(x[-1] == ["$ctxt", "present", "W0", sit.FACT_L, "#:Bob 7"], "knower: %r" % x)
  u, x = fact("c35_qualifier_policy:past_fact", "S4")
  need(x[-1] == ["$ctxt", "past", "W0", sit.FACT_L, sit.FACT_K], "tense: %r" % x)
  a = gold_source(by["c35_qualifier_policy:location_without_role"])
  need(a["support"]["status"] == "unsupported" and a["support"]["reasons"] == ["unsupported_contextual_location"]
       and a["support"]["unsupported_units"] == ["S3"], "a location without a role: %r" % a["support"])
  # a conditional initial description of W0 keeps W0 in every literal; a W1 fact has W1 (c31)
  a = gold_source(by["c31_two_world_scope:base"])
  s3 = [x for x in a["units"] if x["id"] == "S3"][0]
  need(s3["situation"] == "named" and all(sit.situation_of(y) == "W0" for c in s3["clauses"] for y in c["clause"]
                                       if sit.bears_situation(y[0].lstrip("-"))), "c31 S3: %r" % s3["clauses"])
  s4 = [x for x in a["units"] if x["id"] == "S4"][0]
  need(s4["situation"] == "named" and s4["clauses"][0]["clause"][0][-1] == ["$ctxt", "present", "W1", sit.FACT_L, sit.FACT_K],
       "c31 S4: %r" % s4["clauses"])
  law = [x for x in gold_source(by["c31_two_world_scope:standing_law"])["units"] if x["id"] == "S3"][0]
  need(law["situation"] == "shared_current" and all(law_context(y[-1]) for c in law["clauses"] for y in c["clause"]
                                                     if sit.bears_situation(y[0].lstrip("-"))), "c31 standing law: %r" % law["clauses"])
  # the source hash covers the worlds declaration and every context record (section 9)
  base = by["c35_qualifier_policy:objective_control"]
  h = gold_source(base)["hashes"]["source"]
  for name in ("provenance", "scope", "knower_objective", "past_fact"):
    need(gold_source(by["c35_qualifier_policy:" + name])["hashes"]["source"] != h, "%s: a qualifier does not change the source hash" % name)
  one = ar.compile_source(None, [S(["has property", "red", "a 3"])], la.PROFILE, None, ENTS)
  two = ar.compile_source(None, [S(["has property", "red", "a 3"])], la.PROFILE, None, ENTS, worlds=["W0", "W1"])
  need(one["hashes"]["source"] != two["hashes"]["source"], "the worlds declaration does not change the source hash")
  need(one["worlds"] == ["W0"] and two["worlds"] == ["W0", "W1"], "the artifact's worlds: %r %r" % (one["worlds"], two["worlds"]))
  print("  contexts: %d law clauses in the per-literal pattern with the agreement rule; %d facts in their world and record "
        "context; the qualifier variants of c35 and the worlds of c31 as specified" % (laws, facts))


def _strings(f):
  if isinstance(f, list):
    for x in f:
      for y in _strings(x):
        yield y
  elif isinstance(f, str):
    yield f


def run():
  check_gold()
  check_contexts()
  check_scope()
  check_witnesses()
  check_defaults()
  check_mixed()
  check_names()
  check_vocabulary()


if __name__ == "__main__":
  run()
