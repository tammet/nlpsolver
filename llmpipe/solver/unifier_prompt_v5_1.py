"""The clear positive literal-bridge prompt: one cached system prompt, three
user messages.

Plan: `memos/PLAN_2026_08_13_clear_positive_literal_bridge_prompt_opus5.md`.
Specification, treated as fixed and not tuned here:
`prompts/dynamic_alignment/unifier_rules_v5_1_system.txt` and
`memos/EXAMPLE_2026_08_13_clear_literal_bridge_prompt.md`.

This module only BUILDS TEXT.  It calls no LLM and no prover, and it never
reads an accepted answer, a reviewed rule, a grade or a proof.  It does run the
converter and the bridge compiler, which are deterministic offline code.

Four things differ from `unifier_prompt_v5`:

  * **one positive candidate per atom.**  v5 showed both signs of every atom and
    a LEFT/RIGHT/EITHER position word.  Semantic `NOT` is a different task, and
    a negative candidate invited the model to write one.  Here the candidate is
    the ordinary positive atom, and the sign of the clause occurrences it
    matches becomes a suggested ROLE instead: a positive occurrence means the
    atom is usable as a premise, because a premise compiles to the negative
    clause literal that resolves with it;
  * **an atom is displayed only if a real bridge rule can carry it.**  v5 asked
    whether the atom, used as a FACT, converts to a recognisable literal.  That
    is a weaker question: `has time(?X,past,in)` passes it and then vanishes
    from every compiled rule.  Here each displayed atom is compiled twice, once
    as a premise and once as a conclusion, and its content literal has to
    survive both;
  * **the displayed form is the one the compiler receives.**  Where
    `-simpleprops` collapses a degree predicate at DEGREE `"none"`, the
    collapsed atom itself is displayed, and rows that compile to one literal are
    merged into one line, so an argument compilation discards cannot look like a
    restriction;
  * **three honest sections.**  QUESTION-RELATED / OTHER CONTENT / HELPER,
    instead of a FOCUS label that in practice meant "content-bearing".

The passage/question split, the argument comparison and the structural-atom test
are `unifier_prompt_v5`'s, imported unchanged.
"""

import hashlib
import json
import os

import alignment_occurrences as AO
import simple_rule_compiler_v3 as C3
import simple_rule_parser as SP
import unifier_abstraction as UA
import unifier_candidates_v3 as CV3
import unifier_candidates_v4 as CV4
import unifier_prompt_v5 as P5

VERSION = "unifier_prompt_v5_1/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_rules_v5_1_system"

# The two fixed inputs of this task.  Pinned so that a preview can never be
# rendered against silently edited instructions.
SYSTEM_PROMPT_SHA256 = \
    "e0f61739532beca29e262ca797553f56f5b062d2b85e078f58d2e090632ec9d5"
EXAMPLE_PATH = os.path.join(ROOT, "memos",
                            "EXAMPLE_2026_08_13_clear_literal_bridge_prompt.md")
EXAMPLE_SHA256 = \
    "e2e6c36098a850a85d944cd398aaf5ed3e9917bcdd9f69d4b44682f76d4d45f2"

# The three role words the model sees.  They are derived from clause polarity:
# a positive occurrence of A can resolve with the `-A` literal a premise
# compiles to, and a negative occurrence with the `A` a conclusion compiles to.
PREMISE = "PREMISE"
CONCLUSION = "CONCLUSION"
EITHER = "PREMISE OR CONCLUSION"
ROLE_WORD = {CV4.PREMISE: PREMISE, CV4.CONSEQUENCE: CONCLUSION,
             CV4.BOTH: EITHER}

QUESTION_SECTION = "question_related"
CONTENT_SECTION = "other_content"
HELPER_SECTION = "helper"

SECTION_HEADING = {
    QUESTION_SECTION: "QUESTION-RELATED ATOMS:",
    CONTENT_SECTION: "OTHER CONTENT ATOMS:",
    HELPER_SECTION: "HELPER ATOMS — use only together with a content atom:",
}
SECTION_PREFIX = {QUESTION_SECTION: "Q", CONTENT_SECTION: "C",
                  HELPER_SECTION: "H"}
