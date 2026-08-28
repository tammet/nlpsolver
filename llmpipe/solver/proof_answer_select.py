# Answer selection and filtering for the llm-based nlpsolver.
#
# This module decides WHICH prover answer bindings survive: tier ranking
# (concrete > Skolem > population), measure-value preference, the
# relational-vs-classification what-query discriminator, class-name-leak and
# tautological-population filters, and proof deduplication.  Rendering of the
# surviving answers into English lives in proof_answer_format.py.
#
# Used by procproofs.process_proof().
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

import json

from lc_clausify import is_skolem_const, is_skolem_fn


# ======== answer selection and filtering ========

def _answer_all_unbound(ans, askvars):
  """True if every $ans atom in the answer binds only unbound ?:variables in
  its answer positions (the first `askvars` args, or all when askvars is None).

  Such an answer is a leaked, never-instantiated answer variable — it renders
  as a bare name like "X3" — and is never a valid binding.
  """
  val = ans.get("answer")
  if not isinstance(val, list):
    return False
  saw_atom = False
  for atom in val:
    if not (isinstance(atom, list) and len(atom) >= 2 and atom[0] == "$ans"):
      continue
    saw_atom = True
    n = askvars if isinstance(askvars, int) and askvars > 0 else len(atom) - 1
    for arg in atom[1:1 + n]:
      if not (isinstance(arg, str) and arg.startswith("?:")):
        return False  # a real binding exists
  return saw_atom


def _term_contains_list(term):
  """True if a $list (canonical measure value) term appears anywhere in term."""
  if isinstance(term, list):
    if term and term[0] == "$list":
      return True
    return any(_term_contains_list(x) for x in term)
  return False


def _binding_has_measure_value(ans, askvars):
  """True if any $ans atom binds an answer-position argument to a measure
  value ($list term, possibly nested in a $get_world/$ctxt wrapper)."""
  val = ans.get("answer")
  if not isinstance(val, list):
    return False
  for atom in val:
    if not (isinstance(atom, list) and len(atom) >= 2 and atom[0] == "$ans"):
      continue
    n = askvars if isinstance(askvars, int) and askvars > 0 else len(atom) - 1
    for arg in atom[1:1 + n]:
      if _term_contains_list(arg):
        return True
  return False


def _prefer_measure_value_answers(answers, askvars):
  """When the measure_of -> "<noun> of" bridge makes the measure value
  available, a relationally-phrased measure question ("What is the length of
  X?") yields BOTH the definite description (the length of X) and the value
  ($list).  If any answer binds a measure value, keep only the value answers
  so "the length of car A and 80000 meters" collapses to "80000 meters".

  No-op unless some answer carries a $list — measure values only — so
  non-measure queries (and reverse "What is 80km long?" entity answers, which
  produce no $list binding) are unaffected.
  """
  if not any(_binding_has_measure_value(a, askvars) for a in answers):
    return answers
  return [a for a in answers if _binding_has_measure_value(a, askvars)]


def _answer_goodness(ans):
  """Sorting key: high confidence, shorter proof is better."""
  conf     = ans.get("confidence", 0)
  length   = len(ans.get("positive proof", [])) + len(ans.get("negative proof", []))
  blockers = 5 * len(ans.get("blockers", []))
  return conf * 10_000_000 - length - blockers


def _simplify_get_world(atom):
  """Rewrite ["$ans", ["$get_world", ["$ctxt", _, W, _, _]]] -> ["$ans", W].

  Applies the $get_world destructor axiom (axioms_std.js §13.A) eagerly so
  paramodulation-produced wrapping doesn't survive into tier filtering or
  rendering. Atoms whose argument is not a $get_world wrapper, or whose
  $get_world wraps something other than a $ctxt term of length >= 3, are
  returned unchanged.
  """
  if not isinstance(atom, list) or len(atom) < 2 or atom[0] != "$ans":
    return atom
  arg = atom[1]
  if (isinstance(arg, list) and len(arg) >= 2 and arg[0] == "$get_world"):
    ctxt = arg[1]
    if (isinstance(ctxt, list) and len(ctxt) >= 3 and ctxt[0] == "$ctxt"):
      return [atom[0], ctxt[2]]
  return atom


