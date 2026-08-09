# bridge_unit — hand-written fixtures for the break-point locator

Plan step M1.2 of `memos/PLAN_2026_08_07_abstraction_initial_phases.md`.

These are the fixtures the signed clause-goal search (M5.2), the event
extraction (M5.1) and the template enumeration (M5.4) are **developed**
against. They are hand-written: no LLM call, no stored run, no regeneration.
The natural-case benchmark is a different artifact (`tests/bridge_bench/`,
built at M3.2 from reviewer-decided cases) and is used only for scoring.

Clause shapes here mirror what the converter really emits — the `$defq`
question encoding, `$ctxt` argument terms, `has type` + role event groups,
compact `event(...)`, flat `is rel2` with `eventprop` objects, `$block`
literals — copied structurally from stored result trees, not invented.

## Files

| file | covers |
|---|---|
| `search.json` | unification, signed matching, negative-conclusion clauses, `$defq` traversal, branching alternatives, cycle/depth/branch limits, `$block`, non-ground goals, argument clashes, `$ctxt` exactness |
| `events.json` | the three event encodings the pipeline can emit |
| `templates.json` | one minimal clause set per template T1–T9 |

## Record schema

```json
{
  "id": "u01_...",                 // unique, stable
  "purpose": "one line",
  "final_clauses": [ {"@name": "...", "@logic": [...]}, ... ],
  "start_goal": {"sign": "+|-", "atom": [...]},
  "expect": {
    "result": "SUPPLIED | GAPS | UNSUPPORTED | LIMITED",
    "gaps": [[{"sign": "+|-", "atom": [...], "reason": "..."}]],
    "reason": "...",
    "templates": [{"template": "T4", "direction": "...", "argument_map": {}}]
  },
  "notes": "why this fixture exists"
}
```

`gaps` is a list of **alternatives**; each alternative is the set of gaps that
would all have to be bridged together for that one derivation path. A flat gap
list cannot express this and is the reason the search returns a branch result
rather than a list.

## Contract the fixtures encode

- **Supplier test.** A clause supplies signed goal *G* iff it contains a
  literal of the **same sign and predicate** whose **complete argument list**
  unifies with *G*'s. Same predicate alone is not a supplier; `$ctxt` terms
  unify normally and are never wildcards.
- **Recursion.** If the supplying clause has other ordinary literals, their
  signed complements become subgoals under the unifier, all required together.
- **`LIMITED` and `UNSUPPORTED` are never semantic gaps.** A depth, branch,
  match-count or cycle cutoff, a `$block` clause, a multi-positive-literal
  clause or a non-ground goal is reported as such — never handed on as a
  missing bridge, or the later LLM judge would be asked to invent bridges for
  the search's own shallowness.
- **v1 scope is ground yes/no goals.** A non-ground goal is
  `UNSUPPORTED(non_ground_goal)`; it is not existentially closed, because that
  changes what is being asked.
