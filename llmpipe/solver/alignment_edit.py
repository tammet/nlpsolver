"""Direct Stage-2 package edit engine: parse, splice, validate (DA2 WP3).

Plan: memos/PLAN_2026_08_09_dynamic_abstraction_alignment_pilot_opus5.md §9.

The editor returns complete Stage-2 `@id` packages and nothing else — no JSON
Patch, no paths, no occurrence ids, no prose.  Everything downstream of that is
code: splicing, limits, mechanical validation and the diff.  A mechanically
valid edit is not a semantically accepted one; that judgement belongs to the
verifier and, above it, to the reviewer.

No LLM calls and no GK in this module.  Conversion is invoked only to prove the
edited Stage 2 converts at all.
"""

import copy
import json
import re

import alignment_occurrences as AO

MAX_REPLACEMENTS = 4
MAX_ADDITIONS = 3

# The closed predicate inventory an added rule may use, measured from the heads
# that occur in the stored parses plus the standard role predicates.  An edit
# that invents a predicate is rejected rather than silently converted.
INVENTORY = set([
    "isa", "has type", "is rel2", "have", "has part", "member", "=",
    "has property", "has degree property", "has degree rel2", "$setof",
]) | AO.ROLE_PREDS | AO.MODAL_PREDS

CONTROL_HEADS = AO.LOGICAL_HEADS | {"normally", "state time"}

# Things an edit may never contain: proof plumbing, or an answer word smuggled
# in as a constant.
FORBIDDEN_TOKENS = ("$ans", "$answer", "$goal", "$expected")
ANSWER_WORDS = {"true.", "false.", "unknown.", "probably true.", "probably false.",
                "possibly true.", "possibly false.", "likely true.",
                "likely false."}


class EditError(Exception):
    """A hard failure. The edit is rejected; nothing is guessed around."""


def parse_editor_output(text):
    """WP3.1: exactly one JSON array of complete packages, nothing else.

    Returns the parsed list.  Raises EditError with a message suitable for the
    single formatting-repair call — the message carries the validation error
    only, never a benchmark label or a proof result.
    """
    if text is None:
        raise EditError("empty editor response")
    s = text.strip()
    if s.startswith("```"):
        raise EditError("response is wrapped in a markdown fence; return raw "
                        "JSON only")
    if not s.startswith("["):
        raise EditError("response does not begin with a JSON array; prose and "
                        "explanations are not accepted")
    try:
        obj = json.loads(s)
    except ValueError:
        # Accept the first complete JSON value when what follows is nothing but
        # whitespace and stray closing brackets — the exact failure that lost
        # two cases in the first chain run.  Nothing is inserted or removed
        # INSIDE the parsed value; only trailing debris is ignored.
        try:
            obj, end = json.JSONDecoder().raw_decode(s)
        except ValueError as e2:
            raise EditError("response is not valid JSON: %s" % e2)
        tail = s[end:].strip()
        if tail and set(tail) - set("]}) \t\r\n"):
            raise EditError("text after the JSON value that is not stray "
                            "closing brackets: %r" % tail[:60])
    if not isinstance(obj, list):
        raise EditError("top level is %s, expected a JSON array of packages"
                        % type(obj).__name__)
    for item in obj:
        if (not isinstance(item, list) or len(item) != 3 or item[0] != "@id"
                or not isinstance(item[1], str)):
            raise EditError('each element must be ["@id", "<id>", <package>]; '
                            'got %s' % json.dumps(item)[:120])
        if "op" in item or any(isinstance(x, dict) for x in item):
            raise EditError("JSON Patch style objects are not accepted; return "
                            "complete packages")
        if not AO_is_package(item[2]):
            raise EditError("%s: the third element is not a Stage-2 package "
                            "(holds / question / ask / and)" % item[1])
    return obj


def AO_is_package(pkg):
    if not isinstance(pkg, list) or not pkg:
        return False
    head = pkg[0]
    if head == "holds":
        return len(pkg) == 3
    if head == "question":
        return len(pkg) == 2
    if head == "ask":
        return len(pkg) == 3
    if head == "and" and len(pkg) >= 2:
        return AO_is_package(pkg[1])
    return False


def _ids(stage2):
    return [p for p, _ in AO.packages(stage2)]


