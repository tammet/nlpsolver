"""Semantic interface selector: two arms, prompts and parsing (offline).

Follows the retrieval result in
`memos/MEMO_2026_08_09_interface_candidate_retrieval.md`: enumeration already
contains every reviewed interface, and no hand-written ranking finds it, so the
next thing to try is a model choosing from the surviving pairs.

Two arms, one model configuration:

  `candidates`   the model is given the surviving candidate list and returns
                 candidate ids.
  `occurrences`  the model is given only the producer and consumer lists and
                 must name the pairs itself.

The arms differ in ONE thing — whether code hands over the pairing — so a
difference in result is attributable to that and not to the wording, which is
shared as far as the format allows.

This module builds prompts and parses replies.  It has no transport: nothing
here can make a network call, which is why the whole experiment is testable
before the live-call gate.  No expected answer, no benchmark label and no
prover result may enter a prompt; `alignment_protocol.assert_no_leak` is
applied to every one.
"""

import hashlib
import os
import re

import alignment_candidates as AC
import alignment_issues as AI
import alignment_occurrences as AO
import alignment_protocol as P

ARMS = ("candidates", "occurrences")
PROMPT_VERSION = "v1"
MAX_SELECTIONS = 5

# How many candidates a prompt may carry.  The median case has 95 and the
# largest 343; sending everything would make the arms differ by context length
# as much as by task.  The cap is applied by the SAME order for both arms — the
# order candidates were enumerated in, which carries no ranking information —
# so no hand-written score decides what the model sees.
CANDIDATE_CAP = 120


def prompt_file(arm):
    return os.path.join(P.PROMPT_DIR, "selector_%s_%s.txt" % (arm, PROMPT_VERSION))


def load_prompt(arm):
    with open(prompt_file(arm)) as f:
        return f.read()


def prompt_hash(arm):
    return hashlib.sha256(load_prompt(arm).encode()).hexdigest()


def _arg(a):
    """One argument, with variables marked so a constant is never mistaken for
    a bound object."""
    if isinstance(a, list):
        return "[%s]" % ", ".join(_arg(x) for x in a)
    if AO._is_var(a):
        return "?%s" % a
    return str(a)


def render_atom(o):
    """The COMPLETE logical atom: predicate and every argument, in order.

    An earlier version dropped the label slot, so `isa(element, X)` rendered as
    `isa(X)` — the class name, which is the whole content of the atom, was
    invisible to the reader.  Nothing is elided here.
    """
    args = o.get("arguments_or_roles") or []
    body = "%s(%s)" % (o.get("predicate"), ", ".join(_arg(a) for a in args))
    return "not %s" % body if o["polarity"] == "-" else body


def _position(o):
    """Where the atom sits, in the terms the task cares about."""
    if o.get("in_question"):
        return ("question premise" if o["rule_side"] == "antecedent"
                else "question goal")
    return {"antecedent": "rule premise",
            "conclusion": "rule conclusion"}.get(o["rule_side"], "fact")


def _occ_line(o):
    """One occurrence: complete atom, position, source unit, source phrase."""
    quote = o.get("source_quote")
    return "%-52s [%s, %s]%s" % (
        render_atom(o), _position(o), o["unit_id"],
        "  <- %r" % quote if quote else "")


def _pair_note(p, c, row=None):
    """What code already worked out about this pair: how the arguments line up
    and whether the producer would supply the requirement or contradict it."""
    mapping, swapped = AC.argument_mappings(p, c)
    if mapping:
        m = ", ".join("%s = %s" % (_arg(a), _arg(b)) for a, b in mapping)
    else:
        m = "no argument correspondence"
    rel = ((row or {}).get("features", {}).get("polarity_relation")
           or ("supply" if (AC.available(p) or set()) & (AC.required(c) or set())
               else "contradiction"))
    extra = ", arguments in the opposite order" if swapped else ""
    if rel == "supply":
        what = "the producer would give you the requirement directly"
    else:
        what = "the producer would contradict the requirement (this is how a "\
               "question is answered False)"
    return "mapping: %s%s | %s: %s" % (m, extra, rel, what)


