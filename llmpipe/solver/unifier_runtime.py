"""The unifier-driven abstraction pipeline, end to end (WP6-WP8).

    stored parse
      -> conservative front door (stored options)            answered? STOP
      -> signed clause literals, ordered by resolution partners  (WP1-WP3)
      -> one LLM call for `RULE:` lines                          (WP3, WP9)
      -> deterministic parse, validation, compilation            (WP4, WP5)
      -> ONE pooled gk world per round, all rules at once        (WP6)
      -> every returned proof kept; cited sets minimised by replay (WP7)
      -> the rules a proof used are graded, after the fact         (WP8)

Three properties this module is built around:

**Proof first.**  Nothing semantic filters a rule before gk.  The only refusals
before the prover are mechanical (`simple_rule_parser`), and a rule that looks
reversed, over-general or doubtful is compiled and tried.  What a grade can do
is label a proof; it can never withdraw one, and a low grade never turns a found
proof into `Unknown`.

**Pooled.**  All accepted rules go into one world, so gk can combine two or
three abstractions where no single-rule world could.  gk may return several
proofs from one call and all of them are kept, not just the first.

**No fabricated number.**  A bridge clause is full confidence with its `$block`;
the only gk option that changes is the proof-return threshold, recorded on every
call.  A proof is reported with gk's own confidence, the number of invented
rules it used, and their grades — not with a weight multiplied into anything.
"""

import hashlib
import json
import os
import re

import bridge_world as BW
import dynamic_score as DS
import simple_rule_compiler as SC
import simple_rule_parser as SP
import unifier_abstraction as UA

# 1.1 (v2 of the pilot): a rule the converter turns into no clause is refused
# and named instead of raising.  In 1.0 the pool was compiled in one call, so
# one such rule — `has time`, the tense slot — ended four cases of the first
# 50-case run.  Nothing else changed: the same prompt, ordering, validation,
# caps and gk options.
VERSION = "unifier_runtime/1.1"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")

RULES_PROMPT = "unifier_rules_v1"
GRADE_PROMPT = "grade_used_rules_v1"

MAX_ROUNDS = 3
POOL_CAP = 36
MAX_EXCLUSION_WORLDS = 3

# A bridge clause is full confidence.  `bridge_world` requires a weight in
# (0, 1] on a hypothesis; 1.0 is the one value that changes nothing, and no
# weight is applied to a proof either.  What a proof reports is gk's own
# confidence, how many invented rules it used, and their grades.
WEIGHT = 1.0
WEIGHT_POLICY = ("no weight is applied anywhere: the clause is full confidence "
                 "and the reported result carries gk's own confidence, the "
                 "number of invented rules, and their post-proof grades")

BACKGROUNDS = ("none", "english", "english_stage1")

FOCUSED_NOTE = (
    "Look especially for literal patterns that express the same or a closely "
    "related concept in different words or structures. Propose the implication "
    "direction that would connect them. Also include a simple "
    "ordinary-background implication when it is needed to join the "
    "representations.")

GRADES = ("LIKELY", "PLAUSIBLE", "UNCERTAIN", "UNLIKELY", "FALSE")
UNASSESSED = "UNASSESSED"
GRADE_ORDER = ["LIKELY", "PLAUSIBLE", UNASSESSED, "UNCERTAIN", "UNLIKELY",
               "FALSE"]
BAD_GRADES = ("UNLIKELY", "FALSE")

GRADE_LINE = re.compile(r"^\s*[-*#>\s]*grade\s+(R\d+)\s*[:=]\s*([A-Za-z_]+)"
                        r"\s*[;.,]?\s*(.*)$", re.I)


class RuntimeError_(Exception):
    """The runtime cannot proceed.  Never worked around."""


# ---------------------------------------------------------------- prompts

