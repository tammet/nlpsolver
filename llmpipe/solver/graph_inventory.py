"""What names the graph theory holds, where each occurs, and what it needs.

Three views, all computed, none asked of a model:

  * an occurrence inventory over the validated graph Stage 2 — every concept
    and every relation with its participants, sign, package and position;
  * a comparison view, one deterministic normalization of a name into tokens,
    used wherever two names are ranked against each other;
  * supply and demand, read from the compiled clauses: what the theory can
    prove and what a proof of the question still needs.

Supply and demand are the mechanical part of the proof frontier.  A question
clause's content literals are demand.  A rule clause's negative literals are
demand unless the same literal occurs positively somewhere.  Facts and rule
conclusions are supply.  A question clause is one the converter marked as such,
whether it carries `@question` or the `$defq` encoding a generic question gets.
"""

import re
import unicodedata

VERSION = "graph_inventory/2026-08-16"

CONCEPT = "isa"
RELATION = "is rel2"

FACT = "fact"
RULE_BODY = "rule_body"
RULE_HEAD = "rule_head"
QUESTION = "question"

VALUE = re.compile(r"^-?\d+([.,]\d+)?$")
ENTITY_ID = re.compile(r"^.+\s+\d+$")
SPLIT = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------- comparison view

def tokens(name):
  """NFC, lowercase, underscores to spaces, punctuation split, no stemming."""
  if not isinstance(name, str):
    return []
  text = unicodedata.normalize("NFC", name).lower().replace("_", " ")
  return [t for t in SPLIT.split(text) if t]


def comparison_key(name):
  return " ".join(tokens(name))


def overlap(a, b):
  """Jaccard overlap of two names' tokens.  Deterministic, no model."""
  ta, tb = set(tokens(a)), set(tokens(b))
  if not ta or not tb:
    return 0.0
  return round(len(ta & tb) / float(len(ta | tb)), 4)


def shared_root(a, b, floor=4):
  """True when two names share a lexical root of `floor` characters.

  `conductive` / `conductivity`, `class` / `classify`, `inherit` /
  `inherited characteristic`: the first enumeration key of the grounded
  cross-kind shape.
  """
  for x in tokens(a):
    for y in tokens(b):
      if len(x) < floor or len(y) < floor:
        continue
      if x == y or x.startswith(y[:floor]) and y.startswith(x[:floor]):
        return True
  return False


# --------------------------------------------------------- term classification

def is_variable(term, bound=()):
  return isinstance(term, str) and (term in bound
                                    or bool(re.match(r"^[A-Z][A-Za-z0-9_]*$",
                                                     term)))


def is_value(term):
  return isinstance(term, str) and bool(VALUE.match(term.strip()))


def is_entity_id(term, known=()):
  return isinstance(term, str) and (term in known or bool(ENTITY_ID.match(term)))


def is_kind_constant(term, known=(), bound=()):
  """A constant that names a kind, not an entity and not a value.

  `food`, `labeled_data`, `electrical_energy`.  These enter the concept
  inventory as names, so `requires(X, labeled_data)` can meet
  `isa(supervised, X)` and `R(X,k1) -> R(X,k2)` can be judged as a concept
  pair.
  """
  if not isinstance(term, str) or not term:
    return False
  if is_variable(term, bound) or is_value(term) or is_entity_id(term, known):
    return False
  return not term.startswith("$")


# ------------------------------------------------------------- the inventory

def _position(path, is_question):
  if is_question:
    return QUESTION
  if "implies:body" in path:
    return RULE_BODY
  if "implies:head" in path:
    return RULE_HEAD
  return FACT


def build(s2_graph, s1_json=None):
  """-> the occurrence inventory of one graph Stage 2."""
  import graph_stage2 as G2
  known = G2.stage1_entity_ids(s1_json) if s1_json else set()
  question = set(G2.question_packages(s2_graph))
  concepts, relations, roles, kinds = [], [], [], {}
  for pid, atom, path, pol, bound in G2.atoms_of(s2_graph):
    if len(atom) != 3 or not isinstance(atom[0], str):
      continue
    name = G2.name_of(atom)
    if not isinstance(name, str):
      continue
    row = {"name": name, "key": comparison_key(name),
           "package": pid, "path": path,
           "sign": "+" if pol > 0 else "-",
           "position": _position(path, pid in question),
           "bound": list(bound), "atom": atom}
    if atom[0] == CONCEPT:
      row["participant"] = atom[2]
      row["kind"] = "concept"
      concepts.append(row)
    elif atom[0] in G2.ROLES:
      row["left"], row["right"] = atom[1], atom[2]
      row["kind"] = "role"
      row["role"] = True
      roles.append(row)
    else:
      row["left"], row["right"] = atom[1], atom[2]
      row["kind"] = "relation"
      row["role"] = False
      relations.append(row)
    for term in G2.participants(atom):
      if is_kind_constant(term, known, bound):
        kinds.setdefault(term, []).append(row["package"])
  kind_rows = [{"name": k, "key": comparison_key(k), "kind": "concept",
                "kind_constant": True, "packages": sorted(set(v)),
                "participant": None, "sign": "+", "position": FACT,
                "path": "", "package": sorted(set(v))[0], "bound": [],
                "atom": None}
               for k, v in sorted(kinds.items())]
  return {"version": VERSION,
          "concepts": concepts, "relations": relations, "roles": roles,
          "kind_constants": kind_rows,
          "concept_names": sorted(set(r["name"] for r in concepts)),
          "relation_names": sorted(set(r["name"] for r in relations)),
          "kind_constant_names": sorted(kinds),
          "role_names": sorted(set(r["name"] for r in roles)),
          "counts": {"concept_occurrences": len(concepts),
                     "relation_occurrences": len(relations),
                     "role_occurrences": len(roles),
                     "concept_names": len(set(r["name"] for r in concepts)),
                     "relation_names": len(set(r["name"] for r in relations)),
                     "kind_constants": len(kinds)}}


