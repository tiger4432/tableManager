"""Timestamp formatting shared by the web server and the background workers.

Why this is its own module and not a helper inside `main.py`:

`chain_ingestion_worker` needed `to_local_str` to build its WebSocket payloads
and reached for `from main import to_local_str` inside the notification block.
That block is wrapped in `except Exception: logger.error("Failed to build
chained update notification")`, and importing `main` executes the whole web
application module - including the #13 fail-fast that raises `TableConfigError`
on a corrupt table_config.json. So a config that broke while the system was
running (the web server already up, past its own fail-fast) produced this:
the chain batch COMMITTED its rows, the import raised, the exception was
swallowed, and the WebSocket notification never went out. The rows existed and
no client knew, while the single log line named the wrong cause.

That is core value #3 - real-time propagation you can trust. A notification path
must not depend on importing an application module that is allowed to refuse.
This module imports nothing but the standard library, so there is nothing here
that can refuse.
"""

import datetime as dt_pkg
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# S-182 ⓐ - THE ONE FOLD FOR A WORLD TIME (SCHEMA_CANON R5, 판정 289)
# ---------------------------------------------------------------------------
#
# 🔴 R5 ALREADY RULED THIS AXIS: 「시각은 timestamptz 이고, 세상 시각은 «소스별로
# 선언»한다 · 선언이 없으면 «번역을 거절»한다 · naive datetime 금지」. The cell that
# implements it is `occurred_at_timezone` (ledger/config.py) and NO SECOND CELL IS ADDED -
# measured before proposing one: this axis already had three declared names
# (`occurred_at_timezone`, the v2 bind `timezone`, `display_timezone`), and a fourth would
# be the exact opposite of 「한 축은 한 칸」.
#
# ⚠️ WHAT WAS MISSING WAS NOT THE ANSWER BUT THE ENFORCEMENT. The catalogue's own
# comment measured it on assy_qa: an offset-bearing string lands correctly, garbage is
# refused with a DataError, and a NAIVE string is silently reinterpreted in the session
# TimeZone. Nothing checked that a parser actually emitted an offset, so the session
# setting quietly decided - and two processes configured differently disagreed.
#
# 🔴 `None` MEANS 「THE SEAT KEEPS TODAY'S BEHAVIOUR」, and that is what makes this
# round safe to deploy (gate D): a table that has declared nothing is not one character
# different, it is only COUNTED. Refusing an undeclared source is round ⓑ and a separate
# ruling, because turning it on today would stop every running load at once.

#: Seats that saw a naive world time, as counts - `{"<table>.<column>": n}`.
#: A plain dict on purpose: this is a diagnostic counter, not a ledger, and a lost
#: increment under a race costs a number rather than a fact.
_NAIVE_TIME_COUNTS = {}


def fold_time_value(value, *, zone=None):
    """An aware datetime, or `None` when this seat must keep the behaviour it has today.

    `None` is returned for three different reasons, and every one of them means the same
    thing to the caller - 「do exactly what you did before S-182」:
      · the value is not a datetime at all,
      · it is naive and no zone is declared for it (the general-table case today),
      · there is nothing to fold.

    🔴 A VALUE THAT ALREADY CARRIES AN OFFSET IS RETURNED UNTOUCHED. The source saying
    which zone it meant outranks any declaration - that rule is not invented here, it is
    the one `void_sat_format.declare_offset` already carries, and gate B scores it.
    """
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is not None:
        return value
    if not zone:
        return None
    try:
        return value.replace(tzinfo=ZoneInfo(str(zone)))
    except Exception:
        # An unusable zone is NOT silently defaulted - it is refused by returning None,
        # which leaves today's behaviour and lets the counter name the seat.
        return None


def note_naive_time(table, column):
    """Record that a world time arrived naive at `<table>.<column>`."""
    key = "%s.%s" % (table or "?", column or "?")
    _NAIVE_TIME_COUNTS[key] = _NAIVE_TIME_COUNTS.get(key, 0) + 1


def naive_time_counts():
    return dict(_NAIVE_TIME_COUNTS)


def naive_time_note():
    """`timezone_naive: <table.column> N · ...`, or `""` when nothing arrived naive.

    ⚠️ A VALUE, NOT PROSE. The owner cannot issue SQL, so a count the product prints
    beside its own chunk and startup lines is the only way this becomes visible - and an
    empty string when there is nothing to say, so a healthy deployment stays quiet.
    """
    if not _NAIVE_TIME_COUNTS:
        return ""
    parts = ["%s %d" % (k, _NAIVE_TIME_COUNTS[k]) for k in sorted(_NAIVE_TIME_COUNTS)]
    return "timezone_naive: " + " · ".join(parts)


