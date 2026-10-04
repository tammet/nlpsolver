"""The English of the action route: entity names, plan sentences, facts and the answer text.

  render(source, plan, steps=None)      -> the plan as one sentence: "Ann goes from Haapsalu to Tallinn by bus, then ..."
  plan_steps(source, plan, steps=None)  -> one sentence per step, the actor always named
  plan_fields(source, plan, steps=None) -> render, plan_steps, plan_named and plan_verbs of a found plan
  fact_english(source, atom)            -> one fact: "the hand holds block a"
  answer_text(result)                   -> the answer string of a result record

A step repeats its actor only when the actor changes; a change step uses the source verb when the unit that permits
it has exactly one Stage-1 capability action (`Ann paints the gate red`), and otherwise states the new property
(`Ann makes the gate red`).  The answer text has one fixed form per question kind and outcome, `Cannot answer: ...`
for a text the route reads and does not model, and `Error: ...` for a failed run.
"""

import json
import re

import lc_action as la
from linguistics import indef_article, third_person


# ---------------------------------------------------------------------------
# names and plans


def entity_word(t):
  """An entity id without its index: `block a` for `block a 3`; any other term as it is."""
  return t.rsplit(" ", 1)[0] if la.is_concrete(t) else t


def _witness_class(source, w):
  for rec in source["clauses"] or []:
    for lit in rec["clause"]:
      if isinstance(lit, list) and len(lit) == 3 and lit[0] == "isa" and lit[2] == w:
        return lit[1]
  return None


def _stated_class(source, t):
  """The class that the source states for a concrete entity: a type record's class, else a class fact of a
  description (the first in unit order), else None."""
  for rec in source.get("types") or []:
    if rec.get("entity") == t and isinstance(rec.get("class"), str):
      return rec["class"]
  for u in source["units"]:
    if not str(u.get("form") or "").startswith("description"):
      continue
    body = (u.get("stage2") or [None, None, None])[2]
    if isinstance(body, list) and body[:1] == ["and"] and len(body) == 3 and isinstance(body[1], list):
      body = body[1]
    if isinstance(body, list) and body[:1] == ["holds"] and len(body) == 3:
      for a in la.conjuncts(body[2]):
        if isinstance(a, list) and len(a) == 3 and a[0] == "isa" and a[2] == t and isinstance(a[1], str):
          return a[1]
  return None


def name(source, t):
  """An entity as a reader names it: a proper name as it is, a one-letter id with its class (block a), a Skolem
  witness by its class (the cook), anything else with `the` (the egg).  The class of a one-letter id comes from the
  identity map, else from a class that the source states."""
  if isinstance(t, str) and t.startswith("sk_"):
    cls = _witness_class(source, t)
    return "the %s" % cls if cls else t
  w = entity_word(t)
  if w[:1].isupper():
    return w
  if len(w) == 1:
    cls = ((source["identity"] or {}).get(t) or {}).get("class") or _stated_class(source, t)
    return "%s %s" % (cls, w) if cls else w
  return "the %s" % w


def plain_name(source, t):
  """An entity without its index and article, as `plan_named` holds it: `Oskar`, `hand`, `a`; a Skolem witness by its
  class; a lexical value (a mode, a property, `unspecified`) as written."""
  if isinstance(t, str) and t.startswith("sk_"):
    return _witness_class(source, t) or t
  return entity_word(t) if la.is_concrete(t) else t


def plan_named(source, plan):
  """The plan terms with names in place of entity ids: ["move", "Oskar", "Lund", "Malmo", "bus"]."""
  return [[a[0]] + [plain_name(source, t) for t in a[1:]] for a in plan or []]


def capitalized(text):
  """The text with a capital first letter."""
  return text[:1].upper() + text[1:] if text else text


def _source_units(steps, i):
  if not steps or i >= len(steps):
    return []
  out = []
  for p in steps[i]["paths"]:
    if p["holds"] and not p["default"]:
      out.append(p["path"].split(" ")[0])
  return out


def _stage1_action(source, uid):
  """The one Stage-1 capability action of a unit, or None when the unit has none or more than one."""
  u = [x for x in source["units"] if x["id"] == uid]
  s1 = (u[0].get("stage1") or {}) if u else {}
  acts = [a for a in s1.get("actions") or [] if a.get("mode") == "capability"]
  return acts[0] if len(acts) == 1 else None


