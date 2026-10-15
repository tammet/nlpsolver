"""WP11 checks: the independent finite-fragment replay (`solver/action_replay.py`).

No model, no GK.  The replay reads the source artifact's units, never its compiled clauses.

  candidates    every gold candidate: its verdict, its failing step, and the facts, removed facts and derived
                properties of every listed state
  queries       every gold query marked `replay: covered` that names a checkable result: the gold plan validates
                against its goal and bound (witnesses included), a verify answer equals the gold answer (the answer
                on a validated backend where the starting backend refuses), an inconsistent state gives the gold
                conflict facts
  c09           WP11 step 7: the supplied take gives both signs of empty and holding+empty at step 1
  generic       renamed actors, two owners, different tools, novel property values, wrong supplied plans, negative
                facts across unrelated actions, a conditional effect with an unknown condition
  review        Sol's four probes (a false effect condition, a contradictory antecedent, the connective tables,
                a long support cycle)
  support       Sol's re-review: cyclic laws through a contested atom end; a clean support is used when one exists
  independence  the replay module reads no compiled clause and no library file
"""

import json
import os
import re
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_replay as rp
import action_route as ar
import check_action_availability as cav
import check_action_validation as cv
import fixture_materialize as fm
import lc_action as la

need = cav.need
S = lambda uid, f, w="W0": ["@id", uid, ["holds", w, f]]
SKIP = ("not_found", "unsupported_translation", "translation_invalid", "insufficient_search_allowance")


def check_candidates():
  n = facts = 0
  for c in fm.load_all():
    if not c.get("candidates"):
      continue
    a = cv.gold_source(c)
    sel = fm.selection(c["queries"][0]) if c["queries"] else {}
    for k in c["candidates"]:
      w = "%s/%s" % (c["case"], k["id"])
      r = rp.replay(a, k["sequence"], **sel)
      need(r["verdict"] == k["verdict"], "%s: verdict %s, gold %s (%s)" % (w, r["verdict"], k["verdict"], r["reason"]))
      need(k["verdict"] == "valid" or r["step"] == k.get("step"), "%s: step %s, gold %s" % (w, r["step"], k.get("step")))
      for st in k.get("states") or []:
        if not isinstance(st.get("facts"), list):
          need(st["after"] >= len(r["states"]), "%s: a state after %d exists, gold: not reached" % (w, st["after"]))
          continue
        mine = r["states"][st["after"]]
        have = set(mine["facts"]) | set(mine["static"]) | set(mine["derived"])
        for f in st["facts"]:
          facts += 1
          need(f in have, "%s: after %d the fact %s is missing: %s" % (w, st["after"], f, mine["facts"]))
        for f in st.get("removed") or []:
          need(f not in mine["facts"], "%s: after %d the removed fact %s is present" % (w, st["after"], f))
        for f in st.get("derived") or []:
          need(f in mine["derived"], "%s: after %d the derived %s is missing" % (w, st["after"], f))
        for f in st.get("not_derived") or []:
          need(f not in mine["derived"], "%s: after %d %s is derived" % (w, st["after"], f))
      n += 1
  print("  candidates: %d gold candidates give their verdict and failing step; %d listed state facts hold" % (n, facts))


def _steps(pkg):
  return {"comparison": pkg[2][1], "n": pkg[2][2]} if len(pkg) > 2 else None


