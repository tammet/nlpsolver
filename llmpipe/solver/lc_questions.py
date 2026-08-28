# Question encoding and population fact injection for the llm-based nlpsolver.
#
# Handles two related concerns that are closely coupled to the PACKAGE structure
# of stage-2 LLM output:
#
#   1. Question wrapping — converting ["ask", var, body] / ["question", body]
#      into GK @question entries and $defq biconditional clause sets.
#
#   2. Population fact injection — scanning all stage-2 items to discover which
#      isa / has-property classes appear, and emitting synthetic $some_* /
#      $some_not_* ground facts so the prover has at least one positive and one
#      negative instance of each class to reason about.
#
# Public API used by logconvert.py:
#   simplify_contradictory_and(frm)
#   is_simple_question_formula(frm)
#   collect_body_free_vars(frm, bound)
#   find_haslocation_prep(body, ask_var)
#   build_defq_question(name, ask_var, body, where_prep)
#   find_where_atom(body, ask_var)
#   build_where_question(name, entity, ask_var, specific_prep)
#   flatten_q_atoms(frm, varmap)
#   scan_item_formula(frm, name, polarity, classes, has_props, deg_props)
#   build_population_facts(classes, has_props, deg_props)
#   is_ground_term(term)
#   S2_VAR_RE, WHERE_SPATIAL_PREPS, _WHERE_META_PREDS
#
# Module-level counter reset by logconvert.rawlogic_convert():
#   _defq_nr  -- $defq predicate numbering
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

from lc_clausify import (
  looks_like_var,
  apply_varmap,
  clausify,
  connectives,
)


# Counter for $defq predicate names (reset per top-level call).
_defq_nr = 0

# Spatial prepositions handled by "Where is X?" queries.
_SPATIAL_PREPS = ["in", "on", "at", "near", "above", "under"]

# Stage-2 meta-predicates that indicate a "Where is X?" location query.
_WHERE_META_PREDS = frozenset({"located in", "located at", "located on",
                               "located near", "location", "located"})

WHERE_SPATIAL_PREPS = frozenset(_SPATIAL_PREPS)

# Temporal prepositions handled by "When is X?" queries.
_TEMPORAL_PREPS = ["in", "at", "on", "during", "before", "after"]

# Stage-2 meta-predicates that indicate a "When is X?" temporal query.
_WHEN_META_PREDS = frozenset({"scheduled for", "happens in", "occurs at",
                               "takes place in", "happens at", "occurs in",
                               "scheduled at"})

WHEN_TEMPORAL_PREPS = frozenset(_TEMPORAL_PREPS)

# Stage-2 variable pattern: uppercase-initial identifier (X, Y, Entity, ...).
# Kept for importers; the decision itself is `lc_clausify.looks_like_var_broad`,
# which excludes world constants.
S2_VAR_RE = re.compile(r'^[A-Z][A-Za-z0-9]*$')


# ======== yes/no question helpers ========

def simplify_contradictory_and(frm):
  """Simplify ["and", ["not", A], A] to ["not", A].

  The LLM sometimes generates such a contradictory conjunction for yes/no
  questions that ask about a universally-negative statement (e.g. "No elephant
  is an animal?" → ["and", ["not", exists-elephant-animal], exists-elephant-animal]).
  In that case the correct question formula is just the negative part ["not", A].

  Only the pattern NOT-first is simplified.  The pattern A-first (["and", A, ["not", A]])
  is left unchanged because in that case the original self-contradictory formula
  happens to let the prover return the correct answer (e.g. False for
  "John is not defeated?" when John IS defeated).
  """
  if not (isinstance(frm, list) and len(frm) == 3 and frm[0] == "and"):
    return frm
  a, b = frm[1], frm[2]
  # Pattern: ["not", X] and X  (negation comes first)
  if isinstance(a, list) and a and a[0] == "not" and len(a) == 2 and a[1] == b:
    return a
  return frm


def is_simple_question_formula(frm):
  """Return True if frm is a single positive atom with at most 1 distinct variable.

  Simple questions are handled with a direct @question entry (no $defq wrapper).
  Complex questions (multiple atoms, 2+ variables, or nested connectives) need
  the $defq biconditional approach so the prover has richer resolution paths.

  Examples:
    ["isa", "animal", "John 1"]  -> True  (0 variables)
    ["isa", "animal", "X"]       -> True  (1 variable)
    ["have", "X", "Y"]           -> False (2 variables)
    ["and", ...]                 -> False (connective, not a single atom)
    ["forall", "X", ...]         -> False (quantifier, not a single atom)
  """
  if not isinstance(frm, list) or not frm:
    return False
  pred = frm[0]
  if not isinstance(pred, str) or pred in connectives or pred.startswith("-"):
    return False
  for arg in frm[1:]:
    if isinstance(arg, list):
      return False              # nested structure -> not a flat atom
  vars_seen = set()
  for arg in frm[1:]:
    if isinstance(arg, str) and looks_like_var(arg):
      vars_seen.add(arg)
  return len(vars_seen) <= 1


def collect_body_free_vars(frm, bound=None):
  """Collect free variable names appearing in a stage-2 formula.

  Returns a set of plain variable names (e.g. {"Y", "Z"}) that:
    - appear as atom arguments
    - look like variable names (see looks_like_var)
    - are NOT bound by any forall/exists quantifier in frm
    - are NOT in the initial 'bound' set

  Used to find the non-ask free variables that must be wrapped in 'exists'
  before constructing the $defq biconditional.
  """
  if bound is None:
    bound = frozenset()
  if not isinstance(frm, list) or not frm:
    return set()
  op = frm[0]
  if op in ("forall", "exists"):
    var = str(frm[1])
    return collect_body_free_vars(frm[2], bound | {var})
  if op in connectives:
    result = set()
    for el in frm[1:]:
      result |= collect_body_free_vars(el, bound)
    return result
  # Atom: frm[0] is the predicate, frm[1:] are arguments.
  result = set()
  for arg in frm[1:]:
    if isinstance(arg, str) and looks_like_var(arg) and arg not in bound:
      result.add(arg)
    elif isinstance(arg, list):
      result |= collect_body_free_vars(arg, bound)
  return result


