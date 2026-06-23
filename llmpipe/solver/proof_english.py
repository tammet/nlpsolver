# Atom-to-English rendering for proof explanations.
#
# Converts CNF proof atoms and clauses into readable English sentences.
# Table-driven predicate dispatch via _PRED_TABLE.
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

from lc_clausify import is_skolem_const, is_skolem_fn, looks_like_var, is_world_constant

from linguistics import (
  indef_article  as _indef_article,
  conjugate_verb as _conjugate_verb,
  make_comparative as _make_comparative,
  to_gerund      as _to_gerund,
  looks_like_verb as _looks_like_verb,
  PREPOSITIONS   as _PREPOSITIONS,
)

from proof_utils import (
  entity_name, _ctx, _degree_parts, _is_var_display,
  _ans_display_args, _SAFE_LETTERS, _skolem_fn_short_name,
)

import globals as _g


def ans_atom_name(atom):
  """Return the display name from a $ans atom like ["$ans", "John 1"].

  Used for the answer line — URLs appear without the parenthetical URL
  unless the display name is ambiguous (maps to 2+ different URLs).
  """
  if not isinstance(atom, list) or len(atom) < 2:
    return str(atom)
  val = atom[1]
  if isinstance(val, list) and val:
    return render_term_english(val)
  if not isinstance(val, str):
    return str(val)
  # with_url=False: only append URL when the name is ambiguous
  return entity_name(val, with_url=False)


# ======== clause / atom rendering ========
# Converts CNF proof clauses to readable English.
# A clause is a list of atoms (disjunction); atoms with a "-" prefix are negated.
# Negated atoms are rendered as "if" conditions; positive atoms as "then" consequences.
# _atom_to_english handles every predicate in the stage-2 whitelist.

def _forall_or_to_english(frm):
  """Render ["forall", VAR, ["or", ["-isa", TYPE, VAR], CONCL]] as English.

  This is the GK encoding of ∀VAR.(TYPE(VAR) → CONCL), i.e. "all TYPEs are ...".
  Returns a string, or None if the pattern does not match.
  """
  if not (isinstance(frm, list) and len(frm) == 3 and frm[0] == "forall"):
    return None
  var  = frm[1]
  body = frm[2]
  if not (isinstance(body, list) and body and body[0] == "or"):
    return None
  # Find the -isa(TYPE, VAR) guard and the positive conclusion atom(s)
  neg_isa = None
  concls  = []
  for el in body[1:]:
    if (isinstance(el, list) and el and el[0] == "-isa"
        and len(el) >= 3 and el[2] == var):
      neg_isa = el
    else:
      concls.append(el)
  if neg_isa is None or not concls:
    return None
  typ = str(neg_isa[1])

  def _concl_pred(c):
    """Render a conclusion atom without its subject (the universal variable)."""
    if not isinstance(c, list) or not c:
      return str(c)
    p = str(c[0])
    neg = p.startswith("-")
    base = p[1:] if neg else p
    # has degree property: [pred, PROP, ENTITY(=VAR), DEGREE, RELCLASS]
    if base == "has degree property" and len(c) >= 3 and c[2] == var:
      adv, _ = _degree_parts(entity_name(c[3]) if len(c) > 3 else "")
      prop = str(c[1])
      prefix = "not " if neg else ""
      return prefix + adv + prop
    # has property: [pred, PROP, ENTITY(=VAR)]
    if base == "has property" and len(c) >= 3 and c[2] == var:
      prop = str(c[1])
      return ("not " if neg else "") + prop
    # fallback to full atom rendering
    base_atom = [base] + list(c[1:])
    return _atom_to_english_negated(base_atom) if neg else _atom_to_english(c)

  concl_text = " and ".join(_concl_pred(c) for c in concls)
  return "all " + typ + "s are " + concl_text


def block_to_english(block_atom):
  """Render a $block atom as an English exception string.

  Structure: ["$block", PRIORITY, ["$not", INNER]]
  Returns the negated rendering of INNER, or "" if malformed.
  """
  if not isinstance(block_atom, list) or len(block_atom) < 3:
    return ""
  inner = block_atom[2]
  if not (isinstance(inner, list) and inner and inner[0] == "$not"
          and len(inner) > 1 and isinstance(inner[1], list)):
    if isinstance(inner, list):
      return _atom_to_english(inner)
    return str(inner)
  body = inner[1]
  # Special case: forall-or pattern encodes a universal rule head.
  foe = _forall_or_to_english(body)
  if foe is not None:
    return "not: " + foe
  return _atom_to_english_negated(body)



# Traditional/JSON logic rendering (in proof_logic.py).
from proof_logic import (
  format_clause_logic, format_clause_traditional, formula_to_logic,
)


def _defq_ans_bridge(clause):
  """Detect the $defq/$ans bridge pattern in a 2-atom clause.

  Returns 'unwrap' for [-$defq*(args...), $ans(args...)]  -- defq drives ans
  Returns 'wrap'   for [$defq*(args...), -$ans(args...)]  -- ans drives defq
  Returns None otherwise (including wrong atom count or mismatched args).

  Both orderings (a,b) and (b,a) are checked.
  """
  if not isinstance(clause, list) or len(clause) != 2:
    return None
  a, b = clause[0], clause[1]
  if not isinstance(a, list) or not isinstance(b, list) or not a or not b:
    return None
  for first, second in [(a, b), (b, a)]:
    pa = str(first[0]);  args_a = first[1:]
    pb = str(second[0]); args_b = second[1:]
    if args_a != args_b:
      continue
    if pa.startswith("-$defq") and pb == "$ans":
      return "unwrap"
    if pa.startswith("$defq") and pb == "-$ans":
      return "wrap"
  return None


def clause_to_str(clause):
  """Convert a proof clause to a human-readable if-then English string."""
  if clause is False or clause is None:
    return "Contradiction"
  if not isinstance(clause, list):
    return str(clause)

  # Detect the contradiction-assumption step: a single negated $defq* atom,
  # which represents the refutation assumption "suppose the answer is no".
  if (len(clause) == 1 and isinstance(clause[0], list) and clause[0] and
      isinstance(clause[0][0], str) and clause[0][0].startswith("-$defq")):
    if len(clause[0]) <= 1:
      return "assume for contradiction: the answer is no"
    else:
      return "assume for contradiction: no such answer exists"

  # Detect the $defq/$ans bridge step that connects the internal answer
  # marker to the output answer atom (or vice versa).
  bridge = _defq_ans_bridge(clause)
  if bridge == "unwrap":
    return "technical answer unwrap step"
  if bridge == "wrap":
    return "technical answer wrap step"

  # Install a clause-level rendering context (sets up "some X" / "a situation V"
  # / "an event E" intros), and pre-scan to identify event/world variables.
  global _RENDER_CTX
  prev_ctx = _RENDER_CTX
  _RENDER_CTX = _ClauseRenderCtx()
  _scan_clause_vars(clause, _RENDER_CTX)
  try:
    result = _clause_to_str_body(clause)
  finally:
    _RENDER_CTX = prev_ctx
  # Capitalize the first ALPHA character so each proof step reads as a
  # sentence — skip leading quote / bracket chars so "'in the box'..." ->
  # "'In the box'..." at sentence start.
  # Exception: when the leading word is a Skolem-fn identifier ("sk0",
  # "sk1_house", ...) keep it lowercase — these are not English words.
  m = re.match(r'^[^A-Za-z]*([A-Za-z][A-Za-z0-9_]*)', result)
  if m and re.match(r'^sk\d', m.group(1)):
    return result
  for i, ch in enumerate(result):
    if ch.isalpha():
      if ch.islower():
        result = result[:i] + ch.upper() + result[i+1:]
      break
  return result


def _is_tautological_isa(base_atom):
  """True for ['isa', TYPE, 'TYPE N'] where the entity id's noun matches TYPE.

  These literals carry no information when other literals in the clause
  refer to the same entity — Stage-1 numbers constants by their type name.
  """
  if len(base_atom) < 3:
    return False
  typ = base_atom[1]
  ent = base_atom[2]
  if not (isinstance(typ, str) and isinstance(ent, str)):
    return False
  raw = ent[2:] if ent.startswith("#:") else ent
  m = re.match(r'^(.*\S)\s+\d+$', raw)
  return bool(m) and m.group(1).lower() == typ.lower()


