"""The v6 signed runtime with the v6.1 mechanical fixes wired in.

Four changes, and nothing else about the procedure moves:

**WP1-WP3** the exact-template compiler and the polarity-checking parser
replace their v6 counterparts.

**WP4** one narrow negative-relation channel runs beside the distinctness
channel.  It offers at most six `A -> NOT B` pairs built from displayed
templates, the model only selects ids, and the rules it produces then follow the
ordinary compilation, submission, citation and minimisation path.

**WP5** the second bridge-building call is skipped when the first submission
already proved something citing a bridge.  Replay, minimisation and the
exclusion search still run over the first call's rules.  A proof from the
distinctness or negative-relation channel counts as a first-submission proof.
`ask_for_an_alternative_after_a_proof` restores the old behaviour and defaults
to false.

**WP6** a translation that failed is stopped before bridge generation instead of
being carried into it, and is never counted as an abstention.  One bounded
correction attempt is made first; `translation_repair_v6_1` owns that.
"""

import contextlib
import json

import negative_relation_v6_1 as NR
import simple_rule_compiler_v6_1 as C61
import simple_rule_compiler_v6_signed as C6
import simple_rule_parser as SP
import simple_rule_parser_v6_1 as P61
import translation_repair_v6_1 as TR
import unifier_distinctness_v5_3 as DX
import unifier_feedback_v6_signed as FB6
import unifier_prompt_v6_1 as PR61
import unifier_runtime_v3 as U3
import unifier_runtime_v5_4 as U54
import unifier_runtime_v6_signed as U6

VERSION = "unifier_runtime_v6_1/1.0"

SYSTEM_PROMPT_NAME = PR61.SYSTEM_PROMPT_NAME
MAX_BASE_RULES_PER_CALL = U6.MAX_BASE_RULES_PER_CALL
MAX_ACCUMULATED_HYPOTHESES = U6.MAX_ACCUMULATED_HYPOTHESES
MAX_EXCLUSION_WORLDS = U6.MAX_EXCLUSION_WORLDS
WEIGHT = U6.WEIGHT
WEIGHT_POLICY = U6.WEIGHT_POLICY
FRONT_DOOR_POLICY = U6.FRONT_DOOR_POLICY

sha_of = U6.sha_of
run_world = U6.run_world
minimise = U6.minimise
exclusion_search = U6.exclusion_search
order_hypotheses = U6.order_hypotheses
distinct_sets = U6.distinct_sets
front_door = U6.front_door

SECOND_CALL_SKIPPED = "first_submission_proved"
DIAGNOSTIC_OPTION = "ask_for_an_alternative_after_a_proof"


@contextlib.contextmanager
def v6_1_binding():
    """Compile through the exact-template compiler for one case."""
    before_c, before_fb = U54.C53, U54.FB
    U54.C53, U54.FB = C61, FB6
    try:
        yield
    finally:
        U54.C53, U54.FB = before_c, before_fb


def bindings_are_clean():
    import simple_rule_compiler_v5_3 as C53
    import unifier_feedback_v5_4 as FB54
    return U54.C53 is C53 and U54.FB is FB54


def component_hashes():
    got = dict(U6.component_hashes())
    import hashlib
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("simple_rule_parser_v6_1", "simple_rule_compiler_v6_1",
                 "unifier_prompt_v6_1", "negative_relation_v6_1",
                 "translation_repair_v6_1", "unifier_runtime_v6_1"):
        path = os.path.join(here, "%s.py" % name)
        got[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    got[PR61.SYSTEM_PROMPT_NAME] = PR61.system_prompt_sha256()
    got[NR.SYSTEM_PROMPT_NAME] = NR.system_prompt_sha256()
    return got


def _round_record(n, call, message, text, note, parsed):
    got = U6._round_record(n, call, message, text, note, parsed)
    got["polarity_refusals"] = parsed.get("polarity_refusals") or []
    return got


def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             hypothesis_cap=MAX_ACCUMULATED_HYPOTHESES, do_second_round=True,
             do_exclusions=True, do_distinctness=True,
             do_negative_relations=True,
             ask_for_an_alternative_after_a_proof=False, repair=None):
    with v6_1_binding():
        return _run_case(view, respond, gk, bounds, configuration, sidecar,
                         hypothesis_cap, do_second_round, do_exclusions,
                         do_distinctness, do_negative_relations,
                         ask_for_an_alternative_after_a_proof, repair)


