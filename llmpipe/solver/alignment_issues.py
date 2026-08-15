"""Deterministic alignment issue detectors over the occurrence table (DA2 WP2).

Plan: memos/PLAN_2026_08_09_dynamic_abstraction_alignment_pilot_opus5.md §8.

Nine issue kinds (1-9) report a structural problem; four (10-13) are ranking
hints that select what to compare and are never by themselves a reason to merge
concepts or drop a premise.  Every issue names the occurrence ids and source
units that triggered it — a warning without located occurrences is forbidden by
the plan and by this module.

Two things this layer deliberately does not do:

  * it does not attempt general semantic equivalence ("gardening" vs "planting
    seeds").  Unpaired nearby occurrences are handed to the critic instead;
  * it never consults an expected answer or whether GK proves anything.

No LLM calls, no GK.
"""

import re

import alignment_occurrences as AO

SEVERITIES = ("hard_error", "likely_mismatch", "diagnostic")

# How an issue may be SCORED, which is not the same as how bad it is.
#
#   hard_error       the issue claims an actual translation defect.  Precision
#                    and false positives are meaningful and will be measured.
#   candidate_hint   the issue only says which pair or area to look at.  A high
#                    false-positive volume is acceptable inside the per-case cap:
#                    a same-label warning can be useful even when the correct
#                    critic decision is KEEP.
#   diagnostic_probe the issue is not a semantic prediction at all (it counts
#                    premises or question components).  It gets no
#                    false-positive score.
#
# Applying one false-positive gate across all three would be a category error,
# so the score report keeps them apart.
EVALUATION_CATEGORY = {
    "entity_split": "hard_error",
    "dependent_reference_split": "hard_error",
    "modifier_bearer_split": "hard_error",
    "free_rule_conclusion": "hard_error",
    "stage1_unrepresented": "hard_error",
    "stage2_unsourced": "hard_error",
    "bound_class_corruption": "candidate_hint",
    "referenced_event_fold_risk": "candidate_hint",
    "question_no_supplier_signature": "candidate_hint",
    "same_label_different_context": "candidate_hint",
    "similar_label_different_context": "candidate_hint",
    "rule_premise_load": "diagnostic_probe",
    "question_component_load": "diagnostic_probe",
}
EVALUATION_CATEGORIES = ("hard_error", "candidate_hint", "diagnostic_probe")

# Class-ish labels that carry no problem-specific meaning.  Excluded when
# counting "meaning-bearing" premises and question components.
STRUCTURAL_LABELS = {"activity", "thing", "object", "entity", "event"}
STRUCTURAL_PREDS = {"typical", "actuality", "capability", "necessity",
                    "obligation", "volition", "intention", "expectation",
                    "speech_act", "state time", "has time"}


def _issue(kind, unit_ids, occ_ids, summary, evidence, severity):
    assert severity in SEVERITIES
    assert occ_ids or unit_ids, "an issue must locate itself"
    assert kind in EVALUATION_CATEGORY, "every issue kind needs a score category"
    return {"issue_id": "%s:%s" % (kind, ",".join(sorted(set(unit_ids))) or "-"),
            "kind": kind,
            "unit_ids": sorted(set(unit_ids)),
            "occurrence_ids": sorted(set(occ_ids)),
            "summary": summary,
            "evidence": evidence,
            "severity": severity,
            "evaluation_category": EVALUATION_CATEGORY[kind]}


def content_label(o):
    """The problem-specific word an occurrence is about.

    Predicates with a label slot (`isa`, `is rel2`, `has property`, ...) carry
    their word in that slot.  The rest — role atoms, `have`, `=` — are named by
    the logical vocabulary itself, so what they are about is their first
    non-variable argument.  A variable carries no word at all: normalizing it
    would turn the variable X into the "label" x and make every such atom look
    as if Stage 2 had invented vocabulary.
    """
    if AO.LABEL_SLOT.get(o.get("predicate")) is not None:
        return "" if o.get("label_is_variable") else o["normalized_label"]
    for a in o.get("arguments_or_roles") or []:
        if isinstance(a, str) and not AO._is_var(a):
            return AO.normalize_label(a)
    return ""