SECTION_ORDER = (QUESTION_SECTION, CONTENT_SECTION, HELPER_SECTION)

CLOSING_LINE = "Write the missing implication rules now."

# ENCODINGS.md §5.3, at DEGREE "none" only.  Kept as a switch so a preview can
# state exactly what the one admitted predicate rewriting buys.
ALLOW_SIMPLEPROPS_COLLAPSE = True

# A class the passages do not use, for the writability probe only.  It never
# appears in a prompt.
PROBE_CLASS = "zz probe class"
PROBE_ATOM = ["isa", PROBE_CLASS, "?ZZPROBE"]

RULE_ENTITY_MARKER = P5.RULE_ENTITY_MARKER
RULE_LETTER_CASE = P5.RULE_LETTER_CASE
RULE_TRAILING_CONTEXT = P5.RULE_TRAILING_CONTEXT
RULE_SIMPLEPROPS = P5.RULE_SIMPLEPROPS

# The `multi_output_alpha_equal_variants` exception of v5 is gone:
# `unifier_candidates_v3.conversion_of` already deduplicates outputs that are
# equal up to variable renaming, so a remaining multi-output atom always has
# several genuinely different effects.
DOCUMENTED_RULES = dict((k, v) for k, v in P5.DOCUMENTED_RULES.items()
                        if k != P5.RULE_MULTI_ALPHA)

WHY_NO_POSITIVE_FORM = ("only the negated form of this atom was scored: its "
                        "positive form produced no content literal, or none "
                        "that occurs in any clause of either sign")
WHY_MULTI_OUTPUT = ("one surface atom compiles to %d different content "
                    "clauses, so the displayed line would not say what writing "
                    "it asserts")
WHY_NEGATIVE_LITERAL = ("the positive atom compiles to the negative literal "
                        "%s, so writing it would assert the opposite")
WHY_NO_OCCURRENCE = ("its converted literal occurs in no clause of either "
                     "sign, apart from population witnesses and generic frame "
                     "axioms")
WHY_ROUND_TRIP = ("the displayed form does not convert back to the literal it "
                  "stands for (it produced %s)")
WHY_NOT_WRITABLE = ("a bridge rule using it as a %s does not contain the "
                    "content literal %s (%s)")

# The question split is P5's, unchanged.
EXACT_SUFFIX = P5.EXACT_SUFFIX
NORMALIZED_SUFFIX = P5.NORMALIZED_SUFFIX
SEPARATE_FIELD = P5.SEPARATE_FIELD
UNRESOLVED = P5.UNRESOLVED

split_case_text = P5.split_case_text
stored_question = P5.stored_question
is_structural = P5.is_structural
sha256_of = P5.sha256_of


class PromptError(P5.PromptError):
    """The prompt layer cannot proceed.  Never worked around."""


# ------------------------------------------------------------ fixed inputs

def system_prompt():
    p = os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)
    with open(p) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


def example_sha256():
    with open(EXAMPLE_PATH) as f:
        return hashlib.sha256(f.read().encode()).hexdigest()


def check_fixed_inputs():
    """Refuse to build anything against edited instructions."""
    got = system_prompt_sha256()
    if got != SYSTEM_PROMPT_SHA256:
        raise PromptError("the fixed system prompt changed: %s" % got)
    got = example_sha256()
    if got != EXAMPLE_SHA256:
        raise PromptError("the fixed full example changed: %s" % got)
    return True


# ------------------------------------------------- WP2: what may be displayed

def _content_part(literal, n):
    """The predicate and the first `n` arguments: what the passage supplied.

    Conversion appends context arguments on the right (ENCODINGS.md §6), and a
    rule generalises them where an isolated fact conversion leaves them
    concrete.  Only the content part is compared.
    """
    atom = UA.unsigned_atom(literal)
    return [atom[0]] + list(atom[1:1 + n])


def _same_content(a, b, n):
    return UA.alpha_key(_content_part(a, n)) == UA.alpha_key(_content_part(b, n))


