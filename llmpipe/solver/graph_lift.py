"""Carrying a graph proof back into the ordinary representation.

A graph proof is a backbone: which units it used, which atoms, which
substitutions, which invented bridges, and which question literal it reached.
Lifting asks whether the same step holds over the case's own detailed atoms.

The boundary is the literal bridge's own machinery.  Candidate atoms are the
ones `litbridge_atoms.build` displays, so each carries its exact compiled
template; the reply is parsed by `litbridge_rules.parse_response` against that
vocabulary; the rule is compiled by `litbridge_compile.compile_one`, whose
exact-template route governs a model-written rule.  A rule made only of
displayed atoms therefore compiles to those atoms or is refused structurally.

When a proof-used unit has no ordinary counterpart at all, the unit alone is
retranslated with the ordinary Stage-2 prompt and spliced into a copy of the
ordinary Stage 2.  The question package is never retranslated.
"""

import copy
import json
import os

import graph_inventory as GI
import litbridge_compile as compiler
import litbridge_converter as BW
import litbridge_procedure as procedure
import litbridge_prompts as prompts
import litbridge_rules as LR

VERSION = "graph_lift/2026-08-16"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_DIR = os.path.join(ROOT, "prompts", "graph")
LIFT_INSTRUCTIONS = os.path.join(PROMPT_DIR, "graph_lift_system.txt")
RETRANSLATE_SUFFIX = os.path.join(PROMPT_DIR, "graph_retranslate_suffix.txt")

MAX_SETS_PER_PROOF = 3
MAX_LIFTED_WORLDS = 6
MAX_RETRANSLATED_UNITS = 2
MAX_ALIGNMENT_ROWS = 6

LIFTED = "lifted_proof"
SOURCE_GAP = "source_translation_gap"
OVER_ABSTRACTION = "graph_over_abstraction"
INCOMPLETE = "incomplete_lifting"
STILL_BLOCKED = "ordinary_proof_still_blocked"


def _read(path):
  with open(path) as f:
    return f.read().strip()


def lift_instructions():
  return _read(LIFT_INSTRUCTIONS)


def retranslate_suffix():
  return _read(RETRANSLATE_SUFFIX)


def prompt_hashes():
  import hashlib
  out = {}
  for p in (LIFT_INSTRUCTIONS, RETRANSLATE_SUFFIX):
    if os.path.exists(p):
      out[os.path.relpath(p, ROOT)] = hashlib.sha256(
          open(p, "rb").read()).hexdigest()
  return out


# ------------------------------------------------------------- the backbone

def backbone(result, minimal, graph_sidecar, s1_json):
  """What one minimal graph proof rests on."""
  import graph_stage2 as G2
  rules_by_id = result.get("rules_by_id") or {}
  bridges = [rules_by_id[r] for r in (minimal.get("minimal_rules") or [])
             if r in rules_by_id]
  units, atoms = [], []
  for pid, rows in (graph_sidecar.get("atoms_by_package") or {}).items():
    units.append({"unit_id": pid, "text": G2.sentence_of(s1_json, pid)})
    for row in rows:
      atoms.append(dict(row, unit_id=pid))
  return {"answer": minimal.get("answer"), "pool": minimal.get("pool"),
          "bridge_ids": [r["rule_id"] for r in bridges],
          "bridges": [{"rule_id": r["rule_id"], "printed": r["printed"],
                       "a": r.get("graph_a"), "b": r.get("graph_b"),
                       "shape": r.get("graph_shape"),
                       # `judge_label`, not `label`: `assert_no_gold` reserves
                       # `label` for a reviewed key
                       "judge_label": r.get("graph_label")} for r in bridges],
          "units": units, "graph_atoms": atoms,
          "size": minimal.get("size")}


# ------------------------------------------------------------- the alignment

def align(name, graph_inventory_rows, candidates, s1_json, units=None):
  """Ordinary atoms that could stand for one open name.

  The candidates are `built["groups"]` — the atoms the literal bridge would
  display, each carrying its exact compiled template.  Unit-local first, so a
  common word elsewhere in the case cannot be picked by global similarity; then
  ranked by token overlap with the open name.  Every plausible match is kept.
  """
  packages = set(GI.packages_of(graph_inventory_rows, name))
  units = units or {}
  scored = []
  for row in candidates.get("groups") or []:
    mine = set(units.get(row.get("id")) or ())
    same_unit = bool(mine & packages)
    text = row.get("printed") or ""
    score = GI.overlap(name, _words(text))
    scored.append({"id": row.get("id"), "printed": text,
                   "unit": sorted(mine) or None,
                   "same_unit": same_unit, "overlap": score,
                   "role": row.get("role")})
  scored.sort(key=lambda r: (0 if r["same_unit"] else 1, -r["overlap"],
                             str(r["id"])))
  keep = [r for r in scored if r["same_unit"] or r["overlap"] > 0]
  return keep[:MAX_ALIGNMENT_ROWS]