def _depluralize(n):
    """Crude singular form, for comparison only — Stage 1 records surface ids
    ('decomposers') where Stage 2 uses the class ('decomposer')."""
    if len(n) > 3 and n.endswith("ies"):
        return n[:-3] + "y"
    if len(n) > 3 and n.endswith("es") and n[-3] in "sxzh":
        return n[:-2]
    if len(n) > 2 and n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n


def same_word(a, b):
    a, b = AO.normalize_label(a), AO.normalize_label(b)
    return bool(a) and (a == b or _depluralize(a) == _depluralize(b))


def arg_labels(o):
    """Every argument of an atom as a normalized label, variables excluded."""
    out = []
    for a in o.get("arguments_or_roles") or []:
        if isinstance(a, str) and not AO._is_var(a):
            out.append(AO.normalize_label(a))
    return out


def _meaning_bearing(o):
    if o["kind"] in ("rule_variable", "modal"):
        return False
    if o.get("predicate") in STRUCTURAL_PREDS:
        return False
    if content_label(o) in STRUCTURAL_LABELS:
        return False
    if not content_label(o):
        return False
    return True


# ------------------------------------------------------------------ 1-9

def entity_split(table, stage1, stage2):
    """One explicit Stage-1 entity id is a constant somewhere and a freshly
    bound object elsewhere in the same problem."""
    out = []
    named = {}
    for o in table["stage1"]:
        if o["kind"] == "entity" and o.get("entity_type") in (
                "named", "definite", "concrete"):
            named.setdefault(o["normalized_label"], []).append(o)
    const_use, bound_use = {}, {}
    for o in table["stage2"]:
        lbl = AO.normalize_label(o.get("term"))
        if lbl and not o.get("term_is_variable"):
            const_use.setdefault(lbl, []).append(o)
        if o["kind"] == "class" and o.get("term_is_variable"):
            bound_use.setdefault(o["normalized_label"], []).append(o)
    for lbl, s1occs in sorted(named.items()):
        if lbl in const_use and lbl in bound_use:
            occ = ([x["occurrence_id"] for x in s1occs]
                   + [x["occurrence_id"] for x in const_use[lbl]]
                   + [x["occurrence_id"] for x in bound_use[lbl]])
            units = [x["unit_id"] for x in s1occs + const_use[lbl] + bound_use[lbl]]
            out.append(_issue(
                "entity_split", units, occ,
                "Stage 1 names %r as one entity, but Stage 2 uses it both as a "
                "constant and as the class of a separately bound object, so the "
                "two mentions cannot refer to the same thing." % lbl,
                {"label": lbl,
                 "constant_units": sorted(set(x["unit_id"] for x in const_use[lbl])),
                 "bound_units": sorted(set(x["unit_id"] for x in bound_use[lbl]))},
                "likely_mismatch"))
    return out


