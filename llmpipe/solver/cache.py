# The cache machine of nlpsolver.
#
# Three tables in one SQLite file (`cache_db_name`, normally `cache.db`):
#
#   llm_cache    provider responses, keyed by every parameter of the call
#   proof_cache  gk results, keyed by the command and the hashes of its files
#   parse_cache  present for compatibility; no pipeline code reads or writes it
#
# Every table is reached through the same three helpers below -- `_connect`,
# `_ensure_table` and `_fetch_one` / `_insert` -- so the connection lifetime,
# the lock timeout and the failure policy are stated once.
#
# FAILURE POLICY.  A cache is not the answer, so a failure must not end the
# process; but it must not be silent either, because a read failure treated as
# a miss can cost a paid provider call and can make a cached run produce a new
# translation.  So: on the first `sqlite3.Error` for a table, print one line,
# record it in `errors`, and disable that table for the rest of the run.  The
# caller decides what to do about it -- `cache_errors()` reports what happened,
# and a cache-required experiment can check it and stop.  Nothing here calls
# `sys.exit`, and no handler catches `KeyboardInterrupt`.
#
# CONCURRENCY.  `runtests.py` runs one worker process per provider against one
# file.  Writes are `insert or ignore`, so two workers inserting the same key
# race harmlessly instead of raising `IntegrityError`; `_LOCK_TIMEOUT` bounds
# how long a writer waits for the other's lock.
#
#-----------------------------------------------------------------
# Copyright 2022 Tanel Tammet (tanel.tammet@gmail.com)
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

# ==== standard libraries ====

import contextlib
import hashlib
import json
import sqlite3

# ==== import other source files ====

# configuration and other globals are in globals.py
from globals import *

import utils


# ======== the shared SQLite layer ========

# Seconds a writer waits for another process's lock before giving up.  A gk
# result or a provider response is worth a short wait and never a long one:
# the work that produced it is already done, and losing the row only costs a
# repeat later.
_LOCK_TIMEOUT = 10.0

# One row per table that has failed, so a caller can tell a cold cache from a
# broken one.  `{"llm_cache": "unable to open database file", ...}`
errors = {}

# A table is dropped from use after its first failure, so one broken file does
# not print a line per case.
_disabled = set()


def cache_errors():
  """-> {table: first error message}, empty when every cache worked.

  A run that requires its cache -- a replay, a paired comparison -- should
  check this and stop rather than silently make live calls.
  """
  return dict(errors)


def _fail(table, exc):
  """Record one cache failure, say so once, and stop using that table."""
  if table not in errors:
    errors[table] = str(exc)
    print("Cache warning: %s unusable (%s); continuing without it."
          % (table, exc))
  _disabled.add(table)
  return None


@contextlib.contextmanager
def _connect(table):
  """A connection that always closes, or None when the table is unusable.

  The caller writes `with _connect(t) as conn:` and checks `conn`; every exit
  path closes, which the hand-written paths this replaced did not.
  """
  if not cache_db_name or table in _disabled:
    yield None
    return
  try:
    conn = sqlite3.connect(cache_db_name, timeout=_LOCK_TIMEOUT)
  except sqlite3.Error as e:
    _fail(table, e)
    yield None
    return
  try:
    try:
      yield conn
    except sqlite3.Error as e:
      # A context manager must yield exactly once. Record and suppress a
      # database error escaping from the body, then finish normally; yielding
      # None here would make contextlib hide it behind "generator didn't stop
      # after throw()".
      _fail(table, e)
  finally:
    try:
      conn.close()
    except sqlite3.Error:
      pass


# table -> (its own columns, the column that must be unique)
_TABLES = {
  "llm_cache":   ("keyhash text, outtxt text", "keyhash"),
  "proof_cache": ("intxt text, outtxt text, outtype text", "intxt"),
  "parse_cache": ("intxt text, outtxt text, outtype text", "intxt"),
}


