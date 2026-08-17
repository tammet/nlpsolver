"""Ask for a direction, then let code write the bridge.

The model sees a batch of enumerated pairs and returns one label per pair.  It
writes no formula: every clause is serialized here, from the label and from the
exact atoms the pair was enumerated with.  That is the difference the design
rests on — the literal bridge asked four models to compose rules and got 2,464
rules that reduced to 465-760 distinct formulas per arm, of which 22 were
common to all four.  A label is a much smaller thing to disagree about.

A bridge is a simple rule over open atoms: named, defeasible, at full
confidence, with a `$block`, compiled by `litbridge_compile` under the graph
option set.  Nothing here writes a low `@confidence`; trust is applied after
proof search.
"""

import os
import re

import graph_pairs as GP
import litbridge_rules as LR

VERSION = "graph_judge/2026-08-16"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "graph")

JUDGE_SENTENCES = os.path.join(PROMPT_DIR, "graph_judge_system_sentences.txt")
JUDGE_NAMES_ONLY = os.path.join(PROMPT_DIR, "graph_judge_system_names_only.txt")
JUDGE_LEXICAL = os.path.join(PROMPT_DIR, "graph_judge_system_lexical.txt")
HOLISTIC = os.path.join(PROMPT_DIR, "graph_holistic_system.txt")

ORIGIN = "graph_bridge"
MAX_BRIDGE_FORMULAS = 60

A_IMPLIES_B = "A_IMPLIES_B"
B_IMPLIES_A = "B_IMPLIES_A"
EQUIVALENT = "EQUIVALENT"
A_IMPLIES_NOT_B = "A_IMPLIES_NOT_B"
B_IMPLIES_NOT_A = "B_IMPLIES_NOT_A"
EXCLUSIVE = "EXCLUSIVE"
INVERSE = "INVERSE"
RELATED = "RELATED_BUT_NO_IMPLICATION"
UNRELATED = "UNRELATED"
UNCERTAIN = "UNCERTAIN"

LABELS = (A_IMPLIES_B, B_IMPLIES_A, EQUIVALENT, A_IMPLIES_NOT_B,
          B_IMPLIES_NOT_A, EXCLUSIVE, INVERSE, RELATED, UNRELATED, UNCERTAIN)

# design plan §8.8
POOL1_LABELS = (A_IMPLIES_B, B_IMPLIES_A, EQUIVALENT, INVERSE, EXCLUSIVE,
                A_IMPLIES_NOT_B, B_IMPLIES_NOT_A)

# `PAIR 3: A_IMPLIES_B [STATED] [HIGH]` — the tag and the confidence are v2 and
# optional, so a v1 reply still parses.
PAIR_LINE = re.compile(
    r"^\s*PAIR\s+(\d+)\s*:\s*([A-Z_]+)"
    r"(?:\s*\[\s*([A-Z_]+)\s*\])?"
    r"(?:\s*\[\s*([A-Z]+)\s*\])?\s*$", re.I)

# WP3.1 evidence tags
LEXICAL, STATED, BACKGROUND = "LEXICAL", "STATED", "BACKGROUND"
EVIDENCE = (LEXICAL, STATED, BACKGROUND)

# WP0.2 confidence, folded into the judge so the grader is not needed
HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
CONFIDENCE = (HIGH, MEDIUM, LOW)

# the grade a confidence stands for, so one acceptance policy reads both
GRADE_OF_CONFIDENCE = {HIGH: "LIKELY", MEDIUM: "PLAUSIBLE", LOW: "UNCERTAIN"}
WHY_LINE = re.compile(r"^\s*WHY\s*:\s*(.+)$", re.I)
PROPOSAL_LINE = re.compile(
    r"^\s*PROPOSAL\s+\d+\s*:\s*(.+?)\s*\|\s*(.+?)\s*\|\s*([A-Z_]+)\s*$", re.I)
NONE_LINE = re.compile(r"^\s*NONE\s*$", re.I)

# an optional knob, default off (design plan §8.7)
PRIORITY_BY_TOKENS = False


def _read(path):
  with open(path) as f:
    return f.read().strip()


def judge_system_prompt(with_sentences=True):
  return _read(JUDGE_SENTENCES if with_sentences else JUDGE_NAMES_ONLY)


def holistic_system_prompt():
  return _read(HOLISTIC)


def prompt_hashes():
  import hashlib
  out = {}
  for p in (JUDGE_SENTENCES, JUDGE_NAMES_ONLY, HOLISTIC):
    if os.path.exists(p):
      out[os.path.relpath(p, ROOT)] = hashlib.sha256(
          open(p, "rb").read()).hexdigest()
  return out