def dependent_reference_split(table, stage1, stage2):
    """Inside one package a class is both a literal term and the class of a
    bound variable: the dependent participant was not coindexed."""
    out = []
    by_unit = {}
    for o in table["stage2"]:
        by_unit.setdefault(o["unit_id"], []).append(o)
    for uid, occs in sorted(by_unit.items()):
        literal = {}
        bound = {}
        for o in occs:
            t = AO.normalize_label(o.get("term"))
            if t and not o.get("term_is_variable") and o["kind"] != "class":
                literal.setdefault(t, []).append(o)
            if (o["kind"] == "class" and o.get("term_is_variable")
                    and not o.get("label_is_variable")):
                bound.setdefault(o["normalized_label"], []).append(o)
        for lbl in sorted(set(literal) & set(bound)):
            occ = ([x["occurrence_id"] for x in literal[lbl]]
                   + [x["occurrence_id"] for x in bound[lbl]])
            out.append(_issue(
                "dependent_reference_split", [uid], occ,
                "In %s the class %r is used both as a literal term and as the "
                "class of a separately bound object, so the two uses are not "
                "the same individual." % (uid, lbl),
                {"unit": uid, "label": lbl,
                 "literal_paths": [x["json_path"] for x in literal[lbl]],
                 "bound_paths": [x["json_path"] for x in bound[lbl]]},
                "likely_mismatch"))
        # Second trigger: one class binds two different existential variables
        # on opposite sides of the same rule ("a seed ... the seed" became two
        # unrelated objects).  This is the mle2-0049 construction.
        sides = {}
        for o in occs:
            if (o["kind"] != "class" or not o.get("term_is_variable")
                    or o.get("label_is_variable")):
                continue
            if not any(b[0] == "exists" and b[1] == o.get("term")
                       for b in o["binder_stack"]):
                continue
            # Two `exists Y` in different scopes reuse the variable name, so the
            # binder stack — not the name — is what tells the objects apart.
            scope = tuple(tuple(b) for b in o["binder_stack"])
            sides.setdefault(o["normalized_label"], {}).setdefault(
                (o.get("term"), scope), []).append(o)
        for lbl, byvar in sorted(sides.items()):
            # Two distinct events on the two sides of a rule are ordinary, not a
            # reference split: `activity` and friends carry no participant
            # identity to lose.
            if len(byvar) < 2 or lbl in STRUCTURAL_LABELS:
                continue
            occs_l = [x for v in byvar.values() for x in v]
            rside = sorted(set(x["rule_side"] for x in occs_l))
            if len(rside) < 2:
                continue
            out.append(_issue(
                "dependent_reference_split", [uid],
                [x["occurrence_id"] for x in occs_l],
                "In %s the class %r binds %d separate existential objects across "
                "%s of the rule, so the participant introduced on one side is not "
                "the one referred to on the other."
                % (uid, lbl, len(byvar), " and ".join(rside)),
                {"unit": uid, "label": lbl,
                 "variables": sorted(v for v, _ in byvar),
                 "rule_sides": rside}, "likely_mismatch"))
    return out


def modifier_bearer_split(table, stage1, stage2):
    """A Stage-1 modifier and the role it modifies land on a literal kind
    constant instead of one bound object."""
    out = []
    s1_mods = [o for o in table["stage1"] if o["kind"] == "property" and o.get("bearer")]
    for m in s1_mods:
        uid, bearer = m["unit_id"], AO.normalize_label(m.get("bearer"))
        bad_prop = [o for o in table["stage2"]
                    if o["unit_id"] == uid and o["kind"] == "property"
                    and o["normalized_label"] == m["normalized_label"]
                    and not o.get("term_is_variable")
                    and AO.normalize_label(o.get("term")) in (bearer, bearer + "s")]
        if not bad_prop:
            continue
        roles = [o for o in table["stage2"]
                 if o["unit_id"] == uid and o["kind"] == "event_role"
                 and not o.get("term_is_variable")
                 and AO.normalize_label(o.get("term"))
                 == AO.normalize_label(bad_prop[0].get("term"))]
        occ = [m["occurrence_id"]] + [o["occurrence_id"] for o in bad_prop + roles]
        out.append(_issue(
            "modifier_bearer_split", [uid], occ,
            "In %s the modifier %r and the event role it belongs to are attached "
            "to the literal kind constant %r rather than to one bound object, so "
            "nothing ties the modified thing to the participant."
            % (uid, m["label"], bad_prop[0].get("term")),
            {"unit": uid, "modifier": m["label"],
             "bearer_term": bad_prop[0].get("term"),
             "role_predicates": sorted(set(o.get("predicate") for o in roles))},
            "likely_mismatch"))
    return out


