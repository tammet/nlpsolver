# Stage-2 logic-shape sanity checks + dispatch (see stage_sanity.py facade).
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

import re
from stage_sanity_core import Issue, safe_json



# ======== Stage-2 structural operators ========

# Quantifier-like binders whose second element is the bound variable name.
_BINDERS = frozenset({"forall", "exists", "ask"})



# Operators whose body/children are sub-formulas (walk structurally, no
# new binding).  The walker recurses into all list children; entries here
# are used for path labeling and keep the predicate-detection logic clean.
_STRUCTURAL_OPS = frozenset({
  "and", "or", "not", "implies", "iff", "xor",
  "holds", "question", "normally",
  "@id", "@time", "@p",
})




# ======== Stage-2 free-variable check ========

def _collect_binder_names(node, lexicon):
  """Walk the tree; add every string used as the binder of
  forall/exists/ask to the lexicon set.  First pass: defines which names
  are treated as variables in the free-variable scan."""
  if not isinstance(node, list) or not node:
    return
  if isinstance(node[0], str):
    op = node[0]
    if op in _BINDERS and len(node) >= 3 and isinstance(node[1], str):
      lexicon.add(node[1])
  for child in node[1:]:
    if isinstance(child, list):
      _collect_binder_names(child, lexicon)




def _scan_free_vars(node, lexicon, scope, issues, path):
  """Second pass: emit free-variable Issues for lexicon strings that
  appear as atom arguments outside their binding scope.

  scope: frozenset of currently-bound variable names (per enclosing
  forall/exists/ask).
  path: dotted path used as the Issue.location — helps the LLM locate
  the offending atom in its own output.
  """
  if not isinstance(node, list) or not node:
    return
  if not isinstance(node[0], str):
    return
  op = node[0]

  # Binder: extend scope and recurse into the body (node[2]).
  if op in _BINDERS and len(node) >= 3 and isinstance(node[1], str):
    new_scope = scope | {node[1]}
    body = node[2]
    new_path = path + "/" + op + ":" + node[1]
    if isinstance(body, list):
      _scan_free_vars(body, lexicon, new_scope, issues, new_path)
    return

  # Structural recursion: walk every list child; preserve current scope.
  if op in _STRUCTURAL_OPS:
    for i, child in enumerate(node[1:], start=1):
      if isinstance(child, list):
        _scan_free_vars(child, lexicon, scope, issues, path + "/" + op)
    return

  # Otherwise treat as an atom.  Predicate is at position 0 (skipped).
  # Each argument string in the lexicon but not in scope is a free reference.
  for i, arg in enumerate(node[1:], start=1):
    if isinstance(arg, str):
      if arg in lexicon and arg not in scope:
        try:
          ev = json.dumps(node)
        except Exception:
          ev = str(node)
        issues.append(Issue(
          kind="free_variable",
          location=path + "/" + op + "[arg" + str(i) + "]",
          description=("Variable '" + arg + "' is referenced here but is "
                       "not bound by any enclosing forall/exists/ask. "
                       "Stage-2 instructions forbid free variables — the "
                       "binder must enclose every use."),
          evidence=ev,
        ))
    elif isinstance(arg, list):
      _scan_free_vars(arg, lexicon, scope, issues, path + "/" + op)




def _check_stage2_free_variables(logic):
  """Detect variable references outside their binding scope.  A 'variable
  reference' is any string argument that also appears somewhere in the
  formula as a binder name — string constants that never serve as binders
  are treated as entity ids/labels and ignored."""
  if not isinstance(logic, list):
    return []
  lexicon = set()
  _collect_binder_names(logic, lexicon)
  if not lexicon:
    return []
  issues = []
  _scan_free_vars(logic, lexicon, frozenset(), issues, "")
  return issues




# ======== Stage-2 misplaced meta-predicate check ========

# Tense words that, when found as the value slot of state_time/has_time,
# signal the atom is carrying grammatical tense — which should live in
# $ctxt (added during clausification), not as a predicate argument.
_TENSE_WORDS = frozenset({"past", "present", "future", "timeless"})



# Operators whose argument is a formula body.  When the walker descends into
# these, meta-predicates with tense values should no longer be legal at
# that depth — they belong as siblings at the package level.
_BODY_OPS = frozenset({"holds", "question", "ask", "normally"})




def _walk_body_depth(node, inside_body, issues, path):
  """Recurse the tree.  `inside_body` becomes True once we enter the body
  argument of a holds/question/ask/normally wrapper; from that point on,
  any tense-valued state_time/has_time atom is flagged.  Also recurses
  through quantifiers and connectives while preserving inside_body state.
  """
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]

  if inside_body and op in ("state time", "-state time") and len(node) >= 3:
    tval = node[2]
    if isinstance(tval, str) and tval in _TENSE_WORDS:
      issues.append(Issue(
        kind="state_time_in_body",
        location=path + "/" + op,
        description=("Meta-predicate 'state time' with a grammatical tense "
                     "value ('" + tval + "') appears inside a formula body, "
                     "but tense metadata belongs at the package level "
                     "(sibling to 'holds'/'question'/'ask'), not inside "
                     "the quantified formula. Remove this atom from the "
                     "body and place the tense information at the package "
                     "sibling level if needed."),
        evidence=safe_json(node),
      ))
      return

  # NOTE: intentionally do NOT flag `has time E TENSE PREP` here. Per
  # Stage-2 §8.1, this is the canonical shape for grammatical tense on
  # Davidsonian event variables and must survive into clausification.
  # strip_tense_has_time keeps it on event vars and strips it elsewhere.

  # Body-introducing operators: recurse into the last child with inside_body=True.
  if op in _BODY_OPS:
    # holds has signature [holds, W, BODY]; question/ask/normally have a
    # body as their single argument after op.  Recurse structurally but
    # flag inside_body for the body argument(s).
    for i, child in enumerate(node[1:], start=1):
      if isinstance(child, list):
        # For "holds", only the second arg (index 2 in node, i==2) is the body.
        # For "ask", the first arg (i==1) is the var, second (i==2) is body.
        # For "question"/"normally", the first (i==1) is the body.
        if op == "holds" and i == 2:
          _walk_body_depth(child, True, issues, path + "/" + op)
        elif op in ("question", "normally") and i == 1:
          _walk_body_depth(child, True, issues, path + "/" + op)
        elif op == "ask" and i == 2:
          _walk_body_depth(child, True, issues, path + "/" + op)
        else:
          _walk_body_depth(child, inside_body, issues, path + "/" + op)
    return

  # Quantifiers and connectives: recurse preserving inside_body.
  for child in node[1:]:
    if isinstance(child, list):
      _walk_body_depth(child, inside_body, issues, path + "/" + op)




def _check_stage2_misplaced_meta_tense(logic):
  """Detect misplaced tense-valued state_time/has_time atoms inside formula
  bodies.  See cases 37 and 142 for examples."""
  if not isinstance(logic, list):
    return []
  issues = []
  _walk_body_depth(logic, False, issues, "")
  return issues




# ======== Stage-2 dropped-specific-noun check ========

_WH_PLACEHOLDERS = frozenset({
  "who", "what", "which", "whom", "whose",
  "where", "when", "why", "how",
})




def _build_s1_generic_cat_to_id(s1_json):
  """Build {category: unique_specific_id} from Stage-1 generic entities
  that pass the guards.  Only categories where a single qualifying generic
  entity exists are retained — mirrors _build_query_cat_to_id in
  lc_rewrites.py."""
  if not isinstance(s1_json, list):
    return {}
  cat_to_ids = {}
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for asu in pkg.get("units", []) or []:
      if not isinstance(asu, dict):
        continue
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
          continue
        if eid.lower() in _WH_PLACEHOLDERS:
          continue
        if " " in eid:
          continue
        if eid[:1].isupper():
          continue
        cat_to_ids.setdefault(cat, []).append(eid)
  return {cat: ids[0] for cat, ids in cat_to_ids.items() if len(ids) == 1}




