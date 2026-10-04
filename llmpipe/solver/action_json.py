"""Reading a model's JSON response on the action route: the markdown fence, and three repairs of closing brackets.

  parse_response(raw, finish=None, cached=False, probabilities=None) -> (parsed, error, record)

A repair changes closing brackets only: it never makes up a value, a comma, a key or a unit, and the repaired text
must parse.  The record keeps every step, the text before and after each repair, and the reason a repair did not
apply.  The ordinary route's own repairs (`llmparse.fix_json`) are the second step; the ordinary parser itself is not
changed.  K10 is a repair of the controller (`docs/encodings/action-prompts.md`, the table of repairs).
"""

import json
import re

import llmcall
import llmparse

# the stop reasons of a response the provider cut at its output limit (llmcall `finish_reason`)
TRUNCATED = llmcall.TRUNCATED_FINISH
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?")
_STRING = re.compile(r'"(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"')
_LITERAL = re.compile(r"true|false|null")
CLOSER = {"[": "]", "{": "}"}


def _scan(text):
  """Read JSON text token by token; a string is read with its escapes, so a bracket inside it is no delimiter.
  Returns (stack, complete, error): the containers still open, each [opener, state]; whether one complete top-level
  value was read; the first refused token as (position, message), or None."""
  stack, i, n = [], 0, len(text)
  complete = [False]

  def wants_value():
    if not stack:
      return not complete[0]
    kind, state = stack[-1]
    return state in ("start", "comma") if kind == "[" else state == "colon"

  def took_value():
    if stack:
      stack[-1][1] = "value"
    else:
      complete[0] = True

  while i < n:
    c = text[i]
    if c in " \t\r\n":
      i += 1
      continue
    if complete[0]:
      return stack, True, (i, "text after the complete value")
    if c in "[{":
      if not wants_value():
        return stack, False, (i, "%s where no value can stand" % c)
      stack.append([c, "start"])
      i += 1
    elif c in "]}":
      if not stack or CLOSER[stack[-1][0]] != c:
        return stack, False, (i, "%s where %s" % (c, "nothing is open" if not stack else stack[-1][0] + " is open"))
      if stack[-1][1] not in ("start", "value"):
        return stack, False, (i, "%s after a comma, a colon or a key" % c)
      stack.pop()
      took_value()
      i += 1
    elif c == ",":
      if not stack or stack[-1][1] != "value":
        return stack, False, (i, "a comma where no value ends")
      stack[-1][1] = "comma"
      i += 1
    elif c == ":":
      if not stack or stack[-1][0] != "{" or stack[-1][1] != "key":
        return stack, False, (i, "a colon where no key ends")
      stack[-1][1] = "colon"
      i += 1
    elif c == '"':
      m = _STRING.match(text, i)
      if m is None:
        return stack, False, (i, "an unterminated or invalid string")
      if stack and stack[-1][0] == "{" and stack[-1][1] in ("start", "comma"):
        stack[-1][1] = "key"
      elif wants_value():
        took_value()
      else:
        return stack, False, (i, "a string where no value can stand")
      i = m.end()
    else:
      m = _NUMBER.match(text, i) or _LITERAL.match(text, i)
      if m is None:
        return stack, False, (i, "an unknown token")
      if not wants_value():
        return stack, False, (i, "a value where no value can stand")
      took_value()
      i = m.end()
  return stack, complete[0], None


def _repair_terminal(text):
  """Rebuild the final contiguous run of closing brackets of a JSON text.

  The text before that run must be intact JSON as far as it goes, and must end with a value or an opening bracket;
  the open containers then decide the one closing sequence.  Nothing inside the text is changed, and no value,
  comma, key or unit is made up.  Returns (repaired text, edit) or (None, the reason for no repair)."""
  body = text.rstrip()
  k = len(body)
  while k and body[k - 1] in "]} \t\r\n":
    k -= 1
  run = body[k:]
  if not run.strip():
    return None, "the JSON does not end with closing brackets"
  stack, complete, error = _scan(body[:k])
  if error:
    return None, "the text before the final closing brackets is not intact: %s at char %d" % (error[1], error[0])
  if not complete and not stack:
    return None, "no value before the final closing brackets"
  if stack and stack[-1][1] not in ("start", "value"):
    return None, "the text ends after a comma, a colon or a key"
  closers = "".join(CLOSER[o] for o, _ in reversed(stack))
  if closers == "".join(run.split()):
    return None, "the final closing brackets are already right; the error is elsewhere"
  repaired = body[:k] + closers
  try:
    json.loads(repaired)
  except ValueError as e:
    return None, "the rebuilt text does not parse: %s" % e
  return repaired, {"kind": "terminal_delimiters", "offset": k, "removed": run, "inserted": closers}


