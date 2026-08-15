"""The dynamic-abstraction runtime, end to end, from a stored parse.

    stored Stage-2 parse
      -> conservative front door (gk, stored options)
      -> if it answers: STOP, and record that no dynamic work was done
      -> semantic frontier            (computed here, not read from a file)
      -> construction v3              (the model names; code builds)
      -> six-axis admission           (the model judges; code gates)
      -> direct attachment assessment (only where code invented one)
      -> world transport              (archived and rejected refused)
      -> one gk world per eligible canonical formula, full-confidence clause
      -> post-gk weighting, structured result, dynamic rendering

Two things this module is careful about, because both were got wrong before:

**Uncertainty is not written into the clause.**  A bridge reaches gk as a
full-confidence defeasible rule, gk searches with its own confidence, and the
abstraction's weight is applied to the proof afterwards.  Writing a low
confidence onto the clause prunes the search and compounds on reuse, which is
not what anyone meant by "this rule is a guess".  The only gk option that
changes for a dynamic world is the proof-return threshold, and both values are
recorded on every call.

**Nothing reviewed can reach it.**  `runtime_view` is the only door a stored
case comes through, it copies an allowlist, and it raises if a reviewed or
accepted key survives.  The stages below never see anything else.

Transport-free: the LLM and the prover arrive as callables, so every gate,
refusal and cap is testable with no calls at all.
"""

import contextlib
import copy
import hashlib
import json
import os
import re

import admission_policy_v2 as AP
import admission_record as AR
import bridge_world as BW
import construction_forms as CF
import construction_operators as CO
import construction_provenance as CP
import construction_slots as CS
import dynamic_score as DS
import formula_hypothesis as FH
import guard_facts as GF
import operator_input as OI
import operator_input_v2 as OI2
import semantic_frontier as SF
import world_transport as WT

VERSION = "dynamic_runtime/1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")
AXIOMS = os.path.join(ROOT, "axioms_std.js")

GROUP_SELECTOR_PROMPT = "group_selector_v2"
CONSTRUCTION_PROMPT = "operator_proposal_v3"
FORMULA_SELECTOR_PROMPT = "formula_selector_v1"
ADMISSION_PROMPT = "admission_probe_v3"
ATTACHMENT_PROMPT = "attachment_probe_v1"

# The external weight every admitted dynamic hypothesis carries.  Provisional
# and fixed: it is not a calibration, and no measurement supports a particular
# number.  It is applied AFTER gk, to the proof, never to the clause.
WORLD_WEIGHT = 0.1

# The dynamic proof-return threshold.  The stored options keep their value for
# the conservative front door; a dynamic world lowers this one option so a
# proof whose native confidence is small is returned rather than discarded, and
# both values are recorded on every call.
DYNAMIC_CONFIDENCE = "0.0001"
CONFIDENCE_FLAG = "-confidence"

# A conservative answer the runtime treats as resolved.  Anything else opens
# the dynamic path.
UNRESOLVED_ANSWERS = ("Unknown.", None, "")

GROUPS_SHOWN = 3
MAX_HYPOTHESES = 6

# Two runtimes, one entry point.  `isolated` is AL-76/77's, unchanged: one
# admitted formula per world, admission before gk.  `pooled_discovery` refuses
# only mechanically broken formulas before gk, hands gk several bridges at
# once, and assesses what a proof cited afterwards.
ISOLATED = "isolated"
POOLED = "pooled_discovery"
DYNAMIC_MODES = (ISOLATED, POOLED)

STAGES = ("front_door", "frontier", "group_selection", "construction",
          "hypotheses", "formula_selection", "admission", "attachment",
          "transport", "worlds", "scored")

# What the two selectors see and may keep.  Both are PRIORITIZATION: nothing a
# selector leaves out is deleted, every omission is recorded by name, and the
# stage that decides whether a rule may be believed is admission, downstream of
# both.
GROUPS_SHOWN_ALL_UPTO = 60      # at or below this, every group is shown
GROUPS_FIRST_BLOCK = 50         # above it: this many in the frozen order
GROUPS_DIVERSE_BLOCK = 10       # plus this many with unseen signatures
MAX_SELECTED_GROUPS = 8
FORMULA_DISPLAY_CAP = 120
MAX_SELECTED_FORMULAS = 12

# Keys that carry a reviewed decision or an accepted answer.  None may reach
# the runtime.
#
# Deliberately narrow, and each name is a reviewed one.  `labels` and `role`
# were in the first version and had to come out: the construction stage's own
# word table is called `labels`, and every occurrence carries the `role` of the
# sentence it came from.  A gate that fires on an innocent name teaches you to
# widen the allowlist instead of narrowing the leak.
GOLD_KEYS = ("expected_answer", "expected", "correctness",
             "accepted_llmpipe_answers", "accepted_development_answers",
             "gold_replacement_packages", "reviewed_action", "reviewed_rule",
             "reviewed_head", "critic_verdict", "label_provenance",
             "acceptable_actions", "ceiling_outcome", "representability")


class RuntimeError_(Exception):
    """The runtime cannot proceed.  Never worked around."""


class GoldLeak(RuntimeError_):
    """Reviewed or accepted material reached a place that must not see it."""


# ---------------------------------------------------------------- gold gate

def assert_no_gold(obj, where="runtime"):
    blob = json.dumps(obj, sort_keys=True, default=str)
    hit = [k for k in GOLD_KEYS if ('"%s"' % k) in blob]
    if hit:
        raise GoldLeak("%s carries reviewed key(s) %s" % (where, sorted(hit)))
    return True


def runtime_view(case_id, stored, configuration, split="diagnostic"):
    """The only door a stored case comes through.  Allowlisted, and checked."""
    view = {
        "case_id": case_id,
        "split": split,
        "input_text": copy.deepcopy(stored.get("input_text")),
        "stage1": copy.deepcopy(stored.get("stage1")),
        "stage2": copy.deepcopy(stored.get("stage2")),
        "final_clauses": copy.deepcopy(stored.get("final_clauses")
                                       or stored.get("clauses")),
        "configuration": configuration,
        "stored_gk_command": stored.get("gk_command"),
    }
    if not view["final_clauses"]:
        raise RuntimeError_("%s has no stored clause theory" % case_id)
    assert_no_gold(view, "runtime_view(%s)" % case_id)
    return view


def view_hash(view):
    h = hashlib.sha256()
    for part in (view["case_id"], json.dumps(view["stage2"], sort_keys=True),
                 json.dumps(view["final_clauses"], sort_keys=True)):
        h.update(part.encode())
        h.update(b"\x00")
    return h.hexdigest()


# ------------------------------------------------------------- gk options

def stored_prover_params():
    import globals as g
    return list(g.prover_params)


def threshold_of(params):
    if CONFIDENCE_FLAG in params:
        return params[params.index(CONFIDENCE_FLAG) + 1]
    return None


@contextlib.contextmanager
def dynamic_threshold(value=DYNAMIC_CONFIDENCE):
    """Lower ONE gk option for a dynamic world, and put it back.

    Everything else the case stores stays as it is.  The two thresholds are
    returned so the caller records both on the call rather than describing the
    change in prose.
    """
    import globals as g
    before = list(g.prover_params)
    new = list(before)
    if CONFIDENCE_FLAG in new:
        new[new.index(CONFIDENCE_FLAG) + 1] = str(value)
    else:
        new += [CONFIDENCE_FLAG, str(value)]
    g.prover_params = new
    try:
        yield {"stored_gk_threshold": threshold_of(before),
               "dynamic_gk_threshold": threshold_of(new),
               "stored_params": before, "dynamic_params": new,
               "options_changed": [CONFIDENCE_FLAG]}
    finally:
        g.prover_params = before