# ======== has-location prep detection ========

def _find_has_event_role(body, ask_var, role_pred, default_prep):
  """Return default_prep if body contains [role_pred, event_var, ask_var], else None.

  Searches recursively through "and"/"exists"/"forall" wrappers.
  Parameterized: role_pred is "has location" or "has time", etc.
  """
  if not isinstance(body, list) or not body:
    return None
  if body[0] == role_pred and len(body) >= 3 and body[2] == ask_var:
    # Extract preposition from index 3 if present (new 4-arg form)
    if len(body) >= 4 and isinstance(body[3], str) and not body[3].startswith("?:"):
      return body[3]
    return default_prep
  if body[0] == "and":
    for item in body[1:]:
      found = _find_has_event_role(item, ask_var, role_pred, default_prep)
      if found is not None:
        return found
  if body[0] in ("exists", "forall") and len(body) >= 3:
    return _find_has_event_role(body[2], ask_var, role_pred, default_prep)
  # Transparent wrappers: @time, normally, question, ask, holds
  if body[0] in ("@time", "normally", "question", "ask", "holds"):
    return _find_has_event_role(body[-1], ask_var, role_pred, default_prep)
  return None

def find_haslocation_prep(body, ask_var):
  """Return "in" if body contains ["has location", event_var, ask_var], else None."""
  return _find_has_event_role(body, ask_var, "has location", "in")

def find_hastime_prep(body, ask_var):
  """Return "in" if body contains ["has time", event_var, ask_var], else None."""
  return _find_has_event_role(body, ask_var, "has time", "in")


# ======== $defq biconditional question builder ========

_WH_PREP_PREDS = frozenset({"has location", "has time"})

def _replace_prep_with_var(body, concrete_prep, prep_var, target_pred=None):
  """Replace concrete preposition in has_location/has_time atoms with a variable.

  Walks the body recursively.  When an atom of the target predicate has
  concrete_prep at index 3, replaces it with prep_var.
  If target_pred is None, targets all predicates in _WH_PREP_PREDS.
  Returns a modified copy (does not mutate the original).
  """
  if not isinstance(body, list) or not body:
    return body
  pred = body[0]
  match_preds = {target_pred} if target_pred else _WH_PREP_PREDS
  if (isinstance(pred, str) and pred in match_preds
      and len(body) >= 4 and body[3] == concrete_prep):
    return body[:3] + [prep_var] + body[4:]
  return [_replace_prep_with_var(child, concrete_prep, prep_var, target_pred)
          if isinstance(child, list) else child
          for child in body]


def _tree_contains_atom_str(tree, target):
  """True if the string `target` occurs anywhere in the nested list `tree`."""
  if isinstance(tree, str):
    return tree == target
  if isinstance(tree, list):
    return any(_tree_contains_atom_str(el, target) for el in tree)
  return False


def _walk_subst(frm, var, replacement):
  """Substitute every free occurrence of variable name `var` in `frm` with
  `replacement`.  Respects scoping: skips subtrees of binders that re-bind `var`.
  """
  if not isinstance(frm, list):
    return replacement if frm == var else frm
  if not frm:
    return frm
  op = frm[0]
  if op in ("forall", "exists", "ask") and len(frm) >= 3 and frm[1] == var:
    return frm
  return [_walk_subst(el, var, replacement) for el in frm]


def _atom_mentions_var(atom, var):
  """True if `atom` is a flat predicate atom that has `var` as one of its
  top-level arguments.  Predicate atoms are lists whose first element is a
  string predicate name (possibly negated with '-').
  """
  if not isinstance(atom, list) or not atom:
    return False
  if not isinstance(atom[0], str):
    return False
  for el in atom[1:]:
    if el == var:
      return True
  return False


def _norm_class(cls):
  """Class key for the generic-premise test: lowercase, singular-ish."""
  s = str(cls or "").strip().lower()
  if len(s) > 3 and s.endswith("ies"):
    return s[:-3] + "y"
  if len(s) > 2 and s.endswith("es") and not s.endswith("ses"):
    return s[:-2]
  if len(s) > 2 and s.endswith("s"):
    return s[:-1]
  return s


_EXIST_DET_RE_CACHE = {}


def collect_generic_rule_classes(items):
  """(plan fix 4) Classes that some premise package quantifies over generically.

  A class qualifies when a package contains  forall V ( ... isa(C, V) ... → ... ),
  i.e. a rule whose antecedent types the bound variable.  Those are the classes
  for which a fresh generic witness has a rule to fire on.
  """
  out = set()

  def scan(node, bound):
    if not isinstance(node, list) or not node:
      return
    op = node[0] if isinstance(node[0], str) else None
    if op == "forall" and len(node) >= 3:
      scan(node[2], bound | {node[1]})
      return
    if op == "implies" and len(node) >= 3:
      ante = node[1]
      atoms = ante[1:] if (isinstance(ante, list) and ante and ante[0] == "and") else [ante]
      for a in atoms:
        if (isinstance(a, list) and len(a) >= 3 and a[0] == "isa"
            and isinstance(a[1], str) and a[2] in bound):
          out.add(_norm_class(a[1]))
      for child in node[1:]:
        scan(child, bound)
      return
    if op is not None:
      for child in node[1:]:
        scan(child, bound)
    else:
      for child in node:
        scan(child, bound)

  for item in (items or []):
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      pkg = item[2]
      # PREMISES only.  The generic yes/no question itself has the very
      # forall/implies/isa shape this scan looks for, so including it would
      # put its own class into the set and make the "some premise quantifies
      # generically over C" condition always true (audit find: gemini 743).
      if (isinstance(pkg, list) and pkg
          and pkg[0] in ("question", "ask")):
        continue
      scan(pkg, frozenset())
    else:
      scan(item, frozenset())
  return out


