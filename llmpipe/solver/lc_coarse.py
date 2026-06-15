# Flat-event ("coarse") and relational ("ultracoarse") encoding passes.
#
# -coarse: replace a collapsible Davidsonian event with one combined literal
#   ["do", TYPE, ACTOR, TARGET, RECIPIENT]
# folding the role spine and dropping the event variable.  Collapsible = no
# modal classifier, not a has_content nest, only template roles {type, actor,
# target, recipient} (a tense-valued has_time is tolerated and dropped to $ctxt;
# tense lives in the $ctxt term that lc_ctxt attaches to "do").
#
# -ultracoarse: everything -coarse does, plus, to match FOLIO-style atomic
# relations that must unify across a rule and the question:
#   (1) an event with an actor and exactly one object role
#       {target, beneficiary, source, recipient} folds to the binary relation
#       ["is rel2", VERB, ACTOR, OBJECT];
#   (2) a habitual event (the `typical` classifier) is allowed to fold, with the
#       classifier stripped, so "X plays for Y" in a rule and in the question
#       reduce to the same literal.
# Other modal classifiers (capability/necessity/...) and has_content nests still
# block folding.  Both passes attach $ctxt to "do"/"is rel2" exactly as to the
# reified roles, so the encodings differ only in the folded spine.
#
# Gated by options["coarse_flag"] / options["ultracoarse_flag"]; called from
# logconvert.rawlogic_convert after inject_actuality and tense-has_time stripping.

import re, itertools, collections

from lc_rewrites import (
  _collect_content_inner_vars,
  _MODAL_CLASSIFIERS,
)

_TEMPLATE_ROLES = ("has type", "has actor", "has target", "has recipient")
_OBJECT_ROLES = ("has target", "has beneficiary", "has source", "has recipient")
_TENSES = ("past", "present", "future")


# ---- (ultracoarse) entity-constant canonicalization -----------------------
# The same named entity is sometimes split across mentions ("Bayern Munchen"
# vs "FC Bayern Munich", "2008 Summer Olympics" vs "...Olympic Games"), so
# facts about it never unify with the question.  Ideally Stage 1 would unify
# these; failing that, merge programmatically by (a) sharing a type and (b)
# very similar surface form.  Only PROPER-noun entities are merged, so distinct
# indefinites ("a bear" ... "a bear" -> bear 1, bear 2) are never collapsed.

def _strip_num(s):
  return re.sub(r"\s+\d+$", "", s).strip()

def _is_proper(s):
  base = _strip_num(s)
  return bool(re.search(r"[A-Z]", base)) or bool(re.search(r"\d{3,4}", base))

def _ent_tokens(s):
  toks = re.findall(r"[a-z0-9]+", _strip_num(s).lower())
  return {t[:-1] if len(t) > 3 and t.endswith("s") else t for t in toks}

def _jaccard(a, b):
  return len(a & b) / len(a | b) if (a and b) else 0.0

def _collect_typed_entities(tree, ents):
  if isinstance(tree, list):
    if (len(tree) >= 3 and tree[0] == "isa"
        and isinstance(tree[1], str) and isinstance(tree[2], str)):
      ents.setdefault(tree[2], set()).add(tree[1])
    for x in tree:
      _collect_typed_entities(x, ents)

def _canonicalize_entities(tree):
  ents = {}
  _collect_typed_entities(tree, ents)
  propers = [e for e in ents if _is_proper(e)]
  if len(propers) < 2:
    return tree
  parent = {e: e for e in propers}
  def find(x):
    while parent[x] != x:
      parent[x] = parent[parent[x]]; x = parent[x]
    return x
  toks = {e: _ent_tokens(e) for e in propers}
  for a, b in itertools.combinations(propers, 2):
    if ents[a] & ents[b] and _jaccard(toks[a], toks[b]) >= 0.6:
      parent[find(b)] = find(a)
  counts = collections.Counter()
  def _count(n):
    if isinstance(n, list):
      for x in n:
        if isinstance(x, str):
          counts[x] += 1
        else:
          _count(x)
  _count(tree)
  groups = collections.defaultdict(list)
  for e in propers:
    groups[find(e)].append(e)
  remap = {}
  for members in groups.values():
    if len(members) < 2:
      continue
    canon = max(members, key=lambda e: (counts[e], len(e)))
    for m in members:
      if m != canon:
        remap[m] = canon
  if not remap:
    return tree
  def _rw(n):
    if isinstance(n, list):
      return [_rw(x) for x in n]
    return remap.get(n, n) if isinstance(n, str) else n
  return _rw(tree)


