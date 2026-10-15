"""Mutation tests for the fixture toolchain. No model, no GK.

Each entry below is an input the toolchain must reject, with the layer that
rejects it named in the entry.  The thirteen probes of the 2026-09-10
independent review (`elogs/wp02_review_astra_2026_09_10/probe.py`) are the
first block; the materializer's own rules follow; the inputs the 2026-09-11 re-review
found accepted (`elogs/wp02_rereview_astra_2026_09_11/probe.py`) are the
last block; the positive controls at the end must pass.  Every entry names
a fragment of the message it must raise, so a rejection for another reason
does not count.  A check that stops rejecting one of these is a defect.
"""

import copy

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_fixture_schema as schema
import fixture_materialize as fm

P = ["has property", "red", "block 1"]
ENTS = {"block 1": "block", "Ann 1": "person", "Bob 2": "person", "City 3": "place", "City 4": "place"}


def unit(i="S1", **kw):
  u = {"id": i, "text": "Block one is red.",
       "stage1": {"type": "situation", "entities": [{"id": "block 1", "type": "concrete", "category": "artifact"}]},
       "stage2": ["@id", i, ["holds", "W0", P]], "scope": "initial",
       "syntax": "supported", "compile": "supported"}
  u.update(kw)
  return u


def query(i="Q1", **kw):
  q = {"id": i, "text": "Is block one red?", "stage2": ["@id", i, ["question", P]],
       "view": "snapshot", "expect": {"answer": "Yes", "evidence": "S1 at W0"},
       "backend": [], "replay": "n/a"}
  q.update(kw)
  return q


def record(**kw):
  d = {"id": "m", "purpose": "", "contract": [], "family": [], "input_kind": "text",
       "text": "Block one is red.", "profile": "physical_v1", "entities": ENTS,
       "units": [unit()], "queries": [query()], "variants": [], "candidates": [],
       "support": {}, "explain": "", "notes": ""}
  d.update(kw)
  return d


def full_check(d):
  """The schema check on every effective case of a record, as run() does."""
  cases = fm.materialize(d)
  by_case = {c["case"]: c for c in cases}
  for c in cases:
    schema.check_case(c, d["input_kind"], by_case)


ctx_ok = schema.Ctx(entities=ENTS)

BLUE = {"id": "S2", "text": "Block one is blue.",
        "stage1": {"type": "situation", "entities": [{"id": "block 1", "type": "concrete"}]},
        "stage2": ["@id", "S2", ["holds", "W0", ["has property", "blue", "block 1"]]],
        "scope": "initial", "syntax": "supported", "compile": "supported"}
POLISH = ["@id", "S1", ["holds", "W0", ["can", "Ann 1", ["change", "Ann 1", "block 1", "polished", "unspecified"]]]]
POLISH_ENTS = [{"id": "Ann 1", "type": "concrete"}, {"id": "block 1", "type": "concrete"}]
POLISH_ACTIONS = [{"root": "polish", "mode": "capability", "roles": {"actor": "Ann 1", "target": "block 1"}}]


def polish(stage1):
  return {"id": "S1", "text": "Ann can polish block one.", "stage1": stage1, "stage2": POLISH,
          "scope": "availability", "syntax": "supported", "compile": "supported"}


TAKE_NO_ACTIONS = polish({"type": "situation", "entities": POLISH_ENTS, "action_reading": "availability"})
TAKE_NO_READING = polish({"type": "situation", "entities": POLISH_ENTS, "actions": POLISH_ACTIONS})
TAKE_OK = polish({"type": "situation", "entities": POLISH_ENTS, "actions": POLISH_ACTIONS,
                  "action_reading": "availability"})

