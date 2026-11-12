"""The cell-source overhaul's migration: every declared table's old layers (cell_sources) copied into its line table
(<table>__lines), once, with the server stopped (owner 11-11). cell_sources is only read - nothing there is erased.

Usage
-----
    python server/scripts/copy_layers_to_lines.py                       preview: per table, rows and layers to copy
    python server/scripts/copy_layers_to_lines.py --check [--table <t> ...]   copy and roll back each page: cells
                                                                              whose lines merge to other than t, so far
    python server/scripts/copy_layers_to_lines.py --apply [--workers 4] [--table <t> ...] [--page 1000]

Per table: pages of `--page` rows, a commit each (`line_migration.copy_page`). Interrupted, run it again - each table
resumes after its last committed page (`copied_through`); a table already copied says so and is skipped.
The gate rides every page: the copied lines merged again must give what t shows. A page that does not is rolled
back and its table stops, naming the cells; fix and run again. The last page of a table writes its «copy» audit row.
`--workers N` copies N tables at once, one process each.

Refused while any product process (application_name assy_*) is connected to the database - stop the server first.
"""
import argparse
import multiprocessing
import os
import sys
import time

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlalchemy import func, select, text                            # noqa: E402
from sqlalchemy.orm import Session                                   # noqa: E402

from database import crud, line_migration, lines, models             # noqa: E402

#: the cells a stopped table names, at most
SHOWN = 5
#: seconds between a table's progress lines
SAY_EVERY = 10.0


def declared(only=()) -> dict:
    """{table: its declaration} of every declared table that keeps lines, or of `only`."""
    out = {t: cfg for t, cfg in (crud.TABLE_CONFIG or {}).items()
           if isinstance(cfg, dict) and lines.keeps_lines(t, cfg)}
    return {t: out[t] for t in only if t in out} if only else out


def servers_on(engine) -> list:
    """[(pid, application_name)] of the product's processes connected to this database, this process left out."""
    with engine.connect() as c:
        mine = c.execute(text("SELECT current_setting('application_name')")).scalar()
        return [tuple(r) for r in c.execute(text(
            "SELECT pid, application_name FROM pg_stat_activity WHERE datname = current_database() "
            "AND application_name LIKE 'assy\\_%' AND application_name <> :mine AND pid <> pg_backend_pid()"),
            {"mine": mine})]


def plan(engine, tables: dict) -> list:
    """Per table: its old layers and their rows, whether its lines are built and whether it is copied already."""
    cs = models.CellSource.__table__
    ab = lines.AuditBatch.__table__
    out = []
    with Session(bind=engine) as db:
        for table in sorted(tables):
            layers, rows = db.execute(select(func.count(), func.count(func.distinct(cs.c.row_id)))
                                      .where(cs.c.table_name == table)).one()
            built = lines.has_lines(db, table)
            done = built and db.execute(select(func.count()).select_from(ab).where(
                ab.c.table_name == table, ab.c.work_kind == line_migration.COPY_WORK)).scalar() > 0
            names = db.execute(select(cs.c.source_name).where(cs.c.table_name == table).distinct()).scalars().all()
            copies = sorted(n for n in names if crud.merged_layer_origin(n) is not None)
            out.append({"table": table, "layers": layers, "rows": rows, "built": built, "copied": done,
                        "copies": copies})
    return out


def copy_table(engine, table: str, cfg: dict, page: int, say=print) -> dict:
    """Copy one table to its end, a commit a page; stop at a page the gate refuses (rolled back)."""
    tx = "copy_lines:%s" % table
    cs = models.CellSource.__table__
    with Session(bind=engine) as db:
        rows = db.execute(select(func.count(func.distinct(cs.c.row_id))).where(cs.c.table_name == table)).scalar()
        after, copied, pages, mismatched = None, 0, 0, []
        started = said = time.perf_counter()
        while True:
            try:
                n, after_next = line_migration.copy_page(db, table, cfg, after, page, transaction_id=tx,
                                                         mismatched=mismatched)
            except line_migration.AlreadyCopied as already:
                db.rollback()
                say("%s: already copied (%s) - skipped" % (table, already))
                return {"table": table, "already": True}
            except ValueError as refused:                 # line_migration._copyable: this database cannot be copied
                db.rollback()
                say("REFUSED - %s" % refused)
                return {"table": table, "stopped": True, "refused": str(refused), "copied": copied}
            if mismatched:
                db.rollback()
                shown = "; ".join("%s.%s t=%r lines=%r" % m for m in mismatched[:SHOWN])
                say("%s: STOPPED - %d cell(s) where the copied lines do not give what t shows, first: %s - page "
                    "rolled back, the pages before it stay" % (table, len(mismatched), shown))
                return {"table": table, "stopped": True, "mismatched": mismatched, "copied": copied}
            db.commit()
            copied += n
            pages += 1
            after = after_next
            now = time.perf_counter()
            if after is None:
                say("%s: done - %d layer(s) copied in %.0f s" % (table, copied, now - started))
                return {"table": table, "copied": copied, "seconds": now - started}
            if now - said >= SAY_EVERY:
                said = now
                done = min(pages * page, rows)
                rate = done / (now - started)
                say("%s: %d / %d rows, %d layer(s) copied, about %.0f min left"
                    % (table, done, rows, copied, (rows - done) / rate / 60 if rate else 0))


