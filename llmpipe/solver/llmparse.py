# Two-stage LLM parser: English -> Stage-1 ASUs -> Stage-2 logic.
#
# Primary entry point: parse_text(text)
# Returns (stage1_json, stage2_json, stats).
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

import sys
import os
import json
import re

# llmcall.py must be importable (run from the llmpipe/ working directory)
from llmcall import call_llm
import pretty
from stage_sanity import (
  check_stage1 as _check_stage1,
  check_stage2 as _check_stage2,
  check_stage2_id_coverage as _check_id_coverage,
  format_retry_suffix as _format_retry_suffix,
  issue_fingerprints as _issue_fingerprints,
)

# ======== prompt file configuration ========

# Absolute path to llmpipe/ (parent of this file's directory), so that
# prompt files are found regardless of the working directory at runtime.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

prenorm_file             = os.path.join(_root, "prompts", "prenorm_full.txt")
stage1_instructions_file = os.path.join(_root, "prompts", "stage1_instructions_full.txt")
stage1_examples_file     = os.path.join(_root, "prompts", "stage1_examples.txt")
stage1_checklist_file    = os.path.join(_root, "prompts", "stage1_checklist_full.txt")
stage2_instructions_file = os.path.join(_root, "prompts", "stage2_instructions_full.txt")
stage2_examples_file     = os.path.join(_root, "prompts", "stage2_examples.txt")
stage2_checklist_file    = os.path.join(_root, "prompts", "stage2_checklist_full.txt")

# Separator inserted between instructions and examples when building a prompt
examples_separator = "\n\nExamples:\n\n"

# ======== LLM configuration ========

# These are passed through to llmcall.call_llm; None means use llmcall defaults
use_llm   = None   # "gpt" | "claude" | "gemini" | "deepseek" | None
llm_version = None # model version string, or None for llmcall default
max_tokens  = None # int, or None for llmcall default
use_think   = False # True to enable medium reasoning/thinking mode

# ======== debug / logging configuration ========

debug = False          # print stage inputs, outputs and fix details to stdout
debug_file = None      # path to append debug log to, or None to disable
                       # e.g. debug_file = "llmparse_debug.log"

# ======== module-level prompt cache ========

_stage1_sysprompt = None
_stage2_sysprompt = None
_prenorm_sysprompt = None

# Combined single-stage prompt: composed on demand from explicitly named files.
_combined_sysprompt = None
_combined_loaded_key = None

# Experimental pre-Stage-1 normalization: rewrite the English so the same entity /
# property / relation is always worded identically.  Set True (by solve.py's
# -prenorm flag) to enable.  Cached like any other LLM call.
prenorm_enabled = False

# (entity canon) Aggressive entity-name canonicalization over the Stage-1 output.
canon_entities_enabled = False

# (entity canon) Cross-stage unsatisfiable-guard retry: after Stage 2, if a rule
# antecedent names a class/property/relation nothing can satisfy, re-read Stage 1
# and re-encode Stage 2 once with a corrective hint.  Gated on entity
# canonicalization (canon_entities_enabled, i.e. -entitymerge).  At most one retry.
crossstage_guard_retry = True

# Combined single-stage parsing: when enabled, parse_text makes ONE LLM call
# (English -> logic) using the combined prompt files below, instead of the
# two-stage stage1/stage2 calls.  Set by solve.py from globals.options.
combined_enabled = False
combined_instr_file = None      # path to combined instructions prompt file
combined_examples_file = None   # path to combined examples prompt file (optional)
combined_checklist_file = None  # path to combined checklist prompt file (optional)

# Split Stage 2 (-s2split): one Stage-2 LLM call per Stage-1 sentence package;
# the per-sentence outputs are joined into one ["and", ...] logic with world
# constants renumbered (rule c': slice-anchored worlds and W0 keep their
# numbers, locally-invented worlds get fresh global indices).  Set by solve.py.
s2split_enabled = False


def _canon_norm(s):
  """Lowercase and collapse whitespace/underscore runs to a single space."""
  return re.sub(r"[\s_]+", " ", s.strip().lower())


def _canon_strip_suffix(norm):
  """Drop a trailing Stage-1 disambiguator: a number or a single letter."""
  return re.sub(r"\s+(?:[0-9]+|[a-z])$", "", norm).strip()


def _canon_is_proper(eid):
  """A proper/named entity: has an uppercase letter or a 3-4 digit number in
  its base (so distinct common-noun indefinites 'bear 1'/'bear 2' are spared)."""
  base = re.sub(r"\s+(?:[0-9]+|[A-Za-z])$", "", eid.strip())
  return bool(re.search(r"[A-Z]", base)) or bool(re.search(r"[0-9]{3,4}", base))


def _lev_ratio(a, b):
  """Normalized similarity in [0,1] (1 = identical)."""
  if a == b:
    return 1.0
  la, lb = len(a), len(b)
  if not la or not lb:
    return 0.0
  prev = list(range(lb + 1))
  for i, ca in enumerate(a, 1):
    cur = [i]
    for j, cb in enumerate(b, 1):
      cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
    prev = cur
  return 1.0 - prev[lb] / max(la, lb)


def _collect_entity_ids(s1_json):
  ids = []
  for pkg in s1_json if isinstance(s1_json, list) else []:
    for asu in pkg.get("units", []) if isinstance(pkg, dict) else []:
      for ent in asu.get("entities", []) if isinstance(asu, dict) else []:
        eid = ent.get("id") if isinstance(ent, dict) else None
        if isinstance(eid, str) and eid:
          ids.append(eid)
  return ids


