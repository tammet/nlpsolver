"""Broad isolated probing, then semantic refinement of what actually proved.

The previous pipeline let one LLM call decide which two of a hundred candidates
were allowed to exist, and the audit found the reviewed interface twice
enumerated, twice displayed and twice not chosen.  So the order changes:

    schemas -> the model PRIORITISES (it does not gate)
            -> a bounded diverse pool of at most 24
            -> each schema alone in its own gk world, full confidence
            -> keep every bridge-cited proof, however small its weight
            -> the model REVIEWS only what proved
            -> code compiles the reviewed, guarded, scoped rule
            -> rerun each reviewed rule in a fresh world

A probe is not knowledge.  It is a question put to the prover: *if this rule
were true, would anything follow?*  Its weight (0.01) is reporting metadata
applied after search, never a clause confidence, and it must never turn a proof
into `Unknown.`

Transport-free, like `dynamic_pipeline`: the LLM and the prover arrive as
callables, so every path is testable with no calls.
"""

import collections
import copy
import hashlib
import json

import alignment_candidate_filter as CF
import alignment_candidates as AC
import alignment_compare as CMP
import alignment_context as CX
import alignment_occurrences as AO
import alignment_protocol as P
import alignment_rule as AR
import alignment_selector as S
import bridge_world as BW
import dynamic_score as DS
import formula_print as FP

STATES = (
    "preflight", "baseline_reproduced", "baseline_refused",
    "baseline_answered", "baseline_unresolved",
    "schemas_built", "no_schema",
    "selector_completed", "selector_empty", "selector_failed",
    "pool_built",
    "probes_run", "probe_active", "no_probe_active",
    "semantic_completed", "semantic_failed",
    "refined_compiled", "refined_refused", "refined_world_run",
    "model_admitted_dynamic_answer", "model_admitted_bridge_unused",
) + (
    # the optional semantic_v3 mode's own names.  New rather than reused: the
    # old ones described a different decision, and sharing them would make two
    # runs look comparable when they are not.
    "semantic_mechanical_refused", "semantic_judge_refused",
    "semantic_guard_refused", "semantic_falsifier_refused",
    "semantic_opposite_conflict", "semantic_promoted",
    "semantic_promoted_no_answer", "semantic_prompt_error",
)

MAX_SELECTED_SCHEMAS = 12
MAX_PROBE_SCHEMAS_PER_CASE = 24
MAX_REFINEMENTS_PER_CASE = 6
SCHEMA_DISPLAY_CAP = 60
MAX_SELECTOR_CHUNKS = 2

PROBE_WEIGHT = 0.01
REVIEWED_WEIGHT = 0.1

UNRESOLVED_ANSWERS = ("Unknown.", None, "")

ACTIONS = ("bridge", "conditional_bridge", "ordinary", "no_bridge", "uncertain")
SCOPES = ("local", "context", "general", "unclear")
ADMITTING = ("bridge", "conditional_bridge")

GOLD_KEYS = ("gold_replacement_packages", "critic_verdict", "labels",
             "expected_answer", "accepted_llmpipe_answers", "reviewed_action",
             "mechanism", "allowed_changed_unit_ids", "study_class",
             "mechanism_family", "correctness", "expected")


class ProbeError(Exception):
    pass


class GoldLeak(ProbeError):
    pass


# ---------------------------------------------------------------- gold gate

def assert_no_gold(obj, where="runtime"):
    blob = json.dumps(obj, sort_keys=True, default=str)
    hit = [k for k in GOLD_KEYS if ('"%s"' % k) in blob]
    if hit:
        raise GoldLeak("%s carries reviewed key(s) %s" % (where, sorted(hit)))
    return True


def runtime_view(case_id, stored, configuration, dataset=None):
    """The only door in.  Allowlisted, and checked."""
    view = {"case_id": case_id, "dataset": dataset,
            "input_text": copy.deepcopy(stored["input_text"]),
            "stage1": copy.deepcopy(stored["stage1"]),
            "stage2": copy.deepcopy(stored["stage2"]),
            "configuration": configuration,
            "final_clauses": copy.deepcopy(stored["final_clauses"]),
            "stored_answer": stored.get("answer"),
            "stored_gk_command": stored.get("gk_command")}
    assert_no_gold(view, "runtime_view(%s)" % case_id)
    return view


def case_hash(view):
    h = hashlib.sha256()
    for part in (view["case_id"], json.dumps(view["stage2"], sort_keys=True),
                 json.dumps(view["final_clauses"], sort_keys=True)):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


# ---------------------------------------------------------------- pool

