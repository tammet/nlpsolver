"""The rule grammar, and the two channels that build rules in code.

A bridge rule is written by the model in a two-line block:

    MEANING: If something is a bee, then it is normally not a vertebrate.
    RULE: ["isa","bee","?X"] -> NOT ["isa","vertebrate","?X"]

This module owns everything about that rule: reading the line, checking it
against the displayed vocabulary, its canonical form, its printed form, its
ground specializations, and which displayed candidate each atom came from.
Every refusal is named, and the English meaning never repairs a formula.

It also owns the two channels where CODE builds the rule and the model only
selects: distinctness (two named things are not the same) and the
negative-relation channel (`A -> NOT B`).  They belong here because they are
ways a rule comes into existence and is checked.
"""

import copy
import hashlib
import json
import os
import re

import litbridge_atoms as atoms


# --------------------------------------------------------------- constants

VERSION = "litbridge_rules/2026-08-15"

RULE_LINE = re.compile(r"^\s*[-*#>\s]*rule\s*:", re.I)

FORBIDDEN_WORDS = ("true", "false")

MAX_GROUND_SPECIALIZATIONS = 3

LLM_GENERAL = "llm_general"

GROUND_SPECIALIZATION = "system_ground_specialization"

WARN_GENERALIZES = "generalizes_observed_constants"

CONNECTIVES = ("and", "or", "not", "xor", "implies", "=", "$and", "$or",
               "$not") + atoms.SET_BINDERS

REASON_CONTRADICTS = "the conclusion negates one of its own premises"

MAX_BODY_LITERALS = 5

MAX_BASE_RULES_PER_CALL = 12

EVENTPROP = "eventprop"

REASON_TRIED = "already tried in this case"

REASON_SOURCE_RULE = "identical to a rule the passage already states"

REASON_TOO_LONG = "more than %d premises" % MAX_BODY_LITERALS

NO_RULE = "NO_RULE"

REASON_BARE_RULE = "a RULE line without the MEANING line above it"

REASON_LONE_MEANING = "a MEANING line with no RULE line after it"

REASON_EMPTY_MEANING = "an empty MEANING line"

REASON_HELPER_ONLY = "every atom of the rule is a helper atom"

REASON_OVER_CAP = "beyond the %d valid model-written rules this call may add"

_MEANING = re.compile(r"^\s*MEANING\s*:\s*(.*)$", re.I)

_RULE = re.compile(r"^\s*RULE\s*:\s*(.*)$", re.I)

_NO_RULE = re.compile(r"^\s*NO_RULE\s*$", re.I)

REASON_NEGATIVE_PREMISE = ("a premise may not be negated: write `NOT` only "
                           "immediately before the conclusion")

REASON_DOUBLE_NEGATION = "`NOT NOT` is not a rule"

CATEGORY_NEGATIVE_PREMISE = "negated_premise"

CATEGORY_DOUBLE_NEGATION = "double_negation"

_DOUBLE_NOT = re.compile(r"\bNOT\s+NOT\b", re.I)

REASON_POLARITY = "meaning_formula_polarity_mismatch"

CATEGORY_POLARITY = REASON_POLARITY

POLARITY_MESSAGE = (
    "The English meaning states a negative consequence, but the formal "
    "conclusion is positive. Write `-> NOT [...]`, or correct the English "
    "meaning if the consequence is meant to be positive.")

NEGATION = re.compile(
    r"\b(?:not|never|cannot|can't|does\s+not|do\s+not|is\s+not|are\s+not|"
    r"will\s+not|doesn't|don't|isn't|aren't|won't)\b", re.I)

_THEN = re.compile(r"\bthen\b", re.I)

_PAREN = re.compile(r"\([^)]*\)")

DISTINCT_SYSTEM_PROMPT_NAME = "unifier_distinctness_v5_3_system"

DISTINCT_RULE_PREFIX = "D"

CUES = ("different", "distinct", "differ", "not the same", "unlike",
        "separate")

DISTINCT_LINE = re.compile(r"^\s*DISTINCT:\s*(D\d+)\s*$", re.I)

NEGATIVE_SYSTEM_PROMPT_NAME = "negative_relation_v6_1_system"

NEGATIVE_RULE_PREFIX = "N"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROMPT_DIR = os.path.join(ROOT, "prompts", "dynamic_alignment")

ORIGIN = "negative_relation_channel_v6_1"

MAX_PAIRS = 6

NEGATIVE_LINE = re.compile(r"^\s*NEGATIVE:\s*(N\d+)\s*$", re.I)

NONE_LINE = re.compile(r"^\s*NONE\s*$", re.I)


# --------------------------------------------------- reading one rule line

def parse_line(line):
  """-> {body: [(sign, atom)], head: (sign, atom)} for one `RULE:` line."""
  body_text = RULE_LINE.sub("", line, count=1)
  halves = _top_level_split(body_text, "->")
  if len(halves) != 2:
    raise RuleError("a rule needs exactly one `->`, found %d"
                    % (len(halves) - 1))
  left, right = halves
  body = []
  for chunk in _top_level_split(left, "AND"):
    if chunk.strip():
      body.append(_parse_atom(chunk))
  if not body:
    raise RuleError("no body literal")
  head_parts = [c for c in _top_level_split(right, "AND") if c.strip()]
  if len(head_parts) != 1:
    raise RuleError("a rule needs exactly one conclusion, found %d"
                    % len(head_parts))
  return {"body": body, "head": _parse_atom(head_parts[0])}

def _parse_atom(text):
  """-> (sign, atom).  `NOT [..]` is negative; anything else must be JSON."""
  t = text.strip()
  sign = "+"
  m = re.match(r"^(NOT|not)\b\s*(.*)$", t, re.S)
  if m:
    sign = "-"
    t = m.group(2).strip()
  if not t.startswith("["):
    raise RuleError("not a JSON atom: %s" % t[:60])
  try:
    atom = json.loads(t)
  except ValueError as e:
    raise RuleError("unreadable JSON atom (%s): %s" % (e, t[:60]))
  if not (isinstance(atom, list) and atom and isinstance(atom[0], str)):
    raise RuleError("an atom must be a non-empty JSON array beginning with "
                    "a string: %s" % t[:60])
  return sign, atom

def _top_level_split(text, token):
  """Split on `token` only outside JSON strings and arrays."""
  parts, depth, in_str, esc, start, i = [], 0, False, False, 0, 0
  n, tl = len(text), len(token)
  while i < n:
    c = text[i]
    if in_str:
      if esc:
        esc = False
      elif c == "\\":
        esc = True
      elif c == '"':
        in_str = False
      i += 1
      continue
    if c == '"':
      in_str = True
      i += 1
      continue
    if c == "[":
      depth += 1
      i += 1
      continue
    if c == "]":
      depth -= 1
      i += 1
      continue
    if depth == 0 and text[i:i + tl] == token:
      if token.isalpha():
        before = text[i - 1] if i else " "
        after = text[i + tl] if i + tl < n else " "
        if before.isalnum() or after.isalnum():
          i += 1
          continue
      parts.append(text[start:i])
      start = i + tl
      i += tl
      continue
    i += 1
  parts.append(text[start:])
  return parts

class RuleError(Exception):
  """A `RULE:` line that cannot be read."""

def to_rule(parsed):
  """`?X` -> `V1`, and the resulting names are the rule's ONLY variables."""
  rule = to_stage2_variables(parsed)
  order = []
  for lit in rule["body"] + [rule["head"]]:
    for v in _tokens(lit["atom"]):
      if v in rule["variables"].values() and v not in order:
        order.append(v)
  rule["llm_variables"] = order
  return rule

def to_stage2_variables(parsed):
  """`?X` -> `V1`, in first-appearance order over the body then the head.

  Only the SPELLING changes.  Repeated uses of one display variable map to one
  Stage-2 variable, and everything without `?` stays exactly as printed.
  """
  mapping, order = {}, []
  for sign, atom in parsed["body"] + [parsed["head"]]:
    for v in _display_vars(atom):
      if v not in mapping:
        mapping[v] = "V%d" % (len(order) + 1)
        order.append(v)
  body = [{"sign": s, "atom": _rename(a, mapping)} for s, a in parsed["body"]]
  head = {"sign": parsed["head"][0], "atom": _rename(parsed["head"][1],
                                                    mapping)}
  return {"body": body, "head": head, "variables": mapping}


