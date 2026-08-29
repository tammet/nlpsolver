#!/usr/bin/env python3

# Test runner for the LLM-based nlpsolver pipeline.
#
# Loads one or more test files (Python list literals of [input, expected] pairs),
# runs each input through english_to_answer(), compares the result to the
# expected value, and reports a summary.
#
# Default test file: tests/tests_core.py
#
# All command-line flags are documented in the `helptext` string below
# (search for "======== helptext ========"); the same text is printed by
# `python3 test.py -help`.
#
# Auto-resume: human-readable output is appended to test_output.txt. Exact
# machine-readable keys live beside it in test_output.txt.resume.jsonl; a case
# is reused only when the test source, pipeline source state, case content,
# provider, version, solver configuration and scoring policy all match. Pass
# -restart to wipe both files
# and rerun everything; pass -logfile PATH to use a different pair of files.
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------

import re
import sys
import time
import unicodedata
import urllib.parse
import hashlib
import json
import os

sys.path.insert(0, './solver')
from solve import english_to_answer
import solve as _solve_mod


def _print(*args, **kwargs):
  """Print to stdout and, if a log file is open, also write there (flushed)."""
  print(*args, **kwargs)
  _log_write(*args, **kwargs)

def _log_write(*args, **kwargs):
  """Write to the log file only (no console output). Flushed after every call."""
  if _log_fh is not None:
    end = kwargs.get("end", "\n")
    sep = kwargs.get("sep", " ")
    line = sep.join(str(a) for a in args) + end
    _log_fh.write(line)
    _log_fh.flush()

# ======== defaults ========

# Default test file used when no files are given on the command line.
default_test_file = "tests/tests_core.py"

# ======== configuration (overridable via command line) ========

# Output verbosity: exactly one of these will be True after _parse_cmd_line().
#   verbose : print Input / Expected / Received for every test  (default)
#   compact : print a single "." (pass) or "F" (fail) character per test
#   quiet   : no per-test output at all; only the final summary
show_verbose = True
show_compact = False
show_quiet   = False

# When True, print only the tests that failed (skip the passing ones).
show_failures_only = False

# When True, stop the run immediately after the first failure.
stop_on_fail = False

# Run at most this many tests per file (0 = unlimited).
limit = 0

# Skip this many tests at the start of each file (0 = no skip).
skip = 0

# When set, only run tests whose input text contains this substring.
filter_pattern = None

# When True, do not accept answers that contain confidence qualifiers "(…)".
strict_confidences = False

# When True, spatial prepositions must match exactly between expected and received.
# When False (default), a leading preposition on one side but not the other is OK
# (e.g. "Estonia" and "in Estonia" are treated as equivalent).
# Comparison is always case-insensitive.
strict_prepositions = False

# Log file: all output is also written here (flushed after every line).
# Set to None to disable.  Override with -logfile PATH on the command line.
# On restart, the log file is parsed to determine which tests were already
# completed, so the run can resume automatically.  Use -restart to start fresh.
log_file_path = "test_output.txt"
_log_fh = None   # opened in main()
_resume_fh = None
_resume_records = {}

# When True, delete the log file and start fresh (set by -restart flag).
restart = False


# ======== helptext ========

helptext = """test.py — quick single-provider checks for contributors.

Usage:
  python test.py [options] [testfile ...]

Test files are Python files containing a single list literal of
[id, input, expected] triples, e.g.:
  [
    [1, "Elephants are animals. John is an elephant. John is an animal?", True],
    [2, "Elephants are animals. Who is an animal?", "An elephant."],
    [3, "John has a car?", None],   # None means "Unknown" is the expected answer
    [4, "John gave a book to Mary. What did Mary receive?", ["A book.", "The book."]],
  ]
When expected is a list, the test passes if the received answer matches
ANY element of the list.

If no test file is given, tests/tests_core.py is used.

For safety, running test.py with no arguments prints this help instead of
starting the full default suite. Name a test file explicitly to run cases.

output control:
 -v  / -verbose        print Input / Expected / Received for every test (default)
 -c  / -compact        print one character per test: . (pass) or F (fail)
 -q  / -quiet          no per-test output; only the final summary
 -f  / -failonly       only print tests that failed

flow control:
 -stopfail             stop the run after the first failure
 -limit N              run at most N tests per file
 -skip N               skip the first N tests in each file
 -filter PATTERN       only run tests whose input contains PATTERN (case-sensitive)
 -restart              start fresh (ignore any previous progress in the log file);
                       without this flag, an adjacent .resume.jsonl file reuses
                       only exact matches for the test source, case, provider,
                       version, pipeline source, solver configuration and
                       scoring policy

solver options:
 -llm NAME             LLM provider: gpt, claude, gemini, or deepseek
 -version VER          model version string, e.g. gemini-2.0-flash
 -logfile PATH         write log to PATH instead of test_output.txt

cache / matching options:
 -nollmcache           disable LLM response caching for this run
                       (LLM cache is ON by default; results are keyed on
                       provider, version, all call parameters and input text)
 -cache                enable GK prover result caching (off by default)
 -strict               strict confidence comparison: "Probably true." and "Likely true."
                       match each other but not plain "True." (default: qualifiers are
                       stripped so all certainty levels are treated as equivalent)
 -strictprep           strict preposition matching: "in Estonia" and "Estonia" are
                       treated as different answers (default: permissive — a leading
                       spatial preposition on one side but not the other is ignored)

 -help                 show this help text
"""