def _build_entity_canon_map(ids, lev_threshold=0.9):
  """Group entity ids that denote the same entity and return old->canonical for
  the ones that change.  Rules (proper nouns only, except exact-norm):
    1. exact normalized form (whitespace/_/case) -> same;
    2. same base after stripping a number/letter suffix -> same;
    3. token-subset (one's tokens contained in the other's, sharing the head)
       -> same (prefix/suffix removal, e.g. 'Summer Olympics' in '2008 Summer Olympics');
    4. Levenshtein >= threshold on the base -> same (high, typo-catcher only)."""
  uniq = list(dict.fromkeys(ids))
  info = {}
  for i in uniq:
    n = _canon_norm(i)
    base = _canon_strip_suffix(n)
    info[i] = (n, base, frozenset(base.split()), _canon_is_proper(i))
  parent = {i: i for i in uniq}
  def find(x):
    while parent[x] != x:
      parent[x] = parent[parent[x]]; x = parent[x]
    return x
  def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb:
      parent[rb] = ra
  for x in range(len(uniq)):
    for y in range(x + 1, len(uniq)):
      a, b = uniq[x], uniq[y]
      na, ba, ta, pa = info[a]
      nb, bb, tb, pb = info[b]
      if na == nb:                                   # rule 1
        union(a, b); continue
      if not (pa and pb):                            # remaining rules: proper only
        continue
      if ba == bb:                                   # rule 2
        union(a, b); continue
      if (ta and tb and (ta <= tb or tb <= ta) and (ta & tb)   # rule 3
          and ba.split()[-1] == bb.split()[-1]):                # ...sharing the head
        # The shorter id's tokens are contained in the longer's AND both end in
        # the same head noun, so the extra tokens are modifiers of one entity
        # ("Summer Olympics" / "2008 Summer Olympics", "Beethoven" / "Ludwig van
        # Beethoven").  When the extra token IS the head ("Barutin" / "Barutin
        # Cove" -- a settlement vs a cove named after it), the kind differs and
        # they must NOT merge.
        union(a, b); continue
      if _lev_ratio(ba, bb) >= lev_threshold:        # rule 4
        union(a, b)
  # canonical per group: most frequent id, tie -> longest
  from collections import Counter
  freq = Counter(ids)
  groups = {}
  for i in uniq:
    groups.setdefault(find(i), []).append(i)
  remap = {}
  for members in groups.values():
    if len(members) < 2:
      continue
    canon = max(members, key=lambda i: (freq[i], len(i)))
    for m in members:
      if m != canon:
        remap[m] = canon
  return remap


def canonicalize_entity_ids(s1_json, stats=None):
  """Rewrite every occurrence of a merged entity id (in ids and in text/raw
  fields) to its canonical form.  Single-pass, longest-id-first, so overlapping
  ids ('2008 Summer Olympics' contains 'Summer Olympics') are replaced once."""
  ids = _collect_entity_ids(s1_json)
  remap = _build_entity_canon_map(ids)
  if not remap:
    return s1_json
  # Replace whole id occurrences only.  The alternation contains EVERY entity
  # id (merged ones map to their canonical, the rest map to themselves), sorted
  # longest-first.  Because the longest id at any position is matched as a unit,
  # a shorter merged id can never match inside a longer one ("Summer Olympics"
  # inside "2008 Summer Olympics 6" is protected because the full id is matched
  # first), so there is no substring corruption.  Word-anchored so an id is not
  # matched inside a larger word.
  all_ids = sorted(set(ids), key=len, reverse=True)
  full_map = {i: remap.get(i, i) for i in all_ids}
  pat = re.compile(r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(i) for i in all_ids))
  def _t(node):
    if isinstance(node, str):
      if node in remap:                       # exact whole-string value
        return remap[node]
      return pat.sub(lambda m: full_map[m.group(0)], node)
    if isinstance(node, list):
      return [_t(x) for x in node]
    if isinstance(node, dict):
      return {k: _t(v) for k, v in node.items()}
    return node
  if stats is not None and isinstance(stats, dict):
    stats.setdefault("entity_canon", []).append(dict(remap))
  return _t(s1_json)


# ======== (entity canon) Wikipedia-URL entity unification ========
#
# Stage 2 sometimes resolves a proper-noun entity to its Wikipedia URL in the
# logic body ("https://en.wikipedia.org/wiki/Miroslav_Venhoda") while the
# Stage-1 entity registry keeps the numbered surface form ("Miroslav Venhoda
# 1").  The two constants never merge, so facts/types on one don't reach the
# query on the other (cases 61, 23, 55, 72; URL halves of 19).  Map each URL to
# the matching Stage-1 id by page-title similarity and rewrite it in s2.

_WIKI_URL_RE = re.compile(r"^https?://[^/]*wikipedia\.org/wiki/(.+)$",
                          re.IGNORECASE)


def _wiki_title(url):
  m = _WIKI_URL_RE.match(url)
  if not m:
    return None
  title = re.split(r"[#?]", m.group(1))[0].replace("_", " ")
  try:
    import urllib.parse
    title = urllib.parse.unquote(title)
  except Exception:
    pass
  return title.strip()


def _collect_url_strings(node, out):
  if isinstance(node, str):
    if _WIKI_URL_RE.match(node):
      out.add(node)
  elif isinstance(node, list):
    for x in node:
      _collect_url_strings(x, out)
  elif isinstance(node, dict):
    for v in node.values():
      _collect_url_strings(v, out)


def _best_entity_for_url(url_title, entity_ids):
  """Return the Stage-1 entity id that best matches a URL page title, or None
  if there is no confident, unambiguous match."""
  ut = frozenset(_canon_strip_suffix(_canon_norm(url_title)).split())
  ba_url = _canon_strip_suffix(_canon_norm(url_title))
  if not ut:
    return None
  scored = []
  for eid in entity_ids:
    if not _canon_is_proper(eid):
      continue
    et = frozenset(_canon_strip_suffix(_canon_norm(eid)).split())
    if not et or not (ut & et):
      continue
    inter = len(ut & et)
    jac = inter / len(ut | et)
    contained = (ut <= et) or (et <= ut)
    lev = _lev_ratio(ba_url, _canon_strip_suffix(_canon_norm(eid)))
    if contained or jac >= 0.6 or lev >= 0.9:
      scored.append((inter, jac, lev, eid))
  if not scored:
    return None
  scored.sort(reverse=True)
  if len(scored) >= 2 and scored[0][:2] == scored[1][:2]:
    return None                              # ambiguous tie -> leave alone
  return scored[0][3]


