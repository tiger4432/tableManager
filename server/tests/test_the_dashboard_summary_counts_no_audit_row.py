# -*- coding: utf-8 -*-
"""Owner 10-29 «ㄱ» (lead): `/dashboard/summary` no longer counts the audit log - its «today» count had no reader and
was the freeze when the admin opened (C's F4: every STALL line was that count, 9-28 s). The control: with the
re-correction rate and the effort score held (their own once-a-minute caches) and every other cache of the module
emptied, the route asks the audit table nothing. Bring the count back and this is red."""
import os
import sys

from sqlalchemy import event

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402


def test_the_summary_asks_the_audit_table_nothing(client, db_session):
    assert client.get("/dashboard/summary").status_code == 200        # the two kept figures are held from here
    for name in dir(main):
        cache = getattr(main, name)
        if name.endswith("_CACHE") and name not in ("RECORRECTION_CACHE", "EFFORT_CACHE") \
                and isinstance(cache, dict) and "value" in cache:
            cache["value"] = None
    said = []

    def seen(_conn, _cursor, statement, *_args):
        said.append(statement)
    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", seen)
    try:
        answer = client.get("/dashboard/summary")
    finally:
        event.remove(engine, "before_cursor_execute", seen)
    assert answer.status_code == 200
    assert said, "the route asked the database nothing at all - this measures nothing"
    assert [s for s in said if "audit_logs" in s] == []
    assert "today_updates" not in answer.json()
