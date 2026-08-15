"""Two separate assessments: does the body suffice, and what licenses the rule.

v5.5 fixed the rendering and the role reporting, and still accepted
`folio-0143` R7 -- `isa(animal, Heck cattle) AND of(breeding back, artificial
selection) -> artificially selected(Heck cattle)`.  The reply said why: it read
"Heck cattle were bred back" out of the passage and counted it as if the body
contained it.  One model was asked to hold two questions at once, and the
passage answered the wrong one.

v5.6 splits them.

  * the **rule-only** call sees the rule, its deterministic reading, the name
    glosses of its atoms and a structural description of how its premises
    connect.  It sees no passage, no question, no other rule and no proof, so a
    fact that is not a premise is not available to import.  It answers
    DIRECTION, BODY_SUFFICIENT, MISSING_CONDITION and ORDINARY_COUNTEREXAMPLE;
  * the **passage-basis** call sees the passage, the question, the rule and the
    first answer.  It answers BASIS, SCOPE, whether a missing condition does
    occur in the passage, and the exact sentence.  It cannot change DIRECTION or
    BODY_SUFFICIENT;
  * `combine()` derives one decision from the two in code.  A condition present
    elsewhere in the passage never completes an incomplete rule.

The connectivity description is a diagnostic, not a verdict: premises that share
no participant are reported and counted, never rejected mechanically.
"""

import os
import re

import alignment_occurrences as AO
import unifier_grader_v5_5 as GR55
import unifier_prompt_v5_1 as P51

VERSION = "unifier_grader_v5_6/1.0"

PROMPT_DIR = GR55.PROMPT_DIR
LOGIC_PROMPT_NAME = "grade_rule_logic_v5_6_system"
BASIS_PROMPT_NAME = "grade_rule_basis_v5_6_system"

DIRECTIONS = GR55.DIRECTIONS
SUFFICIENCY = GR55.SUFFICIENCY
BASES = GR55.BASES
SCOPES = GR55.SCOPES
DECISIONS = GR55.DECISIONS
PRESENCE = ("YES", "NO", "NOT_APPLICABLE")

SUPPORTED, CONDITIONAL, UNCERTAIN, UNSUPPORTED = (
    GR55.SUPPORTED, GR55.CONDITIONAL, GR55.UNCERTAIN, GR55.UNSUPPORTED)

sha256_of = GR55.sha256_of
display_mapping = GR55.display_mapping
shown = GR55.shown
printed_rule = GR55.printed_rule
formal_reading = GR55.formal_reading
literals_of_rule = GR55.literals_of_rule
role_index = GR55.role_index
roles_of = GR55.roles_of
entity_glosses = GR55.entity_glosses
group_for = GR55.group_for
trust_class = GR55.trust_class
set_user_message = GR55.set_user_message
parse_set = GR55.parse_set
validate_manufacture = GR55.validate_manufacture
SINGLE_RULE_SET = GR55.SINGLE_RULE_SET

_LOGIC = re.compile(r"^\s*ASSESS_LOGIC\s+(R\d+)\s*$", re.I)
_BASIS = re.compile(r"^\s*ASSESS_BASIS\s+(R\d+)\s*$", re.I)
_FIELD = GR55._FIELD


def logic_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % LOGIC_PROMPT_NAME)) as f:
        return f.read()


def basis_system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % BASIS_PROMPT_NAME)) as f:
        return f.read()


def set_system_prompt():
    return GR55.set_system_prompt()


# ------------------------------------------------- WP1: body connectivity

def participants(atom):
    """-> the terms of an atom that stand for a thing, in order.

    The predicate name and the concept label -- `animal` in
    `["isa","animal","Heck cattle"]`, `of` in `["is rel2","of",...]` -- are not
    participants.  A nested term counts both as itself and through the terms
    inside it, so `["eventprop","$target","?Y"]` connects a premise to `?Y`.
    """
    args = list(atom[1:])
    slot = AO.LABEL_SLOT.get(str(atom[0]))
    if slot is not None and slot < len(args):
        args = args[:slot] + args[slot + 1:]
    out = []

    def go(term):
        if isinstance(term, str):
            if term.startswith("$"):
                return
            if term not in out:
                out.append(term)
            return
        if isinstance(term, list) and term:
            key = P51.printed_atom(term)
            if key not in out:
                out.append(key)
            for x in term[1:]:
                go(x)
    for a in args:
        go(a)
    return out


