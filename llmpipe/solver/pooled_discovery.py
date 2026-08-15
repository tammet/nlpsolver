"""Proof first, semantics after: pooled discovery mode.

The isolated mode asks admission which single rule deserves a world, and gives
gk one bridge at a time.  Two rounds of evidence say that filters too early:
eb-0006's reviewed formula was cut by a cap, and eb2-0020 needs TWO
abstractions at once, which no single-bridge world can ever supply.

So this mode inverts the order.  Before gk it refuses only what is mechanically
broken (`mechanical_gate`).  It builds a bounded discovery set, hands gk
several bridges at once, and only then asks what the bridges a proof actually
CITED are worth.  A doubtful bridge that carries a proof is reported as a
doubtful bridge that carried a proof — labelled, not deleted, and never
presented as a calibrated probability.

Nothing here weights a clause: every bridge compiles at full confidence with
its `$block`, the only gk option that changes is the proof-return threshold,
and any numeric adjustment happens after gk, charged once per distinct cited
hypothesis.
"""

import collections
import copy
import hashlib
import json

import bridge_world as BW
import construction_operators as CO
import construction_provenance as CP
import converse_pairs as CV
import dynamic_score as DS
import mechanical_gate as MG

VERSION = "pooled_discovery/1.0"

DISCOVERY_CAP = 30
MAX_CONFLICT_WORLDS = 6
POOL_A, POOL_B, POOL_C = "A_supported", "B_broad", "C_disfavoured"

TRUST = {"supported": "well supported by the passage or ordinary knowledge",
         "plausible": "plausible background abstraction",
         "speculative": "speculative",
         "counterexampled": "counterexampled / very low trust",
         "unassessed": "not assessed"}


# ------------------------------------------------------------------ helpers

def _split(lit):
    """-> (sign, predicate, label, participants), for either negation form.

    The construction library writes a negated literal as `["not", lit]`; a
    compiled clause writes it as a `-` on the predicate.  Both arrive here, and
    reading only the first form is how a premise that negates its own
    conclusion slipped past this check.
    """
    neg = CO.is_negated(lit)
    atom = CO.strip_neg(lit)
    if isinstance(atom, list) and atom and isinstance(atom[0], str) \
            and atom[0].startswith("-"):
        neg = True
        atom = [atom[0][1:]] + list(atom[1:])
    pred, label, parts = CO.split_atom(atom)
    return ("-" if neg else "+", pred, label, [t for _i, t in parts])


def _is_var(t):
    return isinstance(t, str) and t in CO._vars_in([t])


def unifiable(a, b):
    """Could these two literals meet?  Variables match anything of any name."""
    sa, pa, la, aa = _split(a)
    sb, pb, lb, ab = _split(b)
    if sa != sb or pa != pb or len(aa) != len(ab):
        return False
    if la is not None and lb is not None and CO.normalize(str(la)) != \
            CO.normalize(str(lb)):
        return False
    for x, y in zip(aa, ab):
        if _is_var(x) or _is_var(y):
            continue
        if str(x) != str(y):
            return False
    return True


def signature(row):
    """What makes a candidate structurally different from another."""
    s, p, l, args = _split(row["head"])
    paths = row.get("derivation_paths") or []
    return (p, CO.normalize(str(l)) if l is not None else None, s,
            tuple(sorted(set(x["operator"] for x in paths))),
            tuple(sorted(set(str(x.get("direction")) for x in paths))),
            tuple("var" if _is_var(a) else "const" for a in args))


def chain_enabling(row, others, question_lits, source_premises):
    """Can this candidate's head meet something else that needs it?"""
    why = []
    for other in others:
        if other is row:
            continue
        for lit in other["body"]:
            if unifiable(row["head"], lit):
                why.append("its conclusion can feed the premise `%s` of "
                           "another candidate" % json.dumps(lit)[:60])
                break
        if why:
            break
    for lit in question_lits:
        if unifiable(row["head"], lit):
            why.append("its conclusion meets a literal the question needs")
            break
    for lit in source_premises:
        if unifiable(row["head"], lit):
            why.append("its conclusion meets a premise of a source rule on the "
                       "way to the question")
            break
    return why


def source_premises(view):
    """Negative literals of source clauses: what a rule of the passage needs."""
    out = []
    for c in view.get("final_clauses") or []:
        if not isinstance(c, dict) or "@question" in c:
            continue
        if c.get("@sourcetype") == "populate":
            continue
        body = c.get("@logic")
        if not isinstance(body, list) or not body or not isinstance(body[0],
                                                                    list):
            continue
        for lit in body:
            if isinstance(lit, list) and lit and CO.is_negated(lit):
                out.append(CO.strip_neg(lit))
    return out


def question_needs(view):
    """Literals the question's clauses would have to see satisfied."""
    out = []
    for lit in MG.question_literals(view):
        out.append(CO.strip_neg(lit) if CO.is_negated(lit) else lit)
    return out


# --------------------------------------------------- the discovery set (WP3)

def build_discovery_set(rows, selected, view, case, packages, configuration,
                        cap=DISCOVERY_CAP, gate=True):
    """-> the bounded set, with why each entered and what the cap dropped.

    Order of entry: what the selector chose, then candidates that can chain,
    then diverse supplements.  Every omission is recorded with the cap that is
    responsible for it.
    """
    qlits = question_needs(view)
    prem = source_premises(view)
    cheap_refused, pool = [], []
    for r in rows:
        why = []
        if MG.unbound_head_variables(r):
            why.append("unbound")
        if MG.contradicts_own_conclusion(r):
            why.append("self_contradiction")
        if MG.head_word_lost_its_source(r):
            why.append("mapping")
        if MG.impossible_identity(r):
            why.append("impossible_identity")
        if MG.question_only_restatement(r, case, qlits):
            why.append("question_only")
        if why:
            cheap_refused.append({"printed": r["printed_formula"],
                                  "refusals": why})
            continue
        pool.append(r)

    chosen, reasons, seen_sig = [], {}, set()
    by_print = dict((r["printed_formula"], r) for r in pool)

    def take(row, why):
        if row["printed_formula"] in reasons or len(chosen) >= cap:
            return False
        chosen.append(row)
        reasons[row["printed_formula"]] = why
        seen_sig.add(signature(row))
        return True

    for printed in selected:
        row = by_print.get(printed)
        if row is not None:
            take(row, "the formula selector chose it")

    # Chain-enabling, most useful kind first: a conclusion the QUESTION needs,
    # then one a source rule of the passage needs, then one another candidate
    # needs.  Without this ordering the cap fills with guarded variants of the
    # formulas already selected and a different representation never gets in.
    for kind, test in (
            ("its conclusion meets a literal the question needs",
             lambda r: any(unifiable(r["head"], l) for l in qlits)),
            ("its conclusion meets a premise of a source rule on the way to "
             "the question",
             lambda r: any(unifiable(r["head"], l) for l in prem)),
            ("its conclusion can feed a premise of another candidate",
             lambda r: any(any(unifiable(r["head"], l) for l in o["body"])
                           for o in chosen))):
        for prefer_new_shape in (True, False):
            for row in pool:
                if len(chosen) >= cap:
                    break
                if row["printed_formula"] in reasons:
                    continue
                if prefer_new_shape and signature(row) in seen_sig:
                    continue
                if test(row):
                    take(row, "chain-enabling: %s" % kind)

    for row in pool:
        if len(chosen) >= cap:
            break
        if row["printed_formula"] in reasons:
            continue
        if signature(row) in seen_sig:
            continue
        take(row, "diverse supplement: an unseen combination of head "
                  "predicate, word, sign, operator, direction and argument "
                  "shape")

    gated, refused = [], []
    for row in chosen:
        pkg = packages.get(row["printed_formula"])
        if not gate:
            gated.append(row)
            continue
        got = MG.check(row, pkg, view, case, configuration, qlits=qlits)
        row["gate"] = got
        (gated if got["passed"] else refused).append(row)

    omitted = [{"printed": r["printed_formula"],
                "cap_responsible": "the %d-formula discovery cap" % cap}
               for r in pool if r["printed_formula"] not in reasons]
    return {
        "complete_pool": len(rows),
        "after_cheap_mechanical_refusals": len(pool),
        "cheap_refusals": cheap_refused[:40],
        "cheap_refusal_count": len(cheap_refused),
        "discovery_set": gated,
        "entry_reasons": reasons,
        "refused_by_the_gate": [{"printed": r["printed_formula"],
                                 "refusals": r["gate"]["refusals"]}
                                for r in refused],
        "omitted": omitted[:60],
        "omitted_count": len(omitted),
        "cap": cap,
    }