def hoist_generic_yn_subject(formula, name, asu_text=None, generic_classes=None):
  """Detect the bare-plural-generic yes/no question pattern and rewrite.

  Pattern (per Stage-2 prompt §7.4(a)):
    ["forall", VAR, ["implies", ANTE, ["normally", BODY]]]

  where ANTE is either a single atom mentioning VAR, or
    ["and", ATOM_1, ATOM_2, ...] with every ATOM_i mentioning VAR.
  At least one ATOM must be ["isa", CLASS, VAR] (used to name the skolem).

  On match, return:
    (skq_const, hoisted_atom, rewritten_body)
  where:
    - skq_const: fresh constant "skq_<sid>_<class>" (sid extracted from name).
    - hoisted_atom: ANTE with VAR substituted by skq_const.  Returned as a
      single ["and", ...] when ANTE was already an "and"; otherwise a single
      atom list.
    - rewritten_body: BODY with VAR substituted by skq_const.

  Otherwise return (None, None, formula) unchanged.
  """
  if not (isinstance(formula, list) and len(formula) >= 3
          and formula[0] == "forall"):
    return (None, None, formula)
  var = formula[1]
  inner = formula[2]
  if not (isinstance(inner, list) and len(inner) >= 3
          and inner[0] == "implies"):
    return (None, None, formula)
  ante = inner[1]
  cons = inner[2]
  if not (isinstance(cons, list) and len(cons) >= 2
          and cons[0] == "normally"):
    return (None, None, formula)
  body = cons[1]

  if isinstance(ante, list) and ante and ante[0] == "and":
    atoms = list(ante[1:])
  else:
    atoms = [ante]

  isa_class = None
  for a in atoms:
    if (isinstance(a, list) and len(a) >= 3
        and a[0] == "isa" and a[2] == var):
      isa_class = a[1]
      break
  if isa_class is None:
    return (None, None, formula)

  for a in atoms:
    if not _atom_mentions_var(a, var):
      return (None, None, formula)

  # (plan fix 4) The hoist is only right for a BARE-PLURAL GENERIC question
  # ("Do birds fly?").  The newer models emit this same forall+normally shape
  # for plain EXISTENTIAL questions ("Does a square have a nail?"), where the
  # fresh witness is not the square the premises talk about and the question
  # becomes unanswerable by construction.  Require both:
  #   1. the question text does not introduce the class with an existential
  #      determiner ("a"/"an"/"some");
  #   2. some premise actually quantifies generically over the class, so a
  #      generic witness has a rule to fire.
  from globals import options as _opts
  if _opts.get("nofix_skqguard"):
    pass          # guard disabled: original unconditional hoist behaviour
  # On refusal the question must become EXISTENTIAL — "is there a C such that
  # BODY?" — not stay the universal forall+normally shape, which clausifies
  # into a goal no premise can discharge (that is the "strict-collapse" form
  # the hoist was invented to avoid).
  #
  # Sole criterion: does some PREMISE quantify generically over the class?
  # (An earlier second condition — an existential determiner "a C" in the
  # question text — was removed by the old-model control audit: every observed
  # recovery is already explained by this criterion, and the determiner rule
  # broke FOLIO's generic-"a" readings, turning gold-Unknown "A smarter person
  # has gained knowledge?" into a proved existential.)
  elif (generic_classes is not None
        and _norm_class(isa_class) not in generic_classes):
    # (quniv, a `fallback_norm` switch) keep the universal reading instead of the
    # existential rewrite: the existential defq can neither be proved nor
    # refuted by a stated counterexample ("a duster ... doesn't suck", FOLIO
    # 137), while the universal biconditional lets the counterexample refute.
    if _opts.get("quniv_flag", False):
      return (None, None, formula)
    existential = ["exists", var, ["and"] + list(atoms) + [body]]
    return (None, None, existential)

  sid = name[5:] if isinstance(name, str) and name.startswith("sent_") else str(name)
  cname = str(isa_class).replace(" ", "_")
  skq = "skq_" + sid + "_" + cname

  hoisted_atoms = [_walk_subst(a, var, skq) for a in atoms]
  if len(hoisted_atoms) == 1:
    hoisted = hoisted_atoms[0]
  else:
    hoisted = ["and"] + hoisted_atoms
  rewritten_body = _walk_subst(body, var, skq)
  return (skq, hoisted, rewritten_body)


def _strip_normally(frm):
  """Recursively strip 'normally' wrappers from a formula.

  Questions should not contain 'normally' — it is a modality for assertions,
  not queries.  When an LLM wraps the query body in 'normally', the clausifier
  turns it into $block atoms that create self-referential blockers, preventing
  the prover from finding answers.  Stripping 'normally' before clausification
  fixes this.
  """
  if not isinstance(frm, list) or not frm:
    return frm
  op = frm[0]
  if op == "normally" and len(frm) >= 2:
    return _strip_normally(frm[1])
  return [_strip_normally(el) for el in frm]