def _sentences(fixture):
    lines = []
    for sent in fixture["stage1"] or []:
        for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
            lines.append("%s: %s" % (u.get("unit_id"), u.get("text")))
    return "\n".join(lines)


def build_candidates_prompt(fixture, gen, cap=CANDIDATE_CAP):
    """Arm A: the surviving candidate list, with ids."""
    rows = gen["candidates"][:cap]
    table = gen["table"]
    by_id = table["by_id"]
    lines = []
    for i, r in enumerate(rows, start=1):
        p, c = by_id[r["producer"]], by_id[r["consumer"]]
        lines.append("K%d: %s\n      -> %s\n      %s"
                     % (i, _occ_line(p), _occ_line(c), _pair_note(p, c, r)))
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "SENTENCES:\n%s" % _sentences(fixture),
        "CANDIDATE PAIRS (%d of %d; the order carries no information):\n%s"
        % (len(rows), len(gen["candidates"]), "\n".join(lines)),
    ])
    prompt = load_prompt("candidates") + "\n\n" + body
    P.assert_no_leak(prompt)
    ids = ["K%d" % (i + 1) for i in range(len(rows))]
    return prompt, rows, ids


def build_occurrences_prompt(fixture, gen):
    """Arm B: producers and consumers, unpaired."""
    table = gen["table"]
    prods = AC.producers(table)
    cons = AC.consumers(table)
    plines = ["P%d: %s" % (i, _occ_line(o)) for i, o in enumerate(prods, start=1)]
    clines = ["C%d: %s" % (i, _occ_line(o)) for i, o in enumerate(cons, start=1)]
    body = "\n\n".join([
        "ENGLISH PROBLEM:\n%s" % fixture["input_text"],
        "SENTENCES:\n%s" % _sentences(fixture),
        "PRODUCERS:\n%s" % "\n".join(plines),
        "CONSUMERS:\n%s" % "\n".join(clines),
    ])
    prompt = load_prompt("occurrences") + "\n\n" + body
    P.assert_no_leak(prompt)
    return prompt, prods, cons


# ---------------------------------------------------------------- parsing

_K_RE = re.compile(r"\bK(\d+)\b")
_PC_RE = re.compile(r"\bP(\d+)\s*->\s*C(\d+)\b")


def parse_selection(text, arm):
    """Ids off the SELECTED line, prose kept whole.

    Only the SELECTED line is interpreted.  An unparsable or absent line is an
    empty selection with `parsed: False` — never a guess, and never a fallback
    that scoops ids out of the prose, which would let a model score by
    mentioning ids while refusing to choose.
    """
    lines = (text or "").splitlines()
    sel_line, why = None, []
    seen_sel = False
    for raw in lines:
        s = raw.strip()
        up = s.upper()
        if up.startswith("SELECTED:"):
            sel_line = s.split(":", 1)[1].strip()
            seen_sel = True
            continue
        if up.startswith("WHY:"):
            why.append(s.split(":", 1)[1].strip())
            continue
        if seen_sel and why:
            why.append(s)
    prose = "\n".join(x for x in why if x).strip()
    if sel_line is None:
        return {"selected": [], "prose": prose, "parsed": False,
                "note": "no SELECTED line"}
    if sel_line.lower() in ("none", "-", "", "[]"):
        return {"selected": [], "prose": prose, "parsed": True,
                "note": "empty selection"}
    if arm == "candidates":
        ids = ["K%s" % m for m in _K_RE.findall(sel_line)]
    else:
        ids = ["P%s->C%s" % (a, b) for a, b in _PC_RE.findall(sel_line)]
    out, seen = [], set()
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return {"selected": out[:MAX_SELECTIONS], "prose": prose,
            "parsed": bool(out),
            "note": "" if out else "SELECTED line carried no usable id",
            "over_limit": len(out) > MAX_SELECTIONS}


