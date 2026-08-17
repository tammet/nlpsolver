"""The graph Stage 2: a Stage-1-driven Stage 2 whose content atoms are triples.

The ordinary Stage 1 has already segmented the passage, fixed the entity ids
and typed each unit.  This module reads that output, sends it to the model
under its own system prompt, and checks the reply against the atom contract of
`prompts/graph/graph_stage2_instructions.txt`.  The reply has the ordinary
top-level Stage-2 shape, so `logconvert.rawlogic_convert` and everything after
it consume it unchanged; only the content atoms differ.

Every content atom is `[NAME, ARG1, ARG2]`.  `isa` names a concept, any other
open name a binary relation, and nine fixed names are event roles.  The checks
here are structural: they refuse an atom that is not a triple, a role used off
an event variable, an entity id the Stage 1 never introduced, a package that
is missing or doubled, a name written both as a lexical negative and under
`not`, one lemma used as both a concept and a relation where the two can meet,
and a passage package that merely restates the question.  A name that is only
odd is never refused.

The call goes through `llmparse._run_stage`, so JSON repair, the corrective
retry loop and the per-stage statistics are the ordinary ones.
"""

import json
import os
import re

from stage_sanity_core import Issue

VERSION = "graph_stage2/2026-08-16"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "graph")

INSTRUCTIONS = os.path.join(PROMPT_DIR, "graph_stage2_instructions.txt")
EXAMPLES = os.path.join(PROMPT_DIR, "graph_stage2_examples.txt")
CHECKLIST = os.path.join(PROMPT_DIR, "graph_stage2_checklist.txt")

ONESTAGE_INSTRUCTIONS = os.path.join(PROMPT_DIR,
                                     "graph_onestage_instructions.txt")
ONESTAGE_EXAMPLES = os.path.join(PROMPT_DIR, "graph_onestage_examples.txt")

CONCEPT = "isa"

# the fixed role vocabulary of design plan §4.4; these are not open names
ROLES = ("agent", "theme", "recipient", "source", "destination", "location",
         "instrument", "time", "manner")

# formula operators and package wrappers; everything else at position 0 of a
# list is a content atom's name
STRUCTURAL = ("and", "or", "not", "implies", "forall", "exists", "normally",
              "=", "question", "ask", "holds", "@id", "@p")

BINDERS = ("forall", "exists", "ask")

# names the ordinary converter owns; a graph atom may never carry one
RESERVED = ("is rel2", "has property", "has degree property", "has degree rel2",
            "have", "has part", "has type", "has actor", "has target",
            "has recipient", "has location", "has time", "isa activity",
            "$setof", "$count", "$measure", "$measure_of", "$ctxt", "$block",
            "next", "state time", "state location", "xor", "not")

# a Stage-1 numbered entity id: a phrase and a number, as `John 1`
ENTITY_ID = re.compile(r"^.+\s+\d+$")

# a Stage-2 variable: a single uppercase-initial token with no space
VARIABLE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


VAGUE_NAMES = frozenset([
    "related_to", "relates_to", "thing", "things", "entity", "entities",
    "property", "properties", "attribute", "object", "item", "stuff",
    "connected_to", "associated_with", "has_relation", "relation"])

_VAGUE_NUMBERED = re.compile(r"^(relation|property|concept|predicate|name)_?\d+$")

_sysprompt = [None]
_onestage_sysprompt = [None]


# ------------------------------------------------------------------ prompts

def sysprompt():
  """The composed graph Stage-2 system prompt, built as the ordinary ones."""
  if _sysprompt[0] is None:
    import llmparse
    _sysprompt[0] = llmparse._compose_prompt(INSTRUCTIONS, EXAMPLES,
                                             "graph_stage2",
                                             checklist_file=CHECKLIST)
  return _sysprompt[0]


def onestage_sysprompt():
  """The English-only ablation prompt (Phase A arms 2 and 3)."""
  if _onestage_sysprompt[0] is None:
    import llmparse
    _onestage_sysprompt[0] = llmparse._compose_prompt(
        ONESTAGE_INSTRUCTIONS, ONESTAGE_EXAMPLES, "graph_onestage")
  return _onestage_sysprompt[0]


def prompt_sizes():
  """-> the character size of each prompt this module can send."""
  import llmparse
  ordinary = llmparse._compose_prompt(
      os.path.join(ROOT, "prompts", "stage2_instructions_full.txt"),
      os.path.join(ROOT, "prompts", "stage2_examples.txt"), "stage2",
      checklist_file=os.path.join(ROOT, "prompts",
                                  "stage2_checklist_full.txt"))
  return {"graph_stage2": len(sysprompt()),
          "graph_onestage": len(onestage_sysprompt()),
          "ordinary_stage2": len(ordinary),
          "graph_share_of_ordinary": round(len(sysprompt())
                                           / float(len(ordinary) or 1), 3)}


def prompt_hashes():
  import hashlib
  out = {}
  for p in (INSTRUCTIONS, EXAMPLES, CHECKLIST, ONESTAGE_INSTRUCTIONS,
            ONESTAGE_EXAMPLES):
    if os.path.exists(p):
      out[os.path.relpath(p, ROOT)] = hashlib.sha256(
          open(p, "rb").read()).hexdigest()
  return out


# ------------------------------------------------------- reading a Stage 1

