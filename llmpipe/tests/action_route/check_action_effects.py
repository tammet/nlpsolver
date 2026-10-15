"""WP08 unit checks: text effects, markers, state policy, dependencies.

No model, no GK.  Clause inspection, plus the test-only derivation of
`check_action_restrictions`, here over the verify view with one action step.
The derivation is a test tool; it says nothing about what GK proves.

  gold          effect, marker and derived_no_inertia patterns, required and
                forbidden; the compile expectation of every effect and
                standing-law unit
  bindings      the exact clauses of a conditional two-literal effect: old-
                state condition, poss, successor head, marker under the same
                body; variables shared between action, condition and head
  one step      after one action: a positive and a negative write, a blocked
                frame, an unrelated fact kept, a condition read in the old
                state, no availability from an effect
  policy        computed, stored, declared, ambiguous; stored physical state
                in a law head
  licence       a real licence-granting write against a source that only
                reads the negative licence fact
  transport     the per-query transport diagnostic
  conflicts     a text write against a library write of the opposite sign
  metadata      always present; no option removes it
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
import fixture_materialize as fm
import lc_action as la
import lc_action_effects as ef
import lc_action_library as lib
import lc_action_situate as sit

need = cav.need
SC = ["?:Sit", "?:Ctx"]


def with_pending(a, name="a_later_pass"):
  """A copy of a source artifact that names one more pending pass, rehashed."""
  b = copy.deepcopy(a)
  b["pending_passes"].append(name)
  b["hashes"] = ar.source_hashes(b)
  return b


def all_records(a):
  return cav.records_of(a) + a["restriction_clauses"] + a["policy_clauses"]


def _poss_term(rec):
  hit = [x for x in rec["clause"] if x[0] == "-poss"]
  return hit[0][1] if hit else None


def effect_matches(p, rec, recs):
  if not cav.record_matches({k: v for k, v in p.items() if k not in ("action", "marker")}, rec):
    return False
  if "action" in p and not (_poss_term(rec) and cav.term_matches(p["action"], _poss_term(rec), {})):
    return False
  if p.get("marker"):
    head = [x for x in rec["clause"] if sit.situation_class(x) == "successor"][0]
    want = [sit.MARKERS[head[0].lstrip("-")]] + head[1:]
    body = sorted(json.dumps(x) for x in rec["clause"] if x is not head)
    if not any(r["role"] == "marker" and r["unit"] == rec["unit"] and want in r["clause"]
               and sorted(json.dumps(x) for x in r["clause"] if x != want) == body for r in recs):
      return False
  return True


def check_gold():
  have = have_not = units = 0
  for case in fm.load_all():
    prof = case["profile"]["name"] if isinstance(case["profile"], dict) else case["profile"]
    if prof != la.PROFILE or not case["units"]:
      continue
    w = case["case"]
    a = cav.gold_source(case)
    recs = all_records(a)
    for g in case["units"]:
      u = [x for x in a["units"] if x["id"] == g["id"]][0]
      if u["form"] in ("effect", "state_law"):
        units += 1
        if g["compile"] == "supported":
          need(u["status"] == "supported" and u["clauses"], "%s/%s: %r" % (w, g["id"], u["diagnostics"]))
          need(not sit.free_compiler_variables(u["situated"]) and not sit.free_source_variables(u["situated"]),
               "%s/%s: situated view" % (w, g["id"]))
        else:
          need(u["status"] == "unsupported" and not u["clauses"]
               and g["compile"]["unsupported"] in [d.get("reason") for d in u["diagnostics"]], "%s/%s: %r" % (w, g["id"], u["diagnostics"]))
      cl = g.get("clauses") or {}
      for key in ("must_have", "must_not_have"):
        for p in cl.get(key, []):
          if p.get("role") not in ("effect", "marker", "derived_no_inertia", "frame") or p.get("unit") == "library":
            continue
          if p["role"] in ("effect", "marker"):
            hit = [r for r in recs if r["role"] == p["role"] and effect_matches(p, r, recs)]
          else:
            hit = [r for r in recs if cav.record_matches(p, r)]
          if key == "must_have":
            need(hit, "%s/%s: no clause matches %s" % (w, g["id"], json.dumps(p)))
            have += 1
          else:
            need(not hit, "%s/%s: forbidden %s matches %r" % (w, g["id"], json.dumps(p), hit[:1]))
            have_not += 1
  need(have and have_not, "no gold effect pattern was checked")
  print("  gold: %d required and %d forbidden effect, marker and policy patterns; %d effect and standing-law units agree"
        % (have, have_not, units))


# ---------------------------------------------------------------------------

ENTS = {"Ann 1": "person", "lamp 2": "artifact", "switch 3": "artifact", "cup 4": "artifact", "egg 5": "food",
        "hand 6": "hand", "a 7": "block", "table 8": "table", "Tom 9": "person", "key 10": "artifact",
        "hall 11": "place", "garden 12": "place", "bowl 13": "artifact", "Haapsalu 14": "place", "Tallinn 15": "place"}
PRESS = ["change", "Ann 1", "switch 3", "pressed", "unspecified"]
OFF, ON = ["has property", "off", "lamp 2"], ["has property", "on", "lamp 2"]
NOT = lambda f: ["not", f]
TOGGLE_ON = ["implies", OFF, ["after", PRESS, ["and", ON, NOT(OFF)]]]
TOGGLE_OFF = ["implies", ON, ["after", PRESS, ["and", OFF, NOT(ON)]]]


def compiled(*units, **kw):
  pkgs = [cav.S(u, "S%d" % (i + 1)) if u[0] != "@id" else u for i, u in enumerate(units)]
  return ar.compile_source(None, pkgs, kw.get("profile", la.PROFILE), None, ENTS)


def unit(a, i):
  return [u for u in a["units"] if u["id"] == i][0]


def check_bindings():
  a = compiled(TOGGLE_ON)
  press = ["change", "#:Ann 1", "#:switch 3", "pressed", "unspecified"]
  succ = ["$do", press, "?:Sit"]
  body = [["-has property", "off", "#:lamp 2"] + SC, ["-poss", press] + SC]
  got = {r["role"] + ":" + r["clause"][-1][0]: cav.erase(r["clause"]) for r in unit(a, "S1")["clauses"]}
  need(got == {"effect:has property": body + [["has property", "on", "#:lamp 2", succ, "?:Ctx"]],
               "effect:-has property": body + [["-has property", "off", "#:lamp 2", succ, "?:Ctx"]],
               "marker:changed_property": body + [["changed_property", "off", "#:lamp 2", succ, "?:Ctx"]]},
       "the clauses of a conditional effect: %r" % got)
  need(all(r["conditional"] and r["strict"] and r["action"] == PRESS for r in unit(a, "S1")["clauses"]), "effect record fields")
  # an unconditional write: the marker needs poss and nothing else
  a = compiled(["after", PRESS, NOT(OFF)])
  m = [cav.erase(r["clause"]) for r in unit(a, "S1")["clauses"] if r["role"] == "marker"]
  need(m == [[["-poss", press] + SC, ["changed_property", "off", "#:lamp 2", succ, "?:Ctx"]]], "unconditional marker: %r" % m)
  # variables: one X in the action, the condition and the head; the head's own variable stays universal
  f = ["forall", "X", ["forall", "Y", ["implies", ["and", ["isa", "block", "X"], ["is rel2", "on", "X", "Y"]],
                                       ["after", ["take", "hand 6", "X"], NOT(["is rel2", "on", "X", "Y"])]]]]
  a = compiled(f)
  take = ["take", "#:hand 6", "?:v_X"]
  e = [cav.erase(r["clause"]) for r in unit(a, "S1")["clauses"] if r["role"] == "effect"]
  need(e == [[["-isa", "block", "?:v_X"], ["-is rel2", "on", "?:v_X", "?:v_Y"] + SC, ["-poss", take] + SC,
              ["-is rel2", "on", "?:v_X", "?:v_Y", ["$do", take, "?:Sit"], "?:Ctx"]]], "variable bindings: %r" % e)
  # an existential in the condition is a universal of the clause, not a witness
  f = ["forall", "X", ["implies", ["exists", "Y", ["is rel2", "on", "X", "Y"]], ["after", ["take", "hand 6", "X"], ["has property", "lifted", "X"]]]]
  a = compiled(f)
  need("sk_" not in json.dumps(unit(a, "S1")["clauses"]) and not unit(a, "S1")["witnesses"], "a condition existential became a witness")
  # no effect clause concludes can or poss; every effect and marker reads poss once
  for r in all_records(compiled(TOGGLE_ON, TOGGLE_OFF)):
    if r["pass"] == ef.PASS and r["role"] in ("effect", "marker"):
      names = [x[0] for x in r["clause"]]
      need(names.count("-poss") == 1 and "poss" not in names and "can" not in names, "an effect clause: %r" % r["clause"])
  print("  bindings: old-state condition, poss, successor head; a negative write has its marker under the same body; "
        "no effect concludes can or poss")


def one_step(a, depth=1):
  need(a["support"]["status"] == "supported", "unsupported: %r" % a["support"])
  view = ar.library_view(a, "verify", sorted(a["restrictions"]["constructors"]))
  return crs.saturate([r["clause"] for r in a["clauses"]] + [lib.literals(r["clause"]) for r in view], depth)


def after(facts, action, atom, sign="+"):
  act = sit._term(action, set())
  lit = [("-" if sign == "-" else "") + atom[0]] + [sit._term(t, set()) for t in atom[1:]] + [crs.at(["$do", act, "W0"])]
  return crs.holds(facts, lit)


def check_one_step():
  can = ["can", "Ann 1", PRESS]
  polish = ["change", "Ann 1", "cup 4", "polished", "unspecified"]
  a = compiled(OFF, ["has property", "blue", "cup 4"], NOT(["has property", "wet", "cup 4"]), can, TOGGLE_ON, TOGGLE_OFF)
  f = one_step(a)
  need(after(f, PRESS, ON) and after(f, PRESS, OFF, "-"), "the press writes on and not off")
  need(not after(f, PRESS, OFF) and not after(f, PRESS, ON, "-"), "the old value persisted past its marker, or the other branch applied")
  need(after(f, PRESS, ["has property", "blue", "cup 4"]), "an unrelated positive fact is kept")
  need(after(f, PRESS, ["has property", "pressed", "switch 3"]), "the library write of change")
  # the library has no negative frame: the declared semantics keeps the negative, this backend view does not derive it
  need(not after(f, PRESS, ["has property", "wet", "cup 4"], "-"), "a negative persisted without a negative frame")
  need(a["backend_requirements"] == {}, "no dynamic negative is read, so nothing is required: %r" % a["backend_requirements"])
  # an effect supplies no availability
  b = compiled(OFF, TOGGLE_ON)
  g = one_step(b)
  need(crs.executable(b, PRESS, g) == "Unknown" and not after(g, PRESS, ON), "an effect made its action available")
  # the condition is read in the old state: with on and off both unknown nothing is written
  c = compiled(can, TOGGLE_ON, TOGGLE_OFF)
  need(not after(one_step(c), PRESS, ON) and not after(one_step(c), PRESS, OFF), "a conditional effect applied without its condition")
  # a second action is unaffected by the first action's marker
  d = compiled(OFF, can, ["can", "Ann 1", polish], TOGGLE_ON)
  need(after(one_step(d), polish, OFF) and not after(one_step(d), polish, ON), "the marker of press blocked the frame of polish")
  print("  one step: positive and negative write, blocked frame, kept facts, old-state condition, no availability from an effect; "
        "a stated negative is not derived in the successor by this library")


def check_policy():
  law = ["state_law", ["implies", ["has property", "washed", "bowl 13"], ["has property", "clean", "bowl 13"]]]
  clean = ["has property", "clean", "bowl 13"]
  wash = ["can", "Ann 1", ["change", "Ann 1", "bowl 13", "clean", "unspecified"]]
  text = ["after", ["change", "Ann 1", "bowl 13", "scrubbed", "unspecified"], clean]
  derived = lambda a: [r["clause"] for r in a["policy_clauses"]]
  a = compiled(law)
  need(derived(a) == [[["derived_property", "clean"]]] and a["dependencies"]["properties"]["clean"]["policy"] == "computed", "law only")
  for name, extra in (("initial assertion", clean), ("negative initial assertion", NOT(clean)), ("change term", wash), ("text effect", text)):
    a = compiled(law, extra)
    need(a["support"]["reasons"] == ["ambiguous_state_policy"] and a["support"]["unsupported_units"] == ["S1"]
         and not derived(a) and a["clauses"] is None, "%s: %r" % (name, a["support"]))
  for policy, want in (({"computed": ["clean"]}, [[["derived_property", "clean"]]]), ({"stored": ["clean"]}, [])):
    a = compiled(law, clean, profile={"name": la.PROFILE, "policy": policy})
    need(a["support"]["status"] == "supported" and derived(a) == want, "declared %r: %r" % (policy, derived(a)))
  # a condition that only reads the property is no assertion
  a = compiled(law, ["implies", clean, ["has property", "usable", "bowl 13"]])
  need(a["support"]["status"] == "supported" and derived(a) == [[["derived_property", "clean"]]], "a read is not an assertion")
  # an initial conditional description is no law: its head gets no derived_property
  a = compiled(["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "red", "X"]]])
  need(derived(a) == [] and a["dependencies"]["properties"] == {}, "an initial description is not a standing law")
  for head in (["has property", "clear_top", "a 7"], ["has property", "empty", "hand 6"], ["is rel2", "on", "a 7", "table 8"],
               ["have", "Ann 1", "cup 4"], NOT(["is rel2", "holding", "hand 6", "a 7"])):
    a = compiled(["state_law", ["implies", ["isa", "block", "a 7"], head]])
    need(a["support"]["reasons"] == ["unsupported_stored_state_law"] and not unit(a, "S1")["clauses"], "stored head %r: %r" % (head, a["support"]))
  # no implicit exclusivity: cooked does not delete raw, on does not delete off
  a = compiled(["has property", "raw", "egg 5"], ["can", "Ann 1", ["change", "Ann 1", "egg 5", "cooked", "unspecified"]])
  cook = ["change", "Ann 1", "egg 5", "cooked", "unspecified"]
  f = one_step(a)
  need(after(f, cook, ["has property", "cooked", "egg 5"]) and after(f, cook, ["has property", "raw", "egg 5"])
       and not [w for w in a["dependencies"]["writes"]], "change removed another property value")
  print("  policy: law-only computed; declared computed and stored; an initial assertion, a change term or a text effect makes "
        "it ambiguous; stored physical heads are unsupported; change deletes nothing")


def check_licence():
  world = [["isa", "person", "Ann 1"], NOT(["has property", "licensed", "Ann 1"]),
           ["forall", "X", ["forall", "F", ["forall", "T", ["implies", ["and", ["isa", "person", "X"], NOT(["has property", "licensed", "X"])],
                                                            NOT(["can", "X", ["move", "X", "F", "T", "bus"]])]]]]]
  polish = ["can", "Ann 1", ["change", "Ann 1", "cup 4", "polished", "unspecified"]]
  grant = ["can", "Ann 1", ["change", "Ann 1", "Ann 1", "licensed", "unspecified"]]
  text_grant = ["after", ["change", "Ann 1", "cup 4", "polished", "unspecified"], ["has property", "licensed", "Ann 1"]]
  rows = {}
  for name, extra in (("polish", [polish]), ("grant", [grant]), ("text", [polish, text_grant])):
    a = compiled(*(world + extra))
    reads = a["dependencies"]["dynamic_negative_reads"]
    need(len(reads) == 1 and reads[0]["unit"] == "S3" and reads[0]["through"] == "defeater"
         and a["backend_requirements"]["negative_persistence"]["units"] == ["S3"], "%s: %r" % (name, reads))
    rows[name] = reads[0]["positive_writers"]
  need(rows == {"polish": [], "grant": ["S4"], "text": ["S5"]}, "who grants the licence: %r" % rows)
  # the requirement is potential: a source with a negative in the initial state only, read by nothing, requires nothing
  a = compiled(world[0], world[1], polish)
  need(a["backend_requirements"] == {} and a["dependencies"]["dynamic_negative_reads"] == [], "an unread negative requires nothing")
  # indirect reads: a restriction's negative requirement and a standing law's negative body
  a = compiled(["forall", "X", ["implies", ["executable", ["take", "hand 6", "X"]], NOT(["has property", "heavy", "X"])]],
               ["state_law", ["forall", "X", ["implies", NOT(["has property", "wet", "X"]), ["has property", "ready", "X"]]]])
  need(sorted((r["unit"], r["literal"][1]) for r in a["dependencies"]["dynamic_negative_reads"]) == [("S1", "heavy"), ("S2", "wet")],
       "indirect negative reads: %r" % a["dependencies"]["dynamic_negative_reads"])
  print("  licence: a polish-only source has no writer of the read negative; a change to licensed and a text effect are "
        "writers; restriction and standing-law negatives are listed")


def check_transport():
  tom, key, hall, garden = "Tom 9", "key 10", "hall 11", "garden 12"
  person = ["and", ["isa", "person", tom], ["is rel2", "located_at", tom, hall]]
  key_at = ["is rel2", "located_at", key, hall]
  holds = ["is rel2", "holding", tom, key]
  may_go = ["can", tom, ["move", tom, hall, garden, "foot"]]
  go = ["move", tom, hall, garden, "foot"]
  Q = lambda body: ["@id", "Q1", body]
  out = lambda q, src: (ar.compile_query(Q(q), src)["outcome"] or {})
  refused = lambda q, src: out(q, src).get("reasons") == ["unsupported_transport_dependency"]
  through = lambda src: [(t["through"], t["holder"], t["object"]) for t in src["dependencies"]["transport"]]
  a = compiled(person, key_at, holds, may_go)
  need(a["support"]["status"] == "supported" and a["dependencies"]["transport"] ==
       [{"object": key, "holder": tom, "through": "initial_holding", "laws": ["S3"], "holder_moves_by": ["S4"],
         "location_units": ["S2"], "units": ["S2", "S3", "S4"]}], "%r" % a["dependencies"]["transport"])
  # 5. initial holding, then the holder moves: a post-state location query is rejected
  for q in (["plan", ["is rel2", "located_at", key, garden]], ["verify", [go], ["is rel2", "located_at", key, hall]],
            ["plan", ["exists", "X", ["and", ["isa", "artifact", "X"], ["is rel2", "located_at", "X", garden]]]]):
    need(refused(q, a) and out(q, a)["units"] == (["S2", "S3", "S4"] if q[0] == "plan" else ["S2", "S3"]), "%r: %r" % (q, out(q, a)))
  need(out(["verify", [go], ["is rel2", "located_at", tom, garden]], a) == {}
       and out(["verify", [go], ["is rel2", "holding", tom, key]], a) == {}, "a query that does not read the key's location")
  # 3. and 4. a question, an ask and an empty sequence read the root: no transition, no refusal
  for q in (["question", key_at], ["ask", "P", ["is rel2", "located_at", key, "P"]], ["verify", [], key_at]):
    need(out(q, a) == {}, "a snapshot query was refused: %r %r" % (q, out(q, a)))
  # 1. an explicit negative holding is no holding
  b = compiled(person, key_at, NOT(holds), may_go)
  need(through(b) == [] and out(["plan", ["is rel2", "located_at", key, garden]], b) == {}
       and out(["verify", [go], key_at], b) == {}, "not holding became holding: %r" % through(b))
  # 2. an explicit negative location is no tracked location
  c = compiled(person, NOT(key_at), holds, may_go)
  need([t["location_units"] for t in c["dependencies"]["transport"]] == [[]], "not located_at became a location: %r" % c["dependencies"]["transport"])
  need(ef._initial_facts(c["units"], "located_at") == [("S1", tom, hall)], "signed initial facts")
  # possession alone states no accompaniment
  d = compiled(person, key_at, ["have", tom, key], may_go)
  need(through(d) == [] and out(["plan", ["is rel2", "located_at", key, garden]], d) == {} and out(["verify", [go], key_at], d) == {},
       "possession alone is no transport dependency")
  # 6. take, then the holder moves: holding arises from the library's take effect
  world = ["and", ["isa", "person", tom], ["isa", "hand", tom], ["isa", "block", "a 7"], ["isa", "table", "table 8"],
           ["is rel2", "located_at", tom, hall], ["is rel2", "located_at", "a 7", hall], ["is rel2", "on", "a 7", "table 8"],
           ["has property", "clear_top", "a 7"], ["has property", "empty", tom], ["connected", hall, garden, "foot"]]
  e = compiled(world)
  take, a_at = ["take", tom, "a 7"], ["is rel2", "located_at", "a 7", hall]
  need(through(e) == [("library_take", tom, "a 7")] and e["dependencies"]["transport"][0]["laws"] == ["library:poss_take_hand"]
       and e["dependencies"]["transport"][0]["holder_moves_by"] == ["library:poss_move_person"], "library take: %r" % e["dependencies"]["transport"])
  need(refused(["verify", [take, go], a_at], e) and refused(["plan", ["is rel2", "located_at", "a 7", garden]], e), "take then move")
  need(out(["verify", [take], a_at], e) == {} and out(["verify", [go], a_at], e) == {} and out(["question", a_at], e) == {},
       "a take alone, a move alone and a snapshot carry nothing")
  # 7. take, release, then move: the released object is not carried
  for release in (["put_on", tom, "a 7", "table 8"], ["put_in", tom, "a 7", "table 8"]):
    need(out(["verify", [take, release, go], a_at], e) == {}, "a released object was still carried: %r" % release)
  need(refused(["verify", [take, ["put_on", tom, "a 7", "table 8"], take, go], a_at], e), "taken again after a release")
  need(out(["verify", [take, go], ["is rel2", "located_at", tom, garden]], e) == {}, "the holder's own location")
  # a hand that cannot move carries nothing
  f = compiled(["and", ["isa", "hand", "hand 6"], ["isa", "block", "a 7"], ["is rel2", "located_at", "a 7", hall]])
  need(through(f) == [], "a holder without a movement permission: %r" % through(f))
  # a source take permission, with a variable object
  g = compiled(person, key_at, ["forall", "X", ["can", tom, ["take", tom, "X"]]], may_go)
  need(through(g) == [("source_take", tom, "X")] and refused(["plan", ["is rel2", "located_at", key, garden]], g), "source take: %r" % through(g))
  # 8. a positive text effect that establishes holding is in the inventory, and the scan applies it
  grab = ["change", tom, key, "grabbed", "unspecified"]
  h = compiled(person, key_at, ["can", tom, grab], ["after", grab, holds], may_go)
  need(through(h) == [("text_effect", tom, key)] and h["dependencies"]["transport"][0]["units"] == ["S2", "S4", "S5"], "text effect: %r" % h["dependencies"]["transport"])
  need(refused(["verify", [grab, go], key_at], h) and out(["verify", [go], key_at], h) == {}, "a text effect establishes holding")
  drop = ["change", tom, key, "dropped", "unspecified"]
  i = compiled(person, key_at, holds, ["can", tom, drop], ["after", drop, NOT(holds)], may_go)
  need(out(["verify", [drop, go], key_at], i) == {} and refused(["verify", [go, drop], key_at], i), "a text effect releases the object")
  # per root (migration step 1b.6): a W0 holding does not reach a W1-rooted query; the source inventory lists it
  two = ar.compile_source(None, [cav.S(person, "S1"), cav.S(key_at, "S2"), cav.S(holds, "S3"), cav.S(may_go, "S4"),
                                 ["@id", "S5", ["holds", "W1", ["and", ["is rel2", "located_at", tom, hall], key_at]]]],
                          la.PROFILE, None, ENTS, worlds=["W0", "W1"])
  plan = ["@id", "Q1", ["plan", ["is rel2", "located_at", key, garden]]]
  at = lambda root, q=plan: (ar.compile_query(q, two, planning_root=root)["outcome"] or {}).get("reasons")
  need(through(two) == [("initial_holding", tom, key)], "the source inventory: %r" % through(two))
  need(at("W0") == ["unsupported_transport_dependency"] and at("W1") is None and at(None) is None,
       "per root: W0 %r, W1 %r, default root %r" % (at("W0"), at("W1"), at(None)))
  vq = ["@id", "Q1", ["verify", [go], key_at]]
  need(at("W0", vq) == ["unsupported_transport_dependency"] and at("W1", vq) is None, "verify per root")
  need(ef._initial_facts(two["units"], "located_at", "W1") == [("S5", tom, hall), ("S5", key, hall)]
       and ef._initial_facts(two["units"], "holding", "W1") == [], "the initial facts of W1")
  c34 = {c["case"]: c for c in fm.load_all()}["c34_transport_per_root:base"]
  src = cav.gold_source(c34)
  got = [(ar.compile_query(q["stage2"], src, None, **fm.selection(q))["outcome"] or {}).get("reasons") for q in c34["queries"]]
  need(got == [["unsupported_transport_dependency"], None], "c34: %r" % got)
  print("  transport: signed initial facts; snapshot queries and an empty sequence are eligible; initial holding, take, and a "
        "text effect are carried by a moving holder; a release stops it; possession and a fixed hand carry nothing; "
        "the query-time dependency reads the planning root's facts only")


def check_conflicts():
  a = compiled(["forall", "X", ["after", ["take", "hand 6", "X"], ["has property", "empty", "hand 6"]]])
  w = a["dependencies"]["writes"]
  need(a["support"]["status"] == "supported" and w[0]["library_conflicts"] == ["eff_take_not_empty"] and unit(a, "S1")["compile_note"],
       "a text write against the library: %r" % w)
  view = [lib.literals(r["clause"]) for r in ar.library_view(a, "verify")]
  need(any(x[0] == "-has property" and x[1] == "empty" for c in view for x in c)
       and any(r["role"] == "effect" for r in unit(a, "S1")["clauses"]), "both writes stay")
  # a restatement of a library effect stays a separate clause with its own provenance
  a = compiled(["forall", "X", ["after", ["take", "hand 6", "X"], ["is rel2", "holding", "hand 6", "X"]]])
  need(len(unit(a, "S1")["clauses"]) == 1 and unit(a, "S1")["clauses"][0]["provenance"] == "S1"
       and a["dependencies"]["writes"][0]["library_conflicts"] == [], "a restated effect")
  # another actor's take does not unify
  a = compiled(["after", ["take", "Ann 1", "a 7"], ["has property", "empty", "hand 6"]])
  need(a["dependencies"]["writes"][0]["library_conflicts"] == [], "a conflict needs the library's own instance")
  # rejected effect forms
  for f, reason in ((["after", PRESS, ["normally", ON]], "defeasible_text_effect"),
                    (cav.S(["after", PRESS, ON], "S1", 0.8), None)):
    a = compiled(f)
    need(a["support"]["status"] == "unsupported" and not unit(a, "S1")["clauses"]
         and (reason is None or a["support"]["reasons"] == [reason]), "%r: %r" % (f, a["support"]))
  print("  conflicts: a text write against a library write is recorded and both stay; a restatement stays a separate clause; "
        "defeasible and uncertain effects emit no clause")


def check_metadata():
  f = [OFF, ["can", "Ann 1", PRESS], TOGGLE_ON, TOGGLE_OFF]
  before = copy.deepcopy(f)
  a, b = compiled(*f), compiled(*f)
  need(ar.dumps(a) == ar.dumps(b) and f == before, "two runs differ or the input changed")
  need(ef.PASS in a["passes"] and a["pending_passes"] == [] and ar.source_outcome(a)["outcome"] == "source_compiled"
       and ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED,
       "pass bookkeeping: %r" % a["pending_passes"])
  ar.check_artifact(a, ar.SOURCE)
  writes = [(w["unit"], w["literal"][1], w["sign"], w["conditional"], w["marker"]) for w in a["dependencies"]["writes"]]
  need(writes == [("S3", "on", "+", True, False), ("S3", "off", "-", True, True), ("S4", "off", "+", True, False), ("S4", "on", "-", True, True)]
       and all(w["stops_opposite_frame"] for w in a["dependencies"]["writes"]), "signed writes: %r" % writes)
  deps = {d["unit"]: d for d in a["dependencies"]["units"]}
  need([r["literal"] for r in deps["S3"]["reads"]] == [OFF] and deps["S2"]["library_writes"][0]["literal"] == ["has property", "pressed", "switch 3"],
       "reads and library writes: %r" % deps)
  need(set(a["dependencies"]) == {"units", "dynamic_negative_reads", "transport", "writes", "properties"}
       and "export" not in json.dumps(sorted(a)), "the dependency record is always complete; no option removes it")
  o = compiled(["isa", "person", "Ann 1"], profile=la.ORDINARY)
  need(o["dependencies"] is None and o["policy_clauses"] == [], "the ordinary profile has no action metadata")
  print("  metadata: signed writes with their conditions and markers, reads, library writes; deterministic; always computed")


def run():
  check_gold()
  check_bindings()
  check_one_step()
  check_policy()
  check_licence()
  check_transport()
  check_conflicts()
  check_metadata()


if __name__ == "__main__":
  run()
