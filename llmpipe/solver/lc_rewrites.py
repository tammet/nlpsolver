# Pre-clausification formula rewrites for the llm-based nlpsolver.
#
# Pure formula-tree transformations applied before clausification:
#   - Meta-predicate normalization (is_rel2("is",...) → isa, "located in" → "in")
#   - Degree presupposition injection ("not very X" → X and not very X)
#   - Misnested existential hoisting (fix scoping errors from LLMs)
#   - Spurious "can" removal from event queries
#   - Consequent negation for low-confidence rules
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

import re


# ======== meta-predicate normalization ========

# "located X" → "X" for spatial prepositions
_LOCATED_PREFIX_MAP = {}
for _p in ("in", "at", "on", "near", "above", "under"):
  _LOCATED_PREFIX_MAP["located " + _p] = _p


# Possession/ownership relations → canonical have(owner, thing).
# An LLM sometimes encodes possession as a generic binary `is rel2` relation
# ("belonged to" / "owned by" / "owns") instead of the canonical `have`
# predicate.  Those never unify with possessive-have facts or has_part
# inferences, so a "whose / who owns" query and a possessive assertion miss
# each other.  Canonicalise both surface families to have:
#   passive ("belonged to", owner at arg 3)  → swap to have(owner, thing)
#   active  ("owns", owner already at arg 2)  → have(owner, thing)
_OWN_REL_SWAP = frozenset({          # ["is rel2", REL, THING, OWNER]
  "belonged to", "belongs to", "belong to",
  "owned by", "possessed by",
})
_OWN_REL_NOSWAP = frozenset({        # ["is rel2", REL, OWNER, THING]
  "owns", "own", "owned",
  "possesses", "possess", "possessed",
})


# Preposition canonicalisation — pure surface-form variants mapped to the
# canonical form used by the exclusion/subsumption axioms. Handled as
# rewriting (not axioms) because the variants are the SAME concept, just
# spelled differently. Near-synonyms with distinct meaning (over/above,
# under/below, on_top_of/above) are handled by subsumption axioms in
# axioms_std.js, NOT by this table.
_PREP_CANONICAL = {
  # spatial — spaced form → underscored form (LLM mostly underscores already)
  "in front of":       "in_front_of",
  "in front":          "in_front_of",   # missing trailing "of"
  "front of":          "in_front_of",   # missing leading "in"
  "in back of":        "behind",        # colloquial ≡ behind
  "back of":           "behind",
  "to the left of":    "left_of",
  "left of":           "left_of",
  "to the right of":   "right_of",
  "right of":          "right_of",
  "on top of":         "on_top_of",
  "inside of":         "inside",
  "outside of":        "outside",
  "out of":            "outside",
  "far away from":     "far_from",
  "far from":          "far_from",
  "far":               "far_from",       # has_degree_rel2 arg 1: LLM sometimes drops "from"
  "close to":          "near",           # canonical collapse (close_to ⊆ near)
  "close_to":          "near",
  "next to":           "next_to",
  # temporal
  "prior to":          "prior_to",
  "subsequent to":     "after",
}

def rewrite_meta_predicates(tree):
  """Normalize verbose/meta is_rel2 predicates throughout the formula tree.

  Copula/identity:
    ["is rel2", "is", A, B]          → ["isa", A, B]
    ["is rel2", "=",  A, B]          → ["=", A, B]

  Spatial meta-predicates:
    ["is rel2", "located in", A, B]  → ["is rel2", "in", A, B]
    ["is rel2", "located at", A, B]  → ["is rel2", "at", A, B]
    ["is rel2", "located on", A, B]  → ["is rel2", "on", A, B]
    etc. for near, above, under.

  Temporal meta-predicate:
    ["is rel2", "time of", E, X]     → ["has time", E, X, "in"]

  Handles negated forms as well.
  """
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  # Movement verb synonyms: travel/journey/move → go
  # Normalizing in the pipeline avoids synonym axiom chains in the prover,
  # which cause combinatorial explosion with many world states.
  if op in ("has type", "-has type") and len(tree) >= 3:
    verb = tree[2]
    if isinstance(verb, str) and verb in ("travel", "journey", "move"):
      return [tree[0], tree[1], "go"] + tree[3:]
    # Transfer verb synonyms: hand/send → give
    # ("pass" excluded: too polysemous; "students passed the exam" should not
    # become "give" and lose the pass↔fail antonym path.)
    if isinstance(verb, str) and verb in ("hand", "send"):
      return [tree[0], tree[1], "give"] + tree[3:]
    # Placement verb synonyms: place/set/lay/position/deposit → put
    if isinstance(verb, str) and verb in ("place", "set", "lay", "position", "deposit"):
      return [tree[0], tree[1], "put"] + tree[3:]
  # has_destination 3-arg → 4-arg backward compat: insert "at" as default prep.
  # Stage 2 may emit ["has destination", E, Dest] (no prep); axioms now expect
  # ["has destination", E, Dest, Prep]. Insert "at" so existing encodings still work.
  if op in ("has destination", "-has destination") and len(tree) == 3:
    return [tree[0], tree[1], tree[2], "at"]
  if op in ("is rel2", "-is rel2") and len(tree) >= 4:
    pfx = "-" if op.startswith("-") else ""
    rel = tree[1]
    if isinstance(rel, str):
      # Copula/identity
      if rel == "is":
        return [pfx + "isa", tree[2], tree[3]]
      if rel == "=":
        return [pfx + "=", tree[2], tree[3]]
      # Temporal meta-predicate: "time of" → has_time with default prep
      if rel == "time of" and len(tree) >= 4:
        return [pfx + "has time", tree[2], tree[3], "in"]
      # Possession/ownership meta-predicate → canonical have(owner, thing).
      if rel in _OWN_REL_SWAP:
        return [pfx + "have", tree[3], tree[2]]
      if rel in _OWN_REL_NOSWAP:
        return [pfx + "have", tree[2], tree[3]]
      # Spatial meta-predicates: "located in" → "in", etc.
      canonical = _LOCATED_PREFIX_MAP.get(rel)
      if canonical:
        return [pfx + "is rel2", canonical] + tree[2:]
      # Preposition canonicalisation: "in front of" → "in_front_of" etc.
      canonical = _PREP_CANONICAL.get(rel)
      if canonical:
        return [pfx + "is rel2", canonical] + tree[2:]
  # Also canonicalise the preposition in has_degree_rel2 (near/far_from) and
  # in has_location / has_time / has_destination's preposition slot.
  if op in ("has degree rel2", "-has degree rel2") and len(tree) >= 2:
    rel = tree[1]
    if isinstance(rel, str):
      canonical = _PREP_CANONICAL.get(rel)
      if canonical:
        return [op, canonical] + list(tree[2:])
  if op in ("has location", "-has location",
            "has time", "-has time",
            "has destination", "-has destination") and len(tree) >= 4:
    prep = tree[3]
    if isinstance(prep, str):
      canonical = _PREP_CANONICAL.get(prep)
      if canonical:
        return list(tree[:3]) + [canonical] + list(tree[4:])
  return [rewrite_meta_predicates(child) if isinstance(child, list) else child
          for child in tree]