def _ensure_table(conn, table):
  """Create the table and its unique index if they are missing.

  `if not exists` on both, so two workers creating the same table at once do
  not race.  -> True when the table is usable.
  """
  cols, uniq = _TABLES[table]
  try:
    conn.execute("create table if not exists %s "
                 "(id integer primary key autoincrement, %s, "
                 "timestamp datetime default current_timestamp)" % (table, cols))
    conn.execute("create unique index if not exists %s_%s on %s (%s)"
                 % (table, uniq, table, uniq))
    conn.commit()
    return True
  except sqlite3.Error as e:
    _fail(table, e)
    return False


def _fetch_one(table, sql, args):
  """-> the first row, or None for a miss, a missing table or a failure."""
  with _connect(table) as conn:
    if conn is None:
      return None
    try:
      cur = conn.cursor()
      cur.execute(sql, args)
      return cur.fetchone()
    except sqlite3.OperationalError:
      # Almost always "no such table": a cold cache, not a fault.  Create it
      # so the next write has somewhere to go, and report the miss.
      _ensure_table(conn, table)
      return None
    except sqlite3.Error as e:
      return _fail(table, e)


def _insert(table, columns, values):
  """Insert one row, ignoring a key another worker already wrote."""
  with _connect(table) as conn:
    if conn is None:
      return False
    if not _ensure_table(conn, table):
      return False
    try:
      conn.execute("insert or ignore into %s (%s) values (%s)"
                   % (table, ", ".join(columns),
                      ", ".join("?" * len(values))), values)
      conn.commit()
      return True
    except sqlite3.Error as e:
      _fail(table, e)
      return False


def _encode(outdata):
  """-> (text, "text"|"json") for a value going into a cache row."""
  if isinstance(outdata, str):
    return outdata, "text"
  return json.dumps(outdata), "json"


def _decode(row):
  """-> the value a `(outtxt, outtype)` row holds."""
  return row[0] if row[1] == "text" else json.loads(row[0])


# ======== the parse cache ========
#
# Kept as a compatibility interface: no pipeline module reads or writes it, and
# an existing cache.db may still hold its rows.  `clear_all_caches` clears it
# with the others.

def add_parse_to_cache(ctxt, intxt, outdata):
  if not options.get("use_cache_flag"):
    return
  if not intxt or not outdata or not isinstance(intxt, str):
    return
  outtxt, outtype = _encode(outdata)
  if _insert("parse_cache", ("intxt", "outtxt", "outtype"),
             (intxt, outtxt, outtype)):
    utils.debug_print("parse cache insert done")


def get_parse_from_cache(ctxt, intxt):
  if not options.get("use_cache_flag"):
    return None
  if not intxt or not isinstance(intxt, str):
    return None
  row = _fetch_one("parse_cache",
                   "select outtxt,outtype from parse_cache where intxt=?",
                   (intxt,))
  if not row:
    return None
  utils.debug_print("Parse obtained from cache")
  return _decode(row)


# ======== the proof cache ========

def add_proof_to_cache(inparams, outdata):
  if not options.get("use_cache_flag"):
    return
  if not inparams or not outdata:
    return
  intxt = make_proof_key(inparams)
  if not intxt or not isinstance(intxt, str):
    return
  outtxt, outtype = _encode(outdata)
  if _insert("proof_cache", ("intxt", "outtxt", "outtype"),
             (intxt, outtxt, outtype)):
    utils.debug_print("proof cache insert done")


def get_proof_from_cache(ctxt, inparams):
  if not options.get("use_cache_flag"):
    return None
  if not inparams:
    return None
  intxt = make_proof_key(inparams)
  if not intxt or not isinstance(intxt, str):
    return None
  row = _fetch_one("proof_cache",
                   "select outtxt,outtype from proof_cache where intxt=?",
                   (intxt,))
  if not row:
    return None
  utils.debug_print("Proof obtained from cache")
  return _decode(row)


