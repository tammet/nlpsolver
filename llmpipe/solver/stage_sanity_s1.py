# Stage-1 ASU-shape sanity checks (see stage_sanity.py facade).
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

import re
from stage_sanity_core import Issue, safe_json



# ======== Stage-1 missing-wh-placeholder check ========
#
# Detects WH-question units whose Stage-1 entities list is missing a
# wh_placeholder entity.  The Stage-1 instructions require WH queries to
# include {id: "entity", type: "generic", wh_placeholder: true} and to
# transform the unit's text per the question-word rules (What → "Which
# entity", etc.).  Some LLMs (notably gpt) skip the entity injection and
# leave the text unchanged, which then makes Stage-2 fall back to a yes/no
# encoding (case 48 with gpt: "What is the length of the red car?" became
# a yes/no with a hallucinated 80).

# Wh-words that mark the start of a wh-question.  Detection is
# case-insensitive and applied to the leading word of the raw / text
# field.  "How" + "many" is treated specially: "How many ..." should keep
# numeric wording per the Stage-1 instructions, but still needs a
# placeholder to give Stage-2 a binding slot.
_WH_LEAD_WORDS = frozenset({
  "what", "which", "who", "whom", "whose",
  "where", "when", "why", "how",
})




def _starts_with_wh(text):
  """Return True if the leading word of `text` is a wh-question word."""
  if not isinstance(text, str):
    return False
  s = text.strip()
  if not s:
    return False
  # Take the first word, strip punctuation/quotes.
  for sep in (" ", "\t", "\n"):
    idx = s.find(sep)
    if idx > 0:
      s = s[:idx]
      break
  s = s.strip(".,!?;:'\"()[]{}")
  return s.lower() in _WH_LEAD_WORDS




def _has_wh_placeholder(unit):
  """Return True if any entity in the unit has wh_placeholder=True."""
  if not isinstance(unit, dict):
    return False
  for ent in unit.get("entities", []) or []:
    if isinstance(ent, dict) and ent.get("wh_placeholder"):
      return True
  return False




def _leading_word(text):
  """Lowercased first word of `text`, punctuation/quotes stripped, or ""."""
  if not isinstance(text, str):
    return ""
  s = text.strip()
  for sep in (" ", "\t", "\n"):
    idx = s.find(sep)
    if idx > 0:
      s = s[:idx]
      break
  return s.strip(".,!?;:'\"()[]{}").lower()




# Auxiliaries that lead a yes/no question.  A query starting with one of
# these expects a yes/no answer, so it must NOT carry a wh_placeholder.
_YESNO_LEAD_AUX = frozenset({
    "did", "does", "do", "is", "are", "was", "were", "has", "have", "had",
    "can", "could", "will", "would", "shall", "should", "may", "might",
    "must",
})



_WH_ANY_WORDS = _WH_LEAD_WORDS | frozenset({"whom"})




def _contains_wh_word(text):
  """True if any token in `text` is a wh-word.  Catches wh-questions whose
  wh-word is internal after a Stage-1 rewrite, e.g. "Is Ellen afraid of
  which entity?" — which leads with the auxiliary "Is" but is still a
  wh-question."""
  if not isinstance(text, str):
    return False
  for tok in text.replace("?", " ").replace(",", " ").split():
    if tok.strip(".,!?;:'\"()[]{}").lower() in _WH_ANY_WORDS:
      return True
  return False




