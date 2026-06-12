# Dynamic axiom injection passes for the post-clausification clause list.
#
# Each injector scans the clause list for trigger words / patterns and
# returns a list of new axiom clauses.  Injectors never mutate the input
# clause list — the caller appends the returned axioms.
#
# Sections:
#   - shared helpers      _collect_eligible_words, _eligible_word
#   - inject_soft_synonyms          (Tier B synonym biconditionals)
#   - inject_exclusion_axioms       (excl_a.txt mutual-exclusion groups)
#   - inject_isa_cross_group_axioms (cross-group noun mutex)
#   - inject_verb_mutex_axioms      (cross-event verb mutex, e.g. pass↔fail)
#   - inject_kinship_mutex_axioms   (gender-paired role mutex)
#   - inject_beneficiary_for_bridge (has_beneficiary ↔ "for" preposition)
#   - inject_carrier_lifts          (plate/tray/... → isa(carrier, X))
#   - inject_verb_result_state_axioms (destroy/break/... → has property "destroyed"/...)
#   - inject_world_geometry         (minimal next chain over present worlds)
#
# Gate policy:
#   - inject_soft_synonyms keeps a loose gate (a pair fires if both sides are
#     in input OR axiom_vocab) so axiom-vocab synonyms can complete chains.
#   - All other injectors below require AT LEAST ONE side of the pair (or
#     the single trigger word) to appear in the actual user input.  Axiom-
#     vocab presence alone is not enough — without an input mention, the
#     emitted axiom would only duplicate static content or sit idle.
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

from lc_ctxt import fresh_fv as _fresh_fv
from globals import options as _g_options
from lc_clausify import is_world_constant as _is_world_constant

# ======== soft synonym and exclusion axiom injection ========

from data_synonyms import SOFT_SYNONYMS
from data_exclusions import EXCLUSION_GROUPS, EXCLUSION_INDEX

# When True, only emit a soft synonym or exclusion axiom if BOTH sides of the
# pair appear in the problem (input clauses or axiom files). When False, emit
# whenever at least one side appears (original behavior — more axioms, slower).
REQUIRE_BOTH_SIDES = True


def _collect_eligible_words(result):
  """Scan all clauses and collect eligible string arguments (skip pred names,
  URLs, variables, internal markers). Returns a dict mapping lowercase word
  to the original-case form (for use in generated axioms)."""
  words = {}  # lowercase → original case

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    first = frm[0]
    # GK disjunctive clause: first element is a list → recurse each atom.
    if isinstance(first, list):
      for atom in frm:
        _walk(atom)
      return
    # Regular atom: skip position 0 (predicate name), scan positions 1+.
    for i in range(1, len(frm)):
      arg = frm[i]
      if isinstance(arg, list):
        # Skip $ctxt terms — context markers, not semantic content.
        if arg and isinstance(arg[0], str) and arg[0].startswith("$ctxt"):
          pass
        else:
          _walk(arg)
      elif isinstance(arg, str) and _eligible_word(arg):
        words[arg.lower()] = arg  # keep original case

  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      _walk(obj["@logic"])
    if "@question" in obj:
      _walk(obj["@question"])
  return words


def _eligible_word(s):
  """True if s is a candidate for synonym/exclusion matching."""
  if not s:
    return False
  if s.startswith("http"):
    return False
  if s.startswith("?:"):
    return False
  if s.startswith("$"):
    return False
  if s.startswith("@"):
    return False
  return True


# Axiom templates by POS.
# Adjectives use "has property" — normalize_gradable_predicates() promotes
# to "has degree property" afterwards if the word is in GRADABLE_PROPS.
# A single free context variable "?:Ctxt" is used (not the expanded
# ["$ctxt",T,W,L,K] form) — it unifies with any context term.
_SOFT_SYN_TEMPLATES = {
    "a": lambda w, o, ct: [
        ["-has property", w, "?:X", ct],
        ["has property", o, "?:X", ct]
    ],
    "n": lambda w, o, ct: [
        ["-isa", w, "?:X"],
        ["isa", o, "?:X"]
    ],
    "v": lambda w, o, ct: [
        ["-has type", "?:E", w, ct],
        ["has type", "?:E", o, ct]
    ],
}

# Verb soft-synonym taxonomy. These are GENERAL (hypernym) verbs. When a verb
# pair has EXACTLY ONE side here, only the specific->general direction is
# emitted ("a fly/run/drive event IS a going event", not the reverse). This
# prevents invalid transitive chains like run->go->fly that coerced an
# unrelated event into "fly" and tripped the baby-bird ¬fly rule (case 1451).
_GENERAL_VERBS = frozenset({"go", "give", "have", "put", "present"})

# Verb soft-synonym pairs that are simply wrong (polysemy / POS confusion).
# Suppressed entirely — no axiom emitted in either direction.
_BLOCKED_VERB_PAIRS = frozenset({
    frozenset({"go", "live"}), frozenset({"go", "work"}), frozenset({"go", "sit"}),
    frozenset({"chase", "dog"}), frozenset({"dog", "tail"}), frozenset({"say", "have"}),
    frozenset({"be", "present"}), frozenset({"make", "pass"}), frozenset({"come", "near"}),
    frozenset({"break", "give"}), frozenset({"put", "sit"}), frozenset({"give", "leave"}),
})


def inject_soft_synonyms(result, axiom_vocab=frozenset()):
  """Scan clause list for words with soft synonym pairs; emit biconditional
  axiom clauses for each relevant pair. Returns list of new clause dicts.

  When REQUIRE_BOTH_SIDES is True, only emits if the other side of the pair
  also appears in the input clauses or axiom_vocab.
  """
  words = _collect_eligible_words(result)  # {lowercase: original_case}
  if not words:
    return []

  all_known = set(words) | axiom_vocab if REQUIRE_BOTH_SIDES else None

  axioms = []
  emitted = set()  # frozenset pairs to avoid duplicates

  for lc_word, orig_word in words.items():
    if lc_word not in SOFT_SYNONYMS:
      continue
    for other, score, pos in SOFT_SYNONYMS[lc_word]:
      if all_known is not None and other not in all_known:
        continue
      pair_key = frozenset((lc_word, other))
      if pair_key in emitted:
        continue
      emitted.add(pair_key)
      template = _SOFT_SYN_TEMPLATES.get(pos)
      if not template:
        continue
      # Suppress known-bad verb pairs entirely (no axiom in either direction).
      if pair_key in _BLOCKED_VERB_PAIRS:
        continue
      # Verb taxonomy: when exactly one side is a general (hypernym) verb, emit
      # only the specific->general implication and drop the reverse.
      if pos == "v" and len(pair_key & _GENERAL_VERBS) == 1:
        if other in _GENERAL_VERBS:        # orig_word is specific, other general
          clause = template(orig_word, other, _fresh_fv())
        else:                              # orig_word is general, other specific
          clause = template(other, orig_word, _fresh_fv())
        axioms.append({"@name": "frm_syn",
                        "@logic": clause,
                        "@confidence": score})
        continue
      ct = _fresh_fv()
      clause1 = template(orig_word, other, ct)
      axioms.append({"@name": "frm_syn",
                      "@logic": clause1,
                      "@confidence": score})
      ct2 = _fresh_fv()
      clause2 = template(other, orig_word, ct2)
      axioms.append({"@name": "frm_syn",
                      "@logic": clause2,
                      "@confidence": score})
  return axioms


# Groups whose members appear as is_rel2 target arguments (temporal/location)
# rather than has_property adjective atoms.
_IS_REL2_EXCL_GROUPS = frozenset({
    "MONTH", "DAY_OF_WEEK", "SEASON",
})

# Groups whose members appear as the RELATION at is_rel2 argument 1
# (spatial / temporal-order prepositions like behind, above, before).
# Emitted axiom shape:
#   [-is_rel2(w1,?:X,?:Y,ct), -is_rel2(w2,?:X,?:Y,ct)]
_IS_REL2_PREP_GROUPS = frozenset({
    "SPATIAL_SAGITTAL",
    "SPATIAL_VERTICAL",
    "SPATIAL_VERTICAL_OVER_UNDER",
    "SPATIAL_CONTAINMENT",
    "SPATIAL_LATERAL",
    "TEMPORAL_ORDER",
})

# Groups whose members appear as the RELATION at has_degree_rel2 argument 1
# (degree-based binary relations like near, far_from).
# Emitted per pair: two asymmetric axioms — positive side any-degree,
# antonym side "none" intensity, shared RELCLASS:
#   [-has_degree_rel2(W1, ?:X, ?:Y, ?:D, ?:RC, ct),
#    -has_degree_rel2(W2, ?:X, ?:Y, "none", ?:RC, ct)]
#   [-has_degree_rel2(W2, ?:X, ?:Y, ?:D, ?:RC, ct),
#    -has_degree_rel2(W1, ?:X, ?:Y, "none", ?:RC, ct)]
# The existing high→none / low→none intensity bridges in axioms_std.js §9
# then propagate the "none" negation to all intensities via contrapositive.
_HAS_DEGREE_REL2_PREP_GROUPS = frozenset({
    "PROXIMITY",
})

