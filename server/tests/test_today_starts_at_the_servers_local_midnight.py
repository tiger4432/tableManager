# -*- coding: utf-8 -*-
"""소유자 10-28 «2 ㄱ»: the dashboard's «today» audit count starts at the server's local midnight. It stamped the
local date with UTC, so on a +09:00 server «today» began at 09:00 local. Clock fixed at 2026-10-28; driven through
the route."""
import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import main                                                      # noqa: E402
from database import models                                      # noqa: E402

DAY = dt.date(2026, 10, 28)


class _Fixed(dt.date):
    @classmethod
    def today(cls):
        return DAY


def _today(client, monkeypatch):
    monkeypatch.setattr(dt, "date", _Fixed)        # the route imports `date` from the module at call time
    main.TODAY_UPDATES_CACHE["value"] = None
    try:
        res = client.get("/dashboard/summary")
    finally:
        monkeypatch.setattr(dt, "date", _Fixed.__mro__[1])
    assert res.status_code == 200, res.text
    return res.json()["today_updates"]


def test_rows_from_local_midnight_on_are_today(client, db_session, monkeypatch):
    local = dt.datetime.now().astimezone().tzinfo
    if dt.datetime.combine(DAY, dt.time()).replace(tzinfo=local).utcoffset() == dt.timedelta(0):
        pytest.skip("a UTC server's local midnight is UTC midnight - 08:59 and 09:01 cannot tell the two apart")
    before = _today(client, monkeypatch)
    at = [(DAY - dt.timedelta(days=1), dt.time(23, 59)), (DAY, dt.time(0, 1)), (DAY, dt.time(8, 59)),
          (DAY, dt.time(9, 1))]
    for i, (day, clock) in enumerate(at):
        db_session.add(models.AuditLog(table_name="t", row_id="r%d" % i, column_name="c", new_value=i,
                                       source_name="probe", transaction_id="tx%d" % i,
                                       timestamp=dt.datetime.combine(day, clock).replace(tzinfo=local)
                                       .astimezone(dt.timezone.utc)))
    db_session.commit()
    assert _today(client, monkeypatch) - before == 3     # 00:01 · 08:59 · 09:01 - not yesterday's 23:59