# ------------------------------------------------------------- pools (WP4)

def counterexampled_index(prior_records, pair_judgements):
    """printed formula -> why an earlier judgement disfavours it."""
    out = {}
    for rec in prior_records or []:
        kind = rec.get("world_kind")
        direction = ((rec.get("axes") or {}).get("direction") or {}).get(
            "value")
        if kind in ("rejected", "archived") or direction == "COUNTEREXAMPLED":
            out[rec["printed_formula"]] = {
                "source": "an earlier six-axis record",
                "world_kind": kind, "direction": direction}
    for j in pair_judgements or []:
        rel = j.get("relation")
        for side, other in (("a", "b"), ("b", "a")):
            ce = (j.get("counterexample_%s" % side) or "").strip().lower()
            refuted = rel == "NEITHER" or (rel == "%s_ONLY" % other.upper())
            if refuted or (ce and ce not in ("none", "-", "n/a")):
                out.setdefault(j[side], {
                    "source": "a paired-direction judgement",
                    "relation": rel,
                    "counterexample": j.get("counterexample_%s" % side)})
    return out


def make_pools(discovery, disfavoured):
    """A: not disfavoured.  B: everything.  C: the disfavoured ones."""
    a = [r for r in discovery if r["printed_formula"] not in disfavoured]
    c = [r for r in discovery if r["printed_formula"] in disfavoured]
    return [
        {"pool": POOL_A, "why": "structurally valid and not explicitly "
                                "counterexampled by any judgement available "
                                "before the run", "rows": a},
        {"pool": POOL_B, "why": "every candidate in the bounded discovery set, "
                                "including the uncertain and the speculative",
         "rows": list(discovery)},
        {"pool": POOL_C, "why": "explicitly counterexampled or rejected "
                                "candidates, kept apart from the supported "
                                "pool and tried late", "rows": c},
    ]


def hypotheses_for(rows, packages, case_id, weight):
    out = []
    for i, r in enumerate(rows, start=1):
        pkg = packages.get(r["printed_formula"])
        if pkg is None:
            continue
        out.append({"hypothesis_id": "%s::D%d" % (case_id, i),
                    "weight": weight, "label": "D%d" % i, "package": pkg,
                    "case_id": case_id, "printed_formula": r["printed_formula"],
                    "derivation_paths": r.get("derivation_paths") or [],
                    "gate": r.get("gate")})
    return out


def build_world(world_id, hyps, view, configuration):
    world = BW.build_dynamic_world(
        world_id, [{"hypothesis_id": h["hypothesis_id"], "weight": h["weight"],
                    "label": h["label"], "package": h["package"],
                    "case_id": h["case_id"]} for h in hyps],
        view["stage1"], view["stage2"], configuration,
        base_clauses=view["final_clauses"])
    world["hypotheses_in_this_world"] = [h["hypothesis_id"] for h in hyps]
    world["printed_by_id"] = dict((h["hypothesis_id"], h["printed_formula"])
                                  for h in hyps)
    return world


def run_world(world, view, gk, tag):
    stored = {"stage1": view["stage1"], "stage2": view["stage2"],
              "final_clauses": view["final_clauses"],
              "input_text": view["input_text"]}
    clauses = list(view["final_clauses"]) + [
        dict(c) for c in world["compiled_bridge_clauses"]]
    got = gk(clauses, stored, tag, dynamic=True)
    scored = DS.from_raw(got.get("raw") or "{}", world["clause_provenance"],
                         world["weights"],
                         bridge_world_weight=world["bridge_world_weight"])
    return {
        "world_id": world["world_id"], "tag": tag,
        "hypotheses_offered": world["hypotheses_in_this_world"],
        "clause_count": len(world["compiled_bridge_clauses"]),
        "clause_confidence_annotations": [
            c.get("@confidence") for c in world["compiled_bridge_clauses"]],
        "all_clauses_have_block": BW.has_block(world["compiled_bridge_clauses"]),
        "answer": scored["answer"],
        "gk_native_confidence": scored["gk_confidence"],
        "cited_hypothesis_ids": scored["bridge_hypotheses_used"],
        "cited_formulas": [world["printed_by_id"].get(h)
                           for h in scored["bridge_hypotheses_used"]],
        "scored": scored,
        "rendered": DS.render(scored),
        "conservative_formatter_answer": got.get("answer"),
        "gk_thresholds": got.get("thresholds"),
        "error": got.get("error"),
        "raw_prefix": (got.get("raw") or "")[:200],
    }


# ------------------------------------------------- minimisation (WP5)

def minimise(result, hyps, view, configuration, gk, budget, case_id):
    """Replay the cited set, then delete one at a time.

    A proof nobody's bridge is cited in is not a dynamic-abstraction proof, and
    this returns that verdict rather than a minimal set.
    """
    cited = list(result["cited_hypothesis_ids"])
    if result["answer"] is None or not cited:
        return {"minimised": False,
                "why": "no answer" if result["answer"] is None else
                       "an answer with no cited dynamic hypothesis is not a "
                       "dynamic-abstraction proof",
                "cited": cited}
    by_id = dict((h["hypothesis_id"], h) for h in hyps)
    subset = [by_id[h] for h in cited if h in by_id]
    replay = None
    if budget():
        world = build_world("replay_%s" % case_id, subset, view, configuration)
        replay = run_world(world, view, gk, "%s/replay" % case_id)
    if replay is None or replay["answer"] != result["answer"]:
        return {"minimised": False, "cited": cited, "replay": replay,
                "why": "the cited set did not reproduce the answer"}
    keep = list(subset)
    deletions = []
    for h in list(subset):
        if len(keep) <= 1 or not budget():
            break
        trial = [x for x in keep if x["hypothesis_id"] != h["hypothesis_id"]]
        world = build_world("min_%s_without_%s" % (case_id, h["label"]),
                            trial, view, configuration)
        got = run_world(world, view, gk,
                        "%s/without %s" % (case_id, h["label"]))
        destroyed = got["answer"] != result["answer"]
        deletions.append({"removed": h["hypothesis_id"],
                          "formula": h["printed_formula"],
                          "answer_without_it": got["answer"],
                          "removing_it_destroys_the_proof": destroyed,
                          "cited_without_it": got["cited_hypothesis_ids"]})
        if not destroyed:
            keep = trial
    return {"minimised": True, "cited": cited,
            "replay": replay,
            "replay_reproduced": True,
            "minimal_set": [h["hypothesis_id"] for h in keep],
            "minimal_formulas": [h["printed_formula"] for h in keep],
            "deletions": deletions,
            "unused_in_the_pool": [h["hypothesis_id"] for h in hyps
                                   if h["hypothesis_id"] not in cited]}


# ------------------------------------------------- conflict splitting (WP4)

def conflict_components(rows):
    """Groups of candidates that directly contradict each other.

    Only DIRECT conflicts: one candidate's conclusion is the negation of
    another's, or two candidates are converses of each other.  Nothing else is
    partitioned, and no subset enumeration happens.
    """
    groups = []
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            sa, pa, la, aa = _split(a["head"])
            sb, pb, lb, ab = _split(b["head"])
            opposite = (pa == pb and str(la) == str(lb) and sa != sb
                        and len(aa) == len(ab))
            conv = CV.converse(a, b) is not None
            if opposite or conv:
                groups.append({"a": a["printed_formula"],
                               "b": b["printed_formula"],
                               "kind": "opposite conclusions" if opposite
                               else "converse directions"})
    return groups


# ------------------------------------------------- trust labels (WP6)

def trust_label(record, disfavoured_entry, warnings):
    if disfavoured_entry:
        return "counterexampled"
    if record is None:
        return "unassessed"
    axes = record.get("axes") or {}
    sem = (axes.get("semantic") or {}).get("value")
    direction = (axes.get("direction") or {}).get("value")
    if direction == "COUNTEREXAMPLED":
        return "counterexampled"
    if sem == "SUPPORTED":
        return "supported"
    if sem == "PLAUSIBLE":
        return "plausible"
    if sem in ("SPECULATIVE",):
        return "speculative"
    if sem in ("UNSUPPORTED", "INVALID"):
        return "counterexampled"
    return "unassessed"


