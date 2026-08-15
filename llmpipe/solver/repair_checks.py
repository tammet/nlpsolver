"""Deterministic checks a translation repair has to pass, and its class.

The generic edit gates — splice, limits, one question, Stage-2 sanity, free
variables, inventory, leak, conversion, untouched packages — are
`alignment_edit.validate`'s and are not repeated here.  These are the ones a
REPAIR specifically can fail, each of which is a way of "fixing" a sentence by
quietly changing what it said:

  * changing a sentence other than the one the reviewer pointed at;
  * exchanging the participants of a relation while claiming to rename it;
  * turning a named individual into a variable, so a local fact becomes a law;
  * renaming a label that other, untouched sentences still use, which is a
    global rename carried out one package at a time;
  * altering the question's polarity or quantifier structure;
  * replacing a concept with a broader one — often the easiest way to make two
    expressions meet, and a loss.

A repair is classified, never scored on whether it helps: `faithful_local_repair`,
`faithful_but_lossy`, `unrelated_or_overbroad`, `invalid`, `no_edit`.
"""

import json

import alignment_occurrences as AO

CLASSES = ("faithful_local_repair", "faithful_but_lossy",
           "unrelated_or_overbroad", "invalid", "no_edit")

RELATION_PREDS = ("is rel2", "has degree rel2", "have", "has part", "member")


# ---------------------------------------------------------------- helpers

def _atoms(node, out=None):
    """Every predicate atom in a package, as (predicate, args)."""
    out = [] if out is None else out
    if not isinstance(node, list) or not node:
        return out
    head = node[0]
    if isinstance(head, str) and head not in AO.LOGICAL_HEADS:
        out.append((head, list(node[1:])))
        return out
    for ch in node:
        if isinstance(ch, list):
            _atoms(ch, out)
    return out


def _labels(pkg):
    out = set()
    for pred, args in _atoms(pkg):
        slot = AO.LABEL_SLOT.get(pred)
        if slot is not None and slot < len(args) and isinstance(args[slot], str):
            out.add(AO.normalize_label(args[slot]))
        else:
            out.add(pred)
    return out


def _entities(pkg):
    """Grounded individuals: the `#:`-prefixed or numbered constants."""
    import re
    out = set()
    for _, args in _atoms(pkg):
        for a in args:
            if isinstance(a, str) and not AO._is_var(a) and (
                    a.startswith("#:") or re.search(r" \d+$", a)
                    or a.startswith("http")):
                out.add(AO.normalize_label(a))
    return out


def _relation_pairs(pkg):
    """(predicate, label) -> list of participant tuples, order preserved."""
    out = {}
    for pred, args in _atoms(pkg):
        if pred not in RELATION_PREDS:
            continue
        slot = AO.LABEL_SLOT.get(pred)
        label = args[slot] if slot is not None and slot < len(args) else pred
        parts = tuple(AO.normalize_label(a) if isinstance(a, str) else
                      json.dumps(a)
                      for i, a in enumerate(args) if i != slot)
        out.setdefault((pred, AO.normalize_label(str(label))), []).append(parts)
    return out


def _quant_shape(node):
    """The quantifier/connective skeleton of a formula, labels removed."""
    if not isinstance(node, list) or not node:
        return None
    head = node[0]
    if not isinstance(head, str):
        return "?"
    if head in ("forall", "exists"):
        return "%s(%s)" % (head, _quant_shape(node[2]) if len(node) > 2 else "")
    if head in ("and", "or", "implies", "not", "normally", "holds", "question",
                "ask"):
        return "%s[%s]" % (head, ",".join(
            str(_quant_shape(c)) for c in node[1:] if isinstance(c, list)))
    return "atom"


def _polarity_count(node):
    return json.dumps(node).count('"not"')


# ---------------------------------------------------------------- the checks

