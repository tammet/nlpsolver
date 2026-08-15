"""Repairing a bridge whose body the grader called insufficient.

`NEEDS_CONDITION` is not a middle grade.  The audit of the widened run found 31
of 35 audited bridges in that class wrong as written
(`memos/MEMO_2026_08_14_wrong_proof_bridge_and_grader_audit.md`), so the class
is a request: name the missing condition, find an atom of THIS case that could
supply it, add exactly that atom to the body, and put the new rule through
compilation, a blind reassessment and gk again.

Three separations do the work:

  * the grader that describes what is missing never sees a candidate menu, and
    the selector that picks a condition never re-judges the rule.  A single call
    asked to do both defends its first answer and invents a convenient repair;
  * the menu is built by code from the case's own clauses.  The model chooses an
    id; it cannot write an atom, change a premise, or touch the conclusion;
  * a repaired bridge is a new hypothesis with a new id, its own provenance and
    its own fresh assessment.  Nothing about the original record changes.

Two corrections the audit asked for are applied here and nowhere else: only the
implication's own clauses reach gk (a conversion's population witnesses are
artefacts and must not be credited as use of the bridge), and every reported
proof comes from a final replay of exactly the reported minimal set.
"""

import collections
import copy
import json
import os
import re

import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB53
import unifier_grader_v5_5 as GR55
import unifier_grader_v5_6 as GR56
import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_3 as PR53

VERSION = "condition_repair_v5_7/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
DIAGNOSIS_PROMPT_NAME = "grade_rule_logic_v5_7_system"
SELECT_PROMPT_NAME = "select_missing_condition_v1_system"

DIRECTIONS = ("CORRECT", "WRONG", "UNCERTAIN")
SUFFICIENCY = ("YES", "NO", "UNCERTAIN")
MISSING_KINDS = ("NONE", "TYPE_RESTRICTION", "RELATION_LINK", "IDENTITY",
                 "EVENT_FACT", "SCOPE", "CONCLUSION_ITSELF", "OTHER")
REPAIRABLE_KINDS = ("TYPE_RESTRICTION", "RELATION_LINK", "IDENTITY",
                    "EVENT_FACT", "SCOPE", "OTHER")

BASE_FACT = "BASE_FACT"
SOURCE_RULE_CONCLUSION = "SOURCE_RULE_CONCLUSION"
QUESTION_ANTECEDENT = "QUESTION_ANTECEDENT"
OTHER_BRIDGE = "OTHER_BRIDGE"
SUPPLY_ORDER = (BASE_FACT, SOURCE_RULE_CONCLUSION, QUESTION_ANTECEDENT,
                OTHER_BRIDGE)

MAX_MENU = 120
MAX_CONDITIONS_PER_VARIANT = 2

_ASSESS = re.compile(r"^\s*ASSESS_LOGIC\s+(\S+)\s*$", re.I)
_REPAIR = re.compile(r"^\s*REPAIR\s+(\S+)\s*$", re.I)
_FIELD = re.compile(r"^\s*([A-Z_0-9]+)\s*:\s*(.*)$")
_ID = re.compile(r"\bC(\d+)\b")

sha256_of = GR55.sha256_of


def diagnosis_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % DIAGNOSIS_PROMPT_NAME)) as f:
        return f.read()


def select_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SELECT_PROMPT_NAME)) as f:
        return f.read()


# ------------------------------------------------------- reading an atom

_VOWELS = "aeiou"


def _article(word):
    return "an" if str(word)[:1].lower() in _VOWELS else "a"


def _term(t):
    """One argument, as it is read in a sentence."""
    if isinstance(t, str):
        return t
    if isinstance(t, list) and t and str(t[0]) == "eventprop":
        return "the %s %s" % (str(t[1]).lstrip("$"), _term(t[2])) \
            if len(t) > 2 else P51.printed_atom(t)
    return P51.printed_atom(t)


