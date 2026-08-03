# Sanity-check facade: re-exports the Stage-1/Stage-2 check API from the
# per-family modules so importers (llmparse) see a single module.
#----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
# Licensed under the Apache License, Version 2.0.
#----------------------------------------------------------------

from stage_sanity_core import Issue, issue_fingerprints, safe_json
from stage_sanity_s1 import check_stage1, check_dropped_question_negation
from stage_sanity_s2 import check_stage2, format_retry_suffix
from stage_sanity_guards import (check_unsatisfiable_guards,
                                 format_guard_retry_suffix,
                                 check_stage2_id_coverage)
import stage_sanity_s2 as _s2


def set_aggressive_repair(value):
  """Enable/disable the aggressive constant-vs-class repair check (read by
  check_stage2's constant-vs-class sub-check)."""
  _s2.aggressive_repair = value
