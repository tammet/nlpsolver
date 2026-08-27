# Answer formatting for the llm-based nlpsolver.
#
# This module renders the prover answer bindings that survived selection
# (proof_answer_select.py) into the final English answer string: who/what
# descriptions, where/when preposition phrases, boolean answers with verbal
# confidence qualifiers, and the generic answer-value join.  It also holds the
# query-shape probes (@who_query / @what_query / @where_query / @askvars) that
# procproofs.process_proof uses to dispatch among these formatters.
#
# Entity / Skolem rendering is delegated to proof_render.py.
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

from lc_clausify import is_skolem_const, is_skolem_fn, skolem_type_from_name
from proof_render import (
  entity_name, ans_atom_name, get_entity_display,
  get_skolem_type, get_skolem_fn_type,
)
from proof_explain import ans_display_key
from proof_answer_select import _extract_class_names, _ans_object_tier


# ======== formatting helpers ========


# Reconstruction witnesses of the existential-attribute folds (lc_existfold.py,
# lc_existfold_v2.py).  A proof may name one; an answer may not.
_INTERNAL_WITNESS_FUNCTORS = frozenset(("$typed_partof", "$typed_have"))


def _join_and_finish(parts):
  """Join parts with commas/and, capitalize first letter, ensure trailing period."""
  if len(parts) == 1:
    res = parts[0]
  elif len(parts) == 2:
    res = parts[0] + " and " + parts[1]
  else:
    res = ", ".join(parts[:-1]) + " and " + parts[-1]
  if res and res[0].islower():
    res = res[0].upper() + res[1:]
  if not res.endswith("."):
    res += "."
  return res


# ======== query-shape probes ========

def _extract_askvars(logic):
  """Return the @askvars count from the @question clause in logic, or None."""
  if not logic or not isinstance(logic, list):
    return None
  for obj in logic:
    if isinstance(obj, dict) and "@question" in obj and "@askvars" in obj:
      try:
        return int(obj["@askvars"])
      except (TypeError, ValueError):
        return None
  return None


def _is_prep_query(logic):
  """Return True if logic contains a @where_query or @when_query marker."""
  if not logic or not isinstance(logic, list):
    return False
  for obj in logic:
    if isinstance(obj, dict) and (obj.get("@where_query") or obj.get("@when_query")):
      return True
  return False


def _is_who_query(logic):
  """Return True if logic contains a @who_query marker."""
  if not logic or not isinstance(logic, list):
    return False
  for obj in logic:
    if isinstance(obj, dict) and obj.get("@who_query"):
      return True
  return False


def _get_who_entity(logic):
  """Return the @who_entity value from logic, or None."""
  if not logic or not isinstance(logic, list):
    return None
  for obj in logic:
    if isinstance(obj, dict) and "@who_entity" in obj:
      return obj["@who_entity"]
  return None


def _get_who_kind(logic):
  """Return the @who_kind value from logic ("who" or "what"), default "who"."""
  if not logic or not isinstance(logic, list):
    return "who"
  for obj in logic:
    if isinstance(obj, dict) and "@who_kind" in obj:
      return obj["@who_kind"]
  return "who"


def _is_what_query(logic):
  """Return True if logic contains a @what_query marker."""
  if not logic or not isinstance(logic, list):
    return False
  for obj in logic:
    if isinstance(obj, dict) and obj.get("@what_query"):
      return True
  return False


# ======== answer formatting ========

def _extract_question_property_words(logic):
  """Return the set of property words that the question's predicate body
  asks about — has_property / has_degree_property atoms with a literal
  string at the property slot. Used to strip those words from what-answer
  rendering ("What was deep?" / dent 2 → "the dent", not "the deep dent").
  """
  if not logic or not isinstance(logic, list):
    return frozenset()
  out = set()

  def _walk(node):
    if not isinstance(node, list) or not node:
      return
    head = node[0]
    if isinstance(head, str):
      bare = head[1:] if head.startswith("-") else head
      if bare == "has property" and len(node) >= 3 and isinstance(node[1], str):
        if not node[1].startswith("?:"):
          out.add(node[1])
      elif bare == "has degree property" and len(node) >= 3 and isinstance(node[1], str):
        if not node[1].startswith("?:"):
          out.add(node[1])
    for child in node:
      _walk(child)

  for clause in logic:
    if not isinstance(clause, dict):
      continue
    if clause.get("@sourcetype") == "question" or clause.get("@what_query"):
      _walk(clause.get("@logic"))
      _walk(clause.get("@question"))
  return frozenset(out)


