# Logic conversion for the llm-based nlpsolver.
#
# Entry point: rawlogic_convert(logic)
# Takes stage-2 LLM output and produces GK-compatible clause list.
#
# Stage-2 input format:
#   ["and", ["@id","S1", PACKAGE], ["@id","S2", PACKAGE], ...]
#
# PACKAGE is one of:
#   ["holds", world, F]           - assertion: extract F
#   ["question", F]               - query: use F with @question key
#   ["ask", var, F]               - query with binding var -> ["exists",var,F]
#   ["and", PKG, ["@p","Sx",p]]   - with confidence metadata
#
# Output format (GK input):
#   [{"@name":"sent_S1", "@logic": CLAUSE}, ...]
#   {"@name":"sent_S3", "@question": FORMULA}
#
# GK clauses:
#   Single atom:         ["pred", arg, ...]
#   Multi-literal (or):  [["pred1",...], ["pred2",...], ...]
# Variables:  "?:X" (free vars = implicitly universally quantified in GK)
# Negation:   "-" prefix on predicate name, e.g. "-isa"
#
# Module structure:
#   lc_clausify.py   -- FOL-to-CNF compiler (clausify and helpers)
#   lc_questions.py  -- question wrapping and population fact injection
#   logconvert.py    -- main driver, package extraction, context injection,
#                       post-processing passes (this file)
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

from globals import options as _g_options


def _te(gate):
  """True if the named typeenrich sub-gate (super/gender/nametype/compound/
  plural/gnoun) is enabled, per the resolved EncodingConfig.  Selected on the
  CLI with -typeenrich[=<gate-list>]; the -abstract* presets enable all six."""
  return lc_encoding.current().te(gate)


import lc_clausify
import lc_questions
import lc_encoding
import lc_finalize

from lc_clausify import (clausify, is_skolem_const, is_skolem_fn,
                         singularize_isa_classes_in_node,
                         lower_isa_classes_in_node)

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
  scan_item_formula,
  build_population_facts,
  is_ground_term,
  S2_VAR_RE,
  WHERE_SPATIAL_PREPS,
  WHEN_TEMPORAL_PREPS,
)


# Post-clausification passes — split into three concern-based modules:
#   lc_post_normalize.py — fix Stage-2 errors and standardise predicate forms
#   lc_post_reify.py     — replace flat entity IDs with $theof1 / $measure_of
#   lc_post_inject.py    — generate per-problem axioms (synonyms, exclusions, ...)
from lc_post_normalize import (
  populate_clauses as _populate_clauses,
  build_compound_subsumption as _build_compound_subsumption,
  coerce_relclass as _coerce_relclass,
  normalize_gradable_predicates as _normalize_gradable_predicates,
  strip_isa_entity as _strip_isa_entity,
  add_possessive_have as _add_possessive_have,
  add_haspart_for_typed_have as _add_haspart_for_typed_have,
  inject_have_to_haspart_axioms as _inject_have_to_haspart_axioms,
  strip_degree_predicates as _strip_degree_predicates,
)
from lc_post_reify import (
  rewrite_definites as _rewrite_definites,
  rewrite_measure_terms as _rewrite_measure_terms,
)
from lc_post_inject import (
  inject_soft_synonyms as _inject_soft_synonyms,
  inject_exclusion_axioms as _inject_exclusion_axioms,
  inject_isa_cross_group_axioms as _inject_isa_cross_group_axioms,
  inject_verb_mutex_axioms as _inject_verb_mutex_axioms,
  inject_beneficiary_for_bridge as _inject_beneficiary_for_bridge,
  inject_measure_relation_bridges as _inject_measure_relation_bridges,
  inject_negative_implicative_bridges as _inject_negative_implicative_bridges,
  inject_perception_factive_bridges as _inject_perception_factive_bridges,
  inject_kinship_mutex_axioms as _inject_kinship_mutex_axioms,
  inject_carrier_lifts as _inject_carrier_lifts,
  inject_verb_result_state_axioms as _inject_verb_result_state_axioms,
  inject_acquire_have_axioms as _inject_acquire_have_axioms,
  inject_positional_actor_bridges as _inject_positional_actor_bridges,
  inject_containment_bridges as _inject_containment_bridges,
  inject_occasion_location_bridges as _inject_occasion_location_bridges,
  inject_in_haspart_bridge as _inject_in_haspart_bridge,
  inject_reflexive_property_bridge as _inject_reflexive_property_bridge,
  inject_s2split_shape_bridges as _inject_s2split_shape_bridges,
  inject_attribute_relation_bridges as _inject_attribute_relation_bridges,
  inject_stable_adjective_persistence as _inject_stable_adjective_persistence,
  inject_world_geometry as _inject_world_geometry,
)

from lc_post_una import (
  collect_stage1_entities as _collect_stage1_entities,
  is_stage1_entity as _is_stage1_entity,
  apply_una as _apply_una,
)

# $ctxt injection and time handling (in lc_ctxt.py).
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


# Pre-clausification formula rewrites (in lc_rewrites.py).
from lc_rewrites import (
  rewrite_meta_predicates as _rewrite_meta_predicates,
  rewrite_perspective_relations as _rewrite_perspective_relations,
  normalize_receive_events as _normalize_receive_events,
  strip_tense_has_time as _strip_tense_has_time,
  strip_neg_tense_agreement_in_clause as _strip_neg_tense_agreement_in_clause,
  inject_actuality as _inject_actuality,
  inject_degree_presuppositions as _inject_degree_presuppositions,
  hoist_misnested_exists as _hoist_misnested_exists,
  strip_spurious_can as _strip_spurious_can,
  negate_consequent as _negate_consequent,
  inject_query_specific_noun_isas as _inject_query_specific_noun_isas,
  lower_normally_through_forall as _lower_normally_through_forall,
)

# Per-package processing — split into lc_packages.py.
import lc_packages
from lc_packages import (
  convert_id_package,
  extract_package_ctx,
  raw_has_what_word,
)



# Stative event rewriting is in semnormalize.py; import the entry point.
from semnormalize import rewrite_stative_events as _rewrite_stative_events


# ======== structural repair ========

def _hoist_nested_ids(logic):
  """Hoist @id blocks nested inside other @id blocks to the top level.

  LLM JSON errors sometimes drop a closing bracket, causing the auto-fixer
  to nest one @id inside another.  Since @id blocks are never legitimately
  nested, any inner @id is extracted and placed as a sibling.

  Only operates on the top-level ["and", ...] structure.
  """
  if not isinstance(logic, list) or not logic:
    return logic
  op = logic[0]
  if op == "@id":
    items = [logic]
  elif op == "and":
    items = logic[1:]
  else:
    return logic

  changed = False
  new_items = []
  for item in items:
    if not isinstance(item, list) or len(item) < 2 or item[0] != "@id":
      new_items.append(item)
      continue
    # Scan this @id's children (positions 2+) for nested @id blocks.
    hoisted = []
    kept = [item[0], item[1]]  # "@id", SID
    for child in item[2:]:
      if isinstance(child, list) and len(child) >= 2 and child[0] == "@id":
        hoisted.append(child)
      else:
        kept.append(child)
    if hoisted:
      changed = True
      if len(kept) > 2:
        new_items.append(kept)
      new_items.extend(hoisted)
    else:
      new_items.append(item)

  if not changed:
    return logic
  # Recurse: hoisted items may themselves contain nested @ids.
  final_items = []
  for item in new_items:
    sub = _hoist_nested_ids(["and", item])
    if isinstance(sub, list) and sub and sub[0] == "and":
      final_items.extend(sub[1:])
    else:
      final_items.append(sub)
  if len(final_items) == 1:
    return final_items[0]
  return ["and"] + final_items


