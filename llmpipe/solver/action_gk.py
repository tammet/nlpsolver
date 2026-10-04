"""Action route: the GK adapter.  It runs the obligations of one compiled query and extracts typed evidence.

  run_query(source_artifact, query_artifact, backend=None, limits=None, ledger=None) -> evidence record
  extract(stdout, ...)                                                             -> the answers of one launch
  check_prerequisites(backend=None, ledger=None)                                   -> the build's blocker regressions
                                                                                      (run by hand to re-validate
                                                                                      a GK build)

The adapter decides no answer.  It gives the answer policy (`action_answer`) every accepted
answer and every rejected entry of every launch, separately, with the proofs,
the final confidences and the result strings.  Yes, No, Unknown, contested and
the plan outcomes are the policy's decisions.

Backend.  A backend is a registered GK build: a path, the strategy, the
command parameters and the capabilities validated for it.  A caller names a
build of `BACKENDS`; the registry is the trust boundary, and the adapter runs
no other binary.  Like the ordinary pipeline, the adapter does not check which
build is at the path: it records the SHA-256 of the binary it runs, and a
capability counts only for the binary that its validation record names.  A
missing binary, one without execute permission, or a missing data folder gives
the typed outcome `backend_unavailable` before any launch; a launch that cannot
start gives it too (`launch_failed`).  A launch whose output says that the build
ignored a strategy setting gives `backend_incompatible`: the build did not
run the registered strategy.  The command is built from the profile only: the
ordinary pipeline's options, strategy estimation, axiom files and proof cache
are not read.

Requirements.  Before any launch, each backend requirement the query artifact
records is checked against the capabilities validated for the build, the
source's library identity and the strategy.  The caller's own `backend`
declaration in `compile_query` does not count.  An unmet requirement whose
policy is `refuse` (negative persistence) gives
`unsupported_backend_requirement` before any launch, unless only the
negative polarity needs it (`polarities` ["negative"]): then the query runs,
and the answer policy keeps a Yes and refuses every other answer.  An unmet
requirement whose policy is `experimental` (shared-source confidence) lets
the query run.  The confidence of every candidate whose proof uses a clause
of a listed unit is then labelled experimental.

Obligations.  A snapshot or verify obligation runs its positive and its
negative question as two launches.  An ask and a discovery run the positive
question only.  A verify query with steps also runs its joint positive
question.  Every launch is counted under its role (`step:negative`,
`joint:positive`, ...), and so is every termination relaunch.

Eligibility.  Only an entry of GK's `answers` list can be a candidate.  An
entry of `rejected_answers` is a diagnostic, whatever its confidence and
whatever the `result` string says.  An accepted entry is eligible when:

  its launch completed with output that agrees with itself;
  its confidence is a finite number in [0, 1] and at least 0.10;
  it is a verdict for the question asked, not a contrary verdict (`false`);
  it is one answer, not a disjunction of `$ans` literals;
  the reported variables are ground;
  a discovery answer is a situation term rooted at the query's planning root,
  built from the five constructors with their arities.

Canonical candidates.  A question without reported variables is a Boolean: GK's
`$ans` then holds only internal context variables, and every accepted entry is
the same logical answer.  A question with reported variables gives one
candidate per distinct binding, after variables are renamed in order of
appearance.  Distinct witnesses and distinct action histories stay distinct.
A candidate keeps the indexes of its raw entries and every confidence; its
`confidence` is the largest, and `confidence_entry` names the entry that
supplies it.

Experimental confidence.  Each accepted entry has a status.  A candidate's
confidence takes the status of the entry that supplies it: `validated` when
one of the entries at the largest confidence is validated, else
`experimental` with the reasons of those entries.  An entry's confidence is
`validated` unless one of these holds for its proof:

  uncertain_evidence_reused       its proof uses two or more clauses of one uncertain source unit, or one such
                                  clause more than once (the c30 `overlap` guard; no provenance check exists yet)
  shared_source_confidence_unmet  the query records the requirement, the backend does not validate it, and the
                                  proof uses a clause of a listed unit (C29.Q2)
  provenance_unchecked            the entry has no proof steps to check

A use count is the number of times a proof step is reached from the final step
when the proof is read as a tree.

Termination.  Every launch record has a termination reason: `proof` (an
accepted entry exists), `timeout` (the external limit), `error`, or, after one
relaunch with `-printlevel 12`, `search_limit` or `undetermined`.
`search_limit` is inconclusive.  The relaunch never replaces the launch's
answers: a relaunch that fails is `diagnostic_error`, and one that finds an
answer the launch did not is `diagnostic_differs`.

No model call.  The adapter writes no cache and no file outside a temporary
directory, unless the caller names a directory to keep the inputs and outputs.
"""

import contextlib
import copy
import fcntl
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time

import action_route as ar
from digests import sha256_file, sha256_text
import lc_action as la
import lc_action_query as lq
import lc_action_situate as sit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # llmpipe/
EVIDENCE = "action_evidence"
EVIDENCE_VERSION = "1"
CUTOFF = 0.10
EXTRA = 15                  # the external margin over -seconds, in seconds
DEFAULT_SECONDS = 30
STAGE = "actions"           # the stage name of the route's GK calls in a run collector
FLAGS = ("-nonegative",)    # the only extra flag; a run with it gives candidates only
PRINTLEVEL = 12

# the planning strategy: query focus; a $ctxt term and a blocker literal of a rule weigh one constant
PLANNING_STRATEGY = {"strategy": ["query_focus"], "query_preference": 1, "equality": 0,
       "weight_select_ratio": 20, "weight_blocker_const": 2, "weight_ctxt_const": 1}
