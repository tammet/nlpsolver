"""A rule becomes gk clauses, built from the atoms that were displayed.

Two routes, and a check that decides between them.  The Stage-2 bridge
converter runs first; its result is accepted only when the operative clause
carries the displayed template of EVERY premise and of the conclusion.  When it
does not, the exact-template route rebuilds the clause from the stored literal
of each displayed candidate, which is the only way a rule the parser accepted
is guaranteed to reach the prover as the rule that was written.

Four moves are licensed inside a displayed atom, each one the parser already
allows: a displayed `eventprop` participant may become a rule variable, and an
open position may be filled by a displayed constant, by one of the rule's own
variables, or by a displayed nested term.  Anything else refuses the rule with
a named reason.

Every rule clause is defeasible: one `$block` whose literal is the complement
of the conclusion, at full confidence, with no `@confidence` annotation.  A
clause holding an atom and the negation of the exact same atom proves nothing
and is discarded; a population clause is never touched.
"""

import copy
import json

import alignment_occurrences as AO
import bridge_world as BW
import litbridge_atoms as atoms
import litbridge_rules as rules


# --------------------------------------------------------------- constants

VERSION = "litbridge_compile/2026-08-15"

WORLD = "W0"

CLAUSE_NATIVE_ROUTE = "clause_native_fallback"

NORMAL_ROUTE = "stage2_bridge_converter"

CONTEXT_VAR = "?:Cbridge"

EXACT_TEMPLATE_ROUTE = "exact_template"

EVENTPROP = "eventprop"

TEMPLATE_CONFLICT = "candidate_template_conflict"

CONSTANT_NOT_PRESERVED = "constant_not_preserved"

NESTED_NOT_PRESERVED = "nested_term_not_preserved"

CONCLUSION_UNBOUND = "conclusion_variable_unbound"

EXTRA_LITERAL = "extra_literal_introduced"

TAUTOLOGICAL_RULE = "tautological_rule"

DISCARDED_TAUTOLOGY = "discarded_tautological_auxiliary"

EXACT_ORIGINS = (rules.LLM_GENERAL, rules.GROUND_SPECIALIZATION)


# ---------------------------------------------- the package a rule becomes

def simple_rule_to_package(rule, world=WORLD):
    """-> `["holds", W, forall ?vars . BODY -> normally(HEAD)]`.

    Only the rule's own `?` variables are quantified; every other token is a
    constant of the passage.
    """
    if not rule.get("body") or not rule.get("head"):
        raise CompileError("a rule needs a body and one conclusion")
    lits = [_literal(l) for l in rule["body"]]
    body = lits[0] if len(lits) == 1 else ["and"] + lits
    inner = ["implies", body, ["normally", _literal(rule["head"])]]
    for v in reversed(rules.rule_variables(rule)):
        inner = ["forall", v, inner]
    pkg = ["holds", world, inner]
    if BW.to_defeasible_shape(pkg) != pkg:
        raise CompileError("the built package is not in defeasible shape")
    return pkg

def hypothesis(rule, case_id, weight=1.0):
    return {"hypothesis_id": "%s::%s" % (case_id, rule["rule_id"]),
            "label": rule["rule_id"], "weight": weight, "case_id": case_id,
            "package": _package_binding_free_variables(rule),
            "printed_formula": rule["printed"], "rule_id": rule["rule_id"],
            "canonical": rule["canonical"],
            "origin": rule.get("origin"),
            "warnings": rule.get("warnings") or []}

def _literal(lit):
    atom = list(lit["atom"])
    return ["not", atom] if lit["sign"] == "-" else atom


# ------------------------------------------------ the exact-template route