# ------------------------------------------------------------- the batch text

def _sentences_for(name, inventory, s1_json, cap=2, skip=()):
  """The PASSAGE sentences a name occurs in, at most `cap`.

  The question's own sentence is never one of them.  A name may occur in the
  question as well as the passage, and showing that occurrence's sentence would
  tell the judge what the case asks, which design plan §8.3 and the §15
  invariants forbid.  `skip` is the question packages.
  """
  import graph_inventory as GI
  import graph_stage2 as G2
  hidden = set(skip)
  out = []
  for pid in GI.packages_of(inventory, name):
    if pid in hidden:
      continue
    text = G2.sentence_of(s1_json, pid)
    if text and text not in out:
      out.append(text)
  return out[:cap]


def batch_message(pairs, inventory, s1_json, with_sentences=True):
  """The user message of one judge batch.  Never shows the question."""
  import graph_stage2 as G2
  asked = set(G2.question_unit_ids(s1_json))
  lines = []
  for i, pair in enumerate(pairs, start=1):
    lines.append("PAIR %d  (%s)" % (i, pair["kind"]))
    lines.append("  A: %s" % pair["a"])
    lines.append("     atom: %s" % pair["a_reading"])
    lines.append("  B: %s" % pair["b"])
    lines.append("     atom: %s" % pair["b_reading"])
    if pair.get("question"):
      lines.append("  ask: %s" % pair["question"])
    if pair.get("guard"):
      lines.append("  the second atom is asked only of things that are %s"
                   % pair["guard"])
    if pair.get("stricter_question"):
      lines.append("  for this pair, answer A_IMPLIES_B only if a sentence "
                   "below licenses the relation; name it in a WHY line.")
    if pair["shape"] == GP.COMPOSITION:
      lines.append("  the passage states: %s"
                   % "; ".join(pair.get("chain_atoms") or []))
    if with_sentences:
      for side, name in (("A", pair["a"]), ("B", pair["b"])):
        for text in _sentences_for(name, inventory, s1_json, skip=asked):
          lines.append("  %s occurs in: %s" % (side, text))
    lines.append("")
  return "\n".join(lines).strip()


def holistic_message(inventory):
  """The whole name inventory, one example atom each."""
  import graph_inventory as GI
  lines = ["CONCEPT NAMES"]
  for name in inventory["concept_names"]:
    row = GI.example_atom(inventory, name, "concept")
    lines.append("  %-40s %s" % (name, GP._occurrence_reading(row)))
  for name in inventory["kind_constant_names"]:
    lines.append("  %-40s (a kind named as an argument)" % name)
  lines.append("")
  lines.append("RELATION NAMES")
  for name in inventory["relation_names"]:
    row = GI.example_atom(inventory, name, "relation")
    lines.append("  %-40s %s" % (name, GP._occurrence_reading(row)))
  return "\n".join(lines)


# ---------------------------------------------------------------- the parser

def parse_batch(text, pairs):
  """-> [{pair, label, why, raw}].  A missing line is UNCERTAIN."""
  labels, tags, confs, whys, last = {}, {}, {}, {}, None
  for line in (text or "").splitlines():
    m = PAIR_LINE.match(line)
    if m:
      last = int(m.group(1))
      labels[last] = m.group(2).upper()
      # the two bracketed fields may arrive in either order
      for got in (m.group(3), m.group(4)):
        if not got:
          continue
        got = got.upper()
        if got in EVIDENCE:
          tags[last] = got
        elif got in CONFIDENCE:
          confs[last] = got
      continue
    m = WHY_LINE.match(line)
    if m and last is not None:
      whys[last] = m.group(1).strip()[:300]
  out = []
  for i, pair in enumerate(pairs, start=1):
    raw = labels.get(i)
    label = raw if raw in LABELS else UNCERTAIN
    row = {"pair_id": pair.get("pair_id"), "index": i, "label": label,
           "why": whys.get(i), "pair": pair,
           # WP3.1: a missing tag is BACKGROUND — the cautious reading
           "evidence": tags.get(i, BACKGROUND),
           "evidence_given": i in tags,
           "confidence": confs.get(i),
           "same_sentence": bool(pair.get("same_sentence"))}
    if raw and raw not in LABELS:
      row["unknown_label"] = raw
    if raw is None:
      row["missing"] = True
    if label == INVERSE and pair["kind"] != "relation":
      row["label"] = UNCERTAIN
      row["refused_label"] = "INVERSE is for relation pairs only"
    out.append(row)
  return out


