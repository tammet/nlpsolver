"""The dynamic-abstraction runtime, as an explicit state machine.

One stored case goes in; a conservative result and zero or more dynamic worlds
come out, with a trace of every state it passed through and every state it
stopped at.  A case never disappears silently.

Transport-free on purpose.  The two things that touch the outside world — an
LLM and the prover — arrive as callables:

    run_case(view, respond, gk, bounds)

`respond(role, prompt, meta) -> (text, call_log)` and
`gk(clauses, tag) -> {answer, confidence, raw, argv}`.  `mock` passes
deterministic stand-ins, `run` passes the real ones, and every transition,
refusal and cap is therefore testable with no calls at all.

**Gold isolation is structural.**  `runtime_view` is the only way a fixture
enters, it returns an allowlisted object, and it raises if a reviewed key
survives.  Nothing downstream can read a reviewed action, a gold package or an
expected answer, because nothing downstream is given one.
"""

import copy
import hashlib
import json

import alignment_candidates as AC
import alignment_context as CX
import alignment_occurrences as AO
import alignment_protocol as P
import alignment_rule as AR
import alignment_selector as S
import bridge_world as BW
import dynamic_score as DS
import formula_print as FP

# ---------------------------------------------------------------- states

STATES = (
    "preflight",
    "baseline_reproduced", "baseline_refused",
    "baseline_answered", "baseline_unresolved",
    "occurrences_built",
    "candidates_enumerated",
    "selector_completed", "selector_empty", "selector_failed",
    "semantic_judgement_completed", "no_bridge_admitted", "semantic_failed",
    "rule_compiled", "rule_refused",
    "world_run", "world_failed",
    "bridge_cited", "bridge_unused", "answer_unchanged", "dynamic_answer",
)

TERMINAL_REFUSALS = ("baseline_refused", "selector_failed", "semantic_failed")

# The front door: a conservative answer the experiment treats as resolved.
# Anything else enters dynamic abstraction.
UNRESOLVED_ANSWERS = ("Unknown.", None, "")

SELECTOR_ROLE, SEMANTIC_ROLE, RULE_ROLE = "selector", "semantic", "rule"

MAX_PAIRS_PER_CASE = 2
MAX_SELECTIONS = S.MAX_SELECTIONS
CANDIDATE_DISPLAY_CAP = S.CANDIDATE_CAP
MAX_SELECTOR_CHUNKS = 2
WORLD_WEIGHT = 0.1

# Keys that carry a reviewed decision.  None of them may reach the runtime.
GOLD_KEYS = ("gold_replacement_packages", "critic_verdict", "labels",
             "expected_answer", "accepted_llmpipe_answers", "reviewed_action",
             "mechanism", "allowed_changed_unit_ids", "acceptable_actions",
             "label_provenance", "correctness", "expected")


class PipelineError(Exception):
    """The runtime cannot proceed.  Never worked around."""


class GoldLeak(PipelineError):
    """Reviewed material reached a place that must not see it."""


# ---------------------------------------------------------------- gold gate

def assert_no_gold(obj, where="runtime"):
    blob = json.dumps(obj, sort_keys=True, default=str)
    hit = [k for k in GOLD_KEYS if ('"%s"' % k) in blob]
    if hit:
        raise GoldLeak("%s carries reviewed key(s) %s" % (where, sorted(hit)))
    return True


def runtime_view(fixture, stored_result):
    """The only door a fixture comes through.  Allowlisted, and checked."""
    view = {
        "case_id": fixture["case_id"],
        "dataset": fixture.get("dataset"),
        "input_text": copy.deepcopy(fixture["input_text"]),
        "stage1": copy.deepcopy(fixture["stage1"]),
        "stage2": copy.deepcopy(fixture["stage2"]),
        "configuration": fixture["configuration"],
        "final_clauses": copy.deepcopy(fixture["final_clauses"]),
        "source_sha256": fixture.get("source_sha256"),
        "stored_answer": stored_result.get("answer"),
        "stored_gk_command": stored_result.get("gk_command"),
    }
    assert_no_gold(view, "runtime_view(%s)" % fixture["case_id"])
    return view


