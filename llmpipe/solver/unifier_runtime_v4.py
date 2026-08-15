"""The v4 literal-bridge pipeline.

Same structure as v3 — front door, candidates, one rule call, compile at full
confidence with `$block`, one pooled gk world, a second rule call, one
accumulated pool, keep every proof, minimise, exclude, grade after the fact.
Four things behave differently:

  * the proposal prompt now carries the ORIGINAL ENGLISH above the candidate
    lists, which is where three of the audited misses were traced to;
  * the second call is made in BOTH directions of the first result.  No proof:
    the correction prompt, which no longer claims that a body is "available" —
    occurrence in a clause is not derivability, and v3's report said otherwise.
    A proof: the alternative-rules prompt, so an early doubtful bridge cannot
    end rule generation.  Neither prompt reveals the answer, the proof, the
    confidence, the cited ids or any grade;
  * the first pool's result is preserved separately from the accumulated one;
  * an unreadable or empty second reply removes nothing.

Everything else — the world builder, minimisation, the bounded exclusion
search, the grading call and the complete audit record — is v3's, imported.
"""

import hashlib
import json
import os

import bridge_world as BW

import dynamic_runtime as RT
import rule_redundancy_v3 as RR
import simple_rule_compiler_v4 as C4
import simple_rule_parser as SP
import simple_rule_parser_v4 as P4
import unifier_candidates_v4 as CV4
import unifier_runtime as UR
import unifier_runtime_v3 as U3

# 1.1: the first v4 run was aborted after two mechanical defects of my own —
# the harness had no `alternative` role (KeyError on the first case whose pool
# proved) and the world builder caught only BridgeError, so a converter
# TypeError ended `folio-0001`.  Both are fixed here and in
# `simple_rule_compiler_v4`; the aborted run is kept as its own artifact and
# both cohorts were rerun from scratch.
VERSION = "unifier_runtime_v4/1.1"

ROOT = U3.ROOT
PROMPT_DIR = U3.PROMPT_DIR

RULES_PROMPT = "unifier_rules_v4"
FEEDBACK_PROMPT = "unifier_rule_feedback_v2"
ALTERNATIVE_PROMPT = "unifier_rule_alternative_v1"
GRADE_PROMPT = "grade_used_rules_v2"

POOL_CAP = U3.POOL_CAP
MAX_EXCLUSION_WORLDS = U3.MAX_EXCLUSION_WORLDS
MAX_SECOND_ROUND_RULES = 8
WEIGHT = U3.WEIGHT
WEIGHT_POLICY = U3.WEIGHT_POLICY

GRADES = U3.GRADES
UNASSESSED = U3.UNASSESSED
GRADE_ORDER = U3.GRADE_ORDER
BAD_GRADES = U3.BAD_GRADES

prompt_text = U3.prompt_text
prompt_sha = U3.prompt_sha
sha_of = U3.sha_of
classify_gk = U3.classify_gk
distinct_sets = U3.distinct_sets
worst_grade = U3.worst_grade
order_pool = U3.order_pool


class RuntimeError_(U3.RuntimeError_):
    pass


