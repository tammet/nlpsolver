"""Signed demand regression over the exact clause theory gk received.

A diagnostic, not a generator.  It answers one question — *which signed logical
interfaces does this theory fail to supply?* — and answers it from structure
alone: no LLM, no reviewed rule, no accepted answer, no rule construction.

The walk is ordinary backward resolution read as a demand analysis.  To prove a
signed goal `G`, find a clause literal with the same sign and predicate whose
full argument list unifies with `G`; the signed complements of that clause's
other literals become sibling subgoals.  A goal with no matching literal
anywhere is a **demand**: a named opening the theory cannot fill.

Three distinctions the earlier work got wrong and this module keeps apart:

* **No supplier is not unreachable.**  Nothing matched at all, versus something
  matched and every branch under it failed.  Only the first is a demand.
* **A budget or a `$block` is not a decision.**  An incomplete search says
  `budget_exhausted`.  It never becomes evidence that a goal has no supplier.
* **Demand membership is not relevance.**  A demand can fill a named opening on
  a branch whose other openings are unfillable.  `viability` reports how many
  other demands share its branch; even `live` is not a claim about meaning or
  about gk succeeding.

Two record types come out, and they are not the same thing.  A **demand** is the
plan's literal definition: a leaf whose complete supplier scan matched nothing.
An **unmet interface** is any non-supplied node — demand, `supplier_unreachable`
or `budget_exhausted` — because the static axioms match a great many goals
generically (set membership, world succession, event frames) and then fan out,
so the interface a reviewed abstraction would fill is usually *matched and
undecided* rather than unmatched.  Both are reported; neither is folded into the
other; the status field always says which.
"""

import collections
import json
import os
import re

VERSION = "demand_regression/1.0"

# Frozen before the first scored extraction.  Not to be tuned after seeing
# recall: a reached cap is reported as `budget_exhausted`, which is a result.
MAX_DEPTH = 6
MAX_SUPPLIER_BRANCHES = 64
MAX_NODES = 10000
MAX_ALTERNATIVES = 512
CO_BOUND_K = 2

# ------------------------------------------------------------------ statuses

SUPPLIED = "supplied"
NO_SUPPLIER = "no_supplier"
UNREACHABLE = "supplier_unreachable"
BUDGET = "budget_exhausted"

MISSING_SUBGOAL = "missing_subgoal"
BLOCKED = "blocked_structure"
CYCLE = "cycle"
DEPTH_LIMIT = "depth_limit"
SUPPLIER_LIMIT = "supplier_limit"
NODE_LIMIT = "node_limit"
ALTERNATIVE_LIMIT = "alternative_limit"
UNSUPPORTED_LITERAL = "unsupported_literal"

# A cause is DECISIVE if the branch really is dead, and OPAQUE if the branch was
# merely not decided.  Only decisive failures may aggregate to
# `supplier_unreachable`; anything opaque leaves the goal `budget_exhausted`.
OPAQUE_CAUSES = (BLOCKED, CYCLE, DEPTH_LIMIT, SUPPLIER_LIMIT, NODE_LIMIT,
                 ALTERNATIVE_LIMIT, UNSUPPORTED_LITERAL)

LIVE = "live"
CO_DEMAND = "co_demand"
DEAD_BRANCH = "dead_branch"
OPAQUE_BRANCH = "opaque_branch"


class RegressionError(Exception):
    pass


# ------------------------------------------------------------------ terms

def is_var(t):
    return isinstance(t, str) and t.startswith("?:")


def is_compound(t):
    return isinstance(t, list)


def walk(t, sub):
    seen = 0
    while is_var(t) and t in sub:
        t = sub[t]
        seen += 1
        if seen > 10000:
            raise RegressionError("substitution cycle")
    return t


def occurs(v, t, sub):
    t = walk(t, sub)
    if t == v:
        return True
    if is_compound(t):
        return any(occurs(v, x, sub) for x in t)
    return False


