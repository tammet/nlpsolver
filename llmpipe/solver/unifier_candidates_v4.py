"""Candidates v4: expose what v3 hid, and order honestly (WP2, WP4).

Three changes, each answering a measured v3 defect.

**An ambiguous conversion is split, not discarded.**  v3 kept a Stage-2 atom
only when its isolated conversion produced exactly one content literal.  When it
produced several, the atom vanished into diagnostics — which is how `eb-0006`'s
decisive `is rel2(increase, X, eventprop($target, communication))` never reached
the prompt.  Here every distinct converted literal becomes its own candidate,
carrying the shared surface atom, its variant index, and the fact that a rule
written with that surface atom compiles to all of them.

**A nested term is no longer refused for being nested.**  v3's secondary builder
skipped any clause-derived form containing `eventprop` or `$setof`, calling it
"not a Stage-2 shape".  The manual probes proved otherwise: those exact forms
compile through the real bridge boundary and gk cites them.  The test here is
the only honest one — convert the proposed surface form again and require the
intended clause literal back.  Nothing is invented: a constant, label, functor
or argument position that does not survive the round trip is not displayed.

**The priority number means one thing.**  v3's cost was the minimum
partner-shape count over matching occurrences, halved for question links, which
gave large blocks of unrelated candidates an unexplained zero.  Here it is the
number of DISTINCT opposite-sign literal shapes the exact converted literal
unifies with — the ways the theory could actually meet it — and question-clause
candidates are ordered first as a separate group instead of by arithmetic.
"""

import collections
import json

import alignment_occurrences as AO
import unifier_abstraction as UA
import unifier_candidates_v3 as CV3

VERSION = "unifier_candidates_v4/1.0"

MAIN_CAP = 80
SECONDARY_CAP = 24

PREMISE, CONSEQUENCE, BOTH = CV3.PREMISE, CV3.CONSEQUENCE, CV3.BOTH
UNIQUE, EMPTY, AMBIGUOUS = CV3.UNIQUE, CV3.EMPTY, CV3.AMBIGUOUS

SKOLEM_NOTE = CV3.SKOLEM_NOTE

# Predicates that structure a clause rather than assert content.  A rule may not
# be written about them, so they never become writable vocabulary.
STRUCTURAL_PREDICATES = frozenset(AO.LOGICAL_HEADS)

free_variables = CV3.free_variables
bound_variables = CV3.bound_variables
convert_batch = CV3.convert_batch
conversion_of = CV3.conversion_of
role_of = CV3.role_of
match_occurrences = CV3.match_occurrences
role_occurrences = CV3.role_occurrences
has_skolem = CV3.has_skolem
is_skolem = CV3.is_skolem
stage2_signed_atoms = CV3.stage2_signed_atoms
printed_atom = CV3.printed_atom
surface_guesses = CV3.surface_guesses


class CandidateError(CV3.CandidateError):
    pass


# ------------------------------------------------------------------ priority

def opposite_sign_unifiers(literal, pool):
    """How many DISTINCT opposite-sign literal shapes this one can meet.

    Over the valid pool only — population witnesses and generic all-variable
    frame axioms are properties of the encoding, not of the passage, and both
    signs of them exist for everything.  One axiom copied five times is one
    shape.
    """
    sign = UA.sign_of(literal)
    atom = UA.unsigned_atom(literal)
    shapes = set()
    for o in pool:
        if o["sign_symbol"] == sign:
            continue
        if UA.unify_unsigned_atoms(
                atom, UA.unsigned_atom(o["clause_literal"]))["unifiable"]:
            shapes.add(UA.alpha_key(o["clause_literal"]))
    return len(shapes)


def _rank(row):
    """Question-clause content first, then fewest opposite-sign unifiers."""
    return (0 if row["question_linked"] else 1,
            row["priority_cost"],
            0 if row["role"] in (CONSEQUENCE, BOTH) else 1,
            json.dumps(UA.display_atom(row["surface_atom"])),
            row["sign"], row.get("converted_variant_index") or 0)


# ---------------------------------------------------------------- rendering

