"""Terminal display of the action route: what `solve.py` prints for an action-route call at each output level.

Formatting only: no stage runs here and no decision is made here.  The levels are those of the ordinary pipeline
(`solve_display.py`), and each includes the one above it:

  (none)     the answer
  -explain   + the explanation after the answer: the sentences and the library laws that the deciding proof used,
             then the plan steps and the replay verdict, the checks of a supplied sequence, or why there is no answer
  -logic     + the Stage-1 unit texts, the source clauses of each sentence, the query and its obligations, the stages
             block, and the action term of each plan step and the proof steps under the explanation
  -details   + the accepted Stage-1 and Stage-2 JSON, the controller's checks and normalizations, and the prover input
             and result of each GK launch, with the library clauses as one comment line
  -debug     + every model request and raw response, the library clauses in full, and the GK command of each launch

  -json      the logic in raw JSON instead of pred(arg,...) syntax
  -prover    the prover input, command and result of each launch, at any level
  -summary   one block at the end; -summary-json the same block as one JSON line

The route prints its blocks after the run, from its run record and from `view`: the source and query artifacts and
the full text of every GK launch, which the run record does not keep.  Under -debug the model requests are printed
as they are sent (`show_request`, `show_response`).
"""

import json
import os
import shlex

import pretty
from proof_render import format_clause_traditional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))    # llmpipe/


def levels(options):
  """The output levels of a call's options, each including the ones above it."""
  o = options or {}
  debug = bool(o.get("debug_print_flag"))
  details = debug or bool(o.get("show_details_flag"))
  logic = details or bool(o.get("show_logic_flag"))
  explain = logic or bool(o.get("prover_explain_flag"))
  return {"explain": explain, "logic": logic, "details": details, "debug": debug,
          "json": bool(o.get("json_flag")), "prover": bool(o.get("show_prover_flag"))}


# ---------------------------------------------------------------------------
# helpers


def clause_text(clause, as_json=False):
  """One clause or atom in pred(arg,...) syntax, or in JSON."""
  if clause is False:
    return "false"
  if as_json:
    return json.dumps(clause, ensure_ascii=False)
  return format_clause_traditional(clause).replace("\n", "\n    ")


_ROLES = None


def law_roles():
  """{library law name: its role} from axioms_action.roles.json, or {} when the file is missing."""
  global _ROLES
  if _ROLES is None:
    try:
      with open(os.path.join(ROOT, "axioms_action.roles.json")) as f:
        _ROLES = json.load(f).get("roles") or {}
    except (OSError, ValueError):
      _ROLES = {}
  return _ROLES


# the unit part of a generated source clause's name: identity clauses, and the type records of the Stage-2 types field
GENERATED = ("source", "types")


def units_of(name, src=None):
  """The units a clause name comes from: "src:S1:static:0" -> ["S1"], "src:S7+S8:hook:15" -> ["S7", "S8"],
  "query:Q1:plan:positive" -> ["Q1"].  With the source artifact, a source name is read from its clause record (the
  number is its place in the clause list), so a type clause names the unit its type comes from.  A generated clause
  ("src:source:...") and a library law give []."""
  parts = str(name).split(":")
  if len(parts) < 2 or parts[0] not in ("src", "query"):
    return []
  clauses = (src or {}).get("clauses") or []
  if parts[0] == "src" and parts[-1].isdigit() and int(parts[-1]) < len(clauses):
    r = clauses[int(parts[-1])]
    ids = [r["unit"]] if r.get("unit") else [u for u in r.get("units") or [] if u not in GENERATED]
    if r.get("type_unit") and r["type_unit"] not in ids:
      ids.append(r["type_unit"])
    return ids
  return [] if parts[1] in GENERATED else parts[1].split("+")


def is_law(name):
  return not str(name).startswith(("src:", "query:"))


