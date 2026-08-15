"""Converter-aware signed candidates, roles and priority cost (v3, WP1-WP3).

The v2 display had three defects that this module exists to remove:

  * it compared a Stage-2 predicate spelling with a clause predicate spelling,
    so `has degree property(spicy, ...)` was reported as `count unavailable`
    although the converted concept `has property(spicy, ...)` occurs several
    times.  Here every candidate is CONVERTED by the real converter and matched
    as a clause literal, so there is no such message at all;
  * it told the model that an atom was a "question component" with N
    "resolution partners", which says nothing about whether the atom can be
    supplied or must be produced.  Here every candidate carries the rule
    position it can occupy — PREMISE, CONSEQUENCE or BOTH — derived from the
    signs the converted literal actually has in the clauses gk received;
  * it showed one number that mixed duplicated generic axioms with source
    literals.  Here one PRIORITY COST is computed from DISTINCT partner shapes,
    halved (rounded up) when the atom is question-linked.

The role derivation is the clausification fact:

    the theory contains  +p  ->  p is available as a premise
                                 NOT p is a place that needs a consequence
    the theory contains  -p  ->  NOT p is available as a premise
                                 p is a place that needs a consequence

A bridge `p -> q` compiles to `-p | q | $block`: its negative body literal
consumes an available positive `p`, and its positive head meets an existing
negative `q`.

Nothing here calls an LLM or a prover, and nothing reads a reviewed rule or an
accepted answer.
"""

import copy
import json
import math

import bridge_world as BW
import unifier_abstraction as UA

VERSION = "unifier_candidates_v3/1.0"

MAIN_CAP = 80
SECONDARY_CAP = 24

PREMISE, CONSEQUENCE, BOTH = "PREMISE", "CONSEQUENCE", "BOTH"

UNIQUE, EMPTY, AMBIGUOUS = "unique", "empty", "ambiguous"

SKOLEM_NOTE = """SKOLEM CONSTANTS

A name beginning with `sk`, such as `sk0`, is a fresh constant standing for an
arbitrary unknown object introduced while translating the question. The same
name always denotes the same unknown object. A rule containing it is local to
that object; replace it by a variable only when the implication is genuinely
general."""


class CandidateError(Exception):
    """The candidate layer cannot proceed.  Never worked around."""


def is_skolem(term):
    """A constant the question's translation invented, e.g. `sk0`, `sk0_farm`."""
    if not isinstance(term, str):
        return False
    t = term[2:] if term.startswith("#:") else term
    return t.startswith("sk") and not t.startswith("skol")


def has_skolem(atom):
    def go(t):
        if isinstance(t, str):
            return is_skolem(t)
        if isinstance(t, list):
            return any(go(x) for x in t[1:])
        return False
    return any(go(a) for a in atom[1:])


# ------------------------------------------------------- isolated conversion

SET_BINDERS = ("$setof",)


def free_variables(term_or_atom):
    """Stage-2 variables that are FREE, in first-appearance order.

    A variable declared by a set binder — `["$setof", V, ID, BODY]` — is local
    to that term.  Collecting it as a free rule variable is how a set
    expression's bound variable would end up universally quantified at the
    outer level, which is a different formula about different things.
    """
    out = []

    def go(t, bound):
        if isinstance(t, str):
            if UA.is_variable_term(t) and t not in bound and t not in out:
                out.append(t)
            return
        if not isinstance(t, list) or not t:
            return
        if isinstance(t[0], str) and t[0] in SET_BINDERS and len(t) >= 3:
            local = set(bound)
            if isinstance(t[1], str) and UA.is_variable_term(t[1]):
                local.add(t[1])
            for x in t[2:]:
                go(x, local)
            return
        for x in t[1:]:
            go(x, bound)
    go(term_or_atom, set())
    return out


def bound_variables(atom):
    """The variables a set binder declares inside this atom."""
    out = []

    def go(t):
        if not isinstance(t, list) or not t:
            return
        if isinstance(t[0], str) and t[0] in SET_BINDERS and len(t) >= 3:
            if isinstance(t[1], str) and UA.is_variable_term(t[1]) \
                    and t[1] not in out:
                out.append(t[1])
        for x in t[1:]:
            go(x)
    go(atom)
    return out


