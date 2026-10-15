# Coverage index (WP02)

Every contract regression C01–C28 of A8.1, every A8.1 family, and the three
pilot regressions, with the case file that pins each. A case may serve several
identifiers; the `contract` field of the record lists them.

## C01–C28

| ID | required contrast | case | queries / variants that pin it |
|---|---|---|---|
| C01 | negative fact not lost by an unrelated action | `c01_unlicensed_polish` | Q1 (backend diagnostic, then not_found), K1 invalid at step 2 |
| C02 | a real licence-granting write removes the prohibition | `c02_licence_granted` | Q1 plan on a validated backend, Q3 No, K1 valid |
| C03 | only-if-red: Yes / No / Unknown / contested | `c03_only_if_red` | Q1 (base, Unknown); variants true, false, unknown, both (Q2, the `can` contrast, removed in encoding v2) |
| C04 | an explicit denial gives an immediate No | `c04_negative_capability` | Q1, Q3 (Q2, the `can` duplicate, removed in encoding v2) |
| C05 | two restrictions conjoin; other hand needs red; class-scoped guard preserved; anonymous hand; both put_on branches | `c05_two_restrictions`, `c05b_put_on_branches` | c05 Q1/Q2, dry, not_red, third_hand, existential_hand (control), existential_hand_only, class_scoped_hands, class_scoped_robot_red / _not_red / _declared; c05b Q1/Q2 + dry_b_occupied |
| C06 | a stated-endpoint path keeps permit and actor; a public connection stays an alternative | `c06_scoped_route` | Q1–Q3, variants missing_permit, public_route, public_route_no_permit |
| C07 | clean bowl + washing law needs a policy; stored clean persists | `c07_clean_bowl` | Q1 diagnostic; variants stored_policy, computed_policy, law_only |
| C08 | computed readiness loses support; no inertia | `c08_computed_readiness` | Q1–Q4, K1 |
| C09 | physical conflicts, including the empty plan; declared flat set; accepting controls | `c09_inconsistent_states` | ten variants (two_cities_flat with the declaration, two_cities_undeclared without) |
| C10 | ticket OR pass: alternatives, not a collision | `c10_ticket_or_pass` | Q1 + variants |
| C11 | merged methods with different effects | `c11_method_collision` | Q1; variant tools_distinguish |
| C12 | exact / at most / exactly 0 / at most 0 / lower cap; seed inspected | `c12_step_bounds` | Q1–Q10 with seeds |
| C13 | one uncertain source is not two pieces of evidence | `c13_uncertain_scoped_route` | Q2 (0.6), Q3 (the one-step plan, 0.6; `shared_source_confidence`); strict_control; alternative_support; probably_not_available and uninformative_location (unsupported) |
| C14 | source-only artifact; four queries; unsupported unit kept | `c14_source_reuse` | Q0–Q6; variant with_occurrence |
| C15 | quantified clear-top at the root world, not a law; standing stored law unsupported | `c15_quantified_clear_top` | Q1–Q3, K1; variant standing_stored_law |
| C16 | on-table-to-red persists after lifting; standing law recomputed | `c16_on_table_red` | Q1–Q3 |
| C17 | dynamic → timeless class/connection is mixed_scope_rule, also via helper | `c17_mixed_scope_rule` | Q1; variants through_helper, connected_head, controls |
| C18 | immediate questions bind the planning root | `c18_initial_binding` | Q1–Q6 |
| C19 | reserved vocabulary; open values; unspecified | `c19_reserved_vocabulary` | eight variants |
| C20 | verify: valid, false first, unknown prefix, false goal, empty, allowance | `c20_verify` | base Q2, Q5; a_red Q1, Q4, Q6, Q7; unknown_prefix Q3 |
| C21 | slot restrictions unsupported with detail | `c21_slot_restriction` | three variants + fluent control |
| C22 | change deletes nothing; explicit not-raw does; library negatives present | `c22_change_no_delete` | Q1, Q2; variants explicit_not_raw, defeasible_effect, library_negatives_present |
| C23 | source-bound endpoints keep conditions; fresh or question endpoints give no stated-endpoint path | `c23_variable_endpoints` | Q1, Q2; variants fresh_universal, unclassified_relation |
| C24 | Tallinn + Estonia not inconsistent; hierarchy diagnosed, stated or not | `c24_nested_places` | Q1; variants flat_control, different_actors, unstated_hierarchy |
| C25 | rejected_answers at 1.0 not eligible; cutoff; invalid-first | `c25_rejected_answers` | Q1–Q5 |
| C26 | can -> Q rejected; permissions and denials still work | `c26_can_arrow_q` | Q1, Q2; three variants |
| C27 | possession is not accompaniment; held object after a move | `c27_transport` | Q1–Q3; variant possession_only |
| C28 | snapshot view; effect clauses cannot reach initial questions | `c28_snapshot_view` | Q1–Q4 (role lists) |

