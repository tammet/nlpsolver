"""Action route: the detailed checker of the planning test set (`tests/tests_planning.py`, the detailed file).

The runner grades with `solver/planning_check.py` on the basic file; this checker is used to build and check the
detailed file (`tests/action_route/make_planning_tests.py`, `check_planning_tests.py`) and for analyses.

  grade_row(row, answer, record=None)                   -> {"correct", "grade", "detail", "translation_equal"}
  grade(expected, answer, record=None, reference=None) -> the same, from the parts of a row
  parse_answer(text)                                    -> the kind and parts of an answer string
  parse_expected(value)                                 -> the same for an expected value
  compiled(reference)                                   -> (source artifact, query artifact) of a reference record
  POLICY                                                -> the policy record stored in each case file

Pure functions: no model call and no GK launch.  A row of the test file is complete: [id, text, expected,
reference].  `expected` is True, False, None, a string or a list of alternatives.  The reference is a dict: the
reviewed gold translation (`stage1` and `stage2`, or a fixture's `formal` record), the listed plans as terms
(`plans`), the reviewed expectation, the reason code and the known limit; `reference_of` adds the row's text.  A row
without a reference is graded without one.  `answer` is the pipeline's answer string (`action_pipeline.answer_text`).
`record` is the run's `action_route` record, whose result holds the plan terms (`plan`, `plan_named`).

A plan answer is graded by its terms when the answer has plan terms and the row has a supported reference (C1):
listed by terms (`plan_named` equals a listed plan with names in place of ids), else valid or invalid by the replay
(the names are aligned with the reference entities and `action_replay.replay` runs the plan on the reference
translation with its goal, step bound and selection).  A change step that is no action of the reference is aligned
by its source verb (C2, `plan_verbs`): the one reference permission with the same verb root, actor, object and tool
gives its value.  Without plan terms or without a supported reference, the plan is compared by its text (C3, `by:
text`): the step lists of the normalized sentences are equal, in order, with "with" equal to "in" only before the tool
at the end of a change step (C4).  Any valid plan is correct.  `extra_steps` is its length minus the shortest listed
plan's.  The confidence is compared as a word (C7): "Probably" is present in both or in neither.  Each grade records
whether the accepted translation equals the reference translation up to the renaming of entity indices, unit ids and
variables (C6, `translation_equal`).

The grades:

  match           correct   yes, no, unknown, a name, No plan found., No action is needed., Inconsistent, with the
                            same qualifier; No plan found. for Unknown of a reachability question (C5)
  listed          correct   the plan equals a listed plan
  valid           correct   another plan, which the reference replay validates; also a plan answer to a
                            reachability question whose expected value is True (C5)
  not_answered    correct   a Cannot answer row: the answer is Cannot answer, Unknown. or No plan found.
  definite_answer wrong     a Cannot answer row: a plan, Yes, No, a name or No action is needed. that no listed
                            alternative accepts
  invalid         wrong     the reference replay rejects the plan
  unlisted        wrong     another plan, and no reference record to replay it on
  unverified      wrong     the replay gives not_checked or contested, or a name does not align
  mismatch        wrong     another answer kind or value than expected
  no_answer       wrong     Cannot answer, where an answer was expected
  error           wrong     Error: ..., for every expected value
"""

import json
import re


import action_english as aen
import action_pipeline as ap
import action_replay as rp
import action_route as ar
import lc_action as la

POLICY = {
  "name": "planning_answer_check",
  "version": 2,
  "module": "solver/action_check.py",
  "correct_grades": ["match", "listed", "valid", "not_answered"],
  "rules": [
    "True, False and None are Yes, No and Unknown; the confidence is a word: Probably is present in both the answer "
    "and the expected value or in neither",
    "a plan with terms on a row with a supported reference is listed by terms or graded by the replay on the reviewed "
    "reference translation; a change step that is no action of the reference is aligned by its source verb; any valid "
    "plan is correct; a plan without terms or a row without a supported reference is compared by its text",
    "a plan answer to a reachability question with the expected value True is graded by its replay; No plan found. "
    "matches Unknown of a reachability question",
    "on a Cannot answer row, Cannot answer, Unknown. and No plan found. are correct; a definite answer is wrong "
    "unless the row lists it; the reason code is information only",
    "Error: is never correct",
    "a list is any one of its alternatives; the best grade counts",
    "each case records whether its accepted translation equals the reference translation up to renaming"],
}
CORRECT = ("match", "listed", "valid", "not_answered")
# the order in which the grade of one alternative is preferred over another's
RANK = ("match", "listed", "valid", "not_answered", "invalid", "unverified", "definite_answer", "mismatch", "unlisted",
        "no_answer", "error")