def unify(a, b, sub):
    """-> extended substitution, or None.  Occurs check on; nothing wildcards.

    `$ctxt` and every other compound term unifies structurally, like any other
    term.  Wildcarding contexts would hide real tense/world breaks and let a
    later bridge change context silently.
    """
    a, b = walk(a, sub), walk(b, sub)
    if a == b:
        return sub
    if is_var(a):
        if occurs(a, b, sub):
            return None
        out = dict(sub)
        out[a] = b
        return out
    if is_var(b):
        if occurs(b, a, sub):
            return None
        out = dict(sub)
        out[b] = a
        return out
    if is_compound(a) and is_compound(b):
        if len(a) != len(b):
            return None
        for x, y in zip(a, b):
            sub = unify(x, y, sub)
            if sub is None:
                return None
        return sub
    return None


def apply_sub(t, sub):
    t = walk(t, sub)
    if is_compound(t):
        return [apply_sub(x, sub) for x in t]
    return t


# ------------------------------------------------------------------ literals

def predicate(lit):
    return lit[0]


def sign_of(lit):
    return "-" if isinstance(lit[0], str) and lit[0].startswith("-") else "+"


def bare(lit):
    p = lit[0]
    return p[1:] if isinstance(p, str) and p.startswith("-") else p


def args_of(lit):
    return list(lit[1:])


def complement(lit):
    p = lit[0]
    flipped = p[1:] if p.startswith("-") else "-" + p
    return [flipped] + list(lit[1:])


def signature(lit):
    return (sign_of(lit), bare(lit), len(lit) - 1)


def show(lit, sub=None):
    lit = [lit[0]] + [apply_sub(a, sub or {}) for a in lit[1:]]
    def t(x):
        return x if isinstance(x, str) else json.dumps(x, sort_keys=True)
    return "%s(%s)" % (lit[0], ", ".join(t(a) for a in lit[1:]))


def canonical(lit, sub):
    """Alpha-canonical printed form of a bound literal, for cycle and memo keys."""
    names = {}

    def go(t):
        t = walk(t, sub)
        if is_var(t):
            names.setdefault(t, "_v%d" % len(names))
            return names[t]
        if is_compound(t):
            return [go(x) for x in t]
        return t
    return json.dumps([lit[0]] + [go(a) for a in lit[1:]], sort_keys=True)


# ------------------------------------------------------------------ policy
#
# Frozen before the scored run.  An unclassified top-level control predicate is
# `unsupported_literal`, never an approximation.

ORDINARY = "ordinary"
CONTROL_BLOCK = "control_block"
UNSUPPORTED = "unsupported"

CONTROL_PREDICATES = {"$block": CONTROL_BLOCK}

# `$defq*` are question-definition predicates and regress like any other atom.
DEFQ = re.compile(r"^\$defq\d*$")


def classify_literal(lit):
    p = bare(lit)
    if not isinstance(p, str):
        return UNSUPPORTED
    if p in CONTROL_PREDICATES:
        return CONTROL_PREDICATES[p]
    if DEFQ.match(p):
        return ORDINARY
    if p.startswith("$"):
        # a top-level `$` predicate nobody has classified: refuse to guess
        return UNSUPPORTED
    return ORDINARY


# ------------------------------------------------------------------ theory

def literals_of(logic):
    """A clause payload is one literal or a list of them."""
    if not isinstance(logic, list) or not logic:
        return None
    return [logic] if isinstance(logic[0], str) else list(logic)


def strip_js_comments(text):
    """Remove // and /* */ outside string literals.  No JS is executed."""
    out, i, n = [], 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == '"':
                    break
                j += 1
            out.append(text[i:j + 1])
            i = j + 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def load_static_axioms(path):
    """-> (clauses, note).  Tolerant of comments and trailing commas."""
    with open(path) as f:
        raw = f.read()
    text = strip_js_comments(raw)
    text = re.sub(r",(\s*[\]}])", r"\1", text)
    try:
        data = json.loads(text)
    except ValueError as e:
        return None, "unparseable: %s" % e
    if not isinstance(data, list):
        return None, "not a clause array"
    return data, None


AXIOM_RE = re.compile(r"(\S+\.js)")


def axiom_files(gk_command, default_path):
    """The static axiom files the stored command selected."""
    if not gk_command:
        return [], "the stored gk_command is empty"
    hits = AXIOM_RE.findall(gk_command)
    if hits:
        return hits, None
    return [default_path], "no .js in the command; resolved the module default"