def simpleprops_display(surface, converted_predicate):
    """The canonical collapsed atom, at DEGREE "none" only, or None."""
    if not ALLOW_SIMPLEPROPS_COLLAPSE:
        return None
    pred = str(surface[0])
    if pred == "has degree property" and converted_predicate == "has property" \
            and len(surface) == 5 and surface[3] == "none":
        return ["has property", surface[1], surface[2]]
    if pred == "has degree rel2" and converted_predicate == "is rel2" \
            and len(surface) == 6 and surface[4] == "none":
        return ["is rel2", surface[1], surface[2], surface[3]]
    return None


def display_check(display_atom, literal):
    """May this atom be displayed as the syntax the model should copy?

    -> {safe, reasons, rules_applied}.  `safe` is False unless every difference
    between the displayed atom and the clause literal it compiles to is
    explained by a rule in `DOCUMENTED_RULES`.
    """
    reasons, rules = [], []
    if UA.sign_of(literal) != "+":
        return {"safe": False,
                "reasons": [WHY_NEGATIVE_LITERAL % json.dumps(literal)],
                "rules_applied": []}
    atom = UA.unsigned_atom(literal)
    if str(display_atom[0]) != str(atom[0]):
        return {"safe": False,
                "reasons": ["predicate: `%s` compiles to `%s`"
                            % (display_atom[0], atom[0])],
                "rules_applied": []}
    shown, clause = list(display_atom[1:]), list(atom[1:])
    if len(clause) < len(shown):
        reasons.append("conversion dropped %d argument(s)"
                       % (len(shown) - len(clause)))
    else:
        extra = clause[len(shown):]
        if extra:
            if all(P5._is_context_argument(t) for t in extra):
                rules.append(RULE_TRAILING_CONTEXT)
            else:
                reasons.append("conversion added the argument(s) %s, which are "
                               "not context slots"
                               % "; ".join(json.dumps(t) for t in extra))
        got, used = P5._compare_arguments(shown, clause[:len(shown)])
        if got:
            slot = AO.LABEL_SLOT.get(str(display_atom[0]))
            if slot is not None and slot < len(shown) and slot < len(clause) \
                    and P5._norm(shown[slot]) != P5._norm(clause[slot]):
                got = ["content label: `%s` compiles to `%s`"
                       % (shown[slot], clause[slot])] + got
            elif P5._same_multiset(shown, clause[:len(shown)]):
                got = ["argument order: the same arguments appear in a "
                       "different order"] + got
            reasons.extend(got)
        rules.extend(used)
    ordered, seen = [], set()
    for r in rules:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return {"safe": not reasons, "reasons": reasons, "rules_applied": ordered}


# ------------------------------------------------- WP2: bridge writability

def probe_rule(atom, position):
    """A harmless one-premise rule that puts `atom` in the asked position."""
    other = PROBE_ATOM
    if position == PREMISE:
        parsed = {"body": [("+", atom)], "head": ("+", other)}
    else:
        parsed = {"body": [("+", other)], "head": ("+", atom)}
    rule = SP.to_stage2_variables(parsed)
    rule.update({"rule_id": "PROBE", "canonical": "probe",
                 "printed": "writability probe"})
    return rule


def _rule_literals(clauses):
    out = []
    for c in clauses or []:
        if c.get("@sourcetype") == "populate":
            continue
        for lit in UA.literals_of(c.get("@logic")):
            if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                    and not UA.is_control_predicate(lit[0]):
                out.append(lit)
    return out


def writability(atom, literal, view, configuration):
    """-> {writable, premise, conclusion}.  One real compilation per position.

    A rule literal must actually carry the atom's content: as a premise it must
    appear negated, as a conclusion positive.  `has time` fails both, which is
    why no wording could make it safe to display.
    """
    n = len(atom) - 1
    out = {}
    for position, want_sign in ((PREMISE, "-"), (CONCLUSION, "+")):
        rule = probe_rule(atom, position)
        try:
            clauses, _rec = C3.compile_one(rule, view, configuration,
                                           case_id=view.get("case_id"),
                                           world_name="writability_probe")
        except Exception as e:                                  # noqa: BLE001
            out[position] = {"ok": False,
                             "why": "the converter raised %s: %s"
                                    % (type(e).__name__, str(e)[:120]),
                             "literals": []}
            continue
        lits = _rule_literals(clauses)
        found = [l for l in lits
                 if UA.sign_of(l) == want_sign and len(l) - 1 >= n
                 and _same_content(l, literal, n)]
        out[position] = {"ok": bool(found),
                         "why": None if found else
                         "the compiled clause is %s" % json.dumps(lits)[:160],
                         "literals": lits}
    return {"writable": out[PREMISE]["ok"] and out[CONCLUSION]["ok"],
            "premise": out[PREMISE], "conclusion": out[CONCLUSION]}