def _consumer_key(schema, table):
    """The signed consumer literal, canonically — the diversity axis."""
    occ = table["by_id"][schema["consumer_occurrences"][0]]
    return json.dumps(CF.occurrence_sig(occ))


def _producer_family(schema, table):
    occ = table["by_id"][schema["producer_occurrences"][0]]
    s = CF.occurrence_sig(occ)
    return json.dumps(s[:3]) if s else "?"


def build_pool(schemas, selected_ids, table,
               cap=MAX_PROBE_SCHEMAS_PER_CASE):
    """Selector picks first, then a round-robin over consumer groups.

    The supplement is a DIVERSITY mechanism, not a score: it stops one question
    component or one predicate family from eating the whole pool, and it uses
    the stable enumeration order inside each group so it introduces no ranking.
    """
    by_id = {s["schema_id"]: s for s in schemas}
    pool, why = [], {}
    for sid in selected_ids:
        if sid in by_id and sid not in pool and len(pool) < cap:
            pool.append(sid)
            why[sid] = "selector"
    groups = collections.OrderedDict()
    for s in schemas:
        if s["schema_id"] in pool:
            continue
        groups.setdefault(_consumer_key(s, table), []).append(s)
    # round 1: one per consumer group, preferring an unseen producer family
    seen_families = collections.defaultdict(set)
    round_no = 0
    while len(pool) < cap:
        added = False
        round_no += 1
        for key, members in groups.items():
            if len(pool) >= cap:
                break
            pick = None
            for s in members:
                if s["schema_id"] in pool:
                    continue
                fam = _producer_family(s, table)
                if fam not in seen_families[key]:
                    pick = s
                    break
            if pick is None:
                for s in members:
                    if s["schema_id"] not in pool:
                        pick = s
                        break
            if pick is None:
                continue
            pool.append(pick["schema_id"])
            seen_families[key].add(_producer_family(pick, table))
            why[pick["schema_id"]] = "diverse supplement, round %d" % round_no
            added = True
        if not added:
            break
    unprobed = [s["schema_id"] for s in schemas if s["schema_id"] not in pool]
    return pool, why, unprobed


# ---------------------------------------------------------------- prompts

def _instr(name):
    import os
    with open(os.path.join(P.PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_hash(name):
    return hashlib.sha256(_instr(name).encode()).hexdigest()


def _sentences_block(view):
    lines, n = [], 0
    for sent in view["stage1"] or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            n += 1
            lines.append("  %d. [%s] %s" % (n, u.get("unit_id"), u.get("text")))
    return "\n".join(lines)


def _schema_block(s, table):
    by_id = table["by_id"]
    p = by_id[s["producer_occurrences"][0]]
    c = by_id[s["consumer_occurrences"][0]]
    lines = ["%s: %s" % (s["schema_id"], s["canonical_signed_rule"])]
    for ev in s["source_evidence"][:3]:
        lines.append("      from %s %s%s   ->   %s %s%s"
                     % (ev["producer_unit"], ev["producer_position"],
                        "  <- %r" % ev["producer_phrase"]
                        if ev["producer_phrase"] else "",
                        ev["consumer_unit"], ev["consumer_position"],
                        "  <- %r" % ev["consumer_phrase"]
                        if ev["consumer_phrase"] else ""))
    if len(s["source_evidence"]) > 3:
        lines.append("      (and %d more place(s) in the problem produce the "
                     "same rule)" % (len(s["source_evidence"]) - 3))
    lines.append("      %s" % S._pair_note(p, c, {"features": s.get("features")}))
    return "\n".join(lines)


def schema_chunks(schemas, cap=SCHEMA_DISPLAY_CAP,
                  max_chunks=MAX_SELECTOR_CHUNKS):
    chunks = [schemas[i:i + cap] for i in range(0, len(schemas), cap)][:max_chunks]
    shown = sum(len(c) for c in chunks)
    return chunks, len(schemas) - shown


def build_selector_prompt(view, chunk, index, total, table, already=()):
    parts = ["ENGLISH PROBLEM:\n%s" % view["input_text"],
             "SENTENCES:\n%s" % _sentences_block(view)]
    if total > 1:
        note = ("This is list %d of %d.  Names are stable across the lists."
                % (index + 1, total))
        if already:
            note += ("  From the earlier list you chose %s; that is recorded so "
                     "you do not repeat a name, and for no other reason."
                     % ", ".join(already))
        parts.append("ABOUT THIS LIST:\n%s" % note)
    parts.append("CANDIDATE RULES:\n%s"
                 % "\n\n".join(_schema_block(s, table) for s in chunk))
    prompt = _instr("selector_candidates_v3") + "\n\n" + "\n\n".join(parts)
    P.assert_no_leak(prompt)
    assert_no_gold(prompt, "selector prompt")
    return prompt


def build_refine_prompt(view, actives, table):
    """`actives` is [(schema, [(alias, menu_row)])] for proof-active schemas."""
    blocks = []
    for s, menu in actives:
        lines = ["SCHEMA %s\n  the rule that was added:\n    %s"
                 % (s["schema_id"], s["canonical_signed_rule"])]
        ev = s["source_evidence"][0]
        lines.append("  left side:  %s %s%s"
                     % (ev["producer_unit"], ev["producer_position"],
                        "  <- %r" % ev["producer_phrase"]
                        if ev["producer_phrase"] else ""))
        lines.append("  right side: %s %s%s"
                     % (ev["consumer_unit"], ev["consumer_position"],
                        "  <- %r" % ev["consumer_phrase"]
                        if ev["consumer_phrase"] else ""))
        if menu:
            lines.append("  conditions available:")
            for alias, m in menu:
                lines.append("    %s: %-44s [%s]%s"
                             % (alias, FP.formula(m["atom"]), m["why_offered"],
                                "  <- %r" % m["source_quote"]
                                if m.get("source_quote") else ""))
        else:
            lines.append("  conditions available: none")
        blocks.append("\n".join(lines))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % view["input_text"],
        "SENTENCES:\n%s" % _sentences_block(view),
        "RULES THE PROVER USED:\n%s" % "\n\n".join(blocks)])
    prompt = _instr("semantic_refine_v2") + "\n\n" + body
    P.assert_no_leak(prompt)
    assert_no_gold(prompt, "refine prompt")
    return prompt


