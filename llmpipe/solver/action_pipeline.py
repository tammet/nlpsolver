"""The action route: texts about actions and plans, from English to the answer.

  run(text, options, collect=None, llm=None, version=None, max_tokens=None) -> the answer string
  translate(text, bundle, llm=None, version=None, max_tokens=None, think=False) -> a translation record
  resolve(options)                                                        -> the action profile, or OptionError
  load_bundle(name=None)                                                  -> an action prompt bundle, or None

`solve.english_to_answer` calls `run` when the call goes to the action route (`solve.route_choice`).  The steps of
one call, with the module and function of each:

  translate       action_pipeline.translate: Stage 1, then Stage 2, each checked and corrected.  action_prompt holds
                  the annotation and handoff checks, action_repair the recorded repairs, action_json the reading of
                  the model's JSON.
  compile source  action_route.compile_source: lc_action (structure and law forms), lc_action_situate (situations
                  and clauses), then the passes of the physical profile: lc_action_library, lc_action_avail,
                  lc_action_restrict, lc_action_effects.
  compile query   action_route.compile_query: lc_action.validate_query, then lc_action_query (views, obligations).
  prove           action_gk.run_query: one GK launch per obligation and polarity.
  decide          action_answer.decide; action_replay.replay checks every plan and supplied sequence.
  answer text     action_english.answer_text.
  output levels   action_display.

`run` calls `action_answer.solve`; `action_route.translate_source` and `solve_query` are the same operations as a
library interface for the checks.  docs/architecture/action-route.md describes the steps.

The ordinary pipeline is not entered: no ordinary retry stage, critic, graph or literal bridge, and no ordinary
representation rewrite runs, and none is recorded as enabled.  An explicit request for one of them is an error
(`resolve`), never a hybrid theory.  The route sets only the model-call keys in `globals.options`, for the length of
the call (`call_settings`), and writes nothing into the module globals of `llmparse`, so a later ordinary call in
the same process sees what it would have seen without it.

Input.  English text goes through the action prompt bundle: Stage 1, then Stage 2, each checked, each with at most
MAX_CORRECTIONS corrections, and at most MAX_LOGICAL_CALLS logical model calls, plus SEMANTIC_CORRECTIONS for the
request about invented class conditions.  The query packages are separated from the source packages; the source is
compiled once and the query attached.  With `-formal` the input is a formal record (the field names of the gold
fixtures) and no model is called.

Prompt bundles.  A bundle is two assembled system prompts, kept in the bundle record with their SHA-256, never in
`llmparse`'s globals.  The default bundle is the action prompts, `actions` (`prompts/actions/`, assembled by
`action_prompt.assemble`).  Missing prompt files give a typed `not_implemented` result.  Tests register fake bundles
and fake responders, labelled as such; they measure plumbing, not prompt fidelity.

Accounting.  Every model call goes through `llmcall.call_llm` under the tag `actions`, so the shared cache, model
lock, call limit, per-call deadline and call log apply.  The route's record counts logical calls (cached or live) and
provider attempts separately.  A refused call is `call_limit`, a timeout `model_timeout`, another provider failure
`model_error`.  GK launches are appended to the run collector's `gk_calls`, as ordinary prover calls are.

The labels K1 to K16 name the controller's repairs (the table in docs/encodings/action-prompts.md).
"""

import contextlib
import copy
import json
import os
import re
import traceback

import action_answer as aa
import action_display as ad
import action_english as aen
import action_gk as ag
import action_json as aj
import action_route as ar
import action_prompt as apt
import action_repair as arep
import digests
import globals as G
import lc_action as la
import llmcall

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # llmpipe/
TAG = "actions"
MAX_CORRECTIONS = 2          # per stage
MAX_LOGICAL_CALLS = 6        # per translation, every repeated stage call counted
SEMANTIC_CORRECTIONS = 1     # one more logical call after a valid Stage 2 with invented class conditions
MAX_MESSAGES = 12            # the messages of one correction request, handoff and compiler together
# the readings in a fixed order, for the error message; the set is action_prompt.READINGS
READINGS = ("availability", "restriction", "effect", "occurrence",
            "plan_question", "reachable_question", "executable_question", "verify_question")
assert set(READINGS) == apt.READINGS
QUERY_KINDS = ("plan", "reachable", "verify", "question", "ask")

# the action route's own option keys; they never enter globals.options
ACTION_KEYS = ("actions_flag", "plan_depth", "action_backend", "formal_flag")
STAGE_FLAGS = ("fallback_norm_flag", "fallback_hyp_flag", "critic_flag", "graphtrans_flag", "litbridge_flag",
               "graphbridge_flag")
CANCEL_FLAGS = ("nofallback_norm_flag", "nofallback_hyp_flag", "nocritic_flag", "nographtrans_flag",
                "nolitbridge_flag", "nographbridge_flag")
# ordinary keys that keep their meaning on the action route: model calls, caches, the GK time, output
SHARED_KEYS = ("pipeline_name", "api_timeout", "llm_call_limit", "llm_call_timeout", "use_llm_cache_flag",
               "use_gemini_cache_flag", "use_cache_flag", "think_flag", "prover_seconds", "prover_seconds_cli",
               "prover_explain_flag", "show_logic_flag", "show_details_flag", "debug_print_flag", "summary_flag",
               "summary_json_flag", "json_flag", "clearcache_flag", "prover_print_flag", "show_prover_flag",
               "prover_nosolve_flag", "prover_rawresult_flag", "gkin_file")
# the command-line names of ordinary keys that the action route refuses, for its error message
FLAG_NAMES = {"prover_print": "-printlevel", "prover_strategy": "-strategy", "prover_axiomfiles": "-axioms",
              "nocontext_flag": "-nocontext", "noexceptions_flag": "-noexceptions", "noproptypes_flag": "-simpleprops",
              "nosemnormal_flag": "-nosemnormal", "directanswer_flag": "-directanswer", "event_base": "-event"}

# the shared keys llmcall and the caches read from globals.options: set for one action call, then restored
CALL_KEYS = ("llm_call_limit", "llm_call_timeout", "use_llm_cache_flag", "use_gemini_cache_flag", "use_cache_flag")

# the action prompts of prompts/actions (prompt revision I, named in the files' first lines), assembled by
# action_prompt.assemble
ACTION_BUNDLE = "actions"
DEFAULT_BUNDLE = ACTION_BUNDLE
# fake bundles for plumbing tests: {name: {"status", "text": {"stage1", "stage2"}}}
BUNDLES = {}


class OptionError(Exception):
  """An option that the action route cannot honour, or an action option without -actions."""


# -debug: print each model request and its raw response as `translate` sends it (set by `run` for one call)
_TRACE = False


# ---------------------------------------------------------------------------
# options


def resolve(options):
  """The action profile of one call, resolved once.  Raises OptionError on an incompatible explicit request."""
  opts = dict(options or {})
  if not opts.get("actions_flag"):
    raise OptionError("resolve() is for a call with -actions")
  asked = sorted(k for k, v in opts.items() if k in STAGE_FLAGS and v)
  if asked:
    raise OptionError("the action route runs no ordinary retry stage; remove %s (a -pipeline preset or a stage "
                      "switch)" % ", ".join(k[:-5] for k in asked))
  other = sorted(k for k in opts if k not in ACTION_KEYS + STAGE_FLAGS + CANCEL_FLAGS + SHARED_KEYS
                 and not k.startswith("_"))
  if other:
    raise OptionError("options of the ordinary route cannot be combined with -actions: %s"
                      % ", ".join(FLAG_NAMES.get(k) or ("-" + k[:-5] if k.endswith("_flag") else k) for k in other))
  depth = opts.get("plan_depth")
  if depth is not None and (isinstance(depth, bool) or not isinstance(depth, int) or depth < 0):
    raise OptionError("-plan-depth is a non-negative integer, got %r" % (depth,))
  backend = opts.get("action_backend") or ag.DEFAULT_BACKEND
  try:
    ag.backend_profile(backend)
  except ag.AdapterError as e:
    raise OptionError(str(e))
  seconds = opts["prover_seconds"] if opts.get("prover_seconds_cli") and opts.get("prover_seconds") else ag.DEFAULT_SECONDS
  return {"route": TAG, "plan_depth": depth, "limits": {"search_cap": depth, "explicit": True} if depth is not None else None,
          "backend": backend, "seconds": int(seconds), "formal": bool(opts.get("formal_flag")),
          "bundle": DEFAULT_BUNDLE, "disabled_stages": [k[:-5] for k in STAGE_FLAGS],
          "think": bool(opts.get("think_flag")), "nosolve": bool(opts.get("prover_nosolve_flag"))}


