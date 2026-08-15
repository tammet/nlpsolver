"""The v5.2 literal-bridge pipeline: the clear positive prompt, run for real.

The algorithm is v4's and the report should describe it that way:

    conservative front door with the stored gk command
      answered -> stop.  No abstraction call, no dynamic gk call
      silent   -> separate the passage from the question, or refuse the case
                  build the complete positive candidate list
                  ONE proposal call: the fixed v5.1 system prompt as the system
                    message, the case message as the user message
                  parse up to twelve valid model-written base rules
                  compile every rule SEPARATELY; a refusal names that rule and
                    leaves the others alone
                  ONE gk run: the stored base clauses plus every compiled
                    round-1 bridge  ->  the round-1 bridge set
                  a SECOND proposal call, always: the no-proof message if that
                    run proved nothing, the alternative message if it proved
                    something
                  ONE gk run: the stored base clauses plus the union of
                    compiled round-1 and round-2 bridges  ->  the accumulated
                    bridge set
                  every returned proof is kept, replayed and deletion-minimised
                  the bounded exclusion search runs even when the first minimal
                    set looks credible
                  grades are asked for afterwards and can never remove a proof

Four differences from `unifier_runtime_v4`:

  * the prompts are `unifier_prompt_v5_2`'s, and the system message is the fixed
    v5.1 instruction text, identical for every case and every call, so the
    transport can cache it;
  * the twelve-rule limit counts valid model-written base rules only
    (`simple_rule_parser_v5_2`);
  * the candidate inventory is complete: no 80/24 truncation before the positive
    groups are formed;
  * an accumulated bridge set holds at most `MAX_ACCUMULATED_HYPOTHESES`
    compiled hypotheses, and model-written base rules are kept before
    program-generated specializations, which the v4 pool ordering did not
    guarantee.

Nothing in v1-v5.1 is modified.  The world builder, minimisation, the bounded
exclusion search and the grading call are v4's, imported.
"""

import hashlib
import json
import os

import dynamic_runtime as RT
import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import simple_rule_parser_v5_2 as P52
import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_2 as PR52
import unifier_question_v5_2 as Q52
import unifier_runtime as UR
import unifier_runtime_v3 as U3
import unifier_runtime_v4 as U4

VERSION = "unifier_runtime_v5_2/1.0"

ROOT = U3.ROOT

GRADE_PROMPT = U4.GRADE_PROMPT
SYSTEM_PROMPT_NAME = P51.SYSTEM_PROMPT_NAME

# One call may contribute at most this many valid model-written base rules.
MAX_BASE_RULES_PER_CALL = P52.MAX_BASE_RULES_PER_CALL
# An accumulated bridge set may hold at most this many compiled hypotheses.
MAX_ACCUMULATED_HYPOTHESES = 30
MAX_EXCLUSION_WORLDS = U4.MAX_EXCLUSION_WORLDS

WEIGHT = U4.WEIGHT
WEIGHT_POLICY = U4.WEIGHT_POLICY
GRADES = U4.GRADES
UNASSESSED = U4.UNASSESSED

sha_of = U3.sha_of
prompt_sha = U3.prompt_sha
prompt_text = U3.prompt_text
classify_gk = U3.classify_gk
distinct_sets = U3.distinct_sets
worst_grade = U3.worst_grade

run_world = U4.run_world
minimise = U4.minimise
exclusion_search = U4.exclusion_search
grade_rules = U4.grade_rules


class RuntimeError_(U4.RuntimeError_):
    pass


