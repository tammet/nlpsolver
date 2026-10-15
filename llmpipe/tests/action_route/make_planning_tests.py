#!/usr/bin/env python3
"""Build the planning test set from its row list and the reviewed golds.  No model call, no GK launch.

  python3 tests/action_route/make_planning_tests.py            # write the three files
  python3 tests/action_route/make_planning_tests.py --check    # compare them with a fresh build; exit 1 on a drift
  python3 tests/action_route/make_planning_tests.py --inventory FILE   # the review table of the rows (markdown)

Inputs: `planning_rows.json` (the rows, their sections and the reviewed overrides), the v6 cohort
(`v6/cohort.json`, which equals the prompt corpus's gold translations), the gold fixtures (`fixtures/cases/`) and the
golds of the rows that version 1.1 added (`planning_gold.json`, in the cohort format).
Outputs, each a list of complete rows [id, text, expected, reference] in sections:

  tests/tests_planning.py              the test set
  tests/tests_planning_dev.py          the prompt examples of the cohort (never a headline number)
  tests/tests_planning_contrasts.py    the contrast texts of prompt revision I, as they were run

and the basic file of the test set, which the checker reads (`solver/planning_check.py`):

  tests/tests_planning_basic.py        [id, text, expected text, expected action list] rows: the answer texts of
                                       the route, and per text its plan with names, [] or None

The reference of a row is a dict: its section, name, origin, exposure, purpose, question kind, known limit, the
reason code of a Cannot answer row, the reviewed expectation, the listed plans as terms, and the reviewed gold
translation (`stage1` and `stage2`, or a fixture's `formal` record).  `solver/action_check.py` grades with it
(`grade_row`).

The expected value is derived from the reviewed expectation: Yes, No and Unknown become True, False and None; a
stated probability below 0.95 becomes "Probably yes." or "Probably no."; a plan becomes "Plan: <sentence>." rendered from the listed plan on the
reference translation by the route's own renderer (`action_answer.render`); a reachable question with a plan becomes
True; an empty plan "No action is needed."; no plan "No plan found." (a plan question) or None (a reachable
question); an unsupported outcome "Cannot answer: <sentence>." (`action_pipeline.REASON_SENTENCES`); an inconsistent
state "Inconsistent."; a wh-answer the entity's name.  A row's `expected` replaces the derived value; its
`alternatives` stand before the value, and its `also_cannot` adds the Cannot answer string of a reason code after it.
"""
import copy
import csv
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path[:0] = [os.path.join(ROOT, "solver"), HERE]

import action_answer as aa          # noqa: E402

import action_english as aen
import action_check as ac           # noqa: E402
import action_pipeline as ap        # noqa: E402
import action_prompt as apt         # noqa: E402
import action_replay as rp          # noqa: E402
import fixture_materialize as fm    # noqa: E402

ROWS = os.path.join(HERE, "planning_rows.json")
COHORT = os.path.join(HERE, "v6", "cohort.json")
GOLD = os.path.join(HERE, "planning_gold.json")
FIXTURE_ROWS = os.path.join(ROOT, "elogs", "planning_testset_2026_09_30", "fixture_rows.tsv")
OUT = {"test": os.path.join(ROOT, "tests", "tests_planning.py"),
       "basic": os.path.join(ROOT, "tests", "tests_planning_basic.py"),
       "dev": os.path.join(ROOT, "tests", "tests_planning_dev.py"),
       "contrasts": os.path.join(ROOT, "tests", "tests_planning_contrasts.py")}
# the keys of a row's reference, in this order; the row itself holds the id, the text and the expected value
REFERENCE_KEYS = ("section", "name", "origin", "exposure", "purpose", "question_kind", "known_limit", "reason", "note",
                  "expect", "evidence", "plans", "stage1", "stage2", "formal")
QUERY_KINDS = ("plan", "reachable", "verify", "question", "ask")


def load_rows():
  with open(ROWS) as f:
    return json.load(f)


def cohort():
  with open(COHORT) as f:
    return {e["id"]: e for e in json.load(f)}


def fixtures():
  return {c["case"]: c for c in fm.load_all()}


def golds():
  with open(GOLD) as f:
    return {g["id"]: g for g in json.load(f)["golds"]}