def _scan_dropped_noun(node, cat_to_id, issues, path):
  """Walk the tree; for every 'exists VAR, BODY' where BODY is an 'and'
  with exactly one isa(CAT, VAR) literal and CAT has a known specific-id
  mapping distinct from CAT, emit an Issue (the Stage-2 query used the
  generic category where the Stage-1 specific noun should appear).
  """
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]

  if op == "exists" and len(node) == 3 and isinstance(node[1], str):
    var = node[1]
    body = node[2]
    _check_exists_body_for_dropped_noun(body, var, cat_to_id, issues,
                                        path + "/exists:" + var)
    if isinstance(body, list):
      _scan_dropped_noun(body, cat_to_id, issues, path + "/exists:" + var)
    return

  for child in node[1:]:
    if isinstance(child, list):
      _scan_dropped_noun(child, cat_to_id, issues, path + "/" + op)




def _check_exists_body_for_dropped_noun(body, var, cat_to_id, issues, path):
  if not isinstance(body, list) or len(body) < 2 or body[0] != "and":
    return
  args = body[1:]
  isa_cats_for_var = []
  for arg in args:
    if (isinstance(arg, list) and len(arg) >= 3 and arg[0] == "isa"
        and arg[2] == var and isinstance(arg[1], str)):
      isa_cats_for_var.append(arg[1])
  if len(isa_cats_for_var) != 1:
    return
  cat = isa_cats_for_var[0]
  if cat not in cat_to_id:
    return
  specific = cat_to_id[cat]
  if specific == cat or specific in isa_cats_for_var:
    return
  issues.append(Issue(
    kind="dropped_specific_noun",
    location=path,
    description=("Query existential '" + var + "' is constrained only by "
                 "isa('" + cat + "', " + var + "), but the Stage-1 ASU "
                 "declared this entity with id='" + specific + "' and "
                 "category='" + cat + "'. Queries must preserve the "
                 "user's specific noun — add isa('" + specific + "', " +
                 var + ") so the query asks about '" + specific + "', "
                 "not any entity of category '" + cat + "'."),
    evidence=safe_json(body),
  ))




def _check_stage2_dropped_specific_noun(logic, s1_json):
  """Detect query existentials constrained only by the category isa where
  Stage-1 unambiguously specified a different specific noun id.  See
  case 136."""
  if not isinstance(logic, list) or not isinstance(s1_json, list):
    return []
  cat_to_id = _build_s1_generic_cat_to_id(s1_json)
  if not cat_to_id:
    return []
  issues = []
  _scan_dropped_noun(logic, cat_to_id, issues, "")
  return issues




# ======== Stage-2 predicate-arity check ========

# Exact arities for Stage-2 predicates whose shape is unambiguously declared
# in stage2_instructions_full.txt §2.2, §2.3, §2.6.  We only enforce
# predicates where the arity is non-negotiable; skip any predicate whose
# correct arity depends on optional fields.
_ARITY_TABLE = {
  "isa": 2,
  "has property": 2,
  "have": 2,
  "has part": 2,
  "is rel2": 3,
  "can": 2,
  "has degree property": 4,
  "has degree rel2": 5,
  "has type": 2,
  "has actor": 2,
  "has target": 2,
  "has recipient": 2,
  "has source": 2,
  "has instrument": 2,
  "has manner": 2,
  "has direction": 2,
  "has beneficiary": 2,
  "has accompaniment": 2,
  "has path": 2,
  "has result": 2,
  "has topic": 2,
  "has cause": 2,
  "has destination": 3,
  "has location": 3,
  "has time": 3,
  "typical": 1,
  "typically": 2,
  "=": 2,
  "!=": 2,
}




def _scan_arities(node, issues, path):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]
  base = op[1:] if op.startswith("-") else op

  # Structural nodes we only recurse into (they're not atoms).
  _STRUCTURAL = _BINDERS | _STRUCTURAL_OPS | _BODY_OPS
  if base in _STRUCTURAL:
    for child in node[1:]:
      if isinstance(child, list):
        _scan_arities(child, issues, path + "/" + op)
    return

  # Atom: check arity against table if known.
  if base in _ARITY_TABLE:
    expected = _ARITY_TABLE[base]
    actual = len(node) - 1  # minus the predicate name
    if actual != expected:
      issues.append(Issue(
        kind="wrong_arity",
        location=path + "/" + op,
        description=("Predicate '" + base + "' expects arity " +
                     str(expected) + " (" + str(expected) + " arguments "
                     "after the predicate name) but was emitted with "
                     "arity " + str(actual) + ". Check the Stage-2 "
                     "predicate signatures in the instructions and adjust "
                     "the arguments."),
        evidence=safe_json(node),
      ))
      return  # don't also recurse into a malformed atom's children

  # Recurse into any list children (e.g., @time wrappers, nested subterms).
  for child in node[1:]:
    if isinstance(child, list):
      _scan_arities(child, issues, path + "/" + op)




def _check_stage2_arities(logic):
  """Detect atoms whose arity disagrees with the declared Stage-2 signature."""
  if not isinstance(logic, list):
    return []
  issues = []
  _scan_arities(logic, issues, "")
  return issues




# ======== Stage-2 missing-question check ========
#
# Detects the case where a Stage-1 unit was identified as a query (either
# its parent package's raw text contains a "?" or the unit's `type` field
# is "query"), but the corresponding Stage-2 @id package contains no
# `question` / `ask` wrapper.  This catches LLM truncations where the
# query unit was silently dropped, as well as cases where the LLM emitted
# a `holds` package for what should have been a question.

def _contains_question_or_ask(node):
  """Return True if any node in the tree has op `question` or `ask`."""
  if not isinstance(node, list) or not node:
    return False
  if isinstance(node[0], str) and node[0] in ("question", "ask"):
    return True
  for child in node[1:]:
    if isinstance(child, list) and _contains_question_or_ask(child):
      return True
  return False




def _collect_question_ids_from_logic(node, found):
  """Walk the Stage-2 tree.  For every `@id` encountered, record its s_id
  in `found` if the body sub-tree contains a `question` or `ask` wrapper.
  @ids are siblings under the top-level `and`, never nested, so we don't
  recurse past them once visited."""
  if not isinstance(node, list) or not node:
    return
  if isinstance(node[0], str):
    op = node[0]
    if op == "@id" and len(node) >= 3 and isinstance(node[1], str):
      sid = node[1]
      body = node[2]
      if isinstance(body, list) and _contains_question_or_ask(body):
        found.add(sid)
      return
  for child in node[1:]:
    if isinstance(child, list):
      _collect_question_ids_from_logic(child, found)




def _check_stage2_multiple_questions(logic):
  """Detect when Stage-2 emits more than one @id package whose body
  contains a `question` or `ask` wrapper.  The gk prover accepts only
  one @question per call; multiple questions cause "several questions
  given" errors and the pipeline cannot dispatch them.

  Triggered when a single conditional yes/no like "If A and B, does C?"
  is broken into separate sub-questions instead of a single conditional
  question with antecedent (A & B) and consequent C.
  """
  if not isinstance(logic, list):
    return []
  found = set()
  _collect_question_ids_from_logic(logic, found)
  if len(found) < 2:
    return []
  sids = sorted(found)
  return [Issue(
    kind="multiple_questions",
    location=", ".join("@id:" + s for s in sids),
    description=("Stage-2 emitted " + str(len(sids)) + " separate "
                 "question/ask packages (@ids " + ", ".join(sids) + "). "
                 "The downstream prover accepts at most ONE query per "
                 "input, so multiple question packages cannot be answered "
                 "together.  If the source sentence is a single "
                 "conditional yes/no (e.g. \"If A and B, does C?\") or a "
                 "single factive (e.g. \"Does X know that Y?\"), encode "
                 "the whole question as ONE package whose body wraps the "
                 "complete formula — e.g. [\"question\", [\"implies\", "
                 "[\"and\", A, B], C]] for the conditional, or "
                 "[\"question\", [\"and\", knows-A, fact-Y]] for the "
                 "factive embedding.  Assertions extracted from question "
                 "presuppositions belong in their own assertion packages "
                 "(no question/ask wrapper), not as separate queries."),
    evidence="question @ids: " + ", ".join(sids),
  )]




