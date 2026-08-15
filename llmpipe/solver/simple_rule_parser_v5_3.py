"""The v5.3 rule contract: `?` names are the only variables (WP1, WP6.1, WP5).

Three things change, and nothing in v1-v5.2 is touched.

**Only a `?` name is a rule variable.**  `alignment_occurrences._is_var` calls
every capitalised token a variable, so the v5.2 validator read `W0` in

    ["has property","smart","?X"] -> ["is rel2","smart","?X","W0"]

as an unbound rule variable and refused the rule for range safety.  `W0` is a
world constant the passage's own clauses use.  Here the rule's variables are
exactly the `?` names the model wrote, recorded when the line is parsed;
everything else is a constant and must be displayed like any other constant.

**A displayed `eventprop` participant may be generalised.**  The prompt says a
displayed object constant may become a variable when the implication is
genuinely general.  v5.2 allowed that in a top-level argument and refused it
inside a displayed nested term, so in `mle2-0049` the model's correct

    ["is rel2","plant","?P",["eventprop","$target","?S"]]

was refused because the displayed term named a particular seed.  The match here
is narrow: the functor stays `eventprop`, the role stays exactly what it was,
and only the participant value may go from a displayed constant to a rule
variable.  No other nested form generalises.

**Five premises, not three.**  `eb2-0009`'s faithful four-premise restriction
was refused for length alone.  Length is now recorded and used for ordering,
never for refusal below six.

The grammar, the scanner, the canonical form, the printer and the vocabulary
are the frozen ones, imported.
"""

import copy
import json

import alignment_occurrences as AO
import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import simple_rule_parser_v5_1 as P51
import unifier_abstraction as UA
import unifier_prompt_v5_1 as PRINT

VERSION = "simple_rule_parser_v5_3/1.0"

MAX_BODY_LITERALS = 5
MAX_BASE_RULES_PER_CALL = 12
MAX_GROUND_SPECIALIZATIONS = P3.MAX_GROUND_SPECIALIZATIONS

LLM_GENERAL = P3.LLM_GENERAL
GROUND_SPECIALIZATION = P3.GROUND_SPECIALIZATION
WARN_GENERALIZES = P3.WARN_GENERALIZES

FORBIDDEN_WORDS = SP.FORBIDDEN_WORDS
EVENTPROP = "eventprop"

REASON_NEGATIVE = P51.REASON_NEGATIVE
REASON_HELPER_ONLY = P51.REASON_HELPER_ONLY
REASON_CONTRADICTS = P51.REASON_CONTRADICTS
REASON_TRIED = "already tried in this case"
REASON_SOURCE_RULE = "identical to a rule the passage already states"
REASON_TOO_LONG = "more than %d premises" % MAX_BODY_LITERALS
REASON_OVER_CAP = ("beyond the %d valid model-written rules this call may "
                   "contribute")

alpha_equivalent = P3.alpha_equivalent
nested_shapes = P3.nested_shapes
extra_refusals = P51.extra_refusals
split_negative_lines = P51.split_negative_lines


# ---------------------------------------------------------------- vocabulary

def is_display_variable(term):
    """A displayed atom writes its open positions as `?X`, and nothing else."""
    return isinstance(term, str) and term.startswith("?") \
        and not term.startswith("?:")


def constants_in(atom):
    """Every non-variable string of a displayed atom, nested terms included.

    `simple_rule_parser_v3.constants_in` asks `unifier_abstraction`, which calls
    `W0` a variable, so the world constant of `folio-0089`'s question clause
    never became writable vocabulary.
    """
    out = set()

    def go(t):
        if isinstance(t, str):
            if not is_display_variable(t):
                out.add(t)
            return
        if isinstance(t, list) and t:
            for x in t[1:]:
                go(x)
    for a in atom[1:]:
        go(a)
    return out


