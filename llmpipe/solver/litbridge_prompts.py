"""What the model is asked: the system prompts and the case messages.

Three generation calls share one approved system prompt, byte for byte, so its
prefix stays cacheable: the initial call, the no-proof call and the
alternative call.  The case message is built here too — the passage, the
question, the MAIN and HELPER atom lists, and the instruction block — and it is
the same bytes for every model, so an experiment that varies the model varies
only the model.

The system prompt file itself is `prompts/dynamic_alignment/
unifier_rules_v6_1_signed_system.txt`, which is the v6 signed prompt with one
section added: the conclusion's polarity must match the English meaning.
`check_fixed_inputs` refuses to run if the file differs from v6 by more than
that section.
"""

import hashlib
import json
import os
import re

import litbridge_atoms as atoms
import litbridge_chain as chain
import litbridge_compile as compiler
import litbridge_rules as rules

# the prompt this one adds a section to; `check_fixed_inputs`
# refuses to run if the difference is anything else
BASE_SYSTEM_PROMPT_NAME = "unifier_rules_v6_signed_system"


# --------------------------------------------------------------- constants

VERSION = "litbridge_prompts/2026-08-15"

QUESTION_UNIT_TYPES = ("question", "query")

EXACT_SUFFIX = "exact_suffix_removed"

SEPARATE_FIELD = "separate_question_field"

UNRESOLVED = "unresolved"

_SENTENCE = re.compile(r"[^.?!]*[.?!]+(?=\s|$)|[^.?!]+$")

_WORD = re.compile(r"[a-z0-9]+")

RULE_ENTITY_MARKER = "entity_marker"

RULE_LETTER_CASE = "label_case_folding"

RULE_TRAILING_CONTEXT = "trailing_context_argument"

RULE_SIMPLEPROPS = "simpleprops_degree_collapse"

CONTEXT_HEADS = ("$ctxt",)

CONTEXT_CONSTANTS = ("$c",)

SYSTEM_PROMPT_SHA256 = \
    "e0f61739532beca29e262ca797553f56f5b062d2b85e078f58d2e090632ec9d5"

EXAMPLE_SHA256 = \
    "e2e6c36098a850a85d944cd398aaf5ed3e9917bcdd9f69d4b44682f76d4d45f2"

PREMISE = "PREMISE"

CONCLUSION = "CONCLUSION"

EITHER = "PREMISE OR CONCLUSION"

ROLE_WORD = {atoms.PREMISE: PREMISE, atoms.CONSEQUENCE: CONCLUSION,
             atoms.BOTH: EITHER}

QUESTION_SECTION = "question_related"

CONTENT_SECTION = "other_content"

SECTION_PREFIX = {QUESTION_SECTION: "Q", CONTENT_SECTION: "C",
                  atoms.HELPER_SECTION: "H"}

SECTION_ORDER = (QUESTION_SECTION, CONTENT_SECTION, atoms.HELPER_SECTION)

ALLOW_SIMPLEPROPS_COLLAPSE = True

PROBE_CLASS = "zz probe class"

PROBE_ATOM = ["isa", PROBE_CLASS, "?ZZPROBE"]

WHY_NO_POSITIVE_FORM = ("only the negated form of this atom was scored: its "
                        "positive form produced no content literal, or none "
                        "that occurs in any clause of either sign")

WHY_MULTI_OUTPUT = ("one surface atom compiles to %d different content "
                    "clauses, so the displayed line would not say what writing "
                    "it asserts")

WHY_NEGATIVE_LITERAL = ("the positive atom compiles to the negative literal "
                        "%s, so writing it would assert the opposite")

WHY_NO_OCCURRENCE = ("its converted literal occurs in no clause of either "
                     "sign, apart from population witnesses and generic frame "
                     "axioms")

WHY_ROUND_TRIP = ("the displayed form does not convert back to the literal it "
                  "stands for (it produced %s)")

WHY_NOT_WRITABLE = ("a bridge rule using it as a %s does not contain the "
                    "content literal %s (%s)")

MAIN_CAP = 400

SECONDARY_CAP = 200

MAX_USER_MESSAGE_CHARS = 60000

DISPLAYED = "displayed"

ALIAS = "converted_from_source_wording"

CLAUSE_NATIVE = "clause_native"

MAIN = "main"

HELPER = "helper"

MAIN_PREFIX, HELPER_PREFIX = "M", "H"

MAIN_PREFIX, HELPER_PREFIX = "M", "H"

INITIAL_INSTRUCTIONS = """Propose sound implication rules connecting the \
displayed atoms. Every rule
must contain at least one main atom. Helpers may be used only when they add a
necessary link or restriction. Prefer lower total cost among equally sound
rules. If there is no sound connection, write NO_RULE."""

SECOND_INSTRUCTIONS = """Propose only rules not already tried. Every rule must \
contain at least one
main atom. Helpers may be used only when they add a necessary link or
restriction. Prefer lower total cost among equally sound rules. If there is no
additional sound connection, write NO_RULE."""

NO_PROOF_NOTE = """The rules tried in the first call did not produce a proof. \
This does not show
that another sound rule exists. Propose a different rule only if it is
independently reasonable. Otherwise write NO_RULE."""

ALTERNATIVE_NOTE = """The first rules produced a proof. Look for a different \
independently sound
connection that could support an alternative proof. Do not weaken semantic
standards merely to produce a different answer. If there is no additional sound
rule, write NO_RULE."""

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")