# ---------------------------------------------------------------------------
# one reference record


def query_kind(package):
  body = package[2]
  if body[0] == "question" and isinstance(body[1], list) and body[1][:1] == ["executable"]:
    return "executable"
  return body[0]


def _cohort_reference(e):
  qs = [p for p in e["stage2"]["logic"] if isinstance(p[2], list) and p[2][0] in QUERY_KINDS]
  ae = e["answer_expect"]
  return {"name": e["id"], "origin": "cohort v6", "text": e["text"], "stage1": e["stage1"], "stage2": e["stage2"],
          "question_kind": query_kind(qs[0]) if qs else None,
          "plans": [ae["plan"]] if ae.get("plan") else [],
          "expect": ae, "reason": ae.get("reason"), "known_limit": None,
          "exposure": "prompt" if e["prompt"] else "development"}


def _fixture_reference(cs, record, variant, qid):
  key = "%s:%s" % (record, variant)
  c = cs[key]
  q = [x for x in c["queries"] if x["id"] == qid][0]
  units = [{k: u[k] for k in ("id", "text", "stage1", "stage2", "context") if u.get(k) is not None} for u in c["units"]]
  query = {"stage2": q["stage2"], "text": q.get("text")}
  query.update(fm.selection(q))
  if q.get("limits"):
    query["limits"] = {"search_cap": q["limits"]["search_cap"], "explicit": q["limits"].get("explicit", True)}
  formal = {"case": key, "profile": c["profile"], "text": c["text"], "entities": c["entities"], "units": units,
            "query": query}
  if c.get("worlds"):
    formal["worlds"] = c["worlds"]
  e = q["expect"]
  plans = [e["plan"]] if e.get("plan") else []
  if not plans and (e.get("on_validated_backend") or {}).get("plan"):
    plans = [e["on_validated_backend"]["plan"]]
  return {"name": "%s:%s:%s" % (record, variant, qid), "origin": "fixture %s:%s:%s" % (record, variant, qid),
          "text": "%s %s" % (c["text"], q["text"]), "formal": formal, "question_kind": query_kind(q["stage2"]),
          "plans": plans, "expect": {k: v for k, v in e.items() if k != "evidence"}, "evidence": e.get("evidence"),
          "reason": e.get("reason"), "known_limit": None,
          # T10: the fixture rows are development material from prompt revision I on; the run of 2026-09-30 is
          # their first contact
          "exposure": "development"}


def _gold_reference(g):
  ref = _cohort_reference(g)
  ref.update(origin=g.get("origin") or "planning gold v1.1 (%s, the partner of row %d)" % (g["task"], g["partner"]),
             exposure="unseen")
  validated = (g["answer_expect"].get("on_validated_backend") or {}).get("plan")
  if not ref["plans"] and validated:
    # the reader's plan of a row with a known limit, as a fixture reference lists it
    ref["plans"] = [validated]
  return ref


def reference(row, co, cs, gs):
  if "cohort" in row:
    ref = _cohort_reference(co[row["cohort"]])
  elif "gold" in row:
    ref = _gold_reference(gs[row["gold"]])
  else:
    ref = _fixture_reference(cs, *row["fixture"])
  ref["id"] = row["id"]
  ref["section"] = row["section"]
  if row.get("extra_plans"):
    ref["plans"] = ref["plans"] + row["extra_plans"]
  if row.get("known_limit"):
    ref["known_limit"] = row["known_limit"]
  if row.get("note"):
    ref["note"] = row["note"]
  if row.get("exposure"):
    ref["exposure"] = row["exposure"]
  ref["purpose"] = purpose(ref)
  return ref


def purpose(ref):
  e = ref["expect"]
  kind = {"plan": "a plan question", "reachable": "a reachability question", "verify": "a supplied sequence",
          "executable": "a permission question", "question": "a yes-no question", "ask": "a wh-question"}.get(
            ref["question_kind"], "a text")
  out = e.get("outcome") or ("verification_result" if e.get("answer") is not None else None)
  return "%s; reviewed outcome %s" % (kind, out)


# ---------------------------------------------------------------------------
# the expected value