# ---------------------------------------------------------------------------
# prompt bundles


def load_bundle(name=None):
  """The assembled prompts of a bundle: {"name", "status", "stage1", "stage2", "sha256", "files", ...}, or None when
  the name is unknown or the prompt files are missing.  ACTION_BUNDLE, the default, is the action prompts
  (`action_prompt.assemble`); a bundle in BUNDLES is a fake for tests, its texts used as given."""
  name = name or DEFAULT_BUNDLE
  if name == ACTION_BUNDLE:
    try:
      return apt.assemble()
    except FileNotFoundError:
      return None
  spec = BUNDLES.get(name)
  if spec is None:
    return None
  s1, s2 = spec["text"]["stage1"], spec["text"]["stage2"]
  return {"name": name, "status": spec.get("status"), "stage1": s1, "stage2": s2,
          "sha256": {"stage1": digests.sha256_text(s1), "stage2": digests.sha256_text(s2)}, "files": {}}


# ---------------------------------------------------------------------------
# the translation controller


def stage1_units(parsed):
  """The Stage-1 units of an action Stage-1 output (the ordinary Stage-1 shape: sentence packages with `units`),
  or a list of structural errors."""
  errors, units = [], []
  if not isinstance(parsed, list) or not parsed:
    return None, ["the output is not a non-empty list of sentence packages"]
  for n, pkg in enumerate(parsed):
    if not isinstance(pkg, dict) or not isinstance(pkg.get("units"), list) or not pkg["units"]:
      errors.append("sentence package %d has no list of units" % (n + 1))
      continue
    for u in pkg["units"]:
      if not isinstance(u, dict) or not isinstance(u.get("unit_id"), str) or not isinstance(u.get("text"), str):
        errors.append("sentence package %d: a unit without a string unit_id and text: %s" % (n + 1, json.dumps(u)[:120]))
        continue
      reading = u.get("action_reading")
      if reading is not None and reading not in READINGS:
        errors.append("unit %s: action_reading %r is not one of %s" % (u["unit_id"], reading, ", ".join(READINGS)))
      units.append(u)
  ids = [u["unit_id"] for u in units]
  dup = sorted({i for i in ids if ids.count(i) > 1})
  if dup:
    errors.append("unit ids occur twice: %s" % ", ".join(dup))
  questions = [u["unit_id"] for u in units if str(u.get("action_reading", "")).endswith("_question")
               or u.get("type") == "query"]
  if len(questions) > 1:
    errors.append("several question units (%s): one query unit holds the whole question, with one shared scope"
                  % ", ".join(questions))
  if not errors:
    errors.extend(apt.validate_units(units))
  return (None if errors else units), errors


def stage2_packages(parsed):
  """(worlds, contexts, packages) of an action Stage-2 output: ["and", PKG, ...], a list of packages, or an object
  {"worlds", "contexts", "query_contexts", "types", "logic"}; or errors."""
  worlds, contexts = None, None
  if isinstance(parsed, dict):
    if set(parsed) - set(aj.ENVELOPE_FIELDS):
      return None, ["unknown action envelope fields; the envelope holds worlds, contexts, query_contexts, types and "
                    "logic, and no next, state time or state location packages"]
    worlds, contexts, parsed = parsed.get("worlds"), parsed.get("contexts"), parsed.get("logic")
  if isinstance(parsed, list) and parsed[:1] == ["and"]:
    parsed = parsed[1:]
  if isinstance(parsed, list) and len(parsed) == 3 and parsed[0] == "@id":
    parsed = [parsed]
  if not isinstance(parsed, list) or not all(isinstance(p, list) and len(p) == 3 and p[0] == "@id" and isinstance(p[1], str)
                                             for p in parsed):
    return None, ["the output is not a list of [\"@id\", ID, PACKAGE] packages"]
  return (worlds, contexts, parsed), []


def split_packages(packages):
  source, queries = [], []
  for p in packages:
    body = p[2]
    (queries if isinstance(body, list) and body and body[0] in QUERY_KINDS else source).append(p)
  return source, queries


def correction_request(stage, errors, previous, resolved=()):
  """The correction request's suffix: the previous response as data, its errors, and the errors of earlier attempts
  of the stage that this response no longer has (kept as constraints, so a fix is not undone by the next one)."""
  keep = ("\nEarlier attempts were rejected for these errors, which this output no longer has; keep those fixes:\n- %s\n"
          % "\n- ".join(resolved)) if resolved else ""
  return ("\n\nCORRECTION: your previous Stage-%d output was:\n%s\n\nIt has these errors:\n- %s\n%s"
          "Return the whole corrected JSON, and nothing else.  Do not change what the text says to make it fit."
          % (stage, (previous or "").strip(), "\n- ".join(errors), keep))


def _resolved(earlier, errors):
  """The errors of earlier attempts that the current response no longer has, in first-seen order."""
  out = []
  for lst in earlier:
    for e in lst:
      if e not in errors and e not in out:
        out.append(e)
  return out


# the argument names of the five constructors and of the source atoms, for naming a slot in a diagnostic
SLOT_NAMES = {"move": ("actor", "origin", "destination", "means"), "take": ("actor", "object"),
              "put_on": ("actor", "object", "support"), "put_in": ("actor", "object", "container"),
              "change": ("actor", "object", "value", "tool"), "connected": ("origin", "destination", "means"),
              "have": ("owner", "object"), "isa": ("class", "member"), "has property": ("value", "object")}


def _slot(package, path):
  """"the origin slot of move" for a diagnostic path into a package, or None."""
  node, name = package, None
  try:
    for step in (path or "").strip("/").split("/"):
      if not step:
        return None
      i = int(step)
      if isinstance(node, list) and node and isinstance(node[0], str):
        head = node[0]
        if head == "is rel2" and len(node) == 4 and i in (2, 3):
          name = "the %s slot of %s" % ("subject" if i == 2 else "place" if node[1] == "located_at" else "object", node[1])
        elif head in SLOT_NAMES and 1 <= i <= len(SLOT_NAMES[head]):
          name = "the %s slot of %s" % (SLOT_NAMES[head][i - 1], head)
        else:
          name = None
      node = node[i]
  except (IndexError, TypeError, ValueError):
    return None
  return name


def _unit_diagnostics(artifact, packages):
  """The invalid diagnostics of the source's units, deduplicated: one line per code and message, with its units and
  the slot it names."""
  byid = {p[1]: p for p in packages}
  grouped = {}
  for u in artifact["units"]:
    for d in u.get("diagnostics") or []:
      if d.get("level") != "invalid":
        continue
      slot = _slot(byid.get(d.get("unit") or u["id"]), d.get("path"))
      k = (d.get("code") or d.get("reason"), d.get("message"), slot)
      units = grouped.setdefault(k, [])
      if (d.get("unit") or u["id"]) not in units:
        units.append(d.get("unit") or u["id"])
  return ["unit%s %s: %s: %s%s" % ("s" if len(units) > 1 else "", ", ".join(units), code, message,
                                   " (in %s)" % slot if slot else "")
          for (code, message, slot), units in grouped.items()]


def _call_status(mark):
  """The failure reason of the last logical call since `mark`: a call limit or the run's ceiling, a timeout, or another
  provider failure."""
  for e in reversed(llmcall.call_log[mark:]):
    if e.get("reason") in (llmcall.LIMIT_MARKER, llmcall.CEILING_MARKER):
      return "call_limit"
    if e.get("reason") == llmcall.TIMEOUT_MARKER:
      return "model_timeout"
  return "model_error"


