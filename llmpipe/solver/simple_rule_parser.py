"""The small `RULE:` line language, parsed and validated (WP4).

    RULE: ["is rel2","member of","?X","?Y"] -> ["is rel2","part of","?X","?Y"]
    RULE: ["in","?X","Animal"] AND ["isa","organism","?X"] -> ["isa","animal","?X"]
    RULE: ["isa","bird","?X"] -> NOT ["isa","flightless","?X"]

Every atom is a JSON array whose first item is the exact predicate; the rest are
its exact arguments.  Variables start with `?`.  `NOT` sits outside an atom.

Only lines beginning `RULE:` are read.  Prose is kept in the log and ignored, a
malformed line is rejected and recorded, and nothing is scraped out of a
sentence: a rule the model did not write in the grammar is a rule it did not
write.

The validator refuses what is mechanically broken or outside the vocabulary the
model was shown.  It does NOT refuse a rule for being doubtful, reversed,
over-general or under-restricted — those are the hypotheses this pilot exists to
test and to grade after the proof search.
"""

import json
import re

import alignment_occurrences as AO
import unifier_abstraction as UA

VERSION = "simple_rule_parser/1.0"

MAX_BODY_LITERALS = 3
MAX_RULES_PER_CALL = 12

RULE_PREFIX = re.compile(r"^\s*[-*#>\s]*rule\s*:", re.I)
FORBIDDEN_WORDS = ("true", "false")


class RuleError(Exception):
    """A `RULE:` line that cannot be read."""


# ------------------------------------------------------------------ scanning

def _top_level_split(text, token):
    """Split on `token` only outside JSON strings and arrays."""
    parts, depth, in_str, esc, start, i = [], 0, False, False, 0, 0
    n, tl = len(text), len(token)
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "[":
            depth += 1
            i += 1
            continue
        if c == "]":
            depth -= 1
            i += 1
            continue
        if depth == 0 and text[i:i + tl] == token:
            if token.isalpha():
                before = text[i - 1] if i else " "
                after = text[i + tl] if i + tl < n else " "
                if before.isalnum() or after.isalnum():
                    i += 1
                    continue
            parts.append(text[start:i])
            start = i + tl
            i += tl
            continue
        i += 1
    parts.append(text[start:])
    return parts


def _parse_atom(text):
    """-> (sign, atom).  `NOT [..]` is negative; anything else must be JSON."""
    t = text.strip()
    sign = "+"
    m = re.match(r"^(NOT|not)\b\s*(.*)$", t, re.S)
    if m:
        sign = "-"
        t = m.group(2).strip()
    if not t.startswith("["):
        raise RuleError("not a JSON atom: %s" % t[:60])
    try:
        atom = json.loads(t)
    except ValueError as e:
        raise RuleError("unreadable JSON atom (%s): %s" % (e, t[:60]))
    if not (isinstance(atom, list) and atom and isinstance(atom[0], str)):
        raise RuleError("an atom must be a non-empty JSON array beginning with "
                        "a string: %s" % t[:60])
    return sign, atom


def parse_line(line):
    """-> {body: [(sign, atom)], head: (sign, atom)} for one `RULE:` line."""
    body_text = RULE_PREFIX.sub("", line, count=1)
    halves = _top_level_split(body_text, "->")
    if len(halves) != 2:
        raise RuleError("a rule needs exactly one `->`, found %d"
                        % (len(halves) - 1))
    left, right = halves
    body = []
    for chunk in _top_level_split(left, "AND"):
        if chunk.strip():
            body.append(_parse_atom(chunk))
    if not body:
        raise RuleError("no body literal")
    head_parts = [c for c in _top_level_split(right, "AND") if c.strip()]
    if len(head_parts) != 1:
        raise RuleError("a rule needs exactly one conclusion, found %d"
                        % len(head_parts))
    return {"body": body, "head": _parse_atom(head_parts[0])}


# --------------------------------------------------------------- normalising

def _display_vars(atom):
    out = []

    def go(t):
        if isinstance(t, str) and t.startswith("?"):
            if t not in out:
                out.append(t)
        elif isinstance(t, list):
            for x in t[1:]:
                go(x)
    for a in atom[1:]:
        go(a)
    return out


