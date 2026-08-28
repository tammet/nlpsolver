# Compiled representations

The logical forms the compiler may submit to GK in place of, or beside, the
canonical clauses. Every shape here is produced by deterministic code, not by a
model.

The ordinary Stage-2 model never writes any of them. It writes the controlled
predicates of [stage-2.md](stage-2.md); the compiler then rewrites some of that
into the shorter forms below, and adds clauses that connect the two spellings.

Three groups:

- the **canonical neo-Davidsonian form**, which every other form is defined
  against;
- two **equivalent rewrites** the compiler attempts by default, which shorten a
  proof without changing what the theory says;
- the **selectable representations**, each of which deliberately loses or adds
  distinctions and must be asked for.

## Canonical neo-Davidsonian event form

An event is a handle with separate role atoms. Before context injection:

```text
isa(activity,E)
has type(E,V)
has actor(E,A)
has target(E,T)
```

After context injection, every role atom carries the context term as its last
argument:

```text
isa(activity,E)
has type(E,V,C)
has actor(E,A,C)
has target(E,T,C)
```

`isa` does not take the context argument. `C` is the `$ctxt` term described in
[gk-clauses.md](gk-clauses.md), or the constant `"$c"` under `-nocontext`.

Everything else about the event stays as its own atom: a recipient, a
beneficiary, a source, a location, a time, a manner, a degree, and any modal
classifier are separate role atoms on the same handle `E`. They are not part of
the spine, and no rewrite on this page moves them.

These four predicates are the interface. `axioms_std.js` is written against
them, and so is any later knowledge base. A rewrite may replace them inside one
case's theory, but only while emitting clauses that derive them back.

## Reversible compact event representation

Internal name `davidson2`; the command-line keys are `-davidson2`,
`-nodavidson2`, `-noproofshort2` and `-event davidson2`. It is attempted on the
ordinary canonical theory without being asked for.
[Proof shortening](../architecture/proof-shortening.md) explains why, and gives
the table of which command lines attempt it.

### The atom

The rewrite removes the four spine atoms and puts one atom in their place.
Before context injection:

```text
event(V,A,T,E)
```

In the GK clause list, after context injection:

```text
event(V,A,T,E,C)
```

Signed, as it appears in a clause body:

```text
-event(V,A,T,E,C)
```

The five arguments, in order: the **verb**, the **actor**, the **target**, the
**event handle**, and the **context**. The handle is the fourth argument, not
the first, because the context injector appends its argument on the right and
the handle must keep a fixed position.

### The compatibility clauses

For every concrete verb that has a compact atom in the case,
`lc_davidson2.interop_clauses` emits both directions of a strict definition.
The verb is fixed in every clause; there is no schema quantified over verbs.

Four forward clauses, named `frm_event2_def`:

```text
event(V,A,T,E,C) -> isa(activity,E)
event(V,A,T,E,C) -> has type(E,V,C)
event(V,A,T,E,C) -> has actor(E,A,C)
event(V,A,T,E,C) -> has target(E,T,C)
```

One reverse clause, named `frm_event2_def_rev`:

```text
isa(activity,E) & has type(E,V,C) & has actor(E,A,C) & has target(E,T,C)
    -> event(V,A,T,E,C)
```

The reverse clause needs the complete four-atom spine, on the same handle, with
the same context, and the actor and target in their own places. An incomplete or
swapped role set therefore mints no compact atom.

One optional projection, named `frm_event2_rel2`, emitted only for a verb the
same case also uses as a plain three-argument relation, and only in that
direction:

```text
event(V,A,T,E,C) -> is rel2(V,A,T,C)
```

### What is preserved

The actor, the target, the event handle, the verb, the sign, the binders and
the context all survive the rewrite unchanged. Adjuncts stay as separate atoms
on the same handle.

Every accepted rewrite is checked by expanding the compact atom back to the
four spine atoms and comparing the result with the source formula
(`lc_davidson2.round_trip_ok`). A group that fails the comparison stays
reified.

### When it declines

A refusal is local: one declined event does not stop another from being
rewritten. Each is recorded with its reason.

| reason | what it means |
|---|---|
| `no_event` | the block introduces no `isa(activity,E)` |
| `content_event` | the handle is the inner content event of a reified attitude or speech act |
| `missing_actor` | no `has actor` on the handle, or the actor does not occur in the block |
| `missing_target` | no `has target` on the handle, or the target does not occur in the block |
| `multiple_role` | the same role occurs more than once on the handle |
| `abstract_verb` | the verb is a variable rather than a concrete name |
| `spine_arity` | a spine atom has a nonstandard number of arguments |
| `binder_scope` | a participant's binder does not enclose the whole group |
| `round_trip_mismatch` | expanding the compact atom back does not reproduce the source |

The rewrite never replaces a participant by its class, never invents a missing
actor or target, and never accepts a goal or a topic in the target slot. Those
are the three behaviours of the legacy `-event davidson` fold that it does not
have.

### In a proof

A compact atom may appear in the formal proof, and the English proof is
rendered from it. A step that converts between the compact atom and the
canonical spine reads `[representation conversion]` and is never listed under
`Knowledge used:`, because it states no fact about the world.

## Repeated part-witness representation

Internal name `existfold2`; the command-line keys are `-existfold2`,
`-noexistfold2` and `-noproofshort2`. It too is attempted by default.