# ---------------------------------------------------------------- parsing

def _first_word(s):
    t = (s or "").strip().lower()
    return t.split(" ")[0].strip(".,;:!?()[]\"'*_") if t else ""


def parse_refine_response(text, known_schema_ids, known_condition_ids):
    """SCHEMA / ACTION / CONDITIONS / SCOPE strictly; the rest is prose."""
    blocks, cur = [], None
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_ ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().strip("*#_-• \t").lower()
        v = v.strip().strip("*_ ").strip()
        if k == "schema":
            cur = {"schema": (v.split() or [""])[0].strip(".,").upper(),
                   "action": "uncertain", "conditions_raw": "",
                   "conditions": [], "conditions_unavailable": False,
                   "scope": "unclear", "counterexample": "", "why": ""}
            blocks.append(cur)
        elif cur is None:
            continue
        elif k == "action":
            w = _first_word(v)
            cur["action"] = w if w in ACTIONS else "uncertain"
        elif k == "conditions":
            cur["conditions_raw"] = v
            low = v.lower()
            if "unavailable" in low:
                cur["conditions_unavailable"] = True
            elif low.strip(". ") not in ("none", "-", ""):
                import re
                cur["conditions"] = [a.upper() for a
                                     in re.findall(r"[A-Za-z]+\d+", v)]
        elif k == "scope":
            w = _first_word(v)
            cur["scope"] = w if w in SCOPES else "unclear"
        elif k.startswith("counterexample"):
            cur["counterexample"] = v
        elif k == "why":
            cur["why"] = v
    out, unknown_schemas, unknown_conditions = {}, [], []
    for b in blocks:
        sid = b["schema"]
        if sid not in known_schema_ids:
            unknown_schemas.append(b["schema"])
            continue
        bad = [a for a in b["conditions"] if a not in known_condition_ids.get(sid, {})]
        if bad:
            unknown_conditions.append({"schema": sid, "aliases": bad})
            b = dict(b, conditions=[a for a in b["conditions"]
                                    if a in known_condition_ids.get(sid, {})],
                     dropped_condition_aliases=bad)
        if sid not in out:
            out[sid] = b
    return {"decisions": out, "unknown_schema_ids": unknown_schemas,
            "unknown_condition_aliases": unknown_conditions,
            "parsed": bool(out), "blocks_seen": len(blocks)}


def admission(decision):
    """-> (admit, refusal_reason).  Exactly the plan's table, no inference."""
    a = decision["action"]
    if a == "bridge":
        return True, None
    if a == "conditional_bridge":
        if decision.get("conditions_unavailable"):
            return False, "condition_not_representable"
        if not decision.get("conditions"):
            return False, "condition_required_but_not_selected"
        return True, None
    if a == "ordinary":
        return False, "ordinary_candidate_filter_miss"
    if a == "no_bridge":
        return False, "rejected_hypothesis"
    return False, "uncertain"


# ---------------------------------------------------------------- machine

