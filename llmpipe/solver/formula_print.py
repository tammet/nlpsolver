"""Deterministic printer for Stage-2 formulas.

Prints the formula itself — explicit quantifiers, explicit parentheses, one
symbol per connective — and never an English paraphrase.  A paraphrase is what
the verifier was previously left to reconstruct from JSON, and it misread two
correct rules doing so; a paraphrase generated here would only move that risk
into code that cannot be checked against the sentence.

    forall X . ( isa(dog, X) -> isa(animal, X) )

No LLM calls, no GK, no dependency on the rest of the pipeline.
"""

import re

VAR_RE = re.compile(r"^[A-Z][A-Za-z0-9_]*$")

QUANT = {"forall": "forall", "exists": "exists"}
INFIX = {"and": "&", "or": "|", "implies": "->"}


def _is_var(t):
    return isinstance(t, str) and bool(VAR_RE.match(t))


def term(t):
    """One argument.  Variables are marked so a constant cannot be mistaken
    for one; a constant with spaces is quoted."""
    if isinstance(t, list):
        return "[%s]" % ", ".join(term(x) for x in t)
    if _is_var(t):
        return "?%s" % t
    s = str(t)
    return '"%s"' % s if (" " in s or not s) else s


def formula(f, top=True):
    """A formula as text.  Parentheses are always explicit around a
    multi-argument connective, so no reader has to guess the scope."""
    if not isinstance(f, list) or not f:
        return term(f)
    head = f[0]
    if not isinstance(head, str):
        return "[%s]" % ", ".join(formula(x, False) for x in f)
    if head in QUANT and len(f) >= 3:
        return "%s %s . %s" % (QUANT[head], term(f[1]), formula(f[2], False))
    if head == "implies" and len(f) == 3:
        return "( %s -> %s )" % (formula(f[1], False), formula(f[2], False))
    if head in ("and", "or") and len(f) >= 2:
        joined = (" %s " % INFIX[head]).join(formula(x, False) for x in f[1:])
        return "( %s )" % joined
    if head == "not" and len(f) == 2:
        return "not %s" % formula(f[1], False)
    if head == "normally" and len(f) == 2:
        return "normally %s" % formula(f[1], False)
    if head == "holds" and len(f) == 3:
        # the world is a constant even though it looks like a variable
        return "in %s: %s" % (f[1], formula(f[2], False))
    if head == "question" and len(f) == 2:
        return "question: %s" % formula(f[1], False)
    if head == "ask" and len(f) == 3:
        return "ask %s: %s" % (term(f[1]), formula(f[2], False))
    # a predicate atom
    return "%s(%s)" % (head, ", ".join(term(a) for a in f[1:]))


def package(pkg):
    return formula(pkg)


def lines(pkg, indent="  "):
    """The same text, broken after each top-level connective, for prompts."""
    text = formula(pkg)
    out, depth, cur = [], 0, ""
    for ch in text:
        cur += ch
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and cur.strip().endswith(("->", "&", "|")):
            out.append(cur.strip())
            cur = ""
    if cur.strip():
        out.append(cur.strip())
    return "\n".join(indent + l for l in out) if len(out) > 1 else indent + text