def parse_holistic(text, inventory):
  """-> [{a, b, label}] for proposals whose two names are both in the case."""
  known = (set(inventory["concept_names"]) | set(inventory["relation_names"])
           | set(inventory["kind_constant_names"]))
  out, dropped = [], []
  for line in (text or "").splitlines():
    if NONE_LINE.match(line):
      continue
    m = PROPOSAL_LINE.match(line)
    if not m:
      continue
    a, b, label = m.group(1).strip(), m.group(2).strip(), m.group(3).upper()
    # `judge_label`, not `label`: this row is recorded, and
    # `unifier_cases.assert_no_gold` reserves `label` for a reviewed key
    if label not in LABELS:
      dropped.append({"a": a, "b": b, "judge_label": label,
                      "why": "the label is not one of the vocabulary"})
      continue
    if a not in known or b not in known:
      dropped.append({"a": a, "b": b, "judge_label": label,
                      "why": "a name is not in this case's inventory"})
      continue
    out.append({"a": a, "b": b, "label": label})
  return out, dropped


def holistic_pairs(proposals, inventory):
  """-> pairs in the enumeration shape, so they take the same filters."""
  concepts = set(inventory["concept_names"]) | set(
      inventory["kind_constant_names"])
  out = []
  for row in proposals:
    a, b = row["a"], row["b"]
    if a in concepts and b in concepts:
      pair = GP._mk(GP.CONCEPT_CONCEPT, a, b, [GP.concept_atom(a)],
                    [GP.concept_atom(b)], "holistic")
    elif a not in concepts and b not in concepts:
      pair = GP._mk(GP.RELATION_RELATION, a, b, [GP.relation_atom(a)],
                    [GP.relation_atom(b)], "holistic")
    else:
      continue
    pair["holistic_label"] = row["label"]
    out.append(pair)
  return out


# --------------------------------------------------------- serialization

def _lit(atom, sign="+"):
  return {"sign": sign, "atom": list(atom)}


def _variables(literals):
  seen = []
  for atom in literals:
    for term in atom[1:]:
      if isinstance(term, str) and term.startswith("?") and term not in seen:
        seen.append(term)
  return seen


def _rule(rule_id, body, head, pair, label, note):
  """One bridge rule in the shape `litbridge_compile` compiles."""
  literals = [l["atom"] for l in body] + [head["atom"]]
  rule = {"rule_id": rule_id, "body": body, "head": head,
          "llm_variables": _variables(literals),
          "premises": len(body), "origin": ORIGIN, "warnings": [],
          "variants": [], "candidate_matches": [],
          "atoms_matching_no_candidate": [], "rule_priority_cost": 0,
          "graph_pair_id": pair.get("pair_id"),
          "graph_shape": pair.get("shape"),
          "graph_label": label, "graph_a": pair["a"], "graph_b": pair["b"],
          "graph_source": pair.get("source"), "graph_note": note,
          "role_fit": {"fits": True, "body_fits": True, "head_fits": True,
                       "body_roles": ["PREMISE"] * len(body),
                       "head_role": "CONSEQUENCE"}}
  rule["canonical"] = LR.canonical(rule)
  rule["printed"] = LR.printed_rule(rule)
  return rule


def _inverted(atom):
  """A relation atom with its two participants swapped."""
  if atom[0] != GP.RELATION or len(atom) != 4:
    return None
  return [atom[0], atom[1], atom[3], atom[2]]