def reads_as(atom, negated=False):
    """A deterministic English reading of one atom.  Code writes every word.

    Unknown shapes keep their JSON: an invented paraphrase of a predicate this
    module does not know would be a guess about meaning, which is the one thing
    the whole experiment must not do.
    """
    pred = str(atom[0]) if isinstance(atom, list) and atom else ""
    args = list(atom[1:]) if isinstance(atom, list) else []
    got = None
    if pred == "isa" and len(args) == 2:
        got = "%s is %s %s" % (_term(args[1]), _article(args[0]),
                               _term(args[0]))
    elif pred == "has type" and len(args) == 2:
        got = "%s is of type %s" % (_term(args[0]), _term(args[1]))
    elif pred == "has property" and len(args) == 2:
        got = "%s is %s" % (_term(args[1]), _term(args[0]))
    elif pred == "has degree property" and len(args) == 4:
        got = "%s is %s to degree %s, relative to %s" % (
            _term(args[1]), _term(args[0]), _term(args[2]), _term(args[3]))
    elif pred == "is rel2" and len(args) == 3:
        got = "%s %s %s" % (_term(args[1]), _term(args[0]), _term(args[2]))
    elif pred == "has part" and len(args) == 2:
        got = "%s has %s" % (_term(args[0]), _term(args[1]))
    elif pred == "have" and len(args) == 2:
        got = "%s has %s" % (_term(args[0]), _term(args[1]))
    elif pred in ("has actor", "has target", "has recipient", "has topic",
                  "has manner", "has location") and len(args) >= 2:
        got = "%s has %s %s" % (_term(args[0]), pred.split(" ", 1)[1],
                                _term(args[1]))
    elif pred == "member" and len(args) == 2:
        got = "%s is a member of %s" % (_term(args[1]), _term(args[0]))
    if got is None:
        got = P51.printed_atom(atom)
        return ("it is not the case that %s" % got) if negated else got
    if negated:
        got = "it is not the case that %s" % got
    return got


def _sentence(text):
    text = text.strip()
    if not text:
        return text
    return text[0].upper() + text[1:] + ("" if text.endswith(".") else ".")


def _wrap(text, width=74, indent="  "):
    words, lines, line = text.split(), [], indent.rstrip("\n")
    line = indent
    for word in words:
        if len(line) + len(word) + 1 > width and line.strip():
            lines.append(line.rstrip())
            line = indent + word
        else:
            line = (line + " " + word) if line.strip() else line + word
    if line.strip():
        lines.append(line.rstrip())
    return "\n".join(lines)


# ------------------------------------------------- WP2: the diagnosis call

def display(rule):
    """-> (mapping, [(role, index, atom, sign)]) under ONE variable map."""
    mapping = GR55.display_mapping(rule)
    rows, n = [], 0
    for role, lit in GR55.literals_of_rule(rule):
        atom = GR55.shown(lit["atom"], mapping)
        if role == "PREMISE":
            n += 1
            rows.append(("PREMISE", n, atom, lit.get("sign", "+")))
        else:
            rows.append(("CONCLUSION", None, atom, lit.get("sign", "+")))
    return mapping, rows


def formal_reading(rule):
    """"For any ?X and ?Y: if ..., then normally ..." — written by code."""
    mapping, rows = display(rule)
    variables = sorted(set(mapping.values()))
    premises = [reads_as(a, s == "-") for role, _n, a, s in rows
                if role == "PREMISE"]
    head = [reads_as(a, s == "-") for role, _n, a, s in rows
            if role == "CONCLUSION"]
    lead = ("For any %s: " % " and ".join(variables)) if variables else ""
    body = ", and ".join(premises) if premises else "nothing is assumed"
    return _wrap("%sif %s, then normally %s." % (lead, body,
                                                 head[0] if head else "?"))


def connection_text(rule):
    """The premise groups, in words, from the code-computed connectivity."""
    got = GR56.connectivity(rule)
    lines = []
    head_terms = [t["term"] for t in got["conclusion_terms"]
                  if not str(t["term"]).startswith("[")]
    for i, comp in enumerate(got["components"], start=1):
        members = ["premise %d" % p for p in comp["premises"]]
        shared = [t for t in comp["participants"]
                  if not str(t).startswith("[")]
        in_head = [t for t in head_terms if t in comp["participants"]]
        if in_head:
            members.append("the conclusion")
        joiner = "both" if len(members) == 2 else (
            "all" if len(members) > 2 else "only")
        terms = ", ".join(in_head or shared) or "no shared term"
        if len(members) == 1:
            lines.append("  GROUP %d: %s mentions %s."
                         % (i, members[0], terms))
        else:
            lines.append("  GROUP %d: %s %s mention %s."
                         % (i, " and ".join(members[:-1]) + " and "
                            + members[-1] if len(members) > 2
                            else " and ".join(members), joiner, terms))
    if got["component_count"] > 1:
        lines.append("  The %d groups share no term with each other."
                     % got["component_count"])
    for term in head_terms:
        row = [t for t in got["conclusion_terms"] if t["term"] == term][0]
        if not row["components"]:
            lines.append("  The conclusion's %s appears in no premise." % term)
    return "\n".join(lines) or "  The body has no premise."