def _clause_to_str_body(clause):
  conditions    = []   # positively-rendered negated atoms -> "if ..."
  neg_atoms     = []   # base atoms (pred without "-") for pure-negative rendering
  consequences  = []   # (english_str, is_normally) pairs for positive atoms
  raw_pos_atoms = []   # raw positive atoms (for $block matching)
  block_atoms   = []   # raw $block atoms
  blocker_texts = []   # "except when ..." rendered from unmatched $block atoms

  multi_literal = isinstance(clause, list) and len(clause) > 1

  # ---- Pass 1: classify literals (no rendering yet) ----
  neg_specs = []   # base atoms — conditions to render (positive form)
  pos_specs = []   # (kind, atom) where kind in {"pos","ans"}
  ctx = _RENDER_CTX

  # Decide whether isa-bundling applies for this clause.  Bundling absorbs
  # an isa(TYPE, var) literal into the variable's intro ("some penguin X").
  # We only apply this in PURE-NEGATIVE clauses — when there is a positive
  # literal the clause already has an explicit if-then structure and the
  # "X is a TYPE" antecedent should stay visible.
  has_positive_atom = any(
      isinstance(a, list) and a and isinstance(a[0], str)
      and a[0] not in ("$block", "$ans")
      and not a[0].startswith("-")
      for a in clause
  )
  bundling_active = (not has_positive_atom) and ctx is not None
  # If bundling is off, clear the type-hint map so _intro won't emit
  # "some penguin X" while the isa atom is also rendered as "X is a bird"
  # (would read redundantly).
  if not bundling_active and ctx is not None:
    ctx.isa_type_hint = {}

  for atom in clause:
    if not isinstance(atom, list) or not atom:
      continue
    pred = str(atom[0])
    if pred == "$block":
      block_atoms.append(atom)
    elif pred == "$ans":
      pos_specs.append(("ans", atom))
    elif pred.startswith("-"):
      base = [pred[1:]] + list(atom[1:])
      # R1: in multi-literal clauses, drop "X is a TYPE" when entity is "TYPE N".
      if multi_literal and base[0] == "isa" and _is_tautological_isa(base):
        continue
      # isa-bundling: drop -isa(TYPE, var) literals whose type-hint will be
      # absorbed into the variable's introduction in another atom.  Only
      # active in pure-negative clauses (see comment above).
      if (bundling_active and multi_literal and base[0] == "isa"
          and len(base) >= 3 and isinstance(base[2], str)
          and base[2] in ctx.isa_type_hint
          and ctx.isa_type_hint[base[2]] == base[1]
          and base[2] in ctx.used_in_other):
        continue
      neg_specs.append(base)
    else:
      # R1: same tautology filter for positive isa.
      if multi_literal and pred == "isa" and _is_tautological_isa(atom):
        continue
      pos_specs.append(("pos", atom))

  # In pure-negative clauses (no positive atoms), the existing "if A1..An-1
  # then ¬An" formatter uses the LAST literal as the consequent.  Prefer a
  # modal-classifier literal (capability/typical/necessity/...) as the
  # consequent when one is present — the modal claim is usually the
  # informative conclusion ("X is not a capability" reads better than
  # "X is not a penguin").
  _MODAL_CONSEQUENT_PREDS = frozenset({
    "capability", "typical", "necessity", "obligation", "volition",
    "intention", "expectation", "speech_act", "actuality",
  })
  if neg_specs and not pos_specs:
    for i in range(len(neg_specs) - 1):
      if neg_specs[i] and neg_specs[i][0] in _MODAL_CONSEQUENT_PREDS:
        neg_specs.append(neg_specs.pop(i))
        break

  # ---- Pass 2: render conditions FIRST so variables get introduced in the
  # antecedent ("some X" / "an event E"), then consequents reuse them bare.
  # This matters because the assembled output reads "if <conds> then <cons>",
  # so the first VISUAL mention of any variable lives in the antecedent.
  for base in neg_specs:
    rendered = _atom_to_english(base)
    # Theme 2: skip empty renderings (e.g. suppressed `actuality` literal)
    # so they don't leave a dangling " and " in the joined output.
    if not rendered:
      continue
    conditions.append(rendered)
    neg_atoms.append(base)
  for kind, atom in pos_specs:
    if kind == "ans":
      meaningful = _ans_display_args(atom[1:])
      if len(meaningful) >= 2:
        phrase = _prep_answer_phrase(meaningful)
        consequences.append((phrase + " is an answer", False))
      elif meaningful:
        consequences.append((entity_name(meaningful[0]) + " is an answer", False))
      else:
        consequences.append((ans_atom_name(atom) + " is an answer", False))
      raw_pos_atoms.append(atom)
    else:
      rendered = _atom_to_english(atom)
      if not rendered:
        continue
      consequences.append((rendered, False))
      raw_pos_atoms.append(atom)

  # Detect standard defeasible pattern: $block body matches a positive conclusion.
  # When matched, render the conclusion with "normally" instead of appending
  # "except when ..." (which redundantly restates the conclusion's negation).
  matched_blocks = set()
  for bi, block in enumerate(block_atoms):
    if (isinstance(block, list) and len(block) >= 3
        and isinstance(block[2], list) and block[2] and block[2][0] == "$not"
        and len(block[2]) > 1):
      body = block[2][1]
      for ci, raw_atom in enumerate(raw_pos_atoms):
        if raw_atom == body:
          # Mark this consequence as defeasible and this $block as matched.
          text, _ = consequences[ci]
          consequences[ci] = (text, True)
          matched_blocks.add(bi)
          break

  # Unmatched $blocks get rendered as "except when ..." (post-resolution cases).
  for bi, block in enumerate(block_atoms):
    if bi not in matched_blocks:
      bt = block_to_english(block)
      if bt:
        blocker_texts.append(bt)

  # Deduplicate identical condition strings (e.g. isa(man,X) and
  # has_degree_property(strong,X,none,man) may both render as "X is a man").
  conditions = list(dict.fromkeys(conditions))

  # Build consequence text, prepending "normally" to defeasible conclusions.
  cons_parts = []
  for text, is_normally in consequences:
    cons_parts.append("normally " + text if is_normally else text)

  if conditions and cons_parts:
    result = "if " + " and ".join(conditions) + " then " + " or ".join(cons_parts)
  elif cons_parts:
    result = " or ".join(cons_parts)
  elif conditions:
    if len(conditions) == 1:
      # Single negated atom: render in natural negated form.
      result = _atom_to_english_negated(neg_atoms[0])
    else:
      # Multi-atom pure-negative clause ¬A₁ ∨ … ∨ ¬Aₙ is logically equivalent
      # to A₁ ∧ … ∧ Aₙ₋₁ → ¬Aₙ.  Render as "if A₁ and … then not-Aₙ".
      result = ("if " + " and ".join(conditions[:-1]) +
                " then " + _atom_to_english_negated(neg_atoms[-1]))
  elif blocker_texts:
    # Clause is purely $block atoms — outstanding exception(s) still to be ruled out.
    return "outstanding exception: " + " and ".join(blocker_texts)
  elif clause and any(isinstance(a, list) and a and str(a[0]) in ("actuality", "@id", "@p", "@definite") for a in clause):
    # Clause contains only suppressed-from-English internal markers
    # (actuality / @id / @p / @definite).  Return an empty step rather than
    # the placeholder "(empty)" string.
    return ""
  else:
    result = "(empty)"

  if blocker_texts:
    result += ", except when " + " and ".join(blocker_texts)

  return result


# ======== clause-level variable rendering context (R3 + R4-revised) ========
#
# Variables are rendered with a contextual prefix on FIRST mention inside a
# single clause:
#   - World variable / constant     → "a situation V" / "the situation W0"
#   - Event variable / Skolem       → "an event E" / "the event act1"
#   - Bare entity variable          → "some X"
# Subsequent mentions of the same variable inside the same clause are bare.
# Constants outside the world/event families render unchanged.