def connectivity(rule):
    """-> the components of the body, and where each conclusion term sits."""
    mapping = display_mapping(rule)
    premises, head = [], None
    for role, lit in literals_of_rule(rule):
        atom = shown(lit["atom"], mapping)
        row = {"atom": atom, "printed": P51.printed_atom(
            atom, negated=lit.get("sign") == "-"),
            "participants": participants(atom)}
        if role == "PREMISE":
            premises.append(row)
        else:
            head = row
    parent = list(range(len(premises)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    shared = {}
    for i, row in enumerate(premises):
        for term in row["participants"]:
            for j in shared.get(term, []):
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
            shared.setdefault(term, []).append(i)
    groups = {}
    for i in range(len(premises)):
        groups.setdefault(find(i), []).append(i)
    components = []
    for k in sorted(groups, key=lambda k: min(groups[k])):
        members = sorted(groups[k])
        terms = []
        for i in members:
            for term in premises[i]["participants"]:
                if term not in terms:
                    terms.append(term)
        components.append({"premises": [i + 1 for i in members],
                           "participants": terms})
    where = []
    for term in (head or {}).get("participants") or []:
        found = [n for n, comp in enumerate(components, start=1)
                 if term in comp["participants"]]
        where.append({"term": term, "components": found})
    return {"premises": [{"index": i + 1, "printed": r["printed"],
                          "participants": r["participants"]}
                         for i, r in enumerate(premises)],
            "conclusion": (head or {}).get("printed"),
            "components": components,
            "component_count": len(components),
            "disconnected": len(components) > 1,
            "conclusion_terms": where,
            "conclusion_terms_in_no_premise":
                [w["term"] for w in where if not w["components"]],
            "shared_by_everything": len(components) <= 1}


CONNECTIVITY_NOTE = (
    "Two premises are connected when they mention the same variable, the\n"
    "  same constant or the same nested term. A predicate name and a concept\n"
    "  label do not count. Premises in different groups constrain different\n"
    "  things.")


def _plain(terms):
    """Drop the nested terms: each is also listed through the terms inside it."""
    return [t for t in terms if not str(t).startswith("[")]


def render_connectivity(got):
    lines = ["HOW THE PREMISES CONNECT", "", "  " + CONNECTIVITY_NOTE, ""]
    if len(got["premises"]) < 2:
        lines.append("  The body has one premise, so there is nothing to "
                     "connect.")
    else:
        for comp in got["components"]:
            lines.append("  group %d: premise %s — about %s"
                         % (got["components"].index(comp) + 1,
                            ", ".join(str(i) for i in comp["premises"]),
                            ", ".join("`%s`" % t
                                      for t in _plain(comp["participants"]))))
        if got["disconnected"]:
            lines.append("  The %d premises fall into %d groups with no term "
                         "in common."
                         % (len(got["premises"]), got["component_count"]))
        else:
            lines.append("  All premises are in one group.")
    lines.append("")
    for row in got["conclusion_terms"]:
        if str(row["term"]).startswith("["):
            continue
        if row["components"]:
            lines.append("  The conclusion's `%s` appears in group %s."
                         % (row["term"],
                            ", ".join(str(n) for n in row["components"])))
        else:
            lines.append("  The conclusion's `%s` appears in no premise."
                         % row["term"])
    if not _plain([r["term"] for r in got["conclusion_terms"]]):
        lines.append("  The conclusion mentions no participant of its own.")
    return "\n".join(lines)


# --------------------------------------------------- WP2A: the rule-only call

def atom_glosses(view, atom, group, glosses, worlds):
    """The name glosses of one atom.  No passage sentence is included here.

    v5.5's `atom_help` also prints the Stage-1 sentence each atom was built
    from.  A sentence is exactly the thing the rule-only call must not see: on
    `folio-0143` it would hand over "Heck cattle were bred back in the 1920s".
    """
    lines = []
    label_of = set()
    slot = AO.LABEL_SLOT.get(str(atom[0]))
    if slot is not None and slot < len(atom) - 1 \
            and isinstance(atom[slot + 1], str):
        label_of.add(atom[slot + 1])
    for alias in (group or {}).get("source_aliases") or []:
        lines.append("SOURCE WORDING: %s"
                     % P51.printed_atom(GR55._local_display(alias)))
    for name in GR55._constants(atom):
        if name in label_of:
            continue
        got = GR55.constant_gloss(view, name, glosses, worlds, label_of)
        if got:
            lines.append(got)
    seen, out = set(), []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out or [GR55.NO_GLOSS]


def rule_logic_message(view, rule, displayed):
    """One rule, its reading, its name glosses and its connectivity.  No more."""
    glosses = entity_glosses(view)
    worlds = GR55._worlds(view.get("stage2"))
    mapping = display_mapping(rule)
    L = ["THE RULE", "",
         "  %-4s %s" % (rule["rule_id"], printed_rule(rule, mapping)), "",
         "FORMAL READING:", formal_reading(rule, mapping), "",
         "THE ATOMS OF THIS RULE", ""]
    for role, lit in literals_of_rule(rule):
        atom = lit["atom"]
        g = group_for(atom, displayed)
        L.append("  %-11s%s" % (role, P51.printed_atom(
            shown(atom, mapping), negated=lit.get("sign") == "-")))
        reads = GR55._substituted(shown(atom, mapping), glosses)
        if reads is not None:
            L.append("       READS AS: %s"
                     % P51.printed_atom(reads,
                                        negated=lit.get("sign") == "-"))
        for line in atom_glosses(view, atom, g, glosses, worlds):
            L.append("       %s" % line)
        L.append("")
    L.append(render_connectivity(connectivity(rule)))
    L += ["", "Write one ASSESS_LOGIC block for %s." % rule["rule_id"]]
    return "\n".join(L)


def _blocks(text, header):
    """-> [(id written on the block, its fields)], in order.

    A call carries exactly one rule, so a reply with exactly one block is about
    that rule whatever id it copied from the example in the instructions.  Two
    or more blocks stay ambiguous and are refused.
    """
    out = []
    for raw in (text or "").splitlines():
        m = header.match(raw)
        if m:
            out.append((m.group(1).upper(), {}))
            continue
        if not out:
            continue
        f = _FIELD.match(raw)
        if f:
            out[-1][1].setdefault(f.group(1).upper(), f.group(2).strip())
    return out


def _pick(text, rule_id, header):
    """-> (fields, the id it was written under, junk lines)."""
    blocks = _blocks(text, header)
    junk = []
    for written, fields in blocks:
        if written == rule_id.upper():
            return fields, None, junk
    if len(blocks) == 1:
        written, fields = blocks[0]
        junk.append({"line": written,
                     "why": "the only block was written under %s, not %s; one "
                            "call carries one rule, so it was used"
                            % (written, rule_id)})
        return fields, written, junk
    for written, _fields in blocks:
        junk.append({"line": written,
                     "why": "a block for another rule id, among several"})
    return None, None, junk


def parse_logic(text, rule_id):
    """Strict.  An unreadable reply is UNCERTAIN about everything."""
    fields, mismatch, junk = _pick(text, rule_id, _LOGIC)
    seen = fields is not None
    fields = fields or {}
    if not seen:
        return {"direction": None, "body_sufficient": None,
                "missing_condition": "", "counterexample": "", "reason": "",
                "explicitly_assessed": False, "rejected": junk,
                "note": "no readable ASSESS_LOGIC block"}
    got = fields.get("MISSING_CONDITION") or ""
    ce = fields.get("ORDINARY_COUNTEREXAMPLE") or ""
    return {"direction": GR55._field(fields, "DIRECTION", DIRECTIONS),
            "body_sufficient": GR55._field(fields, "BODY_SUFFICIENT",
                                           SUFFICIENCY),
            "missing_condition": "" if GR55._noneish(got)
            else got.strip()[:200],
            "counterexample": "" if GR55._noneish(ce) else ce.strip()[:200],
            "reason": (fields.get("REASON") or "").strip()[:300],
            "explicitly_assessed": bool(
                GR55._field(fields, "BODY_SUFFICIENT", SUFFICIENCY)),
            "written_under": mismatch, "rejected": junk,
            "note": None if GR55._field(fields, "BODY_SUFFICIENT", SUFFICIENCY)
            else "BODY_SUFFICIENT was missing or not one of the three values"}


# ------------------------------------------------- WP2B: the passage-basis call

def rule_basis_message(view, split, rule, displayed, logic, index=None):
    """The passage, the question, the rule, and what the first call answered."""
    glosses = entity_glosses(view)
    worlds = GR55._worlds(view.get("stage2"))
    index = index or role_index(view)
    mapping = display_mapping(rule)
    L = ["PASSAGE", "", split["passage"], "",
         "QUESTION — NOT A FACT", "", split["question"], "",
         "THE INVENTED RULE", "",
         "  %-4s %s" % (rule["rule_id"], printed_rule(rule, mapping)), "",
         "FORMAL READING:", formal_reading(rule, mapping), "",
         "THE ATOMS OF THIS RULE", ""]
    for role, lit in literals_of_rule(rule):
        atom = lit["atom"]
        g = group_for(atom, displayed)
        L.append("  %-11s%s%s" % (role, P51.printed_atom(
            shown(atom, mapping), negated=lit.get("sign") == "-"),
            "   [%s]" % g["id"] if g else ""))
        found, _where = roles_of(shown(atom, mapping), index)
        L.append("       WHERE THIS SHAPE OCCURS: %s" % ", ".join(found))
        reads = GR55._substituted(shown(atom, mapping), glosses)
        if reads is not None:
            L.append("       READS AS: %s"
                     % P51.printed_atom(reads,
                                        negated=lit.get("sign") == "-"))
        for line in GR55.atom_help(view, atom, g, glosses, worlds):
            L.append("       %s" % line)
        L.append("")
    L += ["WHAT THE FIRST ASSESSMENT ALREADY DECIDED", "",
          "  DIRECTION: %s" % logic.get("direction"),
          "  BODY_SUFFICIENT: %s" % logic.get("body_sufficient"),
          "  MISSING_CONDITION: %s" % (logic.get("missing_condition")
                                       or "NONE"),
          "  ORDINARY_COUNTEREXAMPLE: %s" % (logic.get("counterexample")
                                             or "NONE"),
          "  REASON: %s" % logic.get("reason"), "",
          "Those four fields are settled. You are not asked to revisit them.",
          "", GR55.ROLE_LEGEND, "",
          "Write one ASSESS_BASIS block for %s." % rule["rule_id"]]
    return "\n".join(L)


def parse_basis(text, rule_id):
    fields, mismatch, junk = _pick(text, rule_id, _BASIS)
    seen = fields is not None
    fields = fields or {}
    if not seen:
        return {"basis": "NONE", "scope": None, "condition_in_passage": None,
                "supporting_sentence": "", "reason": "",
                "explicitly_assessed": False, "written_under": None,
                "rejected": junk, "note": "no readable ASSESS_BASIS block"}
    sentence = fields.get("SUPPORTING_SENTENCE") or ""
    return {"basis": GR55._field(fields, "BASIS", BASES) or "NONE",
            "scope": GR55._field(fields, "SCOPE", SCOPES),
            "condition_in_passage": GR55._field(
                fields, "MISSING_CONDITION_PRESENT_IN_PASSAGE", PRESENCE),
            "supporting_sentence": "" if GR55._noneish(sentence)
            else sentence.strip()[:300],
            "reason": (fields.get("REASON") or "").strip()[:300],
            "explicitly_assessed": bool(GR55._field(fields, "BASIS", BASES)),
            "written_under": mismatch, "rejected": junk,
            "note": None if GR55._field(fields, "BASIS", BASES)
            else "BASIS was missing or not one of the four values"}


# ------------------------------------------------------ WP3: one decision

def combine(logic, basis=None):
    """-> the decision, the rule that produced it, and why.  Code, not a model.

    The passage-basis answer is recorded and never raises the decision: a
    condition that is missing from the body stays missing however plainly the
    passage states it.
    """
    basis = basis or {}
    direction = logic.get("direction")
    body = logic.get("body_sufficient")
    missing = (logic.get("missing_condition") or "").strip()
    counter = (logic.get("counterexample") or "").strip()
    if not logic.get("explicitly_assessed"):
        return {"decision": "UNCERTAIN", "rule_used": "unreadable_reply",
                "why": "the rule-only reply had no readable block; UNCERTAIN "
                       "is not approval"}
    if direction == "WRONG":
        return {"decision": "REJECT", "rule_used": "direction_wrong",
                "why": "the implication runs the wrong way or misplaces a "
                       "participant"}
    if body == "NO":
        if missing:
            return {"decision": "NEEDS_CONDITION",
                    "rule_used": "body_insufficient_with_a_named_condition",
                    "why": "the body does not support the conclusion without "
                           "%s" % missing}
        if counter:
            return {"decision": "REJECT",
                    "rule_used": "body_insufficient_with_a_counterexample",
                    "why": "the body does not support the conclusion and an "
                           "ordinary counterexample was given"}
        return {"decision": "UNCERTAIN",
                "rule_used": "body_insufficient_without_a_condition",
                "why": "the body was called insufficient but nothing was named "
                       "that would fix it"}
    if body == "UNCERTAIN":
        return {"decision": "UNCERTAIN", "rule_used": "body_uncertain",
                "why": "sufficiency of the body was not decided"}
    if counter:
        return {"decision": "UNCERTAIN", "rule_used": "ordinary_counterexample",
                "why": "an ordinary counterexample was given for a body called "
                       "sufficient"}
    if missing:
        return {"decision": "NEEDS_CONDITION",
                "rule_used": "condition_named_beside_a_sufficient_body",
                "why": "a missing condition was named: %s" % missing}
    if direction == "CORRECT":
        return {"decision": "ACCEPT", "rule_used": "correct_and_sufficient",
                "why": "the direction is correct and the body suffices on its "
                       "own"}
    return {"decision": "UNCERTAIN", "rule_used": "direction_uncertain",
            "why": "the direction of the implication was not decided"}
