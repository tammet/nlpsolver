# Dynamic axiom injection passes for the post-clausification clause list.
#
# Each injector scans the clause list for trigger words / patterns and
# returns a list of new axiom clauses.  Injectors never mutate the input
# clause list — the caller appends the returned axioms.
#
# Sections:
#   - shared helpers      collect_eligible_words, eligible_word
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
from treewalk import walk_result_atoms
from data_exclusions import EXCLUSION_GROUPS
from lc_inject_scan import collect_eligible_words, eligible_word
from lc_inject_synonyms import (inject_soft_synonyms, inject_exclusion_axioms,
                                inject_isa_cross_group_axioms, inject_verb_mutex_axioms,
                                inject_kinship_mutex_axioms)

# ======== beneficiary → "for" preposition bridge ========


def _has_predicates_ben_and_for(result):
  """True iff input clauses contain BOTH a ["has beneficiary", ...] atom
  AND an ["is rel2", "for", ...] atom (positive or negated)."""
  saw_ben = [False]
  saw_for = [False]

  def visit(n, base):
    first = n[0]
    if first in ("has beneficiary", "-has beneficiary"):
      saw_ben[0] = True
    elif (first in ("is rel2", "-is rel2")
          and len(n) >= 2 and n[1] == "for"):
      saw_for[0] = True
  walk_result_atoms(result, visit)
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

  def visit(n, base):
    head = n[0]
    if head == "$measure_of" and len(n) >= 2 and isinstance(n[1], str):
      measure_nouns.add(n[1])
    elif head in ("is rel2", "-is rel2") and len(n) >= 2 \
            and isinstance(n[1], str) and n[1].endswith(" of"):
      rel_nouns.add(n[1][:-len(" of")])
  walk_result_atoms(result, visit)

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
  words = collect_eligible_words(result)
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
  words = collect_eligible_words(result)
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
  words = collect_eligible_words(result)
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
  words = collect_eligible_words(result)
  slight = _g_options.get("s2split_flag", False)
  axioms = []
  for verb, prop in _VERB_RESULT_STATES:
    # (-s2split repair) Bridge C: the result state arrived directly as the past
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

  def visit(n, base):
    if (base == "has location" and len(n) >= 4
        and isinstance(n[3], str) and n[3] in _POSITIONAL_PREPS):
      found.add(n[3])
  walk_result_atoms(result, visit)
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

  def visit(n, base):
    if (base in ("is rel2", "has degree rel2") and len(n) >= 2
        and isinstance(n[1], str) and n[1] in _CONTAINMENT_RELS):
      pairs.add((n[1], base))
  walk_result_atoms(result, visit)

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
# occasion), so it is gated to the abstraction encodings (caller-side).

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

  def visit(n, base):
    neg = n[0].startswith("-")
    if (base == "is rel2" and len(n) >= 2 and isinstance(n[1], str)
        and n[1] in _OCCASION_LOC_PREPS):
      have_rel.add(n[1])
    if (base == "has location" and len(n) >= 4 and isinstance(n[3], str)
        and n[3] in _OCCASION_LOC_PREPS):
      have_loc.add(n[3])
    if (not neg and base == "isa" and len(n) >= 2 and isinstance(n[1], str)
        and n[1] in _LOCATION_CLASSES):
      place_classes.add(n[1])
  walk_result_atoms(result, visit)

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
# under the abstraction encodings FOLIO uses "in" for physical part-of containment (a mine
# in a mountain range), so the bridge is gated to the abstraction encodings
# (caller-side) rather than to a part-noun type.

