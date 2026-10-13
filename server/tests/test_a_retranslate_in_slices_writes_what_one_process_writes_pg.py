"""A whole source's re-translate in slices (총괄 fd550df13 ㄱ · 0cd396d3d) writes what one process writes.

  bounds   `slice_bounds` cuts at key values - every row in exactly one range, no key value in two, read back by the
           slices' own read (`_fetch_v2_lineage_rows` with `after`/`upper`) for a text and a timestamptz key; ONE range
           when one is asked, the page key has no index, or a row's key is NULL
  atoms    four slices and the tail write the atoms (every column but id) and the row index one whole run writes
  door     the Re-translate op in four slices - their answers summed, the tail once, «4 slices (cores C)» said
"""
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from admin import retroactive
from conftest import PG_TEST_SCHEMA
from ledger import backfill
from support import hold_world as hw

pytestmark = pytest.mark.pg
S = PG_TEST_SCHEMA
ROWS = 30


# ------------------------------------------------------------------------------------------------- bounds

KEYS = {
    "text": ("text", ["'g%02d'" % (i // 3) for i in range(40)]),
    # one value holds half the rows (two cuts land on it) and the last value holds the last quarter (a cut lands on it)
    "heavy": ("text", ["'a'"] * 5 + ["'b'"] * 20 + ["'c'"] * 5 + ["'d'"] * 10),
    # one value, two spellings (1.0 · 1.00): the cuts at 10 and 20 land on it - one cut, not an empty range between
    "numeric": ("numeric", ["1.0"] * 12 + ["1.00"] * 13 + ["2"] * 5 + ["3"] * 10),
    "timestamptz": ("timestamptz", ["timestamptz '2026-10-01 00:00:00.123456+00' + interval '%d minutes'" % (i // 3)
                                    for i in range(40)]),
}


#: The index a case puts on the page key - only the btree with no WHERE gives the rows in its order.
INDEXES = {True: "(k)", "hash": "USING hash (k)", "partial": "(k) WHERE v >= 0"}


@pytest.fixture(name="table")
def fixture_table(pg_engine):
    made = []

    def make(kind, index=True, null=False):
        sql_type, values = KEYS[kind]
        name = "sb_%s" % kind
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s".%s' % (S, name)))
            conn.execute(text('CREATE TABLE "%s".%s (k %s, v int)' % (S, name, sql_type)))
            conn.execute(text('INSERT INTO "%s".%s VALUES %s' % (
                S, name, ", ".join("(%s, %d)" % (value, i) for i, value in enumerate(values)))))
            if null:
                conn.execute(text('INSERT INTO "%s".%s VALUES (NULL, -1)' % (S, name)))
            if index:
                conn.execute(text('CREATE INDEX %s_k ON "%s".%s %s' % (name, S, name, INDEXES[index])))
        made.append(name)
        return SimpleNamespace(relation="%s.%s" % (S, name),
                               driver=SimpleNamespace(cursor_columns=("k",), order_by=("v",)))
    yield make
    with pg_engine.begin() as conn:
        for name in made:
            conn.execute(text('DROP TABLE IF EXISTS "%s".%s' % (S, name)))


def _read(engine, plan, key_range):
    connection = engine.raw_connection()
    try:
        return backfill._fetch_v2_lineage_rows(connection, plan, ["k", "v"], after=key_range[0], upper=key_range[1])
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.parametrize("kind, ranges", [("text", 4), ("timestamptz", 4), ("heavy", 2), ("numeric", 2)])
def test_every_row_falls_in_one_range_and_no_key_in_two(pg_engine, table, kind, ranges):
    """«heavy»: the cuts land on b, b and d - one range per value cut, none after the last value: (-, b] · (b, -)."""
    plan = table(kind)
    bounds, rows = backfill.slice_bounds(pg_engine, plan, 4)
    assert (len(bounds), rows) == (ranges, 40), bounds
    read = [_read(pg_engine, plan, key_range) for key_range in bounds]
    assert all(read), [len(part) for part in read]
    assert sorted(row["v"] for part in read for row in part) == list(range(40))
    keys = [{row["k"] for row in part} for part in read]
    assert all(not (keys[i] & keys[j]) for i in range(ranges) for j in range(i + 1, ranges))


def test_the_rows_no_page_reads_are_counted(pg_engine, table):
    """총괄 9752e91f7 ⑤: a NULL page key is outside every page's `>` and every slice's range - counted at the run's end."""
    assert backfill._rows_without_page_key(pg_engine, table("text")) == 0
    assert backfill._rows_without_page_key(pg_engine, table("timestamptz", null=True)) == 1


@pytest.mark.parametrize("why, make, slices", [
    ("one asked", dict(), 1),
    ("no index on the page key", dict(index=False), 4),
    ("a hash index on it", dict(index="hash"), 4),
    ("a partial index on it", dict(index="partial"), 4),
    ("a NULL page key", dict(null=True), 4),
])
def test_one_range_when(pg_engine, table, why, make, slices):
    bounds, _rows = backfill.slice_bounds(pg_engine, table("text", **make), slices)
    assert bounds == [(None, None)], why


# ------------------------------------------------------------------------------------------------- atoms

@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    for w in hw.build(pg_engine, monkeypatch, tmp_path, batch=True):
        hw.push(w, [{"log_id": "L%03d" % i, "dt_job": "J%d" % (i % 3), "dt_x": i, "dt_y": 1, "netdie": i}
                    for i in range(ROWS)])
        hw.settle(w)
        import database.database as database
        monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=pg_engine))
        monkeypatch.setattr(retroactive, "_ledger_setup", lambda params: w["setup"])
        yield w


def _written(world):
    """The source's atoms, every column but id, and its row index lines."""
    with world["engine"].connect() as conn:
        columns = [c for c in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = :s AND table_name = "
            "'ledger_events' AND column_name <> 'id' ORDER BY ordinal_position"), {"s": S}).scalars()]
        atoms = sorted(tuple(map(str, r)) for r in conn.execute(text(
            "SELECT %s FROM ledger_events WHERE source_who = :w" % ", ".join(columns)), {"w": hw.SOURCE}))
        refs = sorted(tuple(map(str, r)) for r in conn.execute(text(
            "SELECT * FROM ledger_source_row_ref WHERE source_who = :w"), {"w": hw.SOURCE}))
    return columns, atoms, refs


