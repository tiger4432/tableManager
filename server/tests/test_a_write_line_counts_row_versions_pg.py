"""Lead 11-09 (owner «autovacuum ... dead 수십만 행»): on PostgreSQL the write line says, per table, the row versions its
committed transaction made - inserted / updated (HOT) / deleted, asked on its connection just before COMMIT
(pg_stat_xact_user_tables). A new batch inserts its rows - put bare by the claim, then written by the merge (A 11-11:
one more row version a new row than the old write's); the same batch again updates nothing; a changed batch updates
its rows. This scratch table keeps no lines: its rows are t's own (lead 11-11 ㄴ)."""
import os
import sys

import pytest
from sqlalchemy import MetaData, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from conftest import PG_TEST_SCHEMA, _declared_as_test_database, _resolve_pg_test_url   # noqa: E402
from database import crud, models, schemas                          # noqa: E402
from maps import alignment_batch_counts                              # noqa: E402

pytestmark = pytest.mark.pg

T = "pgqa_tx_line"
CONFIG = {"business_key": "k", "composite_key_source": ["k"],
          "column_types": {"k": "string", "a": "string", "b": "string"}}


def _batch(value, rows=4):
    return schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="K%d" % i, source_name="tx.csv",
                                  updates={"k": "K%d" % i, "a": value, "b": value}) for i in range(rows)])


@pytest.fixture(scope="module")
def rounds(pg_engine):
    from sqlalchemy.orm import sessionmaker

    url, _ = _resolve_pg_test_url()
    models.init_dynamic_models({T: CONFIG})
    crud.TABLE_CONFIG[T] = CONFIG
    scratch = MetaData(schema=PG_TEST_SCHEMA)
    models.DYNAMIC_TABLES[T].__table__.to_metadata(scratch, schema=None)
    emptied = ", ".join('"%s"."%s"' % (PG_TEST_SCHEMA, t) for t in
                        ("cell_sources", "cell_overwrites", "audit_logs", "database_outbox", T))
    Session = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
    out = {}
    with _declared_as_test_database(url):
        scratch.create_all(pg_engine)
        db = None
        try:
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            for name, value in (("new", "x"), ("same", "x"), ("changed", "y")):
                db = Session()
                with alignment_batch_counts.counting_group() as summary:
                    crud.apply_batch_updates(db, T, _batch(value))
                    db.commit()
                out[name] = summary()
                db.close()
        finally:
            if db is not None:
                db.close()
            with pg_engine.begin() as conn:
                conn.execute(text("TRUNCATE %s RESTART IDENTITY CASCADE" % emptied))
            scratch.drop_all(pg_engine, tables=[scratch.tables["%s.%s" % (PG_TEST_SCHEMA, T)]])
            crud.TABLE_CONFIG.pop(T, None)
    return out


def test_a_new_batch_inserts_its_rows(rounds):
    rows = rounds["new"]["transaction"]["rows"]
    assert rows[T][:2] == [4, 4], rows                          # the claim's bare row, the merge's values
    assert " %s +4 ~4" % T in alignment_batch_counts.write_steps_text(rounds["new"])


def test_the_same_batch_again_leaves_no_dead_version(rounds):
    rows = rounds["same"]["transaction"]["rows"]
    assert all(n[1] == 0 and n[3] == 0 for n in rows.values()), rows


def test_a_changed_batch_updates_its_rows(rounds):
    rows = rounds["changed"]["transaction"]["rows"]
    assert rows[T][:2] == [0, 4], rows                          # a and b on 4 rows; the key k did not change