# ======== perspective verb → dative head normalization ========
#
# A perspective verb (receive/get/hear/see) describes the recipient's view
# of a dative event (give/tell/show).  Canonicalise to the dative head and
# swap actor→recipient so prover queries about the perspective verb match
# facts encoded with the dative head, and vice-versa.
#
# Asymmetry is preserved: the rewrite never adds an actor for
# perspective-verb events that lack an explicit dative agent.  E.g.
# "Mary received a book" → give(recipient=Mary, target=book) — no actor —
# so "Did John receive a book?" still fails (John was actor, not recipient).
_PERSPECTIVE_TO_DATIVE = {
  "receive": "give",
  "get":     "give",
  "hear":    "tell",
  "see":     "show",
}


def _collect_content_holders(node, out):
  """Add the first arg of every has_content atom (the perceiving/embedding
  event var) to out, recursively."""
  if isinstance(node, list) and node:
    if (isinstance(node[0], str) and node[0] in ("has content", "-has content")
        and len(node) >= 2 and isinstance(node[1], str)):
      out.add(node[1])
    for c in node[1:]:
      if isinstance(c, list):
        _collect_content_holders(c, out)


def normalize_receive_events(tree):
  """Rewrite perspective-verb events (receive/get/hear/see) to their dative
  head (give/tell/show) with swapped actor→recipient.

  In an ["and", ...] block containing ["has type", E, V] where V is a
  perspective verb, the verb becomes the dative head and ["has actor",E,X]
  becomes ["has recipient",E,X] for that E.

  Function name kept for back-compat with the original receive-only form;
  see _PERSPECTIVE_TO_DATIVE for the actual mapping.
  """
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  # Look for ["and", ...] blocks containing a perspective-verb event.
  if op == "and" and len(tree) >= 2:
    # Perception OF AN EVENT ("Mary was heard to sing" → hear E1 + has_content
    # E1 E2) is NOT a dative — it is factive perception (handled by
    # inject_perception_factive_bridges). Skip the dative rewrite for any event
    # var that holds a has_content, so "hear"/"see" survive for that bridge.
    content_holders = set()
    _collect_content_holders(tree, content_holders)
    # event-var → dative-head verb (only events whose type is a perspective verb)
    persp_evars = {}
    for item in tree[1:]:
      if (isinstance(item, list) and len(item) >= 3
          and isinstance(item[0], str) and item[0] in ("has type", "-has type")
          and isinstance(item[2], str) and item[2] in _PERSPECTIVE_TO_DATIVE
          and item[1] not in content_holders):
        persp_evars[item[1]] = _PERSPECTIVE_TO_DATIVE[item[2]]
    if persp_evars:
      result = [tree[0]]
      for item in tree[1:]:
        item = normalize_receive_events(item)  # recurse first
        if isinstance(item, list) and len(item) >= 3 and isinstance(item[0], str):
          evar = item[1]
          if evar in persp_evars:
            dative = persp_evars[evar]
            if (item[0] in ("has type", "-has type")
                and isinstance(item[2], str)
                and item[2] in _PERSPECTIVE_TO_DATIVE):
              result.append([item[0], item[1], dative] + item[3:])
              continue
            if item[0] in ("has actor", "-has actor"):
              neg = "-" if item[0].startswith("-") else ""
              result.append([neg + "has recipient"] + item[1:])
              continue
        result.append(item)
      return result
  # Recurse into sub-expressions.
  return [normalize_receive_events(child) if isinstance(child, list) else child
          for child in tree]


# ======== perspective relation → event normalization ========
#
# Some LLMs (gpt, deepseek) encode a perspective verb as a binary `is rel2`
# relation rather than a Davidsonian event.  Example: "Who got a letter?" →
#   ["ask","X",["exists","Y",["and",["isa","letter","Y"],
#                                   ["is rel2","got","X","Y"]]]]
# The downstream normalize_receive_events only inspects ["has type",E,V]
# events, so the relation form never reaches the perspective→dative bridge
# and the query fails to unify with the assertion's give/tell/show event.
#
# This pass rewrites such ["is rel2",V,X,Y] atoms into the canonical event
# form so normalize_receive_events (next pass) can canonicalize them.  The
# dict maps inflected surface forms to the lemma, since the downstream
# normalizer is lemma-only.
_PERSPECTIVE_REL_VERBS = {
  "get": "get", "gets": "get", "got": "get", "gotten": "get",
  "receive": "receive", "receives": "receive", "received": "receive",
  "see": "see", "sees": "see", "saw": "see", "seen": "see",
  "hear": "hear", "hears": "hear", "heard": "hear",
}


def rewrite_perspective_relations(tree):
  """Rewrite ["is rel2", VERB, X, Y] (and negated form) where VERB is a
  perspective verb surface form into the Davidsonian event form so that
  normalize_receive_events can bridge it to the dative head.

  Runs BEFORE clausification — Stage-2 is rel2 has 4 elements at this stage
  (no $ctxt yet), so longer/shorter shapes are left untouched.  Each rewrite
  introduces a fresh existentially-bound event variable EprN.
  """
  counter = [0]
  return _rewrite_perspective_relations_walk(tree, counter)