PIPELINE_PARAMS = ["-taxonomy", "-confidence", "0.1", "-keepconfidence", "0.1"]
DATAFOLDER = os.path.join(os.path.dirname(ROOT), "gk")

RESULTS = ("answer found", "evidence below limit", "no answers found", "no information",
           "time limit, proof not found")
NO_ANSWER_RESULTS = ("no answers found", "no information", "time limit, proof not found")
INCOMPATIBLE = "unknown setting in the strategy"

BACKENDS = {
  # the installed prover, gk 1.0.11 (the binary of the gkreasoner release), with the planning strategy
  "gk": {
    "name": "gk",
    "path": os.path.join(DATAFOLDER, "gk"),
    "status": "installed",
    "strategy": PLANNING_STRATEGY,
    "params": PIPELINE_PARAMS,
    "datafolder": DATAFOLDER,
    # capability records: {"capability", "binary_sha256", "library", "strategy_sha256", "evidence"}
    "validated": [],
    "unmet": {
      lq.NEGATIVE_PERSISTENCE: {
        "reason": "negative_persistence_unavailable", "policy": "refuse",
        "evidence": "an unrelated action drops a negative fact: the build has no negative frame"},
      lq.SHARED_CONFIDENCE: {
        "reason": "evidence_counted_twice_per_application", "policy": "experimental",
        "evidence": "fixture c29, query Q2: 0.1296 where the counting rule gives 0.36"},
    },
    "known_failures": [
      {"row": "M29.neg", "reason": "frame_blocker_under_hypothesis",
       "detail": "a wrong accepted negative answer on a conditional effect with frame reasoning"},
      {"row": "C29.Q2", "reason": "evidence_counted_twice_per_application", "detail": "a wrong plan confidence"}],
    "prerequisites": {
      "folder": "/opt/gk/experiments/regression/defworlds/blocker_checks", "seconds": 10,
      "expect": {"cyclic_small": "Yes", "cyclic_small_control": "contested", "astra_ground6": "Yes",
                 "discarded_pb": "Yes"},
      "evidence": "the four regressions give their expected answers on this binary"},
  },
}
DEFAULT_BACKEND = "gk"


class AdapterError(Exception):
  """A caller error: an unknown backend, a bad limit, an unknown flag."""


# ---------------------------------------------------------------------------
# backend profile


def strategy_sha256(strategy):
  # ASCII-escaped JSON, unlike `digests.canonical`: the recorded strategy hashes read this form
  return sha256_text(json.dumps(strategy, sort_keys=True, separators=(",", ":")))


def binary_sha256(path):
  """The SHA-256 of the binary at `path`, or None when there is no file."""
  return sha256_file(path) if os.path.isfile(path) else None


def backend_profile(backend=None):
  """A copy of a registered profile, by name, with `sha256` the hash of the binary now at its path.  Only a name of
  `BACKENDS` is accepted: the registry is the trust boundary.  Code that adds an entry to it (the tests do, for fake
  executables) is trusted like this module."""
  if backend is None:
    backend = DEFAULT_BACKEND
  if not isinstance(backend, str) or backend not in BACKENDS:
    raise AdapterError("backend is the name of a registered build, got %r; registered: %s"
                       % (backend if isinstance(backend, str) else type(backend).__name__, ", ".join(sorted(BACKENDS))))
  p = BACKENDS[backend]
  missing = [k for k in ("name", "path", "strategy", "params", "datafolder", "validated", "unmet") if k not in p]
  if missing:
    raise AdapterError("the registered backend %r lacks %s" % (backend, missing))
  p = copy.deepcopy(p)
  p["sha256"] = binary_sha256(p["path"])
  return p


def backend_identity(profile, library=None):
  """What an evidence record says about the backend it used."""
  return {"name": profile["name"], "path": profile["path"], "sha256": profile["sha256"],
          "status": profile.get("status"), "strategy": copy.deepcopy(profile["strategy"]),
          "strategy_sha256": strategy_sha256(profile["strategy"]), "params": list(profile["params"]),
          "library": copy.deepcopy(library)}


def availability(profile):
  """None when the registered binary is present and executable and its data folder exists; else the
  `backend_unavailable` outcome."""
  path = profile["path"]
  if not os.path.isfile(path):
    return {"outcome": "backend_unavailable", "reason": "binary_missing", "backend": profile["name"], "path": path,
            "detail": "the registered binary is not at its path; the adapter runs no other binary"}
  if not os.access(path, os.X_OK):
    return {"outcome": "backend_unavailable", "reason": "binary_not_executable", "backend": profile["name"],
            "path": path, "detail": "the registered binary may not be executed"}
  if not os.path.isdir(profile["datafolder"]):
    return {"outcome": "backend_unavailable", "reason": "datafolder_missing", "backend": profile["name"],
            "path": profile["datafolder"], "detail": "the build's data folder is not present"}
  return None


def capability(profile, name, library):
  """{"capability", "validated", "reason", "policy", "evidence"} for this build, library identity and strategy."""
  want = strategy_sha256(profile["strategy"])
  for v in profile["validated"]:
    if v["capability"] == name and v["binary_sha256"] == profile["sha256"] and v["library"] == library \
       and v["strategy_sha256"] == want:
      return {"capability": name, "validated": True, "reason": None, "policy": None, "evidence": v.get("evidence")}
  u = profile["unmet"].get(name) or {"reason": "capability_not_validated", "policy": "refuse",
                                     "evidence": "no validation record for this build"}
  return {"capability": name, "validated": False, "reason": u["reason"], "policy": u["policy"],
          "evidence": u.get("evidence")}