class _ClauseRenderCtx:
  """Per-clause rendering state used to give the first mention of each
  variable a natural-language introduction ("some X", "a situation E3", ...).
  """
  __slots__ = ("seen", "event_vars", "world_vars", "event_consts",
               "has_type_vars", "isa_type_hint", "used_in_other",
               "absorbed_isa_ids", "dav_placeholder_patients")
  def __init__(self):
    self.seen = set()             # raw arg names already introduced
    self.event_vars = set()       # vars known to be events from clause scan
    self.world_vars = set()       # vars known to be worlds from clause scan
    self.event_consts = set()     # Skolem constants known to be events
    self.has_type_vars = set()    # event vars whose has_type(.,V) appears
                                  # in the SAME clause — these introduce
                                  # themselves via "X is a V event" and
                                  # don't need an extra "an event X" prefix
    self.isa_type_hint = {}       # var → TYPE (from isa(TYPE, var) in clause)
    self.used_in_other = set()    # vars that appear in non-isa atoms
    self.absorbed_isa_ids = set() # ids of isa atoms absorbed into a type
                                  # prefix; skipped during rendering
    self.dav_placeholder_patients = set()  # (-davidson) event-patient vars
                                  # that are fresh existential placeholders
                                  # (intransitive/omitted object) — dropped

_RENDER_CTX = None   # module-level slot; clause_to_str owns the lifetime


def _looks_like_var_arg(arg):
  """True if arg is a variable that should get an intro prefix on first mention."""
  return isinstance(arg, str) and looks_like_var(arg)


def _looks_like_world_const(arg):
  return isinstance(arg, str) and is_world_constant(arg)


def _is_event_skolem(arg):
  """Skolem constant that names an event (e.g. sk0_activity)."""
  if not isinstance(arg, str) or not is_skolem_const(arg):
    return False
  typ = _ctx.skolem_types.get(arg)
  return typ == "activity"


def _scan_clause_vars(clause, ctx):
  """Identify which variables in the clause are events vs worlds.

  Event: a variable that appears as the first arg of has_type / has_actor /
  has_target / has_destination / has_recipient / etc., OR as the entity arg
  of isa("activity", X) / capability(X) / typical(X) / actuality(X) / ... .
  Also marks Skolem constants of type "activity" as event constants.

  World: a variable that appears in next/before/moved/is_past_world positions.
  """
  _EVENT_ROLE_PREDS = frozenset({
    "has type", "has actor", "has target", "has destination",
    "has recipient", "has location", "has instrument", "has manner",
    "has direction", "has time", "has source", "has beneficiary",
    "has accompaniment", "has path", "has result", "has topic",
    "has cause", "has content",
  })
  _MODAL_PREDS = frozenset({
    "actuality", "capability", "typical", "necessity", "obligation",
    "volition", "intention", "expectation", "speech_act",
  })
  _WORLD_PREDS = frozenset({"next", "before", "moved", "is_past_world"})

  def _record_event(arg):
    if _looks_like_var_arg(arg):
      ctx.event_vars.add(arg)
    elif _is_event_skolem(arg):
      ctx.event_consts.add(arg)

  def _record_world(arg):
    if _looks_like_var_arg(arg):
      ctx.world_vars.add(arg)

  def _scan(atom):
    if not isinstance(atom, list) or not atom:
      return
    pred = str(atom[0])
    base = pred[1:] if pred.startswith("-") else pred
    args = atom[1:]
    if base in _EVENT_ROLE_PREDS and args:
      _record_event(args[0])
      if base == "has type" and _looks_like_var_arg(args[0]):
        ctx.has_type_vars.add(args[0])
      # All other args of role-predicates count as "used in a non-isa atom"
      # — this gates isa-bundling (we only absorb isa(TYPE, var) when var
      # also appears as a role somewhere we can attach the type prefix).
      for a in args[1:]:
        if _looks_like_var_arg(a):
          ctx.used_in_other.add(a)
    elif base in _MODAL_PREDS and args:
      _record_event(args[0])
      for a in args[1:]:
        if _looks_like_var_arg(a):
          ctx.used_in_other.add(a)
    elif base == "isa" and len(args) >= 2:
      type_name = args[0]
      var_arg = args[1]
      if type_name == "activity":
        _record_event(var_arg)
      # Record type-hint for isa-bundling: applies when type is a string
      # AND target arg is a variable.  We skip "activity" (already covered
      # by has_type) and skip the bundling for event/world vars to avoid
      # double-typing.
      if (isinstance(type_name, str) and type_name != "activity"
          and _looks_like_var_arg(var_arg)):
        ctx.isa_type_hint.setdefault(var_arg, type_name)
    elif base in _WORLD_PREDS:
      for a in args:
        _record_world(a)
        if _looks_like_var_arg(a):
          ctx.used_in_other.add(a)
    else:
      # Any other predicate also counts as "used in a non-isa atom".
      for a in args:
        if _looks_like_var_arg(a):
          ctx.used_in_other.add(a)
    # $ctxt term inside any atom: arg[1] is world slot.
    for a in args:
      if (isinstance(a, list) and a and isinstance(a[0], str)
          and a[0] == "$ctxt" and len(a) >= 3):
        _record_world(a[2])

  if isinstance(clause, list):
    for atom in clause:
      _scan(atom)

  # (-davidson) A placeholder event patient is a variable that appears ONLY as
  # the PATIENT slot of an event atom (and has no isa type) — the fresh
  # existential the fold inserts for an intransitive/omitted object.  The
  # prover renames the original `Dav…` var, so detect it structurally instead.
  if isinstance(clause, list):
    var_occurrences = {}
    event_patient_vars = set()
    for atom in clause:
      if not (isinstance(atom, list) and atom and isinstance(atom[0], str)):
        continue
      pred = atom[0]
      base = pred[1:] if pred.startswith("-") else pred
      atom_args = atom[1:]
      for arg in atom_args:
        if _looks_like_var_arg(arg):
          var_occurrences[arg] = var_occurrences.get(arg, 0) + 1
      if base == "event" and len(atom_args) >= 3 and _looks_like_var_arg(atom_args[2]):
        event_patient_vars.add(atom_args[2])
    for v in event_patient_vars:
      if var_occurrences.get(v, 0) <= 1 and v not in ctx.isa_type_hint:
        ctx.dav_placeholder_patients.add(v)


_COMMON_NOUN_CONST_RE = re.compile(r'^[a-z].*\s\d+$')


def _prep_answer_phrase(args):
  """Render a multi-arg `$ans` / `$defq*` payload.

  Where/when-answers come out of `lc_questions` as
  [PREP, VALUE, ...] (e.g. ["in", "box 2"], ["on", "table 3"], ["before", ...]).
  When the first arg is a preposition, render it inline and wrap the whole
  phrase in single quotes — "'in <rest>'" — so the answer fragment is
  visually demarcated as a unit ("'In the box' is the answer").
  Other multi-arg payloads keep the bracket form.
  """
  if args and isinstance(args[0], str) and args[0].lower() in _PREPOSITIONS:
    prep = args[0]
    rest = " ".join(_intro(a) for a in args[1:])
    return "'" + prep + " " + rest + "'"
  return "[" + ", ".join(entity_name(a, with_url=True) for a in args) + "]"


def _is_common_noun_const(arg):
  """True for entity ids like 'head 2', 'box 2', 'stone 3' — lowercase
  noun with a numeric suffix.  These are not proper nouns and read better
  with a "the" article in proof prose."""
  if not isinstance(arg, str):
    return False
  raw = arg[2:] if arg.startswith("#:") else arg
  return bool(_COMMON_NOUN_CONST_RE.match(raw))


