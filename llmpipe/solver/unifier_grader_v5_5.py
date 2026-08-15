"""The corrected bridge grader: one rule per call, one variable map, real roles.

The v5.4 grader was right about what to show a judge and wrong about three
mechanical things, each of which the audit
(`memos/MEMO_2026_08_14_unifier_v5_4_audit.md`) pinned to a concrete case:

  * **variable identity was destroyed below the rule line** (§5.1).  Every atom
    was passed through `UA.display_atom` on its own, which restarts naming at
    `?X`, so `mle2-0049`'s conclusion `have(?Y, gardening skills)` was shown as
    `have(?X, gardening skills)` and the judge rejected the rule for giving the
    skills to the event.  Here one mapping is built for the whole rule, from the
    rule's own `llm_variables`, and every line reuses it;
  * **a candidate id beginning `Q` was read as "the question asserts this"**
    (§5.2).  It only ever meant question-related.  A conditional question's
    antecedent is a legitimate assumption while its consequent is being proved,
    so the roles are computed from the clauses: which side of the `$defq` guard
    a literal sits on decides `QUESTION_CONDITION` against `QUESTION_CLAIM`, and
    an atom keeps *every* role it has, not the first one found;
  * **grading was context-dependent** (§5.3).  `love(?X,?Y) -> animal lover(?X)`
    was rejected alone and accepted next to its neighbours, which silently
    restricted `?Y` to animals.  A call now carries exactly one invented rule
    and a deterministic universally quantified reading of it.

The set call is narrowed to interaction effects (§5.4); a claim that the set
manufactures a witness must name the constant, and code checks it.  The trust
class stays derived, never asked for.
"""

import hashlib
import json
import os
import re

import alignment_occurrences as AO
import unifier_abstraction as UA
import unifier_feedback_v5_3 as FB53
import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_3 as PR53

VERSION = "unifier_grader_v5_5/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
RULE_PROMPT_NAME = "grade_one_rule_v5_5_system"
SET_PROMPT_NAME = "grade_rule_set_v5_5_system"

DECISIONS = ("ACCEPT", "NEEDS_CONDITION", "UNCERTAIN", "REJECT")
DIRECTIONS = ("CORRECT", "WRONG", "UNCERTAIN")
SUFFICIENCY = ("YES", "NO", "UNCERTAIN")
BASES = ("PASSAGE", "BACKGROUND", "TRANSLATION", "NONE")
SCOPES = ("GENERAL", "THIS_CASE")
SET_VALUES = ("COHERENT", "INTERACTION_PROBLEM", "UNCERTAIN")

SUPPORTED, CONDITIONAL, UNCERTAIN, UNSUPPORTED = (
    "SUPPORTED", "CONDITIONAL", "UNCERTAIN", "UNSUPPORTED")

PASSAGE = "PASSAGE"
QUESTION_CONDITION = "QUESTION_CONDITION"
QUESTION_CLAIM = "QUESTION_CLAIM"
GENERAL_LOGIC = "GENERAL_LOGIC"
UNKNOWN_ORIGIN = "UNKNOWN_ORIGIN"
ROLES = (PASSAGE, QUESTION_CONDITION, QUESTION_CLAIM, GENERAL_LOGIC)

MAX_SOURCE_PHRASES = 3
NO_GLOSS = "NO STORED GLOSS"

# the scope escape of WP3: a stated ordinary counterexample may survive ACCEPT
# only when the answer itself says the rule is meant to hold only here
SCOPE_MARKERS = ("this passage", "this case", "outside", "in this problem",
                 "only here", "local to")

_ASSESS = re.compile(r"^\s*ASSESS\s+(R\d+)\s*$", re.I)
_FIELD = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.*)$")
_SET = re.compile(r"^\s*SET\s+(S\d+)\s*:\s*([A-Z_]+)\s*$", re.I)

_NONEISH = ("NONE", "N/A", "NA", "-", "")


def rule_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % RULE_PROMPT_NAME)) as f:
        return f.read()


