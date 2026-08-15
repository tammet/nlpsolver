"""The AL-92 procedure with one change: the generation conversation.

Everything that decides what gk sees is v5.4's, called through v5.4's own
functions — the conservative front door, the complete candidate inventory, the
compiler, `run_world`, the three separate submissions, deletion minimisation,
the exact replay and the bounded exclusion search.  The distinctness channel and
the internal chain calculation that orders the B and C submissions are kept for
the same reason: a difference in the result should be a difference in the
prompt.

What changes:

  * every generation call uses the approved v5.9 system prompt, byte-for-byte;
  * the case message shows `MAIN ATOMS` and `HELPER ATOMS` with no provenance,
    no supplier category and no unreached-question section;
  * the reply must be `MEANING:`/`RULE:` blocks, or `NO_RULE`;
  * a rule must use at least one main atom.

The post-proof assessment is not run here.  It happens after the record is
closed, in a separate program, with the frozen v5.6.1 configuration.
"""

import json

import simple_rule_parser as SP
import simple_rule_parser_v5_9 as P59
import unifier_distinctness_v5_3 as DX
import unifier_feedback_v5_4 as FB
import unifier_prompt_v5_9 as PR59
import unifier_runtime as UR
import unifier_runtime_v3 as U3
import unifier_runtime_v5_4 as U54

VERSION = "unifier_runtime_v5_9/1.0"

SYSTEM_PROMPT_NAME = PR59.SYSTEM_PROMPT_NAME
MAX_BASE_RULES_PER_CALL = U54.MAX_BASE_RULES_PER_CALL
MAX_ACCUMULATED_HYPOTHESES = U54.MAX_ACCUMULATED_HYPOTHESES
MAX_EXCLUSION_WORLDS = U54.MAX_EXCLUSION_WORLDS
WEIGHT = U54.WEIGHT
WEIGHT_POLICY = U54.WEIGHT_POLICY

sha_of = U54.sha_of
run_world = U54.run_world
minimise = U54.minimise
exclusion_search = U54.exclusion_search
order_hypotheses = U54.order_hypotheses
distinct_sets = U54.distinct_sets
classify_gk = U54.classify_gk


