"""D3 - make "one row per business key" an invariant the DATABASE enforces.

WHY THIS EXISTS
---------------
`business_key_val` is the identity of a row for every write path in this system, and
until now **nothing enforced that it is unique**. Measured on the dev catalogue
(2026-08-07): 50 indexes mention `business_key_val` across 25 tables and
`indisunique` is true on **zero** of them; there is no unique/primary-key constraint on
the column anywhere. Uniqueness held only because the write path happened to look
before it inserted.

That "happened to" is the whole problem. `apply_batch_updates` resolves identity with a
prefetch whose proof of absence is valid against *this session's* loop and nothing else
(`crud.ProbedIdentity`, `crud._absence_is_proven`). A second OS process committing the
same key inside the window produces **two rows with one business key, silently, with no
error** - reproduced with two real processes at the production chunk size of 1,000 items,
window 2.4 s (`agent_workspace/reports/Server_M2_race_reachability.md`). There is no
cross-process lock to fall back on: `grep -rn "pg_advisory" server/` returns nothing, and
the only serialisation that exists is a `threading.Lock` whose own comment says
cross-process exclusion is out of scope.

A unique index converts that silent duplicate into an `IntegrityError`, which
`apply_batch_updates` now catches, re-prefetches and merges (see `crud.py`,
`_is_business_key_unique_violation`). Index first, recovery second: without the index the
recovery never fires, and without the recovery the index turns a race into a failed batch.

WHAT ABOUT D2 ("surplus 389 rows, which D3 requires first")?
------------------------------------------------------------
**On the dev box there is nothing to clean.** Census 2026-08-07 over all 25 tables
carrying the column: 52,725 rows, `count(business_key_val) == count(DISTINCT
business_key_val)` in every single one, surplus = 0. Measured independently twice. The
board's older duplicate figures (`bonding_log` 117, `wafer_process` 43,
`inventory_master` 163) are **absent from this database today** - cleaned, or re-seeded;
nobody knows which. So D2 is not a blocker *here* and the next reader should not re-block
on it.

⚠️ THIS BOX IS A SIMULATION AND PRODUCTION IS A DIFFERENT MACHINE. Nothing above is a
claim about production. `CREATE UNIQUE INDEX` fails outright if even one duplicate
exists, so this script **measures before it builds, per table**, and a table that cannot
take the index is **refused by name and the run continues** - it is never aborted whole
and never skipped in silence. Run `--check` on production first; it opens a read-only
session and cannot write.

NULLs ARE DELIBERATELY STILL ALLOWED
------------------------------------
A plain PostgreSQL UNIQUE index treats NULLs as distinct, so any number of rows may carry
`business_key_val IS NULL`. That is required, not tolerated: `crud.create_empty_rows_batch`
inserts rows with a `row_id` and no business key, and `NULLS NOT DISTINCT` (PG15+) would
break the "add empty row" button on the second click.

⚠️ EMPTY STRING WAS A DIFFERENT MATTER, AND THIS FILE USED TO GET IT WRONG. It said no
path wrote `''` (true of the dev census: zero such rows) and that if one appeared "the
collision is the correct answer". Both halves were wrong.

A path did write it: any payload whose key column arrived blank went through
`crud._update_row_business_key`, which stored the stripped value however empty it was.
And the collision was NOT the correct answer, because `''` is the shared identity of
every KEYLESS row rather than a duplicate of one real identity. Measured on this
workstation against real PostgreSQL with this index installed: five such rows in one
batch collide with EACH OTHER, the `IntegrityError` recovery below cannot help - it
re-reads a database in which none of them was ever committed, so the replay reproduces
the identical collision - and after `BK_CONFLICT_MAX_RETRIES` the whole batch is
refused. **0 rows written, on each of three pushes.** One source file with a blank key
column would stop that table's ingestion outright: loud, but stopped.

`crud._update_row_business_key` now stores **NULL** for a blank key column, which the
paragraph above already establishes is safe here - a plain UNIQUE index treats NULLs as
distinct, so any number of keyless rows may coexist. That is deliberately the whole fix.
No synthetic identity is minted for such rows: they arise only from manual grid work,
never from ingestion (product owner ruling 2026-08-07), and manual work addresses rows
by `row_id`, so nothing needs a handle in `business_key_val`. The live database already
holds them - measured 2026-08-07: 11 rows in `wafer_map_metadata` and 10 in
`production_plan`, all from manual merges, and none of them can block this index.
See `data_model.md` §3.1-bis and `server/tests/test_blank_business_key_is_null.py`.

SECTION 2 - INDEXES THAT DUPLICATE THEIR OWN PRIMARY KEY (independent of section 1)
----------------------------------------------------------------------------------
`Column(..., primary_key=True, index=True)` makes SQLAlchemy emit a second index that the
primary key's own unique index already provides. Both are plain btrees over the same
column with the same opclass and collation, so the extra one is maintained on every write
and read by nothing - the planner can always use the PK index instead.

Measured on the dev catalogue 2026-08-07: **29 such indexes, 382.3 MB**, led by
`ix_cell_sources_id` (314 MB, identical to `cell_sources_pkey`), `ix_audit_logs_id`
(61 MB) and `ix_cell_overwrites_id` (3.6 MB). The three obvious ones come from
`models.py` `AuditLog.id` / `CellOverwrite.id` / `CellSource.id`; the other 26 come from
**two more declarations of the same mistake** that a per-class reading misses -
`FileIngestionLog.id`, and the shared dynamic-table column
`Column("row_id", String, primary_key=True, index=True)`, which reproduces it once per
dynamic table. Their sizes are small on this box and will not be in production, where
`bonding_map` alone is ~1.76M rows.

This section does **not** work from that list. It rediscovers the set from `pg_index` at
run time under a proof that holds per index: not unique, not the primary key, valid, no
predicate, no expression, btree, and `indkey`/`indclass`/`indcollation` **identical** to
the table's primary-key index. A second, independent gate requires the name to match
SQLAlchemy's auto-generated `ix_<table>_<column>` form. Anything structurally redundant
under a hand-written name is REPORTED AND LEFT ALONE - a name we did not generate is a
name someone chose on purpose, and dropping the wrong index on a 14 GB database is not
repaired by re-running.

USAGE
-----
    conda run -n assy_manager python server/migrations/add_business_key_unique_index.py
    conda run -n assy_manager python server/migrations/add_business_key_unique_index.py --apply
    ... --apply --table bonding_map --table dt_log
    ... --drop-redundant            # section 2 only
    ... --apply --drop-redundant    # both

Default is read-only: it reports both sections and writes nothing. `--apply` runs
section 1, `--drop-redundant` runs section 2; they are independent so an operator can
take one and not the other. Exit code is 0 only when every table in scope ended up
covered by a valid unique index and nothing in section 2 failed.

`CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY` cannot run inside a transaction
block, so the session runs with `isolation_level="AUTOCOMMIT"` (same shape as
`server/scripts/setup_db_performance.py`). CONCURRENTLY is not optional: `bonding_map` is
~1.76M rows in production and a plain build locks writes for the duration.

READ-ONLY BY DEFAULT - AND THAT CLAIM USED TO BE FALSE. See the guard section below.
"""
import argparse
import hashlib
import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text  # noqa: E402

