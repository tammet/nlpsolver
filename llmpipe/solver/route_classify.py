"""Which pipeline a text goes to: the action route, the ordinary pipeline, or unclear.  A cheap classifier: rules on
the English text, no model call.

  classify(text) -> {"verdict": "actions" | "ordinary" | "unclear", "signals": [...]}

A strong signal gives `actions`.  Each is a form that the ordinary test sets do not use:

  how_question     a question "How can / could / should X ...?"
  plan_request     a request for a plan: "Find a plan ...", "Give a plan ...", "What is a plan ...?", also after an
                   opening phrase ("Within the lab, find a plan ...")
  after_question   a question that starts with "After X does ..., ...?" in the present or future tense: the state
                   after a supplied sequence.  A past-tense question ("After Mary arrived, did she call Tom?") asks
                   about a narrative and is no signal
  eventually       a question with "eventually": whether a goal can be reached
  block_world      blocks named by a letter with a hand, stacking or a clear block
  route_fact       a public service or route between places: "a bus route from A to B", "a train service"
  travel_permission  a permission to travel between two stated places by a means: "Mira can travel from Harbor to
                   Hilltown by bus"
  tool_permission  a permission for an operation with an instrument: "Ann can whisk the egg with the whisk"
  snapshot         the route's own words for situations: "In snapshot W1", "With no actions performed"

Without one, a weak signal gives `unclear`: a sign of actions that ordinary texts also use.

  operation_permission  "can", "cannot" or "may" before an operation verb ("Ann can paint the gate")
  present_effect        a sentence "After X does ..., Y is ..." in the present tense
  who_can               a question "Who can ...?"
  can_question          a question "Can X <operation> ...?"
  imperative            a sentence that starts with an operation verb ("Put b on a.")

A text with no signal is `ordinary`.  The rules are a heuristic.  `solve.route_choice` sends an `unclear`
text to the ordinary pipeline; the verdict is recorded with the choice.
"""

import re

OPERATIONS = ("travel", "go", "walk", "drive", "fly", "sail", "ride", "take", "put", "move", "paint", "open", "close",
              "lock", "unlock", "cook", "boil", "fry", "bake", "steam", "heat", "press", "push", "pull", "carry", "lift",
              "pick", "place", "stack", "unstack", "whisk", "break", "wash", "clean", "polish", "cut", "buy", "sell",
              "give", "mop", "wax", "sand", "fill", "empty", "obtain", "get", "reach", "board", "fix", "repair",
              "load", "unload", "deliver", "bring", "fetch", "send", "switch", "turn", "plant", "water", "build")
OPS = "|".join(OPERATIONS)
SENTENCE = re.compile(r"(?<=[.?!])\s+")

STRONG = {
  "how_question": re.compile(r"^how (can|could|should) ", re.I),
  "plan_request": re.compile(r"(^|, )((please )?(find|give|show|describe|propose|suggest)( me| us)? (a|an|the|some|one)\b"
                             r"[^.?!]*\bplan\b|what (is|would be) (a|the) plan\b|which (actions|steps)\b)", re.I),
  "after_question": re.compile(r"^after [^,?]+, (is|are|does|do|can|will|has|have)\b", re.I),
  "eventually": re.compile(r"\beventually\b", re.I),
}
BLOCKS = re.compile(r"\bblocks? [a-z]\b", re.I)
BLOCK_CONTEXT = re.compile(r"\b(hand|stack|unstack|clear|on top of)\b", re.I)
ROUTE = re.compile(r"\b(bus|train|ferry|ship|taxi|plane|boat|tram) (route|service|connection|line)s?\b|"
                   r"\broutes? (goes |go |runs |run )?from\b", re.I)
TRAVEL = re.compile(r"\b(can|cannot|could)( not| probably| probably not)? (travel|go|walk|drive|fly|sail|ride|move) "
                    r"from [^.?!]+ to [^.?!]+ by\b", re.I)
TOOL = re.compile(r"\b(can|cannot|could)( not| also)? (%s) (the|a|an) \w+( \w+)? (with|using) (the|a|an|that) \w+" % OPS,
                  re.I)
SNAPSHOT = re.compile(r"\bsnapshot W\d+\b|\bwith no actions performed\b", re.I)
WEAK = {
  "operation_permission": re.compile(r"\b(can|cannot|can't|could|may)( not)? (%s)\b" % OPS, re.I),
  "present_effect": re.compile(r"^after [^,.]+, [^.?!]*\b(is|are|becomes|become|has|have)\b", re.I),
  "who_can": re.compile(r"^who (can|could)\b", re.I),
  "can_question": re.compile(r"^(can|could) [^?]*\b(%s)\b" % OPS, re.I),
  "imperative": re.compile(r"^(%s)\b" % OPS, re.I),
}

# the reader's words for each signal, for the pipeline line of the output; the records keep the names
SIGNAL_WORDS = {
  "how_question": 'a question "How can ...?"',
  "plan_request": "a request for a plan",
  "after_question": 'a question "After ..., ...?"',
  "eventually": 'the word "eventually"',
  "block_world": "blocks named by a letter, with a hand or a stack",
  "route_fact": "a route or service between places",
  "travel_permission": "a permission to travel from one place to another by a means",
  "tool_permission": "a permission for an operation with a tool",
  "snapshot": "a named snapshot",
  "operation_permission": '"can" before an operation verb',
  "present_effect": "an effect sentence in the present tense",
  "who_can": 'a question "Who can ...?"',
  "can_question": 'a question "Can ...?" about an operation',
  "imperative": "a sentence that starts with an operation verb",
}


def sentences(text):
  return [s.strip() for s in SENTENCE.split((text or "").strip()) if s.strip()]


def classify(text):
  """{"verdict", "signals"} of a text: `actions` on a strong signal, `unclear` on a weak one, else `ordinary`."""
  sents = sentences(text)
  questions = [s for s in sents if s.endswith("?")]
  strong = []
  for name in ("how_question", "after_question", "eventually"):
    if any(STRONG[name].search(q) for q in questions):
      strong.append(name)
  if any(STRONG["plan_request"].search(s) for s in sents):
    strong.append("plan_request")
  if BLOCKS.search(text or "") and BLOCK_CONTEXT.search(text or ""):
    strong.append("block_world")
  for name, rx in (("route_fact", ROUTE), ("travel_permission", TRAVEL), ("tool_permission", TOOL),
                   ("snapshot", SNAPSHOT)):
    if rx.search(text or ""):
      strong.append(name)
  if strong:
    return {"verdict": "actions", "signals": strong}
  weak = []
  if any(WEAK["operation_permission"].search(s) for s in sents):
    weak.append("operation_permission")
  if any(WEAK["present_effect"].search(s) for s in sents if not s.endswith("?")):
    weak.append("present_effect")
  for name in ("who_can", "can_question"):
    if any(WEAK[name].search(q) for q in questions):
      weak.append(name)
  if any(WEAK["imperative"].search(s) for s in sents if not s.endswith("?")):
    weak.append("imperative")
  if weak:
    return {"verdict": "unclear", "signals": weak}
  return {"verdict": "ordinary", "signals": []}
