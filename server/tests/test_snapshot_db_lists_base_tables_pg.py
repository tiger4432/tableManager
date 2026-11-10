"""dev_env/snapshot_db truncates and copies BASE tables only - a view (an operator view table, the ledger's views) is not one
(lead 11-11, A census: it TRUNCATEd views)."""
import importlib.util
import os

from sqlalchemy import text

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "dev_env", "snapshot_db.py")


def test_a_view_is_not_listed(pg_engine):
    spec = importlib.util.spec_from_file_location("snapshot_db", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE TABLE snap_base (row_id varchar PRIMARY KEY)"))
        conn.execute(text("CREATE VIEW snap_t AS SELECT row_id FROM snap_base"))
        try:
            schema = conn.execute(text("SELECT current_schema()")).scalar()
            listed = mod.list_tables(conn, schema)
            assert "snap_base" in listed and "snap_t" not in listed
        finally:
            conn.execute(text("DROP VIEW snap_t"))
            conn.execute(text("DROP TABLE snap_base"))