def _event_var(and_block):
  """If and_block is ["and", ...] introducing isa(activity,E), return E."""
  if not (isinstance(and_block, list) and and_block and and_block[0] == "and"):
    return None
  for c in and_block[1:]:
    if (isinstance(c, list) and len(c) >= 3 and c[0] == "isa"
        and c[1] == "activity" and isinstance(c[2], str)):
      return c[2]
  return None


# ---- (ultracoarse) aggressive Davidsonian-event flattening -----------------
# Every event block (isa(activity,E) & has type(E,V) & ...) collapses to a flat
#   is_rel2(V, subject, object)   or   has property(V, subject)
# mirroring FOLIO's flat n-ary predicates.  Subject = actor; if no actor, the
# highest-priority object role (passive: the patient becomes the subject, e.g.
# FOLIO CanBeSpottedNear(x, campus)).  Object = the highest-priority object role
# not used as subject.  A two-event reification (has content E1 E2) collapses
# the inner content event to its verb as the object ("X wants to fly" ->
# is_rel2(want, X, fly)).  Everything else -- classifiers, has time/manner,
# nested adjuncts, prepositions -- is dropped.

_OBJ_ROLE_PRIORITY = ["has recipient", "has beneficiary", "has target",
                      "has destination", "has location", "has source",
                      "has direction", "has goal", "has topic",
                      "has accompaniment", "has instrument"]

_verb_index = {}    # event var -> its has-type verb, built per coarsen_events run


def _build_verb_index(tree):
  idx = {}
  def walk(n):
    if isinstance(n, list):
      if len(n) >= 3 and n[0] == "has type" and isinstance(n[2], str):
        idx.setdefault(n[1], n[2])
      for x in n:
        walk(x)
  walk(tree)
  return idx


def _collect_event_roles(block, E):
  """Collect (vtype, actor, {obj_role: value}, content_evar) for event var E,
  scanning the whole block (roles can sit in nested exists adjuncts).  Atoms are
  attributed to E by their first argument, so a nested inner event's roles (keyed
  on E2) are naturally excluded."""
  state = {"v": None, "a": None, "c": None}
  objs = {}
  def walk(n):
    if isinstance(n, list) and n and isinstance(n[0], str):
      h = n[0]
      if len(n) >= 3 and n[1] == E:
        if h == "has type":
          state["v"] = n[2]
        elif h == "has actor":
          state["a"] = n[2]
        elif h == "has content":
          state["c"] = n[2]
        elif h in _OBJ_ROLE_PRIORITY:
          objs.setdefault(h, n[2])
      for x in n[1:]:
        walk(x)
    elif isinstance(n, list):
      for x in n:
        walk(x)
  walk(block)
  return state["v"], state["a"], objs, state["c"]


def _typed_existential_vars(block, E):
  """Map each variable bound by a nested `exists V [... isa(TYPE,V) ...]` in the
  block to its isa-type TYPE.  Used to fold a typed-existential role filler
  ("eat salads" = exists Y[isa(salad,Y) & has_target(E,Y)]) to the bare type name
  instead of leaving the inner var stranded as an unbound constant.  Excludes the
  event var E itself; only exists-bound vars qualify, so genuine constants and
  forall vars are never rewritten."""
  exist_vars = set()
  types = {}
  def walk(n):
    if isinstance(n, list) and n:
      if n[0] == "exists" and len(n) >= 2 and isinstance(n[1], str):
        exist_vars.add(n[1])
      if (n[0] == "isa" and len(n) >= 3 and isinstance(n[1], str)
          and isinstance(n[2], str)):
        types.setdefault(n[2], n[1])           # entity -> type
      for x in n:
        walk(x)
  walk(block)
  return {v: t for v, t in types.items() if v in exist_vars and v != E}