def component_hashes():
    out = {}
    for mod in ("unifier_candidates_v4", "simple_rule_parser_v4",
                "unifier_runtime_v4", "unifier_candidates_v3",
                "simple_rule_parser_v3", "simple_rule_compiler_v3",
                "rule_redundancy_v3", "unifier_runtime_v3",
                "unifier_abstraction", "simple_rule_parser",
                "simple_rule_compiler", "unifier_runtime", "bridge_world",
                "dynamic_score", "option_scope", "alignment_occurrences"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    for name in (RULES_PROMPT, FEEDBACK_PROMPT, ALTERNATIVE_PROMPT,
                 GRADE_PROMPT):
        out["prompts/dynamic_alignment/%s.txt" % name] = prompt_sha(name)
    ax = os.path.join(ROOT, "axioms_std.js")
    out["axioms_std.js"] = hashlib.sha256(open(ax, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------------------- worlds
#
# `run_world`, `minimise` and `exclusion_search` are v3's, with one difference:
# they build the world through `simple_rule_compiler_v4`, whose guard is total.
# They are copied rather than parameterised because `unifier_runtime_v3.py` is
# hashed by the v4 preflight and must stay byte-identical.

def run_world(view, rules, gk, configuration, world_id, tag, sidecar=None):
    """Compile a pool, append it to the STORED theory, ask gk, record all of it."""
    world = C4.build_world(world_id, rules, view, configuration, weight=WEIGHT,
                           redundancy=RR.checker(view))
    record = {
        "world_id": world_id, "tag": tag,
        "rules_offered": [r["rule_id"] for r in rules],
        "refused_by_the_compiler": world["refused_by_the_compiler"],
        "hypotheses_offered": world["hypotheses_in_this_world"],
        "bridge_hypotheses": [
            dict((k, v) for k, v in h.items() if k != "compiled_clauses")
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
    kept = [p for p in replay["proofs"] if p["answer"] == proof["answer"]]
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
        still = [p for p in got["proofs"] if p["answer"] == proof["answer"]]
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
    """Exclude each bridge of the first minimal set and look for another proof."""
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
                dict((k, v) for k, v in p.items() if k != "proof"))
            row["minimised"].append(m)
        row["found_a_different_proof"] = bool(row["minimised"])
        out.append(row)
    return out


# ------------------------------------------------------------------ prompts

def english_block(view):
    """The passage and its question, exactly as the benchmark states them."""
    text = (view.get("input_text") or "").strip()
    question = UR.question_text(view)
    out = ["THE ORIGINAL PASSAGE AND QUESTION", "", text]
    if question and question not in text:
        out += ["", "THE QUESTION: %s" % question]
    return "\n".join(out)


def rules_prompt(view, candidates):
    """English, then the notation instructions, then the candidate lists."""
    import alignment_protocol as P
    prompt = "\n\n".join([english_block(view), prompt_text(RULES_PROMPT),
                          candidates["body"]])
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def _rules_block(rules, refusals):
    L = ["RULES ALREADY TRIED", ""]
    for r in rules:
        L.append("  %-4s %s" % (r["rule_id"], r["printed"]))
    if refusals:
        L += ["", "OF THOSE, THE PROGRAM COULD NOT USE:", ""]
        for r in refusals:
            L.append("  %-4s %s — %s" % (r.get("rule_id"), r.get("printed"),
                                         r.get("why")))
    return "\n".join(L)


def second_round_prompt(view, candidates, rules, refusals, found_a_proof):
    """The correction prompt, or the alternative-rules prompt.

    Neither carries the answer, the proof, its confidence, the cited bridge ids
    or any grade: the second call must not be able to infer what gk decided.
    """
    import alignment_protocol as P
    name = ALTERNATIVE_PROMPT if found_a_proof else FEEDBACK_PROMPT
    prompt = "\n\n".join([english_block(view), prompt_text(name),
                          candidates["body"],
                          _rules_block(rules, refusals)])
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt, name


def grade_rules(view, rules, respond, case_id):
    """One grading call, under the CORRECTED grader."""
    ids = [r["rule_id"] for r in rules]
    if not ids:
        return {"asked": False, "why": "no rule was used by any proof",
                "grades": {}}
    prompt = UR.grade_prompt(view, rules).replace(
        prompt_text(UR.GRADE_PROMPT), prompt_text(GRADE_PROMPT), 1)
    text, note = respond("grade", case_id, prompt)
    parsed = UR.parse_grades(text, ids)
    return {"asked": True, "raw": text, "note": note,
            "grader_prompt": GRADE_PROMPT,
            "prompt": prompt,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "grades": parsed["grades"], "rejected": parsed["rejected"],
            "readable": parsed["readable"], "graded": parsed["graded"],
            "total": parsed["total"]}


# ------------------------------------------------------------------ driver

def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             pool_cap=POOL_CAP, do_second_round=True, do_exclusions=True,
             do_grade=True):
    """One case, front door to graded proofs, with everything recorded."""
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": case_id, "mode": "unifier_v4", "version": VERSION,
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
    candidates = CV4.build(view, configuration)
    rows = candidates["main"] + candidates["secondary"]
    vocab = P4.vocabulary(rows)
    result["candidates"] = {
        "counts": candidates["counts"],
        "inventory_counts": candidates["inventory_counts"],
        "skolem_note_shown": candidates["skolem_note_shown"],
        "main": [U3._candidate_record(r) for r in candidates["main"]],
        "secondary": [U3._candidate_record(r)
                      for r in candidates["secondary"]],
        "main_omitted": candidates["main_omitted"],
        "secondary_omitted": candidates["secondary_omitted"],
        "mapping_diagnostics": candidates["mapping_diagnostics"],
        "body": candidates["body"],
        "grounding_atoms": vocab["grounding_atoms"],
        "policy": candidates["policy"]}
    if not rows:
        trace.append({"stage": "stopped",
                      "why": "no candidate atom has a rule position"})
        result["stopped_at"] = "no_candidate"
        return result

    source_rules = SP.stage2_source_rules(view["stage2"])
    rounds, worlds = [], []
    stopped = None

    trace.append({"stage": "round_1"})
    prompt = rules_prompt(view, candidates)
    text, note = respond("rules", "%s/r1" % case_id, prompt)
    parsed = P4.parse_response(text, vocab, source_rules)
    rules = list(parsed["accepted"])
    rounds.append(U3._round_record(1, prompt, text, note, parsed))
    rounds[-1]["prompt_name"] = RULES_PROMPT
    first_world = None
    if rules and budget():
        pool, dropped = order_pool(rules, cap=pool_cap)
        first_world, _w = run_world(view, pool, gk, configuration,
                                    "pool_%s_r1" % case_id,
                                    "%s/round 1" % case_id, sidecar)
        first_world["round"] = 1
        first_world["pool_omitted"] = dropped
        worlds.append(first_world)
        rounds[-1].update({"pool": [r["rule_id"] for r in pool],
                           "pool_omitted": dropped,
                           "world_id": first_world["world_id"],
                           "outcome": first_world["outcome"],
                           "dynamic_proofs":
                               len(first_world["dynamic_proofs"])})
    elif not rules:
        rounds[-1]["no_world"] = "no rule was accepted"
    else:
        rounds[-1]["no_world"] = "gk budget reached"
        stopped = "gk_budget"

    found = bool(first_world and first_world["dynamic_proofs"])
    result["first_pool"] = {
        "world_id": (first_world or {}).get("world_id"),
        "outcome": (first_world or {}).get("outcome"),
        "dynamic_proofs": len((first_world or {}).get("dynamic_proofs") or []),
        "answers": [p["answer"] for p in (first_world or {}).get("proofs")
                    or []],
        "kept_separately": "the accumulated second pool never replaces this "
                           "result"}

    if do_second_round and not stopped and rules:
        trace.append({"stage": "round_2"})
        refusals = []
        for w in worlds:
            refusals.extend(w.get("refused_by_the_compiler") or [])
        prompt2, name = second_round_prompt(view, candidates, rules, refusals,
                                            found)
        text2, note2 = respond("feedback" if not found else "alternative",
                               "%s/r2" % case_id, prompt2)
        parsed2 = P4.parse_response(text2, vocab, source_rules,
                                    max_rules=MAX_SECOND_ROUND_RULES,
                                    start_index=parsed["next_index"],
                                    existing=rules)
        rounds.append(U3._round_record(2, prompt2, text2, note2, parsed2))
        rounds[-1]["prompt_name"] = name
        rounds[-1]["because"] = ("the first pool found a bridge-dependent "
                                 "proof" if found else
                                 "the first pool found no proof citing a "
                                 "bridge")
        # an unreadable or empty reply removes nothing
        rules = rules + list(parsed2["accepted"])
        if parsed2["accepted"] and budget():
            pool, dropped = order_pool(rules, cap=pool_cap)
            world, _w = run_world(view, pool, gk, configuration,
                                  "pool_%s_r2" % case_id,
                                  "%s/round 2" % case_id, sidecar)
            world["round"] = 2
            world["pool_omitted"] = dropped
            worlds.append(world)
            rounds[-1].update({"pool": [r["rule_id"] for r in pool],
                               "pool_omitted": dropped,
                               "world_id": world["world_id"],
                               "outcome": world["outcome"],
                               "dynamic_proofs":
                                   len(world["dynamic_proofs"])})
        elif not parsed2["accepted"]:
            rounds[-1]["no_world"] = ("the second call accepted no new rule; "
                                      "the first rules and any first proof "
                                      "are untouched")
        else:
            rounds[-1]["no_world"] = "gk budget reached"
            stopped = "gk_budget"

    result["rounds"] = rounds
    result["rules"] = [U3._rule_record(r) for r in rules]
    result["worlds"] = [U3._world_record(w) for w in worlds]
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
        result["stopped_at"] = stopped or U3._no_proof_reason(worlds, rules)
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
        result["exclusions"] = exclusion_search(
            view, gk, configuration, case_id, list(rules), rules_by_id, first,
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
