"""The v5.4 literal-bridge pipeline: one changed call, three submissions.

Everything is `unifier_runtime_v5_3`'s -- the front door, the initial call, the
alternative call, the positive grammar, source aliases, the eventprop
generalisation, the distinctness channel, fixed constants, the clause-native
fallback, full-confidence defeasible clauses with `$block`, post-gk weighting,
citation checks, minimisation and the exclusion search -- with two changes the
plan asks for and nothing else:

  * **the no-proof second message is `unifier_prompt_v5_4`'s.**  It no longer
    names the question literals no rule reached, no longer says which conclusion
    could reach one, and no longer asks the model to derive one.  It reports why
    each first rule could not start, labels every possible supplier with one
    honest category, and asks for a chain that can START;

  * **three gk submissions are run and stored separately.**  `A_first_only` is
    the first bridge set, `B_second_only` is the new second-call bridges alone,
    and `C_accumulated` is both.  B is a diagnostic measurement: it shows
    whether a second call introduced a false rule or merely activated one from
    the first call, which the accumulated submission alone hides.

A rule that cannot start is never deleted for that reason.  It is ordered last
and recorded as explicitly speculative.
"""

import hashlib
import json
import os

import bridge_world as BW
import dynamic_runtime as RT
import rule_redundancy_v3 as RR
import simple_rule_compiler_v5_3 as C53
import simple_rule_parser as SP
import simple_rule_parser_v5_3 as P53
import unifier_distinctness_v5_3 as DX
import unifier_feedback_v5_3 as FB53
import unifier_feedback_v5_4 as FB
import unifier_grader_v5_4 as GR
import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_3 as PR53
import unifier_prompt_v5_4 as PR54
import unifier_question_v5_2 as Q52
import unifier_runtime as UR
import unifier_runtime_v3 as U3
import unifier_runtime_v4 as U4

VERSION = "unifier_runtime_v5_4/1.0"

ROOT = U3.ROOT

GRADE_PROMPT = U4.GRADE_PROMPT
SYSTEM_PROMPT_NAME = P51.SYSTEM_PROMPT_NAME

MAX_BASE_RULES_PER_CALL = P53.MAX_BASE_RULES_PER_CALL
MAX_ACCUMULATED_HYPOTHESES = 30
MAX_EXCLUSION_WORLDS = U4.MAX_EXCLUSION_WORLDS

WEIGHT = U4.WEIGHT
WEIGHT_POLICY = U4.WEIGHT_POLICY
UNASSESSED = U4.UNASSESSED

sha_of = U3.sha_of
classify_gk = U3.classify_gk
distinct_sets = U3.distinct_sets
worst_grade = U3.worst_grade
grade_rules = U4.grade_rules


class RuntimeError_(U4.RuntimeError_):
    pass