def stage1_units(s1_json):
  """-> [(unit id, unit dict, the raw sentence)] in Stage-1 order."""
  out = []
  for block in s1_json or []:
    raw = (block or {}).get("raw") if isinstance(block, dict) else None
    for unit in ((block or {}).get("units") or []):
      if isinstance(unit, dict) and unit.get("unit_id"):
        out.append((unit["unit_id"], unit, raw))
  return out


def stage1_entity_ids(s1_json):
  out = set()
  for _uid, unit, _raw in stage1_units(s1_json):
    for e in (unit.get("entities") or []):
      if isinstance(e, dict) and e.get("id"):
        out.add(str(e["id"]))
  return out


def stage1_entity_rows(s1_json):
  """-> the entity inventory arm 2 is given: id, type, category."""
  seen, rows = set(), []
  for _uid, unit, _raw in stage1_units(s1_json):
    for e in (unit.get("entities") or []):
      if isinstance(e, dict) and e.get("id") and e["id"] not in seen:
        seen.add(e["id"])
        rows.append({"id": e["id"], "type": e.get("type"),
                     "category": e.get("category")})
  return rows


def question_unit_ids(s1_json):
  return [uid for uid, unit, _raw in stage1_units(s1_json)
          if str(unit.get("type") or "").lower() == "query"]


def sentence_of(s1_json, unit_id):
  """The English a unit came from: its own text, else its raw sentence."""
  for uid, unit, raw in stage1_units(s1_json):
    if uid == unit_id:
      return unit.get("text") or raw
  return None


# -------------------------------------------------------- walking a Stage 2

def packages(s2):
  """-> [(package id, the package body)] for a graph Stage-2 output."""
  out = []
  if not (isinstance(s2, list) and s2 and s2[0] == "and"):
    return out
  for item in s2[1:]:
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      out.append((item[1], item[2]))
  return out


def is_atom(node):
  """A content atom: a list whose head is a name the grammar does not own."""
  return (isinstance(node, list) and node and isinstance(node[0], str)
          and node[0] not in STRUCTURAL)


def walk_atoms(node, path="", polarity=1, bound=(), out=None):
  """-> [(atom, path, polarity, the variables bound above it)]."""
  if out is None:
    out = []
  if not isinstance(node, list) or not node:
    return out
  head = node[0]
  if not isinstance(head, str):
    for i, child in enumerate(node):
      walk_atoms(child, "%s/%d" % (path, i), polarity, bound, out)
    return out
  if is_atom(node):
    out.append((node, path, polarity, tuple(bound)))
    return out
  if head in BINDERS and len(node) >= 3 and isinstance(node[1], str):
    walk_atoms(node[2], "%s/%s:%s" % (path, head, node[1]), polarity,
               tuple(bound) + (node[1],), out)
    return out
  if head == "not" and len(node) == 2:
    walk_atoms(node[1], path + "/not", -polarity, bound, out)
    return out
  if head == "implies" and len(node) == 3:
    walk_atoms(node[1], path + "/implies:body", -polarity, bound, out)
    walk_atoms(node[2], path + "/implies:head", polarity, bound, out)
    return out
  for i, child in enumerate(node[1:], start=1):
    walk_atoms(child, "%s/%s" % (path, head), polarity, bound, out)
  return out


def atoms_of(s2):
  """-> [(package id, atom, path, polarity, bound variables)] for the output."""
  out = []
  for pid, body in packages(s2):
    for atom, path, pol, bound in walk_atoms(body, "@id:%s" % pid):
      out.append((pid, atom, path, pol, bound))
  return out


def kind_of(atom):
  return "concept" if atom and atom[0] == CONCEPT else "relation"


def name_of(atom):
  """The open name an atom carries: the concept for `isa`, else the head."""
  if not atom:
    return None
  if atom[0] == CONCEPT and len(atom) >= 2 and isinstance(atom[1], str):
    return atom[1]
  return atom[0]


def participants(atom):
  """The atom's participant terms: the entity for `isa`, both otherwise."""
  if not atom:
    return []
  if atom[0] == CONCEPT:
    return [atom[2]] if len(atom) > 2 else []
  return list(atom[1:3])


def question_packages(s2):
  out = []
  for pid, body in packages(s2):
    if _has_question(body):
      out.append(pid)
  return out


def _has_question(node):
  if not isinstance(node, list) or not node:
    return False
  if isinstance(node[0], str) and node[0] in ("question", "ask"):
    return True
  return any(_has_question(c) for c in node if isinstance(c, list))


# ----------------------------------------------------------- normalization

def normalize_name(name):
  """Lowercase, underscores for spaces, nothing else."""
  if not isinstance(name, str):
    return name
  return re.sub(r"\s+", "_", name.strip()).lower()


def normalize_in_place(s2):
  """Rewrite every open name to its normalized form.  -> the count changed.

  A space or a capital in a name is repaired here rather than sent back to the
  model: it changes no meaning, and the converter would otherwise read the name
  as a compound.
  """
  changed = [0]

  def fix(node):
    if not isinstance(node, list) or not node:
      return
    if is_atom(node):
      if node[0] == CONCEPT:
        if len(node) > 1 and isinstance(node[1], str):
          new = normalize_name(node[1])
          if new != node[1]:
            node[1] = new
            changed[0] += 1
      else:
        new = normalize_name(node[0])
        if new != node[0]:
          node[0] = new
          changed[0] += 1
      return
    for child in node:
      if isinstance(child, list):
        fix(child)

  fix(s2)
  return changed[0]


