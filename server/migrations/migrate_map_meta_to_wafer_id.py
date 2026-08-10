"""Move stored `wafer_map_metadata` map ids from the old composite spelling to `wafer_id`.

RUN MANUALLY. NEVER ON BOOT. Dry run is the default; writing needs `--apply`.

WHY THIS EXISTS
---------------
`core_wafer_map` used to be identified by `core_lot || '_' || core_slot`. On 2026-08-10
its declaration was corrected in BOTH config files that carry the identity --
`table_config.json` (`core_wafer_map.map_key_columns`) and `map_overlay_config.json`
(`table_bindings.core_wafer_map.columns.key_columns`) -- to `["wafer_id"]`.

**The stored rows were never moved.** So every consumer now composes a lookup key of
`WF.010101` while `wafer_map_metadata` still holds `CL-2601-001_01`, and the lookup in
`map_overlay._meta_select` (`target_table == t AND map_id == m`) misses every time.

    stored now   CL-2601-001_01     ( core_lot || '_' || core_slot )
    should be    WF.010101          ( wafer_id )

WHY IT IS SILENT, AND WHY THAT MAKES IT WORSE
---------------------------------------------
Before `[D5]`, a missing metadata row produced a loud `binding_unresolved`. Since `[D5]`
a missing meta row is a NORMAL state: the map borrows geometry from a neighbour and is
scored anyway. So this defect no longer announces itself -- it degraded from an error
into a quiet borrow, and every map in the table has been scored against borrowed
geometry rather than its own registered spec. Fixing the rows is what makes the
2026-08-10 declaration true again.

WHAT THIS SCRIPT WRITES, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------------
It writes THREE COLUMNS OF ONE TABLE, on the same row, in one transaction:

    wafer_map_metadata.map_id             the identity itself
    wafer_map_metadata.map_pk             "<target_table>_<map_id>" -- the business key
    wafer_map_metadata.business_key_val   the same string; crud addresses rows by it

Those three are not three changes, they are one: `map_pk` is a pure function of
`(target_table, map_id)` (`map_meta_registrar.meta_business_key`), and `business_key_val`
is `map_pk` (`table_config.wafer_map_metadata.business_key = "map_pk"`). Measured on
assy_qa: `map_pk <> business_key_val` on 0 of 200 rows. Leaving any one of them behind
produces a row whose identity disagrees with itself.

**It does NOT touch any other table.** `map_id` is a STRING JOIN KEY, not a foreign key,
so other tables hold copies that nothing will repair automatically. The measured holders
are listed in `scope_report()` below and are CHECKED ON EVERY RUN. If a live reference
exists outside this table the write path REFUSES, because a migration that moves one
table and leaves a second pointing at the old string converts a uniform wrong state into
a split one -- which is worse than not migrating. Expanding the scope is a product-owner
ruling, not something this script may decide; `--i-accept-split-state` exists so the
owner can record that ruling explicitly.

WHAT IS SAFE BECAUSE IT ANCHORS ON row_id
------------------------------------------
`cell_sources`, `cell_overwrites` and `audit_logs` address a row by `row_id` (a UUID),
NOT by the business key. Measured on assy_qa: 1,400 `cell_sources` rows and 200
`audit_logs` rows hang off the 200 meta rows, and an in-place UPDATE keeps every one of
them attached because `row_id` does not change. The layering provenance survives. This
is the reason the migration is an UPDATE and not a delete-and-reinsert -- reinserting
would mint new `row_id`s and detach all 1,600 provenance rows.

REFUSES RATHER THAN GUESSES
---------------------------
A row is migrated only when its old key resolves to EXACTLY ONE non-blank `wafer_id`.
Zero candidates, more than one candidate, or a target business key already taken by a
different row: the row is reported BY NAME and skipped. The script never picks one.

REVERSIBILITY
-------------
`--apply` writes a journal (default `<script dir>/journal_map_meta_wafer_id_<db>_<ts>.json`)
holding `row_id` plus the before and after of all three columns. `--revert <journal>`
replays it backwards. The inverse is ALSO derivable without the journal, because the
mapping is 1:1 and total: for any migrated row,
`old_map_id = (SELECT DISTINCT core_lot || '_' || core_slot FROM core_wafer_map WHERE wafer_id = <map_id>)`.
The journal exists so a revert does not depend on `core_wafer_map` still being intact.

USAGE
-----
    # 1. measure, write nothing (this is the default -- no flag needed)
    python server/migrations/migrate_map_meta_to_wafer_id.py

    # 2. write, naming the database out loud so a wrong target cannot be a typo
    python server/migrations/migrate_map_meta_to_wafer_id.py --apply --confirm-database assy_manager

    # 3. undo
    python server/migrations/migrate_map_meta_to_wafer_id.py --revert <journal.json> --confirm-database assy_manager

Connection precedence is the app's own (`paths.resolve_database_url`): env `DATABASE_URL`
> `config/database.json` > default. `--database-url` overrides all three.
"""