# -------------------------------------------------- WP1: positive candidates

def _positive_rows(rows):
    """Every v4 row whose stored conversion is the conversion of the POSITIVE
    atom, keyed by surface atom.

    `build_main` converts each Stage-2 atom in both signs and keeps a row per
    output; only the `+` rows are conversions of the positive atom.
    `build_secondary` always converts the positive surface guess and negates the
    result afterwards, so all of its rows qualify and their positive literal is
    the variant the row points at.
    """
    positive, negative_only = {}, {}
    for row in rows:
        key = UA.alpha_key(row["surface_atom"])
        if row.get("origin") == "stage2" and row["sign"] != "+":
            negative_only.setdefault(key, []).append(row)
            continue
        lits = row.get("all_converted_literals") or []
        index = row.get("converted_variant_index") or 0
        if index >= len(lits):
            continue
        positive.setdefault(key, {"surface_atom": row["surface_atom"],
                                  "literal": lits[index],
                                  "variant_count": len(lits),
                                  "rows": []})["rows"].append(row)
    for key in list(negative_only):
        if key in positive:
            del negative_only[key]
    return positive, negative_only


def _omission(entry, reason, extra=None):
    out = {"surface_atom": entry["surface_atom"],
           "printed": printed_atom(UA.display_atom(entry["surface_atom"])),
           "source_candidate_ids": [r.get("id") for r in entry["rows"]],
           "compiled_literal": entry.get("literal"),
           "all_compiled_literals":
               (entry["rows"][0].get("all_converted_literals")
                if entry["rows"] else None),
           "reason": reason}
    out.update(extra or {})
    return out