def case_hash(view):
    h = hashlib.sha256()
    for part in (view["case_id"], json.dumps(view["stage2"], sort_keys=True),
                 json.dumps(view["final_clauses"], sort_keys=True)):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


# ---------------------------------------------------------------- chunking

def candidate_chunks(gen, cap=CANDIDATE_DISPLAY_CAP,
                     max_chunks=MAX_SELECTOR_CHUNKS):
    """-> (chunks, unseen).  Global ids are the enumeration index, always.

    Enumeration order carries no ranking, so splitting by it introduces no
    preference.  What it does introduce is a ceiling: with two chunks of `cap`,
    anything past 2*cap is never shown, and that is reported rather than
    dropped in silence.
    """
    rows = gen["candidates"]
    ided = [("K%d" % (i + 1), r) for i, r in enumerate(rows)]
    chunks = [ided[i:i + cap] for i in range(0, len(ided), cap)][:max_chunks]
    shown = sum(len(c) for c in chunks)
    return chunks, len(ided) - shown


# ---------------------------------------------------------------- prompts

def _instr(name):
    import os
    with open(os.path.join(P.PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_hash(name):
    return hashlib.sha256(_instr(name).encode()).hexdigest()


def _sentences_block(view):
    lines = []
    n = 0
    for sent in view["stage1"] or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            n += 1
            lines.append("  %d. [%s] %s" % (n, u.get("unit_id"), u.get("text")))
    return "\n".join(lines)


def build_selector_prompt(view, gen, chunk, chunk_index, total_chunks,
                          already_selected=(), instructions="selector_candidates_v2"):
    by_id = gen["table"]["by_id"]
    lines = []
    for gid, r in chunk:
        p, c = by_id[r["producer"]], by_id[r["consumer"]]
        lines.append("%s: %s\n      -> %s\n      %s"
                     % (gid, S._occ_line(p), S._occ_line(c),
                        S._pair_note(p, c, r)))
    parts = ["ENGLISH PROBLEM:\n%s" % view["input_text"],
             "SENTENCES:\n%s" % _sentences_block(view)]
    if total_chunks > 1:
        note = ("This is list %d of %d for this problem.  The names are stable "
                "across the lists: %s here is the same pair as %s anywhere "
                "else." % (chunk_index + 1, total_chunks, chunk[0][0],
                           chunk[0][0]))
        if already_selected:
            note += ("  From the earlier list you chose %s.  That is recorded "
                     "so you do not repeat a name, and for no other reason: do "
                     "not choose differently here merely to differ."
                     % ", ".join(already_selected))
        parts.append("ABOUT THIS LIST:\n%s" % note)
    parts.append("CANDIDATE PAIRS:\n%s" % "\n\n".join(lines))
    prompt = _instr(instructions) + "\n\n" + "\n\n".join(parts)
    P.assert_no_leak(prompt)
    assert_no_gold(prompt, "selector prompt")
    return prompt


def build_semantic_prompt(view, gen, pairs, instructions="semantic_judge_v1"):
    """`pairs` is [(global_id, row)] — only what the selector chose."""
    by_id = gen["table"]["by_id"]
    lines = []
    for gid, r in pairs:
        p, c = by_id[r["producer"]], by_id[r["consumer"]]
        lines.append("PAIR %s\n  already established: %s\n  still needed:       %s\n  %s"
                     % (gid, S._occ_line(p), S._occ_line(c),
                        S._pair_note(p, c, r)))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % view["input_text"],
        "SENTENCES:\n%s" % _sentences_block(view),
        "THE PAIRS AN EARLIER SELECTOR MARKED AS WORTH EXAMINING:\n%s"
        % "\n\n".join(lines)])
    prompt = _instr(instructions) + "\n\n" + body
    P.assert_no_leak(prompt)
    assert_no_gold(prompt, "semantic prompt")
    return prompt