def check_table(engine, table: str, cfg: dict, page: int, say=print) -> dict:
    """The copy run page by page and rolled back each page: how many cells' lines merge to other than what t shows,
    said after every page - so a stop at any time leaves a true sample. Nothing stays."""
    cs = models.CellSource.__table__
    with Session(bind=engine) as db:
        rows = db.execute(select(func.count(func.distinct(cs.c.row_id))).where(cs.c.table_name == table)).scalar()
        after, checked, mismatched = None, 0, []
        while True:
            page_mismatched = []
            try:
                _n, after = line_migration.copy_page(db, table, cfg, after, page, transaction_id="check_lines:%s" % table,
                                                     mismatched=page_mismatched)
            except line_migration.AlreadyCopied as already:
                db.rollback()
                say("%s: already copied (%s) - not checked" % (table, already))
                return {"table": table, "already": True}
            except ValueError as refused:
                db.rollback()
                say("REFUSED - %s" % refused)
                return {"table": table, "refused": str(refused)}
            db.rollback()
            mismatched += page_mismatched
            checked = rows if after is None else checked + page
            first = "; ".join("%s.%s t=%r lines=%r" % m for m in mismatched[:SHOWN])
            say("%s: %d / %d rows checked, %d mismatched so far%s" % (
                table, checked, rows, len(mismatched), (", first: " + first) if first else ""))
            if after is None:
                return {"table": table, "checked": checked, "mismatched": len(mismatched)}


def _one(args):
    """A worker process: one table, on its own engine."""
    table, page = args
    from database.database import engine

    models.init_dynamic_models(crud.TABLE_CONFIG)
    try:
        return copy_table(engine, table, declared()[table], page, say=lambda line: print(line, flush=True))
    finally:
        engine.dispose()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--page", type=int, default=1000)
    parser.add_argument("--table", action="append", default=[])
    args = parser.parse_args(argv)
    from database.database import engine

    models.init_dynamic_models(crud.TABLE_CONFIG)
    tables = declared(args.table)
    missing = sorted(set(args.table) - set(tables))
    if missing:
        print("not a declared table that keeps lines: %s" % ", ".join(missing))
        return 2
    running = servers_on(engine)
    if running:
        print("refused: the server is running - %s. Stop it first; the copy runs with nothing writing"
              % ", ".join("%s (pid %s)" % (name, pid) for pid, name in running))
        return 2
    todo = plan(engine, tables)
    for p in todo:
        print("%-32s %10d layer(s) on %9d row(s) · %s" % (
            p["table"], p["layers"], p["rows"],
            "copied" if p["copied"] else "lines not built - start the server once" if not p["built"] else "to copy"))
        if p["copies"]:
            print("%-32s names read as an old key merge's copies: %d, first: %s" % (
                "", len(p["copies"]), ", ".join(p["copies"][:SHOWN])))
    unbuilt = [p["table"] for p in todo if not p["built"] and p["layers"]]
    if args.check:
        print("--check: each page is copied and rolled back to count the cells whose lines merge to other than t - "
              "needs the server stopped; Ctrl+C at any time leaves a true count so far", flush=True)
        for p in todo:
            if p["built"] and not p["copied"] and p["layers"]:
                check_table(engine, p["table"], tables[p["table"]], args.page,
                            say=lambda line: print(line, flush=True))
        return 0
    if not args.apply:
        print("total %d layer(s) to copy · preview only - add --apply" % sum(
            p["layers"] for p in todo if p["built"] and not p["copied"]))
        return 0
    if unbuilt:
        print("refused: lines not built for %s - start the server once (it builds them), stop it, run again"
              % ", ".join(unbuilt))
        return 2
    work = [(p["table"], args.page) for p in todo if not p["copied"] and p["layers"]]
    engine.dispose()
    if args.workers > 1:
        with multiprocessing.Pool(args.workers) as pool:
            results = pool.map(_one, work)
    else:
        results = [_one(w) for w in work]
    stopped = [r["table"] for r in results if r.get("stopped")]
    print("copied %d table(s), %d already, %d stopped%s" % (
        sum(1 for r in results if "seconds" in r), sum(1 for r in results if r.get("already")), len(stopped),
        (" - " + ", ".join(stopped)) if stopped else ""))
    return 1 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
