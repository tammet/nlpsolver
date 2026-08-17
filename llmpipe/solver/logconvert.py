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
import lc_reference
from lc_repairs import (hoist_nested_ids, repair_misnested_normally_implies,
                        repair_self_defeating_conditional, rename_offinventory_preds,
                        strip_definite_tags, repair_question_packaging,
                        canonicalize_comparative_relations)
from lc_query_guards import (strip_phantom_query_guards, has_what_query,
                            generate_what_population)
from lc_entity_isa import (collect_positive_isa_entities,
                          build_entity_category_clauses, merge_typeonly_skolems)

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
  drop_reflexive_locatives as _drop_reflexive_locatives,
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
  inject_propclass_bridges as _inject_propclass_bridges,
  parse_numeric_literals as _parse_numeric_literals,
  inject_number_typing as _inject_number_typing,
  inject_comparative_axioms as _inject_comparative_axioms,
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
  drop_category_isa_conjuncts as _drop_category_isa_conjuncts,
  fold_class_name_case as _fold_class_name_case,
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


# (8a) Literal heads that abort gk's reader.  gk rejects the whole input file
# on a parse error, so a clause carrying one of these must be dropped before it
# reaches the prover.  "<=" is reported as "first element of a list must be a
# symbol, not a number" (a misleading message: the head is the problem, not the
# numeric argument).  "<", ">", ">=" and "!=" parse and are simply not proved.
_GK_UNPARSEABLE_HEADS = frozenset(["<="])


def _clause_unparseable_reason(body):
  """Return a reason string when a clause cannot be given to gk, else None."""
  bad = []

  def walk(node, depth=0):
    if bad or depth > 60 or not isinstance(node, list) or not node:
      return
    head = node[0]
    if isinstance(head, str) and head.lstrip("-") in _GK_UNPARSEABLE_HEADS:
      bad.append("unparseable operator '" + head.lstrip("-") + "'")
      return
    if isinstance(head, (int, float)) and not isinstance(head, bool):
      bad.append("number-headed list")
      return
    for child in node:
      walk(child, depth + 1)

  walk(body)
  return bad[0] if bad else None


def _drop_unparseable_clauses(result, fixes=None):
  """Remove clauses whose shape would make gk reject the whole input."""
  if _g_options.get("nofix_containment") or not result:
    return result
  kept = []
  dropped = []
  for cl in result:
    body = cl.get("@logic", cl.get("@question")) if isinstance(cl, dict) else None
    reason = _clause_unparseable_reason(body) if body is not None else None
    if reason is None:
      kept.append(cl)
    else:
      dropped.append((str(cl.get("@name", "?")), reason))
  if dropped and fixes is not None:
    for name, reason in dropped[:4]:
      fixes.append("logconvert: dropped unparseable clause " + name + " (" + reason + ")")
  return kept


