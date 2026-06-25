# Entity-category / typeenrich isa enrichment and typeonly-skolem merge,
# split out of logconvert.py.  build_entity_category_clauses adds isa/
# subsumption atoms (supertypes, gender, name-as-type, ...); merge_typeonly_
# skolems re-corefs per-sentence generic skolems under the abstraction encodings.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

import re
import lc_encoding
from globals import options as _g_options


def _te(gate):
  """True if the named typeenrich sub-gate is enabled (per EncodingConfig)."""
  return lc_encoding.current().te(gate)


def collect_positive_isa_entities(tree, polarity=True):
  """Return the set of entity IDs that appear in positive-polarity isa atoms.

  Recursively walks the raw Stage-2 JSON, tracking polarity through
  connectives, negation, implications, and low-confidence packages.
  Only entities in genuinely positive isa atoms are returned — entities
  in negated, antecedent, or low-confidence contexts are excluded so
  that entity category injection is not skipped for them.
  """
  found = set()
  if not isinstance(tree, list) or len(tree) == 0:
    return found
  op = tree[0]

  # Leaf isa atom — record only if positive polarity
  if (op == "isa" and len(tree) >= 3 and isinstance(tree[2], str)
      and polarity):
    found.add(tree[2])
    return found

  if not isinstance(op, str):
    for child in tree:
      if isinstance(child, list):
        found |= collect_positive_isa_entities(child, polarity)
    return found

  # Connectives: children inherit polarity
  if op in ("and", "or"):
    # Check for low-confidence @p sibling: ["and", ["holds",...], ["@p","S1",0.1]]
    # If confidence < 0.5, the formula will be negated — flip polarity for siblings.
    child_polarity = polarity
    for child in tree[1:]:
      if (isinstance(child, list) and len(child) == 3
          and child[0] == "@p" and isinstance(child[2], (int, float))
          and child[2] < 0.5):
        child_polarity = not polarity
        break
    for child in tree[1:]:
      if isinstance(child, list):
        found |= collect_positive_isa_entities(child, child_polarity)
    return found

  if op == "not" and len(tree) >= 2:
    found |= collect_positive_isa_entities(tree[1], not polarity)
    return found

  if op == "implies" and len(tree) >= 3:
    # Antecedent: flip polarity; consequent: keep polarity
    found |= collect_positive_isa_entities(tree[1], not polarity)
    found |= collect_positive_isa_entities(tree[2], polarity)
    return found

  if op in ("forall", "exists") and len(tree) >= 3:
    found |= collect_positive_isa_entities(tree[2], polarity)
    return found

  if op in ("normally", "holds", "question", "ask", "equivalent", "xor"):
    for child in tree[1:]:
      if isinstance(child, list):
        found |= collect_positive_isa_entities(child, polarity)
    return found

  # @id wrapper: recurse into package
  if op == "@id" and len(tree) >= 3:
    found |= collect_positive_isa_entities(tree[2], polarity)
    return found

  # Default: recurse into children
  for child in tree:
    if isinstance(child, list):
      found |= collect_positive_isa_entities(child, polarity)
  return found


def _try_singularize(word):
  """Return a candidate singular form of word, or None if no rule applies.

  Conservative: handles common -ies, -ches/shes/xes/ses/zes, and -s patterns.
  May produce a non-word for edge cases like "gas" → "ga", but that's harmless
  because rules use proper singular forms which won't match the bad output.

  Used to bridge LLM plural/singular inconsistency when Stage-1 picks a plural
  entity id (e.g. "berries 2") but rules use the singular type ("berry").
  """
  if not isinstance(word, str) or len(word) < 4:
    return None
  if word.endswith("ies"):
    return word[:-3] + "y"
  if (word.endswith("ches") or word.endswith("shes")
      or word.endswith("xes") or word.endswith("ses")
      or word.endswith("zes")):
    return word[:-2]
  if (word.endswith("s")
      and not word.endswith("ss")
      and not word.endswith("us")
      and not word.endswith("is")):
    return word[:-1]
  return None


# Broad biological supertypes that are always sound to assert as a superclass of
# a more specific Stage-2 type (gentleman->person, alligator->animal).
_BROAD_SUPERTYPES = frozenset({"person", "animal"})

try:
  from data_names import gender_of as _name_gender
