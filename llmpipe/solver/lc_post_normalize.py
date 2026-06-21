# Normalising / repair passes for the post-clausification clause list.
#
# All passes here mutate the clause list in place (or return None / a
# modified copy) without producing new axiom clauses.  Their job is to
# fix Stage-2 LLM errors and standardise predicate forms so downstream
# consumers (clausify, prover) see consistent shapes.
#
# Sections:
#   - GRADABLE_PROPS whitelist
#   - populate_clauses           (extract population facts from raw stage-2)
#   - scan_compound_types,
#     build_compound_subsumption (compound noun → head subsumption rules)
#   - coerce_relclass            (RELCLASS mismatch repair)
#   - normalize_gradable_predicates  (has_property ↔ has_degree_property)
#   - strip_isa_entity           (tautology removal)
#   - add_possessive_have        (is_rel2 "X of" + isa → have)
#   - add_haspart_for_typed_have (case-207 has_part bridge)
#   - strip_degree_predicates    (-simpleproperties mode)
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

import os as _os

from lc_ctxt import fresh_fv as _fresh_fv
from lc_questions import (
  scan_item_formula,
  build_population_facts,
  is_ground_term,
)
import globals as _g
_g_options = _g.options

# Lazy import to avoid circular dependency (lc_packages imports this module
# transitively via logconvert).
def _getextract_package_ctx():
  from lc_packages import extract_package_ctx
  return extract_package_ctx

# ======== gradable property whitelist ========

def load_gradable_props():
  """Load solver/gradables.txt into a frozenset of lowercase property names."""
  try:
    path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "gradables.txt")
    with open(path) as f:
      return frozenset(line.strip().lower() for line in f if line.strip())
  except Exception:
    return frozenset()

GRADABLE_PROPS = load_gradable_props()
# ======== population fact scanning ========

def populate_clauses(items):
  """Scan all @id items in the raw stage-2 input and return population entries.

  This is the main entry point called from rawlogic_convert.  The underlying
  scanner (scan_item_formula) handles both raw stage-2 and clausified forms,
  so this function can also be applied to a clausified clause list.
  """
  classes   = {}   # CLASS -> {"name", "has_pos", "has_neg"}
  has_props = {}   # PROPERTY -> {"name", "has_pos", "has_neg"}
  deg_props = {}   # (PROPERTY, RELCLASS) -> {"name", "has_pos", "has_neg"}
  compound_witnesses = {}  # (type, pred, prep, target) -> info dict

  for item in items:
    if not isinstance(item, list) or len(item) < 3 or item[0] != "@id":
      continue
    name    = "sent_" + str(item[1])
    package = item[2]
    _is_q, formula, _conf, _, _, _, _ = _getextract_package_ctx()(package)
    if _is_q:
      continue   # never populate from the question sentence — circular by construction
    if formula is not None:
      scan_item_formula(formula, name, True, classes, has_props, deg_props,
                        compound_witnesses=compound_witnesses)

  # Track concrete intersections (entity X with both isa(TYPE,X) and adj atom)
  # so we can suppress redundant adjective-intersection witnesses.
  from lc_questions import collect_concrete_intersections
  concrete_intersections = collect_concrete_intersections(items)

  # Decide which negative witnesses ($some_not_X) are actually consumable.
  needed_neg = _collect_negative_witness_needs(items)

  return build_population_facts(classes, has_props, deg_props,
                                compound_witnesses=compound_witnesses,
                                concrete_intersections=concrete_intersections,
                                needed_neg=needed_neg)


