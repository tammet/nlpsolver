"""WP05 unit checks, encoding v2: the maintained action library, its templates, roles and views.

No model, no GK.  The checks read `axioms_action.js` and
`axioms_action.templates.json` through `lc_action_library`; they prove
structure, not provability:

  provenance  the signed experimental copy is unchanged; every template is a
              signed poss law with -can replaced by the $source placeholder,
              = by -differ and the hook added; the stated-endpoint template
              is the public movement template without connected; the kept
              clauses equal the signed copy once each context term is
              written back as ?:C, and the file equals the archived 1.3-dev
              the same way; hash and version agree with the role index; a
              changed file, index or template file is rejected, and so is a
              clause outside the per-literal context pattern
  paths       the four executability defaults are the only positive poss
              heads of the executable file; each is its template with the
              default's class conditions and the denial-marker blocker; both
              put_on branches; placement and movement require differ
  hooks       one default hook per constructor; selection drops exactly the
              defaults of the restricted constructors
  denial      one consequence: execution_denied(ACT) gives -poss(ACT); no
              library clause concludes the marker; no can, action_available,
              capability link, necessity or route in the file
  effects     the strict negative effects and their markers are present and
              paired; no effect, marker or frame concludes poss or a hook
  views       snapshot holds no effect, marker, frame or reachability clause
              and no situation or world variable or successor term; it is
              bound to the planning root; a knower replaces $obj in every
              view; verify holds no reachability; discovery holds everything
  boundary    every fluent-like literal has situation and the context
              $ctxt(present, ?:W, L, $obj); static predicates have neither;
              no clause relates the two arities
  gold        the gold clause patterns that name the library are matched
  artifact    a source artifact records the library id, version, hash, role
              index hash and template hash
"""

import copy
import hashlib
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "solver"))
import action_route as ar
import fixture_materialize as fm
import lc_action as la
import lc_action_library as lib

import lc_action_situate as sit
SIGNED = os.path.join(ROOT, "elogs", "action_axioms_2026_09_05", "axioms_action.js")
SIGNED_SHA = "0b08ced1bea08bb1b2a48b6c6c3c52a5557260616f62ce547c3cd90192b4f4da"
# the archived libraries of the migration: 1.3-dev (the situation before the single context variable ?:C) and
# 1.3-dev.1b (the situation before the per-literal context $ctxt(present, ?:W, L, $obj))
ARCHIVE = os.path.join(ROOT, "elogs", "encoding_v2_migration_2026_09_23")
PREVIOUS = ((os.path.join(ARCHIVE, "lib_1.3-dev", "axioms_action.js"), "874c98917a61e269e621eddf370f292816e7cb2f26ae3e4b37d1a57dc2bcdea0"),
            (os.path.join(ARCHIVE, "lib_1.3-dev.1b", "axioms_action.js"), "88249b25668e339390f074b13ec0b8a0ab28eb7269524b57b027aeae01b7efce"))
# the archived 2.0.0 files: 2.0.1 has the same clauses and templates, with corrected comments (Astra's review R3)
SAME = (os.path.join(ARCHIVE, "lib_2.0.0", "axioms_action.js"), "0f141858cb57ba61f78d6d2854d3f13bcfe5f06add4f1d9e1b39efd0ea890ae1",
        os.path.join(ARCHIVE, "lib_2.0.0", "axioms_action.templates.json"), "087843ec63fcea8877a40e03dd95702c827e79612b0a72c99a9a3e937b337d18")
VERSION = "2.0.1"


def ctx(loc, situation="?:S"):
  """The text of a library context term, as the file writes it."""
  return '["$ctxt", "present", %s, "%s", "$obj"]' % (json.dumps(situation), loc)


def _old_context(t):
  return isinstance(t, list) and len(t) == 5 and t[:3] == ["$ctxt", "present", "?:W"] and t[4] == "$obj"


def as_single_context(x):
  """A clause written in the form of 1.3-dev and of the signed copy: [P, args..., S, ?:C], reachable(S, N, ?:C).

  Reads the 2.0.0 form (the situation in the world slot) and the 1.3-dev.1b form (the situation before the
  per-literal context); a clause already in the single-context form is unchanged."""
  if isinstance(x, dict):
    return {k: as_single_context(v) for k, v in x.items()}
  if not isinstance(x, list):
    return x
  if x and isinstance(x[0], str) and x[0].lstrip("-") == "reachable" and len(x) == 3:
    return [x[0], as_single_context(x[1]), as_single_context(x[2]), "?:C"]
  if x and isinstance(x[0], str) and x[0].lstrip("-") == "reachable" and len(x) == 4 and _old_context(x[3]):
    return [as_single_context(y) for y in x[:3]] + ["?:C"]
  if x and isinstance(x[0], str) and lib.law_context(x[-1]):
    return [as_single_context(y) for y in x[:-1]] + [as_single_context(x[-1][2]), "?:C"]
  if x and isinstance(x[0], str) and _old_context(x[-1]):
    return [as_single_context(y) for y in x[:-1]] + ["?:C"]
  return [as_single_context(y) for y in x]
