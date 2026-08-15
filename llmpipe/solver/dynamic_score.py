"""Proof-level scoring for dynamic abstraction worlds.

The alternative — writing a low `@confidence` onto the bridge clause — was
measured in `memos/MEMO_2026_08_10_bridge_world.md` §5 and does three things at
once: it prunes proof search (a bridge at 0.1 produced no proof at all in one
case), it compounds on repeated application (0.1 used twice reported 0.0100),
and it collides with gk's own answer threshold and with the pipeline's 0.10
rendering floor.  None of those is the uncertainty anyone meant.

So a runtime bridge clause is full confidence, and the world's uncertainty is
applied afterwards, to the proof gk actually returned:

  * the bridge hypotheses the proof CITES are charged;
  * each is charged ONCE, however many clauses or steps cite it;
  * a hypothesis that was offered and not used costs nothing;
  * gk's own confidence is kept, untouched, beside the adjusted one.

Everything here is a pure function of its arguments.  Nothing reads global
state, calls a prover, or formats an answer for the normal pipeline —
`_format_bool_answer` is deliberately untouched, and dynamic answers get their
own structured result and their own rendering.
"""

TIER = "dynamic_bridge"
BASE_TIER = "base_theory"

WEIGHT_POLICY = ("provisional: the adjusted confidence is gk's confidence times "
                 "the product of the weights of the DISTINCT bridge hypotheses "
                 "the proof cites.  For a one-bridge world this is "
                 "gk_confidence * bridge_world_weight, which is the only case "
                 "the evidence covers; the product for several bridges treats "
                 "them as independent and is a placeholder, not a decision.")


def _steps(proof):
    """Normalise `proof` to a flat list of steps.

    Accepts one proof (a list of steps), several proofs (a list of lists of
    steps), or None.
    """
    if not proof:
        return []
    out = []
    for item in proof:
        if isinstance(item, list) and item and isinstance(item[0], list):
            out.extend(item)
        else:
            out.append(item)
    return out


def _names_in(step):
    """Clause names a proof step cites, as strings anywhere in its citation."""
    if not isinstance(step, list) or len(step) < 2:
        return []
    found = []

    def walk(x):
        if isinstance(x, list):
            for y in x:
                walk(y)
        elif isinstance(x, str):
            found.append(x)
    walk(step[1])
    return found


def cited_hypotheses(proof, provenance):
    """-> (ordered distinct hypothesis ids cited, {id: [clause names]}).

    `provenance` maps clause name -> hypothesis id.  A clause name that is not
    in it is not a bridge clause and is ignored; nothing is inferred from the
    shape of a name.
    """
    order, by_hyp = [], {}
    for step in _steps(proof):
        for name in _names_in(step):
            hid = provenance.get(name)
            if hid is None:
                continue
            if hid not in by_hyp:
                by_hyp[hid] = []
                order.append(hid)
            if name not in by_hyp[hid]:
                by_hyp[hid].append(name)
    return order, by_hyp


def score(answer, gk_confidence, proof, provenance, weights,
          bridge_world_weight=None):
    """The structured dynamic result.  Pure.

    `answer`      gk's answer value, or None when it returned none
    `gk_confidence` gk's own confidence, kept untouched
    `proof`       the returned proof, or None
    `provenance`  {clause name: hypothesis id}
    `weights`     {hypothesis id: weight}
    `bridge_world_weight`
                  the world's own weight, recorded for reference; the adjusted
                  confidence is computed from the CITED hypotheses, so a world
                  whose second bridge went unused is not charged for it

    No answer is ever manufactured: if gk returned none, this returns none, and
    a proof that cites no bridge is reported as resting on the base theory.
    """
    used, by_hyp = cited_hypotheses(proof, provenance)
    unknown = [h for h in used if h not in weights]
    charged = 1.0
    for hid in used:
        charged *= weights.get(hid, 1.0)
    has_answer = answer is not None
    gk_conf = gk_confidence if has_answer else None
    dyn = (None if not has_answer
           else (gk_conf if gk_conf is None else gk_conf * charged))
    return {
        "answer": answer,
        "gk_confidence": gk_conf,
        "dynamic_confidence": dyn,
        "bridge_hypotheses_used": list(used),
        "bridge_clauses_used": {h: list(by_hyp[h]) for h in used},
        "charged_weight": charged if has_answer else None,
        "world_weight": bridge_world_weight,
        "unweighted_hypotheses_cited": unknown,
        "provenance_tier": TIER if used else BASE_TIER,
        "weight_policy": WEIGHT_POLICY,
    }


def from_raw(raw, provenance, weights, bridge_world_weight=None,
             answer_index=0):
    """Thin adapter: pull answer, confidence and proof out of gk's JSON.

    The scoring itself stays in `score`, which never sees a prover.
    """
    import json
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    answers = (raw or {}).get("answers") or []
    if not answers or answer_index >= len(answers):
        return score(None, None, None, provenance, weights, bridge_world_weight)
    a = answers[answer_index]
    proof = []
    for key in ("positive proof", "negative proof", "proof"):
        if a.get(key):
            proof.append(a[key])
    out = score(a.get("answer"), a.get("confidence"), proof, provenance,
                weights, bridge_world_weight)
    out["blockers"] = a.get("blockers")
    return out


# ------------------------------------------------------------- rendering

def _fmt(x):
    """Four significant figures, so a small confidence stays visible.

    `%.3f` turned 0.0009 into 0.001 and 0.00009 into 0.000; a probe result's
    whole point is that its number is small, and rounding it away would be the
    same mistake as suppressing it.
    """
    return "%.4g" % x


def render(result, kind=None):
    """Text for a dynamic result.  The structured fields are authoritative.

    This is NOT `proof_answer_format._format_bool_answer` and does not go near
    it.  In particular a dynamic answer below 0.10 — or below 0.001 — is shown
    with its confidence instead of becoming `Unknown.`: in a dynamic world a
    small number is the point, not noise.  `Unknown.` is returned only when
    there is no answer at all.

    `kind="unverified_probe"` marks a result whose hypothesis has not been
    semantically reviewed.
    """
    if result["answer"] is None:
        return "Unknown."
    conf = result["dynamic_confidence"]
    val = result["answer"]
    if isinstance(val, bool):
        stem = "true" if val else "false"
    else:
        stem = str(val)
    if conf is None:
        head = "True." if val is True else ("False." if val is False
                                            else "%s." % stem)
        return head
    if conf >= 0.95:
        head = "True" if val is True else ("False" if val is False else stem)
    elif conf >= 0.70:
        head = "Probably %s" % stem
    elif conf >= 0.40:
        head = "Likely %s" % stem
    else:
        head = "Possibly %s" % stem
    used = result["bridge_hypotheses_used"]
    if not used:
        return "%s (confidence %s)." % (head, _fmt(conf))
    which = ", ".join(used)
    word = "abstraction" if len(used) == 1 else "abstractions"
    if kind == "unverified_probe":
        return "%s (confidence %s; unverified dynamic %s %s)." % (
            head, _fmt(conf), word, which)
    return "%s (confidence %s; depends on dynamic %s %s)." % (
        head, _fmt(conf), word, which)