def check_queries():
  counts = {}
  for c in fm.load_all():
    a = cv.gold_source(c) if c["units"] else None
    for q in c["queries"]:
      if q.get("replay") != "covered" or not q.get("stage2") or a is None or a["support"]["status"] != "supported":
        continue
      e = q["expect"]
      if e.get("outcome") == "unsupported_backend_requirement" and e.get("on_validated_backend"):
        e = e["on_validated_backend"]
      want = e.get("outcome") or e.get("answer")
      if want in SKIP:
        continue
      pkg, w, sel = q["stage2"][2], "%s/%s" % (c["case"], q["id"]), fm.selection(q)
      kind = pkg[0]
      if kind in ("plan", "reachable"):
        if want == "inconsistent_action_state":
          r = rp.replay(a, [], **sel)
          need(r["verdict"] == want, "%s: %s, gold %s" % (w, r["verdict"], want))
        else:
          r = rp.replay(a, e.get("plan", []), goal=pkg[1], steps=_steps(pkg), **sel)
          need(r["verdict"] == "valid", "%s: the gold plan is %s: %s" % (w, r["verdict"], r["reason"]))
          for var, val in (e.get("witness") or {}).items():
            need((r["goal"]["witness"] or {}).get(var) == val, "%s: witness %s, gold %s=%s" % (w, r["goal"]["witness"], var, val))
      elif kind == "verify":
        r = rp.replay(a, pkg[1], goal=pkg[2], **sel)
        got = rp.verification(r)["answer"]
        need(got == (e.get("answer") or want), "%s: verification %s, gold %s (%s)" % (w, got, e.get("answer") or want, r["reason"]))
      elif kind == "question" and want == "inconsistent_action_state":
        r = rp.replay(a, [], **sel)
        need(r["verdict"] == want, "%s: %s" % (w, r["verdict"]))
      else:
        continue
      if want == "inconsistent_action_state":
        mine = {f for cf in r["conflicts"] for f in cf["facts"]}
        need(set(e.get("facts") or []) <= mine, "%s: conflict facts %s, gold %s" % (w, sorted(mine), e.get("facts")))
      counts[kind] = counts.get(kind, 0) + 1
  print("  queries: %s covered gold queries agree (plans, witnesses, verification answers, conflict facts)"
        % ", ".join("%d %s" % (n, k) for k, n in sorted(counts.items())))


def check_c09():
  c = {x["case"]: x for x in fm.load_all()}["c09_inconsistent_states:replayed_conflict"]
  r = rp.replay(cv.gold_source(c), [["take", "hand 1", "a 2"]])
  facts = {f for cf in r["conflicts"] for f in cf["facts"]}
  need(r["verdict"] == "inconsistent_action_state" and r["step"] == 1
       and {"empty(hand,W0+1) [S2]", "-empty(hand,W0+1) [library]", "holding(hand,a,W0+1) [library]"} <= facts,
       "c09: %s at %s, %s" % (r["verdict"], r["step"], sorted(facts)))
  print("  c09: the supplied take gives both signs of empty and holding+empty at step 1: inconsistent_action_state")


def compiled(entities, *units, **kw):
  a = ar.compile_source(None, [S("S%d" % (i + 1), f) for i, f in enumerate(units)], la.PROFILE, entities=entities, **kw)
  need(a["support"]["status"] == "supported", "a test source is %s: %s" % (a["support"]["status"], a["support"]))
  return a


def renamed(case, mapping):
  """A gold case with its entity ids renamed: the same source under other names."""
  c = {x["case"]: x for x in fm.load_all()}[case]
  text = json.dumps([u["stage2"] for u in c["units"]])
  ents = dict(c["entities"])
  for old, new in mapping.items():
    text = text.replace('"%s"' % old, '"%s"' % new)
    ents[new] = ents.pop(old)
  return ar.compile_source(None, json.loads(text), c["profile"], entities=ents)


def verdict(a, seq, **kw):
  r = rp.replay(a, seq, **kw)
  return r["verdict"], r["step"], r