# Groups whose mutual-exclusion axioms are emitted statically in
# axioms_std.js §7e. These first-class preposition predicates appear in the
# standard ontology (subsumption rules in §7c/7d), so the exclusions hold
# universally — dynamic injection would emit equivalent clauses on every
# problem (both sides are in axiom_vocab), but placing them statically
# pairs them with the related subsumption rules. Skipped here to avoid
# duplication.
_STATIC_PREP_EXCL_GROUPS = frozenset({
    "SPATIAL_VERTICAL",
    "SPATIAL_VERTICAL_OVER_UNDER",
    "SPATIAL_SAGITTAL",
    "SPATIAL_CONTAINMENT",
    "SPATIAL_LATERAL",
    "TEMPORAL_ORDER",
    "PROXIMITY",
})

# Noun-mutex groups whose members appear as ARG-1 of isa atoms
# (concept names like "table", "floor", "car"). Emit cross-entity
# inequality clauses:
#   [-isa w1 ?:X ?:Ctxt1, -isa w2 ?:Y ?:Ctxt2, -=(?:X, ?:Y)]
# Captures both same-entity ("X is not both a table and a floor")
# and different-entity ("a table-instance and a floor-instance are
# distinct entities") via a single clause shape — when X=Y, the
# inequality is unsatisfiable and the clause collapses to standard
# strict mutex on the same entity.
_ISA_EXCL_GROUPS = frozenset({
    "NOUN_TOP_LEVEL",
    "NOUN_FURNITURE_FIXTURE",
    "NOUN_VEHICLE",
    "NOUN_ANIMAL_KIND",
    "NOUN_BODY_OF_WATER",
    "NOUN_TERRAIN",
    "NOUN_CELESTIAL",
    "NOUN_BUILDING",
    "NOUN_GARMENT",
    "NOUN_TOOL",
    "NOUN_FRUIT",
})

# NOUN_TOP_LEVEL words are HYPERNYM categories that SUBSUME the concrete
# noun groups (a store is a place AND an artifact; a bird is an animal).
# Cross-group mutex between such a hypernym and a word from a group it
# subsumes is unsound, so inject_isa_cross_group_axioms skips those pairs.
# Map: top-level word -> set of concrete groups it subsumes.  Pairs NOT in
# this map stay mutex (place x car, animal x vehicle, building x vehicle...).
_TOP_LEVEL_SUBSUMES = {
    "artifact": frozenset({"NOUN_BUILDING", "NOUN_VEHICLE",
                           "NOUN_FURNITURE_FIXTURE", "NOUN_GARMENT",
                           "NOUN_TOOL"}),
    "place":    frozenset({"NOUN_BUILDING", "NOUN_BODY_OF_WATER",
                           "NOUN_TERRAIN"}),
    "animal":   frozenset({"NOUN_ANIMAL_KIND"}),
    "plant":    frozenset({"NOUN_FRUIT"}),
}


def inject_exclusion_axioms(result, axiom_vocab=frozenset()):
  """Scan clause list for words in exclusion groups; emit pairwise mutual-
  exclusion clauses for groups with 2+ members present. Returns list of
  new clause dicts.

  Each emitted pair requires at least ONE side in the actual input
  (axiom_vocab membership alone is not enough — the other side may come
  from axiom_vocab).
  """
  words = _collect_eligible_words(result)
  if not words:
    return []

  input_lc = set(words)
  all_known = input_lc | axiom_vocab if REQUIRE_BOTH_SIDES else input_lc

  # Find which groups have 2+ members present in all_known.
  group_members = {}  # gid → set of original-case words
  for lc_word in all_known:
    if lc_word not in EXCLUSION_INDEX:
      continue
    for gid in EXCLUSION_INDEX[lc_word]:
      if gid in _STATIC_PREP_EXCL_GROUPS:
        continue
      if gid not in group_members:
        group_members[gid] = set()
      # Use original case from input if available, else lowercase.
      group_members[gid].add(words.get(lc_word, lc_word))

  axioms = []
  for gid, present in group_members.items():
    if len(present) < 2:
      continue
    ginfo = EXCLUSION_GROUPS.get(gid)
    if not ginfo:
      continue
    score = ginfo["score"]
    is_rel2_group = gid in _IS_REL2_EXCL_GROUPS
    is_rel2_prep_group = gid in _IS_REL2_PREP_GROUPS
    has_degree_rel2_prep_group = gid in _HAS_DEGREE_REL2_PREP_GROUPS
    isa_group = gid in _ISA_EXCL_GROUPS
    present_list = sorted(present)
    for i in range(len(present_list)):
      for j in range(i + 1, len(present_list)):
        w1, w2 = present_list[i], present_list[j]
        # Require at least one side to be in the actual input.  Both-from-
        # axiom-vocab pairs add no value (they cannot fire on a proof that
        # mentions neither word).
        if w1.lower() not in input_lc and w2.lower() not in input_lc:
          continue
        if isa_group:
          # Noun mutex within the same group. isa is 3-arg in this pipeline
          # (no Ctxt slot), so axioms use 3-position atoms.
          # Emit two clauses:
          #   (a) Same-entity strict mutex (shortcut):
          #         [¬isa w1 ?:X, ¬isa w2 ?:X]
          #   (b) Cross-entity inequality (general case):
          #         [¬isa w1 ?:X, ¬isa w2 ?:Y, ¬=(?:X, ?:Y)]
          # (b) logically subsumes (a) (collapses when X=Y), but emitting
          # the 2-literal form too gives the prover a directly-applicable
          # shortcut that doesn't require equality reasoning.
          axioms.append({"@name": "frm_excl_isa",
                          "@logic": [
                              ["-isa", w1, "?:X"],
                              ["-isa", w2, "?:X"],
                          ],
                          "@confidence": score})
          axioms.append({"@name": "frm_excl_isa",
                          "@logic": [
                              ["-isa", w1, "?:X"],
                              ["-isa", w2, "?:Y"],
                              ["-=", "?:X", "?:Y"],
                          ],
                          "@confidence": score})
        elif has_degree_rel2_prep_group:
          # Preposition at has_degree_rel2 arg 1. Two asymmetric axioms per
          # pair: positive side any-degree (?:D), antonym side "none"
          # intensity, shared ?:RC. Intensity bridges (high→none, low→none)
          # in axioms_std.js §9 propagate the "none" negation to all
          # intensities via contrapositive.
          for (left, right) in ((w1, w2), (w2, w1)):
            d = _fresh_fv()
            rc = _fresh_fv()
            ct = _fresh_fv()
            clause = [
                ["-has degree rel2", left,  "?:X", "?:Y", d,      rc, ct],
                ["-has degree rel2", right, "?:X", "?:Y", "none", rc, ct],
            ]
            axioms.append({"@name": "frm_excl",
                            "@logic": clause,
                            "@confidence": score})
        elif is_rel2_prep_group:
          # Preposition at is_rel2 arg 1; two free entity variables.
          ct = _fresh_fv()
          clause = [
              ["-is rel2", w1, "?:X", "?:Y", ct],
              ["-is rel2", w2, "?:X", "?:Y", ct],
          ]
          axioms.append({"@name": "frm_excl",
                          "@logic": clause,
                          "@confidence": score})
        elif is_rel2_group:
          ct = _fresh_fv()
          clause = [
              ["-is rel2", "?:R", "?:X", w1, ct],
              ["-is rel2", "?:R", "?:X", w2, ct],
          ]
          axioms.append({"@name": "frm_excl",
                          "@logic": clause,
                          "@confidence": score})
        elif ginfo["needs_blocker"]:
          # Two defeasible axioms per pair, each blockable by the other side.
          # ¬w1(X,CT) ∨ ¬w2(X,CT) ∨ $block(0, w2(X,CT))
          ct1 = _fresh_fv()
          axioms.append({"@name": "frm_excl",
                          "@logic": [
                              ["-has property", w1, "?:X", ct1],
                              ["-has property", w2, "?:X", ct1],
                              ["$block", 0, ["has property", w2, "?:X", ct1]],
                          ],
                          "@confidence": score})
          # ¬w1(X,CT) ∨ ¬w2(X,CT) ∨ $block(0, w1(X,CT))
          ct2 = _fresh_fv()
          axioms.append({"@name": "frm_excl",
                          "@logic": [
                              ["-has property", w1, "?:X", ct2],
                              ["-has property", w2, "?:X", ct2],
                              ["$block", 0, ["has property", w1, "?:X", ct2]],
                          ],
                          "@confidence": score})
        else:
          # Hard exclusion: ¬w1(X,CT) ∨ ¬w2(X,CT)
          ct = _fresh_fv()
          clause = [
              ["-has property", w1, "?:X", ct],
              ["-has property", w2, "?:X", ct],
          ]
          axioms.append({"@name": "frm_excl",
                          "@logic": clause,
                          "@confidence": score})
  return axioms


