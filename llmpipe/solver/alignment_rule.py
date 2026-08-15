"""Occurrence-id bridge rules: format, validation and compiler.

The previous round asked a model to serialise nested Stage-2 logic.  It found
the right connection and then mis-rendered it: quantifier scope wrong in two
cases, unbalanced brackets in two more.  Serialising nested logic is not what
the model is good at, so it stops being its job.

A rule is now named, not written:

    {
      "antecedents": ["S2:s2:/2/1", ...],   existing occurrence ids
      "consequent":  "S4:s2:/1/2/1",        one existing occurrence id
      "strength":    "default" | "strict"
    }

Code does the rest: it takes those atoms as they stand, unifies the argument
positions the CANDIDATE already worked out, freshens the variables, quantifies
what is left, and wraps a default rule in `["normally", ...]`.  The mapping is
never asked of the model — it was computed when the pair was enumerated.

**A newly invented bridge is defeasible by default.**  `strict` has to be
chosen deliberately, and the record says which was asked for.
"""

import re

import alignment_candidates as AC
import alignment_context as CX
import alignment_occurrences as AO

STRENGTHS = ("default", "strict")
DEFAULT_STRENGTH = "default"
MAX_ANTECEDENTS = 3
MAX_CONDITIONS = 3

# Runtime policy for a CONNECT bridge, 2026-08-10.
#
# The builder's strength suggestion is recorded and not obeyed.  Chain v3 chose
# `strict` for five of six rules — worse than v2's three-of-five `default` —
# and a strict bridge is the one kind of error that cannot be recovered from
# downstream: a defeasible rule that turns out to be wrong is overridden, a
# strict one that turns out to be wrong makes the theory wrong.  Strict
# promotion needs evidence nobody has yet defined, so until then it is not
# available at runtime.
STRENGTH_POLICIES = ("always_default", "as_requested")
CONNECT_STRENGTH_POLICY = "always_default"


class RuleError(Exception):
    """The rule cannot be compiled.  Never worked around."""


def _fresh(n):
    return "V%d" % n


def _atom_of(occ):
    """The stored atom of an occurrence, as a list."""
    args = occ.get("arguments_or_roles")
    if not isinstance(args, list) or not occ.get("predicate"):
        raise RuleError("occurrence %s carries no atom" % occ.get("occurrence_id"))
    return [occ["predicate"]] + list(args)


def validate(rule, table, allowed_ids=None):
    """-> normalised rule, or raise.  No id is guessed or corrected."""
    if not isinstance(rule, dict):
        raise RuleError("a rule must be an object")
    ants = rule.get("antecedents")
    cons = rule.get("consequent")
    if not isinstance(ants, list) or not ants:
        raise RuleError("antecedents must be a non-empty list of occurrence ids")
    if len(ants) > MAX_ANTECEDENTS:
        raise RuleError("at most %d antecedents" % MAX_ANTECEDENTS)
    if not isinstance(cons, str):
        raise RuleError("consequent must be one occurrence id")
    strength = (rule.get("strength") or DEFAULT_STRENGTH).strip().lower()
    if strength not in STRENGTHS:
        raise RuleError("strength must be one of %s" % (STRENGTHS,))
    seen = set()
    for oid in ants + [cons]:
        if oid not in table["by_id"]:
            raise RuleError("%s is not an occurrence in this case" % oid)
        if allowed_ids is not None and oid not in allowed_ids:
            raise RuleError("%s is not one of the atoms offered" % oid)
        if oid in seen:
            raise RuleError("%s is used twice" % oid)
        seen.add(oid)
    if cons in ants:
        raise RuleError("the consequent is also an antecedent")
    return {"antecedents": list(ants), "consequent": cons,
            "strength": strength}