def set_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SET_PROMPT_NAME)) as f:
        return f.read()


def sha256_of(text):
    return hashlib.sha256((text or "").encode()).hexdigest()


# ------------------------------------------------------ WP1: one map per rule

def literals_of_rule(rule):
    """The rule's literals in display order: body first, then the head."""
    out = []
    for lit in list(rule.get("body") or []):
        if isinstance(lit, dict):
            out.append(("PREMISE", lit))
    head = rule.get("head")
    if isinstance(head, dict):
        out.append(("CONCLUSION", head))
    return out


def display_mapping(rule):
    """-> {rule variable: `?X`, `?Y`, ...}, assigned once for the whole rule.

    The variables are the ones the parser recorded for this rule, so a fixed
    constant such as the world `W0` -- which merely looks like a variable to a
    capitalisation test -- is never renamed.
    """
    declared = list(rule.get("llm_variables") or [])
    names, out = list(declared), {}

    def go(term):
        if isinstance(term, str):
            if term in names and term not in out:
                i = len(out)
                out[term] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                             else "?V%d" % (i + 1))
            return
        if isinstance(term, list):
            for x in term[1:]:
                go(x)
    for _role, lit in literals_of_rule(rule):
        for arg in lit["atom"][1:]:
            go(arg)
    for name in declared:                        # declared but never displayed
        if name not in out:
            i = len(out)
            out[name] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                         else "?V%d" % (i + 1))
    return out


def shown(atom, mapping):
    """The atom with the rule-wide variable map applied, and nothing else."""
    def go(term):
        if isinstance(term, str):
            return mapping.get(term, term)
        if isinstance(term, list) and term:
            return [term[0]] + [go(x) for x in term[1:]]
        return term
    return [atom[0]] + [go(a) for a in atom[1:]]


def printed_rule(rule, mapping):
    """The whole rule from the same map that prints its atoms."""
    body = [P51.printed_atom(shown(lit["atom"], mapping),
                             negated=lit.get("sign") == "-")
            for role, lit in literals_of_rule(rule) if role == "PREMISE"]
    head = [P51.printed_atom(shown(lit["atom"], mapping),
                             negated=lit.get("sign") == "-")
            for role, lit in literals_of_rule(rule) if role == "CONCLUSION"]
    return "%s -> %s" % (" AND ".join(body) or "TRUE",
                         head[0] if head else "?")


def formal_reading(rule, mapping):
    """A deterministic universal reading.  No model writes this."""
    variables = [mapping[v] for v in sorted(mapping, key=lambda k: mapping[k])]
    lines = []
    if variables:
        lines.append("For every %s:" % " and ".join(variables))
    else:
        lines.append("In this case:")
    first = True
    for role, lit in literals_of_rule(rule):
        text = P51.printed_atom(shown(lit["atom"], mapping),
                                negated=lit.get("sign") == "-")
        if role == "PREMISE":
            lines.append("%s %s" % ("if" if first else "and", text))
            first = False
        else:
            lines.append("then, defeasibly, %s." % text)
    return "\n".join(lines)


# --------------------------------------------- WP2: roles, from the clauses

def _var(term):
    return isinstance(term, str) and term.startswith("?")


def _tag_right(atom):
    """The other side's variables renamed apart, so one substitution can hold
    both without a name of one side capturing a name of the other."""
    def go(t):
        if isinstance(t, str):
            return "?R:" + t[1:] if t.startswith("?") else t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def _walk(term, sub):
    seen = 0
    while _var(term) and term in sub:
        term = sub[term]
        seen += 1
        if seen > 500:                                      # pragma: no cover
            return term
    return term


def _occurs(var, term, sub):
    term = _walk(term, sub)
    if term == var:
        return True
    if isinstance(term, list):
        return any(_occurs(var, x, sub) for x in term[1:])
    return False