# ======== Stage-2 vacuous-tautology-assertion check ========
#
# Detects an ASSERTION (non-question) package whose formula is an
# ["implies", A, B] with A structurally identical to B -- a vacuous
# tautology "if P then P".  No declarative sentence asserts such a thing;
# it is the signature of a conditional QUESTION mis-segmented on its comma
# into an asserted tautology plus a separate question of only the
# consequent (gpt case 384: "If John has three cars, John has three
# cars?" -> holds(implies(P,P)) + question(P)).  The whole conditional is
# then never asked, so the answer is Unknown.
#
# Fires only when (a) a vacuous held implies(A,A) exists on the assertion
# side AND (b) the output also contains a question/ask package, so
# re-encoding "as a single conditional question" is the right advice.
# The CORRECT encoding question(implies(P,P)) (claude/deepseek) is never
# flagged: the scan does not descend into question/ask bodies.

def _scan_vacuous_implies(node, issues, path):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]
  # The correct home for a tautology question; never flag inside it.
  if op in ("question", "ask"):
    return
  if op == "implies" and len(node) >= 3 and node[1] == node[2]:
    issues.append(Issue(
      kind="vacuous_tautology_assertion",
      location=path + "/implies",
      description=("This package contains [\"implies\", A, B] whose "
                   "antecedent and consequent are IDENTICAL -- a vacuous "
                   "tautology \"if P then P\" that carries no information "
                   "and is never what a declarative sentence ASSERTS. This "
                   "is the signature of a conditional QUESTION (e.g. \"If "
                   "P, P?\") that was wrongly split, on its comma, into an "
                   "assertion plus a separate question of only the "
                   "consequent. The whole sentence is ONE yes/no question. "
                   "Your corrected output must contain EXACTLY ONE @id "
                   "package, and that package's body must be "
                   "[\"question\", [\"implies\", ANTECEDENT, CONSEQUENT]] "
                   "wrapping the complete \"if ... then ...\" formula. "
                   "DELETE every other package -- in particular delete any "
                   "[\"holds\", ...] assertion of the implication AND any "
                   "separate [\"question\", CONSEQUENT] that asks only part "
                   "of the conditional. Do NOT assert the implication, do "
                   "NOT emit a second question, and do NOT keep a "
                   "bare-consequent question alongside the conditional one."),
      evidence=safe_json(node),
    ))
    return
  for child in node[1:]:
    if isinstance(child, list):
      _scan_vacuous_implies(child, issues, path + "/" + op)




def _check_stage2_vacuous_tautology_assertion(logic):
  """Flag an assertion-side ["implies", A, B] with A structurally equal to
  B, when the output also contains a question/ask package.  See the
  section comment above (gpt case 384)."""
  if not isinstance(logic, list):
    return []
  if not _contains_question_or_ask(logic):
    return []
  issues = []
  _scan_vacuous_implies(logic, issues, "")
  return issues




# ======== Stage-2 measure-vs-degree_rel2 conflict check ========
#
# For a MEASURABLE property the consistent encoding is $measure_of(P, E, W)
# compared with = / > / <.  When Stage-2 uses BOTH $measure_of(P, ...) AND
# has_degree_rel2(P, ...) for the SAME property P, the equality and the
# comparison land in two disconnected representations that never reason
# together -- no axiom bridges has_degree_rel2 to $measure_of (claude case
# 555: premise =($measure_of(tall,John), $measure_of(tall,Bill)), question
# has_degree_rel2(tall, John, Bill, high, person) -> Unknown).
#
# Narrow: fires only when the SAME property string appears as arg1 of both a
# $measure_of term and a has_degree_rel2 atom.  The presence of $measure_of(P)
# is itself the "P is measurable" signal, so no separate measurability list is
# needed.  Spatial has_degree_rel2 (arg1 a preposition like "in") never
# overlaps a $measure_of property, so PROXIMITY etc. are untouched.

def _collect_measure_props(node, out):
  """Add arg1 of every ["$measure_of", P, ...] term to out."""
  if not isinstance(node, list) or not node:
    return
  if node[0] == "$measure_of" and len(node) >= 2 and isinstance(node[1], str):
    out.add(node[1])
  for c in node:
    if isinstance(c, list):
      _collect_measure_props(c, out)




def _collect_degree_rel2_props(node, out):
  """Add arg1 of every has_degree_rel2 atom (positive or negated) to out."""
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  head = node[0][1:] if node[0].startswith("-") else node[0]
  if head == "has degree rel2" and len(node) >= 2 and isinstance(node[1], str):
    out.add(node[1])
  for c in node[1:]:
    if isinstance(c, list):
      _collect_degree_rel2_props(c, out)




def _check_stage2_measure_vs_degree_rel2(logic):
  """Flag a property encoded BOTH as $measure_of(P,...) and as
  has_degree_rel2(P,...) in one Stage-2 output.  See case 555 (claude)."""
  if not isinstance(logic, list):
    return []
  mprops = set()
  rprops = set()
  _collect_measure_props(logic, mprops)
  _collect_degree_rel2_props(logic, rprops)
  overlap = sorted(mprops & rprops)
  issues = []
  for p in overlap:
    issues.append(Issue(
      kind="measure_degree_rel2_conflict",
      location="property:" + p,
      description=("Stage-2 encodes the property \"" + p + "\" BOTH as "
                   "[\"$measure_of\", \"" + p + "\", ...] (a measure value) "
                   "AND as [\"has degree rel2\", \"" + p + "\", ...] (a "
                   "gradable comparative). \"" + p + "\" is measurable -- you "
                   "already used $measure_of for it -- so ALL of its "
                   "comparisons must live on the SAME measure scale to reason "
                   "together; nothing connects has_degree_rel2 to "
                   "$measure_of. Replace the has_degree_rel2(\"" + p + "\", A, "
                   "B, INTENSITY, ...) atom with the matching $measure_of "
                   "comparison, reusing the SAME property name \"" + p + "\" "
                   "and world W: \"A is as " + p + " as B\" -> [\"=\", "
                   "[\"$measure_of\",\"" + p + "\",A,W], [\"$measure_of\",\""
                   + p + "\",B,W]]; \"A is more " + p + " / " + p + "-er than "
                   "B\" -> [\">\", [\"$measure_of\",\"" + p + "\",A,W], "
                   "[\"$measure_of\",\"" + p + "\",B,W]]; \"less " + p + "\" "
                   "-> [\"<\", ...]. Do NOT use has_degree_rel2 for \"" + p
                   + "\"."),
      evidence="$measure_of and has_degree_rel2 both use property: " + p,
    ))
  return issues




# ======== Stage-2 comparative-as-degree_property check ========
#
# A comparative construction ("as P as", "P-er than", "more/less P than")
# compares TWO entities on a measurable property P, so it is inherently
# binary.  has_degree_property(P, ENTITY, degree) is UNARY (one entity, an
# absolute degree) and cannot express the comparison -- the relation between
# the two entities is simply lost (gpt case 555: "John is as tall as Bill" ->
# has_degree_property(tall,John,none) + has_degree_property(tall,Bill,none),
# so the equality is gone and "taller?" is unprovable -> Unknown).
#
# Narrow: fires only when (a) the Stage-1 text contains a comparative cue for
# adjective P, (b) Stage-2 encodes P with has_degree_property, and (c) Stage-2
# has NO two-argument comparison for P ($measure_of or has_degree_rel2) -- i.e.
# the comparison was genuinely dropped, not merely encoded elsewhere.

_AS_AS_RE = re.compile(r"\bas\s+(\w+)\s+as\b", re.IGNORECASE)


_MORE_LESS_THAN_RE = re.compile(r"\b(?:more|less)\s+(\w+)\s+than\b", re.IGNORECASE)


_ER_THAN_RE = re.compile(r"\b(\w+?)(er|ier)\s+than\b", re.IGNORECASE)



