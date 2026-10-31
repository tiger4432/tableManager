"""Lead 10-31 ② (C measured: of nine spellings of one moment in a string time column, the ledger read six and refused
three - «is not ISO 8601 … declare the format» - where the write door reads all nine): one time judgment. Text the
ledger's reader refuses and PostgreSQL reads is the moment PostgreSQL reads, on the source's declared zone - the
write door's judge (`crud.times_postgresql_reads`), asked once a page and held around the translation
(`roleframe.times_read`); the row's text is not replaced, so a source whose identity holds the time keeps its refs.

  the ledger   nine spellings, one moment - the follow-up, the re-translate and the declaration's preview; the
               re-translate writes nothing twice and the refs carry the text as it is
  Latest       the same nine, the same moment as the ledger's, none counted unread
  the order    a declared format is read first; a binding with one is not asked
  a binding    a time attribute declaring its timezone reads the table too
"""
import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from ledger import roleframe

SEOUL = timezone(timedelta(hours=9))
MOMENT = datetime(2026, 9, 30, 10, 0, tzinfo=SEOUL)
SPELLINGS = ["2026-09-30 10:00:00", "2026-09-30T10:00:00", "2026-09-30 10:00", "2026-09-30T10:00:00.000",
             "2026-09-30 10:00:00+09:00", "2026-09-30T01:00:00Z",
             "2026/09/30 10:00:00", "2026.09.30 10:00:00", "20260930 100000"]
ONLY_POSTGRESQL = SPELLINGS[6:]


def test_the_board_holds_both_kinds():
    assert [s for s in SPELLINGS if roleframe.unread_time_text(s)] == ONLY_POSTGRESQL, "CANARY: three only PG reads"


def test_a_declared_format_is_read_before_the_table():
    held = {("Asia/Seoul", "20260930 100000"): MOMENT + timedelta(hours=1)}
    with roleframe.times_read(held):
        assert roleframe.aware_time("20260930 100000", "Asia/Seoul", "p", fmt="%Y%m%d %H%M%S") == MOMENT
        assert roleframe.aware_time("20260930 100000", "Asia/Seoul", "p") == MOMENT + timedelta(hours=1), \
            "control: no format - the table"
    with pytest.raises(roleframe.RoleFrameError):
        roleframe.aware_time("20260930 100000", "Asia/Seoul", "p")          # nothing held: refused as before


def test_the_table_is_keyed_by_zone():
    with roleframe.times_read({("Asia/Seoul", "2026/09/30 10:00:00"): MOMENT}):
        with pytest.raises(roleframe.RoleFrameError):
            roleframe.aware_time("2026/09/30 10:00:00", "UTC", "p")      # another zone is another moment


def test_a_time_attribute_with_its_timezone_reads_the_table(tmp_path):
    """The value binding is read at the mapper, not where occurred_at is - the table reaches both; what is asked
    names the attribute's column, and a binding that declares a format is not asked."""
    from test_a_test_run_shows_the_atoms_its_rows_became import _document, _service
    from test_the_test_run_reads_until_it_has_a_molecule import _row
    from ledger import backfill, runtime_v2
    from ledger.setup import preview_selected_cursor_batch

    source = "lot_slot_wafer"
    document = _document()
    document["entities"]["wafer@1"]["attributes"] = ["moved_at"]
    document["sources"][source]["read"]["occurred_at"]["format"] = "%Y%m%d_%H%M%S"
    document["sources"][source]["bind"]["entities"] = {"wafer@1": {"attributes": {"moved_at": {
        "kind": "column", "column": "event_type", "timezone": "Asia/Seoul"}}}}
    setup, _index, _ = _service(tmp_path, document).active()
    plan = setup.snapshot.source_plans[source]
    frame = backfill._v2_frame([dict(_row(i), event_time="20261011_2136%02d" % i, event_type="2026/09/30 10:00:00")
                                for i in range(4)])
    assert roleframe.source_times_to_ask(plan, frame) == {"Asia/Seoul": {"2026/09/30 10:00:00"}}, \
        "the attribute's column, not the formatted occurred_at"
    with pytest.raises(roleframe.RoleFrameError):
        preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                      known_registrations=())
    with roleframe.times_read({("Asia/Seoul", "2026/09/30 10:00:00"): MOMENT}):
        preview = preview_selected_cursor_batch(setup, source, frame, runtime_v2.last_cursor(plan, frame),
                                                known_registrations=())
    said = json.dumps([a.object_payload for a in runtime_v2._screened_atoms(setup.snapshot, source, preview)],
                      default=str)
    assert "moved_at" in said and MOMENT.isoformat() in said.replace(" ", "T"), said


# --- the ledger, on PostgreSQL: the product's seats ------------------------------------------------------------------

@pytest.fixture(name="world")
def fixture_world(pg_engine, monkeypatch, tmp_path):
    from support import hold_world as hw

    tables = copy.deepcopy(hw.TABLES)
    tables[hw.OFFICIAL]["column_types"]["stamp"] = "string"
    tables[hw.OFFICIAL]["composite_key_source"] = hw.KEYS + ["stamp"]      # a row's ref is its key: it names the time
    source = copy.deepcopy(hw.LEDGER_SOURCE)
    # the time is in the identity and the key, and in no format
    source["read"] = {"identity": ["dt_job", "dt_x", "dt_y", "stamp"], "order_by": ["dt_job", "dt_x", "dt_y", "stamp"],
                      "occurred_at": {"column": "stamp", "timezone": "Asia/Seoul"}}
    monkeypatch.setattr(hw, "TABLES", tables)
    monkeypatch.setattr(hw, "LEDGER_SOURCE", source)
    for world in hw.build(pg_engine, monkeypatch, tmp_path):
        yield world