def _collect_negative_witness_needs(items):
  """Return (cls_needed, prop_needed, degprop_needed) sets identifying the
  classes / properties whose synthetic negative witness ($some_not_*) might
  participate in a proof.

  Rule (i): the literal `-isa(CLASS, V)` (with V a variable) appears at
            negative polarity inside a question body.  Equivalently, a
            positive `isa(CLASS, V)` literal would end up negated in the
            CNF goal — the witness can then unify with it.
  Rule (ii): a positive `isa(CLASS, V)` literal (with V a variable) appears
             ANYWHERE in a non-question package.  This is over-inclusive on
             purpose (it ignores polarity inside the package): the cost is
             at most one dead clause per class that occurs in some rule.

  The same logic applies to `has property(PROP, V)` and
  `has degree property(PROP, V, _, RELCLASS)` — the latter is keyed by the
  (prop, relclass) pair to match `build_population_facts`.
  """
  cls_needed = set()
  prop_needed = set()
  degprop_needed = set()
  extract = _getextract_package_ctx()

  for item in items:
    if not (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      continue
    is_q, formula, _, _, _, _, _ = extract(item[2])
    if formula is None:
      continue
    if is_q:
      _walk_question_for_neg(formula, +1, cls_needed, prop_needed, degprop_needed)
    else:
      _walk_assertion_for_pos(formula, cls_needed, prop_needed, degprop_needed)

  return (cls_needed, prop_needed, degprop_needed)


_NEG_OPS = frozenset({"not", "-", "~"})


def _walk_question_for_neg(frm, polarity, cls, prop, deg):
  """Walk question body tracking polarity; collect classes/props whose
  predicate appears at NEGATIVE polarity with a variable second arg."""
  from lc_clausify import looks_like_var
  if not isinstance(frm, list) or not frm:
    return
  op = frm[0]
  if not isinstance(op, str):
    return
  if op in _NEG_OPS and len(frm) == 2:
    _walk_question_for_neg(frm[1], -polarity, cls, prop, deg)
    return
  if op == "implies" and len(frm) == 3:
    _walk_question_for_neg(frm[1], -polarity, cls, prop, deg)
    _walk_question_for_neg(frm[2],  polarity, cls, prop, deg)
    return
  if op in ("forall", "exists") and len(frm) >= 3:
    _walk_question_for_neg(frm[-1], polarity, cls, prop, deg)
    return
  if op in ("and", "or", "normally", "ask", "question", "holds"):
    for a in frm[1:]:
      _walk_question_for_neg(a, polarity, cls, prop, deg)
    return
  if op == "isa" and len(frm) >= 3 and polarity < 0 and looks_like_var(frm[2]):
    cls.add(frm[1])
  elif op == "-isa" and len(frm) >= 3 and polarity > 0 and looks_like_var(frm[2]):
    cls.add(frm[1])
  elif op == "has property" and len(frm) >= 3 and polarity < 0 and looks_like_var(frm[2]):
    prop.add(frm[1])
  elif op == "-has property" and len(frm) >= 3 and polarity > 0 and looks_like_var(frm[2]):
    prop.add(frm[1])
  elif op == "has degree property" and len(frm) >= 5 and polarity < 0 and looks_like_var(frm[2]):
    deg.add((frm[1], frm[4]))
  elif op == "-has degree property" and len(frm) >= 5 and polarity > 0 and looks_like_var(frm[2]):
    deg.add((frm[1], frm[4]))


def _walk_assertion_for_pos(frm, cls, prop, deg):
  """Walk an assertion body without polarity tracking; collect every
  positive `isa(C,V)` / `has property(P,V)` / `has degree property(P,V,_,R)`
  literal where V is a variable.  Over-inclusive on purpose — extra
  witnesses are safer than missing ones."""
  from lc_clausify import looks_like_var
  if not isinstance(frm, list) or not frm:
    return
  op = frm[0]
  if not isinstance(op, str):
    return
  if op in ("and", "or", "not", "implies", "normally",
            "ask", "question", "holds"):
    for a in frm[1:]:
      _walk_assertion_for_pos(a, cls, prop, deg)
    return
  if op in ("forall", "exists") and len(frm) >= 3:
    _walk_assertion_for_pos(frm[-1], cls, prop, deg)
    return
  if op == "isa" and len(frm) >= 3 and looks_like_var(frm[2]):
    cls.add(frm[1])
  elif op == "has property" and len(frm) >= 3 and looks_like_var(frm[2]) \
       and isinstance(frm[1], str):
    prop.add(frm[1])                      # structured props ([$has_part,C]) skip: not population-relevant
  elif op == "has degree property" and len(frm) >= 5 and looks_like_var(frm[2]):
    deg.add((frm[1], frm[4]))

# ======== compound type rules ========

def _walk_clause_dicts(extra_clauses, walk):
  """Apply walk() to the @logic / @question body of each clause-dict in
  extra_clauses (e.g. Stage-1 entity-category clauses, which are not @id
  items)."""
  for obj in extra_clauses or ():
    if not isinstance(obj, dict):
      continue
    for key in ("@logic", "@question"):
      body = obj.get(key)
      if isinstance(body, list):
        walk(body)


def scan_compound_types(items, extra_clauses=()):
  """Scan all @id items (and any extra clause-dicts) for isa / -isa atoms with
  space-containing type names.

  Returns a set of compound type strings (e.g. {"baby bird"}).
  """
  compounds = set()

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    op = frm[0]
    if isinstance(op, str) and op in ("isa", "-isa") and len(frm) >= 3:
      typename = frm[1]
      if isinstance(typename, str) and " " in typename:
        compounds.add(typename)
    for el in frm[1:]:
      if isinstance(el, list):
        _walk(el)

  for item in items:
    if not isinstance(item, list) or len(item) < 3 or item[0] != "@id":
      continue
    _walk(item[2])
  _walk_clause_dicts(extra_clauses, _walk)

  return compounds


def scan_all_isa_types(items, extra_clauses=()):
  """Scan all @id items (and any extra clause-dicts) for every isa / -isa class
  name (any word count), including question packages.  Returns a set of class
  strings."""
  classes = set()

  def _walk(frm):
    if not isinstance(frm, list) or not frm:
      return
    op = frm[0]
    if (isinstance(op, str) and op in ("isa", "-isa") and len(frm) >= 3
        and isinstance(frm[1], str)):
      classes.add(frm[1])
    for el in frm[1:]:
      if isinstance(el, list):
        _walk(el)

  for item in items:
    if not isinstance(item, list) or len(item) < 3 or item[0] != "@id":
      continue
    _walk(item[2])
  _walk_clause_dicts(extra_clauses, _walk)
  return classes


def build_compound_subsumption(items, ultra=False, extra_clauses=(), degree_comp=False):
  """Build subsumption and composition rules for compound type names.

  For each compound type like "baby bird", emits:
    Rule 1 (subsumption, strict):
      [-isa, "baby bird", "?:X"], ["isa", "bird", "?:X"]
    Rule 2 (composition, confidence 0.95, no blocker):
      [-isa, "baby", "?:X"], [-isa, "bird", "?:X"], ["isa", "baby bird", "?:X"]

  Under -ultracoarse, Rule 1 subsumes not only to the bare head but to every
  attested intermediate word-suffix, so "American professional basketball
  player" -> "professional basketball player" (not just -> "player").  The
  intermediate target must be an isa class actually present in the problem
  (attestation, case-insensitive); an unattested suffix would only ever produce
  a dead clause.  See FOLIO cases 191/192.

  extra_clauses (clause-dicts, e.g. Stage-1 entity-category isa facts) are
  scanned too, so a compound type that only appears as an entity category
  ("harding pegmatite mine" from entity_S*) still gets its head subsumption
  (-> "mine").  See case 112.
  """
  compounds = scan_compound_types(items, extra_clauses)
  all_lower = ({c.lower() for c in scan_all_isa_types(items, extra_clauses)}
               if ultra else set())
  result = []
  for ctype in sorted(compounds):
    parts = ctype.split()
    head = parts[-1]
    modifier = " ".join(parts[:-1])
    # Rule 1: subsumption (strict) — baby bird -> bird; under -ultracoarse also
    # -> every attested intermediate suffix.
    targets = [head]
    if ultra:
      for k in range(1, len(parts) - 1):       # drop k leading modifier words
        suffix = " ".join(parts[k:])
        if suffix.lower() in all_lower:
          targets.append(suffix)
    for tgt in dict.fromkeys(targets):
      result.append({
        "@name": "compound_sub",
        "@logic": [["-isa", ctype, "?:X"], ["isa", tgt, "?:X"]]
      })
    # Rule 2: composition (semi-strict) — baby + bird -> baby bird
    result.append({
      "@name": "compound_comp",
      "@logic": [
        ["-isa", modifier, "?:X"],
        ["-isa", head, "?:X"],
        ["isa", ctype, "?:X"]
      ],
      "@confidence": 0.95
    })
    # (slightcoarse) Rule 2 in property shape: Stage-2 (isolated -s2split
    # sentences most of all) renders the modifier as a degree/simple property of X, not as an isa
    # ("John is a small fish?" -> isa(fish,X) ∧ has_degree_property(small,X)),
    # so the isa-shaped composition above never matches.  Emit the same
    # composition with the modifier as a property; single-word modifiers only.
    if degree_comp and " " not in modifier:
      result.append({
        "@name": "compound_comp",
        "@logic": [
          ["-has degree property", modifier, "?:X", "?:Dg", "?:Rc", "?:Ct"],
          ["-isa", head, "?:X"],
          ["isa", ctype, "?:X"]
        ],
        "@confidence": 0.95
      })
      result.append({
        "@name": "compound_comp",
        "@logic": [
          ["-has property", modifier, "?:X", "?:Ct"],
          ["-isa", head, "?:X"],
          ["isa", ctype, "?:X"]
        ],
        "@confidence": 0.95
      })
  return result

# ======== RELCLASS coercion ========

# Maps predicate name -> (entity_arg_index, relclass_arg_index).
# Used to identify which argument is the entity (for class lookup) and which
# is the RELCLASS (to be replaced when it doesn't match the entity's known class).
_degree_preds_relclass = {
  "has degree property": (2, 4),   # [pred, PROP, ENTITY, DEGREE, RELCLASS]
  "has degree rel2":     (2, 5),   # [pred, REL, E1, E2, DEGREE, RELCLASS] — RELCLASS describes E1
}


def coerce_relclass(result):
  """Fix RELCLASS mismatches in question degree-predicate atoms.

  Builds two maps from assertional @logic clauses:
    const_classes:   CONST -> {CLASS, ...}  (from isa(CLASS,CONST) facts)
    prop_relclasses: PROP  -> {RELCLASS, ...} (from has degree property assertions)

  For every has degree property atom in @question or @sourcetype:question entries:
    If relclass ∈ entity's known isa classes (spurious entity-category assignment)
    AND relclass does NOT appear as a relclass in any assertional clause for the
    same property (no matching rule exists) → replace with a fresh free variable
    so the question can unify with whichever rule actually applies.

  This fixes the case where stage-1 uses the entity's ontological category
  (e.g. "person") as relclass in a query, while the only relevant rule uses a
  different relclass (e.g. "bear").  Intentional relclasses from explicit nouns
  in the question ("Is John a big mouse?" → "mouse") are preserved because they
  don't match any of John's isa classes.

  Also retains the existing assertional mismatch-coercion (non-question path)
  and the has degree rel2 free-variable substitution in questions.

  Modifies result in place.
  """
  # --- 1. build lookup maps from assertional @logic entries ---
  const_classes   = {}   # CONST -> set of CLASS strings  (from isa facts)
  prop_relclasses = {}   # PROP  -> set of RELCLASS strings (from has degree property)

  for obj in result:
    if not isinstance(obj, dict):
      continue
    src = obj.get("@sourcetype")
    # Skip question / question_bridge / populate entries: question_bridge
    # clauses are mechanically derived from the question's stative literals
    # (lc_ctxt.build_question_tense_bridges), so their relclass values are
    # copies of the question's. Letting them populate prop_relclasses would
    # circularly tell coerce_relclass that the question's own relclass is
    # evidence-supported and suppress coercion.
    if src in ("question", "question_bridge", "populate"):
      continue
    if "@logic" not in obj:
      continue
    clause = obj["@logic"]
    # Normalise to a list of atoms (handle both single-atom and disjunctive clauses).
    atoms = clause if (isinstance(clause, list) and clause and
                       isinstance(clause[0], list)) else [clause]
    for atom in atoms:
      if not isinstance(atom, list) or not atom or not isinstance(atom[0], str):
        continue
      pred = atom[0]
      # Strip leading "-" so rule-body negated literals also contribute.
      base_pred = pred[1:] if pred.startswith("-") else pred
      # isa(CLASS, CONST) — build const_classes (positive only)
      if pred == "isa" and len(atom) >= 3 and is_ground_term(atom[2]):
        const_classes.setdefault(atom[2], set()).add(str(atom[1]))
      # has degree property [pred, PROP, ENTITY, DEGREE, RELCLASS, ...]
      # Collect concrete (non-variable) relclass strings from both positive
      # (ground fact) and negative (rule body) occurrences.
      elif base_pred == "has degree property" and len(atom) >= 5:
        rc = atom[4]
        if isinstance(rc, str) and not rc.startswith("?"):
          prop_relclasses.setdefault(str(atom[1]), set()).add(rc)

  if not const_classes:
    return

  # --- 2. apply coercion to question entries ---
  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@question" in obj:
      obj["@question"] = _coerce_atom(obj["@question"], const_classes,
                                      prop_relclasses=prop_relclasses,
                                      is_question=True)
    if "@logic" in obj and obj.get("@sourcetype") == "question":
      obj["@logic"] = _coerce_clause(obj["@logic"], const_classes,
                                     prop_relclasses=prop_relclasses,
                                     is_question=True)

  # --- 3. apply assertion-side coercion for multi-class entities ---
  # When a ground entity has isa classes that differ from an assertion's
  # RELCLASS slot (e.g. John is isa "bear" but the fact says "nice for an
  # animal"), Stage-1 has leaked a generic category into the relclass.
  # Coerce such assertion-side relclasses to a free variable so rules using
  # the entity's actual class (or another cross-used relclass) can unify.
  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" not in obj:
      continue
    if obj.get("@sourcetype") in ("question", "populate"):
      continue
    obj["@logic"] = _coerce_clause(obj["@logic"], const_classes,
                                   prop_relclasses=prop_relclasses,
                                   is_question=False,
                                   assertion_multi_class=True)


def _coerce_atom(atom, const_classes, prop_relclasses=None, is_question=False,
                 assertion_multi_class=False):
  """Recursively substitute RELCLASS in degree-predicate atoms.

  Handles both raw question formulas (with connectives and quantifiers)
  and flat GK clause atoms.

  For "has degree rel2" in questions: always use a fresh free variable.

  For "has degree property" in questions: use a fresh free variable when
    - relclass is one of the entity's known isa classes (stage-1 spuriously
      used the entity's ontological category), AND
    - that relclass does not appear as a relclass in any assertional clause
      for the same property (no matching rule exists to unify against).
  This preserves intentional relclasses from explicit comparison nouns
  ("Is John a big mouse?" keeps "mouse" when no mouse-bigness rule exists but
  "mouse" is not one of John's isa classes).

  For non-question assertional atoms (default): replace relclass when it
  mismatches the entity's single known isa class (original behaviour).

  For non-question assertional atoms with assertion_multi_class=True:
  replace relclass with a free variable when the entity has multiple
  known classes, the current relclass is one of them, and another of the
  entity's classes appears as a relclass for the same property elsewhere
  (evidence of a rule/fact relclass split, e.g. "John is big (for an
  animal)" vs rule "for a bear").
  """
  if not isinstance(atom, list) or not atom:
    return atom
  pred = atom[0]
  if not isinstance(pred, str):
    return atom

  # Degree predicate (possibly with a leading "-" negation prefix).
  base = pred[1:] if pred.startswith("-") else pred
  if base in _degree_preds_relclass:
    entity_idx, relclass_idx = _degree_preds_relclass[base]
    if len(atom) > relclass_idx:
      entity   = atom[entity_idx]   if len(atom) > entity_idx   else None
      relclass = atom[relclass_idx]
      if is_question:
        # "has degree rel2": always free variable.
        if base == "has degree rel2" and isinstance(relclass, str):
          new_atom = list(atom)
          new_atom[relclass_idx] = _fresh_fv()
          return new_atom
        # "has degree property": replace the relclass with a free variable
        # when stage-1 put a spurious entity-category in the relclass slot.
        if (base == "has degree property" and
            isinstance(relclass, str) and not relclass.startswith("?") and
            entity and is_ground_term(entity) and
            entity in const_classes):
          prop = atom[1] if len(atom) > 1 else ""
          prop_existing  = (prop_relclasses or {}).get(str(prop), set())
          entity_classes = const_classes[entity]
          # case_a: relclass IS a known class of the entity but no rule uses it
          #   as a relclass for this property (spurious category, no match).
          case_a = (relclass in entity_classes and relclass not in prop_existing)
          # case_b: relclass is NOT a known class of the entity, but one of the
          #   entity's actual classes IS used as a relclass for this property by
          #   a rule -- the question used a super/sibling category (e.g.
          #   "animal" while the rule's consequent uses "bear"; case 1418).
          case_b = (relclass not in entity_classes and
                    any(c in prop_existing for c in entity_classes))
          if case_a or case_b:
            new_atom = list(atom)
            new_atom[relclass_idx] = _fresh_fv()
            return new_atom
      elif assertion_multi_class:
        # Assertion-side RELCLASS coercion. Fires in two situations:
        # (a) Entity has multiple isa classes and the relclass is one of them,
        #     while another of the entity's classes is used as a relclass
        #     elsewhere (evidence of a split between generic vs specific class).
        # (b) The relclass is NOT one of the entity's isa classes but a rule
        #     elsewhere uses a relclass that IS one of the entity's classes
        #     (the stage-1 generic category leaked into the relclass slot
        #     even though no matching isa fact was emitted).
        # In either case, replace with a fresh free variable so the rule's
        # relclass can unify.
        if (base == "has degree property" and
            entity and is_ground_term(entity) and
            entity in const_classes and
            isinstance(relclass, str) and not relclass.startswith("?")):
          prop = atom[1] if len(atom) > 1 else ""
          existing = (prop_relclasses or {}).get(str(prop), set())
          entity_classes = const_classes[entity]
          case_a = (relclass in entity_classes and len(entity_classes) > 1 and
                    any(c in existing for c in entity_classes - {relclass}))
          case_b = (relclass not in entity_classes and
                    any(c in existing for c in entity_classes))
          if case_a or case_b:
            new_atom = list(atom)
            new_atom[relclass_idx] = _fresh_fv()
            return new_atom
      else:
        # Assertional (non-question): replace relclass when it mismatches the
        # entity's single known isa class.
        if (entity and is_ground_term(entity) and
            entity in const_classes and
            isinstance(relclass, str) and
            relclass not in const_classes[entity]):
          known = const_classes[entity]
          if len(known) == 1:
            new_atom = list(atom)
            new_atom[relclass_idx] = next(iter(known))
            return new_atom
    return atom

  # Logical connectives / quantifiers: recurse.
  if pred in ("and", "or", "not"):
    return [pred] + [_coerce_atom(el, const_classes, prop_relclasses,
                                  is_question, assertion_multi_class)
                     for el in atom[1:]]
  if pred in ("forall", "exists") and len(atom) >= 3:
    return [pred, atom[1], _coerce_atom(atom[2], const_classes, prop_relclasses,
                                        is_question, assertion_multi_class)]

  return atom


def _coerce_clause(clause, const_classes, prop_relclasses=None, is_question=False,
                   assertion_multi_class=False):
  """Apply _coerce_atom to a GK clause (single atom or disjunction)."""
  if not isinstance(clause, list) or not clause:
    return clause
  # Disjunction: first element is itself a list of atoms.
  if isinstance(clause[0], list):
    return [_coerce_atom(atom, const_classes, prop_relclasses, is_question,
                         assertion_multi_class)
            for atom in clause]
  # Single atom.
  return _coerce_atom(clause, const_classes, prop_relclasses, is_question,
                      assertion_multi_class)


# ======== gradable predicate normalization ========

def normalize_gradable_predicates(result):
  """Normalize has property / has degree property atoms based on GRADABLE_PROPS.

  For every atom in @logic and @question entries:
    - "has degree property" where PROP not in whitelist
        → "has property" (DEGREE and RELCLASS dropped; $ctxt preserved)
    - "has property" where PROP is in whitelist
        → "has degree property" with DEGREE="none", RELCLASS=fresh_var ($ctxt preserved)
    - "has degree property" where PROP is in whitelist and RELCLASS == "entity"
        → RELCLASS replaced with a fresh free variable ("entity" is universal
          and blocks unification against specific-class annotations like "person")

  This ensures consistent predicate names across rules, facts, and queries
  regardless of whether Stage 1/Stage 2 emitted adjectives annotations.
  Modifies result in place.
  """
  if not GRADABLE_PROPS:
    return result
  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      obj["@logic"] = _norm_grad_frm(obj["@logic"])
    if "@question" in obj:
      obj["@question"] = _norm_grad_frm(obj["@question"])
  return result


def _norm_grad_frm(frm):
  """Recursively normalize one formula or GK clause for gradable predicates."""
  if not isinstance(frm, list) or not frm:
    return frm

  first = frm[0]

  # GK disjunctive clause: first element is itself a list — recurse into each atom.
  if isinstance(first, list):
    return [_norm_grad_frm(a) for a in frm]

  if not isinstance(first, str):
    return frm

  pred = first
  neg  = pred.startswith("-")
  base = pred[1:] if neg else pred
  pfx  = "-" if neg else ""

  if base == "has degree property" and len(frm) >= 5:
    # ["has degree property", PROP, ENTITY, DEGREE, RELCLASS, optional_$ctxt]
    prop = frm[1]
    if isinstance(prop, str) and prop.lower() not in GRADABLE_PROPS:
      # Strip to has property; preserve $ctxt at position 5 if present.
      new_atom = [pfx + "has property", frm[1], frm[2]]
      if len(frm) >= 6:
        new_atom.append(frm[5])
      return new_atom
    # Keep as degree property; replace "entity"/"none" relclass with a free variable
    # since both mean "no specific comparison class" and carry no useful constraint.
    relclass = frm[4]
    if relclass in ("entity", "none"):
      new_atom = [frm[0], frm[1], frm[2], frm[3], _fresh_fv()]
      if len(frm) >= 6:
        new_atom.append(frm[5])
      return new_atom

  elif base == "has property" and len(frm) >= 3:
    # ["has property", PROP, ENTITY, optional_$ctxt]
    prop = frm[1]
    if isinstance(prop, str) and prop.lower() in GRADABLE_PROPS:
      # Upgrade to has degree property; use a free variable for relclass
      # (avoids spurious "entity" constant that can block unification).
      new_atom = [pfx + "has degree property", frm[1], frm[2], "none", _fresh_fv()]
      if len(frm) >= 4:
        new_atom.append(frm[3])
      return new_atom

  elif base == "has degree rel2" and len(frm) >= 6:
    # ["has degree rel2", REL, E1, E2, DEGREE, RELCLASS, optional_$ctxt]
    rel = frm[1]
    if isinstance(rel, str) and rel.lower() not in GRADABLE_PROPS:
      # Non-gradable relation: strip to is rel2; preserve $ctxt if present.
      new_atom = [pfx + "is rel2", frm[1], frm[2], frm[3]]
      if len(frm) >= 7:
        new_atom.append(frm[6])
      return new_atom
    # Gradable: replace "entity"/"none" relclass with a free variable.
    relclass = frm[5]
    if relclass in ("entity", "none"):
      new_atom = [frm[0], frm[1], frm[2], frm[3], frm[4], _fresh_fv()]
      if len(frm) >= 7:
        new_atom.append(frm[6])
      return new_atom

  elif base == "is rel2" and len(frm) >= 4:
    # ["is rel2", REL, E1, E2, optional_$ctxt]
    rel = frm[1]
    if isinstance(rel, str) and rel.lower() in GRADABLE_PROPS:
      # Gradable relation: upgrade to has degree rel2 with free relclass.
      new_atom = [pfx + "has degree rel2", frm[1], frm[2], frm[3], "none", _fresh_fv()]
      if len(frm) >= 5:
        new_atom.append(frm[4])
      return new_atom

  # Logical connectives / quantifiers: recurse into sub-formulas.
  return [frm[0]] + [_norm_grad_frm(a) if isinstance(a, list) else a
                     for a in frm[1:]]

# ======== isa-entity stripping ========

def strip_isa_entity(result):
  """Remove all isa/entity literals from the clause list.

  Since "entity" is the universal base type (everything is an entity), the
  literal ["isa","entity",X] is always true and ["-isa","entity",X] is always
  false.  Keeping them causes spurious unification failures when a rule that
  uses a generic variable (annotated as entity) tries to match a concrete fact.

  Rules:
    - Any clause containing a POSITIVE ["isa","entity",X] literal is a
      tautology → remove the entire clause dict.
    - Any ["-isa","entity",X] literal is always false → remove just the
      literal from its clause.  If the clause becomes empty after removal,
      remove the entire clause dict.

  Only @logic dicts are touched; @question dicts are left unchanged.
  Modifies result in place and returns it.
  """
  def _is_pos_isa_entity(lit):
    return (isinstance(lit, list) and len(lit) >= 3
            and lit[0] == "isa" and lit[1] == "entity")

  def _is_neg_isa_entity(lit):
    return (isinstance(lit, list) and len(lit) >= 3
            and lit[0] == "-isa" and lit[1] == "entity")

  keep = []
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      keep.append(obj)
      continue
    clause = obj["@logic"]
    # Unit atom (single literal, not a list-of-lists).
    if clause and not isinstance(clause[0], list):
      if _is_pos_isa_entity(clause) or _is_neg_isa_entity(clause):
        continue          # drop entire clause dict
      keep.append(obj)
      continue
    # Disjunctive clause (list of literal lists).
    if any(_is_pos_isa_entity(lit) for lit in clause):
      continue            # tautology → drop entire clause dict
    filtered = [lit for lit in clause if not _is_neg_isa_entity(lit)]
    if not filtered:
      continue            # empty clause after removal → drop
    obj["@logic"] = filtered
    keep.append(obj)
  result[:] = keep
  return result


# ======== possessive have inference ========

_ACTIVITY_ROLE_PREDS = frozenset({
  "has target", "has actor", "has instrument", "has direction", "has location",
  "has destination", "has recipient", "has source",
  "has beneficiary", "has accompaniment", "has path", "has result",
  "has topic", "has cause",
})

def add_possessive_have(result):
  """Infer have(Y,E,CT) from paired isa(T,E) + is_rel2(T+" of",E,Y,CT) facts.

  "The car of Mary" produces:
    isa("car", car2)
    is_rel2("car of", car2, Mary, CT)
  but "Mary has a car?" checks have(Mary, sk, CT).  This function bridges the
  gap by emitting have(Mary, car2, CT) whenever the isa type T matches the
  relation prefix (T+" of").

  Context (tense, world, location, knower) for the generated have fact:
  - If the possessed entity E appears as the argument of an activity-role fact
    (has_target, has_actor, has_instrument, etc.) we use that fact's CT.
    This handles "John saw a twig of an elephant" correctly: twig2 is the
    has_target of a past see-event, so have(elephant, twig2, CT_past) is
    emitted rather than a spurious present-tense fact.
  - Otherwise fall back to the CT from the is_rel2 fact itself (correct for
    direct possessives like "The bike of John is blue" with no containing event).

  The isa-type check prevents spurious have for non-possessive relations such
  as is_rel2("afraid of", wolf, mice) — there is no isa("afraid", wolf).

  Only ground (non-variable, non-compound-term) entity arguments are processed.
  New facts are inserted before the first @question entry.
  """
  def _is_ground_str(v):
    return isinstance(v, str) and not v.startswith("?:")

  def _is_entity_term(v):
    """True if v is a valid entity: ground string, Skolem function, or $theof1 term."""
    if _is_ground_str(v):
      return True
    if isinstance(v, list) and len(v) >= 2 and isinstance(v[0], str):
      return v[0].startswith("sk") or v[0] == "$theof1"
    return False

  def _entity_key(v):
    """Hashable key for an entity (string or list term)."""
    return str(v) if isinstance(v, list) else v

  def _extract_atoms(clause):
    """Return list of atoms from a clause (single-atom or multi-literal)."""
    if not isinstance(clause, list) or not clause:
      return []
    if isinstance(clause[0], list):
      return clause  # multi-literal: each element is an atom
    if isinstance(clause[0], str):
      return [clause]  # single atom
    return []

  def _extract_guard(clause):
    """Return the guard literals (negative atoms) from a multi-literal clause.
    For single-atom clauses, returns []."""
    if not isinstance(clause, list) or not clause or not isinstance(clause[0], list):
      return []
    return [atom for atom in clause
            if isinstance(atom, list) and atom
            and isinstance(atom[0], str) and atom[0].startswith("-")]

  # Pass 1a: collect isa(T, E) facts for ground and function-term entities.
  # key: _entity_key(E) -> set of type strings
  isa_types = {}
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    for atom in _extract_atoms(obj["@logic"]):
      if (isinstance(atom, list) and len(atom) >= 3
          and isinstance(atom[0], str) and atom[0] == "isa"
          and isinstance(atom[1], str) and _is_entity_term(atom[2])):
        typ, ent = atom[1], atom[2]
        isa_types.setdefault(_entity_key(ent), set()).add(typ)

  # Pass 1b: collect CT of the first activity-role fact mentioning each entity.
  # has_target(act, E, CT) / has_actor(act, E, CT) / has_instrument(act, E, CT) …
  # E is always at argument position 2 (index 2) for these predicates.
  entity_event_ct = {}    # entity_key -> CT from containing activity
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    for atom in _extract_atoms(obj["@logic"]):
      if (isinstance(atom, list) and len(atom) >= 4
          and isinstance(atom[0], str)
          and atom[0] in _ACTIVITY_ROLE_PREDS
          and _is_entity_term(atom[2])):
        ent = atom[2]
        # CT is the last argument if it's a $ctxt list
        ct = None
        if len(atom) > 3:
          last = atom[-1]
          if isinstance(last, list) and last and last[0] == "$ctxt":
            ct = last
        ekey = _entity_key(ent)
        if ekey not in entity_event_ct and ct is not None:
          entity_event_ct[ekey] = ct

  # Pass 2: find is_rel2(R, E, Y, CT_possessive) where R ends in " of" and
  # isa(T, E) exists with T+" of" == R.  Emit have(Y, E, CT_chosen).
  # For rule clauses with guard literals, emit a conditional have with the same guard.
  new_facts = []
  seen = set()
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    # Skip the universal frm_theof schema axioms: their is_rel2 form has a
    # free ?:S owner and would yield a universally-quantified have axiom
    # ("every entity has its own X"), which lets the prover satisfy any
    # wh-query with a free-variable answer (e.g. "X3 and Tom").
    if obj.get("@name") == "frm_theof":
      continue
    clause = obj["@logic"]
    for atom in _extract_atoms(clause):
      if not (isinstance(atom, list) and len(atom) >= 4
              and isinstance(atom[0], str) and atom[0] == "is rel2"):
        continue
      rel, ent, owner = atom[1], atom[2], atom[3]
      ct_possessive = atom[4] if len(atom) > 4 else None
      if not (isinstance(rel, str) and rel.endswith(" of")):
        continue
      if not (_is_entity_term(ent) and (_is_ground_str(owner) or
              (isinstance(owner, str) and owner.startswith("?:")))):
        continue
      expected_type = rel[:-3]    # strip trailing " of"
      ekey = _entity_key(ent)
      if ekey not in isa_types or expected_type not in isa_types[ekey]:
        continue
      # Prefer the activity-event CT (correct tense) over the possessive CT.
      ct = entity_event_ct.get(ekey, ct_possessive)
      have_atom = ["have", owner, ent]
      if ct is not None:
        have_atom.append(list(ct) if isinstance(ct, list) else ct)
      # For rule clauses with guard literals, emit conditional have
      guard = _extract_guard(clause)
      if guard:
        have_clause = guard + [have_atom]
      else:
        have_clause = have_atom
      key = (str(owner), ekey)
      if key in seen:
        continue
      seen.add(key)
      new_facts.append({"@name": obj.get("@name", "sent_?"), "@logic": have_clause})

  if not new_facts:
    return
  first_q = next((i for i, o in enumerate(result) if "@question" in o), len(result))
  for i, fact in enumerate(new_facts):
    result.insert(first_q + i, fact)


# ======== have → has_part bridge for typed body-part nouns ========

def _parse_entity_name_type(entity):
  """Extract a candidate type string from an entity name using Stage-2 naming
  conventions.  Returns None for non-strings or names without a recognisable
  noun stem.

    "trunk 1"      -> "trunk"      (concrete + numeric suffix)
    "sk0_trunk"    -> "trunk"      (Skolem const with type tag)
    "$some_trunk"  -> "trunk"      (population existential)
    "John 1"       -> "John"       (proper name + suffix)

  Used by add_haspart_for_typed_have as a fallback when the explicit
  isa(T, E) atom is missing from Stage-2 output.
  """
  if not isinstance(entity, str):
    return None
  if entity.startswith("$some_"):
    rest = entity[len("$some_"):]
    if rest.startswith("not_"):
      rest = rest[4:]
    return rest.split("_", 1)[0] if rest else None
  if entity.startswith("sk") and "_" in entity:
    return entity.split("_", 1)[1] or None
  parts = entity.split()
  return parts[0] if parts else None


def add_haspart_for_typed_have(result):
  """Bridge specific have-facts to has_part when a rule uses has_part on the
  same noun type.  Conservative: fires only when the problem contains a
  has_part-using rule whose typed premise matches the have-fact's possessee.

  Motivating example (case 207):
    Rule:  "If an animal has a trunk, it is an elephant."
           Stage-2 clause uses has_part:
             [-isa(animal,?:X), -isa(trunk,?:Y), -has_part(?:X,?:Y,Ctxt),
              isa(elephant,?:X), $block, ...]
    Fact:  "John has a long trunk."
           Stage-2 (gemini/gpt) uses have, not has_part:
             have(John 1, trunk 1, Ctxt), isa(trunk, trunk 1)
    Query: "John is an elephant?" → Unknown (rule never fires because
           has_part(John 1, trunk 1, …) is not asserted).

  This bridge scans the rule clauses and finds the type "trunk" is paired
  with has_part.  It then sees have(John 1, trunk 1, …) where trunk 1 has
  isa(trunk, …), matching the rule's expected type, and emits the missing
  has_part(John 1, trunk 1, Ctxt).  The rule then fires → True.

  Conservatism:
  - RULE_HASPART_TYPES is local to the current problem — only types
    explicitly used in a has_part-typed rule premise here qualify.
  - For "John has a book" with no has_part rule about books, nothing fires.
  - For a hypothetical rule about "has_part friend", "John has a friend"
    would correctly fire.

  Name-parsing fallback (_parse_entity_name_type):
  - When the explicit isa(T, Y_const) atom is missing from Stage-2 output,
    parse the entity name (e.g. "trunk 1" → "trunk", "sk0_trunk" → "trunk")
    as a fallback type.  Removes the dependency on LLM reliably emitting
    isa, while remaining safe (still gated by RULE_HASPART_TYPES).
  """
  def _is_var(s):
    return isinstance(s, str) and s.startswith("?:")

  def _is_ground_str(v):
    return isinstance(v, str) and not v.startswith("?:")

  def _is_entity_term(v):
    if _is_ground_str(v):
      return True
    if isinstance(v, list) and len(v) >= 2 and isinstance(v[0], str):
      return v[0].startswith("sk") or v[0] == "$theof1"
    return False

  def _entity_key(v):
    return str(v) if isinstance(v, list) else v

  def _extract_atoms(clause):
    if not isinstance(clause, list) or not clause:
      return []
    if isinstance(clause[0], list):
      return clause
    if isinstance(clause[0], str):
      return [clause]
    return []

  # Pass 1: scan rule clauses for has_part-typed premises.
  # A "has_part-typed rule" is a multi-literal clause containing both
  # ["-has part", ?:X, ?:Y, …] and ["-isa", T, ?:Y] for the same ?:Y.
  rule_haspart_types = set()
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    clause = obj["@logic"]
    if not (isinstance(clause, list) and clause and isinstance(clause[0], list)):
      continue   # not a multi-literal rule
    # collect ?:Y vars that appear as second arg of -has part
    haspart_vars = set()
    for atom in clause:
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "-has part" and _is_var(atom[2])):
        haspart_vars.add(atom[2])
    if not haspart_vars:
      continue
    # for each such ?:Y, find -isa(T, ?:Y) in the same clause
    for atom in clause:
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "-isa"
          and isinstance(atom[1], str)
          and atom[2] in haspart_vars):
        rule_haspart_types.add(atom[1])

  if not rule_haspart_types:
    return   # no has_part-typed rule in this problem; bridge would fire on nothing

  # Pass 2: collect explicit isa(T, E) for ground/function-term entities.
  isa_types = {}
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    for atom in _extract_atoms(obj["@logic"]):
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "isa"
          and isinstance(atom[1], str) and _is_entity_term(atom[2])):
        isa_types.setdefault(_entity_key(atom[2]), set()).add(atom[1])

  # Pass 3: walk single-atom positive have facts and emit has_part where
  # the possessee's type matches a rule's has_part-typed premise.
  new_facts = []
  seen = set()
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    clause = obj["@logic"]
    if not (isinstance(clause, list) and clause and isinstance(clause[0], str)
            and clause[0] == "have" and len(clause) >= 3):
      continue   # not a single-atom positive have fact
    x_const, y_const = clause[1], clause[2]
    if not _is_entity_term(y_const):
      continue
    ekey = _entity_key(y_const)
    types = set(isa_types.get(ekey, ()))
    if not types:
      parsed = _parse_entity_name_type(y_const)
      if parsed:
        types = {parsed}
    if not (types & rule_haspart_types):
      continue
    # Build has_part atom with the same Ctxt (4th arg) if present.
    haspart = ["has part", x_const, y_const]
    if len(clause) > 3:
      haspart.append(clause[3])
    key = (str(x_const), ekey)
    if key in seen:
      continue
    seen.add(key)
    new_facts.append({"@name": obj.get("@name", "sent_?"), "@logic": haspart})

  if not new_facts:
    return
  first_q = next((i for i, o in enumerate(result) if "@question" in o), len(result))
  for i, fact in enumerate(new_facts):
    result.insert(first_q + i, fact)


