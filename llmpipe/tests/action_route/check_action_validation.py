"""WP03 unit checks: artifacts, the four operations, structural validation.

No model, no GK.  Five groups:

  gold        every effective gold case goes through compile_source and
              compile_query; the structural verdicts must equal the gold
  malformed   each malformed source or query package is rejected with the
              named error code, the unit and a path
  reasons     every unsupported reason is either detected here on an example
              or recorded through add_diagnostic by name; both block
              source_compiled
  artifacts   deterministic hashes and serialization, source immutability
              under query attachment, version and tamper checks
  operations  translate_source with a bundle whose files are missing reports not_implemented; solve_query
              stops before any launch on a registered build whose binary is absent; the ordinary profile
              rejects the action syntax
  worlds      (migration steps 1b.1, 1b.2, 1b.5) the worlds declaration, the
              unit context records and the query's selection fields are
              validated with the named diagnostics and recorded

A gold unit whose unsupported reason belongs to a later compiler pass is
counted as deferred, not as passed: this check proves only that the
structural pass leaves it alone.
"""

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "solver"))
import action_gk as ag
import action_route as ar
import fixture_materialize as fm
import lc_action as la


class Bad(Exception):
  pass



ABSENT = "absent_for_checks"


def absent_backend():
  """A registered build whose binary is missing: solve_query then stops with backend_unavailable before any launch,
  so an offline check can pass a runnable query to it."""
  if ABSENT not in ag.BACKENDS:
    ag.BACKENDS[ABSENT] = dict(ag.backend_profile(), name=ABSENT, path=os.path.join(HERE, "no_such_gk_binary"))
  return {"backend": ABSENT}

def with_pending(a, name="a_later_pass"):
  """A copy of a source artifact that names one more pending pass, rehashed."""
  b = copy.deepcopy(a)
  b["pending_passes"].append(name)
  b["hashes"] = ar.source_hashes(b)
  return b


def need(cond, message):
  if not cond:
    raise Bad(message)


# gold `scope` names for the recognized forms
SCOPE = {"description_static": "static", "description_initial": "initial", "state_law": "standing",
         "availability": "availability", "denial": "denial", "restriction": "restriction", "effect": "effect"}


def profile_name(p):
  return p["name"] if isinstance(p, dict) else p


def gold_source(case):
  s1 = None
  if case["input_kind"] == "text":
    s1 = [{"id": u["id"], "text": u.get("text"), "stage1": u.get("stage1")} for u in case["units"]]
  return ar.compile_source(s1, [u["stage2"] for u in case["units"]], case["profile"], case["text"], case["entities"],
                           worlds=case.get("worlds"), contexts=fm.contexts(case))


def gold_limits(q):
  lim = q.get("limits")
  return {"search_cap": lim["search_cap"], "explicit": lim.get("explicit", True)} if lim else None


def check_gold():
  units = queries = deferred = deferred_queries = 0
  deferred_by = {}
  detected = set()
  for case in fm.load_all():
    if profile_name(case["profile"]) != la.PROFILE or not case["units"]:
      continue
    w = case["case"]
    a = gold_source(case)
    need(all(d["level"] == "unsupported" and d["reason"] == "unsupported_location_granularity" for d in a["diagnostics"]),
         "%s: source-level diagnostics %r" % (w, a["diagnostics"]))
    need([u["id"] for u in a["units"]] == [u["id"] for u in case["units"]],
         "%s: the artifact has other units than the source" % w)
    for u, g in zip(a["units"], case["units"]):
      units += 1
      gold = g["compile"] if g["compile"] == "supported" else g["compile"]["unsupported"]
      mine = sorted({d.get("reason") or "invalid:" + d["code"] for d in u["diagnostics"]}) or ["supported"]
      need(u["stage2"] == g["stage2"], "%s/%s: the artifact changed the formula" % (w, u["id"]))
      if gold == "supported" or la.REASONS.get(gold) in ("structural",) + tuple(a["passes"]):
        need(mine == [gold], "%s/%s: gold %s, structural pass %s" % (w, u["id"], gold, mine))
        detected.add(gold)
      else:
        need(gold in la.REASONS, "%s/%s: gold reason %s is not registered" % (w, u["id"], gold))
        need(mine == ["supported"], "%s/%s: a %s unit must pass the structural layer, got %s" % (w, u["id"], gold, mine))
        deferred += 1
        deferred_by[la.REASONS[gold]] = deferred_by.get(la.REASONS[gold], 0) + 1
      if gold == "supported":
        need(SCOPE[u["form"]] == g["scope"], "%s/%s: form %s, gold scope %s" % (w, u["id"], u["form"], g["scope"]))
    need(a["support"]["unsupported_units"] == sorted(u["id"] for u in a["units"] if u["status"] == "unsupported"), "%s: support summary" % w)
    structural_bad = a["support"]["status"] == "unsupported"
    for q in case["queries"]:
      if not q.get("stage2"):
        continue
      queries += 1
      wq = "%s/%s" % (w, q["id"])
      h = dict(a["hashes"])
      qa = ar.compile_query(q["stage2"], a, gold_limits(q), **fm.selection(q))
      need(a["hashes"] == h and ar.source_hashes(a) == h, "%s: query attachment changed the source" % wq)
      e = q["expect"]
      out = (qa["outcome"] or {}).get("outcome")
      invalid = any(d["level"] == "invalid" for d in qa["diagnostics"])
      need(invalid == (e.get("outcome") == "translation_invalid"), "%s: invalid=%s, gold %s" % (wq, invalid, e.get("outcome")))
      if invalid:
        need(e.get("detail") in (None,) + tuple(d["code"] for d in qa["diagnostics"]), "%s: error code, gold detail %s" % (wq, e.get("detail")))
        continue
      need(not qa["diagnostics"], "%s: %r" % (wq, qa["diagnostics"]))
      if q["view"] != "ordinary":
        need(qa["view"] == q["view"], "%s: view %s, gold %s" % (wq, qa["view"], q["view"]))
      if structural_bad:
        need(out == "unsupported_translation", "%s: an unsupported source must give unsupported_translation, got %s" % (wq, out))
        need(e.get("outcome") == "unsupported_translation" and e.get("reason") in qa["outcome"]["reasons"],
             "%s: gold %s/%s, mine %s" % (wq, e.get("outcome"), e.get("reason"), qa["outcome"]))
        named = e.get("units") or ([e["unit"]] if e.get("unit") else [])
        if named:     # exact attribution: every diagnosed unit and no other
          need(sorted(named) == qa["outcome"]["units"], "%s: gold units %s, mine %s" % (wq, sorted(named), qa["outcome"]["units"]))
        continue
      if e.get("outcome") == "unsupported_translation" and la.REASONS.get(e.get("reason")) in a["passes"]:
        # a per-query reason of a pass that ran: the query artifact decides it, with exact unit attribution
        need(out == "unsupported_translation" and qa["outcome"]["reasons"] == [e["reason"]],
             "%s: gold %s, mine %s" % (wq, e["reason"], qa["outcome"]))
        named = e.get("units") or ([e["unit"]] if e.get("unit") else [])
        need(not named or sorted(named) == qa["outcome"]["units"], "%s: gold units %s, mine %s" % (wq, named, qa["outcome"]["units"]))
        continue
      if e.get("outcome") == "unsupported_translation":
        # the gold reason belongs to a later pass; the structural layer gives no verdict here
        need(out is None and e.get("reason") in la.REASONS and la.REASONS[e["reason"]] not in ["structural"] + a["passes"],
             "%s: gold %s/%s, mine %s" % (wq, e.get("outcome"), e.get("reason"), out))
        deferred_queries += 1
        continue
      need((out == "insufficient_search_allowance") == (e.get("outcome") == "insufficient_search_allowance"),
           "%s: allowance outcome %s, gold %s" % (wq, out, e.get("outcome")))
      if "seed" in q:
        need(qa["search"]["seed"] == q["seed"], "%s: seed %s, gold %s" % (wq, qa["search"]["seed"], q["seed"]))
      if "require_zero_remaining" in q:
        need(qa["search"]["require_zero_remaining"] == q["require_zero_remaining"], "%s: require_zero_remaining" % wq)
  print("  gold: %d units and %d queries agree; deferred to later passes: %d units %s and %d queries"
        % (units, queries, deferred, json.dumps(deferred_by, sort_keys=True), deferred_queries))
  return detected


