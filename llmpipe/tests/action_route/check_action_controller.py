"""The controller's derived fields, the package-wise bracket repair, located_at for a person at a place, and the repair
of a cached response, offline.

Every case is built from an authored gold translation, so the check says nothing about what a model writes.  No model
call, no GK launch, no read or write of cache.db.

  derived    worlds, contexts, query_contexts and the @p of a source package take the values that Stage 1 and the
             unit's text decide; each supplied value that differs is replaced and recorded with the model's value
  packages   a surplus closing bracket between two packages is dropped and recorded; text other than closing
             brackets between packages, a bracket inside a package and a truncated response are refused
  at_place   ["is rel2", "in", person, place] becomes located_at, recorded; an object in a container, a place in a
             place and a person in an artifact keep "in"
  cache      a response cut at the output limit stays out of the LLM cache when the caller asks; a response the cache
             serves is repaired; a response without a stop reason from the provider is not
"""
import copy
import json
import os
import sys
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "solver"))
sys.path.insert(0, HERE)

import action_pipeline as ap        # noqa: E402

import action_json as aj
import action_prompt as apt         # noqa: E402
import check_action_round3 as c3    # noqa: E402
import llmcall                      # noqa: E402


def attempt(e, raw, bundle, finish="STOP", cached=False):
  units, errors = ap.stage1_units(e["stage1"])
  assert not errors, errors
  return ap.stage2_attempt(raw, finish, e["text"], units, bundle, set(), cached)


def kinds(att):
  return [n["kind"] for n in att["normalizations"]]


def package(e, uid):
  return next(p for p in e["stage2"]["logic"] if p[1] == uid)


def check_derived(ex, bundle):
  out = []
  # the 0.99 of an indefinite article and the 0.98 of a normal rule give no @p
  for case, uid, p in (("new_tartu_train", "S3", 0.99), ("default_rule_applied", "S1", 0.98)):
    e = ex[case]
    s2 = copy.deepcopy(e["stage2"])
    target = next(x for x in s2["logic"] if x[1] == uid)
    target[2] = ["and", target[2], ["@p", uid, p]]
    att = attempt(e, json.dumps(s2), bundle)
    assert att["errors"] == [] and att["packages"] == e["stage2"]["logic"], (case, att["errors"])
    assert att["normalizations"] == [{"kind": "derived_probability", "unit": uid, "model": ["@p", uid, p],
                                      "derived": None}], att["normalizations"]
  out.append("an @p of 0.99 (indefinite article) and 0.98 (normally) is removed")
  # a stated probability: a missing @p, a wrong value and a wrong unit id get the stated annotation
  e = ex["uncertain_source"]
  gold = package(e, "S3")
  for label, body in (("missing", gold[2][1]), ("value", ["and", gold[2][1], ["@p", "S3", 0.6]]),
                      ("unit id", ["and", gold[2][1], ["@p", "S2", 0.8]])):
    s2 = copy.deepcopy(e["stage2"])
    next(x for x in s2["logic"] if x[1] == "S3")[2] = body
    att = attempt(e, json.dumps(s2), bundle)
    assert att["errors"] == [] and att["packages"] == e["stage2"]["logic"], (label, att["errors"])
    assert kinds(att) == ["derived_probability"] and att["normalizations"][0]["derived"] == 0.8, (label, att)
  out.append("a stated 0.8 is written when the @p is missing, has another value or another unit id")
  # a context that Stage 1 does not state, and a world list: replaced, the model's value recorded
  e = ex["temporal_permission"]
  s2 = dict(copy.deepcopy(e["stage2"]), contexts={"S2": {"tense": "present"}}, worlds=["W0", "W1"])
  att = attempt(e, json.dumps(s2), bundle)
  assert att["errors"] == [] and att["packages"] == e["stage2"]["logic"], att["errors"]
  notes = {n["field"]: n for n in att["normalizations"] if n["kind"] == "derived_field"}
  assert notes["contexts"]["model"] == {"S2": {"tense": "present"}} and notes["contexts"]["derived"] == {}
  assert notes["worlds"]["model"] == ["W0", "W1"] and (att["worlds"], att["contexts"]) == (["W0"], {})
  # an empty value that stands for the default takes the derived value without a note
  att = attempt(e, json.dumps(dict(copy.deepcopy(e["stage2"]), worlds=[], contexts=None)), bundle)
  assert att["errors"] == [] and att["normalizations"] == [], att["normalizations"]
  assert (att["worlds"], att["contexts"]) == (["W0"], {}), (att["worlds"], att["contexts"])
  out.append("a tense context of a law and a second world are replaced and recorded; an empty field gets the "
             "default without a note")
  # the gold of every authored example needs no derivation
  n = 0
  for e in ex.values():
    if not e.get("stage2") or not e.get("stage1"):
      continue
    units, errors = ap.stage1_units(e["stage1"])
    if errors or not isinstance(e["stage2"], dict):
      continue
    env = copy.deepcopy(e["stage2"])
    got, _ = ap.stage2_packages(env)
    assert not apt.derived_fields(units, env) and not apt.derived_probabilities(units, got[2]), e["id"]
    n += 1
  out.append("%d gold translations need no derivation" % n)
  return "derived: " + "; ".join(out)