NEGATIVE_EFFECTS = {"eff_move_not_at": "chg_move_from", "eff_take_not_empty": "chg_take_empty",
                    "eff_take_not_on": "chg_take_on", "eff_put_on_not_holding": "chg_put_on_holding",
                    "eff_put_on_not_clear": "chg_put_on_clear", "eff_put_in_not_holding": "chg_put_in_holding"}
# template -> the signed poss law it comes from
TEMPLATE_SOURCE = {"tpl_move_public": "poss_move", "tpl_take": "poss_take", "tpl_put_on_block": "poss_put_on_block",
                   "tpl_put_on_surface": "poss_put_on_surface", "tpl_put_in": "poss_put_in", "tpl_change": "poss_change"}
DEFAULTS = ("poss_move_person", "poss_take_hand", "poss_put_on_hand_block", "poss_put_on_hand_surface")
OLD = ("can", "action_available", "capability_denied", "route_for")


class Bad(Exception):
  pass


def with_pending(a, name="a_later_pass"):
  """A copy of a source artifact that names one more pending pass, rehashed."""
  b = copy.deepcopy(a)
  b["pending_passes"].append(name)
  b["hashes"] = ar.source_hashes(b)
  return b


def need(cond, message):
  if not cond:
    raise Bad(message)


def by_name(L):
  return {c["name"]: c for c in L["clauses"]}


def lib_role(L, name):
  return by_name(L)[name]["role"]


def expect_error(fn, what):
  try:
    fn()
  except lib.LibraryError:
    return
  raise Bad("%s: accepted" % what)


def as_template(signed_lits, k):
  """A signed poss law read as its v2 template: -can -> -$source, = -> -differ, the hook before poss."""
  out = []
  for x in signed_lits:
    if x[0] == "-can":
      out.append(["-" + lib.SOURCE] + x[2:])
    elif x[0] == "=":
      out.append(["-differ"] + x[1:])
    elif x[0] == "poss":
      out.append(["-" + lib.hook_name(k)] + x[1:])
      out.append(x)
    else:
      out.append(x)
  return out