INDEX_PREFIX = "uq_bk_"
_MAX_IDENTIFIER = 63
BK_COLUMN = "business_key_val"


# =============================================================================
# The read-only guard
# =============================================================================
# 🔴 THE SPELLING HERE IS NOT NEW AND MUST NOT BE RE-INVENTED. It is the one
# `server/scripts/diagnose_wal_headroom.py` (class `RO`) and
# `server/scripts/diagnose_slow_after_ingest.py` already use: the setting goes in as a
# CONNECTION OPTION, which the server applies before this session's first transaction
# exists and re-applies to every transaction after it.
#
# WHAT THIS FILE USED TO DO, AND WHAT WAS ACTUALLY TRUE ABOUT IT
#
#     conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
#     conn.execute(text("SET SESSION default_transaction_read_only = on"))
#
# ⚠️ IN THAT ORDER, IT DID ENGAGE - do not read the paragraph below as "the old code
# was writing to production", because it was not. Measured on the isolated `assy_qa`
# (PostgreSQL 18.3, SQLAlchemy 2.0.49, psycopg2 2.9.11) on 2026-08-13:
# `execution_options` flips psycopg2's `autocommit` to True on this very Connection, so
# there is no open transaction for the SET to be trapped inside. The session variable
# took, `transaction_read_only` read `on`, and a CREATE was refused - still refused
# after a rollback.
#
# 🔴 THE DEFECT IS THAT ITS ONE SAFETY PROPERTY RESTED ON A SETTING THAT IS HERE FOR AN
# UNRELATED REASON. AUTOCOMMIT is in this file because `CREATE INDEX CONCURRENTLY`
# cannot run in a transaction block; the guard silently borrowed it. Remove it, reorder
# those two lines, or run one statement before the `execution_options`, and the SET
# lands inside an implicit transaction that began under the old default and keeps it.
# Measured in that arrangement, same database, same session:
#
#     after SET       default_transaction_read_only = on   <- the variable one checks
#     after SET       transaction_read_only         = off  <- the one PostgreSQL enforces
#     after rollback  transaction_read_only         = off  <- the SET discarded outright
#     CREATE TABLE on that connection                      ACCEPTED
#
# AND NOTHING HERE EVER READ THE FLAG BACK, so those two arrangements were
# indistinguishable from inside the script: it reported itself protected either way.
# An operator was handed this as safe on the strength of a sentence, not a check.
#
# THE REPAIR IS THEREFORE TWO THINGS, NOT ONE:
#   1. Arm at CONNECT time, which is independent of isolation level. Measured `on`
#      with writes refused under BOTH autocommit and the default isolation, before and
#      after a rollback.
#   2. Read `transaction_read_only` back and REFUSE. `default_transaction_read_only`
#      is deliberately NOT what gets checked - it reads `on` in both arrangements
#      above, including the one that accepts writes.
#
# WHAT IS DELIBERATELY *NOT* IN THE OPTIONS. `diagnose_wal_headroom.py` also pins
# `statement_timeout` / `lock_timeout` / `idle_in_transaction_session_timeout`. This
# script has never had any of them, and `duplicate_census` is a full GROUP BY over
# every table carrying the column on a 14 GB database - adding a timeout here would
# turn a pre-flight that works today into one that fails, which is a separate decision
# from arming the guard. `client_encoding` matches `database/database.py`.
READONLY_OPTIONS = ("-c default_transaction_read_only=on "
                    "-c client_encoding=utf8")

