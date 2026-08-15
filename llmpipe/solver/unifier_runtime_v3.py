"""The v3 literal-bridge pipeline, end to end, with a complete audit trail.

    conservative front door
      answered -> stop, no abstraction call, no dynamic gk call
      Unknown  -> converter-aware candidates with roles and priority costs
                  one rule call
                  parse, keep general rules AND their ground specializations
                  compile each rule separately, refuse the empty and the
                    already-present ones by name
                  ONE pooled gk world
                  no cited proof -> mechanical connection report
                                    one feedback call
                                    accumulate old and new rules
                                    a SECOND pooled world
                  any cited proof -> minimise every distinct cited set
                                     bounded exclusion search, always
                                     minimise every exclusion proof too
                                     grade every bridge of every minimal proof

Every bridge reaches gk at full confidence with its `$block`; the only gk option
that changes is the proof-return threshold, and both values are recorded on
every call.  A grade is computed after the proof and can never withdraw one.

What v2 stored was not enough to audit: this module keeps, per gk call, the
exact submitted clause list and its hash, the effective gk command, the raw
output, the parsed result string, and whether the outcome was a proof, no
proof, an error, a timeout, or an answer the formatter alone called Unknown.
"""

import hashlib
import json
import os
import time

import bridge_world as BW
import dynamic_score as DS
import rule_redundancy_v3 as RR
import simple_rule_compiler_v3 as C3
import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import unifier_candidates_v3 as CV
import unifier_feedback_v3 as FB
import unifier_runtime as UR

VERSION = "unifier_runtime_v3/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")

RULES_PROMPT = "unifier_rules_v2"
FEEDBACK_PROMPT = "unifier_rule_feedback_v1"
GRADE_PROMPT = "grade_used_rules_v1"

POOL_CAP = 80
MAX_EXCLUSION_WORLDS = 4
WEIGHT = 1.0
WEIGHT_POLICY = UR.WEIGHT_POLICY

# gk's own result strings, from its README.  They are what separates a genuine
# no-proof from a timeout, which v2 reported as the same thing.
GK_ANSWER = "answer found"
GK_TIMEOUT = "time limit"
GK_BELOW = "evidence below limit"

GRADES = UR.GRADES
UNASSESSED = UR.UNASSESSED
GRADE_ORDER = UR.GRADE_ORDER
BAD_GRADES = UR.BAD_GRADES


class RuntimeError_(Exception):
    """The runtime cannot proceed.  Never worked around."""


