"""The atoms a bridge may be built from, and how they are displayed.

The foundation of the literal-bridge stack.  It reads a case's own clauses and
produces the candidate atoms the model is shown, and owns the three things
every layer above needs:

  * **display** — turning a clause literal into the atom form the model sees,
    and printing that form back;
  * **classification** — whether a clause came from the passage, the question
    or an axiom, and which of its literals carry content;
  * **shape** — when two atoms are the same up to renaming, what a clause
    literal's shape is, and which arguments are context.

Putting those at the bottom is what makes the stack acyclic.  Before the merge
the chain calculation reached up into the prompt builder for `printed_atom`
while the prompt builder reached back into the chain, and the rule parser and
the chain each reached into the other.  Nothing here imports another litbridge
module except the converter.

The last section reads the raw Stage-2 packages, before any conversion.  It is
the only place the SEMANTIC sign of an atom is recorded: a rule premise is not
a negative assertion because clausification negated it.  Dropping that sign
turns `not mean(X,Y) -> not mean(X,Y)` into `mean(X,Y) -> mean(X,Y)`, which is
a different rule about different things; that is what happened to folio-0183 in
the 08-10 pilot.
"""

import collections
import copy
import hashlib
import json
import re

import globals
import litbridge_converter as BW
import utils


# --------------------------------------------------------------- constants

VERSION = "litbridge_atoms/2026-08-15"

HELPER_SECTION = "helper"

CONTENT_ARITY = {
    "isa": 2, "is rel2": 3, "has type": 2, "has actor": 2, "has target": 2,
    "has recipient": 2, "has manner": 2, "has topic": 2, "has location": 3,
    "has property": 2, "has degree property": 4, "has degree rel2": 5,
    "have": 2, "has part": 2, "member": 2, "typical": 1,
}

CLAUSE_VAR = re.compile(r"^\?")

UNIT = re.compile(r"^sent_(S\d+)")

QUESTION, SOURCE, AXIOM, GENERATED = "question", "source", "axiom", "generated"

QUESTION, SOURCE, AXIOM, GENERATED = "question", "source", "axiom", "generated"

QUESTION, SOURCE, AXIOM, GENERATED = "question", "source", "axiom", "generated"

QUESTION, SOURCE, AXIOM, GENERATED = "question", "source", "axiom", "generated"

DISPLAY_VARS = ["?X", "?Y", "?Z", "?U", "?V", "?W", "?P", "?Q", "?R", "?S"]

_LEFT, _RIGHT = "?<L>", "?<R>"

_LEFT, _RIGHT = "?<L>", "?<R>"

PREMISE, CONSEQUENCE, BOTH = "PREMISE", "CONSEQUENCE", "BOTH"

PREMISE, CONSEQUENCE, BOTH = "PREMISE", "CONSEQUENCE", "BOTH"

PREMISE, CONSEQUENCE, BOTH = "PREMISE", "CONSEQUENCE", "BOTH"

UNIQUE, EMPTY, AMBIGUOUS = "unique", "empty", "ambiguous"

UNIQUE, EMPTY, AMBIGUOUS = "unique", "empty", "ambiguous"

UNIQUE, EMPTY, AMBIGUOUS = "unique", "empty", "ambiguous"

SKOLEM_NOTE = """SKOLEM CONSTANTS

A name beginning with `sk`, such as `sk0`, is a fresh constant standing for an
arbitrary unknown object introduced while translating the question. The same
name always denotes the same unknown object. A rule containing it is local to
that object; replace it by a variable only when the implication is genuinely
general."""

SET_BINDERS = ("$setof",)

MAIN_CAP = 80

SECONDARY_CAP = 24

# Formula heads that structure a Stage-2 package rather than assert something.
LOGICAL_HEADS = {
    "and", "or", "not", "xor", "implies", "forall", "exists", "normally",
    "holds", "question", "ask", "@id", "@p", "kb", "kb force", "kb holds",
}

STRUCTURAL_PREDICATES = frozenset(LOGICAL_HEADS)

# Predicate -> the kind of occurrence its atom introduces.
RELATION_PREDS = {
    "is rel2", "have", "has part", "member", "=", "has degree rel2",
}
PROPERTY_PREDS = {"has property", "has degree property"}
ROLE_PREDS = {
    "has actor", "has target", "has recipient", "has source", "has instrument",
    "has manner", "has beneficiary", "has accompaniment", "has topic",
    "has result", "has path", "has direction", "has content", "has cause",
    "has time", "has location", "has destination", "state time",
}
MODAL_PREDS = {
    "typical", "capability", "necessity", "obligation", "volition",
    "intention", "expectation", "speech_act", "actuality",
}

# Arity-independent: which argument of an atom carries the label, and which
# carry terms.  `LABEL_SLOT` is the 0-based index into the atom's arguments.
LABEL_SLOT = {
    "isa": 0, "has type": 1, "is rel2": 0, "has property": 0,
    "has degree property": 0, "has degree rel2": 0,
}


# ----------------------------------------------------------------- display

def display_atom(atom):
  """The atom as the model sees it: variables renamed `?X`, `?Y`, ... ."""
  names = {}

  def go(t):
    if is_variable_term(t):
      if t not in names:
        i = len(names)
        names[t] = DISPLAY_VARS[i] if i < len(DISPLAY_VARS) \
            else "?V%d" % (i + 1)
      return names[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]

def printed_atom(atom, negated=False):
  """The compact JSON of the full example: no space after a comma."""
  body = json.dumps(atom, ensure_ascii=False, separators=(",", ":"))
  return ("NOT " + body) if negated else body

def _display_from_literal(literal):
  """The writable atom a compiled literal stands for: content args only."""
  atom = unsigned_atom(literal)
  args = list(atom[1:])
  want = CONTENT_ARITY.get(str(atom[0]))
  if want is None:
    tail = len(args)
    while tail > 0 and isinstance(args[tail - 1], (str, list)) \
            and _is_plain_context(args[tail - 1]):
      tail -= 1
  else:
    if len(args) < want:
      return None
    tail = want
  if tail == 0 or not all(_is_context_argument(a) for a in args[tail:]):
    return None
  kept = [_strip_entity(a) for a in args[:tail]]
  return _display_clause_atom([atom[0]] + kept)