def requirements(query_artifact, profile, library):
  """The recorded requirements of the query, each checked against the backend."""
  out = []
  for n in query_artifact.get("backend_requirements") or []:
    c = capability(profile, n["capability"], library)
    c["units"] = list(n.get("units") or [])
    c["detail"] = n.get("detail")
    if n.get("polarities"):
      c["polarities"] = list(n["polarities"])
    out.append(c)
  return out


# ---------------------------------------------------------------------------
# limits and the command


def normalize_limits(limits):
  """{"seconds": N or {role: N, "default": N}, "max_launches": N or None, "termination": bool, "flags": [...],
  "keep": directory or None}."""
  limits = dict(limits or {})
  bad = set(limits) - {"seconds", "max_launches", "termination", "flags", "keep"}
  if bad:
    raise AdapterError("unknown limits %s" % sorted(bad))
  secs = limits.get("seconds", DEFAULT_SECONDS)
  vals = list(secs.values()) if isinstance(secs, dict) else [secs]
  if not all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in vals):
    raise AdapterError("seconds is a positive integer or {role: positive integer}")
  cap = limits.get("max_launches")
  if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 0):
    raise AdapterError("max_launches is a non-negative integer or None")
  flags = list(limits.get("flags") or [])
  if set(flags) - set(FLAGS):
    raise AdapterError("unknown flags %s; the adapter accepts %s" % (sorted(set(flags) - set(FLAGS)), list(FLAGS)))
  return {"seconds": secs, "max_launches": cap, "termination": bool(limits.get("termination", True)),
          "flags": flags, "keep": limits.get("keep")}


def seconds_for(limits, role):
  s = limits["seconds"]
  if isinstance(s, dict):
    return s.get(role, s.get("default", DEFAULT_SECONDS))
  return s


def command(profile, input_path, seconds, flags=(), printlevel=None):
  """The GK command of one launch: the registered binary, strategy and parameters, nothing else."""
  cmd = [profile["path"], "-strategytext", json.dumps(profile["strategy"]), "-seconds", str(seconds), input_path] \
    + list(profile["params"]) + list(flags) + ["-datafolder", profile["datafolder"], "-detail", "-outformat", "json"]
  if printlevel is not None:
    cmd += ["-printlevel", str(printlevel)]
  return cmd


def input_text(objs):
  """The input file bytes: json.dump with indent 0, one element per line."""
  return json.dumps(objs, indent=0)


# ---------------------------------------------------------------------------
# one launch


def _execute(cmd, cwd, timeout):
  """(stdout, stderr, exit code, timed out, elapsed, launch error).  A process that cannot start (no execute
  permission, a missing working folder) gives its OSError text as the launch error, never an exception."""
  t0 = time.time()
  failed = None
  try:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout)
    out, err, code, timed_out = p.stdout, p.stderr, p.returncode, False
  except subprocess.TimeoutExpired as e:
    out, err, code, timed_out = e.stdout or b"", e.stderr or b"", None, True
  except OSError as e:
    out, err, code, timed_out, failed = b"", b"", None, False, "%s: %s" % (type(e).__name__, e)
  dec = lambda b: b.decode("utf-8", "replace") if isinstance(b, bytes) else (b or "")
  return dec(out), dec(err), code, timed_out, round(time.time() - t0, 3), failed


def _count(ledger, role, profile, elapsed, clauses):
  """One GK call in a run collector, in the shape `prover.call_prover` records, plus the role and the binary."""
  if ledger is None:
    return
  ledger.setdefault("gk_calls", []).append({"seconds": elapsed, "input_clauses": clauses, "stage": STAGE,
                                            "inner_stage": None, "role": role, "backend": profile["name"],
                                            "binary_sha256": profile["sha256"]})


# The action route runs one GK process at a time on this machine, also when a runner's provider processes
# answer cases in parallel and the route is chosen per text.  A launch waits for this lock; its elapsed time starts
# after the wait.
SERIAL_LOCK = os.path.join(tempfile.gettempdir(), "llmpipe_action_gk.lock")


@contextlib.contextmanager
def _serial():
  with open(SERIAL_LOCK, "a") as f:
    fcntl.flock(f, fcntl.LOCK_EX)
    try:
      yield
    finally:
      fcntl.flock(f, fcntl.LOCK_UN)


# The open recordings of `recording()`: lists that receive every launch's input text, command and raw output.  The
# output levels of the route read them; the evidence records never hold the raw text.
_RECORDINGS = []


@contextlib.contextmanager
def recording():
  """Collect the full text of every launch in this block: [{"label", "role", "command", "input", "stdout", "stderr",
  "elapsed", "relaunch"}], in launch order.  `command` has "<input>" where the input file's path stands."""
  got = []
  _RECORDINGS.append(got)
  try:
    yield got
  finally:
    _RECORDINGS.remove(got)


def _record_launch(entry):
  for got in _RECORDINGS:
    got.append(entry)