def _intro(arg, role_hint=None):
  """Render an argument inside the current clause with the right article /
  prefix.  Tracks first vs subsequent mentions via _RENDER_CTX.seen.

  - World constants (W0/W1/…):     "the situation W0"
  - Event Skolems (sk0_activity):  "the event act1" first / "the act1" later
  - Skolem function terms:         full "the flying event sk0 of Mike" first /
                                   short "sk0 of Mike" later
  - Common-noun constants:         "the head B" (always, every mention)
  - Variable, world-typed:         "a situation V" first / bare later
  - Variable, event-typed:         "an event E" first / bare later
  - Variable with isa(TYPE,X) in clause: "some <TYPE> X" first / bare later
  - Variable with role hint:       "a/an <ROLE> X" first / bare later
  - Bare entity variable:          "some X" first / bare later
  - Everything else:               plain entity_name() rendering
  """
  ctx = _RENDER_CTX
  # Skolem function list-terms: track first vs subsequent mentions and
  # render shorter ("sk0 of Mike") on later mentions to avoid repeating
  # the full "the flying event sk0 of Mike" noun phrase.
  if ctx is not None and isinstance(arg, list) and is_skolem_fn(arg):
    # Also mark any VARIABLE args of the Skolem fn as already-seen so
    # that a later standalone _intro on the same variable in this clause
    # returns bare "X" instead of introducing it as "some X" — the X
    # already appeared inside "sk1 of X".
    for sub in arg[1:]:
      if isinstance(sub, str) and looks_like_var(sub):
        ctx.seen.add(sub)
    key = "skfn:" + str(arg)
    if key in ctx.seen:
      return _skolem_fn_short_name(arg)
    ctx.seen.add(key)
    return entity_name(arg, with_url=True, proof_mode=True)
  if ctx is None or not isinstance(arg, str):
    return entity_name(arg, with_url=True, proof_mode=True)

  # World constants (W0, W1, ...) — always "the situation".
  if is_world_constant(arg):
    return "the situation " + arg

  # Event Skolem constants (sk0_activity, ...). Bypass entity_name's own
  # "some activity actN" intro so we don't double up.  Mark the Skolem as
  # introduced so any later entity_name() call elsewhere returns the bare
  # display name; we'll add "the" ourselves.
  if _is_event_skolem(arg):
    bare = _ctx.skolem_display.get(arg, arg)
    _ctx.skolem_introduced.add(arg)
    if arg in ctx.seen:
      return "the " + bare
    ctx.seen.add(arg)
    return "the event " + bare

  # Common-noun constants ("head 2", "box 2") — always "the noun".
  if _is_common_noun_const(arg):
    return "the " + entity_name(arg, with_url=True, proof_mode=True)

  # Variables — introduce with a-prefix on first mention only.
  if looks_like_var(arg):
    if arg in ctx.seen:
      return entity_name(arg, with_url=True, proof_mode=True)
    ctx.seen.add(arg)
    name = entity_name(arg, with_url=True, proof_mode=True)
    if arg in ctx.world_vars:
      return "a situation " + name
    if arg in ctx.event_vars:
      # When the same clause's has_type literal already introduces this
      # event ("X is a fly event"), drop the "an event" prefix here so
      # we don't double-up.  Bare X reads cleanly.
      if arg in ctx.has_type_vars:
        return name
      return "an event " + name
    # isa-bundling: if the same clause has an isa(TYPE, var) literal AND
    # var appears in some other (non-isa) atom we can attach the type to,
    # render as "some <TYPE> X".  The isa atom itself is suppressed during
    # clause rendering.
    isa_type = ctx.isa_type_hint.get(arg)
    if isa_type and arg in ctx.used_in_other:
      return "some " + isa_type + " " + name  # "some penguin X"
    if role_hint:
      art = "an" if role_hint[0].lower() in "aeiou" else "a"
      return art + " " + role_hint + " " + name
    return "some " + name

  # Proper-noun constants and others: pass through.
  return entity_name(arg, with_url=True, proof_mode=True)


# ======== atom-to-English converters ========
#
# Table-driven dispatch: each predicate has a (min_args, pos_fn, neg_fn) entry.
# pos_fn(e, args) returns the positive English string.
# neg_fn(e, args) returns the negated English string.
# Complex predicates use dedicated helpers; simple ones use inline lambdas.

def _isa_pos(e, args):
  # Use raw type string to avoid entity_map turning "man" into "the strong man".
  typ = str(args[0]) if args else e(0)
  ent = e(1)
  if typ == "activity": return ent + " is an activity"
  if typ == "set":      return ent + " is a set"
  return ent + " is " + _indef_article(typ) + " " + typ

def _isa_neg(e, args):
  typ = str(args[0]) if args else e(0)
  ent = e(1)
  if typ == "activity": return ent + " is not an activity"
  if typ == "set":      return ent + " is not a set"
  return ent + " is not " + _indef_article(typ) + " " + typ

def _dav_patient_is_real(p):
  """(-davidson) The PATIENT slot of event(V, A, P, E) is a real object only
  when the fold found an actual theme filler.  An absent patient (intransitive
  / omitted object) is a fresh existential placeholder — a Skolem function term
  after clausification, or a `Dav…`-named variable before it — and should not
  be rendered as an object ("Mike flies", not "Mike flies the event sk1")."""
  if p is None:
    return False
  if isinstance(p, list):            # Skolemized fresh existential
    return False
  if isinstance(p, str) and looks_like_var(p):
    if _RENDER_CTX is not None and p in _RENDER_CTX.dav_placeholder_patients:
      return False                   # appears only as this event's patient
    base = p[2:] if p.startswith("?:") else p
    return not base.startswith("Dav")
  return True                        # concrete entity or type token

def _event_pos(e, args):
  """Render a folded Davidsonian event atom ["event", VERB, AGENT, PATIENT, E, CTXT]
  as 'AGENT VERBs [PATIENT]'.  The first arg is always a verb root, so it is
  conjugated directly.  A placeholder PATIENT (intransitive) is dropped; the
  handle E and CTXT are not rendered here — E is named via its verb wherever a
  classifier/blocker references it.  Render the subject first so it keeps its
  'some X' / 'Mike' intro before the patient."""
  verb = str(args[0]) if args else ""
  subj = e(1)
  patient = args[2] if len(args) > 2 else None
  if _dav_patient_is_real(patient):
    return subj + " " + _conjugate_verb(verb) + " " + _intro(patient)
  return subj + " " + _conjugate_verb(verb)

def _event_neg(e, args):
  verb = str(args[0]) if args else ""
  subj = e(1)
  patient = args[2] if len(args) > 2 else None
  if _dav_patient_is_real(patient):
    return subj + " does not " + verb + " " + _intro(patient)
  return subj + " does not " + verb

def _has_property_render(e, args, neg=False):
  """has property(PROP, ENT).  Default: 'ENT is PROP'.  (L2 -existfold) a folded
  attribute PROP = ["$has_part", C] / ["$have", C] renders 'ENT has a C'."""
  prop = args[0] if args else ""
  if isinstance(prop, list) and len(prop) >= 2 and prop[0] in ("$has_part", "$have"):
    C = prop[1]
    cname = C if isinstance(C, str) else entity_name(C, with_url=True, proof_mode=True)
    have = " does not have " if neg else " has "
    return e(1) + have + _indef_article(cname) + " " + cname
  return e(1) + (" is not " if neg else " is ") + e(0)

def _is_rel2_pos(e, args):
  rel_raw = args[0] if args else ""
  # Variable-relation case: read as "Y is/was/will-be in relation X to Z
  # <context-from-$ctxt>".  Surfaces the tense and world so two atoms in
  # the same clause that differ only in $ctxt render distinguishably.
  if isinstance(rel_raw, str) and looks_like_var(rel_raw):
    return _is_rel2_var_rel_render(e, args, neg=False)
  rel = e(0)
  last = rel.split()[-1].lower() if rel else ""
  if rel.lower() in _PREPOSITIONS or last in _PREPOSITIONS or last == "of":
    return e(1) + " is " + rel + " " + e(2)
  if _looks_like_verb(rel):
    return e(1) + " " + _conjugate_verb(rel) + " " + e(2)
  return e(1) + " is " + rel + " of " + e(2)

def _is_rel2_neg(e, args):
  rel_raw = args[0] if args else ""
  if isinstance(rel_raw, str) and looks_like_var(rel_raw):
    return _is_rel2_var_rel_render(e, args, neg=True)
  rel = e(0)
  last = rel.split()[-1].lower() if rel else ""
  if rel.lower() in _PREPOSITIONS or last in _PREPOSITIONS or last == "of":
    return e(1) + " is not " + rel + " " + e(2)
  if _looks_like_verb(rel):
    return e(1) + " does not " + rel + " " + e(2)
  return e(1) + " is not " + rel + " of " + e(2)