_PACKAGE = re.compile(r'\[\s*"@id"\s*,\s*("(?:[^"\\]|\\.)*")\s*,')


def _package_end(text, i):
  """The index after the bracket that closes the list opened at text[i], or None.  A string is read with its escapes."""
  depth, n = 0, len(text)
  while i < n:
    c = text[i]
    if c == '"':
      m = _STRING.match(text, i)
      if m is None:
        return None
      i = m.end()
      continue
    if c in "[{":
      depth += 1
    elif c in "]}":
      depth -= 1
      if depth == 0:
        return i + 1
    i += 1
  return None


def repair_packages(text, probabilities=None):
  """Close each ["@id", ID, PACKAGE] package at its own balanced end, and drop surplus closing brackets between
  packages.  The text before the first package must be intact JSON.  Between one package's end and the next package
  only closing brackets and one comma may stand; after the last package only closing brackets.  The final closing
  run is rebuilt from the containers the text before the first package opens.  Every rebuilt package has three
  elements.  K10: a package ["@id", U, PACKAGE, ["@p", U, v]] whose misplaced @p names its own unit and is one of
  the values `probabilities` accepts for U (`action_pipeline.misplaced_values`) loses that element; another number
  stays an error.  Returns (repaired text, edit) or (None, the reason for no repair)."""
  starts = list(_PACKAGE.finditer(text))
  if not starts:
    return None, "no [\"@id\", ID, PACKAGE] package"
  prefix = text[:starts[0].start()]
  stack, _, error = _scan(prefix)
  if error or not stack:
    return None, "the text before the first package is not intact"
  packages, dropped, misplaced = [], [], []
  for k, m in enumerate(starts):
    end = _package_end(text, m.start())
    limit = starts[k + 1].start() if k + 1 < len(starts) else len(text)
    if end is None or end > limit:
      return None, "a package does not close before the next one"
    rest = text[end:limit]
    if k + 1 < len(starts):
      if not re.fullmatch(r"\s*\]*\s*,\s*", rest):
        return None, "other text than closing brackets after a package"
    elif not re.fullmatch(r"[\]\}\s]*", rest):
      return None, "other text than closing brackets after the last package"
    try:
      package = json.loads(text[m.start():end])
    except ValueError as e:
      return None, "a package does not parse: %s" % e
    piece = text[m.start():end]
    if (len(package) == 4 and isinstance(package[3], list) and len(package[3]) == 3 and package[3][0] == "@p"
        and package[3][1] == package[1] and package[3][2] in (probabilities or {}).get(package[1], ())):
      piece = json.dumps(package[:3], ensure_ascii=False)
      misplaced.append({"kind": "misplaced_probability", "repair": "K10", "unit": package[1],
                        "before": text[m.start():end], "after": piece, "support": [package[1]]})
    elif len(package) != 3:
      return None, "the package %s has %d elements after its balanced end; the error is inside it" % (
        package[1], len(package))
    uid = json.loads(m.group(1))
    if k + 1 < len(starts) and "]" in rest:
      dropped.append({"after": uid, "removed": rest.count("]")})
    packages.append(piece)
  if not dropped and not misplaced:
    return None, "no surplus closing bracket between packages"
  repaired = prefix + ", ".join(packages) + "".join(CLOSER[o] for o, _ in reversed(stack))
  try:
    json.loads(repaired)
  except ValueError as e:
    return None, "the rebuilt text does not parse: %s" % e
  edit = {"kind": "package_delimiters", "dropped": dropped}
  if misplaced:
    edit["misplaced_probability"] = misplaced
  return repaired, edit


ENVELOPE_FIELDS = ("worlds", "contexts", "query_contexts", "types", "logic")
_ENVELOPE_KEY = re.compile(r'\s*,\s*"(%s)"\s*:' % "|".join(ENVELOPE_FIELDS))