def prompt_text(name):
    with open(os.path.join(PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_sha(name):
    return hashlib.sha256(prompt_text(name).encode()).hexdigest()


def sha_of(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                     default=str).encode()).hexdigest()


def component_hashes():
    out = {}
    for mod in ("unifier_candidates_v3", "simple_rule_parser_v3",
                "simple_rule_compiler_v3", "rule_redundancy_v3",
                "unifier_feedback_v3", "unifier_runtime_v3",
                "unifier_abstraction", "simple_rule_parser",
                "simple_rule_compiler", "unifier_runtime", "bridge_world",
                "dynamic_score", "option_scope", "alignment_occurrences"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    for name in (RULES_PROMPT, FEEDBACK_PROMPT, GRADE_PROMPT):
        out["prompts/dynamic_alignment/%s.txt" % name] = prompt_sha(name)
    ax = os.path.join(ROOT, "axioms_std.js")
    out["axioms_std.js"] = hashlib.sha256(open(ax, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------------------ prompts

def rules_prompt(candidates):
    import alignment_protocol as P
    instructions = prompt_text(RULES_PROMPT)
    prompt = instructions + "\n\n" + candidates["body"]
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def feedback_prompt(candidates, connection):
    import alignment_protocol as P
    instructions = prompt_text(FEEDBACK_PROMPT)
    prompt = instructions + "\n\n" + FB.render(connection, candidates["body"])
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


# ------------------------------------------------------------------- worlds

def classify_gk(raw, answer, proofs):
    """-> (outcome, gk result string).  A timeout is never an ordinary miss."""
    text = raw if isinstance(raw, str) else json.dumps(raw)
    if text.startswith("Error:"):
        return "gk_error", text[:200]
    try:
        data = json.loads(text)
    except ValueError:
        return "gk_error", "unparsable gk output"
    result = str(data.get("result") or "")
    if data.get("error"):
        return "gk_error", str(data["error"])[:200]
    if result.startswith(GK_TIMEOUT):
        return "timeout", result
    if result == GK_ANSWER:
        if proofs:
            return "proof", result
        return "answer_without_a_proof", result
    if result == GK_BELOW:
        return "evidence_below_limit", result
    if answer not in (None, "Unknown.", "") and not proofs:
        return "formatter_answer_without_proof", result
    return "no_proof", result


def run_world(view, rules, gk, configuration, world_id, tag, sidecar=None):
    """Compile a pool, append it to the STORED theory, ask gk, record all of it."""
    world = C3.build_world(world_id, rules, view, configuration, weight=WEIGHT,
                           redundancy=RR.checker(view))
    record = {
        "world_id": world_id, "tag": tag,
        "rules_offered": [r["rule_id"] for r in rules],
        "refused_by_the_compiler": world["refused_by_the_compiler"],
        "hypotheses_offered": world["hypotheses_in_this_world"],
        "bridge_hypotheses": [
            {k: v for k, v in h.items() if k != "compiled_clauses"}
            for h in world["bridge_hypotheses"]],
        "compiled_bridge_clauses": world["compiled_bridge_clauses"],
        "clause_provenance": world["clause_provenance"],
        "bridge_clause_count": len(world["compiled_bridge_clauses"]),
        "clause_confidence_annotations": [
            c.get("@confidence") for c in world["compiled_bridge_clauses"]],
        "all_clauses_have_block": BW.has_block(
            world["compiled_bridge_clauses"]) if world[
                "compiled_bridge_clauses"] else None,
    }
    if world["nothing_compiled"]:
        record.update({"skipped": "no rule of this pool converted to a clause",
                       "outcome": "compiler_refusal", "proofs": [],
                       "dynamic_proofs": [], "answers_returned": 0})
        return record, world
    clauses = list(view["final_clauses"]) + [
        dict(c) for c in world["compiled_bridge_clauses"]]
    stored = {"stage1": view["stage1"], "stage2": view["stage2"],
              "final_clauses": view["final_clauses"],
              "input_text": view["input_text"]}
    got = gk(clauses, stored, tag, dynamic=True)
    proofs = UR.proofs_of(got.get("raw") or "{}", world["clause_provenance"])
    printed = world["printed_by_hypothesis_id"]
    for p in proofs:
        p["cited_rules"] = [world["rule_by_hypothesis_id"].get(h)
                            for h in p["cited_hypothesis_ids"]]
        p["cited_formulas"] = [printed.get(h)
                               for h in p["cited_hypothesis_ids"]]
    dynamic = [p for p in proofs if not p["cites_no_dynamic_hypothesis"]]
    outcome, result = classify_gk(got.get("raw") or "{}", got.get("answer"),
                                  proofs)
    record.update({
        "submitted_clause_count": len(clauses),
        "submitted_theory_sha256": sha_of(clauses),
        "base_theory_sha256": sha_of(view["final_clauses"]),
        "gk_command": got.get("gk_command"),
        "gk_input_sha256": got.get("gk_input_sha256"),
        "gk_result_string": result,
        "outcome": outcome,
        "proofs": proofs,
        "dynamic_proofs": dynamic,
        "answers_returned": len(proofs),
        "conservative_formatter_answer": got.get("answer"),
        "gk_thresholds": got.get("thresholds"),
        "seconds": got.get("seconds"),
        "error": got.get("error"),
        "raw_gk_output_sha256": hashlib.sha256(
            (got.get("raw") or "").encode()).hexdigest(),
    })
    if sidecar is not None:
        record["sidecar"] = sidecar(world_id, clauses, got)
    else:
        record["raw_gk_output"] = got.get("raw")
        record["submitted_clauses"] = clauses
    return record, world


# ------------------------------------------------------------------- pools

def order_pool(rules, cap=POOL_CAP):
    """-> (the rules gk sees, the ones the cap left out, with the reason).

    Role fit first — a body the theory can supply and a head it needs — then
    rule priority cost, then a general rule before its own ground variants.
    """
    def key(r):
        fit = r.get("role_fit") or {}
        return (0 if fit.get("fits") else 1,
                0 if fit.get("head_fits") else 1,
                r.get("rule_priority_cost", 0),
                0 if r.get("origin") == P3.LLM_GENERAL else 1,
                r["rule_id"])
    ordered = sorted(rules, key=key)
    kept, dropped = ordered[:cap], ordered[cap:]
    return kept, [{"rule_id": r["rule_id"], "printed": r["printed"],
                   "why": "beyond the %d-rule pool cap" % cap}
                  for r in dropped]


# ------------------------------------------------------- minimise / exclude

def _same_answer(proofs, answer):
    return [p for p in proofs if p["answer"] == answer]


def minimise(view, gk, configuration, case_id, rules_by_id, proof, budget,
             tag, sidecar=None):
    """Replay the cited set, then delete one rule at a time.  Deletion-minimal."""
    cited = [rules_by_id[r] for r in proof["cited_rules"] if r in rules_by_id]
    if not cited:
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "why": "the proof cites no dynamic hypothesis"}
    if not budget():
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "why": "gk budget reached before the replay"}
    replay, _w = run_world(view, cited, gk, configuration,
                           "replay_%s_%s" % (case_id, tag),
                           "%s/replay %s" % (case_id, tag), sidecar)
    kept = _same_answer(replay["proofs"], proof["answer"])
    if not kept:
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "replay": replay,
                "replay_answers": [p["answer"] for p in replay["proofs"]],
                "why": "the cited set alone did not reproduce the answer"}
    keep, deletions = list(cited), []
    for r in list(cited):
        if len(keep) <= 1 or not budget():
            break
        trial = [x for x in keep if x["rule_id"] != r["rule_id"]]
        got, _w = run_world(view, trial, gk, configuration,
                            "min_%s_%s_no_%s" % (case_id, tag, r["rule_id"]),
                            "%s/%s without %s" % (case_id, tag, r["rule_id"]),
                            sidecar)
        still = _same_answer(got["proofs"], proof["answer"])
        deletions.append({"removed": r["rule_id"], "printed": r["printed"],
                          "world_id": got["world_id"],
                          "outcome": got["outcome"],
                          "answers_without_it": [p["answer"]
                                                 for p in got["proofs"]][:4],
                          "removing_it_destroys_the_proof": not still})
        if still:
            keep = trial
    return {"minimised": True, "cited_rules": proof["cited_rules"],
            "minimal_rules": [r["rule_id"] for r in keep],
            "minimal_printed": [r["printed"] for r in keep],
            "size": len(keep), "replay_reproduced": True,
            "replay_world_id": replay["world_id"],
            "deletions": deletions,
            "note": "deletion-minimal, not globally minimum"}


def exclusion_search(view, gk, configuration, case_id, pool_rules,
                     rules_by_id, first_minimal, budget, sidecar=None,
                     cap=MAX_EXCLUSION_WORLDS):
    """Exclude each bridge of the first minimal set and look for another proof.

    Run whether or not the first proof's grades look good: a first proof can
    hide a better one, and v2 only looked when the first one graded badly.
    Every proof found here is minimised and graded like any other.
    """
    out = []
    for rid in list(first_minimal)[:cap]:
        if not budget():
            out.append({"excluded": rid, "skipped": "gk budget reached"})
            break
        keep = [r for r in pool_rules if r["rule_id"] != rid]
        if not keep:
            out.append({"excluded": rid, "skipped": "nothing left to try"})
            continue
        got, _w = run_world(view, keep, gk, configuration,
                            "excl_%s_no_%s" % (case_id, rid),
                            "%s/excluding %s" % (case_id, rid), sidecar)
        row = {"excluded": rid,
               "excluded_printed": rules_by_id[rid]["printed"]
               if rid in rules_by_id else None,
               "world_id": got["world_id"], "outcome": got["outcome"],
               "answers": [p["answer"] for p in got["proofs"]],
               "dynamic_proofs": [], "minimised": []}
        for p in got["dynamic_proofs"]:
            m = minimise(view, gk, configuration, case_id, rules_by_id, p,
                         budget, "excl_%s" % rid, sidecar)
            m["answer"] = p["answer"]
            m["gk_native_confidence"] = p["gk_native_confidence"]
            m["world_id"] = got["world_id"]
            m["found_by_excluding"] = rid
            row["dynamic_proofs"].append(
                {k: v for k, v in p.items() if k != "proof"})
            row["minimised"].append(m)
        row["found_a_different_proof"] = bool(row["minimised"])
        out.append(row)
    return out


def distinct_sets(minimal_rows):
    """Deduplicate AFTER minimisation, by (answer, minimal set)."""
    seen, out = set(), []
    for m in minimal_rows:
        ids = m.get("minimal_rules") or m.get("cited_rules") or []
        key = (json.dumps(m.get("answer"), default=str),
               tuple(sorted(ids)))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


# ------------------------------------------------------------------ grading

def grade_rules(view, rules, respond, case_id):
    return UR.grade_rules(view, rules, respond, case_id)


def worst_grade(grades, ids):
    return UR.worst_grade(grades, ids)


# ------------------------------------------------------------------ driver

def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             pool_cap=POOL_CAP, do_feedback=True, do_exclusions=True,
             do_grade=True):
    """One case, front door to graded proofs, with everything recorded."""
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    front = UR.front_door(view, gk) if hasattr(UR, "front_door") else None
    if front is None:
        import dynamic_runtime as RT
        front = RT.front_door(view, gk)
    import dynamic_runtime as RT
    result = {"case_id": case_id, "mode": "unifier_v3", "version": VERSION,
              "view_sha256": RT.view_hash(view),
              "configuration": configuration,
              "input_text": view["input_text"],
              "stage1_sha256": sha_of(view["stage1"]),
              "stage2_sha256": sha_of(view["stage2"]),
              "base_theory_sha256": sha_of(view["final_clauses"]),
              "base_clause_count": len(view["final_clauses"]),
              "conservative": front, "trace": trace,
              "dynamic_work_done": False, "weight_policy": WEIGHT_POLICY}
    if front["resolved"]:
        trace.append({"stage": "stopped",
                      "why": "the conservative front door answered %r; no "
                             "abstraction LLM call and no dynamic gk call were "
                             "made" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "candidates"})
    candidates = CV.build(view, configuration)
    rows = candidates["main"] + candidates["secondary"]
    vocab = P3.vocabulary(rows)
    result["candidates"] = {
        "counts": candidates["counts"],
        "inventory_counts": candidates["inventory_counts"],
        "skolem_note_shown": candidates["skolem_note_shown"],
        "main": [_candidate_record(r) for r in candidates["main"]],
        "secondary": [_candidate_record(r) for r in candidates["secondary"]],
        "main_omitted": candidates["main_omitted"],
        "secondary_omitted": candidates["secondary_omitted"],
        "mapping_diagnostics": candidates["mapping_diagnostics"],
        "body": candidates["body"],
        "policy": candidates["policy"]}
    if not rows:
        trace.append({"stage": "stopped",
                      "why": "no candidate atom has a rule position"})
        result["stopped_at"] = "no_candidate"
        return result

    source_rules = SP.stage2_source_rules(view["stage2"])
    rules, rounds, worlds = [], [], []
    stopped = None

    trace.append({"stage": "round_1"})
    prompt = rules_prompt(candidates)
    text, note = respond("rules", "%s/r1" % case_id, prompt)
    parsed = P3.parse_response(text, vocab, source_rules)
    rules = list(parsed["accepted"])
    rounds.append(_round_record(1, prompt, text, note, parsed))
    if rules and budget():
        pool, dropped = order_pool(rules, cap=pool_cap)
        world, _w = run_world(view, pool, gk, configuration,
                              "pool_%s_r1" % case_id, "%s/round 1" % case_id,
                              sidecar)
        world["round"] = 1
        world["pool_omitted"] = dropped
        worlds.append(world)
        rounds[-1]["pool"] = [r["rule_id"] for r in pool]
        rounds[-1]["pool_omitted"] = dropped
        rounds[-1]["world_id"] = world["world_id"]
        rounds[-1]["outcome"] = world["outcome"]
        rounds[-1]["dynamic_proofs"] = len(world["dynamic_proofs"])
    elif not rules:
        rounds[-1]["no_world"] = "no rule was accepted"
    else:
        rounds[-1]["no_world"] = "gk budget reached"
        stopped = "gk_budget"

    got_proof = any(w["dynamic_proofs"] for w in worlds)
    if do_feedback and not got_proof and not stopped:
        trace.append({"stage": "feedback"})
        refused = []
        already = []
        for w in worlds:
            for r in w["refused_by_the_compiler"]:
                (already if r.get("kind") == "already_present"
                 else refused).append(r)
        connection = FB.report(rules, rows, refused=refused, already=already)
        result["connection_report"] = connection
        fprompt = feedback_prompt(candidates, connection)
        ftext, fnote = respond("feedback", "%s/r2" % case_id, fprompt)
        fparsed = P3.parse_response(ftext, vocab, source_rules,
                                    max_rules=FB.MAX_NEW_RULES,
                                    start_index=parsed["next_index"],
                                    existing=rules)
        rules = rules + list(fparsed["accepted"])
        rounds.append(_round_record(2, fprompt, ftext, fnote, fparsed))
        if fparsed["accepted"] and budget():
            pool, dropped = order_pool(rules, cap=pool_cap)
            world, _w = run_world(view, pool, gk, configuration,
                                  "pool_%s_r2" % case_id,
                                  "%s/round 2" % case_id, sidecar)
            world["round"] = 2
            world["pool_omitted"] = dropped
            worlds.append(world)
            rounds[-1]["pool"] = [r["rule_id"] for r in pool]
            rounds[-1]["pool_omitted"] = dropped
            rounds[-1]["world_id"] = world["world_id"]
            rounds[-1]["outcome"] = world["outcome"]
            rounds[-1]["dynamic_proofs"] = len(world["dynamic_proofs"])
        elif not fparsed["accepted"]:
            rounds[-1]["no_world"] = "the feedback round accepted no new rule"
        else:
            rounds[-1]["no_world"] = "gk budget reached"
            stopped = "gk_budget"

    result["rounds"] = rounds
    result["rules"] = [_rule_record(r) for r in rules]
    result["worlds"] = [_world_record(w) for w in worlds]
    rules_by_id = dict((r["rule_id"], r) for r in rules)

    seen, distinct = set(), []
    for w in worlds:
        for p in w["proofs"]:
            key = (json.dumps(p["answer"], default=str),
                   tuple(sorted(p["cited_rules"])))
            if key in seen:
                continue
            seen.add(key)
            distinct.append(dict(p, world_id=w["world_id"],
                                 round=w.get("round")))
    result["returned_proofs"] = [{k: v for k, v in p.items() if k != "proof"}
                                 for p in distinct]
    result["answers_with_no_cited_hypothesis"] = [
        p["answer"] for p in distinct if p["cites_no_dynamic_hypothesis"]]
    if result["answers_with_no_cited_hypothesis"] and budget():
        stored = {"stage1": view["stage1"], "stage2": view["stage2"],
                  "final_clauses": view["final_clauses"],
                  "input_text": view["input_text"]}
        got = gk(list(view["final_clauses"]), stored,
                 "%s/threshold only" % case_id, dynamic=True)
        base = UR.proofs_of(got.get("raw") or "{}", {})
        result["threshold_only_baseline"] = {
            "why": "a proof cited no dynamic hypothesis; this is the base "
                   "theory alone at the dynamic proof-return threshold",
            "answers": [p["answer"] for p in base],
            "gk_command": got.get("gk_command"),
            "formatter_answer": got.get("answer"),
            "the_threshold_alone_explains_it": bool(base)}
    dynamic = [p for p in distinct if not p["cites_no_dynamic_hypothesis"]]
    if not dynamic:
        trace.append({"stage": "stopped", "why": "no proof cited a bridge"})
        result["stopped_at"] = stopped or _no_proof_reason(worlds, rules)
        return result

    trace.append({"stage": "minimise"})
    minimal = []
    for p in dynamic:
        m = minimise(view, gk, configuration, case_id, rules_by_id, p, budget,
                     "p%d" % (len(minimal) + 1), sidecar)
        m.update({"answer": p["answer"],
                  "gk_native_confidence": p["gk_native_confidence"],
                  "world_id": p["world_id"], "round": p.get("round"),
                  "found_by_excluding": None})
        minimal.append(m)

    if do_exclusions and minimal:
        trace.append({"stage": "exclusions"})
        first = minimal[0].get("minimal_rules") or minimal[0]["cited_rules"]
        pool_rules = [r for r in rules]
        result["exclusions"] = exclusion_search(
            view, gk, configuration, case_id, pool_rules, rules_by_id, first,
            budget, sidecar)
        for row in result["exclusions"]:
            for m in row.get("minimised") or []:
                minimal.append(m)
    result["minimisation"] = distinct_sets(minimal)
    result["distinct_minimal_sets"] = sorted(set(
        tuple(sorted(m.get("minimal_rules") or m.get("cited_rules") or []))
        for m in result["minimisation"]))

    used_ids = []
    for m in result["minimisation"]:
        for r in (m.get("minimal_rules") or m.get("cited_rules") or []):
            if r not in used_ids:
                used_ids.append(r)
    used = [rules_by_id[r] for r in used_ids if r in rules_by_id]
    if do_grade:
        trace.append({"stage": "grade"})
        result["grading"] = grade_rules(view, used, respond, case_id)
    else:
        result["grading"] = {"asked": False, "grades": {}}
    grades = result["grading"].get("grades") or {}
    for m in result["minimisation"]:
        ids = m.get("minimal_rules") or m.get("cited_rules") or []
        m["worst_grade"] = worst_grade(grades, ids)
        m["grades"] = dict((r, grades.get(r, {}).get("grade", UNASSESSED))
                           for r in ids)
    result["stopped_at"] = stopped
    return result


