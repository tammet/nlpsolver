"""Action route: the answer checker of the basic planning test file (`tests/tests_planning_basic.py`).

  grade(expected, actions, answer, plan=None, mode="text", verbs=None) -> {"correct", "grade", "detail"}
  grade_row(row, answer, record=None, mode="text")          -> the same for a row [id, input, expected, actions]
  parse(text)                                               -> the kind and parts of an answer text
  POLICY, policy(mode)                                      -> the policy record stored in each case file

A row is [id, input, expected, actions].  `expected` is the expected answer text, or a list of alternative texts.
`actions` is the expected action list of that text: a plan as a list of action terms with names in place of entity
ids (`["move", "Greta", "Bergen", "Voss", "train"]`), `[]` for the empty plan, or None when the text has no plan; with
a list of alternatives, a list with one such entry per alternative.  `plan` is the plan of the run
(`plan_named` of the route's result), or None; `verbs` are the source verbs of its steps (`plan_verbs`).  The
checker never reads the detailed file `tests/tests_planning.py`.
Pure functions: no model call and no GK launch.

The modes:

  text     the answer text against the expected text (rules T1-T8 below)
  actions  the plan against the expected action list where the alternative has one (rules A1-A2); the text where
           it has none
  both     the text, and the plan where the alternative has an action list

The text comparison reads each text into a kind and its parts, and accepts the differences that come from the
translation rather than from the answer.  It is a heuristic and can be wrong:

  T1  case, spacing, the final period and the articles "the" and "an" do not count; "a" does not count before a word
      that is not a preposition or a conjunction, so "block a" keeps its name
  T2  Yes, No, Unknown and Contested: the kind and the qualifier "Probably" must agree; True and False are Yes and No
  T3  a plan after Yes (a reachability answer, "Yes. Plan: ...", "Yes. No action is needed.") is extra when the
      expected text is a bare Yes; when the expected text has a plan, the plans are compared
  T4  a plan: the same steps in the same order, and the same qualifier ("Plan" or "Probable plan"); a step may name a
      thing with an extra word before its noun ("the robot hand" for "the hand"), and "in" equals "with" before the
      tool at the end of a change step
  T5  a wh-answer: the same names in any order, with T1 and the extra word of T4
  T6  Cannot answer matches Cannot answer whatever its sentence and its bracket of reason codes (the detail says
      whether the sentence is the same); on a Cannot answer alternative, Unknown and No plan found also count as not
      answered (grade not_answered)
  T7  Inconsistent matches Inconsistent with or without its facts; No action is needed. matches itself and "Yes. No
      action is needed."; No plan found. also matches an expected Unknown (a reachability question read as a plan
      question)
  T8  Error: never matches

The action comparison:

  A1  the same number of steps, each with the same action and the same arguments in order; a name compares by T1,
      and a name may have an extra word before its noun (T4)
  A2  [] is the empty plan; a run without a plan matches no action list
  A3  a change step whose result value alone differs matches when the run's source verb of that step is the verb of
      the same step in the expected text ("fried" for "cooked" when both steps say "fries"): the model named the
      result of the stated operation in another word
"""

import re

from linguistics import third_person     # the form the plan sentence writes (fry, fries; wax, waxes)

