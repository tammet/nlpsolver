# Shared utilities for proof rendering: entity naming, Skolem resolution,
# ambiguity detection, render context state.
#
# Used by proof_english.py, proof_logic.py, procproofs.py, proof_explain.py.
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
#-----------------------------------------------------------------

import json
import re

from lc_clausify import is_skolem_const, is_skolem_fn, skolem_type_from_name

from linguistics import (
  indef_article  as _indef_article,
  conjugate_verb as _conjugate_verb,
  make_comparative as _make_comparative,
  to_gerund      as _to_gerund,
  looks_like_verb as _looks_like_verb,
  PREPOSITIONS   as _PREPOSITIONS,
)


# ======== $ans context-arg filtering ========

# Time tokens and world-state pattern that are pipeline residuals, not answer content.
_ANS_TIME_TOKENS = frozenset({"present", "past", "future"})
_ANS_WORLD_RE    = re.compile(r'^W\d+$')

def _ans_display_args(ans_args):
  """Strip context residuals from a $ans arg list, keeping only meaningful args.

  Filtered out: world-state tokens (W0, W1, ...), time tokens (present/past/future),
  and free-variable references (?:X, ?:X3, ...).
  Kept: entity constants, prepositions (for where-queries), numeric values, etc.
  """
  kept = []
  for a in ans_args:
    if not isinstance(a, str):
      kept.append(a)
      continue
    if a.startswith("?"):               # free variable: ?:X, ?:X3, ?:Y3, ...
      continue
    if _ANS_WORLD_RE.match(a):          # world state: W0, W1, ...
      continue
    if a in _ANS_TIME_TOKENS:           # time token
      continue
    kept.append(a)
  return kept


# ======== render context (all per-proof state) ========

class RenderContext:
  """Bundles all per-proof mutable state into one object.

  Avoids fragile module-level globals that can leak between proofs if a
  caller forgets to call one of the reset functions.
  """
  __slots__ = (
    "entity_map",          # entity id -> display name (from stage-1 JSON)
    "ambiguous_bases",     # set of proper-name bases with 2+ distinct numbers
    "ambiguous_url_names", # set of URL display names mapping to 2+ URLs
    "skolem_types",        # skN -> type string from isa(TYPE,skN)
    "skolem_fn_verbs",     # str(fn_term) -> verb string
    "skolem_fn_actors",    # str(fn_term) -> actor string
    "skolem_fn_targets",   # str(fn_term) -> target string
    "skolem_fn_types",     # sk_name -> object type from isa(TYPE,[sk_name,...])
    "skolem_introduced",   # set of skN names already shown with "some TYPE" prefix
    "skolem_display",      # skN -> short display name like "act1"
    "var_display",         # raw var "?:2006" -> short display name "E1"
  )
  def __init__(self):
    self.entity_map          = {}
    self.ambiguous_bases     = set()
    self.ambiguous_url_names = set()
    self.skolem_types        = {}
    self.skolem_fn_verbs     = {}
    self.skolem_fn_actors    = {}
    self.skolem_fn_targets   = {}
    self.skolem_fn_types     = {}
    self.skolem_introduced   = set()
    self.skolem_display      = {}
    self.var_display          = {}


# Module-level context instance, reset per proof.
_ctx = RenderContext()


# ======== public API (backward-compatible thin wrappers) ========

def set_entity_map(emap):
  """Install a new entity display-name map for the current proof."""
  _ctx.entity_map = emap if isinstance(emap, dict) else {}

def get_entity_display(val):
  """Return the entity_map display name for val, or None if not mapped."""
  return _ctx.entity_map.get(val)

def get_skolem_type(sk_name):
  """Return the type string for a Skolem constant (e.g. 'sk0' → 'house'), or None."""
  return _ctx.skolem_types.get(sk_name)

def get_skolem_fn_type(fn_name):
  """Return the type string for a Skolem function name (e.g. 'sk0' → 'house'), or None."""
  return _ctx.skolem_fn_types.get(fn_name)

def compute_ambiguity(obj):
  """Scan obj and populate ambiguous-name sets in the current context."""
  base_numbers = {}
  url_names    = {}
  _scan_constants(obj, base_numbers, url_names)
  _ctx.ambiguous_bases     = {b.lower() for b, nums in base_numbers.items() if len(nums) > 1}
  _ctx.ambiguous_url_names = {n for n, urls in url_names.items()    if len(urls)  > 1}