def vocabulary(candidates):
    """What the displayed atoms and their admitted source aliases license."""
    preds, arities, label_slots, labels = {}, {}, {}, {}
    constants, shapes, atoms, grounding = set(), [], [], []

    def register(atom):
        pred = str(atom[0])
        args = list(atom[1:])
        preds.setdefault(pred, set()).add(len(args))
        arities.setdefault(pred, set()).add(len(args))
        slot = AO.LABEL_SLOT.get(pred)
        if slot is not None and slot < len(args) \
                and isinstance(args[slot], str) \
                and not is_display_variable(args[slot]):
            label_slots.setdefault(pred, set()).add(slot)
            labels.setdefault(pred, set()).add(str(args[slot]))

    for row in candidates["groups"]:
        atom = row["atom"]
        register(atom)
        for inner in P3._inner_atoms(atom):
            register(inner)
        constants |= constants_in(atom)
        for shape in nested_shapes(atom):
            if not any(alpha_equivalent(shape, s) for s in shapes):
                shapes.append(shape)
        atoms.append({"id": row["id"], "atom": atom, "sign": "+",
                      "role": row["internal_role"],
                      "priority_cost": row["cost"],
                      "section": row.get("section"),
                      "printed": row.get("printed")})
        if not [t for t in _tokens(atom) if is_display_variable(t)] \
                and UA.SOURCE in (row.get("same_sign_source_kinds") or []):
            grounding.append({"id": row["id"], "sign": "+", "atom": atom,
                              "source_kinds": row.get("same_sign_source_kinds"),
                              "printed": row.get("printed")})
    return {"predicates": dict((p, sorted(v)) for p, v in preds.items()),
            "arities": dict((p, sorted(v)) for p, v in arities.items()),
            "constants": sorted(constants),
            "label_slots": dict((p, sorted(v)) for p, v in label_slots.items()),
            "labels_per_predicate": dict((p, sorted(v))
                                         for p, v in labels.items()),
            "nested_shapes": shapes, "atoms": atoms,
            "grounding_atoms": grounding,
            "sections": dict((r["id"], r.get("section"))
                             for r in candidates["groups"]),
            "content_ids": sorted(set(r["id"] for r in candidates["groups"]
                                      if r.get("section") != "helper")),
            "policy": "the vocabulary is exactly the displayed atoms and their "
                      "admitted source aliases; only a `?` name is a variable"}


# ------------------------------------------------------------- rule variables

def to_rule(parsed):
    """`?X` -> `V1`, and the resulting names are the rule's ONLY variables."""
    rule = SP.to_stage2_variables(parsed)
    order = []
    for lit in rule["body"] + [rule["head"]]:
        for v in _tokens(lit["atom"]):
            if v in rule["variables"].values() and v not in order:
                order.append(v)
    rule["llm_variables"] = order
    return rule


def _tokens(term):
    out = []
    if isinstance(term, str):
        out.append(term)
    elif isinstance(term, list):
        for x in term[1:]:
            out.extend(_tokens(x))
    return out


def rule_variables(rule):
    return list(rule.get("llm_variables") or [])


def is_rule_variable(term, rule_vars):
    return isinstance(term, str) and term in rule_vars


def free_variables_of(rule):
    """The rule's variables in first-appearance order.  Constants are not."""
    return rule_variables(rule)


def atom_variables(atom, rule_vars):
    return [t for t in _tokens(atom) if t in rule_vars]


# ------------------------------------------- canonical form and printing
#
# `simple_rule_parser.canonical` and `.printed` blank or rename every
# capitalised token, which would turn the constant `W0` into a variable in both
# the deduplication key and the printed line.  These do the same work over the
# rule's OWN variables.

def _canonical_parts(rule, rule_vars):
    def blank(atom):
        def go(t):
            if is_rule_variable(t, rule_vars):
                return "?"
            if isinstance(t, list) and t:
                return [t[0]] + [go(x) for x in t[1:]]
            return t
        return [atom[0]] + [go(a) for a in atom[1:]]
    body = sorted(rule["body"],
                  key=lambda l: json.dumps([l["sign"], blank(l["atom"])]))
    names = {}

    def go(t):
        if is_rule_variable(t, rule_vars):
            names.setdefault(t, "_v%d" % len(names))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t

    def norm(lit):
        return [lit["sign"], [lit["atom"][0]] + [go(a) for a in lit["atom"][1:]]]
    return [norm(l) for l in body], norm(rule["head"])


def canonical(rule, rule_vars=None):
    """The rule up to renaming its OWN variables, as one comparable string."""
    body, head = _canonical_parts(rule, rule_vars if rule_vars is not None
                                  else rule_variables(rule))
    return json.dumps([body, head], sort_keys=True)