def _run_case(view, respond, gk, bounds, configuration, sidecar,
              hypothesis_cap, do_second_round, do_exclusions, do_distinctness,
              do_negative_relations, ask_after_proof, repair):
    PR61.check_fixed_inputs()
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "translation"}]
    result = {"case_id": case_id, "mode": "unifier_v6_1", "version": VERSION,
              "configuration": configuration,
              "input_text": view["input_text"],
              "system_prompt_name": SYSTEM_PROMPT_NAME,
              "system_prompt_sha256": PR61.system_prompt_sha256(),
              "parser_version": P61.VERSION,
              "compiler_version": C61.VERSION,
              "negative_relation_channel": NR.VERSION,
              "front_door_policy": FRONT_DOOR_POLICY,
              "trace": trace, "dynamic_work_done": False,
              "weight_policy": WEIGHT_POLICY,
              "limits": {"base_rules_per_call": MAX_BASE_RULES_PER_CALL,
                         "premises_per_rule": P61.MAX_BODY_LITERALS,
                         "accumulated_hypotheses": hypothesis_cap,
                         "exclusion_worlds": MAX_EXCLUSION_WORLDS,
                         "negative_relation_pairs": NR.MAX_PAIRS,
                         DIAGNOSTIC_OPTION: ask_after_proof}}

    # ---- WP6: a broken translation stops here, after one repair attempt
    status = TR.status_of(view)
    result["translation_status"] = status
    if not status["usable"]:
        trace.append({"stage": "translation_repair", "why": status["why"]})
        got = repair(view, status) if repair else TR.no_repair(status)
        result["translation_repair"] = got
        if not got.get("usable"):
            trace.append({"stage": "stopped",
                          "why": "the translation failed and one bounded "
                                 "correction did not fix it"})
            result["stopped_at"] = TR.TRANSLATION_FAILURE
            result["translation_failure"] = True
            result["grading"] = {"asked": False, "grades": {}}
            return result
        view = got["view"]
        result["translation_repaired"] = True

    result["view_sha256"] = __import__("dynamic_runtime").view_hash(view)
    result["stage1_sha256"] = sha_of(view["stage1"])
    result["stage2_sha256"] = sha_of(view["stage2"])
    result["base_theory_sha256"] = sha_of(view["final_clauses"])
    result["base_clause_count"] = len(view["final_clauses"])

    trace.append({"stage": "front_door"})
    front = front_door(view, gk)
    result["conservative"] = front
    if front["resolved"]:
        trace.append({"stage": "stopped",
                      "why": "the conservative front door answered %r; no "
                             "abstraction LLM call and no dynamic gk call were "
                             "made" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "question_split"})
    preflight = PR61.question_preflight(view)
    result["question_preflight"] = preflight
    if not preflight["llm_call_allowed"]:
        trace.append({"stage": "stopped", "why": preflight["why_refused"]})
        result["stopped_at"] = "question_split_refused"
        return result
    split = PR61.split_case_text(view)
    view["_split"] = split

    trace.append({"stage": "candidates"})
    complete = PR61.complete_inventory(view, configuration)
    built = PR61.build_candidates(view, configuration, complete)
    built["case_id"] = case_id
    PR61.relabel(built)
    main_ids = built["main_ids"]
    vocab = P61.vocabulary({"groups": PR61.vocabulary_rows(built)})
    result["candidates"] = U54._candidate_record(built)
    result["candidates"]["main_atoms"] = sorted(main_ids)
    result["candidates"]["helper_atoms"] = sorted(built["helper_ids"])
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
    message = PR61.build_initial_user_prompt(view, built)
    if message["exceeds_size_guard"]:
        trace.append({"stage": "stopped", "why": message["why_refused"]})
        result["stopped_at"] = "user_message_too_large"
        return result
    text, note = respond("rules", "%s/r1" % case_id, message["text"])
    parsed = P61.parse_response(text, vocab, main_ids, source_rules,
                               max_rules=MAX_BASE_RULES_PER_CALL)
    rules = list(parsed["accepted"])
    rounds.append(_round_record(1, "initial", message, text, note, parsed))

    if do_distinctness:
        trace.append({"stage": "distinctness"})
        got = DX.run(view, built, split["question"], respond, case_id,
                     start_index=parsed["next_index"])
        result["distinctness"] = dict((k, v) for k, v in got.items()
                                      if k != "rules")
        result["distinctness"]["rule_ids"] = [r["rule_id"]
                                              for r in got["rules"]]
        rules = rules + got["rules"]
        parsed["next_index"] = got.get("next_index", parsed["next_index"])

    if do_negative_relations:
        trace.append({"stage": "negative_relations"})
        got = NR.run(view, built, split["passage"], split["question"],
                     respond, case_id, start_index=parsed["next_index"],
                     source_rules=source_rules)
        result["negative_relations"] = dict((k, v) for k, v in got.items()
                                            if k != "rules")
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
                    or []]}

    # ---- WP5: the second call happens only when the first proved nothing
    if found and not ask_after_proof:
        result["second_call_skipped"] = SECOND_CALL_SKIPPED
        trace.append({"stage": "second_call_skipped",
                      "why": "the first submission proved something citing a "
                             "bridge; replay, minimisation and the exclusion "
                             "search still run"})
        do_second_round = False

    if do_second_round and not stopped:
        trace.append({"stage": "round_2"})
        tried = [r for r in rules
                 if r["rule_id"] in set(rounds[0].get("bridge_set")
                                        or [x["rule_id"] for x in rules])]
        first_hypotheses = U54._with_clauses(first_world)
        if not found:
            message2 = PR61.build_no_proof_user_prompt(view, built, tried)
            role = "feedback"
        else:
            cited = set()
            for p in (first_world or {}).get("dynamic_proofs") or []:
                cited |= set(x for x in p["cited_rules"] if x)
            offered = set(rounds[0].get("bridge_set") or [])
            message2 = PR61.build_alternative_user_prompt(
                view, built, [r for r in rules if r["rule_id"] in cited],
                [r for r in rules
                 if r["rule_id"] in offered and r["rule_id"] not in cited])
            role = "alternative"
            result["proof_used_rules"] = sorted(cited)
        if message2["exceeds_size_guard"]:
            rounds.append({"round": 2, "call": "refused",
                           "why": message2["why_refused"]})
            stopped = stopped or "second_message_too_large"
        else:
            text2, note2 = respond(role, "%s/r2" % case_id, message2["text"])
            parsed2 = P61.parse_response(
                text2, vocab, main_ids, source_rules,
                max_rules=MAX_BASE_RULES_PER_CALL,
                start_index=parsed["next_index"], existing=rules,
                tried=[r["canonical"] for r in rules])
            rounds.append(_round_record(2, message2["call"], message2, text2,
                                        note2, parsed2))
            new_rules = list(parsed2["accepted"])
            rules = rules + new_rules
            if new_rules:
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
                pool_b = FB6.order_by_chain(
                    new_rules, (result.get("chain_status") or {}).get(
                        "second_only"))
                pool_b, dropped_b, order_b = order_hypotheses(
                    pool_b, cap=hypothesis_cap)
                world_b, _w = run_world(view, pool_b, gk, configuration,
                                        built["groups"],
                                        "B_second_only_%s" % case_id,
                                        "%s/B second only" % case_id, sidecar)
                world_b.update({"round": 2, "submission": "B_second_only",
                                "ordering": order_b})
                worlds.append(world_b)
                rounds[-1]["B_second_only"] = {
                    "bridge_set": [r["rule_id"] for r in pool_b],
                    "world_id": world_b["world_id"],
                    "outcome": world_b["outcome"],
                    "dynamic_proofs": len(world_b["dynamic_proofs"])}
            if new_rules and budget():
                ordered = FB6.order_by_chain(
                    rules, (result.get("chain_status") or {}).get(
                        "accumulated"))
                pool, dropped, order = order_hypotheses(ordered,
                                                        cap=hypothesis_cap)
                world, _w = run_world(view, pool, gk, configuration,
                                      built["groups"],
                                      "C_accumulated_%s" % case_id,
                                      "%s/C accumulated" % case_id, sidecar)
                world.update({"round": 2, "submission": "C_accumulated",
                              "ordering": order})
                worlds.append(world)
                rounds[-1].update({"bridge_set": [r["rule_id"] for r in pool],
                                   "world_id": world["world_id"],
                                   "outcome": world["outcome"],
                                   "dynamic_proofs":
                                       len(world["dynamic_proofs"])})
            elif not parsed2["accepted"]:
                rounds[-1]["no_gk_run"] = "the second call added no new rule"

    result["rounds"] = rounds
    result["rules"] = [dict(U3._rule_record(r), meaning=r.get("meaning", ""),
                            head_sign=r.get("head_sign",
                                            r["head"]["sign"]
                                            if r.get("head") else "+"),
                            negative_conclusion=bool(
                                r.get("negative_conclusion")
                                or (r.get("head") or {}).get("sign") == "-"))
                       for r in rules]
    result["worlds"] = [U3._world_record(w) for w in worlds]
    result["compiler_routes"] = dict(
        (h["rule_id"], h.get("compiler_route"))
        for w in worlds for h in w.get("bridge_hypotheses") or [])
    result["discarded_tautological_auxiliaries"] = [
        row for w in worlds
        for row in (w.get("discarded_tautological_auxiliaries") or [])]
    negative = [r for r in result["rules"] if r["negative_conclusion"]]
    result["signed"] = {
        "by_case": {"rules": len(result["rules"]),
                    "negative_conclusion": len(negative),
                    "positive_conclusion": len(result["rules"]) - len(negative),
                    "negative_rule_ids": [r["rule_id"] for r in negative],
                    "negative_printed": [r["printed"] for r in negative],
                    "from_the_negative_relation_channel": [
                        r["rule_id"] for r in result["rules"]
                        if r.get("origin") == NR.ORIGIN]},
        "by_call": dict((r["call"], r.get("signed_counts"))
                        for r in rounds if r.get("signed_counts"))}
    rules_by_id = dict((r["rule_id"], r) for r in rules)

    seen, distinct = {}, []
    for w in worlds:
        for p in w["proofs"]:
            key = (json.dumps(p["answer"], default=str),
                   tuple(sorted(p["cited_rules"])))
            if key in seen:
                seen[key]["submissions"].append(w.get("submission"))
                continue
            row = dict(p, world_id=w["world_id"], round=w.get("round"),
                       submission=w.get("submission"),
                       submissions=[w.get("submission")])
            seen[key] = row
            distinct.append(row)
    result["returned_proofs"] = [{k: v for k, v in p.items() if k != "proof"}
                                 for p in distinct]
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
    for m in result["minimisation"]:
        ids = m.get("minimal_rules") or m.get("cited_rules") or []
        m["printed_rules"] = [(rules_by_id.get(rid) or {}).get("printed")
                              for rid in ids]
        m["negative_conclusion_rules"] = [
            rid for rid in ids
            if (rules_by_id.get(rid) or {}).get("head", {}).get("sign") == "-"]
    result["proof_used_negative_rules"] = sorted(set(
        rid for m in result["minimisation"]
        for rid in m["negative_conclusion_rules"]))
    result["grading"] = {"asked": False, "grades": {}}
    result["stopped_at"] = stopped
    return result
