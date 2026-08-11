"""Retire indexes on `cell_sources` / `cell_overwrites` / `audit_logs` that no
query can use, WITHOUT touching the ones that only LOOK redundant.

WHY THIS IS A SEPARATE SCRIPT AND NOT A STEP IN `setup_db_performance.py`
------------------------------------------------------------------------
The mechanism is copied from the two files that already do this work - AUTOCOMMIT
session (CONCURRENTLY cannot run in a transaction block), `DROP INDEX
CONCURRENTLY IF EXISTS`, and "ask the catalogue whether it is gone" instead of
trusting that the statement did not raise. What is deliberately NOT copied is the
TRIGGER.

`setup_db_performance.py` is a make-the-database-right script that operators are
told to run routinely - the server logs literally instruct them to
("접두 인덱스 ... 가 없습니다. server/scripts/setup_db_performance.py 를 실행하세요").
Its Step 3.5 does drop indexes, but every one of those was superseded by an index
that the SAME script had just created a few steps earlier, so the drop is part of
that migration's own story and is safe to repeat on every run.

`idx_sources_lookup` is not that. It is a 267 MB standalone retirement judgement
with no replacement being built alongside it, and folding it into a routine script
means it fires on the next routine run with nobody deciding anything. So this
follows the project's OTHER precedent for drops -
`add_business_key_unique_index.py`: a named script, **read-only by default**,
that re-proves its case against the live catalogue before it writes.

That re-proof is the point. Measurements taken on one database are not facts about
another: on the QA box `idx_sources_by_source` and `idx_sources_confirmation` are
absent while production has them, so a hardcoded DROP list validated on QA could be
wrong on the machine it actually runs on. Every drop below is gated on a proof
evaluated at run time on the target database, and a name whose proof fails is
REFUSED BY NAME and the run continues.

WHAT IS NOT HERE
----------------
`ix_cell_sources_id`, `ix_cell_overwrites_id` and `ix_audit_logs_id` are exact
copies of their tables' primary-key indexes. They belong to a class that already
has a canonical owner:

    python server/migrations/add_business_key_unique_index.py --drop-redundant

That script rediscovers the whole class from `pg_index` (indkey + indclass +
indcollation + indoption identical to the primary key) rather than from a list of
names, which is why it finds 41 of them on the dev catalogue and not just the
three named here. Duplicating those three into this file would be a second
mechanism for one class of defect. Run that script for them.

USAGE
-----
    conda run -n assy_manager python server/migrations/drop_redundant_layering_indexes.py
    conda run -n assy_manager python server/migrations/drop_redundant_layering_indexes.py --apply

Default is read-only and opens the session with
`default_transaction_read_only = on`, so a pre-flight against production is
structurally incapable of writing rather than read-only by convention. Exit code
is 0 only when every listed index ended up either dropped or already absent.
"""
import argparse
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

TABLES = ("cell_sources", "cell_overwrites", "audit_logs")

# --- section 1: a strict LEFT PREFIX of a wider index -------------------------
# Key ORDER, not key membership: `(a, b, c)` is made redundant by `(a, b, c, d)`
# and never by `(b, a, c, d)`, so the proof below compares the ordered key list
# element by element together with each element's opclass, collation and sort
# direction. Two indexes over the same COLUMNS in a different order are not a
# prefix pair and this will not call them one.
RETIRE_PREFIX = {
    # (table_name, row_id, column_name) is a strict left prefix of the UNIQUE
    # (table_name, row_id, column_name, source_name). Verified on assy_qa
    # 2026-08-11 straight out of pg_index, not out of models.py:
    #     idx_sources_lookup         indkey = 2 3 4     indclass = 3126 x3
    #     idx_sources_lookup_source  indkey = 2 3 4 5   indclass = 3126 x4
    # both indcollation 100, both indoption 0, both btree, neither partial.
    #
    # The 14 production readers all use prefix columns only (census 2026-08-11);
    # the predicates that genuinely cannot use a table_name-leading index are
    # chain_replay's (table_name, source_name, ...) family, and those ride
    # `idx_sources_by_source`, which this does not touch.
    #
    # 🔴 The wider one is UNIQUE and this one is NOT, so the drop removes no
    # constraint - it is a space change, not a correctness change. The unique
    # index is also the upsert's ON CONFLICT arbiter
    # (crud.py:1755) and must never be the one dropped.
    "idx_sources_lookup": "cell_sources",
}

