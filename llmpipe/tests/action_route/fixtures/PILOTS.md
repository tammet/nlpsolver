# The three pilot texts as integration regressions

WP02 work item 5. The gold Stage-2 formulas are in `cases/p01_travel.json`,
`cases/p02_tower.json` and `cases/p03_food.json`; the hand GK inputs of the
September 5 pilot are in `gk/`. This page records the reviewed corrections to
the gold formulas and why the maintained compiler's clauses must differ from
the hand files.

## Reviewed corrections to the gold formulas

| text | hand file | gold | reason |
|---|---|---|---|
| tower S3 "Nothing is on top of any block." | three enumerated `clear_top` facts at `s0` | `forall X: isa(block,X) -> clear_top(X)` inside `holds(W0, ...)`, every fluent at W0 | A3.2: a universal statement keeps its quantifier; enumeration is for "both these blocks". The same initial state. |
| tower Q "b on a and c on b" | `$defq0` definition clause with the two conjuncts and the reachability literal | `["plan", ["and", on(b,a), on(c,b)]]` | A3.3: the compiler, not the translation, introduces the answer situation and the seed. |
| travel S1 "Ann is in Haapsalu." | `isa(person, Ann)` as a separate `entity_S1` clause plus `located_at` | one unit with both atoms | same clauses; the typing comes from the Stage-1 category in both. |
| food S2 "Ann can break the egg." | `can(...)` with free `?:S`, `?:C` | `holds(W0, can(Ann, change(Ann, egg, broken, unspecified)))` | A2.3: an unqualified availability is a law at every situation; the compiler binds S, the translation does not write it. |
| food S3/S4 instrument phrases | possession of the tool added to the condition | same | kept; it is A3.2's own example. |
| all three | `reachable(s0, s^3(0))` or `s^4(0)` as a text clause | no seed in the source; `plan` with no bound seeds the configured cap (4) | A3.3: the seed belongs to the query artifact. |

No other formula changed. The expected plans are unchanged: two moves, four
block actions, three property changes.

## Why the compiled clauses differ from the hand files

A4.5 requires these differences to be written down before WP10 compares
anything.

1. **Restriction hooks on every executability path.** The hand library's
   `poss_take`, `poss_put_on_block`, `poss_put_on_surface`, `poss_put_in`,
   `poss_move` and `poss_change` have no hook. Every path of the maintained
   route (the four library defaults and the template paths of the source
   rules) requires `ok_<constructor>(ACTION, C)` (A4.2). With no source
   restriction the hook is universally satisfied, so the pilots' proofs gain
   one trivial step per action and lose nothing.
2. **One executability predicate.** The hand files have the permissions
   `can_*` and signed `poss_*` laws. The maintained route has `poss` only: the
   library's four defaults, and one path per applicability template for each
   source rule (food S2 and S3 take `tpl_change`). An explicit denial gives
   the marker `execution_denied` and `-poss` through `denied_not_poss`; a
   strict restriction gives a `-Q -> -poss(pattern)` necessity clause (A4.2).
   The pilots have no denial and no restriction.
3. **Source scope and contexts made explicit.** In the hand files the
   situation variable in a rule is written by hand (`?:S`) with one context
   variable. The compiler introduces the situation, binds it before
   Skolemization (A4.1) and puts it in the world slot of one context term per
   literal (`docs/encodings/action-clauses.md`). Quantified descriptions get W0 in every fluent
   (tower S3), which the hand files achieved by enumeration.
4. **Stated endpoints.** None of the three pilots states a movement rule with
   its endpoints, so every movement reads `connected` (the library default,
   or the public template). `travel_stated.js` (kept as a variant of p01)
   adds a rule with fresh universal endpoints; its paths take the public
   template, and the gold pins that it creates no stated-endpoint path.
5. **Explicit distinctness in placement.** The hand `poss_put_on_*` and
   `poss_put_in` laws use the positive literal `["=", X, Y]` evaluated by GK
   with `equality: 0` at clause creation. A4.3 makes explicit `differ` the
   reference implementation for move and placement, and the fixtures test
   that form. The `differ` facts themselves (both orders, from every pair of
   `#:` ids the hand file paired) are unchanged: the tower's twenty facts over
   its five entities, and the travel file's six directed facts over its three
   places (Ann is not paired there; all ordered pairs of its four entities
   would be twelve). Backend strategy work is a separate task and is not
   proposed here.
6. **Query and seed.** The hand files put the reachability seed and the
   `$defq0` question into the text file. The compiler puts them into the query
   artifact, with the seed from the stated bound or the configured cap, and
   records whether a cap was explicit (A3.3). The hand files used depth 3 for
   travel and food; the gold uses the default 4 and expects the same plans.
7. **Provenance.** Every emitted clause names its source unit or library law,
   its role and its scope (A4.4). The hand files name units only.
8. **Snapshot views.** The hand files are discovery inputs only. The
   fixtures' initial and verify queries on the same texts (c18, c22, c28, the
   `after_*` variants) select views by role; the hand `*_after_*` checks were
   separate files with the situation term written by hand.

## What must not change

- The signed library's strict negative effects and their markers (rule 4).
- The action strategy and the 0.10 acceptance cutoff (A6.3, A5.2).
- The plans and their lengths. The five- and six-action towers
  (`tower_holding5.js`, `tower_occupied6.js`) stay archived search
  limitations; the fixtures ask for `not_found` within four steps and do not
  require their discovery (A8.1).
