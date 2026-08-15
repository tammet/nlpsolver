"""A narrow channel for one negative fact: two named things are not the same.

The ordinary v5.3 rule task stays positive-only.  `eb2-0127` -- *hail is a kind
of precipitation, sleet is a kind of precipitation, are hail and sleet different
kinds of precipitation?* -- cannot be answered without the one negative fact
`hail != sleet`, which the passage assumes and the translation never states.
v5.2 could not produce it by design.

This module produces that single shape and nothing else:

    ["isa", CLASS, A] AND ["isa", CLASS, B] -> NOT ["=", A, B]

and only when all of the following hold:

  * an actual question clause requires the negative equality of `A` and `B`;
  * `A` and `B` are different ground names -- not variables, not population
    witnesses, not generated terms;
  * the passage's own clauses give them ONE displayed class in common;
  * the question's English carries an explicit cue: different, distinct,
    differ, not the same.

The cue only opens the question; it is not evidence.  One short model call then
decides whether the two names necessarily denote different things, warned that
different spelling is not sufficient.  Silence is abstention, and abstention is
the default.
"""

import hashlib
import json
import os
import re

import simple_rule_parser_v5_3 as P53
import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB
import unifier_prompt_v5_1 as P51

VERSION = "unifier_distinctness_v5_3/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_distinctness_v5_3_system"

CUES = ("different", "distinct", "differ", "not the same", "unlike",
        "separate")

MAX_PAIRS = 6
RULE_PREFIX = "D"

DISTINCT_LINE = re.compile(r"^\s*DISTINCT:\s*(D\d+)\s*$", re.I)


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


# ------------------------------------------------------------- eligibility

def _is_ground_name(term):
    if not isinstance(term, str):
        return False
    if UA.is_clause_variable(term) or term.startswith("$"):
        return False
    if term.startswith("sk") or "$some" in term:
        return False
    return bool(term.strip())


def _bare(term):
    return term[2:] if isinstance(term, str) and term.startswith("#:") else term


def question_needs_distinctness(view):
    """-> [(A, B, clause name)] for every negative equality a question needs."""
    out, seen = [], set()
    for clause in view.get("final_clauses") or []:
        if FB._source_kind(clause) != UA.QUESTION:
            continue
        for lit in UA.literals_of(clause.get("@logic")
                                  or clause.get("@question")):
            if not (isinstance(lit, list) and len(lit) == 3
                    and isinstance(lit[0], str)):
                continue
            if not UA.is_equality_predicate(lit[0]) or UA.sign_of(lit) != "-":
                continue
            a, b = lit[1], lit[2]
            if not (_is_ground_name(a) and _is_ground_name(b)) or a == b:
                continue
            key = json.dumps(sorted([a, b]))
            if key in seen:
                continue
            seen.add(key)
            out.append((a, b, str(clause.get("@name") or "")))
    return out


def _source_classes(view):
    """-> {thing: {class: clause name}} from the passage's own `isa` clauses."""
    out = {}
    for clause in view.get("final_clauses") or []:
        if FB._source_kind(clause) != UA.SOURCE:
            continue
        lits = FB._content_literals(clause)
        if len(lits) != 1:
            continue
        lit = lits[0]
        atom = UA.unsigned_atom(lit)
        if UA.sign_of(lit) != "+" or str(atom[0]) != "isa" or len(atom) != 3:
            continue
        label, thing = atom[1], atom[2]
        if not isinstance(label, str) or not isinstance(thing, str):
            continue
        out.setdefault(_bare(thing), {})[label] = str(clause.get("@name") or "")
    return out


def _displayed(candidates, atom):
    for g in candidates["groups"]:
        if P53.alpha_equivalent(g["atom"], atom):
            return g["id"]
    return None


def cue_in(text):
    low = (text or "").lower()
    return [c for c in CUES if c in low]


def eligible_pairs(view, candidates, question_text):
    """-> (pairs, refusals).  Every refusal names the condition that failed."""
    pairs, refused = [], []
    cues = cue_in(question_text)
    classes = _source_classes(view)
    for a, b, clause in question_needs_distinctness(view):
        row = {"a": _bare(a), "b": _bare(b), "question_clause": clause,
               "cues": cues}
        if not cues:
            row["why_refused"] = ("the question's English carries no "
                                  "difference cue")
            refused.append(row)
            continue
        shared = sorted(set(classes.get(_bare(a), {}))
                        & set(classes.get(_bare(b), {})))
        if not shared:
            row["why_refused"] = "the passage gives them no class in common"
            refused.append(row)
            continue
        label = shared[0]
        atoms = [["isa", label, _bare(a)], ["isa", label, _bare(b)]]
        ids = [_displayed(candidates, x) for x in atoms]
        if not all(ids):
            row["why_refused"] = ("their class atoms are not both displayed "
                                  "candidates")
            row["class"] = label
            refused.append(row)
            continue
        row.update({"class": label, "class_atoms": atoms,
                    "candidate_ids": ids,
                    "class_clauses": [classes[_bare(a)][label],
                                      classes[_bare(b)][label]]})
        pairs.append(row)
    for i, row in enumerate(pairs[:MAX_PAIRS], start=1):
        row["id"] = "%s%d" % (RULE_PREFIX, i)
    return pairs[:MAX_PAIRS], refused


# ------------------------------------------------------------------ the call