def check_provenance(L):
  need(L["id"] == "axioms_action.js" and L["version"] == VERSION and len(L["sha256"]) == 64
       and len(L["roles_sha256"]) == 64 and len(L["templates_sha256"]) == 64, "library identity %r" % (L["id"],))
  need(L["derived_from"]["sha256"] == SIGNED_SHA, "the index names another source copy")
  tpl = {t["name"]: t for t in L["templates"]}
  need(sorted(tpl) == sorted(lib.TEMPLATE_NAMES), "templates: %s" % sorted(tpl))
  # elogs/ is local: each archive comparison runs where its archive exists, and the report names the skipped ones
  ran, skipped = [], []
  if os.path.exists(SIGNED):
    ran.append("the signed copy")
    raw = open(SIGNED, "rb").read()
    need(hashlib.sha256(raw).hexdigest() == SIGNED_SHA, "the signed experimental library changed")
    old = {}
    for c in json.loads(lib.strip_comments(raw.decode("utf-8"))):
      if isinstance(c, dict):
        old[c["@name"]] = c
      else:
        old["standard_mode_" + c[1]] = {"@name": "standard_mode_" + c[1], "@logic": c}
    new = {c["name"]: c["clause"] for c in L["clauses"]}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    need(added == sorted(["ok_%s_default" % k for k in la.CONSTRUCTORS] + list(DEFAULTS) + ["denied_not_poss"]),
         "added clauses: %s" % added)
    need(removed == sorted(["can_move_person", "can_take_hand", "can_put_on_hand"] + sorted(TEMPLATE_SOURCE.values())),
         "removed clauses: %s" % removed)
    changed = sorted(n for n in new if n in old and old[n] != as_single_context(new[n]))
    need(changed == [], "kept clauses must equal the signed copy but for the context terms: %s" % changed)
    for t, src in sorted(TEMPLATE_SOURCE.items()):
      k = tpl[t]["constructor"]
      need(as_single_context(lib.literals(tpl[t]["clause"])) == as_template(lib.literals(old[src]), k),
           "%s is the signed %s with the placeholder, differ and the hook" % (t, src))
    pub, stated = lib.literals(tpl["tpl_move_public"]["clause"]), lib.literals(tpl["tpl_move_stated"]["clause"])
    need([x for x in pub if x[0] != "-connected"] == stated, "the stated-endpoint template is the public one without connected")
  else:
    skipped.append("the signed copy")
  for path, digest in PREVIOUS:   # the archived migration libraries: the same clauses but for the context terms
    label = os.path.basename(os.path.dirname(path))
    if not os.path.exists(path):
      skipped.append(label)
      continue
    ran.append(label)
    raw = open(path, "rb").read()
    need(hashlib.sha256(raw).hexdigest() == digest, "the archived library %s changed" % path)
    prev = {c["@name"]: as_single_context(c) for c in json.loads(lib.strip_comments(raw.decode("utf-8")))}
    need(sorted(prev) == sorted(c["name"] for c in L["clauses"]), "%s has other clauses than %s" % (VERSION, path))
    diff = sorted(c["name"] for c in L["clauses"] if as_single_context(c["clause"]) != prev[c["name"]])
    need(diff == [], "%s differs from %s in more than the context terms: %s" % (VERSION, path, diff))
  js, js_sha, tp, tp_sha = SAME
  if os.path.exists(js) and os.path.exists(tp):
    ran.append("lib_2.0.0")
    raw = open(js, "rb").read()
    need(hashlib.sha256(raw).hexdigest() == js_sha and hashlib.sha256(open(tp, "rb").read()).hexdigest() == tp_sha,
         "the archived 2.0.0 files changed")
    prev = json.loads(lib.strip_comments(raw.decode("utf-8")))
    need([{"name": c["@name"], "clause": c} for c in prev] == [{"name": c["name"], "clause": c["clause"]} for c in L["clauses"]],
         "%s has other clauses than 2.0.0" % VERSION)
    need(json.load(open(tp))["templates"] == json.load(open(lib.TEMPLATES))["templates"], "%s has other templates than 2.0.0" % VERSION)
  else:
    skipped.append("lib_2.0.0")
  # a changed library, index or template file is rejected
  tmp = tempfile.mkdtemp()
  try:
    a, b, t = (os.path.join(tmp, "axioms_action.js"), os.path.join(tmp, "axioms_action.roles.json"),
               os.path.join(tmp, "axioms_action.templates.json"))
    shutil.copy(lib.LIBRARY, a)
    shutil.copy(lib.INDEX, b)
    shutil.copy(lib.TEMPLATES, t)
    lib.load(a, b, t)
    with open(a, "a") as f:
      f.write("\n")
    expect_error(lambda: lib.load(a, b, t), "a library whose bytes changed")
    shutil.copy(lib.LIBRARY, a)
    idx = json.load(open(b))
    for name, edit in (("a missing role", lambda i: i["roles"].pop("poss_take_hand")),
                       ("an unknown role", lambda i: i["roles"].update(poss_take_hand="physics")),
                       ("a role for a clause that does not exist", lambda i: i["roles"].update(poss_fly="applicability_default")),
                       ("an effect labelled as a static helper", lambda i: i["roles"].update(eff_move_at="static_helper")),
                       ("a default labelled as an effect", lambda i: i["roles"].update(poss_take_hand="effect")),
                       ("an old 1.2.0 role", lambda i: i["roles"].update(poss_take_hand="applicability")),
                       ("another library name", lambda i: i.update(library="axioms_other.js")),
                       ("a null version", lambda i: i.update(version=None)),
                       ("an empty version", lambda i: i.update(version=" ")),
                       ("a numeric version", lambda i: i.update(version=1)),
                       ("provenance as a string", lambda i: i.update(derived_from="the signed copy")),
                       ("provenance without a date", lambda i: i["derived_from"].pop("date")),
                       ("a short provenance hash", lambda i: i["derived_from"].update(sha256="0b08ced1")),
                       ("an upper-case library hash", lambda i: i.update(sha256=i["sha256"].upper())),
                       ("an extra top-level field", lambda i: i.update(comment="x")),
                       ("a missing top-level field", lambda i: i.pop("derived_from")),
                       ("roles as a list", lambda i: i.update(roles=sorted(i["roles"]))),
                       ("a role that is not a string", lambda i: i["roles"].update(poss_take_hand=["applicability_default"]))):
      j = copy.deepcopy(idx)
      edit(j)
      json.dump(j, open(b, "w"))
      expect_error(lambda: lib.load(a, b, t), name)
    json.dump(idx, open(b, "w"))
    # clause mutations of the executable file, each with a rehashed index
    src = open(lib.LIBRARY).read()
    take_hook = '["-ok_take", ["take", "?:H", "?:X"], %s],\n  ["poss", ["take", "?:H", "?:X"], %s],' % (ctx("?:L4"), ctx("?:L5"))
    denial = '["-execution_denied", "?:ACT", %s],\n  ["-poss", "?:ACT", %s]' % (ctx("?:L"), ctx("?:L"))
    frame_on = '["is rel2", "on", "?:X", "?:Y", %s],' % ctx("?:L", ["$do", "?:A", "?:S"])
    ok_take = '["ok_take", ["take", "?:H", "?:X"], %s]' % ctx("?:L1")
    for name, old, new in (
        ("a consequence with another action", denial, denial.replace('["-poss", "?:ACT",', '["-poss", "?:ACT2",')),
        ("a consequence with another situation", denial, '["-execution_denied", "?:ACT", %s],\n  ["-poss", "?:ACT", %s]'
         % (ctx("?:L"), ctx("?:L", "?:S2"))),
        ("a consequence with another context", denial, '["-execution_denied", "?:ACT", %s],\n  ["-poss", "?:ACT", %s]'
         % (ctx("?:L"), ctx("?:L2"))),
        ("a consequence of an unknown constructor", denial, denial.replace('"?:ACT"', '["fly", "?:A"]')),
        ("a default without the hook", take_hook, '["poss", ["take", "?:H", "?:X"], %s],' % ctx("?:L5")),
        ("a default blocked by the negated head", '["$block", 0, ["execution_denied", ["take", "?:H", "?:X"], %s]]' % ctx("?:L5"),
         '["$block", 0, ["$not", ["poss", ["take", "?:H", "?:X"], %s]]]' % ctx("?:L5")),
        ("a default blocker with another context than its head", '["$block", 0, ["execution_denied", ["take", "?:H", "?:X"], %s]]' % ctx("?:L5"),
         '["$block", 0, ["execution_denied", ["take", "?:H", "?:X"], %s]]' % ctx("?:L6")),
        ("a $source literal in the executable file", '["-isa", "hand", "?:H"], ["-isa", "block", "?:X"],\n  ["-has property", "empty"',
         '["-$source", ["take", "?:H", "?:X"], %s], ["-isa", "hand", "?:H"], ["-isa", "block", "?:X"],\n  ["-has property", "empty"' % ctx("?:L9")),
        ("a clause concluding the marker", '{"@name": "ok_move_default", "@logic": ["ok_move"',
         '{"@name": "ok_move_default", "@logic": ["execution_denied"'),
        ("a literal with the single context variable ?:C", ok_take, '["ok_take", ["take", "?:H", "?:X"], "?:C"]'),
        ("a literal with a separate situation argument (the 1.3 layout)", ok_take,
         '["ok_take", ["take", "?:H", "?:X"], "?:S", %s]' % ctx("?:L1")),
        ("a law context with a world constant", ok_take, '["ok_take", ["take", "?:H", "?:X"], %s]' % ctx("?:L1", "W0")),
        ("a law context with a knower variable", ok_take,
         '["ok_take", ["take", "?:H", "?:X"], ["$ctxt", "present", "?:S", "?:L1", "?:K"]]'),
        ("a law context with a past tense", ok_take, '["ok_take", ["take", "?:H", "?:X"], ["$ctxt", "past", "?:S", "?:L1", "$obj"]]'),
        ("a frame whose conclusion has another location than its premise", frame_on,
         frame_on.replace(ctx("?:L", ["$do", "?:A", "?:S"]), ctx("?:L7", ["$do", "?:A", "?:S"]))),
        ("a frame whose conclusion stands at the current situation", frame_on, frame_on.replace(ctx("?:L", ["$do", "?:A", "?:S"]), ctx("?:L"))),
        ("a reachability step with a context term", '["reachable", ["$do", "?:A", "?:S"], "?:N"]',
         '["reachable", ["$do", "?:A", "?:S"], "?:N", %s]' % ctx("?:L3")),
        ("two atoms of a default sharing one location", '["-has property", "clear_top", "?:X", %s]' % ctx("?:L2"),
         '["-has property", "clear_top", "?:X", %s]' % ctx("?:L1"))):
      need(src.count(old) == 1, "mutation source not found: %s" % name)
      open(a, "w").write(src.replace(old, new))
      j = copy.deepcopy(idx)
      j["sha256"] = hashlib.sha256(open(a, "rb").read()).hexdigest()
      json.dump(j, open(b, "w"))
      expect_error(lambda: lib.load(a, b, t), name)
    shutil.copy(lib.LIBRARY, a)
    json.dump(idx, open(b, "w"))
    # template mutations
    tdoc = json.load(open(lib.TEMPLATES))
    for name, edit in (
        ("a template with two $source literals", lambda d: d["templates"][2]["clause"]["@logic"].insert(1, copy.deepcopy(d["templates"][2]["clause"]["@logic"][0]))),
        ("a template without $source", lambda d: d["templates"][2]["clause"]["@logic"].pop(0)),
        ("a template without the hook", lambda d: d["templates"][2]["clause"]["@logic"].pop(-2)),
        ("a template for another constructor", lambda d: d["templates"][2].update(constructor="move")),
        ("a template with a blocker", lambda d: d["templates"][2]["clause"]["@logic"].append(["$block", 0, ["execution_denied", ["take", "?:H", "?:X"], json.loads(ctx("?:L5"))]])),
        ("a template with the single context variable ?:C", lambda d: d["templates"][2]["clause"]["@logic"][2].__setitem__(-1, "?:C")),
        ("a template sharing one location between two atoms", lambda d: d["templates"][2]["clause"]["@logic"][3].__setitem__(-1, json.loads(ctx("?:L1")))),
        ("a missing template", lambda d: d["templates"].pop()),
        ("a template of another version", lambda d: d.update(version="9.9.9")),
        ("a template with an extra field", lambda d: d["templates"][0].update(extra=1)),
        ("a default whose template changed", lambda d: d["templates"][2]["clause"]["@logic"].pop(2))):
      j = copy.deepcopy(tdoc)
      edit(j)
      json.dump(j, open(t, "w"))
      expect_error(lambda: lib.load(a, b, t), name)
    shutil.copy(lib.TEMPLATES, t)
    for name, text in (("a list-valued index", "[1, 2]"), ("a string index", '"roles"'), ("malformed JSON", "{roles:")):
      open(b, "w").write(text)
      expect_error(lambda: lib.load(a, b, t), name)
    expect_error(lambda: lib.load(a, os.path.join(tmp, "missing.json"), t), "a missing index")
    json.dump(idx, open(b, "w"))
    expect_error(lambda: lib.load(a, b, os.path.join(tmp, "missing.json")), "a missing template file")
    # the index digest follows the content, not the whitespace
    json.dump(idx, open(b, "w"), indent=4, sort_keys=True)
    need(lib.load(a, b, t)["roles_sha256"] == L["roles_sha256"], "the index digest depends on whitespace or key order")
    # the template hash follows the bytes
    with open(t, "a") as f:
      f.write("\n")
    need(lib.load(a, b, t)["templates_sha256"] != L["templates_sha256"], "the template hash ignores the file's bytes")
  finally:
    shutil.rmtree(tmp)
  print("  provenance: version %s, sha256 %s..., role index %s..., templates %s...; the templates are the signed poss laws "
        "with the placeholder, differ and the hook; kept clauses equal the signed copy, 1.3-dev and 1.3-dev.1b but for the context "
        "terms, and the clauses and templates of 2.0.0; archive comparisons run: %s; skipped (archive absent): %s"
        % (L["version"], L["sha256"][:12], L["roles_sha256"][:12], L["templates_sha256"][:12], ", ".join(ran) or "none",
           ", ".join(skipped) or "none"))