def _match(a, b, sub):
    """Ordinary unification of two display atoms; `?`-tokens are variables."""
    a, b = _walk(a, sub), _walk(b, sub)
    if isinstance(a, str) and isinstance(b, str) and a == b:
        return True
    if _var(a):
        if _occurs(a, b, sub):
            return False
        sub[a] = b
        return True
    if _var(b):
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
    return all(_match(x, y, sub) for x, y in zip(a[1:], b[1:]))


def same_shape(atom, other):
    """Does this rule atom and that clause atom have a common instance?"""
    if not (isinstance(atom, list) and isinstance(other, list)):
        return False
    other = _tag_right(other)
    if atom[0] != other[0] or len(atom) != len(other):
        return False
    sub = {}
    return all(_match(x, y, sub) for x, y in zip(atom[1:], other[1:]))


def _guard_sign(clause_literals):
    """`-` when the clause reads `$defq -> ...`, `+` when it reads `... | $defq`."""
    signs = set()
    for lit in clause_literals:
        pred = str(lit[0]) if isinstance(lit, list) and lit else ""
        bare = pred[1:] if pred.startswith("-") else pred
        if UA.is_control_predicate(bare):
            signs.add("-" if pred.startswith("-") else "+")
    if len(signs) == 1:
        return signs.pop()
    return None


def question_role_index(view):
    """-> ([{atom, role, printed}], [unclassified clause names]).

    A question clause is an implication written with a `$defq` guard.  With the
    guard NEGATIVE the clause says `$defq -> (body -> claim)`, so its negative
    content literals are the question's own conditions and its positive ones are
    what the question asks to be established.  With the guard POSITIVE the
    clause belongs to the refuting branch, and the polarities swap.  Without a
    guard nothing here can tell the two apart, and the atom is left unknown.
    """
    rows, unclassified = [], []
    for clause in view.get("final_clauses") or []:
        if FB53._source_kind(clause) != UA.QUESTION:
            continue
        body = clause.get("@logic") or clause.get("@question")
        lits = list(UA.literals_of(body))
        content = FB53._content_literals(clause)
        if not content:
            continue
        guard = _guard_sign(lits)
        name = str(clause.get("@name") or "")
        if guard is None:
            unclassified.append(name)
        for lit in content:
            atom = UA.unsigned_atom(lit)
            if FB53.is_contentless(atom):
                continue
            display = PR53._display_from_literal(lit)
            if display is None:
                continue
            sign = UA.sign_of(lit)
            if guard is None:
                role = UNKNOWN_ORIGIN
            elif guard == "-":
                role = QUESTION_CONDITION if sign == "-" else QUESTION_CLAIM
            else:
                role = QUESTION_CONDITION if sign == "+" else QUESTION_CLAIM
            rows.append({"atom": display, "role": role, "clause": name,
                         "printed": PR53.printed_atom(display)})
    return rows, sorted(set(unclassified))


def clause_role_index(view):
    """-> [{atom, role}] for the case's own non-question clauses.

    An atom of the passage counts wherever the passage puts it: a bare fact,
    the conclusion of a passage rule, or one of its conditions.  Only the
    converter's own products are left out -- population witnesses and the
    bridge clauses this run itself added.
    """
    rows = []
    for clause in view.get("final_clauses") or []:
        name = str(clause.get("@name") or "")
        if name.startswith(FB53.BRIDGE_CLAUSE_PREFIX):
            continue
        kind = FB53._source_kind(clause)
        if kind in (UA.QUESTION, UA.GENERATED):
            continue
        if clause.get("@sourcetype") == "populate":
            continue
        role = PASSAGE if kind == UA.SOURCE else GENERAL_LOGIC
        for lit in FB53._content_literals(clause):
            atom = UA.unsigned_atom(lit)
            if FB53.is_contentless(atom):
                continue
            display = PR53._display_from_literal(lit)
            if display is None:
                continue
            rows.append({"atom": display, "role": role, "clause": name,
                         "printed": PR53.printed_atom(display)})
    return rows