except Exception:
  def _name_gender(_first):
    return None


def build_entity_category_clauses(s1_json, skip_entities=frozenset()):
  """Build isa clauses for concrete entities that carry a category annotation.

  For each unique concrete entity with a "category" field in any ASU, emits:
    {"@name": "entity_S<N>", "@logic": ["isa", category, entity_id]}
  where S<N> is the unit_id of the first ASU in which the entity appears.

  Additionally, when the entity id has a lowercase base word that differs from
  the category, also emits isa(base, entity_id).  For example, "man 1" with
  category "person" produces both isa(person, man 1) and isa(man, man 1).
  This ensures the descriptive type word is available for query matching.

  When the base word is detectably plural ("berries", "cars", "boxes"), also
  emits isa(singular, entity_id) — e.g. "berries 2" with base "berries" gets
  both isa(berries, berries 2) and isa(berry, berries 2).  Bridges Stage-2
  LLM inconsistency: rules typically use singular type names ("berry") but
  Stage-1 may pick plural entity ids ("berries 2") for mass-noun-like
  references.  Fixes case 164.

  Deduplicates by entity_id so each entity produces at most one set of clauses.
  Entities in *skip_entities* are skipped (they already have an isa in
  the Stage-2 logic).
  """
  if not s1_json or not isinstance(s1_json, list):
    return []
  seen = set()
  clauses = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for asu in pkg.get("units", []):
      if not isinstance(asu, dict):
        continue
      uid = asu.get("unit_id", "")
      for ent in asu.get("entities", []):
        if not isinstance(ent, dict):
          continue
        eid      = ent.get("id")
        category = ent.get("category")
        if not eid or not category:
          continue
        if ent.get("type") != "concrete":
          continue
        if eid in seen:
          continue
        seen.add(eid)
        name = "entity_" + uid
        # Category isa (e.g. isa(person, man 1)) — skip if Stage-2 already has it.
        if eid not in skip_entities:
          clauses.append({"@name": name, "@logic": ["isa", category, eid]})
        # (typeenrich) Broad biological supertypes are emitted even
        # when Stage-2 already gave a subtype (isa(gentleman,Harry) /
        # isa(alligator,Ted)): a gentleman IS a person, an alligator IS an
        # animal, and rules in the problem are quantified over "person"/
        # "animal" that nothing else establishes for the entity.  Gated to
        # -typeenrich (the super sub-gate) so the default path matches the
        # core-2026-06-03 checkpoint behavior.
        elif (category in _BROAD_SUPERTYPES
              and (_g_options.get("s2split_flag", False)
                   or _te("super"))):
          clauses.append({"@name": name, "@logic": ["isa", category, eid]})
        # (typeenrich) Gender from a first-name table: isa(man/woman, E),
        # so a rule guarded by "man"/"woman" can fire ("a man is either kind or
        # evil").  Sound when the name is known.
        if (category == "person" and _te("gender")):
          first = eid.split(" ", 1)[0]
          g = _name_gender(first)
          if g:
            clauses.append({"@name": name, "@logic": ["isa", g, eid]})
        # Base-word isa (e.g. isa(man, man 1)) — always add when the base
        # is a lowercase type word different from the category, even if
        # skip_entities contains the entity (Stage-2 may have isa(person,...)
        # but not isa(man,...)).
        parts = eid.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit():
          base = parts[0]
          if base[:1].islower() and base.lower() != category.lower():
            clauses.append({"@name": name, "@logic": ["isa", base, eid]})
            # Also emit singular form when the base is detectably plural,
            # to bridge "berries"/"berry"-style mismatches (case 164).
            singular = _try_singularize(base)
            if (singular and singular != base
                and singular.lower() != category.lower()):
              clauses.append({"@name": name, "@logic": ["isa", singular, eid]})
        # (typeenrich) Name-as-type: a multiword proper name is also typed by
        # its own name lowercased, so a generic existential ("a winter olympics")
        # can bind to the named constant ("Winter Olympics") that is otherwise
        # typed only by its category (isa(event,...)).
        if _te("nametype"):
          name_base = re.sub(r"\s+\d+$", "", eid).strip()
          name_type = name_base.lower()
          if (" " in name_base and re.search(r"[A-Z]", name_base)
              and name_type != category.lower()):
            clauses.append({"@name": name, "@logic": ["isa", name_type, eid]})
  return clauses


