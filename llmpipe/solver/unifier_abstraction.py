"""Signed clause literals, ordinary unification, and the compact LLM view.

WP1-WP3 of `memos/PLAN_2026_08_11_unifier_driven_abstraction_pilot_opus5.md`.

The pilot's whole input to the abstraction model is a short ordered list of
signed atoms.  Producing it takes three things this module keeps apart:

  1. **The clause layer.**  Every literal of the stored final clauses, with its
     sign read off the predicate name, and — for each one — how many
     opposite-sign literals it could actually resolve with under ordinary
     first-order unification.  This is a fact about the theory gk received, and
     it is computed with every argument the clause has, context slots included.

  2. **The semantic layer.**  The atom templates recovered from the case's
     Stage-2 occurrences, which retain the intended sign of a fact, a rule
     premise, a rule conclusion or a question component.  A clause literal that
     conversion or a generic axiom introduced counts toward partner numbers but
     is not shown as if the passage had said it.

  3. **The mapping between them**, which is allowed to fail.  Conversion renames
     predicates (`belong to` becomes `have` under the abstracted preset) and
     appends context arguments.  Where a template cannot be matched to any
     clause literal the count is reported `unavailable` and a diagnostic is
     recorded; a converted predicate is never guessed.

Nothing here calls an LLM or a prover, and nothing reads a reviewed or accepted
answer.

Two deliberate exclusions.  A literal whose base predicate begins `$` is a
control literal (`$defq`, `$ans`, `$block`, `$ctxt`, `$ev_of`) and never enters
the abstraction inventory; a `$` inside an ARGUMENT does not make the content
predicate a control predicate.  Equality is kept out of the displayed list and
reported separately: this pilot does not invite invented equality rules.
"""

import json
import re

import alignment_occurrences as AO

VERSION = "unifier_abstraction/1.0"

# A final-clause variable.  The stored clauses write `?:X`; a freshened variant
# keeps the prefix (`?:Cu3`, `?:Vre`).  Nothing else in a stored clause starts
# with `?`, so this is the whole convention.
CLAUSE_VAR = re.compile(r"^\?")
UNIT = re.compile(r"^sent_(S\d+)")

QUESTION, SOURCE, AXIOM, GENERATED = "question", "source", "axiom", "generated"

# What the display calls a variable, in first-appearance order.
DISPLAY_VARS = ["?X", "?Y", "?Z", "?U", "?V", "?W", "?P", "?Q", "?R", "?S"]

MAX_TEMPLATES = 80


class UnificationError(Exception):
    """A term shape this layer refuses to interpret."""


# ---------------------------------------------------------------- conventions

def is_clause_variable(term):
    return isinstance(term, str) and bool(CLAUSE_VAR.match(term))


def is_stage2_variable(term):
    """Stage-2 writes a bound variable as a bare capitalised name."""
    return AO._is_var(term)


def is_variable_term(term):
    """Either convention: a Stage-2 name, a clause `?:X`, or a display `?X`.

    The template layer is handed atoms from Stage 2 and, in a fixture or a
    round-trip, atoms already in display form.  A function that recognised only
    one of them would silently treat a variable as a constant and close a
    position that is open.
    """
    return is_stage2_variable(term) or is_clause_variable(term)


def bare_predicate(pred):
    """`-p` is the negation of `p`.  The `-` is removed exactly once."""
    if isinstance(pred, str) and pred.startswith("-"):
        return pred[1:]
    return pred


def sign_of(literal):
    p = literal[0] if isinstance(literal, list) and literal else None
    return "-" if isinstance(p, str) and p.startswith("-") else "+"


def opposite(sign):
    return "-" if sign == "+" else "+"


def is_control_predicate(pred):
    """True for a control literal: the BASE predicate begins with `$`."""
    return str(bare_predicate(pred)).startswith("$")


def is_equality_predicate(pred):
    return str(bare_predicate(pred)) in ("=", "!=")


def unsigned_atom(literal):
    """The literal without its sign: `["-isa","a","?:X"]` -> `["isa","a","?:X"]`."""
    return [bare_predicate(literal[0])] + list(literal[1:])


