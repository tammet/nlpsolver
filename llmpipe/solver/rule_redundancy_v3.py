import litbridge_atoms as atoms
"""Is this compiled rule already a clause the theory has? (WP4.3)

`eb2-0039` refused `recessive trait(X) -> trait(X)` with a message about a
constant.  The real reason is that the converter already emitted

    compound_sub:  -isa(recessive trait, ?:X) | isa(trait, ?:X)

which is that rule.  The check is deliberately narrow: EXACT equality up to
literal order and bound-variable renaming, after removing the bridge's own
`$block` guard.  Broad semantic subsumption is a different question and is not
attempted here — a rule that merely follows from the theory is still a rule the
theory does not contain, and letting it through costs one clause.
"""

import itertools
import json


VERSION = "rule_redundancy_v3/1.0"

MAX_PERMUTATIONS = 720          # 6! — a clause longer than that is not matched


BLOCK = "$block"


def strip_block(clause):
    """The clause's literals without the guard a bridge carries.

    ONLY `$block` is removed.  Removing every control literal instead made the
    question clause `-$defq0 | -in(X,Animal) | have(Eukaryote,X)` look exactly
    like the bridge `in(X,Animal) -> belong to(X,Eukaryote)`, and the one
    defensible proof of the whole v2 pilot was refused as already present.  A
    clause conditional on `$defq0` asserts something different from a clause
    that is not.
    """
    out = []
    for lit in atoms.literals_of(clause.get("@logic")):
        if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
            continue
        if atoms.bare_predicate(lit[0]) == BLOCK:
            continue
        out.append(lit)
    return out


def _same_literal(a, b, mapping, back):
    """Equal up to a consistent, bijective renaming of clause variables."""
    if atoms.sign_of(a) != atoms.sign_of(b):
        return False
    x, y = atoms.unsigned_atom(a), atoms.unsigned_atom(b)
    if x[0] != y[0] or len(x) != len(y):
        return False

    def go(p, q):
        vp = isinstance(p, str) and atoms.is_variable_term(p)
        vq = isinstance(q, str) and atoms.is_variable_term(q)
        if vp or vq:
            if not (vp and vq):
                return False
            if mapping.get(p, q) != q or back.get(q, p) != p:
                return False
            mapping[p], back[q] = q, p
            return True
        if isinstance(p, str) or isinstance(q, str):
            return p == q
        if not (isinstance(p, list) and isinstance(q, list)):
            return False
        if len(p) != len(q) or p[0] != q[0]:
            return False
        return all(go(u, v) for u, v in zip(p[1:], q[1:]))
    return all(go(u, v) for u, v in zip(x[1:], y[1:]))


def alpha_equal_clause(a, b):
    """Same multiset of literals, up to one consistent variable renaming."""
    if len(a) != len(b) or not a:
        return False
    if len(a) > 6:
        return False
    for order in itertools.permutations(range(len(b))):
        mapping, back = {}, {}
        if all(_same_literal(a[i], b[j], mapping, back)
               for i, j in enumerate(order)):
            return True
    return False


def already_present(compiled_clauses, base_clauses):
    """-> the base clause name this rule already is, or None.

    Population helpers a conversion emits beside the rule are not the rule and
    are skipped; the comparison is between the rule's own clause and each base
    clause.
    """
    for c in compiled_clauses:
        if c.get("@sourcetype") == "populate":
            continue
        mine = strip_block(c)
        if not mine:
            continue
        for base in base_clauses or []:
            if not isinstance(base, dict) or "@question" in base:
                continue
            if base.get("@sourcetype") == "populate":
                continue
            theirs = strip_block(base)
            if not theirs:
                continue
            if alpha_equal_clause(mine, theirs):
                return "already present as GK clause %s" % base.get("@name")
    return None


def checker(view):
    """-> a `redundancy(rule, clauses)` callable for the world builder."""
    base = view.get("final_clauses") or []

    def check(_rule, clauses):
        return already_present(clauses, base)
    return check