def _packages(atoms_with_signs):
    """-> [(package id, holds package)] for a batch of signed atoms.

    The atom's free variables are universally quantified.  Without the
    quantifier the converter treats a bare `X` as a CONSTANT, and the resulting
    literal then fails to unify with the clause literals that carry a real
    variable — which silently gave a candidate the wrong role.
    """
    out = []
    for i, (atom, sign) in enumerate(atoms_with_signs, start=1):
        body = ["not", copy.deepcopy(atom)] if sign == "-" \
            else copy.deepcopy(atom)
        for v in reversed(free_variables(atom)):
            body = ["forall", v, body]
        out.append(("Cv%d" % i, ["holds", "W0", body]))
    return out


def _convert_once(view, specs, configuration):
    edited = copy.deepcopy(view["stage2"])
    if not (isinstance(edited, list) and edited and edited[0] == "and"):
        raise CandidateError("stage2 is not an [\"and\", ...] list")
    for pid, pkg in specs:
        edited.append(["@id", pid, pkg])
    clauses, _fixes = BW._convert(edited, view["stage1"],
                                  BW.bridge_options(configuration))
    collapse = not BW._base_uses_ctxt_terms(view.get("final_clauses"))
    out, counter = {}, [0]
    for pid, _pkg in specs:
        mine = [c for c in clauses
                if str(c.get("@name") or "") == "sent_%s" % pid
                or str(c.get("@name") or "").startswith("sent_%s_" % pid)]
        mine = [c for c in mine if c.get("@sourcetype") != "populate"]
        if collapse and mine:
            mine = BW._share_ctxt(mine, counter)
        out[pid] = mine
    return out


def convert_batch(view, atoms_with_signs, configuration, errors=None):
    """Convert every signed atom in ONE isolated conversion.

    Each atom is spliced in as its own `@id` package and only that package's
    own clauses are kept, so the atoms cannot contaminate each other's result.
    The option scope is `bridge_world.bridge_options`, which is the case's own
    configuration with the two passes that destroy a bridge turned off — the
    same scope a rule built from these atoms will be compiled under, so a
    candidate's GK form predicts what a rule using it will produce.

    A batch that raises is SPLIT and retried, down to single atoms, so one atom
    the converter refuses cannot silently remove the rest of the list.  The
    atoms that raise on their own are recorded in `errors`, never dropped
    quietly.
    """
    specs = _packages(atoms_with_signs)
    errors = errors if errors is not None else []

    def run(chunk):
        if not chunk:
            return {}
        try:
            return _convert_once(view, chunk, configuration)
        except Exception as e:                                  # noqa: BLE001
            if len(chunk) == 1:
                pid, pkg = chunk[0]
                errors.append({"package_id": pid, "package": pkg,
                               "error": "%s: %s" % (type(e).__name__, e)})
                return {pid: []}
            half = len(chunk) // 2
            out = run(chunk[:half])
            out.update(run(chunk[half:]))
            return out
    return run(specs)


def _content_literals(clauses):
    """Every non-control literal of these clauses, flattened."""
    out = []
    for c in clauses:
        for lit in UA.literals_of(c.get("@logic")):
            if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
                continue
            if UA.is_control_predicate(lit[0]):
                continue
            out.append(lit)
    return out


def conversion_of(clauses):
    """-> (status, [converted content literals]).

    `unique` when exactly one distinct content literal shape came back;
    `empty` when none did; `ambiguous` when the atom converts to several
    different content literals, which no single candidate can stand for.
    """
    lits = _content_literals(clauses)
    seen, distinct = set(), []
    for lit in lits:
        key = UA.alpha_key(lit)
        if key in seen:
            continue
        seen.add(key)
        distinct.append(lit)
    if not distinct:
        return EMPTY, []
    if len(distinct) > 1:
        return AMBIGUOUS, distinct
    return UNIQUE, distinct


# ------------------------------------------------------------- base matching

def _is_generic(literal):
    """A generic axiom shape: every argument is a variable."""
    args = list(literal[1:])
    if not args:
        return True
    return all(UA.is_variable_term(a) for a in args)


def role_occurrences(occurrences):
    """The literals a role may be derived from.

    Two kinds of literal are excluded, for the same reason: they are properties
    of the ENCODING rather than of the passage, and both signs of them exist for
    everything, so counting them makes every candidate `BOTH` and every cost
    identical.

      * a population clause — `isa(animal, $some_animal)` and its negative twin
        — is a witness the converter emits for every class so the theory is not
        vacuous;
      * a generic frame axiom whose arguments are ALL variables — the
        `is rel2(?V,?A,?O,?C)` pair that ties any relation to its event — makes
        every relation look both suppliable and needed.

    Both stay in the record and are matched separately; neither confers a role.
    """
    return [o for o in occurrences
            if not o["is_control"] and o["source_kind"] != UA.GENERATED
            and not _is_generic(UA.unsigned_atom(o["clause_literal"]))]


