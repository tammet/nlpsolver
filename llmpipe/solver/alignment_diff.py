"""Deterministic before/after diff of a Stage-2 edit (DA2 WP3.4).

Plan: memos/PLAN_2026_08_09_dynamic_abstraction_alignment_pilot_opus5.md §9.4.

The editor is never asked what its edit did.  This module computes it: which
packages changed, which raw atoms were added or removed (canonicalized so a
variable rename is not a change), how binders and entity terms moved, whether a
predicate family or argument order changed, what an added rule's direction and
strictness are, and — when conversion is available — which final clauses each
source package gained or lost.

Two renderings come out of the same record: JSON for measurement and short
English for the verifier.  No LLM calls, no GK.
"""

import json

import alignment_occurrences as AO


def _canon_atom(atom, varmap):
    """An atom with variables replaced by positional placeholders."""
    out = []
    for i, a in enumerate(atom):
        if isinstance(a, str) and i > 0 and AO._is_var(a):
            out.append(varmap.setdefault(a, "?%d" % len(varmap)))
        elif isinstance(a, list):
            out.append(_canon_atom(a, varmap))
        else:
            out.append(a)
    return out


def atoms_of(pkg):
    """Every predicate atom of a package, with its binder stack and rule side."""
    out = []

    def walk(node, binders, side, polarity):
        if not isinstance(node, list) or not node:
            return
        head = node[0]
        if not isinstance(head, str):
            for ch in node:
                walk(ch, binders, side, polarity)
            return
        if head in ("forall", "exists") and len(node) >= 3:
            walk(node[2], binders + [(head, node[1])], side, polarity)
            return
        if head == "implies" and len(node) == 3:
            walk(node[1], binders, "antecedent", polarity)
            walk(node[2], binders, "conclusion", polarity)
            return
        if head == "not" and len(node) == 2:
            walk(node[1], binders, side, "-" if polarity == "+" else "+")
            return
        if head in AO.LOGICAL_HEADS or head == "normally":
            for ch in node[1:]:
                walk(ch, binders, side, polarity)
            return
        out.append({"atom": node, "binders": list(binders), "rule_side": side,
                    "polarity": polarity})

    walk(pkg, [], "none", "+")
    return out


def canonical_atoms(pkg):
    varmap = {}
    return [json.dumps([_canon_atom(a["atom"], varmap), a["rule_side"],
                        a["polarity"]], sort_keys=True)
            for a in atoms_of(pkg)]


def _entity_terms(pkg):
    out = set()
    for a in atoms_of(pkg):
        for x in a["atom"][1:]:
            if isinstance(x, str) and not AO._is_var(x):
                out.add(x)
    return out


def _binders(pkg):
    return sorted(set("%s %s" % (q, v) for a in atoms_of(pkg)
                      for q, v in a["binders"]))


def _families(pkg):
    return sorted(set(a["atom"][0] for a in atoms_of(pkg)))


def _arg_shape(pkg):
    out = {}
    for a in atoms_of(pkg):
        key = a["atom"][0]
        shape = tuple("var" if isinstance(x, str) and AO._is_var(x) else "const"
                      for x in a["atom"][1:])
        out.setdefault(key, set()).add(shape)
    return {k: sorted(v) for k, v in out.items()}


def rule_shape(pkg):
    """Direction and strictness of an added rule, read off the package."""
    blob = json.dumps(pkg)
    strict = '"normally"' not in blob
    ants = sorted(set(a["atom"][0] for a in atoms_of(pkg)
                      if a["rule_side"] == "antecedent"))
    cons = sorted(set(a["atom"][0] for a in atoms_of(pkg)
                      if a["rule_side"] == "conclusion"))
    return {"is_rule": bool(ants and cons),
            "strictness": "strict" if strict else "default",
            "antecedent_families": ants, "conclusion_families": cons,
            "direction": "%s -> %s" % (", ".join(ants) or "-",
                                       ", ".join(cons) or "-")}


def clause_delta(before_clauses, after_clauses):
    """Final-clause additions/removals per source package, after conversion."""
    import clause_trace
    def by_unit(cl):
        out = {}
        for c in cl or []:
            if not isinstance(c, dict):
                continue
            payload = clause_trace.clause_payload(c)
            if payload is None:
                continue
            units = clause_trace.source_unit_ids(c.get("@name") or "")
            key = units[0] if units else (c.get("@name") or "?")
            out.setdefault(key, []).append(
                json.dumps(clause_trace.canonical_form(payload), sort_keys=True))
        return out
    b, a = by_unit(before_clauses), by_unit(after_clauses)
    delta = {}
    for unit in sorted(set(b) | set(a)):
        import collections
        bb, aa = collections.Counter(b.get(unit, [])), collections.Counter(a.get(unit, []))
        add, rem = list((aa - bb).elements()), list((bb - aa).elements())
        if add or rem:
            delta[unit] = {"clauses_added": len(add), "clauses_removed": len(rem)}
    return delta