def inject_isa_cross_group_axioms(result, axiom_vocab=frozenset()):
  """Layer 2 noun mutex: cross-group cross-entity inequality.

  For every pair (w1, w2) where w1 belongs to a group G1 in
  _ISA_EXCL_GROUPS, w2 belongs to a different group G2 in
  _ISA_EXCL_GROUPS, and both w1 and w2 are present in input clauses or
  axiom_vocab, emit:

      [-isa w1 ?:X ?:Ct1, -isa w2 ?:Y ?:Ct2, -=(?:X, ?:Y)]

  Same shape as the within-group axiom emitted by
  inject_exclusion_axioms (Layer 1) — when X=Y the inequality forces
  strict mutex; when X != Y the clause asserts entity distinctness.

  Both layers are gated by REQUIRE_BOTH_SIDES via _eligible_word /
  axiom_vocab membership.
  """
  words = _collect_eligible_words(result)
  input_lc = set(words)
  all_known = input_lc | axiom_vocab if REQUIRE_BOTH_SIDES else input_lc

  # Build word -> group_id (only for _ISA_EXCL_GROUPS entries)
  word_to_group = {}
  for gid in _ISA_EXCL_GROUPS:
    ginfo = EXCLUSION_GROUPS.get(gid)
    if not ginfo:
      continue
    for w in ginfo["words"]:
      if w not in word_to_group:
        word_to_group[w] = gid

  # Eligible words: in some _ISA_EXCL_GROUPS group AND in all_known.
  eligible = sorted(w for w in word_to_group if w in all_known)
  if len(eligible) < 2:
    return []

  axioms = []
  emitted_pairs = set()
  # Use the first group's score as representative (all are 0.95 in our
  # current data; future groups should keep parity).
  default_score = 0.95
  for i in range(len(eligible)):
    for j in range(i + 1, len(eligible)):
      w1, w2 = eligible[i], eligible[j]
      g1, g2 = word_to_group[w1], word_to_group[w2]
      if g1 == g2:
        continue                      # within-group handled by Layer 1
      # Skip hypernym/hyponym pairs: a NOUN_TOP_LEVEL word that subsumes the
      # other side's group is NOT mutex with it (store IS a place/artifact).
      if g2 in _TOP_LEVEL_SUBSUMES.get(w1, ()):
        continue
      if g1 in _TOP_LEVEL_SUBSUMES.get(w2, ()):
        continue
      # Require at least one side to be in the actual input.
      if w1 not in input_lc and w2 not in input_lc:
        continue
      pair = (w1, w2) if w1 < w2 else (w2, w1)
      if pair in emitted_pairs:
        continue
      emitted_pairs.add(pair)
      score = EXCLUSION_GROUPS.get(g1, {}).get("score", default_score)
      # Same shape as Layer 1 (within-group). Emit both same-entity
      # shortcut and cross-entity inequality.
      axioms.append({"@name": "frm_excl_isa_xg",
                      "@logic": [
                          ["-isa", w1, "?:X"],
                          ["-isa", w2, "?:X"],
                      ],
                      "@confidence": score})
      axioms.append({"@name": "frm_excl_isa_xg",
                      "@logic": [
                          ["-isa", w1, "?:X"],
                          ["-isa", w2, "?:Y"],
                          ["-=", "?:X", "?:Y"],
                      ],
                      "@confidence": score})
  return axioms


# Verb-event defeasible mutex pairs. For each (v1, v2) pair, when both
# verbs appear in the input (or axiom vocabulary), inject a defeasible
# cross-event mutex saying that two events sharing actor + target cannot
# defeasibly have these mutually-incompatible types in the same context.
# Verb antonyms cannot be folded into ANTONYMS (verb antonyms are mostly
# perspective inversions, not logical opposites — see mkdata/CLAUDE.md).
# The mutex injector handles the small set where polarity-style mutex IS
# semantically appropriate (pass/fail, succeed/fail, ...).
_VERB_MUTEX_PAIRS = [
    ("pass", "fail"),
]


def inject_verb_mutex_axioms(result, axiom_vocab=frozenset()):
  """Scan clause list for verbs in _VERB_MUTEX_PAIRS; for each pair where
  BOTH verbs appear, emit two symmetric defeasible cross-event mutex
  axioms.

  Shape (one direction):
    [-has type   E1 v1 Ct,
     -has actor  E1 X  Ct,
     -has target E1 Y  Ct,
     -has type   E2 v2 Ct,
     -has actor  E2 X  Ct,
     -has target E2 Y  Ct,
     $block(0, has type E2 v2 Ct)]

  Two events sharing actor + target + context cannot have these
  mutually-incompatible types unless the right-side type is independently
  supported (defeated by $block).
  """
  words = _collect_eligible_words(result)
  if not words:
    return []
  input_lc = set(words)
  all_known = input_lc | axiom_vocab if REQUIRE_BOTH_SIDES else input_lc
  axioms = []
  for v1, v2 in _VERB_MUTEX_PAIRS:
    if v1 not in all_known or v2 not in all_known:
      continue
    # Require at least one side in the actual input.
    if v1 not in input_lc and v2 not in input_lc:
      continue
    for (left, right) in ((v1, v2), (v2, v1)):
      ct = _fresh_fv()
      clause = [
          ["-has type",   "?:E1", left,  ct],
          ["-has actor",  "?:E1", "?:Ag", ct],
          ["-has target", "?:E1", "?:Tg", ct],
          ["-has type",   "?:E2", right, ct],
          ["-has actor",  "?:E2", "?:Ag", ct],
          ["-has target", "?:E2", "?:Tg", ct],
          ["$block", 0, ["has type", "?:E2", right, ct]],
      ]
      axioms.append({"@name": "frm_verb_excl",
                      "@logic": clause,
                      "@confidence": 0.85})
  return axioms


# Gender-paired role mutex pairs (kinship + royalty). For each pair (a, b),
# when both terms appear in the input or axiom_vocab, emit hard
# mutual-exclusion clauses both at the noun-category level
# (-isa a X ∨ -isa b X) and the relation level (-is rel2 "a of" X Y ∨
# -is rel2 "b of" X Y). These terms are in BLOCKED_ANTONYM_WORDS
# (mkdata/build_solver_data.py) — gendered role pairs aren't true antonyms
# (flipping "Sara is a sister" to "Sara is not a brother" loses the positive
# type info), so the polarity-flip path is blocked and we use this
# symmetric mutex instead. Pairs not used in the current test corpus are
# included as low-cost future-proofing — the dynamic injector only emits a
# pair when BOTH sides appear, so unused pairs cost nothing at runtime.
_KINSHIP_MUTEX_PAIRS = (
    # Core kinship
    ("sister",        "brother"),
    ("daughter",      "son"),
    ("mother",        "father"),
    ("wife",          "husband"),
    ("aunt",          "uncle"),
    ("niece",         "nephew"),
    ("grandmother",   "grandfather"),
    ("granddaughter", "grandson"),
    # Step / god relations
    ("stepmother",    "stepfather"),
    ("stepdaughter",  "stepson"),
    ("stepsister",    "stepbrother"),
    ("godmother",     "godfather"),
    # Status
    ("widow",         "widower"),
    ("bride",         "groom"),
    # Royalty (analogous gender-paired mutex)
    ("queen",         "king"),
    ("princess",      "prince"),
)


def inject_kinship_mutex_axioms(result, axiom_vocab=frozenset()):
  """For each gender-paired role pair where both terms appear in the input
  or axiom_vocab, emit hard mutex clauses for both the noun category and
  the "X of" relation.

  Closes case 79 ("Sara, the sister of Mike, left. Sara is the brother of
  Mike?" — expected False).
  """
  words = _collect_eligible_words(result)
  input_lc = set(words)
  all_known = input_lc | axiom_vocab
  axioms = []
  for a, b in _KINSHIP_MUTEX_PAIRS:
    # Accept either the bare role noun ("sister") OR the relation form
    # ("sister of") — gpt's Stage-2 sometimes only emits the relation
    # form for definite-description questions ("Is Sara the brother of
    # Mike?"), which would otherwise fail to trigger kinship mutex.
    a_present = (a in all_known) or ((a + " of") in all_known)
    b_present = (b in all_known) or ((b + " of") in all_known)
    if not (a_present and b_present):
      continue
    # Require at least one side in the actual input.
    a_in_input = (a in input_lc) or ((a + " of") in input_lc)
    b_in_input = (b in input_lc) or ((b + " of") in input_lc)
    if not (a_in_input or b_in_input):
      continue
    # Category-level mutex: isa atoms are 3-arg, no $ctxt.
    axioms.append({"@name": "frm_kin_excl",
                   "@logic": [["-isa", a, "?:X"], ["-isa", b, "?:X"]]})
    # Relation-level mutex: is rel2 "<a> of" / "<b> of" with shared $ctxt.
    ct = _fresh_fv()
    axioms.append({"@name": "frm_kin_excl",
                   "@logic": [
                       ["-is rel2", a + " of", "?:X", "?:Y", ct],
                       ["-is rel2", b + " of", "?:X", "?:Y", ct],
                   ]})
    # Relation→category bridges: `is rel2 "<role> of" X Y CT → isa(<role>, X)`.
    # Required when the relation form is the only encoding emitted (e.g. gpt's
    # case 79 has `is rel2 brother of #:Sara #:Mike` but no `isa(brother, ...)`
    # for any entity, so the isa-mutex above alone cannot fire).  These
    # bridges feed both the category mutex and any other isa-keyed reasoning.
    ct_a = _fresh_fv()
    ct_b = _fresh_fv()
    axioms.append({"@name": "frm_kin_excl",
                   "@logic": [
                       ["-is rel2", a + " of", "?:X", "?:Y", ct_a],
                       ["isa", a, "?:X"],
                   ]})
    axioms.append({"@name": "frm_kin_excl",
                   "@logic": [
                       ["-is rel2", b + " of", "?:X", "?:Y", ct_b],
                       ["isa", b, "?:X"],
                   ]})
  return axioms


