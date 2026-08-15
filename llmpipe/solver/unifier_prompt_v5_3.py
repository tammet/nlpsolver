"""The v5.3 candidate display: source wording, and forms the converter loses.

Two additions to `unifier_prompt_v5_2`, and nothing in v1-v5.2 changes.

**Source wording beside the compiled atom (WP2).**  v5.2 omits a surface atom
whose conversion changes the predicate family, so `eb2-0020` showed
`have(Eukaryote,X)` and hid the `belong to` relation the English makes salient,
and `folio-0089` showed neither of its two `smart` forms.  Here such an atom is
displayed as the atom the compiler actually receives, with the original relation
printed beneath it as SOURCE WORDING.  The displayed form and its aliases are
both writable, because each alias converts, on its own, to exactly this group's
content literal.

**Clause-native question forms (WP6.2).**  A question clause may hold a literal
no Stage-2 surface form converts back to -- `folio-0089`'s
`is rel2(smart, #:Harry 1, W0, C)`, where `W0` is a world constant the converter
turns into a variable.  Such a literal is displayed exactly as the clause has
it, and a rule using it is compiled by `simple_rule_compiler_v5_3`'s exact
clause-native route rather than by the Stage-2 converter.

Everything else -- the fixed system prompt, the display check, the writability
probe, the three sections, the complete inventory, the question split -- is
v5.1/v5.2's, imported unchanged.
"""

import json

import alignment_occurrences as AO
import simple_rule_compiler_v5_3 as C53
import unifier_abstraction as UA
import unifier_candidates_v3 as CV3
import unifier_candidates_v4 as CV4
import unifier_prompt_v5_1 as P51
import unifier_prompt_v5_2 as P52
import unifier_question_v5_2 as Q52

VERSION = "unifier_prompt_v5_3/1.0"

MAIN_CAP = P52.MAIN_CAP
SECONDARY_CAP = P52.SECONDARY_CAP
MAX_USER_MESSAGE_CHARS = P52.MAX_USER_MESSAGE_CHARS

QUESTION_SECTION = P51.QUESTION_SECTION
CONTENT_SECTION = P51.CONTENT_SECTION
HELPER_SECTION = P51.HELPER_SECTION
SECTION_ORDER = P51.SECTION_ORDER
SECTION_HEADING = P51.SECTION_HEADING
SECTION_PREFIX = P51.SECTION_PREFIX
CLOSING_LINE = P51.CLOSING_LINE

PREMISE = P51.PREMISE
CONCLUSION = P51.CONCLUSION
EITHER = P51.EITHER
ROLE_WORD = P51.ROLE_WORD

DISPLAYED = "displayed"
ALIAS = "converted_from_source_wording"
CLAUSE_NATIVE = "clause_native"

PromptError = P51.PromptError

system_prompt = P51.system_prompt
system_prompt_sha256 = P51.system_prompt_sha256
example_sha256 = P51.example_sha256
check_fixed_inputs = P51.check_fixed_inputs
printed_atom = P51.printed_atom
render_case = P51.render_case
split_case_text = Q52.split_case_text
question_preflight = Q52.question_preflight
complete_inventory = P52.complete_inventory

ALIAS_NOTE = ("A SOURCE WORDING line gives the original relation an atom came "
              "from. You may write either form; both compile to the same "
              "logic.")


# ------------------------------------------------------ WP2: the alias groups

def _content_of(literal, n):
    atom = UA.unsigned_atom(literal)
    return [atom[0]] + list(atom[1:1 + n])


# How many arguments of a compiled literal are the passage's own content.  These
# are the arities the fixed system prompt itself lists for the model; anything a
# conversion appends to the right of them is a context slot (ENCODINGS.md §6).
# A predicate that is not here keeps every argument that is not plainly a
# context term.
CONTENT_ARITY = {
    "isa": 2, "is rel2": 3, "has type": 2, "has actor": 2, "has target": 2,
    "has recipient": 2, "has manner": 2, "has topic": 2, "has location": 3,
    "has property": 2, "has degree property": 4, "has degree rel2": 5,
    "have": 2, "has part": 2, "member": 2, "typical": 1,
}


