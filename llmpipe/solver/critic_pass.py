"""The critique pass: one LLM call that audits the initial attempt's translation.

`-critic`.  When the initial attempt ends Unknown after its own retries, one call
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
SYSTEM_V2 = os.path.join(PROMPT_DIR, "critic_system_v2.txt")

# The measurement runs two prompts over the same cases; the pipeline uses
# whatever `system_file` names.  Setting it is the only way to change prompt.
system_file = SYSTEM

MAX_TOKENS = 6000
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
  with open(system_file) as f:
    return f.read()


def use_prompt(which):
  """Select the critic's system prompt: "v1" or "v2".  -> the path used."""
  global system_file
  system_file = SYSTEM_V2 if str(which).lower() in ("v2", "2") else SYSTEM
  return system_file


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
                     "needs": str(row.get("needs") or "")[:400],
                     "produces": str(row.get("produces") or "")[:400],
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


# ======== the corrective ========

# A Stage-2 call is stateless.  Telling the translator to "keep every other
# unit as it was" is empty unless it can see what it wrote, so the corrective
# starts with the previous Stage-2 JSON.

_EMPTY_FIX = re.compile(
    r"\b(no change needed|no changes needed|no change required|"
    r"is fine|are fine|is correct as is|correct as is|is already correct|"
    r"leave as is|leave it as is|nothing to fix|no fix needed)\b", re.I)

_COMPACT = ("\u2200", "\u2203", "\u2227", "\u2228", "\u00ac", "\u2192")

LEGEND = ("The review writes logic in a compact notation.  It maps onto your "
          "JSON output like this: is_rel2(r, x, y) is [\"is rel2\", r, x, y]; "
          "has_degree_property(p, x, d, c) is [\"has degree property\", p, x, "
          "d, c]; has_type(E, v) is [\"has type\", E, v]; the other predicates "
          "likewise with spaces instead of underscores; \u2200X (A \u2192 B) is "
          "[\"forall\", \"X\", [\"implies\", A, B]]; \u2203X is [\"exists\", \"X\", "
          "...]; \u2227 is \"and\"; \u2228 is \"or\"; \u00ac is \"not\"; \"normally F\" is "
          "[\"normally\", F]; \"question(F)\" is [\"question\", F].")

INSTRUCTION = ("Produce the corrected complete answer in the same JSON "
               "format.  Keep every @id package the review does not mention "
               "exactly as it was.  Apply each fix inside the unit(s) it "
               "names; a rule the review asks you to add goes into the "
               "package of the first unit named, conjoined with what that "
               "package already states.  Return only the corrected JSON, "
               "with no additional commentary.")

INSTRUCTION_PACKAGES = ("Return only the corrected @id packages the review "
                        "names, as a JSON list: [[\"@id\", \"S4\", ...], "
                        "[\"@id\", \"S6\", ...]].  Every other package stays "
                        "as it was and must not be repeated.  No commentary.")


def _sorted(findings):
  """A stable order, so the same findings always build the same prompt."""
  def key(f):
    units = sorted(f.get("units") or [])
    head = units[0] if units else ""
    return (_unit_key(head), str(f.get("kind") or ""), str(f.get("fix") or ""))
  return sorted(findings or [], key=key)


def _unit_key(uid):
  m = re.match(r"^[Ss](\d+)$", str(uid or ""))
  return (0, int(m.group(1))) if m else (1, str(uid))


def drop_empty_fixes(findings):
  """-> (the findings that ask for a change, how many said "no change")."""
  kept, empty = [], 0
  for f in findings or []:
    if _EMPTY_FIX.search(str(f.get("fix") or "")):
      empty += 1
      continue
    kept.append(f)
  return kept, empty


def has_compact_fix(findings):
  """True when a fix is written in the critic's compact notation."""
  for f in findings or []:
    if any(ch in str(f.get("fix") or "") for ch in _COMPACT):
      return True
  return False


