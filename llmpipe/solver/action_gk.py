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
strategy keys added for a launch role, the command parameters and the
capabilities validated for it.  A caller names a
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

# the planning strategy of every launch: query focus; a $ctxt term and a blocker literal of a rule weigh one
# constant; a clause whose answers would all have confidence 0 is dropped (the blocker-unit cut, with guarded rules)
PLANNING_STRATEGY = {"strategy": ["query_focus"], "query_preference": 1, "equality": 0,
       "weight_select_ratio": 20, "weight_blocker_const": 2, "weight_ctxt_const": 1,
       "blocker_unit_cut": 1, "blocker_unit_cut_guards": 1}
# the keys added for a plan search (the positive discovery launch): literal selection and eager condensation.  GK
# applies them in every primary search and cannot tell a plan search from another one, so the adapter gives them only
# to this role.  ../gk/Doc/planning.md describes each key.
DISCOVERY_KEYS = {"ground_contextfree_negative_first": 1, "reachable_known_head_first": 1,
                  "permission_pair_first": 1, "eager_condensation": 1}
# the plan search (action_plan) launches its candidate checks and its filtered discovery under these roles: a check
# asks for one proposed plan with the known plan states and stops at its first answer; a filtered discovery reads the
# plan filters of its input
ROLE_STRATEGY = {"discovery:positive": DISCOVERY_KEYS,
                 "discovery:check": dict(DISCOVERY_KEYS, plan_state=1, max_answers=1),
                 "discovery:filtered": dict(DISCOVERY_KEYS, plan_filters=1)}
PIPELINE_PARAMS = ["-taxonomy", "-confidence", "0.1", "-keepconfidence", "0.1"]
DATAFOLDER = os.path.join(os.path.dirname(ROOT), "gk")

RESULTS = ("answer found", "evidence below limit", "no answers found", "no information",
           "time limit, proof not found")
NO_ANSWER_RESULTS = ("no answers found", "no information", "time limit, proof not found")
INCOMPATIBLE = "unknown setting in the strategy"