def _check_stage1_missing_wh_placeholder(s1_json):
  """Detect Stage-1 query units with a wh-leading text but no
  wh_placeholder entity.  Triggers a corrective retry asking the LLM to
  add the placeholder and apply the question-word transformation to the
  unit's `text` field."""
  if not isinstance(s1_json, list):
    return []
  issues = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "")
    raw_text = raw if isinstance(raw, str) else ""
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict):
        continue
      if unit.get("type") != "query":
        continue
      if _has_wh_placeholder(unit):
        continue
      utext = unit.get("text", "") if isinstance(unit.get("text", ""), str) else ""
      # A unit is wh if either its own text or the parent raw begins with
      # a wh-word.  Most reliable signal is the unit's text after Stage-1
      # rewrites; raw is the user's original wording.
      if not (_starts_with_wh(utext) or _starts_with_wh(raw_text)):
        continue
      uid = unit.get("unit_id", "?")
      issues.append(Issue(
        kind="missing_wh_placeholder",
        location="@id:" + str(uid),
        description=("Unit " + str(uid) + " has type='query' and a "
                     "wh-question text (\"" + (utext or raw_text) +
                     "\"), but its entities list contains no "
                     "wh_placeholder entry. Wh-questions MUST include a "
                     "placeholder entity such as "
                     "{\"id\":\"entity\",\"type\":\"generic\","
                     "\"wh_placeholder\":true} (or "
                     "{\"id\":<noun>,\"type\":\"generic\","
                     "\"wh_placeholder\":true} when the question names a "
                     "category, e.g. \"Which person\" → id \"person\"). "
                     "Also transform the unit's `text` field per the "
                     "Question Word Transformation rules: What/Where → "
                     "\"Which entity ...\", Who/Whom → \"Which entity "
                     "...\", When → keep \"When\", How many → keep "
                     "numeric wording."),
        evidence=safe_json(unit),
      ))
  return issues




# ======== Stage-1 entity-used-as-location check ========

def _collect_concrete_entity_ids(unit):
  """Return the set of concrete-entity IDs declared in a unit's
  entities list. Generic / wh-placeholder entities are skipped."""
  out = set()
  if not isinstance(unit, dict):
    return out
  for ent in unit.get("entities", []) or []:
    if not isinstance(ent, dict):
      continue
    if ent.get("type") != "concrete":
      continue
    eid = ent.get("id")
    if isinstance(eid, str) and eid:
      out.add(eid)
  return out




def _check_stage1_entity_used_as_location(s1_json):
  """Detect Stage-1 units where the `location` field is a concrete-entity
  ID declared in the same unit's `entities` list.

  Stage-1's `location` field is the *scene* where the unit's situation
  occurs (e.g. "the kitchen", "the park", "outside"). It must NOT be a
  concrete object that participates in a spatial relation as a secondary
  argument — that belongs in the actions/relations, not in the
  scene-location.

  Symptom: lc_ctxt injects `location` into the `$ctxt` location slot, so
  ASU pairs that should share a context end up with distinct entity
  constants there. Mutex / X2 axioms cannot then unify the two contexts.
  See gemini's case 148 trace (assertion ctxt has "table 3", question
  ctxt has "floor 4" — contexts don't unify, X2 cannot fire).
  """
  if not isinstance(s1_json, list):
    return []
  issues = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict):
        continue
      loc = unit.get("location")
      if not isinstance(loc, str) or not loc:
        continue
      concrete_ids = _collect_concrete_entity_ids(unit)
      if loc not in concrete_ids:
        continue
      uid = unit.get("unit_id", "?")
      issues.append(Issue(
        kind="entity_used_as_location",
        location="@id:" + str(uid),
        description=("Unit " + str(uid) + " has location=\"" + loc +
                     "\" which is a concrete entity declared in the "
                     "same unit's entities list. The `location` field "
                     "is for the SCENE / place where the situation "
                     "occurs (e.g. \"the kitchen\", \"the park\", "
                     "\"outside\"). It must NOT be a concrete object "
                     "that participates in a spatial relation as the "
                     "secondary argument. If the only spatial info is "
                     "\"X is on Y\" (or under/in/etc.), put that "
                     "preposition + entity in the relevant action's "
                     "roles (e.g. roles.location with location_prep) "
                     "and OMIT the unit-level `location` field. If "
                     "there is a separate scene location, replace "
                     "\"" + loc + "\" with that scene name. Do not "
                     "use the concrete entity " + loc + " as the "
                     "scene location."),
        evidence=safe_json(unit),
      ))
  return issues




# ======== Stage-1 pronoun-as-class check ========
#
# An indefinite person-pronoun ("someone", "anybody", ...) is NOT a noun /
# class — it denotes an (existentially or universally quantified) person.
# Some LLMs (gpt on case 626) declare it as a Stage-1 entity with id
# "someone", which Stage-2 then turns into a phantom `isa("someone", X)`
# class atom that nothing ever populates -> the question is unprovable.
# The fix is to retry Stage-1 asking for the common noun "person" instead;
# this leaves both stages clean (vs. patching the leaked class downstream).
#
# Scope: the six PERSON pronouns only.  Thing-pronouns (something/anything)
# are excluded — they map to "thing", which is not a populated class, so a
# retry to "thing" would relocate the same dead-end.  Negative pronouns
# (nobody/nothing) are excluded too — they carry polarity.

