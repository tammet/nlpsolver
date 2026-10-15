# Fixture-review record (WP02)

Status: **approved for WP03 offline implementation — Astra, 2026-09-20.**
All forty records' formula/query expectations and the repaired fixture tools
are approved. Two minor Stage-1 annotation corrections remain before exact
prompt-gold use; they do not block WP03. See the completion review below and
[the completion review memo](../../../memos/MEMO_2026_09_20_wp02_completion_review_astra.md).
Fable authored all forty records (2026-09-10). Astra reviewed them on
2026-09-10 and did not approve them
([the independent review](../../../memos/MEMO_2026_09_10_wp02_gold_review_astra.md)).
Fable applied the repair pass on 2026-09-11
([the repair report](../../../memos/MEMO_2026_09_11_wp02_repair_fable.md)).
Astra completed the focused re-review on 2026-09-11:
[re-review memo](../../../memos/MEMO_2026_09_11_wp02_rereview_astra.md).
That review approved twelve records' formula/query expectations and listed
RR1–RR5 for the others. The historical table below preserves those findings;
the September 20 completion review supersedes its pending dispositions.
Approval is not a claim that an implemented compiler passes these records.
Fable applied the completion pass on 2026-09-20
([the completion report](../../../memos/MEMO_2026_09_20_wp02_completion_fable.md));
the section "Completion pass" below lists each correction.

| field | value |
|---|---|
| author | Fable 5.1 (`claude-fable-5-1`), high effort, 2026-09-10; repair 2026-09-11 |
| reviewer | Codex Astra, 2026-09-10, 2026-09-11 and 2026-09-20; completion review approved for WP03 |
| model calls | 0 (authoring, review, repair) |
| GK calls | 0 |
| inputs | Appendix A of the work-package plan (revision 3), Astra's 2026-09-09 review and response, the WP01 report, the signed library, the pilot hand files, `docs/encodings/stage-1.md` and `stage-2.md`, the saved 2026-09-09 checks, the 2026-09-10 review memo and its probe |

## Author's self-check (after the repair)

Done for every record before handing over again:

1. Every effective case built by `fixture_materialize.py` passes
   `check_fixture_schema.py`: complete units (text, Stage-1 projection with
   concrete/generic entities, Stage-2), strict Stage-2 grammar, declared
   entity ids, query packages with bounds and seeds, an expectation with
   evidence for every query, ground candidates with known verdicts.
2. `check_fixture_mutations.py` rejects 61 invalid inputs, each with the
   message of the intended rule: the thirteen probes of the review, the
   inputs the re-review found accepted, and the materializer's rules; the review's own probe reports zero
   accepted inputs and one launch counted once.
3. No query changes the source; every source change is a variant; every
   candidate names its variant.
4. Every diagnostic uses a reason from the decided list (disposition 1).
5. The seeds in c12 and c14 follow A3.3, including the zero bounds.
6. `README.md` describes the materialization rules, the pattern semantics and
   which layer checks which property.

## Dispositions of the nine open questions

Decided in the repair; recorded here before any validator hard-codes them.

1. **Reason names.** Accepted under `unsupported_translation`:
   `unsupported_stored_state_law` (c15), `existential_state_law_head` (x04),
   `unsupported_action_kind` with details creation / transport / transfer
   (x05), `unexpressible_temporal_permission_scope` (x05),
   `defeasible_text_effect` (c22), `occurrence` (c14, x05). Added:
   `existential_availability_head` (x01 agentless; an existential actor
   inside an availability, whose witness would depend on the situation).
   The unclassified relation is `unsupported_relation_policy` (c23), not
   `ambiguous_state_policy`. `insufficient_search_allowance` (c12, c20) is a
   run limit like `call_limit`, not a translation defect. The existential
   labels are not a ban on source existentials: a static existential
   description (x01 introduced_actor, x04 S2) is supported.
2. **Flat locations.** The flat set is a profile declaration
   (`profile.locations.flat`, c09 two_cities_flat). Exclusivity is checked
   only within a declared set. Two places for one actor with no declaration
   and no stated containment get `unsupported_location_granularity` (c09
   two_cities_undeclared, c24 unstated_hierarchy), never a conflict.
3. **Place containment form.** c24 S4 keeps `located_at(Tallinn, Estonia)` as
   an explicit input of that unsupported test. It is not a rule for English
   "in" and is distinct from the physical container relation `in`.
4. **Unknown goal constant.** c14 Q5 is `translation_invalid` with detail
   `unknown_entity`: a query validation failure, not `not_found`. A future
   query interface may declare a query-only constant; mentioning it would
   still add no route or location.
5. **Block versus surface.** No library law is added. c05b and c15 keep
   Unknown with Yes and No forbidden. The author's premise was wrong: a law
   "a block is not a surface" removes one positive branch and supplies no
   `-poss`, so it would not make these No.
6. **Holding by a non-hand.** Accepted (c27): the relation has actor and
   object slots; handhood constrains the library's default permission only.
7. **Joint can/after consequent.** Split into two derived units with one
   parent (`derived_from`), the same quantifier and the same antecedent
   (x08 S3a/S3b, S4a/S4b). No new reading label.
8. **Negative persistence horizon.** Dependency analysis within the query's
   horizon: the requirement applies when an established negative fact (or a
   negative an action writes) is read by a later step across at least one
   other transition (c01, c02, c20 a_red Q7). It does not apply when the
   negative is never established (x08 blocks) or is read directly in the
   next step (x08 chest, c08 Q4, c22 explicit_not_raw). c20 Q3 now uses a
   timeless denial so that the prefix rule is tested alone.
9. **Class guards.** Preserved. A restriction with a class antecedent keeps
   the guard in its necessity clause; its check is satisfied by the
   condition or by an explicit negative class fact; an actor of unknown
   class gets neither the restriction nor a free pass (c05 class_scoped_*).
   A3.2's guard-free example (c03) is also accepted, because take's own law
   supplies blockhood on every positive path; a translation with the extra
   antecedent keeps it.

## Items 10–12 resolved by the re-review

The original questions follow for traceability. Astra's decisions:

- 10: `answer` alone is enough for the gold; use `snapshot_result` in the
  future runtime adapter, documented when implemented.
- 11: accept `not_found` with preserved eligibility diagnostics for Q4;
  no replay runs on a nonground or non-s0-rooted answer.
- 12: retain the ordinary probability/evidence convention. WP06 must not
  change the convention to make a faulty shared-source implementation pass.

See RR3 for the strict-control metadata correction.


10. The outcome name for an answered snapshot question. A5.3 defines
    `verification_result` for a supplied sequence; the snapshot queries now
    record `answer` only. Propose a name (or confirm `answer` only) before
    WP12 writes outcome records.
11. c25 Q4: an accepted GK answer that fails eligibility (not s0-rooted) is
    recorded as `not_found` with a diagnostic, and `candidate_not_validated`
    is reserved for eligible candidates the replay rejects. Confirm.
12. c13: the three confidence layers (source probability 0.8, compiled
    evidence 0.6, backend-reported value) follow the pipeline convention in
    `solver/lc_packages.py`. Confirm that the action route keeps that
    convention; if WP06 changes it, only the numbers in c13 change.

## Historical review table — 2026-09-11

One row per case. "Checked" records independent inspection, not confirmation
that the gold is correct. R1–R9 refer to the independent review; the repair
column says what changed on 2026-09-11. Every row also received the common
repairs: complete effective units, evidence on every expectation, snapshot
queries without a `verification_result` outcome, `forbidden_*` lists where a
baseline was written as "not Yes". Approval is the re-reviewer's mark.

