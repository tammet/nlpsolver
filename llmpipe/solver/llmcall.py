# LLM API call functions for the nlpsolver: GPT, Claude, Gemini, DeepSeek.
#
# Primary entry point: call_llm(sysprompt, input_text)
# Returns the result string on success, or None on error (error is printed).
#
#-----------------------------------------------------------------
# Copyright 2026 Tanel Tammet (tanel.tammet@gmail.com)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#-------------------------------------------------------------------

import time
import sys
import contextlib
import json
import os
import random
import hashlib
import http.client

# Absolute path to llmpipe/ so secrets files are found from any working directory.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# LLM response cache (same SQLite db used for prover and parse caches).
# Import is conditional so llmcall.py remains usable stand-alone for testing.
try:
  import cache as _cache
except ImportError:
  _cache = None

import utils

# ======== configuration ========

# Which LLM to use: "gpt", "claude", "gemini", or "deepseek"
use_llm = "claude"
use_llm = "gemini"

# Model versions
gptversion = "gpt-5.1"
claudeversion = "claude-sonnet-4-6"
geminiversion = "gemini-2.5-flash"
deepseekversion = "deepseek-v4-flash"      # V4-flash (deepseek-chat alias was V3.2, deprecated); "deepseek-reasoner" for thinking

# New-model trial set (2026-08-04): swap these in to re-run that comparison.
# The version-gated API compatibility code below (sonnet-5 thinking-off,
# gemini-3 thinkingLevel, deepseek -pro reasoning-off) stays active for them.
# gptversion = "gpt-5.6-luna"
# claudeversion = "claude-sonnet-5"
# geminiversion = "gemini-3.6-flash"
# deepseekversion = "deepseek-v4-pro"

# API key files (absolute paths relative to llmpipe/)
_secrets_dir = os.path.normpath(os.path.join(_root, "..", "secrets"))
gpt_secrets_file = os.path.join(_secrets_dir, "gpt_secrets.txt")
claude_secrets_file = os.path.join(_secrets_dir, "claude_secrets.txt")
gemini_secrets_file = os.path.join(_secrets_dir, "gemini_secrets.txt")
deepseek_secrets_file = os.path.join(_secrets_dir, "deepseek_secrets.txt")

# Call parameters
temperature = 0
seed = 1234
default_max_tokens = 8000
sleepseconds = 2
timeout = 60
max_retries = 3
# Extra re-calls when a provider returns None or an empty/whitespace string
# from a 200-OK response (transient malformed/empty payload — not retried by
# _post_with_retry, which only retries HTTP-level failures).
empty_response_retries = 2

# Debug output
debug = False
calldebug = False

# ======== per-call latency and token recording ========

# When record_calls is True, every call_llm() appends one dict to call_log:
#   {"llm","version","seconds","source",
#    "input","cached_input","cache_write","output","thinking"}
# source is "api" for a real request and "cache" for a local SQLite cache hit
# (token counts are then absent).  "input" always counts the tokens billed at
# the full input rate: providers disagree on whether their own input count
# includes the cache-read tokens, so each provider function subtracts as
# needed.  Set record_calls = False to switch off.
record_calls = True
call_log = []

# Every entry also carries the stage that made the call.  Without it a run
# says how many calls it made and not who made them, which is the whole
# question when three mechanisms share one pipeline.  `tagged` sets the label
# for a block; an inner block may rename the tag or only add fields.
call_tag = "untagged"
call_fields = {}


@contextlib.contextmanager
def tagged(tag=None, **fields):
  """Label the calls made inside this block.  tag=None keeps the outer tag."""
  global call_tag, call_fields
  old_tag, old_fields = call_tag, call_fields
  call_tag = tag if tag is not None else old_tag
  merged = dict(old_fields)
  merged.update(fields)
  call_fields = merged
  try:
    yield
  finally:
    call_tag, call_fields = old_tag, old_fields


def _label():
  out = {"tag": call_tag}
  out.update(call_fields)
  return out

_last_usage = None      # set by the provider functions, consumed by call_llm


def reset_call_log():
  """Clear the recorded calls (call once per test case)."""
  del call_log[:]


def _note_usage(input=None, cached_input=None, cache_write=None,
                output=None, thinking=None):
  """Record normalized token counts of the request just completed.
  Counts add up when one call_llm() makes several requests (a provider-level
  retry, or gemini's cache-miss and truncation retries)."""
  global _last_usage
  if not record_calls:
    return
  new = {"input": input, "cached_input": cached_input,
         "cache_write": cache_write, "output": output, "thinking": thinking}
  if _last_usage:
    for k, v in new.items():
      old = _last_usage.get(k)
      new[k] = v if old is None else (old if v is None else old + v)
  _last_usage = new


def _usage_number(d, *path):
  """Fetch a nested numeric field, or None if any step is missing."""
  for k in path:
    if not isinstance(d, dict) or k not in d:
      return None
    d = d[k]
  return d if isinstance(d, (int, float)) else None


# ======== main entry point ========