def _strip_question_props(answer_str, prop_words):
  """Remove each prop word (whole word, case-insensitive) from answer_str
  and tidy up resulting whitespace and articles."""
  if not answer_str or not prop_words:
    return answer_str
  s = answer_str
  for w in prop_words:
    if not w:
      continue
    s = re.sub(r'\b' + re.escape(w) + r'\b', '', s, flags=re.IGNORECASE)
  # Collapse runs of whitespace and tidy stray space before punctuation.
  s = re.sub(r'\s+', ' ', s).strip()
  s = re.sub(r'\s+([.,;:])', r'\1', s)
  return s


def _resolve_what_skolem_answers(answers):
  """For 'what' queries, replace Skolem-typed answer values with population
  constants of the corresponding class.

  Two patterns handled:
    1. Skolem function terms:  $ans(["sk3","Emily 1"]) where sk3 is typed
       "wolf" → $ans("$some_wolf").  Uses get_skolem_fn_type.
    2. Skolem constants:       $ans("sk1_tobacco") where sk1_tobacco is typed
       "tobacco" (from isa(tobacco, sk1_tobacco) facts) → $ans("$some_tobacco").
       Uses get_skolem_type.

  The population constant renders as "a tobacco" / "a wolf" via entity_name,
  matching user expectations for "what is X?" queries that should return a
  class rather than a raw Skolem name.
  """
  for ans in answers:
    val = ans.get("answer")
    if not isinstance(val, list):
      continue
    new_val = []
    changed = False
    for atom in val:
      if not (isinstance(atom, list) and len(atom) >= 2 and atom[0] == "$ans"):
        new_val.append(atom)
        continue
      arg = atom[1]
      # Case 1: Skolem function term like ["sk3", "Emily 1"]
      if isinstance(arg, list) and arg and isinstance(arg[0], str):
        fn_type = get_skolem_fn_type(arg[0])
        if fn_type:
          pop_name = "$some_" + fn_type.replace(" ", "_")
          new_val.append(["$ans", pop_name] + atom[2:])
          changed = True
          continue
      # Case 2: Skolem constant like "sk1_tobacco"
      elif isinstance(arg, str) and is_skolem_const(arg):
        typ = get_skolem_type(arg)
        if typ:
          pop_name = "$some_" + typ.replace(" ", "_")
          new_val.append(["$ans", pop_name] + atom[2:])
          changed = True
          continue
      new_val.append(atom)
    if changed:
      ans["answer"] = new_val


# Generic umbrella categories that LLMs attach as the entity's category
# annotation (isa(person,X), isa(animal,X)) alongside a sentence-asserted
# specific type.  Demoted from "Who is X?" answers when a specific type exists.
_GENERIC_WHO_TYPES = frozenset({
    "person", "animal", "thing", "object", "entity", "place", "location",
    "being", "creature",
})


def _classify_who_answers(logic, who_entity):
  """Scan assertion clauses to build sets of known types and properties for who_entity.

  Only full-confidence isa facts (clauses without @confidence or
  @confidence == 1.0) qualify as type descriptions — partial-confidence
  isa entries (from probabilistic clauses) are excluded, since they
  would over-broaden the answer (case 236: isa(person, John) at 0.77
  is an artifact of the "John is probably not bad" formula structure,
  not a genuine uncertain type claim).  Property detection has no
  confidence filter: a partial-confidence property is still a valid
  qualitative descriptor.

  Returns (isa_types, property_names) where both are sets of strings.
  """
  isa_types = set()
  prop_names = set()
  if not logic or not isinstance(logic, list):
    return isa_types, prop_names
  # Assertion clauses carry the UNA `#:` prefix on Stage-1 numbered entities
  # (e.g. "#:John Sweeney 1"), but @who_entity is the bare form
  # ("John Sweeney 1").  Normalise both sides so the comparison matches
  # (case 236/1335 — without this, isa_types is empty and "Who is John
  # Sweeney?" falls through to Unknown instead of "A car.").
  def _bare(s):
    return s[2:] if isinstance(s, str) and s.startswith("#:") else s
  who_entity = _bare(who_entity)
  for obj in logic:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    nm = obj.get("@name", "")
    # Skip question-derived and population clauses
    if obj.get("@sourcetype") == "question":
      continue
    clause = obj["@logic"]
    if not isinstance(clause, list) or not clause:
      continue
    # Single-atom clauses only (not rules)
    if isinstance(clause[0], list):
      continue
    pred = clause[0]
    conf = obj.get("@confidence")
    full_conf = (conf is None or conf >= 1.0)
    if not full_conf:
      continue          # skip partial-confidence facts in both lists
    if pred == "isa" and len(clause) >= 3 and _bare(clause[2]) == who_entity:
      isa_types.add(clause[1])
    if pred in ("has degree property", "has property") and len(clause) >= 3 and _bare(clause[2]) == who_entity:
      prop_names.add(clause[1])
  return isa_types, prop_names


