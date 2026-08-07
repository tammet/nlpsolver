# Per-ASU-package processing for the llm-based nlpsolver.
#
# Each function in this module operates on (or contributes to processing
# of) a single Stage-2 ["@id", SID, PACKAGE] block.  The high-level
# orchestrator in logconvert.py calls convert_id_package on each block
# and concatenates the resulting clause lists.
#
# Structure:
#   _question_has_main_relation, _fix_missing_ask, _detect_who_query,
#   _process_question, _process_assertion, _distribute_clause_confidence,
#   _clause_has_block, _clause_has_skolem, _has_explicit_negation_at_top,
#   convert_id_package, extract_package_ctx
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

from globals import options as _g_options

import lc_clausify
import lc_questions

from lc_clausify import clausify, is_skolem_const, is_skolem_fn

from lc_questions import (
  simplify_contradictory_and,
  is_simple_question_formula,
  collect_body_free_vars,
  find_haslocation_prep,
  find_hastime_prep,
  build_defq_question,
  find_where_atom,
  find_when_atom,
  build_where_question,
  build_when_question,
  build_who_question,
  flatten_q_atoms,
  hoist_generic_yn_subject,
  scan_item_formula,
  build_population_facts,
  is_ground_term,
  S2_VAR_RE,
  WHERE_SPATIAL_PREPS,
  WHEN_TEMPORAL_PREPS,
)

import lc_ctxt
from lc_ctxt import (
  fresh_fv as _fresh_fv,
  is_rule_formula as _is_rule_formula,
  strip_time_wrappers as _strip_time_wrappers,
  inject_ctxt_atom as _inject_ctxt_atom,
  inject_ctxt_into_objs as _inject_ctxt_into_objs,
  inject_ctxt_question as _inject_ctxt_question,
  inject_const_ctxt_into_objs as _inject_const_ctxt_into_objs,
  build_question_tense_bridges as _build_question_tense_bridges,
  MAIN_RELATION_PREDS as _MAIN_RELATION_PREDS,
)

from lc_rewrites import (
  hoist_misnested_exists as _hoist_misnested_exists,
  strip_spurious_can as _strip_spurious_can,
  negate_consequent as _negate_consequent,
  inject_query_specific_noun_isas as _inject_query_specific_noun_isas,
)


# ======== raw text wh-word probes ========
# Used by both convert_id_package (in this module) and logconvert._has_what_query.

def raw_has_what_word(text):
  """True if `text` contains 'what' or 'which' as a whole word anywhere.
  Covers both front-position queries ('What does John smoke?') and
  back-position queries ('John smokes what?')."""
  if not text or not isinstance(text, str):
    return False
  import re as _re
  return bool(_re.search(r'\b(what|which)\b', text.lower()))


def _raw_has_who_word(text):
  """True if `text` contains 'who' or 'whom' as a whole word anywhere."""
  if not text or not isinstance(text, str):
    return False
  import re as _re
  return bool(_re.search(r'\b(who|whom)\b', text.lower()))


  # ASU-derived clauses.  It is stripped in clause_list_to_json_commented
  # before serialization for the prover.

  return result


# ======== package extraction ========


def _question_has_main_relation(formula):
  """Return True if the question formula contains a main relational predicate.

  Scans top-level conjuncts (not inside exists) for have, can, is_rel2, etc.
  When True, property predicates (has_property, has_degree_property) in the
  question are restrictive modifiers (descriptive), not the matrix predication.
  """
  # Unwrap question/ask wrappers to get the body.
  body = formula
  if isinstance(body, list) and body:
    if body[0] == "question" and len(body) >= 2:
      body = body[1]
    elif body[0] == "ask" and len(body) >= 3:
      body = body[2]
  if not isinstance(body, list) or not body:
    return False
  # Collect top-level conjuncts.
  if body[0] == "and":
    conjuncts = body[1:]
  else:
    conjuncts = [body]
  for c in conjuncts:
    if not isinstance(c, list) or not c or not isinstance(c[0], str):
      continue
    pred = c[0]
    base = pred[1:] if pred.startswith("-") else pred
    # Direct main relation predicate (have, can, is_rel2, etc.)
    if base in _MAIN_RELATION_PREDS:
      return True
    # Event-based predication: an exists block indicates a reified event
    # (e.g. "bought", "ate") which is a main predication, not just a modifier.
    if base == "exists" and len(c) >= 3:
      return True
  return False