# ---------------------------------------------------------------------------
# Per-call deadline
#
# `api_timeout` bounded only the initial parse and conversion phase, so a
# critic, graph or bridge call -- with its retries and its backoff sleeps --
# could block a case for an unbounded time.  This deadline sits at the one
# boundary every LLM call passes through, so it covers the initial translation
# and every later stage alike.  It bounds the complete logical call: provider
# attempts, retries, the sleeps between them, and Gemini's context-cache
# requests.  It never encloses gk, which runs outside this function.
#
# The deadline is cooperative and absolute: one monotonic instant is computed
# per logical `call_llm`, and every place that can block consults it.  An
# earlier version waited on a daemon thread, which returned on time but left
# the provider request running -- it could consume a request after the
# timeout, overlap the next stage and mutate the usage accounting afterwards.
# Nothing is abandoned now: when the instant passes, the code raises and
# unwinds, so no request, retry, sleep, thread or timer outlives the call.
# ---------------------------------------------------------------------------

TIMEOUT_MARKER = "llm_call_timeout"
LIMIT_MARKER = "llm_call_limit"


def _now():
  """Monotonic clock.  A test may replace this to run a fake clock."""
  return time.monotonic()


class LlmDeadlineExceeded(Exception):
  """The per-call deadline passed.  Raised from wherever the call was."""

  def __init__(self, where):
    Exception.__init__(self, where)
    self.where = where


class LlmCallLimitExceeded(Exception):
  """The run's total logical-call limit is already used up."""


class Deadline(object):
  """One absolute instant, plus the arithmetic every caller needs."""

  def __init__(self, seconds, started=None):
    self.limit = float(seconds)
    self.started = _now() if started is None else started
    self.at = self.started + self.limit

  def elapsed(self):
    return _now() - self.started

  def remaining(self):
    return self.at - _now()

  def expired(self):
    return self.remaining() <= 0

  def check(self, where):
    if self.expired():
      raise LlmDeadlineExceeded(where)

  def bounded(self, base):
    """`base` seconds, never past the deadline.  The lower-level HTTP timeout
    stays an upper bound when it is the smaller of the two."""
    left = self.remaining()
    if left <= 0:
      raise LlmDeadlineExceeded("bounding a wait")
    return min(base, left) if base else left

  def sleep(self, seconds, where="backoff"):
    """Sleep, never past the deadline, then check it."""
    self.check(where)
    time.sleep(max(0.0, min(seconds, self.remaining())))
    self.check(where)


# The deadline of the logical call now in progress, or None.  Set and cleared
# by `call_llm`; read by `_post_with_retry` and the Gemini cache helpers, which
# are several frames below and take it as a default argument.
_deadline = None


def _check_deadline(where, deadline=None):
  d = deadline if deadline is not None else _deadline
  if d is not None:
    d.check(where)


def _http_timeout(deadline=None):
  """The connection timeout for one request: the configured HTTP timeout, cut
  down to what is left of the deadline."""
  d = deadline if deadline is not None else _deadline
  if d is None:
    return timeout
  return d.bounded(timeout)


def _sleep_bounded(seconds, where="backoff", deadline=None):
  d = deadline if deadline is not None else _deadline
  if d is None:
    time.sleep(seconds)
    return
  d.sleep(seconds, where)


# ---------------------------------------------------------------------------
# Model identity
#
# One run uses one provider and one version for every call it makes: Stage 1,
# Stage 2 and its format corrections, the critic, the critic's retranslation,
# the graph retranslation, the graph bridges and the literal bridges.  A call
# that names anything else is a defect, not a fallback, so it fails at once
# rather than quietly answering from another model.  A cached response from
# another model is refused for the same reason.
# ---------------------------------------------------------------------------

class ModelMismatch(RuntimeError):
  """A call named a provider or version other than the run's own."""


_model_lock = None


@contextlib.contextmanager
def locked_model(llm, version):
  """Pin the provider and version for every call made inside this block."""
  global _model_lock
  old = _model_lock
  _model_lock = (llm, version) if llm else old
  try:
    yield
  finally:
    _model_lock = old


def _check_model(llm, ver):
  if _model_lock is None:
    return
  want_llm, want_ver = _model_lock
  if llm != want_llm or (want_ver and ver != want_ver):
    raise ModelMismatch(
      "this run is pinned to %s %s; a call named %s %s"
      % (want_llm, want_ver, llm, ver))


# ---------------------------------------------------------------------------
# Total logical-call limit
#
# One counter for the whole run, incremented by every `call_llm` from every
# role -- Stage 1, Stage 2 and its format corrections, the critic and its
# rerun, the graph retranslation, the graph bridges, the literal bridges -- and
# by a local cache hit as well, because a cache hit is still a logical call the
# pipeline decided to make.  Checked before the cache lookup and before any
# provider dispatch, so a refused call touches neither.
# ---------------------------------------------------------------------------

# One vocabulary for the whole run, so the global record and the per-stage rows
# cannot disagree:
#
#   allowed            logical call_llm invocations the limit permitted
#   cached             allowed calls answered from the local cache
#   live               allowed calls dispatched to a provider, counted ONCE
#                      each, whether they then succeed, fail or time out
#   refused            invocations refused before cache lookup and dispatch
#   attempted          allowed + refused
#   provider_requests  actual outbound requests, including the HTTP retries
#                      inside _post_with_retry
#
# The invariants are `allowed == cached + live` and
# `attempted == allowed + refused`.
_counts = {"allowed": 0, "cached": 0, "live": 0, "refused": 0,
           "provider_requests": 0}