def canonicalize_entity_urls(s1_json, s2_json, stats=None):
  """Rewrite Wikipedia-URL constants in s2 to the matching Stage-1 entity id."""
  if not canon_entities_enabled:
    return s2_json
  entity_ids = list(dict.fromkeys(_collect_entity_ids(s1_json)))
  if not entity_ids:
    return s2_json
  urls = set()
  _collect_url_strings(s2_json, urls)
  remap = {}
  for url in urls:
    title = _wiki_title(url)
    if not title:
      continue
    eid = _best_entity_for_url(title, entity_ids)
    if eid:
      remap[url] = eid
  if not remap:
    return s2_json
  def _t(node):
    if isinstance(node, str):
      return remap.get(node, node)
    if isinstance(node, list):
      return [_t(x) for x in node]
    if isinstance(node, dict):
      return {k: _t(v) for k, v in node.items()}
    return node
  if stats is not None and isinstance(stats, dict):
    stats.setdefault("entity_url_canon", []).append(dict(remap))
  return _t(s2_json)


def normalize_text(text, llm=None, version=None, tokens=None):
  """Rewrite the input English so repeated entities/properties/relations are
  worded consistently.  Returns the normalized text (or the original on error)."""
  global _prenorm_sysprompt
  if _prenorm_sysprompt is None:
    try:
      with open(prenorm_file, "r") as f:
        _prenorm_sysprompt = f.read().strip()
    except Exception as e:
      _print_error("Could not read prenorm prompt '" + prenorm_file + "': " + str(e))
      _prenorm_sysprompt = ""
  if not _prenorm_sysprompt:
    return text
  out = call_llm(_prenorm_sysprompt, text, llm=llm, version=version,
                 max_tokens=tokens)
  if not isinstance(out, str) or not out.strip():
    return text
  return out.strip()


def load_prompts():
  """Load and compose stage prompts from files. Called automatically on first use."""
  global _stage1_sysprompt, _stage2_sysprompt
  _stage1_sysprompt = _compose_prompt(stage1_instructions_file, stage1_examples_file, "stage1",
                                      checklist_file=stage1_checklist_file)
  _stage2_sysprompt = _compose_prompt(stage2_instructions_file, stage2_examples_file, "stage2",
                                      checklist_file=stage2_checklist_file)


def _compose_prompt(instructions_file, examples_file, label, checklist_file=None):
  try:
    with open(instructions_file, "r") as f:
      instructions = f.read().strip()
  except Exception as e:
    _print_error("Could not read " + label + " instructions file '" + instructions_file + "': " + str(e))
    instructions = ""
  examples = ""
  if examples_file:
    try:
      with open(examples_file, "r") as f:
        examples = f.read().strip()
    except Exception as e:
      _print_error("Could not read " + label + " examples file '" + examples_file + "': " + str(e))
      examples = ""
  checklist = ""
  if checklist_file:
    try:
      with open(checklist_file, "r") as f:
        checklist = f.read().strip()
    except Exception as e:
      _print_error("Could not read " + label + " checklist file '" + checklist_file + "': " + str(e))
  if instructions and examples:
    prompt = instructions + examples_separator + examples
    if checklist:
      prompt = prompt + "\n\n" + checklist
    return prompt
  return instructions or examples


def load_combined_prompt():
  """Compose the combined single-stage system prompt from the explicitly named
  combined_instr_file / combined_examples_file / combined_checklist_file, caching
  the result.  Re-composes when the file paths change since the last load."""
  global _combined_sysprompt, _combined_loaded_key
  key = (combined_instr_file, combined_examples_file, combined_checklist_file)
  if _combined_sysprompt is not None and _combined_loaded_key == key:
    return
  _combined_sysprompt = _compose_prompt(combined_instr_file, combined_examples_file,
                                        "combined", checklist_file=combined_checklist_file)
  _combined_loaded_key = key


# ======== split Stage 2 (-s2split) ========

_WORLD_RE = re.compile(r"^W\d+$")


def _slice_anchored_worlds(pkg):
  """World constants that are globally meaningful for this Stage-1 sentence
  package: W0 (the shared initial world) plus any pre_state / post_state
  annotation on the package's units.  These keep their numbers; everything
  else the model emits for this slice is locally invented and gets renumbered."""
  anchored = {"W0"}
  for u in (pkg.get("units", []) if isinstance(pkg, dict) else []):
    if not isinstance(u, dict):
      continue
    for key in ("pre_state", "post_state"):
      v = u.get(key)
      if isinstance(v, str) and _WORLD_RE.match(v):
        anchored.add(v)
  return anchored


def _package_has_query(pkg):
  """True if the Stage-1 sentence package contains the question."""
  if not isinstance(pkg, dict):
    return False
  for u in pkg.get("units", []):
    if isinstance(u, dict) and u.get("type") in ("query", "question"):
      return True
  raw = pkg.get("raw")
  return isinstance(raw, str) and raw.strip().endswith("?")


def _collect_worlds(node, out):
  if isinstance(node, str):
    if _WORLD_RE.match(node):
      out.add(node)
  elif isinstance(node, list):
    for x in node:
      _collect_worlds(x, out)


def _renumber_split_worlds(pkgs, anchored, max_seen):
  """Rule c': renumber the locally-invented worlds of one split's packages.

  Worlds in `anchored` (W0 + the slice's pre/post_state annotations) keep
  their numbers.  Every other world constant is remapped, in ascending index
  order, to the next free global index (starting at max_seen + 1, skipping
  indices used by anchored worlds present in this split).  Returns
  (renumbered_pkgs, new_max_seen); new_max_seen covers anchored worlds too."""
  worlds = set()
  _collect_worlds(pkgs, worlds)
  if not worlds:
    return (pkgs, max_seen)
  present_anchored = {int(w[1:]) for w in worlds if w in anchored}
  unanchored = sorted(int(w[1:]) for w in worlds if w not in anchored)
  mapping = {}
  used = set(present_anchored)
  nxt = max_seen + 1
  for i in unanchored:
    while nxt in used:
      nxt += 1
    mapping["W%d" % i] = "W%d" % nxt
    used.add(nxt)
    nxt += 1
  new_max = max([max_seen] + sorted(used)) if used else max_seen
  if not mapping:
    return (pkgs, new_max)

  def _t(node):
    if isinstance(node, str):
      return mapping.get(node, node)
    if isinstance(node, list):
      return [_t(x) for x in node]
    return node
  return (_t(pkgs), new_max)