| case | reviewer / date | review result | repair 2026-09-11 | re-review |
|---|---|---|---|---|
| c01_unlicensed_polish | Astra / 2026-09-10 | not approved (R6, R8) | horizon rule written into the notes | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c02_licence_granted | Astra / 2026-09-10 | not approved (R6, R8) | backend lists only `negative_persistence`; the signed-write note moved to `backend_note`; Q3 forbids contested | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c03_only_if_red | Astra / 2026-09-10 | not approved (R2, R7) | blanket positive-poss ban replaced by `path_coverage`; necessity body exact; Q2 kept in every variant | Semantics reviewed; correction pending: RR1: effective text — Astra, 2026-09-11. |
| c04_negative_capability | Astra / 2026-09-10 | not approved (R6, R8) | forbidden outcome on Q3 | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c05_two_restrictions | Astra / 2026-09-10 | not approved (R2) | base S7 is the unscoped restriction the text states; class_scoped_hands, class_scoped_robot_red / _not_red / _declared added; existential_hand kept as positive control; existential_hand_only added | Semantics reviewed; correction pending: RR1/RR2: effective text and action metadata — Astra, 2026-09-11. |
| c05b_put_on_branches | Astra / 2026-09-10 | not approved (R8, q5) | Unknown exact with Yes and No forbidden; the "block is not a surface" premise corrected | Semantics reviewed; correction pending: RR1/RR2: effective text and action metadata — Astra, 2026-09-11. |
| c06_scoped_route | Astra / 2026-09-10 | not approved (R7) | pattern semantics defined (upper-case = clause variable); variant queries completed (Bob's executability under a public route) | Semantics reviewed; correction pending: RR1: effective text — Astra, 2026-09-11. |
| c07_clean_bowl | Astra / 2026-09-10 | not approved (R6) | partial replacements are `units_patch`; stored_policy confidence structured | Semantics reviewed; correction pending: RR1: effective text — Astra, 2026-09-11. |
| c08_computed_readiness | Astra / 2026-09-10 | not approved (R7, R8) | s0 ban replaced by "no initial_fact, no frame for usable"; Q3 confidence: persistence and frame weights separate, aggregate recorded not pinned | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c09_inconsistent_states | Astra / 2026-09-10 | not approved (R4) | two_cities_flat declares its flat set; two_cities_undeclared added (granularity diagnostic); every sentence is a unit | Semantics reviewed; correction pending: RR2: action projection — Astra, 2026-09-11. |
| c10_ticket_or_pass | Astra / 2026-09-10 | not approved (R6, R8) | ticket_only has its own entity map and text | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| c11_method_collision | Astra / 2026-09-10 | not approved (R6) | roots and roles in every Stage-1 projection, base and variant | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c12_step_bounds | Astra / 2026-09-10 | not approved (R8) | Q8 exactly 0, Q9 at_most 0, Q10 exactly 0 (not found); Q5 is a run limit | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c13_uncertain_scoped_route | Astra / 2026-09-10 | not approved (R1) | actor is a robot (no library default); layers separated (0.8 / 0.6 / backend); Q2, Q3 equal Q1; forbidden 0.36; per-clause 0.8 removed; Ann kept as alternative_support | Semantics reviewed; correction pending: RR3: strict-control backend — Astra, 2026-09-11. |
| c14_source_reuse | Astra / 2026-09-10 | not approved (R6, q4) | Q5 translation_invalid with detail unknown_entity and a declared undeclared id; evidence completed | Semantics reviewed; correction pending: RR1: occurrence variant text — Astra, 2026-09-11. |
| c15_quantified_clear_top | Astra / 2026-09-10 | not approved (R8) | c1p_law described as saved (answers empty, rejected item at 1.0); Q1 Unknown exact; Q2 not_found with the candidate_not_validated alternative | Semantics reviewed; correction pending: RR1: standing-law variant text — Astra, 2026-09-11. |
| c16_on_table_red | Astra / 2026-09-10 | not approved (R6, R8) | evidence and forbidden answers | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c17_mixed_scope_rule | Astra / 2026-09-10 | not approved (R6, R8) | entities declared for the bridge variant; variant texts | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c18_initial_binding | Astra / 2026-09-10 | not approved (R6, R8) | forbidden answers on the Unknown queries | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| c19_reserved_vocabulary | Astra / 2026-09-10 | not approved (R3) | the permission-removed query is the variant unspecified_mode_no_permission | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c20_verify | Astra / 2026-09-10 | not approved (R3, R8) | query-level additions replaced by the variant a_red; Q3 uses a timeless denial (variant unknown_prefix); candidates name their variant | Semantics reviewed; correction pending: RR2: restriction projection — Astra, 2026-09-11. |
| c21_slot_restriction | Astra / 2026-09-10 | not approved (R6, R8) | entities declared; control text reordered so units cover contiguous sentences | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| c22_change_no_delete | Astra / 2026-09-10 | not approved (q1) | reason `defeasible_text_effect` decided; entities declared | Semantics reviewed; correction pending: RR1/RR2: effective text and action metadata — Astra, 2026-09-11. |
| c23_variable_endpoints | Astra / 2026-09-10 | not approved (q1) | reason `unsupported_relation_policy` | Semantics reviewed; correction pending: RR1: effective text — Astra, 2026-09-11. |
| c24_nested_places | Astra / 2026-09-10 | not approved (R4) | S5 (ferry) in every source; unstated_hierarchy gets the granularity diagnostic; containment form documented | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c25_rejected_answers | Astra / 2026-09-10 | not approved (R3, R8) | Q5 replay context is c20_verify:a_red by reference; Q4 is not_found with a diagnostic (open item 11) | Semantics reviewed; correction pending: RR3: resolved source AND goal query — Astra, 2026-09-11. |
| c26_can_arrow_q | Astra / 2026-09-10 | not approved (R6) | override semantics defined by the materializer | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| c27_transport | Astra / 2026-09-10 | not approved (q6) | holding accepted for any actor; K1 names its step | Semantics reviewed; correction pending: RR1: possession variant text — Astra, 2026-09-11. |
| c28_snapshot_view | Astra / 2026-09-10 | not approved (R6, R8) | forbidden answers | Semantics reviewed; correction pending: RR2: effect projection — Astra, 2026-09-11. |
| x01_identity | Astra / 2026-09-10 | not approved (R5, R8) | agentless marked unsupported (`existential_availability_head`); introduced_actor added as the supported control; self_placement Unknown exact | Semantics reviewed; correction pending: RR2: action metadata and universal-control wording — Astra, 2026-09-11. |
| x02_open_values | Astra / 2026-09-10 | not approved (R6, R8) | common repairs only | Semantics reviewed; correction pending: RR2: action projection — Astra, 2026-09-11. |
| x03_partial_effects | Astra / 2026-09-10 | not approved (R8) | absent condition described as unknown; lamp_on and lamp_unknown controls added | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| x04_witness_scope | Astra / 2026-09-10 | not approved (R3, R5) | base queries unsupported while S1 is in the source; without_s1 is the separately materialized source; two_argument_witness added (sk(S,X)) | Semantics reviewed; correction pending: RR5: separate inspection assertions — Astra, 2026-09-11. |
| x05_unsupported_meaning | Astra / 2026-09-10 | not approved (R6, q1) | reasons decided; texts and evidence completed | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| x06_permission_strength | Astra / 2026-09-10 | not approved (R6, R8) | entities declared; evidence completed | Semantics reviewed; correction pending: RR2: action projections — Astra, 2026-09-11. |
| x07_ordinary_profile | Astra / 2026-09-10 | not approved (R6, R8) | outcome `ordinary_result` | Approved formula/query expectations — Astra, 2026-09-11; common tool checks RR3 still required. |
| x08_historical_reassessed | Astra / 2026-09-10 | not approved (R8, q7) | joint units split into derived units; horizon rule applied (no backend requirement in either text) | Semantics reviewed; correction pending: RR2/RR4: metadata and four-step backend requirement — Astra, 2026-09-11. |
| p01_travel | Astra / 2026-09-10 | not approved (R6, R8) | distinctness: six directed facts over three places | Semantics reviewed; correction pending: RR1: effective variant text — Astra, 2026-09-11. |
| p02_tower | Astra / 2026-09-10 | not approved (R6, R8) | common repairs only | Semantics reviewed; correction pending: RR1: effective variant text — Astra, 2026-09-11. |
| p03_food | Astra / 2026-09-10 | not approved (R6, R8) | common repairs only | Semantics reviewed; correction pending: RR1/RR2: effective text and action projection — Astra, 2026-09-11. |

## Amendments

Each row: date, case, unit or query, old expectation, new expectation,
reason, who decided. An implementation producing a different answer is not a
reason (WP02 work item 7). The reviewer proposals of 2026-09-10 were accepted
unless a row says otherwise.

| date | case / unit or query | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-10 | all | pending | reviewed, not approved | independent review | Astra |
| 2026-09-11 | c03 S5 clauses | must_not_have any positive poss(take) head | path_coverage: every positive path conjoins the hook; necessity body exact | R7 | Fable, per review |
| 2026-09-11 | c05 S7 | hand-guarded restriction with the guard dropped in the clauses | unscoped restriction "A block can be taken only if it is red" (text changed); guarded form moved to class_scoped_hands with the guard preserved | R2, disposition 9 | Fable, per review |
| 2026-09-11 | c05 variants | existential_hand expected Yes through hand two as the anonymous-hand test | existential_hand is a positive control; existential_hand_only (hand one only) expects Unknown; class_scoped_robot_red Yes, _not_red Unknown, _declared Yes | R2 | Fable, per review |
| 2026-09-11 | c05b dry_b_occupied Q1, c15 Q1, x01 self_placement Q1 | "not Yes" with Unknown or No allowed | Unknown with Yes and No forbidden | R8, disposition 5 | Fable, per review |
| 2026-09-11 | c08 S7 clauses; Q3 | ban on usable at s0; confidence 0.99 after two steps | no initial_fact and no frame for usable; confidence object (two frames at 0.99, aggregate recorded) | R7, R8 | Fable, per review |
| 2026-09-11 | c09 two_cities_flat; new two_cities_undeclared | conflict from absent containment | conflict only within the declared flat set; undeclared gets unsupported_location_granularity | R4, disposition 2 | Fable, per review |
| 2026-09-11 | c12 | no zero-bound query | Q8 exactly 0 (goal_already_holds), Q9 at_most 0 and Q10 exactly 0 (not_found) | R8 | Fable, per review |
| 2026-09-11 | c13 (whole record) | Ann (person) with the library default; clause confidence 0.8; query confidence 0.8; forbidden 0.64 | Robo (robot), sole support S3; layers 0.8 / 0.6 / backend; Q2 and Q3 equal Q1; forbidden 0.36; no per-clause number; Ann kept as alternative_support without a numeric pin | R1 | Fable, per review |
| 2026-09-11 | c14 Q5 | translation_invalid with a review question | translation_invalid, detail unknown_entity, forbidden not_found | disposition 4 | Fable, per review |
| 2026-09-11 | c15 Q1 evidence; Q2 | c1p_law described as Yes at 1.0; not_found fixed | c1p_law described as saved (answers empty, rejected item at 1.0); not_found from c1_description with candidate_not_validated as the alternative on an eligible candidate | R8 | Fable, per review |
| 2026-09-11 | c19 unspecified_mode Q3 | query-level units_remove | variant unspecified_mode_no_permission | R3 | Fable, per review |
| 2026-09-11 | c20 Q1, Q4, Q6, Q7 | query-level units_add of red(a) | variant a_red | R3 | Fable, per review |
| 2026-09-11 | c20 Q3 | unknown prefix, then a step refuted by -red(b) carried from s0 with no backend requirement listed | variant unknown_prefix: step 2 refuted by the timeless denial "The hand cannot take block b."; Unknown; No, Yes and contested forbidden | R8, disposition 8 | Fable, per review |
| 2026-09-11 | c23 unclassified_relation | ambiguous_state_policy | unsupported_relation_policy | disposition 1 | Fable, per review |
| 2026-09-11 | c24 base units; unstated_hierarchy Q1 | S5 omitted from the base; inconsistent_action_state | S5 in every source; unsupported_location_granularity with inconsistent_action_state forbidden | R4 | Fable, per review |
| 2026-09-11 | c25 Q4; Q5 | candidate_not_validated; replay context in prose | not_found with a diagnostic (open item 11); replay_context c20_verify:a_red | R3, R8 | Fable, per review (Q4 for confirmation) |
| 2026-09-11 | x01 agentless S2, Q1 | supported; world-independent witness sk_A; plan_found | unsupported (existential_availability_head); unsupported_translation; introduced_actor added as the supported control with the witness from a static existential | R5 | Fable, per review |
| 2026-09-11 | x03 Q3 evidence; new variants | "S5's condition ... is false" | "not established"; lamp_on (No / Yes) and lamp_unknown (Unknown / Unknown) controls | R8 | Fable, per review |
| 2026-09-11 | x04 Q1, Q2; new variants | plan_found using S2/S3 while S1 is unsupported | unsupported_translation (S1 in the source); without_s1 holds the plan expectations; two_argument_witness pins sk(S,X) | R3, R5 | Fable, per review |
| 2026-09-11 | x08 S3, S4 (hard_only_if) | one unit with can and after under one antecedent | two derived units each (S3a/S3b, S4a/S4b) with derived_from | disposition 7 | Fable, per review |
| 2026-09-11 | p01 S1 clauses, PILOTS.md | "differ from the four #: ids" | six directed facts over the three place ids | R8 | Fable, per review |
| 2026-09-11 | c02 Q1, Q3 backend | `signed_write_stops_opposite_sign` listed as a backend capability | `negative_persistence` only for Q1; Q3 none; the signed-write condition is a `backend_note` for a backend with negative persistence | R8 | Fable |
| 2026-09-11 | every snapshot query | outcome verification_result | answer only (open item 10) | R8 | Fable |
| 2026-09-11 | every unit of a text record | 180 units without a Stage-1 projection, 102 without text | complete projections with concrete/generic entities, roots and roles; every sentence covered by a unit | R6 | Fable, per review |

## Re-review entry — 2026-09-11

Astra reproduced the existing offline checks and original probes and wrote
new focused metadata/materialization probes. No model or GK calls. No gold
JSON was amended by the reviewer. The first-round semantic corrections are
accepted except for the precisely identified remaining test-boundary issues;
RR1–RR5 in the re-review memo define the bounded completion work. The source
library and copied GK evidence verified unchanged. The installed GK binary
was already changed before this review and was neither modified nor run.

## Completion pass: 2026-09-20 (Fable)

No model call and no GK call. No formula, expected answer or axiom of the
twelve approved records changed; c19 (approved) and x07 (approved) received
input completion only, as listed.

| item | correction | records |
|---|---|---|
| RR1 | every variant that changes a sentence or a formula has its own `text`; the materializer raises when such a variant has none; the checker verifies that each unit sentence occurs in the passage and each passage sentence belongs to a unit | 25 listed variants (c03, c05, c05b, c06, c07, c14, c15, c22, c23, c27, p01, p02, p03) |
| RR1 | `text` is source-only: question sentences removed from passages; the checker rejects a `?` in a passage. The ordinary-route input of x07 is `text` + the query text | p01, p02, p03, x07, x08 |
| RR1 | the two units derived from one sentence hold the parent sentence as `text`, with `derived_from` and a `note`; the editorial note left the passage | x08 S3a/S3b, S4a/S4b |
| RR1 | the formal sentence of the stored-law variant became the source sentence "At all times, every block is clear." | c15 standing_stored_law S3 |
| RR2 | `actions` (root, mode, roles) written by hand from the sentence for the 33 listed units and for 15 further action units that had no `action_reading` either | c05, c05b, c09, c10, c18, c19, c20, c21, c22, c23, c28, p01, p03, x01, x02, x03, x05, x06, x08 |
| RR2 | the checker rejects a null projection, a projection without the concrete entities of its formula, and an action unit without `action_reading` or `actions`; positive controls for a minimal projection, a minimal action unit and a formal-only record | tooling |
| RR2 | "The cook can whisk the egg." became "Every cook can whisk the egg." | x01 introduced_actor S3 |
| RR3 | strict_control Q2 has `backend: []` | c13 |
| RR3 | an override inherits every documented query field; an unknown query field raises | tooling |
| RR3 | `replay_context` is `{case, variant, query}`; the checker resolves it across all effective cases and requires a query with a final goal; c25 Q5 names `c20_verify:a_red/Q1` | c25, tooling |
| RR3 | an effective case holds `input_kind` and its candidates | tooling |
| RR3 | a package runs only in its view; a seed equals the bound and the search cap (`none` for an exact bound above the cap); an expectation may not forbid its own answer or outcome | tooling |
| RR3 | two snapshot queries had reused the id of a discovery query and inherited its seed; they have their own ids now | c24 different_actors Q1 -> Q2; x06 class_default_with_exception Q3 -> Q4 |
| RR4 | Q1 (default four-step horizon) requires `negative_persistence`, with the two-step plan under `on_validated_backend`; the new Q3 (at most two steps) keeps `backend: []` and the two-step plan | x08 hard_only_if_corrected |
| RR5 | the witness patterns moved from `clauses` to `inspection` with the operation `situation_insertion_skolemization`; `compile_source` expects the unit kept, its diagnostic, and no clause from it; the checker rejects `clauses.must_have` on an unsupported unit | x04 S1 (base, two_argument_witness) |
| RR5 (same defect) | the base S6 is unsupported and had a `must_have` "for inspection"; the clause expectation moved to the stored_policy variant, where S6 is supported | c07 |

Items 10 to 12: Astra's decisions are recorded above and need no record
change beyond RR3.

| date | case / unit or query | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-20 | x08 hard_only_if_corrected Q1; new Q3 | plan_found, backend [] under the four-step seed | Q1 unsupported_backend_requirement (negative_persistence) with the plan under on_validated_backend; Q3 at most two steps, plan_found, backend [] | RR4 | Astra (re-review), applied by Fable |
| 2026-09-20 | x04 S1 clauses | must_have sk(S) / sk(S,X) under `clauses` of an unsupported unit | the same patterns under `inspection` (operation named); no clause expected from compile_source | RR5 | Astra, applied by Fable |
| 2026-09-20 | c07 S6 clauses | must_have standing_law on the unsupported base unit | the same must_have on the stored_policy variant only | RR5 rule applied to c07 | Fable |
| 2026-09-20 | c13 strict_control Q2 backend | inherited shared_source_confidence | [] | RR3 | Astra, applied by Fable |
| 2026-09-20 | c25 Q5 replay_context | {case, variant, note} | {case, variant, query: Q1}; the state description moved to the evidence | RR3 | Astra, applied by Fable |
| 2026-09-20 | x01 introduced_actor S3 text | The cook can whisk the egg. | Every cook can whisk the egg. | RR2 | Astra, applied by Fable |
| 2026-09-20 | c15 standing_stored_law S3 text | (formal) a standing law asserting clear-top of every block | At all times, every block is clear. | RR1: a text case needs a source sentence | Fable |
| 2026-09-20 | c24 different_actors Q1; x06 class_default_with_exception Q3 | snapshot questions with an inherited seed s^4(0) | renamed Q2 and Q4; no seed | RR3 seed check | Fable |
| 2026-09-20 | p01, p02, p03, x07, x08 passages | passage ended with the question | source-only passage | RR1 | Fable |

## Completion review — 2026-09-20 (Astra)

RR1–RR5 are accepted. All forty records' formula/query expectations and the
repaired materialization/schema tools may be used for WP03. No further general
WP02 repair cycle is required. This decision supersedes the historical pending
statuses above; it does not claim a compiler, prompt or backend test has passed.

Independently reproduced: 133 effective cases, 61 diagnostic-specific mutation
rejections and positive controls, both earlier independent probes, and runner
self-tests. A further 167 read-only assertions checked the repaired query
requirements, final-goal reference, horizons, inspection boundary and effective
metadata. No provider requests or GK calls. Library and copied GK inputs match
the prior hashes. No fixture JSON was modified in this review.

Two input-annotation amendments may accompany WP03's initial work and must be
completed before these projections become exact gold Stage-1 prompt examples:

- x06 base S3 and class_default_with_exception S3: remove `roles.polarity`.
  Keep negation in the English and the existing Stage-2 `not(can(...))`; do
  not create a new polarity field or production dependency on it.
- x08 blocks_impossible_as_written S4/S5: distinguish the generic moved block
  and destination block in the entities and roles; S3 also needs its generic
  target entry. Keep both generic and preserve the existing Stage-2 formulas.

These are annotation corrections, not changes to logical expectations. The
full rationale and WP03 boundaries are in the completion review memo linked
at the top. WP03 still implements the production validator; the fixture
checker is not a substitute for it. Register the selected GK binary by hash
before backend execution and validate its required capabilities separately.

## Annotation amendments after the completion review: 2026-09-20 (Fable)

Both items of the completion review are applied. No Stage-2 formula, clause
expectation, answer or plan changed. No model call and no GK call.

| date | case / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-20 | x06 base S3; class_default_with_exception S3 (Stage-1 roles) | `polarity: negative` inside `roles` | removed; no replacement field. The sentence holds "cannot" and Stage 2 holds `not(can(...))` | polarity is not a semantic role and ordinary Stage 1 has no such field | Astra, applied by Fable |
| 2026-09-20 | x08 blocks_impossible_as_written S4, S5 (Stage-1 entities and roles) | one generic `block` as target and as destination | generic mentions `block 9` (moved block) and `block 10` (other block); target and destination name them | two generics of one noun are numbered (Stage-1 prompt, section 4.4) | Astra, applied by Fable |
| 2026-09-20 | x08 blocks_impossible_as_written S3 (Stage-1 entities) | the role target `block` had no entity entry | generic entity `block` added | the projection names every mention its roles use | Astra, applied by Fable |

The checker now rejects a role key outside the Stage-1 role set (actor,
target, source, destination, instrument, location, recipient, result) and two
roles of one action that name the same generic mention. The mutation check
has 63 entries. The projections remain action-relevant projections; they are
not complete ordinary Stage-1 outputs.

## Amendments found by the WP04 output check: 2026-09-20 (Fable)

The first check that matches gold clause patterns against emitted clauses
found two patterns that contradict another expectation of the same effective
case. No Stage-2 formula, answer or plan changed.

| date | case / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-20 | c05 class_scoped_robot_red, _not_red, _declared S2 `must_not_have` | `isa(hand, Robo 6)` and `isa(person, Robo 6)` with no sign | the same with `sign: +` | in class_scoped_robot_declared the unsigned pattern also matched the required negative fact of S12 ("Robo is not a hand"); the pattern forbids an invented positive class fact | Fable; for the reviewer's confirmation |
| 2026-09-20 | c06 S5 `must_not_have` | `connected(Haapsalu 3, Tallinn 4, bus)` with no unit | the same with `unit: S5` | in the public_route variants S7 states that public connection; the pattern forbids deriving it from the private availability S5 | Fable; for the reviewer's confirmation |

Both amendments above were approved by Sol on 2026-09-20
(`memos/MEMO_2026_09_20_wp04_review_sol.md`).

## Amendments from the WP06 review: 2026-09-20

Decided by Sol (`memos/MEMO_2026_09_20_wp06_availability_review_sol.md`),
applied by Fable. No Stage-2 formula of an existing case changed.

| date | case / unit or query | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-20 | c24 base Q1 `units` | S3, S4 | S2, S3, S4 | the diagnostic has two instances: Ann at two places outside a declared flat set (S2, S3) and Tallinn located in Estonia (S4); the complete attribution is the clearer result. The checks compare the unit list exactly | Sol (R2) |
| 2026-09-20 | c13 new variants `probably_not_available`, `uninformative_location` | none | S3 with `@p` 0.3 and S2 with `@p` 0.5 are `unsupported_confidence_form`; the unit keeps its formula and emits no clause; Q1 is `unsupported_translation`, with Yes, No, `plan_found` and `not_found` forbidden | the `p <= 0.5` boundary of `physical_v1` must be in reviewed gold material and in PROFILE.md; the ordinary route is unchanged | Sol (R3); wording by Fable, for the reviewer's confirmation |
| 2026-09-21 | c22 `explicit_not_raw` S3 `must_not_have` (inherited from the base text) | two patterns with no unit: no `-raw` effect and no `changed_property(raw)` marker from any clause | the same two patterns with `unit: S3`, through a `units_patch` of the variant | in this variant S4 states `after(cook, not raw)`, and the gold of S4 requires that effect and its marker; the inherited patterns without a unit forbade the clauses that S4 requires. The base text keeps the patterns without a unit | Fable (WP08), for the reviewer's confirmation |

The record set now materializes into 135 effective cases.
| 2026-09-22 | 27 `must_have` / `must_not_have` clause patterns whose literal is `can` with role `availability`, `denial` or `*` (15 case files; the list is in `memos/MEMO_2026_09_22_operational_availability_repair_fable.md`) | head `can(A, ACT)` for a permission; head `-can(A, ACT)` (`sign: -`) for a denial | head `action_available(A, ACT)` for a permission; head `capability_denied(A, ACT)` (`sign: +`) for a denial | library 1.2.0 (Sol's repair after the B3 stop): a source permission establishes the internal operational predicate, a denial its marker; the user-facing `can` follows from the links. The compiled representation changed, not the source, the Stage-1 projection, the Stage-2 `can` syntax or any answer expectation | Sol (authorization of 2026-09-22), applied by Fable |

## Amendments for encoding v2: 2026-09-23 (Opus, implementing the migration plan)

Source of every decision: `memos/MEMO_2026_09_22_encoding_v2_description_and_migration_plan_fable.md`
(revision c), steps 0.4 and 0.5, which apply Sol's answer 6 of 2026-09-22 and
Sol's reviews b and c. The user approved the plan on 2026-09-23 and asked for
its implementation. The rows below were written before any GK run of the
migration; they await the reviewer's confirmation. The edit scripts are
`elogs/encoding_v2_migration_2026_09_23/gold_step0_4.py` and `gold_step0_5.py`.
No model call and no GK call.

| date | case / unit or query | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-23 | c03 Q2 (base and the four variants) | `question(can(hand, take(hand, a)))`, Yes: the underlying-ability contrast | removed; the variants lose `queries_keep` | v2 has one planning predicate; Q1 already tests executability | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c04 Q2 | `question(can(Ann, move(...)))`, No | removed | a duplicate of the executable Q1 | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c14 Q3 | ability to travel Tallinn-Helsinki, Yes, independent of Ann's location | removed | a direct executable question would turn a Yes ability question into an immediate executability question | Sol (answer 6), migration 0.4 |
| 2026-09-23 | x06 base Q2 | ability for the Tallinn-Tartu leg while Ann is in Haapsalu, Yes | removed; the class_default_with_exception variant's own Q2 (a complete plan query) is unchanged | as c14 Q3 | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c13 Q1 (base, strict_control, alternative_support) | the capability control of the shared-source test | removed | Q2 measures current movement executability and holds the 0.6 test | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c13 probably_not_available, uninformative_location | Q1 (can) with the source-level diagnostic | Q2 (executable) with the same diagnostic | the unsupported-confidence variants ask executable | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c13 Q2, Q3 | confidence equals Q1, forbidden 0.36 as a double count; backend `shared_source_confidence` | confidence 0.6 (tolerance 0.005); 0.36 named as the two-application score; backend [] | v2 has no helper; the stated-endpoint path holds the evidence and a one-step proof applies S3 once | Sol (review b), migration 0.4 |
| 2026-09-23 | c18 Q1, Q4 | `can(Ann, change(... whisked ...))` in a question and in a conditional question | `executable(...)`; Q1 text "Can Ann whisk the egg now?" with `stage1_reading: executable_question`; answers Unknown and Yes re-derived from S3's path; the query-literal pattern is `poss` | the capability question is converted, not removed | Sol (answer 6), migration 0.4 |
| 2026-09-23 | x01 Q4 | `ask(P, can(P, change(...)))`, Ann 1 | `ask(P, executable(...))`, Ann 1 re-derived from S5's path | as c18 | Sol (answer 6), migration 0.4 |
| 2026-09-23 | c26 | `can` in a restriction condition: `unsupported_capability_restriction` | unchanged | the reason the contract gives today stays | Sol (review b) |
| 2026-09-23 | new c29_two_applications | none | an uncertain movement rule of a typed robot applied at two steps: Q1 0.6, Q2 plan at 0.36 (counting rule) | two-application control | Sol (choice 5, reviews b and c), migration 0.5 |
| 2026-09-23 | new c30_uncertain_put_on | none | an uncertain `put_on` rule of a typed robot: Q1 0.6 from the block path; variant overlap (a block that is also a table): Yes, confidence recorded | the paths of one unit are alternatives for one application | Sol (reviews b and c), migration 0.5 |
| 2026-09-23 | p01 new Q2, Q3 | none | "Is Ann in Tallinn?" Unknown (Yes forbidden), "Is Ann in Haapsalu?" Yes; the harness also asks both inside Q1's discovery view | factual questions beside successor clauses (Astra 5.3) | Sol (reviews b and c), migration 0.5 |
| 2026-09-23 | new c31_two_world_scope, c32_two_world_witness, c33_root_selection, c34_transport_per_root, c35_qualifier_policy | none | written now to `elogs/encoding_v2_migration_2026_09_23/gold_new/` and frozen by SHA-256 (`FROZEN.json`); moved into this directory by step 1b.7, when the compiler and the tools accept `worlds`, `planning_root`, `ambient`, `knower` and the unit context records | the fields exist from checkpoint 1b; the expectations exist before any GK run | Sol (reviews b and c), migration 0.5 |
| 2026-09-23 | 18 case files: every clause pattern that named `action_available`, `capability_denied`, `route_for`, `scoped_route` or `necessity_capability` (27 availability/denial patterns of the 1.2.0 amendment, 8 required and 5 forbidden route patterns, 2 capability-necessity patterns) | `action_available(A, ACT)`, `capability_denied(A, ACT)`, `route_for(A, F, T, M)`, `necessity_capability` | `poss(ACT)` on the compiled path (role `availability`); `execution_denied(ACT)` (role `denial`); a required route becomes the stated-endpoint path `poss(move(A, F, T, M))` with the same body and `body_absent: [connected]`; a forbidden route becomes "no path of the unit lacks connected"; c03's capability necessity is removed and c04's becomes the library `denial_consequence`; c13 S3's path pins `confidence: 0.6` | encoding v2 step 1.5: the compiled representation changed; no source, Stage-1 projection, Stage-2 formula or answer changed. Two pattern keys are new (`body_absent`, `confidence`; `fixtures/README.md`). Script `elogs/encoding_v2_migration_2026_09_23/gold_step1_5.py` | migration 1.5 |
| 2026-09-23 | c31_two_world_scope, c32_two_world_witness, c33_root_selection, c34_transport_per_root, c35_qualifier_policy | in `elogs/encoding_v2_migration_2026_09_23/gold_new/` | moved into `cases/` unchanged; the SHA-256 of each file equals `FROZEN.json` (checked before the move) | the compiler and the tools accept `worlds`, `planning_root`, `ambient`, `knower` and the unit context records (steps 1b.1-1b.6) | migration 1b.7 |
| 2026-09-23 | every clause pattern of every case file (the 1.5 patterns included) | a pattern names an atom and its sign, situation class and body | unchanged: the matcher of `README.md` compares the atom without its situation and context arguments, so the per-literal context pattern `$ctxt(present, ?:Wld, L, $obj)` of step 1b.4 needs no pattern edit; the pattern itself is asserted by `check_action_situations` (every compiled law clause, the agreement rule) and `check_action_library` (every library clause) | the compiled context term changed; no source, formula, answer or pattern changed | migration 1b.7 |
| 2026-09-23 | the 340 `holds(W0, F)` packages of the earlier cases | the one world W0 | unchanged; a case without `worlds` has the one world W0 | worlds default to `["W0"]` (migration plan section 9) | migration 1b.7 |
| 2026-09-23 | 16 case files: 22 clause patterns with `situation: "s0"`; c20 Q3 obligation strings; c28 Q1 `view_roles_included` | `s0` (the initial situation constant); `poss(take(hand,a),s0)`, `poss(put_on(hand,a,b),S1)`, `on(a,b,S2)`; `standing_law@s0` and six more `@s0` names | `named` (a world name in the world slot); `poss(take(hand,a),W0)`, `poss(put_on(hand,a,b),W0+1)`, `on(a,b,W0+2)`; `@root` (a law bound to the planning root) | encoding v2 step 2.9: the situation stands in the world slot of the context term; W0 is the root of these cases. The two `free` labels (c15 S3, c18 Q1) stay. Evidence prose that says s0 is not edited: it names the root W0 in the old spelling. No answer, source, Stage-1 projection or Stage-2 formula changed. Script `elogs/encoding_v2_migration_2026_09_23/gold_step2_9.py` | migration 2.9 |
| 2026-09-23 | c13 Q3, c29 Q2 (base) | `backend: []` | `backend: ["shared_source_confidence"]`; the pinned confidences stay (0.6 and 0.36) | checkpoint-2 decision (Fable's review, section 2): one action application reads `poss` in the reachability step, its effects and its frames; GK counts the evidence of an uncertain path once per use (C29.Q2 at 0.1296), so a discovery or verify query that can apply an uncertain path needs a backend that counts one application once. The query pass declares the requirement again (`lc_action_query._shared_units`); it never stops compilation. Backend requirements do not change GK inputs: no rerun. Script `elogs/encoding_v2_migration_2026_09_23/gold_step3_ssc.py` | Fable (checkpoint-2 review), migration step 3 |
| 2026-09-23 | new c36_scoped_persistence | none | a scope-located fact (the lamp is on, in the kitchen) across an unrelated move: Q1 verify at the ambient kitchen Yes; Q2 at the ambient hall Unknown (the fact is excluded, scope_location_mismatch); Q3/Q4 the same snapshot questions, Yes and Unknown | Sol's checkpoint-2 review: an action-level test of the frame's shared location variable, where the production encoding differs from the layout experiment; the frame itself is tested by a harness-built GK input (Q1's input asked at the hall), recorded in the run sheet, not as a query of the case. Written before any GK run of the case | Sol (checkpoint-2 review), migration step 3 |
| 2026-09-24 | 35 case files, 167 texts: 148 prose texts (evidence, notes, purpose, explain, candidate reasons, a backend note, a replay fragment, unit and pattern notes, compile details), the text of c25 Q3 and Q4, the expected replay diagnostic of c25 Q4, and the 16 `facts` strings of c09 | explanations in the pre-v2 terms: `s0` for the root, S1, S2 and states 1, 2 for successor situations, the runtime `can` and the capability it named, the `-can -> -poss` necessity, the scoped route `route_for`, the library clauses `can_move_person`, `can_take_hand`, `can_put_on_hand` and the signed `poss_*` laws; c30 `overlap` called its two same-source proofs alternative support | the same explanations in v2 terms: W0 for the planning root, W0+1, W0+2 for successors (as the c20 obligations since step 2.9), the denial marker `execution_denied` with `denied_not_poss`, the stated-endpoint template `tpl_move_stated`, the source paths with their templates, the library defaults `poss_move_person`, `poss_take_hand`, `poss_put_on_hand_block`, `poss_put_on_hand_surface`. A citation of a saved historical output keeps its names and says its date and layout (c15 Q1, c25 Q4); the c25 `gk_output` records stay as saved | Astra's review (answer g): explanations of current behavior use the v2 clauses before the experimental commit; historical evidence is not rewritten as if v2 produced it. Section 3 of the review: the c30 pooled value 0.84 is a measurement, not validated semantics. No answer, outcome, plan, pattern, backend list, Stage-1 projection or Stage-2 formula changed. Scripts `elogs/encoding_v2_migration_2026_09_23/gold_step3_prose.py` to `gold_step3_prose4.py`; every old and new text in `gold_step3_prose.txt` | Astra (review of 2026-09-24), migration step 3 |

## Amendments of the English examples for the repair round: 2026-09-28 (Opus)

Source of every decision: the consolidated work list
`memos/MEMO_2026_09_28_next_round_recommendations_fable.md` with its section 7,
and Astra's answers `memos/MEMO_2026_09_28_wp20_followup_decisions_astra.md`
(D1-D5, decided before this round). The rows change the authored English
examples of `prompts/actions/draft_v1/examples.json` (prompt revision E) and
their answer expectations in `tests/action_route/v3/cohort.json`. No fixture
case file in `cases/` changed: the formal same-term collision of
`c11_method_collision.json` stays as it is. The edit scripts are
`elogs/repair_round_2026_09_28/edit_examples.py` and `make_cohort_v3.py`; the
revision-D file is kept beside them as `examples_revision_D.json`. The WP19
records and scores are unchanged. No model call; the GK confirmation of every
expectation is `elogs/repair_round_2026_09_28/gold_gk/`.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-28 | worked_c11_method_collision S3, S5 | boil and fry both `change(Ann 1, egg 2, cooked, unspecified)`; source unsupported, `method_collision` | fry is `change(Ann 1, egg 2, crisp, unspecified)`, boil stays `cooked`; source supported; answer `plan_found` (frying alone, one step, is the shortest); a method-preservation review: each value a result the text states for its verb, boiling alone gives no crispness, frying alone no wetness | D1, constrained option (b): two methods stay distinct; a value the text never states (boiled, fried) is flagged for review, not accepted | Astra (D1), Fable (section 7) |
| 2026-09-28 | worked_c11_method_collision query | entities include `pot 3` and `pan 4` | removed | the text has no pot or pan | work list D2 |
| 2026-09-28 | worked_c10, c11, p01, p02, p03 query unit | `Q1` | `S7`, `S6`, `S4`, `S7`, `S5` | the prompt teaches S-numbering; the id alone made the reading and exactness checks fail | work list D2 |
| 2026-09-28 | worked_p02_tower S1-S4 | the hand `hand 1`; the block sentence as one unit S2 | the hand `robot hand 1` with class `hand` (C3: the compound stays the id); one unit per block, S2-S4, in the same sentence package; later units S5-S7 | the prompt teaches one unit per fact; C3 | work list D2, C3 |
| 2026-09-28 | world_selection, scope_and_knower, occurrence_not_permission | `prompt: false` (held separate in WP19) | `prompt: true` | D2: they show every selector and context field | Astra (D2) |
| 2026-09-28 | new only_by_restriction | none | a prompt example: only-by with free origin and means variables, `unsupported_restriction_scope`; not a measured case | C5 | work list C5 |
| 2026-09-28 | new new_gripper_hand, new_market_in_town, new_tartu_train, new_dated_fact, new_only_by_ferry | none | five new texts outside the prompts, with gold Stage 1, Stage 2 and answer expectations written before any model output: a compound hand (plan), a place in a place (`unsupported_location_granularity`), real place names with url metadata (plan), a dated past fact with a present question (Unknown; the fact is excluded, no world is invented), only-by with an unstated origin (`unsupported_restriction_scope`) | D3 | Astra (D3) |
| 2026-09-28 | the seven previously unmeasured examples | no answer expectation | standing_stored_unsupported `unsupported_stored_state_law`; snapshot_question Yes; empty_verify Yes; positive_effect_only `not_found`; worked_p01_travel the two-step plan; worked_p03_food the three-step recipe; explicit_point99 Yes at confidence 0.98 (2p - 1 of the stated 0.99) | D3 | Opus, for the reviewer's confirmation |

### Review repairs of the repair round: 2026-09-28 (Opus, after Fable's review)

Fable reviewed part 1 (`memos/MEMO_2026_09_28_repair_round_review_fable.md`),
confirmed the rows above and asked for three repairs before the run. They make
prompt revision E.1; the script is
`elogs/repair_round_2026_09_28/edit_examples_review.py`, and the revision-E
file is kept as `examples_revision_E.json`. No model output of revision E
exists.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-28 | Stage-2 instruction C8' | "A bare operation's VALUE is a result the text states for that verb" | "The VALUE is a property the text states for the object, in an effect, a condition or the goal; when the text states results for the verb, the VALUE is one of them (boil: cooked or wet, never boiled); a participle the text never states is a guessed value" | the first wording contradicted two gold examples (G1) | Fable (G1) |
| 2026-09-28 | positive_effect_only S2 | `after(change(Robo 1, egg 2, cooked, pan 3), wet(egg 2))` | `after(change(Robo 1, egg 2, wet, pan 3), wet(egg 2))`; the answer stays `not_found` | the text states wet as the result of cooking and never says cooked | Fable (G1) |
| 2026-09-28 | worked_c10_ticket_or_pass S7, worked_p02_tower S7 (query entities) | Haapsalu 2 and pass 4; table 5 | removed | the question does not mention them (G3) | Fable (G3) |

## Amendments of the English examples for round 2 after the v3 run: 2026-09-28 (Fable)

Source of every decision: `memos/MEMO_2026_09_28_v3_run_analysis_fable.md` (sections 7 and 8) and Astra's
`memos/MEMO_2026_09_28_v3_analysis_and_next_round_astra.md` (sections 4 to 6). The rows change the authored
English examples of `prompts/actions/draft_v1/examples.json` (prompt revision F) and their expectations in
`tests/action_route/v4/cohort.json`. No fixture case file in `cases/` changed. The edit scripts are
`elogs/round2_2026_09_28/edit_examples_f.py` (run once against the revision-E.1 file) and `make_cohort_v4.py`.
GK confirmation of every expectation under the repaired code: `elogs/round2_2026_09_28/gold_gk_v4_all.log`
(43 of 44; the tower at its known search limit). No model call.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-28 | worked_c11_method_collision S2, S4 | boil is `change(Ann 1, egg 2, cooked, unspecified)` | boil is `change(Ann 1, egg 2, wet, unspecified)`; fry keeps `crisp`; cooked stays an effect of both | the revision-F rule: two methods that share a stated result each take the result the other lacks; cooked/crisp translations still pass the method review | Fable, after Astra's D1 amendment |
| 2026-09-28 | new route_vs_permission_other_person | none | a public ferry route beside Ann's boat permission; "Can Ben eventually be at Isle?" is Yes by the public route; Ben's plan by boat is forbidden | Astra's contrast: a personal permission creates no route for another person | Fable |
| 2026-09-28 | new class_guard_unknown, class_guard_holds | none | "If Nia is a doctor and Nia has the pan, Nia can paint the fence red": with "Nia is a cook" the permission is Unknown, with "Nia is a doctor" Yes | a stated class condition about a named individual stays; unknown is not No | Fable, after Astra's P3 amendment |
| 2026-09-28 | new denied_first_step | none | "Robo cannot paint the gate green with the brush"; the supplied one-step sequence verifies No | a true No at step 1 survives the policy repair R1: the replay reads the denial | Fable |
| 2026-09-28 | new default_root_two_snapshots | none | two snapshots, a bus permission, "Is Mira at Hilltown?" with no selection: Yes at the default root W1; `query_contexts` empty | planning_root only for a snapshot the text names; omission is the accepted default, not W0 | Fable, after Astra's 4.1 |
| 2026-09-28 | new distinct_methods_board | none | sand gives smooth, paint gives smooth and blue; sand is `change(..., smooth, ...)`, paint `change(..., blue, ...)`; plan: paint; method-preservation review as for the egg | the value rule with a shared effect; a second method text beside the egg | Fable |
| 2026-09-28 | new same_source_other_goal | none | the source of worked_p03_food with "How can Ann get the egg whisked?"; plan: break, whisk | source formulas must not change with the question; the analysis compares the pair per model | Astra's source-independence contrast |
| 2026-09-28 | new exactly_zero_plan | none | "Find a plan for Robo to be holding the key in exactly zero actions": a plan question with an exact bound of zero; `goal_already_holds` | a plan with an exact zero bound is not an empty verification | Astra's 4.6 |

## Amendments of the English examples for round 3 after the v4 run: 2026-09-29 (Opus)

Source of every decision: Astra's `memos/MEMO_2026_09_29_round3_recommendations_astra.md` (authoritative, decisions
D1-D7) over Fable's `memos/MEMO_2026_09_28_round3_combined_recommendations_fable.md`. The rows change the authored
English examples of `prompts/actions/draft_v1/examples.json` (prompt revision G) and their expectations in
`tests/action_route/v5/cohort.json`. No fixture case file in `cases/` changed; a formal record keeps its explicit
semantics and gets no derived type. The edit scripts are `elogs/round3_2026_09_29/edit_examples_g.py` (run against
the kept revision-F file `examples_revision_F.json`) and `make_cohort_v5.py`. Each amended unit and its compiled
clauses were read one by one; the GK confirmation of every expectation is `elogs/round3_2026_09_29/gold_gk_v5.log`
(53 of 54; the tower at its known search limit), and the paired controls are `controls_gk_v5.log` (5 of 5 lose the
gold's result). No model call.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-29 | if_only_if_denial S2; conditional_signed_effect S2, S3; scope_and_knower S2, S3; past_fact_excluded S1; possession_and_holding, snapshot_ask, snapshot_question, empty_verify S2; held_object_transport S3; positive_effect_only S1; worked_c11_method_collision S1; new_market_in_town S1; new_dated_fact S1; class_guard_unknown, class_guard_holds S2; denied_first_step S2; exactly_zero_plan S2 | a definite first mention untyped ("Robo has the key": `have` only) | the class fact of the referent's first mention as a conjunct of its fact (`["and",["isa","key","key 2"],["have","Robo 1","key 2"]]`); scope_and_knower S2 keeps the stated `isa place lab 2` beside `isa lab lab 2`; the knower-scoped S3 types its token inside that unit | D1: one class fact at the first asserted introduction by a class noun, whatever the article | Astra (D1) |
| 2026-09-29 | if_only_if_denial S3; open_values_unspecified_tool S2; possession_and_holding, snapshot_ask, snapshot_question, empty_verify S4; positive_effect_only S2; class_guard_unknown, class_guard_holds S3; denied_first_step S3 | a referent first named in a law sentence untyped | its class in the envelope field `types` of that unit (`{"S4": [["isa","box","box 3"]]}`); the law formula holds its rule only | D1 with Astra's format interaction: no dropped type, no class atom in a law head, no added applicability condition; the chosen representation is the source-type record, pinned by the prompt example `hand_in_permission` | Astra (D1), Opus (the representation) |
| 2026-09-29 | worked_p01_travel, worked_c11_method_collision, worked_p03_food, same_source_other_goal S1; distinct_methods_board S1 | `isa person Ann 1` (`Tom 1`) that revision F's line P3b asked for | removed; the compiler records the person type from the Stage-1 category person (`stage1_person`), and the replay reads it | D3; the p01 compiler and replay control passes (`check_action_round3.py`, and gold_gk_v5: the two-step plan) | Astra (D3, G5) |
| 2026-09-29 | worked_p03_food, same_source_other_goal S1 | one unit "Ann 1 has an egg 2, a whisk 3 and a pan 4." | three units S1-S3, one per possession, each with its class fact; the later units S2-S5 become S4-S7 | D6: the strict independent possession facts are atomic, as the Stage-1 contract and both models do | Astra (D6) |
| 2026-09-29 | default_root_two_snapshots S3 | `pre_state W0` | unchanged; the Stage-1 line "a rule without a snapshot phrase has pre_state W0" teaches it | G4 | Fable (G4) |
| 2026-09-29 | new prompt examples dated_descriptions, bounded_permission, stated_guard, hand_in_permission, normal_rule_and_denial | none | prompt material only, not measured: two dated descriptions (past excluded, present kept, no `@time`); a permission "until Friday" with `@time` (temporal-scope diagnostic) and a `types` entry; a stated named-actor guard beside the stated class; a hand and a block first named in a permission (`types`); a default permission with `normally` on its head and a class denial, no `@p` | B7 and Astra's teaching contrasts; written apart from the unseen texts | Astra (prompt revision G) |
| 2026-09-29 | new denied_second_step (N1), unknown_second_step (N2) | none | paint-first sequences: step 1 licensed with its tool condition; step 2 denied (No) or without permission or denial (Unknown). N2 names the gate in a source sentence, since a query never adds an entity | Astra's N1/N2 corrections | Astra |
| 2026-09-29 | new default_rule_applied (N3), default_rule_exception (N4) | none | the default and its baby denial with a person (Yes) and a baby who is a person (No); the fixed endpoints select the stated-endpoint template, no public-route test | Astra's N3/N4 | Astra |
| 2026-09-29 | new robot_public_route (N5a), robot_rule_public_route (N5b), robot_named_ann (N14) | none | a robot on a public route without a rule: `not_found` at the bound 2; "Every robot can travel by bus": universal unconditioned endpoints, `tpl_move_public`, the one-step plan (without the connection: no plan); a human name with a stated robot class: no person type, `not_found`; an injected person category is an offline control with the note `conflicting_category` | D5 and Astra's N5b replacement and N14 | Astra |
| 2026-09-29 | new negative_persistence (N7) | none | the recipe of conditional_signed_effect with a later put_in step and the question "is the egg cooked and not raw?": `unsupported_backend_requirement` (`negative_persistence_unavailable`) before any launch. The question reads the negative: with "is the egg raw?" the requirement analysis reads the literal positively and the query is ready | Astra's N7 | Astra, Opus (the question) |
| 2026-09-29 | new root_selection_three_snapshots (N12) | none | three snapshots, "Starting from snapshot W1 ... exactly zero actions": `goal_already_holds`; the default root W2 and the root W0 give `not_found` (paired controls). With two snapshots W1 is the default root, so the lost-root case would not show | Astra's N12 (decisive envelope test) | Astra, Opus (the third snapshot) |
| 2026-09-29 | new past_first_type (N13) | none | block b and the table first named in a past description; the plan query excludes it and their lexical type records stay: the one-step take (knower-scoped past unit: `not_found`) | A11 in its narrow form | Astra |

## Staged plan-construction texts: 2026-09-29 (Fable)

Eight new English texts, each asking for a plan of two or more steps with a structure that no earlier example has.
The user asked for them. They are staged in `tests/action_route/staged/planning_examples_round4.json`, and are not yet
in `prompts/actions/draft_v1/examples.json` or in a cohort; the next freeze moves them. Each gold passes
`draft_prompts.compile_example`. The GK confirmation through the v5 runner's row code is
`elogs/planning_examples_2026_09_29/gold_gk.log` (9 launches, 7 of 8 give a replay-validated plan). No model call.
Sol reviewed the eight golds on 2026-09-29 (records, compiled clauses, reference plans) and accepted them with two changes, both applied: `reference_shortest_length` 2 for plan_travel_then_paint, and the unstack label `discovery_missed_verified_plan` (a model row gets that attribution only when its compiled translation matches the gold).

| date | example | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-29 | new plan_route_dead_end | none | three public legs past a dead-end first leg; the three-step plan | route search with a branch that leads nowhere | Fable |
| 2026-09-29 | new plan_travel_then_paint | none | a change permission conditioned on the actor's location; move, then change; painting first is forbidden | two constructors in one plan | Fable |
| 2026-09-29 | new plan_order_by_side_effect | none | mopping removes the dryness that waxing needs; wax, then mop; mop-then-wax is forbidden | goal interaction through a removed property | Fable |
| 2026-09-29 | new plan_precondition_other_object | none | baking needs the hot oven that heating produces; heat, then bake | a condition on another object | Fable |
| 2026-09-29 | new plan_unstack_then_take | none | a covered block: take c, put c on the table, take a. On GK, discovery on the gold gives `not_found` (first candidate rejected by its blockers), while the supplied sequence verifies Yes; `backend_observation` `discovery_missed_verified_plan` | clearing a block before taking it | Fable |
| 2026-09-29 | new plan_take_then_put_in | none | a put_in rule that needs holding; take, then put_in | put_in inside a plan | Fable |
| 2026-09-29 | new plan_two_travellers | none | one goal about two people; two moves in either order | a plan with two actors | Fable |
| 2026-09-29 | new plan_two_objects_one_tool | none | one goal about two objects painted with one brush; two changes in either order | a conjunctive goal over two objects | Fable |

## Amendments for round 4 after the v5 run: 2026-09-29 (Opus)

Source of every decision: Fable's `memos/MEMO_2026_09_29_round4_recommendations_fable.md`, which follows Sol's two
reviews where they differ. The rows change one fixture case file, move the eight staged texts into the example
corpus, and add one text and one prompt example. The edit script for the examples is
`elogs/round4_2026_09_29/edit_examples_h.py` (run against the kept revision-G file
`elogs/round4_2026_09_29/prompts_revision_G/examples.json`); the cohort script is `make_cohort_v6.py`. The GK
confirmation of every cohort expectation is `elogs/round4_2026_09_29/gold_gk_v6.log` (61 of 63: the tower at its
known search limit, and plan_unstack_then_take at its recorded discovery miss, each with its backend label), and the
paired T1 control is `controls_gk_v6.log` (without the air route: `not_found`). No compiled source or question of the
54 v5 texts changed. No model call.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-29 | fixture x03_partial_effects Q3 ("After Ann presses the switch twice, is the lamp off?") and variant lamp_on Q2 | answer Yes | `unsupported_backend_requirement` (`negative_persistence_unavailable`), backend requirement `negative_persistence`, `on_validated_backend` answer Yes; the old record is kept in `elogs/round4_2026_09_29/x03_partial_effects_before_R2.json` | R2: the verification now reads its final formula in both polarities. The No side needs -off(lamp) carried across a step that writes off only under a condition, and the starting backend has no negative frame. The Yes answers were correct; the conservative rule refuses them before any launch. An answer-time rule that refuses only when the positive obligation fails would keep them; it is not implemented | Fable and Sol (R2), Opus (the amendment) |
| 2026-09-29 | the eight staged texts (plan_route_dead_end, plan_travel_then_paint, plan_order_by_side_effect, plan_precondition_other_object, plan_unstack_then_take, plan_take_then_put_in, plan_two_travellers, plan_two_objects_one_tool) | staged in `tests/action_route/staged/planning_examples_round4.json` | in `prompts/actions/draft_v1/examples.json` with `"prompt": false`; their answer expectations and backend observations in `tests/action_route/v6/cohort.json` (group new); plan_travel_then_paint, plan_order_by_side_effect and plan_precondition_other_object also get a gold-Stage-1 diagnostic row | the memo's cohort v6; Sol's suggested diagnostics (a location condition, a removed property, a condition on another object) | Fable, Sol |
| 2026-09-29 | plan_unstack_then_take | `backend_observation` `discovery_missed_verified_plan` | the cohort's `known_backend_limitation` `discovery_missed_verified_plan`; a row gets that attribution only when an answer is `not_found` and its translation equals the gold up to renaming (S4) | the cause inside GK discovery is not established; otherwise the row may be a translation failure | Sol (S4) |
| 2026-09-29 | new drone_rule_air_route (T1) | none | "Zip is a drone. Zip is at Tartu. An air route goes from Tartu to Tallinn. Every drone can travel by air. Can Zip eventually be at Tallinn?": S4 binds the actor and both endpoints with forall outside its condition, compiles to `tpl_move_public` and reads the stated air route S3; the one-step plan by air; without the route no plan (paired control) | the P1 form with other words than the prompt example; Zip is no person, so only the stated rule licenses the move | Fable (T1), Opus (the gold) |
| 2026-09-29 | new prompt example movement_rule_without_endpoints | none | prompt material only, not measured: "Rex is a rover. ... Every rover can travel by taxi. Can Rex eventually be at Southport?" with the rule `["forall","A",["forall","F",["forall","T",["implies",["isa","rover","A"],["can","A",["move","A","F","T","taxi"]]]]]]`; nouns that no measured text uses | P1: both models wrote `move(X, unspecified, unspecified, bus)` in v5 | Fable (P1) |
| 2026-09-29 | T2, the original N7 wording of negative_persistence ("is the egg raw?") | an offline observation: the requirement analysis read the literal positively and the query was ready | an offline control in `check_action_round4.py`: `unsupported_backend_requirement` with 0 planned launches; no cohort row | R2 | Sol (T2 as a control) |

## Amendments of 2026-09-30: the controller batch (Opus)

Source of the decision: Fable's `memos/MEMO_2026_09_30_v6_run_analysis_fable.md`, section 5.4 and item B4, which
the user asked to implement. No model call, no GK launch.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-30 | fixture x03_partial_effects Q3 and variant lamp_on Q2 | `unsupported_backend_requirement` (`negative_persistence_unavailable`) before any launch, `on_validated_backend` answer Yes | answer Yes; the backend requirement `negative_persistence` stays, with `polarities` `["negative"]`; the query runs, and the answer policy keeps a Yes and refuses every other answer. The round-4 file is kept as `elogs/controller_batch_2026_09_30/x03_partial_effects_round4.json`, the file before round 4 as `elogs/round4_2026_09_29/x03_partial_effects_before_R2.json` | only the negative obligation of the final formula reads the carried negative; a Yes needs none. The round-4 rule refused the correct Yes answers | Fable (B4), Opus (the amendment) |

## Amendments of 2026-09-30: the answer text of the planning test set (Opus)

Source: Fable's `memos/TASK_2026_09_30_planning_test_set_opus.md`, section 3.3 (T3) and phase 1. The renderer's
sentence starts with a capital letter, and a repeated actor is left out. No model call, no GK launch. The previous
files are kept as `elogs/planning_testset_2026_09_30/x01_identity_before_render.json` and
`x02_open_values_before_render.json`.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-30 | fixture x01_identity:introduced_actor Q1 `render` | `the cook whisks the egg` | `The cook whisks the egg` | T3: a plan sentence starts with a capital letter | Fable (T3), Opus (the amendment) |
| 2026-09-30 | fixture x02_open_values Q1 `render` | `Zed frobs the gronk with the flim, then Zed zaps the gronk with the flim` | `Zed frobs the gronk with the flim, then zaps the gronk with the flim` | the renderer's rule leaves out a repeated actor, as p03's gold does; the check had carried this row as a known difference | Opus |


## Amendments of 2026-09-30: the planning test set, version 1.1, and prompt revision I (Opus)

Source of every decision: Fable's `memos/TASK_2026_09_30_planning_fixes_opus.md`, which follows Sol's review where
it differs from Fable's two memos (the task's section 10), and the user's decisions in its section 1. Sol reads these
rows, the new rows and revision I before the next run (the task's step 6). The previous files are kept in
`elogs/planning_fixes_2026_09_30/`: `c11_method_collision_before_T1.json`, `c13_uncertain_scoped_route_before_T2.json`,
`planning_rows_v1.json` and `prompts_revision_H/`. The nine new golds were first built by
`elogs/planning_fixes_2026_09_30/make_gold_v11.py` (local provenance) into `tests/action_route/planning_gold.json`,
which is the maintained source from then on (Sol's review): a later change is made in that file, with a row here. The
seven new prompt examples were built by `make_examples_i.py` into `prompts/actions/draft_v1/examples.json`. The GK confirmation of every row of the set is `gold_gk_v11.log`, of the new prompt
examples `examples_gk_i.log`. No model call.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-30 | fixture c11_method_collision:tools_distinguish S2 to S5, Stage 1 | the role `instrument` for "in the pot", "in the pan" | the role `location`, as in the gold of row 61 (worked_p03_food); Stage 2 unchanged | T1: the renderer writes "in" for a location tool; row 52 now expects "Plan: Ann fries the egg in the pan." | Fable (T1), Opus (the amendment) |
| 2026-09-30 | fixture c13_uncertain_scoped_route:probably_not_available S3 and Q2 | the availability with @p 0.3 (Stage-1 confidence 0.3), `unsupported_confidence_form`; Q2 forbids Yes and No | the denial `not can(Robo, move(...))` with @p 0.8 (Stage-1 confidence 0.8), scope denial, compile supported; Q2 answer No, forbidden answers Yes | T2: "Robo can probably not go" is a probable denial; the answer text is `Probably no.`, and row 96 also lists the Cannot answer of the unsupported availability reading | user and Sol (T2), Opus (the amendment) |
| 2026-09-30 | new planning gold explicit_markers_stable (row 101) and explicit_markers_red (row 102) | none | c16's text with "Initially, every block on the table is red" and "Whenever a block is on the table, it is stable"; c16's Stage 2 (initial description, `state_law`); stable Unknown, red Yes | T4: the explicit partner of row 32 | Fable and Sol (T4), Opus (the gold) |
| 2026-09-30 | new planning gold licence_result_stated_verify (row 103) and licence_result_stated_plan (row 104) | none | c02's text with "After Ann obtains a licence, Ann is licensed." as the effect `after(change(Ann, Ann, licensed, unspecified), licensed(Ann))`; Q2 Yes; Q1 keeps c02's expectation (the backend refusal, `on_validated_backend` the two-step plan) and the known limit negative_persistence | T5: paired variants of rows 30 and 73 that state the result of obtaining a licence | Sol (T5), Opus (the gold) |
| 2026-09-30 | new planning gold explicit_root_w0 (row 105) | none | row 4's text with "Starting from snapshot W0, is Mira at Harbor?" (`planning_root` W0): Yes | T6, convention 1: the last named snapshot is the default root; an explicit selection reads the other snapshot | Sol (T6), Opus (the gold) |
| 2026-09-30 | new planning gold permitted_first_step (row 106) | none | row 26's text with "Robo can paint the gate green with the brush.": Yes | T6, convention 2: a supplied sequence is verified step by step; the denied step of row 26 gives No | Sol (T6), Opus (the gold) |
| 2026-09-30 | new planning gold stated_permission_with_effect (row 107) | none | row 54's text with "Robo has the pan. Robo can cook the egg in the pan.": the permission `change(Robo, egg, cooked, pan)` (the participle, Q4), the effect's action the same term; the one-step plan | T6, convention 3: an effect grants no permission (row 54) | Sol (T6), Opus (the gold) |
| 2026-09-30 | new planning gold person_public_route (row 108) | none | row 82's text with "Mira is a person.": the one-step plan by bus, reachable Yes | T6, convention 4: only a person moves by a public service without a stated rule (rows 82, 83) | Sol (T6), Opus (the gold) |
| 2026-09-30 | new planning gold cup_is_no_ticket (row 109) | none | row 57's text (c10:neither) with "Robo has a cup.": no plan | T7: a translation that lost the class of the ticket gives a plan here | Fable (T7), Opus (the gold) |
| 2026-09-30 | row 99, the listed plans | "Plan: Ann bakes a cake." | also "Plan: Ann bakes a cake from the flour.", the sentence the renderer gives for the text's roles (target cake, source flour) | T8 | Fable (T8), Opus |
| 2026-09-30 | rows 87 and 88 | `Yes (0.98).`, `Yes (0.6).` | row 87 `True`, row 88 `"Probably yes."`, the values the build derives from the reviewed expectations (0.98 is not below 0.95, 0.6 is) | T3 and A1: the confidence is a word; "Probably" below 0.95. A first build listed both forms on both rows; Fable's review (F1) found that the two rows then test nothing about the qualifier | user and Sol (T3), Fable (F1), Opus |
| 2026-09-30 | the fixture rows of the planning set | exposure unseen | exposure development | T10: prompt revision I was written after reading their first run | Fable (T10) |
| 2026-09-30 | seven new prompt examples of revision I: denial_without_endpoints, conditional_denial, state_rule_and_participle, permission_then_result, one_entity_one_id, who_question_ask, permission_without_actor | none | in `prompts/actions/draft_v1/examples.json` with `"prompt": true`, nouns that no test row, no v6 cohort text and no draft contrast uses; each compiles as its `expect` says | Q1 to Q10 and the state-rule convention (section 7 of the task) | Fable and Sol (Q1 to Q10), Opus (the examples) |

## Amendments of 2026-09-30: the contrast texts of prompt revision I (Opus)

Source: section 8.2 of `memos/TASK_2026_09_30_planning_fixes_opus.md`, Fable's replacement nouns (review F3) and
Sol's review of the repairs. The seventeen golds are in `tests/action_route/planning_gold.json` (task
"contrast ..."), first built by `elogs/planning_fixes_2026_09_30/make_contrasts.py`; the rows are the part
`contrasts` of `planning_rows.json`, built into `tests/tests_planning_contrasts.py`. Each gold passes the controller
unchanged; the GK confirmation is `contrasts_gk.log` (17 of 17, 54 launches). No model call.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-09-30 | contrasts 1 and 2 (minor_denied_plane, adult_not_denied_plane) | none | "Minors cannot take the plane" as a denial without endpoints; No for the minor, Yes for the adult (a person on the public service) | Q1, Q2 and their contrast | Fable (texts), Opus (golds) |
| 2026-09-30 | contrast 3 (uninsured_driver_denied) | none | the denial with the condition "not insured"; No | Q1 | Fable, Opus |
| 2026-09-30 | contrasts 4 and 5 (crawler_unless_uncharged, crawler_unless_charged) | none | "cannot unless it is charged" as a restriction beside the crawler rule; Unknown, and with "Brix is charged." Yes with the one-step plan | the contrast of K1; the nouns of review F3 (the draft reused a prompt example's nouns) | Fable, Opus |
| 2026-09-30 | contrasts 6 and 7 (steam_same_term, steam_other_tool) | none | the permission's term with the pot in the effect and the step; with "in the pan" the step has another term: Yes and Unknown. Both texts say "Ola has a pot and a pan.": the draft named the pan only in the question, where it is no entity of the source | Q5, K5 and the contrast | Fable, Opus (the declared pan) |
| 2026-09-30 | contrast 8 (glaze_state_rule) | none | "If the vase is glazed, the vase is finished" as a standing rule about one object; the one-step plan | Q3 and the convention's rule 2 | Fable, Sol (rule 2), Opus |
| 2026-09-30 | contrasts 9 and 10 (whenever_steady, initially_green) | none | "Whenever" gives a standing rule (Unknown after the take), "Initially" a description of the start (Yes) | 7.1 | Fable, Opus |
| 2026-09-30 | contrast 11 (hone_participle) | none | the value honed, the past participle; the one-step plan | Q4; the nouns of review F3 | Fable, Opus |
| 2026-09-30 | contrast 12 (permission_then_open) | none | two units from one sentence: the permission with its condition and the effect; the plan "Noa unlocks the gate with the key" | Q6 | Fable, Opus |
| 2026-09-30 | contrast 13 (who_drills) | none | ask over executable with the actor variable; Lea | Q10, K4 | Fable, Opus |
| 2026-09-30 | contrast 14 (plank_can_be_sanded) | none | exists over can; Cannot answer (existential_availability_head) | Q10, K8 | Fable, Opus |
| 2026-09-30 | contrasts 15 and 16 (kim_by_train, lee_denied_train) | none | "take the train" as a move by train under a default permission and a named denial; the plan for Kim, no plan for Lee | Q2 and the contrast | Fable, Opus |
| 2026-09-30 | contrast 17 (if_rule_strict_ready) | none | an unqualified if-rule between states as a strict standing rule; Yes | Q8 | Fable, Opus |

## Amendments of 2026-10-02: the contrast run and version 1.2 of the planning set (Opus)

Frozen contrast measurement (`testresults/old/planning_contrasts_actions_2026_09_30`, freeze
`elogs/planning_fixes_2026_09_30/contrast_freeze.json`): 67 of 68 correct. The wrong one was gpt's contrast 9, where
Stage 2 wrote the Stage-1 strict_rule "Whenever a block is on the table, that block is steady" as a description. The
controller repair K16 (`action_repair._standing`, strict rules only) makes such a dependency a standing rule.
Post-run K16 cache replay: 68 of 68 correct. No gold changed. 32 of the 68 accepted translations differ from the gold;
the memo `memos/MEMO_2026_09_30_planning_fixes_opus.md` (section 12.3) separates packaging differences from semantic
deviations and tests these deviations with controls. The golds stay.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-10-02 | rows 110 to 126 of `tests/tests_planning.py` | none | the 17 contrast texts with their golds (`planning_gold.json`), exposure development; the set becomes version 1.2, 126 rows | the task: after their run the contrast texts join the test set | Fable (the task), Opus |

## Amendments of 2026-10-04: the action route on GK 1.0.11 (Opus)

The action route now runs on the installed prover, GK 1.0.11 (`../gk/gk`, the same binary as `/opt/gk/gk` and the
gkreasoner release), with the A6.3 strategy, in place of the experimental build `gk_ctxtworld` with
`weight_ctxt_world`. On the 262 gold queries of the fixtures both give 251 of 254 scored queries ok, with the same
three failures (c29 Q2, the four-step tower, x07 Q1); on the gold translations of the planning set, GK 1.0.11 also
finds row 69's plan (`elogs/gk_build_comparison_2026_10_03/`). No gold changed; the planning set's known limit of row
69 is removed, and the set becomes version 1.3.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-10-04 | row 69 of `tests/tests_planning.py` | known limit `gk_discovery` | no known limit | GK 1.0.11 with A6.3 finds the gold plan | the user (the switch), Opus |

## Amendment of 2026-10-04: the authored examples split by role (Opus)

No gold changed. The authored examples that no prompt shows (the records with `"prompt": false`) moved from
`prompts/actions/examples.json` and `prompts/actions/routing_cases.json` to `tests/action_route/unseen/`, in files of
the same names. The field `prompt` is removed from every record; the directory decides what a prompt shows. The
assembled prompts are unchanged.

| date | example / unit | old | new | reason | decided by |
|---|---|---|---|---|---|
| 2026-10-04 | the 52 examples and 8 routing contrasts with `"prompt": false` | in `prompts/actions/` | in `tests/action_route/unseen/` | prompt material and test material in separate places | the user, Opus |