def reset_call_limit():
  """Start a new run's accounting.  Called once per case."""
  for k in _counts:
    _counts[k] = 0


def call_counts():
  out = dict(_counts)
  out["attempted"] = out["allowed"] + out["refused"]
  return out


def _call_limit():
  try:
    import globals
    v = globals.options.get("llm_call_limit", 0)
  except Exception:                                              # pragma: no cover
    return 0
  try:
    v = int(v or 0)
  except (TypeError, ValueError):
    return 0
  return v if v > 0 else 0


def _take_call_slot():
  """Claim one logical call, or raise when the run's limit is used up.

  A refused invocation never becomes an allowed one, so it consumes no slot and
  is counted separately.
  """
  limit = _call_limit()
  if limit and _counts["allowed"] >= limit:
    _counts["refused"] += 1
    raise LlmCallLimitExceeded(
      "this run's limit of %d logical LLM calls is used up" % limit)
  _counts["allowed"] += 1


def _call_timeout():
  """The per-call deadline in seconds, or 0 for none."""
  try:
    import globals
    v = globals.options.get("llm_call_timeout", 0)
  except Exception:                                              # pragma: no cover
    return 0
  try:
    v = float(v or 0)
  except (TypeError, ValueError):
    return 0
  return v if v > 0 else 0


def call_llm(sysprompt, input_text, llm=None, version=None, max_tokens=None, think=False):
  """Call the configured LLM with a system prompt and input text.

  llm, version, max_tokens, think override module-level configuration when given.
  think=True enables medium reasoning mode (GPT: reasoning_effort=medium;
  Claude: extended thinking with budget_tokens=8000; Gemini: thinkingConfig
  if the model supports it).  think can also be an int, interpreted as the
  thinking budget in tokens (Claude budget_tokens, Gemini thinkingBudget).
  Returns the result string on success, or None on error (error is printed).

  LLM responses are cached by default.  The cache key encodes the provider,
  version, temperature, seed, max_tokens, think, sysprompt and input text, so a
  cached result is only reused when every one of these is identical.
  Caching is controlled by globals.options["use_llm_cache_flag"] (default
  True) and can be disabled per-run via -nollmcache in solve.py.
  """
  llm = llm or use_llm
  max_tokens = max_tokens or default_max_tokens

  # Resolve the actual version here so the cache key is fully deterministic.
  if llm == "claude":
    ver = version or claudeversion
  elif llm == "gemini":
    ver = version or geminiversion
  elif llm == "deepseek":
    ver = version or deepseekversion
  else:
    ver = version or gptversion

  _check_model(llm, ver)

  # One logical call, counted before the cache is consulted and before any
  # provider is dispatched: a refused call touches neither.
  try:
    _take_call_slot()
  except LlmCallLimitExceeded as exc:
    if record_calls:
      rec = {"llm": llm, "version": ver, "source": "refused", "seconds": 0.0,
             "failed": True, "reason": LIMIT_MARKER, "logical": True,
             "limit": _call_limit()}
      rec.update(_label())
      call_log.append(rec)
    return llm_error("%s: %s" % (LIMIT_MARKER, exc))

  # --- check cache ---
  _t0 = time.time()
  cached = _get_llm_cached(llm, ver, max_tokens, think, sysprompt, input_text)
  if cached is not None:
    if debug:
      print("cache hit (" + llm + " " + ver + ")")
    _counts["cached"] += 1
    if record_calls:
      rec = {"llm": llm, "version": ver, "source": "cache", "logical": True,
             "seconds": round(time.time() - _t0, 3)}
      rec.update(_label())
      call_log.append(rec)
    return cached

  # --- call the LLM (retry on None / empty response) ---
  # All providers can return None (200-OK but missing the expected structure)
  # or an empty string (content blocks present but text-less) from a transient
  # failure.  _post_with_retry does not retry these, so retry here.
  if debug:
    print("calling " + llm + " " + ver + " ...")
  result = None
  global _last_usage, _deadline
  budget = _call_timeout()
  deadline = Deadline(budget) if budget else None
  outer_deadline = _deadline
  _deadline = deadline
  # An allowed cache miss is one logical live call, counted once here.  The
  # empty-response retries below are further provider requests, not further
  # logical calls.
  _counts["live"] += 1
  _first_api_entry = [True]

  def _timed_out(where):
    """Record and report one timed-out logical call."""
    elapsed = round(deadline.elapsed(), 3)
    if record_calls:
      rec = {"llm": llm, "version": ver, "source": "api",
             "seconds": elapsed, "failed": True,
             "logical": _first_api_entry[0],
             "reason": TIMEOUT_MARKER, "where": where,
             "timeout_seconds": budget}
      _first_api_entry[0] = False
      rec.update(_label())
      call_log.append(rec)
    return llm_error(
      "%s call to %s %s exceeded the %gs per-call deadline after %.1fs (%s)"
      % (TIMEOUT_MARKER, llm, ver, budget, elapsed, where))

  try:
    for attempt in range(1, empty_response_retries + 2):
      _last_usage = None
      _t0 = time.time()
      try:
        if deadline is not None:
          deadline.check("before attempt %d" % attempt)
        if llm == "claude":
          result = call_claude(ver, input_text, sysprompt, max_tokens,
                               think=think)
        elif llm == "gemini":
          result = call_gemini(ver, input_text, sysprompt, max_tokens,
                               think=think)
        elif llm == "deepseek":
          result = call_deepseek(ver, input_text, sysprompt, max_tokens,
                                 think=think)
        else:
          result = call_gpt(ver, input_text, sysprompt, max_tokens, think=think)
        # the request may have returned just as the deadline passed
        if deadline is not None:
          deadline.check("after attempt %d" % attempt)
      except LlmDeadlineExceeded as late:
        return _timed_out(late.where)
      except KeyboardInterrupt:
        raise
      except MissingApiKeyError as e:
        # Permanent configuration error — do not retry.
        return llm_error(str(e))
      except Exception as e:
        return llm_error("unexpected error calling LLM: " + str(e))
      if record_calls:
        rec = {"llm": llm, "version": ver, "source": "api",
               "logical": _first_api_entry[0],
               "seconds": round(time.time() - _t0, 3)}
        _first_api_entry[0] = False
        rec.update(_label())
        if _last_usage:
          rec.update(_last_usage)
        if result is None or not result.strip():
          rec["failed"] = True
        call_log.append(rec)
      if result is not None and result.strip():
        break
      if attempt <= empty_response_retries:
        print(llm + " returned an empty/None response, retrying...")
        try:
          _sleep_bounded(sleepseconds * attempt,
                         "empty-response retry %d" % attempt, deadline)
        except LlmDeadlineExceeded as late:
          return _timed_out(late.where)
  finally:
    # nothing of this call outlives it
    _deadline = outer_deadline

  # --- store to cache (skip None / empty — likely a transient failure) ---
  if result is not None and result.strip():
    _store_llm_cached(llm, ver, max_tokens, think, sysprompt, input_text, result)

  return result


