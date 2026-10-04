"""The retry-stage machinery of the ordinary pipeline: which stages exist and in what order, the rule that runs one
stage, the per-stage rows of a run, their call accounting, and the run summary record.

  run_stage(name, enabled, answer, rows, run, ...)   run one stage under the pipeline's rules
  complete_stage_rows(rows, answered_by, collect)   one row per stage in PIPELINE_ORDER, with its call counts
  run_outcome(answer, rows, answered_by)            which of the four run outcomes a run reached
  unresolved(answer), is_error(answer)             whether an answer leaves the question open, or is a failure
  summary_record(...)                               the record that -summary prints

`solve._attempt_body` drives the stages; the runners of the stages after the initial attempt are in
`solve_retries.py`.  The run state (the provider and version, the critic flags, where the attempt's calls begin in
the call log) stays in `solve`, which the functions here read at call time.  `solve` re-exports every name here,
because runtests.py and the local tools reach them as `solve.<name>`.
"""
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#-----------------------------------------------------------------

import contextlib
import json

import globals
import lc_encoding
import llmcall
import prover


# ---------------------------------------------------------------------------
# The one declaration of what stages exist and in what order they run.
# Execution, the summary output and the tests all read these, so a stage
# cannot be added to one and forgotten in another.
# ---------------------------------------------------------------------------

# Every stage, in execution order, and the named configurations: one source,
# `globals`, so the two command-line entry points and the option defaults
# cannot drift.  The
# names are re-exported in `solve`, which the tests and tools read them from.
PIPELINE_ORDER = globals.PIPELINE_ORDER
STAGE_KEYS = tuple(s + "_flag" for s in PIPELINE_ORDER[1:])
PIPELINES = globals.PIPELINES
STACK_OPEN_VECTOR = globals.STACK_OPEN_VECTOR

# The ordinary no-option configuration, adopted 2026-08-27.  `globals.options`
# takes its six stage defaults from `PIPELINES[DEFAULT_PIPELINE]`, so naming it
# explicitly and naming nothing at all resolve to the same stage vector.
DEFAULT_PIPELINE = globals.DEFAULT_PIPELINE

# The cancels, so a line that only cancels still counts as naming a
# configuration explicitly.
CANCEL_KEYS = ("nocritic_flag", "nographtrans_flag", "nographbridge_flag",
               "nolitbridge_flag", "nofallback_norm_flag",
               "nofallback_hyp_flag", "nofallback_flag")

# The three stages `ordinary_attempt` dispatches from a table; the two
# fallbacks and the critic are called by name before them.  `PIPELINE_ORDER` is
# the declared order of all seven and the order every record is written in.
ABSTRACTION_STAGES = ("graphtrans", "litbridge", "graphbridge")


def stages_enabled():
  """The stage keys this run has on, in stage order.

  Written into the case record next to `abstraction_order`, so a results
  folder says what ran without its command line.
  """
  return [k[:-5] for k in STAGE_KEYS if globals.options.get(k)]



def abstraction_order():
  """The graph and bridge stages this run may use, in order.

  A stage the list omits never runs, whatever its own flag says: the list is
  what this run is allowed to try, and the flags say which of those are on.
  A name that is not one of the three is an error rather than a silently
  dropped stage.
  """
  order = list(globals.ABSTRACTION_ROUTES)
  unknown = [n for n in order if n not in ABSTRACTION_STAGES]
  if unknown:
    raise ValueError("globals.ABSTRACTION_ROUTES names %s; the stages are %s"
                     % (", ".join(unknown), ", ".join(ABSTRACTION_STAGES)))
  return order


def route_enabled(name):
  import solve
  if solve.in_critic_rerun:
    # The rerun is a retranslation: Stage 2 again, the converter, gk.  Running
    # the routes inside it would run them twice per case — once on the
    # repaired translation and once on the original, in the outer run.
    return False
  if name == "graphtrans":
    return bool(globals.options.get("graphtrans_flag")
                or globals.options.get("graphbridge_flag"))
  if name == "litbridge":
    return bool(globals.options.get("litbridge_flag"))
  if name == "graphbridge":
    return bool(globals.options.get("graphbridge_flag"))
  return False