# Adjectives denoting an OBJECTIVE measurable dimension -- a scale with a unit
# (length, weight, speed, age, price, temperature, ...).  ONLY these may be
# pushed onto the $measure_of scale by the comparative retry: a gradable but
# non-measurable adjective ("interesting", "beautiful", "important") has no
# unit and must NOT be measured (case 559 -- "more interesting than" is not
# measurable).  Base (positive) forms only; the comparative regexes reduce
# "-er than" to the base.  This gate applies to comparative_as_degree_property,
# where WE choose the $measure_of encoding; measure_vs_degree_rel2 is not gated
# because there the LLM already chose $measure_of (its own measurability call).
_MEASURABLE_ADJS = frozenset({
    # length / height / width / depth / size / distance
    "tall", "short", "long", "wide", "narrow", "deep", "shallow", "high",
    "low", "thick", "thin", "big", "large", "small", "huge", "tiny",
    "far", "near", "close", "broad", "fat", "slim",
    # weight
    "heavy", "light",
    # speed
    "fast", "slow", "quick", "rapid", "swift",
    # age / recency
    "old", "young", "new",
    # price / cost / value
    "expensive", "cheap", "costly", "pricey",
    # temperature
    "hot", "cold", "warm", "cool",
    # loudness / brightness (decibel / lumen scales)
    "loud", "quiet", "bright", "dim",
    # strength
    "strong", "weak",
})




def _comparative_adjs_from_text(text):
  """Return candidate comparative adjectives (lowercased base forms) found in
  text.  Best-effort de-suffixing for the '-er than' form adds a few harmless
  noise candidates that simply fail to intersect the parse's properties."""
  out = set()
  if not isinstance(text, str):
    return out
  for m in _AS_AS_RE.finditer(text):
    out.add(m.group(1).lower())
  for m in _MORE_LESS_THAN_RE.finditer(text):
    out.add(m.group(1).lower())
  for m in _ER_THAN_RE.finditer(text):
    stem, suf = m.group(1).lower(), m.group(2).lower()
    out.add(stem)
    if suf == "ier":
      out.add(stem + "y")           # heav(ier) -> heavy
    if len(stem) >= 2 and stem[-1] == stem[-2]:
      out.add(stem[:-1])            # bigg(er) -> big
  return out




def _collect_degree_property_props(node, out):
  """Add arg1 of every has_degree_property atom (positive or negated)."""
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  head = node[0][1:] if node[0].startswith("-") else node[0]
  if head == "has degree property" and len(node) >= 2 and isinstance(node[1], str):
    out.add(node[1])
  for c in node[1:]:
    if isinstance(c, list):
      _collect_degree_property_props(c, out)




def _check_stage2_comparative_as_degree_property(logic, s1_json):
  """Flag a comparative property (cue in Stage-1 text) encoded as the unary
  has_degree_property with no two-argument comparison.  See case 555 (gpt)."""
  if not isinstance(logic, list):
    return []
  comp_adjs = set()
  if isinstance(s1_json, list):
    for pkg in s1_json:
      if not isinstance(pkg, dict):
        continue
      comp_adjs |= _comparative_adjs_from_text(pkg.get("raw", ""))
      for u in pkg.get("units", []) or []:
        if isinstance(u, dict):
          comp_adjs |= _comparative_adjs_from_text(u.get("text", ""))
  if not comp_adjs:
    return []
  dp_props = set()
  _collect_degree_property_props(logic, dp_props)
  twoarg = set()
  _collect_measure_props(logic, twoarg)
  _collect_degree_rel2_props(logic, twoarg)
  issues = []
  for p in sorted(comp_adjs & dp_props):
    if p in twoarg:
      continue                      # comparison already encoded for P
    if p in _MEASURABLE_ADJS:
      # Measurable dimension -> route the comparison onto the $measure_of scale.
      issues.append(Issue(
        kind="comparative_as_degree_property",
        location="property:" + p,
        description=("The source text compares TWO entities on the measurable "
                     "property \"" + p + "\" (\"as " + p + " as\" / \"" + p
                     + "-er than\" / \"more|less " + p + " than\"). A "
                     "comparison is binary, but Stage-2 encoded \"" + p + "\" "
                     "with has_degree_property(\"" + p + "\", ENTITY, ...), "
                     "which is UNARY (one entity, an absolute degree) and "
                     "cannot relate the two entities -- the comparison is "
                     "lost. Encode it on a measure scale with $measure_of, "
                     "using the SAME measure property name and world W for "
                     "BOTH entities AND for every other clause comparing the "
                     "same dimension (so a premise and its question share one "
                     "scale): \"A is as " + p + " as B\" -> [\"=\", "
                     "[\"$measure_of\",\"" + p + "\",A,W], [\"$measure_of\",\""
                     + p + "\",B,W]]; \"A is more " + p + " / " + p + "-er "
                     "than B\" -> [\">\", ...]; \"A is less " + p + " than "
                     "B\" -> [\"<\", ...]. Do NOT use has_degree_property for "
                     "a comparative."),
        evidence="measurable comparative cue for '" + p + "' encoded as has_degree_property",
      ))
    else:
      # Gradable but NON-measurable (no objective unit) -> route the comparison
      # onto the binary gradable-comparative has_degree_rel2 (case 559).
      issues.append(Issue(
        kind="comparative_as_degree_property_nonmeasurable",
        location="property:" + p,
        description=("The source text compares TWO entities on the gradable "
                     "property \"" + p + "\" (\"more " + p + " than\" / \"" + p
                     + "-er than\" / \"less " + p + " than\" / \"as " + p
                     + " as\"). A comparison is binary, but Stage-2 encoded \""
                     + p + "\" with the UNARY has_degree_property(\"" + p
                     + "\", ENTITY, ...), losing the relation between the two "
                     "entities. \"" + p + "\" has no objective unit (it is NOT "
                     "measurable), so encode the comparison with the binary "
                     "gradable-comparative predicate has_degree_rel2(R, X, Y, "
                     "INTENSITY, RELCLASS): \"X is more " + p + " / " + p
                     + "-er than Y\" -> [\"has degree rel2\", \"" + p + "\", "
                     "X, Y, \"high\", RELCLASS]; \"X is less " + p + " than "
                     "Y\" -> [\"has degree rel2\", \"" + p + "\", Y, X, "
                     "\"high\", RELCLASS] (Y is more " + p + " than X). "
                     "RELCLASS is the comparison class (the noun, e.g. the "
                     "entity's category, or \"entity\"). If the question omits "
                     "the entity being compared against (e.g. \"Is that one "
                     "more " + p + "?\"), supply the implicit referent from "
                     "the preceding sentence as Y. Do NOT use "
                     "has_degree_property for a comparative."),
        evidence="non-measurable comparative cue for '" + p + "' encoded as has_degree_property",
      ))
  return issues




# ======== Stage-2 multi-word property check ========
#
# The property name (first argument) of has_property / has_degree_property is
# meant to be a single adjective. When it is a phrase of MORE THAN TWO words it
# usually collapses several meaning components into one opaque adjective -- a
# relation plus its argument(s) packed into a string. gpt case 673:
# has_degree_property("filled with water", cup) -- the containment relation and
# its content "water" are baked into the property name, so nothing connects to
# the question's is_rel2("in", water, cup) -> Unknown. The relatum cannot be
# recovered downstream because it was never a real argument. The retry asks the
# LLM to split the phrase into its meaning components and represent the input
# with more detail (the embedded noun as a separate entity, the relation as the
# appropriate predicate). A two-word compound ("dark blue", "light green") is
# left alone -- only > 2 words are flagged.

_MULTIWORD_PROP_PREDS = frozenset({"has property", "has degree property"})