def compile_rule_exact(rule, groups, hypothesis_id):
    """-> (clauses, record).  Every literal rebuilt from its own template."""
    rule_vars = rules.rule_variables(rule)
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
        literals.append(["-" + atoms.bare_predicate(got[0])] + list(got[1:]))
    head = rule["head"]
    got = match(head["atom"], 0, "conclusion")
    positive_head = copy.deepcopy(got)
    if head["sign"] == "-":
        got = ["-" + atoms.bare_predicate(got[0])] + list(got[1:])
    body_vars = set()
    for lit in rule["body"]:
        body_vars |= set(rules.atom_variables(lit["atom"], rule_vars))
    free = set(rules.atom_variables(head["atom"], rule_vars)) - body_vars
    if free:
        raise TemplateError(CONCLUSION_UNBOUND,
                            "the conclusion uses %s, which the body never "
                            "binds" % ", ".join(sorted(free)))
    literals.append(got)
    block = ["$block", ["$", str(atoms.bare_predicate(got[0])), 1],
             complement(got)]
    clause = {"@name": BW.HYPOTHESIS_PROVENANCE % (hypothesis_id, 1),
              "@logic": literals + [block]}
    taut, pair = is_tautology(clause)
    if taut:
        raise TemplateError(TAUTOLOGICAL_RULE,
                            "the rule's own clause is a tautology: %s"
                            % json.dumps(pair))
    record = {"compiler_route": EXACT_TEMPLATE_ROUTE,
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

def match_template(atom, group, index, rule_vars, bindings, generalised,
                   constants=None, nested=None):
    """-> the literal this rule atom contributes, built from its template."""
    constants = constants if constants is not None else {}
    nested = nested if nested is not None else {}
    display = group["atom"]
    template = atoms.unsigned_atom(_template_of(group))
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
    if not all(atoms._is_context_argument(t) for t in extra):
        raise TemplateError(TEMPLATE_CONFLICT,
                            "the stored literal carries a non-context "
                            "argument the exact route cannot rebuild: %s"
                            % json.dumps(extra))
    names = {}
    args = [_standardise(a, index, names) for a in template[1:1 + n]]
    label_slot = AO.LABEL_SLOT.get(predicate)
    subst = {}
    for i, (written, shown) in enumerate(zip(atom[1:], display[1:])):
        slot = args[i]
        if isinstance(written, list) or isinstance(shown, list):
            if _display_shape(written) == _display_shape(shown):
                continue                       # the template's own term stands
            if rules.is_rule_variable(written, rule_vars):
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
            if isinstance(written, list) and _is_display_variable(shown):
                # the rule filled an open position with a displayed term
                want = nested.get(_display_shape(written))
                if want is None:
                    raise TemplateError(
                        NESTED_NOT_PRESERVED,
                        "%s was never displayed, so it cannot fill an open "
                        "position of `%s`"
                        % (json.dumps(written), predicate))
                if atoms.is_clause_variable(slot):
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
                if atoms.is_clause_variable(built[pos]):
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
                if atoms.is_clause_variable(built[pos]):
                    subst[built[pos]] = want
                elif atoms._norm_constant(str(built[pos])) \
                        != atoms._norm_constant(str(want)):
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
        if rules.is_rule_variable(written, rule_vars):
            mine = bindings.setdefault(written, "?:v_%s" % written)
            if _is_display_variable(shown):
                if not atoms.is_clause_variable(slot):
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
            if _looks_like_a_world(slot):
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
        if _is_display_variable(shown):
            raise TemplateError(CONSTANT_NOT_PRESERVED,
                                "`%s` was written where the displayed atom "
                                "has a variable" % written)
        if atoms._norm_constant(str(written)) != atoms._norm_constant(str(shown)):
            raise TemplateError(CONSTANT_NOT_PRESERVED,
                                "`%s` is not the displayed constant `%s`"
                                % (written, shown))
    args = [_substitute(a, subst) for a in args]
    return [template[0]] + args + [CONTEXT_VAR] * len(extra)

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
            if not _is_display_variable(display) \
                    and not atoms.is_clause_variable(template):
                out.setdefault(display, template)
            return
        if isinstance(display, list) and isinstance(template, list) \
                and len(display) == len(template):
            for a, b in zip(display[1:], template[1:]):
                walk(a, b)
    for g in groups or []:
        atom = g.get("atom")
        template = atoms.unsigned_atom(_template_of(g))
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
        template = atoms.unsigned_atom(_template_of(g))
        n = len(atom) - 1
        for a, b in zip(atom[1:], list(template[1:1 + n])):
            walk(a, b)
    return out

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
        if rules.is_rule_variable(a, rule_vars) and _is_display_variable(b):
            bound[i] = a          # the display is open here; rename its slot
            continue
        if rules.is_rule_variable(a, rule_vars) and isinstance(b, str) \
                and not atoms.is_variable_term(b) \
                and str(written[0]) == EVENTPROP:
            variables[i] = a
            continue
        if isinstance(a, str) and not rules.is_rule_variable(a, rule_vars) \
                and _is_display_variable(b):
            constants[i] = a
            continue
        return None
    return variables, constants, bound

def _apply_nested(template_term, positions, bindings):
    """Put the rule's variables into the template's nested term."""
    got = copy.deepcopy(template_term)
    for i, var in positions.items():
        if i >= len(got):
            return None
        got[i] = bindings.setdefault(var, "?:v_%s" % var)
    return got

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


# -------------------------------------------------------- choosing a route

def compile_one(rule, view, configuration, groups=(), case_id=None,
                world_name="probe", package_id="A1", hypothesis_id=None):
    """-> (clauses, record).  The converter when faithful, else the templates."""
    if not governs(rule):
        clauses, rec = _compile_one_with_fallback(rule, view, configuration, groups=groups,
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
            _check_sign(rule, rec)
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
    _check_sign(rule, ref_record)
    return reference, ref_record

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

def operative_literals(clauses, names):
    out = []
    for c in clauses or []:
        if names and c.get("@name") not in set(names):
            continue
        if is_population(c):
            continue
        for lit in atoms.literals_of(c.get("@logic")):
            if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                    and not atoms.is_control_predicate(lit[0]):
                out.append(lit)
    return out

def _normal_route_is_faithful(clauses, rule, groups):
    """Does the converted clause carry the literals the rule's atoms stand for?

    Only the CONCLUSION is checked: a premise appears negated and may be
    rewritten by the converter in ways the display check already documents,
    while a conclusion that is not the displayed literal means the bridge does
    not assert what the model wrote.
    """
    lits = _content_literals(clauses)
    if not lits:
        return False, "the conversion produced no content literal"
    head = rule["head"]["atom"]
    want = None
    for g in groups:
        if atoms.alpha_equivalent(g["atom"], head) or _generalises(
                head, g["atom"], rules.rule_variables(rule)):
            want = g
            break
    if want is None:
        return True, None                       # nothing to compare against
    n = len(want["atom"]) - 1
    target = atoms.unsigned_atom(want["literal"])
    for l in lits:
        if atoms.sign_of(l) != rule["head"]["sign"]:
            continue
        atom = atoms.unsigned_atom(l)
        if str(atom[0]) != str(target[0]) or len(atom) - 1 < n:
            continue
        return True, None
    return False, ("no converted literal has the conclusion's displayed "
                   "predicate `%s`" % target[0])

def governs(rule):
    origin = rule.get("origin")
    return origin is None or origin in EXACT_ORIGINS


# ------------------------------------------------------------- tautologies

def is_tautology(clause):
    """-> (True, the two literals) when a clause is a tautology.

    A clause is a tautology if and only if it contains an atom and the negation
    of the exact same atom: the predicate and every argument must be identical.
    Unifiability is not enough — `p(X) OR -p(Y)` unifies and is not valid.
    Control literals (`$block` and friends) are not content and are ignored.
    """
    literals = [l for l in atoms.literals_of(clause.get("@logic"))
                if isinstance(l, list) and l and isinstance(l[0], str)
                and not atoms.is_control_predicate(l[0])]
    literals = _standardise_clause(literals)
    for i, a in enumerate(literals):
        for b in literals[i + 1:]:
            if atoms.sign_of(a) == atoms.sign_of(b):
                continue
            if _same_atom(atoms.unsigned_atom(a), atoms.unsigned_atom(b)):
                return True, [a, b]
    return False, None

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

def is_population(clause):
    """A population fact is not a tautology and is never dropped here."""
    return clause.get("@sourcetype") == "populate"

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

def _standardise_clause(literals):
    """Rename this clause's variables to a canonical order."""
    names = {}

    def go(t):
        if isinstance(t, str):
            if atoms.is_clause_variable(t):
                names.setdefault(t, "?:c%d" % len(names))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [[l[0]] + [go(x) for x in l[1:]] for l in literals]


# --------------------------------------------------------- head provenance

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
            head_lit = ["-" + atoms.bare_predicate(head_lit[0])] \
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
                    ["-" + atoms.bare_predicate(m["compiled"][0])]
                    + list(m["compiled"][1:]) for m in body],
                "compiled_head_sign": atoms.sign_of(head_lit) if head_lit
                else None,
                "head_located": head_lit is not None,
                "head_not_located_why": None if head_lit is not None
                else "the exact route recorded no conclusion match",
                "negative_conclusion": head_sign_of(rule) == "-",
                "read_from": "the exact-template match"}
    got = _provenance(rule, clauses, groups, names, agrees=_agrees_v6_1)
    got["read_from"] = "the converter's clause"
    return got