# ------------------------------------------------ the displayed vocabulary

def vocabulary(candidates):
  """What the displayed atoms and their admitted source aliases license."""
  preds, arities, label_slots, labels = {}, {}, {}, {}
  constants, shapes, rows, grounding = set(), [], [], []

  def register(atom):
    pred = str(atom[0])
    args = list(atom[1:])
    preds.setdefault(pred, set()).add(len(args))
    arities.setdefault(pred, set()).add(len(args))
    slot = atoms.LABEL_SLOT.get(pred)
    if slot is not None and slot < len(args) \
            and isinstance(args[slot], str) \
            and not is_display_variable(args[slot]):
      label_slots.setdefault(pred, set()).add(slot)
      labels.setdefault(pred, set()).add(str(args[slot]))

  for row in candidates["groups"]:
    atom = row["atom"]
    register(atom)
    for inner in _inner_atoms(atom):
      register(inner)
    constants |= constants_in(atom)
    for shape in nested_shapes(atom):
      if not any(atoms.alpha_equivalent(shape, s) for s in shapes):
        shapes.append(shape)
    rows.append({"id": row["id"], "atom": atom, "sign": "+",
                  "role": row["internal_role"],
                  "priority_cost": row["cost"],
                  "section": row.get("section"),
                  "printed": row.get("printed")})
    if not [t for t in _tokens(atom) if is_display_variable(t)] \
            and atoms.SOURCE in (row.get("same_sign_source_kinds") or []):
      grounding.append({"id": row["id"], "sign": "+", "atom": atom,
                        "source_kinds": row.get("same_sign_source_kinds"),
                        "printed": row.get("printed")})
  return {"predicates": dict((p, sorted(v)) for p, v in preds.items()),
          "arities": dict((p, sorted(v)) for p, v in arities.items()),
          "constants": sorted(constants),
          "label_slots": dict((p, sorted(v)) for p, v in label_slots.items()),
          "labels_per_predicate": dict((p, sorted(v))
                                       for p, v in labels.items()),
          "nested_shapes": shapes, "atoms": rows,
          "grounding_atoms": grounding,
          "sections": dict((r["id"], r.get("section"))
                           for r in candidates["groups"]),
          "content_ids": sorted(set(r["id"] for r in candidates["groups"]
                                    if r.get("section") != "helper")),
          "policy": "the vocabulary is exactly the displayed atoms and their "
                    "admitted source aliases; only a `?` name is a variable"}

def is_display_variable(term):
  """A displayed atom writes its open positions as `?X`, and nothing else."""
  return isinstance(term, str) and term.startswith("?") \
      and not term.startswith("?:")

def constants_in(atom):
  """Every non-variable string of a displayed atom, nested terms included.

  `simple_rule_parser_v3.constants_in` asks `unifier_abstraction`, which calls
  `W0` a variable, so the world constant of `folio-0089`'s question clause
  never became writable vocabulary.
  """
  out = set()

  def go(t):
    if isinstance(t, str):
      if not is_display_variable(t):
        out.add(t)
      return
    if isinstance(t, list) and t:
      for x in t[1:]:
        go(x)
  for a in atom[1:]:
    go(a)
  return out

def nested_shapes(atom):
  """Every nested (list) argument of an atom, at any depth."""
  out = []

  def go(t):
    if isinstance(t, list):
      for x in t[1:]:
        if isinstance(x, list):
          out.append(x)
          go(x)
  go(atom)
  return out

def nested_is_displayed(term, shapes, rule_vars):
  """-> (ok, how).  Alpha-equal to a displayed shape, or its generalisation."""
  for s in shapes:
    if atoms.alpha_equivalent(term, s):
      return True, None
  for s in shapes:
    if _generalised_eventprop(term, s, rule_vars):
      return True, {"displayed": s, "written": term,
                    "rule": "eventprop_participant_generalisation"}
  return False, None


# --------------------------------------------------------- checking a rule

def validate(rule, vocab, source_keys=()):
  """-> (refusals, warnings, notes).  Refusals are mechanical."""
  why, warn, notes = [], [], []
  body, head = rule["body"], rule["head"]
  rule_vars = rule_variables(rule)
  if not body:
    why.append("no body literal")
  if len(body) > MAX_BODY_LITERALS:
    why.append(REASON_TOO_LONG)
  preds, arities = vocab["predicates"], vocab["arities"]
  constants = set(vocab["constants"])
  label_slots = vocab["label_slots"]
  for lit in body + [head]:
    atom = lit["atom"]
    pred = str(atom[0])
    args = list(atom[1:])
    if atoms.is_control_predicate(pred):
      why.append("control predicate `%s`" % pred)
      continue
    if atoms.is_equality_predicate(pred):
      why.append("equality is not part of the ordinary rule task")
      continue
    if pred.lower() in FORBIDDEN_WORDS:
      why.append("asserts `%s`" % pred)
      continue
    if pred not in preds:
      why.append("predicate `%s` was never displayed" % pred)
      continue
    if len(args) not in arities.get(pred, ()):
      why.append("arity %d was never displayed for `%s`"
                 % (len(args), pred))
      continue
    for i, a in enumerate(args):
      if isinstance(a, list):
        ok, how = nested_is_displayed(a, vocab["nested_shapes"],
                                      rule_vars)
        if not ok:
          why.append("a nested term that was never displayed: %s"
                     % json.dumps(a)[:80])
        elif how:
          notes.append(how)
        continue
      if is_rule_variable(a, rule_vars):
        if i in label_slots.get(pred, ()):
          why.append("a variable in the content-label position of "
                     "`%s`" % pred)
        continue
      if a in FORBIDDEN_WORDS:
        why.append("asserts `%s`" % a)
        continue
      if a not in constants:
        why.append("`%s` was never displayed" % a)
      elif i in label_slots.get(pred, ()) and \
              a not in vocab.get("labels_per_predicate", {}).get(pred,
                                                                ()):
        why.append("`%s` was never displayed as a content label of "
                   "`%s`" % (a, pred))
  body_vars = set()
  for lit in body:
    body_vars |= set(atom_variables(lit["atom"], rule_vars))
  free = set(atom_variables(head["atom"], rule_vars)) - body_vars
  if free:
    why.append("the conclusion uses %s, which the body never binds"
               % ", ".join(sorted(free)))
  cbody, chead = _canonical_parts(rule, rule_vars)
  if chead in cbody:
    why.append("a tautology: the conclusion is one of its own premises")
  if json.dumps([cbody, chead], sort_keys=True) in set(source_keys):
    why.append(REASON_SOURCE_RULE)
  if not why and generalizes_observed_constants(rule, vocab):
    warn.append(WARN_GENERALIZES)
  return why, warn, notes

def extra_refusals(rule, vocab):
  """v5.1's extra refusals, with the content check matched unsigned."""
  why = []
  content = set(vocab.get("content_ids") or [])
  used = []
  for lit in rule["body"] + [rule["head"]]:
    rows, _kind = _matching_rows(lit, vocab, rule)
    used += [r["id"] for r in rows]
  if content and not (set(used) & content):
    why.append(REASON_HELPER_ONLY)
  head = rule["head"]
  for lit in rule["body"]:
    if lit["sign"] != head["sign"] \
            and atoms.alpha_equivalent(lit["atom"], head["atom"]):
      why.append(REASON_CONTRADICTS)
      break
  return why

def polarity_mismatch(entry):
  """True when the English consequence is negative and the formula is not."""
  if head_is_negative(entry):
    return False
  return says_negative(entry.get("meaning"))

def says_negative(meaning):
  """Does the consequence explicitly deny its conclusion?"""
  return bool(NEGATION.search(consequence_of(meaning)))

def consequence_of(meaning):
  """The part of the meaning that states what follows.

  `then` splits an `If ..., then ...` sentence; without it the whole line is
  the consequence, which is the conservative reading for this check.
  """
  text = meaning or ""
  parts = _THEN.split(text, maxsplit=1)
  return parts[1] if len(parts) > 1 else text