def literals_of(payload):
    """A clause payload is one literal or a list of them."""
    if not isinstance(payload, list) or not payload:
        return []
    return [payload] if isinstance(payload[0], str) else list(payload)


# ---------------------------------------------------------------- unification
#
# Ordinary first-order unification with an occurs check.  Variables of the two
# literals are standardised apart first, so two clauses that both print `?:X`
# do not accidentally share it.  Constants match only themselves: nothing is
# lower-cased, `#` is not stripped from an entity name, and argument order is
# significant.

_LEFT, _RIGHT = "?<L>", "?<R>"


def _tag(term, prefix):
    if isinstance(term, str):
        return prefix + term if is_clause_variable(term) else term
    if isinstance(term, list) and term:
        return [term[0]] + [_tag(x, prefix) for x in term[1:]]
    return term


def _is_var(term):
    return isinstance(term, str) and (term.startswith(_LEFT)
                                      or term.startswith(_RIGHT))


def _walk(term, sub):
    seen = 0
    while _is_var(term) and term in sub:
        term = sub[term]
        seen += 1
        if seen > 10000:                                  # pragma: no cover
            raise UnificationError("cyclic substitution")
    return term


def _occurs(var, term, sub):
    term = _walk(term, sub)
    if term == var:
        return True
    if isinstance(term, list):
        return any(_occurs(var, x, sub) for x in term[1:])
    return False


def _unify(a, b, sub):
    a, b = _walk(a, sub), _walk(b, sub)
    if a == b:
        return True, None
    if _is_var(a):
        if _occurs(a, b, sub):
            return False, "occurs check: %s occurs in %s" % (_untag(a),
                                                             _show(b))
        sub[a] = b
        return True, None
    if _is_var(b):
        if _occurs(b, a, sub):
            return False, "occurs check: %s occurs in %s" % (_untag(b),
                                                             _show(a))
        sub[b] = a
        return True, None
    if isinstance(a, str) or isinstance(b, str):
        return False, "different constants: %s and %s" % (_show(a), _show(b))
    if not (isinstance(a, list) and isinstance(b, list)):
        return False, "unsupported term shape"
    if a[0] != b[0]:
        return False, "different functors: %s and %s" % (a[0], b[0])
    if len(a) != len(b):
        return False, "different arities: %d and %d" % (len(a) - 1, len(b) - 1)
    for x, y in zip(a[1:], b[1:]):
        ok, why = _unify(x, y, sub)
        if not ok:
            return False, why
    return True, None


def _untag(term):
    if isinstance(term, str):
        if term.startswith(_LEFT):
            return term[len(_LEFT):]
        if term.startswith(_RIGHT):
            return term[len(_RIGHT):] + "'"
        return term
    if isinstance(term, list) and term:
        return [term[0]] + [_untag(x) for x in term[1:]]
    return term


def _show(term):
    t = _untag(term)
    return t if isinstance(t, str) else json.dumps(t)


def _resolve(term, sub):
    term = _walk(term, sub)
    if isinstance(term, list):
        return [term[0]] + [_resolve(x, sub) for x in term[1:]]
    return term


def unify_unsigned_atoms(a, b):
    """-> {unifiable, substitution_left, substitution_right, reason}.

    `a` and `b` are atoms WITHOUT their signs.  Their variables are standardised
    apart before unification, so the caller may pass two literals that both use
    `?:X`.  A binding of the right literal's variable is printed with a trailing
    `'` so the two sides stay distinguishable in the record.
    """
    if not (isinstance(a, list) and a and isinstance(b, list) and b):
        return {"unifiable": False, "substitution_left": {},
                "substitution_right": {}, "reason": "not an atom"}
    if bare_predicate(a[0]) != bare_predicate(b[0]):
        return {"unifiable": False, "substitution_left": {},
                "substitution_right": {},
                "reason": "different predicates: %s and %s"
                          % (bare_predicate(a[0]), bare_predicate(b[0]))}
    if len(a) != len(b):
        return {"unifiable": False, "substitution_left": {},
                "substitution_right": {},
                "reason": "different arities: %d and %d" % (len(a) - 1,
                                                            len(b) - 1)}
    la, lb = _tag(unsigned_atom(a), _LEFT), _tag(unsigned_atom(b), _RIGHT)
    sub = {}
    ok, why = _unify(la, lb, sub)
    if not ok:
        return {"unifiable": False, "substitution_left": {},
                "substitution_right": {}, "reason": why}
    left, right = {}, {}
    for var in sub:
        value = _show(_resolve(var, sub))
        if var.startswith(_LEFT):
            left[_untag(var)] = value
        else:
            right[_untag(var)[:-1]] = value
    return {"unifiable": True, "substitution_left": left,
            "substitution_right": right, "reason": None}