# ======== exact-key resume records ========

RESUME_SCHEMA_VERSION = 1
ANSWER_MATCH_POLICY_VERSION = 1


def answer_matching_policy(single_stage=False):
  """Machine-readable description of the comparator used for correctness."""
  return {
    "name": "llmpipe_answer_match",
    "version": ANSWER_MATCH_POLICY_VERSION,
    "strict_confidences": bool(strict_confidences),
    "strict_prepositions": bool(strict_prepositions),
    "single_stage_rendering_tolerance": bool(single_stage),
    "multiple_expected_answers": "any alternative may match",
    "unknown_expected": "first output line begins with Unknown",
    "normalizations": [
      "python_boolean_to_true_false",
      "first_output_line_only",
      "case_and_punctuation",
      "word_order",
      "coordinated_phrase_order",
      "articles",
      "confidence_qualifiers",
      "leading_spatial_preposition_unless_strict",
      "equivalent_length_and_mass_units",
      "input_licensed_answer_adjective",
    ] + ([
      "single_stage_entity_rendering",
      "single_stage_temporal_preposition",
      "single_stage_url_and_diacritic",
      "single_stage_plural_coordination",
    ] if single_stage else []),
  }


def _jsonable(value):
  """Convert option values to a stable JSON-compatible structure."""
  if isinstance(value, dict):
    return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
  if isinstance(value, (set, frozenset)):
    return sorted((_jsonable(v) for v in value), key=lambda v: repr(v))
  if isinstance(value, (list, tuple)):
    return [_jsonable(v) for v in value]
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  return repr(value)


def _sha256_text(text):
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_sha256(path):
  with open(path, "rb") as f:
    return hashlib.sha256(f.read()).hexdigest()


def _effective_model():
  """Return the provider and version the single-provider runner will use."""
  import llmcall
  provider = _solve_mod.llm or llmcall.use_llm
  version = _solve_mod.llm_version or getattr(llmcall, provider + "version", None)
  return provider, version


def _pipeline_source_state():
  """Commit plus tracked working-tree changes, for safe regression resume."""
  import subprocess
  root = os.path.dirname(os.path.abspath(__file__))
  try:
    commit = subprocess.run(
      ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
      text=True, timeout=10).stdout.strip()
    diff = subprocess.run(
      ["git", "diff", "--binary", "HEAD"], cwd=root, capture_output=True,
      text=True, timeout=10).stdout
  except Exception:
    return None
  if not commit:
    return None
  return {
    "commit": commit,
    "dirty": bool(diff),
    "tracked_diff_sha256": (hashlib.sha256(diff.encode("utf-8")).hexdigest()
                             if diff else None),
  }


def _run_configuration(solver_opts):
  """The fields that must agree before a stored result may be resumed."""
  import globals as solver_globals
  effective = dict(solver_globals.options)
  effective.update(solver_opts)
  effective["pipeline_name"] = _solve_mod.finalize_pipeline_name(effective)
  provider, version = _effective_model()
  return {
    "provider": provider,
    "version": version,
    "solver_options": _jsonable(effective),
    "scoring_policy": answer_matching_policy(False),
    "pipeline_source": _pipeline_source_state(),
  }


def _resume_path(log_path):
  return log_path + ".resume.jsonl" if log_path else None


def _load_resume_records(path):
  """Read exact-key JSONL resume records; malformed lines are ignored."""
  records = {}
  if not path:
    return records
  try:
    with open(path, "r") as f:
      for line in f:
        try:
          row = json.loads(line)
        except (TypeError, ValueError):
          continue
        if (isinstance(row, dict)
            and row.get("schema_version") == RESUME_SCHEMA_VERSION
            and isinstance(row.get("resume_key"), str)):
          records[row["resume_key"]] = row
  except OSError:
    pass
  return records


def _case_resume_key(test_path, test_file_sha256, test, configuration):
  payload = {
    "test_path": os.path.realpath(test_path),
    "test_file_sha256": test_file_sha256,
    "case_id": test[0],
    "input_text": test[1],
    "expected_answer": test[2],
    "configuration": configuration,
  }
  return _sha256_text(json.dumps(_jsonable(payload), sort_keys=True,
                                 separators=(",", ":"), ensure_ascii=False))


def _record_resume(resume_key, test_path, test_file_sha256, test,
                   configuration, received, ok):
  global _resume_records
  row = {
    "schema_version": RESUME_SCHEMA_VERSION,
    "resume_key": resume_key,
    "test_path": os.path.realpath(test_path),
    "test_file_sha256": test_file_sha256,
    "case_id": test[0],
    "input_text": test[1],
    "expected_answer": test[2],
    "configuration": configuration,
    "received": received,
    "passed": bool(ok),
  }
  _resume_records[resume_key] = row
  if _resume_fh is not None:
    _resume_fh.write(json.dumps(_jsonable(row), ensure_ascii=False,
                                sort_keys=True) + "\n")
    _resume_fh.flush()


