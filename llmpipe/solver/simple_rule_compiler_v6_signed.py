"""Compiling a rule whose conclusion may be negated, with explicit provenance.

The two routes are v5.3's and are called here: the Stage-2 bridge converter
first, the exact clause-native fallback when the conversion produces no clause
or a clause that does not carry the conclusion the model wrote.  Both already
carry a signed head — `simple_rule_compiler._literal` wraps a negative literal
in `not`, and `compile_rule_clause_native` negates the conclusion — so this
module adds no parallel clause format.  It adds three things:

**A correct blocker for a negative conclusion.**  A `$block` names the literal
whose derivation defeats the default.  For a positive conclusion that is
`$not(HEAD)`; for a negative one it is the positive atom itself.  The fallback
wrote `$not` around an already negative literal, which the converter's own route
never produces.  Here both routes emit the complement.

**Head and body provenance.**  Downstream code has read a bridge clause's body
as its negative literals and its head as its positive one.  For

    ["isa","bee","?X"] -> NOT ["isa","vertebrate","?X"]

the clause is `[-isa(bee,X), -isa(vertebrate,X)]` and that reading is wrong, so
the compiler records which compiled literal came from the parsed head, which
came from each premise, and which displayed atom each one stands for.

**A sign check that refuses rather than repairs.**  If the compiled conclusion's
sign is not the parsed conclusion's sign, the rule is refused; no route may
silently drop or flip it.

For a positive rule every clause this module produces is byte-identical to
v5.3's.
"""

import copy
import json

import bridge_world as BW
import simple_rule_compiler_v5_3 as C53
import simple_rule_parser_v5_3 as P53
import unifier_abstraction as UA

VERSION = "simple_rule_compiler_v6_signed/1.0"

WORLD = C53.WORLD
CompileError = C53.CompileError
FallbackError = C53.FallbackError
NORMAL_ROUTE = C53.NORMAL_ROUTE
FALLBACK_ROUTE = C53.FALLBACK_ROUTE
CONTEXT_VAR = C53.CONTEXT_VAR

simple_rule_to_package = C53.simple_rule_to_package
hypothesis = C53.hypothesis
clause_facts = C53.clause_facts
literals = C53.literals


class SignError(CompileError):
    """A route did not preserve the conclusion's sign."""


# ------------------------------------------------------------- signed helpers

def head_sign_of(rule):
    return (rule.get("head") or {}).get("sign") or "+"


def complement(literal):
    """The literal whose derivation defeats this conclusion as a default."""
    if UA.sign_of(literal) == "-":
        return [UA.bare_predicate(literal[0])] + list(literal[1:])
    return ["$not", copy.deepcopy(literal)]


def _content_literals_of(clause):
    out = []
    for lit in UA.literals_of(clause.get("@logic")):
        if isinstance(lit, list) and lit and isinstance(lit[0], str) \
                and not UA.is_control_predicate(lit[0]):
            out.append(lit)
    return out


def _displayed_for(atom, rule, groups):
    """The displayed group this rule atom stands for, if there is one.

    An exact match wins over one the rule generalised, so the recorded
    provenance names the atom the model actually copied.
    """
    rule_vars = P53.rule_variables(rule)
    for g in groups or []:
        if P53.alpha_equivalent(g["atom"], atom):
            return g
    for g in groups or []:
        if C53._generalises(atom, g["atom"], rule_vars):
            return g
    return None


def _template_predicate(atom, rule, groups):
    g = _displayed_for(atom, rule, groups)
    if g is None:
        return str(atom[0])
    return str(UA.unsigned_atom(g["literal"])[0])


def _agrees(literal, atom, rule, predicate):
    """Could this compiled literal be the one this rule atom compiled to?

    The predicate must be the displayed atom's compiled predicate, and every
    argument the rule wrote as a CONSTANT must appear unchanged in the same
    leading position.  Where the rule wrote one of its own variables anything
    may stand.  Trailing context arguments are ignored.
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
            if json.dumps(written) != json.dumps(args[i]):
                return False
            continue
        if UA._norm_constant(str(written)) != UA._norm_constant(str(args[i])):
            return False
    return True


def locate_head(clauses, rule, groups, rule_clause_names=()):
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
             if UA.sign_of(l) == want_sign
             and _agrees(l, rule["head"]["atom"], rule, predicate)]
    if not cands:
        return None, lits, ("no converted literal has the conclusion's "
                            "displayed predicate `%s` with sign `%s`"
                            % (predicate, want_sign))
    head = cands[-1]
    rest = [l for l in lits if l is not head]
    return head, rest, None


def _provenance(rule, clauses, groups, rule_clause_names):
    """-> the record fields that say which literal came from which rule part."""
    head_lit, rest, why = locate_head(clauses, rule, groups,
                                      rule_clause_names)
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
            "compiled_head_sign": UA.sign_of(head_lit) if head_lit else None,
            "head_located": head_lit is not None,
            "head_not_located_why": why,
            "negative_conclusion": head_sign_of(rule) == "-"}


# --------------------------------------------------- the clause-native route

def compile_rule_clause_native(rule, groups, hypothesis_id):
    """v5.3's exact fallback, with the blocker built as the complement."""
    clauses, record = C53.compile_rule_clause_native(rule, groups,
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


# ------------------------------------------------------------- the two routes

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
        ok, why = C53._normal_route_is_faithful(clauses, rule, groups)
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


# ------------------------------------------------------------------ one world

def build_world(world_id, rules, view, configuration, groups=(), weight=1.0,
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