def sentences(view):
  """{unit id: the input sentence it comes from}: the raw sentence of its Stage-1 package, else the unit's text, else
  the `text` of a formal record's unit."""
  out = {}
  for p in view.get("stage1_packages") or []:
    if not isinstance(p, dict):
      continue
    for u in p.get("units") or []:
      if isinstance(u, dict) and u.get("unit_id"):
        out[u["unit_id"]] = p.get("raw") or u.get("text")
  for u in (view.get("source") or {}).get("units") or []:
    if u.get("text"):
      out.setdefault(u["id"], u["text"])
  for uid, text in (view.get("unit_texts") or {}).items():
    out.setdefault(uid, text)
  for qid, text in (view.get("query_texts") or {}).items():
    if text:
      out.setdefault(qid, text)
  return out


def unit_order(view):
  """{unit id: its position}: the source units in text order, then the questions."""
  ids = [u["id"] for u in (view.get("source") or {}).get("units") or []]
  for p in view.get("stage1_packages") or []:
    for u in (p.get("units") or []) if isinstance(p, dict) else []:
      if isinstance(u, dict) and u.get("unit_id") and u["unit_id"] not in ids:
        ids.append(u["unit_id"])
  ids += [q for q in view.get("query_texts") or {} if q not in ids]
  return {u: i for i, u in enumerate(ids)}


def _numbered(texts):
  seen, lines = [], []
  for t in texts:
    if t and t not in seen:
      seen.append(t)
      lines.append("  (%d) %s" % (len(seen), t))
  return lines


def _from_steps(reason):
  # [rule, step, [step, literal], ..., "fromgoal", 1]: the step numbers stand before the first tag
  refs = []
  for x in reason[1:]:
    if isinstance(x, str):
      break
    if isinstance(x, int):
      refs.append(str(x))
    elif isinstance(x, list) and x and isinstance(x[0], int):
      refs.append(str(x[0]))
  return "from steps " + ", ".join(refs) if refs else str(reason[0])


def proof_lines(steps, as_json=False):
  """The steps of a GK proof, one per line: the clause and where it comes from (a clause name or earlier steps)."""
  lines = []
  for step in steps or []:
    if not isinstance(step, list) or len(step) < 3:
      continue
    n, reason, clause = step[0], step[1], step[2]
    why = reason[1] if isinstance(reason, list) and reason[:1] == ["in"] else \
      _from_steps(reason) if isinstance(reason, list) and reason else str(reason)
    lines.append("  (%s) %s  [%s]" % (n, clause_text(clause, as_json), why))
  return lines


def _first_line(answer):
  return str(answer or "").split("\n")[0]


def _results(rec):
  """[(query id or None, result)]: the one result, or each result of a formal record with several queries."""
  res = rec.get("result") or {}
  if res.get("outcome") == "several":
    return [((r.get("query") or {}).get("id"), r) for r in res.get("results") or []]
  return [(None, res)] if res else []


def _obligation_texts(view):
  """{(query id, obligation id): the obligation's formula text} from the query artifacts."""
  out = {}
  for qa in view.get("queries") or []:
    for o in qa.get("obligations") or []:
      out[(qa["query"]["id"], o["id"])] = o.get("text")
  return out


# ---------------------------------------------------------------------------
# the explanation (-explain and above)


def _proofs(res):
  """The proofs a result rests on: its deciding proof, and each verdict's proof of a supplied sequence."""
  out = [res["proof"]] if isinstance(res.get("proof"), dict) else []
  for v in res.get("verdicts") or []:
    p = v.get("proof") if isinstance(v, dict) else None
    if isinstance(p, dict) and p not in out:
      out.append(p)
  return out


def _diagnostic_lines(res, rec):
  lines = []
  diags = list(res.get("diagnostics") or [])
  unsupported = ((rec.get("translation") or {}).get("unsupported") or {}).get("diagnostics") or []
  for d in diags + [d for d in unsupported if d not in diags]:
    if isinstance(d, dict):
      what = d.get("reason") or ", ".join(d.get("reasons") or []) or d.get("outcome") or "diagnostic"
      units = d.get("units") or ([d["unit"]] if d.get("unit") else [])
      text = d.get("message") or d.get("detail")
      lines.append("  %s%s%s" % (what, " (%s)" % ", ".join(units) if units else "",
                                 ": %s" % text if isinstance(text, str) else ""))
    else:
      lines.append("  %s" % str(d)[:300])
  for e in (rec.get("translation") or {}).get("errors") or []:
    if e not in diags:
      lines.append("  %s" % e)
  return lines