def _is_rel2_var_rel_render(e, args, neg=False):
  """Render is_rel2 when the relation arg is a variable (axiom case).

  Form: '<Y> is/was/will-be in relation <X> to <Z>'
        + optional ' before/in/after <world>' suffix from the $ctxt term.
  Surfaces the tense and world from $ctxt so two such atoms with
  different contexts render distinguishably in the same clause.
  """
  # Relation arg: render bare (it's a relation name, not an instance);
  # bypass _intro so it doesn't get a "some" prefix.
  rel  = entity_name(args[0], with_url=True, proof_mode=True)
  subj = e(1)
  obj  = e(2)
  tense_verb = "is not" if neg else "is"
  context_suffix = ""
  ctxt = args[3] if len(args) >= 4 else None
  if (isinstance(ctxt, list) and len(ctxt) >= 3
      and isinstance(ctxt[0], str) and ctxt[0] == "$ctxt"):
    tense = ctxt[1]
    world_arg = ctxt[2]
    if isinstance(tense, str) and tense in ("past", "present", "future"):
      if neg:
        verb_map = {"past": "was not", "present": "is not",
                    "future": "will not be"}
      else:
        verb_map = {"past": "was", "present": "is",
                    "future": "will be"}
      tense_verb = verb_map[tense]
      world_word = {"past": "before ", "present": "in ",
                    "future": "after "}[tense]
      # Render the world via _intro (handles "the situation W" / "a situation V").
      context_suffix = " " + world_word + _intro(world_arg)
  return subj + " " + tense_verb + " in relation " + rel + " to " + obj + context_suffix

def _has_degree_property_render(e, args, neg=False):
  prop = e(0); ent = e(1)
  adv, art_type = _degree_parts(e(2))
  relcls_raw = args[3] if len(args) > 3 else ""
  cop = " is not " if neg else " is "
  # Omit relclass when it's a variable, "none", or "entity" — these carry no
  # useful comparison-class info and produce ugly English like "a big none".
  if isinstance(relcls_raw, str) and (relcls_raw.startswith("?:")
      or relcls_raw in ("none", "entity")):
    return ent + cop + adv + prop
  # Omit relclass when it matches the entity's base noun — avoids redundancy
  # like "the mouse is a very big mouse" → "the mouse is very big".
  ent_raw = args[1] if len(args) > 1 else ""
  if isinstance(ent_raw, str) and isinstance(relcls_raw, str):
    ent_base = re.match(r'^(.*\S)\s+\d+$', ent_raw)
    if ent_base and ent_base.group(1).lower() == relcls_raw.lower():
      return ent + cop + adv + prop
  # Use the raw relclass string (not entity_name) to avoid entity_map lookup
  # turning class names like "man" into "the strong man".
  relcls = str(relcls_raw)
  art = "the" if art_type == "def" else _indef_article(adv if adv else prop)
  return ent + cop + art + " " + adv + prop + " " + relcls

def _has_degree_rel2_render(e, args, neg=False):
  rel = e(0); ent1 = e(1); ent2 = e(2)
  degree_raw = str(args[3]).lower() if len(args) > 3 else "none"
  last = rel.split()[-1].lower() if rel else ""
  cop = " is not " if neg else " is "
  if last in _PREPOSITIONS or last == "of":
    return ent1 + cop + rel + " " + ent2
  if _is_var_display(rel):
    if neg: return ent1 + " does not have a " + rel + "-relation with " + ent2
    return ent1 + " has a " + rel + "-relation with " + ent2
  if degree_raw in ("high", "more"):
    return ent1 + cop + _make_comparative(rel) + " than " + ent2
  if degree_raw == "most":
    return ent1 + cop.rstrip() + " the most " + rel + " of all compared to " + ent2
  if degree_raw in ("low", "less"):
    return ent1 + cop + "less " + rel + " than " + ent2
  if degree_raw == "least":
    return ent1 + cop.rstrip() + " the least " + rel + " of all compared to " + ent2
  return ent1 + cop + rel + " of " + ent2

def _is_var_raw(args, i):
  """True if args[i] is a raw variable string (starts with '?:')."""
  return (len(args) > i and isinstance(args[i], str) and args[i].startswith("?:"))

# Measure-unit promotion table for rendering. When a $list value is exactly
# divisible by the divisor (and has no fractional part), promote to the next
# unit. Cascades naturally: 80000 mm → 80 m → 0.08 km not triggered (80 m %
# 1000 ≠ 0). 1000000 mm → 1000 m → 1 km (cascade fires).
_MEASURE_PROMOTE = {
  "meter":      ("kilometer", 1000),
  "millimeter": ("meter",     1000),
  "centimeter": ("meter",      100),
  "gram":       ("kilogram",  1000),
  "milligram":  ("gram",      1000),
}


def _normalize_measure(val, unit_name):
  """Promote (val, unit_name) to a larger unit when val is integer-valued
  and exactly divisible by the unit's promotion factor.

  Cascades while a promotion still applies. Returns (val, unit_name)
  unchanged when no promotion is possible (e.g. 100 meters stays "100
  meters" because 100 % 1000 ≠ 0).
  """
  if isinstance(val, float) and val.is_integer():
    val = int(val)
  if not isinstance(val, int):
    return val, unit_name
  while unit_name in _MEASURE_PROMOTE:
    bigger, divisor = _MEASURE_PROMOTE[unit_name]
    if val % divisor != 0:
      break
    val //= divisor
    unit_name = bigger
  return val, unit_name


def _measure_phrase(val, unit_name):
  """Render "<val> <unit>" with a pluralised unit for numeric val != 1.

  "80000", "meter" -> "80000 meters";  1, "dollar" -> "1 dollar".
  Leaves an already-plural unit untouched.
  """
  unit_name = str(unit_name)
  num = val
  if isinstance(num, float) and num.is_integer():
    num = int(num)
  pluralise = (not isinstance(num, (int, float))) or num != 1
  if pluralise and unit_name and not unit_name.endswith("s"):
    unit_name = unit_name + "s"
  return str(num) + " " + unit_name


def render_term_english(term, proof_mode=True):
  """Render a complex list term (nested function/predicate) as English.

  Handles $count, $setof, TPTP arithmetic ($sum, $difference, $product,
  $quotient), and infix arithmetic (+, -, *, /).
  Falls back to str() for unrecognized terms.

  proof_mode controls how nested entity names are rendered: True (default,
  used for proof explanation) keeps raw IDs in JSON mode for traceability;
  False (used for the user-facing answer line) consults entity_map to get
  cosmetic names like "Mary" instead of "Mary 1".
  """
  if not isinstance(term, list) or not term:
    return str(term)

  op = term[0]

  # $datetime -> just the value
  if op == "$datetime" and len(term) >= 2:
    return str(term[1])

  # $theof1 -> "SUBJECT's TYPE" for named entities, else "the TYPE of SUBJECT"
  if op == "$theof1" and len(term) >= 3:
    type_name = term[1] if isinstance(term[1], str) else str(term[1])
    subj = entity_name(term[2], proof_mode=proof_mode)
    if subj and subj[0:1].isupper() and not subj.lower().startswith(("the ", "a ", "an ")):
      suffix = "'" if subj.endswith("s") else "'s"
      return subj + suffix + " " + type_name
    return "the " + type_name + " of " + subj

  # $measure_of -> "the TYPE of SUBJECT"
  if op == "$measure_of" and len(term) >= 3:
    type_name = term[1] if isinstance(term[1], str) else str(term[1])
    subj = entity_name(term[2], proof_mode=True)
    return "the " + type_name + " of " + subj

  # $measure -> "80 kilometers" (original form, before canonicalization)
  if op == "$measure" and len(term) == 3:
    return _measure_phrase(term[1], term[2])

  # $list with number + unit -> "80000 meters".  The unit may carry the UNA
  # `#:` prefix (proof-step path) or not (answer path, where the prover echoes
  # the constant with `#:` already stripped).  Handle both: pluralise the unit
  # for numeric values either way.  Promotion to a larger unit is only applied
  # when the canonical `#:`-prefixed form is present.
  if op == "$list" and len(term) == 3:
    val = term[1]
    unit = term[2]
    if isinstance(unit, str) and unit.startswith("#:"):
      unit_name = unit[2:]  # strip #: prefix
      val, unit_name = _normalize_measure(val, unit_name)
      return _measure_phrase(val, unit_name)
    if isinstance(unit, str):
      return _measure_phrase(val, unit)
    return str(val) + " " + str(unit)

  # $count -> "the number of ..."
  if op == "$count" and len(term) >= 2:
    inner = _render_setof_english(term[1])
    return "the number of " + inner

  # $setof -> delegate
  if op == "$setof":
    return _render_setof_english(term)

  # TPTP prefix arithmetic functions
  _ARITH_PREFIX = {
    "$sum": "+", "$difference": "-", "$product": "*", "$quotient": "/",
    "$quotient_e": "/", "$remainder_e": "mod", "$remainder_t": "mod",
    "$remainder_f": "mod", "$uminus": "-",
    "$floor": "floor", "$ceiling": "ceiling",
    "$truncate": "truncate", "$round": "round",
    "$to_int": "int", "$to_real": "real",
  }
  if op in _ARITH_PREFIX and len(term) >= 2:
    if op == "$uminus":
      return "-" + entity_name(term[1], proof_mode=True)
    if len(term) == 2:
      # Unary: $floor(X) etc
      return _ARITH_PREFIX[op] + "(" + entity_name(term[1], proof_mode=True) + ")"
    a = entity_name(term[1], proof_mode=True)
    b = entity_name(term[2], proof_mode=True)
    return a + " " + _ARITH_PREFIX[op] + " " + b

  # Infix arithmetic: [A, "+", B] etc
  if len(term) == 3 and isinstance(term[1], str) and term[1] in ("+", "-", "*", "/"):
    a = entity_name(term[0], proof_mode=True)
    b = entity_name(term[2], proof_mode=True)
    return a + " " + term[1] + " " + b

  return str(term)