def _check_stage2_multiword_property(logic):
  """Flag has_property / has_degree_property atoms whose property name (first
  argument) is a phrase of more than two words. See gpt case 673."""
  if not isinstance(logic, list):
    return []
  found = []

  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      base = n[0][1:] if n[0].startswith("-") else n[0]
      if (base in _MULTIWORD_PROP_PREDS and len(n) >= 2
          and isinstance(n[1], str) and len(n[1].split()) > 2):
        found.append((base, n[1], n))
      for c in n[1:]:
        walk(c)
    elif isinstance(n, list):
      for c in n:
        walk(c)

  walk(logic)
  issues = []
  seen = set()
  for base, prop, atom in found:
    if prop in seen:
      continue
    seen.add(prop)
    issues.append(Issue(
      kind="multiword_property",
      location="property:" + prop,
      description=("The property name \"" + prop + "\" in this " + base
                   + " atom is a phrase of more than two words. A multi-word "
                   "property like this usually packs SEVERAL meaning "
                   "components into one opaque adjective -- typically a "
                   "relation together with its argument(s) (e.g. \"filled with "
                   "water\" = a containment relation between the entity and "
                   "\"water\"). It should probably be CONCEPTUALLY SPLIT into "
                   "its meaning components, and the input represented with more "
                   "detail: introduce the embedded noun(s) as their own "
                   "entities and encode the relation with the appropriate "
                   "predicate (is_rel2 / has_part / a Davidsonian event / a "
                   "single adjective in the degree slot / etc.), rather than "
                   "collapsing the whole phrase into one property name. "
                   "Re-represent \"" + prop + "\" compositionally."),
      evidence=safe_json(atom),
    ))
  return issues




# ======== Stage-2 "either ... or ..." exclusivity check ========
#
# The "either A or B" construction is an EXCLUSIVE disjunction: exactly one of
# the two alternatives holds, not both. The exclusivity is what licenses the
# downstream inference (case 571: "Elephants and sparrows are either animals or
# birds. ... Sparrows are birds. John is not an animal?" -> True, because bird
# excludes animal). Two Stage-2 mis-encodings lose it:
#   * inclusive ["or", A, B]            (gemini 571) -> bird does not exclude
#     animal -> Unknown.
#   * ["normally", [... xor/or ...]]    (deepseek 571) -> the defeasible xor's
#     "not both" clause carries a $block gated on one disjunct, so the
#     exclusivity self-defeats exactly when it is needed -> Unknown.
# The correct encoding is a bare strict ["xor", A, B] (claude/gpt 571 -> True).
# This check fires only when the source text uses "either" AND the Stage-2
# disjunction is NOT already a bare strict xor.

_EITHER_RE = re.compile(r"\beither\b", re.IGNORECASE)




def _text_has_either(s1_json):
  """True if any Stage-1 package raw text (or unit text) uses 'either'."""
  if not isinstance(s1_json, list):
    return False
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    if _EITHER_RE.search(pkg.get("raw", "") or ""):
      return True
    for u in pkg.get("units", []) or []:
      if isinstance(u, dict) and _EITHER_RE.search(u.get("text", "") or ""):
        return True
  return False




def _check_stage2_either_or_not_xor(logic, s1_json):
  """Flag an 'either ... or ...' source disjunction encoded as inclusive `or`
  or wrapped in `normally`, instead of a bare strict `xor`.  See case 571."""
  if not isinstance(logic, list) or not _text_has_either(s1_json):
    return []
  bad = {"inclusive_or": False, "defeasible_disj": False}

  def walk(n, under_normally):
    if not isinstance(n, list):
      return
    head = n[0] if (n and isinstance(n[0], str)) else None
    if head == "or":
      bad["inclusive_or"] = True
    if head in ("or", "xor") and under_normally:
      bad["defeasible_disj"] = True
    child_under = under_normally or (head == "normally")
    for c in (n[1:] if head else n):
      walk(c, child_under)

  walk(logic, False)
  if not (bad["inclusive_or"] or bad["defeasible_disj"]):
    return []   # already a bare strict xor (claude/gpt) -> nothing to fix
  return [Issue(
    kind="either_or_not_xor",
    location="connective:either-or",
    description=("The source text uses the \"either ... or ...\" construction, "
                 "which is an EXCLUSIVE disjunction: exactly ONE of the two "
                 "alternatives holds, never both. Encode \"X is either A or B\" "
                 "as a STRICT exclusive-or [\"xor\", A, B]. Do NOT use "
                 "[\"or\", A, B] -- inclusive or admits both alternatives at "
                 "once, so it cannot exclude one when the other is known. Do "
                 "NOT wrap the disjunction in [\"normally\", ...] -- a "
                 "definitional \"either ... or ...\" is strict, not defeasible. "
                 "For a generic rule \"Ns are either A or B\", encode it as "
                 "forall X ([\"implies\", [\"isa\", N, X], [\"xor\", A_of_X, "
                 "B_of_X]]) with the xor NOT inside a \"normally\"."),
    evidence="'either' in source text with non-xor disjunction encoding",
  )]




def _check_stage2_missing_question(logic, s1_json):
  """Detect Stage-1 query units that have no corresponding question/ask
  package in Stage-2.  Triggered when either unit.type == "query" or the
  parent package's raw text contains "?"."""
  if not isinstance(logic, list) or not isinstance(s1_json, list):
    return []
  expected = []      # list of (unit_id, raw)
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw", "") if isinstance(pkg.get("raw", ""), str) else ""
    raw_has_q = "?" in raw
    units = pkg.get("units", []) or []
    # If any unit in the package is already query-typed, trust Stage-1's
    # split: only flag query-typed units.  Otherwise (no explicit query
    # type) fall back to the raw-has-"?" hail-mary so a totally missing
    # query type doesn't go unnoticed.
    has_query_unit = any(
      isinstance(u, dict) and u.get("type") == "query" for u in units)
    for unit in units:
      if not isinstance(unit, dict):
        continue
      uid = unit.get("unit_id")
      if not isinstance(uid, str):
        continue
      utype = unit.get("type")
      if utype == "query":
        expected.append((uid, raw))
      elif raw_has_q and not has_query_unit:
        expected.append((uid, raw))
  if not expected:
    return []

  found = set()
  _collect_question_ids_from_logic(logic, found)

  issues = []
  for uid, raw in expected:
    if uid in found:
      continue
    issues.append(Issue(
      kind="missing_question",
      location="@id:" + uid,
      description=("Source sentence \"" + raw + "\" is a question (Stage-1 "
                   "marked unit " + uid + " as a query and/or the raw text "
                   "contains '?'), but the Stage-2 output has no "
                   "['question', FORMULA] or ['ask', VAR, FORMULA] wrapper "
                   "for unit " + uid + ".  Every query unit must be wrapped "
                   "as a 'question' (yes/no questions) or 'ask' (WH "
                   "questions) package — the @id for unit " + uid + " is "
                   "missing or wraps the wrong package shape.  Please add "
                   "the appropriate query package."),
      evidence=raw,
    ))
  return issues




# ======== Stage-2 event-shape check ========

# Event-role predicates (other than has_type).  If any of these mentions
# event variable E, the event is considered to have at least one role.
_EVENT_ROLE_PREDS = frozenset({
  "has actor", "has target", "has recipient", "has source",
  "has destination", "has location", "has instrument",
  "has manner", "has direction", "has time", "has beneficiary",
  "has accompaniment", "has path", "has result", "has topic",
  "has cause", "typical",
})




def _collect_atoms_for_var_in_and(body, var):
  """Return all atoms within an 'and' conjunction body that mention var
  (as any argument).  If body isn't an 'and', treat it as a single atom."""
  if not isinstance(body, list) or not body:
    return []
  atoms = []
  if body[0] == "and":
    candidates = body[1:]
  else:
    candidates = [body]
  for c in candidates:
    if isinstance(c, list) and var in c:
      atoms.append(c)
  return atoms




def _scan_event_shapes(node, issues, path):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]

  if op == "exists" and len(node) == 3 and isinstance(node[1], str):
    var = node[1]
    body = node[2]
    atoms = _collect_atoms_for_var_in_and(body, var)
    # Does the event carry a `has type` for this var?
    has_type_seen = any(
      isinstance(a, list) and len(a) >= 3 and a[0] == "has type" and a[1] == var
      for a in atoms)
    if has_type_seen:
      has_activity_isa = any(
        isinstance(a, list) and len(a) >= 3 and a[0] == "isa"
        and a[1] == "activity" and a[2] == var
        for a in atoms)
      has_some_role = any(
        isinstance(a, list) and len(a) >= 2 and a[0] in _EVENT_ROLE_PREDS
        and a[1] == var
        for a in atoms)
      if not has_activity_isa:
        issues.append(Issue(
          kind="event_missing_activity_isa",
          location=path + "/exists:" + var,
          description=("Event variable '" + var + "' has a 'has type' "
                       "atom but no 'isa(activity, " + var + ")' "
                       "conjunct. Stage-2 events must be typed with "
                       "isa(activity, E) in the same 'and' conjunction."),
          evidence=safe_json(body),
        ))
      if not has_some_role:
        issues.append(Issue(
          kind="event_missing_role",
          location=path + "/exists:" + var,
          description=("Event variable '" + var + "' has 'has type' and "
                       "(possibly) isa(activity,…) but no thematic-role "
                       "atom (has_actor / has_target / has_recipient / "
                       "has_location / has_time / typical / etc.). Every "
                       "event needs at least one role linking it to an "
                       "entity or property."),
          evidence=safe_json(body),
        ))
    # Recurse into body in case there are nested existentials.
    if isinstance(body, list):
      _scan_event_shapes(body, issues, path + "/exists:" + var)
    return

  for child in node[1:]:
    if isinstance(child, list):
      _scan_event_shapes(child, issues, path + "/" + op)