# ---------------------------------------------------------------- prompts

def prompt_text(name):
    with open(os.path.join(PROMPT_DIR, "%s.txt" % name)) as f:
        return f.read()


def prompt_sha(name):
    return hashlib.sha256(prompt_text(name).encode()).hexdigest()


def component_hashes():
    """Everything frozen for a run, hashed before any live call."""
    out = {}
    for mod in ("semantic_frontier", "construction_operators",
                "construction_slots", "construction_forms",
                "construction_provenance", "formula_hypothesis",
                "admission_policy", "admission_policy_v2", "admission_record",
                "guard_facts", "world_transport", "bridge_world",
                "dynamic_score", "operator_input", "operator_input_v2",
                "dynamic_runtime"):
        p = os.path.join(ROOT, "solver", "%s.py" % mod)
        out["solver/%s.py" % mod] = hashlib.sha256(
            open(p, "rb").read()).hexdigest()
    for name in (CONSTRUCTION_PROMPT, ADMISSION_PROMPT, ATTACHMENT_PROMPT):
        out["prompts/dynamic_alignment/%s.txt" % name] = prompt_sha(name)
    out["axioms_std.js"] = hashlib.sha256(open(AXIOMS, "rb").read()).hexdigest()
    return out


# ------------------------------------------------------------- stage 1: gk

def front_door(view, gk):
    """The conservative answer, from the stored theory and stored options."""
    got = gk(view["final_clauses"], view, "front_door:%s" % view["case_id"],
             dynamic=False)
    answer = got.get("answer")
    return {"answer": answer,
            "resolved": answer not in UNRESOLVED_ANSWERS,
            "seconds": got.get("seconds"),
            "gk_thresholds": got.get("thresholds"),
            "error": got.get("error")}


# ------------------------------------------------------- stage 2: frontier

def stage1_units(view):
    roles, texts = {}, {}
    for sent in view["stage1"] or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            uid = u.get("unit_id")
            if not uid:
                continue
            texts[uid] = u.get("text")
            t = (u.get("type") or "").lower()
            roles[uid] = ("question" if "question" in t else
                          "rule" if "rule" in t or "implic" in t else
                          "fact" if t else "unknown")
    return roles, texts


def frontier(view, axioms=AXIOMS, groups_shown=GROUPS_SHOWN):
    """The semantic frontier, computed from the stored theory.

    The demand analysis and the grouping are the frozen offline ones.
    `selected` is the DETERMINISTIC fallback — the top of the frozen ranking —
    and is used only when the selector cannot be reached or cannot be read.
    The selector itself is a separate stage.
    """
    import demand_regression as DR
    analysis, _theory = DR.analyse(
        {"stage1": view["stage1"], "stage2": view["stage2"],
         "final_clauses": view["final_clauses"],
         "input_text": view["input_text"],
         "gk_command": view["stored_gk_command"]}, axioms)
    roles, texts = stage1_units(view)
    vocab = SF.source_vocabulary({"final_clauses": view["final_clauses"]})
    built = SF.build({"case_id": view["case_id"], "analysis": analysis},
                     roles, texts, vocab)
    selected = [g["group_id"] for g in built["groups"][:groups_shown]]
    return {"version": SF.VERSION, "counts": built["counts"],
            "groups": built["groups"],
            "low_priority": built.get("low_priority") or [],
            "selected": selected,
            "fallback_selection": list(selected),
            "selection_policy": "the top %d of the frozen ranking, kept as the "
                                "fallback; an LLM selector chooses from the "
                                "displayed groups" % groups_shown,
            "interfaces": len(analysis.get("interfaces") or [])}


# --------------------------------------------------- stage 2b: group selector

def _signature(g):
    """What makes a group mechanically different from another."""
    return (g.get("sign"), g.get("predicate"), g.get("label"),
            tuple(g.get("participants") or ()))


def group_display(front, all_upto=GROUPS_SHOWN_ALL_UPTO,
                  first=GROUPS_FIRST_BLOCK, diverse=GROUPS_DIVERSE_BLOCK):
    """Which groups the selector sees, and exactly which it does not.

    At or below `all_upto` every group is shown, so nothing can hide.  Above
    it, the first `first` of the FROZEN structural order are shown, then up to
    `diverse` more whose predicate/label/participant signature has not appeared
    yet — so a rare shape late in the order still gets in front of the model —
    and every omitted group is listed by id.
    """
    groups = front["groups"]
    if len(groups) <= all_upto:
        return {"shown": list(groups), "omitted": [], "policy":
                "all %d groups shown (at or below the %d threshold)"
                % (len(groups), all_upto)}
    shown = list(groups[:first])
    seen = set(_signature(g) for g in shown)
    extra = []
    for g in groups[first:]:
        if len(extra) >= diverse:
            break
        s = _signature(g)
        if s in seen:
            continue
        seen.add(s)
        extra.append(g)
    shown += extra
    kept = set(g["group_id"] for g in shown)
    omitted = [{"group_id": g["group_id"], "readable": g.get("readable"),
                "question_target": g.get("question_target"),
                "signature_already_shown": _signature(g) in seen}
               for g in groups if g["group_id"] not in kept]
    return {"shown": shown, "omitted": omitted,
            "diverse_added": [g["group_id"] for g in extra],
            "policy": "%d groups: the first %d of the frozen order, plus %d "
                      "with a signature not yet seen; %d omitted and listed"
                      % (len(groups), first, len(extra), len(omitted))}


def group_selector_prompt(view, front, display, source_atoms):
    import alignment_protocol as P
    L = []
    for a in source_atoms:
        L.append("  %s [%s]" % (a["unit"], a["role"]))
        for at in a["atoms"]:
            L.append("      %s" % at)
    atoms = "\n".join(L) or "  (none recorded)"
    rows = []
    for target, heading in (("positive", "what the prover needs in order to "
                                         "SUPPLY the question's claim"),
                            ("negative", "what the prover needs in order to "
                                         "CONTRADICT it")):
        here = [g for g in display["shown"]
                if g["question_target"] == target]
        if not here:
            continue
        rows.append("  %s:" % heading)
        for g in here:
            src = ("from %s" % ", ".join(g["source_units"])) \
                if g.get("source_units") else "no source sentence"
            rows.append("    %-5s %-54s  %s, %d variant(s)"
                        % (g["group_id"], (g.get("readable") or "")[:54], src,
                           g.get("variants", 0)))
    if display["omitted"]:
        rows.append("  (%d further groups are not shown)"
                    % len(display["omitted"]))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % view["input_text"],
        "WHAT THE TRANSLATION PRODUCED:\n%s" % atoms,
        "SEMANTIC GROUPS THE PROVER NEEDED:\n%s" % ("\n".join(rows) or "  (none)")
    ])
    prompt = prompt_text(GROUP_SELECTOR_PROMPT) + "\n\n" + body
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def parse_selection(text, known_ids, cap, prefix="G"):
    """Only a final `SELECTED:` line is read; prose is never scraped."""
    picked = None
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() != "SELECTED":
            continue
        picked = re.findall(r"\b%s\d+\b" % prefix, v.upper())
    if picked is None:
        return {"readable": False, "selected": [], "unknown": [],
                "over_cap": False}
    seen, good, bad = set(), [], []
    for i in picked:
        if i in known_ids and i not in seen:
            seen.add(i)
            good.append(i)
        elif i not in known_ids:
            bad.append(i)
    return {"readable": True, "selected": good[:cap], "unknown": bad,
            "over_cap": len(good) > cap}