# past participles that the regular rule does not give
IRREGULAR_PARTICIPLES = {
  "be": ("been",), "beat": ("beaten",), "bend": ("bent",), "bite": ("bitten",), "blow": ("blown",),
  "break": ("broken",), "bring": ("brought",), "build": ("built",), "burn": ("burnt", "burned"), "buy": ("bought",),
  "catch": ("caught",), "choose": ("chosen",), "cut": ("cut",), "dig": ("dug",), "do": ("done",), "draw": ("drawn",),
  "drink": ("drunk",), "drive": ("driven",), "eat": ("eaten",), "fall": ("fallen",), "feed": ("fed",),
  "find": ("found",), "fly": ("flown",), "forget": ("forgotten",), "freeze": ("frozen",), "get": ("got", "gotten"),
  "give": ("given",), "go": ("gone",), "grind": ("ground",), "grow": ("grown",), "hang": ("hung",), "hide": ("hidden",),
  "hit": ("hit",), "hold": ("held",), "keep": ("kept",), "lay": ("laid",), "lead": ("led",), "leave": ("left",),
  "lend": ("lent",), "light": ("lit", "lighted"), "lose": ("lost",), "make": ("made",), "melt": ("melted", "molten"),
  "mow": ("mown", "mowed"), "pay": ("paid",), "put": ("put",), "read": ("read",), "ride": ("ridden",),
  "ring": ("rung",), "rise": ("risen",), "run": ("run",), "saw": ("sawn", "sawed"), "say": ("said",), "see": ("seen",),
  "sell": ("sold",), "send": ("sent",), "set": ("set",), "sew": ("sewn", "sewed"), "shake": ("shaken",),
  "shear": ("shorn", "sheared"), "shine": ("shone",), "shoot": ("shot",), "show": ("shown",), "shrink": ("shrunk",),
  "shut": ("shut",), "sing": ("sung",), "sink": ("sunk",), "sit": ("sat",), "sleep": ("slept",), "slide": ("slid",),
  "sow": ("sown", "sowed"), "speak": ("spoken",), "spend": ("spent",), "spin": ("spun",), "spit": ("spat",),
  "split": ("split",), "spread": ("spread",), "stand": ("stood",), "steal": ("stolen",), "stick": ("stuck",),
  "sting": ("stung",), "strike": ("struck",), "string": ("strung",), "sweep": ("swept",), "swell": ("swollen",),
  "swim": ("swum",), "swing": ("swung",), "take": ("taken",), "teach": ("taught",), "tear": ("torn",),
  "tell": ("told",), "think": ("thought",), "throw": ("thrown",), "wake": ("woken",), "wear": ("worn",),
  "weave": ("woven",), "win": ("won",), "wind": ("wound",), "write": ("written",)}


def participles(root):
  """The past participles of a verb root: the irregular forms, the regular -ed form (bake baked, fry fried) and, for a
  one-syllable root that ends in consonant, vowel, consonant, the form with the last consonant doubled (chop
  chopped)."""
  r = root.lower()
  out = set(IRREGULAR_PARTICIPLES.get(r, ()))
  if r.endswith("e"):
    out.add(r + "d")
  elif r.endswith("y") and r[-2:-1] not in ("a", "e", "i", "o", "u"):
    out.add(r[:-1] + "ied")
  else:
    out.add(r + "ed")
    if re.fullmatch(r"[^aeiou]*[aeiou][^aeiouwxy]", r):
      out.add(r + r[-1] + "ed")
  return out


def repeats_verb(root, value):
  """Whether a change value is the verb's own participle (cook, cooked): the value then adds nothing.  A shared
  beginning is no test: tie and tight differ."""
  return isinstance(value, str) and value.lower() in participles(root)


def _verb(source, a, steps, i):
  """(root, Stage-1 action) of a change step: the one Stage-1 capability action among the step's permitting units;
  None when there is none or more than one."""
  verbs = {}
  for uid in _source_units(steps, i):
    act = _stage1_action(source, uid)
    if act:
      verbs[act["root"]] = act
  return list(verbs.items())[0] if len(verbs) == 1 else None