def distinct_partner_shapes(occurrence, pool):
    """How many DIFFERENT literal shapes this occurrence can resolve with.

    Computed over `pool`, so a population witness neither counts as a partner
    nor gets counted; one axiom copied five times is one shape, not five.
    """
    shapes = set()
    for other in pool:
        if other is occurrence:
            continue
        if UA.are_resolution_partners(occurrence["clause_literal"],
                                      other["clause_literal"]):
            shapes.add(UA.alpha_key(other["clause_literal"]))
    return len(shapes)


def match_occurrences(literal, occurrences):
    """-> ({same-sign}, {opposite-sign}, {population-only matches}).

    Ordinary unification against the literals gk actually received, with every
    argument the clause has.  Sign is read off the converted literal itself.
    """
    sign = UA.sign_of(literal)
    atom = UA.unsigned_atom(literal)
    same, opposite, population = [], [], []
    for o in occurrences:
        if o["is_control"]:
            continue
        if not UA.unify_unsigned_atoms(
                atom, UA.unsigned_atom(o["clause_literal"]))["unifiable"]:
            continue
        if o["source_kind"] == UA.GENERATED or _is_generic(
                UA.unsigned_atom(o["clause_literal"])):
            population.append(o)
        else:
            (same if o["sign_symbol"] == sign else opposite).append(o)
    return same, opposite, population


def role_of(same, opposite):
    """PREMISE / CONSEQUENCE / BOTH, or None when the atom has no role."""
    if same and opposite:
        return BOTH
    if same:
        return PREMISE
    if opposite:
        return CONSEQUENCE
    return None


def priority_cost(matches, question_linked, pool):
    """-> (base cost, question adjustment, final cost).

    The base cost is the minimum number of DISTINCT alpha-normalised partner
    shapes over the occurrences the candidate maps to: one axiom copied five
    times is one way to resolve, not five.  A question-linked candidate is
    halved, rounded up, so the atoms the question turns on come first.
    """
    counts = [distinct_partner_shapes(o, pool) for o in matches]
    base = min(counts) if counts else 0
    if question_linked:
        return base, "halved and rounded up because it is question-linked", \
            (base + 1) // 2
    return base, None, base


# ---------------------------------------------------------------- rendering

def printed_atom(atom, sign):
    return UA.print_atom(UA.display_atom(atom), negated=sign == "-")


def _same_shape(surface, gk_literal):
    """Is the converted form materially the same line as the surface atom?"""
    a = UA.display_atom(surface)
    b = UA.display_atom(UA.unsigned_atom(gk_literal))
    return json.dumps(a) == json.dumps(b)


def render_candidate(row):
    lines = ["  %-4s %s" % (row["id"], row["printed"])]
    lines.append("       USE: %s" % row["role"])
    lines.append("       PRIORITY COST: %d" % row["priority_cost"])
    if row.get("show_gk_form"):
        lines.append("       GK FORM: %s" % row["gk_form_printed"])
    return "\n".join(lines)


def render_body(main, secondary):
    """The dynamic block appended to the frozen instruction text."""
    parts = []
    if any(has_skolem(r["surface_atom"]) for r in list(main) + list(secondary)):
        parts.append(SKOLEM_NOTE)
    parts.append("MAIN CANDIDATES\n\n%s"
                 % "\n\n".join(render_candidate(r) for r in main))
    if secondary:
        parts.append("SECONDARY CANDIDATES\n\n%s"
                     % "\n\n".join(render_candidate(r) for r in secondary))
    return "\n\n".join(parts)


# ------------------------------------------------------------ the main list

def stage2_signed_atoms(view):
    """Every distinct Stage-2 content atom, in both signs, with its provenance.

    Both signs are built for every atom: the sign a candidate is USEFUL in is a
    fact about the clauses, not about how the sentence happened to be written,
    and `role_of` decides which of the two survives.
    """
    rows, order = {}, []
    for row in UA.stage2_atoms(view):
        atom = row["atom"]
        if UA.is_control_predicate(atom[0]) or UA.is_equality_predicate(
                atom[0]):
            continue
        key = UA.alpha_key(atom)
        if key not in rows:
            rows[key] = {"atom": atom, "units": [], "occurrence_ids": [],
                         "in_question": False, "rule_sides": []}
            order.append(key)
        r = rows[key]
        if row["unit"] not in r["units"]:
            r["units"].append(row["unit"])
        r["occurrence_ids"].append(row["occurrence_id"])
        r["in_question"] = r["in_question"] or row["in_question"]
        if row["rule_side"] not in r["rule_sides"]:
            r["rule_sides"].append(row["rule_side"])
    return [rows[k] for k in order]