def check_generic():
  # renamed actors and objects: the travel and tower plans under other ids
  trav = renamed("p01_travel:base", {"Ann 1": "Mirel 7", "Haapsalu 2": "Paide 8", "Tallinn 3": "Narva 9", "Helsinki 4": "Oulu 5"})
  plan = [["move", "Mirel 7", "Paide 8", "Narva 9", "bus"], ["move", "Mirel 7", "Narva 9", "Oulu 5", "ship"]]
  need(verdict(trav, plan, goal=["is rel2", "located_at", "Mirel 7", "Oulu 5"])[0] == "valid", "renamed travel")
  need(verdict(trav, [["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"]])[:2] == ("invalid", 1), "the old names are no permission")
  tower = renamed("p02_tower:base", {"hand 1": "grip 6", "a 2": "cube 7", "b 3": "cube 8", "c 4": "cube 9"})
  steps = [["take", "grip 6", "cube 8"], ["put_on", "grip 6", "cube 8", "cube 7"], ["take", "grip 6", "cube 9"],
           ["put_on", "grip 6", "cube 9", "cube 8"]]
  need(verdict(tower, steps)[0] == "valid", "renamed tower")
  # wrong supplied plans: swapped steps, a missing first step, a bound, a reversed service
  need(verdict(tower, [steps[1], steps[0]] + steps[2:])[:2] == ("invalid", 1), "swapped tower steps")
  need(verdict(tower, steps[:2] + [steps[3], steps[2]])[:2] == ("invalid", 3), "swapped late tower steps")
  need(verdict(trav, plan, steps={"comparison": "exactly", "n": 1})[0] == "invalid", "two steps against exactly one")
  need(verdict(trav, plan[::-1])[:2] == ("invalid", 1), "the ship leg before the bus leg")
  food = {x["case"]: x for x in fm.load_all()}["p03_food:base"]
  fplan = food["queries"][0]["expect"]["plan"]
  need(verdict(cv.gold_source(food), fplan[1:])[:2] == ("invalid", 1), "the food plan without breaking the egg")
  # two owners: possession is per owner
  ents = {"Ann 1": "person", "Bob 2": "person", "cup 3": "artifact", "cup 4": "artifact"}
  polish = lambda p, c: ["change", p, c, "polished", "unspecified"]
  owners = compiled(ents, ["isa", "person", "Ann 1"], ["isa", "person", "Bob 2"], ["isa", "cup", "cup 3"],
                    ["isa", "cup", "cup 4"], ["have", "Ann 1", "cup 3"], ["have", "Bob 2", "cup 4"],
                    ["forall", "P", ["forall", "C", ["implies", ["and", ["isa", "person", "P"], ["isa", "cup", "C"],
                                                                ["have", "P", "C"]], ["can", "P", polish("P", "C")]]]])
  v, step, r = verdict(owners, [polish("Ann 1", "cup 3"), polish("Bob 2", "cup 4")])
  need(v == "valid" and {"+have(Ann,cup)", "+have(Bob,cup)", "+polished(cup)"} <= set(r["states"][-1]["facts"]),
       "two owners polish their own cups: %s %s" % (v, r["reason"]))
  need(verdict(owners, [polish("Ann 1", "cup 4")])[:2] == ("invalid", 1), "Ann has no permission for Bob's cup")
  # different tools: the rule names the tool class
  ents = {"Ann 1": "person", "egg 2": "food", "whisk 3": "tool", "fork 4": "tool"}
  whisk = lambda t: ["change", "Ann 1", "egg 2", "whisked", t]
  tools = compiled(ents, ["and", ["isa", "whisk", "whisk 3"], ["isa", "fork", "fork 4"]],
                   ["and", ["have", "Ann 1", "whisk 3"], ["have", "Ann 1", "fork 4"]],
                   ["forall", "W", ["implies", ["and", ["isa", "whisk", "W"], ["have", "Ann 1", "W"]], ["can", "Ann 1", whisk("W")]]])
  need(verdict(tools, [whisk("whisk 3")])[0] == "valid", "the whisk")
  need(verdict(tools, [whisk("fork 4")])[:2] == ("invalid", 1), "the fork is no whisk")
  need(verdict(tools, [whisk("unspecified")])[:2] == ("invalid", 1), "an unspecified tool does not bypass the tool class")
  # novel property values, read by a later step
  ents = {"Zed 1": "person", "stone 2": "artifact"}
  rub, polish2 = ["change", "Zed 1", "stone 2", "glimmering", "unspecified"], ["change", "Zed 1", "stone 2", "sparkling", "unspecified"]
  novel = compiled(ents, ["have", "Zed 1", "stone 2"], ["can", "Zed 1", rub],
                   ["implies", ["has property", "glimmering", "stone 2"], ["can", "Zed 1", polish2]])
  v, step, r = verdict(novel, [rub, polish2], goal=["has property", "sparkling", "stone 2"])
  need(v == "valid" and "+glimmering(stone)" in r["states"][-1]["facts"], "novel values: %s" % r["reason"])
  need(verdict(novel, [polish2])[:2] == ("invalid", 1), "the novel condition is not yet true")
  # a negative fact survives an unrelated action and still denies
  c01 = {x["case"]: x for x in fm.load_all()}["c01_unlicensed_polish:base"]
  v, step, r = verdict(cv.gold_source(c01), [["change", "Ann 1", "cup 4", "polished", "unspecified"]])
  need(v == "valid" and "-licensed(Ann)" in r["states"][1]["facts"], "the negative fact persists")
  # a conditional effect with an unknown condition leaves the atoms it may write unknown (x03 lamp_unknown)
  x03 = {x["case"]: x for x in fm.load_all()}["x03_partial_effects:lamp_unknown"]
  q = x03["queries"][0]["stage2"][2]
  r = rp.replay(cv.gold_source(x03), q[1], goal=q[2])
  need(rp.verification(r)["answer"] == "Unknown" and r["steps"][0].get("uncertain_writes"),
       "x03 lamp_unknown: %s %s" % (rp.verification(r), r["steps"]))
  # an ambiguous property policy leaves the source unsupported: the replay does not check it
  c07 = {x["case"]: x for x in fm.load_all()}["c07_clean_bowl:base"]
  r = rp.replay(cv.gold_source(c07), [["move", "Ann 1", "Haapsalu 2", "Tallinn 3", "bus"]])
  need(r["verdict"] == "not_checked" and r["uncovered"] == "source" and "ambiguous_state_policy" in r["reason"],
       "c07 base: %s %s" % (r["verdict"], r["reason"]))
  # the replay does not change its source artifact
  before = ar.canonical(trav)
  rp.replay(trav, plan, goal=["is rel2", "located_at", "Mirel 7", "Oulu 5"])
  need(ar.canonical(trav) == before, "the replay changed its source artifact")
  print("  generic: renamed actors and blocks, wrong plans (swapped, missing, over a bound, reversed), two owners, "
        "tool classes, novel property values, a persisting negative, an unknown effect condition, an ambiguous policy "
        "not checked, the source artifact unchanged")