def faulty(e, where):
  """The gold Stage 2 as a model writes it, one package per line, with one closing bracket too many: after the S1
  package ("between"), inside S1 before its @p ("inside"), or with a stray word after S1 ("text")."""
  s2 = e["stage2"]
  head = json.dumps({k: v for k, v in s2.items() if k != "logic"})[:-1]
  parts = [json.dumps(p) for p in s2["logic"]]
  if where == "between":
    parts[0] += "]"
  elif where == "text":
    parts[0] += ' "note"'
  elif where == "inside":
    p = s2["logic"][0]
    parts[0] = '["@id", "S1", ["and", %s], ["@p", "S1", 0.8]]]' % json.dumps(p[2])
  return head + ', "logic": [\n' + ",\n".join(parts) + "\n]}"


def check_packages(ex, bundle):
  e = ex["default_rule_applied"]
  raw = faulty(e, "between")
  att = attempt(e, raw, bundle)
  rep = att["parse"]["package_repair"]
  assert att["errors"] == [] and att["packages"] == e["stage2"]["logic"], att["errors"]
  assert rep["status"] == "applied" and rep["dropped"] == [{"after": "S1", "removed": 1}], rep
  assert att["parse"]["repair"]["status"] == "refused", att["parse"]["repair"]
  # refused: other text between packages; a bracket inside a package (the four-element package keeps the JSON message)
  for where, reason in (("text", "other text than closing brackets"), ("inside", "the error is inside it")):
    att = attempt(e, faulty(e, where), bundle)
    assert att["errors"] and att["errors"][0].startswith("the response is not JSON"), (where, att["errors"])
    assert att["parse"]["package_repair"]["status"] == "refused" and reason in att["parse"]["package_repair"]["reason"]
  # refused: a truncated response, and a provider response without a stop reason
  for finish in ("MAX_TOKENS", None):
    att = attempt(e, raw, bundle, finish)
    assert att["errors"] and att["parse"]["package_repair"] is None, (finish, att["parse"])
  # a closing bracket inside a string is no delimiter
  assert aj.repair_packages('{"logic": [["@id", "S1", ["isa", "a]]", "b 1"]]], ["@id", "S2", ["p"]]]}')[1] == \
    {"kind": "package_delimiters", "dropped": [{"after": "S1", "removed": 1}]}
  return "packages: one surplus bracket after a package is dropped and recorded, and the translation equals the gold; " \
         "other text between packages, a bracket inside a package, a truncated response and a response without a " \
         "stop reason are refused; a bracket inside a string is no delimiter"


