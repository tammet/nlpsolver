"""What the first rules could not connect, computed from the actual clauses.

`unifier_feedback_v3` answered the same question from the candidate ROLE labels
and tested each premise on its own.  A role label is a statement about where an
atom occurs, not about what the theory can supply, and testing premises
independently calls a conjunction startable when its premises match different,
incompatible individuals.  Neither is reused here.

This module works on the clauses gk actually received:

  * the **possible suppliers** are the source facts, the heads of source rules,
    the question's own assumptions and the heads of non-generic axioms.
    Population witnesses, generic frame axioms and bridge clauses from this run
    are excluded;
  * a semantic positive premise appears NEGATED in the compiled bridge clause,
    so it is matched against an opposite-sign supplier;
  * every supplier is standardised apart, and **one substitution is carried
    across all premises of a rule**, so a body only "may start" when its
    premises can hold of the same objects at once;
  * the heads of jointly startable rules join the supplier set and the search
    repeats, bounded, so a two-step chain is visible;
  * a head is checked against the question's own content literals.

Everything it reports is a mechanical possibility, never a proof.  The words in
the record and in the message say so.
"""

import json

import unifier_abstraction as UA
import unifier_candidates_v3 as CV3
import unifier_prompt_v5 as P5
import unifier_prompt_v5_3 as PR53

VERSION = "unifier_feedback_v5_3/1.0"

FACT = "source_fact"
RULE_HEAD = "source_rule_head"
QUESTION_ASSUMPTION = "question_assumption"
AXIOM_HEAD = "axiom_head"
ATTEMPTED_HEAD = "attempted_rule_head"

SUPPLIER_KINDS = (FACT, RULE_HEAD, QUESTION_ASSUMPTION, AXIOM_HEAD,
                  ATTEMPTED_HEAD)

MAX_ASSIGNMENTS = 3            # how many joint assignments to keep per rule
MAX_STEPS = 4000               # unification attempts per rule
MAX_ROUNDS = 3                 # fixpoint rounds over attempted rule heads

BRIDGE_CLAUSE_PREFIX = "dynamic_bridge"


# ---------------------------------------------------------------- unification

def _is_var(term):
    return UA.is_clause_variable(term)


def _walk(term, sub):
    seen = 0
    while _is_var(term) and term in sub:
        term = sub[term]
        seen += 1
        if seen > 1000:                                     # pragma: no cover
            return term
    return term


def _occurs(var, term, sub):
    term = _walk(term, sub)
    if term == var:
        return True
    if isinstance(term, list):
        return any(_occurs(var, x, sub) for x in term[1:])
    return False


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


def _rename(term, tag, names):
    if isinstance(term, str):
        if _is_var(term):
            names.setdefault(term, "?:%s_%d" % (tag, len(names) + 1))
            return names[term]
        return term
    if isinstance(term, list) and term:
        return [term[0]] + [_rename(x, tag, names) for x in term[1:]]
    return term


def standardise_apart(literal, tag):
    names = {}
    return [literal[0]] + [_rename(a, tag, names) for a in literal[1:]]


# ------------------------------------------------------------- the suppliers

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
    return all(P5._all_variable_term(a) for a in args)


def printed_literal(literal):
    """The literal as the model reads atoms: content arguments, no context."""
    atom = PR53._display_from_literal(literal)
    if atom is None:
        atom = UA.display_atom(UA.unsigned_atom(literal))
    return PR53.printed_atom(atom, negated=UA.sign_of(literal) == "-")


def _content_literals(clause):
    out = []
    for lit in UA.literals_of(clause.get("@logic") or clause.get("@question")):
        if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
            continue
        if UA.is_control_predicate(lit[0]) or UA.is_equality_predicate(lit[0]):
            continue
        out.append(lit)
    return out


def _kind_of(clause, source_kind, positive_count):
    if str(clause.get("@name") or "").startswith(BRIDGE_CLAUSE_PREFIX):
        return None
    if clause.get("@sourcetype") == "populate":
        return None
    if source_kind == UA.GENERATED:
        return None
    if source_kind == UA.QUESTION:
        return QUESTION_ASSUMPTION
    if source_kind == UA.AXIOM:
        return AXIOM_HEAD
    return FACT if positive_count <= 1 else RULE_HEAD


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
        source_kind = _source_kind(clause)
        lits = _content_literals(clause)
        if not lits:
            continue
        positives = [l for l in lits if UA.sign_of(l) == "+"]
        kind = _kind_of(clause, source_kind, len(lits))
        if kind is None:
            continue
        if kind == QUESTION_ASSUMPTION and len(lits) > 1:
            # a question clause with several content literals is a disjunction
            # the refutation must still close, not something it hands over
            continue
        for lit in lits:
            atom = UA.unsigned_atom(lit)
            if is_contentless(atom):
                continue
            if len(lits) > 1 and UA.sign_of(lit) == "-" \
                    and kind in (FACT, RULE_HEAD, AXIOM_HEAD):
                continue                      # a rule's body is not a supplier
            out.append({"clause_name": name, "kind": kind,
                        "source_kind": source_kind,
                        "sign": UA.sign_of(lit), "literal": lit,
                        "printed": printed_literal(lit),
                        "from_rule": None,
                        "one_of": len(positives)})
    return out