def compile_rule(rule, table, world="W0", mapping_source=None):
    """-> (Stage-2 package, record).  Deterministic; the model sees none of it.

    Argument positions the candidate linked become one variable.  A position
    linked to a grounded constant keeps the constant only when both sides are
    the same constant; when one side is a variable the pair becomes a variable,
    which is what makes the rule general rather than a restatement of one
    instance.  Everything else keeps its own term, with variables freshened so
    two atoms cannot collide by accident.
    """
    r = validate(rule, table)
    by_id = table["by_id"]
    cons_occ = by_id[r["consequent"]]
    atoms = [(oid, _atom_of(by_id[oid])) for oid in r["antecedents"]]
    cons_atom = _atom_of(cons_occ)

    # positions the candidate already linked, per antecedent
    groups = []
    for oid in r["antecedents"]:
        why = AC.reject_reason(by_id[oid], cons_occ)
        if why:
            # the same authority that enumerated the candidates: a rule may not
            # be built from a pair the logic already ruled out
            raise RuleError("%s -> %s is not a mechanically valid pair: %s"
                            % (oid, r["consequent"], why))
        pairs, _ = AC.argument_mappings(by_id[oid], cons_occ)
        if not pairs:
            raise RuleError("%s and %s share no argument position, so the rule "
                            "would connect nothing" % (oid, r["consequent"]))
        for a, b in pairs:
            groups.append({"terms": [a, b], "atoms": [oid, r["consequent"]]})

    counter = [0]
    var_of = {}

    def var_for(key):
        if key not in var_of:
            counter[0] += 1
            var_of[key] = _fresh(counter[0])
        return var_of[key]

    def resolve(term, owner):
        """A term as it should appear in the rule."""
        for g in groups:
            if term in g["terms"] and owner in g["atoms"]:
                if all(not AO._is_var(t) for t in g["terms"]):
                    if len(set(g["terms"])) == 1:
                        return g["terms"][0]
                    raise RuleError("two different constants were linked: %s"
                                    % g["terms"])
                return var_for(tuple(sorted(map(str, g["terms"]))))
        if AO._is_var(term):
            # variable scope is the PACKAGE, not the atom: two atoms from one
            # sentence that both mention Y mention the same Y, and a condition
            # lifted from beside the base atom has to keep that link
            return var_for(("own", by_id[owner]["unit_id"], term))
        return term

    def rebuild(atom, owner):
        pred = atom[0]
        slot = AO.LABEL_SLOT.get(pred)
        out = [pred]
        for i, a in enumerate(atom[1:]):
            if i == slot or isinstance(a, list) or not isinstance(a, str):
                out.append(a)
            else:
                out.append(resolve(a, owner))
        return out

    body_ants = [rebuild(a, oid) for oid, a in atoms]
    body_cons = rebuild(cons_atom, r["consequent"])
    inner = ["implies",
             body_ants[0] if len(body_ants) == 1 else ["and"] + body_ants,
             body_cons]
    if r["strength"] == "default":
        inner = ["normally", inner]
    used = []

    def collect(x):
        if isinstance(x, list):
            for y in x:
                collect(y)
        elif isinstance(x, str) and AO._is_var(x) and x not in used:
            used.append(x)
    collect(inner)
    formula = inner
    for v in reversed(used):
        formula = ["forall", v, formula]
    pkg = ["holds", world, formula]
    record = {
        "antecedent_occurrences": r["antecedents"],
        "consequent_occurrence": r["consequent"],
        "strength": r["strength"],
        "quantified_variables": used,
        "unified_positions": [g["terms"] for g in groups],
        "mapping_source": mapping_source or "candidate argument mapping",
        "note": "compiled by code from occurrence ids; the model chose the "
                "atoms and the strength, not the serialisation",
    }
    return pkg, record


# ------------------------------------------------- base candidate + conditions

def _participants(occ):
    """Term positions that hold participants, label and degree slots removed."""
    return CX._terms(occ)


SCOPES = ("local", "context", "general", "unclear")

# What a bridge is FOR.  A question consumer does not determine the head sign:
# the same pair supports proving the question literal and refuting it, and those
# are different rules.  Copying the consumer's sign silently chose the first,
# which is how folio-0169's reviewed `member of -> part of` was never built.
TARGET_MODES = ("supply_premise", "supply_question", "contradict_question")


class ScopeError(RuleError):
    """The requested scope cannot be represented by this rule."""


class RangeError(RuleError):
    """A conclusion variable no antecedent binds."""


def target_modes_for(consumer):
    """Which hypotheses this consumer supports.

    A question GOAL supports two: supply it, or derive its complement and refute
    it.  Anything else — an ordinary rule premise, a question assumption —
    supports only supply.
    """
    if consumer.get("in_question") and consumer.get("rule_side") != "antecedent":
        return ("supply_question", "contradict_question")
    return ("supply_premise",)


