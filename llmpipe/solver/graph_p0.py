"""Layer 1 of the graph mechanism: the retranslation, and one gk call.

`-graphtrans`.  When the initial attempt leaves the question unresolved, the
case
is translated a second time into open triples, compiled under the frozen graph
configuration and given to gk once.  No judge, no grader, no invented bridge:
whatever this layer answers, it answers from the case's own words read a
second way.

Measured on the residual of four homogeneous arms, this is the whole product
on closed-world material (FOLIO 11 correct / 2 wrong, where the bridge layer
adds 2 correct and 7 wrong), and it costs about 1.2 LLM calls a case against
the bridge layer's 2.7.  It runs before the literal bridge for both reasons.

Three things happen here that happen nowhere else:

  * the checks of the P0 memo run with ONE corrective retry and no second;
  * every `normally` rule is capped at confidence 0.95, so a defeasible proof
    comes back as "Probably …" and never as a flat answer;
  * variant rules (plural -> singular, past -> present) are added when BOTH
    forms occur in the case, at 0.9 and marked `norm_<n>`, so a proof shows
    that it crossed a wording difference.
"""

import json
import re
import time

import graph_compile as GC
import graph_procedure as GPR
import graph_stage2 as G2

VERSION = "graph_p0/2026-08-17"

SECONDS = 5

# the P0 memo, §4.3: a defeasible rule never asserts at full confidence
NORMALLY_CAP = 0.95
VARIANT_CONFIDENCE = 0.9

NO_QUESTION = "no question package"
TRANSLATION_FAILED = "the graph translation failed"

# A malformed logical structure must never reach the compiler: it once let a
# conditional conclusion compile as an unconditional clause (gpt/ebn-0016).
# The single corrective retry may repair it; if it does not, layer 1 stops
# before compilation and before GK.
STRUCTURALLY_INVALID = "graph_translation_structurally_invalid"


def arity_issues(s2):
  """The `logical_operator_arity` issues of a graph Stage 2, if any."""
  if s2 is None:
    return []
  try:
    import graph_stage2 as GS
    return [i for i in GS.check_operator_arity(s2)
            if (i["kind"] if isinstance(i, dict) else i.kind)
            == "logical_operator_arity"]
  except Exception:                                              # noqa: BLE001
    return []


def _as_dicts(issues):
  out = []
  for i in issues or []:
    out.append(i if isinstance(i, dict)
               else {"kind": i.kind, "location": i.location,
                     "description": i.description, "evidence": i.evidence})
  return out

# a marked form whose base form also occurs is bridged one way only; nothing
# is written for a future or prospective auxiliary, where the tense is meaning
_NEVER = ("will_", "would_", "going_to_", "gets_to_", "could_", "should_",
          "may_", "might_", "must_")


def _plural_base(name):
  """The singular of a plural name, or None."""
  if name.endswith("ies") and len(name) > 4:
    return name[:-3] + "y"
  if name.endswith("ses") or name.endswith("xes") or name.endswith("ches") \
     or name.endswith("shes"):
    return name[:-2]
  if name.endswith("s") and not name.endswith("ss") and len(name) > 3:
    return name[:-1]
  return None


def _past_base(name):
  """The present of a past-tense name, or None.

  Only the shapes the P0 memo names: `had_X` -> `has_X`, `swam_…` -> `swims_…`,
  `built_…` -> `builds_…`.  A regular `-ed` verb maps to its `-s` form.
  """
  head = name.split("_")[0]
  rest = name[len(head):]
  irregular = {"had": "has", "was": "is", "were": "are", "swam": "swims",
               "built": "builds", "made": "makes", "took": "takes",
               "gave": "gives", "went": "goes", "grew": "grows",
               "held": "holds", "kept": "keeps", "left": "leaves",
               "lost": "loses", "met": "meets", "paid": "pays",
               "ran": "runs", "said": "says", "sold": "sells",
               "sent": "sends", "spent": "spends", "told": "tells",
               "wrote": "writes", "ate": "eats", "drank": "drinks",
               "found": "finds", "got": "gets", "knew": "knows",
               "saw": "sees", "thought": "thinks"}
  if head in irregular:
    return irregular[head] + rest
  if head.endswith("ied") and len(head) > 4:
    return head[:-3] + "ies" + rest
  if head.endswith("ed") and len(head) > 3:
    stem = head[:-2]
    if stem.endswith("e"):
      return stem + "s" + rest
    if re.search(r"(s|x|z|ch|sh)$", stem):
      return stem + "es" + rest
    return stem + "s" + rest
  return None


