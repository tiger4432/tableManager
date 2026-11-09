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
import logging
import re
import time

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from utils import heartbeat

logger = logging.getLogger(__name__)

_COUNTS: contextvars.ContextVar = contextvars.ContextVar(
    "assy_manager.alignment_batch_counts", default=None)
#: What a stage boundary asks before it is entered - set by a chain group on ITS OWN THREAD
#: (`interrupt_at_stages`), so the watcher's stages and the loop's commit/rollback never see
#: it. The chain's pause is the one asker (총괄 3840af307).
_INTERRUPT: contextvars.ContextVar = contextvars.ContextVar(
    "assy_manager.stage_interrupt", default=None)


@contextlib.contextmanager
def interrupt_at_stages(check):
    """`check()` runs at every stage this block enters, and may raise to stop it there."""
    token = _INTERRUPT.set(check)
    try:
        yield
    finally:
        _INTERRUPT.reset(token)


class _Counts:
    """One group's tally. Plain attributes: this is read once, by the line that prints it."""

    __slots__ = ("view_builds", "reference_resolutions", "maps", "started", "phases",
                 "stages", "write_steps", "write_counts", "tx")

    def __init__(self):
        self.view_builds = 0
        self.reference_resolutions = 0
        self.maps: set = set()
        # perf_counter, every layer of the line: monotonic ticks 15.6 ms on Windows - each step read ±16 ms (총괄 10-24)
        self.started = time.perf_counter()
        self.phases: dict = {}
        self.stages: dict = {}
        self.write_steps: dict = {}
        self.write_counts: dict = {}      # write step -> [how many, of what]
        self.tx = _Transaction()          # what the scope's statements and commits did (lead 11-09)

    def summary(self) -> dict:
        return {
            "view_builds": self.view_builds,
            "reference_resolutions": self.reference_resolutions,
            "distinct_maps": len(self.maps),
            "wall_seconds": round(time.perf_counter() - self.started, 3),
            "phases": {name: round(seconds, 3)
                       for name, seconds in sorted(self.phases.items())},
            "stages": {name: round(seconds, 3)
                       for name, seconds in sorted(self.stages.items())},
            "write_steps": {name: round(seconds, 3)
                            for name, seconds in sorted(self.write_steps.items())},
            "write_counts": {name: list(count)
                             for name, count in sorted(self.write_counts.items())},
            "transaction": self.tx.summary() if self.tx is not None else None,
        }


class _Transaction:
    """The scope's database side, from the engine's own events (lead 11-09 «행 수 · 단계별 초 · 쥔 초 · 문장 수 · 표마다
    넣음/고침/지움»): statements; seconds by the table a statement writes (reads together); from the first write to
    each commit's end - what the scope held - and the commits themselves; and per table the row versions each
    committed transaction made, asked on its connection just before COMMIT (pg_stat_xact_user_tables, PostgreSQL)."""

    __slots__ = ("statements", "by_table", "first_write", "held", "commit", "commit_began", "tuples")

    def __init__(self):
        self.statements, self.by_table, self.tuples = 0, {}, {}
        self.first_write = self.commit_began = None
        self.held = self.commit = 0.0

    def summary(self) -> dict:
        return {"statements": self.statements, "held": round(self.held, 3), "commit": round(self.commit, 3),
                "db": {name: round(seconds, 3) for name, seconds in sorted(self.by_table.items())},
                "rows": {name: list(n) for name, n in sorted(self.tuples.items())}}


#: The table a write statement names: INSERT INTO / UPDATE / DELETE FROM / COPY, a schema before it or not.
_WRITTEN = re.compile(r'^\s*(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|COPY)\s+(?:"?\w+"?\.)?"?(\w+)"?', re.I)
#: Reads, and anything else not naming a written table.
READS = "reads"
_XACT = ("SELECT relname, n_tup_ins, n_tup_upd, n_tup_hot_upd, n_tup_del FROM pg_stat_xact_user_tables "
         "WHERE n_tup_ins + n_tup_upd + n_tup_del > 0")


def _tx():
    counts = _COUNTS.get()
    return None if counts is None else counts.tx


def _quiet(where, exc):
    """🔴 THE COUNTERS ARE SILENT ALONE. One line says which part stopped; the scope counts no more, the write goes on."""
    counts = _COUNTS.get()
    if counts is not None:
        counts.tx = None
    logger.warning("[Counts] the write's transaction counts stopped at %s (%s: %s) - the write is unaffected",
                   where, type(exc).__name__, exc)


@event.listens_for(Engine, "before_cursor_execute")
def _statement_began(conn, cursor, statement, parameters, context, executemany):
    tx = _tx()
    if tx is None:
        return
    try:
        written = _WRITTEN.match(statement)
        now = time.perf_counter()
        if written and tx.first_write is None:
            tx.first_write = now
        conn.info.setdefault("assy_tx_counts", []).append((written.group(1) if written else READS, now))
        tx.statements += 1
    except Exception as exc:                                   # noqa: BLE001 - the counters' own failure
        _quiet("a statement", exc)


@event.listens_for(Engine, "after_cursor_execute")
def _statement_ended(conn, cursor, statement, parameters, context, executemany):
    tx = _tx()
    began = conn.info.get("assy_tx_counts")
    if tx is None or not began:
        return
    try:
        name, at = began.pop()
        tx.by_table[name] = tx.by_table.get(name, 0.0) + (time.perf_counter() - at)
    except Exception as exc:                                   # noqa: BLE001
        _quiet("a statement's end", exc)