def build_candidates(view, configuration, v4_candidates):
    """-> the three sections, the omissions and the diagnostics.

    Nothing here reads an answer, a grade or a proof: the inputs are the stored
    parse, the clauses gk received and the v4 candidate inventory.
    """
    check_fixed_inputs()
    occurrences = v4_candidates["occurrences"]
    pool = CV3.role_occurrences(occurrences)
    rows = list(v4_candidates.get("main") or []) + \
        list(v4_candidates.get("secondary") or [])
    positive, negative_only = _positive_rows(rows)

    omitted = []
    for key, rs in sorted(negative_only.items()):
        omitted.append(_omission({"surface_atom": rs[0]["surface_atom"],
                                  "rows": rs, "literal": None},
                                 WHY_NO_POSITIVE_FORM))

    kept = []
    for key in sorted(positive):
        entry = positive[key]
        literal = entry["literal"]
        if entry["variant_count"] > 1:
            omitted.append(_omission(entry, WHY_MULTI_OUTPUT
                                     % entry["variant_count"]))
            continue
        if UA.sign_of(literal) == "-":
            omitted.append(_omission(entry, WHY_NEGATIVE_LITERAL
                                     % json.dumps(literal)))
            continue
        surface = entry["surface_atom"]
        collapsed = simpleprops_display(surface, str(UA.unsigned_atom(
            literal)[0]))
        display = UA.display_atom(collapsed if collapsed is not None
                                  else surface)
        check = display_check(display, literal)
        if not check["safe"]:
            omitted.append(_omission(entry, check["reasons"][0],
                                     {"reasons": check["reasons"],
                                      "displayed_as": display}))
            continue
        same, opposite, _population = CV3.match_occurrences(literal,
                                                            occurrences)
        role = CV3.role_of(same, opposite)
        if role is None:
            omitted.append(_omission(entry, WHY_NO_OCCURRENCE))
            continue
        rules = list(check["rules_applied"])
        if collapsed is not None:
            rules.append(RULE_SIMPLEPROPS)
        kept.append({
            "display": display,
            "surface_atom": surface,
            "literal": literal,
            "role": ROLE_WORD[role],
            "internal_role": role,
            "cost": CV4.opposite_sign_unifiers(literal, pool),
            "question_linked": any(o["source_kind"] == UA.QUESTION
                                   for o in same + opposite),
            "same_sign_source_kinds": sorted(set(o["source_kind"]
                                                 for o in same)),
            "rows": entry["rows"],
            "display_rules_applied": sorted(set(rules)),
        })

    # WP2.4: rows that compile to one literal are one line.
    buckets = {}
    for k in kept:
        buckets.setdefault(UA.alpha_key(k["literal"]), []).append(k)
    groups = []
    for key in sorted(buckets):
        mine = buckets[key]
        shapes = sorted(set(json.dumps(k["display"], ensure_ascii=False)
                            for k in mine))
        chosen = sorted(mine, key=lambda k: (len(k["display"]),
                                             json.dumps(k["display"],
                                                        ensure_ascii=False)))[0]
        groups.append({
            "atom": chosen["display"],
            "printed": printed_atom(chosen["display"]),
            "literal": chosen["literal"],
            "role": chosen["role"],
            "internal_role": chosen["internal_role"],
            "cost": chosen["cost"],
            "question_linked": any(k["question_linked"] for k in mine),
            "surface_atoms": [k["surface_atom"] for k in mine],
            "source_candidate_ids": [r.get("id") for k in mine
                                     for r in k["rows"]],
            "source_roles": sorted(set(k["internal_role"] for k in mine)),
            "same_sign_source_kinds": sorted(set(
                x for k in mine for x in k["same_sign_source_kinds"])),
            "source_costs": sorted(set(k["cost"] for k in mine)),
            "display_rules_applied": sorted(set(r for k in mine
                                                for r in
                                                k["display_rules_applied"])),
            "merged_display_forms": shapes if len(shapes) > 1 else [],
            "merge_note": ("%d surface rows compile to this one literal: %s"
                           % (len(mine),
                              "; ".join(UA.print_atom(UA.display_atom(
                                  k["surface_atom"])) for k in mine))
                           if len(mine) > 1 else None),
        })

    # WP2.5 and WP2.1-2.2: the displayed form must convert back, and a real
    # bridge rule must be able to carry it.
    tries = [(g["atom"], "+") for g in groups]
    errors = []
    converted = CV3.convert_batch(view, tries, configuration,
                                  errors=errors) if tries else {}
    checked = []
    for i, g in enumerate(groups, start=1):
        status, lits = CV3.conversion_of(converted.get("Cv%d" % i) or [])
        n = len(g["atom"]) - 1
        back = [l for l in lits if _same_content(l, g["literal"], n)
                and UA.sign_of(l) == "+"]
        if len(lits) != 1 or not back:
            omitted.append({"surface_atom": g["surface_atoms"][0],
                            "printed": g["printed"],
                            "source_candidate_ids": g["source_candidate_ids"],
                            "compiled_literal": g["literal"],
                            "all_compiled_literals": lits,
                            "reason": WHY_ROUND_TRIP
                            % json.dumps(lits, ensure_ascii=False)[:160]})
            continue
        g["round_trip"] = {"converted": lits, "status": status}
        got = writability(g["atom"], g["literal"], view, configuration)
        if not got["writable"]:
            side = PREMISE if not got["premise"]["ok"] else CONCLUSION
            omitted.append({"surface_atom": g["surface_atoms"][0],
                            "printed": g["printed"],
                            "source_candidate_ids": g["source_candidate_ids"],
                            "compiled_literal": g["literal"],
                            "all_compiled_literals": lits,
                            "reason": WHY_NOT_WRITABLE
                            % (side.lower(),
                               json.dumps(g["literal"], ensure_ascii=False),
                               got[side.lower().replace(" ", "_")]["why"]),
                            "writability": {k: {"ok": v["ok"], "why": v["why"]}
                                            for k, v in got.items()
                                            if isinstance(v, dict)}})
            continue
        g["writability"] = {k: {"ok": v["ok"], "why": v["why"]}
                            for k, v in got.items() if isinstance(v, dict)}
        checked.append(g)

    for g in checked:
        g["section"] = (HELPER_SECTION if is_structural(g["atom"])
                        else QUESTION_SECTION if g["question_linked"]
                        else CONTENT_SECTION)
    sections = {}
    for name in SECTION_ORDER:
        mine = [g for g in checked if g["section"] == name]
        mine.sort(key=lambda g: (g["cost"], g["printed"]))
        for i, g in enumerate(mine, start=1):
            g["id"] = "%s%d" % (SECTION_PREFIX[name], i)
        sections[name] = mine

    return {
        "version": VERSION,
        "case_id": view.get("case_id"),
        "sections": sections,
        "groups": checked,
        "omitted": omitted,
        "conversion_errors": errors,
        "counts": {
            "source_candidate_rows": len(rows),
            "distinct_positive_surface_atoms": len(positive),
            "negative_variants_removed": sum(1 for r in rows
                                             if r["sign"] == "-"),
            "displayed_groups": len(checked),
            "question_related": len(sections[QUESTION_SECTION]),
            "other_content": len(sections[CONTENT_SECTION]),
            "helper": len(sections[HELPER_SECTION]),
            "omitted_atoms": len(omitted),
        },
    }