def serialize(row, next_index):
  """-> (the rules a label produces, a note for the ones it cannot).

  Code writes every sign combination.  A direction whose target side is more
  than one literal cannot be a conclusion and is recorded, not emitted.  When
  either displayed occurrence was negated, the contrapositive is emitted too,
  so a negated occurrence in the theory can still fire the bridge.
  """
  pair, label = row["pair"], row["label"]
  a_lits, b_lits = pair["a_literals"], pair["b_literals"]
  negated = pair.get("a_sign") == "-" or pair.get("b_sign") == "-"
  rules_out, skipped = [], []
  n = [next_index]

  def rid():
    n[0] += 1
    return "G%d" % (n[0] - 1)

  question_only = set(pair.get("question_only_sides") or ())

  def emit(body_lits, body_sign, head_atom, head_sign, note, body_side=None):
    if head_atom is None:
      skipped.append({"pair_id": pair.get("pair_id"), "judge_label": label,
                      "why": "the conclusion side is not a single literal",
                      "note": note})
      return
    if body_side in question_only:
      # §8.9: a bridge whose body name occurs only in the question is refused.
      # The direction, not the pair: the same pair's other direction concludes
      # that name and is exactly what the frontier is for.
      skipped.append({"pair_id": pair.get("pair_id"), "judge_label": label,
                      "why": "the body name occurs only in the question",
                      "note": note})
      return
    body = [_lit(a, body_sign) for a in body_lits]
    rules_out.append(_rule(rid(), body, _lit(head_atom, head_sign), pair,
                           label, note))

  def one(lits):
    return lits[0] if len(lits) == 1 else None

  if label == INVERSE and pair["kind"] == "relation":
    ia, ib = _inverted(a_lits[0]), _inverted(b_lits[0])
    if ib is not None:
      emit(a_lits, "+", ib, "+", "INVERSE, A(X,Y) -> B(Y,X)", "a")
    if ia is not None:
      emit(b_lits, "+", ia, "+", "INVERSE, B(X,Y) -> A(Y,X)", "b")
    return rules_out, skipped, n[0]

  forward = label in (A_IMPLIES_B, EQUIVALENT)
  backward = label in (B_IMPLIES_A, EQUIVALENT)
  forward_negative = label in (A_IMPLIES_NOT_B, EXCLUSIVE)
  backward_negative = label in (B_IMPLIES_NOT_A, EXCLUSIVE)

  if forward:
    emit(a_lits, "+", one(b_lits), "+", "A implies B", "a")
    if negated:
      emit(b_lits, "-", one(a_lits), "-",
           "the contrapositive, for the negated occurrence", "b")
  if backward:
    emit(b_lits, "+", one(a_lits), "+", "B implies A", "b")
    if negated:
      emit(a_lits, "-", one(b_lits), "-",
           "the contrapositive, for the negated occurrence", "a")
  if forward_negative:
    emit(a_lits, "+", one(b_lits), "-", "A implies NOT B", "a")
  if backward_negative:
    emit(b_lits, "+", one(a_lits), "-", "B implies NOT A", "b")
  return rules_out, skipped, n[0]


LEXICAL_LINE = re.compile(
    r"^\s*PAIR\s+(\d+)\s*:\s*(EQUIVALENT|A_IMPLIES_B|B_IMPLIES_A|NO)"
    r"(?:\s+LEXICAL)?\s*$", re.I)
LEXICAL_LABELS = (EQUIVALENT, A_IMPLIES_B, B_IMPLIES_A)


def parse_lexical(text, pairs):
  """The restatement batch: only three labels are allowed, everything else NO.

  A pair the ordinary enumeration refused as a question restatement comes back
  here.  The reply may say the two names are one predicate in other wording,
  and nothing else: any line that is not one of the three allowed labels is
  read as NO, and a NO pair produces no bridge at all.
  """
  got = {}
  for line in (text or "").splitlines():
    m = LEXICAL_LINE.match(line)
    if m:
      got[int(m.group(1))] = m.group(2).upper()
  out = []
  for i, pair in enumerate(pairs, start=1):
    label = got.get(i)
    if label not in LEXICAL_LABELS:
      continue
    out.append({"pair_id": pair.get("pair_id"), "label": label, "pair": pair,
                "why": None, "evidence": LEXICAL, "evidence_given": True,
                "confidence": HIGH, "from_lexical": True,
                "same_sentence": bool(pair.get("same_sentence"))})
  return out


def lexical_system_prompt():
  with open(JUDGE_LEXICAL) as f:
    return f.read()


def pool_of(row):
  """-> 1 or 2: the earliest pool a judged pair may enter, or None.

  WP1.6: only a DECIDED label becomes a bridge.  `RELATED_BUT_NO_IMPLICATION`
  and `UNCERTAIN` used to enter pool P3 as implications in both directions, on
  the grounds that something is better than nothing; measured on the pilot
  record that pool was 5 correct against 9 wrong, and the both-directions rule
  is how a judge that said "I do not know" ended up asserting two rules.  P3 is
  gone; the numbering keeps P0/P1/P2 so records stay comparable.
  """
  import graph_ablation as AB
  label, pair = row["label"], row["pair"]
  source = pair.get("source")
  if label in POOL1_LABELS:
    return 1 if source == "frontier" else 2
  # v2, after the EB ablation: `RELATED_BUT_NO_IMPLICATION` never becomes a
  # bridge — measured 5 correct against 9 wrong.  An UNCERTAIN pair FROM THE
  # FRONTIER does, in both directions, into P2: those bridges carried most of
  # the pilot's EB column, and the grader is what sorts them out.  An UNCERTAIN
  # pair from another source stays out.
  if label == UNCERTAIN and source == "frontier":
    return 2
  if AB.on(AB.REVERT_P3) and label in (RELATED, UNCERTAIN):
    return 3
  return None


