# Terminal display for the pipeline.
#
# Everything `solve.py` prints above the answer itself: the summary block, the
# per-stage blocks of `-explain` and above, and the two `-logic` helpers.  It
# is formatting only -- no stage runs here and no decision is made here -- so
# the pipeline module holds the pipeline.
#
# The two pieces of summary state live here as well, because nothing outside
# this module reads them: `english_to_answer` holds the summary back while a
# nested run is in progress and releases it at the end, through `suppress()`
# and `flush()`.
#
# `solve` imports this module and re-exports every name below, because local
# fixtures call `solve._print_graphbridge` and `solve._print_graph_theory`
# directly.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

import json

import globals
import lc_encoding
import pretty


def _debug():
  """True under `-debug`.  `solve.debug` mirrors this option."""
  return bool(globals.options.get("debug_print_flag"))


# The last summary built, and whether printing it is held back.  A critic rerun
# re-enters the pipeline, so the inner run must not print a block of its own.
_last_summary = None
_suppress_summary = False

# The stages that have already announced themselves in this case.  A stage
# announces once per case, so the set is cleared when a case begins:
# `_english_to_answer_body` calls `reset_announced()`.
_announced = set()


def reset_announced():
  """Start a new case: every stage may announce itself again."""
  _announced.clear()


def suppress(value):
  """Hold the summary back (True) or allow it (False).  Resets the held one."""
  global _suppress_summary, _last_summary
  _suppress_summary = bool(value)
  if value:
    _last_summary = None


def flush():
  """Print the held summary, if there is one.  -> True when one was printed."""
  if _last_summary is None:
    return False
  _show_summary(_last_summary)
  return True


def last_summary():
  """-> the summary record last built, or None."""
  return _last_summary



# ---- helpers the printers share -------------------------------------

def _loud_enough():
  """True from `-logic` up: the level at which the pipeline shows its blocks."""
  return bool(globals.options.get("show_logic_flag")
              or globals.options.get("show_details_flag")
              or globals.options.get("debug_print_flag"))

def _announce_stage(name, late=False):
  """One line naming the stage whose blocks follow.

  A stage after the initial attempt parses, converts and calls gk again, and its
  blocks carry the ordinary headers — `=== stage 2 (logic JSON, …) ===`,
  `=== prover input (JSON) ===` and the rest.  This line is what says whose
  they are, so it is printed only at the levels where those headers actually
  repeat: `-details` and above, and `-logic` for a stage that prints a clause
  block there (`late=True`, printed by the block itself).  At most one line
  per stage per run.  `-explain` prints none: it shows the answer and its
  proof, as it does for an answer the initial attempt found.
  """
  loud = bool(globals.options.get("show_details_flag")
              or globals.options.get("debug_print_flag"))
  if late:
    loud = loud or bool(globals.options.get("show_logic_flag"))
  if not loud or name in _announced:
    return
  _announced.add(name)
  print("\n--- stage: %s ---" % name)

def _graph_atoms(node, out=None):
  out = [] if out is None else out
  if not isinstance(node, list) or not node:
    return out
  if all(not isinstance(x, list) for x in node) and isinstance(node[0], str):
    if node[0] not in ("or", "and", "$block", "$"):
      out.append(node)
    return out
  for sub in node:
    if isinstance(sub, list):
      _graph_atoms(sub, out)
  return out


# ---- the summary block ------------------------------------------------

def _print_summary(answer, answered_by, front_door_answer, state=None,
                   rerun_answered_by=None, stages=None):
  """`-summary`: who answered and what it cost, whatever the output level."""
  global _last_summary
  import solve                  # deferred: solve.py imports this module
  rec = solve._summary_record(answer, answered_by, front_door_answer, state,
                        rerun_answered_by=rerun_answered_by, stages=stages)
  _last_summary = rec
  if _suppress_summary:
    return
  _show_summary(rec)


