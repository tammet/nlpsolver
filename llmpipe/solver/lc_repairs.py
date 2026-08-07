# Pre-clausification structural repairs: id hoisting, misnested-implies
# repair, the self-defeating-conditional engine, the -s2split off-inventory
# predicate rename, and @definite tag stripping.  Split out of logconvert.py.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

import re
import lc_encoding
from lc_post_normalize import GRADABLE_PROPS as _GRADABLE_PROPS


# ======== structural repair ========

def hoist_nested_ids(logic):
  """Hoist @id blocks nested inside other @id blocks to the top level.

  LLM JSON errors sometimes drop a closing bracket, causing the auto-fixer
  to nest one @id inside another.  Since @id blocks are never legitimately
  nested, any inner @id is extracted and placed as a sibling.

  Only operates on the top-level ["and", ...] structure.
  """
  if not isinstance(logic, list) or not logic:
    return logic
  op = logic[0]
  if op == "@id":
    items = [logic]
  elif op == "and":
    items = logic[1:]
  else:
    return logic

  changed = False
  new_items = []
  for item in items:
    if not isinstance(item, list) or len(item) < 2 or item[0] != "@id":
      new_items.append(item)
      continue
    # Scan this @id's children (positions 2+) for nested @id blocks.
    hoisted = []
    kept = [item[0], item[1]]  # "@id", SID
    for child in item[2:]:
      if isinstance(child, list) and len(child) >= 2 and child[0] == "@id":
        hoisted.append(child)
      else:
        kept.append(child)
    if hoisted:
      changed = True
      if len(kept) > 2:
        new_items.append(kept)
      new_items.extend(hoisted)
    else:
      new_items.append(item)

  if not changed:
    return logic
  # Recurse: hoisted items may themselves contain nested @ids.
  final_items = []
  for item in new_items:
    sub = hoist_nested_ids(["and", item])
    if isinstance(sub, list) and sub and sub[0] == "and":
      final_items.extend(sub[1:])
    else:
      final_items.append(sub)
  if len(final_items) == 1:
    return final_items[0]
  return ["and"] + final_items


def repair_misnested_normally_implies(logic):
  """Repair a rule consequent misplaced onto `normally`.

  Some LLMs (deepseek, case 1418) treat `normally` as a binary operator and
  emit ["normally", ["implies", A], C] — hanging the rule's consequent C off
  `normally` instead of inside the `implies`, which is left consequent-less
  (len 2) and would otherwise crash / lose the consequent.  Rewrite to
  ["normally", ["implies", A, C]] so the rule recovers its consequent.

  Discriminator vs the legitimate tagged form ["normally", FRM, CLASS]: the
  malformation's 3rd arg is a FORMULA (list), not a class-name string, and the
  1st arg is specifically a 2-element (consequent-less) `implies`.  A 2-element
  `implies` is always malformed, so the rewrite is unambiguous.  Recursive.
  """
  if not isinstance(logic, list) or not logic:
    return logic
  if (logic[0] == "normally" and len(logic) == 3
      and isinstance(logic[1], list) and len(logic[1]) == 2
      and logic[1][0] == "implies"
      and isinstance(logic[2], list)):
    logic = ["normally", ["implies", logic[1][1], logic[2]]]
  return [repair_misnested_normally_implies(c) if isinstance(c, list) else c
          for c in logic]


# ======== self-defeating-conditional repair (negation scope) ========
#
# Stage-2 sometimes mis-scopes "X is not A and B": it reads "(not A) and B"
# when the sentence means "not (A and B)".  The resulting conditional
# ["implies", ["and", ["not", A], B], CONS] is SELF-DEFEATING when CONS is
# false under every antecedent-satisfying assignment -- the whole rule then
# collapses to just ¬antecedent, losing the intended content (case 41: premise
# "if Rina is not dependent and a student, then ..." parsed as ¬dep∧student,
# reducing to student→dependent).
#
# Detection is a tiny boolean truth-table over the (few) atoms of the
# implication; a *correctly* scoped conditional is never self-defeating, so the
# signal is clean.  Repair only the unambiguous two-conjunct mixed-polarity
# antecedent, by widening the negation to ¬(A∧B), and ONLY when that removes
# the self-defeat -- so we never flip a genuinely narrow-scope "(not A) and B".
# Gated on -guarddrop.

_SDC_CONNECTIVES = frozenset({"and", "or", "not", "xor", "implies",
                              "equivalent", "iff"})