# Containment-bridge injector removed: `axioms_std.js` already includes the
# static `contains ↔ in` biconditional axioms, so dynamic emission only
# duplicates them.  "filled with" / "containing" are handled at the
# axiom-file level (or via paraphrase normalization upstream).


# ======== beneficiary → "for" preposition bridge ========


def _has_predicates_ben_and_for(result):
  """True iff input clauses contain BOTH a ["has beneficiary", ...] atom
  AND an ["is rel2", "for", ...] atom (positive or negated)."""
  saw_ben = [False]
  saw_for = [False]

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    first = frm[0]
    if isinstance(first, list):
      for atom in frm:
        _walk(atom)
      return
    if isinstance(first, str):
      if first in ("has beneficiary", "-has beneficiary"):
        saw_ben[0] = True
      elif (first in ("is rel2", "-is rel2")
            and len(frm) >= 2 and frm[1] == "for"):
        saw_for[0] = True
    for a in frm[1:]:
      if isinstance(a, list):
        _walk(a)

  for obj in result:
    if isinstance(obj, dict):
      if "@logic" in obj:
        _walk(obj["@logic"])
      if "@question" in obj:
        _walk(obj["@question"])
    if saw_ben[0] and saw_for[0]:
      return True
  return saw_ben[0] and saw_for[0]


def inject_beneficiary_for_bridge(result):
  """If the input clauses use both ["has beneficiary", ...] (event-style
  beneficiary role) and ["is rel2", "for", ...] (preposition-relation
  shape), emit a bridge axiom so event-encoded assertions satisfy
  for-preposition queries (and vice versa).

  Shape:
    [-has target ?:E ?:T ?:Ct,
     -has beneficiary ?:E ?:B ?:Ct,
     is rel2 "for" ?:T ?:B ?:Ct]

  Closes case 169 on gpt + deepseek — "The chef cooked a meal for the
  guests. Who was the meal for?" — where the assertion uses
  has_beneficiary but the query uses the for-relation.
  """
  if not _has_predicates_ben_and_for(result):
    return []
  ct = _fresh_fv()
  clause = [
      ["-has target", "?:E", "?:T", ct],
      ["-has beneficiary", "?:E", "?:B", ct],
      ["is rel2", "for", "?:T", "?:B", ct],
  ]
  return [{"@name": "frm_ben_for", "@logic": clause}]


# ======== measure_of -> "<noun> of" relational bridge ========

def inject_measure_relation_bridges(result):
  """Dynamic measure_of -> "<noun> of" relational bridge.

  For each measure noun N that appears in the problem BOTH as the first
  argument of a $measure_of term AND as the relation "N of" of an is_rel2
  atom, emit one bridge axiom:

    [ ["-=", ["$measure_of", N, "?:S", "?:W"], "?:V"],
      ["is rel2", N + " of", "?:V", "?:S", "?:Ctxt"] ]

  Read: if the N of S equals V, then V is the "N of" S relationally
  (E1=value, E2=subject — matching how stage-2 emits is_rel2 "<noun> of").
  This lets a relationally-phrased measure question (ask X: is_rel2 "N of" X S)
  reach the measure value V instead of only the definite description.

  Replaces the former static per-noun block in axioms_std.js.  Gated on BOTH
  forms being present so the bridge is added only when it can actually connect
  a measure fact to a relational query — and generalises to any measure noun
  (length / price / weight / height / ...), not a hard-coded list.
  """
  measure_nouns = set()  # N from ["$measure_of", N, ...]
  rel_nouns = set()      # N from ["is rel2", "N of", ...]

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    if isinstance(frm[0], list):
      for atom in frm:
        _walk(atom)
      return
    head = frm[0]
    if head == "$measure_of" and len(frm) >= 2 and isinstance(frm[1], str):
      measure_nouns.add(frm[1])
    elif head in ("is rel2", "-is rel2") and len(frm) >= 2 \
            and isinstance(frm[1], str) and frm[1].endswith(" of"):
      rel_nouns.add(frm[1][:-len(" of")])
    for arg in frm[1:]:
      if isinstance(arg, list):
        _walk(arg)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      _walk(obj["@logic"])
    if "@question" in obj:
      _walk(obj["@question"])

  axioms = []
  for noun in sorted(measure_nouns & rel_nouns):
    clause = [
        ["-=", ["$measure_of", noun, "?:S", "?:W"], "?:V"],
        ["is rel2", noun + " of", "?:V", "?:S", "?:Ctxt"],
    ]
    axioms.append({"@name": "frm_measure_rel_bridge", "@logic": clause})
  return axioms


# ======== negative implicative bridge (refuse/decline) ========

# Negative implicative verbs: "X refused/declined to V (Y)" entails X did NOT
# actually V (Y).
_NEG_IMPLICATIVE_VERBS = ("refuse", "decline")

# "forget to V" is also negative-implicative ("Eve forgot to lock the door" ->
# Eve did NOT lock it), but "forget" is AMBIGUOUS: "forget THAT P" is FACTIVE
# (-> P is true).  So the forget bridge is gated on the content event sharing
# the forgetter's actor (same-subject control = "forget TO V"), which excludes
# the common "X forgot that [OTHER] V'd" factive reading.  refuse/decline are
# inherently same-subject so they need no such gate.
_NEG_IMPLICATIVE_CONTROL_VERBS = ("forget",)


def inject_negative_implicative_bridges(result):
  """Dynamic negative-implicative bridge for refuse/decline (and forget-to).

  For each verb in _NEG_IMPLICATIVE_VERBS present in the input, emit:

    refuse(E1) & has_content(E1,E2) & E2 = V(X,Y)
      ->  no ACTUAL event E3 = V(X,Y)

  so "Tom refused to eat the soup. Tom ate the soup?" proves False rather than
  Unknown (the refused content event carries no actuality, so the query for an
  actual eat fails; this constraint additionally forbids any other actual eat
  of the same actor/target).  Mirror of the §5.2 factive bridge, negative
  direction.  Replaces the former static axioms_std.js §5.2b block; emitted
  only when "refuse"/"decline" actually appears (case 1597).

  For _NEG_IMPLICATIVE_CONTROL_VERBS ("forget") the same clause is emitted with
  an extra constraint tying E1's actor to the content actor X (same-subject
  control), so it fires on "forget to V" but not on the factive "forget that
  [other] V'd" (case 1599).
  """
  words = _collect_eligible_words(result)
  axioms = []
  for verb in _NEG_IMPLICATIVE_VERBS:
    if verb not in words:
      continue
    clause = [
        ["-has type",    "?:E1", verb,  "?:Ct1"],
        ["-has content", "?:E1", "?:E2"],
        ["-has type",    "?:E2", "?:V", "?:Ct2"],
        ["-has actor",   "?:E2", "?:X", "?:Ct2"],
        ["-has target",  "?:E2", "?:Y", "?:Ct2"],
        ["-has type",    "?:E3", "?:V", "?:Ct3"],
        ["-has actor",   "?:E3", "?:X", "?:Ct3"],
        ["-has target",  "?:E3", "?:Y", "?:Ct3"],
        ["-actuality",   "?:E3"],
    ]
    axioms.append({"@name": "frm_neg_implicative", "@logic": clause})
  for verb in _NEG_IMPLICATIVE_CONTROL_VERBS:
    if verb not in words:
      continue
    clause = [
        ["-has type",    "?:E1", verb,  "?:Ct1"],
        ["-has actor",   "?:E1", "?:X", "?:Ct1"],   # same-subject control
        ["-has content", "?:E1", "?:E2"],
        ["-has type",    "?:E2", "?:V", "?:Ct2"],
        ["-has actor",   "?:E2", "?:X", "?:Ct2"],
        ["-has target",  "?:E2", "?:Y", "?:Ct2"],
        ["-has type",    "?:E3", "?:V", "?:Ct3"],
        ["-has actor",   "?:E3", "?:X", "?:Ct3"],
        ["-has target",  "?:E3", "?:Y", "?:Ct3"],
        ["-actuality",   "?:E3"],
    ]
    axioms.append({"@name": "frm_neg_implicative", "@logic": clause})
  return axioms


# ======== perception-factive bridge (hear/see/watch …) ========
#
# Direct perception is FACTIVE: "X was heard/seen to V" (or "X saw Y do V")
# entails V actually happened — you can only perceive an ACTUAL event. Some
# LLMs (gpt/deepseek case 1603, claude case 1601) encode it as a two-event
# reification (hear/see E1 + has_content E2 = the perceived event), and the
# perceived content event carries no actuality, so "Mary sang?" / "John
# entered?" is only Unknown instead of True. This is the positive counterpart
# of the §5.2 assertive factive bridge, but keyed on the PERCEPTION verb (no
# speech_act classifier) rather than say/claim/…
_PERCEPTION_FACTIVE_VERBS = ("hear", "see", "watch", "observe", "notice",
                             "witness")