def are_resolution_partners(a, b):
    """Opposite signs, same unsigned predicate, same arity, and unifiable."""
    if not (isinstance(a, list) and a and isinstance(b, list) and b):
        return False
    if sign_of(a) == sign_of(b):
        return False
    if bare_predicate(a[0]) != bare_predicate(b[0]):
        return False
    if len(a) != len(b):
        return False
    return unify_unsigned_atoms(a, b)["unifiable"]


def alpha_key(literal):
    """The literal up to variable renaming: sign, predicate, argument shape."""
    names = {}

    def go(t):
        if is_variable_term(t):
            names.setdefault(t, "_v%d" % len(names))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return json.dumps([literal[0]] + [go(a) for a in literal[1:]])


# ------------------------------------------------------- the clause inventory

def _source_kind(clause):
    if clause.get("@sourcetype") == "question" or "@question" in clause:
        return QUESTION
    if clause.get("@sourcetype") == "populate":
        return GENERATED
    if UNIT.match(str(clause.get("@name") or "")):
        return SOURCE
    return AXIOM


def clause_literals(view):
    """Every literal occurrence of the stored final clauses.

    Control literals are recorded and flagged, not silently dropped: their
    presence is why a clause is there, and the count of what was excluded is
    part of the record.
    """
    out = []
    for ci, clause in enumerate(view.get("final_clauses") or []):
        if not isinstance(clause, dict):
            continue
        payload = clause.get("@question") if "@question" in clause \
            else clause.get("@logic")
        for li, lit in enumerate(literals_of(payload)):
            if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
                continue
            pred = bare_predicate(lit[0])
            out.append({
                "literal_id": "C%d.%d" % (ci, li),
                "clause_name": clause.get("@name"),
                "clause_index": ci,
                "literal_index": li,
                "sign": "negative" if sign_of(lit) == "-" else "positive",
                "sign_symbol": sign_of(lit),
                "predicate": pred,
                "arguments": list(lit[1:]),
                "clause_literal": lit,
                "source_kind": _source_kind(clause),
                "is_control": is_control_predicate(lit[0]),
                "is_equality": is_equality_predicate(lit[0]),
                "in_question_clause": _source_kind(clause) == QUESTION,
            })
    return out


def annotate_partners(occurrences):
    """Fill `resolution_partner_count` and `distinct_partner_shape_count`.

    Counted over LITERAL OCCURRENCES, so one axiom copied five times shows as
    five partners; the distinct alpha-normalised shape count is recorded beside
    it so that a repeated axiom does not look like five different ways to
    resolve.  The occurrence count is what orders the display; the shape count
    is a diagnostic and a tie-breaker.
    """
    content = [o for o in occurrences if not o["is_control"]]
    for o in content:
        partners, shapes = [], set()
        for other in content:
            if other is o:
                continue
            if are_resolution_partners(o["clause_literal"],
                                       other["clause_literal"]):
                partners.append(other["literal_id"])
                shapes.add(alpha_key(other["clause_literal"]))
        o["resolution_partner_count"] = len(partners)
        o["distinct_partner_shape_count"] = len(shapes)
        o["resolution_partners"] = partners[:12]
    for o in occurrences:
        if o["is_control"]:
            o["resolution_partner_count"] = None
            o["distinct_partner_shape_count"] = None
            o["resolution_partners"] = []
    return occurrences


