"""Which name pairs are worth judging, and which code refuses outright.

Enumeration is the design's own hypothesis: a bridge that can enter a proof of
this question connects something the theory supplies to something a proof of
the question still demands, so the frontier is computed from the compiled
clauses and every frontier pair is judged.  Exhaustive same-kind pairs come
second, under a size limit, and a holistic proposal call third.

Nine shapes are enumerated (design plan §8.5).  Each pair carries the exact
atoms it was built from, with display variables already in place, so the judge
sees a readable occurrence and `graph_judge` can serialize a label into a rule
without re-deriving anything.

The filters are the Set U lesson: the wrong proofs of the literal-bridge run
came from converses of passage-stated relations, from bridges whose body only
the question mentions, from question restatements and from gradable adjectives
compared across two comparison classes.  Each refusal is recorded with its
reason; none is silent.
"""

import hashlib
import re

import graph_inventory as GI

VERSION = "graph_pairs/2026-08-16"

CONCEPT = "isa"
RELATION = "is rel2"

VAR_X, VAR_Y, VAR_Z = "?X", "?Y", "?Z"

# above this many unordered same-kind pairs the exhaustive source is replaced
# by a token-overlap fill and every unjudged pair is recorded
EXHAUSTIVE_LIMIT = 120
BATCH = 40
SALT = "graph_pairs_2026_08_16_v1"

# shapes
CONCEPT_CONCEPT = "concept_concept"
RELATION_RELATION = "relation_relation"
RELATION_INVERSE = "relation_inverse"
RELATION_CONSTANTS = "relation_constants"
ARGUMENT_SUBSUMPTION = "argument_subsumption"
CROSS_FORWARD = "cross_kind_forward"
CROSS_REVERSE = "cross_kind_reverse"
CROSS_ON_CONSTANT = "cross_kind_on_constant"
COMPOSITION = "composition"

SINGLE_LITERAL_SHAPES = (CONCEPT_CONCEPT, RELATION_RELATION, RELATION_INVERSE,
                         RELATION_CONSTANTS, ARGUMENT_SUBSUMPTION,
                         CROSS_FORWARD, CROSS_REVERSE)

# refusal reasons
PASSAGE_RELATED = "passage_related_pair"
QUESTION_ONLY = "question_only_body_name"
QUESTION_RESTATEMENT = "question_restatement"
POLARITY = "polarity_against_the_passage"
GRADABLE = "gradable_adjective_across_classes"
CLASS_TO_ADJECTIVE = "class_to_adjective_relative_to_it"
ENTITY_NAME = "entity_name_pseudo_class"
SAME_NAME = "the_two_names_are_the_same"
ALREADY_KNOWN = "already_known"

_GRADABLE = re.compile(r"^(.+?)_for_an?_(.+)$")


# ------------------------------------------------------------------ helpers

def concept_atom(name, term=VAR_X):
  return [CONCEPT, name, term]


def relation_atom(name, left=VAR_X, right=VAR_Y):
  return [RELATION, name, left, right]


def _pair_id(n):
  return "P%d" % n


def _readable(atom):
  """A one-line reading of an atom for a judge batch."""
  if not atom:
    return ""
  if atom[0] == CONCEPT:
    return "isa(%s, %s)" % (atom[1], atom[2])
  if atom[0] == RELATION:
    return "%s(%s, %s)" % (atom[1], atom[2], atom[3])
  return "%s(%s)" % (atom[0], ", ".join(str(x) for x in atom[1:]))


def _occurrence_reading(row):
  if row is None or row.get("atom") is None:
    return ""
  atom = row["atom"]
  if atom[0] == CONCEPT:
    text = "isa(%s, %s)" % (atom[1], atom[2])
  else:
    text = "%s(%s, %s)" % (atom[0], atom[1], atom[2])
  return ("NOT " + text) if row.get("sign") == "-" else text


# --------------------------------------------------------------- the shapes

def _mk(shape, a, b, a_literals, b_literals, source, **kw):
  row = {"shape": shape, "a": a, "b": b,
         "a_literals": a_literals, "b_literals": b_literals,
         "source": source,
         "kind": "concept" if shape in (CONCEPT_CONCEPT,
                                        ARGUMENT_SUBSUMPTION) else "relation",
         "a_reading": " AND ".join(_readable(x) for x in a_literals),
         "b_reading": " AND ".join(_readable(x) for x in b_literals),
         "a_sign": "+", "b_sign": "+"}
  row.update(kw)
  return row