def _display_from_literal(literal):
    """The writable atom a compiled literal stands for: content args only."""
    atom = UA.unsigned_atom(literal)
    args = list(atom[1:])
    want = CONTENT_ARITY.get(str(atom[0]))
    if want is None:
        tail = len(args)
        while tail > 0 and isinstance(args[tail - 1], (str, list)) \
                and _is_plain_context(args[tail - 1]):
            tail -= 1
    else:
        if len(args) < want:
            return None
        tail = want
    if tail == 0 or not all(C53._is_context_argument(a) for a in args[tail:]):
        return None
    kept = [_strip_entity(a) for a in args[:tail]]
    return _display_clause_atom([atom[0]] + kept)


def _display_clause_atom(atom):
    """Rename CLAUSE variables to `?X`, `?Y`, ...  and nothing else.

    `unifier_abstraction.display_atom` renames every capitalised token, which
    would turn the world constant `W0` of `folio-0089`'s question clause into a
    rule variable before the model ever sees it.
    """
    names = {}

    def go(t):
        if isinstance(t, str):
            if UA.is_clause_variable(t):
                if t not in names:
                    i = len(names)
                    names[t] = (UA.DISPLAY_VARS[i] if i < len(UA.DISPLAY_VARS)
                                else "?V%d" % (i + 1))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    return [atom[0]] + [go(a) for a in atom[1:]]


def _clause_key(literal):
    """A literal up to renaming its CLAUSE variables.

    `unifier_abstraction.alpha_key` normalises every capitalised token, so the
    question literal `is rel2(smart, #:Harry 1, W0, C)` and the converted
    `is rel2(smart, #:Harry 1, ?:W0, C)` would share one key and the fixed-world
    form would look like something already displayed.
    """
    names = {}

    def go(t):
        if isinstance(t, str):
            if UA.is_clause_variable(t):
                names.setdefault(t, "_v%d" % len(names))
                return names[t]
            return t
        if isinstance(t, list) and t:
            return [t[0]] + [go(x) for x in t[1:]]
        return t
    atom = UA.unsigned_atom(literal)
    return json.dumps([atom[0]] + [go(a) for a in atom[1:]])


def _is_plain_context(term):
    """A context term that cannot be mistaken for content: `$c` or `$ctxt`."""
    if isinstance(term, str):
        return term == "$c"
    return isinstance(term, list) and bool(term) and str(term[0]) == "$ctxt"


def _strip_entity(term):
    if isinstance(term, str) and term.startswith("#:"):
        return term[2:]
    if isinstance(term, list) and term:
        return [term[0]] + [_strip_entity(x) for x in term[1:]]
    return term


def _alias_rows(view, configuration, omitted, occurrences, pool):
    """-> rows for atoms v5.2 dropped only because conversion renamed them.

    The displayed atom becomes the one the compiler receives; the surface atom
    it came from is kept as its source wording.
    """
    wanted = []
    for o in omitted:
        reason = str(o.get("reason") or "")
        if not reason.startswith("predicate: "):
            continue
        literal = o.get("compiled_literal")
        lits = o.get("all_compiled_literals") or []
        if not literal or len(lits) > 1 or UA.sign_of(literal) == "-":
            continue
        display = _display_from_literal(literal)
        if display is None:
            continue
        wanted.append({"display": display, "literal": literal,
                       "surface": o["surface_atom"],
                       "source_candidate_ids": o.get("source_candidate_ids")
                       or []})
    return wanted


# --------------------------------------------- WP6.2: clause-native question

def _clause_native_rows(view, occurrences, covered, pool):
    """-> rows for question-clause content literals nothing displays.

    Only question clauses: a literal the question asks about that the model
    cannot write is exactly the gap `folio-0089` exposes.  Source-clause
    literals the converter cannot round-trip stay out of the display.
    """
    out, seen = [], set()
    for o in occurrences:
        if o["source_kind"] != UA.QUESTION or o["is_control"] \
                or o["is_equality"]:
            continue
        literal = o["clause_literal"]
        atom = UA.unsigned_atom(literal)
        if CV3._is_generic(atom):
            continue
        key = _clause_key(atom)
        if key in covered or key in seen:
            continue
        display = _display_from_literal(literal)
        if display is None or UA.is_control_predicate(atom[0]):
            continue
        seen.add(key)
        positive = atom if UA.sign_of(literal) == "+" else atom
        same, opposite, _pop = CV3.match_occurrences(positive, occurrences)
        role = CV3.role_of(same, opposite)
        if role is None:
            continue
        out.append({"display": display, "literal": positive,
                    "clause_name": o["clause_name"],
                    "literal_id": o["literal_id"],
                    "role": ROLE_WORD[role],
                    "internal_role": role,
                    "cost": CV4.opposite_sign_unifiers(positive, pool),
                    "question_linked": True,
                    "same_sign_source_kinds": sorted(set(x["source_kind"]
                                                         for x in same))})
    return out


