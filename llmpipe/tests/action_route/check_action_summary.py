"""Checkpoint P checks: the planning-summary profile compiler (`solver/lc_action_summary.py`) and the reference
interpreter (`solver/action_summary.py`), compared with the independent replay.

No model, no GK.  The file needs `solver/` and `summary/` only; the sweep over the gold fixtures and the planning test
rows is `check_action_summary_sweep.py`.

  formal        the four formal controls of `summary/`: the compiled profile gives the frozen list, score and lossy
                bit at every prefix, and each list equals the replay's export for the tracked families
  ledger        every clause of the prover input has a disposition; every operation names its clauses or its policy
  cache         a repeated request costs no transition, a one-action extension one, two branches are independent,
                and a record never changes
  updates       per-operation action patterns (bus-only stamp, train-only consumption, a repeated variable), a third
                block, a surface goal, unknown and opposing writes, the lossy score control (C7), a no-op action
  failures      an unknown constructor, its descendants and its sibling; wrong root, open root, non-ground, malformed
  defaults      the default table, a model's choice (valid, invalid), a quantified initial description, a computed
                goal, a witness goal
  audit         an added writer, an unknown role, a changed frame, a standing head
  scope         two planning roots give two identities; an ambient or a knower refuses the profile
  transport     luggage held, luggage that may be taken, an explicit location write, a variable carrier, a holder
                typed by a type record, a quantified initial holding, an inferred type
  identity      the canonical form, a duplicate key, a number that is no integer, a changed semantic part
  boundaries    malformed choices take the default and the profile reloads; malformed profiles give ProfileError;
                the integer range; a sequence with a variable; the depth bound on both sides; the order of reasons;
                the reason of a failed update in `get` and `observe`
  ownership     a change of the caller's profile object after loading changes no calculation
  loss          a family without a persistence rule: a removed fact sets lossy, an empty family does not; a replay
                witness without a compiler record; a guard in an unselected family, default and explicit choice
  selectors     the query helper's situation argument, with and without witnesses, in both signs; no selector for
                a helper of an ask question
  milestones    two restrictions with one place and fact are one milestone
  independence  the replay does not import the interpreter; the interpreter imports no solver module
"""

import copy
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_replay as rp
import action_route as ar
import action_summary as asum
import lc_action as la
import lc_action_summary as ls


class Bad(Exception):
  pass


def need(cond, message):
  if not cond:
    raise Bad(message)


SUMMARY = os.path.join(HERE, "summary")
S = lambda uid, f, w="W0": ["@id", uid, ["holds", w, f]]
on = lambda x, y: ["is rel2", "on", x, y]
holding = lambda h, x: ["is rel2", "holding", h, x]
at = lambda a, c: ["is rel2", "located_at", a, c]
G = ls._gk
H, A, T, C, B = "hand 1", "a 2", "table 3", "c 4", "b 5"
ANN, LUND, MALMO, OSLO = "Ann 1", "Lund 2", "Malmo 3", "Oslo 4"
BLOCKS = [S("S1", ["isa", "hand", H]), S("S2", ["and", ["isa", "block", A], ["isa", "table", T], on(A, T)]),
          S("S3", ["and", ["isa", "block", C], on(C, A)]), S("S4", ["has property", "clear_top", C]),
          S("S5", ["has property", "empty", H])]
TRAVEL = [S("S1", ["and", ["isa", "person", ANN], at(ANN, LUND)]), S("S2", ["connected", LUND, MALMO, "bus"]),
          S("S3", ["connected", MALMO, OSLO, "train"])]
BUS, TRAIN = ["move", ANN, LUND, MALMO, "bus"], ["move", ANN, MALMO, OSLO, "train"]


def build(units, goal, choice=None, types=None, worlds=None, kind="plan", **sel):
  """(source, query, compile result) of a formal source and one discovery query."""
  src = ar.compile_source(None, units, la.PROFILE, types=types, worlds=worlds)
  need(src["support"]["status"] == "supported", "the control source is %s: %r" % (
    src["support"]["status"], [(u["id"], [d.get("reason") or d.get("code") for d in u["diagnostics"]]) for u in src["units"]
                               if u["status"] != "supported"]))
  q = ar.compile_query(["@id", "Q1", [kind, goal]], src, **sel)
  return src, q, ls.compile_profile(src, q, choice)


def run_plan(result, sequence):
  """The records of every prefix of a sequence (source spelling), from one fresh context."""
  ctx = asum.load(result["profile"])
  return [ctx.get_actions([G(a) for a in sequence[:i]]) for i in range(len(sequence) + 1)]


def facts(record):
  return None if record.world is None else sorted(rp.show_atom(ac_source(f)) for f in record.facts())


def ac_source(t):
  import action_gk
  return action_gk.source_term(t)


def subset(src, q, result, sequence, where, exact=False):
  """The summary of every replay-valid prefix is a subset of the replay's export; returns the number of prefixes."""
  r = rp.replay(src, sequence, planning_root=q["planning_root"], ambient=q["ambient"], knower=q["knower"], export=True)
  if r["verdict"] == "inconsistent_action_state" and r["step"] == 0 or not r.get("export"):
    return 0
  records = run_plan(result, sequence[:r["checked_prefix"]])
  fams = result["profile"]["semantic"]["families"]
  for i, rec in enumerate(records):
    if rec.world is None:
      need(not exact, "%s: prefix %d has no list (%s)" % (where, i, rec.world_reason))
      continue
    full = {asum.freeze(G(f)) for f in r["export"][i]}
    need(set(rec.world) <= full, "%s: prefix %d lists %s outside the replay's export" % (
      where, i, sorted(map(str, set(rec.world) - full))))
    if exact:
      mine = {f for f in full if asum.family_of(f) in fams}
      need(set(rec.world) == mine and rec.world, "%s: prefix %d is %s, the replay has %s" % (where, i, rec.facts(), sorted(mine)))
  return len(records)


# ---------------------------------------------------------------------------


def load_formal():
  out = []
  for path in sorted(glob.glob(os.path.join(SUMMARY, "*.json"))):
    with open(path) as f:
      fx = json.load(f)
    src = ar.compile_source(None, [u["stage2"] for u in fx["units"]], la.PROFILE, entities=fx["entities"])
    q = ar.compile_query(fx["queries"][0]["stage2"], src)
    out.append((fx, src, q, ls.compile_profile(src, q, fx["summary"]["choice"])))
  return out


def check_formal(formal):
  need(sorted(fx["id"] for fx, s, q, r in formal) == ["reverse_tower", "ticket_travel", "two_leg_travel", "unstack"],
       "the four formal controls")
  n = 0
  for fx, src, q, r in formal:
    w, want = fx["id"], fx["summary"]
    need(r["status"] == "ready" and r["choice"]["invalid"] is None, "%s: %s %s" % (w, r["status"], r["reason"]))
    sem = r["profile"]["semantic"]
    need(sem["families"] == want["families"] and sem["score"]["template"] == want["template"],
         "%s: families %s, template %s" % (w, sem["families"], sem["score"]["template"]))
    records = run_plan(r, want["sequence"])
    for i, (rec, exp) in enumerate(zip(records, want["prefixes"])):
      need(rec.facts() == exp["world"] and rec.progress == exp["progress"] and rec.lossy == exp["lossy"]
           and rec.calculation == "computed", "%s: prefix %d is %r, frozen %r" % (w, i, rec.as_json(), exp))
    rv = rp.replay(src, want["sequence"], goal=q["query"]["goal"])
    need(rv["verdict"] == "valid", "%s: the supplied sequence is %s" % (w, rv["verdict"]))
    need(subset(src, q, r, want["sequence"], w, exact=True) == len(want["prefixes"]), "%s: every prefix is compared" % w)
    n += len(records)
  print("  formal: the 4 formal controls give their frozen lists and scores at %d prefixes (-2,-1,-1,0; -2,-1,-1,-1,0; "
        "-2,-1,0; -4,-3,-2,0), lossy false, each list equal to the replay's export of the tracked families" % n)