def negation_only_in_an_aside(meaning):
  """Is the only negation inside a parenthetical remark?

  The plan says to inspect the consequence, and a parenthetical justification
  sits inside it, so such a rule is refused like any other.  The fact is
  recorded per refusal, because it is the one class of refusal that may be a
  false positive and the count has to be visible.
  """
  tail = consequence_of(meaning)
  return bool(NEGATION.search(tail)) and not NEGATION.search(
      _PAREN.sub("", tail))


# --------------------------------------------- canonical form and printing

def canonical(rule, rule_vars=None):
  """The rule up to renaming its OWN variables, as one comparable string."""
  body, head = _canonical_parts(rule, rule_vars if rule_vars is not None
                                else rule_variables(rule))
  return json.dumps([body, head], sort_keys=True)

def _canonical_parts(rule, rule_vars):
  def blank(atom):
    def go(t):
      if is_rule_variable(t, rule_vars):
        return "?"
      if isinstance(t, list) and t:
        return [t[0]] + [go(x) for x in t[1:]]
      return t
    return [atom[0]] + [go(a) for a in atom[1:]]
  body = sorted(rule["body"],
                key=lambda l: json.dumps([l["sign"], blank(l["atom"])]))
  names = {}

  def go(t):
    if is_rule_variable(t, rule_vars):
      names.setdefault(t, "_v%d" % len(names))
      return names[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t

  def norm(lit):
    return [lit["sign"], [lit["atom"][0]] + [go(a) for a in lit["atom"][1:]]]
  return [norm(l) for l in body], norm(rule["head"])

def printed_rule(rule):
  """One line, in the grammar it was written in, renaming only its variables."""
  rule_vars = rule_variables(rule)
  names, order = {}, []
  for lit in rule["body"] + [rule["head"]]:
    for v in _tokens(lit["atom"]):
      if v in rule_vars and v not in names:
        i = len(order)
        names[v] = (atoms.DISPLAY_VARS[i] if i < len(atoms.DISPLAY_VARS)
                    else "?V%d" % (i + 1))
        order.append(v)

  def rename(atom):
    def go(t):
      if isinstance(t, str):
        return names.get(t, t)
      if isinstance(t, list) and t:
        return [t[0]] + [go(x) for x in t[1:]]
      return t
    return [atom[0]] + [go(a) for a in atom[1:]]

  def show(lit):
    return atoms.printed_atom(rename(lit["atom"]),
                            negated=lit.get("sign") == "-")
  return "%s -> %s" % (" AND ".join(show(l) for l in rule["body"]),
                       show(rule["head"]))

def source_rule_keys(source_rules):
  """The passage's own rules, canonicalised over their Stage-2 variables."""
  out = set()
  for r in source_rules or []:
    rule_vars = [t for lit in r["body"] + [r["head"]]
                 for t in _tokens(lit["atom"]) if atoms.is_stage2_variable(t)]
    out.add(canonical(r, rule_vars))
  return out


# ------------------------------------- candidates a rule's atoms came from

def rule_candidates(rule, vocab):
  """-> (matched candidate ids per literal, unmatched atoms, total cost).

  Same as v5.3's, except that a literal matches a displayed row by its atom
  rather than by its atom and sign, and each match records the sign the rule
  wrote.
  """
  matched, unmatched, total = [], [], 0
  for lit in rule["body"] + [rule["head"]]:
    rows, kind = _matching_rows(lit, vocab, rule)
    best = (rows or [None])[0]
    if best is None:
      unmatched.append(atoms.printed_atom(atoms.display_atom(lit["atom"]),
                                          negated=lit["sign"] == "-"))
      continue
    matched.append({"literal": atoms.printed_atom(
                        atoms.display_atom(lit["atom"]),
                        negated=lit["sign"] == "-"),
                    "candidate": best["id"], "role": best["role"],
                    "priority_cost": best["priority_cost"],
                    "match_kind": kind,
                    "sign": lit["sign"],
                    "displayed_sign": best["sign"],
                    "equally_good": [r["id"] for r in rows][:6]})
    total += best["priority_cost"]
  return matched, unmatched, total

def _matching_rows(lit, vocab, rule):
  """The displayed rows this literal was copied from, matched UNSIGNED.

  Every displayed row is positive.  A negative conclusion names a displayed
  positive atom and negates it, so the match ignores the sign and the sign is
  reported separately.
  """
  want = lit["atom"]
  exact = [row for row in vocab["atoms"]
           if atoms.alpha_equivalent(row["atom"], want)]
  if exact:
    return exact, "alpha_exact"
  loose = [row for row in vocab["atoms"]
           if atoms.unify_unsigned_atoms(atoms._clause_shape(row["atom"]),
                                      atoms._clause_shape(want))["unifiable"]]
  loose.sort(key=lambda r: (len(atom_variables(r["atom"],
                                               rule_variables(rule))),
                            str(r.get("id"))))
  return loose, "unifier"

def role_fit(rule, vocab):
  """Do the rule's premises sit in PREMISE/BOTH and its head in CONSEQUENCE?"""
  def role_for(lit):
    for row in vocab["atoms"]:
      if row["sign"] == lit["sign"] and atoms.alpha_equivalent(row["atom"],
                                                         lit["atom"]):
        return row["role"]
    for row in vocab["atoms"]:
      if row["sign"] == lit["sign"] and atoms.unify_unsigned_atoms(
              atoms._clause_shape(row["atom"]),
              atoms._clause_shape(lit["atom"]))["unifiable"]:
        return row["role"]
    return None
  body_ok = all(role_for(l) in (atoms.PREMISE, atoms.BOTH) for l in rule["body"])
  head_ok = role_for(rule["head"]) in (atoms.CONSEQUENCE, atoms.BOTH)
  return {"body_roles": [role_for(l) for l in rule["body"]],
          "head_role": role_for(rule["head"]),
          "body_fits": body_ok, "head_fits": head_ok,
          "fits": bool(body_ok and head_ok)}


# -------------------------------------------------- ground specializations

def ground_specializations(rule, vocab, cap=MAX_GROUND_SPECIALIZATIONS):
  """Up to `cap` grounded variants, from signed source-linked matches only."""
  rule_vars = rule_variables(rule)
  evidence = [r for r in vocab.get("grounding_atoms") or []]
  if not evidence or not rule_vars:
    return []
  results, budget = [], [400]

  def walk(i, subst, used):
    if len(results) >= cap or budget[0] <= 0:
      return
    if i >= len(rule["body"]):
      if subst:
        results.append((dict(subst), list(used)))
      return
    lit = rule["body"][i]
    for g in evidence:
      budget[0] -= 1
      if budget[0] <= 0:
        return
      if g["sign"] != lit["sign"]:
        continue
      got = _match_atom(lit["atom"], g["atom"], subst, rule_vars)
      if got is not None:
        walk(i + 1, got, used + [g["id"]])
  walk(0, {}, [])
  out, seen = [], set()
  for subst, used in results:
    body = [{"sign": l["sign"], "atom": _apply(l["atom"], subst)}
            for l in rule["body"]]
    head = {"sign": rule["head"]["sign"],
            "atom": _apply(rule["head"]["atom"], subst)}
    variant = {"body": body, "head": head,
               "llm_variables": [v for v in rule_vars if v not in subst]}
    key = canonical(variant)
    if key == canonical(rule) or key in seen:
      continue
    seen.add(key)
    variant["canonical"] = key
    variant["printed"] = printed_rule(variant)
    variant["substitution"] = dict(subst)
    variant["grounded_on"] = used
    out.append(variant)
  return out[:cap]

def _match_atom(atom, ground, subst, rule_vars):
  """Match a rule atom against a displayed ground atom.  Rule vars only."""
  if str(atom[0]) != str(ground[0]) or len(atom) != len(ground):
    return None
  out = dict(subst)

  def go(x, y):
    if is_rule_variable(x, rule_vars):
      if x in out:
        return json.dumps(out[x]) == json.dumps(y)
      out[x] = y
      return True
    if isinstance(x, str) or isinstance(y, str):
      return x == y
    if not (isinstance(x, list) and isinstance(y, list)):
      return False
    if len(x) != len(y) or x[0] != y[0]:
      return False
    return all(go(p, q) for p, q in zip(x[1:], y[1:]))
  for p, q in zip(atom[1:], ground[1:]):
    if not go(p, q):
      return None
  return out

def _apply(atom, subst):
  def go(t):
    if isinstance(t, str):
      return copy.deepcopy(subst[t]) if t in subst else t
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]