# --- section 2: no reader exists ---------------------------------------------
# Not provable from the catalogue - "nothing queries this column" is a fact about
# the CODE, established by census and only corroborated by the scan counter. The
# counter is therefore a REFUSAL gate here, never the reason.
RETIRE_UNUSED = {
    # `audit_logs.business_key`. Census 2026-08-11 over server/**, config, and
    # tests: zero equality/IN predicates anywhere. The only two predicates that
    # name the column are `IS NOT NULL` guards at main.py:862 and main.py:899,
    # and both are combined with (table_name, row_id), which
    # `idx_audit_row_history` serves - measured on the probe copy, the plan is
    # `Index Scan using idx_audit_row_history` with this index present AND
    # absent, same 8 buffers both ways.
    "ix_audit_logs_business_key": "audit_logs",
}


def quote_ident(name):
    """PostgreSQL folds unquoted identifiers, so `DROP INDEX ix_Foo` asks for
    `ix_foo`; with `IF EXISTS` that miss is swallowed and the caller reports a
    successful drop of something it never touched. Same reasoning, same helper,
    as `add_business_key_unique_index.quote_ident`."""
    return '"%s"' % name.replace('"', '""')


def index_facts(conn, table):
    """Every index on `table`, with its ordered key columns and per-key opclass,
    collation and sort direction. One query, so section 1's proof cannot read a
    different catalogue than the report prints."""
    rows = conn.execute(text("""
        SELECT i.relname, x.indisunique, x.indisprimary, x.indisvalid,
               x.indpred IS NOT NULL, x.indexprs IS NOT NULL, am.amname,
               x.indnkeyatts, x.indkey::text, x.indclass::text,
               x.indcollation::text, x.indoption::text,
               pg_relation_size(x.indexrelid), pg_get_indexdef(x.indexrelid),
               (SELECT string_agg(a.attname, ',' ORDER BY k.ord)
                  FROM unnest(x.indkey[0:x.indnkeyatts-1]) WITH ORDINALITY AS k(att, ord)
                  JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.att)
        FROM pg_index x
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_am am ON am.oid = i.relam
        WHERE n.nspname = 'public' AND c.relname = :t
    """), {"t": table}).fetchall()
    out = {}
    for r in rows:
        n = int(r[7])
        out[r[0]] = {
            "unique": r[1], "primary": r[2], "valid": r[3], "partial": r[4],
            "expr": r[5], "am": r[6], "nkeys": n,
            "key": r[8].split()[:n], "class": r[9].split()[:n],
            "coll": r[10].split()[:n], "option": r[11].split()[:n],
            "bytes": int(r[12]), "def": r[13],
            "cols": (r[14] or "").split(",") if r[14] else [],
        }
    return out


def covering_index(facts, name, exclude):
    """The index that makes `name` redundant, or `None` with the reason.

    Requires, for a candidate `w`: same table, btree, valid, not partial, not an
    expression index, at least one more key column, and the first N keys of `w`
    IDENTICAL to `name`'s N keys in attribute number, opclass, collation AND sort
    direction. Direction matters: a backward scan reverses the WHOLE key, so
    `(a, b DESC)` does not substitute for `(a, b)`.
    """
    me = facts[name]
    if me["unique"]:
        return None, ("it is UNIQUE - dropping it would change what the database "
                      "ACCEPTS, which is a correctness change, not a space change")
    if me["primary"]:
        return None, "it is the primary key"
    if me["partial"] or me["expr"]:
        return None, "it is partial or an expression index"
    if me["am"] != "btree":
        return None, f"it is a {me['am']} index, not btree"
    n = me["nkeys"]
    for wname, w in sorted(facts.items()):
        if wname == name or wname in exclude:
            continue
        if not w["valid"] or w["am"] != "btree" or w["partial"] or w["expr"]:
            continue
        if w["nkeys"] <= n:
            continue
        if (w["key"][:n] == me["key"][:n] and w["class"][:n] == me["class"][:n]
                and w["coll"][:n] == me["coll"][:n]
                and w["option"][:n] == me["option"][:n]):
            return wname, None
    return None, ("no valid non-partial btree index on this table has its key "
                  "columns as a strict left prefix IN THE SAME ORDER")