def _scan_skolem_atom(atom):
  """Extract Skolem type/verb/actor/target info from a single atom."""
  if not isinstance(atom, list) or len(atom) < 3:
    return
  pred = atom[0]
  if not isinstance(pred, str):
    return
  # Strip negation prefix for matching
  base_pred = pred[1:] if pred.startswith("-") else pred
  if base_pred == "isa" and isinstance(atom[2], str) and is_skolem_const(atom[2]):
    _ctx.skolem_types.setdefault(atom[2], str(atom[1]))
  elif base_pred == "isa" and _is_skolem_fn(atom[2]):
    _ctx.skolem_fn_types.setdefault(atom[2][0], str(atom[1]))
  elif base_pred == "has type" and _is_skolem_fn(atom[1]):
    _ctx.skolem_fn_verbs.setdefault(str(atom[1]), str(atom[2]))
  elif base_pred == "has actor" and _is_skolem_fn(atom[1]):
    _ctx.skolem_fn_actors.setdefault(str(atom[1]), str(atom[2]))
  elif base_pred == "has target" and _is_skolem_fn(atom[1]):
    _ctx.skolem_fn_targets.setdefault(str(atom[1]), str(atom[2]))


def compute_skolem_types(proof, logic=None):
  """Scan proof steps (and optionally the logic clause list) to populate
  Skolem lookup tables in the current context.

  When logic is provided, it is scanned first so that Skolem types from
  assertion clauses (which may not appear in the proof) are available
  for rendering.  Proof steps are scanned second and can override.

  Also builds display-name maps for Skolem constants (sk0 → act1) and
  long/numeric prover variables (?:2006 → E1).
  """
  _ctx.skolem_types      = {}
  _ctx.skolem_fn_verbs   = {}
  _ctx.skolem_fn_actors  = {}
  _ctx.skolem_fn_targets = {}
  _ctx.skolem_fn_types   = {}
  _ctx.skolem_introduced = set()
  _ctx.skolem_display    = {}
  _ctx.var_display       = {}

  # Pass 1: scan logic clause list (if provided) for Skolem types.
  if logic and isinstance(logic, list):
    for obj in logic:
      if not isinstance(obj, dict) or "@logic" not in obj:
        continue
      clause = obj["@logic"]
      if not isinstance(clause, list) or not clause:
        continue
      if isinstance(clause[0], list):
        # Multi-literal clause (rule) — scan each atom
        for atom in clause:
          _scan_skolem_atom(atom)
      else:
        # Single-atom clause
        _scan_skolem_atom(clause)

  # Pass 2: scan proof steps (may override with more specific info).
  for step in proof:
    clause = step[2] if len(step) > 2 else []
    if not isinstance(clause, list):
      continue
    for atom in clause:
      _scan_skolem_atom(atom)

  # Build Skolem display names: sk0 → act1 (for activity), evt1 (for event), etc.
  _TYPE_ABBREV = {"activity": "act", "event": "event", "set": "set"}
  type_counters = {}
  def _sk_sort_key(s):
    # Extract numeric part: "sk0" → 0, "sk0_car" → 0
    digits = re.match(r'^sk(\d+)', s)
    return int(digits.group(1)) if digits else 0
  for sk in sorted(_ctx.skolem_types.keys(), key=_sk_sort_key):
    typ = _ctx.skolem_types[sk]
    abbrev = _TYPE_ABBREV.get(typ.lower(), typ.lower()[:3])
    n = type_counters.get(abbrev, 0) + 1
    type_counters[abbrev] = n
    _ctx.skolem_display[sk] = abbrev + str(n)

  # Build variable display names for long/numeric prover variables.
  # Collect all variables across the proof, rename ugly ones.
  all_vars = set()
  for step in proof:
    clause = step[2] if len(step) > 2 else []
    if isinstance(clause, list):
      _collect_vars(clause, all_vars)
  # Only rename variables that are long (>2 chars after ?:) or purely numeric.
  _SHORT_VARS = {"X", "Y", "Z", "W", "U", "V", "E", "N", "S", "K"}
  var_counter = {}
  for v in sorted(all_vars):
    bare = v[2:]  # strip "?:"
    if bare in _SHORT_VARS or (len(bare) <= 2 and bare[0].isalpha()):
      continue  # already short enough
    # Pick a letter based on variable role heuristics.
    if bare.isdigit():
      letter = "E"  # numeric vars are typically event-related
    elif bare[0].isalpha():
      letter = bare[0].upper()  # keep the first letter
    else:
      letter = "V"
    n = var_counter.get(letter, 0) + 1
    var_counter[letter] = n
    display = letter + str(n) if n > 1 or letter in var_counter else letter + str(n)
    _ctx.var_display[v] = display


