"""Construction v3: output forms, structural supplements, a routing protocol.

Two general defects showed up on the AL-70 held-out cases, and neither is about
a particular word.

**A label target names a concept, not a form.**  eb-0001's model named the
operator, the source and a guard correctly and still could not reach the
reviewed rule, because it named the *word* `refraction` and a word carries no
predicate: the head was written with the source's own predicate (`has type`)
when the rule needed `isa`.  The fix is not to make nominalization always emit
`isa` — a relational nominalization must stay relational.  The fix is to declare,
per operator, which output predicate families and arities are permitted, and to
build every permitted form as a separate recorded variant when the target does
not fix one.

**A mechanically recognisable construction can be missed.**  eb-0107's reviewed
rule is derivable from one sentence's own atoms — a property whose label is a
variable, and a two-place link that shares its bearer inside the same unit — but
the model was looking at a different interface (`shoe` is a kind of `object`) and
never proposed it.  Where a pattern is fully determined by shape, code can offer
the hypothesis itself.  A structural supplement is a hypothesis and is labelled
as one: it is never an LLM selection and never a slot completion.

Everything here composes with the frozen v2 library rather than replacing it: a
form variant is built by pinning the predicate and calling `construction_slots`
unchanged, so every check, refusal and provenance record still applies.

Nothing here reads a reviewed rule or an expected answer.
"""

import copy
import re

import alignment_occurrences as AO
import construction_operators as CO
import construction_slots as CS

VERSION = "construction_forms/3.0"

# Synthetic group ids used to pin an output form.  Far above any real id, and
# asserted not to collide.
FORM_ID_BASE = 90001
MAX_TARGET_FORMS = 6
MAX_STRUCTURAL_SUPPLEMENTS = 12

NAMED_GROUP = "named_group"
FRONTIER = "frontier_suggestion"
FALLBACK = "operator_fallback"

# ------------------------------------------------------------------ forms
#
# Per operator: which output predicate families and arities may be built.
# `same_family_as_source` means the operator does not change the shape at all —
# taxonomy relates a class to a class and a relation to a relation, and turning
# `is rel2(member of, X, O)` into `isa(part of, X)` would be a different claim.

FIXED_ISA = [("isa", 1)]

OUTPUT_FORMS = {
    "compound_head": {"forms": FIXED_ISA},
    "argument_label_promotion": {"forms": FIXED_ISA},
    "nominalization": {"by_source_participants": {
        1: [("isa", 1), ("has property", 1), ("has type", 1)],
        2: [("is rel2", 2)]}},
    "event_nominal_equivalence": {"by_role_count": {
        1: [("has property", 1), ("isa", 1)],
        2: [("is rel2", 2)]}},
    "property_class_conversion": {"other_of": ("isa", "has property")},
    "role_or_relation_projection": {"forms": [("is rel2", 2)]},
    "predication_transfer": {"same_family_as_source": True},
    "label_variable_transport": {"same_predicate_as_source": True},
    "typed_taxonomy": {"same_family_as_source": True},
    "other_restructure": {"forms": []},
}

_ANCHOR_SLOT = {"nominalization": "source", "typed_taxonomy": "source",
                "property_class_conversion": "source",
                "role_or_relation_projection": "source",
                "predication_transfer": "predication",
                "label_variable_transport": "holder",
                "event_nominal_equivalence": "event_type",
                "compound_head": "head",
                "argument_label_promotion": "carrier"}


def anchor_of(opspec, filled):
    name = _ANCHOR_SLOT.get(opspec["name"])
    got = filled.get(name) if name else None
    return got[0] if got else None


def permitted_forms(opspec, filled):
    """-> [(predicate, participant count)] this operator may conclude with."""
    decl = OUTPUT_FORMS.get(opspec["name"], {})
    if "forms" in decl:
        return list(decl["forms"])
    anchor = anchor_of(opspec, filled)
    if anchor is None:
        return []
    parts = len(CS._parts(anchor))
    fam = CO.family(anchor["predicate"])
    if "by_source_participants" in decl:
        return list(decl["by_source_participants"].get(parts, []))
    if "by_role_count" in decl:
        n = len(list(filled.get("role") or []) +
                list(filled.get("second_role") or []))
        return list(decl["by_role_count"].get(min(n, 2), []))
    if decl.get("other_of"):
        a, b = decl["other_of"]
        other = b if fam == a else a
        return [(other, 1)]
    if decl.get("same_predicate_as_source"):
        return [(anchor["predicate"], parts)]
    if decl.get("same_family_as_source"):
        return [(fam, 2 if fam == "is rel2" else 1)]
    return []


def frontier_forms(case):
    """(predicate, normalized label) pairs the shown groups actually use."""
    return set((g["predicate"], CO.normalize(g.get("label")))
               for g in case["groups"]
               if isinstance(g.get("label"), str))