# "a" stays: it is also the name of a block ("block a"), and the renderer writes no indefinite article before a name
ARTICLES = re.compile(r"\b(?:the|an)\b", re.I)
QUALIFIER = re.compile(r"^probabl[ey]\s+", re.I)
# the entity slots of each constructor (1-based positions in a term); every other argument is compared as written
ENTITY_SLOTS = {"move": (1, 2, 3), "take": (1, 2), "put_on": (1, 2, 3), "put_in": (1, 2, 3), "change": (1, 2, 4)}


# ---------------------------------------------------------------------------
# reading answers and expected values


def _words(text):
  s = ARTICLES.sub(" ", text.lower())
  s = re.sub(r"[^a-z0-9_ ,]+", " ", s)
  return " ".join(s.split())


def plan_steps_of(text):
  """The normalized step list of a plan sentence: lower case, the articles "the" and "an" removed, spaces collapsed,
  the prefixes Probably, Yes. and Plan: and the final period removed, split at ", then"."""
  s = QUALIFIER.sub("", text.strip())
  s = re.sub(r"^yes\s*\.\s*", "", s, flags=re.I)
  s = re.sub(r"^plan\s*:\s*", "", s, flags=re.I)
  s = s.rstrip(" .")
  return [" ".join(ARTICLES.sub(" ", step.lower()).split()) for step in s.split(", then ")]


def _change_step(step):
  """C4: whether a normalized step is a change step: no put, take or move."""
  return not re.search(r"\b(?:goes|puts|takes)\b", step) and not step.startswith("from ")


def text_steps(steps):
  """C4: a step list for the text comparison: in a change step, "in" before the tool at the end is "with"."""
  return [re.sub(r" in ((?:\w+ )?\w+)$", r" with \1", x) if _change_step(x) else x for x in steps]


def _names_of(text):
  s = _words(text.rstrip(" ."))
  return sorted(x.strip() for x in re.split(r",| and ", s) if x.strip())


def parse_answer(text):
  """{"kind", "qualified", "plan", "names", "reason"} of an answer string.  kind: error, cannot, yes, no, unknown,
  contested, plan, no_action, no_plan, inconsistent, name, other.  A reachable answer "Yes. Plan: ..." is kind yes
  with its plan; "Yes. No action is needed." is kind yes with the empty plan."""
  out = {"kind": "other", "qualified": False, "plan": None, "names": None, "reason": None, "text": text}
  if not isinstance(text, str):
    return out
  s = text.strip()
  if QUALIFIER.match(s):
    # C7: "Probably yes.", "Probably no.", "Probably yes. Plan: ...", "Probable plan: ..."
    out["qualified"] = True
    s = QUALIFIER.sub("", s)
    s = s[:1].upper() + s[1:]
  low = s.lower()
  if low.startswith("error"):
    out["kind"] = "error"
    return out
  if low.startswith("cannot answer"):
    out["kind"] = "cannot"
    m = re.search(r"\[([^;\]]*);", s)
    out["reason"] = [x.strip() for x in m.group(1).split(",")] if m else None
    return out
  if re.match(r"^(yes|true)\b", low):
    out["kind"] = "yes"
    rest = re.sub(r"^(yes|true)\s*\.?\s*", "", s, flags=re.I)
    if rest.lower().startswith("plan"):
      out["plan"] = plan_steps_of(rest)
    elif rest.lower().startswith("no action is needed"):
      out["plan"] = []
    return out
  if re.match(r"^(no|false)\b", low) and not low.startswith(("no plan", "no action")):
    out["kind"] = "no"
    return out
  if low.startswith("plan"):
    out["kind"], out["plan"] = "plan", plan_steps_of(s)
    return out
  if low.startswith("no action is needed"):
    out["kind"], out["plan"] = "no_action", []
    return out
  if low.startswith("no plan found"):
    out["kind"] = "no_plan"
    return out
  if low.startswith("unknown"):
    out["kind"] = "unknown"
    return out
  if low.startswith("contested"):
    out["kind"] = "contested"
    return out
  if low.startswith("inconsistent"):
    out["kind"] = "inconsistent"
    return out
  if low.startswith("source compiled"):
    return out
  out["kind"], out["names"] = "name", _names_of(s)
  return out