def diagnosis_message(rule, view=None, displayed=None):
    """The rule, its reading, its atoms and its premise groups.  Nothing else.

    No passage, no question, no earlier grade, no missing-condition text and no
    proof: the call must be able to disagree with the assessment that sent it
    here.
    """
    mapping, rows = display(rule)
    glosses = GR55.entity_glosses(view) if view else {}
    worlds = GR55._worlds(view.get("stage2")) if view else set()
    L = ["THE RULE", "",
         "  %-4s %s" % (rule["rule_id"], GR55.printed_rule(rule, mapping)), "",
         "FORMAL READING", "", formal_reading(rule), "",
         "THE ATOMS OF THIS RULE", ""]
    for role, n, atom, sign in rows:
        label = "PREMISE %d" % n if role == "PREMISE" else "CONCLUSION"
        L.append("  %-11s %s" % (label, P51.printed_atom(atom,
                                                         negated=sign == "-")))
        reads = GR55._substituted(atom, glosses) if glosses else None
        if reads is not None:
            L.append("              READS AS: %s"
                     % P51.printed_atom(reads, negated=sign == "-"))
        if view is not None:
            group = GR55.group_for(atom, displayed or [])
            for line in GR56.atom_glosses(view, atom, group, glosses, worlds):
                if line != GR55.NO_GLOSS:
                    L.append("              %s" % line)
    L += ["", "HOW THE PREMISES CONNECT", "", connection_text(rule), "",
          "Write one ASSESS_LOGIC block for %s." % rule["rule_id"]]
    return "\n".join(L)


def parse_diagnosis(text, rule_id):
    """Strict.  An unreadable reply is UNCERTAIN and is never scraped."""
    fields, seen, junk = {}, None, []
    blocks = []
    for raw in (text or "").splitlines():
        m = _ASSESS.match(raw)
        if m:
            blocks.append((m.group(1).upper(), {}))
            continue
        if not blocks:
            continue
        f = _FIELD.match(raw)
        if f:
            blocks[-1][1].setdefault(f.group(1).upper(), f.group(2).strip())
    for written, got in blocks:
        if written == str(rule_id).upper():
            fields, seen = got, None
            break
    else:
        if len(blocks) == 1:
            seen, fields = blocks[0][0], blocks[0][1]
            junk.append({"line": seen, "why": "the only block was written "
                                              "under %s, not %s" % (seen,
                                                                    rule_id)})
        else:
            return {"direction": None, "body_sufficient": None,
                    "missing_kind": None, "missing_about": "",
                    "missing_in_words": "", "redundant_premises": "",
                    "counterexample": "", "reason": "",
                    "explicitly_assessed": False, "written_under": None,
                    "rejected": junk, "note": "no readable ASSESS_LOGIC block"}

    def one(name, allowed):
        got = (fields.get(name) or "").strip()
        head = got.split()[0].upper().strip(".,;") if got else ""
        return head if head in allowed else None

    def free(name):
        got = (fields.get(name) or "").strip()
        return "" if GR55._noneish(got) else got[:200]
    body = one("BODY_SUFFICIENT", SUFFICIENCY)
    return {"direction": one("DIRECTION", DIRECTIONS),
            "body_sufficient": body,
            "missing_kind": one("MISSING_KIND", MISSING_KINDS),
            "missing_about": free("MISSING_ABOUT"),
            "missing_in_words": free("MISSING_IN_WORDS"),
            "redundant_premises": free("REDUNDANT_PREMISES"),
            "counterexample": free("ORDINARY_COUNTEREXAMPLE"),
            "reason": (fields.get("REASON") or "").strip()[:300],
            "explicitly_assessed": bool(body), "written_under": seen,
            "rejected": junk,
            "note": None if body else "BODY_SUFFICIENT was missing or not one "
                                      "of the three values"}


def repair_wanted(diagnosis):
    """-> (bool, why).  Only an insufficient body with a named condition."""
    if not diagnosis.get("explicitly_assessed"):
        return False, "unreadable_diagnosis"
    if diagnosis.get("direction") == "WRONG":
        return False, "direction_wrong"
    if diagnosis.get("body_sufficient") == "YES":
        return False, "body_sufficient_now"
    if diagnosis.get("body_sufficient") != "NO":
        return False, "body_sufficiency_uncertain"
    if diagnosis.get("missing_kind") == "CONCLUSION_ITSELF":
        return False, "conclusion_itself"
    if not diagnosis.get("missing_in_words"):
        return False, "no_missing_condition_named"
    return True, None


