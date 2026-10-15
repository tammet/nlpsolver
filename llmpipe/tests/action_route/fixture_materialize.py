"""Materialize the WP02 gold records into complete effective cases.

A record file holds a base source and named variants.  The compiler tests
must never read a variant as a patch; they read the effective case this
module builds from it.  The rules are fixed here and documented in
`fixtures/README.md` (section "Variants and effective cases"):

  base case        <record>:base    exists when the record has units or queries
  variant case     <record>:<id>    one per entry of `variants`

Building a variant case, in this order:

  1. `text`, `profile`, `entities`, `worlds` replace the record's value as a
     whole (no `worlds` anywhere: the one world W0).
     In a text record a variant that changes a unit's sentence or formula
     (any unit edit except a `units_patch` of expectation fields) must give
     its own `text`; an edited source never inherits the base passage.
  2. `units` (if present) replaces the whole unit list; else start from the
     base units and apply `units_remove` (ids must exist), `units_replace`
     (complete units, ids must exist), `units_patch` (fields merged into an
     existing unit, id must exist), `units_add` (ids must be new).
  3. `queries_keep` names base queries copied unchanged; every other base
     query is dropped.  `queries` entries override a base query of the same
     id (`expect` replaces the base `expect` as a whole; every other field
     of QUERY_FIELDS inherits unless the override gives it) or add a complete
     new query.  A query field outside QUERY_FIELDS raises.
  4. A query may not carry `units_add` / `units_remove`; a candidate may not
     carry `extra_units`.  Source changes are variants.

Every id is checked: duplicates and dangling references raise `Bad`.

An effective case also holds the record's `input_kind` and the candidates
that name it, so a consumer needs nothing but the effective case.
"""

import copy
import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = os.path.join(HERE, "fixtures", "cases")

QUERY_FIELDS_INHERITED = ["text", "stage1_reading", "stage1_steps", "stage2",
                          "view", "seed", "require_zero_remaining", "limits",
                          "backend", "backend_note", "replay", "replay_context",
                          "undeclared_entities", "gk_output", "search_note",
                          "planning_root", "ambient", "knower"]
QUERY_FIELDS = set(QUERY_FIELDS_INHERITED) | {"id", "expect"}
VARIANT_FIELDS = {"id", "text", "profile", "entities", "worlds", "units", "units_remove",
                  "units_replace", "units_patch", "units_add", "queries",
                  "queries_keep", "historical", "note", "entities_note"}


class Bad(Exception):
  pass


def _index(items, where, what):
  seen = {}
  for it in items:
    i = it.get("id")
    if not i:
      raise Bad("%s: a %s without id" % (where, what))
    if i in seen:
      raise Bad("%s: duplicate %s id %s" % (where, what, i))
    seen[i] = it
  return seen


def _apply_units(base_units, v, where):
  if "units" in v:
    for k in ("units_remove", "units_replace", "units_patch", "units_add"):
      if k in v:
        raise Bad("%s: `units` replaces the whole list; %s is not allowed with it" % (where, k))
    units = copy.deepcopy(v["units"])
    _index(units, where, "unit")
    return units
  units = copy.deepcopy(base_units)
  idx = _index(units, where, "unit")
  for i in v.get("units_remove", []):
    if i not in idx:
      raise Bad("%s: units_remove names unknown unit %s" % (where, i))
    units = [u for u in units if u["id"] != i]
    del idx[i]
  for u in v.get("units_replace", []):
    i = u.get("id")
    if i not in idx:
      raise Bad("%s: units_replace names unknown unit %s" % (where, i))
    pos = [n for n, x in enumerate(units) if x["id"] == i][0]
    units[pos] = copy.deepcopy(u)
    idx[i] = units[pos]
  for p in v.get("units_patch", []):
    i = p.get("id")
    if i not in idx:
      raise Bad("%s: units_patch names unknown unit %s" % (where, i))
    for k, val in p.items():
      if k != "id":
        idx[i][k] = copy.deepcopy(val)
  for u in v.get("units_add", []):
    i = u.get("id")
    if i in idx:
      raise Bad("%s: units_add repeats unit id %s" % (where, i))
    units.append(copy.deepcopy(u))
    idx[i] = units[-1]
  return units