def _ans_object_tier(val, class_names=frozenset()):
  """Return the object-type tier for an answer value.

  Tiers (lower is better / more preferred):
    0 -- CONCRETE: a specific named constant (e.g. "John 1", a URL)
    1 -- SKOLEM:   a Skolem constant ("sk0", "sk1", ...) or Skolem function
                   term (["sk0", X])
    2 -- POPULATION: a class-population constant ("$some_*") or a bare
                   class-name string (e.g. "elephant" appearing as the first
                   argument of some isa(...) literal — demoted so concrete
                   entities beat class labels but class labels survive as a
                   fallback when no concrete entity exists).

  Boolean answers (True/False) always return 0 so they are never filtered out.
  When val is a list of $ans atoms, the tier of the *most concrete* atom wins.
  """
  if val is True or val is False or val is None:
    return 0
  if not isinstance(val, list):
    return 0
  best = 2
  for atom in val:
    if not isinstance(atom, list) or len(atom) < 2:
      continue
    s = atom[1]
    if isinstance(s, list):
      if is_skolem_fn(s):
        tier = 1
      elif s and s[0] == "$get_world":
        # Residual $get_world wrapper (unsimplified — typically a free-var
        # world slot). Demote so a cleaner sibling answer wins.
        tier = 1
      elif s and s[0] in ("$measure_of", "$theof1"):
        # Abstract reference / definite description ("the price of X", "the
        # length of the car") — semantically the entity, not its value.
        # Demote so a concrete $list/$datetime/number sibling — the actual
        # measure value, surfaced by the measure_of->is_rel2 bridge
        # (axioms_std.js) for relationally-phrased measure questions — wins.
        # When such a description is the ONLY answer (e.g. "Mary's sister",
        # where no concrete entity exists), best-tier filtering still keeps it.
        tier = 1
      else:
        # $list (canonical measurement), $datetime, and other complex value
        # terms carry the actual value and stay at the concrete tier.
        tier = 0
    elif isinstance(s, str):
      if s.startswith("$some_"):
        tier = 2
      elif is_skolem_const(s):
        tier = 1
      elif s in class_names:
        tier = 2
      else:
        tier = 0
    else:
      tier = 0
    if tier < best:
      best = tier
    if best == 0:
      break
  return best


def _has_real_concrete_atom(val, class_names=frozenset()):
  """True if val (a list of $ans atoms) contains an atom whose argument is
  a real concrete entity name — a string that is neither a Skolem constant,
  a population ($some_*) constant, nor a bare class label.  Used to
  distinguish "Tallinn" (a real concrete answer that should beat population)
  from ["sk3","Emily 1"] (a Skolem function) and from "elephant" (a class
  label demoted to the population tier)."""
  if not isinstance(val, list):
    return False
  for atom in val:
    if not isinstance(atom, list) or len(atom) < 2:
      continue
    s = atom[1]
    if (isinstance(s, str)
        and not s.startswith("$some_")
        and not is_skolem_const(s)
        and s not in class_names):
      return True
  return False


def _what_query_is_relational(logic):
  """True if the what-query asks for the relatum of a binary `is rel2` relation
  (e.g. is_rel2("afraid of", X, ?Z)) — the answer's KIND is the natural answer
  ("a cat").  False for classification queries (isa of the answer variable,
  "What is an Estonian city?"), where a concrete instance ("Tallinn") is wanted.

  Classifies by the ANSWER VARIABLE's role, looking through a `$defq` wrapper
  (generic-subject queries like "What are cats afraid of?" compile to
  `$defq0(?Z)` defined by `is rel2("afraid of", cat, ?Z)`).  Only the question's
  own clauses are scanned (a `$defq`-referencing clause, or a direct atom
  @question), so a rule-level relation elsewhere (e.g. 1258's "city in Estonia")
  does not leak in.
  """
  if not isinstance(logic, list):
    return False

  def _clause_atoms(lg):
    if not isinstance(lg, list) or not lg:
      return []
    return lg if isinstance(lg[0], list) else [lg]

  def _base(pred):
    return pred[1:] if isinstance(pred, str) and pred.startswith("-") else pred

  # 1. Answer variables + $defq predicate name(s) from the @question.
  ansvars = set()
  defq_names = set()
  direct_atoms = []
  for obj in logic:
    if isinstance(obj, dict) and isinstance(obj.get("@question"), list):
      q = obj["@question"]
      head = q[0]
      if isinstance(head, str) and head.startswith("$defq"):
        defq_names.add(head)
      else:
        direct_atoms.append(q)
      for a in q[1:]:
        if isinstance(a, str) and a.startswith("?:"):
          ansvars.add(a)
  if not ansvars:
    return False

  # 2. Atoms to scan: direct question atoms + clauses that reference the $defq.
  scan = list(direct_atoms)
  if defq_names:
    for obj in logic:
      if not isinstance(obj, dict):
        continue
      atoms = _clause_atoms(obj.get("@logic"))
      if any(_base(a[0]) in defq_names for a in atoms
             if isinstance(a, list) and a):
        scan.extend(a for a in atoms if isinstance(a, list))

  # 3. Classify by the answer variable's role.  (Args may be Skolem-function
  # terms — lists — so guard with isinstance before the set membership test.)
  def _is_ansvar(x):
    return isinstance(x, str) and x in ansvars

  relational = classification = False
  for atom in scan:
    if not (isinstance(atom, list) and atom):
      continue
    base = _base(atom[0])
    if base in ("is rel2", "has degree rel2") and len(atom) >= 4:
      if _is_ansvar(atom[2]) or _is_ansvar(atom[3]):
        relational = True
    elif base == "isa" and len(atom) >= 3:
      if _is_ansvar(atom[2]):
        classification = True
  return relational and not classification