def variant_rules(clauses, s2_graph):
  """Rules bridging a marked form to its base form, when BOTH occur.

  Names are never rewritten and never collapsed: the rule is a clause the
  proof can show.  One direction only — a plural does not follow from its
  singular, and a past tense does not follow from a present one.
  """
  import graph_inventory as GI
  inv = GI.build(s2_graph, None)
  shape, arity = {}, {}
  for pool, kind in (("concepts", "concept"), ("relations", "relation")):
    for row in inv.get(pool) or []:
      name = row["name"]
      shape.setdefault(name, kind)
      if kind == "relation":
        arity[name] = 2
      else:
        arity[name] = 1
  out, n = [], 0
  seen = set()
  for name in sorted(shape):
    if any(name.startswith(x) for x in _NEVER):
      continue
    for base in (_plural_base(name), _past_base(name)):
      if not base or base == name or base not in shape:
        continue
      if shape[base] != shape[name] or arity[base] != arity[name]:
        continue
      key = (name, base)
      if key in seen:
        continue
      seen.add(key)
      n += 1
      out.append(_variant_clause(n, name, base, shape[name]))
  return out


def _variant_clause(n, marked, base, kind):
  """One `norm_<n>` clause: the marked form implies the base form, normally.

  Defeasible like every generated rule of this stack: a `$block` on the
  conclusion's own predicate, so a stated fact to the contrary wins.
  """
  if kind == "concept":
    body = ["-isa", marked, "?:X"]
    head = ["isa", base, "?:X"]
  else:
    body = ["-" + marked, "?:X", "?:Y"]
    head = [base, "?:X", "?:Y"]
  block = ["$block", ["$", str(head[0]), 1], ["-" + head[0]] + head[1:]]
  return {"@name": "norm_%d" % n,
          "@sourcetype": "graph_variant",
          "@confidence": VARIANT_CONFIDENCE,
          "@logic": ["or", body, head, block],
          "@variant": {"marked": marked, "base": base, "kind": kind,
                       "why": "both forms occur in this case; the marked form "
                              "implies the base form, not the reverse"}}


def cap_normally(clauses):
  """Every defeasible clause carries at most 0.95.  -> the number changed."""
  changed = 0
  for clause in clauses:
    if not isinstance(clause, dict):
      continue
    if clause.get("@sourcetype") == "graph_variant":
      continue
    if not _is_defeasible(clause):
      continue
    got = clause.get("@confidence")
    if got is None or got > NORMALLY_CAP:
      clause["@confidence"] = NORMALLY_CAP
      changed += 1
  return changed


def _is_defeasible(clause):
  """A clause the translator marked `normally`, however it was compiled."""
  if clause.get("@defeasible") or clause.get("@normally"):
    return True
  blob = json.dumps(clause.get("@logic"), default=str)
  return "$block" in blob or "normally" in blob


def drop_invented(clauses, sidecar):
  """Clauses that use a name the converter minted are not the case's own."""
  invented = set((sidecar.get("name_drift") or {})
                 .get("invented_by_the_converter") or [])
  if not invented:
    return clauses, []
  kept, dropped = [], []
  for clause in clauses:
    blob = json.dumps(clause.get("@logic"), default=str)
    if any('"%s"' % name in blob for name in invented):
      dropped.append(clause.get("@name"))
    else:
      kept.append(clause)
  return kept, dropped


# --------------------------------------------------------------- the layer

