# -*- coding: utf-8 -*-
"""A datetime key has one spelling (lead 599fc1988, owner «ㄱ, 한국시간»): a column declared datetime meets the same
instant whatever it is stored as (timestamptz or text) and however it is spelled. A time without an offset is the
wall clock of ingestion_settings "expression_time_zone" (Asia/Seoul when unset); the spelling is the one the stored
keys already carry - ISO, `T`, the zone's offset («2026-08-14T00:03:00+09:00»). Every seat that spells or compares
a key gives one answer: key_part · canonical_bind_value · the group key · the join-key probe · «did it change» ·
SQLite's and PostgreSQL's assy_key_instant · the join and its index. And the write door (d94342107): a time
without an offset is stored as the instant its key names, whatever zone the database session reads in."""
import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, retire_dynamic_model            # noqa: E402
import expression                                                   # noqa: E402
import map_overlay                                                  # noqa: E402
import chain_bindings                                               # noqa: E402
import notation_norm                                                # noqa: E402
from chain import ingestion_worker, join_into, join_key_index       # noqa: E402
import event_constants                                              # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from database.context import channel                                # noqa: E402

T_KEY, T_LEFT, T_RIGHT = "zz_dk_key", "zz_dk_left", "zz_dk_right"
KEY = "2026-08-14T00:03:00+09:00"
MICRO = "2026-08-14T00:03:00.123456+09:00"
INSTANT = datetime(2026, 8, 13, 15, 3, tzinfo=timezone.utc)
SPELLINGS = ["2026-08-14T00:03:00+09:00", "2026-08-13T15:03:00Z", "2026-08-13T15:03:00+00:00",
             "2026-08-13T10:03:00-05:00", "2026-08-14 00:03", "2026-08-14 00:03:00", "2026-08-14T00:03:00",
             " 2026-08-14T00:03:00+0900 ", INSTANT, INSTANT.replace(tzinfo=None, hour=0, day=14),
             pd.Timestamp(INSTANT)]
MICRO_SPELLINGS = ["2026-08-14 00:03:00.123456", "2026-08-13T15:03:00.123456Z", INSTANT.replace(microsecond=123456)]
NOT_A_TIME = ["2026/08/14 00:03", "2026-02-30", "garbage"]


@pytest.fixture(autouse=True)
def _declared_default_zone(monkeypatch):
    """The settings say nothing, so the zone is the written default - not this box's file."""
    import ingestion.settings

    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings", lambda *a, **k: {})
    from database import config_watcher
    config_watcher.forget_held()
    crud.TABLE_CONFIG[T_KEY] = {"composite_key_source": ["lot", "t"],
                                "column_types": {"lot": "string", "t": "datetime"}}
    yield
    crud.TABLE_CONFIG.pop(T_KEY, None)


def _seats(value):
    """Every seat's spelling of one datetime key part."""
    rule = {chain_bindings.GROUP_BY_KEY: ["t"]}
    return {
        "key_part": crud.key_part(T_KEY, "t", value),
        "canonical_bind_value": map_overlay.canonical_bind_value(T_KEY, "t", value),
        "group key": ingestion_worker.spelled_group_key(rule, T_KEY, {"t": value}),
        "join-key probe": (crud._folded_join_key({"t": value}, ["t"], [None], T_KEY) or (None,))[0],
        "sqlite": _sqlite(value),
    }


def _sqlite(value):
    engine = create_engine("sqlite://")
    notation_norm.install_sqlite_fold()
    with engine.connect() as conn:
        raw = value.isoformat(sep=" ") if isinstance(value, datetime) else value
        return conn.execute(text("SELECT %s(:v, :z)" % notation_norm.KEY_INSTANT_FUNCTION),
                            {"v": raw, "z": expression.time_zone().key}).scalar()


@pytest.mark.parametrize("spellings, key", [(SPELLINGS, KEY), (MICRO_SPELLINGS, MICRO)], ids=["seconds", "micro"])
def test_every_spelling_of_one_instant_is_one_key_at_every_seat(spellings, key):
    assert ingestion_worker.group_by_columns({chain_bindings.GROUP_BY_KEY: ["t"]}) == ["t"]
    for value in spellings:
        seats = _seats(value)
        assert seats.pop("group key") == "t=%r" % key, value
        assert set(seats.values()) == {key}, (value, seats)
        assert crud.value_key(value, "datetime") == crud.value_key(key, "datetime"), value


def test_a_date_is_its_midnight_and_a_text_that_is_no_time_keeps_its_text():
    seats = _seats("2026-08-14")
    assert seats.pop("group key") == "t='2026-08-14T00:00:00+09:00'"
    assert set(seats.values()) == {"2026-08-14T00:00:00+09:00"}, seats
    for value in NOT_A_TIME:
        seats = _seats(" %s " % value)
        assert seats.pop("group key") == "t=%r" % value
        assert set(seats.values()) == {value}, seats
    assert crud.key_part(T_KEY, "t", "  ") is None