def translate(text, bundle, llm=None, version=None, max_tokens=None, think=False, semantic=True):
  """English -> a checked Stage 1 and Stage 2 with the bundle's prompts.  Returns a record:

    status        ok | call_limit | model_timeout | model_error | translation_invalid | unsupported_translation
    stage1_units  the accepted Stage-1 units; stage2 the accepted packages, worlds, contexts and types
    history       every request and response: stage, attempt, input SHA-256, raw output, errors, the parse steps
                  and the normalizations of that response
    source        the compiled source artifact, with the query packages kept apart
    normalizations  what the controller derived, replaced or removed in the accepted Stage 2 (envelope_derived,
                  derived_field, derived_probability, the typing cleanups, person_at_place, wrapper_dropped); the
                  parse repairs are in the history
    class_condition_findings  class conditions of the final translation's rule antecedents that their rule's
                  text does not state
    semantic_correction  the one request that asks to remove the high-confidence findings (`requested`), and its
                  result

  A stage gets at most MAX_CORRECTIONS corrections, and the translation at most MAX_LOGICAL_CALLS logical calls.
  A failed correction ends the translation; a known-invalid response is never used.  Unsupported meaning is not
  corrected: it is reported.  After a valid Stage 2 with high-confidence findings, `semantic` allows
  SEMANTIC_CORRECTIONS more logical call: its reply is used only when it equals the accepted translation with
  exactly those conjuncts removed; otherwise the accepted translation stands, with its findings.
  """
  t = _Translation(text, bundle, llm, version, max_tokens, think)
  got = t.stage1()
  if got is None:
    return t.rec
  units, parsed, merges = got
  s1_input = json.dumps(without_urls(parsed), ensure_ascii=False)
  got = t.stage2(units, merges, s1_input)
  if got is None:
    return t.rec
  accepted, raw = got
  rec = t.rec
  _adopt(rec, accepted)
  rec["status"] = "ok"
  _adjusted_route(rec, units, accepted)
  rec["class_condition_findings"] = apt.class_condition_findings(units, accepted["packages"])
  high = [f for f in rec["class_condition_findings"] if f["confidence"] == "high"]
  if semantic and high and bundle.get("annotation_contract"):
    _semantic_correction(rec, accepted, high, raw, s1_input, text, units, bundle, t.ask, t.reviewed_events, t.asked)
  return rec


class _Translation(object):
  """One translation in progress: the record it builds, the model it asks, and its budget of logical calls."""

  def __init__(self, text, bundle, llm, version, max_tokens, think):
    self.text, self.bundle = text, bundle
    self.llm, self.version, self.max_tokens, self.think = llm, version, max_tokens, think
    self.rec = {"status": None, "bundle": {k: bundle[k] for k in ("name", "status", "sha256")}, "stage1_units": None,
                "stage2": None, "history": [], "source": None, "queries": [], "errors": [], "unsupported": None}
    self.logical = 0
    # the units whose event reading the controller reviewed, and the units that got the K13 value message
    self.reviewed_events, self.asked = set(), set()

  def ask(self, stage, sysprompt, prompt, attempt, limit=None):
    """One model request, recorded in the history; None when the budget is used up or the call fails."""
    rec = self.rec
    limit = MAX_LOGICAL_CALLS if limit is None else limit
    if self.logical >= limit:
      rec["status"] = "call_limit"
      rec["errors"].append("the translation used its %d logical calls" % limit)
      return None
    mark = len(llmcall.call_log)
    if _TRACE:
      ad.show_request(stage, attempt, prompt, self.llm or llmcall.use_llm)
    with llmcall.tagged(TAG, stage=stage, correction=attempt):
      # a response cut at the output limit stays out of the LLM cache, so a cached response can be repaired
      raw = llmcall.call_llm(sysprompt, prompt, llm=self.llm, version=self.version, max_tokens=self.max_tokens,
                             think=self.think, cache_truncated=False)
    self.logical += sum(1 for e in llmcall.call_log[mark:] if e.get("logical"))
    rec["history"].append({"stage": stage, "attempt": attempt, "input_sha256": digests.sha256_text(prompt), "raw": raw,
                           "finish_reason": _finish(mark), "cached": _cached(mark)})
    if _TRACE:
      ad.show_response(raw, rec["history"][-1]["cached"])
    if raw is None:
      rec["status"] = _call_status(mark)
      rec["errors"].append("stage %d, attempt %d: no response (%s)" % (stage, attempt, rec["status"]))
    return raw

  def repeated(self, stage, attempt, prompt, sent):
    """A request equal to an earlier request of the stage returns the cached earlier response: stop instead."""
    if prompt not in sent:
      return False
    self.rec["history"].append({"stage": stage, "attempt": attempt, "input_sha256": digests.sha256_text(prompt), "raw": None,
                                "skipped": "repeated_request", "errors": []})
    self.rec["stop_reason"] = "repeated_request"
    self.rec["errors"].append("stage %d, correction %d: the request equals an earlier one (same response, same "
                              "errors), so it is not sent" % (stage, attempt))
    return True

  def stage1(self):
    """Stage 1 with its corrections, the id merges (K9) and the route selection.  Returns (units, the parsed
    packages, the merges), or None when the translation ends here (the record says why)."""
    rec, text, bundle = self.rec, self.text, self.bundle
    units, correction, sent, earlier = None, "", set(), []
    for attempt in range(MAX_CORRECTIONS + 1):
      merges = []
      prompt = text + correction
      if self.repeated(1, attempt, prompt, sent):
        break
      sent.add(prompt)
      raw = self.ask(1, bundle["stage1"], prompt, attempt)
      if raw is None:
        return None
      parsed, err, info = aj.parse_response(raw, rec["history"][-1]["finish_reason"], rec["history"][-1]["cached"])
      rec["history"][-1]["parse"] = info
      units, errors = stage1_units(parsed) if err is None else (None, [err])
      if units is not None and bundle.get("annotation_contract"):
        if not all(isinstance(p.get("raw"), str) for p in parsed) or \
           " ".join(" ".join(p["raw"] for p in parsed).split()) != " ".join(text.split()):
          errors.append("raw sentence packages must cover the original text exactly")
          units = None
        else:
          # K9: a clear anaphor merges two ids; the same index and head noun without one is a Stage-1 correction
          merges, questions = arep.id_findings(units)
          if questions:
            errors, units = questions, None
          elif merges:
            units, notes = arep.merge_units(units, merges)
            rec["history"][-1]["normalizations"] = notes
      rec["history"][-1]["errors"] = errors
      if units is not None:
        break
      correction = correction_request(1, errors, raw, _resolved(earlier, errors))
      earlier.append(list(errors))
    if units is None:
      rec.update(status="translation_invalid", errors=rec["errors"] + ["Stage 1: %s" % e for e in errors])
      return None
    rec["stage1_units"] = units
    rec["stage1_packages"] = parsed
    if merges:
      # the Stage-2 input stays the model's Stage 1; each Stage-2 response gets the same merge
      rec["id_merges"] = merges
    rec.update(apt.select_route(units))
    if rec["route_selected"] == "diagnostic":
      rec["status"] = "unsupported_translation"
      rec["unsupported"] = {"reasons": sorted({x["reason"] for x in rec["route_reasons"]}),
                            "units": [x["unit"] for x in rec["route_reasons"]],
                            "diagnostics": rec["route_reasons"]}
      return None
    return units, parsed, merges

  def stage2(self, units, merges, s1_input):
    """Stage 2, checked structurally and by the compiler, with its corrections, the one focused request (K14) and the
    one clarification (K15).  Returns (the accepted attempt, its raw response), or None when the translation ends
    here (the record says why)."""
    rec, text, bundle = self.rec, self.text, self.bundle
    correction, sent, earlier = "", set(), []
    accepted, errors, raw = None, [], None
    focused = False          # K14: the one focused request has been sent
    splice = None            # K14: the previous response that the focused reply's packages go into
    held = None              # K15: the unsupported attempt that the one clarification asked about
    contract = bool(bundle.get("annotation_contract"))
    for attempt in range(MAX_CORRECTIONS + 1):
      prompt = s1_input + correction
      if prompt in sent and contract and not focused and attempt > 0:
        # K14: the correction returned the same response; one focused request quotes only the failing packages
        failing = _failing_packages(raw, rec["history"][-1], errors)
        if failing:
          prompt = s1_input + _focused_request(failing, errors)
          focused, splice = True, (raw, rec["history"][-1])
      if self.repeated(2, attempt, prompt, sent):
        break
      sent.add(prompt)
      raw = self.ask(2, bundle["stage2"], prompt, attempt)
      if raw is None:
        if held is not None:
          # K15: no reply to the clarification: the unsupported outcome stands; the failed call stays in the record
          _adopt(rec, held)
          rec["status"] = "unsupported_translation"
          rec["unsupported"] = held["result"]["unsupported"]
        return None
      entry = rec["history"][-1]
      if held is not None:
        entry["kind"] = "clarification"
      if splice is not None:
        entry["kind"] = "focused_correction"
        raw, why = _spliced(splice, raw, entry)
        splice = None
        if raw is None:
          entry.update(errors=[why], parse=None)
          errors = [why]
          correction = correction_request(2, errors, entry["raw"], _resolved(earlier, errors))
          earlier.append(list(errors))
          continue
        att = stage2_attempt(raw, "stop", text, units, bundle, self.reviewed_events, True, merges, self.asked)
      else:
        att = stage2_attempt(raw, entry["finish_reason"], text, units, bundle, self.reviewed_events,
                             entry["cached"], merges, self.asked)
      _note_attempt(entry, att)
      unstated, refusals = [], []
      if held is not None and not att["errors"] and att["stop"] != "unsupported":
        named, law_units = _clarified_units(held)
        refusals = arep.clarification_refusals(held, att, named, law_units)
        unstated = arep.unstated_values(units, held["packages"], att["packages"] or [])
      if held is not None and (att["stop"] == "unsupported" or att["errors"] or unstated or refusals):
        # K15: the clarification did not give a valid, supported translation that changes only result labels the
        # text states or the arrangement of a law: the unsupported outcome stands (a real collision keeps it)
        att = held
        entry["clarification"] = "the unsupported outcome stands"
        if unstated:
          entry["unstated_values"] = [{"unit": u, "value": v} for u, v in unstated]
        if refusals:
          entry["clarification_refusals"] = refusals
      if att["stop"] == "unsupported":
        reasons = set((att["result"]["unsupported"] or {}).get("reasons") or [])
        if contract and held is None and reasons and reasons <= CLARIFIED and attempt < MAX_CORRECTIONS:
          # K15: one clarification request for a form-level unsupported outcome
          held = att
          entry["errors"] = []
          correction = _clarification(raw, att)
          continue
        _adopt(rec, att)
        rec["status"] = "unsupported_translation"
        rec["unsupported"] = att["result"]["unsupported"]
        entry["errors"] = []
        return None
      if held is not None:
        entry["clarification"] = "accepted"
      held = None
      errors = att["errors"]
      for u in units:
        if any(e.startswith("unit %s: reading_form_mismatch:" % u["unit_id"]) for e in errors):
          self.reviewed_events.add(u["unit_id"])
      self.asked.update(att.get("value_asked") or [])
      if not errors:
        accepted = att
        break
      correction = correction_request(2, errors, raw, _resolved(earlier, errors))
      earlier.append(list(errors))
    if held is not None:
      # the budget ended before the clarification was sent: the unsupported outcome stands
      _adopt(rec, held)
      rec["status"] = "unsupported_translation"
      rec["unsupported"] = held["result"]["unsupported"]
      return None
    if accepted is None:
      rec.update(status="translation_invalid", errors=rec["errors"] + ["Stage 2: %s" % e for e in errors],
                 source=None, queries=[])
      return None
    return accepted, raw