def launch(profile, objs, seconds, role, flags=(), termination=True, ledger=None, keep=None, label=None):
  """Run GK once on `objs` (and once more for the termination reason when no answer is accepted).

  Returns the raw launch record: command, hashes, elapsed time, exit status, stdout, stderr and, when a relaunch
  ran, its termination lines.  Extraction is `extract`.  With `keep`, the input, output and error text are saved
  under `keep` as LABEL.input.json, LABEL.out and LABEL.err, and a relaunch's as LABEL.relaunch.out and .err.
  """
  text = input_text(objs)
  clauses = sum(1 for o in objs if isinstance(o, dict))
  tmp = tempfile.mkdtemp(prefix="action_gk_")
  try:
    path = os.path.join(tmp, "input.json")
    with open(path, "w") as f:
      f.write(text)
    cmd = command(profile, path, seconds, flags)
    with _serial():
      out, err, code, timed_out, elapsed, failed = _execute(cmd, profile["datafolder"], seconds + EXTRA)
    _count(ledger, role, profile, elapsed, clauses)
    rec = {"role": role, "command": [x if x != path else "<input>" for x in cmd], "seconds": seconds,
           "external_timeout": seconds + EXTRA, "input_sha256": sha256_text(text),
           "clauses": clauses, "binary_sha256": profile["sha256"], "elapsed": elapsed, "exit": code,
           "timed_out": timed_out, "launch_error": failed, "stdout": out, "stderr": err, "relaunch": None}
    parsed = parse_output(out, err, code, timed_out, failed)
    out2 = err2 = None
    if termination and parsed["status"] == "completed" and not parsed["answers"]:
      cmd2 = command(profile, path, seconds, flags, printlevel=PRINTLEVEL)
      with _serial():
        out2, err2, code2, timed2, elapsed2, failed2 = _execute(cmd2, profile["datafolder"], seconds + EXTRA)
      _count(ledger, "termination", profile, elapsed2, clauses)
      rec["relaunch"] = relaunch_record(out2, err2, code2, timed2, failed2)
      rec["relaunch"].update(command=[x if x != path else "<input>" for x in cmd2], elapsed=elapsed2)
    if _RECORDINGS:
      _record_launch({"label": label or role, "role": role, "command": rec["command"], "input": text, "stdout": out,
                      "stderr": err, "elapsed": elapsed,
                      "relaunch": None if rec["relaunch"] is None else dict(rec["relaunch"], stdout=out2 or "")})
    if keep:
      os.makedirs(keep, exist_ok=True)
      base = os.path.join(keep, (label or role).replace(":", "_"))
      with open(base + ".input.json", "w") as f:
        f.write(text)
      with open(base + ".out", "w") as f:
        f.write(out)
      with open(base + ".err", "w") as f:
        f.write(err)
      if rec["relaunch"] is not None:
        # the termination relaunch reads the same input; its raw output is kept beside the launch's
        with open(base + ".relaunch.out", "w") as f:
          f.write(out2 or "")
        with open(base + ".relaunch.err", "w") as f:
          f.write(err2 or "")
    return rec
  finally:
    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# reading GK output

RESULT_START = re.compile(r'^\s*\{\s*"(result|error)"')


def relaunch_record(stdout, stderr, exit_code, timed_out, launch_error=None):
  """The diagnostic relaunch: its termination lines, its own status and result, never an answer of the launch."""
  p = parse_output(stdout, stderr, exit_code, timed_out, launch_error)
  lines = [x.strip() for x in (stdout or "").split("\n")
           if "nothing proved" in x or "search terminated" in x or "search finished" in x]
  return {"exit": exit_code, "timed_out": timed_out, "launch_error": launch_error, "status": p["status"],
          "error": p["error"], "result": p["result"], "accepted": len(p["answers"]), "lines": lines[:5]}


def parse_output(stdout, stderr="", exit_code=0, timed_out=False, launch_error=None):
  """The status of one output and its two raw answer lists.

  status: completed | launch_failed | prover_timeout | prover_error | backend_incompatible | malformed.  Only a
  completed output has answers.  The result object starts at the first line that opens with {"result" or
  {"error" (a -printlevel output prints search lines first), else at the first line that opens with {.
  """
  out = {"status": "completed", "result": None, "answers": [], "rejected": [], "warnings": [], "error": None}
  if launch_error:
    out.update(status="launch_failed", error=launch_error)
    return out
  if timed_out:
    out.update(status="prover_timeout", error="the external time limit expired")
    return out
  lines = (stdout or "").split("\n")
  start = next((i for i, x in enumerate(lines) if RESULT_START.match(x)), None)
  if start is None:
    start = next((i for i, x in enumerate(lines) if x.lstrip().startswith("{")), None)
  out["warnings"] = [x.strip() for x in lines[:start if start is not None else len(lines)] if x.strip()]
  if any(INCOMPATIBLE in x for x in out["warnings"]):
    out.update(status="backend_incompatible",
               error="the build ignored a strategy setting: %s" % "; ".join(out["warnings"][:3]))
    return out
  if start is None:
    out.update(status="malformed" if exit_code == 0 else "prover_error",
               error="no JSON result in the output (exit %r): %s" % (exit_code, (stdout or stderr or "")[:300]))
    return out
  try:
    d = json.loads("\n".join(lines[start:]))
  except ValueError as e:
    out.update(status="malformed", error="the output is not JSON: %s" % e)
    return out
  if isinstance(d, dict) and "error" in d:
    out.update(status="prover_error", error=str(d["error"]))
    return out
  if exit_code not in (0, None):
    out.update(status="prover_error", error="exit %r with a result object" % exit_code)
    return out
  if not isinstance(d, dict) or not isinstance(d.get("result"), str):
    out.update(status="malformed", error="the result object has no result string")
    return out
  acc, rej = d.get("answers", []), d.get("rejected_answers", [])
  if not (isinstance(acc, list) and isinstance(rej, list) and all(isinstance(a, dict) for a in acc + rej)):
    out.update(status="malformed", error="answers and rejected_answers are lists of objects")
    return out
  out["result"], out["answers"], out["rejected"] = d["result"], acc, rej
  if d["result"] not in RESULTS:
    out.update(status="malformed", error="unknown result string %r" % d["result"])
  elif d["result"] in NO_ANSWER_RESULTS and acc:
    out.update(status="malformed", error="result %r with %d accepted answers" % (d["result"], len(acc)))
  elif d["result"] == "answer found" and not acc and not rej:
    out.update(status="malformed", error="result 'answer found' with no answer entry")
  return out


