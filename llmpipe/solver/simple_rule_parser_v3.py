"""The `RULE:` language, v3 validation (WP4).

The grammar, the scanner, the variable normalisation, the canonical form and the
printer are the frozen v2 ones and are imported, not copied.  What changes is
what the validator does with three things the audit showed it got wrong:

  * **Generalising an observed constant is no longer a refusal.**  In
    `folio-0169` every proposed rule died because the passage happened to name
    its members, so `member of(X,Y) -> part of(X,Y)` never reached gk.  It is
    now kept with the warning `generalizes_observed_constants`, and up to three
    GROUNDED specializations are built beside it from real matches against the
    displayed atoms — never from a cross-product of constants.

  * **A nested term the model was shown may be copied.**  `eb2-0121` displayed
    a `$setof(...)` term and then refused every rule that used it.  A nested
    argument is now accepted exactly when it is alpha-equivalent to a nested
    structure that appeared in the candidate list: bound variables may be
    renamed, a functor may not be invented, and constants inside the structure
    may not be swapped.  A variable a set binder declares is LOCAL to that term
    and is not a free rule variable.

  * **A rule already in the theory is refused for that reason.**  The
    `recessive trait(X) -> trait(X)` line was refused in `eb2-0039` with an
    incidental message about a constant; it is in fact already a `compound_sub`
    clause, which `rule_redundancy_v3` now says.

Everything else the v2 validator refused, it still refuses: a control
predicate, equality, an unknown predicate or arity, a variable in a content
label slot, a conclusion variable no premise binds, a tautology, and a
restatement of a rule the passage already gives.
"""

import copy
import json

import alignment_occurrences as AO
import simple_rule_parser as SP
import unifier_abstraction as UA
import unifier_candidates_v3 as CV

VERSION = "simple_rule_parser_v3/1.0"

MAX_BODY_LITERALS = SP.MAX_BODY_LITERALS
MAX_RULES_PER_CALL = 12
MAX_GROUND_SPECIALIZATIONS = 3

LLM_GENERAL = "llm_general"
GROUND_SPECIALIZATION = "system_ground_specialization"

WARN_GENERALIZES = "generalizes_observed_constants"

FORBIDDEN_WORDS = SP.FORBIDDEN_WORDS


# ---------------------------------------------------------------- vocabulary

def _walk_terms(term, fn):
    fn(term)
    if isinstance(term, list):
        for x in term[1:]:
            _walk_terms(x, fn)


def nested_shapes(atom):
    """Every nested (list) argument of an atom, at any depth."""
    out = []

    def go(t):
        if isinstance(t, list):
            for x in t[1:]:
                if isinstance(x, list):
                    out.append(x)
                    go(x)
    go(atom)
    return out


def constants_in(atom):
    """Every non-variable string inside an atom, nested structures included."""
    out = set()

    def go(t):
        if isinstance(t, str):
            if not UA.is_variable_term(t):
                out.add(t)
            return
        if isinstance(t, list) and t:
            for x in t[1:]:
                go(x)
    for a in atom[1:]:
        go(a)
    return out


def alpha_equivalent(a, b):
    """Equal up to a consistent renaming of variables.  Constants are exact."""
    mapping, back = {}, {}

    def go(x, y):
        vx = isinstance(x, str) and UA.is_variable_term(x)
        vy = isinstance(y, str) and UA.is_variable_term(y)
        if vx or vy:
            if not (vx and vy):
                return False
            if mapping.get(x, y) != y or back.get(y, x) != x:
                return False
            mapping[x], back[y] = y, x
            return True
        if isinstance(x, str) or isinstance(y, str):
            return x == y
        if not (isinstance(x, list) and isinstance(y, list)):
            return False
        if len(x) != len(y) or x[0] != y[0]:
            return False
        return all(go(p, q) for p, q in zip(x[1:], y[1:]))
    return go(a, b)


CONNECTIVES = ("and", "or", "not", "xor", "implies", "=", "$and", "$or",
               "$not") + CV.SET_BINDERS


def _inner_atoms(atom):
    """Atoms nested inside a displayed structure, e.g. inside a `$setof` body.

    Without this, `object` in `eb2-0121`'s set term is invisible to the
    vocabulary and a rule copying that term is refused for using a word it was
    shown.
    """
    out = []

    def go(t, top):
        if not isinstance(t, list) or not t or not isinstance(t[0], str):
            return
        if t[0] not in CONNECTIVES and not top:
            out.append(t)
        start = 2 if t[0] in CV.SET_BINDERS else 1
        for x in t[start:]:
            go(x, False)
    go(atom, True)
    return out


