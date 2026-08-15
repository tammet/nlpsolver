"""The v3 semantic-admission stage, wired to the live runtime objects.

This is the optional `semantic_v3` mode.  `legacy` is unchanged and remains the
default: selecting the old mode restores the old behaviour without editing a
prompt or a record.

Two things separate this from the stored-challenge experiment.  It builds every
semantic input from the live view, table, schema, witness and menu — nothing is
resolved again from disk, so what the model judges is what the runtime holds.
And a guard preview that fails is a refusal, not an empty menu: the offline
display helper swallowed exceptions, which at runtime would turn an internal
error into "this rule needs no guard".

Proof activity has exactly one use here, and it is scheduling: after the
selector's own priorities are reviewed, one leftover slot may go to a schema a
probe proved.  It never reaches a prompt, an evidence category, the falsifier or
the decision.
"""

import admission_checks as AK
import admission_stage as AS
import alignment_context as CX
import alignment_rule as AR
import bridge_world as BW
import dynamic_score as DS
import formula_print as FP

LEGACY = "legacy"
SEMANTIC_V3 = "semantic_v3"
MODES = (LEGACY, SEMANTIC_V3)

# New state names.  The old ones described a different decision and reusing them
# would make two runs look comparable when they are not.
STATES = (
    "semantic_mechanical_refused",
    "semantic_judge_refused",
    "semantic_guard_refused",
    "semantic_falsifier_refused",
    "semantic_opposite_conflict",
    "semantic_promoted",
    "semantic_promoted_no_answer",
    "semantic_prompt_error",
)

MAX_SELECTOR_GROUPS = 3
MAX_SUPPLEMENT_GROUPS = 1

GUARD_PREVIEW_ERROR = "guard_preview_error"


class RuntimeAdmissionError(Exception):
    pass


# ---------------------------------------------------------------- WP2 adapter

def semantic_input(view, table, schema, previews):
    """The same shape a frozen challenge has, built from live objects only.

    Nothing here may come from a key, a reviewed rule, an accepted answer or a
    scored artifact — and nothing may say what gk did.
    """
    import build_admission_challenges as B          # shaping helpers only
    return {
        "challenge": schema["schema_id"],
        "case_id": view["case_id"],
        "schema_id_in_run": schema["schema_id"],
        "rule": schema["canonical_signed_rule"],
        "stage2_rule": schema["stage2_rule"],
        "target_mode": schema.get("target_mode"),
        "input_text": view["input_text"],
        "sentences": B.sentences(view),
        "source_evidence": schema["source_evidence"],
        "terms": B.describe_terms(schema["stage2_rule"]),
        "in_words": B.in_words(schema["stage2_rule"]),
        "conditions_offered": [{"alias": p["alias"], "atom": p["source_atom"],
                                "why_offered": p["why_offered"]}
                               for p in previews],
        "compiled_guard_previews": previews,
        "preselected_conditions": [],
    }