def explain_result(res, rec, view, lv):
  """The explanation block of one result: lines, without the "Explained:" header."""
  sent = sentences(view)
  as_json = lv["json"]
  proofs = _proofs(res)
  sources = [n for p in proofs for n in p.get("sources") or []]
  lines = []
  conf, status = res.get("confidence"), res.get("confidence_status")
  if isinstance(conf, (int, float)) and (conf < 0.9999 or status not in (None, "validated")):
    lines.append("Confidence %s%%%s." % (round(conf * 100), " (%s)" % status if status and status != "validated" else ""))
  order = unit_order(view)
  used = [sent.get(u) or u for u in sorted({u for n in sources for u in units_of(n, view.get("source"))},
                                            key=lambda u: (order.get(u, len(order)), u))]
  if used:
    lines += ["Sentences used:"] + _numbered(used)
  laws = []
  for n in sources:
    if is_law(n) and n not in laws:
      laws.append(n)
  if laws:
    roles = law_roles()
    lines += ["Laws used:"] + ["  %s%s" % (n, " (%s)" % roles[n].replace("_", " ") if roles.get(n) else "")
                               for n in laws]
  o = res.get("outcome")
  kind = (res.get("query") or {}).get("kind")
  if o == "plan_found":
    lines.append("Plan steps (each checked by replay):")
    for i, step in enumerate(res.get("plan_steps") or []):
      lines.append("  (%d) %s" % (i + 1, step))
      if lv["logic"] and i < len(res.get("plan") or []):
        lines.append("        " + clause_text(res["plan"][i], as_json))
  elif o == "goal_already_holds":
    lines.append("No action is needed: the goal holds in the start state.")
  elif o == "verification_result" and kind == "verify" and res.get("verdicts"):
    texts = _obligation_texts(view)
    qkey = (res.get("query") or {}).get("id")
    lines.append("Checks of the supplied steps:")
    for v in res["verdicts"]:
      p = v.get("proof") or {}
      ob = p.get("obligation")
      t = texts.get((qkey, ob))
      lines.append("  %s%s: %s" % (ob or "?", " %s" % t if t else "", v.get("verdict")))
  elif o == "verification_result":
    p = res.get("proof") or {}
    if p.get("polarity"):
      lines.append("Answer %s: GK proved the %s question." % (res.get("answer"), p["polarity"]))
  elif o == "not_found":
    qa = [x for x in view.get("queries") or [] if x["query"]["id"] == (res.get("query") or {}).get("id")]
    depth = ((qa[-1].get("search") or {}).get("depth")) if qa else None
    lines.append("No plan within the search depth%s.  The search is bounded: this is no evidence that no plan "
                 "exists." % (" %s" % depth if depth is not None else ""))
  elif o == "candidate_not_validated":
    lines.append("Candidate plans that the replay rejected:")
    for c in res.get("candidates") or []:
      lines.append("  %s: %s%s" % (clause_text(c.get("plan"), as_json), c.get("verdict"),
                                   " (%s)" % c["reason"] if c.get("reason") else ""))
  elif o == "inconsistent_action_state":
    step = res.get("step")
    lines.append("Facts in conflict%s:" % (" in the initial state" if step == 0 else " after step %s" % step
                                           if step is not None else ""))
    lines += ["  " + str(f) for f in res.get("facts_english") or res.get("facts") or []]
  else:
    diag = _diagnostic_lines(res, rec)
    if diag:
      lines += ["Not answered: %s" % (o or (rec.get("error") or {}).get("kind") or "error")] + diag
  rp = res.get("replay")
  if isinstance(rp, dict) and rp.get("verdict"):
    lines.append("Replay: %s: %s." % (rp["verdict"], rp.get("reason") or ""))
  if lv["logic"]:
    for p in proofs:
      if p.get("proof"):
        lines.append("Proof steps (GK, %s %s):" % (p.get("obligation"), p.get("polarity")))
        lines += proof_lines(p["proof"], as_json)
  return lines


