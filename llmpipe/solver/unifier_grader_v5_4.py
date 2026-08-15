"""Assessing a used bridge rule, with what the pipeline itself recorded (WP1-3).

The v5.3 grader underrated real bridges for four reasons the audit named, and
each is answered here:

  * it read the whole case text, question included, under one PASSAGE heading.
    The passage and the question are separate blocks now, and the question is
    labelled as not a fact;
  * it printed a defeasible bridge as a strict implication.  The fixed prompt
    says `A -> B` means "normally, if A then B";
  * it ordered that a rule true only of this passage be graded UNCERTAIN while
    also defining the top grade as "plainly entailed by the passage".  Licensing
    and transferability are now separate fields, and SCOPE never lowers trust;
  * it had no idea what an internal identifier meant, so `…/wiki/Animal` read as
    a web page rather than the passage's own *kingdom animalia*.  Every atom now
    carries whatever the stored parse recorded for it -- the source wording it
    was converted from, the passage words behind a constant, the sentence it
    came from, whether a name is a placeholder the question created -- and
    `NO STORED GLOSS` when nothing was recorded.  Nothing is invented here and
    no model is asked to invent it.

A deletion-minimal set of two or more bridges is also assessed as one package,
because a local translation is only meaningful as a set.  The reported trust
class is then derived deterministically from the two, never by another model
call.
"""

import hashlib
import json
import os
import re

import alignment_occurrences as AO
import unifier_abstraction as UA
import unifier_prompt_v5_1 as P51

VERSION = "unifier_grader_v5_4/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
RULE_PROMPT_NAME = "grade_used_rules_v5_4_system"
SET_PROMPT_NAME = "grade_rule_set_v5_4_system"

DECISIONS = ("ACCEPT", "NEEDS_CONDITION", "UNCERTAIN", "REJECT")
BASES = ("PASSAGE", "BACKGROUND", "TRANSLATION", "NONE")
SCOPES = ("GENERAL", "THIS_CASE")
SET_VALUES = ("COHERENT", "MIXED", "UNSUPPORTED")

SUPPORTED, CONDITIONAL, UNCERTAIN, UNSUPPORTED = (
    "SUPPORTED", "CONDITIONAL", "UNCERTAIN", "UNSUPPORTED")

MAX_SOURCE_PHRASES = 3

NO_GLOSS = "NO STORED GLOSS"

_ASSESS = re.compile(r"^\s*ASSESS\s+(R\d+)\s*$", re.I)
_FIELD = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.*)$")
_SET = re.compile(r"^\s*SET\s+(S\d+)\s*:\s*([A-Z_]+)\s*$", re.I)


def rule_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % RULE_PROMPT_NAME)) as f:
        return f.read()


def set_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SET_PROMPT_NAME)) as f:
        return f.read()


def sha256_of(text):
    return hashlib.sha256((text or "").encode()).hexdigest()


# ------------------------------------------------- WP1.4: representation help

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


def question_units(view):
    return [u for u in _units(view)
            if any(w in str(u.get("type") or "").lower()
                   for w in ("question", "query"))]


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
    """Where a constant occurs in the clauses gk received."""
    import unifier_feedback_v5_3 as FB
    kinds = set()
    for clause in view.get("final_clauses") or []:
        if name in json.dumps(clause.get("@logic") or clause.get("@question")):
            kinds.add(FB._source_kind(clause))
    return kinds


def constant_gloss(view, name, glosses, worlds, label_of):
    """-> one recorded line for this constant, or None."""
    bare = name[2:] if name.startswith("#:") else name
    stripped = re.sub(r"\s+\d+$", "", bare)
    for key in (name, bare, stripped):
        if key in glosses:
            words = glosses[key][:MAX_SOURCE_PHRASES]
            return "NAMED IN THE PASSAGE AS: %s" % ", ".join(
                '"%s" (%s)' % (w, u) for w, u in words)
    if re.match(r"^skq?[_0-9]", bare) or bare.startswith("sk"):
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
    if bare in label_of:
        return None                      # a content label, not a named thing
    return None