def _rewrite_perspective_relations_walk(node, counter):
  if not isinstance(node, list) or not node:
    return node
  op = node[0] if isinstance(node[0], str) else None
  if op in ("is rel2", "-is rel2") and len(node) == 4:
    rel = node[1]
    if isinstance(rel, str) and rel in _PERSPECTIVE_REL_VERBS:
      lemma = _PERSPECTIVE_REL_VERBS[rel]
      x = node[2]
      y = node[3]
      e = "Epr" + str(counter[0])
      counter[0] += 1
      event = ["exists", e,
               ["and",
                ["isa", "activity", e],
                ["has type", e, lemma],
                ["has actor", e, x],
                ["has target", e, y]]]
      if op == "-is rel2":
        return ["not", event]
      return event
  return [_rewrite_perspective_relations_walk(c, counter) if isinstance(c, list) else c
          for c in node]


# ======== strip tense-valued has_time ========

_GRAMMATICAL_TENSES = frozenset({"past", "present", "future", "timeless"})


def _collect_event_vars(tree):
  """Walk tree; return the set of variable strings X for which
  ["isa", "activity", X] appears anywhere — i.e., Davidsonian event
  variables.  has_time on these may legitimately carry a grammatical
  tense per Stage-2 §8.1."""
  out = set()
  def visit(node):
    if not isinstance(node, list) or not node:
      return
    if (len(node) >= 3 and isinstance(node[0], str)
        and node[0] == "isa"
        and isinstance(node[1], str) and node[1] == "activity"
        and isinstance(node[2], str)):
      out.add(node[2])
    for child in node:
      if isinstance(child, list):
        visit(child)
  visit(tree)
  return out


def strip_tense_has_time(tree, event_vars=None):
  """Remove tense-valued has_time / state_time atoms where the value
  is a grammatical tense, EXCEPT when first arg is a Davidsonian event
  variable.

  Per Stage-2 §8.1, the canonical shape for grammatical tense on a
  Davidsonian event is ["has time", E, "past"|"present"|"future", "in"]
  and must survive.  For non-event predicates, tense belongs in $ctxt
  (injected from the Stage-1 ASU "time" field) and a has_time with a
  tense value there is the old wrong shape — strip it.

  ["state time", W, "past"] belongs at the package level as metadata;
  if it appears inside a formula body it is a misplacement and is
  always stripped.
  """
  if event_vars is None:
    event_vars = _collect_event_vars(tree)
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  # has_time with tense value: keep on Davidsonian events, strip otherwise.
  if op in ("has time", "-has time") and len(tree) >= 3:
    if isinstance(tree[2], str) and tree[2] in _GRAMMATICAL_TENSES:
      first_arg = tree[1] if len(tree) >= 2 else None
      if not (isinstance(first_arg, str) and first_arg in event_vars):
        return None  # sentinel: remove this conjunct
  # Misplaced state_time with tense value (belongs at package level).
  if op in ("state time", "-state time") and len(tree) >= 3:
    if isinstance(tree[2], str) and tree[2] in _GRAMMATICAL_TENSES:
      return None
  # Recurse into children; filter out None from "and" conjunctions
  if op == "and":
    children = []
    for child in tree[1:]:
      result = strip_tense_has_time(child, event_vars)
      if result is not None:
        children.append(result)
    if not children:
      return None
    if len(children) == 1:
      return children[0]
    return ["and"] + children
  # Wrappers whose body may be stripped: propagate None upward.
  if op == "@time" and len(tree) == 3:
    body = strip_tense_has_time(tree[2], event_vars)
    if body is None:
      return None
    return [tree[0], tree[1], body]
  return [strip_tense_has_time(child, event_vars) if isinstance(child, list) else child
          for child in tree]


# ======== strip redundant negative tense-agreement has_time ========
#
# A clause-level pass (runs AFTER clausification, on the final clause list).
# A negative literal of the form
#   ["-has time", E, T, Prep, ["$ctxt", T, ...]]
# where T is a grammatical tense EQUAL to the $ctxt tense slot is a vacuous
# query escape: the event's tense is already carried (and normalised to past
# for past worlds) by the $ctxt slot via the axioms_std.js "Context Tense
# Normalization" (D) block.  Requiring it over-constrains a yes/no question
# whose matching assertion expresses time through a temporal MODIFIER instead
# (e.g. "written in June" -> has_time(E, "June", ...)): the modifier value
# never unifies with the tense value "past", so the proof fails (case 709).
# Removing the negative literal drops the escape and lets the question match.
# The POSITIVE counterpart ["has time", E, T, Prep, ["$ctxt", T, ...]] is
# left intact -- it is a redundant-but-true fact, not an over-constraint.


def _is_neg_tense_agreement_literal(lit):
  """True for ["-has time", E, T, Prep, ["$ctxt", T, ...]] with T a
  grammatical tense equal to the $ctxt tense slot."""
  if not (isinstance(lit, list) and len(lit) >= 5 and lit[0] == "-has time"):
    return False
  val, ctxt = lit[2], lit[4]
  return (isinstance(val, str) and val in _GRAMMATICAL_TENSES
          and isinstance(ctxt, list) and len(ctxt) >= 2
          and ctxt[0] == "$ctxt" and ctxt[1] == val)


def strip_neg_tense_agreement_in_clause(logic):
  """Remove negative tense-agreement has_time literals from a single clause's
  @logic / @question (a disjunction of literals).  Positive has_time literals
  are kept.  Single-literal (unit) clauses and clauses that would be emptied
  are returned unchanged."""
  if not isinstance(logic, list) or not logic:
    return logic
  # Only a disjunction (every element a literal-list) can hold the goal
  # escape; a single literal has a string head and is left alone.
  if not all(isinstance(lit, list) for lit in logic):
    return logic
  kept = [lit for lit in logic if not _is_neg_tense_agreement_literal(lit)]
  if kept and len(kept) != len(logic):
    return kept
  return logic