def _get_llm_cached(llm, ver, max_tokens, think, sysprompt, input_text):
  """Return a cached LLM result, or None if not cached / cache disabled."""
  if _cache is None:
    return None
  try:
    key = _cache.make_llm_cache_key(llm, ver, temperature, seed, max_tokens, think, sysprompt, input_text)
    return _cache.get_llm_from_cache(key)
  except Exception:
    return None


def _store_llm_cached(llm, ver, max_tokens, think, sysprompt, input_text, result):
  """Store result in the LLM cache (silently ignored on any error)."""
  if _cache is None or result is None:
    return
  try:
    key = _cache.make_llm_cache_key(llm, ver, temperature, seed, max_tokens, think, sysprompt, input_text)
    _cache.add_llm_to_cache(key, result)
  except Exception:
    pass


# ======== shared helpers ========

class MissingApiKeyError(Exception):
  """Raised when an LLM provider's secrets file is missing or unreadable.
  Used by call_llm to abort retrying on a permanent configuration error."""
  pass


def _read_api_key(filepath, provider):
  """Read an API key from a plain-text file.
  Raises MissingApiKeyError if the file is missing, unreadable, or empty.
  Callers should not catch this — let call_llm handle it to avoid useless retries."""
  try:
    with open(filepath, "r") as f:
      key = f.read().strip()
  except FileNotFoundError:
    raise MissingApiKeyError(
      provider + " API key file not found: " + str(filepath) +
      "\n  Create it with your provider key. See ../secrets/README.txt for details."
    )
  except OSError as e:
    raise MissingApiKeyError(
      "Could not read " + provider + " API key file: " + str(filepath) + " (" + str(e) + ")"
    )
  if not key:
    raise MissingApiKeyError(provider + " API key file is empty: " + str(filepath))
  return key


_rate_limit_max_retries = 7   # 429: exponential backoff goes 2,4,8,16,32,64,128s


