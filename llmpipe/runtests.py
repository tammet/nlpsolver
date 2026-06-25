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

def _worker(args):
  case_id, input_text, expected, llm, run_opts = args
  # Importing inside the worker keeps each process clean of solver-global state.
  sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "solver"))
  import solve as _solve_mod
  from solve import english_to_answer
  import llmcall
  _solve_mod.llm = llm

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
  try:
    english_to_answer(input_text, options=ro, collect=collect)
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
  if run_opts.get("combined_flag"):
    collect["combined"] = {
      "instr": run_opts.get("combined_instr_file"),
      "examples": run_opts.get("combined_examples_file"),
      "checklist": run_opts.get("combined_checklist_file"),
    }
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
  }
  if answer is not None:
    out["answer"] = answer
  if correctness is not None:
    out["correctness"] = correctness
  for k in ("combined", "directanswer",
            "stage1", "stage_1_fixes", "stage_1_retries",
            "stage2", "stage_2_fixes", "stage_2_retries",
            "clauses", "gk_command", "proof", "nl_proof"):
    v = collect.get(k)
    if not v:   # skip None/[]/'' — omit empty keys
      continue
    if k in ("stage1", "stage2", "clauses"):
      v = _strip_internal_keys(v)
    elif k == "nl_proof" and isinstance(v, str):
      v = v.split("\n")
    out[k] = v
  if "_error" in collect:
    out["error"] = collect["_error"]
  out["timestamp"] = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
  return out


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
    return "error" not in data
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
    elif k == "clauses":
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
  return {
    "commit": commit,
    "dirty": bool(run(["status", "--porcelain", "--untracked-files=no"])),
    "tags": run(["tag", "--points-at", "HEAD"]).split(),
  }


# Computed once in main(); embedded in every summary.json the run writes.
_pipeline_git = None


def update_summary(outdir, llm):
  """Scan the LLM's output dir, rebuild summary.json from per-case .py files."""
  if not os.path.isdir(outdir):
    return
  passed = failed = errored = 0
  by_case = []
  for fn in sorted(os.listdir(outdir)):
    if not fn.startswith("case_") or not fn.endswith(".json"):
      continue
    p = os.path.join(outdir, fn)
    try:
      d = _load_case_file(p)
    except Exception:
      continue
    cid = d.get("case_id")
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
    "updated": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
  }
  if _pipeline_git:
    summary["pipeline_git"] = _pipeline_git
  with open(os.path.join(outdir, "summary.json"), "w") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)


# ======== main loop ========