def role_index(view):
    question, unclassified = question_role_index(view)
    return {"question": question, "suppliers": clause_role_index(view),
            "unclassified_question_clauses": unclassified}


def roles_of(atom, index):
    """Every role this atom shape has, in a fixed order; never just the first."""
    found, where = set(), {}
    for row in index["suppliers"] + index["question"]:
        if same_shape(atom, row["atom"]):
            found.add(row["role"])
            where.setdefault(row["role"], row["printed"])
    ordered = [r for r in ROLES if r in found]
    if UNKNOWN_ORIGIN in found:
        ordered.append(UNKNOWN_ORIGIN)
    return (ordered or [UNKNOWN_ORIGIN]), where


# ----------------------------------------------- representation help (v5.4's)

def _units(view):
    out = []
    for sent in view.get("stage1") or []:
        if not isinstance(sent, dict):
            continue
        for u in sent.get("units") or []:
            out.append(u)
    return out


def entity_glosses(view):
    """-> {constant: [(passage words, unit id)]} from Stage 1's own entities."""
    out = {}
    for u in _units(view):
        uid = u.get("unit_id")
        for e in u.get("entities") or []:
            name = e.get("id")
            if not isinstance(name, str) or not name.strip():
                continue
            for key in (e.get("url"), name):
                if isinstance(key, str) and key.strip():
                    out.setdefault(key, [])
                    if (name, uid) not in out[key]:
                        out[key].append((name, uid))
    return out


def _worlds(stage2):
    out = set()

    def walk(node):
        if not isinstance(node, list) or not node:
            return
        if node[0] == "holds" and len(node) >= 2 and isinstance(node[1], str):
            out.add(node[1])
        for x in node[1:]:
            walk(x)
    walk(stage2)
    return out


def _constants(atom):
    out = []

    def go(t):
        if isinstance(t, str):
            if not (t.startswith("?") or t.startswith("$")):
                out.append(t)
            return
        if isinstance(t, list) and t:
            for x in t[1:]:
                go(x)
    for a in atom[1:]:
        go(a)
    return out


def _clause_kinds(view, name):
    kinds = set()
    for clause in view.get("final_clauses") or []:
        if name in json.dumps(clause.get("@logic") or clause.get("@question")):
            kinds.add(FB53._source_kind(clause))
    return kinds


def constant_gloss(view, name, glosses, worlds, label_of):
    bare = name[2:] if name.startswith("#:") else name
    stripped = re.sub(r"\s+\d+$", "", bare)
    for key in (name, bare, stripped):
        if key in glosses:
            words = glosses[key][:MAX_SOURCE_PHRASES]
            return "NAMED IN THE PASSAGE AS: %s" % ", ".join(
                '"%s" (%s)' % (w, u) for w, u in words)
    if bare.startswith("sk"):
        kinds = _clause_kinds(view, name)
        if kinds and kinds <= {UA.QUESTION}:
            unit = re.search(r"_(S\d+)_", bare)
            where = ""
            if unit:
                for u in _units(view):
                    if u.get("unit_id") == unit.group(1):
                        where = ' from "%s"' % (u.get("text") or "").strip()
            return ("QUERY-CREATED PLACEHOLDER: `%s` is a name the question "
                    "introduced%s" % (bare, where))
        if kinds:
            return ("GENERATED NAME: `%s`, created by the converter in %s "
                    "clauses" % (bare, "/".join(sorted(kinds))))
    if bare in worlds:
        return ("ENCODING CONSTANT: `%s` is a world/context name this case's "
                "Stage 2 uses" % bare)
    return None


def _substituted(atom, glosses):
    """The atom with every recorded constant replaced by its passage words."""
    changed = [False]

    def name_for(t):
        bare = t[2:] if t.startswith("#:") else t
        stripped = re.sub(r"\s+\d+$", "", bare)
        for key in (t, bare, stripped):
            if key in glosses and glosses[key]:
                got = glosses[key][0][0]
                if got != t:
                    changed[0] = True
                return got
        return t

    def go(t):
        if isinstance(t, str):
            return name_for(t) if not (t.startswith("?") or t.startswith("$")) \
                else t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    out = [atom[0]] + [go(a) for a in atom[1:]]
    return out if changed[0] else None