_PRONOUN_CLASS_PERSON = frozenset({
    "someone", "somebody", "anyone", "anybody", "everyone", "everybody",
})



_ENTITY_NUM_SUFFIX_RE = re.compile(r"\s*\d+$")




def _entity_id_base(eid):
  """Lowercase an entity id with any trailing number stripped:
  "someone 1" -> "someone", "Someone" -> "someone"."""
  if not isinstance(eid, str):
    return ""
  return _ENTITY_NUM_SUFFIX_RE.sub("", eid).strip().lower()




def _check_stage1_pronoun_as_class(s1_json):
  """Flag a Stage-1 QUERY unit that declares an entity whose id is an
  indefinite person-pronoun used as a class (case 626 gpt).  Triggers a
  corrective retry asking the LLM to type the entity as "person".

  Restricted to query units: in a question ("Did someone go?") the pronoun
  is an existential person and the leaked class makes the query unprovable.
  In an assertion/rule it is usually the bound variable of a universal
  ("If someone is X then Y") where renaming the class is unnecessary and a
  retry can damage the rule (regressed cases 1390/1608)."""
  if not isinstance(s1_json, list):
    return []
  issues = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict):
        continue
      if unit.get("type") != "query":
        continue
      for ent in unit.get("entities", []) or []:
        if not isinstance(ent, dict):
          continue
        base = _entity_id_base(ent.get("id", ""))
        if base in _PRONOUN_CLASS_PERSON:
          uid = unit.get("unit_id", "?")
          issues.append(Issue(
            kind="pronoun_as_class",
            location="@id:" + str(uid),
            description=("Unit " + str(uid) + " declares an entity with id "
                         "\"" + str(ent.get("id", "")) + "\", but \"" + base
                         + "\" is an indefinite pronoun, not a noun / class. "
                         "It denotes a PERSON (someone/somebody/anyone/"
                         "anybody/everyone/everybody all mean \"a person\"). "
                         "Re-declare the entity as a generic person: use the "
                         "common noun \"person\" as the entity id/category "
                         "(type \"generic\"), not the pronoun. Keep the "
                         "existential/universal reading via the question "
                         "form / quantification, not by naming the class "
                         "after the pronoun."),
            evidence=safe_json(ent),
          ))
          break                       # one issue per unit
  return issues




# ======== Stage-1 spurious-wh-placeholder check ========
#
# The converse of _check_stage1_missing_wh_placeholder: a YES/NO query
# (leading auxiliary "Did"/"Is"/...) that wrongly carries a wh_placeholder
# entity, marking it as a wh-question.  Stage-2 then encodes it as an
# `ask X` (askvars) query solving FOR the placeholder, which needs a
# determinate witness — so an indefinite/disjunctive subject yields no
# binding (case 626 claude: "Did someone go?" -> ask X -> Unknown).  Retry
# asking for a plain yes/no encoding without the wh-target.

def _check_stage1_spurious_wh_placeholder(s1_json):
  """Flag a yes/no query unit (leading auxiliary) that carries a
  wh_placeholder entity, and retry asking for a yes/no encoding."""
  if not isinstance(s1_json, list):
    return []
  issues = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict):
        continue
      if unit.get("type") != "query":
        continue
      if not _has_wh_placeholder(unit):
        continue
      text = unit.get("text") or pkg.get("raw", "")
      if _leading_word(text) not in _YESNO_LEAD_AUX:
        continue                      # genuine wh-question, leave alone
      if _contains_wh_word(text):
        continue                      # wh-word present (e.g. "... which
                                      # entity?") -> real wh-question
      uid = unit.get("unit_id", "?")
      issues.append(Issue(
        kind="spurious_wh_placeholder",
        location="@id:" + str(uid),
        description=("Unit " + str(uid) + " (\"" + str(text) + "\") is a "
                     "YES/NO question — it begins with the auxiliary \""
                     + _leading_word(text) + "\" and expects a yes/no "
                     "answer. But it declares a wh_placeholder entity, "
                     "marking it as a wh-question (who/what/which). Remove "
                     "the wh_placeholder flag and do NOT rewrite the text "
                     "into a \"Which ...\" form; encode it as a plain yes/no "
                     "question. An indefinite subject like \"someone\" is an "
                     "existentially quantified person (\"a person\"), not a "
                     "wh-target to solve for."),
        evidence=safe_json(unit),
      ))
  return issues