def frontier(inventory, sd, question_packages=()):
  """Supply meets demand: every pair a proof of this question could use."""
  out = []
  supply = _by_name(sd["supply"])
  demand = _by_name(sd["demand"])
  seen = set()

  def add(row):
    key = (row["shape"], row["a"], row["b"],
           row.get("a_constant"), row.get("b_constant"),
           row.get("relation"))
    if key in seen:
      return
    seen.add(key)
    out.append(row)

  # concept to concept
  for (s_name, s_kind) in sorted(supply):
    for (d_name, d_kind) in sorted(demand):
      if s_name == d_name:
        continue
      if s_kind == "concept" and d_kind == "concept":
        add(_mk(CONCEPT_CONCEPT, s_name, d_name,
                [concept_atom(s_name)], [concept_atom(d_name)], "frontier"))
      elif s_kind == "relation" and d_kind == "relation":
        add(_mk(RELATION_RELATION, s_name, d_name,
                [relation_atom(s_name)], [relation_atom(d_name)], "frontier"))
        add(_mk(RELATION_INVERSE, s_name, d_name,
                [relation_atom(s_name)],
                [relation_atom(d_name, VAR_Y, VAR_X)], "frontier"))
  # relation-with-constant pairs and argument-constant subsumption
  _constant_shapes(inventory, sd, add)
  # grounded cross-kind, both ways
  _cross_kind(inventory, sd, add)
  return out


def _by_name(rows):
  out = {}
  for r in rows:
    out.setdefault((r["name"], r["kind"]), []).append(r)
  return out


def _relation_occurrences(inventory):
  """-> [(name, left, right, sign, package, position)] over open relations."""
  return [(r["name"], r["left"], r["right"], r["sign"], r["package"],
           r["position"]) for r in inventory["relations"]]


def _constant_shapes(inventory, sd, add):
  """`A(X,k1) -> B(X,k2)` and `R(X,k1) -> R(X,k2)`, from occurrences."""
  demand_names = set(n for n, k in sd["demand_names"] if k == "relation")
  supply_names = set(n for n, k in sd["supply_names"] if k == "relation")
  rows = [r for r in inventory["relations"]]
  for s in rows:
    if s["name"] not in supply_names:
      continue
    if not GI.is_kind_constant(s["right"]):
      continue
    for d in rows:
      if d["name"] not in demand_names:
        continue
      if not GI.is_kind_constant(d["right"]):
        continue
      if s["right"] == d["right"] and s["name"] == d["name"]:
        continue
      if s["name"] == d["name"]:
        # argument-constant subsumption: judged as the concept pair (k1, k2)
        add(_mk(ARGUMENT_SUBSUMPTION, s["right"], d["right"],
                [relation_atom(s["name"], VAR_X, s["right"])],
                [relation_atom(d["name"], VAR_X, d["right"])], "frontier",
                relation=s["name"], a_constant=s["right"],
                b_constant=d["right"],
                a_reading=_readable(relation_atom(s["name"], VAR_X,
                                                  s["right"])),
                b_reading=_readable(relation_atom(d["name"], VAR_X,
                                                  d["right"])),
                question=("Is every %s also a %s, in the sense the two atoms "
                          "use them?" % (s["right"], d["right"]))))
      else:
        add(_mk(RELATION_CONSTANTS, s["name"], d["name"],
                [relation_atom(s["name"], VAR_X, s["right"])],
                [relation_atom(d["name"], VAR_X, d["right"])], "frontier",
                a_constant=s["right"], b_constant=d["right"]))


def _cross_kind(inventory, sd, add):
  """`R(X,k) <-> isa(C,X)`, both ways, plus the concept-on-the-constant form."""
  concepts = dict((r["name"], r) for r in inventory["concepts"])
  demand = set(n for n, _k in sd["demand_names"])
  supply = set(n for n, _k in sd["supply_names"])
  for r in inventory["relations"]:
    k = r["right"]
    if not GI.is_kind_constant(k):
      continue
    for cname in sorted(concepts):
      if cname == r["name"]:
        continue
      keyed = GI.shared_root(cname, k) or GI.shared_root(cname, r["name"])
      on_frontier = ((r["name"] in supply and cname in demand)
                     or (cname in supply and r["name"] in demand))
      if not (keyed or on_frontier):
        continue
      add(_mk(CROSS_FORWARD, r["name"], cname,
              [relation_atom(r["name"], VAR_X, k)], [concept_atom(cname)],
              "frontier", a_constant=k, keyed_by_root=keyed))
      add(_mk(CROSS_REVERSE, cname, r["name"],
              [concept_atom(cname)], [relation_atom(r["name"], VAR_X, k)],
              "frontier", b_constant=k, keyed_by_root=keyed,
              stricter_question=True))
  # the concept sits on the constant itself: isa(C,k) AND G(X) -> R(X,k)
  for r in inventory["relations"]:
    k = r["right"]
    if not GI.is_kind_constant(k):
      continue
    if r["name"] not in demand:
      continue
    guard = _guard_of(inventory, r)
    if guard is None:
      continue
    for row in inventory["concepts"]:
      if row["participant"] != k:
        continue
      add(_mk(CROSS_ON_CONSTANT, row["name"], r["name"],
              [concept_atom(row["name"], k), concept_atom(guard, VAR_X)],
              [relation_atom(r["name"], VAR_X, k)], "frontier",
              b_constant=k, guard=guard))


