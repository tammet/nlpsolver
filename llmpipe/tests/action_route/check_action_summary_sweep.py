"""The planning-summary sweep: every gold plan and candidate of the fixtures (`fixtures/cases/`) and of the planning
test rows (`tests/tests_planning*.py`): counts of ready, partial and unavailable profiles with their reasons, and the
subset relation with the replay's export at every replay-valid prefix.

No model, no GK.  It reads the wider action-route test data; the feature checks of the summaries are
`check_action_summary.py` and `check_action_summary_route.py`.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_check as ac
import action_replay as rp
import action_route as ar
import check_action_summary as cs
import check_action_validation as cv
import check_planning_tests as cpt
import fixture_materialize as fm
import lc_action_summary as ls

need, subset, run_plan = cs.need, cs.subset, cs.run_plan


def _sequences():
  """(label, source, query, [sequence]) of every gold discovery query with a plan or a candidate."""
  out = []
  for c in fm.load_all():
    if not c["units"]:
      continue
    try:
      src = cv.gold_source(c)
    except Exception:                                      # noqa: BLE001
      continue
    if src["support"]["status"] != "supported":
      continue
    for q in c["queries"]:
      if not q.get("stage2") or q["stage2"][2][0] not in ("plan", "reachable"):
        continue
      qa = ar.compile_query(q["stage2"], src, cv.gold_limits(q), None, **fm.selection(q))
      seqs = [q["expect"]["plan"]] if q["expect"].get("plan") else []
      seqs += [k["sequence"] for k in c.get("candidates") or [] if k["sequence"] not in seqs]
      out.append(("fixture %s/%s" % (c["case"], q["id"]), src, qa, seqs))
  rows = []
  for name in cpt.FILES:
    rows.extend((name, r[0], ac.reference_of(r)) for r in cpt.load(name))
  for name, tid, ref in rows:
    if not ref.get("plans"):
      continue
    src, qa = ac.compiled(ref)
    if src is None or qa is None:
      continue
    out.append(("%s %s" % (name[:-3], tid), src, qa, ref["plans"]))
  return out


def check_sweep():
  counts, reasons, prefixes, lists, lossy, empty = {}, {}, 0, 0, 0, 0
  plans = reached = 0
  templates = {}
  for label, src, q, seqs in _sequences():
    r = ls.compile_profile(src, q)
    counts[r["status"]] = counts.get(r["status"], 0) + 1
    if r["status"] != "ready":
      why = r["reason"] or ""
      fams = sorted({(v or "").split(":")[0] for v in (r.get("families") or {}).values() if v != "tracked"})
      key = "%s: %s%s" % (r["status"], why, " (%s)" % ", ".join(fams) if fams else "")
      reasons[key] = reasons.get(key, 0) + 1
    if r["profile"] is None:
      continue
    t = r["profile"]["semantic"]["score"]["template"]
    templates[t] = templates.get(t, 0) + 1
    for seq in seqs:
      rv = rp.replay(src, seq, planning_root=q["planning_root"], ambient=q["ambient"], knower=q["knower"], export=True)
      if rv["verdict"] == "inconsistent_action_state" and rv["step"] == 0 or not rv.get("export"):
        continue
      n = subset(src, q, r, seq, label)
      prefixes += n
      if rv["verdict"] == "valid" and t and rp.replay(src, seq, goal=q["query"]["goal"], planning_root=q["planning_root"])["verdict"] == "valid":
        plans += 1
        reached += run_plan(r, seq)[-1].progress == 0
      for rec in run_plan(r, seq[:rv["checked_prefix"]]):
        lists += rec.world is not None
        lossy += bool(rec.lossy)
        empty += rec.world == ()
  total = sum(counts.values())
  need(total and counts.get("ready"), "the sweep has ready profiles")
  print("  sweep: %d discovery queries with a gold plan or candidate: %s" % (
    total, ", ".join("%d %s" % (counts[k], k) for k in ("ready", "partial", "unavailable") if k in counts)))
  for k in sorted(reasons):
    print("    %3d  %s" % (reasons[k], k))
  print("    templates: %s" % ", ".join("%d %s" % (n, t) for t, n in sorted(templates.items(), key=str)))
  print("    %d replay-valid prefixes compared: every list is a subset of the replay's export (%d lists, %d empty, "
        "%d records lossy)" % (prefixes, lists, empty, lossy))
  print("    %d sequences reach their goal in the replay under a scored profile; the last record has Progress 0 for %d"
        % (plans, reached))



def run():
  check_sweep()


if __name__ == "__main__":
  run()
