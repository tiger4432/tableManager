# -*- coding: utf-8 -*-
"""A join whose source rows match a great many left rows is answered and written page by page
(총괄 8934fa36f · e10c58e5e · a4bc9af48).

Production: one source file's 1,000 rows matched hundreds of thousands of left rows, and the
join ran one SELECT and one write of all of them - an active query for more than five minutes
and a chain that showed wedged.

- the join proposes one page and says there is more; the write seat asks the next page only after
  the page before it was written, and the rules after it write after its last page
- the left ids are drawn in pages of keys through the left key's lookup index
"""
import os
import sys

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

import mapper_sdk                                                            # noqa: E402
from chain import ingestion_worker as worker                                 # noqa: E402
from chain import join_into, keyset_scan, rule_shape                         # noqa: E402
from database import crud, models, schemas                                   # noqa: E402
from database.database import Base                                          # noqa: E402
from maps import alignment_batch_counts                                      # noqa: E402

LEFT, RIGHT = "wide_left_log", "wide_right_attribution"
TABLES = {
    LEFT: {"business_key": "log_key", "composite_key_source": ["log_key"],
           "column_types": {"log_key": "string", "job": "string", "lot_confirmed": "string"},
           "display_columns": ["log_key", "job", "lot_confirmed"]},
    RIGHT: {"business_key": "job", "composite_key_source": ["job"],
            "column_types": {"job": "string", "lot": "string"},
            "display_columns": ["job", "lot"]},
}
DECLARATION = {
    "name": "wide_lot_from_attribution", "on": {"table": RIGHT}, "into": {"table": LEFT},
    "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"}],
                                        "take": [{"from": "lot", "into": "lot_confirmed"}]}},
}
PAGE = 10


def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)()


@pytest.fixture(autouse=True)
def _tables():
    yield
    for name in TABLES:
        crud.TABLE_CONFIG.pop(name, None)


def _push(db, table, rows):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(row), source_name="seed", updated_by="wide")
        for row in rows]))
    db.commit()


def _rules():
    return rule_shape.expand_declaration(DECLARATION, crud.TABLE_CONFIG)[0]


def _run(db, rules, on, monkeypatch, fail_on_write=None):
    """The real group seat over the real outbox rows of `on`; -> (ok, left writes, stages)."""
    writes, stages = [], []
    real = crud.apply_batch_updates

    def counting(session, table, batch, *a, **k):
        if table == LEFT:
            writes.append(len(batch.updates))
            if fail_on_write and len(writes) == fail_on_write:
                raise RuntimeError("the write of page %d failed" % fail_on_write)
        return real(session, table, batch, *a, **k)
    monkeypatch.setattr(crud, "apply_batch_updates", counting)
    monkeypatch.setattr(alignment_batch_counts.heartbeat, "progress", stages.append)
    events = db.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == on, models.DatabaseOutbox.processed_chain.is_(False)
    ).all()
    assert events, "no outbox event to run - the cell would prove nothing"
    with alignment_batch_counts.counting_group():
        ok, _error, _broadcasts = worker._process_chain_transaction_group_sync(
            "tx-wide", events, db, rules)
    monkeypatch.setattr(crud, "apply_batch_updates", real)
    if not ok:
        db.rollback()
    return ok, writes, stages


def _cells(db):
    left = models.DYNAMIC_TABLES[LEFT]
    return {r.log_key: r.lot_confirmed for r in db.query(left).all()}


def _seed_wide(db, n=35):
    _push(db, LEFT, [{"log_key": "L-%03d" % i, "job": "J-W"} for i in range(n)])
    _push(db, RIGHT, [{"job": "J-W", "lot": "LOT-W"}])


def test_a_wide_fan_out_is_written_page_by_page_and_ends_as_one_write_would(monkeypatch):
    results = {}
    for size in (PAGE, 1000):
        monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", size)
        db = _db()
        _seed_wide(db)
        ok, writes, stages = _run(db, _rules(), RIGHT, monkeypatch)
        assert ok
        results[size] = (writes, stages, _cells(db))
        db.close()

    paged_writes, paged_stages, paged_cells = results[PAGE]
    assert paged_writes == [10, 10, 10, 5], "one write per page, each its own commit"
    assert results[1000][0] == [35]
    assert paged_cells == results[1000][2], "the pages end where one write ends, cell by cell"
    assert set(paged_cells.values()) == {"LOT-W"}
    # each page's SELECT and each page's write enter a stage - the claim beats per page
    write_stage = "write:%s" % LEFT
    assert paged_stages.count(write_stage) == 4
    after_first = paged_stages[paged_stages.index(write_stage) + 1:]
    assert after_first.count("mapper") == 3, "pages two to four were read without a beat"


