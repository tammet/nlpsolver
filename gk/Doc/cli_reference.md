# Command-Line Reference

The examples below use `gk` as the executable name. In this repository on
Linux, substitute `./bin/gk`.

## Invocation

```text
gk [options] file1 [file2 ...]
gk -jstext 'JSON-LD-LOGIC text' [options]
gk -readkb file [options]
gk -usekb [query-file] [options]
gk -deletekb [options]
```

With ordinary input files, GK reads all files as one problem and proves the
query they contain.

```sh
gk Examples/exceptions/penguin.gkp
gk facts.js rules.js query.js
```

## Input and output formats

### `-informat <json|prolog|tptp|simple>`

Treat all input files as the selected format. `prolog` selects GKP and
`simple` selects GKS. Without this option, GK checks recognizable content and
then the file suffix.

### `-outformat <json|prolog|tptp>`

Select the result format. Native JSON input normally produces JSON output;
GKP produces plain key-value output; TPTP produces TPTP/SZS-oriented output.

### `-jstext '<json>'`

Read JSON-LD-LOGIC directly from the command line:

```sh
gk -jstext '[["bird","tweety"],{"@question":["bird","tweety"]}]'
```

### `-writejson`

Parse the input, print its JSON-LD-LOGIC representation, and exit without
proving it.

### `-detail`

Add a `detail` block to each answer: `support_for`, `support_against`,
`conflict`, `ignorance`, the `calculation`, `coverage_status`, and
`polarity_status` fields, conflict sources, and flags. The field values are
defined in the report-status tables of
[`how_gk_works.md`](how_gk_works.md). `coverage_status: complete` means
that no covered operational failure was detected; it does not establish
that the query lies in the exact-correspondence fragment.

### `-print <n>`

Set output verbosity. The default is 10. Each band includes everything from
the bands below it; levels 0-11 print one valid JSON document, 12 and up
interleave a human-readable trace with the reports.

| Level | Content |
|---|---|
| 0-9 | answers with confidences and blockers; no proofs |
| 10 | default: answers with positive and negative proofs |
| 11 | adds the `detail` block and proof-step provenance |
| 12 | adds the high-level search trace: positive/negative searches, blocker checks with depth and time budget, brief sub-search results |
| 13-15 | adds full intermediate reports, the given-clause trace, and statistics |
| 16-20 | adds kept derived clauses with clause metadata |
| 21-30 | adds subsumed and pre-cut derived clauses and the initial clause lists |
| 31-50 | adds given candidates with resolvability, active clauses, partial derivations, and parser dumps |
| 51+ | adds literal/term selection and datastructure dumps |

### `-derived`

Print all derived clauses independently of `-print`.

## Time and memory

### `-seconds <n>`

Set the total time limit in seconds. The default is 10.

### `-mbsize <n>`

Set the initially allocated database size in megabytes. The default is 5000.
Shared-memory loading requires at least 1000 MB.

### `-parallel <n>`

Run automatic search strategies in up to `n` concurrent processes (1 to 8;
default 1). The default therefore uses one process and no parallel search.
Unix only. Completion order does not affect the result. The option has no
effect with `-strategy` or `-strategytext` and works with `-usekb`. Raw-proof
mode remains single-process.

## Answer and proof limits

### `-confidence <n>`

Set the minimum verdict confidence for an accepted or rejected answer. The
underlying signed confidence is `support_for - support_against`; the routed
verdict uses its absolute value. The default is 0.1.
The value may be a decimal from 0 to 1 or an integer percentage from 2 to 100.
Derivations below the limit are reported under `evidence below limit`.

### `-keepconfidence <n>`

Discard derived clauses below this confidence. The value uses the same decimal
or percentage forms as `-confidence`. The default is 0, which keeps all
derived clauses.

### `-blockerconfidence <n>`

Acceptance threshold for an exception proof in the recursive default check;
same decimal or percentage forms as `-confidence`, default 0.5. An exception
proof below the threshold is ignored, so the reported confidence can jump when
the combined evidence for an exception crosses it. Lower the threshold, or
use `-softblock`, for graded behavior below 0.5.

### `-firstanswer`

Stop after the first answer and its first retained proof.

### `-maxanswers <n>`

Stop after finding `n` distinct answers. If `-maxproofs` is also set, stopping
occurs after the retained answer classes have reached their proof limit.

### `-maxproofs <n>`

Retain at most `n` proofs for each distinct answer. The option does not by
itself stop the search. Raw-proof mode uses 16 when no explicit value is given.

## Confidence and support assessment

The default mode reports a compact verdict `confidence` equal to
`abs(support_for - support_against)` and, with `-detail`, the four components
from which it is derived. Accepted and rejected answer lists carry the sign.
The algorithms and interpretation are described in
[`how_gk_works.md`](how_gk_works.md).

### `-nocumulate`

Do not combine alternative proofs of the same answer.

### `-nonegative`

Do not search for support for the explicit negation.

### `-oldcumulate`

Combine two proofs by noisy-or with the weaker contribution scaled by a
dependency ratio estimated from the proof histories and by the
`independence` strategy percentage. Without this option, GK measures the
overlap from the proofs' activation-event sets.

### `-olduncertainty`

Select the single-number positive-minus-negative calculation.

### `-defworlds`

Select the four-component report. With `-clausify`, `-defworlds` selects
the confidence-aware clause export.

### `-envelope`