def _apply_queries(base_queries, v, where):
  bidx = _index(base_queries, where, "query")
  out = []
  for i in v.get("queries_keep", []):
    if i not in bidx:
      raise Bad("%s: queries_keep names unknown query %s" % (where, i))
    out.append(copy.deepcopy(bidx[i]))
  kept = {q["id"] for q in out}
  for q in v.get("queries", []):
    i = q.get("id")
    if not i:
      raise Bad("%s: a query without id" % where)
    if i in kept:
      raise Bad("%s: query %s both kept and overridden" % (where, i))
    _check_query_fields(q, where)
    if i in bidx:
      merged = {}
      for k in QUERY_FIELDS_INHERITED:
        if k in q:
          merged[k] = copy.deepcopy(q[k])
        elif k in bidx[i]:
          merged[k] = copy.deepcopy(bidx[i][k])
      merged["id"] = i
      if "expect" not in q:
        raise Bad("%s/%s: an override must give its whole expect" % (where, i))
      merged["expect"] = copy.deepcopy(q["expect"])
      merged["overrides"] = "base"
      out.append(merged)
    else:
      out.append(copy.deepcopy(q))
    kept.add(i)
  return out


def _check_query_fields(q, where):
  if any(k in q for k in ("units_add", "units_remove")):
    raise Bad("%s/%s: a query may not change the source; use a variant" % (where, q.get("id")))
  extra = set(q) - QUERY_FIELDS
  if extra:
    raise Bad("%s/%s: unknown query fields %s" % (where, q.get("id"), sorted(extra)))


def _check_query_source_fields(queries, where):
  for q in queries:
    _check_query_fields(q, where)


def _edits_source(v):
  """True when a variant changes a sentence or a formula of the source."""
  if any(k in v for k in ("units", "units_remove", "units_replace", "units_add")):
    return True
  return any(k in p for p in v.get("units_patch", []) for k in ("text", "stage1", "stage2"))


def materialize(record):
  """Return the list of effective cases of one record, in file order."""
  name = record["id"]
  kind = record.get("input_kind")
  cases = []
  base_units = record.get("units", [])
  base_queries = record.get("queries", [])
  _index(base_units, name, "unit")
  _index(base_queries, name, "query")
  _check_query_source_fields(base_queries, name)
  if base_units or base_queries:
    cases.append({"case": name + ":base", "record": name, "variant": None,
                  "input_kind": kind, "text": record.get("text"), "profile": record.get("profile"),
                  "entities": record.get("entities", {}),
                  "worlds": record.get("worlds"),
                  "units": copy.deepcopy(base_units),
                  "queries": copy.deepcopy(base_queries)})
  vids = set()
  for v in record.get("variants", []):
    vid = v.get("id")
    if not vid:
      raise Bad("%s: a variant without id" % name)
    if vid in vids:
      raise Bad("%s: duplicate variant id %s" % (name, vid))
    vids.add(vid)
    where = "%s:%s" % (name, vid)
    extra = set(v) - VARIANT_FIELDS
    if extra:
      raise Bad("%s: unknown variant fields %s" % (where, sorted(extra)))
    if kind == "text" and "text" not in v and _edits_source(v):
      raise Bad("%s: a variant that edits the units must give its own text" % where)
    units = _apply_units(base_units, v, where)
    queries = _apply_queries(base_queries, v, where)
    cases.append({"case": where, "record": name, "variant": vid,
                  "input_kind": kind, "text": v.get("text", record.get("text")),
                  "profile": v.get("profile", record.get("profile")),
                  "entities": v.get("entities", record.get("entities", {})),
                  "worlds": v.get("worlds", record.get("worlds")),
                  "units": units, "queries": queries})
  by_case = {c["case"]: c for c in cases}
  for c in cases:
    c["candidates"] = []
  for k in record.get("candidates", []):
    if "extra_units" in k:
      raise Bad("%s/%s: extra_units is not allowed; reference a variant" % (name, k.get("id")))
    target = "%s:%s" % (name, k.get("variant", "base"))
    if target not in by_case:
      raise Bad("%s/%s: candidate references unknown case %s" % (name, k.get("id"), target))
    by_case[target]["candidates"].append(copy.deepcopy(k))
  return cases


def contexts(case):
  """{unit id: context record} of the units of an effective case that have one (migration plan section 9)."""
  return {u["id"]: u["context"] for u in case["units"] if u.get("context")}


def selection(q):
  """The compile_query keyword arguments of a gold query: planning_root, ambient, knower, where given."""
  return {k: q[k] for k in ("planning_root", "ambient", "knower") if k in q}


def load_all(cases_dir=CASES):
  out = []
  for path in sorted(glob.glob(os.path.join(cases_dir, "*.json"))):
    with open(path) as f:
      out.extend(materialize(json.load(f)))
  return out


if __name__ == "__main__":
  cs = load_all()
  print("%d effective cases" % len(cs))
  for c in cs:
    print("  %-45s %2d units %2d queries" % (c["case"], len(c["units"]), len(c["queries"])))