def make_proof_key(inparams):
  """The gk command as a cache key: its flags verbatim, its files by content.

  A file argument is replaced by the hash of what it held, so a changed axiom
  file or clause file misses the cache instead of returning the old proof.
  The first argument (the gk binary) and every `-flag value` pair stay
  literal.  -> None when a named file cannot be read.
  """
  file_params = []
  non_file_params = []
  lastel_key = False
  for i, el in enumerate(inparams):
    if el and el.startswith("-"):
      lastel_key = True
      non_file_params.append(el)
    elif lastel_key:
      lastel_key = False
      non_file_params.append(el)
    elif i == 0:
      non_file_params.append(el)          # the binary itself
    else:
      file_params.append(el)
  hashes = []
  for fname in file_params:
    h = get_file_hash(fname)
    if not h:
      return None
    hashes.append(h)
  return " ".join(non_file_params + hashes)


def get_file_hash(fname):
  """-> the md5 of a file's contents, or None when it cannot be read."""
  try:
    with open(fname, "rb") as f:
      file_hash = hashlib.md5()
      while True:
        chunk = f.read(8192)
        if not chunk:
          break
        file_hash.update(chunk)
  except OSError:
    return None
  return file_hash.hexdigest()


# ======== the model-response cache ========

def make_llm_cache_key(llm, version, temperature, seed, max_tokens, think,
                       sysprompt, input_text):
  """A deterministic SHA-256 digest identifying one model call.

  Every parameter that can change the response is in the key, so a changed
  provider, version, temperature, seed, token limit, thinking setting, system
  prompt or input misses the cache rather than returning a stale response.
  """
  key_obj = {
    "llm":         llm         or "",
    "version":     version     or "",
    "temperature": temperature,
    "seed":        seed,
    "max_tokens":  max_tokens  or 0,
    "think":       think if isinstance(think, int) else bool(think),
    "sysprompt":   sysprompt   or "",
    "input":       input_text  or "",
  }
  canonical = json.dumps(key_obj, sort_keys=True, ensure_ascii=False)
  return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_llm_from_cache(key):
  """-> the cached response for `key`, or None.

  None means a miss, a cold cache or a failed read; the three are separated by
  `cache_errors()`, which a caller that must not make a live call should check.
  """
  if not options.get("use_llm_cache_flag", True):
    return None
  if not key:
    return None
  row = _fetch_one("llm_cache",
                   "select outtxt from llm_cache where keyhash=?", (key,))
  if not row:
    return None
  utils.debug_print("LLM response obtained from cache")
  return row[0]


def add_llm_to_cache(key, result):
  """Store one model response.  A key another worker already wrote is kept."""
  if not options.get("use_llm_cache_flag", True):
    return
  if not key or not result or not isinstance(result, str):
    return
  if _insert("llm_cache", ("keyhash", "outtxt"), (key, result)):
    utils.debug_print("LLM cache insert done")


# ======== clearing ========

def _clear_one(table):
  """Delete every row of one table.  -> the number deleted."""
  with _connect(table) as conn:
    if conn is None:
      return 0
    try:
      cur = conn.cursor()
      cur.execute("select count(*) from %s" % table)
      n = cur.fetchone()[0]
      conn.execute("delete from %s" % table)
      conn.commit()
      return n
    except sqlite3.OperationalError:
      return 0                            # no such table: nothing to delete
    except sqlite3.Error as e:
      _fail(table, e)
      return 0


# Kept as a compatibility interface: the pipeline uses `clear_all_caches`, but
# an interactive session or a local script may clear one table on its own.

def clear_parse_cache(ctxt=None):
  return _clear_one("parse_cache")


def clear_proof_cache(ctxt=None):
  return _clear_one("proof_cache")


def clear_llm_cache():
  return _clear_one("llm_cache")


def clear_all_caches():
  """Delete every row of every cache table.

  -> {"llm": N, "proof": N, "parse": N}, the rows deleted from each.  A table
  that does not exist counts as 0.  A failure is recorded in `errors` and
  reported as 0 for that table, never as an exception.
  """
  return {table.split("_")[0]: _clear_one(table) for table in _TABLES}
