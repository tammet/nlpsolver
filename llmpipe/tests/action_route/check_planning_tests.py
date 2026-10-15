"""The build checks of the planning test set (tests/tests_planning.py, its development file and its contrasts),
offline.  Each row is complete: [id, text, expected, reference].

  rows      every row has four elements and a reference with its section, name, plans, expectation, reason, known
            limit and gold translation (stage1 and stage2, or formal)
  compile   every reference record compiles: a row that expects an answer has a query ready for the prover; a Cannot
            answer row is unsupported with its reason code; a row with a known limit of negative persistence is refused
            by the backend requirement
  replay    every listed plan replays valid on its reference translation, with its goal and step bound
  render    the listed plans render to the expected plan strings, character for character, in order
  grade     every expected value graded against itself is correct (listed, match or not_answered)
  golds     planning_gold.json, a maintained source: each gold validates and passes the controller unchanged
  files     the generated files equal a fresh build (make_planning_tests.py --check), the contrasts and the basic
            file included

check_planning_basic.py checks the basic file, its checker and the runner.

The sixth check of the task, each expected answer confirmed on GK with the gold translation, is a logged run:
elogs/planning_testset_2026_09_30/gold_gk.py.  No model call, no GK launch here.
"""
import ast
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE]

import action_answer as aa              # noqa: E402

import action_english as aen
import action_check as ac               # noqa: E402
import action_replay as rp              # noqa: E402
import check_action_availability as cav  # noqa: E402
import make_planning_tests as mp        # noqa: E402

need = cav.need
FILES = ("tests_planning.py", "tests_planning_dev.py", "tests_planning_contrasts.py")
REQUIRED = ("section", "name", "origin", "exposure", "purpose", "question_kind", "known_limit", "reason", "expect",
            "plans")


def load(name):
  """The rows of a test file."""
  with open(os.path.join(ROOT, "tests", name)) as f:
    return _literal(f.read())


def _literal(text):
  """The list of a test file: the literal after its header comments."""
  return ast.literal_eval(text[text.index("\n[") + 1:])


def cannot(value):
  return isinstance(value, str) and value.startswith("Cannot answer")


def check_compile(all_rows):
  ready = refused = unsupported = 0
  for name, tid, expected, ref in all_rows:
    source, query = ac.compiled(ref)
    need(source is not None, "%s %d: no source" % (name, tid))
    values = expected if isinstance(expected, list) else [expected]
    out = (query or {}).get("outcome") or {}
    if query is not None and not out and source["support"]["status"] == "supported" \
        and any(not cannot(v) for v in values) and ref.get("known_limit") != "negative_persistence":
      # a supported gold whose row also lists a Cannot answer for another reading (row 96, version 1.1)
      ready += 1
    elif any(cannot(v) for v in values):
      reasons = set(source["support"].get("reasons") or []) | set(out.get("reasons") or []) | {out.get("reason")}
      need(ref["reason"] in reasons, "%s %d: reason %s, compiled %s" % (name, tid, ref["reason"], reasons))
      unsupported += 1
    elif ref.get("known_limit") == "negative_persistence":
      need(out.get("outcome") == "unsupported_backend_requirement", "%s %d: %r" % (name, tid, out))
      refused += 1
    else:
      need(query is not None and not out, "%s %d: the query is not ready: %r" % (name, tid, out))
      ready += 1
  return "compile: %d rows ready for the prover, %d Cannot answer rows unsupported with their reason, %d refused by " \
         "negative persistence (known limit)" % (ready, unsupported, refused)


def check_replay_render(all_rows):
  plans = strings = 0
  for name, tid, expected, ref in all_rows:
    if not ref["plans"]:
      continue
    source, query = ac.compiled(ref)
    q = query["query"]
    values = [v for v in (expected if isinstance(expected, list) else [expected]) if isinstance(v, str)
              and v.startswith("Plan:")]
    for k, plan in enumerate(ref["plans"]):
      r = rp.replay(source, plan, goal=q["goal"], steps=q["steps"], planning_root=query["planning_root"],
                    ambient=query["ambient"], knower=query["knower"])
      need(r["verdict"] == "valid", "%s %d plan %d: %s" % (name, tid, k, r["reason"]))
      plans += 1
      if q["kind"] == "plan":
        text = "Plan: %s." % aen.render(source, plan, r["steps"])
        need(k < len(values) and text == values[k], "%s %d plan %d renders %r, expected %r" % (
          name, tid, k, text, values[k] if k < len(values) else None))
        strings += 1
  return "replay and render: %d listed plans replay valid; %d render to their expected strings" % (plans, strings)