def _words(text):
  """The words of a printed atom, with the JSON punctuation removed."""
  for ch in "[]\"',":
    text = text.replace(ch, " ")
  return text


def group_units(candidates, view):
  """-> {candidate id: the Stage-1 units its literal occurs in}.

  A displayed candidate carries its compiled literal but not the unit it came
  from; the unit is read back by finding the clauses that hold that literal.
  """
  out = {}
  for row in candidates.get("groups") or []:
    key = _literal_key(row.get("literal"))
    if not key:
      continue
    hit = set()
    for clause in view.get("final_clauses") or []:
      name = str(clause.get("@name") or "")
      if not name.startswith("sent_"):
        continue
      for lit in _clause_literals(clause):
        if _literal_key(lit) == key:
          hit.add(name[5:].split("_")[0])
    out[row.get("id")] = sorted(hit)
  return out


def _literal_key(literal):
  """A literal's predicate and its label argument, sign ignored."""
  if not (isinstance(literal, list) and literal
          and isinstance(literal[0], str)):
    return None
  head = literal[0].lstrip("-")
  if len(literal) > 1 and isinstance(literal[1], str):
    return (head, literal[1])
  return (head,)


def _clause_literals(clause):
  body = clause.get("@logic") if "@logic" in clause else clause.get("@question")
  if body is None:
    return []
  if isinstance(body, list) and body and isinstance(body[0], str):
    return [body]
  return [x for x in body if isinstance(x, list)]


def alignment_table(bone, graph_inventory_rows, candidates, s1_json,
                    units=None):
  """-> one row per graph bridge, with both names' candidate ordinary atoms."""
  out = []
  for bridge in bone["bridges"]:
    out.append({"rule_id": bridge["rule_id"], "printed": bridge["printed"],
                "a": bridge["a"], "b": bridge["b"],
                "a_rows": align(bridge["a"], graph_inventory_rows, candidates,
                                s1_json, units),
                "b_rows": align(bridge["b"], graph_inventory_rows, candidates,
                                s1_json, units)})
  return out


# ------------------------------------------------------------ the lift call

def lift_message(view, candidates, table, s1_json, graph_inventory_rows):
  """The user message: the case, the coarse steps, the atoms, the grammar."""
  import graph_judge as GJ
  split = prompts.split_case_text(view)
  lines = ["COARSE STEPS THE SECOND TRANSLATION USED:", ""]
  for row in table:
    lines.append("  COARSE STEP:  %s  ->  %s" % (row["a"], row["b"]))
    for label, name, rows in (("A", row["a"], row["a_rows"]),
                              ("B", row["b"], row["b_rows"])):
      for text in GJ._sentences_for(name, graph_inventory_rows, s1_json):
        lines.append("    %s comes from: %s" % (label, text))
      if rows:
        lines.append("    atoms above that may say %s:" % label)
        for r in rows:
          lines.append("      %s  %s%s" % (r["id"], r["printed"],
                                           "   (same sentence)"
                                           if r["same_unit"] else ""))
      else:
        lines.append("    no atom above appears to say %s." % label)
    lines.append("")
  blocks = [prompts.render_case(split), "\n".join(lines).strip(),
            prompts.render_lists(candidates), lift_instructions()]
  text = "\n\n".join(b for b in blocks if b)
  return {"text": text, "chars": len(text),
          "exceeds_size_guard": len(text) > prompts.MAX_USER_MESSAGE_CHARS}


def parse_lifted(text, ctx):
  """The reply, in the litbridge grammar, against the displayed vocabulary."""
  return LR.parse_response(text, ctx["vocab"], ctx["main_ids"],
                           ctx["source_rules"],
                           max_rules=MAX_SETS_PER_PROOF,
                           start_index=ctx["next_index"],
                           existing=ctx["written"],
                           tried=[r["canonical"] for r in ctx["written"]])


# --------------------------------------------------------- the lifted worlds