def stats_are_trustworthy(conn, table):
    """Is `idx_scan == 0` EVIDENCE here, or just an empty counter?

    Two different ways a zero lies, and both have bitten this project:

      1. `idx_scan` lives in the statistics collector and is lost to
         `pg_stat_reset()` or an unclean shutdown - the index is read every
         minute and the ledger says zero.
      2. The database is a fresh restore or a copy. Then EVERY counter is zero,
         including the ones on indexes nothing could run without, and "this
         index has no reads" is true of the whole table rather than of this
         index. Measured while preparing this script: on a `pg_restore`d copy
         `ix_audit_logs_business_key` read zero - and so did the primary key.

    So the check is comparative, not absolute: sum the scans across the table's
    OTHER indexes. If they are zero too, the counters have observed nothing and
    cannot support a retirement, whatever this one index says.
    """
    reset_at, age = conn.execute(text(
        "SELECT stats_reset, extract(epoch from now() - stats_reset)::bigint "
        "FROM pg_stat_database WHERE datname = current_database()")).first()
    peers = conn.execute(text(
        "SELECT coalesce(sum(idx_scan), 0) FROM pg_stat_user_indexes "
        "WHERE relname = :t"), {"t": table}).scalar()
    return reset_at, (int(age) if age is not None else None), int(peers or 0)


def run(apply=False, engine=None):
    from database.database import engine as default_engine
    engine = engine or default_engine

    print(f"=== Retire redundant layering indexes - "
          f"{'APPLY' if apply else 'CHECK (read-only)'} ===")
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    readonly_pinned = False
    dropped, refused, absent = [], [], []
    try:
        if not apply:
            # Structurally read-only, not read-only by convention - and thrown away
            # afterwards rather than reset, because `close()` returns a pooled
            # connection and the flag would ride it into the next checkout.
            conn.execute(text("SET SESSION default_transaction_read_only = on"))
            readonly_pinned = True

        db = conn.execute(text("SELECT current_database()")).scalar()
        print(f"database: {db}\n")

        facts = {t: index_facts(conn, t) for t in TABLES}
        drop_set = set(RETIRE_PREFIX) | set(RETIRE_UNUSED)

        # --- section 1 ------------------------------------------------------
        print("=== Section 1: strict left-prefix of a wider index ===")
        for name, table in sorted(RETIRE_PREFIX.items()):
            f = facts.get(table, {})
            if name not in f:
                print(f"  -- {name}: not present in this database - nothing to do")
                absent.append(name)
                continue
            wider, why = covering_index(f, name, drop_set)
            me = f[name]
            print(f"  {table}.{name}  ({me['bytes']/1024/1024:.1f} MB)")
            print(f"      this  : ({', '.join(me['cols'])})"
                  f"{'  UNIQUE' if me['unique'] else ''}")
            if not wider:
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            w = f[wider]
            print(f"      wider : {wider} ({', '.join(w['cols'])})"
                  f"{'  UNIQUE' if w['unique'] else ''}  "
                  f"{w['bytes']/1024/1024:.1f} MB")
            print(f"      proof : first {me['nkeys']} keys identical "
                  f"(attnum {me['key']} opclass {me['class']} "
                  f"collation {me['coll']} direction {me['option']})")
            print(f"      ROLLBACK: {rollback_ddl(me['def'])}")
            if apply:
                if _drop(conn, name):
                    dropped.append(name)
            else:
                print(f"      would run: DROP INDEX CONCURRENTLY IF EXISTS "
                      f"{quote_ident(name)};")

        # --- section 2 ------------------------------------------------------
        print(f"\n=== Section 2: no reader (census-established, counter-gated) ===")
        for name, table in sorted(RETIRE_UNUSED.items()):
            f = facts.get(table, {})
            if name not in f:
                print(f"  -- {name}: not present in this database - nothing to do")
                absent.append(name)
                continue
            me = f[name]
            reset_at, age, peers = stats_are_trustworthy(conn, table)
            scans = conn.execute(text(
                "SELECT idx_scan FROM pg_stat_user_indexes WHERE indexrelname = :n"),
                {"n": name}).scalar()
            print(f"  {table}.{name}  ({me['bytes']/1024/1024:.1f} MB)  "
                  f"keys=({', '.join(me['cols'])})  idx_scan={scans}")
            print(f"      counters: {age if age is not None else 'never'} s since "
                  f"reset ({reset_at or 'no reset recorded'}), "
                  f"{peers} scans across all indexes on {table}")
            if me["unique"]:
                why = "it is UNIQUE - that is a constraint, not an index"
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            if peers == 0:
                why = ("every index on this table reads zero, so the counters have "
                       "observed no traffic at all - a fresh restore or a reset "
                       "statistics file. This zero is absence of evidence, not "
                       "evidence of absence. Run against a database that has served "
                       "real traffic")
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            if scans:
                why = (f"idx_scan = {scans}, not 0 - something on THIS database "
                       f"reads it. The census that justified this drop does not "
                       f"describe this installation")
                print(f"      !! REFUSED: {why}")
                refused.append((name, why))
                continue
            print(f"      ROLLBACK: {rollback_ddl(me['def'])}")
            if apply:
                if _drop(conn, name):
                    dropped.append(name)
            else:
                print(f"      would run: DROP INDEX CONCURRENTLY IF EXISTS "
                      f"{quote_ident(name)};")

        # --- everything else that LOOKS redundant, reported and left alone ---
        print(f"\n=== Prefix-redundant indexes NOT being dropped ===")
        print("  (structurally redundant, deliberately kept - a small hot index "
              "replaced by a much larger one is a slower read, not a saving)")
        for table in TABLES:
            for name in sorted(facts[table]):
                if name in drop_set or facts[table][name]["primary"]:
                    continue
                wider, _ = covering_index(facts[table], name, drop_set)
                if wider:
                    me = facts[table][name]
                    print(f"  {table}.{name} ({me['bytes']/1024/1024:.1f} MB) "
                          f"is a prefix of {wider} "
                          f"({facts[table][wider]['bytes']/1024/1024:.1f} MB) - KEPT")

    finally:
        if readonly_pinned:
            conn.invalidate()
        conn.close()

    print(f"\nSummary: {len(dropped)} dropped, {len(refused)} refused, "
          f"{len(absent)} already absent.")
    for name, why in refused:
        print(f"  !! {name}: {why}")
    if not apply:
        print("Nothing was written.")
    return {"dropped": dropped, "refused": refused, "absent": absent}