def build_corrective(findings, s2_json, legend=False, compact_lines=False,
                     findings_first=False, packages_only=False):
  """The corrective text.  The forms of the ladder differ only in these flags.

  legend         -- append the compact-notation legend (a fix that needs it)
  compact_lines  -- also show `logic`, `needs`, `produces` (compact notation)
  findings_first -- the findings before the previous answer, not after it
  packages_only  -- ask for the named packages alone, not the whole answer
  """
  findings = _sorted(findings)
  if not findings:
    return ""
  previous = ["Your previous answer was:",
              json.dumps(s2_json, indent=2, sort_keys=True, default=str)]
  head = ["A reviewer compared this answer with the sentences and found "
          "these problems:"]
  body = []
  for i, f in enumerate(findings, 1):
    body.append("%d. [%s] units %s"
                % (i, f.get("kind"), ", ".join(f.get("units") or [])))
    if f.get("english"):
      body.append("   words: %s" % f["english"])
    if compact_lines:
      for field in ("logic", "needs", "produces"):
        if f.get(field):
          body.append("   %s: %s"
                      % ("logic concerned" if field == "logic" else field,
                         f[field]))
    if f.get("problem"):
      body.append("   problem: %s" % f["problem"])
    body.append("   fix: %s" % (f.get("fix") or ""))
  tail = []
  if legend or (compact_lines and has_compact_fix(findings)):
    tail += ["", LEGEND]
  tail += ["", INSTRUCTION_PACKAGES if packages_only else INSTRUCTION, ""]
  if findings_first:
    lines = [""] + head + body + [""] + previous + tail
  else:
    lines = [""] + previous + [""] + head + body + tail
  return "\n".join(lines)


def corrective_suffix(findings, s2_json=None):
  """What the translator is told: its previous answer and the findings.

  Never the critic's reading: a rerun is a repair, not a dictated answer.
  The fixes arrive in the translator's own JSON list form (critic prompt v2
  §2); a fix that came back in the compact notation anyway brings the legend
  with it.
  """
  findings, _empty = drop_empty_fixes(findings)
  if not findings:
    return ""
  if s2_json is None:
    return corrective_v1(findings)
  return build_corrective(findings, s2_json,
                          legend=has_compact_fix(findings))


def corrective_v1(findings):
  """The first form, kept as the ladder's baseline: findings, no previous
  answer, no output instruction of its own."""
  if not findings:
    return ""
  lines = ["A reviewer read your previous translation and found these "
           "problems. Produce the complete output again. Change only what "
           "the findings ask; keep every other unit as it was."]
  for f in _sorted(findings):
    lines.append("- %s: %s" % (", ".join(f.get("units") or []),
                               f.get("fix") or ""))
  return "\n".join(lines)


def corrective_stage1(findings, s1_json):
  """For a `stage1_unit` finding: Stage 1 runs again, then Stage 2 plain.

  Stage 2 gets no corrective in this case — the rerun may renumber the units,
  so a finding that names S3 would point at a different sentence.
  """
  findings, _empty = drop_empty_fixes(findings)
  if not findings:
    return ""
  lines = ["", "Your previous answer was:",
           json.dumps(s1_json, indent=2, sort_keys=True, default=str), "",
           "A reviewer compared this answer with the sentences and found "
           "these problems:"]
  for i, f in enumerate(_sorted(findings), 1):
    lines.append("%d. units %s" % (i, ", ".join(f.get("units") or [])))
    if f.get("english"):
      lines.append("   words to restore: %s" % f["english"])
    if f.get("problem"):
      lines.append("   problem: %s" % f["problem"])
    lines.append("   fix: %s" % (f.get("fix") or ""))
  lines += ["",
            "Produce the corrected Stage-1 JSON.  Keep the unit ids and every "
            "unit the review does not mention exactly as they were.  Return "
            "only the JSON.", ""]
  return "\n".join(lines)


def splice_packages(previous, returned):
  """Form F3: put the packages the translator returned back into the answer.

  `returned` is a list of `["@id", "S4", ...]` packages, or a whole Stage-2
  tree the translator sent anyway.  -> the complete Stage 2, or None when
  nothing usable came back.
  """
  def packages(tree):
    if isinstance(tree, list) and tree and tree[0] == "and":
      return [x for x in tree[1:]
              if isinstance(x, list) and len(x) >= 3 and x[0] == "@id"]
    if isinstance(tree, list) and tree and tree[0] == "@id":
      return [tree]
    if isinstance(tree, list):
      return [x for x in tree
              if isinstance(x, list) and len(x) >= 3 and x[0] == "@id"]
    return []

  new = {str(p[1]): p for p in packages(returned)}
  if not new:
    return None
  old = packages(previous)
  if not old:
    return None
  out = ["and"]
  for p in old:
    out.append(new.get(str(p[1]), p))
  for uid, p in new.items():
    if uid not in [str(x[1]) for x in old]:
      out.append(p)
  return out


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