def plan_verbs(source, plan, steps=None):
  """The source verb of each change step, None for another step or a change without one verb.  The planning
  checker compares a change by its verb (`planning_check`, rule A3)."""
  return [((_verb(source, a, steps, i) or (None,))[0] if a[0] == "change" else None) for i, a in enumerate(plan or [])]


def plan_fields(source, plan, steps=None):
  """The English and the named terms of a plan: render, plan_steps, plan_named and plan_verbs."""
  return {"render": render(source, plan, steps), "plan_steps": plan_steps(source, plan, steps),
          "plan_named": plan_named(source, plan), "plan_verbs": plan_verbs(source, plan, steps)}


def _change(source, a, steps, i, actor):
  """A change step.  With the source verb (one Stage-1 capability action among the step's permitting units): the verb,
  the object, the value when that action has a result role and the value is not the verb's own participle, and
  the tool.  Without a single verb: `makes OBJECT VALUE`."""
  obj, value, tool = a[2], a[3], a[4]
  found = _verb(source, a, steps, i)
  prep = "with"
  if found:
    root, act = found
    roles = act.get("roles") or {}
    prep = "in" if roles.get("location") == tool else "with"
    target = roles.get("target")
    word = isinstance(target, str) and not la.is_concrete(target) and target != la.UNSPECIFIED
    if word and obj == a[1]:
      # the change of the actor itself, whose Stage-1 target is a word and no entity: "Ann obtains a licence"
      thing = "%s %s" % (indef_article(target), target)
    elif word and roles.get("source") == obj:
      # a word target made from the object: "Ann bakes a cake from the flour"
      thing = "%s %s from %s" % (indef_article(target), target, name(source, obj))
    else:
      thing = name(source, obj)
    text = "%s%s %s" % (actor, third_person(root), thing)
    if "result" in roles and value != la.UNSPECIFIED and not repeats_verb(root, value):
      text += " %s" % value
  else:
    text = "%smakes %s %s" % (actor, name(source, obj), value)
  if tool != la.UNSPECIFIED:
    text += " %s %s" % (prep, name(source, tool))
  return text


def _phrase(source, plan, steps, i, same):
  """One step of a plan; `same`: the actor is the previous step's, so it is left out.  A move after a move of the
  same actor keeps only its endpoints and means."""
  a = plan[i]
  actor = "" if same else name(source, a[1]) + " "
  kind = a[0]
  if kind == "move":
    means = "" if a[4] == la.UNSPECIFIED else " by %s" % a[4]
    where = "from %s to %s%s" % (name(source, a[2]), name(source, a[3]), means)
    return where if same and plan[i - 1][0] == "move" else "%sgoes %s" % (actor, where)
  if kind == "take":
    return "%stakes %s" % (actor, name(source, a[2]))
  if kind == "put_on":
    return "%sputs %s on %s" % (actor, name(source, a[2]), name(source, a[3]))
  if kind == "put_in":
    return "%sputs %s in %s" % (actor, name(source, a[2]), name(source, a[3]))
  return _change(source, a, steps, i, actor)


def render(source, plan, steps=None):
  """The English sentence of a plan in execution order, with a capital first letter and no final period.  A step
  repeats its actor only when the actor changes; a move by the same actor keeps only its endpoints and means.  A
  change uses the source verb when the step's permitting source unit has exactly one Stage-1 capability action;
  otherwise it states the new property."""
  if not plan:
    return "No action is needed: the goal already holds"
  parts = [_phrase(source, plan, steps, i, i > 0 and plan[i][1] == plan[i - 1][1]) for i in range(len(plan))]
  return capitalized(", then ".join(parts))


def plan_steps(source, plan, steps=None):
  """One full sentence per step, the actor always named: ["Oskar goes from Lund to Malmo by bus.", ...]."""
  return [capitalized(_phrase(source, plan, steps, i, False)) + "." for i in range(len(plan or []))]