def diff(before_stage2, after_stage2, changed, added,
         before_clauses=None, after_clauses=None):
    """-> the measurement record (WP3.4)."""
    b = dict(AO.packages(before_stage2))
    a = dict(AO.packages(after_stage2))
    per_package = {}
    for pid in sorted(set(changed) | set(added)):
        bp, ap = b.get(pid), a.get(pid)
        ba = set(canonical_atoms(bp)) if bp is not None else set()
        aa = set(canonical_atoms(ap)) if ap is not None else set()
        entry = {
            "kind": "replacement" if pid in changed else "addition",
            "atoms_added": sorted(aa - ba),
            "atoms_removed": sorted(ba - aa),
            "binders_before": _binders(bp) if bp is not None else [],
            "binders_after": _binders(ap) if ap is not None else [],
            "entity_terms_added": sorted(
                _entity_terms(ap) - (_entity_terms(bp) if bp is not None else set())),
            "entity_terms_removed": sorted(
                (_entity_terms(bp) if bp is not None else set()) - _entity_terms(ap)),
            "predicate_families_before": _families(bp) if bp is not None else [],
            "predicate_families_after": _families(ap),
            "argument_shape_before": _arg_shape(bp) if bp is not None else {},
            "argument_shape_after": _arg_shape(ap),
        }
        entry["binders_changed"] = entry["binders_before"] != entry["binders_after"]
        entry["families_changed"] = (entry["predicate_families_before"]
                                     != entry["predicate_families_after"])
        entry["argument_order_changed"] = (entry["argument_shape_before"]
                                           != entry["argument_shape_after"])
        if pid in added:
            entry["rule"] = rule_shape(ap)
        per_package[pid] = entry
    untouched_changed = [pid for pid in b
                         if pid not in changed and pid not in added
                         and json.dumps(b[pid]) != json.dumps(a.get(pid))]
    rec = {
        "changed_package_ids": sorted(changed),
        "added_package_ids": sorted(added),
        "untouched_packages_changed": sorted(untouched_changed),
        "per_package": per_package,
        "atoms_added_total": sum(len(v["atoms_added"]) for v in per_package.values()),
        "atoms_removed_total": sum(len(v["atoms_removed"]) for v in per_package.values()),
    }
    if before_clauses is not None and after_clauses is not None:
        rec["final_clause_delta"] = clause_delta(before_clauses, after_clauses)
    return rec


def render(rec, stage1=None):
    """Short English for the verifier.  Describes the change, never judges it."""
    lines = []
    for pid in rec["changed_package_ids"] + rec["added_package_ids"]:
        e = rec["per_package"][pid]
        if e["kind"] == "addition":
            r = e.get("rule") or {}
            lines.append("Added %s: a %s rule %s."
                         % (pid, r.get("strictness", "?"),
                            r.get("direction", "with no clear direction")))
            continue
        lines.append("Replaced %s:" % pid)
        if e["atoms_removed"]:
            lines.append("  removes %d atom(s), including %s"
                         % (len(e["atoms_removed"]),
                            _short(e["atoms_removed"][0])))
        if e["atoms_added"]:
            lines.append("  adds %d atom(s), including %s"
                         % (len(e["atoms_added"]), _short(e["atoms_added"][0])))
        if e["binders_changed"]:
            lines.append("  binders change from [%s] to [%s]"
                         % (", ".join(e["binders_before"]),
                            ", ".join(e["binders_after"])))
        if e["entity_terms_removed"]:
            lines.append("  drops the term(s) %s"
                         % ", ".join(repr(t) for t in e["entity_terms_removed"]))
        if e["entity_terms_added"]:
            lines.append("  introduces the term(s) %s"
                         % ", ".join(repr(t) for t in e["entity_terms_added"]))
        if e["families_changed"]:
            lines.append("  predicate families change from [%s] to [%s]"
                         % (", ".join(e["predicate_families_before"]),
                            ", ".join(e["predicate_families_after"])))
        elif e["argument_order_changed"]:
            lines.append("  the same predicates are used with a different "
                         "argument shape")
    if rec["untouched_packages_changed"]:
        lines.append("WARNING: packages changed without being declared: %s"
                     % ", ".join(rec["untouched_packages_changed"]))
    if not lines:
        lines.append("No package changed.")
    return "\n".join(lines)


def _short(canon_atom_json):
    try:
        atom, side, pol = json.loads(canon_atom_json)
    except ValueError:
        return canon_atom_json[:60]
    body = " ".join(str(x) for x in atom)
    tag = "" if side == "none" else " [%s]" % side
    neg = "" if pol == "+" else " [negated]"
    return "%s%s%s" % (body, tag, neg)


def stage1_disagrees(after_stage2, stage1, changed):
    """WP4.2: did the edit move away from what Stage 1 recorded?

    True when a changed package now carries an entity term that Stage 1 does not
    have for that unit.  The English is authoritative, so this is a flag for the
    record, not an error.
    """
    s1_by_unit = {}
    for o in AO.extract_stage1(stage1 or []):
        s1_by_unit.setdefault(o["unit_id"], set()).add(o["normalized_label"])
        if o.get("term"):
            s1_by_unit[o["unit_id"]].add(AO.normalize_label(o["term"]))
    # Only terms in an argument position count.  A class label ("organic
    # matter"), a degree slot ("none") or an event type is vocabulary, not a
    # participant, and treating those as entity terms flags every edit.
    for o in AO.extract_stage2(after_stage2, stage1):
        if (o["unit_id"] not in changed or o["kind"] == "rule_variable"
                or o.get("term_is_variable") or AO._is_var(o.get("term"))):
            continue
        n = AO.normalize_label(o.get("term"))
        if n and n not in s1_by_unit.get(o["unit_id"], set()):
            return True
    return False
