[
// =====================================================================
// axioms_action.js -- the maintained action library of the opt-in action
// route (profile physical_v1).  Version 2.0.1 (encoding v2: one executability
// predicate, per-literal contexts, the situation in the world slot of the
// context term).  2.0.1 has the clauses of 2.0.0; only comments changed.
// Read by solver/lc_action_library.py, which checks this file's hash and
// the role of every clause against axioms_action.roles.json, and the
// applicability templates in axioms_action.templates.json (compiler data,
// never a GK input).
//
// PROVENANCE.  Derived on 2026-09-20 from the signed experimental library
//   elogs/action_axioms_2026_09_05/axioms_action.js
//   sha256 0b08ced1bea08bb1b2a48b6c6c3c52a5557260616f62ce547c3cd90192b4f4da
// which stays unchanged.  Differences, listed in tests/action_route/LIBRARY.md:
//   1. every positive poss law requires the restriction hook of its
//      constructor, ["ok_<constructor>", ACTION, C];
//   2. the default hook clauses: with no source restriction on a
//      constructor its hook holds for every action; the compiler leaves a
//      default hook out when the source restricts that constructor and
//      emits the conjunction of the restriction checks instead;
//   3. (1.1.0-1.2.0 capability necessities; removed in 1.3-dev);
//   4. placement uses the precondition ["-differ", X, Y] in place of the
//      positive literal ["=", X, Y];
//   5. the static helper facts have names;
//   6. (1.1.0-1.2.0 private movement path; removed in 1.3-dev);
//   7. (1.2.0 operational availability; removed in 1.3-dev);
//   8. executability (encoding v2, from 1.3-dev): one public planning predicate,
//      poss.  The library's own permissions are four executability defaults,
//      each the applicability template of its path with the default's class
//      conditions, concluding "normally poss" and blocked by the marker
//      ["execution_denied", ACTION, C] of an explicit source denial.  A
//      source availability compiles to one poss path per template of its
//      constructor; the templates live in axioms_action.templates.json.  One
//      consequence clause gives -poss from the marker.  No runtime can,
//      action_available, capability link, poss -> can necessity or private
//      route exists.  The archived 1.2.0 file is
//      elogs/encoding_v2_migration_2026_09_23/lib_1.2.0/axioms_action.js;
//   9. layout (2.0.0, encoding v2): the situation stands in the world slot
//      of the one context term $ctxt(present, S, L, $obj) and in no other
//      argument; reachable(S, N) has no context term.  The archived
//      1.3-dev.1b file (the same clauses with the situation before the
//      context) is elogs/encoding_v2_migration_2026_09_23/lib_1.3-dev.1b/.
// The optional negative frames are not part of this file and have no
// maintained copy: the historical experimental file is
// elogs/action_axioms_2026_09_05/axioms_action_negframe.js.  Negative
// persistence is a backend capability that is not validated.
//
// NOTATION.  A fluent is an existing wrapped predicate whose last argument
// is the context term C = $ctxt(present, S, L, $obj).  The situation S
// stands in C's world slot and in no other argument: the clause's situation
// variable ?:S, or its successor ["$do", ACTION, ?:S] in an effect, a marker
// or a frame conclusion.  L is one location variable per distinct atom (?:Lh
// for a successor literal; a frame's premise, conclusion and blocker share
// ?:L; a default's blocker and the denial consequence repeat the context of
// the literal they follow); $obj is the objective knower (a
// knower-relative query replaces it):
//   ["is rel2", REL, X, Y, C]    REL: located_at | on | in | holding
//   ["has property", V, X, C]    V open; clear_top and empty reserved
//   ["have", A, X, C]
// Static, no C: ["isa", CLASS, X], ["connected", FROM, TO, MEANS],
// ["differ", X, Y] (per-text facts, both orders, from the entity ids).
// A fact of the text has its world name in the world slot (W0, W1, ...).
// Action terms, one arity each:
//   ["move", A, FROM, TO, MEANS]  ["take", H, X]  ["put_on", H, X, Y]
//   ["put_in", H, X, B]  ["change", A, X, V, TOOL]   ("unspecified" = no
//   tool named by the description; it is not a wildcard)
// Library-internal: ["poss", ACTION, C] executable; ["ok_move" | "ok_take"
// | "ok_put_on" | "ok_put_in" | "ok_change", ACTION, C] the restriction
// hooks; ["execution_denied", ACTION, C] the marker of an explicit denial;
// ["reachable", S, N] with a unary depth counter N (no context term);
// ["changed_rel2", REL, X, Y, C2], ["changed_property", V, X, C2],
// ["changed_have", A, X, C2], C2 with the successor in its world slot, mark
// the instances an action writes and block their persistence;
// ["standard_mode", M], ["surface", Y], ["derived_property", V].
// The fluents have the signatures of the ordinary encoding: an ordinary
// clause in the law pattern matches a fluent of this file directly.  The
// query's reviewed ordinary view (V1-core) and the situation and context
// scope decide which ordinary clauses meet this library; the action input
// does not load axioms_std.js.
// =====================================================================
// == P1. STATIC HELPERS ==
{"@name": "standard_mode_bus", "@logic": ["standard_mode", "bus"]},
{"@name": "standard_mode_train", "@logic": ["standard_mode", "train"]},
{"@name": "standard_mode_ship", "@logic": ["standard_mode", "ship"]},
{"@name": "standard_mode_ferry", "@logic": ["standard_mode", "ferry"]},
{"@name": "standard_mode_plane", "@logic": ["standard_mode", "plane"]},
{"@name": "standard_mode_taxi", "@logic": ["standard_mode", "taxi"]},
{"@name": "standard_mode_foot", "@logic": ["standard_mode", "foot"]},
// a surface takes any number of objects
{"@name": "surface_table", "@logic": [["-isa", "table", "?:Y"], ["surface", "?:Y"]]},
{"@name": "surface_floor", "@logic": [["-isa", "floor", "?:Y"], ["surface", "?:Y"]]},
{"@name": "surface_shelf", "@logic": [["-isa", "shelf", "?:Y"], ["surface", "?:Y"]]},
{"@name": "surface_counter", "@logic": [["-isa", "counter", "?:Y"], ["surface", "?:Y"]]},

// == P2. EXECUTABILITY DEFAULTS ==
// The library's own permissions: person movement by a standard means, a
// hand taking a block, a hand putting a held block on a block or on a
// surface.  Each is the applicability template of its path (the physical
// preconditions and the restriction hook) plus the default's class
// conditions.  Actor-specific and defeasible: an explicit denial
// (execution_denied) of the same action term wins.  A route alone licenses
// no mover.  put_in and change have no default: the text supplies their
// rules, which the compiler completes with the templates.
{"@name": "poss_move_person", "@logic": [
  ["-isa", "person", "?:A"], ["-standard_mode", "?:M"],
  ["-is rel2", "located_at", "?:A", "?:F", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-connected", "?:F", "?:T", "?:M"],
  ["-differ", "?:F", "?:T"],
  ["-ok_move", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["poss", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]],
  ["$block", 0, ["execution_denied", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]]]
]},
// the blocks fragment: one hand, one object held, one block directly on a
// block.  The taken object is typed; the support Y is whatever the text says
// X rests on (a typed support check costs the four-step search).
{"@name": "poss_take_hand", "@logic": [
  ["-isa", "hand", "?:H"], ["-isa", "block", "?:X"],
  ["-has property", "empty", "?:H", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-has property", "clear_top", "?:X", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["-is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", "?:S", "?:L3", "$obj"]],
  ["-ok_take", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L4", "$obj"]],
  ["poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L5", "$obj"]],
  ["$block", 0, ["execution_denied", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L5", "$obj"]]]
]},
{"@name": "poss_put_on_hand_block", "@logic": [
  ["-isa", "hand", "?:H"], ["-isa", "block", "?:X"],
  ["-is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-isa", "block", "?:Y"],
  ["-has property", "clear_top", "?:Y", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["-differ", "?:X", "?:Y"],
  ["-ok_put_on", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]],
  ["poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L4", "$obj"]],
  ["$block", 0, ["execution_denied", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L4", "$obj"]]]
]},
{"@name": "poss_put_on_hand_surface", "@logic": [
  ["-isa", "hand", "?:H"], ["-isa", "block", "?:X"],
  ["-is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-surface", "?:Y"],
  ["-differ", "?:X", "?:Y"],
  ["-ok_put_on", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]],
  ["$block", 0, ["execution_denied", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]]]
]},
// == P3. DEFAULT RESTRICTION HOOKS ==
// With no source restriction on a constructor, its hook holds for every
// action.  The compiler omits the default hook of a constructor the source
// restricts and emits ok_<constructor> from all its restriction checks.
{"@name": "ok_move_default", "@logic": ["ok_move", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]]},
{"@name": "ok_take_default", "@logic": ["ok_take", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]]},
{"@name": "ok_put_on_default", "@logic": ["ok_put_on", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]]},
{"@name": "ok_put_in_default", "@logic": ["ok_put_in", ["put_in", "?:H", "?:X", "?:B"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]]},
{"@name": "ok_change_default", "@logic": ["ok_change", ["change", "?:A", "?:X", "?:V", "?:T"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]]},
// == P3d. DENIAL CONSEQUENCE ==
// An explicit denial of the text compiles to execution_denied.  Nothing else
// derives it: a failed restriction gives -poss through its necessity clause
// and never the marker.  It blocks the defaults (P2) and the default source
// paths, and gives -poss.
{"@name": "denied_not_poss", "@logic": [
  ["-execution_denied", "?:ACT", ["$ctxt", "present", "?:S", "?:L", "$obj"]],
  ["-poss", "?:ACT", ["$ctxt", "present", "?:S", "?:L", "$obj"]]
]},
// == P4. EFFECTS ==
// Every effect needs poss(ACTION, C(S)) and concludes at C($do(ACTION, S)).
// Each deleted instance gets both a strict negative effect and a unit
// changed_* marker (keyed on the action term) that blocks its persistence.
// Effect and marker are one pair: add both or neither.