def build_defq_question(name, ask_var, body, where_prep=None,
                        wh_prep=None, wh_marker=None, wh_prep_pred=None):
  """Build $defq biconditional @logic clauses and a @question entry.

  For a wh-question (ask_var is not None, e.g. "X"):
    Constructs:  forall X. ($defq0(X) <=> exists Ys. body)
    Emits:       @logic clauses (with @sourcetype:"question") from the CNF
                 @question: [$defq0, ?:X]  with @askvars: 1

  For a yes/no question (ask_var is None):
    Constructs:  $defq0() <=> body
    Emits:       @logic clauses (with @sourcetype:"question") from the CNF
                 @question: [$defq0]

  wh_prep/wh_marker: if wh_prep is set (e.g. "in"), the $defq atom becomes
    2-arg [$defqN, Prep, X] so that the answer includes the preposition.
    The concrete prep in has_location/has_time atoms is replaced with a
    forall-bound variable so it matches any preposition.
    Sets @askvars:2 and q_obj[wh_marker]=True.
    wh_marker is "@where_query" or "@when_query".
  where_prep: legacy alias for wh_prep with wh_marker="@where_query".

  Non-ask free variables in body are automatically wrapped in 'exists' so
  the clausification handles them correctly (Skolem functions of ask_var).
  """
  # Strip 'normally' from question body — it creates self-referential $block
  # atoms in query clauses that prevent the prover from finding answers.
  body = _strip_normally(body)

  # Legacy alias
  if where_prep and not wh_prep:
    wh_prep = where_prep
    wh_marker = "@where_query"
  global _defq_nr
  defq_name = "$defq" + str(_defq_nr)
  _defq_nr += 1

  # When wh_prep is set, replace the concrete preposition in the body with
  # a variable so the biconditional matches any preposition.
  #
  # Orphan-prep filter: _replace_prep_with_var only rewrites has_location /
  # has_time atoms (preposition at index 3).  When the query body instead
  # pins the preposition inside an `is rel2` atom (index 1), the replacement
  # is a no-op and prep_var would land in the $defq atom without occurring
  # in the body — an orphan ask-var the prover leaves free (renders as
  # "?:X3").  In that case keep the 2-arg $defq but put the LITERAL
  # preposition in the slot instead of the variable: no orphan, and the
  # in/under/at distinction is still reported from the literal.
  prep_var  = "_Prep"
  prep_slot = None        # value placed in the $defq preposition slot
  if wh_prep and ask_var:
    new_body = _replace_prep_with_var(body, wh_prep, prep_var,
                                      target_pred=wh_prep_pred)
    if _tree_contains_atom_str(new_body, prep_var):
      body      = new_body
      prep_slot = prep_var      # body genuinely varies the preposition
    else:
      prep_slot = wh_prep       # body fixed the preposition to a literal

  # Wrap body in 'exists' for every free variable that is not the ask variable.
  initial_bound = {ask_var} if ask_var else set()
  if prep_slot == prep_var:
    initial_bound.add(prep_var)
  free_vars = sorted(collect_body_free_vars(body, bound=initial_bound))
  wrapped_body = body
  for fv in free_vars:
    wrapped_body = ["exists", fv, wrapped_body]

  # Build the biconditional formula.
  if ask_var:
    if wh_prep:
      # 2-arg $defq: [$defqN, PREP, X].  PREP is the _Prep variable when the
      # body varies the preposition, or a literal when the body fixed it.
      defq_atom = [defq_name, prep_slot, ask_var]
      q_atom    = [defq_name, "?:Rel", "?:" + ask_var]
      askvars   = 2
      if prep_slot == prep_var:
        frm = ["forall", ask_var, ["forall", prep_var,
                ["equivalent", defq_atom, wrapped_body]]]
      else:
        frm = ["forall", ask_var, ["equivalent", defq_atom, wrapped_body]]
    else:
      defq_atom = [defq_name, ask_var]
      q_atom    = [defq_name, "?:" + ask_var]
      askvars   = 1
      frm = ["forall", ask_var, ["equivalent", defq_atom, wrapped_body]]
  else:
    defq_atom = [defq_name]
    frm = ["equivalent", defq_atom, wrapped_body]
    q_atom = [defq_name]
    askvars = None

  # Clausify using the existing CNF machinery (handles forall/exists/equivalent).
  clauses = clausify(frm)

  # Each clause gets @sourcetype:"question" to mark it as question-derived.
  result = []
  for clause in clauses:
    result.append({"@name": name, "@sourcetype": "question", "@logic": clause})

  # The @question entry itself does not carry @sourcetype.
  q_obj = {"@name": name, "@question": q_atom}
  if askvars is not None:
    q_obj["@askvars"] = askvars
  if wh_marker:
    q_obj[wh_marker] = True
  result.append(q_obj)
  return result


# ======== "Where/When is X?" query builders ========

def _find_prep_query_atom(body, ask_var, pred_set, pred_prefixes=()):
  """Find and return a preposition-query atom within body, or None.

  Matches atoms of the form  ["is rel2", pred, entity, ask_var]  where
  pred is in pred_set (or starts with one of pred_prefixes) and ask_var
  appears as the LAST positional argument.

  pred_prefixes catches non-standard location meta-predicates an LLM may
  invent, e.g. gpt's "located in or near" for "Where is X?" — any pred
  starting with "located" is a where-query trigger (case 1252).

  Handles forms:
    Simple:      ["is rel2", pred, entity, ask_var]
    Compound:    ["and", ..., <matching atom>, ...]
    Existential: ["exists", var, <body>]
  Returns the matching atom list if found, else None.
  """
  if not isinstance(body, list) or not body:
    return None
  if (body[0] == "is rel2" and len(body) in (4, 5) and body[3] == ask_var
      and (body[1] in pred_set
           or (isinstance(body[1], str) and pred_prefixes
               and body[1].startswith(pred_prefixes)))):
    return body
  if body[0] == "and":
    for item in body[1:]:
      found = _find_prep_query_atom(item, ask_var, pred_set, pred_prefixes)
      if found is not None:
        return found
  if body[0] in ("exists", "forall") and len(body) >= 3:
    return _find_prep_query_atom(body[2], ask_var, pred_set, pred_prefixes)
  return None