SELECTION_RETRY = ("\n\nYour previous reply had no readable SELECTED line, or "
                   "used ids that were not printed. Reply with the final line "
                   "only, in exactly the form shown.")


def select_groups(view, front, source_atoms, respond, allow_retry=True):
    """The LLM picks which groups construction sees.  Prioritization only."""
    display = group_display(front)
    ids = [g["group_id"] for g in display["shown"]]
    prompt = group_selector_prompt(view, front, display, source_atoms)
    text, note = respond("group_selector", view["case_id"], prompt)
    got = parse_selection(text, set(ids), MAX_SELECTED_GROUPS)
    raw, retried = {"first": text}, False
    if allow_retry and text is not None and not got["readable"]:
        text2, _n = respond("group_selector", view["case_id"],
                            prompt + SELECTION_RETRY, retry=True)
        raw["retry"] = text2
        retried = True
        got2 = parse_selection(text2, set(ids), MAX_SELECTED_GROUPS)
        if got2["readable"]:
            got = got2
    selected = got["selected"] or front["fallback_selection"]
    return {"stage": "group_selection",
            "groups_total": len(front["groups"]),
            "groups_shown": len(display["shown"]),
            "shown_ids": ids,
            "omitted": display["omitted"],
            "diverse_added": display.get("diverse_added") or [],
            "display_policy": display["policy"],
            "selection": got, "selected": selected,
            "used_the_fallback": not got["selected"],
            "fallback": front["fallback_selection"],
            "retried": retried, "raw": raw, "note": note,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def source_atoms(view, cap=40):
    """The problem's own Stage-2 atoms, source-linked, for the selector.

    Taken from the stored source-sentence clauses only: these are what the
    English actually said, as the compiler recorded it.
    """
    import demand_regression as DR
    out = []
    for c in view["final_clauses"] or []:
        if not isinstance(c, dict) or "@question" in c:
            continue
        name = c.get("@name") or ""
        if not SF.UNIT.match(name):
            continue
        if c.get("@sourcetype") == "populate":
            continue
        lits = DR.literals_of(c.get("@logic")) or []
        shown = [DR.show(l) for l in lits
                 if DR.classify_literal(l) == DR.ORDINARY]
        if not shown:
            continue
        out.append({"unit": SF.UNIT.match(name).group(1),
                    "role": "question" if c.get("@sourcetype") == "question"
                    else ("rule" if len(shown) > 1 else "fact"),
                    "atoms": shown})
        if len(out) >= cap:
            break
    return out


def case_of(view, front, selected=None):
    """The construction stage's view of the problem."""
    stored = {"stage1": view["stage1"], "stage2": view["stage2"],
              "final_clauses": view["final_clauses"],
              "input_text": view["input_text"]}
    case = OI.build_case(view["case_id"], stored, view["split"],
                         front["groups"],
                         selected if selected is not None
                         else front["selected"])
    assert_no_gold({k: v for k, v in case.items() if k != "by_oid"},
                   "case_of(%s)" % view["case_id"])
    return case


# --------------------------------------------------- stage 3: construction

def construction_prompt(case):
    import alignment_protocol as P
    prompt = prompt_text(CONSTRUCTION_PROMPT) + "\n\n" + OI2.render(case)
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def compile_proposals(case, view, proposals):
    """Named proposals -> checked, completed, converted alternatives."""
    out = []
    for prop in proposals:
        row = {"proposal": prop, "alternatives": [], "refusals": [],
               "status": "ok"}
        try:
            bare = CF.build(case, prop, complete=False, complete_guards=False)
            row["model_slots_complete"] = bool(bare["alternatives"])
            row["missing_slot_reasons"] = CS.refusal_reasons(bare)[:4]
        except CO.ConstructionError as e:
            row["model_slots_complete"] = False
            row["missing_slot_reasons"] = [str(e)[:160]]
        try:
            got = CF.build(case, prop, max_alternatives=CS.MAX_ALTERNATIVES)
        except CO.ConstructionError as e:
            row["status"] = "refused"
            row["why"] = str(e)[:200]
            out.append(row)
            continue
        row.update({"refusals": got["refusals"][:12],
                    "refusals_reasons": CS.refusal_reasons(got)[:6],
                    "refusals_total": len(got["refusals"]),
                    "capped": got.get("capped"),
                    "target_forms": got.get("target_forms"),
                    "alternatives_generated": got["alternatives_generated"]})
        for alt in got["alternatives"]:
            rec = alt["record"]
            row["alternatives"].append({
                "operator": rec["operator"], "target": rec["target"],
                "direction": rec["direction"],
                "printed": CP.printed(rec),
                "package": alt["package"]})
        if not row["alternatives"]:
            row["status"] = "no_alternative_survived_the_checks"
        out.append(row)
    return out


def construction_diagnostic(parsed, built):
    """The mechanical facts a retry carries.  Never a hint about the answer."""
    lines = []
    if not parsed["readable"]:
        lines.append("Your previous reply had no readable PROPOSE or REPORT "
                     "line.")
    for bad in parsed.get("rejected") or []:
        lines.append("This line could not be read: %s  (%s)"
                     % (bad["line"], bad["why"]))
    for row in built or []:
        if row["status"] == "refused":
            lines.append("Your proposal `%s` was refused: %s"
                         % (_show_proposal(row["proposal"]), row["why"]))
        elif row["status"] != "ok":
            why = "; ".join((row.get("refusals_reasons") or [])[:3])
            lines.append("Your proposal `%s` produced nothing that passed the "
                         "checks%s" % (_show_proposal(row["proposal"]),
                                       (": " + why) if why else "."))
    if not lines:
        return None
    lines.append("Reply again with corrected final lines only, in exactly the "
                 "form shown. You may name a different operator, target or "
                 "slots, or reply with a REPORT line.")
    return "\n\n" + "\n".join(lines)


def _show_proposal(p):
    bits = ["operator=%s" % p["operator"], "target=%s" % p["target"]]
    for k, v in sorted((p.get("roles") or {}).items()):
        bits.append("%s=%s" % (k, ",".join(v)))
    if p.get("sources"):
        bits.append("sources=%s" % ",".join(p["sources"]))
    return "; ".join(bits)


def construction(case, view, respond, allow_retry=True):
    prompt = construction_prompt(case)
    oids, targets = set(case["by_oid"]), CS.known_targets(case)
    text, note = respond("construction", view["case_id"], prompt)
    parsed = CF.parse_response(text, oids, targets)
    built = compile_proposals(case, view, parsed["proposals"])
    raw, retried = {"first": text}, False
    if allow_retry and text is not None and not _useful(parsed, built):
        note2 = construction_diagnostic(parsed, built)
        if note2:
            text2, _n = respond("construction", view["case_id"],
                                prompt + note2, retry=True)
            raw["retry"], raw["diagnostic"] = text2, note2.strip()
            retried = True
            p2 = CF.parse_response(text2, oids, targets)
            b2 = compile_proposals(case, view, p2["proposals"])
            if _useful(p2, b2) or not _useful(parsed, built):
                parsed, built = p2, b2
    return {"parsed": parsed, "built": built, "raw": raw, "retried": retried,
            "note": note, "prompt_chars": len(prompt),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def _useful(parsed, built):
    if parsed.get("report") and not parsed.get("proposals"):
        return True
    return any(b["alternatives"] for b in built or [])


# ----------------------------------------------------- stage 4: hypotheses

def formula_line(row, index, case):
    """One candidate, as the selector sees it: everything that decides it.

    Nothing here is a verdict.  The line says what the rule is, where its pieces
    came from, which of them a model named and which code supplied, and warns
    where code invented an identification — the facts a prioritizer needs and
    no judgement it should not be making.
    """
    paths = row["derivation_paths"]
    named = sorted(set(o for p in paths for o in p["model_named_components"]))
    added = set()
    for p in paths:
        if p["required_slot_completions"]:
            added.add("slots %s" % ", ".join(sorted(set(
                p["required_slot_completions"]))))
        if p["system_guard_supplements"]:
            added.add("guard %s" % ", ".join(sorted(set(
                p["system_guard_supplements"]))))
        if p["system_direction_variant"]:
            added.add("the reverse direction")
        if p["system_target_form_variant"]:
            added.add("the conclusion's predicate")
        if p["system_scope_variant"]:
            added.add("generalisation")
        if p["system_structural_supplement"]:
            added.add("the whole proposal (structural supplement)")
    sentences = []
    for p in paths:
        for s in p.get("source_sentences") or []:
            if s not in sentences:
                sentences.append(s)
    targets = sorted(set(str(p.get("target")) for p in paths))
    modes = []
    for t in targets:
        g = case["by_gid"].get(t)
        if g is not None:
            modes.append("%s (%s)" % (t, "supply"
                                      if g.get("question_target") == "positive"
                                      else "contradict"))
        else:
            modes.append("%s (a word, not a question expression)" % t)
    directions = sorted(set(str(p.get("direction")) for p in paths))
    ops = sorted(set(p["operator"] for p in paths))
    unverified = [a.get("detail") for p in paths for a in p["attachments"]
                  if a.get("status") == "unverified_attachment"]
    L = ["  F%-3d %s" % (index, row["printed_formula"])]
    if sentences:
        L.append("       from: %s" % "  ".join('"%s"' % s[:90]
                                               for s in sentences[:2]))
    L.append("       target %s, %s, operator %s"
             % ("; ".join(modes[:2]),
                "forward" if directions == ["source_to_target"]
                else "reverse" if directions == ["target_to_source"]
                else "/".join(d.replace("_to_", "→") for d in directions),
                ", ".join(ops[:2])))
    L.append("       model named: %s        code added: %s"
             % (", ".join(named) or "nothing",
                "; ".join(sorted(added)) or "nothing"))
    if unverified:
        L.append("       warning: an identification was invented — %s"
                 % unverified[0])
    L.append("       %d derivation path(s)" % len(paths))
    return "\n".join(L)


def formula_display(rows, cap=FORMULA_DISPLAY_CAP):
    """Which candidates the selector sees, and exactly which it does not."""
    if len(rows) <= cap:
        return {"shown": list(rows), "omitted": [],
                "policy": "all %d formulas shown (at or below the %d cap)"
                          % (len(rows), cap)}
    keep = list(rows[:cap - GROUPS_DIVERSE_BLOCK])
    seen = set()
    for r in keep:
        seen.add(_formula_signature(r))
    extra = []
    for r in rows[cap - GROUPS_DIVERSE_BLOCK:]:
        if len(extra) >= GROUPS_DIVERSE_BLOCK:
            break
        s = _formula_signature(r)
        if s in seen:
            continue
        seen.add(s)
        extra.append(r)
    shown = keep + extra
    kept = set(r["printed_formula"] for r in shown)
    return {"shown": shown,
            "omitted": [{"printed": r["printed_formula"],
                         "paths": len(r["derivation_paths"])}
                        for r in rows if r["printed_formula"] not in kept],
            "diverse_added": [r["printed_formula"] for r in extra],
            "policy": "%d formulas: the first %d of the enumeration, plus %d "
                      "with an unseen shape; the rest are recorded, not "
                      "discarded" % (len(rows), cap - GROUPS_DIVERSE_BLOCK,
                                     len(extra))}


def _formula_signature(row):
    """A formula's mechanical shape: heads, body predicates, operators."""
    paths = row["derivation_paths"]
    return (str(row["head"])[:80],
            tuple(sorted(str(b)[:40] for b in row["body"])),
            tuple(sorted(set(p["operator"] for p in paths))))


def formula_selector_prompt(view, case, rows, display):
    import alignment_protocol as P
    lines = []
    for i, r in enumerate(display["shown"], start=1):
        lines.append(formula_line(r, i, case))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % view["input_text"],
        "THE RULES CODE BUILT:\n%s" % "\n\n".join(lines),
    ])
    if display["omitted"]:
        body += "\n\n(%d further rules are not shown.)" % len(
            display["omitted"])
    prompt = prompt_text(FORMULA_SELECTOR_PROMPT) + "\n\n" + body
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


