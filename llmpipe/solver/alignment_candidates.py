"""Non-lexical interface candidate generation over the occurrence table.

Retrieval portion of WP2 of
`memos/PLAN_2026_08_09_superabstract_refinement_trial_opus5.md`, isolated so it
can be validated before any shadow logic is built on top.

The question this answers: given one problem's occurrences, which directional
pairs — a producer that the theory already has, to a consumer that a rule
premise or the question requires — are worth showing a critic?

**Generation is label-independent.**  Two occurrences are never rejected for
having different words, and never enumerated for having similar ones.  Only
mechanical impossibility rejects a pair:

  * grounded constants: two different named individuals in mapped positions
    cannot be the same thing;
  * participant mapping: term positions that cannot be mapped one-to-one;
  * context: different worlds.

Polarity was expected to be a fourth rejection criterion and is not: a positive
producer meeting a negated requirement CONTRADICTS it, and that is how a False
answer is reached.  Polarity is therefore a typed relation on the candidate
(`supply` or `contradiction`), not a filter.

Everything else survives, and ranking decides what a critic sees.  So
`element -> pure substance`, `product of -> from` and
`snapdragon plant -> living thing` all survive enumeration, because nothing
about them is mechanically impossible.

Three ranking arms are provided for comparison: `structural` (shape, shared
participants, argument mapping, neighbouring conjuncts, source context),
`lexical` (the existing similarity tiers), and `fasttext` (phrase and marked
source-sentence vectors).  Vectors rank pairs; they never assert equality, and
a candidate is never merged transitively with another.

No LLM calls, no GK, no bridge compilation.
"""

import math
import os
import re

import alignment_issues as AI
import alignment_occurrences as AO

# ------------------------------------------------------------------ arms

ARMS = ("structural", "lexical", "fasttext")

# Fixed a priori, before any held-out number was computed, and not changed
# afterwards.  They express an ordering, not a fitted model: sharing a
# participant matters most, then how well the argument positions map, then the
# surrounding evidence.
STRUCTURAL_WEIGHTS = {
    "shared_participants": 3.0,
    "argument_mapping": 2.0,
    "shape_compatible": 1.5,
    "neighbour_conjuncts": 1.0,
    "same_unit": -1.0,          # a pair inside one sentence is usually not an
                                # interface between two representations
    "producer_is_fact": 0.5,
    "consumer_in_question": 0.5,
}


def _terms(o):
    """The term positions of an occurrence, label slot removed."""
    args = o.get("arguments_or_roles") or []
    slot = AO.LABEL_SLOT.get(o.get("predicate"))
    return [a for i, a in enumerate(args) if i != slot]


def _grounded(t):
    return isinstance(t, str) and not AO._is_var(t)


def _world_of(o):
    for q, v in o.get("binder_stack") or []:
        if q == "world":
            return v
    return None


# ------------------------------------------------------------------ roles

def _flip(p):
    return "-" if p == "+" else "+"


def available(o):
    """Polarities this occurrence makes AVAILABLE to a proof, or None.

    A question is not uniformly a requirement, and proof search is refutation:

      fact / rule conclusion  makes its own literal available
      question antecedent     is ASSUMED while proving an implication, so it is
                              available
      question conclusion     the prover assumes its NEGATION, so the opposite
                              literal is available — this is how a positive
                              producer meets a negated goal and answers False
      rule antecedent         makes nothing available

    Getting this wrong hides exactly the interfaces this retrieval exists to
    find: with the question treated as a pure requirement, `element -> pure
    substance` and `product of -> from` never even get enumerated.
    """
    if o["kind"] in ("rule_variable", "modal") or not AI._meaning_bearing(o):
        return None
    if o.get("in_question"):
        return {o["polarity"]} if o["rule_side"] == "antecedent" \
            else {_flip(o["polarity"])}
    return None if o["rule_side"] == "antecedent" else {o["polarity"]}


def required(o):
    """Polarities this occurrence REQUIRES, or None.

    A rule antecedent must be supplied before the rule fires; a question
    conclusion is what must be shown.  A question conclusion therefore both
    requires its own literal and (above) makes the opposite one available.
    """
    if o["kind"] in ("rule_variable", "modal") or not AI._meaning_bearing(o):
        return None
    if o.get("in_question"):
        return {o["polarity"]} if o["rule_side"] != "antecedent" else None
    return {o["polarity"]} if o["rule_side"] == "antecedent" else None


def producers(table):
    return [o for o in table["stage2"] if available(o)]


def consumers(table):
    return [o for o in table["stage2"] if required(o)]


# ------------------------------------------------------------------ rejection

