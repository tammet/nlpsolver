#!/usr/bin/env python3
"""The run ceiling of `runtests.py -run-ceiling`: offline, with a fake HTTPS connection.

The ceiling counts every outbound provider request (each HTTP retry and each Gemini context-cache creation) and
every logical call, and llmcall refuses the one past the ceiling before it leaves.  The runner keeps the counts of
a run folder in a ledger, so a resumed run continues with the remaining allowance.

The llmcall checks use a fresh copy of the module: the check runner replaces `_post_with_retry` with a refusing
guard, and these checks need the real retry loop.  The copy talks to a fake connection that records each request
and answers from a script, so no request leaves the process and no cache entry is read or written.
"""

import argparse
import importlib.util
import json
import os
import sys
import tempfile
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "solver"))
sys.path.insert(0, ROOT)


def need(ok, what):
  if not ok:
    raise AssertionError(what)


class FakeResponse(object):
  def __init__(self, status, reason, data):
    self.status, self.reason, self.data = status, reason, data

  def read(self):
    return json.dumps(self.data).encode()


class FakeConnection(object):
  """Records each request and answers from `script`, a list of (status, reason, data)."""
  script = []
  sent = []

  def __init__(self, host, timeout=None):
    self.host = host

  def request(self, method, url, body, headers=None):
    FakeConnection.sent.append(url)

  def getresponse(self):
    status, reason, data = FakeConnection.script.pop(0)
    return FakeResponse(status, reason, data)

  def close(self):
    pass


CLAUDE_OK = (200, "OK", {"content": [{"type": "text", "text": "fine"}], "stop_reason": "end_turn",
                         "usage": {"input_tokens": 1, "output_tokens": 1}})