def locate_head(clauses, rule, groups, rule_clause_names=(), agrees=None):
    """-> (the compiled conclusion literal, the other literals, why not).

    The conclusion is the clause literal that carries the conclusion's
    displayed predicate, its written constants and the sign the model wrote.
    A premise is not a candidate for it: for `A -> NOT B` every literal of the
    clause is negative, so the sign alone decides nothing and the atom must be
    compared.  Where more than one literal still agrees, the last one is the
    conclusion, which is where both routes put it.
    """
    names = set(rule_clause_names or [])
    mine = [c for c in clauses or []
            if (not names or c.get("@name") in names)
            and c.get("@sourcetype") != "populate"]
    if not mine:
        return None, [], "the conversion produced no rule clause"
    lits = []
    for c in mine:
        lits.extend(_content_literals_of(c))
    if not lits:
        return None, [], "the conversion produced no content literal"
    want_sign = head_sign_of(rule)
    predicate = _template_predicate(rule["head"]["atom"], rule, groups)
    cands = [l for l in lits
             if atoms.sign_of(l) == want_sign
             and (agrees or _agrees)(l, rule["head"]["atom"], rule,
                                     predicate)]
    if not cands:
        return None, lits, ("no converted literal has the conclusion's "
                            "displayed predicate `%s` with sign `%s`"
                            % (predicate, want_sign))
    head = cands[-1]
    rest = [l for l in lits if l is not head]
    return head, rest, None