class Theory(object):
    """The exact clause universe, plus provenance for every clause."""

    def __init__(self):
        self.clauses = []          # [{literals, name, origin, sourcetype, idx}]
        self.by_sig = collections.defaultdict(list)   # signature -> [(ci, li)]
        self.notes = []

    def add(self, logic, name, origin, sourcetype=None, extra=None):
        lits = literals_of(logic)
        if lits is None:
            self.notes.append("unreadable clause payload in %s" % origin)
            return
        ci = len(self.clauses)
        self.clauses.append({"literals": lits, "name": name, "origin": origin,
                             "sourcetype": sourcetype, "index": ci,
                             "extra": extra or {}})
        for li, lit in enumerate(lits):
            if not isinstance(lit, list) or not lit:
                continue
            self.by_sig[signature(lit)].append((ci, li))

    def matching(self, goal):
        return self.by_sig.get(signature(goal), [])


def build_theory(stored, axioms_default, extra_clauses=()):
    """Final clauses + the static axioms the stored command selected."""
    th = Theory()
    question = None
    for c in stored.get("final_clauses") or []:
        if not isinstance(c, dict):
            continue
        if "@question" in c:
            question = c
            continue
        st = c.get("@sourcetype")
        origin = "final:%s" % (c.get("@name") or "?")
        th.add(c.get("@logic"), c.get("@name"), origin, st,
               {"confidence": c.get("@confidence")})
    files, note = axiom_files(stored.get("gk_command"), axioms_default)
    if note:
        th.notes.append(note)
    axiom_status = {}
    for path in files:
        if not os.path.exists(path):
            axiom_status[path] = "missing"
            th.notes.append("static axiom file not found: %s" % path)
            continue
        data, why = load_static_axioms(path)
        if data is None:
            axiom_status[path] = "opaque: %s" % why
            th.notes.append("static_axioms_opaque %s (%s)" % (path, why))
            continue
        axiom_status[path] = "loaded:%d" % len(data)
        for i, cl in enumerate(data):
            th.add(cl, "static_axiom", "static_axiom:%s:%d" % (path, i),
                   "static_axiom")
    for name, logic in extra_clauses:
        th.add(logic, name, "inserted:%s" % name, "inserted")
    return th, question, axiom_status


# ------------------------------------------------------------------ regression

class Budget(object):
    def __init__(self):
        self.nodes = 0
        self.hit = set()

    def spend(self):
        self.nodes += 1
        if self.nodes > MAX_NODES:
            self.hit.add(NODE_LIMIT)
            return False
        return True


