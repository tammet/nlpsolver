"""Proof-local acceptance checks for critic and graph retranslations.

A later stage may answer where the canonical theory returned `Unknown`.  This
module inspects what that stage actually changed and what its proof actually
used, and returns an acceptance record.  It never looks at the accepted answer,
the expected answer, the dataset name or the case id: every check reads the
translation, the clauses and the proof.

The three policy levels share one reason-code vocabulary.  It was frozen
before the measurement, in a local archive that this repository does not track,
and `SEVERITY` below is its authoritative copy:

  permissive  current behaviour, except structural corruption is refused
  balanced    also refuses demonstrated information additions and losses
  strict      also cautions unresolved scope changes, refuses contradiction-
              dependent proofs

The module is deterministic and makes no LLM or prover call.  A missing field
or an unparsable proof yields CAUTION, never a silent ACCEPT.

`check(record, policy)` dispatches on the record's answering stage and returns:

  {"decision", "reasons", "answering_stage", "used_units", "changed_units",
   "evidence", "policy"}
"""

import json
import re

import lc_clausify

try:
  from lc_clausify import _safe_singularize_class as _sing_class
except Exception:                                   # pragma: no cover
  def _sing_class(c):
    return c

try:
  from data_synonyms import SOFT_SYNONYMS
except Exception:                                   # pragma: no cover
  SOFT_SYNONYMS = {}
try:
  from data_canonicals import CANONICALS
except Exception:                                   # pragma: no cover
  CANONICALS = {}

POLICIES = ("permissive", "balanced", "strict")
ACCEPT, CAUTION, REFUSE = "ACCEPT", "CAUTION", "REFUSE"
_ORDER = {ACCEPT: 0, CAUTION: 1, REFUSE: 2}

# code -> (permissive, balanced, strict).  Mirrors the frozen declaration.
SEVERITY = {
  "record_incomplete":                 (CAUTION, CAUTION, CAUTION),
  "structural_corruption":             (REFUSE,  REFUSE,  REFUSE),
  "critic_unrequested_unit_changed":   (ACCEPT,  REFUSE,  REFUSE),
  "critic_foreign_content_imported":   (ACCEPT,  REFUSE,  REFUSE),
  "critic_rule_premise_weakened":      (ACCEPT,  REFUSE,  REFUSE),
  "critic_unlicensed_exclusion_added": (ACCEPT,  REFUSE,  REFUSE),
  "critic_licensed_exclusion_added":   (ACCEPT,  ACCEPT,  ACCEPT),
  "critic_skeleton_change_matched":    (ACCEPT,  ACCEPT,  ACCEPT),
  "critic_skeleton_change_unmatched":  (ACCEPT,  ACCEPT,  CAUTION),
  "critic_scope_change_unresolved":    (ACCEPT,  ACCEPT,  CAUTION),
  "graph_modality_lost":               (ACCEPT,  REFUSE,  REFUSE),
  "graph_attitude_content_flattened":  (ACCEPT,  REFUSE,  REFUSE),
  "graph_negation_scope_lost":         (ACCEPT,  REFUSE,  REFUSE),
  "graph_quantifier_lost":             (ACCEPT,  REFUSE,  REFUSE),
  "graph_role_omitted":                (ACCEPT,  REFUSE,  REFUSE),
  "proof_uses_contested_literal":      (ACCEPT,  CAUTION, REFUSE),
}

# Structural operators and wrappers.  A symbol in this set is never "content".
OPERATORS = frozenset((
  "and", "or", "xor", "not", "implies", "iff", "forall", "exists",
  "holds", "question", "ask", "@id", "@p", "@time", "@ctxt", "$ctxt",
  "eventprop", "normally", "typically",
))

# The canonical event spine and its bookkeeping.  Present in every translation,
# so it carries no unit-specific content.
# Predicates the converter itself introduces.  They appear in a rerun because
# the pipeline put them there, not because the critic imported anything.
PIPELINE = frozenset((
  "is rel2", "=", "!=", "$measure", "$measure of", "$setof", "$theof",
  "$theof1", "$count", "have", "event", "eventprop", "$ans",
  ">", "<", ">=", "<=", "greater", "less",
))

# Degree and quantity vocabulary the converter supplies for gradable
# properties.  Not unit-specific content.
DEGREE_WORDS = frozenset((
  "none", "low", "moderate", "high", "very", "amount", "degree", "more",
  "less", "most", "least", "zero", "thing", "entity", "member",
))

# Function words: a preposition or determiner is structure, not content.
FUNCTION_WORDS = frozenset((
  "from", "to", "of", "in", "on", "at", "by", "with", "for", "as", "into",
  "over", "under", "near", "about", "between", "among", "through", "during",
  "a", "an", "the", "some", "any", "all", "each", "every", "this", "that",
  "is", "are", "was", "were", "be", "been", "has", "have", "had", "do",
  "does", "did", "and", "or", "not", "if", "then", "than", "there", "it",
))