# ------------------------------------------- WP3: the condition candidates

def _target_of(clause, view):
    """The question target a question-clause literal belongs to."""
    body = clause.get("@logic") or clause.get("@question")
    for lit in UA.literals_of(body):
        pred = str(lit[0]) if isinstance(lit, list) and lit else ""
        bare = pred[1:] if pred.startswith("-") else pred
        if UA.is_control_predicate(bare):
            return bare
    return str(clause.get("@name") or "question")


def unit_texts(view):
    """-> {unit id: the sentence Stage 1 recorded for it}."""
    out = {}
    for sent in view.get("stage1") or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            if u.get("unit_id"):
                out[u["unit_id"]] = (u.get("text") or "").strip()
    return out


def _phrases_for(clause_name, texts):
    """The Stage-1 sentence a `sent_S3` clause was built from, if recorded."""
    got = re.match(r"^sent_(S\d+)", str(clause_name or ""))
    if not got:
        return []
    text = texts.get(got.group(1))
    return [text] if text else []


def question_antecedents(view):
    """-> [(atom, sign, clause, target)] for genuine question antecedents.

    A question clause is an implication only when it holds literals on BOTH
    sides of its `$defq` guard.  `Does John not have wings?` compiles to a
    clause whose content literals are all on the goal side; reading one of them
    as an available assumption would offer the negated conclusion as a repair,
    which is what the plan forbids and what the first previews exposed.
    """
    out = []
    for clause in view.get("final_clauses") or []:
        if FB53._source_kind(clause) != UA.QUESTION:
            continue
        body = clause.get("@logic") or clause.get("@question")
        guard = GR55._guard_sign(list(UA.literals_of(body)))
        if guard is None:
            continue
        content = [l for l in FB53._content_literals(clause)
                   if not FB53.is_contentless(UA.unsigned_atom(l))]
        want = "-" if guard == "-" else "+"
        antecedents = [l for l in content if UA.sign_of(l) == want]
        claims = [l for l in content if UA.sign_of(l) != want]
        if not antecedents or not claims:
            continue                    # a pure goal, not a conditional question
        target = _target_of(clause, view)
        for lit in antecedents:
            atom = PR53._display_from_literal(lit)
            if atom is None:
                continue
            if any(GR55.same_shape(atom, PR53._display_from_literal(c) or [])
                   for c in claims):
                continue                # the same atom is also the goal
            out.append((atom, UA.sign_of(lit),
                        str(clause.get("@name") or ""), target))
    return out


def suppliers(view, case_rules=(), exclude_rule_id=None):
    """Every signed atom this case could supply, with its provenance.

    Kept out on purpose: a question goal (it is what must be proved, not a
    fact), the standard axioms (no source occurrence), population witnesses,
    this run's own bridge clauses, and the bridge under repair.
    """
    out = []
    texts = unit_texts(view)
    for s in FB53.supplier_inventory(view):
        kind = {FB53.FACT: BASE_FACT,
                FB53.RULE_HEAD: SOURCE_RULE_CONCLUSION}.get(s["kind"])
        if kind is None:
            continue
        atom = PR53._display_from_literal(s["literal"])
        if atom is None:
            continue
        out.append({"atom": atom, "sign": s["sign"], "kind": kind,
                    "clause": s["clause_name"], "target": None,
                    "from_rule": None,
                    "source_phrases": _phrases_for(s["clause_name"], texts),
                    "printed": PR53.printed_atom(atom)})
    for atom, sign, clause_name, target in question_antecedents(view):
        out.append({"atom": atom, "sign": sign,
                    "kind": QUESTION_ANTECEDENT, "clause": clause_name,
                    "target": target, "from_rule": None,
                    "source_phrases": _phrases_for(clause_name, texts),
                    "printed": PR53.printed_atom(atom)})
    for other in case_rules or []:
        if other["rule_id"] == exclude_rule_id:
            continue                            # never repair itself
        mapping = GR55.display_mapping(other)
        head = other.get("head") or {}
        if not head:
            continue
        atom = GR55.shown(head["atom"], mapping)
        out.append({"atom": atom, "sign": head.get("sign", "+"),
                    "kind": OTHER_BRIDGE, "clause": None, "target": None,
                    "from_rule": other["rule_id"], "source_phrases": [],
                    "printed": P51.printed_atom(atom)})
    return out


