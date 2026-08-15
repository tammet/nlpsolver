"""A narrow channel for one negative implication: `A -> NOT B`.

The free-form bridge calls have produced no general negative conclusion in any
run so far, although the parser, both compiler routes and gk all handle one.
This channel is the same shape as `unifier_distinctness_v5_3`: code decides what
may be offered, the model only selects, and code builds the rule from the exact
templates.  Equality stays with the distinctness channel and is refused here.

A pair is offered only when all of these hold:

  * `B`'s NEGATIVE form is what a question needs.  A question clause carries the
    negation of the goal, so a question clause holding `B` positively is a
    question that closes when `NOT B` is derived.  The sign is read that way,
    never from a raw minus sign;
  * `A` is stated by the passage — a source fact, or the conclusion of a source
    rule — not only by a question or a population clause;
  * `A` and `B` name the same participants in the same order.  A constant must
    be the same constant; two open positions become one rule variable.  No
    participant is invented, no argument order is swapped, no constant is
    generalised;
  * both atoms are displayed candidates, so both have an exact template;
  * neither is an equality or a control predicate, the pair is not the same
    atom twice, and the passage does not already state the rule.

At most six pairs are shown, cheapest first by the existing candidate costs.
Silence or `NONE` selects nothing.
"""

import hashlib
import json
import os
import re

import simple_rule_parser_v5_3 as P53
import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB
import unifier_prompt_v5_1 as P51

VERSION = "negative_relation_v6_1/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "negative_relation_v6_1_system"

ORIGIN = "negative_relation_channel_v6_1"
RULE_PREFIX = "N"
MAX_PAIRS = 6

NEGATIVE_LINE = re.compile(r"^\s*NEGATIVE:\s*(N\d+)\s*$", re.I)
NONE_LINE = re.compile(r"^\s*NONE\s*$", re.I)


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


# ------------------------------------------------------------- eligibility

def _label_slot(atom):
    import alignment_occurrences as AO
    return AO.LABEL_SLOT.get(str(atom[0]))


def participants(atom):
    """The arguments that name things, with the content label left out."""
    slot = _label_slot(atom)
    return [a for i, a in enumerate(atom[1:]) if i != slot]


def _is_open(term):
    return isinstance(term, str) and term.startswith("?") \
        and not term.startswith("?:")


def same_participants(a_atom, b_atom):
    """-> True when the two atoms name the same things, in the same order.

    A constant must be the same constant.  Two open positions correspond, and
    become one rule variable when the rule is built.  Nothing else matches, so
    a swapped order or an invented participant is never eligible.
    """
    a, b = participants(a_atom), participants(b_atom)
    if len(a) != len(b) or not a:
        return False
    for x, y in zip(a, b):
        if _is_open(x) and _is_open(y):
            continue
        if isinstance(x, list) or isinstance(y, list):
            if json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
                return False
            continue
        if _is_open(x) or _is_open(y):
            return False
        if UA._norm_constant(str(x)) != UA._norm_constant(str(y)):
            return False
    return True


def negative_is_asked(view):
    """-> {displayed-shaped atom key: [question clause names]}.

    A question clause holds the negation of what is to be proved, so a literal
    that appears POSITIVELY there is one whose negation would close the
    question.  That is the sign logic, not a raw minus sign.
    """
    out = {}
    for clause in view.get("final_clauses") or []:
        if FB._source_kind(clause) != UA.QUESTION:
            continue
        for lit in UA.literals_of(clause.get("@logic")
                                  or clause.get("@question")):
            if not (isinstance(lit, list) and lit
                    and isinstance(lit[0], str)):
                continue
            if UA.is_control_predicate(lit[0]) \
                    or UA.is_equality_predicate(lit[0]):
                continue
            if UA.sign_of(lit) != "+":
                continue
            key = _shape(UA.unsigned_atom(lit))
            out.setdefault(key, []).append(str(clause.get("@name") or ""))
    return out


def stated_by_the_passage(view):
    """-> {shape: [clause names]} for atoms a source clause actually states.

    A source fact states its literal; a source rule states its positive
    conclusion.  A population clause and a question clause state nothing here.
    """
    out = {}
    for clause in view.get("final_clauses") or []:
        if FB._source_kind(clause) != UA.SOURCE:
            continue
        if clause.get("@sourcetype") == "populate":
            continue
        for lit in FB._content_literals(clause):
            if UA.sign_of(lit) != "+":
                continue
            if UA.is_control_predicate(lit[0]) \
                    or UA.is_equality_predicate(lit[0]):
                continue
            out.setdefault(_shape(UA.unsigned_atom(lit)), []).append(
                str(clause.get("@name") or ""))
    return out


