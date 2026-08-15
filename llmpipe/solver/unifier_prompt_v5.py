"""The v5 literal-bridge prompts: one cached system prompt, three user messages.

Plan: `memos/PLAN_2026_08_13_unifier_v5_prompt_builder_preview_opus5.md`.
Specification: `memos/MEMO_2026_08_13_literal_bridge_prompt_audit.md` and
`memos/DRAFT_2026_08_13_unifier_rules_v5_system_prompt.txt`.

This module only BUILDS TEXT.  It calls no LLM and no prover, and it never
reads an accepted answer, a reviewed rule, a grade or a proof.

Four things differ from the v4 prompt (`unifier_runtime_v4.rules_prompt`):

  * **the task comes first and is stable.**  The complete instructions are the
    system prompt, byte-identical for every case and every call, so the second
    call is self-contained instead of referring to a "before" that no stateless
    request can see;
  * **the passage and the question are separate blocks.**  v4 pasted the stored
    input text, which ends in the question, under one heading, so nothing told
    the model which sentence was not a fact;
  * **candidates are grouped by their unsigned atom**, with FOCUS/HELPER for
    relevance instead of MAIN/SECONDARY for provenance, and LEFT/RIGHT/EITHER
    for position instead of PREMISE/CONSEQUENCE/BOTH.  Every source candidate id
    and every signed cost is kept in the record;
  * **a candidate whose displayed meaning is not what it compiles to is not
    shown at all.**  v4 printed the surface atom and, beneath it, a `GK FORM`
    that sometimes asserted something else; no wording can teach a model which
    of the two lines it is writing.  The check here is conservative: it rejects
    unless a small, named list of documented rewritings explains every
    difference.
"""

import hashlib
import json
import os
import re

import alignment_occurrences as AO
import unifier_abstraction as UA

VERSION = "unifier_prompt_v5/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
SYSTEM_PROMPT_NAME = "unifier_rules_v5_system"

FOCUS, HELPER = "FOCUS", "HELPER"
POSITIVE, NEGATED = "POSITIVE", "NEGATED"
LEFT, RIGHT, EITHER = "LEFT", "RIGHT", "EITHER"

# PREMISE / CONSEQUENCE / BOTH are internal words derived from clause polarity.
# Only these three reach the model.
POSITION_WORD = {"PREMISE": LEFT, "CONSEQUENCE": RIGHT, "BOTH": EITHER}

# ENCODINGS.md §5.3.  Kept as a switch so the previews can state exactly what
# the one admitted predicate rewriting buys.
ALLOW_SIMPLEPROPS_COLLAPSE = True

QUESTION_UNIT_TYPES = ("question", "query")

EXACT_SUFFIX = "exact_suffix_removed"
NORMALIZED_SUFFIX = "normalized_suffix_removed"
SEPARATE_FIELD = "separate_question_field"
UNRESOLVED = "unresolved"

# How much of the stored question's wording the passage's final sentence has to
# carry before that sentence is treated as the same question.
QUESTION_MATCH_RATIO = 0.7


class PromptError(Exception):
    """The prompt layer cannot proceed.  Never worked around."""


# ------------------------------------------------------------ system prompt

def system_prompt():
    p = os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)
    with open(p) as f:
        return f.read()


def system_prompt_sha256():
    return hashlib.sha256(system_prompt().encode()).hexdigest()


def sha256_of(text):
    return hashlib.sha256((text or "").encode()).hexdigest()


# ----------------------------------------------------- WP2: passage/question

_SENTENCE = re.compile(r"[^.?!]*[.?!]+(?=\s|$)|[^.?!]+$")
_WORD = re.compile(r"[a-z0-9]+")


def stored_question(view):
    """The question as Stage 1 recorded it.

    `unifier_runtime.question_text` looks for a unit type containing
    "question"; the benchmarks in this pilot write `query`, so that function
    returns "" for all five preview cases and v4's `english_block` never added
    its `THE QUESTION:` line.  Both spellings are accepted here.
    """
    out = []
    for sent in view.get("stage1") or []:
        if not isinstance(sent, dict):
            continue
        for u in sent.get("units") or []:
            kind = str(u.get("type") or "").lower()
            if any(w in kind for w in QUESTION_UNIT_TYPES):
                t = (u.get("text") or "").strip()
                if t and t not in out:
                    out.append(t)
    return " ".join(out)


def _sentences(text):
    return [m.group(0).strip() for m in _SENTENCE.finditer(text or "")
            if m.group(0).strip()]


