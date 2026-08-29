# Instructions for working on mkdata

## Purpose and sources

This directory builds the lexical normalization and exclusion data consumed
by `llmpipe`. Read `README.md` before modifying a generator or data format.
The source text files and generator scripts here are authoritative; the
runtime modules written to `../solver/data_*.py` are generated outputs.

## Safe workflow

- Do not hand-edit `../solver/data_canonicals.py`, `data_antonyms.py`,
  `data_synonyms.py`, or `data_exclusions.py`. Change the corresponding source
  data or generator and run `python3 build_solver_data.py` from this directory.
- The final generation step is fast. Earlier cluster-generation, harvesting,
  and canonical-selection steps are expensive, require the local virtual
  environment and external models, and may rewrite authoritative text files.
  Run those steps only when the task explicitly requires rebuilding them.
- Use `venv/bin/python` for scripts that require fastText, NLTK, wordfreq,
  NumPy, or spaCy. Do not install these heavy dependencies into the main
  pipeline environment merely to run the final generator.
- Preserve provenance, thresholds, manual block lists, and review artifacts
  when changing lexical sources. Do not replace curated exclusions with
  automatically mined groups without review.
- Verb antonyms are intentionally excluded from polarity-flipping runtime
  normalization. Many are perspective inversions or process complements, not
  logical negations. Preserve this boundary unless the task explicitly
  redesigns and evaluates it.
- Preserve both guards that prevent canonical-substitution chains from
  contaminating antonym rewrites.

## Verification

- Review diffs in both the changed source files and every regenerated
  `../solver/data_*.py` file; unexpected large changes require investigation.
- Compile and import the generated Python modules after regeneration.
- Run focused normalization and exclusion tests when those tables change, and
  record any intentional changes in entry counts or behavior.
- Do not commit the local virtual environment, downloaded language resources,
  the fastText model, or temporary review output.