def _agrees_v6_1(literal, atom, rule, predicate):
    """v6's agreement test, with nested terms compared position by position.

    v6 required a nested argument to be byte-identical, which never holds once
    the rule generalises a displayed participant, so the conclusion of such a
    rule could not be located in its own clause.
    """
    got = atoms.unsigned_atom(literal)
    if str(got[0]) != predicate:
        return False
    rule_vars = rules.rule_variables(rule)
    args = list(got[1:])
    for i, written in enumerate(atom[1:]):
        if i >= len(args):
            return False
        if rules.is_rule_variable(written, rule_vars):
            continue
        if isinstance(written, list) or isinstance(args[i], list):
            if not (isinstance(written, list) and isinstance(args[i], list)):
                return False
            if len(written) != len(args[i]) \
                    or str(written[0]) != str(args[i][0]):
                return False
            for a, b in zip(written[1:], args[i][1:]):
                if rules.is_rule_variable(a, rule_vars):
                    continue
                if _display_shape(a) != _display_shape(b) \
                        and atoms._norm_constant(str(a)) \
                        != atoms._norm_constant(str(b)):
                    return False
            continue
        if atoms._norm_constant(str(written)) != atoms._norm_constant(str(args[i])):
            return False
    return True

def _displayed_for(atom, rule, groups):
    """The displayed group this rule atom stands for, if there is one.

    An exact match wins over one the rule generalised, so the recorded
    provenance names the atom the model actually copied.
    """
    rule_vars = rules.rule_variables(rule)
    for g in groups or []:
        if atoms.alpha_equivalent(g["atom"], atom):
            return g
    for g in groups or []:
        if _generalises(atom, g["atom"], rule_vars):
            return g
    return None

def _template_predicate(atom, rule, groups):
    g = _displayed_for(atom, rule, groups)
    if g is None:
        return str(atom[0])
    return str(atoms.unsigned_atom(g["literal"])[0])

def head_sign_of(rule):
    return (rule.get("head") or {}).get("sign") or "+"

def complement(literal):
    """The literal whose derivation defeats this conclusion as a default."""
    if atoms.sign_of(literal) == "-":
        return [atoms.bare_predicate(literal[0])] + list(literal[1:])
    return ["$not", copy.deepcopy(literal)]


# ---------------------------------------------------------- one submission

def build_world(world_id, rules, view, configuration, groups=(), weight=1.0,
                redundancy=None):
    """v6's world, compiled through the exact-template route."""
    got = _build_world_base(world_id, rules, view, configuration,
                            groups=groups, weight=weight,
                            redundancy=redundancy)
    got["compiler_version"] = VERSION
    got["discarded_tautological_auxiliaries"] = [
        row for h in got.get("bridge_hypotheses") or []
        for row in (h.get("discarded_tautological_auxiliaries") or [])]
    return got

def clause_facts(clauses):
    """What a caller must be able to assert about a compiled bridge."""
    blob = json.dumps(clauses)
    rule_clauses = [c for c in clauses if c.get("@sourcetype") != "populate"]
    return {
        "clause_count": len(clauses),
        "rule_clause_count": len(rule_clauses),
        "has_block": "$block" in blob,
        "confidence_annotations": [c.get("@confidence") for c in clauses],
        "any_confidence_annotation": any(c.get("@confidence") is not None
                                         for c in clauses),
        "names": [c.get("@name") for c in clauses],
    }

def literals(clauses):
    """Every literal of a compiled clause list, flattened."""
    out = []
    for c in clauses:
        body = c.get("@logic")
        if not isinstance(body, list) or not body:
            continue
        lits = body if isinstance(body[0], list) else [body]
        for lit in lits:
            if isinstance(lit, list) and lit and isinstance(lit[0], str):
                out.append(lit)
    return out


# ---------------------------------------------------------------- the rest

class CompileError(Exception):
    """The rule cannot be compiled.  Never worked around."""

def free_variables(rule):
    """The rule's free variables, in first-appearance order over body, head."""
    out = []
    for lit in rule["body"] + [rule["head"]]:
        for v in atoms.free_variables(lit["atom"]):
            if v not in out:
                out.append(v)
    return out

