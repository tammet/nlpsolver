#!/usr/bin/env python3

# Batch test runner for the nlpsolver pipeline.
#
# For each [id, input, expected] entry in a test file, runs the pipeline
# under each requested LLM in parallel and writes one JSON file per
# (case, llm) into testresults/<testname>/<llm>/case_NNNN.json.
#
# Resumption: a case is skipped if its output file already exists.  Pass
# -redo-errors to also re-run cases whose JSON contains an "error" key.
#
# Defaults:
#   testfile : tests/tests_core.py  (testname = "core" — taken from filename)
#   llms     : gpt, claude, gemini, deepseek (no UDP)
#   parallel : 4-wide; all requested LLMs for one case run concurrently
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0
#-------------------------------------------------------------------

import os
import sys
import re
import json
import time
import argparse
import datetime
import hashlib
from multiprocessing import Pool, get_context

# ---- defaults ----
DEFAULT_TESTFILE = "tests/tests_core.py"
DEFAULT_LLMS = ["gpt", "claude", "gemini", "deepseek"]
DEFAULT_OUTROOT = "testresults"


# ======== test-file loader ========

def load_tests(path):
  with open(path) as f:
    src = f.read()
  try:
    data = eval(src, {"__builtins__": {}}, {})
  except SyntaxError:
    # Module-style test file (e.g. "tests = [...]" with comments, like the FOLIO
    # subsets): exec the source and pick up the `tests` list.
    ns = {}
    exec(src, {"__builtins__": {}}, ns)
    data = ns.get("tests")
  if not isinstance(data, list):
    raise ValueError(f"{path}: top-level is not a list")
  out = []
  for i, entry in enumerate(data):
    if not isinstance(entry, list) or len(entry) < 3:
      raise ValueError(f"{path} entry #{i}: not a [id, input, expected] triple")
    out.append((entry[0], entry[1], entry[2]))
  return out


def testname_from_path(path):
  """tests/tests_core.py → 'core'.  tests/tests_core_100.py → 'core_100'."""
  base = os.path.basename(path)
  stem = os.path.splitext(base)[0]
  if stem.startswith("tests_"):
    stem = stem[len("tests_"):]
  return stem


def combined_tag(instr_file, examples_file, explicit_tag):
  """Best-effort short label for the combined output dir suffix.
  explicit_tag wins; otherwise derive from the instructions + examples basenames
  (e.g. combined_v2_instructions_full + combined_examples_pure -> 'v2_pure')."""
  if explicit_tag:
    return re.sub(r"[^0-9A-Za-z]+", "_", explicit_tag).strip("_") or "combined"
  def piece(path, strip):
    if not path:
      return ""
    s = os.path.splitext(os.path.basename(path))[0]
    for token in strip:
      s = s.replace(token, "")
    return s.strip("_")
  instr = piece(instr_file, ["combined_", "_instructions_full", "instructions"])
  ex = piece(examples_file, ["combined_examples_", "combined_", "_examples", "examples"])
  parts = [p for p in (instr, ex) if p]
  return "_".join(parts) or "combined"


# ======== worker (runs in a separate process) ========

def _collect_representation(collect):
  """Record which representation ran and what its folds decided.

  Collection only.  It reads state the conversion already left behind and never
  writes any of it back, so the theory, the question, the gk command, the answer
  and every cache key are exactly what they would have been without it.
  """
  try:
    import globals as _g
    import lc_encoding
    enc = lc_encoding.current()
    collect["_representation"] = {
      "event_base": _g.options.get("event_base"),
      "existfold_flag": bool(_g.options.get("existfold_flag")),
      "davidson2_flag": bool(_g.options.get("davidson2_flag")),
      "existfold2_flag": bool(_g.options.get("existfold2_flag")),
      "resolved": {
        "davidson": enc.davidson,
        "davidson2": enc.davidson2,
        "davidson2_not_applicable": enc.davidson2_not_applicable,
        "existfold2": enc.existfold2,
        "flatten": enc.flatten,
        "eventprop": enc.eventprop,
        "needs_coarsen": enc.needs_coarsen,
      },
    }
  except Exception as e:
    collect["_representation"] = {"error": "%s: %s" % (type(e).__name__, e)}
  report = {}
  try:
    import lc_davidson2
    rep = lc_davidson2.report()
    if rep:
      report["davidson2"] = rep
  except Exception:
    pass
  try:
    import lc_existfold_v2
    rep = lc_existfold_v2.report()
    if rep.get("per_key") or rep.get("rewrites"):
      report["existfold2"] = rep
  except Exception:
    pass
  try:
    import lc_existfold
    report["existfold_legacy_fired"] = bool(lc_existfold.any_fired())
  except Exception:
    pass
  if report:
    collect["_conversion_report"] = report


def _worker(args):
  case_id, input_text, expected, llm, run_opts = args
  # Importing inside the worker keeps each process clean of solver-global state.
  sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver"))
  import solve as _solve_mod
  from solve import english_to_answer
  import llmcall
  _solve_mod.llm = llm
  # Per-case latency/token record (llmcall.record_calls switches it off).
  llmcall.reset_call_log()

  # Pop the private version/max_tokens overrides (solve module globals, not option
  # keys) before they reach set_global_options.
  ro = dict(run_opts)
  _ver = ro.pop("_version_override", None)
  _mt = ro.pop("_maxtokens_override", None)
  if _ver:
    _solve_mod.llm_version = _ver
    setattr(llmcall, llm + "version", _ver)   # so version_map records the override
  if _mt:
    _solve_mod.max_tokens = _mt

  collect = {}
  error_payload = None
  # The api_timeout cap (option key) is enforced inside english_to_answer, scoped
  # to the LLM-parse + clause-conversion phase and disarmed before the prover.
  early = None
  try:
    got = english_to_answer(input_text, options=ro, collect=collect)
    # `answered_by` is written by the block that ends a completed run and
    # `stage2` by a parse that produced something, so a run missing both
    # returned before it had anything to reason from: a truncated Stage-1
    # reply whose Stage 2 comes back empty, or the api-timeout cap.  There is
    # no answer to score there, and the case has to be counted as an error
    # rather than stored as a wrong answer.  A run that DID parse and then hit
    # a converter or prover error keeps its message as its answer and is
    # scored, as it is today.
    if ("answered_by" not in collect and "stage2" not in collect
        and isinstance(got, str) and got.startswith("Error")):
      early = got.split("\n", 1)[0]
    _collect_representation(collect)
  except KeyboardInterrupt:
    raise
  except Exception as e:
    import traceback
    error_payload = {
      "exception": type(e).__name__,
      "message": str(e),
      "traceback": traceback.format_exc(limit=8),
    }

  # Capture which model version the chosen LLM actually used.
  version_map = {
    "gpt":      getattr(llmcall, "gptversion", None),
    "claude":   getattr(llmcall, "claudeversion", None),
    "gemini":   getattr(llmcall, "geminiversion", None),
    "deepseek": getattr(llmcall, "deepseekversion", None),
  }
  collect["_llm_version"] = version_map.get(llm)
  if llmcall.call_log:
    collect["_llm_calls"] = list(llmcall.call_log)
  if run_opts.get("combined_flag"):
    collect["combined"] = {
      "instr": run_opts.get("combined_instr_file"),
      "examples": run_opts.get("combined_examples_file"),
      "checklist": run_opts.get("combined_checklist_file"),
    }
  if error_payload is None and early is not None:
    error_payload = {"exception": "PipelineError", "message": early}
  if error_payload is not None:
    collect["_error"] = error_payload
  return (case_id, llm, collect)


