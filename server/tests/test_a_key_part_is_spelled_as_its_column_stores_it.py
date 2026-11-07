# -*- coding: utf-8 -*-
"""총괄 e243d6abf ③ · d5cf3a954: a composite key was assembled from the payload's spelling and
rebuilt from the stored value's, so the same row written twice - a number sent as "1.0", a time
sent without seconds - made a shell and merged it. Each part is now spelled as its column stores
it (`crud.key_part`): a number as `cast_value_by_type` stores it, a time as its instant in ISO on the
declared zone (ingestion_settings "expression_time_zone", 599fc1988). Every spelling of one value lands on one
row; a key part edited to ANOTHER row's value still merges."""
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import MetaData, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
import event_constants                                              # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402
import expression                                                   # noqa: E402

T_ONLY, T_KEY = "zz_spell_only", "zz_spell_key"
TYPES = {"lot": "string", "wafer": "number", "t": "datetime", "v": "string"}
TABLES = {
    T_ONLY: {"composite_key_source": ["lot", "wafer", "t"], "column_types": dict(TYPES)},
    T_KEY: {"business_key": "bk", "composite_key_source": ["lot", "wafer", "t"],
            "column_types": {"bk": "string", **TYPES}},
}
INSTANT = datetime(2026, 10, 3, 3, 0, 0, tzinfo=timezone.utc)
NUMBERS = ["1", "1.0", "01", 1.0, 1, " 1 "]


def _times(instant):
    """Every spelling of one instant the write door takes - naive ones on the declared zone's wall."""
    wall = instant.astimezone(expression.time_zone())
    naive = wall.replace(tzinfo=None)
    micro = ".%06d" % instant.microsecond if instant.microsecond else ""
    return [naive.strftime("%Y-%m-%d %H:%M") if not micro else naive.strftime("%Y-%m-%d %H:%M:%S") + micro,
            naive.strftime("%Y-%m-%d %H:%M:%S") + micro,
            naive.strftime("%Y-%m-%dT%H:%M:%S") + micro,
            wall.isoformat(),
            instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + micro + "Z",
            pd.Timestamp(instant), instant, naive]


# ------------------------------------------------------------------ the spelling, no database

def test_every_spelling_of_one_value_is_one_key_part():
    crud.TABLE_CONFIG[T_ONLY] = TABLES[T_ONLY]
    try:
        assert {crud.clean_str_value(crud.key_part(T_ONLY, "wafer", n)) for n in NUMBERS} == {"1"}
        for instant in (INSTANT, INSTANT.replace(microsecond=123456)):
            spelled = {crud.key_part(T_ONLY, "t", t) for t in _times(instant)}
            assert len(spelled) == 1, spelled
        assert crud.key_part(T_ONLY, "t", INSTANT) != crud.key_part(          # two instants
            T_ONLY, "t", INSTANT.replace(microsecond=123456))
        assert crud.key_part(T_ONLY, "t", "2026-10-03 12:00") == datetime(
            2026, 10, 3, 12, tzinfo=expression.time_zone()).isoformat()          # ISO, T, the zone's offset
        assert crud.key_part(T_ONLY, "t", "2026/10/03 12:00") == "2026/10/03 12:00"  # not ISO: as sent
        assert crud.key_part(T_ONLY, "wafer", "abc") == "abc"          # refused by the column: as sent
        assert crud.key_part(T_ONLY, "wafer", "  ") is None
    finally:
        crud.TABLE_CONFIG.pop(T_ONLY, None)