def proof_steps(proof):
  return [s for s in proof if isinstance(s, list) and len(s) >= 3] if isinstance(proof, list) else []


def proof_sources(proof):
  """The input clause names of a proof, in order: the `in` steps."""
  return [s[1][1] for s in proof_steps(proof) if isinstance(s[1], list) and len(s[1]) > 1 and s[1][0] == "in"]


def _parents(meta):
  out = []
  for x in meta[1:]:
    if isinstance(x, str):
      break
    if isinstance(x, int) and not isinstance(x, bool):
      out.append(x)
    elif isinstance(x, list) and x and isinstance(x[0], int):
      out.append(x[0])
  return out


def use_counts(proof):
  """{step number: the times the step is reached from the final step, reading the proof as a tree}."""
  steps = proof_steps(proof)
  if not steps:
    return {}
  parents = {s[0]: (_parents(s[1]) if isinstance(s[1], list) and s[1] and s[1][0] != "in" else []) for s in steps}
  uses = {n: 0 for n in parents}
  uses[steps[-1][0]] = 1
  for n in sorted(parents, reverse=True):          # a parent has a smaller number than its child
    for p in parents[n]:
      if p in uses:
        uses[p] += uses[n]
  return uses


def _uncertain(name, meta_conf, names):
  """(units, confidence) of an uncertain source clause, or None.  `names` maps clause names to view records."""
  rec = (names or {}).get(name)
  if rec is not None:
    conf = rec.get("confidence")
    if conf is None or conf >= 1:
      return None
    units = [rec["unit"]] if rec.get("unit") else list(rec.get("units") or [])
    return units, conf
  if not (isinstance(name, str) and name.startswith("src:")) or not isinstance(meta_conf, (int, float)) or meta_conf >= 1:
    return None
  return name.split(":")[1].split("+"), meta_conf


def evidence_reuse(proof, names=None):
  """[{unit, clauses: {name: uses}}] of the uncertain source units a proof uses twice or through two clauses."""
  uses = use_counts(proof)
  per = {}
  for s in proof_steps(proof):
    meta = s[1]
    if not (isinstance(meta, list) and len(meta) > 1 and meta[0] == "in"):
      continue
    u = _uncertain(meta[1], meta[3] if len(meta) > 3 else None, names)
    if u is None:
      continue
    for unit in u[0]:
      c = per.setdefault(unit, {})
      c[meta[1]] = c.get(meta[1], 0) + uses.get(s[0], 0)
  return [{"unit": unit, "clauses": per[unit]} for unit in sorted(per)
          if len([n for n in per[unit] if per[unit][n]]) >= 2 or any(v >= 2 for v in per[unit].values())]


def proof_units(proof, names=None):
  """The source units whose uncertain clauses a proof uses."""
  out = set()
  for s in proof_steps(proof):
    meta = s[1]
    if isinstance(meta, list) and len(meta) > 1 and meta[0] == "in":
      u = _uncertain(meta[1], meta[3] if len(meta) > 3 else None, names)
      if u:
        out.update(u[0])
  return sorted(out)


# ---------------------------------------------------------------------------
# answers, terms and candidates


def _variables(t, out):
  if isinstance(t, str):
    if t.startswith("?:") and t not in out:
      out.append(t)
  elif isinstance(t, list):
    for x in t:
      _variables(x, out)
  return out


def canonical_term(t):
  """`t` with its variables renamed ?:_1, ?:_2, ... in order of first appearance."""
  names = {v: "?:_%d" % (i + 1) for i, v in enumerate(_variables(t, []))}

  def walk(x):
    if isinstance(x, list):
      return [walk(y) for y in x]
    return names.get(x, x)
  return walk(t)


def source_term(t):
  """A GK term in source spelling: `#:Ann 1` -> `Ann 1`; world names, lexical values and variables unchanged."""
  if isinstance(t, list):
    return [source_term(x) for x in t]
  if isinstance(t, str) and t.startswith("#:") and la.is_concrete(t[2:]):
    return t[2:]
  return t


def plan_of(term, root):
  """(actions in execution order in source spelling, reasons).  Reasons: not_rooted, not_ground, unrecognized_action."""
  acts, s, reasons = [], term, []
  while isinstance(s, list) and len(s) == 3 and s[0] == sit.DO:
    acts.append(s[1])
    s = s[2]
  if s != root:
    reasons.append("not_rooted")
  acts.reverse()
  if _variables(term, []):
    reasons.append("not_ground")
  for a in acts:
    if not (isinstance(a, list) and a and a[0] in la.CONSTRUCTORS and len(a) - 1 == len(la.CONSTRUCTORS[a[0]])):
      reasons.append("unrecognized_action")
      break
  return [source_term(a) for a in acts], reasons