Compute minimum and maximum support when identified conflicts are resolved in
each direction. The bounds are support values; they have no probability
reading. It implies detailed output.

### `-stake <F>`

Set a decision threshold `F`, from 0 to 1, and report `ACCEPT`, `DEFER`, or
`REJECT`. With `-envelope`, the verdict uses the support bounds.

### `-rawproofs`

Return the retained positive and negative proofs without cumulation or
positive-negative arithmetic. Output is JSON. `-confidence` does not filter
this mode; use `-maxproofs` to limit proofs per answer.

### `-plain`

Ignore input confidences. If the input contains
no blockers, the default machinery is also skipped.

## Defaults and auxiliary data

### `-nocheck`

Do not run blocker checks. Default rules then fire without testing their
exceptions.

### `-softblock`

Multiply a blocked candidate's confidence by `1 - pb`, where `pb` is the
noisy-or pool of the firing blocker confidences. The option selects the
single-number calculation pipeline unless `-defworlds` is given; it is a
different pipeline, and the four-component report does not use this
discounting.

### `-taxonomy`

Load the taxonomy data used by taxonomy-form blocker priorities such as
`tax(name)` and `tax(name, nr)`. GK reads two files, from the
`-datafolder` path or the current working directory:

```text
gk_name_number.txt
gk_taxonomy_packed.txt
```

The canonical copies are in [`../data/`](https://github.com/tammet/gkreasoner/blob/master/data/README.md). The two
files form one generated pair and are validated together; a missing or
mismatched file is an error with a nonzero exit. An input that uses
taxonomy-form priorities without this flag is an error; numeric
priorities never need it. `-defaults` is an accepted synonym. The
comparison rule — a more specific class defeats a more general one — is
described in the defaults section of
[`how_gk_works.md`](how_gk_works.md).

### `-relatedwords`

Load `gk_relatedwords.txt`.

### `-similarities`

Load the word-similarity file `gk_similarity.txt` and enable similarity
derivation.

### `-nosimilarities`

Disable similarity derivation even when a similarity file has been loaded.
Useful with `-usekb` when the shared base contains the file.

### `-datafolder <path>`

Read auxiliary `gk_...` files from `path` rather than the current directory.

```sh
gk Examples/exceptions/classify.gkp \
  -taxonomy -datafolder data
```

### `-task <name>`

Select a build-specific auxiliary task. Task names are not part of the stable
proof-search interface; an ordinary reasoning command does not use this option.

## Search strategies

### `-strategy <file>`

Use a JSON strategy file:

```sh
gk Examples/exceptions/penguin.gkp \
  -strategy Examples/strategy/query_focus.json
```

### `-strategytext '<json>'`

Supply the strategy object directly:

```sh
gk Examples/exceptions/penguin.gkp \
  -strategytext '{"strategy":["query_focus"],"query_preference":1}'
```

Without either option, GK constructs a strategy automatically: a short
ordered sequence with initial proof-finding time limits, described in
[`strategy_reference.md`](strategy_reference.md). Strategy keys are listed
there as well.

### `-explore`

Give every automatically selected strategy the same short time to find its
first proof. The first successful strategy receives the remaining query time.
GK enables this mode automatically when `-seconds` exceeds 30.

## Shared-memory knowledge bases

A parsed knowledge base can be held in shared memory for repeated queries.
Database number 1000 is used by default.

### `-readkb <file>`

Parse a question-free file into shared memory. Use at least `-mbsize 1000`.
Options that load auxiliary data, such as `-taxonomy -datafolder DIR`, belong
on this command.

### `-usekb`

Use the shared knowledge base together with any query file on the command
line. The question must be in that file. Auxiliary data loaded with
`-taxonomy`, `-datafolder`, or `-relatedwords` comes from the shared base; do
not repeat those options. Search and report options, including `-parallel`,
apply to each query. With `-usekb`, SINE relevance filtering is disabled.

### `-deletekb`

Delete the selected shared-memory database.

### `-mbnr <n>`

Select a shared-memory database number. Values of 10 or greater are suitable
for ordinary use. Separate numbers allow several databases to coexist.

### `-writekb <file>`

Write the selected shared-memory database to a dump file.

### `-loadkb <file>`

Load a dump file into shared memory.

### `-readwritekb <logic-file> <dump-file>`

Parse a logic file and write the resulting database directly to a dump file.

Typical sequence:

```sh
gk -readkb axioms.js -mbsize 2000 -taxonomy -datafolder DIR
gk -usekb query.js -parallel 3
gk -deletekb
```

Shared-memory databases are host resources. Delete an unused database before
reusing its number with a different size or configuration.

## Conversion

### `-clausify`

Print the clausified problem instead of proving it. Plain `-clausify` emits the
classic clause representation; `-defworlds -clausify` emits the
confidence-aware clause representation.

## Information

### `-help`

Print the built-in option summary.

### `-version`

Print the version, build date, word sizes, byte order, compiler, and database
features.

### `-licence`

Print the licence embedded in the executable. `-license` is also accepted.

## Result strings

| Result | Meaning |
|---|---|
| `answer found` | at least one answer met the acceptance threshold |
| `evidence below limit` | a proof was found but its assessed margin was below `-confidence` |
| `no answers found` | no substitution was found for an open query |
| `no information` | neither polarity of a ground query was proved |
| `time limit, proof not found` | the search limit expired before a proof was found |

An output may also contain rejected answers when negative support dominates.
Use `-detail` to distinguish negative support, conflict, and ignorance.