// -- move: A is at TO and no longer at FROM
{"@name": "eff_move_at", "@logic": [
  ["-poss", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "located_at", "?:A", "?:T", ["$ctxt", "present", ["$do", ["move", "?:A", "?:F", "?:T", "?:M"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_move_not_at", "@logic": [
  ["-poss", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-is rel2", "located_at", "?:A", "?:F", ["$ctxt", "present", ["$do", ["move", "?:A", "?:F", "?:T", "?:M"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "chg_move_from", "@logic":
  ["changed_rel2", "located_at", "?:A", "?:F", ["$ctxt", "present", ["$do", ["move", "?:A", "?:F", "?:T", "?:M"], "?:S"], "?:Lh", "$obj"]]},

// -- take: H holds and has X, H is not empty, X leaves its support Y,
//    a block support Y gets a clear top
{"@name": "eff_take_holding", "@logic": [
  ["-poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_take_have", "@logic": [
  ["-poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["have", "?:H", "?:X", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_take_not_empty", "@logic": [
  ["-poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-has property", "empty", "?:H", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_take_not_on", "@logic": [
  ["-poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["-is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_take_clear", "@logic": [
  ["-poss", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["-isa", "block", "?:Y"],
  ["has property", "clear_top", "?:Y", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "chg_take_empty", "@logic":
  ["changed_property", "empty", "?:H", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]},
// Y is free: after take(H, X) no on(X, _) persists (one support per object)
{"@name": "chg_take_on", "@logic":
  ["changed_rel2", "on", "?:X", "?:Y", ["$ctxt", "present", ["$do", ["take", "?:H", "?:X"], "?:S"], "?:Lh", "$obj"]]},

// -- put_on: X rests on Y, H no longer holds X, H is empty,
//    a block target Y loses its clear top
{"@name": "eff_put_on_on", "@logic": [
  ["-poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_put_on_not_holding", "@logic": [
  ["-poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_put_on_empty", "@logic": [
  ["-poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["has property", "empty", "?:H", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_put_on_not_clear", "@logic": [
  ["-poss", ["put_on", "?:H", "?:X", "?:Y"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-isa", "block", "?:Y"],
  ["-has property", "clear_top", "?:Y", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "chg_put_on_holding", "@logic":
  ["changed_rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]},
{"@name": "chg_put_on_clear", "@logic": [
  ["-isa", "block", "?:Y"],
  ["changed_property", "clear_top", "?:Y", ["$ctxt", "present", ["$do", ["put_on", "?:H", "?:X", "?:Y"], "?:S"], "?:Lh", "$obj"]]
]},

// -- put_in: X is in B, H no longer holds X, H is empty
{"@name": "eff_put_in_in", "@logic": [
  ["-poss", ["put_in", "?:H", "?:X", "?:B"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "in", "?:X", "?:B", ["$ctxt", "present", ["$do", ["put_in", "?:H", "?:X", "?:B"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_put_in_not_holding", "@logic": [
  ["-poss", ["put_in", "?:H", "?:X", "?:B"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", ["put_in", "?:H", "?:X", "?:B"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "eff_put_in_empty", "@logic": [
  ["-poss", ["put_in", "?:H", "?:X", "?:B"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["has property", "empty", "?:H", ["$ctxt", "present", ["$do", ["put_in", "?:H", "?:X", "?:B"], "?:S"], "?:Lh", "$obj"]]
]},
{"@name": "chg_put_in_holding", "@logic":
  ["changed_rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", ["put_in", "?:H", "?:X", "?:B"], "?:S"], "?:Lh", "$obj"]]},

// -- change: X has property V.  A text that states a removed property
//    ("the egg is no longer whole") adds the pair
//    poss(change(...)) -> -has property(whole, X, C(S')) and its marker.
{"@name": "eff_change", "@logic": [
  ["-poss", ["change", "?:A", "?:X", "?:V", "?:T"], ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["has property", "?:V", "?:X", ["$ctxt", "present", ["$do", ["change", "?:A", "?:X", "?:V", "?:T"], "?:S"], "?:Lh", "$obj"]]
]},

// == P5. PERSISTENCE ==
// A stored fluent normally keeps its value across an executable action,
// unless the action wrote that instance (changed_* marker in the successor).
// Same form and confidence as the frame block of axioms_std.js.  Only the
// four primitive relations, possession and stored properties persist; a
// description defined from other current facts gets no inertia (declare
// ["derived_property", V] for such a property value, and give a derived
// relation a name outside this list).
{"@name": "frame_located_at", "@confidence": 0.99, "@logic": [
  ["-is rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
{"@name": "frame_on", "@confidence": 0.99, "@logic": [
  ["-is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "on", "?:X", "?:Y", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_rel2", "on", "?:X", "?:Y", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
{"@name": "frame_in", "@confidence": 0.99, "@logic": [
  ["-is rel2", "in", "?:X", "?:B", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "in", "?:X", "?:B", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_rel2", "in", "?:X", "?:B", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
{"@name": "frame_holding", "@confidence": 0.99, "@logic": [
  ["-is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_rel2", "holding", "?:H", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
{"@name": "frame_have", "@confidence": 0.99, "@logic": [
  ["-have", "?:A1", "?:X", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["have", "?:A1", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_have", "?:A1", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
{"@name": "frame_property", "@confidence": 0.99, "@logic": [
  ["-has property", "?:V", "?:X", ["$ctxt", "present", "?:S", "?:L", "$obj"]], ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["has property", "?:V", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_property", "?:V", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]
]},
// a declared derived property value counts as written in every successor
{"@name": "derived_no_inertia", "@logic": [
  ["-derived_property", "?:V"],
  ["changed_property", "?:V", "?:X", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:Lh", "$obj"]]
]},
// Negative persistence (a stated "-F" also persists) is not in this file.
// The experimental axioms_action_negframe.js stays in elogs/; a query that
// needs it gets unsupported_backend_requirement until a backend is validated.

// == P6. SEARCH ==
// The query compiler supplies the seed ["reachable", WROOT, N], WROOT the
// query's planning root (a world name), with the unary depth N from the
// query's step bound or the search cap (three actions:
// ["s", ["s", ["s", "0"]]]).  A source text never states it.  The plan
// question is
//   exists S: reachable(S, N) & GOAL(C(S))
// written as the pipeline's definition clause plus ["$defq0", "?:Sit"].  The
// answer substitution for S is the plan, innermost action first, ending in
// WROOT; an already satisfied goal answers with WROOT.  The backend profile
// (A6.3 with weight_ctxt_world) names the strategy.
{"@name": "reach_step", "@logic": [
  ["-reachable", "?:S", ["s", "?:N"]],
  ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["reachable", ["$do", "?:A", "?:S"], "?:N"]
]}
]