def render_candidate(row):
    lines = ["  %-4s %s" % (row["id"], row["printed"])]
    lines.append("       USE: %s" % row["role"])
    lines.append("       PRIORITY COST: %d" % row["priority_cost"])
    if row.get("show_gk_form"):
        lines.append("       GK FORM: %s" % row["gk_form_printed"])
    if (row.get("converted_variant_count") or 1) > 1:
        lines.append("       NOTE: this atom also converts to %d other clause "
                     "form(s); a rule using it produces all of them"
                     % (row["converted_variant_count"] - 1))
    return "\n".join(lines)


def render_body(main, secondary):
    parts = []
    if any(has_skolem(r["surface_atom"]) for r in list(main) + list(secondary)):
        parts.append(SKOLEM_NOTE)
    parts.append("MAIN CANDIDATES\n\n%s"
                 % "\n\n".join(render_candidate(r) for r in main))
    if secondary:
        parts.append("SECONDARY CANDIDATES\n\n%s"
                     % "\n\n".join(render_candidate(r) for r in secondary))
    return "\n\n".join(parts)


# ------------------------------------------------------------------ records

def _record(surface, sign, gk_literal, same, opposite, status, all_literals,
            variant_index, origin, pool, population=(), extra=None):
    role = role_of(same, opposite)
    matches = same + opposite
    question_linked = any(o["source_kind"] == UA.QUESTION for o in matches)
    cost = opposite_sign_unifiers(gk_literal, pool) if gk_literal else 0
    rec = {
        "surface_atom": surface,
        "sign": sign,
        "printed": printed_atom(surface, sign),
        "conversion_status": status,
        "converted_variant_index": variant_index,
        "converted_variant_count": len(all_literals),
        "all_converted_literals": all_literals,
        "one_surface_atom_compiles_to_several_clauses": len(all_literals) > 1,
        "gk_form": gk_literal,
        "gk_form_printed": (UA.print_atom(
            UA.display_atom(UA.unsigned_atom(gk_literal)),
            negated=UA.sign_of(gk_literal) == "-") if gk_literal else None),
        "show_gk_form": bool(gk_literal) and not CV3._same_shape(surface,
                                                                 gk_literal),
        "matched_same_sign": [o["literal_id"] for o in same],
        "matched_opposite_sign": [o["literal_id"] for o in opposite],
        "matched_encoding_only": [o["literal_id"] for o in population],
        "matched_valid_occurrences": len(matches),
        "no_valid_source_occurrence": not matches,
        "matched_source_kinds": sorted(set(o["source_kind"] for o in matches)),
        "same_sign_source_kinds": sorted(set(o["source_kind"] for o in same)),
        "opposite_sign_source_kinds": sorted(set(o["source_kind"]
                                                 for o in opposite)),
        "role": role,
        "question_linked": question_linked,
        "priority_cost": cost,
        "priority_basis": "distinct opposite-sign literal shapes the converted "
                          "literal unifies with, over source, question and "
                          "non-generic axiom clauses",
        "question_ordering": "question-clause candidates are a separate, "
                             "earlier group; the number is not adjusted",
        "origin": origin,
    }
    rec.update(extra or {})
    return rec


# ------------------------------------------------------------ the main list