def _fold_event_flat(and_block, E, content_inner):
  """(ultracoarse) Aggressively flatten one event block; None if not an event or
  if it is the inner content event of a two-event reification."""
  if E in content_inner:
    return None
  vtype, actor, objs, content = _collect_event_roles(and_block, E)
  if vtype is None:
    return None
  # two-event reification: inner content event -> its verb as the object
  if content is not None and "has target" not in objs:
    inner_verb = _verb_index.get(content)
    if inner_verb is not None:
      objs["has target"] = inner_verb
  present = [r for r in _OBJ_ROLE_PRIORITY if r in objs]
  if actor is not None:
    subject, obj = actor, (objs[present[0]] if present else None)
  elif present:                              # passive: patient becomes subject
    subject = objs[present[0]]
    obj = objs[present[1]] if len(present) > 1 else None
  else:
    return None                              # subject-less event: keep reified
  # Resolve typed-existential role fillers ("Y" with isa(salad,Y)) to the type
  # name, so the folded relation carries a meaningful, cross-sentence-consistent
  # object instead of a stranded inner var.
  typed = _typed_existential_vars(and_block, E)
  if typed:
    if isinstance(subject, str):
      subject = typed.get(subject, subject)
    if isinstance(obj, str):
      obj = typed.get(obj, obj)
  if obj is not None:
    return ["is rel2", vtype, subject, obj]
  return ["has property", vtype, subject]


def _fold_event(and_block, E, content_inner, ultra):
  """Return the folded literal for a collapsible event, or None to keep it.
  Under -ultracoarse this is the aggressive flat fold (every event collapses);
  under plain -coarse it is the conservative collapsible fold below."""
  if ultra:
    return _fold_event_flat(and_block, E, content_inner)
  if E in content_inner:
    return None
  roles = {}
  classifiers = set()
  for c in and_block[1:]:
    if not (isinstance(c, list) and c and isinstance(c[0], str)):
      return None
    h = c[0]
    if h == "isa" and len(c) >= 3 and c[1] == "activity":
      continue
    if h == "actuality":
      continue
    if h in _MODAL_CLASSIFIERS:
      classifiers.add(h)
      continue
    if h == "has content":
      return None
    if h == "has time":
      if len(c) >= 3 and c[1] == E and c[2] in _TENSES:
        continue                          # tense -> $ctxt, drop
      if ultra and len(c) >= 3 and c[1] == E:
        continue                          # (ultracoarse) concrete time -> drop
      return None                         # explicit time -> keep reified
    if h.startswith("has "):
      if len(c) >= 3 and c[1] == E:
        roles[h] = c[2]
      else:
        return None
    else:
      return None                         # any other predicate on E -> keep

  # modal gating: a non-typical classifier always blocks; `typical` blocks
  # under -coarse but is allowed (and stripped) under -ultracoarse.
  if classifiers - {"typical"}:
    return None
  if classifiers and not ultra:
    return None
  if "has type" not in roles:
    return None

  # (ultracoarse) relational fold: actor + exactly one object role -> is_rel2
  if ultra and "has actor" in roles:
    objs = [r for r in _OBJECT_ROLES if r in roles]
    extra = set(roles) - {"has type", "has actor"}
    if len(objs) == 1 and extra == {objs[0]}:
      return ["is rel2", roles["has type"], roles["has actor"], roles[objs[0]]]

  # (ultracoarse) topic fold: "X verbs about Y" — actor + a single has_topic,
  # no object role -> is_rel2(verb, actor, topic), so "jokes about caffeine" in a
  # rule, a disjunct and the question all reduce to the same binary literal.
  if ultra and "has actor" in roles and "has topic" in roles:
    if not set(roles) - {"has type", "has actor", "has topic"}:
      return ["is rel2", roles["has type"], roles["has actor"], roles["has topic"]]

  # (ultracoarse) passive fold: a target but no actor -> drop the over-specified
  # from/at phrase (has source / has location) and treat the verb as a property
  # of the target ("X was suspended from Y" -> has_property(suspend, X)), so a
  # passive in a rule consequent and in the question match regardless of the
  # dropped phrase (case 67: "suspended from office" vs "from the House").
  if ultra and "has actor" not in roles and "has target" in roles:
    if not set(roles) - {"has type", "has target", "has source", "has location"}:
      return ["has property", roles["has type"], roles["has target"]]

  # (ultracoarse) intransitive-achievement fold: a `typical` event with an actor
  # and NO goal role (target/beneficiary/source/recipient) -> has_property(verb,
  # actor), dropping a setting location adjunct ("the good guys always win" ->
  # has_property(win, Y)).  Gated on `typical` so a specific goal-bearing event
  # ("Sarah is going camping in Vermont") is untouched.
  if ultra and "typical" in classifiers and "has actor" in roles:
    if not (set(roles) & set(_OBJECT_ROLES)):
      return ["has property", roles["has type"], roles["has actor"]]

  # (both) do-fold: template roles only
  if set(roles) - set(_TEMPLATE_ROLES):
    return None
  return ["do",
          roles.get("has type", "none"),
          roles.get("has actor", "none"),
          roles.get("has target", "none"),
          roles.get("has recipient", "none")]