def component_hashes():
    out = dict(U4.component_hashes())
    for mod in ("unifier_prompt_v5_1", "unifier_prompt_v5_2",
                "unifier_question_v5_2", "simple_rule_parser_v5_1",
                "simple_rule_parser_v5_2", "unifier_runtime_v5_2"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    out["prompts/dynamic_alignment/%s.txt" % SYSTEM_PROMPT_NAME] = \
        PR52.system_prompt_sha256()
    out["memos/EXAMPLE_2026_08_13_clear_literal_bridge_prompt.md"] = \
        PR52.example_sha256()
    return out


# ------------------------------------------------- the accumulated bridge set

def order_hypotheses(rules, cap=MAX_ACCUMULATED_HYPOTHESES):
    """-> (the rules gk sees, the ones the limit left out, with the reason).

    A model-written base rule is never dropped for a program-generated
    specialization: the two are ordered as separate blocks, and only inside a
    block does role fit, then rule cost, then id decide.
    """
    def key(r):
        fit = r.get("role_fit") or {}
        return (0 if r.get("origin") == P3.LLM_GENERAL else 1,
                0 if fit.get("fits") else 1,
                0 if fit.get("head_fits") else 1,
                r.get("rule_priority_cost", 0),
                int(str(r["rule_id"])[1:] or 0))
    ordered = sorted(rules, key=key)
    kept, dropped = ordered[:cap], ordered[cap:]
    return kept, [{"rule_id": r["rule_id"], "printed": r["printed"],
                   "origin": r.get("origin"),
                   "specialization_of": r.get("specialization_of"),
                   "why": "beyond the %d compiled hypotheses an accumulated "
                          "bridge set may hold; model-written base rules are "
                          "kept first" % cap}
                  for r in dropped]


# ------------------------------------------------------------------ records

def _round_record(n, call, message, text, note, parsed):
    return {
        "round": n, "call": call,
        "system_prompt_name": message["system_prompt_name"],
        "system_prompt_sha256": message["system_prompt_sha256"],
        "user_message": message["text"],
        "user_message_sha256": message["sha256"],
        "user_message_chars": message["chars"],
        "question_split": message["question_split"],
        "attempted_rule_status": message.get("attempted_rule_status"),
        "raw": text, "llm_note": note,
        "readable_rule_lines": parsed["readable_lines"],
        "base_rules_accepted": parsed["base_rules_accepted"],
        "generated_specializations_accepted":
            parsed["generated_specializations_accepted"],
        "base_rule_limit": parsed["base_rule_limit"],
        "refused_negative_lines": parsed["refused_negative_lines"],
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
        "rejection_reasons": parsed["rejection_reasons"],
    }


def _candidate_record(built):
    """Everything about the displayed list, without repeating the message."""
    return {
        "version": built["version"],
        "counts": built["counts"],
        "inventory": built["inventory"],
        "groups_hidden_by_the_old_caps": built["groups_hidden_by_the_old_caps"],
        "displayed": [{"id": g["id"], "section": g["section"],
                       "printed": g["printed"], "role": g["role"],
                       "cost": g["cost"], "compiled_literal": g["literal"],
                       "question_linked": g["question_linked"],
                       "surface_atoms": g["surface_atoms"],
                       "source_candidate_ids": g["source_candidate_ids"],
                       "display_rules_applied": g["display_rules_applied"],
                       "merge_note": g["merge_note"],
                       "available_under_the_old_caps":
                           g["available_under_the_old_caps"],
                       "round_trip": g["round_trip"],
                       "writability": g["writability"]}
                      for g in built["groups"]],
        "omitted": built["omitted"],
        "conversion_errors": built["conversion_errors"],
        "policy": "every positive atom of the complete inventory that is "
                  "displayable and writable as a bridge in both positions is "
                  "shown; there is no row or group cap",
    }


# ------------------------------------------------------------------- driver

def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             hypothesis_cap=MAX_ACCUMULATED_HYPOTHESES, do_second_round=True,
             do_exclusions=True, do_grade=True):
    """One case, front door to graded proofs, with everything recorded."""
    PR52.check_fixed_inputs()
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": case_id, "mode": "unifier_v5_2", "version": VERSION,
              "view_sha256": RT.view_hash(view),
              "configuration": configuration,
              "input_text": view["input_text"],
              "stage1_sha256": sha_of(view["stage1"]),
              "stage2_sha256": sha_of(view["stage2"]),
              "base_theory_sha256": sha_of(view["final_clauses"]),
              "base_clause_count": len(view["final_clauses"]),
              "system_prompt_name": SYSTEM_PROMPT_NAME,
              "system_prompt_sha256": PR52.system_prompt_sha256(),
              "conservative": front, "trace": trace,
              "dynamic_work_done": False, "weight_policy": WEIGHT_POLICY,
              "limits": {"base_rules_per_call": MAX_BASE_RULES_PER_CALL,
                         "accumulated_hypotheses": hypothesis_cap,
                         "exclusion_worlds": MAX_EXCLUSION_WORLDS,
                         "user_message_chars": PR52.MAX_USER_MESSAGE_CHARS}}
    if front["resolved"]:
        trace.append({"stage": "stopped",
                      "why": "the conservative front door answered %r; no "
                             "abstraction LLM call and no dynamic gk call were "
                             "made" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "question_split"})
    preflight = Q52.question_preflight(view)
    result["question_preflight"] = preflight
    if not preflight["llm_call_allowed"]:
        trace.append({"stage": "stopped", "why": preflight["why_refused"]})
        result["stopped_at"] = "question_split_refused"
        return result

    trace.append({"stage": "candidates"})
    built = PR52.build_candidates(view, configuration)
    vocab = P52.vocabulary(built)
    result["candidates"] = _candidate_record(built)
    result["candidate_vocabulary"] = {
        "predicates": vocab["predicates"],
        "content_ids": vocab["content_ids"],
        "grounding_atoms": [g["id"] for g in vocab["grounding_atoms"]],
        "policy": vocab["policy"]}
    if not built["groups"]:
        trace.append({"stage": "stopped",
                      "why": "no positive atom of this case is displayable and "
                             "writable as a bridge"})
        result["stopped_at"] = "no_candidate"
        return result

    source_rules = SP.stage2_source_rules(view["stage2"])
    rounds, worlds = [], []
    stopped = None

    trace.append({"stage": "round_1"})
    message = PR52.build_initial_user_prompt(view, built)
    if message["exceeds_size_guard"]:
        trace.append({"stage": "stopped", "why": message["why_refused"]})
        result["stopped_at"] = "user_message_too_large"
        result["refused_message"] = {"chars": message["chars"],
                                     "sha256": message["sha256"]}
        return result
    text, note = respond("rules", "%s/r1" % case_id, message["text"])
    parsed = P52.parse_response(text, vocab, source_rules,
                               max_rules=MAX_BASE_RULES_PER_CALL)
    rules = list(parsed["accepted"])
    rounds.append(_round_record(1, "initial", message, text, note, parsed))
    first_world = None
    if rules and budget():
        pool, dropped = order_hypotheses(rules, cap=hypothesis_cap)
        first_world, _w = run_world(view, pool, gk, configuration,
                                    "round1_%s" % case_id,
                                    "%s/round 1" % case_id, sidecar)
        first_world["round"] = 1
        first_world["omitted_by_the_hypothesis_limit"] = dropped
        worlds.append(first_world)
        rounds[-1].update({"bridge_set": [r["rule_id"] for r in pool],
                           "omitted_by_the_hypothesis_limit": dropped,
                           "world_id": first_world["world_id"],
                           "outcome": first_world["outcome"],
                           "dynamic_proofs":
                               len(first_world["dynamic_proofs"])})
    elif not rules:
        rounds[-1]["no_gk_run"] = "the call produced no usable rule"
    else:
        rounds[-1]["no_gk_run"] = "gk budget reached"
        stopped = "gk_budget"

    found = bool(first_world and first_world["dynamic_proofs"])
    result["round_1_bridge_set"] = {
        "world_id": (first_world or {}).get("world_id"),
        "outcome": (first_world or {}).get("outcome"),
        "dynamic_proofs": len((first_world or {}).get("dynamic_proofs") or []),
        "answers": [p["answer"] for p in (first_world or {}).get("proofs")
                    or []],
        "kept_separately": "the accumulated bridge set never replaces this "
                           "result"}

    if do_second_round and not stopped:
        trace.append({"stage": "round_2"})
        refusals = []
        for w in worlds:
            refusals.extend(w.get("refused_by_the_compiler") or [])
        tried = set(rounds[0].get("bridge_set")
                    or [r["rule_id"] for r in rules])
        attempted = [r for r in rules if r["rule_id"] in tried]
        build = (PR52.build_alternative_user_prompt if found
                 else PR52.build_no_proof_user_prompt)
        message2 = build(view, built, attempted, refusals)
        if message2["exceeds_size_guard"]:
            rounds.append({"round": 2, "call": "refused",
                           "why": message2["why_refused"]})
            stopped = stopped or "second_message_too_large"
        else:
            call = "alternative" if found else "no_proof"
            text2, note2 = respond("alternative" if found else "feedback",
                                   "%s/r2" % case_id, message2["text"])
            parsed2 = P52.parse_response(text2, vocab, source_rules,
                                        max_rules=MAX_BASE_RULES_PER_CALL,
                                        start_index=parsed["next_index"],
                                        existing=rules)
            rounds.append(_round_record(2, call, message2, text2, note2,
                                        parsed2))
            rounds[-1]["because"] = (
                "the round-1 bridge set produced a proof citing a bridge"
                if found else
                "the round-1 bridge set produced no proof citing a bridge")
            # an unreadable or empty reply removes nothing
            rules = rules + list(parsed2["accepted"])
            if parsed2["accepted"] and budget():
                pool, dropped = order_hypotheses(rules, cap=hypothesis_cap)
                world, _w = run_world(view, pool, gk, configuration,
                                      "accumulated_%s" % case_id,
                                      "%s/accumulated" % case_id, sidecar)
                world["round"] = 2
                world["omitted_by_the_hypothesis_limit"] = dropped
                worlds.append(world)
                rounds[-1].update({"bridge_set": [r["rule_id"] for r in pool],
                                   "omitted_by_the_hypothesis_limit": dropped,
                                   "world_id": world["world_id"],
                                   "outcome": world["outcome"],
                                   "dynamic_proofs":
                                       len(world["dynamic_proofs"])})
            elif not parsed2["accepted"]:
                rounds[-1]["no_gk_run"] = (
                    "the second call added no new rule; the round-1 rules and "
                    "any round-1 proof are untouched")
            else:
                rounds[-1]["no_gk_run"] = "gk budget reached"
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