# ------------------------------------------------------------- the candidates

def _probe_rule(atom):
    return {"rule_id": "PROBE", "canonical": "probe", "printed": "probe",
            "llm_variables": [v for v in _display_vars(atom)],
            "body": [{"sign": "+", "atom": atom}],
            "head": {"sign": "+", "atom": atom}}


def _display_vars(atom):
    out = []
    for t in C53.P53._tokens(atom):
        if isinstance(t, str) and t.startswith("?") and t not in out:
            out.append(t)
    return out


def _fallback_writable(group):
    """Can the exact clause-native compiler carry this atom at all?"""
    rule = _probe_rule(group["atom"])
    try:
        C53.compile_rule_clause_native(rule, [group], "probe::PROBE")
    except Exception as e:                                      # noqa: BLE001
        return False, str(e)[:160]
    return True, None


def build_candidates(view, configuration, complete=None, old=None):
    """The v5.2 candidate record, plus alias and clause-native groups."""
    got = P52.build_candidates(view, configuration, complete, old)
    inventory = UA.inventory(view)
    occurrences = inventory["occurrences"]
    pool = CV3.role_occurrences(occurrences)
    for g in got["groups"]:
        g["source_aliases"] = []
        g["origin_kind"] = DISPLAYED
        g["compiler_route"] = C53.NORMAL_ROUTE
    covered = set(_clause_key(g["literal"]) for g in got["groups"])

    # WP2: atoms whose conversion renames the predicate family
    kept_alias, alias_omitted = [], []
    for row in _alias_rows(view, configuration, got["omitted"], occurrences,
                           pool):
        key = _clause_key(row["literal"])
        display = row["display"]
        same, opposite, _pop = CV3.match_occurrences(row["literal"],
                                                     occurrences)
        role = CV3.role_of(same, opposite)
        if role is None:
            alias_omitted.append({"printed": printed_atom(display),
                                  "reason": "its converted literal occurs in "
                                            "no clause of either sign"})
            continue
        existing = [g for g in got["groups"]
                    if _clause_key(g["literal"]) == key]
        if existing:
            existing[0]["source_aliases"].append(row["surface"])
            continue
        already = [g for g in kept_alias
                   if _clause_key(g["literal"]) == key]
        if already:
            already[0]["source_aliases"].append(row["surface"])
            continue
        kept_alias.append({
            "atom": display, "printed": printed_atom(display),
            "literal": row["literal"],
            "role": ROLE_WORD[role], "internal_role": role,
            "cost": CV4.opposite_sign_unifiers(row["literal"], pool),
            "question_linked": any(o["source_kind"] == UA.QUESTION
                                   for o in same + opposite),
            "same_sign_source_kinds": sorted(set(o["source_kind"]
                                                 for o in same)),
            "surface_atoms": [row["surface"]],
            "source_aliases": [row["surface"]],
            "source_candidate_ids": row["source_candidate_ids"],
            "display_rules_applied": ["converted_predicate_family"],
            "merge_note": None, "merged_display_forms": [],
            "source_roles": [role], "source_costs": [],
            "available_under_the_old_caps": True,
            "hidden_by_the_old_caps": False,
            "origin_kind": ALIAS, "compiler_route": C53.NORMAL_ROUTE,
            "round_trip": {"converted": [row["literal"]],
                           "status": "the displayed atom is the compiled "
                                     "literal itself"},
        })

    # the alias must survive the same round trip and both probe positions
    checked_alias = []
    if kept_alias:
        tries = [(g["atom"], "+") for g in kept_alias]
        errors = []
        converted = CV3.convert_batch(view, tries, configuration,
                                      errors=errors)
        for i, g in enumerate(kept_alias, start=1):
            status, lits = CV3.conversion_of(converted.get("Cv%d" % i) or [])
            n = len(g["atom"]) - 1
            if len(lits) != 1 or not P51._same_content(lits[0], g["literal"],
                                                       n):
                alias_omitted.append({"printed": g["printed"],
                                      "reason": "the displayed form does not "
                                                "convert back to the literal "
                                                "it stands for (%s)"
                                                % json.dumps(lits)[:120]})
                continue
            w = P51.writability(g["atom"], g["literal"], view, configuration)
            if not w["writable"]:
                side = "premise" if not w["premise"]["ok"] else "conclusion"
                alias_omitted.append({"printed": g["printed"],
                                      "reason": "a bridge rule using it as a "
                                                "%s does not contain its "
                                                "content literal" % side})
                continue
            g["writability"] = {k: {"ok": v["ok"], "why": v["why"]}
                                for k, v in w.items() if isinstance(v, dict)}
            g["round_trip"]["converted"] = lits
            checked_alias.append(g)
            covered.add(_clause_key(g["literal"]))

    # WP6.2: question literals nothing displays
    native = []
    for row in _clause_native_rows(view, occurrences, covered, pool):
        g = {"atom": row["display"], "printed": printed_atom(row["display"]),
             "literal": row["literal"], "role": row["role"],
             "internal_role": row["internal_role"], "cost": row["cost"],
             "question_linked": True,
             "same_sign_source_kinds": row["same_sign_source_kinds"],
             "surface_atoms": [row["display"]], "source_aliases": [],
             "source_candidate_ids": [], "display_rules_applied": [],
             "merge_note": None, "merged_display_forms": [],
             "source_roles": [row["internal_role"]], "source_costs": [],
             "available_under_the_old_caps": False,
             "hidden_by_the_old_caps": False,
             "origin_kind": CLAUSE_NATIVE,
             "compiler_route": C53.FALLBACK_ROUTE,
             "from_clause": row["clause_name"],
             "round_trip": {"converted": [row["literal"]],
                            "status": "the displayed atom is the clause "
                                      "literal itself"}}
        ok, why = _fallback_writable(g)
        if not ok:
            alias_omitted.append({"printed": g["printed"],
                                  "reason": "the exact clause-native compiler "
                                            "cannot carry it: %s" % why})
            continue
        g["writability"] = {"premise": {"ok": True,
                                        "why": "compiled by the exact "
                                               "clause-native route"},
                            "conclusion": {"ok": True,
                                           "why": "compiled by the exact "
                                                  "clause-native route"}}
        native.append(g)

    added = checked_alias + native
    for g in added:
        g["section"] = (HELPER_SECTION if P51.is_structural(g["atom"])
                        else QUESTION_SECTION if g["question_linked"]
                        else CONTENT_SECTION)
    got["groups"] = got["groups"] + added
    got["omitted"] = [o for o in got["omitted"]
                      if not _now_displayed(o, added)] + alias_omitted
    sections = {}
    for name in SECTION_ORDER:
        mine = [g for g in got["groups"] if g["section"] == name]
        mine.sort(key=lambda g: (g["cost"], g["printed"]))
        for i, g in enumerate(mine, start=1):
            g["id"] = "%s%d" % (SECTION_PREFIX[name], i)
        sections[name] = mine
    got["sections"] = sections
    got["version"] = VERSION
    got["counts"].update({
        "displayed_groups": len(got["groups"]),
        "question_related": len(sections[QUESTION_SECTION]),
        "other_content": len(sections[CONTENT_SECTION]),
        "helper": len(sections[HELPER_SECTION]),
        "omitted_atoms": len(got["omitted"]),
        "groups_with_source_wording": sum(1 for g in got["groups"]
                                          if g["source_aliases"]),
        "alias_groups": len(checked_alias),
        "clause_native_groups": len(native),
    })
    return got


