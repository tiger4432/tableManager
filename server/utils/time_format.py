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
from datetime import timezone

# [성능 최적화] 타임존 객체 캐싱 (astimezone()의 시스템 호출 비용 절감)
LOCAL_TIMEZONE = dt_pkg.datetime.now(dt_pkg.timezone.utc).astimezone().tzinfo

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
#   both aware  -> equal means the same UTC INSTANT, and `astimezone(LOCAL_TIMEZONE)`
#                  maps an instant to one wall time. Two aware values carrying
#                  different tzinfo but the same instant are the same output, which is
#                  exactly what a shared entry should return.
#   mixed       -> naive and aware are never equal, so they never share an entry.
# This is not a claim about "similar" values - `dict` resolves collisions with `==`,
# and `==` on datetimes is precisely the equivalence class above.
#
# [No new staleness] `LOCAL_TIMEZONE` is a FIXED-offset object resolved once at import
# (`datetime.now(utc).astimezone().tzinfo`), so the conversion was already pinned to
# the offset at process start. The memo caches a value that was already constant for
# the life of the process; it cannot drift further than the unmemoised code did.
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
    """UTC 데이트타임을 현지 시간(Local) 문자열로 변환합니다.

    Memoised on the argument - see `_LOCAL_STR_MEMO` for why that is sound.
    """
    if not dt:
        return ""
    cached = _LOCAL_STR_MEMO.get(dt)
    if cached is not None:
        return cached
    # SQLite naive datetime assumes UTC. Force UTC if naive before conversion.
    aware = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    # [최적화] 캐시된 타임존 사용
    out = aware.astimezone(LOCAL_TIMEZONE).strftime(TS_FMT)
    if len(_LOCAL_STR_MEMO) >= _LOCAL_STR_MEMO_MAX:
        _LOCAL_STR_MEMO.clear()
    _LOCAL_STR_MEMO[dt] = out
    return out