def build_rule_prompt(view, gen, gid, row, judgement, menu,
                      instructions="rule_builder_v3"):
    by_id = gen["table"]["by_id"]
    p, c = by_id[row["producer"]], by_id[row["consumer"]]
    cond_lines = []
    for alias, m in menu:
        cond_lines.append("  %s: %-46s [%s]%s"
                          % (alias, FP.formula(m["atom"]), m["why_offered"],
                             "  <- %r" % m["source_quote"]
                             if m.get("source_quote") else ""))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % view["input_text"],
        "SENTENCES:\n%s" % _sentences_block(view),
        "THE PAIR, named %s:\n  from  %s\n  infer %s\n  %s"
        % (gid, S._occ_line(p), S._occ_line(c), S._pair_note(p, c, row)),
        "WHAT THE SEMANTIC JUDGE SAID:\n  bridge: %s\n  scope: %s\n"
        "  conditions in plain words: %s\n  counterexample it considered: %s\n"
        "  why: %s"
        % (judgement.get("bridge"), judgement.get("scope"),
           judgement.get("conditions") or "none",
           judgement.get("counterexample") or "none",
           judgement.get("why") or ""),
        "CONDITIONS AVAILABLE BESIDE THE ESTABLISHED ATOM:\n%s"
        % ("\n".join(cond_lines) or "  (none)")])
    prompt = _instr(instructions) + "\n\n" + body
    P.assert_no_leak(prompt)
    assert_no_gold(prompt, "rule prompt")
    return prompt


# ---------------------------------------------------------------- parsers

BRIDGE_VALUES = ("yes", "conditional", "no", "uncertain")
SCOPE_VALUES = ("local", "context", "general", "unclear")
REPAIR_VALUES = ("yes", "no", "uncertain")


def _first_word(s):
    t = (s or "").strip().lower()
    return t.split(" ")[0].strip(".,;:!?()[]\"'*_") if t else ""


def parse_semantic_response(text, known_ids):
    """One block per pair.  PAIR, BRIDGE and SCOPE are read strictly.

    Anything unrecognised becomes `uncertain`; nothing is guessed into an
    admission, and an id that was not offered is reported, never snapped to a
    neighbour.
    """
    blocks, current = [], None
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_ ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k = k.strip().strip("*#_-• \t").lower()
        v = v.strip().strip("*_ ").strip()
        if k == "pair":
            current = {"pair": v.split()[0].strip(".,") if v else "",
                       "bridge": "uncertain", "scope": "unclear",
                       "repair_also_possible": "uncertain",
                       "conditions": "", "counterexample": "", "why": ""}
            blocks.append(current)
        elif current is None:
            continue
        elif k == "bridge":
            w = _first_word(v)
            current["bridge"] = w if w in BRIDGE_VALUES else "uncertain"
        elif k == "scope":
            w = _first_word(v)
            current["scope"] = w if w in SCOPE_VALUES else "unclear"
        elif k.startswith("repair"):
            w = _first_word(v)
            current["repair_also_possible"] = w if w in REPAIR_VALUES \
                else "uncertain"
        elif k == "conditions":
            current["conditions"] = v
        elif k == "counterexample":
            current["counterexample"] = v
        elif k == "why":
            current["why"] = v
    out, unknown = {}, []
    for b in blocks:
        pid = b["pair"].upper()
        if pid not in known_ids:
            unknown.append(b["pair"])
            continue
        if pid not in out:
            out[pid] = b
    return {"judgements": out, "unknown_pair_ids": unknown,
            "parsed": bool(out), "blocks_seen": len(blocks)}


def admissible(judgement):
    return judgement.get("bridge") in ("yes", "conditional")


def parse_rule_response(text, base_aliases, condition_aliases):
    """BASE and ADDITIONAL CONDITIONS only.  Strength is not asked for."""
    obj, err, prose = AR.parse_base_rule_response(text)
    if obj is None:
        return None, err, prose
    obj = dict(obj)
    obj["strength"] = AR.DEFAULT_STRENGTH      # every runtime bridge is a default
    try:
        resolved = AR.resolve_aliases(obj, base_aliases, condition_aliases)
    except AR.RuleError as e:
        return None, str(e), prose
    return resolved, None, prose