def _now_displayed(omission, added):
    lit = omission.get("compiled_literal")
    if not lit:
        return False
    key = _clause_key(lit)
    return any(_clause_key(g["literal"]) == key for g in added)


# ------------------------------------------------------------------ rendering

def render_group(group):
    lines = ["  %-4s %s" % (group["id"], group["printed"])]
    for alias in group.get("source_aliases") or []:
        lines.append("       SOURCE WORDING: %s"
                     % printed_atom(UA.display_atom(alias)))
    lines.append("       SUGGESTED ROLE: %s" % group["role"])
    lines.append("       COST: %d" % group["cost"])
    return "\n".join(lines)


def render_candidates(sections, annotations=None):
    """The three sections.  `annotations` adds a short mechanical note."""
    annotations = annotations or {}
    parts = []
    if any(g.get("source_aliases") for name in SECTION_ORDER
           for g in sections.get(name) or []):
        parts.append(ALIAS_NOTE)
    for name in SECTION_ORDER:
        mine = sections.get(name) or []
        if not mine:
            continue
        block = []
        for g in mine:
            text = render_group(g)
            note = annotations.get(g["id"])
            if note:
                text += "\n       %s" % note
            block.append(text)
        parts.append("%s\n\n%s" % (SECTION_HEADING[name], "\n\n".join(block)))
    return "\n\n".join(parts)


