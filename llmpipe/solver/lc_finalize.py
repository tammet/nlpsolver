# Strict/abstract clause finalizer for the -abstract* presets.
#
# Under the -abstract presets the encoding is fully strict/monotonic (matching
# FOLIO's classical FOL): defeasible rules become strict and habitual/typical
# events become real.  FOLIO is timeless, so tense/world/location carry no
# information; collapsing each clause's $ctxt to one variable lets the redundancy
# steps see and remove the hidden duplication.  Per clause, in order:
#   0a. unwrap `normally`/`-normally` wrappers       -> their inner formula
#   0b. drop `$block` blocker and `typical` literals -> no exceptions, real events
#       (a clause emptied by this drop is removed)
#   1.  every $ctxt term in a clause  -> one shared fresh ?:Cu var (per clause)
#   2.  flatten any inner ["or", ...] -> its literals at the clause top level
#   3.  tautology  -> a clause with a literal and its negation is dropped
#   4.  duplicate identical literals  -> collapsed to one copy
# Plus equality elimination (definite-description `=` facts and `-=` var=const
# guards).  @question goals keep per-atom freshening (they are not CNF clauses).
#
# Pure: takes the clause list, returns the transformed list; no module state.


def finalize_strict_clauses(result, preserve_generated_blocks=False):
  # Equality elimination: Stage 2 reifies a definite description ("the winner of
  # X was Steinhauer") as a separate entity plus a ground `=(winner 1,
  # Steinhauer 3)`.  After UNA wrapping the two `#:` constants are forced UNEQUAL
  # by axioms_std.js §7g, fighting the asserted identity, so the proof stalls.
  # Substitute one side out globally and drop the `=` fact, merging the definite
  # entity into its referent (= what one-stage does by never minting the entity).
  def _is_eq_fact(b):
    return (isinstance(b, list) and len(b) == 3 and b[0] == "="
            and isinstance(b[1], str) and isinstance(b[2], str)
            and not b[1].startswith("?:") and not b[2].startswith("?:"))
  _eqpar = {}
  def _eq_find(x):
    _eqpar.setdefault(x, x)
    while _eqpar[x] != x:
      _eqpar[x] = _eqpar[_eqpar[x]]
      x = _eqpar[x]
    return x
  for _c in result:
    if isinstance(_c, dict) and _is_eq_fact(_c.get("@logic")):
      a, b = _c["@logic"][1], _c["@logic"][2]
      ra, rb = _eq_find(a), _eq_find(b)
      if ra != rb:
        _eqpar[ra] = rb            # keep the 2nd arg (referent) as canonical
  _eqsubst = {x: _eq_find(x) for x in list(_eqpar) if _eq_find(x) != x}
  if _eqsubst:
    def _eq_apply(n):
      if isinstance(n, list):
        return [_eq_apply(x) for x in n]
      return _eqsubst.get(n, n) if isinstance(n, str) else n
    _kept = []
    for _c in result:
      if isinstance(_c, dict):
        if _is_eq_fact(_c.get("@logic")):
          continue                 # drop the =(A,B) fact
        for _k in ("@logic", "@question"):
          if _k in _c:
            _c[_k] = _eq_apply(_c[_k])
      _kept.append(_c)
    result = _kept

  _ctxt_ctr = [0]

  def _unwrap_normally(node):
    if isinstance(node, list) and node:
      if node[0] in ("normally", "-normally") and len(node) >= 2:
        return _unwrap_normally(node[1])
      return [_unwrap_normally(x) for x in node]
    return node

  def _is_meta_lit(lit, strip_block=True):
    if not (isinstance(lit, list) and lit and isinstance(lit[0], str)):
      return False
    base = lit[0][1:] if lit[0].startswith("-") else lit[0]
    return base == "typical" or (base == "$block" and strip_block)

  def _share_ctxt(node, cuvar):
    if isinstance(node, list):
      if node and node[0] == "$ctxt":
        return cuvar
      return [_share_ctxt(x, cuvar) for x in node]
    return node

  def _freshen_ctxt_per_atom(node):
    if isinstance(node, list):
      if node and node[0] == "$ctxt":
        _ctxt_ctr[0] += 1
        return "?:Cu" + str(_ctxt_ctr[0])
      return [_freshen_ctxt_per_atom(x) for x in node]
    return node

  def _flatten_ors(lits):
    out = []
    for lit in lits:
      if isinstance(lit, list) and lit and lit[0] == "or":
        out.extend(_flatten_ors(lit[1:]))
      else:
        out.append(lit)
    return out

  def _complementary(a, b):
    if not (isinstance(a, list) and a and isinstance(a[0], str)
            and isinstance(b, list) and b and isinstance(b[0], str)):
      return False
    pa, pb = a[0], b[0]
    if pa.startswith("-") == pb.startswith("-"):
      return False
    base_a = pa[1:] if pa.startswith("-") else pa
    base_b = pb[1:] if pb.startswith("-") else pb
    return base_a == base_b and a[1:] == b[1:]

  # Variable=constant guard instantiation: a `-=(V, C)` guard with V a variable
  # and C a constant ("the number 34" -> isa(number,Y) & =(Y,"34")) forces
  # equality reasoning the prover stalls on.  ADD (not replace) the instance with
  # V:=C substituted and the guard dropped, so the constant form
  # (begins_with(X,"34")) is directly available alongside the general clause.
  # Sound: the instance is the V=C universal instantiation of the original.
  def _eq_guard_bindings(lits):
    binds = {}
    used = []
    for lit in lits:
      if isinstance(lit, list) and len(lit) == 3 and lit[0] == "-=":
        a, b = lit[1], lit[2]
        va = isinstance(a, str) and a.startswith("?:")
        vb = isinstance(b, str) and b.startswith("?:")
        ca = isinstance(a, str) and not a.startswith("?:")
        cb = isinstance(b, str) and not b.startswith("?:")
        if va and cb and a not in binds:
          binds[a] = b; used.append(lit)
        elif vb and ca and b not in binds:
          binds[b] = a; used.append(lit)
    return binds, used
  _eq_instances = []
  for _c in result:
    if not isinstance(_c, dict):
      continue
    _body = _c.get("@logic")
    if not (isinstance(_body, list) and _body and isinstance(_body[0], list)):
      continue
    _binds, _used = _eq_guard_bindings(_body)
    if not _binds:
      continue
    def _eq_sub(n, _b=_binds):
      if isinstance(n, list):
        return [_eq_sub(x, _b) for x in n]
      return _b.get(n, n) if isinstance(n, str) else n
    _inst = [_eq_sub(l) for l in _body if l not in _used]
    if _inst:
      _eq_instances.append({"@name": _c.get("@name", "sent"), "@logic": _inst})
  result = result + _eq_instances

  new_result = []
  for _c in result:
    if not isinstance(_c, dict):
      new_result.append(_c)
      continue
    if isinstance(_c.get("@question"), list):
      _c["@question"] = _freshen_ctxt_per_atom(_c["@question"])
    body = _c.get("@logic")
    _strip_block = not (preserve_generated_blocks
                        and str(_c.get("@name", "")).startswith("frm_"))
    if isinstance(body, list) and body:
      body = _unwrap_normally(body)            # 0a: normally -> strict
      if not (isinstance(body, list) and body):
        new_result.append(_c)
        continue
      _ctxt_ctr[0] += 1
      body = _share_ctxt(body, "?:Cu" + str(_ctxt_ctr[0]))
      # Treat a list of literals (or a single top-level "or") as a clause.
      if isinstance(body[0], list) or body[0] == "or":
        lits = _flatten_ors(body if isinstance(body[0], list) else [body])
        # 0b: drop $block/typical meta literals.  Track whether a POSITIVE
        # `typical` literal was present: a defeasible-generic rule like "Dogs
        # bark" folds (davidson) to a clause [-isa(dog,X), typical(handle),
        # $block] whose only positive content is the typicality marker.
        # Stripping it leaves the headless all-negative [-isa(dog,X)] = the
        # unsound "nothing is a dog" unit (the bark event itself is asserted by
        # its own clause).  Drop such a headless clause instead of emitting the
        # spurious antecedent-negation.
        # Key on `typical`, NOT on $block: $block is the defeasibility anchor of
        # EVERY defeasible rule, so a sound rule whose consequent is a negated
        # literal ("all bees do not reproduce" -> [-isa(bee,X),
        # -has_property(reproduce,X), $block]) is all-negative after the meta
        # strip yet must survive -- the negative literal IS the consequent, not
        # a headless antecedent.  Using $block as the signal wrongly deleted the
        # whole normally(not(exists ...)) rule family (FOLIO G1).
        had_pos_typical = any(isinstance(l, list) and l and l[0] == "typical"
                              for l in lits)
        lits = [l for l in lits if not _is_meta_lit(l, _strip_block)]
        # Reflexive equality left by substitution: =(X,X) is always true (the
        # clause is a tautology -> drop it); -=(X,X) is always false (drop the
        # literal, keep the rest of the clause).
        if any(isinstance(l, list) and len(l) == 3 and l[0] == "=" and l[1] == l[2]
               for l in lits):
          continue
        lits = [l for l in lits
                if not (isinstance(l, list) and len(l) == 3
                        and l[0] == "-=" and l[1] == l[2])]
        if not lits:                                       # clause emptied -> drop
          continue
        if had_pos_typical and all(isinstance(l, list) and l and isinstance(l[0], str)
                                   and l[0].startswith("-") for l in lits):
          continue                  # headless defeasibility-marker clause -> drop
        # Drop the whole clause if it is a tautology (L and -L both present).
        if any(_complementary(lits[i], lits[j])
               for i in range(len(lits)) for j in range(i + 1, len(lits))):
          continue
        deduped = []
        for lit in lits:
          if lit not in deduped:
            deduped.append(lit)
        body = deduped[0] if len(deduped) == 1 else deduped
      elif _is_meta_lit(body, _strip_block):    # lone stripped meta unit clause
        continue
      _c["@logic"] = body
    new_result.append(_c)
  result = new_result
  return result