def _check_stage2_event_shapes(logic):
  """Detect events (existentials with has_type) missing isa(activity,E) or
  any thematic-role atom."""
  if not isinstance(logic, list):
    return []
  issues = []
  _scan_event_shapes(logic, issues, "")
  return issues




# ======== Stage-2 inner-content-event missing has_time check ========
#
# In a two-event reification (speech_act / volition / intention /
# expectation), the OUTER event E1 carries the modal classifier and a
# has_time atom, while the INNER content event E2 (linked via
# ["has content", E1, E2]) carries its own Davidsonian roles -- including
# its own has_time, since the embedded clause has independent tense.
#
# Gemini intermittently omits has_time on the inner content event of
# speech_act reifications (e.g., "John said that Mary left." -> the inner
# leave-event lacks has_time(E2, "past", "in")).  The axioms_std.js §5.2
# factive bridge then derives actuality(E2) but the question's tensed
# event ["has time", E_q, "past", "in"] fails to unify with E2.
#
# The check fires only when ALL of the following hold (5-gate criterion):
#   1. V appears as the 2nd argument of ["has content", E1, V] (V is an
#      inner content event).
#   2. V has a ["has type", V, ...] atom in its exists-scope (V is a
#      Davidsonian event, not a stative or propositional content).
#   3. V has NO ["has time", V, ...] atom in its exists-scope.
#   4. V has NO modal classifier in its exists-scope -- capability,
#      typical, necessity, obligation, volition, intention, expectation,
#      or speech_act (events that carry a classifier are intentionally
#      tenseless and shouldn't require has_time).
#   5. The Stage-1 unit containing this @id has its "time" field set
#      (past / present / future) -- evidence that the input is
#      tense-anchored at the matrix level.  Skips generic / tenseless
#      inputs where missing has_time on the inner event is fine.

_INNER_EVENT_MODAL_CLASSIFIERS = frozenset({
  "capability", "typical", "necessity", "obligation",
  "volition", "intention", "expectation", "speech_act",
})




def _collect_inner_content_vars(node, found):
  """Collect every string V that appears as the 2nd argument of an atom
  whose head is 'has content' anywhere in the tree."""
  if not isinstance(node, list) or not node:
    return
  head = node[0] if isinstance(node[0], str) else None
  if head == "has content" and len(node) >= 3 and isinstance(node[2], str):
    found.add(node[2])
  for c in node:
    if isinstance(c, list):
      _collect_inner_content_vars(c, found)




def _has_modal_classifier_for_var(body, var):
  """True if `body` (typically an `and` block) contains any classifier
  atom of arity 1 referencing var, e.g. ["capability", var]."""
  if not isinstance(body, list) or not body:
    return False
  if body[0] == "and":
    children = body[1:]
  else:
    children = [body]
  for c in children:
    if (isinstance(c, list) and len(c) == 2
        and isinstance(c[0], str)
        and c[0] in _INNER_EVENT_MODAL_CLASSIFIERS
        and c[1] == var):
      return True
  return False




def _unit_id_has_tense(s1_json, unit_id):
  """True if Stage-1 contains a unit with the given unit_id whose `time`
  field is set to past/present/future."""
  if not isinstance(s1_json, list):
    return False
  for item in s1_json:
    if not isinstance(item, dict):
      continue
    for u in item.get("units", []) or []:
      if not isinstance(u, dict):
        continue
      if u.get("unit_id") != unit_id:
        continue
      t = u.get("time")
      if isinstance(t, str) and t.lower() in ("past", "present", "future"):
        return True
      return False
  return False




def _scan_inner_event_time(node, inner_vars, s1_json, current_id,
                           issues, path):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  op = node[0]

  # Track which @id we're inside (gate 5 needs this for Stage-1 lookup).
  if op == "@id" and len(node) >= 3 and isinstance(node[1], str):
    new_id = node[1]
    for child in node[2:]:
      if isinstance(child, list):
        _scan_inner_event_time(child, inner_vars, s1_json, new_id,
                               issues, path + "/@id:" + new_id)
    return

  if op == "exists" and len(node) == 3 and isinstance(node[1], str):
    var = node[1]
    body = node[2]
    if var in inner_vars:
      atoms = _collect_atoms_for_var_in_and(body, var)
      has_type_seen = any(
        isinstance(a, list) and len(a) >= 3
        and a[0] == "has type" and a[1] == var
        for a in atoms)
      has_time_seen = any(
        isinstance(a, list) and len(a) >= 3
        and a[0] == "has time" and a[1] == var
        for a in atoms)
      has_classifier = _has_modal_classifier_for_var(body, var)
      unit_is_tensed = (current_id is not None
                       and _unit_id_has_tense(s1_json, current_id))
      if (has_type_seen and not has_time_seen and not has_classifier
          and unit_is_tensed):
        issues.append(Issue(
          kind="inner_content_event_missing_time",
          location=path + "/exists:" + var,
          description=(
            "Inner content event '" + var + "' (linked by has_content) "
            "has a 'has type' atom and no modal classifier, but no "
            "'has time' atom -- yet the Stage-1 unit '"
            + str(current_id) + "' is tense-anchored. Embedded clauses "
            "carry their own tense, so the inner event needs a "
            "has_time atom (e.g., "
            "[\"has time\", \"" + var + "\", \"past\", \"in\"]) matching "
            "the embedded clause's tense, so modal-bridge axioms can "
            "unify it with a tensed query event."),
          evidence=safe_json(body),
        ))
    if isinstance(body, list):
      _scan_inner_event_time(body, inner_vars, s1_json, current_id,
                             issues, path + "/exists:" + var)
    return

  for child in node[1:]:
    if isinstance(child, list):
      _scan_inner_event_time(child, inner_vars, s1_json, current_id,
                             issues, path + "/" + op)




def _check_stage2_inner_content_event_time(logic, s1_json=None):
  """Flag inner content events (referenced by has_content) that have a
  has_type atom but no has_time atom in their exists-scope, AND no modal
  classifier, AND the surrounding Stage-1 unit is tense-anchored.
  See the section comment above for the 5-gate criterion."""
  if not isinstance(logic, list):
    return []
  inner_vars = set()
  _collect_inner_content_vars(logic, inner_vars)
  if not inner_vars:
    return []
  issues = []
  _scan_inner_event_time(logic, inner_vars, s1_json, None, issues, "")
  return issues




# ======== Stage-2 entity-ID prefix-typo check ========
#
# Detects entity IDs like "fr fridge 3" that are an existing entity ID
# ("fridge 3") prefixed by a stray initial fragment of the same noun. Seen
# on case 152 with gemini, where the question's isa guard contained
# "fr fridge 3" while the assertion (and the question's is_rel2 atom)
# used "fridge 3" — the mismatch made the goal unreachable. The check
# triggers a corrective Stage-2 retry via the standard sanity-retry loop.

# Entity IDs follow the convention "<lowercase-noun-or-phrase> <integer>"
# or "<Capitalized-name> <integer>". Match anything that ends with a single
# space + digits.
_ENTITY_ID_RE = re.compile(r'^(\S.*?) (\d+)$')



# Stop the prefix check from flagging legitimate adjective-modified IDs.
_MAX_TYPO_PREFIX_LEN = 4