REJECT = [
  # --- the review's thirteen probes (schema layer) ---
  ("extra not operand", lambda: schema.check_formula(["not", P, P], set(), "m")),
  ("unary implication", lambda: schema.check_formula(["implies", P], set(), "m")),
  ("extra normally operand", lambda: schema.check_formula(["normally", P, P], set(), "m")),
  ("extra holds operand", lambda: schema.check_package(["@id", "S1", ["holds", "W0", P, P]], "m")),
  ("extra question operand", lambda: schema.check_query(["@id", "Q1", ["question", P, P]], "m")),
  ("negative bound", lambda: schema.check_query(["@id", "Q1", ["plan", P, ["steps", "at_most", -1]]], "m")),
  ("Boolean bound", lambda: schema.check_query(["@id", "Q1", ["plan", P, ["steps", "at_most", True]]], "m")),
  ("actor mismatch", lambda: schema.check_formula(["can", "Ann 1", ["move", "Bob 2", "City 3", "City 4", "bus"]], set(), "m")),
  ("unbound property variable", lambda: schema.check_formula(["has property", "V", "block 1"], set(), "m")),
  ("malformed ordinary event", lambda: schema.check_formula(["has actor"], set(), "m", schema.Ctx(supported=False))),
  ("Skolem term in Stage 2", lambda: schema.check_formula(["have", "Ann 1", ["sk", "X"]], set(), "m")),
  ("missing evidence", lambda: schema.check_queries([query(expect={"answer": "Yes"})], "m")),
  ("missing unit text and Stage 1", lambda: schema.check_units([{"id": "S1", "stage2": ["@id", "S1", ["holds", "W0", P]], "scope": "initial", "syntax": "supported", "compile": "supported"}], "m")),
  # --- more schema rejections ---
  ("event predicate in a supported unit", lambda: schema.check_formula(["has actor", "E", "Ann 1"], {"E"}, "m", ctx_ok)),
  ("unclassified relation in a supported unit", lambda: schema.check_formula(["is rel2", "next_to", "City 3", "City 4"], set(), "m", ctx_ok)),
  ("undeclared entity id", lambda: schema.check_formula(["isa", "person", "Zed 9"], set(), "m", ctx_ok)),
  ("unknown unsupported reason", lambda: schema.check_units([unit(compile={"unsupported": "made_up_reason"})], "m", entities=ENTS)),
  ("unknown outcome", lambda: schema.check_queries([query(expect={"outcome": "maybe", "evidence": "x"})], "m")),
  ("discovery query without seed", lambda: schema.check_queries([query(stage2=["@id", "Q1", ["plan", P]], view="discovery")], "m")),
  ("stage1 entity without concrete/generic", lambda: schema.check_units([unit(stage1={"type": "situation", "entities": [{"id": "block 1"}]})], "m", entities=ENTS)),
  ("confidence package with wrong id", lambda: schema.check_package(["@id", "S1", ["and", ["holds", "W0", P], ["@p", "S2", 0.8]]], "m")),
  ("nested after", lambda: schema.check_formula(["after", ["take", "Ann 1", "block 1"], ["after", ["take", "Ann 1", "block 1"], P]], set(), "m", ctx_ok)),
  ("witness constant in Stage 2", lambda: schema.check_formula(["can", "sk_A", ["change", "sk_A", "block 1", "red", "unspecified"]], set(), "m", ctx_ok)),
  # --- materializer rejections ---
  ("query-level units_add", lambda: fm.materialize(record(queries=[query(units_add=[unit("S2")])]))),
  ("dangling units_remove", lambda: fm.materialize(record(variants=[{"id": "v", "text": "Block one is red.", "units_remove": ["S9"], "queries": [query()]}]))),
  ("units_add repeats an id", lambda: fm.materialize(record(variants=[{"id": "v", "text": "Block one is red.", "units_add": [unit("S1")], "queries": [query()]}]))),
  ("units_replace of an unknown id", lambda: fm.materialize(record(variants=[{"id": "v", "text": "Block one is red.", "units_replace": [unit("S7")], "queries": [query()]}]))),
  ("override without expect", lambda: fm.materialize(record(variants=[{"id": "v", "queries": [{"id": "Q1", "view": "snapshot"}]}]))),
  ("queries_keep of an unknown id", lambda: fm.materialize(record(variants=[{"id": "v", "queries_keep": ["Q7"]}]))),
  ("candidate with extra_units", lambda: fm.materialize(record(candidates=[{"id": "K1", "sequence": [], "states": [], "verdict": "valid", "extra_units": ["S1"]}]))),
  ("candidate on an unknown variant", lambda: fm.materialize(record(candidates=[{"id": "K1", "variant": "nope", "sequence": [], "states": [], "verdict": "valid"}]))),
  ("unknown variant field", lambda: fm.materialize(record(variants=[{"id": "v", "units_drop": ["S1"]}]))),
  ("duplicate variant id", lambda: fm.materialize(record(variants=[{"id": "v", "queries": [query()]}, {"id": "v", "queries": [query()]}]))),
  ("partial units_replace reaches the schema check", lambda: full_check(record(variants=[{"id": "v", "text": "Block one is red.", "units_replace": [{"id": "S1", "compile": "supported"}], "queries": [query()]}]))),
  ("variant unit without text reaches the schema check", lambda: full_check(record(variants=[{"id": "v", "text": "Block one is red.", "units_add": [{"id": "S2", "stage1": {"type": "situation"}, "stage2": ["@id", "S2", ["holds", "W0", P]], "scope": "initial", "syntax": "supported", "compile": "supported"}], "queries": [query()]}]))),
  # --- the re-review's inputs (2026-09-11): effective text, Stage-1 content, query metadata ---
  ("unit edit without its own text", lambda: fm.materialize(record(variants=[{"id": "v", "units_add": [BLUE], "queries": [query()]}]))),
  ("patched sentence without its own text", lambda: fm.materialize(record(variants=[{"id": "v", "units_patch": [{"id": "S1", "text": "Block one is blue."}], "queries": [query()]}]))),
  ("unit sentence absent from the passage", lambda: full_check(record(variants=[{"id": "v", "text": "Block one is red.", "units_add": [BLUE], "queries": [query()]}]))),
  ("passage sentence without a unit", lambda: full_check(record(text="Block one is red. Block one is heavy."))),
  ("question inside the passage", lambda: full_check(record(text="Block one is red. Is block one red?"))),
  ("editorial note inside the passage", lambda: full_check(record(text="Block one is red. [the effect part]"))),
  ("null Stage 1", lambda: full_check(record(units=[unit(stage1=None)]))),
  ("Stage 1 without the consumed entity", lambda: full_check(record(units=[unit(stage1={"type": "situation"})]))),
  ("action unit without actions", lambda: full_check(record(text="Ann can polish block one.", units=[TAKE_NO_ACTIONS]))),
  ("action unit without action_reading", lambda: full_check(record(text="Ann can polish block one.", units=[TAKE_NO_READING]))),
  ("invented role in a Stage-1 action", lambda: full_check(record(text="Ann can polish block one.", units=[polish({"type": "situation", "entities": POLISH_ENTS, "actions": [{"root": "polish", "mode": "capability", "roles": {"actor": "Ann 1", "polarity": "negative"}}], "action_reading": "availability"})]))),
  ("two roles on one generic mention", lambda: full_check(record(text="Ann can polish block one.", units=[polish({"type": "situation", "entities": POLISH_ENTS + [{"id": "block", "type": "generic"}], "actions": [{"root": "polish", "mode": "capability", "roles": {"target": "block", "destination": "block"}}], "action_reading": "availability"})]))),
  ("question package in the discovery view", lambda: full_check(record(queries=[query(view="discovery", seed="s^4(0)")]))),
  ("plan package in the snapshot view", lambda: full_check(record(queries=[query(stage2=["@id", "Q1", ["plan", P]])]))),
  ("seed on a snapshot question", lambda: full_check(record(queries=[query(seed="s^4(0)")]))),
  ("invalid seed", lambda: full_check(record(queries=[query(stage2=["@id", "Q1", ["plan", P]], view="discovery", seed="garbage")]))),
  ("seed above the bound", lambda: full_check(record(queries=[query(stage2=["@id", "Q1", ["plan", P, ["steps", "at_most", 2]]], view="discovery", seed="s^4(0)")]))),
  ("seed above the search cap", lambda: full_check(record(queries=[query(stage2=["@id", "Q1", ["plan", P]], view="discovery", seed="s^4(0)", limits={"search_cap": 2, "explicit": True})]))),
  ("expectation forbids its own answer", lambda: full_check(record(queries=[query(expect={"answer": "Yes", "forbidden_answers": ["Yes"], "evidence": "x"})]))),
  ("expectation forbids its own outcome", lambda: full_check(record(queries=[query(expect={"outcome": "not_found", "forbidden_outcomes": ["not_found"], "evidence": "x"})]))),
  ("replay context without a query", lambda: full_check(record(queries=[query(replay_context={"case": "c20_verify", "variant": "a_red"})]))),
  ("replay context on an unknown case", lambda: full_check(record(queries=[query(replay_context={"case": "does_not_exist", "variant": "missing", "query": "Q1"})]))),
  ("replay context on an unknown query", lambda: full_check(record(queries=[query(replay_context={"case": "c20_verify", "variant": "a_red", "query": "Q99"})]))),
  ("replay context on a query without a goal", lambda: full_check(record(queries=[query(replay_context={"case": "m", "variant": "base", "query": "Q1"})]))),
  ("unknown query field", lambda: fm.materialize(record(queries=[query(backend_notes="typo")]))),
  ("unknown query field in an override", lambda: fm.materialize(record(variants=[{"id": "v", "queries": [{"id": "Q1", "expect": {"answer": "Yes", "evidence": "x"}, "replay_ctx": {}}]}]))),
  ("clause expectation on an unsupported unit", lambda: full_check(record(units=[unit(compile={"unsupported": "occurrence"}, clauses={"must_have": [{"role": "initial_fact", "lit": P}]})]))),
  ("inspection without a known operation", lambda: full_check(record(units=[unit(inspection={"operation": "look", "must_have": []})]))),
  # --- encoding v2, step 1: can is source-only; the new pattern keys ---
  ("can in a question", lambda: schema.check_query(["@id", "Q1", ["question", ["can", "Ann 1", ["move", "Ann 1", "City 3", "City 4", "bus"]]]], "m", ctx_ok)),
  ("can in a verify goal", lambda: schema.check_query(["@id", "Q1", ["verify", [], ["can", "Ann 1", ["move", "Ann 1", "City 3", "City 4", "bus"]]]], "m", ctx_ok)),
  ("body_absent with a fluent", lambda: full_check(record(units=[unit(clauses={"must_not_have": [{"role": "availability", "body_absent": ["is rel2"]}]})]))),
  ("pattern confidence above one", lambda: full_check(record(units=[unit(clauses={"must_have": [{"role": "initial_fact", "lit": P, "confidence": 1.5}]})]))),
  # --- encoding v2, step 1b: worlds, context records, query selection (migration plan section 9) ---
  ("location_role outside the two values", lambda: full_check(record(units=[unit(context={"location": "City 3", "location_role": "venue"})]))),
  ("planning_root naming no declared world", lambda: full_check(record(worlds=["W0", "W1"], queries=[query(planning_root="W2")]))),
  ("holds world naming no declared world", lambda: full_check(record(units=[unit(stage2=["@id", "S1", ["holds", "W1", P]])]))),
  ("ambient naming no location", lambda: full_check(record(queries=[query(ambient="Attic 9")]))),
  ("worlds with a repeated name", lambda: full_check(record(worlds=["W0", "W1", "W0"]))),
  ("knower naming no entity", lambda: full_check(record(queries=[query(knower="Eve 9")]))),
  ("a world name as a quantified variable", lambda: schema.check_formula(["forall", "W0", ["has property", "red", "W0"]], set(), "m", ctx_ok)),
  ("a world name as the asked variable", lambda: schema.check_query(["@id", "Q1", ["ask", "W1", ["has property", "red", "W1"]]], "m", ctx_ok)),
]