def example_atom(inventory, name, kind=None):
  """One readable occurrence of a name, for a judge batch."""
  pools = ([inventory["concepts"]] if kind == "concept"
           else [inventory["relations"]] if kind == "relation"
           else [inventory["concepts"], inventory["relations"]])
  for pool in pools:
    for row in pool:
      if row["name"] == name:
        return row
  for row in inventory["kind_constants"]:
    if row["name"] == name:
      return row
  return None


def packages_of(inventory, name):
  out = set()
  for pool in ("concepts", "relations", "kind_constants"):
    for row in inventory[pool]:
      if row["name"] == name:
        if row.get("kind_constant"):
          out.update(row.get("packages") or [])
        else:
          out.add(row["package"])
  return sorted(out)


def names_only_in_the_question(inventory, question_packages):
  """Names no passage package states.  §8.9 refuses a bridge body among them."""
  q = set(question_packages)
  out = []
  for name in set(inventory["concept_names"]) | set(
          inventory["relation_names"]):
    if set(packages_of(inventory, name)) <= q:
      out.append(name)
  return sorted(out)


# ------------------------------------------------------- supply and demand

def _literals(clause):
  body = clause.get("@logic") if "@logic" in clause else clause.get("@question")
  if body is None:
    return []
  if isinstance(body, list) and body and isinstance(body[0], str):
    return [body]
  return [l for l in body if isinstance(l, list)]


def _open_name(literal):
  if not (isinstance(literal, list) and literal
          and isinstance(literal[0], str)):
    return None, None
  head = literal[0].lstrip("-")
  sign = "-" if literal[0].startswith("-") else "+"
  if head == CONCEPT and len(literal) > 1 and isinstance(literal[1], str):
    return literal[1], sign
  if head == RELATION and len(literal) > 1 and isinstance(literal[1], str):
    return literal[1], sign
  return None, sign


def _kind_of_literal(literal):
  head = literal[0].lstrip("-") if literal and isinstance(literal[0],
                                                          str) else ""
  return "concept" if head == CONCEPT else "relation"


def supply_demand(clauses):
  """-> {'supply': [...], 'demand': [...]}, read from the compiled clauses.

  A control literal (`$block` and friends) is not content and is skipped.

  A population witness is not supply.  The converter emits `isa(C, $some_C)`
  for every class it quantifies over, so counting it would make every rule
  premise look satisfied and leave the frontier empty.
  """
  positive, rows = {}, []
  for clause in clauses or []:
    if clause.get("@sourcetype") == "populate":
      continue
    # a generic question is encoded as several `$defq` clauses that carry
    # `@logic`, not `@question`; reading only the `@question` clause would put
    # every question literal on the supply side and leave the frontier empty
    is_q = "@question" in clause or clause.get("@sourcetype") == "question"
    lits = _literals(clause)
    for lit in lits:
      name, sign = _open_name(lit)
      if not name:
        continue
      rows.append({"clause": clause.get("@name"), "question": is_q,
                   "literal": lit, "name": name, "sign": sign,
                   "kind": _kind_of_literal(lit),
                   "population": clause.get("@sourcetype") == "populate",
                   "arity": len(lit)})
      if sign == "+" and not is_q:
        positive.setdefault((name, _kind_of_literal(lit)), []).append(
            clause.get("@name"))
  supply, demand = [], []
  for row in rows:
    key = (row["name"], row["kind"])
    if row["question"]:
      demand.append(dict(row, why="a literal of the question clause"))
    elif row["sign"] == "-":
      if key not in positive:
        demand.append(dict(row, why="an unsupplied premise of a rule clause"))
    else:
      supply.append(dict(row, why="a fact or a rule conclusion"))
  return {"supply": supply, "demand": demand,
          "supply_names": sorted(set((r["name"], r["kind"]) for r in supply)),
          "demand_names": sorted(set((r["name"], r["kind"]) for r in demand)),
          "counts": {"supply": len(supply), "demand": len(demand),
                     "supply_names": len(set(r["name"] for r in supply)),
                     "demand_names": len(set(r["name"] for r in demand))}}


def demand_complement(sd, inventory):
  """Names that are neither demanded nor supplied.

  §8.6 enumerates a supplied name against these too, so a supplied `city` can
  meet a `state` with `EXCLUSIVE`.
  """
  used = set(n for n, _k in sd["supply_names"]) | set(
      n for n, _k in sd["demand_names"])
  every = set(inventory["concept_names"]) | set(inventory["relation_names"])
  return sorted(every - used)


def summary(inventory, sd):
  return {"concept_names": inventory["counts"]["concept_names"],
          "relation_names": inventory["counts"]["relation_names"],
          "kind_constants": inventory["counts"]["kind_constants"],
          "supply_names": sd["counts"]["supply_names"],
          "demand_names": sd["counts"]["demand_names"]}