def fact_english(source, atom):
  """One fact in English: `the robot hand is empty`, `the hand holds block a`, `block a is on block b`."""
  if atom[0] == "has property":
    value = {"clear_top": "clear"}.get(atom[1], atom[1].replace("_", " "))
    return "%s is %s" % (name(source, atom[2]), value)
  if atom[0] == "is rel2":
    rel = atom[1]
    if rel == "holding":
      return "%s holds %s" % (name(source, atom[2]), name(source, atom[3]))
    word = {"located_at": "at"}.get(rel, rel.replace("_", " "))
    return "%s is %s %s" % (name(source, atom[2]), word, name(source, atom[3]))
  if atom[0] == "have":
    return "%s has %s" % (name(source, atom[1]), name(source, atom[2]))
  if atom[0] == "isa":
    return "%s is %s %s" % (name(source, atom[2]), indef_article(atom[1]), atom[1])
  return " ".join(str(x) for x in atom)

# ---------------------------------------------------------------------------
# the answer text


# the outcomes that are results of the question (an answer, a plan, a bounded non-discovery, a typed finding);
# every other outcome is a failure to answer and reads `Error: ...`
ANSWERED = ("verification_result", "plan_found", "goal_already_holds", "not_found", "candidate_not_validated",
            "inconsistent_action_state", "source_compiled")


def answered(result):
  """Whether a result record answers its question: decided from its outcome, never from rendered text.  A record
  of several queries answers only when every query does."""
  if result is None:
    return False
  if result.get("outcome") == "several":
    return all(answered(r) for r in result["results"])
  return result.get("outcome") in ANSWERED


# The outcomes of a text that the route reads and does not model: the answer text is `Cannot answer: ...`, not an
# error.  A failed run (an invalid translation, a call limit, a timeout, a prover error, a missing backend) keeps
# `Error: ...`, so a resume repeats it.
CANNOT_ANSWER = ("unsupported_translation", "unsupported_backend_requirement")

# One English sentence per reason code of an unsupported outcome, for the reader of `Cannot answer: ...`: what the route
# read in the text, and why it gives no answer for it.
REASON_SENTENCES = {
  "unsupported_capability_restriction": "the route read a rule as making one permission a condition of another, "
                                        "which it does not model",
  "unsupported_restriction_scope": "the route read a rule as a restriction of a means, an actor or a tool, which it "
                                   "does not model",
  "defeasible_text_effect": "the route read the result of an action as uncertain or as a default, which it does not "
                            "model",
  "existential_availability_head": "the route read a permission that names no actor, which it does not model",
  "existential_state_law_head": "the route read a rule as concluding that something exists, which it does not model",
  "existential_effect_head": "the route read an action as making something exist, which it does not model",
  "occurrence": "the route read a sentence as a report of an action that happened, which it does not model",
  "unsupported_action_kind": "the route read an action as creating, transporting or handing over an object, which it "
                             "does not model",
  "unsupported_relation_policy": "the route read a relation between objects, which it does not track over actions",
  "unexpressible_temporal_permission_scope": "the route read a permission as limited to a stated time, which it does "
                                             "not model",
  "method_collision": "the route read two different actions of the text as one action, which it does not model",
  "unsupported_goal_form": "the route read the question as asking about an alternative or about every object, which "
                           "it does not model",
  "unsupported_law_form": "the route read a rule with an arrangement of conditions and conclusions, which it does not "
                          "model",
  "unsupported_executability_assertion": "the route read a sentence as saying that an action is possible without "
                                         "giving a permission, which it does not model",
  "unsupported_contextual_location": "the route read a fact as holding at a place, which it does not model",
  "mixed_scope_rule": "the route read a rule as making a lasting class or route depend on a changing state, which it "
                      "does not model",
  "unsupported_default_form": "the route read a default rule with an arrangement of conditions and conclusions, which "
                              "it does not model",
  "ambiguous_state_scope": "the route read a fact without a mark of whether it holds at the start or always, which it "
                           "does not model",
  "unsupported_location_granularity": "the route read one place as inside another, or one thing at two places at "
                                      "once, which it does not model",
  "unsupported_confidence_form": "the route read a statement with a probability of one half or less, or an uncertain "
                                 "restriction or effect, which it does not model",
  "ambiguous_state_policy": "the route read a property without a mark of whether actions change it or a rule "
                            "computes it, which it does not model",
  "unsupported_stored_state_law": "the route read a rule as computing a property that actions also change, which it "
                                  "does not model",
  "unsupported_transport_dependency": "the route read an object as moving with the one who holds it, which it does "
                                      "not model",
  "negative_persistence_unavailable": "the route read the question as needing a negative fact kept across an action, "
                                      "which its prover does not support yet",
  "capability_not_validated": "the route read the question as needing a prover capability, which is not validated "
                              "yet",
  "ambiguous_directive": "the route read the request in more than one way, which it does not resolve",
  "unsupported_request": "the route read the request as a task outside planning and question answering, which it "
                         "does not model",
}
DEFAULT_REASON = "the route read a form of the text, which it does not model"
# below this stated probability the answer says "Probably"; a display convention, no calibrated probability
PROBABLY = 0.95