def test_a_first_page_with_nothing_to_write_does_not_drop_the_rest(monkeypatch):
    """The `:target` side: the first page's rows have no right row, the rest do."""
    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", PAGE)
    db = _db()
    _push(db, RIGHT, [{"job": "J-W", "lot": "LOT-W"}])
    db.query(models.DatabaseOutbox).update({"processed_chain": True})
    db.commit()
    _push(db, LEFT, [{"log_key": "L-%03d" % i, "job": "J-NONE" if i < PAGE else "J-W"}
                     for i in range(25)])

    ok, writes, _stages = _run(db, _rules(), LEFT, monkeypatch)

    assert ok
    cells = _cells(db)
    assert sum(1 for v in cells.values() if v == "LOT-W") == 15, cells
    assert writes == [10, 5], writes


def _other(db, payloads, rule=None):
    """Another rule writing the SAME cell of every left row, in the chain's layer."""
    left = models.DYNAMIC_TABLES[LEFT]
    return {"updates": [
        {"row_id": r.row_id, "updates": {"lot_confirmed": "OTHER"},
         "source_name": join_into.CHAIN_LAYER, "updated_by": "wide_other"}
        for r in db.query(left).all()]}


@pytest.mark.parametrize("join_first", [True, False])
def test_the_later_rule_still_writes_last_on_every_page(monkeypatch, join_first):
    """총괄 e10c58e5e ③: 「같은 표 같은 칸이면 규칙 순서로 마지막이 이김」 on every row."""
    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", PAGE)
    monkeypatch.setitem(mapper_sdk.MAPPER_REGISTRY, "wide_other", _other)
    db = _db()
    _seed_wide(db)
    join = _rules()[0]
    other = {"name": "wide_other", "enabled": True, "trigger_table": RIGHT,
             "target_table": LEFT, "mapper": "wide_other", "is_batch": True}

    ok, writes, _stages = _run(db, [join, other] if join_first else [other, join], RIGHT,
                               monkeypatch)

    assert ok and len(writes) >= 4, writes
    expected = "OTHER" if join_first else "LOT-W"
    assert set(_cells(db).values()) == {expected}, _cells(db)


def test_a_group_that_fails_between_pages_runs_again_to_the_same_cells(monkeypatch):
    """Pages already written stay (each committed); running the group again - what a replay
    does - ends where one write ends, and the pages already written are no-ops."""
    monkeypatch.setattr(keyset_scan, "DEFAULT_CHUNK_SIZE", PAGE)
    db = _db()
    _seed_wide(db)

    ok, _writes, _stages = _run(db, _rules(), RIGHT, monkeypatch, fail_on_write=3)
    assert not ok
    half = _cells(db)
    assert sum(1 for v in half.values() if v == "LOT-W") == 20, "pages one and two stayed"
    logs_after_first = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == LEFT,
        models.AuditLog.source_name == join_into.CHAIN_LAYER).count()

    ok, _writes, _stages = _run(db, _rules(), RIGHT, monkeypatch)
    assert ok
    assert set(_cells(db).values()) == {"LOT-W"}
    logs = db.query(models.AuditLog).filter(
        models.AuditLog.table_name == LEFT,
        models.AuditLog.source_name == join_into.CHAIN_LAYER).count()
    assert logs - logs_after_first == 15, "the pages written before the failure changed again"


# ---------------------------------------------------------------------------
# PostgreSQL: keys by the ten thousand, and the lookup index
# ---------------------------------------------------------------------------

TWO = {"name": "wide_two_keys", "on": {"table": RIGHT}, "into": {"table": LEFT},
       "derive": {"kind": "join", "join": {"on": [{"left": "job", "right": "job"},
                                                  {"left": "log_key", "right": "lot"}],
                                           "take": [{"from": "lot", "into": "lot_confirmed"}]}}}