def supplier_unifies(condition_atom, condition_sign, supplier_atom,
                     supplier_sign):
    """WP3.2: can this condition actually resolve with that supplier?

    A positive condition is compiled into the bridge clause as a NEGATIVE
    literal, so it needs a positive supplier; a negative condition needs a
    negative one.  Both sides are standardised apart first, so a variable named
    `?X` in the rule and a variable named `?X` in a clause cannot be confused.
    """
    if condition_sign != supplier_sign:
        return False, None
    left = FB53.standardise_apart(_as_clause(condition_atom), "cond")
    right = FB53.standardise_apart(_as_clause(supplier_atom), "supp")
    sub = {}
    if not FB53.unify(left, right, sub):
        return False, None
    return True, dict((k, json.dumps(v)) for k, v in sub.items())


def _as_clause(atom):
    """The display atom with `?X` names turned into clause variables."""
    def go(t):
        if isinstance(t, str):
            return "?:%s" % t[1:] if t.startswith("?") else t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def _variables_of(atom):
    out = []

    def go(t):
        if isinstance(t, str):
            if t.startswith("?") and t not in out:
                out.append(t)
        elif isinstance(t, list):
            for x in t[1:]:
                go(x)
    for a in atom[1:]:
        go(a)
    return out


def _substitute(atom, mapping):
    def go(t):
        if isinstance(t, str):
            return mapping.get(t, t)
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def condition_forms(supplier_atom, rule_variables):
    """-> every way of writing this atom with the rule's own variables.

    Only constants from the source occurrence and variables already in the
    bridge may appear, so a repair can never introduce a new object.  Repeated
    positions stay repeated: one source variable maps to one rule variable
    everywhere it occurs.
    """
    variables = _variables_of(supplier_atom)
    if not variables:
        return [(supplier_atom, {})]
    if not rule_variables:
        return []
    out, seen = [], set()
    for assignment in _assignments(variables, list(rule_variables)):
        got = _substitute(supplier_atom, assignment)
        key = P51.printed_atom(got)
        if key in seen:
            continue
        seen.add(key)
        out.append((got, dict(assignment)))
    return out


def _assignments(names, values):
    if not names:
        yield {}
        return
    head, rest = names[0], names[1:]
    for value in values:
        for got in _assignments(rest, values):
            row = {head: value}
            row.update(got)
            yield row


def _shares(atom, rule):
    """The variables and constants an atom shares with the displayed rule."""
    mapping, rows = display(rule)
    mine, theirs = set(), set()

    def collect(a, into):
        def go(t):
            if isinstance(t, str):
                into.add(t)
            elif isinstance(t, list):
                for x in t[1:]:
                    go(x)
        for x in a[1:]:
            go(x)
    collect(atom, mine)
    for _role, _n, other, _sign in rows:
        collect(other, theirs)
    return sorted(t for t in mine & theirs if not str(t).startswith("$"))


def _head_participants(rule):
    mapping, rows = display(rule)
    for role, _n, atom, _sign in rows:
        if role == "CONCLUSION":
            return [t for t in GR56.participants(atom)
                    if not str(t).startswith("[")]
    return []


def relevant(atom, rule, diagnosis, connectivity):
    """WP3.3: a candidate must do at least one useful thing.  -> (bool, why)."""
    about = [t.strip() for t in re.split(r"[,\s]+",
                                         diagnosis.get("missing_about") or "")
             if t.strip() and t.strip().upper() != "NONE"]
    mine = set(_shares(atom, rule))
    terms = set(GR56.participants(atom))
    if about and (mine & set(about) or terms & set(about)):
        return True, "named under MISSING_ABOUT"
    if mine & set(_head_participants(rule)):
        return True, "restricts a participant of the conclusion"
    if connectivity["disconnected"]:
        touched = [i for i, comp in enumerate(connectivity["components"],
                                              start=1)
                   if mine & set(comp["participants"])]
        if len(touched) > 1:
            return True, "connects premise groups %s" % ", ".join(
                str(t) for t in touched)
    if diagnosis.get("missing_kind") == "IDENTITY" and len(mine) > 1:
        return True, "supplies an identity between displayed things"
    return False, "touches nothing the diagnosis names"


def _premise_atoms(rule):
    _mapping, rows = display(rule)
    return [P51.printed_atom(a) for role, _n, a, _s in rows
            if role == "PREMISE"]


def _head_atom(rule):
    _mapping, rows = display(rule)
    for role, _n, atom, _sign in rows:
        if role == "CONCLUSION":
            return atom
    return None