def _words(text):
    return [w for w in _WORD.findall((text or "").lower()) if not w.isdigit()]


def _containment(stored, sentence):
    """How much of the stored question's wording the sentence carries."""
    a, b = _words(stored), set(_words(sentence))
    if not a:
        return 0.0
    return sum(1 for w in a if w in b) / float(len(a))


def split_case_text(view):
    """-> {status, passage, question, stored_question, evidence}.

    The question is removed from the passage only when the passage's final
    sentence is demonstrably the same question: either the stored question is a
    literal suffix, or the final sentence is a question whose wording carries
    the stored question's words.  A final sentence is never deleted on the
    strength of ending in a question mark alone.
    """
    text = (view.get("input_text") or "").strip()
    stored = stored_question(view).strip()
    sents = _sentences(text)
    last = sents[-1] if sents else ""
    evidence = {"final_sentence": last,
                "final_sentence_is_a_question": last.endswith("?"),
                "containment": round(_containment(stored, last), 4)
                if stored else None,
                "match_ratio_required": QUESTION_MATCH_RATIO,
                "sentences": len(sents)}
    if not stored:
        return {"status": UNRESOLVED, "passage": text, "question": "",
                "stored_question": "", "evidence": dict(
                    evidence, why="Stage 1 recorded no question or query unit")}
    if text.endswith(stored):
        passage = text[:len(text) - len(stored)].strip()
        return {"status": EXACT_SUFFIX, "passage": passage, "question": stored,
                "stored_question": stored,
                "evidence": dict(evidence,
                                 why="the stored question is a literal suffix "
                                     "of the input text")}
    if last.endswith("?") and _containment(stored, last) >= QUESTION_MATCH_RATIO:
        passage = text[:len(text) - len(last)].strip()
        return {"status": NORMALIZED_SUFFIX, "passage": passage,
                "question": last, "stored_question": stored,
                "evidence": dict(evidence,
                                 why="the final sentence is a question "
                                     "carrying the stored question's wording; "
                                     "the passage's own wording is shown")}
    return {"status": SEPARATE_FIELD, "passage": text, "question": stored,
            "stored_question": stored,
            "evidence": dict(evidence,
                             why="no final sentence of the input text matches "
                                 "the stored question, so nothing was removed")}


# --------------------------------------------- WP4: the prompt-display check
#
# Named rewritings, and nothing else, may stand between a displayed atom and the
# clause literal it compiles to.

RULE_ENTITY_MARKER = "entity_marker"
RULE_LETTER_CASE = "label_case_folding"
RULE_TRAILING_CONTEXT = "trailing_context_argument"
RULE_SIMPLEPROPS = "simpleprops_degree_collapse"
RULE_MULTI_ALPHA = "multi_output_alpha_equal_variants"

DOCUMENTED_RULES = {
    RULE_ENTITY_MARKER: "conversion marks an entity constant `#:Tom 1`; the "
                        "constant is the same one (unifier_abstraction."
                        "_norm_constant)",
    RULE_LETTER_CASE: "conversion lower-cases a class or relation label; the "
                      "label is the same one (unifier_abstraction."
                      "_norm_constant)",
    RULE_TRAILING_CONTEXT: "conversion appends context arguments to the right "
                           "of the arguments the passage supplied "
                           "(ENCODINGS.md §6)",
    RULE_SIMPLEPROPS: "with `-simpleprops` a degree predicate at DEGREE "
                      "\"none\" becomes its non-gradable equivalent, dropping "
                      "the degree and relclass arguments (ENCODINGS.md §5.3); "
                      "admitted only at DEGREE \"none\", where no degree "
                      "information exists to lose",
    RULE_MULTI_ALPHA: "several converted literals that are the same literal up "
                      "to variable renaming",
}

CONTEXT_HEADS = ("$ctxt",)
CONTEXT_CONSTANTS = ("$c",)


def _is_context_argument(term):
    if isinstance(term, str):
        return UA.is_variable_term(term) or term in CONTEXT_CONSTANTS
    if isinstance(term, list) and term and str(term[0]) in CONTEXT_HEADS:
        return True
    return False


def _looks_generated(head):
    h = str(head)
    return bool(re.match(r"^sk[a-z0-9_]*$", h)) or h.startswith("$")


def _norm(term):
    return UA._norm_constant(term) if isinstance(term, str) else term


