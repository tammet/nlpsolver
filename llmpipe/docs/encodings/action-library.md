# Action library

The action library holds the physical laws of the action route: the defaults
that permit an action, the effects of the five constructors, the frame
clauses that keep a fact across an action, and the search step. The laws do not
depend on the text. The compiler adds the clauses of the text
([action clauses](action-clauses.md)). The route is experimental, and the
ordinary pipeline does not read this library.

## Files

| file | content | read by |
|---|---|---|
| `axioms_action.js` | the 50 library clauses, version 2.0.1 | GK, through the query views |
| `axioms_action.roles.json` | the role of every clause, the library's SHA-256 and its version | `lc_action_library.load` |
| `axioms_action.templates.json` | the seven applicability templates | the compiler only, never GK |

`lc_action_library.load` checks the three files together. It raises
`LibraryError` in these cases:

- a missing or extra field, or a field of the wrong type;
- another library name, or a template version that differs from the library's;
- a library file whose bytes do not match the recorded SHA-256;
- a clause without a role, or a role without a clause;
- a role that does not fit its clause, for example a positive `poss` head
  outside an applicability default.

A library edit therefore needs a new hash in the role index. The version is
a string that must equal the template file's version; a changed library gets a
new version by convention, which no check enforces.

The library identity is `{id, version, hash, roles_hash, templates_hash,
status}`. `hash` and `templates_hash` are the SHA-256 of the two files.
`roles_hash` is the SHA-256 of the role index in canonical JSON, so it
follows the content and not the whitespace. A source artifact records the
identity, and the identity is part of the source hash.
`action_route.library_view` compares a source's identity with the loaded
library; the route's own query compilation uses the loaded library without
that comparison.

## Clauses by role

Every clause has the layout of the [action clauses](action-clauses.md): each
literal that holds a situation ends with one context term
`$ctxt(present, S, L, $obj)`, with the situation in its world slot. The static
literals (`isa`, `connected`, `differ`, `standard_mode`, `surface`,
`derived_property`) and `reachable` have none.

| role | count | clauses | in the views |
|---|---|---|---|
| `static_helper` | 11 | `standard_mode_*` (bus, train, ship, ferry, plane, taxi, foot), `surface_*` (table, floor, shelf, counter) | all |
| `applicability_default` | 4 | `poss_move_person`, `poss_take_hand`, `poss_put_on_hand_block`, `poss_put_on_hand_surface` | all |
| `hook_default` | 5 | `ok_move_default`, `ok_take_default`, `ok_put_on_default`, `ok_put_in_default`, `ok_change_default` | all, except the hook of a constructor that the text restricts |
| `denial_consequence` | 1 | `denied_not_poss` | all |
| `effect` | 15 | `eff_move_*`, `eff_take_*`, `eff_put_on_*`, `eff_put_in_*`, `eff_change` | verify, discovery |
| `marker` | 6 | `chg_move_from`, `chg_take_empty`, `chg_take_on`, `chg_put_on_holding`, `chg_put_on_clear`, `chg_put_in_holding` | verify, discovery |
| `frame` | 6 | `frame_located_at`, `frame_on`, `frame_in`, `frame_holding`, `frame_have`, `frame_property` | verify, discovery |
| `derived_no_inertia` | 1 | `derived_no_inertia` | verify, discovery |
| `reachability` | 1 | `reach_step` | discovery |

A snapshot view (`question`, `ask`, and `verify` with no steps) takes the first
four roles with the situation bound to the planning root. It holds no effect,
marker, frame or reachability clause, and no `$do` term.

### Defaults

The four defaults are the library's own permissions. Each is an applicability
template with the default's class conditions, concludes `poss` and is blocked
by the denial marker of the same action:

```json
{"@name": "poss_move_person", "@logic": [
  ["-isa", "person", "?:A"], ["-standard_mode", "?:M"],
  ["-is rel2", "located_at", "?:A", "?:F", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["-connected", "?:F", "?:T", "?:M"],
  ["-differ", "?:F", "?:T"],
  ["-ok_move", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["poss", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]],
  ["$block", 0, ["execution_denied", ["move", "?:A", "?:F", "?:T", "?:M"], ["$ctxt", "present", "?:S", "?:L3", "$obj"]]]]}
```

| default | conditions |
|---|---|
| a person moves by a standard means | `isa(person, A)`, a standard means M, `located_at(A, F)`, `connected(F, T, M)`, F and T differ |
| a hand takes a block | `isa(hand, H)`, `isa(block, X)`, H empty, X with a clear top, X on some Y |
| a hand puts a held block on a block | `isa(hand, H)`, `isa(block, X)`, H holds X, X and Y differ, `isa(block, Y)`, Y with a clear top |
| a hand puts a held block on a surface | `isa(hand, H)`, `isa(block, X)`, H holds X, X and Y differ, Y a surface |

