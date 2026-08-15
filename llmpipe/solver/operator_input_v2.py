"""What the model is shown, version 2.

Two changes over v1, both of them things the v1 prompt got wrong rather than
merely said briefly.

The groups were labelled "what the prover needed and could not get".  The
regression that produced them usually located an unresolved interface but often
could not decide whether the demand was genuinely unsupplied — AL-65 left half
its branches undecided on a node budget.  Calling them settled demands overstates
the evidence, and a model told that something is definitely missing will look for
something to add.  They are candidate expressions near an unresolved interface,
and the prompt now says so.

And the operators are shown with their SLOTS, generated from the same
declarations that validate the reply, so the model can see that `compound_head`
needs a link and `argument_label_promotion` needs a premise as well as a
carrier.  In AL-68 that contract existed only in an artifact the model never saw,
and two of the five misses were the model naming too few sources.

Nothing here reads a reviewed rule or an expected answer.
"""

import construction_slots as CS
import operator_input as OI

VERSION = "operator_input_v2/2.0"


def render(case, operators=None):
    """The case as the v2 prompt shows it.  Deterministic; no gold, no answer."""
    L = []
    L.append("THE PROBLEM")
    L.append("")
    L.append((case["input_text"] or "").strip())
    L.append("")
    L.append("WHAT THE TRANSLATION PRODUCED")
    L.append("")
    L.append("Each line is one atom, with the role of the sentence it came "
             "from. A line marked `question` comes from the question: it gives "
             "you the words and the shape at issue and asserts nothing.")
    L.append("")
    by_unit = {}
    for r in case["occurrences"]:
        by_unit.setdefault(r["unit"], []).append(r)
    for unit in sorted(by_unit, key=OI._unit_key):
        rows = by_unit[unit]
        sent = (rows[0].get("sentence") or "").strip()
        L.append("  %s  %s" % (unit, sent))
        for r in rows:
            L.append("    %-5s %-16s %s" % (r["oid"], r["role"], r["shown"]))
        L.append("")
    L.append("WORDS THIS PROBLEM USES")
    L.append("")
    L.append("A word marked `argument only` never appears as a predicate "
             "label: the logic can talk about it, but nothing can BE it.")
    L.append("")
    for e in case["labels"]:
        where = ("argument only" if e["argument_only"] else
                 "predicate label" if not e["as_argument"] else
                 "predicate label and argument")
        kind = CS.term_type(e["text"])
        L.append("  %-5s %-30s %-28s %s"
                 % (e["lid"], e["text"][:30], where,
                    "" if kind == CS.CONCEPT else "(%s)" % kind))
    L.append("")
    L.append("EXPRESSIONS NEAR THE UNRESOLVED INTERFACE")
    L.append("")
    L.append("These are expressions the prover was working on when it stopped. "
             "They are candidates, not settled facts: the search that found "
             "them often could not decide whether an expression was really "
             "unavailable or merely not reached. Treat them as a place to "
             "look, not as proof that something is missing.")
    L.append("")
    for g in case["groups"]:
        L.append("  %-5s %s" % (g["group_id"], g["readable"]))
    L.append("")
    L.append("THE OPERATORS")
    L.append("")
    L.append(CS.operator_cards(operators))
    return "\n".join(L)