# K15: the unsupported reasons of a translation's form, which one clarification request may resolve
CLARIFIED = {"method_collision", "unsupported_law_form"}
_UNITS_NAMED = re.compile(r"\bunits? ((?:S\d+)(?:, S\d+)*)")


def _clarified_units(att):
  """(the units the unsupported diagnosis names, the units with unsupported_law_form) of an unsupported attempt."""
  named = set((att["result"].get("unsupported") or {}).get("units") or [])
  law = {u["id"] for u in (att["result"].get("source") or {}).get("units") or []
         for d in u.get("diagnostics") or [] if d.get("reason") == "unsupported_law_form"}
  return named | law, law


def _failing_packages(raw, entry, errors):
  """K14: the packages of the previous response that the errors name, or [] when there are none to quote (a response
  that does not parse, or errors that name no unit)."""
  parsed, err, _ = aj.parse_response(raw, entry.get("finish_reason"), entry.get("cached"))
  if err is not None:
    return []
  logic = parsed.get("logic") if isinstance(parsed, dict) else parsed
  if isinstance(logic, list) and logic[:1] == ["and"]:
    logic = logic[1:]
  named = {x.strip() for e in errors for m in _UNITS_NAMED.finditer(e) for x in m.group(1).split(",")}
  return [p for p in logic if isinstance(p, list) and len(p) >= 3 and p[0] == "@id" and p[1] in named] \
      if isinstance(logic, list) else []


def _focused_request(failing, errors):
  """K14: the one focused request after a correction that returned the same response."""
  return ("\n\nCORRECTION: your corrected Stage-2 output was the same as the output before it, with the same errors. "
          "Only these packages have errors:\n%s\n\nTheir errors:\n- %s\n"
          "Return only these packages, corrected, as a JSON list of [\"@id\", ID, PACKAGE]; every other package "
          "stays as it is.  Do not change what the text says to make it fit." % (
            "\n".join(json.dumps(p, ensure_ascii=False) for p in failing), "\n- ".join(errors)))


def _spliced(splice, reply, entry):
  """K14: (the previous response with the focused reply's packages in place of its own, None) or (None, the
  reason).  The reply is parsed as a response; the result is one intact JSON text."""
  previous, prev_entry = splice
  parsed, err, info = aj.parse_response(reply, entry.get("finish_reason"), entry.get("cached"))
  entry["parse"] = info
  if err is not None:
    return None, err
  if isinstance(parsed, dict):
    parsed = parsed.get("logic")
  if isinstance(parsed, list) and parsed[:1] == ["and"]:
    parsed = parsed[1:]
  if isinstance(parsed, list) and len(parsed) == 3 and parsed[0] == "@id":
    parsed = [parsed]
  if not (isinstance(parsed, list) and parsed and all(isinstance(p, list) and len(p) == 3 and p[0] == "@id"
                                                       for p in parsed)):
    return None, "the reply to the focused request is not a JSON list of [\"@id\", ID, PACKAGE] packages"
  base, _, _ = aj.parse_response(previous, prev_entry.get("finish_reason"), prev_entry.get("cached"))
  logic = base.get("logic") if isinstance(base, dict) else base
  wrapped = isinstance(logic, list) and logic[:1] == ["and"]
  packages = logic[1:] if wrapped else logic
  by = {p[1]: p for p in parsed}
  unknown = sorted(set(by) - {p[1] for p in packages if isinstance(p, list) and len(p) >= 2})
  if unknown:
    return None, "the reply to the focused request has packages for units the previous output does not have: %s" \
      % ", ".join(unknown)
  new = [by.get(p[1], p) if isinstance(p, list) and len(p) >= 2 else p for p in packages]
  new = ["and"] + new if wrapped else new
  if isinstance(base, dict):
    base = dict(base, logic=new)
  else:
    base = new
  text = json.dumps(base, ensure_ascii=False)
  entry["spliced"] = text
  return text, None