def rollback_ddl(indexdef):
    """The exact statement that puts this index back, handed to the operator
    BEFORE the drop rather than after they need it."""
    return indexdef.replace("CREATE INDEX ", "CREATE INDEX CONCURRENTLY ", 1) \
                   .replace("CREATE UNIQUE INDEX ", "CREATE UNIQUE INDEX CONCURRENTLY ", 1) + ";"


_DROPPED = set()


def _drop(conn, name):
    """Drop once, then ask the CATALOGUE whether it is gone. `IF EXISTS` turns a
    name that matches nothing into a silent success, so the return code is not
    evidence - the same standard `add_business_key_unique_index.drop_redundant_indexes`
    holds itself to."""
    if name in _DROPPED:
        return None
    _DROPPED.add(name)
    t0 = time.time()
    try:
        conn.execute(text("DROP INDEX CONCURRENTLY IF EXISTS public."
                          + quote_ident(name)))
    except Exception as e:
        print(f"      !! FAILED: {str(e).strip().splitlines()[0]}")
        return None
    still = conn.execute(text(
        "SELECT 1 FROM pg_class i JOIN pg_namespace n ON n.oid = i.relnamespace "
        "WHERE n.nspname='public' AND i.relname = :n"), {"n": name}).first()
    if still:
        print("      !! FAILED: DROP reported success but the index is still "
              "in the catalogue")
        return None
    print(f"      dropped ({time.time() - t0:.2f}s)")
    return name


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true",
                   help="actually drop. Without it the run is read-only.")
    args = p.parse_args(argv)
    out = run(apply=args.apply)
    return 1 if out["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
