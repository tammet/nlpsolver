#!/usr/bin/env python3
"""Run the tracked action-route checks offline, and count what they spend.

Every check runs inside `cache_guard.guard()`, so an attempted provider
request raises `LiveCallRefused` instead of being paid for.  The runner also
counts GK invocations, because the work packages budget those explicitly.

  python3 tests/action_route/run_checks.py            # run every check
  python3 tests/action_route/run_checks.py -k restrict  # run a subset
  python3 tests/action_route/run_checks.py --selftest   # prove the guard bites

A check is a file named `check_*.py` in this directory.  It exposes
`run()`, which returns nothing and raises on failure.  It may import from
`solver/` and read `fixtures/`.  It must not call a provider.  A check that
needs GK names the binary and its SHA-256 itself; the runner only counts it.
"""

import argparse
import contextlib
import importlib.util
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # llmpipe/
sys.path.insert(0, os.path.join(ROOT, "solver"))
sys.path.insert(0, HERE)

import cache_guard                                      # noqa: E402


# the installed prover, which is also the action route's registered build (solver/action_gk.py), and its copies
GK_BINARIES = ("/opt/nlpsolver/gk/gk", "/opt/gk/gk", "/opt/gkreasoner/bin/gk")


class GkCounter(object):
  """Count process launches of a gk binary, without blocking them.

  Counting happens at one boundary only, `subprocess.Popen`, because
  `subprocess.run` launches through `Popen` and wrapping both counted one
  launch twice.  A launch counts when argv[0] resolves to a registered
  backend path (`GK_BINARIES`); a launch whose basename is `gk` but whose
  path is not registered is counted too and listed under `unregistered`,
  so a run against an unknown build is visible in the report.
  """

  def __init__(self):
    self.calls = []
    self.unregistered = []

  def _argv0(self, cmd):
    if isinstance(cmd, str):
      parts = cmd.split()
      return parts[0] if parts else ""
    if cmd:
      return str(cmd[0])
    return ""

  def _classify(self, cmd, executable=None):
    names = [n for n in (executable, self._argv0(cmd)) if n]
    kind = None
    for n in names:
      try:
        real = os.path.realpath(n)
      except (OSError, ValueError):
        real = n
      if real in GK_BINARIES or n in GK_BINARIES:
        return "registered"
      if os.path.basename(n) == "gk":
        kind = "unregistered"
    return kind

  @contextlib.contextmanager
  def watching(self):
    real_popen = subprocess.Popen
    counter = self

    class Popen(real_popen):
      def __init__(inner, cmd, *a, **k):
        kind = counter._classify(cmd, k.get("executable"))
        if kind:
          counter.calls.append(cmd)
          if kind == "unregistered":
            counter.unregistered.append(cmd)
        real_popen.__init__(inner, cmd, *a, **k)

    subprocess.Popen = Popen
    try:
      yield self
    finally:
      subprocess.Popen = real_popen


def discover(pattern=None, where=None):
  names = sorted(f for f in os.listdir(where or HERE)
                 if f.startswith("check_") and f.endswith(".py"))
  if pattern:
    names = [f for f in names if pattern in f]
  return names


def load(name, where=None):
  path = os.path.join(where or HERE, name)
  spec = importlib.util.spec_from_file_location(name[:-3], path)
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  return mod


def selftest():
  """Show the guard refusing a deliberate provider request."""
  import llmcall
  failures = []

  with cache_guard.guard() as refused:
    try:
      llmcall._post_with_retry("api.anthropic.com", "/v1/messages",
                               "{}", {}, "claude")
      failures.append("_post_with_retry was not refused")
    except cache_guard.LiveCallRefused:
      pass
    try:
      llmcall.http.client.HTTPSConnection("generativelanguage.googleapis.com")
      failures.append("a direct HTTPSConnection was not refused")
    except cache_guard.LiveCallRefused:
      pass

  if len(refused) != 2:
    failures.append("expected 2 recorded refusals, got %d" % len(refused))

  for line in failures:
    print("  FAIL  " + line)
  if failures:
    return 1
  print("  ok    _post_with_retry refused (every provider generation request)")
  print("  ok    direct HTTPSConnection refused (Gemini context cache and any"
        " path added later)")
  print("  ok    both refusals recorded: %s" % ", ".join(refused))
  return 0


