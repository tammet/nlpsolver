"""The normalization fallback (`-fallback_norm`).

When the initial attempt leaves the question unresolved, the same Stage-1/Stage-2
parse is converted a second time with a set of token and shape normalizations
switched on, and gk is called once more.  No LLM call is made.  A definite
answer here stops every later route and names itself `fallback_norm` in
`answered_by`.

Two kinds of change ride in this conversion:

  * normalizations, which do not change what the text says.  A hyphen fold, a
    letter-case fold, a comparative name reduced to its base adjective: each
    fires only when the case itself carries both variants, so no lexical claim
    is made about a word the case does not use.
  * question rewrites the text licenses.  The cued `xor -> or` rewrite fires
    only when the question's own words say "or both" (or another cue); the
    apposition presupposition fires only when Stage 1's question text shows
    the class in an apposition.

The exclusive reading is always submitted before the inclusive one.  An
uncued `xor` is read exclusively first, and only an Unknown from that reading
lets the inclusive reading run.  Reversing the order would let an inclusive
`True.` override a FOLIO-style `False.` on a question where both disjuncts
hold.

Cost: at most two gk calls.  A case whose conversion does not drift and whose
question carries no uncued `xor` costs one converter run and no gk call.

Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com), Apache License 2.0
"""

import json
import re

import globals as _g


# --------------------------------------------------------------------------
# Configuration.  These are module-level booleans, not CLI flags: a flag would
# invite switching a normalization on in the initial attempt, whose behaviour under
# always-on normalizations was never measured.  An experiment that wants one
# off edits this block for one arm.
# --------------------------------------------------------------------------

QUNIV = True      # keep a generic universal question universal (F137, F163, F199)
DASHNORM = True   # hyphen/space fold when both variants occur (F32, F33)
COMPNORM = True   # comparative relation name -> base form (F115)
LISTPREP = True   # in/include -> on for list-naming objects (F13)
SINGROLE = True   # singularize bare plural eventprop values
CASENORM = True   # letter-case fold, same predicate position, both variants present (core 1242, 1243)
QOR_CUED = True   # question-body xor -> or when the text carries an inclusive cue (MLE 34)
QPRESUP = True    # assert an apposed typing from the question text (MLE 12)
INCLUSIVE_SECOND = True  # after an Unknown, retry an uncued xor question inclusively (MLE 283, 284)


# The internal option key each configuration boolean switches on for the
# fallback conversion, and nothing else.  `run` saves and restores every key
# here, so the initial attempt's own conversion is never affected.
_KEYS = {
    "QUNIV": "quniv_flag",
    "DASHNORM": "dashnorm_flag",
    "COMPNORM": "compnorm_flag",
    "LISTPREP": "listprep_flag",
    "SINGROLE": "singrole_flag",
    "CASENORM": "casenorm_flag",
    "QOR_CUED": "qor_flag",
    "QPRESUP": "qpresup_flag",
}

ALL_KEYS = tuple(sorted(set(_KEYS.values())))


def enabled_names():
  """The names of the normalizations this fallback runs with."""
  return [n for n in sorted(_KEYS) if globals().get(n)]


def _switch_on():
  """Set the option keys the configuration turns on; -> the saved values."""
  saved = {k: _g.options.get(k) for k in ALL_KEYS}
  for k in ALL_KEYS:
    _g.options[k] = False
  for name, key in _KEYS.items():
    if globals().get(name):
      _g.options[key] = True
  return saved


def _restore(saved):
  for k, v in saved.items():
    _g.options[k] = v


# ==========================================================================
# casenorm: fold letter-case variants of one token in one predicate position
# ==========================================================================

# The argument positions a class or property name occupies.  A value is folded
# only against another value in the SAME position, so "Ailton" as an isa
# instance (argument 2) never folds onto "ailton" as an isa class (argument 1).
_CASE_POSITIONS = (("isa", 1), ("has property", 1), ("is rel2", 1))


def _case_skip(s):
  """Tokens no fold may touch: variables, entities, meta tokens, skolems."""
  return (not isinstance(s, str) or not s
          or s.startswith(("?:", "#:", "$"))
          or re.match(r"^sk\d", s) is not None)


def _case_scan(node, out):
  """Collect (position, token) pairs from one clause tree."""
  if not isinstance(node, list) or not node:
    return
  head = node[0]
  if isinstance(head, str):
    base = head.lstrip("-")
    for pred, idx in _CASE_POSITIONS:
      if base == pred and len(node) > idx and isinstance(node[idx], str):
        if not _case_skip(node[idx]):
          out.add((pred, node[idx]))
    if base == "eventprop" and len(node) >= 3 and isinstance(node[2], str):
      if not _case_skip(node[2]):
        out.add(("eventprop", node[2]))
  for x in node:
    if isinstance(x, list):
      _case_scan(x, out)