def _question_ids(stage2):
    out = []
    for pid, pkg in AO.packages(stage2):
        head = pkg[0] if isinstance(pkg, list) and pkg else None
        if head in ("question", "ask"):
            out.append((pid, head))
        elif head == "and" and isinstance(pkg[1], list) and pkg[1] \
                and pkg[1][0] in ("question", "ask"):
            out.append((pid, pkg[1][0]))
    return out


def splice(stage2, packages):
    """WP3.2 -> (edited, changed, added, renamed).

    The caller's Stage 2 is never mutated.  `renamed` records any added id that
    collided with an existing one and was given a deterministic fresh name.
    """
    if not isinstance(stage2, list) or not stage2 or stage2[0] != "and":
        raise EditError('stored Stage 2 is not an ["and", ...] list')
    original = _ids(stage2)
    out = copy.deepcopy(stage2)
    index = {pid: i for i, (pid, _) in enumerate(AO.packages(stage2), start=1)}
    changed, added, renamed = [], [], {}
    seen_repl = set()
    for item in packages:
        pid, pkg = item[1], item[2]
        if pid in index:
            if not pid.startswith("A"):
                if pid in seen_repl:
                    raise EditError("%s: duplicate replacement id" % pid)
                seen_repl.add(pid)
                out[index[pid]] = ["@id", pid, copy.deepcopy(pkg)]
                changed.append(pid)
                continue
            # an A* id that collides with an existing package is renamed
            new = pid
            n = 1
            while new in index or new in added:
                n += 1
                new = "%s_%d" % (pid, n)
            renamed[pid] = new
            out.append(["@id", new, copy.deepcopy(pkg)])
            added.append(new)
            continue
        if pid.startswith("S"):
            raise EditError("%s: unknown package id; a replacement must name an "
                            "existing package" % pid)
        if not pid.startswith("A"):
            raise EditError("%s: added package ids must start with A" % pid)
        if pid in added:
            raise EditError("%s: duplicate added id" % pid)
        out.append(["@id", pid, copy.deepcopy(pkg)])
        added.append(pid)
    after = _ids(out)
    for pid in original:
        if pid not in after:
            raise EditError("%s: package removed; an edit may replace but never "
                            "delete a package" % pid)
        if after.count(pid) != 1:
            raise EditError("%s: package occurs %d times after splicing"
                            % (pid, after.count(pid)))
    if after[:len(original)] != original:
        raise EditError("original package order was not preserved")
    return out, changed, added, renamed


def _walk_heads(node, out):
    if isinstance(node, list) and node and isinstance(node[0], str):
        out.append(node[0])
        for ch in node[1:]:
            _walk_heads(ch, out)
    elif isinstance(node, list):
        for ch in node:
            _walk_heads(ch, out)


def check_inventory(packages, stage2=None):
    """WP3.3 step 9: an added rule may only use existing predicates.

    Predicate position and term position are checked separately.  A term
    constructor such as `["eventprop", "$target", G]` is not a predicate, and
    walking every nested list head would reject the abstracted encoding's own
    term forms.  A term constructor is allowed when the stored parse already
    uses it: the edit may reuse the case's vocabulary, not invent one.
    """
    import alignment_diff as AD
    known_terms = set()
    if stage2 is not None:
        for _, pkg in AO.packages(stage2):
            for a in AD.atoms_of(pkg):
                for arg in a["atom"][1:]:
                    if isinstance(arg, list) and arg and isinstance(arg[0], str):
                        known_terms.add(arg[0])
    bad = []
    for item in packages:
        for a in AD.atoms_of(item[2]):
            head = a["atom"][0]
            if head not in CONTROL_HEADS and head not in INVENTORY:
                bad.append("%s: %r is not in the closed predicate inventory"
                           % (item[1], head))
            for arg in a["atom"][1:]:
                if isinstance(arg, list) and arg and isinstance(arg[0], str):
                    if arg[0] not in known_terms:
                        bad.append("%s: the term constructor %r does not occur "
                                   "in the stored parse" % (item[1], arg[0]))
    return bad


def check_no_leak(packages):
    """WP3.3 step 10: no proof plumbing and no answer word as a constant."""
    bad = []
    for item in packages:
        blob = json.dumps(item)
        for t in FORBIDDEN_TOKENS:
            if t in blob:
                bad.append("%s: contains the proof-control token %r"
                           % (item[1], t))
        for m in re.findall(r'"([^"]+)"', blob):
            if m.strip().lower() in ANSWER_WORDS:
                bad.append("%s: contains the answer word %r as a constant"
                           % (item[1], m))
    return bad