### The pattern

One rewrite, in both directions:

```text
exists Y. isa(C,Y) & has part(X,Y,Ct)
    <->
has property([$has_part,C],X,Ct)
```

`C` is a class label, `X` the possessor, and `Ct` the context. `$has_part` is a
tag, so the summary property is a compound term `[$has_part, C]` rather than a
name that could collide with a word from the passage.

### The witness

The reverse direction needs a witness for `Y`. It uses a function of the
possessor and the class:

```text
$typed_partof(X,C)
```

Every consumer of the same `(X, C)` therefore shares one witness. That is the
point of the rewrite. A theory saying "an animal with legs jumps", "a
terricolous animal has legs" and "KiKi is terricolous" mints one Skolem witness
per occurrence, and the prover pairs them all; a shared witness removes the
cross product. The `$` prefix keeps the term out of vocabulary extraction and
out of ordinary answers.

### The compatibility clauses

`lc_existfold_v2.bridge_clauses` emits exactly three clauses per activated
class, with the class fixed:

```text
frm_existfold2      has property([$has_part,C],X,Ct) -> isa(C, $typed_partof(X,C))
frm_existfold2      has property([$has_part,C],X,Ct) -> has part(X, $typed_partof(X,C), Ct)
frm_existfold2_rev  isa(C,Y) & has part(X,Y,Ct)      -> has property([$has_part,C],X,Ct)
```

### Eligibility

The rewrite accepts the bare two-atom pattern only:

- the existential binds exactly one variable `Y`;
- its body is an `and` of exactly two conjuncts;
- one is `isa(C,Y)` and the other is `has part(X,Y,...)`;
- `Y` occurs in those two atoms and nowhere else;
- `C` is a concrete class label, not a variable and not a `$` or `#:` term.

A near miss is recorded with its reason.

| reason | what it means |
|---|---|
| `extra_conjunct` | the existential holds more than the two atoms |
| `class_not_a_label` | the class is a variable, or a `$` or `#:` term |
| `isa_arity` | the `isa` atom has the wrong number of arguments |
| `witness_used_elsewhere` | `Y` also occurs outside the two atoms |
| `equivalence_mismatch` | the class is active, but expanding the summary back does not reproduce this occurrence (`equivalence_ok`) |

The last one is the same check the compact event rewrite makes: an accepted
rewrite must expand back to what it replaced.

**The threshold is four occurrences.** Exact compatibility costs three clauses
for a class, so a class is rewritten only when the pattern occurs at least
`lc_existfold_v2.MIN_OCCURRENCES` times. Below that the clauses cost more than
the rewrite saves.

**`have` is excluded.** The legacy `-existfold` also folds `have`, which covers
ownership, kinship and plain attribution. Those readings already interact with
other axioms, so folding them changes what the theory proves. This rewrite folds
`has part` only.

## Other selectable representations

Each must be asked for, and each is described in
[abstraction](../architecture/abstraction.md) with its algorithm and in
[mechanism experiments](../mechanisms/README.md) with its evidence. The
option keys are listed in
[experimental options](../reference/experimental-options.md).

| option | resulting shape | reversible |
|---|---|---|
| none, the default | the canonical spine above, with the two rewrites attempted | the rewrites are; the spine is the reference |
| `-event davidson` | compact `event(V,A,O,E)` keeping the handle and adjuncts, but replacing a typed existential participant by its class, minting a value for a missing role, and accepting a goal or topic in the object slot | no: a participant and its modifiers can be lost |
| `-event flat` | `is_rel2(V, subject, object)`, a bare positional object; a subject-only event becomes a unary property | no: the handle and every adjunct are dropped |
| `-event flatroles` | `is_rel2(V, subject, ["eventprop", role, value])`, the object slot role-tagged | no, as above, but the role name survives |
| `-existfold` | `has_property([$has_part,C],X)` or `[$have,C]`, with a named-witness bridge and clauses quantified over the class | intended as reversible, but it also folds `have` and floats extra conjuncts |
| `-entitymerge` | proper-noun constants naming one entity are merged | adds an identity the text did not state |
| `-typeenrich[=GATES]` | extra `isa` facts from Stage-1 categories, names, genders and compounds | adds facts |
| `-guarddrop` | antecedent `isa` guards judged vacuous or redundant are removed | removes conditions |
| `-bridges` | frame axioms between relation and event, occasion and location, containment and part | adds implications |
| `-propclass`, `-numtype`, `-compasym` | bridges between property and class, numeral typing, comparative antisymmetry | each adds clauses |
| `-simpleprops`, `-nocontext`, `-noexceptions` | degree arguments, the context term and `$block` defeaters removed | each removes information |
| `-abstract`, `-abstract-roles`, `-abstract-max` | presets combining the above | no |

The separate open-relation graph translation is not in this table because it is
not a compiler rewrite of the ordinary Stage 2: it is a second model
translation with its own atom contract. See [graph-format.md](graph-format.md).

## Related documentation

- [Encoding reference](README.md)
- [Stage 2](stage-2.md) — what the model writes
- [GK clause list](gk-clauses.md) — the clause format and the context term
- [Proof shortening](../architecture/proof-shortening.md) — when each rewrite is attempted
- [Abstraction](../architecture/abstraction.md) — the selectable representations
- [Compilation transformations](../architecture/compilation-transformations.md) — every named rewrite