SPINE = frozenset((
  "isa", "has type", "has actor", "has target", "has object", "has content",
  "has time", "has location", "has property", "has degree property",
  "has part", "has source", "has instrument", "has recipient",
  "has direction", "has destination", "has path", "has manner",
  "has beneficiary", "has result", "has accompaniment", "activity",
  "actuality", "$block",
))

CLASSIFIERS = frozenset((
  "typical", "capability", "necessity", "obligation", "volition",
  "intention", "expectation", "speech_act",
))

# Stage-1 modes that carry a modal or aspectual distinction.  `event` is the
# plain actual reading and is not itself a distinction to preserve.
MODAL_MODES = frozenset((
  "habitual", "capability", "necessity", "obligation", "volition",
  "intention", "expectation", "speech_act",
))

# Words that license a negation or an exclusivity in a unit's own English.
NEGATION_CUES = (
  "not", "no", "never", "none", "cannot", "n't", "without", "nobody",
  "nothing", "neither", "nor", "fails", "fail", "failed", "unable",
  "except", "lacks", "lacked", "lack", "other than", "rather than",
  "instead of", "does not", "did not", "is not", "are not", "was not",
  "were not",
)
EXCLUSIVITY_CUES = (
  "only", "sole", "solely", "exclusively", "just", "alone", "either",
  "neither", "nor", "exactly", "at most", "no other", "none other",
  "distinct", "different", "unlike", "apart from", "but not",
)

_WORD = re.compile(r"[a-z0-9']+")


def _has_cue(text, cues):
  """Whole-word cue test.  A substring test would let `Northern` match the
  negation cue `no` and `knowledge` match it too, licensing an exclusion the
  sentence never states."""
  toks = _WORD.findall((text or "").lower())
  joined = " " + " ".join(toks) + " "
  for c in cues:
    if " " in c:
      if (" " + c + " ") in joined:
        return True
    elif c in toks:
      return True
    elif c == "n't" and any(t.endswith("n't") for t in toks):
      return True
  return False


# --------------------------------------------------------------------------
# generic term helpers
# --------------------------------------------------------------------------

def _norm_symbol(s):
  """Lexical normalization shared with the converter: lower-case, underscores to
  spaces, singularize a class-like token, then fold a canonical.  Soft synonyms
  are NOT folded here -- they widen the allowed vocabulary instead (see
  `_synonyms`), because folding would merge two genuinely different symbols."""
  if not isinstance(s, str):
    return s
  t = s.strip().lower().replace("_", " ")
  try:
    t = _sing_class(t)
  except Exception:
    pass
  if not isinstance(t, str):
    return s.strip().lower()
  c = CANONICALS.get(t)
  return c if isinstance(c, str) else t


def _synonyms(word):
  """Soft synonyms of a normalized word, as normalized strings.  Used only to
  widen a unit's allowed vocabulary, never to rewrite a symbol."""
  out = set()
  for key in (word, word.replace(" ", "_")):
    for entry in SOFT_SYNONYMS.get(key) or ():
      w = entry[0] if isinstance(entry, (list, tuple)) and entry else entry
      if isinstance(w, str):
        out.add(_norm_symbol(w))
  return out


_VAR = re.compile(r"^[A-Z][a-zA-Z]?\d*$")


def _is_var(x):
  """Stage-2 variables: `?:X` in clause form, or a short capitalized token such
  as X, E1, Z3, Fv135 in package form.

  A world constant (W0, W1, ...) is NOT a variable, which is what
  `lc_clausify.looks_like_var` says as well.  This module keeps its own
  narrower pattern rather than calling that one: the broad sibling there also
  accepts a multi-letter word, so `Mary` and `English` would become variables
  and drop out of the vocabulary this module traces.  The two agree on every
  token they both classify; only the range differs.

  """
  if not isinstance(x, str):
    return False
  if x.startswith("?:"):
    return True
  if lc_clausify.is_world_constant(x):
    return False
  return bool(_VAR.match(x))


def canon(node, env=None, depth=0):
  """Canonical form: bound variables renamed positionally, `and`/`or` argument
  order removed.  Two packages that differ only by ordering or by a consistent
  renaming canonicalize equal."""
  env = {} if env is None else env
  if isinstance(node, str):
    return env.get(node, node)
  if not isinstance(node, list) or not node:
    return node
  h = node[0]
  if h in ("forall", "exists") and len(node) >= 3:
    e2 = dict(env)
    e2[node[1]] = "_v%d" % depth
    return [h, "_v%d" % depth, canon(node[2], e2, depth + 1)]
  if h in ("and", "or"):
    parts = [canon(x, env, depth) for x in node[1:]]
    return [h] + sorted(parts, key=lambda p: json.dumps(p, sort_keys=True))
  return [h] + [canon(x, env, depth) for x in node[1:]]