def _package_binding_free_variables(rule, world=WORLD):
    """-> `["holds", W, forall V1 ... . BODY -> normally(HEAD)]`.

    Only the FREE variables are quantified.  A set binder's own variable stays
    inside its term, where the converter binds it.
    """
    if not rule.get("body") or not rule.get("head"):
        raise CompileError("a rule needs a body and one conclusion")
    lits = [_literal(l) for l in rule["body"]]
    body = lits[0] if len(lits) == 1 else ["and"] + lits
    inner = ["implies", body, ["normally", _literal(rule["head"])]]
    for v in reversed(free_variables(rule)):
        inner = ["forall", v, inner]
    pkg = ["holds", world, inner]
    if BW.to_defeasible_shape(pkg) != pkg:
        raise CompileError("the built package is not in defeasible shape")
    return pkg

def compile_by_the_converter(rule, view, configuration, case_id=None, world_name="probe",
                package_id="A1"):
    """-> (clauses, record) for one rule, compiled alone."""
    case_id = case_id or view.get("case_id") or "case"
    h = hypothesis(rule, case_id)
    return BW.compile_bridge(case_id, world_name, h["package"],
                             view["stage1"], view["stage2"], configuration,
                             bridge_evidence=BW.RUNTIME_EVIDENCE,
                             package_id=package_id,
                             base_clauses=view.get("final_clauses"),
                             hypothesis_id=h["hypothesis_id"])

class FallbackError(CompileError):
    """The exact clause-native compiler refuses this rule."""

def _content_length(group):
    return len(group["atom"]) - 1

def _template_of(group):
    """The stored compiled literal this displayed atom stands for."""
    return group["literal"]

def _is_display_variable(term):
    """A displayed atom writes its open positions as `?X`, and nothing else."""
    return isinstance(term, str) and term.startswith("?") \
        and not term.startswith("?:")

def _standardise(term, index, names):
    """Rename this template's clause variables apart from every other atom's.

    Only `?:` clause variables: a template may also carry a constant that looks
    like a variable, such as the world `W0`.
    """
    if isinstance(term, str):
        if atoms.is_clause_variable(term):
            names.setdefault(term, "?:b%d_%d" % (index, len(names) + 1))
            return names[term]
        return term
    if isinstance(term, list) and term:
        return [term[0]] + [_standardise(x, index, names) for x in term[1:]]
    return term

def _substitute(term, subst):
    if isinstance(term, str):
        return subst.get(term, term)
    if isinstance(term, list) and term:
        return [term[0]] + [_substitute(x, subst) for x in term[1:]]
    return term

def _match_display(atom, group, index, rule_vars, bindings, generalised):
    """-> the literal this atom contributes, or raise FallbackError.

    Positional against the displayed atom: where the rule wrote one of its
    variables the template's slot becomes that variable, and where it wrote a
    constant the displayed constant must be the same one.  Each template's own
    variables are standardised apart first, so two atoms cannot share a name by
    accident.
    """
    display = group["atom"]
    template = atoms.unsigned_atom(_template_of(group))
    if str(atom[0]) != str(display[0]):
        raise FallbackError("`%s` is not the displayed predicate `%s`"
                            % (atom[0], display[0]))
    if len(atom) != len(display):
        raise FallbackError("`%s` has %d arguments, the displayed atom has %d"
                            % (atom[0], len(atom) - 1, len(display) - 1))
    n = _content_length(group)
    extra = list(template[1 + n:])
    if not all(atoms._is_context_argument(t) for t in extra):
        raise FallbackError("the stored literal carries a non-context "
                            "argument the fallback cannot rebuild: %s"
                            % json.dumps(extra))
    names = {}
    args = [_standardise(a, index, names) for a in template[1:1 + n]]
    label_slot = AO.LABEL_SLOT.get(str(display[0]))
    predicate = str(display[0])
    subst = {}
    for i, (written, shown) in enumerate(zip(atom[1:], display[1:])):
        slot = args[i]
        if isinstance(written, list) or isinstance(shown, list):
            if json.dumps(written) != json.dumps(shown):
                raise FallbackError("a nested argument of `%s` is not the "
                                    "displayed one" % predicate)
            continue
        if rules.is_rule_variable(written, rule_vars):
            mine = bindings.setdefault(written, "?:v_%s" % written)
            if _is_display_variable(shown):
                if not atoms.is_clause_variable(slot):
                    raise FallbackError("the displayed atom is open at "
                                        "argument %d of `%s` but its stored "
                                        "literal is not" % (i + 1, predicate))
                subst[slot] = mine
                continue
            if i == label_slot:
                raise FallbackError("a content label of `%s` cannot become a "
                                    "variable" % predicate)
            if _looks_like_a_world(slot):
                raise FallbackError("the world or context constant `%s` cannot "
                                    "become a variable" % slot)
            generalised.append({"predicate": predicate, "argument": i + 1,
                                "displayed_constant": shown,
                                "template_constant": slot,
                                "rule_variable": written})
            args[i] = mine
            continue
        if _is_display_variable(shown):
            raise FallbackError("`%s` was written where the displayed atom has "
                                "a variable" % written)
        if atoms._norm_constant(str(written)) != atoms._norm_constant(str(shown)):
            raise FallbackError("`%s` is not the displayed constant `%s`"
                                % (written, shown))
    args = [_substitute(a, subst) for a in args]
    # every trailing context slot becomes ONE shared clause variable, which is
    # what the base theory's own clauses carry and what the manually verified
    # `folio-0089` clause does
    return [template[0]] + args + [CONTEXT_VAR] * len(extra)