MODES = ("text", "actions", "both")
POLICY = {
  "name": "planning_check",
  "version": 1,
  "module": "solver/planning_check.py",
  "test_file": "tests/tests_planning_basic.py",
  "correct_grades": ["match", "not_answered"],
  "rules": [
    "T1 case, spacing, the final period and the articles do not count; a single-letter name after a noun stays",
    "T2 Yes, No, Unknown and Contested: the kind and Probably agree",
    "T3 a plan after Yes is extra when the expected text is a bare Yes",
    "T4 a plan: the same steps in order and the same qualifier; an extra word before a noun; in equals with before "
    "the tool of a change step",
    "T5 a wh-answer: the same names in any order",
    "T6 Cannot answer matches Cannot answer; Unknown and No plan found are not_answered on a Cannot answer row",
    "T7 Inconsistent with or without its facts; No action is needed. with or without Yes.; No plan found. matches an "
    "expected Unknown",
    "T8 Error: never matches",
    "A1 the plan: the same actions and arguments in order, names by T1 and T4",
    "A2 [] is the empty plan; no plan matches no action list",
    "A3 a change step whose value alone differs matches when the run's source verb is the step's verb in the "
    "expected text",
    "actions mode compares the plan where an alternative has an action list, else the text; both compares the text "
    "and the plan"],
}
CORRECT = ("match", "not_answered")
# the order in which the grade of one alternative is preferred over another's
RANK = ("match", "not_answered", "no_answer", "mismatch", "error")

ARTICLES = ("the", "an")
# after "a": a word before which "a" is a name (block a), not an article
NOT_NOUN = {"on", "in", "into", "onto", "to", "from", "with", "by", "at", "and", "then", "of", "off", "is", "was"}
QUALIFIER = re.compile(r"^probabl[ey]\s+", re.I)


def policy(mode):
  """The policy record of a mode."""
  if mode not in MODES:
    raise ValueError("unknown check mode %r; one of %s" % (mode, ", ".join(MODES)))
  return dict(POLICY, mode=mode)


# ---------------------------------------------------------------------------
# reading a text


def words(text):
  """T1: the words of a text: lower case, punctuation but the comma removed, the articles dropped."""
  s = re.sub(r"[^a-z0-9_ ,'-]+", " ", (text or "").lower())
  toks = s.replace(",", " , ").split()
  out = []
  for i, t in enumerate(toks):
    if t in ARTICLES:
      continue
    if t == "a" and i + 1 < len(toks) and toks[i + 1] not in NOT_NOUN and toks[i + 1] != ",":
      continue
    out.append(t)
  return out


def _steps(text):
  """The steps of a plan sentence, each a list of words; "in" before the tool at the end of a change step is
  "with"."""
  s = re.sub(r"^(probable\s+)?plan\s*:\s*", "", text.strip(), flags=re.I).rstrip(" .")
  out = []
  for step in re.split(r",\s*then\s+|\s+then\s+", s):
    w = words(step)
    change = not ({"goes", "puts", "takes"} & set(w)) and w[:1] != ["from"]
    if change and "in" in w[-3:-1]:
      k = len(w) - 1 - w[::-1].index("in")
      w = w[:k] + ["with"] + w[k + 1:]
    out.append(w)
  return out


def _names(text):
  s = text.strip().rstrip(".")
  return [words(x) for x in re.split(r",\s*|\s+and\s+", s) if words(x)]


def parse(text):
  """{"kind", "qualified", "plan", "names", "sentence", "text"} of an answer text.  kind: error, cannot, yes, no,
  unknown, contested, plan, no_action, no_plan, inconsistent, name, other.  "Yes. Plan: ..." is kind yes with its
  plan; "Yes. No action is needed." kind yes with the empty plan."""
  if text is True:
    text = "Yes."
  elif text is False:
    text = "No."
  elif text is None:
    text = "Unknown."
  out = {"kind": "other", "qualified": False, "plan": None, "names": None, "sentence": None, "text": text}
  if not isinstance(text, str):
    return out
  s = text.strip()
  if QUALIFIER.match(s):
    out["qualified"] = True
    s = QUALIFIER.sub("", s)
  low = s.lower()
  if low.startswith("error"):
    out["kind"] = "error"
  elif low.startswith("cannot answer"):
    out["kind"] = "cannot"
    out["sentence"] = words(re.sub(r"\s*\[[^\]]*\]\s*$", "", s)[len("cannot answer"):].lstrip(" :"))
  elif re.match(r"^(yes|true)\b", low):
    out["kind"] = "yes"
    rest = re.sub(r"^(yes|true)\s*\.?\s*", "", s, flags=re.I)
    if rest.lower().startswith("plan"):
      out["plan"] = _steps(rest)
    elif rest.lower().startswith("no action is needed"):
      out["plan"] = []
  elif re.match(r"^(no|false)\b", low) and not low.startswith(("no plan", "no action")):
    out["kind"] = "no"
  elif low.startswith("plan"):
    out["kind"], out["plan"] = "plan", _steps(s)
  elif low.startswith("no action is needed"):
    out["kind"], out["plan"] = "no_action", []
  elif low.startswith("no plan found"):
    out["kind"] = "no_plan"
  elif low.startswith("unknown"):
    out["kind"] = "unknown"
  elif low.startswith("contested"):
    out["kind"] = "contested"
  elif low.startswith("inconsistent"):
    out["kind"] = "inconsistent"
  elif not low.startswith("source compiled"):
    out["kind"], out["names"] = "name", _names(s)
  return out