# ======== actuality classifier injection ========
#
# Post-Stage-2 marker on Davidsonian events that have NO modal classifier
# (capability / typical / necessity / obligation / volition / intention /
# expectation / speech_act).  Stage 2 deliberately doesn't emit it; the
# pipeline injects ["actuality", E] so axioms can dispatch on a positive
# marker rather than on absence-of-classifier.
#
# Skip rule for inner content events (E2 in two-event reification): if E
# appears as the second argument of has_content anywhere in the tree, it
# describes an action type (wanted / intended / spoken-about), not an
# actual occurrence — leave it unmarked.

_MODAL_CLASSIFIERS = frozenset({
  "typical", "capability", "necessity", "obligation",
  "volition", "intention", "expectation", "speech_act",
})

# CAUSATIVE verbs whose `has_content` inner event ACTUALLY occurs: "Tom HAD
# the mechanic fix the car", "MADE/LET/FORCED/GOT him fix it".  The embedded
# event really happens, so its E2 must still receive actuality (case 1616).
# Everything else that reifies content via `has_content` -- the four mental/
# speech modes (want/intend/expect/say) AND non-factive verbs like "try"/
# "attempt"/"hope"/"fail" -- has a NON-actual inner event, so E2 is skipped.
# This is a WHITELIST (only known causatives un-skip) rather than a mode
# blacklist, because non-factive verbs like "try" carry no modal classifier
# yet their content is not actual ("John tried to open the door" =/=> opened).
_CAUSATIVE_CONTENT_VERBS = frozenset({
  "have", "make", "let", "force", "cause", "get",
})


def _collect_content_inner_vars(tree):
  """Collect inner content event variables E2 from `["has content", E1, E2]`
  that must NOT receive an actuality marker.

  E2 is collected (actuality suppressed) UNLESS the outer event E1's verb is a
  known CAUSATIVE (_CAUSATIVE_CONTENT_VERBS), whose embedded event actually
  occurs.  So intention/speech content (want/say/...) and non-factive verbs
  (try/attempt/...) keep E2 non-actual, while a causative "had the mechanic
  fix the car" leaves E2 eligible for actuality (case 1616)."""
  # First pass: map every event var to its has_type verb.
  verb_of = {}
  def collect_verbs(node):
    if not isinstance(node, list) or not node:
      return
    if (isinstance(node[0], str) and node[0] == "has type"
        and len(node) >= 3 and isinstance(node[1], str)
        and isinstance(node[2], str)):
      verb_of.setdefault(node[1], node[2])
    for child in node:
      collect_verbs(child)
  collect_verbs(tree)

  # Second pass: collect E2 unless its outer event E1 is a causative verb.
  out = set()
  def visit(node):
    if not isinstance(node, list) or not node:
      return
    if (isinstance(node[0], str) and node[0] == "has content"
        and len(node) >= 3 and isinstance(node[2], str)):
      e1 = node[1] if isinstance(node[1], str) else None
      if not (e1 is not None
              and verb_of.get(e1) in _CAUSATIVE_CONTENT_VERBS):
        out.add(node[2])
    for child in node:
      if isinstance(child, list):
        visit(child)
  visit(tree)
  return out


def _collect_classified_vars(tree):
  """Collect every event variable E carrying a modal classifier
  (typical / capability / ...) ANYWHERE in the tree — not just as a direct
  sibling of isa(activity, E).  Some LLMs nest the classifier one level
  deeper inside the event's own and-block (case 1418, claude: ["typical", E]
  lives inside the strong-fish ∃Y sub-block), where inject_actuality's
  direct-sibling scan would miss it and wrongly inject actuality(E) — making
  a rule antecedent require actuality while the matching fact only carries
  typical."""
  out = set()
  def visit(node):
    if not isinstance(node, list) or not node:
      return
    if (isinstance(node[0], str) and node[0] in _MODAL_CLASSIFIERS
        and len(node) >= 2 and isinstance(node[1], str)):
      out.add(node[1])
    for child in node:
      visit(child)
  visit(tree)
  return out


def inject_actuality(tree, content_inner=None, classified=None):
  """Append ["actuality", E] to every and-block that introduces a
  Davidsonian event via ["isa","activity",E] and has no modal classifier
  on E anywhere in the tree, provided E is not the inner argument of
  has_content(_, E) anywhere in the tree.

  Idempotent: a second pass over the same tree adds nothing because the
  marker counts as a classifier on the next walk only if listed in
  _MODAL_CLASSIFIERS — actuality isn't, so we additionally guard by
  scanning for an existing actuality(E) sibling.
  """
  if content_inner is None:
    content_inner = _collect_content_inner_vars(tree)
  if classified is None:
    # Tree-wide classifier scan (not just direct siblings) so a classifier
    # nested inside the event's own and-block still suppresses actuality.
    classified = _collect_classified_vars(tree)
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  if op == "and":
    e_vars = []
    seen_e = set()
    already_actual = set()
    for child in tree[1:]:
      if not isinstance(child, list) or not child:
        continue
      head = child[0] if isinstance(child[0], str) else None
      if (head == "isa" and len(child) >= 3 and child[1] == "activity"
          and isinstance(child[2], str)):
        if child[2] not in seen_e:
          e_vars.append(child[2])
          seen_e.add(child[2])
      elif (head == "actuality"
            and len(child) >= 2 and isinstance(child[1], str)):
        already_actual.add(child[1])
    new_children = [inject_actuality(c, content_inner, classified) if isinstance(c, list) else c
                    for c in tree[1:]]
    for ev in e_vars:
      # `classified` is the tree-wide classifier set, so a typical/capability
      # nested deeper in this event's and-block still suppresses actuality.
      if ev in classified or ev in content_inner or ev in already_actual:
        continue
      new_children.append(["actuality", ev])
    return [tree[0]] + new_children
  return [inject_actuality(c, content_inner, classified) if isinstance(c, list) else c
          for c in tree]


# ======== normally-through-forall lowering ========