def _render_setof_english(term):
  """Render a $setof term as English.

  Fully concrete (anchor + subject + $isa in conditions):
    $setof(have, John 1, [$and, $isa(car,$arg1)]) -> "cars John has"
    $setof(have, John 1, [$and, $isa(car,$arg1), $has_degree_property(nice,...)]) -> "nice cars John has"

  Partially concrete (anchor + subject concrete, some variable conditions):
    $setof(have, John 1, [$and, $isa(car,$arg1), ?:Y]) -> "cars John has that satisfy Y"

  All variables (generic axiom):
    $setof(?:Y, ?:Z, [$and, ?:U, ?:V]) -> "a set of things satisfying conditions U and V"
  """
  if not isinstance(term, list) or not term or term[0] != "$setof" or len(term) < 3:
    return str(term)

  # Parse canonical $setof form
  if term[1] == "id":
    # Conditions-only: ["$setof", "id", SET_ID, ["$and", ...]]
    set_id = term[2]
    conds = term[3] if len(term) > 3 else []
    type_name = _extract_type_from_conds(conds)
    return type_name + " in " + str(set_id)

  # Anchored: ["$setof", PRED, SUBJ, ["$and", ...]]
  pred = term[1]
  subj = term[2] if len(term) > 2 else "?"
  conds = term[3] if len(term) > 3 else term[2]

  pred_is_var = isinstance(pred, str) and pred.startswith("?:")
  subj_is_var = isinstance(subj, str) and subj.startswith("?:")

  # All variables -> generic description
  if pred_is_var and subj_is_var:
    cond_str = _render_and_conditions(conds)
    return "a set of things satisfying " + cond_str

  # Concrete anchor/subject -> try to produce natural English
  type_name, props, extra_vars = _extract_type_and_props(conds)
  subj_name = entity_name(subj, proof_mode=True)

  # Build the base: "nice cars John has"
  if props:
    desc = " ".join(props) + " " + type_name
  else:
    desc = type_name

  if pred == "have":
    base = desc + " " + subj_name + " has"
  elif pred == "can":
    base = desc + " that can " + str(conds)
  else:
    base = desc + " " + pred + " " + subj_name

  # Append unresolved variable conditions
  if extra_vars:
    var_str = " and ".join(entity_name(v, proof_mode=True) for v in extra_vars)
    base += " that satisfy " + var_str

  return base


def _extract_type_and_props(conds):
  """Extract type name, property adjectives, and unresolved variable conditions.

  Returns (type_name, props_list, extra_vars_list).
  """
  if not isinstance(conds, list) or not conds:
    return "things", [], []
  items = conds[1:] if conds[0] in ("$and", "and") else [conds]

  type_name = "things"
  props = []
  extra_vars = []

  for item in items:
    if isinstance(item, str) and item.startswith("?:"):
      extra_vars.append(item)
      continue
    if not isinstance(item, list) or len(item) < 2:
      continue
    pred = item[0]
    if pred in ("$isa", "isa") and isinstance(item[1], str):
      type_name = item[1] + "s"
    elif pred in ("$has_degree_property", "has degree property") and len(item) >= 3:
      # Extract the adjective name
      adj = item[1] if isinstance(item[1], str) and not item[1].startswith("?:") else None
      if adj:
        props.append(adj)
      else:
        extra_vars.append(item)
    else:
      # Skip $arg1-only predicates (like $have which duplicates the anchor)
      pass

  return type_name, props, extra_vars


def _render_and_conditions(conds):
  """Render $and conditions as a readable string.

  Variable conditions: "conditions U and V"
  Mixed: "conditions $isa(car, ...) and V"
  """
  if not isinstance(conds, list) or not conds:
    return "conditions " + str(conds)
  items = conds[1:] if conds[0] in ("$and", "and") else [conds]

  parts = []
  for item in items:
    if isinstance(item, str) and item.startswith("?:"):
      parts.append(entity_name(item, proof_mode=True))
    elif isinstance(item, str):
      parts.append(item)
    else:
      parts.append(str(item))

  if len(parts) == 1:
    return "condition " + parts[0]
  return "conditions " + " and ".join(parts)


def _extract_type_from_conds(conds):
  """Extract the type name from a $and conditions list."""
  type_name, _, _ = _extract_type_and_props(conds)
  return type_name


def _render_member(e, args, negated):
  """Render member atom, with special handling for $setof set terms."""
  if len(args) >= 2 and isinstance(args[1], list) and args[1] and args[1][0] == "$setof":
    set_desc = _render_setof_english(args[1])
    ent = e(0)
    if negated:
      return ent + " is not among " + set_desc
    return ent + " is among " + set_desc
  if negated:
    return e(0) + " is not a member of " + e(1)
  return e(0) + " is a member of " + e(1)


def _render_equals(e, args, negated):
  """Render an = atom, with special handling for $count terms."""
  # Check if either argument is a $count term
  for i in (0, 1):
    val = args[i]
    other = args[1 - i]
    if isinstance(val, list) and val and val[0] == "$count":
      set_desc = render_term_english(val)
      other_name = entity_name(other, proof_mode=True)
      if negated:
        return set_desc + " is not " + other_name
      return set_desc + " is " + other_name
  # Default: plain equals
  if negated:
    return e(0) + " does not equal " + e(1)
  return e(0) + " equals " + e(1)


# Predicate dispatch table: pred -> (min_args, pos_fn, neg_fn)
# pos_fn / neg_fn signature: (e, args) -> str
# ======== custom predicate-render helpers ========


def _event_arg_is_specific(arg):
  """True if the event arg (first arg of an event-role atom) refers to a
  specific event (Skolem) rather than a free variable.  Used to pick
  between 'the recipient/destination of <evt>' vs 'a recipient/...'."""
  if isinstance(arg, str) and is_skolem_const(arg):
    return True
  if isinstance(arg, list) and is_skolem_fn(arg):
    return True
  return False


