"""The hypothetical-reading fallback (`-fallback_hyp`).

Stage 2 encodes "If A, is B?" as ["question", ["implies", A, B]].  The
converter reads that materially, so the question is answered `True.` by
anything that refutes A, and left unresolved when nothing in the premises
settles A.  This fallback offers the other reading: assume A, ask B.

The assumption goes into an isolated theory — a copy of the premise packages
plus `hyp_<sid>` holding A in W0, with B as the question and the original
question package dropped.  Nothing is inserted into the ordinary premise set,
so the material reading the front door already produced is not disturbed and
no later route inherits the assumption.

The reading disagrees with FOLIO's vacuous-truth convention on a conditional
whose antecedent the premises refute: FOLIO calls such a question `True.`,
this reading answers whatever B follows from A.  The refutation pre-check
below exists for that case; it is off by default (see the configuration).

Cost: one gk call; two with the pre-check on.  Without a conditional
question the fallback stops before any gk call.

Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com), Apache License 2.0
"""

import globals as _g


# --------------------------------------------------------------------------
# Configuration.  A module-level boolean, not a CLI flag: see fallback_norm.
# --------------------------------------------------------------------------

REFUTATION_CHECK = False  # ask first whether the premises refute the antecedent
# Off (decided 2026-08-25).  The check returned False on 0 of 121 calls across
# FOLIO, MLE-100 and the held-out set; a refutable antecedent already makes
# the front door's material reading answer `True.`, so the fallback is not
# reached; and with it off MLE-100 gave identical answers at half the gk
# calls.  On, it costs one gk call per conditional question and guards one
# unobserved case: a refutation the front door missed under its time limit.


def _strip_normally(frm):
  if not isinstance(frm, list) or not frm:
    return frm
  if frm[0] == "normally" and len(frm) >= 2:
    return _strip_normally(frm[1])
  return [_strip_normally(x) if isinstance(x, list) else x for x in frm]


def conditional_questions(logic):
  """-> [(sid, antecedent, consequent)] for each ["question", ["implies", A, B]].

  The material reading is what the converter emits and stays primary.  This
  only reports where a hypothetical reading is available.
  """
  out = []
  if not (isinstance(logic, list) and logic and logic[0] == "and"):
    return out

  def find(node):
    if not isinstance(node, list) or not node:
      return None
    if node[0] == "question" and len(node) >= 2:
      body = node[1]
      if (isinstance(body, list) and len(body) >= 3 and body[0] == "holds"):
        body = body[2]
      if isinstance(body, list) and len(body) >= 3 and body[0] == "implies":
        return (_strip_normally(body[1]), body[2])
      return None
    if node[0] == "and":
      for x in node[1:]:
        got = find(x)
        if got:
          return got
    if node[0] == "holds" and len(node) >= 3:
      return find(node[2])
    return None

  for item in logic[1:]:
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      got = find(item[2])
      if got:
        out.append((str(item[1]), got[0], got[1]))
  return out


def hypothetical_theory(logic, sid, antecedent, consequent):
  """The isolated theory for the hypothetical reading of one question.

  A copy of the premise packages, plus the antecedent as a named local
  assumption `hyp_<sid>`, plus the consequent as the question.  The original
  question package is dropped, so the material reading is not also present.
  Nothing is inserted into the ordinary premise set.
  """
  out = ["and"]
  for item in (logic[1:] if isinstance(logic, list) else []):
    if (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"
        and str(item[1]) == sid):
      continue
    out.append(item)
  out.append(["@id", "hyp_" + sid, ["holds", "W0", antecedent]])
  out.append(["@id", sid, ["question", consequent]])
  return out


def refutation_theory(logic, sid, antecedent):
  """The theory that asks whether the premises refute the antecedent.

  If they do, the hypothetical reading is skipped: asserting a refuted
  antecedent makes the theory inconsistent, and gk does not conclude ex falso,
  so its search reports nothing useful (FOLIO 65, 73).
  """
  out = ["and"]
  for item in (logic[1:] if isinstance(logic, list) else []):
    if (isinstance(item, list) and len(item) >= 3 and item[0] == "@id"
        and str(item[1]) == sid):
      continue
    out.append(item)
  out.append(["@id", sid, ["question", antecedent]])
  return out


def run(s1_json, s2_json, text, base_logic, options):
  """Try the hypothetical reading of the case's first conditional question.

  Runs with `fallback_norm`'s normalizations on, so a case needing both a
  normalization and this reading is answered here.

  -> {"answered", "answer", "logic", "proof", "record"}.
  """
  import fallback_norm
  import solve
  record = {"fallback": "fallback_hyp",
            "refutation_check": REFUTATION_CHECK,
            "submissions": [],
            "answered": False}
  out = {"answered": False, "answer": None, "logic": None, "proof": None,
         "record": record}
  pairs = conditional_questions(s2_json)
  if not pairs:
    record["stopped_at"] = "the question is not a conditional"
    return out
  sid, ante, cons = pairs[0]
  record["sid"] = sid

  saved = fallback_norm._switch_on()
  try:
    if REFUTATION_CHECK:
      refute = refutation_theory(s2_json, sid, ante)
      ref_logic = fallback_norm._convert(refute, s1_json)
      if ref_logic is not None:
        ref_answer, _ = fallback_norm._submit(refute, ref_logic, s1_json,
                                              text, options, "refutation",
                                              record)
        head = str(ref_answer or "").split("\n")[0].strip().lower()
        if head.startswith("false"):
          record["skipped"] = "the premises refute the antecedent"
          return out

    theory = hypothetical_theory(s2_json, sid, ante, cons)
    hyp_logic = fallback_norm._convert(theory, s1_json)
    if hyp_logic is None:
      record["stopped_at"] = "the isolated theory did not convert"
      return out
    answer, proof = fallback_norm._submit(theory, hyp_logic, s1_json, text,
                                          options, "hypothetical", record)
    if solve._unresolved(answer):
      return out
    record["answered"] = True
    record["answered_by_reading"] = "hypothetical"
    record["answer"] = str(answer or "").split("\n")[0]
    out.update({"answered": True, "answer": answer, "logic": hyp_logic,
                "proof": proof})
    return out
  finally:
    fallback_norm._restore(saved)