def free_rule_conclusion(table, stage1, stage2):
    """A rule concluding about a variable not bound over the rule."""
    import lc_reference
    out = []
    for uid, pkg in AO.packages(stage2):
        free = sorted(lc_reference.free_rule_conclusion_vars(pkg))
        if free:
            occ = [o["occurrence_id"] for o in table["stage2"]
                   if o["unit_id"] == uid and o["rule_side"] == "conclusion"
                   and o.get("term") in free]
            out.append(_issue(
                "free_rule_conclusion", [uid], occ or [uid + ":s2:"],
                "%s concludes about the unbound variable(s) %s, so the rule "
                "states its conclusion about every object." % (uid, ", ".join(free)),
                {"unit": uid, "free_variables": free}, "hard_error"))
    return out


def bound_class_corruption(table, stage1, stage2):
    """A bound variable occupies an isa class position: conversion must keep it
    a variable rather than turn it into a literal class."""
    out = []
    for o in table["stage2"]:
        if o["kind"] == "class" and o.get("label_is_variable"):
            out.append(_issue(
                "bound_class_corruption", [o["unit_id"]], [o["occurrence_id"]],
                "%s classifies an object by the bound variable %r, which stays "
                "meaningful only if conversion preserves it as a variable."
                % (o["unit_id"], o["label"]),
                {"unit": o["unit_id"], "class_variable": o["label"],
                 "path": o["json_path"]}, "diagnostic"))
    return out


def referenced_event_fold_risk(table, stage1, stage2, configuration="standard"):
    """An event whose identity another atom depends on, under a configuration
    whose folds can erase that identity."""
    out = []
    event_vars = {}
    for o in table["stage2"]:
        if o["kind"] == "event" or (o["kind"] == "class"
                                    and o["normalized_label"] == "activity"):
            t = o.get("term") if o["kind"] == "class" else o.get("term")
            if AO._is_var(t):
                event_vars.setdefault((o["unit_id"], t), []).append(o)
    for o in table["stage2"]:
        args = o.get("arguments_or_roles") or []
        if o.get("predicate") not in ("has content", "is rel2", "have", "="):
            continue
        for a in args:
            if AO._is_var(a) and (o["unit_id"], a) in event_vars:
                refs = event_vars[(o["unit_id"], a)]
                out.append(_issue(
                    "referenced_event_fold_risk", [o["unit_id"]],
                    [o["occurrence_id"]] + [r["occurrence_id"] for r in refs],
                    "%s uses the event %r as an argument of %s, so any fold that "
                    "drops the event's identity breaks that reference."
                    % (o["unit_id"], a, o.get("predicate")),
                    {"unit": o["unit_id"], "event_variable": a,
                     "referencing_predicate": o.get("predicate"),
                     "configuration": configuration},
                    "likely_mismatch" if configuration == "abstracted"
                    else "diagnostic"))
    return out


def _signature(o):
    """(normalized label, predicate family, label slot, arity, role/arg
    signature, polarity, rule side) — WP2.1."""
    args = o.get("arguments_or_roles") or []
    return {
        "normalized_label": o["normalized_label"],
        "predicate_family": o.get("predicate"),
        "label_slot": AO.LABEL_SLOT.get(o.get("predicate")),
        "arity": len(args),
        "argument_signature": ["var" if AO._is_var(a) else "const"
                               for a in args],
        "polarity": o["polarity"],
        "rule_side": o["rule_side"],
        "in_question": bool(o.get("in_question")),
    }