def _post_with_retry(host, url, body, headers, provider, deadline=None):
  """POST JSON body to host/url with retries. Returns parsed response dict or None.

  Two retry tracks:
    - 429 (rate limit): exponential backoff with jitter, _rate_limit_max_retries
      attempts. Quota windows are typically per-minute, so short retries don't help.
    - Other HTTP / connection failures: linear backoff, max_retries attempts.

  Both tracks are inside the per-call deadline: the remaining time is checked
  before every attempt and every sleep, each connection timeout is cut down to
  what is left, and no sleep runs past the instant.  `LlmDeadlineExceeded`
  unwinds to `call_llm`, so nothing keeps running once it fires."""
  trycount = 0
  rate_tries = 0
  while True:
    _check_deadline("before a %s request" % provider, deadline)
    _counts["provider_requests"] += 1
    conn = http.client.HTTPSConnection(host,
                                       timeout=_http_timeout(deadline))
    try:
      conn.request("POST", url, body, headers=headers)
      response = conn.getresponse()
    except KeyboardInterrupt:
      raise
    except LlmDeadlineExceeded:
      if conn: conn.close()
      raise
    except Exception:
      trycount += 1
      if conn: conn.close()
      _check_deadline("after a %s connection failure" % provider, deadline)
      if trycount > max_retries:
        return llm_error(provider + " connection failed after " + str(max_retries) + " retries")
      print(provider + " connection failure, retrying...")
      _sleep_bounded(sleepseconds * trycount,
                     "%s connection backoff" % provider, deadline)
      continue
    _check_deadline("after a %s response" % provider, deadline)
    if response.status == 429:
      # Rate-limited: exponential backoff with jitter. Provider quota
      # windows are typically per-minute, so we wait long enough for the
      # quota to refresh rather than burning through short retries.
      message = ""
      try:
        data = json.loads(response.read())
        if "error" in data and "message" in data["error"]:
          message = ": " + data["error"]["message"]
      except Exception:
        pass
      if conn: conn.close()
      rate_tries += 1
      if rate_tries > _rate_limit_max_retries:
        return llm_error(provider + " API rate-limited (429) after " + str(_rate_limit_max_retries) + " retries" + message)
      base = 2 ** rate_tries                       # 2, 4, 8, 16, 32, 64, 128
      delay = base + random.uniform(0, base * 0.25)
      print(provider + " rate-limited (429), waiting " + str(round(delay, 1)) +
            "s before retry " + str(rate_tries) + "/" + str(_rate_limit_max_retries))
      _sleep_bounded(delay, "%s rate-limit backoff" % provider, deadline)
      continue
    if response.status != 200 or response.reason != "OK":
      message = ""
      try:
        data = json.loads(response.read())
        if "error" in data and "message" in data["error"]:
          message = ": " + data["error"]["message"]
      except Exception:
        pass
      trycount += 1
      if conn: conn.close()
      if trycount > max_retries:
        return llm_error(provider + " API error " + str(response.status) + " " + str(response.reason) + message)
      print(provider + " API failure, retrying:", str(response.status), str(response.reason) + message)
      _sleep_bounded(sleepseconds * trycount,
                     "%s API-error backoff" % provider, deadline)
    else:
      break

  rawdata = response.read()
  conn.close()
  try:
    return json.loads(rawdata)
  except KeyboardInterrupt:
    raise
  except Exception:
    return llm_error(provider + " response is not valid JSON: " + str(rawdata))


# ======== gemini ========

# https://ai.google.dev/gemini-api/docs/text-generation
# https://ai.google.dev/gemini-api/docs/caching   (context caching)

# Context-caching state.  Keyed by (model, sha256(sysprompt)) → (cache_name,
# expire_ts).  Per-process — multiprocessing workers each maintain their
# own map.  Gemini enforces a tight per-request input-token cap above which
# large prompts get instant 429 even on the paid tier; caching shifts the
# sysprompt onto Google's server and removes that weight from the request.
_gemini_cache_map = {}
_GEMINI_CACHE_TTL = 1800        # seconds (30 min) — extendable per call
_GEMINI_CACHE_GRACE = 30        # treat cache as expired 30s before TTL ends
_GEMINI_CACHE_MIN_CHARS = 16000 # ~4096 tokens; gemini's minimum cacheable size


def _gemini_cache_key(model, sysprompt):
  h = hashlib.sha256(sysprompt.encode("utf-8")).hexdigest()
  return (model, h)


def _gemini_should_cache(sysprompt):
  if not sysprompt or len(sysprompt) < _GEMINI_CACHE_MIN_CHARS:
    return False
  try:
    import globals as _globals
    return bool(_globals.options.get("use_gemini_cache_flag", True))
  except Exception:
    return True   # default ON when running stand-alone


def _gemini_invalidate_cache(model, sysprompt):
  _gemini_cache_map.pop(_gemini_cache_key(model, sysprompt), None)


def _gemini_get_or_create_cache(model, sysprompt, api_key, deadline=None):
  """Return a live cachedContents name for this (model, sysprompt), creating
  one if no live entry exists.  Returns None on failure (caller should
  fall back to inline system_instruction)."""
  ckey = _gemini_cache_key(model, sysprompt)
  now = time.time()
  entry = _gemini_cache_map.get(ckey)
  if entry and entry[1] > now + _GEMINI_CACHE_GRACE:
    return entry[0]

  body = {
    "model": "models/" + model,
    "contents": [{"role": "user", "parts": [{"text": sysprompt}]}],
    "ttl": str(_GEMINI_CACHE_TTL) + "s",
  }
  host = "generativelanguage.googleapis.com"
  # the context-cache request is part of the logical call, so it is inside the
  # same deadline as the generation request
  _check_deadline("before the Gemini context-cache request", deadline)
  conn = http.client.HTTPSConnection(host, timeout=_http_timeout(deadline))
  try:
    conn.request("POST", "/v1beta/cachedContents", json.dumps(body),
                 headers={"content-Type": "application/json",
                          "x-goog-api-key": api_key})
    resp = conn.getresponse()
    raw = resp.read().decode()
    if resp.status != 200:
      print("Gemini cache creation failed (" + str(resp.status) + " " +
            str(resp.reason) + "): " + raw[:300])
      return None
    data = json.loads(raw)
  except KeyboardInterrupt:
    raise
  except LlmDeadlineExceeded:
    raise
  except Exception as e:
    print("Gemini cache creation error: " + str(e))
    return None
  finally:
    conn.close()

  name = data.get("name")
  if not name:
    return None
  _gemini_cache_map[ckey] = (name, now + _GEMINI_CACHE_TTL)
  return name


def _gemini_supports_thinking(version):
  """Return True if this Gemini model version supports thinkingConfig.
  Thinking is supported by models with 'thinking' in the name and by
  Gemini 2.5+ series (which have built-in thinking capability)."""
  v = version.lower()
  if "thinking" in v:
    return True
  # gemini-2.5-* and any future major version (3+) support thinking
  import re
  m = re.match(r"gemini-(\d+)[\.-]", v)
  if m and int(m.group(1)) >= 3:
    return True
  if v.startswith("gemini-2.5"):
    return True
  return False