def _classify_use_vals(use_vals, isa_types, prop_names, who_entity,
                       non_self, self_only, seen):
  """Bucket each answer value into (types, properties, equalities), then
  inject prop_names (always) and isa_types (only when non_self is empty).

  Mutates `seen` to dedup injected names against answer values.
  Returns (types, properties, equalities, surviving_values).
  """
  surviving_values = set(v for v, _, _ in use_vals)
  equalities, types, properties = [], [], []

  for v, _, _ in use_vals:
    if v in isa_types:
      types.append(v)
    elif v in prop_names:
      properties.append(v)
    elif is_skolem_const(v):
      # Skolem with a known type — promote ("sk1_tobacco" → "tobacco")
      # so the answer renders "a tobacco" not the raw Skolem name.
      typ = get_skolem_type(v)
      if typ:
        types.append(typ)
      else:
        equalities.append(v)
    else:
      base = v.split()[0] if " " in v else v
      is_lower_noun = (base and base[0].islower()
                       and not any(c.isdigit() for c in v))
      if who_entity and isa_types and is_lower_noun:
        # Authoritative isa_types is full-confidence; lowercase value
        # NOT in that set is a partial-conf type leak — drop it.
        surviving_values.discard(v)
        continue
      if is_lower_noun:
        types.append(v)
      else:
        equalities.append(v)

  for p in prop_names:
    if p not in seen:
      seen.add(p)
      properties.append(p)
      surviving_values.add(p)

  # Case 236: prover only had self-ref answers but fact base has known
  # types — inject those and drop the tautological self-reference.
  if not non_self and isa_types:
    for v, _, _ in self_only:
      surviving_values.discard(v)
    equalities = []
    for t in sorted(isa_types):
      if t not in seen:
        seen.add(t)
        types.append(t)
        surviving_values.add(t)

  return types, properties, equalities, surviving_values


