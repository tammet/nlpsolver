# FOLIO — upstream source data (third-party)

**FOLIO is not our dataset.** This is the Yale FOLIO v2 validation split,
redistributed unmodified so the FOLIO results in this repository can be
reproduced from one checkout.

- `folio_v2_validation.jsonl` — the upstream validation split, verbatim (203
  records; the scored set). Each record carries `story_id`, `premises`,
  `premises-FOL`, `conclusion`, `conclusion-FOL`, `label`, `example_id`.
- `folio_v2_validation_readable.txt` — a plain-text dump of the validation
  split, for reading. Same content, reformatted.

`tests/tests_folio_v2.py` is built from this split.

## Attribution

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
- **License:** MIT — see [`../licenses/FOLIO-MIT.txt`](../licenses/FOLIO-MIT.txt).
  This repository is Apache-2.0; the files in this directory remain under their
  upstream MIT license.

See [`../THIRD_PARTY.md`](../THIRD_PARTY.md) for every third-party set here.
