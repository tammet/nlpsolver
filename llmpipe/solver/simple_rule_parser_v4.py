"""Rule parsing v4: grounding that respects sign and provenance (WP3).

The grammar, the validator, the nested-term rule, the redundancy hand-off and
the canonical form are v3's and are imported unchanged.  One thing is different.

v3 built its grounding evidence from displayed atoms WITHOUT their signs and
matched every body literal against all of them.  A positive premise could
therefore be "grounded" on an occurrence that is negative in the theory, or on
the question the rule is supposed to help prove, and the resulting
specialization had no supporting occurrence at all.

Here a ground atom may support a specialization only when

  1. its sign equals the body literal's sign;
  2. it matches structurally under the ordinary unifier — predicate, argument
     order, constants and nested structure;
  3. the occurrence it came from is a SOURCE clause: a fact of the passage or
     the conclusion of one of its rules;
  4. it is not supported only by the question, a population witness, a generic
     frame axiom or another generated clause.

Every grounding candidate keeps the sign and the provenance that admitted it.
"""

import json

import simple_rule_parser as SP
import simple_rule_parser_v3 as P3
import unifier_abstraction as UA
import unifier_candidates_v4 as CV4

VERSION = "simple_rule_parser_v4/1.0"

MAX_BODY_LITERALS = P3.MAX_BODY_LITERALS
MAX_RULES_PER_CALL = P3.MAX_RULES_PER_CALL
MAX_GROUND_SPECIALIZATIONS = P3.MAX_GROUND_SPECIALIZATIONS

LLM_GENERAL = P3.LLM_GENERAL
GROUND_SPECIALIZATION = P3.GROUND_SPECIALIZATION
WARN_GENERALIZES = P3.WARN_GENERALIZES

alpha_equivalent = P3.alpha_equivalent
validate = P3.validate
role_fit = P3.role_fit


def vocabulary(candidates):
    """v3's vocabulary plus the SIGNED, source-linked grounding evidence."""
    vocab = P3.vocabulary(candidates)
    grounding = []
    for row in candidates:
        atom = row["surface_atom"]
        if CV4.free_variables(atom):
            continue
        if UA.SOURCE not in (row.get("same_sign_source_kinds") or []):
            continue
        grounding.append({"id": row.get("id"), "sign": row["sign"],
                          "atom": atom,
                          "source_kinds": row.get("same_sign_source_kinds"),
                          "printed": row["printed"]})
    vocab["grounding_atoms"] = grounding
    vocab["grounding_policy"] = (
        "a ground atom may support a specialization only when its SIGN equals "
        "the body literal's and one of its same-sign occurrences is in a "
        "source clause; question-only, population, generic-axiom and generated "
        "occurrences are not evidence")
    return vocab


def ground_specializations(rule, vocab, cap=MAX_GROUND_SPECIALIZATIONS):
    """Up to `cap` grounded variants, from signed source-linked matches only."""
    evidence = vocab.get("grounding_atoms") or []
    if not evidence:
        return []
    results, budget = [], [400]

    def walk(i, subst, used):
        if len(results) >= cap or budget[0] <= 0:
            return
        if i >= len(rule["body"]):
            if subst:
                results.append((dict(subst), list(used)))
            return
        lit = rule["body"][i]
        for g in evidence:
            budget[0] -= 1
            if budget[0] <= 0:
                return
            if g["sign"] != lit["sign"]:
                continue
            got = P3._match_atom(lit["atom"], g["atom"], subst)
            if got is not None:
                walk(i + 1, got, used + [g["id"]])
    walk(0, {}, [])
    out, seen = [], set()
    for subst, used in results:
        body = [{"sign": l["sign"], "atom": P3._apply(l["atom"], subst)}
                for l in rule["body"]]
        head = {"sign": rule["head"]["sign"],
                "atom": P3._apply(rule["head"]["atom"], subst)}
        variant = {"body": body, "head": head}
        key = SP.canonical(variant)
        if key == SP.canonical(rule) or key in seen:
            continue
        seen.add(key)
        variant["canonical"] = key
        variant["printed"] = SP._safe_printed(variant)
        variant["substitution"] = dict(subst)
        variant["grounded_on"] = used
        out.append(variant)
    return out[:cap]


