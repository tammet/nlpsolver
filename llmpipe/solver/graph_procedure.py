"""One case through the open-relation graph route, end to end.

`graph_context` does everything that costs no gk call: the graph Stage 2, its
checks, the conversion under the frozen option set, the inventories, the
frontier and the candidate pairs.  `graph_run` adds the judge calls, the pooled
gk search, the grading and the lifting, and returns one record.

The record is the deliverable.  Every stage says what it did, what it refused
and why, which cap stopped it, and what the option set was, so a run can be
audited without rerunning it.
"""

import json
import os

import graph_compile as GC
import graph_inventory as GI
import graph_judge as GJ
import graph_lift as GL
import graph_pairs as GP
import graph_search as GS
import graph_stage2 as G2

VERSION = "graph_procedure/2026-08-16"

DEFAULT_SOURCES = ("frontier",)
FULL_SOURCES = ("frontier", "exhaustive", "composition")

TRANSLATION_FAILED = "graph_translation_failed"
NO_QUESTION = "the graph translation has no question package"
NO_CANDIDATE = "no candidate pair survived the filters"


def component_hashes():
  """Every prompt and module the graph route runs on."""
  import hashlib
  out = {}
  root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
  for name in ("graph_stage2", "graph_compile", "graph_inventory",
               "graph_pairs", "graph_judge", "graph_search", "graph_lift",
               "graph_procedure"):
    p = os.path.join(root, "solver", "%s.py" % name)
    if os.path.exists(p):
      out["solver/%s.py" % name] = hashlib.sha256(
          open(p, "rb").read()).hexdigest()
  for source in (G2.prompt_hashes(), GJ.prompt_hashes(), GS.prompt_hashes(),
                 GL.prompt_hashes()):
    out.update(source)
  return out


# ------------------------------------------------------------ the translation

def translate(case_id, s1_json, llm=None, version=None, tokens=None,
              think=None, arm=1, input_text=None, stats=None,
              correction=None):
  """The graph Stage 2 of one case, with its checks and its measurements."""
  import llmparse
  stats = stats if stats is not None else llmparse._make_stats()
  if arm == 1:
    s2, raw, err = G2.translate(s1_json, llm, version, tokens, think, stats,
                                correction)
  elif arm == 2:
    s2, raw, err = G2.translate_english(
        input_text, G2.stage1_entity_rows(s1_json), llm, version, tokens,
        think, stats, s1_json)
  else:
    s2, raw, err = G2.translate_english(input_text, None, llm, version,
                                        tokens, think, stats)
  record = {"case_id": case_id, "arm": arm, "error": err,
            "raw_chars": len(raw or ""),
            "prompt_sha256": _sha(G2.sysprompt() if arm == 1
                                  else G2.onestage_sysprompt())}
  if s2 is None:
    record["stopped_at"] = TRANSLATION_FAILED
    return None, record
  issues = (G2.check_graph(s2, s1_json) if arm == 1
            else G2.check_english(s2, s1_json, arm == 2))
  if arm != 1:
    s2, mapping, unmatched = G2.align_packages_to_stage1(s2, s1_json)
    record["unit_alignment"] = {"mapping": mapping, "unmatched": unmatched,
                                "policy": "an English-only arm mints its own "
                                          "unit ids; they are matched to the "
                                          "Stage-1 units in order so the "
                                          "question package lands on a query "
                                          "unit"}
  record.update({
      "stage2_graph": s2,
      "issues": [{"kind": i.kind, "location": i.location,
                  "description": i.description} for i in issues],
      "issue_kinds": sorted(set(i.kind for i in issues)),
      "valid": not issues,
      "stage_stats": {k: v for k, v in stats.items()
                      if k.startswith("s2_") and v},
      "measurements": G2.measure(s2, s1_json, (), issues)})
  if not G2.question_packages(s2):
    record["stopped_at"] = NO_QUESTION
    return None, record
  return s2, record


def _sha(text):
  import hashlib
  return hashlib.sha256((text or "").encode()).hexdigest()


# --------------------------------------------------------------- the context