# ======== main ========

def main():
  global _log_fh, _resume_fh, _resume_records
  if len(sys.argv) == 1:
    print(helptext)
    return
  test_files, solver_opts = _parse_cmd_line()

  if log_file_path:
    resume_path = _resume_path(log_file_path)
    if restart:
      # Start fresh: truncate the log file
      try:
        _log_fh = open(log_file_path, "w", buffering=1)
      except OSError as e:
        print("Warning: cannot open log file", log_file_path, ":", e)
    else:
      # Resume mode: append to existing log file
      try:
        _log_fh = open(log_file_path, "a", buffering=1)
      except OSError as e:
        print("Warning: cannot open log file", log_file_path, ":", e)
    try:
      if restart:
        _resume_records = {}
        _resume_fh = open(resume_path, "w", buffering=1)
      else:
        _resume_records = _load_resume_records(resume_path)
        _resume_fh = open(resume_path, "a", buffering=1)
    except OSError as e:
      print("Warning: cannot open resume file", resume_path, ":", e)

  all_passed = 0
  all_failed = 0
  all_ran    = 0
  all_errors = []   # list of (file, test, received) triples

  total_start = time.time()

  for tf in test_files:
    passed, failed, ran, errors = run_file(tf, solver_opts)
    all_passed += passed
    all_failed += failed
    all_ran    += ran
    all_errors += errors

  elapsed = round(time.time() - total_start, 2)

  if _log_fh:
    _log_fh.close()
  if _resume_fh:
    _resume_fh.close()

  if len(test_files) > 1:
    _print()
    _print("=" * 50)
    _print("Overall summary")
    _print("=" * 50)
    _print_summary(all_ran, all_passed, all_failed, elapsed, all_errors)
  elif not all_errors and not show_verbose:
    # Single file, no failures — print_summary was already called inside run_file
    pass


# ======== per-file runner ========

def run_file(path, solver_opts):
  """Load a test file, run every test through the solver, return stats."""
  tests = _load_test_file(path)
  if tests is None:
    return (0, 0, 0, [])

  try:
    test_file_sha256 = _file_sha256(path)
  except OSError as e:
    _print(f"Error: could not hash test file {path}: {e}")
    return (0, 0, 0, [])
  configuration = _run_configuration(solver_opts)

  # Apply selection before resume. A stored result can skip only the exact
  # file content, case and model/configuration that produced it.
  selected = []
  for i, test in enumerate(tests):
    if i < skip:
      continue
    if filter_pattern and filter_pattern not in test[1]:
      continue
    selected.append(test)
    if limit and len(selected) >= limit:
      break

  resumable = {}
  if not restart and log_file_path:
    for test in selected:
      key = _case_resume_key(path, test_file_sha256, test, configuration)
      row = _resume_records.get(key)
      if row is not None:
        resumable[key] = row

  _print()
  _print("=" * 50)
  _print("Test file:", path)
  _print("=" * 50)
  if resumable:
    resumed_passed = sum(1 for row in resumable.values() if row.get("passed"))
    resumed_failed = len(resumable) - resumed_passed
    _print(f"Resuming: reusing {len(resumable)} exact matching case records "
           f"({resumed_passed} passed, {resumed_failed} failed)")
    if len(resumable) >= len(selected):
      _print()
      _print(f"All {len(selected)} selected tests are already recorded in "
             f"{_resume_path(log_file_path)}. Nothing new to run.")
      _print("Use -restart to wipe the log and rerun from scratch, "
             "or -help for other options.")
  if show_verbose:
    _print()

  passed = 0
  failed = 0
  ran = 0
  errors = []

  start = time.time()

  for test in selected:
    resume_key = _case_resume_key(path, test_file_sha256, test, configuration)
    resumed = resumable.get(resume_key)
    if resumed is not None:
      ran += 1
      if resumed.get("passed"):
        passed += 1
      else:
        failed += 1
        errors.append((test, resumed.get("received", "")))
      continue

    ran += 1
    case_id  = test[0]
    inp      = test[1]
    expected = test[2]

    # --- run solver ---
    try:
      received = english_to_answer(inp, dict(solver_opts))
    except KeyboardInterrupt:
      _print("\nInterrupted.")
      break
    except Exception as e:
      received = "Software error: " + str(e)

    # --- compare ---
    ok = _result_matches(expected, received, inp)
    _record_resume(resume_key, path, test_file_sha256, test,
                   configuration, received, ok)

    # --- output ---
    if show_compact:
      _print("." if ok else "F", end="", flush=True)
      # Always write structured lines to log for resume support
      _log_write("Case:    ", case_id)
      _log_write("Input:   ", inp)
      _log_write("Expected:", _display(expected))
      _log_write("Received:", received)
      _log_write("Result:  ", "OK" if ok else "FAIL")
      _log_write()
    elif show_quiet:
      # No console output, but write structured lines to log
      _log_write("Case:    ", case_id)
      _log_write("Input:   ", inp)
      _log_write("Expected:", _display(expected))
      _log_write("Received:", received)
      _log_write("Result:  ", "OK" if ok else "FAIL")
      _log_write()
    elif show_verbose:
      if ok and show_failures_only:
        pass  # suppress passing tests on console
      else:
        _print("Case:    ", case_id)
        _print("Input:   ", inp)
        _print("Expected:", _display(expected))
        _print("Received:", received)
        _print("Result:  ", "OK" if ok else "FAIL")
        _print()
      # If suppressed on console, still write to log for resume
      if ok and show_failures_only:
        _log_write("Case:    ", case_id)
        _log_write("Input:   ", inp)
        _log_write("Expected:", _display(expected))
        _log_write("Received:", received)
        _log_write("Result:  ", "OK" if ok else "FAIL")
        _log_write()

    if ok:
      passed += 1
    else:
      failed += 1
      errors.append((test, received))
      if stop_on_fail:
        if show_compact:
          _print()
        _print("Stopping after first failure (-stopfail).")
        break

  if show_compact:
    _print()   # newline after the dot row

  elapsed = round(time.time() - start, 2)
  _print_summary(ran, passed, failed, elapsed, errors)

  return (passed, failed, ran, errors)


