"""Planning pilot v2: English -> sidecar -> planning_ir -> plan.

Stage-1C form of the pilot (improvement plan
memos/MEMO_2026_09_01_planpilot_improvement_plan.md).  The two model calls
and their prompts are unchanged from pilot v1; everything after them runs
the E11 stack:

  sidecar + task JSON
    -> planning_normalize_pilot_v1.import_pilot_v1   (marked legacy importer)
    -> planning_ir.validate                          (E4 strict validation)
    -> planning_compile.compile_ir                   (E3/E5/E7 semantics)
    -> planning_explore.solve                        (E1/E2 application, A1/E8 codes)
    -> planning_gk.ground_theory -> plan_footprints  (gk proves the found plan)

The explorer is the semantics oracle: it finds the shortest plan and its
result codes decide the category.  A found plan is then handed to gk at
exactly that depth; gkc runs when gk fails for any reason (A2); if both
fail, the explorer plan is reported and attributed as an explorer plan.
Every record names its backend.  A strict-profile shadow result is recorded
beside the answer, so no completion is attributed to the English (E6).

The pilot-v1 converter (MOVE_VERBS, argument semantics, verb-keyed merging)
is gone; the pre-switchover file is preserved at
elogs/planpilot_2026_09_01/stage1c/planpilot_pilot_v1_stage0.py.

  python3 solver/planpilot.py "Alice is in Haapsalu. ... How can Alice get to Tallinn?"
  python3 solver/planpilot.py -tests tests/tests_planning.py -llm deepseek [-limit N] [-filter S]
  flags: -llm NAME  -seconds N (gk per depth, default 5)  -maxdepth N
         -profile pilot_v1_defaults|classical_planning|source_strict
         -out DIR (new run directory; default elogs/planpilot_runs/<stamp>_<llm>)
"""

import hashlib, json, os, re, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import plan_footprints as pf
import planning_ir as pir
import planning_normalize_pilot_v1 as pv1
import planning_compile as pc
import planning_explore as px
import planning_gk as pgk

GK = os.environ.get("PLANPILOT_GK", "/opt/nlpsolver/gk/gk")
GKC = os.environ.get("PLANPILOT_GKC", "/opt/gkc/gkc")
DATA = os.environ.get("PLANPILOT_GK_DATA", "/opt/nlpsolver/gk")
STRAT = '{"strategy":["negative_pref","posunitpara"],"query_preference":1}'
RUNBASE = os.path.join(ROOT, "elogs", "planpilot_runs")
PROMPTS = os.path.join(ROOT, "prompts", "planning_pilot")

GK_SECONDS = 5
MAX_DEPTH = 8
IMPERATIVES = ("build ", "make ", "get ", "bring ", "achieve ", "put ", "stack ",
               "deliver ", "move ", "take ", "ensure ")


def prompt(name):
  with open(os.path.join(PROMPTS, name), encoding="utf-8") as f:
    return f.read()


def sha(obj):
  return hashlib.sha256(json.dumps(obj, sort_keys=True,
                                   default=str).encode()).hexdigest()


def code_revision():
  try:
    rev = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                         capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                           capture_output=True, text=True).stdout.strip()
    return (rev or "unknown") + ("+dirty" if dirty else "")
  except Exception:
    return "unknown"


def run_provenance(llm):
  """P2: frozen before the first call of a run."""
  prov = {"run_id": time.strftime("%Y%m%d_%H%M%S", time.gmtime()),
          "code_revision": code_revision(),
          "prompt_sha256": {n: hashlib.sha256(prompt(n).encode()).hexdigest()
                            for n in ("domain_system.txt", "task_system.txt")},
          "llm": llm, "strategy": STRAT, "gk": GK, "gkc": GKC}
  try:
    import llmcall
    prov["llm_version"] = {"gpt": llmcall.gptversion,
                           "claude": llmcall.claudeversion,
                           "gemini": llmcall.geminiversion,
                           "deepseek": llmcall.deepseekversion}.get(llm, "unknown")
  except Exception:
    prov["llm_version"] = "unknown (llmcall unavailable)"
  return prov