def atoms(node, out=None):
  """Every atom (a list whose head is a string) in the tree."""
  out = [] if out is None else out
  if isinstance(node, list) and node and isinstance(node[0], str):
    out.append(node)
    for x in node[1:]:
      atoms(x, out)
  elif isinstance(node, list):
    for x in node:
      atoms(x, out)
  return out


def heads(node):
  return set(a[0].lstrip("-") for a in atoms(node) if isinstance(a[0], str))


def split_units(stage2):
  """{unit_id: package} from a Stage-2 tree `["and", ["@id","S1",PKG], ...]`."""
  out = {}
  if not isinstance(stage2, list):
    return out
  for item in stage2[1:] if stage2 and stage2[0] == "and" else [stage2]:
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      out[item[1]] = item[2]
  return out


def question_units(stage2):
  """Unit ids whose package is the question rather than a premise."""
  out = set()
  for uid, pkg in split_units(stage2).items():
    for a in atoms(pkg):
      if a[0] in ("question", "ask"):
        out.add(uid)
        break
  return out


def _content_symbols(pkg):
  """Content symbols of a package: predicate names that are not operators or
  spine, plus class arguments of `isa`, plus non-variable constants."""
  syms = set()
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h not in OPERATORS and h not in SPINE and h not in CLASSIFIERS \
       and h not in PIPELINE and not h.startswith("$"):
      syms.add(_norm_symbol(h))
    if h == "isa" and len(a) >= 2 and isinstance(a[1], str):
      syms.add(_norm_symbol(a[1]))
    if h in ("has type", "has property", "has degree property") and len(a) >= 3:
      for x in a[2:4]:
        if isinstance(x, str) and not _is_var(x):
          syms.add(_norm_symbol(x))
    for x in a[1:]:
      # A world constant is not a variable and not content either: it names
      # the state an atom holds in.  The literal "W0" that used to stand here
      # covered only the first world; `is_world_constant` covers W1, W2 too.
      if isinstance(x, str) and not _is_var(x) and not x.startswith("$") \
         and not lc_clausify.is_world_constant(x) \
         and x not in ("none", "activity"):
        syms.add(_norm_symbol(x))
  out = set()
  for s in syms:
    if not isinstance(s, str) or not s:
      continue
    s = _strip_index(s)
    if s in FUNCTION_WORDS or s in PIPELINE or s in DEGREE_WORDS \
       or s.startswith(("http", "www.")):
      continue
    out.add(s)
  return out


_INDEX = re.compile(r"\s+\d+$")


def _strip_index(s):
  """`machine learning algorithm 2` -> `machine learning algorithm`: the trailing
  index is the entity-id counter the pipeline adds, not a content word."""
  return _INDEX.sub("", s).strip()


def _unit_vocabulary(s1_unit):
  """Allowed content for a unit: its Stage-1 inventory plus its own English."""
  voc = set()
  if not isinstance(s1_unit, dict):
    return voc
  for e in s1_unit.get("entities") or []:
    for k in ("id", "category", "type"):
      if isinstance(e.get(k), str):
        voc.add(_norm_symbol(e[k]))
  for a in s1_unit.get("actions") or []:
    if isinstance(a.get("root"), str):
      voc.add(_norm_symbol(a["root"]))
    if isinstance(a.get("mode"), str):
      voc.add(_norm_symbol(a["mode"]))
    for rk, rv in (a.get("roles") or {}).items():
      voc.add(_norm_symbol(rk))
      if isinstance(rv, str):
        voc.add(_norm_symbol(rv))
  for adj in s1_unit.get("adjectives") or []:
    for x in (adj if isinstance(adj, list) else [adj]):
      if isinstance(x, str):
        voc.add(_norm_symbol(x))
  for k in ("time", "time_prep", "location", "pre_state", "next_state"):
    v = s1_unit.get(k)
    if isinstance(v, str):
      voc.add(_norm_symbol(v))
  for d in s1_unit.get("definites") or []:
    if isinstance(d, str):
      voc.add(_norm_symbol(d))
    elif isinstance(d, dict):
      for x in d.values():
        if isinstance(x, str):
          voc.add(_norm_symbol(x))
  # the unit's own English, word by word, normalized the same way
  for w in _WORD.findall((s1_unit.get("text") or "").lower()):
    voc.add(_norm_symbol(w))
  # multi-word runs, so "water vapor" traces to its own sentence
  words = _WORD.findall((s1_unit.get("text") or "").lower())
  for n in (2, 3):
    for i in range(len(words) - n + 1):
      voc.add(_norm_symbol(" ".join(words[i:i + n])))
  voc = set(v for v in voc if isinstance(v, str) and v)
  wide = set(voc)
  for v in voc:
    wide.add(_strip_index(v))
    wide |= _synonyms(v)
  return set(w for w in wide if w)


