GK Examples
===========

This folder contains examples organized by category. All examples
use JSON-LD-LOGIC format and work with gk directly.

Run any example with:

    ./gk Examples/core/grandfather.js

For the input format reference, see `../Doc/input_languages.md`.
A tutorial based on the current example set is in the
[gkreasoner repository](https://github.com/tammet/gkreasoner/tree/main/Examples).


Core Examples
-------------

Basic classical logic: facts, rules, queries, and answer predicates.
No confidence values or default rules.

    core/grandfather.js
        Rules and inference. A grandfather rule derives grandfather(john,mark)
        from father(john,pete) and father(pete,mark). Shows rule application
        with confidence propagation (min of premises).

        ./gk Examples/core/grandfather.js

    core/grandfather_equality.js
        Same as grandfather but using equality (father(john)=pete) instead of
        a binary predicate. Demonstrates paramodulation.

    core/grandfather_arc.js
        Grandfather reasoning using JSON-LD $arc triples:
        $arc(X, father, Y) instead of father(X,Y).

    core/grandfather_jsonld.js
        Grandfather using full JSON-LD object notation:
        {"@id":"pete", "father":"john"} style input.

    core/algebra.js
        Abstract algebra: proves m(e,X)=X from algebraic axioms
        using equality reasoning (paramodulation).

    core/algebra_confidence.js
        Same algebra problem with a low-confidence rule, demonstrating
        that equality reasoning works with confidence values.

    core/equality.js
        Basic equality and function reasoning.

    core/lists.js
        List operations: counting elements with $list, $first, $rest,
        and computing sums.

    core/negation.js
        Negation in queries: finding what is NOT true.

    core/negation_conflict.js
        Conflicting facts: positive and negative evidence for the same
        predicate, showing how gk handles contradictions.

    core/logic_chain.js
        A chain of logical implications, testing multi-step derivation.

    core/jsonld_context.js
        JSON-LD @context and @base for URI expansion. Demonstrates
        semantic web compatibility.

    core/named_graphs.js
        JSON-LD named graphs with @graph key.

    core/multiple_graphs.js
        Multiple named graphs with $narc (named arc) triples.


Confidence Examples
-------------------

Problems using @confidence values for uncertain reasoning. GK computes
positive and negative evidence and cumulates confidence from multiple
independent proofs.

### Basic confidence

    confidences/conf1.js
        Multiple facts about the same predicate with different confidences
        (positive: 0.6, 0.5; negative: 0.9, 0.2). Shows cumulation
        of evidence and positive-minus-negative calculation.

        ./gk Examples/confidences/conf1.js

    confidences/conf2.js
        Named axioms with confidences. Similar to conf1 but with
        @name annotations.

    confidences/conf3.js
        Conflicting facts with five confidence values, testing
        how multiple sources of evidence interact.

    confidences/conf4.js
        Two probabilistic facts (coin tosses at 50% and 60%).

### Probabilistic reasoning (coin/alarm problems)

    confidences/coin1.js
        Single coin flip with confidence propagation.

    confidences/coin2.js
        Two independent coin flips.

    confidences/coin3.js
        Existential generalization with probabilistic rules.

    confidences/coin4.js
        Multiple coins with confidence propagation chains.

    confidences/coin4_err.js, coin4_err1.js, coin4_err2.js
        Edge cases in probability handling.

    confidences/alarm.js
        Bayesian-style burglary/earthquake alarm problem.
        Inspired by the classic Pearl example.

        ./gk Examples/confidences/alarm.js

    confidences/alarm_v1.js, alarm_v2.js
        Alarm problem variants with different confidence configurations.

### Rules with confidence

    confidences/rules1.js - rules5.js
        Progressive examples of rules with different confidence values:
        conflicting rules (rules1), multiple rules for same predicate
        (rules2), simple inference (rules3), nested inference (rules4),
        recursive predicates (rules5).

    confidences/equality1.js - equality3.js
        Equality reasoning combined with confidence values.

### Smoking/social examples

    confidences/smokes.js
        Probabilistic smoking: stress causes smoking with 80% confidence,
        influences propagation.

        ./gk Examples/confidences/smokes.js

    confidences/smokes2.js
        Variant with different confidence values.

    confidences/smokes_alchemy.js
        Smoking example in Alchemy/Markov Logic Network style.

    confidences/socialsmoking.js
        Social network smoking propagation with confidences.

    confidences/socialsmoking2.js
        Extended social smoking example.

### Cumulation and evidence

    confidences/cumulate.js
        Multiple proofs of the same fact from independent sources.
        Demonstrates confidence cumulation formula.

        ./gk Examples/confidences/cumulate.js

    confidences/rulemult.js
        Basic confidence multiplication through rules. Two facts
        with confidences 0.5 and 0.6 combined via a rule give 0.3.
        (From the "Confidences for commonsense reasoning" paper, CADE 2021.)

    confidences/n1.js - n3.js
        Various patterns of positive and negative evidence interaction.

    confidences/n2a.js, n2c.js, n2plus.js
        Extended evidence interaction patterns.

### Transitive chains

    confidences/near.js
        Confidence decay through a transitive chain of 10 objects.
        Each transitivity step multiplies confidence by 0.9.

        ./gk Examples/confidences/near.js

    confidences/near2.js
        Same as near.js but using nested function symbols
        (["f", ...]) instead of named constants.

### Comparison studies (vs ProbLog, Alchemy)

23 comparison studies against ProbLog2 and Alchemy 2 form the experimental
basis for the "Confidences for commonsense reasoning" paper (CADE 2021).
They are described and downloadable at https://logictools.org/confer/.


Exception Examples
------------------

Default rules with $block mechanism for defeasible reasoning.
Rules can be overridden by more specific exceptions.

### Basic defaults

    exceptions/trivial.js
        Simplest possible default rule example.

        ./gk Examples/exceptions/trivial.js

    exceptions/bird_default.js
        "Birds fly" as a default rule with $block.

    exceptions/bird_exception.js
        "Birds fly, but this specific bird doesn't" — a single exception
        to a default rule.

    exceptions/bird_penguin.js
        The classic example: birds fly (strength 1), penguins don't fly
        (strength 2). The penguin exception overrides the bird default.

        ./gk Examples/exceptions/bird_penguin.js

    exceptions/bird_hierarchy.js
        Three-level hierarchy: objects, birds, penguins, with cascading
        defaults at different strengths.

    exceptions/hierarchy.js
        Object/bird/penguin hierarchy with integer-based strengths
        and multiple properties.

### Classification

    exceptions/classify.js
        Classification with default rules. Demonstrates how $block
        is used to classify entities into categories.
        Uses taxonomy-based priorities (see the taxonomy section below).

        ./gk Examples/exceptions/classify.js -taxonomy -datafolder Examples/exceptions

    exceptions/kingqueen.js
        Simple type rules (king/queen classification).

### Competing defaults (Nixon diamond)

    exceptions/nixon.js
        The Nixon diamond: "Quakers are pacifists" vs "Republicans are
        not pacifists" with equal strength. Neither default wins: GK
        reports the opposition with a zero margin.
        Expected result: "evidence below limit" at confidence 0.

        ./gk Examples/exceptions/nixon.js

    exceptions/nixon_taxonomy.js
        Nixon diamond using taxonomy-based strengths. Both defaults
        are incomparable in the taxonomy, so neither wins.
        Expected result: "evidence below limit" at confidence 0.
        Uses taxonomy-based priorities (see the taxonomy section below).

### Penguin variants

    exceptions/penguin.js
        Full penguin/bird example with confidence values and blocking.

    exceptions/penguin2.js
        Deep taxonomy: flyingpenguin > penguin > bird > organism,
        each with different flying defaults at integer priorities.

    exceptions/penguin3.js
        Same as penguin2 but using taxonomy-based $block priorities
        like ["$","penguin",3].
        Uses taxonomy-based priorities (see the taxonomy section below).

    exceptions/penguin4.js
        Whether a grandfather of a penguin can fly. Uses nested function
        symbols (father(father(p))) and biconditional rules.
        Uses taxonomy-based priorities (see the taxonomy section below).

### Situation calculus (frame problem)

    exceptions/people_room.js
        Story encoding: "A man entered a room containing a table.
        He wore a black suit. Then the man left the room."
        Models situations, events, and default persistence (frame axioms).
        Question: in which situations is there NOT a man in the room?
        Uses taxonomy-based priorities (see the taxonomy section below).

        ./gk Examples/exceptions/people_room.js -taxonomy -datafolder Examples/exceptions

### Part-capability reasoning

These examples explore how to encode "if a class has a component used
for some capability, then an instance without that component lacks
that capability" (e.g., birds without wings cannot fly).
(From the "GK: implementing full first order default logic" paper, IJCAR 2022.)
partcapability1 and partcapability2 use taxonomy-based priorities and
require the taxonomy flags (see the taxonomy section below).

    exceptions/partcapability1.js
        Same priority for "birds have wings" and "birds can fly" leads
        to unstable results. Demonstrates a problem case.

    exceptions/partcapability2.js
        Fix via priority differentiation: wings get sub-priority 20,
        flying gets sub-priority 10. Yields stable results.

    exceptions/partcapability3.js
        Alternative fix: split rules into class-level (no exception)
        and instance-level (exception allowed via $block).

### ASP comparison examples

These demonstrate gk's advantages over Answer Set Programming systems
(clingo, dlv, s(CASP)): gk handles function symbols and scales to
large constant sets. See https://logictools.org/gk/ for timing comparisons.
(From the "GK: implementing full first order default logic" paper, IJCAR 2022.)

    exceptions/gbirds.js
        Baseline birds-fly/penguins-don't.

    exceptions/gbirds_funsymbs.js
        Same with function symbols added. ASP systems cannot handle this.

### Taxonomy-dependent examples

Examples using taxonomy-based $block strengths (["$","bird"] instead of
integer strengths) require the `-taxonomy` flag (`-defaults` is an
accepted synonym) with the taxonomy data files:

    ./gk Examples/exceptions/taxonomy.js -taxonomy -datafolder Examples/exceptions

Running such an example without the flag is an error.  The examples in
this folder that need it: classify.js, nixon_taxonomy.js, penguin3.js,
penguin4.js, people_room.js, partcapability1.js, partcapability2.js,
taxonomy.js.

    exceptions/taxonomy.js
        Bird/penguin/object hierarchy with taxonomy-based default comparison.

    exceptions/nixon_taxonomy.js
        Nixon diamond with taxonomy-based strengths.

The taxonomy data files (`gk_name_number.txt` and `gk_taxonomy_packed.txt`)
are included in this folder.


Strategy Examples
-----------------

Strategy files control proof search. Pass them with `-strategy`:

    ./gk Examples/core/grandfather.js -strategy Examples/strategy/runs.txt

See also: `../Doc/strategy_reference.md`.

    strategy/runs.txt
        Comprehensive multi-run strategy with 63 sequential runs combining
        different strategies (negative_pref, unit, query_focus, positive_pref,
        double, triple), query preferences (0-3), and depth limits (1-4).

    strategy/query_focus.txt
        Single-strategy: query_focus with query_preference 1.

    strategy/negative_pref.txt
        Single-strategy: negative_pref with query_preference 0.

    strategy/basic.txt
        Basic negative_pref strategy.

    strategy/strat_small.js, strat_large.js
        Strategy configurations in JSON-LD-LOGIC format for small
        and large knowledge bases.