def argument_mappings(p, c):
    """Injective position maps between producer and consumer term positions.

    A mapping is impossible when two positions must be identified but carry
    different grounded constants.  Positions are matched in order first; if the
    arities differ, the shorter side maps into a prefix of the longer one.  We
    do not search all permutations: an interface that needs a reordering is
    reported by `order_swapped` instead of multiplying candidates.
    """
    pt, ct = _terms(p), _terms(c)
    n = min(len(pt), len(ct))
    if n == 0:
        return [], False
    direct = list(zip(pt[:n], ct[:n]))
    swapped = None
    if len(pt) == len(ct) == 2:
        swapped = [(pt[0], ct[1]), (pt[1], ct[0])]

    def possible(pairs):
        for a, b in pairs:
            if _grounded(a) and _grounded(b) and AO.normalize_label(a) != \
                    AO.normalize_label(b):
                return False
        return True

    if possible(direct):
        return direct, False
    if swapped and possible(swapped):
        return swapped, True
    return [], False


def reject_reason(p, c):
    """-> None if the pair survives, else the mechanical reason it cannot."""
    if p["occurrence_id"] == c["occurrence_id"]:
        return "same occurrence"
    av, rq = available(p), required(c)
    if not av:
        return "the producer makes nothing available"
    if not rq:
        return "the consumer requires nothing"
    # Polarity does NOT reject.  The task listed it as a rejection criterion,
    # but the benchmark shows a polarity clash is exactly what a False answer
    # needs: a positive producer meeting a negated requirement CONTRADICTS it,
    # which is how folio-0169's reviewed `member of -> part of` interface does
    # its work.  So polarity is recorded as a typed relation (`supply` or
    # `contradiction`) and both kinds are enumerated.
    pw, cw = _world_of(p), _world_of(c)
    if pw and cw and pw != cw:
        return "different worlds (%s vs %s)" % (pw, cw)
    pt, ct = _terms(p), _terms(c)
    if not pt or not ct:
        return "no term position to map"
    mapping, _ = argument_mappings(p, c)
    if not mapping:
        return ("participant mapping impossible: %s cannot be identified with %s"
                % ([t for t in pt if _grounded(t)],
                   [t for t in ct if _grounded(t)]))
    return None


# ------------------------------------------------------------------ features

def _unit_atoms(table, unit_id):
    return [o for o in table["stage2"] if o["unit_id"] == unit_id
            and AI._meaning_bearing(o)]


def features(p, c, table):
    """Structural evidence for one surviving pair.  No word is compared."""
    mapping, swapped = argument_mappings(p, c)
    shared = 0
    for a, b in mapping:
        if _grounded(a) and _grounded(b):
            if AO.normalize_label(a) == AO.normalize_label(b):
                shared += 1
        elif AO._is_var(a) and AO._is_var(b) and a == b \
                and p["unit_id"] == c["unit_id"]:
            shared += 1
    pt, ct = _terms(p), _terms(c)
    shape = 1.0 if len(pt) == len(ct) else 0.5
    if p.get("predicate") == c.get("predicate"):
        shape += 0.5
    # neighbouring conjuncts: how much of the producer's unit shares a grounded
    # participant with the consumer's unit
    pc = set(AO.normalize_label(t) for o in _unit_atoms(table, p["unit_id"])
             for t in _terms(o) if _grounded(t))
    cc = set(AO.normalize_label(t) for o in _unit_atoms(table, c["unit_id"])
             for t in _terms(o) if _grounded(t))
    neigh = len(pc & cc)
    return {
        "shared_participants": shared,
        "argument_mapping": (len(mapping) / float(max(len(pt), len(ct))))
        if mapping else 0.0,
        "shape_compatible": shape,
        "neighbour_conjuncts": min(neigh, 3),
        "same_unit": 1.0 if p["unit_id"] == c["unit_id"] else 0.0,
        "producer_is_fact": 1.0 if p["rule_side"] == "none" else 0.0,
        "consumer_in_question": 1.0 if c.get("in_question") else 0.0,
        "order_swapped": swapped,
        # the producer is available only because the prover assumes the
        # negation of the goal: a legitimate interface, worth recording
        "refutation_interface": bool(
            c.get("in_question") and c["rule_side"] != "antecedent"
            and p["polarity"] != c["polarity"]),
        # `supply`: the producer can meet the requirement directly.
        # `contradiction`: it meets its opposite, which refutes the goal.
        # Recorded, deliberately NOT weighted: the weights were fixed before
        # any result was seen and adding one here would be tuning.
        "polarity_relation": ("supply"
                              if (available(p) or set()) & (required(c) or set())
                              else "contradiction"),
    }


def structural_score(f):
    return sum(STRUCTURAL_WEIGHTS[k] * f[k] for k in STRUCTURAL_WEIGHTS)


def lexical_score(p, c):
    """The existing similarity tiers, as a comparison arm only."""
    tier = AI.similarity_tier(AI.content_label(p), AI.content_label(c))
    return {1: 4.0, 2: 3.0, 3: 2.0, 4: 1.0}.get(tier, 0.0)