def _traceable(sym, voc):   # noqa: E302
  """A symbol traces to a vocabulary when it, its parts, or its normalization
  are present.  Compound names are traceable when every part is."""
  if sym in voc:
    return True
  parts = [p for p in re.split(r"[ _]+", sym) if p]
  if len(parts) > 1 and all(p in voc for p in parts):
    return True
  return False


# --------------------------------------------------------------------------
# proof provenance
# --------------------------------------------------------------------------

def proof_steps(proof):
  """The step list, from either a bare list or a gk answer record."""
  if isinstance(proof, list):
    return proof
  if isinstance(proof, dict):
    for ans in proof.get("answers") or []:
      if not isinstance(ans, dict):
        continue
      for k in ("proof", "positive proof", "negative proof"):
        if isinstance(ans.get(k), list):
          return ans[k]
    for k in ("proof", "positive proof", "negative proof"):
      if isinstance(proof.get(k), list):
        return proof[k]
  return []


def proof_sources(proof):
  """Source clause names a proof leans on, from its `["in", NAME, ...]` steps."""
  names = set()
  for step in proof_steps(proof):
    if not isinstance(step, list) or len(step) < 2:
      continue
    reason = step[1]
    if isinstance(reason, list) and len(reason) > 1 and reason[0] == "in" \
       and isinstance(reason[1], str):
      names.add(reason[1])
  return names


def used_units(proof):
  """Source unit ids a proof used, e.g. `sent_S6` -> `S6`."""
  out = set()
  for n in proof_sources(proof):
    m = re.match(r"^(?:sent|entity)_(S\d+[a-z]?)", n)
    if m:
      out.add(m.group(1))
  return out


# --------------------------------------------------------------------------
# critic checks C1..C5
# --------------------------------------------------------------------------

def _implications(pkg):
  """Every `implies` node, as (canonical antecedent conjuncts, consequent)."""
  out = []
  for a in atoms(pkg):
    if a[0] == "implies" and len(a) >= 3:
      ante = a[1]
      conj = ante[1:] if isinstance(ante, list) and ante and ante[0] == "and" \
             else [ante]
      out.append(([canon(c) for c in conj], canon(a[2])))
  return out


def _negative_conclusions(pkg):
  """Negative conclusions, disjointness rules and exhaustive alternatives."""
  found = []
  for a in atoms(pkg):
    if a[0] == "implies" and len(a) >= 3:
      cons = a[2]
      if isinstance(cons, list) and cons and cons[0] == "not":
        found.append(("negative_conclusion", canon(cons)))
      if isinstance(cons, list) and cons and cons[0] in ("or", "xor"):
        found.append(("exhaustive_alternative", canon(cons)))
    if a[0] == "not" and len(a) >= 2:
      inner = a[1]
      if isinstance(inner, list) and inner and inner[0] not in OPERATORS:
        found.append(("negative_literal", canon(a)))
  return found


def _skeleton(pkg):
  """A structural fingerprint: quantifier nesting, negation scope, implication
  direction and connective shape."""
  q, neg, conn, imp_dir = [], [], [], []

  def walk(n, depth):
    if not isinstance(n, list) or not n or not isinstance(n[0], str):
      if isinstance(n, list):
        for x in n:
          walk(x, depth)
      return
    h = n[0]
    if h in ("forall", "exists"):
      q.append((h, depth))
      walk(n[2] if len(n) > 2 else None, depth + 1)
      return
    if h == "not" and len(n) >= 2:
      inner = n[1]
      wide = isinstance(inner, list) and inner and inner[0] in (
        "and", "or", "xor", "implies", "forall", "exists")
      n_lits = len([a for a in atoms(inner)
                    if a[0].lstrip("-") not in OPERATORS])
      neg.append(("wide" if wide or n_lits > 1 else "narrow", depth))
    if h == "implies":
      imp_dir.append(depth)
    if h in ("and", "or", "xor"):
      conn.append((h, len(n) - 1))
    for x in n[1:]:
      walk(x, depth + 1)

  walk(pkg, 0)
  return {"quantifiers": sorted(q), "negations": sorted(neg),
          "implications": len(imp_dir), "connectives": sorted(conn)}


def _finding_kinds(report):
  kinds = set()
  if not isinstance(report, dict):
    return kinds
  for f in report.get("findings") or []:
    if isinstance(f, dict):
      for k in ("kind", "type", "category", "finding"):
        if isinstance(f.get(k), str):
          kinds.add(f[k].strip().lower())
  return kinds


_SCOPE_FINDINGS = ("negation_scope", "quantifier", "scope", "question_form",
                   "polarity", "negation")