def _run_stage2_split(s1_json, eff_llm, eff_version, eff_tokens, eff_think, stats):
  """One Stage-2 call per Stage-1 sentence package; join the outputs.

  A failed sentence is skipped (recorded in stats) UNLESS it contains the
  question, in which case the whole Stage 2 fails (returns None).  Each
  split's worlds are renumbered per rule c' (see _renumber_split_worlds)."""
  packages = []
  max_seen = -1
  skipped = []
  stats["s2_splits"] = len(s1_json) if isinstance(s1_json, list) else 0
  for idx, pkg in enumerate(s1_json if isinstance(s1_json, list) else []):
    if not isinstance(pkg, dict):
      continue
    expected_ids = [u.get("unit_id") for u in pkg.get("units", [])
                    if isinstance(u, dict) and u.get("unit_id")]
    s2_input = json.dumps([pkg])

    def _chk(parsed, _pkg=pkg, _ids=tuple(expected_ids)):
      return (_check_stage2(parsed, [_pkg])
              + _check_id_coverage(parsed, list(_ids)))

    sj, _raw, s2_err = _run_stage(2, s2_input, _stage2_sysprompt,
                                  eff_llm, eff_version, eff_tokens, eff_think,
                                  stats, check_fn=_chk)
    pkgs = None
    if isinstance(sj, list) and sj:
      if sj[0] == "and":
        pkgs = [x for x in sj[1:] if isinstance(x, list)]
      elif sj[0] == "@id":
        pkgs = [sj]
    if not pkgs:
      if _package_has_query(pkg):
        _debug_write("S2SPLIT: question sentence %d failed (%s) -> stage 2 fails"
                     % (idx + 1, s2_err))
        return None
      skipped.append(pkg.get("raw") or ("sentence %d" % (idx + 1)))
      _debug_write("S2SPLIT: sentence %d failed (%s) -> skipped" % (idx + 1, s2_err))
      continue
    anchored = _slice_anchored_worlds(pkg)
    pkgs, max_seen = _renumber_split_worlds(pkgs, anchored, max_seen)
    packages.extend(pkgs)
  if skipped:
    stats["s2_split_skipped"] = skipped
  if not packages:
    return None
  _debug_write("S2SPLIT: joined %d packages from %d sentences (%d skipped)"
               % (len(packages), stats["s2_splits"], len(skipped)))
  return ["and"] + packages


# ======== main entry point ========

def parse_text(text, llm=None, version=None, tokens=None, think=None):
  """Parse English text through stage 1 (ASUs) then stage 2 (logic).

  Optional llm/version/tokens/think override the module-level defaults.

  Returns (stage1_json, stage2_json, stats) where:
    - stage1_json is the parsed Stage-1 JSON object, or None on failure.
    - stage2_json is the parsed Stage-2 JSON object, or None on failure.
    - stats is a dict of error/retry counts (printable via print_stats).
  """
  global _stage1_sysprompt, _stage2_sysprompt
  if not combined_enabled and _stage1_sysprompt is None:
    load_prompts()

  eff_llm     = llm     or use_llm
  eff_version = version or llm_version
  eff_tokens  = tokens  or max_tokens
  eff_think   = think if think is not None else use_think

  stats = _make_stats()

  # Input text is already shown by solve.py; no need to repeat here.

  # Original input, before prenorm.  The cross-stage unsatisfiable-guard retry
  # re-reads THIS text (not the prenormed one): prenorm itself can drop the
  # missing word (case 15: prenorm strips "the game" from "created the game the
  # Legend of Zelda"), so the corrective retry must see the original.
  orig_text = text

  # --- experimental pre-Stage-1 normalization ---
  if prenorm_enabled:
    norm = normalize_text(text, eff_llm, eff_version, eff_tokens)
    if norm and norm != text:
      stats["prenorm_text"] = norm
      _debug_write("PRENORM:\n" + norm)
      text = norm

  # --- combined single-stage: one LLM call, English -> logic, no Stage-1 JSON ---
  if combined_enabled:
    load_combined_prompt()
    s2_json, s2_raw, s2_err = _run_stage(2, text, _combined_sysprompt,
                                          eff_llm, eff_version, eff_tokens, eff_think, stats,
                                          check_fn=lambda parsed: _check_stage2(parsed, None))
    _debug_write("COMBINED STAGE " + ("ERROR: " + s2_err if s2_err else "OK"))
    return (None, s2_json, stats)

  import stage_sanity as _ss

  # --- stage 1 then stage 2 (re-runnable once with a corrective hint) ---
  def _stage1_then_stage2(base_text, corrective=""):
    s1in = base_text + corrective
    s1_json, s1_raw, s1_err = _run_stage(1, s1in, _stage1_sysprompt,
                                          eff_llm, eff_version, eff_tokens, eff_think, stats,
                                          check_fn=lambda parsed: _check_stage1(parsed))
    _debug_write("STAGE 1 " + ("ERROR: " + s1_err if s1_err else "OK"))
    if s1_json is None:
      return (None, None)
    # Normalize entity IDs that differ only by sentence-start capitalization.
    _normalize_entity_id_case(s1_json, stats)
    # (entity canon) Aggressively canonicalize entity names across the Stage-1
    # output (ids + text), so the same entity worded several ways becomes one id.
    if canon_entities_enabled:
      s1_json = canonicalize_entity_ids(s1_json, stats)
    # (entity canon) Enable the constant-vs-class / dropped-fact repair check.
    _ss.aggressive_repair = canon_entities_enabled
    if s2split_enabled:
      # -s2split: one Stage-2 call per Stage-1 sentence package, joined.
      s2_json = _run_stage2_split(s1_json, eff_llm, eff_version, eff_tokens,
                                  eff_think, stats)
      _debug_write("STAGE 2 (split) " + ("FAILED" if s2_json is None else "OK"))
    else:
      s2_input = json.dumps(s1_json)
      s2_json, s2_raw, s2_err = _run_stage(2, s2_input, _stage2_sysprompt,
                                            eff_llm, eff_version, eff_tokens, eff_think, stats,
                                            check_fn=lambda parsed: _check_stage2(parsed, s1_json))
      if s2_err:
        _debug_write("STAGE 2 ERROR: " + s2_err)
      else:
        _debug_write("STAGE 2 OK")
    if s2_json is not None:
      # (entity canon) Fold Stage-2 Wikipedia-URL constants into the matching
      # Stage-1 entity id so split constants reunify.
      s2_json = canonicalize_entity_urls(s1_json, s2_json, stats)
    return (s1_json, s2_json)

  s1_json, s2_json = _stage1_then_stage2(text)
  if s1_json is None:
    return (None, None, stats)

  # (entity canon, once) Unsatisfiable-guard cross-stage retry: a rule antecedent
  # names a class/property/relation that nothing states or derives (a likely
  # dropped word, case 15).  Re-read Stage 1 + re-encode Stage 2 with a neutral
  # corrective hint; keep the retry only if it reduces the unsatisfiable guards.
  if crossstage_guard_retry and canon_entities_enabled and s2_json is not None:
    guards = _ss.check_unsatisfiable_guards(s2_json)
    if guards:
      stats["crossstage_guards"] = guards
      _debug_write("UNSATISFIABLE GUARDS: " + str(guards))
      suffix = "\n\n" + _ss.format_guard_retry_suffix(guards)
      ns1, ns2 = _stage1_then_stage2(orig_text, suffix)
      stats["crossstage_retries"] = 1
      # Keep the retry iff it resolved ALL originally-flagged guards (none of
      # the original (kind,name) pairs remain).  New guards it may introduce
      # elsewhere are tolerated; what matters is the targeted recovery.  For a
      # genuinely-absent class (case 156's Greek) the model adds nothing, the
      # guard remains, and the original parse is kept.
      if ns2 is not None and not (set(guards) & set(_ss.check_unsatisfiable_guards(ns2))):
        s1_json, s2_json = ns1, ns2
        stats["crossstage_resolved"] = guards
        _debug_write("CROSS-STAGE RETRY: applied (all flagged guards resolved)")
      else:
        _debug_write("CROSS-STAGE RETRY: no improvement, kept original")

  return (s1_json, s2_json, stats)


