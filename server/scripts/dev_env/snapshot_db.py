"""Build / refresh the isolated snapshot database (default: assy_qa).

Not a clone. `bonding_map` alone is ~1.76M rows and `cell_sources` ~12.5M, so a
full copy is neither fast nor needed. What verification actually needs is copied:

  * every map registered in `wafer_map_metadata`, and the rows of its target
    table that belong to those maps
  * the plan tables (map_doe, map_doe_source, map_split_registry, transfer_plan*)
  * every small table in full
  * the layering tables (cell_sources / cell_overwrites) and audit_logs
    restricted to the rows actually copied
  * the graph store, so /graph/* serves something real

SAFETY - the source connection is opened READ ONLY at the PostgreSQL session
level and that guard is *self-tested* on every run (a deliberate write is
attempted and must fail) before a single row is read. A bug in this script
cannot write to production; it can only crash.

Idempotent: target tables are truncated and refilled, so re-running refreshes.

Usage:
    python server/scripts/dev_env/snapshot_db.py                   # defaults
    python server/scripts/dev_env/snapshot_db.py --target postgresql://...
    python server/scripts/dev_env/snapshot_db.py --full-copy-max-rows 50000
"""
import os
import sys
import time
import json
import argparse

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url

DEFAULT_SOURCE = "postgresql://postgres:admin@localhost:5432/assy_manager"
DEFAULT_TARGET = "postgresql://postgres:admin@localhost:5432/assy_qa"

CHUNK = 1000  # rows per round trip (10M-row discipline: never load a table whole)

# Tables intentionally left EMPTY in the snapshot.
#   database_outbox  - 2.9M rows of already-consumed events; a fresh env wants an
#                      empty queue, otherwise the chain/graph workers would replay
#                      production history on first start.
EMPTY_TABLES = {"database_outbox"}

# Row-scoped side tables: copied only for (table_name, row_id) pairs that made it
# into the snapshot, so they can never be larger than the data they describe.
# The value is a global row budget for the whole table (not per chunk).
ROW_SCOPED = {
    "cell_sources": 400_000,     # layering source rows: ~1 per (row, column)
    "cell_overwrites": 100_000,  # only cells a human actually pinned
    "audit_logs": 50_000,        # history, not state - newest N is enough
}


def log(msg):
    print(f"[snapshot] {msg}", flush=True)


# ---------------------------------------------------------------- source guard
def open_source_readonly(url):
    """Open the production connection and PROVE it cannot write.

    Returns (engine, connection). The connection has session-level read-only
    transaction characteristics; the guard is verified by attempting a write.
    """
    engine = create_engine(url, connect_args={
        "application_name": "assy_devenv_snapshot_readonly",
    })
    conn = engine.connect()
    conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
    conn.execute(text("SET default_transaction_read_only = on"))
    conn.commit()

    # Self-test: the guard must actually be live. A temp table touches no
    # production relation - PostgreSQL rejects the statement as read-only first.
    # Matched on SQLSTATE 25006 (read_only_sql_transaction), never on the message
    # text: the server speaks the OS locale, so string matching silently breaks.
    READ_ONLY_SQLSTATE = "25006"
    try:
        conn.execute(text("CREATE TEMP TABLE _devenv_readonly_probe (x int)"))
        conn.rollback()
        raise SystemExit(
            "ABORT: the source connection accepted a write. Refusing to run "
            "against production without a live read-only guard."
        )
    except SystemExit:
        raise
    except Exception as e:
        conn.rollback()
        pgcode = getattr(getattr(e, "orig", None), "pgcode", None)
        if pgcode != READ_ONLY_SQLSTATE:
            raise SystemExit(
                f"ABORT: read-only guard produced SQLSTATE {pgcode!r}, "
                f"expected {READ_ONLY_SQLSTATE}: {e}")
    log(f"source READ ONLY guard verified ({make_url(url).database})")
    return engine, conn