def _answer_value(answer, askvars):
  """(value, reasons) of one accepted `answer` field.  A Boolean question: True, or False for a contrary verdict.
  A question with n reported variables: the n bound terms."""
  if isinstance(answer, bool):
    return answer, ([] if answer else ["contrary_verdict"])
  if not (isinstance(answer, list) and answer and all(isinstance(x, list) and x and x[0] == "$ans" for x in answer)):
    return None, ["malformed_answer"]
  if len(answer) > 1:
    return None, ["disjunctive_answer"]
  args = answer[0][1:]
  if not askvars:
    return True, []
  if len(args) < askvars:
    return None, ["malformed_answer"]
  return args[:askvars], []


def _entry(a, i, where, names):
  det = a.get("detail") if isinstance(a.get("detail"), dict) else {}
  pos, neg = a.get("positive proof"), a.get("negative proof")
  return {"list": where, "index": i, "answer": copy.deepcopy(a.get("answer")), "confidence": a.get("confidence"),
          "detail": copy.deepcopy(det), "blockers": copy.deepcopy(a.get("blockers")),
          "positive_proof": copy.deepcopy(pos), "negative_proof": copy.deepcopy(neg),
          "sources": {"positive": proof_sources(pos), "negative": proof_sources(neg)},
          "conflict": det.get("conflict"), "support_for": det.get("support_for"),
          "support_against": det.get("support_against"), "recursive_checks": det.get("recursive_checks"),
          "flags": copy.deepcopy(det.get("flags")),
          "both_proofs": bool(proof_steps(pos)) and bool(proof_steps(neg)),
          "reuse": evidence_reuse(pos, names), "units": proof_units(pos, names)}


def confidence_ok(conf):
  """A confidence is a finite number in [0, 1], not a Boolean."""
  return isinstance(conf, (int, float)) and not isinstance(conf, bool) and math.isfinite(conf) and 0 <= conf <= 1


def _entry_status(e, experimental_units):
  why = set()
  if not proof_steps(e["positive_proof"]):
    why.add("provenance_unchecked")
  if e["reuse"]:
    why.add("uncertain_evidence_reused")
  for reason, units in experimental_units:
    if set(units) & set(e["units"]):
      why.add(reason)
  return sorted(why)


def extract(stdout, stderr="", exit_code=0, timed_out=False, kind="boolean", askvars=0, root=None, names=None,
            experimental_units=(), candidates_only=False, launch_error=None):
  """The answers of one launch.

  `kind` is `boolean` (a snapshot, verify or joint question), `ask` or `discovery`; `askvars` the number of
  variables the question reports; `root` the planning root; `names` the view's source records by clause name;
  `experimental_units` maps each unmet experimental capability to its units.
  Returns {"status", "error", "result", "warnings", "accepted", "rejected", "candidates"}.
  """
  p = parse_output(stdout, stderr, exit_code, timed_out, launch_error)
  out = {"status": p["status"], "error": p["error"], "result": p["result"], "warnings": p["warnings"],
         "accepted": [], "rejected": [], "candidates": []}
  if p["status"] != "completed":
    return out
  for i, a in enumerate(p["rejected"]):
    e = _entry(a, i, "rejected_answers", names)
    e["eligible"], e["reasons"] = False, ["rejected_entry"]
    out["rejected"].append(e)
  groups = {}
  for i, a in enumerate(p["answers"]):
    e = _entry(a, i, "answers", names)
    value, reasons = _answer_value(a.get("answer"), askvars)
    conf = a.get("confidence")
    if not confidence_ok(conf):
      reasons.append("malformed_confidence")
    elif conf < CUTOFF:
      reasons.append("below_cutoff")
    key, fields = None, {}
    if not reasons and askvars:
      if kind == "discovery":
        plan, why = plan_of(value[0], root)
        wit = [source_term(w) for w in value[1:]]
        if _variables(value[1:], []) and "not_ground" not in why:
          why.append("not_ground")
        reasons.extend(why)
        fields = {"plan": plan, "witnesses": wit, "term": copy.deepcopy(value[0])}
        key = json.dumps(canonical_term([plan, wit]))
      else:
        if _variables(value, []):
          reasons.append("not_ground")
        fields = {"answer": source_term(value)}
        key = json.dumps(canonical_term(source_term(value)))
    elif not reasons:
      key, fields = "true", {"verdict": True}
    if candidates_only:
      reasons.append("nonegative_run")
    e["eligible"], e["reasons"], e["key"] = not reasons, reasons, key
    e["experimental_reasons"] = _entry_status(e, experimental_units)
    e["confidence_status"] = "experimental" if e["experimental_reasons"] else "validated"
    out["accepted"].append(e)
    if e["eligible"]:
      g = groups.get(key)
      if g is None:
        g = groups[key] = dict({"key": key, "entries": [], "confidences": []}, **fields)
        out["candidates"].append(g)
      g["entries"].append(i)
      g["confidences"].append(conf)
  for g in out["candidates"]:
    # the confidence and its status come from the same proof: the largest confidence, from a validated entry when
    # one of the entries at that confidence is validated; the other entries' statuses stay in `entry_status`
    g["confidence"] = max(g["confidences"])
    top = [i for i in g["entries"] if out["accepted"][i]["confidence"] == g["confidence"]]
    clean = [i for i in top if out["accepted"][i]["confidence_status"] == "validated"]
    g["confidence_entry"] = (clean or top)[0]
    g["experimental_reasons"] = [] if clean else sorted({r for i in top for r in out["accepted"][i]["experimental_reasons"]})
    g["confidence_status"] = "experimental" if g["experimental_reasons"] else "validated"
    g["entry_status"] = [{"entry": i, "confidence": out["accepted"][i]["confidence"],
                          "confidence_status": out["accepted"][i]["confidence_status"],
                          "experimental_reasons": out["accepted"][i]["experimental_reasons"]} for i in g["entries"]]
  return out


