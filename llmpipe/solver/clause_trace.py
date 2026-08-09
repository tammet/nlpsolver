"""Provenance for the clause list actually handed to the prover.

Plan step M1.1 of memos/PLAN_2026_08_07_abstraction_initial_phases.md.

Why this module exists.  Three later components (the proof audit, the
break-point locator and the fidelity diff) all need to know what gk actually
received and where each clause came from, and neither of the two things that
look like they answer that question does:

  * ``collect["clauses"]`` is built in solve.py *before*
    ``semnormalize.sem_normalize_clauses`` runs, so it can differ from the
    clauses gk was given;
  * a gk proof step records only ``["in", name, "assumption", ...]`` plus the
    clause.  ``utils.clause_list_to_json_commented`` deliberately drops
    ``@sourcetype`` when serialising for gk (utils.py:81), and several final
    clauses legitimately share one ``@name`` (a question compiles to a group of
    ``sent_S2`` clauses), so a name alone identifies neither the origin nor the
    individual clause.

So we record the final list and a per-clause sidecar next to it.  The sidecar
is never sent to gk.  A proof input step is joined back to it by name plus
canonicalised clause content; if that still matches several entries the
provenance is reported as ambiguous rather than guessed.
"""

import hashlib
import json
import re

import globals as _g

# --- name shapes actually produced by the converter ---------------------------
# sent_S1, sent_S1_2 (repeated unit id), sent_S1_el3 / sent_S1_dist (derived),
# entity_S1 (entity category clauses), and the injector families below.
_UNIT_NAME_RE = re.compile(r"^(?:sent|entity)_(S\d+)")
_BRIDGE_NAME_RE = re.compile(r"^sent_(B\d+)")          # dynamic bridges (M5+)
_INJECTOR_PREFIXES = ("frm_", "compound_sub", "compound_comp")
_INJECTOR_SUFFIXES = ("_bridge",)

# Literals that are proof plumbing rather than asserted content.  Used when
# classifying proof steps of historical runs, where no sidecar exists.
_CONTROL_PREDICATES = ("$defq", "$ans", "$auto_negated_question")


def _norm(obj):
    """Canonical JSON for hashing/comparison (stable key order, no spacing)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def clause_key(name, logic_obj):
    """sha256 over (name, exact logic).  Identical duplicates share a key."""
    return hashlib.sha256(_norm([name, logic_obj]).encode("utf-8")).hexdigest()


def _blind_vars(obj):
    """Replace every variable with a single placeholder, keeping structure."""
    if isinstance(obj, str):
        return "?:_" if obj.startswith("?:") else obj
    if isinstance(obj, list):
        return [_blind_vars(x) for x in obj]
    return obj


def _rename_vars(obj, mapping):
    if isinstance(obj, str):
        if obj.startswith("?:"):
            if obj not in mapping:
                mapping[obj] = "?:v%d" % len(mapping)
            return mapping[obj]
        return obj
    if isinstance(obj, list):
        return [_rename_vars(x, mapping) for x in obj]
    return obj


def canonical_form(logic_obj):
    """A clause form that survives gk's echo of the clause in a proof.

    gk renames variables (?:Fv22 -> ?:Y) and reorders literals (it puts $block
    first), so hashing the clause as written never matches the clause as it
    comes back in a proof step. This normalises both: literals are sorted by
    their variable-blinded text, then variables are renumbered in that fixed
    order.

    Clauses differing only in which variable sits where can canonicalise the
    same way. That is safe: the join then reports 'ambiguous' rather than
    picking one.
    """
    if not isinstance(logic_obj, list) or not logic_obj:
        return _rename_vars(logic_obj, {})
    lits = logic_obj if isinstance(logic_obj[0], list) else [logic_obj]
    ordered = sorted(lits, key=lambda l: _norm(_blind_vars(l)))
    return _rename_vars(ordered, {})


def canonical_key(name, logic_obj):
    """sha256 over (name, canonical logic) -- stable across gk's renaming."""
    return hashlib.sha256(
        _norm([name, canonical_form(logic_obj)]).encode("utf-8")).hexdigest()