def previews(view, table, schema):
    """-> {"ok": True, "previews": [...]} or {"ok": False, "refusal": ...}.

    Every selectable preview is `compile_from_base` on this schema's own
    construction witness and this table, through the same gates the offline
    tests pin.  An exception is reported, never converted into "no guards".
    """
    try:
        # `CX.menu` answers [] for an occurrence it cannot resolve, which is
        # indistinguishable from "this rule has no companions".  An empty menu
        # is legitimate; an unresolvable base occurrence is an internal failure
        # and must be a refusal, so it is checked here rather than inferred.
        for key in ("producer_occurrences", "consumer_occurrences"):
            oid = (schema.get(key) or [None])[0]
            if oid not in table["by_id"]:
                return {"ok": False, "refusal": GUARD_PREVIEW_ERROR,
                        "detail": "%s %r is not in this table" % (key, oid)}
        if not schema.get("construction_witness"):
            return {"ok": False, "refusal": GUARD_PREVIEW_ERROR,
                    "detail": "the schema carries no construction witness"}
        rows = CX.menu(table, view["stage2"], schema["producer_occurrences"][0],
                       schema["consumer_occurrences"][0])
        base = schema["stage2_rule"]
        w = schema["construction_witness"]
        base_atoms = AS._atom_strings(base)
        out, seen = [], {}
        for i, m in enumerate(rows):
            alias = "G%d" % (i + 1)
            row = {"alias": alias, "source_atom": FP.formula(m["atom"]),
                   "occurrence": m["occurrence_id"],
                   "why_offered": m["why_offered"]}
            try:
                pkg, _rec = AR.compile_from_base(
                    w["producer"], w["consumer"], [m["occurrence_id"]], table,
                    target_mode=w.get("target_mode"),
                    require_range_restriction=True)
                pkg = BW.to_defeasible_shape(pkg)
            except (AR.RuleError, BW.BridgeError) as e:
                row["unavailable"] = "the compiler refuses it: %s" % e
                out.append(row)
                continue
            added = [a for a in AS._atom_strings(pkg) if a not in base_atoms]
            if not added:
                row["unavailable"] = "it adds no condition after canonicalization"
                out.append(row)
                continue
            gates = AK.mechanical_gates(pkg, base_pkg=base,
                                        condition_atoms=[m["atom"]])
            if not gates["ok"]:
                row["unavailable"] = ", ".join(r["name"]
                                               for r in gates["refusals"])
                out.append(row)
                continue
            guard = "; ".join(added)
            if guard in seen:
                row["unavailable"] = "same compiled guard as %s" % seen[guard]
                out.append(row)
                continue
            seen[guard] = alias
            row["compiled_guard"] = guard
            row["if_selected"] = FP.formula(pkg)
            out.append(row)
        return {"ok": True, "previews": out,
                "occurrence_by_alias": {("G%d" % (i + 1)): m["occurrence_id"]
                                        for i, m in enumerate(rows)}}
    except Exception as e:                                  # noqa: BLE001
        return {"ok": False, "refusal": GUARD_PREVIEW_ERROR,
                "detail": "%s: %s" % (type(e).__name__, e)}


def pool_gates(schemas, pool):
    """Mechanical gates over every pooled schema, before any probe or call.

    -> {schema_id: {"ok", "refusals"}}.  A refusal here makes the schema
    permanently ineligible for promotion; it does not stop the probe, because a
    probe asks what would follow and answers nothing about belief.
    """
    by_id = {s["schema_id"]: s for s in schemas}
    out = {}
    for sid in pool:
        s = by_id.get(sid)
        if s is None or "stage2_rule" not in s:
            # the record's copy of a schema is stripped of its package; this
            # must be called with the LIVE schemas, and saying so beats
            # silently reporting no refusals
            raise RuntimeAdmissionError(
                "pool_gates needs the live schema objects (%s has no "
                "stage2_rule)" % sid)
        g = AK.mechanical_gates(s["stage2_rule"], schema_id=sid)
        out[sid] = {"ok": g["ok"],
                    "refusals": [r["name"] for r in g["refusals"]],
                    "detail": g["refusals"]}
    return out


def ineligible(rec):
    """Pooled schema ids the mechanical gates already refused."""
    return set(sid for sid, g in (rec.get("pool_mechanical") or {}).items()
               if not g["ok"])


# ---------------------------------------------------------------- WP3 groups

def schedule(schemas, selected, pool, proof_active, ineligible_ids=()):
    """-> [{"members": [schema_id, ...], "reason": ...}] in review order.

    A chosen schema and its unchosen opposite sibling are reviewed as one group,
    so the judge compares them instead of ruling on each alone.  No canonical
    formula and no sibling group is reviewed twice.  The supplement's reason is
    scheduling metadata and never reaches a prompt.
    """
    by_id = {s["schema_id"]: s for s in schemas}
    groups = AK.opposite_head_groups(schemas)
    seen, out = set(), []

    def group_of(sid):
        g = AK.in_conflict(sid, groups)
        if not g:
            return [sid]
        both = [x for x in (g["positive"] + g["negative"]) if x in by_id]
        return sorted(set(both), key=lambda x: (x != sid, x))

    for sid in selected:
        if sid in seen or sid not in by_id:
            continue
        if sid in ineligible_ids:
            seen.add(sid)
            continue
        members = group_of(sid)
        if any(m in seen for m in members):
            continue
        seen.update(members)
        out.append({"members": members, "reason": "selector_priority"})
        if len([g for g in out if g["reason"] == "selector_priority"]) \
                >= MAX_SELECTOR_GROUPS:
            break
    return out, groups, seen