`put_in` and `change` have no default: the text states who can do them. A
route alone permits no mover. A robot needs a rule of the text, such as "Every
robot can travel by bus".

The five default hooks `ok_<constructor>(ACTION, C)` hold for every action of
their constructor. When the text restricts a constructor, the compiler leaves
its default hook out and adds a hook that requires every restriction check.

`denied_not_poss` is `execution_denied(ACT, C) -> -poss(ACT, C)`. Only an
explicit denial of the text produces the marker. A failed restriction gives
`-poss` through its own necessity clause and never the marker.

### Effects and markers

Every effect needs `poss(ACTION, C(S))` and concludes at
`C($do(ACTION, S))`. Each fact that an action deletes has a strict negative
effect and a marker clause `changed_*`, keyed on the action term, that blocks
the frame of that instance. An effect and its marker form a pair.

| constructor | writes |
|---|---|
| `move(A, F, T, M)` | A at T; A not at F, with a marker |
| `take(H, X)` | H holds X; H has X; H not empty, with a marker; X not on its support Y, with a marker; a block support Y gets a clear top |
| `put_on(H, X, Y)` | X on Y; H does not hold X, with a marker; H empty; a block Y loses its clear top, with a marker |
| `put_in(H, X, B)` | X in B; H does not hold X, with a marker; H empty |
| `change(A, X, V, Tool)` | X has the property V; nothing is deleted |

A positive write has no marker clause.

### Frames

A frame keeps a stored fact across an executable action, unless the action
wrote that instance. The six frames cover `located_at`, `on`, `in`,
`holding`, `have` and every `has property` value. Each has confidence 0.99,
the frame confidence of `axioms_std.js`:

```json
{"@name": "frame_located_at", "@confidence": 0.99, "@logic": [
  ["-is rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", "?:S", "?:L", "$obj"]],
  ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L1", "$obj"]],
  ["is rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]],
  ["$block", 0, ["changed_rel2", "located_at", "?:X", "?:P", ["$ctxt", "present", ["$do", "?:A", "?:S"], "?:L", "$obj"]]]]}
```

A plan of three frame uses therefore has the confidence 0.9703 although the
text states no probability. The answer text does not count this part
([answer text](../architecture/action-answers.md#answer-text)).

`derived_no_inertia` marks every value V with `derived_property(V)` as written
in every successor. A computed property is therefore never carried by a frame.

The library has no frame for a negative fact. A query that needs a negative
fact kept across an action stops, except a verification in which only the
negative question of the final formula needs it
([backend requirements](../architecture/action-compilation.md#backend-requirements)).

### The search step

```json
{"@name": "reach_step", "@logic": [
  ["-reachable", "?:S", ["s", "?:N"]],
  ["-poss", "?:A", ["$ctxt", "present", "?:S", "?:L2", "$obj"]],
  ["reachable", ["$do", "?:A", "?:S"], "?:N"]]}
```

The query supplies the seed `reachable(WROOT, N)`. N is the depth in unary
form, from the stated step bound or the search cap.

## Templates

A template is a `poss` law of one constructor. The literal
`-$source(ACTION, C)` stands for the conditions of a permission of the text.
The compiler replaces it when it compiles a permission. GK never reads this
file.

| template | constructor | physical conditions |
|---|---|---|
| `tpl_move_public` | `move` | A at F, `connected(F, T, M)`, F and T differ |
| `tpl_move_stated` | `move` | A at F, F and T differ: the endpoints that the rule states |
| `tpl_take` | `take` | X a block, H empty, X with a clear top, X on some Y |
| `tpl_put_on_block` | `put_on` | H holds X, Y a block with a clear top, X and Y differ |
| `tpl_put_on_surface` | `put_on` | H holds X, Y a surface, X and Y differ |
| `tpl_put_in` | `put_in` | H holds X, X and B differ |
| `tpl_change` | `change` | none |

Every template also requires the restriction hook `ok_<constructor>` of its
action.

## What the library covers

- `take` takes a block from a support. It does not take a utensil or food.
- Taking gives possession (`have`). Putting down removes `holding` and keeps
  `have`. The two fluents have separate frames.
- A surface takes any number of objects. A block top takes one.
- A held object does not move with its holder. A query that reads the
  location of such an object stops (`unsupported_transport_dependency`).
- `unspecified` is a constant in a means or tool slot. No standard mode and no
  default uses it.

## The ordinary view

The action input does not load `axioms_std.js`. The query pass adds one
reviewed family of ordinary clauses, `V1-core`, in the law pattern of the
library: `on` excludes `under` and `below`. The fluents have the signatures of
the ordinary encoding, so these clauses apply to the library's fluents
unchanged.

## Related pages

- [Action clauses](action-clauses.md) — the predicates, the context term and the clauses of the text
- [Action compilation](../architecture/action-compilation.md) — how the compiler selects the library clauses of a view
- [GK clause list](gk-clauses.md) — the clause format and the frame block of `axioms_std.js`