class Walker(object):
    """One question target's regression over one theory."""

    def __init__(self, theory, target):
        self.th = theory
        self.target = target
        self.budget = Budget()
        self.demands = []
        self.interfaces = []
        self._memo = {}
        self.memo_hits = 0

    # -- the walk ---------------------------------------------------------

    def run(self, goal):
        return self.regress(goal, {}, 0, (), ())

    def regress(self, goal, sub, depth, path, chain):
        if not self.budget.spend():
            return self._node(goal, sub, depth, BUDGET, [], {NODE_LIMIT}, chain)
        kind = classify_literal(goal)
        if kind == CONTROL_BLOCK:
            return self._node(goal, sub, depth, BUDGET, [], {BLOCKED}, chain)
        if kind == UNSUPPORTED:
            return self._node(goal, sub, depth, BUDGET, [], {UNSUPPORTED_LITERAL},
                              chain)
        key = canonical(goal, sub)
        if key in path:
            return self._node(goal, sub, depth, BUDGET, [], {CYCLE}, chain)
        memo = self._memo.get(key)
        if memo is not None:
            self.memo_hits += 1
            n = self._node(goal, sub, depth, memo, [], set(), chain,
                           local=set())
            n["memo_hit"] = True
            if memo == NO_SUPPLIER:
                self._emit_demand(n, goal, sub, chain)
                self.interfaces[-1]["demand_id"] = n["demand_id"]
            return n
        if depth >= MAX_DEPTH:
            return self._node(goal, sub, depth, BUDGET, [], {DEPTH_LIMIT}, chain)

        matches = self.th.matching(goal)
        branches, causes, truncated = [], set(), False
        considered = 0
        for ci, li in matches:
            if considered >= MAX_SUPPLIER_BRANCHES:
                truncated = True
                break
            clause = self.th.clauses[ci]
            fresh = _freshen(clause["literals"], ci, self.budget.nodes)
            s2 = _unify_literals(goal, fresh[li], sub)
            if s2 is None:
                continue
            considered += 1
            others = [l for k, l in enumerate(fresh) if k != li]
            br = {"clause": clause["name"], "origin": clause["origin"],
                  "sourcetype": clause["sourcetype"],
                  "literal_index": li, "children": [], "causes": set(),
                  "status": SUPPLIED}
            if not others:
                branches.append(br)
                continue
            ok = True
            for other in others:
                sub_goal = complement(other)
                child = self.regress(sub_goal, s2, depth + 1,
                                     path + (key,),
                                     chain + ((clause["name"], clause["origin"]),))
                br["children"].append(child)
                if child["status"] != SUPPLIED:
                    ok = False
                    br["causes"] |= child["causes"]
                    if child["status"] in (NO_SUPPLIER, UNREACHABLE):
                        br["causes"].add(MISSING_SUBGOAL)
            br["status"] = SUPPLIED if ok else BUDGET
            if ok:
                branches.append(br)
                break                       # one complete branch settles it
            br["status"] = "failed"
            branches.append(br)
        if truncated:
            causes.add(SUPPLIER_LIMIT)

        if any(b["status"] == SUPPLIED for b in branches):
            self._remember(key, goal, sub, SUPPLIED)
            return self._node(goal, sub, depth, SUPPLIED, branches, causes,
                              chain, local=set())
        if considered == 0 and not truncated:
            self._remember(key, goal, sub, NO_SUPPLIER)
            n = self._node(goal, sub, depth, NO_SUPPLIER, branches, causes,
                           chain, local=set())
            self._emit_demand(n, goal, sub, chain)
            self.interfaces[-1]["demand_id"] = n["demand_id"]
            return n
        all_causes = set(causes)
        for b in branches:
            all_causes |= b["causes"]
        local = {SUPPLIER_LIMIT} if truncated else set()
        if truncated or (all_causes & set(OPAQUE_CAUSES)):
            return self._node(goal, sub, depth, BUDGET, branches, all_causes,
                              chain, local=local)
        return self._node(goal, sub, depth, UNREACHABLE, branches, all_causes,
                          chain, local=local)

    def _remember(self, key, goal, sub, status):
        """Memoize only what cannot change with the caller's bindings.

        `no_supplier` is decided by the supplier scan of the bound goal alone,
        so it is safe for any goal.  Anything else is remembered only when the
        bound goal is ground: a memoized `supplied` for a goal with variables
        would drop the bindings that made it supplied, and a sibling could then
        succeed on bindings that never existed.
        """
        if status == NO_SUPPLIER:
            self._memo[key] = status
            return
        if status == SUPPLIED and _ground(goal, sub):
            self._memo[key] = status

    # -- records ----------------------------------------------------------

    def _interface(self, node, goal, sub, chain):
        """Every non-supplied node: the objective is unmet INTERFACES.

        A demand (nothing matched) is one kind of unmet interface.  The others
        matter just as much: a generic axiom matching a goal and then failing,
        or a budget stopping the decision, both leave the interface unfilled.
        """
        self.interfaces.append({
            "interface_id": "I%d" % (len(self.interfaces) + 1),
            "kind": node["status"],
            "question_target": self.target,
            "signed_literal": show(goal, sub),
            "signed_shape": list(signature(goal)),
            "predicate": bare(goal), "sign": sign_of(goal),
            "depth": node["depth"],
            "causes": sorted(node["causes"]),
            "demanding_chain": [c[0] for c in chain],
            "demanding_origins": [c[1] for c in chain],
            "axiom_internal": bool(chain) and all(
                o.startswith("static_axiom") for _n, o in chain),
            "instantiated_literal": [goal[0]] + [apply_sub(a, sub)
                                                 for a in goal[1:]],
            "canonical": canonical(goal, sub),
            "demand_id": node.get("demand_id")})
        node["interface_id"] = self.interfaces[-1]["interface_id"]

    def _node(self, goal, sub, depth, status, branches, causes, chain,
              local=None):
        n = {"goal": show(goal), "bound_goal": show(goal, sub),
             "signature": list(signature(goal)),
             "status": status, "depth": depth,
             # `causes` is aggregated for reporting; `local_causes` is what
             # actually happened AT this node.  Only the local ones may make a
             # branch opaque — aggregating upward and then re-applying downward
             # marked every clean alternative opaque.
             "causes": set(causes),
             "local_causes": set(causes if local is None else local),
             "branches": branches,
             "question_target": self.target,
             "demanding_chain": [c[0] for c in chain],
             # the bound literal itself, so a caller can match a node against a
             # rule head structurally instead of parsing the printed form
             "literal": [goal[0]] + [apply_sub(a, sub) for a in goal[1:]]}
        if status != SUPPLIED:
            self._interface(n, goal, sub, chain)
        return n

    def _emit_demand(self, node, goal, sub, chain):
        d = {"demand_id": "D%d" % (len(self.demands) + 1),
             "question_target": self.target,
             "signed_literal": show(goal, sub),
             "signed_shape": list(signature(goal)),
             "predicate": bare(goal), "sign": sign_of(goal),
             "binding_environment": {k: apply_sub(v, sub)
                                     for k, v in sub.items()
                                     if isinstance(apply_sub(v, sub),
                                                   (str, list))},
             "demanding_chain": [c[0] for c in chain],
             "demanding_origins": [c[1] for c in chain],
             "depth": node["depth"],
             "instantiated_literal": [goal[0]] + [apply_sub(a, sub)
                                                  for a in goal[1:]],
             "canonical": canonical(goal, sub)}
        node["demand_id"] = d["demand_id"]
        self.demands.append(d)
        return d