# ------------------------------------------------------------------- inventory
def list_tables(conn):
    return [r[0] for r in conn.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' ORDER BY table_name"))]


def columns_of(conn, table):
    return [r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"),
        {"t": table})]


def count_of(conn, table):
    return conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()


def json_columns_of(conn, table):
    """json/jsonb columns need explicit re-adaptation on the way back in.

    psycopg2 DECODES them on read (a json column yields a dict / list / str /
    int), and a decoded Python value cannot be bound straight into a json column:
    dicts raise "can't adapt type 'dict'", and a bare string like EQP_1 would be
    parsed as JSON and rejected. Every non-NULL value of these columns is wrapped
    in psycopg2.extras.Json before insert.
    """
    return {r[0] for r in conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name=:t "
        "AND data_type IN ('json','jsonb')"), {"t": table})}


# ------------------------------------------------------------------ target DDL
def ensure_target_database(target_url):
    """CREATE DATABASE if absent. Connects to the 'postgres' maintenance DB."""
    u = make_url(target_url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        exists = c.execute(text("SELECT 1 FROM pg_database WHERE datname=:d"),
                           {"d": u.database}).first()
        if not exists:
            c.execute(text(f'CREATE DATABASE "{u.database}"'))
            log(f"created database {u.database}")
        else:
            log(f"database {u.database} already exists")
    admin.dispose()


def build_target_schema(target_url):
    """Create the schema using the server's OWN bootstrap path.

    Same calls main.py makes at startup, so the snapshot cannot drift from what
    the isolated server expects. Reads table_config through server/paths.py, so
    running this with ASSY_DATA_ROOT set uses the isolated config.
    """
    import paths
    from database import models
    from database.database import engine as target_engine

    with open(paths.config_path("table_config.json"), encoding="utf-8") as f:
        table_config = json.load(f)
    models.init_dynamic_models(table_config)
    models.Base.metadata.create_all(bind=target_engine)
    try:
        models.sync_dynamic_tables_schema(target_engine)
    except Exception as e:
        log(f"WARN sync_dynamic_tables_schema: {e}")
    try:
        models.ensure_ingestion_checkpoint_table(target_engine)
    except Exception as e:
        log(f"WARN ensure_ingestion_checkpoint_table: {e}")
    log(f"target schema built from {paths.config_path('table_config.json')}")
    return target_engine


# ----------------------------------------------------------------------- copy
def copy_rows(src, dst, table, cols, where_sql, params, limit=None, order_by=None,
              json_cols=frozenset()):
    """Stream rows source -> target in CHUNK-sized batches. Returns rows copied."""
    from psycopg2.extras import Json
    collist = ", ".join(f'"{c}"' for c in cols)
    q = f'SELECT {collist} FROM "{table}"'
    if where_sql:
        q += f" WHERE {where_sql}"
    if order_by:
        q += f" ORDER BY {order_by}"
    if limit:
        q += f" LIMIT {int(limit)}"

    ins = text(f'INSERT INTO "{table}" ({collist}) VALUES '
               f'({", ".join(":" + c for c in cols)})')

    def adapt(row):
        d = dict(zip(cols, row))
        for c in json_cols:
            if d.get(c) is not None:
                d[c] = Json(d[c])
        return d

    total = 0
    res = src.execution_options(stream_results=True, yield_per=CHUNK).execute(text(q), params or {})
    while True:
        batch = res.fetchmany(CHUNK)
        if not batch:
            break
        dst.execute(ins, [adapt(row) for row in batch])
        dst.commit()
        total += len(batch)
    res.close()
    return total


def fix_sequences(dst, tables):
    """Re-point every serial/identity sequence past the copied max(id).

    Ids are copied verbatim (graph_edges.from_node/to_node reference
    graph_nodes.id), so the sequences must be advanced or the first insert in the
    isolated env collides on the primary key.
    """
    fixed = 0
    for t in tables:
        # pg_get_serial_sequence raises UndefinedColumn (not NULL) when the column
        # does not exist, so gate on information_schema first. Most dynamic tables
        # key on row_id and have no id at all.
        if "id" not in set(columns_of(dst, t)):
            continue
        seq = dst.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": t}).scalar()
        if not seq:
            continue
        dst.execute(text(
            f"SELECT setval('{seq}', COALESCE((SELECT MAX(\"id\") FROM \"{t}\"), 0) + 1, false)"))
        fixed += 1
    dst.commit()
    return fixed


# ------------------------------------------------------------------------ main
def run(args):
    t_start = time.time()

    # Pin the server's own engine (database/database.py reads this at import) to
    # the TARGET before any server module is imported. The production connection
    # below is opened explicitly and read-only; it never comes from this env var.
    os.environ["DATABASE_URL"] = args.target

    src_engine, src = open_source_readonly(args.source)

    ensure_target_database(args.target)
    build_target_schema(args.target)
    dst_engine = create_engine(args.target)
    dst = dst_engine.connect()

    src_tables = set(list_tables(src))
    dst_tables = set(list_tables(dst))
    shared = sorted(src_tables & dst_tables)
    log(f"tables: source={len(src_tables)} target={len(dst_tables)} shared={len(shared)}")

    only_src = sorted(src_tables - dst_tables)
    if only_src:
        log(f"NOTE not in target (skipped): {', '.join(only_src)}")

    # Wipe target so the run is idempotent. TRUNCATE ... CASCADE in one statement
    # so FK order does not matter. TARGET ONLY.
    quoted = ", ".join(f'"{t}"' for t in shared)
    dst.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    dst.commit()
    log(f"target truncated ({len(shared)} tables)")

    # -- table_config drives which tables carry map keys -----------------------
    import paths
    with open(paths.config_path("table_config.json"), encoding="utf-8") as f:
        table_config = json.load(f)

    # Registered maps: (target_table -> [map_id, ...])
    registered = {}
    if "wafer_map_metadata" in src_tables:
        for tt, mid in src.execute(text(
                "SELECT target_table, map_id FROM wafer_map_metadata "
                "WHERE target_table IS NOT NULL AND map_id IS NOT NULL")):
            registered.setdefault(tt, []).append(mid)
    log(f"registered maps: {sum(len(v) for v in registered.values())} across "
        f"{len(registered)} table(s)")

    report = {}
    copied_row_tables = []          # tables whose row_id set feeds the side tables

    for t in shared:
        if t in EMPTY_TABLES:
            report[t] = ("empty-by-design", 0)
            continue
        if t in ROW_SCOPED:
            continue                # handled after, needs the copied row set

        cols = [c for c in columns_of(src, t) if c in set(columns_of(dst, t))]
        if not cols:
            report[t] = ("no shared columns", 0)
            continue
        jcols = json_columns_of(src, t)

        n = count_of(src, t)
        cfg = table_config.get(t, {})
        map_cols = cfg.get("map_key_columns") or []
        map_ids = registered.get(t) or []

        if n <= args.full_copy_max_rows:
            got = copy_rows(src, dst, t, cols, None, None, json_cols=jcols)
            report[t] = (f"full ({n})", got)
        elif map_cols and map_ids:
            # map_pk convention: map_key_columns joined with '_' == map_id
            expr = " || '_' || ".join(f'"{c}"' for c in map_cols)
            got = copy_rows(src, dst, t, cols, f"({expr}) = ANY(:ids)", {"ids": map_ids},
                            json_cols=jcols)
            report[t] = (f"registered maps ({len(map_ids)}) of {n}", got)
        else:
            order = "created_at DESC" if "created_at" in cols else None
            got = copy_rows(src, dst, t, cols, None, None, limit=args.head_rows,
                            order_by=order, json_cols=jcols)
            report[t] = (f"newest {args.head_rows} of {n}", got)

        if "row_id" in cols and got:
            copied_row_tables.append(t)

    # -- side tables, scoped to what was actually copied -----------------------
    # row_id lists come from the TARGET (already bounded by the copy plan above),
    # so nothing here is proportional to production size.
    # Owners are visited smallest-first with a per-owner cap of
    # remaining_budget / remaining_owners (max-min fair share). Straight
    # first-come spending starves everything alphabetically late: a first cut of
    # this script gave core_defect_map 351k of the 400k cell_sources budget and
    # left eds_fail_map, dt_map and every map table after it with zero, so their
    # layering UI had nothing to show.
    owner_sizes = {o: dst.execute(text(f'SELECT COUNT(*) FROM "{o}"')).scalar()
                   for o in copied_row_tables}
    owners_by_size = sorted(copied_row_tables, key=lambda o: owner_sizes[o])

    for t, budget in ROW_SCOPED.items():
        if t not in shared:
            continue
        cols = [c for c in columns_of(src, t) if c in set(columns_of(dst, t))]
        jcols = json_columns_of(src, t)
        total = 0
        remaining = budget
        starved = []
        for idx, owner in enumerate(owners_by_size):
            left_owners = len(owners_by_size) - idx
            share = max(1, remaining // left_owners)
            got_owner = 0
            ids = [r[0] for r in dst.execute(text(f'SELECT row_id FROM "{owner}"'))]
            for i in range(0, len(ids), CHUNK):
                if got_owner >= share:
                    break
                got = copy_rows(
                    src, dst, t, cols,
                    "table_name = :tn AND row_id = ANY(:rids)",
                    {"tn": owner, "rids": ids[i:i + CHUNK]},
                    limit=share - got_owner,
                    order_by="id DESC",
                    json_cols=jcols,
                )
                got_owner += got
            if got_owner >= share:
                starved.append(owner)
            total += got_owner
            remaining -= got_owner

        note = f"fair share across {len(owners_by_size)} copied table(s)"
        if starved:
            note += f" [capped: {', '.join(starved)}]"
        report[t] = (note, total)

    # -- graph cursor: the snapshot's outbox is empty, so start the worker at 0 -
    if "graph_sync_state" in shared:
        dst.execute(text("DELETE FROM graph_sync_state"))
        dst.execute(text("INSERT INTO graph_sync_state (id, last_outbox_id) VALUES (1, 0)"))
        dst.commit()
        report["graph_sync_state"] = ("reset to 0 (empty outbox)", 1)

    n_seq = fix_sequences(dst, shared)
    log(f"sequences advanced: {n_seq}")

    dst.close(); dst_engine.dispose()
    src.close(); src_engine.dispose()

    elapsed = time.time() - t_start
    print("\n" + "=" * 72)
    print(f"SNAPSHOT COMPLETE  {make_url(args.source).database} -> "
          f"{make_url(args.target).database}   {elapsed:.1f}s")
    print("=" * 72)
    grand = 0
    for t in sorted(report):
        how, n = report[t]
        grand += n
        print(f"  {n:>9,}  {t:<32} {how}")
    print(f"  {grand:>9,}  TOTAL")
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", default=os.getenv("ASSY_SOURCE_DATABASE_URL", DEFAULT_SOURCE),
                   help="production URL, opened READ ONLY")
    p.add_argument("--target", default=os.getenv("ASSY_QA_DATABASE_URL", DEFAULT_TARGET))
    p.add_argument("--full-copy-max-rows", type=int, default=20_000,
                   help="tables at or below this row count are copied whole")
    p.add_argument("--head-rows", type=int, default=5_000,
                   help="rows kept from a large table that has no map key")
    args = p.parse_args()

    if make_url(args.source).database == make_url(args.target).database:
        raise SystemExit("ABORT: source and target are the same database.")
    sys.exit(run(args))


if __name__ == "__main__":
    main()