def check_critic(record, policy="balanced"):
  """Acceptance record for an answer produced by the critic rerun."""
  reasons, evidence = [], {}
  critic = record.get("critic") or {}
  rerun = critic.get("rerun") or {}
  orig2 = record.get("stage2")
  new2 = rerun.get("stage2")
  s1 = rerun.get("stage1") or record.get("stage1") or []
  proof = record.get("proof")

  if not isinstance(orig2, list) or not isinstance(new2, list):
    return _record(CAUTION, ["record_incomplete"],
                   "critic", set(), set(),
                   {"missing": "stage2 original or corrected"}, policy)

  o_units, n_units = split_units(orig2), split_units(new2)
  s1_units = {}
  for sent in s1 if isinstance(s1, list) else []:
    for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
      if isinstance(u, dict) and u.get("unit_id"):
        s1_units[u["unit_id"]] = u

  asked = set(critic.get("units_to_redo") or [])
  changed = set()
  for uid in set(o_units) | set(n_units):
    a = canon(o_units.get(uid))
    b = canon(n_units.get(uid))
    if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
      changed.add(uid)
  evidence["changed_units_recomputed"] = sorted(changed)
  evidence["units_to_redo"] = sorted(asked)
  evidence["unasked_units_recorded"] = sorted(critic.get("unasked_units") or [])

  used = used_units(proof) if proof else set()
  evidence["used_units"] = sorted(used)

  # ---- C1: a unit changed outside units_to_redo
  unasked = sorted(changed - asked)
  evidence["unasked_units_recomputed"] = unasked
  if unasked:
    reasons.append("critic_unrequested_unit_changed")
    evidence["C1"] = {"changed_outside_request": unasked}

  # only units the proof actually used can carry the answer
  relevant = sorted(changed & used) if used else sorted(changed)
  evidence["changed_and_used"] = relevant

  # ---- C2: foreign content imported into a corrected unit
  imports, shared = [], []
  qunits = question_units(orig2) | question_units(new2)
  for uid in relevant:
    voc = _unit_vocabulary(s1_units.get(uid))
    if not voc:
      continue
    before = _content_symbols(o_units.get(uid))
    after = _content_symbols(n_units.get(uid))
    for sym in sorted(after - before):
      if _traceable(sym, voc):
        continue
      where = sorted(v for v, u in s1_units.items()
                     if v != uid and _traceable(sym, _unit_vocabulary(u)))
      item = {"unit": uid, "symbol": sym, "traces_to_other_units": where,
              "question_units": sorted(qunits)}
      # a class present only in the question, pulled into a repaired rule
      if where and set(where) <= qunits:
        imports.append(item)
      elif not where:
        item["traces_nowhere"] = True
        imports.append(item)
      else:
        shared.append(item)
  if shared:
    evidence["C2_shared_with_other_premises"] = shared
  if imports:
    reasons.append("critic_foreign_content_imported")
    evidence["C2"] = imports

  # ---- C3: a rule premise weakened
  weakened = []
  for uid in relevant:
    o_imps, n_imps = _implications(o_units.get(uid)), _implications(n_units.get(uid))
    if o_imps and not n_imps:
      weakened.append({"unit": uid, "how": "conditioned statement became unconditional"})
      continue
    for oa, oc in o_imps:
      best = None
      for na, nc in n_imps:
        if json.dumps(nc, sort_keys=True) == json.dumps(oc, sort_keys=True):
          best = (na, nc)
          break
      if best is None:
        continue
      na, _ = best
      ok = [json.dumps(x, sort_keys=True) for x in oa]
      nk = [json.dumps(x, sort_keys=True) for x in na]
      dropped = [x for x in ok if x not in nk]
      if dropped:
        weakened.append({"unit": uid, "how": "premise dropped",
                         "dropped": len(dropped),
                         "example": json.loads(dropped[0])})
  if weakened:
    reasons.append("critic_rule_premise_weakened")
    evidence["C3"] = weakened

  # ---- C4: a new exclusion or negative conclusion
  added_excl = []
  for uid in relevant:
    before = set(json.dumps(x, sort_keys=True)
                 for x in _negative_conclusions(o_units.get(uid)))
    after = _negative_conclusions(n_units.get(uid))
    text = ((s1_units.get(uid) or {}).get("text") or "").lower()
    for kind, node in after:
      if json.dumps([kind, node], sort_keys=True) in before:
        continue
      if json.dumps(["%s" % kind, node], sort_keys=True) in before:
        continue
      neg_cue = _has_cue(text, NEGATION_CUES)
      exc_cue = _has_cue(text, EXCLUSIVITY_CUES)
      licensed = neg_cue if kind in ("negative_conclusion", "negative_literal") \
                 else exc_cue
      voc = _unit_vocabulary(s1_units.get(uid))
      outside = sorted(sym for sym in _content_symbols(node)
                       if voc and not _traceable(sym, voc))
      if outside:
        # the cue is about this sentence; it cannot license a disjointness
        # whose other side comes from elsewhere
        licensed = False
      added_excl.append({"unit": uid, "kind": kind, "licensed": bool(licensed),
                         "negation_cue": neg_cue, "exclusivity_cue": exc_cue,
                         "classes_not_in_this_unit": outside})
  if added_excl:
    if any(not x["licensed"] for x in added_excl):
      reasons.append("critic_unlicensed_exclusion_added")
    else:
      reasons.append("critic_licensed_exclusion_added")
    evidence["C4"] = added_excl

  # ---- C5: logical-skeleton change
  kinds = _finding_kinds(critic.get("report"))
  skel = []
  for uid in relevant:
    a, b = _skeleton(o_units.get(uid)), _skeleton(n_units.get(uid))
    diff = {k: [a[k], b[k]] for k in a if a[k] != b[k]}
    if diff:
      skel.append({"unit": uid, "diff": diff})
  if skel:
    matched = bool(kinds & set(_SCOPE_FINDINGS))
    reasons.append("critic_skeleton_change_matched" if matched
                   else "critic_skeleton_change_unmatched")
    def _hard(entry):
      d = entry["diff"]
      if "quantifiers" in d:
        return True
      if "negations" in d and any(n[0] == "wide" for n in d["negations"][1]):
        return True
      # a negation whose surrounding connectives changed is a scope change:
      # `not (A and B)` and `not A and not B` differ only here
      if "connectives" in d:
        pkg = n_units.get(entry["unit"])
        if any(a[0] == "not" for a in atoms(pkg)) or \
           any(a[0] == "not" for a in atoms(o_units.get(entry["unit"]))):
          return True
      return False

    hard = any(_hard(x) for x in skel)
    if hard:
      reasons.append("critic_scope_change_unresolved")
    evidence["C5"] = {"changes": skel, "finding_kinds": sorted(kinds),
                      "matched_named_finding": matched}

  if proof is None:
    reasons.append("record_incomplete")
    evidence["missing"] = "proof"

  return _record(None, reasons, "critic", used, changed, evidence, policy)