# ---------------------------------------------------------------- the checks

_RESERVED_KEYS = frozenset(re.sub(r"\s+", "_", n).lower() for n in RESERVED)


def _is_reserved(name):
  """A reserved name, whether it was written with a space or an underscore."""
  return isinstance(name, str) and normalize_name(name) in _RESERVED_KEYS


def _is_variable(term, bound=()):
  return isinstance(term, str) and (term in bound or bool(VARIABLE.match(term)))


def _looks_like_entity_id(term):
  return isinstance(term, str) and bool(ENTITY_ID.match(term))


def _event_variables(atom_rows):
  """A variable used as the first argument of a fixed role, or typed `*_event`.

  Only a variable qualifies.  Reading the first argument of every role atom as
  an event would let a role written on an entity declare that entity an event,
  and the check for exactly that mistake could never fire.
  """
  out = set()
  for _pid, atom, _p, _pol, _b in atom_rows:
    if atom[0] in ROLES and len(atom) > 1 and isinstance(atom[1], str) \
            and VARIABLE.match(atom[1]):
      out.add(atom[1])
    if atom[0] == CONCEPT and len(atom) > 2 and isinstance(atom[1], str) \
            and isinstance(atom[2], str) and atom[1].endswith("_event"):
      out.add(atom[2])
  return out


def _issue(kind, location, description, evidence):
  return Issue(kind=kind, location=location, description=description,
               evidence=evidence if isinstance(evidence, str)
               else json.dumps(evidence))


def check_atoms(s2, s1_json=None):
  """The structural checks of design plan §4.7.  -> [Issue]."""
  issues = []
  rows = atoms_of(s2)
  known = stage1_entity_ids(s1_json) if s1_json else set()
  events = _event_variables(rows)
  for pid, atom, path, _pol, bound in rows:
    where = "%s%s" % (pid, path.split("@id:%s" % pid)[-1])
    if len(atom) != 3:
      issues.append(_issue(
          "atom_arity", where,
          "A content atom must have exactly three items: [NAME, ARG1, ARG2]. "
          "This one has %d. Write a concept as [\"isa\", CONCEPT, ENTITY] and "
          "a relation as [NAME, LEFT, RIGHT]." % len(atom), atom))
      continue
    head = atom[0]
    if not isinstance(head, str):
      issues.append(_issue("atom_name_not_a_string", where,
                           "The first item of a content atom must be a name.",
                           atom))
      continue
    if _is_reserved(head) or (head == CONCEPT and _is_reserved(atom[1])):
      issues.append(_issue(
          "reserved_name", where,
          "`%s` is reserved by the downstream system and may not be a content "
          "name. Build an open name from the words of the unit instead."
          % (head if _is_reserved(head) else atom[1]), atom))
      continue
    if head == CONCEPT and not isinstance(atom[1], str):
      issues.append(_issue("concept_not_a_string", where,
                           "The concept slot of `isa` must be a name.", atom))
      continue
    # roles
    subject = atom[1]
    if head in ROLES:
      if not (isinstance(subject, str) and subject in events):
        issues.append(_issue(
            "role_off_an_event", where,
            "`%s` is a fixed event role and may only take an event variable as "
            "its first argument. Use an open relation name for an ordinary "
            "relation." % head, atom))
    elif head != CONCEPT and isinstance(subject, str) and subject in events:
      issues.append(_issue(
          "open_name_on_an_event", where,
          "`%s` is an open relation name used on the event variable `%s`. An "
          "event participant is attached with one of the fixed roles %s."
          % (head, subject, ", ".join(ROLES)), atom))
    # entity ids
    for term in participants(atom):
      if not isinstance(term, str):
        continue
      if _is_variable(term, bound) or term in events:
        continue
      if _looks_like_entity_id(term) and known and term not in known:
        issues.append(_issue(
            "entity_id_not_in_stage1", where,
            "`%s` is written as a Stage-1 entity id but Stage 1 does not "
            "introduce it. Use exactly the ids Stage 1 gives, or write the "
            "value or kind as a plain lowercase name." % term, atom))
    # swapped isa arguments
    if head == CONCEPT and len(atom) == 3:
      concept, entity = atom[1], atom[2]
      if isinstance(concept, str) and concept in known \
              and not (_is_variable(entity, bound) or entity in known
                       or entity in events):
        issues.append(_issue(
            "isa_arguments_swapped", where,
            "`isa` takes the concept first and the entity second: `%s` is a "
            "Stage-1 entity, so write [\"isa\", CONCEPT, \"%s\"]."
            % (concept, concept), atom))
  return issues