def new_run_dir(llm, out=None):
  path = out or os.path.join(RUNBASE, "%s_%s"
                             % (time.strftime("%Y%m%d_%H%M%S", time.gmtime()), llm))
  os.makedirs(path, exist_ok=False)   # P2: immutable, never overwritten
  return path


def parse_json_reply(raw):
  if not isinstance(raw, str) or not raw.strip():
    raise ValueError("empty model reply")
  text = raw.strip()
  if text.startswith("```"):
    lines = text.splitlines()
    if lines[0].strip().lower() in ("```", "```json"):
      lines = lines[1:]
    if lines and lines[-1].strip() == "```":
      lines = lines[:-1]
    text = "\n".join(lines).strip()
  try:
    return json.loads(text)
  except json.JSONDecodeError as first:
    left, right = text.find("{"), text.rfind("}")
    if left >= 0 and right > left:
      try:
        return json.loads(text[left:right + 1])
      except json.JSONDecodeError:
        pass
    raise ValueError("invalid JSON: %s" % first)


def call_json(system, user, llm, record, tag):
  import llmcall
  from llmcall import call_llm

  def one(user_text, tag2):
    n0 = len(llmcall.call_log)
    raw = call_llm(system, user_text, llm=llm)
    record["calls"].append({"tag": tag2, "chars": len(raw or ""), "raw": raw,
                            "llm_log": [dict(r) for r in llmcall.call_log[n0:]]})
    return raw

  raw = one(user, tag)
  try:
    return parse_json_reply(raw), None
  except Exception as first:
    fix = user + "\n\nYour previous reply was invalid: %s\nReturn one corrected JSON object only." % first
    raw2 = one(fix, tag + "_retry")
    try:
      return parse_json_reply(raw2), None
    except Exception as second:
      return None, "unparsable %s reply: %s" % (tag, second)


# ---------------------------------------------------------------- text split

def split_text(text):
  sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
  domain, task = [], []
  for i, s in enumerate(sents):
    low = s.lower()
    if s.endswith("?"):
      task.append(s)
    elif i == len(sents) - 1 and any(low.startswith(v) for v in IMPERATIVES) \
        and " can " not in low and " if " not in low:
      task.append(s)
    else:
      domain.append(s)
  return " ".join(domain), " ".join(task)


# ---------------------------------------------------------------- provers

class _R:
  def __init__(self, p):
    dec = lambda b: (b or b"").decode("utf-8", errors="replace")
    self.stdout, self.stderr, self.returncode = dec(p.stdout), dec(p.stderr), p.returncode


def run(cmd):
  return _R(subprocess.run(cmd, capture_output=True))


def unwind(term):
  steps = []
  while isinstance(term, list) and term and term[0] == "$do":
    steps.append(term[1])
    term = term[2]
  steps.reverse()
  return steps


def gk_answer_term(a):
  ans = a.get("answer")
  if isinstance(ans, list) and ans and isinstance(ans[0], list) and len(ans[0]) > 1:
    return ans[0][1]
  return None


def run_gk(name, clauses, seconds, outdir):
  path = os.path.join(outdir, "input_%s.js" % name)
  json.dump(clauses, open(path, "w"), indent=1)
  cmd = [GK, "-seconds", str(seconds), "-strategytext", STRAT, path,
         "-taxonomy", "-confidence", "0.1", "-keepconfidence", "0.1", "-datafolder", DATA]
  t0 = time.time()
  p = run(cmd)
  el = round(time.time() - t0, 2)
  open(os.path.join(outdir, "output_%s.json" % name), "w").write(p.stdout)
  try:
    d = json.loads(p.stdout)
  except Exception:
    return {"result": "PARSE-FAIL", "seconds": el, "answers": [], "stderr": p.stderr[:200]}
  answers = []
  for a in d.get("answers", []):
    if a.get("confidence", 0) < 0.1:
      continue
    answers.append({"confidence": round(a.get("confidence", 0), 4),
                    "term": gk_answer_term(a)})
  return {"result": d.get("result"), "seconds": el, "answers": answers}