def _ground(lit, sub):
    def go(t):
        t = walk(t, sub)
        if is_var(t):
            return False
        if is_compound(t):
            return all(go(x) for x in t)
        return True
    return all(go(a) for a in args_of(lit))


def _freshen(literals, ci, tick):
    """Standardize a clause apart on every application."""
    tag = "#%d_%d" % (ci, tick)
    def go(t):
        if is_var(t):
            return t + tag
        if is_compound(t):
            return [go(x) for x in t]
        return t
    return [[l[0]] + [go(a) for a in l[1:]] for l in literals]


def _unify_literals(goal, lit, sub):
    if sign_of(goal) != sign_of(lit) or bare(goal) != bare(lit):
        return None
    ga, la = args_of(goal), args_of(lit)
    if len(ga) != len(la):
        return None
    s = sub
    for x, y in zip(ga, la):
        s = unify(x, y, s)
        if s is None:
            return None
    return s


# ------------------------------------------------------------------ viability

def _leaf_id(node):
    """Every non-supplied node has an interface id; demands join to it by id.

    One id space for the alternative sets, or a set built from demand ids and a
    lookup keyed by interface ids never meet and everything reads opaque.
    """
    return node.get("interface_id")


def demand_sets(node, cap=MAX_ALTERNATIVES):
    """Alternative ways to satisfy a node, as (demand ids, opacity causes).

    A supplied node needs nothing; a demand needs itself; an AND-combination is
    the cross product; alternative suppliers are alternatives.  The smallest
    sets are kept when the cap bites, and the truncation is recorded as its own
    opacity cause so nothing silently looks cleaner than it is.
    """
    st = node["status"]
    if st == SUPPLIED:
        return [(frozenset(), frozenset())]
    if st == NO_SUPPLIER or not node["branches"]:
        # a terminal opening: nothing matched, or the search stopped here with
        # nothing explored.  A node that DID explore branches is not a leaf —
        # its children carry the real openings and expanding it is what puts
        # them in the set.  Its own opacity travels with it.
        return [(frozenset([_leaf_id(node)]),
                 frozenset(c for c in node.get("local_causes", ())
                           if c in OPAQUE_CAUSES))]
    opaque_here = frozenset(c for c in node.get("local_causes", node["causes"])
                            if c in OPAQUE_CAUSES)
    out = []
    for br in node["branches"]:
        # a branch carries no opacity of its own: its children already carry
        # theirs, and `br["causes"]` is aggregated for reporting
        combos = [(frozenset(), frozenset())]
        for child in br["children"]:
            child_sets = demand_sets(child, cap)
            nxt = []
            for ds, cs in combos:
                for ds2, cs2 in child_sets:
                    nxt.append((ds | ds2, cs | cs2))
            combos = _trim(nxt, cap)
        out.extend(combos)
    if not out:
        out = [(frozenset(), opaque_here or frozenset([BLOCKED]))]
    else:
        out = [(d, c | opaque_here) for d, c in out]
    trimmed = _trim(out, cap)
    if len(out) > len(trimmed):
        trimmed = [(d, c | frozenset([ALTERNATIVE_LIMIT])) for d, c in trimmed]
    return trimmed