def _fix_missing_ask(formula, asu_index, sid):
  """Wrap formula as ["ask", VAR, BODY] when Stage-1 has wh_placeholder.

  Some LLMs produce ["question", BODY] instead of ["ask", VAR, BODY] for
  wh-questions.  After extract_package_ctx, ["question", BODY] becomes just
  BODY (unwrapped), while ["ask", VAR, BODY] stays as-is.  So we detect the
  missing "ask" by checking: is_question is True, formula doesn't start with
  "ask", and Stage-1 has wh_placeholder.  Then find the free variable and wrap.
  """
  if not isinstance(formula, list) or not formula:
    return formula
  # Already correct: ["ask", VAR, BODY] survived extraction.
  if formula[0] == "ask":
    return formula
  # Check Stage-1 for wh_placeholder.
  if not asu_index:
    return formula
  asu = asu_index.get(sid)
  if asu is None:
    return formula
  has_wh = False
  for ent in asu.get("entities", []):
    if isinstance(ent, dict) and ent.get("wh_placeholder"):
      has_wh = True
      break
  if not has_wh:
    return formula
  # Find free variables in the question body.
  free_vars = sorted(collect_body_free_vars(formula))
  if len(free_vars) == 1:
    return ["ask", free_vars[0], formula]
  return formula


def _detect_who_query(body, ask_var):
  """Detect 'Who is X?' / 'What is X?' pattern and return the entity constant.

  Matches:
    ["=", ask_var, ENTITY] or ["=", ENTITY, ask_var]
    ["isa", ask_var, ENTITY] or ["isa", ENTITY, ask_var]
    ["is rel2", "is", ENTITY, ask_var]
  where ENTITY is a ground constant (not a stage-2 variable).
  Also recurses into top-level ["and", ...] bodies so compound forms like
  `["and", ["isa","person","John 1"], ["=","X","John 1"]]` still return
  the identity entity "John 1".
  Returns the entity string, or None if not matched.
  """
  if not isinstance(body, list) or len(body) < 3:
    return None
  op = body[0]
  if op == "=" and len(body) == 3:
    a, b = body[1], body[2]
    if a == ask_var and isinstance(b, str) and not S2_VAR_RE.match(b):
      return b
    if b == ask_var and isinstance(a, str) and not S2_VAR_RE.match(a):
      return a
  # ["isa", ask_var, ENTITY] — ask_var in type position: "What type is ENTITY?"
  # Do NOT match ["isa", TYPE, ask_var] — that's "Which X is a TYPE?" (standard wh)
  if op == "isa" and len(body) == 3:
    if body[1] == ask_var and isinstance(body[2], str) and not S2_VAR_RE.match(body[2]):
      return body[2]
  # ["is rel2", "is", ENTITY, ask_var] or ["is rel2", "is", ask_var, ENTITY]
  if op == "is rel2" and len(body) >= 4 and body[1] == "is":
    a, b = body[2], body[3]
    if b == ask_var and isinstance(a, str) and not S2_VAR_RE.match(a):
      return a
    if a == ask_var and isinstance(b, str) and not S2_VAR_RE.match(b):
      return b
  # Compound conjunction: look inside each conjunct for an identity atom.
  if op == "and":
    for conj in body[1:]:
      found = _detect_who_query(conj, ask_var)
      if found is not None:
        return found
  return None