def check_at_place(ex, bundle):
  e = ex["plan_two_travellers"]
  s2 = json.loads(json.dumps(e["stage2"]).replace('"located_at"', '"in"'))
  att = attempt(e, json.dumps(s2), bundle)
  assert att["errors"] == [] and att["packages"] == e["stage2"]["logic"], att["errors"]
  assert kinds(att) == ["person_at_place"] * 4 and [n["unit"] for n in att["normalizations"]] == ["S1", "S2", "S5", "S5"]
  # an object in a container keeps "in"
  e = ex["plan_take_then_put_in"]
  att = attempt(e, json.dumps(e["stage2"]), bundle)
  assert att["errors"] == [] and "person_at_place" not in kinds(att)
  # a place in a place, and a person in an artifact
  units = [{"unit_id": "S1", "text": "Tartu 1 is in Estonia 2.", "entities": [
             {"id": "Tartu 1", "type": "concrete", "category": "place"},
             {"id": "Estonia 2", "type": "concrete", "category": "place"}]},
           {"unit_id": "S2", "text": "Ann 3 is in the car 4.", "entities": [
             {"id": "Ann 3", "type": "concrete", "category": "person"},
             {"id": "car 4", "type": "concrete", "category": "artifact"}]}]
  env = {"logic": [["@id", "S1", ["holds", "W0", ["is rel2", "in", "Tartu 1", "Estonia 2"]]],
                   ["@id", "S2", ["holds", "W0", ["is rel2", "in", "Ann 3", "car 4"]]]]}
  before = copy.deepcopy(env)
  assert apt.at_place_cleanup(units, env) == [] and env == before
  return "at_place: gemini's plan_two_travellers with in for located_at gives the gold with four recorded rewrites; " \
         "an object in a container, a place in a place and a person in a car keep in"


def check_cache(ex, bundle):
  # llmcall: a response cut at the output limit is kept out of the cache only when the caller asks
  cut = {"model": "claude-sonnet-4-6", "content": [{"text": "[1,"}], "stop_reason": "max_tokens",
         "usage": {"input_tokens": 5, "output_tokens": 1}}
  done = dict(cut, content=[{"text": "[1]"}], stop_reason="end_turn")
  stored = []
  for response, keep, want in ((cut, False, 0), (cut, True, 1), (done, False, 1)):
    with patch.object(llmcall, "_get_llm_cached", return_value=None), \
        patch.object(llmcall, "_store_llm_cached", side_effect=lambda *a: stored.append(a)), \
        patch.object(llmcall, "_read_api_key", return_value="key"), \
        patch.object(llmcall, "_post_with_retry", return_value=response):
      before = len(stored)
      assert llmcall.call_llm("sys", "x", llm="claude", version="claude-sonnet-4-6", cache_truncated=keep)
      assert len(stored) - before == want, (response["stop_reason"], keep)
  # the controller: a response the LLM cache serves is repaired; one from the provider without a stop reason is not
  e = ex["default_rule_applied"]
  raw = faulty(e, "between")
  for source, want in (("cache", "ok"), ("api", "translation_invalid")):
    replies = iter([json.dumps(e["stage1"]), raw, raw, raw])

    def fake(sysprompt, prompt, **kwargs):
      assert kwargs.get("cache_truncated") is False
      llmcall.call_log.append({"source": source, "logical": True, "llm": "fake"})
      return next(replies)
    with patch.object(ap.llmcall, "call_llm", fake):
      tr = ap.translate(e["text"], bundle, semantic=False)
    first = [h for h in tr["history"] if h["stage"] == 2][0]
    assert tr["status"] == want and first["cached"] == (source == "cache"), (source, tr["status"], tr["errors"])
    assert (first["parse"]["package_repair"] or {}).get("status") == ("applied" if source == "cache" else None)
  return "cache: a response cut at the output limit is not stored when the caller asks (and is by default); the " \
         "controller asks; a cached response with a surplus bracket is repaired, a provider response without a stop " \
         "reason is not"


def run():
  ex = c3.examples()
  bundle = apt.assemble()
  for line in (check_derived(ex, bundle), check_packages(ex, bundle), check_at_place(ex, bundle),
               check_cache(ex, bundle)):
    print("  " + line)


if __name__ == "__main__":
  run()