def _source_kind(clause):
    if clause.get("@sourcetype") == "question" or "@question" in clause:
        return UA.QUESTION
    if clause.get("@sourcetype") == "populate":
        return UA.GENERATED
    import re
    if re.match(r"^sent_", str(clause.get("@name") or "")):
        return UA.SOURCE
    return UA.AXIOM


def question_literals(view):
    """The question's own content literals, both polarities."""
    out = []
    for clause in view.get("final_clauses") or []:
        if _source_kind(clause) != UA.QUESTION:
            continue
        for lit in _content_literals(clause):
            atom = UA.unsigned_atom(lit)
            if is_contentless(atom):
                continue
            out.append({"clause_name": str(clause.get("@name") or ""),
                        "sign": UA.sign_of(lit), "literal": lit,
                        "printed": printed_literal(lit)})
    seen, uniq = set(), []
    for row in out:
        key = json.dumps([row["sign"], _key(row["literal"])])
        if key in seen:
            continue
        seen.add(key)
        row["id"] = "QL%d" % (len(uniq) + 1)
        uniq.append(row)
    return uniq


def _key(literal):
    names = {}

    def go(t):
        if isinstance(t, str):
            if _is_var(t):
                names.setdefault(t, "_v%d" % len(names))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return json.dumps([literal[0]] + [go(a) for a in literal[1:]])


# --------------------------------------------------------- the joint matching

def bridge_literals(hypothesis):
    """The content literals of one compiled bridge clause."""
    out = []
    for clause in hypothesis.get("compiled_clauses") or []:
        if clause.get("@sourcetype") == "populate":
            continue
        for lit in _content_literals(clause):
            out.append(lit)
    return out


def body_and_head(hypothesis):
    """-> (the negated premises, the positive conclusion) of a bridge clause."""
    lits = bridge_literals(hypothesis)
    body = [l for l in lits if UA.sign_of(l) == "-"]
    head = [l for l in lits if UA.sign_of(l) == "+"]
    return body, head


def match_body(body, suppliers, budget=None):
    """-> {may_start, assignments, unmatched}.  One substitution throughout."""
    budget = budget if budget is not None else [MAX_STEPS]
    unmatched, per_literal = [], []
    for lit in body:
        mine = []
        for i, s in enumerate(suppliers):
            if s["sign"] == UA.sign_of(lit):
                continue                      # a premise needs the other sign
            budget[0] -= 1
            if budget[0] <= 0:
                break
            other = standardise_apart(UA.unsigned_atom(s["literal"]),
                                      "s%d" % i)
            if unify(UA.unsigned_atom(lit), other, {}):
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
            if unify(UA.unsigned_atom(body[i]), other, trial):
                walk(i + 1, trial, used + [s])
    walk(0, {}, [])
    return {"may_start": bool(found), "assignments": found, "unmatched": [],
            "truncated": budget[0] <= 0,
            "why": None if found else "every premise has a supplier of its own, "
                                      "but no single assignment satisfies them "
                                      "together"}


def head_connects(head, questions):
    """Which question content literal a conclusion could resolve with."""
    out = []
    for i, q in enumerate(questions):
        for lit in head:
            if q["sign"] == UA.sign_of(lit):
                continue
            other = standardise_apart(UA.unsigned_atom(q["literal"]), "q%d" % i)
            if unify(UA.unsigned_atom(lit), other, {}):
                out.append(q)
                break
    return out


# ------------------------------------------------------------------ the report