def check_packages(s2, s1_json=None):
  """Package ids, their Stage-1 origin, and exactly one question."""
  issues = []
  if not (isinstance(s2, list) and s2 and s2[0] == "and"):
    return [_issue("output_shape", "",
                   "The output must be [\"and\", [\"@id\", \"Sx\", PACKAGE], "
                   "...] and nothing else.", json.dumps(s2)[:400])]
  ids = [pid for pid, _b in packages(s2)]
  want = [uid for uid, _u, _r in stage1_units(s1_json)] if s1_json else []
  seen = set()
  for pid in ids:
    if pid in seen:
      issues.append(_issue("duplicate_package", str(pid),
                           "Unit %s has more than one package. Write exactly "
                           "one [\"@id\", \"%s\", ...] for each unit."
                           % (pid, pid), pid))
    seen.add(pid)
    if want and pid not in want:
      issues.append(_issue("unknown_package", str(pid),
                           "`%s` is not a Stage-1 unit id. Use the unit ids "
                           "of the input." % pid, pid))
  for uid in want:
    if uid not in seen:
      issues.append(_issue("missing_package", str(uid),
                           "Unit %s has no package. Every Stage-1 unit needs "
                           "exactly one." % uid, uid))
  qs = question_packages(s2)
  if len(qs) != 1:
    issues.append(_issue(
        "question_packages", ",".join(str(q) for q in qs),
        "There must be exactly one question package; this output has %d. The "
        "query unit gets [\"question\", F] or [\"ask\", \"X\", F] and no other "
        "unit does." % len(qs), json.dumps(qs)))
  return issues


def check_lexical_negatives(s2):
  """`not [P, a, b]` beside `[not_P, a, b]` for the same participants."""
  issues = []
  negated, positive = {}, {}
  for pid, atom, path, pol, _b in atoms_of(s2):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    key = (name_of(atom), json.dumps(participants(atom), sort_keys=True),
           kind_of(atom))
    (negated if pol < 0 else positive)[key] = (pid, path, atom)
  for (name, args, kind), (pid, path, atom) in positive.items():
    if not isinstance(name, str):
      continue
    for prefix in ("not_", "non_", "un"):
      if name.startswith(prefix):
        bare = name[len(prefix):]
        hit = negated.get((bare, args, kind))
        if hit:
          issues.append(_issue(
              "lexical_negative_and_not", "%s/%s" % (pid, hit[0]),
              "The same statement is written twice: `%s` as a lexical negative "
              "and `%s` under `not`. Keep one form — use [\"not\", ...] when "
              "the text says not." % (name, bare),
              json.dumps([atom, hit[2]])))
  return issues


def check_shape_consistency(s2):
  """One lemma used as a concept and as a relation where the two can meet."""
  issues = []
  concepts, relations = {}, {}
  for pid, atom, path, _pol, bound in atoms_of(s2):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    name = name_of(atom)
    if not isinstance(name, str):
      continue
    lemma = normalize_name(name).replace("_", " ")
    row = (pid, atom, participants(atom), bound)
    (concepts if kind_of(atom) == "concept" else relations).setdefault(
        lemma, []).append(row)
  for lemma in sorted(set(concepts) & set(relations)):
    for c in concepts[lemma]:
      for r in relations[lemma]:
        if not _can_interact(c, r):
          continue
        issues.append(_issue(
            "shape_inconsistency", "%s/%s" % (c[0], r[0]),
            "`%s` is written as a concept in %s and as a relation in %s, and "
            "the two can meet. Within one case a verb or construction takes "
            "one shape everywhere: choose either [\"isa\", \"%s\", X] or "
            "[\"%s\", X, Y] and use it in both."
            % (lemma, c[0], r[0], normalize_name(lemma),
               normalize_name(lemma)),
            json.dumps([c[1], r[1]])))
        break
      else:
        continue
      break
  return issues


def _can_interact(a, b):
  """Two occurrences meet when they share an entity or one is quantified."""
  if a[0] == b[0]:
    return True
  a_terms = [t for t in a[2] if isinstance(t, str)]
  b_terms = [t for t in b[2] if isinstance(t, str)]
  if set(a_terms) & set(b_terms):
    return True
  return bool(a[3]) or bool(b[3])


def check_question_restatement(s2):
  """A passage package whose atoms are the question's, same participants."""
  issues = []
  qs = question_packages(s2)
  if len(qs) != 1:
    return issues
  qid = qs[0]
  by = {}
  for pid, atom, _path, pol, _b in atoms_of(s2):
    if len(atom) != 3:
      continue
    by.setdefault(pid, []).append(
        (pol, name_of(atom), kind_of(atom),
         json.dumps(participants(atom), sort_keys=True)))
  want = sorted(by.get(qid) or [])
  if not want:
    return issues
  for pid in sorted(by):
    if pid == qid:
      continue
    if sorted(by[pid]) == want:
      issues.append(_issue(
          "question_restated", str(pid),
          "Unit %s asserts exactly what the question asks. A passage unit must "
          "translate its own sentence; the question is never a fact." % pid,
          json.dumps(want)))
  return issues


def check_free_variables(s2):
  import stage_sanity_s2
  try:
    return list(stage_sanity_s2._check_stage2_free_variables(s2))
  except Exception:                                             # noqa: BLE001
    return []


# ------------------------------------------------ WP4.2, the translator checks

_NAME_EXCEPTIONS = ("_for_a_", "_event")
_PLURAL = ("ies", "es", "s")
_TENSE = ("ing", "ed")
_PREFIX = ("has_", "is_", "can_", "are_")
_HEAD = ("form_of_", "kind_of_", "type_of_")
_STOP_TOKENS = frozenset(("a", "an", "the", "of", "to", "in", "on", "for",
                          "by", "with", "and", "or", "not", "is", "are",
                          "that", "this", "it", "its", "as", "at", "from",
                          "be", "can", "will", "has", "have"))