# ======== Stage-1 split-conditional (comma mis-segmentation) check ========
#
# A single conditional / adverbial sentence "If A, B?" (or "When A, B.")
# must be ONE Stage-1 package, but some LLMs (gpt case 384) split it at the
# internal comma into two packages -- a dangling subordinate-clause
# fragment whose raw ends in a comma ("If John has three cars,") plus the
# main clause in the next package ("John has three cars?").  Stage-2 then
# encodes the fragment as a (vacuous) rule and the main clause as a
# separate query, so the real conditional question is never asked ->
# Unknown.
#
# Detection (all must hold):
#   1. A package whose raw, stripped, ENDS WITH a comma.
#   2. Its first word is a subordinating conjunction (if/when/while/...) --
#      it introduces an adverbial clause that needs a main clause.
#   3. There is a following package (the split-off main clause).
# The retry asks Stage-1 to keep the comma-joined clauses in ONE package.

_SUBORDINATORS = frozenset({
    "if", "when", "whenever", "while", "unless", "although", "though",
    "because", "since", "after", "before", "until", "once", "provided",
    "whether", "as", "even", "supposing", "assuming",
})




def _check_stage1_split_conditional(s1_json):
  """Flag a Stage-1 package that is a dangling subordinate clause (raw ends
  in a comma, first word a subordinating conjunction) with a following
  package holding the main clause -- a single conditional/adverbial
  sentence wrongly split at its internal comma.  See case 384 (gpt)."""
  if not isinstance(s1_json, list):
    return []
  issues = []
  n = len(s1_json)
  for idx, pkg in enumerate(s1_json):
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "")
    if not isinstance(raw, str):
      continue
    stripped = raw.strip()
    if not stripped.endswith(","):
      continue
    parts = stripped.split(None, 1)
    if not parts:
      continue
    first = parts[0].strip(".,!?;:'\"()[]{}").lower()
    if first not in _SUBORDINATORS:
      continue
    if idx + 1 >= n:
      continue                          # no following package to merge with
    nxt = s1_json[idx + 1]
    nxt_raw = nxt.get("raw", "") if isinstance(nxt, dict) else ""
    issues.append(Issue(
      kind="split_conditional_sentence",
      location="package[" + str(idx) + "]",
      description=("Stage-1 split the input at an internal comma: this "
                   "package's raw text (\"" + stripped + "\") is a dangling "
                   "subordinate clause that ends in a comma and has no main "
                   "clause, while the following package (\"" + str(nxt_raw)
                   + "\") holds the main clause. A subordinating conjunction "
                   "like \"if\" / \"when\" / \"while\" introduces an "
                   "adverbial clause that belongs to the SAME sentence as "
                   "its main clause -- they must NOT be split into separate "
                   "packages. Re-segment so the comma-joined clauses form "
                   "ONE package. If that sentence is a conditional QUESTION "
                   "(it ends with '?'), put both clauses in a SINGLE query "
                   "unit covering the whole \"If ... , ... ?\" conditional "
                   "(one question over the if-then), NOT a separate rule "
                   "package plus a separate query package."),
      evidence=safe_json([stripped, "+", nxt_raw]),
    ))
  return issues




# ======== public API ========

def check_stage1(s1_json):
  """Run all registered Stage-1 sanity checks and return the combined
  issue list."""
  issues = []
  issues.extend(_check_stage1_missing_wh_placeholder(s1_json))
  issues.extend(_check_stage1_entity_used_as_location(s1_json))
  issues.extend(_check_stage1_pronoun_as_class(s1_json))
  issues.extend(_check_stage1_spurious_wh_placeholder(s1_json))
  issues.extend(_check_stage1_split_conditional(s1_json))
  return issues