# --------------------------------------------------------------------------
# graph representability checks G1..G6
# --------------------------------------------------------------------------

def _graph_modal_markers(pkg):
  m = set()
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h in ("normally", "typically") or h in CLASSIFIERS:
      m.add(h)
  return m


# `habitual` and `typical` are Stage 1's default generic reading, not a
# distinction a unit deliberately carries.  Counting them made G1 fire on
# essentially every rule.
DEFAULT_MODES = frozenset(("habitual", "typical", "event", "actuality", None))


def _verb_modes(pkg, s1_unit):
  """{verb: set of modality labels} the unit carries canonically."""
  out = {}
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h == "has type" and len(a) >= 3 and isinstance(a[2], str):
      out.setdefault(_norm_symbol(a[2]), set())
  ev = {}
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h == "has type" and len(a) >= 3:
      ev[json.dumps(a[1])] = _norm_symbol(a[2]) if isinstance(a[2], str) else None
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h in CLASSIFIERS and len(a) >= 2:
      v = ev.get(json.dumps(a[1]))
      if v:
        out.setdefault(v, set()).add(h)
  for a in (s1_unit or {}).get("actions") or []:
    root = _norm_symbol(a.get("root")) if isinstance(a.get("root"), str) else None
    mode = a.get("mode")
    if root:
      out.setdefault(root, set())
      if isinstance(mode, str):
        out[root].add(mode.strip().lower())
  return {v: m for v, m in out.items() if v}


def _has_content_event(pkg, s1_unit):
  if "has content" in heads(pkg):
    return True
  for a in (s1_unit or {}).get("actions") or []:
    if "content" in (a.get("roles") or {}):
      return True
  return False


def _wide_negations(pkg):
  return [n for n in _skeleton(pkg)["negations"] if n[0] == "wide"]


def _quantifier_profile(pkg):
  """Universal binders only.  The graph language has no event variable, so its
  missing existentials are a design property, not a lost distinction."""
  return len([q for q in _skeleton(pkg)["quantifiers"] if q[0] == "forall"])


# Genuine participants of an event.  `actor` and `type` are the spine itself;
# time, location, property, degree and part are adjuncts the graph is not
# expected to carry as argument slots.
PARTICIPANTS = frozenset((
  "target", "object", "content", "recipient", "source", "instrument",
  "destination", "direction", "path", "beneficiary", "accompaniment", "result",
))