def _gemini_major(version):
  """Major version number of a gemini model name, or 0 if not recognized."""
  import re
  m = re.match(r"gemini-(\d+)[\.-]", (version or "").lower())
  return int(m.group(1)) if m else 0


def _gemini_version_pair(version):
  """(major, minor) of a gemini model name, or (0, 0) if not recognized."""
  import re
  m = re.match(r"gemini-(\d+)\.(\d+)", (version or "").lower())
  if m:
    return (int(m.group(1)), int(m.group(2)))
  return (_gemini_major(version), 0)


class ThinkingLevelError(Exception):
  """An explicit thinking level the provider or model does not accept."""


def thinking_level(think):
  """-> the level name a caller asked for, or None for the old True/False.

  `think` has always been False (off), True (the provider's default thinking)
  or an int budget.  It may now also be a level name, so an experiment can ask
  for a level between those two without changing what True and False mean.
  """
  return think if isinstance(think, str) else None


def _gpt_effort(think):
  """-> the reasoning effort to send.  gpt-5.x takes none/low/medium/high."""
  level = thinking_level(think)
  if level is None:
    return "medium" if think else "none"
  if level not in ("none", "low", "medium", "high"):
    raise ThinkingLevelError("GPT takes none, low, medium or high, not %r"
                             % level)
  return level


def _gemini_level(think, version):
  """-> the thinkingLevel to send to a gemini-3 model."""
  level = thinking_level(think)
  if level is None:
    return "high" if think else _gemini_cheapest_level(version)
  if level not in ("minimal", "low", "medium", "high"):
    raise ThinkingLevelError("gemini 3 takes minimal, low, medium or high, "
                             "not %r" % level)
  floor = _gemini_cheapest_level(version)
  if level == "minimal" and floor != "minimal":
    raise ThinkingLevelError("%s does not accept MINIMAL; its floor is %s"
                             % (version, floor))
  return level


def _gemini_cheapest_level(version):
  """The cheapest thinkingLevel this Gemini model accepts.

  None of the gemini-3 models can turn thinking off: thinkingLevel takes an
  enum and neither OFF nor NONE is a member.  gemini-3.0 to 3.5 accept MINIMAL.
  gemini-3.7-flash rejects it with 400 "Thinking level MINIMAL is not supported
  for this model", and accepts only LOW, MEDIUM and HIGH (measured 2026-08-14),
  so LOW is the floor there."""
  return "low" if _gemini_version_pair(version) >= (3, 7) else "minimal"


def call_gemini(version, sentences, sysprompt, max_tokens, think=False,
                 deadline=None):
  key = _read_api_key(gemini_secrets_file, "Gemini")
  if key is None: return None

  # Context-caching path: shift large sysprompts off the wire to dodge
  # the per-request input-token ceiling that triggers instant 429s.  The
  # cache stays alive for ~30 min and is reused across calls.
  use_cache = _gemini_should_cache(sysprompt)
  cache_name = (_gemini_get_or_create_cache(version, sysprompt, key,
                                           deadline=deadline)
                if use_cache else None)

  # Gemini 3 and later: temperature is deprecated and thinking is configured
  # by level rather than by token budget (thinkingBudget is rejected with 400).
  # These models think by default, so the level must be set explicitly to keep
  # them comparable with the other providers' non-thinking calls.
  new_api = _gemini_major(version) >= 3

  def _attempt(budget, with_cache):
    genconfig = {"maxOutputTokens": budget}
    if not new_api:
      genconfig["temperature"] = temperature
    if new_api:
      genconfig["thinkingConfig"] = {
        "thinkingLevel": _gemini_level(think, version)}
    elif _gemini_supports_thinking(version):
      # 2.5 thinks by default and its thinking counts against maxOutputTokens,
      # so a non-thinking call must say so explicitly, as the other providers
      # do.  Measured 2026-08-07: without this, hard cases spent 7676-7679 of
      # the 8000-token budget on thinking (up to 23034 elsewhere), leaving a
      # truncated stage-2 JSON, and ordinary calls ran ~32% slower
      # (19.9s vs 13.6s) with no change in output length.
      # bool is a subclass of int, so test it first: think=True must mean the
      # default budget, not a literal True in the request body.
      if thinking_level(think) is not None:
        raise ThinkingLevelError("%s takes a thinking BUDGET, not the level "
                                 "%r" % (version, think))
      if not think:
        tbudget = 0
      elif isinstance(think, bool):
        tbudget = 8000
      else:
        tbudget = int(think)
      genconfig["thinkingConfig"] = {"thinkingBudget": tbudget}
    call = {
      "contents": [{"parts": [{"text": sentences}]}],
      "generationConfig": genconfig
    }
    if with_cache:
      call["cachedContent"] = with_cache
    elif sysprompt:
      call["system_instruction"] = {"parts": [{"text": sysprompt}]}

    utils.debug_print("gemini call", call, flag=calldebug)
    url = "/v1beta/models/" + version + ":generateContent"
    data = _post_with_retry("generativelanguage.googleapis.com", url,
                            json.dumps(call),
                            {"content-Type": "application/json", "x-goog-api-key": key},
                            "Gemini", deadline=deadline)
    if data is None:
      return None, None
    um = data.get("usageMetadata")
    # promptTokenCount includes the cached part; bill the remainder in full.
    prompt = _usage_number(um, "promptTokenCount")
    gcached = _usage_number(um, "cachedContentTokenCount")
    _note_usage(input=None if prompt is None else prompt - (gcached or 0),
                cached_input=gcached,
                output=_usage_number(um, "candidatesTokenCount"),
                thinking=_usage_number(um, "thoughtsTokenCount"))
    if "candidates" not in data:
      return llm_error("Gemini response has no candidates: " + str(data)), None
    cand = data["candidates"][0]
    if "content" not in cand:
      return llm_error("Gemini response has no content: " + str(cand)), None
    if "parts" not in cand["content"]:
      return llm_error("Gemini response has no parts: " + str(cand)), None
    utils.debug_print("gemini response:", data, flag=debug)
    res = ""
    for el in cand["content"]["parts"]:
      if "text" in el:
        res += el["text"].strip()
    return res, cand.get("finishReason")

  res, finish = _attempt(max_tokens, cache_name)
  # If the cache was missing server-side (e.g. evicted between our
  # creation and use), _attempt returns None.  Drop the cache entry,
  # recreate, retry once; on second failure, fall back to inline
  # system_instruction (which will hit the input-token cap but at
  # least surfaces a useful error rather than silently failing).
  if res is None and cache_name:
    _gemini_invalidate_cache(version, sysprompt)
    new_cache = _gemini_get_or_create_cache(version, sysprompt, key,
                                            deadline=deadline)
    if new_cache:
      res, finish = _attempt(max_tokens, new_cache)
    if res is None:
      res, finish = _attempt(max_tokens, None)
  # gemini-2.5+ has built-in thinking that counts against maxOutputTokens, so a
  # verbose answer can be truncated mid-formula (finishReason MAX_TOKENS). The
  # downstream JSON repair then closes the fragment into a malformed atom. Retry
  # once with a larger output budget so the answer has room beyond the thinking.
  if finish == "MAX_TOKENS":
    res, finish = _attempt(max(max_tokens * 2, 16000), cache_name)
  return res


