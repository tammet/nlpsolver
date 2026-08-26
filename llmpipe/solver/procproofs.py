# Proof result processing for the llm-based nlpsolver.
#
# Entry point: process_proof(proof_result, text=None, s1_json=None, logic=None, options=None)
# Called by solve.py after the theorem prover returns its raw result.
#
# This module orchestrates the post-processing of a raw prover result into a
# final answer string.  The two heavy halves of the job live in sibling
# modules:
#   proof_answer_select.py -- decides WHICH answer bindings survive (tier
#                             ranking, measure preference, tautology/leak
#                             filters, proof deduplication)
#   proof_answer_format.py -- renders the surviving bindings into English
#                             (who/what/where/when/bool formatters)
# Entity/Skolem rendering is delegated to proof_render.py; explanation
# formatting to proof_explain.py.
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

from proof_render import (
  compute_ambiguity, compute_skolem_types, entity_name, set_entity_map,
)
from proof_explain import format_explanation, build_sentence_map
from entity_map import build_entity_map

from proof_answer_select import (
  _simplify_get_world, _answer_goodness, _extract_class_names,
  _what_query_is_relational, _filter_by_best_tier,
  _filter_tautological_population_answers, _deduplicate_proofs,
  _answer_all_unbound, _prefer_measure_value_answers,
)
from proof_answer_format import (
  _extract_askvars, _is_what_query, _is_who_query, _is_prep_query,
  _resolve_what_skolem_answers, _format_prep_answers, _format_who_answers,
  _format_answers, _extract_question_property_words, _strip_question_props,
)


def _strip_una_prefix(node):
  """Recursively strip the leading `#:` UNA marker from every string."""
  if isinstance(node, str):
    return node[2:] if node.startswith("#:") else node
  if isinstance(node, list):
    return [_strip_una_prefix(x) for x in node]
  if isinstance(node, dict):
    return {k: _strip_una_prefix(v) for k, v in node.items()}
  return node


# ======== main entry point ========

