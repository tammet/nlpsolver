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




# ======== dropped-question-negation check (prenorm-negation-fallback) ========
#
# A yes/no conclusion carrying sentential negation ("X is not a Y", "X does
# not V", "neither ... nor") must keep that negation so Stage-2 negates the
# WHOLE predication.  Under -prenorm (the -abstract-max default), the pre-Stage-1
# normalization LLM strips the negation and rewrites the conclusion into the
# POSITIVE question ("Yuri is not an American ..." -> "Is Yuri an American
# ...?"); Stage-1 then faithfully parses that positive input and every
# downstream stage answers the opposite question, flipping the final answer
# (FOLIO cases 80, 127, 189, 200).  Verified: gpt's Stage-1 preserves the
# negation when given the ORIGINAL text, so the recovery is to re-parse from the
# original (pre-prenorm) wording -- done at the parse_text level.
#
# This checker is the detector for that fallback: it compares the ORIGINAL
# question text (orig_text) against the produced query unit.  The negation must
# be read off orig_text because prenorm rewrote it away in both the unit `text`
# AND the package `raw`.
#
# Detection (all must hold):
#   1. The original question sentence (a "?"-terminated sentence in orig_text)
#      contains a sentential-negation cue.
#   2. A query unit exists whose OWN text carries NO negation cue -- i.e. the
#      negation was fully DROPPED, not merely mis-scoped.  If the unit text
#      still has a "not", the LLM kept some negation; a scope error there is a
#      different, out-of-scope problem and must NOT trigger a blind retry.
# The zero-negation-in-unit guard is what makes this safe: it fires only on a
# TOTAL drop, so the retry can never introduce a double negation.

_NEG_CUE_RE = re.compile(
    r"\b(not|never|neither|nor|none|cannot)\b|n['’]t\b", re.IGNORECASE)

# Function words dropped when extracting the content tokens that anchor a query
# unit's question clause inside the (possibly run-on) original sentence.
_QUESTION_STOPWORDS = frozenset({
  "is", "are", "was", "were", "am", "be", "been", "being", "do", "does", "did",
  "has", "have", "had", "will", "would", "shall", "should", "can", "could",
  "may", "might", "must", "a", "an", "the", "of", "in", "on", "at", "for",
  "to", "with", "and", "or", "not", "that", "this", "these", "those", "his",
  "her", "its", "their", "he", "she", "it", "they", "them", "him", "who",
  "whom", "whose", "which", "what", "where", "when", "why", "how", "as", "by",
  "from", "any", "some", "no",
})


def _has_negation_cue(text):
  """True if `text` contains a sentential-negation cue word."""
  return bool(isinstance(text, str) and _NEG_CUE_RE.search(text))


def _question_sentences(text):
  """Return the list of '?'-terminated sentences in the raw input, each
  trimmed to the fragment following the previous sentence terminator."""
  if not isinstance(text, str):
    return []
  out = []
  buf = []
  for ch in text:
    buf.append(ch)
    if ch in ".?!":
      seg = "".join(buf).strip()
      if seg.endswith("?"):
        out.append(seg)
      buf = []
  tail = "".join(buf).strip()
  if tail.endswith("?"):
    out.append(tail)
  return out


def _content_tokens(text):
  """Lowercase alphanumeric content tokens of `text`, minus function words and
  bare numbers (Stage-1 entity-id suffixes like the '1' in 'Yuri 1')."""
  out = []
  for w in re.findall(r"[a-z0-9]+", (text or "").lower()):
    if w.isdigit() or w in _QUESTION_STOPWORDS:
      continue
    out.append(w)
  return out


def _question_clause_negated(orig_q, unit_text):
  """True if the actual question clause of `orig_q` carries a negation cue.

  FOLIO inputs sometimes omit the period between the last premise and the
  conclusion, so `orig_q` can be a run-on premise+question whose negation
  belongs to the PREMISE, not the question (cases 102/108, where the premise
  'Luke ... does not live with strangers' runs straight into the positive
  question 'Luke spends a lot of time ...?').  Anchor the question clause to
  the query subject -- the unit's leading content token -- and inspect from its
  LAST occurrence (the run-on repeats the subject, so the earliest occurrence
  is the premise's).  Returns False if the subject can't be located (can't
  align -> stay conservative and do not fire)."""
  anchors = _content_tokens(unit_text)
  if not anchors:
    return False
  subj = anchors[0]                 # the query subject's leading content word
  start = orig_q.lower().rfind(subj)
  if start < 0:
    return False
  return _has_negation_cue(orig_q[start:])


