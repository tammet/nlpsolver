"""Compiling a v5.3 rule: only `?` names are quantified, plus an exact
clause-native fallback (WP6.1, WP6.3).

Two differences from `simple_rule_compiler_v4`, and nothing in v1-v5.2 changes.

**Quantification follows the rule's own variables.**  `simple_rule_compiler_v3`
quantifies every capitalised token, so a rule mentioning the world constant `W0`
would be turned into a statement about all worlds.  Here the package quantifies
exactly the `?` names the model wrote, which the v5.3 parser records.

**A clause-native fallback.**  The Stage-2 bridge converter cannot express some
things the clauses plainly contain: in `folio-0089` the question clause holds
`is rel2(smart, #:Harry 1, W0, C)` with `W0` a constant, and the corresponding
Stage-2 package converts to no clause at all.  When the normal route produces no
clause, or produces content literals that are not the ones the rule's own
displayed atoms compile to, the fallback assembles the clause directly from
those stored templates.

The fallback is not a raw-clause escape hatch:

  * every premise and conclusion must match exactly one displayed candidate
    group, and the clause is built from that group's stored compiled literal.
    An atom that matches nothing refuses the rule;
  * the rule's `?` correspondence is applied positionally against the displayed
    atom.  Where the displayed atom has a constant and the rule wrote one of its
    variables, that template position becomes the variable -- the same
    object-constant generalisation the prompt already permits -- and it is
    refused in a content-label slot and recorded everywhere else;
  * a premise is negated and the conclusion keeps its sign;
  * trailing context arguments become ONE shared context variable for the whole
    clause, which is what the base theory's own clauses do;
  * a conclusion variable no premise binds refuses the rule;
  * a `$block` is added for the conclusion, no population clause is emitted and
    no `@confidence` is written.
"""

import copy
import json

import alignment_occurrences as AO
import bridge_world as BW
import simple_rule_compiler as SC
import simple_rule_compiler_v3 as C3
import simple_rule_compiler_v4 as C4
import simple_rule_parser_v5_3 as P53
import unifier_abstraction as UA

VERSION = "simple_rule_compiler_v5_3/1.0"

WORLD = C3.WORLD
CompileError = C3.CompileError

NORMAL_ROUTE = "stage2_bridge_converter"
FALLBACK_ROUTE = "clause_native_fallback"

CONTEXT_VAR = "?:Cbridge"


class FallbackError(CompileError):
    """The exact clause-native compiler refuses this rule."""


# --------------------------------------------------- WP6.1: the normal route

def simple_rule_to_package(rule, world=WORLD):
    """-> `["holds", W, forall ?vars . BODY -> normally(HEAD)]`.

    Only the rule's own `?` variables are quantified; every other token is a
    constant of the passage.
    """
    if not rule.get("body") or not rule.get("head"):
        raise CompileError("a rule needs a body and one conclusion")
    lits = [SC._literal(l) for l in rule["body"]]
    body = lits[0] if len(lits) == 1 else ["and"] + lits
    inner = ["implies", body, ["normally", SC._literal(rule["head"])]]
    for v in reversed(P53.rule_variables(rule)):
        inner = ["forall", v, inner]
    pkg = ["holds", world, inner]
    if BW.to_defeasible_shape(pkg) != pkg:
        raise CompileError("the built package is not in defeasible shape")
    return pkg


def hypothesis(rule, case_id, weight=1.0):
    return {"hypothesis_id": "%s::%s" % (case_id, rule["rule_id"]),
            "label": rule["rule_id"], "weight": weight, "case_id": case_id,
            "package": simple_rule_to_package(rule),
            "printed_formula": rule["printed"], "rule_id": rule["rule_id"],
            "canonical": rule["canonical"], "origin": rule.get("origin"),
            "warnings": rule.get("warnings") or []}


# ------------------------------------------------- WP6.3: the exact fallback

def _content_length(group):
    return len(group["atom"]) - 1


def _template_of(group):
    """The stored compiled literal this displayed atom stands for."""
    return group["literal"]


