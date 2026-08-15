"""The accepted formalizations, parsed once and pinned against fixtures.

`tests/external/formalized_37_sol.json` records, per case, the rule a reviewer
accepted, written in a compact text notation:

    is rel2(member of,X,O,C1) => is rel2(part of,X,O,C2)
    isa(precipitation,hail) & isa(precipitation,sleet) => -=(hail,sleet)

The previous scorer never read it, so four new case studies were recorded as
having no reviewed connection when they had one, and eb2-0127's admitted
one-premise rule was never compared with the reviewed two-premise rule.

Parsing someone else's notation is exactly where a scorer can quietly invent
agreement, so every case this module is asked about carries an explicit
expected structure in `FIXTURES`, and `check_fixtures()` compares the parse
against it.  A case whose parse does not match its fixture is reported
`parse_status: "mismatch"` and is never used for scoring.

The trailing context argument (`C1`, `C2`, `C`) is dropped: Stage-2 rules do not
carry one — conversion adds it — so keeping it would misalign every arity.
"""

import json
import os
import re

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tests", "external", "formalized_37_sol.json")

CONTEXT_ARG = re.compile(r"^C\d*$")


class ParseError(Exception):
    pass


# ---------------------------------------------------------------- parsing

def _split_top(text, sep):
    """Split on `sep` at bracket depth zero."""
    out, depth, cur, i = [], 0, "", 0
    while i < len(text):
        ch = text[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if depth == 0 and text.startswith(sep, i):
            out.append(cur)
            cur = ""
            i += len(sep)
            continue
        cur += ch
        i += 1
    out.append(cur)
    return [x.strip() for x in out if x.strip()]


def _term(text):
    """One argument.  A bracket term is a list; a quoted token loses its quotes.

    `json.loads` is not enough: the notation writes bare variables inside
    brackets — `["eventprop","$source",S]` — which is not JSON.  Each element is
    parsed the same way instead.
    """
    t = text.strip()
    if t.startswith("[") and t.endswith("]"):
        return [_term(x) for x in _split_top(t[1:-1], ",")]
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    return t


def parse_literal(text):
    """-> (sign, predicate, [args]), context argument still attached."""
    t = text.strip()
    sign = "+"
    while t.startswith("-"):
        sign = "-" if sign == "+" else "+"
        t = t[1:].strip()
    i = t.find("(")
    if i < 0 or not t.endswith(")"):
        raise ParseError("not a literal: %r" % text)
    pred = t[:i].strip()
    args = [_term(a) for a in _split_top(t[i + 1:-1], ",")]
    if not pred:
        raise ParseError("no predicate in %r" % text)
    return (sign, pred, args)


def _context_names(literals):
    """Which `C`-shaped names in this rule are really the context argument.

    Dropping every trailing `C`-shaped argument is wrong: eb2-0121 writes
    `isa(plant cell,C) & has part(O,C,C1) & isa(onion,O) => isa(onion cell,C)`,
    where `C` is the cell and only `C1` is the context.  A context name is one
    that occurs nowhere except in a literal's final position — `C` there occurs
    second of three in `has part`, so it is kept.
    """
    cand, disqualified = set(), set()
    for _, _, args in literals:
        for i, a in enumerate(args):
            if not (isinstance(a, str) and CONTEXT_ARG.match(a)):
                continue
            if i == len(args) - 1:
                cand.add(a)
            else:
                disqualified.add(a)
    return cand - disqualified


def _strip_context(lit, names):
    sign, pred, args = lit
    if args and isinstance(args[-1], str) and args[-1] in names:
        args = args[:-1]
    return (sign, pred, args)


class UnsupportedForm(ParseError):
    """A reviewed rule outside the shape a bridge can take."""


def parse_rule(line):
    """-> {"antecedents": [...], "consequent": ...} for one `A & B => C`.

    Two reviewed shapes are refused rather than approximated, because a bridge
    cannot take either and pretending otherwise would score a case as coverable
    when the compiler could never produce it:

      * an existentially quantified consequent, `=> exists E (...)`;
      * a conjunctive consequent, `=> isa(activity,E) & has type(E,happen,C)`.
    """
    parts = _split_top(line, "=>")
    if len(parts) != 2:
        raise ParseError("not one implication: %r" % line)
    head = parts[1].strip()
    if head.startswith("exists "):
        raise UnsupportedForm("existentially quantified consequent: %r" % head)
    if len(_split_top(head, "&")) > 1:
        raise UnsupportedForm("conjunctive consequent: %r" % head)
    ants = [parse_literal(x) for x in _split_top(parts[0], "&")]
    cons = parse_literal(head)
    if not ants:
        raise ParseError("no antecedent in %r" % line)
    names = _context_names(ants + [cons])
    return {"antecedents": [_strip_context(a, names) for a in ants],
            "consequent": _strip_context(cons, names),
            "dropped_context": [_dropped(a, names) for a in ants + [cons]]}


def _dropped(lit, names):
    args = lit[2]
    if args and isinstance(args[-1], str) and args[-1] in names:
        return args[-1]
    return None


# ------------------------------------------------------------ round trip
#
# A parser that silently drops or reorders an argument would still produce a
# self-consistent structure, and the fixtures alone cannot see that: they were
# written by reading the same text.  So the parse is also rendered back and
# compared with the stored line, ignoring only whitespace and the context
# argument the parse documents dropping.

def _render_term(t):
    import alignment_occurrences as AO
    if isinstance(t, list):
        return "[%s]" % ",".join(_render_term(x) for x in t)
    return t if AO._is_var(t) else '"%s"' % t


def _render_literal(lit, context=None):
    sign, pred, args = lit
    out = list(args) + ([context] if context else [])
    rendered = []
    for a in out:
        rendered.append(a if isinstance(a, str) and not a.startswith("[")
                        else _render_term(a))
    return "%s%s(%s)" % ("-" if sign == "-" else "", pred, ",".join(
        x if isinstance(x, str) else _render_term(x) for x in rendered))


def render_rule(rule):
    """The parse, written back in the source notation."""
    ctx = rule.get("dropped_context") or [None] * (len(rule["antecedents"]) + 1)
    ants = [_render_literal(a, ctx[i] if i < len(ctx) else None)
            for i, a in enumerate(rule["antecedents"])]
    cons = _render_literal(rule["consequent"], ctx[-1] if ctx else None)
    return "%s => %s" % (" & ".join(ants), cons)


def _squash(text):
    return "".join(text.split()).replace('"', "").replace("'", "")


def round_trip(case_id, cases=None):
    """-> {"ok", "lines": [{"source", "rendered", "matches"}]}.

    Compares the stored `formal_rule` text with the parse rendered back, modulo
    whitespace and quoting.  A mismatch means the parse is not the text.
    """
    got = reviewed_rules(case_id, cases)
    text = got.get("formal_rule_text")
    if not got["rules"] or not text:
        return {"ok": got["parse_status"] in ("no_rule",), "lines": [],
                "parse_status": got["parse_status"]}
    lines = [l for l in text.splitlines() if l.strip()]
    out = []
    for line, rule in zip(lines, got["rules"]):
        r = render_rule(rule)
        out.append({"source": line.strip(), "rendered": r,
                    "matches": _squash(line) == _squash(r)})
    return {"ok": len(lines) == len(got["rules"])
            and all(x["matches"] for x in out),
            "lines": out, "parse_status": got["parse_status"]}


def check_round_trips(cases=None):
    """-> {case: ok}.  Every fixture, rendered back and compared."""
    cases = cases if cases is not None else load()
    return {cid: round_trip(cid, cases)["ok"] for cid in FIXTURES}


def parse_formal_rule(text):
    """-> [rule, ...] for the possibly multi-line `formal_rule` field."""
    out = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        out.append(parse_rule(line))
    return out


# ---------------------------------------------------------------- fixtures
#
# One expected structure per case this module may be asked about.  A parse that
# does not reproduce its fixture is not used.  Written by reading the recorded
# `formal_rule` text, not generated from the parser.

def L(sign, pred, *args):
    return (sign, pred, list(args))


FIXTURES = {
    "eb2-0020": [
        {"antecedents": [L("+", "is rel2", "part of", "X", "D")],
         "consequent": L("+", "is rel2", "in", "X", "D")},
        {"antecedents": [L("+", "is rel2", "part of", "X", "D")],
         "consequent": L("+", "have", "D", "X")},
    ],
    "eb2-0099": [
        {"antecedents": [L("+", "isa", "surface", "S"),
                         L("+", "is rel2", "reflect", "sound",
                           ["eventprop", "$source", "S"])],
         "consequent": L("+", "has property", "produce", "echo")},
    ],
    "eb2-0127": [
        {"antecedents": [L("+", "isa", "precipitation", "hail"),
                         L("+", "isa", "precipitation", "sleet")],
         "consequent": L("-", "=", "hail", "sleet")},
    ],
    "mle2-0029": [
        {"antecedents": [L("+", "has property", "motivated", "#:Tigers 3")],
         "consequent": L("+", "has property", "motivated", "#:players 6")},
        {"antecedents": [L("+", "is rel2", "win", "#:players 6",
                           ["eventprop", "$target", "G"])],
         "consequent": L("+", "is rel2", "win", "#:Tigers 3",
                         ["eventprop", "$target", "G"])},
    ],
    "folio-0169": [
        {"antecedents": [L("+", "is rel2", "member of", "X", "O")],
         "consequent": L("+", "is rel2", "part of", "X", "O")},
    ],
    "eb2-0049": [
        {"antecedents": [L("+", "isa", "snapdragon plant", "X")],
         "consequent": L("+", "isa", "living thing", "X")},
    ],
    "folio-0080": [
        {"antecedents": [L("+", "is rel2", "product of", "X", "O")],
         "consequent": L("+", "is rel2", "from", "X", "O")},
    ],
    "folio-0183": [
        {"antecedents": [L("+", "is rel2", "loving", "X", "A"),
                         L("+", "isa", "animal", "A")],
         "consequent": L("+", "isa", "animal lover", "X")},
    ],
    "folio-0184": [
        {"antecedents": [L("+", "is rel2", "love", "X", "A"),
                         L("+", "isa", "animal", "A")],
         "consequent": L("+", "isa", "animal lover", "X")},
    ],
    "eb2-0121": [
        {"antecedents": [L("+", "isa", "plant cell", "C"),
                         L("+", "has part", "O", "C"),
                         L("+", "isa", "onion", "O")],
         "consequent": L("+", "isa", "onion cell", "C")},
    ],
    # ---- cohort-extension candidates.  Written from the stored text, and each
    # one additionally checked by `round_trip`, which re-renders the parse and
    # compares it with that text.  A case whose reviewed rule has an existential
    # or conjunctive consequent gets no fixture: `parse_status` is then
    # `unsupported_form`, which is the honest answer — a bridge cannot take that
    # shape, so the case is not coverable by construction.
    "eb-0001": [
        {"antecedents": [L("+", "has type", "E", "refract")],
         "consequent": L("+", "isa", "refraction", "E")},
    ],
    "eb-0006": [
        {"antecedents": [L("+", "isa", "communication", "X")],
         "consequent": L("+", "isa", "sharing", "X")},
        {"antecedents": [L("+", "isa", "communication", "X"),
                         L("+", "isa", "information", "I")],
         "consequent": L("+", "is rel2", "sharing of", "X", "I")},
    ],
    "eb-0035": [
        {"antecedents": [L("+", "isa", "element", "X")],
         "consequent": L("+", "isa", "pure substance", "X")},
    ],
    "eb-0107": [
        {"antecedents": [L("+", "is rel2", "made of", "O", "M"),
                         L("+", "has property", "P", "M")],
         "consequent": L("+", "has property", "P", "O")},
    ],
    "eb2-0009": [
        {"antecedents": [L("+", "isa", "organism", "Y"),
                         L("+", "has property", "dead", "Y")],
         "consequent": L("+", "isa", "organic matter", "Y")},
    ],
    "eb2-0010": [
        {"antecedents": [L("+", "is rel2", "in", "A", "B"),
                         L("+", "is rel2", "in", "B", "D")],
         "consequent": L("+", "is rel2", "in", "A", "D")},
    ],
    "eb2-0046": [
        {"antecedents": [L("+", "isa", "inherited trait", "T"),
                         L("+", "is rel2", "inherit", "X",
                           ["eventprop", "$target", "T"])],
         "consequent": L("+", "is rel2", "inherit", "X",
                         ["eventprop", "$target", "trait"])},
    ],
    "eb2-0055": [
        {"antecedents": [L("+", "is rel2", "made of", "W", "P"),
                         L("+", "have", "P", "M")],
         "consequent": L("+", "is rel2", "in", "M", "W")},
    ],
    "folio-0041": [
        {"antecedents": [L("+", "isa", "design", "X"),
                         L("+", "is rel2", "design by", "X", "M")],
         "consequent": L("+", "is rel2", "adored by", "X", "M")},
    ],
    "folio-0042": [
        {"antecedents": [L("+", "is rel2", "design by", "X", "D")],
         "consequent": L("+", "is rel2", "design style of", "X", "D")},
    ],
    "folio-0143": [
        {"antecedents": [L("+", "has property", "breed back", "X"),
                         L("+", "is rel2", "of", "breeding back",
                           "artificial selection")],
         "consequent": L("+", "has property", "artificially selected", "X")},
    ],
    "mle-0004": [
        {"antecedents": [L("+", "has type", "E", "fumble"),
                         L("+", "has manner", "E", "a lot")],
         "consequent": L("+", "has manner", "E", "multiple times")},
    ],
    "mle-0082": [
        {"antecedents": [L("+", "isa", "activity", "E"),
                         L("+", "has type", "E", "gain"),
                         L("+", "has actor", "E", "A"),
                         L("+", "has target", "E", "K"),
                         L("+", "isa", "knowledge", "K")],
         "consequent": L("+", "have", "A", "K")},
    ],
    "mle-0086": [
        {"antecedents": [L("+", "isa", "activity", "E"),
                         L("+", "has type", "E", "improve"),
                         L("+", "has actor", "E",
                           ["$theof1", "quality", "S", "C1"])],
         "consequent": L("+", "has property", "high quality", "S")},
    ],
    "mle2-0049": [
        {"antecedents": [L("+", "isa", "sunflower seed", "X")],
         "consequent": L("+", "isa", "seed", "X")},
    ],
    # recorded with `formal_rule: null` and `antecedent_supported: no` — the
    # reviewer's own note calls it one of the anticipated
    # cannot-be-formalised-soundly cases.  It has no reviewed rule at all.
    "eb-0140": [],
}


def _norm(rule):
    return {"antecedents": [(s, p, list(a)) for s, p, a in rule["antecedents"]],
            "consequent": (rule["consequent"][0], rule["consequent"][1],
                           list(rule["consequent"][2]))}


def load(path=None):
    with open(path or PATH) as f:
        return json.load(f)["cases"]


def reviewed_rules(case_id, cases=None):
    """-> {"rules": [...], "parse_status": ..., "record": {...}}.

    `parse_status` is one of `ok`, `no_rule`, `no_fixture`, `mismatch`,
    `parse_error`.  Only `ok` (and `no_rule`, which means the reviewer recorded
    none) may be used for scoring.
    """
    cases = cases if cases is not None else load()
    rec = cases.get(case_id)
    if rec is None:
        return {"rules": [], "parse_status": "absent", "record": None}
    text = rec.get("formal_rule")
    out = {"record": {k: rec.get(k) for k in
                      ("connection_status", "confidence", "rule_targets",
                       "tree", "encoding_of_case_correct",
                       "antecedent_supported", "conclusion_wanted", "notes")},
           "formal_rule_text": text}
    # An unsupported shape is reported even without a fixture: writing one for a
    # rule a bridge can never take would be writing a fixture for nothing.
    if text:
        try:
            parse_formal_rule(text)
        except UnsupportedForm as e:
            out.update({"rules": [], "parse_status": "unsupported_form",
                        "why": str(e)})
            return out
        except ParseError:
            pass
    if case_id not in FIXTURES:
        out.update({"rules": [], "parse_status": "no_fixture"})
        return out
    if not text:
        out.update({"rules": [], "parse_status": "no_rule",
                    "why": "the reviewer recorded no formalisable rule"})
        return out
    try:
        rules = parse_formal_rule(text)
    except UnsupportedForm as e:
        out.update({"rules": [], "parse_status": "unsupported_form",
                    "why": str(e)})
        return out
    except ParseError as e:
        out.update({"rules": [], "parse_status": "parse_error", "why": str(e)})
        return out
    want = FIXTURES[case_id]
    if [_norm(r) for r in rules] != [_norm(r) for r in want]:
        out.update({"rules": [], "parse_status": "mismatch",
                    "parsed": rules, "fixture": want})
        return out
    out.update({"rules": rules, "parse_status": "ok"})
    return out


def check_fixtures(cases=None):
    """-> {case: parse_status}.  Every fixture, checked."""
    cases = cases if cases is not None else load()
    return {cid: reviewed_rules(cid, cases)["parse_status"] for cid in FIXTURES}


# ------------------------------------------------------------ as a package
#
# One comparison engine, not two.  `alignment_compare` already maintains a
# bijection between the two rules' variables, distinguishes a grounded constant
# from a quantified variable in each direction, detects reversal and argument
# swaps, and separates a predicate-family difference from a missing condition.
# The pairwise matcher below it does none of that, and treating its verdict as
# agreement is how a reviewed `p(X,Y) -> q(X,Y)` matched a compiled
# `p(Z,Z) -> q(Z,Z)`.  Reviewed rules are therefore turned into rule packages
# and put through the same engine as everything else.

def _atom(lit):
    sign, pred, args = lit
    atom = [pred] + list(args)
    return ["not", atom] if sign == "-" else atom


def to_package(rule, world="W0", defeasible=True):
    """A reviewed rule as a Stage-2 rule package.

    Quantified over every variable it mentions, in first-appearance order, and
    written `BODY -> normally(HEAD)` by default: every dynamic bridge is
    compiled defeasible by fixed policy, so strength is not a degree of freedom
    the comparison should spend on.  The reviewer's own `connection_status` is
    reported separately.
    """
    import alignment_occurrences as AO
    body = [_atom(a) for a in rule["antecedents"]]
    head = _atom(rule["consequent"])
    if defeasible:
        head = ["normally", head]
    f = ["implies", body[0] if len(body) == 1 else ["and"] + body, head]
    seen = []
    for lit in rule["antecedents"] + [rule["consequent"]]:
        for a in lit[2]:
            for v in _vars(a):
                if v not in seen:
                    seen.append(v)
    for v in reversed(seen):
        f = ["forall", v, f]
    return ["holds", world, f]


def _vars(term):
    import alignment_occurrences as AO
    if isinstance(term, str):
        return [term] if AO._is_var(term) else []
    if isinstance(term, list):
        return [v for x in term for v in _vars(x)]
    return []


def classify(rule, compiled_pkg):
    """How a compiled rule stands to one reviewed rule, by the shared engine.

    -> `alignment_compare.classify`'s result, with the reviewed package added.
    """
    import alignment_compare as CMP
    pkg = to_package(rule)
    out = CMP.classify(compiled_pkg, pkg)
    out["reviewed_package"] = pkg
    return out


# ------------------------------------------------- superseded pairwise matcher
#
# Kept because the first correction's artifact and tool were produced with it.
# It does NOT maintain a bijection and it treats a compiled variable standing in
# for a reviewed constant as agreement, so it must not be used for any coverage
# claim.  Use `classify` above.

def _label_and_participants(sign, pred, args):
    import alignment_occurrences as AO
    slot = AO.LABEL_SLOT.get(pred)
    label = args[slot] if (slot is not None and slot < len(args)) else pred
    parts = [a for i, a in enumerate(args) if i != slot]
    return str(label), parts


def _lit_key(lit):
    import alignment_occurrences as AO
    sign, pred, args = lit
    label, parts = _label_and_participants(sign, pred, args)
    return (sign, pred, AO.normalize_label(label), len(parts)), parts


def literal_agrees(reviewed, compiled, subst):
    """Same sign, predicate, label and arity, under a consistent renaming."""
    import alignment_occurrences as AO
    ka, pa = _lit_key(reviewed)
    kb, pb = _lit_key(compiled)
    if ka != kb:
        return False, subst
    sub = dict(subst)
    for x, y in zip(pa, pb):
        xv = isinstance(x, str) and AO._is_var(x)
        yv = isinstance(y, str) and AO._is_var(y)
        kx = x if xv else (AO.normalize_label(x) if isinstance(x, str)
                           else json.dumps(x, sort_keys=True))
        ky = y if yv else (AO.normalize_label(y) if isinstance(y, str)
                           else json.dumps(y, sort_keys=True))
        if xv and yv:
            if sub.setdefault(("v", x), y) != y:
                return False, subst
        elif xv:
            if sub.setdefault(("v", x), ky) != ky:
                return False, subst
        elif yv:
            pass          # the compiled rule generalises where the reviewed one
                          # names something: a difference, recorded by the
                          # caller, not a disagreement about which literal it is
        elif kx != ky:
            return False, subst
    return True, sub


def compare(reviewed_rule, compiled):
    """How a compiled rule stands to one reviewed rule.

    `compiled` is `alignment_compare.parse_rule_package`'s output.

    -> {"consequent_agrees", "antecedents_matched", "missing_antecedents",
        "extra_antecedents", "complete"}
    """
    ok, sub = literal_agrees(reviewed_rule["consequent"],
                             (compiled["consequent"][0],
                              compiled["consequent"][1],
                              compiled["consequent"][2]), {})
    out = {"consequent_agrees": ok, "missing_antecedents": [],
           "extra_antecedents": [], "antecedents_matched": 0}
    comp_ants = [(a[0], a[1], a[2]) for a in compiled["antecedents"]]
    used = set()
    for r in reviewed_rule["antecedents"]:
        hit = None
        for i, cmp_a in enumerate(comp_ants):
            if i in used:
                continue
            ok2, sub2 = literal_agrees(r, cmp_a, sub)
            if ok2:
                hit, sub = i, sub2
                break
        if hit is None:
            out["missing_antecedents"].append(_show(r))
        else:
            used.add(hit)
            out["antecedents_matched"] += 1
    out["extra_antecedents"] = [_show(a) for i, a in enumerate(comp_ants)
                                if i not in used]
    out["complete"] = bool(out["consequent_agrees"]
                           and not out["missing_antecedents"])
    return out


def _show(lit):
    sign, pred, args = lit
    return "%s%s(%s)" % ("" if sign == "+" else "not ", pred,
                         ", ".join(x if isinstance(x, str) else json.dumps(x)
                                   for x in args))
