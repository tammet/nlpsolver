"""Pooled proof search over the graph theory, and the grading that follows it.

P0 is the graph theory alone: no generated bridge, so a proof there says the
open translation found a route the controlled one missed, or invented one.
P1 to P3 add bridges cumulatively.  gk searches both polarities in one call.
Every proof is kept.  After a proof the cited set is replayed, minimised by
deleting one bridge at a time, and each member of the first minimal set is
excluded in turn to look for a second route — unconditionally, because a
mechanism that stops at its first derivation reports its luck.

Grading runs last and only on the bridges a minimal set cites.  A grade labels
a proof and orders proof sets; it never deletes a proof and never turns an
answer into Unknown.

A bridge's own conversion emits population witnesses.  They are dropped before
submission: a witness the bridge itself introduced must never ground that
bridge's body (design plan §8.9, the folio-0144 pattern).
"""

import hashlib
import json
import os
import re

import litbridge_chain as chain
import litbridge_compile as compiler
import litbridge_converter as BW
import litbridge_procedure as procedure

VERSION = "graph_search/2026-08-16"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRADER = os.path.join(ROOT, "prompts", "graph", "graph_grader_system.txt")

# design plan §9, calibrated in Phase A against the stored gk commands
POOL_SECONDS = {0: 5, 1: 5, 2: 8}
MAX_EXCLUSION_WORLDS = 4
MAX_MINIMAL_SETS = 4

GRADES = ("LIKELY", "PLAUSIBLE", "UNCERTAIN", "UNLIKELY", "FALSE")

RULE_BLOCK = re.compile(r"^\s*RULE\s+(\S+)\s*$", re.I)
GRADE_LINE = re.compile(r"^\s*GRADE\s*:\s*([A-Z_]+)\s*$", re.I)
POLARITY_LINE = re.compile(r"^\s*POLARITY_OK\s*:\s*(yes|no)\b", re.I)
BOTH_LINE = re.compile(r"^\s*BOTH\s*:\s*(.+)$", re.I)


def grader_system_prompt():
  with open(GRADER) as f:
    return f.read().strip()


def prompt_hashes():
  if not os.path.exists(GRADER):
    return {}
  return {os.path.relpath(GRADER, ROOT):
          hashlib.sha256(open(GRADER, "rb").read()).hexdigest()}