def graph_context(case_id, s1_json, s2_graph, options=None,
                  sources=DEFAULT_SOURCES, policy_strict=True,
                  limit=GP.EXHAUSTIVE_LIMIT, input_text=None):
  """Everything the case needs before the first judge call and the first gk."""
  opts = options if options is not None else GC.graph_options()
  clauses, sidecar = GC.compile(s2_graph, s1_json, options=opts,
                                case_id=case_id)
  inventory = GI.build(s2_graph, s1_json)
  sd = GI.supply_demand(clauses)
  pairs, refused, note, filters = GP.enumerate_pairs(
      s2_graph, s1_json, inventory, sd, sources=sources,
      policy_strict=policy_strict, limit=limit)
  view = {"case_id": "%s_graph" % case_id, "stage1": s1_json,
          "stage2": sidecar["controlled_stage2"], "final_clauses": clauses,
          "input_text": input_text, "configuration": opts}
  return {"version": VERSION, "case_id": case_id, "graph_case_id":
          "%s_graph" % case_id,
          "options": opts, "options_sha256": GC.options_sha256(opts),
          "clauses": clauses, "sidecar": sidecar, "inventory": inventory,
          "supply_demand": sd, "pairs": pairs, "refused_pairs": refused,
          "enumeration": note, "filters": filters, "view": view,
          "demand_complement": GI.demand_complement(sd, inventory),
          "summary": GI.summary(inventory, sd)}


# ------------------------------------------------------------------ the run

def judge(ctx, respond, with_sentences=True, holistic=False, cap_batches=3):
  """Every batch, then the optional holistic call.  -> the judged rows."""
  case_id, s1 = ctx["case_id"], ctx["view"]["stage1"]
  judged, calls, note = [], [], {"batches": 0, "holistic": False}
  batches = GP.batches(ctx["pairs"])
  for i, batch in enumerate(batches, start=1):
    if i > cap_batches:
      note.setdefault("unjudged_batches", []).append(
          {"batch": i, "pairs": len(batch),
           "why": "beyond the %d judge batches a case may send" % cap_batches})
      continue
    message = GJ.batch_message(batch, ctx["inventory"], s1, with_sentences)
    text, err = respond("graph_judge", "%s/judge/%d" % (case_id, i), message)
    calls.append({"batch": i, "pairs": len(batch), "chars": len(message),
                  "error": err, "reply_chars": len(text or "")})
    note["batches"] += 1
    if err or not text:
      for pair in batch:
        judged.append({"pair_id": pair.get("pair_id"), "label": GJ.UNCERTAIN,
                       "pair": pair, "why": None,
                       "no_reply": err or "the judge returned nothing"})
      continue
    judged.extend(GJ.parse_batch(text, batch))
  # WP3.2: a pair the enumeration refused as a restatement of the question is
  # asked, not dropped — in its own batch, whose prompt allows only "these two
  # names are one predicate in other wording" or NO.
  restated = [r for r in ctx["refused_pairs"]
              if r.get("refused") == GP.QUESTION_RESTATEMENT
              and r.get("kind") and r.get("a_reading")
              and r.get("b_reading")]
  if restated:
    for n, pair in enumerate(restated, start=1):
      pair["pair_id"] = "L%d" % n
      pair["source"] = pair.get("source") or "restatement"
    message = GJ.batch_message(restated, ctx["inventory"], s1, with_sentences)
    text, err = respond("graph_judge_lexical", "%s/judge/lexical" % case_id,
                        message)
    calls.append({"batch": "restatement", "pairs": len(restated),
                  "chars": len(message), "error": err,
                  "reply_chars": len(text or "")})
    rows = GJ.parse_lexical(text, restated) if text else []
    note["restatement_pairs_asked"] = len(restated)
    note["restatement_pairs_kept"] = len(rows)
    judged.extend(rows)
  if holistic:
    message = GJ.holistic_message(ctx["inventory"])
    text, err = respond("graph_holistic", "%s/holistic" % case_id, message)
    note["holistic"] = True
    calls.append({"call": "holistic", "chars": len(message), "error": err,
                  "reply_chars": len(text or "")})
    if text:
      proposals, dropped = GJ.parse_holistic(text, ctx["inventory"])
      note["holistic_proposals"] = len(proposals)
      note["holistic_dropped"] = dropped
      # WP1.7: the holistic call may only ADD pairs the frontier never
      # enumerated, and it never overrides a frontier label.  Its own label is
      # not trusted: the pair goes back through the ordinary judge.
      already = set()
      for r in judged:
        already.add((r["pair"]["a"], r["pair"]["b"]))
        already.add((r["pair"]["b"], r["pair"]["a"]))
      extra, refused, overrides = [], [], []
      for pair in GJ.holistic_pairs(proposals, ctx["inventory"]):
        if (pair["a"], pair["b"]) in already:
          overrides.append({"a": pair["a"], "b": pair["b"],
                            "why": "the frontier judge already labelled this "
                                   "pair; the holistic label is discarded"})
          continue
        why = GP.refuse(pair, ctx["filters"],
                        ctx["enumeration"].get("policy_strict", True))
        if why:
          refused.append(dict(pair, refused=why))
          continue
        pair["pair_id"] = "H%d" % (len(extra) + 1)
        pair["from_holistic"] = True
        extra.append(pair)
      note["holistic_overrides_discarded"] = overrides
      if extra:
        message = GJ.batch_message(extra, ctx["inventory"], s1, with_sentences)
        text, err = respond("graph_judge", "%s/judge/holistic" % case_id,
                            message)
        calls.append({"batch": "holistic pairs", "pairs": len(extra),
                      "chars": len(message), "error": err,
                      "reply_chars": len(text or "")})
        rows = (GJ.parse_batch(text, extra) if text else
                [{"pair_id": p.get("pair_id"), "label": GJ.UNCERTAIN,
                  "pair": p, "why": None,
                  "no_reply": err or "the judge returned nothing"}
                 for p in extra])
        for r in rows:
          r["from_holistic"] = True
        judged.extend(rows)
        extra = rows
      note["holistic_refused"] = refused
      judged.extend(extra)
  return judged, calls, note