def _format_who_answers(answers, logic=None):
  """Format who/what-query answers as type, property, or identity descriptions.

  Each answer has val = [["$ans", TYPE_OR_ENTITY_OR_PROP], ...].
  Filters out $-prefixed constants (population/metadata).
  Self-referential answers (entity = queried entity) are kept only if no
  other answers exist.
  Ranking:
    Who:  equality > isa types > properties
    What: isa types > properties > equality
  Returns (answer_string, surviving_values_set).
  """
  who_entity = _get_who_entity(logic)
  who_kind = _get_who_kind(logic)
  isa_types, prop_names = _classify_who_answers(logic, who_entity)
  # Drop generic umbrella categories (person/animal/thing/…) from the answer
  # type set when a more specific type is also known: several LLMs assert the
  # entity's category isa(person,X) alongside the sentence's isa(car,X), which
  # would render "A car and a person" instead of "A car" (cases 1335/1556).
  if isa_types and not isa_types <= _GENERIC_WHO_TYPES:
    isa_types = isa_types - _GENERIC_WHO_TYPES
  class_names = _extract_class_names(logic)

  # Collect all valid answer values with their per-answer confidences.
  # Lower bound 0.05 (was 0.60): keep partial-confidence answers so that
  # cases 241/242 emit "Probably John." / "Maybe John." with a qualitative
  # prefix instead of "Unknown."  Very low confidence (< 0.05) is still
  # dropped — such answers are dominated by noise from the prover chain.
  # Per-atom tier filtering: a single proof's val may carry multiple $ans
  # atoms of different tiers (e.g. [$ans("John 1"), $ans("wing")] from a
  # part-inheritance chain).  Within each val we keep only atoms at the
  # best tier present, so concrete entities suppress class-label / Skolem
  # leaks within the same proof.
  all_vals = []  # (value, is_self_ref, confidence)
  seen = set()
  # Disjunctive answer detection: a single answer object whose val carries
  # 2+ $ans atoms is a multi-witness disjunctive residual from a clause-
  # level proof (e.g. case-analysis on "X or Y is …").  Render with "or"
  # instead of "and" — see also _format_answers line ~921 which already
  # handles this for the non-who-query path.
  is_disjunctive = any(
    isinstance(a.get("answer"), list)
    and sum(1 for x in a["answer"]
            if isinstance(x, list) and len(x) >= 2 and x[0] == "$ans") > 1
    for a in answers
  )

  for ans in answers:
    val = ans.get("answer")
    if not isinstance(val, list):
      continue
    conf = ans.get("confidence", 1)
    if conf < 0.05:
      continue
    best_atom_tier = _ans_object_tier(val, class_names)
    for atom in val:
      if not isinstance(atom, list) or len(atom) < 2 or atom[0] != "$ans":
        continue
      atom_tier = _ans_object_tier([atom], class_names)
      if atom_tier > best_atom_tier:
        continue
      v = atom[1]
      if isinstance(v, list):
        # Canonical witnesses introduced by existential folds represent "some
        # such object" inside the proof, not a user-facing answer.  Inspect the
        # original term narrowly: an unrelated structured answer must not be
        # discarded merely because its fallback rendering begins with '['.
        if _is_internal_fold_witness(v):
          continue
        # Complex term (e.g., ["$theof1","sister","Mary 1",...]) — render
        # via entity_name → render_term_english to get an English string
        # like "Mary's sister".  Without this, $theof1 answers fall through
        # and the user sees "Unknown."
        rendered = entity_name(v)
        if not isinstance(rendered, str) or not rendered:
          continue
        v = rendered
      elif not isinstance(v, str):
        continue
      # Filter internal $-markers ($defq*, $arc, $narc, ...).  Keep
      # $some_* / $some_not_* population witnesses — they only reach
      # this point when no concrete or Skolem answer exists (the tier
      # filter would otherwise have eliminated them), and entity_name
      # already renders them as natural English ("a penguin" /
      # "a non-bird"), letting "Who can't fly?" → "A penguin." instead
      # of falsely returning "Unknown."
      if v.startswith("$") and not v.startswith("$some_"):
        continue
      if v in seen:
        continue
      seen.add(v)
      is_self = (who_entity and v == who_entity)
      all_vals.append((v, is_self, conf))

  # Separate self-referential from non-self
  non_self = [(v, s, c) for v, s, c in all_vals if not s]
  self_only = [(v, s, c) for v, s, c in all_vals if s]

  # Decide which answer set to render.
  #   - non_self non-empty: prover found real answers; render those.
  #   - otherwise: drop self_only entirely.  A bare "Who is John?" → "John."
  #     restatement is tautological and worse than "Unknown."  When the fact
  #     base supplies isa_types or prop_names, the injection in
  #     _classify_use_vals below surfaces them; if nothing is known, the
  #     final answer falls through to "Unknown."
  if non_self:
    use_vals = non_self
  else:
    use_vals = []

  types, properties, equalities, surviving_values = _classify_use_vals(
    use_vals, isa_types, prop_names, who_entity, non_self, self_only, seen,
  )

  if not types and not properties and not equalities:
    return "Unknown.", set()

  # Build formatted parts.
  # When types and properties coexist, compose noun phrases: "a bad red car".
  # When only properties, list bare: "nice" or "nice and big".
  # Equalities rendered separately.
  parts = []

  # Compose type noun phrases with properties as adjectives
  if types:
    primary_type = types[0]
    adj_str = " ".join(properties) if properties else ""
    noun = adj_str + " " + primary_type if adj_str else primary_type
    if noun.startswith(("the ", "a ", "an ")):
      parts.append(noun)
    else:
      article = "an" if noun[0] in "aeiou" else "a"
      parts.append(article + " " + noun)
    # Additional types without adjectives
    for t in types[1:]:
      if t.startswith(("the ", "a ", "an ")):
        parts.append(t)
      else:
        article = "an" if t[0] in "aeiou" else "a"
        parts.append(article + " " + t)
  elif properties:
    # No types — list properties bare
    parts.extend(properties)

  # Equality answers
  for v in equalities:
    parts.append(entity_name(v, with_url=False))

  # Rank: for "what", types+props already first; for "who", equalities first
  if who_kind == "who" and equalities and (types or properties):
    # Move equality parts to front
    eq_parts = parts[len(types) + (1 if types else len(properties)):]
    type_parts = parts[:len(types) + (1 if types else len(properties))]
    parts = eq_parts + type_parts

  result = parts[0]
  if len(parts) > 1:
    join_word = " or " if is_disjunctive else " and "
    result = ", ".join(parts[:-1]) + join_word + parts[-1]

  # Qualitative confidence prefix based on the MINIMUM confidence across
  # the surviving answer set (the weakest link in the claim):
  #   > 0.8  -> no prefix
  #   > 0.4  -> "Probably "
  #   else   -> "Maybe "
  # Thresholds mirror the Stage-1 confidence table (0.8 = probably/likely,
  # 0.6 = maybe/possibly).  Applied to who-queries only; "what"-queries
  # have their own rendering pathway (set via who_kind).
  prefix = ""
  confs_in_use = [c for v, _, c in use_vals if v in surviving_values]
  if confs_in_use:
    min_conf = min(confs_in_use)
    if min_conf <= 0.4:
      prefix = "Maybe "
    elif min_conf <= 0.8:
      prefix = "Probably "

  if prefix:
    # Keep the first word's original case — "John" stays capitalized,
    # "a tobacco" stays lowercase after the capitalized prefix.
    result = prefix + result + "."
  else:
    result = result[0].upper() + result[1:] + "."

  return result, surviving_values