def run_graph_p0(text, s1_json, llm=None, version=None, max_tokens=None,
                 options=None, case_id=None, seconds=SECONDS, respond=None,
                 gk=None):
  """The whole of layer 1.  -> the record the pipeline stores and prints."""
  t0 = time.time()
  case_id = case_id or "case"
  out = {"version": VERSION, "case_id": case_id, "answer": None,
         "probably": False, "confidence": None, "answer_string": None,
         "stage2_graph": None, "issues_before": {}, "issues_after": {},
         "retries": 0, "variant_rules": [], "clauses": None,
         "gk_result": None, "gk_verdict": None, "proof": None, "llm_calls": 0,
         "gk_seconds": 0.0, "sidecar": None, "stopped_at": None}
  s2, translation = _translate_with_retry(case_id, s1_json, llm, version,
                                          max_tokens, out, text)
  out["translation"] = translation
  if s2 is None:
    out["stopped_at"] = translation.get("stopped_at") or TRANSLATION_FAILED
    out["seconds"] = round(time.time() - t0, 2)
    return out
  out["stage2_graph"] = s2
  opts = options if options is not None else _frozen_options()
  clauses, sidecar = GC.compile(s2, s1_json, options=opts, case_id=case_id)
  clauses, dropped = drop_invented(clauses, sidecar)
  out["dropped_invented_clauses"] = dropped
  variants = variant_rules(clauses, s2)
  clauses = list(clauses) + variants
  out["variant_rules"] = [{"name": c["@name"], "marked": c["@variant"]["marked"],
                           "base": c["@variant"]["base"],
                           "kind": c["@variant"]["kind"],
                           "confidence": c["@confidence"]}
                          for c in variants]
  out["capped_normally_rules"] = cap_normally(clauses)
  out["clauses"] = clauses
  out["sidecar"] = sidecar
  got = _call_gk(clauses, s1_json, s2, text, opts, seconds, gk)
  out["gk_seconds"] = got.get("seconds")
  # the short verdict ("answer found", "time limit", ...) and the whole result
  out["gk_verdict"] = got.get("result")
  out["gk_result"] = _parsed(got.get("raw"))
  out["gk_command"] = got.get("gk_command")
  out["proof"] = got.get("proof")
  out["answer_string"] = got.get("answer_string")
  out["answer"] = got.get("answer")
  out["confidence"] = got.get("confidence")
  out["probably"] = bool(got.get("confidence") is not None
                         and got.get("confidence") < 1.0
                         and got.get("answer") is not None)
  # An unconditional proof-validity check, independent of the optional -accept
  # policies: a definite answer whose proof rests on the question translation
  # alone is not evidence, so layer 1 reports unresolved and the pipeline may
  # continue to any later enabled stage.  The raw result is kept for audit.
  if out["answer"] is not None:
    refusal = question_only_proof(out.get("proof"), s1_json)
    if refusal:
      out["refused"] = refusal
      out["refused_answer"] = out["answer"]
      out["refused_answer_string"] = out["answer_string"]
      out["refused_confidence"] = out["confidence"]
      out["stopped_at"] = QUESTION_ONLY
      out["answer"] = None
      out["answer_string"] = None
      out["confidence"] = None
      out["probably"] = False
  out["seconds"] = round(time.time() - t0, 2)
  return out


def _frozen_options():
  """The graph converter configuration, over the live abstraction options."""
  import litbridge_converter as LC
  try:
    base = LC.live_options()
  except Exception:                                            # noqa: BLE001
    base = None
  return GC.graph_options(base)