# --------------------------------------------------------------- WP3: render

def printed_atom(atom, negated=False):
    """The compact JSON of the full example: no space after a comma."""
    body = json.dumps(atom, ensure_ascii=False, separators=(",", ":"))
    return ("NOT " + body) if negated else body


def printed_rule(rule):
    """One rule line, in the same compact syntax as the candidates.

    `simple_rule_parser.printed`'s shared renaming — a rule whose two atoms
    share a variable must print as sharing it — with this module's spacing.
    """
    names, order = {}, []
    for lit in list(rule.get("body") or []) + [rule.get("head")]:
        if not isinstance(lit, dict):
            continue
        for a in lit["atom"][1:]:
            for v in SP._stage2_vars(a):
                if v not in names:
                    i = len(order)
                    names[v] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                                else "?V%d" % (i + 1))
                    order.append(v)

    def show(lit):
        return printed_atom(SP._rename_s2(lit["atom"], names),
                            negated=lit.get("sign") == "-")
    return "%s -> %s" % (" AND ".join(show(l) for l in rule["body"]),
                         show(rule["head"]))


def render_group(group):
    return "\n".join(["  %-4s %s" % (group["id"], group["printed"]),
                      "       SUGGESTED ROLE: %s" % group["role"],
                      "       COST: %d" % group["cost"]])


def render_candidates(sections):
    parts = []
    for name in SECTION_ORDER:
        mine = sections.get(name) or []
        if not mine:
            continue
        parts.append("%s\n\n%s" % (SECTION_HEADING[name],
                                   "\n\n".join(render_group(g) for g in mine)))
    return "\n\n".join(parts)


def render_case(split):
    return "\n".join(["CASE", "",
                      "PASSAGE (facts and rules):", split["passage"], "",
                      "QUESTION (not a fact):", split["question"]])


NO_PROOF_BLOCK = """RESULT OF THE PREVIOUS TRY

GK found no proof with the rules listed below. Propose missing or corrected
connections. Do not repeat those rules."""

ALTERNATIVE_BLOCK = """RESULT OF THE PREVIOUS TRY

GK found a proof with the rules listed below. Propose different, independently
reasonable connections so the prover can search for another proof. Do not repeat
those rules."""

STATUS_AVAILABLE = "STATUS: ALREADY TRIED; ALL ATOMS AVAILABLE"
STATUS_UNUSABLE = "STATUS: ALREADY TRIED; CANNOT BE REUSED AS WRITTEN"
NEGATIVE_RULE_NOTE = ("REASON: it uses explicit NOT, and explicit negative "
                      "rules are outside the current task")


# ------------------------------------------------------- WP4: attempted rules