def _local_display(atom):
    """A clause atom printed with its own local variable names, `?U1`, `?U2`."""
    names = {}

    def go(t):
        if isinstance(t, str):
            if UA.is_clause_variable(t):
                names.setdefault(t, "?U%d" % (len(names) + 1))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def group_for(atom, displayed):
    """The displayed candidate an atom was written from, if any."""
    import simple_rule_parser_v3 as P3
    for g in displayed:
        got = g.get("atom")
        if got is None:
            got = json.loads(g["printed"])
        if P3.alpha_equivalent(got, atom):
            return g
    for g in displayed:
        got = g.get("atom") or json.loads(g["printed"])
        if str(got[0]) == str(atom[0]) and len(got) == len(atom):
            return g
    return None


def atom_help(view, atom, group, glosses, worlds):
    """-> the recorded lines for one atom, all from stored data."""
    lines = []
    label_of = set()
    slot = AO.LABEL_SLOT.get(str(atom[0]))
    if slot is not None and slot < len(atom) - 1 \
            and isinstance(atom[slot + 1], str):
        label_of.add(atom[slot + 1])
    if group:
        for alias in group.get("source_aliases") or []:
            lines.append("SOURCE WORDING: %s"
                         % P51.printed_atom(_local_display(alias)))
        for phrase in (group.get("source_phrases") or [])[:MAX_SOURCE_PHRASES]:
            lines.append('FROM: "%s" (%s)' % (phrase["text"], phrase["unit"]))
        if group.get("omitted_source_phrases"):
            lines.append("(%d more source sentences not shown)"
                         % group["omitted_source_phrases"])
        if group.get("origin_kind") == "clause_native":
            lines.append("FORM: this atom is a clause of this case exactly as "
                         "the prover received it")
    for name in _constants(atom):
        if name in label_of:
            continue
        got = constant_gloss(view, name, glosses, worlds, label_of)
        if got:
            lines.append(got)
    seen, out = set(), []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out or [NO_GLOSS]


# ------------------------------------------------------ WP3: one rule, shown

def rule_block(view, rule, displayed, glosses, worlds, index):
    """The rule and its atoms, all under ONE variable map."""
    mapping = display_mapping(rule)
    lines = ["  %-4s %s" % (rule["rule_id"], printed_rule(rule, mapping)), "",
             "FORMAL READING:", formal_reading(rule, mapping), "",
             "THE ATOMS OF THIS RULE", ""]
    for role, lit in literals_of_rule(rule):
        atom = lit["atom"]
        g = group_for(atom, displayed)
        text = P51.printed_atom(shown(atom, mapping),
                                negated=lit.get("sign") == "-")
        lines.append("  %-11s%s%s" % (role, text,
                                      "   [%s]" % g["id"] if g else ""))
        found, _where = roles_of(shown(atom, mapping), index)
        lines.append("       WHERE THIS SHAPE OCCURS: %s" % ", ".join(found))
        reads = _substituted(shown(atom, mapping), glosses)
        if reads is not None:
            lines.append("       READS AS: %s"
                         % P51.printed_atom(reads,
                                            negated=lit.get("sign") == "-"))
        for line in atom_help(view, atom, g, glosses, worlds):
            lines.append("       %s" % line)
        lines.append("")
    return "\n".join(lines).rstrip()