def lower_normally_through_forall(tree):
  """Push `normally` from outside a `forall...implies` down to the consequent.

  Some LLMs (gemini) emit
    ["normally", ["forall", X, ["implies", A, B]]]
  ("normally the rule holds"), while others (claude) emit
    ["forall", X, ["implies", A, ["normally", B]]]
  ("for each X, normally if A then B").

  The two readings are intended to be equivalent, but only the latter
  clausifies into a useful per-entity defeasible rule (with a $block
  guard).  The outer-normally form clausifies into a Skolem witness for
  "the rule has an exception" which doesn't propagate to concrete
  entities.

  Rewrite the outer-normally form into the inner-normally form by walking
  the tree bottom-up.  Cases 225, 232 rely on this for gemini.
  """
  if not isinstance(tree, list) or not tree:
    return tree
  tree = [lower_normally_through_forall(c) if isinstance(c, list) else c
          for c in tree]
  if (len(tree) == 2 and tree[0] == "normally"
      and isinstance(tree[1], list) and len(tree[1]) >= 3
      and tree[1][0] == "forall"
      and isinstance(tree[1][2], list) and len(tree[1][2]) >= 3
      and tree[1][2][0] == "implies"):
    var = tree[1][1]
    impl = tree[1][2]
    antecedent = impl[1]
    consequent = impl[2]
    return ["forall", var, ["implies", antecedent, ["normally", consequent]]]
  return tree


# ======== degree presupposition injection ========

def inject_degree_presuppositions(tree):
  """Expand negated high-degree properties to include a presupposed positive assertion.

  Recursively walks *tree* (the raw Stage-2 JSON) and replaces every occurrence of
    ["not", ["has degree property", P, E, "high", C]]
  with
    ["and", ["has degree property", P, E, "none", C],
            ["not", ["has degree property", P, E, "high", C]]]

  "John is not very big" presupposes that John IS big (at the unmarked/none degree).
  The LLM pipelines only emit the negation; this adds the implicit positive assertion.
  """
  if not isinstance(tree, list) or len(tree) == 0:
    return tree
  # Recurse into children first (bottom-up).
  tree = [inject_degree_presuppositions(child) for child in tree]
  # Check for the target pattern.
  if (len(tree) == 2
      and tree[0] == "not"
      and isinstance(tree[1], list)
      and len(tree[1]) >= 4
      and tree[1][0] == "has degree property"
      and tree[1][3] == "high"):
    inner = tree[1]          # ["has degree property", P, E, "high", C]
    positive = list(inner)
    positive[3] = "none"     # ["has degree property", P, E, "none", C]
    return ["and", positive, tree]
  return tree


# ======== hoist misnested existentials ========

_VAR_PAT = re.compile(r'^[A-Z][A-Z0-9]?$')  # X, Y, Z, E, E1, X1, etc.

def _is_stage2_var(s):
  """True if s looks like a Stage-2 variable name (short uppercase)."""
  return isinstance(s, str) and _VAR_PAT.match(s) is not None

def _collect_free_vars(node, bound):
  """Collect Stage-2 variable names used free (not in bound) in node."""
  free = set()
  if not isinstance(node, list) or not node:
    return free
  op = node[0]
  if op in ("exists", "forall") and len(node) == 3:
    return _collect_free_vars(node[2], bound | {node[1]})
  if isinstance(op, str) and not isinstance(op, list):
    # Atom: check arguments (skip predicate name at index 0)
    for arg in node[1:]:
      if _is_stage2_var(arg) and arg not in bound:
        free.add(arg)
      elif isinstance(arg, list):
        free |= _collect_free_vars(arg, bound)
  else:
    for child in node:
      if isinstance(child, list):
        free |= _collect_free_vars(child, bound)
  return free

def hoist_misnested_exists(formula, bound=None):
  """Hoist existential quantifiers that bind variables used free in sibling conjuncts.

  Only processes ["and",...] nodes. Recurses into sub-formulas first (bottom-up),
  then checks the current and-node for misnested exists.
  """
  if bound is None:
    bound = set()
  if not isinstance(formula, list) or not formula:
    return formula
  op = formula[0]
  if op in ("exists", "forall") and len(formula) == 3:
    formula[2] = hoist_misnested_exists(formula[2], bound | {formula[1]})
    return formula
  if op == "implies" and len(formula) == 3:
    formula[1] = hoist_misnested_exists(formula[1], bound)
    formula[2] = hoist_misnested_exists(formula[2], bound)
    return formula
  if op != "and":
    # Recurse into children
    for i in range(len(formula)):
      if isinstance(formula[i], list):
        formula[i] = hoist_misnested_exists(formula[i], bound)
    return formula

  # op == "and": recurse into children first (bottom-up)
  for i in range(1, len(formula)):
    if isinstance(formula[i], list):
      formula[i] = hoist_misnested_exists(formula[i], bound)

  # Now check for misnested exists in this and-node
  changed = True
  while changed:
    changed = False
    conjuncts = formula[1:]  # re-read after mutations
    # Find exists conjuncts and free vars in non-exists conjuncts
    for i, conj in enumerate(conjuncts):
      if not (isinstance(conj, list) and len(conj) == 3
              and conj[0] == "exists"):
        continue
      var = conj[1]
      body = conj[2]
      # Check if var appears free in any other conjunct
      used_free = False
      for j, other in enumerate(conjuncts):
        if j == i:
          continue
        if var in _collect_free_vars(other, bound):
          used_free = True
          break
      if not used_free:
        continue
      # Collision check: var must not be already bound by enclosing scope
      if var in bound:
        continue
      # Hoist: remove the exists conjunct, merge body into and, wrap in exists
      idx = i + 1  # offset for "and" at index 0
      formula.pop(idx)
      # Merge body conjuncts into the and list
      if isinstance(body, list) and body and body[0] == "and":
        for bc in body[1:]:
          formula.append(bc)
      else:
        formula.append(body)
      # Wrap in exists
      formula = ["exists", var, formula]
      # Update bound for next iteration
      bound = bound | {var}
      changed = True
      break  # restart scan after mutation
    if changed and isinstance(formula, list) and formula[0] == "exists":
      # The and-node is now formula[2]; continue hoisting inside it
      formula[2] = hoist_misnested_exists(formula[2], bound)
      break

  return formula