def _match_display(atom, display, subst, back):
    """Is `atom` this displayed atom, up to renaming and the allowed
    object-constant generalisation?"""
    if str(atom[0]) != str(display[0]) or len(atom) != len(display):
        return False
    slot = AO.LABEL_SLOT.get(str(display[0]))

    def go(a, b, position, top):
        if isinstance(a, str) and UA.is_variable_term(a):
            if isinstance(b, str) and UA.is_variable_term(b):
                if subst.get(a, b) != b or back.get(b, a) != a:
                    return False
                subst[a], back[b] = b, a
                return True
            # the recorded object-constant generalisation: only in an object or
            # participant position, never in a content-label one
            if top and slot is not None and position == slot:
                return False
            return isinstance(b, str)
        if isinstance(a, str):
            return isinstance(b, str) and not UA.is_variable_term(b) \
                and P5._norm(a) == P5._norm(b)
        if not (isinstance(a, list) and isinstance(b, list)):
            return False
        if str(a[0]) != str(b[0]) or len(a) != len(b):
            return False
        return all(go(x, y, i, False)
                   for i, (x, y) in enumerate(zip(a[1:], b[1:])))
    return all(go(x, y, i, True)
               for i, (x, y) in enumerate(zip(atom[1:], display[1:])))


def atom_availability(atom, groups):
    """-> the displayed atom this rule atom may be copied from, or None.

    An exact copy wins over one that used the allowed generalisation, so the
    id reported is the closest displayed line and not merely the first.
    """
    for exact in (True, False):
        for g in groups:
            if _match_display(atom, g["atom"], {}, {}) \
                    and (not exact
                         or UA.alpha_key(atom) == UA.alpha_key(g["atom"])):
                return g
    return None


def canonical_replacement(atom, groups):
    """The displayed atom that says what an unavailable one said, or None.

    An old rule written with `has degree property(P,X,"none",K)` is not
    reusable as written — that form is no longer displayed — but the collapsed
    atom it compiles to is on the list, and saying so is the difference between
    "your wording is gone" and "your idea is gone".
    """
    for pred in ("has property", "is rel2"):
        got = simpleprops_display(atom, pred)
        if got is None:
            continue
        found = atom_availability(got, groups)
        if found is not None:
            return found
    return None


def rule_atoms(rule):
    """Every atom of an attempted rule, with its sign, from its stored form."""
    out = []
    for key in ("body", "head"):
        part = rule.get(key)
        if part is None:
            continue
        for lit in (part if isinstance(part, list) else [part]):
            if isinstance(lit, dict) and isinstance(lit.get("atom"), list):
                out.append({"sign": lit.get("sign", "+"), "atom": lit["atom"]})
    return out


def attempted_status(rule, groups):
    """-> {status, unavailable, negative, atoms}.  WP4."""
    atoms = rule_atoms(rule)
    negative = any(a["sign"] == "-" for a in atoms)
    unavailable, matched, replacements = [], [], []
    for a in atoms:
        got = atom_availability(a["atom"], groups)
        if got is not None:
            matched.append(got["id"])
            continue
        printed = printed_atom(UA.display_atom(a["atom"]),
                               negated=a["sign"] == "-")
        unavailable.append(printed)
        instead = canonical_replacement(a["atom"], groups)
        if instead is not None:
            replacements.append({"unavailable_atom": printed,
                                 "now_shown_as": instead["id"],
                                 "printed": instead["printed"]})
    reusable = bool(atoms) and not unavailable and not negative
    return {"status": STATUS_AVAILABLE if reusable else STATUS_UNUSABLE,
            "reusable": reusable, "negative": negative,
            "unavailable_atoms": unavailable, "replacements": replacements,
            "matched_candidate_ids": matched, "atoms_checked": len(atoms)}


def render_attempted(rules, statuses, refusals):
    by_id = dict((r.get("rule_id"), r) for r in refusals or [])
    lines = ["RULES ALREADY TRIED", ""]
    if not rules:
        lines.append("  (none)")
    for r in rules:
        st = statuses[r.get("rule_id")]
        lines.append("  %-4s %s" % (r.get("rule_id"), printed_rule(r)))
        lines.append("       %s" % st["status"])
        instead = dict((x["unavailable_atom"], x)
                       for x in st.get("replacements") or [])
        for atom in st["unavailable_atoms"]:
            lines.append("       UNAVAILABLE ATOM: %s" % atom)
            if atom in instead:
                lines.append("       THE SAME CONTENT IS NOW SHOWN AS: %s %s"
                             % (instead[atom]["now_shown_as"],
                                instead[atom]["printed"]))
        if st["negative"]:
            lines.append("       %s" % NEGATIVE_RULE_NOTE)
        refused = by_id.get(r.get("rule_id"))
        if refused and refused.get("why"):
            lines.append("       THE PROGRAM COULD NOT USE IT: %s"
                         % refused["why"])
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


