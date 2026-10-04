"""SHA-256 digests and the canonical JSON that the action route's hashes read.

  sha256_bytes(data), sha256_text(text), sha256_file(path)   hex digests
  canonical(obj)   the one JSON serialization of a hashed or stored artifact: sorted keys, no spaces, UTF-8 kept
  digest(obj)      sha256_text(canonical(obj))

No module of the route is imported here, so every route module can use it.
"""

import hashlib
import json


def sha256_bytes(data):
  return hashlib.sha256(data).hexdigest()


def sha256_text(text):
  """The digest of a text's UTF-8 bytes."""
  return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
  """The digest of a file's bytes, read in blocks."""
  h = hashlib.sha256()
  with open(path, "rb") as f:
    for block in iter(lambda: f.read(1 << 20), b""):
      h.update(block)
  return h.hexdigest()


def canonical(obj):
  """The one serialization every hash and every stored artifact uses."""
  return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(obj):
  return sha256_text(canonical(obj))