# ======== spurious "can" removal ========

_MODAL_WORDS = frozenset({
  "can", "could", "able", "capable", "possible", "allowed",
  "permitted", "may", "might", "ability",
})

def strip_spurious_can(formula, asu_text):
  """Remove ["can", X, E] from event queries when no modal language is present.

  Only fires when:
  - The ASU text contains no modal words
  - ["can", X, E] appears in an ["and",...] conjunction inside question/ask
  - The same conjunction contains ["isa","activity",E] and ["has actor",E,X]
  - Both X and E are existentially quantified
  """
  if not asu_text or not isinstance(formula, list) or len(formula) < 2:
    return formula
  # Check for modal language in ASU text
  text_lower = asu_text.lower()
  for mw in _MODAL_WORDS:
    if mw in text_lower:
      return formula
  # Walk and strip
  _strip_can_walk(formula, set())
  return formula

def _strip_can_walk(node, existential_vars):
  """Recursively walk formula, collecting existential vars, stripping can."""
  if not isinstance(node, list) or not node:
    return
  op = node[0]
  if op == "exists" and len(node) == 3:
    new_vars = existential_vars | {node[1]}
    _strip_can_walk(node[2], new_vars)
    return
  if op in ("question", "ask"):
    for child in node[1:]:
      _strip_can_walk(child, existential_vars)
    return
  if op == "and":
    _try_remove_can(node, existential_vars)
    for child in node[1:]:
      if isinstance(child, list):
        _strip_can_walk(child, existential_vars)
    return
  for child in node:
    if isinstance(child, list):
      _strip_can_walk(child, existential_vars)

def _try_remove_can(and_node, existential_vars):
  """If and_node contains a spurious ["can",X,E], remove it."""
  conjuncts = and_node[1:]
  can_idx = None
  can_x = None
  can_e = None
  for i, c in enumerate(conjuncts):
    if (isinstance(c, list) and len(c) >= 3
        and c[0] == "can" and isinstance(c[1], str) and isinstance(c[2], str)):
      can_idx = i + 1  # offset by 1 for "and" at index 0
      can_x = c[1]
      can_e = c[2]
      break
  if can_idx is None:
    return
  # Check X and E are existentially quantified
  if can_x not in existential_vars or can_e not in existential_vars:
    return
  # Check for isa("activity", E) and has_actor(E, X) in same conjunction
  has_isa_activity = False
  has_actor = False
  for c in conjuncts:
    if not isinstance(c, list):
      continue
    if (len(c) >= 3 and c[0] == "isa" and c[1] == "activity" and c[2] == can_e):
      has_isa_activity = True
    if (len(c) >= 3 and c[0] == "has actor" and c[1] == can_e and c[2] == can_x):
      has_actor = True
  if has_isa_activity and has_actor:
    and_node.pop(can_idx)


# ======== pre-clausification polarity flip ========

def flip_polarity_atom(frm):
  """Toggle the sign of a single literal (add/remove "-" prefix on predicate)."""
  if not isinstance(frm, list) or not frm:
    return frm
  pred = frm[0]
  if not isinstance(pred, str):
    return frm
  if pred.startswith("-"):
    return [pred[1:]] + frm[1:]
  return ["-" + pred] + frm[1:]


def negate_inner(frm):
  """Negate the innermost content of a formula (used for consequent negation).

  Strips outermost exists/and wrappers, then flips the atom or normally body.
  Returns the negated form for use inside a normally wrapper.
  """
  if not isinstance(frm, list) or not frm:
    return ["not", frm]
  op = frm[0]
  if op == "exists" and len(frm) >= 3:
    return ["forall", frm[1], ["not", frm[2]]]
  if op == "and":
    if len(frm) >= 3:
      return [op] + list(frm[1:-1]) + [negate_inner(frm[-1])]
    return frm
  if op == "normally":
    if len(frm) >= 2:
      return [op, ["not", frm[1]]]
    return frm
  if op == "forall" and len(frm) >= 3:
    return [op, frm[1], negate_inner(frm[2])]
  if op == "implies" and len(frm) >= 3:
    return [op, frm[1], negate_inner(frm[2])]
  if op == "not" and len(frm) >= 2:
    return frm[1]
  return flip_polarity_atom(frm)


# Non-atomic operators: these are connectives, wrappers, or other compound
# formulas that should be negated by wrapping in ["not", ...] rather than
# flipping a predicate prefix.  The clausifier handles the NNF distribution.
_NON_ATOMIC_OPS = frozenset({
  "and", "or", "not", "implies", "equivalent", "xor",
  "normally", "typically", "holds", "question", "ask",
})

def negate_consequent(formula):
  """Negate the consequent of a rule formula before clausification.

  Handles:
    ["implies", A, B]            → ["implies", A, negate_inner(B)]
    ["forall", X, F]             → ["forall", X, negate_consequent(F)]
    ["exists", X, F]             → ["forall", X, ["not", F]]
    non-atomic formula           → ["not", formula]  (clausifier handles via NNF)
    bare atom ["pred", ...]      → ["-pred", ...]
  """
  if not isinstance(formula, list) or not formula:
    return formula
  op = formula[0]
  if not isinstance(op, str):
    return ["not", formula]
  if op == "implies" and len(formula) >= 3:
    return [op, formula[1], negate_inner(formula[2])]
  if op == "forall" and len(formula) >= 3:
    return [op, formula[1], negate_consequent(formula[2])]
  if op == "exists" and len(formula) >= 3:
    return ["forall", formula[1], ["not", formula[2]]]
  if op in _NON_ATOMIC_OPS:
    # "not" here gives double-negation: ["not",["not",F]] → clausifier eliminates
    return ["not", formula]
  return flip_polarity_atom(formula)