def inject_perception_factive_bridges(result):
  """For each perception verb present, emit a defeasible bridge making the
  perceived content event actual:  perceive(E1) ∧ has_content(E1,E2) →
  actuality(E2), with a $block escape. Fires only on perception OF AN EVENT
  (has_content), not perception of an object (has_target). See cases
  1601/1603."""
  words = _collect_eligible_words(result)
  axioms = []
  for verb in _PERCEPTION_FACTIVE_VERBS:
    if verb not in words:
      continue
    clause = [
        ["-has type",    "?:E1", verb, "?:Ct1"],
        ["-has content", "?:E1", "?:E2"],
        ["actuality",    "?:E2"],
        ["$block", 0, ["$not", ["actuality", "?:E2"]]],
    ]
    axioms.append({"@name": "frm_perception_factive",
                    "@logic": clause,
                    "@confidence": 0.95})
  return axioms


# ======== carrier vocabulary lift ========

# Carrier nouns: small movable surfaces that "pass through" the on-support
# relation. The carrier-transparency axiom (axioms_std.js §7g) consumes
# `isa(carrier, X, Ctxt)` to derive on(X, S) from on(X, C) + on(C, S).
# Each lift here is emitted only when its noun appears in the input clauses
# or axiom_vocab (mirrors REQUIRE_BOTH_SIDES from soft synonyms).
_CARRIER_NOUNS = frozenset({
    "plate", "tray", "saucer", "dish",
    "newspaper", "napkin", "tablecloth",
    "mat", "rug", "carpet",
})


def inject_carrier_lifts(result, axiom_vocab=frozenset()):
  """Scan clause list for carrier nouns; emit one isa-to-carrier
  lifting clause per noun present in the input.

  Shape (per noun N):
    [-isa N ?:X ?:Ctxt, isa "carrier" ?:X ?:Ctxt]

  Gated on input presence only — without a carrier-noun mention in the
  problem there is no Skolem to lift, so axiom_vocab presence alone
  would emit dead axioms.  ``axiom_vocab`` is kept in the signature for
  call-site uniformity.
  """
  del axiom_vocab  # unused; see docstring
  words = _collect_eligible_words(result)
  axioms = []
  for noun in _CARRIER_NOUNS:
    if noun not in words:
      continue
    ct = _fresh_fv()
    clause = [
        ["-isa", noun, "?:X", ct],
        ["isa", "carrier", "?:X", ct],
    ]
    axioms.append({"@name": "frm_carrier_lift", "@logic": clause})
  return axioms


# ======== verb-result-state bridges ========

# Verb → past-participle result-state property pairs. For each pair where
# the verb appears in the input clauses (or axiom_vocab), inject a
# defeasible bridge: if event E has type V and target X, and next(W, W2)
# in E's context, then X has property <past_participle> at present W2.
# Defeasible at 0.9 with $block(¬property@W2) — explicit ¬property defeats.
#
# Conservative initial set — verbs whose past-participle is unambiguously
# a stable result property.  Ambiguous cases (start/started — process vs
# state, leave/left — direction vs state) deliberately omitted.
_VERB_RESULT_STATES = (
    ("destroy",  "destroyed"),
    ("break",    "broken"),
    ("damage",   "damaged"),
    ("complete", "completed"),
    ("kill",     "killed"),
    ("repair",   "repaired"),
    # (finish, finished) is covered by a static axiom in axioms_std.js;
    # adding it here would duplicate that.
)


def inject_verb_result_state_axioms(result, axiom_vocab=frozenset()):
  """For each (verb, property) pair in _VERB_RESULT_STATES whose verb
  appears in the actual input clauses, emit a defeasible result-state
  bridge axiom.

  Shape:
    [-has type E V Ct, -has target E X CtFull, -next W W2,
     has property <prop> X CtNext,
     $block(0, $not(has property <prop> X CtNext))]
  where CtFull is the full $ctxt and W comes from its world slot;
  CtNext is the present-tense $ctxt at W2 with the same L/K vars.

  Gated on input presence only.  ``axiom_vocab`` is kept in the
  signature for call-site uniformity.

  Closes case 156 ("The city was destroyed. Is the city destroyed?")
  and case 157 ("...Is the city intact?") via the destroy → destroyed
  result-state plus the destroyed/intact mutex (data_exclusions.py).
  """
  del axiom_vocab  # unused; see docstring
  words = _collect_eligible_words(result)
  slight = _g_options.get("slightcoarse_flag", False)
  axioms = []
  for verb, prop in _VERB_RESULT_STATES:
    # (slightcoarse) Bridge C: the result state arrived directly as the past
    # participle (has property "destroyed" X at past/W) with no verb form in
    # the clauses (split-mode claude, case 1052).  Persist it into the next
    # world at present tense — the same target context Bridges A/B produce —
    # so the mutex axioms (destroyed/intact) can fire on the question's
    # present-tense reading.
    if slight and prop in words:
      tc  = _fresh_fv()
      wca = _fresh_fv()
      wcb = _fresh_fv()
      lc  = _fresh_fv()
      kc  = _fresh_fv()
      clause_c = [
          ["-has property", prop, "?:X", ["$ctxt", tc, wca, lc, kc]],
          ["-next",         wca,  wcb],
          ["has property",  prop, "?:X", ["$ctxt", "present", wcb, lc, kc]],
          ["$block", 0,
            ["$not", ["has property", prop, "?:X",
                      ["$ctxt", "present", wcb, lc, kc]]]],
      ]
      axioms.append({"@name": "frm_verb_result",
                      "@logic": clause_c,
                      "@confidence": 0.9})
    if verb not in words:
      continue
    # Bridge A: event-based encoding (gemini/deepseek style).
    #   has type E V Ct  +  has target E X Ct  +  next W W2
    #     →  has property <prop> X CtNext
    t  = _fresh_fv()
    w  = _fresh_fv()
    w2 = _fresh_fv()
    l  = _fresh_fv()
    k  = _fresh_fv()
    full_ct = ["$ctxt", t, w, l, k]
    next_ct = ["$ctxt", "present", w2, l, k]
    clause = [
        ["-has type",   "?:E", verb, full_ct],
        ["-has target", "?:E", "?:X", full_ct],
        ["-next",       w,    w2],
        ["has property", prop, "?:X", next_ct],
        ["$block", 0,
          ["$not", ["has property", prop, "?:X", next_ct]]],
    ]
    axioms.append({"@name": "frm_verb_result",
                    "@logic": clause,
                    "@confidence": 0.9})
    # Bridge B: stative property encoding (claude style).
    # Claude sometimes emits `was destroyed` as `has property "destroy" X`
    # (verb root as property name).  Emit the canonical past-participle
    # result-state at present at the next world — same target context as
    # Bridge A so mutex axioms (e.g. destroyed/intact) can fire on the
    # question's present-tense reading.
    t2  = _fresh_fv()
    w2a = _fresh_fv()
    w2b = _fresh_fv()
    l2  = _fresh_fv()
    k2  = _fresh_fv()
    full_ct_b = ["$ctxt", t2, w2a, l2, k2]
    next_ct_b = ["$ctxt", "present", w2b, l2, k2]
    clause_b = [
        ["-has property", verb, "?:X", full_ct_b],
        ["-next",         w2a,  w2b],
        ["has property",  prop, "?:X", next_ct_b],
        ["$block", 0,
          ["$not", ["has property", prop, "?:X", next_ct_b]]],
    ]
    axioms.append({"@name": "frm_verb_result",
                    "@logic": clause_b,
                    "@confidence": 0.9})
  return axioms


# ======== positional-preposition actor-location bridges (case 670) ========
#
# Event location implies ACTOR location for POSITIONAL prepositions. Like the
# static in/at actor bridges (axioms_std.js §5e), these locate the actor AT a
# position relative to the landmark, so when an event HAS a location (not a
# destination) with such a preposition the actor is there: "the car parked
# behind the house" → the car is behind the house (case 670, has_actor
# reading). Support prepositions (on/under) are NOT included — they attach to
# the target (handled by the static target bridge). Injected dynamically: one
# bridge per positional preposition that actually appears in a has_location
# atom, so the prover carries only the relevant bridges. The equivalent static
# axioms are commented out in axioms_std.js §5e with a pointer here.
_POSITIONAL_PREPS = frozenset({
    "behind", "in_front_of", "beside", "next_to",
    "near", "by", "left_of", "right_of",
})


def _collect_has_location_preps(result):
  """Return the set of positional prepositions appearing in the prep slot
  (arg 3) of any has_location atom (positive or negated) in the clause list."""
  found = set()

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base == "has location" and len(n) >= 4
          and isinstance(n[3], str) and n[3] in _POSITIONAL_PREPS):
        found.add(n[3])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)
  return found


