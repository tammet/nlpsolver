"""One switch per v2 fix, so a fix can be reverted alone and measured alone.

The v2 work changed several things at once and the EB column fell from 44
correct proofs to 10.  A combined change cannot say which part did it, so each
fix gets a named switch here and the run records which switches were set.

Every switch is False in a normal run: the code behaves as v2 intends.  Setting
one restores exactly the pilot's behaviour for that one fix and nothing else.
"""

# C1: population witnesses ($some_C) back in the graph theory
REVERT_C1_POPULATE = "revert_c1_populate"
# C2: Stage-1 entity-category and base-word isa clauses back in the theory
REVERT_C2_ENTITYCAT = "revert_c2_entitycat"
# WP1.3: count proof steps as a proof even when gk did not say "answer found"
REVERT_VERDICT = "revert_gk_verdict"
# WP1.6: RELATED / UNCERTAIN pairs become bridges again, in both directions
REVERT_P3 = "revert_p3_undecided_bridges"

SWITCHES = (REVERT_C1_POPULATE, REVERT_C2_ENTITYCAT, REVERT_VERDICT, REVERT_P3)

_state = dict((k, False) for k in SWITCHES)


def set_switches(names):
  """Turn on the named switches and nothing else.  -> the resulting state."""
  for k in SWITCHES:
    _state[k] = False
  for n in (names or ()):
    if n not in _state:
      raise KeyError("unknown ablation switch %r" % n)
    _state[n] = True
  return dict(_state)


def on(name):
  return bool(_state.get(name))


def state():
  return dict(_state)


def active():
  return sorted(k for k, v in _state.items() if v)