def _filter_by_best_tier(answers, prefer_population=False,
                         population_beats_concrete=False,
                         class_names=frozenset()):
  """Return answers filtered to the best object-type tier.

  Boolean answers are never filtered out.  If all answers are boolean,
  or if no object answers exist, the list is returned unchanged.

  prefer_population: when True ("what" questions), prefer population tier (2)
  over Skolem-function answers — yielding class-level renderings like
  "A wolf" instead of opaque Skolem function output.  Real concrete entity
  names (proper names, URLs) are never overridden by population — Tallinn
  must beat $some_city_in_Estonia for "What is an Estonian city?" (cases
  189, 190).
  """
  tiers = [_ans_object_tier(a.get("answer"), class_names) for a in answers]
  obj_tiers = [t for a, t in zip(answers, tiers)
               if not isinstance(a.get("answer"), bool)]
  if not obj_tiers:
    return answers
  if prefer_population and 2 in obj_tiers and min(obj_tiers) < 2:
    # population_beats_concrete (relational what-query): the class is the answer
    # ("What is X afraid of?" -> "A cat"), so it wins even over a real concrete
    # instance ("Emily").  Otherwise (classification what-query) a real concrete
    # entity (proper name / URL) still wins — "Tallinn" beats "a city in
    # Estonia" for "What is an Estonian city?" (cases 1258/1259).
    has_real_concrete = (not population_beats_concrete) and any(
      not isinstance(a.get("answer"), bool)
      and _has_real_concrete_atom(a.get("answer"), class_names)
      for a in answers
    )
    if not has_real_concrete:
      return [a for a, t in zip(answers, tiers)
              if isinstance(a.get("answer"), bool) or t == 2]
  best = min(obj_tiers)
  if best == 2:
    # All object answers are population constants — keep them all as-is.
    return answers
  return [a for a, t in zip(answers, tiers)
          if isinstance(a.get("answer"), bool) or t == best]


def _extract_class_names(logic):
  """Return the set of strings that appear as the CLASS (first arg) of any
  isa(CLASS, ENTITY) atom in the clause list.  Used to detect class-name
  leaks in wh-answers (cases 241, 242)."""
  class_names = set()
  if not isinstance(logic, list):
    return class_names
  for obj in logic:
    if not isinstance(obj, dict):
      continue
    clause = obj.get("@logic")
    if not isinstance(clause, list) or not clause:
      continue
    # Clause may be a single atom [pred, ...] or a disjunction of atoms.
    atoms = [clause] if isinstance(clause[0], str) else clause
    for atom in atoms:
      if not isinstance(atom, list) or len(atom) < 3:
        continue
      pred = atom[0]
      if isinstance(pred, str) and pred.lstrip("-") == "isa":
        cls = atom[1]
        if isinstance(cls, str) and cls:
          class_names.add(cls)
  return class_names