# ======== result comparison ========

# Unit conversion factors to a canonical base unit, grouped by dimension.
# Singular unit names; the parser strips a trailing plural "s".
_UNIT_FACTORS = {
  # length -> meters
  "millimeter": ("length", 0.001), "centimeter": ("length", 0.01),
  "meter": ("length", 1.0), "kilometer": ("length", 1000.0),
  # mass -> grams
  "milligram": ("mass", 0.001), "gram": ("mass", 1.0),
  "kilogram": ("mass", 1000.0), "ton": ("mass", 1000000.0),
  "tonne": ("mass", 1000000.0),
}

_MEASURE_RE = re.compile(r'^\s*([0-9]*\.?[0-9]+)\s+([a-zA-Z]+?)s?\s*\.?\s*$')


def _parse_measure(s):
  """Parse "80 kilometers" / "3.5 kg" -> (dimension, value_in_base) or None."""
  if type(s) != str:
    return None
  m = _MEASURE_RE.match(s)
  if not m:
    return None
  unit = m.group(2).lower()
  if unit not in _UNIT_FACTORS:
    return None
  dim, factor = _UNIT_FACTORS[unit]
  try:
    return (dim, float(m.group(1)) * factor)
  except ValueError:
    return None


def _measures_match(expected, received):
  """True if both sides are measurements of the same dimension and equal
  magnitude after unit conversion (e.g. "80 kilometers" == "80000 meters")."""
  a = _parse_measure(expected)
  b = _parse_measure(received)
  if a is None or b is None:
    return False
  if a[0] != b[0]:
    return False
  return abs(a[1] - b[1]) < 1e-6


def _result_matches(expected, received, input_text="", single_stage=False):
  """Return True if received is an acceptable answer for expected.

  When expected is a list, the test passes if received matches ANY element.

  single_stage: set True only for one-stage (combined-prompt) runs.  It enables
  an extra, conservative final fallback that tolerates English-rendering
  artefacts which arise because there is no Stage-1 to name entities (leaked
  entity-id letters, dropped adjectives, singular/plural).  Two-stage runs leave
  it False, so their matching is completely unchanged.
  """
  # Multiple acceptable answers: pass if any alternative matches.
  if isinstance(expected, list):
    return any(_result_matches_single(alt, received, input_text, single_stage) for alt in expected)
  return _result_matches_single(expected, received, input_text, single_stage)