def _process_question(formula, name, raw_text=None, generic_classes=None):
  """Handle question formulas (ask / yes-no) → (result_list, question_kind).

  generic_classes -- (plan fix 4) classes some premise quantifies over
  generically; gates the bare-plural-generic hoist.

  question_kind is None, "where", or "when".
  Returns (None, None) when the formula produces no output (caller should return []).
  """
  question_kind = None
  # Distinguish wh-questions (["ask", var, body]) from yes/no questions.
  if isinstance(formula, list) and len(formula) >= 3 and formula[0] == "ask":
    ask_var = str(formula[1])
    body    = formula[2]
    # "Where is X?" pattern: body contains ["is rel2", <meta-pred>, entity, ask_var]
    result = None
    where_atom = find_where_atom(body, ask_var)
    if where_atom is not None:
      entity = where_atom[2]
      atom_pred = where_atom[1]
      # Use specific prep when query uses a non-default spatial preposition
      # (near, above, under); use all preps for "in"/"on"/"at" and meta-predicates
      # since these are generic location queries.
      _GENERIC_SPATIAL = frozenset({"in", "on", "at"})
      specific_prep = atom_pred if (atom_pred in WHERE_SPATIAL_PREPS
                                    and atom_pred not in _GENERIC_SPATIAL) else None
      # When the entity is a stage-2 variable (e.g. "Y" for "a car"),
      # build_where_question would generate an over-broad biconditional
      # matching ANY entity's location.  Instead, use build_defq_question
      # which preserves all constraints from the original body (e.g. isa(car,Y)).
      # For meta-predicates with variable entity, fall through to the general
      # defq path below (meta-preds like "located in" don't exist in facts).
      entity_is_s2var = isinstance(entity, str) and bool(S2_VAR_RE.match(entity))
      if entity_is_s2var:
        # Variable entity + spatial preposition (in/on/at/near/above/under):
        # build a defq question tagged @where_query.  This includes the
        # generic preps in/on/at — without this branch they would leave
        # result=None and fall through to the when-branch, which matches the
        # same is_rel2 atom (in/on/at are also temporal preps) and would
        # mislabel a spatial query as @when_query.
        # Variable entity + meta-predicate ("located in", ...): NOT in
        # WHERE_SPATIAL_PREPS, so fall through to the general defq path
        # (the when-branch will not match a where meta-predicate).
        if atom_pred in WHERE_SPATIAL_PREPS:
          result = build_defq_question(name, ask_var, body,
                                       wh_prep=atom_pred, wh_marker="@where_query")
          question_kind = "where"
      else:
        result = build_where_question(name, entity, ask_var, specific_prep=specific_prep)
        question_kind = "where"
    if result is None:
      # "When is X?" pattern: body contains ["is rel2", <temporal-pred>, entity, ask_var]
      when_atom = find_when_atom(body, ask_var)
      if when_atom is not None:
        entity = when_atom[2]
        atom_pred = when_atom[1]
        specific_prep = atom_pred if atom_pred in WHEN_TEMPORAL_PREPS else None
        entity_is_s2var = isinstance(entity, str) and bool(S2_VAR_RE.match(entity))
        if entity_is_s2var:
          wp = specific_prep if specific_prep else "in"
          result = build_defq_question(name, ask_var, body,
                                       wh_prep=wp, wh_marker="@when_query")
        else:
          result = build_when_question(name, entity, ask_var, specific_prep=specific_prep)
        question_kind = "when"
      else:
        # "Who is X?" / "What is X?" pattern: body is [=, var, entity] or [isa, ...]
        who_entity = _detect_who_query(body, ask_var)
        if who_entity is not None:
          # Determine who vs what from raw question text
          who_kind = "what" if raw_has_what_word(raw_text) else "who"
          result = build_who_question(name, who_entity, ask_var, who_kind=who_kind)
          question_kind = "who"
        elif is_simple_question_formula(body):
          # Single atom with ≤1 variable: direct @question, no $defq wrapper.
          free_vars_in_body = sorted(collect_body_free_vars(body))
          varmap = {ask_var: "?:" + ask_var}
          varmap.update({v: "?:" + v for v in free_vars_in_body})
          flat = flatten_q_atoms(body, varmap)
          if not flat:
            return None, None
          q_formula = flat[0] if len(flat) == 1 else [["and"] + flat]
          result = [{"@name": name, "@question": q_formula, "@askvars": 1}]
          if raw_has_what_word(raw_text):
            for obj in result:
              if "@question" in obj:
                obj["@what_query"] = True
        else:
          # Complex case: wrap in $defq biconditional.
          # Detect has_location(E, ask_var) → encode "in" as the preposition.
          where_prep = find_haslocation_prep(body, ask_var)
          if where_prep:
            result = build_defq_question(name, ask_var, body, where_prep=where_prep,
                                         wh_prep_pred="has location")
            question_kind = "where"
          else:
            # Detect has_time(E, ask_var) → encode "in" as the temporal preposition.
            when_prep = find_hastime_prep(body, ask_var)
            if when_prep:
              result = build_defq_question(name, ask_var, body,
                                           wh_prep=when_prep, wh_marker="@when_query",
                                           wh_prep_pred="has time")
              question_kind = "when"
            else:
              result = build_defq_question(name, ask_var, body)
              if raw_has_what_word(raw_text):
                for obj in result:
                  if "@question" in obj:
                    obj["@what_query"] = True
              elif _raw_has_who_word(raw_text):
                # Complex "who"-question (e.g. "Who does not have wings?").
                # _detect_who_query only matches simple identity patterns;
                # for complex bodies we still want @who_query so answer
                # formatting goes through _format_who_answers (strips the
                # numeric confidence suffix, applies qualitative labels).
                for obj in result:
                  if "@question" in obj:
                    obj["@who_query"] = True
  else:
    # Yes/no question.
    # Bare-plural-generic rewrite (Stage-2 prompt §7.4(a)): if the formula
    # matches  forall X, isa(C,X) → normally(BODY)  hoist isa(C, skq) as a
    # fact and replace the question body with BODY[X ← skq] — this produces
    # the named-Skolem encoding (UDP-shaped) where the defeasible rule fires
    # on the fresh skq, avoiding the John-shortcut bug of the existential
    # form and the strict-collapse bug of the universal form.
    extra_facts = []
    skq, hoisted, rewritten = hoist_generic_yn_subject(
      formula, name, asu_text=raw_text, generic_classes=generic_classes)
    # rewritten is always the formula to use: the skq-substituted body when the
    # hoist fired, the existential rewrite when the guard refused it, and the
    # untouched formula when the pattern did not match at all.
    formula = rewritten
    if skq is not None:
      hoisted_conjuncts = (hoisted[1:] if (isinstance(hoisted, list)
                                           and hoisted and hoisted[0] == "and")
                           else [hoisted])
      for atom in hoisted_conjuncts:
        extra_facts.append({"@name": name,
                            "@sourcetype": "question_subject",
                            "@logic": atom})

    # When $ctxt is active, always use $defq so the @question atom is the
    # machinery literal ["$defq0"] (no free variables → GK returns plain
    # `true` rather than `$ans(W0,…)` which confuses answer extraction).
    if is_simple_question_formula(formula) and _g_options.get("nocontext_flag", False):
      # Direct @question only when $ctxt is disabled.
      free_vars_in_formula = sorted(collect_body_free_vars(formula))
      varmap = {v: "?:" + v for v in free_vars_in_formula}
      flat = flatten_q_atoms(formula, varmap)
      if not flat:
        return None, None
      q_formula = flat[0] if len(flat) == 1 else [["and"] + flat]
      result = [{"@name": name, "@question": q_formula}]
    else:
      # Complex formula, or: simple but $ctxt active → $defq biconditional.
      # Fix contradictory ["and", ["not", A], A] that LLM generates for
      # "No X is Y?" questions — simplify to just ["not", A].
      formula = simplify_contradictory_and(formula)
      result = build_defq_question(name, None, formula)
    if extra_facts:
      result = extra_facts + result
  return result, question_kind


