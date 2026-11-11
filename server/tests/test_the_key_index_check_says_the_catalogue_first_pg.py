# -*- coding: utf-8 -*-
"""migrations/add_business_key_unique_index.py, read-only: the catalogue's answer - each table's key indexes and its
row estimate - is printed before the duplicate census reads the whole table (owner 11-11: 70M rows on an HDD; the
first line answers «does a key index stand» and Ctrl+C keeps it). Three tables on PostgreSQL (scratch schema): a
valid unique index, none, an INVALID one."""
import pytest
from sqlalchemy import text

import migrations.add_business_key_unique_index as mig
from tests.test_business_key_unique_migration import CatalogueConn, FakeEngine


@pytest.fixture()
def conn(pg_engine):
    with pg_engine.begin() as c:
        for name in ("kc_ok", "kc_none", "kc_bad"):
            c.execute(text(f'CREATE TABLE "{name}" (row_id varchar PRIMARY KEY, business_key_val varchar, a text)'))
        c.execute(text('CREATE UNIQUE INDEX "uq_bk_kc_ok" ON "kc_ok" (business_key_val)'))
        c.execute(text('CREATE INDEX "ix_kc_ok_a" ON "kc_ok" (a)'))                       # not a key index
        c.execute(text('CREATE UNIQUE INDEX "uq_bk_kc_bad" ON "kc_bad" (business_key_val)'))
        c.execute(text("UPDATE pg_index SET indisvalid = false WHERE indexrelid = "
                       "(SELECT oid FROM pg_class WHERE relname = 'uq_bk_kc_bad' AND relnamespace = "
                       "(SELECT oid FROM pg_namespace WHERE nspname = current_schema()))"))
    with pg_engine.connect() as c:
        yield c
    with pg_engine.begin() as c:
        for name in ("kc_ok", "kc_none", "kc_bad"):
            c.execute(text(f'DROP TABLE IF EXISTS "{name}"'))


def test_each_table_says_its_key_indexes_from_the_catalogue(conn):
    lines = {t: mig.key_catalogue_line(t, mig.key_catalogue(conn, t)) for t in ("kc_ok", "kc_none", "kc_bad")}
    assert "uq_bk_kc_ok (unique: business_key_val)" in lines["kc_ok"] and "ix_kc_ok_a" not in lines["kc_ok"]
    assert "a lookup by key reads the whole table" in lines["kc_none"]
    assert "uq_bk_kc_bad (unique, INVALID - serves nothing: business_key_val)" in lines["kc_bad"]


def test_the_catalogue_lines_come_before_the_census(monkeypatch, capsys):
    monkeypatch.setattr(mig, "tables_with_business_key", lambda conn: ["t1", "t2"])
    monkeypatch.setattr(mig, "key_catalogue", lambda conn, t: {"rows": 70_000_000, "indexes": []})

    def census(conn, t):
        print(f"CENSUS {t}")
        return {"table": t, "rows": 0, "null_keys": 0, "dup_keys": 0, "surplus": 0, "sample": [], "verdict": None,
                "index_name": mig.unique_index_name(t)}

    monkeypatch.setattr(mig, "plan_table", census)
    conn = CatalogueConn(redundant_rows=[])
    mig.run(apply=False, engine=FakeEngine(conn), readonly_engine=FakeEngine(conn))
    out = capsys.readouterr().out
    assert out.index("t2: ~70,000,000 rows") < out.index("CENSUS t1"), out