def termination(rec, extracted):
  """Why a launch ended.  The launch's own record decides proof, timeout and error; the relaunch only explains a
  completed launch with no accepted entry, and only when the relaunch itself completed with no accepted entry:
  a failed relaunch is `diagnostic_error`, one that found an answer the launch did not is `diagnostic_differs`."""
  if rec["timed_out"]:
    return "timeout"
  if extracted["status"] != "completed":
    return "error"
  if extracted["accepted"]:
    return "proof"
  r = rec.get("relaunch")
  if r is None:
    return "not_diagnosed"
  if r.get("status") != "completed" or r.get("timed_out") or r.get("exit") != 0:
    return "diagnostic_error"
  if r.get("accepted"):
    return "diagnostic_differs"
  if any("search limit reached" in x for x in r["lines"]):
    return "search_limit"
  return "undetermined"


# ---------------------------------------------------------------------------
# a query


def _names(source_artifact, query_artifact):
  src, _, _ = lq.view_records(source_artifact, ar._library(), query_artifact["selected_clauses"]["view"],
                              ar._selection(query_artifact), query_artifact["excluded"] or [])
  return {r["name"]: {"unit": r.get("unit"), "units": r.get("units"), "role": r["role"],
                      "confidence": r.get("confidence")} for r in src}


def planned_launches(query_artifact):
  """[(obligation id, polarity, role, question)] in launch order: every obligation's positive, then its negative;
  the joint positive last."""
  out = []
  for o in query_artifact["obligations"] or []:
    for pol in ("positive", "negative"):
      if o.get(pol) is not None:
        out.append((o["id"], pol, o["role"], o[pol]["question"]))
  if query_artifact.get("joint_positive"):
    out.append(("joint", "positive", "joint", query_artifact["joint_positive"]["question"]))
  return out


def _kind(query_artifact, role):
  if role == "discovery":
    return "discovery"
  if query_artifact["query"]["kind"] == "ask":
    return "ask"
  return "boolean"


def _record(query_artifact, source_artifact, profile, limits, reqs, outcome=None, planned=None):
  return {"artifact": EVIDENCE, "version": EVIDENCE_VERSION,
          "source": {"source_hash": source_artifact["hashes"]["source"],
                     "artifact_hash": source_artifact["hashes"]["artifact"]},
          "query": {"id": query_artifact["query"]["id"], "kind": query_artifact["query"]["kind"],
                    "hash": query_artifact["hash"], "view": query_artifact.get("view"),
                    "view_hash": query_artifact.get("view_hash"), "obligations_hash": query_artifact.get("obligations_hash"),
                    "planning_root": query_artifact["planning_root"]},
          "backend": backend_identity(profile, source_artifact.get("library")),
          "limits": {k: v for k, v in limits.items() if k != "keep"},
          "requirements": reqs, "outcome": outcome, "planned": planned,
          "obligations": [], "joint": None, "incomplete": [],
          "calls": {"gk": 0, "by_role": {}, "elapsed": 0.0}}


