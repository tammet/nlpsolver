"""One case, from a translation to a minimal set of bridges that prove it.

The order is fixed and every step is recorded:

  1. **translation status** — a parse with no question, no clause theory or an
     `Error:` answer is repaired once and otherwise stopped as a translation
     failure.  It never reaches bridge generation and is never counted as an
     abstention;
  2. **the conservative front door** — gk on the case's own clauses.  A
     definite answer ends the case with no LLM call and no dynamic gk call;
  3. **candidates**, then the **initial call**, then the two channels that
     build rules in code;
  4. **submission A**, the initial call's rules, offered to gk on their own;
  5. **the second call**, made only when A proved nothing.  When A did prove,
     the call is skipped and recorded as such — replay, minimisation and the
     exclusion search still run;
  6. **submissions B and C**, the new rules alone and everything together,
     always separate so a proof can be attributed to a round;
  7. **minimisation** — replay the cited set, then delete one rule at a time —
     and a bounded **exclusion search** for a different proof.

No assessor runs here and no post-proof grade is recorded.
"""

import collections
import hashlib
import json
import os
import re

import litbridge_atoms as atoms
import litbridge_chain as chain
import litbridge_compile as compiler
import litbridge_converter as BW
import litbridge_prompts as prompts
import litbridge_rules as rules


# --------------------------------------------------------------- constants

VERSION = "litbridge_procedure/2026-08-15"

# Round 1 also runs the two code-built channels (distinctness, negative
# relation), one more LLM call each, when this is True.
EXTRAS = False

WEIGHT_POLICY = ("no weight is applied anywhere: the clause is full confidence "
                 "and the reported result carries gk's own confidence, the "
                 "number of invented rules, and their post-proof grades")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")

MAX_EXCLUSION_WORLDS = 4

WEIGHT = 1.0

GK_ANSWER = "answer found"

GK_TIMEOUT = "time limit"

GK_BELOW = "evidence below limit"

RULES_PROMPT = "unifier_rules_v4"

FEEDBACK_PROMPT = "unifier_rule_feedback_v2"

ALTERNATIVE_PROMPT = "unifier_rule_alternative_v1"

GRADE_PROMPT = "grade_used_rules_v2"

MAX_ACCUMULATED_HYPOTHESES = 30

ERROR_ANSWER_LINE = re.compile(r"^\s*error\b", re.I)

FRONT_DOOR_POLICY = ("an answer beginning `Error:` is not a definite answer; "
                     "the case is unresolved and goes on to bridge generation")

SECOND_CALL_SKIPPED = "first_submission_proved"

DIAGNOSTIC_OPTION = "ask_for_an_alternative_after_a_proof"

TRANSLATION_FAILURE = "translation_failure"

REPEATED = "repeated_failed_request_reply"

NO_STAGE1 = "stage1_missing_or_unreadable"

NO_STAGE2 = "stage2_missing_or_unreadable"

NO_CLAUSES = "no_clause_theory"

NO_QUESTION = "no_usable_question_clause"

MANY_QUESTIONS = "incompatible_question_clauses"

PARSE_FAILED = "parse_failed"

ERROR_ANSWER = "conservative_answer_is_an_error"

STAGE1_CORRECTION = """The previous response could not be used.

VALIDATION ERROR:
%s

THE RESPONSE THAT FAILED:
%s

Read the original text again and return a corrected Stage-1 result in the same
format. Fix only what the validation error names."""

STAGE2_CORRECTION = """The previous response could not be used: its question \
package is missing or unusable.

VALIDATION ERROR:
%s

THE ENGLISH QUESTION:
%s

THE STAGE-1 UNITS, WHICH ARE VALID AND MUST BE PRESERVED:
%s

THE RESPONSE THAT FAILED:
%s

Return the corrected Stage-2 result. Preserve the non-question logic exactly as
it is and correct only the question package."""


# ------------------------------- translation status and one bounded repair