def atom_help(view, atom, group, glosses, worlds):
    """-> the recorded lines for one atom of a used rule."""
    lines = []
    label_of = set()
    slot = AO.LABEL_SLOT.get(str(atom[0]))
    if slot is not None and slot < len(atom) - 1 \
            and isinstance(atom[slot + 1], str):
        label_of.add(atom[slot + 1])
    if group:
        for alias in group.get("source_aliases") or []:
            lines.append("SOURCE WORDING: %s"
                         % P51.printed_atom(UA.display_atom(alias)))
        for phrase in (group.get("source_phrases") or [])[:MAX_SOURCE_PHRASES]:
            lines.append('FROM: "%s" (%s)' % (phrase["text"], phrase["unit"]))
        if group.get("omitted_source_phrases"):
            lines.append("(%d more source sentences not shown)"
                         % group["omitted_source_phrases"])
        if group.get("origin_kind") == "clause_native":
            lines.append("FORM: this atom is a clause of this case exactly as "
                         "the prover received it")
    for name in _constants(atom):
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


def group_for(atom, displayed):
    """The displayed candidate an atom was written from, if any."""
    import simple_rule_parser_v3 as P3
    for g in displayed:
        shown = g.get("atom")
        if shown is None:
            shown = json.loads(g["printed"])
        if P3.alpha_equivalent(shown, atom):
            return g
    for g in displayed:
        shown = g.get("atom") or json.loads(g["printed"])
        if str(shown[0]) == str(atom[0]) and len(shown) == len(atom):
            return g
    return None


# ------------------------------------------------------------ WP2: the block

def _substituted(atom, glosses):
    """The atom with every recorded constant replaced by its passage words.

    A deterministic substitution of what Stage 1 itself stored, so an internal
    identifier cannot be read as the thing it merely looks like.
    """
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


def rule_block(view, rule, displayed, glosses, worlds):
    lines = ["  %-4s %s" % (rule["rule_id"], rule["printed"])]
    for lit in list(rule.get("body") or []) + [rule.get("head")]:
        if not isinstance(lit, dict):
            continue
        atom = lit["atom"]
        g = group_for(atom, displayed)
        shown = P51.printed_atom(UA.display_atom(atom),
                                 negated=lit.get("sign") == "-")
        lines.append("       %s%s" % (shown,
                                      "   [%s]" % g["id"] if g else ""))
        reads = _substituted(UA.display_atom(atom), glosses)
        if reads is not None:
            lines.append("           READS AS: %s"
                         % P51.printed_atom(reads,
                                            negated=lit.get("sign") == "-"))
        for line in atom_help(view, atom, g, glosses, worlds):
            lines.append("           %s" % line)
    return "\n".join(lines)


def rule_user_message(view, split, rules, displayed):
    glosses = entity_glosses(view)
    worlds = _worlds(view.get("stage2"))
    L = ["PASSAGE", "", split["passage"], "",
         "QUESTION — NOT A FACT", "", split["question"], "",
         "THE INVENTED RULES THE PROOF USED", ""]
    for r in rules:
        L.append(rule_block(view, r, displayed, glosses, worlds))
        L.append("")
    L.append("Write one ASSESS block for each of: %s."
             % ", ".join(r["rule_id"] for r in rules))
    return "\n".join(L)


def parse_assessments(text, rule_ids, displayed_ids):
    """Strict.  A missing or malformed block is UNCERTAIN, never ACCEPT."""
    out, junk = {}, []
    current, fields = None, {}

    def flush():
        if current is None:
            return
        out[current] = _clean(fields, displayed_ids, junk)
    for raw in (text or "").splitlines():
        m = _ASSESS.match(raw)
        if m:
            flush()
            current, fields = m.group(1).upper(), {}
            if current not in rule_ids:
                junk.append({"line": raw.strip()[:160],
                             "why": "unknown rule id"})
                current = None
            continue
        if current is None:
            continue
        f = _FIELD.match(raw)
        if f:
            fields[f.group(1).upper()] = f.group(2).strip()
    flush()
    for rid in rule_ids:
        out.setdefault(rid, {"decision": "UNCERTAIN", "basis": "NONE",
                             "scope": None, "missing_condition": [],
                             "reason": "", "explicitly_assessed": False,
                             "note": "no readable ASSESS block; UNCERTAIN is "
                                     "not approval and does not delete a "
                                     "proof"})
    return {"assessments": out, "rejected": junk,
            "readable": any(v["explicitly_assessed"] for v in out.values()),
            "assessed": sum(1 for v in out.values()
                            if v["explicitly_assessed"]),
            "total": len(rule_ids)}