# ======== result-matching (reused from test.py) ========

def _import_matcher():
  """Reuse test.py's _result_matches comparator."""
  here = os.path.dirname(os.path.abspath(__file__))
  if here not in sys.path:
    sys.path.insert(0, here)
  import test as _test_mod
  return _test_mod._result_matches


def _import_scoring_policy():
  """Return the machine-readable policy paired with the shared matcher."""
  here = os.path.dirname(os.path.abspath(__file__))
  if here not in sys.path:
    sys.path.insert(0, here)
  import test as _test_mod
  return _test_mod.answer_matching_policy(False)


# ======== solve.py's own flags ========

def _solve_options(extra):
  """Parse the flags the runner does not define with solve.py's own parser.

  `solve._parse_cmd_line` returns only the keys the command line changed, so
  the result merges straight into `run_opts`.  A flag solve.py does not know
  makes it print its help and exit 0; that would look like success here, so it
  is caught and turned into an error.
  """
  if not extra:
    return {}
  import contextlib
  import io
  _solver = os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver")
  if _solver not in sys.path:
    sys.path.insert(0, _solver)
  import solve
  sentinel = "RUNTESTS_SENTINEL_TEXT"
  argv = list(sys.argv)
  said = io.StringIO()
  try:
    sys.argv = ["solve.py"] + list(extra) + [sentinel]
    with contextlib.redirect_stdout(said):    # solve.py prints its whole help
      text, opts = solve._parse_cmd_line()
  except SystemExit:
    raise SystemExit("runtests: %s"
                     % (said.getvalue().split("\n")[0]
                        or "solve.py rejected one of %s" % extra))
  finally:
    sys.argv = argv
  if text.strip() != sentinel:
    raise SystemExit("runtests: %r was read as input text, not as a flag"
                     % text.replace(sentinel, "").strip())
  return opts


# ======== per-case JSON builder ========

def _strip_internal_keys(obj):
  """Recursively drop keys that are pipeline internals (e.g. '_raw',
  injected by rawlogic_convert into stage1 packages).  Returns a new
  structure; does not mutate input."""
  if isinstance(obj, dict):
    return {k: _strip_internal_keys(v) for k, v in obj.items()
            if not (isinstance(k, str) and k.startswith("_"))}
  if isinstance(obj, list):
    return [_strip_internal_keys(x) for x in obj]
  return obj


