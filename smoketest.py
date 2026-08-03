#!/usr/bin/env python3
"""Smoke-test the nlpsolver install without spending any LLM credits.

Checks, in order:
  1. Python version (>= 3.8).
  2. llmpipe imports (so missing stdlib modules / syntax errors surface).
  3. The bundled gk reasoner binary runs.
  4. gk produces a proof on the bundled birdspenguins.js example.
  5. At least one provider key file is present (warning, not a failure).

Exits 0 on success, non-zero on the first hard failure.

Run from anywhere; resolves repo paths relative to this script's location:
    python3 smoketest.py
"""

import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


def step(msg):
  print("  " + msg)


def ok(msg):
  print("  OK  " + msg)


def fail(msg):
  print("  FAIL " + msg)
  sys.exit(1)


def warn(msg):
  print("  WARN " + msg)


def check_python():
  print("[1/6] Python version")
  if sys.version_info < (3, 8):
    fail("Python 3.8+ required, got " + sys.version.split()[0])
  ok("Python " + sys.version.split()[0])


def check_imports():
  print("[2/6] llmpipe imports (no pip packages needed)")
  solver = os.path.join(REPO_ROOT, "llmpipe", "solver")
  if not os.path.isdir(solver):
    fail("llmpipe/solver/ not found at " + solver)
  sys.path.insert(0, solver)
  try:
    import solve  # noqa: F401
    import llmcall  # noqa: F401
    import prover  # noqa: F401
  except Exception as e:
    fail("could not import llmpipe modules: " + str(e))
  ok("solve, llmcall, prover import cleanly")


def check_gk_runs():
  print("[3/6] gk binary executes")
  gk = os.path.join(REPO_ROOT, "gk", "gk")
  if not os.path.isfile(gk):
    fail("gk binary not found at " + gk)
  if not os.access(gk, os.X_OK):
    fail("gk binary at " + gk + " is not executable")
  try:
    out = subprocess.run([gk], capture_output=True, timeout=5)
  except Exception as e:
    fail("could not run gk: " + str(e) +
         " (the bundled binary is Linux x86-64; build from gkc on other platforms)")
  if b"gk is a first order logic reasoner" not in out.stdout:
    fail("gk did not produce the expected help banner")
  ok("gk runs and prints the help banner")


def check_gk_proof():
  print("[4/6] gk solves the bundled birdspenguins.js example")
  gk = os.path.join(REPO_ROOT, "gk", "gk")
  ex = os.path.join(REPO_ROOT, "gk", "birdspenguins.js")
  if not os.path.isfile(ex):
    fail("missing example: " + ex)
  try:
    out = subprocess.run([gk, ex], capture_output=True, timeout=30)
  except Exception as e:
    fail("running gk on the example failed: " + str(e))
  if b'"result": "answer found"' not in out.stdout:
    fail("gk did not find the expected proof on birdspenguins.js\n"
         "  gk output was:\n  "
         + out.stdout.decode("utf-8", "replace").strip().replace("\n", "\n  "))
  ok("gk found an answer for birdspenguins.js")


def check_secrets():
  print("[5/6] llmpipe API key presence (optional)")
  secrets = os.path.join(REPO_ROOT, "secrets")
  files = ["gpt_secrets.txt", "claude_secrets.txt",
           "gemini_secrets.txt", "deepseek_secrets.txt"]
  found = [f for f in files if os.path.isfile(os.path.join(secrets, f))]
  if not found:
    warn("no API key files in " + secrets + "/")
    warn("the gk reasoner works, but solve.py needs an LLM key — see secrets/README.txt")
  else:
    ok("found key file(s): " + ", ".join(found))


def _discover_python_interpreters(udppipe):
  """Return a list of candidate python3 paths likely to host stanza.

  Order: current interpreter, $VIRTUAL_ENV, any venv-shaped directory found
  in conventional locations. A directory counts as a venv if it contains
  pyvenv.cfg (so naming — .venv / venv / my-venv / custom — doesn't matter)."""
  seen = []
  def add(py):
    # Use abspath, NOT realpath: a venv's bin/python3 is a symlink that
    # resolves to the system python, but the venv path is what activates
    # the venv's site-packages. Dedup by location, not inode.
    py = os.path.abspath(py)
    if os.path.isfile(py) and py not in seen:
      seen.append(py)
  add(sys.executable)
  venv_env = os.environ.get("VIRTUAL_ENV")
  if venv_env:
    add(os.path.join(venv_env, "bin", "python3"))
  search_roots = [REPO_ROOT, udppipe, os.path.join(REPO_ROOT, "llmpipe"),
                  os.path.expanduser("~/.virtualenvs")]
  for root in search_roots:
    if not os.path.isdir(root):
      continue
    try:
      entries = os.listdir(root)
    except OSError:
      continue
    for name in entries:
      cand = os.path.join(root, name)
      if (os.path.isfile(os.path.join(cand, "pyvenv.cfg"))
          and os.path.isfile(os.path.join(cand, "bin", "python3"))):
        add(os.path.join(cand, "bin", "python3"))
  return seen


def check_udppipe():
  print("[6/6] udppipe stanza availability (optional)")
  udppipe = os.path.join(REPO_ROOT, "udppipe")
  if not os.path.isdir(udppipe):
    warn("udppipe/ not found — skipping")
    return
  # udppipe is typically run from its own venv (per udppipe/README.md), so
  # the interpreter running this script may not be the one that has stanza.
  # Auto-discover any venv-shaped directory rather than hard-coding names.
  candidates = _discover_python_interpreters(udppipe)
  for py in candidates:
    try:
      r = subprocess.run([py, "-c", "import stanza; print(stanza.__version__)"],
                         capture_output=True, timeout=15)
    except Exception:
      continue
    if r.returncode == 0:
      version = r.stdout.decode().strip()
      where = "current interpreter" if py == os.path.abspath(sys.executable) else py
      ok("stanza " + version + " importable (" + where +
         ") — udppipe is ready (start with ./udppipe/nlpserver.py)")
      return
  warn("stanza not installed in any discovered interpreter — udppipe will not run (llmpipe does not need it).")
  warn("Checked: " + ", ".join(candidates))
  warn("To enable, follow the venv recipe in " +
       os.path.join(udppipe, "README.md") + " (Installation section).")


def main():
  print("nlpsolver smoke-test (repo at " + REPO_ROOT + ")")
  check_python()
  check_imports()
  check_gk_runs()
  check_gk_proof()
  check_secrets()
  check_udppipe()
  print()
  print("All smoke-test checks passed.")
  print("Next step: cd " + os.path.join(REPO_ROOT, "llmpipe") +
        " && python3 solver/solve.py \"YOUR QUESTION\"")


if __name__ == "__main__":
  main()