def _simpleprops_map(surface, converted_predicate):
    """The one documented predicate rewriting, at DEGREE "none" only."""
    if not ALLOW_SIMPLEPROPS_COLLAPSE:
        return None
    pred = str(surface[0])
    if pred == "has degree property" and converted_predicate == "has property" \
            and len(surface) == 5 and surface[3] == "none":
        return ["has property", surface[1], surface[2]]
    if pred == "has degree rel2" and converted_predicate == "is rel2" \
            and len(surface) == 6 and surface[4] == "none":
        return ["is rel2", surface[1], surface[2], surface[3]]
    return None


def _compare_arguments(surface_args, clause_args):
    """-> (reasons, rules).  Positionwise, up to a bijective variable renaming."""
    reasons, rules = [], []
    left, right = {}, {}

    def go(a, b, path):
        if isinstance(a, str) and UA.is_variable_term(a):
            if not (isinstance(b, str) and UA.is_variable_term(b)):
                reasons.append("argument %s: the variable became %s"
                               % (path, json.dumps(b)))
                return
            if left.setdefault(a, b) != b or right.setdefault(b, a) != a:
                reasons.append("argument %s: variables are not renamed "
                               "consistently" % path)
            return
        if isinstance(a, str):
            if isinstance(b, list):
                what = "generated term" if _looks_generated(b[0]) else "term"
                reasons.append("argument %s: %s became the %s %s"
                               % (path, json.dumps(a), what, json.dumps(b)))
                return
            if not isinstance(b, str):
                reasons.append("argument %s: unsupported term shape" % path)
                return
            if UA.is_variable_term(b):
                reasons.append("argument %s: the constant %s became a variable"
                               % (path, json.dumps(a)))
                return
            if a == b:
                return
            if _norm(a) == _norm(b):
                if a.replace("#:", "") != b.replace("#:", ""):
                    rules.append(RULE_LETTER_CASE)
                if ("#:" in a) != ("#:" in b):
                    rules.append(RULE_ENTITY_MARKER)
                return
            reasons.append("argument %s: %s became %s"
                           % (path, json.dumps(a), json.dumps(b)))
            return
        if isinstance(a, list):
            if not isinstance(b, list):
                reasons.append("argument %s: the term %s became %s"
                               % (path, json.dumps(a), json.dumps(b)))
                return
            if str(a[0]) != str(b[0]):
                reasons.append("argument %s: the nested form %s became %s"
                               % (path, json.dumps(a[0]), json.dumps(b[0])))
                return
            if len(a) != len(b):
                reasons.append("argument %s: the nested form %s changed arity"
                               % (path, json.dumps(a[0])))
                return
            for i, (x, y) in enumerate(zip(a[1:], b[1:])):
                go(x, y, "%s.%d" % (path, i + 1))
            return
        reasons.append("argument %s: unsupported term shape" % path)

    for i, (a, b) in enumerate(zip(surface_args, clause_args)):
        go(a, b, str(i + 1))
    return reasons, rules


def _same_multiset(a, b):
    return sorted(json.dumps(_norm(x), sort_keys=True) for x in a) == \
        sorted(json.dumps(_norm(x), sort_keys=True) for x in b)