def component_hashes():
    out = dict(U4.component_hashes())
    for mod in ("unifier_prompt_v5_1", "unifier_prompt_v5_2",
                "unifier_prompt_v5_3", "unifier_question_v5_2",
                "simple_rule_parser_v5_1", "simple_rule_parser_v5_2",
                "simple_rule_parser_v5_3", "simple_rule_compiler_v5_3",
                "unifier_feedback_v5_3", "unifier_distinctness_v5_3",
                "unifier_runtime_v5_2", "unifier_runtime_v5_3",
                "unifier_feedback_v5_4", "unifier_prompt_v5_4",
                "unifier_grader_v5_4", "unifier_runtime_v5_4"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    out["prompts/dynamic_alignment/%s.txt" % SYSTEM_PROMPT_NAME] = \
        PR53.system_prompt_sha256()
    out["prompts/dynamic_alignment/%s.txt" % DX.SYSTEM_PROMPT_NAME] = \
        DX.system_prompt_sha256()
    out["memos/EXAMPLE_2026_08_13_clear_literal_bridge_prompt.md"] = \
        PR53.example_sha256()
    import unifier_grader_v5_4 as GR
    for name in (GR.RULE_PROMPT_NAME, GR.SET_PROMPT_NAME):
        p = os.path.join(ROOT, "prompts", "dynamic_alignment", "%s.txt" % name)
        out["prompts/dynamic_alignment/%s.txt" % name] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------- the accumulated set

def order_hypotheses(rules, cap=MAX_ACCUMULATED_HYPOTHESES):
    """-> (the rules gk sees, the ones the limit left out, with the reason).

    Model-written base rules first, then the distinctness channel's rule, then
    program-generated specializations.  Inside a block: a body that may start,
    then role fit, then fewer premises, then rule cost, then id.
    """
    def block(r):
        if r.get("origin") == P53.GROUND_SPECIALIZATION:
            return 2
        if r.get("origin") == "distinctness_channel_v5_3":
            return 1
        return 0

    def key(r):
        fit = r.get("role_fit") or {}
        return (block(r),
                0 if r.get("body_may_start") is not False else 1,
                0 if fit.get("fits") else 1,
                r.get("premises", len(r.get("body") or [])),
                r.get("rule_priority_cost", 0),
                int(str(r["rule_id"])[1:] or 0))
    ordered = sorted(rules, key=key)
    kept, dropped = ordered[:cap], ordered[cap:]
    return kept, [{"rule_id": r["rule_id"], "printed": r["printed"],
                   "origin": r.get("origin"),
                   "why": "beyond the %d compiled hypotheses an accumulated "
                          "bridge set may hold; model-written base rules are "
                          "kept first" % cap}
                  for r in dropped], [
        {"rule_id": r["rule_id"], "reason_for_its_place":
         "block %d, body may start %s, role fit %s, %d premises, cost %s"
         % (block(r), r.get("body_may_start"),
            (r.get("role_fit") or {}).get("fits"),
            r.get("premises", len(r.get("body") or [])),
            r.get("rule_priority_cost"))} for r in kept]


# ------------------------------------------------------------------- worlds

def run_world(view, rules, gk, configuration, groups, world_id, tag,
              sidecar=None):
    """Compile a bridge set, append it to the STORED theory, ask gk."""
    world = C53.build_world(world_id, rules, view, configuration,
                            groups=groups, weight=WEIGHT,
                            redundancy=RR.checker(view))
    record = {
        "world_id": world_id, "tag": tag,
        "rules_offered": [r["rule_id"] for r in rules],
        "refused_by_the_compiler": world["refused_by_the_compiler"],
        "hypotheses_offered": world["hypotheses_in_this_world"],
        "compiler_routes": world["compiler_routes"],
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
        record.update({"skipped": "no rule of this set converted to a clause",
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
        "gk_result_string": result, "outcome": outcome, "proofs": proofs,
        "dynamic_proofs": dynamic, "answers_returned": len(proofs),
        "conservative_formatter_answer": got.get("answer"),
        "gk_thresholds": got.get("thresholds"), "seconds": got.get("seconds"),
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


def minimise(view, gk, configuration, groups, case_id, rules_by_id, proof,
             budget, tag, sidecar=None):
    """Replay the cited set, then delete one rule at a time."""
    cited = [rules_by_id[r] for r in proof["cited_rules"] if r in rules_by_id]
    if not cited:
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "why": "the proof cites no dynamic hypothesis"}
    if not budget():
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "why": "gk budget reached before the replay"}
    replay, _w = run_world(view, cited, gk, configuration, groups,
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
        got, _w = run_world(view, trial, gk, configuration, groups,
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
            "replay_world_id": replay["world_id"], "deletions": deletions,
            "note": "deletion-minimal, not globally minimum"}


def exclusion_search(view, gk, configuration, groups, case_id, pool_rules,
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
        got, _w = run_world(view, keep, gk, configuration, groups,
                            "excl_%s_no_%s" % (case_id, rid),
                            "%s/excluding %s" % (case_id, rid), sidecar)
        row = {"excluded": rid,
               "excluded_printed": rules_by_id[rid]["printed"]
               if rid in rules_by_id else None,
               "world_id": got["world_id"], "outcome": got["outcome"],
               "answers": [p["answer"] for p in got["proofs"]],
               "dynamic_proofs": [], "minimised": []}
        for p in got["dynamic_proofs"]:
            m = minimise(view, gk, configuration, groups, case_id, rules_by_id,
                         p, budget, "excl_%s" % rid, sidecar)
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


# ------------------------------------------------------------------ records

def _round_record(n, call, message, text, note, parsed):
    return {
        "round": n, "call": call,
        "system_prompt_name": message["system_prompt_name"],
        "system_prompt_sha256": message["system_prompt_sha256"],
        "user_message": message["text"],
        "user_message_sha256": message["sha256"],
        "user_message_chars": message["chars"],
        "raw": text, "llm_note": note,
        "readable_rule_lines": parsed["readable_lines"],
        "base_rules_accepted": parsed["base_rules_accepted"],
        "generated_specializations_accepted":
            parsed["generated_specializations_accepted"],
        "base_rule_limit": parsed["base_rule_limit"],
        "refused_negative_lines": parsed["refused_negative_lines"],
        "rejections_by_category": parsed["rejections_by_category"],
        "generalisation_notes": parsed["generalisation_notes"],
        "accepted": [{"rule_id": r["rule_id"], "printed": r["printed"],
                      "origin": r["origin"], "warnings": r["warnings"],
                      "premises": r["premises"],
                      "rule_priority_cost": r["rule_priority_cost"],
                      "role_fit": r["role_fit"],
                      "candidate_matches": r["candidate_matches"],
                      "atoms_matching_no_candidate":
                          r["atoms_matching_no_candidate"],
                      "specialization_of": r.get("specialization_of")}
                     for r in parsed["accepted"]],
        "rejected": parsed["rejected"], "over_cap": parsed["over_cap"],
        "rejection_reasons": parsed["rejection_reasons"],
    }


def _candidate_record(built):
    return {
        "version": built["version"], "counts": built["counts"],
        "inventory": built["inventory"],
        "groups_hidden_by_the_old_caps": built["groups_hidden_by_the_old_caps"],
        "displayed": [{"id": g["id"], "section": g["section"],
                       "printed": g["printed"], "role": g["role"],
                       "cost": g["cost"], "compiled_literal": g["literal"],
                       "question_linked": g["question_linked"],
                       "origin_kind": g["origin_kind"],
                       "compiler_route": g["compiler_route"],
                       "source_aliases": g["source_aliases"],
                       "surface_atoms": g["surface_atoms"],
                       "source_candidate_ids": g["source_candidate_ids"],
                       "available_under_the_old_caps":
                           g["available_under_the_old_caps"],
                       "round_trip": g.get("round_trip"),
                       "writability": g.get("writability")}
                      for g in built["groups"]],
        "omitted": built["omitted"],
        "policy": "every positive atom of the complete inventory that is "
                  "displayable and writable is shown, with the source wording "
                  "it was converted from and the clause-native question forms "
                  "the Stage-2 converter cannot express",
    }


def grader_groups(view, complete, built):
    """The displayed atoms with the Stage-1 sentences each was built from.

    A lookup in the inventory this case already built, not a new judgement.
    """
    rows = dict((r["id"], r) for r in complete["main"] + complete["secondary"])
    text_of = {}
    for sent in view.get("stage1") or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            text_of[u.get("unit_id")] = (u.get("text") or "").strip()
    out = []
    for g in built["groups"]:
        mine = dict(g)
        seen, phrases = set(), []
        for rid in g.get("source_candidate_ids") or []:
            for uid in (rows.get(rid) or {}).get("units") or []:
                if uid in seen or uid not in text_of:
                    continue
                seen.add(uid)
                phrases.append({"unit": uid, "text": text_of[uid]})
        mine["source_phrases"] = phrases[:GR.MAX_SOURCE_PHRASES]
        mine["omitted_source_phrases"] = max(0, len(phrases)
                                             - GR.MAX_SOURCE_PHRASES)
        out.append(mine)
    return out


def assess_rules(view, split, rules, displayed, respond, case_id):
    """WP2: one ASSESS block per used rule, with one formatting retry."""
    ids = [r["rule_id"] for r in rules]
    if not ids:
        return {"asked": False, "why": "no rule was used by any proof",
                "assessments": {}}
    message = GR.rule_user_message(view, split, rules, displayed)
    displayed_ids = set(g["id"] for g in displayed)
    text, note = respond("rule_assess", "%s/assess" % case_id, message)
    got = GR.parse_assessments(text, ids, displayed_ids)
    retried = None
    if not got["readable"]:
        retried = "the first reply held no readable ASSESS block"
        text2, _n = respond("rule_assess", "%s/assess2" % case_id,
                            message + "\n\nWrite the ASSESS blocks now, one "
                                      "per rule, and nothing else.")
        got2 = GR.parse_assessments(text2, ids, displayed_ids)
        if got2["readable"]:
            got, text = got2, text2
    return {"asked": True, "user_message": message,
            "user_message_sha256": GR.sha256_of(message),
            "system_prompt_name": GR.RULE_PROMPT_NAME,
            "system_prompt_sha256": GR.sha256_of(GR.rule_system_prompt()),
            "raw": text, "llm_note": note, "retried": retried,
            "assessments": got["assessments"], "rejected": got["rejected"],
            "assessed": got["assessed"], "total": got["total"]}


def assess_sets(view, split, minimal, rules_by_id, assessments, respond,
                case_id):
    """WP3: one SET block per deletion-minimal set of two or more bridges."""
    out = []
    for i, m in enumerate(minimal, start=1):
        ids = m.get("minimal_rules") or m.get("cited_rules") or []
        set_id = "S%d" % i
        if len(ids) < 2:
            out.append({"set_id": set_id, "rules": ids, "asked": False,
                        "assessment": {"value": "COHERENT",
                                       "explicitly_assessed": False,
                                       "note": GR.SINGLE_RULE_SET,
                                       "unsupported_rules": [],
                                       "manufactures": None, "reason": ""}})
            continue
        mine = [rules_by_id[r] for r in ids if r in rules_by_id]
        message = GR.set_user_message(view, split, set_id, mine, assessments)
        text, note = respond("set_assess", "%s/%s" % (case_id, set_id),
                             message)
        out.append({"set_id": set_id, "rules": ids, "asked": True,
                    "user_message": message,
                    "user_message_sha256": GR.sha256_of(message),
                    "raw": text, "llm_note": note,
                    "assessment": GR.parse_set(text, set_id, ids)})
    return out


def _with_clauses(world):
    """The compiled hypotheses of a submission, each with its own clauses."""
    clauses = (world or {}).get("compiled_bridge_clauses") or []
    out = []
    for h in (world or {}).get("bridge_hypotheses") or []:
        mine = dict(h)
        mine["compiled_clauses"] = [c for c in clauses
                                    if c["@name"] in (h.get("clause_names")
                                                      or [])]
        out.append(mine)
    return out


def _chain_records(view, configuration, built, new_rules, first_hypotheses,
                   case_id):
    """WP6: can these new rules start on their own, and with the first ones?

    The rules are compiled once here, with no gk call, only to read the content
    literals of their bodies and heads.
    """
    world = C53.build_world("chain_%s" % case_id, new_rules, view,
                            configuration, groups=built["groups"])
    mine = _with_clauses(world)
    second = FB.chain_status(view, mine)
    accumulated = FB.chain_status(view, mine, extra_hypotheses=first_hypotheses)
    return {"second_only": second["status"],
            "accumulated": accumulated["status"],
            "second_only_search_bound_reached": second["search_bound_reached"],
            "accumulated_search_bound_reached":
                accumulated["search_bound_reached"],
            "refused_by_the_compiler": world["refused_by_the_compiler"],
            "policy": "a rule that cannot start is ordered last and recorded as "
                      "explicitly speculative; it is never deleted for that "
                      "reason"}


# ------------------------------------------------------------------- driver

def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             hypothesis_cap=MAX_ACCUMULATED_HYPOTHESES, do_second_round=True,
             do_exclusions=True, do_grade=True, do_distinctness=True):
    """One case, front door to graded proofs, with everything recorded."""
    PR53.check_fixed_inputs()
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": case_id, "mode": "unifier_v5_4", "version": VERSION,
              "view_sha256": RT.view_hash(view),
              "configuration": configuration,
              "input_text": view["input_text"],
              "stage1_sha256": sha_of(view["stage1"]),
              "stage2_sha256": sha_of(view["stage2"]),
              "base_theory_sha256": sha_of(view["final_clauses"]),
              "base_clause_count": len(view["final_clauses"]),
              "system_prompt_name": SYSTEM_PROMPT_NAME,
              "system_prompt_sha256": PR53.system_prompt_sha256(),
              "conservative": front, "trace": trace,
              "dynamic_work_done": False, "weight_policy": WEIGHT_POLICY,
              "no_proof_prompt_version": PR54.VERSION,
              "connection_report_version": FB.VERSION,
              "limits": {"base_rules_per_call": MAX_BASE_RULES_PER_CALL,
                         "premises_per_rule": P53.MAX_BODY_LITERALS,
                         "accumulated_hypotheses": hypothesis_cap,
                         "exclusion_worlds": MAX_EXCLUSION_WORLDS,
                         "user_message_chars": PR53.MAX_USER_MESSAGE_CHARS}}
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
    split = PR53.split_case_text(view)
    view["_split"] = split

    trace.append({"stage": "candidates"})
    complete = PR54.complete_inventory(view, configuration)
    built = PR54.build_candidates(view, configuration, complete)
    built["case_id"] = case_id
    vocab = P53.vocabulary({"groups": PR53.vocabulary_rows(built)})
    result["candidates"] = _candidate_record(built)
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
    message = PR53.build_initial_user_prompt(view, built)
    if message["exceeds_size_guard"]:
        trace.append({"stage": "stopped", "why": message["why_refused"]})
        result["stopped_at"] = "user_message_too_large"
        result["refused_message"] = {"chars": message["chars"],
                                     "sha256": message["sha256"]}
        return result
    text, note = respond("rules", "%s/r1" % case_id, message["text"])
    parsed = P53.parse_response(text, vocab, source_rules,
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
        refused = []
        for w in worlds:
            refused.extend(w.get("refused_by_the_compiler") or [])
        tried = [r for r in rules
                 if r["rule_id"] in set(rounds[0].get("bridge_set")
                                        or [x["rule_id"] for x in rules])]
        feedback = None
        first_hypotheses = _with_clauses(first_world)
        if not found:
            full = first_hypotheses
            feedback = FB.report(view, full, refused)
            result["connection_report"] = feedback
            first_hypotheses = full
            for r in rules:
                row = [x for x in feedback["rules"]
                       if x["rule_id"] == r["rule_id"]]
                if row:
                    r["body_may_start"] = row[0]["body_may_start"]
            message2 = PR54.build_no_proof_user_prompt(view, built, tried,
                                                       refused, feedback)
            role = "feedback"
        else:
            cited = set()
            for p in (first_world or {}).get("dynamic_proofs") or []:
                cited |= set(x for x in p["cited_rules"] if x)
            offered = set(rounds[0].get("bridge_set") or [])
            cited_rules = [r for r in rules if r["rule_id"] in cited]
            unused = [r for r in rules
                      if r["rule_id"] in offered and r["rule_id"] not in cited]
            message2 = PR53.build_alternative_user_prompt(
                view, built, cited_rules, unused, refused)
            role = "alternative"
            result["proof_used_rules"] = sorted(cited)
        if message2["exceeds_size_guard"]:
            rounds.append({"round": 2, "call": "refused",
                           "why": message2["why_refused"]})
            stopped = stopped or "second_message_too_large"
        else:
            text2, note2 = respond(role, "%s/r2" % case_id, message2["text"])
            parsed2 = P53.parse_response(
                text2, vocab, source_rules,
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
                result["chain_status"] = _chain_records(
                    view, configuration, built, new_rules, first_hypotheses,
                    case_id)
                for r in new_rules:
                    got = (result["chain_status"]["second_only"]
                           .get(r["rule_id"]) or {})
                    r["chain_status"] = got.get("status")
                    r["chain_after"] = got.get("after")
            if new_rules and budget():
                # B: the new rules alone, so an activation of a first-call rule
                # cannot be mistaken for a new one
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
    result["rules"] = [U3._rule_record(r) for r in rules]
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
    if do_grade:
        trace.append({"stage": "assess"})
        displayed = grader_groups(view, complete, built)
        rule_assessment = assess_rules(view, split, used, displayed, respond,
                                       case_id)
        sets = assess_sets(view, split, result["minimisation"], rules_by_id,
                           rule_assessment.get("assessments") or {}, respond,
                           case_id)
        result["assessment"] = {"version": GR.VERSION,
                                "rules": rule_assessment, "sets": sets}
        for m, s in zip(result["minimisation"], sets):
            ids = m.get("minimal_rules") or m.get("cited_rules") or []
            cls, why = GR.trust_class(
                ids, rule_assessment.get("assessments") or {},
                s["assessment"])
            m["trust_class"] = cls
            m["trust_because"] = why
            m["set_assessment"] = s["assessment"]
            m["rule_decisions"] = dict(
                (r, ((rule_assessment.get("assessments") or {}).get(r)
                     or {}).get("decision"))
                for r in ids)
    result["stopped_at"] = stopped
    return result