def source_rule_keys(source_rules):
    """The passage's own rules, canonicalised over their Stage-2 variables."""
    out = set()
    for r in source_rules or []:
        rule_vars = [t for lit in r["body"] + [r["head"]]
                     for t in _tokens(lit["atom"]) if AO._is_var(t)]
        out.add(canonical(r, rule_vars))
    return out


def printed_rule(rule):
    """One line, in the grammar it was written in, renaming only its variables."""
    rule_vars = rule_variables(rule)
    names, order = {}, []
    for lit in rule["body"] + [rule["head"]]:
        for v in _tokens(lit["atom"]):
            if v in rule_vars and v not in names:
                i = len(order)
                names[v] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                            else "?V%d" % (i + 1))
                order.append(v)

    def rename(atom):
        def go(t):
            if isinstance(t, str):
                return names.get(t, t)
            if isinstance(t, list) and t:
                return [t[0]] + [go(x) for x in t[1:]]
            return t
        return [atom[0]] + [go(a) for a in atom[1:]]

    def show(lit):
        return PRINT.printed_atom(rename(lit["atom"]),
                                negated=lit.get("sign") == "-")
    return "%s -> %s" % (" AND ".join(show(l) for l in rule["body"]),
                         show(rule["head"]))


# --------------------------------------------------- the narrow nested match

def _generalised_eventprop(term, shape, rule_vars):
    """`eventprop($role, C)` displayed, `eventprop($role, ?V)` written."""
    if not (isinstance(term, list) and isinstance(shape, list)):
        return False
    if str(term[0]) != EVENTPROP or str(shape[0]) != EVENTPROP:
        return False
    if len(term) != 3 or len(shape) != 3:
        return False
    if json.dumps(term[1]) != json.dumps(shape[1]):
        return False                                    # the role is exact
    written, displayed = term[2], shape[2]
    if not is_rule_variable(written, rule_vars):
        return False
    return isinstance(displayed, str) and displayed not in rule_vars \
        and not UA.is_variable_term(displayed)


def nested_is_displayed(term, shapes, rule_vars):
    """-> (ok, how).  Alpha-equal to a displayed shape, or its generalisation."""
    for s in shapes:
        if alpha_equivalent(term, s):
            return True, None
    for s in shapes:
        if _generalised_eventprop(term, s, rule_vars):
            return True, {"displayed": s, "written": term,
                          "rule": "eventprop_participant_generalisation"}
    return False, None


# ----------------------------------------------------------------- validation

def validate(rule, vocab, source_keys=()):
    """-> (refusals, warnings, notes).  Refusals are mechanical."""
    why, warn, notes = [], [], []
    body, head = rule["body"], rule["head"]
    rule_vars = rule_variables(rule)
    if not body:
        why.append("no body literal")
    if len(body) > MAX_BODY_LITERALS:
        why.append(REASON_TOO_LONG)
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
            why.append("equality is not part of the ordinary rule task")
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
                ok, how = nested_is_displayed(a, vocab["nested_shapes"],
                                              rule_vars)
                if not ok:
                    why.append("a nested term that was never displayed: %s"
                               % json.dumps(a)[:80])
                elif how:
                    notes.append(how)
                continue
            if is_rule_variable(a, rule_vars):
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
        body_vars |= set(atom_variables(lit["atom"], rule_vars))
    free = set(atom_variables(head["atom"], rule_vars)) - body_vars
    if free:
        why.append("the conclusion uses %s, which the body never binds"
                   % ", ".join(sorted(free)))
    cbody, chead = _canonical_parts(rule, rule_vars)
    if chead in cbody:
        why.append("a tautology: the conclusion is one of its own premises")
    if json.dumps([cbody, chead], sort_keys=True) in set(source_keys):
        why.append(REASON_SOURCE_RULE)
    if not why and generalizes_observed_constants(rule, vocab):
        warn.append(WARN_GENERALIZES)
    return why, warn, notes


def generalizes_observed_constants(rule, vocab):
    """Did the model put a variable where every displayed atom had a constant?"""
    rule_vars = rule_variables(rule)
    for lit in rule["body"] + [rule["head"]]:
        atom = lit["atom"]
        pred = str(atom[0])
        args = list(atom[1:])
        shown = [r["atom"] for r in vocab["atoms"]
                 if str(r["atom"][0]) == pred and len(r["atom"]) == len(atom)]
        if not shown:
            continue
        for i, a in enumerate(args):
            if not is_rule_variable(a, rule_vars):
                continue
            if AO.LABEL_SLOT.get(pred) == i:
                continue
            values = [s[i + 1] for s in shown]
            if values and all(isinstance(v, str) and not UA.is_variable_term(v)
                              for v in values):
                return True
    return False