def display_check(row):
    """May this candidate be displayed as the syntax the model should copy?

    -> {safe, reasons, rules_applied, detail}.  `safe` is False unless every
    difference between the displayed atom and the clause literal it compiles to
    is explained by a rule in `DOCUMENTED_RULES`.
    """
    surface = row["surface_atom"]
    sign = row["sign"]
    literal = row.get("gk_form")
    variants = row.get("all_converted_literals") or ([literal] if literal
                                                     else [])
    reasons, rules = [], []
    if not literal:
        return {"safe": False, "reasons": ["the atom converts to no clause "
                                           "literal"], "rules_applied": [],
                "detail": {}}
    if len(variants) > 1:
        keys = set(UA.alpha_key(v) for v in variants)
        if len(keys) > 1:
            reasons.append("one surface atom compiles to %d different content "
                           "clauses (%s), so the displayed line does not say "
                           "what writing it asserts"
                           % (len(variants),
                              "; ".join(json.dumps(v) for v in variants)))
        else:
            rules.append(RULE_MULTI_ALPHA)
    if UA.sign_of(literal) != sign:
        reasons.append("polarity: the %s atom compiles to a %s literal"
                       % ("negated" if sign == "-" else "positive",
                          "negative" if UA.sign_of(literal) == "-"
                          else "positive"))
    atom = UA.unsigned_atom(literal)
    pred, converted_pred = str(surface[0]), str(atom[0])
    compare = surface
    if pred != converted_pred:
        mapped = _simpleprops_map(surface, converted_pred)
        if mapped is None:
            reasons.append("predicate: `%s` compiles to `%s`"
                           % (pred, converted_pred))
        else:
            rules.append(RULE_SIMPLEPROPS)
            compare = mapped
    surface_args, clause_args = list(compare[1:]), list(atom[1:])
    if len(clause_args) < len(surface_args):
        reasons.append("conversion dropped %d argument(s)"
                       % (len(surface_args) - len(clause_args)))
    else:
        extra = clause_args[len(surface_args):]
        if extra:
            if all(_is_context_argument(t) for t in extra):
                rules.append(RULE_TRAILING_CONTEXT)
            else:
                reasons.append("conversion added the argument(s) %s, which are "
                               "not context slots"
                               % "; ".join(json.dumps(t) for t in extra))
        got, used = _compare_arguments(surface_args,
                                       clause_args[:len(surface_args)])
        if got:
            slot = AO.LABEL_SLOT.get(str(compare[0]))
            if slot is not None and slot < len(surface_args) \
                    and slot < len(clause_args) \
                    and _norm(surface_args[slot]) != _norm(clause_args[slot]):
                got = ["content label: `%s` compiles to `%s`"
                       % (surface_args[slot], clause_args[slot])] + got
            elif _same_multiset(surface_args, clause_args[:len(surface_args)]):
                got = ["argument order: the same arguments appear in a "
                       "different order"] + got
            reasons.extend(got)
        rules.extend(used)
    ordered, seen = [], set()
    for r in rules:
        if r not in seen:
            seen.add(r)
            ordered.append(r)
    return {"safe": not reasons, "reasons": reasons, "rules_applied": ordered,
            "detail": {"surface_atom": surface, "sign": sign,
                       "compiled_literal": literal,
                       "all_compiled_literals": variants,
                       "compared_as": compare if compare is not surface
                       else None}}


# ---------------------------------------------------- WP3: FOCUS and HELPER

def _all_variable_term(term):
    if isinstance(term, str):
        return UA.is_variable_term(term)
    if isinstance(term, list) and term:
        return all(_all_variable_term(x) for x in term[1:])
    return False


def is_structural(atom):
    """A bare event-role or unlabelled frame atom: a connector, not a concept.

    `AO.ROLE_PREDS` is the pipeline's own list of event-role predicates.  An
    atom is structural only when it also carries NO content: every argument is a
    variable, or a generated term over variables such as `$ev_of(?X,?Y,?Z)`.
    `have(?X,?Y)` and `typical(?X)` are therefore not structural, which is what
    the audit asks for.
    """
    pred = str(atom[0])
    args = list(atom[1:])
    if pred in AO.ROLE_PREDS:
        return all(_all_variable_term(a) for a in args)
    slot = AO.LABEL_SLOT.get(pred)
    if slot is not None and slot < len(args) \
            and isinstance(args[slot], str) and UA.is_variable_term(args[slot]):
        return all(_all_variable_term(a) for a in args)
    return False


# --------------------------------------------------------- WP3: the grouping

def _merge_position(positions):
    """LEFT and RIGHT together mean either position may be useful."""
    got = set(positions)
    if len(got) == 1:
        return got.pop()
    if EITHER in got or (LEFT in got and RIGHT in got):
        return EITHER
    return got.pop()


def _merge_cost(rows):
    """The minimum only for truly equivalent compiled forms; else the maximum."""
    costs = [r["priority_cost"] for r in rows]
    shapes = set(UA.alpha_key(r["gk_form"]) for r in rows if r.get("gk_form"))
    if len(shapes) <= 1:
        return min(costs), "minimum over equivalent compiled forms"
    return max(costs), ("maximum: these rows compile to %d different literals"
                        % len(shapes))