def inject_positional_actor_bridges(result, axiom_vocab=frozenset()):
  """For each positional preposition present in a has_location atom, emit one
  defeasible actor-location bridge:
    [-has location E L PREP Ct, -has actor E X Ct,
     is rel2 PREP X L Ct, $block(0, $not(is rel2 PREP X L Ct))]
  Mirrors the static in/at actor bridges (axioms_std.js §5e); see case 670.
  Gated on input presence only. ``axiom_vocab`` kept for call-site uniformity."""
  del axiom_vocab  # unused; gated on has_location prep presence
  axioms = []
  for prep in sorted(_collect_has_location_preps(result)):
    ct = _fresh_fv()
    clause = [
        ["-has location", "?:E", "?:L", prep, ct],
        ["-has actor", "?:E", "?:X", ct],
        ["is rel2", prep, "?:X", "?:L", ct],
        ["$block", 0, ["$not", ["is rel2", prep, "?:X", "?:L", ct]]],
    ]
    axioms.append({"@name": "frm_positional_actor_loc",
                    "@logic": clause,
                    "@confidence": 0.9})
  return axioms


# ======== containment bridges: "filled with"/"full of" → in (case 673) ========
#
# "X filled with Y" / "X full of Y" entails that Y is IN X. Some LLMs encode
# these as a relational predicate (is_rel2 / has_degree_rel2 with relation
# "filled with") rather than the containment primitive, so a "contained?" / "in?"
# query is not met (case 673 claude: has_degree_rel2("filled with", cup, water)
# vs question is_rel2("in", water, cup)). Rather than REWRITE the relation (which
# would discard the original "filled with"/fullness meaning), inject a one-way
# BRIDGE that PRESERVES the original atom and ADDS the containment entailment:
#   filled_with(X, Y) → in(Y, X)
# Strict (a sound lexical entailment, like the static contains↔in in
# axioms_std.js). One-directional only — "Y in X" does NOT imply X is full of Y.
# Injected dynamically: one bridge per (containment relation, predicate form)
# actually present. The gpt variant that packs the content into the property
# NAME (has_degree_property "filled with water") is handled separately by
# stage_sanity._check_stage2_multiword_property (under-decomposition retry).
_CONTAINMENT_RELS = frozenset({"filled with", "full of"})


def inject_containment_bridges(result, axiom_vocab=frozenset()):
  """For each containment relation ("filled with"/"full of") present as an
  is_rel2 or has_degree_rel2 atom, inject a strict bridge to is_rel2("in",
  content, container) that keeps the original atom. See case 673."""
  del axiom_vocab  # gated on relation presence in the clause list
  pairs = set()   # (relation, predicate-name)

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base in ("is rel2", "has degree rel2") and len(n) >= 2
          and isinstance(n[1], str) and n[1] in _CONTAINMENT_RELS):
        pairs.add((n[1], base))
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  axioms = []
  for rel, pred in sorted(pairs):
    ct = _fresh_fv()
    if pred == "has degree rel2":
      antecedent = ["-has degree rel2", rel, "?:X", "?:Y", "?:D", "?:RC", ct]
    else:
      antecedent = ["-is rel2", rel, "?:X", "?:Y", ct]
    clause = [antecedent, ["is rel2", "in", "?:Y", "?:X", ct]]
    axioms.append({"@name": "frm_containment_in", "@logic": clause})
  return axioms


# ======== occasion co-location bridge (case 178) ========
#
# An event located <prep> a place is also located <prep> any OCCASION that is
# itself <prep> that place.  Lets "US won medals IN Tokyo" + "the Olympics was
# IN Tokyo" derive "US won medals IN the Olympics":
#
#   is_rel2(P, Occ, Place) & has_location(E, Place, P) -> has_location(E, Occ, P)
#
# Emitted per preposition P only when BOTH an is_rel2(P,...) relation AND a
# has_location(...,P) atom are present (so it never fires on unrelated problems).
# The bridge is spatially loose (everything <prep> the place inherits the
# occasion), so it is gated to the ultracoarse encoding (caller-side).

_OCCASION_LOC_PREPS = frozenset({"in", "on", "at", "near"})

# Physical-location classes.  The bridge only fires when its Place is typed as
# one of these, so abstract "in" containment ("in the six-way tie", "in the
# leaderboard") does not inherit the occasion (case 195 regression).
_LOCATION_CLASSES = frozenset({
    "place", "location", "city", "country", "town", "village", "region",
    "area", "state", "province", "continent", "island", "airport", "venue",
})


def inject_occasion_location_bridges(result, axiom_vocab=frozenset()):
  """Co-location bridge for {in,on,at,near}: has_location(E,Place,P) plus
  is_rel2(P,Occ,Place) and Place is a physical location ->
  has_location(E,Occ,P).  See case 178 (and the case-195 guard)."""
  del axiom_vocab  # gated on atom presence in the clause list
  have_rel = set()       # prepositions seen as an is_rel2 relation
  have_loc = set()       # prepositions seen as a has_location preposition
  place_classes = set()  # physical-location classes asserted in the problem

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      neg = n[0].startswith("-")
      base = n[0][1:] if neg else n[0]
      if (base == "is rel2" and len(n) >= 2 and isinstance(n[1], str)
          and n[1] in _OCCASION_LOC_PREPS):
        have_rel.add(n[1])
      if (base == "has location" and len(n) >= 4 and isinstance(n[3], str)
          and n[3] in _OCCASION_LOC_PREPS):
        have_loc.add(n[3])
      if (not neg and base == "isa" and len(n) >= 2 and isinstance(n[1], str)
          and n[1] in _LOCATION_CLASSES):
        place_classes.add(n[1])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  axioms = []
  for prep in sorted(have_rel & have_loc):
    for cls in sorted(place_classes):
      c1 = _fresh_fv()
      c2 = _fresh_fv()
      clause = [["-is rel2", prep, "?:Occ", "?:Place", c1],
                ["-has location", "?:E", "?:Place", prep, c2],
                ["-isa", cls, "?:Place"],
                ["has location", "?:E", "?:Occ", prep, c2]]
      axioms.append({"@name": "frm_occasion_loc", "@logic": clause})
  return axioms


# ======== containment -> has_part bridge (cases 112/114) ========
#
# An entity located "in" a whole is a part of that whole:
#
#   is_rel2("in", X, Y, C) -> has_part(Y, X, C)
#
# ("X in Y" makes the container Y the whole and X the part.)  Emitted once, only
# when the clause set contains BOTH an is_rel2("in", ...) atom and a has_part
# atom, so the consequent can be consumed and no dead clause is added.  Untyped:
# under -ultracoarse FOLIO uses "in" for physical part-of containment (a mine
# in a mountain range), so the bridge is gated to the ultracoarse encoding
# (caller-side) rather than to a part-noun type.

def inject_in_haspart_bridge(result, axiom_vocab=frozenset()):
  """Containment->part bridge is_rel2("in",X,Y,C) -> has_part(Y,X,C), emitted
  only when both an is_rel2("in",...) and a has_part atom are present.  See
  cases 112/114.  Ultracoarse-only (caller-side gate)."""
  del axiom_vocab  # gated on atom presence in the clause list
  state = {"in": False, "haspart": False}

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if base == "is rel2" and len(n) >= 2 and n[1] == "in":
        state["in"] = True
      elif base == "has part":
        state["haspart"] = True
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  if not (state["in"] and state["haspart"]):
    return []
  return [{"@name": "frm_in_haspart",
           "@logic": [["-is rel2", "in", "?:X", "?:Y", "?:C"],
                      ["has part", "?:Y", "?:X", "?:C"]]}]


# ======== reflexive relation <-> property bridge (case 89) ========
#
# A degenerate self-comparison "X is ADJ-er than [X-]before" parses to the
# reflexive relation is_rel2(ADJ, X, X), but the same adjective on a rule
# consequent ("become smarter") is the unary has_property(ADJ, X).  Bridge the
# two so either satisfies the other:
#
#   has_property(ADJ, X, C) <-> is_rel2(ADJ, X, X, C)
#
# Emitted per predicate P only when P appears BOTH as a reflexive is_rel2
# (equal args) AND as a has_property in the clause set, so it never fires on an
# ordinary two-place relation.  Ultracoarse-only (caller-side gate).

def inject_reflexive_property_bridge(result, axiom_vocab=frozenset()):
  """Bridge has_property(P,X,C) <-> is_rel2(P,X,X,C) for each P present both as
  a reflexive is_rel2(P,A,A) and as a has_property(P,...).  See case 89."""
  del axiom_vocab  # gated on atom presence in the clause list
  refl_props = set()   # P seen as reflexive is_rel2(P, A, A)
  prop_props = set()   # P seen as has_property(P, ...)

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base == "is rel2" and len(n) >= 4 and isinstance(n[1], str)
          and n[2] == n[3]):
        refl_props.add(n[1])
      elif base == "has property" and len(n) >= 3 and isinstance(n[1], str):
        prop_props.add(n[1])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  axioms = []
  for p in sorted(refl_props & prop_props):
    axioms.append({"@name": "frm_reflexive_prop",
                   "@logic": [["-has property", p, "?:X", "?:C"],
                              ["is rel2", p, "?:X", "?:X", "?:C"]]})
    axioms.append({"@name": "frm_reflexive_prop",
                   "@logic": [["-is rel2", p, "?:X", "?:X", "?:C"],
                              ["has property", p, "?:X", "?:C"]]})
  return axioms