## A8.1 families

| family | cases |
|---|---|
| Permission strength | c01, c04, c10, x06 |
| Route scope | c06, c13, c23, p01 |
| Necessary/sufficient conditions | c03, c26, x08 |
| Restriction composition | c05, c05b, c21 |
| Condition evidence | c03, c04 |
| Actor/object identity | c09 (two_held, self_support), x01 |
| Open property values | c19, x02, p03 |
| Situation scope | c07, c15, c16, c17, x04, p02 |
| Partial effects | c02, c22, x03 |
| Derived state | c07, c08, c16, p03 |
| Negative state | c01, c02, c20, c22, x03 |
| Queries | c12, c18, c20, c25, c28, x04, p01, p02 |
| Source reuse | c14, c28, x07 |
| Unsupported meaning | c10, c11, c19, c21, c24, c27, x05 |
| Ordinary-route regression | x07 |

## Cases added by the encoding-v2 migration (2026-09-23)

| case | what it pins | queries |
|---|---|---|
| `c29_two_applications` | an uncertain robot movement rule: one application 0.6, a two-step plan 0.36 (the counting rule) | Q1, Q2 |
| `c30_uncertain_put_on` | an uncertain `put_on` rule: the block path at 0.6; a target that is a block and a table has two paths of the same rule (measured: GK pools them to 0.84; the two paths share one source, so the value is not validated semantics) | Q1; variant overlap |
| `c31_two_world_scope` | a conditional initial description of W0 does not reach W1; a standing law applies at both roots | Q1, Q2; variant standing_law |
| `c32_two_world_witness` | an initial witness is tied to its world; a standing existential head is unsupported | Q1, Q2; variant standing_existential |
| `c33_root_selection` | the planning root selects the seed and the question world; a W1 fact does not shorten a W0 plan; one source, two roots | Q1-Q5 |
| `c34_transport_per_root` | the transport dependency is decided from the root's facts only | Q1, Q2 |
| `c35_qualifier_policy` | provenance and scope locations, knowers, a past fact, a location without a role | Q1; seven variants |
| `c36_scoped_persistence` | a scope-located fact persists across an action at its own location, not at another | Q1-Q4 |

## Retained earlier tests (A8.1 last paragraph)

| test | case |
|---|---|
| witness scope | x04 (base unsupported; without_s1; two_argument_witness sk(S,X)) |
| source mode (occurrence vs ability) | x05 same_verb, c14 with_occurrence |
| alias | x01 (S6 pronoun); introduced_actor is the supported existential-actor control |
| signed write | c02, c22, x03 (with lamp_on and lamp_unknown controls) |
| invalid first candidate | c25 Q5 |
| ordinary profile | x07 |
| profile mismatch of blocks_impossible / hard_only_if | x08 |

## Pilot regressions

| pilot | case | controls kept |
|---|---|---|
| travel | `p01_travel` | reversed, stated_capability, after_bus_not_at; baby in c04; rabbit and rabbit_forest in c19 |
| tower | `p02_tower` | holding_c (five actions, not required), occupied (six, not required), after_take_b (three checks) |
| food | `p03_food` | no_pan, after_break_have_pan |

## Work item 6 of WP02

Source-only use, an initial question, a bounded discovery question and a
supplied-sequence query on one source: `c14_source_reuse` Q0–Q4. The
no-invented-entity checks are its Q5 and Q6 and `x04` Q1.

## Counts

48 case files: 28 contract cases (C05 has two files, so 29 files), 8 family
cases (x01–x08), 3 pilots and the 8 migration cases above.
`fixture_materialize.py` builds 153 effective cases from them (one per base source and per variant); `check_fixture_schema.py`
validates every effective case and verifies that every identifier C01–C28
appears in at least one record's `contract` list.
