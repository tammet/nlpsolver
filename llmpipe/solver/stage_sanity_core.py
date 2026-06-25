# Shared types/helpers for the Stage-1/Stage-2 sanity checks.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from dataclasses import dataclass
import json

@dataclass(frozen=True)
class Issue:
  """A single structural problem detected in LLM output.

  Equality / hashing is by all fields; fingerprinting for persistence
  detection across retries uses only (kind, location) — see
  issue_fingerprints().
  """
  kind: str          # e.g. "free_variable"
  location: str      # path into the formula, e.g. "@id:S1/forall:X/implies/..."
  description: str   # human-readable one-liner
  evidence: str      # JSON snippet of the offending atom/subtree




def issue_fingerprints(issues):
  """Return a frozenset of (kind, location) tuples for persistence detection."""
  return frozenset((i.kind, i.location) for i in issues)




# ======== small helpers ========

def safe_json(obj):
  try:
    return json.dumps(obj)
  except Exception:
    return str(obj)
