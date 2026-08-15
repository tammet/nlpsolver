"""The semantic admission stage: judge, guard selection, falsifier, policy.

The stage this replaces sent only proof-active rules to one model call, told it
those were "RULES THE PROVER USED", and promoted whatever came back admitting.
That is a utility signal presented as a semantic one, and in the 08-10 corrected
run it promoted a rule concluding the complement of the reviewed rule, twice,
and a control rule quantified over a property label.

Here nothing about gk reaches a prompt.  A candidate is put to three separate
questions — is this connection licensed, which restriction does it need, and can
it be broken — and promoted only if the mechanical gates, all three answers and
the opposite-head adjudication agree.

Only footer lines are parsed.  Prose is never scraped for a verdict: a model
that reasons its way to REJECT and then writes an encouraging closing paragraph
must come out as REJECT.
"""

import os
import re

import admission_checks as AK
import alignment_protocol as P
import formula_print as FP

PROMPT_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "prompts", "dynamic_alignment")

# v2 adds one section to each v1 prompt: how to read the notation.  The first
# experiment showed the falsifier reading `isa(TYPE, THING)` backwards and
# reading a universally quantified antecedent variable as "for all of them at
# once", and rejecting two intended rules on those readings.  Nothing about any
# case, answer or verdict is in the added text — it describes the notation.
# v3 adds three things to v2: every occurrence carries its role, and a query
# role carries the warning that a question is not evidence; conditions are shown
# as the guard the compiler actually produces; and both models must name what
# the connection rests on, from a fixed list, because "the passage does not say
# so" was failing exactly the abstractions this stage exists to admit.
JUDGE_PROMPT = "meaning_judge_v3"
GUARD_PROMPT = "guard_select_v3"
FALSIFIER_PROMPT = "falsifier_v3"

MECHANISMS = ("paraphrase_or_synonym", "taxonomic_abstraction",
              "nominalization_or_event_state_reformulation",
              "argument_or_role_reformulation",
              "compound_or_modifier_abstraction",
              "local_identity_or_coreference",
              "contextual_relational_interpretation")

JUDGE_VERDICTS = ("ACCEPT", "NEEDS_GUARD", "REJECT", "UNCERTAIN")
PAIR_VERDICTS = ("FIRST", "SECOND", "NEITHER", "UNCERTAIN")
FALSIFIER_VERDICTS = ("PASS", "FAIL", "UNCERTAIN")
FAULTS = ("direction", "sign", "arguments", "missing_guard", "scope",
          "not_an_alignment", "counterexample", "evidence_category", "none")

# What a bridge rests on.  The first three are representation and lexical
# abstraction and may be promoted; a stable background relation is real
# knowledge but is not an alignment and is recorded only; the last three are
# never promoted.  No numeric weight is attached to any of them here.
EVIDENCE = ("TEXTUAL_REPRESENTATION", "LEXICAL_TAXONOMY",
            "CONVENTIONAL_NOMINALIZATION_OR_ROLE", "STABLE_BACKGROUND_RELATION",
            "SPECULATIVE_CORRELATION", "OPEN_WORLD_NEGATIVE", "NONE")
PROMOTABLE_EVIDENCE = ("TEXTUAL_REPRESENTATION", "LEXICAL_TAXONOMY",
                       "CONVENTIONAL_NOMINALIZATION_OR_ROLE")
RECORDED_ONLY_EVIDENCE = ("STABLE_BACKGROUND_RELATION",)

MAX_GUARDS = AK.MAX_CONDITIONS


class AdmissionError(Exception):
    pass