@event.listens_for(Engine, "commit")
def _committing(conn):
    tx = _tx()
    if tx is None:
        return
    try:
        if conn.dialect.name == "postgresql":
            cursor = conn.connection.cursor()
            try:
                cursor.execute(_XACT)
                for name, ins, upd, hot, dele in cursor.fetchall():
                    had = tx.tuples.setdefault(name, [0, 0, 0, 0])
                    for at, n in enumerate((ins, upd, hot, dele)):
                        had[at] += n
            finally:
                cursor.close()
        tx.commit_began = time.perf_counter()
    except Exception as exc:                                   # noqa: BLE001
        _quiet("a commit", exc)


@event.listens_for(Session, "after_commit")
def _committed(session):
    tx = _tx()
    if tx is None or tx.commit_began is None:
        return
    now = time.perf_counter()
    tx.commit += now - tx.commit_began
    if tx.first_write is not None:
        tx.held += now - tx.first_write
    tx.first_write = tx.commit_began = None


@event.listens_for(Session, "after_rollback")
def _rolled_back(session):
    """A rolled-back attempt held nothing that stays - the next commit is held from its own first write."""
    tx = _tx()
    if tx is not None:
        tx.first_write = tx.commit_began = None


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
    started = time.perf_counter()
    try:
        yield
    finally:
        counts.phases[name] = counts.phases.get(name, 0.0) + (time.perf_counter() - started)


@contextlib.contextmanager
def stage(name: str, said: str = None):
    """Charge this block's WALL CLOCK to `name` among the group's MACHINERY (S-94, 판정 241).
    `said` - what the beat says beyond the name while in it: a write carries its page line (총괄 59f2ab3f4 -
    the write stage had replaced it on every page). The seconds still go to `name`.

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
    # Entering a stage is progress on the work this thread claimed - the watcher's file,
    # the chain's group - and the stage is what a stalled line names.
    heartbeat.progress(name if said is None else "%s · %s" % (name, said))
    check = _INTERRUPT.get()
    if check is not None:
        check()
    started = time.perf_counter()
    try:
        yield
    finally:
        counts.stages[name] = counts.stages.get(name, 0.0) + (time.perf_counter() - started)


@contextlib.contextmanager
def write_step(name: str, unit: str = "rows"):
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

    Yields `count(n)`: the block says how many `unit` it wrote, from a length it already
    holds - no query is added to count it (소유자 2026-09-26 헤비 레인 쓰기 로그).
    """
    counts = _COUNTS.get()
    if counts is None:
        yield _not_counting
        return
    started = time.perf_counter()

    def count(n):
        tally = counts.write_counts.setdefault(name, [0, unit])
        tally[0] += int(n)
    try:
        yield count
    finally:
        counts.write_steps[name] = counts.write_steps.get(name, 0.0) + (
            time.perf_counter() - started)


def _not_counting(n):
    """What a write step's `count` is when no scope is open - nothing to add to."""


def write_count(name: str, n: int, unit: str):
    """A count with no clock of its own, said beside the write steps (`cells offered`, lead 11-09)."""
    counts = _COUNTS.get()
    if counts is not None:
        tally = counts.write_counts.setdefault(name, [0, unit])
        tally[0] += int(n)


def write_steps_rewind():
    """A callable that puts this scope's write steps back to what they are NOW.

    A write that rolls back and tries again calls it before each attempt, so the seconds
    and rows a line prints are the committing attempt's - what the rolled-back attempt
    wrote never happened (총괄 69aad666e ②). Other tables' steps in the scope are kept.
    """
    counts = _COUNTS.get()
    if counts is None:
        return _not_rewinding
    steps = dict(counts.write_steps)
    tallies = {name: list(tally) for name, tally in counts.write_counts.items()}

    def rewind():
        counts.write_steps.clear()
        counts.write_steps.update(steps)
        counts.write_counts.clear()
        counts.write_counts.update({name: list(tally) for name, tally in tallies.items()})
    return rewind


def _not_rewinding():
    """What `write_steps_rewind` hands back when no scope is open - nothing to put back."""


def write_steps_text(summary: dict) -> str:
    """The INSIDE THE WRITE part of a line - one spelling for the watcher's chunk line and
    the chain's group line: each step's seconds and, when it counted, how many of what."""
    counts = dict(summary.get("write_counts") or {})
    steps = summary.get("write_steps") or {}
    said = "".join(
        " · %s %.3f s%s" % (name, seconds,
                            " / %d %s" % tuple(counts[name]) if name in counts else "")
        for name, seconds in sorted(steps.items())
    ) or " (none named)"
    said += "".join(" · %d %s" % tuple(count) for name, count in sorted(counts.items()) if name not in steps)
    return said + transaction_text(summary.get("transaction"))


def transaction_text(tx) -> str:
    """The TRANSACTION part: statements, seconds held (first write to commit end), commit seconds, database seconds
    by written table, and per table its row versions - inserted / updated (HOT) / deleted; dead = updated + deleted."""
    if not tx:
        return ""
    return (" · TRANSACTION %d statement(s) · held %.3f s · commit %.3f s · db%s · rows%s"
            % (tx["statements"], tx["held"], tx["commit"],
               "".join(" %s %.3f s" % (name, s) for name, s in tx["db"].items()) or " -",
               "".join(" %s +%d ~%d(hot %d) -%d" % (name, n[0], n[1], n[2], n[3])
                       for name, n in tx["rows"].items()) or " -"))


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
