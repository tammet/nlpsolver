# Pipeline mechanism experiments, August 2026

These pages say which mechanisms the pipeline uses, which it keeps as options,
and which were tried and set aside. They exist so that a reader can tell an
adopted default from an experiment, and can see the evidence behind each
decision without rerunning it.

Read a page here when you want to know why something is the way it is. Read
the [architecture](../architecture/README.md) pages when you want to know how
it works, the [encoding reference](../encodings/README.md) when you want its
exact form, and the [reference](../reference/README.md) pages when you want to
use it. These pages carry evidence and status, never normative syntax.

Each entry describes one mechanism: what it does, how it was evaluated, what
the evaluation found, and what was decided. An entry is written to stand on its
own, because the experiment logs behind it are local files that this repository
does not track. A memo name at the end of an entry is an archival identifier,
not a link.

The pages cover mechanisms that were introduced, compared, materially revised,
rejected, or adopted during this period. They are not a description of every
ordinary converter feature. A small fix appears only when an experiment showed
that it affected a meaningful class of cases.

The implementation-status statements refer to the repository state on
2026-08-28: commit `6b266d0c935d8bca2716051ffbec7f99cbac04d0`
(`Adopt safe proof shorteners and balanced retry pipeline`) plus the two graph
structural-safety repairs of 2026-08-28, which are described under
[default mechanisms](default.md) and are not yet committed. Later code may
change a mechanism's availability without changing the historical result
recorded here.

## Pages

- [Default mechanisms](default.md) — enabled in an ordinary run
- [Optional mechanisms](optional.md) — higher-recall and specialist
- [Experimental mechanisms](experimental.md) — research and diagnosis
- [Superseded mechanisms](superseded.md) — rejected, removed or replaced
- [Cross-cutting conclusions](lessons.md) — and the limits of the evidence

## Reading the results

### Status terms

- **Default**: enabled in an ordinary run without a special option.
- **Optional**: retained and available through a command-line option or a
  named pipeline configuration, but not enabled by default.
- **Experimental**: retained for research or diagnosis; the evidence is not
  sufficient for ordinary use.
- **Superseded**: replaced by a later mechanism that addresses the same need
  more safely or clearly.
- **Removed**: measured as ineffective or harmful and subsequently deleted
  from the active implementation.

### Important evaluation sets

The experiments used several kinds of material. Their differences matter.

| Set | Size used | Main diagnostic value |
|---|---:|---|
| Core | up to 1,600 cases | Short everyday reasoning; high baseline accuracy; many cases expose damage caused by over-abstraction. |
| Core 100 | 100 | A compact regression and accepted-Unknown control set. |
| Core challenging | 341 | Harder Core cases, including longer proofs and some accepted-Unknown answers. |
| FOLIO | 203 | Closed-passage first-order reasoning with True, False, and Unknown labels; useful for both recall and over-answering checks. |
| Multi-LogiEval | 100-case design and held-out samples | Rule chains, conditional questions, non-monotonic and modal cases, and greater reasoning depth. |
| EntailmentBank and EB2 | 20/21-case early cohorts and later 100-case samples | Open-world science entailment where a missing ordinary-knowledge connection is often necessary. |
| Literal-bridge widening cohort | 165 | 80 FOLIO, 41 EntailmentBank, 25 Core, and 19 Multi-LogiEval cases, deliberately including positive and negative controls. |
| Action-planning pilot | 20 | Travel, tools, blocks, effects, possession, reachability, and actual-versus-hypothetical action tests. |

The same numeric result can mean different things on these sets. A mechanism
that invents a plausible background rule may help EntailmentBank while being
unsafe on FOLIO, where an unstated connection should normally leave the answer
Unknown. Results are therefore reported by set rather than only as combined
totals.

A **model-case run** is one case processed with one model. Thus 203 FOLIO
cases tested with three models are 609 model-case runs. An activation count
means that the mechanism actually changed the submitted theory or executed its
special search, not merely that a preliminary text pattern matched. Unless an
entry says otherwise, “correct” and “wrong” are case-level comparisons with the
stored accepted answer.