def supplement(schemas, proof_active, seen, groups, budget_ok):
    """At most one leftover group, chosen because a probe proved it."""
    if not budget_ok:
        return []
    by_id = {s["schema_id"]: s for s in schemas}
    for sid in proof_active:
        if sid in seen or sid not in by_id:
            continue
        g = AK.in_conflict(sid, groups)
        members = sorted(set([x for x in (g["positive"] + g["negative"])
                              if x in by_id])) if g else [sid]
        if any(m in seen for m in members):
            continue
        return [{"members": members, "reason": "proof_active_supplement"}]
    return []


# ---------------------------------------------------------------- WP4 protocol

def review_group(view, table, by_id, members, respond, tr=None):
    """The v3 protocol over one singleton or opposite-head group.

    -> {schema_id: row}.  A row always has a state, and always says why.
    """
    rows, inputs, gates, pvs = {}, {}, {}, {}
    for sid in members:
        s = by_id[sid]
        pv = previews(view, table, s)
        pvs[sid] = pv
        gates[sid] = AK.mechanical_gates(s["stage2_rule"])
        if pv["ok"]:
            inputs[sid] = semantic_input(view, table, s, pv["previews"])

    # every mechanical refusal happens before any call
    blocked = {}
    for sid in members:
        why = [r["name"] for r in gates[sid]["refusals"]]
        if not pvs[sid]["ok"]:
            why.append(pvs[sid]["refusal"])
        if why:
            blocked[sid] = why
    if len(blocked) == len(members):
        for sid in members:
            rows[sid] = _row(by_id[sid], "semantic_mechanical_refused",
                             blocked[sid], gates[sid], pvs[sid])
        return rows, 0

    calls = 0
    pair = len(members) == 2
    first_id = members[0]
    ch = inputs.get(first_id) or inputs[[m for m in members if m in inputs][0]]
    sib = inputs.get(members[1]) if pair and members[1] in inputs else None
    prompt = AS.build_judge_prompt(ch, sib)
    text, _log, note = respond("judge", prompt, {"schemas": members})
    calls += 1
    judged = AS.parse_judge(text, pair=sib is not None)
    raws = {"judge": text}
    if not judged["readable"] and text is not None:
        text2, _l2, _n2 = respond(
            "judge_retry",
            prompt + "\n\nYour previous reply had no readable FINAL line. "
                     "Reply with the footer lines only.",
            {"schemas": members, "retry": True})
        calls += 1
        raws["judge_retry"] = text2
        judged = AS.parse_judge(text2, pair=sib is not None)

    for sid in members:
        if sid in blocked:
            rows[sid] = _row(by_id[sid], "semantic_mechanical_refused",
                             blocked[sid], gates[sid], pvs[sid], raws=raws)
            continue
        if not judged["readable"]:
            rows[sid] = _row(by_id[sid], "semantic_prompt_error",
                             ["the judge footer was unreadable twice"],
                             gates[sid], pvs[sid], raws=raws)
            continue
        if sib is not None:
            mine = judged["verdict"] == ("FIRST" if sid == first_id else "SECOND")
            eff = {"verdict": "ACCEPT" if mine else "REJECT",
                   "mechanism": judged["mechanism"] if mine else None,
                   "evidence": judged.get("evidence") if mine else None,
                   "guard_needed": judged["guard_needed"] if mine else None,
                   "readable": True}
        else:
            eff = judged

        guards, final_pkg = None, by_id[sid]["stage2_rule"]
        if eff["verdict"] == "NEEDS_GUARD":
            gtext, _gl, _gn = respond(
                "guard", AS.build_guard_prompt(inputs[sid],
                                               eff["guard_needed"]),
                {"schema": sid})
            calls += 1
            aliases = [p["alias"] for p in pvs[sid]["previews"]
                       if not p.get("unavailable")]
            chosen = AS.parse_guards(gtext, aliases)
            raws.setdefault("guard", {})[sid] = gtext
            guards = dict(chosen)
            if chosen["readable"] and chosen["guards"]:
                comp = _compile(view, table, by_id[sid],
                                pvs[sid]["occurrence_by_alias"],
                                chosen["guards"])
                guards.update(comp)
                if comp.get("compiled"):
                    final_pkg = comp["package"]
            else:
                guards["compiled"] = False

        falsifier = None
        eligible = (eff["verdict"] == "ACCEPT"
                    or (eff["verdict"] == "NEEDS_GUARD"
                        and (guards or {}).get("compiled")))
        if eligible:
            ftext, _fl, _fn = respond(
                "falsifier",
                AS.build_falsifier_prompt(inputs[sid], FP.formula(final_pkg)),
                {"schema": sid})
            calls += 1
            falsifier = AS.parse_falsifier(ftext)
            raws.setdefault("falsifier", {})[sid] = ftext

        final_gates = AK.mechanical_gates(
            final_pkg, base_pkg=by_id[sid]["stage2_rule"],
            condition_atoms=_atoms(view, table, by_id[sid],
                                   pvs[sid]["occurrence_by_alias"],
                                   (guards or {}).get("guards") or []))
        d = AS.decide(final_gates, eff, guards, falsifier,
                      judged["verdict"] if sib is not None else None,
                      (sid == first_id) if sib is not None else None)
        row = _row(by_id[sid], None, d["refusals"], final_gates, pvs[sid],
                   raws=raws, judge=eff, judge_raw_verdict=judged["verdict"],
                   guards=guards, falsifier=falsifier,
                   final_pkg=final_pkg, evidence=d.get("evidence"))
        row["state"] = _state(d, eff, guards, falsifier)
        rows[sid] = row
    return rows, calls