def find_where_atom(body, ask_var):
  """Find a where-query atom (spatial meta-pred or preposition) in body."""
  return _find_prep_query_atom(body, ask_var, _WHERE_META_PREDS | WHERE_SPATIAL_PREPS,
                               pred_prefixes=("located",))

def find_when_atom(body, ask_var):
  """Find a when-query atom (temporal meta-pred or preposition) in body."""
  return _find_prep_query_atom(body, ask_var, _WHEN_META_PREDS | WHEN_TEMPORAL_PREPS)


def _s2var_to_gk(name_str):
  """Convert a stage-2 variable name like 'Y' to a GK variable '?:Y'.

  Stage-2 variables are uppercase-initial identifiers (X, Y, Entity, ...).
  Constants (John 1, box 1, etc.) contain spaces or start lowercase.
  If already a GK variable (starts with "?:"), returned unchanged.
  """
  if isinstance(name_str, str):
    if name_str.startswith("?:"):
      return name_str
    from lc_clausify import looks_like_var_broad
    if looks_like_var_broad(name_str):
      return "?:" + name_str
  return name_str


def _build_prep_question(name, entity, ask_var, prep_list, query_marker,
                         specific_prep=None):
  """Build biconditional @logic clauses and @question entry for a preposition query.

  For each preposition p in the applicable set, generates two CNF clauses:
    Forward:  ["-is rel2", p, entity_gk, "?:Q1"], [$defqN, p, "?:Q1"]
    Backward: ["-" + defqN, p, "?:Q1"],            ["is rel2", p, entity_gk, "?:Q1"]

  entity may be a stage-2 variable name (e.g. "Y") — it is converted to a GK
  variable ("?:Y") so the biconditional matches any entity's location/time.

  If specific_prep is given (e.g. "near"), only that preposition is used;
  otherwise all prep_list entries are used.

  query_marker is "@where_query" or "@when_query".
  The @question is [$defqN, ?:Rel, ?:Q1] with @askvars=2.
  $ctxt is injected into "is rel2" atoms automatically by _inject_ctxt_into_objs.
  """
  global _defq_nr
  defq_name = "$defq" + str(_defq_nr)
  _defq_nr += 1

  entity_gk = _s2var_to_gk(entity)
  preps = [specific_prep] if specific_prep else prep_list

  result = []
  for prep in preps:
    # Forward: is_rel2(prep, entity_gk, Q1) => defqN(prep, Q1)
    fwd = [["-is rel2", prep, entity_gk, "?:Q1"], [defq_name, prep, "?:Q1"]]
    result.append({"@name": name, "@sourcetype": "question", "@logic": fwd})
    # Backward: defqN(prep, Q1) => is_rel2(prep, entity_gk, Q1)
    bwd = [["-" + defq_name, prep, "?:Q1"], ["is rel2", prep, entity_gk, "?:Q1"]]
    result.append({"@name": name, "@sourcetype": "question", "@logic": bwd})

  q_atom = [defq_name, "?:Rel", "?:Q1"]
  q_obj = {"@name": name, "@question": q_atom, "@askvars": 2, query_marker: True}
  result.append(q_obj)
  return result

def build_where_question(name, entity, ask_var, specific_prep=None):
  """Build where-query biconditional clauses (spatial prepositions)."""
  return _build_prep_question(name, entity, ask_var, _SPATIAL_PREPS,
                              "@where_query", specific_prep)

def build_when_question(name, entity, ask_var, specific_prep=None):
  """Build when-query biconditional clauses (temporal prepositions)."""
  return _build_prep_question(name, entity, ask_var, _TEMPORAL_PREPS,
                              "@when_query", specific_prep)


def build_who_question(name, entity, ask_var, who_kind="who"):
  """Build who/what-query biconditional clauses for 'Who is X?' / 'What is X?'.

  Generates biconditional sets sharing one $defq:
    Set 1 — isa: what types does ENTITY have?
    Set 2 — equality: what equals ENTITY?
    Set 3 — properties (has degree property): what properties does ENTITY have?
  The prover returns all matching types, equal entities, and properties.
  who_kind is "who" or "what" — controls answer ranking in procproofs.
  """
  global _defq_nr
  defq_name = "$defq" + str(_defq_nr)
  _defq_nr += 1

  entity_gk = _s2var_to_gk(entity)

  result = []

  # Set 1: isa(?:X, entity) <=> $defqN(?:X)
  fwd_isa = [["-isa", "?:X", entity_gk], [defq_name, "?:X"]]
  result.append({"@name": name, "@sourcetype": "question", "@logic": fwd_isa})
  bwd_isa = [["-" + defq_name, "?:X"], ["isa", "?:X", entity_gk]]
  result.append({"@name": name, "@sourcetype": "question", "@logic": bwd_isa})

  # Set 2: =(?:X, entity) <=> $defqN(?:X)
  fwd_eq = [["-=", "?:X", entity_gk], [defq_name, "?:X"]]
  result.append({"@name": name, "@sourcetype": "question", "@logic": fwd_eq})
  bwd_eq = [["-" + defq_name, "?:X"], ["=", "?:X", entity_gk]]
  result.append({"@name": name, "@sourcetype": "question", "@logic": bwd_eq})

  # Property biconditionals are deferred to phase 2 — the search space expansion
  # from has_degree_property with variable PROP causes prover performance issues.

  q_obj = {"@name": name, "@question": [defq_name, "?:X"],
           "@askvars": 1, "@who_query": True, "@who_entity": entity,
           "@who_kind": who_kind}
  result.append(q_obj)
  return result


# ======== question formula flattening ========