def explanation(rec, view, options):
  """The "Explained:" text of a run, or "" when it has nothing to say."""
  lv = levels(dict(options or {}, prover_explain_flag=True))
  blocks = []
  results = _results(rec)
  if not results and rec.get("error"):
    return ""
  for qid, res in results:
    lines = explain_result(res, rec, view, lv)
    if lines:
      blocks.append(("%s:\n" % qid if qid and len(results) > 1 else "") + "\n".join(lines))
  if not blocks:
    return ""
  return "Explained:\n\n" + "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# the blocks above the result (-logic and above, -prover)


def show_request(stage, attempt, prompt, llm, kind=None):
  """-debug: one model request as it is sent."""
  print("\n=== action stage %d LLM call (%s), request %d%s ===\n" % (stage, llm or "?", attempt + 1,
                                                                     ", %s" % kind if kind else ""))
  print("INPUT:")
  print(prompt)


def show_response(raw, cached):
  """-debug: the raw response of the request just shown."""
  print("\nLLM response obtained from %s" % ("cache" if cached else "the provider"))
  print("RAW OUTPUT:")
  print(raw if raw is not None else "(no response)")


def _stage_json(tr, llm):
  if tr.get("stage1_packages") is not None:
    print("\n=== action stage 1 (ASU JSON, %s) ===\n" % llm)
    pretty.pp_stage1(tr["stage1_packages"])
  s2 = tr.get("stage2")
  if s2:
    print("\n=== action stage 2 (logic JSON, %s) ===\n" % llm)
    envelope = {k: s2[k] for k in ("worlds", "contexts", "query_contexts", "types") if s2.get(k)}
    if envelope:
      print(json.dumps(envelope, ensure_ascii=False))
    pretty.pp_stage2(["and"] + list(s2.get("packages") or []))


def _checks(tr):
  """-details: what the controller found in each response and what it changed."""
  lines = []
  for h in tr.get("history") or []:
    label = "stage %d, request %d" % (h["stage"], h["attempt"] + 1)
    if h.get("kind"):
      label += " (%s)" % h["kind"].replace("_", " ")
    if h.get("skipped"):
      lines.append("  %s: not sent (%s)" % (label, h["skipped"].replace("_", " ")))
      continue
    errors = h.get("errors") or []
    parse = h.get("parse") or {}
    repairs = [k for k in ("repair", "fix_json", "package_repair", "envelope_repair") if parse.get(k)]
    state = "%d error%s" % (len(errors), "" if len(errors) == 1 else "s") if errors else "no error"
    lines.append("  %s: %s%s%s" % (label, state, " (%s)" % ("cached" if h.get("cached") else "live"),
                                   "; parse repairs: %s" % ", ".join(repairs) if repairs else ""))
    lines += ["    " + e for e in errors]
    for n in h.get("normalizations") or []:
      lines.append("    normalization %s" % _normalization(n))
    if h.get("clarification"):
      lines.append("    clarification: %s" % h["clarification"])
  for f in tr.get("class_condition_findings") or []:
    lines.append("  class condition not stated (%s): unit %s, %s" % (
      f.get("confidence"), f.get("unit"), json.dumps(f.get("atom"), ensure_ascii=False)))
  sc = tr.get("semantic_correction")
  if sc:
    lines.append("  semantic correction: %s" % json.dumps(sc, ensure_ascii=False, default=str)[:300])
  if lines:
    print("\n=== translation checks ===\n")
    print("\n".join(lines))


def _normalization(n):
  if not isinstance(n, dict):
    return str(n)
  rest = {k: v for k, v in n.items() if k not in ("kind", "unit")}
  return "%s%s%s" % (n.get("kind", "?"), " %s" % n["unit"] if n.get("unit") else "",
                     ": %s" % json.dumps(rest, ensure_ascii=False, default=str)[:300] if rest else "")


def _source_clauses(src, sent, as_json):
  """-logic: the source clauses, grouped by the sentence they come from.  `clauses` holds every source clause; the
  identity, restriction and policy lists are parts of it."""
  groups = {}
  for c in src.get("clauses") or []:
    unit = c.get("unit") or c.get("type_unit")
    head = sent.get(unit) or ("unit %s" % unit if unit else "[generated: %s]" % c.get("role", "?").replace("_", " "))
    groups.setdefault(head, []).append(c)
  print("\n=== sentences mapped to clauses: ===\n")
  for head, cs in groups.items():
    print(head)
    for c in cs:
      role = (c.get("role") or "").replace("_", " ")
      print("  %-22s %s" % (role, clause_text(c.get("clause"), as_json)))