def resolve(selection, arm, rows=None, prods=None, cons=None):
    """Selected ids -> (producer occurrence id, consumer occurrence id) pairs.

    An id outside the listed range is dropped and reported; it is never mapped
    to the nearest valid one.
    """
    pairs, bad = [], []
    for sid in selection["selected"]:
        if arm == "candidates":
            n = int(sid[1:])
            if rows is None or not (1 <= n <= len(rows)):
                bad.append(sid)
                continue
            r = rows[n - 1]
            pairs.append((r["producer"], r["consumer"]))
        else:
            m = _PC_RE.match(sid.replace("->", "->"))
            a, b = sid.split("->")
            pi, ci = int(a[1:]), int(b[1:])
            if prods is None or cons is None or not (1 <= pi <= len(prods)) \
                    or not (1 <= ci <= len(cons)):
                bad.append(sid)
                continue
            pairs.append((prods[pi - 1]["occurrence_id"],
                          cons[ci - 1]["occurrence_id"]))
    return pairs, bad


def prompt_parts(prompt, arm):
    """(instructions, case body) — the exact two halves of a built prompt.

    The transport sends the instructions as the system prompt and the body as
    the input, which is how every other role in this pipeline is called.  The
    text is unchanged and provably so: the split is by prefix, and the
    approved hash is of the instruction file.
    """
    instr = load_prompt(arm)
    if not prompt.startswith(instr):
        raise ValueError("prompt does not begin with its instruction file")
    return instr, prompt[len(instr):].lstrip("\n")


def build_repair_prompt(prompt, bad_response, error):
    """The one formatting-repair prompt: the error and the previous response.

    Nothing else is added — no benchmark label, no hint about what the right
    answer would have been, and no second chance after this one.
    """
    return "\n\n".join([
        prompt,
        "Your previous response could not be read: %s" % error,
        "Your previous response was:\n%s" % (bad_response or "")[:3000],
        "Answer again in exactly the required form, starting with a SELECTED: "
        "line.",
    ])


def check_mechanically_valid(pairs, gen):
    """Split selected pairs into the mechanically valid and the rest.

    Arm B names pairs itself, so it can name one that enumeration already ruled
    out — a grounded-constant conflict, an impossible participant mapping, a
    world mismatch.  Such a selection is reported and dropped, with the reason
    enumeration gave, rather than silently scored: a pair the logic cannot
    support is not a retrieval hit however plausible it reads.
    """
    valid = set((r["producer"], r["consumer"]) for r in gen["candidates"])
    by_id = gen["table"]["by_id"]
    ok, rejected = [], []
    for p, c in pairs:
        if (p, c) in valid:
            ok.append((p, c))
            continue
        po, co = by_id.get(p), by_id.get(c)
        why = (AC.reject_reason(po, co) if po and co
               else "an occurrence id that is not in this case")
        rejected.append({"producer": p, "consumer": c,
                         "reason": why or "not in the enumerated pair set"})
    return ok, rejected


def cache_key(arm, case_id, prompt):
    """Distinct per arm, case and prompt version, like the other roles."""
    h = hashlib.sha256()
    for part in ("selector", arm, PROMPT_VERSION, case_id or "", prompt or ""):
        h.update(part.encode())
        h.update(b"\x00")
    return "selector_%s:%s:%s" % (arm, PROMPT_VERSION, h.hexdigest()[:32])


# ---------------------------------------------------------------- estimation

def estimate_tokens(text):
    """A characters-per-token estimate, deliberately crude and stated as such.

    Counting exactly would mean calling a tokenizer we do not have locally, or
    the count-tokens endpoint, which is a live call.  Four characters per token
    is the usual English approximation; the approval bundle reports the
    character counts too so the estimate can be checked without trusting it.
    """
    return int(round(len(text or "") / 4.0))