def inject_in_haspart_bridge(result, axiom_vocab=frozenset()):
  """Containment->part bridge is_rel2("in",X,Y,C) -> has_part(Y,X,C), emitted
  only when both an is_rel2("in",...) and a has_part atom are present.  See
  cases 112/114.  Abstraction-encodings-only (caller-side gate)."""
  del axiom_vocab  # gated on atom presence in the clause list
  state = {"in": False, "haspart": False}

  def visit(n, base):
    if base == "is rel2" and len(n) >= 2 and n[1] == "in":
      state["in"] = True
    elif base == "has part":
      state["haspart"] = True
  walk_result_atoms(result, visit)

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
# ordinary two-place relation.  Abstraction-encodings-only (caller-side gate).

def inject_reflexive_property_bridge(result, axiom_vocab=frozenset()):
  """Bridge has_property(P,X,C) <-> is_rel2(P,X,X,C) for each P present both as
  a reflexive is_rel2(P,A,A) and as a has_property(P,...).  See case 89."""
  del axiom_vocab  # gated on atom presence in the clause list
  refl_props = set()   # P seen as reflexive is_rel2(P, A, A)
  prop_props = set()   # P seen as has_property(P, ...)

  def visit(n, base):
    if (base == "is rel2" and len(n) >= 4 and isinstance(n[1], str)
        and n[2] == n[3]):
      refl_props.add(n[1])
    elif base == "has property" and len(n) >= 3 and isinstance(n[1], str):
      prop_props.add(n[1])
  walk_result_atoms(result, visit)

  axioms = []
  for p in sorted(refl_props & prop_props):
    axioms.append({"@name": "frm_reflexive_prop",
                   "@logic": [["-has property", p, "?:X", "?:C"],
                              ["is rel2", p, "?:X", "?:X", "?:C"]]})
    axioms.append({"@name": "frm_reflexive_prop",
                   "@logic": [["-is rel2", p, "?:X", "?:X", "?:C"],
                              ["has property", p, "?:X", "?:C"]]})
  return axioms


# ======== property↔class canonicalization (P1, -propclass) ========
#
# The flat fold sometimes leaves ONE concept in both predicate shapes: a class
# atom isa(W,X) and a property atom has_property(W,X,C).  A rule guard and the
# query/fact then fail to unify.  Bridge them
# (docs/architecture/abstraction.md):
#   SAFE   isa(W,X) -> has_property(W,X,C): a class member has the property in
#          every context, so this is sound for ANY W (no word-category gate).
#          Two trigger shapes: same word (W in both isa and has_property), and
#          adjective-compound-modifier (isa("A N") -> has_property(A) where the
#          modifier A is used as a property -- noun modifiers never are).
#   PROMOTE has_property(W,X,C) -> isa(W,X): asserts PERMANENT class membership,
#          so only for a kind-naming nominal compound -- detected by W already
#          having a compound_sub head -- and only when isa(W) is demanded (-isa).
# Strict clauses; free context variable (timeless class -> property in all C).