def inventory(view):
    """The complete clause-literal layer, with counts and what it excluded."""
    occs = annotate_partners(clause_literals(view))
    content = [o for o in occs if not o["is_control"]]
    return {
        "version": VERSION,
        "occurrences": occs,
        "content_occurrences": content,
        "counts": {
            "literals": len(occs),
            "content_literals": len(content),
            "control_literals": sum(1 for o in occs if o["is_control"]),
            "equality_literals": sum(1 for o in content if o["is_equality"]),
            "by_source_kind": _tally(o["source_kind"] for o in content),
        },
        "control_predicates_excluded": sorted(set(
            o["predicate"] for o in occs if o["is_control"])),
        "policy": "a literal whose BASE predicate begins `$` is a control "
                  "literal and is excluded from the abstraction inventory; a "
                  "`$` inside an argument does not make the content predicate a "
                  "control predicate. Equality is counted but never displayed.",
    }


def _tally(items):
    out = {}
    for x in items:
        out[x] = out.get(x, 0) + 1
    return out


# ---------------------------------------------------- Stage-2 atom templates

def _to_clause_shape(atom, prefix="?:T"):
    """A Stage-2 atom with its bound variables written the clause's way.

    Only the variable spelling changes.  Predicates, labels, constants and
    argument order are untouched, and no argument is added or removed.
    """
    names = {}

    def go(t):
        if is_variable_term(t):
            names.setdefault(t, "%s%d" % (prefix, len(names) + 1))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def display_atom(atom):
    """The atom as the model sees it: variables renamed `?X`, `?Y`, ... ."""
    names = {}

    def go(t):
        if is_variable_term(t):
            if t not in names:
                i = len(names)
                names[t] = DISPLAY_VARS[i] if i < len(DISPLAY_VARS) \
                    else "?V%d" % (i + 1)
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def print_atom(atom, negated=False):
    body = json.dumps(atom, ensure_ascii=False)
    return ("NOT " + body) if negated else body


def _norm_constant(term):
    """The converter's two mechanical rewritings of a constant, undone.

    Stage 2 writes an entity id `Emily 4`; the clause writes `#:Emily 4`, and a
    class word may reach the clause lower-cased (`Dried Thai chili` becomes
    `dried thai chili`).  Both are deterministic markings of the SAME constant,
    and undoing them is not guessing a converted predicate: the predicate, the
    arity and the argument order still have to match exactly.

    Used ONLY when matching a Stage-2 template to a clause literal.  The raw
    clause-to-clause unifier never does this — there, constants match only
    themselves.
    """
    t = term[2:] if term.startswith("#:") else term
    return t.lower()


def _relax(atom):
    def go(t):
        if isinstance(t, str):
            return t if is_variable_term(t) else _norm_constant(t)
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [str(bare_predicate(atom[0])).lower()] + [go(a) for a in atom[1:]]


def prefix_unifies(template_atom, clause_atom, relaxed=False):
    """Does this Stage-2-shaped atom match that clause literal's atom?

    Conversion appends generated arguments — a context slot — to the right of
    the arguments the passage supplied.  So a template matches a clause literal
    when the predicates are equal and the template's arguments unify with the
    clause literal's LEADING arguments.  Nothing is deleted from the clause
    side: the extra arguments simply have nothing opposite them, and the raw
    clause-to-clause unification above never uses this relation.

    With `relaxed`, the two constant markings above are undone first.
    """
    if not (isinstance(template_atom, list) and template_atom
            and isinstance(clause_atom, list) and clause_atom):
        return False
    if len(clause_atom) < len(template_atom):
        return False
    a, b = template_atom, [clause_atom[0]] + list(
        clause_atom[1:len(template_atom)])
    if relaxed:
        a, b = _relax(a), _relax(b)
    if bare_predicate(a[0]) != bare_predicate(b[0]):
        return False
    return unify_unsigned_atoms(a, b)["unifiable"]