def _extract_question_pop_keys(logic):
  """Extract a list of (pred, prop_or_class) tuples identifying predicates queried.

  Used by _is_tautological_population_answer to detect circular population proofs.
  Returns a list of tuples (may be empty).

  For direct questions like ["isa", CLASS, ?:var]:
    -> [("isa", CLASS)]

  For $defq-wrapped questions like ["$defq0", ?:X]:
    Scans the biconditional @logic clauses for negative conditions and extracts
    the population-relevant predicates from them.  E.g. the clause
      [["-isa","car","?:X"], ["-has degree property","nice","?:X",...], ["$defq0","?:X"]]
    yields [("isa", "car"), ("has degree property", "nice")].
  """
  _POP_PREDS = {"isa", "has degree property", "has property"}
  if not logic or not isinstance(logic, list):
    return []
  keys = []
  for obj in logic:
    if not isinstance(obj, dict) or "@question" not in obj:
      continue
    q = obj["@question"]
    if not isinstance(q, list) or len(q) < 2:
      continue
    pred = q[0]
    if pred in _POP_PREDS:
      keys.append((pred, str(q[1])))
      return keys
    # $defq question: scan the biconditional clauses for query predicates.
    if pred.startswith("$defq"):
      for obj2 in logic:
        if not isinstance(obj2, dict) or "@logic" not in obj2:
          continue
        clause = obj2["@logic"]
        if not isinstance(clause, list) or not clause:
          continue
        # Look for multi-atom clause containing ["$defqN", ...] as positive literal.
        if not isinstance(clause[0], list):
          continue  # single atom, not the biconditional clause
        has_defq = any(isinstance(a, list) and a and isinstance(a[0], str)
                       and a[0].startswith("$defq") for a in clause)
        if not has_defq:
          continue
        # Extract (pred, arg1) from negative literals in this clause.
        # Skip "isa" — isa population facts are legitimate type witnesses,
        # not circular.  Only property predicates indicate circularity.
        for atom in clause:
          if (isinstance(atom, list) and atom and isinstance(atom[0], str)
              and atom[0].startswith("-") and len(atom) >= 3):
            base_pred = atom[0][1:]
            if base_pred in _POP_PREDS and base_pred != "isa":
              key = (base_pred, str(atom[1]))
              if key not in keys:
                keys.append(key)
      return keys
  return keys


def _is_tautological_population_answer(ans, question_pop_keys, class_names=frozenset()):
  """Return True if ans is a $some_* constant proved directly via the
  population clause that asserts the very property/class being queried,
  or a bare class-label string that matches the queried class/property.

  Three checks:
    1. question_pop_keys non-empty: $some_* constant proved via a single-atom
       population clause [PRED, PROP, answer_const, ...] where PRED/PROP
       match any of the question's population keys.
    2. $some_not_* constant proved via its own negative population clause
       ["-PRED", ..., answer_const, ...] — always circular regardless of
       what the question predicate is.
    3. Bare class-label string answer (e.g. "elephant") that matches the
       second element of any question_pop_keys entry — e.g. "Who is an
       elephant? -> elephant" restates the queried class, so it's a
       tautological wh-leak via part-inheritance / population chains.
  """
  val = ans.get("answer")
  if not isinstance(val, list) or not val:
    return False
  if not isinstance(val[0], list) or len(val[0]) < 2:
    return False
  answer_const = val[0][1]
  # Class-label tautology: bare class string matching the queried class.
  if (isinstance(answer_const, str)
      and answer_const in class_names
      and any(answer_const == qkey[1] for qkey in question_pop_keys)):
    return True
  if not isinstance(answer_const, str) or not answer_const.startswith("$some_"):
    return False

  proof = ans.get("positive proof", [])
  for step in proof:
    if len(step) < 3:
      continue
    justification = step[1]
    clause = step[2]
    if not isinstance(justification, list) or not justification:
      continue
    if justification[0] != "in":
      continue
    # Unwrap single-element list wrapper if present: [[atom]] -> [atom]
    inner_clause = clause
    if (isinstance(clause, list) and len(clause) == 1
        and isinstance(clause[0], list)):
      inner_clause = clause[0]
    if not (isinstance(inner_clause, list) and len(inner_clause) >= 3):
      continue
    # Check 1: matches any question predicate/property.
    if question_pop_keys:
      for qkey in question_pop_keys:
        if (inner_clause[0] == qkey[0]
            and str(inner_clause[1]) == qkey[1]
            and inner_clause[2] == answer_const):
          return True
    # Check 2: $some_not_* proved from its own negative population clause.
    if (answer_const.startswith("$some_not_")
        and isinstance(inner_clause[0], str)
        and inner_clause[0].startswith("-")
        and inner_clause[2] == answer_const):
      return True
  return False


