# KB-driven soft-synonym + exclusion/mutex axiom injectors.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from lc_ctxt import fresh_fv as _fresh_fv
from lc_inject_scan import collect_eligible_words, eligible_word

from data_synonyms import SOFT_SYNONYMS
from data_exclusions import EXCLUSION_GROUPS, EXCLUSION_INDEX

# When True, only emit a soft synonym or exclusion axiom if BOTH sides of the
# pair appear in the problem (input clauses or axiom files). When False, emit
# whenever at least one side appears (original behavior — more axioms, slower).
REQUIRE_BOTH_SIDES = True



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
  words = collect_eligible_words(result)  # {lowercase: original_case}
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
  words = collect_eligible_words(result)
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

  Both layers are gated by REQUIRE_BOTH_SIDES via eligible_word /
  axiom_vocab membership.
  """
  words = collect_eligible_words(result)
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
  words = collect_eligible_words(result)
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
  words = collect_eligible_words(result)
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