def stage2_atoms(view):
    """-> [{atom, sign, unit, rule_side, in_question, occurrence_id}].

    From `alignment_occurrences`, which is the tested reading of a Stage-2
    package and the only place the SEMANTIC sign of an atom is recorded: a rule
    premise is not a negative assertion because clausification negated it.
    """
    out = []
    for occ in AO.extract_stage2(view.get("stage2"), view.get("stage1")):
        if occ["kind"] == "rule_variable":
            continue
        args = occ.get("arguments_or_roles")
        if not isinstance(args, list) or not occ.get("predicate"):
            continue
        atom = [occ["predicate"]] + list(args)
        out.append({"atom": atom, "sign": AO.literal_sign(occ),
                    "unit": occ.get("unit_id"), "rule_side": occ.get("rule_side"),
                    "in_question": bool(occ.get("in_question")),
                    "occurrence_id": occ.get("occurrence_id"),
                    "kind": occ.get("kind")})
    return out


def template_counts(atom, sign, occurrences):
    """-> {count, matched, partners, by_source_kind, unavailable_because}.

    The count is the number of clause-literal occurrences of the OPPOSITE sign
    whose atom this template matches.  It is `None` — `count unavailable` in the
    display — when the template matches no clause literal of either sign at all,
    which is what happens when conversion renamed the predicate.

    `by_source_kind` is a diagnostic, not part of the ordering: a generic frame
    axiom with a variable in every slot is a genuine resolution partner for
    every relation, and a reader of the record should be able to see how much of
    a count comes from there rather than from the passage.
    """
    shaped = _to_clause_shape(atom)
    matched, partners, kinds, exact = [], [], {}, 0
    for o in occurrences:
        if o["is_control"]:
            continue
        atom_of = unsigned_atom(o["clause_literal"])
        if not prefix_unifies(shaped, atom_of, relaxed=True):
            continue
        matched.append(o["literal_id"])
        if prefix_unifies(shaped, atom_of):
            exact += 1
        if o["sign_symbol"] == opposite(sign):
            partners.append(o["literal_id"])
            kinds[o["source_kind"]] = kinds.get(o["source_kind"], 0) + 1
    if not matched:
        return {"count": None, "matched": [], "partners": [],
                "by_source_kind": {}, "matched_exactly": 0,
                "unavailable_because": "no clause literal has this predicate "
                                       "with these arguments; conversion may "
                                       "have renamed it"}
    return {"count": len(partners), "matched": matched, "partners": partners,
            "by_source_kind": kinds, "matched_exactly": exact,
            "matched_only_up_to_the_entity_marker_and_letter_case":
                len(matched) - exact,
            "unavailable_because": None}


# ---------------------------------------------------- WP2: question components

def question_components(view, occurrences):
    """The signed content atoms of the stored Stage-2 question package.

    Question priority is about the CONCEPTS the question uses.  `$defq0`, `$ans`
    and their defining equivalence clauses are control literals and never
    appear here; a compound question contributes one entry per content atom,
    and an atom's complement is a resolution opportunity, not "the false
    question".
    """
    rows, seen = [], set()
    for row in stage2_atoms(view):
        if not row["in_question"]:
            continue
        atom = row["atom"]
        if is_control_predicate(atom[0]):
            continue
        key = (row["sign"], alpha_key(atom))
        if key in seen:
            continue
        seen.add(key)
        got = template_counts(atom, row["sign"], occurrences)
        rows.append({
            "atom": atom, "sign": row["sign"],
            "unit": row["unit"], "rule_side": row["rule_side"],
            "occurrence_id": row["occurrence_id"],
            "is_question_component": True,
            "partner_count": got["count"],
            "partners_by_source_kind": got["by_source_kind"],
            "matched_clause_literals": got["matched"],
            "mapping_unavailable_because": got["unavailable_because"],
        })
    return rows


def complements(components, occurrences):
    """The opposite-sign form of each question component, as its own entry."""
    out = []
    for c in components:
        sign = opposite(c["sign"])
        got = template_counts(c["atom"], sign, occurrences)
        out.append(dict(c, sign=sign, is_question_component=False,
                        is_complement_of_a_question_component=True,
                        partner_count=got["count"],
                        partners_by_source_kind=got["by_source_kind"],
                        matched_clause_literals=got["matched"],
                        mapping_unavailable_because=got[
                            "unavailable_because"]))
    return out


