"""Retire the old graph branch's STORAGE: drop `graph_nodes`, `graph_edges` and
`graph_sync_state`. No archive.

RULING
------
R-2026-08-14-H (docs/process/LEDGER_RULINGS.md), product owner, 2026-08-14:
"실측할 거 없고 그냥 기존 그래프는 날려." The remaining gate of the earlier
retirement plan (prove the ledger graph view is really in use before dropping the
storage) was EXPLICITLY WAIVED by the owner, so this script does not re-open it.

WHAT DIES AND WHAT LIVES
------------------------
Dies: the pipeline that kept a SECOND COPY of the source tables - extract →
materialize → store. The measurement behind the ruling: `graph_sync_worker.py`
carries zero `ledger` references and `server/ledger/` carries zero graph coupling,
i.e. two branches read the same source tables and did not know about each other.
The ledger (`ledger_events`) is the instance layer of the ontology and
`vocabulary.py` is the type layer; the old pipeline was a third, redundant copy.

Lives: the graph VIEWER (`client2/graph.html` + `src/graph_viewer.js`). It is not
being deleted - it is being ported to read the ledger walk. That is why this
script drops tables and touches no client file.

WHY THERE IS NO ARCHIVE
-----------------------
Re-confirmed by the owner in the ruling. These three tables hold DERIVED data:
every row was minted from a source table that still exists and is untouched here.
Archiving a derivation is archiving the output of a function whose input you kept.
The reverse script restores the SHAPE; nothing restores the rows, and nothing
needs to.

  ⚠️ One caveat that is NOT covered by "it is all derived": `graph_sync_state`
  holds `last_outbox_id`, the materializer's cursor. That single number is the only
  non-derived value here. It is deliberately dropped too - a cursor for a consumer
  that no longer exists is not state, it is litter. If the branch were ever
  revived, the honest restart is a full resync, not a resumed cursor.

USAGE
-----
    conda run -n assy_manager python server/migrations/drop_graph_storage.py
    conda run -n assy_manager python server/migrations/drop_graph_storage.py --apply \
        --i-accept-writing-to-owner-database

Default is a DRY RUN: it counts, prints, and drops nothing. The two flags are
separate on purpose - `--apply` says "write", the long flag says "and I know this
is the owner's working database". The long flag is the same spelling the seed
scripts use (`seed_syn_lot_excursion.py:321` `guard_database`), because one
mechanism for "you are about to write to `assy_manager`" is the whole point of
having named it once.

Exit code is 0 when every target ended up absent (dropped, or already gone).

REVERSE
-------
`server/migrations/drop_graph_storage_reverse.sql` recreates the three tables
EMPTY, with the column set and indexes taken from `server/database/models.py`.
It restores the shape so a revived branch can start resyncing; it cannot bring
rows back.

  🔴 THE REVERSE SCRIPT IS NOT ENOUGH TO REVIVE THE BRANCH, and pretending
  otherwise is how a half-revival happens. The same change that prepared this
  drop also closed the paths that would have refilled these tables. To actually
  come back you must undo all of it:
    1. `server/main.py`  - `_graph_branch_retired()` raises at the top of all
       seven `/graph/*` + `/api/graph/sync` routes, and the boot
       `create_all` skips `RETIRED_GRAPH_TABLES`.
    2. `server/database/models.py` - `refresh_dynamic_models` no longer calls
       `ensure_graph_tables`.
    3. `server/run_auto_update.py` - the scheduler no longer sweeps orphans.
    4. `server/retroactive.py` - the `graph_orphans` admin operation is
       deregistered.
    5. `run_decoupled_app.py` + `server/scripts/dev_env/devenv.py` - the
       `run_graph_sync.py` child is gone from both stacks.
  Running only the reverse SQL gives you three empty tables that nothing writes
  to and nothing reads - which reads on screen as "the graph is empty" rather
  than "the graph is retired". That is precisely the dishonest state the ruling
  ordered the execution sequence to prevent.
"""
import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

import db_safety  # noqa: E402

# Order matters only for readability - there are no foreign keys between them
# (measured: the materializer joins in Python, never in SQL).
GRAPH_TABLES = ("graph_edges", "graph_nodes", "graph_sync_state")

# The database this script must not silently write to. Same spelling and same
# meaning as `db_safety.PRODUCTION_DB_NAMES` / the seed scripts' guard.
OWNER_DATABASES = ("assy_manager",)

READONLY_APPLICATION_NAME = "assy_drop_graph_storage_check"