# ------------------------------------------------------------------ vectors

class Vectors(object):
    """fastText phrase vectors, loaded from the extracted subset.

    A phrase vector is the mean of its word vectors; a pair is scored by cosine
    over the source phrase, blended with cosine over the marked source
    sentence, so context contributes without drowning the phrase.  Absent
    words are skipped; a phrase with no known word scores 0 and says so.
    """

    TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*")
    PHRASE_WEIGHT = 0.7

    def __init__(self, path=None):
        self.ok = False
        self.words, self.vecs, self.index = None, None, {}
        path = path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "elogs", "fasttext_bench_subset.npz")
        try:
            import numpy as np
            d = np.load(path, allow_pickle=False)
            self.np = np
            self.words = [str(w) for w in d["words"]]
            self.vecs = d["vectors"]
            self.index = {w: i for i, w in enumerate(self.words)}
            self.ok = True
        except Exception as e:
            self.error = str(e)

    def phrase(self, text):
        if not self.ok or not text:
            return None
        rows = []
        for w in self.TOKEN.findall(text):
            i = self.index.get(w)
            if i is None:
                i = self.index.get(w.lower())
            if i is not None:
                rows.append(self.vecs[i])
        if not rows:
            return None
        v = self.np.mean(self.np.asarray(rows), axis=0)
        n = float(self.np.linalg.norm(v))
        return v / n if n else None

    def cos(self, a, b):
        if a is None or b is None:
            return None
        return float(self.np.dot(a, b))

    def marked_sentence(self, occ):
        """The source sentence with the occurrence's phrase marked.

        Marking is what makes the sentence vector about this occurrence rather
        than about the sentence as a whole; with a mean-of-words vector the
        practical effect is to weight the phrase's own words twice.
        """
        sent = occ.get("source_sentence") or ""
        quote = occ.get("source_quote")
        return ("%s %s" % (sent, quote)) if quote else sent

    def score(self, p, c):
        pp = self.phrase(p.get("source_quote") or AI.content_label(p))
        cp = self.phrase(c.get("source_quote") or AI.content_label(c))
        ps = self.phrase(self.marked_sentence(p))
        cs = self.phrase(self.marked_sentence(c))
        a, b = self.cos(pp, cp), self.cos(ps, cs)
        if a is None and b is None:
            return 0.0, "no known word"
        if a is None:
            return b, "sentence only"
        if b is None:
            return a, "phrase only"
        return self.PHRASE_WEIGHT * a + (1 - self.PHRASE_WEIGHT) * b, "blended"


# ------------------------------------------------------------------ driver

def generate(stage1, stage2, configuration="standard", vectors=None,
             cap_per_case=None):
    """-> {"candidates": [...], "rejected": n, "counts": {...}}.

    Every candidate is directional: `producer -> consumer`.  Candidates are
    never merged transitively; a chain has to be found by whatever consumes
    this list, not invented here.
    """
    table = AO.extract(stage1, stage2)
    P, C = producers(table), consumers(table)
    cands, rejected = [], {}
    for p in P:
        for c in C:
            why = reject_reason(p, c)
            if why:
                rejected[why.split(":")[0]] = rejected.get(why.split(":")[0], 0) + 1
                continue
            f = features(p, c, table)
            row = {
                "producer": p["occurrence_id"],
                "consumer": c["occurrence_id"],
                "direction": "%s -> %s" % (p["occurrence_id"], c["occurrence_id"]),
                "producer_unit": p["unit_id"], "consumer_unit": c["unit_id"],
                "producer_predicate": p.get("predicate"),
                "consumer_predicate": c.get("predicate"),
                "producer_label": AI.content_label(p),
                "consumer_label": AI.content_label(c),
                "producer_quote": p.get("source_quote"),
                "consumer_quote": c.get("source_quote"),
                "features": f,
                "scores": {"structural": structural_score(f),
                           "lexical": lexical_score(p, c)},
            }
            if vectors is not None and vectors.ok:
                s, how = vectors.score(p, c)
                row["scores"]["fasttext"] = s
                row["fasttext_basis"] = how
            else:
                row["scores"]["fasttext"] = None
            cands.append(row)
    if cap_per_case:
        cands = cands[:cap_per_case]
    return {"table": table, "candidates": cands,
            "producers": len(P), "consumers": len(C),
            "enumerated": len(P) * len(C),
            "survived": len(cands),
            "rejected_by_reason": rejected}


def ranked(cands, arm):
    """Candidates ordered by one arm.  Ties break deterministically."""
    def key(r):
        s = r["scores"].get(arm)
        return (-(s if s is not None else -1e9), r["direction"])
    return sorted(cands, key=key)