def build_case_json(testname, case_id, input_text, expected, llm, collect, matcher):
  """Assemble the final per-case dict from the collect dict + meta.

  Keys with empty/null values are omitted.
  - stage1/stage2 have pipeline-internal '_'-prefixed keys stripped.
  - nl_proof is returned as a list of lines (strict-JSON friendly: each
    line lives on its own row of the file, no '\\n' escapes).
  """
  answer = collect.get("answer")
  correctness = None
  if answer is not None and "_error" not in collect:
    try:
      # One-stage (combined-prompt) runs enable the lenient rendering-artefact
      # fallback in the matcher; two-stage runs do not.
      correctness = bool(matcher(expected, answer, input_text,
                                 single_stage=bool(collect.get("combined"))))
    except Exception:
      correctness = None

  out = {
    "test_name": testname,
    "case_id": case_id,
    "input_text": input_text,
    "expected_answer": expected,
    "llm_name": llm,
    "llm_version": collect.get("_llm_version"),
    "scoring_policy": _import_scoring_policy(),
  }
  if collect.get("_llm_calls"):
    out["llm_calls"] = collect["_llm_calls"]
  if answer is not None:
    out["answer"] = answer
  if correctness is not None:
    out["correctness"] = correctness
  for k in ("combined", "directanswer",
            "stage1", "stage_1_fixes", "stage_1_retries",
            "stage2", "stage_2_fixes", "stage_2_retries",
            "clauses", "final_clauses", "final_clause_trace",
            "final_clause_trace_error",
            "gk_command", "proof", "nl_proof",
            "front_door_proof", "front_door_gk_command",
            "downstream_retries",
            # which stage answered, what it cost, and what each route did
            "answered_by", "front_door_answer", "abstraction_order",
            "stages_enabled", "stages", "encoding_experiments",
            "llm_call_counts", "llm_calls_total",
            "graphtrans", "litbridge", "graphbridge", "critic", "fallback",
            # EXPERIMENTAL (Task 2B): one acceptance record per judged stage
            "acceptance",
            # Task 3: the resolved configuration and which of the four
            # outcomes the run reached
            "pipeline_name", "run_outcome",
            # Task 4: the case-level LLM accounting vocabulary
            "llm_accounting", "llm_accounting_stages"):
    v = collect.get(k)
    if not v:   # skip None/[]/'' — omit empty keys
      continue
    if k in ("stage1", "stage2", "clauses", "final_clauses"):
      v = _strip_internal_keys(v)
    elif k == "nl_proof" and isinstance(v, str):
      v = v.split("\n")
    out[k] = v
  # ---- collection only: what representation ran, what it did, what gk cost ----
  # Read after the run has closed.  None of it reaches the theory, the question,
  # the gk command, the answer selection or a cache key.
  rep = collect.get("_representation")
  if rep:
    out["representation"] = rep
  conv = collect.get("_conversion_report")
  if conv:
    out["conversion_report"] = conv
  if collect.get("gk_calls"):
    out["gk_calls"] = collect["gk_calls"]
    out["gk_seconds_total"] = round(
      sum(g.get("seconds") or 0 for g in collect["gk_calls"]), 3)
    out["input_clauses"] = collect["gk_calls"][-1].get("input_clauses")
  # GK may retain a below-reporting-threshold evidence trace even when the
  # user-facing answer is Unknown.  That trace is useful diagnostics, but it
  # is not a proof the pipeline accepted and must not enter proof-length
  # comparisons.
  pl = _proof_length(out.get("proof")) if _answer_is_definite(out.get("answer")) else None
  if pl is not None:
    out["proof_length"] = pl

  if "_error" in collect:
    out["error"] = collect["_error"]
  out["timestamp"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
  return out


def _proof_length(proof):
  """Derived clauses in a proof, excluding input clauses (the paper's count)."""
  if not isinstance(proof, dict):
    return None
  best = None
  for a in proof.get("answers") or []:
    for key in ("positive proof", "negative proof", "proof"):
      steps = a.get(key)
      if not steps:
        continue
      derived = 0
      for st in steps:
        rule = st[1] if isinstance(st, list) and len(st) > 1 else None
        head = rule[0] if isinstance(rule, list) and rule else None
        if head != "in":
          derived += 1
      best = derived if best is None else min(best, derived)
  return best


def _answer_is_definite(answer):
  """Whether the pipeline exposed a definite answer rather than abstaining."""
  if not isinstance(answer, str) or not answer.strip():
    return False
  s = answer.strip().lower()
  if s.startswith("error"):
    return False
  return not s.startswith(("unknown", "no answer"))


# ======== file IO ========

def case_filename(outdir, case_id):
  return os.path.join(outdir, f"case_{case_id:04d}.json")


def _load_case_file(path):
  """Read a per-case JSON file as a dict."""
  with open(path) as f:
    return json.load(f)


def should_skip(outpath, redo_errors):
  if not os.path.exists(outpath):
    return False
  if not redo_errors:
    return True
  try:
    data = _load_case_file(outpath)
    if "error" in data:
      return False
    # Some failures never set an "error" key: the api-timeout cap and the
    # early returns in english_to_answer put their message in "answer"
    # instead, so matching only on the key silently skips them.
    answer = data.get("answer")
    if isinstance(answer, str) and answer.startswith("Error"):
      return False
    return True
  except Exception:
    return False   # malformed → re-run


_COMPACT_WIDTH = 100


def _smart_compact(obj):
  """Recursive single-line JSON render: ', ' between elements when the
  list/dict contains compound children, ',' (no space) when it is a
  pure-atom list — matching the -debug style.  Strict valid JSON."""
  if obj is True:  return "true"
  if obj is False: return "false"
  if obj is None:  return "null"
  if isinstance(obj, (int, float)):
    return json.dumps(obj)
  if isinstance(obj, str):
    return json.dumps(obj, ensure_ascii=False)
  if isinstance(obj, list):
    sep = ", " if any(isinstance(x, (list, dict)) for x in obj) else ","
    return "[" + sep.join(_smart_compact(x) for x in obj) + "]"
  if isinstance(obj, dict):
    return ("{" + ", ".join(json.dumps(str(k), ensure_ascii=False) + ": "
                             + _smart_compact(v) for k, v in obj.items()) + "}")
  return json.dumps(obj)


# Stage-2 / formula-level connectives.  Lists whose first element is one
# of these are COMPOUND formulas (sub-elements are sub-formulas) and must
# be allowed to expand.  Everything else with a string head is a literal.
_CONNECTIVES = frozenset({
  "and", "or", "not", "implies", "iff", "xor",
  "holds", "normally", "exists", "forall",
  "@id", "@time", "@p", "@question",
  "ask", "question",
})


def _is_literal(obj):
  """A 'literal' = a list that is never broken across lines.  Covers:
    - logical atoms: list whose first element is a string predicate name
      (NOT a logical connective), e.g. ['isa','elephant','X'] or
      ['-has degree property',..., ['$ctxt',...]]
    - proof steps: list whose first element is an integer (step number),
      e.g. [1, ['in','sent_S1','assumption',1], [['-isa',...]]]
  Connectives ('and', 'or', '@id', 'holds', 'exists', ...) are NOT
  literals — their sub-formulas may need expansion."""
  if not isinstance(obj, list) or not obj:
    return False
  head = obj[0]
  if isinstance(head, str):
    return head not in _CONNECTIVES
  if isinstance(head, bool):
    return False
  if isinstance(head, int):
    return True
  return False


def _fmt_value_b(obj, col):
  """Format obj at column `col` using Style B.

  Compact when it fits in _COMPACT_WIDTH at this column.  Literals are
  always compact (no break).  Other lists/dicts use Style B: first
  element after [/{, subsequent at col+1; closing ] at col, closing }
  on the last key's line."""
  compact = _smart_compact(obj)
  if col + len(compact) <= _COMPACT_WIDTH:
    return compact
  if _is_literal(obj):
    return compact   # rule: literals never break
  if isinstance(obj, list):
    return _fmt_list_b(obj, col)
  if isinstance(obj, dict):
    return _fmt_dict_b(obj, col)
  return compact   # very long scalar — accept as is


def _fmt_list_b(obj, col):
  """Style B list expansion at col: first elem right after [, subsequent
  aligned at col+1, closing ] at col."""
  if not obj:
    return "[]"
  child_col = col + 1
  child_ind = " " * child_col
  close_ind = " " * col
  rendered = [_fmt_value_b(x, child_col) for x in obj]
  if len(rendered) == 1:
    return "[" + rendered[0] + "]"
  return ("[" + rendered[0] + ",\n"
          + ",\n".join(child_ind + s for s in rendered[1:])
          + "\n" + close_ind + "]")


def _fmt_dict_b(obj, col):
  """Style B dict at col: first key right after {, subsequent at col+1.
  Closing } sits on the last key's line (no separate line)."""
  if not obj:
    return "{}"
  pairs = list(obj.items())
  child_col = col + 1
  child_ind = " " * child_col
  rendered = []
  for k, v in pairs:
    key_str = json.dumps(str(k), ensure_ascii=False)
    val_col = child_col + len(key_str) + 2  # account for ": "
    rendered.append(key_str + ": " + _fmt_value_b(v, val_col))
  if len(rendered) == 1:
    return "{" + rendered[0] + "}"
  return ("{" + rendered[0] + ",\n"
          + ",\n".join(child_ind + s for s in rendered[1:])
          + "}")


def _fmt_clauses_field(obj):
  """Format the 'clauses' field: each clause-dict opens at column 0
  (the col-0 rule), Style B inside each clause."""
  if not isinstance(obj, list) or not obj:
    return _smart_compact(obj)
  rendered = []
  for clause in obj:
    if isinstance(clause, dict):
      rendered.append(_fmt_dict_b(clause, 0))
    else:
      rendered.append(_smart_compact(clause))
  return "[\n" + ",\n".join(rendered) + "\n]"


def _fmt_nl_proof_field(obj):
  """Format 'nl_proof' (list of line-strings): each on its own row at
  column 0; closing ] at column 0."""
  if not isinstance(obj, list) or not obj:
    return _smart_compact(obj)
  return "[\n" + ",\n".join(_smart_compact(x) for x in obj) + "\n]"


def _fmt_depth(obj, depth):
  """Depth-based formatter for stage1, stage2, proof — 2 spaces per
  nesting level.  Layout rules:
    - Compact when it fits in _COMPACT_WIDTH at this column.
    - Literals (list-with-string-pred-first, int-first) never break.
    - Lists with mixed atoms+compounds: atom 'streak' stays on the
      opening-bracket line (e.g. `['holds','W0',`); the first compound
      child breaks to a new line at depth+1; subsequent children
      (compound OR atom) at depth+1.  Closing ']' at depth.
    - Dicts: each key on its own line at depth+1, value rendered
      at depth+1.
  """
  compact = _smart_compact(obj)
  if depth * 2 + len(compact) <= _COMPACT_WIDTH:
    return compact
  if _is_literal(obj):
    return compact
  ind  = "  " * depth
  ind1 = "  " * (depth + 1)
  if isinstance(obj, list):
    if not obj:
      return "[]"
    parts = ["["]
    expanded = False
    for i, child in enumerate(obj):
      is_compound = isinstance(child, (list, dict))
      if i == 0:
        if is_compound:
          parts.append(_fmt_depth(child, depth + 1))
          expanded = True
        else:
          parts.append(_smart_compact(child))
      else:
        if is_compound:
          parts.append(",\n" + ind1 + _fmt_depth(child, depth + 1))
          expanded = True
        elif expanded:
          parts.append(",\n" + ind1 + _smart_compact(child))
        else:
          parts.append("," + _smart_compact(child))
    parts.append("\n" + ind + "]")
    return "".join(parts)
  if isinstance(obj, dict):
    if not obj:
      return "{}"
    items = [ind1 + json.dumps(str(k), ensure_ascii=False) + ": "
             + _fmt_depth(v, depth + 1) for k, v in obj.items()]
    return "{\n" + ",\n".join(items) + "\n" + ind + "}"
  return compact


def smart_json(obj):
  """Top-level formatter for the case dict.

  Each top-level key sits at column 2.  Per-field formatting:
    - clauses : col-0 list (each clause-dict opens at col 0,
                Style B inside, literals never break)
    - nl_proof : list of line-strings, each at col 0
    - stage1, stage2, proof, others : depth-based
    - scalars / short values : compact on the same line
  """
  if not isinstance(obj, dict):
    return _fmt_depth(obj, 0)
  parts = []
  for k, v in obj.items():
    key_str = json.dumps(str(k), ensure_ascii=False)
    val_compact = _smart_compact(v)
    val_col = 2 + len(key_str) + 2
    if val_col + len(val_compact) <= _COMPACT_WIDTH:
      val_str = val_compact
    elif k in ("clauses", "final_clauses"):
      val_str = _fmt_clauses_field(v)
    elif k == "nl_proof":
      val_str = _fmt_nl_proof_field(v)
    else:
      val_str = _fmt_depth(v, 1)
    parts.append("  " + key_str + ": " + val_str)
  return "{\n" + ",\n".join(parts) + "\n}"


def case_filename(outdir, case_id):
  return os.path.join(outdir, f"case_{case_id:04d}.json")


def write_case_file(outpath, payload):
  """Write payload as strict JSON using the smart depth-based formatter.
  Atom lists stay compact; compound lists/dicts expand with consistent
  2-space-per-depth indent.  Round-trips through json.loads."""
  os.makedirs(os.path.dirname(outpath), exist_ok=True)
  tmp = outpath + ".tmp"
  with open(tmp, "w") as f:
    f.write(smart_json(payload))
    f.write("\n")
  os.replace(tmp, outpath)


def pipeline_git_state():
  """Pipeline provenance for summary.json: commit hash, dirty flag (tracked
  files only — the working tree always carries untracked scratch), and any
  tags pointing at the commit.  Returns None when git is unavailable."""
  import subprocess
  here = os.path.dirname(os.path.abspath(__file__))
  def run(args):
    try:
      return subprocess.run(["git"] + args, cwd=here, capture_output=True,
                            text=True, timeout=10).stdout.strip()
    except Exception:
      return ""
  commit = run(["rev-parse", "HEAD"])
  if not commit:
    return None
  diff = run(["diff", "--binary", "HEAD"])
  return {
    "commit": commit,
    "dirty": bool(diff),
    "tracked_diff_sha256": (hashlib.sha256(diff.encode("utf-8")).hexdigest()
                             if diff else None),
    "tags": run(["tag", "--points-at", "HEAD"]).split(),
  }


# Computed once in main(); embedded in every summary.json the run writes.
_pipeline_git = None

RUN_MANIFEST_SCHEMA_VERSION = 1


def _jsonable(value):
  """Convert resolved option values to stable JSON-compatible data."""
  if isinstance(value, dict):
    return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
  if isinstance(value, (set, frozenset)):
    return sorted((_jsonable(v) for v in value), key=lambda v: repr(v))
  if isinstance(value, (list, tuple)):
    return [_jsonable(v) for v in value]
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  return repr(value)


def _file_sha256(path):
  with open(path, "rb") as f:
    return hashlib.sha256(f.read()).hexdigest()


def _provider_versions(llms, override=None):
  """Resolve the model version recorded for each requested provider."""
  here = os.path.dirname(os.path.abspath(__file__))
  solver_dir = os.path.join(here, "solver")
  if solver_dir not in sys.path:
    sys.path.insert(0, solver_dir)
  import llmcall
  return {name: (override or getattr(llmcall, name + "version", None))
          for name in llms}


def _manifest_identity(testfile, testname, run_opts, scoring_policy,
                       sequential=False):
  """Fields that must not be mixed in one result directory."""
  options = dict(run_opts)
  options.pop("_version_override", None)
  git_identity = None
  if _pipeline_git:
    git_identity = {k: _pipeline_git.get(k) for k in
                    ("commit", "dirty", "tracked_diff_sha256")}
  return {
    "test_name": testname,
    "test_file": os.path.realpath(testfile),
    "test_file_sha256": _file_sha256(testfile),
    "pipeline_git": _jsonable(git_identity),
    "resolved_options": _jsonable(options),
    "scoring_policy": _jsonable(scoring_policy),
    "execution_mode": "sequential" if sequential else "parallel_by_provider",
  }


def _manifest_path(outroot):
  return os.path.join(outroot, "run_manifest.json")


def _write_json_atomic(path, payload):
  os.makedirs(os.path.dirname(path), exist_ok=True)
  tmp = path + ".tmp"
  with open(tmp, "w") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False, sort_keys=True)
    f.write("\n")
  os.replace(tmp, path)


