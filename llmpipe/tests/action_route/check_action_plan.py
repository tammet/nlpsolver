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
  stages       on a fake GK build that answers by launch stage: a failed first check and a passing second one; a
               retry without the $planstate records; a filtered launch that finds the plan; a filtered launch
               without a plan, then the single discovery launch; every launch with its own label, and -gkin writes
               one file per launch
  budget       a check that uses up the budget of the extra stages: the next check and the filtered launch are
               skipped and recorded, and the single discovery launch still runs
No model call.  The search part launches GK: two launches.
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
import action_display as ad
import check_action_answer as caa
import solve
import stat
import tempfile
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


FAKE = """#!%s
import json, os, sys, time
here = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
strategy = json.loads(args[1])
stage = "check" if strategy.get("plan_state") else "filtered" if strategy.get("plan_filters") else "discovery"
objs = json.load(open(args[4]))
names = [o.get("@name", "") for o in objs if isinstance(o, dict)]
table = json.load(open(os.path.join(here, "table.json")))
count = os.path.join(here, "count_" + stage)
n = int(open(count).read()) if os.path.exists(count) else 0
open(count, "w").write(str(n + 1))
with open(os.path.join(here, "log.jsonl"), "a") as f:
  f.write(json.dumps({"stage": stage, "planstate": any(x.startswith("planstate:") for x in names),
                      "planfilter": any(x.startswith("planfilter:") for x in names)}) + "\\n")
outs = table.get(stage) or []
out = outs[n] if n < len(outs) else "none"
if out == "sleep":
  time.sleep(3)
  out = "none"
if "-printlevel" in args:
  print("<- nothing proved (search limit reached)")
print(json.dumps({"result": "no answers found"} if out == "none" else out))
"""


def fake_stages(table):
  """A registered fake build that answers by launch stage (check, filtered, discovery) from `table`: {stage: [the
  output of its first launch, of its second, ...]}; "none" is no answer, "sleep" waits 3 seconds first.  Returns
  (name, the folder with log.jsonl)."""
  tmp = tempfile.mkdtemp()
  with open(os.path.join(tmp, "table.json"), "w") as f:
    json.dump(table, f)
  path = os.path.join(tmp, "fake_stage_prover")
  with open(path, "w") as f:
    f.write(FAKE % sys.executable)
  os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
  name = "fake_stages_%d" % len(caa.FAKES)
  ag.BACKENDS[name] = dict(ag.backend_profile(), name=name, path=path, sha256=ag.sha256_file(path), datafolder=tmp)
  caa.FAKES.append(name)
  return name, tmp


def calls(tmp):
  p = os.path.join(tmp, "log.jsonl")
  return [json.loads(x) for x in open(p)] if os.path.exists(p) else []


class Patched:
  """Replace module attributes for one block."""

  def __init__(self, pairs):
    self.pairs = pairs

  def __enter__(self):
    self.old = [(m, k, getattr(m, k)) for m, k, _ in self.pairs]
    for m, k, v in self.pairs:
      setattr(m, k, v)

  def __exit__(self, *a):
    for m, k, v in self.old:
      setattr(m, k, v)


def run_search(name, src, pkg, qa, lim, sel, seconds=30):
  ledger = {}
  with ag.recording() as got:
    res = apl.solve(src, pkg, qa, name, {"seconds": seconds}, ledger, compile_limits=lim, selection=sel)
  return res, got