# ------------------------------------------------------ WP3: the ordered view

def _template_key(row):
    return (row["sign"], alpha_key(row["atom"]))


def build_templates(view, occurrences):
    """Every distinct signed Stage-2 template, merged up to variable renaming."""
    merged = {}
    for row in stage2_atoms(view):
        atom = row["atom"]
        if is_control_predicate(atom[0]) or is_equality_predicate(atom[0]):
            continue
        key = (row["sign"], alpha_key(atom))
        if key in merged:
            merged[key]["occurrence_ids"].append(row["occurrence_id"])
            if row["unit"] not in merged[key]["units"]:
                merged[key]["units"].append(row["unit"])
            merged[key]["in_question"] = merged[key]["in_question"] \
                or row["in_question"]
            continue
        got = template_counts(atom, row["sign"], occurrences)
        merged[key] = {"atom": atom, "sign": row["sign"],
                       "units": [row["unit"]],
                       "occurrence_ids": [row["occurrence_id"]],
                       "in_question": row["in_question"],
                       "rule_side": row["rule_side"],
                       "partner_count": got["count"],
                       "partners_by_source_kind": got["by_source_kind"],
                       "matched_clause_literals": got["matched"],
                       "mapping_unavailable_because": got[
                           "unavailable_because"]}
    return list(merged.values())


def order_templates(view, occurrences, cap=MAX_TEMPLATES):
    """Question components first, then the scarcest partners upward.

    Every question component and every displayed complement is mandatory: the
    cap can only remove ordinary templates, and each removal is recorded with
    its count.

    The cap is a PER-CALL cap.  `ranked` is the complete ordering and nothing is
    deleted from it; `shown` is the block one call fits, and a later round shows
    the next block.  Display ids run once over the whole ordering, so `L37`
    means the same template in every round it appears in.
    """
    components = question_components(view, occurrences)
    comps = complements(components, occurrences)
    mandatory = []
    for i, c in enumerate(components, start=1):
        mandatory.append(dict(c, display_id="Q%d" % i,
                              display_note="QUESTION COMPONENT"))
    for i, c in enumerate(comps, start=1):
        mandatory.append(dict(c, display_id="Q%dc" % i,
                              display_note="OPPOSITE SIGN OF QUESTION "
                                           "COMPONENT"))
    taken = set(_template_key(m) for m in mandatory)
    rest = [t for t in build_templates(view, occurrences)
            if _template_key(t) not in taken]

    def rank(t):
        c = t["partner_count"]
        return (1 if c is None else 0, c if c is not None else 0,
                json.dumps(display_atom(t["atom"])))
    rest.sort(key=rank)
    for i, t in enumerate(rest, start=1):
        t["display_id"] = "L%d" % i
        t["display_note"] = None
    room = max(1, cap - len(mandatory))
    shown, omitted = rest[:room], rest[room:]
    return {
        "mandatory": mandatory,
        "ranked": rest,
        "shown": shown,
        "per_call_room": room,
        "omitted": [{"display_id": t["display_id"],
                     "atom": display_atom(t["atom"]), "sign": t["sign"],
                     "partner_count": t["partner_count"]} for t in omitted],
        "cap": cap,
        "counted_literals_without_a_stage2_template":
            _unmapped_clause_literals(occurrences, mandatory + rest),
        "policy": "all question components and their complements are shown in "
                  "every call; the remaining slots of a call go to the "
                  "templates with the fewest opposite-sign partners first. The "
                  "cap is per call: what one call omits is listed by id, and a "
                  "later round shows the next block.",
    }


def vocabulary_for(display, block, entity_ids=()):
    """The vocabulary of ONE call: its question components and its own block."""
    return displayed_vocabulary({"mandatory": display["ordered"]["mandatory"],
                                 "shown": list(block)}, entity_ids)