def main():
  global _pipeline_git
  _pipeline_git = pipeline_git_state()
  ap = argparse.ArgumentParser(description="Batch test runner for nlpsolver.")
  ap.add_argument("testfile", nargs="?", default=DEFAULT_TESTFILE,
                  help=f"Test file (default: {DEFAULT_TESTFILE})")
  ap.add_argument("-llms", default=",".join(DEFAULT_LLMS),
                  help=f"Comma-separated LLMs to run (default: {','.join(DEFAULT_LLMS)})")
  ap.add_argument("-out", default=DEFAULT_OUTROOT,
                  help=f"Output root directory (default: {DEFAULT_OUTROOT})")
  ap.add_argument("-ids", default=None,
                  help="Run only these case ids (comma-separated)")
  ap.add_argument("-limit", type=int, default=0,
                  help="Run at most N cases (0=all)")
  ap.add_argument("-filter", default=None,
                  help="Only run cases whose input contains this substring")
  ap.add_argument("-redo-errors", action="store_true", dest="redo_errors",
                  help="Re-run cases whose existing JSON has an 'error' key")
  ap.add_argument("-redo", action="store_true",
                  help="Re-run all cases (overwrite existing JSON files)")
  ap.add_argument("-geminicache", action="store_true",
                  help="Enable Gemini context caching (off by default)")
  ap.add_argument("-sequential", action="store_true",
                  help="Run the requested LLMs SEQUENTIALLY in-process (no "
                       "parallel Pool). Best for cache-served reruns where the "
                       "LLM calls hit the local SQLite cache.")
  ap.add_argument("-combined-instr", dest="combined_instr", default=None,
                  help="Combined single-stage instructions prompt file (enables "
                       "one-call English->logic parsing; results go to a "
                       "<set>_<tag> output dir so they don't clash with two-stage runs)")
  ap.add_argument("-combined-examples", dest="combined_examples", default=None,
                  help="Combined examples prompt file (optional)")
  ap.add_argument("-combined-checklist", dest="combined_checklist", default=None,
                  help="Combined checklist prompt file (optional)")
  ap.add_argument("-combined-tag", dest="combined_tag", default=None,
                  help="Label for the combined output dir suffix; if omitted, "
                       "derived from the prompt filenames")
  ap.add_argument("-directanswer", dest="directanswer", default=None,
                  help="Direct-answer prompt file: answer each case with ONE LLM "
                       "call (no logic, no prover). Output goes to a <set>_<tag> dir.")
  ap.add_argument("-prenorm", action="store_true",
                  help="Enable the pre-Stage-1 normalization LLM phase")
  ap.add_argument("-s2split", action="store_true",
                  help="Run Stage 2 sentence-by-sentence: one Stage-2 LLM call "
                       "per Stage-1 sentence package, outputs joined. Output "
                       "goes to a <set>_s2split dir unless -tag is given.")
  ap.add_argument("-slightcoarse", action="store_true",
                  help="Light shape unification: predicate rename, shape "
                       "bridges, property-shape compound composition, "
                       "broad-supertype isa (see solve.py -slightcoarse)")
  ap.add_argument("-event", choices=["neodavidson", "davidson", "flat", "flatroles"],
                  default="neodavidson",
                  help="event-encoding base: neodavidson (default) | davidson "
                       "(compact event(V,A,O,E)) | flat (is_rel2) | flatroles "
                       "(is_rel2 with eventprop-tagged object)")
  ap.add_argument("-abstract", action="store_true",
                  help="preset: -event flat + all abstraction buckets + simpleprops + localantonyms")
  ap.add_argument("-abstract-roles", dest="abstract_roles", action="store_true",
                  help="preset: as -abstract but -event flatroles")
  ap.add_argument("-abstract-max", dest="abstract_max", action="store_true",
                  help="preset: as -abstract-roles + -prenorm (strongest abstraction)")
  ap.add_argument("-existfold", action="store_true",
                  help="(L2) fold exists Y.isa(C,Y)&has_part/have(X,Y) into has_property([$has_part/$have,C],X); named-witness bridge")
  # Additive abstraction primitives (compose with any -event base).
  ap.add_argument("-entitymerge", action="store_true", help="proper-noun entity canonicalization + set coreference")
  ap.add_argument("-typeenrich", action="store_true", help="taxonomy/isa enrichment (all six sub-gates)")
  ap.add_argument("-typeenrich-gates", dest="typeenrich_gates", default=None,
                  help="restrict typeenrich to a comma list of sub-gates "
                       "(super,gender,nametype,compound,plural,gnoun; -name excludes; all)")
  ap.add_argument("-guarddrop", action="store_true", help="drop redundant antecedent type guards (needs a fold base)")
  ap.add_argument("-bridges", action="store_true", help="frame/bridge axioms (needs -event flat/flatroles)")
  ap.add_argument("-dropdefinites", action="store_true", help="skip $theof1 definite reification (leave as relations)")
  ap.add_argument("-localantonyms", action="store_true", help="restrict antonym folding to the problem + axiom vocabulary")
  ap.add_argument("-nocrossstage", action="store_true",
                  help="Disable the ultracoarse cross-stage unsatisfiable-guard "
                       "retry (avoids live corrective LLM calls)")
  ap.add_argument("-api-timeout", dest="api_timeout", type=int, default=120,
                  help="Hard wall-clock cap (seconds) on the LLM-parse + clause-"
                       "conversion phase of each case; disarmed before the prover "
                       "(gk) and proof post-processing run, so it never clips those. "
                       "A case exceeding it is recorded as an Error and the run "
                       "continues (default 120; 0 disables). Guards against wedged "
                       "LLM calls retrying through their timeouts.")
  ap.add_argument("-version", dest="version", default=None,
                  help="Override the model version for the chosen LLM "
                       "(e.g. claude-opus-4-8). Applies to all -llms in the run.")
  ap.add_argument("-think", dest="think", type=int, default=None,
                  help="Enable extended thinking with this token budget "
                       "(Claude budget_tokens / Gemini thinkingBudget). "
                       "Must be below -maxtokens.")
  ap.add_argument("-maxtokens", dest="maxtokens", type=int, default=None,
                  help="Override max output tokens (must exceed the -think budget).")
  ap.add_argument("-tag", dest="tag", default=None,
                  help="General output-dir suffix: results go to testresults/<set>_<tag>/. "
                       "Use to keep a variant (directanswer, ultracoarse, ...) separate.")
  args = ap.parse_args()

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

  # Prepare outdirs
  outroot = os.path.join(args.out, testname)
  os.makedirs(outroot, exist_ok=True)
  for llm in llms:
    os.makedirs(os.path.join(outroot, llm), exist_ok=True)

  # Solver options — keep cache on per project rules.
  run_opts = {}
  if args.geminicache:
    run_opts["use_gemini_cache_flag"] = True
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
  if args.slightcoarse:
    run_opts["slightcoarse_flag"] = True
  if args.event != "neodavidson":
    run_opts["event_base"] = args.event
  if args.abstract or args.abstract_roles or args.abstract_max:
    # Preset expansion into primitives (mirrors solve.py).
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
  if args.existfold:
    run_opts["existfold_flag"] = True
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
  print(f"Done. {total_done} task(s) run, {total_skipped} skipped, {elapsed:.1f}s.")


if __name__ == "__main__":
  main()


# =========== the end ==========