def _repair_envelope(text):
  """Drop a run of surplus closing brackets before a field of the action envelope, as in
  `...]]]]], "types": {...}` with one `]` too many.

  The first token the scanner refuses must be a `]` while only the envelope object is open, after a complete value
  of a field; the run of `]` there must be followed by a comma and a field name of the envelope.  The run is
  dropped; nothing else is changed, and the repaired text must parse.  Returns (repaired text, edit) or (None, the
  reason for no repair)."""
  stack, _, error = _scan(text)
  if error is None:
    return None, "the scanner refuses no token"
  i = error[0]
  if text[i] != "]" or [o for o, _ in stack] != ["{"] or stack[0][1] != "value":
    return None, "the first refused token is not a closing bracket after a field value of the envelope"
  j = i
  while j < len(text) and text[j] in "] \t\r\n":
    j += 1
  m = _ENVELOPE_KEY.match(text, j)
  if m is None:
    return None, "the surplus closing brackets are not followed by a field of the envelope"
  repaired = text[:i] + text[j:]
  try:
    json.loads(repaired)
  except ValueError as e:
    return None, "the repaired text does not parse: %s" % e
  return repaired, {"kind": "envelope_delimiters", "offset": i, "removed": text[i:j], "before_field": m.group(1)}


def parse_response(raw, finish=None, cached=False, probabilities=None):
  """(parsed, error, record) of a model response.

  The steps, each kept in the record: the text without its fence (`llmparse.strip_fence`) is parsed first; when that fails, its error position is
  kept (a position in the model's own JSON), and the final run of closing brackets is rebuilt (`_repair_terminal`);
  when that does not apply, `llmparse.fix_json` runs as before; when that fails too, each package is closed at its
  own balanced end and the surplus closing brackets between packages are dropped (`repair_packages`, which also
  drops a misplaced @p whose value `probabilities` accepts for its unit: K10); when that fails too, a run of surplus
  closing brackets before a field of the action envelope is dropped (`_repair_envelope`).  A response
  the provider stopped at its output limit (`finish` in TRUNCATED) is not repaired: its JSON is incomplete, not
  mistyped.  Neither is a response without a stop reason that did not come from the LLM cache: it may be cut off, so
  the ordinary correction runs.  A response from the LLM cache (`cached`) has no stop reason and is repaired: the
  route keeps a response cut at the output limit out of the cache (`llmcall.call_llm` with cache_truncated=False).
  The ordinary route's parser is not changed.
  """
  info = {"finish_reason": finish, "cached": cached, "unfenced": False, "error": None, "repair": None,
          "fix_json": None, "package_repair": None, "envelope_repair": None}
  if not isinstance(raw, str) or not raw.strip():
    return None, "the response is empty", info
  text = llmparse.strip_fence(raw)[0]
  info["unfenced"] = text != raw.strip()
  try:
    return json.loads(text), None, info
  except ValueError as e:
    info["error"] = {"message": e.msg, "pos": e.pos, "near": text[max(0, e.pos - 40):e.pos + 10]}
    message = "the response is not JSON: %s at char %d of the JSON, near %s" % (e.msg, e.pos, json.dumps(info["error"]["near"]))
  if finish in TRUNCATED:
    info["repair"] = {"status": "refused", "reason": "the provider stopped the response at its output limit (%s)" % finish}
    return None, "the response is not JSON: the provider stopped it at the output limit (%s)" % finish, info
  if finish is None and not cached:
    # a response whose stop reason is unknown may be cut off: no repair; the ordinary correction runs
    info["repair"] = {"status": "refused", "reason": "no stop reason"}
    return None, message, info
  repaired, edit = _repair_terminal(text)
  if repaired is not None:
    info["repair"] = dict(edit, status="applied", text=repaired)
    return json.loads(repaired), None, info
  info["repair"] = {"status": "refused", "reason": edit}
  fixed, fixes = llmparse.fix_json(raw)
  try:
    parsed = json.loads(fixed)
    info["fix_json"] = {"fixes": fixes, "text": fixed}
    return parsed, None, info
  except ValueError:
    pass
  repaired, edit = repair_packages(text, probabilities)
  if repaired is not None:
    info["package_repair"] = dict(edit, status="applied", text=repaired)
    return json.loads(repaired), None, info
  info["package_repair"] = {"status": "refused", "reason": edit}
  repaired, edit = _repair_envelope(text)
  if repaired is None:
    info["envelope_repair"] = {"status": "refused", "reason": edit}
    return None, message, info
  info["envelope_repair"] = dict(edit, status="applied", text=repaired)
  return json.loads(repaired), None, info