def _forget(world):
    """The source's atoms and row index lines gone - from this world's scratch schema."""
    with world["engine"].begin() as conn:
        assert conn.execute(text("SELECT current_schema()")).scalar() == S
        conn.execute(text("DELETE FROM ledger_events WHERE source_who = :w"), {"w": hw.SOURCE})
        conn.execute(text("DELETE FROM ledger_source_row_ref WHERE source_who = :w"), {"w": hw.SOURCE})


def _whole(world, **given):
    return backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                            page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True, **given)


def test_four_slices_and_the_tail_write_what_one_run_writes(world):
    one = _whole(world)
    columns, atoms, refs = written = _written(world)
    assert one["rows_in_scope"] == ROWS and atoms and refs and "source_event_id" in columns
    plan, _scoped = backfill.rescope_scope(world["setup"], hw.SOURCE, None, None, whole_source=True)
    bounds, rows = backfill.slice_bounds(world["engine"], plan, 4)
    assert (len(bounds), rows) == (4, ROWS), bounds
    _forget(world)                      # 총괄 9752e91f7 ③: the slices write it all again, or the answer is the first run's
    assert _written(world)[1:] == ([], [])
    parts = [_whole(world, key_range=key_range) for key_range in bounds]
    backfill.whole_source_tail(world["engine"], world["setup"], hw.SOURCE, plan)
    assert [part["rows_in_scope"] > 0 for part in parts] == [True] * 4
    assert sum(part["rows_in_scope"] for part in parts) == ROWS
    assert _written(world) == written


def test_the_run_door_in_four_slices_answers_as_one_process(world, monkeypatch, pg_engine):
    """`_run_ledger_rescope` with four slices run here, one after another, in place of their processes (a slice's
    process reads the configured database, not this scratch schema - the real launcher pass runs them)."""
    import ingestion.settings
    monkeypatch.setattr(retroactive.os, "cpu_count", lambda: 16)                 # 4 slices allowed on any box
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings",
                        lambda path=None: {"retroactive_debug": False, "ledger_translate_slices": 4})
    params = {"source": hw.SOURCE, "whole_source": True}
    lines, ran = [], []
    db = sessionmaker(bind=pg_engine)()

    def here(control, bounds, total):
        ran.append((list(bounds), total))
        return [retroactive._rescope(db, params, retroactive.RunControl(None, op="ledger_rescope", log=lines.append,
                                                                         report=lambda processed: None),
                                     key_range=key_range) for key_range in bounds]
    tails = []
    real_tail = backfill.whole_source_tail
    monkeypatch.setattr(retroactive, "_run_slices", here)
    monkeypatch.setattr(backfill, "whole_source_tail", lambda *a, **k: tails.append(1) or real_tail(*a, **k))
    # rows no page reads (a NULL page key) are counted at the run's end and said (총괄 9752e91f7 ⑤)
    monkeypatch.setattr(backfill, "_rows_without_page_key", lambda engine, plan: 2)
    _whole(world)
    written = _written(world)
    tails.clear()
    _forget(world)
    try:
        control = retroactive.RunControl("slices-door", op="ledger_rescope", log=lines.append)
        with retroactive._beating(control, pg_engine):
            out = retroactive._run_ledger_rescope(db, params, lines.append, control=control)
    finally:
        db.close()
    assert [len(bounds) for bounds, _total in ran] == [4] and ran[0][1] == ROWS
    assert tails == [1]
    assert out["rows_in_scope"] == ROWS and out["refused"] == 0 and out["rows_without_page_key"] == 2
    assert any(line.startswith("[ledger_rescope] 4 slices (cores ") for line in lines), lines[:5]
    assert any(line.startswith("[ledger_rescope] 2 rows of ") and " have no row_id (the page key) - " in line
               for line in lines), [line for line in lines if "page key" in line]
    assert _written(world) == written