BACKENDS = {
  # the installed prover, gk 1.1.0 (branch planning of the gk repository), with the planning strategy
  "gk": {
    "name": "gk",
    "path": os.path.join(DATAFOLDER, "gk"),
    "status": "installed",
    "strategy": PLANNING_STRATEGY,
    "role_strategy": ROLE_STRATEGY,
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
# The build with planning summaries (`-planning-profile`): the installed gk 1.1.0 has the read-only summary module.
# Same binary, strategies, parameters and data folder as DEFAULT_BACKEND.  A call that asks for summaries uses this
# entry, and every other call uses DEFAULT_BACKEND.
SUMMARY_BACKEND = "gk_summary"
SUMMARY_OUTPUT = "planning_summary_output/1"
SUMMARY_CAPABILITY = "planning_summary"
BACKENDS[SUMMARY_BACKEND] = dict(copy.deepcopy(BACKENDS["gk"]), name=SUMMARY_BACKEND, summary=True)
# The summary capability counts only for the binary, library, strategy and summary contract that were tested; a
# rebuilt binary at the same path needs its own record.  The unmet requirements and known failures of `gk` stay.
BACKENDS[SUMMARY_BACKEND]["validated"] = [{
  "capability": SUMMARY_CAPABILITY,
  "binary_sha256": "d2985bcf3e73e9a48e78b03c7b3b7cd9a2d4db464006663d9b13bb34255f81b9",
  "library": {"id": "axioms_action.js", "version": "2.0.1",
              "hash": "fa3347058f0175b3e2d0907c828eb3d22fc1e2ae25e7f7f9255c4b91b60a4474",
              "roles_hash": "b389587cbcd000318f81c4d16ed03b826e00ee02eb491b47f1ba74161256da2f",
              "templates_hash": "0c49cec76553c3f620a9a78004aad031e538286e985e0db701a8b770f64143a6", "status": "selected"},
  "strategy_sha256": "9b559e9de7a86908464db5c90e2bc6ec5a1ba5baa39eb7844edc76e30d0a07a4",
  "contract": {"profile": "planning_summary_profile/2", "summary": "planning_summary/1", "output": SUMMARY_OUTPUT},
  "evidence": "on this binary, gk 1.1.0, with these strategies: 18 route launches give 6 controls (unstack, "
              "two_leg_travel, ticket_travel, reverse_tower, ystad, witness) equal with and without the summary and "
              "on gk, each summary check ok; 19 hand-written clauses give 527 observations equal to the hand-written "
              "table (inspect-only runs); the backend prerequisites give 4 of 4.  The summary evaluator is the same "
              "source as in the build that agreed with the reference interpreter on 133 profiles and 2837 requests.  "
              "Not shown: negative persistence and the per-application confidence (the unmet requirements of gk)"}]


class SummaryError(Exception):
  """A planning-summary sidecar that does not belong to its input, or a staged file whose bytes changed."""


class AdapterError(Exception):
  """A caller error: an unknown backend, a bad limit, an unknown flag."""


# ---------------------------------------------------------------------------
# backend profile


def strategy_sha256(strategy):
  # ASCII-escaped JSON, unlike `digests.canonical`: the recorded strategy hashes read this form
  return sha256_text(json.dumps(strategy, sort_keys=True, separators=(",", ":")))


def strategy_for(profile, role):
  """The strategy of one launch: the backend's strategy plus the keys that `role_strategy` adds for this role."""
  return dict(profile["strategy"], **(profile.get("role_strategy") or {}).get(role, {}))


def profile_strategy_sha256(profile):
  """The hash of the backend's strategies: the strategy alone, or the strategy and the keys of each role."""
  if not profile.get("role_strategy"):
    return strategy_sha256(profile["strategy"])
  return strategy_sha256({"strategy": profile["strategy"], "roles": profile["role_strategy"]})


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
          "role_strategy": copy.deepcopy(profile.get("role_strategy") or {}),
          "strategy_sha256": profile_strategy_sha256(profile), "params": list(profile["params"]),
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


def capability(profile, name, library, contract=None):
  """{"capability", "validated", "reason", "policy", "evidence"} for this build, library identity and strategy, and
  for the interface versions `contract` when the capability has them."""
  want = profile_strategy_sha256(profile)
  for v in profile["validated"]:
    if v["capability"] == name and v["binary_sha256"] == profile["sha256"] and v["library"] == library \
       and v["strategy_sha256"] == want and v.get("contract") == contract:
      return {"capability": name, "validated": True, "reason": None, "policy": None, "evidence": v.get("evidence")}
  u = profile["unmet"].get(name) or {"reason": "capability_not_validated", "policy": "refuse",
                                     "evidence": "no validation record for this build"}
  return {"capability": name, "validated": False, "reason": u["reason"], "policy": u["policy"],
          "evidence": u.get("evidence")}


def summary_contract():
  """The planning-summary interface versions this adapter reads: profile schema, summary contract, output schema."""
  import action_summary as asum
  return {"profile": asum.SCHEMA, "summary": asum.CONTRACT, "output": SUMMARY_OUTPUT}


def summary_capability(profile, library, any_library=False):
  """None when the build may run planning-summary launches for this library, else the refusal outcome.  The build
  needs the summary module and a validation record that names this binary, library, strategy and
  `summary_contract()`; another binary at the same path has no record.  With `any_library` the record may name any
  library (`summary_preflight`, before a source exists)."""
  base = {"outcome": "unsupported_backend_requirement", "capabilities": [SUMMARY_CAPABILITY], "units": [],
          "backend": profile["name"]}
  if not profile.get("summary"):
    return dict(base, reason="planning_summary_unsupported",
                detail="the build %r has no planning-summary module; the summary build is %r" % (profile["name"], SUMMARY_BACKEND))
  try:
    import action_summary  # noqa: F401
    import lc_action_summary  # noqa: F401
  except ImportError as e:
    return dict(base, reason="planning_summary_unsupported",
                detail="the pipeline's planning-summary modules are not present: %s" % e)
  contract = summary_contract()
  if any_library:
    strategy = profile_strategy_sha256(profile)
    ok = any(v["capability"] == SUMMARY_CAPABILITY and v["binary_sha256"] == profile["sha256"]
             and v["strategy_sha256"] == strategy and v.get("contract") == contract for v in profile["validated"])
  else:
    ok = capability(profile, SUMMARY_CAPABILITY, library, contract)["validated"]
  if not ok:
    return dict(base, reason="planning_summary_not_validated",
                detail="no planning-summary validation record names the binary %s at %s with this %sstrategy and "
                       "summary contract" % (profile["sha256"], profile["path"], "" if any_library else "library, "))
  return None


def summary_preflight(backend):
  """The checks of a planning-summary request that need no source: None, or the outcome that `run_query` would give
  before its first launch.  The binary and its data folder are present, the summary modules import, and a
  validation record names the binary now at the path, the strategy and the summary contract.  The action route
  runs this before any model call; `run_query` checks again, with the source's library."""
  profile = backend_profile(backend)
  return availability(profile) or summary_capability(profile, None, any_library=True)


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
  "keep": directory or None, "summary", "summary_choice", "strategy_role", "extra_clauses"}.

  `strategy_role`, `extra_clauses` and `launch_label` belong to the plan search: the positive discovery launch runs
  under that role strategy (a key of the backend's `role_strategy`), with those clauses added to its input, and with
  the label QUERY.`launch_label` (for -gkin and `keep`) in place of QUERY.plan.positive."""
  limits = dict(limits or {})
  bad = set(limits) - {"seconds", "max_launches", "termination", "flags", "keep", "summary", "summary_choice",
                       "strategy_role", "extra_clauses", "launch_label"}
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
  role = limits.get("strategy_role")
  if role is not None and not isinstance(role, str):
    raise AdapterError("strategy_role is the name of a role strategy or None")
  label = limits.get("launch_label")
  if label is not None and not (isinstance(label, str) and label and all(c.isalnum() or c in "._" for c in label)):
    raise AdapterError("launch_label is a nonempty string of letters, digits, dots and underscores")
  extra = limits.get("extra_clauses") or []
  if not (isinstance(extra, list) and all(isinstance(c, dict) and "@logic" in c for c in extra)):
    raise AdapterError("extra_clauses is a list of GK clause objects")
  return {"seconds": secs, "max_launches": cap, "termination": bool(limits.get("termination", True)),
          "flags": flags, "keep": limits.get("keep"), "summary": bool(limits.get("summary")),
          "summary_choice": copy.deepcopy(limits.get("summary_choice")), "strategy_role": role,
          "extra_clauses": copy.deepcopy(extra), "launch_label": label}


def seconds_for(limits, role):
  s = limits["seconds"]
  if isinstance(s, dict):
    return s.get(role, s.get("default", DEFAULT_SECONDS))
  return s


def command(profile, input_path, seconds, flags=(), printlevel=None, sidecar_path=None, role=None):
  """The GK command of one launch: the registered binary, the strategy of the launch's role and the parameters,
  nothing else.  With `sidecar_path`, the one planning-summary profile of this input; no other file and no other
  flag is added."""
  cmd = [profile["path"], "-strategytext", json.dumps(strategy_for(profile, role)), "-seconds", str(seconds), input_path] \
    + list(profile["params"]) + list(flags) + ["-datafolder", profile["datafolder"], "-detail", "-outformat", "json"]
  if sidecar_path is not None:
    cmd += ["-planning-profile", sidecar_path]
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
_TAMPER = []      # tests only: a function (input path, profile path) called between staging and verification


@contextlib.contextmanager
def recording():
  """Collect the full text of every launch in this block: [{"label", "role", "command", "input", "profile",
  "profile_sha256", "stdout", "stderr", "elapsed", "relaunch"}], in launch order.  `command` has "<input>" where the
  input file's path stands and "<profile>" for a planning-summary profile, whose exact text is `profile` (None
  without one)."""
  got = []
  _RECORDINGS.append(got)
  try:
    yield got
  finally:
    _RECORDINGS.remove(got)


def _record_launch(entry):
  for got in _RECORDINGS:
    got.append(entry)


def summary_binding_error(sidecar, source_artifact, query_artifact, oid, pol, objs):
  """None when the profile belongs to exactly this launch, else the reason.  Checked before any launch: the
  profile's own identity, then the source, query, view, root, obligation, polarity, question name and input bytes
  that its binding records."""
  import action_summary as asum
  try:
    asum.validate(sidecar)
  except asum.ProfileError as e:
    return "profile_invalid: %s" % e
  b, sem = sidecar["binding"], sidecar["semantic"]
  question = [o for o in objs if isinstance(o, dict) and "@question" in o]
  checks = (("source", b.get("source_hashes") == source_artifact["hashes"]),
            ("query", b.get("query_hash") == query_artifact["hash"]),
            ("view", b.get("view_hash") == query_artifact.get("view_hash")),
            ("root", sem["root"] == query_artifact["planning_root"]
             and (b.get("selection") or {}).get("planning_root") == query_artifact["planning_root"]),
            ("obligation", b.get("obligation") == oid and b.get("polarity") == pol),
            ("question", len(question) == 1 and b.get("question") == question[0].get("@name")),
            ("input_bytes", b.get("input_sha256") == sha256_text(input_text(objs))))
  bad = [name for name, ok in checks if not ok]
  return "binding_mismatch: %s" % ", ".join(bad) if bad else None


def _verify_staged(path, text, sidecar_path, sidecar_text):
  """Read both staged files back and compare their bytes with what the adapter wrote.  Raises SummaryError
  `staged_input_changed`, `staged_profile_changed`, or `staged_input_unreadable` / `staged_profile_unreadable` for
  a file that is missing or cannot be read."""
  for p, want, what in ((path, text, "input"), (sidecar_path, sidecar_text, "profile")):
    if p is None:
      continue
    try:
      got = sha256_file(p)
    except OSError:
      raise SummaryError("staged_%s_unreadable" % what)
    if got != sha256_text(want):
      raise SummaryError("staged_%s_changed" % what)


def _staged_problem(path, text, sidecar_path, sidecar_text):
  """None when both staged files hold the bytes the adapter wrote, else the reason."""
  try:
    _verify_staged(path, text, sidecar_path, sidecar_text)
  except SummaryError as e:
    return str(e)
  except OSError as e:
    return "staged_file_unreadable: %s" % type(e).__name__
  return None


TAXONOMY_FILES = ("gk_name_number.txt", "gk_taxonomy_packed.txt")


def data_fingerprints(profile):
  """The taxonomy-priority files that GK reads from the data folder with -taxonomy: {name: {"status", "sha256"}},
  status `present`, `absent`, `unreadable`, or `not_used` when the registered parameters have no -taxonomy."""
  used = "-taxonomy" in profile["params"]
  out = {}
  for name in TAXONOMY_FILES:
    p = os.path.join(profile["datafolder"], name)
    if not used:
      out[name] = {"status": "not_used", "sha256": None}
    elif not os.path.isfile(p):
      out[name] = {"status": "absent", "sha256": None}
    else:
      try:
        out[name] = {"status": "present", "sha256": sha256_file(p)}
      except OSError:
        out[name] = {"status": "unreadable", "sha256": None}
  return out


def launch(profile, objs, seconds, role, flags=(), termination=True, ledger=None, keep=None, label=None, sidecar=None):
  """Run GK once on `objs` (and once more for the termination reason when no answer is accepted).

  Returns the raw launch record: command, hashes, elapsed time, exit status, stdout, stderr and, when a relaunch
  ran, its termination lines.  Extraction is `extract`.  With `keep`, the input, output and error text are saved
  under `keep` as LABEL.input.json, LABEL.out and LABEL.err, a relaunch's as LABEL.relaunch.out and .err, and a
  planning-summary profile as LABEL.profile.json.

  With `sidecar`, both staged files are verified inside the serial lock, immediately before each process.  A file
  that is missing or changed before the launch raises SummaryError (phase `launch`): no process ran.  Before the
  diagnostic relaunch it does not raise: the completed launch is returned with its output and its count, and
  `relaunch` says that the relaunch was not made and why (`launched` false, `staged_error`).
  """
  text = input_text(objs)
  clauses = sum(1 for o in objs if isinstance(o, dict))
  tmp = tempfile.mkdtemp(prefix="action_gk_")
  try:
    path = os.path.join(tmp, "input.json")
    with open(path, "w") as f:
      f.write(text)
    # the sidecar is staged beside the input, in this launch's private directory; the diagnostic relaunch reads
    # the same two files
    spath = stext = None
    if sidecar is not None:
      spath, stext = os.path.join(tmp, "profile.json"), json.dumps(sidecar, ensure_ascii=False)
      with open(spath, "w") as f:
        f.write(stext)
    shown = lambda c: ["<input>" if x == path else "<profile>" if x == spath else x for x in c]
    cmd = command(profile, path, seconds, flags, sidecar_path=spath, role=role)
    data = data_fingerprints(profile) if sidecar is not None else None
    with _serial():
      if _TAMPER:
        _TAMPER[0](path, spath, "launch")
      bad = _staged_problem(path, text, spath, stext)
      if bad is None:
        out, err, code, timed_out, elapsed, failed = _execute(cmd, profile["datafolder"], seconds + EXTRA)
    if bad is not None:
      e = SummaryError(bad)
      e.phase = "launch"
      raise e
    _count(ledger, role, profile, elapsed, clauses)
    rec = {"role": role, "command": shown(cmd), "seconds": seconds,
           "strategy_sha256": strategy_sha256(strategy_for(profile, role)),
           "summary": None if sidecar is None else {"profile_id": sidecar["profile_id"], "profile_sha256": sha256_text(stext),
                                                    "output_schema": SUMMARY_OUTPUT, "data_files": data},
           "external_timeout": seconds + EXTRA, "input_sha256": sha256_text(text),
           "clauses": clauses, "binary_sha256": profile["sha256"], "elapsed": elapsed, "exit": code,
           "timed_out": timed_out, "launch_error": failed, "stdout": out, "stderr": err, "relaunch": None}
    parsed = parse_output(out, err, code, timed_out, failed)
    out2 = err2 = None
    if termination and parsed["status"] == "completed" and not parsed["answers"]:
      cmd2 = command(profile, path, seconds, flags, printlevel=PRINTLEVEL, sidecar_path=spath, role=role)
      with _serial():
        if _TAMPER:
          _TAMPER[0](path, spath, "relaunch")
        bad = _staged_problem(path, text, spath, stext)
        if bad is None:
          out2, err2, code2, timed2, elapsed2, failed2 = _execute(cmd2, profile["datafolder"], seconds + EXTRA)
      if bad is not None:
        rec["relaunch"] = {"launched": False, "staged_error": bad, "command": shown(cmd2), "elapsed": None, "exit": None,
                           "timed_out": False, "launch_error": None, "status": "not_launched", "error": bad,
                           "result": None, "accepted": 0, "lines": []}
      else:
        _count(ledger, "termination", profile, elapsed2, clauses)
        rec["relaunch"] = relaunch_record(out2, err2, code2, timed2, failed2)
        rec["relaunch"].update(command=shown(cmd2), elapsed=elapsed2)
    if _RECORDINGS:
      _record_launch({"label": label or role, "role": role, "command": rec["command"], "input": text,
                      "profile": stext, "profile_sha256": None if stext is None else sha256_text(stext),
                      "stdout": out, "stderr": err, "elapsed": elapsed,
                      "relaunch": None if rec["relaunch"] is None else dict(rec["relaunch"], stdout=out2 or "")})
    if keep:
      os.makedirs(keep, exist_ok=True)
      base = os.path.join(keep, (label or role).replace(":", "_"))
      with open(base + ".input.json", "w") as f:
        f.write(text)
      if stext is not None:
        with open(base + ".profile.json", "w") as f:
          f.write(stext)
      with open(base + ".out", "w") as f:
        f.write(out)
      with open(base + ".err", "w") as f:
        f.write(err)
      if rec["relaunch"] is not None and rec["relaunch"]["status"] != "not_launched":
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
          "both_proofs": bool(proof_steps(pos)) and bool(proof_steps(neg)), "summary": copy.deepcopy(a.get("_summary")),
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


def _world_list(term):
  """The JSON array of a rendered $list chain, or None for another term."""
  out = []
  while term != "$nil":
    if not (isinstance(term, list) and len(term) == 3 and term[0] == "$list"):
      return None
    out.append(term[1])
    term = term[2]
  return out


SUMMARY_SLOTS = {"plan": 1, "world": 2, "progress": 3}
UNDECORATED = ("not_applicable", "allocation_failed")


def _exact_int(x):
  return isinstance(x, int) and not isinstance(x, bool)


def _summary_layout(meta, ans, sidecar):
  """None when an entry's metadata and answer have the layout of the output contract, else the problem.  The
  layout decides which answer positions are witnesses, so a problem here stops the decoding."""
  if not (isinstance(meta, dict) and meta.get("schema") == SUMMARY_OUTPUT and meta.get("profile_id") == sidecar["profile_id"]
          and isinstance(meta.get("decorated"), bool)):
    return "an entry has no planning_summary of this profile and schema: %r" % (meta,)
  if not meta["decorated"]:
    reason = meta.get("reason")
    if not (isinstance(reason, str) and reason in UNDECORATED):
      return "an entry that is not decorated has the reason %r" % (reason,)
    return None
  slots, arity = meta.get("slots"), meta.get("core_arity")
  if not (isinstance(slots, dict) and sorted(slots) == sorted(SUMMARY_SLOTS)
          and all(_exact_int(slots[k]) and slots[k] == v for k, v in SUMMARY_SLOTS.items())
          and _exact_int(arity) and arity >= 1
          and isinstance(ans, list) and len(ans) == 1 and isinstance(ans[0], list) and len(ans[0]) == arity + 3
          and ans[0][0] == "$ans"):
    return "a decorated entry does not fit its slot map: core_arity %r, slots %r, answer %r" % (arity, slots, str(ans)[:200])
  return None


def _world_fact(f, families):
  """True for a World fact of the output contract: a ground fact of one of `families` (`action_summary.term_defect`,
  `family_of`) in which every compound term is a nonempty list with a string functor and every string can be
  encoded as UTF-8 (no lone surrogate).  Checked before any order key is built."""
  import action_summary as asum
  if asum.term_defect(f) is not None or asum.family_of(f) not in families:
    return False
  stack = [f]
  while stack:
    x = stack.pop()
    if isinstance(x, list):
      if not (x and isinstance(x[0], str)):
        return False
      stack.extend(x)
    elif isinstance(x, str):
      try:
        x.encode("utf-8")
      except UnicodeEncodeError:
        return False
  return True


def _summary_payload(meta, world_term, world, progress, sidecar):
  """True when the rendered World, Progress and their metadata have the forms of the output contract: World a
  strictly ordered list of facts of the profile's families (`_world_fact`), Progress an integer in the portable
  range, and the calculation, lossy bit, reasons, template and units consistent with them."""
  import action_summary as asum
  reasons = {r for rs in asum.REASONS.values() for r in rs} | {"allocation_failed"}
  reason_ok = lambda x: isinstance(x, str) and x in reasons
  calc, lossy, score = meta.get("calculation"), meta.get("lossy"), sidecar["semantic"]["score"]
  if not (isinstance(calc, str) and calc in ("computed", "partial", "unavailable")):
    return False
  if not (lossy is True or lossy is False or (lossy is None and calc == "unavailable")):
    return False
  if (calc == "unavailable") != (world_term is None) or (calc == "computed") != (progress is not None):
    return False
  if world_term is not None:
    fams = sidecar["semantic"]["families"]
    if world is None or meta.get("world_reason") is not None or not all(_world_fact(f, fams) for f in world):
      return False
    keys = [asum.order_key(f) for f in world]
    if any(a >= b for a, b in zip(keys, keys[1:])):
      return False
  elif not reason_ok(meta.get("world_reason")):
    return False
  if progress is not None:
    if not (_exact_int(progress) and -asum.MAX_INT <= progress <= asum.MAX_INT) or meta.get("progress_reason") is not None:
      return False
  elif not reason_ok(meta.get("progress_reason")):
    return False
  return meta.get("template") == score["template"] and meta.get("units") == score.get("units")


def _undecorate(p, sidecar):
  """Remove the two rendered positions from every entry of a parsed output and keep them as `_summary`.

  Returns None, or the error text when the layout cannot be trusted (`_summary_layout`): no metadata, another
  schema or profile, an unknown reason, or an arity or slot map that does not fit the answer.  Then no answer is
  decoded.  A decorated entry whose payload has another form (`_summary_payload`) keeps its answer and gets a
  disabled annotation."""
  for where, lst in (("accepted", p["answers"]), ("rejected", p["rejected"])):
    for a in lst:
      meta = a.pop("planning_summary", None)
      ans = a.get("answer")
      bad = _summary_layout(meta, ans, sidecar)
      if bad:
        return bad
      # an entry's annotation is never checked here: the answer policy checks the candidates it replays
      ann = {"gk_disposition": where, "decorated": meta["decorated"], "profile_id": meta["profile_id"], "summary_check": "not_checked"}
      if not meta["decorated"]:
        ann.update(reason=meta["reason"], disabled=None)
        a["_summary"] = ann
        continue
      world_term, progress = ans[0][2], ans[0][3]
      a["answer"] = [ans[0][:2] + ans[0][4:]]
      world = None if world_term is None else _world_list(world_term)
      fields = ("calculation", "lossy", "world_reason", "progress_reason", "template", "units")
      if _summary_payload(meta, world_term, world, progress, sidecar):
        ann.update({k: meta.get(k) for k in fields}, core_arity=meta["core_arity"], world=world, progress=progress, disabled=None)
      else:
        # values of another form are not kept: the raw output is in the launch record
        ann.update(dict.fromkeys(fields), core_arity=meta["core_arity"], world=None, progress=None, disabled="malformed_payload")
      a["_summary"] = ann
  return None


def extract(stdout, stderr="", exit_code=0, timed_out=False, kind="boolean", askvars=0, root=None, names=None,
            experimental_units=(), candidates_only=False, launch_error=None, summary=None):
  """The answers of one launch.

  `kind` is `boolean` (a snapshot, verify or joint question), `ask` or `discovery`; `askvars` the number of
  variables the question reports; `root` the planning root; `names` the view's source records by clause name;
  `experimental_units` maps each unmet experimental capability to its units.  `summary` is the planning-summary
  profile the launch was given: every entry is then checked against it, its two rendered positions are removed
  before any other decoding, and the entry gets the annotation `summary`.  World and Progress are never witnesses.
  Extra statuses with `summary`: `planning_profile_error` (the build refused the profile) and
  `summary_output_error` (the output's layout cannot be trusted).
  Returns {"status", "error", "result", "warnings", "accepted", "rejected", "candidates"}.
  """
  p = parse_output(stdout, stderr, exit_code, timed_out, launch_error)
  out = {"status": p["status"], "error": p["error"], "result": p["result"], "warnings": p["warnings"],
         "accepted": [], "rejected": [], "candidates": []}
  if summary is not None and p["status"] == "prover_error" and (p["error"] or "").startswith("planning_profile_error"):
    out["status"] = "planning_profile_error"
  if p["status"] != "completed":
    return out
  if summary is not None:
    bad = _undecorate(p, summary)
    if bad:
      out.update(status="summary_output_error", error=bad)
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
  a failed relaunch is `diagnostic_error`, one that found an answer the launch did not is `diagnostic_differs`, and
  one that was not made because a staged file changed is `diagnostic_not_launched`."""
  if rec["timed_out"]:
    return "timeout"
  if extracted["status"] != "completed":
    return "error"
  if extracted["accepted"]:
    return "proof"
  r = rec.get("relaunch")
  if r is None:
    return "not_diagnosed"
  if r.get("status") == "not_launched":
    return "diagnostic_not_launched"
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
  if lim["strategy_role"] and lim["strategy_role"] not in (profile.get("role_strategy") or {}):
    raise AdapterError("the backend %r has no role strategy %r" % (profile["name"], lim["strategy_role"]))
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
  if lim["summary"]:
    # a build without the summary module, or a binary without a validation record: an explicit refusal, never a
    # run that pretends to summarize
    refused = summary_capability(profile, library)
    if refused:
      return _record(query_artifact, source_artifact, profile, lim, reqs, refused)
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
  if lim["summary"]:
    rec["backend"]["summary_capability"] = dict(capability(profile, SUMMARY_CAPABILITY, library, summary_contract()),
                                                contract=summary_contract())
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
    label = "%s.%s.%s" % (query_artifact["query"]["id"], oid, pol)
    if role == "discovery" and pol == "positive":
      objs = objs + copy.deepcopy(lim["extra_clauses"])
      if lim["strategy_role"]:
        tag = lim["strategy_role"]
      if lim["launch_label"]:
        label = "%s.%s" % (query_artifact["query"]["id"], lim["launch_label"])
    sidecar, compiled = None, None
    if lim["summary"] and role == "discovery" and pol == "positive":
      # the profile of exactly this input; a query the compiler cannot summarize runs unchanged
      import lc_action_summary
      compiled = lc_action_summary.compile_profile(source_artifact, query_artifact, lim["summary_choice"])
      sidecar = compiled["profile"]
      why = sidecar and summary_binding_error(sidecar, source_artifact, query_artifact, oid, pol, objs)
      if why:
        rec["outcome"] = {"outcome": "planning_profile_error", "reason": why, "backend": profile["name"],
                          "detail": "the profile does not belong to this launch; no launch was made"}
        break
    try:
      raw = launch(profile, objs, seconds_for(lim, role), tag, lim["flags"], lim["termination"], local, lim["keep"],
                   label=label, sidecar=sidecar)
    except SummaryError as e:
      rec["outcome"] = {"outcome": "planning_profile_error", "reason": str(e), "backend": profile["name"],
                        "phase": getattr(e, "phase", "launch"), "launch": tag,
                        "detail": "a staged file was missing or changed before the launch; this launch did not run"}
      break
    ex = extract(raw["stdout"], raw["stderr"], raw["exit"], raw["timed_out"], _kind(query_artifact, role),
                 question.get("@askvars", 0), query_artifact["planning_root"], names, exper,
                 candidates_only="-nonegative" in lim["flags"], launch_error=raw["launch_error"], summary=sidecar)
    ev = dict(raw, obligation=oid, polarity=pol, **ex)
    if compiled is not None:
      ev["summary"] = dict(raw["summary"] or {}, status=compiled["status"], reason=compiled["reason"], families=compiled.get("families"),
                           choice=compiled.get("choice"), profile=sidecar)
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
    if ex["status"] in ("planning_profile_error", "summary_output_error"):
      rec["outcome"] = {"outcome": "planning_profile_error", "reason": ex["status"], "backend": profile["name"],
                        "detail": ex["error"]}
      break
    if ex["status"] == "launch_failed":
      rec["outcome"] = {"outcome": "backend_unavailable", "reason": "launch_failed", "backend": profile["name"],
                        "detail": ex["error"]}
      break
    if (raw["relaunch"] or {}).get("status") == "not_launched":
      # the launch completed and its evidence stays in this record; only the diagnostic relaunch was not made
      rec["outcome"] = {"outcome": "planning_profile_error", "reason": raw["relaunch"]["staged_error"],
                        "backend": profile["name"], "phase": "relaunch", "launch": tag,
                        "detail": "a staged file was missing or changed before the diagnostic relaunch; the launch "
                                  "completed and is kept, the relaunch was not made"}
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