def _complement(lit):
    """`p` <-> `not p`.  The complement of a literal, not its negation twice."""
    if isinstance(lit, list) and len(lit) == 2 and lit[0] == "not":
        return lit[1]
    return ["not", lit]


def _vars_in(node, out=None):
    out = [] if out is None else out
    if isinstance(node, list):
        for x in node:
            _vars_in(x, out)
    elif isinstance(node, str) and AO._is_var(node) and node not in out:
        out.append(node)
    return out


def compile_from_base(producer_id, consumer_id, condition_ids, table,
                      strength=DEFAULT_STRENGTH, world="W0", policy=None,
                      scope="general", target_mode=None,
                      require_range_restriction=False):
    """Compile a selected candidate plus chosen companion conditions.

    The candidate fixes the primary antecedent, the consequent, the direction
    and the argument map; the model only chooses which extra conditions travel
    with it.  A condition is refused unless it shares a variable or a grounded
    entity with the rule built so far, because a condition connected to nothing
    is either a copied premise or a mistake, and silently keeping it would make
    the rule fire on the wrong things.

    Quantification happens last, after every unification.
    """
    if strength not in STRENGTHS:
        raise RuleError("strength must be one of %s" % (STRENGTHS,))
    policy = policy or CONNECT_STRENGTH_POLICY
    if policy not in STRENGTH_POLICIES:
        raise RuleError("unknown strength policy %r" % policy)
    if scope not in SCOPES:
        raise RuleError("unknown scope %r" % scope)
    if scope == "unclear":
        raise ScopeError("unclear scope produces no rule")
    if target_mode is not None and target_mode not in TARGET_MODES:
        raise RuleError("unknown target mode %r" % target_mode)
    suggested = strength
    if policy == "always_default":
        strength = DEFAULT_STRENGTH
    by_id = table["by_id"]
    for oid in [producer_id, consumer_id] + list(condition_ids):
        if oid not in by_id:
            raise RuleError("%s is not an occurrence in this case" % oid)
    if consumer_id in condition_ids or producer_id in condition_ids:
        raise RuleError("a condition repeats the base pair")
    if len(condition_ids) != len(set(condition_ids)):
        raise RuleError("a condition is named twice")
    if len(condition_ids) > MAX_CONDITIONS:
        raise RuleError("at most %d additional conditions" % MAX_CONDITIONS)

    p, c = by_id[producer_id], by_id[consumer_id]
    allowed = target_modes_for(c)
    if target_mode is None:
        target_mode = allowed[0]
    elif target_mode not in allowed:
        raise RuleError("%s does not support target mode %s (it supports %s)"
                        % (consumer_id, target_mode, list(allowed)))
    why = AC.reject_reason(p, c)
    if why:
        raise RuleError("%s -> %s is not a mechanically valid pair: %s"
                        % (producer_id, consumer_id, why))
    pairs, swapped = AC.argument_mappings(p, c)
    if not pairs:
        raise RuleError("%s and %s share no argument position, so the rule "
                        "would connect nothing" % (producer_id, consumer_id))

    counter, var_of = [0], {}

    def var_for(key):
        if key not in var_of:
            counter[0] += 1
            var_of[key] = "V%d" % counter[0]
        return var_of[key]

    if scope == "context" and not condition_ids:
        raise ScopeError("context_scope_without_condition")

    linked = {}     # (unit, term) -> group key, for the base pair's mapping
    grounded = {}   # local scope: a linked position that a constant anchors
    for a, b in pairs:
        if not AO._is_var(a) and not AO._is_var(b):
            if AO.normalize_label(a) != AO.normalize_label(b):
                raise RuleError("two different constants were linked: %r, %r"
                                % (a, b))
            continue
        key = ("linked", producer_id, consumer_id, str(a), str(b))
        linked[(p["unit_id"], a)] = key
        linked[(c["unit_id"], b)] = key
        if scope == "local":
            # a variable linked to a named individual is INSTANTIATED to it
            # rather than generalised: that is what `local` means, and letting
            # it generalise would silently widen the rule the reviewer scoped.
            for term in (a, b):
                if isinstance(term, str) and not AO._is_var(term):
                    grounded[key] = term
    if scope == "local" and not grounded:
        anchored = any(
            isinstance(t, str) and not AO._is_var(t)
            for oid in [producer_id, consumer_id] + list(condition_ids)
            for t in _participants(by_id[oid]))
        if not anchored:
            raise ScopeError("local_scope_unrepresentable")

    def resolve(term, occ):
        if not isinstance(term, str):
            return term
        k = linked.get((occ["unit_id"], term))
        if k is not None:
            if k in grounded:
                return grounded[k]
            return var_for(k)
        if AO._is_var(term):
            return var_for(("own", occ["unit_id"], term))
        return term

    def rebuild(occ):
        """The occurrence as a complete SIGNED literal, arguments resolved.

        The sign is the occurrence's own polarity and is never dropped: a
        producer found under a negation contributes `not p(...)`, and a
        consumer found under one is concluded as `not q(...)`.  Losing it turns
        one rule into a different rule about different things.
        """
        atom = AO.bare_atom(occ)
        slot = AO.LABEL_SLOT.get(atom[0])
        out = [atom[0]]
        for i, a in enumerate(atom[1:]):
            out.append(a if (i == slot or not isinstance(a, str))
                       else resolve(a, occ))
        return ["not", out] if AO.literal_sign(occ) == "-" else out

    body = [rebuild(p)]
    cons_atom = rebuild(c)
    if target_mode == "contradict_question":
        # the bridge derives the OPPOSITE of what the question asks, which is
        # how a False answer is reached
        cons_atom = _complement(cons_atom)
    # everything the rule already talks about, as resolved terms
    known = set()
    for occ in (p, c):
        for t in _participants(occ):
            r = resolve(t, occ)
            if isinstance(r, str):
                known.add(r)
    record_conditions = []
    for oid in condition_ids:
        occ = by_id[oid]
        terms = [resolve(t, occ) for t in _participants(occ)]
        shared = [t for t in terms if isinstance(t, str) and t in known]
        if not shared:
            raise RuleError(
                "%s shares no variable or entity with the rule so far, so it "
                "would restrict nothing: %s" % (oid, _atom_of(occ)))
        body.append(rebuild(occ))
        for t in terms:
            if isinstance(t, str):
                known.add(t)
        record_conditions.append({"occurrence_id": oid,
                                  "shares": sorted(set(shared)),
                                  "unit_id": occ["unit_id"]})

    ante_vars = set(v for b in body for v in _vars_in(b))
    cons_vars = set(_vars_in(cons_atom))
    unbound = sorted(cons_vars - ante_vars)
    if unbound and require_range_restriction:
        raise RangeError("unbound_conclusion_variable: %s" % ", ".join(unbound))

    inner = ["implies", body[0] if len(body) == 1 else ["and"] + body, cons_atom]
    if strength == DEFAULT_STRENGTH:
        inner = ["normally", inner]
    used = []

    def collect(x):
        if isinstance(x, list):
            for y in x:
                collect(y)
        elif isinstance(x, str) and AO._is_var(x) and x not in used:
            used.append(x)
    collect(inner)
    formula = inner
    for v in reversed(used):
        formula = ["forall", v, formula]
    pkg = ["holds", world, formula]
    record = {
        "base_producer": producer_id,
        "base_consumer": consumer_id,
        "antecedent_occurrences": [producer_id] + list(condition_ids),
        "consequent_occurrence": consumer_id,
        "conditions": record_conditions,
        "strength": strength,
        "model_suggested_strength": suggested,
        "compiled_strength": strength,
        "strict_promotion_requested": suggested == "strict",
        "strength_policy": policy,
        "strict_promotion_available": policy != "always_default",
        "quantified_variables": used,
        "unified_positions": [[a, b] for a, b in pairs],
        "argument_order_swapped": swapped,
        "scope": scope,
        "target_mode": target_mode,
        "unbound_conclusion_variables": unbound,
        "structurally_unsafe_probe": bool(unbound),
        "range_restricted": not unbound,
        "grounded_positions": {str(k): v for k, v in grounded.items()},
        "mapping_source": "the selected candidate's argument mapping",
        "note": "compiled by code from a selected candidate plus named "
                "conditions; the model chose neither the serialisation nor the "
                "argument map",
    }
    return pkg, record


