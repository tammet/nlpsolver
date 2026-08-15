"""The only thing that may stop a candidate before gk in discovery mode.

Discovery asks a different question from admission.  Admission asks whether a
rule may be believed; discovery asks whether it can be TRIED.  So the gate here
is mechanical only: a formula is refused when it is broken, not when it is
doubtful.  Semantic uncertainty, BACKGROUND_ONLY, NOT_SUPPORTED, an uncertain
or even counterexampled direction, an unverified attachment, and every
system-added variant all pass this gate and travel as warnings.

The eight hard refusals, and nothing else:

    malformed          the logic will not convert
    unbound            a conclusion variable the body never binds
    witness            a slot occurrence that is not in this case
    mapping            the head's word came from a term the body dropped
    self_contradiction a premise that is the negation of the conclusion
    impossible_identity two different named individuals identified as one
    question_only      built from the question alone and restating its answer
    not_preserved      compilation lost the formula

Pure except for `compiles`, which calls the real bridge compiler because
"unconvertible" cannot be decided any other way.
"""

import json

import construction_operators as CO

VERSION = "mechanical_gate/1.0"

HARD = ("malformed", "unbound", "witness", "mapping", "self_contradiction",
        "impossible_identity", "question_only", "not_preserved")

# Warnings, explicitly NOT refusals.  Named here so a reader can see what
# discovery mode deliberately lets through.
SOFT = ("semantic_uncertainty", "background_only", "not_supported",
        "uncertain_direction", "counterexampled_direction",
        "unverified_attachment", "system_direction_variant",
        "system_guard_supplement", "system_scope_variant",
        "system_target_form_variant", "physical_location_reading")

# Operators whose conclusion word is synthesized from an argument rather than
# taken from the target.  For those, generalising that argument away breaks the
# link between the word and its source, and that is a mapping error.
HEAD_FROM_ARGUMENT = ("category_membership_projection",)


def _split(lit):
    """-> (sign, predicate, label, participants), for either negation form.

    The construction library writes a negated literal as `["not", lit]`; a
    compiled clause writes it as a `-` on the predicate.  Both arrive here, and
    reading only the first form is how a premise that negates its own
    conclusion slipped past this check.
    """
    neg = CO.is_negated(lit)
    atom = CO.strip_neg(lit)
    if isinstance(atom, list) and atom and isinstance(atom[0], str) \
            and atom[0].startswith("-"):
        neg = True
        atom = [atom[0][1:]] + list(atom[1:])
    pred, label, parts = CO.split_atom(atom)
    return ("-" if neg else "+", pred, label, [t for _i, t in parts])


def _vars(lit):
    return set(CO._vars_in(lit))


def _constants(lit):
    out = []
    for t in _split(lit)[3]:
        if isinstance(t, str) and t not in CO._vars_in([t]):
            out.append(t)
    return out


def _words_of(term):
    """Every word a constant could contribute as a label."""
    if not isinstance(term, str):
        return set()
    tail = term.rstrip("/").split("/")[-1].replace("_", " ")
    return {CO.normalize(term), CO.normalize(tail)}


def unbound_head_variables(row):
    body = set()
    for lit in row["body"]:
        body |= _vars(lit)
    return sorted(_vars(row["head"]) - body)


def contradicts_own_conclusion(row):
    hs, hp, hl, ha = _split(row["head"])
    for lit in row["body"]:
        s, p, l, a = _split(lit)
        if p == hp and l == hl and a == ha and s != hs:
            return True
    return False


def head_word_lost_its_source(row):
    """For a synthesized head: the word's constant is gone from the body."""
    ops = set(p.get("operator") for p in row.get("derivation_paths") or [])
    if not (ops & set(HEAD_FROM_ARGUMENT)):
        return False
    label = _split(row["head"])[2]
    if not isinstance(label, str):
        return False
    word = CO.normalize(label)
    for lit in row["body"]:
        for c in _constants(lit):
            if word in _words_of(c):
                return False
    return True


def impossible_identity(row):
    """An attachment that identifies two DIFFERENT named individuals."""
    bad = []
    for p in row.get("derivation_paths") or []:
        for a in p.get("attachments") or []:
            if a.get("status") != "unverified_attachment":
                continue
            detail = a.get("detail") or ""
            parts = detail.split(" with ")
            if len(parts) != 2:
                continue
            right = parts[1].strip()
            left_term = parts[0].split(" of ")[0].strip()
            if "/" in right or right in CO._vars_in([right]):
                continue
            if left_term in CO._vars_in([left_term]):
                continue
            if left_term and right and left_term != right \
                    and not right.startswith("?") \
                    and CO.normalize(left_term) != CO.normalize(right):
                # both sides name something, and they are different names
                bad.append(detail)
    return bad


