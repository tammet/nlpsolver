#!/usr/bin/env python3
"""Write the formal-input examples of the action route (`examples/*.json`) from the reviewed gold fixtures.

Each example is a formal record in the gold fixtures' field names: the units of one gold source (id, text,
Stage-1 projection, Stage-2 package, context record), its entities, worlds and text, and one or more queries.
The queries are gold queries, except `tower_sequence`, whose one query is derived from p02's gold plan and goal:
the supplied four-action tower sequence as a verification.  Every query keeps its gold expectation beside it,
under `expect`, for a reader; the route does not read it.

  python3 tests/action_route/make_examples.py           # write examples/
  python3 tests/action_route/make_examples.py --check   # compare examples/ with a fresh generation; exit 1 on a drift

  python3 solver/solve.py -actions -formal tests/action_route/examples/travel.json
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import fixture_materialize as fm

OUT = os.path.join(HERE, "examples")
# example -> (gold case, [query ids]) ; a query id "derived:plan-as-verify" is derived as described above
EXAMPLES = {
  "travel": ("p01_travel:base", ["Q1"]),
  "food": ("p03_food:base", ["Q1"]),
  "reuse": ("c14_source_reuse:base", ["Q1", "Q2", "Q4", "Q6"]),
  "restrictions": ("c05_two_restrictions:base", ["Q1", "Q2"]),
  "negative_capability": ("c04_negative_capability:base", ["Q1", "Q3"]),
  "tower_steps": ("p02_tower:after_take_b", ["Q2", "Q3", "Q4"]),
  "tower_sequence": ("p02_tower:base", ["derived:plan-as-verify"]),
}


def record(name):
  case_id, qids = EXAMPLES[name]
  c = {x["case"]: x for x in fm.load_all()}[case_id]
  units = []
  for u in c["units"]:
    units.append({k: u[k] for k in ("id", "text", "stage1", "stage2", "context") if u.get(k) is not None})
  queries = []
  for qid in qids:
    if qid == "derived:plan-as-verify":
      q = c["queries"][0]
      pkg = ["@id", "QV", ["verify", q["expect"]["plan"], q["stage2"][2][1]]]
      queries.append({"stage2": pkg, "text": "Does the supplied sequence build the tower?",
                      "expect": {"answer": "Yes", "derived_from": "%s %s: the gold plan as a supplied sequence"
                                                                 % (case_id, q["id"])}})
      continue
    q = [x for x in c["queries"] if x["id"] == qid][0]
    e = {"stage2": q["stage2"], "text": q.get("text")}
    e.update(fm.selection(q))
    if q.get("limits"):
      e["limits"] = {"search_cap": q["limits"]["search_cap"], "explicit": q["limits"].get("explicit", True)}
    e["expect"] = {k: v for k, v in q["expect"].items() if k != "evidence"}
    queries.append(e)
  rec = {"example": name, "gold": case_id, "text": c["text"], "entities": c["entities"], "units": units,
         "queries": queries}
  if c.get("worlds"):
    rec["worlds"] = c["worlds"]
  return rec


def render(rec):
  return json.dumps(rec, indent=1, ensure_ascii=False) + "\n"


def main(argv):
  check = "--check" in argv
  drift = []
  if not check:
    os.makedirs(OUT, exist_ok=True)
  for name in sorted(EXAMPLES):
    text = render(record(name))
    path = os.path.join(OUT, name + ".json")
    if check:
      if not os.path.exists(path) or open(path).read() != text:
        drift.append(name)
    else:
      with open(path, "w") as f:
        f.write(text)
  if check:
    print("examples: %d, drift: %s" % (len(EXAMPLES), drift or "none"))
    return 1 if drift else 0
  print("wrote %d examples to %s" % (len(EXAMPLES), os.path.relpath(OUT)))
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