def status_of(view, conservative=None):
  """-> {usable, why, detail}.  Checked before any candidate is built."""
  detail = {}
  if view.get("parse_failed"):
    return {"usable": False, "why": PARSE_FAILED, "detail": detail}
  if not view.get("stage1"):
    return {"usable": False, "why": NO_STAGE1, "detail": detail}
  if not view.get("stage2"):
    return {"usable": False, "why": NO_STAGE2, "detail": detail}
  clauses = view.get("final_clauses")
  if not clauses:
    return {"usable": False, "why": NO_CLAUSES, "detail": detail}
  questions = _question_clauses(view)
  detail["question_clauses"] = len(questions)
  if not questions:
    return {"usable": False, "why": NO_QUESTION, "detail": detail}
  sources = _question_sources(questions)
  detail["question_source_sentences"] = sorted(sources)
  if len(sources) > 1:
    return {"usable": False, "why": MANY_QUESTIONS, "detail": detail}
  answer = (conservative or {}).get("answer")
  if isinstance(answer, str) and answer.strip().lower().startswith("error"):
    detail["answer"] = answer[:120]
    return {"usable": False, "why": ERROR_ANSWER, "detail": detail}
  return {"usable": True, "why": None, "detail": detail}

class Repair(object):
  """One bounded correction attempt, with the arm's own model.

  The caller supplies `parse`, which re-runs the ordinary pipeline for a
  corrected response, so the ordinary validators judge it.  Nothing here
  decides that a reply is good because it looks like a question.
  """

  def __init__(self, respond, parse, case_id, seen=None):
    self.respond = respond
    self.parse = parse
    self.case_id = case_id
    self.seen = seen if seen is not None else set()
    self.log = []

  def __call__(self, view, status):
    got = {"version": VERSION, "attempted": True, "usable": False,
           "why": status["why"], "requests": []}
    stage = "stage1" if status["why"] in (NO_STAGE1, PARSE_FAILED) \
        else "stage2"
    error = "%s (%s)" % (status["why"],
                         json.dumps(status.get("detail") or {}))
    if stage == "stage1":
      request = stage1_correction(view.get("input_text"), error,
                                  view.get("stage1_raw"))
    else:
      request = stage2_correction(
          (view.get("_split") or {}).get("question")
          or view.get("input_text"), view.get("stage1"), error,
          view.get("stage2_raw"))
    key = fingerprint(stage, request, "")
    if key in self.seen:
      got.update({"stopped": REPEATED,
                  "note": "this correction request has already failed "
                          "for this case"})
      return got
    self.seen.add(key)
    reply, note = self.respond("format_retry_%s" % stage,
                               "%s/%s_repair" % (self.case_id, stage),
                               request)
    pair = fingerprint(stage, request, reply)
    got["requests"].append({"stage": stage, "request": request,
                            "request_sha256": hashlib.sha256(
                                request.encode()).hexdigest(),
                            "reply": reply, "llm_note": note,
                            "pair_sha256": pair})
    if pair in self.seen:
      got.update({"stopped": REPEATED,
                  "note": "this request produced a reply that has "
                          "already failed"})
      return got
    self.seen.add(pair)
    try:
      fixed = self.parse(view, stage, reply)
    except Exception as e:                                  # noqa: BLE001
      got.update({"stopped": "the corrected response did not parse",
                  "error": "%s: %s" % (type(e).__name__, e)})
      return got
    if fixed is None:
      got["stopped"] = "the corrected response produced no view"
      return got
    after = status_of(fixed)
    got["status_after"] = after
    if not after["usable"]:
      got["stopped"] = "the corrected response is still unusable: %s" \
          % after["why"]
      return got
    got.update({"usable": True, "view": fixed})
    return got

def no_repair(status):
  """The record written when no repair callable was supplied."""
  return {"version": VERSION, "attempted": False, "usable": False,
          "why": status["why"],
          "note": "no correction attempt was configured for this run"}