def dynamic_result(result, trusts, weight=None):
    """The reported result: gk's own number, symbolic trust, and a caveat."""
    cited = result["cited_hypothesis_ids"]
    provisional = None
    if weight is not None and result["gk_native_confidence"] is not None:
        provisional = result["gk_native_confidence"] * (weight ** len(
            set(cited)))
    lines = ["proof found" if result["answer"] is not None else "no proof",
             "native gk confidence: %s" % result["gk_native_confidence"]]
    if cited:
        lines.append("depends on:")
        for h in cited:
            lines.append("  %s — %s" % (h, TRUST.get(trusts.get(h,
                                                                "unassessed"),
                                                     "not assessed")))
    return {
        "answer": result["answer"],
        "native_gk_confidence": result["gk_native_confidence"],
        "distinct_cited_bridges": len(set(cited)),
        "trust_per_bridge": dict((h, trusts.get(h, "unassessed"))
                                 for h in cited),
        "provisional_numeric": provisional,
        "provisional_numeric_policy":
            "gk's own confidence times one fixed provisional weight per "
            "DISTINCT cited bridge, applied after gk and never to a clause",
        "this_number_is_not_calibrated":
            "no measurement supports it; it is kept only so earlier records "
            "stay comparable",
        "rendered": "\n".join(lines),
    }


# ------------------------------------------------------------------ driver

def run_case(view, respond, gk, bounds=None, weight=None, cap=None,
             prior_records=None, pair_judgements=None, configuration=None):
    """One case, proof first.  The shared stages are the isolated mode's own.

    Front door, frontier, group selection, construction and formula selection
    are `dynamic_runtime`'s, unchanged and called here; everything after them
    is this module's.
    """
    import dynamic_runtime as RT
    bounds = bounds or {}
    weight = RT.WORLD_WEIGHT if weight is None else weight
    configuration = configuration or view["configuration"]
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": view["case_id"], "mode": "pooled_discovery",
              "view_sha256": RT.view_hash(view), "conservative": front,
              "trace": trace, "dynamic_work_done": False}
    if front["resolved"]:
        trace.append({"stage": "stopped", "why": "the conservative front door "
                      "answered %r" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "frontier"})
    fr = RT.frontier(view)
    result["frontier"] = {k: fr[k] for k in ("version", "counts", "selected",
                                             "interfaces")}
    trace.append({"stage": "group_selection"})
    pick = RT.select_groups(view, fr, RT.source_atoms(view), respond,
                            allow_retry=bounds.get("selector_retry", True))
    result["group_selection"] = {k: pick[k] for k in
                                 ("groups_total", "groups_shown", "selected",
                                  "used_the_fallback", "omitted", "retried",
                                  "display_policy", "raw")}
    case = RT.case_of(view, fr, pick["selected"])

    trace.append({"stage": "construction"})
    con = RT.construction(case, view, respond,
                          allow_retry=bounds.get("construction_retry", True))
    result["construction"] = {"retried": con["retried"],
                              "parsed": con["parsed"], "built": con["built"],
                              "raw": con["raw"],
                              "prompt_sha256": con["prompt_sha256"]}

    trace.append({"stage": "pool"})
    proposals = con["parsed"].get("proposals") or []
    acc, packages = CP.collect(case, view["case_id"], proposals)
    rows = acc.rows()
    model_rows = [r for r in rows if CP.model_reached(r)]
    model_rows.sort(key=lambda r: (min(
        i for i, p in enumerate(r["derivation_paths"])
        if p["source_run"] == CP.MODEL_RUN), r["printed_formula"]))
    selected_printed = []
    if model_rows and bounds.get("formula_selector", True):
        trace.append({"stage": "formula_selection"})
        chosen = RT.select_formulas(view, case, model_rows, respond,
                                    allow_retry=bounds.get("selector_retry",
                                                           True))
        selected_printed = [r["printed_formula"] for r in chosen["chosen"]]
        result["formula_selection"] = {
            "formulas_total": chosen["formulas_total"],
            "formulas_shown": chosen["formulas_shown"],
            "selected_ids": chosen["selected_ids"],
            "used_the_fallback": chosen["used_the_fallback"],
            "not_selected": len(chosen["not_selected"]),
            "raw": chosen["raw"]}

    trace.append({"stage": "discovery_set"})
    built = build_discovery_set(rows, selected_printed, view, case, packages,
                               configuration, cap=cap or DISCOVERY_CAP)
    discovery = built["discovery_set"]
    result["pool"] = {k: built[k] for k in
                      ("complete_pool", "after_cheap_mechanical_refusals",
                       "cheap_refusal_count", "cheap_refusals", "cap",
                       "omitted_count", "omitted", "refused_by_the_gate")}
    result["pool"]["model_reached"] = len(model_rows)
    result["discovery_set"] = [
        {"printed": r["printed_formula"],
         "why_it_entered": built["entry_reasons"].get(r["printed_formula"]),
         "model_reached": CP.model_reached(r),
         "paths": len(r.get("derivation_paths") or []),
         "operators": sorted(set(p["operator"] for p in
                                 r.get("derivation_paths") or [])),
         "warnings": (r.get("gate") or {}).get("warnings")}
        for r in discovery]
    if not discovery:
        trace.append({"stage": "stopped", "why": "no candidate survived the "
                      "mechanical gate"})
        result["stopped_at"] = "no_candidate_survived"
        return result

    disfavoured = counterexampled_index(prior_records, pair_judgements)
    result["disfavoured_before_the_run"] = dict(
        (k, v) for k, v in disfavoured.items()
        if k in set(r["printed_formula"] for r in discovery))

    trace.append({"stage": "pools"})
    hyps_all = hypotheses_for(discovery, packages, view["case_id"], weight)
    by_print = dict((h["printed_formula"], h) for h in hyps_all)
    runs, worlds_used = [], 0
    for spec in make_pools(discovery, result["disfavoured_before_the_run"]):
        rows_here = spec["rows"]
        hyps = [by_print[r["printed_formula"]] for r in rows_here
                if r["printed_formula"] in by_print]
        if not hyps:
            runs.append({"pool": spec["pool"], "why": spec["why"],
                         "skipped": "no candidate in this pool"})
            continue
        if not bounds.get("gk_budget", lambda: True)() or \
                worlds_used >= MAX_CONFLICT_WORLDS:
            runs.append({"pool": spec["pool"], "why": spec["why"],
                         "skipped": "gk budget or pool-world cap"})
            continue
        world = build_world("pool_%s_%s" % (view["case_id"], spec["pool"]),
                            hyps, view, configuration)
        got = run_world(world, view, gk,
                        "%s/%s" % (view["case_id"], spec["pool"]))
        worlds_used += 1
        got.update({"pool": spec["pool"], "why": spec["why"],
                    "candidates": len(hyps)})
        conflicts = conflict_components(rows_here)
        got["direct_conflicts_inside_this_pool"] = conflicts[:8]
        if got["answer"] is None and conflicts and \
                worlds_used < MAX_CONFLICT_WORLDS and \
                bounds.get("gk_budget", lambda: True)():
            # partition ONLY the explicit conflict: drop one side of each
            # conflicting pair, never enumerate subsets
            drop = set(c["b"] for c in conflicts)
            split = [h for h in hyps if h["printed_formula"] not in drop]
            if split and len(split) < len(hyps):
                w2 = build_world("pool_%s_%s_split" % (view["case_id"],
                                                       spec["pool"]),
                                 split, view, configuration)
                got2 = run_world(w2, view, gk, "%s/%s split"
                                 % (view["case_id"], spec["pool"]))
                worlds_used += 1
                got2.update({"pool": spec["pool"] + "_conflict_split",
                             "why": "the pool returned nothing and holds "
                                    "direct conflicts; one side of each "
                                    "conflicting pair was dropped",
                             "dropped": sorted(drop)[:6],
                             "candidates": len(split)})
                runs.append(got2)
        runs.append(got)
    result["pool_worlds"] = runs
    result["pool_worlds_used"] = worlds_used

    trace.append({"stage": "minimise"})
    minimal = []
    seen_sets = set()
    for got in runs:
        if got.get("skipped") or got.get("answer") is None:
            continue
        key = tuple(sorted(got["cited_hypothesis_ids"]))
        if key in seen_sets:
            continue
        seen_sets.add(key)
        m = minimise(got, hyps_all, view, configuration, gk,
                     bounds.get("gk_budget", lambda: True), view["case_id"])
        m["pool"] = got["pool"]
        m["answer"] = got["answer"]
        m["native_gk_confidence"] = got["gk_native_confidence"]
        minimal.append(m)
    result["minimisation"] = minimal
    result["distinct_cited_sets"] = [list(k) for k in seen_sets]

    trace.append({"stage": "assess_after_the_proof"})
    result["assessment"] = assess_after_proof(
        view, case, fr, discovery, hyps_all, minimal, runs, respond,
        result["disfavoured_before_the_run"], bounds, weight)
    result["stopped_at"] = None
    return result