_SOME_START = ("some ", "there is ", "there are ", "a few ", "several ",
               "at least one ", "there exists ", "there exist ")


def _all_names(s2):
  """-> {name: [package ids]} over every atom of a graph Stage 2."""
  out = {}
  for pid, atom, _path, _pol, _bound in atoms_of(s2):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    name = name_of(atom)
    if isinstance(name, str):
      out.setdefault(name, []).append(pid)
  return out


def check_kind_class_consistency(s2, s1_json=None):
  """One entity id used both as a class and as a kind constant."""
  issues = []
  as_class, as_constant = {}, {}
  for pid, atom, _path, _pol, bound in atoms_of(s2):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    if kind_of(atom) == "concept":
      name = name_of(atom)
      if isinstance(name, str):
        as_class.setdefault(name, []).append(pid)
    for term in participants(atom):
      if isinstance(term, str) and not term.startswith("?") \
         and term not in bound:
        as_constant.setdefault(term, []).append(pid)
  for name in sorted(set(as_class) & set(as_constant)):
    issues.append(_issue(
        "kind_class_inconsistency", as_class[name][0],
        "`%s` is written as a class in %s and as a kind constant in %s. "
        "A generic entity is one or the other, the same choice in every "
        "unit including the question: either [\"isa\", \"%s\", X] "
        "everywhere, or the bare constant %s everywhere."
        % (name, as_class[name][0], as_constant[name][0], name, name),
        json.dumps([as_class[name][0], as_constant[name][0]])))
  return issues


def check_monolith_names(s2, s1_json=None):
  """A name whose tokens contain another name of the same case."""
  issues = []
  names = _all_names(s2)
  ids = set()
  if s1_json:
    try:
      ids = set(stage1_entity_ids(s1_json))
    except Exception:
      ids = set()
  for name in sorted(names):
    if any(x in name for x in _NAME_EXCEPTIONS):
      continue
    tokens = [t for t in str(name).split("_") if t]
    if len(tokens) < 3:
      continue
    inside = []
    for other in names:
      if other == name or len(str(other).split("_")) < 2:
        continue
      if ("_%s_" % other) in ("_%s_" % name):
        inside.append(other)
    for eid in ids:
      key = normalize_name(str(eid))
      if key and key != name and ("_%s_" % key) in ("_%s_" % name):
        inside.append(str(eid))
    if inside:
      issues.append(_issue(
          "monolith_name", names[name][0],
          "the name `%s` contains %s, which the case already has as its own "
          "name. One head name per verb: put the modifier, object or adjunct "
          "in its own atom or role instead of inside the name."
          % (name, ", ".join("`%s`" % x for x in sorted(set(inside))[:3])),
          json.dumps(sorted(set(inside)))))
  return issues


def _name_key(name):
  """A name stripped of number, tense, a `has_`/`is_` prefix and a head."""
  key = normalize_name(str(name))
  for pre in _PREFIX:
    if key.startswith(pre):
      key = key[len(pre):]
      break
  for head in _HEAD:
    if key.startswith(head):
      key = key[len(head):]
      break
  parts = []
  for token in key.split("_"):
    for suf in _TENSE + _PLURAL:
      if len(token) > len(suf) + 2 and token.endswith(suf):
        token = token[:-len(suf)]
        break
    parts.append(token)
  return "_".join(p for p in parts if p)


def check_near_duplicate_names(s2, s1_json=None):
  """Two names that differ only in number, tense, prefix or head word."""
  issues, seen = [], {}
  for name in sorted(_all_names(s2)):
    seen.setdefault(_name_key(name), []).append(name)
  for key, group in sorted(seen.items()):
    if len(group) < 2:
      continue
    issues.append(_issue(
        "near_duplicate_names", "s2",
        "%s are the same name in different wording. Use one form for one "
        "meaning in a case, or say why the two differ."
        % ", ".join("`%s`" % g for g in group),
        json.dumps(group)))
  return issues


def check_question_reuse(s2, s1_json=None):
  """A question name that half-matches a passage name instead of reusing it."""
  issues = []
  asked = set(question_packages(s2))
  if not asked:
    return issues
  qnames, pnames = {}, {}
  for pid, atom, _path, _pol, _bound in atoms_of(s2):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    name = name_of(atom)
    if not isinstance(name, str):
      continue
    (qnames if pid in asked else pnames).setdefault(name, pid)
  for qname in sorted(qnames):
    if qname in pnames:
      continue
    q = set(t for t in _name_key(qname).split("_")
            if t and t not in _STOP_TOKENS)
    if len(q) < 2:
      continue
    for pname in sorted(pnames):
      p = set(t for t in _name_key(pname).split("_")
              if t and t not in _STOP_TOKENS)
      shared = q & p
      if len(shared) >= 2 and q != p:
        issues.append(_issue(
            "question_not_reused", qnames[qname],
            "the question writes `%s` where the passage writes `%s`; they "
            "share %s. The question reuses the passage's names and shapes "
            "wherever the same words occur, or nothing connects them."
            % (qname, pname, ", ".join(sorted(shared))),
            json.dumps([qname, pname])))
        break
  return issues