def stated_probability(ref):
  """Whether a source unit of the reference states a probability (the confidence shown as `Yes (c).`)."""
  if ref.get("stage1"):
    units = [u for p in ref["stage1"] for u in p["units"] if u.get("type") != "query"]
    return any(apt.expected_probability(u) is not None for u in units)
  for u in ref["formal"]["units"]:
    body = u["stage2"][2]
    if (isinstance(body, list) and body[:1] == ["and"] and len(body) == 3 and isinstance(body[2], list)
        and body[2][:1] == ["@p"] and body[2][2] < 1
        and re.search(r"probab|likely|chance|\d\s*%|0\.\d", u.get("text") or "", re.I)):
      return True
  return False


def rendered(ref, plan):
  """The plan sentence of a listed plan, rendered on the reference translation."""
  source, query = ac.compiled(ref)
  q = query["query"]
  r = rp.replay(source, plan, goal=q["goal"], steps=q["steps"], planning_root=query["planning_root"],
                ambient=query["ambient"], knower=query["knower"])
  if r["verdict"] != "valid":
    raise ValueError("%s: a listed plan does not replay valid: %s" % (ref["name"], r["reason"]))
  return aen.render(source, plan, r["steps"])


def derived_expected(ref):
  e, kind = ref["expect"], ref["question_kind"]
  out = e.get("outcome")
  validated = (e.get("on_validated_backend") or {}).get("plan")
  if ref["plans"] and (out in ("plan_found", None) or validated):
    if kind == "reachable":
      return True
    plans = ["Plan: %s." % rendered(ref, p) for p in ref["plans"]]
    return plans[0] if len(plans) == 1 else plans
  if out == "goal_already_holds" or (e.get("plan") == [] and out is None):
    return "No action is needed."
  if out == "not_found":
    return None if kind == "reachable" else "No plan found."
  if out in ("unsupported_translation", "unsupported_backend_requirement"):
    return "Cannot answer: %s." % aen.REASON_SENTENCES.get(e.get("reason"), aen.DEFAULT_REASON)
  if out == "inconsistent_action_state":
    return "Inconsistent."
  answer = e.get("answer")
  if kind == "ask":
    source, _ = ac.compiled(ref)
    return aen.capitalized(aen.name(source, answer)) + "."
  if answer in ("Yes", "No"):
    conf = e.get("confidence")
    value = conf.get("value") if isinstance(conf, dict) else conf
    if isinstance(value, (int, float)) and stated_probability(ref) and value < aen.PROBABLY:
      return "Probably %s." % answer.lower()
    return answer == "Yes"
  if answer == "Unknown":
    return None
  raise ValueError("%s: no expected value for %r" % (ref["name"], e))


def expected_value(row, ref):
  value = row["expected"] if "expected" in row else derived_expected(ref)
  if row.get("alternatives"):
    value = (value if isinstance(value, list) else [value])
    value = list(row["alternatives"]) + value
  if row.get("also_cannot"):
    value = (value if isinstance(value, list) else [value])
    value = value + ["Cannot answer: %s." % aen.REASON_SENTENCES.get(row["also_cannot"], aen.DEFAULT_REASON)]
  return value


# ---------------------------------------------------------------------------
# the files


def row_reference(ref):
  """The reference of a test row: the reference record without the id, the text and the expected value, which the
  row holds."""
  out = {k: ref[k] for k in REFERENCE_KEYS if k in ref}
  extra = set(ref) - set(REFERENCE_KEYS) - {"id", "text", "expected"}
  if extra:
    raise ValueError("%s: reference keys without a place in the row: %s" % (ref["name"], sorted(extra)))
  return out


def build():
  """(rows of planning_rows.json, {part: (test rows, reference records by id)}).  A test row is complete:
  [id, text, expected, reference]; the reference record adds the id, the text and the expected value."""
  rows = load_rows()
  co, cs, gs = cohort(), fixtures(), golds()
  out = {}
  for part in ("rows", "development", "contrasts"):
    tests, refs = [], {}
    for row in rows.get(part) or []:
      ref = reference(row, co, cs, gs)
      ref["expected"] = expected_value(row, ref)
      tests.append([row["id"], ref["text"], ref["expected"], row_reference(ref)])
      refs[str(row["id"])] = ref
    out[part] = (tests, refs)
  return rows, out