# ======== stage runner ========

def _run_stage(stage_nr, input_text, sysprompt, llm, version, tokens, think, stats,
               check_fn=None):
  """Run one LLM stage with JSON checking, fixing, and one retry on bad JSON.

  If check_fn is provided, it is called on the successfully-parsed output
  (check_fn(parsed) -> list[Issue]).  When it reports issues a separate
  sanity-retry loop kicks in: the LLM is re-called with the original input
  plus a suffix describing the flawed output and the issues.  At most two
  sanity retries per stage; retry stops early if an issue persists across
  attempts (see _run_sanity_retry).

  Returns (parsed_json, raw_text, error_or_None).
  """
  key = "s" + str(stage_nr)
  stats[key + "_calls"] += 1

  import llmcall as _llmcall
  actual_llm = llm or use_llm or _llmcall.use_llm
  _debug_write("\n=== stage " + str(stage_nr) + " LLM call (" + actual_llm + ") ===\n")
  _debug_write_json("INPUT:", input_text)

  raw = call_llm(sysprompt, input_text, llm=llm, version=version, max_tokens=tokens, think=think)

  if raw is None:
    stats[key + "_llm_errors"] += 1
    return (None, None, "stage " + str(stage_nr) + " LLM call returned None")

  _debug_write_json("RAW OUTPUT:", raw)

  # --- first parse attempt ---
  parsed, err = _try_parse(raw)
  if parsed is not None:
    return _maybe_sanity_retry(stage_nr, input_text, parsed, raw, check_fn,
                               sysprompt, llm, version, tokens, think, stats)

  stats[key + "_json_errors"] += 1
  _debug_write("JSON parse failed: " + err)

  # --- try fixes ---
  fixed, fixes = fix_json(raw)
  if fixes:
    _debug_write("Fixes applied: " + ", ".join(fixes))
    stats[key + "_json_fixes"] += len(fixes)
    _record_fixes(stats, key, fixes)
    parsed, err = _try_parse(fixed)
    if parsed is not None:
      _debug_write("Fixed JSON parsed OK")
      return _maybe_sanity_retry(stage_nr, input_text, parsed, fixed, check_fn,
                                 sysprompt, llm, version, tokens, think, stats)
    _debug_write("Fixed JSON still invalid: " + err)

  # --- LLM retry ---
  stats[key + "_retry_calls"] += 1
  stats[key + "_retries"].append("json-fail retry: " + (err or "parse error")[:60])
  retry_input = _build_retry_prompt(input_text, raw)
  _debug_write("Retrying stage " + str(stage_nr) + " with error feedback...")

  raw2 = call_llm(sysprompt, retry_input, llm=llm, version=version, max_tokens=tokens, think=think)

  if raw2 is None:
    stats[key + "_llm_errors"] += 1
    stats[key + "_retry_fail"] += 1
    return (None, raw, "stage " + str(stage_nr) + " retry LLM call returned None")

  _debug_write_json("RETRY OUTPUT:", raw2)

  parsed, err = _try_parse(raw2)
  if parsed is not None:
    stats[key + "_retry_ok"] += 1
    return _maybe_sanity_retry(stage_nr, input_text, parsed, raw2, check_fn,
                               sysprompt, llm, version, tokens, think, stats)

  # --- fixes on retry output ---
  fixed2, fixes2 = fix_json(raw2)
  if fixes2:
    _debug_write("Retry fixes applied: " + ", ".join(fixes2))
    stats[key + "_json_fixes"] += len(fixes2)
    _record_fixes(stats, key, fixes2)
    parsed, err = _try_parse(fixed2)
    if parsed is not None:
      stats[key + "_retry_ok"] += 1
      _debug_write("Retry fixed JSON parsed OK")
      return _maybe_sanity_retry(stage_nr, input_text, parsed, fixed2, check_fn,
                                 sysprompt, llm, version, tokens, think, stats)

  stats[key + "_retry_fail"] += 1
  _debug_write("Stage " + str(stage_nr) + " failed after retry: " + err)
  return (None, raw2, "stage " + str(stage_nr) + " JSON invalid after fix and retry: " + err)