# ------------------------------------------------------ ground specializations

def _match_atom(atom, ground, subst, rule_vars):
    """Match a rule atom against a displayed ground atom.  Rule vars only."""
    if str(atom[0]) != str(ground[0]) or len(atom) != len(ground):
        return None
    out = dict(subst)

    def go(x, y):
        if is_rule_variable(x, rule_vars):
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
    """Up to `cap` grounded variants, from signed source-linked matches only."""
    rule_vars = rule_variables(rule)
    evidence = [r for r in vocab.get("grounding_atoms") or []]
    if not evidence or not rule_vars:
        return []
    results, budget = [], [400]

    def walk(i, subst, used):
        if len(results) >= cap or budget[0] <= 0:
            return
        if i >= len(rule["body"]):
            if subst:
                results.append((dict(subst), list(used)))
            return
        lit = rule["body"][i]
        for g in evidence:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            if g["sign"] != lit["sign"]:
                continue
            got = _match_atom(lit["atom"], g["atom"], subst, rule_vars)
            if got is not None:
                walk(i + 1, got, used + [g["id"]])
    walk(0, {}, [])
    out, seen = [], set()
    for subst, used in results:
        body = [{"sign": l["sign"], "atom": _apply(l["atom"], subst)}
                for l in rule["body"]]
        head = {"sign": rule["head"]["sign"],
                "atom": _apply(rule["head"]["atom"], subst)}
        variant = {"body": body, "head": head,
                   "llm_variables": [v for v in rule_vars if v not in subst]}
        key = canonical(variant)
        if key == canonical(rule) or key in seen:
            continue
        seen.add(key)
        variant["canonical"] = key
        variant["printed"] = printed_rule(variant)
        variant["substitution"] = dict(subst)
        variant["grounded_on"] = used
        out.append(variant)
    return out[:cap]


# ------------------------------------------------------------ rule candidates

def rule_candidates(rule, vocab):
    """-> (matched candidate ids per literal, unmatched atoms, total cost)."""
    matched, unmatched, total = [], [], 0
    for lit in rule["body"] + [rule["head"]]:
        want = lit["atom"]
        exact = [row for row in vocab["atoms"]
                 if row["sign"] == lit["sign"]
                 and alpha_equivalent(row["atom"], want)]
        loose = []
        if not exact:
            for row in vocab["atoms"]:
                if row["sign"] != lit["sign"]:
                    continue
                if UA.unify_unsigned_atoms(
                        P3._clause_shape(row["atom"]),
                        P3._clause_shape(want))["unifiable"]:
                    loose.append(row)
            loose.sort(key=lambda r: (len(atom_variables(r["atom"],
                                                         rule_variables(rule))),
                                      str(r.get("id"))))
        best = (exact or loose or [None])[0]
        if best is None:
            unmatched.append(PRINT.printed_atom(UA.display_atom(want),
                                              negated=lit["sign"] == "-"))
            continue
        matched.append({"literal": PRINT.printed_atom(UA.display_atom(want)),
                        "candidate": best["id"], "role": best["role"],
                        "priority_cost": best["priority_cost"],
                        "match_kind": "alpha_exact" if exact else "unifier",
                        "equally_good": [r["id"] for r in (exact or loose)][:6]})
        total += best["priority_cost"]
    return matched, unmatched, total


def role_fit(rule, vocab):
    return P3.role_fit(rule, vocab)


# ------------------------------------------------------------------- parsing