def _result_matches_single(expected, received, input_text="", single_stage=False):
  """Return True if received matches a single expected value."""
  # Normalise Python booleans to canonical answer strings
  if received is True:  received  = "True."
  if received is False: received  = "False."
  if expected is True:  expected  = "True."
  if expected is False: expected  = "False."

  if not received:
    return False

  # Strip confidence qualifiers like "(0.95)" from the received string
  cleaned = received
  if type(cleaned) == str and "(" in cleaned and ")" in cleaned:
    if strict_confidences:
      return False
    tmp = []
    depth = 0
    for ch in cleaned:
      if ch == "(":
        depth += 1
      elif ch == ")":
        depth -= 1
      elif depth == 0:
        tmp.append(ch)
    cleaned = "".join(tmp).replace(" .", ".").strip()

  # Take only the first line of the answer
  if type(cleaned) == str:
    cleaned = cleaned.split("\n")[0].strip()

  # None expected means any "Unknown…" answer is acceptable
  if expected is None:
    return type(cleaned) == str and cleaned.startswith("Unknown")

  if type(expected) == str:
    expected = expected.strip()

  if expected == cleaned:
    return True

  # Phrase-level comparison: order-independent, preposition-permissive
  if type(expected) == str and type(cleaned) == str:
    if _phrases_match(expected, cleaned):
      return True

  # Standardised comparison: ignore punctuation, sort words
  if _standardize(expected) == _standardize(cleaned):
    return True

  # Measurement comparison: "80 kilometers" == "80000 meters",
  # "2 kilograms" == "2000 grams", etc. (length and mass unit conversion).
  if type(expected) == str and type(cleaned) == str:
    if _measures_match(expected, cleaned):
      return True

  # Confidence-qualifier comparison.
  # Default (non-strict): strip leading certainty adverbs from both sides and
  #   compare core content — "Probably true." == "True." == "Likely true."
  # Strict: normalise all qualifier words to a single canonical form ("Probably")
  #   so qualifiers at the same certainty class match each other but not the
  #   plain unqualified form — "Probably true." == "Likely true." != "True."
  norm_cleaned  = _norm_conf_qualifier(cleaned)
  norm_expected = _norm_conf_qualifier(expected)
  if norm_cleaned != cleaned or norm_expected != expected:
    if norm_cleaned == norm_expected:
      return True
    if _standardize(norm_expected) == _standardize(norm_cleaned):
      return True
    # Combine the confidence strip with the preposition-permissive and
    # measurement comparisons, so a hedged location/measure answer matches
    # too: "Probably at the office." (→ "at the office.") matches "office" /
    # "In the office." just as the unhedged "At the office." does.
    if type(norm_expected) == str and type(norm_cleaned) == str:
      if _phrases_match(norm_expected, norm_cleaned):
        return True
      if _measures_match(norm_expected, norm_cleaned):
        return True

  # Adjective-prepend: "The nice mother" matches "The mother" if "nice" is in the input text
  if type(expected) == str and type(cleaned) == str and input_text:
    if _adjective_prepend_match(expected, cleaned, input_text):
      return True

  # One-stage (combined-prompt) runs only: a final conservative fallback for
  # English-rendering artefacts that have no Stage-1 to fix them.
  if single_stage and type(expected) == str and type(cleaned) == str:
    # adjectives dropped / entity-id letters / plural / truncated stems
    if _lenient_single_stage_match(expected, cleaned):
      return True
    # A1: temporal-point-preposition equivalence ("In 1800" == "During 1800")
    te = _temporal_phrases(expected)
    if te is not None and te == _temporal_phrases(cleaned):
      return True
    # A2: URL-encoded / diacritic entity names ("Emaj%C3%B5gi" == "Emajogi")
    en, rn = _url_diacritic_norm(expected), _url_diacritic_norm(cleaned)
    if (en != expected or rn != cleaned) and (
        en == rn or _standardize(en) == _standardize(rn)
        or _phrases_match(en, rn) or _lenient_single_stage_match(en, rn)):
      return True
    # A3: plural noun answer vs a coordination of that noun's instances
    if _plural_coordination_match(expected, cleaned):
      return True

  return False


# Spatial prepositions that may prefix location phrases in answers.
# These are stripped for comparison only when one side has a prep and the other does not.
_SPATIAL_PREPS = frozenset({
  "in", "on", "at", "near", "above", "under", "below", "over",
  "inside", "outside", "behind", "beside", "between", "by",
  "within", "upon", "onto", "into",
})

# Articles stripped when normalising phrase content.
_ARTICLES = frozenset({"a", "an", "the"})

# Certainty adverbs that may prefix an answer (case-insensitive match on first word).
_CONF_QUALIFIERS = frozenset({"probably", "likely", "perhaps", "certainly", "possibly"})


def _split_and_phrases(txt):
  """Split a string on ' and ', ', and ', or ', ' into individual phrases."""
  parts = re.split(r',\s+and\s+|,\s+|\s+and\s+', txt)
  return [p.strip() for p in parts if p.strip()]


def _parse_phrase(phrase):
  """Return (prep, content) for a phrase (all lowercase, stripped of articles).

  prep is the leading spatial preposition (lowercase) or "".
  content is the remaining words, lowercased, articles removed, joined by space.
  In non-strict confidence mode, leading confidence qualifiers (e.g. "likely")
  are also stripped from individual phrases.
  """
  words = phrase.lower().replace(".", "").replace(",", "").split()
  prep = ""
  if words and words[0] in _SPATIAL_PREPS:
    prep = words[0]
    words = words[1:]
  if not strict_confidences and words and words[0] in _CONF_QUALIFIERS:
    words = words[1:]
  words = [w for w in words if w not in _ARTICLES]
  return prep, " ".join(words)


def _adjective_prepend_match(expected, received, input_text):
  """Return True if received equals expected with adjectives prepended before nouns,
  and every extra adjective appears in input_text.

  E.g. expected="The mother", received="The nice mother", input has "nice" → True.
  Works for multi-word answers like "The mother and the fox" vs "The nice mother and the nice fox".
  """
  input_lower = input_text.lower()
  exp_phrases = _split_and_phrases(expected)
  rec_phrases = _split_and_phrases(received)
  if len(exp_phrases) != len(rec_phrases):
    return False
  # Sort both sides by content for order-independent comparison
  exp_sorted = sorted(exp_phrases, key=str.lower)
  rec_sorted = sorted(rec_phrases, key=str.lower)
  for ep, rp in zip(exp_sorted, rec_sorted):
    ew = ep.lower().replace(".", "").split()
    rw = rp.lower().replace(".", "").split()
    # received must contain all words of expected in order, with extra words (adjectives)
    ei = 0
    extras = []
    for w in rw:
      if ei < len(ew) and w == ew[ei]:
        ei += 1
      else:
        extras.append(w)
    if ei != len(ew):
      return False
    # Every extra word must appear in the input text
    if not extras:
      continue
    for adj in extras:
      if adj not in input_lower:
        return False
  return True