def _looks_like_a_world(term):
    return isinstance(term, str) and bool(AO._is_var(term)) \
        and not atoms.is_clause_variable(term)

def _generalises(atom, display, rule_vars):
    """Is `atom` the displayed atom with some constants replaced by variables?"""
    for written, shown in zip(atom[1:], display[1:]):
        if rules.is_rule_variable(written, rule_vars):
            continue
        if isinstance(written, list) or isinstance(shown, list):
            if json.dumps(written) != json.dumps(shown):
                return False
            continue
        if _is_display_variable(shown):
            return False
        if atoms._norm_constant(str(written)) != atoms._norm_constant(str(shown)):
            return False
    return True

def _content_literals(clauses):
    out = []
    for c in clauses or []:
        if c.get("@sourcetype") == "populate":
            continue
        for lit in atoms.literals_of(c.get("@logic")):
            if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                    and not atoms.is_control_predicate(lit[0]):
                out.append(lit)
    return out

def _clause_native_with_positive_blocker(rule, groups, hypothesis_id):
    """-> (clauses, record).  The exact clause this rule's own atoms describe."""
    rule_vars = rules.rule_variables(rule)
    bindings, generalised, used = {}, [], []

    def match(atom, index):
        """The displayed atom this one is, preferring the least generalised."""
        best, why = None, []
        for g in groups:
            if str(g["atom"][0]) != str(atom[0]) \
                    or len(g["atom"]) != len(atom):
                continue
            trial_b, trial_g = dict(bindings), []
            try:
                got = _match_display(atom, g, index, rule_vars, trial_b,
                                     trial_g)
            except FallbackError as e:
                why.append(str(e))
                continue
            if best is None or len(trial_g) < len(best[0]):
                best = (trial_g, g, got, trial_b)
        if best is None:
            raise FallbackError("no displayed atom matches %s%s"
                                % (json.dumps(atom)[:70],
                                   ": %s" % why[0] if why else ""))
        trial_g, g, got, trial_b = best
        bindings.update(trial_b)
        generalised.extend(trial_g)
        used.append(g.get("id"))
        return got

    literals = []
    for k, lit in enumerate(rule["body"], start=1):
        if lit["sign"] == "-":
            raise FallbackError("the fallback compiles positive premises only")
        got = match(lit["atom"], k)
        literals.append(["-" + atoms.bare_predicate(got[0])] + list(got[1:]))
    head = rule["head"]
    got = match(head["atom"], 0)
    if head["sign"] == "-":
        got = ["-" + atoms.bare_predicate(got[0])] + list(got[1:])
    body_vars = set()
    for lit in rule["body"]:
        body_vars |= set(rules.atom_variables(lit["atom"], rule_vars))
    free = set(rules.atom_variables(head["atom"], rule_vars)) - body_vars
    if free:
        raise FallbackError("the conclusion uses %s, which the body never binds"
                            % ", ".join(sorted(free)))
    literals.append(got)
    concl = literals[-1]
    block = ["$block", ["$", str(atoms.bare_predicate(concl[0])), 1],
             ["$not", copy.deepcopy(concl)]]
    clause = {"@name": BW.HYPOTHESIS_PROVENANCE % (hypothesis_id, 1),
              "@logic": literals + [block]}
    record = {"compiler_route": CLAUSE_NATIVE_ROUTE,
              "displayed_atoms_used": used,
              "generalised_constants": generalised,
              "clause_provenance": {clause["@name"]: hypothesis_id},
              "rule_clause_names": [clause["@name"]],
              "population_clause_names": [],
              "has_block": True,
              "bridge_evidence": None,
              "context_policy": "every trailing context argument became one "
                                "shared clause variable"}
    return [clause], record

class SignError(CompileError):
    """A route did not preserve the conclusion's sign."""

def _content_literals_of(clause):
    out = []
    for lit in atoms.literals_of(clause.get("@logic")):
        if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                and not atoms.is_control_predicate(lit[0]):
            out.append(lit)
    return out