class Trace(object):
    def __init__(self):
        self.states = []

    def enter(self, state, **d):
        if state not in STATES:
            raise ProbeError("unknown state %r" % state)
        self.states.append(dict(d, state=state))
        return state


def witness(schema):
    """The construction witness to replay.

    The schema's first occurrence pair used to be re-derived here, and the mode
    with it, so a schema built as `contradict_question` was rebuilt as its
    complement.  The witness is what the displayed formula was compiled from.
    """
    w = schema.get("construction_witness")
    if w:
        return w
    return {"producer": schema["producer_occurrences"][0],
            "consumer": schema["consumer_occurrences"][0],
            "target_mode": schema.get("target_mode"),
            "compiled_base_formula": schema.get("canonical_signed_rule")}


def _same_rule(pkg, schema):
    """Is this package the schema's own rule, up to `normally` placement?

    `normally(A -> B)` and `A -> normally(B)` say the same thing and are the
    only difference the bridge shape introduces; everything else — head, sign,
    argument mapping, conditions — must be identical.
    """
    base = schema.get("stage2_rule")
    if base is None:
        return True
    try:
        return BW.to_defeasible_shape(base) == pkg
    except BW.BridgeError:
        return False


def _compile_probe(view, schema, hyp_id, table):
    """The minimal probe bridge: signed base rule, no conditions, defeasible."""
    w = witness(schema)
    pkg, prec = BW.bridge_package(w["producer"], w["consumer"], [], table,
                                  target_mode=w.get("target_mode"))
    if not _same_rule(pkg, schema):
        raise BW.BridgeError(
            "probe formula is not its schema's: probe %s, schema %s"
            % (FP.formula(pkg), schema.get("canonical_signed_rule")))
    clauses, brec = BW.compile_bridge(
        view["case_id"], hyp_id, pkg, view["stage1"], view["stage2"],
        view["configuration"], bridge_evidence=BW.RUNTIME_EVIDENCE,
        base_clauses=view["final_clauses"], hypothesis_id=hyp_id)
    return pkg, clauses, brec


def _compile_refined(view, schema, hyp_id, table, condition_ids, scope):
    """The refined bridge: the same base rule plus the chosen conditions.

    Two gates the probe tier does not have.  The target mode comes from the
    witness, so refinement cannot change the head; and range restriction is
    mandatory, so a rule whose conclusion quantifies something no antecedent
    binds is refused here rather than admitted, weighted and sent to gk.
    """
    w = witness(schema)
    base, prec = AR.compile_from_base(w["producer"], w["consumer"],
                                      condition_ids, table, scope=scope,
                                      target_mode=w.get("target_mode"),
                                      require_range_restriction=True)
    pkg = BW.to_defeasible_shape(base)
    _check_base_preserved(pkg, schema)
    clauses, brec = BW.compile_bridge(
        view["case_id"], hyp_id, pkg, view["stage1"], view["stage2"],
        view["configuration"], bridge_evidence=BW.RUNTIME_EVIDENCE,
        base_clauses=view["final_clauses"], hypothesis_id=hyp_id)
    return pkg, clauses, brec, prec


def _check_base_preserved(pkg, schema):
    """Conditions may only be added.  The base rule must survive intact.

    Adding conditions may change the antecedent set and the quantifiers.  It may
    not change the conclusion, its sign, the argument mapping or the target
    mode — and the schema's own antecedent must still be there.
    """
    base = schema.get("stage2_rule")
    if not base:
        return
    try:
        a = CMP.parse_rule_package(pkg)
        b = CMP.parse_rule_package(base)
    except CMP.ShapeError:
        return
    cmp_res = CMP.compare(pkg, base, mode="exact")
    if not cmp_res.get("comparable") or cmp_res["direction"] != "forward":
        raise BW.BridgeError(
            "refinement changed the base rule: conclusion %s, was %s"
            % (CMP._show(a["consequent"]), CMP._show(b["consequent"])))
    if cmp_res["missing_antecedents"]:
        raise BW.BridgeError("refinement dropped the base antecedent %s"
                             % "; ".join(cmp_res["missing_antecedents"]))


def _proofs(raw):
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return None
    out = []
    for a in d.get("answers") or []:
        for k in ("positive proof", "negative proof", "proof"):
            if a.get(k):
                out.append(a[k])
    return out or None


def _inert(n):
    return [{"@name": "probe_inert_%d" % i,
             "@logic": [["-$probe_inert", "$probe_a_%d" % i],
                        ["$probe_inert", "$probe_b_%d" % i]]}
            for i in range(1, n + 1)]