def _state(d, judge, guards, falsifier):
    if d["outcome"] == AS.PROMOTE:
        return "semantic_promoted"
    for r in d["refusals"]:
        if r.startswith("mechanical:") or r.startswith("guard:"):
            return "semantic_guard_refused" if r.startswith("guard:") \
                else "semantic_mechanical_refused"
        if r == AK.OPPOSITE_HEAD_CONFLICT or r.startswith("opposite_head"):
            return "semantic_opposite_conflict"
        if r.startswith("falsifier:"):
            return "semantic_falsifier_refused"
        if r.startswith("judge:needs_guard"):
            return "semantic_guard_refused"
    return "semantic_judge_refused"


def _scrub(d):
    """`mechanism` is a reviewed-metadata key elsewhere in this codebase.

    The gold gate scans records for that key by name, so the judge's alignment
    mechanism is recorded under its own name.  Renamed only when written down —
    the decision has already read it.
    """
    if not isinstance(d, dict) or "mechanism" not in d:
        return d
    out = dict(d)
    out["alignment_mechanism"] = out.pop("mechanism")
    return out


def _row(schema, state, refusals, gates, pv, raws=None, judge=None,
         judge_raw_verdict=None, guards=None, falsifier=None, final_pkg=None,
         evidence=None):
    return {"schema_id": schema["schema_id"],
            "rule": schema["canonical_signed_rule"],
            "state": state, "refusals": refusals,
            "mechanical": gates,
            "guard_previews": pv.get("previews") if pv.get("ok") else None,
            "guard_preview_error": None if pv.get("ok") else pv.get("detail"),
            "judge": _scrub(judge), "group_verdict": judge_raw_verdict,
            "guards": guards, "falsifier": falsifier,
            "evidence": evidence,
            "final_rule": FP.formula(final_pkg) if final_pkg else
                          schema["canonical_signed_rule"],
            "final_package": final_pkg,
            "raw": raws}


def _atoms(view, table, schema, by_alias, aliases):
    rows = CX.menu(table, view["stage2"], schema["producer_occurrences"][0],
                   schema["consumer_occurrences"][0])
    want = set(by_alias.get(a) for a in aliases)
    return [m["atom"] for m in rows if m["occurrence_id"] in want]


def _compile(view, table, schema, by_alias, aliases):
    ids = [by_alias[a] for a in aliases if a in by_alias]
    w = schema["construction_witness"]
    try:
        base, rec = AR.compile_from_base(
            w["producer"], w["consumer"], ids, table,
            target_mode=w.get("target_mode"), require_range_restriction=True)
    except AR.RuleError as e:
        return {"compiled": False, "why": str(e)}
    pkg = BW.to_defeasible_shape(base)
    atoms = _atoms(view, table, schema, by_alias, aliases)
    return {"compiled": True, "package": pkg, "printed": FP.formula(pkg),
            "atoms": [FP.formula(a) for a in atoms],
            "occurrences": ids,
            "mechanical": AK.mechanical_gates(pkg,
                                              base_pkg=schema["stage2_rule"],
                                              condition_atoms=atoms)}


# ---------------------------------------------------------------- WP5 worlds