def vocabulary_rows(candidates):
    """One writable row per displayed atom AND per admitted source alias."""
    rows = []
    for g in candidates["groups"]:
        rows.append({"id": g["id"], "atom": g["atom"], "printed": g["printed"],
                     "internal_role": g["internal_role"], "cost": g["cost"],
                     "section": g["section"],
                     "same_sign_source_kinds": g["same_sign_source_kinds"]})
        for alias in g.get("source_aliases") or []:
            rows.append({"id": g["id"], "atom": UA.display_atom(alias),
                         "printed": printed_atom(UA.display_atom(alias)),
                         "internal_role": g["internal_role"], "cost": g["cost"],
                         "section": g["section"],
                         "same_sign_source_kinds": g["same_sign_source_kinds"]})
    return rows


# ---------------------------------------------------------- WP5: the messages
#
# The system prompt stays byte-identical for all three proposal calls, so its
# prefix remains cacheable.  Everything below is a versioned user-message block.

SUPPLIER_NOTE = "THE EXISTING CLAUSES MAY SUPPLY THIS"
TARGET_NOTE = "A RULE CONCLUDING THIS COULD REACH AN UNREACHED QUESTION ATOM"

NO_PROOF_RESULT = "GK found no proof using the first rules."

NO_PROOF_INSTRUCTIONS = """SECOND ATTEMPT: REPAIR OR COMPLETE THE CONNECTION

The first rules did not produce a proof. The mechanical report above says which
rule premises have a possible supplier and which question atoms remain
unreached. "Possible" does not mean proved.

Do not repeat a tried rule or a rule already in the passage.

First look for a tried rule whose body cannot start. Replace it with a rule
using premise atoms which the existing clauses may supply. Then look for a
short chain ending at one of the unreached question atoms.

Prefer one or two direct, well-supported connections over many cosmetic
variants. A new rule may have one to five premises. Every conclusion variable
must occur in a premise.

Do not assert a question atom merely because it is needed. Propose it only when
the passage or ordinary background knowledge licenses the implication.

Output only new RULE: lines."""

ALTERNATIVE_INSTRUCTIONS = """SECOND ATTEMPT: FIND A DIFFERENT BRIDGE ROUTE

GK found a proof using the rules under PROOF-USED RULES. Propose a genuinely
different route which could work without at least one of those rules.

Do not merely reverse a rule, rename variables, ground a general rule, remove a
necessary restriction, or repeat an unused rule. Look for a different
intermediate concept or representation connection supported by the passage or
ordinary background knowledge.

If no reasonable alternative exists, output no RULE: lines. Output only new
RULE: lines."""

PROOF_USED_HEADING = "PROOF-USED RULES"
UNUSED_HEADING = "TRIED BUT UNUSED RULES"
REFUSED_HEADING = "REFUSED RULES"


def supplier_annotations(candidates, feedback):
    """-> {group id: one short mechanical note}.

    Two marks only: an atom the existing clauses may supply, and an atom whose
    conclusion could reach a question literal no usable rule reached.  They are
    additions to the frozen ordering, never a reordering.
    """
    import unifier_feedback_v5_3 as FB
    out = {}
    suppliers = feedback.get("suppliers") or []
    unreached = [q for q in feedback.get("question_literals") or []
                 if q["id"] in set(x["id"] for x in
                                   feedback.get(
                                       "question_literals_not_reached") or [])]
    for g in candidates["groups"]:
        literal = g["literal"]
        marks = []
        for s in suppliers:
            if s["sign"] != UA.sign_of(literal):
                continue
            other = FB.standardise_apart(UA.unsigned_atom(s["literal"]), "a")
            if FB.unify(UA.unsigned_atom(literal), other, {}):
                marks.append(SUPPLIER_NOTE)
                break
        for q in unreached:
            if q["sign"] == UA.sign_of(literal):
                continue
            other = FB.standardise_apart(UA.unsigned_atom(q["literal"]), "b")
            if FB.unify(UA.unsigned_atom(literal), other, {}):
                marks.append(TARGET_NOTE)
                break
        if marks:
            out[g["id"]] = "; ".join(marks)
    return out