# ------------------------------------------------- assessment after gk (WP6)

def assess_after_proof(view, case, fr, discovery, hyps, minimal, runs, respond,
                       disfavoured, bounds, weight):
    """Six axes and a paired direction, asked about the bridges a proof cited.

    Nothing here can withdraw a proof.  A bridge judged badly is labelled
    badly and the proof is still reported, because what gk did is a fact and
    what a judge thinks of the rule is a separate one.
    """
    import dynamic_runtime as RT
    cited_ids = []
    for m in minimal:
        for h in (m.get("minimal_set") or m.get("cited") or []):
            if h not in cited_ids:
                cited_ids.append(h)
    by_id = dict((h["hypothesis_id"], h) for h in hyps)
    by_print = dict((r["printed_formula"], r) for r in discovery)
    rows = []
    for hid in cited_ids:
        h = by_id.get(hid)
        if h is None:
            continue
        row = by_print.get(h["printed_formula"])
        if row is not None:
            rows.append(dict(row, hypothesis_id=hid))
    if not rows:
        return {"cited_bridges": 0,
                "why": "no proof cited a dynamic bridge, so there is nothing "
                       "to assess after the fact",
                "results": []}
    for i, r in enumerate(rows):
        r["variant_id"] = chr(ord("A") + i)
    challenge = RT.admission_challenge(case, view, fr, rows)
    judged = RT.admission(challenge, respond,
                          allow_retry=bounds.get("selector_retry", True))
    records = RT.records(challenge, judged, [])
    by_variant = dict((rec["variant_id"], rec) for rec in records)

    pairs = CV.find_pairs(rows, [r["variant_id"] for r in rows])
    paired = None
    if pairs and respond is not None:
        paired = judge_pair(view, pairs[0], respond)

    trusts, per_bridge = {}, []
    for r in rows:
        rec = by_variant.get(r["variant_id"])
        dis = disfavoured.get(r["printed_formula"])
        label = trust_label(rec, dis, (r.get("gate") or {}).get("warnings"))
        if paired and paired.get("relation"):
            side = ("a" if paired["pair"]["a_id"] == r["variant_id"] else
                    "b" if paired["pair"]["b_id"] == r["variant_id"] else None)
            if side:
                ce = (paired.get("counterexample_%s" % side) or "").strip()
                if ce and ce.lower() not in ("none", "-", "n/a"):
                    label = "counterexampled"
        trusts[r["hypothesis_id"]] = label
        axes = (rec or {}).get("axes") or {}
        per_bridge.append({
            "hypothesis_id": r["hypothesis_id"],
            "variant_id": r["variant_id"],
            "formula": r["printed_formula"],
            "trust": label, "trust_means": TRUST[label],
            "semantic": (axes.get("semantic") or {}).get("value"),
            "evidence_basis": (axes.get("semantic") or {}).get(
                "evidence_basis"),
            "passage_support": (axes.get("passage") or {}).get("value"),
            "direction_support": (axes.get("direction") or {}).get("value"),
            "restriction": (axes.get("restriction") or {}).get("judged"),
            "attachment": (axes.get("attachment") or {}).get("result"),
            "counterexample": (paired or {}).get("counterexample_a")
            if paired and paired["pair"]["a_id"] == r["variant_id"]
            else (paired or {}).get("counterexample_b")
            if paired and paired["pair"]["b_id"] == r["variant_id"] else None,
            "world_kind_if_admission_had_gated_it": (rec or {}).get(
                "world_kind"),
            "provenance": {
                "paths": len(r.get("derivation_paths") or []),
                "operators": sorted(set(p["operator"] for p in
                                        r.get("derivation_paths") or [])),
                "model_named": any(p.get("model_named_components")
                                   for p in r.get("derivation_paths") or []),
                "system_supplemented": any(
                    p.get("required_slot_completions")
                    or p.get("system_guard_supplements")
                    or p.get("system_direction_variant")
                    or p.get("system_scope_variant")
                    or p.get("system_target_form_variant")
                    for p in r.get("derivation_paths") or [])},
            "entered_the_discovery_set_because": None,
        })
    reported = []
    for m in minimal:
        got = next((g for g in runs if g.get("pool") == m.get("pool")), None)
        if got is None:
            continue
        reported.append(dict(dynamic_result(got, trusts, weight),
                             pool=m["pool"],
                             minimal_set=m.get("minimal_set"),
                             replay_reproduced=m.get("replay_reproduced")))
    return {"cited_bridges": len(rows),
            "admission_retried": judged.get("retried"),
            "admission_raw": judged.get("raw"),
            "paired_direction": paired,
            "per_bridge": per_bridge,
            "dynamic_results": reported,
            "note": "assessment cannot withdraw a proof; a doubtful bridge is "
                    "labelled and its proof still reported"}


PAIRED_PROMPT = "paired_direction_v1"


def judge_pair(view, pair, respond):
    """One paired-direction call about two cited bridges."""
    import dynamic_runtime as RT
    import re as _re
    body = ["THE PASSAGE", "", (view.get("input_text") or "").strip(), "",
            "THE TWO RULES", ""]
    for side, label in (("a", "A"), ("b", "B")):
        body.append("  %s  %s" % (label, pair[side]))
        body.append("     guards: %s" % (", ".join(pair["guards_on_%s" % side])
                                         or "none"))
        terms = pair["grounded_terms_%s" % side]
        body.append("     %s" % ("mentions a particular thing: %s"
                                 % ", ".join(str(t) for t in terms) if terms
                                 else "quantifies over everything"))
        body.append("")
    prompt = RT.prompt_text(PAIRED_PROMPT) + "\n\n" + "\n".join(body)
    text, _note = respond("paired_direction", view["case_id"], prompt)
    got = {"pair": pair, "raw": text}
    for line in (text or "").splitlines():
        m = _re.match(r"^\s*([A-Z_]+)\s*:\s*(.*)$", line.strip().strip("*_# "))
        if not m:
            continue
        key, value = m.group(1).upper(), m.group(2).strip()
        if key == "RELATION":
            got["relation"] = value.strip(".").upper()
        elif key == "COUNTEREXAMPLE_A":
            got["counterexample_a"] = value
        elif key == "COUNTEREXAMPLE_B":
            got["counterexample_b"] = value
        elif key == "SCOPE":
            got["scope"] = value.strip(".").lower()
    return got


# =====================================================================
# v2: stratified coverage, chain-directed pools, alternative proofs
# =====================================================================

DISCOVERY_CAP_V2 = 60
PER_FAMILY_SOFT_CAP = 8
MAX_CHAIN_LENGTH = 3
MAX_EXCLUSION_WORLDS = 6


def head_signature(row):
    """sign, predicate, content label, arity, argument correspondence.

    The correspondence records WHERE each conclusion argument comes from in the
    premises — which literal and which position — so `S(X,Y)` and `S(Y,X)` over
    the same body are two signatures, not one.  Reading only var/const made the
    reversed mapping a duplicate of the same-order one and dropped exactly the
    rule an inverse-relation case needs.
    """
    s, p, l, args = _split(row["head"])
    corr = []
    for a in args:
        if not _is_var(a):
            corr.append("const:%s" % a)
            continue
        where = None
        for bi, lit in enumerate(row["body"]):
            for ai, t in enumerate(_split(lit)[3]):
                if str(t) == str(a):
                    where = "b%d.%d" % (bi, ai)
                    break
            if where:
                break
        corr.append(where or "free")
    return (s, p, CO.normalize(str(l)) if l is not None else None, len(args),
            tuple(corr))