#: Present in every refusal, so a caller can pin the reason rather than the exception
#: type (same discipline as `db_safety.REFUSAL_MARKER`).
READONLY_REFUSAL = "[read-only guard] REFUSED"


def open_readonly_engine(url: str = None):
    """An engine every one of whose transactions is read-only, armed at connect time.

    `NullPool` is load-bearing, not tidiness: these connections must never be handed to
    anything else. It is also what retired the `invalidate()` dance this file used to
    need - the old pattern set a session variable on a connection borrowed from the
    APPLICATION pool, so returning it poisoned the next checkout and an apply run that
    followed a check run in the same process failed every CREATE with
    `ReadOnlySqlTransaction`. An engine of our own has no next checkout to poison.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool
    if url is None:
        from database.database import SQLALCHEMY_DATABASE_URL
        url = SQLALCHEMY_DATABASE_URL
    return create_engine(
        url, poolclass=NullPool,
        connect_args={"options": READONLY_OPTIONS,
                      "application_name": "assy_bk_index_check"})


def assert_readonly(conn):
    """Refuse unless POSTGRESQL ITSELF reports that this connection cannot write.

    A guard that cannot verify itself is the defect this exists to end, so the answer
    comes from the server rather than from the fact that an option string was passed.
    """
    try:
        armed = conn.execute(text("SHOW transaction_read_only")).scalar()
    except Exception as exc:
        raise RuntimeError(
            f"{READONLY_REFUSAL}: `transaction_read_only` could not be read from this "
            f"connection ({type(exc).__name__}: {str(exc).strip().splitlines()[0]}). "
            f"This is a PostgreSQL operator script and it will not run a pass it "
            f"cannot prove is read-only.") from exc
    if str(armed).lower() != "on":
        raise RuntimeError(
            f"{READONLY_REFUSAL}: PostgreSQL reports transaction_read_only={armed!r} "
            f"on the connection this run counts with. Refusing to run a pre-flight "
            f"that is not actually protected.")
    return conn


def assert_writable(conn):
    """The mirror, for `--apply`. Fails BEFORE the first table instead of during it.

    This is the direct net for the incident the old code left a comment about: a
    read-only flag inherited from a pooled connection used to surface as a
    `ReadOnlySqlTransaction` on every individual CREATE/DROP, halfway through a run.
    """
    armed = conn.execute(text("SHOW transaction_read_only")).scalar()
    if str(armed).lower() != "off":
        raise RuntimeError(
            f"{READONLY_REFUSAL} (inverted): --apply was asked for but PostgreSQL "
            f"reports transaction_read_only={armed!r} on the connection that would do "
            f"the writing. Nothing was attempted.")
    return conn


def open_readonly_connection(engine):
    """THE ONLY DOOR to a counting-pass connection: connect, then prove it, or refuse."""
    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        assert_readonly(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def unique_index_name(table: str) -> str:
    """`uq_bk_<table>`, folded to PostgreSQL's 63-byte identifier limit.

    Same discipline (and same limit) as `virtual_join_config.required_index_name` and
    `value_suggest.suggest_index_name`: when the natural name is too long, truncate and
    append a digest of the FULL name so two long table names cannot collide onto one
    index. Lower-cased because PostgreSQL folds unquoted identifiers, and a name we
    report differently from the one the catalogue holds makes the idempotency check
    below lie.
    """
    base = f"{INDEX_PREFIX}{table}".lower()
    if len(base.encode("utf-8")) <= _MAX_IDENTIFIER:
        return base
    digest = hashlib.sha1(table.encode("utf-8")).hexdigest()[:8]
    keep = _MAX_IDENTIFIER - len(INDEX_PREFIX) - len(digest) - 1
    return f"{INDEX_PREFIX}{table.lower()[:keep]}_{digest}"


def tables_with_business_key(conn) -> list:
    """Every public table that actually has the column, asked of the live catalogue.

    Not read from `table_config.json`: config declares intent, and this migration must
    act on what the database HAS. A table declared but never created, or created under
    an older schema, would otherwise turn into a crash or a silent miss.
    """
    rows = conn.execute(text("""
        SELECT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND c.column_name = :col
          AND t.table_type = 'BASE TABLE'
        ORDER BY c.table_name
    """), {"col": BK_COLUMN}).fetchall()
    return [r[0] for r in rows]


def existing_unique_index(conn, table: str):
    """`(name, is_valid)` of a unique index on exactly `(business_key_val)`, or None.

    The three exclusions are the ones `virtual_join_config` documents, and they matter
    for the same reason here:
      * `indpred IS NOT NULL` - a partial index is unique only inside its predicate.
      * `indexprs IS NOT NULL` - unique on an expression, not on the column.
      * single key column - a unique index on `(business_key_val, row_id)` is NOT what we
        want; `row_id` is already unique so the pair is trivially unique and constrains
        nothing. `idx_<t>_bk` has exactly that shape, which is why it can never be
        mistaken for the guard even if someone makes it unique.
    `indisvalid` is RETURNED rather than filtered, because an invalid leftover is the
    trap this script has to speak about instead of walking past.
    """
    row = conn.execute(text("""
        SELECT i.relname, x.indisvalid
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = x.indkey[0]
        WHERE n.nspname = 'public'
          AND c.relname = :t
          AND x.indisunique
          AND x.indpred IS NULL
          AND x.indexprs IS NULL
          AND x.indnatts = 1
          AND a.attname = :col
        ORDER BY x.indisvalid DESC, i.relname
        LIMIT 1
    """), {"t": table, "col": BK_COLUMN}).first()
    return (row[0], bool(row[1])) if row else None


def index_exists(conn, name: str):
    """`(exists, is_valid)` for an index by NAME - the `IF NOT EXISTS` blind spot.

    `CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS` looks only at the NAME. A build
    that was cancelled or that hit a duplicate leaves an **invalid** index behind under
    exactly that name, so a re-run reports "already exists" and enforces nothing. That
    is a silent hole dressed as idempotency, so it is checked separately and named.
    """
    row = conn.execute(text("""
        SELECT x.indisvalid
        FROM pg_class i
        JOIN pg_namespace n ON n.oid = i.relnamespace
        JOIN pg_index x ON x.indexrelid = i.oid
        WHERE n.nspname = 'public' AND i.relname = :n
    """), {"n": name}).first()
    return (True, bool(row[0])) if row else (False, False)


def duplicate_census(conn, table: str, sample: int = 5) -> dict:
    """What the table looks like BEFORE any DDL is attempted.

    Returns rows / null keys / duplicated key count / surplus rows / a few offending
    keys. The surplus is `rows_in_duplicate_groups - number_of_groups`, i.e. exactly how
    many rows would have to disappear for the index to build - the number an operator
    needs in order to decide whether to clean or to refuse.

    The GROUP BY walks the existing non-unique `business_key_val` index rather than the
    heap, so the cost is index-sized, not row-width-sized. It is still a full pass and
    this is a one-shot operator action, not a request path.
    """
    t0 = time.time()
    n, nbk = conn.execute(text(
        f'SELECT count(*), count({BK_COLUMN}) FROM public."{table}"')).first()
    groups, dup_rows = conn.execute(text(f'''
        SELECT count(*), coalesce(sum(c), 0) FROM (
            SELECT {BK_COLUMN}, count(*) AS c FROM public."{table}"
            WHERE {BK_COLUMN} IS NOT NULL
            GROUP BY {BK_COLUMN} HAVING count(*) > 1
        ) s''')).first()
    keys = []
    if groups:
        keys = [r[0] for r in conn.execute(text(f'''
            SELECT {BK_COLUMN} FROM public."{table}"
            WHERE {BK_COLUMN} IS NOT NULL
            GROUP BY {BK_COLUMN} HAVING count(*) > 1
            ORDER BY count(*) DESC LIMIT :k'''), {"k": sample}).fetchall()]
    return {
        "table": table,
        "rows": int(n),
        "null_keys": int(n) - int(nbk),
        "dup_keys": int(groups),
        "surplus": int(dup_rows) - int(groups),
        "sample": keys,
        "elapsed": time.time() - t0,
    }


# --- verdicts -----------------------------------------------------------------
# Named states, so the summary can say WHICH tables ended where instead of printing a
# count. A count of refusals is not actionable; a list of names is.
OK_ALREADY = "already_enforced"   # a valid unique index was already there
OK_CREATED = "created"            # this run built it
REFUSED_DUPLICATES = "refused_duplicates"      # the data cannot take the index
REFUSED_INVALID_INDEX = "refused_invalid_index"  # dead leftover holds the name
FAILED = "failed"                 # the DDL itself errored


def plan_table(conn, table: str) -> dict:
    """Read-only verdict for one table. **No DDL, ever.** Shared by check and apply.

    Having one function decide means `--check` on production cannot disagree with what
    `--apply` will then do - the pre-flight is the same judgement, not a second
    implementation of it.
    """
    name = unique_index_name(table)
    census = duplicate_census(conn, table)
    result = dict(census, index_name=name)

    present = existing_unique_index(conn, table)
    if present and present[1]:
        result["verdict"] = OK_ALREADY
        result["index_name"] = present[0]
        return result

    exists, valid = index_exists(conn, name)
    if exists and not valid:
        result["verdict"] = REFUSED_INVALID_INDEX
        return result

    if census["dup_keys"]:
        result["verdict"] = REFUSED_DUPLICATES
        return result

    result["verdict"] = None  # buildable
    return result


def build_index(conn, table: str, name: str) -> tuple:
    """Create the index and CHECK THAT IT CAME OUT VALID. Returns `(verdict, detail)`.

    A CONCURRENTLY build can return without raising and still leave an invalid index
    (that is what happens when the second pass finds a row inserted meanwhile that
    violates uniqueness). Reporting success on the strength of "the statement did not
    raise" would ship exactly the silent non-enforcement this migration exists to end.
    """
    ddl = (f'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {quote_ident(name)} '
           f'ON public.{quote_ident(table)} ({BK_COLUMN})')
    try:
        conn.execute(text(ddl))
    except Exception as e:  # duplicates that appeared between census and build land here
        return FAILED, str(e).strip().splitlines()[0]
    exists, valid = index_exists(conn, name)
    if not exists:
        return FAILED, "index absent after CREATE reported success"
    if not valid:
        return FAILED, (f"index {name} was built INVALID - it enforces nothing. "
                        f"DROP INDEX CONCURRENTLY {name}; then re-run after cleaning "
                        f"the duplicates PostgreSQL names in the server log")
    return OK_CREATED, ddl


# --- section 2: indexes that duplicate their own primary key ------------------

# SQLAlchemy's auto-generated index name for `Column(..., index=True)`. The SECOND gate,
# and it is deliberately not the load-bearing one: the catalogue query below is the
# proof, this only refuses to act on names a human chose. `ix_` + at least one character.
_SQLALCHEMY_INDEX_NAME = "ix_"

# Every clause here is doing work; none is decoration.
#   NOT indisunique / NOT indisprimary  the PK index itself must never be a candidate
#   indisvalid                          an invalid index is a different problem (§1)
#   indpred IS NULL                     a partial index covers a different row set
#   indexprs IS NULL                    an expression index covers a different key
#   amname = 'btree' on BOTH            a GIN/BRIN index over the same column is NOT the
#                                       same index - different operators, different plans
#   indkey / indclass / indcollation    identical key columns, IN THE SAME ORDER, with
#   / indoption                         the same operator class, collation, and SORT
#                                       DIRECTION. Equality of `indkey` alone would call
#                                       `(a, b)` and `(b, a)` the same index; equality
#                                       without `indclass` would drop a
#                                       `text_pattern_ops` index whose whole purpose is
#                                       the prefix search the PK index cannot serve; and
#                                       equality without `indoption` would drop an index
#                                       on `(a, b DESC)` as a "duplicate" of a plain
#                                       `(a, b)` primary key. A backward scan reverses
#                                       the WHOLE key and therefore does not substitute
#                                       for MIXED ordering - that one is a wrongly
#                                       dropped index on production, which is the single
#                                       outcome in this script that a re-run cannot undo.
#                                       `indoption` also carries NULLS FIRST/LAST.
_PK_DUPLICATE_SQL = """
SELECT c.relname, d.relname, p.relname,
       pg_relation_size(xd.indexrelid),
       pg_get_indexdef(xd.indexrelid),
       pg_get_indexdef(xp.indexrelid)
