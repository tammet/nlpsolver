# $ctxt context injection and time-wrapper stripping for the llm-based nlpsolver.
#
# Handles:
#   - Fresh free-variable generation (?:Fv1, ?:Fv2, ...)
#   - @time wrapper stripping and $tense sentinel annotation
#   - $ctxt term injection into eligible predicate atoms
#   - Three-way world dispatch for question atoms (descriptive/stative/dynamic)
#   - Rule vs fact formula detection
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


# Counter for fresh free-variable names (reset per top-level rawlogic_convert call).
_fv_nr = 0

# Predicates that receive a $ctxt term as their last argument during context injection.
CTXT_ELIGIBLE = frozenset({
  "has property", "have", "has part", "can", "is rel2", "event",
  "has degree property", "has degree rel2",
  "has type", "has actor", "has target", "has location",
  "has instrument", "has manner", "has direction", "has time",
  "has destination", "has recipient", "has source",
  "has beneficiary", "has accompaniment", "has path", "has result",
  "has topic", "has cause",
  "typical", "typically",
  "do",
})

# Descriptive predicates in questions: these identify/describe the referent
# and should use free-variable world in $ctxt.
DESC_PREDS = frozenset({
  "isa",
  "do", "event",
  "has type", "has actor", "has target", "has time",
  "has location", "has instrument", "has manner", "has direction",
  "has destination", "has recipient", "has source",
  "has beneficiary", "has accompaniment", "has path", "has result",
  "has topic", "has cause",
  "typical", "typically",
})

# Extended set: also treat property predicates as descriptive when the question
# has a main relational predicate.
DESC_PREDS_WITH_PROPS = DESC_PREDS | frozenset({
  "has property", "has degree property",
})

# Stative predicates: describe persistent states rather than momentary events.
STATIVE_MATRIX_PREDS = frozenset({
  "have", "has part", "can",
})

# Predicates that signal a "main relation" in a question formula.
MAIN_RELATION_PREDS = frozenset({
  "have", "can", "has part", "is rel2", "has degree rel2", "event",
})

# Connective/quantifier ops to recurse through in _strip_time_wrappers.
_TIME_RECURSE_OPS = frozenset({
  "and", "or", "not", "implies", "equivalent", "xor", "normally", "-normally",
  "ask", "question", "holds",
})


def fresh_fv():
  """Return a fresh GK free-variable name, e.g. '?:Fv1', '?:Fv2', …"""
  global _fv_nr
  _fv_nr += 1
  return "?:Fv" + str(_fv_nr)


def is_rule_formula(frm):
  """Return True if frm contains 'forall' or 'normally' at any nesting level."""
  if not isinstance(frm, list) or not frm:
    return False
  if frm[0] in ("forall", "normally"):
    return True
  return any(is_rule_formula(el) for el in frm[1:])


