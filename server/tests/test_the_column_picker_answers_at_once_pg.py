"""Owner 11-10 «4 ㄱ» (ops: a column picker read held 6.5 min during a file load): the picker answers at once with the
planner's estimate - `exact` false, its ordering `counting`, `updating` - and its exact counts run behind it, once a key;
the next read has them (`exact`, `counted_at`). A count past column_count_seconds is cut, said (`count_cut`), and not
counted again until a person asks (`recount`).
"""
import time

import pytest
from sqlalchemy import text

from ledger import column_stats

pytestmark = pytest.mark.pg

TABLE = {"business_key": "k"}
KEYS = tuple(tuple(names) for names in column_stats.declared_unique_keys(TABLE))


def _until(predicate, seconds=20.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def probe(pg_session, monkeypatch):
    name = "picker_probe_%d" % int(time.time() * 1000)
    pg_session.execute(text('CREATE TABLE "%s" (k text, note text, amount double precision)' % name))
    pg_session.execute(text('INSERT INTO "%s" SELECT \'k\' || g, CASE WHEN g %% 4 = 0 THEN \'\' WHEN g %% 4 = 1 THEN NULL '
                            'ELSE \'n\' END, CASE WHEN g %% 2 = 0 THEN g END FROM generate_series(1, 400) g' % name))
    pg_session.commit()
    pg_session.execute(text('ANALYZE "%s"' % name))
    pg_session.commit()
    column_stats.COUNTS.forget()
    runs = []
    real = column_stats.exact_counts
    monkeypatch.setattr(column_stats, "exact_counts", lambda *a, **k: runs.append(1) or real(*a, **k))
    try:
        yield name, runs
    finally:
        _until(lambda: not column_stats.COUNTS.running())
        column_stats.COUNTS.forget()
        pg_session.rollback()
        pg_session.execute(text('DROP TABLE IF EXISTS "%s"' % name))
        pg_session.commit()


def _cells(answer):
    return {column["name"]: column["populated"] for column in answer["columns"]}


def test_at_once_the_estimate_then_the_exact_counts_counted_once(pg_session, probe):
    name, runs = probe
    first = column_stats.picked(pg_session, name, TABLE, (), False, None)
    assert (first["exact"], first["updating"], first["ordering"], first["counted_at"]) == (False, True,
                                                                                         {"counting": True}, None)
    assert first["total_rows"] == 400 and _cells(first)["k"] == 400, first
    assert abs(_cells(first)["note"] - 200) <= 20 and abs(_cells(first)["amount"] - 200) <= 20, \
        ("the estimate takes the NULLs and the blanks off", first)
    assert _until(lambda: not column_stats.COUNTS.busy((name, (), KEYS)))
    then = column_stats.picked(pg_session, name, TABLE, (), False, None)
    assert then["exact"] is True and then["counted_at"] and then["updating"] is False
    assert _cells(then) == {"k": 400, "note": 200, "amount": 200}
    assert [item["columns"] for item in then["ordering"]["declared_keys"]] == [["k"]]
    again = column_stats.picked(pg_session, name, TABLE, (), False, None)
    assert runs == [1] and again["counted_at"] == then["counted_at"], "a key is counted once"
    asked = column_stats.picked(pg_session, name, TABLE, (), True, None)
    assert asked["updating"] is True and asked["exact"] is True, "a recount shows the last counts meanwhile"
    assert _until(lambda: len(runs) == 2 and not column_stats.COUNTS.busy((name, (), KEYS)))


def test_a_count_past_its_limit_is_cut_said_and_not_counted_again_by_itself(pg_session, probe, monkeypatch):
    name, runs = probe
    real = column_stats.population

    def slow(db, relation, columns=None):
        db.execute(text("SELECT pg_sleep(5)"))
        return real(db, relation, columns)

    monkeypatch.setattr(column_stats, "population", slow)
    column_stats.picked(pg_session, name, TABLE, ["k", "note"], False, 0.3)
    key = (name, ("k", "note"), KEYS)
    assert _until(lambda: not column_stats.COUNTS.busy(key), 10), "the limit did not cut the count"
    cut = column_stats.picked(pg_session, name, TABLE, ["k", "note"], False, 0.3)
    assert cut["exact"] is False and cut["count_cut"]["seconds"] == 0.3 and cut["count_cut"]["at"]
    assert (cut["ordering"], cut["combination"], cut["updating"]) == ({"cut": True}, {"cut": True}, False)
    time.sleep(0.5)
    assert runs == [1], "a cut count was counted again by itself"