def check_review_repairs():
  """Sol's WP11 review (MEMO_2026_09_24_wp11_replay_review_codex.md): four supported-input probes and the GK
  results that review recorded for the first three."""
  T, F, B, U = rp.T, rp.F, rp.B, rp.U
  prop = lambda v, x: ["has property", v, x]
  profile = lambda *stored: {"name": la.PROFILE, "policy": {"stored": list(stored)}}
  # R1: a false effect condition writes nothing; the stored fact persists (GK: raw(egg) at 0.99, no negative proof)
  cook = ["change", "Ann 1", "egg 2", "cooked", "unspecified"]
  ents = {"Ann 1": "person", "egg 2": "food"}
  src = ar.compile_source(None, [S("S1", prop("raw", "egg 2")), S("S2", ["not", prop("trigger", "egg 2")]),
                                 S("S3", ["can", "Ann 1", cook]),
                                 S("S4", ["implies", prop("trigger", "egg 2"), ["after", cook, ["not", prop("raw", "egg 2")]]])],
                          profile("raw", "trigger"), entities=ents)
  need(src["support"]["status"] == "supported", "R1 source: %s" % src["support"])
  r = rp.replay(src, [cook], goal=prop("raw", "egg 2"))
  need(r["verdict"] == "valid" and "+raw(egg)" in r["states"][1]["facts"] and not r["steps"][0].get("uncertain_writes"),
       "R1: a false condition erased raw(egg): %s %s" % (r["verdict"], r["reason"]))
  unknown = ar.compile_source(None, [S("S1", prop("raw", "egg 2")), S("S3", ["can", "Ann 1", cook]),
                                     S("S4", ["implies", prop("trigger", "egg 2"), ["after", cook, ["not", prop("raw", "egg 2")]]])],
                              profile("raw", "trigger"), entities=ents)
  r = rp.replay(unknown, [cook], goal=prop("raw", "egg 2"))
  need(r["verdict"] == "invalid" and r["goal"]["value"] == U, "R1 control: an unknown condition leaves raw unknown: %s" % r["reason"])
  # R2: a contradictory antecedent gives the strict head its positive support only (GK: the positive proof, no
  # negative proof); the candidate rests on a contested premise and is not validated (A5.1)
  lit = ["change", "Robo 1", "lamp 2", "lit", "unspecified"]
  both = [S("S1", prop("ready", "lamp 2")), S("S2", ["not", prop("ready", "lamp 2")])]
  src = ar.compile_source(None, both + [S("S3", ["implies", prop("ready", "lamp 2"), ["can", "Robo 1", lit]])],
                          la.PROFILE, entities={"Robo 1": "robot", "lamp 2": "artifact"})
  r = rp.replay(src, [lit])
  need(r["steps"][0]["value"] == T and r["steps"][0]["premises"] == ["ready(lamp)"],
       "R2: the step is %s, not true with a contested premise" % r["steps"][0]["value"])
  need(r["verdict"] == "not_checked" and r["uncovered"] == "contested_premise", "R2: %s %s" % (r["verdict"], r["reason"]))
  law = ["state_law", ["forall", "X", ["implies", prop("ready", "X"), prop("marked", "X")]]]
  src = ar.compile_source(None, [S("S1", ["isa", "block", "a 1"]), S("S2", prop("ready", "a 1")),
                                 S("S3", ["not", prop("ready", "a 1")]), S("S4", law)], la.PROFILE, entities={"a 1": "block"})
  v, _, tr = rp.evaluate(src, prop("marked", "a 1"))
  need(v == T and tr == ["ready(a)"], "R2: marked(a) is %s (GK: accepted at 1.0, no -marked proof), premises %s" % (v, tr))
  r = rp.replay(src, [], goal=prop("marked", "a 1"))
  need(r["verdict"] == "not_checked" and r["uncovered"] == "contested_premise", "R2 law: %s" % r["reason"])
  # the negative side: a denial or a false goal that rests on a contested premise gives no validated No
  src = ar.compile_source(None, both + [S("S3", ["implies", prop("ready", "lamp 2"), ["not", ["can", "Robo 1", lit]]])],
                          la.PROFILE, entities={"Robo 1": "robot", "lamp 2": "artifact"})
  r = rp.replay(src, [lit])
  need(r["verdict"] == "invalid" and r["steps"][0]["value"] == F and r["premises"] == ["ready(lamp)"],
       "a contested denial: %s %s" % (r["verdict"], r["reason"]))
  need(rp.verification(r)["answer"] == "not_checked", "a contested denial gives %s, not not_checked" % rp.verification(r))
  src = ar.compile_source(None, both[:1] + [S("S3", ["implies", prop("ready", "lamp 2"), ["not", ["can", "Robo 1", lit]]])],
                          la.PROFILE, entities={"Robo 1": "robot", "lamp 2": "artifact"})
  need(rp.verification(rp.replay(src, [lit]))["answer"] == "No", "a denial on an established premise gives No")
  src = ar.compile_source(None, [S("S1", ["isa", "block", "a 1"]), S("S2", prop("ready", "a 1")),
                                 S("S3", ["not", prop("ready", "a 1")]), S("S4", law)], la.PROFILE, entities={"a 1": "block"})
  r = rp.replay(src, [], goal=["not", prop("marked", "a 1")])
  need(r["verdict"] == "invalid" and rp.verification(r)["answer"] == "not_checked",
       "a false goal on a contested premise: %s %s" % (r["verdict"], rp.verification(r)))
  # R3: the connectives on signed support (GK: ready(a) and clean(a) has no positive proof and a negative one at 1.0)
  v, _, _ = rp.evaluate(src, ["and", prop("ready", "a 1"), prop("clean", "a 1")])
  need(v == F, "R3: both and unknown is %s, not false" % v)
  v, _, _ = rp.evaluate(src, ["or", prop("ready", "a 1"), prop("clean", "a 1")])
  need(v == T, "R3: both or unknown is %s, not true" % v)
  # the full 4x4 tables of docs/architecture/action-answers.md (the replay), through the evaluator: t is stated, f denied, b both, u neither
  four = ar.compile_source(None, [S("S1", ["and", ["isa", "block", "t 1"], ["isa", "block", "f 2"], ["isa", "block", "b 3"],
                                                    ["isa", "block", "u 4"]]),
                                  S("S2", prop("ready", "t 1")), S("S3", ["not", prop("ready", "f 2")]),
                                  S("S4", prop("ready", "b 3")), S("S5", ["not", prop("ready", "b 3")])],
                           la.PROFILE, entities={"t 1": "block", "f 2": "block", "b 3": "block", "u 4": "block"})
  atom = {T: prop("ready", "t 1"), F: prop("ready", "f 2"), B: prop("ready", "b 3"), U: prop("ready", "u 4")}
  need([rp.evaluate(four, atom[x])[0] for x in (T, F, B, U)] == [T, F, B, U], "the four atoms")
  AND = {(T, T): T, (T, F): F, (T, B): B, (T, U): U, (F, T): F, (F, F): F, (F, B): F, (F, U): F,
         (B, T): B, (B, F): F, (B, B): B, (B, U): F, (U, T): U, (U, F): F, (U, B): F, (U, U): U}
  OR = {(T, T): T, (T, F): T, (T, B): T, (T, U): T, (F, T): T, (F, F): F, (F, B): B, (F, U): U,
        (B, T): T, (B, F): B, (B, B): B, (B, U): T, (U, T): T, (U, F): U, (U, B): T, (U, U): U}
  for op, table in (("and", AND), ("or", OR)):
    for (a, b), want in table.items():
      got = rp.evaluate(four, [op, atom[a], atom[b]])[0]
      need(got == want, "%s(%s, %s) = %s, not %s" % (op, a, b, got, want))
  need([rp.evaluate(four, ["not", atom[x]])[0] for x in (T, F, B, U)] == [F, T, B, U], "negation")
  two = ar.compile_source(None, [S("S1", ["and", ["isa", "block", "a 1"], ["isa", "block", "b 2"]]),
                                 S("S2", prop("ready", "a 1")), S("S3", ["not", prop("ready", "a 1")])],
                          la.PROFILE, entities={"a 1": "block", "b 2": "block"})
  some = ["exists", "X", ["and", ["isa", "block", "X"], prop("ready", "X")]]
  every = ["forall", "X", ["implies", ["isa", "block", "X"], prop("ready", "X")]]
  need(rp.evaluate(two, some)[0] == T and rp.evaluate(two, every)[0] == F,
       "quantifiers over both and unknown: exists %s, forall %s" % (rp.evaluate(two, some)[0], rp.evaluate(two, every)[0]))
  guarded = ar.compile_source(None, [S("S1", ["isa", "robot", "Robo 1"]), S("S2", prop("ready", "Robo 1")),
                                     S("S3", ["not", prop("ready", "Robo 1")]),
                                     S("S4", ["implies", ["and", prop("ready", "Robo 1"), prop("clean", "Robo 1")],
                                              ["can", "Robo 1", ["change", "Robo 1", "Robo 1", "shiny", "unspecified"]]])],
                              la.PROFILE, entities={"Robo 1": "robot"})
  r = rp.replay(guarded, [["change", "Robo 1", "Robo 1", "shiny", "unspecified"]])
  need(r["verdict"] == "invalid" and r["steps"][0]["paths"][0]["permission"] == F,
       "a condition both-and-unknown gives no permission: %s" % r["reason"])
  # R4: a support cycle of any length; a long chain is no cycle
  ids = ["b %d" % i for i in range(1, 19)]
  on = [["is rel2", "on", ids[i], ids[(i + 1) % len(ids)]] for i in range(len(ids))]
  ring = ar.compile_source(None, [S("S1", ["and"] + [["isa", "block", x] for x in ids] + on)], la.PROFILE,
                           entities={x: "block" for x in ids})
  need(ring["support"]["status"] == "supported", "R4 source: %s" % ring["support"])
  r = rp.replay(ring, [])
  cyc = [c for c in r["conflicts"] if c["rule"] == "a support cycle"]
  need(r["verdict"] == "inconsistent_action_state" and len(cyc) == 1 and len(cyc[0]["facts"]) == 18,
       "R4: an 18-block cycle: %s %s" % (r["verdict"], [len(c["facts"]) for c in cyc]))
  ids = ["c %d" % i for i in range(1, 31)]
  chain = ar.compile_source(None, [S("S1", ["and"] + [["isa", "block", x] for x in ids] +
                                     [["is rel2", "on", ids[i], ids[i + 1]] for i in range(len(ids) - 1)])],
                            la.PROFILE, entities={x: "block" for x in ids})
  need(rp.replay(chain, [])["verdict"] == "valid", "a 30-block tower is no cycle")
  print("  review repairs: a false effect condition keeps the stored fact (R1); a contradictory antecedent gives the "
        "positive head only and the candidate is not_checked as a contested premise, and a No on one is not_checked (R2); the 4x4 tables, the "
        "quantifiers and a guarded condition on signed support (R3); an 18-block support cycle and a 30-block chain (R4)")