def check_grade(all_rows):
  n = 0
  for name, tid, expected, ref in all_rows:
    for v in (expected if isinstance(expected, list) else [expected]):
      answer = {True: "Yes.", False: "No.", None: "Unknown."}.get(v, v) if not isinstance(v, str) else v
      g = ac.grade_row([tid, ref["text"], expected, ref], answer)
      need(g["correct"], "%s %d: %r graded %r" % (name, tid, v, g))
      n += 1
  return "grade: %d expected values graded correct against themselves" % n


def check_golds():
  """planning_gold.json is a maintained source: every gold validates, passes the controller with no error and no
  repair (a note of an accepted form is allowed), and is used by exactly one row."""
  import action_pipeline as ap
  bundle = ap.load_bundle(ap.DEFAULT_BUNDLE)
  with open(mp.GOLD) as f:
    golds = json.load(f)["golds"]
  rows = mp.load_rows()
  used = [r["gold"] for r in rows["rows"] if "gold" in r]
  contrast = [r["gold"] for r in rows.get("contrasts") or []]
  need(sorted(used) == sorted(g["id"] for g in golds) and len(set(used)) == len(used) and set(contrast) <= set(used)
       and len(set(contrast)) == len(contrast), "every gold is used by one row, a contrast gold by its contrast too")
  for g in golds:
    units, errors = ap.stage1_units(g["stage1"])
    need(not errors, "%s: %r" % (g["id"], errors))
    need(" ".join(p["raw"] for p in g["stage1"]) == g["text"], "%s: raw coverage" % g["id"])
    att = ap.stage2_attempt(json.dumps(g["stage2"]), "stop", g["text"], units, bundle, set(), False)
    changed = [n for n in att["normalizations"] if n.get("repair") and n.get("before") != n.get("after")
               and n.get("kind") not in ("verify_role_not_compared", "ask_executable")]
    need(not att["errors"] and not changed, "%s: %r %r" % (g["id"], att["errors"], changed))
  return "golds: the %d golds of planning_gold.json validate, pass the controller unchanged and are each used by " \
         "one row (a contrast gold also by its contrast)" % len(golds)


def check_files():
  files = mp.rendered_files()
  drift = [k for k, text in files.items() if not os.path.exists(mp.OUT[k]) or open(mp.OUT[k]).read() != text]
  need(not drift, "the generated files differ from a fresh build: %s" % drift)
  return "files: the four generated files equal a fresh build"


def check_rows():
  """Every row is [id, text, expected, reference] with the required reference keys and a gold translation."""
  all_rows = []
  for name in FILES:
    tests = load(name)
    # version 1.1 places its new ids 101..109 in their sections
    need(sorted(t[0] for t in tests) == list(range(1, len(tests) + 1)), "%s: the ids 1..n" % name)
    for t in tests:
      need(len(t) == 4 and isinstance(t[3], dict), "%s %r: not [id, text, expected, reference]" % (name, t[0]))
      ref = t[3]
      need(all(k in ref for k in REQUIRED) and not {"id", "text", "expected"} & set(ref)
           and (("stage1" in ref and "stage2" in ref) != ("formal" in ref)),
           "%s %d: reference keys %s" % (name, t[0], sorted(ref)))
      all_rows.append((name, t[0], t[2], ac.reference_of(t)))
  need(len(all_rows) == 154, "126 rows, 11 development rows and 17 contrasts: %d" % len(all_rows))
  return all_rows


def run():
  all_rows = check_rows()
  print("  rows: the %d rows of the three files are complete: [id, text, expected, reference], with the reference's "
        "section, name, plans, expectation, reason, known limit and gold translation" % len(all_rows))
  for line in (check_compile(all_rows), check_replay_render(all_rows), check_grade(all_rows), check_golds(),
               check_files()):
    print("  " + line)


if __name__ == "__main__":
  run()