def _rename(atom, mapping):
    def go(t):
        if isinstance(t, str) and t.startswith("?"):
            return mapping[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def to_stage2_variables(parsed):
    """`?X` -> `V1`, in first-appearance order over the body then the head.

    Only the SPELLING changes.  Repeated uses of one display variable map to one
    Stage-2 variable, and everything without `?` stays exactly as printed.
    """
    mapping, order = {}, []
    for sign, atom in parsed["body"] + [parsed["head"]]:
        for v in _display_vars(atom):
            if v not in mapping:
                mapping[v] = "V%d" % (len(order) + 1)
                order.append(v)
    body = [{"sign": s, "atom": _rename(a, mapping)} for s, a in parsed["body"]]
    head = {"sign": parsed["head"][0], "atom": _rename(parsed["head"][1],
                                                      mapping)}
    return {"body": body, "head": head, "variables": mapping}


def canonical_parts(rule):
    """-> ([normalised body literals], normalised head), one shared renaming.

    Sign, predicate, content label, constants and ARGUMENT ORDER are all
    significant; only the names of the bound variables are not, and body order
    is not.
    """
    def blank(atom):
        def go(t):
            if isinstance(t, str) and AO._is_var(t):
                return "?"
            if isinstance(t, list) and t:
                return [t[0]] + [go(x) for x in t[1:]]
            return t
        return [atom[0]] + [go(a) for a in atom[1:]]
    body = sorted(rule["body"],
                  key=lambda l: json.dumps([l["sign"], blank(l["atom"])]))
    names = {}

    def go(t):
        if isinstance(t, str) and AO._is_var(t):
            names.setdefault(t, "_v%d" % len(names))
            return names[t]
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t

    def norm(lit):
        return [lit["sign"], [lit["atom"][0]] + [go(a) for a in lit["atom"][1:]]]
    return [norm(l) for l in body], norm(rule["head"])


def canonical(rule):
    """The rule up to bound-variable renaming, as one comparable string."""
    body, head = canonical_parts(rule)
    return json.dumps([body, head], sort_keys=True)


def printed(rule):
    """The rule back in the grammar it was written in, one line.

    `display_atom` renames each atom on its own, so the whole rule goes through
    one shared renaming here instead: a rule whose two atoms share a variable
    must print as sharing it.
    """
    names, order = {}, []
    for lit in rule["body"] + [rule["head"]]:
        for a in lit["atom"][1:]:
            for v in _stage2_vars(a):
                if v not in names:
                    i = len(order)
                    names[v] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                                else "?V%d" % (i + 1))
                    order.append(v)

    def show(lit):
        atom = _rename_s2(lit["atom"], names)
        return UA.print_atom(atom, negated=lit["sign"] == "-")
    return "%s -> %s" % (" AND ".join(show(l) for l in rule["body"]),
                         show(rule["head"]))


def _stage2_vars(term):
    out = []
    if isinstance(term, str):
        if AO._is_var(term):
            out.append(term)
    elif isinstance(term, list):
        for x in term[1:]:
            out.extend(_stage2_vars(x))
    return out


def _rename_s2(atom, names):
    def go(t):
        if isinstance(t, str) and AO._is_var(t):
            return names.get(t, t)
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


# --------------------------------------------------------------- source rules

def stage2_source_rules(stage2):
    """The passage's OWN rules, in the same canonical form.

    Used for one rejection only: a proposed rule byte-identical to something the
    theory already states adds nothing and costs a slot.
    """
    out = []

    def conjuncts(node):
        if isinstance(node, list) and node and node[0] == "and":
            got = []
            for ch in node[1:]:
                got.extend(conjuncts(ch))
            return got
        return [node]

    def as_literal(node):
        if isinstance(node, list) and len(node) == 2 and node[0] == "not":
            inner = node[1]
            if isinstance(inner, list) and inner and isinstance(inner[0], str):
                return {"sign": "-", "atom": list(inner)}
            return None
        if isinstance(node, list) and node and isinstance(node[0], str) \
                and node[0] not in AO.LOGICAL_HEADS:
            return {"sign": "+", "atom": list(node)}
        return None

    def walk(node):
        if not isinstance(node, list) or not node:
            return
        head = node[0]
        if head in ("holds", "question") and len(node) >= 2:
            walk(node[-1])
            return
        if head == "ask" and len(node) == 3:
            walk(node[2])
            return
        if head in ("forall", "exists") and len(node) >= 3:
            walk(node[2])
            return
        if head == "normally" and len(node) == 2:
            walk(node[1])
            return
        if head == "and":
            for ch in node[1:]:
                walk(ch)
            return
        if head == "implies" and len(node) == 3:
            body, concl = node[1], node[2]
            if isinstance(concl, list) and concl and concl[0] == "normally":
                concl = concl[1]
            lits = [as_literal(c) for c in conjuncts(body)]
            h = as_literal(concl)
            if h is not None and all(l is not None for l in lits) and lits:
                out.append({"body": lits, "head": h})
            return

    for _uid, pkg in AO.packages(stage2):
        walk(pkg)
    return out


# ---------------------------------------------------------------- validation

def _args_ok(atom):
    for a in atom[1:]:
        if not isinstance(a, str):
            return False
    return True


def _atom_vars(atom):
    return set(v for a in atom[1:] for v in _stage2_vars(a))