def report(view, hypotheses, refused=()):
    """-> the connection record for one gk submission that proved nothing."""
    suppliers = supplier_inventory(view)
    questions = question_literals(view)
    rows, reached = [], set()
    rounds = []
    pool = list(suppliers)
    for round_index in range(MAX_ROUNDS):
        added, changed = [], False
        rows = []
        for h in hypotheses:
            body, head = body_and_head(h)
            got = match_body(body, pool)
            connects = head_connects(head, questions)
            rows.append({"rule_id": h["rule_id"],
                         "printed": h.get("printed_formula"),
                         "body_may_start": got["may_start"],
                         "why_not": got.get("why"),
                         "premises_with_no_possible_supplier":
                             [printed_literal(UA.unsigned_atom(l))
                              for l in got["unmatched"]],
                         "assignments": [[{"clause": s["clause_name"],
                                           "kind": s["kind"],
                                           "printed": s["printed"]}
                                          for s in a]
                                         for a in got["assignments"]],
                         "conclusion_connects_to": [q["id"] for q in connects],
                         "conclusion_connects_printed": [q["printed"]
                                                         for q in connects],
                         "search_truncated": got["truncated"]})
            if got["may_start"]:
                for q in connects:
                    reached.add(q["id"])
                for lit in head:
                    key = json.dumps([UA.sign_of(lit), _key(lit)])
                    if key in set(json.dumps([s["sign"], _key(s["literal"])])
                                  for s in pool):
                        continue
                    added.append({"clause_name": "%s (a rule this case "
                                                 "proposed)" % h["rule_id"],
                                  "kind": ATTEMPTED_HEAD,
                                  "source_kind": "attempted",
                                  "sign": UA.sign_of(lit), "literal": lit,
                                  "printed": printed_literal(lit),
                                  "from_rule": h["rule_id"], "one_of": 1})
                    changed = True
        rounds.append({"round": round_index + 1,
                       "suppliers": len(pool),
                       "rules_that_may_start": sum(1 for r in rows
                                                   if r["body_may_start"])})
        pool = pool + added
        if not changed:
            break
    # a positive conclusion can only resolve with a NEGATIVE question literal,
    # so those are the only reachable targets worth naming
    unreached = [q for q in questions
                 if q["id"] not in reached and q["sign"] == "-"]
    return {
        "version": VERSION,
        "policy": "a possible supplier is a clause literal a premise could "
                  "resolve with; it is not a derived fact and this is not a "
                  "proof",
        "supplier_counts": _counts(suppliers),
        "suppliers": suppliers,
        "question_literals": questions,
        "rules": rows,
        "rounds": rounds,
        "question_literals_reached": sorted(reached),
        "question_literals_not_reached": [{"id": q["id"],
                                           "printed": q["printed"]}
                                          for q in unreached],
        "refused_rules": list(refused),
    }


def _counts(suppliers):
    out = {}
    for s in suppliers:
        out[s["kind"]] = out.get(s["kind"], 0) + 1
    return out


# ------------------------------------------------------------------ rendering

HEADING = "WHY THE FIRST RULES MAY NOT HAVE HELPED"
UNREACHED_HEADING = "QUESTION ATOMS NOT REACHED BY A USABLE RULE"
CLOSING = ("Use premises which the existing clauses may actually supply, and "
           "try to derive one of the unreached question atoms. These are "
           "mechanical hints, not facts and not permission to force an answer.")

MAX_SHOWN_UNREACHED = 8


def render(rec):
    lines = [HEADING, ""]
    for row in rec["rules"]:
        lines.append("  %-4s %s" % (row["rule_id"], row["printed"]))
        if row["body_may_start"]:
            lines.append("       BODY MAY START: YES (mechanical possibility, "
                         "not a proof)")
        else:
            lines.append("       BODY MAY START: NO")
            if row["premises_with_no_possible_supplier"]:
                lines.append("       NO POSSIBLE SUPPLIER FOR: %s"
                             % ", ".join(
                                 row["premises_with_no_possible_supplier"]))
            elif row["why_not"]:
                lines.append("       THE PREMISES CANNOT HOLD OF THE SAME "
                             "OBJECTS AT ONCE")
        lines.append("       CONCLUSION CAN CONNECT TO: %s"
                     % (", ".join(row["conclusion_connects_printed"])
                        if row["conclusion_connects_printed"]
                        else "nothing found"))
        lines.append("")
    for row in rec["refused_rules"]:
        lines.append("  %-4s %s" % (row.get("rule_id"), row.get("printed")))
        lines.append("       THE PROGRAM COULD NOT USE IT: %s"
                     % row.get("why"))
        lines.append("")
    unreached = rec["question_literals_not_reached"][:MAX_SHOWN_UNREACHED]
    if unreached:
        lines.append(UNREACHED_HEADING)
        lines.append("")
        for q in unreached:
            lines.append("  %-4s %s" % (q["id"], q["printed"]))
        if len(rec["question_literals_not_reached"]) > len(unreached):
            lines.append("  (%d more)"
                         % (len(rec["question_literals_not_reached"])
                            - len(unreached)))
        lines.append("")
    lines.append(CLOSING)
    return "\n".join(lines)