def _is_context_argument(term):
    if isinstance(term, str):
        return UA.is_variable_term(term) or term == "$c"
    return isinstance(term, list) and bool(term) and str(term[0]) == "$ctxt"


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
        if UA.is_clause_variable(term):
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
    template = UA.unsigned_atom(_template_of(group))
    if str(atom[0]) != str(display[0]):
        raise FallbackError("`%s` is not the displayed predicate `%s`"
                            % (atom[0], display[0]))
    if len(atom) != len(display):
        raise FallbackError("`%s` has %d arguments, the displayed atom has %d"
                            % (atom[0], len(atom) - 1, len(display) - 1))
    n = _content_length(group)
    extra = list(template[1 + n:])
    if not all(_is_context_argument(t) for t in extra):
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
        if P53.is_rule_variable(written, rule_vars):
            mine = bindings.setdefault(written, "?:v_%s" % written)
            if _is_display_variable(shown):
                if not UA.is_clause_variable(slot):
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
        if UA._norm_constant(str(written)) != UA._norm_constant(str(shown)):
            raise FallbackError("`%s` is not the displayed constant `%s`"
                                % (written, shown))
    args = [_substitute(a, subst) for a in args]
    # every trailing context slot becomes ONE shared clause variable, which is
    # what the base theory's own clauses carry and what the manually verified
    # `folio-0089` clause does
    return [template[0]] + args + [CONTEXT_VAR] * len(extra)


def _looks_like_a_world(term):
    return isinstance(term, str) and bool(AO._is_var(term)) \
        and not UA.is_clause_variable(term)


def compile_rule_clause_native(rule, groups, hypothesis_id):
    """-> (clauses, record).  The exact clause this rule's own atoms describe."""
    rule_vars = P53.rule_variables(rule)
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
        literals.append(["-" + UA.bare_predicate(got[0])] + list(got[1:]))
    head = rule["head"]
    got = match(head["atom"], 0)
    if head["sign"] == "-":
        got = ["-" + UA.bare_predicate(got[0])] + list(got[1:])
    body_vars = set()
    for lit in rule["body"]:
        body_vars |= set(P53.atom_variables(lit["atom"], rule_vars))
    free = set(P53.atom_variables(head["atom"], rule_vars)) - body_vars
    if free:
        raise FallbackError("the conclusion uses %s, which the body never binds"
                            % ", ".join(sorted(free)))
    literals.append(got)
    concl = literals[-1]
    block = ["$block", ["$", str(UA.bare_predicate(concl[0])), 1],
             ["$not", copy.deepcopy(concl)]]
    clause = {"@name": BW.HYPOTHESIS_PROVENANCE % (hypothesis_id, 1),
              "@logic": literals + [block]}
    record = {"compiler_route": FALLBACK_ROUTE,
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


def _generalises(atom, display, rule_vars):
    """Is `atom` the displayed atom with some constants replaced by variables?"""
    for written, shown in zip(atom[1:], display[1:]):
        if P53.is_rule_variable(written, rule_vars):
            continue
        if isinstance(written, list) or isinstance(shown, list):
            if json.dumps(written) != json.dumps(shown):
                return False
            continue
        if _is_display_variable(shown):
            return False
        if UA._norm_constant(str(written)) != UA._norm_constant(str(shown)):
            return False
    return True


# ------------------------------------------------------------- the two routes

def _content_literals(clauses):
    out = []
    for c in clauses or []:
        if c.get("@sourcetype") == "populate":
            continue
        for lit in UA.literals_of(c.get("@logic")):
            if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                    and not UA.is_control_predicate(lit[0]):
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
        if P53.alpha_equivalent(g["atom"], head) or _generalises(
                head, g["atom"], P53.rule_variables(rule)):
            want = g
            break
    if want is None:
        return True, None                       # nothing to compare against
    n = len(want["atom"]) - 1
    target = UA.unsigned_atom(want["literal"])
    for l in lits:
        if UA.sign_of(l) != rule["head"]["sign"]:
            continue
        atom = UA.unsigned_atom(l)
        if str(atom[0]) != str(target[0]) or len(atom) - 1 < n:
            continue
        return True, None
    return False, ("no converted literal has the conclusion's displayed "
                   "predicate `%s`" % target[0])


def compile_one(rule, view, configuration, groups=(), case_id=None,
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
            rec["compiler_route"] = NORMAL_ROUTE
            return clauses, rec
        normal_error = why
    except BW.BridgeError as e:
        normal_error = str(e)[:200]
    except Exception as e:                                      # noqa: BLE001
        normal_error = "the converter raised %s: %s" % (type(e).__name__,
                                                        str(e)[:160])
    clauses, rec = compile_rule_clause_native(rule, groups, hypothesis_id)
    rec["normal_route_refusal"] = normal_error
    return clauses, rec


def build_world(world_id, rules, view, configuration, groups=(), weight=1.0,
                redundancy=None):
    """Every rule of a bridge set, compiled separately into one gk submission."""
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
             "bridge_evidence": rec["bridge_evidence"]}
        entries.append(h)
        hyps.append(h)
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
        "runtime_clause_policy": (
            "guarded, defeasible ($block), full confidence; no weight is "
            "applied to a clause or to a proof"),
    }


clause_facts = C4.clause_facts
literals = C4.literals
