"""Open triples to GK clauses, under one frozen converter configuration.

Two steps.  `to_stage2` is syntax: an open relation `[R, X, Y]` becomes the
ordinary controlled atom `["is rel2", R, X, Y]`, `["isa", C, X]` stays as it
is, and the formula structure is copied.  `compile` then runs the ordinary
`logconvert.rawlogic_convert` inside `litbridge_converter.scoped`, under the
option set of design plan §6.

The option set is the point of this file.  The graph theory must contain no
connection between two open names except a named clause, so the axiom file,
the injectors, the semantic normalization and every abstraction primitive are
off, and the context is the constant `$c`.  What stays on is stated in the
table below and each of those emits a named clause with provenance.

The dict is captured once per case, before the first conversion.  `scoped`
replaces `globals.options` for the duration, so a set read inside a conversion
would be the scope and not the run.
"""

import copy
import hashlib
import json

import litbridge_converter as BW

VERSION = "graph_compile/2026-08-16"

CONCEPT = "isa"
RELATION = "is rel2"
WORLD = "W0"

# structural heads copied through unchanged
STRUCTURAL = ("and", "or", "not", "implies", "forall", "exists", "normally",
              "=", "question", "ask", "holds", "@id", "@p")

# design plan §6.  Every row is a decision about what may connect two open
# names; changing one is a new graph experiment version.
GRAPH_OPTION_TABLE = {
    "nocontext_flag": True,       # one constant context; no tense or world term
    "nosemnormal_flag": True,     # no antonym fold, no canonicals, no injector
    "noclassnumbernorm_flag": True,  # `swims` and `swim` stay two open names
    "noopennamerewrite_flag": True,  # `owns` does not become the pipeline's
                                     # `have`, and a perspective verb does not
                                     # become a Davidsonian event
    "nopopulate_flag": True,      # v2/C1: no `$some_C` witness, so an invented
                                  # bridge cannot ground its own body
    "noentitycat_flag": True,     # v2/C2: no `entity_S*` name enters supply
    "prover_axiomfiles": [],      # no axioms_std.js
    "event_base": "neodavidson",  # no event reaches the fold
    "entitymerge_flag": False,
    "guarddrop_flag": False,
    "bridges_flag": False,
    "typeenrich_flag": False,
    "propclass_flag": False,
    "numtype_flag": False,
    "compasym_flag": False,
    "existfold_flag": False,
    "dropdefinites_flag": False,
    "noexceptions_flag": False,   # $block on a `normally` rule survives
    "noproptypes_flag": False,
    "prenorm_flag": False,        # a pre-Stage-1 phase; the graph starts at 2
    "s2split_flag": False,
    "combined_flag": False,
    "directanswer_flag": False,
    "litbridge_flag": False,
    "litbridge_extras_flag": False,
    "crossstage_retry_flag": False,
    "nominalretry_flag": False,
    "negretry_flag": False,
    "prover_seconds_cli": True,   # the pool's seconds, never an auto-estimate
}

STAYS_ACTIVE = (
    "entity UNA wrapping (`#:` on Stage-1 numbered entities)",
    "the $defq question encoding and the bare-plural generic question hoist",
    "Skolemization",
    "the structural repairs (every nofix_* is False)")

# Two things the pilot left active and v2 turns off, because each puts a name
# or a constant into the theory that the translator never wrote:
TURNED_OFF_IN_V2 = (
    "population witnesses ($some_C, $some_not_C) — `nopopulate_flag`",
    "Stage-1 entity-category and base-word isa (`entity_S*`) — "
    "`noentitycat_flag`")


class GraphError(Exception):
  """The graph theory cannot be built."""


# ------------------------------------------------------------ the option set

def graph_options(base=None):
  """The complete option dict a graph theory is converted under.

  `base` is the run's own options when there is a run (`solve.py`), and None
  in a study tool, where the shipped defaults are the base.  Either way every
  `nofix_*` is cleared and the §6 table is applied last.
  """
  if base is None:
    opts = BW.defaults()
  else:
    opts = copy.deepcopy(base)
  for k in list(opts):
    if str(k).startswith("nofix_"):
      opts[k] = False
  for k, v in GRAPH_OPTION_TABLE.items():
    if k not in opts:
      raise GraphError("option %r is not recognized" % k)
    opts[k] = copy.deepcopy(v)
  # single-fix ablations: restore the pilot's behaviour for exactly one fix
  import graph_ablation as AB
  if AB.on(AB.REVERT_C1_POPULATE):
    opts["nopopulate_flag"] = False
  if AB.on(AB.REVERT_C2_ENTITYCAT):
    opts["noentitycat_flag"] = False
  return opts