def check_ledger(formal):
  n = ops = 0
  for fx, src, q, r in formal:
    b = r["profile"]["binding"]
    objs = ar.query_input(src, q, "plan", "positive")
    names = [o["@name"] for o in objs]
    need([e["name"] for e in b["coverage"]] and sorted(e["name"] for e in b["coverage"]) == sorted(names),
         "%s: the ledger has one entry per input clause" % fx["id"])
    need(all(e["disposition"] and e["disposition"] != "unsupported-writer" for e in b["coverage"]),
         "%s: every input clause has a disposition" % fx["id"])
    listed = {p["operation"] for p in b["operations"]}
    for op in r["profile"]["semantic"]["operations"]:
      need(asum.digest(op) in listed, "%s: an operation without provenance: %r" % (fx["id"], op))
    need(all(p["clauses"] or p["notes"] for p in b["operations"]), "%s: an operation names a clause or a policy" % fx["id"])
    import action_gk
    import hashlib
    need(b["input_sha256"] == hashlib.sha256(action_gk.input_text(objs).encode()).hexdigest() and b["view_hash"] == q["view_hash"]
         and b["query_hash"] == q["hash"] and b["question"] == "query:Q1:plan:positive", "%s: the binding" % fx["id"])
    n += len(b["coverage"])
    ops += len(b["operations"])
  u = [r for fx, s, q, r in formal if fx["id"] == "unstack"][0]["profile"]["binding"]
  by = {e["name"]: e for e in u["coverage"]}
  need(by["chg_take_on"]["disposition"] == "change-marker" and by["eff_take_holding"]["disposition"] == "possible-write"
       and by["eff_take_clear"]["disposition"] == "excluded-family" and by["frame_on"]["disposition"] == "frame"
       and by["eff_move_at"]["disposition"] == "excluded-family" and by["ordinary:V1-core:on_not_under"]["disposition"] == "standing-writer"
       and by["src:S3:initial_fact:5"]["disposition"] == "initial", "unstack: the dispositions of the named clauses")
  used = sorted({c for p in u["operations"] for c in p["clauses"]})
  need(used == ["chg_put_in_holding", "chg_put_on_holding", "chg_take_on", "eff_put_in_not_holding", "eff_put_on_not_holding",
                "eff_put_on_on", "eff_take_holding", "eff_take_not_on"], "unstack: the clauses behind its operations: %s" % used)
  print("  ledger: %d input clauses have a disposition, %d operations name their clauses; the unstack operations come "
        "from the 8 library clauses of the design table" % (n, ops))


def check_cache(formal):
  r = [r for fx, s, q, r in formal if fx["id"] == "unstack"][0]
  ctx = asum.load(r["profile"])
  s1 = ["$do", G(["take", H, C]), "W0"]
  s2 = ["$do", G(["put_on", H, C, T]), s1]
  s3 = ["$do", G(["take", H, A]), s2]
  rec3, why = ctx.get(s3)
  need(why is None and ctx.advance_calls == 3 and rec3.progress == 0, "a new three-action plan costs three transitions")
  need(ctx.get(s3)[0] is rec3 and ctx.advance_calls == 3, "a repeated request costs none and returns the same record")
  rec1 = ctx.get(s1)[0]
  before = (rec1.world, rec1.progress)
  sib, _ = ctx.get(["$do", G(["put_on", H, C, A]), s1])
  need(ctx.advance_calls == 4, "a sibling branch costs one transition from the stored prefix")
  root = ctx.get("W0")[0]
  need(sib.world == root.world and sib is not root and sib.progress == -2 and sib.parent is rec1,
       "putting c back gives the root's list in a separate record")
  ext, _ = ctx.get(["$do", G(["put_on", H, A, C]), s3])
  need(ctx.advance_calls == 5 and ext.parent is rec3, "a one-action extension costs one transition")
  need((rec1.world, rec1.progress) == before and rec3.parent.parent is rec1, "a record does not change after its children")
  try:
    rec1.world = ()
    need(False, "a record is immutable")
  except AttributeError:
    pass
  print("  cache: 3 transitions for a new three-action plan, 0 for its repetition, 1 for a sibling, 1 for an extension; "
        "the shared prefix record is unchanged")


def _hand_profile(operations, initial, score=None, families=("have", "rel:located_at")):
  sem = asum.normalize({
    "contract": {"summary": asum.CONTRACT, "normalizer": asum.NORMALIZER, "transport": None}, "root": "W0",
    "scope": {"ambient": None, "knower": None}, "families": list(families), "initial": {"facts": initial, "lossy": False},
    "static": [], "constructors": {c: len(s) for c, s in la.CONSTRUCTORS.items()}, "operations": operations,
    "score": score or {"template": None, "reason": "none"},
    "situation_constructor": {"functor": "$do", "arity": 2, "action_arg": 1, "parent_arg": 2}, "situation_positions": []})
  return {"schema": asum.SCHEMA, "profile_id": asum.profile_id(sem), "semantic": sem, "binding": {}}


def check_updates():
  # a stamp granted by the bus only; a ticket consumed by the train only
  stamp, ticket = "stamp 5", "ticket 6"
  units = TRAVEL + [S("S4", ["after", BUS, ["have", ANN, stamp]]), S("S5", ["have", ANN, ticket]),
                    S("S6", ["after", TRAIN, ["not", ["have", ANN, ticket]]])]
  src, q, r = build(units, ["and", at(ANN, OSLO), ["have", ANN, stamp]])
  need(r["status"] == "ready" and r["profile"]["semantic"]["score"]["template"] == "goal_count", "stamp: %r" % (r["reason"],))
  recs = run_plan(r, [BUS, TRAIN])
  need([facts(x) for x in recs] == [["have(Ann,ticket)", "located_at(Ann,Lund)"],
                                    ["have(Ann,stamp)", "have(Ann,ticket)", "located_at(Ann,Malmo)"],
                                    ["have(Ann,stamp)", "located_at(Ann,Oslo)"]] and [x.progress for x in recs] == [-2, -1, 0]
       and not recs[-1].lossy, "stamp and ticket: %r" % [facts(x) for x in recs])
  ctx = asum.load(r["profile"])
  other = ctx.get_actions([G(TRAIN)])
  need(facts(other) == ["located_at(Ann,Lund)", "located_at(Ann,Oslo)"], "the train alone grants no stamp: %r" % facts(other))
  subset(src, q, r, [BUS, TRAIN], "stamp", exact=True)
  # a repeated variable in an action pattern
  p = _hand_profile([{"kind": "insert", "action": ["move", {"var": "A"}, {"var": "F"}, {"var": "F"}, {"var": "M"}],
                      "fact": ["have", {"var": "A"}, "loop"], "guards": []}], [])
  ctx = asum.load(p)
  need(ctx.get_actions([["move", "x", "p", "p", "foot"]]).facts() == [["have", "x", "loop"]]
       and ctx.get_actions([["move", "x", "p", "q", "foot"]]).facts() == [], "a repeated variable matches equal slots only")
  # a third block on c; a surface goal
  third = BLOCKS[:3] + [S("S4", ["and", ["isa", "block", B], on(B, C)]), S("S5", ["has property", "empty", H]),
                        S("S6", ["has property", "clear_top", B])]
  src, q, r = build(third, on(A, C))
  recs = run_plan(r, [["take", H, B], ["put_on", H, B, T]])
  need([x.progress for x in recs] == [-3, -2, -2] and "on(b,table)" in facts(recs[2]) and "on(c,a)" in facts(recs[2]),
       "a third block: %r %r" % ([x.progress for x in recs], facts(recs[2])))
  src, q, r = build(BLOCKS, on(C, T))
  need(run_plan(r, [])[0].progress == -1, "a surface goal counts no block on the surface")
  # unknown conditional writes, opposing writes, and the lossy score control
  lamp, door, sw = "lamp 5", "door 6", "switch 7"
  press = ["change", ANN, sw, "pressed", "unspecified"]
  base = [S("S1", ["isa", "person", ANN]), S("S2", ["has property", "lit", lamp]), S("S3", ["can", ANN, press])]
  lit, opened = ["has property", "lit", lamp], ["has property", "open", door]
  for name, head in (("negative", ["not", lit]), ("positive", lit)):
    src, q, r = build(base + [S("S4", ["implies", opened, ["after", press, head]])], lit)
    recs = run_plan(r, [press])
    need(facts(recs[0]) == ["lit(lamp)"] and facts(recs[1]) == [] and recs[1].lossy and recs[1].progress == -1,
         "an unknown conditional %s write forgets its target: %r" % (name, facts(recs[1])))
    subset(src, q, r, [press], "conditional " + name)
  # a condition that is false in the full state: the list is smaller than the replay's, and states no negation
  src, q, r = build(base + [S("S4", ["implies", opened, ["after", press, ["not", lit]]]), S("S5", ["not", opened])], lit)
  recs = run_plan(r, [press])
  kept = rp.replay(src, [press], export=True)["export"][1]
  need(facts(recs[1]) == [] and recs[1].lossy and ["has property", "lit", lamp] in kept, "a false guard: the replay keeps lit")
  subset(src, q, r, [press], "false guard")
  src, q, r = build(base + [S("S4", ["after", press, ["and", lit, ["not", lit]]])], lit)
  recs = run_plan(r, [press])
  need(facts(recs[1]) == [] and recs[1].lossy, "an opposing write inserts nothing: %r" % facts(recs[1]))
  subset(src, q, r, [press], "opposing")
  c7 = BLOCKS + [S("S6", ["isa", "person", ANN]), S("S7", ["can", ANN, press]),
                 S("S8", ["implies", lit, ["after", press, ["not", on(C, A)]]])]
  src, q, r = build(c7, holding(H, A))
  recs = run_plan(r, [press])
  need(facts(recs[1]) == ["on(a,table)"] and recs[1].progress == -1 and recs[1].lossy and recs[0].progress == -2
       and not recs[0].lossy, "C7: %r %r %r" % (facts(recs[1]), recs[1].progress, recs[1].lossy))
  later = asum.load(r["profile"]).get_actions([G(press), G(["take", H, A])])
  need(later.lossy and later.progress == 0, "the lossy bit is inherited")
  subset(src, q, r, [press], "C7")
  # a no-op: an audited identity for the tracked families
  src, q, r = build(BLOCKS + [S("S6", ["isa", "person", ANN]), S("S7", ["can", ANN, press])], holding(H, A))
  ctx = asum.load(r["profile"])
  rec = ctx.get_actions([G(press)])
  need(rec.world == ctx.root_node.record.world and not rec.lossy and ctx.advance_calls == 1 and rec.calculation == "computed",
       "an action without an operation on the tracked families keeps the list")
  print("  updates: a bus-only stamp, a train-only consumption, a repeated variable, a third block (-3,-2,-2), a surface "
        "goal (-1), unknown negative and positive conditional writes, a false guard (a smaller list), an opposing write, the lossy control (-2 to -1, "
        "lossy), an audited no-op")


