"""One assessment call per minimal proof set, with a code-owned glossary.

The v5.6.1 assessor spent two calls per bridge and filled them with the
pipeline's own bookkeeping: where an atom occurs, what an earlier call decided,
which supplier could offer it.  This one shows the passage, the question marked
as not a fact, the bridges of a single proof in their stored order, and fixed
templates for the predicates those bridges actually use.  Nothing else.

Three consequences are deliberate:

  * the bridges of one proof are judged together, so a rule that only looks
    reasonable beside its neighbours is visible as such;
  * no rule id is shown or returned.  An assessment is matched to a bridge by
    repeating the exact rule, which is why the parser refuses anything it
    cannot match character for character;
  * the glossary explains predicate FORMS, never a particular atom.  A
    paraphrase of `["isa","earthworm","?X"]` would be this module deciding what
    the case means, which is the assessor's job and not the builder's.
"""

import hashlib
import json
import os
import re

VERSION = "bridge_set_assessor_v6/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "grade_bridge_set_v6_draft_system"
EXAMPLE_NAME = "EXAMPLE_2026_08_14_grade_bridge_set_v6_earthworm.txt"

GRADES = ("SOUND", "PLAUSIBLE", "NEEDS_CONDITION", "UNSOUND", "UNCERTAIN")
PASS, FAIL, UNCERTAIN = "PASS", "FAIL", "UNCERTAIN"

_RULE = re.compile(r"^\s*RULE\s*:\s*(.*?)\s*$")
_MEANING = re.compile(r"^\s*MEANING\s*:\s*(.*?)\s*$")
_GRADE = re.compile(r"^\s*GRADE\s*:\s*([A-Z_]+)\s*$")


def system_prompt():
    with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
        return f.read()


def sha256_of(text):
    return hashlib.sha256((text or "").encode()).hexdigest()


def system_prompt_sha256():
    return sha256_of(system_prompt())