def run_case(view, respond, gk, weights=None, admission_mode="legacy"):
    """The whole runtime for one case.  No gold anywhere.

    `admission_mode` selects the semantic stage: `legacy` is the historical
    `semantic_refine_v2` path and the default, so every existing runner and test
    behaves exactly as before; `semantic_v3` runs the mechanical gates, meaning
    judge, guard selection and falsifier of `admission_runtime`.  The experiment
    is reversible by passing the other mode — no prompt or record is edited.
    """
    import admission_runtime as ARN
    if admission_mode not in ARN.MODES:
        raise ProbeError("unknown admission mode %r" % admission_mode)
    w_probe = (weights or {}).get("probe", PROBE_WEIGHT)
    w_reviewed = (weights or {}).get("reviewed", REVIEWED_WEIGHT)
    tr = Trace()
    rec = {"case_id": view["case_id"], "case_hash": case_hash(view),
           "configuration": view["configuration"],
           "conservative_result": None, "probe_worlds": [],
           "reviewed_dynamic_worlds": [], "unresolved_diagnostics": [],
           "trace": None}
    tr.enter("preflight", stored_answer=view["stored_answer"])

    base = gk(view["final_clauses"], "baseline")
    if base.get("answer") != view["stored_answer"] or \
            base.get("command_matches_stored") is False:
        tr.enter("baseline_refused",
                 why="answer %r vs stored %r; command matches %s"
                     % (base.get("answer"), view["stored_answer"],
                        base.get("command_matches_stored")))
        rec["conservative_result"] = {"answer": base.get("answer"),
                                      "reproduced": False}
        rec["trace"] = tr.states
        return rec
    tr.enter("baseline_reproduced")
    rec["conservative_result"] = {"answer": base.get("answer"),
                                  "gk_confidence": base.get("confidence"),
                                  "reproduced": True,
                                  "gk_command": base.get("argv")}
    if base.get("answer") not in UNRESOLVED_ANSWERS:
        tr.enter("baseline_answered", answer=base.get("answer"))
        rec["front_door_stopped"] = True
        rec["trace"] = tr.states
        return rec
    tr.enter("baseline_unresolved")
    rec["front_door_stopped"] = False

    gen = AC.generate(view["stage1"], view["stage2"], view["configuration"])
    table = gen["table"]
    built = CF.build(gen, view["stage2"], table)
    schemas = built["schemas"]
    rec["enumeration"] = dict(built["counts"], rule_edges=built["rule_edges"])
    rec["routed_out"] = built["routed"]
    rec["schemas"] = [{k: v for k, v in s.items() if k != "stage2_rule"}
                      for s in schemas]
    if not schemas:
        tr.enter("no_schema", why="every surviving pair was ordinary or encoded")
        rec["unresolved_diagnostics"].append("no candidate abstraction remained")
        rec["trace"] = tr.states
        return rec
    tr.enter("schemas_built", unique=len(schemas))

    chunks, unshown = schema_chunks(schemas)
    rec["selector"] = {"chunks": len(chunks), "shown": sum(len(c) for c in chunks),
                       "never_shown": unshown, "calls": []}
    selected = []
    for i, chunk in enumerate(chunks):
        prompt = build_selector_prompt(view, chunk, i, len(chunks), table,
                                       already=list(selected))
        text, log, note = respond("selector", prompt,
                                  {"case": view["case_id"], "chunk": i})
        sel = S.parse_selection(text or "", "candidates")
        valid = set(s["schema_id"] for s in chunk)
        ids = [x.upper() for x in sel["selected"]]
        # the selector's own cap is 5; this experiment keeps up to 12
        extra = _ids_from_line(text)
        for x in extra:
            if x not in ids:
                ids.append(x)
        kept = [x for x in ids if x in valid]
        rec["selector"]["calls"].append(
            {"chunk": i, "raw": text, "parsed": bool(kept), "selected": ids,
             "kept": kept, "call_log": log, "note": note})
        for x in kept:
            if x not in selected and len(selected) < MAX_SELECTED_SCHEMAS:
                selected.append(x)
    rec["selector"]["merged"] = selected
    if selected:
        tr.enter("selector_completed", chosen=selected)
    else:
        tr.enter("selector_empty",
                 why="no usable schema id; the pool is built from diversity alone")

    pool, why, unprobed = build_pool(schemas, selected, table)
    rec["pool"] = {"schema_ids": pool, "reason": why,
                   "not_probed": unprobed,
                   "cap": MAX_PROBE_SCHEMAS_PER_CASE,
                   "from_selector": [s for s in pool if why.get(s) == "selector"],
                   "from_supplement": [s for s in pool
                                       if why.get(s) != "selector"]}
    tr.enter("pool_built", size=len(pool), unprobed=len(unprobed))

    if admission_mode == ARN.SEMANTIC_V3:
        # The plan puts mechanical admission checks on EVERY pooled schema, not
        # only on the ones that reach semantic review.  A schema refused here is
        # still probed — a probe asks what would follow, and answers nothing
        # about belief — but it can never be promoted, and the refusal is
        # recorded whether or not the selector ever prioritised it.
        rec["pool_mechanical"] = ARN.pool_gates(schemas, pool)

    by_id = {s["schema_id"]: s for s in schemas}
    active = []
    for n, sid in enumerate(pool, start=1):
        s = by_id[sid]
        hyp = "P%d" % n
        w = {"hypothesis_id": hyp, "schema_id": sid,
             "abstraction_status": "unverified_probe",
             "hypothesis_weight": w_probe,
             "canonical_signed_rule": s["canonical_signed_rule"],
             "pool_reason": why.get(sid)}
        try:
            pkg, clauses, brec = _compile_probe(view, s, hyp, table)
        except (AR.RuleError, BW.BridgeError) as e:
            w["state"] = "compile_refused"
            w["error"] = str(e)
            rec["probe_worlds"].append(w)
            continue
        w["stage2_rule"] = pkg
        w["clauses"] = clauses
        w["has_block"] = brec["has_block"]
        w["clause_provenance"] = brec["clause_provenance"]
        res = gk(list(view["final_clauses"]) + clauses, "probe_%s" % hyp)
        if res.get("error"):
            w["state"] = "gk_error"
            w["gk"] = {"error": res["error"]}
            rec["probe_worlds"].append(w)
            continue
        scored = DS.from_raw(res.get("raw") or "", brec["clause_provenance"],
                             {hyp: w_probe}, w_probe)
        cited = bool(scored["bridge_hypotheses_used"])
        changed = res.get("answer") != view["stored_answer"]
        w["gk"] = {"answer": res.get("answer"),
                   "gk_confidence": res.get("confidence"),
                   "argv": res.get("argv"), "seconds": res.get("seconds"),
                   "answer_changed_from_baseline": changed}
        w["raw_proof"] = res.get("raw")
        w["bridge_cited"] = cited
        w["dynamic"] = {k: v for k, v in scored.items() if k != "raw"}
        w["rendered"] = DS.render(scored, kind="unverified_probe")
        if cited and scored["answer"] is not None:
            w["state"] = "probe_proof"
            active.append(sid)
        elif cited:
            w["state"] = "bridge_cited_without_answer"
        elif changed:
            ctl = gk(list(view["final_clauses"]) + _inert(len(clauses)),
                     "inert_%s" % hyp)
            w["inert_control"] = {k: v for k, v in ctl.items() if k != "raw"}
            w["state"] = "search_order_effect"
        else:
            w["state"] = "no_proof"
        rec["probe_worlds"].append(w)
    tr.enter("probes_run", probed=len(rec["probe_worlds"]), active=len(active))
    rec["proof_active_schema_ids"] = active

    if admission_mode == ARN.SEMANTIC_V3:
        # Semantic review is scheduled by SELECTOR priority, not by what proved:
        # a rule the English licenses is licensed whether or not it closes this
        # case, and the plan requires its decision to be recorded either way.
        return _semantic_v3(view, respond, gk, rec, tr, table, by_id, schemas,
                            selected, pool, active, w_reviewed)

    if not active:
        tr.enter("no_probe_active", why="no probe produced a bridge-cited proof")
        rec["unresolved_diagnostics"].append("no probe proved anything")
        rec["trace"] = tr.states
        return rec
    tr.enter("probe_active", schemas=active)

    # refine, selector-prioritised actives first, then stable pool order
    ordered = [s for s in selected if s in active] + \
              [s for s in active if s not in selected]
    to_refine = ordered[:MAX_REFINEMENTS_PER_CASE]
    rec["refinement"] = {"reviewed": to_refine,
                         "active_not_reviewed": ordered[MAX_REFINEMENTS_PER_CASE:]}
    menus, alias_map = {}, {}
    actives_for_prompt = []
    for sid in to_refine:
        s = by_id[sid]
        rows = CX.menu(table, view["stage2"], s["producer_occurrences"][0],
                       s["consumer_occurrences"][0])
        menu = [("G%d" % (i + 1), m) for i, m in enumerate(rows)]
        menus[sid] = menu
        alias_map[sid] = {a: m["occurrence_id"] for a, m in menu}
        actives_for_prompt.append((s, menu))
    rec["refinement"]["conditions_offered"] = {
        sid: [{"alias": a, "occurrence": m["occurrence_id"],
               "atom": FP.formula(m["atom"]), "why_offered": m["why_offered"]}
              for a, m in menus[sid]] for sid in to_refine}

    prompt = build_refine_prompt(view, actives_for_prompt, table)
    text, log, note = respond("refine", prompt, {"case": view["case_id"]})
    parsed = parse_refine_response(text or "", set(to_refine), alias_map)
    rec["refinement"].update({"raw": text, "call_log": log, "note": note,
                              "decisions": parsed["decisions"],
                              "unknown_schema_ids": parsed["unknown_schema_ids"],
                              "unknown_condition_aliases":
                                  parsed["unknown_condition_aliases"]})
    if not parsed["parsed"]:
        tr.enter("semantic_failed", why="no readable SCHEMA block")
        rec["unresolved_diagnostics"].append("semantic refinement unreadable")
        rec["trace"] = tr.states
        return rec
    tr.enter("semantic_completed", decided=sorted(parsed["decisions"]))

    for n, sid in enumerate(to_refine, start=1):
        d = parsed["decisions"].get(sid)
        s = by_id[sid]
        out = {"hypothesis_id": "R%d" % n, "schema_id": sid,
               "abstraction_status": "model_admitted_bridge",
               "hypothesis_weight": w_reviewed,
               "decision": d, "canonical_signed_rule": s["canonical_signed_rule"]}
        if d is None:
            out["state"] = "not_decided"
            out["refusal"] = "the response carried no block for this schema"
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        admit, refusal = admission(d)
        out["admitted"] = admit
        if not admit:
            out["state"] = "not_admitted"
            out["refusal"] = refusal
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        cond_ids = [alias_map[sid][a] for a in d["conditions"]]
        try:
            pkg, clauses, brec, prec = _compile_refined(
                view, s, out["hypothesis_id"], table, cond_ids, d["scope"])
        except AR.ScopeError as e:
            tr.enter("refined_refused", schema=sid, why=str(e))
            out["state"] = "scope_refused"
            out["refusal"] = str(e)
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        except AR.RangeError as e:
            # mechanical, not a judgement: the conclusion quantifies something
            # no antecedent binds, so the rule asserts about everything.  gk is
            # not invoked and no weight is recorded.
            tr.enter("refined_refused", schema=sid, why=str(e))
            out["state"] = "unbound_conclusion_variable"
            out["refusal"] = str(e)
            out["range_restriction_refused"] = True
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        except (AR.RuleError, BW.BridgeError) as e:
            tr.enter("refined_refused", schema=sid, why=str(e))
            out["state"] = "compile_refused"
            out["refusal"] = str(e)
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        tr.enter("refined_compiled", schema=sid)
        out.update({"conditions": d["conditions"],
                    "condition_occurrences": cond_ids,
                    "scope": d["scope"], "stage2_rule": pkg,
                    "printed": FP.formula(pkg), "clauses": clauses,
                    "has_block": brec["has_block"],
                    "clause_provenance": brec["clause_provenance"],
                    "grounded_positions": prec.get("grounded_positions")})
        res = gk(list(view["final_clauses"]) + clauses,
                 "reviewed_%s" % out["hypothesis_id"])
        if res.get("error"):
            out["state"] = "gk_error"
            out["gk"] = {"error": res["error"]}
            rec["reviewed_dynamic_worlds"].append(out)
            continue
        tr.enter("refined_world_run", schema=sid)
        scored = DS.from_raw(res.get("raw") or "", brec["clause_provenance"],
                             {out["hypothesis_id"]: w_reviewed}, w_reviewed)
        cited = bool(scored["bridge_hypotheses_used"])
        out["gk"] = {"answer": res.get("answer"),
                     "gk_confidence": res.get("confidence"),
                     "argv": res.get("argv"),
                     "answer_changed_from_baseline":
                         res.get("answer") != view["stored_answer"]}
        out["raw_proof"] = res.get("raw")
        out["bridge_cited"] = cited
        out["dynamic"] = {k: v for k, v in scored.items() if k != "raw"}
        out["rendered"] = DS.render(scored)
        probe = next((w for w in rec["probe_worlds"]
                      if w["schema_id"] == sid), {})
        out["vs_probe"] = {
            "probe_answer": (probe.get("gk") or {}).get("answer"),
            "refined_answer": res.get("answer"),
            "conditions_changed_the_proof":
                (probe.get("gk") or {}).get("answer") != res.get("answer")}
        if cited and scored["answer"] is not None:
            tr.enter("model_admitted_dynamic_answer", schema=sid)
            out["state"] = "model_admitted_dynamic_answer"
        else:
            tr.enter("model_admitted_bridge_unused", schema=sid)
            out["state"] = "model_admitted_bridge_unused"
        rec["reviewed_dynamic_worlds"].append(out)

    # a probe whose hypothesis the review rejected keeps its proof, marked
    rejected = set(sid for sid in to_refine
                   if parsed["decisions"].get(sid)
                   and not admission(parsed["decisions"][sid])[0])
    for w in rec["probe_worlds"]:
        if w.get("state") == "probe_proof" and w["schema_id"] in rejected:
            w["semantic_status"] = "proof_found_under_rejected_hypothesis"
        elif w.get("state") == "probe_proof":
            w["semantic_status"] = ("reviewed"
                                    if w["schema_id"] in to_refine
                                    else "active_but_not_reviewed")
    rec["trace"] = tr.states
    return rec