def _atoms(world):
    from ledger import schema
    from support import hold_world as hw

    with world["engine"].connect() as conn:
        return conn.execute(text("SELECT occurred_at, source_raw_ref FROM %s WHERE source_who = :s"
                                 % schema.LEDGER_TABLE), {"s": hw.SOURCE}).fetchall()


@pytest.mark.pg
def test_nine_spellings_are_one_moment_in_the_ledger_and_a_re_translate_writes_nothing_twice(world):
    import event_constants
    from database import crud, schemas
    from database.context import channel
    from ledger import backfill, followup
    from support import hold_world as hw

    with channel(event_constants.CHANNEL_API):
        crud.apply_batch_updates(world["db"], hw.OFFICIAL, schemas.GeneralUpdateBatch(updates=[
            schemas.GeneralUpdateItem(updates={"dt_job": "J", "dt_x": x, "dt_y": 1, "netdie": x, "stamp": spelling},
                                      source_name="user", updated_by="t")
            for x, spelling in enumerate(SPELLINGS, 1)]))
        world["db"].commit()
    with world["engine"].connect() as conn:
        stored = sorted(r[0] for r in conn.execute(text('SELECT stamp FROM "%s"' % hw.OFFICIAL)))
    assert stored == sorted(SPELLINGS), "CANARY: the text is stored as written"
    hw.run_chain(dict(world, rules=[]))                 # the outbox marked as the chain does; no rule here
    while followup.drain_outbox_once(world["engine"], world["setup"]) is not None:
        pass
    first = _atoms(world)
    assert len(first) == len(SPELLINGS), first
    assert {at for at, _ref in first} == {MOMENT}, first
    named = sorted(keys["stamp"] for _at, ref in first for _relation, keys in backfill._ref_row_keys(ref))
    assert named == sorted(SPELLINGS), "the refs name each row's text as written"

    out = backfill.rescope(world["engine"], world["setup"], hw.SOURCE, None, [], apply=True,
                           page_rows=backfill.RESCOPE_PAGE_ROWS, whole_source=True)
    again = _atoms(world)
    # withdrawn by the refs it remakes, written again: a ref that moved would leave the old atom standing beside it
    assert out["refused"] == {} and out["withdrawn"] == out["inserted"] == len(SPELLINGS), out
    assert sorted(again) == sorted(first), "the same atoms - nothing twice"

    reading = backfill.preview_first_batch(world["engine"], world["setup"], hw.SOURCE)
    assert reading.preview.refusals == () or list(reading.preview.refusals) == [], reading.preview.refusals
    assert reading.preview.molecule_count == len(SPELLINGS)


# --- Latest's $at: the same nine, the same moment --------------------------------------------------------------------

LATEST_SRC = "x1031_src"
LATEST_TABLES = {LATEST_SRC: {"business_key": "rid", "column_types": {"rid": "string", "lot": "string",
                                                                       "s": "string", "v": "string"}}}


@pytest.mark.pg
def test_latest_reads_the_nine_as_the_ledger_does(pg_session, monkeypatch, caplog):
    from types import SimpleNamespace

    import expression
    from chain.enrichment import mapper
    from database import crud, models
    from ledger import worker
    from ledger.setup_registry import OccurredAtPlan

    db = pg_session
    models.init_dynamic_models(LATEST_TABLES)
    monkeypatch.setattr(crud, "TABLE_CONFIG", {**crud.TABLE_CONFIG, **LATEST_TABLES})
    model = models.DYNAMIC_TABLES[LATEST_SRC]
    model.__table__.create(bind=db.get_bind(), checkfirst=True)
    try:
        for i, spelling in enumerate(SPELLINGS):
            db.add(model(row_id="r%d" % i, business_key_val="r%d" % i, rid="r%d" % i, lot="K", s=spelling,
                         v="S%d" % i))
        db.flush()
        plans = {"src": SimpleNamespace(relation=LATEST_SRC, runs=True, driver=SimpleNamespace(
            occurred_at=OccurredAtPlan(column="s", timezone="Asia/Seoul", basis=None), exclude_when=(),
            group_by=()))}
        monkeypatch.setattr(worker, "_compiled_setup", lambda world: SimpleNamespace(snapshot=SimpleNamespace(
            source_plans=plans)))
        seen = []
        run = expression.run
        monkeypatch.setattr(expression, "run", lambda compiled, rows, types: (seen.extend(rows),
                                                                              run(compiled, rows, types))[1])
        with caplog.at_level("WARNING", logger="Chain.enrichment_dedup"):
            mapper._aggregate_affected_keys(db, LATEST_SRC, ["lot"], {("K",): ("K",)},
                                            {"latest": {"expression": "Latest([v])"}})
    finally:
        db.rollback()
        model.__table__.drop(bind=db.get_bind(), checkfirst=True)
    unread = [r.getMessage() for r in caplog.records if "whose time the ledger cannot read" in r.getMessage()]
    assert unread == [], unread
    assert sorted(row["s"] for row in seen) == sorted(SPELLINGS), "CANARY: every row reached Latest"
    assert {row["$at"] for row in seen} == {MOMENT.timestamp() * 1000}, seen