def _has_case_records(outroot):
  if not os.path.isdir(outroot):
    return False
  for _root, _dirs, files in os.walk(outroot):
    if any(fn.startswith("case_") and fn.endswith(".json") for fn in files):
      return True
  return False


def prepare_run_manifest(outroot, identity, providers, invocation):
  """Create/update the manifest, refusing incompatible result reuse.

  Subsets may be added in later invocations. The test source, code state,
  resolved pipeline options, scoring policy and each provider's version may
  not change inside one result directory.
  """
  path = _manifest_path(outroot)
  existing = None
  if os.path.exists(path):
    try:
      with open(path) as f:
        existing = json.load(f)
    except Exception as e:
      raise SystemExit(f"runtests: cannot read existing manifest {path}: {e}")
  elif _has_case_records(outroot):
    raise SystemExit(
      "runtests: result directory already contains case files but no "
      f"run_manifest.json: {outroot}\nUse -tag or -out to select a new "
      "directory; refusing to mix an unidentified earlier configuration.")

  if existing is None:
    manifest = {
      "schema_version": RUN_MANIFEST_SCHEMA_VERSION,
      "identity": _jsonable(identity),
      "providers": _jsonable(providers),
      "invocations": [],
    }
  else:
    if existing.get("schema_version") != RUN_MANIFEST_SCHEMA_VERSION:
      raise SystemExit(f"runtests: unsupported manifest schema in {path}")
    if existing.get("identity") != _jsonable(identity):
      raise SystemExit(
        "runtests: result directory belongs to a different test, code state, "
        f"pipeline configuration, or scoring policy: {outroot}\n"
        "Use -tag or -out to select a new directory.")
    manifest = existing
    known = manifest.setdefault("providers", {})
    for provider, version in providers.items():
      if provider in known and known[provider] != version:
        raise SystemExit(
          f"runtests: {outroot} records {provider} version {known[provider]!r}, "
          f"not {version!r}. Use -tag or -out to select a new directory.")
      known[provider] = version

  manifest.setdefault("invocations", []).append(_jsonable(invocation))
  _write_json_atomic(path, manifest)
  return manifest