def check_existential_units(s2, s1_json=None):
  """A "some" / "there is" unit that came out as a bare universal.

  folio-0046: "Some pets are not mammals" written as a universal turns a
  counterexample into a rule, and the run then proves the opposite.
  """
  issues = []
  if not s1_json:
    return issues
  try:
    units = stage1_units(s1_json)
  except Exception:
    return issues
  wanted = set()
  for uid, unit, raw in units:
    text = str(unit.get("text") or raw or "").strip().lower()
    if any(text.startswith(w) for w in _SOME_START):
      wanted.add(uid)
  if not wanted:
    return issues
  for pid, body in packages(s2):
    if pid not in wanted:
      continue
    blob = json.dumps(body, default=str)
    if '"exists"' in blob:
      continue
    if '"forall"' not in blob:
      continue
    issues.append(_issue(
        "existential_written_as_universal", pid,
        "%s begins with an existential word but its package has a `forall` "
        "and no `exists`. \"Some A are B\" is an `exists`, never a bare "
        "`forall`: written as a universal it says every A is a B." % pid,
        blob[:300]))
  return issues


_HEDGE = ("generally", "usually", "typically", "normally", "tend to",
          "tends to", "often", "most ", "likely", "may ", "might ", "seems",
          "suggests", "in general", "as a rule", "commonly", "sometimes")


def check_question_entity(s2, s1_json=None):
  """A concrete entity of the question unit that the question package drops.

  folio-0117: "Peter can block Windy's shooting?" lost Windy, so the question
  asked whether Peter blocks at all.  This is the ONLY mechanical check on
  that failure — generic entities, passage units and the shape of the relation
  are left to the prompt rules.
  """
  issues = []
  if not s1_json:
    return issues
  import graph_inventory as GI
  try:
    units = dict((uid, unit) for uid, unit, _raw in stage1_units(s1_json))
  except Exception:
    return issues
  for pid, body in packages(s2):
    if pid not in set(question_packages(s2)):
      continue
    unit = units.get(pid) or {}
    terms = set()
    for _p, atom, _path, _pol, _bound in atoms_of(["and", ["@id", pid, body]]):
      for term in participants(atom):
        if isinstance(term, str):
          terms.add(GI.comparison_key(term))
    for ent in (unit.get("entities") or []):
      if not isinstance(ent, dict) or not ent.get("id"):
        continue
      if str(ent.get("type") or "").lower() != "concrete":
        continue
      key = GI.comparison_key(str(ent["id"]))
      if key and key not in terms:
        issues.append(_issue(
            "question_entity_missing", pid,
            "the question unit names the concrete entity `%s`, and the "
            "question package never mentions it. Ask about the entity the "
            "question asks about: every concrete entity of the question unit "
            "is an argument somewhere in its package." % ent["id"],
            json.dumps({"entity": ent["id"], "package": pid})))
  return issues


def _has_hedge(text):
  low = " %s " % str(text or "").strip().lower()
  return any(h in low for h in _HEDGE)


def check_hedge_rule(s2, s1_json=None):
  """`normally` exactly where the unit's own words hedge, and nowhere else."""
  issues = []
  if not s1_json:
    return issues
  try:
    units = dict((uid, (unit, raw)) for uid, unit, raw in stage1_units(s1_json))
  except Exception:
    return issues
  for pid, body in packages(s2):
    got = units.get(pid)
    if not got:
      continue
    unit, raw = got
    text = unit.get("text") or raw or ""
    hedged = _has_hedge(text)
    has_normally = '"normally"' in json.dumps(body, default=str)
    if hedged and not has_normally:
      issues.append(_issue(
          "hedge_without_normally", pid,
          "%s reads %r, which hedges, and its package has no `normally`. "
          "A hedged rule is defeasible: wrap the consequent."
          % (pid, str(text)[:90]), str(text)[:200]))
    elif has_normally and not hedged:
      issues.append(_issue(
          "normally_without_hedge", pid,
          "%s has `normally` but its own text %r carries no hedge word. "
          "Read the words, not the Stage-1 unit type: with no hedge the rule "
          "is strict." % (pid, str(text)[:90]), str(text)[:200]))
  return issues


def _literals(node, out):
  """Every atom of a formula, with its polarity, as comparable keys."""
  if not isinstance(node, list) or not node:
    return
  head = node[0]
  if head == "not":
    inner = []
    _literals(node[1] if len(node) > 1 else None, inner)
    for sign, key in inner:
      out.append(("-" if sign == "+" else "+", key))
    return
  if head in ("and", "or"):
    for sub in node[1:]:
      _literals(sub, out)
    return
  if head in ("forall", "exists"):
    _literals(node[-1], out)
    return
  if head in ("normally", "holds", "question"):
    _literals(node[-1], out)
    return
  if head == "implies":
    return
  if len(node) == 3 and isinstance(head, str):
    out.append(("+", json.dumps(node, default=str)))


def _strip(node):
  """Look through forall / normally / holds to the formula underneath."""
  while isinstance(node, list) and node and node[0] in ("forall", "exists",
                                                        "normally", "holds"):
    node = node[-1]
  return node