def check_paths(L):
  paths = {}
  for c in L["clauses"]:
    poss = lib.head(c["clause"], "poss")
    if poss is None:
      continue
    need(c["role"] == "applicability_default", "%s concludes poss" % c["name"])
    lits = lib.literals(c["clause"])
    k = poss[1][0]
    paths.setdefault(k, []).append(c["name"])
    body = [x for x in lits if not lib.positive(x)]
    hook = [x for x in body if lib.predicate(x) == "ok_" + k]
    block = [x for x in lits if x[0] == "$block"]
    need(len(hook) == 1 and hook[0][1:-1] == poss[1:-1] and lib.law_context(hook[0][-1]) and sit.situation_of(hook[0]) == sit.situation_of(poss)
         and hook[0][-1][3] != poss[-1][3],
         "%s: the hook on the same action and situation, with its own location variable" % c["name"])
    need(block == [["$block", 0, [lib.MARKER] + poss[1:]]], "%s: blocked by the denial marker of its action" % c["name"])
    need(not any(x[0] == "=" for x in lits), "%s: the equality shortcut remains" % c["name"])
    if k in ("move", "put_on"):
      d = [x for x in body if lib.predicate(x) == "differ"]
      need(len(d) == 1 and d[0][1:] == poss[1][2:4], "%s: differ on %s" % (c["name"], poss[1][2:4]))
  need(sorted(paths) == ["move", "put_on", "take"], "constructors with a default: %s" % sorted(paths))
  need(sorted(paths["put_on"]) == ["poss_put_on_hand_block", "poss_put_on_hand_surface"], "both put_on branches: %s" % paths["put_on"])
  take = [lib.predicate(x) + ":" + str(x[1]) for x in lib.literals(by_name(L)["poss_take_hand"]["clause"]) if not lib.positive(x)]
  need(take == ["isa:hand", "isa:block", "has property:empty", "has property:clear_top", "is rel2:on", "ok_take:['take', '?:H', '?:X']"],
       "take coverage: hand, block, empty hand, clear top, on a support: %s" % take)
  for t in L["templates"]:
    lits = lib.literals(t["clause"])
    need([x[0] for x in lits].count("-" + lib.SOURCE) == 1 and lits[-2][0] == "-" + lib.hook_name(t["constructor"]),
         "%s: one placeholder and the hook" % t["name"])
    if t["constructor"] in ("move", "put_on", "put_in"):
      need(sum(1 for x in lits if x[0] == "-differ") == 1, "%s: differ" % t["name"])
  need(not any(lib.predicate(x) == lib.SOURCE for c in L["clauses"] for x in lib.literals(c["clause"])),
       "the executable file holds no $source literal")
  print("  paths: %d executability defaults, each its template with the class conditions, the hook and the marker blocker; "
        "both put_on branches; %d templates with one placeholder and the hook" % (sum(len(v) for v in paths.values()), len(L["templates"])))


