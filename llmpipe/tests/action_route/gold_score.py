"""The checks of an action-route result against a structured gold expectation, for the fixture checks.

  score(result, expect) -> {"ok", "checks", "info", "not_checked", "category", "confidence_status"}

The gold expectations are the `expect` records of the fixtures (`fixtures/README.md`).  Scoring is additive: the
ordinary answer matching is not changed, and the planning test files are graded by `planning_check`.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "solver"))
import action_answer as aa   # noqa: E402
import action_route as ar    # noqa: E402

CUTOFF = aa.CUTOFF


# the gold expectation keys, by who checks them
ANSWER_KEYS = ("outcome", "alternative", "not_outcome", "answer", "not_answer", "forbidden_answers",
               "forbidden_outcomes", "plan", "forbidden_plans", "witness", "facts", "step", "reason", "unit", "units",
               "record", "confidence")
INFO_KEYS = ("reference_shortest_length", "render", "on_validated_backend")
OTHER_LAYER_KEYS = {"clauses": "check_action_queries", "view_roles_included": "check_action_queries",
                    "view_roles_excluded": "check_action_queries", "source_hash_after": "check_action_queries",
                    "obligations": "check_action_queries", "detail": "check_action_validation",
                    "eligible_candidates": "check_action_gk", "diagnostics": "check_action_gk",
                    "per_candidate": "check_action_answer", "stage": "the ordinary route (WP14)"}
DOCUMENTATION_KEYS = ("evidence", "historical_label", "profile_mismatch")
UNCHECKED_KEYS = ("entity", "artifact_retains")
PINNED_TOLERANCE = 0.0001        # a bare pinned number: GK prints four decimals


def _confidence_check(result, pin):
  """(check or None, info) for a gold confidence.  A number or {"value", "tolerance"} is pinned; a one-frame
  {"per_frame"} is pinned to that value; {"forbidden": {"value"}} must not be met; other forms ({"recorded"},
  several frames) record the value and require only the cutoff."""
  got = result.get("confidence")
  info = {"confidence": got, "confidence_status": result.get("confidence_status")}
  if isinstance(pin, (int, float)) and not isinstance(pin, bool):
    want, tol = pin, PINNED_TOLERANCE
  elif isinstance(pin, dict) and "value" in pin:
    want, tol = pin["value"], pin.get("tolerance", PINNED_TOLERANCE)
  elif isinstance(pin, dict) and "per_frame" in pin and pin.get("frames_crossed") == 1:
    want, tol = pin["per_frame"], PINNED_TOLERANCE
  else:
    info["confidence_pin"] = "recorded, not pinned"
    return (got is not None and got >= CUTOFF), info
  ok = got is not None and abs(got - want) <= tol
  if isinstance(pin, dict) and isinstance(pin.get("forbidden"), dict):
    ok = ok and not (got is not None and abs(got - pin["forbidden"]["value"]) <= tol)
  info["confidence_pin"] = want
  return ok, info


def score(result, expect):
  """The checks of a result against a structured gold expectation.

  Returns {"ok", "checks": {name: bool}, "info", "not_checked", "category"}.  Every answer-level key the
  expectation states is checked (`ANSWER_KEYS`):
    outcome (or its `alternative`), not_outcome, answer, not_answer, forbidden answers, outcomes and plans;
    plan: the result has an accepted plan that the replay validated (another or a longer valid plan than the gold
      one is not a failure: `same_as_gold_plan` and `extra_length` report the difference);
    witness; facts (a subset) and step of a conflict; reason, unit and units of an unsupported result; record (a
      diagnostic); confidence (a pinned value with its tolerance, a forbidden value, else the cutoff).
  `render`, `reference_shortest_length` and `on_validated_backend` are information.  Keys of another layer
  (clauses, views, source hashes, obligations, compile details, adapter records, the ordinary route's stage),
  prose, and keys no check reads are listed in `not_checked`; a key the scorer does not know fails `known_keys`.
  `category` separates a validated plan, an empty plan, a supplied sequence, an answer, a length constraint,
  unsupported input, a bounded non-discovery, a backend limit, a validation finding, a source without a question,
  an execution failure and a query the action route does not implement.
  """
  checks, info = {}, {}
  o = result["outcome"]
  has_plan = o in ("plan_found", "goal_already_holds")
  alt = expect.get("alternative") or {}
  if expect.get("outcome") is not None:
    checks["outcome"] = o in (expect["outcome"], alt.get("outcome"))
  if expect.get("not_outcome"):
    checks["not_outcome"] = o not in expect["not_outcome"]
  if expect.get("answer") is not None:
    checks["answer"] = result["answer"] == expect["answer"]
  if expect.get("not_answer"):
    checks["not_answer"] = not set(result.get("answers") or [result["answer"]]) & set(expect["not_answer"])
  if expect.get("forbidden_answers"):
    checks["forbidden_answers"] = result["answer"] not in expect["forbidden_answers"]
  if expect.get("forbidden_outcomes"):
    checks["forbidden_outcomes"] = o not in expect["forbidden_outcomes"]
  if expect.get("plan") is not None:
    checks["plan"] = has_plan
    if has_plan:
      info["same_as_gold_plan"] = result["plan"] == expect["plan"]
      shortest = expect.get("reference_shortest_length")
      info["extra_length"] = len(result["plan"]) - (shortest if shortest is not None else len(expect["plan"]))
  if expect.get("forbidden_plans"):
    checks["forbidden_plans"] = not has_plan or result["plan"] not in expect["forbidden_plans"]
  if expect.get("witness"):
    got = result.get("witnesses") or {}
    checks["witness"] = has_plan and all(got.get(k) == v for k, v in expect["witness"].items())
  if expect.get("facts"):
    checks["facts"] = o == "inconsistent_action_state" and set(expect["facts"]) <= set(result.get("facts") or [])
  if expect.get("step") is not None:
    checks["step"] = o == "inconsistent_action_state" and result.get("step") == expect["step"]
  d0 = result["diagnostics"][0] if result["diagnostics"] and isinstance(result["diagnostics"][0], dict) else {}
  if expect.get("reason"):
    checks["reason"] = expect["reason"] in set(d0.get("reasons") or [d0.get("reason")])
  if expect.get("unit"):
    checks["unit"] = expect["unit"] in (d0.get("units") or [])
  if expect.get("units"):
    checks["units"] = set(expect["units"]) <= set(d0.get("units") or [])
  if expect.get("record"):
    checks["record"] = any(expect["record"] in str(d) for d in result["diagnostics"])
  if expect.get("confidence") is not None:
    checks["confidence"], more = _confidence_check(result, expect["confidence"])
    info.update(more)
  if expect.get("render") is not None:
    info["render_exact"] = result.get("render") == expect["render"]
  if expect.get("on_validated_backend") is not None:
    info["on_validated_backend"] = "not checked: the selected backend does not validate the requirement"
  not_checked = {"other_layer": {k: OTHER_LAYER_KEYS[k] for k in expect if k in OTHER_LAYER_KEYS},
                 "documentation": [k for k in expect if k in DOCUMENTATION_KEYS],
                 "unchecked": [k for k in expect if k in UNCHECKED_KEYS]}
  unknown = [k for k in expect if k not in ANSWER_KEYS + INFO_KEYS + DOCUMENTATION_KEYS + UNCHECKED_KEYS
             and k not in OTHER_LAYER_KEYS]
  if unknown:
    checks["known_keys"] = False
    not_checked["unknown"] = unknown
  kind = (result.get("query") or {}).get("kind")
  cat = {"plan_found": "validated_plan", "goal_already_holds": "empty_plan", "not_found": "bounded_non_discovery",
         "source_compiled": "source_without_question",
         "insufficient_search_allowance": "length_constraint", "unsupported_translation": "unsupported_input",
         "translation_invalid": "unsupported_input", "unsupported_backend_requirement": "backend_limit",
         "backend_unavailable": "backend_limit", "backend_incompatible": "backend_limit",
         "inconsistent_action_state": "validation", "candidate_not_validated": "validation",
         ar.NOT_IMPLEMENTED: "not_implemented"}.get(o, "execution_failure")
  if o == "verification_result":
    cat = "supplied_sequence" if kind == "verify" and result.get("verdicts") and len(result["verdicts"]) > 1 else "answer"
  return {"ok": all(checks.values()), "checks": checks, "info": info, "not_checked": not_checked, "category": cat,
          "confidence_status": result.get("confidence_status")}