SYSTEM_PROMPT_NAME = "unifier_rules_v6_1_signed_system"

POLARITY_HEADING = "POLARITY MUST MATCH"

FINAL_QUESTION = "final_question_sentence_removed"

ALLOWED_SPLITS = (EXACT_SUFFIX, FINAL_QUESTION)

SEPARATE_FIELD_MAX_OVERLAP = 0.5

WHY_REFUSED = {
    UNRESOLVED: "Stage 1 recorded no question or query unit, so the question "
                "cannot be separated from the passage",
    SEPARATE_FIELD: "the input does not end in a question and its wording "
                    "already carries the stored question, so showing that "
                    "question as a separate field would also state it as a "
                    "passage fact",
}

EXAMPLE_PATH = os.path.join(ROOT, "memos",
                            "EXAMPLE_2026_08_13_clear_literal_bridge_prompt.md")


# ---------------------------------------------- the approved system prompt

def system_prompt():
  with open(os.path.join(PROMPT_DIR, "%s.txt" % SYSTEM_PROMPT_NAME)) as f:
    return f.read()

def system_prompt_sha256():
  return hashlib.sha256(system_prompt().encode()).hexdigest()

def check_fixed_inputs():
  text = system_prompt()
  for want in ("MAIN ATOMS", "HELPER ATOMS", "MEANING:", "RULE:", "NO_RULE",
               POLARITY_HEADING,
               'RULE: ["isa","person","?X"] -> NOT ["isa","elephant","?X"]'):
    if want not in text:
      raise PromptError("the v6.1 system prompt lacks %r" % want)
  if not only_the_polarity_section_differs():
    raise PromptError("the v6.1 prompt differs from v6 by more than "
                          "the polarity section")
  return {"system_prompt_name": SYSTEM_PROMPT_NAME,
          "system_prompt_sha256": system_prompt_sha256(),
          "chars": len(text)}

def only_the_polarity_section_differs():
  """-> True when the prompt is v6's with exactly one section inserted."""
  mine, base = system_prompt(), base_system_prompt()
  if POLARITY_HEADING not in mine or POLARITY_HEADING in base:
    return False
  start = mine.index(POLARITY_HEADING)
  end = mine.index("OUTPUT\n\nFor each proposed rule")
  return mine[:start] + mine[end:] == base

class PromptError(Exception):
  """The prompt layer cannot proceed.  Never worked around."""


# ------------------------------------------------------ splitting the case

def split_case_text(view):
  """-> {status, passage, question, stored_question, evidence}."""
  text = (view.get("input_text") or "").strip()
  stored = stored_question(view).strip()
  sents = _sentences(text)
  last = sents[-1] if sents else ""
  evidence = {"final_sentence": last,
              "final_sentence_is_a_question": last.endswith("?"),
              "stored_question": stored,
              "containment": round(_containment(stored, last), 4)
              if stored else None,
              "containment_is_diagnostic_only": True,
              "sentences": len(sents)}
  if not stored:
    return {"status": UNRESOLVED, "passage": text, "question": "",
            "stored_question": "", "version": VERSION,
            "evidence": dict(evidence,
                             why="Stage 1 recorded no question or query "
                                 "unit")}
  if text.endswith(stored):
    return {"status": EXACT_SUFFIX,
            "passage": text[:len(text) - len(stored)].strip(),
            "question": stored, "stored_question": stored,
            "version": VERSION,
            "evidence": dict(evidence,
                             why="the stored question is a literal suffix "
                                 "of the input text")}
  if last.endswith("?"):
    return {"status": FINAL_QUESTION,
            "passage": text[:len(text) - len(last)].strip(),
            "question": last, "stored_question": stored,
            "version": VERSION,
            "evidence": dict(evidence,
                             why="Stage 1 stored a question and the input's "
                                 "final sentence is itself a question, so "
                                 "that sentence is the question and is "
                                 "shown as the passage wrote it")}
  return {"status": SEPARATE_FIELD, "passage": text, "question": stored,
          "stored_question": stored, "version": VERSION,
          "evidence": dict(evidence,
                           why="the input does not end in a question, so "
                               "nothing was removed and Stage 1's question "
                               "is shown on its own")}

def question_preflight(view):
  """-> one row.  May this case be sent at all?

  Fails closed: a case whose question cannot be separated is refused for
  review rather than shown with its question standing in the passage.
  """
  split = split_case_text(view)
  status = split["status"]
  allowed = status in ALLOWED_SPLITS
  why = None
  overlap = None
  if not allowed:
    why = WHY_REFUSED.get(status, "unknown split status")
    if status == SEPARATE_FIELD:
      words = _words(split["question"])
      carried = set(_words(split["passage"]))
      overlap = (sum(1 for w in words if w in carried) / float(len(words))
                 if words else 1.0)
      if overlap < SEPARATE_FIELD_MAX_OVERLAP:
        allowed, why = True, None
  return {"case_id": view.get("case_id"), "status": status,
          "llm_call_allowed": allowed, "why_refused": why,
          "question": split["question"],
          "passage_overlap_with_the_question": overlap,
          "version": VERSION, "evidence": split["evidence"]}

def render_case(split):
  return "\n".join(["CASE", "", "PASSAGE:", split["passage"], "",
                    "QUESTION:", split["question"]])


# ------------------------------- the candidate inventory the message shows

def complete_inventory(view, configuration):
  """The v4 candidate inventory with limits no case reaches."""
  return atoms.build(view, configuration, main_cap=MAIN_CAP,
                   secondary_cap=SECONDARY_CAP)

