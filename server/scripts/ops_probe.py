"""Read-only probe of this install's database (lead 11-14, owner «속도테스트에 운영 수치 반영해»). Run from the server
folder: `python scripts/ops_probe.py` - prints a short block (about 25 lines) to read off a screen; `--full FILE` also
writes every relation, every leftover column and pg_stat_io to FILE. Every statement runs read-only; the URL is never
printed. The disk line times one full scan of the largest table between 200 MB and 2 GB and says how many of its
blocks came from disk - near 0 means the rate is the cache's, not the disk's."""
import argparse
import os
import sys
import time

SERVER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SERVER)

import json                                                         # noqa: E402

import psycopg2                                                     # noqa: E402

import paths                                                        # noqa: E402

SETTINGS = ("shared_buffers", "work_mem", "effective_cache_size", "random_page_cost", "seq_page_cost",
            "maintenance_work_mem")
#: a table's own columns besides its declared ones (lines.FRAMEWORK + won_by)
FRAMEWORK = {"row_id", "business_key_val", "created_at", "updated_at", "won_by"}
MB = 2 ** 20


def ram() -> str:
    try:
        import psutil
    except ImportError:
        return "unknown (no psutil)"
    try:
        return "%.0f GB" % (psutil.virtual_memory().total / 2 ** 30)
    except psutil.Error as exc:
        return "unknown (%s)" % type(exc).__name__


def group(name) -> str:
    if name.endswith("__lines"):
        return "lines"
    if name.startswith("ledger_"):
        return "ledger"
    if name in ("cell_sources", "audit_logs", "database_outbox"):
        return "cell_sources/audit"
    return "other"


def probe(url, tables, full=None) -> list:
    """The short block's lines; `full` (a path) also gets the long listing."""
    conn = psycopg2.connect(url.replace("postgresql+psycopg2://", "postgresql://"),
                            options="-c default_transaction_read_only=on")
    cur = conn.cursor()

    def q(sql, *a):
        cur.execute(sql, a or None)
        return cur.fetchall()

    out, long = [], []
    out.append("OPS PROBE read_only=%s | %s | RAM %s" % (q("SHOW default_transaction_read_only")[0][0],
                                                          q("SHOW server_version")[0][0], ram()))
    out.append(" ".join("%s=%s" % (s, q("SHOW " + s)[0][0]) for s in SETTINGS))
    out.append("db %s" % q("SELECT pg_size_pretty(pg_database_size(current_database()))")[0][0])
    rows = q("""SELECT n.nspname, c.relname, c.reltuples::bigint, pg_total_relation_size(c.oid),
                       pg_relation_size(c.oid), pg_indexes_size(c.oid), coalesce(t.spcname, 'default'),
                       coalesce(s.heap_blks_read, 0) + coalesce(s.idx_blks_read, 0),
                       coalesce(s.heap_blks_hit, 0) + coalesce(s.idx_blks_hit, 0)
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                LEFT JOIN pg_tablespace t ON t.oid = c.reltablespace
                LEFT JOIN pg_statio_user_tables s ON s.relid = c.oid
                WHERE c.relkind IN ('r', 'p', 'm') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
                      AND n.nspname NOT LIKE 'pg_toast%%'
                ORDER BY 4 DESC""")
    sums = {}
    for r in rows:
        a = sums.setdefault(group(r[1]), [0, 0])
        a[0] += r[3]
        a[1] += r[5]
    out.append("groups GB(index): " + " · ".join("%s %.1f(%.1f)" % (k, v[0] / 2 ** 30, v[1] / 2 ** 30)
                                                 for k, v in sorted(sums.items())))
    out.append("top 10: table rows totalMB heap/idx space read/hit")
    for r in rows[:10]:
        out.append(" %s %s %.0f %.0f/%.0f %s %s/%s" % (r[1], r[2], r[3] / MB, r[4] / MB, r[5] / MB, r[6], r[7], r[8]))
    long += ["%s.%s rows %s total %.0f heap %.0f idx %.0f space %s read %s hit %s" % (
        r[0], r[1], r[2], r[3] / MB, r[4] / MB, r[5] / MB, r[6], r[7], r[8]) for r in rows]
    kinds, left_tables = {}, 0
    for name, cfg in (tables or {}).items():
        if not isinstance(cfg, dict) or "column_types" not in cfg:
            continue
        extra = [(col, typ) for col, typ in q("SELECT column_name, data_type FROM information_schema.columns "
                                               "WHERE table_schema = 'public' AND table_name = %s", name)
                 if col not in cfg["column_types"] and col not in FRAMEWORK]
        left_tables += bool(extra)
        for col, typ in extra:
            kinds[(col, typ)] = kinds.get((col, typ), 0) + 1
            long.append("leftover %s.%s %s" % (name, col, typ))
    out.append("leftover columns in %d tables: %s" % (left_tables, ", ".join(
        "%s %s x%d" % (c, t, n) for (c, t), n in sorted(kinds.items(), key=lambda kv: -kv[1])[:4]) or "none"))
    cand = [r for r in rows if 200 * MB <= r[4] <= 2048 * MB]
    if cand:
        nsp, rel, heap = cand[0][0], cand[0][1], cand[0][4]
        stat = "SELECT coalesce(heap_blks_read, 0) FROM pg_statio_user_tables WHERE schemaname = %s AND relname = %s"
        before = q(stat, nsp, rel)[0][0]
        t0 = time.perf_counter()
        q('SELECT count(*) FROM "%s"."%s"' % (nsp, rel))
        took = max(time.perf_counter() - t0, 1e-6)
        after = q(stat, nsp, rel)[0][0]
        out.append("seq read %s %.0f MB in %.1f s = %.0f MB/s, from disk %s of %d blocks" % (
            rel, heap / MB, took, heap / MB / took, after - before, heap // 8192))
    else:
        out.append("seq read: no table between 200 MB and 2 GB")
    try:
        long += ["pg_stat_io %s" % (r,) for r in q("SELECT backend_type, object, context, reads, read_time "
                                                   "FROM pg_stat_io WHERE reads > 0 ORDER BY reads DESC")]
    except psycopg2.Error as exc:                                   # an older server: no pg_stat_io
        conn.rollback()
        long.append("pg_stat_io not available: %s" % type(exc).__name__)
    conn.rollback()
    conn.close()
    if full:
        with open(full, "w", encoding="utf-8") as fh:
            fh.write("\n".join(out + [""] + long) + "\n")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--full", default=None, help="also write the long listing to this file")
    args = parser.parse_args(argv)
    url, _source = paths.resolve_database_url()
    with open(os.path.join(paths.CONFIG_DIR, "table_config.json"), encoding="utf-8") as fh:
        tables = json.load(fh)
    print("\n".join(probe(url, tables, args.full)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