def _sdc_atom_key(atom):
  """Canonical hashable form of an atom, ignoring $ctxt sub-terms."""
  if isinstance(atom, list):
    parts = []
    for x in atom:
      if (isinstance(x, list) and x and isinstance(x[0], str)
          and x[0].startswith("$ctxt")):
        continue
      parts.append(_sdc_atom_key(x))
    return tuple(parts)
  return atom


def _sdc_collect_atoms(node, out):
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return
  if node[0] in _SDC_CONNECTIVES:
    for c in node[1:]:
      _sdc_collect_atoms(c, out)
  else:
    out.add(_sdc_atom_key(node))


def _sdc_eval(node, assign):
  """Evaluate a boolean formula; return True/False, or None if not evaluable."""
  if not isinstance(node, list) or not node or not isinstance(node[0], str):
    return None
  h = node[0]
  if h == "not":
    v = _sdc_eval(node[1], assign) if len(node) >= 2 else None
    return None if v is None else (not v)
  if h in ("and", "or", "xor"):
    vs = [_sdc_eval(c, assign) for c in node[1:]]
    if any(v is None for v in vs):
      return None
    if h == "and":
      return all(vs)
    if h == "or":
      return any(vs)
    return (sum(1 for v in vs if v) % 2) == 1
  if h == "implies" and len(node) >= 3:
    a = _sdc_eval(node[1], assign); b = _sdc_eval(node[2], assign)
    return None if (a is None or b is None) else ((not a) or b)
  if h in ("equivalent", "iff") and len(node) >= 3:
    a = _sdc_eval(node[1], assign); b = _sdc_eval(node[2], assign)
    return None if (a is None or b is None) else (a == b)
  # atom
  return assign.get(_sdc_atom_key(node))


def _sdc_is_self_defeating(ant, cons):
  """True iff ant is satisfiable but cons is false in every ant-true row."""
  atoms = set()
  _sdc_collect_atoms(ant, atoms)
  _sdc_collect_atoms(cons, atoms)
  atoms = sorted(atoms)
  if not atoms or len(atoms) > 5:
    return False
  n = len(atoms)
  ant_sat = False
  for mask in range(1 << n):
    assign = {atoms[i]: bool(mask >> i & 1) for i in range(n)}
    a = _sdc_eval(ant, assign)
    if a is None:
      return False                      # not fully evaluable -> don't flag
    if a:
      ant_sat = True
      c = _sdc_eval(cons, assign)
      if c is None:
        return False
      if c:
        return False                    # an ant-true row with cons true
  return ant_sat


def _sdc_overlaps(conj, cons_atoms):
  a = set()
  _sdc_collect_atoms(conj, a)
  return bool(a & cons_atoms)


def _sdc_widen_negation(ant, cons):
  """For an ["and", ...] antecedent with EXACTLY ONE negated conjunct ["not", P],
  widen that negation over P plus the other "content" conjuncts (those whose
  atoms appear in the consequent), leaving guard conjuncts (e.g. isa(person,X),
  whose atoms the consequent never mentions) outside.  Returns the rewritten
  antecedent, or None if the shape doesn't qualify.
  "not (a person dependent on caffeine) and a student" ->
  person ∧ ¬(dependent ∧ student)."""
  if not (isinstance(ant, list) and len(ant) >= 2 and ant[0] == "and"):
    return None
  conjs = ant[1:]
  negated = [c for c in conjs
             if isinstance(c, list) and len(c) == 2 and c[0] == "not"]
  if len(negated) != 1:
    return None
  negc = negated[0]
  positives = [c for c in conjs if c is not negc]
  cons_atoms = set()
  _sdc_collect_atoms(cons, cons_atoms)
  content = [c for c in positives if _sdc_overlaps(c, cons_atoms)]
  guards = [c for c in positives if not _sdc_overlaps(c, cons_atoms)]
  if not content:
    return None
  new_neg = ["not", ["and", negc[1]] + content]
  new_conjs = guards + [new_neg]
  return new_conjs[0] if len(new_conjs) == 1 else ["and"] + new_conjs


# (-s2split repair) Off-inventory predicate names an isolated per-sentence
# Stage-2 call drifts into, mapped to their inventory forms.
_OFFINV_PRED_RENAME = {"has": "have", "has rel2": "is rel2",
                       "has agent": "has actor"}