def instructions(name):
    with open(os.path.join(PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_hashes():
    import hashlib
    return {n: hashlib.sha256(instructions(n).encode()).hexdigest()[:16]
            for n in (JUDGE_PROMPT, GUARD_PROMPT, FALSIFIER_PROMPT)}


# ------------------------------------------------- WP2: what a position means
#
# The v1/v2 falsifier read the question "Are no politicians part of the
# Reichstag?" as an assertion that they are not, and failed a rule on that.  A
# question supplies wording and a target representation; it is not evidence
# about what holds.  Every occurrence now carries its role in plain words, and
# the two query roles carry the same warning next to them.

ROLES = {
    "fact": "ASSERTED FACT",
    "rule premise": "ASSERTED RULE PREMISE",
    "rule conclusion": "ASSERTED RULE CONCLUSION",
    "question goal": "QUERY WORDING — NOT ASSERTED TRUE OR FALSE",
    "question assumption":
        "QUERY ASSUMPTION USED BY REFUTATION — NOT A BACKGROUND FACT",
}

QUERY_ROLES = ("question goal", "question assumption")

QUERY_NOTE = ("This tells you which expression and sense the question uses. It "
              "is not evidence that the expression is true, false, or denied. "
              "Do not use the question's polarity to validate or falsify the "
              "proposed bridge.")


def role_of(position):
    return ROLES.get(position, "ASSERTED FACT")


def is_query(position):
    return position in QUERY_ROLES


# ------------------------------------------------- WP3: compiled guard preview
#
# A condition was offered as its source atom, `isa(animal, ?Y)`, while the rule
# was displayed with the compiler's own variables, `love(?V1, ?V2)`.  Sonnet
# read `?Y` as a variable the rule does not have and answered UNAVAILABLE — for
# a guard the compiler would in fact unify.  So each condition is now compiled
# WITH the rule and shown as the guard it actually becomes.

def guard_previews(case_id, schema_id):
    """-> [{alias, source_atom, compiled_guard, if_selected, unavailable}].

    Every preview comes from the real compiler run on the construction witness
    plus that one condition; the added antecedent is what the compiled rule has
    and the base does not.  A condition that cannot compile, that changes the
    head, that leaves a variable in a content label, that contradicts the
    conclusion, that adds nothing, or that duplicates another's compiled guard
    is marked unavailable and says why.
    """
    import admission_cases as CASES
    import alignment_compare as CMP
    import alignment_rule as AR
    import bridge_world as BW
    view, gen, _ = CASES.space(case_id)
    s = CASES.schema(case_id, schema_id)
    base = s["stage2_rule"]
    w = s["construction_witness"]
    base_atoms = _atom_strings(base)
    out, seen = [], {}
    for alias, m in CASES.menu(case_id, schema_id):
        row = {"alias": alias, "source_atom": FP.formula(m["atom"]),
               "occurrence": m["occurrence_id"],
               "why_offered": m["why_offered"]}
        try:
            pkg, _rec = AR.compile_from_base(
                w["producer"], w["consumer"], [m["occurrence_id"]],
                gen["table"], target_mode=w.get("target_mode"),
                require_range_restriction=True)
            pkg = BW.to_defeasible_shape(pkg)
        except (AR.RuleError, BW.BridgeError) as e:
            row["unavailable"] = "the compiler refuses it: %s" % e
            out.append(row)
            continue
        added = [a for a in _atom_strings(pkg) if a not in base_atoms]
        if not added:
            row["unavailable"] = "it adds no condition after canonicalization"
            out.append(row)
            continue
        same = CMP.compare(pkg, base, mode="exact")
        if not same.get("comparable") or same["direction"] != "forward" \
                or same["missing_antecedents"]:
            row["unavailable"] = "it would change the rule, not restrict it"
            out.append(row)
            continue
        gates = AK.mechanical_gates(pkg, base_pkg=base,
                                    condition_atoms=[m["atom"]])
        if not gates["ok"]:
            row["unavailable"] = ", ".join(r["name"] for r in gates["refusals"])
            out.append(row)
            continue
        guard = "; ".join(added)
        if guard in seen:
            row["unavailable"] = "same compiled guard as %s" % seen[guard]
            out.append(row)
            continue
        seen[guard] = alias
        row["compiled_guard"] = guard
        row["if_selected"] = FP.formula(pkg)
        out.append(row)
    return out


def _atom_strings(pkg):
    import alignment_compare as CMP
    try:
        r = CMP.parse_rule_package(pkg)
    except CMP.ShapeError:
        return []
    return [AK._show(a) for a in r["antecedents"]]


# ---------------------------------------------------------------- prompts

def _sentences(ch):
    return "\n".join("  %s  %s" % (s["unit_id"], s["text"])
                     for s in ch["sentences"])


def _sides(ch):
    lines, queried = [], False
    for ev in ch["source_evidence"][:3]:
        for side, unit, pos, phrase in (
                ("left", ev["producer_unit"], ev["producer_position"],
                 ev.get("producer_phrase")),
                ("right", ev["consumer_unit"], ev["consumer_position"],
                 ev.get("consumer_phrase"))):
            lines.append("    %s side: %s, %s%s"
                         % (side, unit, role_of(pos),
                            ", the words %r" % phrase if phrase else ""))
            queried = queried or is_query(pos)
    if len(ch["source_evidence"]) > 3:
        lines.append("    (the same rule arises from %d further places)"
                     % (len(ch["source_evidence"]) - 3))
    if queried:
        lines.append("    %s" % QUERY_NOTE)
    return "\n".join(lines)


def _terms(ch):
    return "\n".join("    %-46s %s" % (t["term"], t["kind"])
                     for t in ch["terms"])


def _reading(ch):
    w = ch.get("in_words") or {}
    lines = ["    if all of: %s" % "; ".join(w.get("if_all_of") or []),
             "    then normally: %s" % w.get("then_normally")]
    if w.get("conclusion_is_negative"):
        lines.append("    the conclusion is a DENIAL: the rule concludes that "
                     "this does NOT hold")
    return "\n".join(lines)


def _conditions(ch, previews=None):
    """Conditions as the guards they compile to, not as raw source atoms."""
    rows = previews if previews is not None else previews_for(ch)
    if not rows:
        return "    none are available for this rule"
    out = []
    for r in rows:
        if r.get("unavailable"):
            out.append("    %-4s %-52s  UNAVAILABLE: %s"
                       % (r["alias"], r["source_atom"], r["unavailable"]))
            continue
        out.append("    %-4s source atom:    %s" % (r["alias"], r["source_atom"]))
        out.append("         compiled guard: %s" % r["compiled_guard"])
        out.append("         if selected:    %s" % r["if_selected"])
    return "\n".join(out)


def previews_for(ch):
    """The compiled guard previews for a challenge, or [] if it has no menu."""
    try:
        return guard_previews(ch["case_id"], ch["schema_id_in_run"])
    except Exception:                                   # noqa: BLE001
        return []


def selectable(ch, previews=None):
    rows = previews if previews is not None else previews_for(ch)
    return [r["alias"] for r in rows if not r.get("unavailable")]


def _one_rule_block(ch, label="THE PROPOSED RULE"):
    return "\n".join([
        "%s:\n    %s" % (label, ch["rule"]),
        "READ AS:\n%s" % _reading(ch),
        "WHERE EACH SIDE COMES FROM:\n%s" % _sides(ch),
        "TERMS:\n%s" % _terms(ch),
        "POSSIBLE ADDITIONAL ANTECEDENTS (not chosen here):\n%s"
        % _conditions(ch)])


def build_judge_prompt(ch, sibling=None):
    """One candidate, or one opposite-head pair, for the meaning judge."""
    parts = ["ENGLISH TEXT:\n%s" % ch["input_text"],
             "SENTENCES AS PARSED:\n%s" % _sentences(ch)]
    if sibling is None:
        parts.append(_one_rule_block(ch))
    else:
        parts.append("TWO RULES THAT CONCLUDE OPPOSITE THINGS FROM THE SAME "
                     "PREMISE.  At most one can be licensed.")
        parts.append(_one_rule_block(ch, "FIRST RULE"))
        parts.append(_one_rule_block(sibling, "SECOND RULE"))
    prompt = instructions(JUDGE_PROMPT) + "\n\n" + "\n\n".join(parts)
    _no_leak(prompt)
    return prompt


def build_guard_prompt(ch, guard_needed):
    parts = ["ENGLISH TEXT:\n%s" % ch["input_text"],
             "SENTENCES AS PARSED:\n%s" % _sentences(ch),
             _one_rule_block(ch),
             "THE RESTRICTION THE RULE WAS SAID TO NEED:\n    %s"
             % (guard_needed or "(not stated)"),
             "THE CONDITIONS YOU MAY CHOOSE FROM:\n%s" % _conditions(ch)]
    prompt = instructions(GUARD_PROMPT) + "\n\n" + "\n\n".join(parts)
    _no_leak(prompt)
    return prompt


def build_falsifier_prompt(ch, final_formula):
    parts = ["ENGLISH TEXT:\n%s" % ch["input_text"],
             "SENTENCES AS PARSED:\n%s" % _sentences(ch),
             "THE RULE TO ATTACK:\n    %s" % final_formula,
             "READ AS:\n%s" % _reading(ch),
             "WHERE EACH SIDE COMES FROM:\n%s" % _sides(ch),
             "TERMS:\n%s" % _terms(ch)]
    prompt = instructions(FALSIFIER_PROMPT) + "\n\n" + "\n\n".join(parts)
    _no_leak(prompt)
    return prompt


def _no_leak(prompt):
    """No answer, label, reviewed formula, gk result or proof activity."""
    P.assert_no_leak(prompt, extra_forbidden=(
        "the prover", "gk ", "proof-active", "bridge_cited",
        "accepted_llmpipe_answers", "reviewed rule", "expected answer"))
    return True


# ---------------------------------------------------------------- parsing
#
# Footer only.  A verdict is read from a line that starts with the key, and from
# nowhere else; a response whose footer is missing or unreadable is a formatting
# failure, not a silent default.

def _footer(text, key, allowed):
    """The LAST `KEY: value` line whose value is in `allowed`."""
    found = None
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() != key:
            continue
        v = v.strip().strip("*_. ")
        for a in allowed:
            if v.upper() == a.upper():
                found = a
                break
    return found


def _free_footer(text, key):
    found = None
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() == key:
            found = v.strip().strip("*_ ")
    return found


def parse_judge(text, pair=False):
    """-> {"verdict", "mechanism", "evidence", "guard_needed", "readable"}."""
    allowed = PAIR_VERDICTS if pair else JUDGE_VERDICTS
    verdict = _footer(text, "FINAL", allowed)
    mech = _footer(text, "MECHANISM", MECHANISMS + ("none",))
    ev = _footer(text, "EVIDENCE", EVIDENCE)
    guard = _free_footer(text, "GUARD_NEEDED")
    if guard and guard.strip().lower() in ("none", "n/a", "-"):
        guard = None
    return {"verdict": verdict, "mechanism": mech, "evidence": ev,
            "guard_needed": guard, "readable": verdict is not None}


def parse_guards(text, known_aliases):
    """-> {"guards", "unavailable", "none", "unknown", "readable"}."""
    line = _free_footer(text, "GUARDS")
    if line is None:
        return {"guards": [], "unavailable": False, "none": False,
                "unknown": [], "readable": False}
    up = line.strip().upper().strip(".")
    if up == "UNAVAILABLE":
        return {"guards": [], "unavailable": True, "none": False,
                "unknown": [], "readable": True}
    if up == "NONE":
        return {"guards": [], "unavailable": False, "none": True,
                "unknown": [], "readable": True}
    ids = re.findall(r"\bG\d+\b", line.upper())
    good = [i for i in ids if i in known_aliases]
    bad = [i for i in ids if i not in known_aliases]
    return {"guards": good[:MAX_GUARDS], "unavailable": False, "none": False,
            "unknown": bad, "over_cap": len(good) > MAX_GUARDS,
            "readable": True}


def parse_falsifier(text):
    verdict = _footer(text, "FINAL", FALSIFIER_VERDICTS)
    fault = _footer(text, "FAULT", FAULTS)
    ev = _footer(text, "EVIDENCE", EVIDENCE)
    return {"verdict": verdict, "fault": fault, "evidence": ev,
            "readable": verdict is not None}


# ---------------------------------------------------------------- policy

PROMOTE = "promote"
KEEP_AS_PROBE = "keep_as_unverified_probe"


def decide(mechanical, judge, guards, falsifier, pair_verdict=None,
           is_first_of_pair=None):
    """The whole admission decision, in one place.

    Promotion needs every one of: the mechanical gates, a meaning verdict of
    ACCEPT (or NEEDS_GUARD whose guard was legally compiled), an allowed
    mechanism, a falsifier PASS, and — when the rule has an opposite-head
    sibling — an adjudication naming THIS rule.  Anything else keeps the probe
    result at its own low weight and promotes nothing.
    """
    why = []
    if mechanical and not mechanical.get("ok"):
        why += ["mechanical:%s" % r["name"] for r in mechanical["refusals"]]
    jv = (judge or {}).get("verdict")
    if jv is None:
        why.append("judge:unreadable")
    elif jv == "REJECT":
        why.append("judge:rejected_not_an_alignment")
    elif jv == "UNCERTAIN":
        why.append("judge:uncertain")
    elif jv == "NEEDS_GUARD":
        if not guards or not guards.get("compiled"):
            why.append("judge:needs_guard_not_supplied")
        elif guards.get("mechanical") and not guards["mechanical"]["ok"]:
            why += ["guard:%s" % r["name"]
                    for r in guards["mechanical"]["refusals"]]
    mech = (judge or {}).get("mechanism")
    if jv in ("ACCEPT", "NEEDS_GUARD") and mech not in MECHANISMS:
        why.append("judge:no_allowed_mechanism")
    # what the bridge rests on decides eligibility.  A stable background
    # relation is real knowledge and is recorded, not promoted; a correlation or
    # an open-world denial is neither.
    ev = _evidence(judge, falsifier)
    if jv in ("ACCEPT", "NEEDS_GUARD"):
        if ev is None:
            why.append("evidence:not_reported")
        elif ev in RECORDED_ONLY_EVIDENCE:
            why.append("evidence:recorded_only_%s" % ev.lower())
        elif ev not in PROMOTABLE_EVIDENCE:
            why.append("evidence:not_promotable_%s" % ev.lower())
    fv = (falsifier or {}).get("verdict")
    if fv is None:
        why.append("falsifier:not_run_or_unreadable")
    elif fv == "FAIL":
        why.append("falsifier:failed_%s" % ((falsifier or {}).get("fault")
                                            or "unspecified"))
    elif fv == "UNCERTAIN":
        why.append("falsifier:uncertain")
    if pair_verdict is not None:
        if pair_verdict in (None, "UNCERTAIN", "NEITHER"):
            why.append(AK.OPPOSITE_HEAD_CONFLICT)
        elif is_first_of_pair is True and pair_verdict != "FIRST":
            why.append("opposite_head:the_other_one_was_licensed")
        elif is_first_of_pair is False and pair_verdict != "SECOND":
            why.append("opposite_head:the_other_one_was_licensed")
    return {"outcome": PROMOTE if not why else KEEP_AS_PROBE,
            "refusals": why, "evidence": _evidence(judge, falsifier)}


def _evidence(judge, falsifier):
    """The category, from the falsifier if it named one, else from the judge.

    The falsifier sees the final compiled rule, including any guard, so when the
    two disagree its reading is the later one.  A disagreement is visible in the
    record because both are stored.
    """
    fe = (falsifier or {}).get("evidence")
    je = (judge or {}).get("evidence")
    if fe in EVIDENCE:
        return fe
    return je if je in EVIDENCE else None


def render_unverified(hypothesis_id, weight, answer, semantic_status):
    """A probe that was not promoted is still an answer, and says why not.

    Never `Unknown.` merely because the weight is low, and never deleted
    because the semantic stage declined it.
    """
    value = {"True.": "possibly true", "False.": "possibly false"}.get(
        answer, "no answer")
    return ("Unverified alternative: %s, weight %s, under hypothesis %s; "
            "semantic status: %s." % (value, _num(weight), hypothesis_id,
                                      semantic_status))


def _num(x):
    return ("%.4g" % x) if isinstance(x, float) else str(x)