def graph_run(ctx, respond, gk, budget=None, with_sentences=True,
              holistic=False, lift=False, sidecar=None, ordinary=None,
              pool_seconds=None, cap_batches=2, grader="all",
              evidence="any"):
  """The judge calls, the pooled search, the grading, the lifting."""
  budget = budget or (lambda: True)
  case_id = ctx["case_id"]
  record = {"version": VERSION, "case_id": case_id,
            "options_sha256": ctx["options_sha256"],
            "options": ctx["options"],
            "inventory": ctx["summary"],
            "enumeration": ctx["enumeration"],
            "pairs_enumerated": len(ctx["pairs"]),
            "pairs_refused": [{"a": r["a"], "b": r["b"], "shape": r["shape"],
                               "why": r["refused"]}
                              for r in ctx["refused_pairs"]],
            "clause_count": len(ctx["clauses"])}
  # A case can enumerate no ordinary pair and still have work for the judge:
  # the restatement batch (WP3.2) asks the pairs the enumeration refused, and
  # eb-0014's only candidate is one of those.  Skipping the judge on an empty
  # pair list skipped exactly the case the batch exists for.
  restated = any(r.get("refused") == GP.QUESTION_RESTATEMENT
                 for r in ctx["refused_pairs"])
  if ctx["pairs"] or restated or holistic:
    judged, calls, note = judge(ctx, respond, with_sentences, holistic,
                                cap_batches)
  else:
    judged, calls, note = [], [], {"batches": 0}
  record.update({"judge_calls": calls, "judge_note": note,
                 "labels": GJ.label_summary(judged),
                 # `judge_label`, not `label`: `unifier_cases.assert_no_gold`
                 # reserves `label` for a reviewed key, and a runtime record
                 # must not carry a word a scoring key uses
                 "judged": [{"pair_id": r.get("pair_id"),
                             "judge_label": r["label"], "why": r.get("why"),
                             "a": r["pair"]["a"], "b": r["pair"]["b"],
                             "shape": r["pair"]["shape"],
                             "source": r["pair"].get("source")}
                            for r in judged]})
  pools, omitted, tally = GJ.build_pools(
      judged, inventory=ctx["inventory"], s1_json=ctx["view"]["stage1"])
  record.update({"bridges_per_pool": dict(
      ("P%d" % n, len(pools[n])) for n in sorted(pools)),
      "bridge_omissions": omitted, "label_tally": tally,
      "bridges": [{"rule_id": r["rule_id"], "printed": r["printed"],
                   "pool": r.get("pool"), "shape": r.get("graph_shape"),
                   "judge_label": r.get("graph_label"),
                   "pair_label": r.get("graph_pair_label"),
                   "pair_id": r.get("graph_pair_id"),
                   "a": r.get("graph_a"), "b": r.get("graph_b"),
                   "evidence": r.get("evidence"),
                   "confidence": r.get("confidence"),
                   "from_holistic": bool(r.get("from_holistic")),
                   "source": r.get("graph_source")}
                  for r in pools[max(pools)]]})
  result = GS.search(ctx["view"], pools, gk, ctx["options"], budget,
                     sidecar=sidecar, case_id=ctx["graph_case_id"],
                     pool_seconds=pool_seconds)
  record.update({
      "pools": [{k: v for k, v in row.items() if k != "world"}
                for row in result["pools"]],
      "pool_worlds": [row.get("world") for row in result["pools"]],
      "minimal_sets": [{k: v for k, v in row.items() if k != "world"}
                       for row in result["minimal_sets"]],
      "stopping_reason": result["stopping_reason"],
      "graph_answers": GS.proof_answers(result),
      "zero_bridge_proof": any(row.get("zero_bridge_proof")
                               for row in result["pools"])})
  # WP0.2 as revised twice.  The grader sees every bridge a proof cites, one
  # message each, so a bridge's grade does not move when the rest of the cited
  # set changes.  Restricting it to bridges from undecided pairs was measured
  # (x1c against x1d) and rejected: it let through 8 wrong FOLIO proofs whose
  # bridges came from pairs the judge had decided confidently.  The judge's own
  # confidence is recorded beside the grade, as a calibration feature.
  grades = (GS.grade(result, ctx["inventory"], ctx["view"]["stage1"], respond,
                     case_id, mode=grader)
            if (grader and result["minimal_sets"]) else
            {"graded": {}, "why": "the grader is off; the judge's label and "
                                  "confidence stand in"})
  record["grades"] = grades
  record["grader_ran"] = bool(grader)
  record["grader_mode"] = (grades.get("mode") if grader else "off")
  record["grader_scope"] = (grader if isinstance(grader, str)
                            else "cited-undecided" if grader else "off")
  lifting = {"attempted": False,
             "why": ("lifting is off" if not lift else
                     "no ordinary theory was given" if not ordinary else
                     "no graph proof to lift")}
  retranslation = {"rows": [], "units_retranslated": 0,
                   "retranslated_proof": False}
  if lift and ordinary and result["minimal_sets"]:
    lifting = GL.lift(ordinary["view"], result, result["minimal_sets"],
                      ctx["sidecar"], ctx["inventory"],
                      ctx["view"]["stage1"], respond, ordinary["gk"],
                      case_id, ordinary["options"], budget, sidecar)
    if lifting.get("attempted") and not lifting.get("lifted_proof"):
      retranslation = GL.retranslate(
          ordinary["view"], ctx["view"]["stage1"],
          lifting.get("backbones") or [], respond, ordinary["gk"], case_id,
          ctx["options"], ordinary["options"], sidecar=sidecar)
  record["lifting"] = lifting
  record["retranslation"] = retranslation
  tier, why = GS.tier(result, grades,
                      {"lifted_proof": lifting.get("lifted_proof"),
                       "retranslated_proof":
                           retranslation.get("retranslated_proof")},
                      evidence)
  record["tier"] = tier
  record["tier_reason"] = why
  record["evidence_mode"] = evidence
  # WP2.1/2.2: the acceptance verdict per minimal set, with its reasons, so a
  # record can be read without recomputing the policy
  rules_by_id = result.get("rules_by_id") or {}
  graded = (grades or {}).get("graded") or {}
  verdicts = []
  for row in result["minimal_sets"]:
    ok, reasons = GS.credible_set(row, rules_by_id, graded, evidence)
    ok_any, _ = GS.credible_set(row, rules_by_id, graded, "any")
    ok_stated, _ = GS.credible_set(row, rules_by_id, graded, "stated")
    rids = list(row.get("minimal_rules") or [])
    wit = GS.witness_verdict(row, ctx["view"]["stage1"])
    verdicts.append({"minimal_rules": rids,
                     "answer": row.get("answer"), "credible": ok,
                     "credible_any": ok_any, "credible_stated": ok_stated,
                     "why_not": reasons,
                     "graded_by": dict(
                         (r, GS.grade_of(r, rules_by_id, graded)[1])
                         for r in rids),
                     "uncertain_born": sum(
                         1 for r in rids
                         if GS.uncertain_born(rules_by_id.get(r))),
                     "cites_witness": wit["cites_witness"],
                     "witness_ok": wit["ok"],
                     "witness_counterexample": wit["counterexample"],
                     "witness_reason": wit["why"]})
  record["acceptance"] = verdicts
  record["populate_clauses_in_theory"] = sum(
      1 for c in ctx["clauses"] if c.get("@sourcetype") == "populate")
  record["converter_invented_names"] = (
      ctx["sidecar"]["name_drift"]["invented_by_the_converter"])
  return record