def validate(rule, vocabulary, source_rule_keys=()):
    """-> list of refusal reasons.  Empty means the rule is admitted to GK.

    Every reason is mechanical.  Nothing here judges whether the rule is TRUE.
    """
    why = []
    body, head = rule["body"], rule["head"]
    if not body:
        why.append("no body literal")
    if len(body) > MAX_BODY_LITERALS:
        why.append("more than %d body literals" % MAX_BODY_LITERALS)
    preds = vocabulary["predicates"]
    arities = vocabulary["arities"]
    constants = set(vocabulary["constants"])
    closed = vocabulary["named_entity_only_positions"]
    label_slots = vocabulary["label_slots"]
    for lit in body + [head]:
        atom = lit["atom"]
        pred = str(atom[0])
        args = list(atom[1:])
        if not _args_ok(atom):
            why.append("an argument that is not a plain word or variable: %s"
                       % json.dumps(atom)[:70])
            continue
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
            key = UA.position_key(pred, args, i)
            if AO._is_var(a):
                if i in label_slots.get(pred, ()):
                    why.append("a variable in the content-label position of "
                               "`%s`" % pred)
                elif key in closed:
                    why.append("a variable where the display only ever had the "
                               "named thing %s" % ", ".join(closed[key]))
                continue
            if a in FORBIDDEN_WORDS:
                why.append("asserts `%s`" % a)
                continue
            if a not in constants:
                why.append("`%s` was never displayed" % a)
            elif i in label_slots.get(pred, ()) and \
                    a not in vocabulary.get("labels_per_predicate",
                                            {}).get(pred, ()):
                why.append("`%s` was never displayed as a content label of "
                           "`%s`" % (a, pred))
    body_vars = set()
    for lit in body:
        body_vars |= _atom_vars(lit["atom"])
    free = _atom_vars(head["atom"]) - body_vars
    if free:
        why.append("the conclusion uses %s, which the body never binds"
                   % ", ".join(sorted(free)))
    cbody, chead = canonical_parts(rule)
    if chead in cbody:
        why.append("a tautology: the conclusion is one of its own premises")
    key = json.dumps([cbody, chead], sort_keys=True)
    if key in set(source_rule_keys):
        why.append("identical to a rule the passage already states")
    return why


# ------------------------------------------------------------------- parsing

def parse_response(text, vocabulary, source_rules=(), max_rules=MAX_RULES_PER_CALL):
    """-> {accepted, rejected, over_cap, readable_lines, prose_lines}.

    Accepted rules are deduplicated up to bound-variable renaming; every
    original line that produced one is kept as its provenance.
    """
    lines = (text or "").splitlines()
    rule_lines = [l for l in lines if RULE_PREFIX.match(l)]
    keys = set(canonical(r) for r in source_rules or [])
    accepted, by_key, rejected, over_cap = [], {}, [], []
    for raw in rule_lines:
        line = raw.strip()
        try:
            parsed = parse_line(line)
        except RuleError as e:
            rejected.append({"line": line[:200], "reasons": [str(e)]})
            continue
        rule = to_stage2_variables(parsed)
        why = validate(rule, vocabulary, keys)
        if why:
            rejected.append({"line": line[:200], "reasons": why,
                             "printed": _safe_printed(rule)})
            continue
        key = canonical(rule)
        if key in by_key:
            by_key[key]["lines"].append(line[:200])
            continue
        if len(accepted) >= max_rules:
            over_cap.append({"line": line[:200],
                             "why": "beyond the %d-rule limit for one call"
                                    % max_rules})
            continue
        entry = {"rule_id": "R%d" % (len(accepted) + 1),
                 "body": rule["body"], "head": rule["head"],
                 "canonical": key, "printed": _safe_printed(rule),
                 "lines": [line[:200]]}
        by_key[key] = entry
        accepted.append(entry)
    return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
            "readable_lines": len(rule_lines),
            "response_lines": len(lines),
            "rejection_reasons": sorted(set(r for x in rejected
                                            for r in x["reasons"]))[:20]}


def _safe_printed(rule):
    try:
        return printed(rule)
    except Exception:                                       # pragma: no cover
        return json.dumps([rule["body"], rule["head"]])[:200]


def merge(previous, new, max_total=None):
    """Accumulate rules across rounds, keeping one entry per canonical rule."""
    out = list(previous)
    seen = dict((r["canonical"], r) for r in out)
    added = []
    for r in new:
        if r["canonical"] in seen:
            seen[r["canonical"]]["lines"].extend(r["lines"])
            continue
        if max_total is not None and len(out) >= max_total:
            break
        entry = dict(r, rule_id="R%d" % (len(out) + 1))
        seen[entry["canonical"]] = entry
        out.append(entry)
        added.append(entry)
    return out, added