def test_the_write_door_gives_a_time_without_an_offset_the_declared_zone():
    """d94342107: into a time column, read where the key reads it and passed on with the zone's offset; into a text
    column declared datetime - and anything else - byte-identical (the lead, after 3ea1ae778)."""
    tables = {T_KEY: {"column_types": {"lot": "string", "t": "datetime"}},
              T_LEFT: {"column_types": {"lot": "string", "t": "string"}}}
    for name in tables:
        retire_dynamic_model(name)
    models.init_dynamic_models(tables)
    try:
        assert crud.cast_value_by_type("2026-08-14 00:03", "datetime", "t", T_KEY) == KEY
        assert crud.cast_value_by_type(datetime(2026, 8, 14, 0, 3), "datetime", "t", T_KEY) == KEY
        for kept in ("2026-08-13T15:03:00Z", "2026-08-14T00:03:00+09:00", "2026/08/14 00:03"):
            assert crud.cast_value_by_type(kept, "datetime", "t", T_KEY) == kept
        for kept in ("2026-08-14 00:03", "2026-08-14T00:03:00", "2026-08-13T15:03:00Z"):
            assert crud.cast_value_by_type(kept, "datetime", "t", T_LEFT) == kept
    finally:
        for name in tables:
            retire_dynamic_model(name)


def test_a_pair_of_a_time_and_not_a_time_is_said():
    crud.TABLE_CONFIG[T_LEFT] = {"column_types": {"t": "string"}}
    try:
        said = join_into._key_types_differ({"right_table": T_KEY, "on": [{"left": "t", "right": "t"}]}, T_LEFT)
        assert said == ["%s.t string · %s.t datetime" % (T_LEFT, T_KEY)], said
    finally:
        crud.TABLE_CONFIG.pop(T_LEFT, None)


# ------------------------------------------------------------------ on PostgreSQL