def _repair_misnested_normally_implies(logic):
  """Repair a rule consequent misplaced onto `normally`.

  Some LLMs (deepseek, case 1418) treat `normally` as a binary operator and
  emit ["normally", ["implies", A], C] — hanging the rule's consequent C off
  `normally` instead of inside the `implies`, which is left consequent-less
  (len 2) and would otherwise crash / lose the consequent.  Rewrite to
  ["normally", ["implies", A, C]] so the rule recovers its consequent.

  Discriminator vs the legitimate tagged form ["normally", FRM, CLASS]: the
  malformation's 3rd arg is a FORMULA (list), not a class-name string, and the
  1st arg is specifically a 2-element (consequent-less) `implies`.  A 2-element
  `implies` is always malformed, so the rewrite is unambiguous.  Recursive.
  """
  if not isinstance(logic, list) or not logic:
    return logic
  if (logic[0] == "normally" and len(logic) == 3
      and isinstance(logic[1], list) and len(logic[1]) == 2
      and logic[1][0] == "implies"
      and isinstance(logic[2], list)):
    logic = ["normally", ["implies", logic[1][1], logic[2]]]
  return [_repair_misnested_normally_implies(c) if isinstance(c, list) else c
          for c in logic]


# ======== self-defeating-conditional repair (negation scope) ========
#
# Stage-2 sometimes mis-scopes "X is not A and B": it reads "(not A) and B"
# when the sentence means "not (A and B)".  The resulting conditional
# ["implies", ["and", ["not", A], B], CONS] is SELF-DEFEATING when CONS is
# false under every antecedent-satisfying assignment -- the whole rule then
# collapses to just ¬antecedent, losing the intended content (case 41: premise
# "if Rina is not dependent and a student, then ..." parsed as ¬dep∧student,
# reducing to student→dependent).
#
# Detection is a tiny boolean truth-table over the (few) atoms of the
# implication; a *correctly* scoped conditional is never self-defeating, so the
# signal is clean.  Repair only the unambiguous two-conjunct mixed-polarity
# antecedent, by widening the negation to ¬(A∧B), and ONLY when that removes
# the self-defeat -- so we never flip a genuinely narrow-scope "(not A) and B".
# Gated on -guarddrop.

_SDC_CONNECTIVES = frozenset({"and", "or", "not", "xor", "implies",
                              "equivalent", "iff"})


def _sdc_atom_key(atom):
  """Canonical hashable form of an atom, ignoring $ctxt sub-terms."""
  if isinstance(atom, list):
    parts = []
    for x in atom:
      if (isinstance(x, list) and x and isinstance(x[0], str)
          and x[0].startswith("$ctxt")):
        continue
      parts.append(_sdc_atom_key(x))
    return tuple(parts)
  return atom


def _sdc_collect_atoms(node, out):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  if node[0] in _SDC_CONNECTIVES:
    for c in node[1:]:
      _sdc_collect_atoms(c, out)
  else:
    out.add(_sdc_atom_key(node))


def _sdc_eval(node, assign):
  """Evaluate a boolean formula; return True/False, or None if not evaluable."""
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return None
  h = node[0]
  if h == "not":
    v = _sdc_eval(node[1], assign) if len(node) >= 2 else None
    return None if v is None else (not v)
  if h in ("and", "or", "xor"):
    vs = [_sdc_eval(c, assign) for c in node[1:]]
    if any(v is None for v in vs):
      return None
    if h == "and":
      return all(vs)
    if h == "or":
      return any(vs)
    return (sum(1 for v in vs if v) % 2) == 1
  if h == "implies" and len(node) >= 3:
    a = _sdc_eval(node[1], assign); b = _sdc_eval(node[2], assign)
    return None if (a is None or b is None) else ((not a) or b)
  if h in ("equivalent", "iff") and len(node) >= 3:
    a = _sdc_eval(node[1], assign); b = _sdc_eval(node[2], assign)
    return None if (a is None or b is None) else (a == b)
  # atom
  return assign.get(_sdc_atom_key(node))


def _sdc_is_self_defeating(ant, cons):
  """True iff ant is satisfiable but cons is false in every ant-true row."""
  atoms = set()
  _sdc_collect_atoms(ant, atoms)
  _sdc_collect_atoms(cons, atoms)
  atoms = sorted(atoms)
  if not atoms or len(atoms) > 5:
    return False
  n = len(atoms)
  ant_sat = False
  for mask in range(1 << n):
    assign = {atoms[i]: bool(mask >> i & 1) for i in range(n)}
    a = _sdc_eval(ant, assign)
    if a is None:
      return False                      # not fully evaluable -> don't flag
    if a:
      ant_sat = True
      c = _sdc_eval(cons, assign)
      if c is None:
        return False
      if c:
        return False                    # an ant-true row with cons true
  return ant_sat


def _sdc_overlaps(conj, cons_atoms):
  a = set()
  _sdc_collect_atoms(conj, a)
  return bool(a & cons_atoms)


def _sdc_widen_negation(ant, cons):
  """For an ["and", ...] antecedent with EXACTLY ONE negated conjunct ["not", P],
  widen that negation over P plus the other "content" conjuncts (those whose
  atoms appear in the consequent), leaving guard conjuncts (e.g. isa(person,X),
  whose atoms the consequent never mentions) outside.  Returns the rewritten
  antecedent, or None if the shape doesn't qualify.
  "not (a person dependent on caffeine) and a student" ->
  person ∧ ¬(dependent ∧ student)."""
  if not (isinstance(ant, list) and len(ant) >= 2 and ant[0] == "and"):
    return None
  conjs = ant[1:]
  negated = [c for c in conjs
             if isinstance(c, list) and len(c) == 2 and c[0] == "not"]
  if len(negated) != 1:
    return None
  negc = negated[0]
  positives = [c for c in conjs if c is not negc]
  cons_atoms = set()
  _sdc_collect_atoms(cons, cons_atoms)
  content = [c for c in positives if _sdc_overlaps(c, cons_atoms)]
  guards = [c for c in positives if not _sdc_overlaps(c, cons_atoms)]
  if not content:
    return None
  new_neg = ["not", ["and", negc[1]] + content]
  new_conjs = guards + [new_neg]
  return new_conjs[0] if len(new_conjs) == 1 else ["and"] + new_conjs


# (-s2split repair) Off-inventory predicate names an isolated per-sentence
# Stage-2 call drifts into, mapped to their inventory forms.
_OFFINV_PRED_RENAME = {"has": "have", "has rel2": "is rel2",
                       "has agent": "has actor"}

# (-s2split repair) Adjective -> measurement-dimension noun, for $measure_of
# terms whose dimension slot drifted to the adjective ("$measure_of tall"
# instead of "$measure_of height", claude case 552).
_ADJ_DIMENSION = {
  "tall": "height", "high": "height", "heavy": "weight", "long": "length",
  "old": "age", "big": "size", "large": "size", "fast": "speed",
  "wide": "width", "deep": "depth", "hot": "temperature", "far": "distance",
}

from lc_post_normalize import GRADABLE_PROPS as _GRADABLE_PROPS


def _comparative_to_base(word):
  """"higher than" / "higher" -> "high"; "nicer" -> "nice"; "bigger" -> "big".
  Strips a trailing " than", then tries the standard -er reversals, accepting
  a candidate only if it is a known gradable adjective.  Returns the original
  string when nothing matches (so ordinary relation names are untouched)."""
  w = word
  if w.endswith(" than"):
    w = w[:-5].strip()
  if w.startswith("more "):
    cand = w[5:].strip()
    return cand if cand in _GRADABLE_PROPS else word
  if w in _GRADABLE_PROPS:
    return w
  if w.endswith("er"):
    for cand in (w[:-2], w[:-1], w[:-3]):   # tall-er, nice-r, bigg-er
      if cand and cand in _GRADABLE_PROPS:
        return cand
  return word