def _roles_of(pkg, s1_unit):
  """Non-actor participants per event, as a set of role names."""
  r = set()
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h.startswith("has ") and h[4:] in PARTICIPANTS:
      r.add(h[4:])
  for a in (s1_unit or {}).get("actions") or []:
    for k in (a.get("roles") or {}):
      if k in PARTICIPANTS:
        r.add(k)
  return r


def _graph_arity_roles(pkg):
  """How many participant slots the graph atoms actually carry."""
  best = 0
  for a in atoms(pkg):
    h = a[0].lstrip("-")
    if h in OPERATORS or h == "isa":
      continue
    best = max(best, len(a) - 1)
  return best


def unifiable_literals(a, b):
  """True when two unsigned atoms unify after standardizing their variables
  apart.  Ordinary first-order unification: predicate, arity, argument
  positions, constants, nested terms and repeated-variable constraints all have
  to agree, and the occurs check applies.

  `litbridge_atoms.unify_unsigned_atoms` already does exactly this and is
  tested; this is a thin, named wrapper so the intent is readable here.
  """
  try:
    import litbridge_atoms as LA
  except Exception:                                              # pragma: no cover
    return False
  bare_a = [a[0].lstrip("-")] + list(a[1:])
  bare_b = [b[0].lstrip("-")] + list(b[1:])
  try:
    return bool(LA.unify_unsigned_atoms(bare_a, bare_b).get("unifiable"))
  except Exception:                                              # pragma: no cover
    return False


def _contested_literals(clauses):
  """Unit literals present in both polarities that a resolution step could put
  against each other.

  A positive and a negative unit literal are contested when their unsigned
  forms UNIFY after standardizing the two clauses' variables apart -- ordinary
  first-order unification, which is what the prover would do.  An earlier
  version compared alpha-canonical keys, which refused `R(X,Y)` against
  `-R(Y,X)`; those two do resolve, so they are contested.
  """
  pos, neg = [], []
  for c in clauses or []:
    if not isinstance(c, dict) or c.get("@question") is not None:
      continue
    body = c.get("@logic")
    lits = body if (isinstance(body, list) and body
                    and isinstance(body[0], list)) else [body]
    lits = [l for l in lits if isinstance(l, list) and l and isinstance(l[0], str)]
    if len(lits) != 1:
      continue
    l = lits[0]
    (neg if l[0].startswith("-") else pos).append((l, c.get("@name")))
  out = []
  for pl, pname in pos:
    for nl, nname in neg:
      if unifiable_literals(pl, nl):
        out.append({"literal": json.dumps(pl)[:200],
                    "against": json.dumps(nl)[:200],
                    "positive_in": [pname], "negative_in": [nname]})
  return out