# --------------------------------------------------- parsing a whole reply

def parse_response(text, vocab, main_ids, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
  """The v6 signed parse, with polarity-mismatched rules refused by name."""
  got = _parse_response_blocks(text, vocab, main_ids, source_rules,
                          max_rules=max_rules, start_index=start_index,
                          existing=existing, tried=tried)
  kept, refused = [], []
  dropped_parents = set()
  for entry in got["accepted"]:
    if entry.get("origin") == GROUND_SPECIALIZATION:
      continue
    if polarity_mismatch(entry):
      dropped_parents.add(entry["rule_id"])
      refused.append({"line": (entry.get("lines") or [""])[0],
                      "printed": entry["printed"],
                      "meaning": entry.get("meaning", ""),
                      "reasons": [REASON_POLARITY],
                      "message": POLARITY_MESSAGE,
                      "category": CATEGORY_POLARITY,
                      "negation_only_in_an_aside":
                          negation_only_in_an_aside(
                              entry.get("meaning"))})
      continue
    kept.append(entry)
  for entry in got["accepted"]:
    if entry.get("origin") != GROUND_SPECIALIZATION:
      continue
    if entry.get("specialization_of") in dropped_parents:
      refused.append({"line": (entry.get("lines") or [""])[0],
                      "printed": entry["printed"],
                      "meaning": entry.get("meaning", ""),
                      "reasons": [REASON_POLARITY],
                      "message": POLARITY_MESSAGE,
                      "category": CATEGORY_POLARITY,
                      "variant_of": entry.get("specialization_of")})
      continue
    kept.append(entry)
  kept.sort(key=lambda r: int(str(r["rule_id"])[1:] or 0))
  got["accepted"] = kept
  got["rejected"] = list(got["rejected"]) + refused
  got["polarity_refusals"] = refused
  got["rejections_by_category"] = _counts(got["rejected"])
  got["rejection_reasons"] = sorted(set(
      r for x in got["rejected"] for r in (x.get("reasons") or [])))[:20]
  got["base_rules_accepted"] = sum(
      1 for r in kept if r.get("origin") != GROUND_SPECIALIZATION)
  got["generated_specializations_accepted"] = len(kept) - got[
      "base_rules_accepted"]
  got["signed_counts"] = signed_counts(kept)
  got["negative_conclusions"] = [r["rule_id"] for r in kept
                                 if head_is_negative(r)]
  got["meanings"] = dict((r["rule_id"], r.get("meaning", "")) for r in kept)
  got["version"] = VERSION
  return got

def parse_rule_lines(text, vocab, source_rules=(),
                     max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                     existing=(), tried=()):
  """v5.3's `parse_response` with a signed conclusion allowed.

  Every step is v5.3's own function; only the sign rule, the candidate match
  and the two new refusals differ.
  """
  lines = (text or "").splitlines()
  rule_lines = [l for l in lines if RULE_LINE.match(l)]
  source_keys = source_rule_keys(source_rules)
  tried_keys = set(tried or [])
  seen = dict((r["canonical"], r) for r in existing)
  accepted, rejected, over_cap, notes = [], [], [], []
  base_kept = 0
  n = [start_index - 1]

  def fresh_id():
    n[0] += 1
    return "R%d" % n[0]

  for raw in rule_lines:
    line = raw.strip()
    parsed, refusal = _parse_one_line(line)
    if refusal is not None:
      rejected.append(refusal)
      continue
    rule = to_rule(parsed)
    why, warn, got_notes = validate(rule, vocab, source_keys)
    if not why:
      why = extra_refusals(rule, vocab)
    if why:
      rejected.append({"line": line[:220], "reasons": why,
                       "printed": printed_rule(rule),
                       "category": _category(why)})
      continue
    key = canonical(rule)
    if key in tried_keys:
      rejected.append({"line": line[:220], "reasons": [REASON_TRIED],
                       "printed": printed_rule(rule),
                       "category": "repeat_of_a_tried_rule"})
      continue
    if key in seen:
      seen[key].setdefault("lines", []).append(line[:220])
      continue
    if base_kept >= max_rules:
      over_cap.append({"line": line[:220],
                       "printed": printed_rule(rule),
                       "why": REASON_OVER_CAP % max_rules})
      continue
    matched, unmatched, cost = rule_candidates(rule, vocab)
    entry = {"rule_id": fresh_id(), "body": rule["body"],
             "head": rule["head"], "canonical": key,
             "llm_variables": rule["llm_variables"],
             "printed": printed_rule(rule), "lines": [line[:220]],
             "origin": LLM_GENERAL, "warnings": warn,
             "premises": len(rule["body"]),
             "head_sign": rule["head"]["sign"],
             "negative_conclusion": rule["head"]["sign"] == "-",
             "candidate_matches": matched,
             "atoms_matching_no_candidate": unmatched,
             "rule_priority_cost": cost,
             "role_fit": role_fit(rule, vocab),
             "generalisation_notes": got_notes,
             "variants": []}
    seen[key] = entry
    accepted.append(entry)
    notes.extend(got_notes)
    base_kept += 1
    if WARN_GENERALIZES in warn:
      for variant in ground_specializations(rule, vocab):
        if variant["canonical"] in seen:
          continue
        vmatched, vunmatched, vcost = rule_candidates(variant, vocab)
        child = {"rule_id": fresh_id(), "body": variant["body"],
                 "head": variant["head"],
                 "canonical": variant["canonical"],
                 "llm_variables": variant["llm_variables"],
                 "printed": variant["printed"],
                 "lines": [line[:220]],
                 "origin": GROUND_SPECIALIZATION,
                 "specialization_of": entry["rule_id"],
                 "substitution": variant["substitution"],
                 "grounded_on": variant["grounded_on"],
                 "warnings": [], "premises": len(variant["body"]),
                 "head_sign": variant["head"]["sign"],
                 "negative_conclusion":
                     variant["head"]["sign"] == "-",
                 "candidate_matches": vmatched,
                 "atoms_matching_no_candidate": vunmatched,
                 "rule_priority_cost": vcost,
                 "role_fit": role_fit(variant, vocab),
                 "generalisation_notes": [],
                 "variants": []}
        seen[variant["canonical"]] = child
        entry["variants"].append(child["rule_id"])
        accepted.append(child)
  return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
          "readable_lines": len(rule_lines), "response_lines": len(lines),
          "rejection_reasons": sorted(set(r for x in rejected
                                          for r in x["reasons"]))[:20],
          "rejections_by_category": _counts(rejected),
          "base_rules_accepted": base_kept,
          "generated_specializations_accepted": len(accepted) - base_kept,
          "base_rule_limit": max_rules,
          "refused_negative_lines": sum(
              1 for r in rejected
              if r["category"] in (CATEGORY_NEGATIVE_PREMISE,
                                   CATEGORY_DOUBLE_NEGATION)),
          "generalisation_notes": notes,
          "next_index": n[0] + 1, "version": VERSION}

def split_blocks(text):
  """-> (blocks, refusals, said_no_rule).  Order is the reply's own order."""
  blocks, refusals = [], []
  pending = None
  said_no_rule = False
  for raw in (text or "").splitlines():
    if _NO_RULE.match(raw):
      said_no_rule = True
      continue
    m = _MEANING.match(raw)
    if m:
      if pending is not None:
        refusals.append({"line": pending["raw"][:220],
                         "reasons": [REASON_LONE_MEANING],
                         "category": "meaning_without_rule"})
      meaning = m.group(1).strip()
      pending = {"meaning": meaning, "raw": raw.strip()}
      if not meaning:
        refusals.append({"line": raw.strip()[:220],
                         "reasons": [REASON_EMPTY_MEANING],
                         "category": "empty_meaning"})
        pending = None
      continue
    r = _RULE.match(raw)
    if r:
      if pending is None:
        refusals.append({"line": raw.strip()[:220],
                         "reasons": [REASON_BARE_RULE],
                         "category": "rule_without_meaning"})
        continue
      blocks.append({"meaning": pending["meaning"],
                     "rule_line": raw.strip(),
                     "rule_text": r.group(1).strip()})
      pending = None
      continue
  if pending is not None:
    refusals.append({"line": pending["raw"][:220],
                     "reasons": [REASON_LONE_MEANING],
                     "category": "meaning_without_rule"})
  return blocks, refusals, said_no_rule