def basic_alternatives(value, ref):
  """[(text, action list)] of one expected value of the detailed file: the answer text of the route and the plan of
  that text with names (`action_answer.plan_named` on the reference translation), [] for the empty plan, or None.
  True, False and None are Yes., No. and Unknown.; a reachability question with a listed plan is "Yes. Plan: ...",
  one alternative per listed plan, and its goal at the start "Yes. No action is needed."."""
  reachable = ref["question_kind"] == "reachable"
  named = []
  if ref["plans"] and ac.supported(ref):
    source, _ = ac.compiled(ref)
    named = [("Plan: %s." % rendered(ref, p), aen.plan_named(source, p)) for p in ref["plans"]]
  if value is True and reachable and named:
    return [("Yes. " + text, plan) for text, plan in named]
  if value == "No action is needed.":
    return [("Yes. No action is needed." if reachable else value, [])]
  if isinstance(value, str) and value.startswith(("Plan:", "Probable plan:")):
    hit = [plan for text, plan in named if text == value]
    return [(value, hit[0] if hit else None)]
  return [({True: "Yes.", False: "No.", None: "Unknown."}.get(value, value) if not isinstance(value, str) else value,
           None)]


def basic_row(test, ref):
  """[id, text, expected text or texts, action list or lists] of a row of the detailed file."""
  values = test[2] if isinstance(test[2], list) else [test[2]]
  pairs = [p for v in values for p in basic_alternatives(v, ref)]
  if len(pairs) == 1:
    return [test[0], test[1], pairs[0][0], pairs[0][1]]
  return [test[0], test[1], [t for t, _ in pairs], [a for _, a in pairs]]


def literal(value):
  """A Python literal of an expected value, as tests_core.py writes it."""
  if isinstance(value, list):
    return "[" + ", ".join(literal(v) for v in value) + "]"
  return repr(value)


_JSON_CONSTANT = re.compile(r'"(?:[^"\\]|\\.)*"|\b(true|false|null)\b')
_PYTHON_CONSTANT = {"true": "True", "false": "False", "null": "None"}
WIDTH = 116


def _flat(value):
  """One line of JSON text with true, false and null outside the strings written as True, False and None: a Python
  literal."""
  text = json.dumps(value, separators=(", ", ": "))
  return _JSON_CONSTANT.sub(lambda m: _PYTHON_CONSTANT[m.group(1)] if m.group(1) else m.group(0), text)


def row_literal(value, col=2):
  """A test row as a Python literal that starts at column `col`.  A list or dict that does not fit in WIDTH has one
  element per line, aligned one column right of its opening bracket; a dict value starts after its key."""
  flat = _flat(value)
  if col + len(flat) <= WIDTH or not isinstance(value, (list, dict)) or not value:
    return flat
  inner = col + 1
  sep = ",\n" + " " * inner
  if isinstance(value, list):
    return "[" + sep.join(row_literal(x, inner) for x in value) + "]"
  parts = []
  for k, x in value.items():
    key = json.dumps(k) + ": "
    parts.append(key + row_literal(x, inner + len(key)))
  return "{" + sep.join(parts) + "}"


def test_file(rows, tests, refs, title, note):
  titles = dict(rows["sections"])
  counts = {}
  for t in tests:
    counts[refs[str(t[0])]["section"]] = counts.get(refs[str(t[0])]["section"], 0) + 1
  lines = ["# %s" % title, "#"] + ["# " + x for x in note] + ["#", "# Table of contents", "#"]
  for key, name in rows["sections"]:
    if counts.get(key):
      lines.append("# %s (%d tests)" % (name, counts[key]))
  lines += ["", "["]
  last = None
  for t in tests:
    sec = refs[str(t[0])]["section"]
    if sec != last:
      lines += ([] if last is None else [""]) + ["# == %s ==" % titles[sec], ""]
      last = sec
    lines.append("  " + row_literal(t) + ",")
  lines += ["]", ""]
  return "\n".join(lines)