def _show_summary(rec):
  if globals.options.get("summary_json_flag"):
    print(json.dumps(rec, default=str))
    if not globals.options.get("summary_flag"):
      return
  print("\n=== summary ===")
  print("answer: %s" % rec["answer"])
  by = rec["answered_by"]
  if rec.get("rerun_answered_by") in ("fallback_norm", "fallback_hyp"):
    by = "%s (rerun answered by %s)" % (by, rec["rerun_answered_by"])
  print("answered_by: %s   (front door: %s)"
        % (by, rec["front_door_answer"]))
  print("stages_enabled: %s" % (", ".join(rec["stages_enabled"]) or "none"))
  print("abstraction_order: %s" % rec["abstraction_order"])
  if rec.get("encoding_experiments"):
    # only when set: an ordinary run has none, and a line saying "none" every
    # time would train a reader to skip it
    print("encoding_experiments: %s   (LLMPIPE_ABSEXP)"
          % ", ".join(rec["encoding_experiments"]))
  parts = []
  for tag in sorted(rec["llm_call_counts"]):
    cell = rec["llm_call_counts"][tag]
    bits = "live %d" % cell["live"]
    if cell["retries"]:
      bits += ", retries %d" % cell["retries"]
    parts.append("%s %d (%s)" % (tag, cell["calls"], bits))
  print("llm calls: %s; total %d, live %d"
        % ("; ".join(parts) or "none", rec["llm_calls_total"],
           rec["llm_calls_live"]))
  print("routes run: %s" % "; ".join(rec["routes"]))

def _print_critic(record):
  """The `-explain` block of the critique pass."""
  print("\n=== critic (one reading of the front door's translation) ===")
  report = record.get("report")
  if not report:
    print("  no usable reply: %s" % (record.get("parse_failure") or "?"))
    return
  print("  reading: %s   chain: %s"
        % (report["answer_by_reading"], ", ".join(report["chain"]) or "-"))
  for f in report["findings"]:
    print("  [%s, %s] %s: %s"
          % (f["kind"], f["severity"], ", ".join(f["units"]),
             f["problem"][:110]))
  if report.get("dropped_findings"):
    print("  dropped %d finding(s) (unquoted or malformed)"
          % len(report["dropped_findings"]))
  print("  verdict: %s%s" % (record["verdict"],
                             ("" if record["verdict"] == "KEEP"
                              else " (stage %s, units %s)"
                              % (record["stage"],
                                 ", ".join(record["units_to_redo"])))))
  if record.get("rerun_changed_units"):
    got = record["rerun_changed_units"]
    print("  corrective call: %s (stage %s)"
          % (record.get("corrective_call") or "?",
             record.get("corrective_stage") or 2))
    print("  rerun changed units %s%s; answer after rerun: %s"
          % (", ".join(got["changed"]) or "none",
             ("; unasked %s" % ", ".join(record["unasked_units"])
              if record.get("unasked_units") else ""),
             str(record.get("answer_after") or "").split("\n")[0]))

def _print_stages(rows):
  """The stages block: which stages ran, and which one produced the answer."""
  if not (rows and _loud_enough()):
    return
  print("\n=== stages ===\n")
  for row in rows:
    mark = "  <- the answer" if row.get("answered") else ""
    if not row.get("ran"):
      print("  %-14s %s%s" % (row["stage"], row.get("why") or "not run", mark))
      continue
    print("  %-14s ran   %s%s"
          % (row["stage"], row.get("answer") or "no answer", mark))

def _print_graph_theory(got, s1_json=None, llm=None):
  """The second translation's own copies of the ordinary output blocks.

  The headers are the ordinary ones: what marks the blocks as the second
  translation's is the `--- stage: … ---` line printed before the route ran,
  not a different vocabulary in every header.  `-logic` adds
  the clause list with its source comments, `-details` the Stage-2 JSON and
  the prover result.  The prover input and params are printed by
  `prover.call_prover` itself, as for any call.
  """
  show_logic = globals.options.get("show_logic_flag")
  show_details = globals.options.get("show_details_flag")
  if not (show_logic or show_details or _debug()):
    return
  clauses = got.get("clauses")
  if show_details or _debug():
    if got.get("stage2_graph") is not None:
      print("\n=== stage 2 (logic JSON, %s) ===\n" % (llm or ""))
      print(json.dumps(got["stage2_graph"], indent=2))
  if (show_logic or _debug()) and clauses:
    # the same renderer the initial attempt's block uses, so the two read alike
    from proof_render import compute_ambiguity as _compute_ambiguity
    from utils import format_sentences_to_clauses
    _announce_stage("graphtrans", late=True)
    try:
      _compute_ambiguity(clauses)
      print("\n" + format_sentences_to_clauses(
          clauses, s1_json,
          json_mode=bool(globals.options.get("json_flag"))) + "\n")
    except Exception as e:                                      # noqa: BLE001
      print("  (clause block not renderable: %s)" % e)
  if show_details or _debug():
    if got.get("gk_result") is not None:
      print("\n=== prover result (JSON) ===\n")
      print(json.dumps(got["gk_result"], indent=2))