def _phrases_match(expected_str, received_str):
  """Return True if expected_str and received_str represent the same set of phrases.

  Order is always ignored.  Preposition handling depends on strict_prepositions:
    permissive (default): "Estonia" == "in Estonia" (prep on one side only → OK)
    strict: prepositions must match exactly on both sides.
  Comparison is case-insensitive and strips articles.

  Single-phrase comparisons are handled by the same prep-permissive logic
  so e.g. "Estonia." matches "In Estonia." for case 187.
  """
  exp_phrases = _split_and_phrases(expected_str)
  rec_phrases = _split_and_phrases(received_str)
  if len(exp_phrases) != len(rec_phrases):
    return False
  if not exp_phrases:
    return False

  exp_parsed = sorted([_parse_phrase(p) for p in exp_phrases], key=lambda x: x[1])
  rec_parsed = sorted([_parse_phrase(p) for p in rec_phrases], key=lambda x: x[1])

  for (ep, ec), (rp, rc) in zip(exp_parsed, rec_parsed):
    if ec != rc:
      return False
    if strict_prepositions:
      if ep != rp:
        return False
    else:
      # permissive: both have preps → must match; one absent → OK
      if ep and rp and ep != rp:
        return False
  return True

def _norm_conf_qualifier(txt):
  """Normalise a leading confidence-qualifier word in txt.

  Non-strict mode (default): drop the qualifier entirely.
  Strict mode: replace all qualifier words with the canonical "Probably".
  Returns txt unchanged if no qualifier is found.
  """
  if type(txt) != str:
    return txt
  parts = txt.split(" ", 1)
  if len(parts) == 2 and parts[0].rstrip(".").lower() in _CONF_QUALIFIERS:
    return parts[1] if not strict_confidences else "Probably " + parts[1]
  return txt


def _standardize(txt):
  """Remove punctuation, lower-case, sort words — for fuzzy comparison.

  Also strips articles (a/an/the) and single-letter Skolem-suffix words
  (e.g. 'Mother A' -> 'mother', 'The mother' -> 'mother') so that entity
  naming style differences don't cause spurious failures.
  """
  if type(txt) != str:
    return txt
  txt = txt.replace(".", "").replace(",", " ").lower()
  words = txt.split()
  # Remove articles and single-letter words (Skolem suffixes like 'a', 'b', 'c')
  _skip = {"a", "an", "the"}
  words = [w for w in words if w not in _skip and len(w) > 1]
  words.sort()
  return words


def _singularize(w):
  """Crudely fold a plural to its singular: 'foxes'->'fox', 'guests'->'guest'.

  Strips a trailing 'es' then 's'.  Conservative: only for words long enough
  that the stem stays meaningful.
  """
  if len(w) > 3 and w.endswith("es"):
    return w[:-2]
  if len(w) > 2 and w.endswith("s"):
    return w[:-1]
  return w


def _lenient_words(phrase):
  """Content words of one coordinated chunk, normalised for one-stage matching.

  Reuses _parse_phrase (drops leading spatial preposition, confidence qualifier
  and articles), then drops leaked entity-id tokens (single letters and bare
  numbers, e.g. the 'A' in 'car A') and singularises the rest.  The chunk's head
  noun is the LAST word returned.
  """
  _, content = _parse_phrase(phrase)
  words = [w for w in content.split() if len(w) > 1 and not w.isdigit()]
  return [_singularize(w) for w in words]


def _lenient_single_stage_match(expected, received):
  """Conservative one-stage-only fallback for English-rendering artefacts.

  Splits both sides into coordinated chunks on ' and ' / ',' (NOT 'or', so a
  disjunctive expected like 'Mike or Mickey' is never matched by a conjunctive
  'Mickey and Mike').  Requires the SAME number of chunks, pairs them by head
  noun, and for each pair requires the received chunk's words to be a SUBSET of
  the expected chunk's words.  This accepts answers that merely lost adjectives
  or carry a leaked entity-id letter / plural ('car A' ~ 'a red car',
  'Guest C' ~ 'the guests', 'A foxes' ~ 'a fox'), while rejecting answers that
  add a conflicting word ('blue box' vs 'red box'), drop or add an item
  ('garden' vs 'garden, hallway and kitchen'), or switch and/or.
  """
  if type(expected) != str or type(received) != str:
    return False
  exp_chunks = _split_and_phrases(expected)
  rec_chunks = _split_and_phrases(received)
  if not rec_chunks or len(exp_chunks) != len(rec_chunks):
    return False

  def chunk(p):
    prep, content = _parse_phrase(p)   # prep = leading spatial preposition, or ""
    words = [_singularize(w) for w in content.split() if len(w) > 1 and not w.isdigit()]
    return prep, words

  exp = [chunk(c) for c in exp_chunks]
  rec = [chunk(c) for c in rec_chunks]
  # Every chunk must reduce to at least one content word (its head noun).
  if any(not w for _, w in exp) or any(not w for _, w in rec):
    return False
  used = [False] * len(exp)
  for rprep, rw in rec:
    rhead = rw[-1]
    paired = False
    for i, (eprep, ew) in enumerate(exp):
      if used[i]:
        continue
      # Prepositions must be compatible (permissively: both present must match,
      # one absent is OK) so 'in the box' never matches 'on the box'; head nouns
      # match (allowing truncated stem+id, 'Ele1' ~ 'elephant'); and every
      # received word is covered by an expected word (dropped adjectives OK, a
      # conflicting word is not).
      prep_ok = (eprep == rprep) if strict_prepositions else (not eprep or not rprep or eprep == rprep)
      if prep_ok and _heads_match(ew[-1], rhead) and all(any(_heads_match(x, y) for y in ew) for x in rw):
        used[i] = True
        paired = True
        break
    if not paired:
      return False
  return all(used)