def render_tried(rules, statuses=None, refused=()):
    """The rules this case has already submitted, with their status."""
    lines = ["RULES ALREADY TRIED", ""]
    if not rules:
        lines.append("  (none)")
    for r in rules:
        lines.append("  %-4s %s" % (r["rule_id"], r.get("printed")))
        note = (statuses or {}).get(r["rule_id"])
        if note:
            lines.append("       %s" % note)
    if refused:
        lines += ["", "OF THOSE, THE PROGRAM COULD NOT USE:", ""]
        for r in refused:
            lines.append("  %-4s %s — %s" % (r.get("rule_id"),
                                             r.get("printed"), r.get("why")))
    return "\n".join(lines)


def render_proof_used(cited, unused, refused):
    """Cited, submitted-but-unused and refused, kept apart."""
    parts = []
    block = ["%s\n" % PROOF_USED_HEADING]
    for r in cited:
        block.append("  %-4s %s" % (r["rule_id"], r.get("printed")))
    if not cited:
        block.append("  (none)")
    parts.append("\n".join(block))
    block = ["%s\n" % UNUSED_HEADING]
    for r in unused:
        block.append("  %-4s %s" % (r["rule_id"], r.get("printed")))
    if not unused:
        block.append("  (none)")
    parts.append("\n".join(block))
    if refused:
        block = ["%s\n" % REFUSED_HEADING]
        for r in refused:
            block.append("  %-4s %s — %s" % (r.get("rule_id"),
                                             r.get("printed"), r.get("why")))
        parts.append("\n".join(block))
    return "\n\n".join(parts)


def _record(call, candidates, blocks, split, extra=None):
    text = "\n\n".join(b for b in blocks if b)
    P51._forbidden(text)
    P51._forbidden(system_prompt())
    got = {"call": call, "version": VERSION,
           "case_id": candidates.get("case_id"),
           "system_prompt_name": P51.SYSTEM_PROMPT_NAME,
           "system_prompt_sha256": system_prompt_sha256(),
           "text": text, "sha256": P51.sha256_of(text), "chars": len(text),
           "question_split": split, "counts": candidates["counts"],
           "size_guard": MAX_USER_MESSAGE_CHARS,
           "exceeds_size_guard": len(text) > MAX_USER_MESSAGE_CHARS}
    if got["exceeds_size_guard"]:
        got["why_refused"] = ("the user message is %d characters, over the "
                              "%d-character guard; the case is refused rather "
                              "than truncated" % (got["chars"],
                                                  MAX_USER_MESSAGE_CHARS))
    got.update(extra or {})
    return got


def build_initial_user_prompt(view, candidates):
    split = split_case_text(view)
    blocks = [render_case(split), render_candidates(candidates["sections"]),
              CLOSING_LINE]
    return _record("initial", candidates, blocks, split)


def build_no_proof_user_prompt(view, candidates, tried, refused, feedback):
    """The repair call: what could not start, and what was never reached."""
    import unifier_feedback_v5_3 as FB
    split = split_case_text(view)
    annotations = supplier_annotations(candidates, feedback)
    blocks = [render_case(split), NO_PROOF_RESULT,
              render_tried(tried, refused=refused), FB.render(feedback),
              render_candidates(candidates["sections"], annotations),
              NO_PROOF_INSTRUCTIONS]
    return _record("no_proof", candidates, blocks, split,
                   {"annotations": annotations,
                    "connection_report_version": feedback["version"]})


def build_alternative_user_prompt(view, candidates, cited, unused, refused,
                                  feedback=None):
    """The alternative call: which rules the proof actually used."""
    import unifier_feedback_v5_3 as FB
    split = split_case_text(view)
    blocks = [render_case(split), render_proof_used(cited, unused, refused)]
    annotations = {}
    if feedback is not None:
        annotations = supplier_annotations(candidates, feedback)
        unreached = feedback.get("question_literals_not_reached") or []
        if unreached:
            lines = ["QUESTION ATOMS A DIFFERENT ROUTE COULD REACH", ""]
            for q in unreached[:FB.MAX_SHOWN_UNREACHED]:
                lines.append("  %-4s %s" % (q["id"], q["printed"]))
            blocks.append("\n".join(lines))
    blocks.append(render_candidates(candidates["sections"], annotations))
    blocks.append(ALTERNATIVE_INSTRUCTIONS)
    return _record("alternative", candidates, blocks, split,
                   {"annotations": annotations,
                    "proof_used_rules": [r["rule_id"] for r in cited],
                    "tried_but_unused_rules": [r["rule_id"] for r in unused]})