def group_candidates(rows):
    """-> (groups, omitted).  One group per unsigned surface atom.

    Only rows that pass `display_check` are grouped; a group all of whose rows
    were rejected does not exist.
    """
    safe, omitted = [], []
    for row in rows:
        got = display_check(row)
        if got["safe"]:
            safe.append((row, got))
            continue
        omitted.append({"candidate_id": row.get("id"),
                        "printed": row.get("printed"),
                        "sign": row["sign"],
                        "surface_atom": row["surface_atom"],
                        "compiled_literal": row.get("gk_form"),
                        "all_compiled_literals":
                            row.get("all_converted_literals"),
                        "origin": row.get("origin"),
                        "role": row.get("role"),
                        "priority_cost": row.get("priority_cost"),
                        "reason": got["reasons"][0],
                        "reasons": got["reasons"],
                        "rules_applied": got["rules_applied"]})
    buckets = {}
    for row, got in safe:
        display = UA.display_atom(row["surface_atom"])
        key = json.dumps(display, ensure_ascii=False)
        b = buckets.setdefault(key, {"display": display, "rows": []})
        b["rows"].append((row, got))
    groups = []
    for key in sorted(buckets):
        b = buckets[key]
        signs, notes = {}, []
        for name, symbol in ((POSITIVE, "+"), (NEGATED, "-")):
            mine = [(r, g) for r, g in b["rows"] if r["sign"] == symbol]
            if not mine:
                continue
            positions = [POSITION_WORD[r["role"]] for r, _g in mine]
            cost, why = _merge_cost([r for r, _g in mine])
            if len(mine) > 1:
                notes.append("%s: %d source rows merged (%s), positions %s, "
                             "costs %s; %s"
                             % (name, len(mine),
                                ", ".join(r["id"] for r, _g in mine),
                                "/".join(positions),
                                "/".join(str(r["priority_cost"])
                                         for r, _g in mine), why))
            signs[name] = {
                "position": _merge_position(positions),
                "cost": cost,
                "source_candidate_ids": [r["id"] for r, _g in mine],
                "source_positions": positions,
                "source_costs": [r["priority_cost"] for r, _g in mine],
                "source_roles": [r["role"] for r, _g in mine],
                "compiled_literals": [r["gk_form"] for r, _g in mine],
                "display_rules_applied": sorted(set(
                    x for _r, g in mine for x in g["rules_applied"])),
                "origins": sorted(set(r["origin"] for r, _g in mine)),
                "cost_merge": why,
            }
        question_linked = any(r["question_linked"] for r, _g in b["rows"])
        content = any(not is_structural(r["surface_atom"])
                      for r, _g in b["rows"])
        groups.append({
            "atom": b["display"],
            "printed": json.dumps(b["display"], ensure_ascii=False),
            "kind": FOCUS if (question_linked or content) else HELPER,
            "question_linked": question_linked,
            "carries_content": content,
            "signs": signs,
            "source_candidate_ids": sorted(
                (r["id"] for r, _g in b["rows"]),
                key=lambda i: (i[0], int(re.sub(r"\D", "", i) or 0))),
            "min_cost": min(s["cost"] for s in signs.values()),
            "merge_notes": notes,
        })
    groups.sort(key=lambda g: (0 if g["question_linked"] else 1,
                               g["min_cost"], g["printed"]))
    focus = [g for g in groups if g["kind"] == FOCUS]
    helper = [g for g in groups if g["kind"] == HELPER]
    for i, g in enumerate(focus, start=1):
        g["id"] = "F%d" % i
    for i, g in enumerate(helper, start=1):
        g["id"] = "H%d" % i
    return focus + helper, omitted


# ------------------------------------------------------------ WP3: rendering

FOCUS_HEADING = "FOCUS ATOMS — every rule must use at least one:"
HELPER_HEADING = "HELPER ATOMS — use only together with a focus atom:"
NO_FOCUS_NOTE = ("No atom of this case qualified as a focus atom, so a rule may "
                 "use the atoms below on their own.")
CLOSING_LINE = "Write the missing bridge rules now."


def render_group(group):
    lines = ["  %-4s %s" % (group["id"], group["printed"])]
    for name in (POSITIVE, NEGATED):
        s = group["signs"].get(name)
        if not s:
            continue
        lines.append("       %-9s %s, COST %d"
                     % (name + ":", s["position"], s["cost"]))
    return "\n".join(lines)


def render_candidates(groups):
    focus = [g for g in groups if g["kind"] == FOCUS]
    helper = [g for g in groups if g["kind"] == HELPER]
    parts = []
    if focus:
        parts.append("%s\n\n%s" % (FOCUS_HEADING,
                                   "\n\n".join(render_group(g)
                                               for g in focus)))
    if helper:
        head = HELPER_HEADING if focus else "%s\n\n%s" % (HELPER_HEADING,
                                                          NO_FOCUS_NOTE)
        parts.append("%s\n\n%s" % (head, "\n\n".join(render_group(g)
                                                     for g in helper)))
    return "\n\n".join(parts)


