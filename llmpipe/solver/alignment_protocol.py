"""Critic / editor / verifier prompt construction and response parsing (WP4).

Plan: memos/PLAN_2026_08_09_dynamic_abstraction_alignment_pilot_opus5.md §10.

This module builds prompts and reads replies.  It does not call an LLM: the
caller supplies the response text, which in the current scope always comes from
a mock.  Keeping the transport out means the whole protocol is testable offline
and the live wiring is a later, separately approved change.

Three invariants the tests pin:

  * only the first line of a critic or verifier reply is interpreted; the prose
    is passed through untouched, and an unknown token is UNCERTAIN, never a
    guess;
  * no prompt may contain an expected answer, a benchmark label or a proof
    result — `assert_no_leak` enforces it on every built prompt;
  * cache identity is per role and per alternative, so an editor reply can never
    be served to a verifier, or one alternative's reply to another.
"""

import hashlib
import json
import os
import re

import alignment_diff as AD
import alignment_edit as AE
import alignment_occurrences as AO

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "prompts", "dynamic_alignment")

ROLES = ("critic", "editor", "verifier")

CRITIC_VERDICTS = ("KEEP", "REVISE", "CONNECT", "ALTERNATIVES", "UNCERTAIN")
VERIFIER_DECISIONS = ("ACCEPT", "REJECT", "UNCERTAIN")

MAX_ALTERNATIVES = 2

# Tokens that must never reach a model.  Answer words are the benchmark's
# expected values; the label vocabulary would tell the critic what to say.
LEAK_TOKENS = ("expected_answer", "accepted_llmpipe_answers", "$ans",
               "gold_replacement_packages", "critic_verdict", "label_id",
               "benchmark", "proof found", "answer found")
LEAK_ANSWER_WORDS = ("true.", "false.", "unknown.", "probably true.",
                     "probably false.", "possibly true.", "possibly false.")


class ProtocolError(Exception):
    pass


def load_prompt(role, version="v1"):
    if role not in ROLES:
        raise ProtocolError("unknown role %r" % role)
    p = os.path.join(PROMPT_DIR, "%s_%s.txt" % (role, version))
    with open(p) as f:
        return f.read()


def prompt_hash(role, version="v1"):
    return hashlib.sha256(load_prompt(role, version).encode()).hexdigest()


def assert_no_leak(text, extra_forbidden=()):
    """Raise if a built prompt carries an answer, a label or a proof result."""
    low = (text or "").lower()
    bad = [t for t in LEAK_TOKENS if t.lower() in low]
    for w in LEAK_ANSWER_WORDS:
        # an answer word only leaks when it stands alone as a value, which is
        # how the stored records write it
        if ('"%s"' % w) in low or ("answer: %s" % w) in low:
            bad.append(w)
    bad += [t for t in extra_forbidden if t and t.lower() in low]
    if bad:
        raise ProtocolError("prompt would leak: %s" % sorted(set(bad)))
    return True


# ------------------------------------------------------------------ critic

def _units_block(stage1):
    lines = []
    for sent in stage1 or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            lines.append("%s [%s] %s" % (u.get("unit_id"), u.get("type"),
                                         u.get("text")))
    return "\n".join(lines)


def _issue_block(issues):
    if not issues:
        return "(deterministic checks found nothing)"
    lines = []
    for i in issues:
        tag = {"hard_error": "PROBLEM", "candidate_hint": "LOOK AT",
               "diagnostic_probe": "STRUCTURE"}.get(
                   i.get("evaluation_category"), "NOTE")
        lines.append("%-9s %s" % (tag, i["summary"]))
    return "\n".join(lines)


def build_critic_prompt(fixture, detection, max_issues=12):
    """Input per §10.1: English, Stage-1 units, raw Stage 2, the compact
    comparison, and the deterministic issues."""
    table = detection["table"]
    issues = [i for i in detection["issues"]
              if i.get("evaluation_category") != "diagnostic_probe"][:max_issues]
    units = sorted(set(o["unit_id"] for o in table["stage2"]))
    views = "\n\n".join(AO.render_unit(table, u) for u in units)
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "STAGE 1 UNITS:\n%s" % _units_block(fixture["stage1"]),
        "STAGE 2 LOGIC (complete, raw):\n%s" % json.dumps(fixture["stage2"]),
        "HOW EACH SOURCE EXPRESSION WAS REPRESENTED:\n%s" % views,
        "WHAT DETERMINISTIC CHECKS FOUND:\n%s" % _issue_block(issues),
    ])
    prompt = load_prompt("critic") + "\n\n" + body
    assert_no_leak(prompt)
    return prompt