def run_stage(name, enabled, answer, rows, run, adopt=None, announce=None,
              on_error=None, tag=None, disabled_why="off"):
  """Run one retry stage under the pipeline's rules, and say what came of it.

  This is the whole control flow, in one place, so the pipeline and the tests
  exercise the same implementation rather than two loops that can drift:

    * a disabled stage does not run and says so;
    * an enabled stage runs only while the question is unresolved;
    * an exception becomes a recorded error and the run continues;
    * `None`, empty output, `Unknown`, `no answer` and every `Error:` value
      leave the question unresolved;
    * an earlier definite answer is never replaced.

  Returns (answer, answered_by_or_None).  `adopt(got)` runs only when the
  stage's answer is definite and is where a stage does its own bookkeeping.
  """
  import solve
  if not enabled:
    note_stage(rows, name, False, why=disabled_why)
    return answer, None
  if not unresolved(answer):
    note_stage(rows, name, False,
                why="not needed: the question was already answered")
    return answer, None
  if announce:
    announce(name)
  ctx = contextlib.ExitStack()
  with ctx:
    if tag is not None:
      ctx.enter_context(llmcall.tagged(tag))
    ctx.enter_context(prover.stage(name))
    got, err = guarded(name, rows, run)
  if err and on_error:
    on_error(err)
  note_stage(rows, name, True, (got or {}).get("answer"), error=err,
              theory=(got or {}).get("logic"),
              provider=solve.llm, version=solve.llm_version)
  if err or not got:
    return answer, None
  got_answer = got.get("answer")
  if got_answer is None or unresolved(got_answer):
    return answer, None
  if adopt:
    adopt(got)
  return got_answer, name



def guarded(name, rows, fn, *a, **kw):
  """Run one stage.  An exception becomes a recorded error on that stage's row
  and the run continues with the next enabled stage; it never aborts the case
  and never becomes an answer."""
  try:
    return fn(*a, **kw), None
  except KeyboardInterrupt:
    raise
  except Exception as exc:
    return None, "Error: %s: %s" % (type(exc).__name__, str(exc)[:160])


def note_stage(rows, name, ran, answer=None, why=None, enabled=None,
               error=None, theory=None, provider=None, version=None):
  """Record what one stage did, for the stages block and the case record.

  One row per stage, whether or not it ran, so a results folder says what the
  run tried without its command line.  `answered` is set later, once the run
  knows which stage produced the final answer.
  """
  row = {"stage": name, "ran": bool(ran), "answered": False,
         "enabled": bool(ran) if enabled is None else bool(enabled),
         "answer": None, "error": None, "why": None,
         "theory_sha256": _theory_sha(theory),
         "gk_calls": 0, "gk_seconds": 0.0,
         "llm_calls": 0, "llm_seconds": 0.0, "llm_allowed": 0,
         "llm_cached": 0, "llm_live": 0, "llm_refused": 0,
         "llm_provider_requests": 0,
         "provider": provider, "version": version, "acceptance": None}
  head = str(answer or "").split("\n")[0].strip()
  if ran:
    row["answer"] = head or None
    if error is None and is_error(answer):
      error = head
  if error:
    row["error"] = str(error).split("\n")[0][:200]
  if not ran and why:
    row["why"] = why
  rows.append(row)
  return row


