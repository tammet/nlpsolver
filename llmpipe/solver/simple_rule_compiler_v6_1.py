"""v6.1: a displayed atom compiles as the atom that was displayed.

Three mechanical corrections over `simple_rule_compiler_v6_signed`, and nothing
else.  Candidate selection, atom priorities, costs, proof preference and every
prompt are untouched.

**WP1 — the exact-template route.**  A candidate row carries both the atom the
model was shown and the GK literal it was built from.  The v6 fallback matched
a rule atom against that template but demanded a nested term be byte-identical,
while the parser explicitly allows one narrow generalisation inside a displayed
`eventprop` term.  So a rule the parser accepted could be refused by the
compiler with a message naming an unrelated candidate:

    displayed  ["is rel2","inherit","?X",["eventprop","$target","height 1"]]
    written    ["is rel2","inherit","?Y",["eventprop","$target","?X"]]
    v6 said    `inherit` is not the displayed constant `copy`

Here the same generalisation is honoured inside the template, every match is
recorded, and a refusal names the closest candidate rather than the first one
tried.  The completed rule is then verified literal by literal before gk sees
it, and the normal Stage-2 converter's result is accepted only when its
operative clause carries the displayed templates for **every premise and the
conclusion**, not the conclusion alone.

**WP2 — tautologies.**  A clause is a tautology if and only if it contains an
atom and the negation of the exact same atom, predicate and arguments alike.
An auxiliary tautology is discarded and recorded; an operative one refuses the
rule.  A population clause is not a tautology and is never removed for this
reason: population clauses are wanted and are preserved.

**WP3's polarity check lives in the parser**, not here; this module only keeps
the sign it is given.
"""

import copy
import json

import alignment_occurrences as AO
import bridge_world as BW
import simple_rule_compiler_v5_3 as C53
import simple_rule_compiler_v6_signed as C6
import simple_rule_parser_v5_3 as P53
import unifier_abstraction as UA

VERSION = "simple_rule_compiler_v6_1/1.0"

WORLD = C6.WORLD
CompileError = C6.CompileError
FallbackError = C6.FallbackError
SignError = C6.SignError
NORMAL_ROUTE = C6.NORMAL_ROUTE
FALLBACK_ROUTE = "exact_template"
CONTEXT_VAR = C6.CONTEXT_VAR
EVENTPROP = "eventprop"

simple_rule_to_package = C6.simple_rule_to_package
head_sign_of = C6.head_sign_of
complement = C6.complement
locate_head = C6.locate_head

# refusal reasons the plan names
TEMPLATE_CONFLICT = "candidate_template_conflict"
CONSTANT_NOT_PRESERVED = "constant_not_preserved"
NESTED_NOT_PRESERVED = "nested_term_not_preserved"
CONCLUSION_UNBOUND = "conclusion_variable_unbound"
EXTRA_LITERAL = "extra_literal_introduced"
TAUTOLOGICAL_RULE = "tautological_rule"
DISCARDED_TAUTOLOGY = "discarded_tautological_auxiliary"