def _candidate_record(surface, sign, gk_literal, same, opposite, status,
                      converted, origin, pool, population=(), extra=None):
    role = role_of(same, opposite)
    matches = same + opposite
    question_linked = any(o["source_kind"] == UA.QUESTION for o in matches)
    base, adjust, cost = priority_cost(matches, question_linked, pool)
    rec = {
        "surface_atom": surface,
        "sign": sign,
        "printed": printed_atom(surface, sign),
        "conversion_status": status,
        "converted_literals": converted,
        "gk_form": gk_literal,
        "gk_form_printed": (UA.print_atom(
            UA.display_atom(UA.unsigned_atom(gk_literal)),
            negated=UA.sign_of(gk_literal) == "-") if gk_literal else None),
        "show_gk_form": bool(gk_literal) and not _same_shape(surface,
                                                             gk_literal),
        "matched_same_sign": [o["literal_id"] for o in same],
        "matched_opposite_sign": [o["literal_id"] for o in opposite],
        "matched_source_kinds": sorted(set(o["source_kind"]
                                           for o in matches)),
        "matched_encoding_only": [o["literal_id"] for o in population],
        "role": role,
        "question_linked": question_linked,
        "raw_distinct_partner_count": base,
        "question_adjustment": adjust,
        "priority_cost": cost,
        "origin": origin,
    }
    rec.update(extra or {})
    return rec


def build_main(view, configuration, inventory, cap=MAIN_CAP):
    """-> (shown, omitted, diagnostics).  The converter-mapped Stage-2 list."""
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
            clauses = converted.get(pid) or []
            status, lits = conversion_of(clauses)
            if status != UNIQUE:
                diagnostics.append({
                    "surface_atom": row["atom"], "sign": sign,
                    "printed": printed_atom(row["atom"], sign),
                    "conversion_status": status,
                    "converted_literals": lits,
                    "why_it_is_not_scored":
                        "isolated conversion produced no content literal"
                        if status == EMPTY else
                        "isolated conversion produced several different "
                        "content literals, so one candidate cannot stand for "
                        "it"})
                continue
            lit = lits[0]
            same, opposite, population = match_occurrences(
                lit, inventory["occurrences"])
            rec = _candidate_record(
                row["atom"], sign, lit, same, opposite, status, lits,
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
                    "matched_encoding_only": rec["matched_encoding_only"],
                    "why_it_is_not_scored":
                        "its converted form occurs in no clause of either "
                        "sign, apart from population witnesses and generic "
                        "frame axioms, so it can be neither supplied nor "
                        "needed"})
                continue
            rows.append(rec)
    rows.sort(key=_rank)
    for i, r in enumerate(rows[:cap], start=1):
        r["id"] = "M%d" % i
    return rows[:cap], rows[cap:], diagnostics


def _rank(row):
    return (row["priority_cost"],
            0 if row["role"] in (CONSEQUENCE, BOTH) else 1,
            json.dumps(UA.display_atom(row["surface_atom"])), row["sign"])


# ------------------------------------------------------- the secondary list

def _strip_entity(term):
    if isinstance(term, str) and term.startswith("#:"):
        return term[2:]
    if isinstance(term, list) and term:
        return [term[0]] + [_strip_entity(x) for x in term[1:]]
    return term


def surface_guesses(literal):
    """Candidate SURFACE forms for a clause literal, most likely first.

    A clause literal carries what the converter added: an entity marker on a
    constant, and a trailing context argument.  Undoing those is a guess, so
    every guess is verified by converting it again and checking that it returns
    to this literal; an unverified guess is dropped, never displayed.
    """
    atom = UA.unsigned_atom(literal)
    args = list(atom[1:])
    out = []
    for drop in (1, 0, 2):
        if drop and len(args) - drop < 1:
            continue
        trimmed = args[:len(args) - drop] if drop else list(args)
        out.append([atom[0]] + [_strip_entity(a) for a in trimmed])
    seen, uniq = set(), []
    for a in out:
        k = json.dumps(a)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(a)
    return uniq


def _all_variables(literal):
    def go(t):
        if isinstance(t, str):
            return [t] if UA.is_variable_term(t) else []
        if isinstance(t, list):
            return [v for x in t[1:] for v in go(x)]
        return []
    return [v for a in literal[1:] for v in go(a)]