def select_formulas(view, case, rows, respond, allow_retry=True,
                    cap=MAX_SELECTED_FORMULAS):
    """The LLM prioritizes which candidates admission judges.

    Selection reorders and truncates a list.  It does not touch a formula, a
    clause or a derivation path, and everything it leaves out stays in the
    record under `not_selected`.
    """
    display = formula_display(rows)
    ids = ["F%d" % (i + 1) for i in range(len(display["shown"]))]
    prompt = formula_selector_prompt(view, case, rows, display)
    text, note = respond("formula_selector", view["case_id"], prompt)
    got = parse_selection(text, set(ids), cap, prefix="F")
    raw, retried = {"first": text}, False
    if allow_retry and text is not None and not got["readable"]:
        text2, _n = respond("formula_selector", view["case_id"],
                            prompt + SELECTION_RETRY, retry=True)
        raw["retry"] = text2
        retried = True
        got2 = parse_selection(text2, set(ids), cap, prefix="F")
        if got2["readable"]:
            got = got2
    by_id = dict(zip(ids, display["shown"]))
    chosen = [by_id[i] for i in got["selected"]]
    fallback = not chosen
    if fallback:
        chosen = display["shown"][:cap]
    return {"stage": "formula_selection",
            "formulas_total": len(rows),
            "formulas_shown": len(display["shown"]),
            "display_policy": display["policy"],
            "omitted_from_the_display": display["omitted"],
            "selection": got, "selected_ids": got["selected"],
            "chosen": chosen,
            "used_the_fallback": fallback,
            "not_selected": [r["printed_formula"] for r in rows
                             if r not in chosen],
            "retried": retried, "raw": raw, "note": note,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


def hypotheses(case, view, built_construction, cap=MAX_HYPOTHESES,
               select=None):
    """Canonical formulas the model reached, each with every derivation path.

    A formula enters only if some model proposal produces it.  The enumerated
    space is walked so that a formula carries every derivation that also
    reaches it, but a formula NO model proposal reaches is not a runtime
    hypothesis — it is counted and reported, never quietly admitted.

    `select(rows) -> selection record` prioritizes the pool.  Without one the
    first `cap` of the enumeration order are kept, which is the AL-76
    behaviour and is a truncation, not a ranking: it is what cut the one
    formula in eb-0006 that said what the reviewed rule says.
    """
    proposals = built_construction["parsed"].get("proposals") or []
    acc, packages = CP.collect(case, view["case_id"], proposals)
    rows = acc.rows()
    reached = [r for r in rows if CP.model_reached(r)]
    reached.sort(key=lambda r: (min(
        i for i, p in enumerate(r["derivation_paths"])
        if p["source_run"] == CP.MODEL_RUN), r["printed_formula"]))
    if select is not None:
        chosen = select(reached)
        kept = chosen["chosen"]
        how = {"selector": chosen["stage"],
               "formulas_shown": chosen["formulas_shown"],
               "display_policy": chosen["display_policy"],
               "selected_ids": chosen["selected_ids"],
               "used_the_fallback": chosen["used_the_fallback"],
               "retried": chosen["retried"],
               "omitted_from_the_display": chosen["omitted_from_the_display"],
               "not_selected": chosen["not_selected"],
               "prompt_sha256": chosen["prompt_sha256"],
               "raw": chosen["raw"]}
    else:
        kept = reached[:cap]
        how = {"selector": None, "cap": cap,
               "not_selected": [r["printed_formula"] for r in reached[cap:]]}
    for i, r in enumerate(kept):
        r["variant_id"] = chr(ord("A") + i)
    return {
        "formulas_from_model_proposals": len(reached),
        "formulas_in_the_enumerated_space_only": len(rows) - len(reached),
        "kept": kept,
        "packages": dict((r["printed_formula"], packages[r["printed_formula"]])
                         for r in kept if r["printed_formula"] in packages),
        "cap": cap,
        "selection": how,
        "dropped_by_the_cap": how["not_selected"],
        "note": "a formula enters only if a model proposal produces it; the "
                "enumerated space contributes provenance, not hypotheses. "
                "Nothing left out is deleted: every formula not selected is "
                "listed here by name.",
    }


# ------------------------------------------------------ stage 5: admission

def _render_path(p):
    lines = ["  PATH %s" % p["path_id"]]
    lines.append("    model named: %s"
                 % (", ".join(p["model_named_components"]) or "none"))
    if p["model_named_components"]:
        lines.append("    operator: %s" % p["operator"])
    else:
        lines.append("    system generated: %s%s" % (
            p["operator"],
            " (structural supplement)" if p["system_structural_supplement"]
            else ""))
    added = []
    if p["required_slot_completions"]:
        added.append("slots %s" % ", ".join(p["required_slot_completions"]))
    if p["system_guard_supplements"]:
        added.append("guard %s" % ", ".join(p["system_guard_supplements"]))
    if p["system_direction_variant"]:
        added.append("the reverse direction")
    if p["system_target_form_variant"]:
        added.append("the conclusion's predicate")
    if p["system_scope_variant"]:
        added.append("generalisation")
    lines.append("    code added: %s" % ("; ".join(added) or "nothing"))
    if p["has_unverified_attachment"]:
        for a in p["attachments"]:
            if a.get("status") == "unverified_attachment":
                lines.append("    attachment: UNVERIFIED — %s"
                             % a.get("detail"))
    else:
        lines.append("    attachment: none")
    return "\n".join(lines)


def group_title(case, front):
    """A mechanical description of the unresolved interface.  No gold.

    The hand-written titles of the earlier probes are not available at runtime
    and must not be: they were written by someone who had read the reviewed
    rule.  This one is built from the group's own fields.
    """
    if not front["selected"]:
        return "the unresolved interface"
    gid = front["selected"][0]
    g = next((x for x in front["groups"] if x["group_id"] == gid), None)
    if g is None:
        return "the unresolved interface"
    return "the unresolved %s interface %s%s(%s)" % (
        g.get("question_target"), "" if g.get("sign") == "+" else "not ",
        g.get("predicate"), g.get("label") or "")


def admission_challenge(case, view, front, kept):
    """The judge's input: the passage, its atoms, and every candidate rule."""
    variants = []
    for r in kept:
        guards = _guard_rows(case, r)
        variants.append({
            "variant": r["variant_id"],
            "hypothesis_id": r["hypothesis_id"],
            "canonical_formula": r["canonical_formula"],
            "printed": r["printed_formula"],
            "rule": {"body": r["body"], "head": r["head"]},
            "derivation_paths": r["derivation_paths"],
            "provenance": FH.summarise(r),
            "rendered_paths": "\n\n".join(_render_path(p)
                                          for p in r["derivation_paths"]),
            "guards": guards,
        })
    return {"group_id": view["case_id"], "case_id": view["case_id"],
            "title": group_title(case, front),
            "english": (view["input_text"] or "").strip(),
            "source_atoms": [{"oid": o["oid"], "unit": o["unit"],
                              "role": o["role"], "atom": o["shown"],
                              "sentence": o["sentence"]}
                             for o in case["occurrences"]],
            "variants": variants}


def _guard_rows(case, row):
    """Which body literals came from a guard supplement, with their atoms."""
    out, seen = [], set()
    for p in row["derivation_paths"]:
        for occ in p["system_guard_supplements"]:
            if occ in seen:
                continue
            seen.add(occ)
            o = case["by_oid"].get(occ)
            if o is None:
                for r in case["occurrences"]:
                    if r["occurrence_id"] == occ or r["oid"] == occ:
                        o = r["occ"]
                        break
            shown = None
            for r in case["occurrences"]:
                if r["oid"] == occ or r["occurrence_id"] == occ:
                    shown = r["shown"]
                    break
            out.append({"occurrence": occ, "atom": shown})
    return out


def admission_prompt(challenge):
    import alignment_protocol as P
    L = ["THE PASSAGE", "", challenge["english"], "",
         "WHAT THE TRANSLATION PRODUCED", "",
         "Each line is one atom, with the role of the sentence it came from. A "
         "line marked `question` comes from the question and asserts nothing.",
         ""]
    by_unit = {}
    for a in challenge["source_atoms"]:
        by_unit.setdefault(a["unit"], []).append(a)
    for unit in sorted(by_unit):
        rows = by_unit[unit]
        L.append("  %s  %s" % (unit, (rows[0]["sentence"] or "").strip()))
        for a in rows:
            L.append("    %-5s %-16s %s" % (a["oid"], a["role"], a["atom"]))
        L.append("")
    L.append("THE QUESTION AT ISSUE: %s" % challenge["title"])
    L.append("")
    L.append("THE CANDIDATE RULES")
    L.append("")
    for v in challenge["variants"]:
        L.append("  %s. %s" % (v["variant"], v["printed"]))
        L.append("")
        L.append("\n".join("  " + x for x in v["rendered_paths"].splitlines()))
        L.append("")
    prompt = prompt_text(ADMISSION_PROMPT) + "\n\n" + "\n".join(L)
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold",
                                              "adjudication"))
    return prompt


