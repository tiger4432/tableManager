# -*- coding: utf-8 -*-
"""How much work one chain group asked the alignment view for (S-94, 판정 235).

🔴 A NUMBER, NOT A GUESS, AND IT STAYS. The alignment mapper calls
`alignment_view_service.resolve_alignment_view` once per job, and each call resolves a
reference and builds a view. Whether those resolutions REPEAT inside one group is a
property of the data, not of the declaration - so it cannot be read off a config file, and
the only place it can be counted is the run itself. 「큐 깊이는 값으로 보임」 is the
standing rule this follows: the depth of the work a group does is a value an operator can
see, not an inference from a wall clock.

⚠️ THE BOUNDARY IS THE CHAIN GROUP'S, AND ONLY THE WORKER KNOWS IT. This module holds a
`contextvars.ContextVar`, so a scope opened by the group processing is visible to whatever
that group calls and to nothing else - a second group in another task cannot add to it, and
a route serving a user in the same process counts nothing because it never opens one. The
mapper is untouched: it calls the service, the service counts, the worker prints.

⛔ COUNTING IS FREE WHEN NOBODY IS COUNTING. Outside a scope every `note_*` is one
`ContextVar.get()` and a return, so the request path pays nothing for a number the chain
wants.
"""
from __future__ import annotations

import contextlib
import contextvars
import time

_COUNTS: contextvars.ContextVar = contextvars.ContextVar(
    "assy_manager.alignment_batch_counts", default=None)


class _Counts:
    """One group's tally. Plain attributes: this is read once, by the line that prints it."""

    __slots__ = ("view_builds", "reference_resolutions", "maps", "started", "phases",
                 "stages", "write_steps")

    def __init__(self):
        self.view_builds = 0
        self.reference_resolutions = 0
        self.maps: set = set()
        self.started = time.monotonic()
        self.phases: dict = {}
        self.stages: dict = {}
        self.write_steps: dict = {}

    def summary(self) -> dict:
        return {
            "view_builds": self.view_builds,
            "reference_resolutions": self.reference_resolutions,
            "distinct_maps": len(self.maps),
            "wall_seconds": round(time.monotonic() - self.started, 3),
            "phases": {name: round(seconds, 3)
                       for name, seconds in sorted(self.phases.items())},
            "stages": {name: round(seconds, 3)
                       for name, seconds in sorted(self.stages.items())},
            "write_steps": {name: round(seconds, 3)
                            for name, seconds in sorted(self.write_steps.items())},
        }


@contextlib.contextmanager
def counting_group():
    """Count what happens inside this block, and hand the tally back on the way out.

    Yields a callable returning the summary dict, rather than the tally itself, so the
    caller cannot accumulate into a scope it did not open.
    """
    counts = _Counts()
    token = _COUNTS.set(counts)
    try:
        yield counts.summary
    finally:
        _COUNTS.reset(token)


@contextlib.contextmanager
def phase(name: str):
    """Charge this block's WALL CLOCK to `name` in the open scope (S-94, 판정 236).

    🔴 WALL CLOCK, NOT A PROFILER. Four times this week a profiler's per-call charge
    picked the wrong target - twenty connections that a pool never opens, an eager read
    worth 1.5 %, 292,000 regex calls worth zero, a reference cache worth zero. The number
    that decides where to work is the one an operator waits through, so that is the number
    this collects, on the same line as the counts it belongs beside.

    ⚠️ OVERLAPPING NAMES WOULD LIE. Each phase wraps a contiguous block and the
    blocks do not nest, so the seconds sum to less than the build and the remainder is
    "everything not named" - which is itself an answer about whether the named four are the
    whole story.
    """
    counts = _COUNTS.get()
    if counts is None:
        yield
        return
    started = time.monotonic()
    try:
        yield
    finally:
        counts.phases[name] = counts.phases.get(name, 0.0) + (time.monotonic() - started)