def _case_apply(node, fold):
  """Rewrite the collected positions per `fold`; every other string is left."""
  if not isinstance(node, list) or not node:
    return node
  out = list(node)
  head = out[0]
  if isinstance(head, str):
    base = head.lstrip("-")
    for pred, idx in _CASE_POSITIONS:
      if base == pred and len(out) > idx and isinstance(out[idx], str):
        out[idx] = fold.get((pred, out[idx]), out[idx])
    if base == "eventprop" and len(out) >= 3 and isinstance(out[2], str):
      out[2] = fold.get(("eventprop", out[2]), out[2])
  return [_case_apply(x, fold) if isinstance(x, list) else x for x in out]


def apply_casenorm(result):
  """Fold letter-case variants of one token inside one predicate position.

  "Estonian city" and "estonian city" both appear as isa classes, so both
  become "estonian city" and the rule meets the question (core 1242, 1243).
  Both variants must be present, as for the hyphen fold: a token the case
  spells only one way is left exactly as the case spells it.

  What keeps an entity name out of the fold is the position, not the `#:`
  test below: this pass runs before `apply_una` marks entities, so an entity
  name is still bare here.  "Ailton" as an isa instance sits in argument 2,
  which no position in `_CASE_POSITIONS` names, so it never folds onto
  "ailton" as an isa class in argument 1.  Modifies `result` in place.
  """
  if not _g.options.get("casenorm_flag", False):
    return result
  seen = set()
  for c in result:
    if isinstance(c, dict):
      for k in ("@logic", "@question"):
        _case_scan(c.get(k), seen)
  groups = {}
  for pos, tok in seen:
    groups.setdefault((pos, tok.lower()), set()).add(tok)
  fold = {}
  for (pos, low), variants in groups.items():
    if len(variants) < 2:
      continue                        # only one spelling in this position
    for v in variants:
      if v != low:
        fold[(pos, v)] = low
  if not fold:
    return result
  for c in result:
    if isinstance(c, dict):
      for k in ("@logic", "@question"):
        if isinstance(c.get(k), list):
          c[k] = _case_apply(c[k], fold)
  return result


# ==========================================================================
# The question rewrites the text licenses
# ==========================================================================

# An inclusive reading is licensed by the question's own words, not by the
# shape of the formula.  These are the cues that license it.
_INCLUSIVE_CUES = ("or both", "at least one", "one or both", "and/or",
                   "either or both", "possibly both")


def _question_text(s1_json):
  """The raw text of the case's question unit(s), lowercased.

  Stage 1 marks a question unit `type: "query"`; where it does not, a raw
  sentence ending in "?" is the question.  Returns "" when neither is found,
  and every trigger below then reads as absent — a rewrite never fires on
  evidence the case does not carry.
  """
  out = []
  for pkg in (s1_json or []):
    if not isinstance(pkg, dict):
      continue
    raw = pkg.get("raw") if isinstance(pkg.get("raw"), str) else ""
    units = pkg.get("units") or []
    is_q = any(isinstance(u, dict) and u.get("type") == "query" for u in units)
    if is_q or raw.strip().endswith("?"):
      out.append(raw)
      for u in units:
        if isinstance(u, dict) and isinstance(u.get("text"), str):
          out.append(u["text"])
  return " ".join(out).lower()


def has_inclusive_cue(s1_json):
  """Does the question's wording license reading a disjunction inclusively?"""
  text = _question_text(s1_json)
  return any(cue in text for cue in _INCLUSIVE_CUES)


def apposed_classes(s1_json):
  """The class words the question text presents in an apposition.

  "Janet, an employee, ..." -> {"employee"}.  Only these may be asserted as
  presuppositions; a class that appears as a plain conjunct of the question
  ("Is Ted a student and employed?") is part of what is being asked and is
  not here.
  """
  text = _question_text(s1_json)
  out = set()
  for m in re.finditer(r",\s*(?:an?|the)\s+([a-z][a-z _-]*?)\s*[,?]", text):
    out.add(m.group(1).strip())
  for m in re.finditer(r"\(\s*(?:an?|the)\s+([a-z][a-z _-]*?)\s*\)", text):
    out.add(m.group(1).strip())
  return {c for c in out if c}


def _rewrite_xor_to_or(frm):
  if not isinstance(frm, list) or not frm:
    return frm
  head = frm[0]
  if head == "xor":
    return ["or"] + [_rewrite_xor_to_or(x) for x in frm[1:]]
  return [_rewrite_xor_to_or(x) if isinstance(x, list) else x for x in frm]


def _is_named_const(s):
  """A plain named constant: not a variable, meta token, or skolem."""
  return (isinstance(s, str) and s != ""
          and not s.startswith(("?", "$", "#", "sk"))
          and not s[0].isdigit())