def check_failures(formal):
  r = [r for fx, s, q, r in formal if fx["id"] == "unstack"][0]
  ctx = asum.load(r["profile"])
  take = G(["take", H, C])
  bad = ctx.get_actions([take, ["fly", "#:c 4"]])
  need(bad.world is None and bad.world_reason == "no_rule_for_action" and bad.progress is None
       and bad.calculation == "unavailable", "an unknown constructor gives no list")
  n = ctx.advance_calls
  child = ctx.get_actions([take, ["fly", "#:c 4"], G(["take", H, A])])
  need(child.world is None and child.world_reason == "no_rule_for_action" and ctx.advance_calls == n,
       "a descendant inherits the failure without a transition")
  need(ctx.get_actions([take, G(["put_on", H, C, T])]).progress == -1, "a sibling of a failed step is unaffected")
  need(ctx.get_actions([take, ["take", "#:hand 1"]]).world_reason == "no_rule_for_action", "a wrong arity is no rule")
  for term, why in ((["$do", take, "W1"], "wrong_root"), (["$do", take, "?:S"], "open_root"), ("?:S", "open_root"),
                    (["$do", ["take", "?:H", "#:c 4"], "W0"], "not_ground"), (["$do", take, ["x", "W0"]], "malformed_situation")):
    need(ctx.get(term) == (None, why), "%r gives %s, got %r" % (term, why, ctx.get(term)[1]))
  deep = "W0"
  for _ in range(asum.MAX_DEPTH + 1):
    deep = ["$do", take, deep]
  need(ctx.get(deep) == (None, "depth_limit"), "a term beyond the depth bound")
  # the clause lookup's reference: a ground rooted prefix under an unbound action
  s1 = ["$do", take, "W0"]
  o = ctx.observe(["$do", "?:A", s1])
  need(o["whole"] is False and o["record"] is ctx.get(s1)[0] and o["reason"] == "not_ground", "the prefix under an unbound action")
  need(ctx.observe(["$do", ["take", "?:H", "?:X"], "W0"])["record"] is ctx.root_node.record, "the root alone is a prefix")
  need(ctx.observe(s1)["whole"] is True and ctx.observe(["$do", take, "?:S"]) == {"whole": False, "record": None, "reason": "open_root"},
       "a whole situation; an open root")
  # a backward candidate that is not executable: a calculation, with no usable score
  back = ctx.get_actions([G(["put_on", H, A, C])])
  r2 = [r for fx, s, q, r in formal if fx["id"] == "reverse_tower"][0]
  back = asum.load(r2["profile"]).get_actions([G(["put_on", H, A, C])])
  need(back.calculation == "partial" and back.progress is None and back.progress_reason in ("support_conflict", "support_cycle"),
       "put a on c at the root: %r" % back.as_json())
  print("  failures: no_rule_for_action is stored and inherited, a sibling is unaffected; wrong_root, open_root, "
        "not_ground, malformed_situation, depth_limit; the prefix under an unbound action; an unexecutable candidate "
        "has no score")


def check_defaults(formal):
  # one default table with and without a choice
  src, q, r0 = build(TRAVEL, at(ANN, OSLO))
  for bad in ({"schema": 1, "tracked": ["rel:located_at"], "score": "route_distance", "milestones": [], "update_code": "x"},
              {"schema": 1, "tracked": [{"family": "rel:on", "subjects": ["a", "c"]}], "score": "blocks_links", "milestones": []},
              {"schema": 1, "tracked": ["rel:located_at"], "score": "blocks_links", "milestones": []},
              {"schema": 1, "tracked": ["rel:located_at"], "score": "route_milestones", "milestones": ["ms:none"]},
              {"schema": 1, "tracked": ["property:clear_top"], "score": "goal_count", "milestones": []}):
    r = ls.compile_profile(src, q, bad)
    need(r["choice"]["invalid"] and r["profile"]["profile_id"] == r0["profile"]["profile_id"],
         "an invalid choice gives the default: %r" % (r["choice"],))
  r = ls.compile_profile(src, q, {"schema": 1, "tracked": ["rel:located_at"], "score": "goal_count", "milestones": []})
  need(r["choice"]["origin"] == "choice" and r["profile"]["semantic"]["score"]["template"] == "goal_count"
       and r["profile"]["profile_id"] != r0["profile"]["profile_id"], "a valid choice is used")
  t = [r for fx, s, q, r in formal if fx["id"] == "ticket_travel"][0]
  need(t["choice"]["milestone_catalog"] == {"ms:restriction_1_S4": {"fact": ["have", "#:Ann 1", "#:ticket 5"], "city": "#:Lund 2"}},
       "the milestone catalog of the ticket source: %r" % t["choice"]["milestone_catalog"])
  # the city-only scores of the ticket source, without the milestone: -2,-2,-1,0
  fx, src, q, _ = [x for x in formal if x[0]["id"] == "ticket_travel"][0]
  plain = ls.compile_profile(src, q)
  need([x.progress for x in run_plan(plain, fx["summary"]["sequence"])] == [-2, -2, -1, 0], "the default has no milestone")
  # a blocks goal without the support's type falls back to goal_count
  src, q, r = build(BLOCKS[:1] + [S("S2", ["and", ["isa", "block", A], on(A, T)]), BLOCKS[2]] + BLOCKS[3:], on(C, T))
  need(r["profile"]["semantic"]["score"]["template"] == "goal_count", "an untyped support gives goal_count")
  # a quantified initial description, a standing law and a computed goal
  b = "b 5"
  quant = [S("S1", ["isa", "hand", H]), S("S2", ["and", ["isa", "block", A], ["isa", "block", b], ["isa", "table", T]]),
           S("S3", ["forall", "X", ["implies", ["isa", "block", "X"], on("X", T)]]),
           S("S4", ["state_law", ["forall", "X", ["implies", ["and", ["isa", "block", "X"], on("X", T)], ["has property", "stable", "X"]]]]),
           S("S5", ["has property", "empty", H]), S("S6", ["has property", "clear_top", A]), S("S7", ["has property", "clear_top", b])]
  src, q, r = build(quant, on(A, b))
  recs = run_plan(r, [["take", H, A]])
  need(facts(recs[0]) == ["on(a,table)", "on(b,table)"] and facts(recs[1]) == ["on(b,table)"], "a quantified initial: %r" % facts(recs[0]))
  subset(src, q, r, [["take", H, A], ["put_on", H, A, b]], "quantified", exact=True)
  src, q, r = build(quant, ["has property", "stable", A])
  need(q["outcome"] is None and r["status"] == "unavailable" and r["reason"] == "computed_goal"
       and r["families"]["property:stable"] in ("computed_family", "standing_writer"), "a computed goal: %r %r" % (r["reason"], r.get("families")))
  r = ls.compile_profile(src, q, {"schema": 1, "tracked": ["property:stable"], "score": "goal_count", "milestones": []})
  need(r["status"] == "unavailable" and r["choice"]["invalid"] == "choice_unavailable_family", "a computed family cannot be chosen")
  # a goal with a witness: the list is calculated, the score is undefined
  src, q, r = build(BLOCKS, ["exists", "X", holding(H, "X")])
  need(q["outcome"] is None and r["status"] == "partial" and r["reason"] == "witness_goal"
       and r["profile"]["semantic"]["families"] == ["rel:holding"], "a witness goal: %r" % (r["status"],))
  rec = run_plan(r, [["take", H, C]])[1]
  need(facts(rec) == ["holding(hand,c)"] and rec.progress is None and rec.progress_reason == "witness_goal"
       and rec.calculation == "partial", "a witness goal has a list and no score: %r" % rec.as_json())
  r = ls.compile_profile(src, q, {"schema": 1, "tracked": ["rel:on"], "score": "goal_count", "milestones": []})
  need(r["choice"]["invalid"] == "choice_score_not_applicable" and r["status"] == "partial", "a witness goal has no applicable score")
  print("  defaults: five invalid choices give the default profile, a valid choice is used; the milestone catalog; the "
        "city-only ticket scores -2,-2,-1,0; an untyped support gives goal_count; a quantified initial description; a "
        "computed goal is unavailable and leaves the query unchanged; a witness goal has a list and no score")


