"""Which rules can start, on what, and in what order they are offered.

A bridge rule can only fire if something in the case can supply its premises.
This module inventories those suppliers — passage facts, rule heads, axiom
heads, question assumptions and earlier proposed rules — matches a rule body
against them with a small unifier, and computes a bounded fixpoint saying
whether each rule is startable now, startable after another rule, or not
startable at all.  The runtime uses that only to ORDER submissions; a rule that
cannot start is never deleted for it.

Reading a compiled bridge is done by provenance, not by clause sign.  For
`A -> NOT B` every literal of the clause is negative, so the sign split that
served positive rules would call both literals premises and find no conclusion.
`body_and_head_by_sign` is that older reading, kept because a hypothesis
compiled before provenance existed still needs it.
"""

import collections
import json

import litbridge_atoms as atoms
import litbridge_rules as rules


# --------------------------------------------------------------- constants

VERSION = "litbridge_chain/2026-08-15"

SUPPLIER_QUESTION_ASSUMPTION = "question_assumption"

FACT = "source_fact"

RULE_HEAD = "source_rule_head"

AXIOM_HEAD = "axiom_head"

ATTEMPTED_HEAD = "attempted_rule_head"

MAX_ASSIGNMENTS = 3            # how many joint assignments to keep per rule

MAX_STEPS = 4000               # unification attempts per rule

MAX_ROUNDS = 3                 # fixpoint rounds over attempted rule heads

BRIDGE_CLAUSE_PREFIX = "dynamic_bridge"

CATEGORY_QUESTION_ASSUMPTION = "QUESTION_ASSUMPTION"

PASSAGE = "PASSAGE"

GENERAL_LOGIC = "GENERAL_LOGIC"

EARLIER_PROPOSED_RULE = "EARLIER_PROPOSED_RULE"

CATEGORY_OF = {FACT: PASSAGE, RULE_HEAD: PASSAGE,
               AXIOM_HEAD: GENERAL_LOGIC,
               SUPPLIER_QUESTION_ASSUMPTION: CATEGORY_QUESTION_ASSUMPTION,
               ATTEMPTED_HEAD: EARLIER_PROPOSED_RULE}

STARTABLE_NOW = "STARTABLE_NOW"

STARTABLE_AFTER = "STARTABLE_AFTER"

NOT_STARTABLE = "NOT_STARTABLE"


# ------------------------------------------------ what the case can supply

def supplier_inventory(view):
  """-> the literals a bridge premise could resolve with, with provenance.

  An approximation, and named as one: a clause the theory holds is not the
  same thing as a fact the prover has derived.
  """
  out = []
  for clause in view.get("final_clauses") or []:
    name = str(clause.get("@name") or "")
    if name.startswith(BRIDGE_CLAUSE_PREFIX):
      continue
    source_kind = atoms._source_kind(clause)
    lits = atoms._content_literals(clause)
    if not lits:
      continue
    positives = [l for l in lits if atoms.sign_of(l) == "+"]
    kind = _kind_of(clause, source_kind, len(lits))
    if kind is None:
      continue
    if kind == SUPPLIER_QUESTION_ASSUMPTION and len(lits) > 1:
      # a question clause with several content literals is a disjunction
      # the refutation must still close, not something it hands over
      continue
    for lit in lits:
      atom = atoms.unsigned_atom(lit)
      if is_contentless(atom):
        continue
      if len(lits) > 1 and atoms.sign_of(lit) == "-" \
              and kind in (FACT, RULE_HEAD, AXIOM_HEAD):
        continue                      # a rule's body is not a supplier
      out.append({"clause_name": name, "kind": kind,
                  "source_kind": source_kind,
                  "sign": atoms.sign_of(lit), "literal": lit,
                  "printed": printed_literal(lit),
                  "from_rule": None,
                  "one_of": len(positives)})
  return out

def categorise(suppliers):
  """One honest label per possible supplier; nothing is merged."""
  out = []
  for s in suppliers:
    row = dict(s)
    row["category"] = CATEGORY_OF.get(s["kind"], GENERAL_LOGIC)
    out.append(row)
  return out

def _kind_of(clause, source_kind, positive_count):
  if str(clause.get("@name") or "").startswith(BRIDGE_CLAUSE_PREFIX):
    return None
  if clause.get("@sourcetype") == "populate":
    return None
  if source_kind == atoms.GENERATED:
    return None
  if source_kind == atoms.QUESTION:
    return SUPPLIER_QUESTION_ASSUMPTION
  if source_kind == atoms.AXIOM:
    return AXIOM_HEAD
  return FACT if positive_count <= 1 else RULE_HEAD

def bridge_literals(hypothesis):
  """The content literals of one compiled bridge clause."""
  out = []
  for clause in hypothesis.get("compiled_clauses") or []:
    if clause.get("@sourcetype") == "populate":
      continue
    for lit in atoms._content_literals(clause):
      out.append(lit)
  return out