def parse_critic_response(text):
    """Only VERDICT is interpreted; the prose is passed on verbatim."""
    verdict, problem, request = "UNCERTAIN", "", ""
    alternatives = []
    section = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        up = line.upper()
        if up.startswith("VERDICT:"):
            token = line.split(":", 1)[1].strip().split()[0].upper() \
                if line.split(":", 1)[1].strip() else ""
            verdict = token if token in CRITIC_VERDICTS else "UNCERTAIN"
            section = None
        elif up.startswith("PROBLEM:"):
            problem = line.split(":", 1)[1].strip()
            section = "problem"
        elif up.startswith("EDIT REQUEST:"):
            request = line.split(":", 1)[1].strip()
            section = "request"
        elif section == "problem" and line:
            problem += "\n" + line
        elif section == "request" and line:
            request += "\n" + line
    if verdict == "ALTERNATIVES":
        for line in request.splitlines():
            s = line.strip()
            if s and s[0].isdigit():
                alternatives.append(s.lstrip("0123456789.) ").strip())
        alternatives = alternatives[:MAX_ALTERNATIVES]
    return {"critic_verdict": verdict, "critic_problem": problem.strip(),
            "critic_request": request.strip(), "alternatives": alternatives,
            "invokes_editor": verdict in ("REVISE", "CONNECT", "ALTERNATIVES")}


# ------------------------------------------------------------------ editor

CRITIC_KINDS = ("strict", "defeasible", "conditional", "translation repair",
                "none")


def build_selected_critic_prompt(fixture, selections, version="v1"):
    """Critic input when a selector has already picked candidate pairs.

    `selections` is a list of dicts with `id` and a rendered description of the
    pair.  The critic sees the English, the current Stage 2 and those picks —
    and nothing about which of them anybody thinks is right.
    """
    lines = []
    for s in selections:
        lines.append("%s: %s" % (s["id"], s["text"]))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "SENTENCES:\n%s" % _units_block(fixture["stage1"]),
        "CURRENT STAGE 2 (complete, raw):\n%s" % json.dumps(fixture["stage2"]),
        "PAIRS PICKED OUT OF THE LOGIC:\n%s"
        % ("\n".join(lines) or "(none were picked)"),
    ])
    with open(os.path.join(PROMPT_DIR, "critic_selected_%s.txt" % version)) as f:
        instr = f.read()
    prompt = instr + "\n\n" + body
    assert_no_leak(prompt)
    return prompt


def selected_critic_prompt_hash(version="v1"):
    with open(os.path.join(PROMPT_DIR, "critic_selected_%s.txt" % version)) as f:
        return hashlib.sha256(f.read().encode()).hexdigest()


def parse_selected_critic_response(text):
    """VERDICT, MISMATCH, ORDINARY, CONNECTION, KIND, EDIT REQUEST.

    Only VERDICT, the ids and KIND are interpreted; every prose field is kept
    verbatim for the editor and for the record.  An unknown verdict or kind is
    the uncertain value, never a guess.
    """
    fields = {"VERDICT": "", "MISMATCH": "", "ORDINARY": "", "CONNECTION": "",
              "KIND": "", "EDIT REQUEST": ""}
    order = ["VERDICT", "MISMATCH", "ORDINARY", "CONNECTION", "KIND",
             "EDIT REQUEST"]
    current = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        up = line.upper()
        hit = None
        for key in order:
            if up.startswith(key + ":"):
                hit = key
                break
        if hit:
            fields[hit] = line.split(":", 1)[1].strip()
            current = hit
        elif current and line:
            fields[current] += "\n" + line
    verdict = fields["VERDICT"].split()[0].upper() if fields["VERDICT"] else ""
    if verdict not in CRITIC_VERDICTS:
        verdict = "UNCERTAIN"
    kind = fields["KIND"].strip().lower()
    kind = kind if kind in CRITIC_KINDS else "none"
    ids = re.findall(r"\bK\d+\b", fields["MISMATCH"])
    ordinary = re.findall(r"\bK\d+\b", fields["ORDINARY"])
    return {
        "critic_verdict": verdict,
        "mismatch_ids": ids,
        "mismatch_says_none": not ids and "none" in fields["MISMATCH"].lower(),
        "ordinary_ids": ordinary,
        "connection": fields["CONNECTION"].strip(),
        "kind": kind,
        "critic_problem": fields["CONNECTION"].strip(),
        "critic_request": fields["EDIT REQUEST"].strip(),
        "invokes_editor": (verdict in ("REVISE", "CONNECT", "ALTERNATIVES")
                           and fields["EDIT REQUEST"].strip().lower()
                           not in ("", "none")),
        "parsed": bool(fields["VERDICT"]),
    }