### The default pipeline at the end of the period

The ordinary pipeline now uses the following ordered procedure:

```text
canonical translation with reversible event compression and repeated
part-witness compression
  -> GK
  -> normalization fallback, if still unresolved
  -> conditional-question fallback, if still unresolved
  -> critic-guided retranslation, if still unresolved
  -> open-relation graph retranslation, if still unresolved
  -> Unknown
```

The first definite answer stops later stages. The default does not use a
dataset name, an expected answer, literal bridges, graph bridges, a lossy
abstract retry, or a post-proof acceptance policy.

Named configurations are:

| Configuration | Enabled retry stages |
|---|---|
| `conservative` | normalization and conditional-question fallbacks |
| `balanced` (default) | conservative stages, critic, graph retranslation |
| `high-recall` | balanced stages plus graph bridges |
| `stack-open` | all of the above plus literal bridges |

The central design rule is ordered fallback: start with the most faithful
representation, and try alternative translations only when an earlier attempt
yields no definite answer.

## Present classification at a glance

| Mechanism | Present classification | Main reason |
|---|---|---|
| Reversible event compression (`davidson2`) | default | Exact round trip, broad proof shortening, 0 losses in full paired study. |
| Repeated part-witness compression (`existfold2`) | default | Narrow repeated-existential compression, several gains, 0 observed losses. |
| structural reference and conversion repairs | default | Restore identity, scope, binders, and valid question packages without adding knowledge. |
| safe converter and question-presence repairs | default | Restore omitted or malformed source structure. |
| normalization fallback | default | LLM-free, attributable gains after Unknown. |
| conditional-question fallback | default | Recovers a distinct question shape after Unknown at low cost. |
| critic retranslation | default | High-precision detailed-translation repair. |
| graph retranslation, no bridges | default | Complementary, relatively precise second reading. |
| graph logical-shape and question-only-proof checks | default safety repairs | Prevent malformed graph formulas and question encodings from producing accepted answers. |
| uniform later-stage proof rendering | default | Makes graph and compact proofs as inspectable as canonical proofs. |
| graph bridges | optional high-recall | Strong on open-world material; slight closed-world loss. |
| literal bridges | optional / research | Useful multi-bridge recall; substantial over-answer risk. |
| negative bridge syntax and distinctness | retained capability | Mechanically sound; broad generation unmeasured after a successful focused diagnostic. |
| legacy abstract presets | optional / reproduction | Can recover FOLIO proofs but erase distinctions and damage Core. |
| legacy Davidson/Existfold | historical only | Replaced by reversible version-2 mechanisms. |
| critic/graph acceptance policy | experimental, off | Removes far more correct than wrong answers. |
| bridge graders | diagnostic only | Semantic grade did not improve case-level decisions. |
| NEEDS_CONDITION repair | experimental, not integrated | Most repaired rules remained counterexampled; large recall loss. |
| graph-proof lifting | experimental | Produces detailed proofs in some cases, no clear net answer gain. |
| action-planning translator | isolated experimental pipeline | Sound representation pilot; translation coverage not mature. |
| multiple-model voting or proposal union | evaluation only | Models are complementary, but no reliable conflict-selection rule was found. |
| typed-filler and role-shape projections | considered, not built | Corrected opportunity census found 12 and 0 qualifying residual records. |
| template/operator bridge pipeline | superseded | Valuable lessons, but excessive selector and admission complexity. |
| critic--editor--verifier chain | superseded | Located interfaces well, but formal editing and verification were unreliable. |
| scalar admission / mechanical relevance | removed | Collapsed independent evidence and made false semantic judgments. |
| three-stage `qretry` | superseded and removed | Safe parts became two fallbacks; the generated stage over-answered. |
| small zero-effect flags | removed | Changed theories without improving answers. |
| always-on lossy question rewrites | not adopted | Repaired some wrong answers but destroyed canonical proofs. |

## Related documentation

- [Pipeline](../architecture/pipeline.md)
- [Retries and retranslation](../architecture/retries.md)
- [Proof shortening](../architecture/proof-shortening.md)
- [Abstraction](../architecture/abstraction.md)