def _rename_offinventory_preds(node):
  if not isinstance(node, list) or not node:
    return node
  head = node[0]
  if isinstance(head, str) and head in _OFFINV_PRED_RENAME:
    head = _OFFINV_PRED_RENAME[head]
  out = [head] + [_rename_offinventory_preds(x) if isinstance(x, list) else x
                  for x in node[1:]]
  # comparative-phrase relation name: has degree rel2("higher than",...) ->
  # ("high",...)  (gemini case 553; also bare "higher")
  if (head in ("has degree rel2", "is rel2") and len(out) >= 2
      and isinstance(out[1], str)):
    out[1] = _comparative_to_base(out[1])
  # adjective-as-dimension: $measure_of("tall", X, W) -> ("height", X, W)
  if head == "$measure_of" and len(out) >= 2 and isinstance(out[1], str):
    out[1] = _ADJ_DIMENSION.get(out[1], out[1])
  return out


def _repair_self_defeating_conditional(logic):
  if not lc_encoding.current().guarddrop:
    return logic
  return _rsdc(logic)


def _rsdc(node):
  if not isinstance(node, list) or not node:
    return node
  node = [_rsdc(c) if isinstance(c, list) else c for c in node]
  if node[0] == "implies" and len(node) >= 3 and _sdc_is_self_defeating(node[1], node[2]):
    widened = _sdc_widen_negation(node[1], node[2])
    if widened is not None and not _sdc_is_self_defeating(widened, node[2]):
      node = ["implies", widened] + node[2:]
  return node


# ======== @definite tag stripping ========

def _strip_definite_tags(tree):
  """Remove @definite atoms from the logic tree.

  Strips ["@definite", ...] from "and" conjunctions.  These are metadata
  annotations not consumed by the pipeline.
  """
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  if op == "@definite":
    return None  # sentinel: remove this conjunct
  if op == "and":
    children = []
    for child in tree[1:]:
      result = _strip_definite_tags(child)
      if result is not None:
        children.append(result)
    if not children:
      return None
    if len(children) == 1:
      return children[0]
    return ["and"] + children
  return [_strip_definite_tags(child) if isinstance(child, list) else child
          for child in tree]


# ======== phantom isa-guard stripping (query bodies) ========

def _gather_entities(node, acc, stage1_set):
  """Collect Stage-1 numbered-entity constants ("car 1", "price 4") in node."""
  if isinstance(node, str):
    if _is_stage1_entity(node, stage1_set):
      acc.add(node)
  elif isinstance(node, list):
    for child in node:
      _gather_entities(child, acc, stage1_set)


def _count_entity(entity, node):
  """Count occurrences of the constant `entity` anywhere in node."""
  if node == entity:
    return 1
  if isinstance(node, list):
    return sum(_count_entity(entity, child) for child in node)
  return 0


def _strip_phantom_query_guards(logic, stage1_set):
  """Drop isa(C, E) guards from question/ask bodies when E is an ORPHAN
  Stage-1 entity: never asserted anywhere, and used nowhere else in the query
  body (only in the guard itself).

  Such a guard is *guaranteed unsatisfiable* — a query type-guard on a concrete
  constant that has no asserted type can only ever block the query, never
  contribute to a proof.  These leak in when Stage 2 drops a definite
  description's presupposition scaffolding (isa on the definite's referent)
  into the question body — e.g. gpt case 466 emitted `isa(price, price 4)` in
  the ask, where `price 4` only existed via a (since-stripped) @definite, so
  the whole conjunctive query became unprovable -> Unknown.

  The "used nowhere else in the body" condition is essential: it distinguishes
  a leaked presupposition (price 4, typed but never used) from the query's own
  SUBJECT (e.g. `isa(person, John)` in "John is tall?", where John also appears
  in the actual predication and the guard is load-bearing).  Without it the
  filter would strip ~100+ legitimate query-subject guards.

  Safety: removing a provably-unsatisfiable, otherwise-unused conjunct is a
  sound query simplification — it never turns a correct answer wrong.  Caveat
  (the unmasking risk): it converts a guaranteed-Unknown into whatever the rest
  of the now guard-free query proves; if that remainder is itself malformed, a
  previously-masked wrong answer may surface.  It removes a false Unknown; it
  does not validate the remaining query.

  Operates on the Stage-2 logic tree (after @definite stripping).  Returns the
  (possibly rewritten) tree.
  """
  if not isinstance(logic, list) or not logic:
    return logic

  # Pass 1: entities mentioned anywhere inside assertion (holds) packages.
  asserted = set()
  def collect_asserted(node):
    if not isinstance(node, list) or not node:
      return
    if node[0] == "holds":
      _gather_entities(node, asserted, stage1_set)
      return  # don't double-walk; holds bodies aren't queries
    for child in node:
      collect_asserted(child)
  collect_asserted(logic)

  # Pass 2: inside query (question/ask) bodies, drop orphan isa guards.
  def walk(node, in_query):
    if not isinstance(node, list) or not node:
      return node
    head = node[0]
    if head in ("question", "ask"):
      in_query = True
    if head == "and" and in_query:
      conjuncts = node[1:]
      kept = []
      for child in conjuncts:
        if (isinstance(child, list) and len(child) == 3 and child[0] == "isa"
            and isinstance(child[2], str)
            and _is_stage1_entity(child[2], stage1_set)
            and child[2] not in asserted
            # orphan: used nowhere else in this query body
            and sum(_count_entity(child[2], o) for o in conjuncts if o is not child) == 0):
          continue  # drop the dead orphan guard
        kept.append(walk(child, in_query) if isinstance(child, list) else child)
      if not kept:
        return ["and"]  # degenerate; leave an empty conjunction
      if len(kept) == 1:
        return kept[0]
      return ["and"] + kept
    return [walk(child, in_query) if isinstance(child, list) else child
            for child in node]

  return walk(logic, False)


# ======== "what" question population facts ========

def _has_what_query(s1_json):
  """Return True if any query ASU text contains 'what' or 'which' as a
  wh-word (anywhere in the text)."""
  if not s1_json or not isinstance(s1_json, list):
    return False
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []):
      if not isinstance(unit, dict):
        continue
      if unit.get("type") == "query":
        if raw_has_what_word(unit.get("text", "")):
          return True
  return False


# Classes to skip when generating "what" population facts.
_WHAT_POP_SKIP = frozenset({
  "activity", "entity", "object", "thing", "event",
})


def _generate_what_population(result):
  """Generate population isa facts for classes with concrete witnesses.

  Scans the clause list for unconditional isa(CLASS, ENTITY) facts where
  ENTITY is a concrete entity (not $some_*, not a variable).  For each
  such CLASS, generates isa(CLASS, $some_CLASS) if not already present.

  Returns a list of new clause dicts.
  """
  # Collect classes with concrete witnesses and existing population constants.
  witnessed_classes = set()
  existing_pop = set()
  for obj in result:
    if not isinstance(obj, dict):
      continue
    logic = obj.get("@logic")
    if not isinstance(logic, list) or not logic:
      continue
    # Single-literal positive clause: ["isa", CLASS, ENTITY]
    if (len(logic) == 3 and isinstance(logic[0], str) and logic[0] == "isa"
        and isinstance(logic[1], str) and isinstance(logic[2], str)):
      cls = logic[1]
      ent = logic[2]
      if cls.lower() in _WHAT_POP_SKIP:
        continue
      if ent.startswith("$some_"):
        existing_pop.add(cls)
      elif not ent.startswith("?:"):
        witnessed_classes.add(cls)

  # Generate population facts for witnessed classes without existing $some_
  new_facts = []
  for cls in witnessed_classes:
    if cls in existing_pop:
      continue
    pop_name = "$some_" + cls.replace(" ", "_")
    new_facts.append({"@name": "pop_what",
                      "@logic": ["isa", cls, pop_name]})
  return new_facts
