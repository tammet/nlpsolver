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
#   - strip_degree_predicates    (-simpleprops mode)
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
from lc_questions import is_ground_term

# The population-fact and have-bridge passes live in sibling modules; re-export
# their entry points so the import surface (used by logconvert) is unchanged.
from lc_post_population import populate_clauses
from lc_post_have import (add_possessive_have, add_haspart_for_typed_have,
                          inject_have_to_haspart_axioms)


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

# ======== reflexive locative self-loop drop ========
# Nothing is in / on / above / inside ... itself.  A reflexive locative atom
# is_rel2(R, X, X) for an irreflexive spatial/containment relation R is always a
# subject-collapse parse artifact, and with a "unique location" premise it
# manufactures false entity identities (case 59: in(Montana,Montana) +
# "a city is in only one state" ⇒ US=Montana).  Drop such unit assertions.
_IRREFLEXIVE_LOC_RELS = frozenset({
    "in", "inside", "within", "on", "outside", "contains", "part of",
    "above", "below", "over", "under", "located in", "located on",
    "in_front_of", "behind", "left_of", "right_of",
})

def drop_reflexive_locatives(result):
  """Return a new clause list with unit clauses asserting a reflexive locative
  self-loop is_rel2(R,X,X) (R irreflexive, X a constant) removed."""
  out = []
  for c in result:
    lg = c.get("@logic") if isinstance(c, dict) else None
    if (isinstance(lg, list) and len(lg) >= 4 and lg[0] == "is rel2"
        and isinstance(lg[1], str) and lg[1] in _IRREFLEXIVE_LOC_RELS
        and isinstance(lg[2], str) and lg[2] == lg[3]):
      continue
    out.append(c)
  return out

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

  Under -typeenrich, Rule 1 subsumes not only to the bare head but to every
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
    # Rule 1: subsumption (strict) — baby bird -> bird; under -typeenrich also
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
    # (-s2split repair) Rule 2 in property shape: Stage-2 (isolated -s2split
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