def user_message(passage, question, pairs):
    lines = ["PASSAGE:", passage, "", "QUESTION:", question, "", "PAIRS:", ""]
    for row in pairs:
        lines.append("  %-4s %s  and  %s" % (row["id"], row["a"], row["b"]))
        lines.append("       the passage calls both of them: %s" % row["class"])
        lines.append("")
    lines.append("For each pair you are sure denotes two different things, "
                 "write one DISTINCT: line. Write nothing else.")
    return "\n".join(lines)


def parse_reply(text, pairs):
    """-> (affirmed ids, unreadable lines).  Silence is abstention."""
    ids = set(row["id"] for row in pairs)
    affirmed, junk = [], []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        m = DISTINCT_LINE.match(line)
        if not m:
            junk.append(line.strip()[:120])
            continue
        got = m.group(1).upper()
        if got in ids and got not in affirmed:
            affirmed.append(got)
        elif got not in ids:
            junk.append(line.strip()[:120])
    return affirmed, junk


# --------------------------------------------------------------- the rule

def build_rule(row, rule_id):
    """-> the one rule shape this channel may produce, or raise."""
    a, b, label = row["a"], row["b"], row["class"]
    if a == b:
        raise ValueError("a distinctness rule needs two different names")
    if not (_is_ground_name(a) and _is_ground_name(b)):
        raise ValueError("both names must be ground")
    if not isinstance(label, str) or not label:
        raise ValueError("the shared class must be a displayed label")
    body = [{"sign": "+", "atom": ["isa", label, a]},
            {"sign": "+", "atom": ["isa", label, b]}]
    head = {"sign": "-", "atom": ["=", a, b]}
    rule = {"rule_id": rule_id, "body": body, "head": head,
            "llm_variables": [], "premises": 2,
            "origin": "distinctness_channel_v5_3",
            "warnings": [], "variants": [],
            "candidate_matches": [{"literal": P51.printed_atom(l["atom"]),
                                   "candidate": cid, "role": "PREMISE",
                                   "priority_cost": 0,
                                   "match_kind": "distinctness_channel"}
                                  for l, cid in zip(body,
                                                    row["candidate_ids"])],
            "atoms_matching_no_candidate": [],
            "rule_priority_cost": 0,
            "role_fit": {"fits": True, "body_fits": True, "head_fits": True,
                         "body_roles": ["PREMISE", "PREMISE"],
                         "head_role": "CONSEQUENCE"},
            "distinctness_pair": {"a": a, "b": b, "class": label,
                                  "question_clause": row["question_clause"],
                                  "cues": row["cues"],
                                  "class_clauses": row.get("class_clauses")}}
    rule["canonical"] = P53.canonical(rule)
    rule["printed"] = P53.printed_rule(rule)
    return rule


def check_rule(rule):
    """-> the refusals this channel applies to its own output."""
    why = []
    head = rule["head"]
    body = rule["body"]
    if head["sign"] != "-" or not UA.is_equality_predicate(head["atom"][0]):
        why.append("the conclusion must be a negative equality")
    if len(head["atom"]) != 3:
        why.append("the equality must have exactly two terms")
    else:
        a, b = head["atom"][1], head["atom"][2]
        if a == b:
            why.append("the two terms are the same")
        if not (_is_ground_name(a) and _is_ground_name(b)):
            why.append("a term of the equality is not a ground name")
        names = set()
        for lit in body:
            atom = lit["atom"]
            if lit["sign"] != "+" or str(atom[0]) != "isa" or len(atom) != 3:
                why.append("every premise must be a positive `isa` guard")
                continue
            names.add(atom[2])
        if names != {a, b}:
            why.append("the class guards must be about exactly those two terms")
        labels = set(str(l["atom"][1]) for l in body
                     if len(l["atom"]) == 3)
        if len(labels) != 1:
            why.append("the two guards must use the same class")
    if len(body) != 2:
        why.append("a distinctness rule has exactly two guards")
    return why


def run(view, candidates, question_text, respond, case_id, start_index=1):
    """-> the record for this case's distinctness channel.  One call at most."""
    pairs, refused = eligible_pairs(view, candidates, question_text)
    rec = {"version": VERSION, "eligible": pairs, "not_eligible": refused,
           "asked": False, "rules": [], "system_prompt_name":
               SYSTEM_PROMPT_NAME,
           "system_prompt_sha256": system_prompt_sha256()}
    if not pairs:
        rec["why"] = "no question clause needs a negative equality between two "\
                     "displayed named things"
        return rec
    split = view.get("_split") or {}
    message = user_message(split.get("passage") or view.get("input_text") or "",
                           question_text, pairs)
    rec.update({"asked": True, "user_message": message,
                "user_message_sha256": hashlib.sha256(
                    message.encode()).hexdigest()})
    text, note = respond("distinct", "%s/d" % case_id, message)
    affirmed, junk = parse_reply(text, pairs)
    rec.update({"raw": text, "llm_note": note, "affirmed": affirmed,
                "unreadable_lines": junk})
    n = start_index
    for row in pairs:
        if row["id"] not in affirmed:
            continue
        try:
            rule = build_rule(row, "R%d" % n)
        except ValueError as e:
            rec.setdefault("refused_rules", []).append(
                {"pair": row["id"], "why": str(e)})
            continue
        bad = check_rule(rule)
        if bad:
            rec.setdefault("refused_rules", []).append(
                {"pair": row["id"], "printed": rule["printed"], "why": bad})
            continue
        rule["distinctness_pair"]["pair_id"] = row["id"]
        rec["rules"].append(rule)
        n += 1
    rec["next_index"] = n
    return rec