TS_FMT = "%Y-%m-%d %H:%M:%S"

# Value memo. Rows are bulk-ingested, so a page of them shares a handful of
# timestamps: measured on a 10,000-row `dt_log` grid page, this function is called
# 20,000 times (created_at + updated_at per row) across 146 DISTINCT values.
# `strftime` and `astimezone` were therefore re-deriving the same string ~137x each.
#
# 🔴 **The key is the ARGUMENT, not the UTC-forced value.** Keying on the converted
# datetime would make a naive input miss forever, because a naive datetime never
# compares equal to an aware one.
#
# [Why the memo cannot answer wrongly]
# Two datetimes that are `==` (and therefore share a dict slot) always render the
# same string here:
#   both naive  -> equal means identical fields, and naive inputs are all forced to
#                  the same UTC assumption, so the output is a function of the fields.
#   both aware  -> equal means the same UTC INSTANT, and the render converts to UTC
#                  before formatting, so an instant maps to ONE string. Two aware values
#                  carrying different tzinfo but the same instant are the same output,
#                  which is exactly what a shared entry should return.
#                  🔴 THE UTC CONVERSION IS LOAD-BEARING FOR THIS PROOF, not cosmetic:
#                  `isoformat()` on the values as given would render `+00:00` and `+09:00`
#                  differently while `==` calls them equal, so they would share a memo slot
#                  and the second one would receive the first one's string.
#   mixed       -> naive and aware are never equal, so they never share an entry.
# This is not a claim about "similar" values - `dict` resolves collisions with `==`,
# and `==` on datetimes is precisely the equivalence class above.
#
# [No staleness at all, now] The render is `astimezone(utc).isoformat()`, a pure function
# of the instant - it reads no process state, so a memo entry cannot go stale for any
# reason. It used to convert to `LOCAL_TIMEZONE`, which at least pinned the offset at
# process start; S-182 ⓐ removed that seat, and with it the only thing this note had to
# reassure anyone about.
_LOCAL_STR_MEMO = {}

# Declared ceiling. This module is imported by four long-lived processes (web server,
# chain ingestion worker, graph sync worker, column filter), so an uncapped dict keyed
# on user data is the `TABLE_COUNT_CACHE` defect wearing a different hat - a cache
# nobody bounded, growing for the life of the process.
#
# On overflow the memo is CLEARED rather than evicted one entry at a time: eviction
# needs an ordering structure whose upkeep costs more per call than the lookup saves,
# and clearing lets the memo refill with whatever is hot now. A table whose timestamps
# are all distinct degrades to one failed dict lookup per call (~40 ns against the
# ~4.8 us this function costs) plus an occasional clear - under 1%, and bounded.
_LOCAL_STR_MEMO_MAX = 8192


def to_local_str(dt):
    """A timestamp rendered for a payload, as an OFFSET-BEARING string (S-182 ⓐ).

    🔴 IT NO LONGER RENDERS THE MACHINE'S LOCAL ZONE. It used to convert to
    `LOCAL_TIMEZONE` - the ambient zone of whatever host the process started on, resolved
    at import - so the same instant printed differently on two differently configured
    machines with nothing declared anywhere. `ledger_trace.DISPLAY_TIMEZONE_RULING` had
    already named that 「the same class of defect one step over」; this is that ruling
    applied to the seat it was written about.

    The string now carries its own offset, so the reader can convert it and the value says
    what it means. Which zone a HUMAN sees is the display side's question, and the display
    side has its own declaration (`display_timezone`) - it is not this function's to guess.

    ⚠️ THE NAME IS NOW STALE and is kept deliberately: renaming it would touch 31 call
    sites in four modules for no behaviour, against 「바뀌는 층만 바꾼다」. Named in the
    S-182 report as debt rather than left to be discovered.

    Memoised on the argument - see `_LOCAL_STR_MEMO` for why that is sound.
    """
    if not dt:
        return ""
    cached = _LOCAL_STR_MEMO.get(dt)
    if cached is not None:
        return cached
    # A naive value is still read as UTC HERE, which is today's behaviour and stays that
    # way (gate D) - this seat renders, it does not decide what a source meant. The seat
    # that decides is the write boundary, and it now COUNTS what arrives naive.
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    out = aware.astimezone(timezone.utc).isoformat(sep=" ", timespec="seconds")
    if len(_LOCAL_STR_MEMO) >= _LOCAL_STR_MEMO_MAX:
        _LOCAL_STR_MEMO.clear()
    _LOCAL_STR_MEMO[dt] = out
    return out