def parse_term_text(s):
  s = s.strip().rstrip(".")
  i = s.find("(")
  if i < 0:
    return s
  name, inner = s[:i], s[i + 1:s.rfind(")")]
  args, depth, cur = [], 0, ""
  for ch in inner:
    if ch == "(":
      depth += 1
    if ch == ")":
      depth -= 1
    if ch == "," and depth == 0:
      args.append(parse_term_text(cur))
      cur = ""
    else:
      cur += ch
  if cur.strip():
    args.append(parse_term_text(cur))
  return [name] + args


def run_gkc(name, clauses, seconds, outdir):
  path = os.path.join(outdir, "input_%s.js" % name)
  json.dump(clauses, open(path, "w"), indent=1)
  cmd = [GKC, path, "-seconds", str(seconds), "-strategytext",
         '{"strategy":["negative_pref"],"query_preference":1}']
  t0 = time.time()
  p = run(cmd)
  el = round(time.time() - t0, 2)
  open(os.path.join(outdir, "output_%s_gkc.txt" % name), "w").write(p.stdout)
  result, answer = "no proof", None
  for line in p.stdout.splitlines():
    if line.startswith("result:"):
      result = line.split(":", 1)[1].strip()
    elif line.startswith("answer:") and answer is None:
      answer = line.split(":", 1)[1].strip()
  term = None
  if answer:
    t = parse_term_text(answer)
    if isinstance(t, list) and t and t[0] == "$ans" and len(t) > 1:
      term = t[1]
  return {"result": result, "seconds": el,
          "answers": ([{"confidence": 1.0, "term": term}] if term is not None else [])}


# ---------------------------------------------------------------- solving

def registry_from_ir(dom, ir):
  """The frozen registry shown to the task call, built from the IR."""
  return {"objects": dom.get("objects", []),
          "predicates": {f["fluent"]: f["arity"] for f in ir.get("fluents", [])},
          "occurrences": [{"schema": o.get("schema"), "args": o.get("args")}
                          for o in dom.get("occurrences", [])],
          "schemas": [{"id": s.get("id"), "verb": s.get("verb"),
                       "args": [a.get("role") for a in s.get("args", [])]}
                      for s in dom.get("schemas", []) if s.get("id")]}


def prove_plan_with_gk(rec, model, base, report, plan, seconds, name, outdir,
                       backends):
  """A2: gk proves the explorer's plan length; gkc on any gk failure; the
  explorer plan is the attributed fallback.  Returns (backend, plan)."""
  theory, aux = pgk.ground_theory(model, base, report)
  if theory is None:
    rec["gk"] = {"skipped": aux}
    return "explorer", plan
  name_map = aux
  depth = len(plan)
  rows = pf.Compiler(theory).compile(depth, pgk.goal_atoms(model))
  rec["clauses"] = len(rows)
  rec["ground_actions"] = len(theory["actions"])
  if "gk" in backends:
    # one run at the known depth replaces the pilot's per-depth iteration,
    # so it gets three depth budgets; the ground theory is larger than the
    # pilot's schematic one
    gk = run_gk("%s_d%d" % (name, depth), rows, seconds * 3, outdir)
    rec["gk"] = gk
    got = _mapped_plan(gk, name_map, model, base, report)
    if got is not None:
      return "gk", got
  if "gkc" in backends:
    gkc = run_gkc("%s_d%d" % (name, depth), rows, seconds * 2, outdir)
    rec["gkc"] = gkc
    got = _mapped_plan(gkc, name_map, model, base, report)
    if got is not None:
      return "gkc", got
  return "explorer", plan


def _mapped_plan(prover_out, name_map, model, base, report):
  for a in prover_out.get("answers", []):
    steps = unwind(a.get("term"))
    mapped = pgk.plan_from_term(name_map, steps) if steps else None
    if not mapped:
      continue
    ok, _, _, _ = px.replay(model, base, mapped, report)
    if ok:
      return mapped
    report["diagnostics"].append("prover plan failed replay: %r" % (mapped,))
  return None