def bounded(seconds, fn, *args, **kw):
  """fn(*args, **kw), or a failure when it does not return within the given seconds."""
  def stop(signum, frame):
    raise RuntimeError("%s did not return within %d s" % (fn.__name__, seconds))
  old = signal.signal(signal.SIGALRM, stop)
  signal.alarm(seconds)
  try:
    return fn(*args, **kw)
  finally:
    signal.alarm(0)
    signal.signal(signal.SIGALRM, old)


def check_support_paths():
  """Sol's re-review (MEMO_2026_09_24_wp11_replay_rereview_codex.md): the support of each sign is a finite set of
  base contested atoms, so cyclic rules end (P1); a clean support is used when one exists (P2)."""
  T, F = rp.T, rp.F
  prop = lambda v, x: ["has property", v, x]
  law = lambda a, b: ["state_law", ["forall", "X", ["implies", prop(a, "X"), prop(b, "X")]]]
  stored = lambda *n: {"name": la.PROFILE, "policy": {"stored": list(n)}}
  blk = [S("S0", ["isa", "block", "a 1"])]
  contested = [S("S1", prop("p", "a 1")), S("S2", ["not", prop("p", "a 1")])]
  # P1: p(a), -p(a), p -> q, q -> p
  src = ar.compile_source(None, blk + contested + [S("S3", law("p", "q")), S("S4", law("q", "p"))], stored("p", "q"),
                          entities={"a 1": "block"})
  need(src["support"]["status"] == "supported", "P1 source: %s" % src["support"])
  r = bounded(10, rp.replay, src, [], goal=prop("q", "a 1"))
  need(r["verdict"] == "not_checked" and r["uncovered"] == "contested_premise" and r["goal"]["premises"] == ["p(a)"],
       "P1: %s %s" % (r["verdict"], r["reason"]))
  # a four-law cycle through the contested atom: a clean q(a) gives clean r(a) and s(a)
  src = ar.compile_source(None, blk + contested + [S("S5", prop("q", "a 1")), S("S3", law("p", "q")), S("S4", law("q", "r")),
                                                   S("S6", law("r", "s")), S("S7", law("s", "p"))],
                          stored("p", "q", "r", "s"), entities={"a 1": "block"})
  r = bounded(10, rp.replay, src, [], goal=["and", prop("r", "a 1"), prop("s", "a 1")])
  need(r["verdict"] == "valid", "a law cycle with a clean entry: %s %s" % (r["verdict"], r["reason"]))
  # P2: a stated q(a) beside the derivation p -> q from a contested p(a)
  src = ar.compile_source(None, blk + contested + [S("S5", prop("q", "a 1")), S("S3", law("p", "q"))], stored("q"),
                          entities={"a 1": "block"})
  r = rp.replay(src, [], goal=prop("q", "a 1"))
  need(r["verdict"] == "valid" and r["goal"]["premises"] == [], "P2: %s %s" % (r["verdict"], r["reason"]))
  # alternative permissions and denials: a clean one is used
  lit = ["change", "Robo 1", "lamp 2", "lit", "unspecified"]
  ents = {"Robo 1": "robot", "lamp 2": "artifact"}
  base = [S("S1", prop("ready", "lamp 2")), S("S2", ["not", prop("ready", "lamp 2")]), S("S5", prop("clean", "lamp 2"))]
  src = ar.compile_source(None, base + [S("S3", ["implies", prop("ready", "lamp 2"), ["can", "Robo 1", lit]]),
                                        S("S4", ["implies", prop("clean", "lamp 2"), ["can", "Robo 1", lit]])], la.PROFILE, entities=ents)
  r = rp.replay(src, [lit])
  need(r["verdict"] == "valid" and r["steps"][0]["premises"] == [], "a clean second permission: %s %s" % (r["verdict"], r["reason"]))
  src = ar.compile_source(None, base + [S("S3", ["implies", prop("ready", "lamp 2"), ["not", ["can", "Robo 1", lit]]]),
                                        S("S4", ["implies", prop("clean", "lamp 2"), ["not", ["can", "Robo 1", lit]]])], la.PROFILE, entities=ents)
  r = rp.replay(src, [lit])
  need(r["verdict"] == "invalid" and rp.verification(r)["answer"] == "No", "a clean second denial gives %s" % rp.verification(r))
  # alternative branches of a goal: a tainted binding and a clean one, a contested disjunct and a clean one
  ents = {"a 1": "block", "b 2": "block"}
  src = ar.compile_source(None, [S("S0", ["and", ["isa", "block", "a 1"], ["isa", "block", "b 2"]]), S("S1", prop("ready", "a 1")),
                                 S("S2", ["not", prop("ready", "a 1")]), S("S3", law("ready", "marked")),
                                 S("S4", prop("marked", "b 2"))], stored("marked"), entities=ents)
  r = rp.replay(src, [], goal=["exists", "X", ["and", ["isa", "block", "X"], prop("marked", "X")]])
  need(r["verdict"] == "valid" and r["goal"]["witness"] == {"X": "b 2"}, "a clean binding: %s %s" % (r["verdict"], r["goal"]))
  r = rp.replay(src, [], goal=["or", prop("ready", "a 1"), prop("marked", "b 2")])
  need(r["verdict"] == "valid", "a clean disjunct: %s %s" % (r["verdict"], r["reason"]))
  r = rp.replay(src, [], goal=prop("marked", "a 1"))
  need(r["verdict"] == "not_checked" and r["goal"]["premises"] == ["ready(a)"], "a tainted fact alone: %s" % r["reason"])
  # two tainted derivations of q(a) with incomparable premises: the one with fewer premises, in either rule order
  three = [S("S%d" % (i + 1), f) for i, f in enumerate(
    [["isa", "block", "a 1"]] + [g for v in ("p", "r", "t") for g in (prop(v, "a 1"), ["not", prop(v, "a 1")])])]
  pair = S("S8", ["state_law", ["forall", "X", ["implies", ["and", prop("r", "X"), prop("t", "X")], prop("q", "X")]]])
  for laws in ([pair, S("S9", law("p", "q"))], [S("S9", law("p", "q")), pair]):
    src = ar.compile_source(None, three + laws, stored("q"), entities={"a 1": "block"})
    need(src["support"]["status"] == "supported", "ranking source: %s" % src["support"])
    r = bounded(10, rp.replay, src, [], goal=prop("q", "a 1"))
    need(r["verdict"] == "not_checked" and r["goal"]["premises"] == ["p(a)"],
         "the smaller of two incomparable supports: %s %s" % (r["verdict"], r["goal"]))
  print("  support paths: a two-law cycle through a contested atom ends (P1); a stated fact beside a contested "
        "derivation, a clean second permission or denial, a clean binding or disjunct are used (P2); a law cycle "
        "with a clean entry is clean")


def check_independence():
  text = open(os.path.join(HERE, "..", "..", "solver", "action_replay.py")).read()
  code = re.sub(r'"""[\s\S]*?"""', "", text)
  imports = re.findall(r"^import (\S+)|^from (\S+)", code, re.M)
  names = {a or b for a, b in imports}
  need(names <= {"itertools", "re", "lc_action", "lc_action_query"}, "the replay imports %s" % sorted(names))
  need('["clauses"]' not in code and "axioms_action" not in code and "templates" not in code,
       "the replay reads compiled clauses or the library files")
  print("  independence: the replay imports the vocabulary and the query selection only; it reads no compiled "
        "clause and no library file")


def run():
  check_candidates()
  check_queries()
  check_c09()
  check_generic()
  check_review_repairs()
  check_support_paths()
  check_independence()


if __name__ == "__main__":
  run()