# ======== query-side specific-noun isa injection ========
# Mirror of the assertion-side _build_entity_category_clauses: when a Stage-2
# question formula constrains an existential with isa(CAT, X) but Stage-1 has
# a unique generic entity with category=CAT and id!=CAT, add isa(id, X) as
# an extra conjunct so the query reflects the user's specific noun.
# Covers gemini's tendency to emit the category instead of the specific noun
# in query bodies (case 136: "Did a man buy a car?" → isa(person,X) only).

_WH_PLACEHOLDERS = frozenset({
  "who", "what", "which", "whom", "whose",
  "where", "when", "why", "how",
})


def _build_query_cat_to_id(asu):
  """From a Stage-1 ASU, build {category: specific_id} for generic entities
  that pass all the conservative guards.  Only categories with a UNIQUE
  matching generic entity are kept.  Returns {} when no entry qualifies."""
  if not isinstance(asu, dict):
    return {}
  cat_to_ids = {}
  for ent in asu.get("entities", []) or []:
    if not isinstance(ent, dict):
      continue
    if ent.get("type") != "generic":
      continue
    eid = ent.get("id")
    cat = ent.get("category")
    if not (isinstance(eid, str) and isinstance(cat, str)):
      continue
    if not eid or not cat:
      continue
    if eid.lower() == cat.lower():
      continue                         # already specific
    if eid.lower() in _WH_PLACEHOLDERS:
      continue                         # wh-placeholder
    if " " in eid:
      continue                         # multi-word id
    if eid[:1].isupper():
      continue                         # proper noun
    cat_to_ids.setdefault(cat, []).append(eid)
  return {cat: ids[0] for cat, ids in cat_to_ids.items() if len(ids) == 1}


def _inject_isa_into_and(body, var, cat_to_id):
  """If body is ['and', ...args] with EXACTLY ONE isa(CAT, var) literal where
  CAT is in cat_to_id, return a new 'and' with isa(cat_to_id[CAT], var)
  appended.  Otherwise return body unchanged.

  The single-isa requirement is the key safety guard: if Stage-2 already
  emits multiple isa constraints for var, we don't interfere."""
  if not (isinstance(body, list) and len(body) >= 2 and body[0] == "and"):
    return body
  args = body[1:]
  isa_cats_for_var = []
  for arg in args:
    if (isinstance(arg, list) and len(arg) >= 3 and
        arg[0] == "isa" and arg[2] == var and isinstance(arg[1], str)):
      isa_cats_for_var.append(arg[1])
  if len(isa_cats_for_var) != 1:
    return body
  cat = isa_cats_for_var[0]
  if cat not in cat_to_id:
    return body
  specific = cat_to_id[cat]
  if specific == cat:
    return body
  # Defensive: also skip if the specific already appears somewhere (shouldn't
  # given len==1 check, but harmless).
  if specific in isa_cats_for_var:
    return body
  return ["and"] + list(args) + [["isa", specific, var]]


def _inject_walk(node, cat_to_id):
  """Recurse through the formula tree.  Only 'exists VAR BODY' triggers
  injection on VAR; other structural nodes pass through unchanged except
  for recursion into children."""
  if not isinstance(node, list) or not node:
    return node
  op = node[0]
  if not isinstance(op, str):
    return node
  if op == "exists" and len(node) == 3:
    var = node[1]
    new_body = _inject_walk(node[2], cat_to_id)
    new_body = _inject_isa_into_and(new_body, var, cat_to_id)
    return [op, var, new_body]
  # Recurse into other structural nodes (question, ask, holds, and, or, not,
  # implies, forall, @time, etc.).  Leave children that are not lists alone.
  return [op] + [_inject_walk(el, cat_to_id) if isinstance(el, list) else el
                 for el in node[1:]]


def inject_query_specific_noun_isas(formula, asu):
  """Add isa(specific_noun, X) constraints for generic query entities whose
  Stage-1 id differs from category.  Mirrors _build_entity_category_clauses
  on the assertion side.  Conservative: only fires when Stage-1 has a
  UNIQUE matching generic entity and Stage-2 emitted exactly one isa for
  the existential variable.  See also: _inject_isa_into_and.

  No-op when asu is missing, has no qualifying generic entities, or the
  formula lacks a matching 'exists VAR, (and ... isa(CAT, VAR) ...)' pattern.
  """
  cat_to_id = _build_query_cat_to_id(asu)
  if not cat_to_id:
    return formula
  return _inject_walk(formula, cat_to_id)


# ======== category-isa filter (plan fix 3) ========

def _asu_text_words(asu):
  """Lowercased word bag of an ASU's text, for the 'is this class actually
  mentioned?' test."""
  if not isinstance(asu, dict):
    return set()
  text = asu.get("text")
  if not isinstance(text, str):
    return set()
  return set(re.findall(r"[a-z]+", text.lower()))


def _class_mentioned(cls, words):
  """Stem-tolerant containment: 'animals' in the text protects class 'animal'."""
  if not isinstance(cls, str) or not cls:
    return False
  for part in re.findall(r"[a-z]+", cls.lower()):
    if part in words:
      continue
    stemmed = {w for w in words}
    hit = False
    for w in stemmed:
      if w == part or w.rstrip("s") == part or w == part + "s" \
         or w == part + "es" or (part.endswith("y") and w == part[:-1] + "ies"):
        hit = True
        break
    if not hit:
      return False
  return True


def _collect_isa_by_entity(node, out):
  """Map entity -> list of classes positively asserted for it in this tree."""
  if not isinstance(node, list) or not node:
    return
  if isinstance(node[0], str):
    if node[0] == "isa" and len(node) >= 3 and isinstance(node[2], str):
      out.setdefault(node[2], []).append(node[1])
    for child in node[1:]:
      _collect_isa_by_entity(child, out)
  else:
    for child in node:
      _collect_isa_by_entity(child, out)