# The message fragment each rejection must contain.
EXPECT = {'extra not operand': 'not takes one operand',
 'unary implication': 'implies takes two',
 'extra normally operand': 'normally takes one',
 'extra holds operand': 'must be holds(W, F)',
 'extra question operand': 'question takes one formula',
 'negative bound': 'bad steps item',
 'Boolean bound': 'bad steps item',
 'actor mismatch': "differs from the action's actor",
 'unbound property variable': 'must be a lexical constant',
 'malformed ordinary event': 'has actor arity',
 'Skolem term in Stage 2': 'Skolem terms do not occur',
 'missing evidence': 'expect needs evidence',
 'missing unit text and Stage 1': 'missing text',
 'event predicate in a supported unit': 'unknown predicate has actor',
 'unclassified relation in a supported unit': 'unclassified relation next_to',
 'undeclared entity id': 'undeclared entity id',
 'unknown unsupported reason': '<known reason>',
 'unknown outcome': "outcome 'maybe'",
 'discovery query without seed': 'needs a seed',
 'stage1 entity without concrete/generic': 'needs type concrete|generic',
 'confidence package with wrong id': 'a confidence package is',
 'nested after': 'nested after',
 'witness constant in Stage 2': 'witness constant sk_A',
 'query-level units_add': 'may not change the source',
 'dangling units_remove': 'units_remove names unknown unit',
 'units_add repeats an id': 'units_add repeats unit id',
 'units_replace of an unknown id': 'units_replace names unknown unit',
 'override without expect': 'must give its whole expect',
 'queries_keep of an unknown id': 'queries_keep names unknown query',
 'candidate with extra_units': 'extra_units is not allowed',
 'candidate on an unknown variant': 'candidate references unknown case',
 'unknown variant field': 'unknown variant fields',
 'duplicate variant id': 'duplicate variant id',
 'partial units_replace reaches the schema check': 'missing stage2',
 'variant unit without text reaches the schema check': 'missing text',
 'unit edit without its own text': 'must give its own text',
 'patched sentence without its own text': 'must give its own text',
 'unit sentence absent from the passage': 'is not in the passage',
 'passage sentence without a unit': 'belongs to no unit',
 'question inside the passage': 'the passage is source-only',
 'editorial note inside the passage': 'editorial note',
 'null Stage 1': 'missing stage1 projection',
 'Stage 1 without the consumed entity': 'lacks the concrete entities',
 'action unit without actions': 'needs its stage1 actions',
 'action unit without action_reading': 'needs action_reading',
 'invented role in a Stage-1 action': 'is not a Stage-1 semantic role',
 'two roles on one generic mention': 'number the mentions',
 'question package in the discovery view': 'does not run in the discovery view',
 'plan package in the snapshot view': 'does not run in the snapshot view',
 'seed on a snapshot question': 'only a discovery query has a seed',
 'invalid seed': "seed 'garbage'",
 'seed above the bound': "give 's^2(0)'",
 'seed above the search cap': "give 's^2(0)'",
 'expectation forbids its own answer': 'forbids its own answer',
 'expectation forbids its own outcome': 'forbids its own outcome',
 'replay context without a query': 'replay_context is {case, variant, query}',
 'replay context on an unknown case': 'names unknown case',
 'replay context on an unknown query': 'names unknown query',
 'replay context on a query without a goal': 'has no final goal',
 'unknown query field': 'unknown query fields',
 'unknown query field in an override': 'unknown query fields',
 'clause expectation on an unsupported unit': 'compiles to no clauses',
 'inspection without a known operation': 'needs a known operation',
 'can in a question': 'can is a source-only form',
 'can in a verify goal': 'can is a source-only form',
 'body_absent with a fluent': 'body_absent is a list of static predicate names',
 'pattern confidence above one': 'a pattern confidence is a number',
 'location_role outside the two values': 'is not one of',
 'planning_root naming no declared world': 'planning_root',
 'holds world naming no declared world': 'names no declared world',
 'ambient naming no location': 'ambient',
 'worlds with a repeated name': 'worlds repeats a name',
 'knower naming no entity': 'knower',
 'a world name as a quantified variable': 'reserved_variable',
 'a world name as the asked variable': 'reserved_variable'}