def _process_assertion(formula, name, confidence):
  """Handle assertion formulas → list of GK clause dicts.

  Confidence distribution.  Stage-1 probability p is transformed to an
  evidence value e = 2p - 1 (with polarity flip for p < 0.5) before being
  distributed across clauses.  The distribution picks an anchor set via
  priority:

    1. Clauses carrying a $block atom (defeasibility anchors) → each gets
       e^(1/k); non-$block clauses stay at 1.0.
    2. Else, clauses referencing a Skolem constant/function (the event's
       structural spine) → each gets e^(1/k); non-Skolem clauses at 1.0.
    3. Else (pure class/relation assertion, no events) → every clause gets
       e^(1/k).

  The chain product over the anchor set equals e exactly, so the prover's
  chain multiplication reports the intended confidence rather than
  decaying by e per clause.  See DOCUMENTATION.md §7.8 companion notes.
  """
  # Safety net for LLMs that double-encode negation.  Some LLMs render
  # "It is false that X" as BOTH an explicit `["not", F]` in the formula
  # AND an @p=0.0 on the package.  The two encodings are redundant; the
  # existing @p<0.5 branch would call _negate_consequent on the already-
  # negated formula and flip polarity back to positive (case 234).
  # Resolution: drop @p (treat as full-confidence); the formula's own
  # `not` carries the negation.  Narrow to @p==0.0 exactly — a genuine
  # "probably not X" can legitimately pair `not F` with @p<0.5.
  if confidence == 0.0 and _has_explicit_negation_at_top(formula):
    confidence = None
  # Pre-clausification polarity flip for low-confidence negative-leaning rules.
  # Stage-1 probability p ∈ [0, 0.5) → negate the consequent BEFORE clausify
  # so the negation is encoded in the formula structure (avoids Skolem companion
  # clause split that the post-clausification approach suffered from).  p=0
  # is included: "John is an elephant with probability 0" should become a
  # full-confidence negated assertion (evidence = 1 - 2*0 = 1).
  if confidence is not None and 0 <= confidence < 0.5:
    formula = _negate_consequent(formula)
    confidence = round(1.0 - 2.0 * confidence, 4)
  elif confidence is not None and 0.5 < confidence < 1.0:
    confidence = round(2.0 * confidence - 1.0, 4)
  elif confidence == 0.5:
    confidence = 0   # exactly 0.5 → abs(2*0.5-1)=0; prover filters it out → "no information"
  # Clausify the formula.
  clauses = clausify(formula)
  return _distribute_clause_confidence(clauses, confidence, name)