def fingerprint(sysprompt, request, reply):
  return hashlib.sha256(("%s\x00%s\x00%s" % (sysprompt, request, reply or ""))
                        .encode()).hexdigest()

def stage1_correction(text, error, failed_reply):
  return STAGE1_CORRECTION % (error, (failed_reply or "")[:4000])

def stage2_correction(question, units, error, failed_reply):
  return STAGE2_CORRECTION % (error, question,
                              json.dumps(units)[:4000],
                              (failed_reply or "")[:4000])


# ---------------------------------------------------------- the front door

UNRESOLVED_ANSWERS = ("Unknown.", None, "")


def view_hash(view):
  """The case as gk sees it: its id, its Stage-2 parse and its clauses."""
  h = hashlib.sha256()
  for part in (view["case_id"], json.dumps(view["stage2"], sort_keys=True),
               json.dumps(view["final_clauses"], sort_keys=True)):
    h.update(part.encode())
    h.update(b"\x00")
  return h.hexdigest()


def front_door(view, gk):
  """gk on the case's own clauses, with an error string read as no answer.

  A definite answer here ends the case: no bridge is built, no model is
  called and no dynamic gk call is made.
  """
  got = gk(view["final_clauses"], view, "front_door:%s" % view["case_id"],
           dynamic=False)
  answer = got.get("answer")
  got = {"answer": answer,
         "resolved": answer not in UNRESOLVED_ANSWERS,
         "seconds": got.get("seconds"),
         "gk_thresholds": got.get("thresholds"),
         "error": got.get("error")}
  got["front_door_policy"] = FRONT_DOOR_POLICY
  if got.get("resolved") and isinstance(answer, str) \
          and ERROR_ANSWER_LINE.match(answer):
    got["resolved"] = False
    got["error_answer"] = answer
    got["unresolved_because"] = (
        "the front door returned an error string rather than an answer: "
        "%r" % answer[:120])
  return got


# -------------------------------------------------------- running one case

def run_case(view, respond, gk, bounds=None, configuration=None, sidecar=None,
             hypothesis_cap=MAX_ACCUMULATED_HYPOTHESES, do_second_round=True,
             do_exclusions=True, do_distinctness=True,
             do_negative_relations=True,
             ask_for_an_alternative_after_a_proof=False, repair=None):
  return _run_case(view, respond, gk, bounds, configuration, sidecar,
                       hypothesis_cap, do_second_round, do_exclusions,
                       do_distinctness, do_negative_relations,
                       ask_for_an_alternative_after_a_proof, repair)