def _clarification(raw, att):
  """K15: the one clarification request for method_collision and unsupported_law_form.  Its reply is adopted only
  when it is a valid, supported translation that changes nothing but result labels, which the text states as results
  of their operation on their object (`action_repair.unstated_values`), and the arrangement of a law with
  unsupported_law_form (`action_repair.clarification_refusals`)."""
  lines = []
  for u in (att["result"].get("source") or {}).get("units") or []:
    for d in u.get("diagnostics") or []:
      if d.get("level") == "unsupported" and d.get("reason") in CLARIFIED:
        lines.append("unit %s: %s: %s" % (u["id"], d["reason"], d.get("message")))
  if not lines:
    lines = ["%s (units %s)" % (", ".join(att["result"]["unsupported"].get("reasons") or []),
                                ", ".join(att["result"]["unsupported"].get("units") or []))]
  return ("\n\nCLARIFICATION: your previous Stage-2 output was:\n%s\n\nThe route cannot read it:\n- %s\n"
          "Check two things.  First: did the translation lose a distinction that the text states, for example two "
          "actions with different verbs, tools or results written as one action term?  Second: did it use an "
          "arrangement that the route cannot read, where a supported arrangement says the same, for example a "
          "condition beside the can head where it belongs in the antecedent?  If one of them holds, return the whole "
          "corrected JSON.  If neither holds, return the same JSON again, unchanged.  Do not invent an effect, do "
          "not delete a condition, and do not weaken a quantifier.  Return nothing else."
          % ((raw or "").strip(), "\n- ".join(lines)))


def _adjusted_route(rec, units, att):
  """K11 (and K1, K2): an accepted translation whose readings the compiler adjusted gets its route selection computed
  again from the adjusted readings; the selection from the model's Stage 1 is kept beside it."""
  adjusted = {n["unit"]: n["after"] for n in att["normalizations"] if n.get("kind") == "reading_adjusted"}
  if not adjusted:
    return
  new = []
  for u in units:
    v = dict(u)
    if u["unit_id"] in adjusted:
      if adjusted[u["unit_id"]] is None:
        v.pop("action_reading", None)
      else:
        v["action_reading"] = adjusted[u["unit_id"]]
    new.append(v)
  rec["route_selection_stage1"] = {"route_selected": rec.get("route_selected"), "route_reasons": rec.get("route_reasons")}
  rec.update(apt.select_route(new))


def without_urls(packages):
  """The Stage-1 sentence packages without the entities' `url` fields: the action route does not read them, and a
  model once used one as an entity id.  The accepted Stage 1 keeps them."""
  out = copy.deepcopy(packages)
  for p in out if isinstance(out, list) else []:
    for u in p.get("units") or [] if isinstance(p, dict) else []:
      for e in u.get("entities") or [] if isinstance(u, dict) else []:
        if isinstance(e, dict):
          e.pop("url", None)
  return out


def _finish(mark):
  """The provider's stop reason for the response of the calls since `mark`; None for a cached response."""
  for e in reversed(llmcall.call_log[mark:]):
    if e.get("source") == "api":
      return e.get("finish_reason")
  return None


def _cached(mark):
  """Whether the LLM cache served the logical call since `mark`."""
  return any(e.get("source") == "cache" and e.get("logical") for e in llmcall.call_log[mark:])


def _note_attempt(entry, att):
  entry["errors"] = att["errors"]
  entry["parse"] = att["parse"]
  if att["normalizations"]:
    entry["normalizations"] = att["normalizations"]
  if att.get("merged"):
    entry["merged_compiler_messages"] = att["merged"]


def stage2_attempt(raw, finish, text, units, bundle, reviewed_events, cached=False, merges=(), asked=()):
  """Check one Stage-2 response.  Returns {"errors", "parse", "normalizations", "envelope", "worlds", "contexts",
  "selections", "types", "packages", "result", "stop"}: `result` is the record `compile_translation` filled (source,
  queries, unsupported, types) and `stop` is "unsupported" when the compiler reports unsupported meaning.

  Three steps.  `_normalized` parses the response and, with the annotation contract (the reviewed bundle), applies
  the normalizations, each recorded: the envelope fields worlds, contexts and query_contexts are the values derived
  from the validated Stage 1 (`apt.derive_envelope`, `apt.derived_fields`): a field the response leaves out is
  derived, and a supplied value that differs is replaced, with the model's value kept in the record; the typing
  cleanups (`apt.typing_cleanups`); a person at a place is located_at (`apt.at_place_cleanup`); a source package
  ["and", ["holds", W, F]] with that one conjunct is ["holds", W, F]; the @p of a source package is the one Stage 1
  and the unit's text decide (`apt.derived_probabilities`); and the controller's repairs, each with its repair id,
  unit, text before and after and supporting units: K10 in the parser and in an intact response (a misplaced @p with
  the derived probability or the convention confidence, `misplaced_values`), K9 (the merged ids of `merges`, found
  at Stage 1), and K8, K7, K6 and K5 (`action_repair.repair_packages`).  A fake test bundle (no annotation contract)
  keeps the bare list without an envelope.  `_checked` finds the errors of coverage, of the handoff between the
  stages (K3 and K4 are forms that the handoff check accepts, with a note) and of a value against its permission
  (K13; `asked` holds the units that got the K13 message before, which are not asked again).  `_compiled` runs the
  compiler beside those errors, so one correction names every independent error; the compiler adjusts readings (K1,
  K2, K11).  The repairs are listed in docs/encodings/action-prompts.md.
  """
  att = {"errors": [], "parse": None, "normalizations": [], "envelope": None, "worlds": None, "contexts": None,
         "selections": {}, "types": None, "packages": None, "result": None, "stop": None}
  contract = bundle.get("annotation_contract")
  got = _normalized(att, raw, finish, cached, units, merges, contract)
  if got is None:
    return att
  parsed, worlds, contexts, packages = got
  errors, source, queries, selections, types, covered = _checked(att, parsed, packages, units, contract, asked)
  att.update(envelope=parsed, worlds=worlds, contexts=contexts, selections=selections, types=types or None,
             packages=packages)
  if covered and isinstance(selections, dict) and len(queries) <= 1:
    errors = _compiled(att, errors, text, units, worlds, contexts, source, queries, selections, types,
                       reviewed_events)
    if att["stop"] == "unsupported":
      return att
  att["errors"] = errors
  return att


def _normalized(att, raw, finish, cached, units, merges, contract):
  """(parsed, worlds, contexts, packages) of a response after the normalizations, or None with att["errors"] set."""
  probabilities = misplaced_values(units) if contract else None
  parsed, err, info = aj.parse_response(raw, finish, cached, probabilities)
  att["parse"] = info
  if err is not None:
    att["errors"] = [err]
    return None
  if contract:
    att["normalizations"].extend((info.get("package_repair") or {}).get("misplaced_probability") or [])
    att["normalizations"].extend(_misplaced_probabilities(parsed, probabilities))
    parsed, merged = arep.merge_response(parsed, list(merges))
    att["normalizations"].extend(merged)
    env, derived = apt.derive_envelope(units, parsed)
    if env is not None:
      if derived:
        att["normalizations"].append({"kind": "envelope_derived", "fields": derived,
                                      "form": "object" if isinstance(parsed, dict) else "logic list"})
      parsed = env
      att["normalizations"].extend(apt.derived_fields(units, parsed))
      att["normalizations"].extend(apt.typing_cleanups(units, parsed))
      att["normalizations"].extend(apt.at_place_cleanup(units, parsed))
  got, errors = stage2_packages(parsed)
  if got is None:
    att["errors"] = errors
    return None
  worlds, contexts, packages = got
  if contract:
    for p in packages:
      if (isinstance(p[2], list) and len(p[2]) == 2 and p[2][0] == "and" and isinstance(p[2][1], list)
          and p[2][1][:1] == ["holds"]):
        p[2] = p[2][1]
        att["normalizations"].append({"kind": "wrapper_dropped", "unit": p[1]})
    att["normalizations"].extend(apt.derived_probabilities(units, packages))
    att["normalizations"].extend(arep.repair_packages(units, packages))
  return parsed, worlds, contexts, packages