def inject_have_to_haspart_axioms(result):
  """Bridge axiom: for body-part-typed Y, have(X, Y, Ctxt) -> has_part(X, Y, Ctxt).

  axioms_std.js §2 ships the converse (has_part -> have).  The forward
  direction is needed for case 6: assertion "Elephants do not have wings"
  encodes as -has_part(X, Y, Ctxt); query "Who does not have a wing?"
  encodes as -have(X, Y, Ctxt).  Without a forward bridge the prover
  can't link the two; contrapositive of the new axiom
  (isa(T,Y) ∧ -has_part(X,Y) -> -have(X,Y)) closes the gap.

  Type-gated: emits one axiom per type T that appears as a has_part
  premise (-isa(T, Y) + -has_part(_, Y, _)) in some rule clause — same
  gate as add_haspart_for_typed_have.  Unconditional have == has_part
  would over-generalise ("John has a book" -> book is structural part).

  Defeasible at 0.9 confidence (no $block).  A $block(0, $not(has_part))
  guard would circularly self-block in case 6: the proof needs the
  bridge's positive has_part to combine with the rule body's
  -has_part, but that very -has_part is independently derivable, so
  the block would suppress the bridge before it can fire.  Confidence
  weighting alone (0.9 × rule confidence) is enough to demote the
  bridged conclusion below a directly-asserted contradicting fact.
  """
  def _is_var(s):
    return isinstance(s, str) and s.startswith("?:")

  rule_haspart_types = set()
  for obj in result:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    clause = obj["@logic"]
    if not (isinstance(clause, list) and clause and isinstance(clause[0], list)):
      continue
    haspart_vars = set()
    for atom in clause:
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "-has part" and _is_var(atom[2])):
        haspart_vars.add(atom[2])
    if not haspart_vars:
      continue
    for atom in clause:
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "-isa"
          and isinstance(atom[1], str)
          and atom[2] in haspart_vars):
        rule_haspart_types.add(atom[1])

  if not rule_haspart_types:
    return

  first_q = next((i for i, o in enumerate(result) if "@question" in o), len(result))
  axioms = []
  for t in sorted(rule_haspart_types):
    axioms.append({
      "@name": "sent_haspart_bridge",
      "@logic": [
        ["-isa", t, "?:Y"],
        ["-have", "?:X", "?:Y", "?:Ctxt"],
        ["has part", "?:X", "?:Y", "?:Ctxt"],
      ],
      "@confidence": 0.9,
    })
  for i, ax in enumerate(axioms):
    result.insert(first_q + i, ax)


