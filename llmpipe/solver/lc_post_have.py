# Possessive-have inference and have<->has_part bridges, split out of
# lc_post_normalize.py.  Pure clause-list passes; re-exported from there.
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
#-----------------------------------------------------------------

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