def question_no_supplier_signature(table, stage1, stage2):
    """A question occurrence whose (label, predicate family) never appears on
    the premise side."""
    out = []
    q = [o for o in table["stage2"] if o.get("in_question") and _meaning_bearing(o)]
    prem = [o for o in table["stage2"] if not o.get("in_question")]
    supplied = set((_depluralize(content_label(o)), o.get("predicate"))
                   for o in prem)
    fam = set(o.get("predicate") for o in prem)
    for o in q:
        key = (_depluralize(content_label(o)), o.get("predicate"))
        if key in supplied:
            continue
        same_label = any(same_word(content_label(p), content_label(o))
                         for p in prem)
        out.append(_issue(
            "question_no_supplier_signature", [o["unit_id"]], [o["occurrence_id"]],
            "The question asks for %r as %s, and no premise supplies that label "
            "in that predicate family%s."
            % (content_label(o), o.get("predicate"),
               "; the same label does occur in another family"
               if same_label else " or under any other family"),
            {"label": o["label"], "predicate": o.get("predicate"),
             "label_present_in_other_family": same_label,
             "premise_families": sorted(x for x in fam if x)},
            "likely_mismatch"))
    return out


def stage1_unrepresented(table, stage1, stage2):
    """Explicit Stage-1 content with no Stage-2 occurrence in its unit."""
    out = []
    unpaired = set(table["pairing"]["unpaired_stage1"])
    by_unit = {}
    for o in table["stage2"]:
        by_unit.setdefault(o["unit_id"], []).append(o)
    for o in table["stage1"]:
        if o["occurrence_id"] not in unpaired or o["kind"] == "event_role":
            continue
        n = o["normalized_label"]
        if not n:
            continue
        pool = by_unit.get(o["unit_id"], [])

        def represented(p):
            # tier 1 or 2: the same word, or a multiword Stage-2 label whose
            # head phrase is the Stage-1 label ("source" -> "source of").  A
            # merely shared head word (tier 3) is not enough.
            for cand in [p["normalized_label"], AO.normalize_label(p.get("term"))] \
                    + arg_labels(p):
                if same_word(n, cand):
                    return True
                if (similarity_tier(_depluralize(n), _depluralize(cand)) or 9) <= 2:
                    return True
            return False

        if any(represented(p) for p in pool):
            continue
        out.append(_issue(
            "stage1_unrepresented", [o["unit_id"]], [o["occurrence_id"]],
            "Stage 1 records the %s %r in %s, and no Stage-2 atom of that unit "
            "mentions it." % (o["kind"], o["label"], o["unit_id"]),
            {"unit": o["unit_id"], "kind": o["kind"], "label": o["label"]},
            "likely_mismatch"))
    return out


def stage2_unsourced(table, stage1, stage2):
    """A meaning-bearing Stage-2 label with no Stage-1 or source-text support."""
    out = []
    s1_labels = set()
    for o in table["stage1"]:
        s1_labels.add(_depluralize(o["normalized_label"]))
        s1_labels.add(_depluralize(AO.normalize_label(o.get("term"))))
    for o in table["stage2"]:
        if not _meaning_bearing(o) or o["kind"] == "rule_variable":
            continue
        n = content_label(o)
        if not n or _depluralize(n) in s1_labels:
            continue
        sentence = o.get("source_sentence") or ""
        if AO._spans(sentence, n) or AO._spans(sentence, _depluralize(n)):
            continue
        out.append(_issue(
            "stage2_unsourced", [o["unit_id"]], [o["occurrence_id"]],
            "Stage 2 introduces %r in %s (as %s), and neither Stage 1 nor "
            "the sentence text contains it." % (n, o["unit_id"], o.get("predicate")),
            {"unit": o["unit_id"], "label": n, "atom_label": o["label"],
             "predicate": o.get("predicate"), "path": o["json_path"]},
            "diagnostic"))
    return out


# ------------------------------------------------------------------ 10-13

def _head_words(n):
    return [w for w in re.split(r"[\s_]+", n) if w]


def similarity_tier(a, b):
    """1 same label; 2 one is the other's complete head phrase; 3 shared head
    word; 4 linked by the canonical or synonym table.  None otherwise."""
    if not a or not b:
        return None
    if a == b:
        return 1
    aw, bw = _head_words(a), _head_words(b)
    if aw and bw and (aw == bw[-len(aw):] or bw == aw[-len(bw):]):
        return 2
    if aw and bw and aw[-1] == bw[-1]:
        return 3
    try:
        import data_canonicals
        C = data_canonicals.CANONICALS
        if C.get(a) == b or C.get(b) == a or (
                a in C and b in C and C[a] == C[b]):
            return 4
    except Exception:
        pass
    try:
        import data_synonyms
        S = data_synonyms.SOFT_SYNONYMS
        for x, y in ((a, b), (b, a)):
            for cand in S.get(x.replace(" ", "_"), []):
                if cand[0] == y.replace(" ", "_"):
                    return 4
    except Exception:
        pass
    return None