def _checked(att, parsed, packages, units, contract, asked):
  """The errors of coverage, handoff and values of a normalized response: (errors, source packages, query packages,
  query selections, types, whether every unit has exactly its package)."""
  errors = []
  ids = {p[1] for p in packages}
  missing = [u["unit_id"] for u in units if u["unit_id"] not in ids]
  unknown = sorted(ids - {u["unit_id"] for u in units})
  if missing:
    errors.append("no Stage-2 package for the Stage-1 units %s" % ", ".join(missing))
  if unknown:
    errors.append("Stage-2 packages for units Stage 1 does not have: %s" % ", ".join(unknown))
  source, queries = split_packages(packages)
  selections = parsed.get("query_contexts", {}) if isinstance(parsed, dict) else {}
  types = parsed.get("types") if isinstance(parsed, dict) else None
  covered = not errors
  if not isinstance(selections, dict):
    errors.append("query_contexts must be an object")
  elif covered:
    # the full cross-stage contract belongs to the real bundle; a fake test bundle uses the bare list of packages
    if contract:
      notes = []
      errors.extend(apt.handoff_errors(units, parsed if isinstance(parsed, dict) else {}, packages, notes))
      att["normalizations"].extend(notes)
      # K13: a later mention with another value than its one permission; asked once per unit
      values = arep.value_mismatches(units, packages, asked)
      errors.extend(m for _, m in values)
      att["value_asked"] = [uid for uid, _ in values]
    query_ids = {q[1] for q in queries}
    for uid, sel in selections.items():
      if uid not in query_ids or not isinstance(sel, dict) or set(sel) - apt.SELECTORS:
        errors.append("invalid query_contexts entry %s" % uid)
  if len(queries) > 1:
    errors.append("several query packages (%s); one query package holds the whole question"
                  % ", ".join(q[1] for q in queries))
  return errors, source, queries, selections, types, covered


def _compiled(att, errors, text, units, worlds, contexts, source, queries, selections, types, reviewed_events):
  """Compile a covered response, also beside the handoff errors, so one correction names every independent error.
  Returns the errors; sets att["result"] and att["stop"] when the response is otherwise valid."""
  usable = types if isinstance(types, dict) and not apt.types_errors(units, types) else None
  # an invalid selection has its message already; the compiler reads only the valid ones
  scratch = {"query_contexts": {uid: sel for uid, sel in selections.items()
                                if uid in {q[1] for q in queries} and isinstance(sel, dict)
                                and not set(sel) - apt.SELECTORS}}
  stop = compile_translation(scratch, text, units, worlds, contexts, source, queries, reviewed_events, usable)
  att["normalizations"].extend(scratch.get("reading_adjustments") or [])
  if not errors:
    att["result"] = scratch
    if stop == "unsupported":
      att["stop"] = "unsupported"
      return errors
    return stop or []
  if isinstance(stop, list):
    extra = [e for e in stop if e not in errors and not e.startswith("the source packages cannot be compiled")]
    att["merged"] = len(extra)
    errors = (errors + extra)[:MAX_MESSAGES]
  return errors


def misplaced_values(units):
  """K10: {unit id: the values of a misplaced @p that the controller drops}.  The probability it derives for the unit
  (`action_prompt.expected_probability`); without one, the Stage-1 convention confidence that a well-placed @p would
  lose too: 0.99 of an indefinite article, 0.98 of normally."""
  out = {}
  for u in units:
    if u.get("type") == "query":
      continue
    p = apt.expected_probability(u)
    c = u.get("confidence")
    if p is not None:
      out[u["unit_id"]] = (p,)
    elif c == 0.99 or (c == 0.98 and u.get("type") == "normal_rule"):
      out[u["unit_id"]] = (c,)
  return out


def _misplaced_probabilities(parsed, probabilities):
  """K10 in an intact response: a package ["@id", U, PACKAGE, ["@p", U, v]] whose @p names its own unit and has a value
  that `probabilities` accepts for U loses that element, in place.  Another number stays, and the structural check asks
  for a correction.  Returns the records."""
  logic = parsed.get("logic") if isinstance(parsed, dict) else parsed
  records = []
  for p in logic if isinstance(logic, list) else []:
    if (isinstance(p, list) and len(p) == 4 and p[0] == "@id" and isinstance(p[3], list) and len(p[3]) == 3
        and p[3][0] == "@p" and p[3][1] == p[1] and p[3][2] in (probabilities or {}).get(p[1], ())):
      before = json.dumps(p, ensure_ascii=False)
      del p[3]
      records.append({"kind": "misplaced_probability", "repair": "K10", "unit": p[1], "before": before,
                      "after": json.dumps(p, ensure_ascii=False), "support": [p[1]]})
  return records


def _adopt(rec, att):
  """The translation record takes one checked Stage-2 attempt."""
  rec["stage2"] = {"worlds": att["worlds"], "contexts": att["contexts"], "query_contexts": att["selections"],
                   "packages": att["packages"]}
  if att["types"]:
    rec["stage2"]["types"] = att["types"]
  rec["query_contexts"] = att["selections"]
  rec["normalizations"] = att["normalizations"]
  res = att["result"] or {}
  rec["source"] = res.get("source")
  rec["queries"] = res.get("queries") or []
  rec["types"] = res.get("types")


def _semantic_request(previous, findings, units):
  byid = {u["unit_id"]: u for u in units}
  lines = []
  for f in findings:
    line = "unit %s, path %s: %s (%s; the unit's text: %s)" % (
      f["unit"], "/" + "/".join(str(i) for i in f["path"]), json.dumps(f["atom"], ensure_ascii=False), f["reason"],
      json.dumps(byid[f["unit"]]["text"], ensure_ascii=False))
    if f.get("repair") == "move_to_types":
      line += ("; it is the class of a referent this sentence introduces, so it goes to the envelope field types: "
               "{\"%s\": [%s]}" % (f["unit"], json.dumps(f["atom"], ensure_ascii=False)))
    lines.append(line)
  return ("\n\nCORRECTION: your previous Stage-2 output was:\n%s\n\nIt is valid, but these rule conditions are class "
          "facts that no sentence of their rule states:\n- %s\n"
          "Conditions exactly as stated: return the same JSON with only these conjuncts removed from the conditions, "
          "and a class that the text gives a referent of the sentence moved to types as stated above. An antecedent "
          "left with one conjunct is that conjunct; a rule whose antecedent is left empty is its head alone. Change "
          "nothing else, and return nothing else." % ((previous or "").strip(), "\n- ".join(lines)))


def _semantic_correction(rec, accepted, high, raw, s1_input, text, units, bundle, ask, reviewed_events, asked=()):
  """One Stage-2 request that asks to remove the high-confidence invented class conditions.

  The reply must be a valid translation equal to the accepted one with exactly the flagged conjuncts removed and the
  emptied or singleton conjunctions collapsed (`apt.drop_conjuncts`).  A finding with repair `move_to_types` (the class
  of a referent that its own law sentence introduces) must also appear in the envelope field types of that unit; every
  other envelope field and package stays as it was.  Otherwise, or when the request gets no response, the accepted
  translation stands with its findings.  Never repeated."""
  sc = {"requested": high, "status": None, "reason": None}
  rec["semantic_correction"] = sc
  attempt = sum(1 for h in rec["history"] if h["stage"] == 2)
  status = rec["status"]
  reply = ask(2, bundle["stage2"], s1_input + _semantic_request(raw, high, units), attempt,
              limit=MAX_LOGICAL_CALLS + SEMANTIC_CORRECTIONS)
  if reply is None:
    # the accepted translation is valid: a missing reply to the optional request is recorded, and the call log and
    # the history keep the failed call
    sc.update(status="no_response", reason=rec["errors"][-1] if rec["errors"] else rec["status"])
    rec["status"] = status
    rec["errors"] = rec["errors"][:-1]
    return
  entry = rec["history"][-1]
  entry["kind"] = "semantic_correction"
  att = stage2_attempt(reply, entry["finish_reason"], text, units, bundle, set(reviewed_events), entry["cached"],
                       rec.get("id_merges") or (), asked)
  _note_attempt(entry, att)
  paths = {}
  for f in high:
    paths.setdefault(f["unit"], []).append(f["path"])
  expected = [apt.drop_conjuncts(p, paths[p[1]]) if p[1] in paths else p for p in accepted["packages"]]
  moved = {uid: list(atoms) for uid, atoms in (accepted["types"] or {}).items()}
  for f in high:
    if f.get("repair") == "move_to_types" and f["atom"] not in moved.get(f["unit"], []):
      moved.setdefault(f["unit"], []).append(f["atom"])
  if att["stop"] == "unsupported":
    reason = "the reply compiles to unsupported meaning"
  elif att["errors"]:
    reason = "the reply is not a valid translation: %s" % "; ".join(att["errors"][:3])
  elif att["packages"] != expected:
    changed = [p[1] for p, q in zip(att["packages"], expected) if p != q] if len(att["packages"]) == len(expected) \
      else ["the package list"]
    reason = "the reply differs from the accepted translation by more than the removal of the flagged conjuncts (%s)" \
      % ", ".join(changed)
  elif (att["worlds"], att["contexts"], att["selections"], arep.types_key(att["types"])) != \
      (accepted["worlds"], accepted["contexts"], accepted["selections"], arep.types_key(moved)):
    reason = "the reply changes the envelope beyond the classes moved to types"
  else:
    reason = None
  if reason:
    sc.update(status="refused", reason=reason)
    return
  _adopt(rec, att)
  sc["status"] = "accepted"
  # the findings describe the final translation; the requested ones stay in the semantic_correction record
  rec["class_condition_findings"] = apt.class_condition_findings(units, att["packages"])