class TemplateError(FallbackError):
    """A rule atom cannot be rebuilt from the candidate it was copied from."""

    def __init__(self, reason, detail):
        FallbackError.__init__(self, "%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail


# --------------------------------------------------------------- tautologies

def _standardise_clause(literals):
    """Rename this clause's variables to a canonical order."""
    names = {}

    def go(t):
        if isinstance(t, str):
            if UA.is_clause_variable(t):
                names.setdefault(t, "?:c%d" % len(names))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [[l[0]] + [go(x) for x in l[1:]] for l in literals]


def _same_atom(a, b):
    """Are these the same atom, variable names included?

    The plan says "two unifiable complementary literals".  Unifiability is too
    strong a test and would delete sound rules: `p(X) OR -p(Y)` unifies but is
    NOT valid — it is false whenever `p(a)` is false and `p(b)` is true — and a
    real rule was refused by it here (`core-0360`:
    `has target(X,Y) AND has part(Z,Y) -> has target(X,Z)`).  A clause is
    tautological only when the SAME literal appears with both signs, so that is
    what is tested.  The deviation is deliberate and is reported.
    """
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def is_tautology(clause):
    """-> (True, the two literals) when a clause is a tautology.

    A clause is a tautology if and only if it contains an atom and the negation
    of the exact same atom: the predicate and every argument must be identical.
    Unifiability is not enough — `p(X) OR -p(Y)` unifies and is not valid.
    Control literals (`$block` and friends) are not content and are ignored.
    """
    literals = [l for l in UA.literals_of(clause.get("@logic"))
                if isinstance(l, list) and l and isinstance(l[0], str)
                and not UA.is_control_predicate(l[0])]
    literals = _standardise_clause(literals)
    for i, a in enumerate(literals):
        for b in literals[i + 1:]:
            if UA.sign_of(a) == UA.sign_of(b):
                continue
            if _same_atom(UA.unsigned_atom(a), UA.unsigned_atom(b)):
                return True, [a, b]
    return False, None


def is_population(clause):
    """A population fact is not a tautology and is never dropped here."""
    return clause.get("@sourcetype") == "populate"


def strip_tautologies(clauses, operative_names):
    """-> (kept clauses, discarded rows).  An operative tautology raises."""
    kept, discarded = [], []
    for clause in clauses:
        taut, pair = is_tautology(clause)
        if not taut or is_population(clause):
            kept.append(clause)
            continue
        if clause.get("@name") in set(operative_names or ()):
            raise TemplateError(TAUTOLOGICAL_RULE,
                                "the rule's own clause is a tautology: %s"
                                % json.dumps(pair))
        discarded.append({"clause": clause, "complementary_literals": pair,
                          "why": DISCARDED_TAUTOLOGY})
    return kept, discarded


# ------------------------------------------------------- the exact template

def _display_shape(term):
    return json.dumps(term, sort_keys=True)


def _nested_correspondence(written, shown, rule_vars):
    """-> (generalised, filled, bound) positions inside a nested term, or None.

    Three moves are licensed, and only these three: a displayed `eventprop`
    participant may become a rule variable; an open displayed position may be
    filled with a constant the display itself shows; and an open displayed
    position may be named by one of the rule's own variables, which is only
    renaming.  Anything else means the term is not the displayed one.
    """
    if not (isinstance(written, list) and isinstance(shown, list)):
        return None
    if len(written) != len(shown) or str(written[0]) != str(shown[0]):
        return None
    variables, constants, bound = {}, {}, {}
    for i in range(1, len(written)):
        a, b = written[i], shown[i]
        if _display_shape(a) == _display_shape(b):
            continue
        if P53.is_rule_variable(a, rule_vars) and C53._is_display_variable(b):
            bound[i] = a          # the display is open here; rename its slot
            continue
        if P53.is_rule_variable(a, rule_vars) and isinstance(b, str) \
                and not UA.is_variable_term(b) \
                and str(written[0]) == EVENTPROP:
            variables[i] = a
            continue
        if isinstance(a, str) and not P53.is_rule_variable(a, rule_vars) \
                and C53._is_display_variable(b):
            constants[i] = a
            continue
        return None
    return variables, constants, bound


def constant_map(groups):
    """-> {displayed constant: the constant its template carries}.

    A displayed atom and its stored literal agree position by position, but a
    display constant may be written differently in the clause — `height 1` is
    `#:height 1` there.  Harvesting the correspondence lets the exact route put
    a displayed constant into an open template position, which is what the
    parser licenses when the model writes a constant where the display showed
    an open argument.
    """
    out = {}

    def walk(display, template):
        if isinstance(display, str) and isinstance(template, str):
            if not C53._is_display_variable(display) \
                    and not UA.is_clause_variable(template):
                out.setdefault(display, template)
            return
        if isinstance(display, list) and isinstance(template, list) \
                and len(display) == len(template):
            for a, b in zip(display[1:], template[1:]):
                walk(a, b)
    for g in groups or []:
        atom = g.get("atom")
        template = UA.unsigned_atom(C53._template_of(g))
        n = len(atom) - 1
        for a, b in zip(atom[1:], list(template[1:1 + n])):
            walk(a, b)
    return out


def nested_template_map(groups):
    """-> {a displayed nested term: the term its stored literal carries}.

    The parser licenses writing any displayed nested term into an open
    position, so the exact route needs that term in template form.
    """
    out = {}

    def walk(display, template):
        if isinstance(display, list) and isinstance(template, list) \
                and len(display) == len(template) \
                and str(display[0]) == str(template[0]):
            out.setdefault(_display_shape(display), template)
            for a, b in zip(display[1:], template[1:]):
                walk(a, b)
    for g in groups or []:
        atom = g.get("atom")
        template = UA.unsigned_atom(C53._template_of(g))
        n = len(atom) - 1
        for a, b in zip(atom[1:], list(template[1:1 + n])):
            walk(a, b)
    return out


def _apply_nested(template_term, positions, bindings):
    """Put the rule's variables into the template's nested term."""
    got = copy.deepcopy(template_term)
    for i, var in positions.items():
        if i >= len(got):
            return None
        got[i] = bindings.setdefault(var, "?:v_%s" % var)
    return got


def match_template(atom, group, index, rule_vars, bindings, generalised,
                   constants=None, nested=None):
    """-> the literal this rule atom contributes, built from its template."""
    constants = constants if constants is not None else {}
    nested = nested if nested is not None else {}
    display = group["atom"]
    template = UA.unsigned_atom(C53._template_of(group))
    predicate = str(display[0])
    if str(atom[0]) != predicate:
        raise TemplateError(TEMPLATE_CONFLICT,
                            "`%s` is not the displayed predicate `%s`"
                            % (atom[0], predicate))
    if len(atom) != len(display):
        raise TemplateError(TEMPLATE_CONFLICT,
                            "`%s` has %d arguments, the displayed atom has %d"
                            % (predicate, len(atom) - 1, len(display) - 1))
    n = len(display) - 1
    extra = list(template[1 + n:])
    if not all(C53._is_context_argument(t) for t in extra):
        raise TemplateError(TEMPLATE_CONFLICT,
                            "the stored literal carries a non-context "
                            "argument the exact route cannot rebuild: %s"
                            % json.dumps(extra))
    names = {}
    args = [C53._standardise(a, index, names) for a in template[1:1 + n]]
    label_slot = AO.LABEL_SLOT.get(predicate)
    subst = {}
    for i, (written, shown) in enumerate(zip(atom[1:], display[1:])):
        slot = args[i]
        if isinstance(written, list) or isinstance(shown, list):
            if _display_shape(written) == _display_shape(shown):
                continue                       # the template's own term stands
            if P53.is_rule_variable(written, rule_vars):
                # the rule generalised a displayed nested term to a variable
                mine = bindings.setdefault(written, "?:v_%s" % written)
                if i == label_slot:
                    raise TemplateError(
                        CONSTANT_NOT_PRESERVED,
                        "a content label of `%s` cannot become a variable"
                        % predicate)
                generalised.append({"predicate": predicate,
                                    "argument": i + 1,
                                    "displayed_term": shown,
                                    "rule_variable": written})
                args[i] = mine
                continue
            if isinstance(written, list) and C53._is_display_variable(shown):
                # the rule filled an open position with a displayed term
                want = nested.get(_display_shape(written))
                if want is None:
                    raise TemplateError(
                        NESTED_NOT_PRESERVED,
                        "%s was never displayed, so it cannot fill an open "
                        "position of `%s`"
                        % (json.dumps(written), predicate))
                if UA.is_clause_variable(slot):
                    subst[slot] = copy.deepcopy(want)
                elif _display_shape(slot) != _display_shape(want):
                    raise TemplateError(
                        NESTED_NOT_PRESERVED,
                        "the stored literal holds %s where the rule wrote %s"
                        % (json.dumps(slot)[:60], json.dumps(written)[:60]))
                continue
            got = _nested_correspondence(written, shown, rule_vars)
            if got is None:
                raise TemplateError(
                    NESTED_NOT_PRESERVED,
                    "a nested argument of `%s` is neither the displayed term "
                    "nor an allowed participant substitution: %s"
                    % (predicate, json.dumps(written)))
            positions, filled, bound = got
            built = _apply_nested(slot, positions, bindings)
            if built is None:
                raise TemplateError(
                    NESTED_NOT_PRESERVED,
                    "the stored literal's nested term does not have the "
                    "displayed shape at `%s`" % predicate)
            for pos, var in bound.items():
                if pos >= len(built):
                    raise TemplateError(NESTED_NOT_PRESERVED,
                                        "the stored nested term is shorter "
                                        "than the displayed one at `%s`"
                                        % predicate)
                mine = bindings.setdefault(var, "?:v_%s" % var)
                if UA.is_clause_variable(built[pos]):
                    subst[built[pos]] = mine
                else:
                    built = copy.deepcopy(built)
                    built[pos] = mine
            for pos, value in filled.items():
                if pos >= len(built):
                    raise TemplateError(NESTED_NOT_PRESERVED,
                                        "the stored nested term is shorter "
                                        "than the displayed one at `%s`"
                                        % predicate)
                want = constants.get(value)
                if want is None:
                    raise TemplateError(
                        CONSTANT_NOT_PRESERVED,
                        "`%s` is not a displayed constant, so it cannot fill "
                        "an open position of `%s`" % (value, predicate))
                if UA.is_clause_variable(built[pos]):
                    subst[built[pos]] = want
                elif UA._norm_constant(str(built[pos])) \
                        != UA._norm_constant(str(want)):
                    raise TemplateError(
                        CONSTANT_NOT_PRESERVED,
                        "the stored nested term holds `%s` where the rule "
                        "wrote `%s`" % (built[pos], value))
                built = copy.deepcopy(built)
                built[pos] = want
            args[i] = built
            for pos, var in positions.items():
                generalised.append({"predicate": predicate,
                                    "argument": i + 1, "nested_position": pos,
                                    "displayed_constant": shown[pos],
                                    "rule_variable": var})
            continue
        if P53.is_rule_variable(written, rule_vars):
            mine = bindings.setdefault(written, "?:v_%s" % written)
            if C53._is_display_variable(shown):
                if not UA.is_clause_variable(slot):
                    raise TemplateError(
                        TEMPLATE_CONFLICT,
                        "the displayed atom is open at argument %d of `%s` "
                        "but its stored literal is not" % (i + 1, predicate))
                subst[slot] = mine
                continue
            if i == label_slot:
                raise TemplateError(
                    CONSTANT_NOT_PRESERVED,
                    "a content label of `%s` cannot become a variable"
                    % predicate)
            if C53._looks_like_a_world(slot):
                raise TemplateError(
                    CONSTANT_NOT_PRESERVED,
                    "the world or context constant `%s` cannot become a "
                    "variable" % slot)
            generalised.append({"predicate": predicate, "argument": i + 1,
                                "displayed_constant": shown,
                                "template_constant": slot,
                                "rule_variable": written})
            args[i] = mine
            continue
        if C53._is_display_variable(shown):
            raise TemplateError(CONSTANT_NOT_PRESERVED,
                                "`%s` was written where the displayed atom "
                                "has a variable" % written)
        if UA._norm_constant(str(written)) != UA._norm_constant(str(shown)):
            raise TemplateError(CONSTANT_NOT_PRESERVED,
                                "`%s` is not the displayed constant `%s`"
                                % (written, shown))
    args = [C53._substitute(a, subst) for a in args]
    return [template[0]] + args + [CONTEXT_VAR] * len(extra)


def _score(atom, group):
    """How closely a candidate resembles this rule atom, for error reporting."""
    display = group["atom"]
    if str(display[0]) != str(atom[0]) or len(display) != len(atom):
        return -1
    same = 0
    for written, shown in zip(atom[1:], display[1:]):
        if _display_shape(written) == _display_shape(shown):
            same += 1
    return same


def compile_rule_exact(rule, groups, hypothesis_id):
    """-> (clauses, record).  Every literal rebuilt from its own template."""
    rule_vars = P53.rule_variables(rule)
    bindings, generalised, used, matches = {}, [], [], []
    constants = constant_map(groups)
    nested = nested_template_map(groups)

    def match(atom, index, role):
        best, errors = None, []
        for g in groups:
            if str(g["atom"][0]) != str(atom[0]) \
                    or len(g["atom"]) != len(atom):
                continue
            trial_b, trial_g = dict(bindings), []
            try:
                got = match_template(atom, g, index, rule_vars, trial_b,
                                     trial_g, constants, nested)
            except TemplateError as e:
                errors.append((_score(atom, g), e, g))
                continue
            if best is None or len(trial_g) < len(best[0]):
                best = (trial_g, g, got, trial_b)
        if best is None:
            if errors:
                errors.sort(key=lambda row: -row[0])
                _s, err, g = errors[0]
                raise TemplateError(err.reason,
                                    "%s (closest candidate %s: %s)"
                                    % (err.detail, g.get("id"),
                                       json.dumps(g["atom"])))
            raise TemplateError(TEMPLATE_CONFLICT,
                                "no displayed atom has the predicate and "
                                "arity of %s" % json.dumps(atom))
        trial_g, g, got, trial_b = best
        bindings.update(trial_b)
        generalised.extend(trial_g)
        used.append(g.get("id"))
        matches.append({"role": role, "atom": atom, "candidate": g.get("id"),
                        "displayed": g["atom"], "template": g["literal"],
                        "compiled": got})
        return got

    literals = []
    for k, lit in enumerate(rule["body"], start=1):
        if lit["sign"] == "-":
            raise TemplateError(TEMPLATE_CONFLICT,
                                "the exact route compiles positive premises "
                                "only")
        got = match(lit["atom"], k, "premise")
        literals.append(["-" + UA.bare_predicate(got[0])] + list(got[1:]))
    head = rule["head"]
    got = match(head["atom"], 0, "conclusion")
    positive_head = copy.deepcopy(got)
    if head["sign"] == "-":
        got = ["-" + UA.bare_predicate(got[0])] + list(got[1:])
    body_vars = set()
    for lit in rule["body"]:
        body_vars |= set(P53.atom_variables(lit["atom"], rule_vars))
    free = set(P53.atom_variables(head["atom"], rule_vars)) - body_vars
    if free:
        raise TemplateError(CONCLUSION_UNBOUND,
                            "the conclusion uses %s, which the body never "
                            "binds" % ", ".join(sorted(free)))
    literals.append(got)
    block = ["$block", ["$", str(UA.bare_predicate(got[0])), 1],
             complement(got)]
    clause = {"@name": BW.HYPOTHESIS_PROVENANCE % (hypothesis_id, 1),
              "@logic": literals + [block]}
    taut, pair = is_tautology(clause)
    if taut:
        raise TemplateError(TAUTOLOGICAL_RULE,
                            "the rule's own clause is a tautology: %s"
                            % json.dumps(pair))
    record = {"compiler_route": FALLBACK_ROUTE,
              "displayed_atoms_used": used,
              "generalised_constants": generalised,
              "template_matches": matches,
              "clause_provenance": {clause["@name"]: hypothesis_id},
              "rule_clause_names": [clause["@name"]],
              "population_clause_names": [],
              "has_block": True,
              "bridge_evidence": None,
              "positive_conclusion_literal": positive_head,
              "context_policy": "every trailing context argument became one "
                                "shared clause variable",
              "blocker_policy": "the blocker is the complement of the "
                                "conclusion"}
    record["signed"] = provenance(rule, [clause], groups,
                                  record["rule_clause_names"], matches)
    return [clause], record


def _agrees_v6_1(literal, atom, rule, predicate):
    """v6's agreement test, with nested terms compared position by position.

    v6 required a nested argument to be byte-identical, which never holds once
    the rule generalises a displayed participant, so the conclusion of such a
    rule could not be located in its own clause.
    """
    got = UA.unsigned_atom(literal)
    if str(got[0]) != predicate:
        return False
    rule_vars = P53.rule_variables(rule)
    args = list(got[1:])
    for i, written in enumerate(atom[1:]):
        if i >= len(args):
            return False
        if P53.is_rule_variable(written, rule_vars):
            continue
        if isinstance(written, list) or isinstance(args[i], list):
            if not (isinstance(written, list) and isinstance(args[i], list)):
                return False
            if len(written) != len(args[i]) \
                    or str(written[0]) != str(args[i][0]):
                return False
            for a, b in zip(written[1:], args[i][1:]):
                if P53.is_rule_variable(a, rule_vars):
                    continue
                if _display_shape(a) != _display_shape(b) \
                        and UA._norm_constant(str(a)) \
                        != UA._norm_constant(str(b)):
                    return False
            continue
        if UA._norm_constant(str(written)) != UA._norm_constant(str(args[i])):
            return False
    return True


def provenance(rule, clauses, groups, names, matches=None):
    """Which compiled literal came from the parsed head, and from each premise.

    With `matches` — the exact route — this is what the compiler just built.
    Without them the converter's clause is searched, using the corrected
    agreement test.
    """
    if matches:
        head = [m for m in matches if m["role"] == "conclusion"]
        body = [m for m in matches if m["role"] == "premise"]
        head_lit = head[0]["compiled"] if head else None
        if head_lit is not None and head_sign_of(rule) == "-":
            head_lit = ["-" + UA.bare_predicate(head_lit[0])] \
                + list(head_lit[1:])
        return {"parsed_body": [{"sign": l["sign"], "atom": l["atom"]}
                                for l in rule["body"]],
                "parsed_head": {"sign": head_sign_of(rule),
                                "atom": rule["head"]["atom"]},
                "parsed_body_displayed_atoms": [m["candidate"] for m in body],
                "parsed_head_displayed_atom": head[0]["candidate"]
                if head else None,
                "compiled_head_literal": head_lit,
                "compiled_body_literals": [
                    ["-" + UA.bare_predicate(m["compiled"][0])]
                    + list(m["compiled"][1:]) for m in body],
                "compiled_head_sign": UA.sign_of(head_lit) if head_lit
                else None,
                "head_located": head_lit is not None,
                "head_not_located_why": None if head_lit is not None
                else "the exact route recorded no conclusion match",
                "negative_conclusion": head_sign_of(rule) == "-",
                "read_from": "the exact-template match"}
    before = C6._agrees
    C6._agrees = _agrees_v6_1
    try:
        got = C6._provenance(rule, clauses, groups, names)
    finally:
        C6._agrees = before
    got["read_from"] = "the converter's clause"
    return got


# ------------------------------------------------ verifying a compiled rule

def _canonical(literals):
    return sorted(json.dumps(l, sort_keys=True)
                  for l in _standardise_clause(literals))


def operative_literals(clauses, names):
    out = []
    for c in clauses or []:
        if names and c.get("@name") not in set(names):
            continue
        if is_population(c):
            continue
        for lit in UA.literals_of(c.get("@logic")):
            if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                    and not UA.is_control_predicate(lit[0]):
                out.append(lit)
    return out


def verify_against_templates(clauses, names, reference):
    """-> (ok, why).  The operative clause must be the exact-template clause.

    Compared up to renaming the clause's own variables, so the converter may
    name variables as it likes but may not add, drop or alter a literal.
    """
    mine = operative_literals(clauses, names)
    want = operative_literals(reference, None)
    if not mine:
        return False, "the conversion produced no operative literal"
    if len(mine) != len(want):
        return False, ("%s: the conversion has %d content literals, the "
                       "displayed templates give %d"
                       % (EXTRA_LITERAL, len(mine), len(want)))
    if _canonical(mine) != _canonical(want):
        return False, ("the conversion does not carry the displayed "
                       "templates: %s vs %s"
                       % (json.dumps(_canonical(mine))[:200],
                          json.dumps(_canonical(want))[:200]))
    return True, None


# ------------------------------------------------------------- the routes

# The exact route governs rules the model wrote out of displayed atoms.  A
# channel that BUILDS its rule in code from something else — the distinctness
# channel's equalities, whose predicate is deliberately not a displayed atom —
# is compiled as before; the plan leaves equality to that channel.
EXACT_ORIGINS = (P53.LLM_GENERAL, P53.GROUND_SPECIALIZATION)


def governs(rule):
    origin = rule.get("origin")
    return origin is None or origin in EXACT_ORIGINS


def compile_one(rule, view, configuration, groups=(), case_id=None,
                world_name="probe", package_id="A1", hypothesis_id=None):
    """-> (clauses, record).  The converter when faithful, else the templates."""
    if not governs(rule):
        clauses, rec = C6.compile_one(rule, view, configuration, groups=groups,
                                      case_id=case_id, world_name=world_name,
                                      package_id=package_id,
                                      hypothesis_id=hypothesis_id)
        rec["exact_route"] = ("not applicable: this rule was built by the %s "
                              "channel, not from displayed atoms"
                              % rule.get("origin"))
        kept, discarded = strip_tautologies(clauses,
                                            rec.get("rule_clause_names"))
        rec["discarded_tautological_auxiliaries"] = discarded
        return kept, rec
    case_id = case_id or view.get("case_id") or "case"
    hypothesis_id = hypothesis_id or "%s::%s" % (case_id, rule["rule_id"])
    reference, ref_record = compile_rule_exact(rule, groups, hypothesis_id)
    normal_error = None
    try:
        pkg = simple_rule_to_package(rule)
        clauses, rec = BW.compile_bridge(
            case_id, world_name, pkg, view["stage1"], view["stage2"],
            configuration, bridge_evidence=BW.RUNTIME_EVIDENCE,
            package_id=package_id, base_clauses=view.get("final_clauses"),
            hypothesis_id=hypothesis_id)
        ok, why = verify_against_templates(clauses,
                                           rec.get("rule_clause_names"),
                                           reference)
        if ok:
            kept, discarded = strip_tautologies(
                clauses, rec.get("rule_clause_names"))
            rec["compiler_route"] = NORMAL_ROUTE
            rec["signed"] = provenance(rule, kept, groups,
                                       rec.get("rule_clause_names"))
            rec["template_matches"] = ref_record["template_matches"]
            rec["discarded_tautological_auxiliaries"] = discarded
            rec["verified_against_templates"] = True
            C6._check_sign(rule, rec)
            return kept, rec
        normal_error = why
    except BW.BridgeError as e:
        normal_error = str(e)[:200]
    except TemplateError:
        raise
    except SignError as e:
        normal_error = str(e)[:200]
    except Exception as e:                                      # noqa: BLE001
        normal_error = "the converter raised %s: %s" % (type(e).__name__,
                                                        str(e)[:160])
    ref_record["normal_route_refusal"] = normal_error
    ref_record.setdefault("signed",
                          provenance(rule, reference, groups,
                                     ref_record["rule_clause_names"],
                                     ref_record.get("template_matches")))
    ref_record["discarded_tautological_auxiliaries"] = []
    ref_record["verified_against_templates"] = True
    C6._check_sign(rule, ref_record)
    return reference, ref_record


def build_world(world_id, rules, view, configuration, groups=(), weight=1.0,
                redundancy=None):
    """v6's world, compiled through the exact-template route."""
    before = C6.compile_one
    C6.compile_one = compile_one
    try:
        got = C6.build_world(world_id, rules, view, configuration,
                             groups=groups, weight=weight,
                             redundancy=redundancy)
    finally:
        C6.compile_one = before
    got["compiler_version"] = VERSION
    got["discarded_tautological_auxiliaries"] = [
        row for h in got.get("bridge_hypotheses") or []
        for row in (h.get("discarded_tautological_auxiliaries") or [])]
    return got


clause_facts = C6.clause_facts
literals = C6.literals