def _is_internal_fold_witness(term):
  """True only for canonical witness terms created by existential folds."""
  return (isinstance(term, list) and bool(term)
          and term[0] in _INTERNAL_WITNESS_FUNCTORS)


def _resolve_skolem_entity(val):
  """Resolve a Skolem constant or function to a human-readable name.

  For string Skolems like "sk0": looks up skolem_types → "the house".
  For list Skolems like ["sk0","box 2"]: looks up skolem_fn_types → "the house".
  Returns the resolved name string, or None if not a Skolem or no type found.
  """
  if is_skolem_const(val):
    # Fast path: extract type from name (sk0_house → house)
    typ = skolem_type_from_name(val)
    # Fallback: clause-list scan
    if not typ:
      typ = get_skolem_type(val)
    if typ:
      return "the " + typ if typ[0].islower() else typ
  if is_skolem_fn(val):
    typ = get_skolem_fn_type(val[0])
    if typ:
      return "the " + typ if typ[0].islower() else typ
  return None


def _location_entity_name(val, entity_props=None):
  """Format a location entity constant for display in a 'where' answer.

  Checks the entity_map first (user's original phrasing, with qualifier and
  article already incorporated).  Falls back to Skolem resolution, URL-name
  extraction and common-noun article logic.

  "house 2"             -> "the house"
  "house 3" (red)       -> "the red house"  (entity_map or entity_props lookup)
  "London 1"            -> "London"          (proper noun: no article)
  "https://.../Estonia" -> "Estonia"
  "sk0"                 -> "the house"       (Skolem type lookup)
  """
  if not isinstance(val, str):
    # List Skolem function like ["sk0", "box 2"]
    resolved = _resolve_skolem_entity(val)
    if resolved:
      return resolved
    return str(val)
  # Entity map overrides everything — already has correct article and qualifier
  em = get_entity_display(val)
  if em is not None:
    return em
  # String Skolem constants like "sk0"
  resolved = _resolve_skolem_entity(val)
  if resolved:
    return resolved
  # Population witness constants ($some_house) — humanise to "the house".
  if val.startswith("$some_"):
    cls = val[len("$some_"):]
    if cls.startswith("not_"):
      cls = cls[len("not_"):]
    cls = cls.replace("_", " ").strip()
    return ("the " + cls) if cls else val
  # URL constants: use entity_name which extracts the last path segment
  if val.startswith("http://") or val.startswith("https://"):
    return entity_name(val, with_url=False)
  # Strip trailing digit suffix
  m = re.match(r'^(.*\S)\s+\d+$', val)
  base = m.group(1) if m else val
  if base[:1].isupper():
    return base       # proper noun — no article
  # Numeric / temporal values: no article (years, times, counts)
  if base[:1].isdigit():
    return base
  # Strip leading "the " or "The " (entity names sometimes include the article)
  if base.lower().startswith("the "):
    base = base[4:]
  # Look up adjectives for this entity (e.g. "red" for "house 3")
  adjs = entity_props.get(val, []) if entity_props else []
  adj_prefix = " ".join(adjs) + " " if adjs else ""
  return "the " + adj_prefix + base