def example_sha256():
    with open(os.path.join(ROOT, "memos", EXAMPLE_NAME), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ------------------------------------------------------ WP2: the glossary

PREDICATE_TEMPLATES = {
    ("isa", 2): ('["isa", CLASS, THING]',
                 "means that THING is an instance or subtype of CLASS."),
    ("is rel2", 3): ('["is rel2", RELATION, SUBJECT, OBJECT]',
                     "means that SUBJECT stands in RELATION to OBJECT."),
    ("has property", 2): ('["has property", PROPERTY, THING]',
                          "means that THING has PROPERTY."),
    ("has part", 2): ('["has part", WHOLE, PART]',
                      "means that WHOLE has PART."),
    ("have", 2): ('["have", OWNER, OBJECT]',
                  "means that OWNER has OBJECT."),
    ("has type", 2): ('["has type", EVENT, TYPE]',
                      "means that EVENT is an event of kind TYPE."),
    ("has actor", 2): ('["has actor", EVENT, ACTOR]',
                       "means that ACTOR performs EVENT."),
    ("has target", 2): ('["has target", EVENT, TARGET]',
                        "means that EVENT is directed at TARGET."),
    ("has recipient", 2): ('["has recipient", EVENT, RECIPIENT]',
                           "means that EVENT is directed to RECIPIENT."),
    ("has topic", 2): ('["has topic", EVENT, TOPIC]',
                       "means that EVENT is about TOPIC."),
    ("has manner", 2): ('["has manner", EVENT, MANNER]',
                        "means that EVENT happens in MANNER."),
    ("has location", 3): ('["has location", EVENT, PLACE, PREPOSITION]',
                          "means that EVENT is at PLACE, in the sense given "
                          "by PREPOSITION."),
    ("has degree property", 4): (
        '["has degree property", PROPERTY, THING, DEGREE, KIND]',
        "means that THING has PROPERTY to DEGREE, compared with things of "
        "kind KIND."),
    ("has degree rel2", 5): (
        '["has degree rel2", RELATION, SUBJECT, OBJECT, DEGREE, KIND]',
        "means that SUBJECT stands in RELATION to OBJECT to DEGREE, compared "
        "with things of kind KIND."),
    ("member", 2): ('["member", COLLECTION, THING]',
                    "means that THING is a member of COLLECTION."),
    ("=", 2): ('["=", THING, THING]',
               "means that the two named things are the same thing. A rule "
               "may conclude NOT [\"=\", A, B], which says that A and B are "
               "different things."),
    ("less_measure", 2): ('["less_measure", MEASURE_1, MEASURE_2]',
                          "means that the first measured quantity is smaller "
                          "than the second."),
    ("typical", 1): ('["typical", EVENT]',
                     "means that EVENT is a typical rather than an actual "
                     "event."),
    ("actuality", 1): ('["actuality", EVENT]',
                       "means that EVENT actually happens."),
}

NESTED_TEMPLATES = {
    ("eventprop", 2): ('["eventprop", ROLE, VALUE]',
                       "is one structured argument, not a separate atom. It "
                       "names the ROLE that VALUE plays in the relation, for "
                       "example `$target` or `$source`."),
    ("$measure_of", 3): ('["$measure_of", QUANTITY, THING, UNIT]',
                         "is one structured argument naming a measured "
                         "quantity of THING."),
    ("$setof", 2): ('["$setof", KIND, MEMBERS]',
                    "is one structured argument naming a set."),
    ("$ev_of", 3): ('["$ev_of", TYPE, ACTOR, TARGET]',
                    "is one structured argument naming an event."),
    ("$list", 2): ('["$list", LENGTH, ITEMS]',
                   "is one structured argument naming a list."),
}

SKOLEM_NOTE = ("A name beginning with `sk` is a generated name for one "
               "particular unnamed object. The same `sk` name denotes the same "
               "object; different names need not.")


class GlossaryError(Exception):
    """A predicate form with no fixed template.  The builder fails closed."""


def forms_in(atom, into_pred, into_nested):
    """Collect the predicate form and every nested functor of one atom."""
    if not (isinstance(atom, list) and atom):
        return
    into_pred.add((str(atom[0]), len(atom) - 1))

    def walk(term):
        if isinstance(term, list) and term:
            into_nested.add((str(term[0]), len(term) - 1))
            for x in term[1:]:
                walk(x)
    for arg in atom[1:]:
        walk(arg)


def forms_of(rules):
    """-> (predicate forms, nested functors, whether an `sk` name occurs)."""
    preds, nested, skolem = set(), set(), False
    for rule in rules:
        for lit in list(rule.get("body") or []) + [rule.get("head") or {}]:
            atom = lit.get("atom")
            if atom:
                forms_in(atom, preds, nested)
                if "sk" in json.dumps(atom):
                    skolem = True
    return preds, nested, skolem


def glossary(rules):
    """-> the fixed templates for exactly the forms these rules use."""
    preds, nested, skolem = forms_of(rules)
    missing = [p for p in preds if p not in PREDICATE_TEMPLATES]
    missing += [n for n in nested
                if n not in NESTED_TEMPLATES and not str(n[0]).startswith("sk")]
    if missing:
        raise GlossaryError("no fixed template for %s"
                            % ", ".join("%s/%d" % m for m in sorted(missing)))
    lines = []
    for form in sorted(preds):
        head, text = PREDICATE_TEMPLATES[form]
        lines.append("  %s\n      %s" % (head, text))
    for form in sorted(nested):
        if str(form[0]).startswith("sk"):
            continue
        head, text = NESTED_TEMPLATES[form]
        lines.append("  %s\n      %s" % (head, text))
    if skolem or any(str(f[0]).startswith("sk") for f in nested):
        lines.append("  %s" % SKOLEM_NOTE)
    return "\n\n".join(lines), sorted(preds), sorted(nested)


# ------------------------------------------------------- WP1: the message

def build_message(passage, question, printed_rules, rules):
    """The four sections, and nothing else."""
    got, preds, nested = glossary(rules)
    lines = ["PASSAGE", "", (passage or "").strip(), "",
             "QUESTION — NOT A FACT", "", (question or "").strip(), "",
             "BRIDGES USED IN ONE PROOF", ""]
    for printed in printed_rules:
        lines.append("  %s" % printed)
        lines.append("")
    lines += ["PREDICATES USED IN THESE BRIDGES", "", got]
    text = "\n".join(lines).rstrip() + "\n"
    return {"text": text, "sha256": sha256_of(text), "chars": len(text),
            "bridges": list(printed_rules),
            "predicate_forms": ["%s/%d" % p for p in preds],
            "nested_forms": ["%s/%d" % n for n in nested]}


# -------------------------------------------------------- WP3: the parser

FORBIDDEN = ("THE ATOMS OF THIS RULE", "WHAT THE FIRST ASSESSMENT",
             "WHERE THIS SHAPE OCCURS", "SUGGESTED ROLE", "MAY BE SUPPLIED BY",
             "BASE_FACT", "QUESTION_CLAIM", "SOURCE STATUS", "trust_class",
             "expected", "accepted answer", "R1 ", "R2 ")


def parse_response(text, printed_rules):
    """-> one assessment per displayed bridge, matched by the exact rule text.

    No rule id is displayed, so a reply is bound to a bridge only by repeating
    it exactly.  Anything else — a near-miss, a reversed argument order, an
    invented rule, a second opinion on the same bridge — is refused and named.
    """
    wanted = list(printed_rules)
    blocks, errors = [], []
    current = None
    for raw in (text or "").splitlines():
        m = _RULE.match(raw)
        if m:
            if current is not None:
                errors.append({"rule": current.get("rule"),
                               "why": "a RULE line before the previous block "
                                      "was finished"})
            current = {"rule": m.group(1).strip()}
            continue
        if current is None:
            continue
        m = _MEANING.match(raw)
        if m:
            current["meaning"] = m.group(1).strip()
            continue
        m = _GRADE.match(raw)
        if m:
            current["grade"] = m.group(1).strip().upper()
            blocks.append(current)
            current = None
    if current is not None:
        errors.append({"rule": current.get("rule"),
                       "why": "a block without a GRADE line"})
    got, seen = {}, []
    for block in blocks:
        rule = block.get("rule", "")
        if rule not in wanted:
            errors.append({"rule": rule[:200],
                           "why": "not one of the displayed bridges, "
                                  "character for character"})
            continue
        if rule in got:
            errors.append({"rule": rule[:200],
                           "why": "a second assessment of the same bridge"})
            continue
        grade = block.get("grade")
        if grade not in GRADES:
            errors.append({"rule": rule[:200],
                           "why": "the grade %r is not one of the five"
                                  % grade})
            continue
        if not (block.get("meaning") or "").strip():
            errors.append({"rule": rule[:200], "why": "an empty MEANING line"})
            continue
        got[rule] = {"rule": rule, "meaning": block["meaning"],
                     "grade": grade}
        seen.append(rule)
    missing = [r for r in wanted if r not in got]
    return {"assessments": [got[r] for r in wanted if r in got],
            "by_rule": got, "missing": missing, "errors": errors,
            "complete": not missing and not errors,
            "all_bridges_assessed": not missing,
            "blocks_read": len(blocks)}


def fill_uncertain(parsed, printed_rules, why):
    """Every bridge the model did not assess is UNCERTAIN, never borrowed."""
    out = []
    for rule in printed_rules:
        got = parsed["by_rule"].get(rule)
        if got:
            out.append(dict(got, filled=False))
        else:
            out.append({"rule": rule, "meaning": "", "grade": "UNCERTAIN",
                        "filled": True, "why": why})
    return out


# ------------------------------------------------- WP6: the derived classes

def set_class(grades):
    """PASS / FAIL / UNCERTAIN, exactly as the plan defines them."""
    if any(g in ("NEEDS_CONDITION", "UNSOUND") for g in grades):
        return FAIL
    if any(g == "UNCERTAIN" for g in grades):
        return UNCERTAIN
    if grades and all(g in ("SOUND", "PLAUSIBLE") for g in grades):
        return PASS
    return UNCERTAIN


def policies(grades):
    """Every reading of the same grades, reported side by side."""
    return {"strict": bool(grades) and all(g == "SOUND" for g in grades),
            "sound_or_plausible": set_class(grades) == PASS,
            "contains_needs_condition": any(g == "NEEDS_CONDITION"
                                            for g in grades),
            "contains_unsound": any(g == "UNSOUND" for g in grades),
            "all_proofs": True}