_SK_SUFFIX_RE = re.compile(r'^sk\d+_(\w+)$')


def merge_typeonly_skolems(result):
  """(abstraction) Merge per-sentence Skolem CONSTANTS of the same type that are
  used only generically, so a definite "the gym"/"the campus" that Stage 2
  re-introduced as a separate `exists G[isa(gym,G)]` in each sentence (folding to
  sk1_gym, sk4_gym, ...) co-refers across the rule and the question.

  A constant sk<N>_<suffix> is MERGEABLE iff every one of its occurrences is:
    - the 2nd arg of a POSITIVE isa(TYPE, S)             (a type-only fact), or
    - a NON-subject arg (index >= 3) of an is rel2 of either polarity (object /
      location of the relation, never the agent/subject).
  Any other occurrence -- is rel2 SUBJECT, has property/degree/part, have, =,
  negated isa, a $block/other nesting -- is a distinguishing predicate, and marks
  the constant (and so its whole same-suffix group) un-mergeable.  Condition (b):
  all positive isa types over a group must agree.  Only string Skolem constants
  merge (never Skolem functions ['sk0', X]).  Constants are not `#:`-UNA-wrapped,
  so the rename is clean (no equality/UNA interaction).
  """
  groups = {}        # suffix -> set(skolem const)
  bad = set()        # constants with a distinguishing occurrence
  isatypes = {}      # skolem -> set of positive-isa TYPEs

  def _note(s):
    m = _SK_SUFFIX_RE.match(s) if isinstance(s, str) else None
    if m:
      groups.setdefault(m.group(1), set()).add(s)
      return True
    return False

  def _scan(lit):
    if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
      if isinstance(lit, list):
        for x in lit:
          if _note(x):
            bad.add(x)
          elif isinstance(x, list):
            _scan(x)
      return
    head = lit[0]
    base = head[1:] if head.startswith("-") else head
    pos = not head.startswith("-")
    if base == "isa" and len(lit) >= 3:
      for i, a in enumerate(lit):
        if _note(a):
          if i == 2 and pos:
            isatypes.setdefault(a, set()).add(lit[1] if isinstance(lit[1], str) else None)
          else:
            bad.add(a)            # type slot, negated isa, or extra position
        elif isinstance(a, list):
          _scan(a)
      return
    if base == "is rel2" and len(lit) >= 2:
      for i, a in enumerate(lit):
        # (flatroles) an event object can be role-tagged as
        # ["eventprop", $role, value]; treat the inner value as occupying this
        # position so an object Skolem stays MERGEABLE instead of being scanned
        # as a distinguishing nested literal (which would mark it un-mergeable
        # and break "the gym"/"the campus" cross-sentence coreference).
        if isinstance(a, list) and len(a) == 3 and a[0] == "eventprop":
          a = a[2]
        if _note(a):
          if i <= 2:              # verb(1) or subject(2) -> distinguishing
            bad.add(a)
        elif isinstance(a, list):
          _scan(a)
      return
    for a in lit:                 # any other predicate -> distinguishing
      if _note(a):
        bad.add(a)
      elif isinstance(a, list):
        _scan(a)

  for c in result:
    if not isinstance(c, dict):
      continue
    for key in ("@logic", "@question"):
      body = c.get(key)
      if not isinstance(body, list):
        continue
      lits = body if (body and isinstance(body[0], list)) else [body]
      for lit in lits:
        _scan(lit)

  subst = {}
  for suffix, members in groups.items():
    members = sorted(members)
    if len(members) < 2 or any(m in bad for m in members):
      continue
    types = set()
    for m in members:
      types |= isatypes.get(m, set())
    if len(types) > 1:            # condition (b): inconsistent isa type
      continue
    for m in members[1:]:
      subst[m] = members[0]       # canonical = lowest-numbered Skolem

  if not subst:
    return result

  def _apply(n):
    if isinstance(n, list):
      return [_apply(x) for x in n]
    return subst.get(n, n) if isinstance(n, str) else n

  for c in result:
    if isinstance(c, dict):
      for key in ("@logic", "@question"):
        if key in c:
          c[key] = _apply(c[key])
  return result