import argparse
import datetime
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.abspath(os.path.join(_HERE, ".."))
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

import paths as _paths  # noqa: E402

try:
    import psycopg2
    import psycopg2.extras
except ImportError:  # pragma: no cover - environment problem, not a code path
    sys.stderr.write(
        "psycopg2 is missing. This almost always means the conda environment was not "
        "used. Retry with:  conda run -n assy_manager python %s\n" % __file__)
    raise

DEFAULT_PG_URL = "postgresql://postgres:admin@localhost:5432/assy_manager"

META_TABLE = "wafer_map_metadata"
DEFAULT_TARGET_TABLE = "core_wafer_map"
DEFAULT_OLD_KEY = ["core_lot", "core_slot"]
DEFAULT_NEW_KEY = "wafer_id"

# Row verdicts. Every matched row lands in exactly one bucket.
V_ALREADY = "already_migrated"
V_CHANGE = "would_change"
V_UNRESOLVED = "no_wafer_id"
V_AMBIGUOUS = "ambiguous"
V_COLLISION = "target_key_taken"


# --------------------------------------------------------------------------
# configuration
# --------------------------------------------------------------------------

def _separator():
    """The `wafer_map_metadata` composite separator, from the declaration.

    Read from config rather than hardcoded for the same reason
    `map_meta_registrar.meta_business_key` reads it: two spellings of a business key is
    how one writer creates the row another cannot find. Falls back to "_" when the
    config tree is not reachable (the migration may run from a bare checkout).
    """
    try:
        with open(_paths.config_path("table_config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return (cfg.get(META_TABLE) or {}).get("composite_key_separator", "_") or "_"
    except Exception:
        return "_"


def _declared_new_key(target_table):
    """`map_key_columns` for the target table, so the script and the app agree.

    Returns None when unreadable; the caller then falls back to the CLI default. This is
    a CROSS-CHECK, not the source of truth -- if config says something other than the
    requested new key the run stops, because that disagreement means either the config
    was not corrected or this migration is being pointed at the wrong table.
    """
    try:
        with open(_paths.config_path("table_config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return (cfg.get(target_table) or {}).get("map_key_columns")
    except Exception:
        return None


def _db_name(url):
    tail = url.rsplit("/", 1)[-1]
    return tail.split("?")[0]


def _mask(url):
    """Hide the password when echoing the connection string."""
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return "%s://%s:***@%s" % (scheme, user, host)


# --------------------------------------------------------------------------
# scope guard -- the blast radius, re-measured on every run
# --------------------------------------------------------------------------

def _table_exists(cur, name):
    cur.execute("""select 1 from information_schema.tables
                    where table_schema='public' and table_name=%s""", (name,))
    return cur.fetchone() is not None


def _column_exists(cur, table, column):
    cur.execute("""select 1 from information_schema.columns
                    where table_schema='public' and table_name=%s and column_name=%s""",
                (table, column))
    return cur.fetchone() is not None


def scope_report(cur, target_table):
    """Every OTHER place measured to hold a copy of this table's map-id string.

    `map_id` is a string join key with no referential integrity behind it, so each of
    these is a place a rename can orphan silently. This runs on EVERY invocation --
    including the production dry run -- because the dev box's zeros are not production's
    zeros. A holder is only a real problem when its stored string RESOLVES today: a
    string that already matches nothing is stale seed data that this migration neither
    breaks nor fixes.

    Returns a list of dicts; `live` is the count that resolves today and would be broken.
    """
    findings = []

    def add(table, column, where_sql, args, note):
        if not _table_exists(cur, table):
            findings.append({"table": table, "column": column, "total": None,
                             "live": None, "note": "TABLE ABSENT -- cannot measure here"})
            return
        if not _column_exists(cur, table, column):
            findings.append({"table": table, "column": column, "total": None,
                             "live": None, "note": "column absent"})
            return
        cur.execute('select count(*) from "%s" where %s' % (table, where_sql), args)
        total = cur.fetchone()[0]
        # "live" = the stored string still resolves to a metadata row today, so the
        # rename would break a reference that currently works.
        cur.execute(
            'select count(*) from "%s" t where %s and exists ('
            '  select 1 from "%s" m where m.target_table=%%s and m.map_id = t."%s")'
            % (table, where_sql, META_TABLE, column),
            tuple(args) + (target_table,))
        live = cur.fetchone()[0]
        findings.append({"table": table, "column": column, "total": total,
                         "live": live, "note": note})

    add("frame_confirmation", "reference_map_id",
        "reference_table=%s and reference_map_id is not null and reference_map_id<>''",
        (target_table,), "the confirmed coordinate system's floor")
    add("frame_confirmation_source", "map_id",
        "source_table=%s and map_id is not null and map_id<>''",
        (target_table,), "indexed by (source_table, map_id) -- two indexes depend on it")
    add("map_split_registry", "map_key",
        "ref_table=%s and map_key is not null and map_key<>''",
        (target_table,), "legend/DOE plans; split_key embeds it too")
    add("map_doe", "map_key",
        "ref_table=%s and map_key is not null and map_key<>''",
        (target_table,), "retired sibling of map_split_registry")
    add("map_doe_source", "map_key",
        "ref_table=%s and map_key is not null and map_key<>''",
        (target_table,), "retired sibling of map_split_registry")

    # grid_metadata JSON blobs on ANY map that point AT this table (valid_die_ref,
    # phys_assumed_from, grid_assumed_from, phys_confirmed_from, frame_confirmed_from).
    # A cheap text probe: a blob that never names the table cannot embed its map id.
    cur.execute("""select count(*) from wafer_map_metadata
                    where grid_metadata like %s""", ("%%%s%%" % target_table,))
    blobs = cur.fetchone()[0]
    findings.append({
        "table": META_TABLE, "column": "grid_metadata (JSON)", "total": blobs,
        "live": blobs,
        "note": "blobs naming the target table -- may embed its map id in "
                "valid_die_ref/phys_assumed_from/grid_assumed_from/"
                "phys_confirmed_from/frame_confirmed_from"})

    # dt_inventory stores whole metadata blobs (core_frame / dt_frame) that can embed
    # both the map id and a "<table>:<map_id>" reference spec.
    if _table_exists(cur, "dt_inventory"):
        cur.execute("""select count(*) from dt_inventory
                        where core_frame like %s or dt_frame like %s""",
                    ("%%%s%%" % target_table, "%%%s%%" % target_table))
        n = cur.fetchone()[0]
        findings.append({"table": "dt_inventory", "column": "core_frame/dt_frame (JSON)",
                         "total": n, "live": n,
                         "note": "embeds reference / primary_reference_spec"})
    else:
        findings.append({"table": "dt_inventory", "column": "core_frame/dt_frame (JSON)",
                         "total": None, "live": None,
                         "note": "TABLE ABSENT -- cannot measure here"})

    return findings


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------

def build_resolution(cur, target_table, old_key_cols, new_key, sep):
    """old composite string -> (candidate_count, the_single_wafer_id_or_None).

    ONE grouped aggregate over the source table, not a query per row: at the 10M-row
    ceiling this table works to, a per-row lookup would be 10M round trips. The GROUP BY
    collapses to one entry per lot/slot group (200 on assy_qa), so the result set is tiny
    regardless of table size.
    """
    old_expr = (" || %s || " % _lit(sep)).join(
        'coalesce("%s"::text, %s)' % (c, _lit("")) for c in old_key_cols)
    cur.execute("""
        select {old_expr} as old_key,
               count(distinct "{nk}") filter (where "{nk}" is not null and "{nk}" <> '') as n,
               min("{nk}") filter (where "{nk}" is not null and "{nk}" <> '') as one
          from "{src}"
         group by 1
    """.format(old_expr=old_expr, nk=new_key, src=target_table))
    return {r[0]: (r[1], r[2]) for r in cur.fetchall()}


def known_new_keys(cur, target_table, new_key):
    """The set of live `wafer_id` values -- used to recognise ALREADY-migrated rows.

    A half-migrated database is the realistic production state if anyone ran anything by
    hand, so "this map_id is already a valid new-spelling key" must be a recognised
    verdict and not fall through to `no_wafer_id`.
    """
    cur.execute("""select distinct "{nk}" from "{src}"
                    where "{nk}" is not null and "{nk}" <> ''"""
                .format(nk=new_key, src=target_table))
    return {r[0] for r in cur.fetchall()}


def _lit(s):
    return "'" + str(s).replace("'", "''") + "'"


def classify(cur, target_table, old_key_cols, new_key, sep):
    """Every meta row for `target_table`, bucketed. Pure read."""
    resolution = build_resolution(cur, target_table, old_key_cols, new_key, sep)
    already = known_new_keys(cur, target_table, new_key)

    cur.execute("""select row_id, map_id, map_pk, business_key_val
                     from "{meta}" where target_table=%s order by map_id"""
                .format(meta=META_TABLE), (target_table,))
    rows = cur.fetchall()

    # Business keys currently in use across the WHOLE table -- the unique index is on
    # the column, not on (target_table, map_id), so a collision can come from any target.
    cur.execute('select business_key_val, row_id from "%s" '
                'where business_key_val is not null' % META_TABLE)
    taken = {bk: rid for bk, rid in cur.fetchall()}

    planned_bk = {}
    out = []
    for row_id, map_id, map_pk, bk in rows:
        rec = {"row_id": row_id, "map_id": map_id, "map_pk": map_pk,
               "business_key_val": bk, "new_map_id": None, "new_map_pk": None,
               "verdict": None, "detail": ""}

        if map_id in already:
            rec["verdict"] = V_ALREADY
            rec["detail"] = "map_id is already a live %s" % new_key
            out.append(rec)
            continue

        n, one = resolution.get(map_id, (0, None))
        if n == 0:
            rec["verdict"] = V_UNRESOLVED
            rec["detail"] = ("no row in %s has this old key with a non-blank %s"
                             % (target_table, new_key))
            out.append(rec)
            continue
        if n > 1:
            rec["verdict"] = V_AMBIGUOUS
            rec["detail"] = "%d distinct %s values for this old key" % (n, new_key)
            out.append(rec)
            continue

        new_pk = "%s%s%s" % (target_table, sep, one)
        owner = taken.get(new_pk)
        if owner is not None and owner != row_id:
            rec["verdict"] = V_COLLISION
            rec["detail"] = "business key %r already held by row_id %s" % (new_pk, owner)
            out.append(rec)
            continue
        clash = planned_bk.get(new_pk)
        if clash is not None:
            rec["verdict"] = V_COLLISION
            rec["detail"] = ("business key %r already claimed in this same run by "
                             "row_id %s" % (new_pk, clash))
            out.append(rec)
            continue

        rec["new_map_id"] = one
        rec["new_map_pk"] = new_pk
        rec["verdict"] = V_CHANGE
        planned_bk[new_pk] = row_id
        out.append(rec)

    return out


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def print_report(records, findings, target_table, new_key, sample, applied):
    buckets = {}
    for r in records:
        buckets.setdefault(r["verdict"], []).append(r)

    print("")
    print("=" * 78)
    print("  ROWS  (%s where target_table=%r)" % (META_TABLE, target_table))
    print("=" * 78)
    print("  matched                    %6d" % len(records))
    print("  would change               %6d" % len(buckets.get(V_CHANGE, [])))
    print("  already migrated           %6d" % len(buckets.get(V_ALREADY, [])))
    print("  no resolvable %-12s %6d" % (new_key, len(buckets.get(V_UNRESOLVED, []))))
    print("  ambiguous (>1 candidate)   %6d" % len(buckets.get(V_AMBIGUOUS, [])))
    print("  target key already taken   %6d" % len(buckets.get(V_COLLISION, [])))

    changes = buckets.get(V_CHANGE, [])
    if changes:
        print("\n  before -> after  (first %d of %d)" % (min(sample, len(changes)), len(changes)))
        for r in changes[:sample]:
            print("    %-34s -> %s" % (r["map_id"], r["new_map_id"]))
            print("      %-32s -> %s" % (r["map_pk"], r["new_map_pk"]))

    # Skipped rows are named individually. A count alone would let a silently
    # unmigratable map hide inside a number.
    for verdict, title in ((V_UNRESOLVED, "NOT MIGRATED -- no resolvable %s" % new_key),
                           (V_AMBIGUOUS, "NOT MIGRATED -- ambiguous, refused rather than guessed"),
                           (V_COLLISION, "NOT MIGRATED -- target business key already taken")):
        rs = buckets.get(verdict, [])
        if not rs:
            continue
        print("\n  %s  (%d)" % (title, len(rs)))
        for r in rs:
            print("    %-34s  %s" % (r["map_id"], r["detail"]))

    print("")
    print("=" * 78)
    print("  SCOPE GUARD -- other holders of this map-id string")
    print("=" * 78)
    print("  %-28s %-26s %8s %8s" % ("table", "column", "total", "live"))
    for f in findings:
        tot = "-" if f["total"] is None else str(f["total"])
        live = "-" if f["live"] is None else str(f["live"])
        print("  %-28s %-26s %8s %8s" % (f["table"], f["column"], tot, live))
        if f["note"]:
            print("      %s" % f["note"])
    print("\n  'live' = the stored string resolves to a metadata row TODAY, so this")
    print("  migration would break a reference that currently works.")
    print("  'total' with live=0 is stale data this migration neither breaks nor fixes.")

    return buckets


def split_state_risk(findings):
    """Holders that would be left pointing at the old string. Non-zero = needs a ruling."""
    return [f for f in findings
            if f["table"] != META_TABLE and f["live"]]


# --------------------------------------------------------------------------
# write paths
# --------------------------------------------------------------------------

CHUNK = 1000


def apply_changes(cur, records, target_table):
    """One transaction. Chunked so a large table does not build one giant statement."""
    changes = [r for r in records if r["verdict"] == V_CHANGE]
    written = 0
    for i in range(0, len(changes), CHUNK):
        batch = changes[i:i + CHUNK]
        psycopg2.extras.execute_batch(cur, """
            update "{meta}"
               set map_id=%(new_map_id)s,
                   map_pk=%(new_map_pk)s,
                   business_key_val=%(new_map_pk)s,
                   updated_at=now()
             where row_id=%(row_id)s
               and target_table=%(tt)s
               and map_id=%(map_id)s
        """.format(meta=META_TABLE),
            [dict(r, tt=target_table) for r in batch], page_size=CHUNK)
        written += cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(batch)
    # `execute_batch` reports only the last statement's rowcount, so recount for truth
    # rather than trusting the driver: the printed number must be what the DB holds.
    cur.execute("""select count(*) from "{meta}" where target_table=%s
                    and map_id = any(%s)""".format(meta=META_TABLE),
                (target_table, [r["new_map_id"] for r in changes] or [None]))
    verified = cur.fetchone()[0]
    return len(changes), verified


def revert(cur, journal, target_table):
    entries = [e for e in journal["changes"]]
    for i in range(0, len(entries), CHUNK):
        batch = entries[i:i + CHUNK]
        psycopg2.extras.execute_batch(cur, """
            update "{meta}"
               set map_id=%(map_id)s,
                   map_pk=%(map_pk)s,
                   business_key_val=%(business_key_val)s,
                   updated_at=now()
             where row_id=%(row_id)s
               and map_id=%(new_map_id)s
        """.format(meta=META_TABLE), batch, page_size=CHUNK)
    cur.execute("""select count(*) from "{meta}" where target_table=%s
                    and map_id = any(%s)""".format(meta=META_TABLE),
                (target_table, [e["map_id"] for e in entries] or [None]))
    return len(entries), cur.fetchone()[0]


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Move wafer_map_metadata map ids to the wafer_id spelling. "
                    "Dry run unless --apply.")
    ap.add_argument("--database-url", default=None,
                    help="overrides env DATABASE_URL and config/database.json")
    ap.add_argument("--target-table", default=DEFAULT_TARGET_TABLE)
    ap.add_argument("--old-key", default=",".join(DEFAULT_OLD_KEY),
                    help="comma-separated old composite columns (default core_lot,core_slot)")
    ap.add_argument("--new-key", default=DEFAULT_NEW_KEY)
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--apply", action="store_true",
                    help="WRITE. Without this the script cannot modify anything.")
    ap.add_argument("--confirm-database", default=None,
                    help="must equal the target database name; required with --apply")
    ap.add_argument("--journal", default=None, help="reversal journal path")
    ap.add_argument("--revert", default=None, metavar="JOURNAL",
                    help="undo a previous --apply using its journal")
    ap.add_argument("--i-accept-split-state", action="store_true",
                    help="proceed even though another table still points at the old "
                         "string. Records a product-owner ruling; not a default.")
    args = ap.parse_args(argv)

    url = args.database_url or _paths.resolve_database_url(DEFAULT_PG_URL)[0]
    dbname = _db_name(url)
    old_key_cols = [c.strip() for c in args.old_key.split(",") if c.strip()]
    sep = _separator()

    print("database   : %s   (db=%s)" % (_mask(url), dbname))
    print("mode       : %s" % ("REVERT" if args.revert else
                               ("APPLY (writes)" if args.apply else "DRY RUN (writes nothing)")))
    print("target     : %s.map_id where target_table=%r"
          % (META_TABLE, args.target_table))
    print("mapping    : %s  ->  %s" % (" || '%s' || " % sep, args.new_key))
    print("separator  : %r (from table_config.%s.composite_key_separator)" % (sep, META_TABLE))

    if (args.apply or args.revert) and args.confirm_database != dbname:
        print("\nREFUSED: writing requires --confirm-database %s" % dbname)
        print("Naming the database out loud is what stops a wrong-target run being a typo.")
        return 2

    declared = _declared_new_key(args.target_table)
    if declared is not None and declared != [args.new_key]:
        print("\nREFUSED: table_config declares %s.map_key_columns = %r, but this run "
              "would migrate to %r." % (args.target_table, declared, [args.new_key]))
        print("Either the config was not corrected, or this migration is pointed at the "
              "wrong table. Both are stop conditions.")
        return 2

    conn = psycopg2.connect(url)
    conn.autocommit = False
    try:
        cur = conn.cursor()

        if args.revert:
            with open(args.revert, "r", encoding="utf-8") as f:
                journal = json.load(f)
            n, verified = revert(cur, journal, args.target_table)
            conn.commit()
            print("\nREVERTED %d rows; %d now carry the old spelling again." % (n, verified))
            return 0

        for t in (META_TABLE, args.target_table):
            if not _table_exists(cur, t):
                print("\nREFUSED: table %r does not exist in %s." % (t, dbname))
                return 2
        for c in old_key_cols + [args.new_key]:
            if not _column_exists(cur, args.target_table, c):
                print("\nREFUSED: %s has no column %r." % (args.target_table, c))
                return 2

        records = classify(cur, args.target_table, old_key_cols, args.new_key, sep)
        findings = scope_report(cur, args.target_table)
        buckets = print_report(records, findings, args.target_table, args.new_key,
                               args.sample, args.apply)

        changes = buckets.get(V_CHANGE, [])
        risk = split_state_risk(findings)

        if not args.apply:
            print("\n" + "=" * 78)
            if not changes:
                print("  NOTHING TO DO -- no row would change. Safe to stop here.")
            else:
                print("  DRY RUN. Nothing was written. %d rows would change." % len(changes))
                print("  To write:  --apply --confirm-database %s" % dbname)
            if risk:
                print("\n  WARNING: %d other holder(s) carry a LIVE reference to the old"
                      % len(risk))
                print("  spelling. Migrating this table alone would SPLIT the state:")
                for f in risk:
                    print("    %s.%s  live=%s" % (f["table"], f["column"], f["live"]))
                print("  The write path will refuse unless --i-accept-split-state is given.")
            print("=" * 78)
            conn.rollback()
            return 0

        if risk and not args.i_accept_split_state:
            print("\nREFUSED TO WRITE: another table still points at the old string.")
            for f in risk:
                print("   %s.%s  live=%s   (%s)"
                      % (f["table"], f["column"], f["live"], f["note"]))
            print("\nMoving this table alone turns a uniform wrong state into a split one.")
            print("Expanding the rename to those tables is a product-owner ruling.")
            print("To proceed anyway (recording that ruling): --i-accept-split-state")
            conn.rollback()
            return 3

        if not changes:
            print("\nIDEMPOTENT: 0 rows need to change. Nothing written.")
            conn.rollback()
            return 0

        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        jpath = args.journal or os.path.join(
            _HERE, "journal_map_meta_wafer_id_%s_%s.json" % (dbname, stamp))
        journal = {
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "database": dbname, "meta_table": META_TABLE,
            "target_table": args.target_table,
            "old_key": old_key_cols, "new_key": args.new_key, "separator": sep,
            "inverse_without_journal":
                "old_map_id = SELECT DISTINCT %s FROM %s WHERE %s = <map_id>"
                % ((" || '%s' || " % sep).join(old_key_cols), args.target_table, args.new_key),
            "changes": [{k: r[k] for k in ("row_id", "map_id", "map_pk",
                                           "business_key_val", "new_map_id", "new_map_pk")}
                        for r in changes],
        }
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)

        attempted, verified = apply_changes(cur, records, args.target_table)
        conn.commit()

        print("\n" + "=" * 78)
        print("  WROTE %d rows. Verified in the database: %d now carry the new spelling."
              % (attempted, verified))
        print("  journal: %s" % jpath)
        print("  undo:    python %s --revert %s --confirm-database %s"
              % (os.path.relpath(__file__), jpath, dbname))
        print("=" * 78)
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