def target_form_variants(case, opspec, target, filled):
    """Every permitted form for this target, ordered, nothing chosen silently.

    A GROUP target already fixes predicate, sign, label and arity, and is never
    broadened.  A label target fixes only the word, so each permitted form
    becomes its own recorded variant; a form the frontier also mentions is
    offered first, but a form the frontier does not mention is still offered.
    """
    if target["kind"] == "group":
        g = target["group"]
        return [{"predicate": g["predicate"], "label": g["label"],
                 "sign": g["sign"],
                 "arity": 2 if CO.family(g["predicate"]) == "is rel2" else 1,
                 "origin": NAMED_GROUP,
                 "predicate_family": CO.family(g["predicate"])}]
    label = target.get("text")
    if not isinstance(label, str) or not label:
        return []
    if target.get("is_variable"):
        # The target IS a quantified label position.  It has no word to give a
        # predicate to, and the operator that consumes it (label variable
        # transport) fixes the predicate itself, so there is exactly one form
        # and it must not be pinned through a synthetic group — that would lose
        # the very fact that the label is a variable.
        forms = permitted_forms(opspec, filled)
        return [{"predicate": p, "label": label, "sign": "+", "arity": a,
                 "predicate_family": CO.family(p), "origin": FALLBACK,
                 "keep_original_target": True} for p, a in forms]
    near = frontier_forms(case)
    out = []
    for pred, arity in permitted_forms(opspec, filled):
        out.append({"predicate": pred, "label": label, "sign": "+",
                    "arity": arity, "predicate_family": CO.family(pred),
                    "origin": FRONTIER if (pred, CO.normalize(label)) in near
                    else FALLBACK})
    out.sort(key=lambda f: (0 if f["origin"] == FRONTIER else 1,
                            f["predicate"]))
    return out[:MAX_TARGET_FORMS]


def with_form(case, form):
    """A shallow case copy carrying one synthetic group that pins the form.

    Pinning the predicate through a group is how v2's own emitters are reused
    without touching them: they already treat a group target as fixing the
    predicate, so a form variant is the same code on a different target.
    """
    n = FORM_ID_BASE
    while "G%d" % n in case["by_gid"]:
        n += 1
    gid = "G%d" % n
    g = {"group_id": gid, "predicate": form["predicate"],
         "label": form["label"], "sign": form["sign"],
         "participants": [], "question_target": "synthetic",
         "readable": "%s(%s, ...)" % (form["predicate"], form["label"]),
         "synthetic_form": True}
    out = dict(case)
    out["by_gid"] = dict(case["by_gid"])
    out["by_gid"][gid] = g
    return out, gid


# ------------------------------------------------------------------ build

def build(case, proposal, complete=True, complete_guards=True,
          max_alternatives=CS.MAX_ALTERNATIVES, slot_cap=CS.MAX_COMPLETIONS,
          guard_cap=CS.MAX_GUARD_CANDIDATES):
    """v2's build, once per permitted output form.  Nothing else changes."""
    name = proposal.get("operator")
    if name not in CS.BY_NAME:
        raise CS.SlotError("unknown operator %r" % name)
    opspec = CS.BY_NAME[name]
    if name == "other_restructure":
        raise CS.SlotError("other_restructure builds nothing: the construction "
                           "is recorded as unsupported")
    target = CO.resolve_target(case, proposal.get("target"))
    filled, _prov = CS.fill_named(case, opspec, proposal)
    forms = target_form_variants(case, opspec, target, filled)
    if not forms:
        raise CS.SlotError("no output form is permitted for %s with this "
                           "target" % name)
    alts, refusals, counts = [], [], []
    generated = 0
    for form in forms:
        if form.get("keep_original_target"):
            sub, gid = case, proposal.get("target")
        else:
            sub, gid = with_form(case, form)
        try:
            got = CS.build(sub, dict(proposal, target=gid),
                           complete=complete, complete_guards=complete_guards,
                           max_alternatives=max_alternatives,
                           slot_cap=slot_cap, guard_cap=guard_cap)
        except CO.ConstructionError as e:
            refusals.append({"why": str(e)[:200], "target_form": form})
            continue
        generated += got["alternatives_generated"]
        counts.append(got["candidate_counts"])
        for r in got["refusals"]:
            refusals.append(dict(r, target_form=form))
        for alt in got["alternatives"]:
            rec = alt["record"]
            rec["target"] = proposal.get("target")
            rec["target_form"] = {k: form[k] for k in
                                  ("predicate", "predicate_family", "arity",
                                   "sign", "origin")}
            rec["target_form_origin"] = form["origin"]
            rec["target_form_variants_offered"] = len(forms)
            if any(a["package"] == alt["package"] for a in alts):
                continue
            alts.append(alt)
    return {"alternatives": alts, "refusals": refusals,
            "target_forms": forms, "target_form_count": len(forms),
            "target_forms_capped": len(forms) >= MAX_TARGET_FORMS,
            "candidate_counts": counts[0] if counts else {},
            "alternatives_generated": generated,
            "capped": any(len(alts) >= max_alternatives for _ in [0]),
            "operator": name, "target": target}