def parse_expected(value):
  """The same record for one expected value of the test file."""
  if value is True:
    return dict(parse_answer("Yes."), text=value)
  if value is False:
    return dict(parse_answer("No."), text=value)
  if value is None:
    return dict(parse_answer("Unknown."), text=value)
  return parse_answer(value)


# ---------------------------------------------------------------------------
# the reference


_COMPILED = {}


def compiled(reference):
  """(source, query) compiled from a reference record: `stage1` and `stage2` (a reviewed translation, compiled as the
  route compiles a model's translation), or `formal` (a reviewed fixture record, compiled as the fixtures are)."""
  key = json.dumps([reference.get("stage1"), reference.get("stage2"), reference.get("formal"), reference.get("text")],
                   sort_keys=True)
  if key in _COMPILED:
    return _COMPILED[key]
  if reference.get("formal"):
    f = reference["formal"]
    # as the formal route: the Stage-1 projections only when every unit has one, else a formal source
    s1 = ([{"id": u["id"], "text": u.get("text"), "stage1": u["stage1"]} for u in f["units"]]
          if all(u.get("stage1") for u in f["units"]) else None)
    contexts = {u["id"]: u["context"] for u in f["units"] if u.get("context")}
    source = ar.compile_source(s1, [u["stage2"] for u in f["units"]], f.get("profile") or la.PROFILE, f.get("text"),
                               f.get("entities"), worlds=f.get("worlds"), contexts=contexts or None)
    q = f["query"]
    query = ar.compile_query(q["stage2"], source, q.get("limits"), None,
                             **{k: q[k] for k in ("planning_root", "ambient", "knower") if k in q})
  else:
    units, errors = ap.stage1_units(reference["stage1"])
    if errors:
      raise ValueError("the reference Stage 1 is invalid: %s" % errors)
    got, errors = ap.stage2_packages(reference["stage2"])
    if errors:
      raise ValueError("the reference Stage 2 is invalid: %s" % errors)
    worlds, contexts, packages = got
    src, qs = ap.split_packages(packages)
    rec = {"query_contexts": reference["stage2"].get("query_contexts") or {}}
    stop = ap.compile_translation(rec, reference["text"], units, worlds, contexts, src, qs, (), reference["stage2"].get("types"))
    if stop not in ([], "unsupported"):
      raise ValueError("the reference does not compile: %s" % stop)
    source = rec.get("source")
    query = ar.compile_query(qs[0], source, None, None, **rec["query_contexts"].get(qs[0][1], {})) \
        if qs and source else None
  _COMPILED[key] = (source, query)
  return source, query


def _index(source):
  """{name: [entity ids]} and {last word: [entity ids]} of a reference source, lower case."""
  by_name, by_last = {}, {}
  for t in (source.get("identity") or {}):
    n = aen.entity_word(t).lower()
    by_name.setdefault(n, []).append(t)
    by_last.setdefault(n.split()[-1], []).append(t)
  return by_name, by_last


def align(named, source):
  """The plan with reference entity ids in place of names, or (None, the name that does not align).  A name maps to
  the reference entity of the same name; else to the one reference entity with the same last word (hand for robot
  hand)."""
  by_name, by_last = _index(source)
  out = []
  for step in named:
    term = list(step)
    for i in ENTITY_SLOTS.get(step[0], ()):
      if i >= len(term) or term[i] == la.UNSPECIFIED:
        continue
      n = str(term[i]).lower()
      hit = by_name.get(n) or by_last.get(n.split()[-1] if n else n)
      if not hit or len(hit) != 1:
        return None, term[i]
      term[i] = hit[0]
    out.append(term)
  return out, None


def _listed_named(reference):
  return [[[step[0]] + [aen.entity_word(t).lower() if la.is_concrete(t) else t for t in step[1:]] for step in p]
          for p in reference.get("plans") or []]


def _lower(named):
  return [[step[0]] + [str(t).lower() for t in step[1:]] for step in named]


def _shortest(reference):
  plans = reference.get("plans") or []
  n = (reference.get("expect") or {}).get("reference_shortest_length")
  return n if isinstance(n, int) else (min(len(p) for p in plans) if plans else None)


def _answer_plan(record):
  """(plan terms, plan_named) of a run's result, or (None, None)."""
  res = (record or {}).get("result") or {}
  if res.get("plan") is None:
    return None, None
  named = res.get("plan_named")
  if named is None:
    named = [[s[0]] + [aen.entity_word(t) if la.is_concrete(t) else t for t in s[1:]] for s in res["plan"]]
  return res["plan"], named