def vocabulary(candidates):
    """What the displayed candidates license, nested structures included."""
    preds, arities, label_slots = {}, {}, {}
    constants, shapes, atoms = set(), [], []
    labels = {}

    def register(atom):
        pred = str(atom[0])
        args = list(atom[1:])
        preds.setdefault(pred, set()).add(len(args))
        arities.setdefault(pred, set()).add(len(args))
        slot = AO.LABEL_SLOT.get(pred)
        if slot is not None and slot < len(args) \
                and not UA.is_variable_term(args[slot]) \
                and isinstance(args[slot], str):
            label_slots.setdefault(pred, set()).add(slot)
            labels.setdefault(pred, set()).add(str(args[slot]))

    for row in candidates:
        atom = row["surface_atom"]
        register(atom)
        for inner in _inner_atoms(atom):
            register(inner)
        constants |= constants_in(atom)
        for shape in nested_shapes(atom):
            if not any(alpha_equivalent(shape, s) for s in shapes):
                shapes.append(shape)
        atoms.append({"id": row.get("id"), "atom": atom, "sign": row["sign"],
                      "role": row["role"],
                      "priority_cost": row["priority_cost"]})
    return {"predicates": dict((p, sorted(v)) for p, v in preds.items()),
            "arities": dict((p, sorted(v)) for p, v in arities.items()),
            "constants": sorted(constants),
            "label_slots": dict((p, sorted(v)) for p, v in label_slots.items()),
            "labels_per_predicate": dict((p, sorted(v))
                                         for p, v in labels.items()),
            "nested_shapes": shapes,
            "atoms": atoms}


# ---------------------------------------------------------------- validation

def free_variables_of(rule):
    """The rule's free variables: set-binder variables are local, not free."""
    out = []
    for lit in rule["body"] + [rule["head"]]:
        for v in CV.free_variables(lit["atom"]):
            if v not in out:
                out.append(v)
    return out


def _atom_free_vars(atom):
    return CV.free_variables(atom)


def validate(rule, vocab, source_rule_keys=()):
    """-> (refusals, warnings).  Refusals are mechanical; warnings are kept."""
    why, warn = [], []
    body, head = rule["body"], rule["head"]
    if not body:
        why.append("no body literal")
    if len(body) > MAX_BODY_LITERALS:
        why.append("more than %d body literals" % MAX_BODY_LITERALS)
    preds, arities = vocab["predicates"], vocab["arities"]
    constants = set(vocab["constants"])
    label_slots = vocab["label_slots"]
    for lit in body + [head]:
        atom = lit["atom"]
        pred = str(atom[0])
        args = list(atom[1:])
        if UA.is_control_predicate(pred):
            why.append("control predicate `%s`" % pred)
            continue
        if UA.is_equality_predicate(pred):
            why.append("equality is not part of this experiment")
            continue
        if pred.lower() in FORBIDDEN_WORDS:
            why.append("asserts `%s`" % pred)
            continue
        if pred not in preds:
            why.append("predicate `%s` was never displayed" % pred)
            continue
        if len(args) not in arities.get(pred, ()):
            why.append("arity %d was never displayed for `%s`"
                       % (len(args), pred))
            continue
        for i, a in enumerate(args):
            if isinstance(a, list):
                if not any(alpha_equivalent(a, s)
                           for s in vocab["nested_shapes"]):
                    why.append("a nested term that was never displayed: %s"
                               % json.dumps(a)[:80])
                continue
            if UA.is_variable_term(a):
                if i in label_slots.get(pred, ()):
                    why.append("a variable in the content-label position of "
                               "`%s`" % pred)
                continue
            if a in FORBIDDEN_WORDS:
                why.append("asserts `%s`" % a)
                continue
            if a not in constants:
                why.append("`%s` was never displayed" % a)
            elif i in label_slots.get(pred, ()) and \
                    a not in vocab.get("labels_per_predicate", {}).get(pred,
                                                                      ()):
                why.append("`%s` was never displayed as a content label of "
                           "`%s`" % (a, pred))
    body_vars = set()
    for lit in body:
        body_vars |= set(_atom_free_vars(lit["atom"]))
    free = set(_atom_free_vars(head["atom"])) - body_vars
    if free:
        why.append("the conclusion uses %s, which the body never binds"
                   % ", ".join(sorted(free)))
    cbody, chead = SP.canonical_parts(rule)
    if chead in cbody:
        why.append("a tautology: the conclusion is one of its own premises")
    key = json.dumps([cbody, chead], sort_keys=True)
    if key in set(source_rule_keys):
        why.append("identical to a rule the passage already states")
    if not why and generalizes_observed_constants(rule, vocab):
        warn.append(WARN_GENERALIZES)
    return why, warn