# (-s2split repair) Adjective -> measurement-dimension noun, for $measure_of
# terms whose dimension slot drifted to the adjective ("$measure_of tall"
# instead of "$measure_of height", claude case 552).
_ADJ_DIMENSION = {
  "tall": "height", "high": "height", "heavy": "weight", "long": "length",
  "old": "age", "big": "size", "large": "size", "fast": "speed",
  "wide": "width", "deep": "depth", "hot": "temperature", "far": "distance",
}

from lc_post_normalize import GRADABLE_PROPS as _GRADABLE_PROPS


def _comparative_to_base(word):
  """"higher than" / "higher" -> "high"; "nicer" -> "nice"; "bigger" -> "big".
  Strips a trailing " than", then tries the standard -er reversals, accepting
  a candidate only if it is a known gradable adjective.  Returns the original
  string when nothing matches (so ordinary relation names are untouched)."""
  w = word
  if w.endswith(" than"):
    w = w[:-5].strip()
  if w.startswith("more "):
    cand = w[5:].strip()
    return cand if cand in _GRADABLE_PROPS else word
  if w in _GRADABLE_PROPS:
    return w
  if w.endswith("er"):
    for cand in (w[:-2], w[:-1], w[:-3]):   # tall-er, nice-r, bigg-er
      if cand and cand in _GRADABLE_PROPS:
        return cand
  return word


def rename_offinventory_preds(node):
  if not isinstance(node, list) or not node:
    return node
  head = node[0]
  if isinstance(head, str) and head in _OFFINV_PRED_RENAME:
    head = _OFFINV_PRED_RENAME[head]
  out = [head] + [rename_offinventory_preds(x) if isinstance(x, list) else x
                  for x in node[1:]]
  # comparative-phrase relation name: has degree rel2("higher than",...) ->
  # ("high",...)  (gemini case 553; also bare "higher")
  if (head in ("has degree rel2", "is rel2") and len(out) >= 2
      and isinstance(out[1], str)):
    out[1] = _comparative_to_base(out[1])
  # adjective-as-dimension: $measure_of("tall", X, W) -> ("height", X, W)
  if head == "$measure_of" and len(out) >= 2 and isinstance(out[1], str):
    out[1] = _ADJ_DIMENSION.get(out[1], out[1])
  return out


def repair_self_defeating_conditional(logic):
  if not lc_encoding.current().guarddrop:
    return logic
  return _rsdc(logic)


def _rsdc(node):
  if not isinstance(node, list) or not node:
    return node
  node = [_rsdc(c) if isinstance(c, list) else c for c in node]
  if node[0] == "implies" and len(node) >= 3 and _sdc_is_self_defeating(node[1], node[2]):
    widened = _sdc_widen_negation(node[1], node[2])
    if widened is not None and not _sdc_is_self_defeating(widened, node[2]):
      node = ["implies", widened] + node[2:]
  return node


# ======== @definite tag stripping ========

def strip_definite_tags(tree):
  """Remove @definite atoms from the logic tree.

  Strips ["@definite", ...] from "and" conjunctions.  These are metadata
  annotations not consumed by the pipeline.
  """
  if not isinstance(tree, list) or not tree:
    return tree
  op = tree[0] if isinstance(tree[0], str) else None
  if op == "@definite":
    return None  # sentinel: remove this conjunct
  if op == "and":
    children = []
    for child in tree[1:]:
      result = strip_definite_tags(child)
      if result is not None:
        children.append(result)
    if not children:
      return None
    if len(children) == 1:
      return children[0]
    return ["and"] + children
  return [strip_definite_tags(child) if isinstance(child, list) else child
          for child in tree]



# ======== question-packaging repair (plan fix 5) ========

_ASSERTION_TYPES = frozenset(["real", "situation", "strict_rule", "normal_rule"])
_WH_WORDS = frozenset(["who", "whom", "what", "which", "where", "when", "whose", "why", "how"])


def _s1_unit_index(s1_json):
  """unit_id -> ASU dict."""
  out = {}
  for pkg in s1_json if isinstance(s1_json, list) else []:
    if not isinstance(pkg, dict):
      continue
    for u in pkg.get("units", []) or []:
      if isinstance(u, dict) and u.get("unit_id"):
        out[str(u["unit_id"])] = u
  return out


def _has_wh_word(text):
  if not isinstance(text, str):
    return False
  return any(w in _WH_WORDS for w in re.findall(r"[a-z]+", text.lower()))