def process_proof(proof_result, text=None, s1_json=None, s2_json=None, logic=None, options=None):
  """Post-process the raw prover result into a final answer string.

  Arguments:
    proof_result -- raw JSON string returned by prover.call_prover()
    text         -- the original English input (for context / fallback)
    s1_json      -- stage-1 ASU list; used to map clause names to raw sentences
    s2_json      -- stage-2 logic JSON; used for adjective extraction in entity names
    logic        -- the logic list sent to the prover (unused for now)
    options      -- dict of option flags, e.g. {"prover_explain_flag": True,
                    "show_logic_flag": True}

  Returns the final answer string.
  """
  if options is None:
    options = {}

  # Parse prover JSON
  data = _parse_result(proof_result)
  if isinstance(data, str):       # _parse_result returned an error string
    return data

  # Strip the UNA `#:` prefix from every string in the prover output before
  # the rest of the post-processing runs. The prefix is only meaningful to
  # gk's UNA mechanism inside the prover; all downstream entity-id parsing
  # (Skolem detection, type extraction, ambiguity scanning) expects the
  # bare ids it emitted in the original logic.
  data = _strip_una_prefix(data)

  # Top-level error / no answer
  if "error" in data:
    return "Error: " + str(data["error"])
  if data.get("result") != "answer found":
    return "Unknown."

  answers = data.get("answers", [])
  if not answers:
    return "Unknown."

  # Simplify $get_world($ctxt(_, W, _, _)) → W in $ans atoms before any
  # filtering. The $get_world destructor axiom (axioms_std.js §13.A) is
  # bidirectional: paramodulation can wrap any term as $get_world of a
  # synthesized $ctxt, producing redundant alternative shapes of the same
  # answer. Reducing eagerly collapses those shapes so dedup and tier
  # filtering treat them as one.
  for ans in answers:
    val = ans.get("answer")
    if isinstance(val, list):
      ans["answer"] = [_simplify_get_world(atom) for atom in val]

  # Sort: highest confidence first, shorter proofs preferred
  answers = sorted(answers, key=_answer_goodness, reverse=True)

  # For wh-questions: keep only answers in the best object-type tier
  # (concrete > Skolem > population), preserving the goodness order within tier.
  # For "what" questions: prefer population (class) answers over concrete instances.
  # Class-name leaks (the part-inheritance bg axiom `has_part(X,Y,Z) &
  # isa(X,U) -> has_part(U,Y,Z)` can unify the answer variable with a class
  # name string via a population fact) are demoted to the population tier:
  # concrete entities beat class labels, but class labels survive as a
  # fallback when no concrete entity exists (cases 236, 241, 242).  Class
  # labels that are tautological wrt the queried predicate are dropped by
  # _filter_tautological_population_answers.
  is_what = _is_what_query(logic)
  is_who  = _is_who_query(logic)
  class_names = _extract_class_names(logic)
  if is_what:
    # Relational what-query ("What is X afraid of?" -> is_rel2("afraid of",X,?))
    # wants the KIND of the relatum ("a cat"), so the population class beats the
    # incidental concrete instance ("Emily").  A classification what-query
    # ("What is an Estonian city?" -> isa/has_property of the answer var) wants
    # the concrete instance ("Tallinn"), so the has_real_concrete guard applies.
    relational = _what_query_is_relational(logic)
    answers = _filter_by_best_tier(answers, prefer_population=True,
                                   population_beats_concrete=relational,
                                   class_names=class_names)
  else:
    answers = _filter_by_best_tier(answers, class_names=class_names)
  answers = _filter_tautological_population_answers(answers, logic,
                                                   class_names=class_names)
  answers = _deduplicate_proofs(answers)

  if not answers:
    return "Unknown."

  # Build entity display-name map from stage-1 output (user's original phrasing)
  # and install it in proof_render so that entity_name() uses it globally.
  set_entity_map(build_entity_map(s1_json, s2_json))

  # Build sent_SN -> raw sentence text map from stage-1 output
  sentence_map = build_sentence_map(s1_json)

  # How many $ans arguments are actual answer variables (1 for a single-ask
  # wh-question; None means show all, e.g. yes/no or a pair question).
  askvars = _extract_askvars(logic)

  # Drop answers whose answer-variable positions are entirely unbound ?:vars.
  # The goal was proved without ever instantiating the answer variable — e.g.
  # a relationally-phrased query closed via a reflexive $theof1 axiom, binding
  # the definite description but leaving $ans uninstantiated — so the binding
  # leaks the bare variable name ("X3").  An unbound answer var is never a real
  # answer.
  answers = [a for a in answers if not _answer_all_unbound(a, askvars)]
  if not answers:
    return "Unknown."

  # Prefer the measure value over a competing definite description when the
  # measure_of -> "<noun> of" bridge surfaced both (e.g. drop "the length of
  # car A" in favour of "80000 meters").  No-op when no $list answer exists.
  answers = _prefer_measure_value_answers(answers, askvars)

  # Determine which proper-name bases are ambiguous (multiple entities share
  # the same base name, e.g. "John 1" and "John 3") so that rendering can
  # keep the distinguishing number instead of silently dropping it.
  # Scan the full logic input (all clauses sent to the prover) so that
  # entities present in the problem but absent from this specific proof path
  # are still counted.  Fall back to scanning just the answers if logic is None.
  compute_ambiguity(logic if logic is not None else answers)

  # Populate Skolem type tables from logic + proofs so that answer formatting
  # can resolve Skolem constants/functions to human-readable names.
  all_proofs = []
  for ans in answers:
    for key in ("positive proof", "negative proof"):
      p = ans.get(key)
      if isinstance(p, list):
        all_proofs.extend(p)
  compute_skolem_types(all_proofs, logic=logic)

  # For "what" queries: resolve Skolem function answers to their class.
  # E.g., $ans(["sk3","Emily 1"]) where sk3 is typed as "wolf" → $ans("$some_wolf").
  if is_what:
    _resolve_what_skolem_answers(answers)

  # Format the answer value(s)
  who_surviving = None
  if _is_prep_query(logic):
    answer_str = _format_prep_answers(answers, logic=logic)
  elif _is_who_query(logic):
    answer_str, who_surviving = _format_who_answers(answers, logic=logic)
  else:
    answer_str = _format_answers(answers, askvars=askvars)

  # For what-queries, strip property words named in the question from the
  # rendered answer. "What was deep? / the deep dent" → "the dent".
  if is_what:
    qprops = _extract_question_property_words(logic)
    if qprops:
      answer_str = _strip_question_props(answer_str, qprops)

  # Optionally append a step-by-step proof explanation
  explain     = options.get("prover_explain_flag", False)
  show_logic  = options.get("show_logic_flag", False)
  if explain:
    # For who/what queries, only explain answers that survived filtering
    explain_answers = answers
    if who_surviving is not None:
      def _atom_in_surviving(atom):
        if not (isinstance(atom, list) and len(atom) >= 2 and atom[0] == "$ans"):
          return False
        v = atom[1]
        if isinstance(v, list):
          v = entity_name(v)   # match the rendering done in _format_who_answers
        return isinstance(v, str) and v in who_surviving
      explain_answers = [a for a in answers
                         if isinstance(a.get("answer"), list)
                         and any(_atom_in_surviving(atom) for atom in a["answer"])]
    explanation = format_explanation(explain_answers, sentence_map, show_logic=show_logic, logic=logic)
    if explanation:
      answer_str = answer_str + "\n\n" + explanation

  return answer_str


# ======== JSON parsing ========

def _parse_result(proof_result):
  """Parse the raw prover JSON string. Returns a dict or an error string."""
  if not proof_result:
    return "Error: prover returned empty result."
  if isinstance(proof_result, dict):
    return proof_result
  try:
    return json.loads(proof_result)
  except Exception as e:
    return "Error: could not parse prover result as JSON: " + str(e)


# =========== the end ==========