def _trim(sets, cap):
    seen, uniq = set(), []
    for d, c in sorted(sets, key=lambda x: (len(x[0]), sorted(x[0]))):
        k = (d, c)
        if k in seen:
            continue
        seen.add(k)
        uniq.append((d, c))
        if len(uniq) >= cap:
            break
    return uniq


def viability(demands, sets, key="demand_id"):
    """Attach residual_k and a stratum to every demand.

    A demand's residual on one alternative is the other demands that alternative
    still needs.  Clean (non-opaque) alternatives decide the stratum; if a
    demand appears only on opaque ones it is `opaque_branch`, and both numbers
    are reported.
    """
    by_id = {d[key]: d for d in demands}
    best, siblings = {}, collections.defaultdict(set)
    for ds, causes in sets:
        clean = not causes
        k = len(ds) - 1
        cand_head = (0 if clean else 1, k, sorted(causes))
        for did in ds:
            if did not in by_id:
                continue
            cur = best.get(did)
            if cur is None or cand_head < cur:
                best[did] = cand_head
            if len(siblings[did]) < 12:
                siblings[did] |= (ds - {did})
    for did, d in by_id.items():
        got = best.get(did)
        if got is None:
            d["residual_k"] = None
            d["viability"] = OPAQUE_BRANCH
            d["branch_failure_causes"] = [ALTERNATIVE_LIMIT]
            continue
        opaque, k, causes = got
        d["residual_k"] = k
        d["branch_failure_causes"] = causes
        if opaque:
            d["viability"] = OPAQUE_BRANCH
        elif k == 0:
            d["viability"] = LIVE
        elif k <= CO_BOUND_K:
            d["viability"] = CO_DEMAND
        else:
            d["viability"] = DEAD_BRANCH
        d["sibling_residual_demand_ids"] = sorted(siblings.get(did, ()))[:12]
    return demands


# ------------------------------------------------------------------ grouping

def group_records(records, key_fields, cap_examples=3):
    """Collapse alpha-identical occurrences, keeping the count and exemplars.

    Occurrences stay distinct in the analysis — each was regressed on its own
    path — but writing several hundred near-identical records per case tells a
    reader nothing.  The group keeps how many there were, the shallowest one,
    and up to three demanding chains.
    """
    groups = collections.OrderedDict()
    for r in records:
        k = tuple(r.get(f) for f in key_fields)
        g = groups.get(k)
        if g is None:
            g = dict(r)
            g["occurrences"] = 0
            g["example_chains"] = []
            g["min_depth"] = r["depth"]
            g["causes"] = set(r.get("causes") or [])
            g["viabilities"] = set()
            groups[k] = g
        g["occurrences"] += 1
        g["min_depth"] = min(g["min_depth"], r["depth"])
        g["causes"] |= set(r.get("causes") or [])
        g["viabilities"].add(r.get("viability"))
        if len(g["example_chains"]) < cap_examples:
            g["example_chains"].append(r.get("demanding_chain"))
    out = []
    for g in groups.values():
        g["causes"] = sorted(x for x in g["causes"] if x)
        g["viability"] = _best_viability(g.pop("viabilities"))
        g["depth"] = g["min_depth"]
        g.pop("demanding_chain", None)
        out.append(g)
    out.sort(key=lambda r: (r["min_depth"], -r["occurrences"]))
    return out


_VIA_ORDER = (LIVE, CO_DEMAND, DEAD_BRANCH, OPAQUE_BRANCH)


def _best_viability(vs):
    for v in _VIA_ORDER:
        if v in vs:
            return v
    return OPAQUE_BRANCH


# ------------------------------------------------------------------ per case