# ======== main entry point ========

def _build_asu_index(s1_json):
  """Build a {unit_id: ASU} dict from Stage-1 JSON for programmatic $ctxt injection.

  s1_json is the list of sentence packages returned by llmparse.parse_text().
  Returns an empty dict when s1_json is None or malformed.
  """
  if not s1_json or not isinstance(s1_json, list):
    return {}
  index = {}
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "")
    for asu in pkg.get("units", []):
      if isinstance(asu, dict):
        uid = asu.get("unit_id")
        if uid:
          asu["_raw"] = raw  # store parent raw text for who/what detection
          index[uid] = asu
  return index


def _dedup_entity_clauses(result):
  """Remove entity_S* clauses whose @logic duplicates a sent_S* clause.

  Modifies result in place.  When entity category injection produces an isa
  fact that Stage-2 also produced, the entity_S* copy is removed so the
  content-derived sent_S* version (with proper @name and @confidence) is kept.
  """
  import json as _json
  sent_logics = set()
  for obj in result:
    if isinstance(obj, dict) and obj.get("@name", "").startswith("sent_"):
      logic = obj.get("@logic")
      if logic is not None:
        sent_logics.add(_json.dumps(logic, sort_keys=True))
  i = 0
  while i < len(result):
    obj = result[i]
    if (isinstance(obj, dict) and obj.get("@name", "").startswith("entity_")
        and obj.get("@logic") is not None
        and _json.dumps(obj["@logic"], sort_keys=True) in sent_logics):
      result.pop(i)
    else:
      i += 1


def _collect_positive_isa_entities(tree, polarity=True):
  """Return the set of entity IDs that appear in positive-polarity isa atoms.

  Recursively walks the raw Stage-2 JSON, tracking polarity through
  connectives, negation, implications, and low-confidence packages.
  Only entities in genuinely positive isa atoms are returned — entities
  in negated, antecedent, or low-confidence contexts are excluded so
  that entity category injection is not skipped for them.
  """
  found = set()
  if not isinstance(tree, list) or len(tree) == 0:
    return found
  op = tree[0]

  # Leaf isa atom — record only if positive polarity
  if (op == "isa" and len(tree) >= 3 and isinstance(tree[2], str)
      and polarity):
    found.add(tree[2])
    return found

  if not isinstance(op, str):
    for child in tree:
      if isinstance(child, list):
        found |= _collect_positive_isa_entities(child, polarity)
    return found

  # Connectives: children inherit polarity
  if op in ("and", "or"):
    # Check for low-confidence @p sibling: ["and", ["holds",...], ["@p","S1",0.1]]
    # If confidence < 0.5, the formula will be negated — flip polarity for siblings.
    child_polarity = polarity
    for child in tree[1:]:
      if (isinstance(child, list) and len(child) == 3
          and child[0] == "@p" and isinstance(child[2], (int, float))
          and child[2] < 0.5):
        child_polarity = not polarity
        break
    for child in tree[1:]:
      if isinstance(child, list):
        found |= _collect_positive_isa_entities(child, child_polarity)
    return found

  if op == "not" and len(tree) >= 2:
    found |= _collect_positive_isa_entities(tree[1], not polarity)
    return found

  if op == "implies" and len(tree) >= 3:
    # Antecedent: flip polarity; consequent: keep polarity
    found |= _collect_positive_isa_entities(tree[1], not polarity)
    found |= _collect_positive_isa_entities(tree[2], polarity)
    return found

  if op in ("forall", "exists") and len(tree) >= 3:
    found |= _collect_positive_isa_entities(tree[2], polarity)
    return found

  if op in ("normally", "holds", "question", "ask", "equivalent", "xor"):
    for child in tree[1:]:
      if isinstance(child, list):
        found |= _collect_positive_isa_entities(child, polarity)
    return found

  # @id wrapper: recurse into package
  if op == "@id" and len(tree) >= 3:
    found |= _collect_positive_isa_entities(tree[2], polarity)
    return found

  # Default: recurse into children
  for child in tree:
    if isinstance(child, list):
      found |= _collect_positive_isa_entities(child, polarity)
  return found


def _try_singularize(word):
  """Return a candidate singular form of word, or None if no rule applies.

  Conservative: handles common -ies, -ches/shes/xes/ses/zes, and -s patterns.
  May produce a non-word for edge cases like "gas" → "ga", but that's harmless
  because rules use proper singular forms which won't match the bad output.

  Used to bridge LLM plural/singular inconsistency when Stage-1 picks a plural
  entity id (e.g. "berries 2") but rules use the singular type ("berry").
  """
  if not isinstance(word, str) or len(word) < 4:
    return None
  if word.endswith("ies"):
    return word[:-3] + "y"
  if (word.endswith("ches") or word.endswith("shes")
      or word.endswith("xes") or word.endswith("ses")
      or word.endswith("zes")):
    return word[:-2]
  if (word.endswith("s")
      and not word.endswith("ss")
      and not word.endswith("us")
      and not word.endswith("is")):
    return word[:-1]
  return None


# Broad biological supertypes that are always sound to assert as a superclass of
# a more specific Stage-2 type (gentleman->person, alligator->animal).
_BROAD_SUPERTYPES = frozenset({"person", "animal"})

try:
  from data_names import gender_of as _name_gender
except Exception:
  def _name_gender(_first):
    return None


def _build_entity_category_clauses(s1_json, skip_entities=frozenset()):
  """Build isa clauses for concrete entities that carry a category annotation.

  For each unique concrete entity with a "category" field in any ASU, emits:
    {"@name": "entity_S<N>", "@logic": ["isa", category, entity_id]}
  where S<N> is the unit_id of the first ASU in which the entity appears.

  Additionally, when the entity id has a lowercase base word that differs from
  the category, also emits isa(base, entity_id).  For example, "man 1" with
  category "person" produces both isa(person, man 1) and isa(man, man 1).
  This ensures the descriptive type word is available for query matching.

  When the base word is detectably plural ("berries", "cars", "boxes"), also
  emits isa(singular, entity_id) — e.g. "berries 2" with base "berries" gets
  both isa(berries, berries 2) and isa(berry, berries 2).  Bridges Stage-2
  LLM inconsistency: rules typically use singular type names ("berry") but
  Stage-1 may pick plural entity ids ("berries 2") for mass-noun-like
  references.  Fixes case 164.

  Deduplicates by entity_id so each entity produces at most one set of clauses.
  Entities in *skip_entities* are skipped (they already have an isa in
  the Stage-2 logic).
  """
  if not s1_json or not isinstance(s1_json, list):
    return []
  seen = set()
  clauses = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for asu in pkg.get("units", []):
      if not isinstance(asu, dict):
        continue
      uid = asu.get("unit_id", "")
      for ent in asu.get("entities", []):
        if not isinstance(ent, dict):
          continue
        eid      = ent.get("id")
        category = ent.get("category")
        if not eid or not category:
          continue
        if ent.get("type") != "concrete":
          continue
        if eid in seen:
          continue
        seen.add(eid)
        name = "entity_" + uid
        # Category isa (e.g. isa(person, man 1)) — skip if Stage-2 already has it.
        if eid not in skip_entities:
          clauses.append({"@name": name, "@logic": ["isa", category, eid]})
        # (typeenrich) Broad biological supertypes are emitted even
        # when Stage-2 already gave a subtype (isa(gentleman,Harry) /
        # isa(alligator,Ted)): a gentleman IS a person, an alligator IS an
        # animal, and rules in the problem are quantified over "person"/
        # "animal" that nothing else establishes for the entity.  Gated to
        # -typeenrich (the super sub-gate) so the default path matches the
        # core-2026-06-03 checkpoint behavior.
        elif (category in _BROAD_SUPERTYPES
              and (_g_options.get("s2split_flag", False)
                   or _te("super"))):
          clauses.append({"@name": name, "@logic": ["isa", category, eid]})
        # (typeenrich) Gender from a first-name table: isa(man/woman, E),
        # so a rule guarded by "man"/"woman" can fire ("a man is either kind or
        # evil").  Sound when the name is known.
        if (category == "person" and _te("gender")):
          first = eid.split(" ", 1)[0]
          g = _name_gender(first)
          if g:
            clauses.append({"@name": name, "@logic": ["isa", g, eid]})
        # Base-word isa (e.g. isa(man, man 1)) — always add when the base
        # is a lowercase type word different from the category, even if
        # skip_entities contains the entity (Stage-2 may have isa(person,...)
        # but not isa(man,...)).
        parts = eid.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
          base = parts[0]
          if base[:1].islower() and base.lower() != category.lower():
            clauses.append({"@name": name, "@logic": ["isa", base, eid]})
            # Also emit singular form when the base is detectably plural,
            # to bridge "berries"/"berry"-style mismatches (case 164).
            singular = _try_singularize(base)
            if (singular and singular != base
                and singular.lower() != category.lower()):
              clauses.append({"@name": name, "@logic": ["isa", singular, eid]})
        # (typeenrich) Name-as-type: a multiword proper name is also typed by
        # its own name lowercased, so a generic existential ("a winter olympics")
        # can bind to the named constant ("Winter Olympics") that is otherwise
        # typed only by its category (isa(event,...)).
        if _te("nametype"):
          name_base = re.sub(r"\s+\d+$", "", eid).strip()
          name_type = name_base.lower()
          if (" " in name_base and re.search(r"[A-Z]", name_base)
              and name_type != category.lower()):
            clauses.append({"@name": name, "@logic": ["isa", name_type, eid]})
  return clauses