def options_sha256(opts):
  return hashlib.sha256(
      json.dumps(opts, sort_keys=True, default=str).encode()).hexdigest()


# ------------------------------------------------------------- the rewriting

def to_stage2(node):
  """Open triples to controlled atoms.  A pure syntactic pass.

  `["isa", C, X]` and `["=", A, B]` pass through; every other content atom
  `[R, X, Y]` becomes `["is rel2", R, X, Y]`, a fixed event role included.
  """
  if not isinstance(node, list) or not node:
    return copy.deepcopy(node)
  head = node[0]
  if not isinstance(head, str):
    return [to_stage2(x) for x in node]
  if head in STRUCTURAL:
    if head in ("forall", "exists", "ask") and len(node) >= 3:
      return [head, node[1]] + [to_stage2(x) for x in node[2:]]
    if head == "@id" and len(node) >= 3:
      return [head, node[1]] + [to_stage2(x) for x in node[2:]]
    if head == "@p":
      return copy.deepcopy(node)
    if head == "holds" and len(node) == 3:
      return [head, node[1], to_stage2(node[2])]
    if head == "=":
      return copy.deepcopy(node)
    return [head] + [to_stage2(x) for x in node[1:]]
  if head == CONCEPT:
    return copy.deepcopy(node)
  return [RELATION, head] + [copy.deepcopy(x) for x in node[1:]]


def from_stage2_name(atom):
  """-> the open name a controlled atom carries, or None."""
  if not (isinstance(atom, list) and atom and isinstance(atom[0], str)):
    return None
  head = atom[0].lstrip("-")
  if head == CONCEPT and len(atom) > 1:
    return atom[1] if isinstance(atom[1], str) else None
  if head == RELATION and len(atom) > 1:
    return atom[1] if isinstance(atom[1], str) else None
  return None


# ------------------------------------------------------------- the conversion

def convert(s2_graph, s1_json, options):
  """-> (clauses, converter notes).  One conversion in one option scope."""
  import llmparse
  import logconvert
  controlled = to_stage2(s2_graph)
  with BW.scoped(options):
    s1 = copy.deepcopy(s1_json)
    s2 = copy.deepcopy(controlled)
    stats = llmparse._make_stats()
    llmparse._fill_missing_asu_time(s1, stats)
    s2 = llmparse._repair_entity_ids(s1, s2, stats)
    notes = []
    clauses = logconvert.rawlogic_convert(s2, s1, notes)
  if clauses is None:
    raise GraphError("rawlogic_convert returned None for the graph theory")
  return clauses, notes


def written_names(s2_graph):
  """Every open name the graph Stage 2 wrote."""
  import graph_stage2 as G2
  out = set()
  for _pid, atom, _p, _pol, _b in G2.atoms_of(s2_graph):
    name = G2.name_of(atom)
    if isinstance(name, str):
      out.add(name)
  return out


def compiled_names(clauses):
  """Every open name the compiled clause list carries."""
  out = set()
  for c in clauses or []:
    body = c.get("@logic") if "@logic" in c else c.get("@question")
    out.update(n for n in _names_in(body) if n)
  return out


def name_drift(s2_graph, clauses):
  """Names the converter added or altered.  Empty is the design's invariant.

  A name the translator never wrote, or a written name the clause list has
  lost, means some pass renamed it — which would connect two open names
  without a clause a proof can show.  Two kinds of clause carry names of their
  own by design and are not counted: the population witnesses, and the
  Stage-1 entity-category clauses (`entity_S*`), which state the category
  Stage 1 gave an entity and are declared to stay active.
  """
  written = written_names(s2_graph)
  got = compiled_names([c for c in clauses or []
                        if c.get("@sourcetype") != "populate"
                        and not str(c.get("@name") or "").startswith(
                            "entity_")])
  return {"invented_by_the_converter": sorted(got - written),
          "lost_in_conversion": sorted(written - got)}


def compile(s2_graph, s1_json, options=None, case_id=None):
  """-> (clauses, sidecar).  The graph theory and where each clause came from.

  `options` must be the dict captured before the first conversion of this
  case.  When it is None the set is built here, which is right for a study
  tool and wrong inside another conversion.
  """
  opts = options if options is not None else graph_options()
  controlled = to_stage2(s2_graph)
  clauses, notes = convert(s2_graph, s1_json, opts)
  return clauses, sidecar(s2_graph, controlled, s1_json, clauses, opts, notes,
                          case_id)