def build_menu(view, rule, diagnosis, case_rules=(), compile_check=None,
               max_menu=MAX_MENU):
    """-> the deterministic candidate menu, with every exclusion named."""
    mapping, _rows = display(rule)
    rule_variables = sorted(set(mapping.values()))
    connectivity = GR56.connectivity(rule)
    head = _head_atom(rule)
    premises = set(_premise_atoms(rule))
    rows, excluded, by_key = [], [], {}
    for s in suppliers(view, case_rules, rule["rule_id"]):
        for atom, assignment in condition_forms(s["atom"], rule_variables):
            printed = P51.printed_atom(atom)
            sign = s["sign"]
            key = (printed, sign, s["kind"] if s["kind"] == QUESTION_ANTECEDENT
                   else s["kind"], s.get("target"))
            why = None
            if printed in premises and sign == "+":
                why = "duplicates an existing premise"
            elif printed in premises and sign == "-":
                why = "contradicts an existing premise"
            elif head is not None and GR55.same_shape(atom, head):
                why = ("restates the conclusion" if sign == "+"
                       else "negates the conclusion")
            elif any(v not in rule_variables for v in _variables_of(atom)):
                why = "introduces a variable the rule does not have"
            else:
                ok, reason = relevant(atom, rule, diagnosis, connectivity)
                if not ok:
                    why = reason
            if why:
                excluded.append({"printed": printed, "sign": sign,
                                 "supply": s["kind"], "why": why,
                                 "from_rule": s.get("from_rule")})
                continue
            ok, substitution = supplier_unifies(atom, sign, s["atom"],
                                                s["sign"])
            if not ok:
                excluded.append({"printed": printed, "sign": sign,
                                 "supply": s["kind"],
                                 "why": "no supplier of the required sign "
                                        "unifies with it"})
                continue
            row = by_key.get(key)
            if row is None:
                row = {"atom": atom, "sign": sign, "printed": printed,
                       "reads_as": _sentence(reads_as(atom, sign == "-")),
                       "supply": [], "sources": [], "targets": [],
                       "from_rules": [], "assignment": assignment,
                       "shares_with_rule": _shares(atom, rule),
                       "substitutions": [], "source_phrases": [],
                       "needs_another_bridge": s["kind"] == OTHER_BRIDGE}
                by_key[key] = row
                rows.append(row)
            label = s["kind"] if s["kind"] != QUESTION_ANTECEDENT \
                else "%s:%s" % (QUESTION_ANTECEDENT, s.get("target"))
            if s["kind"] == OTHER_BRIDGE:
                label = "%s:%s" % (OTHER_BRIDGE, s["from_rule"])
                if s["from_rule"] not in row["from_rules"]:
                    row["from_rules"].append(s["from_rule"])
            if label not in row["supply"]:
                row["supply"].append(label)
            if substitution not in row["substitutions"]:
                row["substitutions"].append(substitution)
            for phrase in s.get("source_phrases") or []:
                if phrase not in row["source_phrases"]:
                    row["source_phrases"].append(phrase)
            if s.get("clause") and s["clause"] not in row["sources"]:
                row["sources"].append(s["clause"])
            if s.get("target") and s["target"] not in row["targets"]:
                row["targets"].append(s["target"])
            row["needs_another_bridge"] = all(
                x.startswith(OTHER_BRIDGE) for x in row["supply"])
    for i, row in enumerate(rows, start=1):
        row["id"] = "C%d" % i          # provisional, so a trial can compile
    if compile_check is not None:
        kept = []
        for row in rows:
            ok, why = compile_check(row)
            if ok:
                kept.append(row)
            else:
                excluded.append({"printed": row["printed"], "sign": row["sign"],
                                 "supply": ",".join(row["supply"]),
                                 "why": why})
        rows = kept
    rows.sort(key=_menu_key(diagnosis, rule, connectivity))
    for i, row in enumerate(rows, start=1):
        row["id"] = "C%d" % i
    return {"candidates": rows, "excluded": excluded,
            "count": len(rows),
            "too_large": len(rows) > max_menu,
            "connectivity": connectivity,
            "rule_variables": rule_variables}