# ======== sanity-check retry ========

# Hard cap on total LLM calls per stage for sanity retry (not counting the
# initial call).  Attempt 1 is the first corrective retry; attempt 2 is the
# last.  Beyond that the current best-effort output is returned even if
# issues linger, so the pipeline can proceed.
_SANITY_MAX_RETRIES = 2


def _maybe_sanity_retry(stage_nr, input_text, parsed, raw, check_fn,
                        sysprompt, llm, version, tokens, think, stats):
  """Run the per-stage sanity checker and, if it reports issues, re-call
  the LLM with a corrective prompt.  Returns (parsed, raw, None) — the
  best-effort output regardless of whether the issues were fully fixed
  (the pipeline continues with imperfect output rather than aborting).
  """
  if check_fn is None:
    return (parsed, raw, None)

  key = "s" + str(stage_nr)
  try:
    issues = check_fn(parsed)
  except Exception as e:
    _debug_write("Sanity checker raised exception: " + str(e))
    return (parsed, raw, None)

  if not issues:
    return (parsed, raw, None)

  # Track issue fingerprints across attempts to detect persistence.
  prev_fingerprints = _issue_fingerprints(issues)
  current_parsed, current_raw = parsed, raw
  current_issues = issues

  for attempt in range(1, _SANITY_MAX_RETRIES + 1):
    stats[key + "_sanity_retries"] += 1
    _debug_write("Stage " + str(stage_nr) + " sanity retry #" + str(attempt)
                 + " with " + str(len(current_issues)) + " issue(s)")
    # Record a short message summarising why the retry fired: the issue KINDS
    # only (descriptions are long and live in the corrective prompt / debug log).
    kinds = [(getattr(it, "kind", "") or "issue") for it in current_issues]
    stats[key + "_retries"].append("sanity #" + str(attempt) + ": " + ", ".join(kinds))
    suffix = _format_retry_suffix(current_issues, current_parsed)
    retry_input = input_text + suffix

    raw_new = call_llm(sysprompt, retry_input,
                       llm=llm, version=version, max_tokens=tokens, think=think)
    if raw_new is None:
      stats[key + "_sanity_fail"] += 1
      _debug_write("Stage " + str(stage_nr) + " sanity retry #" + str(attempt)
                   + " LLM returned None; stopping")
      break
    _debug_write_json("SANITY RETRY #" + str(attempt) + " OUTPUT:", raw_new)

    # Parse + JSON-fix fallback (mirrors the _run_stage primary path).
    parsed_new, perr = _try_parse(raw_new)
    raw_final = raw_new
    if parsed_new is None:
      fixed_new, fixes_new = fix_json(raw_new)
      if fixes_new:
        stats[key + "_json_fixes"] += len(fixes_new)
        _record_fixes(stats, key, fixes_new)
        parsed_new, perr = _try_parse(fixed_new)
        if parsed_new is not None:
          raw_final = fixed_new

    if parsed_new is None:
      stats[key + "_sanity_fail"] += 1
      _debug_write("Stage " + str(stage_nr) + " sanity retry #" + str(attempt)
                   + " JSON invalid: " + perr + "; stopping")
      break

    current_parsed, current_raw = parsed_new, raw_final

    try:
      new_issues = check_fn(parsed_new)
    except Exception as e:
      _debug_write("Sanity checker raised exception on retry: " + str(e))
      break

    if not new_issues:
      stats[key + "_sanity_ok"] += 1
      _debug_write("Stage " + str(stage_nr) + " sanity retry #" + str(attempt)
                   + " produced clean output")
      return (current_parsed, current_raw, None)

    new_fingerprints = _issue_fingerprints(new_issues)
    # Persistence: any issue from the previous attempt still present → stop.
    if new_fingerprints & prev_fingerprints:
      stats[key + "_sanity_fail"] += 1
      _debug_write("Stage " + str(stage_nr) + " sanity retry #" + str(attempt)
                   + " — issue(s) persist across attempts; stopping")
      break

    # All-new issues: try once more (if cap not reached).
    prev_fingerprints = new_fingerprints
    current_issues = new_issues

  # Out of retries or stopped on persistence.  Return the best-effort output;
  # downstream passes handle residual imperfections (or the query fails in
  # ways we already recognise).
  return (current_parsed, current_raw, None)


# ======== JSON fixing ========