def body_signature(lit):
    s, p, l, args = _split(lit)
    return (s, p, CO.normalize(str(l)) if l is not None else None, len(args))


def operator_family(row):
    ops = sorted(set(p["operator"] for p in row.get("derivation_paths") or []))
    return ops[0] if ops else "unknown"


def base_of(row, rows_with_same_head):
    """The least supplemented formula this one is a guarded variant of.

    B is the base of R when they conclude the same thing and B's premises are a
    subset of R's.  That is the general form of "one claim wearing many
    guards", and it needs no per-operator knowledge of which slot a literal
    came from.
    """
    mine = set(json.dumps(l, sort_keys=True) for l in row["body"])
    best = None
    for other in rows_with_same_head:
        theirs = set(json.dumps(l, sort_keys=True) for l in other["body"])
        if theirs <= mine and (best is None or len(theirs) < len(best[1])):
            best = (other, theirs)
    return best[0] if best else row


def families(rows):
    """-> {family key: [rows]}, base first inside each family."""
    by_head = collections.defaultdict(list)
    for r in rows:
        by_head[json.dumps(r["head"], sort_keys=True)].append(r)
    out = collections.defaultdict(list)
    for head, group in by_head.items():
        group = sorted(group, key=lambda r: (len(r["body"]),
                                             r["printed_formula"]))
        for r in group:
            base = base_of(r, group)
            out[(head, base["printed_formula"])].append(r)
    for key in out:
        out[key].sort(key=lambda r: (len(r["body"]), r["printed_formula"]))
    return out


def stratified_discovery_set(rows, selected, view, case, packages,
                             configuration, cap=DISCOVERY_CAP_V2,
                             per_family=PER_FAMILY_SOFT_CAP, gate=True):
    """Fill the slots in rounds, so no one family can crowd out the rest.

    AL-79 filled a first-come cap and spent every slot on guard variants of one
    claim: two hundred candidates of the family the case actually needed never
    got in.  The rounds below give the selector's picks first, then one slot to
    every operator family, then one to every distinct head signature, then
    chain participants, then the frozen order — with a soft per-family cap that
    holds until each represented family has a slot.
    """
    qlits = question_needs(view)
    prem = source_premises(view)
    cheap_refused, pool = [], []
    for r in rows:
        why = []
        if MG.unbound_head_variables(r):
            why.append("unbound")
        if MG.contradicts_own_conclusion(r):
            why.append("self_contradiction")
        if MG.head_word_lost_its_source(r):
            why.append("mapping")
        if MG.impossible_identity(r):
            why.append("impossible_identity")
        if MG.question_only_restatement(r, case, qlits):
            why.append("question_only")
        if why:
            cheap_refused.append({"printed": r["printed_formula"],
                                  "refusals": why})
            continue
        pool.append(r)

    fam = families(pool)
    fam_of = {}
    for key, members in fam.items():
        for r in members:
            fam_of[r["printed_formula"]] = key
    chosen, reasons, rounds = [], {}, {}
    per_family_count = collections.Counter()
    seen_head, seen_operator = set(), set()

    def take(row, why, round_name, respect_soft_cap=True):
        if row["printed_formula"] in reasons or len(chosen) >= cap:
            return False
        key = fam_of.get(row["printed_formula"])
        if respect_soft_cap and per_family_count[key] >= per_family:
            return False
        chosen.append(row)
        reasons[row["printed_formula"]] = why
        rounds[row["printed_formula"]] = round_name
        per_family_count[key] += 1
        seen_head.add(head_signature(row))
        seen_operator.add(operator_family(row))
        return True

    by_print = dict((r["printed_formula"], r) for r in pool)
    for printed in selected:                                   # round 1
        row = by_print.get(printed)
        if row is not None:
            take(row, "the formula selector chose it", "1_selected",
                 respect_soft_cap=False)

    by_operator = collections.defaultdict(list)
    for r in pool:
        by_operator[operator_family(r)].append(r)
    for op in sorted(by_operator):                             # round 2
        if op in seen_operator:
            continue
        for r in by_operator[op]:
            if take(r, "one representative of operator family `%s`" % op,
                    "2_operator_family", respect_soft_cap=False):
                break

    for r in pool:                                             # round 3
        if len(chosen) >= cap:
            break
        if head_signature(r) in seen_head:
            continue
        take(r, "one representative of an unseen head signature",
             "3_head_signature", respect_soft_cap=False)

    for kind, test in (                                        # round 4
            ("its conclusion meets a literal the question needs",
             lambda r: any(unifiable(r["head"], l) for l in qlits)),
            ("its conclusion meets a premise of a source rule",
             lambda r: any(unifiable(r["head"], l) for l in prem)),
            ("its conclusion can feed a premise of a chosen candidate",
             lambda r: any(any(unifiable(r["head"], l) for l in o["body"])
                           for o in chosen))):
        for r in pool:
            if len(chosen) >= cap:
                break
            take(r, "structural chain: %s" % kind, "4_chain")

    for r in pool:                                             # round 5
        if len(chosen) >= cap:
            break
        take(r, "frozen priority order", "5_remaining")

    gated, refused = [], []
    for row in chosen:
        pkg = packages.get(row["printed_formula"])
        if not gate:
            gated.append(row)
            continue
        got = MG.check(row, pkg, view, case, configuration, qlits=qlits)
        row["gate"] = got
        (gated if got["passed"] else refused).append(row)

    omitted = [{"printed": r["printed_formula"],
                "family": str(fam_of.get(r["printed_formula"]))[:80],
                "cap_responsible": "the %d-formula discovery cap" % cap}
               for r in pool if r["printed_formula"] not in reasons]
    return {
        "complete_pool": len(rows),
        "after_cheap_mechanical_refusals": len(pool),
        "cheap_refusals": cheap_refused[:40],
        "cheap_refusal_count": len(cheap_refused),
        "families_in_the_pool": len(fam),
        "operator_families_in_the_pool": len(by_operator),
        "discovery_set": gated,
        "entry_reasons": reasons,
        "entry_rounds": rounds,
        "round_counts": dict(collections.Counter(rounds.values())),
        "per_family_counts": dict(
            (str(k)[:70], v) for k, v in per_family_count.most_common(10)),
        "refused_by_the_gate": [{"printed": r["printed_formula"],
                                 "refusals": r["gate"]["refusals"]}
                                for r in refused],
        "omitted": omitted[:60],
        "omitted_count": len(omitted),
        "cap": cap, "per_family_soft_cap": per_family,
    }


# --------------------------------------------------- chain graph (WP4)

def dependency_graph(rows, view):
    """Candidates, facts and question targets, joined by what can meet what.

    A SCHEDULING DEVICE.  An edge says one formula's conclusion could unify
    with another's premise; it says nothing about whether either is true.
    """
    qlits = question_needs(view)
    facts = []
    for c in view.get("final_clauses") or []:
        if not isinstance(c, dict) or "@question" in c:
            continue
        body = c.get("@logic")
        if isinstance(body, list) and body and not isinstance(body[0], list):
            facts.append(body)
    edges, to_question, from_facts = [], [], []
    for i, a in enumerate(rows):
        for j, b in enumerate(rows):
            if i == j:
                continue
            if any(unifiable(a["head"], l) for l in b["body"]):
                edges.append((i, j))
        if any(unifiable(a["head"], q) for q in qlits):
            to_question.append(i)
        if all(any(unifiable(f, l) for f in facts) for l in a["body"]):
            from_facts.append(i)
    return {"edges": edges, "to_question": to_question,
            "grounded_in_facts": from_facts,
            "note": "a scheduling device only: an edge is a unification "
                    "opportunity, never a claim that either rule is valid"}


def chain_paths(rows, graph, max_length=MAX_CHAIN_LENGTH, cap=40):
    """Bounded paths that end at a question target, shortest first."""
    out, seen = [], set()
    adj = collections.defaultdict(list)
    for a, b in graph["edges"]:
        adj[a].append(b)
    targets = set(graph["to_question"])

    def walk(node, path):
        if len(out) >= cap or len(path) > max_length:
            return
        if node in targets and len(path) >= 1:
            key = tuple(sorted(path))
            if key not in seen:
                seen.add(key)
                out.append(list(path))
        if len(path) >= max_length:
            return
        for nxt in adj.get(node, []):
            if nxt in path:
                continue
            walk(nxt, path + [nxt])

    starts = graph["grounded_in_facts"] or list(range(len(rows)))
    for s in starts:
        walk(s, [s])
    if not out:
        # nothing reaches a question literal directly.  Fall back to paths that
        # end at a premise of a source rule — the next thing the theory needs —
        # and say so, rather than returning an empty pool.
        for i, a in enumerate(rows):
            if len(out) >= cap:
                break
            out.append([i])
    out.sort(key=len)
    return out[:cap]