# ------------------------------------------------------------ WP5: the three

def _forbidden(text):
    """Nothing from the scored side of the experiment may reach a prompt."""
    import alignment_protocol as P
    P.assert_no_leak(text, extra_forbidden=("reviewed", "accepted answer",
                                            "expected answer", "gold"))
    banned = ("MAIN CANDIDATES", "SECONDARY CANDIDATES", "USE: PREMISE",
              "USE: CONSEQUENCE", "PRIORITY COST", "GK FORM", "same as before",
              "FOCUS", "POSITIVE:", "NEGATED:", "LEFT", "RIGHT", "EITHER",
              PROBE_CLASS)
    bad = [b for b in banned if b in text]
    if bad:
        raise PromptError("prompt carries retired or internal wording: %s"
                          % bad)
    return True


def _record(call, candidates, blocks, split, attempted=None):
    text = "\n\n".join(b for b in blocks if b)
    _forbidden(text)
    _forbidden(system_prompt())
    block = render_candidates(candidates["sections"])
    return {
        "call": call,
        "version": VERSION,
        "case_id": candidates.get("case_id"),
        "system_prompt_name": SYSTEM_PROMPT_NAME,
        "system_prompt_sha256": system_prompt_sha256(),
        "text": text,
        "sha256": sha256_of(text),
        "chars": len(text),
        "question_split": split,
        "candidate_block": block,
        "candidate_block_sha256": sha256_of(block),
        "attempted_rule_status": attempted,
        "counts": candidates["counts"],
    }


def build_initial_user_prompt(view, candidates):
    split = split_case_text(view)
    blocks = [render_case(split), render_candidates(candidates["sections"]),
              CLOSING_LINE]
    return _record("initial", candidates, blocks, split)


def _followup(call, block, view, candidates, attempted_rules, refusals):
    split = split_case_text(view)
    statuses = dict((r.get("rule_id"), attempted_status(r, candidates["groups"]))
                    for r in attempted_rules or [])
    blocks = [render_case(split), block,
              render_attempted(attempted_rules or [], statuses, refusals or []),
              render_candidates(candidates["sections"]), CLOSING_LINE]
    return _record(call, candidates, blocks, split, statuses)


def build_no_proof_user_prompt(view, candidates, attempted_rules, refusals):
    return _followup("no_proof", NO_PROOF_BLOCK, view, candidates,
                     attempted_rules, refusals)


def build_alternative_user_prompt(view, candidates, attempted_rules, refusals):
    return _followup("alternative", ALTERNATIVE_BLOCK, view, candidates,
                     attempted_rules, refusals)


# ------------------------------------------------------ WP6: split preflight

ALLOWED_SPLITS = (EXACT_SUFFIX, NORMALIZED_SUFFIX)

WHY_REFUSED = {
    UNRESOLVED: "Stage 1 recorded no question or query unit, so the question "
                "cannot be separated from the passage",
    SEPARATE_FIELD: "the stored question could not be located in the input "
                    "text; showing it as a separate field is safe only when "
                    "the input does not contain it",
}


def question_preflight(view):
    """-> one row.  May this case be sent at all?  WP6.

    `separate_question_field` is admitted only when the input demonstrably does
    not carry the question: otherwise the question would also stand in the
    passage, as a fact.
    """
    split = split_case_text(view)
    status = split["status"]
    allowed = status in ALLOWED_SPLITS
    why = None
    if not allowed:
        why = WHY_REFUSED.get(status, "unknown split status")
        if status == SEPARATE_FIELD:
            question = (split["question"] or "").strip()
            words = P5._words(question)
            carried = [w for w in words
                       if w in set(P5._words(split["passage"]))]
            if question and words and len(carried) / float(len(words)) < 0.5:
                allowed, why = True, None
    return {"case_id": view.get("case_id"), "status": status,
            "llm_call_allowed": allowed, "why_refused": why,
            "question": split["question"], "evidence": split["evidence"]}