def _uses_a_main_atom(entry, main_ids):
  for got in entry.get("candidate_matches") or []:
    if got.get("candidate") in main_ids:
      return True
    for other in got.get("equally_good") or []:
      if other in main_ids:
        return True
  return False


# ------------------------------------------------ the distinctness channel

def build_rule(row, rule_id):
  """-> the one rule shape this channel may produce, or raise."""
  a, b, label = row["a"], row["b"], row["class"]
  if a == b:
    raise ValueError("a distinctness rule needs two different names")
  if not (_is_ground_name(a) and _is_ground_name(b)):
    raise ValueError("both names must be ground")
  if not isinstance(label, str) or not label:
    raise ValueError("the shared class must be a displayed label")
  body = [{"sign": "+", "atom": ["isa", label, a]},
          {"sign": "+", "atom": ["isa", label, b]}]
  head = {"sign": "-", "atom": ["=", a, b]}
  rule = {"rule_id": rule_id, "body": body, "head": head,
          "llm_variables": [], "premises": 2,
          "origin": "distinctness_channel_v5_3",
          "warnings": [], "variants": [],
          "candidate_matches": [{"literal": atoms.printed_atom(l["atom"]),
                                 "candidate": cid, "role": "PREMISE",
                                 "priority_cost": 0,
                                 "match_kind": "distinctness_channel"}
                                for l, cid in zip(body,
                                                  row["candidate_ids"])],
          "atoms_matching_no_candidate": [],
          "rule_priority_cost": 0,
          "role_fit": {"fits": True, "body_fits": True, "head_fits": True,
                       "body_roles": ["PREMISE", "PREMISE"],
                       "head_role": "CONSEQUENCE"},
          "distinctness_pair": {"a": a, "b": b, "class": label,
                                "question_clause": row["question_clause"],
                                "cues": row["cues"],
                                "class_clauses": row.get("class_clauses")}}
  rule["canonical"] = canonical(rule)
  rule["printed"] = printed_rule(rule)
  return rule

def question_needs_distinctness(view):
  """-> [(A, B, clause name)] for every negative equality a question needs."""
  out, seen = [], set()
  for clause in view.get("final_clauses") or []:
    if atoms._source_kind(clause) != atoms.QUESTION:
      continue
    for lit in atoms.literals_of(clause.get("@logic")
                              or clause.get("@question")):
      if not (isinstance(lit, list) and len(lit) == 3
              and isinstance(lit[0], str)):
        continue
      if not atoms.is_equality_predicate(lit[0]) or atoms.sign_of(lit) != "-":
        continue
      a, b = lit[1], lit[2]
      if not (_is_ground_name(a) and _is_ground_name(b)) or a == b:
        continue
      key = json.dumps(sorted([a, b]))
      if key in seen:
        continue
      seen.add(key)
      out.append((a, b, str(clause.get("@name") or "")))
  return out


# ------------------------------------------- the negative-relation channel

def negative_is_asked(view):
  """-> {displayed-shaped atom key: [question clause names]}.

  A question clause holds the negation of what is to be proved, so a literal
  that appears POSITIVELY there is one whose negation would close the
  question.  That is the sign logic, not a raw minus sign.
  """
  out = {}
  for clause in view.get("final_clauses") or []:
    if atoms._source_kind(clause) != atoms.QUESTION:
      continue
    for lit in atoms.literals_of(clause.get("@logic")
                              or clause.get("@question")):
      if not (isinstance(lit, list) and lit
              and isinstance(lit[0], str)):
        continue
      if atoms.is_control_predicate(lit[0]) \
              or atoms.is_equality_predicate(lit[0]):
        continue
      if atoms.sign_of(lit) != "+":
        continue
      key = _shape(atoms.unsigned_atom(lit))
      out.setdefault(key, []).append(str(clause.get("@name") or ""))
  return out

def stated_by_the_passage(view):
  """-> {shape: [clause names]} for atoms a source clause actually states.

  A source fact states its literal; a source rule states its positive
  conclusion.  A population clause and a question clause state nothing here.
  """
  out = {}
  for clause in view.get("final_clauses") or []:
    if atoms._source_kind(clause) != atoms.SOURCE:
      continue
    if clause.get("@sourcetype") == "populate":
      continue
    for lit in atoms._content_literals(clause):
      if atoms.sign_of(lit) != "+":
        continue
      if atoms.is_control_predicate(lit[0]) \
              or atoms.is_equality_predicate(lit[0]):
        continue
      out.setdefault(_shape(atoms.unsigned_atom(lit)), []).append(
          str(clause.get("@name") or ""))
  return out

def same_participants(a_atom, b_atom):
  """-> True when the two atoms name the same things, in the same order.

  A constant must be the same constant.  Two open positions correspond, and
  become one rule variable when the rule is built.  Nothing else matches, so
  a swapped order or an invented participant is never eligible.
  """
  a, b = participants(a_atom), participants(b_atom)
  if len(a) != len(b) or not a:
    return False
  for x, y in zip(a, b):
    if _is_open(x) and _is_open(y):
      continue
    if isinstance(x, list) or isinstance(y, list):
      if json.dumps(x, sort_keys=True) != json.dumps(y, sort_keys=True):
        return False
      continue
    if _is_open(x) or _is_open(y):
      return False
    if atoms._norm_constant(str(x)) != atoms._norm_constant(str(y)):
      return False
  return True

def participants(atom):
  """The arguments that name things, with the content label left out."""
  slot = _label_slot(atom)
  return [a for i, a in enumerate(atom[1:]) if i != slot]


# ---------------------------------------------------------------- the rest

def _display_vars(atom):
  out = []

  def go(t):
    if isinstance(t, str) and t.startswith("?"):
      if t not in out:
        out.append(t)
    elif isinstance(t, list):
      for x in t[1:]:
        go(x)
  for a in atom[1:]:
    go(a)
  return out

def _rename(atom, mapping):
  def go(t):
    if isinstance(t, str) and t.startswith("?"):
      return mapping[t]
    if isinstance(t, list) and t:
      return [t[0]] + [go(x) for x in t[1:]]
    return t
  return [atom[0]] + [go(a) for a in atom[1:]]

def stage2_source_rules(stage2):
  """The passage's OWN rules, in the same canonical form.

  Used for one rejection only: a proposed rule byte-identical to something the
  theory already states adds nothing and costs a slot.
  """
  out = []

  def conjuncts(node):
    if isinstance(node, list) and node and node[0] == "and":
      got = []
      for ch in node[1:]:
        got.extend(conjuncts(ch))
      return got
    return [node]

  def as_literal(node):
    if isinstance(node, list) and len(node) == 2 and node[0] == "not":
      inner = node[1]
      if isinstance(inner, list) and inner and isinstance(inner[0], str):
        return {"sign": "-", "atom": list(inner)}
      return None
    if isinstance(node, list) and node and isinstance(node[0], str) \
            and node[0] not in atoms.LOGICAL_HEADS:
      return {"sign": "+", "atom": list(node)}
    return None

  def walk(node):
    if not isinstance(node, list) or not node:
      return
    head = node[0]
    if head in ("holds", "question") and len(node) >= 2:
      walk(node[-1])
      return
    if head == "ask" and len(node) == 3:
      walk(node[2])
      return
    if head in ("forall", "exists") and len(node) >= 3:
      walk(node[2])
      return
    if head == "normally" and len(node) == 2:
      walk(node[1])
      return
    if head == "and":
      for ch in node[1:]:
        walk(ch)
      return
    if head == "implies" and len(node) == 3:
      body, concl = node[1], node[2]
      if isinstance(concl, list) and concl and concl[0] == "normally":
        concl = concl[1]
      lits = [as_literal(c) for c in conjuncts(body)]
      h = as_literal(concl)
      if h is not None and all(l is not None for l in lits) and lits:
        out.append({"body": lits, "head": h})
      return

  for _uid, pkg in atoms.stage2_packages(stage2):
    walk(pkg)
  return out