def check_hooks(L):
  defaults = [c for c in L["clauses"] if c["role"] == "hook_default"]
  need(sorted(lib.predicate(lib.literals(c["clause"])[0]) for c in defaults) == sorted("ok_" + k for k in la.CONSTRUCTORS), "one default hook per constructor")
  for c in defaults:
    lit = lib.literals(c["clause"])[0]
    need(all(isinstance(t, str) and t.startswith("?:") for t in lit[1][1:]) and len(set(lit[1][1:])) == len(lit[1][1:]),
         "%s must hold for every action of its constructor" % c["name"])
  for restricted in ((), ("take",), ("take", "move"), tuple(la.CONSTRUCTORS)):
    names = {c["name"] for c in lib.select(L, "discovery", restricted) if c["role"] == "hook_default"}
    need(names == {"ok_%s_default" % k for k in la.CONSTRUCTORS if k not in restricted}, "selection with %s: %s" % (restricted, sorted(names)))
    full = {c["name"] for c in lib.select(L, "discovery", restricted)}
    need(len(full) == len(L["clauses"]) - len(restricted), "a restriction removes its default hook and nothing else")
  expect_error(lambda: lib.select(L, "discovery", ("fly",)), "an unknown constructor")
  expect_error(lambda: lib.select(L, "everything"), "an unknown view")
  print("  hooks: 5 default hooks; a restricted constructor loses its default hook and nothing else")