def _tautology_of(node, premises):
  """-> the repeated literal, or None.  Pools nested antecedents (memo §4.3)."""
  node = _strip(node)
  # a malformed implies (the model wrote one arm, or none) is a shape problem
  # for `check_atoms` to report, not something to crash on here
  if not (isinstance(node, list) and len(node) >= 3
          and node[0] == "implies"):
    return None
  body, head = node[1], node[2]
  got = []
  _literals(_strip(body), got)
  premises = list(premises) + got
  deeper = _tautology_of(head, premises)
  if deeper:
    return deeper
  conclusions = []
  _literals(_strip(head), conclusions)
  for lit in conclusions:
    if lit in premises:
      return lit
  return None


def check_rule_tautology(s2, s1_json=None):
  """A rule or question whose conclusion is one of its own premises.

  Python only, no prover.  mle2-0032's question supposed "a Diamond is not
  valuable" and asked whether a Diamond is not valuable, so it proved True
  from an empty passage.
  """
  issues = []
  for pid, body in packages(s2):
    for node in _walk_implications(body):
      lit = _tautology_of(node, [])
      if lit:
        issues.append(_issue(
            "rule_tautology", pid,
            "%s concludes %s%s, which is already one of its own premises. "
            "The consequent never repeats the antecedent: such a rule is "
            "true of anything and proves nothing."
            % (pid, "not " if lit[0] == "-" else "", lit[1][:80]),
            json.dumps({"package": pid, "literal": lit[1]})))
        break
  return issues


def _walk_implications(node):
  """Every `implies` node of a package, outermost first."""
  out = []
  stack = [node]
  while stack:
    got = stack.pop()
    if not isinstance(got, list) or not got:
      continue
    if got[0] == "implies" and len(got) >= 3:
      out.append(got)
    for sub in got[1:]:
      if isinstance(sub, list):
        stack.append(sub)
  return out


def check_graph(s2, s1_json=None):
  """Every structural check, in one list.

  The atom checks run BEFORE normalization: an entity id in the concept slot
  and a reserved name written with a space are both invisible once the name
  has been lowercased and underscored.
  """
  issues = list(check_atoms(s2, s1_json))
  normalize_in_place(s2)
  issues.extend(check_packages(s2, s1_json))
  issues.extend(check_free_variables(s2))
  issues.extend(check_lexical_negatives(s2))
  issues.extend(check_shape_consistency(s2))
  issues.extend(check_question_restatement(s2))
  # WP4.2: the translator checks, each with one corrective retry
  issues.extend(check_kind_class_consistency(s2, s1_json))
  issues.extend(check_monolith_names(s2, s1_json))
  issues.extend(check_near_duplicate_names(s2, s1_json))
  issues.extend(check_question_reuse(s2, s1_json))
  issues.extend(check_existential_units(s2, s1_json))
  issues.extend(check_question_entity(s2, s1_json))
  issues.extend(check_hedge_rule(s2, s1_json))
  issues.extend(check_rule_tautology(s2, s1_json))
  return issues


def check_english(s2, s1_json=None, with_inventory=False):
  """The checks of the English-only arms.

  Their unit ids are the model's own, so no package check reads Stage 1; the
  entity ids are checked only when the arm was given the inventory.
  """
  issues = list(check_atoms(s2, s1_json if with_inventory else None))
  normalize_in_place(s2)
  issues.extend(check_packages(s2, None))
  issues.extend(check_free_variables(s2))
  issues.extend(check_lexical_negatives(s2))
  issues.extend(check_shape_consistency(s2))
  issues.extend(check_question_restatement(s2))
  # WP4.2: the translator checks, each with one corrective retry
  issues.extend(check_kind_class_consistency(s2, s1_json))
  issues.extend(check_monolith_names(s2, s1_json))
  issues.extend(check_near_duplicate_names(s2, s1_json))
  issues.extend(check_question_reuse(s2, s1_json))
  issues.extend(check_existential_units(s2, s1_json))
  issues.extend(check_question_entity(s2, s1_json))
  issues.extend(check_hedge_rule(s2, s1_json))
  issues.extend(check_rule_tautology(s2, s1_json))
  return issues


def checker(s1_json=None):
  """-> a `check_fn(parsed)` for `llmparse._run_stage`."""
  def go(parsed):
    return check_graph(parsed, s1_json)
  return go


# ------------------------------------------------------------------- the call

def translate(s1_json, llm=None, version=None, tokens=None, think=None,
              stats=None, correction=None):
  """-> (the graph Stage 2, the raw reply, an error or None).

  The user message is `json.dumps(s1_json)`, byte for byte what the ordinary
  Stage 2 sees, so the cache key differs only by the system prompt.  A
  `correction` is appended to that message: the corrective retry must reach
  the model, and a message identical to the first would only return the first
  reply out of the cache.
  """
  import llmparse
  stats = stats if stats is not None else llmparse._make_stats()
  message = json.dumps(s1_json)
  if correction:
    message = "%s\n\n%s" % (message, correction)
  return llmparse._run_stage(2, message, sysprompt(), llm, version,
                             tokens, think, stats,
                             check_fn=checker(s1_json))


def english_user_message(text, entity_rows=None):
  """The user message of the English-only arms."""
  if entity_rows is None:
    return text
  lines = ["Use exactly these entity ids, and no others:"]
  for row in entity_rows:
    lines.append("  %s   type %s, category %s"
                 % (row["id"], row.get("type"), row.get("category")))
  return "%s\n\n%s" % (text, "\n".join(lines))