def _coarsen_node(node, content_inner, ultra):
  if not isinstance(node, list) or not node:
    return node
  if node[0] == "exists" and len(node) >= 3 and isinstance(node[1], str):
    E = node[1]
    inner = node[2]
    if _event_var(inner) == E:
      folded = _fold_event(inner, E, content_inner, ultra)
      if folded is not None:
        return folded
    return ([node[0], node[1], _coarsen_node(inner, content_inner, ultra)]
            + [_coarsen_node(x, content_inner, ultra) for x in node[3:]])
  head = node[0] if isinstance(node[0], str) else _coarsen_node(node[0], content_inner, ultra)
  return [head] + [_coarsen_node(x, content_inner, ultra) for x in node[1:]]


def _vars_in_relational(conj):
  """Collect every argument of is_rel2 / do literals in a conjunct list."""
  bound = set()
  for c in conj:
    if isinstance(c, list) and c and c[0] in ("is rel2", "do"):
      for a in c[1:]:
        if isinstance(a, str):
          bound.add(a)
  return bound


def _collapse_degree_node(node):
  """(ultracoarse) Collapse gradable degree literals to their simple forms on
  the pre-clausification tree, so the guard-drop sees them as relational:
    has degree rel2(REL, E1, E2, DEG, RELCLASS) -> is rel2(REL, E1, E2)
    has degree property(PROP, ENT, DEG, RELCLASS) -> has property(PROP, ENT)
  Mirrors lc_post_normalize.strip_degree_predicates, but early.  CTXT is not yet
  attached at this stage, so it is not carried."""
  if not isinstance(node, list) or not node:
    return node
  head = node[0]
  if isinstance(head, str):
    base = head[1:] if head.startswith("-") else head
    pfx = "-" if head.startswith("-") else ""
    if base == "has degree rel2" and len(node) >= 4:
      return [pfx + "is rel2", node[1], node[2], node[3]]
    if base == "has degree property" and len(node) >= 3:
      return [pfx + "has property", node[1], node[2]]
  return [_collapse_degree_node(c) if isinstance(c, list) else c for c in node]


# Near-universal types: everything is a "thing", so an isa(thing,X) antecedent
# guard is vacuous and only blocks rules whose subjects are not typed as such
# ("all four-sided things are shapes" never fires for a square).  FOLIO's FOL
# carries no such guard.  Dropping these is sound.
_UNIVERSAL_TYPES = frozenset({
  "thing", "things", "object", "objects", "entity", "entities",
  "item", "items", "something", "one", "stuff",
})