def _drop_isa_conjuncts(node, victims):
  """Remove ['isa', C, E] conjuncts listed in victims from `and` blocks."""
  if not isinstance(node, list) or not node:
    return node
  if not isinstance(node[0], str):
    return [_drop_isa_conjuncts(el, victims) for el in node]
  op = node[0]
  if op == "and":
    kept = []
    for el in node[1:]:
      if (isinstance(el, list) and len(el) >= 3 and el[0] == "isa"
          and isinstance(el[1], str) and isinstance(el[2], str)
          and (el[1], el[2]) in victims):
        continue
      kept.append(_drop_isa_conjuncts(el, victims))
    if not kept:
      return None
    if len(kept) == 1:
      return kept[0]
    return ["and"] + kept
  return [op] + [_drop_isa_conjuncts(el, victims) if isinstance(el, list) else el
                 for el in node[1:]]


def drop_category_isa_conjuncts(logic, s1_json):
  """(fix 3) Drop an isa conjunct that merely restates a Stage-1 entity
  `category` annotation the sentence never states.

  Gemini's uncertainty cluster (1481/1483/1487/1508/1512) fails because
  Stage 2 turns the metadata `{"id":"John 1","category":"animal"}` into an
  asserted `isa(animal, John 1)` for the sentence "John 1 is an elephant."
  The rule under test says elephants are NOT animals, so the injected fact
  proves the question outright.

  The pipeline already treats category isa as ITS OWN business:
  build_entity_category_clauses() injects those facts and deliberately skips
  entities Stage 2 typed.  This filter restores that invariant when Stage 2
  smuggles the category into its own package.

  Fires only when all hold, so no entity is ever left untyped:
    * the class equals the entity's Stage-1 category,
    * the class word does not occur in that ASU's text (stem-tolerant),
    * another positive isa for the same entity survives in the package.
  """
  from globals import options as _opts
  if (_opts.get("nofix_categoryisa") or not isinstance(logic, list)
      or not isinstance(s1_json, list)):
    return logic
  # entity id -> (category, ASU text words), per unit
  asu_by_uid = {}
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for u in pkg.get("units", []) or []:
      if isinstance(u, dict) and u.get("unit_id"):
        asu_by_uid[str(u.get("unit_id"))] = u

  # Only a category the QUESTION itself asserts about the same entity may be
  # dropped.  That is the shape this repair exists for: "John is an elephant."
  # + "John is an animal?" — the question package contains isa(animal, John 1)
  # as its goal, and Stage 2 smuggling the same atom into a premise settles the
  # question by fiat.  Anything looser mis-fires: a word test on the query text
  # dropped Harry's basic isa(animal, …) typing because the question mentioned
  # "an animal with a backbone" (old-model control, gpt FOLIO 101), and basic
  # types are what the problem's rules quantify over.
  question_isa_pairs = set()

  def _collect_question_isa(node):
    if not isinstance(node, list) or not node:
      return
    if isinstance(node[0], str):
      head = node[0].lstrip("-")
      if head == "isa" and len(node) >= 3 and isinstance(node[1], str) \
         and isinstance(node[2], str):
        question_isa_pairs.add((node[1], node[2]))
      for ch in node[1:]:
        _collect_question_isa(ch)
    else:
      for ch in node:
        _collect_question_isa(ch)

  for item in logic:
    if (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"
        and isinstance(item[2], list) and item[2]
        and item[2][0] in ("question", "ask")):
      _collect_question_isa(item[2])

  changed = False
  out = []
  for item in logic:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      out.append(item)
      continue
    sid = str(item[1])
    asu = asu_by_uid.get(sid)
    if asu is None:
      out.append(item)
      continue
    cats = {}
    for ent in asu.get("entities", []) or []:
      if isinstance(ent, dict) and isinstance(ent.get("id"), str):
        cats[ent["id"]] = ent.get("category")
    if not cats:
      out.append(item)
      continue
    words = _asu_text_words(asu)
    isa_map = {}
    _collect_isa_by_entity(item[2], isa_map)
    victims = set()
    for entity, classes in isa_map.items():
      cat = cats.get(entity)
      if not isinstance(cat, str) or not cat:
        continue
      if _class_mentioned(cat, words):
        continue           # the sentence really says it
      if (cat, entity) not in question_isa_pairs:
        continue           # not the question's own goal atom — keep the typing
      matching = [c for c in classes if c == cat]
      others = [c for c in classes if c != cat]
      if matching and others:
        victims.add((cat, entity))
    if not victims:
      out.append(item)
      continue
    body = _drop_isa_conjuncts(item[2], victims)
    if body is None or body == item[2]:
      out.append(item)
      continue
    changed = True
    out.append([item[0], item[1], body] + list(item[3:]))
  return out if changed else logic


# ======== class-name case folding (plan fix 7c) ========

def fold_class_name_case(logic):
  """(fix 7c) Unify class constants that differ only in capitalization.

  Stage 2 sometimes writes a class one way in a rule and another in the
  question ("Estonian city" vs "estonian city", claude 1242), which blocks
  unification.  Folds to the first-seen spelling.

  Scope is deliberately narrow: only the CLASS position of `isa` — never
  entity ids, URL constants or predicate names, where case can be meaningful.
  """
  from globals import options as _opts
  if _opts.get("nofix_casefold") or not isinstance(logic, list):
    return logic
  seen = {}
  order = []

  def scan(node):
    if not isinstance(node, list) or not node:
      return
    if isinstance(node[0], str):
      if node[0] == "isa" and len(node) >= 3 and isinstance(node[1], str):
        key = node[1].lower()
        if key not in seen:
          seen[key] = node[1]
          order.append(key)
      for child in node[1:]:
        scan(child)
    else:
      for child in node:
        scan(child)

  scan(logic)
  remap = {}
  for key, first in seen.items():
    remap[key] = first

  changed = [False]

  def fold(node):
    if not isinstance(node, list) or not node:
      return node
    if not isinstance(node[0], str):
      return [fold(el) for el in node]
    if node[0] == "isa" and len(node) >= 3 and isinstance(node[1], str):
      canon = remap.get(node[1].lower())
      if canon is not None and canon != node[1]:
        changed[0] = True
        return [node[0], canon] + [fold(el) if isinstance(el, list) else el
                                   for el in node[2:]]
    return [node[0]] + [fold(el) if isinstance(el, list) else el
                        for el in node[1:]]

  folded = fold(logic)
  return folded if changed[0] else logic