def _shape(atom):
    """A predicate-and-label key that survives the display's own variables."""
    slot = _label_slot(atom)
    parts = [str(atom[0])]
    for i, a in enumerate(atom[1:]):
        if i == slot:
            parts.append(str(a))
    return json.dumps(parts)


def source_rule_shapes(source_rules):
    """The rules the passage already states, canonically."""
    return set(P53.source_rule_keys(source_rules or ()))


def eligible_pairs(view, candidates, source_rules=()):
    """-> (pairs, refusals).  Every refusal names the condition that failed."""
    asked = negative_is_asked(view)
    stated = stated_by_the_passage(view)
    known = source_rule_shapes(source_rules)
    rows, refused = [], []
    groups = candidates["groups"]
    for b in groups:
        b_atom = b["atom"]
        if UA.is_equality_predicate(str(b_atom[0])) \
                or UA.is_control_predicate(str(b_atom[0])):
            continue
        b_key = _shape(b_atom)
        if b_key not in asked:
            continue
        for a in groups:
            a_atom = a["atom"]
            if a["id"] == b["id"]:
                continue
            if UA.is_equality_predicate(str(a_atom[0])) \
                    or UA.is_control_predicate(str(a_atom[0])):
                continue
            row = {"a_id": a["id"], "b_id": b["id"], "a": a_atom, "b": b_atom,
                   "question_clauses": asked[b_key],
                   "cost": (a.get("cost") or a.get("priority_cost") or 0)
                   + (b.get("cost") or b.get("priority_cost") or 0)}
            a_key = _shape(a_atom)
            if a_key not in stated:
                row["why_refused"] = ("the passage does not state the premise; "
                                      "it appears only in a question or a "
                                      "population clause")
                refused.append(row)
                continue
            if a_key == b_key:
                row["why_refused"] = "the premise and the conclusion are the " \
                                     "same atom"
                refused.append(row)
                continue
            if not same_participants(a_atom, b_atom):
                row["why_refused"] = ("the two atoms do not name the same "
                                      "participants in the same order")
                refused.append(row)
                continue
            rule = _build(row, "N0")
            if P53.canonical(rule) in known:
                row["why_refused"] = "the passage already states this rule"
                refused.append(row)
                continue
            row["stated_by"] = stated[a_key]
            rows.append(row)
    rows.sort(key=lambda r: (r["cost"], r["a_id"], r["b_id"]))
    for i, row in enumerate(rows[:MAX_PAIRS], start=1):
        row["id"] = "%s%d" % (RULE_PREFIX, i)
    return rows[:MAX_PAIRS], refused


# ------------------------------------------------------------------ the rule

def _rule_atoms(a_atom, b_atom):
    """The two atoms with their open positions named by one rule variable."""
    names, out = {}, []
    for atom in (a_atom, b_atom):
        got = [atom[0]]
        slot = _label_slot(atom)
        seen = 0
        for i, arg in enumerate(atom[1:]):
            if i == slot:
                got.append(arg)
                continue
            if _is_open(arg):
                names.setdefault(seen, "?X%d" % (len(names) + 1))
                got.append(names[seen])
            else:
                got.append(arg)
            seen += 1
        out.append(got)
    return out[0], out[1]


def _build(row, rule_id):
    a_atom, b_atom = _rule_atoms(row["a"], row["b"])
    rule = {"rule_id": rule_id,
            "body": [{"sign": "+", "atom": a_atom}],
            "head": {"sign": "-", "atom": b_atom},
            "premises": 1, "origin": ORIGIN, "warnings": [], "variants": [],
            "head_sign": "-", "negative_conclusion": True,
            "candidate_matches": [
                {"literal": P51.printed_atom(a_atom), "candidate": row["a_id"],
                 "role": "PREMISE", "priority_cost": 0,
                 "match_kind": "negative_relation_channel"},
                {"literal": P51.printed_atom(b_atom, negated=True),
                 "candidate": row["b_id"], "role": "CONSEQUENCE",
                 "priority_cost": 0,
                 "match_kind": "negative_relation_channel"}],
            "atoms_matching_no_candidate": [], "rule_priority_cost": 0,
            "role_fit": {"fits": True, "body_fits": True, "head_fits": True,
                         "body_roles": ["PREMISE"],
                         "head_role": "CONSEQUENCE"},
            "negative_relation_pair": {
                "a": row["a"], "b": row["b"], "a_id": row["a_id"],
                "b_id": row["b_id"],
                "question_clauses": row.get("question_clauses"),
                "stated_by": row.get("stated_by")}}
    rule["llm_variables"] = [t for t in P53._tokens(a_atom)
                             + P53._tokens(b_atom) if str(t).startswith("?X")]
    rule["llm_variables"] = sorted(set(rule["llm_variables"]))
    rule = P53.to_rule({"body": [(l["sign"], l["atom"]) for l in rule["body"]],
                        "head": (rule["head"]["sign"], rule["head"]["atom"])}
                       ) if False else rule
    rule["canonical"] = P53.canonical(rule)
    rule["printed"] = P53.printed_rule(rule)
    return rule