def sha_of(obj):
  return hashlib.sha256(
      json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------------- a world

def _drop_population(world):
  """Remove the bridges' own population witnesses before submission."""
  dropped = [c["@name"] for c in world["compiled_bridge_clauses"]
             if c.get("@sourcetype") == "populate"]
  world["compiled_bridge_clauses"] = [
      c for c in world["compiled_bridge_clauses"]
      if c.get("@sourcetype") != "populate"]
  for h in world.get("bridge_hypotheses") or []:
    h["clause_names"] = [n for n in (h.get("clause_names") or [])
                         if n not in set(dropped)]
  return dropped


def run_world(view, rules, gk, options, world_id, tag, sidecar=None,
              seconds=None):
  """Compile a bridge set, append it to the graph theory, ask gk."""
  record = {"world_id": world_id, "tag": tag,
            "rules_offered": [r["rule_id"] for r in rules]}
  if not rules:
    clauses = list(view["final_clauses"])
    world = {"compiled_bridge_clauses": [], "clause_provenance": {},
             "bridge_hypotheses": [], "refused_by_the_compiler": [],
             "hypotheses_in_this_world": [], "compiler_routes": {},
             "rule_by_hypothesis_id": {}, "printed_by_hypothesis_id": {},
             "nothing_compiled": False}
    dropped = []
  else:
    world = compiler.build_world(world_id, rules, view, options, groups=(),
                                 weight=1.0, check_redundancy=True,
                                 hypothesis_case_id=view["case_id"])
    dropped = _drop_population(world)
    if world["nothing_compiled"]:
      record.update({"skipped": "no rule of this set converted to a clause",
                     "outcome": "compiler_refusal", "proofs": [],
                     "dynamic_proofs": [], "answers_returned": 0,
                     "refused_by_the_compiler":
                         world["refused_by_the_compiler"]})
      return record, world
    clauses = list(view["final_clauses"]) + [
        dict(c) for c in world["compiled_bridge_clauses"]]
  record.update({
      "refused_by_the_compiler": world["refused_by_the_compiler"],
      "hypotheses_offered": world["hypotheses_in_this_world"],
      "compiler_routes": world["compiler_routes"],
      "bridge_clause_count": len(world["compiled_bridge_clauses"]),
      "population_clauses_dropped": dropped,
      "all_clauses_have_block": BW.has_block(world["compiled_bridge_clauses"])
      if world["compiled_bridge_clauses"] else None,
      "clause_confidence_annotations": [
          c.get("@confidence") for c in world["compiled_bridge_clauses"]]})
  stored = {"stage1": view["stage1"], "stage2": view["stage2"],
            "final_clauses": view["final_clauses"],
            "input_text": view.get("input_text")}
  got = gk(clauses, stored, tag, seconds=seconds)
  proofs = procedure.proofs_of(got.get("raw") or "{}",
                               world["clause_provenance"])
  printed = world.get("printed_by_hypothesis_id") or {}
  for p in proofs:
    p["cited_rules"] = [world["rule_by_hypothesis_id"].get(h)
                        for h in p["cited_hypothesis_ids"]]
    p["cited_formulas"] = [printed.get(h) for h in p["cited_hypothesis_ids"]]
    p["cites_witness"] = witness_in_proof(p)
  outcome, result = procedure.classify_gk(got.get("raw") or "{}",
                                          got.get("answer"), proofs)
  # WP1.3: the gk verdict decides.  `proofs_of` reads proof steps out of the
  # raw output; only an "answer found" verdict makes them a proof.  A timeout
  # or an evidence-below-limit result that still carried steps was counted as
  # a proof in the pilot.
  import graph_ablation as AB
  if outcome != "proof" and not AB.on(AB.REVERT_VERDICT):
    proofs = []
  answers = [p["answer"] for p in proofs]
  polarities = set(_answer_key(a) for a in answers if a is not None)
  record.update({
      "gk_verdict_is_answer_found": outcome == "proof",
      "conflicting_polarities": len(polarities) > 1,
      "submitted_clause_count": len(clauses),
      "submitted_theory_sha256": sha_of(clauses),
      "gk_command": got.get("gk_command"),
      "gk_input_sha256": got.get("gk_input_sha256"),
      "gk_result_string": result, "outcome": outcome, "proofs": proofs,
      "dynamic_proofs": [p for p in proofs
                         if not p["cites_no_dynamic_hypothesis"]],
      "answers_returned": len(proofs),
      "conservative_formatter_answer": got.get("answer"),
      "seconds": got.get("seconds"), "error": got.get("error"),
      "raw_gk_output_sha256": hashlib.sha256(
          (got.get("raw") or "").encode()).hexdigest()})
  if sidecar is not None:
    record["sidecar"] = sidecar(world_id, clauses, got)
  else:
    record["raw_gk_output"] = got.get("raw")
  return record, world


# --------------------------------------------------- minimal sets, exclusion

def minimise(view, gk, options, case_id, rules_by_id, proof, budget, tag,
             sidecar=None, seconds=None):
  """Replay the cited set, then delete one bridge at a time."""
  cited = [rules_by_id[r] for r in proof["cited_rules"] if r in rules_by_id]
  if not cited:
    return {"minimised": False, "cited_rules": proof["cited_rules"],
            "cites_witness": bool(proof.get("cites_witness")),
            "why": "the proof cites no generated bridge"}
  if not budget():
    return {"minimised": False, "cited_rules": proof["cited_rules"],
            "why": "the gk budget was reached before the replay"}
  replay, _w = run_world(view, cited, gk, options,
                         "replay_%s_%s" % (case_id, tag),
                         "%s/replay %s" % (case_id, tag), sidecar, seconds)
  kept = [p for p in replay["proofs"] if p["answer"] == proof["answer"]]
  if not kept:
    return {"minimised": False, "cited_rules": proof["cited_rules"],
            "replay_answers": [p["answer"] for p in replay["proofs"]],
            "why": "the cited set alone did not reproduce the answer"}
  keep, deletions = list(cited), []
  for r in list(cited):
    if len(keep) <= 1 or not budget():
      break
    trial = [x for x in keep if x["rule_id"] != r["rule_id"]]
    got, _w = run_world(view, trial, gk, options,
                        "min_%s_%s_no_%s" % (case_id, tag, r["rule_id"]),
                        "%s/%s without %s" % (case_id, tag, r["rule_id"]),
                        sidecar, seconds)
    still = [p for p in got["proofs"] if p["answer"] == proof["answer"]]
    deletions.append({"removed": r["rule_id"], "printed": r["printed"],
                      "outcome": got["outcome"],
                      "removing_it_destroys_the_proof": not still})
    if still:
      keep = trial
  return {"minimised": True, "cited_rules": proof["cited_rules"],
          "minimal_rules": [r["rule_id"] for r in keep],
          "minimal_printed": [r["printed"] for r in keep],
          "size": len(keep), "answer": proof["answer"],
          "deletions": deletions,
          "cites_witness": bool(proof.get("cites_witness")
                                or any(p.get("cites_witness") for p in kept)),
          "note": "deletion-minimal, not globally minimum"}


def _pair_of(rule):
  """The judged pair a bridge came from, direction ignored."""
  if not rule:
    return None
  a, b = rule.get("graph_a"), rule.get("graph_b")
  if a is None and b is None:
    return None
  return tuple(sorted([str(a), str(b)]))


def exclusion_search(view, gk, options, case_id, pool_rules, rules_by_id,
                     first_minimal, budget, sidecar=None,
                     cap=MAX_EXCLUSION_WORLDS, seconds=None):
  """Exclude each bridge of the first minimal set and look for another proof.

  WP1.8: the alternative must be **pair-disjoint**.  Excluding one direction of
  a judged pair and finding the other direction is not a second route — it is
  the same guess read backwards, which is how folio-0046 passed the condition.
  Every bridge born of the excluded bridge's pair is removed together with it.
  """
  out = []
  for rid in list(first_minimal)[:cap]:
    if not budget():
      out.append({"excluded": rid, "skipped": "the gk budget was reached"})
      break
    pair = _pair_of(rules_by_id.get(rid))
    keep = [r for r in pool_rules
            if r["rule_id"] != rid
            and not (pair is not None and _pair_of(r) == pair)]
    dropped = [r["rule_id"] for r in pool_rules
               if r["rule_id"] != rid
               and pair is not None and _pair_of(r) == pair]
    if not keep:
      out.append({"excluded": rid, "skipped": "nothing is left to try",
                  "also_excluded_same_pair": dropped})
      continue
    got, _w = run_world(view, keep, gk, options,
                        "excl_%s_no_%s" % (case_id, rid),
                        "%s/excluding %s" % (case_id, rid), sidecar, seconds)
    out.append({"excluded": rid,
                "excluded_printed": rules_by_id[rid]["printed"]
                if rid in rules_by_id else None,
                "outcome": got["outcome"],
                "answers": [p["answer"] for p in got["proofs"]],
                "another_route": bool(got["dynamic_proofs"]),
                "also_excluded_same_pair": dropped,
                "pair_disjoint": True,
                "cited": [p["cited_rules"] for p in got["dynamic_proofs"]]})
  return out


def _answer_key(answer):
  """A hashable key for a gk answer.

  A wh question answers with a LIST of bindings, which cannot go into a set;
  the pilot crashed on core-0110 for exactly that.  Everything is rendered to
  a stable string instead.
  """
  if isinstance(answer, (list, tuple)):
    return json.dumps(answer, sort_keys=True, default=str)
  return json.dumps(answer, default=str)


def distinct_sets(minimal_rows):
  seen, out = set(), []
  for row in minimal_rows:
    if not row.get("minimised"):
      continue
    key = (_answer_key(row.get("answer")),
           tuple(sorted(row.get("minimal_rules") or [])))
    if key in seen:
      continue
    seen.add(key)
    out.append(row)
  return out


# ------------------------------------------------------------ the pooled run

def search(view, pools, gk, options, budget, sidecar=None, case_id=None,
           pool_seconds=None, stop_after_a_proof=True):
  """P0, then cumulative P1-P3.  -> the per-pool record."""
  case_id = case_id or view["case_id"]
  seconds = dict(pool_seconds or POOL_SECONDS)
  rules_by_id = {}
  for n in sorted(pools):
    for r in pools.get(n) or []:
      rules_by_id[r["rule_id"]] = r
  out, minimal_rows, stopped = [], [], None
  for n in [0] + sorted(pools):
    if not budget():
      stopped = "the gk budget was reached"
      break
    rules = list(pools.get(n) or []) if n else []
    if n and not rules:
      out.append({"pool": "P%d" % n, "skipped": "this pool adds no bridge"})
      continue
    if n and n > 1 and rules == list(pools.get(n - 1) or []):
      out.append({"pool": "P%d" % n, "skipped": "this pool adds no new bridge"})
      continue
    record, world = run_world(view, rules, gk, options,
                              "%s_p%d" % (case_id, n), "%s/P%d" % (case_id, n),
                              sidecar, seconds.get(n))
    row = {"pool": "P%d" % n, "bridges_offered": len(rules),
           "bridges_compiled": record.get("bridge_clause_count"),
           "outcome": record.get("outcome"),
           "gk_seconds": record.get("seconds"),
           "timeout": record.get("outcome") == "timeout",
           "answers": [p["answer"] for p in record.get("proofs") or []],
           "proofs": len(record.get("proofs") or []),
           "zero_bridge_proof": bool(n == 0 and record.get("proofs")),
           "refused_by_the_compiler": record.get("refused_by_the_compiler"),
           "world": record}
    got = record.get("proofs") or []
    for p in got:
      if n == 0:
        minimal_rows.append({"minimised": True, "pool": "P0",
                             "minimal_rules": [], "minimal_printed": [],
                             "size": 0, "answer": p["answer"],
                             "cited_rules": [],
                             "cites_witness": bool(p.get("cites_witness")),
                             "note": "a proof that uses no generated bridge"})
        continue
      m = minimise(view, gk, options, case_id, rules_by_id, p, budget,
                   "p%d" % n, sidecar, seconds.get(n))
      m["pool"] = "P%d" % n
      minimal_rows.append(m)
    out.append(row)
    if got and stop_after_a_proof:
      sets = distinct_sets(minimal_rows)
      first = (sets[0].get("minimal_rules") if sets else []) or []
      row["exclusion"] = exclusion_search(view, gk, options, case_id, rules,
                                          rules_by_id, first, budget, sidecar,
                                          seconds=seconds.get(n)) \
          if first else []
      stopped = "a proof was found in P%d and the exclusion pass has run" % n
      break
  return {"version": VERSION, "pools": out,
          "minimal_sets": distinct_sets(minimal_rows),
          "all_minimisations": minimal_rows,
          "stopping_reason": stopped,
          "rules_by_id": rules_by_id}


def proof_answers(result):
  """Every definite answer the graph search reached.

  gk returns the answer as a Boolean, so a `False` answer is falsy; testing it
  for truth would drop exactly the answers §8.6 makes a first-class target.
  """
  out = []
  for row in result["pools"]:
    for a in row.get("answers") or []:
      if a is not None and a not in out:
        out.append(a)
  return out


# ------------------------------------------------------------------ grading

def cited_rules(result):
  """The bridges any minimal set cites, in a stable order."""
  seen, out = set(), []
  for row in result["minimal_sets"]:
    for rid in row.get("minimal_rules") or []:
      if rid in seen:
        continue
      seen.add(rid)
      rule = result["rules_by_id"].get(rid)
      if rule:
        out.append(rule)
  return out


def english_of(rule):
  """The program's own reading of a bridge, for the grader."""
  def read(lit):
    atom, sign = lit["atom"], lit["sign"]
    if atom[0] == "isa":
      text = "X is %s" % str(atom[1]).replace("_", " ") \
          if atom[2].startswith("?") else "%s is %s" % (atom[2], atom[1])
    else:
      text = "%s holds between %s and %s" % (
          str(atom[1]).replace("_", " "), atom[2], atom[3])
    return ("it is not the case that " + text) if sign == "-" else text
  body = " and ".join(read(l) for l in rule["body"])
  head = read(rule["head"])
  return "if %s then normally %s" % (body, head)


def grade_message(rules, inventory, s1_json):
  """The grader's user message: the rules, their names' sentences, a reading."""
  import graph_judge as GJ
  import graph_stage2 as G2
  asked = set(G2.question_unit_ids(s1_json))
  lines = []
  for rule in rules:
    lines.append("RULE %s" % rule["rule_id"])
    lines.append("  formula: %s" % rule["printed"])
    lines.append("  reading: %s" % english_of(rule))
    lines.append("  direction: %s -> %s"
                 % (rule.get("graph_a"), rule.get("graph_b")))
    for label, name in (("first", rule.get("graph_a")),
                        ("second", rule.get("graph_b"))):
      for text in GJ._sentences_for(name, inventory, s1_json, skip=asked):
        lines.append("  the %s name occurs in: %s" % (label, text))
    if rule["head"]["sign"] == "-":
      lines.append("  this rule says the two exclude each other.")
    lines.append("")
  return "\n".join(lines).strip()


def parse_grades(text, rules):
  """-> {rule_id: {grade, polarity_ok, both}}.  A missing grade is UNCERTAIN."""
  got, current = {}, None
  for line in (text or "").splitlines():
    m = RULE_BLOCK.match(line)
    if m:
      current = m.group(1).strip()
      got.setdefault(current, {})
      continue
    if current is None:
      continue
    m = GRADE_LINE.match(line)
    if m:
      value = m.group(1).upper()
      got[current]["grade"] = value if value in GRADES else "UNCERTAIN"
      continue
    m = POLARITY_LINE.match(line)
    if m:
      got[current]["polarity_ok"] = m.group(1).lower() == "yes"
      continue
    m = BOTH_LINE.match(line)
    if m:
      got[current]["both"] = m.group(1).strip()[:300]
  out = {}
  for rule in rules:
    row = got.get(rule["rule_id"]) or {}
    out[rule["rule_id"]] = {
        "grade": row.get("grade") or "UNCERTAIN",
        "polarity_ok": row.get("polarity_ok"),
        "both": row.get("both"),
        "missing": rule["rule_id"] not in got,
        "printed": rule["printed"]}
  return out


def grade(result, inventory, s1_json, respond, case_id, mode="all"):
  """Grade the bridges a minimal set cites, one message per bridge.

  `mode="all"` is the v2 default: every cited bridge, one message each, so a
  bridge's grade is one cached call whose prompt does not depend on what else
  the proof cites.  `mode=True` grades only the bridges born from a pair the
  judge did not decide — measured and rejected.  `mode="set"` is the pilot's
  behaviour: every cited bridge, all in one message.
  """
  rules = cited_rules(result)
  if not rules:
    return {"graded": {}, "why": "no minimal set cites a generated bridge"}
  if mode == "set":
    text, err = respond("graph_grader", "%s/grade" % case_id,
                        grade_message(rules, inventory, s1_json))
    if err or not text:
      return {"graded": {}, "error": err or "the grader returned nothing",
              "rules": [r["rule_id"] for r in rules], "mode": "set"}
    grades = parse_grades(text, rules)
    return _grade_report(grades, rules, "set")

  want = rules if mode == "all" else [r for r in rules if uncertain_born(r)]
  grades, errors = {}, []
  for rule in want:
    # The rule id is minted per run, so it must not reach the message: a
    # bridge's prompt has to depend on the bridge alone, or the cache misses
    # whenever enumeration renumbers it.  Grade under a fixed name, map back.
    anon = dict(rule, rule_id="R")
    text, err = respond("graph_grader",
                        "%s/grade/%s" % (case_id, rule["rule_id"]),
                        grade_message([anon], inventory, s1_json))
    if err or not text:
      errors.append({"rule": rule["rule_id"],
                     "error": err or "the grader returned nothing"})
      continue
    got = parse_grades(text, [anon])
    grades[rule["rule_id"]] = dict(got["R"], printed=rule["printed"])
  report = _grade_report(grades, want, "per-bridge")
  report["errors"] = errors
  report["cited"] = [r["rule_id"] for r in rules]
  report["not_graded"] = [r["rule_id"] for r in rules if r not in want]
  report["why_not_graded"] = ("the judge decided the pair; its own label "
                              "stands (WP0.2)")
  return report


def _grade_report(grades, rules, mode):
  return {"graded": grades, "rules": [r["rule_id"] for r in rules],
          "mode": mode,
          "calls": len(rules) if mode == "per-bridge" else (1 if rules else 0),
          "distribution": _tally(g["grade"] for g in grades.values()),
          "polarity_ok_rate": _rate(g.get("polarity_ok")
                                    for g in grades.values()),
          "policy": ("a grade labels a proof and orders proof sets; it never "
                     "deletes a proof and never turns an answer into Unknown")}


def _tally(values):
  out = {}
  for v in values:
    out[v] = out.get(v, 0) + 1
  return out


def _rate(values):
  rows = [v for v in values if v is not None]
  if not rows:
    return None
  return round(sum(1 for v in rows if v) / float(len(rows)), 3)


# --------------------------------------------------------- the credibility

ACCEPTABLE_GRADES = ("LIKELY", "PLAUSIBLE")
MAX_CREDIBLE_BRIDGES = 2
MAX_CREDIBLE_POOL = 2


def grade_of(rule_id, rules_by_id, grades):
  """The grade a bridge carries.

  The grader supplies one when it runs.  With the grader off (the v2 default)
  the judge's own confidence stands in: HIGH/MEDIUM/LOW map to
  LIKELY/PLAUSIBLE/UNCERTAIN, so one acceptance policy reads either run.
  """
  import graph_judge as GJ
  got = (grades or {}).get(rule_id) or {}
  if got.get("grade"):
    return got["grade"], "grader"
  rule = (rules_by_id or {}).get(rule_id) or {}
  # An UNCERTAIN pair's confidence is the judge's confidence in saying "I do
  # not know", so it cannot stand in for a grade.  Only the grader can accept
  # a bridge born from an undecided pair.
  if uncertain_born(rule):
    return "UNCERTAIN", "the judge did not decide the pair and no grade came"
  conf = rule.get("confidence")
  if conf in GJ.GRADE_OF_CONFIDENCE:
    return GJ.GRADE_OF_CONFIDENCE[conf], "judge confidence"
  # a pair the judge DECIDED is accepted on that decision
  if pair_label_of(rule) in GJ.POOL1_LABELS:
    return "PLAUSIBLE", "judge label"
  return "UNCERTAIN", "no grade given"


def pair_label_of(rule):
  """The judge's own label for the pair a bridge came from.

  A running rule dict carries it as `graph_pair_label`; a closed record's
  bridge row surfaces the same value as `pair_label`.  Read either, so the
  policy gives the same answer during the run and when the record is scored.
  """
  rule = rule or {}
  return rule.get("graph_pair_label") or rule.get("pair_label")


def uncertain_born(rule):
  """True when the bridge came from a pair the judge did not decide."""
  import graph_judge as GJ
  return pair_label_of(rule) in (GJ.UNCERTAIN, GJ.RELATED)


# ------------------------------------------------------ the witness policy

def witness_in_proof(proof):
  """True when the gk proof cites a population witness.

  A witness is the converter's own `$some_C` / `$some_not_C` constant: the
  clause says "there is at least one C", which nothing in the English said.
  It is sound for a generic question read as a bare plural, and unsound as a
  counterexample to a universal one, so the proof has to say which it is.
  """
  return "$some_" in json.dumps(proof.get("proof") or [], default=str)


def cites_populate(row):
  """The recorded witness reading of a minimal set."""
  return bool(row.get("cites_witness"))


def _question_is_bare_plural_generic(s1_json):
  """The question asks about a kind, not about a named individual."""
  import graph_stage2 as G2
  try:
    asked = set(G2.question_unit_ids(s1_json))
    units = [(uid, unit) for uid, unit, _raw in G2.stage1_units(s1_json)
             if uid in asked]
  except Exception:
    return False
  if not units:
    return False
  for _uid, unit in units:
    blob = json.dumps(unit, default=str).lower()
    # a universal question is not answered by one invented individual
    for mark in ('"all"', '"every"', '"each"', '"universal"'):
      if mark in blob:
        return False
    text = str(unit.get("text") or "").lower()
    if text.startswith("are all ") or text.startswith("is every "):
      return False
  return True


def witness_verdict(row, s1_json):
  """Whether a witness-citing proof may be believed, and why not when it may not.

  A proof that cites a witness is credible only when the question is a hoisted
  bare-plural generic one AND the answer is the positive one.  A witness used
  to refute a universal question is a counterexample the converter invented;
  folio-0046 is the case that showed it.
  """
  if not cites_populate(row):
    return {"cites_witness": False, "ok": True, "counterexample": False,
            "why": "no population witness in the proof"}
  answer = direction_of(row.get("answer"))
  generic = _question_is_bare_plural_generic(s1_json)
  if answer == "False":
    return {"cites_witness": True, "ok": False, "counterexample": True,
            "why": "a population witness refuting the question is an invented "
                   "counterexample, not evidence"}
  if not generic:
    return {"cites_witness": True, "ok": False, "counterexample": False,
            "why": "the question is not a bare-plural generic one, so a "
                   "witness does not answer it"}
  return {"cites_witness": True, "ok": True, "counterexample": False,
          "why": "a positive answer to a bare-plural generic question"}


def direction_of(answer):
  """'True' / 'False' / None, from whatever shape the answer arrived in."""
  if answer is True or answer == "True" or answer == "true":
    return "True"
  if answer is False or answer == "False" or answer == "false":
    return "False"
  if isinstance(answer, (list, tuple)) and len(answer) == 1:
    return direction_of(answer[0])
  return None


def polarity_of(rule_id, grades):
  """False only when the grader positively said the polarity is wrong."""
  return (grades or {}).get(rule_id, {}).get("polarity_ok") is not False


def credible_set(row, rules_by_id, grades, evidence="any"):
  """-> (credible, the reasons it is not).  WP2.1, one definition for all.

  A P0 proof — no invented bridge at all — is credible by construction.
  """
  rids = list(row.get("minimal_rules") or [])
  why = []
  if not rids:
    return True, []
  if len(rids) > MAX_CREDIBLE_BRIDGES:
    why.append("more than %d bridges" % MAX_CREDIBLE_BRIDGES)
  for rid in rids:
    rule = (rules_by_id or {}).get(rid) or {}
    grade, _src = grade_of(rid, rules_by_id, grades)
    if grade not in ACCEPTABLE_GRADES:
      why.append("%s is graded %s" % (rid, grade))
    if not polarity_of(rid, grades):
      why.append("%s failed the polarity check" % rid)
    if rule.get("from_holistic"):
      why.append("%s came from the holistic call" % rid)
    pool = rule.get("pool")
    if isinstance(pool, int) and pool > MAX_CREDIBLE_POOL:
      why.append("%s is beyond pool P%d" % (rid, MAX_CREDIBLE_POOL))
    if evidence in ("stated", "combined") and evidence_of(rule) == "BACKGROUND":
      why.append("%s rests on background knowledge" % rid)
  return (not why), why


def evidence_of(rule):
  """The evidence tag a bridge carries, with two mechanical rules applied.

  A bridge born from a pair the judge did not decide is `BACKGROUND` whatever
  tag the reply gave it: the judge read the same sentences and could not say
  which way the implication runs, so the passage did not state it.

  `STATED` means one sentence says it.  When the two names never occur in one
  Stage-1 unit, no single sentence can have said it, and the tag is downgraded
  to `BACKGROUND` — the judge combined two sentences, or read a "some" as an
  "all".  Code decides this from `same_sentence`, so it costs no call and does
  not depend on the reply being honest about its own reasoning.

  The grader may still rate a downgraded bridge acceptable, which keeps it
  under `--evidence any` and drops it under `stated`.
  """
  rule = rule or {}
  if uncertain_born(rule):
    return "BACKGROUND"
  tag = rule.get("evidence") or "BACKGROUND"
  if tag == "STATED" and not rule.get("same_sentence"):
    return "BACKGROUND"
  return tag


def proof_evidence(row, rules_by_id):
  """A proof's evidence class: its weakest cited bridge.

  Any BACKGROUND bridge makes the proof a background proof; otherwise any
  STATED bridge makes it stated; only an all-LEXICAL proof is lexical.  A
  proof citing no bridge at all is `NONE`.
  """
  tags = [evidence_of((rules_by_id or {}).get(rid))
          for rid in (row.get("minimal_rules") or [])]
  if not tags:
    return "NONE"
  for weak in ("BACKGROUND", "STATED", "LEXICAL"):
    if weak in tags:
      return weak
  return "BACKGROUND"


def background_only(row, rules_by_id):
  """True when the set cites a BACKGROUND bridge (the `stated` column)."""
  return any(evidence_of((rules_by_id or {}).get(rid)) == "BACKGROUND"
             for rid in (row.get("minimal_rules") or []))


def set_origin(row, rules_by_id):
  """'none', 'decided' or 'undecided' — where a set's bridges came from."""
  rids = list(row.get("minimal_rules") or [])
  if not rids:
    return "none"
  return ("undecided"
          if any(uncertain_born((rules_by_id or {}).get(r)) for r in rids)
          else "decided")


# -------------------------------------------------------------------- tiers

T4 = "T4"     # a conservative detailed proof; the graph route never sets it
T3 = "T3"     # a lifted detailed bridge proof
T2 = "T2"     # a detailed proof after unit retranslation
T1A = "T1a"   # a graph proof that uses no generated bridge
T1 = "T1"     # a graph proof, at most two bridges, all LIKELY or PLAUSIBLE
T0 = "T0"     # a graph proof with an unassessed, unlikely or false bridge


def tier(result, grades, lifting=None, evidence="any"):
  """-> (the tier, why).  Never better than the evidence allows."""
  lifting = lifting or {}
  rules_by_id = result.get("rules_by_id") or {}
  graded = (grades or {}).get("graded") or {}
  if lifting.get("lifted_proof"):
    return T3, "the ordinary clauses plus the lifted bridges prove it"
  if lifting.get("retranslated_proof"):
    return T2, "the ordinary theory proves it after one unit was retranslated"
  sets = result.get("minimal_sets") or []
  if not sets:
    return None, "no graph proof"
  answers = set(_answer_key(row.get("answer")) for row in sets)
  opposite = len(answers) > 1
  if opposite:
    return T0, "graph proofs of both polarities exist"
  zero = [row for row in sets if row.get("size") == 0]
  if zero:
    return T1A, "a graph proof that uses no generated bridge"
  for row in sets:
    ok, _why = credible_set(row, rules_by_id, graded, evidence)
    if ok:
      return T1, ("a graph proof from %d bridge(s), each acceptable under the "
                  "v2 policy" % len(row.get("minimal_rules") or []))
  return T0, "no minimal set passes the acceptance policy"