def check_stages(src, pkg, qa, lim, sel, r):
  sit = apl._situation(r["plan_terms"], qa["planning_root"])
  plan = caa.answers(([sit], 1.0))
  real = apl._proposals
  one = lambda task, source, query: (lambda kept, rec: (kept * 2, rec))(*real(task, source, query))
  # a failed first check, a passing second one; no retry while the model covers every family
  name, tmp = fake_stages({"check": ["none", plan]})
  with Patched([(apl, "_proposals", one)]):
    res, got = run_search(name, src, pkg, qa, lim, sel)
  ps_ = res["plan_search"]
  need(res["outcome"] == "plan_found" and ps_["stage"] == "builder_check" and len(ps_["checks"]) == 2,
       "the second check answers: %r" % ((res["outcome"], ps_["stage"], len(ps_["checks"])),))
  need([c["stage"] for c in calls(tmp)] == ["check", "check"] and all(c["planstate"] for c in calls(tmp)),
       "two check launches, each with the $planstate records: %r" % calls(tmp))
  need([g["label"] for g in got] == ["Q1.plan.check1", "Q1.plan.check2"], "the labels: %r" % [g["label"] for g in got])
  # a check without a proof while a family is left out: the same plan once more without the records
  real_records = ps.records
  left = lambda task, terms, root: (lambda recs, info: (recs, dict(info, left_out={"x": "a test omission"})))(
    *real_records(task, terms, root))
  name, tmp = fake_stages({"check": ["none", plan]})
  with Patched([(ps, "records", left)]):
    res, got = run_search(name, src, pkg, qa, lim, sel)
  need(res["outcome"] == "plan_found" and [c["planstate"] for c in calls(tmp)] == [True, False]
       and [g["label"] for g in got] == ["Q1.plan.check1", "Q1.plan.check1_nostates"],
       "the retry without the records: %r" % ((calls(tmp), [g["label"] for g in got]),))
  # no proposal: the filtered launch finds the plan
  none = lambda task, source, query: (lambda kept, rec: ([], dict(rec, dropped=[{"plan": "x", "reason": "a test"}])))(
    *real(task, source, query))
  name, tmp = fake_stages({"filtered": [plan]})
  with Patched([(apl, "_proposals", none)]):
    res, got = run_search(name, src, pkg, qa, lim, sel)
  need(res["outcome"] == "plan_found" and res["plan_search"]["stage"] == "filtered_discovery"
       and [c["stage"] for c in calls(tmp)] == ["filtered"] and calls(tmp)[0]["planfilter"],
       "the filtered launch: %r" % ((res["plan_search"]["stage"], calls(tmp)),))
  # the filtered launch finds none: the single discovery launch decides; every launch has its own label
  name, tmp = fake_stages({"filtered": ["none"], "discovery": [plan]})
  with Patched([(apl, "_proposals", none)]):
    res, got = run_search(name, src, pkg, qa, lim, sel)
  labels = [g["label"] for g in got]
  need(res["outcome"] == "plan_found" and res["plan_search"]["stage"] == "discovery"
       and [c["stage"] for c in calls(tmp)] == ["filtered", "discovery"] and not calls(tmp)[1]["planfilter"]
       and labels == ["Q1.plan.filtered", "Q1.plan.discovery"],
       "the single discovery launch after the filtered one: %r" % ((res["plan_search"]["stage"], calls(tmp), labels),))
  d = tempfile.mkdtemp()
  paths = ad.write_gkin(os.path.join(d, "x.json"), got, {"source": src})
  need(len(set(paths)) == 2 and all(os.path.exists(p) for p in paths)
       and sorted(os.path.basename(p) for p in paths) == ["x.Q1.plan.discovery.json", "x.Q1.plan.filtered.json"],
       "-gkin writes one file per launch: %r" % paths)
  print("  stages: a failed first check and a passing second; a retry without the $planstate records; a filtered "
        "launch with the plan; a filtered launch without, then the single discovery launch; one label and one "
        "-gkin file per launch")


def check_budget(src, pkg, qa, lim, sel, r):
  sit = apl._situation(r["plan_terms"], qa["planning_root"])
  plan = caa.answers(([sit], 1.0))
  real = apl._proposals
  two = lambda task, source, query: (lambda kept, rec: (kept * 2, rec))(*real(task, source, query))
  # 1-second launches: a budget of 3 seconds; the first check sleeps 3 seconds and uses it up
  name, tmp = fake_stages({"check": ["sleep", plan], "filtered": [plan], "discovery": [plan]})
  with Patched([(apl, "_proposals", two)]):
    res, got = run_search(name, src, pkg, qa, lim, sel, seconds=1)
  b = res["plan_search"]["budget"]
  need(res["plan_search"]["stage"] == "discovery" and [c["stage"] for c in calls(tmp)] == ["check", "discovery"]
       and b["total"] == 3 and "plan.check2" in b["skipped"] and "plan.filtered" in b["skipped"],
       "the budget: %r" % ((res["plan_search"]["stage"], calls(tmp), b),))
  print("  budget: after a check that uses up the budget, the next check and the filtered launch are skipped and "
        "recorded; the single discovery launch runs")


def run():
  src, pkg, qa, lim, sel, task, r = check_builder()
  check_question(src, pkg, qa, lim, sel, r)
  check_states(task, r, qa)
  check_search(src, pkg, qa, lim, sel)
  check_options()
  check_stages(src, pkg, qa, lim, sel, r)
  check_budget(src, pkg, qa, lim, sel, r)


if __name__ == "__main__":
  run()