def check_denial(L):
  neg = [c for c in L["clauses"] if any(lib.predicate(x) == "poss" and not lib.positive(x) for x in lib.literals(c["clause"]))
         and c["role"] not in ("effect", "frame", "reachability")]
  need([c["name"] for c in neg] == ["denied_not_poss"], "negative poss clauses: %s" % [c["name"] for c in neg])
  c = json.loads(ctx("?:L"))
  need(lib.literals(neg[0]["clause"]) == [["-" + lib.MARKER, "?:ACT", c], ["-poss", "?:ACT", c]],
       "the consequence repeats one context term: %r" % lib.literals(neg[0]["clause"]))
  need(not any(lib.head(c["clause"], lib.MARKER) for c in L["clauses"]), "no library clause derives %s" % lib.MARKER)
  need(not any(lib.predicate(x) in OLD for c in L["clauses"] for x in lib.literals(c["clause"])),
       "no can, action_available, capability_denied or route_for in the file")
  need(sorted({c["role"] for c in L["clauses"]}) == sorted(lib.ROLES), "roles: %s" % sorted({c["role"] for c in L["clauses"]}))
  print("  denial: one consequence execution_denied(ACT) -> -poss(ACT); no clause derives the marker; no can, "
        "action_available, capability link, necessity or route")


def check_effects(L):
  names = by_name(L)
  for eff, marker in sorted(NEGATIVE_EFFECTS.items()):
    need(eff in names and marker in names, "%s and %s must both be present" % (eff, marker))
    e = [x for x in lib.literals(names[eff]["clause"]) if lib.is_successor(sit.situation_of(x))][0]
    m = [x for x in lib.literals(names[marker]["clause"]) if lib.positive(x)][0]
    se, sm = sit.situation_of(e), sit.situation_of(m)
    need(e[0].startswith("-") and se == sm and se[1][0] == sm[1][0], "%s and %s write into the same successor" % (eff, marker))
  for c in L["clauses"]:
    if c["role"] in ("effect", "marker", "frame", "derived_no_inertia"):
      heads = [lib.predicate(x) for x in lib.literals(c["clause"]) if lib.positive(x) and lib.predicate(x) != "$block"]
      need(not any(h == "poss" or h.startswith("ok_") for h in heads), "%s grants executability" % c["name"])
  change = [c["name"] for c in L["clauses"] if c["role"] in ("effect", "marker") and "change" in c["name"]]
  need(change == ["eff_change"], "change writes its value and deletes nothing: %s" % change)
  need(not any(c["role"] == "applicability_default" and lib.head(c["clause"], "poss")[1][0] in ("put_in", "change") for c in L["clauses"]),
       "put_in and change have no source-free permission")
  have = [x for x in lib.literals(names["eff_put_on_not_holding"]["clause"]) if lib.predicate(x) == "have"]
  need(not have and "eff_put_on_not_have" not in names, "putting down removes holding, not possession")
  print("  effects: %d strict negative effects, each paired with its marker; no effect grants executability; change deletes nothing"
        % len(NEGATIVE_EFFECTS))


def _strings(x):
  if isinstance(x, list):
    for y in x:
      for z in _strings(y):
        yield z
  elif isinstance(x, str):
    yield x