_CONTEXT_DIMENSIONS = ("predicate_family", "label_slot", "arity",
                       "argument_signature", "polarity", "rule_side")

_DIMENSION_NAME = {"predicate_family": "predicate", "label_slot": "label slot",
                   "arity": "arity", "argument_signature": "argument shape",
                   "polarity": "polarity", "rule_side": "rule side"}


def _context_difference(x, y):
    """-> the dimensions on which two occurrences' contexts differ."""
    sx, sy = _signature(x), _signature(y)
    return [k for k in _CONTEXT_DIMENSIONS if sx[k] != sy[k]]


def _context_differs(x, y):
    return bool(_context_difference(x, y))


def _describe(o, dims):
    """How one occurrence looks on the dimensions that differ."""
    sig = _signature(o)
    parts = []
    for d in dims:
        v = sig[d]
        parts.append(",".join(v) if isinstance(v, list) else str(v))
    return " ".join(parts) or o.get("predicate") or "?"


def label_context_hints(table, stage1, stage2, cap=12):
    """Kinds 10 and 11: same or similar label in a different logical context."""
    occs = [o for o in table["stage2"] if _meaning_bearing(o)]
    ranked = []
    for i, x in enumerate(occs):
        for y in occs[i + 1:]:
            tier = similarity_tier(content_label(x), content_label(y))
            if tier is None or not _context_differs(x, y):
                continue
            ranked.append((tier, x, y))
    ranked.sort(key=lambda t: (t[0], t[1]["occurrence_id"], t[2]["occurrence_id"]))
    out, dropped = [], max(0, len(ranked) - cap)
    for tier, x, y in ranked[:cap]:
        diffs = _context_difference(x, y)
        kind = ("same_label_different_context" if tier == 1
                else "similar_label_different_context")
        out.append(_issue(
            kind, [x["unit_id"], y["unit_id"]],
            [x["occurrence_id"], y["occurrence_id"]],
            "%r in %s and %r in %s are %s but differ in %s (%s vs %s)." % (
                x["label"], x["unit_id"], y["label"], y["unit_id"],
                "the same label" if tier == 1 else "related labels (tier %d)" % tier,
                " and ".join(_DIMENSION_NAME[d] for d in diffs),
                _describe(x, diffs), _describe(y, diffs)),
            {"tier": tier, "differs_on": diffs,
             "left": _signature(x), "right": _signature(y)},
            "diagnostic"))
    return out, dropped


def rule_premise_load(table, stage1, stage2):
    """Kind 12: a rule with two or more meaning-bearing antecedents, each
    recorded separately so a later probe can vary one at a time."""
    out = []
    by_unit = {}
    for o in table["stage2"]:
        if o["rule_side"] == "antecedent" and _meaning_bearing(o):
            by_unit.setdefault(o["unit_id"], []).append(o)
    for uid, occs in sorted(by_unit.items()):
        if len(occs) < 2:
            continue
        out.append(_issue(
            "rule_premise_load", [uid], [o["occurrence_id"] for o in occs],
            "%s has %d meaning-bearing premises, so a failure to fire may come "
            "from any one of them." % (uid, len(occs)),
            {"unit": uid,
             "premises": [{"occurrence_id": o["occurrence_id"],
                           "predicate": o.get("predicate"),
                           "label": o["label"], "path": o["json_path"]}
                          for o in occs]},
            "diagnostic"))
    return out