ADMISSION_RETRY = ("\n\nYour previous reply was missing an ASSESS line for one "
                   "or more candidates, or used a value or path id outside the "
                   "ones printed. Reply with exactly one ASSESS line per "
                   "candidate and nothing after them.")


def path_maps(challenge):
    ids = [v["variant"] for v in challenge["variants"]]
    paths = dict((v["variant"], [p["path_id"] for p in v["derivation_paths"]])
                 for v in challenge["variants"])
    unverified = dict(
        (v["variant"], [p["path_id"] for p in v["derivation_paths"]
                        if p["has_unverified_attachment"]])
        for v in challenge["variants"])
    scope = dict((v["variant"],
                  AP.GENERALISED if all(p["scope"] == "generalised"
                                        for p in v["derivation_paths"])
                  else "as written")
                 for v in challenge["variants"])
    return ids, paths, unverified, scope


def admission(challenge, respond, allow_retry=True):
    ids, paths, unverified, scope = path_maps(challenge)
    prompt = admission_prompt(challenge)
    text, note = respond("admission", challenge["group_id"], prompt)
    got = AP.parse_assessments(text, ids, paths, unverified, scope)
    raw, retried = {"first": text}, False
    if allow_retry and text is not None and not got["complete"]:
        text2, _n = respond("admission", challenge["group_id"],
                            prompt + ADMISSION_RETRY, retry=True)
        raw["retry"] = text2
        retried = True
        got2 = AP.parse_assessments(text2, ids, paths, unverified, scope)
        if got2["complete"] or not got["readable"]:
            got = got2
    return {"parsed": {k: got[k] for k in ("readable", "complete", "missing",
                                           "rejected", "assessments")},
            "variants": ids, "paths": paths, "unverified_paths": unverified,
            "scope": scope, "raw": raw, "retried": retried, "note": note,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}