def _run_case(view, respond, gk, bounds, configuration, sidecar,
              hypothesis_cap, do_second_round, do_exclusions, do_distinctness,
              do_negative_relations, ask_after_proof, repair):
  prompts.check_fixed_inputs()
  bounds = bounds or {}
  budget = bounds.get("gk_budget", lambda: True)
  configuration = configuration or view["configuration"]
  case_id = view["case_id"]
  trace = [{"stage": "translation"}]
  result = {"case_id": case_id, "mode": "unifier_v6_1", "version": VERSION,
            "configuration": configuration,
            "input_text": view["input_text"],
            "system_prompt_name": prompts.SYSTEM_PROMPT_NAME,
            "system_prompt_sha256": prompts.system_prompt_sha256(),
            "parser_version": rules.VERSION,
            "compiler_version": compiler.VERSION,
            "negative_relation_channel": rules.VERSION,
            "front_door_policy": FRONT_DOOR_POLICY,
            "trace": trace, "dynamic_work_done": False,
            "weight_policy": WEIGHT_POLICY,
            "limits": {"base_rules_per_call": rules.MAX_BASE_RULES_PER_CALL,
                       "premises_per_rule": rules.MAX_BODY_LITERALS,
                       "accumulated_hypotheses": hypothesis_cap,
                       "exclusion_worlds": MAX_EXCLUSION_WORLDS,
                       "negative_relation_pairs": rules.MAX_PAIRS,
                       DIAGNOSTIC_OPTION: ask_after_proof}}

  # ---- WP6: a broken translation stops here, after one repair attempt
  status = status_of(view)
  result["translation_status"] = status
  if not status["usable"]:
    trace.append({"stage": "translation_repair", "why": status["why"]})
    got = repair(view, status) if repair else no_repair(status)
    result["translation_repair"] = got
    if not got.get("usable"):
      trace.append({"stage": "stopped",
                    "why": "the translation failed and one bounded "
                           "correction did not fix it"})
      result["stopped_at"] = TRANSLATION_FAILURE
      result["translation_failure"] = True
      result["grading"] = {"asked": False, "grades": {}}
      return result
    view = got["view"]
    result["translation_repaired"] = True

  result["view_sha256"] = view_hash(view)
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
  preflight = prompts.question_preflight(view)
  result["question_preflight"] = preflight
  if not preflight["llm_call_allowed"]:
    trace.append({"stage": "stopped", "why": preflight["why_refused"]})
    result["stopped_at"] = "question_split_refused"
    return result
  split = prompts.split_case_text(view)
  view["_split"] = split

  trace.append({"stage": "candidates"})
  complete = prompts.complete_inventory(view, configuration)
  built = prompts.build_candidates(view, configuration, complete)
  built["case_id"] = case_id
  prompts.relabel(built)
  main_ids = built["main_ids"]
  vocab = rules.vocabulary({"groups": prompts.vocabulary_rows(built)})
  result["candidates"] = _candidate_record(built)
  result["candidates"]["main_atoms"] = sorted(main_ids)
  result["candidates"]["helper_atoms"] = sorted(built["helper_ids"])
  if not built["groups"]:
    trace.append({"stage": "stopped",
                  "why": "no positive atom of this case is displayable and "
                         "writable as a bridge"})
    result["stopped_at"] = "no_candidate"
    return result

  source_rules = rules.stage2_source_rules(view["stage2"])
  rounds, worlds = [], []
  stopped = None

  trace.append({"stage": "round_1"})
  message = prompts.build_initial_user_prompt(view, built)
  if message["exceeds_size_guard"]:
    trace.append({"stage": "stopped", "why": message["why_refused"]})
    result["stopped_at"] = "user_message_too_large"
    return result
  text, note = respond("rules", "%s/r1" % case_id, message["text"])
  parsed = rules.parse_response(text, vocab, main_ids, source_rules,
                             max_rules=rules.MAX_BASE_RULES_PER_CALL)
  written = list(parsed["accepted"])
  rounds.append(_round_record(1, "initial", message, text, note, parsed))

  if do_distinctness:
    trace.append({"stage": "distinctness"})
    got = rules.run_distinctness(view, built, split["question"], respond, case_id,
                 start_index=parsed["next_index"])
    result["distinctness"] = dict((k, v) for k, v in got.items()
                                  if k != "rules")
    result["distinctness"]["rule_ids"] = [r["rule_id"]
                                          for r in got["rules"]]
    written = written + got["rules"]
    parsed["next_index"] = got.get("next_index", parsed["next_index"])

  if do_negative_relations:
    trace.append({"stage": "negative_relations"})
    got = rules.run_negative_relation(view, built, split["passage"], split["question"],
                 respond, case_id, start_index=parsed["next_index"],
                 source_rules=source_rules)
    result["negative_relations"] = dict((k, v) for k, v in got.items()
                                        if k != "rules")
    written = written + got["rules"]
    parsed["next_index"] = got.get("next_index", parsed["next_index"])

  first_world = None
  if written and budget():
    pool, dropped, order = order_hypotheses(written, cap=hypothesis_cap)
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
  elif not written:
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
    tried = [r for r in written
             if r["rule_id"] in set(rounds[0].get("bridge_set")
                                    or [x["rule_id"] for x in written])]
    first_hypotheses = _with_clauses(first_world)
    if not found:
      message2 = prompts.build_no_proof_user_prompt(view, built, tried)
      role = "feedback"
    else:
      cited = set()
      for p in (first_world or {}).get("dynamic_proofs") or []:
        cited |= set(x for x in p["cited_rules"] if x)
      offered = set(rounds[0].get("bridge_set") or [])
      message2 = prompts.build_alternative_user_prompt(
          view, built, [r for r in written if r["rule_id"] in cited],
          [r for r in written
           if r["rule_id"] in offered and r["rule_id"] not in cited])
      role = "alternative"
      result["proof_used_rules"] = sorted(cited)
    if message2["exceeds_size_guard"]:
      rounds.append({"round": 2, "call": "refused",
                     "why": message2["why_refused"]})
      stopped = stopped or "second_message_too_large"
    else:
      text2, note2 = respond(role, "%s/r2" % case_id, message2["text"])
      parsed2 = rules.parse_response(
          text2, vocab, main_ids, source_rules,
          max_rules=rules.MAX_BASE_RULES_PER_CALL,
          start_index=parsed["next_index"], existing=written,
          tried=[r["canonical"] for r in written])
      rounds.append(_round_record(2, message2["call"], message2, text2,
                                  note2, parsed2))
      new_rules = list(parsed2["accepted"])
      written = written + new_rules
      if new_rules:
        result["chain_status"] = _chain_records(
            view, configuration, built, new_rules, first_hypotheses,
            case_id)
        result["chain_status"]["shown_to_the_model"] = False
        for r in new_rules:
          got = (result["chain_status"]["second_only"]
                 .get(r["rule_id"]) or {})
          r["chain_status"] = got.get("status")
          r["chain_after"] = got.get("after")
      if new_rules and budget():
        pool_b = chain.order_by_chain(
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
        ordered = chain.order_by_chain(
            written, (result.get("chain_status") or {}).get(
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
  result["rules"] = [dict(_rule_record(r), meaning=r.get("meaning", ""),
                          head_sign=r.get("head_sign",
                                          r["head"]["sign"]
                                          if r.get("head") else "+"),
                          negative_conclusion=bool(
                              r.get("negative_conclusion")
                              or (r.get("head") or {}).get("sign") == "-"))
                     for r in written]
  result["worlds"] = [_world_record(w) for w in worlds]
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
                      if r.get("origin") == rules.ORIGIN]},
      "by_call": dict((r["call"], r.get("signed_counts"))
                      for r in rounds if r.get("signed_counts"))}
  rules_by_id = dict((r["rule_id"], r) for r in written)

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
    result["stopped_at"] = stopped or _no_proof_reason(worlds, written)
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
        view, gk, configuration, built["groups"], case_id, list(written),
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