def guard_database(conn, allow_owner, writing):
    """Refuse an unflagged write to the owner's working database.

    Copied in spelling from `server/scripts/seed_syn_lot_excursion.py:321` on
    purpose: the operator should meet ONE sentence for this class of refusal,
    not a per-script dialect.
    """
    name = conn.execute(text("SELECT current_database()")).scalar()
    if writing and name in OWNER_DATABASES and not allow_owner:
        raise SystemExit(
            "REFUSED: connected to '%s', the owner's working database, and this run "
            "would DROP three tables. Pass --i-accept-writing-to-owner-database only "
            "once the owner's approval exists. A dry run needs no flag." % name)
    return name


def survey(conn):
    """What is actually there, right now, on THIS database.

    Read before write, and report before deciding - a count taken on the build
    box is not a fact about the owner's box, which is the entire reason this
    prints instead of assuming.
    """
    rows = []
    for table in GRAPH_TABLES:
        present = conn.execute(
            text("SELECT to_regclass(:q)"), {"q": "public." + table}).scalar()
        if present is None:
            rows.append((table, None, None))
            continue
        n = conn.execute(text(f"SELECT count(*) FROM public.{table}")).scalar()
        size = conn.execute(
            text("SELECT pg_size_pretty(pg_total_relation_size(:q))"),
            {"q": "public." + table}).scalar()
        rows.append((table, n, size))
    return rows


def print_survey(rows, db_name):
    print(f"database: {db_name}")
    print("-" * 62)
    for table, n, size in rows:
        if n is None:
            print(f"  {table:<20} ABSENT (nothing to drop)")
        else:
            print(f"  {table:<20} {n:>12,} row(s)   {size}")
    print("-" * 62)


def run(apply=False, allow_owner=False, url=None):
    if apply:
        from database.database import engine as shared_engine
        engine = shared_engine if url is None else __import__(
            "sqlalchemy").create_engine(url)
        conn = engine.connect()
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    else:
        # 🔴 The dry run is read-only ENFORCED BY POSTGRES, not by this script
        # remembering not to write. `db_safety` owns that guard; see
        # `drop_redundant_layering_indexes.py` for why it does not get a second
        # spelling here.
        engine = db_safety.open_readonly_engine(
            url, application_name=READONLY_APPLICATION_NAME)
        conn = db_safety.open_readonly_connection(engine)

    try:
        db_name = guard_database(conn, allow_owner, writing=apply)
        rows = survey(conn)
        print_survey(rows, db_name)

        present = [t for t, n, _ in rows if n is not None]
        if not apply:
            print("\nDRY RUN - nothing was dropped.")
            if present:
                print("To drop, re-run with:")
                print("    --apply --i-accept-writing-to-owner-database")
            return {"dropped": [], "already_absent":
                    [t for t, n, _ in rows if n is None], "applied": False}

        dropped = []
        for table in GRAPH_TABLES:
            # RESTRICT, not CASCADE. Nothing was measured to depend on these three,
            # so anything CASCADE would have to remove is something this migration
            # did not foresee - and a drop must not silently destroy a dependency
            # nobody knew about.
            conn.execute(text(f"DROP TABLE IF EXISTS public.{table} RESTRICT"))
            # Ask the CATALOGUE, do not trust that the statement did not raise.
            still = conn.execute(
                text("SELECT to_regclass(:q)"), {"q": "public." + table}).scalar()
            if still is not None:
                print(f"  !! FAILED: {table} is still in the catalogue")
            else:
                dropped.append(table)
                print(f"  dropped: {table}")

        # Worded as a STATE, not as an action: this is idempotent, so on a second
        # run nothing was dropped and saying "dropped" would be a lie.
        print(f"\ndone: none of {', '.join(GRAPH_TABLES)} exist in '{db_name}'")
        print("reverse (shape only, no rows): "
              "server/migrations/drop_graph_storage_reverse.sql")
        return {"dropped": dropped, "already_absent": [], "applied": True}
    finally:
        if apply:
            conn.close()
        else:
            db_safety.close_readonly_connection(conn)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true",
                   help="actually drop. Without it the run is read-only.")
    p.add_argument("--i-accept-writing-to-owner-database", action="store_true",
                   dest="allow_owner",
                   help="required in addition to --apply when the target is "
                        "the owner's working database")
    p.add_argument("--url", default=None,
                   help="target database URL (default: the shared engine's)")
    args = p.parse_args(argv)
    out = run(apply=args.apply, allow_owner=args.allow_owner, url=args.url)
    return 0 if out is not None else 1


if __name__ == "__main__":
    sys.exit(main())
