"""Resolve a portfolio case id to its stored parse and its schema space.

The development challenges came from the fourteen-case cohort, which has a
hand-written entry per case.  The held-out challenges do not, so the same
lookup has to work for any portfolio id: find the stored abstracted result,
rebuild the occurrence table and the schema space from it, and hand back the
same three objects either way.

Matching a case to its stored result is by INPUT TEXT, never by index — a
result folder is a subset of its dataset, so `eb2-0020` is case 19 in
`cases.json` and `case_0015.json` on disk.
"""

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATASETS = {"eb2": "entailmentbank_task1_wave2", "eb": "entailmentbank_task1",
            "folio": "folio_v2_agreed", "mle2": "multilogieval_wave2",
            "mle": "multilogieval_gaming"}

TREES = {"entailmentbank_task1_wave2": "external_entailmentbank_task1_wave2_w2absnp",
         "multilogieval_wave2": "external_multilogieval_wave2_w2absnp",
         "entailmentbank_task1": "external_entailmentbank_task1_ext0807absnp",
         "folio_v2_agreed": "external_folio_v2_agreed_w2absnp"}

BENCH = os.path.join(ROOT, "tests", "external", "dynamic_alignment_bench")

_CACHE = {}
_TEXT_INDEX = {}


class CaseError(Exception):
    pass


def _jload(p):
    with open(p) as f:
        return json.load(f)


def _text_index(tree):
    if tree in _TEXT_INDEX:
        return _TEXT_INDEX[tree]
    idx = {}
    for p in glob.glob(os.path.join(ROOT, "testresults", tree, "gemini",
                                    "case_*.json")):
        try:
            d = _jload(p)
        except ValueError:
            continue
        t = (d.get("input_text") or "").strip()
        if t:
            idx.setdefault(t, (d, os.path.relpath(p, ROOT)))
    _TEXT_INDEX[tree] = idx
    return idx


def stored_result(case_id):
    """-> (stored result dict, path) for a portfolio case."""
    fx = os.path.join(BENCH, "case_%s.json" % case_id)
    if os.path.exists(fx):
        f = _jload(fx)
        stored = _jload(os.path.join(ROOT, f["source_result"]))
        stored = dict(stored, stage1=f["stage1"], stage2=f["stage2"],
                      final_clauses=f["final_clauses"],
                      input_text=f["input_text"])
        return stored, f["source_result"], f["configuration"]
    ds = DATASETS.get(case_id.split("-")[0])
    tree = TREES.get(ds)
    if not tree:
        raise CaseError("no result tree for %s (%s)" % (case_id, ds))
    cases = os.path.join(ROOT, "tests", "external", ds, "cases.json")
    want = None
    for c in _jload(cases):
        if c.get("portfolio_id") == case_id:
            want = "%s %s" % (c.get("original_context", "").strip(),
                              c.get("original_question", "").strip())
            break
    if want is None:
        raise CaseError("%s is not in %s cases.json" % (case_id, ds))
    hit = _text_index(tree).get(want.strip())
    if hit is None:
        raise CaseError("no stored result under %s matches %s" % (tree, case_id))
    return hit[0], hit[1], "abstracted"


def space(case_id):
    """-> (view, gen, built) for a case, cached."""
    if case_id in _CACHE:
        return _CACHE[case_id]
    import alignment_candidate_filter as CF
    import alignment_candidates as AC
    import dynamic_probe_pipeline as DPP
    stored, path, cfg = stored_result(case_id)
    view = DPP.runtime_view(case_id, stored, cfg)
    gen = AC.generate(view["stage1"], view["stage2"], view["configuration"])
    built = CF.build(gen, view["stage2"])
    _CACHE[case_id] = (view, gen, built)
    return _CACHE[case_id]


def schema(case_id, schema_id):
    _, _, built = space(case_id)
    for s in built["schemas"]:
        if s["schema_id"] == schema_id:
            return s
    raise CaseError("%s has no schema %s" % (case_id, schema_id))


def menu(case_id, schema_id):
    """The condition menu with real atom nodes, aliases G1..Gn in table order."""
    import alignment_context as CX
    view, gen, _ = space(case_id)
    s = schema(case_id, schema_id)
    rows = CX.menu(gen["table"], view["stage2"], s["producer_occurrences"][0],
                   s["consumer_occurrences"][0])
    return [("G%d" % (i + 1), m) for i, m in enumerate(rows)]
