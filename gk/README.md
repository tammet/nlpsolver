GK in nlpsolver
===============

This folder contains the Linux GK binary and taxonomy data used by the
nlpsolver pipelines (llmpipe and udppipe). GK proves first-order queries
over facts, rules, uncertain statements, defaults, exceptions, and
explicit contradictions. It returns answers, proofs, and confidence
information.

Binaries for other platforms, current documentation, and complete
examples are in the [gkreasoner
repository](https://github.com/tammet/gkreasoner). A browser version is
available at [logictools.org/commonsense.html](https://logictools.org/commonsense.html).


Folder contents
---------------

    gk                        Linux x86-64 binary (statically linked)
    gk_name_number.txt        taxonomy data: name -> number table
    gk_taxonomy_packed.txt    taxonomy data: packed parent graph
    Doc/                      reference copies of the main GK documents
    Examples/                 example problems


Pipeline invocation
-------------------

llmpipe calls the binary as a subprocess (`solver/prover.py`, paths in
`solver/globals.py`). From the `llmpipe/` directory the command has the
shape:

    ../gk/gk axioms_std.js [strategy and time options] INPUT \
      -taxonomy -confidence 0.1 -keepconfidence 0.1 \
      -datafolder ../gk

Strategy and time options vary per query.

  * `axioms_std.js` — llmpipe's background axioms, read together with
    the generated problem file.
  * `-taxonomy` — loads the `gk_*` data files from the `-datafolder`
    path for taxonomy-based default priorities. `-defaults` is an
    accepted synonym.
  * `-confidence 0.1` — minimum verdict confidence for an accepted or
    rejected answer.
  * `-keepconfidence 0.1` — discards derived clauses below the given
    confidence.

`solve.py -gkin FILE` saves the GK input and command for a separate GK
run.


GK input and output
-------------------

GK reads JSON files in JSON-LD-LOGIC format (the pipelines' native
representation); it also accepts Prolog-style GKP, GKS, and TPTP CNF
inputs. See `Doc/input_languages.md`.

    ["bird","tweety"]                                    fact
    [["bird","?:X"], "=>", ["flies","?:X"]]              rule
    {"@logic": ["bird","tweety"], "@confidence": 0.9}    confidence annotation
    {"@question": ["flies","?:X"]}                       question (free
                                                         variables collect answers)

Default rules with exceptions, shown in the GKP notation:

    bird(X)   :- penguin(X).
    -flies(X) :- penguin(X).
    flies(X)  :- bird(X), unless(-flies(X), 3).

The last rule derives `flies(X)` for a bird X unless a rule of strength
above 3 derives `-flies(X)`. Here the strict penguin rule does, so
penguins are rejected as flying. The equivalent JSON form uses a
`$block` literal; see `Doc/how_gk_works.md` and
`Examples/exceptions/`.

Output is one JSON document: a `result` string, then an `answers` list
where each answer has `answer`, `confidence` (0 to 1), any firing
`blockers`, and `positive proof` / `negative proof` step lists. GK
computes signed confidence as positive support minus negative support.
Its sign determines whether the answer is accepted or rejected; the
reported verdict confidence is its magnitude. `-detail` adds a
four-component support breakdown per answer.

Result strings: `answer found`, `evidence below limit`,
`no answers found`, `no information`, `time limit, proof not found`.

Frequently used options: `-seconds N` (time limit, default 10),
`-print N` (verbosity, default 10), `-parallel N` (concurrent search
strategies, Unix), `-rawproofs`, `-help`, `-version`. Full list:
`Doc/cli_reference.md`.


Documentation
-------------

`Doc/` contains reference copies of the main GK documents. The example
files and related material they link to are in the gkreasoner
repository.

  * `Doc/cli_reference.md` — command-line options and result strings
  * `Doc/input_languages.md` — the four input notations by example
  * `Doc/how_gk_works.md` — resolution, confidences, proof support,
    verdict calculation, contradictions, defaults
  * `Doc/strategy_reference.md` — automatic search and strategy files

In the gkreasoner repository:

  * [Overview and proof-search structure](https://github.com/tammet/gkreasoner)
  * [Examples grouped by feature](https://github.com/tammet/gkreasoner/tree/main/Examples),
    including the logic generated from English by llmpipe
  * [Comparison with other systems](https://github.com/tammet/gkreasoner/blob/main/Doc/comparison_with_other_systems.md),
    [sampling comparisons](https://github.com/tammet/gkreasoner/tree/main/montecarlo),
    and [comparison inputs and outputs](https://github.com/tammet/gkreasoner/tree/main/comparisons)


References
----------

  * T. Tammet. GKC: a reasoning system for large knowledge bases.
    CADE 2019. <https://doi.org/10.1007/978-3-030-29436-6_32>
  * T. Tammet, D. Draheim, P. Järv. Confidences for commonsense
    reasoning. CADE 2021. <https://doi.org/10.1007/978-3-030-79876-5_29>
  * T. Tammet, D. Draheim, P. Järv. GK: implementing full first order
    default logic for commonsense reasoning. IJCAR 2022.
    <https://doi.org/10.1007/978-3-031-10769-6_18>