def promoted_world(view, row, hyp_id, gk, weight, inert):
    """One promoted rule, alone, in its own gk world.

    The formula run is the one the falsifier passed, byte for byte.  The weight
    is applied after the proof is found, never inside search.  An answer that
    changes without citing the bridge gets the inert control and is not
    credited.
    """
    pkg = row["final_package"] or row["stage2_rule"]
    clauses, brec = BW.compile_bridge(
        view["case_id"], hyp_id, pkg, view["stage1"], view["stage2"],
        view["configuration"], bridge_evidence=BW.RUNTIME_EVIDENCE,
        base_clauses=view["final_clauses"], hypothesis_id=hyp_id)
    out = {"hypothesis_id": hyp_id, "schema_id": row["schema_id"],
           "promoted_rule": FP.formula(pkg),
           "clauses": clauses, "has_block": brec["has_block"],
           "clause_provenance": brec["clause_provenance"],
           "evidence": row.get("evidence"),
           "guards": (row.get("guards") or {}).get("guards") or [],
           "guard_occurrences": (row.get("guards") or {}).get("occurrences")
           or []}
    res = gk(list(view["final_clauses"]) + clauses, "promoted_%s" % hyp_id)
    if res.get("error"):
        out["state"] = "gk_error"
        out["gk"] = {"error": res["error"]}
        return out
    scored = DS.from_raw(res.get("raw") or "", brec["clause_provenance"],
                         {hyp_id: weight}, weight)
    cited = bool(scored["bridge_hypotheses_used"])
    changed = res.get("answer") != view["stored_answer"]
    out["gk"] = {"answer": res.get("answer"),
                 "gk_confidence": res.get("confidence"),
                 "argv": res.get("argv"),
                 "answer_changed_from_baseline": changed}
    out["raw_proof"] = res.get("raw")
    out["bridge_cited"] = cited
    out["dynamic"] = {k: v for k, v in scored.items() if k != "raw"}
    out["rendered"] = DS.render(scored, kind="reviewed")
    if cited and scored["answer"] is not None:
        out["state"] = "semantic_promoted"
    elif changed and not cited:
        ctl = gk(list(view["final_clauses"]) + inert(len(clauses)),
                 "inert_promoted_%s" % hyp_id)
        out["inert_control"] = {k: v for k, v in ctl.items() if k != "raw"}
        out["state"] = "semantic_promoted_no_answer"
        out["why"] = ("the answer changed without citing the bridge; a "
                      "search-order effect, not credited")
    else:
        out["state"] = "semantic_promoted_no_answer"
        out["why"] = "no proof used the promoted rule"
    return out


# ---------------------------------------------------------------- invariants

PROMOTED_STATES = ("semantic_promoted", "semantic_promoted_no_answer")


def assert_invariants(rec):
    """WP6.  Every one of these has been violated by some earlier version.

    `semantic_promoted_no_answer` counts as promoted: the rule was admitted and
    its world ran; that no proof used it is a fact about usefulness, and the
    plan is explicit that it is not a semantic rejection.
    """
    promoted = set(w["schema_id"]
                   for w in rec.get("semantic_promoted_worlds", []))
    reviewed = {r["schema_id"]: r for g in rec.get("semantic_groups", [])
                for r in g["rows"]}
    refused = set(sid for sid, r in reviewed.items()
                  if r["state"] not in PROMOTED_STATES)
    both = promoted & refused
    if both:
        raise RuntimeAdmissionError("promoted and refused: %s" % sorted(both))
    for g in rec.get("semantic_groups", []):
        if len(g["members"]) > 1:
            got = [m for m in g["members"]
                   if reviewed.get(m, {}).get("state") in PROMOTED_STATES]
            if len(got) > 1:
                raise RuntimeAdmissionError(
                    "both sides of an opposite-head group promoted: %s" % got)
    for w in rec.get("semantic_promoted_worlds", []):
        r = reviewed.get(w["schema_id"])
        if r and r["final_rule"] != w["promoted_rule"]:
            raise RuntimeAdmissionError(
                "the promoted formula is not the falsified one: %s"
                % w["schema_id"])
        for atom in ((r or {}).get("guards") or {}).get("atoms") or []:
            head = (atom or "").split("(")[0]
            if head and head not in w["promoted_rule"]:
                raise RuntimeAdmissionError(
                    "a selected guard is missing from the compiled rule: %s"
                    % atom)
    for w in rec.get("probe_worlds", []):
        if w.get("state") == "probe_proof" and not w.get("rendered"):
            raise RuntimeAdmissionError("a found probe proof lost its answer")
    return True