def check_views(L):
  snap = lib.select(L, "snapshot")
  need({c["role"] for c in snap} == set(lib.SNAPSHOT_ROLES), "snapshot roles: %s" % sorted({c["role"] for c in snap}))
  for c in snap:
    words = set(_strings(c["clause"]["@logic"]))
    need(lib.SITUATION not in words and "$do" not in words and "reachable" not in words
         and not any(w.startswith("changed_") for w in words), "snapshot clause %s still reaches another situation" % c["name"])
  poss = [c for c in snap if c["name"] == "poss_take_hand"][0]
  need(sit.situation_of(lib.head(poss["clause"], "poss")) == "W0" and all(sit.situation_of(x) == "W0" for x in lib.literals(poss["clause"])
                                                             if lib.predicate(x) in lib.FLUENT_LIKE),
       "snapshot laws are specialized to the root W0")
  # the root binding and the knower (migration step 1b.4): W1 at the root W1; the knower in place of $obj
  w1 = lib.select(L, "snapshot", root="W1", knower="Bob 7")
  poss = [c for c in w1 if c["name"] == "poss_take_hand"][0]
  need(all(sit.situation_of(x) == "W1" and x[-1][4] == "#:Bob 7" for x in lib.literals(poss["clause"])
           if lib.predicate(x) in lib.FLUENT_LIKE), "the root W1 and the knower Bob: %r" % poss["clause"])
  need(not any(lib.OBJ in _strings(c["clause"]["@logic"]) for c in lib.select(L, "discovery", knower="Bob 7")),
       "a knower replaces $obj in every view")
  gen = [c for c in lib.select(L, "verify", root="W1") if c["name"] == "frame_on"][0]
  need(lib.SITUATION in _strings(gen["clause"]["@logic"]),
       "the verify view keeps its laws general at any root")
  need(len({lib.view_hash(lib.select(L, "snapshot", root=r)) for r in ("W0", "W1", "W2")}) == 3, "the view hash covers the root")
  expect_error(lambda: lib.select(L, "snapshot", root="s0"), "a root that is not a world name")
  expect_error(lambda: lib.select(L, "snapshot", root="?:S"), "a variable root")
  need(sit.situation_of(lib.head(by_name(L)["poss_take_hand"]["clause"], "poss")) == lib.SITUATION, "selection must not change the loaded library")
  verify = lib.select(L, "verify")
  need({c["role"] for c in verify} == set(lib.ROLES) - {"reachability"}, "verify holds everything but reachability")
  need(len(lib.select(L, "discovery")) == len(L["clauses"]), "discovery holds every clause")
  need(len({lib.view_hash(lib.select(L, v)) for v in lib.VIEW_ROLES}) == 3 and lib.view_hash(snap) == lib.view_hash(lib.select(L, "snapshot")),
       "view hashes are stable and distinct")
  for field, value in (("name", "poss_take_renamed"), ("role", "frame")):
    changed = copy.deepcopy(snap)
    changed[0][field] = value
    need(lib.view_hash(changed) != lib.view_hash(snap), "the view hash ignores a record's %s" % field)
  need(not any("$source" in json.dumps(c["clause"]) for v in lib.VIEW_ROLES for c in lib.select(L, v)), "a template reached a view")
  print("  views: snapshot %d clauses bound to the root without effects, markers, frames or reachability; verify %d; discovery %d; "
        "no template in a view"
        % (len(snap), len(verify), len(L["clauses"])))


def check_boundary(L):
  for c in L["clauses"] + [dict(t, clause=t["clause"]) for t in L["templates"]]:
    for x in lib.literals(c["clause"]):
      p = lib.predicate(x)
      if p == "$block":
        x = x[2][1] if x[2][0] == "$not" else x[2]
        p = lib.predicate(x)
      if p in lib.FLUENT_LIKE and p != "reachable":
        need(lib.law_context(x[-1]), "%s: %s lacks the context with its situation" % (c["name"], p))
        need(not any(y == lib.SITUATION or lib.is_successor(y) for y in x[1:-1]), "%s: %s has a situation outside the context" % (c["name"], p))
        want = {"is rel2": 5, "has property": 4, "have": 4, "poss": 3, lib.MARKER: 3, lib.SOURCE: 3}.get(p)
        need(want is None or len(x) == want, "%s: %s has the ordinary arity plus the context" % (c["name"], p))
      elif p == "reachable":
        need(len(x) == 3 and "$ctxt" not in json.dumps(x), "%s: reachable(S, N) has no context term" % c["name"])
      elif p in ("isa", "connected", "differ", "standard_mode", "surface", "derived_property"):
        need(lib.SITUATION not in x and "$ctxt" not in json.dumps(x), "%s: static %s must hold no situation" % (c["name"], p))
  print("  boundary: every fluent-like literal ends with the context $ctxt(present, S, L, $obj), its situation in the world slot and "
        "nowhere else; reachable(S, N) has no context; static predicates have neither")