def unsupported_reason(result):
  """(reason codes, units) of an unsupported result: from its own fields, else from its first diagnostic."""
  d = result if (result.get("reasons") or result.get("reason")) else (result.get("diagnostics") or [{}])[0]
  d = d if isinstance(d, dict) else {}
  codes = d.get("reasons") or ([d["reason"]] if d.get("reason") else [])
  return list(codes), list(d.get("units") or [])


def cannot_answer(result):
  """`Cannot answer: <sentence>. [<reason codes>; <units>]` of an unsupported result."""
  codes, units = unsupported_reason(result)
  sentence = REASON_SENTENCES.get(codes[0], DEFAULT_REASON) if codes else DEFAULT_REASON
  return "Cannot answer: %s. [%s; %s]" % (sentence, ", ".join(codes) or "no reason code", ", ".join(units) or "-")


def _stated(result):
  """The stated-uncertainty part of a confidence: `confidence_parts.other_product`, or None when it is 1 or absent.
  The frame axioms' part is not stated."""
  parts = result.get("confidence_parts") or {}
  p = parts.get("other_product")
  return p if isinstance(p, (int, float)) and p < 1 else None


def _probably(result):
  """Whether the answer says "Probably": a stated probability below PROBABLY.  The number, its parts and the
  experimental status stay in the result record."""
  p = _stated(result)
  return p is not None and p < PROBABLY


def _joined(words):
  """`a`, `a and b`, `a, b and c`; "" for no word."""
  words = list(words)
  if len(words) <= 1:
    return "".join(words)
  return "%s and %s" % (", ".join(words[:-1]), words[-1])


def _names(words):
  return _joined([capitalized(words[0])] + list(words[1:]) if words else [])


def answer_text(result):
  """The answer string of a result: one fixed form per question kind and outcome (the table of answer forms in
  docs/reference/experimental-options.md).  An answer,
  `Cannot answer: ...` for a text the route does not model, or `Error: ...` for a failed run; never two of them."""
  o = result["outcome"]
  kind = (result.get("query") or {}).get("kind")
  if o in CANNOT_ANSWER:
    return cannot_answer(result)
  if o not in ANSWERED:
    why = result.get("detail") or (result.get("diagnostics") or [None])[0]
    return "Error: %s%s" % (o, ": %s" % (why if isinstance(why, str) else json.dumps(why)[:300]) if why else "")
  if o == "verification_result":
    a = result["answer"]
    if kind == "ask" and result.get("answer_names"):
      return _names(result["answer_names"]) + "."
    if a in ("Yes", "No"):
      return "Probably %s." % a.lower() if _probably(result) else "%s." % a
    if a == "Unknown":
      return "Unknown."
    if a == "contested":
      return "Contested."
    return (a if isinstance(a, str) else json.dumps(a)) + "."
  reachable = kind == "reachable"
  if o == "plan_found":
    if reachable:
      return "%s. Plan: %s." % ("Probably yes" if _probably(result) else "Yes", result.get("render"))
    return "%s: %s." % ("Probable plan" if _probably(result) else "Plan", result.get("render"))
  if o == "goal_already_holds":
    return "Yes. No action is needed." if reachable else "No action is needed."
  if o == "not_found":
    return "Unknown." if reachable else "No plan found."
  if o == "candidate_not_validated":
    return "Unknown: no candidate plan was validated."
  if o == "inconsistent_action_state":
    return "Inconsistent: %s." % _joined(result.get("facts_english") or result.get("facts") or ["the facts"])
  return "Source compiled: no question."