def chain_pool(rows, view, max_formulas=DISCOVERY_CAP_V2):
    """The union of the best distinct structural paths, as its own pool."""
    graph = dependency_graph(rows, view)
    paths = chain_paths(rows, graph)
    picked, chosen = [], []
    for path in paths:
        for i in path:
            if rows[i]["printed_formula"] not in [r["printed_formula"]
                                                  for r in chosen]:
                chosen.append(rows[i])
        picked.append([rows[i]["printed_formula"] for i in path])
        if len(chosen) >= max_formulas:
            break
    return {"rows": chosen, "paths": picked[:12], "path_count": len(paths),
            "edges": len(graph["edges"]),
            "candidates_reaching_the_question": len(graph["to_question"]),
            "candidates_grounded_in_facts": len(graph["grounded_in_facts"]),
            "note": graph["note"]}


# ------------------------------------------- alternative proofs (WP5)

def alternative_proofs(base_result, hyps, view, configuration, gk, budget,
                       case_id, first_minimal, cap=MAX_EXCLUSION_WORLDS):
    """Exclude one cited bridge at a time and look for a different proof.

    A pooled call returns one proof even when several exist, so a false proof
    found first can hide a better one.  Each exclusion world is a separate
    FULL-CONFIDENCE search: nothing is reweighted, a bridge is simply absent.
    """
    out, seen = [], {tuple(sorted(first_minimal))}
    excluded_ids = list(first_minimal)[:cap]
    by_id = dict((h["hypothesis_id"], h) for h in hyps)
    pool_ids = [h["hypothesis_id"] for h in hyps]
    for drop in excluded_ids:
        if len(out) >= cap or not budget():
            break
        keep = [by_id[h] for h in pool_ids if h != drop and h in by_id]
        if not keep:
            continue
        world = build_world("alt_%s_without_%s" % (case_id,
                                                   by_id[drop]["label"]),
                            keep, view, configuration)
        got = run_world(world, view, gk, "%s/without %s"
                        % (case_id, by_id[drop]["label"]))
        row = {"excluded": drop,
               "excluded_formula": by_id[drop]["printed_formula"],
               "answer": got["answer"],
               "gk_native_confidence": got["gk_native_confidence"],
               "cited": got["cited_hypothesis_ids"],
               "cited_formulas": got["cited_formulas"]}
        if got["answer"] is not None and got["cited_hypothesis_ids"]:
            m = minimise(got, keep, view, configuration, gk, budget, case_id)
            row["minimal_set"] = m.get("minimal_set")
            row["minimal_formulas"] = m.get("minimal_formulas")
            row["reproduced"] = m.get("replay_reproduced")
            key = tuple(sorted(m.get("minimal_set") or []))
            row["is_a_new_distinct_proof"] = bool(key) and key not in seen
            if key:
                seen.add(key)
        else:
            row["is_a_new_distinct_proof"] = False
        out.append(row)
    return {"exclusion_worlds": out, "cap": cap,
            "distinct_minimal_sets": [list(k) for k in seen],
            "note": "each exclusion is a separate full-confidence world; no "
                    "bridge confidence is altered inside gk"}


def run_case_v2(view, respond, gk, bounds=None, weight=None,
                prior_records=None, pair_judgements=None, configuration=None,
                cap=DISCOVERY_CAP_V2):
    """Pooled discovery with stratified coverage and alternative-proof search.

    The shared stages are `dynamic_runtime`'s, unchanged.  What differs from
    v1: the discovery set is filled in rounds instead of first-come, a
    chain-directed pool is built from the dependency graph, and after a proof
    is minimised each of its bridges is excluded in turn to see whether a
    different proof exists behind it.
    """
    import dynamic_runtime as RT
    bounds = bounds or {}
    weight = RT.WORLD_WEIGHT if weight is None else weight
    configuration = configuration or view["configuration"]
    budget = bounds.get("gk_budget", lambda: True)
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": view["case_id"], "mode": "pooled_discovery_v2",
              "view_sha256": RT.view_hash(view), "conservative": front,
              "trace": trace, "dynamic_work_done": False}
    if front["resolved"]:
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    fr = RT.frontier(view)
    result["frontier"] = {k: fr[k] for k in ("version", "counts", "selected")}
    pick = RT.select_groups(view, fr, RT.source_atoms(view), respond,
                            allow_retry=bounds.get("selector_retry", True))
    result["group_selection"] = {k: pick[k] for k in
                                 ("groups_total", "groups_shown", "selected",
                                  "used_the_fallback", "retried", "raw")}
    case = RT.case_of(view, fr, pick["selected"])
    con = RT.construction(case, view, respond,
                          allow_retry=bounds.get("construction_retry", True))
    result["construction"] = {"retried": con["retried"],
                              "parsed": con["parsed"], "built": con["built"],
                              "raw": con["raw"]}
    proposals = con["parsed"].get("proposals") or []
    acc, packages = CP.collect(case, view["case_id"], proposals)
    rows = acc.rows()
    model_rows = [r for r in rows if CP.model_reached(r)]
    model_rows.sort(key=lambda r: (min(
        i for i, p in enumerate(r["derivation_paths"])
        if p["source_run"] == CP.MODEL_RUN), r["printed_formula"]))
    selected_printed = []
    if model_rows and bounds.get("formula_selector", True):
        chosen = RT.select_formulas(view, case, model_rows, respond,
                                    allow_retry=bounds.get("selector_retry",
                                                           True))
        selected_printed = [r["printed_formula"] for r in chosen["chosen"]]
        result["formula_selection"] = {
            "formulas_total": chosen["formulas_total"],
            "formulas_shown": chosen["formulas_shown"],
            "selected_ids": chosen["selected_ids"],
            "used_the_fallback": chosen["used_the_fallback"],
            "raw": chosen["raw"]}

    built = stratified_discovery_set(rows, selected_printed, view, case,
                                     packages, configuration, cap=cap)
    discovery = built["discovery_set"]
    result["pool"] = {k: built[k] for k in
                      ("complete_pool", "after_cheap_mechanical_refusals",
                       "cheap_refusal_count", "families_in_the_pool",
                       "operator_families_in_the_pool", "round_counts",
                       "per_family_counts", "refused_by_the_gate",
                       "omitted_count", "omitted", "cap",
                       "per_family_soft_cap")}
    result["discovery_set"] = [
        {"printed": r["printed_formula"],
         "why_it_entered": built["entry_reasons"].get(r["printed_formula"]),
         "round": built["entry_rounds"].get(r["printed_formula"]),
         "operator_family": operator_family(r),
         "head_signature": list(head_signature(r)),
         "paths": len(r.get("derivation_paths") or []),
         "warnings": (r.get("gate") or {}).get("warnings")}
        for r in discovery]
    if not discovery:
        result["stopped_at"] = "no_candidate_survived"
        return result

    disfavoured = counterexampled_index(prior_records, pair_judgements)
    result["disfavoured_before_the_run"] = dict(
        (k, v) for k, v in disfavoured.items()
        if k in set(r["printed_formula"] for r in discovery))

    chain = chain_pool(discovery, view)
    result["chain_graph"] = {k: chain[k] for k in
                             ("paths", "path_count", "edges",
                              "candidates_reaching_the_question",
                              "candidates_grounded_in_facts", "note")}
    hyps_all = hypotheses_for(discovery, packages, view["case_id"], weight)
    by_print = dict((h["printed_formula"], h) for h in hyps_all)
    specs = make_pools(discovery, result["disfavoured_before_the_run"])
    specs.append({"pool": "D_chain_directed", "rows": chain["rows"],
                  "why": "the union of the best bounded structural paths "
                         "toward a question target; a scheduling device, not "
                         "a claim of validity"})

    runs, worlds_used = [], 0
    for spec in specs:
        hyps = [by_print[r["printed_formula"]] for r in spec["rows"]
                if r["printed_formula"] in by_print]
        if not hyps or worlds_used >= MAX_CONFLICT_WORLDS or not budget():
            runs.append({"pool": spec["pool"], "why": spec["why"],
                         "skipped": "no candidate, cap, or gk budget"})
            continue
        world = build_world("pool_%s_%s" % (view["case_id"], spec["pool"]),
                            hyps, view, configuration)
        got = run_world(world, view, gk, "%s/%s" % (view["case_id"],
                                                    spec["pool"]))
        worlds_used += 1
        got.update({"pool": spec["pool"], "why": spec["why"],
                    "candidates": len(hyps)})
        got["direct_conflicts_inside_this_pool"] = conflict_components(
            spec["rows"])[:8]
        runs.append(got)
    result["pool_worlds"] = runs
    result["pool_worlds_used"] = worlds_used

    minimal, seen_sets = [], set()
    for got in runs:
        if got.get("skipped") or got.get("answer") is None:
            continue
        key = tuple(sorted(got["cited_hypothesis_ids"]))
        if key in seen_sets:
            continue
        seen_sets.add(key)
        m = minimise(got, hyps_all, view, configuration, gk, budget,
                     view["case_id"])
        m["pool"] = got["pool"]
        m["answer"] = got["answer"]
        m["native_gk_confidence"] = got["gk_native_confidence"]
        minimal.append(m)
    result["minimisation"] = minimal

    alternatives = []
    for m in minimal:
        if not m.get("minimised"):
            continue
        got = next(g for g in runs if g.get("pool") == m["pool"])
        hyps_here = [by_print[f] for f in
                     [r["printed_formula"] for r in
                      next(s["rows"] for s in specs
                           if s["pool"] == m["pool"])]
                     if f in by_print]
        alt = alternative_proofs(got, hyps_here, view, configuration, gk,
                                 budget, view["case_id"],
                                 m.get("minimal_set") or [])
        alt["from_pool"] = m["pool"]
        alternatives.append(alt)
        break                      # one pool's exclusions, inside the cap
    result["alternative_proofs"] = alternatives

    all_minimal = []
    for m in minimal:
        if m.get("minimal_set"):
            all_minimal.append(m["minimal_set"])
    for alt in alternatives:
        for row in alt["exclusion_worlds"]:
            if row.get("minimal_set"):
                all_minimal.append(row["minimal_set"])
    distinct = []
    for s in all_minimal:
        key = tuple(sorted(s))
        if key not in [tuple(sorted(x)) for x in distinct]:
            distinct.append(list(s))
    result["distinct_minimal_sets"] = distinct

    result["assessment"] = assess_after_proof(
        view, case, fr, discovery, hyps_all,
        [{"minimal_set": s} for s in distinct] or minimal, runs, respond,
        result["disfavoured_before_the_run"], bounds, weight)
    result["stopped_at"] = None
    return result