def fix_json(s):
  """Attempt to repair common JSON errors in LLM output.

  Returns (fixed_string, list_of_fix_names) where list_of_fix_names is
  non-empty if any fix was applied and the result is valid JSON, or
  (best_attempt, None) if all fixes failed.
  """
  s = s.strip()
  applied = []

  # 0. Strip preamble text before JSON (e.g. LLM planning/reasoning output)
  if not s.startswith(("```", "[", "{")):
    fence = re.search(r'^```(?:json)?\s*$', s, re.MULTILINE)
    if fence:
      s = s[fence.start():]
      applied.append("stripped preamble before fence")
    else:
      m = re.search(r'^[\[{]', s, re.MULTILINE)
      if m:
        s = s[m.start():]
        applied.append("stripped preamble before JSON")
  if _ok(s): return (s, applied or None)

  # 1. Strip markdown code fences (```json...``` or ```...```)
  if s.startswith("```"):
    lines = s.splitlines()
    if lines[0].startswith("```"):
      lines = lines[1:]
    if lines and lines[-1].strip() == "```":
      lines = lines[:-1]
    s = "\n".join(lines).strip()
    applied.append("stripped markdown fence")
  if _ok(s): return (s, applied or None)

  # 2. Remove null / None values appearing as bare array elements
  s2 = s
  for pattern, repl in [
    (r",\s*null\s*(?=[\],])", ""),
    (r"(?<=[\[,])\s*null\s*,", ""),
    (r",\s*None\s*(?=[\],])", ""),
    (r"(?<=[\[,])\s*None\s*,", ""),
  ]:
    s2 = re.sub(pattern, repl, s2)
  if s2 != s:
    s = s2
    applied.append("removed null/None elements")
  if _ok(s): return (s, applied or None)

  # 3. Replace Python literals: True/False/None -> true/false/null
  s2 = re.sub(r'\bTrue\b', 'true', re.sub(r'\bFalse\b', 'false',
              re.sub(r'\bNone\b', 'null', s)))
  if s2 != s:
    s = s2
    applied.append("replaced Python literals")
  if _ok(s): return (s, applied or None)

  # 4. Strip any leading/trailing non-JSON text (keep from first [ or { to last ] or })
  m = re.search(r'[\[{]', s)
  if m:
    start = m.start()
    # find matching end from the right
    end = max(s.rfind("]"), s.rfind("}"))
    if end > start:
      s2 = s[start:end + 1]
      if s2 != s:
        s = s2
        applied.append("stripped non-JSON wrapper text")
  if _ok(s): return (s, applied or None)

  # 5. Add missing commas between adjacent array/object elements (] [ and } {)
  s2 = re.sub(r'\]\s*\[', '], [', s)
  s2 = re.sub(r'\}\s*\{', '}, {', s2)
  if s2 != s:
    s = s2
    applied.append("added missing commas between adjacent elements")
  if _ok(s): return (s, applied or None)

  # 6. Remove trailing commas before ] or }
  s2 = re.sub(r',\s*([\]}])', r'\1', s)
  if s2 != s:
    s = s2
    applied.append("removed trailing commas")
  if _ok(s): return (s, applied or None)

  # 7. Fix ]"] -> ]] (a specific bracket-quote-bracket glitch)
  if ']"]' in s:
    s2 = s.replace(']"]', ']]')
    if s2 != s:
      s = s2
      applied.append('fixed ]\"][ glitch')
  if _ok(s): return (s, applied or None)

  # 7a. Quote bare Stage-2-style variable identifiers in JSON array context.
  # Some LLMs (notably gpt) emit ["ask","X",[..., ["=", ..., X]]] where the
  # interior X is left as a bare identifier instead of "X".  The bare token
  # only appears in array element positions (between [/, on the left and
  # ,/] on the right), and is a single uppercase letter optionally followed
  # by digits (Stage-2 variable convention: X, Y, E, S1, ...).  Quoting it
  # leaves quoted strings unchanged because the lookbehind requires [ or ,.
  s2 = re.sub(r'(?<=[\[,])(\s*)([A-Z][0-9]*)(\s*)(?=[,\]])', r'\1"\2"\3', s)
  if s2 != s:
    s = s2
    applied.append("quoted bare variable identifiers")
  if _ok(s): return (s, applied or None)

  # 8. Remove junk after the top-level closing bracket (fix_internal)
  s2 = _fix_internal(s)
  if s2 != s:
    s = s2
    applied.append("removed content after top-level close bracket")
  if _ok(s): return (s, applied or None)

  # 9. Balance square brackets
  opens  = s.count("[")
  closes = s.count("]")
  if opens > closes:
    s = s + "]" * (opens - closes)
    applied.append("added " + str(opens - closes) + " closing bracket(s)")
  elif closes > opens:
    excess = closes - opens
    # trim from the right
    tmp = s
    while excess > 0 and tmp.endswith("]"):
      tmp = tmp[:-1]
      excess -= 1
    if tmp != s:
      s = tmp
      applied.append("removed " + str(closes - opens) + " excess closing bracket(s)")
  if _ok(s): return (s, applied or None)

  # 10. Re-apply fix_internal after bracket balance (may expose new top-level junk)
  s2 = _fix_internal(s)
  if s2 != s:
    s = s2
    applied.append("fix_internal pass 2")
    opens  = s.count("[")
    closes = s.count("]")
    if opens > closes:
      s = s + "]" * (opens - closes)
      applied.append("re-balanced brackets after fix_internal pass 2")
  if _ok(s): return (s, applied or None)

  return (s, None)


def _fix_internal(s):
  """Recursively remove content that appears after the top-level closing bracket.

  Handles cases like  [...][...] or [...] "trailing text"  produced by LLMs.
  """
  in_quotes = False
  depth = 0
  for i, c in enumerate(s):
    if c == '"' and not in_quotes:
      in_quotes = True
      continue
    if c == '"' and in_quotes:
      in_quotes = False
      continue
    if in_quotes:
      continue
    if c == "[":
      depth += 1
    elif c == "]":
      depth -= 1
      if depth == 0 and i < len(s) - 1 and s[i + 1:].strip():
        # There is non-whitespace after the closing bracket: remove it and recurse
        return _fix_internal(s[:i] + s[i + 1:])
  return s


def _ok(s):
  """Return True if s is valid JSON."""
  try:
    json.loads(s)
    return True
  except:
    return False


def _try_parse(s):
  """Try json.loads; return (obj, None) on success or (None, error_str) on failure."""
  try:
    return (json.loads(s), None)
  except Exception as e:
    return (None, str(e))


# ======== entity ID case normalization ========

import re as _re

_ID_WITH_NUMBER_RE = _re.compile(r'^(.+)\s+(\d+)$')