def solve_sidecar(dom, task, llm="offline", seconds=GK_SECONDS,
                  maxdepth=MAX_DEPTH, name="case", outdir=None, rec=None,
                  backends=("gk", "gkc", "explorer"), profile=None):
  """The deterministic part: stored or fresh sidecar+task JSON -> record."""
  rec = rec if rec is not None else {"llm": llm, "calls": [], "t0": time.time()}
  outdir = outdir or new_run_dir(llm)
  rec["sidecar"], rec["task"] = dom, task

  ir, import_notes = pv1.import_pilot_v1(dom, task)
  if profile:
    ir["completion_profile"] = {"name": profile,
                                "switches": dict(pir.PROFILES[profile])}
  rec["ir"] = ir
  rec["import_notes"] = import_notes
  rec["hashes"] = {"sidecar": sha(dom), "task": sha(task), "ir": sha(ir)}

  kind = (task or {}).get("kind", "plan")
  rec["kind"] = kind
  errs = pir.validate(ir)
  if errs:
    rec["validation_errors"] = errs
    codes = sorted({e["code"] for e in errs})
    if codes == ["unknown_goal_fluent"]:
      preds = sorted({e["detail"] for e in errs})
      rec["category"] = "unknown goal"
      rec["answer"] = "The goal uses predicates the passage never defines: %s." \
          % ", ".join(preds)
    else:
      rec["category"] = "conversion failed"
      rec["answer"] = "The translation fails validation: %s." % ", ".join(codes)
      rec["error"] = "validation: " + ", ".join(codes)
    return finish(rec)

  if kind == "truth":
    rec["category"] = "not a planning task"
    rec["answer"] = "This is an ordinary question; the planning pilot does not answer it."
    return finish(rec)

  model, report = pc.compile_ir(ir)
  assert model is not None    # validation passed above
  base = px.base_state(model, report)
  if model["occurrences"]:
    base2 = px.apply_occurrences(model, base, report)
    if base2 is None:
      rec["category"] = "incomplete action model"
      rec["answer"] = "No result: effect closure is off, occurrences cannot be applied."
      rec["report"] = report_fields(report)
      return finish(rec)
    base = base2
  out = px.solve(model, report, maxdepth=maxdepth, base=base)
  rec["outcome"] = {k: out.get(k) for k in
                    ("result", "holds", "depth", "states_seen", "exhausted",
                     "certificate", "searched_depth_cap", "witness")}
  rec["user_bound"] = (task or {}).get("user_bound")

  # E6: the source-only shadow result, so no completion is attributed to the
  # English.  Explorer only; assumptions of the main run stay separate.
  try:
    smodel, sreport = pc.compile_ir(ir, "source_strict")
    sout = px.solve(smodel, sreport, maxdepth=maxdepth)
    rec["strict"] = {"result": sout.get("result"), "holds": sout.get("holds")}
  except Exception as e:
    rec["strict"] = {"error": str(e)}

  backend, plan = None, None
  if kind in ("narrative",):
    rec["category"] = "narrative " + out["holds"]
    occ = ["%s" % pc.render_step(model, o["schema"],
                                 px._occurrence_values(model, o["schema"], o["bindings"]))
           for o in model["occurrences"]]
    rec["answer"] = {"yes": "Yes", "no": "No",
                     "unknown": "Unknown from the stated facts"}[out["holds"]] + \
        ((" (after: %s)" % "; ".join(occ)) if occ else "")
  elif kind == "verification":
    ok = out["plan_valid"] is True and out["holds"] == "yes"
    rec["category"] = "verification " + ("yes" if ok else "no")
    if out["plan_valid"] is not True:
      why = next((d for d in report["diagnostics"] if "fails at step" in d),
                 "the sequence is not executable")
    elif out["holds"] != "yes":
      why = "the sequence runs but the goal is not established"
    else:
      why = ""
    rec["answer"] = "Yes, the sequence works." if ok else "No: %s." % why
    plan, backend = out.get("plan"), "explorer"
  elif out["result"] == "plan_found":
    backend, plan = prove_plan_with_gk(rec, model, base, report, out["plan"],
                                       seconds, name, outdir, backends)
    rec["category"] = "plan found"
    steps_en = [pc.render_step(model, sid, values) for sid, values in plan]
    rec["plan_english"] = steps_en
    lead = "Plan (%d step%s): " % (len(steps_en), "s" if len(steps_en) != 1 else "")
    body = "; ".join("%d) %s" % (i + 1, s) for i, s in enumerate(steps_en))
    rec["answer"] = ("Yes. " if kind == "reachability" else "") + lead + body
  elif out["result"] == "proved_unreachable_in_finite_closed_model":
    rec["category"] = "proved unreachable"
    rec["answer"] = "No plan exists: the goal is unreachable in the closed " \
        "model (%d states, frontier exhausted)." % out["states_seen"]
  elif out["result"] == "no_plan_within_user_bound":
    rec["category"] = "no plan within bound"
    note = next((d for d in report["diagnostics"] if "reachable at depth" in d), "")
    rec["answer"] = "No plan within %d steps%s." % (
      out.get("depth") or rec.get("user_bound") or maxdepth,
      (" (%s)" % note) if note else "")
  elif out["result"] == "search_budget_exhausted":
    rec["category"] = "no plan found"
    rec["answer"] = "No plan found within the search budget."
  elif out["result"] == "incomplete_action_model":
    rec["category"] = "incomplete action model"
    why = "; ".join(report["certificate_blockers"]) or \
        "; ".join(report["diagnostics"][-2:])
    rec["answer"] = "No result: the action model is incomplete: %s." % why
  else:
    rec["category"] = "conversion failed"
    rec["answer"] = "No result (%r)." % (out["result"],)

  if plan is not None:
    rec["plan"] = [[sid] + list(values) for sid, values in plan]
  rec["backend"] = backend
  rec["report"] = report_fields(report)
  return finish(rec)