def check_audit(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  records, objs = ls._view(src, q)
  ctx = lambda s: ["$ctxt", "present", s, "?:Lh", "$obj"]
  put = ["put_on", "?:H", "?:X", "?:Y"]
  extra = {"name": "eff_put_on_clears", "role": "effect", "origin": "library", "clause": {"@name": "eff_put_on_clears", "@logic": [
    ["-poss", put, ["$ctxt", "present", "?:S", "?:L1", "$obj"]], ["-is rel2", "on", "?:Y", "?:Z", ctx(["$do", put, "?:S"])]]}}
  a = ls._audit(records + [extra])
  ops, _ = ls._operations(a["writes"], a["frames"], ["rel:holding", "rel:on"])
  new = sorted({asum.canonical(asum.normalize_operation(o)) for o, c, n in ops})
  old = sorted(asum.canonical(o) for o in r["profile"]["semantic"]["operations"])
  need(set(old) < set(new) and len(new) == len(old) + 2, "an added writer gives new operations")
  p = copy.deepcopy(r["profile"])
  p["semantic"]["operations"] = [json.loads(x) for x in new]
  p["semantic"] = asum.normalize(p["semantic"])
  p["profile_id"] = asum.profile_id(p["semantic"])
  need(p["profile_id"] != r["profile"]["profile_id"], "an added writer changes the identity")
  seq = [G(["take", H, C]), G(["put_on", H, C, T]), G(["take", H, A]), G(["put_on", H, A, T])]
  stale, fresh = asum.load(r["profile"]).get_actions(seq[:1] + [G(["put_on", H, C, A])]), None
  fresh = asum.load(p).get_actions(seq[:1] + [G(["put_on", H, C, A])])
  need(["is rel2", "on", "#:a 2", "#:table 3"] in stale.facts() and ["is rel2", "on", "#:a 2", "#:table 3"] not in fresh.facts()
       and fresh.lossy is False, "the old program keeps a fact that the added writer removes")
  unknown = dict(extra, role="consequence", name="x_unknown")
  need(ls._audit(records + [unknown])["bad"].get("rel:on") == "unsupported_writer", "a clause of an unknown role disables its family")
  odd = dict(extra, name="x_shape", clause={"@logic": extra["clause"]["@logic"] + [["is rel2", "in", "?:X", "?:Y", ctx(["$do", put, "?:S"])]]})
  bad = ls._audit(records + [odd])["bad"]
  need(bad.get("rel:on") == "unsupported_writer" and bad.get("rel:in") == "unsupported_writer", "an effect outside the shape")
  frames = [x for x in records if x["name"] == "frame_on"]
  broken = copy.deepcopy(frames[0])
  broken["clause"]["@logic"] = broken["clause"]["@logic"][:3]
  need(ls._audit([x for x in records if x["name"] != "frame_on"] + [broken])["bad"].get("rel:on") == "unsupported_writer",
       "a frame without its blocker")
  a = ls._audit([x for x in records if x["name"] != "frame_on"])
  ops, _ = ls._operations(a["writes"], a["frames"], ["rel:on"])
  need(sum(1 for o, c, n in ops if n == "no_persistence_rule") == len(la.CONSTRUCTORS), "a family without a frame is forgotten by every constructor")
  need(ls._audit(records)["bad"] == {"rel:under": "standing_writer", "rel:below": "standing_writer"}, "the V1-core heads")
  print("  audit: an added writer changes the operations and the identity, and the old program keeps the stale fact; an "
        "unknown role, an effect outside the shape and a frame without its blocker disable their families; a family "
        "without a frame is forgotten at every step; the selected ordinary laws write under and below only")


def check_scope():
  two = [S("S1", ["and", ["isa", "person", ANN], at(ANN, LUND)]), S("S2", ["connected", LUND, MALMO, "bus"]),
         S("S3", ["connected", MALMO, OSLO, "train"]), S("S4", at(ANN, MALMO), "W1")]
  ids = {}
  for root in ("W0", "W1"):
    src, q, r = build(two, at(ANN, OSLO), worlds=["W0", "W1"], planning_root=root)
    need(r["status"] == "ready" and r["profile"]["semantic"]["root"] == root, "root %s: %r" % (root, r["reason"]))
    ids[root] = r["profile"]["profile_id"]
    ctx = asum.load(r["profile"])
    need(ctx.get("W0" if root == "W1" else "W1") == (None, "wrong_root"), "the other world is a wrong root")
    need(ctx.root_node.record.progress == (-2 if root == "W0" else -1), "the root score of %s" % root)
  need(ids["W0"] != ids["W1"], "two roots give two identities")
  src = ar.compile_source(None, TRAVEL, la.PROFILE)
  for sel in ({"knower": ANN}, {"ambient": LUND}):
    q = ar.compile_query(["@id", "Q1", ["plan", at(ANN, OSLO)]], src, **sel)
    r = ls.compile_profile(src, q)
    need(r["status"] == "unavailable" and r["reason"].split(":")[0] in ("context_projection", "not_a_runnable_discovery_query"),
         "%r: %r" % (sel, r["reason"]))
  q = ar.compile_query(["@id", "Q1", ["question", at(ANN, LUND)]], src)
  need(ls.compile_profile(src, q)["reason"] == "not_a_runnable_discovery_query: question", "a snapshot question has no profile")
  print("  scope: two planning roots give two profile identities and each refuses the other root; a knower or an "
        "ambient gives context_projection; a snapshot question has no profile")


def check_transport():
  bag, case = "bag 5", "case 6"
  goal = at(ANN, OSLO)
  # luggage held at the start: its location is forgotten when Ann moves, Ann's own is kept
  src, q, r = build(TRAVEL + [S("S4", ["and", holding(ANN, bag), at(bag, LUND)])], goal)
  need(r["status"] == "ready" and r["profile"]["semantic"]["contract"]["transport"] == ls.TRANSPORT_CONTRACT, "held luggage: %r" % r["reason"])
  recs = run_plan(r, [BUS])
  need(facts(recs[0]) == ["located_at(Ann,Lund)", "located_at(bag,Lund)"] and facts(recs[1]) == ["located_at(Ann,Malmo)"]
       and recs[1].lossy and recs[1].progress == -1, "held luggage: %r" % facts(recs[1]))
  subset(src, q, r, [BUS, TRAIN], "held luggage")
  # luggage that may be taken but is not held: the same erasure, a disclosed loss; the replay keeps the location
  may = TRAVEL + [S("S4", at(bag, LUND)), S("S5", ["can", ANN, ["take", ANN, bag]])]
  src, q, r = build(may, goal)
  recs = run_plan(r, [BUS])
  need(facts(recs[1]) == ["located_at(Ann,Malmo)"] and recs[1].lossy, "luggage that may be taken: %r" % facts(recs[1]))
  need(subset(src, q, r, [BUS, TRAIN], "may take") == 3, "the plan without the take is valid in the replay")
  # an explicit location write establishes the new location
  src, q, r = build(TRAVEL + [S("S4", ["and", holding(ANN, bag), at(bag, LUND)]), S("S5", ["after", BUS, at(bag, MALMO)])], goal)
  recs = run_plan(r, [BUS, TRAIN])
  need(facts(recs[1]) == ["located_at(Ann,Malmo)", "located_at(bag,Malmo)"] and facts(recs[2]) == ["located_at(Ann,Oslo)"],
       "an explicit location write: %r" % [facts(x) for x in recs])
  subset(src, q, r, [BUS, TRAIN], "explicit write")
  # a variable carrier: a text effect lets any person hold the case
  grab = ["change", "P", case, "grabbed", "unspecified"]
  var = TRAVEL + [S("S4", at(case, LUND)), S("S5", ["forall", "P", ["implies", ["isa", "person", "P"], ["can", "P", grab]]]),
                  S("S6", ["forall", "P", ["after", grab, holding("P", case)]])]
  src, q, r = build(var, goal)
  need(r["status"] == "ready", "variable carrier: %r" % r["reason"])
  inv = r["profile"]["binding"]["transport_inventory"]
  need([(e["holder"], e["object"], e["through"]) for e in inv] == [("P", case, "text_effect")], "the inventory: %r" % inv)
  recs = run_plan(r, [["change", ANN, case, "grabbed", "unspecified"], BUS])
  need(facts(recs[1]) == ["located_at(Ann,Lund)", "located_at(case,Lund)"] and facts(recs[2]) == ["located_at(Ann,Malmo)"]
       and recs[2].lossy, "a variable carrier: %r" % [facts(x) for x in recs])
  # a holder typed through a type record of the source
  typed = [S("S1", at(ANN, LUND)), TRAVEL[1], TRAVEL[2], S("S4", ["and", holding(ANN, bag), at(bag, LUND)])]
  src, q, r = build(typed, goal, types=[{"entity": ANN, "class": "person", "kind": "stated", "unit": "S1"}])
  need(r["status"] == "ready" and facts(run_plan(r, [BUS])[1]) == ["located_at(Ann,Malmo)"], "a holder typed by a type record")
  # a quantified initial holding, and a type that only a static rule gives: the family is refused
  src, q, r = build(TRAVEL + [S("S4", ["and", ["isa", "bag", bag], at(bag, LUND)]),
                              S("S5", ["forall", "X", ["implies", ["isa", "bag", "X"], holding(ANN, "X")]])], goal)
  need(r["status"] == "unavailable" and r["families"]["rel:located_at"].startswith("transport_inventory_incomplete"),
       "a quantified initial holding: %r" % (r,))
  robot = "Robo 7"
  src, q, r = build(TRAVEL + [S("S4", ["and", ["isa", "robot", robot], at(robot, LUND), holding(robot, bag), at(bag, LUND)]),
                              S("S5", ["forall", "X", ["implies", ["isa", "robot", "X"], ["isa", "person", "X"]]])], goal)
  need(r["status"] == "unavailable" and "inferred type" in r["families"]["rel:located_at"], "an inferred person type: %r" % (r,))
  need(q["outcome"] is None, "the ordinary query still compiles")
  print("  transport: held luggage and luggage that may be taken lose their location when the holder moves (lossy, "
        "subset of the replay); an explicit location write is kept; a variable carrier; a holder typed by a type "
        "record; a quantified initial holding and an inferred person type refuse rel:located_at")


def check_identity(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  p = r["profile"]
  again = ls.compile_profile(src, q)["profile"]
  need(asum.canonical(again) == asum.canonical(p), "the compiler is deterministic")
  text = json.dumps(p, indent=3, ensure_ascii=False)
  need(asum.loads(text) == p and asum.load(asum.loads(text)).profile_id == p["profile_id"], "indentation does not change a profile")
  b = copy.deepcopy(p)
  b["binding"]["implementation"]["action_replay.py"] = "0" * 64
  asum.validate(b)                # the binding is no part of the identity
  for change in (lambda s: s["initial"]["facts"].pop(), lambda s: s["operations"].pop(), lambda s: s["score"].update(goal=[["is rel2", "on", "#:a 2", "#:c 4"]]),
                 lambda s: s.update(root="W1")):
    c = copy.deepcopy(p)
    change(c["semantic"])
    need(asum.profile_id(c["semantic"]) != p["profile_id"], "a semantic change gives another identity")
    try:
      asum.validate(c)
      need(False, "a changed semantic part with the old identifier is refused")
    except asum.ProfileError:
      pass
  need(asum.loads('{"binding": {"raw": 1.5}, "semantic": {"a": 1}}')["binding"]["raw"] == 1.5, "the binding may hold a fraction")
  for bad in ('{"a": 1, "a": 2}', '{"semantic": {"a": 1.5}}', '{"semantic": {"a": 1e3}}', '{"binding": {"a": NaN}}',
              '{"binding": {"a": -Infinity}}', '{"semantic": {"a": 9007199254740992}}'):
    try:
      asum.loads(bad)
      need(False, "%s is refused" % bad)
    except asum.ProfileError:
      pass
  ops = p["semantic"]["operations"]
  shuffled = copy.deepcopy(p["semantic"])
  shuffled["operations"] = [dict(o, action=[o["action"][0]] + [{"var": "Q" + x["var"]} if isinstance(x, dict) and "var" in x else x
                                                               for x in o["action"][1:]]) for o in reversed(ops)]
  for o in shuffled["operations"]:
    for k in ("pattern", "fact"):
      if k in o:
        o[k] = [{"var": "Q" + x["var"]} if isinstance(x, dict) and "var" in x else x for x in o[k]]
  need(asum.profile_id(asum.normalize(shuffled)) == p["profile_id"], "operation order and variable names do not change the identity")
  for mutate, what in ((lambda s: s["operations"].append({"kind": "erase", "action": ["take", "a", "b"], "pattern": ["have", "a", "b"]}), "kind"),
                       (lambda s: s["operations"].append({"kind": "insert", "action": ["take", {"var": "V0"}, {"var": "V1"}],
                                                          "fact": ["is rel2", "on", {"var": "V1"}, {"var": "V9"}], "guards": []}), "unbound"),
                       (lambda s: s["operations"].append({"kind": "insert", "action": ["take", {"var": "V0"}, {"var": "V1"}],
                                                          "fact": ["is rel2", "on", {"var": "V1"}, {"wildcard": True}], "guards": []}), "wildcard"),
                       (lambda s: s["operations"].append({"kind": "forget", "action": ["fly", {"var": "V0"}], "pattern": ["have", "a", "b"], "loss": None}), "constructor"),
                       (lambda s: s["initial"]["facts"].append(["is rel2", "on", "?:X", "#:a 2"]), "ground"),
                       (lambda s: s["initial"]["facts"].append(["is rel2", "in", "#:c 4", "#:a 2"]), "family"),
                       (lambda s: s.update(extra=1), "field")):
    c = copy.deepcopy(p)
    mutate(c["semantic"])
    try:
      c["semantic"] = asum.normalize(c["semantic"])
      c["profile_id"] = asum.profile_id(c["semantic"])
      asum.validate(c)
      need(False, "a profile with a wrong %s is refused" % what)
    except asum.ProfileError:
      pass
  print("  identity: deterministic; indentation, binding, operation order and variable names leave the identifier; a "
        "changed initial list, operation, goal or root changes it; a duplicate key, a fraction or a large integer in the "
        "semantic part, NaN, Infinity and 7 malformed profiles are refused; a fraction in the binding is read")


def _refused(profile, mutate, whole=False):
  """True when the changed profile gives ProfileError.  Any other exception is a failure of the check."""
  c = copy.deepcopy(profile)
  mutate(c if whole else c["semantic"])
  try:
    c["semantic"] = asum.normalize(c["semantic"])
    c["profile_id"] = asum.profile_id(c["semantic"])
    asum.validate(c)
  except asum.ProfileError:
    return True
  return False


def check_boundaries(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  p = r["profile"]
  ok = {"schema": 1, "tracked": ["rel:on"], "score": "goal_count", "milestones": []}
  choices = [dict(ok, score=[]), dict(ok, score={}), dict(ok, schema=1.5), dict(ok, schema=True), dict(ok, schema=1.0),
             dict(ok, tracked=[[]]), dict(ok, tracked="rel:on"), dict(ok, milestones=[{}]), dict(ok, milestones=None), [ok], "x", 7]
  for bad in choices:
    got = ls.compile_profile(src, q, bad)
    need(got["choice"]["invalid"] and got["profile"]["profile_id"] == p["profile_id"], "the choice %r takes the default" % (bad,))
    back = asum.loads(json.dumps(got["profile"]))
    need(back == got["profile"] and asum.load(back).profile_id == p["profile_id"], "the profile of the choice %r reloads" % (bad,))
  need(ls.compile_profile(src, q, ok)["choice"]["origin"] == "choice", "the valid form of that choice is used")
  pos = lambda **f: (lambda s: s["situation_positions"].append(dict({"predicate": "poss", "arity": 2, "path": [2, 2], "via": "$ctxt",
                                                                      "role": "context"}, **f)))
  need(not _refused(p, pos()), "a context position of the closed form is accepted")
  take = ["take", {"var": "V0"}, {"var": "V1"}]
  mutations = [
    ("a Boolean arity", pos(arity=True)), ("a Boolean path index", pos(path=[True, 2])), ("an empty path", pos(path=[])),
    ("an unknown position field", pos(surprise=1)), ("a context path outside the last argument", pos(path=[1, 2])),
    ("a zero arity", pos(arity=0)), ("an unknown role", pos(role="plan")),
    ("a query_plan path outside the arity", lambda s: s["situation_positions"].append({"predicate": "$defq0", "arity": 2, "path": [3], "role": "query_plan"})),
    ("a reachable position with a variable arity", lambda s: s["situation_positions"].append({"predicate": "reachable", "arity": "variable", "path": [1], "role": "reachable"})),
    ("null positions", lambda s: s.update(situation_positions=None)), ("a scope that is no object", lambda s: s.update(scope=7)),
    ("a scope with a knower", lambda s: s.update(scope={"ambient": None, "knower": "x"})),
    ("an integer of 2**80", lambda s: s["static"].append(["n", 2 ** 80])), ("an integer of 2**53", lambda s: s["static"].append(["n", 2 ** 53])),
    ("a Boolean in $do", lambda s: s["situation_constructor"].update(action_arg=True)),
    ("a Boolean normalizer", lambda s: s["contract"].update(normalizer=True)),
    ("an extra contract field", lambda s: s["contract"].update(extra=1)),
    ("a Boolean constructor arity", lambda s: s["constructors"].update(take=True)),
    ("null operations", lambda s: s.update(operations=None)), ("a null score", lambda s: s.update(score=None)),
    ("an operation that is no object", lambda s: s["operations"].append(7)),
    ("an unknown score field", lambda s: s["score"].update(extra=1)),
    ("a Boolean term", lambda s: s["initial"]["facts"].append(["is rel2", "on", True, "#:a 2"])),
    ("a lossy bit that is a number", lambda s: s["initial"].update(lossy=1)),
    ("a forget of an untracked family", lambda s: s["operations"].append({"kind": "forget", "action": take, "pattern": ["have", {"var": "V0"}, {"var": "V1"}], "loss": None})),
    ("a forget whose pattern is no fact", lambda s: s["operations"].append({"kind": "forget", "action": take, "pattern": ["is rel2", {"var": "V0"}, "x", "y"], "loss": None})),
    ("an old guard of an untracked family", lambda s: s["operations"].append({"kind": "insert", "action": take, "fact": ["is rel2", "on", {"var": "V1"}, {"var": "V0"}],
                                                                               "guards": [{"scope": "old", "atom": ["have", {"var": "V0"}, {"var": "V1"}]}]})),
    ("a guard that is no object", lambda s: s["operations"].append({"kind": "insert", "action": take, "fact": ["is rel2", "on", {"var": "V1"}, {"var": "V0"}], "guards": [7]})),
    ("a static fact that is no list", lambda s: s["static"].append("x"))]
  for what, mutate in mutations:
    need(_refused(p, mutate), "%s gives ProfileError" % what)
  for what, mutate in (("a binding that is no object", lambda c: c.update(binding=[])), ("a null semantic part", lambda c: c.update(semantic=None)),
                       ("an extra profile field", lambda c: c.update(extra=1))):
    need(_refused(p, mutate, whole=True), "%s gives ProfileError" % what)
  need(not _refused(p, lambda s: s["static"].append(["n", -(2 ** 53 - 1)])), "a negative integer of the range is a legal term")
  # a score outside the range: the list stays, Progress is undefined
  mv, w = ["move", {"var": "A"}, {"var": "F"}, {"var": "T"}, {"var": "M"}], {"wildcard": True}
  big = _hand_profile([{"kind": "forget", "action": mv, "pattern": ["is rel2", "located_at", {"var": "A"}, w], "loss": None},
                       {"kind": "insert", "action": mv, "fact": ["is rel2", "located_at", {"var": "A"}, {"var": "T"}], "guards": []}],
                      [["is rel2", "located_at", "x", "p"]],
                      {"template": "route_milestones", "units": asum.UNITS["route_milestones"], "subject": "x", "destination": "q",
                       "distance": {"p": asum.MAX_INT, "r": 1}, "no_route_distance": 4, "milestones": [{"city": "p", "fact": ["have", "x", "t"]}]})
  ctx = asum.load(big)
  root = ctx.root_node.record
  need(root.progress is None and root.progress_reason == "numeric_range" and root.facts() == [["is rel2", "located_at", "x", "p"]]
       and root.calculation == "partial", "a score outside the range: %r" % root.as_json())
  need(ctx.get_actions([["move", "x", "p", "r", "bus"]]).progress == -2, "a later score inside the range is a number")
  # a sequence with a variable, and the depth bound
  ctx = asum.load(p)
  for seq, why in (([["change", "?:A", "#:switch 8", "pressed", "unspecified"]], "not_ground"), ([G(["take", H, C])] * (asum.MAX_DEPTH + 1), "depth_limit")):
    try:
      ctx.get_actions(seq)
      need(False, "get_actions refuses a sequence that is %s" % why)
    except ValueError as e:
      need(str(e) == why and not ctx.root_node.children and ctx.advance_calls == 0, "get_actions: %s, nothing stored" % why)
  take_c, deep = G(["take", H, C]), "W0"
  for _ in range(asum.MAX_DEPTH):
    deep = ["$do", take_c, deep]
  rec, why = ctx.get(deep)
  need(rec is not None and rec.depth == asum.MAX_DEPTH and why is None, "a term of %d actions has a record" % asum.MAX_DEPTH)
  need(ctx.get(["$do", take_c, deep]) == (None, "depth_limit"), "a term of %d actions has none" % (asum.MAX_DEPTH + 1))
  # one order of reasons for a term with several defects
  open_deep = "?:S"
  for _ in range(asum.MAX_DEPTH + 1):
    open_deep = ["$do", ["take", "?:H", "#:c 4"], open_deep]
  loose = ["take", "?:H", "#:c 4"]
  for term, why in ((open_deep, "depth_limit"), (["$do", loose, "?:S"], "open_root"), (["$do", loose, ["x", "W0"]], "malformed_situation"),
                    (["$do", loose, 7], "malformed_situation"), (["$do", loose, "W1"], "wrong_root"), (["$do", loose, "W0"], "not_ground")):
    need(ctx.get(term)[1] == why and ctx.observe(term)["reason"] == why, "the first reason is %s, got %s" % (why, ctx.get(term)[1]))
  # a failed update: the record exists and the reason says why
  fly = ["$do", ["fly", "#:c 4"], "W0"]
  rec, why = ctx.get(fly)
  o = ctx.observe(fly)
  need(rec.world is None and why == "no_rule_for_action" and o == {"whole": True, "record": rec, "reason": "no_rule_for_action"},
       "a failed update is reported by get and observe")
  o = ctx.observe(["$do", "?:A", fly])
  need(o["whole"] is False and o["reason"] == "not_ground" and o["record"] is rec and rec.world_reason == "no_rule_for_action",
       "a failed prefix under an unbound action")
  need(len({x for xs in asum.REASONS.values() for x in xs}) == 18, "the 18 reason codes")
  # the shared limits: a ground action over a limit is no open action
  def nest(n, leaf="x"):
    t = leaf
    for _ in range(n):
      t = ["box", t]
    return t
  act = lambda arg: ["change", "#:Ann 7", arg, "pressed", "unspecified"]
  ctx = asum.load(p)
  need(asum.term_defect(act(nest(asum.MAX_TERM_DEPTH - 1))) is None and ctx.get(["$do", act(nest(asum.MAX_TERM_DEPTH - 1)), "W0"])[0] is not None,
       "an action of %d levels has a record" % asum.MAX_TERM_DEPTH)
  for arg, why in ((nest(asum.MAX_TERM_DEPTH), "term_depth_limit"), (2 ** 53, "numeric_range"), (-2 ** 53, "numeric_range"), (1.5, "unsupported_term"),
                   (None, "unsupported_term"), (True, "unsupported_term"), ([], "unsupported_term"), ("a\x00b", "unsupported_term"),
                   ("?:X", "not_ground"), (nest(asum.MAX_TERM_DEPTH, "?:X"), "term_depth_limit"), (["f", "?:X", 2 ** 53], "numeric_range"),
                   (["f", "?:X", 1.5], "unsupported_term")):
    term = ["$do", act(arg), ["$do", take_c, "W0"]]
    o = ctx.observe(term)
    need(ctx.get(term) == (None, why) and o["whole"] is False and o["reason"] == why and o["record"] is ctx.get(["$do", take_c, "W0"])[0],
         "the argument %r gives %s and the prefix below it, got %r" % (str(arg)[:40], why, o["reason"]))
    try:
      ctx.get_actions([act(arg)])
      need(False, "get_actions refuses %s" % why)
    except ValueError as e:
      need(str(e) == why, "get_actions: %s" % why)
  need(ctx.observe(["$do", act(1.5), ["$do", act("?:X"), "W0"]])["reason"] == "not_ground", "the oldest defective action gives the reason")
  # a fact built from a deep argument: the update fails with term_depth_limit
  deep = _hand_profile([{"kind": "insert", "action": mv, "fact": ["have", {"var": "A"}, ["wrapped", {"var": "T"}]], "guards": []}], [])
  dctx = asum.load(deep)
  ok_rec = dctx.get_actions([["move", "x", "p", nest(asum.MAX_TERM_DEPTH - 2), "bus"]])
  bad_rec = dctx.get_actions([["move", "x", "p", nest(asum.MAX_TERM_DEPTH - 1), "bus"]])
  need(ok_rec.world is not None and bad_rec.world is None and bad_rec.world_reason == "term_depth_limit", "a built fact over the level limit")
  many = {"kind": "forget", "action": ["take", {"var": "V0"}, [ "f"] + [{"var": "X%d" % i} for i in range(asum.MAX_VARIABLES)]],
          "pattern": ["is rel2", "on", {"var": "V0"}, {"wildcard": True}], "loss": None}
  need(_refused(p, lambda s: s["operations"].append(many)), "an operation with %d variables gives ProfileError" % (asum.MAX_VARIABLES + 1))
  for what, mutate in (("a zero character in a fact", lambda s: s["static"].append(["n", "a\x00b"])),
                       ("a zero character in a key", lambda s: s["constructors"].update({"a\x00b": 1})),
                       ("a fact of %d levels" % (asum.MAX_TERM_DEPTH + 1), lambda s: s["static"].append(nest(asum.MAX_TERM_DEPTH + 1))),
                       ("a constructor arity over the index limit", lambda s: s["constructors"].update(big=asum.MAX_INDEX + 1))):
    need(_refused(p, mutate), "%s gives ProfileError" % what)
  need(not _refused(p, lambda s: s["static"].append(nest(asum.MAX_TERM_DEPTH))), "a fact of %d levels loads" % asum.MAX_TERM_DEPTH)
  b = copy.deepcopy(p)
  b["binding"]["choice"]["raw"] = "a\x00b"
  need(asum.load(asum.loads(json.dumps(b))).profile_id == p["profile_id"], "a zero character in the binding is provenance")
  print("  boundaries: %d malformed choices take the default and their profiles reload; %d malformed profiles give "
        "ProfileError; a score outside -(2**53-1)..2**53-1 is numeric_range with its list kept; get_actions refuses a "
        "variable and %d actions; %d actions have a record; the order depth_limit, open_root, malformed_situation, "
        "wrong_root, not_ground; get and observe report a failed update; an action of 64 levels has a record, 65 levels "
        "give term_depth_limit, an integer of 2**53 numeric_range, a fraction unsupported_term, each with the prefix "
        "below it; a zero character, 65 variables and an arity over 1000000 are refused in the semantic part" % (len(choices), len(mutations) + 3, asum.MAX_DEPTH + 1, asum.MAX_DEPTH))


def check_ownership(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  mine = copy.deepcopy(r["profile"])
  ctx, ref = asum.load(mine), asum.load(r["profile"])
  first = ctx.get_actions([G(["take", H, C])])
  mine["semantic"]["score"]["goal"] = [["is rel2", "on", "#:a 2", "#:table 3"]]
  del mine["semantic"]["operations"][:]
  mine["semantic"]["initial"]["facts"].pop()
  press = ["change", "#:Ann 7", "#:switch 8", "pressed", "unspecified"]
  seqs = ([press], [G(["take", H, C])], [G(["take", H, C]), G(["put_on", H, C, T])], [G(["take", H, C]), G(["put_on", H, C, T]), G(["take", H, A])])
  for seq in seqs:
    a, b = ctx.get_actions(seq), ref.get_actions(seq)
    need(a.as_json() == b.as_json(), "after the caller's change %r gives %r, the unchanged profile %r" % (seq, a.as_json(), b.as_json()))
  need(ctx.get_actions([G(["take", H, C])]) is first and ctx.root_node.record.progress == -2 and ctx.profile_id == r["profile"]["profile_id"],
       "the stored prefixes are unchanged")
  mine["semantic"] = asum.normalize(mine["semantic"])
  mine["profile_id"] = asum.profile_id(mine["semantic"])
  other = asum.load(mine)
  need(other.profile_id != ctx.profile_id and other.root_node.record.progress == 0, "the changed profile, loaded under its own identifier, calculates differently")
  print("  ownership: after loading, a change of the caller's score, operations and initial facts changes no stored "
        "and no new prefix; the changed profile under its own identifier calculates differently")


def check_loss(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  records, objs = ls._view(src, q)
  a = ls._audit([x for x in records if x["name"] != "frame_on"])
  ops, _ = ls._operations(a["writes"], a["frames"], ["rel:holding", "rel:on"])
  need(all(o["loss"] == "if_removed" for o, c, n in ops if n == "no_persistence_rule"), "a forget without a persistence rule is no certain deletion")
  p = copy.deepcopy(r["profile"])
  p["semantic"]["operations"] = [o for o, c, n in ops]
  p["semantic"] = asum.normalize(p["semantic"])
  p["profile_id"] = asum.profile_id(p["semantic"])
  press = ["change", "#:Ann 7", "#:switch 8", "pressed", "unspecified"]
  ctx = asum.load(p)
  rec = ctx.get_actions([press])
  need(rec.facts() == [] and rec.progress == -1 and rec.lossy and not ctx.root_node.record.lossy, "no frame: the removed facts set lossy: %r" % rec.as_json())
  need(ctx.get_actions([press, G(["take", H, A])]).lossy, "a descendant inherits the bit")
  p["semantic"]["initial"]["facts"] = []
  p["profile_id"] = asum.profile_id(p["semantic"])
  rec = asum.load(p).get_actions([press])
  need(rec.facts() == [] and not rec.lossy, "an empty family sets no bit")
  ctx = asum.load(p)
  put = ctx.get_actions([G(["take", H, C]), G(["put_on", H, C, T])])
  need(put.facts() == [G(on(C, T))] and not put.lossy, "a written fact of that family is present and no loss: %r" % put.as_json())
  rec = ctx.get_actions([G(["take", H, C]), G(["put_on", H, C, T]), press])
  need(rec.facts() == [] and rec.lossy, "the written fact is lost at the next step")
  # a replay witness: the compiler's witness records decide, by the term itself
  init = [["has property", "empty", "hand 1"], ["is rel2", "on", "a 2", "table 3"], ["is rel2", "on", "sk_X", "a 2"]]
  need(ls._initial(init, ["rel:on"], ["sk_X"], set()) == ([G(on(A, T))], True), "a witness without a record is left out and is a loss")
  need(ls._initial(init, ["rel:on"], ["sk_X"], {"sk_X"}) == ([G(on(A, T)), ["is rel2", "on", "sk_X", "#:a 2"]], False), "a recorded witness is kept")
  need(ls._initial(init, ["property:empty"], ["sk_X"], set()) == ([["has property", "empty", "#:hand 1"]], False),
       "a witness in an unselected family is no loss")
  need(ls._initial([["is rel2", "on", "a 2", 'the "sk_X" block']], ["rel:on"], ["sk_X"], set())[1] is False, "a name that only contains the witness text is no witness")
  ex = [S("S1", ["isa", "hand", H]), S("S2", ["and", ["isa", "block", A], ["isa", "table", T], on(A, T)]),
        S("S3", ["exists", "X", ["and", ["isa", "block", "X"], on("X", A)]]), S("S5", ["has property", "empty", H])]
  src2, q2, r2 = build(ex, holding(H, A))
  ini = r2["profile"]["semantic"]["initial"]
  need(ini == {"facts": [G(on(A, T)), ["is rel2", "on", "sk_X", "#:a 2"]], "lossy": False}, "an existential description: %r" % ini)
  # a guard in another stored family: left out by default, admitted by an explicit choice of both families
  lamp, door, sw = "lamp 5", "door 6", "switch 7"
  press = ["change", ANN, sw, "pressed", "unspecified"]
  lit, opened = ["has property", "lit", lamp], ["has property", "open", door]
  units = [S("S1", ["isa", "person", ANN]), S("S2", opened), S("S3", ["can", ANN, press]), S("S4", ["implies", opened, ["after", press, lit]])]
  src3, q3, r3 = build(units, lit)
  om = r3["profile"]["binding"]["omitted_insertions"]
  need(r3["profile"]["semantic"]["families"] == ["property:lit"] and [(o["family"], o["reason"]) for o in om] == [("property:lit", "guard_untracked_family")],
       "the default leaves the insertion out: %r" % om)
  rec = run_plan(r3, [press])[1]
  need(facts(rec) == [] and rec.lossy and rec.progress == -1, "the default: no list, lossy: %r" % rec.as_json())
  subset(src3, q3, r3, [press], "guard default")
  r4 = ls.compile_profile(src3, q3, {"schema": 1, "tracked": ["property:lit", "property:open"], "score": "goal_count", "milestones": []})
  need(r4["choice"]["origin"] == "choice" and r4["profile"]["binding"]["omitted_insertions"] == [], "the choice of both families: %r" % (r4["choice"],))
  recs = run_plan(r4, [press])
  need(facts(recs[0]) == ["open(door)"] and facts(recs[1]) == ["lit(lamp)", "open(door)"] and not recs[1].lossy and recs[1].progress == 0,
       "both families: %r" % recs[1].as_json())
  need(subset(src3, q3, r4, [press], "guard choice", exact=True) == 2, "both families equal the replay")
  print("  loss: without a persistence rule a removed fact sets lossy (-2 to -1, lossy), an empty family does not, a "
        "descendant inherits; a replay witness without a compiler record is a root loss, a recorded one is kept; a guard "
        "in an unselected family omits the insertion by default (lossy) and an explicit choice of both families equals the replay")


def check_selectors(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "unstack"][0]
  helper = lambda res: [x for x in res["profile"]["semantic"]["situation_positions"] if x["role"] == "query_plan"]
  need(helper(r) == [{"predicate": "$defq0", "arity": 1, "path": [1], "role": "query_plan"}], "a plan without a witness: %r" % helper(r))
  objs = ar.query_input(src, q, "plan", "positive")
  signs = sorted({x[0] for o in objs if "@logic" in o for x in o["@logic"] if isinstance(x, list) and x[0].lstrip("-") == "$defq0"})
  qs = [o["@question"] for o in objs if "@question" in o]
  need(signs == ["$defq0"] and qs == [["$defq0", "?:Sit"]], "the helper is positive in its definition and the question is negated by the prover: %r %r" % (signs, qs))
  src2, q2, r2 = build(BLOCKS, ["exists", "X", holding(H, "X")])
  need(helper(r2) == [{"predicate": "$defq0", "arity": 2, "path": [1], "role": "query_plan"}], "a plan with a witness: %r" % helper(r2))
  for res in (r, r2):
    need(sorted({x["role"] for x in res["profile"]["semantic"]["situation_positions"]}) == ["answer_plan", "context", "query_plan", "reachable"], "the four roles")
  # an ask question has the same helper name with an entity as its first argument
  qa = ar.compile_query(["@id", "Q1", ["ask", "X", on("X", A)]], src)
  ob = [o for o in qa["obligations"] if o["positive"]][0]
  asked = [ob["positive"]["question"]] + ob["positive"]["clauses"]
  need(asked[0]["@question"][0] == "$defq0" and not [x for x in ls._positions(asked) if x["role"] == "query_plan"]
       and ls.compile_profile(src, qa)["status"] == "unavailable", "an ask helper gets no selector: %r" % (asked[0],))
  print("  selectors: $defq0 has the role query_plan at argument 1 with arity 1 (no witness) and 2 (one witness); it is "
        "positive in its definition clause and is the question; the helper of an ask question gets no selector")


def check_milestones(formal):
  fx, src, q, r = [x for x in formal if x[0]["id"] == "ticket_travel"][0]
  units = [u["stage2"] for u in fx["units"]]
  s4 = [u for u in units if u[1] == "S4"][0]
  src2 = ar.compile_source(None, units + [["@id", "S9", copy.deepcopy(s4[2])]], la.PROFILE, entities=fx["entities"])
  q2 = ar.compile_query(fx["queries"][0]["stage2"], src2)
  plain = ls.compile_profile(src2, q2)
  cat, al = plain["choice"]["milestone_catalog"], plain["choice"]["milestone_aliases"]
  need(len(cat) == 1 and len(al) == 1 and list(al.values()) == list(cat) and r["choice"]["milestone_aliases"] == {},
       "two restrictions, one catalog entry and one alias: %r %r" % (cat, al))
  want = r["profile"]["semantic"]["score"]
  for names in (list(cat), list(al), list(cat) + list(al)):
    got = ls.compile_profile(src2, q2, dict(fx["summary"]["choice"], milestones=names))
    need(got["choice"]["invalid"] is None and got["profile"]["semantic"]["score"] == want, "the choice %r gives the one milestone: %r" % (
      names, got["profile"]["semantic"]["score"].get("milestones")))
    need([x.progress for x in run_plan(got, fx["summary"]["sequence"])] == [-4, -3, -2, 0], "the scores do not change")
  two = copy.deepcopy(r["profile"])
  two["semantic"]["score"]["milestones"].append({"city": "#:Malmo 3", "fact": ["have", "#:Ann 1", "#:ticket 5"]})
  two["semantic"] = asum.normalize(two["semantic"])
  two["profile_id"] = asum.profile_id(two["semantic"])
  need([x.progress for x in run_plan({"profile": two}, fx["summary"]["sequence"])] == [-6, -5, -3, 0], "one fact at two places is two entries")
  dup = copy.deepcopy(r["profile"])
  dup["semantic"]["score"]["milestones"] *= 2
  dup["profile_id"] = asum.profile_id(dup["semantic"])
  try:
    asum.validate(dup)
    need(False, "a repeated milestone is refused")
  except asum.ProfileError:
    pass
  print("  milestones: a duplicated restriction gives one catalog entry and an alias; a choice by either name or both "
        "gives the same score parameters and the scores -4,-3,-2,0; one fact at two places is two entries; a repeated "
        "entry in a profile is refused")


def check_independence():
  solver = os.path.join(HERE, "..", "..", "solver")
  with open(os.path.join(solver, "action_replay.py")) as f:
    text = f.read()
  need("action_summary" not in text and "lc_action_summary" not in text, "the replay does not import the summary modules")
  with open(os.path.join(solver, "action_summary.py")) as f:
    imports = [x.split()[1] for x in f.read().split("\n") if x.startswith(("import ", "from "))]
  need(sorted(imports) == ["hashlib", "json"], "the interpreter imports no solver module: %s" % imports)
  with open(os.path.join(solver, "lc_action_summary.py")) as f:
    need(".successor(" not in f.read(), "the compiler does not call the replay's successor")
  print("  independence: the replay imports no summary module; the interpreter imports hashlib and json only; the "
        "compiler never calls the replay's successor")


def run():
  formal = load_formal()
  check_formal(formal)
  check_ledger(formal)
  check_cache(formal)
  check_updates()
  check_failures(formal)
  check_defaults(formal)
  check_audit(formal)
  check_scope()
  check_transport()
  check_identity(formal)
  check_boundaries(formal)
  check_ownership(formal)
  check_loss(formal)
  check_selectors(formal)
  check_milestones(formal)
  check_independence()


if __name__ == "__main__":
  run()