def prompt_text(name):
    with open(os.path.join(PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_sha(name):
    return hashlib.sha256(prompt_text(name).encode()).hexdigest()


def component_hashes():
    """Everything this experiment freezes, hashed before the first live call."""
    out = {}
    for mod in ("unifier_abstraction", "simple_rule_parser",
                "simple_rule_compiler", "unifier_runtime", "bridge_world",
                "dynamic_score", "option_scope", "alignment_occurrences"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    for name in (RULES_PROMPT, GRADE_PROMPT):
        out["prompts/dynamic_alignment/%s.txt" % name] = prompt_sha(name)
    ax = os.path.join(ROOT, "axioms_std.js")
    out["axioms_std.js"] = hashlib.sha256(open(ax, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------------- the rounds

def rounds_of(display, max_rounds=MAX_ROUNDS, cap=UA.MAX_TEMPLATES):
    """Split the ordered templates into at most `max_rounds` displayed blocks.

    Every round shows all question components and their complements; the rest
    of each round's slots go to the next block of ordinary templates, scarcest
    partners first.  A round with no new template is not run and says so.
    """
    mandatory = display["ordered"]["mandatory"]
    rest = display["ordered"].get("ranked") or display["ordered"]["shown"]
    room = display["ordered"].get("per_call_room") or max(
        1, cap - len(mandatory))
    out = []
    for i in range(max_rounds):
        block = rest[i * room:(i + 1) * room]
        out.append({"round": i + 1, "mandatory": mandatory, "block": block,
                    "new_templates": len(block),
                    "block_ids": [t["display_id"] for t in block],
                    "templates_shown": len(mandatory) + len(block),
                    "still_not_shown": max(0, len(rest) - (i + 1) * room)})
        if (i + 1) * room >= len(rest):
            break
    return out


def render_round(rnd):
    return "\n".join(UA.render_line(r) for r in rnd["mandatory"] + rnd["block"])


def question_text(view):
    """The question sentence, from Stage 1's own unit types where it says one."""
    out = []
    for sent in view.get("stage1") or []:
        if not isinstance(sent, dict):
            continue
        for u in sent.get("units") or []:
            if "question" in str(u.get("type") or "").lower():
                t = (u.get("text") or "").strip()
                if t and t not in out:
                    out.append(t)
    return " ".join(out)


def rules_prompt_parts(view, rnd, background="none", focused=False,
                       compact_units=None):
    """-> (instructions, body).  The one prompt the abstraction model sees.

    The literal block is identical across background arms; only the block above
    it changes, which is what WP9 compares.
    """
    import alignment_protocol as P
    if background not in BACKGROUNDS:
        raise RuntimeError_("unknown background %r" % background)
    parts = []
    if background in ("english", "english_stage1"):
        parts.append("THE ORIGINAL PROBLEM\n\n%s"
                     % (view.get("input_text") or "").strip())
    if background == "english_stage1":
        compact = UA.compact_stage1(view.get("stage1"), cap_units=compact_units)
        block = compact["text"]
        if compact["omitted_units"]:
            block += ("\n  (%d further units are not shown: %s)"
                      % (len(compact["omitted_units"]),
                         ", ".join(compact["omitted_units"])))
        parts.append("WHAT THE FIRST TRANSLATION STAGE FOUND\n\n%s" % block)
    parts.append("THE PATTERNS\n\n%s" % render_round(rnd))
    body = "\n\n".join(parts)
    instructions = prompt_text(RULES_PROMPT)
    if focused:
        instructions += "\n\nONE MORE THING\n\n%s\n" % FOCUSED_NOTE
    P.assert_no_leak(instructions + "\n\n" + body,
                     extra_forbidden=("reviewed", "accepted answer",
                                      "expected answer", "gold"))
    return instructions, body


def rules_prompt(view, rnd, background="none", focused=False,
                 compact_units=None):
    instructions, body = rules_prompt_parts(view, rnd, background=background,
                                            focused=focused,
                                            compact_units=compact_units)
    return instructions + "\n\n" + body


# ------------------------------------------------------------ the gk worlds

def _cited_clause_names(proof_lists):
    names = []
    for step in DS._steps(proof_lists):
        for n in DS._names_in(step):
            if n not in names:
                names.append(n)
    return names


def proofs_of(raw, provenance):
    """Every proof gk returned, not only answer index zero.

    A returned answer that cites no dynamic hypothesis is kept and marked: it is
    a search-order or base-theory result, not a dynamic-abstraction proof.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = {}
    out = []
    for i, a in enumerate((raw or {}).get("answers") or []):
        proof_lists, kinds = [], []
        for key in ("positive proof", "negative proof", "proof"):
            if a.get(key):
                proof_lists.append(a[key])
                kinds.append(key)
        used, by_hyp = DS.cited_hypotheses(proof_lists, provenance)
        out.append({
            "answer_index": i,
            "answer": a.get("answer"),
            "gk_native_confidence": a.get("confidence"),
            "proof_kinds": kinds,
            "proof_steps": sum(len(p) for p in proof_lists),
            "cited_clause_names": _cited_clause_names(proof_lists),
            "cited_hypothesis_ids": list(used),
            "cited_clauses_by_hypothesis": {h: by_hyp[h] for h in used},
            "cites_no_dynamic_hypothesis": not used,
            "blockers": a.get("blockers"),
            "proof": proof_lists,
        })
    return out


def run_world(view, rules, gk, configuration, world_id, tag):
    """Compile a pool of rules, append them to the STORED theory, ask gk.

    A rule the converter turns into no clause is refused here and named; the
    rest of the pool still goes to gk.  If nothing compiles there is nothing to
    ask, and the world says so instead of sending the base theory alone under a
    dynamic label.
    """
    world = SC.build_world(world_id, rules, view, configuration, weight=WEIGHT)
    if world["nothing_compiled"]:
        return {"world_id": world_id, "tag": tag,
                "rules_offered": [r["rule_id"] for r in rules],
                "refused_by_the_compiler": world["refused_by_the_compiler"],
                "skipped": "no rule of this pool converted to a clause",
                "proofs": [], "dynamic_proofs": [], "answers_returned": 0,
                "bridge_clause_count": 0}, world
    clauses = list(view["final_clauses"]) + [
        dict(c) for c in world["compiled_bridge_clauses"]]
    stored = {"stage1": view["stage1"], "stage2": view["stage2"],
              "final_clauses": view["final_clauses"],
              "input_text": view["input_text"]}
    got = gk(clauses, stored, tag, dynamic=True)
    proofs = proofs_of(got.get("raw") or "{}", world["clause_provenance"])
    printed = world["printed_by_hypothesis_id"]
    for p in proofs:
        p["cited_rules"] = [world["rule_by_hypothesis_id"].get(h)
                            for h in p["cited_hypothesis_ids"]]
        p["cited_formulas"] = [printed.get(h)
                               for h in p["cited_hypothesis_ids"]]
    return {
        "world_id": world_id, "tag": tag,
        "rules_offered": [r["rule_id"] for r in rules],
        "refused_by_the_compiler": world["refused_by_the_compiler"],
        "hypotheses_offered": world["hypotheses_in_this_world"],
        "bridge_clause_count": len(world["compiled_bridge_clauses"]),
        "clause_confidence_annotations": [
            c.get("@confidence") for c in world["compiled_bridge_clauses"]],
        "all_clauses_have_block": BW.has_block(
            world["compiled_bridge_clauses"]),
        "clause_provenance": world["clause_provenance"],
        "printed_by_hypothesis_id": printed,
        "proofs": proofs,
        "answers_returned": len(proofs),
        "dynamic_proofs": [p for p in proofs
                           if not p["cites_no_dynamic_hypothesis"]],
        "conservative_formatter_answer": got.get("answer"),
        "gk_thresholds": got.get("thresholds"),
        "seconds": got.get("seconds"),
        "error": got.get("error"),
    }, world


def _world_record(world):
    """The world as the case record keeps it: no clause map, no proof steps.

    The steps are gk's own and can run to hundreds of lines per proof; what a
    reader needs is the answer, its confidence and what it cited, all of which
    stay.
    """
    out = dict((k, v) for k, v in world.items()
               if k not in ("clause_provenance", "proofs", "dynamic_proofs"))
    out["proofs"] = [dict((x, y) for x, y in p.items() if x != "proof")
                     for p in world.get("proofs") or []]
    out["dynamic_proof_count"] = len(world.get("dynamic_proofs") or [])
    return out


def _q_atoms(display):
    return [r["atom"] for r in display["ordered"]["mandatory"]]


def _head_meets_question(rule, q_atoms):
    head = UA._to_clause_shape(rule["head"]["atom"])
    for q in q_atoms:
        if UA.unify_unsigned_atoms(head, UA._to_clause_shape(q))["unifiable"]:
            return True
    return False


def pool_for_round(rules, q_atoms, cap=POOL_CAP):
    """-> (the rules gk sees, the rules the cap left out).

    Rules whose conclusion meets a question component or its complement go
    first; the rest keep the order the model returned them in.  Nothing is
    dropped for being doubtful.
    """
    first = [r for r in rules if _head_meets_question(r, q_atoms)]
    rest = [r for r in rules if r not in first]
    ordered = first + rest
    return ordered[:cap], [{"rule_id": r["rule_id"], "printed": r["printed"],
                            "why": "beyond the %d-rule pool cap" % cap}
                           for r in ordered[cap:]]


# ------------------------------------------------------ minimisation (WP7)

def _same_answer(proofs, answer):
    return [p for p in proofs if p["answer"] == answer]


def minimise(view, gk, configuration, case_id, rules_by_id, proof, budget):
    """Replay the cited set, then delete one rule at a time.

    Deletion-minimal, not globally minimum: a smaller set of DIFFERENT rules may
    also prove the answer, and this search never looks for one.
    """
    cited = [rules_by_id[r] for r in proof["cited_rules"] if r in rules_by_id]
    if not cited:
        return {"minimised": False,
                "why": "the proof cites no dynamic hypothesis, so there is no "
                       "invented rule set to minimise",
                "cited_rules": proof["cited_rules"]}
    if not budget():
        return {"minimised": False, "why": "gk budget reached before the replay",
                "cited_rules": proof["cited_rules"]}
    replay, _w = run_world(view, cited, gk, configuration,
                           "replay_%s" % case_id, "%s/replay" % case_id)
    kept = _same_answer(replay["proofs"], proof["answer"])
    if not kept:
        return {"minimised": False, "cited_rules": proof["cited_rules"],
                "replay_answers": [p["answer"] for p in replay["proofs"]],
                "why": "the cited set alone did not reproduce the answer"}
    keep, deletions = list(cited), []
    for r in list(cited):
        if len(keep) <= 1 or not budget():
            break
        trial = [x for x in keep if x["rule_id"] != r["rule_id"]]
        got, _w = run_world(view, trial, gk, configuration,
                            "min_%s_no_%s" % (case_id, r["rule_id"]),
                            "%s/without %s" % (case_id, r["rule_id"]))
        still = _same_answer(got["proofs"], proof["answer"])
        deletions.append({"removed": r["rule_id"], "printed": r["printed"],
                          "answer_without_it": [p["answer"]
                                                for p in got["proofs"]][:3],
                          "removing_it_destroys_the_proof": not still})
        if still:
            keep = trial
    return {"minimised": True,
            "cited_rules": proof["cited_rules"],
            "minimal_rules": [r["rule_id"] for r in keep],
            "minimal_printed": [r["printed"] for r in keep],
            "size": len(keep),
            "replay_reproduced": True,
            "deletions": deletions,
            "note": "deletion-minimal, not globally minimum"}


def order_proofs(rows):
    """Fewer invented rules, then higher gk confidence, then stable id order."""
    def key(row):
        conf = row.get("gk_native_confidence")
        return (row.get("size") if row.get("size") is not None
                else len(row.get("cited_rules") or []),
                -(conf if isinstance(conf, (int, float)) else 0.0),
                ",".join(sorted(row.get("minimal_rules")
                                or row.get("cited_rules") or [])))
    return sorted(rows, key=key)


# ----------------------------------------------------------- grading (WP8)

def grade_prompt(view, rules):
    import alignment_protocol as P
    L = ["THE PASSAGE", "", (view.get("input_text") or "").strip(), ""]
    q = question_text(view)
    if q:
        L += ["THE QUESTION IT ASKS", "", q, ""]
    L += ["THE INVENTED RULES THE PROOF USED", ""]
    for r in rules:
        L.append("  %s  %s" % (r["rule_id"], r["printed"]))
    L.append("")
    prompt = prompt_text(GRADE_PROMPT) + "\n\n" + "\n".join(L)
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def parse_grades(text, rule_ids):
    """Only `GRADE` lines are read.  A missing grade is UNASSESSED, not a pass."""
    got, bad = {}, []
    for raw in (text or "").splitlines():
        m = GRADE_LINE.match(raw.strip())
        if not m:
            continue
        rid, value, reason = m.group(1).upper(), m.group(2).upper(), m.group(3)
        if rid not in rule_ids:
            bad.append({"line": raw.strip()[:160], "why": "unknown rule id"})
            continue
        if value not in GRADES:
            bad.append({"line": raw.strip()[:160],
                        "why": "unknown grade %r" % value[:20]})
            continue
        got[rid] = {"grade": value, "reason": reason.strip()[:300],
                    "explicitly_graded": True}
    for rid in rule_ids:
        got.setdefault(rid, {"grade": UNASSESSED, "reason": "",
                             "explicitly_graded": False,
                             "note": "no readable grade; UNASSESSED is not "
                                     "approval and does not delete a proof"})
    return {"grades": got, "rejected": bad,
            "readable": any(v["explicitly_graded"] for v in got.values()),
            "graded": sum(1 for v in got.values() if v["explicitly_graded"]),
            "total": len(rule_ids)}


def worst_grade(grades, rule_ids):
    """The summary of a proof: the worst grade among the rules it used."""
    values = [grades.get(r, {}).get("grade", UNASSESSED) for r in rule_ids]
    if not values:
        return None
    return max(values, key=lambda g: GRADE_ORDER.index(g)
               if g in GRADE_ORDER else GRADE_ORDER.index(UNASSESSED))


def grade_rules(view, rules, respond, case_id):
    ids = [r["rule_id"] for r in rules]
    if not ids:
        return {"asked": False, "why": "no rule was used by any proof",
                "grades": {}}
    prompt = grade_prompt(view, rules)
    text, note = respond("grade", case_id, prompt)
    parsed = parse_grades(text, ids)
    return {"asked": True, "raw": text, "note": note,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "grades": parsed["grades"], "rejected": parsed["rejected"],
            "readable": parsed["readable"], "graded": parsed["graded"],
            "total": parsed["total"]}


# ------------------------------------------------------------------ driver

def run_case(view, respond, gk, bounds=None, background="english",
             focused=False, max_rounds=MAX_ROUNDS, pool_cap=POOL_CAP,
             do_minimise=True, do_grade=True, do_exclusions=True,
             configuration=None, template_cap=UA.MAX_TEMPLATES):
    """One case, front door to graded proofs.  Every stop is recorded."""
    import dynamic_runtime as RT
    bounds = bounds or {}
    budget = bounds.get("gk_budget", lambda: True)
    configuration = configuration or view["configuration"]
    case_id = view["case_id"]
    trace = [{"stage": "front_door"}]
    front = RT.front_door(view, gk)
    result = {"case_id": case_id, "mode": "unifier_abstraction",
              "version": VERSION, "view_sha256": RT.view_hash(view),
              "background_arm": background, "focused_instruction": focused,
              "conservative": front, "trace": trace,
              "dynamic_work_done": False, "weight_policy": WEIGHT_POLICY}
    if front["resolved"]:
        trace.append({"stage": "stopped",
                      "why": "the conservative front door answered %r; no "
                             "abstraction LLM call and no dynamic gk call were "
                             "made" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result
    result["dynamic_work_done"] = True

    trace.append({"stage": "literals"})
    display = UA.build_display(view, cap=template_cap)
    result["literals"] = {
        "counts": display["inventory"]["counts"],
        "control_predicates_excluded":
            display["inventory"]["control_predicates_excluded"],
        "question_components": display["question_components"],
        "templates_shown": display["templates_shown"],
        "templates_omitted": display["ordered"]["omitted"],
        "counted_literals_without_a_stage2_template":
            display["ordered"]["counted_literals_without_a_stage2_template"],
        "unmappable_question_components": [
            {"atom": r["atom"], "sign": r["sign"],
             "why": r["mapping_unavailable_because"]}
            for r in display["ordered"]["mandatory"]
            if r["mapping_unavailable_because"]],
        "display_block": display["block"],
        "vocabulary": display["vocabulary"],
    }
    if not display["ordered"]["mandatory"]:
        trace.append({"stage": "stopped",
                      "why": "no question content atom could be extracted"})
        result["stopped_at"] = "no_question_component"
        return result

    source_rules = SP.stage2_source_rules(view["stage2"])
    q_atoms = _q_atoms(display)
    rules, rounds_run, worlds = [], [], []
    stopped = None
    for rnd in rounds_of(display, max_rounds=max_rounds, cap=template_cap):
        trace.append({"stage": "round_%d" % rnd["round"]})
        if rnd["round"] > 1 and not rnd["new_templates"]:
            rounds_run.append({"round": rnd["round"],
                               "skipped": "no further literal to show"})
            break
        prompt = rules_prompt(view, rnd, background=background,
                              focused=focused)
        text, note = respond("rules", "%s/r%d" % (case_id, rnd["round"]),
                             prompt)
        # each round is validated against the vocabulary THAT CALL showed, so a
        # word only a later block carries cannot be used before it is shown
        vocab = UA.vocabulary_for(display, rnd["block"],
                                  display.get("entity_ids") or ())
        parsed = SP.parse_response(text, vocab, source_rules)
        rules, added = SP.merge(rules, parsed["accepted"])
        row = {"round": rnd["round"],
               "templates_shown": rnd["templates_shown"],
               "new_templates": rnd["new_templates"],
               "still_not_shown": rnd.get("still_not_shown"),
               "prompt_chars": len(prompt),
               "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
               "llm_note": note,
               "raw": text,
               "readable_rule_lines": parsed["readable_lines"],
               "accepted_here": [r["printed"] for r in parsed["accepted"]],
               "new_here": [r["rule_id"] for r in added],
               "rejected": parsed["rejected"],
               "over_cap": parsed["over_cap"],
               "rules_so_far": len(rules)}
        if not rules:
            row["no_world"] = "no rule has been accepted yet"
            rounds_run.append(row)
            continue
        if not budget():
            row["no_world"] = "gk budget reached"
            rounds_run.append(row)
            stopped = "gk_budget"
            break
        pool, dropped = pool_for_round(rules, q_atoms, cap=pool_cap)
        row["pool"] = [r["rule_id"] for r in pool]
        row["pool_omitted"] = dropped
        got, _world = run_world(view, pool, gk, configuration,
                                "pool_%s_r%d" % (case_id, rnd["round"]),
                                "%s/round %d" % (case_id, rnd["round"]))
        got["round"] = rnd["round"]
        worlds.append(got)
        row["answers_returned"] = got["answers_returned"]
        row["dynamic_proofs"] = len(got["dynamic_proofs"])
        row["refused_by_the_compiler"] = got.get("refused_by_the_compiler")
        if got.get("skipped"):
            row["no_world"] = got["skipped"]
        rounds_run.append(row)
        if got["dynamic_proofs"]:
            break
    result["rounds"] = rounds_run
    result["rules"] = [{"rule_id": r["rule_id"], "printed": r["printed"],
                        "canonical": r["canonical"], "lines": r["lines"],
                        "body": r["body"], "head": r["head"]} for r in rules]
    result["worlds"] = [_world_record(w) for w in worlds]
    if not rules:
        trace.append({"stage": "stopped",
                      "why": "the model proposed no rule that survived the "
                             "mechanical checks"})
        result["stopped_at"] = stopped or "no_rule_accepted"
        return result

    rules_by_id = dict((r["rule_id"], r) for r in rules)
    distinct, seen = [], set()
    for w in worlds:
        for p in w["proofs"]:
            key = (json.dumps(p["answer"], default=str),
                   tuple(sorted(p["cited_rules"])))
            if key in seen:
                continue
            seen.add(key)
            distinct.append(dict(p, world_id=w["world_id"],
                                 round=w.get("round")))
    result["returned_proofs"] = [
        {k: v for k, v in p.items() if k != "proof"} for p in distinct]
    result["answers_with_no_cited_hypothesis"] = [
        p["answer"] for p in distinct if p["cites_no_dynamic_hypothesis"]]
    if result["answers_with_no_cited_hypothesis"] and budget():
        # An answer that cites no bridge did not come from an abstraction.  The
        # one other thing this run changed is the proof-return threshold, so ask
        # the base theory alone under that threshold and record what comes back.
        stored = {"stage1": view["stage1"], "stage2": view["stage2"],
                  "final_clauses": view["final_clauses"],
                  "input_text": view["input_text"]}
        got = gk(list(view["final_clauses"]), stored,
                 "%s/threshold only" % case_id, dynamic=True)
        base = proofs_of(got.get("raw") or "{}", {})
        result["threshold_only_baseline"] = {
            "why": "a proof cited no dynamic hypothesis; this is the base "
                   "theory alone at the dynamic proof-return threshold",
            "answers": [p["answer"] for p in base],
            "formatter_answer": got.get("answer"),
            "the_threshold_alone_explains_it": bool(base)}
    dynamic = [p for p in distinct if not p["cites_no_dynamic_hypothesis"]]
    if not dynamic:
        trace.append({"stage": "stopped",
                      "why": "rules compiled and reached gk, and no proof "
                             "citing one came back"})
        result["stopped_at"] = stopped or "no_proof"
        return result

    trace.append({"stage": "minimise"})
    minimal = []
    for p in dynamic:
        m = minimise(view, gk, configuration, case_id, rules_by_id, p,
                     budget) if do_minimise else {
            "minimised": False, "why": "minimisation disabled for this arm",
            "cited_rules": p["cited_rules"]}
        m.update({"answer": p["answer"],
                  "gk_native_confidence": p["gk_native_confidence"],
                  "world_id": p["world_id"], "round": p.get("round"),
                  "cited_rules": p["cited_rules"]})
        minimal.append(m)
    result["minimisation"] = order_proofs(minimal)
    result["distinct_minimal_sets"] = sorted(set(
        tuple(sorted(m.get("minimal_rules") or m["cited_rules"]))
        for m in minimal))

    used_ids = []
    for m in result["minimisation"]:
        for r in (m.get("minimal_rules") or m["cited_rules"]):
            if r not in used_ids:
                used_ids.append(r)
    used = [rules_by_id[r] for r in used_ids if r in rules_by_id]
    if do_grade:
        trace.append({"stage": "grade"})
        result["grading"] = grade_rules(view, used, respond, case_id)
    else:
        result["grading"] = {"asked": False,
                             "why": "grading is done jointly for this study",
                             "grades": {}}
    grades = result["grading"].get("grades") or {}
    for m in result["minimisation"]:
        ids = m.get("minimal_rules") or m["cited_rules"]
        m["worst_grade"] = worst_grade(grades, ids)
        m["grades"] = dict((r, grades.get(r, {}).get("grade", UNASSESSED))
                           for r in ids)

    if do_exclusions:
        result["exclusions"] = maybe_exclusions(
            view, gk, configuration, case_id, rules, rules_by_id,
            result["minimisation"], budget, q_atoms, pool_cap)
    result["stopped_at"] = stopped
    return result


def maybe_exclusions(view, gk, configuration, case_id, rules, rules_by_id,
                     minimal, budget, q_atoms, pool_cap):
    """WP7's bounded second look, and only where the plan allows one.

    One dynamic proof, and its grading contains UNLIKELY or FALSE: exclude one
    such rule at a time, up to three worlds.  No subset enumeration, and a
    healthy first proof is never re-searched.
    """
    if len(minimal) != 1:
        return {"ran": False,
                "why": "more than one distinct dynamic proof was returned"
                       if minimal else "no dynamic proof"}
    m = minimal[0]
    ids = m.get("minimal_rules") or m["cited_rules"]
    bad = [r for r in ids if (m.get("grades") or {}).get(r) in BAD_GRADES]
    if not bad:
        return {"ran": False,
                "why": "the only proof's rules are not graded UNLIKELY or "
                       "FALSE", "worst_grade": m.get("worst_grade")}
    out = []
    for rid in bad[:MAX_EXCLUSION_WORLDS]:
        if not budget():
            out.append({"excluded": rid, "skipped": "gk budget reached"})
            break
        keep = [r for r in rules if r["rule_id"] != rid]
        keep, _dropped = pool_for_round(keep, q_atoms, cap=pool_cap)
        if not keep:
            out.append({"excluded": rid, "skipped": "nothing left to try"})
            continue
        got, _w = run_world(view, keep, gk, configuration,
                            "excl_%s_no_%s" % (case_id, rid),
                            "%s/excluding %s" % (case_id, rid))
        fresh = [p for p in got["proofs"]
                 if not p["cites_no_dynamic_hypothesis"]]
        out.append({"excluded": rid,
                    "excluded_printed": rules_by_id[rid]["printed"],
                    "answers": [p["answer"] for p in got["proofs"]],
                    "dynamic_proofs": [
                        {"answer": p["answer"],
                         "cited_rules": p["cited_rules"],
                         "cited_formulas": p["cited_formulas"],
                         "gk_native_confidence": p["gk_native_confidence"]}
                        for p in fresh],
                    "found_a_different_proof": bool(fresh)})
    return {"ran": True, "reason": "the single proof used a rule graded "
                                   "UNLIKELY or FALSE",
            "worlds": out, "cap": MAX_EXCLUSION_WORLDS}