def flatten_q_atoms(frm, varmap):
  """Strip all quantifiers and flatten AND conjunctions in a question formula.

  Every bound variable (forall or exists) is renamed to ?:VAR and the
  quantifier wrapper is dropped.  Nested ["and", ...] conjunctions are
  recursively flattened.  All other formulas (atoms, or, etc.) have the
  varmap applied and are returned as a single-element list.

  Returns a flat list of atoms ready for the @question value.
  """
  if not isinstance(frm, list) or not frm:
    return []
  op = frm[0]

  if op in ("exists", "forall"):
    var    = str(frm[1])
    gk_var = "?:" + var
    new_vm = dict(varmap)
    new_vm[var] = gk_var
    return flatten_q_atoms(frm[2], new_vm)

  if op == "and":
    atoms = []
    for el in frm[1:]:
      atoms.extend(flatten_q_atoms(el, varmap))
    return atoms

  # Atom or other formula (or, not, …) — apply varmap, return as one item.
  return [apply_varmap(frm, varmap)]


# ======== population fact injection ========

def _norm_for_const(s):
  """Normalise a class/property name for use in a $some_* constant name.
  Spaces become underscores; other characters kept as-is.
  """
  return str(s).replace(" ", "_")


def is_ground_term(term):
  """Return True if term is a ground constant (not a variable or term with vars).

  Strings that look like variables (uppercase-initial no-space identifiers, or
  ?:-prefixed GK variables) are not ground.  Lists (Skolem function terms) are
  not ground.  All other strings are treated as ground constants.
  """
  return isinstance(term, str) and not looks_like_var(term)


def _record_polarity(registry, key, name, entity, atom_pol):
  """Register a positive or negative ground occurrence in a scan registry."""
  if key not in registry:
    registry[key] = {"name": name, "has_pos": False, "has_neg": False}
  if is_ground_term(entity):
    if atom_pol:
      registry[key]["has_pos"] = True
    else:
      registry[key]["has_neg"] = True


def scan_item_formula(frm, name, polarity, classes, has_props, deg_props,
                      compound_witnesses=None):
  """Recursively scan a formula for isa / has-property / has-degree-property atoms.

  Works on both raw stage-2 formulas (connectives and/or/not/forall/exists/
  implies/equivalent/xor/ask) and clausified GK clause lists (disjunctions
  represented as a list whose first element is itself a list).

  Arguments:
    frm       -- formula or clause to scan
    name      -- sent_SN name to record on first occurrence
    polarity  -- True = positive context, False = negative context
    classes   -- dict: CLASS -> {"name", "has_pos", "has_neg"}
    has_props -- dict: PROPERTY -> {"name", "has_pos", "has_neg"}
    deg_props -- dict: (PROPERTY, RELCLASS) -> {"name", "has_pos", "has_neg"}
    compound_witnesses -- dict or None: accumulates compound antecedent patterns
  """
  if not isinstance(frm, list) or not frm:
    return
  first = frm[0]

  _cw = compound_witnesses  # shorthand

  # Clausified disjunction: first element is itself a list (atom).
  if isinstance(first, list):
    for atom in frm:
      scan_item_formula(atom, name, polarity, classes, has_props, deg_props, _cw)
    return

  pred = first

  # Structural connectives — recurse, tracking polarity.
  if pred in ("and", "or", "equivalent", "xor"):
    for el in frm[1:]:
      scan_item_formula(el, name, polarity, classes, has_props, deg_props, _cw)
    return
  if pred == "implies":
    # Scan antecedent for compound witness patterns (in positive polarity,
    # meaning the rule itself is asserted — the antecedent describes a class).
    if len(frm) >= 3:
      if polarity and _cw is not None:
        _scan_compound_antecedent(frm[1], name, _cw)
      scan_item_formula(frm[1], name, polarity, classes, has_props, deg_props, _cw)
      scan_item_formula(frm[2], name, polarity, classes, has_props, deg_props, _cw)
    return
  if pred == "not":
    if len(frm) >= 2:
      scan_item_formula(frm[1], name, not polarity, classes, has_props, deg_props, _cw)
    return
  if pred in ("forall", "exists"):
    if len(frm) >= 3:
      scan_item_formula(frm[2], name, polarity, classes, has_props, deg_props, _cw)
    return
  # ["ask", var, body] — scan the body.
  if pred == "ask":
    if len(frm) >= 3:
      scan_item_formula(frm[2], name, polarity, classes, has_props, deg_props, _cw)
    return
  # Transparent wrappers — recurse into the formula argument.
  if pred == "normally" or pred == "question":
    if len(frm) >= 2:
      scan_item_formula(frm[1], name, polarity, classes, has_props, deg_props, _cw)
    return
  if pred == "holds":
    if len(frm) >= 3:
      scan_item_formula(frm[2], name, polarity, classes, has_props, deg_props, _cw)
    return

  # Atom (may carry a "-" negation prefix on the predicate name).
  if isinstance(pred, str) and pred.startswith("-"):
    actual_pred = pred[1:]
    atom_pol    = not polarity
  else:
    actual_pred = pred
    atom_pol    = polarity

  args = frm[1:]

  if actual_pred == "isa" and len(args) >= 2:
    _record_polarity(classes, str(args[0]), name, args[1], atom_pol)

  elif actual_pred == "has property" and len(args) >= 2:
    _record_polarity(has_props, str(args[0]), name, args[1], atom_pol)

  elif actual_pred == "has degree property" and len(args) >= 4:
    relclass = args[3]
    # Only include when RELCLASS is a constant (not a variable).
    if isinstance(relclass, str) and not looks_like_var(relclass):
      _record_polarity(deg_props, (str(args[0]), relclass), name, args[1], atom_pol)