def supported(reference):
  """Whether a reference record compiles to a supported source with a plan or reachability query (C1)."""
  if not reference:
    return False
  try:
    source, query = compiled(reference)
  except (ValueError, ar.ArtifactError):
    return False
  return (source is not None and query is not None and query["query"]["kind"] in ("plan", "reachable")
          and (source.get("support") or {}).get("status") == "supported")


def _unifies(pattern, term):
  """Whether a reference action term (with variables) covers a ground term."""
  if not (isinstance(pattern, list) and isinstance(term, list) and len(pattern) == len(term) and pattern[0] == term[0]):
    return False
  env = {}
  for p, t in zip(pattern[1:], term[1:]):
    if la.is_var(p):
      if env.setdefault(p, t) != t:
        return False
    elif p != t:
      return False
  return True


def _permissions(source):
  """[(unit, Stage-1 roots, action term)] of the reference's availability units."""
  return [(u["id"], u.get("roots") or [], t) for u in source["units"] if u.get("form") == "availability"
          and u.get("status") == "supported" for t in u.get("action_terms") or []]


def align_verbs(plan, verbs, source):
  """C2: (plan, alignments).  A change step whose term is no action of the reference takes the value of the one
  reference permission with the same source verb root, actor, object and tool; otherwise the step stays as written."""
  perms = _permissions(source)
  out, notes = [], []
  for i, step in enumerate(plan):
    verb = verbs[i] if verbs and i < len(verbs) else None
    if step[0] != "change" or verb is None or any(_unifies(t, step) for _, _, t in perms):
      out.append(step)
      continue
    hits = [(uid, t) for uid, roots, t in perms if verb in roots and t[0] == "change"
            and all(la.is_var(t[k]) or t[k] == step[k] for k in (1, 2, 4))]
    terms = []
    for uid, t in hits:
      if t not in [x for _, x in terms]:
        terms.append((uid, t))
    if len(terms) != 1 or la.is_var(terms[0][1][3]):
      out.append(step)
      notes.append({"step": i + 1, "verb": verb, "aligned": False, "candidates": len(terms)})
      continue
    new = list(step)
    new[3] = terms[0][1][3]
    out.append(new)
    notes.append({"step": i + 1, "verb": verb, "aligned": True, "unit": terms[0][0], "from": step, "to": new})
  return out, notes


def replay_plan(named, reference, verbs=None):
  """(verdict, detail) of a named plan replayed on the reference translation with its goal, step bound and
  selection.  `verbs` are the answer's `plan_verbs` (C2)."""
  source, query = compiled(reference)
  if source is None or query is None or query["query"]["kind"] not in ("plan", "reachable"):
    return "no_reference_query", {}
  plan, bad = align(named, source)
  if plan is None:
    return "unaligned", {"name": bad}
  plan, notes = align_verbs(plan, verbs, source)
  q = query["query"]
  r = rp.replay(source, plan, goal=q["goal"], steps=q["steps"], planning_root=query["planning_root"],
                ambient=query["ambient"], knower=query["knower"])
  detail = {"step": r["step"], "reason": r["reason"], "aligned_plan": plan}
  if notes:
    detail["verb_alignment"] = notes
  return r["verdict"], detail


# ---------------------------------------------------------------------------
# translation fidelity (C6)


WORLD = la.WORLD


def _canonical(packages, types=None, worlds=None, contexts=None, selections=None):
  """The canonical form of a translation: unit ids, entity indices and variables renamed in order of first
  appearance; world names kept; the effective world declaration, the context records and the effective query
  selections (an explicit planning_root equal to the default root, the last declared world, is the default)."""
  worlds = list(worlds or ["W0"])
  units, ents = {}, {}
  for p in packages:
    if isinstance(p, list) and len(p) == 3:
      units.setdefault(p[1], "U%d" % (len(units) + 1))

  def ent(t):
    if t not in ents:
      base = t.rsplit(" ", 1)[0]
      ents[t] = "%s #%d" % (base, 1 + sum(1 for x in ents if x.rsplit(" ", 1)[0] == base))
    return ents[t]

  def walk(f, vs):
    if isinstance(f, list):
      return [walk(x, vs) for x in f]
    if isinstance(f, str):
      if f in units:
        return units[f]
      if f in worlds or WORLD.match(f):
        return f
      if la.is_var(f):
        return vs.setdefault(f, "V%d" % (len(vs) + 1))
      if la.is_concrete(f):
        return ent(f)
    return f
  out = [[p[0], units.get(p[1], p[1]), walk(p[2], {})] if isinstance(p, list) and len(p) == 3 else p
         for p in packages]
  typ = {units.get(k, k): sorted(json.dumps(walk(a, {}), sort_keys=True) for a in v)
         for k, v in (types or {}).items()} if isinstance(types, dict) else {}
  # a context record as the compiler reads it: no entry is no record, and tense present is the default
  ctx = {}
  for k, v in (contexts or {}).items():
    rec = {kk: walk(vv, {}) for kk, vv in (v or {}).items() if vv is not None and (kk, vv) != ("tense", "present")}
    if rec:
      ctx[units.get(k, k)] = rec
  queries = [p[1] for p in packages if isinstance(p, list) and len(p) == 3 and isinstance(p[2], list) and p[2]
             and p[2][0] in ("plan", "reachable", "verify", "question", "ask")]
  sel = {}
  for q in queries:
    given = (selections or {}).get(q) or {}
    sel[units.get(q, q)] = {"planning_root": given.get("planning_root") or worlds[-1],
                            "ambient": walk(given.get("ambient"), {}), "knower": walk(given.get("knower"), {})}
  return {"worlds": worlds, "packages": out, "types": typ, "contexts": ctx, "selections": sel}