def translate_english(text, entity_rows=None, llm=None, version=None,
                      tokens=None, think=None, stats=None, s1_json=None):
  """Phase-A arms 2 and 3: the English, with or without the entity inventory.

  Study code.  The unit ids are the model's own, so the checks verify entity
  ids only when the inventory was supplied.
  """
  import llmparse
  stats = stats if stats is not None else llmparse._make_stats()
  def go(parsed):
    return check_english(parsed, s1_json, entity_rows is not None)

  return llmparse._run_stage(2, english_user_message(text, entity_rows),
                             onestage_sysprompt(), llm, version, tokens, think,
                             stats, check_fn=go)


# ------------------------------------------------------------- measurements

def align_units(s2, s1_json):
  """Match the output's package ids to Stage-1 unit ids by text overlap.

  Arms 2 and 3 mint their own unit ids, so a Phase-A measurement that counts
  represented units needs this; arm 1 matches by identity.
  """
  want = [uid for uid, _u, _r in stage1_units(s1_json)]
  got = [pid for pid, _b in packages(s2)]
  if set(got) <= set(want):
    return dict((p, p) for p in got)
  out = {}
  for i, pid in enumerate(got):
    out[pid] = want[i] if i < len(want) else None
  return out


def align_packages_to_stage1(s2, s1_json):
  """Renumber an English-only arm's package ids onto Stage-1 unit ids.

  Arms 2 and 3 mint their own `S1..Sn`, and the converter decides what is a
  question from the Stage-1 unit type, so a question package landing on a
  Stage-1 assertion unit loses the question entirely.  The packages are matched
  in order — the question package to a Stage-1 query unit, the rest to the
  remaining units — which is the same order-based alignment `align_units`
  measures with.  A package with no Stage-1 unit left keeps a fresh id of its
  own.  Arm 1 never needs this: it is given the Stage-1 ids.

  -> (the renumbered Stage 2, the mapping, what could not be matched).
  """
  import copy
  want = [uid for uid, _u, _r in stage1_units(s1_json)]
  queries = question_unit_ids(s1_json)
  free = [u for u in want if u not in queries]
  asked = set(question_packages(s2))
  mapping, unmatched = {}, []
  qi = fi = 0
  spare = 0
  for pid, _body in packages(s2):
    if pid in asked and qi < len(queries):
      mapping[pid] = queries[qi]
      qi += 1
    elif pid not in asked and fi < len(free):
      mapping[pid] = free[fi]
      fi += 1
    else:
      spare += 1
      new = "G%d" % spare
      while new in want:
        spare += 1
        new = "G%d" % spare
      mapping[pid] = new
      unmatched.append(pid)
  out = copy.deepcopy(s2)
  for item in out[1:]:
    if isinstance(item, list) and len(item) >= 2 and item[0] == "@id":
      item[1] = mapping.get(item[1], item[1])
  return out, mapping, unmatched


def measure(s2, s1_json, issues_before=(), issues_after=()):
  """The per-case Phase-A record of one translation."""
  rows = atoms_of(s2)
  names = [name_of(a) for _p, a, _pa, _pol, _b in rows
           if isinstance(name_of(a), str)]
  concepts = [name_of(a) for _p, a, _pa, _pol, _b in rows
              if kind_of(a) == "concept" and isinstance(name_of(a), str)]
  relations = [name_of(a) for _p, a, _pa, _pol, _b in rows
               if kind_of(a) == "relation" and a[0] not in ROLES]
  events = _event_variables(rows)
  units = align_units(s2, s1_json)
  want = [uid for uid, _u, _r in stage1_units(s1_json)]
  covered = set(v for v in units.values() if v)
  vague = [n for n in names
           if n in VAGUE_NAMES or _VAGUE_NUMBERED.match(str(n))]
  negations = sum(1 for _p, _a, _pa, pol, _b in rows if pol < 0)
  quantified = sum(1 for _p, _a, _pa, _pol, b in rows if b)
  return {
      "packages": len(packages(s2)),
      "stage1_units": len(want),
      "units_represented": len(covered),
      "units_missing": [u for u in want if u not in covered],
      "atoms": len(rows),
      "concept_atoms": len(concepts), "relation_atoms": len(relations),
      "role_atoms": sum(1 for _p, a, _pa, _pol, _b in rows if a[0] in ROLES),
      "reified_events": len(events),
      "distinct_names": len(set(names)),
      "mean_name_tokens": round(
          sum(len(str(n).split("_")) for n in names) / float(len(names) or 1),
          2),
      "mean_name_chars": round(
          sum(len(str(n)) for n in names) / float(len(names) or 1), 2),
      "vague_names": sorted(set(vague)), "vague_name_count": len(vague),
      "negated_atoms": negations,
      "quantified_atoms": quantified,
      "question_packages": question_packages(s2),
      "entity_ids_used": sorted(set(
          t for _p, a, _pa, _pol, _b in rows for t in participants(a)
          if _looks_like_entity_id(t))),
      "issues_before_retry": [i.kind for i in issues_before],
      "issues_after_retry": [i.kind for i in issues_after],
      "shape_inconsistency_before": sum(
          1 for i in issues_before if i.kind == "shape_inconsistency"),
      "shape_inconsistency_after": sum(
          1 for i in issues_after if i.kind == "shape_inconsistency"),
      "question_restated_after": sum(
          1 for i in issues_after if i.kind == "question_restated"),
  }