def run_checks(names, where=None, quiet=False):
  """Run the named checks; return (failed, gk_calls, refused, unregistered).

  A check that raises SystemExit is a failed check, not the end of the
  suite: the report is always printed.  KeyboardInterrupt still stops.
  """
  counter = GkCounter()
  failed = []
  with cache_guard.guard() as refused, counter.watching():
    for name in names:
      before = len(counter.calls)
      try:
        mod = load(name, where)
        mod.run()
      except KeyboardInterrupt:
        raise
      except SystemExit as e:
        failed.append(name)
        if not quiet:
          print("FAIL  %s (called sys.exit(%r); a check must raise, not exit)" % (name, e.code))
      except Exception:
        failed.append(name)
        if not quiet:
          print("FAIL  %s" % name)
          traceback.print_exc()
      else:
        spent = len(counter.calls) - before
        if not quiet:
          print("ok    %-40s %s" % (name, "%d gk" % spent if spent else ""))
  return failed, counter.calls, list(refused), counter.unregistered


def selftest_runner():
  """A fake check that calls sys.exit(0) must be reported as failed."""
  import tempfile
  failures = []
  with tempfile.TemporaryDirectory() as tmp:
    with open(os.path.join(tmp, "check_exit.py"), "w") as f:
      f.write("import sys\ndef run():\n  sys.exit(0)\n")
    with open(os.path.join(tmp, "check_pass.py"), "w") as f:
      f.write("def run():\n  pass\n")
    names = discover(where=tmp)
    failed, calls, refused, unreg = run_checks(names, tmp, quiet=True)
  if failed != ["check_exit.py"]:
    failures.append("expected check_exit.py to fail and check_pass.py to pass, got failed=%r" % failed)
  # one process launch whose argv[0] is named gk is counted once, as unregistered
  counter = GkCounter()
  with counter.watching():
    subprocess.run(["gk"], executable="/usr/bin/true", check=True)
  if len(counter.calls) != 1:
    failures.append("one launch counted %d times" % len(counter.calls))
  if len(counter.unregistered) != 1:
    failures.append("an unregistered gk launch was not listed")
  for line in failures:
    print("  FAIL  " + line)
  if failures:
    return 1
  print("  ok    a check calling sys.exit is reported as failed; the suite report still prints")
  print("  ok    one gk launch counts once; an unregistered path is listed")
  return 0


def main(argv=None):
  ap = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
  ap.add_argument("-k", dest="pattern", default=None,
                  help="run only checks whose file name contains this")
  ap.add_argument("--selftest", action="store_true",
                  help="verify the provider guard refuses a deliberate request and"
                       " the runner reports a check that exits")
  args = ap.parse_args(argv)

  if args.selftest:
    print("provider guard selftest")
    rc = selftest()
    print("runner selftest")
    return rc or selftest_runner()

  names = discover(args.pattern)
  if not names:
    print("no checks found in %s (WP01 reserved the directory; WP02 fills it)"
          % os.path.relpath(HERE, ROOT))
    return 0

  failed, calls, refused, unregistered = run_checks(names)
  print("\n%d checks, %d failed, %d gk calls, %d refused provider requests"
        % (len(names), len(failed), len(calls), len(refused)))
  if unregistered:
    print("gk launched from an unregistered path: %s" % ", ".join(str(c) for c in unregistered))
  if refused:
    print("a check attempted a provider request: %s" % ", ".join(refused))
    return 1
  return 1 if failed else 0


if __name__ == "__main__":
  sys.exit(main())
