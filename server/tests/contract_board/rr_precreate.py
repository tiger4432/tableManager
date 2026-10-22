"""Every product table of the CURRENT worktree code made in ASSY_SCRATCH_SCHEMA. The ledger's own DDL FIRST (its tables
in their real types - create_all would make them from the ORM shape and the DDL then trips on them), then create_all with
the search_path that schema ALONE - so it never sees a public table of the same name and skips it
(scratch-schema-leaks-to-public-via-create-all). Run with cwd = <worktree>/server and the launcher's env. One PRECREATE line."""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from sqlalchemy import create_engine, text                           # noqa: E402

schema = os.environ["ASSY_SCRATCH_SCHEMA"]
engine = create_engine(os.environ["DATABASE_URL"], connect_args={"options": "-csearch_path=%s" % schema})
with engine.connect() as conn:
    assert conn.execute(text("SELECT current_schema()")).scalar() == schema
from database import models                                          # noqa: E402
from database.database import Base                                   # noqa: E402

if os.environ.get("PRECREATE_LEDGER"):
    from datetime import datetime, timezone
    from ledger import schema as ledger_schema
    # its DDL calls a function that lives in public; its tables are not in public (asserted), so they land here
    with_public = create_engine(os.environ["DATABASE_URL"], connect_args={"options": "-csearch_path=%s,public" % schema})
    with with_public.connect() as conn:
        for name in ("ledger_events", "ledger_source_row_ref", "ledger_translator_cursor"):
            assert conn.execute(text("SELECT to_regclass(:n)"), {"n": "public." + name}).scalar() is None, name
    raw = with_public.raw_connection()
    try:
        ledger_schema.ensure_schema(raw)
        raw.commit()
        ledger_schema.ensure_partition(raw, datetime.now(timezone.utc))
        raw.commit()
    finally:
        raw.close()
tables = json.load(open(os.path.join(os.environ["ASSY_DATA_ROOT"], "config", "table_config.json"), encoding="utf-8"))
models.init_dynamic_models({k: v for k, v in tables.items() if not k.startswith("_")})
Base.metadata.create_all(engine)
with engine.connect() as conn:
    made = conn.execute(text("SELECT count(*) FROM pg_tables WHERE schemaname = :s"), {"s": schema}).scalar()
print("PRECREATE %d table(s) in %s, shadowing a product table: []" % (made, schema))