# ======== attribute property↔relation bridges (case 901) ========
#
# A property VALUE that belongs to an attribute family (color/shape/material/
# taste) is the same fact as the corresponding attribute RELATION: "X is red"
# (has_property("red", X)) == "the color of X is red" (is_rel2("color of",
# red, X)) == "X's color is red" (is_rel2("color", X, red)). LLMs split on the
# encoding: claude/gemini query has_property directly, but gpt/deepseek query
# the relation (is_rel2 "color of"/"color"), which nothing bridged to the
# stored property -> Unknown (case 901). This generalises the dead static
# "red -> color of" stub (axioms_std.js §8, commented out): it covered one
# colour, in one arg-order, and (fatally) expected has_degree_property while
# colours normalise to has_property.
#
# Value sets are reused from the data_exclusions mutex groups. For each
# attribute family with a relation name actually QUERIED and a value actually
# PRESENT as a property, inject both arg-orders of a strict bridge from the
# (post-normalize) has_property form -- "red is the color of X" and "X's color
# is red" -- so whichever relation/arg-order the LLM emitted is met.

def _family_words(*group_names):
  out = set()
  for gn in group_names:
    g = EXCLUSION_GROUPS.get(gn)
    if g:
      out.update(w for w in g.get("words", []) if isinstance(w, str))
  return frozenset(out)


_ATTRIBUTE_FAMILIES = {
    "color":    (_family_words("COLOR_BASIC", "COLOR_EXTRA"),
                 ("color of", "color", "colour of", "colour")),
    "shape":    (_family_words("SHAPE_BASIC"),
                 ("shape of", "shape")),
    "material": (_family_words("MATERIAL_BASIC"),
                 ("material of", "material", "made of", "made from",
                  "made out of")),
    "taste":    (_family_words("TASTE"),
                 ("taste of", "taste", "flavor of", "flavor",
                  "flavour of", "flavour")),
}


def inject_attribute_relation_bridges(result, axiom_vocab=frozenset()):
  """For each attribute family (color/shape/material/taste), bridge a stored
  property value to the attribute relation when that relation is queried.
  Injects both arg-orders per (value, relation) actually present. See case 901."""
  del axiom_vocab  # gated on value + relation presence in the clause list
  prop_values = set()   # arg1 of has_property / has_degree_property
  rel_names = set()     # arg1 of is_rel2

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base in ("has property", "has degree property") and len(n) >= 2
          and isinstance(n[1], str)):
        prop_values.add(n[1])
      elif base == "is rel2" and len(n) >= 2 and isinstance(n[1], str):
        rel_names.add(n[1])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  axioms = []
  for values, relations in _ATTRIBUTE_FAMILIES.values():
    present_rels = [r for r in relations if r in rel_names]
    if not present_rels:
      continue
    present_vals = sorted(v for v in prop_values if v in values)
    for v in present_vals:
      for r in present_rels:
        ct = _fresh_fv()
        # value-first:  "<v> is the <r> of X"
        axioms.append({"@name": "frm_attr_relation",
                        "@logic": [["-has property", v, "?:X", ct],
                                   ["is rel2", r, v, "?:X", ct]]})
        ct2 = _fresh_fv()
        # entity-first: "X's <r> is <v>"
        axioms.append({"@name": "frm_attr_relation",
                        "@logic": [["-has property", v, "?:X", ct2],
                                   ["is rel2", r, "?:X", v, ct2]]})
  return axioms


# ======== stable-adjective past→present persistence (case 911) ========
#
# INDIVIDUAL-LEVEL (stable) adjectives -- height, build, age, mental/character
# traits, etc. -- describe enduring properties: if X was tall, X is normally
# still tall. STAGE-LEVEL (temporary) adjectives -- hot/cold, wet/dry,
# hungry/tired, open/closed, broken, happy/sad -- do not persist that way and
# are deliberately excluded.
#
# The §6 frame persistence in axioms_std.js carries properties across WORLD
# transitions (next W W2) at the SAME tense; it does NOT bridge the past/present
# TENSE slot at one world. So when an LLM tenses a present copula as past (case
# 911: "The man whom John saw is tall" -> tall@past, contaminated by the past
# relative clause "whom John saw"), a present-tense query ("Is the man short?")
# never meets it -> Unknown, even though gemini/deepseek (tall@present) refute
# it via the tall/short mutex.
#
# This injects, for each stable adjective present as a property, a defeasible
# SAME-WORLD past→present persistence axiom (with a $not block override), so a
# past stable property reaches the present-tense reading. Dynamic: one pair of
# axioms per stable adjective actually present.
_STABLE_ADJS = frozenset({
    # physical dimension / size / build (stable for an object or person)
    "tall", "short", "big", "small", "large", "huge", "tiny", "little",
    "long", "wide", "narrow", "thick", "thin", "deep", "shallow", "high",
    "low", "broad", "flat", "heavy", "light", "fat", "slim", "skinny",
    "lean", "muscular", "bald", "round", "square",
    # age (only increases; past→present holds). "new" excluded (newness fades).
    "old", "young", "ancient", "elderly",
    # strength / physique trait
    "strong", "weak",
    # mental / ability (individual-level)
    "intelligent", "smart", "clever", "wise", "stupid", "dumb", "foolish",
    "brilliant", "talented", "skilled", "gifted", "educated",
    # character traits
    "kind", "cruel", "mean", "honest", "dishonest", "brave", "courageous",
    "cowardly", "generous", "selfish", "polite", "rude", "lazy", "shy",
    "friendly", "gentle", "loyal",
    # beauty (fairly stable)
    "beautiful", "pretty", "handsome", "ugly", "attractive", "plain",
    # value / quality / material hardness (property of the object)
    "expensive", "cheap", "valuable", "precious", "rare", "famous",
    "important", "dangerous", "poisonous", "rich", "poor", "hard", "soft",
})

# Colours, shapes, and materials are likewise INHERENT, individual-level
# attributes (a red car stays red, a wooden table stays wooden, a round table
# stays round), so they persist past→present too. Value sets are reused from
# the attribute families above. Taste is excluded -- it is gradable and a
# substance's taste can change (spoilage), so it is not treated as stable.
_STABLE_PERSIST_PROPS = (_STABLE_ADJS
                         | _ATTRIBUTE_FAMILIES["color"][0]
                         | _ATTRIBUTE_FAMILIES["shape"][0]
                         | _ATTRIBUTE_FAMILIES["material"][0])


def inject_stable_adjective_persistence(result, axiom_vocab=frozenset()):
  """For each STABLE (individual-level) adjective present as a property, inject
  a defeasible same-world past→present persistence axiom (has_property and
  has_degree_property forms), so a past stable property reaches a present-tense
  query. See case 911."""
  del axiom_vocab  # gated on stable-adjective presence in the clause list
  present_adjs = set()

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base in ("has property", "has degree property") and len(n) >= 2
          and isinstance(n[1], str) and n[1] in _STABLE_PERSIST_PROPS):
        present_adjs.add(n[1])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    walk(body)

  axioms = []
  for adj in sorted(present_adjs):
    # has_property form
    w, l, k = _fresh_fv(), _fresh_fv(), _fresh_fv()
    past_ct = ["$ctxt", "past", w, l, k]
    pres_ct = ["$ctxt", "present", w, l, k]
    pres_atom = ["has property", adj, "?:X", pres_ct]
    axioms.append({"@name": "frm_stable_persist",
                    "@logic": [["-has property", adj, "?:X", past_ct],
                               pres_atom,
                               ["$block", 0, ["$not", pres_atom]]],
                    "@confidence": 0.95})
    # has_degree_property form
    w2, l2, k2 = _fresh_fv(), _fresh_fv(), _fresh_fv()
    past_ct2 = ["$ctxt", "past", w2, l2, k2]
    pres_ct2 = ["$ctxt", "present", w2, l2, k2]
    pres_atom2 = ["has degree property", adj, "?:X", "?:D", "?:RC", pres_ct2]
    axioms.append({"@name": "frm_stable_persist",
                    "@logic": [["-has degree property", adj, "?:X", "?:D",
                                "?:RC", past_ct2],
                               pres_atom2,
                               ["$block", 0, ["$not", pres_atom2]]],
                    "@confidence": 0.95})
  return axioms


# ======== acquire → have bridges (case 1163) ========
#
# Acquisition verbs: the ACTOR ends up POSSESSING the target, acquired from an
# unnamed source.  Contrast with give→have (axioms_std.js §5b), which keys on
# the RECIPIENT and strips the giver's possession via `transferred`: an
# acquisition has no named party that loses the object, so Bridge A keys on
# the actor and needs no transferred-block.  Closes case 1163 ("Susan bought
# herself a new car. Who owns a new car?" → Susan): every LLM parse carries
# has_actor(E, Susan) even though the "herself" role is encoded
# inconsistently (has_beneficiary / has_recipient / dropped).

# Bridge A: actor acquires -> actor has.  Clean acquisition verbs only;
# take/get are excluded as too polysemous ("take a walk", "get tired").
_ACQUIRE_VERBS = ("buy", "purchase", "acquire", "obtain")

# Bridge B: benefactive ditransitive ("X bought/got Y a Z") -> the
# beneficiary / recipient owns it.  A buy-specific frame — you cannot
# "obtain Bill a car" — so the verb set is much narrower than Bridge A.
_ACQUIRE_BENEFACTIVE = ("buy", "get")