def _guard_of(inventory, relation_row):
  """The class guard the demanding rule or question already puts on `X`."""
  subject = relation_row["left"]
  for row in inventory["concepts"]:
    if row["package"] == relation_row["package"] \
            and row["participant"] == subject and row["sign"] == "+":
      return row["name"]
  return None


def exhaustive(inventory, already, limit=EXHAUSTIVE_LIMIT):
  """Every unordered same-kind pair, when there are few enough of them."""
  concepts = sorted(set(inventory["concept_names"])
                    | set(inventory["kind_constant_names"]))
  relations = sorted(set(inventory["relation_names"]))
  total = _n_pairs(len(concepts)) + _n_pairs(len(relations))
  seen = set((r["shape"], r["a"], r["b"]) for r in already)
  out, skipped = [], []
  rows = []
  for i, a in enumerate(concepts):
    for b in concepts[i + 1:]:
      rows.append((CONCEPT_CONCEPT, a, b))
  for i, a in enumerate(relations):
    for b in relations[i + 1:]:
      rows.append((RELATION_RELATION, a, b))
  if total > limit:
    rows.sort(key=lambda r: (-GI.overlap(r[1], r[2]), r[1], r[2]))
    keep, rest = rows[:limit], rows[limit:]
    skipped = [{"shape": s, "a": a, "b": b,
                "why": "beyond the %d same-kind pairs an exhaustive source may "
                       "judge; the pairs kept are the ones with the highest "
                       "token overlap" % limit}
               for s, a, b in rest]
    rows = keep
  for shape, a, b in rows:
    if (shape, a, b) in seen or (shape, b, a) in seen:
      continue
    if shape == CONCEPT_CONCEPT:
      out.append(_mk(shape, a, b, [concept_atom(a)], [concept_atom(b)],
                     "exhaustive"))
    else:
      out.append(_mk(shape, a, b, [relation_atom(a)], [relation_atom(b)],
                     "exhaustive"))
  return out, skipped, total


def _n_pairs(n):
  return n * (n - 1) // 2


def composition(inventory, sd):
  """`R1(a,b) AND R2(b,c) -> R3(a,c)`, only where the theory has the chain."""
  out, seen = [], set()
  demand = set(n for n, k in sd["demand_names"] if k == "relation")
  rows = inventory["relations"]
  for r1 in rows:
    for r2 in rows:
      if r1 is r2:
        continue
      if r1["right"] != r2["left"]:
        continue
      for r3 in sorted(demand):
        if r3 in (r1["name"], r2["name"]):
          continue
        key = (r1["name"], r2["name"], r3)
        if key in seen:
          continue
        seen.add(key)
        out.append(_mk(
            COMPOSITION, "%s o %s" % (r1["name"], r2["name"]), r3,
            [relation_atom(r1["name"], VAR_X, VAR_Y),
             relation_atom(r2["name"], VAR_Y, VAR_Z)],
            [relation_atom(r3, VAR_X, VAR_Z)], "composition",
            middle=r1["right"],
            chain_atoms=[_readable([RELATION, r1["name"], r1["left"],
                                    r1["right"]]),
                         _readable([RELATION, r2["name"], r2["left"],
                                    r2["right"]])]))
  return out


# ---------------------------------------------------------------- the filters