# ----------------------------------------------------- stage 6: attachment

# A guard attachment reads `<var> of <occurrence> with <what it was identified
# with>`, and the right-hand side is either another unit's variable (`S2/X`) or
# a constant (`canyon wall 1`).  AL-74's probe recognised only the first, so a
# constant identification was never asked about and was recorded NOT_ASSESSED
# without anyone being asked.  Both are recognised here; the question the prompt
# puts — are these the same thing? — is the same question either way.
_DETAIL_VAR = re.compile(r"^\s*(\S+)\s+of\s+(\S+)\s+with\s+(\S+?)/(\S+)\s*$")
_DETAIL_CONST = re.compile(r"^\s*(\S+)\s+of\s+(\S+)\s+with\s+(.+?)\s*$")


def parse_detail(detail):
    """-> (term, occurrence, unit or None, other term) or None."""
    m = _DETAIL_VAR.match(detail or "")
    if m:
        return m.group(1), m.group(2), m.group(3), m.group(4)
    m = _DETAIL_CONST.match(detail or "")
    if m:
        return m.group(1), m.group(2), None, m.group(3)
    return None


def attachment_rows(challenge, case):
    """The identifications code invented in this case, each asked about once.

    One row per CASE, not per candidate.  The same identification recurs across
    candidates — a guard attached to the same variable produces the same
    detail string — and the judgement is a property of the identification, not
    of the rule that carries it.  Asking once and applying the answer wherever
    that detail appears assesses every candidate within one call, instead of
    spending the budget on the first candidate and leaving the rest recorded
    NOT_ASSESSED for want of a call.
    """
    by_occ, by_unit = {}, {}
    for o in case["occurrences"]:
        by_occ[o["occurrence_id"]] = o
        by_occ[o["oid"]] = o
        by_unit.setdefault(o["unit"], []).append(o)
    seen, idents, rules, variants = set(), [], [], []
    for v in challenge["variants"]:
        for p in v["derivation_paths"]:
            for a in p["attachments"]:
                if a.get("status") != "unverified_attachment":
                    continue
                detail = a.get("detail") or ""
                if detail in seen:
                    continue
                seen.add(detail)
                got = parse_detail(detail)
                if not got:
                    continue
                term_a, occ_a, unit_b, term_b = got
                oa = by_occ.get(occ_a)
                pool = (by_unit.get(unit_b) or []) if unit_b else \
                    case["occurrences"]
                others = [o for o in pool
                          if term_b in json.dumps(o["literal"])]
                idents.append({
                    "ident_id": "A%d" % (len(idents) + 1),
                    "detail": detail,
                    "guard_occurrences": p["system_guard_supplements"],
                    "left": {"term": term_a,
                             "occurrence": oa["oid"] if oa else occ_a,
                             "atom": oa["shown"] if oa else None,
                             "unit": oa["unit"] if oa else None,
                             "sentence": (oa or {}).get("sentence")},
                    "kind": ("another sentence's variable" if unit_b
                             else "a constant"),
                    "right": {"term": term_b, "unit": unit_b,
                              "occurrences": [{"occurrence": o["oid"],
                                               "atom": o["shown"]}
                                              for o in others[:4]],
                              "sentence": (others[0].get("sentence")
                                           if others else None)},
                    "resulting_guard": next(
                        (x["atom"] for x in v["guards"]
                         if x["occurrence"] in p["system_guard_supplements"]),
                        None),
                    "complete_rule": v["printed"],
                    "first_seen_in": v["variant"],
                    "path_ids": [q["path_id"] for q in v["derivation_paths"]
                                 if any(y.get("detail") == detail
                                        for y in q["attachments"])],
                })
                if v["variant"] not in variants:
                    variants.append(v["variant"])
                if v["printed"] not in rules:
                    rules.append(v["printed"])
    if not idents:
        return []
    return [{"group_id": challenge["group_id"],
             "variant": "+".join(variants),
             "variants": variants,
             "english": challenge["english"],
             "printed_formula": rules[0],
             "rules": rules,
             "identifications": idents}]


def attachment_prompt(row):
    import alignment_protocol as P
    L = ["THE PASSAGE", "", row["english"], "",
         "THE RULE THAT WAS BUILT" if len(row.get("rules") or [1]) == 1
         else "THE RULES THAT WERE BUILT", ""]
    for r in (row.get("rules") or [row["printed_formula"]]):
        L.append("  " + r)
    L += ["", "THE IDENTIFICATIONS CODE MADE", ""]
    for i in row["identifications"]:
        L.append("  %s" % i["ident_id"])
        L.append("    code decided that `%s` in one sentence and `%s` in "
                 "another are the same thing."
                 % (i["left"]["term"], i["right"]["term"]))
        L.append("    first sentence  (%s): %s"
                 % (i["left"]["unit"], (i["left"]["sentence"] or "").strip()))
        L.append("        the atom:   %s   [%s]"
                 % (i["left"]["atom"], i["left"]["occurrence"]))
        L.append("        the term:   %s" % i["left"]["term"])
        L.append("    the other side (%s): %s"
                 % (i["right"]["unit"] or i.get("kind") or "a constant",
                    (i["right"]["sentence"] or "").strip()))
        for o in i["right"]["occurrences"][:4]:
            L.append("        the atom:   %s   [%s]" % (o["atom"],
                                                        o["occurrence"]))
        L.append("        the term:   %s" % i["right"]["term"])
        if i["resulting_guard"]:
            L.append("    the guard this attaches: %s" % i["resulting_guard"])
        L.append("    the complete rule: %s" % i["complete_rule"])
        L.append("")
    prompt = prompt_text(ATTACHMENT_PROMPT) + "\n\n" + "\n".join(L)
    P.assert_no_leak(prompt, extra_forbidden=("reviewed", "accepted answer",
                                              "expected answer", "gold"))
    return prompt


ATTACHMENT_RESULTS = ("SUPPORTED", "POSSIBLE", "UNSUPPORTED")
ATTACHMENT_DEFAULT = "POSSIBLE"


def parse_attachment(text, ids):
    """Only IDENT lines are read.  Silence is recorded, never taken as yes."""
    got, bad = {}, []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("*_# ")
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        if k.strip().strip("*_# ").upper() != "IDENT":
            continue
        m = re.match(r"^\s*(A\d+)\s*=\s*([A-Z_]+)\s*;?\s*(.*)$", v.strip())
        if not m:
            bad.append({"line": line[:160], "why": "not `A<n> = RESULT; ...`"})
            continue
        vid, result, rest = m.group(1), m.group(2).upper(), m.group(3)
        if vid not in ids:
            bad.append({"line": line[:160], "why": "unknown id %r" % vid})
            continue
        if result not in ATTACHMENT_RESULTS:
            bad.append({"line": line[:160],
                        "why": "unknown result %r" % result[:30]})
            continue
        reason = re.sub(r"^reason\s*=\s*", "", rest.strip(), flags=re.I)
        got[vid] = {"result": result, "reason": reason[:300],
                    "explicitly_assessed": True}
    for i in ids:
        if i not in got:
            got[i] = {"result": ATTACHMENT_DEFAULT, "reason": "",
                      "explicitly_assessed": False,
                      "note": "not explicitly assessed; recorded as %s, which "
                              "is not approval" % ATTACHMENT_DEFAULT}
    return {"readable": any(v["explicitly_assessed"] for v in got.values()),
            "results": got, "rejected": bad,
            "assessed": sum(1 for v in got.values()
                            if v["explicitly_assessed"]),
            "total": len(ids)}