def _has_type_render(e, args, neg=False):
  """Render `has_type(E, V)` as 'E is a V event' / 'E is not a V event'.

  When E is a Skolem fn term, use the SHORT form 'sk0 of X' (no
  gerund/event-noun prefix) because the predicate already asserts the
  event type — "the flying event sk0 of X is a fly event" would be
  redundant.  Marks the Skolem fn as seen so other atoms in the same
  clause use the short form too.

  When V is a variable, fall back to '<subj> has type V' (no "?:V
  event" leak) and mark V as seen so a later atom in the same clause
  referencing V (e.g. $defq0) renders bare instead of being
  re-introduced as "some V".
  """
  first = args[0] if args else None
  verb = args[1] if len(args) > 1 else "?"
  if isinstance(first, list) and is_skolem_fn(first):
    subj = _skolem_fn_short_name(first)
    if _RENDER_CTX is not None:
      _RENDER_CTX.seen.add("skfn:" + str(first))
      # Mark variable args of the Skolem fn as seen too, so a later
      # standalone mention of the same variable in the clause renders
      # bare instead of being re-introduced as "some X".
      for sub in first[1:]:
        if isinstance(sub, str) and looks_like_var(sub):
          _RENDER_CTX.seen.add(sub)
  else:
    subj = e(0)
  if isinstance(verb, str) and looks_like_var(verb):
    if _RENDER_CTX is not None:
      _RENDER_CTX.seen.add(verb)
    verb_name = entity_name(verb, with_url=True, proof_mode=True)
    if neg:
      return subj + " does not have type " + verb_name
    return subj + " has type " + verb_name
  if neg:
    return subj + " is not a " + str(verb) + " event"
  return subj + " is a " + str(verb) + " event"


def _has_recipient_render(e, args, neg=False):
  """Pivot rendering: '<recipient> is the/a recipient of <event>'."""
  evt_arg = args[0]
  evt   = e(0)
  recip = e(1)
  art   = "the" if _event_arg_is_specific(evt_arg) else "a"
  if neg:
    return recip + " is not " + art + " recipient of " + evt
  return recip + " is " + art + " recipient of " + evt


def _has_destination_render(e, args, neg=False):
  """Pivot rendering: '<destination> is the/a destination of <event>'.
  Drops the preposition slot from the English (it's an internal
  Skolem-bound variable in axioms and noise in concrete steps)."""
  evt_arg = args[0]
  evt  = e(0)
  dest = e(1)
  art  = "the" if _event_arg_is_specific(evt_arg) else "a"
  if neg:
    return dest + " is not " + art + " destination of " + evt
  return dest + " is " + art + " destination of " + evt


def _has_time_render(e, args, neg=False):
  """Render has_time with the past/present/future verb matching the tense.

  Stage-2 canonical shape: ['has time', E, TENSE, PREP] where TENSE is
  'past'/'present'/'future' and PREP is the temporal preposition (usually
  'in').  Render with the matching English verb form."""
  evt  = e(0)
  tense = args[1] if len(args) > 1 else None
  prep_arg = args[2] if len(args) > 2 else None
  # When the tense slot itself is a variable, fall back to the original form.
  if not (isinstance(tense, str) and tense in ("past", "present", "future")):
    prep = e(2) if len(args) > 2 else ""
    suffix = ("time " if _is_var_raw(args, 1) else "") + e(1)
    if neg:
      return evt + " does not happen " + prep + " " + suffix
    return evt + " happens " + prep + " " + suffix
  # Tense is a literal string — pick a natural verb.
  verb = {"past":    ("happened",     "did not happen"),
          "present": ("happens",      "does not happen"),
          "future":  ("will happen",  "will not happen")}[tense]
  v = verb[1] if neg else verb[0]
  # Drop the variable preposition slot in axioms; keep concrete ones.
  if isinstance(prep_arg, str) and not looks_like_var(prep_arg):
    return evt + " " + v + " " + prep_arg + " the " + tense
  return evt + " " + v + " in the " + tense


_PRED_TABLE = {
  # core predicates
  "has property":       (2, lambda e,a: _has_property_render(e, a, neg=False),
                            lambda e,a: _has_property_render(e, a, neg=True)),
  "have":               (2, lambda e,a: e(0)+" has "+e(1),
                            lambda e,a: e(0)+" does not have "+e(1)),
  "has part":           (2, lambda e,a: e(0)+" has "+e(1)+" as a part",
                            lambda e,a: e(0)+" does not have "+e(1)+" as a part"),
  "can":                (2, lambda e,a: e(0)+" can "+e(1),
                            lambda e,a: e(0)+" cannot "+e(1)),
  # predicates with complex logic
  "isa":                (2, _isa_pos, _isa_neg),
  "is rel2":            (3, _is_rel2_pos, _is_rel2_neg),
  "event":              (3, _event_pos, _event_neg),
  "has degree property":(4, lambda e,a: _has_degree_property_render(e, a, neg=False),
                            lambda e,a: _has_degree_property_render(e, a, neg=True)),
  "has degree rel2":    (4, lambda e,a: _has_degree_rel2_render(e, a, neg=False),
                            lambda e,a: _has_degree_rel2_render(e, a, neg=True)),
  # event reification predicates
  "has type":           (2, lambda e,a: _has_type_render(e, a, neg=False),
                            lambda e,a: _has_type_render(e, a, neg=True)),
  "has actor":          (2, lambda e,a: e(1)+" performs "+e(0),
                            lambda e,a: e(1)+" does not perform "+e(0)),
  "has target":         (2, lambda e,a: e(0)+" targets "+e(1),
                            lambda e,a: e(0)+" does not target "+e(1)),
  "has location":       (3, lambda e,a: e(0)+" takes place "+e(2)+" "+e(1),
                            lambda e,a: e(0)+" does not take place "+e(2)+" "+e(1)),
  "has instrument":     (2, lambda e,a: e(0)+" uses "+e(1),
                            lambda e,a: e(0)+" does not use "+e(1)),
  "has manner":         (2, lambda e,a: e(0)+" happens in a "+e(1)+" manner",
                            lambda e,a: e(0)+" does not happen in a "+e(1)+" manner"),
  "has direction":      (2, lambda e,a: e(0)+" goes towards "+e(1),
                            lambda e,a: e(0)+" does not go towards "+e(1)),
  "has destination":    (3, lambda e,a: _has_destination_render(e, a, neg=False),
                            lambda e,a: _has_destination_render(e, a, neg=True)),
  "has recipient":      (2, lambda e,a: _has_recipient_render(e, a, neg=False),
                            lambda e,a: _has_recipient_render(e, a, neg=True)),
  "has source":         (2, lambda e,a: e(0)+" comes from "+e(1),
                            lambda e,a: e(0)+" does not come from "+e(1)),
  "has beneficiary":    (2, lambda e,a: e(0)+" is for "+e(1),
                            lambda e,a: e(0)+" is not for "+e(1)),
  "has accompaniment":  (2, lambda e,a: e(0)+" is with "+e(1),
                            lambda e,a: e(0)+" is not with "+e(1)),
  "has path":           (2, lambda e,a: e(0)+" goes through "+e(1),
                            lambda e,a: e(0)+" does not go through "+e(1)),
  "has result":         (2, lambda e,a: e(0)+" results in "+e(1),
                            lambda e,a: e(0)+" does not result in "+e(1)),
  "has topic":          (2, lambda e,a: e(0)+" is about "+e(1),
                            lambda e,a: e(0)+" is not about "+e(1)),
  "has cause":          (2, lambda e,a: e(0)+" is caused by "+e(1),
                            lambda e,a: e(0)+" is not caused by "+e(1)),
  "has time":           (3, lambda e,a: _has_time_render(e, a, neg=False),
                            lambda e,a: _has_time_render(e, a, neg=True)),
  # state / world predicates
  "next":               (2, lambda e,a: e(0)+" is followed by "+e(1),
                            lambda e,a: e(0)+" is not followed by "+e(1)),
  "before":             (2, lambda e,a: e(0)+" is earlier than "+e(1),
                            lambda e,a: e(0)+" is not earlier than "+e(1)),
  "state time":         (2, lambda e,a: "at time "+e(1),         None),
  "state location":     (2, lambda e,a: "at location "+e(1),     None),
  # helper predicates from axioms_std.js — render with situation-aware text.
  "moved":              (2, lambda e,a: e(0)+" moved in "+e(1),
                            lambda e,a: e(0)+" did not move in "+e(1)),
  "transferred":        (2, lambda e,a: e(0)+" was transferred in "+e(1),
                            lambda e,a: e(0)+" was not transferred in "+e(1)),
  "is_past_world":      (1, lambda e,a: e(0)+" is in the past",
                            lambda e,a: e(0)+" is not in the past"),
  # set predicates
  "is set of":          (2, lambda e,a: e(1)+" is a set of "+e(0),
                            lambda e,a: e(1)+" is not a set of "+e(0)),
  "member":             (2, lambda e,a: _render_member(e, a, False),
                            lambda e,a: _render_member(e, a, True)),
  "member has property":(2, lambda e,a: "members of "+e(1)+" are "+e(0),
                            lambda e,a: "members of "+e(1)+" are not "+e(0)),
  "is subset of":       (2, lambda e,a: e(0)+" is a subset of "+e(1),
                            lambda e,a: e(0)+" is not a subset of "+e(1)),
  "set union":          (3, lambda e,a: e(2)+" is the union of "+e(0)+" and "+e(1),
                            None),
  "$count":             (1, lambda e,a: "count of "+e(0),        None),
  # comparison predicates
  "=":                  (2, lambda e,a: _render_equals(e, a, False),
                            lambda e,a: _render_equals(e, a, True)),
  "<":                  (2, lambda e,a: e(0)+" is less than "+e(1),
                            lambda e,a: e(0)+" is not less than "+e(1)),
  ">":                  (2, lambda e,a: e(0)+" is greater than "+e(1),
                            lambda e,a: e(0)+" is not greater than "+e(1)),
  "$less":              (2, lambda e,a: e(0)+" is less than "+e(1),
                            lambda e,a: e(0)+" is not less than "+e(1)),
  "$lesseq":            (2, lambda e,a: e(0)+" is at most "+e(1),
                            lambda e,a: e(0)+" is not at most "+e(1)),
  "$greater":           (2, lambda e,a: e(0)+" is greater than "+e(1),
                            lambda e,a: e(0)+" is not greater than "+e(1)),
  "$greatereq":         (2, lambda e,a: e(0)+" is at least "+e(1),
                            lambda e,a: e(0)+" is not at least "+e(1)),
  "less_measure":       (2, lambda e,a: e(0)+" is less than "+e(1),
                            lambda e,a: e(0)+" is not less than "+e(1)),
  # mental predicates
  "kb":                 (3, lambda e,a: e(1)+" "+e(2)+" that ...", None),
  "kb force":           (0, None,                                  None),
  # ---- modal classifiers (arity-1, attach to a Davidsonian event variable) ----
  # Atom-level forms; clause-level rendering ("X can V" from sibling
  # has_type+has_actor) is deferred to Phase 6.
  "capability":         (1, lambda e,a: e(0)+" is a capability",
                            lambda e,a: e(0)+" is not a capability"),
  "volition":           (1, lambda e,a: e(0)+" is wanted",
                            lambda e,a: e(0)+" is not wanted"),
  "intention":          (1, lambda e,a: e(0)+" is intended",
                            lambda e,a: e(0)+" is not intended"),
  "expectation":        (1, lambda e,a: e(0)+" is expected",
                            lambda e,a: e(0)+" is not expected"),
  "necessity":          (1, lambda e,a: e(0)+" is necessary",
                            lambda e,a: e(0)+" is not necessary"),
  "obligation":         (1, lambda e,a: e(0)+" is obligatory",
                            lambda e,a: e(0)+" is not obligatory"),
  "speech_act":         (1, lambda e,a: e(0)+" is a speech act",
                            lambda e,a: e(0)+" is not a speech act"),
  "has content":        (2, lambda e,a: e(0)+" is about "+e(1),
                            lambda e,a: e(0)+" is not about "+e(1)),
}