def build_main(view, configuration, inventory, cap=MAIN_CAP):
    """-> (shown, omitted, diagnostics).  One candidate per converted literal."""
    pool = role_occurrences(inventory["occurrences"])
    atoms = stage2_signed_atoms(view)
    batch = []
    for row in atoms:
        batch.append((row["atom"], "+"))
        batch.append((row["atom"], "-"))
    errors = []
    converted = convert_batch(view, batch, configuration,
                              errors=errors) if batch else {}
    rows, diagnostics = [], []
    for e in errors:
        diagnostics.append({"package_id": e["package_id"],
                            "conversion_status": "converter_error",
                            "error": e["error"][:200],
                            "why_it_is_not_scored":
                                "the converter raised on this atom in "
                                "isolation"})
    for i, row in enumerate(atoms):
        for j, sign in enumerate(("+", "-")):
            pid = "Cv%d" % (2 * i + j + 1)
            status, lits = conversion_of(converted.get(pid) or [])
            if status == EMPTY:
                diagnostics.append({
                    "surface_atom": row["atom"], "sign": sign,
                    "printed": printed_atom(row["atom"], sign),
                    "conversion_status": status,
                    "why_it_is_not_scored":
                        "isolated conversion produced no content literal"})
                continue
            for k, lit in enumerate(lits):
                same, opposite, population = match_occurrences(
                    lit, inventory["occurrences"])
                rec = _record(
                    row["atom"], sign, lit, same, opposite, status, lits, k,
                    "stage2", pool, population,
                    {"units": row["units"],
                     "occurrence_ids": row["occurrence_ids"],
                     "stage2_in_question": row["in_question"],
                     "stage2_rule_sides": row["rule_sides"]})
                if rec["role"] is None:
                    diagnostics.append({
                        "surface_atom": row["atom"], "sign": sign,
                        "printed": rec["printed"],
                        "conversion_status": status,
                        "converted_variant_index": k,
                        "gk_form": lit,
                        "matched_encoding_only": rec["matched_encoding_only"],
                        "why_it_is_not_scored":
                            "this converted form occurs in no clause of either "
                            "sign, apart from population witnesses and generic "
                            "frame axioms, so it can be neither supplied nor "
                            "needed"})
                    continue
                rows.append(rec)
    rows.sort(key=_rank)
    kept = rows[:cap]
    _assign_ids(kept, "M")
    return kept, rows[cap:], diagnostics


def _assign_ids(rows, prefix):
    by_surface = collections.defaultdict(list)
    for i, r in enumerate(rows, start=1):
        r["id"] = "%s%d" % (prefix, i)
        by_surface[(json.dumps(r["surface_atom"]), r["sign"])].append(r["id"])
    for r in rows:
        siblings = by_surface[(json.dumps(r["surface_atom"]), r["sign"])]
        r["shares_surface_atom_with"] = [x for x in siblings if x != r["id"]]
    return rows


# ------------------------------------------------------- the secondary list

def build_secondary(view, configuration, inventory, main, cap=SECONDARY_CAP):
    """-> (shown, omitted).  Final-clause content the main list does not carry.

    A nested clause-side term is NOT excluded here: `eventprop` and `$setof`
    forms are exactly what v3 lost, and the round trip is what keeps them
    honest.  A guess whose conversion does not return the literal it came from
    is dropped with its reason.
    """
    pool = role_occurrences(inventory["occurrences"])
    taken = set()
    for r in main:
        for lit in r.get("all_converted_literals") or []:
            taken.add(UA.alpha_key(UA.unsigned_atom(lit)))
    order = {UA.SOURCE: 0, UA.QUESTION: 1, UA.AXIOM: 2, UA.GENERATED: 9}
    candidates, omitted, seen = [], [], set()
    for o in sorted(inventory["occurrences"],
                    key=lambda x: (order.get(x["source_kind"], 5),
                                   x["clause_index"], x["literal_index"])):
        lit = o["clause_literal"]
        if o["is_control"]:
            continue
        if o["is_equality"]:
            omitted.append({"literal_id": o["literal_id"],
                            "why": "equality is not part of this experiment"})
            continue
        if o["source_kind"] == UA.GENERATED:
            omitted.append({"literal_id": o["literal_id"],
                            "why": "a generated population clause"})
            continue
        if str(o["predicate"]) in STRUCTURAL_PREDICATES:
            # `kb holds` scopes a knowledge base; it is structure, not content,
            # and a rule may not be written about it
            omitted.append({"literal_id": o["literal_id"],
                            "printed": UA.print_atom(UA.display_atom(
                                UA.unsigned_atom(lit))),
                            "why": "a structural predicate (`%s`), not content"
                                   % o["predicate"]})
            continue
        key = UA.alpha_key(UA.unsigned_atom(lit))
        if key in taken or key in seen:
            continue
        seen.add(key)
        if CV3._is_generic(UA.unsigned_atom(lit)):
            omitted.append({"literal_id": o["literal_id"],
                            "printed": UA.print_atom(UA.display_atom(
                                UA.unsigned_atom(lit))),
                            "why": "a generic axiom shape: every argument is a "
                                   "variable"})
            continue
        candidates.append(o)
    if not candidates:
        return [], omitted
    tries, index = [], []
    for o in candidates[:cap * 4]:
        for guess in surface_guesses(o["clause_literal"]):
            surface = CV3._to_display_variables(guess)
            tries.append((surface, "+"))
            index.append((o, surface))
    errors = []
    converted = convert_batch(view, tries, configuration,
                              errors=errors) if tries else {}
    for e in errors:
        omitted.append({"package_id": e["package_id"],
                        "why": "the converter refused this surface form: %s"
                               % e["error"][:160]})
    rows, used = [], set()
    for k, (o, surface) in enumerate(index, start=1):
        if len(rows) >= cap:
            break
        if o["literal_id"] in used:
            continue
        status, lits = conversion_of(converted.get("Cv%d" % k) or [])
        if status == EMPTY:
            continue
        want = UA.unsigned_atom(o["clause_literal"])
        back = [l for l in lits
                if UA.unify_unsigned_atoms(UA.unsigned_atom(l),
                                           want)["unifiable"]]
        if not back:
            continue
        used.add(o["literal_id"])
        sign = o["sign_symbol"]
        for variant, got in enumerate(back):
            signed = got if sign == "+" else \
                ["-" + UA.bare_predicate(got[0])] + list(got[1:])
            same, opposite, population = match_occurrences(
                signed, inventory["occurrences"])
            rec = _record(surface, sign, signed, same, opposite, status, lits,
                          lits.index(got), "final_clause", pool, population,
                          {"from_literal_id": o["literal_id"],
                           "from_clause": o["clause_name"],
                           "from_source_kind": o["source_kind"],
                           "round_trip": {
                               "surface": surface,
                               "converted": lits,
                               "matched_the_clause_literal": want}})
            if rec["role"] is None:
                continue
            rows.append(rec)
    for o in candidates:
        if o["literal_id"] not in used:
            omitted.append({"literal_id": o["literal_id"],
                            "printed": UA.print_atom(UA.display_atom(
                                UA.unsigned_atom(o["clause_literal"]))),
                            "why": "no surface form of it converted back to "
                                   "this literal, or the secondary cap was "
                                   "reached"})
    rows.sort(key=_rank)
    _assign_ids(rows, "S")
    return rows, omitted