# ---------------------------------------------------------------------------
# comparing


def same_words(a, b):
  """T4: equal word lists, or equal once the longer list drops words that each stand directly before a noun both
  lists share (an extra modifier: "robot hand" for "hand").  A word before a preposition or a conjunction is no
  modifier: "paints the door white with the brush" is not "paints the door with the brush"."""
  if a == b:
    return True
  long, short = (a, b) if len(a) > len(b) else (b, a)
  i = j = 0
  while i < len(long):
    if j < len(short) and long[i] == short[j]:
      i += 1
      j += 1
    elif (j < len(short) and i + 1 < len(long) and long[i] != "," and long[i + 1] == short[j]
          and short[j] not in NOT_NOUN and short[j] != ","):
      i += 1                           # an extra word directly before the next shared noun
    else:
      return False
  return j == len(short)


def same_plan(a, b):
  return a is not None and b is not None and len(a) == len(b) and all(same_words(x, y) for x, y in zip(a, b))


def same_names(a, b):
  if a is None or b is None or len(a) != len(b):
    return False
  rest = list(b)
  for x in a:
    hit = next((y for y in rest if same_words(x, y)), None)
    if hit is None:
      return False
    rest.remove(hit)
  return True


def _term(t):
  return words(t) if isinstance(t, str) else [str(t).lower()]


def same_actions(plan, expected, verbs=None, text=None):
  """A1-A3: the run's plan against one expected action list.  `verbs` are the run's source verbs per step, `text` the
  step word lists of the expected plan text (A3)."""
  if plan is None or expected is None or len(plan) != len(expected):
    return False
  for i, (x, y) in enumerate(zip(plan, expected)):
    if not (isinstance(x, list) and isinstance(y, list) and x[:1] == y[:1] and len(x) == len(y)):
      return False
    same = [same_words(_term(p), _term(q)) for p, q in zip(x[1:], y[1:])]
    if all(same):
      continue
    # A3: only the value of a change differs, and the run's verb is the expected step's verb
    verb = verbs[i] if verbs and i < len(verbs) else None
    if not (x[0] == "change" and len(x) == 5 and same[:2] + same[3:] == [True, True, True] and verb
            and text and i < len(text) and third_person(str(verb).lower()) in text[i]):
      return False
  return True


