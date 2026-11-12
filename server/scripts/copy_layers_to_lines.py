"""The cell-source overhaul's migration: every declared table's old layers (cell_sources) copied into its line table
(<table>__lines), once, with the server stopped (owner 11-11). cell_sources is only read - nothing there is erased.

Usage
-----
    python server/scripts/copy_layers_to_lines.py                       preview: per table, rows and layers to copy
    python server/scripts/copy_layers_to_lines.py --check [--table <t> ...]   copy and roll back each page: cells
                                                                              whose lines merge to other than t, so far
    python server/scripts/copy_layers_to_lines.py --apply [--workers 4] [--table <t> ...] [--page 1000]
    python server/scripts/copy_layers_to_lines.py --apply --rows copy_mismatch_<t>.csv   those rows' copy lines
                                         taken out and copied again (after their layers or t were fixed)
    python server/scripts/copy_layers_to_lines.py --estimate [--workers 4] [--analyze] [--sample]   per table, layers
                                         from the database's statistics (nothing read) and hours; --analyze makes them
                                         first; --sample copies the biggest table for SAMPLE_SECONDS and rolls it back
                                         - this disk's rate (it loads the disk: run it off-hours)

Per table: pages of `--page` rows, a commit each (`line_migration.copy_page`). Interrupted, run it again - each table
resumes after its last committed page (`copied_through`); a table already copied says so and is skipped.
The gate rides every page: the copied lines merged again must give what t shows. A cell that does not is written to
copy_mismatch_<t>.csv (table, row_id, column, t_value, lines_value) and the page lands (owner ㄴ): t still shows its
value, and the cell turns to its lines' winner only when that column is written (c7319dfb6 - a merge re-decides only
the cells its write touched). The last page of a table writes its «copy» audit row.
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

#: the cells a line names, at most
SHOWN = 5
#: a table's cells whose copied lines do not give what t shows: copy_mismatch_<t>.csv, in the directory it runs in
RECORD = "copy_mismatch_%s.csv"
RECORD_COLUMNS = ("table", "row_id", "column", "t_value", "lines_value")
#: seconds between a table's progress lines
SAY_EVERY = 10.0
#: layers a second --estimate counts hours at: a quiet box, one 30-column table, one process (C, lead 11-12)
BOX_RATE = 25000
#: --sample: the schema it copies in (gone with its rollback), how long it copies, rows of t it brings in at a time
SAMPLE_SCHEMA = "c_copy_sample"
SAMPLE_SECONDS = 90.0
SAMPLE_AHEAD = 10


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


def estimate(engine) -> tuple:
    """cell_sources' layers per table from the catalogue's own statistics (pg_class.reltuples, pg_stats' common
    values of table_name) - no row of it read. -> ({table: layers}, layers of the tables the statistics' common list
    leaves out, all layers). LookupError where cell_sources has no statistics yet."""
    where = ("schemaname = current_schema() AND tablename = '%s' AND attname = 'table_name'"
             % line_migration.OLD_LAYERS)
    with engine.connect() as c:
        total = c.execute(text("SELECT reltuples FROM pg_class WHERE relname = :t AND relnamespace = "
                               "(SELECT oid FROM pg_namespace WHERE nspname = current_schema())"),
                          {"t": line_migration.OLD_LAYERS}).scalar()
        common = c.execute(text("SELECT u.v, u.f FROM pg_stats, unnest(most_common_vals::text::text[], "
                                "most_common_freqs) AS u(v, f) WHERE " + where)).all()
        known = c.execute(text("SELECT count(*) FROM pg_stats WHERE " + where)).scalar()
    if not total or total < 0 or not known:
        raise LookupError("no statistics for %s - run again with --analyze (reads a sample, takes about a minute)"
                          % line_migration.OLD_LAYERS)
    per = {t: round(f * total) for t, f in common}
    return per, max(0, round(total) - sum(per.values())), round(total)


def sample(engine, table: str, cfg: dict, seconds: float = SAMPLE_SECONDS, page: int = 1000, during=None) -> dict:
    """This disk's copy rate: `line_migration.copy_page` as it is, page after page for `seconds`, on SAMPLE_SCHEMA -
    made inside one transaction, first on the search path (SET LOCAL): t's rows a page needs copied into it ahead of
    the page (not timed), the ledger tables and t__lines built there; cell_sources and the pins read where they are.
    The transaction is rolled back - the schema and all it held go; t is only read (ACCESS SHARE). Refused where the
    lines are built already (it is for before the window). `during(conn)`: called after the first page, inside.
    -> {"pages", "rows", "layers", "seconds", "rate"} (layers a second)."""
    from sqlalchemy import MetaData, Table

    with engine.connect() as conn:
        home = conn.execute(text("SELECT current_schema()")).scalar()
        names = set(lines.base_tables(conn, lines=True, schema=home))
        built = sorted(names & {lines.lines_relation(table), lines.LineColumn.__tablename__,
                                lines.AuditBatch.__tablename__, lines.LineSource.__tablename__})
        if built:
            raise ValueError("%s is built here already - the sample is for a database before the window" % built[0])
        conn.rollback()                                # the look above autobegan
        tx = conn.begin()
        try:
            conn.execute(text('CREATE SCHEMA "%s"' % SAMPLE_SCHEMA))
            conn.execute(text('SET LOCAL search_path = "%s", "%s"' % (SAMPLE_SCHEMA, home)))
            conn.execute(text('CREATE TABLE "%s"."%s" (LIKE "%s"."%s" INCLUDING ALL)' % (SAMPLE_SCHEMA, table, home, table)))
            for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource):
                model.__table__.to_metadata(MetaData(), schema=SAMPLE_SCHEMA).create(conn)
            db = Session(bind=conn)
            lines.ensure_line_table(db, table, cfg)
            here = Table(table, MetaData(), schema=SAMPLE_SCHEMA, autoload_with=conn)
            there = Table(table, MetaData(), schema=home, autoload_with=conn)
            cs = models.CellSource.__table__
            ahead, after, out = None, None, {"pages": 0, "rows": 0, "layers": 0, "seconds": 0.0}
            while out["seconds"] < seconds:
                if ahead is None or after == ahead:                 # the next page's rows of t brought in, untimed
                    q = (select(cs.c.row_id).where(cs.c.table_name == table).group_by(cs.c.row_id)
                         .order_by(cs.c.row_id).limit(page * SAMPLE_AHEAD))
                    if ahead is not None:
                        q = q.where(cs.c.row_id > ahead)
                    wanted = conn.execute(q).scalars().all()
                    if not wanted:
                        break
                    conn.execute(here.insert().from_select([c.name for c in there.columns],
                                                           select(there).where(there.c.row_id.in_(wanted))))
                    ahead = wanted[-1]
                began = time.perf_counter()
                n, after = line_migration.copy_page(db, table, cfg, after, page, transaction_id="copy_sample")
                out["seconds"] += time.perf_counter() - began
                out["pages"] += 1
                out["layers"] += n
                out["rows"] += page if after is not None else 0
                if out["pages"] == 1 and during is not None:
                    during(conn)
                if after is None:
                    break
            db.close()
        finally:
            tx.rollback()
    out["rate"] = out["layers"] / out["seconds"] if out["seconds"] else 0.0
    return out


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


def record(path, table, mismatched) -> None:
    """Append (row_id, column, t's value, the lines' winner) cells to the record, its head line first."""
    import csv

    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        if new:
            out.writerow(RECORD_COLUMNS)
        out.writerows((table,) + tuple("" if v is None else v for v in m) for m in mismatched)


def recorded_rows(path) -> dict:
    """{table: [row_id]} of a record."""
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        got = {}
        for r in csv.DictReader(f):
            got.setdefault(r["table"], set()).add(r["row_id"])
    return {t: sorted(r) for t, r in got.items()}


def copy_table(engine, table: str, cfg: dict, page: int, say=print, rows=None) -> dict:
    """Copy one table to its end, a commit a page; a cell the gate finds is recorded and the page lands. `rows`: those
    rows only (a record's), their copy lines taken out first."""
    tx = "copy_lines:%s" % table
    cs = models.CellSource.__table__
    path = os.path.abspath(RECORD % table)
    with Session(bind=engine) as db:
        total = db.execute(select(func.count(func.distinct(cs.c.row_id))).where(cs.c.table_name == table)).scalar()
        after, copied, pages, mismatched, found = None, 0, 0, [], 0
        if rows is not None:
            path = os.path.abspath((RECORD % table)[:-4] + time.strftime(".again-%Y%m%d-%H%M%S.csv"))
            taken = take_copy_lines(db, table, cfg, rows, tx)
            n, _ = line_migration.copy_page(db, table, cfg, None, len(rows), transaction_id=tx,
                                            mismatched=mismatched, rows=rows)
            db.commit()
            if mismatched:
                record(path, table, mismatched)
            say("%s: %d row(s) copied again - %d copy line(s) taken out, %d layer(s) copied - %s" % (
                table, len(rows), taken, n, "%d cell(s) still do not match, listed in %s" % (len(mismatched), path)
                if mismatched else "every cell matches"))
            return {"table": table, "again": len(rows), "copied": n, "mismatched": len(mismatched),
                    "record": path if mismatched else None}
        rows = total
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
            db.commit()
            if mismatched:
                record(path, table, mismatched)
                found += len(mismatched)
                mismatched = []
            copied += n
            pages += 1
            after = after_next
            now = time.perf_counter()
            if after is None:
                began = time.perf_counter()          # a migrated t__lines has no statistics: its first reads plan blind
                with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as c:
                    c.execute(text('ANALYZE "%s"' % lines.lines_relation(table)))
                say("%s: done - %d layer(s) copied in %.0f s - analyzed %s in %.0f s%s" % (
                    table, copied, now - started, lines.lines_relation(table), time.perf_counter() - began,
                    (" - %d cell(s) do not match, listed in %s: each shows t's value until its column is written, "
                     "then its lines' winner; to copy those rows again: python server/scripts/copy_layers_to_lines.py "
                     "--apply --rows %s" % (found, path, path)) if found else ""))
                return {"table": table, "copied": copied, "seconds": now - started, "mismatched": found,
                        "record": path if found else None}
            if now - said >= SAY_EVERY:
                said = now
                done = min(pages * page, rows)
                rate = done / (now - started)
                say("%s: %d / %d rows, %d layer(s) copied, %d mismatched so far, about %.0f min left"
                    % (table, done, rows, copied, found, (rows - done) / rate / 60 if rate else 0))


def take_copy_lines(db, table, cfg, rows, tx) -> int:
    """Take these rows' copy lines out of t__lines, and the won_by entries naming them. -> lines taken."""
    from sqlalchemy import delete, update

    s = lines.shape(db, table, cfg)
    lt, t = s["lines"], lines.current_table(db, table, cfg)
    gone = set(db.execute(select(lt.c.line_id).where(lt.c.batch == tx, lt.c.row_id.in_(rows))).scalars())
    if gone:
        db.execute(delete(lt).where(lt.c.line_id.in_(sorted(gone))))
        for row_id, won_by in db.execute(select(t.c.row_id, t.c[lines.WON_BY]).where(t.c.row_id.in_(rows))).all():
            kept = {c: lid for c, lid in (won_by or {}).items() if lid not in gone}
            if kept != (won_by or {}):
                db.execute(update(t).where(t.c.row_id == row_id).values({lines.WON_BY: kept or None}))
    return len(gone)


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
    parser.add_argument("--estimate", action="store_true")
    parser.add_argument("--analyze", action="store_true")
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--page", type=int, default=1000)
    parser.add_argument("--table", action="append", default=[])
    parser.add_argument("--rows", help="a copy_mismatch_<t>.csv: copy its rows again (with --apply)")
    args = parser.parse_args(argv)
    from database.database import engine

    models.init_dynamic_models(crud.TABLE_CONFIG)
    tables = declared(args.table)
    missing = sorted(set(args.table) - set(tables))
    if missing:
        print("not a declared table that keeps lines: %s" % ", ".join(missing))
        return 2
    if args.estimate:
        if args.analyze:
            began = time.perf_counter()
            with engine.begin() as c:
                c.execute(text("ANALYZE %s" % line_migration.OLD_LAYERS))
            print("ANALYZE %s done in %.0f s - its statistics are made" % (line_migration.OLD_LAYERS,
                                                                         time.perf_counter() - began))
        try:
            per, rest, total = estimate(engine)
        except LookupError as none:
            print("refused: %s" % none)
            return 2
        shown = {t: n for t, n in per.items() if t in tables}
        rate, whose = BOX_RATE, "a quiet box's rate; this disk's own is not measured - add --sample"
        if args.sample and shown:
            biggest_table = max(shown, key=shown.get)
            print("sample: copying %s for %.0f s and rolling it back ..." % (biggest_table, SAMPLE_SECONDS), flush=True)
            try:
                got = sample(engine, biggest_table, tables[biggest_table], page=args.page)
            except ValueError as refused:
                print("refused: %s" % refused)
                return 2
            print("sample %s: %d page(s), %d layer(s) in %.1f s - %.0f layers/s on this disk; rolled back, nothing kept"
                  % (biggest_table, got["pages"], got["layers"], got["seconds"], got["rate"]))
            if got["rate"]:
                rate, whose = got["rate"], "this disk's rate, from the sample"
        for t in sorted(shown, key=lambda t: -shown[t]):
            print("%-32s about %12d layer(s)  %6.2f h" % (t, shown[t], shown[t] / rate / 3600))
        print("%-32s about %12d layer(s) in tables too small for the statistics' list" % ("(the rest)", rest))
        biggest = max(shown.values(), default=0)
        print("total about %d layer(s): %.1f h with 1 process, at least %.1f h with %d (the biggest table alone %.1f h)"
              " - at %.0f layers/s, %s"
              % (total, total / rate / 3600, max(biggest, total / max(1, args.workers)) / rate / 3600,
                 args.workers, biggest / rate / 3600, rate, whose))
        return 0
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
    if args.rows:
        asked = recorded_rows(args.rows)
        unknown = sorted(t for t in asked if t not in tables)
        if unknown:
            print("refused: %s names %s, not a declared table that keeps lines" % (args.rows, ", ".join(unknown)))
            return 2
        again = [copy_table(engine, t, tables[t], args.page, say=lambda line: print(line, flush=True), rows=r)
                 for t, r in sorted(asked.items())]
        print("copied again %d row(s) of %d table(s) - %d cell(s) still do not match" % (
            sum(r["again"] for r in again), len(again), sum(r["mismatched"] for r in again)))
        return 0
    work = [(p["table"], args.page) for p in todo if not p["copied"] and p["layers"]]
    engine.dispose()
    if args.workers > 1:
        with multiprocessing.Pool(args.workers) as pool:
            results = pool.map(_one, work)
    else:
        results = [_one(w) for w in work]
    stopped = [r["table"] for r in results if r.get("stopped")]
    records = [r["record"] for r in results if r.get("record")]
    print("copied %d table(s), %d already, %d stopped%s - %d cell(s) do not match%s" % (
        sum(1 for r in results if "seconds" in r), sum(1 for r in results if r.get("already")), len(stopped),
        (" - " + ", ".join(stopped)) if stopped else "", sum(r.get("mismatched") or 0 for r in results),
        (" (" + ", ".join(records) + ")") if records else ""))
    return 1 if stopped else 0


if __name__ == "__main__":
    sys.exit(main())
