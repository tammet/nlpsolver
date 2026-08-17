"""The critique pass: one LLM call that audits the front door's translation.

`-critic`.  When the front door ends Unknown after its own retries, one call
reads the English, the compacted Stage 1 and the Stage-2 logic, and reports
what is wrong with the translation.  On `RETRANSLATE` the pipeline runs Stage 2
(or Stage 1 and 2) once more with the findings appended as a corrective.  One
critique, one rerun, then stop.

Two separations hold throughout and the code enforces both:

  * the critic never sees an accepted answer;
  * the translator never sees the critic's own reading of the answer, its
    chain or its derivation — only the findings, so a rerun is a repair and
    not a dictated answer.
"""

import json
import os
import re

import critic_render as CR

VERSION = "critic_pass/2026-08-17"

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "prompts", "critic")
SYSTEM = os.path.join(PROMPT_DIR, "critic_system.txt")

MAX_TOKENS = 3000
MAX_FINDINGS = 6

READINGS = ("true", "false", "unknown")
VERDICTS = ("RETRANSLATE", "KEEP")
SEVERITIES = ("blocking", "note")
KINDS = ("quantifier", "direction", "negation_scope", "guard_unproducible",
         "shape_mismatch", "name_mismatch", "entity_split",
         "missing_participant", "dropped_condition", "modality", "definite",
         "question_form", "stage1_unit", "other")

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.M)
_WORDS = re.compile(r"[A-Za-z][A-Za-z'\-]+")


def system_prompt():
  with open(SYSTEM) as f:
    return f.read()


def prompt_sha256():
  import hashlib
  return hashlib.sha256(system_prompt().encode()).hexdigest()


def critique(text, s1_json, s2_json, llm=None, version=None, result=None,
             respond=None):
  """One critic call.  -> {report, raw, message, error}."""
  message = CR.critic_user_message(text, s1_json, s2_json, result)
  if respond is not None:
    raw, err = respond("critic", message)
  else:
    raw, err = _call(message, llm, version)
  out = {"message": message, "raw": raw, "error": err,
         "tokens_estimate": CR.token_estimate(message),
         "system_prompt_sha256": prompt_sha256()}
  if err or not raw:
    out["report"] = None
    out["parse_failure"] = "no reply"
    return out
  report = parse_reply(raw)
  out["report"] = report
  if report is None:
    out["parse_failure"] = "the reply is not the JSON the prompt asks for"
  return out


def _call(message, llm, version):
  import llmcall
  try:
    raw = llmcall.call_llm(system_prompt(), message, llm=llm, version=version,
                           max_tokens=MAX_TOKENS)
    return raw, None
  except Exception as e:                                       # noqa: BLE001
    return None, "%s: %s" % (type(e).__name__, e)


def parse_reply(raw, unit_texts=None):
  """-> the validated report, or None when the reply is not usable."""
  blob = _FENCE.sub("", str(raw or "")).strip()
  start = blob.find("{")
  if start > 0:
    blob = blob[start:]
  try:
    got = json.loads(blob)
  except ValueError:
    got = _repair(blob)
  if not isinstance(got, dict):
    return None
  reading = str(got.get("answer_by_reading") or "").strip().lower()
  verdict = str(got.get("verdict") or "").strip().upper()
  if reading not in READINGS or verdict not in VERDICTS:
    return None
  findings, dropped = [], []
  for row in (got.get("findings") or [])[:MAX_FINDINGS]:
    if not isinstance(row, dict):
      continue
    kind = str(row.get("kind") or "other").strip()
    severity = str(row.get("severity") or "note").strip().lower()
    units = [str(u) for u in (row.get("units") or []) if u]
    fix = str(row.get("fix") or "").strip()
    if kind not in KINDS or severity not in SEVERITIES or not units or not fix:
      dropped.append({"why": "malformed finding", "row": row})
      continue
    if unit_texts is not None and not _quotes_unit(fix, units, unit_texts):
      dropped.append({"why": "unquoted_fix", "units": units, "fix": fix})
      continue
    findings.append({"units": units, "kind": kind, "severity": severity,
                     "english": str(row.get("english") or "")[:400],
                     "logic": str(row.get("logic") or "")[:400],
                     "problem": str(row.get("problem") or "")[:600],
                     "fix": fix[:800]})
  out = {"answer_by_reading": reading, "verdict": verdict,
         "chain": [str(x) for x in (got.get("chain") or [])],
         "derivation": str(got.get("derivation") or "")[:1200],
         "findings": findings, "dropped_findings": dropped,
         "reason": str(got.get("reason") or "")[:400]}
  rt = got.get("retranslate")
  if isinstance(rt, dict):
    out["retranslate"] = {"stage": int(rt.get("stage") or 2),
                          "units": [str(u) for u in (rt.get("units") or [])]}
  return out


def _repair(blob):
  """The pipeline's own last resort for a nearly-JSON reply."""
  try:
    import utils
    if hasattr(utils, "repair_json"):
      return utils.repair_json(blob)
  except Exception:                                            # noqa: BLE001
    pass
  end = blob.rfind("}")
  if end > 0:
    try:
      return json.loads(blob[:end + 1])
    except ValueError:
      return None
  return None


def _quotes_unit(fix, units, unit_texts):
  """A fix must quote at least one word sequence of a unit's own text."""
  want = set()
  for uid in units:
    for word in _WORDS.findall(str(unit_texts.get(uid) or "")):
      if len(word) > 3:
        want.add(word.lower())
  if not want:
    return True
  said = set(w.lower() for w in _WORDS.findall(fix))
  return bool(want & said)


def decide(report):
  """-> (verdict, the units to redo, the stage).  KEEP unless it is earned."""
  if not report:
    return "KEEP", [], 2
  if report["verdict"] != "RETRANSLATE":
    return "KEEP", [], 2
  if report["answer_by_reading"] not in ("true", "false"):
    return "KEEP", [], 2
  chain = set(report.get("chain") or [])
  blocking = [f for f in report["findings"] if f["severity"] == "blocking"]
  on_chain = [f for f in blocking if (set(f["units"]) & chain)]
  if not on_chain:
    # the question unit counts as on the chain even when the chain omits it
    on_chain = [f for f in blocking if f["kind"] == "question_form"]
  if not on_chain:
    return "KEEP", [], 2
  units = []
  for f in on_chain:
    for u in f["units"]:
      if u not in units:
        units.append(u)
  stage = 1 if any(f["kind"] == "stage1_unit" for f in on_chain) else 2
  return "RETRANSLATE", units, stage


def corrective_suffix(findings):
  """What the translator is told: the findings, never the reading."""
  if not findings:
    return ""
  lines = ["A reviewer read your previous translation and found these "
           "problems. Produce the complete output again. Change only what "
           "the findings ask; keep every other unit as it was."]
  for f in findings:
    lines.append("- %s: %s" % (", ".join(f["units"]), f["fix"]))
  return "\n".join(lines)


def unit_texts(s1_json):
  """{unit id: its Stage-1 text}, for the quoted-fix check."""
  out = {}
  for block in (s1_json or []):
    if not isinstance(block, dict):
      continue
    for unit in (block.get("units") or []):
      if isinstance(unit, dict) and unit.get("unit_id"):
        out[unit["unit_id"]] = unit.get("text") or block.get("raw") or ""
  return out