def _drop_redundant_guards(node):
  """In rule antecedents, drop an isa(T,V) guard when either V is already bound
  by a folded is_rel2/do literal in the same antecedent (the relation already
  constrains V, so the type guard demands a typing fact the problem never
  states -- matches FOLIO's relation-implies-type FOL), or T is a near-universal
  type ("thing"/"object"/...) that everything satisfies."""
  if not isinstance(node, list) or not node:
    return node
  if node[0] == "implies" and len(node) == 3 and isinstance(node[1], list) \
     and len(node[1]) == 3 and node[1][0] == "isa" \
     and node[1][1] in _UNIVERSAL_TYPES and isinstance(node[1][2], str):
    # lone universal-type guard ("a thing is either A or B" -> for all x, A or B);
    # the enclosing `forall` still binds the variable.  Matches FOLIO's gold,
    # which carries no `thing` guard (case 62).
    return _drop_redundant_guards(node[2])
  if node[0] == "implies" and len(node) >= 3 and isinstance(node[1], list) \
     and node[1] and node[1][0] == "and":
    ant = node[1]
    bound = _vars_in_relational(ant[1:])
    kept = [ant[0]]
    for c in ant[1:]:
      if isinstance(c, list) and len(c) == 3 and c[0] == "isa" and isinstance(c[2], str):
        if c[1] in _UNIVERSAL_TYPES:
          continue                        # vacuous universal-type guard -> drop
        if c[2] in bound:
          continue                        # redundant relational type guard -> drop
      kept.append(c)
    ant = kept if len(kept) > 1 else node[1]
    return ["implies", ant] + [_drop_redundant_guards(x) for x in node[2:]]
  head = node[0] if isinstance(node[0], str) else _drop_redundant_guards(node[0])
  return [head] + [_drop_redundant_guards(x) for x in node[1:]]


# ---- (ultracoarse) fold flattened event-groups in rule antecedents ---------
# _coarsen_node only folds an event wrapped in its own `exists`.  A rule
# antecedent introduces its event as bare conjuncts under `forall` (no `exists`
# wrapper), so the same verb stays Davidsonian in the rule while it folds to
# is_rel2 in an exists-wrapped fact -- and the two no longer unify (case 17:
# "RL left Bayern" folds, but the "if a player left a team" rule does not).
# Fold such a flattened group in place, then the existing guard-drop removes the
# now-redundant isa(player,X)/isa(team,Y) antecedent guards.

def _belongs_to_event(c, E):
  """True if conjunct c is a role / classifier / activity-intro literal of the
  event variable E."""
  if not (isinstance(c, list) and c and isinstance(c[0], str)):
    return False
  h = c[0]
  if h == "isa":
    return len(c) >= 3 and c[1] == "activity" and c[2] == E
  if h.startswith("has "):
    return len(c) >= 2 and c[1] == E
  if h == "actuality" or h in _MODAL_CLASSIFIERS:
    return len(c) >= 2 and c[1] == E
  return False


def _var_appears(tree, v):
  if isinstance(tree, str):
    return tree == v
  if isinstance(tree, list):
    return any(_var_appears(x, v) for x in tree)
  return False


def _rewrite_rel2_event_object(conj):
  """Rewrite ["is rel2", V, A, E, ctxt] -> ["has property", V, A, ctxt] when E is
  an activity variable in the same conjunct list ("X wins the fight E" -> X has
  the win property).  This frees E so the event group can fold and unifies the
  relation with a unary property elsewhere (case 12)."""
  evars = {c[2] for c in conj
           if isinstance(c, list) and len(c) >= 3 and c[0] == "isa"
           and c[1] == "activity" and isinstance(c[2], str)}
  if not evars:
    return conj, False
  out = []
  changed = False
  for c in conj:
    if (isinstance(c, list) and len(c) >= 4 and c[0] == "is rel2"
        and isinstance(c[3], str) and c[3] in evars):
      new = ["has property", c[1], c[2]]
      if len(c) >= 5:
        new.append(c[4])                  # carry $ctxt
      out.append(new)
      changed = True
    else:
      out.append(c)
  return out, changed