def _translate_with_retry(case_id, s1_json, llm, version, max_tokens, out,
                          text):
  """One translation, one corrective retry on the checks, and no second."""
  s2, record = GPR.translate(case_id, s1_json, llm, version, max_tokens,
                             None, 1, text)
  out["llm_calls"] += 1
  out["issues_before"] = _kinds(record.get("issues"))
  first_arity = arity_issues(s2)
  record["arity_issues_first"] = _as_dicts(first_arity)
  if s2 is None:
    return None, record
  if not record.get("issues") and not first_arity:
    out["issues_after"] = {}
    return s2, record
  correction = _correction_text(record["issues"])
  s2b, record_b = GPR.translate(case_id, s1_json, llm, version, max_tokens,
                                None, 1, text, stats=None,
                                correction=correction)
  out["llm_calls"] += 1
  out["retries"] = 1
  record["retry_correction"] = correction
  if s2b is None:
    # the retry lost the translation.  Keeping the first response is only safe
    # when it is structurally sound; a malformed one must not reach compile.
    out["issues_after"] = out["issues_before"]
    record["retry_failed"] = record_b.get("stopped_at") or TRANSLATION_FAILED
    if first_arity:
      record["stopped_at"] = STRUCTURALLY_INVALID
      record["structurally_invalid"] = {
        "where": "first response kept after the retry failed",
        "arity_issues": _as_dicts(first_arity)}
      return None, record
    return s2, record
  out["issues_after"] = _kinds(record_b.get("issues"))
  record_b["retry_correction"] = correction
  record_b["issues_before_retry"] = record.get("issue_kinds")
  record_b["arity_issues_first"] = _as_dicts(first_arity)
  retry_arity = arity_issues(s2b)
  record_b["arity_issues_retry"] = _as_dicts(retry_arity)
  if retry_arity:
    # the retry was told about it and still returned a malformed formula
    record_b["stopped_at"] = STRUCTURALLY_INVALID
    record_b["structurally_invalid"] = {
      "where": "corrective retry still malformed",
      "arity_issues": _as_dicts(retry_arity)}
    record_b["first_response_stage2"] = s2
    return None, record_b
  return s2b, record_b


def _kinds(issues):
  out = {}
  for issue in issues or []:
    kind = issue["kind"] if isinstance(issue, dict) else issue.kind
    out[kind] = out.get(kind, 0) + 1
  return out


def _correction_text(issues):
  """What the retry is told: every issue, by package, in the model's terms."""
  lines = ["The previous translation has these problems. Write the whole "
           "translation again, fixing them and changing nothing else."]
  for issue in issues:
    kind = issue["kind"] if isinstance(issue, dict) else issue.kind
    where = issue["location"] if isinstance(issue, dict) else issue.location
    what = (issue["description"] if isinstance(issue, dict)
            else issue.description)
    lines.append("- [%s] %s: %s" % (kind, where, what))
  return "\n".join(lines)


# Sources that carry no evidence of their own and must not count when asking
# whether a proof rests on anything but the question.
BOOKKEEPING_SOURCES = ("$auto_negated_question", "assumption", "goal",
                       "question", "$ans", "negated_question")

QUESTION_ONLY = "question_only_graph_proof"


def proof_sources(proof):
  """Clause names a gk proof actually cites, from its `["in", NAME, ...]` steps.

  Read from the proof itself rather than from `@sourcetype`, because some
  generated question clauses lose that annotation.
  """
  names = []
  steps = proof if isinstance(proof, list) else []
  if isinstance(proof, dict):
    for ans in proof.get("answers") or []:
      for k in ("proof", "positive proof", "negative proof"):
        if isinstance(ans.get(k), list):
          steps = ans[k]
          break
      break
  for step in steps:
    if not isinstance(step, list) or len(step) < 2:
      continue
    why = step[1]
    if (isinstance(why, list) and len(why) > 1 and why[0] == "in"
        and isinstance(why[1], str)):
      names.append(why[1])
  seen, out = set(), []
  for n in names:
    if n not in seen:
      seen.add(n)
      out.append(n)
  return out


def _is_bookkeeping(name):
  low = str(name).strip().lower()
  if low in BOOKKEEPING_SOURCES:
    return True
  # representation-conversion definitions carry no case evidence
  return low.startswith("frm_") or low.startswith("$")


def question_clause_names(s1_json):
  """Graph clause names of the Stage-1 question units, normally `sent_Sx`."""
  import graph_stage2 as GS
  out = set()
  for uid in GS.question_unit_ids(s1_json) or []:
    out.add("sent_%s" % uid)
    out.add(str(uid))
  return out


def question_only_proof(proof, s1_json):
  """-> the refusal record when the proof rests on the question alone.

  Refused only when at least one substantive source remains after the
  bookkeeping ones are set aside, AND every one of those is a Stage-1 question
  unit.  A proof citing any passage unit, background clause or substantive
  axiom is never refused.
  """
  qnames = question_clause_names(s1_json)
  cited = proof_sources(proof)
  substantive = [n for n in cited if not _is_bookkeeping(n)]
  if not substantive:
    return None
  if not all(n in qnames for n in substantive):
    return None
  return {"reason": QUESTION_ONLY,
          "question_units": sorted(qnames & set(substantive)),
          "proof_sources": cited}