ROW_NOTE = ["Rows [id, english_text, expected_answer, reference].  The reference holds the row's section and name, the",
            "known limit, the reason code of a Cannot answer row, the reviewed expectation, the listed plans as terms, and",
            "the reviewed gold translation (stage1 and stage2, or a fixture's formal record).",
            "tests/tests_planning_README.md defines the expected values.  Grade with solver/action_check.py",
            "(grade_row; runtests.py -actions does).  Checker: %s, version %d." % (ac.POLICY["name"],
                                                                                ac.POLICY["version"])]
NOTE = ROW_NOTE + ["Built by tests/action_route/make_planning_tests.py from tests/action_route/planning_rows.json; do "
                   "not edit by hand."]
CONTRAST_NOTE = ["The contrast texts of prompt revision I (memos/TASK_2026_09_30_planning_fixes_opus.md, section 8.2): one",
                 "text where a changed rule applies and one near text where it must not.  They join tests_planning.py",
                 "after their run.  Built by tests/action_route/make_planning_tests.py."] + ROW_NOTE
BASIC_NOTE = ["Rows [id, english_text, expected_answer, expected_actions]: the basic file of the planning test set.",
              "expected_answer is the answer text of the route, or a list of alternative texts.  expected_actions is",
              "the plan of that text as action terms with names, [] for the empty plan, or None when the text has no",
              "plan; with alternatives, one entry per alternative.  Grade with solver/planning_check.py (runtests.py",
              "-actions does; -answer-check text, actions or both).  tests/tests_planning.py holds the same rows with",
              "their gold translations; the checker does not read it.  tests/tests_planning_README.md describes both.",
              "Built by tests/action_route/make_planning_tests.py; do not edit by hand."]
DEV_NOTE = ["The prompt examples of the action route's measured prompts, in the form of tests_planning.py.  They are",
            "development material: never part of a headline number.  Built by tests/action_route/make_planning_tests.py."] + \
    ROW_NOTE


def rendered_files():
  rows, out = build()
  tests, refs = out["rows"]
  dtests, drefs = out["development"]
  ctests, crefs = out["contrasts"]
  basic = [basic_row(t, refs[str(t[0])]) for t in tests]
  return {"test": test_file(rows, tests, refs, "Planning test set for the action route, version %s." % rows["version"],
                            NOTE),
          "basic": test_file(rows, basic, refs, "Planning test set for the action route, version %s: the basic file."
                             % rows["version"], BASIC_NOTE),
          "dev": test_file(rows, dtests, drefs, "Planning development set: the prompt examples.", DEV_NOTE),
          "contrasts": test_file(rows, ctests, crefs, "Planning contrasts of prompt revision I: fresh texts in pairs.",
                                 CONTRAST_NOTE)}


# ---------------------------------------------------------------------------
# the inventory (phase 0 of the task)


ELLIPTICAL = re.compile(r"^(After (the same|taking|putting|the bus)|Does \w+ing )")
INTERNAL = ("other:insufficient_search_allowance", "other:translation_invalid", "other:ordinary_result",
            "other:source_compiled")
S2_RECORDS = ("c07_clean_bowl",)


def fixture_triage(rows):
  """Every row of fixture_rows.tsv with its disposition: version 1, or the rule that drops it, or version 2."""
  chosen = {"%s:%s:%s" % tuple(r["fixture"]) for r in rows["rows"] if "fixture" in r}
  s3 = {k: v for k, v in rows["not_in_version_1"].items() if k.count(":") == 2}
  out = []
  with open(FIXTURE_ROWS) as f:
    for r in csv.DictReader(f, delimiter="\t"):
      variant = "base" if r["variant"] == "None" else r["variant"]
      key = "%s:%s:%s" % (r["record"], variant, r["query"])
      q = r["question"]
      if key in chosen:
        why = "version 1"
      elif r["in_cohort"] == "True":
        why = "S5: a v6 text"
      elif q.startswith("(") or r["qkind"] != "@id":
        why = "S1: no English question"
      elif ELLIPTICAL.match(q):
        why = "S1: an elliptical question"
      elif r["kind"] in INTERNAL or (r["record"] == "c11_method_collision" and variant == "base"):
        why = "S4: an internal outcome"
      elif r["record"] in S2_RECORDS:
        why = "S2: the answer depends on a profile option"
      elif key in s3:
        why = s3[key]
      else:
        why = "version 2"
      out.append((key, r["kind"], q, why))
  return out