# ---------------------------------------------------------------- machine

class Trace(object):
    """Every state a case entered, with why and when."""

    def __init__(self):
        self.states = []

    def enter(self, state, **detail):
        if state not in STATES:
            raise PipelineError("unknown state %r" % state)
        self.states.append(dict(detail, state=state))
        return state

    def names(self):
        return [s["state"] for s in self.states]

    def stopped_at(self):
        return self.states[-1]["state"] if self.states else None


def run_case(view, respond, gk, bounds=None, weight=WORLD_WEIGHT):
    """The whole runtime for one case.  No gold, no reviewed material."""
    bounds = bounds or {}
    tr = Trace()
    rec = {"case_id": view["case_id"], "case_hash": case_hash(view),
           "configuration": view["configuration"],
           "conservative_result": None, "dynamic_worlds": [],
           "unresolved_diagnostics": [], "trace": None, "usage": {},
           "prompt_hashes": {}}
    tr.enter("preflight", stored_answer=view["stored_answer"])

    # ---- baseline
    base = gk(view["final_clauses"], "baseline")
    ok_answer = base.get("answer") == view["stored_answer"]
    ok_cmd = base.get("command_matches_stored")
    if not (ok_answer and ok_cmd is not False):
        tr.enter("baseline_refused",
                 why="answer %r vs stored %r; command matches: %s"
                     % (base.get("answer"), view["stored_answer"], ok_cmd))
        rec["conservative_result"] = {"answer": base.get("answer"),
                                      "reproduced": False}
        rec["trace"] = tr.states
        return rec
    tr.enter("baseline_reproduced")
    rec["conservative_result"] = {
        "answer": base.get("answer"), "gk_confidence": base.get("confidence"),
        "reproduced": True, "gk_command": base.get("argv"),
        "seconds": base.get("seconds")}

    if base.get("answer") not in UNRESOLVED_ANSWERS:
        tr.enter("baseline_answered", answer=base.get("answer"))
        rec["front_door_stopped"] = True
        rec["trace"] = tr.states
        return rec
    tr.enter("baseline_unresolved")
    rec["front_door_stopped"] = False

    # ---- occurrences and candidates
    gen = AC.generate(view["stage1"], view["stage2"], view["configuration"])
    tr.enter("occurrences_built",
             stage2_occurrences=len(gen["table"]["stage2"]))
    chunks, unseen = candidate_chunks(gen)
    rec["enumeration"] = {
        "producers": gen["producers"], "consumers": gen["consumers"],
        "enumerated": gen["enumerated"], "survived": gen["survived"],
        "rejected_by_reason": gen["rejected_by_reason"],
        "chunks": len(chunks),
        "shown": sum(len(c) for c in chunks),
        "never_shown": unseen,
        "display_cap": CANDIDATE_DISPLAY_CAP,
        "chunk_ceiling": MAX_SELECTOR_CHUNKS}
    tr.enter("candidates_enumerated", survived=gen["survived"],
             never_shown=unseen)
    if not gen["candidates"]:
        tr.enter("selector_empty", why="nothing survived mechanical rejection")
        rec["unresolved_diagnostics"].append("no candidate survived")
        rec["trace"] = tr.states
        return rec

    # ---- selector, one call per chunk
    selected, sel_records = [], []
    for i, chunk in enumerate(chunks):
        prompt = build_selector_prompt(view, gen, chunk, i, len(chunks),
                                       already_selected=list(selected))
        text, log, note = respond(SELECTOR_ROLE, prompt,
                                  {"chunk": i, "case": view["case_id"]})
        sel = S.parse_selection(text or "", "candidates")
        ids = [s for s in sel["selected"]]
        valid = set(g for g, _ in chunk)
        kept = [s for s in ids if s in valid]
        sel_records.append({"chunk": i, "raw": text, "parsed": sel["parsed"],
                            "selected": ids, "kept": kept,
                            "out_of_this_chunk": [s for s in ids
                                                  if s not in valid],
                            "call_log": log, "note": note})
        for s in kept:
            if s not in selected:
                selected.append(s)
    rec["selector"] = {"calls": sel_records, "merged": selected[:MAX_SELECTIONS]}
    selected = selected[:MAX_SELECTIONS]
    if not selected:
        tr.enter("selector_empty", why="no usable id on any SELECTED line")
        rec["unresolved_diagnostics"].append("the selector chose nothing")
        rec["trace"] = tr.states
        return rec
    tr.enter("selector_completed", chosen=selected)

    by_gid = {g: r for c in chunks for g, r in c}
    pairs = [(g, by_gid[g]) for g in selected]

    # ---- semantic judgement
    sprompt = build_semantic_prompt(view, gen, pairs)
    stext, slog, snote = respond(SEMANTIC_ROLE, sprompt,
                                 {"case": view["case_id"]})
    parsed = parse_semantic_response(stext or "", set(g for g, _ in pairs))
    rec["semantic"] = {"raw": stext, "call_log": slog, "note": snote,
                       "judgements": parsed["judgements"],
                       "unknown_pair_ids": parsed["unknown_pair_ids"],
                       "blocks_seen": parsed["blocks_seen"]}
    if not parsed["parsed"]:
        tr.enter("semantic_failed", why="no readable PAIR block")
        rec["unresolved_diagnostics"].append("semantic judgement unreadable")
        rec["trace"] = tr.states
        return rec
    admitted = [(g, r) for g, r in pairs
                if admissible(parsed["judgements"].get(g, {}))]
    rec["semantic"]["admitted"] = [g for g, _ in admitted]
    rec["semantic"]["repair_also_possible"] = {
        g: parsed["judgements"].get(g, {}).get("repair_also_possible")
        for g, _ in pairs}
    tr.enter("semantic_judgement_completed", admitted=[g for g, _ in admitted])
    if not admitted:
        tr.enter("no_bridge_admitted",
                 why="every examined pair was judged no or uncertain")
        rec["unresolved_diagnostics"].append("no pair admitted a bridge")
        rec["trace"] = tr.states
        return rec
    admitted = admitted[:MAX_PAIRS_PER_CASE]

    # ---- one world per admitted pair, never combined
    for n, (gid, row) in enumerate(admitted, start=1):
        world = _one_bridge(view, gen, gid, row,
                            parsed["judgements"][gid], respond, gk, tr,
                            "A%d" % n, weight)
        rec["dynamic_worlds"].append(world)
    rec["trace"] = tr.states
    return rec