def run_lifted(view, ctx, rules, gk, case_id, world_index, sidecar=None):
  """Append one coherent set to the ORDINARY clauses and ask gk."""
  world = compiler.build_world(
      "graphlift_%s_%d" % (case_id, world_index), rules, view,
      ctx["configuration"], groups=ctx["built"]["groups"],
      check_redundancy=True,
      hypothesis_case_id="%s_graphlift" % case_id)
  if world["nothing_compiled"]:
    return {"world": "graphlift_%s_%d" % (case_id, world_index),
            "outcome": "compiler_refusal",
            "refused_by_the_compiler": world["refused_by_the_compiler"],
            "proofs": [], "answers": []}
  clauses = list(view["final_clauses"]) + [
      dict(c) for c in world["compiled_bridge_clauses"]]
  stored = {"stage1": view["stage1"], "stage2": view["stage2"],
            "final_clauses": view["final_clauses"],
            "input_text": view.get("input_text")}
  got = gk(clauses, stored, "%s/lift %d" % (case_id, world_index),
           dynamic=True)
  proofs = procedure.proofs_of(got.get("raw") or "{}",
                               world["clause_provenance"])
  for p in proofs:
    p["cited_rules"] = [world["rule_by_hypothesis_id"].get(h)
                        for h in p["cited_hypothesis_ids"]]
  outcome, result = procedure.classify_gk(got.get("raw") or "{}",
                                          got.get("answer"), proofs)
  row = {"world": world["world_id"], "outcome": outcome,
         "gk_result_string": result,
         "rules": [r["rule_id"] for r in rules],
         "printed": [r["printed"] for r in rules],
         "refused_by_the_compiler": world["refused_by_the_compiler"],
         "answers": [p["answer"] for p in proofs],
         "proofs": len(proofs),
         "conservative_formatter_answer": got.get("answer"),
         "seconds": got.get("seconds")}
  if sidecar is not None:
    row["sidecar"] = sidecar(world["world_id"], clauses, got)
  return row


# atoms the ordinary pipeline injects rather than the passage stating them;
# they were reaching the lift prompt's candidate list (folio-0046)
INJECTED_CLASSES = frozenset([
    "activity", "woman", "man", "person", "thing", "entity", "object",
    "abstract", "event", "artifact", "place", "animal", "substance", "group"])


def drop_injected(candidates):
  """-> (candidates without the injected atoms, what was dropped).

  A candidate whose atom is a bare `isa(<pipeline class>, ?X)` is the ordinary
  translation's own type scaffolding, not something the passage said.  It gave
  the lift model atoms like `isa(woman, ?X)` to build a rule from.
  """
  import copy
  out = copy.deepcopy(candidates)
  kept, dropped = [], []
  for row in out.get("groups") or []:
    atom = row.get("atom") or []
    if (len(atom) == 3 and atom[0] == "isa"
            and isinstance(atom[1], str)
            and atom[1] in INJECTED_CLASSES
            and isinstance(atom[2], str) and atom[2].startswith("?")):
      dropped.append(row.get("printed"))
      continue
    kept.append(row)
  out["groups"] = kept
  return out, dropped


def _tokens(text):
  import re
  return set(t for t in re.split(r"[^a-z0-9]+", str(text or "").lower()) if t)


def mentions_step(rule, step_a, step_b):
  """WP1.9: a lifted rule has to be about the coarse step it was asked for.

  Both names of the step must appear, token-wise, somewhere in the rule.  A
  rule that restates the passage instead (folio-0046 was asked `pet -> cat` and
  wrote `cat -> mammal`) is not a lift of that step.
  """
  written = _tokens(rule.get("printed"))
  for name in (step_a, step_b):
    want = _tokens(name)
    if want and not (want & written):
      return False
  return True


def classify(bone, lifted_rows, parsed, wrote_nothing):
  """Which of the five outcomes this lifting attempt reached."""
  if any(row.get("answers") for row in lifted_rows):
    if any(a == bone.get("answer") for row in lifted_rows
           for a in row.get("answers") or []):
      return LIFTED, "the ordinary clauses plus the lifted rules prove it"
    return OVER_ABSTRACTION, ("the lifted rules prove a different answer than "
                              "the graph proof did")
  if wrote_nothing:
    return SOURCE_GAP, ("the model wrote no rule over the ordinary atoms for "
                        "this step: the detailed translation does not hold "
                        "what the graph step needs")
  if parsed and not parsed.get("accepted"):
    return INCOMPLETE, "every written rule was refused by the parser"
  if lifted_rows and all(row.get("outcome") == "compiler_refusal"
                         for row in lifted_rows):
    return INCOMPLETE, "every written rule was refused by the compiler"
  return STILL_BLOCKED, "the ordinary theory does not prove it with these rules"