def _render_atom(atom, negated=False):
  """Unified atom-to-English renderer.  Dispatches via _PRED_TABLE for most
  predicates; handles special cases (holds, normally, $defq*, etc.) inline.

  negated=False: positive form ("X is Y")
  negated=True:  natural negated form ("X is not Y")
  """
  if not isinstance(atom, list) or not atom:
    return ("not: " + str(atom)) if negated else str(atom)

  pred = str(atom[0])
  args = atom[1:]

  def e(i):
    """Display name of args[i].

    When a clause-rendering context is active (see _intro / _RENDER_CTX),
    the first mention of a variable / world-constant / event-skolem in the
    clause gets a contextual prefix ("some X", "a situation V",
    "the event act1").  Otherwise falls back to entity_name() proof-mode.
    """
    if i >= len(args): return "?"
    return _intro(args[i])

  # ---- table-driven dispatch ----
  entry = _PRED_TABLE.get(pred)
  if entry is not None:
    min_args, pos_fn, neg_fn = entry
    if len(args) < min_args:
      return ("not: " if negated else "") + _atom_fallback(atom)
    if negated:
      if neg_fn is not None:
        return neg_fn(e, args)
      return "not: " + (pos_fn(e, args) if pos_fn else _atom_fallback(atom))
    if pos_fn is not None:
      return pos_fn(e, args)
    return _atom_fallback(atom)

  # ---- special predicates requiring recursive dispatch or custom logic ----

  if pred == "typical":
    if len(args) >= 1:
      return (e(0) + " is not typical") if negated else (e(0) + " is typical")
    return "not typical" if negated else "typically"

  if pred == "typically":
    if len(args) >= 2:
      if negated:
        return e(0) + " does not typically " + str(args[1])
      return e(0) + " typically " + _conjugate_verb(str(args[1]))
    return "not typically" if negated else "typically"

  if pred == "holds":
    if len(args) >= 2 and isinstance(args[1], list):
      return _render_atom(args[1], negated=negated)
    return ("not: " if negated else "") + _atom_fallback(atom)

  if pred == "normally":
    if len(args) >= 1 and isinstance(args[0], list):
      return "normally, " + _render_atom(args[0], negated=negated)
    return "normally"

  if pred == "kb holds":
    if len(args) >= 2 and isinstance(args[1], list):
      return _render_atom(args[1], negated=negated)
    return ("not: " if negated else "") + _atom_fallback(atom)

  if pred == "kb says":
    if len(args) >= 3 and isinstance(args[2], list):
      if negated:
        return "not: " + e(1) + " says that " + _render_atom(args[2])
      return e(1) + " says that " + _render_atom(args[2])
    return ("not: " if negated else "") + _atom_fallback(atom)

  if pred == "next":
    return ""

  # ---- $defq* question-definition atoms ----
  if pred.startswith("$defq"):
    if not args:
      return "the answer does not hold" if negated else "answer holds"
    if len(args) == 1:
      return (e(0) + " is not the answer") if negated else (e(0) + " is the answer")
    phrase = _prep_answer_phrase(args)
    return (phrase + " is not the answer") if negated else (phrase + " is the answer")

  # ---- traceability (skip in English) ----
  if pred in ("@id", "@p", "@definite"):
    if pred == "@id" and len(args) >= 2 and isinstance(args[1], list):
      return _render_atom(args[1], negated=negated)
    return ""

  # actuality is a pipeline-injected event marker — hide from English output.
  if pred == "actuality":
    return ""

  # ---- fallback ----
  if negated:
    return "not: " + _render_atom(atom)
  return _atom_fallback(atom)


def _atom_fallback(atom):
  """Fallback renderer: pred(arg1, arg2) with underscores as spaces."""
  if not isinstance(atom, list) or not atom:
    return str(atom)
  pred = str(atom[0]).replace("_", " ")
  parts = []
  for a in atom[1:]:
    if isinstance(a, str):
      parts.append(entity_name(a, with_url=True))
    elif isinstance(a, list):
      parts.append(_render_atom(a))
    else:
      parts.append(str(a))
  return pred + "(" + ", ".join(parts) + ")" if parts else pred


def _atom_to_english(atom):
  """Convert a single logic atom to readable English."""
  return _render_atom(atom, negated=False)


def _atom_to_english_negated(atom):
  """Render a single atom in its natural negated English form.

  The atom argument is the BASE atom (predicate name WITHOUT the leading "-").
  """
  return _render_atom(atom, negated=True)