def _presup_atoms(body, allowed=None):
  """Ground ["isa", CLASS, CONST] conjuncts a question body only presupposes.

  `allowed` is the set of class words Stage 1's question text shows in an
  apposition.  A conjunct whose class is not in that set is part of what is
  being asked, not a presupposition, and is never returned — so
  "Is Ted a student and employed?" yields nothing.  With `allowed` None the
  provenance is unavailable and nothing fires.

  Returns [] when the body is not a conjunction or when every conjunct is such
  an isa (then the typing IS the question and must not be asserted)."""
  b = body
  if isinstance(b, list) and len(b) >= 3 and b[0] == "exists":
    b = b[2]
  if not (isinstance(b, list) and b and b[0] == "and"):
    return []
  conj = b[1:]
  allowed = allowed or set()
  pres = [c for c in conj
          if isinstance(c, list) and len(c) >= 3 and c[0] == "isa"
          and isinstance(c[1], str) and _is_named_const(c[2])
          and str(c[1]).strip().lower() in allowed]
  if not pres or len(pres) == len(conj):
    return []
  return pres


def _transform_question_node(qnode, hyps, s1_json=None, notes=None):
  """Rewrite one ["question", BODY] node, where the text licenses it.

  `hyps` collects presupposition atoms only.  The hypothetical reading of a
  conditional question is NOT applied here: it needs an isolated theory, which
  `fallback_hyp` builds.
  """
  opts = _g.options
  if not (isinstance(qnode, list) and len(qnode) >= 2 and qnode[0] == "question"):
    return qnode
  body = qnode[1]
  world = None
  if (isinstance(body, list) and len(body) >= 3 and body[0] == "holds"):
    world = body[1]
    body = body[2]
  if opts.get("qor_flag", False) and has_inclusive_cue(s1_json):
    new_body = _rewrite_xor_to_or(body)
    if new_body != body and notes is not None:
      notes.append("qor: the question's words carry an inclusive cue")
    body = new_body
  if opts.get("qpresup_flag", False):
    allowed = apposed_classes(s1_json)
    for atom in _presup_atoms(body, allowed):
      hyps.append(atom)
      if notes is not None:
        notes.append("qpresup: %r is apposed in the question text"
                     % (atom[1],))
  if world is not None:
    body = ["holds", world, body]
  return ["question", body]


def _walk_package(pkg, hyps, s1_json=None, notes=None):
  """Find and rewrite the question node inside one package tree."""
  if not isinstance(pkg, list) or not pkg:
    return pkg
  if pkg[0] == "question":
    return _transform_question_node(pkg, hyps, s1_json, notes)
  if pkg[0] == "and":
    return ["and"] + [_walk_package(x, hyps, s1_json, notes) for x in pkg[1:]]
  if pkg[0] == "holds" and len(pkg) >= 3:
    return [pkg[0], pkg[1], _walk_package(pkg[2], hyps, s1_json, notes)]
  return pkg