def validate(stage2, packages, stage1, configuration, input_text=None,
             convert_fn=None):
    """WP3.3, in the plan's order.  -> record dict; never raises for a merely
    invalid edit (only a caller error raises)."""
    rec = {"ok": False, "stage": None, "errors": [], "warnings": [],
           "changed": [], "added": [], "renamed": {}}

    def fail(stage, errs):
        rec["stage"], rec["errors"] = stage, list(errs)
        return rec

    # 1 shape (already enforced by parse_editor_output; re-checked for direct
    #   callers such as the oracle, which bypasses the parser)
    for item in packages:
        if (not isinstance(item, list) or len(item) != 3 or item[0] != "@id"
                or not AO_is_package(item[2])):
            return fail("shape", ["not a complete [\"@id\", id, package]: %s"
                                  % json.dumps(item)[:100]])
    # 2 limits
    existing = set(_ids(stage2))
    n_repl = sum(1 for i in packages if i[1] in existing and not i[1].startswith("A"))
    n_add = len(packages) - n_repl
    if n_repl > MAX_REPLACEMENTS:
        return fail("limits", ["%d replacements exceeds the limit of %d"
                               % (n_repl, MAX_REPLACEMENTS)])
    if n_add > MAX_ADDITIONS:
        return fail("limits", ["%d additions exceeds the limit of %d"
                               % (n_add, MAX_ADDITIONS)])
    # 3 splice; ids survive exactly once
    try:
        edited, changed, added, renamed = splice(stage2, packages)
    except EditError as e:
        return fail("splice", [str(e)])
    rec.update({"changed": changed, "added": added, "renamed": renamed,
                "edited_stage2": edited})
    # 4 exactly one question, same mode
    q_before, q_after = _question_ids(stage2), _question_ids(edited)
    if len(q_after) != 1:
        return fail("question", ["the edit leaves %d question packages, expected 1"
                                 % len(q_after)])
    if q_before and q_after[0] != q_before[0]:
        return fail("question", ["the question package changed from %s to %s"
                                 % (q_before[0], q_after[0])])
    # 5 Stage-2 sanity: no NEW issue
    import stage_sanity
    before_fp = stage_sanity.issue_fingerprints(
        stage_sanity.check_stage2(stage2, stage1, input_text))
    new_issues = [i for i in stage_sanity.check_stage2(edited, stage1, input_text)
                  if (i.kind, i.location) not in before_fp]
    if new_issues:
        return fail("stage2_sanity",
                    ["new %s at %s: %s" % (i.kind, i.location, i.description[:90])
                     for i in new_issues])
    # 6 free variables / binders: no NEW free conclusion variable
    import lc_reference
    def free(s2):
        out = set()
        for pid, pkg in AO.packages(s2):
            for v in lc_reference.free_rule_conclusion_vars(pkg):
                out.add("%s:%s" % (pid, v))
        return out
    new_free = free(edited) - free(stage2)
    if new_free:
        return fail("free_variables",
                    ["the edit introduces free conclusion variable(s) %s"
                     % sorted(new_free)])
    # 9 inventory, 10 leak — checked before conversion so a rejected edit never
    #   reaches the converter
    inv = check_inventory(packages, stage2)
    if inv:
        return fail("inventory", inv)
    leak = check_no_leak(packages)
    if leak:
        return fail("leak", leak)
    # 7 + 8 conversion
    if convert_fn is not None:
        try:
            clauses, fixes = convert_fn(edited, stage1, configuration)
        except Exception as e:
            return fail("conversion", ["%s: %s" % (type(e).__name__, e)])
        if not clauses:
            return fail("conversion", ["conversion produced no clauses"])
        malformed = [c for c in clauses
                     if not isinstance(c, dict) or not c.get("@name")
                     or ("@logic" not in c and "@question" not in c)]
        if malformed:
            return fail("conversion", ["%d malformed GK clause(s)" % len(malformed)])
        rec["conversion_fixes"] = fixes
        rec["clauses"] = clauses
    rec["ok"] = True
    rec["stage"] = "valid"
    return rec