# ---------------------------------------------------------------- parsing

_JSON_OBJ = re.compile(r"\{.*\}", re.S)

_BASE_LINE = re.compile(r"^\s*BASE\s*:\s*(.*)$", re.M | re.I)
_COND_LINE = re.compile(r"^\s*ADDITIONAL\s+CONDITIONS\s*:\s*(.*)$", re.M | re.I)
_STRENGTH_LINE = re.compile(r"^\s*STRENGTH\s*:\s*(.*)$", re.M | re.I)
_ALIAS = re.compile(r"[A-Za-z]+\d+")
_NONE = ("none", "-", "n/a", "na", "nothing", "()", "[]", "")


def parse_base_rule_response(text):
    """Read the three-field answer.

        BASE: K14
        ADDITIONAL CONDITIONS: G2,G4
        STRENGTH: strict

    -> ({"base","conditions","strength"}, error, prose).  Aliases are returned
    exactly as written; nothing is guessed or snapped to a nearby name.
    """
    if not text:
        return None, "empty response", ""
    m = _BASE_LINE.search(text)
    if not m:
        return None, "no BASE line", text.strip()
    base_field = m.group(1).strip()
    names = _ALIAS.findall(base_field)
    if len(names) != 1:
        return None, ("BASE must name exactly one candidate, found %r"
                      % base_field), text.strip()
    base = names[0].upper()
    conds = []
    mc = _COND_LINE.search(text)
    if mc:
        field = mc.group(1).strip()
        if field.strip().lower().strip(".") not in _NONE:
            conds = [a.upper() for a in _ALIAS.findall(field)]
            if not conds:
                return None, ("ADDITIONAL CONDITIONS is neither `none` nor a "
                              "list of names: %r" % field), text.strip()
    strength = DEFAULT_STRENGTH
    ms = _STRENGTH_LINE.search(text)
    if ms:
        want = ms.group(1).strip().lower().split()[0].strip(".,") if \
            ms.group(1).strip() else ""
        if want in STRENGTHS:
            strength = want
        elif want:
            return None, ("STRENGTH must be `strict` or `default`, found %r"
                          % ms.group(1).strip()), text.strip()
    prose = "\n".join(l for l in text.splitlines()
                      if not (_BASE_LINE.match(l) or _COND_LINE.match(l)
                              or _STRENGTH_LINE.match(l))).strip()
    if len(conds) != len(set(conds)):
        return None, "a condition is named twice", prose
    return ({"base": base, "conditions": conds, "strength": strength},
            None, prose)