def _one_bridge(view, gen, gid, row, judgement, respond, gk, tr, hyp_id,
                weight):
    table = gen["table"]
    out = {"hypothesis_id": hyp_id, "pair": gid,
           "producer": row["producer"], "consumer": row["consumer"],
           "semantic_judgement": judgement}
    menu_rows = CX.menu(table, view["stage2"], row["producer"], row["consumer"])
    menu = [("G%d" % (i + 1), m) for i, m in enumerate(menu_rows)]
    out["conditions_offered"] = [{"alias": a, "occurrence": m["occurrence_id"],
                                  "atom": FP.formula(m["atom"]),
                                  "why_offered": m["why_offered"]}
                                 for a, m in menu]
    prompt = build_rule_prompt(view, gen, gid, row, judgement, menu)
    text, log, note = respond(RULE_ROLE, prompt,
                              {"case": view["case_id"], "pair": gid})
    base_aliases = {gid: {"producer": row["producer"],
                          "consumer": row["consumer"]}}
    cond_aliases = {a: m["occurrence_id"] for a, m in menu}
    resolved, err, prose = parse_rule_response(text or "", base_aliases,
                                               cond_aliases)
    out["rule_response"] = {"raw": text, "prose": prose, "error": err,
                            "call_log": log, "note": note}
    if resolved is None:
        tr.enter("rule_refused", pair=gid, why=err)
        out["state"] = "rule_refused"
        return out

    try:
        pkg, prec = BW.bridge_package(resolved["producer"], resolved["consumer"],
                                      resolved["condition_ids"], table)
        clauses, brec = BW.compile_bridge(
            view["case_id"], hyp_id, pkg, view["stage1"], view["stage2"],
            view["configuration"], bridge_evidence=BW.RUNTIME_EVIDENCE,
            base_clauses=view["final_clauses"], hypothesis_id=hyp_id)
    except (AR.RuleError, BW.BridgeError) as e:
        tr.enter("rule_refused", pair=gid, why=str(e))
        out["state"] = "rule_refused"
        out["compiler_error"] = str(e)
        return out
    out["rule"] = {"base": resolved["base_alias"],
                   "conditions": resolved["condition_aliases"],
                   "condition_occurrences": resolved["condition_ids"],
                   "stage2": pkg, "printed": FP.formula(pkg),
                   "clauses": clauses,
                   "has_block": brec["has_block"],
                   "guards": BW.guards_present(
                       clauses, [str(x) for x in _labels(pkg)]),
                   "clause_provenance": brec["clause_provenance"]}
    tr.enter("rule_compiled", pair=gid, rule=FP.formula(pkg))

    theory = list(view["final_clauses"]) + clauses
    res = gk(theory, "world_%s" % hyp_id)
    if res.get("error"):
        tr.enter("world_failed", pair=gid, why=res["error"])
        out["state"] = "world_failed"
        out["gk"] = res
        return out
    tr.enter("world_run", pair=gid)
    prov = brec["clause_provenance"]
    scored = DS.from_raw(res.get("raw") or "", prov, {hyp_id: weight}, weight)
    changed = res.get("answer") != view["stored_answer"]
    cited = bool(scored["bridge_hypotheses_used"])
    out["gk"] = {"answer": res.get("answer"), "gk_confidence": res.get("confidence"),
                 "argv": res.get("argv"), "seconds": res.get("seconds"),
                 "answer_changed_from_baseline": changed}
    out["proof"] = {"bridge_cited": cited,
                    "clauses_cited": scored["bridge_clauses_used"],
                    "steps": DS.cited_hypotheses(_proofs(res.get("raw")),
                                                 prov)[1]}
    out["dynamic"] = {k: v for k, v in scored.items() if k != "raw"}
    out["rendered"] = DS.render(scored)

    if cited:
        tr.enter("bridge_cited", pair=gid)
        if changed:
            tr.enter("dynamic_answer", pair=gid, answer=res.get("answer"))
            out["state"] = "dynamic_answer"
        else:
            tr.enter("answer_unchanged", pair=gid)
            out["state"] = "bridge_used_but_unresolved"
    else:
        tr.enter("bridge_unused", pair=gid)
        if changed:
            ctl = gk(list(view["final_clauses"]) + _inert(len(clauses)),
                     "inert_%s" % hyp_id)
            out["inert_control"] = {k: v for k, v in ctl.items() if k != "raw"}
            out["state"] = "search_order_effect"
            tr.enter("answer_unchanged", pair=gid,
                     why="answer changed with no bridge citation; "
                         "search-order effect, not a dynamic answer")
        else:
            out["state"] = "bridge_unused"
    return out


def _labels(pkg):
    import alignment_compare as CMP
    try:
        p = CMP.parse_rule_package(pkg)
    except CMP.ShapeError:
        return []
    out = []
    for a in p["antecedents"] + [p["consequent"]]:
        lbl, _ = CMP.label_and_participants(a)
        out.append(lbl)
    return out


def _proofs(raw):
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except (ValueError, TypeError):
        return None
    out = []
    for a in d.get("answers") or []:
        for k in ("positive proof", "negative proof", "proof"):
            if a.get(k):
                out.append(a[k])
    return out or None


def _inert(n):
    return [{"@name": "dyn_inert_%d" % i,
             "@logic": [["-$dyn_inert", "$dyn_a_%d" % i],
                        ["$dyn_inert", "$dyn_b_%d" % i]]}
            for i in range(1, n + 1)]