def _theory_sha(logic):
  """An immutable reference to the theory a stage submitted."""
  if not logic:
    return None
  try:
    import hashlib
    return hashlib.sha256(
      json.dumps(logic, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:16]
  except Exception:                                              # pragma: no cover
    return None


def complete_stage_rows(rows, answered_by, collect=None):
  """One ordered row per stage in `PIPELINE_ORDER`, whether or not it ran.

  A stage that never reached its call site still gets a row saying it was off
  or not needed, so a case record can be read without the command line.  The
  per-stage gk and LLM accounting is attached here, from the tagged call log.
  """
  seen = {}
  for r in rows:
    seen.setdefault(r["stage"], r)
  out = []
  for name in PIPELINE_ORDER:
    row = seen.get(name)
    if row is None:
      on = (name == "front_door") or bool(
        globals.options.get(name + "_flag"))
      row = {"stage": name, "ran": False, "answered": False, "enabled": on,
             "answer": None, "error": None,
             "why": ("off" if not on else
                     "not needed: an earlier stage answered"),
             "theory_sha256": None, "gk_calls": 0, "gk_seconds": 0.0,
             "llm_calls": 0, "llm_seconds": 0.0, "llm_allowed": 0,
             "llm_cached": 0, "llm_live": 0, "llm_refused": 0,
             "llm_provider_requests": 0, "provider": None,
             "version": None, "acceptance": None}
    # `enabled` comes from the resolved options, not from whether the stage
    # happened to run: a stage skipped because an earlier one answered is still
    # an enabled stage.
    row["enabled"] = (True if name == "front_door"
                      else bool(globals.options.get(name + "_flag")))
    if not row["ran"] and not row.get("why"):
      row["why"] = ("off" if not row["enabled"]
                    else "not needed: an earlier stage answered")
    if not row["ran"] and row["enabled"] and row.get("why") == "off":
      # the stage is on; something other than the flag stopped it
      row["why"] = "not needed: the stage was already used in this run"
    row["answered"] = bool(row["ran"] and name == answered_by)
    out.append(row)
  attach_call_accounting(out, collect)
  return out


def attach_call_accounting(rows, collect):
  """Per-stage LLM and gk counts, provider and version, from the call log.

  Only the calls of the attempt these rows describe are counted: the
  downstream-error retry runs the whole pipeline again, and the call log keeps
  growing across attempts.
  """
  import solve
  by = {r["stage"]: r for r in rows}
  try:
    log = list(llmcall.call_log)[solve.call_log_mark:]
  except Exception:                                              # pragma: no cover
    log = []
  for entry in log:
    # `tagged` labels each call with the stage that made it; an untagged call
    # is the initial attempt's own parse.
    stage = entry.get("tag") or "front_door"
    if stage in ("untagged", "stage1", "stage2", "parse", "prenorm"):
      stage = "front_door"
    row = by.get(stage)
    if row is None:
      continue
    row["llm_seconds"] = round(
      row["llm_seconds"] + float(entry.get("seconds") or 0), 3)
    source = entry.get("source")
    # Every provider attempt is one log entry; only the first of a logical call
    # has `logical`, so an empty-response retry adds provider requests and not
    # a second logical call.  `requests` counts the attempt's outbound requests,
    # its HTTP retries and a Gemini context-cache creation included.
    if source == "api":
      row["llm_provider_requests"] = row.get("llm_provider_requests", 0) + int(entry.get("requests", 1))
    if not entry.get("logical"):
      continue
    row["llm_calls"] += 1              # attempted: allowed + refused
    if source == "cache":
      row["llm_cached"] = row.get("llm_cached", 0) + 1
      row["llm_allowed"] = row.get("llm_allowed", 0) + 1
    elif source == "refused":
      # refused before the cache lookup and before any dispatch: never live
      row["llm_refused"] = row.get("llm_refused", 0) + 1
    else:
      row["llm_live"] = row.get("llm_live", 0) + 1
      row["llm_allowed"] = row.get("llm_allowed", 0) + 1
    for a, b in (("input", "input_tokens"), ("output", "output_tokens")):
      if entry.get(a) is not None:
        row[b] = row.get(b, 0) + int(entry[a] or 0)
    if entry.get("reason"):
      row["error"] = row.get("error") or ("Error: %s" % entry["reason"])
    if entry.get("llm"):
      row["provider"] = entry["llm"]
    if entry.get("version"):
      row["version"] = entry["version"]
  for g in (collect or {}).get("gk_calls") or []:
    stage = g.get("stage") or "front_door"
    row = by.get(stage)
    if row is None:
      continue
    row["gk_calls"] += 1
    row["gk_seconds"] = round(row["gk_seconds"] + float(g.get("seconds") or 0), 3)
  for rec in (collect or {}).get("acceptance") or []:
    row = by.get(rec.get("answering_stage"))
    if row is not None:
      row["acceptance"] = {k: rec[k] for k in ("decision", "reasons", "policy")
                           if k in rec}
  return rows


def run_outcome(answer, rows, answered_by):
  """Which of the four outcomes this run reached.

  `Unknown` after every enabled stage ran is not the same as `Unknown` because
  a later stage failed, and neither is a translation failure before a valid gk
  question existed.
  """
  if not unresolved(answer):
    return "answered"
  ran = [r for r in rows if r["ran"]]
  front = next((r for r in rows if r["stage"] == "front_door"), None)
  if front is not None and front.get("error"):
    return "translation_failure"
  if any(r.get("error") for r in ran):
    return "unknown_after_stage_failure"
  return "unknown_all_stages_ran"


# Everything a stage can hand back that is not a definite answer.  An error is
# never an answer and never a correct abstention: it means the stage failed.
_NON_ANSWERS = ("unknown", "no answer", "none", "n/a")


def unresolved(answer):
  """The question is still open, so a later stage is worth running.

  `None`, empty output, `Unknown.`, `no answer`, and every `Error:` value.  The
  error case follows litbridge_procedure.FRONT_DOOR_POLICY: an error is not a
  definite answer.
  """
  if answer is None:
    return True
  head = str(answer).split("\n", 1)[0].strip()
  if not head:
    return True
  low = head.lower().rstrip(".").strip()
  return (low in _NON_ANSWERS or head.lower().startswith("error")
          or low.startswith("unknown"))


def is_error(answer):
  """The value is a stage failure rather than an abstention."""
  if answer is None:
    return False
  return str(answer).split("\n", 1)[0].strip().lower().startswith("error")


def set_answering_call(collect, answering, front_door_proof,
                       front_door_gk_command):
  """Put the gk call that produced the answer at the top level of the record.

  `proof` and `gk_command` describe the ANSWERING stage's call, whichever
  stage that was.  When a stage after the initial attempt answered, the front
  door's own call is kept beside them as `front_door_proof` and
  `front_door_gk_command`.  When nothing after the initial attempt answered, the
  initial attempt's call is the top-level one — every `call_prover` writes
  `collect["gk_command"]`, so a stage that RAN without answering would
  otherwise leave its own command there.  `clauses` is untouched: it is the
  initial attempt's clause list at every level.
  """
  if collect is None:
    return
  if answering is not None:
    collect["front_door_proof"] = as_json(front_door_proof)
    collect["front_door_gk_command"] = front_door_gk_command
    collect["proof"] = as_json(answering.get("proof"))
    if answering.get("gk_command"):
      collect["gk_command"] = answering["gk_command"]
  else:
    collect["proof"] = as_json(front_door_proof)
    if front_door_gk_command:
      collect["gk_command"] = front_door_gk_command
  if collect.get("proof") is None:
    collect.pop("proof", None)


def as_json(proof_result):
  """A gk result as a JSON object, so a dump does not drown in escapes.

  Falls back to the raw string when it does not parse (an "Error: …" return),
  and to None when there is nothing.
  """
  if proof_result is None:
    return None
  if isinstance(proof_result, (dict, list)):
    return proof_result
  if not (isinstance(proof_result, str) and proof_result.strip()):
    return None
  try:
    return json.loads(proof_result)
  except Exception:                                             # noqa: BLE001
    return proof_result


def call_counts():
  """Per stage tag: how many LLM calls, how many live, how many were retries.

  `llmcall.call_log` is reset once per case by the runners, so this counts
  this case alone.  The tag is set by `llmcall.tagged` at each call site.
  """
  out = {}
  for row in llmcall.call_log:
    tag = row.get("tag") or "untagged"
    cell = out.setdefault(tag, {"calls": 0, "live": 0, "retries": 0})
    cell["calls"] += 1
    if row.get("source") == "api":
      cell["live"] += 1
    if row.get("retry"):
      cell["retries"] += 1
  return out


def summary_record(answer, answered_by, front_door_answer, state=None,
                   rerun_answered_by=None, stages=None):
  """The one block `-summary` prints, as a dict."""
  counts = call_counts()
  routes = []
  for name in abstraction_order():
    if name == answered_by:
      routes.append("%s (answer found)" % name)
    elif not route_enabled(name):
      routes.append("%s off" % name)
    elif counts.get(name):
      routes.append("%s ran, no answer" % name)
    else:
      routes.append("%s not run" % name)
  return {"answer": str(answer or "").split("\n")[0],
          "answered_by": answered_by,
          "front_door_answer": str(front_door_answer or "").split("\n")[0],
          "abstraction_order": ",".join(abstraction_order()),
          "stages_enabled": stages_enabled(),
          # `LLMPIPE_ABSEXP` is the one control outside the option dict, so a
          # record that did not name it could not be reproduced.  [] is ordinary.
          "encoding_experiments": lc_encoding.active_experiments(),
          "stages": stages or [],
          "rerun_answered_by": rerun_answered_by,
          "llm_call_counts": counts,
          "llm_calls_total": sum(v["calls"] for v in counts.values()),
          "llm_calls_live": sum(v["live"] for v in counts.values()),
          "routes": routes}