# ======== degree-predicate stripping (noproptypes_flag) ========

def strip_degree_predicates(result):
  """Replace degree predicates with their non-gradable equivalents throughout
  the result clause list.  Called from rawlogic_convert when noproptypes_flag
  is True.  Modifies each clause dict in place and returns the same list.

    has degree property(PROP, ENTITY, DEGREE, RELCLASS) -> has property(PROP, ENTITY)
    has degree rel2(REL, E1, E2, DEGREE, RELCLASS)      -> is rel2(REL, E1, E2)

  Handles negated forms ("-has degree property", "-has degree rel2") as well,
  and recurses into nested sub-formulas (e.g. inside $block / $not).
  """
  for obj in result:
    if not isinstance(obj, dict):
      continue
    if "@logic" in obj:
      obj["@logic"] = _strip_deg_frm(obj["@logic"])
    if "@question" in obj:
      obj["@question"] = _strip_deg_frm(obj["@question"])
  return result


def _strip_deg_frm(frm):
  """Recursively strip degree info from one formula or GK clause."""
  if not isinstance(frm, list) or not frm:
    return frm

  first = frm[0]

  # GK clause: first element is itself a list (atom) — recurse into each atom.
  if isinstance(first, list):
    return [_strip_deg_frm(a) for a in frm]

  if not isinstance(first, str):
    return frm

  # Atom whose predicate may carry a "-" negation prefix.
  pred = first
  neg  = pred.startswith("-")
  base = pred[1:] if neg else pred
  pfx  = "-" if neg else ""

  if base == "has degree property" and len(frm) >= 3:
    # [pred, PROP, ENTITY, DEGREE, RELCLASS, ctx?] -> [simple_pred, PROP, ENTITY, ctx?]
    result = [pfx + "has property", frm[1], frm[2]]
    # Preserve context argument (last element) if present beyond RELCLASS.
    # Full form: [pred, PROP, ENTITY, DEGREE, RELCLASS, CTXT] — 6 elements.
    if len(frm) >= 6:
      result.append(frm[5])
    return result

  if base == "has degree rel2" and len(frm) >= 4:
    # [pred, REL, E1, E2, DEGREE, RELCLASS, ctx?] -> [simple_pred, REL, E1, E2, ctx?]
    result = [pfx + "is rel2", frm[1], frm[2], frm[3]]
    # Full form: [pred, REL, E1, E2, DEGREE, RELCLASS, CTXT] — 7 elements.
    if len(frm) >= 7:
      result.append(frm[6])
    return result

  # Any other formula/atom: recurse into sub-elements to catch nested occurrences.
  return [frm[0]] + [_strip_deg_frm(a) if isinstance(a, list) else a
                     for a in frm[1:]]

