"""Lead 11-09 (owner «필요한 로그는 빨리 다 지어»): the chunk line and the chain group line say the write's transaction -
statements, seconds held from the first write to the commit's end, the commit, database seconds by the table a statement
writes, the cells offered beside the cells changed - from the engine's own events, inside a counting scope only; per table
row versions on PostgreSQL (its PG file). The counters are silent alone: one line, the write goes on."""
import logging

import pytest
from sqlalchemy import text

from database import crud, models, schemas
from maps import alignment_batch_counts

T = "zztx_line"
CONFIG = {"business_key": "k", "column_types": {"k": "string", "a": "string", "b": "string"}}


@pytest.fixture
def table(db_session):
    crud.TABLE_CONFIG[T] = CONFIG
    models.init_dynamic_models({T: CONFIG})
    models.create_missing_dynamic_tables(db_session.get_bind())
    yield db_session
    db_session.rollback()
    crud.TABLE_CONFIG.pop(T, None)


def _batch(value, rows=3):
    return schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="K%d" % i, source_name="tx.csv",
                                  updates={"k": "K%d" % i, "a": value, "b": value}) for i in range(rows)])


def _written(db, batch):
    with alignment_batch_counts.counting_group() as summary:
        crud.apply_batch_updates(db, T, batch)
        db.commit()
    return summary()


def test_a_write_says_its_statements_its_hold_its_commit_and_its_tables(table):
    said = _written(table, _batch("x"))
    tx = said["transaction"]
    assert tx["statements"] > 0 and tx["held"] > 0 and tx["commit"] >= 0
    assert {"cell_sources", T, alignment_batch_counts.READS} <= set(tx["db"]), tx["db"]
    assert tx["rows"] == {}, "per-table row versions are PostgreSQL's"
    assert said["write_counts"]["cells offered"] == [9, "cells offered"]
    line = alignment_batch_counts.write_steps_text(said)
    assert " · 9 cells offered" in line and " · TRANSACTION %d statement(s) · held " % tx["statements"] in line
    assert " cell_sources " in line.split(" · db")[1]


def test_nothing_is_counted_outside_a_scope_and_an_unchanged_write_holds_nothing(table):
    crud.apply_batch_updates(table, T, _batch("x"))
    table.commit()
    assert alignment_batch_counts._tx() is None
    again = _written(table, _batch("x"))["transaction"]
    assert again["held"] == 0.0 and set(again["db"]) == {alignment_batch_counts.READS}, again


def test_the_counters_fail_alone(table, monkeypatch, caplog):
    def broken(statement):
        raise RuntimeError("counter broke")

    monkeypatch.setattr(alignment_batch_counts, "_WRITTEN", type("W", (), {"match": staticmethod(broken)}))
    with caplog.at_level(logging.WARNING, logger=alignment_batch_counts.logger.name):
        said = _written(table, _batch("y"))
    assert said["transaction"] is None
    assert [r.getMessage() for r in caplog.records if r.name == alignment_batch_counts.logger.name] == [
        "[Counts] the write's transaction counts stopped at a statement (RuntimeError: counter broke) - "
        "the write is unaffected"]
    assert table.execute(text('SELECT count(*) FROM "%s" WHERE a = %s' % (T, "'y'"))).scalar() == 3
    assert alignment_batch_counts.write_steps_text(said).endswith("cells offered"), "no TRANSACTION part"