def question_literal(question_clause):
    """-> (literal, note).  v1 accepts one signed literal."""
    if question_clause is None:
        return None, "no @question clause in the stored final clauses"
    q = question_clause.get("@question")
    if not isinstance(q, list) or not q:
        return None, "unreadable @question payload"
    if isinstance(q[0], str):
        return list(q), None
    if len(q) == 1 and isinstance(q[0], list):
        return list(q[0]), None
    return None, "unsupported_query_shape: a compound question of %d literals" \
        % len(q)


def analyse(stored, axioms_default, extra_clauses=()):
    """The whole diagnostic for one case, both question targets."""
    th, qclause, axiom_status = build_theory(stored, axioms_default,
                                             extra_clauses)
    lit, note = question_literal(qclause)
    out = {"version": VERSION,
           "bounds": {"depth": MAX_DEPTH, "supplier_branches":
                      MAX_SUPPLIER_BRANCHES, "nodes": MAX_NODES,
                      "alternatives": MAX_ALTERNATIVES, "co_bound": CO_BOUND_K},
           "clauses": len(th.clauses), "axiom_status": axiom_status,
           "theory_notes": th.notes, "question": None, "targets": {},
           "demands": [], "interfaces": [], "unsupported_query_shape": False}
    if lit is None:
        out["unsupported_query_shape"] = True
        out["why"] = note
        return out, th
    out["question"] = show(lit)
    for target, goal in (("positive", lit), ("negative", complement(lit))):
        w = Walker(th, target)
        root = w.run(goal)
        sets = demand_sets(root)
        viability(w.interfaces, sets, key="interface_id")
        by_demand = {i["demand_id"]: i for i in w.interfaces
                     if i.get("demand_id")}
        for d in w.demands:
            i = by_demand.get(d["demand_id"])
            if i is None:
                d["viability"] = OPAQUE_BRANCH
                d["residual_k"] = None
                d["branch_failure_causes"] = []
                continue
            for f in ("viability", "residual_k", "branch_failure_causes",
                      "sibling_residual_demand_ids"):
                d[f] = i.get(f)
        out["targets"][target] = {
            "goal": show(goal), "status": root["status"],
            "causes": sorted(root["causes"]),
            "nodes_visited": w.budget.nodes, "memo_hits": w.memo_hits,
            "budget_caps_hit": sorted(w.budget.hit),
            "alternatives_considered": len(sets),
            "demand_occurrences": len(w.demands),
            "unmet_interface_occurrences": len(w.interfaces)}
        out["demands"].extend(group_records(
            w.demands, ("question_target", "canonical")))
        out["interfaces"].extend(group_records(
            w.interfaces, ("question_target", "kind", "canonical")))
    return out, th


# ------------------------------------------------------------------ producers

def producer_inventory(theory):
    """Source-linked literals, and whether the theory can actually supply them.

    Only input-sentence clauses contribute producers.  Generated, population and
    axiom clauses stay in the walk as suppliers but are never offered as lexical
    producers — they are the machinery, not the problem's content.

    Reachability is the same regression, run with the producer literal as its
    own goal: a literal merely present in a rule is not a producer until its own
    premises are supplied.
    """
    seen, producers = set(), []
    for c in theory.clauses:
        if not (c["origin"] or "").startswith("final:"):
            continue
        if c["sourcetype"] in ("question", "populate", "static_axiom",
                               "inserted"):
            continue
        for lit in c["literals"]:
            if not isinstance(lit, list) or not lit:
                continue
            if classify_literal(lit) != ORDINARY:
                continue
            key = canonical(lit, {})
            if key in seen:
                continue
            seen.add(key)
            producers.append({"literal": show(lit), "clause": c["name"],
                              "origin": c["origin"],
                              "signature": list(signature(lit)),
                              "_lit": lit})
    for p in producers:
        w = Walker(theory, "producer")
        node = w.run(p.pop("_lit"))
        p["status"] = node["status"]
        p["reachable"] = node["status"] == SUPPLIED
        p["causes"] = sorted(node["causes"])
        p["supplied_by"] = sorted(set(b["origin"] for b in node["branches"]
                                      if b["status"] == SUPPLIED))[:4]
        p["supplied_by_input_only"] = bool(p["supplied_by"]) and all(
            o.startswith("final:") for o in p["supplied_by"])
    return producers