def _collect_entity_ids_with_paths(node, found, path):
  """Walk node (dicts, lists, strings), recording the first path at which
  each id-shaped string is seen. id-shape := "<text> <integer>".

  found: dict id -> path (first occurrence wins).
  """
  if isinstance(node, str):
    if _ENTITY_ID_RE.match(node) and node not in found:
      found[node] = path
    return
  if isinstance(node, dict):
    # Walk dict values; key into path so we can locate by key when useful.
    for key, val in node.items():
      _collect_entity_ids_with_paths(val, found, path + "/" + str(key))
    return
  if not isinstance(node, list) or not node:
    return
  head = node[0] if isinstance(node[0], str) else None
  for i, child in enumerate(node):
    child_path = (path + "/" + head) if head and i == 0 else (path + "[" + str(i) + "]")
    _collect_entity_ids_with_paths(child, found, child_path)




def _is_prefix_typo(candidate_base, target_base):
  """Return the stray prefix `extra` if candidate_base = extra + ' ' + target_base
  AND extra is a prefix of target_base's first word (case-insensitive),
  with len(extra) <= _MAX_TYPO_PREFIX_LEN. Otherwise None.
  """
  needle = " " + target_base
  if not candidate_base.endswith(needle):
    return None
  extra = candidate_base[: -len(needle)]
  if not extra or " " in extra:
    return None
  if len(extra) > _MAX_TYPO_PREFIX_LEN:
    return None
  first_word = target_base.split(" ", 1)[0]
  if not first_word:
    return None
  if first_word.lower().startswith(extra.lower()):
    return extra
  return None




def _check_stage2_entity_id_typos(logic):
  """Flag entity IDs that look like prefix-typos of another entity in the
  same Stage-2 output. See module docstring for case 152 (gemini) example.
  """
  if not isinstance(logic, list):
    return []
  found = {}
  _collect_entity_ids_with_paths(logic, found, "")
  if len(found) < 2:
    return []

  # Bucket by numeric suffix to limit the pairwise scan.
  by_suffix = {}
  for ident, path in found.items():
    m = _ENTITY_ID_RE.match(ident)
    if not m:
      continue
    by_suffix.setdefault(m.group(2), []).append((ident, m.group(1), path))

  issues = []
  reported = set()
  for suffix, items in by_suffix.items():
    if len(items) < 2:
      continue
    # Compare every distinct pair; flag the longer one if the shorter
    # is a typo-target of it.
    for i in range(len(items)):
      for j in range(len(items)):
        if i == j:
          continue
        cand_id, cand_base, cand_path = items[i]
        tgt_id,  tgt_base,  _         = items[j]
        if cand_id in reported:
          continue
        if len(cand_base) <= len(tgt_base):
          continue
        extra = _is_prefix_typo(cand_base, tgt_base)
        if extra is None:
          continue
        reported.add(cand_id)
        issues.append(Issue(
          kind="entity_id_typo",
          location=cand_path,
          description=('Entity id ' + json.dumps(cand_id)
                       + ' looks like a typo of '
                       + json.dumps(tgt_id)
                       + ' (stray prefix ' + json.dumps(extra) + ').'
                       + ' Replace ' + json.dumps(cand_id)
                       + ' with ' + json.dumps(tgt_id)
                       + ' wherever it appears.'),
          evidence=safe_json([cand_id, "->", tgt_id]),
        ))
        break
  return issues




# ======== Stage-2 possessive-without-ownership check ========
#
# A possessive in the source ("the students brought THEIR books", "his car")
# asserts ownership and must surface as a `have` (or `has part` for a
# part-whole / body-part relation) predicate.  Some LLMs drop the possessive
# determiner entirely — e.g. gpt on case 154 encodes "brought their books"
# as only the bring event (has_actor / has_target), with no ownership atom —
# so a later "Whose books?" / "who owns X?" query (which DOES become a have
# goal) matches nothing and the answer is Unknown.
#
# The cue is read from the Stage-1 unit `text` (what Stage-2 consumes), so an
# LLM that already resolved the possessive into a separate ownership unit
# (gemini rewrites S1 to "brought the books" + a distinct "students own
# books" unit) still shows the cue but supplies the ownership elsewhere.  So
# the "is it handled?" test is GLOBAL over the assertion side (all packages
# outside the question), and accepts relational genitives too: `is rel2 "X
# of"` ("sister of", "head of") plus `have` / `has part` / ownership verbs.
# The check fires only when (a) a "Whose X?" wh-question solves for an owner,
# (b) a possessive cue is present, and (c) the assertion side carries NO
# ownership-bearing atom at all — i.e. the possessive was genuinely dropped.

# Possessive determiners, matched only when followed by a noun (a word that is
# not an article/determiner) so the dative object pronoun "her" in "gave her
# the book" / "Mary saw her." does not trigger, while "her books" does.
_POSSESSIVE_RE = re.compile(
  r"\b(their|his|her|its|our|your|my)\s+"
  r"(?!(?:the|a|an|this|that|these|those|some|any|no)\b)\w",
  re.IGNORECASE)



# Genitive "'s" possessive ("the students' books", "John's car", "students 1's
# books") followed by a noun.  Stage-1 text expands "is"/"has" contractions
# ("the car's red" → "the car is red"), so a genitive here is reliably
# possessive; the contraction-stem blocklist below is belt-and-suspenders.
_GENITIVE_RE = re.compile(r"(\w+)'s\s+\w", re.IGNORECASE)


_CONTRACTION_STEMS = frozenset({
  "it", "that", "what", "who", "there", "here", "he", "she", "let", "this",
})



# is_rel2 relatums that already denote ownership (canonicalised to `have`
# later in lc_rewrites); counting them as ownership-present avoids retrying a
# parse that encoded the possessive as a relation rather than bare `have`.
_OWNERSHIP_REL2 = frozenset({
  "belonged to", "belongs to", "belong to", "owned by", "possessed by",
  "owns", "own", "owned", "possesses", "possess", "possessed",
})




def _text_has_possessive(text):
  """Return the matched possessive cue (lowercased) in `text`, or None.

  Matches a possessive determiner (their/his/...) or a genitive "'s"
  followed by a noun, skipping genitives whose stem is a contraction word
  (it's / that's / he's ...)."""
  if not isinstance(text, str):
    return None
  m = _POSSESSIVE_RE.search(text)
  if m:
    return m.group(1).lower()
  for g in _GENITIVE_RE.finditer(text):
    if g.group(1).lower() not in _CONTRACTION_STEMS:
      return g.group(0).strip().lower()
  return None




def _assertion_has_ownership(node):
  """True if the assertion side of `node` carries any ownership-bearing atom:
  `have` / `has part`, an `is rel2` with an ownership relatum (belonged to /
  owns / ...), or a relational genitive `is rel2 "X of"` ("sister of", "head
  of").  Subtrees under `ask` / `question` are skipped — the question's own
  ownership goal must not count as the assertion supplying it."""
  if not isinstance(node, list) or not node:
    return False
  head = node[0]
  if isinstance(head, str):
    if head in ("ask", "question"):
      return False  # do not look inside the question
    base = head[1:] if head.startswith("-") else head
    if base in ("have", "has part"):
      return True
    if base == "is rel2" and len(node) >= 2 and isinstance(node[1], str):
      rel = node[1]
      if rel in _OWNERSHIP_REL2 or rel.endswith(" of"):
        return True
  return any(_assertion_has_ownership(c) for c in node if isinstance(c, list))




def _ownership_atom_with_var(node, var):
  """True if some ownership atom (have / has part / ownership-is_rel2) under
  node has `var` as one of its arguments."""
  if not isinstance(node, list) or not node:
    return False
  head = node[0]
  if isinstance(head, str):
    base = head[1:] if head.startswith("-") else head
    if base in ("have", "has part") and var in node[1:]:
      return True
    if (base == "is rel2" and len(node) >= 2 and node[1] in _OWNERSHIP_REL2
        and var in node[2:]):
      return True
  return any(_ownership_atom_with_var(c, var) for c in node if isinstance(c, list))