def apply_question_transforms(logic, fixes=None, s1_json=None, notes=None):
  """Apply the text-licensed question rewrites to the Stage-2 tree.

  Input/output: the top-level ["and", ["@id", SID, PKG], ...] tree.  For each
  rewritten question a hypothesis package ["@id", SID+"h", ["holds", "W0",
  H]] is appended (H = the conjunction of collected hypothesis formulas).
  With both option keys off the function returns its input unchanged, so the
  initial attempt never enters it.
  """
  opts = _g.options
  if not (opts.get("qor_flag", False) or opts.get("qpresup_flag", False)):
    return logic
  if not (isinstance(logic, list) and logic and logic[0] == "and"):
    return logic
  out = ["and"]
  extra = []
  changed = False
  for item in logic[1:]:
    if (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"):
      sid, pkg = item[1], item[2]
      hyps = []
      new_pkg = _walk_package(pkg, hyps, s1_json, notes)
      if new_pkg != pkg:
        changed = True
      if hyps:
        h = hyps[0] if len(hyps) == 1 else (["and"] + hyps)
        extra.append(["@id", str(sid) + "h", ["holds", "W0", h]])
        changed = True
      out.append([item[0], sid, new_pkg] + item[3:])
    else:
      out.append(item)
  out.extend(extra)
  if changed and fixes is not None:
    fixes.append("logconvert: question transforms (qor/qpresup)")
  return out


def has_question_xor(logic):
  """Does some question body contain an ["xor", ...]?"""
  def find(node):
    if not isinstance(node, list) or not node:
      return False
    if node[0] == "question" and len(node) >= 2:
      return "xor" in str(node[1])
    return any(find(x) for x in node[1:] if isinstance(x, list))
  return find(logic) if isinstance(logic, list) else False


def _walk_inclusive(pkg):
  if not isinstance(pkg, list) or not pkg:
    return pkg
  if pkg[0] == "question" and len(pkg) >= 2:
    return ["question", _rewrite_xor_to_or(pkg[1])] + pkg[2:]
  if pkg[0] == "and":
    return ["and"] + [_walk_inclusive(x) for x in pkg[1:]]
  if pkg[0] == "holds" and len(pkg) >= 3:
    return [pkg[0], pkg[1], _walk_inclusive(pkg[2])]
  return pkg


def inclusive_theory(logic):
  """The same tree with every question-body xor read inclusively.

  Submitted only after the exclusive reading has run and returned Unknown.
  """
  if not (isinstance(logic, list) and logic and logic[0] == "and"):
    return logic
  out = ["and"]
  for item in logic[1:]:
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      out.append([item[0], item[1], _walk_inclusive(item[2])] + item[3:])
    else:
      out.append(item)
  return out


# ==========================================================================
# The runner
# ==========================================================================

def _key_of(c):
  return (json.dumps({k: v for k, v in c.items() if k != "@nl"},
                     sort_keys=True) if isinstance(c, dict)
          else json.dumps(c))


def _convert(theory, s1_json):
  """Convert one theory with the fallback's options on; -> the clause list."""
  import logconvert
  import semnormalize
  logic = logconvert.rawlogic_convert(theory, s1_json, fixes=[])
  if logic is None:
    return None
  if not _g.options.get("nosemnormal_flag"):
    logic = semnormalize.sem_normalize_clauses(logic)
  return logic


def _submit(theory, logic, s1_json, text, options, reading, record):
  """One gk call on an already-converted theory; -> the processed answer."""
  import prover
  import solve
  from procproofs import process_proof
  sub = {"reading": reading,
         "clauses": solve._build_clauses_with_nl(logic, s1_json)}
  record["submissions"].append(sub)
  proof = prover.call_prover(logic, s1_json=s1_json)
  sub["gk_result"] = proof
  if not (isinstance(proof, str) and proof and not proof.startswith("Error")):
    sub["stopped_at"] = "gk returned no usable result"
    return None, None
  answer = process_proof(proof, text=text, s1_json=s1_json, s2_json=theory,
                         logic=logic, options=options)
  sub["answer"] = str(answer or "").split("\n")[0]
  return answer, proof


def run(s1_json, s2_json, text, base_logic, options):
  """Convert the same parse with the normalizations on and ask gk again.

  -> {"answered", "answer", "logic", "proof", "record"}.  The record names the
  normalizations that were on, every submission with its clauses, its diff
  against the initial attempt's clause set, its raw gk result and its answer, so a
  recovery can be read back without re-running anything.
  """
  import solve
  record = {"fallback": "fallback_norm",
            "normalizations": enabled_names(),
            "submissions": [],
            "answered": False}
  out = {"answered": False, "answer": None, "logic": None, "proof": None,
         "record": record}
  saved = _switch_on()
  try:
    logic = _convert(s2_json, s1_json)
    if logic is None:
      record["stopped_at"] = "the converter returned nothing"
      return out
    base_keys = {_key_of(c) for c in (base_logic or [])}
    now_keys = {_key_of(c) for c in logic}
    diff = {"added": [c for c in logic if _key_of(c) not in base_keys],
            "removed": [c for c in (base_logic or [])
                        if _key_of(c) not in now_keys]}
    drifted = bool(diff["added"] or diff["removed"])
    answer = proof = None
    if drifted:
      answer, proof = _submit(s2_json, logic, s1_json, text, options,
                              "exclusive", record)
      record["submissions"][-1]["clause_diff"] = diff
    else:
      record["note"] = ("the conversion is identical to the front door's; "
                        "no gk call was made for the exclusive reading")

    # The inclusive reading of an UNCUED xor, second and only after an
    # Unknown.  The exclusive reading is the primary one; letting the
    # inclusive reading run first would override a `False.` that holds
    # because both disjuncts are true.
    if (INCLUSIVE_SECOND and solve._unresolved(answer)
        and has_question_xor(s2_json) and not has_inclusive_cue(s1_json)):
      theory = inclusive_theory(s2_json)
      inc_logic = _convert(theory, s1_json)
      if inc_logic is None:
        record["submissions"].append(
            {"reading": "inclusive",
             "stopped_at": "the inclusive theory did not convert"})
      else:
        inc, inc_proof = _submit(theory, inc_logic, s1_json, text, options,
                                 "inclusive", record)
        if not solve._unresolved(inc):
          answer, logic, proof = inc, inc_logic, inc_proof
          record["answered_by_reading"] = "inclusive"

    if solve._unresolved(answer):
      return out
    record["answered"] = True
    record.setdefault("answered_by_reading", "exclusive")
    record["answer"] = str(answer or "").split("\n")[0]
    out.update({"answered": True, "answer": answer, "logic": logic,
                "proof": proof})
    return out
  finally:
    _restore(saved)