FROM pg_index xd
JOIN pg_class d ON d.oid = xd.indexrelid
JOIN pg_class c ON c.oid = xd.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am amd ON amd.oid = d.relam
JOIN pg_index xp ON xp.indrelid = xd.indrelid AND xp.indisprimary
JOIN pg_class p ON p.oid = xp.indexrelid
JOIN pg_am amp ON amp.oid = p.relam
WHERE n.nspname = 'public'
  AND NOT xd.indisunique
  AND NOT xd.indisprimary
  AND xd.indisvalid
  AND xd.indpred IS NULL AND xd.indexprs IS NULL
  AND xp.indpred IS NULL AND xp.indexprs IS NULL
  AND amd.amname = 'btree' AND amp.amname = 'btree'
  AND xd.indkey = xp.indkey
  AND xd.indclass = xp.indclass
  AND xd.indcollation = xp.indcollation
  AND xd.indoption = xp.indoption
ORDER BY pg_relation_size(xd.indexrelid) DESC
"""


def quote_ident(name: str) -> str:
    """Double-quote an identifier for interpolation into DDL.

    Unquoted identifiers are CASE-FOLDED by PostgreSQL, so `DROP INDEX ... ix_Foo_Id`
    asks for `ix_foo_id`, which does not exist - and `IF EXISTS` then swallows the miss
    while the caller reports a successful drop. The catalogue hands us the exact stored
    spelling; quoting is what preserves it.
    """
    return '"%s"' % name.replace('"', '""')


def redundant_pk_indexes(conn) -> list:
    """Every index proven to be a second copy of its table's primary-key index.

    Returns dicts with both definitions carried along, because the operator reading the
    report should be able to compare the two DDL strings themselves rather than trust
    the verdict. `droppable` is the name gate; `False` means report only.
    """
    out = []
    for tbl, dup, pk, size, dup_def, pk_def in conn.execute(text(_PK_DUPLICATE_SQL)):
        out.append({
            "table": tbl, "index": dup, "pk_index": pk, "bytes": int(size),
            "index_def": dup_def, "pk_def": pk_def,
            "droppable": dup.startswith(_SQLALCHEMY_INDEX_NAME) and
                         len(dup) > len(_SQLALCHEMY_INDEX_NAME),
        })
    return out


def drop_redundant_indexes(conn, apply: bool, write_conn=None) -> dict:
    """Report - and, with `apply`, drop - the PK-duplicating indexes.

    Idempotent in both directions: the discovery query returns nothing once they are
    gone, and the DDL carries `IF EXISTS` so a concurrent operator running the same
    script is a no-op rather than an error.

    TWO CONNECTIONS, ON PURPOSE. `conn` DISCOVERS and CONFIRMS (catalogue reads);
    `write_conn` DROPS. `run` hands in the read-only connection as `conn` and the
    writable one as `write_conn`, so the pass that decides what is redundant physically
    cannot issue the DDL it is deciding about, and the post-drop confirmation comes off
    a connection that could not have caused the state it is reading. Omitting
    `write_conn` sends the drops through `conn`, which is what a direct caller holding
    one writable connection wants - and cannot become a silent bypass, because the
    server refuses the DDL outright if that connection is the read-only one.
    """
    wconn = write_conn if write_conn is not None else conn
    found = redundant_pk_indexes(conn)
    total = sum(r["bytes"] for r in found)
    print(f"\n=== Section 2: indexes duplicating their own PRIMARY KEY ===")
    print(f"Found {len(found)}, {total / 1024 / 1024:.1f} MB total")
    if not found:
        print("Nothing to do.")
        return {"found": [], "dropped": [], "skipped": [], "failed": []}

    dropped, skipped, failed = [], [], []
    for r in found:
        size_mb = r["bytes"] / 1024 / 1024
        if not r["droppable"]:
            # A hand-written name. Structurally redundant, but somebody named it, so it
            # is reported and left in place - see the module docstring.
            skipped.append(r)
            print(f"  -- {r['table']}.{r['index']} ({size_mb:.1f} MB): redundant with "
                  f"{r['pk_index']}, but the name is not `ix_*` - LEFT ALONE, decide by "
                  f"hand")
            continue
        if not apply:
            print(f"  would drop {r['index']:44s} ({size_mb:8.1f} MB)  == {r['pk_index']}")
            continue
        try:
            wconn.execute(text("DROP INDEX CONCURRENTLY IF EXISTS public."
                               + quote_ident(r["index"])))
        except Exception as e:
            failed.append(dict(r, error=str(e).strip().splitlines()[0]))
            print(f"  !! FAILED   {r['index']}: {failed[-1]['error']}")
            continue
        # 🔴 "The statement did not raise" is not "the index is gone" - the same standard
        # `build_index` already holds itself to. `IF EXISTS` turns a name that does not
        # match anything into a silent success, so a reported "Reclaimed 314.0 MB" could
        # have reclaimed nothing. Ask the catalogue instead of the return code.
        still_there, _valid = index_exists(conn, r["index"])
        if still_there:
            failed.append(dict(r, error="DROP reported success but the index is still "
                                        "in the catalogue"))
            print(f"  !! FAILED   {r['index']}: {failed[-1]['error']}")
            continue
        dropped.append(r)
        print(f"  dropped     {r['index']:44s} ({size_mb:8.1f} MB)")

    if apply:
        print(f"Reclaimed {sum(r['bytes'] for r in dropped) / 1024 / 1024:.1f} MB "
              f"across {len(dropped)} indexes.")
    else:
        would = sum(r["bytes"] for r in found if r["droppable"])
        print(f"Nothing was written. {would / 1024 / 1024:.1f} MB would be reclaimed.")
    return {"found": found, "dropped": dropped, "skipped": skipped, "failed": failed}


def run(apply: bool, only: list = None, engine=None, drop_redundant: bool = False,
        readonly_engine=None) -> dict:
    """Section 1 and section 2, counted on a read-only connection and applied on another.

    🔴 TWO ENGINES, AND THE SPLIT IS THE SAFETY PROPERTY. The counting pass
    (`tables_with_business_key`, `plan_table` -> `duplicate_census` /
    `existing_unique_index` / `index_exists`, `redundant_pk_indexes`) is only ever
    handed `conn`, which comes from `open_readonly_connection` and has been PROVEN
    read-only by the server. The writable engine is resolved and connected to only
    inside `if writes:` - so in a check-only run this process never resolves it, never
    opens it, and has no writable connection for the counting pass to reach for.

    Both passes ask the same questions of the same catalogue through the same
    functions, so `--check` against production cannot disagree with what `--apply`
    would then do; that was already true and the split does not break it.

    `readonly_engine` exists for callers injecting a stub. It does not skip
    verification: whatever is passed still has to answer `SHOW transaction_read_only`
    with `on` or the run refuses.
    """
    writes = apply or drop_redundant
    print(f"=== D3 - section 1 {'APPLY' if apply else 'CHECK (read-only)'}, "
          f"section 2 {'DROP' if drop_redundant else 'CHECK (read-only)'} ===")

    results = []
    redundant = None
    own_ro_engine = readonly_engine is None
    if own_ro_engine:
        # Derived from the writable engine's URL when one was handed in, so an injected
        # engine still decides WHICH database is counted - only not whether the counting
        # connection may write.
        url = None
        if engine is not None:
            url = getattr(engine, "url", None)
            if url is None:
                raise TypeError(
                    "run(engine=...) received an object with no `.url`, so no read-only "
                    "engine can be derived from it. Inject `readonly_engine=` as well.")
            url = str(url)
        readonly_engine = open_readonly_engine(url)

    try:
        conn = open_readonly_connection(readonly_engine)
    except BaseException:
        # A refusal must not leak the engine it refused on.
        if own_ro_engine:
            readonly_engine.dispose()
        raise

    wconn = None
    try:
        if writes:
            # Resolved HERE and nowhere earlier. AUTOCOMMIT because CREATE/DROP INDEX
            # CONCURRENTLY cannot run inside a transaction block.
            if engine is None:
                from database.database import engine as default_engine
                engine = default_engine
            wconn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
            # Before the first table, not on the twelfth: an apply that cannot write
            # must say so up front.
            assert_writable(wconn)

        tables = tables_with_business_key(conn)
        if only:
            missing = [t for t in only if t not in tables]
            for t in missing:
                print(f" !! {t}: no `{BK_COLUMN}` column in this database - skipped")
            tables = [t for t in tables if t in only]

        print(f"Tables carrying `{BK_COLUMN}`: {len(tables)}\n")
        header = (f"{'table':38s} {'rows':>10s} {'nullbk':>8s} {'dupkeys':>8s} "
                  f"{'surplus':>8s}  verdict")
        print(header)

        for t in tables:
            r = plan_table(conn, t)          # read-only connection. Always.
            if r["verdict"] is None:
                if apply:
                    # The writable one, and only here.
                    verdict, detail = build_index(wconn, t, r["index_name"])
                    r["verdict"] = verdict
                    r["detail"] = detail
                else:
                    r["verdict"] = "buildable"
            print(f"{t:38s} {r['rows']:10d} {r['null_keys']:8d} {r['dup_keys']:8d} "
                  f"{r['surplus']:8d}  {r['verdict']}")
            results.append(r)

        section1 = _report_section1(results, apply)

        # Section 2 shares the connections but nothing else. It never reads section 1's
        # verdicts and section 1 never reads its result, so `--drop-redundant` alone is
        # a complete, meaningful run. `wconn` is None unless something is being written,
        # in which case the drops fall back to the read-only `conn` and the server
        # refuses them - a bypass would have to survive PostgreSQL, not just review.
        redundant = drop_redundant_indexes(conn, drop_redundant, write_conn=wconn)
    finally:
        conn.close()
        if own_ro_engine:
            readonly_engine.dispose()
        if wconn is not None:
            wconn.close()

    return dict(section1, redundant=redundant)


def _report_section1(results: list, apply: bool) -> dict:
    refused = [r for r in results if r["verdict"] == REFUSED_DUPLICATES]
    invalid = [r for r in results if r["verdict"] == REFUSED_INVALID_INDEX]
    failed = [r for r in results if r["verdict"] == FAILED]
    created = [r for r in results if r["verdict"] == OK_CREATED]
    already = [r for r in results if r["verdict"] == OK_ALREADY]

    print("")
    if already:
        print(f"Already enforced ({len(already)}): "
              f"{', '.join(r['table'] for r in already)}")
    if created:
        print(f"Created ({len(created)}): {', '.join(r['table'] for r in created)}")

    # REFUSALS ARE ITEMISED WITH THEIR EVIDENCE. "3 tables refused" tells an operator
    # nothing they can act on; the table name, the surplus and the offending keys do.
    for r in refused:
        print(f"\n!! REFUSED (duplicates) {r['table']}: {r['dup_keys']} duplicated keys, "
              f"{r['surplus']} surplus rows. The index was NOT attempted here and the "
              f"rest of the run continued.")
        print(f"   Offending keys (top {len(r['sample'])}): {r['sample']}")
        print(f"   Inspect:  SELECT {BK_COLUMN}, count(*) FROM public.\"{r['table']}\" "
              f"GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC;")
    for r in invalid:
        print(f"\n!! REFUSED (invalid leftover) {r['table']}: an index named "
              f"{r['index_name']} exists but `indisvalid` is false - a cancelled "
              f"CONCURRENTLY build. It enforces NOTHING, and `IF NOT EXISTS` would "
              f"skip past it forever. This script does not drop anything; run:")
        print(f"   DROP INDEX CONCURRENTLY {quote_ident(r['index_name'])};"
              f"   -- then re-run --apply")
    for r in failed:
        print(f"\n!! FAILED {r['table']}: {r.get('detail')}")

    covered = len(created) + len(already)
    print(f"\nSummary: {covered} enforced, {len(refused)} refused (duplicates), "
          f"{len(invalid)} refused (invalid leftover), {len(failed)} failed, "
          f"out of {len(results)} tables in scope.")
    if not apply:
        buildable = [r for r in results if r["verdict"] == "buildable"]
        print(f"Nothing was written. {len(buildable)} table(s) would be built: "
              f"{', '.join(r['table'] for r in buildable) or '-'}")
    return {"results": results, "refused": refused, "invalid": invalid, "failed": failed,
            "created": created, "already": already}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--apply", action="store_true",
                   help="section 1: build the UNIQUE business_key_val indexes. "
                        "Without it the run is read-only.")
    p.add_argument("--drop-redundant", action="store_true", dest="drop_redundant",
                   help="section 2: drop indexes proven to duplicate their table's "
                        "primary-key index. Independent of --apply.")
    p.add_argument("--table", action="append", dest="tables",
                   help="section 1 only: limit to this table (repeatable). Default: "
                        "every table that has the column.")
    args = p.parse_args(argv)
    out = run(apply=args.apply, only=args.tables,
              drop_redundant=args.drop_redundant)
    bad = (out["refused"] + out["invalid"] + out["failed"]
           + out["redundant"]["failed"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
