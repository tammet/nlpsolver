# Proof shortening

The compiler attempts two rewrites on the ordinary canonical theory without
being asked for them. Each replaces a group of atoms by one shorter atom, so
the prover has less to pair up and the resulting proof has fewer steps.

- **Reversible event compression**, `davidson2` in the code and on the command
  line.
- **Repeated part-witness compression**, `existfold2` in the code and on the
  command line.

Both are guarded and exactly reversible. Each checks its conditions at every
occurrence. When a condition fails, that occurrence is left as it was. One
declined occurrence does not stop another from being rewritten.

Neither rewrite loses or adds a distinction. That separates them from the
representations on the [abstraction](abstraction.md) page, which do.

## Reversible event compression

The canonical encoding gives an event four atoms:

```
isa(activity,E)   has type(E,V)   has actor(E,A)   has target(E,T)
```

The rewrite removes those four and puts one in their place:

```
event(V,A,T,E)
```

Everything else in the event group stays as it was. The rewrite runs before
context injection, so the context argument is appended afterwards, exactly as
it is for a reified role.

Every rewrite is checked by expanding it back to the four atoms and comparing
with the original group. A group that fails the comparison stays reified.
`lc_davidson2.round_trip_ok` performs that check, and each refusal is recorded
with its reason.

The rewrite declines in three cases where an earlier compact fold did not:

- a typed existential participant is kept as a variable with its binder, so
  "eat a big fish" does not lose the fish or its modifier;
- a missing actor or target makes the rewrite decline, rather than minting a
  value that could reach an answer;
- only a real `has target` is accepted in the compact object slot; a goal or a
  topic stays an adjunct.

## Repeated part-witness compression

The rewrite recognises one pattern:

```
exists Y. isa(C,Y) & has part(X,Y)     ->     has property([$has_part,C], X)
```

What matters is the Skolem witness the rewrite deletes. A theory saying "an
animal with legs jumps", "a terricolous animal has legs" and "KiKi is
terricolous" mints one witness per occurrence, and the prover pairs them all.
Collapsing the pattern to a unary property removes the pairing.

The rewrite is narrower than the legacy `-existfold`, which stays as it is:

- it does not fold `have`, which also covers ownership, kinship and plain
  attribution, and already interacts with other axioms;
- it accepts the bare two-atom pattern only, and does not float extra conjuncts
  out of the existential;
- it rewrites a class only when the pattern occurs at least four times, because
  exact compatibility costs three class-specific clauses. Below four
  occurrences those clauses cost more than the rewrite saves.
  `lc_existfold_v2.MIN_OCCURRENCES` holds the threshold.

## The canonical predicates stay the interface

The neo-Davidsonian role predicates remain the language of `axioms_std.js` and
of any later knowledge base. A compact atom is an internal proof-search form,
tied to the canonical spine by a strict definition in both directions
(`frm_event2_def`, `frm_event2_def_rev`) and, for the attribute rewrite, by
three class-specific clauses (`frm_existfold2`, `frm_existfold2_rev`).

A compact atom can appear in the formal proof and is the basis of the English
proof. A step that converts between the two spellings reads
`[representation conversion]` and is never listed under `Knowledge used:`.

## When each is attempted

One rule decides, applied in `EncodingConfig.__init__` after the whole command
line is read. No position on the command line matters.

| the command line | event compression | part-witness compression |
|---|---|---|
| no encoding option | on | on |
| `-event neodavidson` / `davidson` / `flat` / `flatroles` | off | off |
| `-event davidson2` | on | off |
| legacy `-existfold` | off | off |
| `-abstract`, `-abstract-roles`, `-abstract-max` | off | off |
| `-davidson2` / `-existfold2` / `-proofshort2` | requested | requested |
| `-abstract-max -proofshort2` | declines: no spine on a flat base | on |
| `-nodavidson2` | off | on |
| `-noexistfold2` | on | off |
| `-noproofshort2` | off | off |

Naming a base or a preset asks for that base's own theory, so the defaults
stand aside and every earlier run reproduces. A request turns a rewrite on from
any position. A cancellation turns it off from any position and beats both.

`-noproofshort2` reproduces the ordinary theory and answers as they stood
before 2026-08-26. Legacy `-event davidson`, legacy `-existfold` and the three
`-abstract*` presets reproduce byte-identically on their own.

## Boundaries

Graph translation and graph bridge generation use a separate representation.
`graph_compile.GRAPH_OPTION_TABLE` cancels both rewrites, so the default does
not reach that theory.

Literal bridge generation compiles against the ordinary theory stored for its
case, whatever that theory resolved to.

## Code

`solver/lc_davidson2.py` and `solver/lc_existfold_v2.py` hold the two
rewrites, and each emits its own reverse-adapter clauses.
`solver/lc_encoding.py` decides whether each is attempted.
`solver/proof_explain.py` recognises an adapter step when it renders the
English proof.

## Related documentation

- [Abstraction](abstraction.md)
- [Logic compilation](logic-compilation.md)
- [Experimental options](../reference/experimental-options.md)
- [Compiler modules](../code/logic-compilation.md)