# ------------------------------------------------------------------ structural

def bound_label(occ):
    """A label position holding a genuinely QUANTIFIED variable.

    `alignment_occurrences` calls any capitalised token a variable, so
    folio-0169's `German` reads as one.  A structural trigger must not fire on a
    word that merely starts with a capital, so the label must also be bound by a
    quantifier in the occurrence's own binder stack.  This is the difference
    between eb-0107's `forall P` and a proper adjective.
    """
    lab = occ.get("label")
    if not isinstance(lab, str) or not AO._is_var(lab):
        return False
    return any(b[1] == lab for b in (occ.get("binder_stack") or []))


def _same_key(a_occ, a_term, b_occ, b_term):
    """Mechanically the same term: one unit's variable, or one constant.

    A variable in a different unit is NOT the same term — that is an invented
    identification, and a structural supplement never makes one.
    """
    if not isinstance(a_term, str) or not isinstance(b_term, str):
        return False
    if AO._is_var(a_term):
        return (a_occ["unit_id"] == b_occ["unit_id"] and a_term == b_term)
    return CO.normalize(a_term) == CO.normalize(b_term)


def structural_supplements(case, cap=MAX_STRUCTURAL_SUPPLEMENTS):
    """Hypotheses whose whole pattern is present in the logic, not guessed.

    Enabled only for operators whose shape determines the construction with no
    semantic judgment.  `typed_taxonomy` is deliberately excluded: whether one
    word is a kind of another is exactly the judgment code must not make.

    Every supplement records why the trigger fired and what it used, and is kept
    apart from anything the model said.
    """
    out = []
    occs = [(oid, case["by_oid"][oid]) for oid in
            sorted(case["by_oid"], key=lambda k: int(k[1:]))
            if CO.usable_source(case["by_oid"][oid])]
    for hoid, h in occs:
        if not bound_label(h):
            continue
        hp = CS._parts(h)
        if not hp:
            continue
        bearer = hp[0]
        for loid, link in occs:
            if loid == hoid or not CS.form_two_place(link):
                continue
            lp = CS._parts(link)
            ends = [i for i, t in enumerate(lp)
                    if _same_key(h, bearer, link, t)]
            if not ends:
                continue
            for i in ends:
                other = lp[1 - i]
                out.append({
                    "operator": "label_variable_transport",
                    "target": "%s.label" % hoid,
                    "roles": {"holder": [hoid], "link": [loid]},
                    "sources": [],
                    "provenance": "system_structural_supplement",
                    "trigger": {
                        "why": "%s holds a variable label and its bearer %s is "
                               "the %s end of the link %s in the same unit"
                               % (hoid, bearer, "first" if i == 0 else "second",
                                  loid),
                        "holder": hoid, "link": loid,
                        "shared_term": bearer,
                        "conclusion_about": other,
                        "unit": h["unit_id"],
                        "all_links_mechanically_present": True},
                })
                if len(out) >= cap:
                    return out, True
    return out, False


# ------------------------------------------------------------------ routing

_FIELD = re.compile(r"^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$")
MAX_PROPOSALS = 3


def parse_response(text, known_oids, known_targets):
    """v3 routing: a REPORT and PROPOSE lines can both be present.

    v2 read them as competing answers, so a model that diagnosed an
    ordinary-inference gap and also saw a usable construction had to drop one.
    Here the report is the primary diagnosis and any proposals are kept beside
    it; neither suppresses the other, and neither suppresses a structural
    supplement.
    """
    proposes, reports = [], []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        key = k.strip().strip("*_# ").upper()
        if key == "PROPOSE":
            proposes.append(v.strip())
        elif key == "REPORT":
            reports.append(v.strip())
    report, bad_reports = None, []
    for r in reports:
        want = r.strip().strip(".").lower().replace(" ", "_")
        if want in CS.REPORT_OUTCOMES:
            report = want
        else:
            bad_reports.append(r[:80])
    good, bad = [], []
    for line in proposes[-MAX_PROPOSALS:]:
        parsed, why = CS._parse_one(line, known_oids, known_targets)
        if why:
            bad.append({"line": line[:200], "why": why})
        else:
            good.append(parsed)
    return {"readable": bool(report or good),
            "report": report, "rejected_reports": bad_reports,
            "proposals": good, "rejected": bad,
            "lines_seen": len(proposes),
            "lines_read": min(len(proposes), MAX_PROPOSALS),
            "report_and_proposal": bool(report and good)}