def reference_translation(reference):
  """(packages, types, worlds, contexts, selections) of a reference record's translation, or None."""
  if reference.get("formal"):
    f = reference["formal"]
    q = f["query"]
    contexts = {u["id"]: u["context"] for u in f["units"] if u.get("context")}
    selection = {k: q[k] for k in ("planning_root", "ambient", "knower") if q.get(k)}
    return ([u["stage2"] for u in f["units"]] + [q["stage2"]], f.get("types"), f.get("worlds"), contexts,
            {q["stage2"][1]: selection} if selection else {})
  if reference.get("stage2"):
    got, errors = ap.stage2_packages(reference["stage2"])
    if errors:
      return None
    s2 = reference["stage2"] if isinstance(reference["stage2"], dict) else {}
    return got[2], s2.get("types"), got[0], got[1], s2.get("query_contexts")
  return None


def translation_equal(record, reference):
  """C6: whether the run's accepted translation equals the reference translation up to the renaming of unit ids,
  entity indices and variables, with the same worlds, context records and query selections; None
  without an accepted translation or a reference translation."""
  stage2 = ((record or {}).get("translation") or {}).get("stage2")
  ref = reference_translation(reference) if reference else None
  if not stage2 or not stage2.get("packages") or ref is None:
    return None
  mine = _canonical(stage2["packages"], stage2.get("types"), stage2.get("worlds"), stage2.get("contexts"),
                    stage2.get("query_contexts"))
  return mine == _canonical(*ref)


# ---------------------------------------------------------------------------
# grading


def _result(grade, **detail):
  return {"correct": grade in CORRECT, "grade": grade, "detail": detail}


def _qualifier(exp, ans):
  """C7: the confidence as a word: Probably in both or in neither."""
  return exp["qualified"] == ans["qualified"]


def _plan_verbs(record):
  return ((record or {}).get("result") or {}).get("plan_verbs")


def _plan_grade(exp, ans, record, reference):
  """The grade of a plan answer against one expected plan: by the terms when the answer has them and the row has a
  supported reference (C1), else by the text (C3)."""
  steps = ans["plan"]
  terms, named = _answer_plan(record)
  shortest = _shortest(reference or {})
  extra = (len(named) if named is not None else len(steps)) - shortest if shortest is not None else None
  if not _qualifier(exp, ans):
    return _result("mismatch", why="confidence", expected=exp["qualified"], got=ans["qualified"])
  if named is not None and supported(reference):
    if _lower(named) in _listed_named(reference):
      return _result("listed", by="terms", extra_steps=extra)
    verdict, detail = replay_plan(named, reference, _plan_verbs(record))
    if verdict == "valid":
      return _result("valid", by="terms", extra_steps=extra, **detail)
    if verdict == "invalid":
      return _result("invalid", by="terms", **detail)
    return _result("unverified", by="terms", verdict=verdict, **detail)
  why = "no plan terms" if named is None else "no supported reference"
  if exp["plan"] is not None and text_steps(steps) == text_steps(exp["plan"]):
    return _result("listed", by="text", why=why, extra_steps=extra)
  return _result("unlisted", by="text", why=why)


def _reachable(record, reference):
  """Whether the question is a reachability question: the reference's query kind, else the run's."""
  if reference and supported(reference):
    return compiled(reference)[1]["query"]["kind"] == "reachable"
  return (((record or {}).get("result") or {}).get("query") or {}).get("kind") == "reachable"