def _defined_property_witnesses(logic, question_pop_keys):
  """Return the set of $some_* population constants whose DEFINING clause
  asserts the very property being queried.

  A "what/who is ADJ?" question populates a witness $some_<adj>_<class> defined
  by a single-atom clause [PRED, PROP, $some_..., ...] with (PRED, PROP) equal
  to a question pop key (e.g. has_degree_property("good", $some_nice_car, ...)
  for "What is nice?").  Such a witness is intrinsically the property witness —
  ANY binding of it to the question is tautological, even when the binding's
  own proof reaches it via a different route ("$some_nice_car is a car, and
  cars are nice").  This is the gap the proof-scan-only
  _is_tautological_population_answer misses (cases 1434 / 1487).

  Only POSITIVE property keys count: the queried-CLASS witness ($some_car via
  isa) is never collected here, because question_pop_keys carries the property
  predicate, not isa.
  """
  if not question_pop_keys or not isinstance(logic, list):
    return frozenset()
  qkeys = {(p, c) for (p, c) in question_pop_keys}
  witnesses = set()
  for obj in logic:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    atom = obj["@logic"]
    # single-atom population clause: [PRED, PROP, const, ...]
    if (not isinstance(atom, list) or len(atom) < 3
        or not isinstance(atom[0], str) or isinstance(atom[1], list)):
      continue
    const = atom[2]
    if not (isinstance(const, str) and const.startswith("$some_")
            and not const.startswith("$some_not_")):
      continue
    if (atom[0], str(atom[1])) in qkeys:
      witnesses.add(const)
  return frozenset(witnesses)


def _filter_tautological_population_answers(answers, logic, class_names=frozenset()):
  """Remove tautological population / class-label answers.

  A tautological answer is one of:
    - A $some_* constant proved solely via the population clause that
      asserts the very property/class being queried ('some big elephant is
      big because some big elephant is big').
    - A $some_* constant whose DEFINING population clause asserts the queried
      property, regardless of which proof route this binding used (the witness
      is intrinsically the property witness; cases 1434 / 1487).
    - A bare class-label string that matches the class being queried
      ('Who is an elephant? -> elephant').
  Such answers are always filtered out, even when no non-tautological
  alternatives exist (producing "Unknown").
  """
  question_pop_keys = _extract_question_pop_keys(logic)
  defined_witnesses = _defined_property_witnesses(logic, question_pop_keys)

  def _is_taut(a):
    if _is_tautological_population_answer(a, question_pop_keys, class_names):
      return True
    val = a.get("answer")
    if (defined_witnesses and isinstance(val, list) and val
        and isinstance(val[0], list) and len(val[0]) >= 2
        and val[0][1] in defined_witnesses):
      return True
    return False

  tautological = [a for a in answers if _is_taut(a)]
  if not tautological:
    return answers
  return [a for a in answers if a not in tautological]


# ======== proof deduplication ========

def _proof_content_sources(ans):
  """Return frozenset of sent_* clause names used as axiom sources in the proof."""
  sources = set()
  for key in ("positive proof", "negative proof"):
    proof = ans.get(key)
    if not isinstance(proof, list):
      continue
    for step in proof:
      reason = step[1] if len(step) > 1 else []
      if (isinstance(reason, list) and len(reason) > 1
          and reason[0] == "in" and isinstance(reason[1], str)
          and reason[1].startswith("sent_")):
        sources.add(reason[1])
  return frozenset(sources)


def _answer_key(ans):
  """Hashable key for grouping answers by conclusion value."""
  val = ans.get("answer")
  return json.dumps(val, sort_keys=True)


def _proof_step_count(ans):
  """Total number of proof steps (positive + negative)."""
  return (len(ans.get("positive proof", []))
        + len(ans.get("negative proof", [])))


def _deduplicate_proofs(answers, threshold=0.15):
  """Remove redundant shadow proofs that differ only in navigation paths.

  Two proofs are in the same group if they have the same answer value
  and the same set of content (sent_*) sources.  Within each group,
  shorter proofs with fewer blockers dominate longer ones when confidence
  is within threshold.
  """
  groups = {}
  for ans in answers:
    key = (_answer_key(ans), _proof_content_sources(ans))
    groups.setdefault(key, []).append(ans)

  result = []
  for key, group in groups.items():
    if len(group) == 1:
      result.append(group[0])
      continue
    # Sort: fewer blockers, fewer steps, higher confidence
    group.sort(key=lambda a: (
      len(a.get("blockers", [])),
      _proof_step_count(a),
      -a.get("confidence", 0)
    ))
    # Keep first (best); discard any dominated by it
    kept = group[0]
    result.append(kept)
    kb = len(kept.get("blockers", []))
    kc = kept.get("confidence", 0)
    ks = _proof_step_count(kept)
    for other in group[1:]:
      ob = len(other.get("blockers", []))
      oc = other.get("confidence", 0)
      os = _proof_step_count(other)
      dominated = (kb <= ob and kc >= oc - threshold and ks <= os)
      if not dominated:
        result.append(other)
  return result