def inject_propclass_bridges(result, axiom_vocab=frozenset()):
  """Property↔class canonicalization bridges; see the section comment above."""
  del axiom_vocab  # gated on atom presence in the clause list
  hp = set()        # words W appearing as has_property(W, ...)
  isa = set()       # words W appearing as isa(W, ...)
  isa_sentence = set()  # isa evidence not manufactured by a generated bridge
  isa_neg = set()   # words W appearing as -isa(W, ...)  (promote demand)

  current_generated = [False]
  def visit(n, base):
    if base == "has property" and len(n) >= 2 and isinstance(n[1], str):
      hp.add(n[1])
    elif base == "isa" and len(n) >= 2 and isinstance(n[1], str):
      isa.add(n[1])
      if not current_generated[0]:
        isa_sentence.add(n[1])
      if n[0].startswith("-"):
        isa_neg.add(n[1])
  for obj in result:
    if not isinstance(obj, dict):
      continue
    current_generated[0] = str(obj.get("@name", "")).startswith("frm_")
    walk_result_atoms([obj], visit)

  # Nominal compounds = words the compound machinery decomposed to a noun head.
  csub = set()
  for c in result:
    if isinstance(c, dict) and c.get("@name") == "compound_sub":
      lg = c.get("@logic")
      if (isinstance(lg, list) and lg and isinstance(lg[0], list)
          and len(lg[0]) >= 2 and isinstance(lg[0][1], str)):
        csub.add(lg[0][1])

  axioms = []
  def safe(src, prop):
    axioms.append({"@name": "frm_propclass",
                   "@logic": [["-isa", src, "?:X"],
                              ["has property", prop, "?:X", "?:C"]]})
  # SAFE same-word: isa(W) -> has_property(W)
  # A noun-tagged synonym can manufacture isa(W) for a word used adjectivally
  # as has_property(W).  Crossing that generated class back into a property
  # confuses parts of speech (pw-0102: noun "young"=offspring vs adjective
  # "young").  Require sentence-derived class evidence; the kill switch keeps
  # the prior behavior independently replayable.
  safe_isa = isa if _g_options.get("nofix_propclasspos") else isa_sentence
  for w in sorted(hp & safe_isa):
    safe(w, w)
  # SAFE compound-modifier: isa("A N") -> has_property(A), A = adjectival modifier
  # (in has_property) of the compound class "A N".
  for a in sorted(hp):
    for cc in safe_isa:
      if cc != a and cc.startswith(a + " "):
        safe(cc, a)
  # PROMOTE has_property(W) -> isa(W): nominal compound (compound_sub) demanded as -isa.
  for w in sorted(hp):
    if w in isa_neg and w in csub:
      axioms.append({"@name": "frm_propclass",
                     "@logic": [["-has property", w, "?:X", "?:C"],
                                ["isa", w, "?:X"]]})
  return axioms


# ======== numeric-literal typing (P3, -numtype) ========
#
# Two related steps for problems that reason about numbers:
#   parse_numeric_literals  -- rewrite a pure-numeral string argument ("34",
#       "5.5", "-3") to an int/float, so numbers are numbers (consistent
#       unification across clauses, and gk can use them arithmetically).
#   inject_number_typing    -- when a numeric literal N is DEMANDED as a guard
#       -isa(TYPE,N) (TYPE a number-like type) but never supplied positively,
#       materialize the ground fact isa(TYPE,N).  Always sound (N is a number);
#       demand-gated, so it only fires where a rule actually needs the typing.
# gk has no built-in isa(number,N), so the fact must be asserted.

import re as _re_num
_NUMBER_TYPES = frozenset({"number", "integer", "int", "float", "real",
                           "decimal", "natural number", "whole number", "digit"})
_INT_RE = _re_num.compile(r"^-?\d+$")
_FLOAT_RE = _re_num.compile(r"^-?\d+\.\d+$")

def _to_number(s):
  if isinstance(s, str):
    if _INT_RE.match(s):
      return int(s)
    if _FLOAT_RE.match(s):
      return float(s)
  return s

def _is_number(x):
  return isinstance(x, (int, float)) or (
      isinstance(x, str) and (_INT_RE.match(x) or _FLOAT_RE.match(x)))

def _parse_numeric_node(node):
  if isinstance(node, list):
    if node and isinstance(node[0], str):   # atom: keep predicate name, convert args
      return [node[0]] + [_parse_numeric_node(a) if isinstance(a, list) else _to_number(a)
                          for a in node[1:]]
    return [_parse_numeric_node(x) for x in node]
  return node

def parse_numeric_literals(result):
  """Rewrite pure-numeral string arguments to int/float in every clause (in place).
  Entity names that merely contain digits (e.g. "Symphony No. 9 1") are NOT pure
  numerals, so they are untouched."""
  for c in result:
    if isinstance(c, dict):
      if isinstance(c.get("@logic"), list):
        c["@logic"] = _parse_numeric_node(c["@logic"])
      if c.get("@question") is not None:
        c["@question"] = _parse_numeric_node(c["@question"])