def _scan_compound_antecedent(ante, name, compound_witnesses):
  """Scan a rule antecedent for compound patterns on the same variable.

  Detects two flavors:
    (a) type + spatial relation: isa(TYPE, VAR) + is_rel2/has_degree_rel2(prep, VAR, ground_target)
    (b) type + adjective property: isa(TYPE, VAR) + has_property(ATTR, VAR)
        or has_degree_property(ATTR, VAR, intensity, relclass)

  For each match, records a compound witness pattern so that
  build_population_facts can emit a concrete intersection entity that satisfies
  both atoms — needed by defeasibility cases where rules of shape
  "ADJ TYPEs are/are not P" must apply to a concrete witness (case 74).
  """
  if not isinstance(ante, list) or not ante:
    return
  # Unwrap single-child and
  if ante[0] != "and":
    return
  conjuncts = ante[1:]

  # Collect conditions grouped by variable
  var_isa = {}       # var -> list of (type_name,)
  var_spatial = {}    # var -> list of (pred, prep, target, extra_args)
  var_adj = {}        # var -> list of (pred, attr, intensity_or_None, relclass_or_None)

  for conj in conjuncts:
    if not isinstance(conj, list) or len(conj) < 3:
      continue
    pred = conj[0]
    if not isinstance(pred, str):
      continue

    if pred == "isa" and len(conj) >= 3:
      typ, entity = conj[1], conj[2]
      if isinstance(typ, str) and isinstance(entity, str) and looks_like_var(entity):
        var_isa.setdefault(entity, []).append(typ)

    elif pred in ("is rel2", "has degree rel2") and len(conj) >= 4:
      prep, entity, target = conj[1], conj[2], conj[3]
      if (isinstance(entity, str) and looks_like_var(entity)
          and isinstance(prep, str) and isinstance(target, str)
          and not looks_like_var(target)):
        extra = conj[4:] if len(conj) > 4 else []
        var_spatial.setdefault(entity, []).append((pred, prep, target, extra))

    elif pred == "has property" and len(conj) >= 3:
      attr, entity = conj[1], conj[2]
      if (isinstance(attr, str) and isinstance(entity, str)
          and looks_like_var(entity)):
        var_adj.setdefault(entity, []).append(("has property", attr, None, None))

    elif pred == "has degree property" and len(conj) >= 5:
      attr, entity, intensity, relclass = conj[1], conj[2], conj[3], conj[4]
      if (isinstance(attr, str) and isinstance(entity, str)
          and looks_like_var(entity)
          and isinstance(intensity, str) and isinstance(relclass, str)):
        var_adj.setdefault(entity, []).append(
          ("has degree property", attr, intensity, relclass))

  # Generate compound witnesses for variables with both type and spatial
  for var in var_isa:
    if var not in var_spatial:
      continue
    for typ in var_isa[var]:
      for pred, prep, target, extra in var_spatial[var]:
        # Build key to dedup
        key = (typ, pred, prep, target)
        if key not in compound_witnesses:
          compound_witnesses[key] = {
            "kind": "spatial",
            "name": name, "type": typ, "pred": pred,
            "prep": prep, "target": target, "extra": extra,
          }

  # Generate compound witnesses for variables with both type and adjective
  for var in var_isa:
    if var not in var_adj:
      continue
    for typ in var_isa[var]:
      for pred, attr, intensity, relclass in var_adj[var]:
        key = (typ, pred, attr, intensity, relclass)
        if key not in compound_witnesses:
          compound_witnesses[key] = {
            "kind": "adjective",
            "name": name, "type": typ, "pred": pred,
            "attr": attr, "intensity": intensity, "relclass": relclass,
          }


def collect_concrete_intersections(items):
  """Walk raw stage-2 items; return a set of (TYPE, PRED, ATTR, INT, RC) keys
  that are already satisfied by a concrete ground entity in the input.

  A key is "satisfied" when some ground entity X has BOTH a positive
  isa(TYPE, X) atom and a positive PRED(ATTR, X, ...) atom (where PRED is
  "has property" or "has degree property", with matching INT/RC if applicable).

  Used by build_population_facts to suppress redundant adjective intersection
  witnesses when a real entity already covers the conjunction (case cars3:
  "John is a red car" makes $some_red_car redundant noise).
  """
  isa_entities = {}     # TYPE -> set of ground entities
  has_prop_entities = {}  # ATTR -> set of ground entities
  deg_prop_entities = {}  # (ATTR, INT, RC) -> set of ground entities

  def walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    first = frm[0]
    # Disjunction-of-clauses or list of clauses (clausified shape)
    if isinstance(first, list):
      for atom in frm:
        walk(atom)
      return
    if not isinstance(first, str):
      return
    # Connectives and wrappers — recurse into children
    if first in ("@id", "and", "or", "implies", "not", "forall", "exists",
                 "ask", "normally", "question", "holds", "@time"):
      for child in frm[1:]:
        if isinstance(child, list):
          walk(child)
      return
    # Atoms — only collect positive polarity
    pred = first
    if pred.startswith("-"):
      return
    if pred == "isa" and len(frm) >= 3:
      typ, ent = frm[1], frm[2]
      if isinstance(typ, str) and is_ground_term(ent):
        isa_entities.setdefault(typ, set()).add(ent)
    elif pred == "has property" and len(frm) >= 3:
      attr, ent = frm[1], frm[2]
      if isinstance(attr, str) and is_ground_term(ent):
        has_prop_entities.setdefault(attr, set()).add(ent)
    elif pred == "has degree property" and len(frm) >= 5:
      attr, ent, intensity, rc = frm[1], frm[2], frm[3], frm[4]
      if (isinstance(attr, str) and is_ground_term(ent)
          and isinstance(intensity, str) and isinstance(rc, str)):
        deg_prop_entities.setdefault((attr, intensity, rc), set()).add(ent)

  for item in items:
    walk(item)

  satisfied = set()
  # has_property intersections
  for typ, type_ents in isa_entities.items():
    for attr, attr_ents in has_prop_entities.items():
      if type_ents & attr_ents:
        satisfied.add((typ, "has property", attr, None, None))
  # has_degree_property intersections
  for typ, type_ents in isa_entities.items():
    for (attr, intensity, rc), attr_ents in deg_prop_entities.items():
      if type_ents & attr_ents:
        satisfied.add((typ, "has degree property", attr, intensity, rc))
  return satisfied