def build_editor_prompt(fixture, critic, alternative=None):
    request = alternative if alternative is not None else critic["critic_request"]
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "STAGE 1 UNITS:\n%s" % _units_block(fixture["stage1"]),
        "CURRENT STAGE 2:\n%s" % json.dumps(fixture["stage2"]),
        "REVIEWER'S PROBLEM:\n%s" % critic["critic_problem"],
        "REVIEWER'S REQUEST:\n%s" % request,
    ])
    prompt = load_prompt("editor") + "\n\n" + body
    assert_no_leak(prompt)
    return prompt


def build_editor_repair_prompt(fixture, critic, bad_response, error,
                               alternative=None):
    """The single formatting-repair call (§9.1): the validation error and the
    original response only — no labels, no proof results."""
    body = "\n\n".join([
        "Your previous response was rejected: %s" % error,
        "Your previous response was:\n%s" % (bad_response or "")[:4000],
        "Return one JSON array of complete packages and nothing else.",
    ])
    prompt = build_editor_prompt(fixture, critic, alternative) + "\n\n" + body
    assert_no_leak(prompt)
    return prompt


def parse_editor_response(text):
    """-> (packages, error).  Never raises; the caller decides about a retry."""
    try:
        return AE.parse_editor_output(text), None
    except AE.EditError as e:
        return None, str(e)


MAX_FORMAT_RETRIES = 1


def run_editor(fixture, critic, respond, alternative=None,
               max_retries=MAX_FORMAT_RETRIES):
    """Editor call plus at most one formatting-repair call (§9.1).

    `respond(prompt, attempt)` supplies the reply text; in this scope it is
    always a mock.  The repair prompt carries the validation error and the
    previous response only.  After the cap the edit is abandoned — the loop
    never runs until something parses.
    """
    prompt = build_editor_prompt(fixture, critic, alternative)
    attempts = []
    for attempt in range(max_retries + 1):
        text = respond(prompt, attempt)
        pkgs, err = parse_editor_response(text)
        attempts.append({"attempt": attempt, "error": err,
                         "accepted": pkgs is not None})
        if pkgs is not None:
            return {"packages": pkgs, "attempts": attempts, "gave_up": False}
        if attempt == max_retries:
            break
        prompt = build_editor_repair_prompt(fixture, critic, text, err,
                                            alternative)
    return {"packages": None, "attempts": attempts, "gave_up": True}


# ------------------------------------------------------------------ verifier

def build_verifier_prompt(fixture, edited_stage2, changed, added, diff_record):
    before = dict(AO.packages(fixture["stage2"]))
    after = dict(AO.packages(edited_stage2))
    touched = sorted(set(changed) | set(added))
    src = []
    for sent in fixture["stage1"] or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            if u.get("unit_id") in touched:
                src.append("%s: %s" % (u["unit_id"], u.get("text")))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "SOURCE SENTENCES THE EDIT TOUCHES:\n%s"
        % ("\n".join(src) or "(the edit only adds a new rule)"),
        "PACKAGES BEFORE:\n%s"
        % json.dumps([[p, before[p]] for p in touched if p in before]),
        "PACKAGES AFTER:\n%s"
        % json.dumps([[p, after[p]] for p in touched if p in after]),
        "WHAT CHANGED:\n%s" % AD.render(diff_record),
    ])
    prompt = load_prompt("verifier") + "\n\n" + body
    assert_no_leak(prompt)
    return prompt