def attachment(row, respond):
    ids = [i["ident_id"] for i in row["identifications"]]
    prompt = attachment_prompt(row)
    text, note = respond("attachment", "%s/%s" % (row["group_id"],
                                                  row["variant"]), prompt)
    parsed = parse_attachment(text, ids)
    return {"group_id": row["group_id"], "variant": row["variant"],
            "identifications": row["identifications"], "parsed": parsed,
            "raw": text, "note": note}


# --------------------------------------------------------- stage 7: records

BEST_FIRST = ["NONE_INVENTED", "SUPPORTED_IDENTIFICATION",
              "POSSIBLE_IDENTIFICATION", "UNSUPPORTED_IDENTIFICATION"]
_MAP = {"SUPPORTED": "SUPPORTED_IDENTIFICATION",
        "POSSIBLE": "POSSIBLE_IDENTIFICATION",
        "UNSUPPORTED": "UNSUPPORTED_IDENTIFICATION"}


def attachment_index(attachment_results):
    """detail -> the assessed identification, for the whole case.

    Keyed by the identification itself: the judgement is about the two terms,
    not about which candidate happens to carry them, so one answer applies
    wherever that identification appears.  An unassessed one keeps
    NOT_ASSESSED, which is not approval.
    """
    out = {}
    for r in attachment_results:
        by_id = {i["ident_id"]: i for i in r["identifications"]}
        for ident, res in (r["parsed"].get("results") or {}).items():
            if ident not in by_id:
                continue
            det = by_id[ident]["detail"]
            out[det] = {"ident_id": ident,
                        "result": _MAP.get(res["result"], "NOT_ASSESSED")
                        if res.get("explicitly_assessed") else "NOT_ASSESSED",
                        "judged_value": res["result"],
                        "reason": res.get("reason", ""),
                        "explicitly_assessed": res.get("explicitly_assessed"),
                        "left": by_id[ident]["left"],
                        "right": by_id[ident]["right"]}
    return out


def attachment_axis(variant, assessed):
    """Best available derivation, with the worst one recorded beside it."""
    paths = variant["derivation_paths"]
    clean = [p["path_id"] for p in paths if not p["has_unverified_attachment"]]
    per_path = []
    for p in paths:
        details = [a.get("detail") for a in p["attachments"]
                   if a.get("status") == "unverified_attachment"]
        if not details:
            per_path.append({"path_id": p["path_id"],
                             "result": "NONE_INVENTED", "identifications": []})
            continue
        rows = [assessed.get(d) for d in details]
        results = [r["result"] if r else "NOT_ASSESSED" for r in rows]
        worst = max(results, key=lambda x: BEST_FIRST.index(x)
                    if x in BEST_FIRST else 2)
        per_path.append({"path_id": p["path_id"], "result": worst,
                         "identifications": [r for r in rows if r]})
    best = min([p["result"] for p in per_path],
               key=lambda x: BEST_FIRST.index(x) if x in BEST_FIRST else 2)
    worst = max([p["result"] for p in per_path],
                key=lambda x: BEST_FIRST.index(x) if x in BEST_FIRST else 2)
    return best, {"best_available": best, "worst_on_any_path": worst,
                  "clean_path_ids": clean,
                  "a_clean_derivation_exists": bool(clean),
                  "per_path": per_path,
                  "identifications": list(assessed.values())}


def records(challenge, judged, attachment_results):
    """Six-axis records, one per canonical formula."""
    index = attachment_index(attachment_results)
    out = []
    for v in challenge["variants"]:
        a = (judged["parsed"]["assessments"] or {}).get(v["variant"])
        if a is None:
            continue
        details = set(x.get("detail") for p in v["derivation_paths"]
                      for x in p["attachments"]
                      if x.get("status") == "unverified_attachment")
        assessed = dict((d, index[d]) for d in details if d in index)
        result, detail = attachment_axis(v, assessed)
        facts = GF.guard_facts(v["rule"]["body"], v["rule"]["head"],
                               v["guards"],
                               [x for p in v["derivation_paths"]
                                for x in p["attachments"]])
        scope = AP.GENERALISED if all(p["scope"] == "generalised"
                                      for p in v["derivation_paths"]) \
            else "as written"
        rec = AR.record(
            variant_id=v["variant"], hypothesis_id=v["hypothesis_id"],
            printed_formula=v["printed"],
            semantic=a["semantic_status"], evidence=a["evidence_basis"],
            passage=a["passage_support"], direction=a["direction_support"],
            restriction=a["restriction_status"],
            attachment_result=result, attachment_detail=detail,
            guard_facts_rows=facts,
            derivation_paths=v["derivation_paths"], scope=scope,
            reason=a["reason"], supporting_paths=a["supporting_paths"],
            uncertain_paths=a["uncertain_paths"],
            attachment_reason="; ".join(
                "%s: %s" % (r["ident_id"], (r["reason"] or "")[:80])
                for r in assessed.values()) if assessed else "")
        rec["guard_summary"] = GF.summarise(facts)
        rec["case_id"] = challenge["group_id"]
        out.append(rec)
    return out


# ---------------------------------------------------------- stage 8: worlds

def run_worlds(view, recs, packages, gk, budget=None, weight=WORLD_WEIGHT):
    """One gk world per eligible canonical formula.  Never stops at the first.

    The clause is full confidence; the weight is applied to the proof gk
    returned.  Archived and rejected records are refused by the transport, and
    the refusal is logged there.
    """
    spec = AR.world_specifications(recs)
    hyps = WT.hypotheses_from_records(recs, packages, case_id=view["case_id"])
    by_id = dict((h["record_hypothesis_id"], h) for h in hyps)
    stored = {"stage1": view["stage1"], "stage2": view["stage2"],
              "final_clauses": view["final_clauses"],
              "input_text": view["input_text"]}
    out, skipped = [], []
    for w in spec["worlds"]:
        h = by_id.get(w["hypothesis_id"])
        if h is None:
            skipped.append({"variant": w["variant_id"], "why": "the transport "
                            "refused it or no package was resolved"})
            continue
        if budget is not None and not budget():
            skipped.append({"variant": w["variant_id"],
                            "why": "gk call cap reached before this world"})
            continue
        # The external weight rides on the hypothesis, never into the clause:
        # `build_world` compiles at full confidence whatever the weight says,
        # and `weights` is what post-gk scoring charges.
        h = dict(h, weight=weight)
        world = WT.build_world("dyn_%s_%s" % (view["case_id"], w["variant_id"]),
                               h, stored, view["configuration"])
        got = WT.submit(
            world, h, stored,
            lambda clauses: gk(clauses, stored,
                               "%s/%s" % (view["case_id"], w["variant_id"]),
                               dynamic=True))
        scored = DS.from_raw(got.get("raw") or "{}", world["clause_provenance"],
                             world["weights"],
                             bridge_world_weight=world["bridge_world_weight"])
        out.append({
            "variant": w["variant_id"], "hypothesis_id": h["hypothesis_id"],
            "world_id": world["world_id"], "formula": h["printed_formula"],
            "world_kind": w["world_kind"], "order": w["order"],
            "order_key": w["order_key"], "axes": w["axes"],
            "compiled_clauses": world["compiled_bridge_clauses"],
            "clause_has_block": BW.has_block(
                world["compiled_bridge_clauses"]),
            "clause_confidence_annotations": [
                c.get("@confidence") for c in world["compiled_bridge_clauses"]],
            "derivation_path_count": world["derivation_path_count"],
            "gk_native_confidence": scored["gk_confidence"],
            "abstraction_world_weight": weight,
            "adjusted_dynamic_confidence": scored["dynamic_confidence"],
            "cited_hypothesis_ids": scored["bridge_hypotheses_used"],
            "stored_gk_threshold": (got.get("thresholds") or {}).get(
                "stored_gk_threshold"),
            "dynamic_gk_threshold": (got.get("thresholds") or {}).get(
                "dynamic_gk_threshold"),
            "conservative_formatter_answer": got.get("answer"),
            "scored": scored,
            "rendered": DS.render(scored),
            "seconds": got.get("seconds"),
            "error": got.get("error"),
        })
    return {"world_set": spec, "worlds": out, "skipped": skipped,
            "transport_log": WT.log()}