def _menu_key(diagnosis, rule, connectivity):
    about = set(t.strip() for t in
                re.split(r"[,\s]+", diagnosis.get("missing_about") or "")
                if t.strip() and t.strip().upper() != "NONE")
    head = set(_head_participants(rule))

    def key(row):
        first = min((SUPPLY_ORDER.index(x.split(":")[0])
                     for x in row["supply"]), default=len(SUPPLY_ORDER))
        named = 0 if (about and set(row["shares_with_rule"]) & about) else 1
        joins = 0 if (connectivity["disconnected"]
                      and len(set(row["shares_with_rule"]) & head) > 0) else 1
        return (first, named, joins, row["printed"], row["sign"])
    return key


# ------------------------------------------------ WP4: the selection call

def repair_message(rule, diagnosis, menu):
    """The original rule, the diagnosis, and every eligible candidate."""
    mapping, _rows = display(rule)
    L = ["ORIGINAL RULE", "",
         "  %-4s %s" % (rule["rule_id"], GR55.printed_rule(rule, mapping)), "",
         "DIAGNOSIS", "",
         "  MISSING_KIND: %s" % (diagnosis.get("missing_kind") or "NONE"),
         "  MISSING_ABOUT: %s" % (diagnosis.get("missing_about") or "NONE"),
         "  MISSING_IN_WORDS: %s" % (diagnosis.get("missing_in_words")
                                     or "NONE"), "",
         "CONDITION CANDIDATES", ""]
    for row in menu["candidates"]:
        L.append("  %-4s %s" % (row["id"],
                                P51.printed_atom(row["atom"],
                                                 negated=row["sign"] == "-")))
        L.append("       READS AS: %s" % row["reads_as"])
        L.append("       SUPPLY: %s" % ", ".join(row["supply"]))
        L.append("       SOURCE: %s" % _source_text(row))
        L.append("       SHARES WITH RULE: %s"
                 % (", ".join(row["shares_with_rule"]) or "nothing"))
        L.append("")
    last = menu["candidates"][-1]["id"] if menu["candidates"] else "C0"
    L.append("Choose conditions only from C1-%s. Write one REPAIR block for %s."
             % (last, rule["rule_id"]))
    return "\n".join(L)


def _source_text(row):
    if row.get("source_phrases"):
        return "; ".join('"%s"' % p for p in row["source_phrases"][:2])
    if row.get("from_rules"):
        return "the conclusion of proposed bridge %s" % ", ".join(
            row["from_rules"])
    if row.get("targets"):
        return "an antecedent of question target %s" % ", ".join(row["targets"])
    if row.get("sources"):
        return "clause %s of this case" % ", ".join(row["sources"][:2])
    return "this case's own clauses"


def parse_repair(text, rule_id, valid_ids):
    """Only VARIANT_1/2 and REASON_1/2 of one REPAIR block.  Ids are exact."""
    blocks, junk = [], []
    for raw in (text or "").splitlines():
        m = _REPAIR.match(raw)
        if m:
            blocks.append((m.group(1).upper(), {}))
            continue
        if not blocks:
            continue
        f = _FIELD.match(raw)
        if f:
            blocks[-1][1].setdefault(f.group(1).upper(), f.group(2).strip())
    fields, written = None, None
    for got_id, got in blocks:
        if got_id == str(rule_id).upper():
            fields = got
            break
    if fields is None and len(blocks) == 1:
        written, fields = blocks[0]
        junk.append({"line": written, "why": "the only block was written under "
                                             "%s, not %s" % (written, rule_id)})
    if fields is None:
        return {"variants": [], "explicitly_answered": False,
                "written_under": None, "rejected": junk,
                "note": "no readable REPAIR block"}
    variants, seen = [], set()
    for n in (1, 2):
        raw = fields.get("VARIANT_%d" % n) or ""
        reason = (fields.get("REASON_%d" % n) or "").strip()[:200]
        if GR55._noneish(raw):
            continue
        ids, bad = [], []
        for token in re.findall(r"\bC\d+\b", raw):
            if token in valid_ids and token not in ids:
                ids.append(token)
            elif token not in valid_ids:
                bad.append(token)
        if bad:
            junk.append({"line": raw[:120],
                         "why": "ids not in the menu: %s" % ", ".join(bad)})
        if not ids:
            junk.append({"line": raw[:120], "why": "no usable id"})
            continue
        if len(ids) > MAX_CONDITIONS_PER_VARIANT:
            junk.append({"line": raw[:120],
                         "why": "more than %d conditions"
                                % MAX_CONDITIONS_PER_VARIANT})
            continue
        key = ",".join(sorted(ids))
        if key in seen:
            junk.append({"line": raw[:120], "why": "repeats variant 1"})
            continue
        seen.add(key)
        variants.append({"variant": n, "condition_ids": ids,
                         "reason": reason})
    return {"variants": variants, "explicitly_answered": bool(blocks),
            "written_under": written, "rejected": junk,
            "note": None if variants else "no variant was selected"}