def _query_block(qa, as_json):
  q = qa.get("query") or {}
  print("\n=== query %s (%s) ===\n" % (q.get("id"), q.get("kind")))
  if q.get("goal") is not None:
    print("  goal: %s" % clause_text(q["goal"], as_json))
  for s in q.get("steps") or q.get("sequence") or []:
    print("  step: %s" % clause_text(s, as_json))
  search = qa.get("search") or {}
  print("  root %s; view %s%s" % (qa.get("planning_root"), qa.get("view"),
                                 "; search depth %s" % search["depth"] if search.get("depth") is not None else ""))
  for x in qa.get("excluded") or []:
    print("  excluded: %s" % json.dumps(x, ensure_ascii=False))
  if qa.get("outcome"):
    print("  outcome before the prover: %s" % json.dumps(qa["outcome"], ensure_ascii=False, default=str)[:300])
  for o in qa.get("obligations") or []:
    pols = [p for p in ("positive", "negative") if o.get(p) is not None]
    print("  obligation %s (%s, %s): %s" % (o["id"], o.get("role"), " and ".join(pols), o.get("text")))


def _launch_objects(launch):
  try:
    return json.loads(launch["input"])
  except (ValueError, KeyError, TypeError):
    return None


def input_lines(objs, sent, library="summary", src=None):
  """The prover input, one clause per line, with a comment line before each sentence's clauses.  `library` is
  "summary" (one comment line for the library laws), "full" or "none"."""
  lines, prev = [], None
  laws = [o for o in objs if isinstance(o, dict) and is_law(o.get("@name"))]
  for o in objs:
    if not isinstance(o, dict):
      continue
    name = o.get("@name", "")
    if is_law(name):
      continue
    units = units_of(name, src)
    head = " ".join(sent.get(u) or u for u in units) if units else "[generated]" if name.startswith("src:") \
      else "[question]"
    if head != prev:
      lines.append("// " + head)
      prev = head
    lines.append(json.dumps(o, ensure_ascii=False))
  if laws and library == "summary":
    lines.append("// [library axioms_action.js: %d laws; -debug prints them]" % len(laws))
  elif laws and library == "full":
    lines.append("// [library]")
    lines += [json.dumps(o, ensure_ascii=False) for o in laws]
  return lines


def _launch_blocks(launches, sent, lv, src=None):
  n = len(launches)
  shown = None
  for i, launch in enumerate(launches):
    tag = "launch %d of %d: %s" % (i + 1, n, launch.get("label") or launch.get("role"))
    objs = _launch_objects(launch)
    if objs is not None:
      print("\n=== prover input (JSON), %s ===\n" % tag)
      base = [o for o in objs if not str(o.get("@name", "")).startswith("query:")]
      if shown is not None and base == shown[1]:
        print("// the source and library clauses of launch %d" % shown[0])
        print("\n".join(input_lines([o for o in objs if o not in base], sent, "none", src)))
      else:
        shown = (i + 1, base)
        print("\n".join(input_lines(objs, sent, "full" if lv["debug"] else "summary", src)))
    if lv["debug"] or lv["prover"]:
      print("\n=== prover params, %s ===\n" % tag)
      print(" ".join(launch.get("command") or []))
    print("\n=== prover result (JSON), %s ===\n" % tag)
    print((launch.get("stdout") or "").strip() or "(no output; %s)" % ((launch.get("stderr") or "").strip()[:300] or "empty"))
    rl = launch.get("relaunch")
    if rl and (lv["debug"] or lv["prover"]):
      print("\n=== termination relaunch, %s ===\n" % tag)
      print(" ".join(rl.get("command") or []))
      print("\n".join(rl.get("lines") or []) or "(no termination line)")