# =====================================================================
# v3: fair scheduling across a cohort, trust-guided exclusion, scope
# =====================================================================

MAX_EXCLUSIONS_PER_CASE = 8

# Which cited bridge to exclude first.  Lowest trust first, and within that the
# mechanically suspicious shapes named in the plan: a reversed or otherwise odd
# argument mapping, a counterexampled direction, an unsupported attachment, a
# generalisation of something grounded, and a passage-bound claim compiled as a
# general rule.
TRUST_ORDER = {"counterexampled": 0, "speculative": 1, "unassessed": 2,
               "plausible": 3, "supported": 4}


def scope_of(row):
    """`grounded` when the rule names a particular thing, else `general`."""
    for lit in list(row["body"]) + [row["head"]]:
        for t in _split(lit)[3]:
            if isinstance(t, str) and not _is_var(t):
                return "grounded"
    return "general"


def suspicion(bridge, record):
    """How mechanically suspicious a cited bridge is, for exclusion order."""
    marks = []
    axes = (record or {}).get("axes") or {}
    if (axes.get("direction") or {}).get("value") == "COUNTEREXAMPLED":
        marks.append("counterexampled direction")
    if (axes.get("attachment") or {}).get("result") in (
            "UNSUPPORTED_IDENTIFICATION", "NOT_ASSESSED"):
        marks.append("unsupported or unassessed attachment")
    paths = bridge.get("derivation_paths") or []
    if any(p.get("system_direction_variant") for p in paths):
        marks.append("a system-reversed argument mapping")
    if any(p.get("system_scope_variant") for p in paths):
        marks.append("a system generalisation of a grounded claim")
    if (axes.get("passage") or {}).get("value") in ("PASSAGE_RESTRICTED",) \
            and scope_of(bridge) == "general":
        marks.append("a passage-bound claim compiled as a general rule")
    return marks


def classify_set(rows):
    """WP6's six categories, over the assessed bridges of one minimal set."""
    if not rows:
        return "mechanically invalid"
    trusts = [r["trust"] for r in rows]
    scopes = [r.get("scope") for r in rows]
    if all(t == "counterexampled" for t in trusts):
        return "all counterexampled"
    if all(t in ("supported", "plausible") for t in trusts):
        if all(s == "general" for s in scopes):
            return "all generally defensible"
        return "all defensible with stated local restrictions"
    if all(t in ("speculative", "unassessed", "counterexampled")
           for t in trusts):
        return "all doubtful"
    return "mixed defensible and doubtful"


