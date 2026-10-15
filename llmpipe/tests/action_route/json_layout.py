#!/usr/bin/env python3
"""The layout of the authored example files of the action route, after prompts/stage1_examples.txt and
prompts/stage2_examples.txt.

A list or dict without a nested list or dict stays on one line.  A nested one stays on one line when it fits in
100 columns; otherwise each element or key gets its own line, indented by two spaces, and the closing bracket gets
its own line.  A list that is broken keeps its leading strings and numbers on its first line, as in
`["@id", "S1",`.

  python3 tests/action_route/json_layout.py           # rewrite the four files in this layout
  python3 tests/action_route/json_layout.py --check   # list the files that are not in this layout; exit 1 if any
"""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
FILES = [ROOT / "prompts" / "actions" / "examples.json", ROOT / "prompts" / "actions" / "routing_cases.json",
         ROOT / "tests" / "action_route" / "unseen" / "examples.json",
         ROOT / "tests" / "action_route" / "unseen" / "routing_cases.json"]
WIDTH = 100


def one_line(value):
  return json.dumps(value, ensure_ascii=False)


def nested(value):
  return any(isinstance(x, (dict, list)) for x in (value.values() if isinstance(value, dict) else value))


def layout(value, indent=0, column=0):
  """The text of `value`, which starts at `column`; its continuation lines are indented by `indent`."""
  text = one_line(value)
  if not isinstance(value, (dict, list)) or not nested(value) or column + len(text) <= WIDTH:
    return text
  pad = " " * (indent + 2)
  if isinstance(value, dict):
    parts = []
    for k, v in value.items():
      key = one_line(k) + ": "
      parts.append(pad + key + layout(v, indent + 2, indent + 2 + len(key)))
    return "{\n" + ",\n".join(parts) + "\n" + " " * indent + "}"
  head = 0
  while head < len(value) and not isinstance(value[head], (dict, list)):
    head += 1
  first = "[" + ", ".join(one_line(x) for x in value[:head]) + ("," if head else "")
  parts = [pad + layout(x, indent + 2, indent + 2) for x in value[head:]]
  return first + "\n" + ",\n".join(parts) + "\n" + " " * indent + "]"


def dumps(value):
  return layout(value) + "\n"


def misplaced(paths=FILES):
  """The files whose text differs from the layout of their own content."""
  return [p for p in paths if p.read_text() != dumps(json.loads(p.read_text()))]


if __name__ == "__main__":
  p = argparse.ArgumentParser()
  p.add_argument("--check", action="store_true")
  args = p.parse_args()
  if args.check:
    bad = misplaced()
    for path in bad:
      print("not in the layout: %s" % path.relative_to(ROOT))
    sys.exit(1 if bad else 0)
  for path in FILES:
    path.write_text(dumps(json.loads(path.read_text())))