# ------------------------------------------------------------------ driver

def run_case(view, respond, gk, bounds=None, weight=WORLD_WEIGHT,
             cap=MAX_HYPOTHESES, mode=ISOLATED, **kw):
    """One case, end to end.  Every stage it passed and every stage it stopped
    at is recorded; a case never disappears silently.

    `mode` selects the runtime.  The isolated path below is untouched by the
    pooled one: pooled_discovery calls the shared stages of this module and
    implements its own pooling, so nothing here changes when it runs.
    """
    if mode not in DYNAMIC_MODES:
        raise RuntimeError_("unknown dynamic mode %r" % mode)
    if mode == POOLED:
        import pooled_discovery as PD
        return PD.run_case(view, respond, gk, bounds=bounds, weight=weight,
                           **kw)
    bounds = bounds or {}
    trace = [{"stage": "front_door"}]
    front = front_door(view, gk)
    result = {"case_id": view["case_id"], "view_sha256": view_hash(view),
              "conservative": front, "trace": trace,
              "dynamic_work_done": False}
    if front["resolved"]:
        trace.append({"stage": "stopped", "why": "the conservative front door "
                      "answered %r; no dynamic work was done" % front["answer"]})
        result["stopped_at"] = "front_door_answered"
        return result

    result["dynamic_work_done"] = True
    trace.append({"stage": "frontier"})
    fr = frontier(view)
    result["frontier"] = {k: fr[k] for k in ("version", "counts", "selected",
                                             "selection_policy", "interfaces")}
    if bounds.get("group_selector", True):
        trace.append({"stage": "group_selection"})
        pick = select_groups(view, fr, source_atoms(view), respond,
                             allow_retry=bounds.get("selector_retry", True))
        result["group_selection"] = {k: pick[k] for k in
                                     ("groups_total", "groups_shown",
                                      "shown_ids", "omitted", "diverse_added",
                                      "display_policy", "selection",
                                      "selected", "used_the_fallback",
                                      "fallback", "retried", "raw",
                                      "prompt_sha256")}
        selected_groups = pick["selected"]
    else:
        selected_groups = fr["selected"]
        result["group_selection"] = {"selector": None,
                                     "selected": selected_groups,
                                     "display_policy": fr["selection_policy"]}
    result["frontier"]["groups_used_by_construction"] = selected_groups
    case = case_of(view, fr, selected_groups)

    trace.append({"stage": "construction"})
    con = construction(case, view, respond,
                       allow_retry=bounds.get("construction_retry", True))
    result["construction"] = {
        "retried": con["retried"], "note": con["note"],
        "prompt_sha256": con["prompt_sha256"],
        "parsed": con["parsed"], "built": con["built"], "raw": con["raw"]}
    if not (con["parsed"].get("proposals") or []):
        trace.append({"stage": "stopped", "why": "no readable proposal: %s"
                      % (con["parsed"].get("report") or "nothing proposed")})
        result["stopped_at"] = "construction_produced_nothing"
        return result

    trace.append({"stage": "hypotheses"})
    chooser = None
    if bounds.get("formula_selector", True):
        def chooser(rows):
            trace.append({"stage": "formula_selection"})
            return select_formulas(view, case, rows, respond,
                                   allow_retry=bounds.get("selector_retry",
                                                          True))
    hyp = hypotheses(case, view, con, cap=cap, select=chooser)
    result["hypotheses"] = {k: hyp[k] for k in
                            ("formulas_from_model_proposals",
                             "formulas_in_the_enumerated_space_only", "cap",
                             "selection", "dropped_by_the_cap", "note")}
    if not hyp["kept"]:
        trace.append({"stage": "stopped",
                      "why": "no canonical formula survived construction"})
        result["stopped_at"] = "no_hypothesis_built"
        return result

    challenge = admission_challenge(case, view, fr, hyp["kept"])
    result["candidates"] = [{"variant": v["variant"],
                             "hypothesis_id": v["hypothesis_id"],
                             "printed": v["printed"],
                             "paths": len(v["derivation_paths"]),
                             "provenance": v["provenance"]}
                            for v in challenge["variants"]]

    trace.append({"stage": "admission"})
    judged = admission(challenge, respond,
                       allow_retry=bounds.get("admission_retry", True))
    result["admission"] = {"retried": judged["retried"],
                           "parsed": judged["parsed"], "raw": judged["raw"],
                           "prompt_sha256": judged["prompt_sha256"]}
    if not (judged["parsed"]["assessments"] or {}):
        trace.append({"stage": "stopped", "why": "no readable assessment"})
        result["stopped_at"] = "admission_unreadable"
        return result

    trace.append({"stage": "attachment"})
    rows = attachment_rows(challenge, case)
    attach = []
    for row in rows:
        if bounds.get("attachment_calls_left") is not None and \
                not bounds["attachment_calls_left"]():
            attach.append({"group_id": row["group_id"],
                           "variant": row["variant"],
                           "skipped": "attachment call cap reached",
                           "identifications": row["identifications"],
                           "parsed": {"results": {}, "readable": False,
                                      "assessed": 0,
                                      "total": len(row["identifications"])}})
            continue
        attach.append(attachment(row, respond))
    result["attachment"] = {"rows": len(rows), "results": attach}

    trace.append({"stage": "transport"})
    recs = records(challenge, judged, [a for a in attach
                                       if not a.get("skipped")])
    result["records"] = recs

    trace.append({"stage": "worlds"})
    ran = run_worlds(view, recs, hyp["packages"], gk,
                     budget=bounds.get("gk_budget"), weight=weight)
    result["world_set"] = ran["world_set"]
    result["worlds"] = ran["worlds"]
    result["skipped_worlds"] = ran["skipped"]
    trace.append({"stage": "scored"})
    result["dynamic_answers"] = [
        {"variant": w["variant"], "answer": w["scored"]["answer"],
         "rendered": w["rendered"],
         "gk_native_confidence": w["gk_native_confidence"],
         "abstraction_world_weight": w["abstraction_world_weight"],
         "adjusted_dynamic_confidence": w["adjusted_dynamic_confidence"],
         "cited_hypothesis_ids": w["cited_hypothesis_ids"]}
        for w in ran["worlds"] if w["scored"]["answer"] is not None]
    result["stopped_at"] = None
    return result