# ---------------------------------------------------- one submission to gk

def run_world(view, rules, gk, configuration, groups, world_id, tag,
              sidecar=None):
  """Compile a bridge set, append it to the STORED theory, ask gk."""
  world = compiler.build_world(world_id, rules, view, configuration,
                          groups=groups, weight=WEIGHT,
                          check_redundancy=True)
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
  proofs = proofs_of(got.get("raw") or "{}", world["clause_provenance"])
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

def order_hypotheses(written, cap=MAX_ACCUMULATED_HYPOTHESES):
  """-> (the rules gk sees, the ones the limit left out, with the reason).

  Model-written base rules first, then the distinctness channel's rule, then
  program-generated specializations.  Inside a block: a body that may start,
  then role fit, then fewer premises, then rule cost, then id.
  """
  def block(r):
    if r.get("origin") == rules.GROUND_SPECIALIZATION:
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
  ordered = sorted(written, key=key)
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


# ---------------------------------------------- minimisation and exclusion

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


# -------------------------------------------------------------- the record

def _round_record(n, call, message, text, note, parsed):
  got = _round_record_signed(n, call, message, text, note, parsed)
  got["polarity_refusals"] = parsed.get("polarity_refusals") or []
  return got

def _rule_record(r):
  return dict((k, v) for k, v in r.items())

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