def run_cohort(views, respond, gk, bounds=None, weight=None,
               prior_records=None, pair_judgements=None, cap=DISCOVERY_CAP_V2):
    """Every case's pools first, then minimisation and exclusion.

    The first case to find a proof must not spend the whole budget: phase one
    runs the three principal pools for every unanswered case, and only then
    does phase two minimise, assess and search for alternatives.  Whatever the
    caps stop is listed by name rather than dropped.
    """
    import dynamic_runtime as RT
    bounds = bounds or {}
    weight = RT.WORLD_WEIGHT if weight is None else weight
    budget = bounds.get("gk_budget", lambda: True)
    disfavoured_all = counterexampled_index(prior_records, pair_judgements)
    state, unrun = [], []

    # ---------------------------------------------------------- phase one
    for view in views:
        cid = view["case_id"]
        rec = {"case_id": cid, "mode": "pooled_discovery_v3",
               "view_sha256": RT.view_hash(view),
               "configuration": view["configuration"], "trace": []}
        front = RT.front_door(view, gk)
        rec["conservative"] = front
        rec["dynamic_work_done"] = not front["resolved"]
        if front["resolved"]:
            rec["stopped_at"] = "front_door_answered"
            state.append((view, rec, None, None, None))
            continue
        fr = RT.frontier(view)
        rec["frontier"] = {k: fr[k] for k in ("version", "counts", "selected")}
        pick = RT.select_groups(view, fr, RT.source_atoms(view), respond,
                                allow_retry=bounds.get("selector_retry", True))
        rec["group_selection"] = {k: pick[k] for k in
                                  ("groups_total", "groups_shown", "selected",
                                   "used_the_fallback", "retried", "raw")}
        case = RT.case_of(view, fr, pick["selected"])
        con = RT.construction(case, view, respond,
                              allow_retry=bounds.get("construction_retry",
                                                     True))
        rec["construction"] = {"retried": con["retried"],
                               "parsed": con["parsed"], "built": con["built"],
                               "raw": con["raw"]}
        acc, packages = CP.collect(case, cid,
                                   con["parsed"].get("proposals") or [])
        rows = acc.rows()
        model_rows = [r for r in rows if CP.model_reached(r)]
        model_rows.sort(key=lambda r: (min(
            i for i, p in enumerate(r["derivation_paths"])
            if p["source_run"] == CP.MODEL_RUN), r["printed_formula"]))
        selected_printed = []
        if model_rows:
            chosen = RT.select_formulas(view, case, model_rows, respond,
                                        allow_retry=bounds.get(
                                            "selector_retry", True))
            selected_printed = [r["printed_formula"] for r in chosen["chosen"]]
            rec["formula_selection"] = {
                "formulas_total": chosen["formulas_total"],
                "formulas_shown": chosen["formulas_shown"],
                "selected_ids": chosen["selected_ids"],
                "used_the_fallback": chosen["used_the_fallback"],
                "raw": chosen["raw"]}
        built = stratified_discovery_set(rows, selected_printed, view, case,
                                         packages, view["configuration"],
                                         cap=cap)
        discovery = built["discovery_set"]
        rec["pool"] = {k: built[k] for k in
                       ("complete_pool", "after_cheap_mechanical_refusals",
                        "cheap_refusal_count", "families_in_the_pool",
                        "operator_families_in_the_pool", "round_counts",
                        "refused_by_the_gate", "omitted_count", "cap")}
        rec["discovery_set"] = [
            {"printed": r["printed_formula"],
             "why_it_entered": built["entry_reasons"].get(r["printed_formula"]),
             "round": built["entry_rounds"].get(r["printed_formula"]),
             "operator_family": operator_family(r),
             "scope": scope_of(r),
             "paths": len(r.get("derivation_paths") or []),
             "warnings": (r.get("gate") or {}).get("warnings")}
            for r in discovery]
        if not discovery:
            rec["stopped_at"] = "no_candidate_survived"
            state.append((view, rec, None, None, None))
            continue
        disfavoured = dict((k, v) for k, v in disfavoured_all.items()
                           if k in set(r["printed_formula"]
                                       for r in discovery))
        rec["disfavoured_before_the_run"] = disfavoured
        chain = chain_pool(discovery, view)
        rec["chain_graph"] = {k: chain[k] for k in
                              ("path_count", "edges",
                               "candidates_reaching_the_question",
                               "candidates_grounded_in_facts", "note")}
        hyps_all = hypotheses_for(discovery, packages, cid, weight)
        by_print = dict((h["printed_formula"], h) for h in hyps_all)
        specs = make_pools(discovery, disfavoured)
        order = {POOL_A: 0, "D_chain_directed": 1, POOL_B: 2, POOL_C: 3}
        specs.append({"pool": "D_chain_directed", "rows": chain["rows"],
                      "why": "the union of the best bounded structural paths; "
                             "a scheduling device, not a claim of validity"})
        specs.sort(key=lambda s: order.get(s["pool"], 9))
        runs, used = [], 0
        for spec in specs:
            hyps = [by_print[r["printed_formula"]] for r in spec["rows"]
                    if r["printed_formula"] in by_print]
            if not hyps:
                runs.append({"pool": spec["pool"], "skipped": "no candidate"})
                continue
            if used >= MAX_CONFLICT_WORLDS or not budget():
                unrun.append({"case": cid, "pool": spec["pool"],
                              "why": "pool cap" if used >= MAX_CONFLICT_WORLDS
                              else "gk budget"})
                runs.append({"pool": spec["pool"],
                             "skipped": "pool cap or gk budget"})
                continue
            world = build_world("pool_%s_%s" % (cid, spec["pool"]), hyps, view,
                                view["configuration"])
            got = run_world(world, view, gk, "%s/%s" % (cid, spec["pool"]))
            used += 1
            got.update({"pool": spec["pool"], "why": spec["why"],
                        "candidates": len(hyps)})
            got["direct_conflicts_inside_this_pool"] = conflict_components(
                spec["rows"])[:8]
            runs.append(got)
        rec["pool_worlds"] = runs
        rec["pool_worlds_used"] = used
        state.append((view, rec, case, fr, (discovery, hyps_all, by_print,
                                            specs)))

    # ---------------------------------------------------------- phase two
    for view, rec, case, fr, extra in state:
        if extra is None:
            continue
        discovery, hyps_all, by_print, specs = extra
        cid = view["case_id"]
        runs = rec["pool_worlds"]
        minimal, seen = [], set()
        for got in runs:
            if got.get("skipped") or got.get("answer") is None:
                continue
            key = tuple(sorted(got["cited_hypothesis_ids"]))
            if key in seen:
                continue
            seen.add(key)
            if not budget():
                unrun.append({"case": cid, "minimisation": got["pool"],
                              "why": "gk budget"})
                continue
            m = minimise(got, hyps_all, view, view["configuration"], gk,
                         budget, cid)
            m.update({"pool": got["pool"], "answer": got["answer"],
                      "native_gk_confidence": got["gk_native_confidence"]})
            minimal.append(m)
        rec["minimisation"] = minimal

        first = next((m for m in minimal if m.get("minimised")), None)
        rec["assessment"] = {"cited_bridges": 0, "results": []}
        exclusions = []
        if first:
            rec["assessment"] = assess_after_proof(
                view, case, fr, discovery, hyps_all,
                [{"minimal_set": first["minimal_set"]}], runs, respond,
                rec.get("disfavoured_before_the_run") or {}, bounds, weight)
            per = dict((b["hypothesis_id"], b)
                       for b in rec["assessment"].get("per_bridge") or [])
            got = next(g for g in runs if g.get("pool") == first["pool"])
            pool_rows = next(s["rows"] for s in specs
                             if s["pool"] == first["pool"])
            hyps_here = [by_print[r["printed_formula"]] for r in pool_rows
                         if r["printed_formula"] in by_print]
            by_id = dict((h["hypothesis_id"], h) for h in hyps_here)
            ranked = sorted(
                first["minimal_set"],
                key=lambda h: (TRUST_ORDER.get(per.get(h, {}).get("trust",
                                                                  "unassessed"),
                                               2),
                               -len(suspicion(by_id.get(h, {}), None)), h))
            done = {tuple(sorted(first["minimal_set"]))}
            for drop in ranked[:MAX_EXCLUSIONS_PER_CASE]:
                if not budget() or len(exclusions) >= MAX_EXCLUSIONS_PER_CASE:
                    unrun.append({"case": cid, "exclusion": drop,
                                  "why": "gk budget or exclusion cap"})
                    continue
                keep = [h for h in hyps_here if h["hypothesis_id"] != drop]
                if not keep:
                    continue
                world = build_world("excl_%s_%s" % (cid, by_id[drop]["label"]),
                                    keep, view, view["configuration"])
                out = run_world(world, view, gk, "%s/excl %s"
                                % (cid, by_id[drop]["label"]))
                row = {"excluded": drop,
                       "excluded_formula": by_id[drop]["printed_formula"],
                       "excluded_trust": per.get(drop, {}).get("trust"),
                       "why_this_one_first": suspicion(by_id.get(drop, {}),
                                                       None),
                       "answer": out["answer"],
                       "gk_native_confidence": out["gk_native_confidence"],
                       "cited": out["cited_hypothesis_ids"]}
                if out["answer"] is not None and out["cited_hypothesis_ids"] \
                        and budget():
                    m2 = minimise(out, keep, view, view["configuration"], gk,
                                  budget, cid)
                    row["minimal_set"] = m2.get("minimal_set")
                    row["minimal_formulas"] = m2.get("minimal_formulas")
                    row["reproduced"] = m2.get("replay_reproduced")
                    key = tuple(sorted(m2.get("minimal_set") or []))
                    row["is_a_new_distinct_proof"] = bool(key) and \
                        key not in done
                    row["blocked_to_expose_this"] = drop
                    if key:
                        done.add(key)
                else:
                    row["is_a_new_distinct_proof"] = False
                exclusions.append(row)
        rec["exclusions"] = exclusions

        sets = []
        for m in minimal:
            if m.get("minimal_set"):
                sets.append({"bridges": m["minimal_set"],
                             "formulas": m.get("minimal_formulas"),
                             "answer": m["answer"],
                             "native_gk_confidence":
                                 m.get("native_gk_confidence"),
                             "from_pool": m["pool"],
                             "blocked_to_expose_this": None})
        for row in exclusions:
            if row.get("minimal_set"):
                sets.append({"bridges": row["minimal_set"],
                             "formulas": row.get("minimal_formulas"),
                             "answer": row["answer"],
                             "native_gk_confidence":
                                 row.get("gk_native_confidence"),
                             "from_pool": "exclusion",
                             "blocked_to_expose_this":
                                 row.get("blocked_to_expose_this")})
        distinct, keys = [], set()
        for s in sets:
            key = tuple(sorted(s["bridges"]))
            if key in keys:
                continue
            keys.add(key)
            distinct.append(s)
        rec["distinct_minimal_sets"] = distinct
        rec["stopped_at"] = rec.get("stopped_at")
    return {"cases": [rec for _v, rec, _c, _f, _e in state],
            "unrun": unrun,
            "scheduling": "phase one ran every unanswered case's three "
                          "principal pools; phase two spent what remained on "
                          "minimisation, assessment and exclusion"}