def inject_acquire_have_axioms(result, axiom_vocab=frozenset()):
  """Emit buy/acquire → have bridges (case 1163), modeled on axioms_std.js
  §5b give→have and on inject_verb_result_state_axioms (fresh free-vars,
  next-world present result).

  Bridge A — for each verb in _ACQUIRE_VERBS present in input: the actor of
  an acquisition event has the target in the next world (defeasible).

  Bridge B — for each verb in _ACQUIRE_BENEFACTIVE present in input: the
  beneficiary and the recipient have the target in the next world (the gift
  reading).

  Gated on input presence only.  ``axiom_vocab`` kept for call-site
  uniformity.
  """
  del axiom_vocab  # unused; input-presence gating
  words = _collect_eligible_words(result)
  axioms = []

  def _have_clause(role, verb):
    t  = _fresh_fv()
    w  = _fresh_fv()
    w2 = _fresh_fv()
    l  = _fresh_fv()
    k  = _fresh_fv()
    full_ct = ["$ctxt", t, w, l, k]
    next_ct = ["$ctxt", "present", w2, l, k]
    clause = [
        ["-has type",   "?:E", verb,      full_ct],
        ["-" + role,    "?:E", "?:Owner", full_ct],
        ["-has target", "?:E", "?:Obj",   full_ct],
        ["-next", w, w2],
        ["have", "?:Owner", "?:Obj", next_ct],
    ]
    return clause, next_ct

  # Bridge A: actor owns (defeasible).
  for verb in _ACQUIRE_VERBS:
    if verb not in words:
      continue
    clause, next_ct = _have_clause("has actor", verb)
    clause.append(["$block", 0, ["$not", ["have", "?:Owner", "?:Obj", next_ct]]])
    axioms.append({"@name": "frm_acquire_have",
                    "@logic": clause,
                    "@confidence": 0.9})

  # Bridge B: beneficiary / recipient owns (benefactive ditransitive).
  for verb in _ACQUIRE_BENEFACTIVE:
    if verb not in words:
      continue
    for role in ("has beneficiary", "has recipient"):
      clause, _ = _have_clause(role, verb)
      axioms.append({"@name": "frm_acquire_have",
                      "@logic": clause,
                      "@confidence": 0.95})
  return axioms


# ======== world-graph geometry ========

def inject_world_geometry(result):
  """Emit a minimal `next` chain spanning the concrete worlds (W0, W1, ...)
  actually present in the clause list.

  Replaces the static W0..W12 chain that used to live in axioms_std.js §11.
  When 0 or 1 distinct worlds are present, emits nothing (transitivity has
  nothing to chain). Otherwise fills any gaps in [min_idx, max_idx] so the
  `before` transitivity closure still derives `before(Wi,Wj)` for all
  observed i<j.
  """
  worlds = set()
  def _scan(tree):
    if isinstance(tree, str):
      if _is_world_constant(tree):
        worlds.add(tree)
      return
    if isinstance(tree, list):
      for el in tree:
        _scan(el)
  for obj in result:
    if not isinstance(obj, dict):
      continue
    for key in ("@logic", "@question"):
      v = obj.get(key)
      if v is not None:
        _scan(v)

  if len(worlds) <= 1:
    return []

  indices = sorted(int(w[1:]) for w in worlds)
  lo, hi = indices[0], indices[-1]
  axioms = []
  for i in range(lo, hi):
    axioms.append({"@name": "frm_world_geom",
                   "@sourcetype": "world_geometry",
                   "@logic": ["next", "W" + str(i), "W" + str(i + 1)]})
  return axioms


# ======== light shape-unification bridges (-slightcoarse) ========
#
# Stage-2 output sometimes uses near-synonymous constructions inconsistently:
# the question says has_location where the fact said has_destination, a role on
# the target entity where the fact put it on the event, a measure comparison
# where the question uses a comparative.  Per-sentence -s2split calls diverge
# this way most of all, but joint calls do too.  These bridges let the shapes
# interderive.  Each is emitted only when BOTH shapes (or the bridged
# predicate) actually occur in the clause list, and only under -slightcoarse
# (caller-side gate in logconvert), so the default path and the coarse
# encodings are untouched.

def _scan_predicates(result):
  """Set of positive base predicate names occurring in the clause list."""
  preds = set()

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      h = n[0]
      preds.add(h[1:] if h.startswith("-") else h)
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if isinstance(obj, dict):
      body = obj.get("@logic")
      if body is None:
        body = obj.get("@question")
      walk(body)
  return preds


def inject_slightcoarse_shape_bridges(result):
  """Bridges between near-synonymous constructions (-slightcoarse).

  - have <-> has_part: a part is had and a had part-ish thing is a part
    ("Who has a grey trunk?" vs rule "elephants have trunks" encoded has_part).
  - has_destination -> has_location: a motion event's destination answers a
    location question ("Where did Mary go?").
  - beneficiary lift: an event's beneficiary is also its target's beneficiary
    ("cooked a meal for the guests" -> "the meal is for the guests").
  """
  preds = _scan_predicates(result)
  axioms = []
  # have / has_part needs NO bridge here: has_part -> have (the sound
  # direction) is a static axiom (axioms_std.js top), and the risky
  # have -> has_part direction is covered conservatively by the always-on,
  # per-problem-typed lc_post_normalize.add_haspart_for_typed_have.  Case 190
  # only needed the has->have predicate rename for the static axiom to reach
  # the question atom.
  if "has destination" in preds and "has location" in preds:
    axioms.append({"@name": "frm_s2bridge", "@confidence": 0.99, "@logic": [
      ["-has destination", "?:Esb", "?:Xsb", "?:Psb", "?:Csb"],
      ["has location", "?:Esb", "?:Xsb", "?:Psb", "?:Csb"]]})
  if "has beneficiary" in preds:
    axioms.append({"@name": "frm_s2bridge", "@confidence": 0.99, "@logic": [
      ["-has target", "?:Esb", "?:Ysb", "?:Csb"],
      ["-has beneficiary", "?:Esb", "?:Xsb", "?:Csb"],
      ["has beneficiary", "?:Ysb", "?:Xsb", "?:Csb"]]})
  if "has recipient" in preds:
    axioms.append({"@name": "frm_s2bridge", "@confidence": 0.99, "@logic": [
      ["-has target", "?:Esb", "?:Ysb", "?:Csb"],
      ["-has recipient", "?:Esb", "?:Xsb", "?:Csb"],
      ["has recipient", "?:Ysb", "?:Xsb", "?:Csb"]]})
  axioms.extend(_measure_comparative_bridges(result))
  return axioms


# Measurement dimension -> the comparative adjective whose has_degree_rel2 it
# grounds (less_measure(m(D,X), m(D,Y)) means X measures less in D than Y).
_MEASURE_DIM_ADJ = {
  "height": "high", "weight": "heavy", "length": "long", "size": "big",
  "age": "old", "speed": "fast", "width": "wide", "depth": "deep",
  "temperature": "hot", "distance": "far",
}


def _measure_comparative_bridges(result):
  """(slightcoarse) Bridge the measurement shape to the comparative shape:
  one Stage-2 output encodes "X is higher than Y" as less_measure($measure_of(height,Y),
  $measure_of(height,X)) while the question split uses
  has_degree_rel2(high, ...).  Per dimension/adjective pair present on both
  sides, emit:
    less_measure(m(D,X,W), m(D,Y,W)) -> has_degree_rel2(ADJ, Y, X, ...)
    less_measure(m(D,X,W), m(D,Y,W)) -> -has_degree_rel2(ADJ, X, Y, ...)
  (X measures strictly less than Y, so Y is ADJ-er and X is not.)"""
  dims = set()
  adjs = set()

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if base == "less_measure":
        for a in n[1:]:
          if (isinstance(a, list) and len(a) >= 2 and a[0] == "$measure_of"
              and isinstance(a[1], str)):
            dims.add(a[1])
      elif base == "has degree rel2" and len(n) >= 2 and isinstance(n[1], str):
        adjs.add(n[1])
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  for obj in result:
    if isinstance(obj, dict):
      body = obj.get("@logic")
      if body is None:
        body = obj.get("@question")
      walk(body)

  axioms = []
  for dim in sorted(dims):
    adj = _MEASURE_DIM_ADJ.get(dim)
    if not adj or adj not in adjs:
      continue
    mx = ["$measure_of", dim, "?:Xsb", "?:Wsb"]
    my = ["$measure_of", dim, "?:Ysb", "?:Wsb"]
    axioms.append({"@name": "frm_s2bridge", "@confidence": 0.99, "@logic": [
      ["-less_measure", mx, my],
      ["has degree rel2", adj, "?:Ysb", "?:Xsb", "?:Dsb", "?:Rsb", "?:Csb"]]})
    axioms.append({"@name": "frm_s2bridge", "@confidence": 0.99, "@logic": [
      ["-less_measure", mx, my],
      ["-has degree rel2", adj, "?:Xsb", "?:Ysb", "?:Dsb2", "?:Rsb2", "?:Csb2"]]})
  return axioms