def run_bridges(s2_graph, s1_json, respond, gk, case_id="case", options=None,
                input_text=None, sources=DEFAULT_SOURCES, evidence="any",
                lift=False, ordinary=None, cap_batches=2, budget=None):
  """Layer 2 on a translation layer 1 already made.  -> the record.

  The pipeline and the harness meet here.  Everything the v2 measurements
  settled is baked in: the judge sees the passage sentences, decided pairs go
  to P1 and the frontier's UNCERTAIN pairs to P2 in both directions, the
  grader reads every cited bridge one message at a time, and lifting is off
  unless the caller asks for it.  The translation is never made twice: layer 1
  produced it, and this reads it.
  """
  record = {"version": VERSION, "case_id": case_id}
  try:
    ctx = graph_context(case_id, s1_json, s2_graph, options, sources,
                        True, input_text=input_text)
  except Exception as e:                                        # noqa: BLE001
    record["stopped_at"] = "graph_conversion_failed"
    record["error"] = "%s: %s" % (type(e).__name__, e)
    return record
  record["graph_theory"] = {"clauses": len(ctx["clauses"]),
                            "sidecar": ctx["sidecar"]["clauses"],
                            "theory_sha256": ctx["sidecar"]["theory_sha256"]}
  if not ctx["pairs"]:
    record["stopped_at"] = NO_CANDIDATE
  record.update(graph_run(ctx, respond, gk, budget, True, False, lift, None,
                          ordinary, None, cap_batches, "all", evidence))
  return record