def _pg(pg_engine):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=pg_engine)
    models.sync_dynamic_tables_schema(pg_engine)
    return sessionmaker(bind=pg_engine)()


def _insert(db, table, rows):
    model = models.DYNAMIC_TABLES[table]
    db.execute(model.__table__.insert(), rows)
    db.commit()


@pytest.mark.pg
def test_two_column_keys_by_the_ten_thousand_are_asked_in_pages(pg_engine):
    """One tuple IN of 20,000 two-column keys is a statement PostgreSQL refuses to plan
    (StatementTooComplex, measured). The keys go in pages; every left row still gets its value."""
    db = _pg(pg_engine)
    try:
        n = 20000
        _insert(db, RIGHT, [{"row_id": "R%05d" % i, "business_key_val": "J%05d" % i,
                             "job": "J%05d" % i, "lot": "K%05d" % i} for i in range(n)])
        _insert(db, LEFT, [{"row_id": "L%05d" % i, "business_key_val": "K%05d" % i,
                            "log_key": "K%05d" % i, "job": "J%05d" % i} for i in range(n)])
        rule = rule_shape.expand_declaration(TWO, crud.TABLE_CONFIG)[0][0]

        result = join_into.propose(db, rule, ["R%05d" % i for i in range(n)])
        written = len(result["updates"])
        while result.get("next_page") is not None:
            result = result["next_page"]()
            written += len(result["updates"])

        assert written == n
    finally:
        db.rollback()
        db.close()


@pytest.mark.pg
def test_the_left_rows_are_selected_through_the_lookup_index(pg_engine, monkeypatch):
    """The index work builds the left key's lookup index, and a page of keys is answered
    through it - an index or bitmap scan, whatever its name."""
    from chain import synthesis, unique_key

    db = _pg(pg_engine)
    try:
        _insert(db, RIGHT, [{"row_id": "R%04d" % i, "business_key_val": "J%04d" % i,
                             "job": "J%04d" % i, "lot": "LOT"} for i in range(2000)])
        _insert(db, LEFT, [{"row_id": "L%06d" % i, "business_key_val": "K%06d" % i,
                            "log_key": "K%06d" % i, "job": "J%04d" % (i % 2000)}
                           for i in range(40000)])
        rules = _rules()
        monkeypatch.setattr(worker, "read_rules_document",
                            lambda *a, **k: {"rules": [DECLARATION]})
        unique_key.forget()

        worker._ensure_declared_indexes_sync(rules, lambda: sessionmaker(bind=pg_engine)())

        db.execute(text("ANALYZE %s" % LEFT))
        spec = join_into.join_spec(rules[0])
        left_model, right_model = join_into._models(spec, LEFT)
        wheres = join_into._left_rows_for_reference(
            db, spec, left_model, right_model, ["R%04d" % i for i in range(100)], LEFT)
        from sqlalchemy.dialects import postgresql
        sql = str(select(left_model.row_id).where(wheres[0]).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
        plan = "\n".join(r[0] for r in db.execute(text("EXPLAIN " + sql)))
        assert "Index Scan" in plan or "Bitmap Index Scan" in plan, plan
        assert "Seq Scan" not in plan, plan
    finally:
        db.rollback()
        db.close()
        unique_key.forget()
        synthesis  # noqa: B018  (the seat under test reads it)


@pytest.mark.pg
def test_a_lookup_index_no_join_needs_is_taken_back(pg_engine):
    """An index lives as long as the join that needs it (S-248) - the left lookup index too."""
    from chain import unique_key
    from chain.join_key_index import LOOKUP_PREFIX

    db = _pg(pg_engine)
    index = LOOKUP_PREFIX + "wide_left_log_gone"
    try:
        db.execute(text('CREATE INDEX "%s" ON %s (job)' % (index, LEFT)))
        db.commit()
        required = {name for _t, name in unique_key.product_indexes(db) if name != index}
        unique_key.forget_retractions()

        report = unique_key.retract_unrequired_once(db, required)

        assert index in report["dropped"], report
    finally:
        db.rollback()
        db.close()
        unique_key.forget_retractions()