def _unmapped_clause_literals(occurrences, templates):
    """How many counted clause literals no displayed template stands for."""
    shapes = [_to_clause_shape(t["atom"]) for t in templates]
    n, preds = 0, {}
    for o in occurrences:
        if o["is_control"]:
            continue
        atom = unsigned_atom(o["clause_literal"])
        if any(prefix_unifies(s, atom, relaxed=True) for s in shapes):
            continue
        n += 1
        preds[o["predicate"]] = preds.get(o["predicate"], 0) + 1
    return {"count": n, "by_predicate": preds,
            "note": "these affect partner counts but are not shown as concepts "
                    "the passage expressed: conversion or a generic axiom "
                    "introduced them"}


def render_line(row):
    atom = display_atom(row["atom"])
    text = print_atom(atom, negated=row["sign"] == "-")
    count = row["partner_count"]
    note = row.get("display_note")
    tail = ("existing resolution partners: %d" % count if count is not None
            else "count unavailable (this predicate does not occur in the "
                 "converted theory)")
    head = "  %-5s %s" % (row["display_id"], text)
    return "%s\n        %s" % (head, ("%s; %s" % (note, tail)) if note
                               else tail)


def render_block(ordered):
    return "\n".join(render_line(r) for r in
                     ordered["mandatory"] + ordered["shown"])


# --------------------------------------------------- the displayed vocabulary

_ENTITY_SHAPE = re.compile(r"^(#:|https?://)|\s\d+$")


def stage1_entity_ids(stage1):
    """The entity ids Stage 1 declared, normalised.  The authoritative list."""
    out = set()
    for occ in AO.extract_stage1(stage1 or []):
        if occ["kind"] == "entity" and isinstance(occ.get("label"), str):
            out.add(occ["label"])
    return out


def looks_like_a_named_entity(term, entity_ids=()):
    """A particular thing, as opposed to a kind word or a relation name.

    Stage 1's own entity list decides it where there is one; the shapes are the
    fallback for a constant conversion produced — `#:Tom 1`, a canonical URL, or
    an id ending in an entity number.
    """
    if not isinstance(term, str):
        return False
    if term in entity_ids:
        return True
    return bool(_ENTITY_SHAPE.search(term))


def position_key(pred, args, index):
    """The identity of one argument position, for the generalisation rule.

    Keyed by the CONTENT LABEL as well as the predicate where there is one:
    under the `is rel2` encoding the relation name lives in an argument, so a
    key of `is rel2/3/2` would pool `part of`, `in` and `lives with` into one
    position and lose exactly the distinction the rule is about.
    """
    slot = AO.LABEL_SLOT.get(pred)
    label = None
    if slot is not None and slot < len(args) and isinstance(args[slot], str) \
            and not is_variable_term(args[slot]):
        label = args[slot]
    return "%s%s/%d/%d" % (pred, "" if label is None else "|" + label,
                           len(args), index)


def displayed_vocabulary(ordered, entity_ids=()):
    """Exactly what the model was shown, for the rule validator.

    A rule may only use a predicate, a content label or a constant that appeared
    in the display, at an arity that appeared for it.  Two positions are closed
    to generalisation: the content-label slot of a predicate (`isa`'s class,
    `is rel2`'s relation name), which the display never shows as a variable and
    which is not a term of the theory; and an argument position where the
    display only ever held a NAMED ENTITY, where a variable would silently turn
    a claim about one thing into a claim about everything.  An ordinary kind
    word in a term position stays generalisable.
    """
    preds, constants, arities = {}, set(), {}
    label_slots, const_only, entity_only = {}, {}, {}
    variable_seen, seen_entities = {}, set()
    for row in ordered["mandatory"] + ordered["shown"]:
        atom = row["atom"]
        pred = str(atom[0])
        args = list(atom[1:])
        preds.setdefault(pred, set()).add(len(args))
        arities.setdefault(pred, set()).add(len(args))
        slot = AO.LABEL_SLOT.get(pred)
        if slot is not None and slot < len(args):
            label_slots.setdefault(pred, set()).add(slot)
        for i, a in enumerate(args):
            key = position_key(pred, args, i)
            if is_variable_term(a):
                variable_seen[key] = True
                continue
            if isinstance(a, str):
                constants.add(a)
                const_only.setdefault(key, set()).add(a)
                if looks_like_a_named_entity(a, entity_ids):
                    seen_entities.add(a)
                    entity_only.setdefault(key, set()).add(a)
                else:
                    entity_only.setdefault(key, set())
    for key in list(const_only):
        if variable_seen.get(key):
            const_only.pop(key)
    closed = {}
    for key, values in entity_only.items():
        if variable_seen.get(key) or not values:
            continue
        if key in const_only and values == const_only[key]:
            closed[key] = values
    labels = {}
    for row in ordered["mandatory"] + ordered["shown"]:
        atom = row["atom"]
        pred = str(atom[0])
        slot = AO.LABEL_SLOT.get(pred)
        args = list(atom[1:])
        if slot is not None and slot < len(args) \
                and not is_variable_term(args[slot]):
            labels.setdefault(pred, set()).add(str(args[slot]))
    return {
        "predicates": dict((p, sorted(v)) for p, v in preds.items()),
        "arities": dict((p, sorted(v)) for p, v in arities.items()),
        "constants": sorted(constants),
        "named_entities": sorted(seen_entities),
        "label_slots": dict((p, sorted(v)) for p, v in label_slots.items()),
        "labels_per_predicate": dict((p, sorted(v))
                                     for p, v in labels.items()),
        "positions_never_shown_as_a_variable":
            dict((k, sorted(v)) for k, v in const_only.items()),
        "named_entity_only_positions":
            dict((k, sorted(v)) for k, v in closed.items()),
    }