def _where_conf_prefix(conf):
  """Return a confidence qualifier prefix for a where answer, or None if below threshold.

  conf >= 0.95: no prefix (plain answer)
  conf >= 0.85: "Likely"
  conf >= 0.60: "Probably"
  conf <  0.60: return empty string to signal Unknown
  """
  if conf >= 0.95:
    return ""
  if conf >= 0.85:
    return "Likely"
  if conf >= 0.60:
    return "Probably"
  return None   # below threshold -> Unknown


def _build_entity_props(logic):
  """Build a dict mapping entity constant -> list of its property adjectives.

  Scans assertional @logic clauses for ["has property", adj, entity, ...] atoms.
  Returns {entity: [adj, ...]} where adj strings are in order of occurrence.
  """
  props = {}
  if not logic:
    return props
  for obj in logic:
    if not isinstance(obj, dict) or "@logic" not in obj:
      continue
    if obj.get("@sourcetype") == "question":
      continue
    clause = obj["@logic"]
    # Accept single atom or list of atoms (disjunctive clause)
    atoms = clause if isinstance(clause[0], list) else [clause]
    for atom in atoms:
      if (isinstance(atom, list) and len(atom) >= 3
          and atom[0] == "has property"
          and isinstance(atom[1], str) and isinstance(atom[2], str)):
        adj    = atom[1]
        entity = atom[2]
        if not entity.startswith("$"):
          props.setdefault(entity, [])
          if adj not in props[entity]:
            props[entity].append(adj)
  return props


def _format_prep_answers(answers, logic=None):
  """Format where/when-query answers as preposition + entity strings.

  Each answer has val = [["$ans", prep, entity], ...].
  Returns e.g. "In the house.", "On Monday.", "In the house and in the city."
  Applies confidence prefix ("Probably", "Likely") when confidence < 0.95.
  Returns "Unknown." when all answers are below the 0.60 confidence threshold.
  If logic is provided, adjectives for location entities are reconstructed.
  """
  entity_props = _build_entity_props(logic)

  # Collect all (prep, entity_key) pairs first, then filter.
  _SPECIFIC_PREPS = frozenset({"on", "in", "above", "under", "near"})
  entries = []   # list of (prep, entity_key, display_str, conf)
  seen    = set()
  for ans in answers:
    val  = ans.get("answer")
    conf = ans.get("confidence", 1.0)
    if not isinstance(val, list) or not val:
      continue
    atom = val[0]   # first (should be only) $ans atom
    if not isinstance(atom, list) or len(atom) < 3:
      continue
    prep       = atom[1]
    entity_raw = atom[2]
    if not isinstance(prep, str):
      continue
    if not isinstance(entity_raw, (str, list)):
      continue
    # Drop answers whose entity slot is an unresolved variable (the prover
    # returned a free `?:Xn` rather than a concrete location); they would
    # render as garbage like "in ?:X3".
    if isinstance(entity_raw, str) and entity_raw.startswith("?:"):
      continue
    # If the preposition slot is an unresolved variable, drop the prep
    # prefix and keep just the entity. Common when the prover unifies via
    # persistence with a variable-prep axiom and never narrows the prep.
    prep_for_display = "" if prep.startswith("?:") else prep
    entity_key = str(entity_raw)
    key = (prep, entity_key)
    if key in seen:
      continue
    seen.add(key)
    entity_display = _location_entity_name(entity_raw, entity_props)
    display = (prep_for_display + " " + entity_display) if prep_for_display else entity_display
    entries.append((prep, entity_key, display, conf))

  # Drop "at" answers when a more specific preposition ("on", "in", etc.)
  # exists for the same entity.  "at" is derived from on→at / in→at axioms;
  # showing both "on X" and "at X" is redundant.
  specific_entities = {ek for p, ek, _, _ in entries if p in _SPECIFIC_PREPS}
  parts = []
  seen_display = set()
  best_conf = 0.0
  for prep, ek, display, conf in entries:
    if prep == "at" and ek in specific_entities:
      continue
    if conf > best_conf:
      best_conf = conf
    # Dedup on the rendered string: distinct proof routes to the same
    # location (e.g. a $some_* witness vs a Skolem) render identically.
    if display in seen_display:
      continue
    seen_display.add(display)
    parts.append(display)

  if not parts:
    return "Unknown."

  prefix = _where_conf_prefix(best_conf)
  if prefix is None:
    return "Unknown."

  if prefix:
    parts[0] = prefix + " " + parts[0]
  return _join_and_finish(parts)