_SK_SUFFIX_RE = re.compile(r'^sk\d+_(\w+)$')


def _merge_typeonly_skolems(result):
  """(abstraction) Merge per-sentence Skolem CONSTANTS of the same type that are
  used only generically, so a definite "the gym"/"the campus" that Stage 2
  re-introduced as a separate `exists G[isa(gym,G)]` in each sentence (folding to
  sk1_gym, sk4_gym, ...) co-refers across the rule and the question.

  A constant sk<N>_<suffix> is MERGEABLE iff every one of its occurrences is:
    - the 2nd arg of a POSITIVE isa(TYPE, S)             (a type-only fact), or
    - a NON-subject arg (index >= 3) of an is rel2 of either polarity (object /
      location of the relation, never the agent/subject).
  Any other occurrence -- is rel2 SUBJECT, has property/degree/part, have, =,
  negated isa, a $block/other nesting -- is a distinguishing predicate, and marks
  the constant (and so its whole same-suffix group) un-mergeable.  Condition (b):
  all positive isa types over a group must agree.  Only string Skolem constants
  merge (never Skolem functions ['sk0', X]).  Constants are not `#:`-UNA-wrapped,
  so the rename is clean (no equality/UNA interaction).
  """
  groups = {}        # suffix -> set(skolem const)
  bad = set()        # constants with a distinguishing occurrence
  isatypes = {}      # skolem -> set of positive-isa TYPEs

  def _note(s):
    m = _SK_SUFFIX_RE.match(s) if isinstance(s, str) else None
    if m:
      groups.setdefault(m.group(1), set()).add(s)
      return True
    return False

  def _scan(lit):
    if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
      if isinstance(lit, list):
        for x in lit:
          if _note(x):
            bad.add(x)
          elif isinstance(x, list):
            _scan(x)
      return
    head = lit[0]
    base = head[1:] if head.startswith("-") else head
    pos = not head.startswith("-")
    if base == "isa" and len(lit) >= 3:
      for i, a in enumerate(lit):
        if _note(a):
          if i == 2 and pos:
            isatypes.setdefault(a, set()).add(lit[1] if isinstance(lit[1], str) else None)
          else:
            bad.add(a)            # type slot, negated isa, or extra position
        elif isinstance(a, list):
          _scan(a)
      return
    if base == "is rel2" and len(lit) >= 2:
      for i, a in enumerate(lit):
        # (flatroles) an event object can be role-tagged as
        # ["eventprop", $role, value]; treat the inner value as occupying this
        # position so an object Skolem stays MERGEABLE instead of being scanned
        # as a distinguishing nested literal (which would mark it un-mergeable
        # and break "the gym"/"the campus" cross-sentence coreference).
        if isinstance(a, list) and len(a) == 3 and a[0] == "eventprop":
          a = a[2]
        if _note(a):
          if i <= 2:              # verb(1) or subject(2) -> distinguishing
            bad.add(a)
        elif isinstance(a, list):
          _scan(a)
      return
    for a in lit:                 # any other predicate -> distinguishing
      if _note(a):
        bad.add(a)
      elif isinstance(a, list):
        _scan(a)

  for c in result:
    if not isinstance(c, dict):
      continue
    for key in ("@logic", "@question"):
      body = c.get(key)
      if not isinstance(body, list):
        continue
      lits = body if (body and isinstance(body[0], list)) else [body]
      for lit in lits:
        _scan(lit)

  subst = {}
  for suffix, members in groups.items():
    members = sorted(members)
    if len(members) < 2 or any(m in bad for m in members):
      continue
    types = set()
    for m in members:
      types |= isatypes.get(m, set())
    if len(types) > 1:            # condition (b): inconsistent isa type
      continue
    for m in members[1:]:
      subst[m] = members[0]       # canonical = lowest-numbered Skolem

  if not subst:
    return result

  def _apply(n):
    if isinstance(n, list):
      return [_apply(x) for x in n]
    return subst.get(n, n) if isinstance(n, str) else n

  for c in result:
    if isinstance(c, dict):
      for key in ("@logic", "@question"):
        if key in c:
          c[key] = _apply(c[key])
  return result