def is_contentless(atom):
  """A generic frame shape: every argument is a variable, or a generated term
  over variables.

  `unifier_candidates_v3._is_generic` only checks top-level variables, so the
  `frm_rel2_event` axiom -- which gives EVERY relation an event with a type,
  an actor and a target -- would otherwise make every reified premise look
  suppliable.  That is the false "may start" for `eb2-0009`.
  """
  args = list(atom[1:])
  if not args:
    return True
  return all(atoms._all_variable_term(a) for a in args)


# ----------------------------------- matching a body against the suppliers

def match_body(body, suppliers, budget=None):
  """-> {may_start, assignments, unmatched}.  One substitution throughout."""
  budget = budget if budget is not None else [MAX_STEPS]
  unmatched, per_literal = [], []
  for lit in body:
    mine = []
    for i, s in enumerate(suppliers):
      if s["sign"] == atoms.sign_of(lit):
        continue                      # a premise needs the other sign
      budget[0] -= 1
      if budget[0] <= 0:
        break
      other = standardise_apart(atoms.unsigned_atom(s["literal"]),
                                "s%d" % i)
      if unify(atoms.unsigned_atom(lit), other, {}):
        mine.append((i, s, other))
    per_literal.append(mine)
    if not mine:
      unmatched.append(lit)
  if unmatched:
    return {"may_start": False, "assignments": [], "unmatched": unmatched,
            "truncated": budget[0] <= 0}
  found = []

  def walk(i, sub, used):
    if len(found) >= MAX_ASSIGNMENTS or budget[0] <= 0:
      return
    if i >= len(body):
      found.append(list(used))
      return
    for _idx, s, other in per_literal[i]:
      budget[0] -= 1
      if budget[0] <= 0:
        return
      trial = dict(sub)
      if unify(atoms.unsigned_atom(body[i]), other, trial):
        walk(i + 1, trial, used + [s])
  walk(0, {}, [])
  return {"may_start": bool(found), "assignments": found, "unmatched": [],
          "truncated": budget[0] <= 0,
          "why": None if found else "every premise has a supplier of its own, "
                                    "but no single assignment satisfies them "
                                    "together"}

def unify(a, b, sub):
  """Ordinary unification over CLAUSE variables, with an occurs check.

  A capitalised constant such as the world `W0` is a constant here, not a
  variable: only `?:` names are variables in a clause.
  """
  a, b = _walk(a, sub), _walk(b, sub)
  if isinstance(a, str) and isinstance(b, str) and a == b:
    return True
  if _is_var(a):
    if _occurs(a, b, sub):
      return False
    sub[a] = b
    return True
  if _is_var(b):
    if _occurs(b, a, sub):
      return False
    sub[b] = a
    return True
  if isinstance(a, str) or isinstance(b, str):
    return a == b
  if not (isinstance(a, list) and isinstance(b, list)):
    return False
  if a[0] != b[0] or len(a) != len(b):
    return False
  return all(unify(x, y, sub) for x, y in zip(a[1:], b[1:]))

def standardise_apart(literal, tag):
  names = {}
  return [literal[0]] + [_rename(a, tag, names) for a in literal[1:]]

def _rename(term, tag, names):
  if isinstance(term, str):
    if _is_var(term):
      names.setdefault(term, "?:%s_%d" % (tag, len(names) + 1))
      return names[term]
    return term
  if isinstance(term, list) and term:
    return [term[0]] + [_rename(x, tag, names) for x in term[1:]]
  return term

def _occurs(var, term, sub):
  term = _walk(term, sub)
  if term == var:
    return True
  if isinstance(term, list):
    return any(_occurs(var, x, sub) for x in term[1:])
  return False

def _walk(term, sub):
  seen = 0
  while _is_var(term) and term in sub:
    term = sub[term]
    seen += 1
    if seen > 1000:                                     # pragma: no cover
      return term
  return term

def _is_var(term):
  return atoms.is_clause_variable(term)


# ----------------------------------------------- reading a compiled bridge

def body_and_head(hypothesis):
  """-> (the premise literals, the conclusion literals) of a bridge clause.

  From the compiler's own record when it is there, and from the v5.3 sign
  split when it is not.
  """
  if has_provenance(hypothesis):
    return (list(hypothesis.get("body_literals") or []),
            [hypothesis["head_literal"]])
  return body_and_head_by_sign(hypothesis)

def body_and_head_by_sign(hypothesis):
  """-> (the negated premises, the positive conclusion) of a bridge clause."""
  lits = bridge_literals(hypothesis)
  body = [l for l in lits if atoms.sign_of(l) == "-"]
  head = [l for l in lits if atoms.sign_of(l) == "+"]
  return body, head

def has_provenance(hypothesis):
  return hypothesis.get("head_literal") is not None

def _head_suppliers(hypothesis, head):
  return [{"clause_name": "%s (a rule this case proposed)"
                          % hypothesis["rule_id"],
           "kind": ATTEMPTED_HEAD, "category": EARLIER_PROPOSED_RULE,
           "source_kind": "attempted", "sign": atoms.sign_of(lit),
           "literal": lit, "printed": printed_literal(lit),
           "from_rule": hypothesis["rule_id"], "one_of": 1}
          for lit in head]