def _agrees(literal, atom, rule, predicate):
    """Could this compiled literal be the one this rule atom compiled to?

    The predicate must be the displayed atom's compiled predicate, and every
    argument the rule wrote as a CONSTANT must appear unchanged in the same
    leading position.  Where the rule wrote one of its own variables anything
    may stand.  Trailing context arguments are ignored.
    """
    got = atoms.unsigned_atom(literal)
    if str(got[0]) != predicate:
        return False
    rule_vars = rules.rule_variables(rule)
    args = list(got[1:])
    for i, written in enumerate(atom[1:]):
        if i >= len(args):
            return False
        if rules.is_rule_variable(written, rule_vars):
            continue
        if isinstance(written, list) or isinstance(args[i], list):
            if json.dumps(written) != json.dumps(args[i]):
                return False
            continue
        if atoms._norm_constant(str(written)) != atoms._norm_constant(str(args[i])):
            return False
    return True

def _provenance(rule, clauses, groups, rule_clause_names, agrees=None):
    """-> the record fields that say which literal came from which rule part."""
    head_lit, rest, why = locate_head(clauses, rule, groups,
                                      rule_clause_names, agrees=agrees)
    body_groups = []
    for lit in rule["body"]:
        g = _displayed_for(lit["atom"], rule, groups)
        body_groups.append(g["id"] if g else None)
    ghead = _displayed_for(rule["head"]["atom"], rule, groups)
    return {"parsed_body": [{"sign": l["sign"], "atom": l["atom"]}
                            for l in rule["body"]],
            "parsed_head": {"sign": head_sign_of(rule),
                            "atom": rule["head"]["atom"]},
            "parsed_body_displayed_atoms": body_groups,
            "parsed_head_displayed_atom": ghead["id"] if ghead else None,
            "compiled_head_literal": head_lit,
            "compiled_body_literals": rest,
            "compiled_head_sign": atoms.sign_of(head_lit) if head_lit else None,
            "head_located": head_lit is not None,
            "head_not_located_why": why,
            "negative_conclusion": head_sign_of(rule) == "-"}

def compile_rule_clause_native(rule, groups, hypothesis_id):
    """v5.3's exact fallback, with the blocker built as the complement."""
    clauses, record = _clause_native_with_positive_blocker(rule, groups,
                                                     hypothesis_id)
    for clause in clauses:
        logic = clause["@logic"]
        concl = logic[-2]                      # the conclusion, then the block
        block = logic[-1]
        if not (isinstance(block, list) and block and block[0] == "$block"):
            raise CompileError("the fallback clause has no $block to correct")
        logic[-1] = ["$block", block[1], complement(concl)]
    record["blocker_policy"] = ("the blocker is the complement of the "
                                "conclusion: `$not(HEAD)` for a positive "
                                "conclusion, the positive atom for a negative "
                                "one")
    return clauses, record

def _check_sign(rule, rec):
    """A route that changes or drops the conclusion's sign refuses the rule."""
    got = (rec.get("signed") or {})
    if not got.get("head_located"):
        raise SignError("the compiled clause has no literal for the "
                        "conclusion: %s" % got.get("head_not_located_why"))
    if got.get("compiled_head_sign") != head_sign_of(rule):
        raise SignError("the compiled conclusion is `%s` where the rule wrote "
                        "`%s`" % (got.get("compiled_head_sign"),
                                  head_sign_of(rule)))

def _compile_one_with_fallback(rule, view, configuration, groups=(), case_id=None,
                world_name="probe", package_id="A1", hypothesis_id=None):
    """-> (clauses, record).  The normal route, else the exact fallback."""
    case_id = case_id or view.get("case_id") or "case"
    hypothesis_id = hypothesis_id or "%s::%s" % (case_id, rule["rule_id"])
    normal_error = None
    try:
        pkg = simple_rule_to_package(rule)
        clauses, rec = BW.compile_bridge(
            case_id, world_name, pkg, view["stage1"], view["stage2"],
            configuration, bridge_evidence=BW.RUNTIME_EVIDENCE,
            package_id=package_id, base_clauses=view.get("final_clauses"),
            hypothesis_id=hypothesis_id)
        ok, why = _normal_route_is_faithful(clauses, rule, groups)
        if ok:
            head_lit, _rest, why_head = locate_head(
                clauses, rule, groups, rec.get("rule_clause_names"))
            if head_lit is None:
                normal_error = why_head
            else:
                rec["compiler_route"] = NORMAL_ROUTE
                rec["signed"] = _provenance(rule, clauses, groups,
                                            rec.get("rule_clause_names"))
                _check_sign(rule, rec)
                return clauses, rec
        else:
            normal_error = why
    except BW.BridgeError as e:
        normal_error = str(e)[:200]
    except SignError:
        raise
    except Exception as e:                                      # noqa: BLE001
        normal_error = "the converter raised %s: %s" % (type(e).__name__,
                                                        str(e)[:160])
    clauses, rec = compile_rule_clause_native(rule, groups, hypothesis_id)
    rec["normal_route_refusal"] = normal_error
    rec["signed"] = _provenance(rule, clauses, groups,
                                rec.get("rule_clause_names"))
    _check_sign(rule, rec)
    return clauses, rec

