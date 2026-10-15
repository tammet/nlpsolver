"""WP06 unit checks, encoding v2: executability paths, denials, identity, source evidence.

No model, no GK.  The checks inspect the compiler's emitted clauses:

  gold         every gold clause pattern with the roles availability and
               denial, required or forbidden, and the distinctness patterns
  paths        a source rule becomes one poss path per template of its
               constructor, holding the rule's conditions, the template's
               preconditions and the hook; the stated-endpoint path (no
               connected literal) only for identified endpoints and means
               and a conditioned or named actor; no route_for, no helper, no
               can or action_available literal anywhere
  controls     missing permit, other actor, reversed route, alternative public
               route, alias, unknown identity: each has its own outcome
  permissions  strict and default kept as written; a default path is blocked
               by the denial marker; alternatives stay alternatives; a denial
               is the marker execution_denied(ACTION); effects and restrictions
               give no path
  uncertainty  every path of an uncertain unit holds its evidence 2p - 1; no
               helper clause and no shared_source_confidence requirement;
               numeric behavior on a backend is not claimed here
  identity     differ facts, both orders, for used declared ids only
  granularity  two places outside a declared flat set, and nested places
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
import lc_action_avail as av
import lc_action_library as lib
import lc_action_situate as sit
from check_action_situations import erase, law_context  # noqa: F401  (the exact expectations write a law context as ?:Ctx)

ROLES = ("availability", "denial")
OLD = ("can", "action_available", "capability_denied", "route_for")


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


# ---------------------------------------------------------------------------
# pattern matching with variable bindings (fixtures/README.md)


def term_matches(p, t, binding):
  if isinstance(p, list):
    if not isinstance(t, list) or len(p) != len(t):
      return False
    if p[0] in la.CONSTRUCTORS:
      return t[0] == p[0] and all(term_matches(a, b, binding) for a, b in zip(p[1:], t[1:]))
    return False
  if not isinstance(t, str):
    return False
  if la.is_var(p):
    if not t.startswith("?:") or t == sit.SIT:
      return False
    return binding.setdefault(p, t) == t
  if la.is_concrete(p):
    return t == "#:" + p
  return t == p


def literal_matches(p, lit, binding, negate=False):
  name = lit[0].lstrip("-")
  if name == "$block":
    return False
  args = lit[1:-1] if sit.bears_situation(name) else lit[1:]
  if "lit" in p:
    if p["lit"][0] != name or len(p["lit"]) - 1 != len(args):
      return False
    trial = dict(binding)
    if not all(term_matches(a, b, trial) for a, b in zip(p["lit"][1:], args)):
      return False
    binding.update(trial)
  if "sign" in p and (p["sign"] == "+") != ((not lit[0].startswith("-")) != negate):
    return False
  if "situation" in p and p["situation"] != sit.situation_class(lit):
    return False
  return True


def record_matches(p, rec):
  if p.get("role") not in ("*", rec["role"]):
    return False
  if "unit" in p and p["unit"] != rec["unit"]:
    return False
  for key in ("provenance", "defeasible", "strict", "confidence"):
    if key in p and p[key] != rec.get(key):
      return False
  if any(x[0].lstrip("-") in p.get("body_absent", []) for x in rec["clause"]):
    return False
  for head in rec["clause"]:
    binding = {}
    if not literal_matches(p, head, binding):
      continue
    rest = [x for x in rec["clause"] if x is not head and x[0] != "$block"]
    used, ok = [], True
    for b in p.get("body", []):
      hit = [x for x in rest if x not in used and literal_matches(b, x, dict(binding), negate=True)]
      if not hit:
        ok = False
        break
      literal_matches(b, hit[0], binding, negate=True)
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


def differ_pairs(a):
  return {(c["clause"][0][1], c["clause"][0][2]) for c in a["identity_clauses"]}


def check_gold():
  have = have_not = distinct = law_units = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    w = case["case"]
    a = gold_source(case)
    recs = records_of(a)
    pairs = differ_pairs(a)
    for u in a["units"]:
      if u["form"] in av.FORMS and u["status"] == "supported":
        law_units += 1
        need(u["clauses"], "%s/%s: a supported %s unit has no clause" % (w, u["id"], u["form"]))
        need(not sit.free_compiler_variables(u["situated"]) and not sit.free_source_variables(u["situated"])
             and u["situated"][:2] == ["forall", sit.SIT], "%s/%s: situated view" % (w, u["id"]))
        need(not any(lit[0].lstrip("-") in OLD for r in u["clauses"] for lit in r["clause"]),
             "%s/%s: a compiled clause holds can, action_available, capability_denied or route_for" % (w, u["id"]))
    for g in case["units"]:
      cl = g.get("clauses") or {}
      for key in ("must_have", "must_not_have"):
        for p in cl.get(key, []):
          if p.get("role") == "distinct":
            for x, y in p["pairs"]:
              both = ("#:" + x, "#:" + y) in pairs and ("#:" + y, "#:" + x) in pairs
              names = lambda i: (i, "#:" + i)      # a witness is written without the id prefix
              none = not any(pp[0] in names(x) + names(y) and pp[1] in names(x) + names(y) for pp in pairs)
              need(both if key == "must_have" else none, "%s/%s: distinct %s %s (%s)" % (w, g["id"], x, y, key))
            distinct += 1
          elif p.get("role") in ROLES:
            hit = [r for r in recs if record_matches(p, r)]
            if key == "must_have":
              need(hit, "%s/%s: no clause matches %s" % (w, g["id"], json.dumps(p)))
              have += 1
            else:
              need(not hit, "%s/%s: forbidden %s matches %r" % (w, g["id"], json.dumps(p), hit[:1]))
              have_not += 1
  print("  gold: %d required and %d forbidden path and denial patterns and %d distinctness patterns "
        "checked on %d compiled law units" % (have, have_not, distinct, law_units))


# ---------------------------------------------------------------------------

ENTS = {"Ann 1": "person", "Bob 2": "person", "Haapsalu 3": "place", "Tallinn 4": "place", "permit 5": "artifact",
        "egg 6": "food", "Robo 7": "robot", "Tartu 8": "place", "Estonia 9": "place", "a 10": "block", "b 11": "block"}
GO = ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "bus"]
PERMIT = ["have", "Ann 1", "permit 5"]
SC = ["?:Sit", "?:Ctx"]
TERM = ["move", "#:Ann 1", "#:Haapsalu 3", "#:Tallinn 4", "bus"]


def S(f, i="S1", p=None):
  pkg = ["holds", "W0", f]
  return ["@id", i, pkg if p is None else ["and", pkg, ["@p", i, p]]]


def compiled(*units, **kw):
  pkgs = [u if u[0] == "@id" else S(u, "S%d" % (i + 1)) for i, u in enumerate(units)]
  return ar.compile_source(None, pkgs, kw.get("profile", la.PROFILE), None, ENTS)


def clauses(a, unit, role=None):
  """The clauses of one unit, law contexts erased (`erase`)."""
  u = [x for x in a["units"] if x["id"] == unit][0]
  return [erase(r["clause"]) for r in u["clauses"] or [] if role in (None, r["role"])]


def templates(a, unit):
  u = [x for x in a["units"] if x["id"] == unit][0]
  return [r.get("template") for r in u["clauses"] or [] if r["role"] == "availability"]


def stated(c):
  return not any(x[0] == "-connected" for x in c)


def check_paths():
  a = compiled(["implies", PERMIT, ["can", "Ann 1", GO]])
  cond = ["-have", "#:Ann 1", "#:permit 5"] + SC
  want = [[cond, ["-is rel2", "located_at", "#:Ann 1", "#:Haapsalu 3"] + SC, ["-differ", "#:Haapsalu 3", "#:Tallinn 4"],
           ["-ok_move", TERM] + SC, ["poss", TERM] + SC]]
  need(clauses(a, "S1") == want, "a conditional rule with stated endpoints: %r" % clauses(a, "S1"))
  need(templates(a, "S1") == ["tpl_move_stated"] and all(r["provenance"] == "S1" for r in a["units"][0]["clauses"]),
       "template and provenance")
  public = [("fresh universal endpoints", ["forall", "F", ["forall", "T", ["can", "Ann 1", ["move", "Ann 1", "F", "T", "bus"]]]]),
            ("a fresh universal destination", ["forall", "T", ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "T", "bus"]]]),
            ("a fresh universal means", ["forall", "M", ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "M"]]]),
            ("a destination that only a negated condition mentions",
             ["forall", "T", ["implies", ["not", ["has property", "closed", "T"]], ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "T", "bus"]]]]),
            ("an unconditioned universal actor", ["forall", "X", ["can", "X", ["move", "X", "Haapsalu 3", "Tallinn 4", "bus"]]])]
  for name, f in public:
    a = compiled(f)
    need(a["units"][0]["status"] == "supported" and templates(a, "S1") == ["tpl_move_public"]
         and all(not stated(c) for c in clauses(a, "S1")), "%s must take the public path: %r" % (name, clauses(a, "S1")))
  routed = [("a destination bound by a positive condition",
             ["forall", "T", ["implies", ["and", ["isa", "city", "T"], ["has property", "open", "T"]], ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "T", "train"]]]],
             ["move", "#:Ann 1", "#:Haapsalu 3", "?:v_T", "train"]),
            ("a class of actors", ["forall", "X", ["implies", ["isa", "robot", "X"], ["can", "X", ["move", "X", "Haapsalu 3", "Tallinn 4", "shuttle"]]]],
             ["move", "?:v_X", "#:Haapsalu 3", "#:Tallinn 4", "shuttle"]),
            ("the unspecified means", ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "unspecified"]],
             ["move", "#:Ann 1", "#:Haapsalu 3", "#:Tallinn 4", "unspecified"])]
  for name, f, term in routed:
    a = compiled(f)
    cs = clauses(a, "S1")
    need(templates(a, "S1") == ["tpl_move_stated"] and len(cs) == 1 and stated(cs[0]) and cs[0][-1] == ["poss", term] + SC,
         "%s: %r" % (name, cs))
  # two rules in one unit: a stated path for the one that qualifies only
  a = compiled(["and", ["can", "Ann 1", GO], ["forall", "T", ["can", "Bob 2", ["move", "Bob 2", "Haapsalu 3", "T", "bus"]]]])
  need(sorted(templates(a, "S1")) == ["tpl_move_public", "tpl_move_stated"]
       and [c[-1][1][1] for c in clauses(a, "S1") if stated(c)] == ["#:Ann 1"], "paths per head")
  # direction: a stated path is one-way, like its source
  a = compiled(["can", "Ann 1", GO])
  need(not any(c[-1][1][3] == "#:Haapsalu 3" for c in clauses(a, "S1")), "no reverse path")
  # the other constructors: one template each, put_on two
  for act, want in ((["take", "Robo 7", "a 10"], ["tpl_take"]), (["put_on", "Robo 7", "a 10", "b 11"], ["tpl_put_on_block", "tpl_put_on_surface"]),
                    (["put_in", "Robo 7", "a 10", "b 11"], ["tpl_put_in"]),
                    (["change", "Ann 1", "egg 6", "broken", "unspecified"], ["tpl_change"])):
    a = compiled(["can", act[1], act])
    need(templates(a, "S1") == want, "%s: templates %r" % (act[0], templates(a, "S1")))
    tpl = [lib.literals(lib.template(ar._library(), t)["clause"]) for t in want]
    for c, t in zip(clauses(a, "S1"), tpl):
      need(len(c) == len(t) - 1 and c[-2][0] == "-ok_" + act[0] and c[-1][0] == "poss",   # $source: no condition here
           "%s: the path holds the template's preconditions and the hook: %r" % (act[0], c))
  # a template variable outside the action is a fresh universal of the path
  a = compiled(["can", "Robo 7", ["take", "Robo 7", "a 10"]])
  on = [x for x in clauses(a, "S1")[0] if x[0] == "-is rel2" and x[1] == "on"]
  need(len(on) == 1 and on[0][3].startswith("?:v_Z"), "take's support is a fresh variable: %r" % on)
  need(not sit.free_source_variables(a["units"][0]["situated"]), "the fresh support variable is bound in the situated view")
  print("  paths: one path per template; the stated-endpoint path for identified endpoints and a named or conditioned "
        "actor; %d forms take the public path, %d the stated one; put_on has two paths" % (len(public), len(routed)))


def check_branches():
  """Path qualification is local to a branch (review R1 of WP06)."""
  ann = lambda t, m="bus": ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", t, m]]
  bob = lambda t, m="train": ["can", "Bob 2", ["move", "Bob 2", "Haapsalu 3", t, m]]
  city = lambda t: ["isa", "city", t]
  port = lambda t: ["isa", "port", t]

  def routed(a):
    return sorted(c[-1][1][1] for c in clauses(a, "S1") if stated(c))

  def views_bound(a):
    for u in a["units"]:
      if u["situated"] is not None:
        need(not sit.free_compiler_variables(u["situated"]) and not sit.free_source_variables(u["situated"]),
             "a free variable in the situated view %r" % (u["situated"],))

  # 1. sibling quantifiers reuse T; only the conditioned head gets the stated path
  a = compiled(["and", ["forall", "T", ["implies", city("T"), ann("T")]], ["forall", "T", bob("T")]])
  need(a["support"]["status"] == "supported" and routed(a) == ["#:Ann 1"], "sibling T: %s" % routed(a))
  need(len(clauses(a, "S1", "availability")) == 2, "both rules keep a path")
  views_bound(a)
  a = compiled(["and", ["forall", "T", bob("T")], ["forall", "T", ["implies", city("T"), ann("T")]]])
  need(routed(a) == ["#:Ann 1"], "sibling T, other order: %s" % routed(a))
  a = compiled(["forall", "T", ["implies", city("T"), ["and", ann("T"), ["forall", "T", bob("T")]]]])
  need(a["units"][0]["status"] == "invalid" or routed(a) == ["#:Ann 1"], "a rebound name must not inherit the outer condition")
  # 2. distinct variables and conditions: no condition crosses between the branches
  a = compiled(["and", ["forall", "T", ["implies", city("T"), ann("T")]], ["forall", "U", ["implies", port("U"), bob("U")]]])
  need(routed(a) == ["#:Ann 1", "#:Bob 2"], "two conditioned branches: %s" % routed(a))
  for c in clauses(a, "S1"):
    text = json.dumps(c)
    need(("city" in text) == ("Ann 1" in text) and ("port" in text) == ("Bob 2" in text) and not ("city" in text and "port" in text),
         "a condition crossed between branches: %s" % text)
  views_bound(a)
  # 3. one shared antecedent with two heads keeps that antecedent on both
  a = compiled(["forall", "T", ["implies", city("T"), ["and", ann("T"), bob("T")]]])
  need(routed(a) == ["#:Ann 1", "#:Bob 2"] and all(c[0] == ["-isa", "city", "?:v_T"] for c in clauses(a, "S1")),
       "shared antecedent: %r" % clauses(a, "S1"))
  a = compiled(["forall", "T", ["forall", "M", ["implies", city("T"), ["and", ann("T", "M"), ["implies", ["standard_means", "M"], bob("T", "M")]]]]])
  need(a["units"][0]["status"] == "invalid" or routed(a) == ["#:Bob 2"], "nested condition")
  # 4. a certain multi-head unit stays supported; 5. an uncertain one is reported, with no clause
  two = ["and", ["forall", "T", ["implies", city("T"), ann("T")]], ["forall", "U", ["implies", port("U"), bob("U")]]]
  need(compiled(S(two, "S1", 1))["support"]["status"] == "supported", "a multi-head unit with probability 1")
  for f in (two, ["and", ["not", ann("Tallinn 4")], ["not", bob("Tallinn 4")]], ["forall", "T", ["implies", city("T"), ["and", ann("T"), bob("T")]]]):
    a = compiled(S(f, "S1", 0.8))
    u = a["units"][0]
    need(u["status"] == "unsupported" and [d["reason"] for d in u["diagnostics"]] == ["unsupported_confidence_form"] and u["clauses"] == []
         and a["clauses"] is None and u["stage2"][2][1][2] == f, "an uncertain multi-head unit: %s %r" % (u["status"], u["diagnostics"]))
  print("  branches: path qualification is branch-local; an uncertain unit with several can heads is unsupported_confidence_form")


def check_controls():
  by_case = {c["case"]: c for c in fm.load_all()}

  def case(name):
    return gold_source(by_case[name])

  # missing permit: the stated path exists but only under the permit, and no permit fact is compiled
  a = case("c06_scoped_route:missing_permit")
  r = [x for x in records_of(a) if x["role"] == "availability" and stated(x["clause"])]
  need(len(r) == 1 and r[0]["clause"][0][0] == "-have", "missing permit: the stated path keeps its condition")
  need(not any(x["clause"][0][0] == "have" for x in records_of(a) if x["role"] == "initial_fact"), "missing permit: no permit fact")
  # other actor: the stated path names Ann; no clause gives Bob or a variable actor that path
  a = case("c06_scoped_route:base")
  actors = {x["clause"][-1][1][1] for x in records_of(a) if x["role"] == "availability" and stated(x["clause"])}
  need(actors == {"#:Ann 1"}, "other actor: stated-path actors %s" % actors)
  # reversed route: the stated direction only
  a = case("p01_travel:reversed")
  conn = [x["clause"][0][1:] for x in records_of(a) if x["clause"][0][0] == "connected"]
  need(["#:Helsinki 4", "#:Tallinn 3", "ship"] in conn and ["#:Tallinn 3", "#:Helsinki 4", "ship"] not in conn, "reversed route: %r" % conn)
  # alternative public route: the public connection and the stated path are both there
  a = case("c06_scoped_route:public_route")
  need(any(x["clause"][0][0] == "connected" for x in records_of(a))
       and any(x["role"] == "availability" and stated(x["clause"]) for x in records_of(a)), "alternative public route")
  # alias: one id is one entity; two ids are two
  a = compiled(["and", ["isa", "person", "Ann 1"], ["is rel2", "located_at", "Ann 1", "Haapsalu 3"]], ["isa", "person", "Ann 1"])
  need(differ_pairs(a) == {("#:Ann 1", "#:Haapsalu 3"), ("#:Haapsalu 3", "#:Ann 1")}, "alias: %s" % sorted(differ_pairs(a)))
  # unknown identity: a witness is not declared distinct from anything
  a = case("c05_two_restrictions:existential_hand_only")
  need(not any("sk_" in x or "sk_" in y for x, y in differ_pairs(a)), "unknown identity: a witness got a differ fact")
  need(any(w["term"].startswith("sk_") for u in a["units"] for w in u["witnesses"]), "the control must have a witness")
  print("  controls: missing permit, other actor, reversed route, alternative public route, alias, unknown identity")


def check_permissions():
  a = compiled(["forall", "F", ["forall", "T", ["normally", ["can", "Ann 1", ["move", "Ann 1", "F", "T", "bus"]]]]],
               ["not", ["can", "Ann 1", GO]],
               ["forall", "X", ["implies", ["isa", "robot", "X"], ["can", "X", ["take", "X", "egg 6"]]]])
  r1, r2, r3 = [erase(a["units"][i]["clauses"]) for i in range(3)]
  poss = ["poss", ["move", "#:Ann 1", "?:v_F", "?:v_T", "bus"]] + SC
  block = [x for x in r1[0]["clause"] if x[0] == "$block"]
  need(len(r1) == 1 and r1[0]["defeasible"] and not r1[0]["strict"] and r1[0]["clause"][-2] == poss
       and block == [["$block", ["$", "$generic", 1], [av.MARKER, ["move", "#:Ann 1", "?:v_F", "?:v_T", "bus"]] + SC]],
       "a named actor does not make a default strict, and the default path is blocked by the denial marker: %r" % r1)
  need([x["clause"] for x in r2] == [[[av.MARKER, TERM] + SC]] and r2[0]["role"] == "denial" and r2[0]["strict"],
       "an explicit denial is the marker execution_denied(ACTION): %r" % r2)
  need(not any(lit[0].lstrip("-") in OLD for u in a["units"] for r in u["clauses"] for lit in r["clause"]),
       "a source unit compiles to poss paths and execution_denied, never to can, action_available or route_for")
  need(r3[0]["strict"] and not r3[0]["defeasible"], "a strict class law stays strict")
  # a default with stated endpoints: one default path, blocked by the marker
  a = compiled(["normally", ["can", "Ann 1", GO]])
  rs = erase(a["units"][0]["clauses"])
  need(len(rs) == 1 and rs[0]["defeasible"] and stated(rs[0]["clause"])
       and [x[2][0] for x in rs[0]["clause"] if x[0] == "$block"] == [av.MARKER], "a default stated path: %r" % rs)
  # a defeasible denial keeps the ordinary default blocker of its marker
  a = compiled(["normally", ["not", ["can", "Ann 1", GO]]])
  u = a["units"][0]
  need(u["status"] != "supported" or [x for x in erase(u["clauses"][0]["clause"]) if x[0] == "$block"][0][2] == ["$not", [av.MARKER, TERM] + SC],
       "a defeasible denial: %r" % u["clauses"])
  # alternatives stay alternatives: two units, two paths, no merge and no collision
  tick = lambda cls: ["forall", "X", ["implies", ["and", ["isa", "robot", "X"], ["exists", "Y", ["and", ["isa", cls, "Y"], ["have", "X", "Y"]]]],
                                       ["can", "X", ["move", "X", "Haapsalu 3", "Tallinn 4", "bus"]]]]
  a = compiled(tick("ticket"), tick("pass"))
  need(a["support"]["status"] == "supported" and [len(clauses(a, u, "availability")) for u in ("S1", "S2")] == [1, 1], "ticket or pass")
  need(all("?:v_Y" in json.dumps(c) and "sk_" not in json.dumps(c) for u in ("S1", "S2") for c in clauses(a, u)),
       "an existential in a condition is a universal of the clause, not a witness")
  # a conditional denial keeps its conditions
  a = compiled(["forall", "X", ["implies", ["and", ["isa", "person", "X"], ["not", ["has property", "licensed", "X"]]],
                                ["forall", "F", ["forall", "T", ["not", ["can", "X", ["move", "X", "F", "T", "bus"]]]]]]])
  need(clauses(a, "S1") == [[["-isa", "person", "?:v_X"], ["has property", "licensed", "?:v_X"] + SC,
                             [av.MARKER, ["move", "?:v_X", "?:v_F", "?:v_T", "bus"]] + SC]], "conditional denial: %r" % clauses(a, "S1"))
  # an effect or a restriction gives no path
  a = compiled(["after", ["change", "Ann 1", "egg 6", "broken", "unspecified"], ["has property", "broken", "egg 6"]],
               ["forall", "X", ["implies", ["executable", ["take", "Robo 7", "X"]], ["has property", "red", "X"]]])
  need(not any(r["role"] in ROLES for r in records_of(a)), "an effect or a restriction became a path")
  print("  permissions: default and strict as written; default paths blocked by execution_denied; explicit and conditional "
        "denials are the marker; alternatives kept apart; no path from an effect or a restriction")


def check_uncertainty():
  a = compiled(S(["can", "Robo 7", ["move", "Robo 7", "Haapsalu 3", "Tallinn 4", "bus"]], "S1", 0.8))
  u = a["units"][0]
  need([(r["role"], r.get("template"), r.get("confidence")) for r in u["clauses"]] == [("availability", "tpl_move_stated", 0.6)],
       "one uncertain stated path holds the evidence itself: %r" % u["clauses"])
  need(all(r["source_probability"] == 0.8 and r["provenance"] == "S1" for r in u["clauses"]), "source probability and provenance on every clause")
  need(u["requirements"] == [] and not u["compile_note"] and not any(r["role"] == "availability_source" for r in u["clauses"]),
       "no helper and no shared_source_confidence requirement")
  # put_on: two paths, each with the evidence; one application uses one of them
  a = compiled(S(["can", "Robo 7", ["put_on", "Robo 7", "a 10", "b 11"]], "S1", 0.8))
  need([(r.get("template"), r.get("confidence")) for r in a["units"][0]["clauses"]]
       == [("tpl_put_on_block", 0.6), ("tpl_put_on_surface", 0.6)] and a["units"][0]["requirements"] == [],
       "two paths of one uncertain put_on rule: %r" % a["units"][0]["clauses"])
  # a variable in the path keeps the evidence on the one path
  a = compiled(S(["forall", "T", ["implies", ["isa", "city", "T"], ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "T", "bus"]]]], "S1", 0.9))
  need([r.get("confidence") for r in a["units"][0]["clauses"]] == [0.8], "a path with a variable: %r" % a["units"][0]["clauses"])
  # a certain rule and an uncertain denial
  a = compiled(S(["can", "Ann 1", ["change", "Ann 1", "egg 6", "broken", "unspecified"]], "S1", 0.8),
               S(["not", ["can", "Ann 1", GO]], "S2", 0.9), S(["can", "Ann 1", GO], "S3", 1), S(["can", "Bob 2", ["move", "Bob 2", "Haapsalu 3", "Tallinn 4", "bus"]], "S4"))
  need([(r["role"], r.get("confidence")) for r in a["units"][0]["clauses"]] == [("availability", 0.6)], "single path")
  need([(r["role"], r.get("confidence")) for r in a["units"][1]["clauses"]] == [("denial", 0.8)], "uncertain denial")
  for i in (2, 3):
    need(all("confidence" not in r for r in a["units"][i]["clauses"]) and not a["units"][i]["requirements"],
         "a certain source has no confidence")
  # default and uncertain: a default path with the evidence
  a = compiled(S(["normally", ["can", "Ann 1", GO]], "S1", 0.8))
  rs = a["units"][0]["clauses"]
  need([(r["defeasible"], r.get("confidence")) for r in rs] == [(True, 0.6)], "default and uncertain: %r" % rs)
  # a probably-false or uninformative law is kept and reported, not negated
  for p in (0.5, 0.3):
    a = compiled(S(["can", "Ann 1", GO], "S1", p))
    u = a["units"][0]
    need(u["status"] == "unsupported" and [d["reason"] for d in u["diagnostics"]] == ["unsupported_confidence_form"] and u["clauses"] == []
         and a["clauses"] is None, "probability %s: %r" % (p, u["diagnostics"]))
  # an uncertain state description uses the ordinary convention and distribution
  at = ["is rel2", "located_at", "Ann 1", "Tallinn 4"]
  a = compiled(S(at, "S1", 0.8), S(["exists", "W", ["and", ["isa", "whisk", "W"], ["have", "Ann 1", "W"]]], "S2", 0.8), S(at, "S3", 1), S(at, "S4", 0.2))
  need([r.get("confidence") for r in a["units"][0]["clauses"]] == [0.6], "an uncertain fact: %r" % a["units"][0]["clauses"])
  need([r.get("confidence") for r in a["units"][1]["clauses"]] == [0.7746, 0.7746], "two anchor clauses share the evidence: their product is 0.6")
  need(all("confidence" not in r for r in a["units"][2]["clauses"]), "probability 1 has no confidence")
  need([d["reason"] for d in a["units"][3]["diagnostics"]] == ["unsupported_confidence_form"], "a probably-false description")
  print("  uncertainty: every path of an uncertain unit holds 2p - 1; no helper, no shared_source_confidence; "
        "p <= 0.5 is unsupported_confidence_form")


def check_identity():
  a = compiled(["and", ["isa", "person", "Ann 1"], ["is rel2", "located_at", "Ann 1", "Haapsalu 3"]],
               ["connected", "Haapsalu 3", "Tallinn 4", "bus"], ["exists", "W", ["have", "Ann 1", "W"]])
  pairs = differ_pairs(a)
  ids = ["#:Ann 1", "#:Haapsalu 3", "#:Tallinn 4"]
  need(pairs == {(x, y) for x in ids for y in ids if x != y}, "differ: %s" % sorted(pairs))
  need(all(c["role"] == "distinct" and c["unit"] is None and len(c["clause"]) == 1 for c in a["identity_clauses"]), "identity clause records")
  need(a["clauses"][-len(pairs):] == a["identity_clauses"], "identity clauses are part of the artifact clause list")
  need(not any("bus" in x or "sk_" in x or "Bob" in x for p in pairs for x in p), "no fact for a lexical value, a witness or an unused id")
  b = compiled(["isa", "person", "Ann 1"], profile=la.ORDINARY)
  need(b["identity_clauses"] == [], "the ordinary profile gets no differ fact")
  print("  identity: %d differ facts, both orders, for the used declared ids; none for a lexical value, a witness or an unused id" % len(pairs))


def check_granularity():
  at = lambda x, p: ["is rel2", "located_at", x, p]
  a = compiled(at("Ann 1", "Tallinn 4"), at("Ann 1", "Tartu 8"))
  need(ar.source_outcome(a) == {"outcome": "unsupported_translation", "reasons": ["unsupported_location_granularity"], "units": ["S1", "S2"]}
       and a["clauses"] is None and all(u["status"] == "supported" for u in a["units"]), "two undeclared places: %r" % ar.source_outcome(a))
  flat = {"name": la.PROFILE, "locations": {"flat": ["Tallinn 4", "Tartu 8"]}}
  a = compiled(at("Ann 1", "Tallinn 4"), at("Ann 1", "Tartu 8"), profile=flat)
  need(a["support"]["status"] == "supported", "inside the declared flat set two places are a conflict for the replay, not a granularity defect")
  a = compiled(at("Ann 1", "Tallinn 4"), at("Ann 1", "Estonia 9"), profile={"name": la.PROFILE, "locations": {"flat": ["Tallinn 4", "Tartu 8"]}})
  need(a["support"]["reasons"] == ["unsupported_location_granularity"], "one place outside the flat set")
  a = compiled(at("Ann 1", "Tallinn 4"), at("Tallinn 4", "Estonia 9"))
  need(a["units"][1]["status"] == "unsupported" and a["units"][1]["clauses"] == [] and a["support"]["units"] == ["S2"], "a place located in a place")
  for ok in ([at("Ann 1", "Tallinn 4"), at("Bob 2", "Estonia 9")], [at("Ann 1", "Tallinn 4"), at("Ann 1", "Tallinn 4")],
             [at("Ann 1", "Tallinn 4"), ["not", at("Ann 1", "Tartu 8")]]):
    need(compiled(*ok)["support"]["status"] == "supported", "%r must stay supported" % (ok,))
  c24 = [c for c in fm.load_all() if c["case"] == "c24_nested_places:base"][0]
  o = ar.source_outcome(gold_source(c24))
  need(o == {"outcome": "unsupported_translation", "reasons": ["unsupported_location_granularity"], "units": ["S2", "S3", "S4"]}
       and [q["expect"]["units"] for q in c24["queries"]] == [["S2", "S3", "S4"]], "c24 base attribution: %r" % o)
  q = ar.compile_query(["@id", "Q1", ["plan", at("Ann 1", "Tartu 8")]], compiled(at("Ann 1", "Tallinn 4"), at("Ann 1", "Tartu 8")))
  need(q["outcome"]["outcome"] == "unsupported_translation", "an attached query is unsupported")
  # facts are grouped by entity and world (migration step 1b.6): two worlds, two facts
  two = ar.compile_source(None, [S(at("Ann 1", "Tallinn 4")), ["@id", "S2", ["holds", "W1", at("Ann 1", "Tartu 8")]]],
                          la.PROFILE, None, ENTS, worlds=["W0", "W1"])
  need(two["support"]["status"] == "supported", "one entity at two places in two worlds: %r" % two["support"])
  one = ar.compile_source(None, [["@id", "S1", ["holds", "W1", at("Ann 1", "Tallinn 4")]], ["@id", "S2", ["holds", "W1", at("Ann 1", "Tartu 8")]]],
                          la.PROFILE, None, ENTS, worlds=["W0", "W1"])
  need(one["support"]["reasons"] == ["unsupported_location_granularity"], "two places in one world W1: %r" % one["support"])
  c33 = [c for c in fm.load_all() if c["case"] == "c33_root_selection:base"][0]
  need(gold_source(c33)["support"]["status"] == "supported", "c33: Ann in Haapsalu at W0 and in Tallinn at W1 is supported")
  # E1 (repair round): in between two declared places states a place inside a place, as located_at does
  inside = lambda x, p: ["is rel2", "in", x, p]
  a = compiled(at("Ann 1", "Tallinn 4"), inside("Tallinn 4", "Estonia 9"))
  need(a["units"][1]["status"] == "unsupported" and a["support"]["reasons"] == ["unsupported_location_granularity"]
       and a["support"]["units"] == ["S2"] and "both places" in a["units"][1]["diagnostics"][0]["message"],
       "a positive in between two places: %r" % a["support"])
  for label, ok in (("negated", [["not", inside("Tallinn 4", "Estonia 9")]]),
                    ("conditional", [["implies", ["isa", "person", "Ann 1"], inside("Tallinn 4", "Estonia 9")]]),
                    ("law", [["state_law", ["forall", "X", ["implies", ["isa", "person", "X"],
                                                              inside("Tallinn 4", "Estonia 9")]]]])):
    r = compiled(*ok)["support"]
    need("unsupported_location_granularity" not in r["reasons"], "%s in is not an asserted nesting: %r" % (label, r))
  box = dict(ENTS, **{"box 12": "box"})
  a = ar.compile_source(None, [S(inside("permit 5", "box 12"))], la.PROFILE, None, box)
  need(a["support"]["status"] == "supported", "an object in a container stays supported: %r" % a["support"])
  a = ar.compile_source(None, [S(at("Ann 1", "Tallinn 4")), ["@id", "S2", ["holds", "W1", inside("Tallinn 4", "Estonia 9")]]],
                        la.PROFILE, None, ENTS, worlds=["W0", "W1"])
  need(a["support"]["units"] == ["S2"] and a["support"]["reasons"] == ["unsupported_location_granularity"],
       "the nesting fact of W1: %r" % a["support"])
  print("  granularity: two places outside a declared flat set and nested places (located_at, or in between two declared "
        "places) are unsupported_location_granularity; negated, conditional and law in, an object in a container and "
        "3 other controls stay free of it; facts of two worlds are grouped apart")


def check_determinism():
  f = S(["forall", "T", ["implies", ["isa", "city", "T"], ["normally", ["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "T", "bus"]]]]], "S1", 0.8)
  before = copy.deepcopy(f)
  a, b = compiled(f), compiled(f)
  need(ar.dumps(a) == ar.dumps(b) and f == before, "two runs differ or the input changed")
  need(av.PASS in a["passes"] and a["pending_passes"] == [] and ar.source_outcome(a)["outcome"] == "source_compiled"
       and ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED,
       "pass bookkeeping: %r" % a["pending_passes"])
  print("  determinism: identical bytes on two runs; the input is unchanged; no pass pending")


def run():
  check_gold()
  check_paths()
  check_branches()
  check_controls()
  check_permissions()
  check_uncertainty()
  check_identity()
  check_granularity()
  check_determinism()


if __name__ == "__main__":
  run()