def _fold_flat_groups_in_and(and_block, exclude, content_inner, ultra):
  """Fold each local event-group inside an antecedent `and`.  A group is local
  iff its event variable E appears only in that group (not in the sibling
  conjuncts nor in `exclude`, the rule consequent) -- so removing it is safe."""
  conj, rel2_changed = _rewrite_rel2_event_object(list(and_block[1:]))
  evars = [c[2] for c in conj
           if isinstance(c, list) and len(c) >= 3 and c[0] == "isa"
           and c[1] == "activity" and isinstance(c[2], str)]
  if not evars:
    return ["and"] + conj if rel2_changed else and_block
  changed = False
  for E in evars:
    belong = [c for c in conj if _belongs_to_event(c, E)]
    if not any(isinstance(c, list) and c[0] == "isa" and len(c) >= 3
               and c[1] == "activity" and c[2] == E for c in belong):
      continue
    others = [c for c in conj if c not in belong]
    if _var_appears(others, E) or _var_appears(exclude, E):
      continue                          # E used elsewhere -> not a local event
    folded = _fold_event(["and"] + belong, E, content_inner, ultra)
    if folded is None:
      continue
    idx = conj.index(belong[0])
    conj = [c for c in conj if c not in belong]
    conj.insert(idx, folded)
    changed = True
  return ["and"] + conj if (changed or rel2_changed) else and_block


def _merge_into_and(ant, extra):
  if isinstance(ant, list) and ant and ant[0] == "and":
    return ant + [extra]
  return ["and", ant, extra]


def _flatten_nested_implies(node):
  """Rewrite implies(A, [forall*] implies(B, C)) -> [forall*] implies(A∧B, C)
  (logically equivalent).  Pulls a consequent-side condition (e.g. the "person
  they are fighting", has_target(E,Y)) into the antecedent so an event variable
  spanning both sides becomes local and can fold (case 12).  Recursive."""
  if not isinstance(node, list) or not node:
    return node
  node = [_flatten_nested_implies(c) if isinstance(c, list) else c for c in node]
  if node[0] == "implies" and len(node) >= 3:
    ant, cons = node[1], node[2]
    quants = []
    c = cons
    while isinstance(c, list) and len(c) == 3 and c[0] == "forall":
      quants.append(c[1]); c = c[2]
    if isinstance(c, list) and len(c) >= 3 and c[0] == "implies":
      out = ["implies", _merge_into_and(ant, c[1]), c[2]]
      for v in reversed(quants):
        out = ["forall", v, out]
      return _flatten_nested_implies(out)
  return node


def _fold_antecedent_events(node, content_inner, ultra):
  if not isinstance(node, list) or not node:
    return node
  if (node[0] == "implies" and len(node) >= 3 and isinstance(node[1], list)
      and node[1] and node[1][0] == "and"):
    ant = _fold_flat_groups_in_and(node[1], node[2:], content_inner, ultra)
    return ["implies", ant] + [_fold_antecedent_events(x, content_inner, ultra)
                               for x in node[2:]]
  head = (node[0] if isinstance(node[0], str)
          else _fold_antecedent_events(node[0], content_inner, ultra))
  return [head] + [_fold_antecedent_events(x, content_inner, ultra)
                   for x in node[1:]]


def _norm_const(s):
  return re.sub(r"[^A-Za-z0-9]+", "_", str(s)).strip("_")


def _atoms_of(clause):
  """Yield the literal atoms of a clause (single atom, or a disjunction list)."""
  if not isinstance(clause, list) or not clause:
    return
  if isinstance(clause[0], str):
    yield clause
  else:
    for a in clause:
      if isinstance(a, list):
        yield a


def inject_verb_bridges(result):
  """(ultracoarse, Experiment F1 / "several shapes") For every verb that appears
  in BOTH a binary is_rel2(V,A,B) and a reified event has_type(E,V), emit a
  bidirectional bridge so the two shapes interderive:

      isa(activity,E) & has_type(E,V) & has_actor(E,A) & has_target(E,B)
          ->  is_rel2(V,A,B)
      is_rel2(V,A,B)
          ->  exists Ev . isa(activity,Ev) & has_type(Ev,V)
                          & has_actor(Ev,A) & has_target(Ev,B)

  Gated to verbs with a real shape mismatch in this problem, so it never fires
  on verbs that are already consistently one shape.  Returns a list of clauses.
  """
  rel_verbs = set()
  evt_verbs = set()
  for obj in result:
    if not (isinstance(obj, dict)):
      continue
    body = obj.get("@logic")
    if body is None:
      body = obj.get("@question")
    if body is None:
      continue
    for atom in _atoms_of(body):
      h = atom[0] if atom and isinstance(atom[0], str) else None
      if h in ("is rel2", "-is rel2") and len(atom) >= 2 and isinstance(atom[1], str):
        rel_verbs.add(atom[1])
      elif h in ("has type", "-has type") and len(atom) >= 3 and isinstance(atom[2], str):
        evt_verbs.add(atom[2])
  shared = sorted(rel_verbs & evt_verbs)
  out = []
  C = "?:Cvb"
  A, B, E = "?:Avb", "?:Bvb", "?:Evb"
  for v in shared:
    sk = ["$skvb_" + _norm_const(v), A, B]
    # event -> is_rel2
    out.append({"@name": "frm_vbridge", "@logic": [
      ["-isa", "activity", E],
      ["-has type", E, v, C],
      ["-has actor", E, A, C],
      ["-has target", E, B, C],
      ["is rel2", v, A, B, C]]})
    # is_rel2 -> event (Skolemised)
    for lit in (["isa", "activity", sk],
                ["has type", sk, v, C],
                ["has actor", sk, A, C],
                ["has target", sk, B, C]):
      out.append({"@name": "frm_vbridge", "@logic": [
        ["-is rel2", v, A, B, C], lit]})
  return out


