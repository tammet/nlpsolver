"""What the critic reads: the case, its Stage 1 and its Stage 2, compacted.

The critic never sees the raw JSON.  It sees the English, one block per
Stage-1 unit, and per Stage-2 package one compact logic line and one
program-made English paraphrase of that same line.  The paraphrase exists so
that a reading error is visible without decoding the formula, and it is made
by template, never by a model: the critic must be reading OUR logic, not a
second model's summary of it.

Everything here is deterministic and costs no call.
"""

import json

VERSION = "critic_render/2026-08-17"

# the atoms an event bundle is made of, in the order they read
_EVENT_ROLES = ("has_actor", "has_target", "has_recipient", "has_location",
                "has_instrument", "has_content", "has_time")
_CLASSIFIERS = ("typical", "capability", "necessity", "obligation",
                "volition", "intention", "expectation", "speech_act",
                "actuality")

_CONNECTIVE = {"and": " ∧ ", "or": " ∨ "}


def _name(pred):
  """A predicate name as the critic sees it: spaces become underscores."""
  return str(pred).replace(" ", "_")


def _term(x):
  if isinstance(x, str) and x.startswith("?:"):
    return x[2:]
  return str(x)


# --------------------------------------------------------------- Stage 1

def compact_stage1(s1_json):
  """One block per unit: id, type, text, entities, actions, and the rest."""
  out = []
  for block in (s1_json or []):
    if not isinstance(block, dict):
      continue
    for unit in (block.get("units") or []):
      if not isinstance(unit, dict) or not unit.get("unit_id"):
        continue
      out.append(_unit_block(unit))
  return "\n".join(out)


def _unit_block(unit):
  head = [str(unit.get("type") or "")]
  if unit.get("time"):
    head.append(str(unit["time"]))
  if unit.get("confidence") not in (None, 1, 1.0):
    head.append("confidence %s" % unit["confidence"])
  lines = ["%s [%s] %s" % (unit["unit_id"], ", ".join(x for x in head if x),
                           str(unit.get("text") or "").strip())]
  ents = []
  for e in (unit.get("entities") or []):
    if not isinstance(e, dict) or not e.get("id"):
      continue
    kind = "c" if str(e.get("type") or "").lower().startswith("c") else "g"
    cat = e.get("category")
    ents.append("%s [%s%s]" % (e["id"], kind, ",%s" % cat if cat else ""))
  if ents:
    lines.append("    entities: %s" % "; ".join(ents))
  acts = [_action(a) for a in (unit.get("actions") or [])
          if isinstance(a, dict)]
  acts = [a for a in acts if a]
  if acts:
    lines.append("    actions: %s" % "; ".join(acts))
  tail = []
  for key, label in (("definites", "definites"),
                     ("adjectives", "adjectives")):
    got = unit.get(key)
    if got:
      tail.append("%s: %s" % (label, _short(got)))
  if tail:
    lines.append("    %s" % "; ".join(tail))
  return "\n".join(lines)


def _action(a):
  root = a.get("root") or a.get("predicate") or a.get("verb")
  if not root:
    return ""
  bits = []
  mode = a.get("mode")
  if mode:
    bits.append(str(mode))
  for key, value in sorted(a.items()):
    if key in ("root", "predicate", "verb", "mode"):
      continue
    if value in (None, "", [], {}):
      continue
    if isinstance(value, dict):
      bits.append("%s=%s" % (key, _action(value) or _short(value)))
    else:
      bits.append("%s=%s" % (key, _short(value)))
  return "%s(%s)" % (root, ", ".join(bits))


def _short(x):
  if isinstance(x, str):
    return x
  blob = json.dumps(x, default=str, ensure_ascii=False)
  return blob.replace('"', "").replace("[", "").replace("]", "")[:160]


# --------------------------------------------------------------- Stage 2

def compact_logic(package):
  """The Stage-2 formula of one `@id` package, as one line."""
  body, tail = _unwrap(package)
  return "%s%s" % (_formula(body), tail)


def _unwrap(package):
  """-> (the formula, the trailing annotations) of a package body."""
  tail = ""
  node = package
  while isinstance(node, list) and node:
    head = node[0]
    if head == "and" and len(node) == 3 and isinstance(node[2], list) \
       and node[2] and node[2][0] == "@p":
      tail = "   @p %s" % node[2][2]
      node = node[1]
      continue
    if head == "holds":
      node = node[2]
      continue
    if head == "question":
      return ("question(%s)" % _formula(node[1])), tail
    if head == "ask":
      return ("ask %s: %s" % (_term(node[1]), _formula(node[2]))), tail
    break
  return _formula(node), tail


def _formula(node):
  if not isinstance(node, list) or not node:
    return _term(node)
  head = node[0]
  if head in ("and", "or"):
    return _CONNECTIVE[head].join(_wrap(x) for x in node[1:])
  if head == "not":
    return "¬%s" % _wrap(node[1])
  if head == "implies":
    return "%s → %s" % (_wrap(node[1]), _formula(node[2]))
  if head == "forall":
    return "∀%s %s" % (_term(node[1]), _wrap(node[2]))
  if head == "exists":
    return "∃%s %s" % (_term(node[1]), _wrap(node[2]))
  if head == "normally":
    return "normally %s" % _formula(node[1])
  if head == "@time":
    return "@time(%s, %s)" % (_term(node[1]), _formula(node[2]))
  if head == "question":
    return "question(%s)" % _formula(node[1])
  return "%s(%s)" % (_name(head), ", ".join(_formula(x) for x in node[1:]))