def check_repair(stage1, stage2, edited_stage2, packages, changed, added,
                 expected_units, question_id=None):
    """-> a record of every repair-specific check.  Nothing raises."""
    before = dict(AO.packages(stage2))
    after = dict(AO.packages(edited_stage2))
    touched = sorted(set(changed) | set(added))
    unit_text = {}
    for sent in stage1 or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            unit_text[u.get("unit_id")] = u.get("text")

    out = {"touched_units": touched,
           "expected_units": sorted(expected_units or []),
           "checks": {}, "notes": []}
    c = out["checks"]

    # 1. only sentences the reviewer pointed at changed.  Subset, not equality:
    #    a mismatch can often be repaired from either side, and repairing one
    #    of the two is not a fault.  Touching a third one is.
    extra = sorted(set(touched) - set(expected_units or []))
    c["selected_occurrence_changed"] = bool(touched) and not extra
    if extra:
        out["notes"].append(
            "changed %s, which the reviewer did not point at" % extra)

    # 2. relation argument order preserved
    swapped = []
    for pid in changed:
        b, a = _relation_pairs(before.get(pid, [])), _relation_pairs(after.get(pid, []))
        for key, bl in b.items():
            al = a.get(key)
            if not al:
                continue
            for t in bl:
                if t in al:
                    continue
                if tuple(reversed(t)) in al:
                    swapped.append({"package": pid, "relation": key[1],
                                    "before": list(t),
                                    "after": list(reversed(t))})
    c["argument_order_preserved"] = not swapped
    out["swapped_arguments"] = swapped

    # 3. local constants stay local
    lost_entities, new_entities = [], []
    for pid in changed:
        be, ae = _entities(before.get(pid, [])), _entities(after.get(pid, []))
        lost_entities += sorted(be - ae)
        new_entities += sorted(ae - be)
    elsewhere = set()
    for pid, pkg in before.items():
        if pid not in touched:
            elsewhere |= _entities(pkg)
    c["local_constants_remain_local"] = not lost_entities
    out["entities_dropped_by_the_edit"] = lost_entities
    out["entities_introduced_by_the_edit"] = new_entities
    out["introduced_entities_borrowed_from_elsewhere"] = sorted(
        set(new_entities) & elsewhere)

    # 4. no other occurrence of a renamed label is silently renamed
    renamed_out, still_elsewhere = [], []
    for pid in changed:
        bl, al = _labels(before.get(pid, [])), _labels(after.get(pid, []))
        for lost in sorted(bl - al):
            renamed_out.append({"package": pid, "label": lost})
            where = [q for q, pkg in before.items()
                     if q not in touched and lost in _labels(pkg)]
            if where:
                still_elsewhere.append({"label": lost, "still_used_in": where})
    out["labels_removed_by_the_edit"] = renamed_out
    out["removed_labels_still_used_in_untouched_packages"] = still_elsewhere
    # this is not a failure by itself — a local repair MAY leave the old label
    # standing elsewhere — but it is what a global rename would have to do, and
    # it has to be visible
    c["no_silent_global_rename"] = all(
        q not in touched for e in still_elsewhere for q in e["still_used_in"]
    ) if still_elsewhere else True

    # 5. the question survives unchanged unless it is the repaired unit
    qid = question_id or next(
        (p for p, pkg in before.items()
         if isinstance(pkg, list) and pkg and pkg[0] in ("question", "ask")),
        None)
    if qid is None:
        c["question_preserved"] = True
    elif qid not in touched:
        c["question_preserved"] = json.dumps(before.get(qid)) == json.dumps(
            after.get(qid))
    else:
        c["question_preserved"] = (
            _quant_shape(before.get(qid)) == _quant_shape(after.get(qid))
            and _polarity_count(before.get(qid)) == _polarity_count(
                after.get(qid)))
        out["notes"].append("the question itself is the repaired unit; its "
                            "quantifier shape and polarity were compared")
    out["question_package"] = qid

    # 6. specificity
    lossy = []
    for pid in changed:
        bl, al = _labels(before.get(pid, [])), _labels(after.get(pid, []))
        for lost in sorted(bl - al):
            for kept in sorted(al):
                if kept and kept != lost and (
                        lost.endswith(" " + kept) or lost.startswith(kept + " ")):
                    lossy.append({"package": pid, "from": lost, "to": kept,
                                  "why": "a compound replaced by its head"})
        b_atoms = len(_atoms(before.get(pid, [])))
        a_atoms = len(_atoms(after.get(pid, [])))
        if a_atoms < b_atoms:
            lossy.append({"package": pid, "from": "%d atoms" % b_atoms,
                          "to": "%d atoms" % a_atoms,
                          "why": "the package says less than it did"})
    c["no_specificity_loss"] = not lossy
    out["specificity_loss"] = lossy

    # 7. source linkage
    out["source_linkage"] = {p: unit_text.get(p) for p in touched}
    c["source_linkage_available"] = all(
        unit_text.get(p) for p in changed) if changed else True

    out["all_checks_passed"] = all(c.values())
    return out


def classify(packages, validation, repair_record, checks):
    """-> (class, reasons).  Deterministic; no model and no prover involved."""
    reasons = []
    if not packages:
        return "no_edit", ["the editor returned no package"]
    if not validation.get("ok"):
        return "invalid", ["rejected at %s: %s" % (validation.get("stage"),
                                                   (validation.get("errors")
                                                    or [""])[0][:120])]
    c = checks["checks"]
    if not c["selected_occurrence_changed"]:
        reasons.append("it changed %s, not the sentence the reviewer named (%s)"
                       % (checks["touched_units"], checks["expected_units"]))
    if not c["argument_order_preserved"]:
        reasons.append("it exchanged the participants of %s"
                       % ", ".join(s["relation"] for s in
                                   checks["swapped_arguments"]))
    if not c["local_constants_remain_local"]:
        reasons.append("it dropped the named individual(s) %s"
                       % checks["entities_dropped_by_the_edit"])
    if checks["introduced_entities_borrowed_from_elsewhere"]:
        reasons.append("it brought in %s from another sentence"
                       % checks["introduced_entities_borrowed_from_elsewhere"])
    if not c["question_preserved"]:
        reasons.append("the question's polarity or quantifier structure changed")
    if repair_record is not None and not repair_record.get(
            "repair_is_local_to_its_units"):
        reasons.append("clauses outside the repaired sentences moved: %s"
                       % repair_record["clauses_outside_the_touched_units_that_moved"])
    if reasons:
        return "unrelated_or_overbroad", reasons
    if not c["no_specificity_loss"]:
        return "faithful_but_lossy", [
            "%s -> %s (%s)" % (l["from"], l["to"], l["why"])
            for l in checks["specificity_loss"]]
    return "faithful_local_repair", ["every repair check passed"]
