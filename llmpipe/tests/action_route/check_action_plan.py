"""The plan search of a plan or reachable query (solver/action_plan.py) and its parts.

  builder      the ground model and the builder on the three-block tower: a four-step plan that the route's replay
               validates; the relaxed graph of a state with no fluent gives no level and raises nothing
  question     compile_query with a plan situation: the definition clauses hold the situation, the question still
               asks for ?:Sit, the artifact has its own hash; another query kind and a situation not rooted at the
               planning root are refused
  states       the $planstate records: one per prefix, ground situations, the families and their omissions
  search       on GK (the installed binary, named below): the plan search answers the tower from the builder's
               plan with one check launch, with the plan and confidence of today's discovery launch
  options      -plan-builder and -noplan-builder: action keys, exclusive, the default on, off with
               -planning-summary
No model call.  The search part launches GK: three launches.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_answer as aa
import action_gk as ag
import action_pipeline as ap
import action_plan as apl
import action_route as ar
import check_action_gk as cg
import plan_builder as pb
import plan_state as ps
import solve
from check_action_availability import need

GK_SHA256 = "d2985bcf3e73e9a48e78b03c7b3b7cd9a2d4db464006663d9b13bb34255f81b9"   # gk 1.1.0 at ../gk/gk


def tower():
  c = cg.GOLD["p02_tower:base"]
  q = [x for x in c["queries"] if x["id"] == "Q1"][0]
  src = cg.cv.gold_source(c)
  lim, sel = cg.cv.gold_limits(q), cg.fm.selection(q)
  return src, q["stage2"], ar.compile_query(q["stage2"], src, lim, **sel), lim, sel


def check_builder():
  src, pkg, qa, lim, sel = tower()
  task = pb.Task(ar.query_input(src, qa, "plan", "positive"), "tower")
  r = pb.build(task, "ehc")
  need(r["status"] == "found" and r["length"] == 4 and r["valid"], "the builder's tower plan: %r" % (r,))
  kept, rec = apl._proposals(task, src, qa)
  need(len(kept) == 1 and kept[0]["replay"]["verdict"] == "valid" and not rec["dropped"],
       "one proposal, valid in the route's replay: %r" % (rec,))
  rel = pb.Relaxed(task, task.goals[0], True)
  level, ach, ok = rel.levels(frozenset())
  need(level == {} and not ok, "a state with no fluent gives no level: %r" % (level,))
  print("  builder: the tower's four-step plan, valid in the route's replay; a state with no fluent gives no level")
  return src, pkg, qa, lim, sel, task, r


def check_question(src, pkg, qa, lim, sel, r):
  s = apl._situation(r["plan_terms"], qa["planning_root"])
  cq = ar.compile_query(pkg, src, lim, plan_situation=s, **sel)
  ob = [o for o in cq["obligations"] if o["id"] == "plan"][0]["positive"]
  text = json.dumps([c["@logic"] for c in ob["clauses"]])
  need(json.dumps(s) in text and '"?:Sit"' not in text, "the definition clauses hold the plan situation")
  need(ob["question"]["@question"][1] == "?:Sit" and cq["hash"] != qa["hash"] and cq["plan_situation"] == s,
       "the question still asks for ?:Sit, and the artifact has its own hash")
  verify = cg.GOLD["p02_tower:after_take_b"]
  vq = [x for x in verify["queries"] if x["id"] == "Q2"][0]
  try:
    ar.compile_query(vq["stage2"], cg.cv.gold_source(verify), cg.cv.gold_limits(vq), plan_situation=s, **cg.fm.selection(vq))
    need(False, "a plan situation on a verify query is refused")
  except ar.ArtifactError:
    pass
  for bad in (["$do", ["take", "?:X", "#:b 2"], qa["planning_root"]], ["$do", r["plan_terms"][0], "W9"]):
    try:
      ar.compile_query(pkg, src, lim, plan_situation=bad, **sel)
      need(False, "a plan situation with a variable or another root is refused: %r" % (bad,))
    except ar.ArtifactError:
      pass
  print("  question: the definition clauses hold the plan situation, the question asks for ?:Sit, the hash is new; a "
        "verify query, a variable and another root are refused")
  return cq


def check_states(task, r, qa):
  recs, info = ps.records(task, r["plan_terms"], qa["planning_root"])
  need(len(recs) == len(r["plan_terms"]) + 1 and info["families"], "one record per prefix: %r" % (info,))
  sits = [x["@logic"][0][1] for x in recs]
  need(sits[0] == qa["planning_root"] and all(s[0] == "$do" for s in sits[1:]), "the record situations")
  print("  states: %d records, families %s, left out %s" % (len(recs), ", ".join(" ".join(f) for f in info["families"]),
                                                            info["left_out"] or "none"))


def check_search(src, pkg, qa, lim, sel):
  prof = ag.backend_profile()
  need(prof["sha256"] == GK_SHA256, "the installed GK is the binary this check names: %s" % prof["sha256"])
  ledger = {}
  res = apl.solve(src, pkg, qa, "gk", {"seconds": 30}, ledger, compile_limits=lim, selection=sel)
  ps_ = res["plan_search"]
  need(res["outcome"] == "plan_found" and ps_["stage"] == "builder_check" and len(res["plan"]) == 4,
       "the tower from the builder's plan: %r" % (({k: res.get(k) for k in ("outcome", "plan")}, ps_["stage"],
                                                  ps_["checks"]),))
  need(res["query"]["hash"] == qa["hash"] and ps_["answered_query"]["hash"] != qa["hash"],
       "the result names the original query and the checked one")
  roles = [c["role"] for c in ledger["gk_calls"]]
  need(roles == ["discovery:check"], "one check launch: %r" % roles)
  base = aa.solve(src, qa, "gk", {"seconds": 30}, {})
  need(base["outcome"] == "plan_found" and base["plan"] == res["plan"] and base["confidence"] == res["confidence"],
       "today's discovery launch gives the same plan and confidence: %r %r" % (base["plan"], base["confidence"]))
  print("  search: the tower from one check launch, plan and confidence %s equal to today's discovery launch"
        % res["confidence"])


def check_options():
  need("plan_builder_flag" in ap.ACTION_KEYS and "noplan_builder_flag" in ap.ACTION_KEYS
       and "plan_builder_flag" in solve._ACTION_KEYS and "noplan_builder_flag" in solve._ACTION_KEYS,
       "both keys are action keys")
  need(ap.resolve({"actions_flag": True})["plan_builder"] is True, "the plan search is on by default")
  need(ap.resolve({"actions_flag": True, "plan_builder_flag": True})["plan_builder"] is True, "-plan-builder")
  need(ap.resolve({"actions_flag": True, "noplan_builder_flag": True})["plan_builder"] is False, "-noplan-builder")
  need(ap.resolve({"actions_flag": True, "planning_summary_flag": True})["plan_builder"] is False,
       "a summary request keeps the single discovery launch")
  for bad in ({"plan_builder_flag": True, "noplan_builder_flag": True},
              {"plan_builder_flag": True, "planning_summary_flag": True}):
    try:
      ap.resolve(dict(bad, actions_flag=True))
      need(False, "refused: %r" % bad)
    except ap.OptionError:
      pass
  c = solve.route_choice("x", {"noactions_flag": True, "noplan_builder_flag": True})
  need("error" in c, "an action key with -noactions is an error")
  print("  options: both keys are action keys; on by default, off with -noplan-builder or -planning-summary; "
        "-plan-builder with either is refused")


def run():
  src, pkg, qa, lim, sel, task, r = check_builder()
  check_question(src, pkg, qa, lim, sel, r)
  check_states(task, r, qa)
  check_search(src, pkg, qa, lim, sel)
  check_options()


if __name__ == "__main__":
  run()