def rule_candidates(rule, vocab):
    """-> (matched candidate ids per literal, unmatched atoms, total cost).

    Among candidates that only unify, the most specific one wins — fewest
    variables, then id order — instead of whichever happened to be first, and
    every equally good match is recorded.
    """
    matched, unmatched, total = [], [], 0
    for lit in rule["body"] + [rule["head"]]:
        want = lit["atom"]
        exact = [row for row in vocab["atoms"]
                 if row["sign"] == lit["sign"]
                 and alpha_equivalent(row["atom"], want)]
        loose = []
        if not exact:
            for row in vocab["atoms"]:
                if row["sign"] != lit["sign"]:
                    continue
                if UA.unify_unsigned_atoms(
                        P3._clause_shape(row["atom"]),
                        P3._clause_shape(want))["unifiable"]:
                    loose.append(row)
            loose.sort(key=lambda r: (len(CV4.free_variables(r["atom"])),
                                      str(r.get("id"))))
        best = (exact or loose or [None])[0]
        if best is None:
            unmatched.append(SP._safe_printed({"body": [lit], "head": lit}))
            continue
        matched.append({"literal": SP.printed({"body": [lit], "head": lit}
                                              ).split(" -> ")[0],
                        "candidate": best["id"], "role": best["role"],
                        "priority_cost": best["priority_cost"],
                        "match_kind": "alpha_exact" if exact else "unifier",
                        "equally_good": [r["id"] for r in (exact or loose)][:6]})
        total += best["priority_cost"]
    return matched, unmatched, total


def parse_response(text, vocab, source_rules=(), max_rules=MAX_RULES_PER_CALL,
                   start_index=1, existing=()):
    """The v3 parse, with v4 grounding and v4 candidate matching."""
    lines = (text or "").splitlines()
    rule_lines = [l for l in lines if SP.RULE_PREFIX.match(l)]
    keys = set(SP.canonical(r) for r in source_rules or [])
    seen = dict((r["canonical"], r) for r in existing)
    accepted, rejected, over_cap = [], [], []
    n = [start_index - 1]

    def fresh_id():
        n[0] += 1
        return "R%d" % n[0]

    for raw in rule_lines:
        line = raw.strip()
        try:
            parsed = SP.parse_line(line)
        except SP.RuleError as e:
            rejected.append({"line": line[:220], "reasons": [str(e)]})
            continue
        rule = SP.to_stage2_variables(parsed)
        why, warn = validate(rule, vocab, keys)
        if why:
            rejected.append({"line": line[:220], "reasons": why,
                             "printed": SP._safe_printed(rule)})
            continue
        key = SP.canonical(rule)
        if key in seen:
            seen[key].setdefault("lines", []).append(line[:220])
            continue
        if len(accepted) >= max_rules:
            over_cap.append({"line": line[:220],
                             "why": "beyond the %d-rule limit for one call"
                                    % max_rules})
            continue
        matched, unmatched, cost = rule_candidates(rule, vocab)
        entry = {"rule_id": fresh_id(), "body": rule["body"],
                 "head": rule["head"], "canonical": key,
                 "printed": SP._safe_printed(rule), "lines": [line[:220]],
                 "origin": LLM_GENERAL, "warnings": warn,
                 "candidate_matches": matched,
                 "atoms_matching_no_candidate": unmatched,
                 "rule_priority_cost": cost,
                 "role_fit": role_fit(rule, vocab),
                 "variants": []}
        seen[key] = entry
        accepted.append(entry)
        if WARN_GENERALIZES in warn:
            for variant in ground_specializations(rule, vocab):
                if variant["canonical"] in seen:
                    continue
                vmatched, vunmatched, vcost = rule_candidates(variant, vocab)
                child = {"rule_id": fresh_id(), "body": variant["body"],
                         "head": variant["head"],
                         "canonical": variant["canonical"],
                         "printed": variant["printed"],
                         "lines": [line[:220]],
                         "origin": GROUND_SPECIALIZATION,
                         "specialization_of": entry["rule_id"],
                         "substitution": variant["substitution"],
                         "grounded_on": variant["grounded_on"],
                         "warnings": [], "candidate_matches": vmatched,
                         "atoms_matching_no_candidate": vunmatched,
                         "rule_priority_cost": vcost,
                         "role_fit": role_fit(variant, vocab),
                         "variants": []}
                seen[variant["canonical"]] = child
                entry["variants"].append(child["rule_id"])
                accepted.append(child)
    return {"accepted": accepted, "rejected": rejected, "over_cap": over_cap,
            "readable_lines": len(rule_lines), "response_lines": len(lines),
            "rejection_reasons": sorted(set(r for x in rejected
                                            for r in x["reasons"]))[:20],
            "next_index": n[0] + 1}