def instance_matches(pattern, lit):
  """A gold library pattern names an instance; the library law is general."""
  atom = lit[:-1]
  if lib.predicate(atom) != pattern[0] or len(atom) != len(pattern):
    return False
  binding = {}
  for p, t in zip(pattern[1:], atom[1:]):
    if isinstance(t, str) and t.startswith("?:"):
      if binding.setdefault(t, p) != p and not la.is_var(p):
        return False
    elif t != p:
      return False
  return True


def check_gold(L):
  n = 0
  eff = [c for c in L["clauses"] if c["role"] == "effect"]
  markers = [c for c in L["clauses"] if c["role"] in ("marker", "derived_no_inertia")]
  for case in fm.load_all():
    for g in case["units"]:
      cl = g.get("clauses") or {}
      for p in cl.get("must_have", []):
        if p.get("role") == "denial_consequence" and p.get("unit") == "library":
          need([c["name"] for c in L["clauses"] if c["role"] == "denial_consequence"] == ["denied_not_poss"],
               "%s: %s" % (case["case"], json.dumps(p)))
          n += 1
        if p.get("role") == "effect" and p.get("unit") == "library":
          hit = []
          for c in eff:
            head = [x for x in lib.literals(c["clause"]) if lib.is_successor(sit.situation_of(x))][0]
            if lib.positive(head) == (p["sign"] == "+") and instance_matches(p["lit"], head):
              hit.append((c, head))
          need(hit, "%s/%s: no library effect for %s" % (case["case"], g["id"], json.dumps(p)))
          if p.get("marker") and p["sign"] == "-":
            ok = any(sit.situation_of(lib.literals(m["clause"])[-1])[1][0] == sit.situation_of(h)[1][0] for c, h in hit for m in markers)
            need(ok, "%s/%s: the negative library effect has no marker" % (case["case"], g["id"]))
          n += 1
      for p in cl.get("must_not_have", []):
        if p.get("unit") == "library" and p.get("role") == "necessity_restriction":
          # a poss is refuted by the denial consequence only, never by a branch condition of the library
          bad = [c["name"] for c in L["clauses"] if c["role"] != "denial_consequence"
                 and any(lib.predicate(x) == "poss" and not lib.positive(x) for x in lib.literals(c["clause"]))
                 and lib.head(c["clause"], "poss") is None and c["role"] not in ("effect", "frame", "reachability")]
          need(not bad, "%s: the library refutes poss from a branch condition: %s" % (case["case"], bad))
          n += 1
  need(n >= 8, "the gold library patterns were not found")
  print("  gold: %d gold clause patterns that name the library are satisfied" % n)


def check_artifact(L):
  S = lambda f, i: ["@id", i, ["holds", "W0", f]]
  a = ar.compile_source(None, [S(["isa", "person", "Ann 1"], "S1")], la.PROFILE, None, {"Ann 1": "person"})
  need(a["library"] == {"id": L["id"], "version": L["version"], "hash": L["sha256"], "roles_hash": L["roles_sha256"],
                        "templates_hash": L["templates_sha256"], "status": "selected"}, "artifact library: %r" % a["library"])
  need(lib.PASS in a["passes"] and lib.PASS not in a["pending_passes"], "pass bookkeeping")
  need([c["name"] for c in ar.library_view(a, "snapshot")] == [c["name"] for c in lib.select(L, "snapshot")], "library_view")
  for field, value in (("hash", "0" * 64), ("roles_hash", "0" * 64), ("templates_hash", "0" * 64), ("id", "axioms_other.js"),
                       ("version", "9.9.9"), ("status", "guessed")):
    other = copy.deepcopy(a)
    other["library"][field] = value
    other["hashes"] = ar.source_hashes(other)      # a caller who recomputes the ordinary hashes
    need(other["hashes"]["source"] != a["hashes"]["source"], "the library %s is part of the source hash" % field)
    try:
      ar.library_view(other, "snapshot")
      raise Bad("a source artifact with another library %s was accepted" % field)
    except ar.ArtifactError:
      pass
  o = ar.compile_source(None, [S(["isa", "animal", "Ann 1"], "S1")], la.ORDINARY, None, {"Ann 1": "person"})
  need(o["library"]["status"] == "not_selected" and lib.PASS not in o["passes"], "the ordinary profile selects no action library")
  need(ar.source_outcome(a)["outcome"] == "source_compiled" and ar.source_outcome(with_pending(a))["outcome"] == ar.NOT_IMPLEMENTED,
       "a source with a pending pass is not source_compiled; one without is")
  print("  artifact: a source artifact records library id, version, hash, role-index hash and template hash; another revision is rejected")


def run():
  L = lib.load()
  check_provenance(L)
  check_paths(L)
  check_hooks(L)
  check_denial(L)
  check_effects(L)
  check_views(L)
  check_boundary(L)
  check_gold(L)
  check_artifact(L)


if __name__ == "__main__":
  run()