def compile_translation(rec, text, units, worlds, contexts, source, queries, reviewed_events=(), types=None):
  """Compile the source and check the query packages.  Returns [] when both are usable, a list of structural
  errors to correct, or "unsupported" (rec gets the result).  `types` is the envelope field types; the type records
  of the source are its stated classes and the documented person convention (`apt.person_types`)."""
  s1 = [{"id": u["unit_id"], "text": u["text"], "stage1": {k: v for k, v in u.items() if k not in ("unit_id", "text")}}
        for u in units if u["unit_id"] in {p[1] for p in source}]
  derived, notes = apt.person_types(units, source, types)
  given = apt.stated_types(types) + derived
  rec["types"] = {"stated": apt.stated_types(types), "stage1_person": derived, "notes": notes}
  try:
    a = ar.compile_source(s1, source, la.PROFILE, text, worlds=worlds, contexts=contexts, types=given or None,
                          type_notes=notes or None)
  except ar.ArtifactError as e:
    return ["the source packages cannot be compiled: %s" % e]
  rec["reading_adjustments"] = [{"kind": "reading_adjusted", "repair": d["repair"], "unit": u["id"],
                                 "before": d["before"], "after": d["after"], "support": [u["id"]]}
                                for u in a["units"] for d in u["diagnostics"]
                                if d.get("reason") == "reading_adjusted" and d.get("repair")]
  sup = a["support"]
  # A recognized action reading accidentally reified as a capability event is
  # correctable. Ask once per unit: if the corrected, well-formed response keeps
  # an event, preserve the compiler's unsupported diagnosis. A new operator must
  # not be rewritten until it happens to fit a constructor.
  for unit in a["units"]:
    reading = (unit.get("stage1") or {}).get("action_reading")
    if reading in apt.LAW_READINGS and unit.get("form") == "ordinary_event" and unit["id"] not in reviewed_events:
      return ["unit %s: reading_form_mismatch: check the stated %s for a faithful action form. "
              "If no constructor preserves it, retain the event for an unsupported diagnosis; invent no result or permission" %
              (unit["id"], reading)]
  if sup["status"] == "invalid":
    # The ordinary event/capability vocabulary is a frequent model fallback
    # for an action reading. Make that repairable at the prompt boundary even
    # though the formal action compiler correctly rejects those predicates.
    def contains(node, names):
      # a list may open with a list (the action list of a verify package): only a string names a predicate
      return isinstance(node, list) and ((node and isinstance(node[0], str) and node[0] in names)
                                         or any(contains(x, names) for x in node))
    for p in source:
      u = next((x for x in units if x["unit_id"] == p[1]), None)
      reading = (u or {}).get("action_reading")
      if reading in ("availability", "restriction", "effect") and contains(p[2], {"capability", "has actor", "has type", "event"}):
        return ["unit %s: reading_form_mismatch: translate the stated %s with its action form, not an ordinary event" %
                (p[1], reading)]
    return (["unit %s: %s: %s" % (d.get("unit"), d.get("code"), d.get("message")) for d in a["diagnostics"]
             if d.get("level") == "invalid"] + _unit_diagnostics(a, source)
            or ["the source is invalid: %s" % sup["errors"]])
  rec["source"] = a
  if sup["status"] == "unsupported":
    rec["status"] = "unsupported_translation"
    rec["unsupported"] = {"reasons": sup["reasons"], "units": sup["units"]}
    return "unsupported"
  # the query packages: a structural error is corrected; unsupported meaning ends the translation.  The limits,
  # the backend and the selection are the solve step's (an allowance is not a translation matter).
  errors = []
  for q in queries:
    try:
      qa = ar.compile_query(q, a, **rec.get("query_contexts", {}).get(q[1], {}))
    except ar.ArtifactError as e:
      errors.append("unit %s: invalid query selection: %s" % (q[1], e))
      continue
    o = (qa["outcome"] or {}).get("outcome")
    if o == "translation_invalid":
      errors += ["unit %s: %s: %s" % (q[1], d.get("code"), d.get("message")) for d in qa["diagnostics"]
                 if d.get("level") == "invalid"] or ["unit %s: %s" % (q[1], qa["outcome"].get("errors"))]
    elif o == "unsupported_translation":
      rec["status"] = "unsupported_translation"
      rec["unsupported"] = {"reasons": qa["outcome"].get("reasons"), "units": qa["outcome"].get("units")}
      return "unsupported"
  if errors:
    rec["source"] = None
    return errors
  rec["queries"] = queries
  return []


# ---------------------------------------------------------------------------
# the route


@contextlib.contextmanager
def call_settings(options):
  """The call's model-call settings in globals.options for the length of the call, then the previous values: the
  action route leaves no option behind for a later ordinary call."""
  saved = {k: G.options[k] for k in CALL_KEYS if k in G.options}
  try:
    for k in CALL_KEYS:
      if k in (options or {}) and k in G.options:
        G.options[k] = options[k]
    yield
  finally:
    G.options.update(saved)


def _calls(mark):
  log = llmcall.call_log[mark:]
  mine = [e for e in log if e.get("tag") == TAG or e.get("call_tag") == TAG]
  mine = mine or log
  return {"logical": sum(1 for e in mine if e.get("logical")),
          "cached": sum(1 for e in mine if e.get("source") == "cache"),
          "live": sum(1 for e in mine if e.get("source") == "api" and e.get("logical")),
          "provider_attempts": sum(1 for e in mine if e.get("source") == "api"),
          "refused": sum(1 for e in mine if e.get("source") == "refused"),
          "timeouts": sum(1 for e in mine if e.get("reason") == llmcall.TIMEOUT_MARKER)}