def _inner_atoms(atom):
  """Atoms nested inside a displayed structure, e.g. inside a `$setof` body.

  Without this, `object` in `eb2-0121`'s set term is invisible to the
  vocabulary and a rule copying that term is refused for using a word it was
  shown.
  """
  out = []

  def go(t, top):
    if not isinstance(t, list) or not t or not isinstance(t[0], str):
      return
    if t[0] not in CONNECTIVES and not top:
      out.append(t)
    start = 2 if t[0] in atoms.SET_BINDERS else 1
    for x in t[start:]:
      go(x, False)
  go(atom, True)
  return out

def _tokens(term):
  out = []
  if isinstance(term, str):
    out.append(term)
  elif isinstance(term, list):
    for x in term[1:]:
      out.extend(_tokens(x))
  return out

def rule_variables(rule):
  return list(rule.get("llm_variables") or [])

def is_rule_variable(term, rule_vars):
  return isinstance(term, str) and term in rule_vars

def atom_variables(atom, rule_vars):
  return [t for t in _tokens(atom) if t in rule_vars]

def _generalised_eventprop(term, shape, rule_vars):
  """`eventprop($role, C)` displayed, `eventprop($role, ?V)` written."""
  if not (isinstance(term, list) and isinstance(shape, list)):
    return False
  if str(term[0]) != EVENTPROP or str(shape[0]) != EVENTPROP:
    return False
  if len(term) != 3 or len(shape) != 3:
    return False
  if json.dumps(term[1]) != json.dumps(shape[1]):
    return False                                    # the role is exact
  written, displayed = term[2], shape[2]
  if not is_rule_variable(written, rule_vars):
    return False
  return isinstance(displayed, str) and displayed not in rule_vars \
      and not atoms.is_variable_term(displayed)

def generalizes_observed_constants(rule, vocab):
  """Did the model put a variable where every displayed atom had a constant?"""
  rule_vars = rule_variables(rule)
  for lit in rule["body"] + [rule["head"]]:
    atom = lit["atom"]
    pred = str(atom[0])
    args = list(atom[1:])
    shown = [r["atom"] for r in vocab["atoms"]
             if str(r["atom"][0]) == pred and len(r["atom"]) == len(atom)]
    if not shown:
      continue
    for i, a in enumerate(args):
      if not is_rule_variable(a, rule_vars):
        continue
      if atoms.LABEL_SLOT.get(pred) == i:
        continue
      values = [s[i + 1] for s in shown]
      if values and all(isinstance(v, str) and not atoms.is_variable_term(v)
                        for v in values):
        return True
  return False

def _category(why):
  first = why[0]
  if first == REASON_SOURCE_RULE:
    return "already_in_the_passage"
  if first == REASON_TOO_LONG:
    return "too_many_premises"
  if first.startswith("the conclusion uses"):
    return "range_unsafe"
  if first == REASON_HELPER_ONLY:
    return "helper_atoms_only"
  if "never displayed" in first:
    return "atom_not_in_the_candidate_list"
  if first.startswith("a tautology"):
    return "conclusion_repeats_a_premise"
  return "other"

def _counts(rejected):
  out = {}
  for r in rejected:
    out[r["category"]] = out.get(r["category"], 0) + 1
  return out

def head_is_negative(rule):
  return (rule.get("head") or {}).get("sign") == "-"

def signed_counts(rules):
  neg = sum(1 for r in rules if head_is_negative(r))
  return {"rules": len(rules), "positive_conclusion": len(rules) - neg,
          "negative_conclusion": neg}

def _parse_one_line(line):
  """-> (parsed, refusal).  Signed conclusions pass; signed premises do not."""
  if _DOUBLE_NOT.search(line):
    return None, {"line": line[:220], "reasons": [REASON_DOUBLE_NEGATION],
                  "category": CATEGORY_DOUBLE_NEGATION}
  try:
    parsed = parse_line(line)
  except RuleError as e:
    return None, {"line": line[:220], "reasons": [str(e)],
                  "category": "unreadable"}
  if any(s == "-" for s, _a in parsed["body"]):
    return None, {"line": line[:220], "reasons": [REASON_NEGATIVE_PREMISE],
                  "category": CATEGORY_NEGATIVE_PREMISE}
  return parsed, None

def _parse_response_blocks(text, vocab, main_ids, source_rules=(),
                   max_rules=MAX_BASE_RULES_PER_CALL, start_index=1,
                   existing=(), tried=()):
  """The v5.9 block contract over the signed rule loop."""
  blocks, refusals, said_no_rule = split_blocks(text)
  meaning_of = {}
  for b in blocks:
    meaning_of.setdefault(b["rule_line"][:220], b["meaning"])
  synthetic = "\n".join(b["rule_line"] for b in blocks)
  got = parse_rule_lines(synthetic, vocab, source_rules,
                         max_rules=10 ** 6, start_index=start_index,
                         existing=existing, tried=tried)
  for entry in got["accepted"]:
    entry["meaning"] = meaning_of.get((entry.get("lines") or [""])[0], "")
  for row in got["rejected"]:
    row["meaning"] = meaning_of.get(row.get("line", ""), "")

  kept, dropped, base_kept = [], [], 0
  by_parent = {}
  for entry in got["accepted"]:
    if entry.get("origin") == GROUND_SPECIALIZATION:
      continue
    if not _uses_a_main_atom(entry, main_ids):
      dropped.append({"line": (entry.get("lines") or [""])[0],
                      "printed": entry["printed"],
                      "meaning": entry.get("meaning", ""),
                      "reasons": [REASON_HELPER_ONLY],
                      "category": "helper_only"})
      continue
    if base_kept >= max_rules:
      dropped.append({"line": (entry.get("lines") or [""])[0],
                      "printed": entry["printed"],
                      "meaning": entry.get("meaning", ""),
                      "why": REASON_OVER_CAP % max_rules,
                      "category": "over_cap", "over_cap": True})
      continue
    base_kept += 1
    kept.append(entry)
    by_parent[entry["rule_id"]] = entry
  for entry in got["accepted"]:
    if entry.get("origin") != GROUND_SPECIALIZATION:
      continue
    if entry.get("specialization_of") in by_parent:
      entry["meaning"] = by_parent[entry["specialization_of"]].get(
          "meaning", "")
      kept.append(entry)
  kept.sort(key=lambda r: int(str(r["rule_id"])[1:] or 0))
  over_cap = list(got["over_cap"]) + [d for d in dropped
                                      if d.get("over_cap")]
  rejected = list(got["rejected"]) + refusals + [
      d for d in dropped if not d.get("over_cap")]
  ids = [int(str(r["rule_id"])[1:] or 0) for r in kept]
  return {"accepted": kept, "rejected": rejected, "over_cap": over_cap,
          "blocks": blocks, "format_refusals": refusals,
          "said_no_rule": said_no_rule and not blocks,
          "readable_blocks": len(blocks),
          "readable_lines": len(blocks),
          "response_lines": len((text or "").splitlines()),
          "rejection_reasons": sorted(set(
              r for x in rejected for r in (x.get("reasons") or [])))[:20],
          "rejections_by_category": _counts(rejected),
          "base_rules_accepted": base_kept,
          "generated_specializations_accepted": len(kept) - base_kept,
          "base_rule_limit": max_rules,
          "refused_negative_lines": got["refused_negative_lines"],
          "generalisation_notes": got["generalisation_notes"],
          "meanings": dict((r["rule_id"], r.get("meaning", ""))
                           for r in kept),
          "signed_counts": signed_counts(kept),
          "negative_conclusions": [r["rule_id"] for r in kept
                                   if head_is_negative(r)],
          "next_index": (max(ids) + 1) if ids else got["next_index"],
          "version": VERSION}