def parse_response(text, vocab, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
    """-> the v5.3 parse.  Every refusal is named and separately countable.

    `tried` is the canonical form of the rules this case already submitted; a
    repeat of one is reported as its own category rather than merged silently.
    """
    lines = (text or "").splitlines()
    rule_lines = [l for l in lines if SP.RULE_PREFIX.match(l)]
    source_keys = source_rule_keys(source_rules)
    tried_keys = set(tried or [])
    seen = dict((r["canonical"], r) for r in existing)
    accepted, rejected, over_cap, notes = [], [], [], []
    base_kept = 0
    n = [start_index - 1]

    def fresh_id():
        n[0] += 1
        return "R%d" % n[0]

    for raw in rule_lines:
        line = raw.strip()
        try:
            parsed = SP.parse_line(line)
        except SP.RuleError as e:
            rejected.append({"line": line[:220], "reasons": [str(e)],
                             "category": "unreadable"})
            continue
        if any(s == "-" for s, _a in parsed["body"] + [parsed["head"]]):
            rejected.append({"line": line[:220], "reasons": [REASON_NEGATIVE],
                             "category": "explicit_negative"})
            continue
        rule = to_rule(parsed)
        why, warn, got_notes = validate(rule, vocab, source_keys)
        if not why:
            why = extra_refusals(rule, vocab)
        if why:
            rejected.append({"line": line[:220], "reasons": why,
                             "printed": printed_rule(rule),
                             "category": _category(why)})
            continue
        key = canonical(rule)
        if key in tried_keys:
            rejected.append({"line": line[:220], "reasons": [REASON_TRIED],
                             "printed": printed_rule(rule),
                             "category": "repeat_of_a_tried_rule"})
            continue
        if key in seen:
            seen[key].setdefault("lines", []).append(line[:220])
            continue
        if base_kept >= max_rules:
            over_cap.append({"line": line[:220],
                             "printed": printed_rule(rule),
                             "why": REASON_OVER_CAP % max_rules})
            continue
        matched, unmatched, cost = rule_candidates(rule, vocab)
        entry = {"rule_id": fresh_id(), "body": rule["body"],
                 "head": rule["head"], "canonical": key,
                 "llm_variables": rule["llm_variables"],
                 "printed": printed_rule(rule), "lines": [line[:220]],
                 "origin": LLM_GENERAL, "warnings": warn,
                 "premises": len(rule["body"]),
                 "candidate_matches": matched,
                 "atoms_matching_no_candidate": unmatched,
                 "rule_priority_cost": cost,
                 "role_fit": role_fit(rule, vocab),
                 "generalisation_notes": got_notes,
                 "variants": []}
        seen[key] = entry
        accepted.append(entry)
        notes.extend(got_notes)
        base_kept += 1
        if WARN_GENERALIZES in warn:
            for variant in ground_specializations(rule, vocab):
                if variant["canonical"] in seen:
                    continue
                vmatched, vunmatched, vcost = rule_candidates(variant, vocab)
                child = {"rule_id": fresh_id(), "body": variant["body"],
                         "head": variant["head"],
                         "canonical": variant["canonical"],
                         "llm_variables": variant["llm_variables"],
                         "printed": variant["printed"],
                         "lines": [line[:220]],
                         "origin": GROUND_SPECIALIZATION,
                         "specialization_of": entry["rule_id"],
                         "substitution": variant["substitution"],
                         "grounded_on": variant["grounded_on"],
                         "warnings": [], "premises": len(variant["body"]),
                         "candidate_matches": vmatched,
                         "atoms_matching_no_candidate": vunmatched,
                         "rule_priority_cost": vcost,
                         "role_fit": role_fit(variant, vocab),
                         "generalisation_notes": [],
                         "variants": []}
                seen[variant["canonical"]] = child
                entry["variants"].append(child["rule_id"])
                accepted.append(child)
    return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
            "readable_lines": len(rule_lines), "response_lines": len(lines),
            "rejection_reasons": sorted(set(r for x in rejected
                                            for r in x["reasons"]))[:20],
            "rejections_by_category": _counts(rejected),
            "base_rules_accepted": base_kept,
            "generated_specializations_accepted": len(accepted) - base_kept,
            "base_rule_limit": max_rules,
            "refused_negative_lines": sum(
                1 for r in rejected if r["category"] == "explicit_negative"),
            "generalisation_notes": notes,
            "next_index": n[0] + 1, "version": VERSION}


def _category(why):
    first = why[0]
    if first == REASON_SOURCE_RULE:
        return "already_in_the_passage"
    if first == REASON_TOO_LONG:
        return "too_many_premises"
    if first.startswith("the conclusion uses"):
        return "range_unsafe"
    if first == REASON_HELPER_ONLY:
        return "helper_atoms_only"
    if "never displayed" in first:
        return "atom_not_in_the_candidate_list"
    if first.startswith("a tautology"):
        return "conclusion_repeats_a_premise"
    return "other"


def _counts(rejected):
    out = {}
    for r in rejected:
        out[r["category"]] = out.get(r["category"], 0) + 1
    return out
