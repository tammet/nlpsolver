"""Scoped, complete option state for conversion experiments.

`globals.set_global_options` MERGES: it writes the keys it is given and leaves
every other key at whatever the previous caller set.  That is fine for a single
run configured once, and wrong for a matrix, where one conversion's flags become
the next conversion's silent defaults.  It has already produced one false
finding — a `standard` conversion that had inherited `abstract-max` flags and was
reported as evidence about `normally` placement.

Use this instead of calling `set_global_options` with a partial dict:

    with option_scope.scoped(guarddrop_flag=True):
        clauses = convert(...)

Inside the block the option state is *exactly* the module defaults plus the
overrides given; on exit the caller's previous state is restored, so a scope can
nest inside a run that had its own configuration.
"""

import contextlib
import copy

_PRISTINE = [None]


def defaults():
    """A copy of `globals.options` as the module defines it.

    Captured the first time it is asked for.  Import this module before any
    conversion runs if the process configures options at start-up and you want
    the shipped defaults rather than that configuration.
    """
    import globals as g
    if _PRISTINE[0] is None:
        if not g.options:
            raise RuntimeError("globals.options is empty; the defaults cannot "
                               "be captured from it")
        _PRISTINE[0] = copy.deepcopy(g.options)
    return copy.deepcopy(_PRISTINE[0])


def full_options(overrides=None, clear_nofix=True):
    """The complete option dict for a conversion: defaults + overrides."""
    opts = defaults()
    if clear_nofix:
        for k in opts:
            if k.startswith("nofix_"):
                opts[k] = False
    for k, v in (overrides or {}).items():
        if k not in opts:
            raise KeyError("option %r is not recognized" % k)
        opts[k] = v
    return opts


@contextlib.contextmanager
def scoped(overrides=None, clear_nofix=True, **kw):
    """Run a block with a complete, isolated option state."""
    import globals as g
    merged = dict(overrides or {})
    merged.update(kw)
    # build the new state BEFORE touching the live dict: `full_options` reads
    # the defaults, and the defaults are captured lazily from that same dict, so
    # clearing first would snapshot an empty one
    new = full_options(merged, clear_nofix)
    before = copy.deepcopy(g.options)
    try:
        g.options.clear()
        g.options.update(new)
        yield g.options
    finally:
        g.options.clear()
        g.options.update(before)


def is_pristine_for(names):
    """True if every named option currently equals its shipped default.

    A cheap assertion for a test that wants to show a scope really reset the
    state rather than merely writing over part of it.
    """
    import globals as g
    d = defaults()
    return all(g.options.get(n) == d.get(n) for n in names)