def inventory():
  rows, out = build()
  tests, refs = out["rows"]
  L = ["# Planning test set, version %s: the inventory" % rows["version"], "",
       "Written by `tests/action_route/make_planning_tests.py --inventory` from `planning_rows.json`. One row per test:",
       "its origin, question kind, the reviewed expectation, the expected value of the test file, its section, exposure",
       "and known limit.", "",
       "| id | origin | kind | reviewed expectation | expected value | exposure | known limit |",
       "|---|---|---|---|---|---|---|"]
  titles = dict(rows["sections"])
  last = None
  for t in tests:
    ref = refs[str(t[0])]
    if ref["section"] != last:
      L.append("| **%s** | | | | | | |" % titles[ref["section"]])
      last = ref["section"]
    e = ref["expect"]
    rev = e.get("outcome") or "answer %s" % e.get("answer")
    if e.get("reason"):
      rev += " (%s)" % e["reason"]
    L.append("| %d | %s | %s | %s | `%s` | %s | %s |" % (
      t[0], ref["origin"], ref["question_kind"], rev, literal(t[2]).replace("|", "/"), ref["exposure"],
      ref["known_limit"] or ""))
  L += ["", "## The texts", ""]
  for t in tests:
    L.append("%d. %s" % (t[0], t[1]))
  L += ["", "## Rows whose expected value differs from the reviewed expectation", ""]
  for t in tests:
    ref = refs[str(t[0])]
    row = [r for r in rows["rows"] if r["id"] == t[0]][0]
    if "expected" in row or row.get("known_limit") or (ref["expect"].get("outcome") == "unsupported_backend_requirement"):
      L.append("- %d %s: expected `%s`, reviewed %s; known limit %s. %s" % (
        t[0], ref["name"], literal(t[2]), ref["expect"].get("outcome") or ref["expect"].get("answer"),
        ref["known_limit"], row.get("note") or ""))
  L += ["", "## Cannot answer rows", ""]
  for t in tests:
    ref = refs[str(t[0])]
    vals = t[2] if isinstance(t[2], list) else [t[2]]
    if any(isinstance(v, str) and v.startswith("Cannot answer") for v in vals):
      other = [literal(v) for v in vals if not (isinstance(v, str) and v.startswith("Cannot answer"))]
      L.append("- %d %s (`%s`): %s" % (t[0], ref["name"], ref.get("reason"),
                                       "the reader's answer %s" % ", ".join(other) if other else "no single reading"))
  L += ["", "## Near-equal texts", ""]
  for x in rows.get("near_equal") or []:
    L.append("- rows %s: %s" % (", ".join(str(i) for i in x["rows"]), x["note"]))
  L += ["", "## Texts not in version 1", ""]
  for k, v in rows["not_in_version_1"].items():
    L.append("- %s: %s" % (k, v))
  triage = fixture_triage(rows)
  counts = {}
  for _, _, _, why in triage:
    counts[why.split(":")[0]] = counts.get(why.split(":")[0], 0) + 1
  L += ["", "## The %d fixture rows" % len(triage), "",
        "By disposition: %s." % ", ".join("%s %d" % kv for kv in sorted(counts.items())), "",
        "| fixture row | kind | question | disposition |", "|---|---|---|---|"]
  for key, kind, q, why in triage:
    L.append("| %s | %s | %s | %s |" % (key, kind, q.replace("|", "/"), why))
  return "\n".join(L) + "\n"


def main(argv):
  if "--inventory" in argv:
    path = argv[argv.index("--inventory") + 1]
    with open(path, "w") as f:
      f.write(inventory())
    print("wrote " + path)
    return 0
  files = rendered_files()
  if "--check" in argv:
    drift = [k for k, text in files.items() if not os.path.exists(OUT[k]) or open(OUT[k]).read() != text]
    if drift:
      print("drift: " + ", ".join(OUT[k] for k in drift))
      return 1
    print("the planning files equal a fresh build")
    return 0
  for k, text in files.items():
    with open(OUT[k], "w") as f:
      f.write(text)
    print("wrote " + OUT[k])
  return 0


if __name__ == "__main__":
  sys.exit(main(sys.argv[1:]))