def update_summary(outdir, llm):
  """Scan the LLM's output dir, rebuild summary.json from per-case .py files."""
  if not os.path.isdir(outdir):
    return
  passed = failed = errored = 0
  by_case = []
  answered_by = {}
  calls = {}
  calls_total = calls_live = 0
  model_versions = set()
  scoring_policies = []
  for fn in sorted(os.listdir(outdir)):
    if not fn.startswith("case_") or not fn.endswith(".json"):
      continue
    p = os.path.join(outdir, fn)
    try:
      d = _load_case_file(p)
    except Exception:
      continue
    cid = d.get("case_id")
    if d.get("llm_version") is not None:
      model_versions.add(d.get("llm_version"))
    policy = d.get("scoring_policy")
    if policy is not None and policy not in scoring_policies:
      scoring_policies.append(policy)
    # who answered, and what the case cost in LLM calls, per stage
    who = d.get("answered_by")
    if who:
      answered_by[who] = answered_by.get(who, 0) + 1
    for tag, cell in (d.get("llm_call_counts") or {}).items():
      got = calls.setdefault(tag, {"calls": 0, "live": 0, "retries": 0})
      for k in got:
        got[k] += cell.get(k) or 0
      calls_total += cell.get("calls") or 0
      calls_live += cell.get("live") or 0
    if "error" in d:
      errored += 1
      by_case.append({"case_id": cid, "status": "error"})
    elif d.get("correctness") is True:
      passed += 1
    else:
      failed += 1
      by_case.append({"case_id": cid, "status": "fail",
                      "expected": d.get("expected_answer"),
                      "got":      d.get("answer")})
  summary = {
    "llm_name": llm,
    "total":   passed + failed + errored,
    "passed":  passed,
    "failed":  failed,
    "errored": errored,
    "failed_or_errored": by_case,
    "answered_by": answered_by,
    "llm_call_counts": calls,
    "llm_calls_total": calls_total,
    "llm_calls_live": calls_live,
    "model_versions": sorted(model_versions),
    "scoring_policies": scoring_policies,
    "updated": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
  }
  if _pipeline_git:
    summary["pipeline_git"] = _pipeline_git
  with open(os.path.join(outdir, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)


def update_combined_summary(outroot, testname, providers):
  """Write one cross-provider summary beside the provider directories."""
  rows = []
  case_status = {}
  for provider in sorted(providers):
    summary_path = os.path.join(outroot, provider, "summary.json")
    try:
      with open(summary_path) as f:
        summary = json.load(f)
    except Exception:
      continue
    total = int(summary.get("total") or 0)
    passed = int(summary.get("passed") or 0)
    failed = int(summary.get("failed") or 0)
    errored = int(summary.get("errored") or 0)
    rows.append({
      "provider": provider,
      "model_versions": summary.get("model_versions") or [],
      "total": total,
      "passed": passed,
      "failed": failed,
      "errored": errored,
      "accuracy": (round(passed / total, 6) if total else None),
      "answered_by": summary.get("answered_by") or {},
      "llm_calls_total": int(summary.get("llm_calls_total") or 0),
      "llm_calls_live": int(summary.get("llm_calls_live") or 0),
    })
    provider_dir = os.path.join(outroot, provider)
    for fn in (os.listdir(provider_dir) if os.path.isdir(provider_dir) else []):
      if not (fn.startswith("case_") and fn.endswith(".json")):
        continue
      try:
        with open(os.path.join(provider_dir, fn)) as f:
          case = json.load(f)
      except Exception:
        continue
      cid = str(case.get("case_id"))
      status = ("error" if "error" in case else
                "correct" if case.get("correctness") is True else "wrong")
      case_status.setdefault(cid, {})[provider] = status

  requested = sorted(providers)
  complete = {cid: statuses for cid, statuses in case_status.items()
              if all(p in statuses for p in requested)}
  correct_count_distribution = {}
  all_correct = any_correct = none_correct = mixed = 0
  for statuses in complete.values():
    n = sum(1 for p in requested if statuses[p] == "correct")
    correct_count_distribution[str(n)] = correct_count_distribution.get(str(n), 0) + 1
    if n == len(requested):
      all_correct += 1
    if n:
      any_correct += 1
    else:
      none_correct += 1
    if 0 < n < len(requested):
      mixed += 1

  combined = {
    "schema_version": 1,
    "test_name": testname,
    "providers_requested": requested,
    "providers_with_results": [row["provider"] for row in rows],
    "provider_results": rows,
    "cross_provider_cases": {
      "cases_seen": len(case_status),
      "complete_for_all_requested_providers": len(complete),
      "all_providers_correct": all_correct,
      "at_least_one_provider_correct": any_correct,
      "no_provider_correct": none_correct,
      "mixed_correctness": mixed,
      "by_number_of_correct_providers": correct_count_distribution,
    },
    "scoring_policy": _import_scoring_policy(),
    "pipeline_git": _pipeline_git,
    "updated": datetime.datetime.now(datetime.timezone.utc).replace(
      microsecond=0).isoformat().replace("+00:00", "Z"),
  }
  _write_json_atomic(os.path.join(outroot, "summary.json"), combined)
  return combined


# ======== main loop ========

def make_parser():
  """The runner's own command-line parser.

  Split out of `main` so the option resolution can be exercised without running
  a batch.  It defines exactly the same flags `main` always defined.
  """
  ap = argparse.ArgumentParser(
    description=("Research evaluation and record-generation runner for nlpsolver. "
                 "Running with no arguments prints this help; name a test file "
                 "explicitly to start a potentially paid run."),
    epilog="Each result directory gets a run_manifest.json; incompatible test, "
           "code, option, scoring, or model-version reuse is refused. A combined "
           "cross-provider summary is written at its top level. Any key this "
           "runner does not define is forwarded to solve.py's "
           "own parser, so -pipeline, the single stage switches and their "
           "cancels work here too. Reference: docs/reference/command-line.md "
           "and docs/reference/experimental-options.md.",
    formatter_class=argparse.RawDescriptionHelpFormatter)
  common = ap.add_argument_group("common")
  advanced = ap.add_argument_group("advanced")
  experimental = ap.add_argument_group("experimental and legacy")
  common.add_argument("testfile", nargs="?", default=DEFAULT_TESTFILE,
                  help=f"Test file (default: {DEFAULT_TESTFILE})")
  common.add_argument("-llms", default=",".join(DEFAULT_LLMS),
                  help=f"Comma-separated LLMs to run (default: {','.join(DEFAULT_LLMS)})")
  common.add_argument("-out", default=DEFAULT_OUTROOT,
                  help=f"Output root directory (default: {DEFAULT_OUTROOT})")
  common.add_argument("-ids", default=None,
                  help="Run only these case ids (comma-separated)")
  common.add_argument("-limit", type=int, default=0,
                  help="Run at most N cases (0=all)")
  common.add_argument("-filter", default=None,
                  help="Only run cases whose input contains this substring")
  common.add_argument("-redo-errors", action="store_true", dest="redo_errors",
                  help="Re-run cases whose existing JSON has an 'error' key")
  common.add_argument("-redo", action="store_true",
                  help="Re-run all cases (overwrite existing JSON files)")
  common.add_argument("-sequential", action="store_true",
                  help="Run the requested LLMs SEQUENTIALLY in-process (no "
                       "parallel Pool). Best for cache-served reruns where the "
                       "LLM calls hit the local SQLite cache.")
  common.add_argument("-version", dest="version", default=None,
                  help="Override the model version for the chosen LLM "
                       "(e.g. claude-opus-4-8). Applies to all -llms in the run.")
  common.add_argument("-tag", dest="tag", default=None,
                  help="General output-dir suffix: results go to testresults/<set>_<tag>/. "
                       "Use to keep a variant (directanswer, ultracoarse, ...) separate.")
  advanced.add_argument("-nogeminicache", action="store_true",
                  help="Disable Gemini context caching (on by default)")
  advanced.add_argument("-llm-call-timeout", dest="llm_call_timeout", type=float,
                  default=None,
                  help="Per-LLM-call deadline in seconds, covering attempts, "
                       "retries and backoff sleeps, for the initial parse and "
                       "every later stage. 0 disables.")
  advanced.add_argument("-llm-call-limit", dest="llm_call_limit", type=int,
                  default=None,
                  help="Total logical LLM calls allowed for one case, counting "
                       "every role and local cache hits. 0 (default) is "
                       "unlimited.")
  advanced.add_argument("-api-timeout", dest="api_timeout", type=int, default=120,
                  help="Hard wall-clock cap (seconds) on the LLM-parse + clause-"
                       "conversion phase of each case; disarmed before the prover "
                       "(gk) and proof post-processing run, so it never clips those. "
                       "A case exceeding it is recorded as an Error and the run "
                       "continues (default 120; 0 disables). Guards against wedged "
                       "LLM calls retrying through their timeouts.")
  advanced.add_argument("-think", dest="think", type=int, default=None,
                  help="Enable extended thinking with this token budget "
                       "(Claude budget_tokens / Gemini thinkingBudget). "
                       "Must be below -maxtokens.")
  advanced.add_argument("-maxtokens", dest="maxtokens", type=int, default=None,
                  help="Override max output tokens (must exceed the -think budget).")
  experimental.add_argument("-geminicache", action="store_true",
                  help="Accepted and ignored: Gemini context caching is on by "
                       "default. Kept so older command lines keep working.")
  experimental.add_argument("-accept", metavar="POLICY", default=None,
                  help="EXPERIMENTAL: proof-local acceptance checks on critic "
                       "and graph answers (permissive|balanced|strict). Off "
                       "unless named; permissive reproduces current behaviour.")
  experimental.add_argument("-combined-instr", dest="combined_instr", default=None,
                  help="Combined single-stage instructions prompt file (enables "
                       "one-call English->logic parsing; results go to a "
                       "<set>_<tag> output dir so they don't clash with two-stage runs)")
  experimental.add_argument("-combined-examples", dest="combined_examples", default=None,
                  help="Combined examples prompt file (optional)")
  experimental.add_argument("-combined-checklist", dest="combined_checklist", default=None,
                  help="Combined checklist prompt file (optional)")
  experimental.add_argument("-combined-tag", dest="combined_tag", default=None,
                  help="Label for the combined output dir suffix; if omitted, "
                       "derived from the prompt filenames")
  experimental.add_argument("-directanswer", dest="directanswer", default=None,
                  help="Direct-answer prompt file: answer each case with ONE LLM "
                       "call (no logic, no prover). Output goes to a <set>_<tag> dir.")
  experimental.add_argument("-prenorm", action="store_true",
                  help="Enable the pre-Stage-1 normalization LLM phase")
  experimental.add_argument("-s2split", action="store_true",
                  help="Run Stage 2 sentence-by-sentence: one Stage-2 LLM call "
                       "per Stage-1 sentence package, outputs joined. Output "
                       "goes to a <set>_s2split dir unless -tag is given.")
  experimental.add_argument("-event",
                  choices=["neodavidson", "davidson", "davidson2", "flat", "flatroles"],
                  default="neodavidson",
                  help="event-encoding base: neodavidson (default) | davidson "
                       "(compact event(V,A,O,E)) | davidson2 (the exact spine "
                       "compression) | flat (is_rel2) | flatroles "
                       "(is_rel2 with eventprop-tagged object)")
  experimental.add_argument("-abstract", action="store_true",
                  help="preset: -event flat + all abstraction buckets + simpleprops + localantonyms")
  experimental.add_argument("-abstract-roles", dest="abstract_roles", action="store_true",
                  help="preset: as -abstract but -event flatroles")
  experimental.add_argument("-abstract-max", dest="abstract_max", action="store_true",
                  help="preset: as -abstract-roles + -prenorm (strongest abstraction)")
  experimental.add_argument("-existfold", action="store_true",
                  help="(L2) fold exists Y.isa(C,Y)&has_part/have(X,Y) into has_property([$has_part/$have,C],X); named-witness bridge")
  # The versioned proof shorteners are attempted by default on the unnamed
  # canonical base.  These flags request or cancel them explicitly.
  experimental.add_argument("-davidson2", action="store_true",
                  help="exact event-spine compression: fold only a reversible "
                       "group, never invent a participant, decline on a flat base")
  experimental.add_argument("-existfold2", action="store_true",
                  help="fold only the bare has-part pattern, only for a class "
                       "with at least four occurrences, class-specific clauses")
  experimental.add_argument("-proofshort2", action="store_true",
                  help="-davidson2 and -existfold2 together")
  experimental.add_argument("-nodavidson2", action="store_true",
                  help="disable davidson2, restoring the canonical neo-Davidsonian spine")
  experimental.add_argument("-noexistfold2", action="store_true",
                  help="disable existfold2")
  experimental.add_argument("-noproofshort2", action="store_true",
                  help="disable both; reproduces the pre-2026-08-26 ordinary theory")
  experimental.add_argument("-noprenorm", dest="noprenorm", action="store_true",
                  help="override: force prenorm OFF even under -abstract-max (prenorm ablation experiment)")
  # Additive abstraction primitives (compose with any -event base).
  experimental.add_argument("-entitymerge", action="store_true", help="proper-noun entity canonicalization + set coreference")
  experimental.add_argument("-typeenrich", action="store_true", help="taxonomy/isa enrichment (all six sub-gates)")
  experimental.add_argument("-typeenrich-gates", dest="typeenrich_gates", default=None,
                  help="restrict typeenrich to a comma list of sub-gates "
                       "(super,gender,nametype,compound,plural,gnoun; -name excludes; all)")
  experimental.add_argument("-guarddrop", action="store_true", help="drop redundant antecedent type guards (needs a fold base)")
  experimental.add_argument("-bridges", action="store_true", help="frame/bridge axioms (needs -event flat/flatroles)")
  experimental.add_argument("-dropdefinites", action="store_true", help="skip $theof1 definite reification (leave as relations)")
  experimental.add_argument("-localantonyms", action="store_true", help="restrict antonym folding to the problem + axiom vocabulary")
  experimental.add_argument("-nocrossstage", action="store_true",
                  help="Disable the ultracoarse cross-stage unsatisfiable-guard "
                       "retry (avoids live corrective LLM calls)")
  return ap

def parse_args(argv=None):
  """Parse `argv` (default sys.argv[1:]) into (args, extra solve.py options)."""
  ap = make_parser()
  args, extra = ap.parse_known_args(argv)
  # `-event neodavidson` names the canonical base outright, which argparse cannot
  # distinguish from the default.  Keep the raw words so the resolution can.
  args._raw_argv = list(sys.argv[1:] if argv is None else argv)
  return args, _solve_options(extra)


def main():
  global _pipeline_git
  if len(sys.argv) == 1:
    print(make_parser().format_help())
    return
  _pipeline_git = pipeline_git_state()
  args, extra_opts = parse_args()

  llms = [s.strip() for s in args.llms.split(",") if s.strip()]
  if not llms:
    print("No LLMs requested.")
    sys.exit(1)

  tests = load_tests(args.testfile)
  testname = testname_from_path(args.testfile)
  # Variant modes suffix the set name so results live beside (not on top of) the
  # plain two-stage testresults/<set>/ data.
  combined_on = bool(args.combined_instr)
  directanswer_on = bool(args.directanswer)
  if combined_on:
    tag = args.tag or combined_tag(args.combined_instr, args.combined_examples, args.combined_tag)
  elif directanswer_on:
    tag = args.tag or "directanswer"
  elif args.s2split:
    tag = args.tag or "s2split"
  else:
    tag = args.tag
  if tag:
    testname = testname + "_" + re.sub(r"[^0-9A-Za-z]+", "_", tag).strip("_")
  print(f"Loaded {len(tests)} cases from {args.testfile} (testname={testname})")
  print(f"LLMs: {llms}")
  if combined_on:
    print(f"Combined single-stage: instr={args.combined_instr} "
          f"examples={args.combined_examples} checklist={args.combined_checklist}")
  print(f"Output: {os.path.join(args.out, testname)}/<llm>/case_NNNN.json")

  # ID / limit / filter selection
  if args.ids:
    wanted_ids = {int(s) for s in args.ids.split(",") if s.strip()}
    tests = [t for t in tests if t[0] in wanted_ids]
  if args.filter:
    tests = [t for t in tests if args.filter in t[1]]
  if args.limit:
    tests = tests[:args.limit]
  print(f"Selected: {len(tests)} cases")

  matcher = _import_matcher()

  # Solver options — keep cache on per project rules.
  run_opts = build_run_options(args, extra_opts)
  scoring_policy = _import_scoring_policy()

  # One output directory may hold several subsets and providers, but it may
  # never mix test content, source state, pipeline options, scoring policies or
  # two versions of the same provider.
  outroot = os.path.join(args.out, testname)
  versions = _provider_versions(llms, args.version)
  identity = _manifest_identity(args.testfile, testname, run_opts,
                                scoring_policy, sequential=args.sequential)
  invocation = {
    "timestamp": datetime.datetime.now(datetime.timezone.utc).replace(
      microsecond=0).isoformat().replace("+00:00", "Z"),
    "argv": list(sys.argv[1:]),
    "case_ids": [t[0] for t in tests],
    "case_count": len(tests),
    "providers": llms,
    "sequential": bool(args.sequential),
    "redo": bool(args.redo),
    "redo_errors": bool(args.redo_errors),
  }
  manifest = prepare_run_manifest(outroot, identity, versions, invocation)
  for llm in llms:
    os.makedirs(os.path.join(outroot, llm), exist_ok=True)
  print(f"Manifest: {_manifest_path(outroot)}")

  # Per-case parallel: one worker per (case, llm).  Pool size = len(llms).
  return _run_batch(args, llms, tests, testname, outroot, run_opts, matcher,
                    manifest)


def build_run_options(args, extra_opts):
  """The solver options one parsed command line resolves to.

  Every option the runner sets goes through here, so a test can ask what a
  command line resolves to without running anything.
  """
  combined_on = bool(args.combined_instr)
  directanswer_on = bool(args.directanswer)
  run_opts = {}
  if args.nogeminicache:
    run_opts["use_gemini_cache_flag"] = False
  # `is not None`, not truthiness: an explicit `-llm-call-timeout 0` disables
  # the deadline and must not fall back to the 240s default.
  if getattr(args, "llm_call_timeout", None) is not None:
    run_opts["llm_call_timeout"] = args.llm_call_timeout
  if getattr(args, "llm_call_limit", None) is not None:
    run_opts["llm_call_limit"] = args.llm_call_limit
  if getattr(args, "accept", None):
    # EXPERIMENTAL (Task 2B): proof-local acceptance checks, off unless named.
    run_opts["accept_policy"] = args.accept
  if combined_on:
    # Only solver-known keys go into run_opts (set_global_options rejects unknowns).
    run_opts["combined_flag"] = True
    run_opts["combined_instr_file"] = args.combined_instr
    run_opts["combined_examples_file"] = args.combined_examples
    run_opts["combined_checklist_file"] = args.combined_checklist
  if directanswer_on:
    run_opts["directanswer_flag"] = True
    run_opts["directanswer_file"] = args.directanswer
  if args.prenorm:
    run_opts["prenorm_flag"] = True
  if args.s2split:
    run_opts["s2split_flag"] = True
  if args.event != "neodavidson":
    run_opts["event_base"] = args.event
    run_opts["event_base_explicit"] = True
  elif "-event" in (getattr(args, "_raw_argv", None) or []):
    run_opts["event_base_explicit"] = True   # -event neodavidson, named outright
  if args.abstract or args.abstract_roles or args.abstract_max:
    # Preset expansion into primitives (mirrors solve.py).
    run_opts["abstract_preset_flag"] = True
    run_opts["event_base"] = "flatroles" if (args.abstract_roles or args.abstract_max) else "flat"
    run_opts["entitymerge_flag"] = True
    run_opts["guarddrop_flag"] = True
    run_opts["bridges_flag"] = True
    run_opts["dropdefinites_flag"] = True
    run_opts["typeenrich_flag"] = True
    run_opts["localantonyms_flag"] = True
    run_opts["noproptypes_flag"] = True
    if args.abstract_max:
      run_opts["prenorm_flag"] = True
      run_opts["propclass_flag"] = True
      run_opts["numtype_flag"] = True
      run_opts["compasym_flag"] = True
      run_opts["nominalretry_flag"] = True
      run_opts["negretry_flag"] = True
      # solve.py's -abstract-max turns the literal bridge on and the CLI
      # documentation says the preset includes it.  This expansion omitted it
      # until 2026-08-20, so every `…absnp` folder made through this runner
      # before that date ran WITHOUT the bridge.  Name -litbridge or
      # -nolitbridge explicitly in an experiment and the question does not
      # arise.
      # All six stage keys, exactly as solve.py's -abstract-max sets them: the
      # converter preset plus the open-world stack.  The two expansions must
      # agree.  A -stack* set, an explicit stage switch and every cancel reach
      # solve.py through `_solve_options` and are merged after this block, so
      # they still override it.
      run_opts["fallback_norm_flag"] = True
      run_opts["fallback_hyp_flag"] = True
      run_opts["critic_flag"] = True
      run_opts["graphtrans_flag"] = True
      run_opts["litbridge_flag"] = True
      run_opts["graphbridge_flag"] = True
  if args.noprenorm:                       # prenorm ablation: force OFF after presets
    run_opts["prenorm_flag"] = False
  if args.existfold:
    run_opts["existfold_flag"] = True
  if args.davidson2 or args.proofshort2:
    run_opts["davidson2_flag"] = True
  if args.existfold2 or args.proofshort2:
    run_opts["existfold2_flag"] = True
  if args.nodavidson2 or args.noproofshort2:
    run_opts["nodavidson2_flag"] = True
  if args.noexistfold2 or args.noproofshort2:
    run_opts["noexistfold2_flag"] = True
  if args.noproofshort2:
    run_opts["noproofshort2_flag"] = True
  if args.entitymerge:
    run_opts["entitymerge_flag"] = True
  if args.typeenrich or args.typeenrich_gates:
    run_opts["typeenrich_flag"] = True
    if args.typeenrich_gates:
      import solve
      run_opts["typeenrich_gates"] = solve._parse_te_gates(args.typeenrich_gates)
  if args.guarddrop:
    run_opts["guarddrop_flag"] = True
  if args.bridges:
    run_opts["bridges_flag"] = True
  if args.dropdefinites:
    run_opts["dropdefinites_flag"] = True
  if args.localantonyms:
    run_opts["localantonyms_flag"] = True
  if args.nocrossstage:
    run_opts["crossstage_retry_flag"] = False
  if args.think is not None:
    run_opts["think_flag"] = args.think
  # version / max_tokens are solve module globals, not option keys; carry them
  # under private keys that _worker pops before english_to_answer (set_global_options
  # rejects unknown keys).
  if args.version:
    run_opts["_version_override"] = args.version
  if args.maxtokens:
    run_opts["_maxtokens_override"] = args.maxtokens
  if args.api_timeout and args.api_timeout > 0:
    run_opts["api_timeout"] = args.api_timeout
  # Flags the runner does not define go to solve.py's own parser, so every
  # solve.py flag works here without being restated (-pipeline, -graphtrans,
  # -critic, -nolitbridge, -stack-closed, ...).  An explicit flag wins over the
  # runner's preset expansion.  `-pipeline` deliberately belongs here rather
  # than in the runner's own argparse: forwarding keeps it in the same
  # left-to-right resolution pass as -stack* and -abstract*, so both front
  # doors agree on a line that names two sets.
  if extra_opts:
    run_opts.update(extra_opts)
  # Both entry points derive the recorded configuration name the same way, from
  # the final resolved stage vector (WP3).
  import solve
  run_opts.pop("_pipeline_named", None)
  run_opts["pipeline_name"] = solve.finalize_pipeline_name(run_opts)
  return run_opts


def run_options_for(argv):
  """The resolved solver options for a raw runner command line."""
  args, extra_opts = parse_args(list(argv))
  return build_run_options(args, extra_opts)


def _run_batch(args, llms, tests, testname, outroot, run_opts, matcher,
               manifest=None):
  """The batch itself, unchanged; split out so option resolution is testable."""
  # Per-case parallel: one worker per (case, llm).  Pool size = len(llms).
  ctx = get_context("fork")
  total_done = 0
  total_skipped = 0
  start = time.time()

  # -sequential: run the per-(case,llm) tasks one at a time in this process,
  # no worker Pool. Otherwise the requested LLMs for one case run concurrently.
  pool = None if args.sequential else ctx.Pool(processes=max(1, len(llms)))
  if args.sequential:
    print("Mode: SEQUENTIAL (in-process, one LLM at a time).")
  try:
    for case_id, input_text, expected in tests:
      # Build the per-LLM task list, skipping those that already exist.
      tasks = []
      for llm in llms:
        outpath = case_filename(os.path.join(outroot, llm), case_id)
        if should_skip(outpath, args.redo_errors) and not args.redo:
          total_skipped += 1
          continue
        tasks.append((case_id, input_text, expected, llm, run_opts))
      if not tasks:
        continue

      t0 = time.time()
      results = ([_worker(t) for t in tasks] if args.sequential
                 else pool.map(_worker, tasks))
      dt = time.time() - t0

      # Write per-case files
      summary_line = []
      for cid, llm, collect in results:
        payload = build_case_json(testname, cid, input_text, expected, llm, collect, matcher)
        outpath = case_filename(os.path.join(outroot, llm), cid)
        write_case_file(outpath, payload)
        if "error" in payload:
          summary_line.append(f"{llm}=ERR")
        else:
          ok = payload.get("correctness")
          summary_line.append(f"{llm}={'OK' if ok else 'FAIL'}")
      total_done += len(tasks)
      print(f"[{case_id:04d}] {dt:5.1f}s  " + " ".join(summary_line) + "  | " + input_text[:60].replace("\n", " "))

      # Update per-LLM summary.json after each case so it's live.
      for llm in llms:
        update_summary(os.path.join(outroot, llm), llm)
      update_combined_summary(outroot, testname,
                              (manifest or {}).get("providers", {}) or llms)

      # Throttle solo gemini runs: free-tier RPM is tight, and back-to-back
      # Stage-1 + Stage-2 calls + no parallelism across LLMs make 429s easy
      # to hit.  When other LLMs share the loop, their wall time naturally
      # spaces gemini's calls, so no throttle is applied.
      if llms == ["gemini"]:
        time.sleep(3.0)
  finally:
    if pool is not None:
      pool.close()
      pool.join()

  elapsed = time.time() - start
  print()
  update_combined_summary(outroot, testname,
                          (manifest or {}).get("providers", {}) or llms)
  print(f"Done. {total_done} task(s) run, {total_skipped} skipped, {elapsed:.1f}s.")
  print(f"Combined summary: {os.path.join(outroot, 'summary.json')}")


if __name__ == "__main__":
  main()


# =========== the end ==========