def build_display(view, cap=MAX_TEMPLATES):
    """The complete WP1-WP3 view of one case: inventory, order, vocabulary.

    `vocabulary` is the FIRST call's — what a single-round arm may use.  A
    later round has its own, from `vocabulary_for`.
    """
    inv = inventory(view)
    ordered = order_templates(view, inv["occurrences"], cap=cap)
    entities = stage1_entity_ids(view.get("stage1"))
    vocab = displayed_vocabulary(ordered, entities)
    return {"version": VERSION, "inventory": inv, "ordered": ordered,
            "vocabulary": vocab, "block": render_block(ordered),
            "entity_ids": sorted(entities),
            "question_components": len([r for r in ordered["mandatory"]
                                        if r.get("is_question_component")]),
            "templates_ranked": len(ordered["ranked"]),
            "templates_shown": len(ordered["mandatory"])
            + len(ordered["shown"]),
            "templates_omitted": len(ordered["omitted"])}


# ------------------------------------------------------------- Stage-1 compact

def compact_stage1(stage1, cap_units=None):
    """A deterministic compact rendering of the REAL Stage-1 analysis.

    Not a summary written by a model: unit id, text and type, entity ids and
    types, action roots with their role fillers, and adjectives with their
    bearers, with empty fields omitted.  Retry logs, token counts and parser
    statistics are not part of the analysis and are left out.
    """
    lines, kept, omitted = [], [], []
    for sent in stage1 or []:
        if not isinstance(sent, dict):
            continue
        for u in sent.get("units") or []:
            uid = u.get("unit_id") or "S?"
            if cap_units is not None and len(kept) >= cap_units:
                omitted.append(uid)
                continue
            kept.append(uid)
            lines.append("  %s [%s] %s" % (uid, u.get("type") or "?",
                                           (u.get("text") or "").strip()))
            ents = ["%s (%s)" % (e.get("id"), e.get("type") or "?")
                    for e in u.get("entities") or [] if e.get("id")]
            if ents:
                lines.append("      entities: %s" % "; ".join(ents))
            for act in u.get("actions") or []:
                roles = act.get("roles") or {}
                shown = ", ".join("%s=%s" % (k, v)
                                  for k, v in sorted(roles.items()) if v)
                lines.append("      action: %s(%s)%s"
                             % (act.get("root"), shown,
                                "" if not act.get("mode")
                                else " [%s]" % act.get("mode")))
            for adj in u.get("adjectives") or []:
                if isinstance(adj, list) and adj:
                    lines.append("      modifier: %s -> %s"
                                 % (adj[0], adj[2] if len(adj) > 2 else "?"))
    return {"text": "\n".join(lines), "units": kept, "omitted_units": omitted}