def report_fields(report):
  return {"diagnostics": report["diagnostics"],
          "assumptions": report["assumptions"],
          "certificate_blockers": report["certificate_blockers"],
          "profile": (report["profile"] or {}).get("name")}


def solve(text, llm="gemini", seconds=GK_SECONDS, maxdepth=MAX_DEPTH,
          name="case", outdir=None, backends=("gk", "gkc", "explorer"),
          profile=None):
  rec = {"text": text, "llm": llm, "calls": [], "t0": time.time(),
         "provenance": run_provenance(llm)}
  outdir = outdir or new_run_dir(llm)

  domain_text, task_text = split_text(text)
  rec["domain_text"], rec["task_text"] = domain_text, task_text
  if not task_text:
    task_text = "(no task; translate the domain only)"

  dom, err = call_json(prompt("domain_system.txt"), domain_text, llm, rec, "domain")
  rec["sidecar"] = dom
  if err:
    rec.update({"category": "conversion failed", "error": err})
    return finish(rec)

  dom_ir, _ = pv1.import_pilot_v1(dom, None)
  registry = registry_from_ir(dom, dom_ir)
  task, err = call_json(prompt("task_system.txt"),
                        "Registry: %s\nTask: %s" % (json.dumps(registry), task_text),
                        llm, rec, "task")
  rec["task"] = task
  if err:
    rec.update({"category": "conversion failed", "error": err})
    return finish(rec)

  return solve_sidecar(dom, task, llm=llm, seconds=seconds, maxdepth=maxdepth,
                       name=name, outdir=outdir, rec=rec, backends=backends,
                       profile=profile)


def finish(rec):
  rec["seconds_total"] = round(time.time() - rec.pop("t0"), 2)
  return rec


# ---------------------------------------------------------------- batch