def _head_key(tok):
  """('ele1' -> ('ele', True)) for a truncated stem+id leak; else (singular, False)."""
  m = re.match(r"^([a-z]{2,})\d+$", tok.lower())
  if m:
    return (m.group(1), True)
  return (_singularize(tok.lower()), False)


def _heads_match(a, b):
  """Two content words match if equal (singularised), or one is a truncated
  stem+id whose >=3-char stem is a prefix of the other ('Ele1' ~ 'elephant',
  'Stu1' ~ 'students', 'Pea1' ~ 'pear').  The truncated form must carry a digit,
  so ordinary words never prefix-match (no 'still' ~ 'stillness')."""
  ca, ta = _head_key(a)
  cb, tb = _head_key(b)
  if ca == cb:
    return True
  if ta and len(ca) >= 3 and cb.startswith(ca):
    return True
  if tb and len(cb) >= 3 and ca.startswith(cb):
    return True
  return False


def _plural_coordination_match(expected, received):
  """A single PLURAL-noun answer matches a coordination of that noun's instances:
  'The elephants' ~ 'Elephant 2 and Elephant 1' (or 'Ele1 and Ele2').  Requires
  the expected head to be plural so a singular answer never matches >1 instance."""
  if not (isinstance(expected, str) and isinstance(received, str)):
    return False
  ec = _split_and_phrases(expected)
  rc = _split_and_phrases(received)
  if len(ec) != 1 or len(rc) < 2:
    return False
  ew = [w for w in _parse_phrase(ec[0])[1].split() if len(w) > 1 and not w.isdigit()]
  if not ew:
    return False
  raw = ew[-1]
  if not (raw.endswith("s") and len(raw) > 3):   # expected head must be plural
    return False
  ehead = _singularize(raw)
  for rp in rc:
    rw = _lenient_words(rp)
    if not rw or not _heads_match(ehead, rw[-1]):
      return False
  return True


# Temporal-point prepositions that mean "at this time" and are interchangeable
# (in/on/at/during a year/month/day) — but NOT before/after, which are directional.
_TEMPORAL_POINT_PREPS = frozenset({"in", "on", "at", "during"})
_MONTHS = frozenset(("january february march april may june july august september "
                     "october november december jan feb mar apr jun jul aug sep "
                     "sept oct nov dec").split())
_WEEKDAYS = frozenset("monday tuesday wednesday thursday friday saturday sunday".split())
_TIMEWORDS = frozenset({"noon", "midnight", "morning", "afternoon", "evening",
                        "night", "today", "tomorrow", "yesterday"})


def _is_temporal_token(t):
  return bool(re.fullmatch(r"\d{3,4}", t)) or t in _MONTHS or t in _WEEKDAYS or t in _TIMEWORDS


def _temporal_phrases(s):
  """Per coordinated phrase that contains a temporal token, drop a leading
  in/on/at/during so 'In 1800' == 'During 1800'.  Returns the sorted phrase list,
  or None if no phrase is temporal (so this only fires on time answers — it never
  collapses spatial 'in the box' vs 'on the box')."""
  if not isinstance(s, str):
    return None
  out = []
  saw = False
  for ph in _split_and_phrases(s):
    w = [x for x in ph.lower().replace(".", "").replace(",", "").split() if x not in _ARTICLES]
    if any(_is_temporal_token(x) for x in w):
      saw = True
      if w and w[0] in _TEMPORAL_POINT_PREPS:
        w = w[1:]
    out.append(" ".join(w))
  return sorted(out) if saw else None


def _url_diacritic_norm(s):
  """URL-decode and strip diacritics: 'Emaj%C3%B5gi' -> 'Emajogi' (single-stage
  entity-name renderings sometimes leak percent-encoded / accented constants)."""
  if not isinstance(s, str):
    return s
  try:
    s = urllib.parse.unquote(s)
  except Exception:
    pass
  s = unicodedata.normalize("NFKD", s)
  return "".join(c for c in s if not unicodedata.combining(c))