@pytest.fixture(name="pg")
def fixture_pg(pg_engine):
    """Left: `t` stored as TEXT, declared datetime - what a column becomes when its type is changed in the
    declaration and schema sync adds nothing. Right: `t` a timestamptz column declared datetime."""
    saved = dict(crud.TABLE_CONFIG)
    tables = {T_LEFT: {"composite_key_source": ["lot"], "column_types": {"lot": "string", "t": "string"}},
              T_RIGHT: {"composite_key_source": ["lot"], "column_types": {"lot": "string", "t": "datetime",
                                                                         "v": "string"}}}
    for name in tables:
        retire_dynamic_model(name)
    models.init_dynamic_models(tables)
    crud.TABLE_CONFIG.update(tables)
    crud.TABLE_CONFIG[T_LEFT]["column_types"]["t"] = "datetime"

    def clean():
        with pg_engine.begin() as conn:
            for name in tables:
                conn.execute(text('DROP TABLE IF EXISTS "%s"."%s"' % (PG_TEST_SCHEMA, name)))

    clean()
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    for name in tables:
        models.DYNAMIC_TABLES[name].__table__.to_metadata(scratch, schema=None)
    scratch.create_all(pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    maker = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        clean()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        for name in tables:
            retire_dynamic_model(name)


@pytest.mark.pg
def test_the_function_is_made_in_the_scratch_schema_and_answers_as_python(pg):
    where = pg.execute(text("SELECT DISTINCT n.nspname, p.provolatile FROM pg_proc p JOIN pg_namespace n "
                            "ON n.oid = p.pronamespace WHERE p.proname = :f AND n.nspname = :s"),
                       {"f": notation_norm.KEY_INSTANT_FUNCTION, "s": PG_TEST_SCHEMA}).fetchall()
    assert where == [(PG_TEST_SCHEMA, "i")], where                     # IMMUTABLE by PostgreSQL's own word
    zone = expression.time_zone()
    for value in SPELLINGS + MICRO_SPELLINGS + NOT_A_TIME + ["2026-08-14"]:
        cast = "timestamptz" if isinstance(value, datetime) and value.tzinfo else (
            "timestamp" if isinstance(value, datetime) else "text")
        sql = pg.execute(text("SELECT %s(CAST(:v AS %s), :z)" % (notation_norm.KEY_INSTANT_FUNCTION, cast)),
                         {"v": value, "z": zone.key}).scalar()
        assert sql == map_overlay.time_key_text(value, zone), value


@pytest.mark.pg
def test_a_timestamptz_column_and_a_text_column_declared_datetime_meet_and_the_join_reads_the_index(pg):
    pg.execute(text('INSERT INTO "%s" (row_id, lot, t, v) VALUES (\'r1\', \'R\', :t, \'took\')' % T_RIGHT),
               {"t": INSTANT})
    for row_id, spelled in enumerate(["2026-08-14 00:03", "2026-08-13T15:03:00Z", "2026-08-14T00:03:00+09:00"]):
        pg.execute(text('INSERT INTO "%s" (row_id, lot, t) VALUES (:r, \'L\', :t)' % T_LEFT),
                   {"r": "l%d" % row_id, "t": spelled})
    pg.commit()
    spec = {"right_table": T_RIGHT, "on": [{"left": "t", "right": "t"}]}
    left_model, right_model = models.DYNAMIC_TABLES[T_LEFT], models.DYNAMIC_TABLES[T_RIGHT]
    left_rows, answers, _empty, _rows = join_into._read_once(pg, spec, left_model, right_model,
                                                      [left_model.row_id.isnot(None)], T_LEFT)
    assert {key for _row, key in left_rows} == {(KEY,)} and list(answers) == [(KEY,)], (left_rows, answers)

    pg.execute(text(join_key_index.required_index_ddl(T_RIGHT, ["t"]).replace(" CONCURRENTLY", "")))
    pg.commit()
    # `unique_index_covering`'s comparison, on the scratch schema (it reads public): PostgreSQL's own rendering of each
    # key, folded, against our expression - the round trip that decides whether the index is built again next time
    oid, nkeys = pg.execute(text("SELECT x.indexrelid, x.indnkeyatts FROM pg_index x JOIN pg_class i ON i.oid = "
                                 "x.indexrelid JOIN pg_namespace n ON n.oid = i.relnamespace WHERE i.relname = :i "
                                 "AND n.nspname = :s"), {"i": join_key_index.required_index_name(T_RIGHT, ["t"]),
                                                         "s": PG_TEST_SCHEMA}).one()
    built = {join_key_index.normalize_index_expression(e)
             for e in join_key_index._index_key_expressions(pg, oid, nkeys)}
    assert built == {join_key_index.normalize_index_expression(join_key_index.index_key_expression("t", None, T_RIGHT)),
                     join_key_index.normalize_index_expression(
                         join_key_index.blank_key_slot_expression(T_RIGHT, ["t"]))}, built
    pg.execute(text("SET enable_seqscan = off"))
    key = join_into._folded(right_model.t, None, map_overlay.key_time_zone(T_RIGHT, "t"))
    from sqlalchemy import select

    plan = "\n".join(r[0] for r in pg.execute(text("EXPLAIN " + str(
        select(right_model.row_id).where(key == KEY).compile(pg.get_bind(), compile_kwargs={"literal_binds": True})))))
    assert "uq_vjoin_%s" % T_RIGHT in plan, plan
    pg.execute(text("RESET enable_seqscan"))


@pytest.mark.pg
@pytest.mark.parametrize("session_zone", ["UTC", "Asia/Seoul"])
def test_a_naive_time_written_is_stored_as_its_key_instant_in_any_session_zone(pg, pg_engine, session_zone):
    """The session reads a naive text in ITS zone; the door hands it the declared one's offset first, so the stored
    instant is the key's - 08-13T15:03Z - under a UTC session and a Seoul one alike."""
    pg.execute(text("SET TIME ZONE '%s'" % session_zone))
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(pg, T_RIGHT, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"lot": "L1", "t": "2026-08-14 00:03", "v": "x"},
                                      source_name="parser_a", updated_by="t")]))
        pg.commit()
    with pg_engine.connect() as conn:
        stored = conn.execute(text('SELECT t FROM "%s"."%s"' % (PG_TEST_SCHEMA, T_RIGHT))).scalar()
    assert stored == INSTANT, (session_zone, stored)
    assert crud.key_part(T_RIGHT, "t", stored) == crud.key_part(T_RIGHT, "t", "2026-08-14 00:03") == KEY


@pytest.mark.pg
def test_a_naive_time_written_into_a_text_column_keeps_its_bytes_and_its_key(pg, pg_engine):
    """A TEXT column declared datetime: PostgreSQL does not read it, so the door leaves the person's text as written
    (the lead, after 3ea1ae778) - and its key is still the instant every other spelling keys to."""
    pg.execute(text("SET TIME ZONE 'UTC'"))
    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(pg, T_LEFT, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"lot": "L1", "t": "2026-08-14 00:03"},
                                      source_name="parser_a", updated_by="t")]))
        pg.commit()
    with pg_engine.connect() as conn:
        stored = conn.execute(text('SELECT t FROM "%s"."%s"' % (PG_TEST_SCHEMA, T_LEFT))).scalar()
    assert stored == "2026-08-14 00:03", stored
    assert crud.key_part(T_LEFT, "t", stored) == KEY