def _print_graphtrans(got, verbose=False):
  """The layer-1 block of `-explain` and above."""
  print("\n=== the second translation, step by step ===")
  tr = got.get("translation") or {}
  m = (tr.get("measurements") or {})
  before = got.get("issues_before") or {}
  after = got.get("issues_after") or {}
  line = "  translation: %s units, %s atoms" % (m.get("units", "?"),
                                                m.get("atoms", "?"))
  if before:
    line += "; checks fired: %s" % ", ".join(
        "%s x%d" % (k, v) for k, v in sorted(before.items()))
    line += " -> retried once" if got.get("retries") else " -> not retried"
    line += "; after retry: %s" % ("clean" if not after else ", ".join(
        "%s x%d" % (k, v) for k, v in sorted(after.items())))
  else:
    line += "; checks: clean"
  print(line)
  for rule in got.get("variant_rules") or []:
    print("  variant rule %s: %s -> normally %s @%s"
          % (rule["name"], rule["marked"], rule["base"], rule["confidence"]))
  if got.get("dropped_invented_clauses"):
    print("  dropped %d clause(s) using a name the converter invented"
          % len(got["dropped_invented_clauses"]))
  if got.get("stopped_at"):
    print("  stopped: %s" % got["stopped_at"])
    return
  if got.get("answer") is None:
    print("  gk: no answer")
    return
  # the first line only: the explanation, when there is one, is printed with
  # the answer at the end of the run
  print("  gk: answer found, confidence %s -> %s"
        % (got.get("confidence"),
           str(got.get("answer_string") or "").split("\n")[0]))
  if verbose and got.get("proof"):
    for line in _graph_proof_lines(got["proof"]):
      print("    %s" % line)

def _graph_proof_lines(proof):
  """A graph proof as plain atoms: `pred(arg, …)  [name]`, negation spelled.

  The open names are the case's own words, not the ordinary vocabulary, so
  they are never routed through the English renderer.
  """
  out = []
  for block in (proof or []):
    for step in (block or []):
      text = _graph_step_line(step)
      if text:
        out.append(text)
  return out[:40]

def _graph_step_line(step):
  import json as _json
  blob = step if isinstance(step, (list, dict)) else None
  if blob is None:
    return str(step)[:120]
  name = ""
  if isinstance(blob, list) and blob and isinstance(blob[0], str):
    name = blob[0]
  literals = []
  for atom in _graph_atoms(blob):
    pred = str(atom[0])
    sign = "not " if pred.startswith("-") else ""
    pred = pred[1:] if pred.startswith("-") else pred
    literals.append("%s%s(%s)" % (sign, pred,
                                  ", ".join(str(x) for x in atom[1:])))
  if not literals:
    return _json.dumps(blob, default=str)[:120]
  return "%s%s" % (" or ".join(literals), ("  [%s]" % name) if name else "")

def _print_litbridge(records, verbose=False, options=None):
  """Show what each bridge round did, for -logic and above."""
  print("\n=== litbridge (the ordinary run left the question unresolved) ===\n")
  if options is not None:
    print("  converted as the theory was: %s" % _litbridge_encoding(options))
  for rec in records:
    number = rec.get("round", 0)
    if not number:
      print("  not started: %s" % rec.get("stopped_at"))
      continue
    print("  round %d:" % number)
    if rec.get("stopped_at"):
      print("    stopped at: %s" % rec["stopped_at"])
    if not rec.get("asked"):
      print("    no LLM call")
    print("    candidate atoms shown to the model: %s"
          % rec.get("candidate_atoms", 0))
    print("    rules written: %d, clauses added: %d"
          % (rec.get("rules", 0), rec.get("clauses", 0)))
    for label, key in (("distinctness", "distinctness"),
                       ("negative relation", "negative_relation")):
      got = rec.get(key)
      if got is None:
        continue
      if got.get("asked"):
        print("      %s channel: asked, %d eligible pair(s), %d rule(s)"
              % (label, got.get("eligible_pairs", 0), got.get("rules", 0)))
      else:
        print("      %s channel: no call (%s)"
              % (label, got.get("why_not_asked") or "no eligible pair"))
    for printed in rec.get("printed_rules") or []:
      print("      " + printed)
    if rec.get("gk_called"):
      print("    gk called again: %s"
            % ("a proof was found" if rec.get("resolved")
               else "still no proof"))
    else:
      print("    gk not called again (no clause to add)")
    if not verbose:
      continue
    counts = rec.get("signed_counts") or {}
    if counts:
      print("      conclusions: %d positive, %d negative"
            % (counts.get("positive_conclusion", 0),
               counts.get("negative_conclusion", 0)))
    for row in rec.get("refused_by_the_compiler") or []:
      print("      refused: %s  (%s)" % (row.get("printed"), row.get("why")))
    rejected = rec.get("rejections_by_category") or {}
    if rejected:
      print("      rules the parser rejected: %s"
            % ", ".join("%s %s" % (k, v) for k, v in sorted(rejected.items())))
    for row in rec.get("omitted_by_the_hypothesis_limit") or []:
      print("      over the hypothesis limit: %s" % row)