def _clean(fields, displayed_ids, junk):
    decision = (fields.get("DECISION") or "").split()[0].upper() \
        if fields.get("DECISION") else ""
    basis = (fields.get("BASIS") or "").split()[0].upper() \
        if fields.get("BASIS") else ""
    scope = (fields.get("SCOPE") or "").split()[0].upper() \
        if fields.get("SCOPE") else ""
    missing, unknown = [], []
    for token in re.findall(r"[A-Za-z]+\d+",
                            fields.get("MISSING_CONDITION") or ""):
        if token.upper() == "NONE":
            continue
        if token in displayed_ids:
            missing.append(token)
        else:
            unknown.append(token)
    if unknown:
        junk.append({"line": fields.get("MISSING_CONDITION", "")[:160],
                     "why": "unknown candidate id(s) %s; recorded and ignored"
                            % unknown})
    ok = decision in DECISIONS
    return {"decision": decision if ok else "UNCERTAIN",
            "basis": basis if basis in BASES else "NONE",
            "scope": scope if scope in SCOPES else None,
            "missing_condition": missing,
            "unknown_ids": unknown,
            "reason": (fields.get("REASON") or "").strip()[:300],
            "explicitly_assessed": ok,
            "note": None if ok else "the DECISION field was missing or not one "
                                    "of the four values; UNCERTAIN is not "
                                    "approval"}


# ------------------------------------------------------------- WP3: the set

def set_user_message(view, split, set_id, rules, assessments):
    L = ["PASSAGE", "", split["passage"], "",
         "QUESTION — NOT A FACT", "", split["question"], "",
         "THE RULES OF SET %s" % set_id, ""]
    for r in rules:
        L.append("  %-4s %s" % (r["rule_id"], r["printed"]))
        a = assessments.get(r["rule_id"]) or {}
        L.append("       ASSESSED: %s, basis %s, scope %s%s"
                 % (a.get("decision"), a.get("basis"), a.get("scope"),
                    ", missing %s" % ", ".join(a["missing_condition"])
                    if a.get("missing_condition") else ""))
        if a.get("reason"):
            L.append("       BECAUSE: %s" % a["reason"])
        L.append("")
    L.append("Write one SET block for %s." % set_id)
    return "\n".join(L)


def parse_set(text, set_id, rule_ids):
    out = {"value": "MIXED", "unsupported_rules": [],
           "manufactures": None, "reason": "", "explicitly_assessed": False,
           "note": "no readable SET block; MIXED is not approval"}
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
            fields[f.group(1).upper()] = f.group(2).strip()
    got = fields.get("UNSUPPORTED_RULES") or ""
    out["unsupported_rules"] = [t for t in re.findall(r"R\d+", got)
                                if t in rule_ids]
    m = (fields.get("MANUFACTURES_WITNESS_OR_ANSWER") or "").upper()
    out["manufactures"] = True if m.startswith("YES") else (
        False if m.startswith("NO") else None)
    out["reason"] = (fields.get("REASON") or "").strip()[:300]
    return out


# ------------------------------------------------- WP3: the derived class

SINGLE_RULE_SET = "COHERENT (one rule; not separately assessed)"


def trust_class(rule_ids, assessments, set_assessment=None):
    """-> (class, why).  Deterministic; never another model call."""
    decisions = [(assessments.get(r) or {}).get("decision", "UNCERTAIN")
                 for r in rule_ids]
    value = (set_assessment or {}).get("value")
    if "REJECT" in decisions:
        return UNSUPPORTED, "a used rule was rejected"
    if value == "UNSUPPORTED":
        return UNSUPPORTED, "the set was assessed unsupported"
    if "NEEDS_CONDITION" in decisions:
        return CONDITIONAL, "a used rule needs a condition it does not have"
    if "UNCERTAIN" in decisions or value == "MIXED":
        return UNCERTAIN, ("a used rule is uncertain" if "UNCERTAIN"
                           in decisions else "the set is mixed")
    if all(d == "ACCEPT" for d in decisions) and value in (None, "COHERENT"):
        return SUPPORTED, "every used rule was accepted and the set is coherent"
    return UNCERTAIN, "no decision covered this combination"