def _normalize_entity_id_case(s1_json, stats=None):
  """Normalize entity IDs that differ only by sentence-start capitalization.

  When the same entity appears as "Car 1" (sentence start) and "car 1"
  (mid-sentence), replace the capitalized form with the lowercase form.

  Only fires when ALL conditions hold:
    (a) Two IDs differ only in the first character's case, rest identical
    (b) The ID contains a number suffix (e.g., "Car 1", not bare "Car")
    (c) The capitalized form appears as the first word of a raw sentence

  Modifies s1_json in place.
  """
  if not isinstance(s1_json, list):
    return

  # Collect all entity IDs and raw sentence texts.
  all_ids = set()
  raw_sentences = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "")
    if raw:
      raw_sentences.append(raw)
    for unit in pkg.get("units", []):
      for ent in unit.get("entities", []):
        eid = ent.get("id")
        if isinstance(eid, str):
          all_ids.add(eid)

  # Find pairs differing only by first-char case.
  replacements = {}  # capitalized_id → lowercase_id
  for eid in all_ids:
    if not eid or not eid[0].isupper():
      continue
    m = _ID_WITH_NUMBER_RE.match(eid)
    if not m:
      continue  # condition (b): must have number
    lower_form = eid[0].lower() + eid[1:]
    if lower_form not in all_ids:
      continue  # condition (a): lowercase form must exist
    # condition (c): capitalized form must be first word of a raw sentence
    first_word = eid.split()[0]  # e.g., "Car"
    is_sentence_start = any(r.startswith(first_word + " ") or r.startswith(first_word + "'")
                            for r in raw_sentences)
    if is_sentence_start:
      replacements[eid] = lower_form

  if not replacements:
    return

  # Apply replacements throughout all entities, definites, actions, etc.
  _replace_ids_in_s1(s1_json, replacements)
  if stats is not None:
    stats["s1_fixes"].append("entity-id case normalized")


def _replace_ids_in_s1(obj, replacements):
  """Recursively replace entity ID strings in Stage 1 JSON."""
  if isinstance(obj, dict):
    for key in obj:
      val = obj[key]
      if isinstance(val, str) and val in replacements:
        obj[key] = replacements[val]
      elif isinstance(val, (dict, list)):
        _replace_ids_in_s1(val, replacements)
  elif isinstance(obj, list):
    for i, val in enumerate(obj):
      if isinstance(val, str) and val in replacements:
        obj[i] = replacements[val]
      elif isinstance(val, (dict, list)):
        _replace_ids_in_s1(val, replacements)


# ======== retry prompt ========

def _build_retry_prompt(original_input, bad_output):
  return (
    "The output you produced is not valid JSON. "
    "Please try again and output ONLY valid JSON, with no additional text.\n\n"
    "Original input:\n" + original_input + "\n\n"
    "Your invalid output:\n" + bad_output
  )


# ======== stats ========

def _make_stats():
  keys = [
    "s1_calls", "s1_llm_errors", "s1_json_errors", "s1_json_fixes",
    "s1_retry_calls", "s1_retry_ok", "s1_retry_fail",
    "s1_sanity_retries", "s1_sanity_ok", "s1_sanity_fail",
    "s2_calls", "s2_llm_errors", "s2_json_errors", "s2_json_fixes",
    "s2_retry_calls", "s2_retry_ok", "s2_retry_fail",
    "s2_sanity_retries", "s2_sanity_ok", "s2_sanity_fail",
  ]
  d = {k: 0 for k in keys}
  # Detail lists for runtests: fix names actually applied and retry messages.
  # "stripped markdown fence" is excluded from fix lists per spec.
  d["s1_fixes"] = []
  d["s2_fixes"] = []
  d["s1_retries"] = []
  d["s2_retries"] = []
  return d


# Cosmetic wrapper-stripping fixes that are NOT registered (LLM-output noise,
# not a structural repair): the markdown fence and the preamble before the JSON
# header.  Everything else from fix_json IS registered (prefixed "json: ").
_SKIP_FIX_NAMES = {
    "stripped markdown fence",
    "stripped preamble before fence",
    "stripped preamble before JSON",
}


def _record_fixes(stats, key, fixes):
  """Append non-skipped JSON fix names (prefixed "json: ") to the stage's
  fix list.  All fixes here originate from fix_json (JSON-syntax repairs)."""
  if not fixes:
    return
  for f in fixes:
    if f not in _SKIP_FIX_NAMES:
      stats[key + "_fixes"].append("json: " + f)


def print_stats(stats):
  """Print a human-readable summary of parse stats."""
  print("Parse stats:")
  print("  Stage 1: calls={s1_calls}  llm_errors={s1_llm_errors}"
        "  json_errors={s1_json_errors}  fixes={s1_json_fixes}"
        "  retries={s1_retry_calls}  retry_ok={s1_retry_ok}  retry_fail={s1_retry_fail}"
        "  sanity_retries={s1_sanity_retries}  sanity_ok={s1_sanity_ok}  sanity_fail={s1_sanity_fail}".format(**stats))
  print("  Stage 2: calls={s2_calls}  llm_errors={s2_llm_errors}"
        "  json_errors={s2_json_errors}  fixes={s2_json_fixes}"
        "  retries={s2_retry_calls}  retry_ok={s2_retry_ok}  retry_fail={s2_retry_fail}"
        "  sanity_retries={s2_sanity_retries}  sanity_ok={s2_sanity_ok}  sanity_fail={s2_sanity_fail}".format(**stats))


def add_stats(total, delta):
  """Accumulate delta into total stats dict (for multi-text runs)."""
  for k in total:
    total[k] += delta.get(k, 0)
  return total


# ======== debug helpers ========

def _debug_write(msg):
  if debug:
    print(msg)
  if debug_file:
    try:
      with open(debug_file, "a") as f:
        f.write(msg + "\n")
    except Exception as e:
      print("Could not write to debug file:", e)


def _debug_write_json(label, text):
  """Write label + text to the debug output.  If text is valid JSON, pretty-print it."""
  try:
    obj = json.loads(text)
    msg = label + "\n" + pretty.pp_str(obj)
  except Exception:
    msg = label + "\n" + text
  _debug_write(msg)


def _print_error(msg):
  print("llmparse error:", msg)


# =========== the end ==========