def text_grade(exp, ans):
  """(grade, detail) of an answer text against one expected text, both parsed."""
  ek, ak = exp["kind"], ans["kind"]
  if ak == "error":
    return "error", {}
  if ek == "cannot":
    if ak == "cannot":
      return "match", {"same_sentence": exp["sentence"] == ans["sentence"]}
    if ak in ("unknown", "no_plan"):
      return "not_answered", {"answer_kind": ak}
    return "mismatch", {"answer_kind": ak}
  if ak == "cannot":
    return "no_answer", {}
  if exp["qualified"] != ans["qualified"] and ek in ("yes", "no", "plan"):
    return "mismatch", {"why": "the qualifier Probably"}
  if ek == "yes":
    if ak != "yes" and not (ak == "no_action" and exp["plan"] == []):
      return "mismatch", {"answer_kind": ak}
    if exp["plan"] is None:
      return "match", {}
    return ("match", {}) if same_plan(exp["plan"], ans["plan"]) else ("mismatch", {"why": "the plan"})
  if ek == "plan":
    if ak in ("plan", "yes") and same_plan(exp["plan"], ans["plan"]):
      return "match", {}
    return "mismatch", ({"answer_kind": ak} if ak not in ("plan", "yes") else {"why": "the plan"})
  if ek == "no_action":
    ok = ak == "no_action" or (ak == "yes" and ans["plan"] == [])
    return ("match", {}) if ok else ("mismatch", {"answer_kind": ak})
  if ek == "unknown" and ak == "no_plan":
    return "match", {"no_plan_for_unknown": True}
  if ek == "name":
    if ak == "name" and same_names(exp["names"], ans["names"]):
      return "match", {}
    return "mismatch", {"answer_kind": ak}
  return ("match", {}) if ek == ak else ("mismatch", {"answer_kind": ak})


def grade(expected, actions, answer, plan=None, mode="text", verbs=None):
  """{"correct", "grade", "detail"} of an answer.  With a list as `expected`, `actions` has one entry per
  alternative, and the best grade of the alternatives counts; `detail.alternative` names the one that gave it."""
  if mode not in MODES:
    raise ValueError("unknown check mode %r" % mode)
  if isinstance(expected, list):
    alternatives = expected
    lists = actions if isinstance(actions, list) and len(actions) == len(expected) else [None] * len(expected)
  else:
    alternatives, lists = [expected], [actions]
  ans = parse(answer)
  best = None
  for i, (value, acts) in enumerate(zip(alternatives, lists)):
    if ans["kind"] == "error":
      g, d = "error", {}
    elif mode == "text" or acts is None:
      g, d = text_grade(parse(value), ans)
      d = dict(d, by="text")
    else:
      ok = same_actions(plan, acts, verbs, parse(value)["plan"])
      if mode == "actions":
        g, d = ("match" if ok else "mismatch"), {"by": "actions"}
      else:
        g, d = text_grade(parse(value), ans)
        d = dict(d, by="both", text=g in CORRECT, actions=ok)
        if g in CORRECT and not ok:
          g = "mismatch"
    if len(alternatives) > 1:
      d["alternative"] = i
    if best is None or RANK.index(g) < RANK.index(best[0]):
      best = (g, d)
  return {"correct": best[0] in CORRECT, "grade": best[0], "detail": dict(best[1], mode=mode)}


def grade_row(row, answer, record=None, mode="text"):
  """The grade of an answer to a row [id, input, expected, actions]; `record` is the run's `action_route` record,
  whose result holds the plan (`plan_named`)."""
  actions = row[3] if len(row) > 3 else None
  result = (record or {}).get("result") or {}
  return grade(row[2], actions, answer, result.get("plan_named"), mode, result.get("plan_verbs"))


def check_row(row):
  """The structural errors of a row of the basic file: [] when it is [id, input, expected, actions] with a text or a
  list of texts, and an action list (or None) per text."""
  errs = []
  if not (isinstance(row, list) and len(row) == 4):
    return ["not [id, input, expected, actions]"]
  exp, acts = row[2], row[3]
  texts = exp if isinstance(exp, list) else [exp]
  if not all(isinstance(t, str) for t in texts):
    errs.append("an expected value that is no text")
  if isinstance(exp, list):
    if not (isinstance(acts, list) and len(acts) == len(exp)):
      errs.append("a list of alternatives needs one action entry per alternative")
    lists = acts if isinstance(acts, list) else []
  else:
    lists = [acts]
  for a in lists:
    if a is not None and not (isinstance(a, list) and all(isinstance(s, list) and s and isinstance(s[0], str)
                                                          for s in a)):
      errs.append("an action list that is no list of action terms: %r" % (a,))
  return errs