def clause_payload(clause):
    """The asserted part of a clause dict: @logic or @question."""
    if not isinstance(clause, dict):
        return clause
    for key in ("@logic", "@question"):
        if key in clause:
            return clause[key]
    return None


def is_control_literal(lit):
    """True for gk proof plumbing ($defq0, $ans, the negated-goal marker)."""
    head = None
    if isinstance(lit, str):
        head = lit
    elif isinstance(lit, list) and lit and isinstance(lit[0], str):
        head = lit[0]
    if not head:
        return False
    head = head.lstrip("-")
    return any(head.startswith(p) for p in _CONTROL_PREDICATES)


def source_unit_ids(name):
    m = _UNIT_NAME_RE.match(name or "")
    return [m.group(1)] if m else []


def _lookup_source(name, text_map):
    """Resolve a clause name against a sent_S<N>[_k] keyed map.

    Derived names (sent_S1_el3, sent_S1_dist) fall back to their base; the
    duplicate-unit form sent_S1_2 is itself a key, so exact match is tried
    first and only then suffix stripping.
    """
    if not name:
        return None
    if name in text_map:
        return text_map[name]
    parts = name.split("_")
    while len(parts) > 2:
        parts = parts[:-1]
        cand = "_".join(parts)
        if cand in text_map:
            return text_map[cand]
    return None


def classify_clause(clause):
    """Return (source_kind, mechanism_tags) for one final clause dict.

    source_kind is one of: sentence | question | generated | bridge | unknown.
    'generated' covers everything the pipeline manufactured rather than
    translated: population witnesses, entity-category clauses, injected axioms,
    compound subsumption, world geometry, question tense bridges.
    """
    if not isinstance(clause, dict):
        return "unknown", []
    name = str(clause.get("@name") or "")
    stype = clause.get("@sourcetype")
    tags = []
    if stype:
        tags.append("sourcetype:" + str(stype))

    if _BRIDGE_NAME_RE.match(name):
        tags.append("dynamic_bridge")
        return "bridge", tags

    if name.startswith(_INJECTOR_PREFIXES) or name.endswith(_INJECTOR_SUFFIXES):
        tags.append("injected_axiom")
        return "generated", tags

    if name.startswith("entity_"):
        tags.append("entity_category")
        return "generated", tags

    if stype in ("populate", "question_bridge", "world_geometry"):
        return "generated", tags

    if stype in ("question", "question_subject"):
        return "question", tags

    # The query goal itself carries @question and usually no @sourcetype, so it
    # must be recognised by its payload key rather than by name or sourcetype.
    if "@question" in clause:
        tags.append("query_goal")
        return "question", tags

    if name.startswith("sent_"):
        return "sentence", tags

    return "unknown", tags


def _encoding_tags():
    """Abstraction gates active for this run.

    A lossy fold rewrites ordinary sent_S* clauses in place, so a name-based
    test cannot reveal it; the audit needs to know the gates were on.
    """
    try:
        cfg = _g and __import__("lc_encoding").current()
    except Exception:
        return []
    tags = []
    if getattr(cfg, "event_base", "neodavidson") != "neodavidson":
        tags.append("event_base:" + cfg.event_base)
    for attr in ("entitymerge", "guarddrop", "bridges", "dropdefinites",
                 "localantonyms", "simpleprops", "propclass", "typeenrich"):
        if getattr(cfg, attr, False):
            tags.append(attr)
    return tags