ROLE_LEGEND = """WHERE THIS SHAPE OCCURS tells you where an atom of this shape
appears in the stored problem, and an atom may appear in more than one place:

    PASSAGE             a clause of the passage: a fact, or a part of one of
                        the passage's own rules
    QUESTION_CONDITION  a condition of the question itself
    QUESTION_CLAIM      part of what the question asks to be established
    GENERAL_LOGIC       only in the standard axioms, not in the passage
    UNKNOWN_ORIGIN      this shape occurs nowhere in the stored problem; judge
                        the atom as written

An atom occurring in the PASSAGE is not thereby a fact: the passage may use it
as the condition of one of its own rules.

A QUESTION_CONDITION may legitimately be assumed while proving a conditional
question. Using it as a premise is not circular. A QUESTION_CLAIM is not
evidence that the claim is true."""


def rule_user_message(view, split, rule, displayed, index=None):
    """One invented rule, and no other invented rule anywhere in the message."""
    glosses = entity_glosses(view)
    worlds = _worlds(view.get("stage2"))
    index = index or role_index(view)
    L = ["PASSAGE", "", split["passage"], "",
         "QUESTION — NOT A FACT", "", split["question"], "",
         "THE INVENTED RULE", ""]
    L.append(rule_block(view, rule, displayed, glosses, worlds, index))
    L += ["", "The same variable name means the same thing everywhere in the "
              "rule, including the lines under it.", "",
          ROLE_LEGEND, "",
          "Write one ASSESS block for %s." % rule["rule_id"]]
    return "\n".join(L)


# ---------------------------------------------------------- WP3: the parsing

def _field(fields, name, allowed):
    got = (fields.get(name) or "").strip()
    head = got.split()[0].upper().strip(".,;") if got else ""
    return head if head in allowed else None


def _noneish(text):
    got = (text or "").strip().rstrip(".").upper()
    return got in _NONEISH


def parse_assessment(text, rule_id, displayed_ids):
    """Strict.  Unreadable or self-contradicting is UNCERTAIN, never ACCEPT."""
    fields, junk, seen = {}, [], False
    for raw in (text or "").splitlines():
        m = _ASSESS.match(raw)
        if m:
            if m.group(1).upper() != rule_id.upper():
                junk.append({"line": raw.strip()[:160],
                             "why": "an ASSESS block for another rule id"})
                seen = False
                continue
            seen, fields = True, {}
            continue
        if not seen:
            continue
        f = _FIELD.match(raw)
        if f:
            fields.setdefault(f.group(1).upper(), f.group(2).strip())
    if not seen:
        return {"decision": "UNCERTAIN", "direction": None,
                "body_sufficient": None, "basis": "NONE", "scope": None,
                "missing_condition": [], "missing_condition_text": "",
                "counterexample": "", "unknown_ids": [], "reason": "",
                "explicitly_assessed": False, "adjustments": [],
                "model_decision": None, "rejected": junk,
                "note": "no readable ASSESS block; UNCERTAIN is not approval "
                        "and does not delete a proof"}
    missing, unknown = [], []
    got = fields.get("MISSING_CONDITION") or ""
    if not _noneish(got):
        for token in re.findall(r"\b[A-Z]{1,2}\d+\b", got):
            (missing if token in displayed_ids else unknown).append(token)
    if unknown:
        junk.append({"line": got[:160],
                     "why": "unknown candidate id(s) %s; recorded and ignored"
                            % unknown})
    decision = _field(fields, "DECISION", DECISIONS)
    row = {"model_decision": decision,
           "decision": decision or "UNCERTAIN",
           "direction": _field(fields, "DIRECTION", DIRECTIONS),
           "body_sufficient": _field(fields, "BODY_SUFFICIENT", SUFFICIENCY),
           "basis": _field(fields, "BASIS", BASES) or "NONE",
           "scope": _field(fields, "SCOPE", SCOPES),
           "missing_condition": missing,
           "missing_condition_text": "" if _noneish(got) else got.strip()[:200],
           "counterexample": ""
           if _noneish(fields.get("ORDINARY_COUNTEREXAMPLE"))
           else (fields.get("ORDINARY_COUNTEREXAMPLE") or "").strip()[:200],
           "unknown_ids": unknown,
           "reason": (fields.get("REASON") or "").strip()[:300],
           "explicitly_assessed": bool(decision),
           "rejected": junk, "adjustments": [], "note": None}
    if not decision:
        row["note"] = ("the DECISION field was missing or not one of the four "
                       "values; UNCERTAIN is not approval")
    return consistency(row)