def _calls_by_stage(tr):
  out = {}
  for h in (tr or {}).get("history") or []:
    if h.get("skipped"):
      continue
    c = out.setdefault("stage%d" % h["stage"], {"calls": 0, "live": 0, "corrections": 0})
    c["calls"] += 1
    c["live"] += 0 if h.get("cached") else 1
    c["corrections"] += 1 if h["attempt"] > 0 else 0
  return out


def stage_rows(rec, view):
  """The rows of the stages block: [(name, text, answered)]."""
  rows = []
  tr = rec.get("translation")
  if rec.get("input") == "formal":
    rows.append(("translation", "not run: a formal input", False))
  elif tr:
    counts = _calls_by_stage(tr)
    for stage in ("stage1", "stage2"):
      c = counts.get(stage)
      if not c:
        rows.append((stage, "not run", False))
        continue
      if stage == "stage1":
        state = "accepted" if tr.get("stage1_units") is not None else "failed"
      else:
        state = {"ok": "accepted", "unsupported_translation": "unsupported meaning",
                 "translation_invalid": "invalid"}.get(tr.get("status"), tr.get("status") or "?")
      rows.append((stage, "%d request%s (%d live, %d correction%s): %s" % (
        c["calls"], "" if c["calls"] == 1 else "s", c["live"], c["corrections"],
        "" if c["corrections"] == 1 else "s", state), False))
  src = view.get("source")
  if src:
    n = len(src.get("clauses") or [])
    support = src.get("support") or {}
    rows.append(("compile", "%s: %d units, %d clauses%s" % (
      support.get("status"), len(src.get("units") or []), n,
      "; %s" % ", ".join(support.get("reasons") or []) if support.get("reasons") else ""), False))
  for qa in view.get("queries") or []:
    q = qa.get("query") or {}
    rows.append(("query", "%s %s: root %s, view %s, %d obligation%s%s" % (
      q.get("id"), q.get("kind"), qa.get("planning_root"), qa.get("view"), len(qa.get("obligations") or []),
      "" if len(qa.get("obligations") or []) == 1 else "s",
      "; %s" % qa["outcome"].get("outcome") if qa.get("outcome") else ""), False))
  results = _results(rec)
  for qid, res in results:
    prefix = "%s " % qid if qid else ""
    launches = ((res.get("evidence") or {}).get("launches")) or []
    if view.get("nosolve"):
      rows.append(("prover", prefix + "not run (-nosolve)", False))
      continue
    if launches:
      rows.append(("prover", prefix + "%d launch%s: %s" % (len(launches), "" if len(launches) == 1 else "es", "; ".join(
        "%s %s %.2f s" % (launch.get("role"), launch.get("result") or launch.get("status"), launch.get("elapsed") or 0)
        for launch in launches)), False))
    rp = res.get("replay")
    if isinstance(rp, dict) and rp.get("verdict"):
      rows.append(("replay", prefix + "%s: %s" % (rp["verdict"], rp.get("reason") or ""), False))
    rows.append(("answer", prefix + (res.get("outcome") or "?"), True))
  if rec.get("error"):
    rows.append(("error", "%s: %s" % (rec["error"].get("kind"), rec["error"].get("message")), False))
  return rows


def _stages(rec, view):
  print("\n=== stages ===\n")
  for name, text, answered in stage_rows(rec, view):
    print("  %-12s %s%s" % (name, text, "  <- the answer" if answered else ""))


def show(rec, view, options, text=None, llm=None):
  """Print the route's blocks above the result, at the levels the options ask for."""
  lv = levels(options)
  if not (lv["logic"] or lv["prover"]):
    return
  tr = rec.get("translation") or {}
  sent = sentences(view)
  if lv["details"] and tr:
    _stage_json(tr, llm or "?")
    _checks(tr)
  if lv["logic"]:
    if tr.get("stage1_packages") and text:
      import solve_display
      solve_display.show_simplified_to(text, tr["stage1_packages"])
    if view.get("source"):
      _source_clauses(view["source"], sent, lv["json"])
    for qa in view.get("queries") or []:
      _query_block(qa, lv["json"])
  if lv["details"] or lv["prover"]:
    _launch_blocks(view.get("launches") or [], sent, lv, view.get("source"))
  if lv["logic"]:
    _stages(rec, view)


# ---------------------------------------------------------------------------
# -gkin, -rawresult