def _collect_vars(obj, result):
  """Recursively collect all ?:-prefixed variable strings from a clause."""
  if isinstance(obj, str):
    if obj.startswith("?:"):
      result.add(obj)
  elif isinstance(obj, list):
    for el in obj:
      _collect_vars(el, result)


# ======== ambiguity scanning ========

def _scan_constants(obj, base_numbers, url_names):
  """Recursively scan obj for proper-name constants and URL constants."""
  if isinstance(obj, str):
    if obj.startswith("?:"):
      return
    # Strip the UNA `#:` marker before classifying so ambiguity tracking
    # uses bare entity bases ("John") rather than prefixed ones ("#:John").
    if obj.startswith("#:"):
      obj = obj[2:]
    if obj.startswith("http://") or obj.startswith("https://"):
      name = _extract_url_name(obj)
      url_names.setdefault(name, set()).add(obj)
      return
    m = re.match(r'^(.*\S)\s+(\d+)$', obj)
    if m:
      base = m.group(1)
      # Track both proper-name and common-noun bases for ambiguity detection.
      base_numbers.setdefault(base, set()).add(int(m.group(2)))
  elif isinstance(obj, list):
    for el in obj:
      _scan_constants(el, base_numbers, url_names)
  elif isinstance(obj, dict):
    for v in obj.values():
      _scan_constants(v, base_numbers, url_names)


# ======== Skolem helpers ========

def _is_skolem_fn(val):
  """Return True if val is a Skolem function term: a list whose first element
  is a Skolem name (e.g. ["sk0", "Greg 2", "Mike 1"])."""
  return is_skolem_fn(val)


# ======== URL helpers ========

def _extract_url_name(url):
  """Extract a human-readable display name from a URL.

  Takes the last non-empty path segment, strips URL encoding, converts
  underscores to spaces.  Falls back to the full URL if no segment found.

  Examples:
    https://en.wikipedia.org/wiki/Paris            -> "Paris"
    https://en.wikipedia.org/wiki/New_York_City    -> "New York City"
    https://dbpedia.org/resource/Eiffel_Tower      -> "Eiffel Tower"
  """
  try:
    # Drop query string and fragment
    path = url.split("?")[0].split("#")[0]
    segments = [s for s in path.split("/") if s]
    # segments[0] is the scheme-less domain; name is the last path component
    # (index >= 2 means there is at least one path element after the domain)
    if segments:
      name = segments[-1]
    else:
      return url
    # Basic URL decoding and underscore expansion
    name = name.replace("_", " ").replace("%20", " ").replace("%27", "'")
    return name if name else url
  except Exception:
    return url


# ======== constants ========

# Safe letters for labelling noun-phrase constants.
# Skips letters that are common stage-2 variable names (E, K, N, S, V, X, Y, Z)
# so that "car B" can never be confused with a proof variable.
_SAFE_LETTERS = "ABCDFGHIJLMPQRTUW"   # 17 slots; enough for any realistic proof

# Prepositions used as relations in ["is rel2", RELATION, E1, E2].
# These render as "E1 is RELATION E2" (no "of").
# Anything else (relational nouns: parent, part, member, …) renders as
# "E1 is RELATION of E2".
_DEGREE_TABLE = {
  "none":    ("",           "indef"),   # "a nice person"
  "":        ("",           "indef"),
  "regular": ("",           "indef"),
  "high":    ("very ",      "indef"),   # "a very nice person"
  "low":     ("slightly ",  "indef"),   # "a slightly nice person"
  "more":    ("more ",      "indef"),   # "a more nice person"
  "most":    ("most ",      "def"),     # "the most nice person"
  "less":    ("less ",      "indef"),
  "least":   ("least ",     "def"),     # "the least nice person"
}