def render_case(split):
    return "\n".join(["CASE", "",
                      "PASSAGE (facts and rules):", split["passage"], "",
                      "QUESTION (not a fact):", split["question"]])


def render_attempted(rules, refusals):
    lines = ["RULES ALREADY TRIED", ""]
    for r in rules:
        lines.append("  %-4s %s" % (r.get("rule_id"), r.get("printed")))
    if not rules:
        lines.append("  (none)")
    if refusals:
        lines += ["", "OF THOSE, THE PROGRAM COULD NOT USE:", ""]
        for r in refusals:
            lines.append("  %-4s %s — %s" % (r.get("rule_id"),
                                             r.get("printed"), r.get("why")))
    return "\n".join(lines)


NO_PROOF_BLOCK = """RESULT OF THE PREVIOUS TRY

GK found no proof. This does not make any attempted rule false. Propose missing
or corrected connections. Do not repeat the rules listed below."""

ALTERNATIVE_BLOCK = """RESULT OF THE PREVIOUS TRY

GK found a proof. Propose different, independently reasonable connections so
the prover can search for another proof. Do not repeat the rules listed below."""


# ------------------------------------------------------------ WP5: the three

def _forbidden(text):
    """Nothing from the scored side of the experiment may reach a prompt."""
    import alignment_protocol as P
    P.assert_no_leak(text, extra_forbidden=("reviewed", "accepted answer",
                                            "expected answer", "gold"))
    banned = ("MAIN CANDIDATES", "SECONDARY CANDIDATES", "USE: PREMISE",
              "USE: CONSEQUENCE", "PRIORITY COST", "GK FORM", "same as before")
    bad = [b for b in banned if b in text]
    if bad:
        raise PromptError("prompt carries retired wording: %s" % bad)
    return True


def _record(call, view, rows, blocks, split, groups, omitted):
    text = "\n\n".join(b for b in blocks if b)
    _forbidden(text)
    _forbidden(system_prompt())
    candidate_block = render_candidates(groups)
    return {
        "call": call,
        "version": VERSION,
        "case_id": view.get("case_id"),
        "system_prompt_name": SYSTEM_PROMPT_NAME,
        "system_prompt_sha256": system_prompt_sha256(),
        "text": text,
        "sha256": sha256_of(text),
        "chars": len(text),
        "question_split": split,
        "candidate_block": candidate_block,
        "candidate_block_sha256": sha256_of(candidate_block),
        "groups": groups,
        "omitted_candidates": omitted,
        "counts": {
            "source_candidate_rows": len(rows),
            "displayed_rows": sum(len(s["source_candidate_ids"])
                                  for g in groups
                                  for s in g["signs"].values()),
            "omitted_rows": len(omitted),
            "groups": len(groups),
            "focus_groups": sum(1 for g in groups if g["kind"] == FOCUS),
            "helper_groups": sum(1 for g in groups if g["kind"] == HELPER),
        },
    }


def _rows_of(v4_candidates):
    return list(v4_candidates.get("main") or []) + \
        list(v4_candidates.get("secondary") or [])


def build_initial_user_prompt(view, v4_candidates):
    rows = _rows_of(v4_candidates)
    groups, omitted = group_candidates(rows)
    split = split_case_text(view)
    blocks = [render_case(split), render_candidates(groups), CLOSING_LINE]
    return _record("initial", view, rows, blocks, split, groups, omitted)


def _followup(call, block, view, v4_candidates, attempted_rules,
              compiler_refusals):
    rows = _rows_of(v4_candidates)
    groups, omitted = group_candidates(rows)
    split = split_case_text(view)
    blocks = [render_case(split), block,
              render_attempted(attempted_rules or [], compiler_refusals or []),
              render_candidates(groups), CLOSING_LINE]
    return _record(call, view, rows, blocks, split, groups, omitted)


def build_no_proof_user_prompt(view, v4_candidates, attempted_rules,
                               compiler_refusals):
    return _followup("no_proof", NO_PROOF_BLOCK, view, v4_candidates,
                     attempted_rules, compiler_refusals)


def build_alternative_user_prompt(view, v4_candidates, attempted_rules,
                                  compiler_refusals):
    return _followup("alternative", ALTERNATIVE_BLOCK, view, v4_candidates,
                     attempted_rules, compiler_refusals)