def _is_ground_name(term):
  if not isinstance(term, str):
    return False
  if atoms.is_clause_variable(term) or term.startswith("$"):
    return False
  if term.startswith("sk") or "$some" in term:
    return False
  return bool(term.strip())

def _bare(term):
  return term[2:] if isinstance(term, str) and term.startswith("#:") else term

def _source_classes(view):
  """-> {thing: {class: clause name}} from the passage's own `isa` clauses."""
  out = {}
  for clause in view.get("final_clauses") or []:
    if atoms._source_kind(clause) != atoms.SOURCE:
      continue
    lits = atoms._content_literals(clause)
    if len(lits) != 1:
      continue
    lit = lits[0]
    atom = atoms.unsigned_atom(lit)
    if atoms.sign_of(lit) != "+" or str(atom[0]) != "isa" or len(atom) != 3:
      continue
    label, thing = atom[1], atom[2]
    if not isinstance(label, str) or not isinstance(thing, str):
      continue
    out.setdefault(_bare(thing), {})[label] = str(clause.get("@name") or "")
  return out

def _displayed(candidates, atom):
  for g in candidates["groups"]:
    if atoms.alpha_equivalent(g["atom"], atom):
      return g["id"]
  return None

def cue_in(text):
  low = (text or "").lower()
  return [c for c in CUES if c in low]

def distinct_system_prompt():
  with open(os.path.join(PROMPT_DIR, "%s.txt" % DISTINCT_SYSTEM_PROMPT_NAME)) as f:
    return f.read()

def distinct_system_prompt_sha256():
  return hashlib.sha256(distinct_system_prompt().encode()).hexdigest()

def distinct_eligible_pairs(view, candidates, question_text):
  """-> (pairs, refusals).  Every refusal names the condition that failed."""
  pairs, refused = [], []
  cues = cue_in(question_text)
  classes = _source_classes(view)
  for a, b, clause in question_needs_distinctness(view):
    row = {"a": _bare(a), "b": _bare(b), "question_clause": clause,
           "cues": cues}
    if not cues:
      row["why_refused"] = ("the question's English carries no "
                            "difference cue")
      refused.append(row)
      continue
    shared = sorted(set(classes.get(_bare(a), {}))
                    & set(classes.get(_bare(b), {})))
    if not shared:
      row["why_refused"] = "the passage gives them no class in common"
      refused.append(row)
      continue
    label = shared[0]
    atoms = [["isa", label, _bare(a)], ["isa", label, _bare(b)]]
    ids = [_displayed(candidates, x) for x in atoms]
    if not all(ids):
      row["why_refused"] = ("their class atoms are not both displayed "
                            "candidates")
      row["class"] = label
      refused.append(row)
      continue
    row.update({"class": label, "class_atoms": atoms,
                "candidate_ids": ids,
                "class_clauses": [classes[_bare(a)][label],
                                  classes[_bare(b)][label]]})
    pairs.append(row)
  for i, row in enumerate(pairs[:MAX_PAIRS], start=1):
    row["id"] = "%s%d" % (DISTINCT_RULE_PREFIX, i)
  return pairs[:MAX_PAIRS], refused

def distinct_user_message(passage, question, pairs):
  lines = ["PASSAGE:", passage, "", "QUESTION:", question, "", "PAIRS:", ""]
  for row in pairs:
    lines.append("  %-4s %s  and  %s" % (row["id"], row["a"], row["b"]))
    lines.append("       the passage calls both of them: %s" % row["class"])
    lines.append("")
  lines.append("For each pair you are sure denotes two different things, "
               "write one DISTINCT: line. Write nothing else.")
  return "\n".join(lines)

def distinct_parse_reply(text, pairs):
  """-> (affirmed ids, unreadable lines).  Silence is abstention."""
  ids = set(row["id"] for row in pairs)
  affirmed, junk = [], []
  for line in (text or "").splitlines():
    if not line.strip():
      continue
    m = DISTINCT_LINE.match(line)
    if not m:
      junk.append(line.strip()[:120])
      continue
    got = m.group(1).upper()
    if got in ids and got not in affirmed:
      affirmed.append(got)
    elif got not in ids:
      junk.append(line.strip()[:120])
  return affirmed, junk

def distinct_check_rule(rule):
  """-> the refusals this channel applies to its own output."""
  why = []
  head = rule["head"]
  body = rule["body"]
  if head["sign"] != "-" or not atoms.is_equality_predicate(head["atom"][0]):
    why.append("the conclusion must be a negative equality")
  if len(head["atom"]) != 3:
    why.append("the equality must have exactly two terms")
  else:
    a, b = head["atom"][1], head["atom"][2]
    if a == b:
      why.append("the two terms are the same")
    if not (_is_ground_name(a) and _is_ground_name(b)):
      why.append("a term of the equality is not a ground name")
    names = set()
    for lit in body:
      atom = lit["atom"]
      if lit["sign"] != "+" or str(atom[0]) != "isa" or len(atom) != 3:
        why.append("every premise must be a positive `isa` guard")
        continue
      names.add(atom[2])
    if names != {a, b}:
      why.append("the class guards must be about exactly those two terms")
    labels = set(str(l["atom"][1]) for l in body
                 if len(l["atom"]) == 3)
    if len(labels) != 1:
      why.append("the two guards must use the same class")
  if len(body) != 2:
    why.append("a distinctness rule has exactly two guards")
  return why

def run_distinctness(view, candidates, question_text, respond, case_id, start_index=1):
  """-> the record for this case's distinctness channel.  One call at most."""
  pairs, refused = distinct_eligible_pairs(view, candidates, question_text)
  rec = {"version": VERSION, "eligible": pairs, "not_eligible": refused,
         "asked": False, "rules": [], "system_prompt_name":
             DISTINCT_SYSTEM_PROMPT_NAME,
         "system_prompt_sha256": distinct_system_prompt_sha256()}
  if not pairs:
    rec["why"] = "no question clause needs a negative equality between two "\
                 "displayed named things"
    return rec
  split = view.get("_split") or {}
  message = distinct_user_message(split.get("passage") or view.get("input_text") or "",
                         question_text, pairs)
  rec.update({"asked": True, "user_message": message,
              "user_message_sha256": hashlib.sha256(
                  message.encode()).hexdigest()})
  text, note = respond("distinct", "%s/d" % case_id, message)
  affirmed, junk = distinct_parse_reply(text, pairs)
  rec.update({"raw": text, "llm_note": note, "affirmed": affirmed,
              "unreadable_lines": junk})
  n = start_index
  for row in pairs:
    if row["id"] not in affirmed:
      continue
    try:
      rule = build_rule(row, "R%d" % n)
    except ValueError as e:
      rec.setdefault("refused_rules", []).append(
          {"pair": row["id"], "why": str(e)})
      continue
    bad = distinct_check_rule(rule)
    if bad:
      rec.setdefault("refused_rules", []).append(
          {"pair": row["id"], "printed": rule["printed"], "why": bad})
      continue
    rule["distinctness_pair"]["pair_id"] = row["id"]
    rec["rules"].append(rule)
    n += 1
  rec["next_index"] = n
  return rec

def _label_slot(atom):
  return atoms.LABEL_SLOT.get(str(atom[0]))

def _is_open(term):
  return isinstance(term, str) and term.startswith("?") \
      and not term.startswith("?:")

def _shape(atom):
  """A predicate-and-label key that survives the display's own variables."""
  slot = _label_slot(atom)
  parts = [str(atom[0])]
  for i, a in enumerate(atom[1:]):
    if i == slot:
      parts.append(str(a))
  return json.dumps(parts)

def source_rule_shapes(source_rules):
  """The rules the passage already states, canonically."""
  return set(source_rule_keys(source_rules or ()))

def _rule_atoms(a_atom, b_atom):
  """The two atoms with their open positions named by one rule variable."""
  names, out = {}, []
  for atom in (a_atom, b_atom):
    got = [atom[0]]
    slot = _label_slot(atom)
    seen = 0
    for i, arg in enumerate(atom[1:]):
      if i == slot:
        got.append(arg)
        continue
      if _is_open(arg):
        names.setdefault(seen, "?X%d" % (len(names) + 1))
        got.append(names[seen])
      else:
        got.append(arg)
      seen += 1
    out.append(got)
  return out[0], out[1]