# ------------------------------------------------------------------ the view

def build(view, configuration, main_cap=MAIN_CAP, secondary_cap=SECONDARY_CAP):
    inventory = UA.inventory(view)
    main, main_omitted, diagnostics = build_main(view, configuration,
                                                 inventory, cap=main_cap)
    secondary, secondary_omitted = build_secondary(view, configuration,
                                                   inventory, main,
                                                   cap=secondary_cap)
    body = render_body(main, secondary)
    split = sum(1 for r in main + secondary
                if r["one_surface_atom_compiles_to_several_clauses"])
    nested = sum(1 for r in main + secondary
                 if any(isinstance(a, list) for a in r["surface_atom"][1:]))
    return {
        "version": VERSION,
        "inventory_counts": inventory["counts"],
        "occurrences": inventory["occurrences"],
        "main": main,
        "main_omitted": [{"printed": r["printed"], "role": r["role"],
                          "priority_cost": r["priority_cost"]}
                         for r in main_omitted],
        "secondary": secondary,
        "secondary_omitted": secondary_omitted,
        "mapping_diagnostics": diagnostics,
        "skolem_note_shown": any(has_skolem(r["surface_atom"])
                                 for r in main + secondary),
        "body": body,
        "counts": {"main": len(main), "main_omitted": len(main_omitted),
                   "secondary": len(secondary),
                   "secondary_omitted": len(secondary_omitted),
                   "mapping_diagnostics": len(diagnostics),
                   "candidates_from_a_multi_output_conversion": split,
                   "candidates_with_a_nested_term": nested},
        "policy": "every candidate is converted by the real converter and "
                  "matched as a clause literal; an atom whose conversion has "
                  "several outputs contributes one candidate per output, and a "
                  "nested term is kept when the round trip returns the clause "
                  "literal it came from. A candidate whose converted form "
                  "occurs in no clause of either sign is a recorded "
                  "diagnostic, not a displayed line.",
    }


def by_id(built):
    return dict((r["id"], r) for r in built["main"] + built["secondary"])