def _is_var_display(s):
  """Return True if s looks like a prover variable display name (e.g. 'X', 'V2006', 'R')."""
  return bool(re.match(r'^(V\d+|[A-Z]\d*)$', s))


def _degree_parts(degree):
  """Return (adverb_str, article_type) for a degree value."""
  key = str(degree).lower()
  if key in _DEGREE_TABLE:
    return _DEGREE_TABLE[key]
  # Numeric degree (0..1 or 0..100): map to rough adverbs
  try:
    n = float(key)
    if n > 0.75:
      return ("very ",     "indef")
    if n < 0.25:
      return ("slightly ", "indef")
    return ("",            "indef")
  except ValueError:
    return (key + " ",     "indef")


# ======== entity naming ========

def _skolem_fn_arg_display(arg):
  """Render a Skolem fn argument keeping the raw entity id so "Mike 1"
  stays "Mike 1" (not trimmed to "Mike") — the Skolem fn term identifies
  a specific instance and the number disambiguates it.  Variables are
  stripped of "?:" prefix; UNA `#:` prefix is also stripped.
  """
  if isinstance(arg, str):
    if arg.startswith("#:"): return arg[2:]
    if arg.startswith("?:"): return arg[2:]
    return arg
  return entity_name(arg)


def _skolem_fn_short_name(term):
  """Short identifier-style rendering of a Skolem fn for later mentions:
  "sk0 of Mike 1" / "sk0 of X" / bare "sk0" when there are no args.  Used
  on second-and-after mentions inside the same clause to avoid repeating
  the full noun-phrase form.
  """
  if not isinstance(term, list) or not term:
    return "the event"
  fn_name = term[0] if isinstance(term[0], str) else str(term[0])
  if len(term) > 1:
    return fn_name + " of " + ", ".join(_skolem_fn_arg_display(a)
                                        for a in term[1:])
  return fn_name


def _skolem_fn_to_name(term):
  """Render a Skolem function term ["sk0", arg1, arg2, ...] as English.

  Always shows the function-name + ground args so the term's identity is
  visible in the proof (e.g. "sk0 of Mike 1").  Uses the verb-gerund as a
  noun-phrase prefix when known: "the flying event sk0 of Mike 1".

  Examples (event Skolem, verb known):
    ["sk0","Mike 1"]           -> "the flying event sk0 of Mike 1"
    ["sk0","?:X"]              -> "the flying event sk0"
  Examples (object Skolem, type="roof"):
    ["sk0","$some_car"]        -> "the roof sk0 of some car"
    ["sk0","?:X"]              -> "the roof sk0"
  Examples (no type info):
    ["sk0","Mike 1"]           -> "the event sk0 of Mike 1"
    ["sk0"]                    -> "the event sk0"
  """
  if not isinstance(term, list) or not term:
    return "the event"
  fn_name = term[0] if isinstance(term[0], str) else str(term[0])
  fn_args = term[1:]
  if fn_args:
    args_str = ", ".join(_skolem_fn_arg_display(a) for a in fn_args)
    suffix = " " + fn_name + " of " + args_str
  else:
    suffix = " " + fn_name

  key = str(term)
  verb = _ctx.skolem_fn_verbs.get(key)
  if verb:
    return "the " + _to_gerund(verb) + " event" + suffix
  obj_type = _ctx.skolem_fn_types.get(fn_name)
  if obj_type:
    return "the " + obj_type + suffix
  return "the event" + suffix