def credible_answer(record, evidence="any"):
  """The answer layer 2 may return: a credible minimal set, or None.

  A proof the acceptance policy refuses is kept in the record and never
  becomes the run's answer.
  """
  for verdict in (record.get("acceptance") or []):
    ok = verdict.get("credible_stated" if evidence == "stated"
                     else "credible_any")
    if not ok:
      continue
    if verdict.get("cites_witness") and not verdict.get("witness_ok"):
      continue
    answer = verdict.get("answer")
    if answer is True or str(answer).lower() == "true":
      return True, verdict
    if answer is False or str(answer).lower() == "false":
      return False, verdict
  return None, None


def run_case(case_id, s1_json, respond, gk, options=None, input_text=None,
             sources=DEFAULT_SOURCES, policy_strict=True, budget=None,
             with_sentences=True, holistic=False, lift=False, ordinary=None,
             sidecar=None, llm=None, version=None, tokens=None, think=None,
             arm=1, pool_seconds=None, cap_batches=2, grader="all",
             evidence="any"):
  """One case, translation included.  -> the record, whatever went wrong."""
  s2, translation = translate(case_id, s1_json, llm, version, tokens, think,
                              arm, input_text)
  record = {"version": VERSION, "case_id": case_id,
            "translation": {k: v for k, v in translation.items()
                            if k != "stage2_graph"},
            "stage2_graph": translation.get("stage2_graph")}
  if s2 is None:
    record["stopped_at"] = translation.get("stopped_at") or TRANSLATION_FAILED
    return record
  try:
    ctx = graph_context(case_id, s1_json, s2, options, sources, policy_strict,
                        input_text=input_text)
  except Exception as e:                                        # noqa: BLE001
    record["stopped_at"] = "graph_conversion_failed"
    record["error"] = "%s: %s" % (type(e).__name__, e)
    return record
  record["graph_theory"] = {"clauses": len(ctx["clauses"]),
                            "sidecar": ctx["sidecar"]["clauses"],
                            "theory_sha256": ctx["sidecar"]["theory_sha256"]}
  if not ctx["pairs"] and not holistic:
    record["stopped_at"] = NO_CANDIDATE
  record.update(graph_run(ctx, respond, gk, budget, with_sentences, holistic,
                          lift, sidecar, ordinary, pool_seconds, cap_batches,
                          grader, evidence))
  return record