def check_rule(rule):
    """-> the refusals this channel applies to its own output."""
    why = []
    head, body = rule["head"], rule["body"]
    if head["sign"] != "-":
        why.append("the conclusion must be negative")
    if UA.is_equality_predicate(str(head["atom"][0])):
        why.append("equality belongs to the distinctness channel")
    if len(body) != 1 or body[0]["sign"] != "+":
        why.append("the body must be one positive atom")
    if json.dumps(head["atom"]) == json.dumps(body[0]["atom"]):
        why.append("the conclusion is the negation of its own premise")
    body_vars = set(P53.atom_variables(body[0]["atom"],
                                       P53.rule_variables(rule)))
    free = set(P53.atom_variables(head["atom"],
                                  P53.rule_variables(rule))) - body_vars
    if free:
        why.append("the conclusion uses %s, which the body never binds"
                   % ", ".join(sorted(free)))
    return why


# ------------------------------------------------------------------ the call

def user_message(passage, question, pairs):
    lines = ["PASSAGE:", passage, "", "QUESTION:", question, "",
             "POSSIBLE NEGATIVE RULES:", ""]
    for row in pairs:
        rule = _build(row, row["id"])
        lines.append("%-4s %s" % (row["id"], rule["printed"]))
    lines += ["", "Select only normally sound negative implications."]
    return "\n".join(lines)


def parse_reply(text, pairs):
    """-> (selected ids, unreadable lines, said none).  Silence selects none."""
    ids = set(row["id"] for row in pairs)
    selected, junk, none = [], [], False
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        if NONE_LINE.match(line):
            none = True
            continue
        m = NEGATIVE_LINE.match(line)
        if not m:
            junk.append(line.strip()[:120])
            continue
        got = m.group(1).upper()
        if got in ids and got not in selected:
            selected.append(got)
        elif got not in ids:
            junk.append(line.strip()[:120])
    return selected, junk, none


def run(view, candidates, passage, question, respond, case_id,
        start_index=1, source_rules=()):
    """One selection call.  -> the rules built from the ids it selected."""
    pairs, refused = eligible_pairs(view, candidates, source_rules)
    got = {"version": VERSION, "system_prompt_name": SYSTEM_PROMPT_NAME,
           "system_prompt_sha256": system_prompt_sha256(),
           "eligible": [dict((k, v) for k, v in row.items() if k != "cost")
                        for row in pairs],
           "not_eligible": refused[:60],
           "not_eligible_total": len(refused),
           "asked": False, "rules": [], "selected": [], "unselected": [],
           "next_index": start_index}
    if not pairs:
        got["why_not_asked"] = "no pair is eligible"
        return got
    message = user_message(passage, question, pairs)
    got.update({"asked": True, "user_message": message,
                "user_message_sha256": hashlib.sha256(
                    message.encode()).hexdigest()})
    text, note = respond("negative", "%s/negative" % case_id, message)
    selected, junk, none = parse_reply(text, pairs)
    got.update({"raw": text, "llm_note": note, "unreadable_lines": junk,
                "said_none": none, "selected": selected,
                "unselected": [row["id"] for row in pairs
                               if row["id"] not in set(selected)]})
    rules, refusals = [], []
    n = start_index - 1
    for row in pairs:
        if row["id"] not in set(selected):
            continue
        n += 1
        rule = _build(row, "R%d" % n)
        why = check_rule(rule)
        if why:
            n -= 1
            refusals.append({"pair": row["id"], "printed": rule["printed"],
                             "why": why})
            continue
        rules.append(rule)
    got.update({"rules": rules, "rule_ids": [r["rule_id"] for r in rules],
                "mechanical_refusals": refusals, "next_index": n + 1})
    return got