def _to_display_variables(atom):
    """Clause variables (`?:X`) become Stage-2 variables (`V1`, `V2`, ...)."""
    names = {}

    def go(t):
        if isinstance(t, str) and UA.is_variable_term(t):
            names.setdefault(t, "V%d" % (len(names) + 1))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def build_secondary(view, configuration, inventory, main, cap=SECONDARY_CAP):
    """-> (shown, omitted).  Final-clause content the main list does not carry.

    Source-linked clauses first, then axioms.  Population and generated
    clauses, control literals, equality and generic all-variable axiom shapes
    are excluded by name.
    """
    pool = role_occurrences(inventory["occurrences"])
    taken = set()
    for r in main:
        taken.add(UA.alpha_key(UA.unsigned_atom(r["gk_form"])))
    order = {UA.SOURCE: 0, UA.QUESTION: 1, UA.AXIOM: 2, UA.GENERATED: 9}
    pool, omitted = [], []
    seen = set()
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
        key = UA.alpha_key(UA.unsigned_atom(lit))
        if key in taken:
            continue
        if key in seen:
            continue
        seen.add(key)
        if _is_generic(lit):
            omitted.append({"literal_id": o["literal_id"],
                            "printed": UA.print_atom(UA.display_atom(
                                UA.unsigned_atom(lit))),
                            "why": "a generic axiom shape: every argument is a "
                                   "variable"})
            continue
        pool.append(o)
    if not pool:
        return [], omitted
    # verify every proposed surface form by converting it again
    tries, index = [], []
    for o in pool[:cap * 3]:
        for guess in surface_guesses(o["clause_literal"]):
            surface = _to_display_variables(guess)
            if any(isinstance(a, list) for a in surface[1:]):
                # a clause-side nested term (`$ev_of`, a raw `$setof`) is not a
                # Stage-2 surface shape; the Stage-2 ones are already in MAIN
                omitted.append({"literal_id": o["literal_id"],
                                "printed": UA.print_atom(UA.display_atom(
                                    UA.unsigned_atom(o["clause_literal"]))),
                                "why": "its surface form would carry a nested "
                                       "clause-side term, which is not a "
                                       "Stage-2 shape"})
                continue
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
        if status != UNIQUE:
            continue
        got = lits[0]
        want = UA.unsigned_atom(o["clause_literal"])
        if not UA.unify_unsigned_atoms(UA.unsigned_atom(got),
                                       want)["unifiable"]:
            continue
        used.add(o["literal_id"])
        sign = o["sign_symbol"]
        signed = got if sign == "+" else ["-" + UA.bare_predicate(got[0])] \
            + list(got[1:])
        same, opposite, population = match_occurrences(
            signed, inventory["occurrences"])
        rec = _candidate_record(surface, sign, signed, same, opposite, status,
                                lits, "final_clause", pool, population,
                                {"from_literal_id": o["literal_id"],
                                 "from_clause": o["clause_name"],
                                 "from_source_kind": o["source_kind"]})
        if rec["role"] is None:
            continue
        rows.append(rec)
    for o in pool:
        if o["literal_id"] not in used:
            omitted.append({"literal_id": o["literal_id"],
                            "printed": UA.print_atom(UA.display_atom(
                                UA.unsigned_atom(o["clause_literal"]))),
                            "why": "no surface form of it converted back to "
                                   "this literal, or the secondary cap was "
                                   "reached"})
    rows.sort(key=_rank)
    for i, r in enumerate(rows, start=1):
        r["id"] = "S%d" % i
    return rows, omitted


# ------------------------------------------------------------------ the view

def build(view, configuration, main_cap=MAIN_CAP, secondary_cap=SECONDARY_CAP):
    """Everything WP1-WP3 asks for, in one record."""
    inventory = UA.inventory(view)
    main, main_omitted, diagnostics = build_main(view, configuration,
                                                 inventory, cap=main_cap)
    secondary, secondary_omitted = build_secondary(view, configuration,
                                                   inventory, main,
                                                   cap=secondary_cap)
    body = render_body(main, secondary)
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
                   "mapping_diagnostics": len(diagnostics)},
        "policy": "every candidate is converted by the real converter and "
                  "matched as a clause literal; a candidate whose conversion "
                  "is empty or ambiguous, or whose converted form occurs in no "
                  "clause of either sign, is recorded as a diagnostic and not "
                  "scored or displayed.",
    }


def by_id(built):
    return dict((r["id"], r) for r in built["main"] + built["secondary"])