def generalizes_observed_constants(rule, vocab):
    """Did the model put a variable where every displayed atom had a constant?

    A warning, never a refusal: the rule stays range restricted and mechanically
    sound, and whether the generalisation is true is a question for the grader
    after a proof, not for the parser before one.
    """
    for lit in rule["body"] + [rule["head"]]:
        atom = lit["atom"]
        pred = str(atom[0])
        args = list(atom[1:])
        shown = [r["atom"] for r in vocab["atoms"]
                 if str(r["atom"][0]) == pred and len(r["atom"]) == len(atom)]
        if not shown:
            continue
        for i, a in enumerate(args):
            if not (isinstance(a, str) and UA.is_variable_term(a)):
                continue
            if AO.LABEL_SLOT.get(pred) == i:
                continue
            values = [s[i + 1] for s in shown]
            if values and all(isinstance(v, str) and not UA.is_variable_term(v)
                              for v in values):
                return True
    return False


# ----------------------------------------------------- ground specializations

def _match_atom(atom, ground, subst):
    """Match a rule atom against a displayed ground atom.  -> new subst | None."""
    if str(atom[0]) != str(ground[0]) or len(atom) != len(ground):
        return None
    out = dict(subst)

    def go(x, y):
        if isinstance(x, str) and UA.is_variable_term(x):
            if x in out:
                return json.dumps(out[x]) == json.dumps(y)
            out[x] = y
            return True
        if isinstance(x, str) or isinstance(y, str):
            return x == y
        if not (isinstance(x, list) and isinstance(y, list)):
            return False
        if len(x) != len(y) or x[0] != y[0]:
            return False
        return all(go(p, q) for p, q in zip(x[1:], y[1:]))
    for p, q in zip(atom[1:], ground[1:]):
        if not go(p, q):
            return None
    return out


def _apply(atom, subst):
    def go(t):
        if isinstance(t, str):
            return copy.deepcopy(subst[t]) if t in subst else t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def ground_specializations(rule, vocab, cap=MAX_GROUND_SPECIALIZATIONS):
    """Up to `cap` grounded variants, from REAL matches of the whole body.

    The substitutions come from matching each body literal against displayed
    ground atoms and joining them consistently.  No cross-product of constants
    is ever formed: a substitution that does not match every body literal at
    once is not produced.
    """
    ground_atoms = [r["atom"] for r in vocab["atoms"]
                    if not CV.free_variables(r["atom"])]
    if not ground_atoms:
        return []
    results, budget = [], [400]

    def walk(i, subst):
        if len(results) >= cap or budget[0] <= 0:
            return
        if i >= len(rule["body"]):
            if subst:
                results.append(dict(subst))
            return
        atom = rule["body"][i]["atom"]
        for g in ground_atoms:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            got = _match_atom(atom, g, subst)
            if got is not None:
                walk(i + 1, got)
    walk(0, {})
    out, seen = [], set()
    for subst in results:
        body = [{"sign": l["sign"], "atom": _apply(l["atom"], subst)}
                for l in rule["body"]]
        head = {"sign": rule["head"]["sign"],
                "atom": _apply(rule["head"]["atom"], subst)}
        variant = {"body": body, "head": head}
        key = SP.canonical(variant)
        if key == SP.canonical(rule) or key in seen:
            continue
        seen.add(key)
        variant["canonical"] = key
        variant["printed"] = SP._safe_printed(variant)
        variant["substitution"] = dict((k, v) for k, v in subst.items())
        out.append(variant)
    return out[:cap]


# ------------------------------------------------------------ rule priority

def rule_candidates(rule, vocab):
    """-> (matched candidate ids per literal, unmatched atoms, total cost).

    A rule's cost is the sum of its literals' candidate costs.  It orders pools
    and never rejects anything; an atom that matches no candidate is named.
    """
    matched, unmatched, total = [], [], 0
    for lit in rule["body"] + [rule["head"]]:
        want = lit["atom"]
        best = None
        for row in vocab["atoms"]:
            if row["sign"] != lit["sign"]:
                continue
            if alpha_equivalent(row["atom"], want):
                best = row
                break
        if best is None:
            for row in vocab["atoms"]:
                if row["sign"] != lit["sign"]:
                    continue
                if UA.unify_unsigned_atoms(
                        _clause_shape(row["atom"]),
                        _clause_shape(want))["unifiable"]:
                    best = row
                    break
        if best is None:
            unmatched.append(SP._safe_printed({"body": [lit], "head": lit}))
            continue
        matched.append({"literal": SP.printed({"body": [lit], "head": lit}
                                              ).split(" -> ")[0],
                        "candidate": best["id"], "role": best["role"],
                        "priority_cost": best["priority_cost"]})
        total += best["priority_cost"]
    return matched, unmatched, total


