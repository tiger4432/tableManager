"""Lead 11-11 안 1: on SQLite `now()` is CURRENT_TIMESTAMP, whole seconds - two writes in one second took one instant
and their lines' `at` tied (test_replace_map_scope_diff: «a REAL change must still move it»). The one seat that reads
the database's time (`crud.batch_write_instant`) reads SQLite's clock to the millisecond."""
import time

from database import crud


def test_two_writes_milliseconds_apart_take_two_instants(db_session):
    assert db_session.get_bind().dialect.name == "sqlite", "canary: the clock this test is about"
    first = crud.batch_write_instant(db_session)
    time.sleep(0.005)
    second = crud.batch_write_instant(db_session)
    assert second > first, (first, second)
    assert (second - first).total_seconds() < 1, "the same second - a whole-second clock gives them one instant"