@contextlib.contextmanager
def stage(name: str):
    """Charge this block's WALL CLOCK to `name` among the group's MACHINERY (S-94, 판정 241).

    🔴 A SECOND LAYER, AND IT HAS TO BE A SECOND DICT. `phase` names what happens INSIDE
    one alignment view build; this names what the group does AROUND the mapper - reading
    the outbox, calling the mapper, writing each target table. The mapper call contains
    every phase, so putting the two in one dict would count the same seconds twice and the
    line's own remainder would stop being an answer.

    ⚠️ WHY IT IS NOT ANOTHER `mapper_ms`. The batch loop already records a `mapper_ms`
    for its latency budget, and that name is not true of what it measures: it brackets the
    WHOLE group body - mapper, writes and outbox together - which is exactly why the ~15 s
    of chain machinery could not be aimed at. This layer splits that one number, and the
    stage names say which part is which rather than one of them borrowing the name.

    ⛔ LIKE `phase`, THE BLOCKS MUST NOT NEST INSIDE EACH OTHER, or the sum stops being
    comparable with the group's wall clock and the unnamed remainder goes negative - the
    arithmetic saying a cost was filed under something that did not incur it.
    """
    counts = _COUNTS.get()
    if counts is None:
        yield
        return
    started = time.monotonic()
    try:
        yield
    finally:
        counts.stages[name] = counts.stages.get(name, 0.0) + (time.monotonic() - started)


@contextlib.contextmanager
def write_step(name: str):
    """Charge this block's WALL CLOCK to `name` INSIDE one `write:<table>` stage (S-151).

    🔴 A THIRD DICT, FOR THE REASON `stage` NEEDED A SECOND ONE. `stage("write:<table>")`
    already brackets the whole `apply_batch_updates` call, so naming its inner parts in
    the SAME dict would count those seconds twice - `sum(stages)` would exceed the group's
    wall clock and the MACHINERY remainder, which is clamped at zero, would silently stop
    being an answer. The layers nest in reality, so they must not share a dict.

    ⚠️ WHAT THE REMAINDER MEANS HERE. The line subtracts these from the `write:*` stages,
    so "unnamed" is the part of the write that no step below claimed. Like the other two
    layers the blocks must be contiguous and must not nest inside each other.

    ⛔ NOT A PROFILER, AND NOT PER ROW. A group writes a thousand rows through one call;
    a per-row charge here would cost more than the thing it measures and would answer a
    question - "which row" - that nobody is asking.
    """
    counts = _COUNTS.get()
    if counts is None:
        yield
        return
    started = time.monotonic()
    try:
        yield
    finally:
        counts.write_steps[name] = counts.write_steps.get(name, 0.0) + (
            time.monotonic() - started)


def in_group() -> bool:
    """Is a chain group's scope open around this call? (S-94, 판정 242)

    🔴 ONE BOUNDARY, NOT A SECOND SWITCH. The scoring diagnostics exist so a person
    can follow ONE scoring run with a pencil - the file says so itself - and the automatic
    chain writes a thousand of them per group, which nobody reads and which cost a third of
    the mapper call. The question "is this a person's request or the chain's" already has an
    answer here, opened by the one loop that knows where a group begins, so nothing new is
    declared: the emit site asks this instead of a flag somebody has to remember to set.
    """
    return _COUNTS.get() is not None


def note_view_build() -> None:
    """One `resolve_alignment_view` call reached the view builder."""
    counts = _COUNTS.get()
    if counts is not None:
        counts.view_builds += 1


def note_reference(table, map_id) -> None:
    """One reference was resolved, to this map. `None` map ids are counted, not folded:
    a group whose references all resolve to nothing is a different fact from one whose
    references repeat, and both are answers this line has to be able to give."""
    counts = _COUNTS.get()
    if counts is not None:
        counts.reference_resolutions += 1
        counts.maps.add((table, map_id))