def both_directions(row):
  """An UNCERTAIN pair has no direction, so it is offered as both.

  Only the frontier's UNCERTAIN pairs reach here (see `pool_of`); the pair's
  own label travels on every bridge as `graph_pair_label`, so a proof can say
  how many of its bridges rest on a pair the judge did not decide.
  """
  return [dict(row, label=lab,
               note="an undecided frontier pair, offered as both directions")
          for lab in (A_IMPLIES_B, B_IMPLIES_A)]


def _cap_order(row):
  """The deterministic order the formula cap consumes (WP1.4).

  Frontier pairs first, then by shape, then by the two names.  The pilot
  consumed the cap in the judge's SALTED order, so a P3 formula could push out
  a P1 one and which case got truncated depended on the salt.
  """
  pair = row["pair"]
  return (0 if pair.get("source") == "frontier" else 1,
          str(pair.get("shape")), str(pair.get("a")), str(pair.get("b")),
          str(row.get("pair_id")))


def constant_substitutions(row, inventory):
  """WP3.3: the same relation, with one kind constant put for the other.

  A concept pair (k1, k2) the judge called A_IMPLIES_B is about the kinds
  themselves.  When both names also stand as kind constants in an argument
  slot — `requires(?E, labeled_data)` beside `requires(?E, data)` — the
  implication carries to that slot: for every relation R holding of k1 in that
  position, R of k2 holds too.  Code writes the rule; the judge is not asked
  again.  Positive occurrences only, and the argument position must match.
  """
  pair, label = row["pair"], row["label"]
  if pair.get("kind") != "concept" or label not in (A_IMPLIES_B, EQUIVALENT,
                                                    B_IMPLIES_A):
    return []
  a, b = pair["a"], pair["b"]
  ways = ([(a, b)] if label == A_IMPLIES_B else
          [(b, a)] if label == B_IMPLIES_A else [(a, b), (b, a)])
  slots = {}
  for kind in ("relations", "roles"):
    for occ in (inventory or {}).get(kind) or []:
      if occ.get("sign") != "+":
        continue
      for side in ("left", "right"):
        term = occ.get(side)
        if isinstance(term, str) and term in (a, b):
          slots.setdefault((occ["name"], side), set()).add(term)
  out = []
  for (rel, side), terms in sorted(slots.items()):
    for src, dst in ways:
      if src not in terms:
        continue
      out.append({"relation": rel, "side": side, "from": src, "to": dst})
  return out


def substitution_rules(row, inventory, next_index):
  """The rules `constant_substitutions` describes, serialized."""
  rules, n = [], [next_index]

  def rid():
    n[0] += 1
    return "G%d" % (n[0] - 1)

  for sub in constant_substitutions(row, inventory):
    var = "?X"
    body_atom = ([sub["relation"], var, sub["from"]] if sub["side"] == "right"
                 else [sub["relation"], sub["from"], var])
    head_atom = ([sub["relation"], var, sub["to"]] if sub["side"] == "right"
                 else [sub["relation"], sub["to"], var])
    rules.append(_rule(rid(), [_lit(body_atom, "+")], _lit(head_atom, "+"),
                       row["pair"], row["label"],
                       "the kind implication carried into the %s argument of "
                       "%s (WP3.3)" % (sub["side"], sub["relation"])))
  return rules, n[0]