def expected_ok(rec, expected):
  cat = rec.get("category", "")
  if expected.startswith("plan"):
    if cat != "plan found":
      return False
    if "!" in expected:
      want = int(expected.split("!")[1])
      return len(rec.get("plan") or []) == want
    return True
  if expected == "yes":
    return cat in ("plan found", "narrative yes", "verification yes")
  if expected == "no":
    return cat in ("narrative no", "verification no")
  # Stage-0 split of the old "noplan" (improvement plan P1/E8), refined by
  # the 1C categories: a certified exhaustion is the strong closed-model no,
  # a complete bounded search the weaker one; both pass noplan_closed.
  # "no plan found" (budget) and "unknown goal" pass neither.
  if expected == "noplan_closed":
    return cat in ("proved unreachable", "no plan within bound")
  if expected == "noplan_incomplete":
    return cat == "incomplete action model"
  if expected == "truth":
    return cat == "not a planning task"
  return False


def run_tests(path, llm, limit=None, pattern=None, seconds=GK_SECONDS,
              maxdepth=MAX_DEPTH, out=None, profile=None):
  import importlib.util
  spec = importlib.util.spec_from_file_location("tests_planning", path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  cases = mod.PLANNING_TESTS
  if pattern:
    cases = [c for c in cases if pattern in c[0]]
  if limit:
    cases = cases[:int(limit)]
  outdir = new_run_dir(llm, out)
  # P2: the run manifest is written before the first call
  manifest = dict(run_provenance(llm), tests=path, cases=len(cases),
                  seconds=seconds, maxdepth=maxdepth,
                  profile=profile or "pilot_v1_defaults (importer)")
  json.dump(manifest, open(os.path.join(outdir, "run.json"), "w"), indent=1)
  print("run directory:", outdir)
  okc = 0
  rows = []
  for cid, text, expected in cases:
    rec = solve(text, llm=llm, seconds=seconds, maxdepth=maxdepth, name=cid,
                outdir=outdir, profile=profile)
    rec["case_id"], rec["expected"] = cid, expected
    rec["ok"] = expected_ok(rec, expected)
    okc += bool(rec["ok"])
    json.dump(rec, open(os.path.join(outdir, "case_%s.json" % cid), "w"),
              indent=1, default=str)
    rows.append(rec)
    plan = "; ".join(rec.get("plan_english", [])) if rec.get("plan_english") else "-"
    print("%-24s %-6s %-26s %-4s %5.1fs %-9s %s" % (
      cid, expected, rec.get("category", "?"), "OK" if rec["ok"] else "FAIL",
      rec.get("seconds_total", 0), rec.get("backend") or "-", plan[:60]))
    sys.stdout.flush()
  print("\n%s: %d/%d correct" % (llm, okc, len(rows)))
  json.dump([{k: r.get(k) for k in ("case_id", "expected", "ok", "category",
                                    "kind", "backend", "plan_english",
                                    "seconds_total")}
             for r in rows],
            open(os.path.join(outdir, "summary.json"), "w"), indent=1)
  return rows


def main():
  args = sys.argv[1:]
  def flag(name, default=None):
    if name in args:
      i = args.index(name)
      v = args[i + 1]
      del args[i:i + 2]
      return v
    return default
  llm = flag("-llm", "gemini")
  seconds = int(flag("-seconds", GK_SECONDS))
  maxdepth = int(flag("-maxdepth", MAX_DEPTH))
  tests = flag("-tests")
  limit = flag("-limit")
  pattern = flag("-filter")
  out = flag("-out")
  profile = flag("-profile")
  if tests:
    run_tests(tests, llm, limit, pattern, seconds, maxdepth, out, profile)
    return
  if not args:
    print(__doc__)
    return
  rec = solve(" ".join(args), llm=llm, seconds=seconds, maxdepth=maxdepth,
              outdir=out and new_run_dir(llm, out), profile=profile)
  print("Answer:", rec.get("answer"))
  print("Category:", rec.get("category"))
  if rec.get("backend"):
    print("Backend:", rec["backend"])
  rep = rec.get("report") or {}
  if rep.get("assumptions"):
    print("Assumptions:", "; ".join("%s x%d" % kv
                                    for kv in sorted(rep["assumptions"].items())))
  if rep.get("diagnostics"):
    print("Diagnostics:", "; ".join(map(str, rep["diagnostics"])))
  if rec.get("strict"):
    print("Strict-profile result:", rec["strict"])


if __name__ == "__main__":
  main()