def _chain_records(view, configuration, built, new_rules, first_hypotheses,
                   case_id):
  """WP6: can these new rules start on their own, and with the first ones?

  The rules are compiled once here, with no gk call, only to read the content
  literals of their bodies and heads.
  """
  world = compiler.build_world("chain_%s" % case_id, new_rules, view,
                          configuration, groups=built["groups"])
  mine = _with_clauses(world)
  second = chain.chain_status(view, mine)
  accumulated = chain.chain_status(view, mine, extra_hypotheses=first_hypotheses)
  return {"second_only": second["status"],
          "accumulated": accumulated["status"],
          "second_only_search_bound_reached": second["search_bound_reached"],
          "accumulated_search_bound_reached":
              accumulated["search_bound_reached"],
          "refused_by_the_compiler": world["refused_by_the_compiler"],
          "policy": "a rule that cannot start is ordered last and recorded as "
                    "explicitly speculative; it is never deleted for that "
                    "reason"}

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

def component_hashes():
  """Every source whose change would make a run incomparable."""
  here = os.path.dirname(os.path.abspath(__file__))
  got = {}
  for name in ("litbridge_atoms", "litbridge_rules", "litbridge_compile",
               "litbridge_chain", "litbridge_prompts", "litbridge_procedure",
               "litbridge_converter"):
    path = os.path.join(here, "%s.py" % name)
    got[name] = hashlib.sha256(open(path, "rb").read()).hexdigest()
  got[prompts.SYSTEM_PROMPT_NAME] = prompts.system_prompt_sha256()
  got[rules.NEGATIVE_SYSTEM_PROMPT_NAME] =         rules.negative_system_prompt_sha256()
  got[rules.DISTINCT_SYSTEM_PROMPT_NAME] =         rules.distinct_system_prompt_sha256()
  return got

def sha_of(obj):
  return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                   default=str).encode()).hexdigest()


# ---------------------------------------------------------------- the rest

def _cited_clause_names(proof_lists):
  names = []
  for step in chain._proof_steps(proof_lists):
    for n in chain._names_in_step(step):
      if n not in names:
        names.append(n)
  return names

def proofs_of(raw, provenance):
  """Every proof gk returned, not only answer index zero.

  A returned answer that cites no dynamic hypothesis is kept and marked: it is
  a search-order or base-theory result, not a dynamic-abstraction proof.
  """
  if isinstance(raw, str):
    try:
      raw = json.loads(raw)
    except ValueError:
      raw = {}
  out = []
  for i, a in enumerate((raw or {}).get("answers") or []):
    proof_lists, kinds = [], []
    for key in ("positive proof", "negative proof", "proof"):
      if a.get(key):
        proof_lists.append(a[key])
        kinds.append(key)
    used, by_hyp = chain.cited_hypotheses(proof_lists, provenance)
    out.append({
        "answer_index": i,
        "answer": a.get("answer"),
        "gk_native_confidence": a.get("confidence"),
        "proof_kinds": kinds,
        "proof_steps": sum(len(p) for p in proof_lists),
        "cited_clause_names": _cited_clause_names(proof_lists),
        "cited_hypothesis_ids": list(used),
        "cited_clauses_by_hypothesis": {h: by_hyp[h] for h in used},
        "cites_no_dynamic_hypothesis": not used,
        "blockers": a.get("blockers"),
        "proof": proof_lists,
    })
  return out

def prompt_text(name):
  with open(os.path.join(PROMPT_DIR, "%s.txt" % name)) as f:
    return f.read()

def prompt_sha(name):
  return hashlib.sha256(prompt_text(name).encode()).hexdigest()

def _round_record_base(n, call, message, text, note, parsed):
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