def component_hashes():
    """Every source whose change would make this run incomparable."""
    got = dict(U54.component_hashes())
    import hashlib
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("unifier_prompt_v5_9", "simple_rule_parser_v5_9",
                 "unifier_runtime_v5_9"):
        path = os.path.join(here, "%s.py" % name)
        got[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    got[PR59.SYSTEM_PROMPT_NAME] = PR59.system_prompt_sha256()
    return got


def _round_record(n, call, message, text, note, parsed):
    got = U54._round_record(n, call, message, text, note, parsed)
    got.update({"readable_blocks": parsed.get("readable_blocks"),
                "said_no_rule": parsed.get("said_no_rule"),
                "meanings": parsed.get("meanings"),
                "format_refusals": parsed.get("format_refusals"),
                "blocks": parsed.get("blocks")})
    got["accepted"] = [dict(a, meaning=a.get("meaning", ""))
                       for a in got.get("accepted") or []]
    return got


def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             hypothesis_cap=MAX_ACCUMULATED_HYPOTHESES, do_second_round=True,
             do_exclusions=True, do_distinctness=True):
    """One case, front door to minimal proof sets.  No assessment call."""
    PR59.check_fixed_inputs()
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    import dynamic_runtime as RT
    front = RT.front_door(view, gk)
    result = {"case_id": case_id, "mode": "unifier_v5_9", "version": VERSION,
              "view_sha256": RT.view_hash(view),
              "configuration": configuration,
              "input_text": view["input_text"],
              "stage1_sha256": sha_of(view["stage1"]),
              "stage2_sha256": sha_of(view["stage2"]),
              "base_theory_sha256": sha_of(view["final_clauses"]),
              "base_clause_count": len(view["final_clauses"]),
              "system_prompt_name": SYSTEM_PROMPT_NAME,
              "system_prompt_sha256": PR59.system_prompt_sha256(),
              "conservative": front, "trace": trace,
              "dynamic_work_done": False, "weight_policy": WEIGHT_POLICY,
              "limits": {"base_rules_per_call": MAX_BASE_RULES_PER_CALL,
                         "premises_per_rule": P59.MAX_BODY_LITERALS,
                         "accumulated_hypotheses": hypothesis_cap,
                         "exclusion_worlds": MAX_EXCLUSION_WORLDS,
                         "user_message_chars": PR59.MAX_USER_MESSAGE_CHARS}}
    if front["resolved"]:
        trace.append({"stage": "stopped",
                      "why": "the conservative front door answered %r; no "
                             "abstraction LLM call and no dynamic gk call were "
                             "made" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "question_split"})
    preflight = PR59.question_preflight(view)
    result["question_preflight"] = preflight
    if not preflight["llm_call_allowed"]:
        trace.append({"stage": "stopped", "why": preflight["why_refused"]})
        result["stopped_at"] = "question_split_refused"
        return result
    split = PR59.split_case_text(view)
    view["_split"] = split

    trace.append({"stage": "candidates"})
    complete = PR59.complete_inventory(view, configuration)
    built = PR59.build_candidates(view, configuration, complete)
    built["case_id"] = case_id
    PR59.relabel(built)
    main_ids = built["main_ids"]
    vocab = P59.vocabulary({"groups": PR59.vocabulary_rows(built)})
    result["candidates"] = U54._candidate_record(built)
    result["candidates"]["main_atoms"] = sorted(main_ids)
    result["candidates"]["helper_atoms"] = sorted(built["helper_ids"])
    result["candidate_vocabulary"] = {
        "predicates": vocab["predicates"], "content_ids": vocab["content_ids"],
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
    message = PR59.build_initial_user_prompt(view, built)
    if message["exceeds_size_guard"]:
        trace.append({"stage": "stopped", "why": message["why_refused"]})
        result["stopped_at"] = "user_message_too_large"
        result["refused_message"] = {"chars": message["chars"],
                                     "sha256": message["sha256"]}
        return result
    text, note = respond("rules", "%s/r1" % case_id, message["text"])
    parsed = P59.parse_response(text, vocab, main_ids, source_rules,
                                max_rules=MAX_BASE_RULES_PER_CALL)
    rules = list(parsed["accepted"])
    rounds.append(_round_record(1, "initial", message, text, note, parsed))

    if do_distinctness:
        trace.append({"stage": "distinctness"})
        got = DX.run(view, built, split["question"], respond, case_id,
                     start_index=parsed["next_index"])
        result["distinctness"] = dict(
            (k, v) for k, v in got.items() if k != "rules")
        result["distinctness"]["rule_ids"] = [r["rule_id"]
                                              for r in got["rules"]]
        rules = rules + got["rules"]
        parsed["next_index"] = got.get("next_index", parsed["next_index"])

    first_world = None
    if rules and budget():
        pool, dropped, order = order_hypotheses(rules, cap=hypothesis_cap)
        first_world, _w = run_world(view, pool, gk, configuration,
                                    built["groups"],
                                    "A_first_only_%s" % case_id,
                                    "%s/A first only" % case_id, sidecar)
        first_world["round"] = 1
        first_world["submission"] = "A_first_only"
        first_world["omitted_by_the_hypothesis_limit"] = dropped
        first_world["ordering"] = order
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
        tried = [r for r in rules
                 if r["rule_id"] in set(rounds[0].get("bridge_set")
                                        or [x["rule_id"] for x in rules])]
        first_hypotheses = U54._with_clauses(first_world)
        if not found:
            message2 = PR59.build_no_proof_user_prompt(view, built, tried)
            role = "feedback"
        else:
            cited = set()
            for p in (first_world or {}).get("dynamic_proofs") or []:
                cited |= set(x for x in p["cited_rules"] if x)
            offered = set(rounds[0].get("bridge_set") or [])
            cited_rules = [r for r in rules if r["rule_id"] in cited]
            unused = [r for r in rules
                      if r["rule_id"] in offered and r["rule_id"] not in cited]
            message2 = PR59.build_alternative_user_prompt(view, built,
                                                          cited_rules, unused)
            role = "alternative"
            result["proof_used_rules"] = sorted(cited)
        if message2["exceeds_size_guard"]:
            rounds.append({"round": 2, "call": "refused",
                           "why": message2["why_refused"]})
            stopped = stopped or "second_message_too_large"
        else:
            text2, note2 = respond(role, "%s/r2" % case_id, message2["text"])
            parsed2 = P59.parse_response(
                text2, vocab, main_ids, source_rules,
                max_rules=MAX_BASE_RULES_PER_CALL,
                start_index=parsed["next_index"], existing=rules,
                tried=[r["canonical"] for r in rules])
            rounds.append(_round_record(2, message2["call"], message2, text2,
                                        note2, parsed2))
            rounds[-1]["because"] = (
                "the round-1 bridge set produced a proof citing a bridge"
                if found else
                "the round-1 bridge set produced no proof citing a bridge")
            new_rules = list(parsed2["accepted"])
            rules = rules + new_rules
            if new_rules:
                # computed to order B and C exactly as AL-92 did; it is never
                # shown to the model in this version
                result["chain_status"] = U54._chain_records(
                    view, configuration, built, new_rules, first_hypotheses,
                    case_id)
                result["chain_status"]["shown_to_the_model"] = False
                for r in new_rules:
                    got = (result["chain_status"]["second_only"]
                           .get(r["rule_id"]) or {})
                    r["chain_status"] = got.get("status")
                    r["chain_after"] = got.get("after")
            if new_rules and budget():
                pool_b = FB.order_by_chain(
                    new_rules, (result.get("chain_status") or {}).get(
                        "second_only"))
                pool_b, dropped_b, order_b = order_hypotheses(
                    pool_b, cap=hypothesis_cap)
                world_b, _w = run_world(view, pool_b, gk, configuration,
                                        built["groups"],
                                        "B_second_only_%s" % case_id,
                                        "%s/B second only" % case_id, sidecar)
                world_b["round"] = 2
                world_b["submission"] = "B_second_only"
                world_b["omitted_by_the_hypothesis_limit"] = dropped_b
                world_b["ordering"] = order_b
                worlds.append(world_b)
                rounds[-1]["B_second_only"] = {
                    "bridge_set": [r["rule_id"] for r in pool_b],
                    "world_id": world_b["world_id"],
                    "outcome": world_b["outcome"],
                    "dynamic_proofs": len(world_b["dynamic_proofs"])}
            if new_rules and budget():
                ordered = FB.order_by_chain(
                    rules, (result.get("chain_status") or {}).get(
                        "accumulated"))
                pool, dropped, order = order_hypotheses(ordered,
                                                        cap=hypothesis_cap)
                world, _w = run_world(view, pool, gk, configuration,
                                      built["groups"],
                                      "C_accumulated_%s" % case_id,
                                      "%s/C accumulated" % case_id, sidecar)
                world["round"] = 2
                world["submission"] = "C_accumulated"
                world["omitted_by_the_hypothesis_limit"] = dropped
                world["ordering"] = order
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
    result["rules"] = [dict(U3._rule_record(r), meaning=r.get("meaning", ""))
                       for r in rules]
    result["worlds"] = [U3._world_record(w) for w in worlds]
    result["compiler_routes"] = dict(
        (h["rule_id"], h.get("compiler_route"))
        for w in worlds for h in w.get("bridge_hypotheses") or [])
    rules_by_id = dict((r["rule_id"], r) for r in rules)

    seen, distinct = {}, []
    for w in worlds:
        for p in w["proofs"]:
            key = (json.dumps(p["answer"], default=str),
                   tuple(sorted(p["cited_rules"])))
            if key in seen:
                seen[key]["submissions"].append(w.get("submission")
                                                or w["world_id"])
                continue
            row = dict(p, world_id=w["world_id"], round=w.get("round"),
                       submission=w.get("submission"),
                       submissions=[w.get("submission") or w["world_id"]])
            seen[key] = row
            distinct.append(row)
    result["returned_proofs"] = [{k: v for k, v in p.items() if k != "proof"}
                                 for p in distinct]
    result["answers_with_no_cited_hypothesis"] = [
        p["answer"] for p in distinct if p["cites_no_dynamic_hypothesis"]]
    dynamic = [p for p in distinct if not p["cites_no_dynamic_hypothesis"]]
    if not dynamic:
        trace.append({"stage": "stopped", "why": "no proof cited a bridge"})
        result["stopped_at"] = stopped or U3._no_proof_reason(worlds, rules)
        result["grading"] = {"asked": False, "grades": {}}
        return result

    trace.append({"stage": "minimise"})
    minimal = []
    for p in dynamic:
        m = minimise(view, gk, configuration, built["groups"], case_id,
                     rules_by_id, p, budget, "p%d" % (len(minimal) + 1),
                     sidecar)
        m.update({"answer": p["answer"],
                  "gk_native_confidence": p["gk_native_confidence"],
                  "world_id": p["world_id"], "round": p.get("round"),
                  "submission": p.get("submission"),
                  "submissions": p.get("submissions"),
                  "found_by_excluding": None})
        minimal.append(m)

    if do_exclusions and minimal:
        trace.append({"stage": "exclusions"})
        first = minimal[0].get("minimal_rules") or minimal[0]["cited_rules"]
        result["exclusions"] = exclusion_search(
            view, gk, configuration, built["groups"], case_id, list(rules),
            rules_by_id, first, budget, sidecar)
        for row in result["exclusions"]:
            for m in row.get("minimised") or []:
                minimal.append(m)
    result["minimisation"] = distinct_sets(minimal)
    result["distinct_minimal_sets"] = sorted(set(
        tuple(sorted(m.get("minimal_rules") or m.get("cited_rules") or []))
        for m in result["minimisation"]))
    result["grading"] = {"asked": False, "grades": {},
                         "note": "the assessment runs after this record is "
                                 "closed, in a separate program"}
    result["stopped_at"] = stopped
    return result