def entity_name(val, with_url=False, proof_mode=False):
  """Display name for a logic constant or variable.

  - Skolem functions (lists)  -> "the eating by Greg of Mike" etc.
  - Variables (?:X)           -> strip prefix -> "X"
  - URL constants             -> extract last path segment ->
                                   "Paris" or "Paris (https://...)" depending
                                   on with_url and _ctx.ambiguous_url_names
  - Proper-name constants     -> strip trailing number -> "John 1" -> "John"
                                 (keeps number when base is in _ctx.ambiguous_bases)
  - Noun-phrase constants     -> replace number with safe letter ->
                                 "car 2" -> "car B",  "dog 1" -> "dog A"

  with_url=True   : append full URL in parentheses for URL constants
                    (used in proof steps for traceability)
  with_url=False  : omit URL unless the display name is ambiguous
                    (used in answer line for readability)
  proof_mode=True : skip entity_map for single common-noun entities to avoid
                    qualifier-predicate redundancy in proof steps (e.g.
                    "the very big mouse is very big" instead of
                    "the very big mouse is a very big mouse")
  """
  # --- Shared handling for non-string types (both JSON and non-JSON modes) ---
  import globals as _g
  json_mode = _g.options.get("json_flag") and proof_mode

  # (ultracoarse2) role-tagged event object: ["eventprop", role, value] -> render
  # the inner value, dropping the role label (it is a disambiguation tag only).
  if isinstance(val, list) and len(val) == 3 and val[0] == "eventprop":
    val = val[2]

  # Skolem functions: ["sk0", "Greg 2", ...] -> English event description
  if _is_skolem_fn(val):
    return _skolem_fn_to_name(val)
  # Complex list terms: $count, $setof, arithmetic
  if isinstance(val, list) and val:
    from proof_english import render_term_english
    return render_term_english(val, proof_mode=proof_mode)
  if not isinstance(val, str):
    return str(val)

  # --- UNA prefix: strip `#:` so display name matches the raw entity id. ---
  # All later branches (entity_map lookup, regex parsing, etc.) treat the
  # bare form. Entity ids are wrapped only inside the prover input.
  if val.startswith("#:"):
    val = val[2:]

  # --- Variables: use display map, then fallback ---
  if val.startswith("?:"):
    orig = val
    if orig in _ctx.var_display:
      return _ctx.var_display[orig]
    bare = val[2:]
    if bare.isdigit():
      return "V" + bare
    return bare

  # --- Population constants: $some_not_* / $some_* ---
  if val.startswith("$some_not_"):
    noun = val[len("$some_not_"):].replace("_", " ")
    return _indef_article(noun) + " non-" + noun
  if val.startswith("$some_"):
    noun = val[len("$some_"):].replace("_", " ")
    return _indef_article(noun) + " " + noun

  # --- Skolem constants: sk0, sk1, ... ---
  if is_skolem_const(val):
    display = _ctx.skolem_display.get(val, val)
    typ = _ctx.skolem_types.get(val)
    if typ:
      if val in _ctx.skolem_introduced:
        return display
      _ctx.skolem_introduced.add(val)
      return "some " + typ + " " + display
    return display

  # --- JSON mode: keep raw entity IDs (e.g. "John 1") for traceability ---
  if json_mode:
    return val

  # --- Non-JSON mode: cosmetic entity name rendering ---

  # Check entity map: prefer the user's original phrasing for answer display.
  # In proof_mode, skip entity_map for single (non-ambiguous) common-noun
  # entities — their qualifier adjectives often duplicate predicate content.
  if val in _ctx.entity_map:
    if proof_mode:
      m = re.match(r'^(.*\S)\s+(\d+)$', val)
      if m and m.group(1)[:1].islower() and m.group(1).lower() not in _ctx.ambiguous_bases:
        pass  # fall through to default "the NOUN" rendering below
      else:
        return _ctx.entity_map[val]
    else:
      name = _ctx.entity_map[val]
      if with_url and (val.startswith("http://") or val.startswith("https://")):
        return name + " (" + val + ")"
      return name
  # URL constant
  if val.startswith("http://") or val.startswith("https://"):
    name = _extract_url_name(val)
    if with_url or name in _ctx.ambiguous_url_names:
      return name + " (" + val + ")"
    return name
  m = re.match(r'^(.*\S)\s+(\d+)$', val)
  if not m:
    return val
  base = m.group(1)
  n    = int(m.group(2))
  if base[:1].isupper():
    # Proper name — keep the number when multiple entities share the same base
    # (e.g. "John 1" vs "John 3"); drop it when there is only one "John".
    if base.lower() in _ctx.ambiguous_bases:
      return base + " " + str(n)
    return base
  # Noun-phrase constant — replace number with a safe letter
  if 1 <= n <= len(_SAFE_LETTERS):
    label = _SAFE_LETTERS[n - 1]        # 1->A, 2->B, 3->C, 4->D, 5->F, …
  else:
    label = str(n)                       # fallback for very large indices
  return base + " " + label