def _litbridge_encoding(options):
  """The part of the bridge's option set worth showing: what it encodes to.

  Only the axes `lc_encoding.EncodingConfig` reads, so the line says what the
  clauses look like and not which flags the run happened to carry.
  """
  if not isinstance(options, dict):
    return str(options)
  axes = [name for name in lc_encoding.EncodingConfig.__slots__
          if options.get(name + "_flag") is True]
  return "event %s; %s" % (options.get("event_base"),
                           ", ".join(axes) if axes
                           else "no abstraction primitive")

def _print_graphbridge(record, verbose=False):
  """Show what the graph route did, for -logic and above."""
  print("\n=== the second translation and its invented rules, step by "
        "step ===\n")
  if record.get("stopped_at"):
    print("  stopped at: %s" % record["stopped_at"])
  translation = record.get("translation") or {}
  if translation:
    m = translation.get("measurements") or {}
    print("  translation: %d package(s), %d atom(s), %d name(s); %s"
          % (m.get("packages", 0), m.get("atoms", 0),
             m.get("distinct_names", 0),
             "no structural issue" if translation.get("valid")
             else "issues: %s" % ", ".join(translation.get("issue_kinds")
                                           or [])))
  theory = record.get("graph_theory") or {}
  if theory:
    print("  graph theory: %d clauses" % theory.get("clauses", 0))
  inv = record.get("inventory") or {}
  if inv:
    print("  names: %d concept, %d relation, %d kind constant; "
          "%d supplied, %d demanded"
          % (inv.get("concept_names", 0), inv.get("relation_names", 0),
             inv.get("kind_constants", 0), inv.get("supply_names", 0),
             inv.get("demand_names", 0)))
  print("  pairs: %d enumerated, %d refused"
        % (record.get("pairs_enumerated", 0),
           len(record.get("pairs_refused") or [])))
  labels = record.get("labels") or {}
  if labels:
    print("  labels: %s" % ", ".join("%s %d" % (k, v)
                                     for k, v in sorted(labels.items())))
  per_pool = record.get("bridges_per_pool") or {}
  if per_pool:
    print("  bridges: %s" % ", ".join("%s %d" % (k, v)
                                      for k, v in sorted(per_pool.items())))
  for row in record.get("pools") or []:
    if row.get("skipped"):
      print("    %s: %s" % (row["pool"], row["skipped"]))
      continue
    print("    %s: %d bridge(s), %s, %s"
          % (row["pool"], row.get("bridges_offered", 0), row.get("outcome"),
             ", ".join(str(a) for a in row.get("answers") or [])
             or "no answer"))
  for row in record.get("minimal_sets") or []:
    print("    minimal set (%s): %s -> %s"
          % (row.get("pool"), ", ".join(row.get("minimal_rules") or [])
             or "no bridge", row.get("answer")))
  grades = (record.get("grades") or {}).get("distribution")
  if grades:
    print("  grades of the cited bridges: %s"
          % ", ".join("%s %d" % (k, v) for k, v in sorted(grades.items())))
  lifting = record.get("lifting") or {}
  if lifting.get("attempted"):
    print("  lifting: %s" % (lifting.get("outcome") or "nothing to lift"))
  elif lifting:
    print("  lifting: not attempted (%s)" % lifting.get("why"))
  if record.get("tier"):
    print("  tier %s: %s" % (record["tier"], record.get("tier_reason")))
  if not verbose:
    return
  for row in record.get("judged") or []:
    print("      %-24s %-24s %s" % (row["a"], row["b"], row["judge_label"]))
  for row in record.get("pairs_refused") or []:
    print("      refused %-20s %-20s %s" % (row["a"], row["b"], row["why"]))
  for row in record.get("bridges") or []:
    print("      %s  %s" % (row["rule_id"], row["printed"]))
  for row in record.get("bridge_omissions") or []:
    print("      omitted: %s" % row.get("why"))

def _show_simplified_to(text, s1_json):
  """Show the 'simplified to' block if ASU texts differ from the input."""
  asu_texts = []
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for unit in pkg.get("units", []):
      if isinstance(unit, dict) and unit.get("text"):
        asu_texts.append(unit["text"])
  if not asu_texts:
    return
  simplified = "\n".join(asu_texts)
  if simplified.strip() == text.strip():
    return
  print("\n=== simplified to ===\n")
  for t in asu_texts:
    print(t)
