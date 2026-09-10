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

    __slots__ = ("view_builds", "reference_resolutions", "maps", "started")

    def __init__(self):
        self.view_builds = 0
        self.reference_resolutions = 0
        self.maps: set = set()
        self.started = time.monotonic()

    def summary(self) -> dict:
        return {
            "view_builds": self.view_builds,
            "reference_resolutions": self.reference_resolutions,
            "distinct_maps": len(self.maps),
            "wall_seconds": round(time.monotonic() - self.started, 3),
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