def role_alias_rules(inventory, s1_json, next_index):
  """WP3.4: an inanimate agent is an instrument.

  No judge call.  When a kind constant that Stage 1 does not call a person or
  an animal stands as the agent of an event, and `instrument` is wanted on the
  demand side, the same constant may fill the instrument role: a rock does not
  act, it is used.
  """
  import graph_stage2 as G2
  rules, n = [], [next_index]
  roles = (inventory or {}).get("roles") or []
  names = set(r["name"] for r in roles)
  if "agent" not in names or "instrument" not in names:
    return [], next_index
  animate = set()
  try:
    for ent in G2.stage1_entity_rows(s1_json):
      cat = str(ent.get("category") or ent.get("type") or "").lower()
      if cat in ("person", "animal", "people", "human", "organization"):
        animate.add(ent.get("id"))
  except Exception:
    pass
  seen = set()
  for occ in roles:
    if occ["name"] != "agent" or occ.get("sign") != "+":
      continue
    k = occ.get("right")
    if not isinstance(k, str) or k in animate or k in seen:
      continue
    if not is_kind_constant_name(k, inventory):
      continue
    seen.add(k)
    n[0] += 1
    rule = _rule("G%d" % (n[0] - 1),
                 [_lit(["agent", "?E", k], "+")],
                 _lit(["instrument", "?E", k], "+"),
                 {"a": "agent", "b": "instrument", "kind": "role",
                  "pair_id": "R%d" % n[0], "source": "role_alias",
                  "a_literals": [["agent", "?E", k]],
                  "b_literals": [["instrument", "?E", k]]},
                 A_IMPLIES_B,
                 "an inanimate agent may be the instrument (WP3.4)")
    rule["evidence"] = LEXICAL
    rule["confidence"] = HIGH
    rule["graph_pair_label"] = A_IMPLIES_B
    rules.append(rule)
  return rules, n[0]


def is_kind_constant_name(name, inventory):
  return name in set((inventory or {}).get("kind_constant_names") or ())


def build_pools(judged, cap=MAX_BRIDGE_FORMULAS, inventory=None,
                s1_json=None):
  """-> ({pool: [rules]}, the omissions, the label tally).

  The pools are cumulative: P2 contains P1's rules.  There is no P3.  With an
  inventory the two judge-free shapes of WP3 are added: the kind implication
  carried into a relation's argument slot, and the inanimate agent that may be
  an instrument.
  """
  import graph_ablation as AB
  top = 3 if AB.on(AB.REVERT_P3) else 2
  tally, omitted = {}, []
  by_pool, index, seen = dict((n, []) for n in range(1, top + 1)), 1, set()
  for row in judged:
    tally[row["label"]] = tally.get(row["label"], 0) + 1
  for row in sorted(judged, key=_cap_order):
    pool = pool_of(row)
    if pool is None:
      continue
    rows = ([row] if row["label"] in POOL1_LABELS else both_directions(row))
    for one in rows:
      built, skipped, index = serialize(one, index)
      omitted.extend(skipped)
      _place(built, one, row, pool, by_pool, seen, omitted, cap, top)
    if inventory is not None and row["label"] in POOL1_LABELS:
      built, index = substitution_rules(row, inventory, index)
      _place(built, row, row, pool, by_pool, seen, omitted, cap, top)
  if inventory is not None:
    built, index = role_alias_rules(inventory, s1_json, index)
    for rule in built:
      _place([rule], {"evidence": LEXICAL, "confidence": HIGH},
             {"label": A_IMPLIES_B, "pair_id": rule.get("graph_pair_id")},
             1, by_pool, seen, omitted, cap, top)
  return by_pool, omitted, tally


def _place(built, one, row, pool, by_pool, seen, omitted, cap, top):
  """Put one serialization's rules into every pool from `pool` upward."""
  if True:
    for rule in built:
      # the label the JUDGE gave the pair, before both_directions rewrote it
      # to A_IMPLIES_B/B_IMPLIES_A; without it a bridge born of an UNCERTAIN
      # pair is indistinguishable from a decided one in the record
      rule["graph_pair_label"] = row.get("label")
      rule["graph_pair_id"] = row.get("pair_id")
      rule["evidence"] = one.get("evidence", BACKGROUND)
      rule["confidence"] = one.get("confidence")
      rule["same_sentence"] = bool(one.get("same_sentence"))
      rule["from_holistic"] = bool(one.get("from_holistic"))
      if rule["canonical"] in seen:
        omitted.append({"rule_id": rule["rule_id"],
                        "printed": rule["printed"],
                        "why": "the same formula is already in a pool"})
        continue
      seen.add(rule["canonical"])
      if len(seen) > cap:
        omitted.append({"rule_id": rule["rule_id"],
                        "printed": rule["printed"],
                        "why": "beyond the %d distinct bridge formulas a "
                               "case may offer" % cap})
        continue
      rule["pool"] = pool
      if PRIORITY_BY_TOKENS:
        rule["priority_by_tokens"] = len(str(one["pair"]["a"]).split("_"))
      for p in range(pool, top + 1):
        by_pool[p].append(rule)


def label_summary(judged):
  out = {}
  for row in judged:
    out[row["label"]] = out.get(row["label"], 0) + 1
  return out