# ---------------------------------------------------------------------------
# malformed packages

ENTS = {"Ann 1": "person", "Bob 2": "person", "Haapsalu 3": "place", "Tallinn 4": "place",
        "hand 5": "hand", "a 6": "block", "b 7": "block", "egg 8": "food", "whisk 9": "artifact"}
MOVE = ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "bus"]
TAKE = ["take", "hand 5", "a 6"]
RED = ["has property", "red", "a 6"]
AT = ["is rel2", "located_at", "Ann 1", "Tallinn 4"]
EXE = ["executable", TAKE]
WET = ["has property", "wet", "a 6"]


def S(f, i="S1"):
  return ["@id", i, ["holds", "W0", f]]


def Q(p, i="Q1"):
  return ["@id", i, p]


BAD_SOURCE = [
  ("action term as a fluent atom", S(MOVE), "action_term_position"),
  ("action term inside a fluent", S(["has property", "red", TAKE]), "term"),
  ("wrong action arity", S(["can", "hand 5", ["take", "hand 5"]]), "action_arity"),
  ("unknown constructor", S(["can", "Ann 1", ["fly", "Ann 1", "Tallinn 4"]]), "action_term"),
  ("actor disagreement", S(["can", "Bob 2", MOVE]), "actor_agreement"),
  ("executable with its own actor slot", S(["implies", ["executable", "hand 5", TAKE], RED]), "arity"),
  ("unbound variable", S(["can", "hand 5", ["take", "hand 5", "X"]]), "unbound_variable"),
  ("variable bound twice", S(["forall", "X", ["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "red", "X"]]]]), "rebound_variable"),
  ("negated executable in a source", S(["implies", ["not", ["executable", TAKE]], RED]), "executable_position"),
  ("action operator in a restriction consequent", S(["implies", ["executable", TAKE], ["can", "hand 5", TAKE]]), "restriction_consequent"),
  ("nested after", S(["after", TAKE, ["after", TAKE, RED]]), "nested_after"),
  ("negated after", S(["not", ["after", TAKE, RED]]), "after_position"),
  ("executable inside an effect head", S(["after", TAKE, ["executable", TAKE]]), "executable_position"),
  ("event predicate with a free event variable", S(["has actor", "E", "Ann 1"]), "unbound_variable"),
  ("event predicate with a Skolem term", S(["exists", "E", ["has actor", "E", ["sk", "X"]]]), "term"),
  ("event predicate with an undeclared participant", S(["exists", "E", ["has actor", "E", "Ghost 99"]]), "unknown_entity"),
  ("event type that is not lexical", S(["exists", "E", ["has type", "E", "Ann 1"]]), "lexical_value"),
  ("event context word that is not lexical", S(["exists", "E", ["has location", "E", "Tallinn 4", "Ann 1"]]), "lexical_value"),
  ("after in an antecedent", S(["implies", ["after", TAKE, RED], RED]), "after_in_antecedent"),
  ("disjunctive effect head", S(["after", TAKE, ["or", RED, ["has property", "blue", "a 6"]]]), "after_head"),
  ("conditional effect head", S(["after", TAKE, ["implies", RED, ["has property", "blue", "a 6"]]]), "after_head"),
  ("can in an effect head", S(["after", TAKE, ["can", "hand 5", TAKE]]), "can_position"),
  ("nested state_law", S(["state_law", ["state_law", RED]]), "state_law_position"),
  ("negated state_law", S(["not", ["state_law", RED]]), "state_law_position"),
  ("state_law in an antecedent", S(["implies", ["state_law", RED], RED]), "state_law_position"),
  ("state_law under a quantifier", S(["forall", "X", ["state_law", ["has property", "red", "X"]]]), "state_law_position"),
  ("effect inside state_law", S(["state_law", ["after", TAKE, RED]]), "state_law_content"),
  ("permission and effect in one unit", S(["and", ["can", "hand 5", TAKE], ["after", TAKE, RED]]), "mixed_law_forms"),
  ("availability and denial in one unit", S(["and", ["can", "hand 5", TAKE], ["not", ["can", "Ann 1", MOVE]]]), "mixed_law_forms"),
  ("negated default permission", S(["not", ["normally", ["can", "Ann 1", MOVE]]]), "can_position"),
  ("disjunctive permission", S(["or", ["can", "hand 5", TAKE], ["can", "Ann 1", MOVE]]), "can_position"),
  ("unspecified as an entity", S(["is rel2", "located_at", "Ann 1", "unspecified"]), "unspecified_position"),
  ("unspecified as the actor", S(["can", "unspecified", ["take", "unspecified", "a 6"]]), "unspecified_position"),
  ("lexical constant in an entity slot", S(["can", "Ann 1", ["take", "Ann 1", "block"]]), "entity_slot"),
  ("Skolem term", S(["have", "Ann 1", ["sk", "X"]]), "term"),
  ("witness constant", S(["have", "Ann 1", "sk_W"]), "witness_constant"),
  ("undeclared entity", S(["isa", "person", "Zed 99"]), "unknown_entity"),
  ("variable as a property value", S(["forall", "V", ["has property", "V", "a 6"]]), "lexical_value"),
  ("unknown predicate", S(["weighs", "a 6", "heavy"]), "unknown_predicate"),
  ("wrong fluent arity", S(["has property", "red"]), "arity"),
  ("unary implication", S(["implies", RED]), "arity"),
  ("two operands under not", S(["not", RED, RED]), "arity"),
  ("query package inside the source", ["@id", "S1", ["plan", AT]], "query_in_source"),
  ("an undeclared world", ["@id", "S1", ["holds", "W1", RED]], "undeclared_world"),
  ("a world name as a variable", S(["forall", "W0", ["implies", ["isa", "block", "W0"], ["has property", "red", "W0"]]]), "reserved_variable"),
  ("confidence with another id", ["@id", "S1", ["and", ["holds", "W0", RED], ["@p", "S2", 0.8]]], "package"),
  ("confidence out of range", ["@id", "S1", ["and", ["holds", "W0", RED], ["@p", "S1", 1.5]]], "package"),
  ("event form mixed with an action operator",
   S(["and", ["exists", "E", ["and", ["isa", "activity", "E"], ["has actor", "E", "Ann 1"]]], ["can", "Ann 1", MOVE]]), "mixed_event_form"),
  ("time wrapper around a state fact", S(["@time", "until noon", RED]), "time_wrapper"),
]

BAD_QUERY = [
  ("a world name as the asked variable", Q(["ask", "W1", ["has property", "red", "W1"]]), "reserved_variable"),
  ("two queries", ["and", Q(["plan", AT]), Q(["plan", AT], "Q2")], "query_count"),
  ("source package as a query", Q(["holds", "W0", AT]), "source_in_query"),
  ("unknown query package", Q(["achieve", AT]), "package"),
  ("negative bound", Q(["plan", AT, ["steps", "at_most", -1]]), "step_constraint"),
  ("Boolean bound", Q(["plan", AT, ["steps", "exactly", True]]), "step_constraint"),
  ("fractional bound", Q(["plan", AT, ["steps", "at_most", 2.5]]), "step_constraint"),
  ("unknown step comparison", Q(["plan", AT, ["steps", "at_least", 2]]), "step_constraint"),
  ("free variable in a goal", Q(["plan", ["is rel2", "located_at", "Ann 1", "X"]]), "unbound_variable"),
  ("after in a query", Q(["question", ["after", TAKE, RED]]), "after_in_query"),
  ("state_law in a query", Q(["question", ["state_law", RED]]), "state_law_position"),
  ("supplied sequence with a variable", Q(["verify", [["take", "hand 5", "X"]], RED]), "sequence_not_ground"),
  ("supplied sequence with a malformed action", Q(["verify", [["take", "hand 5"]], RED]), "action_arity"),
  ("verify without a list", Q(["verify", TAKE, RED]), "action_term"),
  ("unknown entity in a query", Q(["plan", ["is rel2", "located_at", "Ann 1", "Tartu 77"]]), "unknown_entity"),
  ("ask without its variable", Q(["ask", "X", AT]), "ask_variable"),
  ("extra question operand", Q(["question", RED, RED]), "arity"),
  ("can in a question (source-only form)", Q(["question", ["can", "Ann 1", MOVE]]), "can_in_query"),
  ("can in a verify goal (source-only form)", Q(["verify", [TAKE], ["can", "hand 5", TAKE]]), "can_in_query"),
  ("can in an ask", Q(["ask", "X", ["can", "X", ["move", "X", "Haapsalu 3", "Tallinn 4", "bus"]]]), "can_in_query"),
  ("one witness name bound twice in a goal",
   Q(["plan", ["and", ["exists", "X", ["is rel2", "located_at", "Ann 1", "X"]], ["exists", "X", ["isa", "port", "X"]]]]), "split_goal_witness"),
  ("event form in a query", Q(["question", ["exists", "E", ["and", ["isa", "activity", "E"], ["has actor", "E", "Ann 1"]]]]), "event_form_in_query"),
]

GOOD_SOURCE = [
  ("ground availability", S(["can", "Ann 1", MOVE]), "availability"),
  ("conditional availability", S(["implies", ["and", ["has property", "broken", "egg 8"], ["have", "Ann 1", "whisk 9"]],
                                  ["can", "Ann 1", ["change", "Ann 1", "egg 8", "whisked", "whisk 9"]]]), "availability"),
  ("default availability", S(["forall", "F", ["forall", "T", ["normally", ["can", "Ann 1", ["move", "Ann 1", "F", "T", "bus"]]]]]), "availability"),
  ("denial", S(["not", ["can", "Ann 1", MOVE]]), "denial"),
  ("restriction", S(["forall", "X", ["implies", ["executable", ["take", "hand 5", "X"]], ["has property", "red", "X"]]]), "restriction"),
  ("class-guarded restriction", S(["forall", "H", ["forall", "X", ["implies", ["and", ["isa", "hand", "H"], ["executable", ["take", "H", "X"]]],
                                                                     ["has property", "red", "X"]]]]), "restriction"),
  ("strict signed effect", S(["after", ["change", "Ann 1", "egg 8", "cooked", "unspecified"], ["not", ["has property", "raw", "egg 8"]]]), "effect"),
  ("conditional effect", S(["implies", RED, ["after", TAKE, ["and", ["has property", "held", "a 6"], ["not", RED]]]]), "effect"),
  ("standing law", S(["state_law", ["forall", "X", ["implies", ["has property", "whisked", "X"], ["has property", "ready", "X"]]]]), "state_law"),
  ("quantified initial description", S(["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "clear_top", "X"]]]), "description_initial"),
  ("static description", S(["and", ["isa", "person", "Ann 1"], ["connected", "Haapsalu 3", "Tallinn 4", "bus"]]), "description_static"),
  ("source existential", S(["exists", "W", ["and", ["isa", "whisk", "W"], ["have", "Ann 1", "W"]]]), "description_initial"),
  ("uncertain availability", ["@id", "S1", ["and", ["holds", "W0", ["can", "Ann 1", MOVE]], ["@p", "S1", 0.8]]], "availability"),
  ("effect stated with full confidence", ["@id", "S1", ["and", ["holds", "W0", ["after", TAKE, RED]], ["@p", "S1", 1]]], "effect"),
  ("restriction with a signed conjunctive requirement", S(["implies", EXE, ["and", RED, ["not", WET], ["isa", "block", "a 6"]]]), "restriction"),
  ("two valid restrictions in one unit", S(["and", ["implies", EXE, RED], ["implies", EXE, ["not", WET]]]), "restriction"),
  ("conditional denial", S(["implies", RED, ["not", ["can", "hand 5", TAKE]]]), "denial"),
  ("availability under an existential condition",
   S(["forall", "X", ["implies", ["and", ["isa", "person", "X"], ["exists", "Y", ["and", ["isa", "ticket", "Y"], ["have", "X", "Y"]]]],
                      ["can", "X", ["move", "X", "Haapsalu 3", "Tallinn 4", "bus"]]]]), "availability"),
  ("open lexical values", S(["can", "Ann 1", ["change", "Ann 1", "egg 8", "frobnicated", "whisk 9"]]), "availability"),
  ("a means outside the standard modes", S(["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "hovercraft"]]), "availability"),
]

GOOD_QUERY = [
  ("plan", Q(["plan", AT]), "discovery"),
  ("zero-step reachable", Q(["reachable", AT, ["steps", "exactly", 0]]), "discovery"),
  ("exact-step plan", Q(["plan", AT, ["steps", "exactly", 2]]), "discovery"),
  ("conjunctive goal", Q(["plan", ["and", AT, ["not", RED]]]), "discovery"),
  ("existential goal with one shared witness",
   Q(["reachable", ["exists", "X", ["and", ["isa", "port", "X"], ["is rel2", "located_at", "Ann 1", "X"]]]]), "discovery"),
  ("executability question", Q(["question", ["executable", TAKE]]), "snapshot"),
  ("quantified initial-state question", Q(["question", ["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "red", "X"]]]]), "snapshot"),
  ("ask", Q(["ask", "X", ["is rel2", "located_at", "Ann 1", "X"]]), "snapshot"),
  ("supplied sequence", Q(["verify", [TAKE, ["put_on", "hand 5", "a 6", "b 7"]], ["is rel2", "on", "a 6", "b 7"]]), "verify"),
  ("empty supplied sequence", Q(["verify", [], RED]), "verify"),
  ("executability after a supplied sequence", Q(["verify", [TAKE], ["executable", ["put_on", "hand 5", "a 6", "b 7"]]]), "verify"),
  ("negated executability after a supplied sequence", Q(["verify", [TAKE], ["not", ["executable", TAKE]]]), "verify"),
  ("negated literal under exists", Q(["plan", ["exists", "X", ["and", ["isa", "block", "X"], ["not", ["has property", "red", "X"]]]]]), "discovery"),
]

# well-formed packages outside the fragment: (reason, kind, package)
EVENT_OK = ["exists", "E", ["and", ["isa", "activity", "E"], ["has type", "E", "sing"], ["has actor", "E", "Ann 1"],
                            ["has location", "E", "Tallinn 4", "in"]]]
EXTRA_UNSUPPORTED = [
  ("unsupported_goal_form", "query", Q(["plan", ["or", AT, RED]])),
  ("unsupported_goal_form", "query", Q(["plan", ["executable", TAKE]])),
  ("unsupported_goal_form", "query", Q(["plan", ["not", ["and", RED, AT]]])),
  ("unsupported_goal_form", "query", Q(["reachable", ["not", ["exists", "X", ["has property", "red", "X"]]]])),
  ("unsupported_goal_form", "query", Q(["plan", ["forall", "X", ["implies", ["isa", "block", "X"], ["has property", "red", "X"]]]])),
  ("unsupported_goal_form", "query", Q(["verify", [TAKE], ["not", ["and", RED, ["executable", TAKE]]]])),
  ("unsupported_law_form", "source", S(["not", ["implies", RED, ["can", "hand 5", TAKE]]])),
  ("unsupported_law_form", "source", S(["implies", ["or", RED, AT], ["can", "hand 5", TAKE]])),
  ("unsupported_law_form", "source", S(["implies", ["not", ["and", RED, AT]], ["after", TAKE, RED]])),
  ("unsupported_law_form", "source", S(["implies", RED, ["implies", AT, ["can", "hand 5", TAKE]]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["or", RED, WET]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["forall", "X", ["has property", "red", "X"]]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["implies", RED, WET]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["not", ["and", RED, WET]]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["exists", "X", ["have", "Ann 1", "X"]]])),
  ("unsupported_restriction_scope", "source", S(["and", ["implies", EXE, RED], ["implies", EXE, ["or", RED, WET]]])),
  ("unsupported_restriction_scope", "source", S(["implies", EXE, ["=", "hand 5", "hand 5"]])),
  ("unsupported_executability_assertion", "source", S(["executable", TAKE])),
  ("unsupported_executability_assertion", "source", S(["implies", RED, ["executable", TAKE]])),
  ("existential_effect_head", "source", S(["after", ["change", "Ann 1", "egg 8", "baked", "unspecified"], ["exists", "C", ["isa", "cake", "C"]]])),
  ("mixed_scope_rule", "source", S(["after", TAKE, ["isa", "held_thing", "a 6"]])),
  ("defeasible_text_effect", "source", S(["after", TAKE, ["normally", RED]])),
  ("defeasible_text_effect", "source", S(["normally", ["after", TAKE, RED]])),
  ("defeasible_text_effect", "source", S(["forall", "X", ["normally", ["after", ["take", "hand 5", "X"], ["has property", "held", "X"]]]])),
  ("defeasible_text_effect", "source", ["@id", "S1", ["and", ["holds", "W0", ["after", TAKE, RED]], ["@p", "S1", 0.8]]]),
  ("occurrence", "source", S(EVENT_OK)),
]


def check_malformed():
  for name, pkg, code in BAD_SOURCE:
    before = copy.deepcopy(pkg)
    v = la.validate_source_unit(pkg, ENTS)
    codes = [d.get("code") for d in v["diagnostics"] if d["level"] == "invalid"]
    need(v["status"] == "invalid" and code in codes, "source %r: expected %s, got %s %s" % (name, code, v["status"], codes))
    need(all(d["unit"] == "S1" and d["path"].startswith("/") and d["message"] for d in v["diagnostics"]),
         "source %r: a diagnostic names the unit, a path and the error" % name)
    need(pkg == before, "source %r: validation changed its input" % name)
  for name, pkg, code in BAD_QUERY:
    v = la.validate_query(pkg, ENTS)
    codes = [d.get("code") for d in v["diagnostics"] if d["level"] == "invalid"]
    need(v["status"] == "invalid" and code in codes, "query %r: expected %s, got %s %s" % (name, code, v["status"], codes))
  for name, pkg, form in GOOD_SOURCE:
    v = la.validate_source_unit(pkg, ENTS)
    need(v["status"] == "supported" and v["form"] == form, "source %r: %s %s %r" % (name, v["status"], v["form"], v["diagnostics"]))
  for name, pkg, view in GOOD_QUERY:
    v = la.validate_query(pkg, ENTS)
    need(v["status"] == "supported" and ar.VIEWS[v["kind"]] == view, "query %r: %s %r" % (name, v["status"], v["diagnostics"]))
  print("  malformed: %d source and %d query packages rejected by the named rule; %d and %d valid forms accepted"
        % (len(BAD_SOURCE), len(BAD_QUERY), len(GOOD_SOURCE), len(GOOD_QUERY)))


def small_source(extra=None, stage1=None):
  pkgs = [S(["and", ["isa", "person", "Ann 1"], ["is rel2", "located_at", "Ann 1", "Haapsalu 3"]]),
          S(["connected", "Haapsalu 3", "Tallinn 4", "bus"], "S2")]
  return ar.compile_source(stage1, pkgs + (extra or []), la.PROFILE, "Ann is a person in Haapsalu. A bus runs to Tallinn.", ENTS)


def check_reasons(detected):
  for reason, kind, pkg in EXTRA_UNSUPPORTED:
    v = la.validate_query(pkg, ENTS) if kind == "query" else la.validate_source_unit(pkg, ENTS)
    got = sorted({d.get("reason") for d in v["diagnostics"]})
    need(v["status"] == "unsupported" and got == [reason], "%s example: %s %s" % (reason, v["status"], got))
    detected.add(reason)
  # through the public operations: the unit stays, and an attached query is unsupported
  n = 0
  for reason, kind, pkg in EXTRA_UNSUPPORTED:
    if kind != "source":
      continue
    pkg = copy.deepcopy(pkg)
    pkg[1] = "S3"
    if pkg[2][0] == "and" and pkg[2][-1][0] == "@p":
      pkg[2][-1][1] = "S3"
    c = small_source([pkg])
    need(c["units"][2]["stage2"] == pkg and c["units"][2]["status"] == "unsupported"
         and ar.source_outcome(c) == {"outcome": "unsupported_translation", "reasons": [reason], "units": ["S3"]},
         "%s through compile_source: %r" % (reason, ar.source_outcome(c)))
    q = ar.compile_query(Q(["plan", AT]), c)
    need(q["outcome"]["outcome"] == "unsupported_translation" and ar.solve_query(c, q)["outcome"] == "unsupported_translation",
         "%s: an attached query must be unsupported" % reason)
    n += 1
  structural = {r for r, owner in la.REASONS.items() if owner == "structural"}
  done = set(small_source()["passes"])
  need(structural <= detected, "structural reasons never detected: %s" % sorted(structural - detected))
  later = sorted(r for r, owner in la.REASONS.items() if owner != "structural" and owner not in done)
  base = small_source()
  need(base["support"]["status"] == "supported" and ar.source_outcome(base)["outcome"] == "source_compiled"
       and ar.source_outcome(with_pending(base))["outcome"] == ar.NOT_IMPLEMENTED,
       "a validated source with pending passes is not source_compiled")
  for reason in later:
    a = ar.add_diagnostic(base, "S2", reason, "recorded by a later pass", la.REASONS[reason])
    need(base["support"]["status"] == "supported", "add_diagnostic changed its input")
    need(a["hashes"]["source"] == base["hashes"]["source"] and a["hashes"]["artifact"] != base["hashes"]["artifact"],
         "%s: the source hash stays, the artifact hash changes" % reason)
    need([u["stage2"] for u in a["units"]] == [u["stage2"] for u in base["units"]], "%s: the unit was dropped or changed" % reason)
    o = ar.source_outcome(a)
    need(o["outcome"] == "unsupported_translation" and o["reasons"] == [reason] and o["units"] == ["S2"], "%s: %r" % (reason, o))
    q = ar.compile_query(Q(["plan", AT]), a)
    need(q["outcome"]["outcome"] == "unsupported_translation", "%s: a query must not solve a partly supported source" % reason)
  try:
    ar.add_diagnostic(base, "S2", "made_up_reason", "x", "x")
    raise Bad("an unknown reason was accepted")
  except ar.ArtifactError:
    pass
  # the A5.3 reason list is covered
  a53 = ["ambiguous_state_policy", "method_collision", "ambiguous_state_scope", "mixed_scope_rule",
         "unsupported_restriction_scope", "unsupported_capability_restriction", "unsupported_location_granularity",
         "unsupported_transport_dependency", "unexpressible_temporal_permission_scope"]
  need(set(a53) <= set(la.REASONS), "A5.3 reasons missing: %s" % sorted(set(a53) - set(la.REASONS)))
  import check_fixture_schema as schema
  need(schema.REASONS <= set(la.REASONS), "fixture reasons not registered: %s" % sorted(schema.REASONS - set(la.REASONS)))
  print("  reasons: %d structural reasons detected on examples; %d later-pass reasons recorded by name; each blocks a query"
        % (len(structural), len(later)))


def shuffled(x):
  """The same JSON value with every dictionary's key order reversed."""
  if isinstance(x, dict):
    return {k: shuffled(x[k]) for k in reversed(list(x))}
  if isinstance(x, list):
    return [shuffled(i) for i in x]
  return x


def check_artifacts():
  a = small_source()
  b = small_source()
  need(ar.dumps(a) == ar.dumps(b) and a["hashes"] == b["hashes"], "two compilations of one source differ")
  need(ar.source_hashes(shuffled(a)) == a["hashes"], "a hash depends on dictionary order")
  need(json.loads(ar.dumps(a)) == a, "an artifact does not survive serialization")
  need(a["artifact"] == ar.SOURCE and a["version"] == ar.ARTIFACT_VERSION, "container name and version")
  need(not a["pending_passes"] and ar.source_outcome(a)["outcome"] == "source_compiled"
       and ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED,
       "a source with pending passes must not count as compiled; a supported source without one is source_compiled")
  # source-only compilation needs no question; four different queries leave the hashes unchanged
  stored = ar.dumps(a)
  hashes = []
  for name, pkg, _ in GOOD_QUERY:
    q = ar.compile_query(pkg, a)
    need(ar.dumps(a) == stored, "query %r changed the source artifact" % name)
    need(q["source"]["source_hash"] == a["hashes"]["source"] and q["outcome"] is None, "query %r: %r" % (name, q["outcome"]))
    hashes.append(q["hash"])
  need(len(set(hashes)) == len(hashes), "distinct queries must have distinct hashes")
  # a query never extends the identity map
  q = ar.compile_query(Q(["plan", ["is rel2", "located_at", "Ann 1", "Tartu 77"]]), a)
  need(q["outcome"]["outcome"] == "translation_invalid" and "Tartu 77" not in a["identity"], "unknown entity in a query")
  # bounds and caps (A3.3)
  cases = [(Q(["plan", AT]), None, "s^4(0)", False), (Q(["plan", AT, ["steps", "exactly", 2]]), None, "s^2(0)", True),
           (Q(["plan", AT, ["steps", "at_most", 6]]), None, "s^6(0)", False),
           (Q(["plan", AT, ["steps", "at_most", 6]]), {"search_cap": 3}, "s^3(0)", False),
           (Q(["reachable", AT, ["steps", "exactly", 0]]), None, "0", True)]
  for pkg, lim, seed, zero in cases:
    q = ar.compile_query(pkg, a, lim)
    need(q["search"]["seed"] == seed and q["search"]["require_zero_remaining"] == zero, "seed for %r %r: %r" % (pkg, lim, q["search"]))
  q = ar.compile_query(Q(["plan", AT, ["steps", "at_most", 6]]), a, {"search_cap": 3})
  need(q["search"]["covers_bound"] is False and q["limits"]["explicit"] is True, "a search below the bound must be recorded")
  q = ar.compile_query(Q(["plan", AT, ["steps", "exactly", 5]]), a, {"search_cap": 4})
  need(q["outcome"]["outcome"] == "insufficient_search_allowance", "an exact bound above an explicit cap")
  q = ar.compile_query(Q(["verify", [TAKE, TAKE, TAKE, TAKE, TAKE], RED]), a)
  need(q["outcome"] is None, "the default cap does not truncate a supplied sequence")
  q = ar.compile_query(Q(["verify", [TAKE, TAKE], RED]), a, {"search_cap": 1})
  need(q["outcome"]["outcome"] == "insufficient_search_allowance", "an explicit allowance below a supplied sequence")
  # tamper and version checks
  t = copy.deepcopy(a)
  t["units"][0]["stage2"][2][2] = RED
  for broken in (t, dict(a, version="0"), {"artifact": "something"}):
    try:
      ar.compile_query(Q(["plan", AT]), broken)
      raise Bad("a changed or foreign artifact was accepted")
    except ar.ArtifactError:
      pass
  # Stage-1 and Stage-2 unit coverage, and the reading/form agreement
  s1 = [{"id": "S1", "text": "Ann is a person in Haapsalu.", "stage1": {"type": "situation"}},
        {"id": "S9", "text": "A sentence without logic.", "stage1": {"type": "situation"}}]
  c = small_source(stage1=s1)
  codes = sorted(d["code"] for d in c["diagnostics"])
  need(codes == ["unit_coverage", "unit_coverage"] and ar.source_outcome(c)["outcome"] == "translation_invalid", "coverage: %s" % codes)
  s1 = [{"id": "S1", "text": "x", "stage1": {"type": "situation"}}, {"id": "S2", "text": "x", "stage1": {"type": "situation"}},
        {"id": "S3", "text": "Ann can go.", "stage1": {"type": "situation", "action_reading": "effect",
                                                        "actions": [{"root": "go", "mode": "capability", "roles": {}}]}}]
  c = small_source([S(["can", "Ann 1", MOVE], "S3")], s1)
  need([d["code"] for u in c["units"] for d in u["diagnostics"]] == ["reading_form_mismatch"], "reading/form agreement")
  # no lexical normalization
  pk = S(["can", "Ann 1", ["move", "Ann 1", "Haapsalu 3", "Tallinn 4", "fly"]], "S3")
  c = small_source([pk])
  need(c["units"][2]["stage2"] == pk and "plane" not in ar.canonical(c), "a lexical value was normalized")
  print("  artifacts: deterministic hashes and serialization; %d queries leave the source unchanged; bounds, caps, tamper, coverage checked"
        % len(GOOD_QUERY))


def expect_error(fn, what):
  try:
    fn()
  except ar.ArtifactError:
    return
  except Exception as e:
    raise Bad("%s: %s instead of ArtifactError: %s" % (what, type(e).__name__, e))
  raise Bad("%s: accepted" % what)


def check_integrity():
  """Query integrity and the exact source revision (review R1)."""
  a = small_source()
  q = ar.compile_query(Q(["plan", AT]), a)
  need(ar.solve_query(a, copy.deepcopy(q), absent_backend())["outcome"] == "backend_unavailable",
       "an unchanged query artifact is accepted")
  edits = {"outcome without rehash": lambda x: x.update(outcome={"outcome": "plan_found"}),
           "goal without rehash": lambda x: x["query"].update(goal=RED),
           "hash": lambda x: x.update(hash="0" * 64),
           "limits without rehash": lambda x: x["limits"].update(search_cap=9)}
  for name, edit in edits.items():
    x = copy.deepcopy(q)
    edit(x)
    expect_error(lambda: ar.solve_query(a, x), "query with an edited %s" % name)
  for claim in ("plan_found", "goal_already_holds", "not_found", "verification_result", "source_compiled"):
    x = copy.deepcopy(q)
    x["outcome"] = {"outcome": claim}
    x["hash"] = ar.query_hash(x)
    expect_error(lambda: ar.solve_query(a, x), "a rehashed query artifact claiming %s" % claim)
  later = ar.add_diagnostic(a, "S2", "ambiguous_state_policy", "a later pass rejects the source", "effects_state_policy")
  expect_error(lambda: ar.solve_query(later, q), "an old query against a source with a new diagnostic")
  need(ar.solve_query(later, ar.compile_query(Q(["plan", AT]), later))["outcome"] == "unsupported_translation",
       "a query compiled again against the new revision is unsupported")
  passed = copy.deepcopy(a)
  passed["passes"].append("a_later_pass")
  passed["hashes"] = ar.source_hashes(passed)
  need(passed["hashes"]["source"] == a["hashes"]["source"], "a pass does not change the source content hash")
  expect_error(lambda: ar.solve_query(passed, q), "an old query against a source revision with another pass")
  expect_error(lambda: ar.solve_query(small_source([S(RED, "S3")]), q), "a query against other source content")
  for name, broken in (("a query without fields", {"artifact": ar.QUERY, "version": ar.ARTIFACT_VERSION}),
                       ("a query whose source is a string", dict(q, source="x")),
                       ("a list", [q]), ("a source without units", {k: v for k, v in a.items() if k != "units"})):
    expect_error(lambda: ar.solve_query(a, broken) if name != "a source without units" else ar.compile_query(Q(["plan", AT]), broken), name)
  for o in ar.QUERY_DECIDED:
    need(o in ar.OUTCOMES, "decided outcome %s" % o)
  print("  integrity: edited, rehashed-with-a-claim, stale-revision, foreign and malformed query artifacts raise ArtifactError")


def check_metadata():
  """Caller metadata is typed, never coerced (review R3)."""
  bad_profiles = [{"name": la.PROFILE, "policy": {"stored": "red"}}, {"name": la.PROFILE, "policy": ["stored"]},
                  {"name": la.PROFILE, "policy": {"stored": ["clean"], "computed": ["clean"]}},
                  {"name": la.PROFILE, "policy": {"stored": [3]}}, {"name": la.PROFILE, "policy": {"stored": ["red", "red"]}},
                  {"name": la.PROFILE, "locations": {"flat": "Tallinn 4"}}, {"name": la.PROFILE, "locations": ["flat"]},
                  {"name": la.PROFILE, "policy": None}, {"name": la.PROFILE, "colour": "red"}, ["physical_v1"]]
  for p in bad_profiles:
    expect_error(lambda: ar.normalize_profile(p), "profile %r" % (p,))
  ok = ar.normalize_profile({"name": la.PROFILE, "policy": {"stored": ["red"], "computed": ["ready"]}, "locations": {"flat": ["Tallinn 4", "Haapsalu 3"]}})
  need(ok["policy"] == {"stored": ["red"], "computed": ["ready"]} and ok["locations"]["flat"] == ["Haapsalu 3", "Tallinn 4"], "profile: %r" % ok)
  for lim in ({"search_cap": 1, "explicit": "false"}, {"search_cap": 1, "explicit": 0}, {"search_cap": True}, {"search_cap": "2"},
              {"search_cap": -1}, {"cap": 2}, [2]):
    expect_error(lambda: ar.normalize_limits(lim), "limits %r" % (lim,))
  need(ar.normalize_limits({"search_cap": 2, "explicit": False}) == {"search_cap": 2, "explicit": False}, "explicit false is kept")
  need(ar.normalize_limits({"search_cap": 2}) == {"search_cap": 2, "explicit": True}, "a given cap is explicit by default")
  a = small_source()
  q = ar.compile_query(Q(["plan", AT, ["steps", "at_most", 6]]), a, {"search_cap": 2, "explicit": False})
  need(q["search"]["seed"] == "s^6(0)", "a cap that is not explicit does not shorten a stated bound")
  # Stage-1 wrappers and projections
  can = S(["can", "Ann 1", MOVE], "S3")
  base = [{"id": "S1", "text": "x", "stage1": {"type": "situation"}}, {"id": "S2", "text": "x", "stage1": {"type": "situation"}}]
  act = {"type": "situation", "actions": [{"root": "go", "mode": "capability", "roles": {"actor": "Ann 1"}}], "action_reading": "availability"}
  for name, proj in (("null", None), ("a string", "situation"), ("actions as a string", dict(act, actions="go")),
                     ("an action without a root", dict(act, actions=[{"mode": "capability"}])),
                     ("roles as a list", dict(act, actions=[{"root": "go", "roles": ["Ann 1"]}])),
                     ("an unknown reading", dict(act, action_reading="permission")),
                     ("a reading that is a list", dict(act, action_reading=[])),
                     ("a reading that is an object", dict(act, action_reading={})),
                     ("a reading that is a number", dict(act, action_reading=1)),
                     ("entities without a type", dict(act, entities=[{"id": "Ann 1"}]))):
    c = small_source([can], base + [{"id": "S3", "text": "Ann can go.", "stage1": proj}])
    u = c["units"][2]
    need(u["status"] == "invalid" and [d["code"] for d in u["diagnostics"]] == ["stage1_projection"] and u["stage2"] == can,
         "a Stage-1 projection that is %s: %s %r" % (name, u["status"], u["diagnostics"]))
  c = small_source([can], base + [{"id": "S3", "text": "Ann can go.", "stage1": act}])
  need(c["support"]["status"] == "supported", "a minimal action projection is legal: %r" % c["support"])
  numbered = dict(act, entities=[{"id": "block 9", "type": "generic"}, {"id": "block 10", "type": "generic"}])
  c = small_source([can], base + [{"id": "S3", "text": "Ann can go.", "stage1": numbered}])
  need(c["support"]["status"] == "supported" and "block 9" not in c["identity"], "numbered generic mentions are legal and are not identities")
  need(small_source([can])["units"][2]["status"] == "supported", "a formal source (stage1=None) needs no projection")
  for name, s1 in (("a dictionary", {"S1": {}}), ("a list of strings", ["S1"]), ("a unit without id", [{"text": "x"}])):
    expect_error(lambda: small_source(stage1=s1), "stage1 that is %s" % name)
  expect_error(lambda: ar.compile_source(None, [S(RED)], la.PROFILE, entities=["a 6"]), "entities as a list")
  # a malformed event unit keeps its unit and gets a structural diagnostic; a bound one is unsupported
  c = small_source([S(["has actor", "E", "Ann 1"], "S3")])
  need(c["units"][2]["status"] == "invalid" and ar.source_outcome(c)["outcome"] == "translation_invalid", "free event variable through compile_source")
  c = small_source([S(EVENT_OK, "S3")])
  need(c["units"][2]["status"] == "unsupported" and ar.source_outcome(c)["reasons"] == ["occurrence"], "a bound event unit is an occurrence")
  c = small_source(stage1=base)
  need(c["support"]["status"] == "supported", "a projection without the optional reading is legal")
  print("  metadata: %d profiles, 7 limits, 10 Stage-1 projections and 4 wrapper forms rejected without coercion or a Python crash"
        % len(bad_profiles))


def check_collisions():
  """Method collision by overlap of action terms (review R4)."""
  def unit(i, form, root, term):
    return {"id": i, "form": form, "roots": [root], "action_terms": [term]}
  ground = ["change", "Ann 1", "egg 8", "cooked", "whisk 9"]
  cases = [
    ("a generic effect over a ground permission", unit("S1", "availability", "fry", ground),
     unit("S2", "effect", "boil", ["change", "X", "egg 8", "cooked", "whisk 9"]), True),
    ("renamed variables", unit("S1", "availability", "fry", ["change", "A", "B", "cooked", "T"]),
     unit("S2", "restriction", "boil", ["change", "X", "Y", "cooked", "Z"]), True),
    ("the same letter in two units is two variables", unit("S1", "availability", "fry", ["put_on", "hand 5", "X", "b 7"]),
     unit("S2", "effect", "drop", ["put_on", "hand 5", "a 6", "X"]), True),
    ("a repeated variable against two different constants", unit("S1", "availability", "stack", ["put_on", "hand 5", "a 6", "b 7"]),
     unit("S2", "effect", "balance", ["put_on", "hand 5", "X", "X"]), False),
    ("a repeated variable against one constant twice", unit("S1", "availability", "stack", ["put_on", "hand 5", "a 6", "a 6"]),
     unit("S2", "effect", "balance", ["put_on", "hand 5", "X", "X"]), True),
    ("different concrete tools", unit("S1", "availability", "fry", ground),
     unit("S2", "effect", "boil", ["change", "Ann 1", "egg 8", "cooked", "a 6"]), False),
    ("different values", unit("S1", "availability", "fry", ground),
     unit("S2", "effect", "boil", ["change", "X", "egg 8", "boiled", "whisk 9"]), False),
    ("two sufficient permissions and no law", unit("S1", "availability", "show a ticket", MOVE),
     unit("S2", "availability", "show a pass", MOVE), False),
    ("one verb on both units", unit("S1", "availability", "fry", ground),
     unit("S2", "effect", "fry", ["change", "X", "egg 8", "cooked", "whisk 9"]), False),
  ]
  for name, u1, u2, collide in cases:
    hit = la.method_collisions([u1, u2])
    need(bool(hit) == collide, "%s: %r" % (name, hit))
    if collide:
      need(set(hit) == {"S1", "S2"} and hit["S1"][0]["with"] == "S2" and hit["S1"][0]["term"] == u1["action_terms"][0]
           and hit["S1"][0]["other_term"] == u2["action_terms"][0], "%s: provenance %r" % (name, hit))
  # through compile_source: both units stay, both are diagnosed, each names the other
  s1 = [{"id": "S1", "text": "x", "stage1": {"type": "situation"}}, {"id": "S2", "text": "x", "stage1": {"type": "situation"}},
        {"id": "S3", "text": "Ann can fry the egg.", "stage1": {"type": "situation", "action_reading": "availability",
                                                               "actions": [{"root": "fry", "mode": "capability", "roles": {}}]}},
        {"id": "S4", "text": "After anyone boils the egg, it is wet.", "stage1": {"type": "strict_rule", "action_reading": "effect",
                                                                                  "actions": [{"root": "boil", "mode": "event", "roles": {}}]}}]
  c = small_source([S(["can", "Ann 1", ground], "S3"),
                    S(["forall", "X", ["after", ["change", "X", "egg 8", "cooked", "whisk 9"], ["has property", "wet", "egg 8"]]], "S4")], s1)
  d = {u["id"]: [(x["reason"], x["with"]) for x in u["diagnostics"]] for u in c["units"] if u["diagnostics"]}
  need(d == {"S3": [("method_collision", "S4")], "S4": [("method_collision", "S3")]}, "collision through compile_source: %r" % d)
  print("  collisions: %d term pairs; overlap by unification with variables standardized apart; permissions alone do not collide"
        % len(cases))


def check_operations():
  # a bundle whose files are missing; the default bundle would call a model
  r = ar.translate_source("Ann is in Haapsalu.", la.PROFILE, {"bundle": "actions-v1"})
  need(r["outcome"] == ar.NOT_IMPLEMENTED and r["calls"] == {"model": 0, "gk": 0}, "translate_source: %r" % r)
  a = small_source()
  q = ar.compile_query(Q(["plan", AT]), a)
  r = ar.solve_query(a, q, absent_backend())
  need(r["outcome"] == "backend_unavailable" and r["calls"]["gk"] == 0 and r["answer"] is None and r["plan"] is None,
       "solve_query must not fabricate: %r" % r)
  bad = ar.compile_query(Q(["plan", AT, ["steps", "exactly", 9]]), a, {"search_cap": 2})
  need(ar.solve_query(a, bad)["outcome"] == "insufficient_search_allowance", "a decided query outcome needs no prover")
  other = small_source([S(RED, "S3")])
  try:
    ar.solve_query(other, q)
    raise Bad("a query artifact was run against another source")
  except ar.ArtifactError:
    pass
  try:
    ar.result("plan_probably_found")
    raise Bad("an unknown outcome was accepted")
  except ar.ArtifactError:
    pass
  # the ordinary profile rejects the action syntax; the action profile accepts the same packages
  for name, pkg, _ in GOOD_SOURCE:
    if la.contains(pkg, set(la.ACTION_OPERATORS) | {"connected"}):
      v = la.validate_source_unit(pkg, ENTS, la.ORDINARY)
      need([d["code"] for d in v["diagnostics"]][:1] == ["action_syntax_in_ordinary_profile"], "ordinary profile accepted %r" % name)
  for name, pkg, _ in GOOD_QUERY:
    if pkg[2][0] in ("plan", "reachable", "verify"):
      v = la.validate_query(pkg, ENTS, la.ORDINARY)
      need([d["code"] for d in v["diagnostics"]] == ["action_syntax_in_ordinary_profile"], "ordinary profile accepted %r" % name)
  v = la.validate_source_unit(S(["isa", "animal", "Ann 1"]), ENTS, la.ORDINARY)
  need(v["status"] == "supported", "the ordinary profile keeps its ordinary packages")
  try:
    ar.compile_source(None, [S(RED)], "physical_v2")
    raise Bad("an unknown profile was accepted")
  except ar.ArtifactError:
    pass
  print("  operations: translate_source reports not_implemented; solve_query without its binary stops before any "
        "launch and fabricates nothing; the ordinary profile rejects the action syntax")


def check_worlds():
  W1 = ["@id", "S2", ["holds", "W1", RED]]
  # holds(W, F) for every declared world; an undeclared world is invalid at the world's path
  v = la.validate_source_unit(W1, ENTS, la.PROFILE, ["W0", "W1"])
  need(v["status"] == "supported" and v["world"] == "W1", "a declared world: %r" % v["diagnostics"])
  v = la.validate_source_unit(W1, ENTS)
  need([(d["code"], d["path"]) for d in v["diagnostics"]] == [("undeclared_world", "/2/1")], "undeclared: %r" % v["diagnostics"])
  v = la.validate_source_unit(["@id", "S2", ["and", ["holds", "W1", RED], ["@p", "S2", 0.8]]], ENTS)
  need([(d["code"], d["path"]) for d in v["diagnostics"]] == [("undeclared_world", "/2/1/1")], "undeclared under @p: %r" % v["diagnostics"])
  for bad in (["W0", "W0"], [], "W0", ["W0", "w1"], ["S1"]):
    expect_error(lambda: ar.compile_source(None, [S(RED)], la.PROFILE, entities=ENTS, worlds=bad), "worlds %r" % (bad,))
  a = ar.compile_source(None, [S(RED), W1], la.PROFILE, entities=ENTS, worlds=["W0", "W1"])
  need(a["worlds"] == ["W0", "W1"] and [u["world"] for u in a["units"]] == ["W0", "W1"], "worlds in the artifact")
  # context records: types checked by the caller interface, meaning by unit diagnostics
  for bad in ({"S1": {"tense": "later"}}, {"S1": {"location_role": "venue", "location": "Tallinn 4"}}, {"S1": {"mood": "x"}},
              {"S1": {"knower": 7}}, ["S1"]):
    expect_error(lambda: ar.compile_source(None, [S(RED)], la.PROFILE, entities=ENTS, contexts=bad), "contexts %r" % (bad,))
  cases = [({"location": "Tartu 99", "location_role": "scope"}, "invalid", "undeclared_context_location", "/context/location"),
           ({"knower": "Eve 99"}, "invalid", "undeclared_context_knower", "/context/knower"),
           ({"location": "Tallinn 4"}, "unsupported", "unsupported_contextual_location", "/context/location_role")]
  for rec, level, code, path in cases:
    a = ar.compile_source(None, [S(RED)], la.PROFILE, entities=ENTS, contexts={"S1": rec})
    d = a["units"][0]["diagnostics"]
    need([(x["level"], x.get("code") or x.get("reason"), x["path"]) for x in d] == [(level, code, path)] and a["units"][0]["status"] == level,
         "%s: %r" % (code, d))
  a = ar.compile_source(None, [S(["state_law", RED])], la.PROFILE, entities=ENTS, contexts={"S1": {"knower": "Ann 1"}})
  need([x["code"] for x in a["units"][0]["diagnostics"]] == ["context_record_position"], "a context on a standing law: %r" % a["units"][0]["diagnostics"])
  a = ar.compile_source(None, [S(RED)], la.PROFILE, entities=ENTS, contexts={"S9": {"tense": "past"}})
  need([x["code"] for x in a["diagnostics"]] == ["context_unit"] and a["support"]["status"] == "invalid", "a record for no unit: %r" % a["diagnostics"])
  a = ar.compile_source(None, [S(RED)], la.PROFILE, entities=ENTS, contexts={"S1": {"location": "Tallinn 4", "location_role": "provenance"}})
  need(a["units"][0]["provenance_location"] == "Tallinn 4" and a["units"][0]["context"]["location_role"] == "provenance"
       and a["support"]["status"] == "supported", "the provenance location is kept in the unit record")
  # the query's selection fields
  a = ar.compile_source(None, [S(RED), W1], la.PROFILE, entities=ENTS, worlds=["W0", "W1"])
  q = ar.compile_query(Q(["question", RED]), a)
  need(q["planning_root"] == "W1" and q["ambient"] is None and q["knower"] is None and q["excluded"] == [], "the default root: %r" % q["planning_root"])
  q = ar.compile_query(Q(["question", RED]), a, planning_root="W0", ambient="Tallinn 4", knower="Ann 1")
  need((q["planning_root"], q["ambient"], q["knower"]) == ("W0", "Tallinn 4", "Ann 1") and q["outcome"] is None, "an explicit selection")
  for kw, code in (({"planning_root": "W2"}, "unknown_planning_root"), ({"ambient": "Tartu 99"}, "unknown_ambient"),
                   ({"knower": "Eve 99"}, "unknown_knower")):
    q = ar.compile_query(Q(["question", RED]), a, **kw)
    need(q["outcome"] == {"outcome": "translation_invalid", "errors": [code]} and q["obligations"] is None, "%s: %r" % (code, q["outcome"]))
  need(ar.query_hash(ar.compile_query(Q(["question", RED]), a, planning_root="W0"))
       != ar.query_hash(ar.compile_query(Q(["question", RED]), a, planning_root="W1")), "the root is part of the query hash")
  print("  worlds: declared worlds, undeclared_world at its path; context records with their diagnostics and the kept provenance "
        "location; the default root is the last declared world; unknown_planning_root, unknown_ambient and unknown_knower")


def run():
  detected = check_gold()
  check_malformed()
  check_reasons(detected)
  check_artifacts()
  check_integrity()
  check_metadata()
  check_collisions()
  check_operations()
  check_worlds()


if __name__ == "__main__":
  run()