def _display_clause_atom(atom):
  """Rename CLAUSE variables to `?X`, `?Y`, ...  and nothing else.

  `unifier_abstraction.display_atom` renames every capitalised token, which
  would turn the world constant `W0` of `folio-0089`'s question clause into a
  rule variable before the model ever sees it.
  """
  names = {}

  def go(t):
    if isinstance(t, str):
      if is_clause_variable(t):
        if t not in names:
          i = len(names)
          names[t] = (DISPLAY_VARS[i] if i < len(DISPLAY_VARS)
                      else "?V%d" % (i + 1))
        return names[t]
      return t
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]

def _all_variable_term(term):
  if isinstance(term, str):
    return is_variable_term(term)
  if isinstance(term, list) and term:
    return all(_all_variable_term(x) for x in term[1:])
  return False

def _is_plain_context(term):
  """A context term that cannot be mistaken for content: `$c` or `$ctxt`."""
  if isinstance(term, str):
    return term == "$c"
  return isinstance(term, list) and bool(term) and str(term[0]) == "$ctxt"

def bare_predicate(pred):
  """`-p` is the negation of `p`.  The `-` is removed exactly once."""
  if isinstance(pred, str) and pred.startswith("-"):
    return pred[1:]
  return pred

def unsigned_atom(literal):
  """The literal without its sign: `["-isa","a","?:X"]` -> `["isa","a","?:X"]`."""
  return [bare_predicate(literal[0])] + list(literal[1:])

def sign_of(literal):
  p = literal[0] if isinstance(literal, list) and literal else None
  return "-" if isinstance(p, str) and p.startswith("-") else "+"


# --------------------------------------------------- clause classification

def _source_kind(clause):
  if clause.get("@sourcetype") == "question" or "@question" in clause:
    return QUESTION
  if clause.get("@sourcetype") == "populate":
    return GENERATED
  import re
  if re.match(r"^sent_", str(clause.get("@name") or "")):
    return SOURCE
  return AXIOM

def _content_literals(clause):
  out = []
  for lit in literals_of(clause.get("@logic") or clause.get("@question")):
    if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
      continue
    if is_control_predicate(lit[0]) or is_equality_predicate(lit[0]):
      continue
    out.append(lit)
  return out

def literals_of(payload):
  """A clause payload is one literal or a list of them."""
  if not isinstance(payload, list) or not payload:
    return []
  return [payload] if isinstance(payload[0], str) else list(payload)

def is_control_predicate(pred):
  """True for a control literal: the BASE predicate begins with `$`."""
  return str(bare_predicate(pred)).startswith("$")

def is_equality_predicate(pred):
  return str(bare_predicate(pred)) in ("=", "!=")


# -------------------------------------------------------------- atom shape

def alpha_equivalent(a, b):
  """Equal up to a consistent renaming of variables.  Constants are exact."""
  mapping, back = {}, {}

  def go(x, y):
    vx = isinstance(x, str) and is_variable_term(x)
    vy = isinstance(y, str) and is_variable_term(y)
    if vx or vy:
      if not (vx and vy):
        return False
      if mapping.get(x, y) != y or back.get(y, x) != x:
        return False
      mapping[x], back[y] = y, x
      return True
    if isinstance(x, str) or isinstance(y, str):
      return x == y
    if not (isinstance(x, list) and isinstance(y, list)):
      return False
    if len(x) != len(y) or x[0] != y[0]:
      return False
    return all(go(p, q) for p, q in zip(x[1:], y[1:]))
  return go(a, b)

def _clause_shape(atom):
  names = {}

  def go(t):
    if isinstance(t, str) and is_variable_term(t):
      names.setdefault(t, "?:R%d" % (len(names) + 1))
      return names[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]