def repair_question_packaging(logic, s1_json):
  """(fix 5) Deterministic last-resort repair of query packaging.

  The Stage-2 sanity checks already flag `multiple_questions` and
  `missing_question` and re-prompt once; this runs when the model did not
  comply (gpt-luna repeats the mistake, so the retry loop stops on
  persistence).  Stage 1 declares exactly which ASU is the query, so the
  correct packaging is determined without re-reading the English:

    * a `question`/`ask` head on an ASU Stage 1 typed as an assertion
      -> ["holds", W, F]  (W from the ASU's pre_state, else "W0")
    * no query package anywhere, exactly one ASU typed `query`
      -> that ASU's package becomes ["question", F]
    * an answer variable on a query whose Stage-1 text has no wh-word
      -> ["ask", V, F] becomes ["question", ["exists", V, F]] — sound, and
         unlike simply dropping V it keeps F's occurrences of V bound.

  All three require exactly one Stage-1 `query` ASU; with zero or several the
  repair has no ground truth and does nothing.
  """
  from globals import options as _opts
  if (_opts.get("nofix_questionpkg") or not isinstance(logic, list)
      or not isinstance(s1_json, list)):
    return logic
  units = _s1_unit_index(s1_json)
  query_ids = [uid for uid, u in units.items() if u.get("type") == "query"]
  if len(query_ids) != 1:
    return logic
  qid = query_ids[0]

  def head_of(pkg):
    return pkg[0] if isinstance(pkg, list) and pkg and isinstance(pkg[0], str) else None

  # Locate the @id items and their package heads.
  items = []
  for i, item in enumerate(logic):
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      items.append((i, str(item[1]), item))
  if not items:
    return logic

  changed = False
  out = list(logic)

  # (a) query package on an assertion ASU -> holds
  for i, sid, item in items:
    if sid == qid:
      continue
    u = units.get(sid)
    if u is None or u.get("type") not in _ASSERTION_TYPES:
      continue
    pkg = item[2]
    h = head_of(pkg)
    if h == "question" and len(pkg) >= 2:
      world = u.get("pre_state") if isinstance(u.get("pre_state"), str) else "W0"
      out[i] = [item[0], item[1], ["holds", world, pkg[1]]] + list(item[3:])
      changed = True
    elif h == "ask" and len(pkg) >= 3:
      world = u.get("pre_state") if isinstance(u.get("pre_state"), str) else "W0"
      out[i] = [item[0], item[1],
                ["holds", world, ["exists", pkg[1], pkg[2]]]] + list(item[3:])
      changed = True

  # (b) no query package anywhere -> wrap the Stage-1 query ASU
  def any_query(tree):
    if isinstance(tree, list) and tree:
      if isinstance(tree[0], str) and tree[0] in ("question", "ask"):
        return True
      return any(any_query(c) for c in tree if isinstance(c, list))
    return False

  if not any(any_query(it[2]) for it in items):
    for i, sid, item in items:
      if sid != qid:
        continue
      pkg = item[2]
      body = pkg[2] if (head_of(pkg) == "holds" and len(pkg) >= 3) else pkg
      out[i] = [item[0], item[1], ["question", body]] + list(item[3:])
      changed = True
      break

  # (c) answer variable on a yes/no query -> question(exists V, F)
  qtext = units.get(qid, {}).get("text")
  if not _has_wh_word(qtext):
    for i, sid, item in items:
      if sid != qid:
        continue
      pkg = out[i][2]
      if head_of(pkg) == "ask" and len(pkg) >= 3:
        out[i] = [item[0], item[1],
                  ["question", ["exists", pkg[1], pkg[2]]]] + list(item[3:])
        changed = True
      break

  return out if changed else logic


# ======== comparative canonicalisation (plan fix 7d) ========

# "taller than" -> ("tall", "high"): the adjective plus the degree direction.
_COMPARATIVE_SUFFIX_RE = re.compile(r"^(.+?)(?:er)\s+than$", re.IGNORECASE)
_COMPARATIVE_MORE_RE = re.compile(r"^more\s+(.+?)\s+than$", re.IGNORECASE)
_COMPARATIVE_LESS_RE = re.compile(r"^less\s+(.+?)\s+than$", re.IGNORECASE)

# Irregular comparatives worth handling; anything else falls through untouched.
_IRREGULAR_COMPARATIVES = {
  "better than": ("good", "high"),
  "worse than": ("good", "low"),
  "further than": ("far", "high"),
  "farther than": ("far", "high"),
  "more than": None,          # quantity, not a gradable adjective — skip
  "less than": None,
  "older than": ("old", "high"),
  "younger than": ("old", "low"),
}