def _clause_atoms(body, acc):
  if isinstance(body, list) and body and isinstance(body[0], str):
    acc.append(body)
    for x in body[1:]:
      _clause_atoms(x, acc)
  elif isinstance(body, list):
    for x in body:
      _clause_atoms(x, acc)

def inject_number_typing(result):
  """Materialize isa(TYPE,N) for a number-like TYPE demanded as a guard but never
  supplied positively.  The demand is recognised both directly (`-isa(TYPE,N)`) and
  through an equality binding in the same clause (`-isa(TYPE,V)` with `-=(V,N)`, the
  `isa(number,Y) ∧ Y=N → …` rule shape).  Sound (N is a number); demand-gated."""
  supplied = set()
  demanded = set()
  def is_var(x):
    return isinstance(x, str) and x.startswith("?:")
  for c in result:
    if not isinstance(c, dict):
      continue
    body = c.get("@logic") if c.get("@logic") is not None else c.get("@question")
    atoms = []
    _clause_atoms(body, atoms)
    # variable -> numeric literal bindings from -=(V,N)/-=(N,V) guards in this clause
    binds = {}
    for a in atoms:
      base = a[0][1:] if a[0].startswith("-") else a[0]
      if base == "=" and len(a) >= 3:
        v, w = a[1], a[2]
        if is_var(v) and _is_number(w):
          binds[v] = _to_number(w)
        elif is_var(w) and _is_number(v):
          binds[w] = _to_number(v)
    for a in atoms:
      if not (len(a) >= 3 and isinstance(a[0], str)):
        continue
      neg = a[0].startswith("-")
      if (a[0][1:] if neg else a[0]) != "isa" or not isinstance(a[1], str) or a[1] not in _NUMBER_TYPES:
        continue
      arg = a[2]
      if _is_number(arg):
        (demanded if neg else supplied).add((a[1], _to_number(arg)))
      elif neg and is_var(arg) and arg in binds:
        demanded.add((a[1], binds[arg]))
  return [{"@name": "frm_numtype", "@logic": ["isa", t, v]}
          for (t, v) in sorted(demanded - supplied, key=str)]


# ======== comparative asymmetry (P3, -compasym) ========
#
# The flat / -simpleprops fold collapses a degree-comparative
# has_degree_rel2(R,X,Y,high) into a plain is_rel2(R,X,Y), which bypasses the
# comparative-order axioms in axioms_std.js §3/§3.1 (those key on has_degree_rel2
# with degree=high).  For a STRICT-SCALAR adjective R (height, size, speed, age,
# value, price, ...) the binary relation "X is more-R than Y" is asymmetric, so we
# re-emit that order axiom for the flat is_rel2 form.  R is restricted to a curated
# positive list (comparable_adjectives.txt) because gradables.txt also contains
# SYMMETRIC relations (similar, near, equal, different, adjacent) and relational/
# attitude verbs (love, need, want, like) for which asymmetry is FALSE.

def _load_comparable_adjs():
  import os as _os
  path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                       "comparable_adjectives.txt")
  out = set()
  try:
    with open(path, encoding="utf-8") as fh:
      for line in fh:
        w = line.strip()
        if w and not w.startswith("#"):
          out.add(w.lower())
  except OSError:
    pass
  return frozenset(out)

COMPARABLE_ADJS = _load_comparable_adjs()