def _build(row, rule_id):
  a_atom, b_atom = _rule_atoms(row["a"], row["b"])
  rule = {"rule_id": rule_id,
          "body": [{"sign": "+", "atom": a_atom}],
          "head": {"sign": "-", "atom": b_atom},
          "premises": 1, "origin": ORIGIN, "warnings": [], "variants": [],
          "head_sign": "-", "negative_conclusion": True,
          "candidate_matches": [
              {"literal": atoms.printed_atom(a_atom), "candidate": row["a_id"],
               "role": "PREMISE", "priority_cost": 0,
               "match_kind": "negative_relation_channel"},
              {"literal": atoms.printed_atom(b_atom, negated=True),
               "candidate": row["b_id"], "role": "CONSEQUENCE",
               "priority_cost": 0,
               "match_kind": "negative_relation_channel"}],
          "atoms_matching_no_candidate": [], "rule_priority_cost": 0,
          "role_fit": {"fits": True, "body_fits": True, "head_fits": True,
                       "body_roles": ["PREMISE"],
                       "head_role": "CONSEQUENCE"},
          "negative_relation_pair": {
              "a": row["a"], "b": row["b"], "a_id": row["a_id"],
              "b_id": row["b_id"],
              "question_clauses": row.get("question_clauses"),
              "stated_by": row.get("stated_by")}}
  rule["llm_variables"] = [t for t in _tokens(a_atom)
                           + _tokens(b_atom) if str(t).startswith("?X")]
  rule["llm_variables"] = sorted(set(rule["llm_variables"]))
  rule = to_rule({"body": [(l["sign"], l["atom"]) for l in rule["body"]],
                      "head": (rule["head"]["sign"], rule["head"]["atom"])}
                     ) if False else rule
  rule["canonical"] = canonical(rule)
  rule["printed"] = printed_rule(rule)
  return rule

def negative_system_prompt():
  with open(os.path.join(PROMPT_DIR, "%s.txt" % NEGATIVE_SYSTEM_PROMPT_NAME)) as f:
    return f.read()

def negative_system_prompt_sha256():
  return hashlib.sha256(negative_system_prompt().encode()).hexdigest()

def negative_eligible_pairs(view, candidates, source_rules=()):
  """-> (pairs, refusals).  Every refusal names the condition that failed."""
  asked = negative_is_asked(view)
  stated = stated_by_the_passage(view)
  known = source_rule_shapes(source_rules)
  rows, refused = [], []
  groups = candidates["groups"]
  for b in groups:
    b_atom = b["atom"]
    if atoms.is_equality_predicate(str(b_atom[0])) \
            or atoms.is_control_predicate(str(b_atom[0])):
      continue
    b_key = _shape(b_atom)
    if b_key not in asked:
      continue
    for a in groups:
      a_atom = a["atom"]
      if a["id"] == b["id"]:
        continue
      if atoms.is_equality_predicate(str(a_atom[0])) \
              or atoms.is_control_predicate(str(a_atom[0])):
        continue
      row = {"a_id": a["id"], "b_id": b["id"], "a": a_atom, "b": b_atom,
             "question_clauses": asked[b_key],
             "cost": (a.get("cost") or a.get("priority_cost") or 0)
             + (b.get("cost") or b.get("priority_cost") or 0)}
      a_key = _shape(a_atom)
      if a_key not in stated:
        row["why_refused"] = ("the passage does not state the premise; "
                              "it appears only in a question or a "
                              "population clause")
        refused.append(row)
        continue
      if a_key == b_key:
        row["why_refused"] = "the premise and the conclusion are the " \
                             "same atom"
        refused.append(row)
        continue
      if not same_participants(a_atom, b_atom):
        row["why_refused"] = ("the two atoms do not name the same "
                              "participants in the same order")
        refused.append(row)
        continue
      rule = _build(row, "N0")
      if canonical(rule) in known:
        row["why_refused"] = "the passage already states this rule"
        refused.append(row)
        continue
      row["stated_by"] = stated[a_key]
      rows.append(row)
  rows.sort(key=lambda r: (r["cost"], r["a_id"], r["b_id"]))
  for i, row in enumerate(rows[:MAX_PAIRS], start=1):
    row["id"] = "%s%d" % (NEGATIVE_RULE_PREFIX, i)
  return rows[:MAX_PAIRS], refused

def negative_check_rule(rule):
  """-> the refusals this channel applies to its own output."""
  why = []
  head, body = rule["head"], rule["body"]
  if head["sign"] != "-":
    why.append("the conclusion must be negative")
  if atoms.is_equality_predicate(str(head["atom"][0])):
    why.append("equality belongs to the distinctness channel")
  if len(body) != 1 or body[0]["sign"] != "+":
    why.append("the body must be one positive atom")
  if json.dumps(head["atom"]) == json.dumps(body[0]["atom"]):
    why.append("the conclusion is the negation of its own premise")
  body_vars = set(atom_variables(body[0]["atom"],
                                     rule_variables(rule)))
  free = set(atom_variables(head["atom"],
                                rule_variables(rule))) - body_vars
  if free:
    why.append("the conclusion uses %s, which the body never binds"
               % ", ".join(sorted(free)))
  return why

def negative_user_message(passage, question, pairs):
  lines = ["PASSAGE:", passage, "", "QUESTION:", question, "",
           "POSSIBLE NEGATIVE RULES:", ""]
  for row in pairs:
    rule = _build(row, row["id"])
    lines.append("%-4s %s" % (row["id"], rule["printed"]))
  lines += ["", "Select only normally sound negative implications."]
  return "\n".join(lines)

def negative_parse_reply(text, pairs):
  """-> (selected ids, unreadable lines, said none).  Silence selects none."""
  ids = set(row["id"] for row in pairs)
  selected, junk, none = [], [], False
  for line in (text or "").splitlines():
    if not line.strip():
      continue
    if NONE_LINE.match(line):
      none = True
      continue
    m = NEGATIVE_LINE.match(line)
    if not m:
      junk.append(line.strip()[:120])
      continue
    got = m.group(1).upper()
    if got in ids and got not in selected:
      selected.append(got)
    elif got not in ids:
      junk.append(line.strip()[:120])
  return selected, junk, none

def run_negative_relation(view, candidates, passage, question, respond, case_id,
        start_index=1, source_rules=()):
  """One selection call.  -> the rules built from the ids it selected."""
  pairs, refused = negative_eligible_pairs(view, candidates, source_rules)
  got = {"version": VERSION, "system_prompt_name": NEGATIVE_SYSTEM_PROMPT_NAME,
         "system_prompt_sha256": negative_system_prompt_sha256(),
         "eligible": [dict((k, v) for k, v in row.items() if k != "cost")
                      for row in pairs],
         "not_eligible": refused[:60],
         "not_eligible_total": len(refused),
         "asked": False, "rules": [], "selected": [], "unselected": [],
         "next_index": start_index}
  if not pairs:
    got["why_not_asked"] = "no pair is eligible"
    return got
  message = negative_user_message(passage, question, pairs)
  got.update({"asked": True, "user_message": message,
              "user_message_sha256": hashlib.sha256(
                  message.encode()).hexdigest()})
  text, note = respond("negative", "%s/negative" % case_id, message)
  selected, junk, none = negative_parse_reply(text, pairs)
  got.update({"raw": text, "llm_note": note, "unreadable_lines": junk,
              "said_none": none, "selected": selected,
              "unselected": [row["id"] for row in pairs
                             if row["id"] not in set(selected)]})
  rules, refusals = [], []
  n = start_index - 1
  for row in pairs:
    if row["id"] not in set(selected):
      continue
    n += 1
    rule = _build(row, "R%d" % n)
    why = negative_check_rule(rule)
    if why:
      n -= 1
      refusals.append({"pair": row["id"], "printed": rule["printed"],
                       "why": why})
      continue
    rules.append(rule)
  got.update({"rules": rules, "rule_ids": [r["rule_id"] for r in rules],
              "mechanical_refusals": refusals, "next_index": n + 1})
  return got