def consistency(row):
    """WP3's deterministic checks.  They can only lower a decision."""
    if row["decision"] != "ACCEPT":
        return row
    if row["direction"] == "WRONG":
        row["adjustments"].append("DIRECTION: WRONG cannot be ACCEPT")
        row["decision"] = "UNCERTAIN"
        return row
    if row["body_sufficient"] == "NO":
        row["adjustments"].append("BODY_SUFFICIENT: NO cannot be ACCEPT")
        row["decision"] = "NEEDS_CONDITION"
    if row["missing_condition"] or row["missing_condition_text"]:
        row["adjustments"].append("a stated missing condition cannot be ACCEPT")
        row["decision"] = "NEEDS_CONDITION"
    if row["counterexample"]:
        reason = (row["reason"] or "").lower()
        excused = row["scope"] == "THIS_CASE" and any(m in reason
                                                      for m in SCOPE_MARKERS)
        if not excused:
            row["adjustments"].append("a stated ordinary counterexample cannot "
                                      "be ACCEPT without a scope reason")
            row["decision"] = "NEEDS_CONDITION"
        else:
            row["adjustments"].append("a counterexample was stated and the "
                                      "reason places it outside the scope")
    return row


# ------------------------------------------------------ WP4: the set, narrowed

def set_user_message(view, split, set_id, rules, assessments):
    """The rules of one set with their exact individual assessments."""
    L = ["PASSAGE", "", split["passage"], "",
         "QUESTION — NOT A FACT", "", split["question"], "",
         "THE RULES OF SET %s, AS ALREADY ASSESSED ONE BY ONE" % set_id, ""]
    for r in rules:
        mapping = display_mapping(r)
        L.append("  %-4s %s" % (r["rule_id"], printed_rule(r, mapping)))
        a = assessments.get(r["rule_id"]) or {}
        L.append("       DECISION: %s   DIRECTION: %s   BODY_SUFFICIENT: %s"
                 % (a.get("decision"), a.get("direction"),
                    a.get("body_sufficient")))
        L.append("       BASIS: %s   SCOPE: %s   MISSING_CONDITION: %s"
                 % (a.get("basis"), a.get("scope"),
                    ", ".join(a.get("missing_condition") or [])
                    or (a.get("missing_condition_text") or "NONE")))
        if a.get("counterexample"):
            L.append("       ORDINARY_COUNTEREXAMPLE: %s"
                     % a["counterexample"])
        if a.get("reason"):
            L.append("       REASON: %s" % a["reason"])
        L.append("")
    L.append("Each variable name is local to its own rule.")
    L.append("")
    L.append("Write one SET block for %s." % set_id)
    return "\n".join(L)


def parse_set(text, set_id, rule_ids):
    out = {"value": "UNCERTAIN", "problem_rules": [], "constants": [],
           "introduced_by": [], "reason": "", "explicitly_assessed": False,
           "note": "no readable SET block; UNCERTAIN is not approval"}
    fields, seen = {}, False
    for raw in (text or "").splitlines():
        m = _SET.match(raw)
        if m and m.group(1).upper() == set_id.upper():
            value = m.group(2).upper()
            if value in SET_VALUES:
                out["value"], out["explicitly_assessed"] = value, True
                out["note"] = None
            seen = True
            continue
        if not seen:
            continue
        f = _FIELD.match(raw)
        if f:
            fields.setdefault(f.group(1).upper(), f.group(2).strip())
    out["problem_rules"] = [t for t in re.findall(
        r"R\d+", fields.get("PROBLEM_RULES") or "") if t in rule_ids]
    out["introduced_by"] = [t for t in re.findall(
        r"R\d+", fields.get("INTRODUCED_BY") or "") if t in rule_ids]
    got = fields.get("INTRODUCED_CONSTANTS") or ""
    if not _noneish(got):
        out["constants"] = [t.strip().strip('`"\'')
                            for t in re.split(r"[,\s]+", got.strip())
                            if t.strip().strip('`"\'')][:8]
    out["reason"] = (fields.get("REASON") or "").strip()[:300]
    return out