def test_the_census_names_which_parts_spelling_moved():
    """`rebuild_blank_business_keys` previews the rows whose stored key is not the rebuilt one;
    it says which part moved, by the column's type."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    import rebuild_blank_business_keys as census

    crud.TABLE_CONFIG[T_ONLY] = TABLES[T_ONLY]
    try:
        parts = TABLES[T_ONLY]["composite_key_source"]
        moved = [census._moved_parts(T_ONLY, old, "L1_1_2026-10-03 12:00:00", parts, "_")
                 for old in ("L1_1.0_2026-10-03 12:00:00", "L1_1_2026-10-03 12:00",
                             "L1_1.0_2026-10-03 12:00", "L1_1_2026/10/03 12:00", "L_1_1_x")]
        assert moved == ["number", "datetime", "datetime + number", "not_iso", "split"], moved
    finally:
        crud.TABLE_CONFIG.pop(T_ONLY, None)


# ------------------------------------------------------------------ on PostgreSQL, both shapes

@pytest.fixture(name="db")
def fixture_db(pg_engine):
    with pg_engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname = :s"),
                            {"s": PG_TEST_SCHEMA}).scalar() == 1
    # The write door still hands a naive time to PostgreSQL, which stores it on the SESSION zone (R5 ⓑ) - so
    # stored = rebuilt below asks that the session reads it on the zone the key reads it on.
    with pg_engine.connect() as conn:
        assert conn.execute(text("SHOW TimeZone")).scalar() == expression.time_zone().key
    saved = dict(crud.TABLE_CONFIG)
    for name in TABLES:
        retire_dynamic_model(name)
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)

    def clean():
        with pg_engine.begin() as conn:
            for name in TABLES:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))
                for side in ("cell_sources", "cell_overwrites", "database_outbox", "audit_logs"):
                    conn.execute(text('DELETE FROM "%s".%s WHERE table_name = :t'
                                      % (PG_TEST_SCHEMA, side)), {"t": name})

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in TABLES:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = maker()
    try:
        yield session, maker
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in TABLES:
            retire_dynamic_model(name)


def _write(db, table, row, row_id=None):
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(row_id=row_id, updates=dict(row), source_name="parser_a",
                                      updated_by="t")]))
        db.commit()


def _state(maker, table):
    """Rows, merges, and each row's stored key beside the key its parts rebuild to - read in a
    fresh session, so the parts are what PostgreSQL gives back."""
    db = maker()
    try:
        rows = db.query(models.DYNAMIC_TABLES[table]).all()
        keys = [(r.business_key_val, crud.rebuilt_business_key(table, r)) for r in rows]
        merges = db.execute(text("SELECT count(*) FROM audit_logs WHERE table_name = :t "
                                 "AND source_name = 'collision_merge'"), {"t": table}).scalar()
        return len(rows), merges, keys
    finally:
        db.close()


@pytest.mark.pg
@pytest.mark.parametrize("table", [T_ONLY, T_KEY])
@pytest.mark.parametrize("instant", [INSTANT, INSTANT.replace(microsecond=123456)],
                         ids=["seconds", "microseconds"])
def test_every_spelling_written_in_turn_lands_on_one_row(db, table, instant):
    session, maker = db
    for wafer in NUMBERS:
        for when in _times(instant):
            _write(session, table, {"lot": "L1", "wafer": wafer, "t": when, "v": repr(when)})
    rows, merges, keys = _state(maker, table)
    assert (rows, merges) == (1, 0), keys
    assert keys[0][0] == keys[0][1], keys                          # stored = rebuilt after reading


@pytest.mark.pg
@pytest.mark.parametrize("table", [T_ONLY, T_KEY])
def test_a_time_that_is_not_iso_keeps_its_text_and_the_census_names_it(db, table):
    """Kept as it came (총괄 d5cf3a954): written again it finds its row, but read back the part
    is a datetime - the census counts that row by name."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
    import rebuild_blank_business_keys as census

    session, maker = db
    for _ in range(3):
        _write(session, table, {"lot": "L1", "wafer": "1", "t": "2026/10/03 12:00", "v": "x"})
    rows, merges, keys = _state(maker, table)
    assert (rows, merges) == (1, 0), keys
    stored, rebuilt = keys[0]
    assert stored == "L1_1_2026/10/03 12:00" and rebuilt != stored, keys
    assert census._moved_parts(table, stored, rebuilt, TABLES[table]["composite_key_source"],
                               "_") == "not_iso"


@pytest.mark.pg
@pytest.mark.parametrize("table", [T_ONLY, T_KEY])
def test_a_blank_part_is_a_part_one_key_one_row(db, table):
    """Since 10-24 (소유자 «a,빈값 a,빈값 같은거로 처리», 총괄 242f4a43a) the blank part composes blank: the two writes
    are one key, one row, nothing merged."""
    session, maker = db
    for _ in range(2):
        _write(session, table, {"lot": "L1", "wafer": "", "t": "2026-10-03 12:00:00", "v": "x"})
    rows, merges, keys = _state(maker, table)
    assert (rows, merges) == (1, 0) and {k for k, _ in keys} == {"L1__2026-10-03T12:00:00+09:00"}, keys


@pytest.mark.pg
@pytest.mark.parametrize("table", [T_ONLY, T_KEY])
def test_a_key_part_edited_to_another_rows_value_still_merges(db, table):
    session, maker = db
    _write(session, table, {"lot": "L1", "wafer": "1", "t": "2026-10-03 12:00:00", "v": "a"})
    _write(session, table, {"lot": "L1", "wafer": "2", "t": "2026-10-03 12:00:00", "v": "b"})
    moved = [r.row_id for r in session.query(models.DYNAMIC_TABLES[table]).all()
             if r.wafer == 2]
    _write(session, table, {"wafer": "1.0"}, row_id=moved[0])
    rows, merges, keys = _state(maker, table)
    assert (rows, merges) == (1, 1), keys