# --------------------------------------- WP5: building the repaired bridge

def repaired_rule(rule, menu, condition_ids):
    """The old body plus exactly the chosen atoms; the head byte for byte."""
    mapping, _rows = display(rule)
    inverse = dict((v, k) for k, v in mapping.items())
    by_id = dict((row["id"], row) for row in menu["candidates"])
    chosen = [by_id[i] for i in condition_ids]
    body = [copy.deepcopy(lit) for lit in rule.get("body") or []]
    for row in chosen:
        body.append({"sign": row["sign"],
                     "atom": _substitute(row["atom"], inverse)})
    variables = list(rule.get("llm_variables") or [])
    got = {"rule_id": "%s+COND-%s" % (rule["rule_id"], "-".join(condition_ids)),
           "body": body, "head": copy.deepcopy(rule["head"]),
           "llm_variables": variables,
           "origin": "condition_repair_v5_7",
           "repaired_from": rule["rule_id"],
           "conditions_added": [{"id": row["id"], "printed": row["printed"],
                                 "sign": row["sign"],
                                 "supply": row["supply"],
                                 "needs_another_bridge":
                                     row["needs_another_bridge"],
                                 "from_rules": row["from_rules"]}
                                for row in chosen]}
    got["printed"] = GR55.printed_rule(got, GR55.display_mapping(got))
    got["premises"] = len(body)
    return got


def check_repaired(original, repaired, menu, condition_ids, view=None):
    """WP5's mechanical checks.  A failure names itself and stops the variant."""
    failures = []
    by_id = dict((row["id"], row) for row in menu["candidates"])
    if any(i not in by_id for i in condition_ids):
        failures.append("a selected id was not in the displayed menu")
    if not 1 <= len(condition_ids) <= MAX_CONDITIONS_PER_VARIANT:
        failures.append("a variant must add one or two conditions")
    old_body = [json.dumps(l, sort_keys=True) for l in original.get("body") or []]
    new_body = [json.dumps(l, sort_keys=True) for l in repaired.get("body") or []]
    if new_body[:len(old_body)] != old_body:
        failures.append("the original premises are not preserved unchanged")
    if len(new_body) != len(old_body) + len(condition_ids):
        failures.append("the body did not grow by exactly the chosen atoms")
    if json.dumps(repaired["head"], sort_keys=True) != json.dumps(
            original["head"], sort_keys=True):
        failures.append("the conclusion changed")
    head = _head_atom(repaired)
    for row in (by_id.get(i) for i in condition_ids):
        if row is None:
            continue
        if head is not None and GR55.same_shape(row["atom"], head) \
                and row["sign"] == original["head"].get("sign", "+"):
            failures.append("%s restates the conclusion" % row["id"])
        if row["needs_another_bridge"] and not row["from_rules"]:
            failures.append("%s claims another bridge without naming it"
                            % row["id"])
        if original["rule_id"] in (row["from_rules"] or []):
            failures.append("%s would be supplied by the rule under repair"
                            % row["id"])
    body_vars = set()
    for lit in repaired["body"]:
        body_vars |= set(_variables_of(GR55.shown(
            lit["atom"], GR55.display_mapping(repaired))))
    head_vars = set(_variables_of(GR55.shown(
        repaired["head"]["atom"], GR55.display_mapping(repaired))))
    if head_vars - body_vars:
        failures.append("the conclusion would use a variable the body never "
                        "binds")
    return {"ok": not failures, "failures": failures}


def rule_clauses_only(world):
    """WP5/audit §5: a conversion's population witnesses never reach gk."""
    allowed, dropped = set(), []
    for h in world.get("bridge_hypotheses") or []:
        allowed.update(h.get("rule_clause_names") or [])
    kept = []
    for clause in world.get("compiled_bridge_clauses") or []:
        name = str(clause.get("@name") or "")
        if name in allowed:
            kept.append(clause)
        else:
            dropped.append(name)
    return kept, dropped


def clause_health(clauses):
    """-> what the plan requires of every dynamic clause reaching gk."""
    blob = json.dumps(clauses)
    return {"has_block": "$block" in blob,
            "confidence_annotations": [c.get("@confidence") for c in clauses
                                       if c.get("@confidence") is not None],
            "clause_count": len(clauses)}