def positive_controls():
  # A declared second world, a fact of it, a context record and the selection fields are accepted.
  full_check(record(worlds=["W0", "W1"],
                    units=[unit(), unit("S2", text="Block one is blue.", stage2=["@id", "S2", ["holds", "W1", ["has property", "blue", "block 1"]]],
                                        context={"location": "City 3", "location_role": "scope", "knower": "Ann 1"})],
                    text="Block one is red. Block one is blue.",
                    queries=[query(planning_root="W1", ambient="City 3", knower="Ann 1")]))
  # An override replaces the whole expect: the base outcome must not survive.
  d = record(queries=[query(expect={"outcome": "unsupported_translation", "reason": "occurrence", "evidence": "base"})],
             variants=[{"id": "v", "queries": [{"id": "Q1", "expect": {"answer": "Yes", "evidence": "variant"}}]}])
  cases = fm.materialize(d)
  v = [c for c in cases if c["variant"] == "v"][0]
  e = v["queries"][0]["expect"]
  if "outcome" in e or e.get("answer") != "Yes":
    raise schema.Bad("override did not replace expect as a whole: %r" % e)
  if v["queries"][0]["stage2"] != d["queries"][0]["stage2"]:
    raise schema.Bad("override lost the inherited stage2")
  full_check(d)
  # A zero bound is legal.
  schema.check_query(["@id", "Q1", ["reachable", P, ["steps", "exactly", 0]]], "m")
  # queries_keep copies the base query unchanged and a new query is complete.
  d = record(variants=[{"id": "v", "text": "Block one is red. Block one is blue.",
                        "units_add": [unit("S2", text="Block one is blue.", stage2=["@id", "S2", ["holds", "W0", ["has property", "blue", "block 1"]]])],
                        "queries_keep": ["Q1"], "queries": [query("Q2", stage2=["@id", "Q2", ["question", ["has property", "blue", "block 1"]]])]}])
  full_check(d)
  v = fm.materialize(d)[1]
  if [q["id"] for q in v["queries"]] != ["Q1", "Q2"]:
    raise schema.Bad("queries_keep order")
  # A minimal Stage-1 projection is legal: no category, no optional field.
  full_check(record(units=[unit(stage1={"type": "situation", "entities": [{"id": "block 1", "type": "concrete"}]})]))
  # A complete minimal action unit is legal.
  full_check(record(text="Ann can polish block one.", units=[TAKE_OK]))
  # A formal-only record needs no sentence and no Stage-1 projection.
  full_check(record(input_kind="formal_only", text="(formal-only)",
                    units=[{"id": "S1", "text": "(formal) block one is red", "stage2": ["@id", "S1", ["holds", "W0", P]],
                            "scope": "initial", "syntax": "supported", "compile": "supported"}]))
  # An unsupported unit may hold an inspection target with a named operation.
  full_check(record(units=[unit(compile={"unsupported": "occurrence"},
                                inspection={"operation": "situation_insertion_skolemization",
                                            "must_have": [{"role": "initial_fact", "lit": P}]})]))
  # An override keeps the documented query fields, its own or the base's.
  base = query(stage2=["@id", "Q1", ["plan", P]], view="discovery", seed="s^4(0)", backend_note="base note",
               replay_context={"case": "m", "variant": "base", "query": "Q1"})
  d = record(queries=[base], variants=[
    {"id": "v", "queries": [{"id": "Q1", "expect": {"answer": "Yes", "evidence": "x"}, "backend_note": "variant note"}]}])
  q = fm.materialize(d)[1]["queries"][0]
  if q.get("backend_note") != "variant note" or q.get("replay_context") != base["replay_context"]:
    raise schema.Bad("override lost a documented query field: %r" % q)
  full_check(d)
  # An effective case names its input kind and holds its candidates.
  d = record(candidates=[{"id": "K1", "sequence": [], "states": [], "verdict": "valid", "reason": "x"}])
  c = fm.materialize(d)[0]
  if c.get("input_kind") != "text" or [k["id"] for k in c["candidates"]] != ["K1"]:
    raise schema.Bad("effective case lacks input_kind or candidates")
  # A stated bound above four seeds that bound when no cap was imposed (A3.3).
  full_check(record(queries=[query(stage2=["@id", "Q1", ["plan", P, ["steps", "at_most", 6]]], view="discovery", seed="s^6(0)")]))
  # The no-search diagnostic: an exact bound above the cap has seed `none`.
  full_check(record(queries=[query(stage2=["@id", "Q1", ["reachable", P, ["steps", "exactly", 2]]], view="discovery",
                                   seed="none", limits={"search_cap": 1, "explicit": True})]))


def run():
  failures = []
  if set(EXPECT) != {name for name, _ in REJECT} or len(EXPECT) != len(REJECT):
    raise schema.Bad("REJECT and EXPECT name different entries")
  for name, fn in REJECT:
    try:
      fn()
    except (schema.Bad, fm.Bad) as e:
      if EXPECT[name] not in str(e):
        failures.append("%s (rejected for another reason: %s)" % (name, e))
      continue
    failures.append(name)
  if failures:
    raise schema.Bad("accepted invalid input: %s" % "; ".join(failures))
  positive_controls()
  print("  %d rejections verified; positive controls pass" % len(REJECT))


if __name__ == "__main__":
  run()
