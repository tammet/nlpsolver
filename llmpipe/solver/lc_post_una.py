"""Post-clausification UNA (unique-name assumption) wrapping.

The `gk` prover treats two distinct constants as definitely unequal only
when they are prefixed with `#:`. Without this, the X2 direct-support
uniqueness axiom (axioms_std.js §7h) cannot close cases like

    "John ate the pizza on the table. Was the pizza on the floor?"

because the prover would happily unify or paramodulate "table 3" with
"floor 4" rather than detecting the contradiction.

This module wraps every Stage-1 numbered entity (e.g. "table 3", "Mary 1")
with a `#:` prefix, in every clause emitted by `rawlogic_convert`.

A string is wrapped iff ALL three independent checks pass:

  1. Surface-form regex: `^[A-Za-z][A-Za-z0-9_' -]* \\d+$`  (word + space + digits)
  2. Membership in the Stage-1 entity set passed in by the caller
  3. Not a Skolem (`^sk\\d+_`), `$`-special, `?:`-variable, or already `#:`-prefixed

Skolems, function terms ($theof1, $measure_of), worlds (W0/W1), and
$some_X / $some_not_X constants are intentionally NOT wrapped — they
have their own distinctness machinery, and broadening UNA to them is
out of scope for this change.
"""

import re

_STAGE1_REGEX  = re.compile(r"^[A-Za-z][A-Za-z0-9_' -]* \d+$")
_SKOLEM_PREFIX = re.compile(r"^sk\d+_")


def is_stage1_entity(s, stage1_set):
  """Return True iff *s* should be wrapped with `#:` prefix."""
  return (isinstance(s, str)
          and _STAGE1_REGEX.match(s) is not None
          and s in stage1_set
          and _SKOLEM_PREFIX.match(s) is None
          and not s.startswith(('$', '?:', '#:')))


def collect_stage1_entities(s1_json):
  """Build the Stage-1 entity set from the Stage-1 JSON.

  Walks `s1_json -> packages -> units -> entities`, collects every
  concrete entity id that matches the surface-form regex and is not
  Skolem-shaped.
  """
  # id -> whether it is EVER annotated with a category in Stage 1.
  cand = {}
  if not s1_json or not isinstance(s1_json, list):
    return set()
  for pkg in s1_json:
    if not isinstance(pkg, dict):
      continue
    for asu in pkg.get("units", []):
      if not isinstance(asu, dict):
        continue
      for ent in asu.get("entities", []):
        if not isinstance(ent, dict):
          continue
        eid = ent.get("id")
        if (isinstance(eid, str)
            and _STAGE1_REGEX.match(eid) is not None
            and _SKOLEM_PREFIX.match(eid) is None
            and not eid.startswith(('$', '?:', '#:'))):
          cand[eid] = cand.get(eid, False) or bool(ent.get("category"))
  # UNA applies to RIGID designators only: proper-noun named individuals
  # (uppercase-initial id) and any entity carrying a category (concrete object
  # instances, the X2 direct-support case).  Exclude lowercase common-noun
  # reifications with no category — these are non-rigid DEFINITE DESCRIPTIONS
  # ("Mia's favorite season", "the output of MT") that can co-refer with a named
  # entity, so UNA must not declare them distinct by name (case 48).
  return {eid for eid, has_cat in cand.items()
          if eid[:1].isupper() or has_cat}


def apply_una(clauses, stage1_set):
  """Walk every clause, replace each Stage-1 entity occurrence with its
  `#:`-prefixed form. Returns a new list; input is not mutated.

  Operates on the standard clause-list shape:
    [{"@name": ..., "@logic": CLAUSE} | {"@name": ..., "@question": F} | ...]
  Other dict keys (@confidence, @sourcetype, ...) pass through unchanged.
  """
  if not stage1_set:
    return clauses

  def visit(node, in_question=False, under_eq=False):
    if isinstance(node, str):
      if under_eq:
        return node
      return "#:" + node if is_stage1_entity(node, stage1_set) else node
    if isinstance(node, list):
      return [visit(x, in_question, under_eq) for x in node]
    return node

  out = []
  for c in clauses:
    if isinstance(c, dict):
      new_c = dict(c)
      for k in ("@logic", "@question"):
        if k in new_c:
          new_c[k] = visit(new_c[k], in_question=(k == "@question"))
      out.append(new_c)
    elif isinstance(c, list):
      out.append(visit(c))
    else:
      out.append(c)
  return out
