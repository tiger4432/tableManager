# -*- coding: utf-8 -*-
"""A statement the database cancels (statement_timeout) spent its time in the database - the request's clock counts it
as SQL, not Python (lead 11-13: the grid's writers read cut at grid_read_timeout_seconds read «SQL 0.00 s · Python
10.03 s» on the slow line, after_cursor_execute never runs for a statement that raised)."""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from runtime import request_timing


def test_a_statement_cancelled_by_its_limit_is_counted_as_database_time(pg_engine):
    began = request_timing.begin("/probe")
    try:
        with pg_engine.connect() as conn:
            conn.execute(text("SET statement_timeout = 400"))
            with pytest.raises(OperationalError, match="QueryCanceled"):
                conn.execute(text("SELECT pg_sleep(3)"))
        said = request_timing.spent()
    finally:
        request_timing.end(began, "GET", "/probe", None)
    assert said["queries"] == 2, said             # the SET and the cancelled statement
    assert said["seconds"] >= 0.35, said          # the 0.4 s the database spent before it cancelled