def _call_gk(clauses, s1_json, s2_graph, text, opts, seconds, gk=None):
  """One gk call over the graph theory, read the pipeline's way."""
  import globals as g
  import procproofs
  import prover
  if gk is not None:
    return gk(clauses, s1_json, s2_graph, text, seconds)
  t0 = time.time()
  before_collect = g.options.get("_collect")
  before_seconds = g.options.get("prover_seconds")
  g.options["_collect"] = {}
  if seconds:
    g.options["prover_seconds"] = seconds
  out = {"answer": None, "answer_string": None, "confidence": None,
         "result": None, "proof": None}
  render = GC.render_options()
  try:
    raw = prover.call_prover(clauses, s1_json=s1_json)
    # `to_stage2` is the controlled form of the same triples, so `entity_map`'s
    # `is rel2` scan sees the relation names; `open_names` says the names are
    # the case's own words, so the renderer does not conjugate them.
    with GC.open_names():
      got = procproofs.process_proof(raw, text=text, s1_json=s1_json,
                                     s2_json=GC.to_stage2(s2_graph),
                                     logic=clauses, options=render)
    if isinstance(got, tuple):
      got = got[0]
    out["answer_string"] = got
    out["answer"] = _polarity(got)
    out["confidence"] = _confidence(got, raw)
    out["result"] = _result_string(raw)
    out["raw"] = raw
    out["proof"] = _proof_steps(raw)
  except Exception as e:                                       # noqa: BLE001
    out["error"] = "%s: %s" % (type(e).__name__, e)
  finally:
    out["gk_command"] = (g.options.get("_collect") or {}).get("gk_command")
    if before_collect is None:
      g.options.pop("_collect", None)
    else:
      g.options["_collect"] = before_collect
    if seconds:
      if before_seconds is None:
        g.options.pop("prover_seconds", None)
      else:
        g.options["prover_seconds"] = before_seconds
  out["seconds"] = round(time.time() - t0, 2)
  return out


_HEDGE = re.compile(r"^(likely|probably|possibly)\s+", re.I)


def _polarity(answer_string):
  """True / False / None, from the pipeline's own answer string."""
  head = str(answer_string or "").strip().split("\n")[0].strip().rstrip(".")
  head = _HEDGE.sub("", head).lower()
  if head.startswith("true"):
    return True
  if head.startswith("false"):
    return False
  return None


def _confidence(answer_string, raw):
  """gk's own confidence for the answer, 1.0 when it asserted flatly."""
  if _polarity(answer_string) is None:
    return None
  if _HEDGE.match(str(answer_string or "").strip()):
    got = _raw_confidence(raw)
    return got if got is not None else 0.9
  got = _raw_confidence(raw)
  return 1.0 if got is None else got


def _raw_confidence(raw):
  try:
    data = json.loads(raw) if isinstance(raw, str) else raw
  except (ValueError, TypeError):
    return None
  for answer in ((data or {}).get("answers") or []):
    got = answer.get("confidence")
    if isinstance(got, (int, float)):
      return float(got)
  return None


def _parsed(raw):
  """The gk result as JSON, so the record carries it the way `proof` is kept."""
  if raw is None:
    return None
  try:
    return json.loads(raw) if isinstance(raw, str) else raw
  except (ValueError, TypeError):
    return None


def _result_string(raw):
  try:
    data = json.loads(raw) if isinstance(raw, str) else raw
  except (ValueError, TypeError):
    return None
  return (data or {}).get("result")


def _proof_steps(raw):
  """The proof lists of the first answer, for the -explain block."""
  try:
    data = json.loads(raw) if isinstance(raw, str) else raw
  except (ValueError, TypeError):
    return None
  for answer in ((data or {}).get("answers") or []):
    for key in ("positive proof", "negative proof", "proof"):
      if answer.get(key):
        return answer[key]
  return None