def _round_record_signed(n, call, message, text, note, parsed):
  got = _round_record_base(n, call, message, text, note, parsed)
  got.update({"readable_blocks": parsed.get("readable_blocks"),
              "said_no_rule": parsed.get("said_no_rule"),
              "meanings": parsed.get("meanings"),
              "format_refusals": parsed.get("format_refusals"),
              "blocks": parsed.get("blocks"),
              "signed_counts": parsed.get("signed_counts"),
              "negative_conclusions": parsed.get("negative_conclusions")})
  got["accepted"] = [dict(a, meaning=a.get("meaning", ""),
                          head_sign=a.get("head_sign"),
                          negative_conclusion=a.get("negative_conclusion"))
                     for a in got.get("accepted") or []]
  return got

def _question_clauses(view):
  out = []
  for clause in view.get("final_clauses") or []:
    if atoms._source_kind(clause) == atoms.QUESTION:
      out.append(clause)
    elif clause.get("@question") is not None:
      out.append(clause)
  return out

def _question_sources(clauses):
  """The sentences the question clauses came from.

  One English question converts to MANY clauses — the negated goal in CNF —
  and `folio-0101` has 44 of them from one sentence.  So the count of clauses
  says nothing; what would be incompatible is question clauses from more than
  one source sentence, which is a translation that asked two things at once.
  """
  return set(str(c.get("@name") or "") for c in clauses)

def _blank(term):
  if isinstance(term, str):
    return "?" if atoms.is_clause_variable(term) else term
  if isinstance(term, list):
    return [_blank(x) for x in term]
  return term



# ----------------------------------- the clauses a bridge round contributes

# The pipeline drives the rounds, because only the pipeline knows what gk said.
# `bridge_context` reads the case and builds the candidate atoms once, with no
# LLM call; `bridge_round` makes the calls of one round and returns the clauses
# that round's rules compile to.  Neither calls gk.
#
# Round 1 asks the model to propose rules over the displayed atoms.  Round 2 is
# asked only when round 1's clauses reached gk and gk still proved nothing; it
# says so and asks for rules not already tried.  The two code-built channels,
# distinctness and negative relation, belong to round 1 and run only when the
# caller asks for them (`EXTRAS`).

ROUND_LABEL = {1: "r1", 2: "r2"}


class Context(dict):
  """What every round needs: the candidates, the vocabulary, what was tried."""


def bridge_context(view, configuration=None):
  """-> (context, why_refused).  No LLM call and no gk call is made here."""
  configuration = configuration or view.get("configuration") or "standard"
  case_id = view.get("case_id") or "case"

  status = status_of(view)
  if not status["usable"]:
    return None, status["why"]
  preflight = prompts.question_preflight(view)
  if not preflight["llm_call_allowed"]:
    return None, preflight["why_refused"]

  split = prompts.split_case_text(view)
  view["_split"] = split
  complete = prompts.complete_inventory(view, configuration)
  built = prompts.build_candidates(view, configuration, complete)
  built["case_id"] = case_id
  prompts.relabel(built)
  if not built["groups"]:
    return None, "no_candidate"

  return Context({
      "case_id": case_id,
      "configuration": configuration,
      "built": built,
      "split": split,
      "main_ids": built["main_ids"],
      "vocab": rules.vocabulary({"groups": prompts.vocabulary_rows(built)}),
      "source_rules": rules.stage2_source_rules(view["stage2"]),
      "written": [],                      # every rule accepted so far
      "next_index": 1,
      "compiled": 0,                      # hypotheses already given to gk
      "candidate_atoms": len(built["groups"]),
  }), None