def _build_world_base(world_id, rules, view, configuration, groups=(), weight=1.0,
                redundancy=None):
    """v5.3's world, compiled through the signed `compile_one`.

    Identical to `simple_rule_compiler_v5_3.build_world` except that it calls
    this module's compiler, refuses a sign change by name, and counts positive
    and negative conclusions.
    """
    if not rules:
        raise CompileError("a bridge set needs at least one rule")
    hyps, clauses, provenance, entries, refused = [], [], {}, [], []
    for r in rules:
        hid = "%s::%s" % (view["case_id"], r["rule_id"])
        try:
            cl, rec = compile_one(r, view, configuration, groups=groups,
                                  case_id=view["case_id"],
                                  world_name=world_id,
                                  package_id="A%d" % (len(entries) + 1),
                                  hypothesis_id=hid)
        except SignError as e:
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": str(e)[:200], "kind": "sign_not_preserved"})
            continue
        except FallbackError as e:
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": str(e)[:200], "kind": "fallback_refusal"})
            continue
        except BW.BridgeError as e:
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": str(e)[:200], "kind": "compiler_refusal"})
            continue
        except Exception as e:                                  # noqa: BLE001
            refused.append({"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": "the converter raised %s: %s"
                                   % (type(e).__name__, str(e)[:160]),
                            "kind": "converter_error"})
            continue
        if redundancy is not None:
            already = redundancy(r, cl)
            if already:
                refused.append({"rule_id": r["rule_id"],
                                "printed": r["printed"], "why": already,
                                "kind": "already_present"})
                continue
        clauses.extend(cl)
        provenance.update(rec["clause_provenance"])
        try:
            package = simple_rule_to_package(r)
        except Exception:                                       # noqa: BLE001
            package = None
        signed = rec.get("signed") or {}
        h = {"hypothesis_id": hid, "rule_id": r["rule_id"], "weight": weight,
             "label": r["rule_id"], "origin": r.get("origin"),
             "warnings": r.get("warnings") or [],
             "package": package,
             "printed_formula": r["printed"],
             "compiler_route": rec.get("compiler_route"),
             "normal_route_refusal": rec.get("normal_route_refusal"),
             "generalised_constants": rec.get("generalised_constants"),
             "displayed_atoms_used": rec.get("displayed_atoms_used"),
             "compiled_clauses": cl,
             "clause_names": [c["@name"] for c in cl],
             "rule_clause_names": rec["rule_clause_names"],
             "has_block": rec["has_block"],
             "bridge_evidence": rec["bridge_evidence"],
             "head_sign": head_sign_of(r),
             "negative_conclusion": signed.get("negative_conclusion"),
             "head_literal": signed.get("compiled_head_literal"),
             "body_literals": signed.get("compiled_body_literals"),
             "parsed_head": signed.get("parsed_head"),
             "parsed_body": signed.get("parsed_body"),
             "head_displayed_atom": signed.get("parsed_head_displayed_atom"),
             "body_displayed_atoms":
                 signed.get("parsed_body_displayed_atoms")}
        entries.append(h)
        hyps.append(h)
    negative = [h["rule_id"] for h in hyps if h["negative_conclusion"]]
    return {
        "world_id": world_id,
        "bridge_hypotheses": entries,
        "compiled_bridge_clauses": clauses,
        "clause_provenance": provenance,
        "weights": dict((h["hypothesis_id"], weight) for h in hyps),
        "rule_by_hypothesis_id": dict((h["hypothesis_id"], h["rule_id"])
                                      for h in hyps),
        "printed_by_hypothesis_id": dict((h["hypothesis_id"],
                                          h["printed_formula"])
                                         for h in hyps),
        "hypotheses_in_this_world": [h["hypothesis_id"] for h in hyps],
        "refused_by_the_compiler": refused,
        "nothing_compiled": not hyps,
        "compiler_routes": dict((h["rule_id"], h["compiler_route"])
                                for h in hyps),
        "negative_conclusion_rules": negative,
        "signed_counts": {"compiled": len(hyps),
                          "positive_conclusion": len(hyps) - len(negative),
                          "negative_conclusion": len(negative)},
        "runtime_clause_policy": (
            "guarded, defeasible ($block), full confidence; no weight is "
            "applied to a clause or to a proof"),
    }

class TemplateError(FallbackError):
    """A rule atom cannot be rebuilt from the candidate it was copied from."""

    def __init__(self, reason, detail):
        FallbackError.__init__(self, "%s: %s" % (reason, detail))
        self.reason = reason
        self.detail = detail

def _display_shape(term):
    return json.dumps(term, sort_keys=True)

def _canonical(literals):
    return sorted(json.dumps(l, sort_keys=True)
                  for l in _standardise_clause(literals))