def _malformed_package_reason(item):
  """(8a) Return a short reason string when a Stage-2 package is structurally
  unusable, or None when it looks convertible.

  Only shapes that gk or the converter cannot represent at all are rejected:
  a list whose head is a number or a list where a predicate/connective name
  belongs.  gk reports the first of these as
  "first element of a list must be a symbol, not a number"; the second raises
  inside the converter.  Everything else is left to the normal passes, which
  have their own repairs.
  """
  bad = []

  def walk(node, depth=0):
    if bad or depth > 60 or not isinstance(node, list) or not node:
      return
    head = node[0]
    if isinstance(head, (int, float)) and not isinstance(head, bool):
      bad.append("number-headed list")
      return
    for child in node:
      walk(child, depth + 1)

  # The package body only: ["@id", SID, BODY].  A numeric SID is fine.
  body = item[2] if (isinstance(item, list) and len(item) >= 3
                     and item[0] == "@id") else item
  walk(body)
  return bad[0] if bad else None


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
  logic = hoist_nested_ids(logic)
  _note_repair(_b, logic, "hoist nested @ids")

  # Repair a rule consequent that an LLM hung off `normally` as a 2nd arg
  # instead of inside the `implies` (case 1418, deepseek): rewrite
  # ["normally", ["implies", A], C] -> ["normally", ["implies", A, C]].
  _b = logic
  logic = repair_misnested_normally_implies(logic)
  _note_repair(_b, logic, "repair misnested normally/implies")

  # Repair a self-defeating conditional caused by a "not A and B" negation-scope
  # mis-parse: widen ["implies", ["and", ["not", A], B], CONS] to ¬(A∧B) when the
  # current reading makes CONS impossible under its antecedent (-guarddrop,
  # case 41).
  _b = logic
  logic = repair_self_defeating_conditional(logic)
  _note_repair(_b, logic, "repair self-defeating conditional")

  # (-s2split repair) Normalize off-inventory predicate-name drift: an isolated
  # per-sentence Stage-2 call sometimes writes "has" for "have" or "has rel2" for
  # "is rel2" (cases 190/248).  Whole-head rename, before any other pass reads
  # predicate names.
  if _g_options.get("s2split_flag", False):
    _b = logic
    logic = rename_offinventory_preds(logic)
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

  # Preserve Stage-1 participant identity and generic-kind information before
  # the event fold can erase it.  These are construction-level repairs: they
  # consume explicit Stage-1 scope/role/modifier/coreference annotations, not
  # a list of favored words.
  _b = logic
  logic = lc_reference.normalize_stage1_kind_constants(logic, s1_json)
  _note_repair(_b, logic, "normalized Stage-1 kind number")
  _b = logic
  logic = lc_reference.resolve_unique_definite_rule_entities(logic, s1_json)
  _note_repair(_b, logic, "resolved unique definite rule entity")
  _b = logic
  logic = lc_reference.introduce_modified_generic_participants(logic, s1_json)
  _note_repair(_b, logic, "bound modified generic participant")
  _b = logic
  logic = lc_reference.coindex_dependent_rule_participants(logic, s1_json)
  _note_repair(_b, logic, "coindexed dependent rule participant")
  _b = logic
  logic = lc_reference.repair_rule_variable_scope(logic)
  _note_repair(_b, logic, "repaired rule variable scope")

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
  logic = strip_definite_tags(logic)

  # (fix 5) Deterministic repair of query packaging, after the Stage-2 sanity
  # retry has had its chance: a query package on an assertion ASU, a missing
  # query package, or an answer variable on a yes/no question.
  _b = logic
  logic = repair_question_packaging(logic, s1_json)
  _note_repair(_b, logic, "repaired question packaging")

  # (fix 7d) Rewrite opaque comparative relations ("taller than") into the
  # pipeline's degree form, so premise and question share one representation.
  _b = logic
  logic = canonicalize_comparative_relations(logic)
  _note_repair(_b, logic, "canonicalized comparative relation")

  # (fix 3) Drop isa conjuncts that only restate a Stage-1 entity `category`
  # the sentence never states.  Must run BEFORE collect_positive_isa_entities
  # below, so the pipeline's own entity-category injection sees the filtered
  # logic and applies its normal skip policy.
  _b = logic
  logic = _drop_category_isa_conjuncts(logic, s1_json)
  _note_repair(_b, logic, "dropped category-only isa")

  # (fix 7c) Unify class constants differing only in capitalization.
  _b = logic
  logic = _fold_class_name_case(logic)
  _note_repair(_b, logic, "folded class-name case")

  # Drop phantom isa-guards from query bodies: a leaked definite-description
  # presupposition (isa on a Stage-1 entity that nothing asserts) makes the
  # whole conjunctive query unprovable.  Removing the dead guard is a sound
  # simplification (see strip_phantom_query_guards).
  _b = logic
  logic = strip_phantom_query_guards(logic, _collect_stage1_entities(s1_json))
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
  s2_isa_entities = collect_positive_isa_entities(logic)
  # `noentitycat_flag`: the open-relation graph theory admits no name its own
  # translator did not write, and these clauses mint entity categories and base
  # words ("world championship") that then enter the bridge frontier as supply.
  entity_cat_clauses = ([] if _g_options.get("noentitycat_flag", False)
                        else build_entity_category_clauses(
                            s1_json, skip_entities=s2_isa_entities))

  # Build population facts by scanning the raw stage-2 input first.
  # `nopopulate_flag`: a population witness is a constant the converter mints
  # for a quantified class; in the graph theory it can ground an invented
  # bridge's own body, which is how folio-0046 proved False.
  pop_facts = ([] if _g_options.get("nopopulate_flag", False)
               else _populate_clauses(items))

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
  # (fix 4) Classes some premise quantifies over generically.  Gates the
  # bare-plural-generic question hoist, which is only sound when a generic
  # rule exists for the queried class.
  generic_classes = lc_questions.collect_generic_rule_classes(items)
  result = []
  for item in items:
    sid = str(item[1]) if (isinstance(item, list) and len(item) >= 2
                           and item[0] == "@id") else "?"
    # (8a) Per-package containment.  A single malformed package must not lose
    # the whole case: Stage 2 occasionally emits a term whose head is a number
    # or a list where an atom is expected, which raises deep inside the
    # conversion.  Screen for the malformed shape, and catch anything else, so
    # only the offending package is dropped and the rest of the problem still
    # reaches the prover.
    bad = _malformed_package_reason(item)
    if bad is not None:
      if fixes is not None:
        fixes.append("logconvert: skipped malformed package " + sid + " (" + bad + ")")
      continue
    # A rule that still concludes about an unbound Stage-2 variable is not a
    # weaker approximation: it states the conclusion about every object.  Do
    # not send that unsound clause to GK.  The warning is surfaced through the
    # normal stage_2_fixes channel rather than silently losing the package.
    if not _g_options.get("nofix_freeconclusion"):
      free_cons = lc_reference.free_rule_conclusion_vars(item)
      if free_cons:
        if fixes is not None:
          fixes.append("logconvert: rejected package " + sid
                       + " (free rule conclusion variable(s): "
                       + ", ".join(sorted(free_cons)) + ")")
        continue
    try:
      if sid != "?":
        uid_count[sid] = uid_count.get(sid, 0) + 1
        objs = convert_id_package(item, asu_index, uid_suffix=uid_count[sid],
                                   set_el_by_sid=set_el_by_sid,
                                   generic_classes=generic_classes)
      else:
        objs = convert_id_package(item, asu_index, set_el_by_sid=set_el_by_sid,
                                  generic_classes=generic_classes)
    except Exception as e:
      if fixes is not None:
        fixes.append("logconvert: skipped malformed package " + sid
                     + " (" + type(e).__name__ + ")")
      continue
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

  # (P1, -propclass) property<->class canonicalization bridges.  Runs after
  # `background` (so compound_sub clauses are present for the nominal-compound
  # promote gate) and scans the full clause list for both predicate shapes.
  if lc_encoding.current().propclass:
    result.extend(_inject_propclass_bridges(result))

  # (P3, -numtype) parse numeral strings to numbers, then materialize a type fact
  # isa(number/integer/...,N) when a guard -isa(...,N) demands it but nothing supplies it.
  if lc_encoding.current().numtype:
    _parse_numeric_literals(result)
    result.extend(_inject_number_typing(result))

  # (P3, -compasym) comparative asymmetry for strict-scalar adjectives used as
  # binary is_rel2(R,X,Y) (restores the §3.1 order axioms the flat fold drops).
  if lc_encoding.current().compasym:
    result.extend(_inject_comparative_axioms(result))

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
  if has_what_query(s1_json):
    what_pop = generate_what_population(result)
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

  # Drop reflexive locative self-loops is_rel2(in/on/...,X,X) (subject-collapse
  # artifacts that manufacture false identities under a unique-location rule, case 59).
  result = _drop_reflexive_locatives(result)

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
    result = lc_finalize.finalize_strict_clauses(
        result, preserve_generated_blocks=not _g_options.get("nofix_blockorigin"))

    # Merge per-sentence Skolem constants of the same type that are used only
    # generically ("the gym"/"the campus" re-existentialised per sentence), so
    # the rule and the question co-refer.  Runs last, on the clean strict clauses.
    result = merge_typeonly_skolems(result)

  # (8a) Final containment: drop clauses gk's reader cannot parse, so one bad
  # literal costs its own clause instead of the whole problem.  gk aborts the
  # entire input on a parse error, which turns a single Stage-2 slip into a
  # total loss (gemini FOLIO 59/60, where Stage 2 wrote ["<=", COUNT, 1]).
  result = _drop_unparseable_clauses(result, fixes)

  return result

# =========== the end ==========