def strip_time_wrappers(frm, current_tense):
  """Strip @time wrappers and annotate leaf predicates with $tense sentinels.

  Recursively walks the formula tree:
    - ["@time", T, body] -> recurse into body with current_tense = T
    - Connectives/quantifiers -> recurse into children passing current_tense
    - Leaf atom with base predicate in CTXT_ELIGIBLE -> append ["$tense", current_tense]
    - Everything else -> return unchanged
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if not isinstance(op, str):
    return frm

  if op == "@time" and len(frm) == 3:
    tense_val = frm[1]
    body = frm[2]
    return strip_time_wrappers(body, tense_val)

  if op in ("forall", "exists") and len(frm) == 3:
    return [op, frm[1], strip_time_wrappers(frm[2], current_tense)]

  if op in _TIME_RECURSE_OPS:
    return [op] + [strip_time_wrappers(child, current_tense) for child in frm[1:]]

  base = op[1:] if op.startswith("-") else op
  if base in CTXT_ELIGIBLE and current_tense is not None:
    return list(frm) + [["$tense", current_tense]]

  return frm


# ======== question-specific past->present bridge axioms ========

# Stative predicates that get same-world past->present bridges, with confidence.
STATIVE_BRIDGE_CONFIDENCE = {
  "have":                0.97,
  "has part":            0.99,
  "can":                 0.99,
  "has property":        0.99,
  "has degree property": 0.99,
  "is rel2":             0.95,
  "has degree rel2":     0.95,
}


def _arg_signature(arg):
  """Return a hashable signature for an entity argument.
  Free variables collapse to a single token "?" so different fresh
  variables produce the same bridge. Function terms (lists) reject."""
  if isinstance(arg, str):
    if arg.startswith("?:"):
      return ("?",)
    return ("c", arg)
  if isinstance(arg, (int, float, bool)):
    return ("c", arg)
  if isinstance(arg, list):
    return None  # function term — reject
  return ("c", arg)


def _collect_stative_signatures(atom, sigs):
  """Walk an atom; collect signatures for stative literals appearing as
  NEGATIVE literals (body->defq direction) with ground tense in $ctxt.
  Each signature is (pred, tuple of arg signatures, tense_in_question)
  where tense_in_question is "present" or "past" — the bridge will go
  the opposite direction (from the assertion's tense to the question's).

  Recurses into 'or' and '$block' bodies."""
  if not isinstance(atom, list) or not atom:
    return
  pred = atom[0]
  if not isinstance(pred, str):
    return

  if pred == "or":
    for sub in atom[1:]:
      _collect_stative_signatures(sub, sigs)
    return

  if pred == "$block" and len(atom) >= 3:
    # Skip $block bodies — those are not question body literals.
    return

  # Only consider NEGATIVE literals: body->defq direction needs them satisfied.
  if not pred.startswith("-"):
    return
  base = pred[1:]
  if base not in STATIVE_BRIDGE_CONFIDENCE:
    return

  # Last argument must be ["$ctxt", "present"|"past", ...]
  if len(atom) < 2:
    return
  ctxt = atom[-1]
  if not (isinstance(ctxt, list) and len(ctxt) >= 2 and ctxt[0] == "$ctxt"):
    return
  tense = ctxt[1]
  if tense not in ("present", "past"):
    return

  ent_args = atom[1:-1]
  arg_sigs = []
  for a in ent_args:
    s = _arg_signature(a)
    if s is None:
      return  # function term — skip whole literal
    arg_sigs.append(s)

  sigs.add((base, tuple(arg_sigs), tense))


def _collect_question_goal_signatures(frm, sigs):
  """Walk a direct ["@question", FORMULA] goal and collect signatures for
  POSITIVE stative literals (the goal `have(X, present)` becomes the negative
  `-have(X, present)` once the prover negates it for refutation, so it needs
  the same past->present bridge a $defq-wrapped question gets via its negative
  body literal).  Recurses into and/or; a $defq reference (guarded question)
  is not stative and is skipped — its bridge comes from the @logic clauses.
  """
  if not isinstance(frm, list) or not frm:
    return
  pred = frm[0]
  if not isinstance(pred, str):
    return
  if pred in ("and", "or"):
    for sub in frm[1:]:
      _collect_question_goal_signatures(sub, sigs)
    return
  if pred.startswith("-"):
    return
  if pred not in STATIVE_BRIDGE_CONFIDENCE:
    return
  ctxt = frm[-1]
  if not (isinstance(ctxt, list) and len(ctxt) >= 2 and ctxt[0] == "$ctxt"):
    return
  tense = ctxt[1]
  if tense not in ("present", "past"):
    return
  arg_sigs = []
  for a in frm[1:-1]:
    s = _arg_signature(a)
    if s is None:
      return
    arg_sigs.append(s)
  sigs.add((pred, tuple(arg_sigs), tense))


def build_question_tense_bridges(question_objs, name):
  """For each unique (predicate, ground-args) combination appearing as a
  present-tense stative literal in the question clauses, emit a specialized
  past->present bridge axiom with $block.

  Covers both question shapes: a $defq-wrapped question exposes the stative
  goal as a NEGATIVE literal in its `@logic` biconditional clauses, while a
  direct question carries it as a POSITIVE literal under `@question`.  Both
  must get the bridge, otherwise an unguarded stative question (e.g. "who
  does the backpack belong to?" -> direct @question have(X, present)) misses
  the past->present persistence a guarded one receives.

  Returns a list of clause dicts (may be empty).
  """
  sigs = set()
  for obj in question_objs:
    if not isinstance(obj, dict):
      continue
    clause = obj.get("@logic")
    if clause is not None and isinstance(clause, list) and clause:
      if isinstance(clause[0], list):
        for atom in clause:
          _collect_stative_signatures(atom, sigs)
      else:
        _collect_stative_signatures(clause, sigs)
    q = obj.get("@question")
    if q is not None:
      _collect_question_goal_signatures(q, sigs)

  bridges = []
  fv_counter = [0]
  def _fv():
    fv_counter[0] += 1
    return "?:Br" + str(fv_counter[0])

  for base, arg_sigs, q_tense in sigs:
    conf = STATIVE_BRIDGE_CONFIDENCE[base]
    # Materialize args: constants stay, placeholders become fresh variables.
    args_list = []
    for s in arg_sigs:
      if s == ("?",):
        args_list.append(_fv())
      else:
        args_list.append(s[1])
    # Bridge goes from the OPPOSITE tense (assertion side) to the question side.
    asn_tense = "past" if q_tense == "present" else "present"
    head_neg = ["-" + base] + args_list + [["$ctxt", asn_tense, "?:W", "?:L", "?:K"]]
    head_pos = [base] + args_list + [["$ctxt", q_tense, "?:W", "?:L", "?:K"]]
    block_lit = ["$block", 0, ["$not", [base] + args_list +
                  [["$ctxt", q_tense, "?:W", "?:L", "?:K"]]]]
    clause = [head_neg, head_pos, block_lit]
    bridges.append({
      "@name": name,
      "@sourcetype": "question_bridge",
      "@confidence": conf,
      "@logic": clause,
    })
  return bridges


def _inject_const_ctxt_atom(atom):
  """Append "$c" as the last argument of an eligible GK atom.

  Used when nocontext_flag is set: provides a constant context argument
  so axioms with "?:Ctxt" still unify, while axioms with explicit
  $ctxt(...) terms (frame axioms, tense bridges) do not.
  Strips any $tense sentinel left by time-wrapper processing.
  """
  if not isinstance(atom, list) or not atom:
    return atom
  pred = atom[0]
  if not isinstance(pred, str):
    return atom
  base = pred[1:] if pred.startswith("-") else pred

  if base == "or":
    return ["or"] + [_inject_const_ctxt_atom(sub) for sub in atom[1:]]

  if base == "$block" and len(atom) >= 3:
    body = atom[2]
    if isinstance(body, list) and len(body) >= 2 and body[0] == "$not":
      inner = _inject_const_ctxt_atom(body[1])
      return [atom[0], atom[1], ["$not", inner]]
    inner = _inject_const_ctxt_atom(body)
    return [atom[0], atom[1], inner]

  if base in CTXT_ELIGIBLE:
    args = list(atom)
    # Strip $tense sentinel if present
    if (len(args) >= 2 and isinstance(args[-1], list)
        and len(args[-1]) == 2 and args[-1][0] == "$tense"):
      args = args[:-1]
    return args + ["$c"]

  return atom


def inject_const_ctxt_into_objs(objs):
  """Inject "$c" constant context into clause dicts (in place).

  Parallel to inject_ctxt_into_objs but for nocontext mode.
  """
  for obj in objs:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      clause = obj["@logic"]
      if isinstance(clause, list) and clause:
        if isinstance(clause[0], list):
          obj["@logic"] = [_inject_const_ctxt_atom(atom) for atom in clause]
        else:
          obj["@logic"] = _inject_const_ctxt_atom(clause)
    if "@question" in obj:
      obj["@question"] = _inject_const_ctxt_atom(obj["@question"])


def inject_ctxt_atom(atom, ctxt_template, default_tense):
  """Append a $ctxt term as the last argument of an eligible GK atom.

  Uses per-predicate tense from $tense sentinel if present, otherwise
  uses default_tense.  ctxt_template is ["$ctxt", None, situation, loc, kn]
  with tense slot as placeholder.
  """
  if not isinstance(atom, list) or not atom:
    return atom
  pred = atom[0]
  if not isinstance(pred, str):
    return atom
  base = pred[1:] if pred.startswith("-") else pred

  if base == "or":
    return ["or"] + [inject_ctxt_atom(sub, ctxt_template, default_tense) for sub in atom[1:]]

  if base == "$block" and len(atom) >= 3:
    body = atom[2]
    if isinstance(body, list) and len(body) >= 2 and body[0] == "$not":
      inner = inject_ctxt_atom(body[1], ctxt_template, default_tense)
      return [atom[0], atom[1], ["$not", inner]]
    inner = inject_ctxt_atom(body, ctxt_template, default_tense)
    return [atom[0], atom[1], inner]

  if base in CTXT_ELIGIBLE:
    args = list(atom)
    tense = default_tense
    if (len(args) >= 2 and isinstance(args[-1], list)
        and len(args[-1]) == 2 and args[-1][0] == "$tense"):
      tense = args[-1][1]
      args = args[:-1]
    ctxt = [ctxt_template[0], tense, ctxt_template[2], ctxt_template[3], ctxt_template[4]]
    return args + [ctxt]

  return atom


def inject_ctxt_into_objs(objs, ctxt_template, default_tense):
  """Inject ctxt into @logic and @question entries of clause dicts (in place)."""
  for obj in objs:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      clause = obj["@logic"]
      if isinstance(clause, list) and clause:
        if isinstance(clause[0], list):
          obj["@logic"] = [inject_ctxt_atom(atom, ctxt_template, default_tense) for atom in clause]
        else:
          obj["@logic"] = inject_ctxt_atom(clause, ctxt_template, default_tense)
    if "@question" in obj:
      obj["@question"] = inject_ctxt_atom(obj["@question"], ctxt_template, default_tense)


def is_desc_pred(atom, desc_set):
  """True if atom's predicate is in the given descriptive set."""
  if not isinstance(atom, list) or not atom:
    return False
  pred = atom[0]
  if not isinstance(pred, str):
    return False
  base = pred[1:] if pred.startswith("-") else pred
  return base in desc_set


def is_stative_matrix(atom):
  """True if atom's predicate is a stative matrix predicate (have, can, has part)."""
  if not isinstance(atom, list) or not atom:
    return False
  pred = atom[0]
  if not isinstance(pred, str):
    return False
  base = pred[1:] if pred.startswith("-") else pred
  return base in STATIVE_MATRIX_PREDS


def inject_ctxt_question(objs, ctxt_matrix, ctxt_desc, default_tense,
                         props_are_desc=False):
  """Inject $ctxt into question clause dicts with three-way world dispatch.

  Three categories of atoms in $defq questions:
    1. Descriptive (isa, event atoms, properties when main relation present):
       each gets its own independent fresh free-var world.
    2. Stative matrix (have, can, has part): free-var world.
    3. Dynamic matrix (is_rel2, has_degree_rel2, or properties when no main
       relation): keep the query's concrete world.

  @question entries always get ctxt_matrix.
  """
  desc_set = DESC_PREDS_WITH_PROPS if props_are_desc else DESC_PREDS
  def _pick_tmpl_and_tense(atom):
    if is_desc_pred(atom, desc_set):
      tmpl = ["$ctxt", None, fresh_fv(), ctxt_desc[3], ctxt_desc[4]]
      return tmpl, fresh_fv()
    if is_stative_matrix(atom):
      tmpl = ["$ctxt", None, fresh_fv(), ctxt_desc[3], ctxt_desc[4]]
      return tmpl, default_tense
    return ctxt_matrix, default_tense
  for obj in objs:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      clause = obj["@logic"]
      if isinstance(clause, list) and clause:
        if isinstance(clause[0], list):
          obj["@logic"] = [
            inject_ctxt_atom(atom, *_pick_tmpl_and_tense(atom))
            for atom in clause
          ]
        else:
          tmpl, tense = _pick_tmpl_and_tense(clause)
          obj["@logic"] = inject_ctxt_atom(clause, tmpl, tense)
    if "@question" in obj:
      obj["@question"] = inject_ctxt_atom(obj["@question"], ctxt_matrix, default_tense)
