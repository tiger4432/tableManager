# -*- coding: utf-8 -*-
"""소유자 10-28 «속도만»: the dashboard's «today» audit count is read once a minute, as the re-correction rate and the
effort score are - one pair (`main._held` / `main._hold`) for the three. Driven through the route."""
import os
import sys

from sqlalchemy import event

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402


def _today_counts(engine, client):
    said = []

    def seen(_conn, _cursor, statement, *_args):
        if "count(audit_logs.id)" in statement:
            said.append(statement)
    event.listen(engine, "before_cursor_execute", seen)
    try:
        res = client.get("/dashboard/summary")
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    assert res.status_code == 200, res.text
    return len(said), res.json()["today_updates"]


def test_the_today_count_is_read_once_a_minute(client, db_session):
    engine = db_session.get_bind()
    main.TODAY_UPDATES_CACHE["value"] = None
    first = _today_counts(engine, client)
    assert first[0] == 1, first
    assert _today_counts(engine, client) == (0, first[1])
    main.TODAY_UPDATES_CACHE["at"] -= main.TODAY_UPDATES_CACHE_TTL + 1
    assert _today_counts(engine, client)[0] == 1