def _semantic_v3(view, respond, gk, rec, tr, table, by_id, schemas, selected,
                 pool, active, w_reviewed):
    """The optional semantic-admission stage.  Legacy is untouched.

    Reviews GROUPS, not individual schemas: a selector-chosen rule and its
    unchosen opposite sibling go to one judge call, because deciding which of
    two contradictory rules the English licenses is one question, not two.

    Proof activity enters here once, to fill a leftover review slot after the
    selector's own priorities.  It reaches scheduling metadata and nothing else.
    """
    import admission_runtime as ARN
    rec["semantic_groups"] = []
    rec["semantic_promoted_worlds"] = []
    rec["admission_mode"] = ARN.SEMANTIC_V3

    refused_by_gates = ARN.ineligible(rec)
    groups, sib_groups, seen = ARN.schedule(schemas, selected, pool, active,
                                            refused_by_gates)
    rec["semantic_scheduling"] = {
        "selector_priority_groups": [g["members"] for g in groups],
        "opposite_head_groups": sib_groups,
        "mechanically_ineligible_pooled": sorted(refused_by_gates)}

    # A caller may share the global call budget across cases, so that one case
    # with many groups cannot starve the later ones.  Transport-free: the
    # predicate rides on the responder, and its absence means "no limit".
    may_review = getattr(respond, "may_review", None)
    skipped = []
    calls = 0
    for g in groups + ARN.supplement(schemas, active, seen, sib_groups, True):
        if may_review is not None and not may_review():
            skipped.append({"members": g["members"], "reason": g["reason"],
                            "why": "the case's share of the call budget was "
                                   "spent"})
            continue
        rows, n = ARN.review_group(view, table, by_id, g["members"], respond, tr)
        calls += n
        rec["semantic_groups"].append(
            {"members": g["members"], "scheduling_reason": g["reason"],
             "llm_calls": n, "rows": [rows[m] for m in g["members"]
                                      if m in rows]})
        for m in g["members"]:
            if m in rows:
                tr.enter(rows[m]["state"], schema=m)
    rec["semantic_scheduling"]["llm_calls"] = calls
    rec["semantic_scheduling"]["skipped_for_budget"] = skipped
    rec["semantic_scheduling"]["unreviewed_groups"] = [
        s["schema_id"] for s in schemas
        if s["schema_id"] not in
        set(m for g in rec["semantic_groups"] for m in g["members"])]

    n = 0
    for grp in rec["semantic_groups"]:
        for row in grp["rows"]:
            if row["state"] != "semantic_promoted":
                continue
            n += 1
            world = ARN.promoted_world(view, row, "A%d" % n, gk, w_reviewed,
                                       _inert)
            world["scheduling_reason"] = grp["scheduling_reason"]
            rec["semantic_promoted_worlds"].append(world)
            row["state"] = world["state"]
            tr.enter(world["state"], schema=row["schema_id"])

    # a probe whose rule the semantic stage refused keeps its proof and says so
    reviewed = {r["schema_id"]: r for grp in rec["semantic_groups"]
                for r in grp["rows"]}
    for w in rec["probe_worlds"]:
        r = reviewed.get(w["schema_id"])
        if w.get("state") != "probe_proof":
            continue
        w["semantic_status"] = (r["state"] if r else "not_reviewed")
        w["semantic_refusals"] = (r or {}).get("refusals")
    rec["unverified_probe_worlds"] = [w for w in rec["probe_worlds"]
                                      if w.get("state") == "probe_proof"
                                      and w.get("semantic_status")
                                      != "semantic_promoted"]
    ARN.assert_invariants(rec)
    rec["trace"] = tr.states
    return rec


def _ids_from_line(text):
    """Schema ids off a SELECTED line only — never scraped from prose."""
    import re
    for raw in (text or "").splitlines():
        s = raw.strip()
        if s.upper().startswith("SELECTED:"):
            return [x.upper() for x in re.findall(r"[Hh]\d+", s)]
    return []