def run_query(source_artifact, query_artifact, backend=None, limits=None, ledger=None):
  """Run every obligation of a compiled query on the registered backend.  Returns an `action_evidence` record.

  `backend` is the name of a registered build (default `gk`).  A typed outcome before any launch: the
  query's own outcome (invalid, unsupported, insufficient allowance, an unvalidated requirement at compile time),
  `backend_unavailable`, `unsupported_backend_requirement`, or `call_limit` when the worst-case launch count
  exceeds `max_launches`.  A launch that cannot start gives `backend_unavailable` (`launch_failed`), and a build
  that ignores a strategy setting gives `backend_incompatible`; both stop the query.  Otherwise `outcome` is None
  and the record holds the evidence of every launch; the answer policy decides.  `incomplete` lists the launches
  that did not complete (a timeout, a GK error, malformed output): an answer that needs one of them is not
  supported by this record.
  """
  ar.check_artifact(source_artifact, ar.SOURCE)
  ar.check_artifact(query_artifact, ar.QUERY)
  ar.same_revision(source_artifact, query_artifact)
  profile = backend_profile(backend)
  lim = normalize_limits(limits)
  library = source_artifact.get("library")
  if query_artifact["outcome"]:
    return _record(query_artifact, source_artifact, profile, lim, [], copy.deepcopy(query_artifact["outcome"]))
  if not query_artifact["obligations"]:
    raise AdapterError("the query artifact has no obligations: %r" % (query_artifact["pending_passes"],))
  reqs = requirements(query_artifact, profile, library)
  gone = availability(profile)
  if gone:
    return _record(query_artifact, source_artifact, profile, lim, reqs, gone)
  # a requirement that only the negative polarity reads is decided at answer time (action_answer.decide)
  refused = [r for r in reqs if not r["validated"] and r["policy"] == "refuse"
             and "positive" in r.get("polarities", ["positive"])]
  if refused:
    r = refused[0]
    return _record(query_artifact, source_artifact, profile, lim, reqs,
                   {"outcome": "unsupported_backend_requirement", "reason": r["reason"],
                    "capabilities": [x["capability"] for x in refused], "units": r["units"], "detail": r["detail"],
                    "backend": profile["name"]})
  plan = planned_launches(query_artifact)
  planned = {"main": len(plan), "worst": len(plan) * (2 if lim["termination"] else 1)}
  if lim["max_launches"] is not None and planned["worst"] > lim["max_launches"]:
    return _record(query_artifact, source_artifact, profile, lim, reqs,
                   {"outcome": "call_limit", "planned": planned, "max_launches": lim["max_launches"],
                    "detail": "the query's obligations may need %d launches (%d questions, each with a possible "
                              "termination relaunch); the limit is %d" % (planned["worst"], planned["main"],
                                                                           lim["max_launches"])},
                   planned)
  rec = _record(query_artifact, source_artifact, profile, lim, reqs, None, planned)
  names = _names(source_artifact, query_artifact)
  exper = [(r["reason"] if r["capability"] != lq.SHARED_CONFIDENCE else "shared_source_confidence_unmet", r["units"])
           for r in reqs if not r["validated"] and r["policy"] == "experimental"]
  by_id = {o["id"]: {"id": o["id"], "role": o["role"], "text": o.get("text"), "step": o.get("step"),
                     "requires_prefix": o.get("requires_prefix"), "positive": None, "negative": None}
           for o in query_artifact["obligations"]}
  rec["obligations"] = [by_id[o["id"]] for o in query_artifact["obligations"]]
  local = {"gk_calls": []}
  for oid, pol, role, question in plan:
    objs = ar.query_input(source_artifact, query_artifact, oid, pol)
    tag = "%s:%s" % (role, pol)
    raw = launch(profile, objs, seconds_for(lim, role), tag, lim["flags"], lim["termination"], local, lim["keep"],
                 label="%s.%s.%s" % (query_artifact["query"]["id"], oid, pol))
    ex = extract(raw["stdout"], raw["stderr"], raw["exit"], raw["timed_out"], _kind(query_artifact, role),
                 question.get("@askvars", 0), query_artifact["planning_root"], names, exper,
                 candidates_only="-nonegative" in lim["flags"], launch_error=raw["launch_error"])
    ev = dict(raw, obligation=oid, polarity=pol, **ex)
    ev["termination"] = termination(raw, ex)
    if oid == "joint":
      rec["joint"] = ev
    else:
      by_id[oid][pol] = ev
    if ex["status"] != "completed":
      rec["incomplete"].append({"launch": "%s:%s" % (oid, pol), "status": ex["status"],
                                "error": ex["error"]})
    if ex["status"] == "backend_incompatible":
      # every later launch of this build ignores the same setting: stop
      rec["outcome"] = {"outcome": "backend_incompatible", "backend": profile["name"], "detail": ex["error"]}
      break
    if ex["status"] == "launch_failed":
      rec["outcome"] = {"outcome": "backend_unavailable", "reason": "launch_failed", "backend": profile["name"],
                        "detail": ex["error"]}
      break
  for c in local["gk_calls"]:
    rec["calls"]["gk"] += 1
    rec["calls"]["by_role"][c["role"]] = rec["calls"]["by_role"].get(c["role"], 0) + 1
    rec["calls"]["elapsed"] = round(rec["calls"]["elapsed"] + c["seconds"], 3)
  if ledger is not None:
    ledger.setdefault("gk_calls", []).extend(local["gk_calls"])
  return rec


def launches(evidence):
  """Every launch record of an evidence record, in launch order."""
  out = []
  for o in evidence["obligations"]:
    out.extend(x for x in (o["positive"], o["negative"]) if x is not None)
  if evidence["joint"]:
    out.append(evidence["joint"])
  return out


# ---------------------------------------------------------------------------
# the build's own regressions


def prerequisite_status(extracted):
  """Yes, No, contested or Unknown of a prerequisite launch, from all its accepted entries."""
  acc = extracted["accepted"]
  if extracted["status"] != "completed" or not acc:
    return "Unknown"
  if any((e["conflict"] or 0) > 0 or ((e["support_for"] or 0) > 0 and (e["support_against"] or 0) > 0) for e in acc):
    return "contested"
  if any((e["support_for"] or 0) > 0 for e in acc):
    return "Yes"
  if any((e["support_against"] or 0) > 0 for e in acc):
    return "No"
  return "Unknown"


def check_prerequisites(backend=None, ledger=None):
  """Run the build's recursive-blocker and invalidated-exception regressions: four launches, run by hand to
  re-validate a GK build (no check or pipeline step calls this).

  Returns {"ok", "backend", "rows": [{"case", "expected", "status", "elapsed"}]} or {"ok": False, "outcome": ...}
  when the binary or the regression files are missing.
  """
  profile = backend_profile(backend)
  gone = availability(profile)
  if gone:
    return {"ok": False, "backend": profile["name"], "outcome": gone}
  pre = profile.get("prerequisites")
  if not pre or not os.path.isdir(pre["folder"]):
    return {"ok": False, "backend": profile["name"],
            "outcome": {"outcome": "backend_unavailable", "reason": "prerequisites_missing",
                        "detail": "the regression folder %r is not present" % (pre or {}).get("folder")}}
  rows = []
  for case in sorted(pre["expect"]):
    path = os.path.join(pre["folder"], case + ".js")
    cmd = [profile["path"], path, "-detail", "-outformat", "json"]
    out, err, code, timed_out, elapsed, failed = _execute(cmd, profile["datafolder"], pre["seconds"] + EXTRA)
    _count(ledger, "backend_check", profile, elapsed, None)
    ex = extract(out, err, code, timed_out, launch_error=failed)
    status = prerequisite_status(ex)
    rows.append({"case": case, "expected": pre["expect"][case], "status": status, "elapsed": elapsed,
                 "ok": status == pre["expect"][case]})
  return {"ok": all(r["ok"] for r in rows), "backend": profile["name"], "sha256": profile["sha256"], "rows": rows}