def _extract_location_name(target):
  """Extract a short name from a location entity for witness naming.

  'https://en.wikipedia.org/wiki/Tallinn' → 'Tallinn'
  'Tallinn 1' → 'Tallinn'
  'house 3' → 'house'
  """
  if target.startswith("http://") or target.startswith("https://"):
    parts = target.rstrip("/").rsplit("/", 1)
    return parts[-1] if len(parts) > 1 else target
  # Strip trailing digits
  import re
  m = re.match(r'^(.*\S)\s+\d+$', target)
  return m.group(1) if m else target


def build_population_facts(classes, has_props, deg_props,
                           compound_witnesses=None,
                           concrete_intersections=None,
                           needed_neg=None):
  """Build the list of @logic population entries from collected scan data.

  For each key, emits a positive and/or negative synthetic clause, skipping
  whichever polarity is already covered by an existing ground constant.
  Every entry carries @sourcetype:"populate".

  concrete_intersections: optional set of (TYPE, PRED, ATTR, INT, RC) keys
  that are already satisfied by a real ground entity in the input. Adjective
  intersection witnesses for these keys are suppressed as redundant.

  needed_neg: optional triple (cls_set, prop_set, degprop_set) identifying
  the classes / properties whose `$some_not_*` witness may participate in
  a proof.  When given, negative witnesses for any key NOT in the
  corresponding set are suppressed (positive witnesses are unaffected).
  When None, all negative witnesses are emitted (legacy behaviour).
  """
  if concrete_intersections is None:
    concrete_intersections = set()
  if needed_neg is None:
    neg_cls = neg_prop = neg_deg = None      # None means "no filter"
  else:
    neg_cls, neg_prop, neg_deg = needed_neg
  result = []

  for cls, info in classes.items():
    name = info["name"]
    cn   = _norm_for_const(cls)
    if not info["has_pos"]:
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["isa", cls, "$some_" + cn]})
    if not info["has_neg"] and (neg_cls is None or cls in neg_cls):
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["-isa", cls, "$some_not_" + cn]})

  for prop, info in has_props.items():
    name = info["name"]
    cn   = _norm_for_const(prop)
    if not info["has_pos"]:
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["has property", prop, "$some_" + cn]})
    if not info["has_neg"] and (neg_prop is None or prop in neg_prop):
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["-has property", prop, "$some_not_" + cn]})

  for (prop, relclass), info in deg_props.items():
    name = info["name"]
    # Degenerate degree (relclass=="none") reduces to has_property semantically;
    # name the witness $some_<prop> (no relclass suffix) and skip the companion
    # isa, since "none" is a sentinel string, not a class.
    is_degenerate = (relclass == "none")
    if is_degenerate:
      cn = _norm_for_const(prop)
    else:
      cn = _norm_for_const(prop) + "_" + _norm_for_const(relclass)
    if not info["has_pos"]:
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["has degree property", prop, "$some_" + cn,
                                "none", relclass]})
      if not is_degenerate:
        # Companion isa: $some_PROP_CLASS is by construction a member of CLASS.
        result.append({"@name": name, "@sourcetype": "populate",
                       "@logic": ["isa", relclass, "$some_" + cn]})
    if not info["has_neg"] and (neg_deg is None or (prop, relclass) in neg_deg):
      result.append({"@name": name, "@sourcetype": "populate",
                     "@logic": ["-has degree property", prop, "$some_not_" + cn,
                                "none", relclass]})

  # Compound witnesses: type + spatial relation OR type + adjective on same variable
  if compound_witnesses:
    for key, info in compound_witnesses.items():
      kind = info.get("kind", "spatial")  # back-compat: missing kind = spatial
      name = info["name"]
      typ = info["type"]
      pred = info["pred"]

      if kind == "spatial":
        prep = info["prep"]
        target = info["target"]
        extra = info["extra"]
        loc_name = _extract_location_name(target)
        const = "$some_" + _norm_for_const(typ) + "_" + _norm_for_const(prep) + "_" + loc_name
        # isa fact
        result.append({"@name": name, "@sourcetype": "populate",
                       "@logic": ["isa", typ, const]})
        # spatial relation fact
        rel_atom = [pred, prep, const, target]
        if pred == "has degree rel2" and extra:
          rel_atom.extend(extra)
        result.append({"@name": name, "@sourcetype": "populate",
                       "@logic": rel_atom})

      elif kind == "adjective":
        attr = info["attr"]
        intensity = info["intensity"]
        relclass = info["relclass"]
        # Skip if a real ground entity already satisfies both atoms.
        intersect_key = (typ, pred, attr, intensity, relclass)
        if intersect_key in concrete_intersections:
          continue
        const = "$some_" + _norm_for_const(attr) + "_" + _norm_for_const(typ)
        # isa fact: the witness is a TYPE
        result.append({"@name": name, "@sourcetype": "populate",
                       "@logic": ["isa", typ, const]})
        # property fact: the witness has the attribute (3-arg has_property
        # for degenerate degree, 5-arg has_degree_property otherwise; Ctxt is
        # injected downstream by lc_ctxt for context-bearing predicates).
        if pred == "has degree property" and (intensity != "none" or relclass != "none"):
          result.append({"@name": name, "@sourcetype": "populate",
                         "@logic": [pred, attr, const, intensity, relclass]})
        else:
          # Degenerate has_degree_property (none/none) reduces to has_property,
          # matching the lc_rewrites canonical form used downstream.
          result.append({"@name": name, "@sourcetype": "populate",
                         "@logic": ["has property", attr, const]})

  return result


# =========== the end ==========