def _coarsen_one(node, content_inner, ultra):
  """Fold one scope: coarsen events, then (ultracoarse) fold antecedent event
  groups and drop the now-redundant guards."""
  node = _coarsen_node(node, content_inner, ultra)
  if ultra:
    node = _fold_antecedent_events(node, content_inner, ultra)
    node = _drop_redundant_guards(node)
  return node


def coarsen_events(tree, ultra=False):
  """Top-level entry: fold collapsible events across the tree."""
  if not isinstance(tree, list) or not tree:
    return tree
  if ultra:
    global _verb_index
    _verb_index = _build_verb_index(tree)  # for two-event inner-verb lookup
    tree = _canonicalize_entities(tree)
    tree = _collapse_degree_node(tree)     # degrees -> simple, before guard-drop
    # (ultracoarse) Scope the content-inner var set PER top-level package.
    # Stage 2 reuses event names (E1/E2/...) across sentences, so a single
    # tree-wide set lets a has_content inner var in one sentence wrongly block
    # folding an unrelated event of the same name in another (cases 2, 3:
    # "...E2..." attend event blocked by an E2 content-inner elsewhere).  Per
    # package each `@id`/`holds` formula folds against only its own inner-content
    # vars, still skipping a genuine same-scope inner content event.
    if tree[0] == "and":
      return [tree[0]] + [
        _coarsen_one(child, _collect_content_inner_vars(child), ultra)
        if isinstance(child, list) else child
        for child in tree[1:]]
    return _coarsen_one(tree, _collect_content_inner_vars(tree), ultra)
  content_inner = _collect_content_inner_vars(tree)
  return _coarsen_one(tree, content_inner, ultra)


def rel2_event_axiom_clauses():
  """The relation<->event equivalence
    is_rel2(V,A,O) <-> exists E. isa(activity,E) & has_type(E,V)
                                 & has_actor(E,A) & has_target(E,O)
  so a relation and a reified event of the same verb/actor/object interderive
  regardless of which shape each clause used (case 12 fight)."""
  V, A, O, Ctx = "?:Vre", "?:Are", "?:Ore", "?:Cre"
  ev = ["$ev_of", V, A, O]
  neg = ["-is rel2", V, A, O, Ctx]
  fwd = [                                            # is_rel2 -> event
    {"@name": "frm_rel2_event", "@logic": [neg, ["isa", "activity", ev]]},
    {"@name": "frm_rel2_event", "@logic": [neg, ["has type", ev, V, Ctx]]},
    {"@name": "frm_rel2_event", "@logic": [neg, ["has actor", ev, A, Ctx]]},
    {"@name": "frm_rel2_event", "@logic": [neg, ["has target", ev, O, Ctx]]},
  ]
  E = "?:Ere"
  rev = [                                            # event -> is_rel2
    {"@name": "frm_event_rel2", "@logic": [
      ["-isa", "activity", E],
      ["-has type", E, V, Ctx],
      ["-has actor", E, A, Ctx],
      ["-has target", E, O, Ctx],
      ["is rel2", V, A, O, Ctx]]},
  ]
  return fwd + rev