def check_graph(record, policy="balanced"):
  """Acceptance record for an answer produced by the graph retranslation."""
  reasons, evidence = [], {}
  g = record.get("graphtrans") or {}
  proof = g.get("proof")
  gclauses = g.get("clauses")
  gstage2 = g.get("stage2_graph")
  cstage2 = record.get("stage2")
  s1 = record.get("stage1") or []

  if not isinstance(gstage2, list) or not isinstance(cstage2, list):
    return _record(CAUTION, ["record_incomplete"], "graphtrans", set(), set(),
                   {"missing": "graph or canonical stage2"}, policy)
  if not proof:
    return _record(CAUTION, ["record_incomplete"], "graphtrans", set(), set(),
                   {"missing": "graph proof"}, policy)

  s1_units = {}
  for sent in s1 if isinstance(s1, list) else []:
    for u in (sent.get("units") or []) if isinstance(sent, dict) else []:
      if isinstance(u, dict) and u.get("unit_id"):
        s1_units[u["unit_id"]] = u

  used = used_units(proof)
  evidence["used_units"] = sorted(used)
  evidence["proof_sources"] = sorted(proof_sources(proof))
  proof_preds = set()
  for step in proof_steps(proof):
    if isinstance(step, list) and len(step) >= 3:
      for a in atoms(step[2]):
        if isinstance(a[0], str):
          proof_preds.add(_norm_symbol(a[0].lstrip("-")))

  # structural: the proof must cite clauses the submitted theory contains
  if gclauses:
    have = set(c.get("@name") for c in gclauses if isinstance(c, dict))
    missing = sorted(n for n in proof_sources(proof)
                     if n not in have and not n.startswith(("frm_", "axiom", "$")))
    if missing:
      reasons.append("structural_corruption")
      evidence["structural"] = {"proof_cites_absent_clauses": missing}
  if not used:
    reasons.append("record_incomplete")
    evidence["missing"] = "proof cites no source unit"

  c_units, g_units = split_units(cstage2), split_units(gstage2)
  lost = {"G1": [], "G2": [], "G3": [], "G4": [], "G5": []}
  unit_modes = {}
  for uid in sorted(used):
    cpkg, gpkg = c_units.get(uid), g_units.get(uid)
    if cpkg is None or gpkg is None:
      continue
    su = s1_units.get(uid)

    vm = _verb_modes(cpkg, su)
    if vm and not _graph_modal_markers(gpkg):
      unit_modes[uid] = vm

    if _has_content_event(cpkg, su) and "has content" not in heads(gpkg):
      nested = any(isinstance(x, list) and x and x[0] not in OPERATORS
                   for a in atoms(gpkg) if a[0] not in OPERATORS
                   for x in a[1:])
      if not nested:
        lost["G2"].append({"unit": uid})

    cw = _wide_negations(cpkg)
    if cw and not _wide_negations(gpkg):
      touched = set()
      for a in atoms(cpkg):
        if a[0] == "not" and len(a) >= 2:
          touched |= set(x[0].lstrip("-") for x in atoms(a[1])
                         if x[0].lstrip("-") not in OPERATORS)
      if touched & proof_preds:
        lost["G3"].append({"unit": uid, "canonical_wide_negations": len(cw),
                           "negated_predicates_used": sorted(touched & proof_preds)})

    cq, gq = _quantifier_profile(cpkg), _quantifier_profile(gpkg)
    if cq > gq:
      lost["G4"].append({"unit": uid, "canonical": cq, "graph": gq})

    croles = _roles_of(cpkg, su)
    if len(croles) >= 2 and _graph_arity_roles(gpkg) < len(croles) + 1:
      lost["G5"].append({"unit": uid, "canonical_participants": sorted(croles),
                         "graph_max_slots": _graph_arity_roles(gpkg)})

  # G1: two proof-used units share a verb but give it different modality, and
  # the graph package for both carries no modality marker.  The graph theory
  # then cannot keep them apart, so a rule needing one reading fires on the
  # other.  Mere presence of a modal mode is not a loss.
  for u1 in sorted(unit_modes):
    for u2 in sorted(unit_modes):
      if u1 >= u2:
        continue
      for verb in set(unit_modes[u1]) & set(unit_modes[u2]):
        m1 = set(unit_modes[u1][verb])
        m2 = set(unit_modes[u2][verb])
        if m1 and m2 and m1 != m2:
          lost["G1"].append({"units": [u1, u2], "verb": verb,
                             "modality": [sorted(m1), sorted(m2)]})
  for code, key in (("graph_modality_lost", "G1"),
                    ("graph_attitude_content_flattened", "G2"),
                    ("graph_negation_scope_lost", "G3"),
                    ("graph_quantifier_lost", "G4"),
                    ("graph_role_omitted", "G5")):
    if lost[key]:
      reasons.append(code)
      evidence[key] = lost[key]

  contested = _contested_literals(gclauses)
  if contested:
    names = set()
    for c in contested:
      names.update(c["positive_in"] or [])
      names.update(c["negative_in"] or [])
    if names & proof_sources(proof):
      reasons.append("proof_uses_contested_literal")
      evidence["G6"] = [c for c in contested
                        if set((c["positive_in"] or []) + (c["negative_in"] or []))
                        & proof_sources(proof)]

  return _record(None, reasons, "graphtrans", used, set(), evidence, policy)


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

def _record(forced, reasons, stage, used, changed, evidence, policy):
  if policy not in POLICIES:
    raise ValueError("unknown acceptance policy %r; expected one of %s"
                     % (policy, ", ".join(POLICIES)))
  idx = POLICIES.index(policy)
  decision = forced
  if decision is None:
    decision = ACCEPT
    for r in reasons:
      sev = SEVERITY.get(r, (ACCEPT, ACCEPT, ACCEPT))[idx]
      if _ORDER[sev] > _ORDER[decision]:
        decision = sev
  return {"decision": decision, "reasons": sorted(set(reasons)),
          "answering_stage": stage, "used_units": sorted(used),
          "changed_units": sorted(changed), "evidence": evidence,
          "policy": policy}


# The stages Task 2B measured.  A graph BRIDGE invents implications between open
# names; it is a different mechanism with different failure modes and no
# evidence behind these checks, so it is never judged here and never
# reinterpreted as a graph retranslation.
JUDGED_STAGES = ("critic", "graphtrans")


def check(record, policy="balanced"):
  """Acceptance record for `record`, dispatched on its answering stage.

  An answer from any other stage -- a fallback, a literal bridge, a graph
  bridge -- is accepted unchanged: this module only judges the critic and the
  graph retranslation, which are what Task 2B measured."""
  stage = record.get("answered_by")
  if stage == "critic":
    return check_critic(record, policy)
  if stage == "graphtrans":
    return check_graph(record, policy)
  return {"decision": ACCEPT, "reasons": [], "answering_stage": stage,
          "used_units": [], "changed_units": [], "evidence": {},
          "policy": policy}