# ----------------------------------------------- chain status and ordering

def chain_status(view, hypotheses, extra_hypotheses=()):
  """v5.4's bounded fixpoint, reading each bridge through `body_and_head`."""
  suppliers = categorise(supplier_inventory(view))
  pool = list(suppliers)
  pending = {}
  for h in list(hypotheses) + list(extra_hypotheses):
    body, head = body_and_head(h)
    pending[h["rule_id"]] = {"h": h, "body": body, "head": head,
                             "asked": h in hypotheses}
  status = {}
  truncated = False
  for round_index in range(MAX_ROUNDS):
    added, changed = [], False
    for rid, row in pending.items():
      if rid in status:
        continue
      got = match_body(row["body"], pool)
      truncated = truncated or got["truncated"]
      if not got["may_start"]:
        continue
      used_rules = []
      if got["assignments"]:
        used_rules = sorted(set(
            s["from_rule"] for s in got["assignments"][0]
            if s.get("from_rule")))
      status[rid] = {
          "status": STARTABLE_NOW if round_index == 0 and not used_rules
          else STARTABLE_AFTER if used_rules else STARTABLE_NOW,
          "after": used_rules,
          "premises": [{"premise": printed_literal(atoms.unsigned_atom(l)),
                        "supplier": s["printed"],
                        "category": s["category"],
                        "clause": s["clause_name"]}
                       for l, s in zip(row["body"],
                                       got["assignments"][0])]
          if got["assignments"] else [],
          "unmatched": [printed_literal(atoms.unsigned_atom(l))
                        for l in got["unmatched"]],
          "negative_conclusion": bool(
              row["h"].get("negative_conclusion")),
          "read_from": ("the compiler's head provenance"
                        if has_provenance(row["h"])
                        else "the clause sign split"),
          "round": round_index + 1}
      added.extend(_head_suppliers(row["h"], row["head"]))
      changed = True
    pool = pool + added
    if not changed:
      break
  for rid, row in pending.items():
    if rid in status:
      continue
    got = match_body(row["body"], pool)
    status[rid] = {"status": NOT_STARTABLE, "after": [],
                   "premises": [],
                   "unmatched": [printed_literal(atoms.unsigned_atom(l))
                                 for l in got["unmatched"]],
                   "negative_conclusion": bool(
                       row["h"].get("negative_conclusion")),
                   "read_from": ("the compiler's head provenance"
                                 if has_provenance(row["h"])
                                 else "the clause sign split"),
                   "why": got.get("why"), "round": None}
  return {"status": dict((k, v) for k, v in status.items()
                         if pending[k]["asked"]),
          "all_status": status,
          "search_bound_reached": truncated,
          "rounds_allowed": MAX_ROUNDS,
          "version": VERSION}

def order_by_chain(rules, status):
  """Startable now, then startable after another rule, then not startable."""
  rank = {STARTABLE_NOW: 0, STARTABLE_AFTER: 1, NOT_STARTABLE: 2}

  def key(r):
    got = (status or {}).get(r["rule_id"]) or {}
    return (rank.get(got.get("status"), 3),
            int(str(r["rule_id"])[1:] or 0))
  return sorted(rules, key=key)


# ----------------------------------------------------- the readable report

def printed_literal(literal):
  """The literal as the model reads atoms: content arguments, no context."""
  atom = atoms._display_from_literal(literal)
  if atom is None:
    atom = atoms.display_atom(atoms.unsigned_atom(literal))
  return atoms.printed_atom(atom, negated=atoms.sign_of(literal) == "-")


# --------------------------------------------------- what a proof cites

def _proof_steps(proof):
  """Normalise `proof` to a flat list of steps.

  Accepts one proof (a list of steps), several proofs (a list of lists of
  steps), or None.
  """
  if not proof:
    return []
  out = []
  for item in proof:
    if isinstance(item, list) and item and isinstance(item[0], list):
      out.extend(item)
    else:
      out.append(item)
  return out

def _names_in_step(step):
  """Clause names a proof step cites, as strings anywhere in its citation."""
  if not isinstance(step, list) or len(step) < 2:
    return []
  found = []

  def walk(x):
    if isinstance(x, list):
      for y in x:
        walk(y)
    elif isinstance(x, str):
      found.append(x)
  walk(step[1])
  return found

def cited_hypotheses(proof, provenance):
  """-> (ordered distinct hypothesis ids cited, {id: [clause names]}).

  `provenance` maps clause name -> hypothesis id.  A clause name that is not
  in it is not a bridge clause and is ignored; nothing is inferred from the
  shape of a name.
  """
  order, by_hyp = [], {}
  for step in _proof_steps(proof):
    for name in _names_in_step(step):
      hid = provenance.get(name)
      if hid is None:
        continue
      if hid not in by_hyp:
        by_hyp[hid] = []
        order.append(hid)
      if name not in by_hyp[hid]:
        by_hyp[hid].append(name)
  return order, by_hyp