def _no_proof_reason(worlds, rules):
    if not rules:
        return "no_rule_accepted"
    if not worlds:
        return "no_world_ran"
    if all(w.get("outcome") == "compiler_refusal" for w in worlds):
        return "every_rule_refused_by_the_compiler"
    if any(w.get("outcome") == "timeout" for w in worlds):
        return "gk_timeout"
    if any(w.get("outcome") == "gk_error" for w in worlds):
        return "gk_error"
    return "no_proof"


def _candidate_record(row):
    return dict((k, v) for k, v in row.items() if k != "converted_literals")


def _rule_record(r):
    return dict((k, v) for k, v in r.items())


def _round_record(n, prompt, text, note, parsed):
    return {"round": n, "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "prompt_chars": len(prompt), "raw": text, "llm_note": note,
            "readable_rule_lines": parsed["readable_lines"],
            "accepted": [{"rule_id": r["rule_id"], "printed": r["printed"],
                          "origin": r["origin"], "warnings": r["warnings"],
                          "rule_priority_cost": r["rule_priority_cost"],
                          "role_fit": r["role_fit"],
                          "candidate_matches": r["candidate_matches"],
                          "atoms_matching_no_candidate":
                              r["atoms_matching_no_candidate"],
                          "specialization_of": r.get("specialization_of")}
                         for r in parsed["accepted"]],
            "rejected": parsed["rejected"],
            "over_cap": parsed["over_cap"],
            "rejection_reasons": parsed["rejection_reasons"]}


def _world_record(w):
    out = dict((k, v) for k, v in w.items()
               if k not in ("proofs", "dynamic_proofs", "clause_provenance"))
    out["proofs"] = [dict((x, y) for x, y in p.items() if x != "proof")
                     for p in w.get("proofs") or []]
    out["proof_steps"] = dict(
        (p["answer_index"], p.get("proof")) for p in w.get("proofs") or [])
    out["dynamic_proof_count"] = len(w.get("dynamic_proofs") or [])
    out["clause_provenance"] = w.get("clause_provenance")
    return out