def _wrap(node):
  text = _formula(node)
  if isinstance(node, list) and node and node[0] in ("and", "or", "implies"):
    return "(%s)" % text
  return text


# ------------------------------------------------------------ paraphrase

def paraphrase(package):
  """Deterministic English for the same formula.  No model, no clauses."""
  body, _tail = _unwrap(package)
  del body
  node = package
  while isinstance(node, list) and node and node[0] in ("holds", "and") \
        and not (node[0] == "and" and len(node) != 3):
    if node[0] == "holds":
      node = node[2]
    elif isinstance(node[2], list) and node[2] and node[2][0] == "@p":
      node = node[1]
    else:
      break
  return _english(node).strip()


def _english(node):
  if not isinstance(node, list) or not node:
    return _term(node)
  head = node[0]
  if head == "question":
    return "Is it the case that %s?" % _english(node[1])
  if head == "ask":
    return "Which %s: %s?" % (_term(node[1]), _english(node[2]))
  if head == "forall":
    inner = node[2]
    if isinstance(inner, list) and inner and inner[0] == "implies":
      return "For every %s: if %s then %s" % (_term(node[1]),
                                              _english(inner[1]),
                                              _english(inner[2]))
    return "For every %s: %s" % (_term(node[1]), _english(inner))
  if head == "exists":
    return "there is some %s such that %s" % (_term(node[1]),
                                              _english(node[2]))
  if head == "implies":
    return "if %s then %s" % (_english(node[1]), _english(node[2]))
  if head == "not":
    return "it is not the case that %s" % _english(node[1])
  if head == "normally":
    return "normally %s" % _english(node[1])
  if head == "or":
    return " or ".join(_english(x) for x in node[1:])
  if head == "xor":
    return " or, but not both, ".join(_english(x) for x in node[1:])
  if head == "@time":
    return "%s: %s" % (_term(node[1]), _english(node[2]))
  if head == "and":
    return _english_conjunction(node[1:])
  return _atom_english(node)


def _english_conjunction(parts):
  """An `and` block, with an event bundle collapsed into one clause."""
  bundle, rest = _split_event(parts)
  said = []
  if bundle:
    said.append(bundle)
  said.extend(_english(x) for x in rest)
  return " and ".join(x for x in said if x)


def _split_event(parts):
  """-> (the event read as one clause, the atoms that are not part of it)."""
  var, kind, roles, marks = None, None, {}, []
  rest = []
  for part in parts:
    if not (isinstance(part, list) and part and isinstance(part[0], str)):
      rest.append(part)
      continue
    pred = _name(part[0])
    if pred == "isa" and len(part) == 3 and part[1] == "activity":
      var = part[2]
      continue
    if pred == "has_type" and len(part) == 3:
      kind = part[2]
      continue
    if pred in _EVENT_ROLES and len(part) >= 3:
      roles[pred] = part[2:]
      continue
    if pred in _CLASSIFIERS and len(part) == 2:
      marks.append(pred)
      continue
    rest.append(part)
  if var is None or kind is None:
    return None, list(parts)
  actor = roles.get("has_actor")
  target = roles.get("has_target")
  said = "%s %s" % (_term(actor[0]) if actor else "something", kind)
  if target:
    said += " %s" % _term(target[0])
  for role in ("has_recipient", "has_location", "has_instrument"):
    if roles.get(role):
      said += " %s %s" % (role.replace("has_", ""), _term(roles[role][0]))
  if "capability" in marks:
    said = said.replace(" %s" % kind, " can %s" % kind, 1)
  elif "typical" in marks:
    said = "typically %s" % said
  if roles.get("has_time"):
    said += " (%s)" % _term(roles["has_time"][0])
  return said, rest


def _article(word):
  return "an" if str(word)[:1].lower() in "aeiou" else "a"


def _atom_english(atom):
  """One atom, through the ordinary renderer where it applies."""
  pred = _name(atom[0])
  args = [_term(x) for x in atom[1:]]
  if pred == "isa" and len(args) == 2:
    return "%s is %s %s" % (args[1], _article(args[0]), args[0])
  if pred == "have" and len(args) == 2:
    return "%s has %s" % (args[0], args[1])
  if pred == "has_part" and len(args) == 2:
    return "%s has part %s" % (args[0], args[1])
  if pred == "has_property" and len(args) == 2:
    return "%s is %s" % (args[1], args[0])
  if pred == "is_rel2" and len(args) == 3:
    return "%s holds between %s and %s" % (args[0], args[1], args[2])
  return "%s(%s)" % (pred, ", ".join(args))


# ------------------------------------------------------------- assembly

def critic_user_message(text, s1_json, s2_json, result=None):
  """TEXT / STAGE 1 / STAGE 2 / RESULT, exactly as the example file has it."""
  parts = ["TEXT", str(text or "").strip(), "", "STAGE 1",
           compact_stage1(s1_json), "", "STAGE 2"]
  for pid, body in _packages(s2_json):
    parts.append("%-3s %s" % (pid, compact_logic(body)))
    said = paraphrase(body)
    if said:
      parts.append('    "%s"' % said)
  parts.extend(["", "RESULT",
                result or "The prover found no answer."])
  return "\n".join(parts)


def _packages(s2_json):
  """-> [(unit id, the package body)] of a Stage-2 output."""
  out = []
  if not (isinstance(s2_json, list) and s2_json and s2_json[0] == "and"):
    return out
  for item in s2_json[1:]:
    if isinstance(item, list) and len(item) >= 3 and item[0] == "@id":
      out.append((str(item[1]), item[2]))
  return out


def token_estimate(message):
  """A rough size guard for the log; nothing is ever truncated."""
  return int(len(message) / 3.6)