def _head_constants(rule):
    head = rule.get("head") or {}
    body = [lit["atom"] for _r, lit in literals_of_rule(rule)
            if _r == "PREMISE"]
    in_body = set()
    for atom in body:
        in_body.update(_constants(atom))
    return [c for c in _constants(head.get("atom") or ["x"])
            if c not in in_body]


def passage_individuals(view):
    """Every constant an asserted (non-question, non-bridge) clause mentions."""
    out = set()
    for clause in view.get("final_clauses") or []:
        if str(clause.get("@name") or "").startswith(
                FB53.BRIDGE_CLAUSE_PREFIX):
            continue
        if FB53._source_kind(clause) != UA.SOURCE:
            continue
        for lit in FB53._content_literals(clause):
            out.update(_constants(UA.unsigned_atom(lit)))
    return set(c[2:] if c.startswith("#:") else c for c in out)


def validate_manufacture(assessment, rules, view):
    """WP4: a claimed introduced constant must survive three mechanical tests."""
    by_id = dict((r["rule_id"], r) for r in rules)
    asserted = passage_individuals(view)
    checks, all_ok = [], True
    for name in assessment.get("constants") or []:
        bare = name[2:] if name.startswith("#:") else name
        heads = [rid for rid, r in by_id.items()
                 if any(bare == (c[2:] if c.startswith("#:") else c)
                        for c in _head_constants(r))]
        in_head = bool(heads)
        named = assessment.get("introduced_by") or []
        by_named = bool(set(heads) & set(named)) if named else in_head
        fresh = bare not in asserted
        ok = in_head and by_named and fresh
        all_ok = all_ok and ok
        checks.append({"constant": name, "in_a_named_rule_head": in_head,
                       "introduced_by_a_named_rule": by_named,
                       "absent_from_the_passage": fresh,
                       "rules_whose_head_introduces_it": sorted(heads),
                       "valid": ok})
    claimed = bool(assessment.get("constants"))
    rules_ok = set(assessment.get("problem_rules") or []) <= set(by_id)
    validated = (assessment.get("value") == "INTERACTION_PROBLEM"
                 and rules_ok and (all_ok if claimed else True))
    return {"constant_checks": checks, "claimed_constants": claimed,
            "problem_rules_exist": rules_ok, "validated": validated,
            "grader_error": bool(claimed and not all_ok)}


# --------------------------------------------------- WP4: the derived class

SINGLE_RULE_SET = "COHERENT (one rule; the set call is not made)"


def trust_class(rule_ids, assessments, set_assessment=None, validation=None):
    """-> (class, why).  Deterministic; never another model call."""
    decisions = [(assessments.get(r) or {}).get("decision", "UNCERTAIN")
                 for r in rule_ids]
    value = (set_assessment or {}).get("value")
    if (validation or {}).get("grader_error") and value == "INTERACTION_PROBLEM":
        value = "UNCERTAIN"                       # an unchecked witness claim
    if "REJECT" in decisions:
        return UNSUPPORTED, "a used rule was rejected"
    if "NEEDS_CONDITION" in decisions:
        return CONDITIONAL, "a used rule needs a condition it does not have"
    if "UNCERTAIN" in decisions:
        return UNCERTAIN, "a used rule is uncertain"
    if all(d == "ACCEPT" for d in decisions) and value in (None, "COHERENT"):
        return SUPPORTED, "every used rule was accepted and the set is coherent"
    if value == "INTERACTION_PROBLEM" and (validation or {}).get("validated"):
        return UNSUPPORTED, "the rules interact in a way code could confirm"
    return UNCERTAIN, "no decision covered this combination"