def question_component_load(table, stage1, stage2):
    """Kind 13: a question with two or more meaning-bearing conjuncts, with the
    premise-side occurrences that could supply each."""
    out = []
    q = [o for o in table["stage2"] if o.get("in_question") and _meaning_bearing(o)]
    if len(q) < 2:
        return out
    prem = [o for o in table["stage2"] if not o.get("in_question")]
    comps = []
    for o in q:
        sup = [p["occurrence_id"] for p in prem
               if same_word(content_label(p), content_label(o))
               and p.get("predicate") == o.get("predicate")]
        comps.append({"occurrence_id": o["occurrence_id"],
                      "predicate": o.get("predicate"), "label": o["label"],
                      "possible_suppliers": sorted(sup)})
    units = sorted(set(o["unit_id"] for o in q))
    out.append(_issue(
        "question_component_load", units, [o["occurrence_id"] for o in q],
        "The question has %d meaning-bearing components; %d of them have no "
        "premise-side occurrence with the same label and predicate."
        % (len(comps), sum(1 for c in comps if not c["possible_suppliers"])),
        {"components": comps}, "diagnostic"))
    return out


# ------------------------------------------------------------------ WP2.2

def probe_descriptions(issues):
    """Descriptions of the one-component variants a later GK probe may run.

    Data only.  Nothing here removes a premise or a question component from the
    accepted logic, and no probe description mentions an expected answer.
    """
    out = []
    for iss in issues:
        if iss["kind"] == "rule_premise_load":
            prem = iss["evidence"]["premises"]
            for p in prem:
                out.append({
                    "probe_kind": "omit_one_premise",
                    "unit_id": iss["evidence"]["unit"],
                    "omitted_occurrence_id": p["occurrence_id"],
                    "omitted_path": p["path"],
                    "description": "Variant of %s without the premise %s(%s)."
                                   % (iss["evidence"]["unit"], p["predicate"],
                                      p["label"]),
                    "status": "described only; not applied to any logic"})
        elif iss["kind"] == "question_component_load":
            comps = iss["evidence"]["components"]
            for c in comps:
                out.append({
                    "probe_kind": "question_component_alone",
                    "component_occurrence_id": c["occurrence_id"],
                    "description": "Question restricted to the component %s(%s)."
                                   % (c["predicate"], c["label"]),
                    "status": "described only; not applied to any logic"})
            if len(comps) > 2:
                out.append({
                    "probe_kind": "question_all_but_one",
                    "components": [c["occurrence_id"] for c in comps],
                    "description": "All-but-one combinations over %d question "
                                   "components." % len(comps),
                    "status": "described only; not applied to any logic"})
    return out


# ------------------------------------------------------------------ driver

DETECTORS = [
    ("entity_split", entity_split),
    ("dependent_reference_split", dependent_reference_split),
    ("modifier_bearer_split", modifier_bearer_split),
    ("free_rule_conclusion", free_rule_conclusion),
    ("bound_class_corruption", bound_class_corruption),
    ("question_no_supplier_signature", question_no_supplier_signature),
    ("stage1_unrepresented", stage1_unrepresented),
    ("stage2_unsourced", stage2_unsourced),
    ("rule_premise_load", rule_premise_load),
    ("question_component_load", question_component_load),
]


def detect(stage1, stage2, configuration="standard", hint_cap=12):
    """-> {"table", "issues", "probes", "hints_dropped"}."""
    table = AO.extract(stage1, stage2)
    issues = []
    for name, fn in DETECTORS:
        issues.extend(fn(table, stage1, stage2))
    issues.extend(referenced_event_fold_risk(table, stage1, stage2, configuration))
    hints, dropped = label_context_hints(table, stage1, stage2, hint_cap)
    issues.extend(hints)
    issues.sort(key=lambda i: (SEVERITIES.index(i["severity"]), i["kind"],
                               i["issue_id"]))
    return {"table": table, "issues": issues,
            "probes": probe_descriptions(issues),
            "hints_dropped": dropped}