def sidecar(s2_graph, controlled, s1_json, clauses, options, notes=(),
            case_id=None):
  """Every clause mapped to its package, its unit text and its open names."""
  import graph_stage2 as G2
  text_of = {}
  for uid, unit, raw in G2.stage1_units(s1_json):
    text_of[uid] = unit.get("text") or raw
  atoms_by_package = {}
  for pid, atom, path, pol, _b in G2.atoms_of(s2_graph):
    atoms_by_package.setdefault(pid, []).append(
        {"atom": atom, "path": path, "polarity": pol,
         "name": G2.name_of(atom), "kind": G2.kind_of(atom),
         "atom_id": "%s#%d" % (pid, len(atoms_by_package.get(pid) or []))})
  rows = []
  for c in clauses or []:
    name = str(c.get("@name") or "")
    pid = None
    if name.startswith("sent_"):
      pid = name[5:].split("_")[0]
    body = c.get("@logic") if "@logic" in c else c.get("@question")
    names = sorted(set(n for n in _names_in(body) if n))
    rows.append({"clause_name": name, "package_id": pid,
                 "unit_text": text_of.get(pid),
                 "sourcetype": c.get("@sourcetype"),
                 "is_question": "@question" in c,
                 "open_names": names,
                 "graph_atom_ids": [a["atom_id"]
                                    for a in atoms_by_package.get(pid) or []]})
  return {"version": VERSION, "case_id": case_id,
          "name_drift": name_drift(s2_graph, clauses),
          "options_sha256": options_sha256(options),
          "options": options,
          "converter_notes": list(notes or []),
          "controlled_stage2": controlled,
          "atoms_by_package": atoms_by_package,
          "clauses": rows,
          "clause_count": len(clauses or []),
          "theory_sha256": hashlib.sha256(
              json.dumps(clauses, sort_keys=True,
                         default=str).encode()).hexdigest()}


def _names_in(node, out=None):
  if out is None:
    out = []
  if isinstance(node, list) and node:
    n = from_stage2_name(node)
    if n:
      out.append(n)
    for x in node:
      if isinstance(x, list):
        _names_in(x, out)
  return out


# --------------------------------------------------------------- the prover

def prover_call(clauses, s1_json, seconds=5, options=None):
  """Ask gk for the graph theory, with no axiom file and this pool's seconds."""
  import prover
  opts = dict(options if options is not None else graph_options())
  opts["prover_axiomfiles"] = []
  opts["prover_seconds"] = seconds
  opts["prover_seconds_cli"] = True
  with BW.scoped(opts):
    return prover.call_prover(clauses, s1_json=s1_json)


def gk_runner(s1_json, seconds=5, options=None, log=None, budget=None):
  """-> a `gk(clauses, stored, tag, seconds=None)` over the graph theory.

  One door for every graph gk call: the pool's seconds, no axiom file, the
  effective command and the input hash recorded on each call.
  """
  import globals as g
  import procproofs
  import time

  default_seconds = seconds

  def call(clauses, stored, tag, seconds=None, dynamic=False):
    t0 = time.time()
    call.calls += 1
    before = g.options.get("_collect")
    g.options["_collect"] = {}
    text = None
    try:
      opts = dict(options if options is not None else graph_options())
      opts["prover_axiomfiles"] = []
      opts["prover_seconds"] = seconds or default_seconds
      opts["prover_seconds_cli"] = True
      with BW.scoped(opts):
        import prover
        import utils
        try:
          text = utils.clause_list_to_json_commented(clauses,
                                                     s1_json=s1_json)
        except Exception:                                       # noqa: BLE001
          text = None
        try:
          raw = prover.call_prover(clauses, s1_json=s1_json)
          answer = procproofs.process_proof(
              raw, text=stored.get("input_text"), s1_json=s1_json,
              s2_json=stored.get("stage2"), logic=clauses)
          if isinstance(answer, tuple):
            answer = answer[0]
          got = {"answer": answer, "gk_input": text,
                 "raw": raw if isinstance(raw, str) else json.dumps(raw)}
        except Exception as e:                                  # noqa: BLE001
          got = {"answer": None, "raw": "{}", "gk_input": text,
                 "error": "%s: %s" % (type(e).__name__, e)}
      command = (g.options.get("_collect") or {}).get("gk_command")
    finally:
      if before is None:
        g.options.pop("_collect", None)
      else:
        g.options["_collect"] = before
    got["gk_command"] = command
    got["seconds"] = round(time.time() - t0, 2)
    got["gk_input_sha256"] = hashlib.sha256(
        (got.get("gk_input") or "").encode()).hexdigest()
    got["thresholds"] = {"stored_gk_threshold": None,
                         "dynamic_gk_threshold": None,
                         "options_changed": []}
    if log is not None:
      log.append({"tag": tag, "clauses": len(clauses),
                  "prover_seconds": seconds or default_seconds,
                  "seconds": got["seconds"], "gk_command": command,
                  "gk_input_sha256": got["gk_input_sha256"]})
    return got
  call.calls = 0
  return call