def lift(view, result, minimal_rows, graph_sidecar, graph_inventory_rows,
         s1_json, respond, gk, case_id, options, budget=None, sidecar=None,
         cap=MAX_LIFTED_WORLDS):
  """Every minimal graph proof, lifted as far as the caps allow."""
  ctx, why = procedure.bridge_context(view, options)
  if ctx is None:
    return {"attempted": False, "why": why, "outcome": SOURCE_GAP}
  units = group_units(ctx["built"], view)
  rows, worlds, bones = [], 0, []
  for minimal in minimal_rows[:MAX_SETS_PER_PROOF]:
    if not (minimal.get("minimal_rules") or []):
      continue
    bone = backbone(result, minimal, graph_sidecar, s1_json)
    bones.append(bone)
    built, dropped_atoms = drop_injected(ctx["built"])
    table = alignment_table(bone, graph_inventory_rows, built, s1_json, units)
    message = lift_message(view, built, table, s1_json, graph_inventory_rows)
    row = {"backbone": bone, "alignment": table,
           "injected_atoms_dropped": dropped_atoms,
           "message_chars": message["chars"]}
    if message["exceeds_size_guard"]:
      row.update({"asked": False,
                  "why": "the lifting message is over the size guard",
                  "outcome": INCOMPLETE})
      rows.append(row)
      continue
    text, err = respond("graph_lift", "%s/lift" % case_id, message["text"])
    row["asked"] = True
    if err or not text:
      row.update({"outcome": SOURCE_GAP,
                  "why": err or "the lifting call returned nothing"})
      rows.append(row)
      continue
    parsed = parse_lifted(text, ctx)
    ctx["next_index"] = parsed["next_index"]
    accepted = list(parsed["accepted"])
    # WP1.9: keep only rules that are about the coarse step they were asked for
    steps = [(r.get("a"), r.get("b")) for r in table]
    off_step = [r["printed"] for r in accepted
                if not any(mentions_step(r, a, b) for a, b in steps)]
    accepted = [r for r in accepted
                if any(mentions_step(r, a, b) for a, b in steps)]
    row["rules_off_the_step"] = off_step
    ctx["written"] = ctx["written"] + accepted
    row["written"] = [r["printed"] for r in accepted]
    row["rejections"] = parsed.get("rejections_by_category")
    lifted_rows = []
    for rule in accepted:
      if worlds >= cap or (budget is not None and not budget()):
        row.setdefault("omitted", []).append(
            {"rule_id": rule["rule_id"],
             "why": "beyond the %d lifted gk worlds a case may run" % cap})
        continue
      worlds += 1
      lifted_rows.append(run_lifted(view, ctx, [rule], gk, case_id, worlds,
                                    sidecar))
    row["worlds"] = lifted_rows
    outcome, note = classify(bone, lifted_rows, parsed, not accepted)
    row["outcome"] = outcome
    row["note"] = note
    row["backbone_correspondence"] = _correspondence(bone, lifted_rows)
    rows.append(row)
  return {"attempted": True, "rows": rows, "backbones": bones,
          "lifted_worlds": worlds,
          "lifted_proof": any(r.get("outcome") == LIFTED for r in rows),
          "outcome": _best(rows)}


def _best(rows):
  for want in (LIFTED, OVER_ABSTRACTION, INCOMPLETE, SOURCE_GAP,
               STILL_BLOCKED):
    for row in rows:
      if row.get("outcome") == want:
        return want
  return None


def _correspondence(bone, lifted_rows):
  """Did the detailed proof use analogous units and directions?"""
  want = set(u["unit_id"] for u in bone.get("units") or [])
  used = set()
  for row in lifted_rows:
    for name in row.get("rules") or []:
      used.add(name)
  return {"graph_units": sorted(want),
          "lifted_rules": sorted(used),
          "answer_matches": any(a == bone.get("answer")
                                for row in lifted_rows
                                for a in row.get("answers") or [])}


# ------------------------------------------------------ unit retranslation

def missing_units(bone, view):
  """Proof-used units with no content clause in the ordinary theory."""
  have = set()
  for c in view.get("final_clauses") or []:
    name = str(c.get("@name") or "")
    if name.startswith("sent_") and c.get("@sourcetype") != "populate":
      have.add(name[5:].split("_")[0])
  return [u["unit_id"] for u in bone.get("units") or []
          if u["unit_id"] not in have]