# ======== claude ========

def _claude_uses_effort_api(version):
  """Newer Claude models (Opus 4.8, Sonnet 5, Fable 5, Mythos 5) deprecate
  `temperature` and replace thinking.budget_tokens with adaptive thinking +
  output_config.effort (adaptive thinking is always on for Fable/Mythos)."""
  v = (version or "").lower()
  return ("opus-4-8" in v or "sonnet-5" in v or "fable" in v or "mythos" in v)


def _claude_effort(think):
  """Map a -think value to an effort level for the adaptive-thinking API."""
  if isinstance(think, str) and think.lower() in ("low", "medium", "high"):
    return think.lower()
  if isinstance(think, int):
    if think <= 1500: return "low"
    if think <= 5000: return "medium"
    return "high"
  return "medium"


def call_claude(version, sentences, sysprompt, max_tokens, think=False,
                 deadline=None):
  key = _read_api_key(claude_secrets_file, "Claude")
  if key is None: return None

  messages = [{"role": "user", "content": sentences}]
  use_effort = _claude_uses_effort_api(version)
  call = {
    "model": version,
    "messages": messages,
    "max_tokens": max_tokens
  }
  if not use_effort:                       # newer models deprecate temperature
    call["temperature"] = 1 if think else temperature
  if think:
    if use_effort:
      call["thinking"] = {"type": "adaptive"}
      call["output_config"] = {"effort": _claude_effort(think)}
    else:
      budget = think if isinstance(think, int) else 8000
      call["thinking"] = {"type": "enabled", "budget_tokens": budget}
  elif use_effort:
    # Adaptive-thinking models think by default on anything non-trivial, and
    # the thinking counts against max_tokens: an 8000-token budget is then
    # spent entirely on thinking and the reply comes back with no text at all.
    # The pipeline never asks for thinking, so switch it off explicitly.
    call["thinking"] = {"type": "disabled"}
  if sysprompt:
    call["system"] = [{"type": "text", "text": sysprompt, "cache_control": {"type": "ephemeral"}}]

  utils.debug_print("claude call", call, flag=calldebug)
  data = _post_with_retry("api.anthropic.com", "/v1/messages",
                          json.dumps(call),
                          {"content-Type": "application/json",
                           "anthropic-version": "2023-06-01",
                           "x-api-key": key},
                          "Claude", deadline=deadline)
  if data is None: return None

  # Claude's input_tokens already excludes both cache-read and cache-write.
  u = data.get("usage")
  _note_usage(input=_usage_number(u, "input_tokens"),
              cached_input=_usage_number(u, "cache_read_input_tokens"),
              cache_write=_usage_number(u, "cache_creation_input_tokens"),
              output=_usage_number(u, "output_tokens"),
              thinking=_usage_number(u, "output_tokens_details", "thinking_tokens"))

  if "content" not in data:
    return llm_error("Claude response has no content: " + str(data))

  utils.debug_print("claude response:", data, flag=debug)
  res = ""
  for el in data["content"]:
    if "text" in el:
      res += el["text"].strip()
  return res


# ======== gpt ========