def build_final_clause_trace(final_clauses, s1_json=None, pre_clauses=None):
    """Sidecar for the clause list as sent to the prover.

    pre_clauses, when given, is a deep copy of the list taken before
    semnormalize; clauses it rewrote are tagged and their earlier form kept.
    sem_normalize_clauses documents in-place modification, so index alignment
    is valid; it is verified by length and only used when it holds.
    """
    try:
        from proof_explain import build_sentence_map
        from utils import build_asu_text_map
        raw_map = build_sentence_map(s1_json) if s1_json else {}
        asu_map = build_asu_text_map(s1_json) if s1_json else {}
    except Exception:
        raw_map, asu_map = {}, {}

    aligned = (isinstance(pre_clauses, list)
               and len(pre_clauses) == len(final_clauses))
    enc_tags = _encoding_tags()

    trace = []
    for i, clause in enumerate(final_clauses):
        name = str(clause.get("@name") or "") if isinstance(clause, dict) else ""
        payload = clause_payload(clause)
        kind, tags = classify_clause(clause)
        tags = list(tags) + enc_tags

        pre_logic = None
        if aligned:
            prev = clause_payload(pre_clauses[i])
            if _norm(prev) != _norm(payload):
                tags.append("semnormalize")
                pre_logic = prev

        trace.append({
            "clause_key": clause_key(name, payload),
            "canonical_key": canonical_key(name, payload),
            "index": i,
            "name": name,
            "sourcetype": clause.get("@sourcetype") if isinstance(clause, dict) else None,
            "source_kind": kind,
            "source_unit_ids": source_unit_ids(name),
            "source_raw_text": _lookup_source(name, raw_map),
            "source_asu_text": _lookup_source(name, asu_map),
            "mechanism_tags": tags,
            "pre_transform_logic": pre_logic,
        })
    return trace


def join_proof_step(name, logic_obj, trace):
    """Map a gk proof input step back to its trace entry.

    Tried in order: exact content, then the canonical form (gk renames
    variables and reorders literals in the clauses it echoes), then the name
    alone when it identifies exactly one clause.  Returns (entry_or_None,
    status) with status in matched_exact | matched_canonical | matched_name |
    ambiguous | not_found.  Never picks between candidates.
    """
    if not trace:
        return None, "not_found"

    hits = [e for e in trace if e["clause_key"] == clause_key(name, logic_obj)]
    if len(hits) == 1:
        return hits[0], "matched_exact"

    ckey = canonical_key(name, logic_obj)
    chits = [e for e in trace if e.get("canonical_key") == ckey]
    if len(chits) == 1:
        return chits[0], "matched_canonical"
    if len(chits) > 1:
        # same canonical form: fall through only if the entries agree on what
        # the audit needs, otherwise report ambiguous
        first = chits[0]
        same = all(e["source_kind"] == first["source_kind"]
                   and e["source_raw_text"] == first["source_raw_text"]
                   for e in chits)
        return (first, "matched_canonical") if same else (None, "ambiguous")

    by_name = [e for e in trace if e["name"] == name]
    if len(by_name) == 1:
        return by_name[0], "matched_name"
    # Several clauses share the name and the content matched none of them, so
    # this is not identifiable: report ambiguous rather than attaching the
    # step to whichever entry happens to come first.
    return None, ("ambiguous" if by_name else "not_found")


def backfill_canonical_keys(trace, final_clauses):
    """Add canonical_key to trace entries written before it existed.

    Runs stored by an earlier build carry clause_key only; the canonical key
    can be recomputed from the clause list the trace indexes into.
    """
    if not trace or not final_clauses:
        return trace
    for e in trace:
        if e.get("canonical_key"):
            continue
        i = e.get("index")
        if not isinstance(i, int) or i >= len(final_clauses):
            continue
        e["canonical_key"] = canonical_key(e["name"],
                                           clause_payload(final_clauses[i]))
    return trace


def historical_step_kind(name, logic_obj):
    """Classify a proof step of a run that predates the sidecar.

    Only mechanically unambiguous cases are decided; everything else is
    'unknown' rather than a guess (the M4 audit is designed to tolerate that).
    """
    n = str(name or "")
    if n.startswith("$") or n == "$auto_negated_question":
        return "proof_control"
    lits = logic_obj if isinstance(logic_obj, list) else [logic_obj]
    if lits and all(is_control_literal(l) for l in lits):
        return "proof_control"
    if _BRIDGE_NAME_RE.match(n):
        return "bridge"
    if n.startswith(_INJECTOR_PREFIXES) or n.endswith(_INJECTOR_SUFFIXES) \
            or n.startswith("entity_"):
        return "generated"
    return "unknown"