def run(text, options, collect=None, llm=None, version=None, max_tokens=None):
  """The action route for one call.  Returns the answer string; the run record goes to collect["action_route"].

  The output options are honoured as in the ordinary pipeline (`action_display`): the explanation follows the answer
  under -explain and is `nl_proof` in the collector, -nosolve stops before GK and answers "", -rawresult answers with
  GK's raw output, and -gkin writes each launch's input."""
  global _TRACE
  opts = options or {}
  lv = ad.levels(opts)
  mark = len(llmcall.call_log)
  rec = {"route": TAG, "profile": None, "input": "formal" if opts.get("formal_flag") else "text",
         "translation": None, "source": None, "query": None, "result": None, "error": None, "calls": None}
  view = new_view(opts)
  ledger = {"gk_calls": []}
  answer = None
  record = lv["details"] or lv["prover"] or opts.get("prover_rawresult_flag") or opts.get("gkin_file")
  try:
    prof = resolve(options)
    rec["profile"] = prof
    _TRACE = lv["debug"]
    with call_settings(options), (ag.recording() if record else contextlib.nullcontext([])) as launches:
      if prof["formal"]:
        answer = _run_formal(text, prof, rec, ledger, view)
      else:
        answer = run_text(text, prof, rec, ledger, llm, version, max_tokens, view)
    view["launches"] = launches
  except OptionError as e:
    rec["error"] = {"kind": "options", "message": str(e)}
    answer = "Error: incompatible options: %s" % e
  except Exception as e:                                          # noqa: BLE001  an exception is never an answer
    rec["error"] = {"kind": type(e).__name__, "message": str(e), "trace": traceback.format_exc()[-2000:]}
    answer = "Error: the action route failed: %s: %s" % (type(e).__name__, e)
  finally:
    _TRACE = False
  rec["calls"] = dict(_calls(mark), gk=len(ledger["gk_calls"]))
  if view["nosolve"] and rec["error"] is None and not str(answer).startswith("Error"):
    answer = ""
  explained = ad.explanation(rec, view, opts) if (lv["explain"] or collect is not None) and answer else ""
  if collect is not None:
    collect["action_route"] = rec
    collect["answer"] = answer
    if explained:
      collect["nl_proof"] = explained
    ok = rec["error"] is None and aen.answered(rec["result"])
    collect["answered_by"] = TAG if ok else None
    collect["pipeline_name"] = TAG
    collect["stages_enabled"] = {k[:-5]: False for k in STAGE_FLAGS}
    collect["run_outcome"] = ((rec["result"] or {}).get("outcome") or "error") if ok else "error"
    collect.setdefault("gk_calls", []).extend(ledger["gk_calls"])
  ad.show(rec, view, opts, text if rec["input"] == "text" else None, llm or llmcall.use_llm)
  if opts.get("gkin_file") and view["launches"]:
    paths = ad.write_gkin(opts["gkin_file"], view["launches"], view)
    if len(paths) > 1:
      print("GK inputs of %d launches: %s" % (len(paths), ", ".join(paths)))
  if opts.get("summary_flag") or opts.get("summary_json_flag"):
    import solve_display
    solve_display.hold_summary(ad.summary_record(rec, answer), opts.get("summary_flag"),
                                opts.get("summary_json_flag"))
  if opts.get("prover_rawresult_flag") and view["launches"]:
    return ad.raw_result(view["launches"])
  if lv["explain"] and explained:
    return "%s\n\n%s" % (answer, explained)
  return answer


def solve_one_query(source, query_pkg, prof, rec, ledger, view, selection=None, limits=None):
  """The result of one query, or None under -nosolve (the query is compiled, GK is not launched)."""
  qa = ar.compile_query(query_pkg, source, limits if limits is not None else prof["limits"], **(selection or {}))
  view["queries"].append(qa)
  rec["query"] = {"id": qa["query"]["id"], "kind": qa["query"]["kind"], "hash": qa["hash"],
                  "outcome": qa["outcome"] and qa["outcome"]["outcome"]}
  if prof.get("nosolve"):
    return None
  return aa.solve(source, qa, prof["backend"], {"seconds": prof["seconds"]}, ledger)


NOT_SOLVED = {"outcome": "not_solved", "detail": "-nosolve: the query was compiled and GK was not launched"}


def new_view(options=None):
  """What the output levels read and the run record does not keep: the artifacts and the raw text of each launch."""
  return {"source": None, "queries": [], "launches": [], "stage1_packages": None, "query_texts": {}, "unit_texts": {},
          "nosolve": bool((options or {}).get("prover_nosolve_flag"))}


def run_text(text, prof, rec, ledger, llm, version, max_tokens, view=None):
  view = new_view() if view is None else view
  bundle = load_bundle(prof["bundle"])
  if bundle is None:
    res = ar.result(ar.NOT_IMPLEMENTED, operation="translate_source", reason="no_action_prompt_bundle",
                    detail="the action prompt bundle %r has missing files; use -formal with a Stage-2 record"
                           % prof["bundle"])
    rec["result"] = res
    return aen.answer_text(res)
  tr = translate(text, bundle, llm, version, max_tokens, prof["think"])
  rec["translation"] = {k: v for k, v in tr.items() if k != "source"}
  view["stage1_packages"] = tr.get("stage1_packages")
  src = tr["source"]
  if src is not None:
    rec["source"] = {"hashes": src["hashes"], "support": src["support"]}
    view["source"] = src
  if tr["status"] == "unsupported_translation":
    res = ar.result("unsupported_translation", **tr["unsupported"])
  elif tr["status"] != "ok":
    res = ar.result(tr["status"], diagnostics=tr["errors"])
  elif not tr["queries"]:
    res = ar.result(ar.source_outcome(src)["outcome"])
  else:
    res = solve_one_query(src, tr["queries"][0], prof, rec, ledger, view,
                 tr.get("query_contexts", {}).get(tr["queries"][0][1], {}))
    if res is None:
      rec["result"] = dict(NOT_SOLVED)
      return ""
  rec["result"] = copy.deepcopy(res)        # the run record keeps its own copy
  return aen.answer_text(res)


def _run_formal(text, prof, rec, ledger, view=None):
  """A formal record, or the path of a file holding one: {"units": [{"id", "stage2", "text"?, "stage1"?,
  "context"?}], "queries": [{"id"?, "stage2", "text"?, "planning_root"?, "ambient"?, "knower"?, "limits"?}],
  "entities"?, "worlds"?, "text"?, "types"?}.  No model call.  A formal record keeps its explicit semantics: no type
  is derived from its Stage-1 fields; "types" lists given type records (action_route.TYPE_KINDS)."""
  view = new_view() if view is None else view
  src_text = text
  if text and not text.lstrip().startswith("{") and os.path.isfile(text.strip()):
    # the path of a record file (solve.py reads a short file name itself; a longer path arrives as text)
    with open(text.strip()) as f:
      src_text = f.read()
  try:
    case = json.loads(src_text)
  except ValueError as e:
    raise OptionError("-formal needs a JSON record or the path of a file holding one: %s" % e)
  if not isinstance(case, dict) or not isinstance(case.get("units"), list):
    raise OptionError("-formal needs a JSON object with a list of units")
  units = case["units"]
  s1 = None
  if all(u.get("stage1") for u in units):
    s1 = [{"id": u["id"], "text": u.get("text"), "stage1": u["stage1"]} for u in units]
  contexts = {u["id"]: u["context"] for u in units if u.get("context")}
  src = ar.compile_source(s1, [u["stage2"] for u in units], case.get("profile") or la.PROFILE, case.get("text"),
                          case.get("entities"), worlds=case.get("worlds"), contexts=contexts or None,
                          provenance={"kind": "formal_input"}, types=case.get("types"))
  rec["source"] = {"hashes": src["hashes"], "support": src["support"]}
  view["source"] = src
  queries = case.get("queries") or []
  view["unit_texts"] = {u["id"]: u["text"] for u in units if u.get("text")}
  view["query_texts"] = {q["stage2"][1]: q.get("text") for q in queries
                         if isinstance(q.get("stage2"), list) and len(q["stage2"]) > 1}
  if not queries:
    res = ar.result(ar.source_outcome(src)["outcome"])
    rec["result"] = res
    return aen.answer_text(res)
  out, results = [], []
  for q in queries:
    sel = {k: q[k] for k in ("planning_root", "ambient", "knower") if k in q}
    lim = q.get("limits")
    res = solve_one_query(src, q["stage2"], prof, rec, ledger, view, sel, lim if lim is not None else prof["limits"])
    if res is None:
      continue
    results.append(res)
    out.append("%s: %s" % (q["stage2"][1], aen.answer_text(res)))
  if prof.get("nosolve"):
    rec["result"] = dict(NOT_SOLVED)
    return ""
  if len(results) == 1:
    rec["result"] = results[0]
    return aen.answer_text(results[0])
  failed = [q["stage2"][1] for q, r in zip(queries, results) if not aen.answered(r)]
  rec["result"] = {"outcome": "several", "results": results, "failed": failed}
  if failed:
    # one failed query makes the call a failure: the string starts with Error:, and every query's line follows
    return "Error: %d of %d queries failed (%s)\n%s" % (len(failed), len(results), ", ".join(failed), "\n".join(out))
  return "\n".join(out)