def retranslate_unit(view, s1_json, unit_id, graph_atoms, respond, case_id,
                     llm=None, version=None, tokens=None, think=None):
  """Re-call the ordinary Stage 2 on ONE unit, with the graph atoms as a note.

  The regenerated package replaces the stored one in a COPY of the ordinary
  Stage 2; the stored translation is never edited.  The question package is
  protected.
  """
  import graph_stage2 as G2
  if unit_id in G2.question_unit_ids(s1_json):
    return {"unit_id": unit_id, "asked": False,
            "why": "the question package is protected"}
  block = None
  for sentence in s1_json or []:
    for unit in (sentence.get("units") or []):
      if unit.get("unit_id") == unit_id:
        block = {"raw": sentence.get("raw"), "units": [unit]}
  if block is None:
    return {"unit_id": unit_id, "asked": False,
            "why": "the unit is not in Stage 1"}
  atoms = [a for a in graph_atoms if a.get("unit_id") == unit_id]
  message = "%s%s\n\nThe coarse atoms for this unit were:\n%s" % (
      json.dumps([block]), retranslate_suffix(),
      "\n".join("  %s" % json.dumps(a["atom"]) for a in atoms) or "  (none)")
  text, err = respond("graph_retranslate", "%s/retranslate/%s"
                      % (case_id, unit_id), message)
  if err or not text:
    return {"unit_id": unit_id, "asked": True,
            "why": err or "the retranslation returned nothing"}
  import llmparse
  parsed, perr = llmparse._try_parse(text)
  if parsed is None:
    fixed, _fixes = llmparse.fix_json(text)
    parsed, perr = llmparse._try_parse(fixed)
  if parsed is None:
    return {"unit_id": unit_id, "asked": True,
            "why": "the retranslation is not valid JSON: %s" % perr}
  package = None
  for item in (parsed[1:] if isinstance(parsed, list) and parsed
               and parsed[0] == "and" else []):
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id" \
            and item[1] == unit_id:
      package = item
  if package is None:
    return {"unit_id": unit_id, "asked": True,
            "why": "the retranslation holds no package for %s" % unit_id}
  spliced = copy.deepcopy(view["stage2"])
  replaced = False
  for i, item in enumerate(spliced):
    if isinstance(item, list) and len(item) >= 2 and item[0] == "@id" \
            and item[1] == unit_id:
      spliced[i] = copy.deepcopy(package)
      replaced = True
  if not replaced:
    spliced.append(copy.deepcopy(package))
  return {"unit_id": unit_id, "asked": True, "replaced": replaced,
          "package": package, "stage2": spliced}


def run_retranslated(view, s1_json, spliced, gk, case_id, options, unit_id,
                     sidecar=None):
  """Reconvert the ordinary Stage 2 with one package replaced, and ask gk."""
  import llmparse
  import logconvert
  with BW.scoped(options):
    s1 = copy.deepcopy(s1_json)
    s2 = copy.deepcopy(spliced)
    stats = llmparse._make_stats()
    llmparse._fill_missing_asu_time(s1, stats)
    s2 = llmparse._repair_entity_ids(s1, s2, stats)
    notes = []
    clauses = logconvert.rawlogic_convert(s2, s1, notes)
  if clauses is None:
    return {"unit_id": unit_id, "outcome": "conversion_failed"}
  stored = {"stage1": s1_json, "stage2": spliced, "final_clauses": clauses,
            "input_text": view.get("input_text")}
  got = gk(clauses, stored, "%s/retranslated %s" % (case_id, unit_id))
  proofs = procedure.proofs_of(got.get("raw") or "{}", {})
  outcome, result = procedure.classify_gk(got.get("raw") or "{}",
                                          got.get("answer"), proofs)
  row = {"unit_id": unit_id, "outcome": outcome, "gk_result_string": result,
         "answer": got.get("answer"), "clauses": len(clauses),
         "proofs": len(proofs), "seconds": got.get("seconds")}
  if sidecar is not None:
    row["sidecar"] = sidecar("retranslated_%s_%s" % (case_id, unit_id),
                             clauses, got)
  return row


def retranslate(view, s1_json, bones, respond, gk, case_id, options,
                ordinary_options, cap=MAX_RETRANSLATED_UNITS, sidecar=None):
  """At most two units per case, only for a unit a graph proof used."""
  rows, done = [], 0
  for bone in bones:
    for unit_id in missing_units(bone, view):
      if done >= cap:
        rows.append({"unit_id": unit_id,
                     "why": "beyond the %d retranslated units a case may run"
                            % cap})
        continue
      done += 1
      got = retranslate_unit(view, s1_json, unit_id,
                             bone.get("graph_atoms") or [], respond, case_id)
      if not got.get("stage2"):
        rows.append(got)
        continue
      run = run_retranslated(view, s1_json, got["stage2"], gk, case_id,
                             ordinary_options, unit_id, sidecar)
      got.pop("stage2", None)
      got["gk"] = run
      rows.append(got)
  return {"rows": rows, "units_retranslated": done,
          "retranslated_proof": any(
              (r.get("gk") or {}).get("outcome") == "proof" for r in rows)}