def call_gpt(version, sentences, sysprompt, max_tokens, think=False,
              deadline=None):
  key = _read_api_key(gpt_secrets_file, "GPT")
  if key is None: return None

  if version.startswith("gpt-5"):
    url = "/v1/responses"
    messages = []
    if sysprompt:
      messages.append({"role": "system", "content": [{"type": "input_text", "text": sysprompt}]})
    messages.append({"role": "user", "content": [{"type": "input_text", "text": sentences}]})
    effort = _gpt_effort(think)
    call = {
      "model": version,
      "input": messages,
      "text": {"verbosity": "low", "format": {"type": "text"}},
      "reasoning": {"effort": effort}
    }
    if max_tokens:
      call["max_output_tokens"] = max_tokens
  else:
    url = "/v1/chat/completions"
    messages = []
    if sysprompt:
      messages.append({"role": "system", "content": sysprompt})
    messages.append({"role": "user", "content": sentences})
    call = {
      "model": version,
      "messages": messages,
      "seed": seed,
      "temperature": temperature
    }
    if max_tokens:
      call["max_tokens"] = max_tokens

  utils.debug_print("gpt call", call, flag=calldebug)
  host = "api.openai.com"
  data = _post_with_retry(host, url, json.dumps(call),
                          {"Host": host, "Content-Type": "application/json",
                           "Authorization": "Bearer " + key},
                          "GPT", deadline=deadline)
  if data is None: return None

  utils.debug_print("gpt response:", data, flag=debug)

  # OpenAI's input/prompt count includes the cached part; bill the remainder.
  u = data.get("usage")
  if version.startswith("gpt-5"):
    gin = _usage_number(u, "input_tokens")
    gcached = _usage_number(u, "input_tokens_details", "cached_tokens")
    _note_usage(input=None if gin is None else gin - (gcached or 0),
                cached_input=gcached,
                output=_usage_number(u, "output_tokens"),
                thinking=_usage_number(u, "output_tokens_details", "reasoning_tokens"))
  else:
    gin = _usage_number(u, "prompt_tokens")
    gcached = _usage_number(u, "prompt_tokens_details", "cached_tokens")
    _note_usage(input=None if gin is None else gin - (gcached or 0),
                cached_input=gcached,
                output=_usage_number(u, "completion_tokens"))

  if version.startswith("gpt-5"):
    if "output" not in data:
      return llm_error("GPT response has no 'output'")
    for el in data["output"]:
      if "content" in el and el.get("type") == "message":
        for cel in el["content"]:
          if "text" in cel and cel.get("type") == "output_text":
            return cel["text"]
    return llm_error("GPT response structure not understood: " + str(data))
  else:
    if "choices" not in data:
      return llm_error("GPT response has no 'choices'")
    res = ""
    for el in data["choices"]:
      if "message" in el:
        msg = el["message"]
        if "content" in msg:
          res += msg["content"]
      elif "text" in el:
        if res: res += "\n"
        res += el["text"].strip()
    return res


# ======== deepseek ========

# https://api-docs.deepseek.com/
# DeepSeek uses an OpenAI-compatible chat completions API.

def call_deepseek(version, sentences, sysprompt, max_tokens, think=False,
                   deadline=None):
  key = _read_api_key(deepseek_secrets_file, "DeepSeek")
  if key is None: return None

  # Switch to reasoning model when think is requested.
  if think and version == "deepseek-chat":
    version = "deepseek-reasoner"

  messages = []
  if sysprompt:
    messages.append({"role": "system", "content": sysprompt})
  messages.append({"role": "user", "content": sentences})
  call = {
    "model": version,
    "messages": messages,
    "stream": False
  }
  # deepseek-reasoner does not support temperature or max_tokens.
  if version != "deepseek-reasoner":
    call["temperature"] = temperature
    if max_tokens:
      call["max_tokens"] = max_tokens
  # The V4 models (flash and pro) reason by default, which the pipeline does not
  # ask for and which costs ~8x the latency: switch it off unless thinking was
  # requested, as for the other providers.
  if "-v4-" in version and not think:
    call["reasoning_effort"] = "none"

  utils.debug_print("deepseek call", call, flag=calldebug)
  data = _post_with_retry("api.deepseek.com", "/v1/chat/completions",
                          json.dumps(call),
                          {"Content-Type": "application/json",
                           "Authorization": "Bearer " + key},
                          "DeepSeek", deadline=deadline)
  if data is None: return None

  utils.debug_print("deepseek response:", data, flag=debug)

  # DeepSeek splits the prompt into cache-hit and cache-miss counts directly.
  u = data.get("usage")
  _note_usage(input=_usage_number(u, "prompt_cache_miss_tokens"),
              cached_input=_usage_number(u, "prompt_cache_hit_tokens"),
              output=_usage_number(u, "completion_tokens"),
              thinking=_usage_number(u, "completion_tokens_details", "reasoning_tokens"))

  if "choices" not in data:
    return llm_error("DeepSeek response has no 'choices': " + str(data))
  res = ""
  for el in data["choices"]:
    if "message" in el:
      msg = el["message"]
      if "content" in msg and msg["content"]:
        res += msg["content"]
  return res


# ======== utilities ========

def llm_error(msg):
  print("LLM error:", msg)
  return None


# =========== the end ==========