def inject_comparative_axioms(result):
  """For each strict-scalar adjective R that occurs as a binary is_rel2(R,X,Y),
  emit the comparative ANTISYMMETRY  is_rel2(R,X,Y) & is_rel2(R,Y,X) -> X=Y  and the
  flat property bridge  is_rel2(R,X,Y) -> has_property(R,X)  (the latter only when a
  has_property(R,*) consumer is present).  Gated on R present as is_rel2, so it fires
  only where a comparison actually occurs.

  Antisymmetry (not strict asymmetry): two distinct entities cannot each be more-R
  than the other (refutes comparison cycles via entity UNA), but a reflexive
  self-comparison is_rel2(R,A,A) is left consistent.  The reflexive case arises when
  abstraction collapses a "more-R than before" temporal comparison onto one constant
  (e.g. "Harry is smarter than before" -> is_rel2(smart,Harry,Harry), case 89); strict
  asymmetry would wrongly make that self-contradictory."""
  rel2 = set()       # adjectives used as binary is_rel2
  hp_consumed = set()  # adjectives demanded as has_property (guards)
  def visit(n, base):
    if base == "is rel2" and len(n) >= 4 and isinstance(n[1], str) and n[1] in COMPARABLE_ADJS:
      rel2.add(n[1])
    elif base == "has property" and len(n) >= 2 and isinstance(n[1], str) and n[0].startswith("-"):
      hp_consumed.add(n[1])
  walk_result_atoms(result, visit)
  axioms = []
  for r in sorted(rel2):
    axioms.append({"@name": "frm_compasym",
                   "@logic": [["-is rel2", r, "?:X", "?:Y", "?:C"],
                              ["-is rel2", r, "?:Y", "?:X", "?:C"],
                              ["=", "?:X", "?:Y"]]})
    if r in hp_consumed:
      axioms.append({"@name": "frm_compasym",
                     "@logic": [["-is rel2", r, "?:X", "?:Y", "?:C"],
                                ["has property", r, "?:X", "?:C"]]})
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

  def visit(n, base):
    if (base in ("has property", "has degree property") and len(n) >= 2
        and isinstance(n[1], str)):
      prop_values.add(n[1])
    elif base == "is rel2" and len(n) >= 2 and isinstance(n[1], str):
      rel_names.add(n[1])
  walk_result_atoms(result, visit)

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

  def visit(n, base):
    if (base in ("has property", "has degree property") and len(n) >= 2
        and isinstance(n[1], str) and n[1] in _STABLE_PERSIST_PROPS):
      present_adjs.add(n[1])
  walk_result_atoms(result, visit)

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
  words = collect_eligible_words(result)
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


# ======== cross-sentence shape-unification bridges (-s2split repair) ========
#
# Per-sentence -s2split Stage-2 calls use near-synonymous constructions
# inconsistently: one sentence says has_location where its sibling said
# has_destination, a role on the target entity vs on the event, a measure
# comparison vs a comparative.  These bridges let the divergent shapes
# interderive.  Each is emitted only when BOTH shapes (or the bridged predicate)
# actually occur in the clause list, and only under -s2split (caller-side gate in
# logconvert), so the default path and the abstraction encodings are untouched.

def _scan_predicates(result):
  """Set of positive base predicate names occurring in the clause list."""
  preds = set()

  def visit(n, base):
    preds.add(base)
  walk_result_atoms(result, visit)
  return preds


def inject_s2split_shape_bridges(result):
  """Bridges between near-synonymous constructions (-s2split repair).

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
  """(-s2split repair) Bridge the measurement shape to the comparative shape:
  one Stage-2 output encodes "X is higher than Y" as less_measure($measure_of(height,Y),
  $measure_of(height,X)) while the question split uses
  has_degree_rel2(high, ...).  Per dimension/adjective pair present on both
  sides, emit:
    less_measure(m(D,X,W), m(D,Y,W)) -> has_degree_rel2(ADJ, Y, X, ...)
    less_measure(m(D,X,W), m(D,Y,W)) -> -has_degree_rel2(ADJ, X, Y, ...)
  (X measures strictly less than Y, so Y is ADJ-er and X is not.)"""
  dims = set()
  adjs = set()

  def visit(n, base):
    if base == "less_measure":
      for a in n[1:]:
        if (isinstance(a, list) and len(a) >= 2 and a[0] == "$measure_of"
            and isinstance(a[1], str)):
          dims.add(a[1])
    elif base == "has degree rel2" and len(n) >= 2 and isinstance(n[1], str):
      adjs.add(n[1])
  walk_result_atoms(result, visit)

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