def gk_input_text(launch, sent, path=None, src=None):
  """A launch's input as a GK input file: the command as the first comment line, then one clause per line."""
  cmd = [path if x == "<input>" and path else x for x in launch.get("command") or []]
  lines = input_lines(_launch_objects(launch) or [], sent, "full", src)
  last = max([i for i, x in enumerate(lines) if not x.startswith("//")] or [-1])
  # the clauses are the elements of one JSON list: a comma after each but the last, none after a comment line
  body = [x if x.startswith("//") or i == last else x + "," for i, x in enumerate(lines)]
  return "// " + shlex.join(cmd) + "\n[\n" + "\n".join(body) + "\n]\n"


def write_gkin(path, launches, view):
  """-gkin FILE: each launch's input.  One launch is written to FILE, several to FILE with the launch label before its
  extension.  Returns the paths written."""
  sent = sentences(view)
  written = []
  stem, ext = os.path.splitext(path)
  for launch in launches:
    p = path if len(launches) == 1 else "%s.%s%s" % (stem, (launch.get("label") or launch.get("role")).replace(":", "_"), ext)
    with open(p, "w") as f:
      f.write(gk_input_text(launch, sent, p, view.get("source")))
    written.append(p)
  return written


def raw_result(launches):
  """-rawresult: the raw GK output, each launch's after a comment line naming it when there are several."""
  if len(launches) == 1:
    return (launches[0].get("stdout") or "").strip()
  return "\n".join("// launch %s\n%s" % (launch.get("label") or launch.get("role"), (launch.get("stdout") or "").strip())
                   for launch in launches)


# ---------------------------------------------------------------------------
# -summary


def summary_record(rec, answer, route_choice=None):
  """The record `-summary` prints for an action-route call."""
  calls = _calls_by_stage(rec.get("translation"))
  results = [r for _, r in _results(rec)]
  launches = [launch for r in results for launch in ((r.get("evidence") or {}).get("launches") or [])]
  by_role = {}
  for launch in launches:
    by_role[launch.get("role")] = by_role.get(launch.get("role"), 0) + 1
  res = rec.get("result") or {}
  rp = res.get("replay") if isinstance(res.get("replay"), dict) else {}
  outcome = res.get("outcome") or (rec.get("error") or {}).get("kind")
  if outcome == "several":
    # one answer line per query
    answer = "; ".join(x for x in str(answer or "").split("\n") if x.strip())
    outcome = "; ".join("%s %s" % (qid, r.get("outcome")) for qid, r in _results(rec))
  return {"pipeline": "actions", "answer": _first_line(answer), "route_choice": route_choice,
          "input": rec.get("input"), "outcome": outcome,
          "replay": rp.get("verdict"), "confidence": res.get("confidence"),
          "llm_call_counts": calls, "llm_calls_total": sum(c["calls"] for c in calls.values()),
          "llm_calls_live": sum(c["live"] for c in calls.values()),
          "gk_launches": len(launches), "gk_by_role": by_role,
          "gk_seconds": round(sum(launch.get("elapsed") or 0 for launch in launches), 3)}


def summary_lines(rec):
  """The lines of an action-route summary block, after the answer and pipeline lines."""
  parts = []
  for tag in sorted(rec["llm_call_counts"]):
    c = rec["llm_call_counts"][tag]
    parts.append("%s %d (live %d%s)" % (tag, c["calls"], c["live"],
                                        ", corrections %d" % c["corrections"] if c["corrections"] else ""))
  return ["outcome: %s%s%s" % (rec["outcome"], "   replay: %s" % rec["replay"] if rec.get("replay") else "",
                               "   confidence: %s" % rec["confidence"] if rec.get("confidence") is not None else ""),
          "llm calls: %s; total %d, live %d" % ("; ".join(parts) or "none", rec["llm_calls_total"],
                                                 rec["llm_calls_live"]),
          "gk launches: %d%s; %.2f s" % (rec["gk_launches"], " (%s)" % ", ".join(
            "%s %d" % kv for kv in sorted(rec["gk_by_role"].items())) if rec["gk_by_role"] else "",
                                          rec["gk_seconds"])]