def _format_bool_answer(val, conf, has_conflict=False):
  """Format a True/False answer with verbal confidence qualifier.

  has_conflict: True when the prover returned both a positive and a negative
  proof; confidence then represents the net surplus of positive over negative
  evidence rather than pure positive-chain strength.

  Threshold scheme:
    True,  conf >= 0.95              -> "True"
    True,  conf >= 0.70              -> "Probably true"
    True,  conf >= 0.40, no conflict -> "Likely true"
    True,  conf >= 0.10              -> "Possibly true (confidence X)"
    True,  conf <  0.10              -> "Unknown."
    False, conf >= 0.95              -> "False"
    False, conf >= 0.85              -> "Likely false"
    False, conf >= 0.60              -> "Probably false"
    False, conf <  0.60              -> "Probably false"

  The asymmetry is intentional: True uses finer graduation because positive
  proofs carry varying chain strength, and very low confidence (<0.10) is
  indistinguishable from noise (→ "Unknown.").  False is proved by
  contradiction, so even weak negative evidence is informative — low-confidence
  False still reports "Probably false" rather than falling back to "Unknown.".
  """
  if conf >= 0.95:
    return "True" if val else "False"
  if val is True:
    if conf >= 0.70:
      return "Probably true"
    if conf >= 0.40 and not has_conflict:
      return "Likely true"
    if conf >= 0.10:
      return "Possibly true (confidence " + _fmt_conf(conf) + ")"
    return "Unknown."
  else:  # val is False
    if conf >= 0.85:
      return "Likely false"
    if conf >= 0.60:
      return "Probably false"
    return "Probably false"


def _format_answers(answers, askvars=None):
  """Collect answer values from all (non-duplicate) answer entries and join.

  askvars: if set, only the first askvars $ans atoms in each answer are
  shown in the output (the rest are auxiliary existential variables).
  The detailed proof explanation is unaffected.
  """
  parts     = []
  seen_keys = set()
  for ans in answers:
    val  = ans.get("answer")
    conf = ans.get("confidence", 1)

    key = ans_display_key(val)
    if key in seen_keys:
      continue
    seen_keys.add(key)

    if val is True or val is False:
      has_conflict = ("negative proof" in ans) and ("positive proof" in ans)
      s = _format_bool_answer(val, conf, has_conflict=has_conflict)
    elif isinstance(val, list) and val:
      # Each element is an $ans atom like ["$ans", "John 1"].
      # When len(val) > askvars, the prover produced a disjunctive residual:
      # multiple possible values for the same ask variable(s).  Group atoms
      # into chunks of size askvars; each chunk is one alternative.
      # Example: askvars=1, val=[[$ans,Mike],[$ans,Mary]] → "Mike or Mary"
      if askvars and len(val) > askvars:
        groups = [val[i:i+askvars] for i in range(0, len(val), askvars)]
        alt_strs = []
        for grp in groups:
          names = [ans_atom_name(a) for a in grp]
          alt_strs.append(" and ".join(names) if len(names) > 1 else names[0])
        s = " or ".join(alt_strs)
      else:
        display = val[:askvars] if askvars is not None else val
        names = [ans_atom_name(a) for a in display]
        s = names[0] if len(names) == 1 else "(" + " and ".join(names) + ")"
    else:
      s = str(val)
    parts.append(s)

  if not parts:
    return "Could not find an answer."
  return _join_and_finish(parts)


def _fmt_conf(conf):
  """Format a confidence float as a two-decimal string."""
  return str(round(conf, 2))