def rawlogic_convert(logic, s1_json=None, fixes=None):
  """Convert stage-2 LLM output to a GK-compatible clause list.

  Input:  stage-2 list ["and", ["@id","S1",PACKAGE], ...]
          s1_json -- Stage-1 JSON from llmparse.parse_text(), used for
                     programmatic $ctxt injection (tense, world, location)
                     and entity category isa injection.
          fixes   -- optional list; when a structural clause-repair pass
                     actually rewrites the logic, a short "logconvert: <name>"
                     marker is appended (surfaced as stage_2_fixes).
  Output: list of {"@name":..., "@logic":CLAUSE} / {"@name":..., "@question":F}
  Returns None on fatal error.
  """
  def _note_repair(before, after, name):
    if fixes is not None and after != before:
      fixes.append("logconvert: " + name)
  lc_ctxt._fv_nr = 0             # reset once for the whole conversion
  lc_clausify._skolem_nr = 0
  lc_clausify._gobj_nr   = 0
  lc_questions._defq_nr  = 0

  if not logic or not isinstance(logic, list):
    return None

  # Hoist nested @id blocks to top level.  LLM JSON errors sometimes cause
  # a closing bracket to be dropped, nesting one @id inside another after
  # auto-fix.  @id blocks are never legitimately nested.
  _b = logic
  logic = _hoist_nested_ids(logic)
  _note_repair(_b, logic, "hoist nested @ids")

  # Repair a rule consequent that an LLM hung off `normally` as a 2nd arg
  # instead of inside the `implies` (case 1418, deepseek): rewrite
  # ["normally", ["implies", A], C] -> ["normally", ["implies", A, C]].
  _b = logic
  logic = _repair_misnested_normally_implies(logic)
  _note_repair(_b, logic, "repair misnested normally/implies")

  # Repair a self-defeating conditional caused by a "not A and B" negation-scope
  # mis-parse: widen ["implies", ["and", ["not", A], B], CONS] to ¬(A∧B) when the
  # current reading makes CONS impossible under its antecedent (-guarddrop,
  # case 41).
  _b = logic
  logic = _repair_self_defeating_conditional(logic)
  _note_repair(_b, logic, "repair self-defeating conditional")

  # (-s2split repair) Normalize off-inventory predicate-name drift: an isolated
  # per-sentence Stage-2 call sometimes writes "has" for "have" or "has rel2" for
  # "is rel2" (cases 190/248).  Whole-head rename, before any other pass reads
  # predicate names.
  if _g_options.get("s2split_flag", False):
    _b = logic
    logic = _rename_offinventory_preds(logic)
    _note_repair(_b, logic, "rename off-inventory predicates (s2split)")

  # Lower outer `normally` into the consequent of forall...implies bodies:
  # ["normally", ["forall", X, ["implies", A, B]]] →
  # ["forall", X, ["implies", A, ["normally", B]]].
  # Some LLMs (gemini) emit the outer-normally form which clausifies into a
  # Skolem witness for "the rule has an exception" — useless for concrete
  # entities. The inner-normally form clausifies into the per-entity
  # defeasible rule (with $block guard) other LLMs already produce.
  logic = _lower_normally_through_forall(logic)

  # Inject degree presuppositions before any other processing:
  # "not very X" presupposes "X", so expand ["not",["has degree property",P,E,"high",C]]
  # into ["and", ["has degree property",P,E,"none",C], ["not",["has degree property",P,E,"high",C]]]
  logic = _inject_degree_presuppositions(logic)

  # Rewrite event-reified stative verbs (have, like, own, ...) to direct
  # predicates.  LLMs sometimes use Davidsonian event encoding for statives;
  # the prover needs the direct predicate form.
  logic = _rewrite_stative_events(logic)

  # Rewrite is_rel2("is", A, B) → isa(A, B).  The copula "is" is not a real
  # relation; LLMs (especially Gemini) sometimes produce it for identity/type
  # questions.  Safe because is_rel2("is",...) has no valid semantic meaning.
  logic = _rewrite_meta_predicates(logic)

  # Lift binary-relation perspective verbs (`["is rel2","got",X,Y]` etc.)
  # into Davidsonian events so normalize_receive_events can bridge them.
  # Some LLMs (gpt, deepseek) emit the relation form for perspective verbs
  # in queries; without this lift, "Who got a letter?" never unifies with
  # "Eve gave a letter to Tom".
  logic = _rewrite_perspective_relations(logic)

  # Normalize "receive" events: receive→give with actor→recipient swap.
  # Must run after rewrite_meta_predicates (which normalizes verb synonyms)
  # and rewrite_perspective_relations (which produces fresh perspective events).
  logic = _normalize_receive_events(logic)

  # Remove has_time atoms where the value is a grammatical tense ("past", etc.)
  # LLMs sometimes put tense in has_time instead of leaving it to $ctxt.
  logic = _strip_tense_has_time(logic)

  # Attach ["actuality", E] to every Davidsonian event without a modal
  # classifier.  Pipeline-only marker; Stage 2 doesn't emit it.  Skips
  # inner content events of two-event reifications (has_content second arg).
  logic = _inject_actuality(logic)

  # Event fold: rewrite collapsible Davidsonian events (no modal, no content
  # nest, no world change, template roles only).  Two folds select here via the
  # encoding flags: the flat relational fold (-event flat / flatroles, the
  # latter role-tagging the object as ["eventprop", role, value]) and the
  # compact Davidsonian fold (-event davidson).  Runs after actuality injection
  # and tense-has_time stripping so the eligibility test sees the final event
  # shape.  $ctxt is attached to the folded literal later (lc_ctxt) exactly as
  # for reified roles.
  _enc = lc_encoding.current()
  if _enc.needs_coarsen:
    import lc_coarse as _lc_coarse
    logic = _lc_coarse.coarsen_events(logic,
                                      flatten=_enc.flatten,
                                      eventprop=_enc.eventprop,
                                      davidson=_enc.davidson,
                                      do_canon=_enc.entitymerge,
                                      do_guard=_enc.guarddrop,
                                      collapse_degree=_enc.collapse_degree)

  # (L2 -existfold) fold bare existential attributes into unary has_property.
  # Pre-clausification tree pass (exists nodes still present); the bridge is
  # injected later in the sem_axioms block.  Gated entirely on existfold_flag.
  if _g_options.get("existfold_flag", False):
    import lc_existfold as _lc_existfold
    _lc_existfold.reset()
    logic = _lc_existfold.fold_existential_attributes(logic)

  # Strip @definite tags from the logic tree.  These are metadata annotations
  # produced by Stage 2 but not consumed by the pipeline (definite info comes
  # from Stage 1).  Leaving them in can cause extract_package_ctx to mistake
  # them for the main formula.
  logic = _strip_definite_tags(logic)

  # Drop phantom isa-guards from query bodies: a leaked definite-description
  # presupposition (isa on a Stage-1 entity that nothing asserts) makes the
  # whole conjunctive query unprovable.  Removing the dead guard is a sound
  # simplification (see _strip_phantom_query_guards).
  _b = logic
  logic = _strip_phantom_query_guards(logic, _collect_stage1_entities(s1_json))
  _note_repair(_b, logic, "strip phantom query guard")

  # Rewrite $setof terms to canonical form (replaces ?:X with $arg1,
  # extracts anchors, $-prefixes internal predicates, generates membership
  # axioms and element instantiation clauses).
  import lc_sets as _lc_sets
  _lc_sets._set_counter = 0
  logic, set_axioms, set_element_clauses = _lc_sets.process_sets(logic)

  if logic[0] == "@id":
    items = [logic]
  elif logic[0] == "and":
    items = logic[1:]
  else:
    return None

  # Group set element clauses by source SID so each ASU can inject its own
  # $ctxt (world, tense) into its element facts.  @name format is
  # "sent_S1_el1", "sent_S1_dist", etc. — extract SID as the part between
  # "sent_" and the last "_el" or "_dist" suffix.
  set_el_by_sid = {}
  for cl in set_element_clauses:
    nm = cl.get("@name", "")
    if nm.startswith("sent_"):
      core = nm[5:]  # strip "sent_"
      # Find the SID: everything before "_el" or "_dist"
      for sep in ("_el", "_dist", "_exist"):
        idx = core.find(sep)
        if idx >= 0:
          sid = core[:idx]
          set_el_by_sid.setdefault(sid, []).append(cl)
          break

  # Build unit_id -> ASU index for programmatic $ctxt injection from Stage-1 data.
  asu_index = _build_asu_index(s1_json)

  # Build entity category isa facts from Stage-1 entity annotations.
  # Skip entities that already have a positive-polarity isa in Stage-2
  # (avoids conflicting categories like isa(person,John) when text says "John is a car").
  # Entities in negative polarity (negation, low-confidence, implies-antecedent)
  # are NOT skipped — they need the injection for resolution.
  s2_isa_entities = _collect_positive_isa_entities(logic)
  entity_cat_clauses = _build_entity_category_clauses(s1_json, skip_entities=s2_isa_entities)

  # Build population facts by scanning the raw stage-2 input first.
  pop_facts = _populate_clauses(items)

  # Build compound type subsumption rules (e.g. "baby bird" -> "bird").
  # Under -typeenrich also scan the Stage-1 entity-category clauses, so a
  # compound that only appears as an entity category ("harding pegmatite mine")
  # still gets its head subsumption (-> "mine").  See case 112.
  _ultra_flag = _te("compound")
  compound_subs = _build_compound_subsumption(
      items, ultra=_ultra_flag,
      extra_clauses=(entity_cat_clauses if _ultra_flag else ()),
      degree_comp=_g_options.get("s2split_flag", False))

  # Track how many times each unit_id has been seen so we can generate
  # globally unique clause names (sent_S1, sent_S1_2, sent_S1_3, ...).
  uid_count = {}
  theof_relations = set()  # collect (REL, TYPE) pairs for bridge axiom generation
  result = []
  for item in items:
    if isinstance(item, list) and len(item) >= 2 and item[0] == "@id":
      sid = str(item[1])
      uid_count[sid] = uid_count.get(sid, 0) + 1
      objs = convert_id_package(item, asu_index, uid_suffix=uid_count[sid],
                                 set_el_by_sid=set_el_by_sid)
    else:
      objs = convert_id_package(item, asu_index, set_el_by_sid=set_el_by_sid)
    if objs:
      result.extend(objs)

  # Emit any orphan element clauses (SIDs not matched) with context.
  for sid, el_clauses in set_el_by_sid.items():
    if _g_options.get("nocontext_flag", False):
      _inject_const_ctxt_into_objs(el_clauses)
    else:
      ctxt_template = ["$ctxt", None, _fresh_fv(), _fresh_fv(), _fresh_fv()]
      _inject_ctxt_into_objs(el_clauses, ctxt_template, _fresh_fv())
    result.extend(el_clauses)

  # Add set membership axioms (pre-clausified by lc_sets).
  for ax_clause in set_axioms:
    result.append({"@name": "frm_set", "@logic": ax_clause})

  # Rewrite definite functional descriptions to $theof1 terms (global pass).
  # Runs after all packages are collected so question packages can find
  # is_rel2/have+isa matches from assertion packages.
  # With -dropdefinites (set by the -abstract* presets), skip $theof1
  # reification: the function-term rewrite can absorb a named subject's relation
  # ("Andrew was the script editor for X" -> the relation is folded into $theof1
  # and the Andrew link is lost).  Leaving definites as plain relations keeps
  # those links and matches FOLIO's atomic relation style.  Otherwise reify in
  # the default lenient first-match mode (the core-2026-06-03 behaviour).
  if asu_index and not lc_encoding.current().dropdefinites:
    for sid_key in asu_index:
      _rewrite_definites(result, asu_index, sid_key, theof_relations)

  # Add per-relation $theof1 bridge axioms.
  for rel_name, type_base in theof_relations:
    # is_rel2("father of", $theof1("father", ?:S, ?:C), ?:S, ?:C)
    bridge_rel = ["is rel2", rel_name,
                  ["$theof1", type_base, "?:S", "?:C"], "?:S", "?:C"]
    result.append({"@name": "frm_theof", "@logic": bridge_rel})
    # isa("father", $theof1("father", ?:S, ?:C))
    bridge_isa = ["isa", type_base,
                  ["$theof1", type_base, "?:S", "?:C"]]
    result.append({"@name": "frm_theof", "@logic": bridge_isa})

  # Convert $measure terms to canonical $list form and collect $measure_of attrs.
  measure_attrs = _rewrite_measure_terms(result)
  for attr in measure_attrs:
    # have(?:S, $measure_of(ATTR, ?:S, ?:W), context)
    bridge_have = ["have", "?:S", ["$measure_of", attr, "?:S", "?:W"]]
    if _g_options.get("nocontext_flag", False):
      bridge_have.append("$c")
    else:
      bridge_have.append(["$ctxt", "?:T", "?:W", "?:L", "?:K"])
    result.append({"@name": "frm_measure", "@logic": bridge_have})
    # isa(ATTR, $measure_of(ATTR, ?:S, ?:W))
    bridge_isa = ["isa", attr, ["$measure_of", attr, "?:S", "?:W"]]
    result.append({"@name": "frm_measure", "@logic": bridge_isa})

  # Prepend entity category clauses at the start of the clause list so they
  # are available as given facts throughout the proof.
  # Then remove entity_S* clauses that duplicate sent_S* clauses (prefer the
  # content-derived ones which carry proper @name and may have @confidence).
  result = entity_cat_clauses + result
  _dedup_entity_clauses(result)

  # Insert population facts and compound subsumption rules immediately before
  # the first @question entry so they are available as background knowledge.
  background = pop_facts + compound_subs

  # Inject soft synonym biconditional axioms and mutual-exclusion axioms
  # for words appearing in the clause list. These use a single free context
  # variable (not the expanded $ctxt template), so they are inserted
  # separately and NOT passed through context injection.
  sem_axioms = []
  if not _g_options.get("nosemnormal_flag"):
    from axiom_vocab import load_axiom_vocab as _load_axiom_vocab
    _axiom_vocab = _load_axiom_vocab()
    # Verb-result-state must run BEFORE inject_exclusion_axioms so that
    # the result-state property words (e.g. "destroyed" from a destroy
    # event) become eligible for the exclusion injector's REQUIRE_BOTH_SIDES
    # check (e.g. destroyed/intact via MANUAL_ADJ_GRAD_*).
    # (-event davidson) injectors scan the static clauses for has_type (the verb),
    # has_actor/has_target and is_rel2 -- which davidson folds into event(...).
    # Give them a SCAN-ONLY expanded view so they recognise folded events exactly
    # as the reified encoding; the real clause list is unchanged (the event<->roles
    # bridge supplies the roles at prove time).
    _davx = lc_encoding.current().davidson
    def _dv(r):
      if not _davx:
        return r
      import lc_coarse as _lcc
      return _lcc._davidson_expand_for_scan(r)
    verb_result_axioms = _inject_verb_result_state_axioms(_dv(result), _axiom_vocab)
    result.extend(verb_result_axioms)
    iv = _dv(result)                       # recompute after extend (exclusion sees result-states)
    sem_axioms = (_inject_soft_synonyms(iv, _axiom_vocab)
                  + _inject_exclusion_axioms(iv, _axiom_vocab)
                  + _inject_isa_cross_group_axioms(iv, _axiom_vocab)
                  + _inject_verb_mutex_axioms(iv, _axiom_vocab)
                  + _inject_beneficiary_for_bridge(iv)
                  + _inject_kinship_mutex_axioms(iv, _axiom_vocab)
                  + _inject_carrier_lifts(iv)
                  + _inject_acquire_have_axioms(iv)
                  + _inject_positional_actor_bridges(iv)
                  + _inject_containment_bridges(iv)
                  + _inject_attribute_relation_bridges(iv)
                  + _inject_stable_adjective_persistence(iv))
    if lc_encoding.current().bridges:
      import lc_coarse as _lcc
      sem_axioms = (sem_axioms
                    + _inject_occasion_location_bridges(iv)
                    + _inject_in_haspart_bridge(iv)
                    + _inject_reflexive_property_bridge(iv))
      if not _davx:                        # davidson injects its own event<->roles bridge
        sem_axioms = sem_axioms + _lcc.rel2_event_axiom_clauses()
    if _g_options.get("s2split_flag"):
      sem_axioms = sem_axioms + _inject_s2split_shape_bridges(iv)

  # (-event davidson) event<->reified-roles bridge. Injected independently of
  # nosemnormal: the folded event(...) atoms must interderive with the role
  # atoms that wh/answer/rendering read, else those break.
  if lc_encoding.current().davidson:
    import lc_coarse as _lcc
    sem_axioms = sem_axioms + _lcc.event_axiom_clauses()

  # (L2 -existfold) named-witness bidirectional bridge, injected only when a fold
  # actually fired (avoids the reverse clause firing on unrelated problems).
  if _g_options.get("existfold_flag", False):
    import lc_existfold as _lc_existfold
    if _lc_existfold.any_fired():
      sem_axioms = sem_axioms + _lc_existfold.bridge_clauses()

  # Append population facts, synonym axioms, and exclusion axioms after
  # all sentence clauses (assertions + questions come first).
  result.extend(background)
  result.extend(sem_axioms)

  # Dynamic measure_of -> "<noun> of" relational bridge (replaces the former
  # static block in axioms_std.js).  Emitted per measure noun only when both a
  # $measure_of(N,...) fact and an is_rel2 "N of" atom are present.  Runs
  # unconditionally (structural bridge, not lexical normalisation).
  result.extend(_inject_measure_relation_bridges(result))

  # Dynamic negative-implicative bridge for refuse/decline (replaces the former
  # static axioms_std.js §5.2b block).  Emitted only when the verb appears.
  result.extend(_inject_negative_implicative_bridges(result))

  # Dynamic perception-factive bridge (hear/see/… → perceived event is actual).
  result.extend(_inject_perception_factive_bridges(result))

  # For "what" questions: generate extra population witnesses for classes
  # that have concrete unconditional isa facts.  This lets the prover find
  # class-level answers (e.g., "A wolf") in addition to concrete instances
  # (e.g., "Gertrude").
  if _has_what_query(s1_json):
    what_pop = _generate_what_population(result)
    if what_pop:
      result.extend(what_pop)

  # Inject context into population and subsumption facts.
  if _g_options.get("nocontext_flag", False):
    _inject_const_ctxt_into_objs(background)
  else:
    for fact in background:
      ctxt_template = ["$ctxt", None, _fresh_fv(), _fresh_fv(), _fresh_fv()]
      _inject_ctxt_into_objs([fact], ctxt_template, _fresh_fv())

  # Infer have(Y,E,CT) from possessive is_rel2(T+" of",E,Y,CT) + isa(T,E) pairs.
  _add_possessive_have(result)

  # Bridge have(X,Y,CT) -> has_part(X,Y,CT) when a rule uses has_part on the
  # same noun type (case 207: "John has a long trunk" + has_part-typed rule).
  _add_haspart_for_typed_have(result)

  # Forward bridge axiom (have -> has_part), type-gated, to complement
  # axioms_std.js §2 (has_part -> have).  Closes case 6: assertion with
  # -has_part and query with -have on the same body-part type.
  _inject_have_to_haspart_axioms(result)

  # Normalize has property / has degree property based on the gradable whitelist.
  # Must run before _coerce_relclass so relclass coercion sees the correct predicate.
  _normalize_gradable_predicates(result)

  # Remove isa/entity literals: positive ones make a clause a tautology (remove
  # the whole clause); negative ones are always false (remove just the literal).
  _strip_isa_entity(result)

  # Fix RELCLASS mismatches in question degree-predicate atoms.
  _coerce_relclass(result)

  # When -simpleprops / -simple is active, replace degree predicates with
  # their non-gradable equivalents so the prover sees simpler atoms.
  if _g_options.get("noproptypes_flag", False):
    _strip_degree_predicates(result)

  # Emit a minimal `next` chain over the concrete worlds actually present.
  # Replaces the static W0..W12 chain that used to live in axioms_std.js §11.
  result.extend(_inject_world_geometry(result))

  # Class-number normalization: singularize the class argument of every isa
  # atom across the final clause list (LLM-emitted, population facts, and
  # injected $defq guards alike), so a bare-plural generic ("animals") unifies
  # with the singular form and with the population witness isa(animal,
  # $some_animal).  Runs after all injection so no later pass can reintroduce a
  # plural class name.
  _ultra = _te("plural")
  for _c in result:
    if isinstance(_c, dict):
      for _k in ("@logic", "@question"):
        if isinstance(_c.get(_k), list):
          _c[_k] = singularize_isa_classes_in_node(_c[_k])
          if _ultra:
            # (typeenrich) fold isa-class case so "American national" and
            # "american national" become one predicate.  Runs after all
            # injection (incl. compound subsumption) so no later pass can
            # reintroduce a capitalized class.
            _c[_k] = lower_isa_classes_in_node(_c[_k])

  # Drop vacuous negative tense-agreement has_time escapes from query goal
  # clauses (-has time(E, T, _, $ctxt(T, ...)) with the value equal to the
  # $ctxt tense): the event's tense is already carried by the $ctxt slot, so
  # the literal only over-constrains a question whose assertion expresses
  # time via a modifier ("written in June").  Positive has_time facts kept.
  for _c in result:
    if isinstance(_c, dict):
      for _k in ("@logic", "@question"):
        if isinstance(_c.get(_k), list):
          _c[_k] = _strip_neg_tense_agreement_in_clause(_c[_k])

  # @sourcetype is kept in the clause list so that downstream display code
  # (format_sentences_to_clauses) can distinguish population facts from
  # ASU-derived clauses.  It is stripped in clause_list_to_json_commented
  # before serialization for the prover.

  # (typeenrich) Gendered-noun -> gender axioms.  For each gendered role
  # noun that occurs as a type in the clauses (gentleman, actress, waitress,
  # ...), inject isa(noun,X) -> isa(man/woman,X), so a rule guarded by
  # "man"/"woman" fires for an entity typed only with the role noun.  Gated to
  # nouns actually present, so at most a handful of axioms are added.
  if _te("gnoun"):
    try:
      from data_names import GENDERED_NOUN as _GN
    except Exception:
      _GN = {}
    if _GN:
      present = set()
      def _scan_types(node):
        if isinstance(node, list):
          if (len(node) >= 3 and node[0] in ("isa", "-isa")
              and isinstance(node[1], str) and node[1] in _GN):
            present.add(node[1])
          for x in node:
            _scan_types(x)
      for obj in result:
        if isinstance(obj, dict):
          _scan_types(obj.get("@logic") or obj.get("@question"))
      for noun in sorted(present):
        result.append({"@name": "frm_gender",
                       "@logic": [["-isa", noun, "?:Xg"], ["isa", _GN[noun], "?:Xg"]]})

  # UNA wrapping: prefix every Stage-1 numbered entity with "#:" so the gk
  # prover treats distinct entity constants as definitely unequal. Required
  # by axioms_std.js §7h (X2 direct-support uniqueness).
  stage1_entities = _collect_stage1_entities(s1_json)
  if stage1_entities:
    result = _apply_una(result, stage1_entities)

  # (abstraction) Strip ALL defeasibility, then decouple $ctxt across clauses but
  # share ONE context variable within each clause, then tidy the clauses.  Under
  # the -abstract presets the encoding is fully strict/monotonic (matching FOLIO's
  # classical FOL): defeasible rules become strict and habitual/typical events
  # become real.
  # Per clause, in order:
  #   0a. unwrap `normally`/`-normally` wrappers      -> their inner formula
  #   0b. drop `$block` blocker and `typical` literals -> no exceptions, real events
  #       (a clause emptied by this drop is removed)
  #   1.  every $ctxt term in a clause  -> one shared fresh ?:Cu var (per clause)
  #   2.  flatten any inner ["or", ...]  -> its literals at the clause top level
  #   3.  tautology  -> a clause with a literal and its negation is dropped
  #   4.  duplicate identical literals   -> collapsed to one copy
  # FOLIO is timeless, so tense/world/location carry no information; collapsing
  # each clause's $ctxt to one var lets steps 3-4 recognise the hidden redundancy.
  # @question goals keep per-atom freshening (they are not CNF clauses).
  if _ultra:
    result = lc_finalize.finalize_strict_clauses(result)

    # Merge per-sentence Skolem constants of the same type that are used only
    # generically ("the gym"/"the campus" re-existentialised per sentence), so
    # the rule and the question co-refer.  Runs last, on the clean strict clauses.
    result = _merge_typeonly_skolems(result)

  return result

# =========== the end ==========