def build_candidates(view, configuration, complete=None, old=None):
  """The v5.2 candidate record, plus alias and clause-native groups."""
  got = _candidates_over_the_complete_inventory(view, configuration, complete, old)
  inventory = atoms.inventory(view)
  occurrences = inventory["occurrences"]
  pool = atoms.role_occurrences(occurrences)
  for g in got["groups"]:
    g["source_aliases"] = []
    g["origin_kind"] = DISPLAYED
    g["compiler_route"] = compiler.NORMAL_ROUTE
  covered = set(_clause_key(g["literal"]) for g in got["groups"])

  # WP2: atoms whose conversion renames the predicate family
  kept_alias, alias_omitted = [], []
  for row in _alias_rows(view, configuration, got["omitted"], occurrences,
                         pool):
    key = _clause_key(row["literal"])
    display = row["display"]
    same, opposite, _pop = atoms.match_occurrences(row["literal"],
                                                 occurrences)
    role = atoms.role_of(same, opposite)
    if role is None:
      alias_omitted.append({"printed": atoms.printed_atom(display),
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
        "atom": display, "printed": atoms.printed_atom(display),
        "literal": row["literal"],
        "role": ROLE_WORD[role], "internal_role": role,
        "cost": atoms.opposite_sign_unifiers(row["literal"], pool),
        "question_linked": any(o["source_kind"] == atoms.QUESTION
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
        "origin_kind": ALIAS, "compiler_route": compiler.NORMAL_ROUTE,
        "round_trip": {"converted": [row["literal"]],
                       "status": "the displayed atom is the compiled "
                                 "literal itself"},
    })

  # the alias must survive the same round trip and both probe positions
  checked_alias = []
  if kept_alias:
    tries = [(g["atom"], "+") for g in kept_alias]
    errors = []
    converted = atoms.convert_batch(view, tries, configuration,
                                  errors=errors)
    for i, g in enumerate(kept_alias, start=1):
      status, lits = atoms.conversion_of(converted.get("Cv%d" % i) or [])
      n = len(g["atom"]) - 1
      if len(lits) != 1 or not _same_content(lits[0], g["literal"],
                                                 n):
        alias_omitted.append({"printed": g["printed"],
                              "reason": "the displayed form does not "
                                        "convert back to the literal "
                                        "it stands for (%s)"
                                        % json.dumps(lits)[:120]})
        continue
      w = writability(g["atom"], g["literal"], view, configuration)
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
    g = {"atom": row["display"], "printed": atoms.printed_atom(row["display"]),
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
         "compiler_route": compiler.CLAUSE_NATIVE_ROUTE,
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
    g["section"] = (atoms.HELPER_SECTION if is_structural(g["atom"])
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
      "helper": len(sections[atoms.HELPER_SECTION]),
      "omitted_atoms": len(got["omitted"]),
      "groups_with_source_wording": sum(1 for g in got["groups"]
                                        if g["source_aliases"]),
      "alias_groups": len(checked_alias),
      "clause_native_groups": len(native),
  })
  return got

def relabel(candidates):
  """Merge the two content sections into MAIN and renumber M1.. / H1.. .

  The relative order inside each former section is the v5.4 order, and the
  former question-related atoms keep their place at the front: only the
  heading and the id prefix change, so a comparison with AL-92 stays about
  the message, not about which atoms were offered.
  """
  main, helper = [], []
  for name in (QUESTION_SECTION, CONTENT_SECTION):
    main.extend(candidates["sections"].get(name) or [])
  helper.extend(candidates["sections"].get(atoms.HELPER_SECTION) or [])
  seen = {}
  ordered = []
  for g in main:                     # collapse only duplicates the builder
    key = g["printed"]             # already treated as one candidate
    if key in seen:
      continue
    seen[key] = True
    ordered.append(g)
  for i, g in enumerate(ordered, start=1):
    g["v5_4_id"] = g.get("v5_4_id", g["id"])
    g["id"] = "%s%d" % (MAIN_PREFIX, i)
    g["list"] = MAIN
  for i, g in enumerate(helper, start=1):
    g["v5_4_id"] = g.get("v5_4_id", g["id"])
    g["id"] = "%s%d" % (HELPER_PREFIX, i)
    g["list"] = HELPER
  candidates["lists"] = {MAIN: ordered, HELPER: helper}
  candidates["main_ids"] = set(g["id"] for g in ordered)
  candidates["helper_ids"] = set(g["id"] for g in helper)
  return candidates

def vocabulary_rows(candidates):
  """One writable row per displayed atom AND per admitted source alias."""
  rows = []
  for g in candidates["groups"]:
    rows.append({"id": g["id"], "atom": g["atom"], "printed": g["printed"],
                 "internal_role": g["internal_role"], "cost": g["cost"],
                 "section": g["section"],
                 "same_sign_source_kinds": g["same_sign_source_kinds"]})
    for alias in g.get("source_aliases") or []:
      rows.append({"id": g["id"], "atom": atoms.display_atom(alias),
                   "printed": atoms.printed_atom(atoms.display_atom(alias)),
                   "internal_role": g["internal_role"], "cost": g["cost"],
                   "section": g["section"],
                   "same_sign_source_kinds": g["same_sign_source_kinds"]})
  return rows

def render_lists(candidates):
  parts = []
  for name, heading in ((MAIN, "MAIN ATOMS:"), (HELPER, "HELPER ATOMS:")):
    mine = (candidates.get("lists") or {}).get(name) or []
    if not mine:
      continue
    parts.append("%s\n\n%s" % (heading,
                               "\n\n".join(render_group(g)
                                           for g in mine)))
  return "\n\n".join(parts)

def render_group(group):
  return "\n".join(["  %-4s %s" % (group["id"], group["printed"]),
                    "       SUGGESTED ROLE: %s" % group["role"],
                    "       COST: %d" % group["cost"]])


# ------------------------------------------------------ the three messages

def build_initial_user_prompt(view, candidates):
  return _restamp(_initial_message(view, candidates))

def build_no_proof_user_prompt(view, candidates, tried):
  return _restamp(_no_proof_message(view, candidates, tried))

def build_alternative_user_prompt(view, candidates, cited, unused):
  return _restamp(_alternative_message(view, candidates, cited,
                                                    unused))

def _record(call, candidates, blocks, split, extra=None):
  text = "\n\n".join(b for b in blocks if b)
  _forbidden(text)
  got = {"call": call, "version": VERSION,
         "case_id": candidates.get("case_id"),
         "system_prompt_name": SYSTEM_PROMPT_NAME,
         "system_prompt_sha256": system_prompt_sha256(),
         "text": text, "sha256": sha256_of(text), "chars": len(text),
         "question_split": split, "counts": candidates["counts"],
         "main_atoms": len((candidates.get("lists") or {}).get(MAIN) or []),
         "helper_atoms": len((candidates.get("lists")
                              or {}).get(HELPER) or []),
         "size_guard": MAX_USER_MESSAGE_CHARS,
         "exceeds_size_guard": len(text) > MAX_USER_MESSAGE_CHARS}
  if got["exceeds_size_guard"]:
    got["why_refused"] = ("the user message is %d characters, over the "
                          "%d-character guard; the case is refused rather "
                          "than truncated" % (got["chars"],
                                              MAX_USER_MESSAGE_CHARS))
  got.update(extra or {})
  return got

def _restamp(got):
  got["version"] = VERSION
  got["user_message_builder"] = VERSION
  got["system_prompt_name"] = SYSTEM_PROMPT_NAME
  got["system_prompt_sha256"] = system_prompt_sha256()
  return got


# -------------------------------------------------- what each message says

def render_tried(rules):
  lines = ["RULES ALREADY TRIED:", ""]
  if not rules:
    lines.append("  (none)")
  for r in rules:
    lines.append("  %s" % r.get("printed"))
  return "\n".join(lines)

def render_proof_used(cited, unused):
  parts = ["RULES USED IN THE PROOF:", ""]
  for r in cited:
    parts.append("  %s" % r.get("printed"))
  if not cited:
    parts.append("  (none)")
  parts += ["", "RULES TRIED BUT NOT USED:", ""]
  for r in unused:
    parts.append("  %s" % r.get("printed"))
  if not unused:
    parts.append("  (none)")
  return "\n".join(parts)


# ---------------------------------------------------------------- the rest

def sha256_of(text):
  return hashlib.sha256((text or "").encode()).hexdigest()

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

def _is_context_argument(term):
  if isinstance(term, str):
    return atoms.is_variable_term(term) or term in CONTEXT_CONSTANTS
  if isinstance(term, list) and term and str(term[0]) in CONTEXT_HEADS:
    return True
  return False

def _looks_generated(head):
  h = str(head)
  return bool(re.match(r"^sk[a-z0-9_]*$", h)) or h.startswith("$")

def _norm(term):
  return atoms._norm_constant(term) if isinstance(term, str) else term

def _compare_arguments(surface_args, clause_args):
  """-> (reasons, rules).  Positionwise, up to a bijective variable renaming."""
  reasons, applied = [], []
  left, right = {}, {}

  def go(a, b, path):
    if isinstance(a, str) and atoms.is_variable_term(a):
      if not (isinstance(b, str) and atoms.is_variable_term(b)):
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
      if atoms.is_variable_term(b):
        reasons.append("argument %s: the constant %s became a variable"
                       % (path, json.dumps(a)))
        return
      if a == b:
        return
      if _norm(a) == _norm(b):
        if a.replace("#:", "") != b.replace("#:", ""):
          applied.append(RULE_LETTER_CASE)
        if ("#:" in a) != ("#:" in b):
          applied.append(RULE_ENTITY_MARKER)
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
  return reasons, applied

def _same_multiset(a, b):
  return sorted(json.dumps(_norm(x), sort_keys=True) for x in a) == \
      sorted(json.dumps(_norm(x), sort_keys=True) for x in b)

def is_structural(atom):
  """A bare event-role or unlabelled frame atom: a connector, not a concept.

  `atoms.ROLE_PREDS` is the pipeline's own list of event-role predicates.  An
  atom is structural only when it also carries NO content: every argument is a
  variable, or a generated term over variables such as `$ev_of(?X,?Y,?Z)`.
  `have(?X,?Y)` and `typical(?X)` are therefore not structural, which is what
  the audit asks for.
  """
  pred = str(atom[0])
  args = list(atom[1:])
  if pred in atoms.ROLE_PREDS:
    return all(atoms._all_variable_term(a) for a in args)
  slot = atoms.LABEL_SLOT.get(pred)
  if slot is not None and slot < len(args) \
          and isinstance(args[slot], str) and atoms.is_variable_term(args[slot]):
    return all(atoms._all_variable_term(a) for a in args)
  return False

def example_sha256():
  with open(EXAMPLE_PATH) as f:
    return hashlib.sha256(f.read().encode()).hexdigest()

def _content_part(literal, n):
  """The predicate and the first `n` arguments: what the passage supplied.

  Conversion appends context arguments on the right (docs/encodings/gk-clauses.md), and a
  rule generalises them where an isolated fact conversion leaves them
  concrete.  Only the content part is compared.
  """
  atom = atoms.unsigned_atom(literal)
  return [atom[0]] + list(atom[1:1 + n])

def _same_content(a, b, n):
  return atoms.alpha_key(_content_part(a, n)) == atoms.alpha_key(_content_part(b, n))

def simpleprops_display(surface, converted_predicate):
  """The canonical collapsed atom, at DEGREE "none" only, or None."""
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

def display_check(display_atom, literal):
  """May this atom be displayed as the syntax the model should copy?

  -> {safe, reasons, rules_applied}.  `safe` is False unless every difference
  between the displayed atom and the clause literal it compiles to is
  explained by a rule in `DOCUMENTED_RULES`.
  """
  reasons, applied = [], []
  if atoms.sign_of(literal) != "+":
    return {"safe": False,
            "reasons": [WHY_NEGATIVE_LITERAL % json.dumps(literal)],
            "rules_applied": []}
  atom = atoms.unsigned_atom(literal)
  if str(display_atom[0]) != str(atom[0]):
    return {"safe": False,
            "reasons": ["predicate: `%s` compiles to `%s`"
                        % (display_atom[0], atom[0])],
            "rules_applied": []}
  shown, clause = list(display_atom[1:]), list(atom[1:])
  if len(clause) < len(shown):
    reasons.append("conversion dropped %d argument(s)"
                   % (len(shown) - len(clause)))
  else:
    extra = clause[len(shown):]
    if extra:
      if all(_is_context_argument(t) for t in extra):
        applied.append(RULE_TRAILING_CONTEXT)
      else:
        reasons.append("conversion added the argument(s) %s, which are "
                       "not context slots"
                       % "; ".join(json.dumps(t) for t in extra))
    got, used = _compare_arguments(shown, clause[:len(shown)])
    if got:
      slot = atoms.LABEL_SLOT.get(str(display_atom[0]))
      if slot is not None and slot < len(shown) and slot < len(clause) \
              and _norm(shown[slot]) != _norm(clause[slot]):
        got = ["content label: `%s` compiles to `%s`"
               % (shown[slot], clause[slot])] + got
      elif _same_multiset(shown, clause[:len(shown)]):
        got = ["argument order: the same arguments appear in a "
               "different order"] + got
      reasons.extend(got)
    applied.extend(used)
  ordered, seen = [], set()
  for r in applied:
    if r not in seen:
      seen.add(r)
      ordered.append(r)
  return {"safe": not reasons, "reasons": reasons, "rules_applied": ordered}

def probe_rule(atom, position):
  """A harmless one-premise rule that puts `atom` in the asked position."""
  other = PROBE_ATOM
  if position == PREMISE:
    parsed = {"body": [("+", atom)], "head": ("+", other)}
  else:
    parsed = {"body": [("+", other)], "head": ("+", atom)}
  rule = rules.to_stage2_variables(parsed)
  rule.update({"rule_id": "PROBE", "canonical": "probe",
               "printed": "writability probe"})
  return rule

def _rule_literals(clauses):
  out = []
  for c in clauses or []:
    if c.get("@sourcetype") == "populate":
      continue
    for lit in atoms.literals_of(c.get("@logic")):
      if isinstance(lit, list) and lit and isinstance(lit[0], str) \
              and not atoms.is_control_predicate(lit[0]):
        out.append(lit)
  return out

def writability(atom, literal, view, configuration):
  """-> {writable, premise, conclusion}.  One real compilation per position.

  A rule literal must actually carry the atom's content: as a premise it must
  appear negated, as a conclusion positive.  `has time` fails both, which is
  why no wording could make it safe to display.
  """
  n = len(atom) - 1
  out = {}
  for position, want_sign in ((PREMISE, "-"), (CONCLUSION, "+")):
    rule = probe_rule(atom, position)
    try:
      clauses, _rec = compiler.compile_by_the_converter(rule, view, configuration,
                                     case_id=view.get("case_id"),
                                     world_name="writability_probe")
    except Exception as e:                                  # noqa: BLE001
      out[position] = {"ok": False,
                       "why": "the converter raised %s: %s"
                              % (type(e).__name__, str(e)[:120]),
                       "literals": []}
      continue
    lits = _rule_literals(clauses)
    found = [l for l in lits
             if atoms.sign_of(l) == want_sign and len(l) - 1 >= n
             and _same_content(l, literal, n)]
    out[position] = {"ok": bool(found),
                     "why": None if found else
                     "the compiled clause is %s" % json.dumps(lits)[:160],
                     "literals": lits}
  return {"writable": out[PREMISE]["ok"] and out[CONCLUSION]["ok"],
          "premise": out[PREMISE], "conclusion": out[CONCLUSION]}

def _positive_rows(rows):
  """Every v4 row whose stored conversion is the conversion of the POSITIVE
  atom, keyed by surface atom.

  `build_main` converts each Stage-2 atom in both signs and keeps a row per
  output; only the `+` rows are conversions of the positive atom.
  `build_secondary` always converts the positive surface guess and negates the
  result afterwards, so all of its rows qualify and their positive literal is
  the variant the row points at.
  """
  positive, negative_only = {}, {}
  for row in rows:
    key = atoms.alpha_key(row["surface_atom"])
    if row.get("origin") == "stage2" and row["sign"] != "+":
      negative_only.setdefault(key, []).append(row)
      continue
    lits = row.get("all_converted_literals") or []
    index = row.get("converted_variant_index") or 0
    if index >= len(lits):
      continue
    positive.setdefault(key, {"surface_atom": row["surface_atom"],
                              "literal": lits[index],
                              "variant_count": len(lits),
                              "rows": []})["rows"].append(row)
  for key in list(negative_only):
    if key in positive:
      del negative_only[key]
  return positive, negative_only

def _omission(entry, reason, extra=None):
  out = {"surface_atom": entry["surface_atom"],
         "printed": atoms.printed_atom(atoms.display_atom(entry["surface_atom"])),
         "source_candidate_ids": [r.get("id") for r in entry["rows"]],
         "compiled_literal": entry.get("literal"),
         "all_compiled_literals":
             (entry["rows"][0].get("all_converted_literals")
              if entry["rows"] else None),
         "reason": reason}
  out.update(extra or {})
  return out

# a prompt that carries any of these would be showing the model the answer,
# the label or the result it is supposed to produce
LEAK_TOKENS = ("expected_answer", "accepted_llmpipe_answers", "$ans",
               "gold_replacement_packages", "critic_verdict", "label_id",
               "benchmark", "proof found", "answer found",
               "reviewed", "accepted answer", "expected answer", "gold")
LEAK_ANSWER_WORDS = ("true.", "false.", "unknown.", "probably true.",
                     "probably false.", "possibly true.", "possibly false.")


def assert_no_leak(text):
  """Raise if a built prompt carries an answer, a label or a proof result."""
  low = (text or "").lower()
  bad = [t for t in LEAK_TOKENS if t.lower() in low]
  for w in LEAK_ANSWER_WORDS:
    # an answer word only leaks when it stands alone as a value, which is
    # how the stored records write it
    if ('"%s"' % w) in low or ("answer: %s" % w) in low:
      bad.append(w)
  if bad:
    raise PromptError("prompt would leak: %s" % sorted(set(bad)))
  return True


def _forbidden(text):
  """Nothing from the scored side of the experiment may reach a prompt."""
  assert_no_leak(text)
  banned = ("MAIN CANDIDATES", "SECONDARY CANDIDATES", "USE: PREMISE",
            "USE: CONSEQUENCE", "PRIORITY COST", "GK FORM", "same as before",
            "FOCUS", "POSITIVE:", "NEGATED:", "LEFT", "RIGHT", "EITHER",
            PROBE_CLASS)
  bad = [b for b in banned if b in text]
  if bad:
    raise PromptError("prompt carries retired or internal wording: %s"
                      % bad)
  return True

def _candidate_sections(view, configuration, v4_candidates):
  """-> the three sections, the omissions and the diagnostics.

  Nothing here reads an answer, a grade or a proof: the inputs are the stored
  parse, the clauses gk received and the v4 candidate inventory.
  """
  check_fixed_inputs()
  occurrences = v4_candidates["occurrences"]
  pool = atoms.role_occurrences(occurrences)
  rows = list(v4_candidates.get("main") or []) + \
      list(v4_candidates.get("secondary") or [])
  positive, negative_only = _positive_rows(rows)

  omitted = []
  for key, rs in sorted(negative_only.items()):
    omitted.append(_omission({"surface_atom": rs[0]["surface_atom"],
                              "rows": rs, "literal": None},
                             WHY_NO_POSITIVE_FORM))

  kept = []
  for key in sorted(positive):
    entry = positive[key]
    literal = entry["literal"]
    if entry["variant_count"] > 1:
      omitted.append(_omission(entry, WHY_MULTI_OUTPUT
                               % entry["variant_count"]))
      continue
    if atoms.sign_of(literal) == "-":
      omitted.append(_omission(entry, WHY_NEGATIVE_LITERAL
                               % json.dumps(literal)))
      continue
    surface = entry["surface_atom"]
    collapsed = simpleprops_display(surface, str(atoms.unsigned_atom(
        literal)[0]))
    display = atoms.display_atom(collapsed if collapsed is not None
                              else surface)
    check = display_check(display, literal)
    if not check["safe"]:
      omitted.append(_omission(entry, check["reasons"][0],
                               {"reasons": check["reasons"],
                                "displayed_as": display}))
      continue
    same, opposite, _population = atoms.match_occurrences(literal,
                                                        occurrences)
    role = atoms.role_of(same, opposite)
    if role is None:
      omitted.append(_omission(entry, WHY_NO_OCCURRENCE))
      continue
    applied = list(check["rules_applied"])
    if collapsed is not None:
      applied.append(RULE_SIMPLEPROPS)
    kept.append({
        "display": display,
        "surface_atom": surface,
        "literal": literal,
        "role": ROLE_WORD[role],
        "internal_role": role,
        "cost": atoms.opposite_sign_unifiers(literal, pool),
        "question_linked": any(o["source_kind"] == atoms.QUESTION
                               for o in same + opposite),
        "same_sign_source_kinds": sorted(set(o["source_kind"]
                                             for o in same)),
        "rows": entry["rows"],
        "display_rules_applied": sorted(set(applied)),
    })

  # WP2.4: rows that compile to one literal are one line.
  buckets = {}
  for k in kept:
    buckets.setdefault(atoms.alpha_key(k["literal"]), []).append(k)
  groups = []
  for key in sorted(buckets):
    mine = buckets[key]
    shapes = sorted(set(json.dumps(k["display"], ensure_ascii=False)
                        for k in mine))
    chosen = sorted(mine, key=lambda k: (len(k["display"]),
                                         json.dumps(k["display"],
                                                    ensure_ascii=False)))[0]
    groups.append({
        "atom": chosen["display"],
        "printed": atoms.printed_atom(chosen["display"]),
        "literal": chosen["literal"],
        "role": chosen["role"],
        "internal_role": chosen["internal_role"],
        "cost": chosen["cost"],
        "question_linked": any(k["question_linked"] for k in mine),
        "surface_atoms": [k["surface_atom"] for k in mine],
        "source_candidate_ids": [r.get("id") for k in mine
                                 for r in k["rows"]],
        "source_roles": sorted(set(k["internal_role"] for k in mine)),
        "same_sign_source_kinds": sorted(set(
            x for k in mine for x in k["same_sign_source_kinds"])),
        "source_costs": sorted(set(k["cost"] for k in mine)),
        "display_rules_applied": sorted(set(r for k in mine
                                            for r in
                                            k["display_rules_applied"])),
        "merged_display_forms": shapes if len(shapes) > 1 else [],
        "merge_note": ("%d surface rows compile to this one literal: %s"
                       % (len(mine),
                          "; ".join(atoms.print_atom(atoms.display_atom(
                              k["surface_atom"])) for k in mine))
                       if len(mine) > 1 else None),
    })

  # WP2.5 and WP2.1-2.2: the displayed form must convert back, and a real
  # bridge rule must be able to carry it.
  tries = [(g["atom"], "+") for g in groups]
  errors = []
  converted = atoms.convert_batch(view, tries, configuration,
                                errors=errors) if tries else {}
  checked = []
  for i, g in enumerate(groups, start=1):
    status, lits = atoms.conversion_of(converted.get("Cv%d" % i) or [])
    n = len(g["atom"]) - 1
    back = [l for l in lits if _same_content(l, g["literal"], n)
            and atoms.sign_of(l) == "+"]
    if len(lits) != 1 or not back:
      omitted.append({"surface_atom": g["surface_atoms"][0],
                      "printed": g["printed"],
                      "source_candidate_ids": g["source_candidate_ids"],
                      "compiled_literal": g["literal"],
                      "all_compiled_literals": lits,
                      "reason": WHY_ROUND_TRIP
                      % json.dumps(lits, ensure_ascii=False)[:160]})
      continue
    g["round_trip"] = {"converted": lits, "status": status}
    got = writability(g["atom"], g["literal"], view, configuration)
    if not got["writable"]:
      side = PREMISE if not got["premise"]["ok"] else CONCLUSION
      omitted.append({"surface_atom": g["surface_atoms"][0],
                      "printed": g["printed"],
                      "source_candidate_ids": g["source_candidate_ids"],
                      "compiled_literal": g["literal"],
                      "all_compiled_literals": lits,
                      "reason": WHY_NOT_WRITABLE
                      % (side.lower(),
                         json.dumps(g["literal"], ensure_ascii=False),
                         got[side.lower().replace(" ", "_")]["why"]),
                      "writability": {k: {"ok": v["ok"], "why": v["why"]}
                                      for k, v in got.items()
                                      if isinstance(v, dict)}})
      continue
    g["writability"] = {k: {"ok": v["ok"], "why": v["why"]}
                        for k, v in got.items() if isinstance(v, dict)}
    checked.append(g)

  for g in checked:
    g["section"] = (atoms.HELPER_SECTION if is_structural(g["atom"])
                    else QUESTION_SECTION if g["question_linked"]
                    else CONTENT_SECTION)
  sections = {}
  for name in SECTION_ORDER:
    mine = [g for g in checked if g["section"] == name]
    mine.sort(key=lambda g: (g["cost"], g["printed"]))
    for i, g in enumerate(mine, start=1):
      g["id"] = "%s%d" % (SECTION_PREFIX[name], i)
    sections[name] = mine

  return {
      "version": VERSION,
      "case_id": view.get("case_id"),
      "sections": sections,
      "groups": checked,
      "omitted": omitted,
      "conversion_errors": errors,
      "counts": {
          "source_candidate_rows": len(rows),
          "distinct_positive_surface_atoms": len(positive),
          "negative_variants_removed": sum(1 for r in rows
                                           if r["sign"] == "-"),
          "displayed_groups": len(checked),
          "question_related": len(sections[QUESTION_SECTION]),
          "other_content": len(sections[CONTENT_SECTION]),
          "helper": len(sections[atoms.HELPER_SECTION]),
          "omitted_atoms": len(omitted),
      },
  }

def _surface_keys(candidates):
  return set(atoms.alpha_key(r["surface_atom"])
             for r in (candidates.get("main") or [])
             + (candidates.get("secondary") or []))

def _candidates_over_the_complete_inventory(view, configuration, complete=None, old=None):
  """-> the v5.1 candidate record, over the complete inventory, annotated.

  `available_under_the_old_caps` is measured, not inferred: the same builder
  is run again with the v4 caps and the surface atoms are compared.
  """
  complete = complete if complete is not None else complete_inventory(
      view, configuration)
  old = old if old is not None else atoms.build(view, configuration)
  got = _candidate_sections(view, configuration, complete)
  old_keys = _surface_keys(old)
  for g in got["groups"]:
    seen = [atoms.alpha_key(a) for a in g["surface_atoms"]]
    g["available_under_the_old_caps"] = any(k in old_keys for k in seen)
    g["hidden_by_the_old_caps"] = not g["available_under_the_old_caps"]
  hidden = [g["id"] for g in got["groups"] if g["hidden_by_the_old_caps"]]
  got["version"] = VERSION
  got["inventory"] = {
      "complete_main_rows": len(complete.get("main") or []),
      "complete_secondary_rows": len(complete.get("secondary") or []),
      "old_cap_main_rows": len(old.get("main") or []),
      "old_cap_secondary_rows": len(old.get("secondary") or []),
      "limits_used": {"main_cap": MAIN_CAP, "secondary_cap": SECONDARY_CAP},
      "old_limits": {"main_cap": atoms.MAIN_CAP,
                     "secondary_cap": atoms.SECONDARY_CAP},
      "reached_a_limit": (len(complete.get("main") or []) >= MAIN_CAP
                          or len(complete.get("secondary") or [])
                          >= SECONDARY_CAP),
  }
  got["counts"]["displayed_groups_hidden_by_the_old_caps"] = len(hidden)
  got["groups_hidden_by_the_old_caps"] = hidden
  return got

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
      if atoms.is_clause_variable(t):
        names.setdefault(t, "_v%d" % len(names))
        return names[t]
      return t
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  atom = atoms.unsigned_atom(literal)
  return json.dumps([atom[0]] + [go(a) for a in atom[1:]])

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
    if not literal or len(lits) > 1 or atoms.sign_of(literal) == "-":
      continue
    display = atoms._display_from_literal(literal)
    if display is None:
      continue
    wanted.append({"display": display, "literal": literal,
                   "surface": o["surface_atom"],
                   "source_candidate_ids": o.get("source_candidate_ids")
                   or []})
  return wanted

def _clause_native_rows(view, occurrences, covered, pool):
  """-> rows for question-clause content literals nothing displays.

  Only question clauses: a literal the question asks about that the model
  cannot write is exactly the gap `folio-0089` exposes.  Source-clause
  literals the converter cannot round-trip stay out of the display.
  """
  out, seen = [], set()
  for o in occurrences:
    if o["source_kind"] != atoms.QUESTION or o["is_control"] \
            or o["is_equality"]:
      continue
    literal = o["clause_literal"]
    atom = atoms.unsigned_atom(literal)
    if atoms._is_generic(atom):
      continue
    key = _clause_key(atom)
    if key in covered or key in seen:
      continue
    display = atoms._display_from_literal(literal)
    if display is None or atoms.is_control_predicate(atom[0]):
      continue
    seen.add(key)
    positive = atom if atoms.sign_of(literal) == "+" else atom
    same, opposite, _pop = atoms.match_occurrences(positive, occurrences)
    role = atoms.role_of(same, opposite)
    if role is None:
      continue
    out.append({"display": display, "literal": positive,
                "clause_name": o["clause_name"],
                "literal_id": o["literal_id"],
                "role": ROLE_WORD[role],
                "internal_role": role,
                "cost": atoms.opposite_sign_unifiers(positive, pool),
                "question_linked": True,
                "same_sign_source_kinds": sorted(set(x["source_kind"]
                                                     for x in same))})
  return out

def _probe_rule(atom):
  return {"rule_id": "PROBE", "canonical": "probe", "printed": "probe",
          "llm_variables": [v for v in _display_vars(atom)],
          "body": [{"sign": "+", "atom": atom}],
          "head": {"sign": "+", "atom": atom}}

def _display_vars(atom):
  out = []
  for t in rules._tokens(atom):
    if isinstance(t, str) and t.startswith("?") and t not in out:
      out.append(t)
  return out

def _fallback_writable(group):
  """Can the exact clause-native compiler carry this atom at all?"""
  rule = _probe_rule(group["atom"])
  try:
    compiler._clause_native_with_positive_blocker(rule, [group], "probe::PROBE")
  except Exception as e:                                      # noqa: BLE001
    return False, str(e)[:160]
  return True, None

def _now_displayed(omission, added):
  lit = omission.get("compiled_literal")
  if not lit:
    return False
  key = _clause_key(lit)
  return any(_clause_key(g["literal"]) == key for g in added)

def _initial_message(view, candidates):
  split = split_case_text(view)
  blocks = [render_case(split), render_lists(candidates),
            INITIAL_INSTRUCTIONS]
  return _record("initial", candidates, blocks, split)

def _no_proof_message(view, candidates, tried):
  split = split_case_text(view)
  blocks = [render_case(split), NO_PROOF_NOTE, render_tried(tried),
            render_lists(candidates), SECOND_INSTRUCTIONS]
  return _record("no_proof", candidates, blocks, split)

def _alternative_message(view, candidates, cited, unused):
  split = split_case_text(view)
  blocks = [render_case(split), ALTERNATIVE_NOTE,
            render_proof_used(cited, unused), render_lists(candidates),
            SECOND_INSTRUCTIONS]
  return _record("alternative", candidates, blocks, split)

def base_system_prompt():
  with open(os.path.join(PROMPT_DIR,
                         "%s.txt" % BASE_SYSTEM_PROMPT_NAME)) as f:
    return f.read()

