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


def to_local_str(dt):
    """UTC 데이트타임을 현지 시간(Local) 문자열로 변환합니다."""
    if not dt:
        return ""
    ts_fmt = "%Y-%m-%d %H:%M:%S"
    # SQLite naive datetime assumes UTC. Force UTC if naive before conversion.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # [최적화] 캐시된 타임존 사용
    return dt.astimezone(LOCAL_TIMEZONE).strftime(ts_fmt)