def question_only_restatement(row, case, question_literals):
    """Built from question occurrences alone AND restating the question."""
    occs = []
    for p in row.get("derivation_paths") or []:
        occs.extend(p.get("required_slot_completions") or [])
        occs.extend(p.get("system_guard_supplements") or [])
    roles = []
    by_oid = {}
    for r in case.get("occurrences") or []:
        by_oid[r["oid"]] = r
        by_oid[r["occurrence_id"]] = r
    for o in occs:
        row_ = by_oid.get(o)
        if row_ is not None:
            roles.append(row_.get("role"))
    if not roles or any(r != "question" for r in roles):
        return False
    hs, hp, hl, _ha = _split(row["head"])
    for lit in question_literals:
        s, p, l, _a = _split(lit)
        if (s, p, l) == (hs, hp, hl):
            return True
    return False


def question_literals(view):
    """Literals the question clauses assert or deny, for the check above."""
    out = []
    for c in view.get("final_clauses") or []:
        if not isinstance(c, dict):
            continue
        if c.get("@sourcetype") != "question" and "@question" not in c:
            continue
        body = c.get("@logic") or c.get("@question")
        if not isinstance(body, list) or not body:
            continue
        lits = body if isinstance(body[0], list) else [body]
        out.extend(l for l in lits if isinstance(l, list) and l)
    return out


def compiles(row, package, view, configuration):
    """-> (clauses, why).  The real compiler, because nothing else decides."""
    import bridge_world as BW
    try:
        clauses, _rec = BW.compile_bridge(
            view["case_id"], "gate", package, view["stage1"], view["stage2"],
            configuration, base_clauses=view["final_clauses"],
            hypothesis_id="GATE")
    except Exception as e:                                    # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, str(e)[:160])
    if not clauses:
        return None, "the conversion produced no clause"
    return clauses, None


def preserved(row, clauses):
    """Did the compiled clause keep the formula's predicates?"""
    blob = json.dumps(clauses)
    want = [_split(row["head"])[1]] + [_split(l)[1] for l in row["body"]]
    missing = [p for p in set(want) if p and p not in blob]
    return (not missing), missing


def check(row, package, view, case, configuration, qlits=None):
    """-> {"passed": bool, "refusals": [...], "warnings": [...]}."""
    refusals, warnings = [], []
    unbound = unbound_head_variables(row)
    if unbound:
        refusals.append({"kind": "unbound",
                         "why": "the conclusion uses %s, which the body never "
                                "binds" % ", ".join(unbound)})
    if contradicts_own_conclusion(row):
        refusals.append({"kind": "self_contradiction",
                         "why": "a premise is the negation of the conclusion"})
    if head_word_lost_its_source(row):
        refusals.append({"kind": "mapping",
                         "why": "the conclusion's word was taken from a term "
                                "the body no longer mentions"})
    bad = impossible_identity(row)
    if bad:
        refusals.append({"kind": "impossible_identity",
                         "why": "two different named things are identified: "
                                "%s" % bad[0]})
    by_oid = set()
    for r in case.get("occurrences") or []:
        by_oid.add(r["oid"])
        by_oid.add(r["occurrence_id"])
    unknown = []
    for p in row.get("derivation_paths") or []:
        for o in (p.get("required_slot_completions") or []) + \
                (p.get("system_guard_supplements") or []):
            if o not in by_oid:
                unknown.append(o)
    if unknown:
        refusals.append({"kind": "witness",
                         "why": "slot occurrence(s) not in this case: %s"
                                % ", ".join(sorted(set(unknown))[:3])})
    if question_only_restatement(row, case,
                                 qlits if qlits is not None
                                 else question_literals(view)):
        refusals.append({"kind": "question_only",
                         "why": "built from question occurrences alone and "
                                "restating the question's own literal"})
    clauses = None
    if package is None:
        refusals.append({"kind": "malformed",
                         "why": "no Stage-2 package was resolved"})
    else:
        clauses, why = compiles(row, package, view, configuration)
        if why:
            refusals.append({"kind": "malformed", "why": why})
        else:
            ok, missing = preserved(row, clauses)
            if not ok:
                refusals.append({"kind": "not_preserved",
                                 "why": "compilation lost %s"
                                        % ", ".join(missing)})
    for p in row.get("derivation_paths") or []:
        for name, flag in (("system_direction_variant",
                            p.get("system_direction_variant")),
                           ("system_guard_supplement",
                            bool(p.get("system_guard_supplements"))),
                           ("system_scope_variant",
                            p.get("system_scope_variant")),
                           ("system_target_form_variant",
                            p.get("system_target_form_variant")),
                           ("unverified_attachment",
                            p.get("has_unverified_attachment"))):
            if flag and name not in warnings:
                warnings.append(name)
    return {"passed": not refusals, "refusals": refusals,
            "warnings": warnings,
            "clause_count": len(clauses or []),
            "gate_version": VERSION}