SERVER_ERROR = (500, "Internal Server Error", {"error": {"message": "try again"}})
CACHE_OK = (200, "OK", {"name": "cachedContents/fake"})
GEMINI_OK = (200, "OK", {"candidates": [{"content": {"parts": [{"text": "fine"}]}, "finishReason": "STOP"}],
                         "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1}})


def fresh_llmcall():
  spec = importlib.util.spec_from_file_location("llmcall_ceiling_copy", os.path.join(ROOT, "solver", "llmcall.py"))
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  mod._get_llm_cached = lambda *a, **k: None
  mod._store_llm_cached = lambda *a, **k: None
  mod._read_api_key = lambda *a, **k: "test-key"
  mod._sleep_bounded = lambda *a, **k: None
  mod.record_calls = True
  return mod


def calls(mod, script):
  """Run with the fake connection; return the requests it saw."""
  FakeConnection.script = list(script)
  FakeConnection.sent = []
  return patch.object(mod.http.client, "HTTPSConnection", FakeConnection)


def check_llmcall():
  mod = fresh_llmcall()
  # a retry near the ceiling: two requests are left; the first two attempts fail with 500, the third attempt is
  # refused before it leaves
  mod.reset_call_limit(); mod.reset_call_log()
  mod.set_run_budget(10, 2)
  with calls(mod, [SERVER_ERROR, SERVER_ERROR, CLAUDE_OK]):
    got = mod.call_llm("system", "input", llm="claude")
  b = mod.run_budget()
  last = mod.call_log[-1]
  need(len(FakeConnection.sent) == 2 and b["requests_used"] == 2 and b["refused"] == 1
       and got is None and last.get("reason") == mod.CEILING_MARKER
       and last.get("requests") == 2 and mod.call_counts()["provider_requests"] == 2,
       "a retry near the ceiling: %r %r %r %r" % (FakeConnection.sent, b, got, last))
  # the retries count: three requests left, the third attempt succeeds and the entry records 3 requests
  mod.reset_call_limit(); mod.reset_call_log()
  mod.set_run_budget(10, 3)
  with calls(mod, [SERVER_ERROR, SERVER_ERROR, CLAUDE_OK]):
    got = mod.call_llm("system", "input", llm="claude")
  need(got == "fine" and mod.call_log[-1].get("requests") == 3 and mod.run_budget()["requests_used"] == 3,
       "three requests for one logical call: %r %r" % (got, mod.call_log[-1]))
  # a Gemini context-cache creation is an outbound request: with one request left it takes it, and the
  # generation request is refused
  mod.reset_call_limit(); mod.reset_call_log()
  mod.set_run_budget(10, 1)
  mod._gemini_should_cache = lambda s: True
  mod._gemini_cache_map.clear()
  with calls(mod, [CACHE_OK, GEMINI_OK]):
    got = mod.call_llm("x" * 20000, "input", llm="gemini")
  need(FakeConnection.sent == ["/v1beta/cachedContents"] and got is None
       and mod.call_log[-1].get("requests") == 1,
       "the context-cache creation counts: %r %r %r" % (FakeConnection.sent, got, mod.call_log[-1]))
  # with two requests left both go out, and the entry records both
  mod.reset_call_limit(); mod.reset_call_log()
  mod.set_run_budget(10, 2)
  mod._gemini_cache_map.clear()
  with calls(mod, [CACHE_OK, GEMINI_OK]):
    got = mod.call_llm("x" * 20000, "input", llm="gemini")
  need(got == "fine" and len(FakeConnection.sent) == 2 and mod.call_log[-1].get("requests") == 2,
       "the cache creation and the generation request: %r %r" % (FakeConnection.sent, mod.call_log[-1]))
  # the logical ceiling: one logical call left; the second call is refused before the cache and the provider
  mod.reset_call_limit(); mod.reset_call_log()
  mod.set_run_budget(1, 10)
  with calls(mod, [CLAUDE_OK, CLAUDE_OK]):
    first = mod.call_llm("system", "input", llm="claude")
    second = mod.call_llm("system", "input", llm="claude")
  need(first == "fine" and second is None and len(FakeConnection.sent) == 1
       and mod.call_log[-1].get("source") == "refused",
       "the logical ceiling: %r %r %r" % (first, second, FakeConnection.sent))
  # the runner's hook gets each count before the request leaves: when the connection gets a request, the hook has
  # already seen it
  mod.reset_call_limit(); mod.reset_call_log()
  seen, at_send = [], []
  mod.set_run_budget(10, 10, on_count=lambda b: seen.append((b["logical_used"], b["requests_used"])))

  class Watching(FakeConnection):
    def request(self, method, url, body, headers=None):
      at_send.append(seen[-1])
      FakeConnection.request(self, method, url, body, headers)
  FakeConnection.script, FakeConnection.sent = [SERVER_ERROR, CLAUDE_OK], []
  with patch.object(mod.http.client, "HTTPSConnection", Watching):
    got = mod.call_llm("system", "input", llm="claude")
  need(got == "fine" and seen == [(1, 0), (1, 1), (1, 2)] and at_send == [(1, 1), (1, 2)],
       "the count is reported before the request leaves: %r %r %r" % (got, seen, at_send))
  # the per-case reset keeps the batch budget; clearing it removes every limit
  mod.reset_call_limit()
  need(mod.run_budget() is not None, "reset_call_limit keeps the batch budget")
  mod.clear_run_budget()
  mod.reset_call_limit(); mod.reset_call_log()
  with calls(mod, [SERVER_ERROR, CLAUDE_OK]):
    got = mod.call_llm("system", "input", llm="claude")
  need(mod.run_budget() is None and got == "fine" and mod.call_counts()["provider_requests"] == 2,
       "without a budget no call is limited: %r %r" % (got, mod.call_counts()))


def check_runner():
  import runtests
  import llmcall
  sys.path.insert(0, HERE)
  import check_planning_tests as cpt
  grader = runtests.PlanningGrader(os.path.join(ROOT, "tests", "tests_planning_basic.py"))
  tests = dict((t[0], t) for t in cpt.load("tests_planning_basic.py"))
  rows = [tuple(tests[i][:3]) for i in (1, 2, 3, 4)]
  ran = []

  def worker(spend):
    """A fake case: `spend` = (logical calls, requests per logical call), each through llmcall's slots."""
    def run(task):
      ran.append(task[0])
      log = []
      try:
        for _ in range(spend[0]):
          llmcall._take_call_slot()
          for _ in range(spend[1]):
            llmcall._take_request_slot("Fake")
          log.append({"logical": True, "source": "api", "requests": spend[1]})
      except llmcall.LlmRunCeilingExceeded:
        log.append({"logical": True, "source": "api", "failed": True, "reason": llmcall.CEILING_MARKER})
      return task[0], task[3], {"answer": "Unknown.", "_llm_calls": log, "action_route": {"result": {}}}
    return run

  def batch(folder, ceiling, spend):
    del ran[:]
    args = argparse.Namespace(sequential=True, run_ceiling=ceiling, redo=False, redo_errors=False)
    llmcall.reset_call_limit()
    with patch.object(runtests, "_worker", side_effect=worker(spend)):
      runtests._run_batch(args, ["claude"], rows, "planning", folder, {"llm_call_limit": 7}, None, None, grader)
    with open(os.path.join(folder, runtests.CEILING_LEDGER)) as f:
      ledger = json.load(f)
    gem = os.path.join(folder, "claude")
    saved = sorted(int(n[5:9]) for n in (os.listdir(gem) if os.path.isdir(gem) else []) if n.startswith("case_"))
    return ledger, saved

  # 3 logical calls and 3 requests per case, per-case bound 7, ceiling 12,12: case 3 could pass (6 + 7 > 12),
  # so two cases run
  d = tempfile.mkdtemp()
  ledger, saved = batch(d, "12,12", (3, 1))
  need(ran == [1, 2] and saved == [1, 2] and ledger["used"] == {"logical": 6, "requests": 6}
       and ledger["parts"][0].get("stopped") == "ceiling",
       "the ceiling before a case: %r %r %r" % (ran, saved, ledger))
  # the resumed run: the ledger says 6 and 6 were used; with the ceiling 20,20 cases 3 and 4 run (6 + 7 and
  # 9 + 7 stay within 20); the saved cases 1 and 2 are skipped
  ledger, saved = batch(d, "20,20", (3, 1))
  need(ran == [3, 4] and saved == [1, 2, 3, 4] and ledger["used"] == {"logical": 12, "requests": 12}
       and len(ledger["parts"]) == 2 and ledger["parts"][1]["logical"] == 6
       and ledger["parts"][1]["logical_before"] == 6,
       "the resumed run: %r %r %r" % (ran, saved, ledger))
  need(llmcall.run_budget() is None, "the batch clears its budget")
  # a ceiling reached inside a case: 3 logical calls with 3 requests each, ceiling 20,7; case 1 starts
  # (0 + 7 <= 7), and its 8th request is refused before it leaves; the case is not written
  d = tempfile.mkdtemp()
  ledger, saved = batch(d, "20,7", (3, 3))
  need(ran == [1] and saved == [] and ledger["used"] == {"logical": 3, "requests": 7}
       and ledger["parts"][0]["unwritten"] == [[1, "claude"]] and ledger["parts"][0].get("stopped") == "ceiling",
       "a ceiling reached inside a case: %r %r %r" % (ran, saved, ledger))
  # resumed with the ceiling 40,50 the unwritten case runs again; the ledger keeps the first part's counts
  ledger, saved = batch(d, "40,50", (3, 3))
  need(ran == [1, 2, 3, 4] and saved == [1, 2, 3, 4] and ledger["used"] == {"logical": 3 + 12, "requests": 7 + 36},
       "the resumed run after an unwritten case: %r %r %r" % (ran, saved, ledger))
  need(llmcall.run_budget() is None, "the batch clears its budget after a stop")
  # the stop file: the worker of case 2 creates it, so the run stops before case 3 and both cases are written; a run
  # with the stop file present runs nothing; after its removal the resumed run does cases 3 and 4
  d = tempfile.mkdtemp()
  stop = os.path.join(d, runtests.STOP_FILE)
  plain = worker((3, 1))

  def stopping(task):
    if task[0] == 2:
      open(stop, "w").close()
    return plain(task)
  args = argparse.Namespace(sequential=True, run_ceiling="40,40", redo=False, redo_errors=False)
  del ran[:]
  with patch.object(runtests, "_worker", side_effect=stopping):
    runtests._run_batch(args, ["claude"], rows, "planning", d, {"llm_call_limit": 7}, None, None, grader)
  with open(os.path.join(d, runtests.CEILING_LEDGER)) as f:
    ledger = json.load(f)
  need(ran == [1, 2] and ledger["parts"][0].get("stopped") == "stop_file" and ledger["used"]["logical"] == 6,
       "the stop file: %r %r" % (ran, ledger))
  del ran[:]
  with patch.object(runtests, "_worker", side_effect=plain):
    code = runtests._run_batch(args, ["claude"], rows, "planning", d, {"llm_call_limit": 7}, None, None, grader)
  need(code == 3 and ran == [] and llmcall.run_budget() is None, "a run with the stop file present: %r %r" % (code, ran))
  os.remove(stop)
  ledger, saved = batch(d, "40,40", (3, 1))
  need(ran == [3, 4] and saved == [1, 2, 3, 4] and ledger["used"]["logical"] == 12 and len(ledger["parts"]) == 2,
       "resumed after the stop file: %r %r %r" % (ran, saved, ledger))
  # a killed process: the ledger on disk already counts the request in flight.  The worker of case 2 reads the
  # ledger file after its first request slot, which is what a process killed during that request leaves
  d = tempfile.mkdtemp()
  on_disk = []

  def reading(task):
    if task[0] != 2:
      return plain(task)
    ran.append(task[0])
    llmcall._take_call_slot()
    llmcall._take_request_slot("Fake")
    with open(os.path.join(d, runtests.CEILING_LEDGER)) as f:
      on_disk.append(json.load(f))
    return task[0], task[3], {"answer": "Unknown.", "_llm_calls": [{"logical": True, "source": "api", "requests": 1}],
                              "action_route": {"result": {}}}
  del ran[:]
  with patch.object(runtests, "_worker", side_effect=reading):
    runtests._run_batch(args, ["claude"], rows, "planning", d, {"llm_call_limit": 7}, None, None, grader)
  part = on_disk[0]["parts"][-1]
  need(on_disk[0]["used"] == {"logical": 4, "requests": 4} and part.get("in_progress") == [2, "claude"]
       and "ended" not in part and part.get("updated"),
       "the ledger on disk during a request: %r" % on_disk)
  with open(os.path.join(d, runtests.CEILING_LEDGER)) as f:
    ledger = json.load(f)
  need(ledger["used"] == {"logical": 10, "requests": 10} and "in_progress" not in ledger["parts"][-1]
       and ledger["parts"][-1].get("ended"),
       "the ledger after the part: %r" % ledger)


def run():
  check_llmcall()
  check_runner()
  print("  the run ceiling: a retry near the ceiling is refused before it leaves; HTTP retries and the Gemini "
        "context-cache creation count as requests; the logical ceiling refuses before the cache; the batch "
        "budget does not limit other calls; the runner stops before a case that could pass the ceiling, does not "
        "write a case the ceiling interrupted, and a resumed run continues from the ledger; the ledger is written "
        "after each count, before the request leaves; the stop file stops the run before the next case, and a run "
        "does not start while it exists")


if __name__ == "__main__":
  run()