def entity_pseudo_classes(s1_json):
  """Class names that are a named individual's own name, which never bridge.

  The case is folio-0140's `isa("hachi: a dog's tale", X)`: a title became a
  class and a bridge out of it answered the question.  Two conditions, both
  needed: the entity is CONCRETE (numbered, or typed concrete by Stage 1), and
  its name reads as a proper name (a capital or a colon).  A generic Stage-1
  entity is an ordinary class however it is written — `pure substance` and
  `element` are exactly the names a bridge has to be free to use.
  """
  import graph_stage2 as G2
  out = set()
  for row in G2.stage1_entity_rows(s1_json or []):
    eid = str(row.get("id") or "")
    numbered = bool(re.search(r"\s+\d+$", eid))
    if not (numbered or str(row.get("type") or "").lower() == "concrete"):
      continue                       # a generic class is an ordinary class
    base = re.sub(r"\s+\d+$", "", eid).strip()
    if base and (base[:1].isupper() or ":" in base):
      out.add(GI.comparison_key(base))
  return out


def passage_relations(s2_graph):
  """-> {(A, B): the direction and sign the passage itself states}.

  A pair the passage relates in one unit may only be bridged in that unit's
  own direction and sign.  A pair the passage merely mentions together in a
  fact may not be bridged at all: a universal strengthening of a particular is
  how the literal bridge answered folio-0121 and folio-0140 wrongly.
  """
  import graph_stage2 as G2
  question = set(G2.question_packages(s2_graph))
  by_package = {}
  for pid, atom, path, pol, _b in G2.atoms_of(s2_graph):
    if pid in question or len(atom) != 3:
      continue
    name = G2.name_of(atom)
    if not isinstance(name, str):
      continue
    by_package.setdefault(pid, []).append(
        {"name": name, "polarity": pol, "path": path,
         "position": GI._position(path, False)})
  out = {}
  for pid, rows in by_package.items():
    for a in rows:
      for b in rows:
        if a["name"] == b["name"]:
          continue
        key = (a["name"], b["name"])
        if a["position"] == GI.RULE_BODY and b["position"] == GI.RULE_HEAD:
          out.setdefault(key, []).append(
              {"package": pid, "direction": "a_implies_b",
               "sign": "+" if b["polarity"] > 0 else "-"})
        elif a["position"] == b["position"]:
          out.setdefault(key, []).append(
              {"package": pid, "direction": "same_position",
               "sign": "+" if b["polarity"] > 0 else "-"})
  return out


def refuse(pair, context, policy_strict=True):
  """-> a refusal reason, or None.  Applied before and after the judge."""
  a, b = pair["a"], pair["b"]
  if a == b and pair["shape"] != ARGUMENT_SUBSUMPTION:
    return SAME_NAME
  keys = context.get("entity_pseudo_classes") or set()
  if GI.comparison_key(a) in keys or GI.comparison_key(b) in keys:
    return ENTITY_NAME
  ga, gb = _GRADABLE.match(str(a)), _GRADABLE.match(str(b))
  if ga and gb and ga.group(1) == gb.group(1) and ga.group(2) != gb.group(2):
    return GRADABLE
  if gb and GI.comparison_key(gb.group(2)) == GI.comparison_key(a):
    return CLASS_TO_ADJECTIVE
  if ga and GI.comparison_key(ga.group(2)) == GI.comparison_key(b):
    return CLASS_TO_ADJECTIVE
  # §8.9 refuses a bridge whose BODY name occurs only in the question.  The
  # head being a question-only name is what a frontier pair is for: the
  # question asks about a name the passage never states, and the bridge has to
  # conclude it.  So the pair is refused only when neither direction is usable,
  # and the direction itself is checked at serialization.
  only_question = set(context.get("question_only_names") or ())
  if a in only_question and b in only_question:
    return QUESTION_ONLY
  question_names = set(context.get("question_names") or ())
  sole = set(context.get("question_subject_sole_class") or ())
  if b in question_names and a in sole:
    return QUESTION_RESTATEMENT
  if not policy_strict:
    return _contradiction_only(pair, context)
  related = context.get("passage_relations") or {}
  rows = related.get((a, b)) or []
  if rows:
    if any(r["direction"] == "same_position" for r in rows):
      return PASSAGE_RELATED
    if all(r["direction"] == "a_implies_b" and r["sign"] == "+"
           for r in rows):
      return ALREADY_KNOWN
  if related.get((b, a)):
    return PASSAGE_RELATED
  return _contradiction_only(pair, context)


def _contradiction_only(pair, context):
  """The refusals that hold whatever the background-knowledge policy is."""
  a, b = pair["a"], pair["b"]
  negative = context.get("negative_relations") or set()
  if (a, b) in negative or (b, a) in negative:
    return POLARITY
  return None