def _logic_has_ownership_wh_question(logic):
  """True if logic has an `["ask", VAR, BODY]` whose answer variable VAR sits
  in an ownership atom in BODY — i.e. a "Whose X?" / "Who owns X?" question
  that is solving FOR the owner.

  This is the only shape where a dropped assertion-side possessive yields a
  wrong answer.  Incidental possessives in yes/no questions ("Did John see
  Mary's head?", "John's brother has a car?") and non-ownership wh-questions
  are deliberately excluded — they parse correctly without a retry."""
  found = []

  def walk(node):
    if found or not isinstance(node, list) or not node:
      return
    if (isinstance(node[0], str) and node[0] == "ask" and len(node) >= 3
        and _ownership_atom_with_var(node[2], node[1])):
      found.append(True)
      return
    for child in node:
      walk(child)

  walk(logic)
  return bool(found)




def _first_possessive_unit(s1_json):
  """Return (unit_id, text, cue) for the first Stage-1 unit whose text carries
  a possessive cue, or None."""
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []) or []:
      if not isinstance(unit, dict):
        continue
      text = unit.get("text", "")
      cue = _text_has_possessive(text)
      if cue:
        return (unit.get("unit_id", "?"), text, cue)
  return None




def _check_stage2_possessive_without_ownership(logic, s1_json):
  """Flag a parse with a "Whose X?" wh-question and a possessive cue whose
  assertion side carries no ownership-bearing atom at all (the possessive was
  dropped — see case 154).  Triggers a corrective Stage-2 retry asking for an
  explicit `have`."""
  if not isinstance(logic, list) or not isinstance(s1_json, list):
    return []
  # (a) a "Whose X?" / "who owns X?" wh-question solving for the owner.
  if not _logic_has_ownership_wh_question(logic):
    return []
  # (b) a possessive cue is present in the Stage-1 text.
  cued = _first_possessive_unit(s1_json)
  if cued is None:
    return []
  # (c) the assertion side supplies no ownership relation (have / has part /
  #     ownership verb / relational genitive) — so the possessive was dropped.
  if _assertion_has_ownership(logic):
    return []
  uid, text, cue = cued
  return [Issue(
    kind="possessive_without_ownership",
    location="@id:" + str(uid),
    description=("The text (\"" + text + "\") contains the possessive \""
                 + cue + "\", which asserts ownership, and the question asks "
                 "who owns / whose — but the assertion side emits no `have` "
                 "(or `has part`) predicate, so the owner is never stated. "
                 "Add an explicit ownership atom: resolve the possessive to "
                 "its referent OWNER and emit [\"have\", OWNER, THING] (e.g. "
                 "\"the students brought their books\" → also assert "
                 "[\"have\", \"students 1\", BOOKS]). Use [\"has part\", "
                 "WHOLE, PART] instead only when the possessive is a part-"
                 "whole / body-part relation (\"his arm\" → [\"has part\", "
                 "\"John 1\", ARM])."),
    evidence=safe_json(text),
  )]




# When True (set under entity canonicalization (-entitymerge)), enable the aggressive
# constant-vs-class / dropped-fact repair check that re-prompts the LLM.
aggressive_repair = False




def _csc_norm(s):
  return re.sub(r"[\s_]+", " ", re.sub(r"\s+(?:[0-9]+|[A-Za-z])$", "", s.strip())).lower()




def _check_stage2_constant_vs_class(logic, s1_json):
  """Detect a name used BOTH as a specific entity (a constant) and as a class
  (an isa type) -- e.g. premise "the Winter Olympics" (constant) vs conclusion
  "a winter olympics" (class isa).  The corrective description tells the LLM the
  likely fix and to not drop stated conjuncts (the dropped-fact case)."""
  if not aggressive_repair:
    return []
  types = set()
  def _walk(n):
    if isinstance(n, list):
      if len(n) >= 3 and n[0] == "isa" and isinstance(n[1], str):
        types.add(_csc_norm(n[1]))
      for x in n:
        _walk(x)
  _walk(logic)
  ent = {}
  for pkg in s1_json or []:
    if not isinstance(pkg, dict):
      continue
    for u in pkg.get("units", []):
      for e in u.get("entities", []) if isinstance(u, dict) else []:
        eid = e.get("id") if isinstance(e, dict) else None
        if isinstance(eid, str) and re.search(r"[A-Z]", eid):
          ent[_csc_norm(eid)] = eid
  issues = []
  for t in sorted(types):
    if t in ent and len(t.split()) >= 1 and t not in ("person", "thing"):
      eid = ent[t]
      issues.append(Issue(
        kind="constant_vs_class",
        location=eid,
        description=(
          "The name '" + eid + "' is used as a specific entity (a constant) in "
          "some sentences and as a class/type (inside an isa, e.g. 'a " + t +
          "') elsewhere. They most likely refer to the same thing. Make the "
          "representation consistent: either treat the generic mention as the "
          "same specific entity '" + eid + "', or assert that '" + eid + "' is "
          "an instance of '" + t + "'. Also make sure EVERY fact stated in the "
          "text is present as its own assertion -- do not drop conjuncts such "
          "as 'both A and B' or 'A, B and C'."),
        evidence=t))
  return issues




def check_stage2(logic, s1_json=None):
  """Run all registered Stage-2 sanity checks and return the combined
  issue list.  s1_json provides ASU context for checks that need it
  (currently: the dropped-specific-noun check).
  """
  issues = []
  issues.extend(_check_stage2_constant_vs_class(logic, s1_json))
  issues.extend(_check_stage2_free_variables(logic))
  issues.extend(_check_stage2_misplaced_meta_tense(logic))
  issues.extend(_check_stage2_dropped_specific_noun(logic, s1_json))
  issues.extend(_check_stage2_arities(logic))
  issues.extend(_check_stage2_event_shapes(logic))
  issues.extend(_check_stage2_inner_content_event_time(logic, s1_json))
  issues.extend(_check_stage2_missing_question(logic, s1_json))
  issues.extend(_check_stage2_multiple_questions(logic))
  issues.extend(_check_stage2_vacuous_tautology_assertion(logic))
  issues.extend(_check_stage2_measure_vs_degree_rel2(logic))
  issues.extend(_check_stage2_comparative_as_degree_property(logic, s1_json))
  issues.extend(_check_stage2_multiword_property(logic))
  issues.extend(_check_stage2_either_or_not_xor(logic, s1_json))
  issues.extend(_check_stage2_entity_id_typos(logic))
  issues.extend(_check_stage2_possessive_without_ownership(logic, s1_json))
  return issues




# ======== retry-prompt suffix ========

def format_retry_suffix(issues, flawed_parsed):
  """Build the text appended to the original stage input when re-calling
  the LLM after a sanity-check failure.

  Structure:
    * Shows the LLM's previous (flawed) answer.
    * Lists each issue with kind, location, and description.
    * Asks for a corrected JSON.
  """
  try:
    # sort_keys makes the serialization canonical, so the retry input_text
    # (and thus its LLM-cache key) is byte-identical across runs.
    flawed_str = json.dumps(flawed_parsed, indent=2, sort_keys=True)
  except Exception:
    flawed_str = str(flawed_parsed)

  # Sort the issues into a stable order before formatting.  The checkers may
  # collect issues via sets/dicts, whose iteration order varies across
  # processes under hash randomization; an unstable order would change the
  # corrective prompt byte-for-byte and miss the cache on every fresh run.
  issues = sorted(issues, key=lambda iss: (iss.kind or "", iss.location or "",
                                           iss.description or "", iss.evidence or ""))

  lines = []
  lines.append("")
  lines.append("Your previous answer was:")
  lines.append(flawed_str)
  lines.append("")
  lines.append("This answer has the following issues:")
  for i, iss in enumerate(issues, start=1):
    lines.append(str(i) + ". [" + iss.kind + "] " + iss.description)
    if iss.location:
      lines.append("   location: " + iss.location)
    if iss.evidence:
      lines.append("   offending subtree: " + iss.evidence)
  lines.append("")
  lines.append("Please produce a corrected answer that does not have these "
               "issues. Return only the corrected JSON, with no additional "
               "commentary.")
  lines.append("")
  return "\n".join(lines)