def _gradable_set():
  """Known gradable adjectives, used to validate a comparative stem."""
  global _GRADABLE_CACHE
  if _GRADABLE_CACHE is None:
    try:
      _GRADABLE_CACHE = frozenset(x.lower() for x in _GRADABLE_PROPS)
    except Exception:
      _GRADABLE_CACHE = frozenset()
  return _GRADABLE_CACHE


_GRADABLE_CACHE = None


def _stem_candidates(comp):
  """Plausible base adjectives for a comparative form ending in -er."""
  out = [comp]
  if comp.endswith("e"):
    out.append(comp[:-1])
  if len(comp) > 2 and comp[-1] == comp[-2] and comp[-1] not in "aeiou":
    out.append(comp[:-1])          # bigger -> big
  if comp.endswith("i"):
    out.append(comp[:-1] + "y")    # happier -> happy
  out.append(comp + "e")           # nicer -> nice  (stem was "nic")
  return out


def _pick_stem(comp):
  """Choose the base adjective for a comparative stem, preferring a known
  gradable.  Returns None when nothing plausible is known — better to leave
  the relation alone than to invent a predicate."""
  grad = _gradable_set()
  cands = _stem_candidates(comp)
  for c in cands:
    if c in grad:
      return c
  return None


def _comparative_parts(rel):
  """('taller than') -> ('tall', 'high'), or None when not a comparative.

  The stem is validated against the gradable-adjective lexicon, because
  English comparative morphology is not invertible by rule: "taller" could
  stem to "tall" or "tal", "bigger" to "big" or "bigg".
  """
  if not isinstance(rel, str):
    return None
  key = rel.strip().lower()
  if key in _IRREGULAR_COMPARATIVES:
    return _IRREGULAR_COMPARATIVES[key]
  m = _COMPARATIVE_MORE_RE.match(key)
  if m:
    return (m.group(1).strip(), "high")
  m = _COMPARATIVE_LESS_RE.match(key)
  if m:
    return (m.group(1).strip(), "low")
  m = _COMPARATIVE_SUFFIX_RE.match(key)
  if m:
    stem = _pick_stem(m.group(1).strip())
    if stem:
      return (stem, "high")
  return None


def canonicalize_comparative_relations(tree, _top=True):
  """(fix 7d) Rewrite ["is rel2", "<adj>er than", X, Y] to the pipeline's
  degree form ["has degree rel2", "<adj>", X, Y, "high"|"low", "none"].

  Stage 2 sometimes encodes a comparative as an opaque binary relation whose
  name embeds the comparison ("taller than", "higher than", "faster than").
  Nothing in the pipeline relates that constant to the measure machinery, so
  premise and question stop unifying even when both use it (claude 551,
  gpt 553, gemini 549).  Only morphologically recognisable comparatives are
  rewritten; anything else is left alone.
  """
  if _top:
    from globals import options as _opts
    if _opts.get("nofix_comparative"):
      return tree
  if not isinstance(tree, list) or not tree:
    return tree
  if isinstance(tree[0], str):
    base = tree[0].lstrip("-")
    neg = "-" if tree[0].startswith("-") else ""
    if base == "is rel2" and len(tree) >= 4 and isinstance(tree[1], str):
      parts = _comparative_parts(tree[1])
      if parts:
        adj, direction = parts
        return ([neg + "has degree rel2", adj, tree[2], tree[3], direction, "none"]
                + [canonicalize_comparative_relations(x, _top=False) if isinstance(x, list) else x
                   for x in tree[4:]])
    # Stage 2 also writes the comparative into the ADJECTIVE slot of an
    # otherwise correct degree relation: ["has degree rel2","taller than",X,Y,
    # "high",C].  Normalise the slot, keeping the explicit direction when the
    # phrase does not itself carry one.
    if base == "has degree rel2" and len(tree) >= 5 and isinstance(tree[1], str):
      parts = _comparative_parts(tree[1])
      if parts:
        adj, direction = parts
        slot = tree[4] if isinstance(tree[4], str) and tree[4] in ("high", "low") \
               else direction
        if str(tree[1]).strip().lower().startswith("less "):
          slot = "low"
        return ([neg + "has degree rel2", adj, tree[2], tree[3], slot]
                + [canonicalize_comparative_relations(x, _top=False) if isinstance(x, list) else x
                   for x in tree[5:]])
    return [tree[0]] + [canonicalize_comparative_relations(x, _top=False) if isinstance(x, list) else x
                        for x in tree[1:]]
  return [canonicalize_comparative_relations(x, _top=False) if isinstance(x, list) else x
          for x in tree]