def _display(expected):
  """Pretty-print an expected value for output."""
  if isinstance(expected, list):
    return " | ".join(_display(alt) for alt in expected)
  if expected is True:  return "True."
  if expected is False: return "False."
  if expected is None:  return "Unknown (None)"
  return repr(expected)


# ======== summary printer ========

def _print_summary(ran, passed, failed, elapsed, errors):
  _print()
  _print(f"Tests run: {ran}  |  Passed: {passed}  |  Failed: {failed}  |  Time: {elapsed}s")
  if errors:
    _print()
    _print("Failed tests:")
    for test, received in errors:
      _print("  Case:    ", test[0])
      _print("  Input:   ", test[1])
      _print("  Expected:", _display(test[2]))
      _print("  Received:", received)
      _print()


# ======== test file loader ========

def _load_test_file(path):
  """Read and eval a test file; return the list of tests or None on error."""
  try:
    with open(path, "r") as f:
      src = f.read()
  except OSError:
    print(f"Error: could not read test file: {path}")
    return None
  try:
    tests = eval(src)
  except Exception as e:
    print(f"Error: could not parse test file {path}: {e}")
    return None
  if not isinstance(tests, list):
    print(f"Error: test file {path} does not contain a list.")
    return None
  return tests


# ======== command-line parser ========

def _parse_cmd_line():
  """Return (list_of_test_files, solver_options_dict)."""
  global show_verbose, show_compact, show_quiet, show_failures_only
  global stop_on_fail, limit, skip, filter_pattern, strict_confidences, strict_prepositions
  global restart, log_file_path

  solver_opts = {}
  test_files  = []
  params = sys.argv[1:]
  elpos  = -1
  skippos = 0

  for el in params:
    elpos += 1
    if skippos > 0:
      skippos -= 1
      continue

    if el in ["-v", "--v", "-verbose", "--verbose"]:
      show_verbose = True
      show_compact = False
      show_quiet   = False
    elif el in ["-c", "--c", "-compact", "--compact"]:
      show_compact = True
      show_verbose = False
      show_quiet   = False
    elif el in ["-q", "--q", "-quiet", "--quiet"]:
      show_quiet   = True
      show_verbose = False
      show_compact = False
    elif el in ["-f", "--f", "-failonly", "--failonly"]:
      show_failures_only = True
    elif el in ["-stopfail", "--stopfail"]:
      stop_on_fail = True
    elif el in ["-strict", "--strict"]:
      strict_confidences = True
    elif el in ["-strictprep", "--strictprep"]:
      strict_prepositions = True
    elif el in ["-restart", "--restart"]:
      restart = True
    elif el in ["-nollmcache", "--nollmcache"]:
      solver_opts["use_llm_cache_flag"] = False
    elif el in ["-cache", "--cache"]:
      solver_opts["use_cache_flag"] = True
    elif el in ["-limit", "--limit"]:
      if elpos + 1 >= len(params):
        print("-limit requires an integer argument"); sys.exit(0)
      try:
        limit = int(params[elpos + 1])
      except ValueError:
        print("-limit requires an integer argument"); sys.exit(0)
      skippos = 1
    elif el in ["-skip", "--skip"]:
      if elpos + 1 >= len(params):
        print("-skip requires an integer argument"); sys.exit(0)
      try:
        skip = int(params[elpos + 1])
      except ValueError:
        print("-skip requires an integer argument"); sys.exit(0)
      skippos = 1
    elif el in ["-filter", "--filter"]:
      if elpos + 1 >= len(params):
        print("-filter requires a pattern argument"); sys.exit(0)
      filter_pattern = params[elpos + 1]
      skippos = 1
    elif el in ["-llm", "--llm"]:
      if elpos + 1 >= len(params):
        print("-llm requires a provider name"); sys.exit(0)
      _solve_mod.llm = params[elpos + 1]
      skippos = 1
    elif el in ["-version", "--version"]:
      if elpos + 1 >= len(params):
        print("-version requires a version string"); sys.exit(0)
      _solve_mod.llm_version = params[elpos + 1]
      skippos = 1
    elif el in ["-think", "--think"]:
      # -think alone → True; -think N → integer budget
      if elpos + 1 < len(params):
        try:
          solver_opts["think_flag"] = int(params[elpos + 1])
          skippos = 1
        except ValueError:
          solver_opts["think_flag"] = True
      else:
        solver_opts["think_flag"] = True
    elif el in ["-logfile", "--logfile"]:
      if elpos + 1 >= len(params):
        print("-logfile requires a file path"); sys.exit(0)
      log_file_path = params[elpos + 1]
      skippos = 1
    elif el in ["help", "-help", "--help"]:
      print(helptext); sys.exit(0)
    elif el and el.startswith("-"):
      print(f"Unknown option: {el}"); print(helptext); sys.exit(0)
    else:
      test_files.append(el)

  if not test_files:
    test_files = [default_test_file]

  # In quiet mode, failures_only is implied for per-test output (there is none),
  # but we still show the failures block in the summary.
  if show_quiet:
    show_verbose = False
    show_compact = False

  return test_files, solver_opts


# ======== entry point ========

if __name__ == "__main__":
  main()


# =========== the end ==========