def _clause_shape(atom):
    names = {}

    def go(t):
        if isinstance(t, str) and UA.is_variable_term(t):
            names.setdefault(t, "?:R%d" % (len(names) + 1))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def role_fit(rule, vocab):
    """Do the rule's premises sit in PREMISE/BOTH and its head in CONSEQUENCE?"""
    def role_for(lit):
        for row in vocab["atoms"]:
            if row["sign"] == lit["sign"] and alpha_equivalent(row["atom"],
                                                               lit["atom"]):
                return row["role"]
        for row in vocab["atoms"]:
            if row["sign"] == lit["sign"] and UA.unify_unsigned_atoms(
                    _clause_shape(row["atom"]),
                    _clause_shape(lit["atom"]))["unifiable"]:
                return row["role"]
        return None
    body_ok = all(role_for(l) in (CV.PREMISE, CV.BOTH) for l in rule["body"])
    head_ok = role_for(rule["head"]) in (CV.CONSEQUENCE, CV.BOTH)
    return {"body_roles": [role_for(l) for l in rule["body"]],
            "head_role": role_for(rule["head"]),
            "body_fits": body_ok, "head_fits": head_ok,
            "fits": bool(body_ok and head_ok)}


# ------------------------------------------------------------------ parsing

def parse_response(text, vocab, source_rules=(), max_rules=MAX_RULES_PER_CALL,
                   start_index=1, existing=()):
    """-> the v3 parse: accepted rules, their variants, refusals and warnings."""
    lines = (text or "").splitlines()
    rule_lines = [l for l in lines if SP.RULE_PREFIX.match(l)]
    keys = set(SP.canonical(r) for r in source_rules or [])
    seen = dict((r["canonical"], r) for r in existing)
    accepted, rejected, over_cap = [], [], []
    n = [start_index - 1]

    def fresh_id():
        n[0] += 1
        return "R%d" % n[0]

    for raw in rule_lines:
        line = raw.strip()
        try:
            parsed = SP.parse_line(line)
        except SP.RuleError as e:
            rejected.append({"line": line[:220], "reasons": [str(e)]})
            continue
        rule = SP.to_stage2_variables(parsed)
        why, warn = validate(rule, vocab, keys)
        if why:
            rejected.append({"line": line[:220], "reasons": why,
                             "printed": SP._safe_printed(rule)})
            continue
        key = SP.canonical(rule)
        if key in seen:
            seen[key].setdefault("lines", []).append(line[:220])
            continue
        if len(accepted) >= max_rules:
            over_cap.append({"line": line[:220],
                             "why": "beyond the %d-rule limit for one call"
                                    % max_rules})
            continue
        matched, unmatched, cost = rule_candidates(rule, vocab)
        entry = {"rule_id": fresh_id(), "body": rule["body"],
                 "head": rule["head"], "canonical": key,
                 "printed": SP._safe_printed(rule), "lines": [line[:220]],
                 "origin": LLM_GENERAL, "warnings": warn,
                 "candidate_matches": matched,
                 "atoms_matching_no_candidate": unmatched,
                 "rule_priority_cost": cost,
                 "role_fit": role_fit(rule, vocab),
                 "variants": []}
        seen[key] = entry
        accepted.append(entry)
        if WARN_GENERALIZES in warn:
            for variant in ground_specializations(rule, vocab):
                if variant["canonical"] in seen:
                    continue
                vmatched, vunmatched, vcost = rule_candidates(variant, vocab)
                child = {"rule_id": fresh_id(), "body": variant["body"],
                         "head": variant["head"],
                         "canonical": variant["canonical"],
                         "printed": variant["printed"],
                         "lines": [line[:220]],
                         "origin": GROUND_SPECIALIZATION,
                         "specialization_of": entry["rule_id"],
                         "substitution": variant["substitution"],
                         "warnings": [], "candidate_matches": vmatched,
                         "atoms_matching_no_candidate": vunmatched,
                         "rule_priority_cost": vcost,
                         "role_fit": role_fit(variant, vocab),
                         "variants": []}
                seen[variant["canonical"]] = child
                entry["variants"].append(child["rule_id"])
                accepted.append(child)
    return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
            "readable_lines": len(rule_lines), "response_lines": len(lines),
            "rejection_reasons": sorted(set(r for x in rejected
                                            for r in x["reasons"]))[:20],
            "next_index": n[0] + 1}