def _distribute_clause_confidence(clauses, e, name):
  """Build the clause-dict list from clausify() output, applying the
  three-tier confidence distribution described in _process_assertion.

  e==None → no confidence annotation (prover default = full confidence).
  e==0.0  → all clauses dropped (prover rejects @confidence 0).
  e==1.0  → no annotation (prover default).
  else    → case 1/2/3 selection as described.
  """
  if e == 0.0:
    return []                       # 0.5 probability → no evidence either way
  # No confidence or full confidence: emit unannotated clauses.
  if e is None or e == 1.0:
    return [{"@name": name, "@logic": c} for c in clauses]
  if not clauses:
    return []

  # Case 1: $block-carrying clauses are the defeasibility anchors.
  anchor_idx = [i for i, c in enumerate(clauses) if _clause_has_block(c)]
  # Case 2: else, clauses referencing a Skolem (event spine).
  if not anchor_idx:
    anchor_idx = [i for i, c in enumerate(clauses) if _clause_has_skolem(c)]
  # Case 3: else, every clause is part of the claim.
  if not anchor_idx:
    anchor_idx = list(range(len(clauses)))

  k = len(anchor_idx)
  # Each anchor clause gets e^(1/k); product over the anchor set = e.
  per_clause = round(e ** (1.0 / k), 4) if k > 1 else e
  anchor_set = set(anchor_idx)

  result = []
  for i, clause in enumerate(clauses):
    obj = {"@name": name, "@logic": clause}
    if i in anchor_set:
      obj["@confidence"] = per_clause
    # Non-anchor clauses carry no @confidence → prover treats as 1.0.
    result.append(obj)
  return result


def _clause_has_block(clause):
  """True if the clause contains any atom with '$block' at position 0."""
  if not isinstance(clause, list) or not clause:
    return False
  # Single-atom clause.
  if isinstance(clause[0], str):
    return clause[0] == "$block"
  # Disjunctive clause (list of atoms).
  for atom in clause:
    if isinstance(atom, list) and atom and atom[0] == "$block":
      return True
  return False


def _clause_has_skolem(clause):
  """True if any argument anywhere in the clause references a Skolem
  constant (like 'sk0_house') or Skolem function term (like ['sk0', '?:X']).
  Uses is_skolem_const / is_skolem_fn from lc_clausify."""
  def walk(term):
    if isinstance(term, str):
      return is_skolem_const(term)
    if isinstance(term, list) and term:
      if is_skolem_fn(term):
        return True
      for sub in term[1:]:                 # skip op/predicate name
        if walk(sub):
          return True
    return False
  if not isinstance(clause, list) or not clause:
    return False
  # Single-atom clause.
  if isinstance(clause[0], str):
    for arg in clause[1:]:
      if walk(arg):
        return True
    return False
  # Disjunctive clause.
  for atom in clause:
    if isinstance(atom, list) and atom:
      if isinstance(atom[0], str):
        for arg in atom[1:]:
          if walk(arg):
            return True
      elif walk(atom):
        return True
  return False


def _has_explicit_negation_at_top(formula):
  """True if formula has ['not', F] at a position representing the
  assertion's main claim: root, direct 'and' conjunct, 'implies'
  consequent, or 'forall/exists' body root.  Used by the double-
  encoding safety net in _process_assertion (case 234)."""
  if not isinstance(formula, list) or not formula:
    return False
  op = formula[0]
  if op == "not":
    return True
  if op == "and":
    return any(
      isinstance(c, list) and len(c) >= 1 and c[0] == "not"
      for c in formula[1:]
    )
  if op == "implies" and len(formula) >= 3:
    cons = formula[2]
    return isinstance(cons, list) and len(cons) >= 1 and cons[0] == "not"
  if op in ("forall", "exists") and len(formula) >= 3:
    return _has_explicit_negation_at_top(formula[2])
  return False


