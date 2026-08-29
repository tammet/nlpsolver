# Third-party test data

Some test sets in this directory are **not our data**. They are established
benchmarks, redistributed here so the published results can be reproduced from
one checkout.

The repository's root `LICENSE` is Apache-2.0 and covers our own code and our
own test sets. **It does not extend to the files listed below.** Each of those
stays under its upstream license, whose text is in `licenses/`.

Every set below permits redistribution. The condition each one attaches is that
the copyright notice and license travel with the copy; that is what this file
and `licenses/` are for.

The repository root `NOTICE` carries the short form of the same statement, so
that it is visible beside the `LICENSE` it qualifies. Anyone redistributing a
derivative of this repository has to carry those notices forward, under
Apache-2.0 section 4(d). This file is the long form.

## What is ours

`tests_core.py`, `tests_core_100.py`, `tests_core_challenging.py` and
`tests_core_abstregress.py` are written for this pipeline. They are Apache-2.0
under the root `LICENSE`, like the rest of the repository.

## What is not

| files | dataset | license | text |
|---|---|---|---|
| `tests_folio_v2.py`, `FOLIO_yale/` | FOLIO | MIT | [`licenses/FOLIO-MIT.txt`](licenses/FOLIO-MIT.txt) |
| `tests_multilogieval.py`, `tests_multilogieval_sample.py` | Multi-LogiEval | MIT | [`licenses/MULTILOGIEVAL-MIT.txt`](licenses/MULTILOGIEVAL-MIT.txt) |
| `tests_hans.py` | HANS | MIT | [`licenses/HANS-MIT.txt`](licenses/HANS-MIT.txt) |
| `tests_multilogieval_100.py`, `tests_multilogieval_heldout100.py`, `tests_cohort165_mle2.py` | Multi-LogiEval | MIT | [`licenses/MULTILOGIEVAL-MIT.txt`](licenses/MULTILOGIEVAL-MIT.txt) |
| `tests_eb_100.py`, `tests_eb2_100.py`, `tests_eb_negatives_2026_08.py`, `tests_arc_negatives_2026_08.py`, `tests_cohort165_eb.py`, `tests_cohort165_eb2.py` | EntailmentBank | Apache-2.0 | [`licenses/ENTAILMENTBANK-APACHE-2.0.txt`](licenses/ENTAILMENTBANK-APACHE-2.0.txt) |

### FOLIO

- **Dataset:** FOLIO (First-Order Logic with Natural Language), v2.
- **Introduced in:** *FOLIO: Natural Language Reasoning with First-Order
  Logic*, arXiv:2209.00840 (2022; v2 2024), EMNLP 2024.
- **Authors:** Simeng Han, Hailey Schoelkopf, Yilun Zhao, Zhenting Qi, Martin
  Riddell, Wenfei Zhou, James Coady, David Peng, Yujie Qiao, Luke Benson, Lucy
  Sun, Alex Wardle-Solano, Hannah Szabo, Ekaterina Zubova, Matthew Burtell,
  Jonathan Fan, Yixin Liu, Brian Wong, Malcolm Sailor, Ansong Ni, Linyong Nan,
  Jungo Kasai, Tao Yu, Rui Zhang, Alexander R. Fabbri, Wojciech Kryściński,
  Semih Yavuz, Ye Liu, Xi Victoria Lin, Shafiq Joty, Yingbo Zhou, Caiming
  Xiong, Rex Ying, Arman Cohan, Dragomir Radev.
- **Obtained from:** the HuggingFace dataset `yale-nlp/FOLIO`, retrieved
  2026-06-07. The dataset card declares `license: mit`.
- **What we changed:** nothing about the data. `FOLIO_yale/*.jsonl` is the
  upstream split verbatim. `tests_folio_v2.py` repackages each validation
  record as `[id, input, expected]`, where `input` is the premises followed by
  the conclusion phrased as a question and `expected` is FOLIO's own v2 gold
  label.

### Multi-LogiEval

- **Dataset:** Multi-LogiEval.
- **Introduced in:** *Multi-LogiEval: Towards Evaluating Multi-Step Logical
  Reasoning Ability of Large Language Models*, arXiv:2406.17169, EMNLP 2024
  (Main).
- **Authors:** Nisarg Patel, Mohith Kulkarni, Mihir Parmar, Aashna Budhiraja,
  Mutsumi Nakamura, Neeraj Varshney, Chitta Baral.
- **Obtained from:** https://github.com/Mihir3009/Multi-LogiEval.
  Copyright (c) 2024 Mihir.
- **What we changed:** the context and question of each record are joined into
  one English string; the gold `yes` becomes `True.` and `no` becomes the pair
  `["Unknown.", "False."]`, either of which the runner accepts. Per-case depth
  and logic metadata is in `tests_multilogieval_meta.json`, keyed by id.

### EntailmentBank

- **Dataset:** EntailmentBank, task 1.
- **Introduced in:** *Explaining Answers with Entailment Trees*,
  arXiv:2104.08661, EMNLP 2021.
- **Authors:** Bhavana Dalvi, Peter Jansen, Oyvind Tafjord, Zhengnan Xie,
  Hannah Smith, Leighanna Pipatanangkura, Peter Clark.
- **Obtained from:** https://github.com/allenai/entailment_bank
  (`entailment_trees_emnlp2021_data_v2`, task 1), under Apache-2.0, retrieved
  against a pinned commit. The upstream repository ships no `NOTICE` file, so
  Apache-2.0 section 4(d) adds nothing to propagate.
- **What we changed:** each record's supporting sentences are joined into a
  passage and its hypothesis is phrased as a question. The `_100` files are
  uniform-random samples, seeded and recorded in each file's header. The
  `negatives` files pair a passage with a hypothesis that does not follow from
  it, to give the family its `False.` and `Unknown.` answers; the pairing is
  ours, the sentences are EntailmentBank's.
- **ARC:** `tests_arc_negatives_2026_08.py` uses wrong answer options from the
  ARC question that each EntailmentBank record already carries. The text
  reaches us through EntailmentBank and is covered by its Apache-2.0 license;
  there is no separate ARC download.

### HANS

- **Dataset:** HANS (Heuristic Analysis for NLI Systems).
- **Introduced in:** *Right for the Wrong Reasons: Diagnosing Syntactic
  Heuristics in Natural Language Inference*, arXiv:1902.01007, ACL 2019.
- **Authors:** R. Thomas McCoy, Ellie Pavlick, Tal Linzen.
- **Obtained from:** https://github.com/tommccoy1/hans.
  Copyright (c) 2019 R. Thomas McCoy.
- **What we changed:** a selection covering the distinct template and
  entailment patterns, each case carrying its HANS template-pattern label.
  Premise and hypothesis are joined into one English string. Cases whose
  parse or confidence is known to be wrong are commented out in place.

## Datasets held back

Further corpora and their converted cases are held locally and not committed:
raw downloads, annotation queues and the converted `tests_external_*` files. A
local lock file records each source with its license and a pinned URL. One of
those sources, MALLS, derives from CC BY-NC 4.0 material and is not
redistributable here; the others are MIT or Apache-2.0, and none of their text
appears in the files this repository does track.