def alpha_key(literal):
  """The literal up to variable renaming: sign, predicate, argument shape."""
  names = {}

  def go(t):
    if is_variable_term(t):
      names.setdefault(t, "_v%d" % len(names))
      return names[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return json.dumps([literal[0]] + [go(a) for a in literal[1:]])

def unify_unsigned_atoms(a, b):
  """-> {unifiable, substitution_left, substitution_right, reason}.

  `a` and `b` are atoms WITHOUT their signs.  Their variables are standardised
  apart before unification, so the caller may pass two literals that both use
  `?:X`.  A binding of the right literal's variable is printed with a trailing
  `'` so the two sides stay distinguishable in the record.
  """
  if not (isinstance(a, list) and a and isinstance(b, list) and b):
    return {"unifiable": False, "substitution_left": {},
            "substitution_right": {}, "reason": "not an atom"}
  if bare_predicate(a[0]) != bare_predicate(b[0]):
    return {"unifiable": False, "substitution_left": {},
            "substitution_right": {},
            "reason": "different predicates: %s and %s"
                      % (bare_predicate(a[0]), bare_predicate(b[0]))}
  if len(a) != len(b):
    return {"unifiable": False, "substitution_left": {},
            "substitution_right": {},
            "reason": "different arities: %d and %d" % (len(a) - 1,
                                                        len(b) - 1)}
  la, lb = _tag(unsigned_atom(a), _LEFT), _tag(unsigned_atom(b), _RIGHT)
  sub = {}
  ok, why = _unify(la, lb, sub)
  if not ok:
    return {"unifiable": False, "substitution_left": {},
            "substitution_right": {}, "reason": why}
  left, right = {}, {}
  for var in sub:
    value = _show(_resolve(var, sub))
    if var.startswith(_LEFT):
      left[_untag(var)] = value
    else:
      right[_untag(var)[:-1]] = value
  return {"unifiable": True, "substitution_left": left,
          "substitution_right": right, "reason": None}

def is_variable_term(term):
  """Either convention: a Stage-2 name, a clause `?:X`, or a display `?X`.

  The template layer is handed atoms from Stage 2 and, in a fixture or a
  round-trip, atoms already in display form.  A function that recognised only
  one of them would silently treat a variable as a constant and close a
  position that is open.
  """
  return is_stage2_variable(term) or is_clause_variable(term)

def is_clause_variable(term):
  return isinstance(term, str) and bool(CLAUSE_VAR.match(term))

def _is_context_argument(term):
  if isinstance(term, str):
    return is_variable_term(term) or term == "$c"
  return isinstance(term, list) and bool(term) and str(term[0]) == "$ctxt"


# ---------------------------------------------------------------- the rest

class UnificationError(Exception):
  """A term shape this layer refuses to interpret."""

_STAGE2_VAR = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

def is_stage2_variable(term):
  """Stage-2 writes a bound variable as a bare capitalised name.

  Not to be confused with `_is_var`, which asks whether a term is a variable
  of the little unifier below and answers on the `_LEFT` / `_RIGHT` prefixes.
  """
  return isinstance(term, str) and bool(_STAGE2_VAR.match(term))

def _tag(term, prefix):
  if isinstance(term, str):
    return prefix + term if is_clause_variable(term) else term
  if isinstance(term, list) and term:
    return [term[0]] + [_tag(x, prefix) for x in term[1:]]
  return term

def _is_var(term):
  return isinstance(term, str) and (term.startswith(_LEFT)
                                    or term.startswith(_RIGHT))

def _walk(term, sub):
  seen = 0
  while _is_var(term) and term in sub:
    term = sub[term]
    seen += 1
    if seen > 10000:                                  # pragma: no cover
      raise UnificationError("cyclic substitution")
  return term

def _occurs(var, term, sub):
  term = _walk(term, sub)
  if term == var:
    return True
  if isinstance(term, list):
    return any(_occurs(var, x, sub) for x in term[1:])
  return False

def _unify(a, b, sub):
  a, b = _walk(a, sub), _walk(b, sub)
  if a == b:
    return True, None
  if _is_var(a):
    if _occurs(a, b, sub):
      return False, "occurs check: %s occurs in %s" % (_untag(a),
                                                       _show(b))
    sub[a] = b
    return True, None
  if _is_var(b):
    if _occurs(b, a, sub):
      return False, "occurs check: %s occurs in %s" % (_untag(b),
                                                       _show(a))
    sub[b] = a
    return True, None
  if isinstance(a, str) or isinstance(b, str):
    return False, "different constants: %s and %s" % (_show(a), _show(b))
  if not (isinstance(a, list) and isinstance(b, list)):
    return False, "unsupported term shape"
  if a[0] != b[0]:
    return False, "different functors: %s and %s" % (a[0], b[0])
  if len(a) != len(b):
    return False, "different arities: %d and %d" % (len(a) - 1, len(b) - 1)
  for x, y in zip(a[1:], b[1:]):
    ok, why = _unify(x, y, sub)
    if not ok:
      return False, why
  return True, None

def _untag(term):
  if isinstance(term, str):
    if term.startswith(_LEFT):
      return term[len(_LEFT):]
    if term.startswith(_RIGHT):
      return term[len(_RIGHT):] + "'"
    return term
  if isinstance(term, list) and term:
    return [term[0]] + [_untag(x) for x in term[1:]]
  return term

def _show(term):
  t = _untag(term)
  return t if isinstance(t, str) else json.dumps(t)

def _resolve(term, sub):
  term = _walk(term, sub)
  if isinstance(term, list):
    return [term[0]] + [_resolve(x, sub) for x in term[1:]]
  return term

def are_resolution_partners(a, b):
  """Opposite signs, same unsigned predicate, same arity, and unifiable."""
  if not (isinstance(a, list) and a and isinstance(b, list) and b):
    return False
  if sign_of(a) == sign_of(b):
    return False
  if bare_predicate(a[0]) != bare_predicate(b[0]):
    return False
  if len(a) != len(b):
    return False
  return unify_unsigned_atoms(a, b)["unifiable"]

def clause_literals(view):
  """Every literal occurrence of the stored final clauses.

  Control literals are recorded and flagged, not silently dropped: their
  presence is why a clause is there, and the count of what was excluded is
  part of the record.
  """
  out = []
  for ci, clause in enumerate(view.get("final_clauses") or []):
    if not isinstance(clause, dict):
      continue
    payload = clause.get("@question") if "@question" in clause \
        else clause.get("@logic")
    for li, lit in enumerate(literals_of(payload)):
      if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
        continue
      pred = bare_predicate(lit[0])
      out.append({
          "literal_id": "C%d.%d" % (ci, li),
          "clause_name": clause.get("@name"),
          "clause_index": ci,
          "literal_index": li,
          "sign": "negative" if sign_of(lit) == "-" else "positive",
          "sign_symbol": sign_of(lit),
          "predicate": pred,
          "arguments": list(lit[1:]),
          "clause_literal": lit,
          "source_kind": _source_kind_by_unit(clause),
          "is_control": is_control_predicate(lit[0]),
          "is_equality": is_equality_predicate(lit[0]),
          "in_question_clause": _source_kind_by_unit(clause) == QUESTION,
      })
  return out

def annotate_partners(occurrences):
  """Fill `resolution_partner_count` and `distinct_partner_shape_count`.

  Counted over LITERAL OCCURRENCES, so one axiom copied five times shows as
  five partners; the distinct alpha-normalised shape count is recorded beside
  it so that a repeated axiom does not look like five different ways to
  resolve.  The occurrence count is what orders the display; the shape count
  is a diagnostic and a tie-breaker.
  """
  content = [o for o in occurrences if not o["is_control"]]
  for o in content:
    partners, shapes = [], set()
    for other in content:
      if other is o:
        continue
      if are_resolution_partners(o["clause_literal"],
                                 other["clause_literal"]):
        partners.append(other["literal_id"])
        shapes.add(alpha_key(other["clause_literal"]))
    o["resolution_partner_count"] = len(partners)
    o["distinct_partner_shape_count"] = len(shapes)
    o["resolution_partners"] = partners[:12]
  for o in occurrences:
    if o["is_control"]:
      o["resolution_partner_count"] = None
      o["distinct_partner_shape_count"] = None
      o["resolution_partners"] = []
  return occurrences

def inventory(view):
  """The complete clause-literal layer, with counts and what it excluded."""
  occs = annotate_partners(clause_literals(view))
  content = [o for o in occs if not o["is_control"]]
  return {
      "version": VERSION,
      "occurrences": occs,
      "content_occurrences": content,
      "counts": {
          "literals": len(occs),
          "content_literals": len(content),
          "control_literals": sum(1 for o in occs if o["is_control"]),
          "equality_literals": sum(1 for o in content if o["is_equality"]),
          "by_source_kind": _tally(o["source_kind"] for o in content),
      },
      "control_predicates_excluded": sorted(set(
          o["predicate"] for o in occs if o["is_control"])),
      "policy": "a literal whose BASE predicate begins `$` is a control "
                "literal and is excluded from the abstraction inventory; a "
                "`$` inside an argument does not make the content predicate a "
                "control predicate. Equality is counted but never displayed.",
  }

def _tally(items):
  out = {}
  for x in items:
    out[x] = out.get(x, 0) + 1
  return out

def print_atom(atom, negated=False):
  body = json.dumps(atom, ensure_ascii=False)
  return ("NOT " + body) if negated else body

def _norm_constant(term):
  """The converter's two mechanical rewritings of a constant, undone.

  Stage 2 writes an entity id `Emily 4`; the clause writes `#:Emily 4`, and a
  class word may reach the clause lower-cased (`Dried Thai chili` becomes
  `dried thai chili`).  Both are deterministic markings of the SAME constant,
  and undoing them is not guessing a converted predicate: the predicate, the
  arity and the argument order still have to match exactly.

  Used ONLY when matching a Stage-2 template to a clause literal.  The raw
  clause-to-clause unifier never does this — there, constants match only
  themselves.
  """
  t = term[2:] if term.startswith("#:") else term
  return t.lower()

def stage2_atoms(view):
  """-> [{atom, sign, unit, rule_side, in_question, occurrence_id}].

  From `stage2_occurrences` below, which records the semantic sign.
  """
  out = []
  for occ in stage2_occurrences(view.get("stage2"), view.get("stage1")):
    if occ["kind"] == "rule_variable":
      continue
    args = occ.get("arguments_or_roles")
    if not isinstance(args, list) or not occ.get("predicate"):
      continue
    atom = [occ["predicate"]] + list(args)
    out.append({"atom": atom, "sign": literal_sign(occ),
                "unit": occ.get("unit_id"), "rule_side": occ.get("rule_side"),
                "in_question": bool(occ.get("in_question")),
                "occurrence_id": occ.get("occurrence_id"),
                "kind": occ.get("kind")})
  return out

def _source_kind_by_unit(clause):
  if clause.get("@sourcetype") == "question" or "@question" in clause:
    return QUESTION
  if clause.get("@sourcetype") == "populate":
    return GENERATED
  if UNIT.match(str(clause.get("@name") or "")):
    return SOURCE
  return AXIOM

class CandidateError(Exception):
  """The candidate layer cannot proceed.  Never worked around."""

def is_skolem(term):
  """A constant the question's translation invented, e.g. `sk0`, `sk0_farm`."""
  if not isinstance(term, str):
    return False
  t = term[2:] if term.startswith("#:") else term
  return t.startswith("sk") and not t.startswith("skol")

def has_skolem(atom):
  def go(t):
    if isinstance(t, str):
      return is_skolem(t)
    if isinstance(t, list):
      return any(go(x) for x in t[1:])
    return False
  return any(go(a) for a in atom[1:])

def free_variables(term_or_atom):
  """Stage-2 variables that are FREE, in first-appearance order.

  A variable declared by a set binder — `["$setof", V, ID, BODY]` — is local
  to that term.  Collecting it as a free rule variable is how a set
  expression's bound variable would end up universally quantified at the
  outer level, which is a different formula about different things.
  """
  out = []

  def go(t, bound):
    if isinstance(t, str):
      if is_variable_term(t) and t not in bound and t not in out:
        out.append(t)
      return
    if not isinstance(t, list) or not t:
      return
    if isinstance(t[0], str) and t[0] in SET_BINDERS and len(t) >= 3:
      local = set(bound)
      if isinstance(t[1], str) and is_variable_term(t[1]):
        local.add(t[1])
      for x in t[2:]:
        go(x, local)
      return
    for x in t[1:]:
      go(x, bound)
  go(term_or_atom, set())
  return out

def _packages(atoms_with_signs):
  """-> [(package id, holds package)] for a batch of signed atoms.

  The atom's free variables are universally quantified.  Without the
  quantifier the converter treats a bare `X` as a CONSTANT, and the resulting
  literal then fails to unify with the clause literals that carry a real
  variable — which silently gave a candidate the wrong role.
  """
  out = []
  for i, (atom, sign) in enumerate(atoms_with_signs, start=1):
    body = ["not", copy.deepcopy(atom)] if sign == "-" \
        else copy.deepcopy(atom)
    for v in reversed(free_variables(atom)):
      body = ["forall", v, body]
    out.append(("Cv%d" % i, ["holds", "W0", body]))
  return out

def _convert_once(view, specs, configuration):
  edited = copy.deepcopy(view["stage2"])
  if not (isinstance(edited, list) and edited and edited[0] == "and"):
    raise CandidateError("stage2 is not an [\"and\", ...] list")
  for pid, pkg in specs:
    edited.append(["@id", pid, pkg])
  clauses, _fixes = BW._convert(edited, view["stage1"],
                                BW.bridge_options(configuration))
  collapse = not BW._base_uses_ctxt_terms(view.get("final_clauses"))
  out, counter = {}, [0]
  for pid, _pkg in specs:
    mine = [c for c in clauses
            if str(c.get("@name") or "") == "sent_%s" % pid
            or str(c.get("@name") or "").startswith("sent_%s_" % pid)]
    mine = [c for c in mine if c.get("@sourcetype") != "populate"]
    if collapse and mine:
      mine = BW._share_ctxt(mine, counter)
    out[pid] = mine
  return out

def convert_batch(view, atoms_with_signs, configuration, errors=None):
  """Convert every signed atom in ONE isolated conversion.

  Each atom is spliced in as its own `@id` package and only that package's
  own clauses are kept, so the atoms cannot contaminate each other's result.
  The option scope is `litbridge_converter.bridge_options`, which is the case's own
  configuration with the two passes that destroy a bridge turned off — the
  same scope a rule built from these atoms will be compiled under, so a
  candidate's GK form predicts what a rule using it will produce.

  A batch that raises is SPLIT and retried, down to single atoms, so one atom
  the converter refuses cannot silently remove the rest of the list.  The
  atoms that raise on their own are recorded in `errors`, never dropped
  quietly.
  """
  specs = _packages(atoms_with_signs)
  errors = errors if errors is not None else []

  def run(chunk):
    if not chunk:
      return {}
    try:
      return _convert_once(view, chunk, configuration)
    except Exception as e:                                  # noqa: BLE001
      if len(chunk) == 1:
        pid, pkg = chunk[0]
        errors.append({"package_id": pid, "package": pkg,
                       "error": "%s: %s" % (type(e).__name__, e)})
        return {pid: []}
      half = len(chunk) // 2
      out = run(chunk[:half])
      out.update(run(chunk[half:]))
      return out
  return run(specs)

def conversion_of(clauses):
  """-> (status, [converted content literals]).

  `unique` when exactly one distinct content literal shape came back;
  `empty` when none did; `ambiguous` when the atom converts to several
  different content literals, which no single candidate can stand for.
  """
  lits = _content_literals_of_clauses(clauses)
  seen, distinct = set(), []
  for lit in lits:
    key = alpha_key(lit)
    if key in seen:
      continue
    seen.add(key)
    distinct.append(lit)
  if not distinct:
    return EMPTY, []
  if len(distinct) > 1:
    return AMBIGUOUS, distinct
  return UNIQUE, distinct

def _is_generic(literal):
  """A generic axiom shape: every argument is a variable."""
  args = list(literal[1:])
  if not args:
    return True
  return all(is_variable_term(a) for a in args)

def role_occurrences(occurrences):
  """The literals a role may be derived from.

  Two kinds of literal are excluded, for the same reason: they are properties
  of the ENCODING rather than of the passage, and both signs of them exist for
  everything, so counting them makes every candidate `BOTH` and every cost
  identical.

    * a population clause — `isa(animal, $some_animal)` and its negative twin
      — is a witness the converter emits for every class so the theory is not
      vacuous;
    * a generic frame axiom whose arguments are ALL variables — the
      `is rel2(?V,?A,?O,?C)` pair that ties any relation to its event — makes
      every relation look both suppliable and needed.

  Both stay in the record and are matched separately; neither confers a role.
  """
  return [o for o in occurrences
          if not o["is_control"] and o["source_kind"] != GENERATED
          and not _is_generic(unsigned_atom(o["clause_literal"]))]

def match_occurrences(literal, occurrences):
  """-> ({same-sign}, {opposite-sign}, {population-only matches}).

  Ordinary unification against the literals gk actually received, with every
  argument the clause has.  Sign is read off the converted literal itself.
  """
  sign = sign_of(literal)
  atom = unsigned_atom(literal)
  same, opposite, population = [], [], []
  for o in occurrences:
    if o["is_control"]:
      continue
    if not unify_unsigned_atoms(
            atom, unsigned_atom(o["clause_literal"]))["unifiable"]:
      continue
    if o["source_kind"] == GENERATED or _is_generic(
            unsigned_atom(o["clause_literal"])):
      population.append(o)
    else:
      (same if o["sign_symbol"] == sign else opposite).append(o)
  return same, opposite, population

def role_of(same, opposite):
  """PREMISE / CONSEQUENCE / BOTH, or None when the atom has no role."""
  if same and opposite:
    return BOTH
  if same:
    return PREMISE
  if opposite:
    return CONSEQUENCE
  return None

def _same_shape(surface, gk_literal):
  """Is the converted form materially the same line as the surface atom?"""
  a = display_atom(surface)
  b = display_atom(unsigned_atom(gk_literal))
  return json.dumps(a) == json.dumps(b)

def stage2_signed_atoms(view):
  """Every distinct Stage-2 content atom, in both signs, with its provenance.

  Both signs are built for every atom: the sign a candidate is USEFUL in is a
  fact about the clauses, not about how the sentence happened to be written,
  and `role_of` decides which of the two survives.
  """
  rows, order = {}, []
  for row in stage2_atoms(view):
    atom = row["atom"]
    if is_control_predicate(atom[0]) or is_equality_predicate(
            atom[0]):
      continue
    key = alpha_key(atom)
    if key not in rows:
      rows[key] = {"atom": atom, "units": [], "occurrence_ids": [],
                   "in_question": False, "rule_sides": []}
      order.append(key)
    r = rows[key]
    if row["unit"] not in r["units"]:
      r["units"].append(row["unit"])
    r["occurrence_ids"].append(row["occurrence_id"])
    r["in_question"] = r["in_question"] or row["in_question"]
    if row["rule_side"] not in r["rule_sides"]:
      r["rule_sides"].append(row["rule_side"])
  return [rows[k] for k in order]

def _strip_entity(term):
  if isinstance(term, str) and term.startswith("#:"):
    return term[2:]
  if isinstance(term, list) and term:
    return [term[0]] + [_strip_entity(x) for x in term[1:]]
  return term

def surface_guesses(literal):
  """Candidate SURFACE forms for a clause literal, most likely first.

  A clause literal carries what the converter added: an entity marker on a
  constant, and a trailing context argument.  Undoing those is a guess, so
  every guess is verified by converting it again and checking that it returns
  to this literal; an unverified guess is dropped, never displayed.
  """
  atom = unsigned_atom(literal)
  args = list(atom[1:])
  out = []
  for drop in (1, 0, 2):
    if drop and len(args) - drop < 1:
      continue
    trimmed = args[:len(args) - drop] if drop else list(args)
    out.append([atom[0]] + [_strip_entity(a) for a in trimmed])
  seen, uniq = set(), []
  for a in out:
    k = json.dumps(a)
    if k in seen:
      continue
    seen.add(k)
    uniq.append(a)
  return uniq

def _to_display_variables(atom):
  """Clause variables (`?:X`) become Stage-2 variables (`V1`, `V2`, ...)."""
  names = {}

  def go(t):
    if isinstance(t, str) and is_variable_term(t):
      names.setdefault(t, "V%d" % (len(names) + 1))
      return names[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]

def _content_literals_of_clauses(clauses):
  """Every non-control literal of these clauses, flattened."""
  out = []
  for c in clauses:
    for lit in literals_of(c.get("@logic")):
      if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
        continue
      if is_control_predicate(lit[0]):
        continue
      out.append(lit)
  return out

def printed_candidate_atom(atom, sign):
  return print_atom(display_atom(atom), negated=sign == "-")

def opposite_sign_unifiers(literal, pool):
  """How many DISTINCT opposite-sign literal shapes this one can meet.

  Over the valid pool only — population witnesses and generic all-variable
  frame axioms are properties of the encoding, not of the passage, and both
  signs of them exist for everything.  One axiom copied five times is one
  shape.
  """
  sign = sign_of(literal)
  atom = unsigned_atom(literal)
  shapes = set()
  for o in pool:
    if o["sign_symbol"] == sign:
      continue
    if unify_unsigned_atoms(
            atom, unsigned_atom(o["clause_literal"]))["unifiable"]:
      shapes.add(alpha_key(o["clause_literal"]))
  return len(shapes)

def _rank(row):
  """Question-clause content first, then fewest opposite-sign unifiers."""
  return (0 if row["question_linked"] else 1,
          row["priority_cost"],
          0 if row["role"] in (CONSEQUENCE, BOTH) else 1,
          json.dumps(display_atom(row["surface_atom"])),
          row["sign"], row.get("converted_variant_index") or 0)

def render_candidate(row):
  lines = ["  %-4s %s" % (row["id"], row["printed"])]
  lines.append("       USE: %s" % row["role"])
  lines.append("       PRIORITY COST: %d" % row["priority_cost"])
  if row.get("show_gk_form"):
    lines.append("       GK FORM: %s" % row["gk_form_printed"])
  if (row.get("converted_variant_count") or 1) > 1:
    lines.append("       NOTE: this atom also converts to %d other clause "
                 "form(s); a rule using it produces all of them"
                 % (row["converted_variant_count"] - 1))
  return "\n".join(lines)

def render_body(main, secondary):
  parts = []
  if any(has_skolem(r["surface_atom"]) for r in list(main) + list(secondary)):
    parts.append(SKOLEM_NOTE)
  parts.append("MAIN CANDIDATES\n\n%s"
               % "\n\n".join(render_candidate(r) for r in main))
  if secondary:
    parts.append("SECONDARY CANDIDATES\n\n%s"
                 % "\n\n".join(render_candidate(r) for r in secondary))
  return "\n\n".join(parts)

def _record(surface, sign, gk_literal, same, opposite, status, all_literals,
            variant_index, origin, pool, population=(), extra=None):
  role = role_of(same, opposite)
  matches = same + opposite
  question_linked = any(o["source_kind"] == QUESTION for o in matches)
  cost = opposite_sign_unifiers(gk_literal, pool) if gk_literal else 0
  rec = {
      "surface_atom": surface,
      "sign": sign,
      "printed": printed_candidate_atom(surface, sign),
      "conversion_status": status,
      "converted_variant_index": variant_index,
      "converted_variant_count": len(all_literals),
      "all_converted_literals": all_literals,
      "one_surface_atom_compiles_to_several_clauses": len(all_literals) > 1,
      "gk_form": gk_literal,
      "gk_form_printed": (print_atom(
          display_atom(unsigned_atom(gk_literal)),
          negated=sign_of(gk_literal) == "-") if gk_literal else None),
      "show_gk_form": bool(gk_literal) and not _same_shape(surface,
                                                               gk_literal),
      "matched_same_sign": [o["literal_id"] for o in same],
      "matched_opposite_sign": [o["literal_id"] for o in opposite],
      "matched_encoding_only": [o["literal_id"] for o in population],
      "matched_valid_occurrences": len(matches),
      "no_valid_source_occurrence": not matches,
      "matched_source_kinds": sorted(set(o["source_kind"] for o in matches)),
      "same_sign_source_kinds": sorted(set(o["source_kind"] for o in same)),
      "opposite_sign_source_kinds": sorted(set(o["source_kind"]
                                               for o in opposite)),
      "role": role,
      "question_linked": question_linked,
      "priority_cost": cost,
      "priority_basis": "distinct opposite-sign literal shapes the converted "
                        "literal unifies with, over source, question and "
                        "non-generic axiom clauses",
      "question_ordering": "question-clause candidates are a separate, "
                           "earlier group; the number is not adjusted",
      "origin": origin,
  }
  rec.update(extra or {})
  return rec

def build_main(view, configuration, inventory, cap=MAIN_CAP):
  """-> (shown, omitted, diagnostics).  One candidate per converted literal."""
  pool = role_occurrences(inventory["occurrences"])
  atoms = stage2_signed_atoms(view)
  batch = []
  for row in atoms:
    batch.append((row["atom"], "+"))
    batch.append((row["atom"], "-"))
  errors = []
  converted = convert_batch(view, batch, configuration,
                            errors=errors) if batch else {}
  rows, diagnostics = [], []
  for e in errors:
    diagnostics.append({"package_id": e["package_id"],
                        "conversion_status": "converter_error",
                        "error": e["error"][:200],
                        "why_it_is_not_scored":
                            "the converter raised on this atom in "
                            "isolation"})
  for i, row in enumerate(atoms):
    for j, sign in enumerate(("+", "-")):
      pid = "Cv%d" % (2 * i + j + 1)
      status, lits = conversion_of(converted.get(pid) or [])
      if status == EMPTY:
        diagnostics.append({
            "surface_atom": row["atom"], "sign": sign,
            "printed": printed_candidate_atom(row["atom"], sign),
            "conversion_status": status,
            "why_it_is_not_scored":
                "isolated conversion produced no content literal"})
        continue
      for k, lit in enumerate(lits):
        same, opposite, population = match_occurrences(
            lit, inventory["occurrences"])
        rec = _record(
            row["atom"], sign, lit, same, opposite, status, lits, k,
            "stage2", pool, population,
            {"units": row["units"],
             "occurrence_ids": row["occurrence_ids"],
             "stage2_in_question": row["in_question"],
             "stage2_rule_sides": row["rule_sides"]})
        if rec["role"] is None:
          diagnostics.append({
              "surface_atom": row["atom"], "sign": sign,
              "printed": rec["printed"],
              "conversion_status": status,
              "converted_variant_index": k,
              "gk_form": lit,
              "matched_encoding_only": rec["matched_encoding_only"],
              "why_it_is_not_scored":
                  "this converted form occurs in no clause of either "
                  "sign, apart from population witnesses and generic "
                  "frame axioms, so it can be neither supplied nor "
                  "needed"})
          continue
        rows.append(rec)
  rows.sort(key=_rank)
  kept = rows[:cap]
  _assign_ids(kept, "M")
  return kept, rows[cap:], diagnostics

def _assign_ids(rows, prefix):
  by_surface = collections.defaultdict(list)
  for i, r in enumerate(rows, start=1):
    r["id"] = "%s%d" % (prefix, i)
    by_surface[(json.dumps(r["surface_atom"]), r["sign"])].append(r["id"])
  for r in rows:
    siblings = by_surface[(json.dumps(r["surface_atom"]), r["sign"])]
    r["shares_surface_atom_with"] = [x for x in siblings if x != r["id"]]
  return rows

def build_secondary(view, configuration, inventory, main, cap=SECONDARY_CAP):
  """-> (shown, omitted).  Final-clause content the main list does not carry.

  A nested clause-side term is NOT excluded here: `eventprop` and `$setof`
  forms are exactly what v3 lost, and the round trip is what keeps them
  honest.  A guess whose conversion does not return the literal it came from
  is dropped with its reason.
  """
  pool = role_occurrences(inventory["occurrences"])
  taken = set()
  for r in main:
    for lit in r.get("all_converted_literals") or []:
      taken.add(alpha_key(unsigned_atom(lit)))
  order = {SOURCE: 0, QUESTION: 1, AXIOM: 2, GENERATED: 9}
  candidates, omitted, seen = [], [], set()
  for o in sorted(inventory["occurrences"],
                  key=lambda x: (order.get(x["source_kind"], 5),
                                 x["clause_index"], x["literal_index"])):
    lit = o["clause_literal"]
    if o["is_control"]:
      continue
    if o["is_equality"]:
      omitted.append({"literal_id": o["literal_id"],
                      "why": "equality is not part of this experiment"})
      continue
    if o["source_kind"] == GENERATED:
      omitted.append({"literal_id": o["literal_id"],
                      "why": "a generated population clause"})
      continue
    if str(o["predicate"]) in STRUCTURAL_PREDICATES:
      # `kb holds` scopes a knowledge base; it is structure, not content,
      # and a rule may not be written about it
      omitted.append({"literal_id": o["literal_id"],
                      "printed": print_atom(display_atom(
                          unsigned_atom(lit))),
                      "why": "a structural predicate (`%s`), not content"
                             % o["predicate"]})
      continue
    key = alpha_key(unsigned_atom(lit))
    if key in taken or key in seen:
      continue
    seen.add(key)
    if _is_generic(unsigned_atom(lit)):
      omitted.append({"literal_id": o["literal_id"],
                      "printed": print_atom(display_atom(
                          unsigned_atom(lit))),
                      "why": "a generic axiom shape: every argument is a "
                             "variable"})
      continue
    candidates.append(o)
  if not candidates:
    return [], omitted
  tries, index = [], []
  for o in candidates[:cap * 4]:
    for guess in surface_guesses(o["clause_literal"]):
      surface = _to_display_variables(guess)
      tries.append((surface, "+"))
      index.append((o, surface))
  errors = []
  converted = convert_batch(view, tries, configuration,
                            errors=errors) if tries else {}
  for e in errors:
    omitted.append({"package_id": e["package_id"],
                    "why": "the converter refused this surface form: %s"
                           % e["error"][:160]})
  rows, used = [], set()
  for k, (o, surface) in enumerate(index, start=1):
    if len(rows) >= cap:
      break
    if o["literal_id"] in used:
      continue
    status, lits = conversion_of(converted.get("Cv%d" % k) or [])
    if status == EMPTY:
      continue
    want = unsigned_atom(o["clause_literal"])
    back = [l for l in lits
            if unify_unsigned_atoms(unsigned_atom(l),
                                       want)["unifiable"]]
    if not back:
      continue
    used.add(o["literal_id"])
    sign = o["sign_symbol"]
    for variant, got in enumerate(back):
      signed = got if sign == "+" else \
          ["-" + bare_predicate(got[0])] + list(got[1:])
      same, opposite, population = match_occurrences(
          signed, inventory["occurrences"])
      rec = _record(surface, sign, signed, same, opposite, status, lits,
                    lits.index(got), "final_clause", pool, population,
                    {"from_literal_id": o["literal_id"],
                     "from_clause": o["clause_name"],
                     "from_source_kind": o["source_kind"],
                     "round_trip": {
                         "surface": surface,
                         "converted": lits,
                         "matched_the_clause_literal": want}})
      if rec["role"] is None:
        continue
      rows.append(rec)
  for o in candidates:
    if o["literal_id"] not in used:
      omitted.append({"literal_id": o["literal_id"],
                      "printed": print_atom(display_atom(
                          unsigned_atom(o["clause_literal"]))),
                      "why": "no surface form of it converted back to "
                             "this literal, or the secondary cap was "
                             "reached"})
  rows.sort(key=_rank)
  _assign_ids(rows, "S")
  return rows, omitted

def build(view, configuration, main_cap=MAIN_CAP, secondary_cap=SECONDARY_CAP):
  found = inventory(view)
  main, main_omitted, diagnostics = build_main(view, configuration,
                                               found, cap=main_cap)
  secondary, secondary_omitted = build_secondary(view, configuration,
                                                 found, main,
                                                 cap=secondary_cap)
  body = render_body(main, secondary)
  split = sum(1 for r in main + secondary
              if r["one_surface_atom_compiles_to_several_clauses"])
  nested = sum(1 for r in main + secondary
               if any(isinstance(a, list) for a in r["surface_atom"][1:]))
  return {
      "version": VERSION,
      "inventory_counts": found["counts"],
      "occurrences": found["occurrences"],
      "main": main,
      "main_omitted": [{"printed": r["printed"], "role": r["role"],
                        "priority_cost": r["priority_cost"]}
                       for r in main_omitted],
      "secondary": secondary,
      "secondary_omitted": secondary_omitted,
      "mapping_diagnostics": diagnostics,
      "skolem_note_shown": any(has_skolem(r["surface_atom"])
                               for r in main + secondary),
      "body": body,
      "counts": {"main": len(main), "main_omitted": len(main_omitted),
                 "secondary": len(secondary),
                 "secondary_omitted": len(secondary_omitted),
                 "mapping_diagnostics": len(diagnostics),
                 "candidates_from_a_multi_output_conversion": split,
                 "candidates_with_a_nested_term": nested},
      "policy": "every candidate is converted by the real converter and "
                "matched as a clause literal; an atom whose conversion has "
                "several outputs contributes one candidate per output, and a "
                "nested term is kept when the round trip returns the clause "
                "literal it came from. A candidate whose converted form "
                "occurs in no clause of either sign is a recorded "
                "diagnostic, not a displayed line.",
  }


# ------------------------------------------------- the raw Stage-2 reading

# An occurrence is one use of a class, property, relation, event, event role or
# rule variable in a Stage-2 package, tied to the JSON path it came from and,
# where the text supports it, to a span of the source sentence.  A span is
# recorded only when the label occurs literally in the unit's sentence: one hit
# is `exact`, several are `repeated` (all offsets kept, none chosen), none is
# `unavailable`.  Offsets are never invented.

def normalize_label(label):
  """Lowercase, collapse whitespace, drop a leading determiner and a trailing
  Stage-1 entity number.  Multiword labels stay whole."""
  if not isinstance(label, str):
    return ""
  t = re.sub(r"\s+", " ", label.strip().lower())
  t = re.sub(r"^(the|a|an) ", "", t)
  t = re.sub(r"^#:", "", t)
  t = re.sub(r" \d+$", "", t)
  return t

def _spans(text, needle):
  """All literal spans of `needle` in `text`, case-insensitively."""
  if not text or not needle or not isinstance(needle, str):
    return []
  out, low, n = [], text.lower(), needle.lower().strip()
  if not n:
    return []
  i = low.find(n)
  while i >= 0:
    out.append([i, i + len(n)])
    i = low.find(n, i + 1)
  return out

def _match_status(spans):
  if not spans:
    return "unavailable"
  return "exact" if len(spans) == 1 else "repeated"

class Occurrence(dict):
  """A dict, so it serialises directly."""

  @property
  def id(self):
    return self["occurrence_id"]

def _mk(unit_id, stage, path, kind, label, term, sentence, **kw):
  spans = _spans(sentence, label if isinstance(label, str) else None)
  occ = Occurrence({
      "occurrence_id": "%s:%s:%s" % (unit_id, stage, path),
      "unit_id": unit_id,
      "source_sentence": sentence,
      "source_quote": label if spans else None,
      "source_offsets": spans or None,
      "source_match_status": _match_status(spans),
      "stage": stage,
      "json_path": path,
      "kind": kind,
      "label": label,
      "normalized_label": normalize_label(label),
      "term": term,
      "arguments_or_roles": kw.pop("arguments_or_roles", None),
      "polarity": kw.pop("polarity", "+"),
      "binder_stack": kw.pop("binder_stack", []),
      "rule_side": kw.pop("rule_side", "none"),
  })
  occ.update(kw)
  return occ

def _stage1_units(stage1):
  for si, sent in enumerate(stage1 or []):
    if not isinstance(sent, dict):
      continue
    for ui, u in enumerate(sent.get("units") or []):
      yield si, ui, sent, u

def stage2_packages(stage2):
  out = []
  if isinstance(stage2, list) and stage2 and stage2[0] == "and":
    for it in stage2[1:]:
      if isinstance(it, list) and len(it) >= 3 and it[0] == "@id":
        out.append((it[1], it[2]))
  return out

def _atom_occurrences(atom, unit_id, path, sentence, binders, side, polarity,
                      in_question):
  """One predicate atom -> zero or more occurrences."""
  pred = atom[0]
  args = atom[1:]
  kind = ("class" if pred == "isa" else
          "property" if pred in PROPERTY_PREDS else
          "relation" if pred in RELATION_PREDS else
          "event_role" if pred in ROLE_PREDS else
          "event" if pred == "has type" else
          "modal" if pred in MODAL_PREDS else
          "other")
  slot = LABEL_SLOT.get(pred)
  label = args[slot] if (slot is not None and slot < len(args)) else pred
  if pred == "has type":
    label = args[1] if len(args) > 1 else pred
  terms = [a for i, a in enumerate(args) if i != slot]
  event_term = None
  if pred in ROLE_PREDS and len(args) >= 2:
    # A role atom is about its filler: ["has target", E, filler].  Carrying
    # the event as the term would make every role occurrence look like the
    # event and hide the filler.
    event_term = args[0]
    terms = [args[1]] + [a for a in args[2:]]
  occ = _mk(unit_id, "s2", path, kind, label if isinstance(label, str) else pred,
            terms[0] if terms else None, sentence,
            predicate=pred, event_term=event_term,
            arguments_or_roles=list(args),
            polarity=polarity, binder_stack=list(binders), rule_side=side,
            in_question=in_question,
            term_is_variable=is_stage2_variable(terms[0]) if terms else None,
            label_is_variable=is_stage2_variable(label))
  out = [occ]
  # a bound variable used as a term is itself an occurrence worth naming
  for ai, a in enumerate(args):
    if is_stage2_variable(a) and any(b[1] == a for b in binders):
      out.append(_mk(unit_id, "s2", "%s/%d" % (path, ai + 1),
                     "rule_variable", a, a, sentence,
                     predicate=pred, arg_index=ai,
                     term_is_variable=True, label_is_variable=True,
                     polarity=polarity, binder_stack=list(binders),
                     rule_side=side, in_question=in_question))
  return out

def stage2_occurrences(stage2, stage1=None):
  """-> [Occurrence] over the raw packages, before any conversion."""
  text_by_unit = {}
  for si, ui, sent, u in _stage1_units(stage1 or []):
    text_by_unit[u.get("unit_id")] = u.get("text") or sent.get("raw") or ""
  out = []

  def walk(node, unit_id, path, binders, side, polarity, in_question):
    if not isinstance(node, list) or not node:
      return
    head = node[0]
    if not isinstance(head, str):
      for i, ch in enumerate(node):
        walk(ch, unit_id, "%s/%d" % (path, i), binders, side, polarity,
             in_question)
      return
    sentence = text_by_unit.get(unit_id, "")
    if head in ("forall", "exists") and len(node) >= 3:
      walk(node[2], unit_id, "%s/2" % path, binders + [(head, node[1])],
           side, polarity, in_question)
      return
    if head == "implies" and len(node) == 3:
      walk(node[1], unit_id, "%s/1" % path, binders, "antecedent",
           polarity, in_question)
      walk(node[2], unit_id, "%s/2" % path, binders, "conclusion",
           polarity, in_question)
      return
    if head == "not" and len(node) == 2:
      walk(node[1], unit_id, "%s/1" % path, binders, side,
           "-" if polarity == "+" else "+", in_question)
      return
    if head == "question":
      walk(node[1], unit_id, "%s/1" % path, binders, side, polarity, True)
      return
    if head == "ask" and len(node) == 3:
      walk(node[2], unit_id, "%s/2" % path, binders + [("ask", node[1])],
           side, polarity, True)
      return
    if head == "holds" and len(node) == 3:
      walk(node[2], unit_id, "%s/2" % path, binders, side, polarity,
           in_question)
      return
    if head in LOGICAL_HEADS:
      for i, ch in enumerate(node[1:], start=1):
        walk(ch, unit_id, "%s/%d" % (path, i), binders, side, polarity,
             in_question)
      return
    out.extend(_atom_occurrences(node, unit_id, path, sentence, binders,
                                 side, polarity, in_question))

  for uid, pkg in stage2_packages(stage2):
    walk(pkg, uid, "", [], "none", "+", False)
  return out

def literal_sign(occ):
  """The sign the occurrence was found under, and from nowhere else.

  In particular it is NOT read off `supply` / `contradiction`: those describe
  how a pair could be used in a proof, not what the literal says.
  """
  return "-" if occ.get("polarity") == "-" else "+"