def negative_relations(s2_graph):
  """-> {(A, B)} the theory states as `A -> not B` or `B -> not A`."""
  import graph_stage2 as G2
  out = set()
  question = set(G2.question_packages(s2_graph))
  by_package = {}
  for pid, atom, path, pol, _b in G2.atoms_of(s2_graph):
    if pid in question or len(atom) != 3:
      continue
    name = G2.name_of(atom)
    if isinstance(name, str):
      by_package.setdefault(pid, []).append(
          (name, pol, GI._position(path, False)))
  for rows in by_package.values():
    bodies = [n for n, pol, pos in rows if pos == GI.RULE_BODY and pol < 0]
    heads = [n for n, pol, pos in rows if pos == GI.RULE_HEAD and pol < 0]
    for x in bodies:
      for y in heads:
        if x != y:
          out.add((x, y))
          out.add((y, x))
  return out


def context_for(s2_graph, s1_json, inventory, sd):
  """Everything the filters read, computed once per case."""
  import graph_stage2 as G2
  qp = G2.question_packages(s2_graph)
  question_names, subjects = [], set()
  for pid, atom, _path, _pol, bound in G2.atoms_of(s2_graph):
    if pid not in qp or len(atom) != 3:
      continue
    name = G2.name_of(atom)
    if isinstance(name, str):
      question_names.append(name)
    # only a CONSTANT is a question subject: a bound variable matches every
    # class in the case, and reading it as a subject refuses the whole frontier
    subjects.update(t for t in G2.participants(atom)
                    if isinstance(t, str) and not GI.is_variable(t, bound))
  classes_of = {}
  for row in inventory["concepts"]:
    if row["package"] not in qp and row["participant"] in subjects:
      classes_of.setdefault(row["participant"], set()).add(row["name"])
  # the refused shape is `the subject's ONLY known class -> a question name`
  # (folio-0144, core-0026); a subject with two stated classes is not it
  sole = set(next(iter(v)) for v in classes_of.values() if len(v) == 1)
  return {"question_packages": qp,
          "question_names": sorted(set(question_names)),
          "question_subjects": sorted(subjects),
          "question_subject_classes": sorted(
              set(n for v in classes_of.values() for n in v)),
          "question_subject_sole_class": sorted(sole),
          "question_only_names": GI.names_only_in_the_question(inventory, qp),
          "passage_relations": passage_relations(s2_graph),
          "negative_relations": negative_relations(s2_graph),
          "entity_pseudo_classes": entity_pseudo_classes(s1_json)}


# ----------------------------------------------------------------- assembly

def enumerate_pairs(s2_graph, s1_json, inventory, sd, sources=("frontier",),
                    policy_strict=True, limit=EXHAUSTIVE_LIMIT):
  """-> (the pairs to judge, the refusals, a per-source note).

  `sources` is any of `frontier`, `exhaustive`, `composition`; the holistic
  call is a separate source and does not enumerate pairs.
  """
  context = context_for(s2_graph, s1_json, inventory, sd)
  rows, note = [], {}
  if "frontier" in sources:
    rows.extend(frontier(inventory, sd, context["question_packages"]))
    note["frontier"] = len(rows)
  if "exhaustive" in sources:
    more, skipped, total = exhaustive(inventory, rows, limit)
    rows.extend(more)
    note["exhaustive"] = len(more)
    note["exhaustive_pairs_possible"] = total
    note["unjudged_pairs"] = skipped
  if "composition" in sources:
    more = composition(inventory, sd)
    rows.extend(more)
    note["composition"] = len(more)
  kept, refused = [], []
  only_question = set(context.get("question_only_names") or ())
  for row in rows:
    why = refuse(row, context, policy_strict)
    if why:
      refused.append(dict(row, refused=why))
    else:
      # which side may not be a rule body, checked when the label is serialized
      row["question_only_sides"] = [side for side, name
                                    in (("a", row["a"]), ("b", row["b"]))
                                    if name in only_question]
      kept.append(row)
  for i, row in enumerate(order(kept), start=1):
    row["pair_id"] = _pair_id(i)
  note["kept"] = len(kept)
  note["refused"] = len(refused)
  note["policy_strict"] = policy_strict
  return kept, refused, note, context


def order(rows, salt=SALT):
  """A frozen salted order, so a position effect is measurable."""
  def key(row):
    blob = "%s|%s|%s|%s" % (salt, row["shape"], row["a"], row["b"])
    return hashlib.sha256(blob.encode()).hexdigest()
  return sorted(rows, key=key)


def batches(rows, size=BATCH):
  return [rows[i:i + size] for i in range(0, len(rows), size)]