def _check_stage1_dropped_question_negation(s1_json, orig_text=None):
  """Flag a query unit that dropped a sentential negation present in the
  original question (prenorm-negation-fallback detector).  Gated on the
  `negretry_flag`.  No-op when orig_text is unavailable.  See cases
  80/127/189/200 (gpt)."""
  import globals as _g
  if not _g.options.get("negretry_flag"):
    return []
  if not isinstance(s1_json, list) or not orig_text:
    return []
  questions = _question_sentences(orig_text)
  if not questions:
    return []
  orig_q = questions[-1]                      # FOLIO: the conclusion question
  issues = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict) or unit.get("type") != "query":
        continue
      unit_text = unit.get("text", "")
      # If the unit kept ANY negation (in its own text), the LLM did not drop
      # it -- leave it alone (mis-scope is a separate, out-of-scope problem).
      if _has_negation_cue(unit_text):
        continue
      # Fire only if the QUESTION CLAUSE (anchored to the unit's content) is
      # negated -- not a run-on premise's negation swept in by the sentence
      # split (cases 102/108 false positives).
      if not _question_clause_negated(orig_q, unit_text):
        continue
      uid = unit.get("unit_id", "?")
      issues.append(Issue(
        kind="dropped_question_negation",
        location="@id:" + str(uid),
        description=("The question is NEGATED in the input: \"" + orig_q
                     + "\". But query unit " + str(uid) + " (\""
                     + str(unit_text) + "\") dropped the negation and asks the "
                     "POSITIVE question. Preserve the negation in the query "
                     "unit's text so the WHOLE predication is negated (e.g. "
                     "\"Is X NOT a Y?\" / \"Does X NOT play ...?\"), not the "
                     "affirmative form. The negation scopes over the entire "
                     "statement; do not move it onto a single inner word."),
        evidence=safe_json(unit),
      ))
  return issues




# ======== public API ========

def _check_stage1_dropped_question(s1_json, orig_text=None):
  """The input asks a question and Stage 1 kept no trace of it.

  FOLIO states its conclusion as a declarative that ends in "?"
  ("Djokovic lives in a tax haven?").  A model can read that as one more
  assertion and never emit it, and then no block's raw text carries the "?"
  and no unit is typed `query`.  Both Stage-2 defences key on exactly that
  evidence, so with the sentence gone neither can fire and the run ends at
  gk's `no question given` (19 of 203 deepseek FOLIO cases, 2026-08-19).

  Fires only when the question left NO trace at all.  A question Stage 1
  merely mistyped still shows up in a raw text, and
  `stage_sanity_s2._check_stage2_missing_question` handles that one.
  """
  if not isinstance(s1_json, list) or not orig_text:
    return []
  questions = _question_sentences(orig_text)
  if not questions:
    return []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    if "?" in (pkg.get("raw") if isinstance(pkg.get("raw"), str) else ""):
      return []
    for unit in pkg.get("units", []) or []:
      if isinstance(unit, dict) and unit.get("type") == "query":
        return []
  return [Issue(
      kind="dropped_question",
      location="",
      description=("The input asks: \"" + questions[-1] + "\"  Stage 1 has no "
                   "unit for it: no unit is typed `query` and no block's raw "
                   "text carries the question. A sentence that ends with '?' "
                   "is a question even when it is worded as a statement — it "
                   "asks whether what it says is so. Emit every sentence of "
                   "the input, and emit that one as a unit of type `query`."),
      evidence=questions[-1][:200])]


def check_stage1(s1_json, orig_text=None):
  """Run all registered Stage-1 sanity checks and return the combined
  issue list.

  Note: the dropped-question-negation check is NOT run here.  Under -prenorm
  (the -abstract-max default) the negation is stripped by prenorm BEFORE Stage
  1, so the Stage-1 input is already positive and there is nothing to detect at
  this point.  The recovery is driven at the parse_text level instead, by
  re-parsing from the original (pre-prenorm) text -- see llmparse.parse_text
  and check_dropped_question_negation()."""
  issues = []
  issues.extend(_check_stage1_missing_wh_placeholder(s1_json))
  issues.extend(_check_stage1_entity_used_as_location(s1_json))
  issues.extend(_check_stage1_pronoun_as_class(s1_json))
  issues.extend(_check_stage1_spurious_wh_placeholder(s1_json))
  issues.extend(_check_stage1_split_conditional(s1_json))
  issues.extend(_check_stage1_dropped_question(s1_json, orig_text))
  return issues


def check_dropped_question_negation(s1_json, orig_text):
  """Public entry for the prenorm-negation-fallback (llmparse.parse_text):
  return issues if a query unit dropped a sentential negation present in the
  ORIGINAL question text.  Gated on `negretry_flag` inside the checker."""
  return _check_stage1_dropped_question_negation(s1_json, orig_text)