def convert_id_package(item, asu_index=None, uid_suffix=None, set_el_by_sid=None,
                       generic_classes=None):
  """Process ["@id", sid, PACKAGE] → list of GK clause dicts.

  generic_classes -- (plan fix 4) classes some premise quantifies over
  generically; gates the bare-plural-generic question hoist.
  """
  if not isinstance(item, list) or len(item) < 3 or item[0] != "@id":
    return []
  sid = item[1]
  package = item[2]
  name = "sent_" + str(sid)
  if uid_suffix is not None and uid_suffix > 1:
    name = name + "_" + str(uid_suffix)

  is_question, formula, confidence, world, location, knower, tense = extract_package_ctx(package)
  if formula is None:
    return []

  s1_time_value = None  # set below if Stage 1 has explicit time expression
  s1_time_prep = None   # set below from asu_index[sid].time_prep
  s1_state_tense = None # set below from asu_index[sid].state_tense

  # Override $ctxt parameters with Stage-1 ASU data when available.
  # Stage-1 "time", "pre_state", "location" are more reliable than scanning
  # Stage-2 siblings; this is the programmatic $ctxt injection (option B).
  if asu_index:
    asu = asu_index.get(sid)
    if asu is not None:
      s1_tense = asu.get("time")
      s1_time_value = None  # explicit time expression (e.g., "1995")
      s1_time_prep = asu.get("time_prep")  # temporal preposition (e.g., "during")
      s1_state_tense = asu.get("state_tense")  # world tense when "time" has a value
      if s1_tense is not None:
        if s1_tense in ("past", "present", "future", "timeless"):
          tense = s1_tense
        else:
          # Explicit time value — don't use as $ctxt tense.
          # Facts are "present" at that time; "past" comes from axioms.
          s1_time_value = s1_tense
          # tense stays as-is (default present from package or None)
      if is_question:
        s1_world = asu.get("pre_state")
        if s1_world is not None:
          world = s1_world
        elif world is None and asu_index:
          # No pre_state on query — compute latest world from all ASUs.
          # The latest world is the highest next_state across all ASUs.
          # Compare numerically (W0 < W1 < ... < W10) not lexicographically.
          latest = None
          latest_n = -1
          for a in asu_index.values():
            ns = a.get("next_state")
            if ns is not None and isinstance(ns, str) and ns.startswith("W"):
              try:
                n = int(ns[1:])
              except ValueError:
                n = -1
              if n > latest_n:
                latest_n = n
                latest = ns
          if latest is not None:
            world = latest
      s1_loc = asu.get("location")
      if s1_loc is not None:
        location = s1_loc

  # Strip @time wrappers and annotate leaf atoms with $tense sentinels.
  # Pass the ASU-level tense as the default; atoms inside @time wrappers
  # will get their specific tense instead.
  # Always run: even in nocontext mode, @time wrappers must be removed
  # from the formula tree (the $tense sentinels are stripped during injection).
  formula = _strip_time_wrappers(formula, tense)

  question_kind = None
  if is_question:
    # Remove spurious "can" from event queries with no modal language.
    asu_text = ""
    if asu_index:
      asu = asu_index.get(sid)
      if asu:
        asu_text = asu.get("text", "")
    formula = _strip_spurious_can(formula, asu_text)
    # Safety net: if Stage-1 has wh_placeholder but Stage-2 used ["question",...]
    # instead of ["ask",VAR,...], detect the free variable and convert.
    formula = _fix_missing_ask(formula, asu_index, sid)
    # Inject isa(specific_noun, X) constraints for generic query entities
    # whose Stage-2 used only the ontological category (e.g. gemini emitting
    # isa(person,X) for a "man"-id entity — see case 136).
    asu_for_isa = asu_index.get(sid) if asu_index else None
    formula = _inject_query_specific_noun_isas(formula, asu_for_isa)
    # Get raw question text for who/what detection
    raw_q_text = ""
    if asu_index:
      asu_q = asu_index.get(sid)
      if asu_q:
        raw_q_text = asu_q.get("_raw", asu_q.get("text", ""))
    result, question_kind = _process_question(formula, name, raw_text=raw_q_text,
                                              generic_classes=generic_classes)
    if result is None:
      return []
  else:
    formula = _hoist_misnested_exists(formula)
    result = _process_assertion(formula, name, confidence)

  # Inject context into @logic entries (not @question entries).
  ctxt_template = None
  tense_term = None
  if _g_options.get("nocontext_flag", False):
    # Nocontext mode: inject "$c" constant so axioms with ?:Ctxt still unify.
    _inject_const_ctxt_into_objs(result)
  else:
    loc_term = location if location is not None else _fresh_fv()
    kn_term  = knower  if knower  is not None else _fresh_fv()
    if _is_rule_formula(formula):
      situation  = _fresh_fv()
      tense_term = _fresh_fv()   # rules are tense-independent
      ctxt_template = ["$ctxt", None, situation, loc_term, kn_term]
      _inject_ctxt_into_objs(result, ctxt_template, tense_term)
    elif is_question:
      if question_kind in ("where", "when"):
        # Where/when questions: use the query's world and tense from Stage 1.
        # The movement axiom produces present-tense results at the new world,
        # and frame axioms persist locations across worlds.
        matrix_world = world if world is not None else _fresh_fv()
        desc_world   = _fresh_fv()
        tense_term   = tense if tense is not None else "present"
        ctxt_matrix = ["$ctxt", None, matrix_world, loc_term, kn_term]
        ctxt_desc   = ["$ctxt", None, desc_world,   loc_term, kn_term]
        props_desc = _question_has_main_relation(formula)
        _inject_ctxt_question(result, ctxt_matrix, ctxt_desc, tense_term,
                              props_are_desc=props_desc)
      else:
        # Non-where questions: matrix predicates use the query's world;
        # descriptive predicates (isa, event atoms from relative clauses)
        # use free-var world so they can match assertions in any world state.
        # When a main relation (have, can, is_rel2) is present, property
        # predicates are also descriptive (restrictive noun modifiers).
        matrix_world = world if world is not None else _fresh_fv()
        desc_world   = _fresh_fv()
        tense_term   = tense if tense is not None else "present"
        ctxt_matrix = ["$ctxt", None, matrix_world, loc_term, kn_term]
        ctxt_desc   = ["$ctxt", None, desc_world,   loc_term, kn_term]
        props_desc = _question_has_main_relation(formula)
        _inject_ctxt_question(result, ctxt_matrix, ctxt_desc, tense_term,
                              props_are_desc=props_desc)
    else:
      # Situational facts: world from ["holds",W,F]; tense from Stage-1 time field.
      situation  = world if world is not None else _fresh_fv()
      tense_term = tense if tense is not None else "present"
      ctxt_template = ["$ctxt", None, situation, loc_term, kn_term]
      _inject_ctxt_into_objs(result, ctxt_template, tense_term)

  # Question-specific past->present bridge axioms: for each present-tense
  # stative literal in the question (with ground entity args), emit a
  # specialized bridge axiom so past-tense assertions can satisfy the
  # question. Replaces the disabled global axioms in axioms_std.js Section 6a.
  if is_question and not _g_options.get("nocontext_flag", False):
    bridges = _build_question_tense_bridges(result, name)
    result.extend(bridges)

  # NOTE: $theof1 definite rewrite moved to rawlogic_convert (global pass)
  # so question packages can find is_rel2 matches from assertion packages.

  # Inject context into set element instantiation clauses for this ASU.
  # Element clauses inherit the same world/tense as the ASU's own clauses.
  sid_key = str(sid)
  if set_el_by_sid and sid_key in set_el_by_sid:
    el_clauses = set_el_by_sid.pop(sid_key)
    if _g_options.get("nocontext_flag", False):
      _inject_const_ctxt_into_objs(el_clauses)
    elif ctxt_template is not None and not is_question:
      _inject_ctxt_into_objs(el_clauses, ctxt_template, tense_term)
    result.extend(el_clauses)

  # Generate $theof1/datetime time fact for explicit time values.
  # "In 1995, ..." → ["=", ["$theof1","time","W1","?:C"], ["$datetime", 1995]]
  # The $datetime value is numeric (integer) for $less comparison in axioms.
  if s1_time_value is not None and world is not None:
    # Convert to numeric if possible (years, dates as YYYYMMDD, etc.)
    try:
      dt_numeric = int(str(s1_time_value).replace("-", "").replace(":", "").replace("T", ""))
    except (ValueError, TypeError):
      dt_numeric = s1_time_value  # non-numeric time expressions stay as strings
    time_fact = {"@name": name,
                 "@logic": ["=", ["$theof1", "time", world, _fresh_fv()],
                                 ["$datetime", dt_numeric]]}
    result.append(time_fact)

    # Repair: ensure event-level has_time clause exists.  Stage 2 sometimes
    # omits it or puts a tense string ("past") instead of the real value.
    # Only fires when ALL of these hold:
    #   - Stage 1 explicitly provides time_prep (we don't guess the preposition)
    #   - This is an assertion, not a question (questions build their own has_time)
    #   - The ASU describes an event (has "actions" in Stage 1)
    #   - A clausified activity Skolem exists but lacks has_time with the value
    if (s1_time_prep and not is_question
        and asu is not None and asu.get("actions")):
      tv_str = str(s1_time_value)
      # The event position is usually a plain Skolem constant, but Stage 2 can
      # put a compound term there, which is a list and so unhashable: key both
      # maps on the term's string form and keep the term itself as the value.
      def _termkey(t):
        return t if isinstance(t, str) else repr(t)
      activity_skolems = {}   # term key -> event term
      hastime_by_subj = {}    # term key -> list of time-value strings
      for cl in result:
        logic = cl.get("@logic")
        if not isinstance(logic, list) or not logic:
          continue
        op = logic[0] if isinstance(logic[0], str) else None
        if op == "isa" and len(logic) >= 3 and logic[1] == "activity":
          activity_skolems[_termkey(logic[2])] = logic[2]
        elif op == "has time" and len(logic) >= 3:
          hastime_by_subj.setdefault(_termkey(logic[1]), []).append(str(logic[2]))
      for evkey, ev in activity_skolems.items():
        existing = hastime_by_subj.get(evkey, [])
        if tv_str in existing:
          continue  # already present — nothing to do
        ht_logic = ["has time", ev, s1_time_value, s1_time_prep]
        if ctxt_template is not None:
          t = tense if tense is not None else "present"
          ht_logic.append([ctxt_template[0], t] + ctxt_template[2:])
        result.append({"@name": name, "@logic": ht_logic})

  # Generate is_past_world fact from state_tense.
  # This handles non-numeric time values ("Monday") where the $less bridge
  # cannot derive is_past_world.  For numeric years the bridge also works,
  # so this is harmlessly redundant.
  if s1_state_tense == "past" and world is not None:
    result.append({"@name": name,
                   "@logic": ["is_past_world", world]})

  return result


