#!/usr/bin/env python3
"""A guard that turns a live provider call into an immediate failure.

The action-route copy of the local `tools/cache_only.py`, so the tracked
checks run without the untracked tools directory.

A test that says it replays from the cache should fail loudly the moment it
would pay for a call, rather than quietly making one and reporting a small
number at the end.  Two things are replaced: `_post_with_retry`, which every provider's generation
request goes through, and `http.client.HTTPSConnection`, because Gemini's
context-cache creation opens its own connection and never reaches
`_post_with_retry`.

  import cache_guard
  with cache_guard.guard() as refused:
    ...                      # any live call raises LiveCallRefused
  assert not refused, refused
"""

import contextlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # llmpipe/
sys.path.insert(0, os.path.join(ROOT, "solver"))


class LiveCallRefused(RuntimeError):
  """A guarded block tried to reach a provider."""


@contextlib.contextmanager
def guard():
  """Refuse every outbound provider request inside the block."""
  import http.client
  import llmcall
  # `call_llm` catches everything a provider function raises and returns an
  # error reply, so raising is not enough to make a refusal visible: the count
  # is what a caller checks.
  refusals = []

  real_post = llmcall._post_with_retry

  def refuse(host, url, body, headers, provider, deadline=None):
    refusals.append(provider)
    raise LiveCallRefused(
      "a live %s request was attempted inside a cache-only block "
      "(url %s); the case is not in cache.db under these options"
      % (provider, str(url)[:60]))

  # `_post_with_retry` is not the only way out.  Gemini's context cache opens
  # its own connection before the generation request, so a guard on
  # `_post_with_retry` alone would let a run create a remote context cache.
  # Blocking the connection class covers that path and any other added later.
  real_conn = http.client.HTTPSConnection

  class RefusedConnection(object):
    def __init__(self, host, *a, **k):
      refusals.append("direct:%s" % host)
      raise LiveCallRefused(
        "a direct HTTPS connection to %s was attempted inside a cache-only "
        "block" % host)

  llmcall._post_with_retry = refuse
  llmcall.http.client.HTTPSConnection = RefusedConnection
  try:
    yield refusals
  finally:
    llmcall._post_with_retry = real_post
    llmcall.http.client.HTTPSConnection = real_conn
