"""The per-cited-rule grader for the literal bridge (`MODE`, below).

The bridge's failure mode is over-answering: on Core 100 it answered 9 cases
and got 0 right; on FOLIO its precision was 60%.  The graph route solved the
same problem with a per-bridge grader on every proof-cited bridge.  This is the
literal bridge's analogue.

The design follows what earlier experiments ruled out:

  * one call per rule, never a call about the set — a set-level assessor
    anti-correlated with answer agreement (AL-95);
  * the grader sees the passage and one rule, never the answer and never the
    question's polarity, so it cannot grade backwards from a conclusion;
  * a FAIL on any cited rule withdraws that proof, and a case whose proof is
    withdrawn keeps the initial attempt's answer.  No new rule search and no extra
    gk round follow a withdrawal.

Two evidence modes, mirroring `graph_procedure.EVIDENCE`:

  `stated`  the rule must restate the passage or be forced by it.  General
            world knowledge fails.  For FOLIO and the core sets, where the
            passage is the whole world.
  `any`     the rule must be true as general knowledge, whatever the passage
            says.  For EntailmentBank, whose rules are world knowledge.
"""

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
PROMPT_NAME = "litbridge_grader_v1_system"

VERSION = "litbridge_grader/2026-08-20"

# At most this many rules of one proof are graded.  A proof citing more is
# graded on its first four in citation order, and the record says so.
MAX_GRADED_RULES = 4

MODES = ("stated", "any")

# The grader is off at None.  "stated" asks whether the passage states or
# forces the rule; "any" asks whether it is true as general knowledge.
MODE = None

_EVIDENCE = {
    "stated": (
        "The rule must be a restatement of the passage's own sentences, or be "
        "forced by them. The passage is the whole world here: if the rule is "
        "true of the world but the passage does not state it or force it, it "
        "FAILS. A rule that connects two ways of saying one thing the passage "
        "does say PASSES."),
    "any": (
        "The rule must be true as ordinary general knowledge, whatever the "
        "passage says. The passage does not have to state it. A rule that is "
        "false in general FAILS even if this passage would let it through."),
}

_VERDICT = re.compile(r"^\s*VERDICT\s+([A-Za-z0-9_.:-]+)\s*:\s*(PASS|FAIL)\b",
                      re.I | re.M)
_BARE = re.compile(r"^\s*VERDICT\s*:?\s*(PASS|FAIL)\b", re.I | re.M)
_REASON = re.compile(r"^\s*REASON\s*:\s*(.+)$", re.I | re.M)


def system_prompt(mode="stated"):
  """The grader's system prompt with the mode's standard spliced in."""
  mode = normalise_mode(mode)
  with open(os.path.join(PROMPT_DIR, "%s.txt" % PROMPT_NAME)) as f:
    text = f.read()
  return text.replace("{EVIDENCE}", _EVIDENCE[mode])


def normalise_mode(mode):
  """`None` means `stated`; anything unknown means it too."""
  got = str(mode or "").strip().lower()
  return got if got in MODES else "stated"


def passage_only(text):
  """The input with every "?"-terminated sentence removed.

  The grader must not see the question: FOLIO writes its conclusion as a
  declarative ending in "?" ("Beethoven is not a conductor?"), and a grader
  that reads it as one more passage sentence fails a rule for contradicting
  the question's own polarity (gpt FOLIO 39, 2026-08-20).
  """
  out, buf = [], []
  for ch in str(text or ""):
    buf.append(ch)
    if ch in ".?!":
      seg = "".join(buf).strip()
      if seg and not seg.endswith("?"):
        out.append(seg)
      buf = []
  tail = "".join(buf).strip()
  if tail and not tail.endswith("?"):
    out.append(tail)
  return " ".join(out)


def request(passage, rule_id, printed, meaning=None):
  """The one-rule message.  The answer and the question never appear in it:
  the passage goes through `passage_only` here."""
  lines = ["PASSAGE", "", passage_only(passage), "",
           "THE RULE TO ASSESS", "",
           "    %s: %s" % (rule_id, printed)]
  if meaning:
    lines += ["", "    READS AS: %s" % meaning]
  lines += ["", "Assess this rule alone."]
  return "\n".join(lines)


def parse(reply, rule_id):
  """-> {"verdict": "PASS"|"FAIL", "reason": str, "parsed": bool}.

  An unreadable reply is a FAIL: the step exists to withhold answers that rest
  on unchecked rules, so a verdict nobody can read withholds too.
  """
  text = str(reply or "")
  verdict = None
  for got_id, got in _VERDICT.findall(text):
    if str(got_id).strip().lower() == str(rule_id).strip().lower():
      verdict = got.upper()
      break
  if verdict is None:
    found = _VERDICT.findall(text)
    if len(found) == 1:
      verdict = found[0][1].upper()
  if verdict is None:
    got = _BARE.search(text)
    if got:
      verdict = got.group(1).upper()
  reason = ""
  got = _REASON.search(text)
  if got:
    reason = got.group(1).strip()[:300]
  if verdict is None:
    return {"verdict": "FAIL", "reason": reason or "the reply carried no "
            "readable verdict", "parsed": False}
  return {"verdict": verdict, "reason": reason, "parsed": True}


def withdraws(grades):
  """Does this proof fall?  Any FAIL among the graded rules withdraws it."""
  return any(g.get("verdict") == "FAIL" for g in grades or [])


def to_grade(cited, rules_by_id, cap=MAX_GRADED_RULES):
  """-> [(rule_id, printed, meaning)] for the rules this proof cites.

  In citation order, capped.  A cited id with no recorded rule is skipped: it
  cannot be shown to a grader, and grading what is not shown is not grading.
  """
  out = []
  for rid in cited or []:
    row = (rules_by_id or {}).get(rid)
    if not row:
      continue
    out.append((rid, row.get("printed") or row.get("printed_formula") or "",
                row.get("meaning") or ""))
    if len(out) >= cap:
      break
  return out


def grade_proof(passage, cited, rules_by_id, ask, mode="stated",
                cap=MAX_GRADED_RULES):
  """Grade one proof's cited rules.  `ask(rule_id, message) -> reply text`.

  -> {"mode", "graded", "grades", "withdrawn", "cited", "over_cap"}.
  A proof citing no recorded rule is not graded and is not withdrawn: there is
  nothing invented holding it up.
  """
  mode = normalise_mode(mode)
  rows = to_grade(cited, rules_by_id, cap)
  grades = []
  for rid, printed, meaning in rows:
    reply = ask(rid, request(passage, rid, printed, meaning))
    got = parse(reply, rid)
    got.update({"rule_id": rid, "printed": printed})
    grades.append(got)
  return {"mode": mode, "graded": len(grades), "grades": grades,
          "withdrawn": withdraws(grades),
          "cited": list(cited or []),
          "over_cap": max(0, len(cited or []) - len(rows))}