def extract_package_ctx(package):
  """Like _extract_package but also returns (world, location, knower, tense).

  Returns: (is_question, formula, confidence, world, location, knower, tense)
    world    -- the W constant from ["holds", W, F], or None
    location -- the LOC from a sibling ["state location", W, LOC], or None
                (fallback only; Stage-1 ASU "location" takes priority via convert_id_package)
    knower   -- the HOLDER from a sibling ["kb", K, HOLDER, ...], or None
    tense    -- T from a sibling ["state time", W, T], or None
                (fallback only; Stage-1 ASU "time" takes priority via convert_id_package)
  """
  if not isinstance(package, list) or not package:
    return False, None, None, None, None, None, None

  op = package[0]

  if op == "holds":
    if len(package) >= 3:
      return False, package[2], None, package[1], None, None, None
    return False, None, None, None, None, None, None

  elif op == "question":
    if len(package) >= 2:
      body = package[1]
      # Strip "holds" wrapper from question body: ["question", ["holds", W, F]]
      # → use F as formula and W as world (for $ctxt injection).
      world = None
      if (isinstance(body, list) and len(body) >= 3
          and body[0] == "holds"):
        world = body[1]
        body  = body[2]
      return True, body, None, world, None, None, None
    return True, None, None, None, None, None, None

  elif op == "ask":
    if len(package) >= 3:
      body = package
      # Strip "holds" wrapper from ask body: ["ask", var, ["holds", W, F]]
      # → use ["ask", var, F] and W as world.
      world = None
      if (len(package) >= 3 and isinstance(package[2], list)
          and len(package[2]) >= 3 and package[2][0] == "holds"):
        world = package[2][1]
        body  = [package[0], package[1], package[2][2]]
      return True, body, None, world, None, None, None
    return True, None, None, None, None, None, None

  elif op == "and":
    main_pkg   = None
    confidence = None
    location   = None
    knower     = None
    tense      = None
    for el in package[1:]:
      if not isinstance(el, list) or not el:
        continue
      elop = el[0]
      if elop == "@p" and len(el) == 3:
        confidence = el[2]
      elif elop == "state location" and len(el) >= 3:
        location = el[2]
      elif elop == "state time" and len(el) >= 3:
        tense = el[2]
      elif elop == "kb" and len(el) >= 3:
        knower = el[2]   # ["kb", K, HOLDER, ATTITUDE, W]
      else:
        # Collect all main children (holds, question, ask, etc.)
        if main_pkg is None:
          main_pkg = el
          other_pkgs = []
        else:
          other_pkgs.append(el)
    if main_pkg is not None:
      is_q, formula, _, world, loc2, kn2, _ = extract_package_ctx(main_pkg)
      if location is None:
        location = loc2
      if knower is None:
        knower = kn2
      # If there are additional siblings (e.g. holds + question in same and),
      # merge them: extract each and combine formulas.
      for other in other_pkgs:
        is_q2, formula2, _, world2, loc3, kn3, _ = extract_package_ctx(other)
        if is_q2:
          # question/ask takes priority as the main result
          if formula is not None and formula2 is not None:
            formula2 = ["and", formula, formula2] if formula2[0] != "and" else ["and", formula] + formula2[1:]
          is_q = True
          formula = formula2
        elif formula2 is not None:
          # holds provides extra facts — merge into existing formula
          if formula is not None:
            formula = ["and", formula, formula2] if formula[0] != "and" else formula + [formula2]
          else:
            formula = formula2
        if world is None and world2 is not None:
          world = world2
      return is_q, formula, confidence, world, location, knower, tense
    return False, None, confidence, None, location, knower, tense

  else:
    return False, package, None, None, None, None, None