def parse_verifier_response(text):
    """First recognised token decides; anything else is UNCERTAIN."""
    lines = [l.strip() for l in (text or "").splitlines() if l.strip()]
    decision, reason = "UNCERTAIN", ""
    if lines:
        first = lines[0].upper().strip(".:")
        for d in VERIFIER_DECISIONS:
            if first == d or first.startswith(d):
                decision = d
                break
        reason = " ".join(lines[1:]).strip()
    return {"verifier_decision": decision, "verifier_reason": reason,
            "accepted": decision == "ACCEPT"}


# --------------------------------------------------- component-wise CONNECT

CONNECT_COMPONENTS = ("connection", "direction", "arguments", "conditions",
                      "strength")
_YES_NO = {"yes": "yes", "y": "yes", "no": "no", "n": "no",
           "unclear": "unclear", "unknown": "unclear"}
_CONDITION_VALUES = {"ok": "ok", "fine": "ok", "complete": "ok",
                     "missing": "missing", "extra": "extra",
                     "unclear": "unclear"}


def _first_word(raw):
    t = (raw or "").strip().lower()
    return t.split(" ")[0].strip(".,;:!?()[]\"'") if t else ""


def _strength_value(raw):
    t = " ".join(raw.lower().split()).strip(".")
    if t in ("ok", "fine", "correct", "as printed"):
        return "ok"
    if "default" in t:
        return "should_be_default"
    if "strict" in t:
        return "should_be_strict"
    return "unclear"


def parse_connect_verifier_response(text):
    """The five components, the verdict, and whether they agree with each other.

    One judgement per component, so a rule can fail on conditions while its
    direction is credited.  The agreement check is computed here, not asked of
    the model: chain v2 produced an UNCERTAIN whose stated reason argued for the
    rule, and that inconsistency was only visible by reading the prose.
    """
    fields = {}
    wanted = set(CONNECT_COMPONENTS) | {"verdict", "why", "correction"}
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        # the field names come back decorated often enough that reading only
        # bare `NAME:` lines lost every field of a whole response
        k = k.strip().strip("*#_-• \t").lower().strip()
        if k not in wanted or k in fields:
            continue
        fields[k] = v.strip().strip("*_ ").strip()
    out = {"connection": _YES_NO.get(_first_word(fields.get("connection")),
                                     "unclear"),
           "direction": _YES_NO.get(_first_word(fields.get("direction")),
                                    "unclear"),
           "arguments": _YES_NO.get(_first_word(fields.get("arguments")),
                                    "unclear"),
           "conditions": _CONDITION_VALUES.get(
               _first_word(fields.get("conditions")), "unclear"),
           "strength": _strength_value(fields.get("strength", "")),
           "why": fields.get("why", ""),
           "correction": fields.get("correction", ""),
           "fields_present": sorted(fields)}
    verdict = "UNCERTAIN"
    raw = fields.get("verdict", "").strip().upper()
    for d in VERIFIER_DECISIONS:
        if raw.startswith(d):
            verdict = d
            break
    out["verifier_decision"] = verdict
    out["verdict_line_present"] = bool(raw)
    out["accepted"] = verdict == "ACCEPT"
    faults = [k for k in CONNECT_COMPONENTS
              if out[k] in ("no", "missing", "extra", "should_be_default",
                            "should_be_strict")]
    out["faulted_components"] = faults
    out["all_components_clean"] = not faults and not any(
        out[k] == "unclear" for k in CONNECT_COMPONENTS)
    # ACCEPT while naming a fault, or REJECT while naming none, is a response
    # that contradicts itself; recorded rather than silently resolved
    out["verdict_agrees_with_components"] = bool(
        (verdict == "ACCEPT" and not faults)
        or (verdict in ("REJECT", "UNCERTAIN") and faults))
    return out


# ------------------------------------------------------------------ caching

def cache_key(role, case_id, prompt, version="v1", alternative=None):
    """Distinct per role, per case, per prompt version, per alternative.

    Two roles that happened to be given the same text must not share a cached
    reply, so the role is part of the key rather than only the content.
    """
    if role not in ROLES:
        raise ProtocolError("unknown role %r" % role)
    h = hashlib.sha256()
    for part in (role, version, case_id or "",
                 "alt%s" % ("-" if alternative is None else alternative),
                 prompt or ""):
        h.update(part.encode())
        h.update(b"\x00")
    return "%s:%s:%s" % (role, version, h.hexdigest()[:32])