def _grade_one(exp, ans, record, reference):
  kind = ans["kind"]
  if kind == "error":
    return _result("error")
  if exp["kind"] == "cannot":
    if kind in ("cannot", "unknown", "no_plan", "contested"):
      want = (reference or {}).get("reason")
      agrees = None if not (want and ans["reason"]) else want in ans["reason"]
      return _result("not_answered", cannot_answer=kind == "cannot", reason_agrees=agrees, answer_kind=kind)
    return _result("definite_answer", answer_kind=kind)
  if kind == "cannot":
    return _result("no_answer", reason=ans["reason"])
  if exp["kind"] == "plan":
    if kind == "plan" or (kind == "yes" and ans["plan"]):
      return _plan_grade(exp, ans, record, reference)
    return _result("mismatch", answer_kind=kind)
  if exp["kind"] == "no_plan":
    if kind == "no_plan":
      return _result("match")
    detail = {"answer_kind": kind}
    _, named = _answer_plan(record)
    if kind in ("plan", "yes") and named and supported(reference):
      detail["replay"], _ = replay_plan(named, reference, _plan_verbs(record))
    return _result("mismatch", **detail)
  if exp["kind"] == "no_action":
    if kind == "no_action" or (kind == "yes" and ans["plan"] == []):
      return _result("match")
    return _result("mismatch", answer_kind=kind)
  if exp["kind"] == "yes" and kind == "plan" and _reachable(record, reference):
    # C5: a plan answer to a reachability question whose expected value is True: graded by its replay
    if not _qualifier(exp, ans):
      return _result("mismatch", why="confidence", expected=exp["qualified"], got=ans["qualified"])
    _, named = _answer_plan(record)
    if named is None or not supported(reference):
      return _result("unverified", by="text", why="no plan terms" if named is None else "no supported reference")
    verdict, detail = replay_plan(named, reference, _plan_verbs(record))
    grade = {"valid": "valid", "invalid": "invalid"}.get(verdict, "unverified")
    return _result(grade, by="terms", verdict=verdict, **detail)
  if exp["kind"] in ("yes", "no"):
    if kind != exp["kind"]:
      return _result("mismatch", answer_kind=kind)
    if not _qualifier(exp, ans):
      return _result("mismatch", why="confidence", expected=exp["qualified"], got=ans["qualified"])
    _, named = _answer_plan(record)
    if kind == "yes" and ans["plan"] is not None and named is not None and supported(reference):
      verdict, detail = replay_plan(named, reference, _plan_verbs(record))
      if verdict == "invalid":
        return _result("invalid", by="terms", **detail)
      return _result("match", plan_replay=verdict)
    return _result("match")
  if exp["kind"] == "unknown" and kind == "no_plan" and _reachable(record, reference):
    # C5: No plan found. is Unknown for a reachability question
    return _result("match", reachable_no_plan=True)
  if exp["kind"] in ("unknown", "inconsistent"):
    return _result("match") if kind == exp["kind"] else _result("mismatch", answer_kind=kind)
  if exp["kind"] == "name":
    if kind == "name" and ans["names"] == exp["names"]:
      return _result("match")
    return _result("mismatch", answer_kind=kind, got=ans["names"], expected=exp["names"])
  return _result("mismatch", answer_kind=kind)


def reference_of(row):
  """The reference record of a test row [id, text, expected, reference]: its reference with the row's text, or None
  for a row without a reference."""
  if len(row) < 4 or not row[3]:
    return None
  return dict(row[3], text=row[1])


def grade_row(row, answer, record=None):
  """The grade of an answer to a test row: the row's expected value against the answer, with the row's reference."""
  return grade(row[2], answer, record, reference_of(row))


def grade(expected, answer, record=None, reference=None):
  """{"correct", "grade", "detail", "translation_equal"} of one answer.  With a list as `expected`, the best grade of
  the alternatives counts, and `detail.alternative` names the one that gave it.  `translation_equal` is C6."""
  alternatives = expected if isinstance(expected, list) else [expected]
  ans = parse_answer(answer)
  best = None
  for i, value in enumerate(alternatives):
    g = _grade_one(parse_expected(value), ans, record, reference)
    if len(alternatives) > 1:
      g["detail"]["alternative"] = i
    if best is None or RANK.index(g["grade"]) < RANK.index(best["grade"]):
      best = g
  best["translation_equal"] = translation_equal(record, reference)
  return best