def bridge_round(ctx, view, respond, round_number=1, extras=False, cap=None):
  """-> (clauses, record).  One round: the calls, then the compile.

  The clauses are only this round's, because the caller has already appended
  every earlier round's to the theory it submits.
  """
  built, case_id = ctx["built"], ctx["case_id"]
  record = {"version": VERSION, "round": round_number, "asked": False,
            "rules": 0, "clauses": 0, "stopped_at": None,
            "printed_rules": [], "candidate_atoms": ctx["candidate_atoms"]}

  if round_number == 1:
    message = prompts.build_initial_user_prompt(view, built)
  else:
    message = prompts.build_no_proof_user_prompt(view, built, ctx["written"])
  if message["exceeds_size_guard"]:
    record["stopped_at"] = message["why_refused"]
    return [], record

  record["asked"] = True
  text, _note = respond("rules", "%s/%s" % (case_id, ROUND_LABEL.get(
      round_number, "r%d" % round_number)), message["text"])
  if text is None:
    record["stopped_at"] = "no_llm_response"
    return [], record

  parsed = rules.parse_response(
      text, ctx["vocab"], ctx["main_ids"], ctx["source_rules"],
      max_rules=rules.MAX_BASE_RULES_PER_CALL,
      start_index=ctx["next_index"], existing=ctx["written"],
      tried=[r["canonical"] for r in ctx["written"]])
  fresh = list(parsed["accepted"])
  ctx["next_index"] = parsed["next_index"]
  record["rejections_by_category"] = parsed.get("rejections_by_category")

  if round_number == 1 and extras:
    got = rules.run_distinctness(view, built, ctx["split"]["question"], respond,
                                 case_id, start_index=ctx["next_index"])
    fresh = fresh + got["rules"]
    ctx["next_index"] = got.get("next_index", ctx["next_index"])
    record["distinctness"] = {"asked": got.get("asked", False),
                              "eligible_pairs": len(got.get("eligible") or []),
                              "rules": len(got["rules"]),
                              "why_not_asked": got.get("why")}
    got = rules.run_negative_relation(
        view, built, ctx["split"]["passage"], ctx["split"]["question"], respond,
        case_id, start_index=ctx["next_index"],
        source_rules=ctx["source_rules"])
    fresh = fresh + got["rules"]
    ctx["next_index"] = got.get("next_index", ctx["next_index"])
    record["negative_relation"] = {"asked": got.get("asked", False),
                                   "eligible_pairs": len(got.get("eligible")
                                                         or []),
                                   "rules": len(got["rules"]),
                                   "why_not_asked": got.get("why_not_asked")}

  if not fresh:
    record["stopped_at"] = "no_rule_written"
    return [], record

  room = (cap or MAX_ACCUMULATED_HYPOTHESES) - ctx["compiled"]
  if room <= 0:
    record["stopped_at"] = "hypothesis_limit_reached"
    return [], record
  pool, dropped, order = order_hypotheses(fresh, cap=room)
  world = compiler.build_world(
      "litbridge_%s_%s" % (case_id, ROUND_LABEL.get(round_number,
                                                    "r%d" % round_number)),
      pool, view, ctx["configuration"], groups=built["groups"],
      check_redundancy=True,
      # the round travels in the clause name, so a proof step can say which
      # round invented the rule it leans on
      hypothesis_case_id="%s_%s" % (case_id,
                                    ROUND_LABEL.get(round_number,
                                                    "r%d" % round_number)))
  clauses = world["compiled_bridge_clauses"]
  ctx["written"] = ctx["written"] + pool
  ctx["compiled"] += len(world.get("bridge_hypotheses") or [])
  record.update({
      "rules": len(pool),
      "omitted_by_the_hypothesis_limit": dropped,
      "ordering": order,
      "clauses": len(clauses),
      "printed_rules": [h["printed_formula"]
                        for h in world.get("bridge_hypotheses") or []],
      "refused_by_the_compiler": world.get("refused_by_the_compiler"),
      "signed_counts": world.get("signed_counts"),
      # what a grader needs to name the rules a proof leans on: clause name ->
      # hypothesis id, and hypothesis id -> the rule as printed
      "clause_provenance": world.get("clause_provenance") or {},
      "rules_by_id": dict(
          (h.get("hypothesis_id") or h.get("rule_id"),
           {"printed": h.get("printed_formula"),
            "meaning": h.get("meaning") or ""})
          for h in world.get("bridge_hypotheses") or []
          if h.get("hypothesis_id") or h.get("rule_id")),
  })
  return clauses, record