def resolve_aliases(parsed, base_aliases, condition_aliases):
    """Alias -> occurrence ids.  An unknown alias is refused, never guessed."""
    if parsed["base"] not in base_aliases:
        raise RuleError("BASE %s is not one of the candidates offered (%s)"
                        % (parsed["base"], ", ".join(sorted(base_aliases))))
    row = base_aliases[parsed["base"]]
    out = []
    for a in parsed["conditions"]:
        if a not in condition_aliases:
            raise RuleError("%s is not one of the conditions offered (%s)"
                            % (a, ", ".join(sorted(condition_aliases)) or "none"))
        out.append(condition_aliases[a])
    return {"producer": row["producer"], "consumer": row["consumer"],
            "base_alias": parsed["base"], "condition_ids": out,
            "condition_aliases": list(parsed["conditions"]),
            "strength": parsed["strength"]}


def parse_rule_response(text):
    """The model's answer: a small JSON object, plus prose.

    Only the object is interpreted.  The reader accepts the first complete JSON
    value when what follows is nothing but whitespace and stray closing
    brackets — the failure that lost two cases last round — and it never
    inserts or removes a bracket inside the value it parses.
    """
    import json
    if not text:
        return None, "empty response", ""
    s = text.strip()
    start = s.find("{")
    if start < 0:
        return None, "no JSON object in the response", s
    dec = json.JSONDecoder()
    try:
        obj, end = dec.raw_decode(s[start:])
    except ValueError as e:
        return None, "not valid JSON: %s" % e, s
    # Trailing text is fine: the prompt invites a sentence of explanation after
    # the object, and the object is already complete and unambiguous.  What is
    # never done is inserting or removing a bracket INSIDE the parsed value.
    tail = s[start + end:].strip()
    if not isinstance(obj, dict):
        return None, "the JSON value is not an object", s
    prose = (s[:start] + " " + tail).strip()
    return obj, None, prose


def stray_only(tail):
    """True when what follows a complete JSON value is only whitespace and
    stray closing brackets — recorded so the distinction stays visible."""
    return bool(tail) and not (set(tail) - set("]}) \t\r\n"))
