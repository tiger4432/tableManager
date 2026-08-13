"""Physical DDL for `ledger_events` and the translator cursor. ONE spelling, here.

The migration script under `server/migrations/` is the operator's entry point and this
module is what it runs, so there is no second copy of the DDL to drift. `store.py` calls
the same functions, which is what lets a test build the real table in a scratch schema
instead of a lookalike (`SQLite accepts what PostgreSQL refuses` - the third time that
lesson was paid for in this project was 2026-08-05).

🔴 TIME PARTITIONED FROM DAY ONE
---------------------------------
`LEDGER_SLICE_1_BRIEF` §3-1: "첫날부터 시간 파티션(나중에 붙이면 스키마 재작성이라는
것이 본 세션에서 실측됨)". Converting a populated table to a partitioned one is a full
rewrite - there is no `ALTER TABLE ... PARTITION BY`. So the empty table is created
partitioned, and the translator creates the month it is about to write into.

WHAT THE CONSTRAINTS ARE FOR
-----------------------------
Each CHECK below is a rule from the design that would otherwise live only in prose:

  * `ck_ledger_register_has_no_object` - the design says `register`'s object is ∅, and
    the pinned `object_kind` enum has no spelling for ∅. The resolution (stated in
    `vocabulary.py`) is `object_kind IS NULL`, and this constraint makes that legal for
    `register` and for nothing else, in BOTH directions - a register with an object and
    a non-register without one are equally refused.
  * `ck_ledger_subject_keys_is_object` - §3's `subject` row. The incident was a
    concatenated key collapsing when a piece was blank; storing a bare string here would
    reintroduce it at the storage layer, below every Python check.
  * `ck_ledger_no_self_supersede` - a correction that supersedes itself is a cycle the
    resolver would follow forever.

WHY THE UNIQUE INDEX IS ON COLUMNS AND NOT ON A HASH
-----------------------------------------------------
A hash index key would have to be computed identically by Python (at write time) and by
PostgreSQL (in the index expression), and those two do not spell JSON the same way -
`json.dumps(separators=(",",":"))` versus jsonb's own `::text`. Two spellings of one key
is exactly how a unique index stops matching what the writer computes, and it fails
SILENTLY (every row looks new). Indexing the columns themselves has no second spelling:
PostgreSQL compares jsonb to jsonb, semantically, and the writer computes nothing.

`coalesce(object_payload, '{}'::jsonb)` rather than the bare column, because NULLs in a
unique index are DISTINCT from each other on every PostgreSQL before 15 - two identical
`register` atoms would both be accepted. An empty object is a safe stand-in: no predicate's
signature accepts `{}` as a payload, so it can never collide with a real one.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger("Ledger.Schema")

LEDGER_TABLE = "ledger_events"
CURSOR_TABLE = "ledger_translator_cursor"

#: The seven columns the unique index compares. Named once, used by the DDL and by the
#: writer's `ON CONFLICT` reasoning, so "what makes two atoms the same claim" has one
#: definition.
DEDUPE_COLUMNS = (
    "occurred_at", "predicate", "subject_type", "subject_keys",
    "coalesce(object_payload, '{}'::jsonb)", "source_translator_ver", "source_raw_ref",
)


CREATE_LEDGER = f"""
CREATE TABLE IF NOT EXISTS {LEDGER_TABLE} (
    id                    UUID        NOT NULL,
    subject_type          TEXT        NOT NULL,
    subject_keys          JSONB       NOT NULL,
    predicate             TEXT        NOT NULL,
    object_kind           TEXT,
    object_payload        JSONB,
    occurred_at           TIMESTAMPTZ NOT NULL,
    source_who            TEXT        NOT NULL,
    source_translator_ver TEXT        NOT NULL,
    source_raw_ref        TEXT        NOT NULL,
    supersedes            UUID,
    CONSTRAINT ck_ledger_object_kind CHECK (
        object_kind IS NULL OR object_kind IN ('value', 'entity_ref', 'event_ref')),
    CONSTRAINT ck_ledger_register_has_no_object CHECK (
        (predicate = 'register') = (object_kind IS NULL)),
    CONSTRAINT ck_ledger_objectless_has_no_payload CHECK (
        object_kind IS NOT NULL OR object_payload IS NULL),
    CONSTRAINT ck_ledger_subject_keys_is_object CHECK (
        jsonb_typeof(subject_keys) = 'object'),
    CONSTRAINT ck_ledger_no_self_supersede CHECK (
        supersedes IS NULL OR supersedes <> id),
    PRIMARY KEY (id, occurred_at)
) PARTITION BY RANGE (occurred_at)
"""

CREATE_CURSOR = f"""
CREATE TABLE IF NOT EXISTS {CURSOR_TABLE} (
    source               TEXT        PRIMARY KEY,
    translator_ver       TEXT        NOT NULL,
    cursor_value         JSONB       NOT NULL,
    molecules_done       BIGINT      NOT NULL DEFAULT 0,
    atoms_written        BIGINT      NOT NULL DEFAULT 0,
    atoms_deduped        BIGINT      NOT NULL DEFAULT 0,
    molecules_refused    BIGINT      NOT NULL DEFAULT 0,
    incomplete_molecules BIGINT      NOT NULL DEFAULT 0,
    source_head          JSONB,
    head_probed_at       TIMESTAMPTZ,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# 🔴 EVERY INDEX BELOW HAS A NAMED CONSUMER, AND THAT IS THE ADMISSION RULE.
#
# Measured on this box at 300,000 atoms of the shapes this translator actually produces
# (VACUUM ANALYZE, PostgreSQL 18.3): the heap is 312.8 B/atom - within half a percent of
# the 312.3 B/atom the design measured independently - and indexes are the larger half of
# the bill. So an index nobody queries is not free: it is ~0.3-0.6 GB at ten million
# atoms, paid forever, to answer nothing.
#
# Three candidates were built, measured and then REMOVED for exactly that reason. They
# are recorded here with their prices so that adding one back is a decision with a number
# attached rather than a fresh guess:
#
#   idx_ledger_type_pred_time (subject_type, predicate, occurred_at)   64.4 B/atom
#       No consumer. The trace walk filters on the subject key, not on the type.
#   idx_ledger_subject_gin  USING gin (subject_keys jsonb_path_ops)    38.3 B/atom
#       Serves `subject_keys @> '{...}'`. Nothing asks that today; the walk asks
#       `subject_keys->>'lot' = ...`, which a GIN cannot answer. Add it when a consumer
#       needs to look a subject up by a key OTHER than `lot` (the reverse-radius query
#       of week 3 is the likely first one).
#   idx_ledger_id (id)                                                 31.6 B/atom
#       Redundant. The primary key is (id, occurred_at) with `id` LEADING, so the
#       watermark scan `WHERE id > :cursor ORDER BY id` already has an index per
#       partition and a MergeAppend across them.
INDEXES = (
    # CONSUMER: idempotency - `store.insert_atoms`'s `ON CONFLICT DO NOTHING`, proven by
    # `test_the_unique_index_holds_when_the_cursor_is_reset`. Risk 1 of the brief. The
    # cursor is the FIRST answer (a re-run reads nothing); this is the one that still
    # holds when somebody resets the cursor.
    # PRICE: 284.6 B/atom, the single largest line in the bill, because it carries
    # `source_raw_ref` plus both jsonb columns. That is the cost of schema-enforced
    # idempotency and it is stated so the trade can be re-decided rather than rediscovered.
    f"CREATE UNIQUE INDEX IF NOT EXISTS uq_ledger_atom ON {LEDGER_TABLE} "
    f"({', '.join(DEDUPE_COLUMNS)})",

    # CONSUMER: `server/ledger_trace.py`'s recursive lineage walk (the slice's other
    # lane), which asks `subject_keys->>'lot' = :lot AND predicate = ANY(...)`.
    # 🔴 Its shape is dictated by a property of that query rather than by taste: the walk
    # carries NO `occurred_at` predicate, because "everything about this lot" has no time
    # bound - so partition pruning can never help it and every partition is visited on
    # every hop. Declared on the parent so PostgreSQL cascades it to partitions that do
    # not exist yet, which is what makes a monthly partition created next year still fast.
    f"CREATE INDEX IF NOT EXISTS idx_ledger_subject_lot ON {LEDGER_TABLE} "
    f"((subject_keys->>'lot'), predicate)",

    # CONSUMER: `store.existing_registrations`, once per page rather than once per row -
    # a per-entity lookup is what makes a ten-million row backfill quadratic. PARTIAL,
    # because registers are O(entities) while the table is O(atoms), so this index stops
    # growing long before the table does. PRICE: 16.6 B/atom and falling.
    f"CREATE INDEX IF NOT EXISTS idx_ledger_register ON {LEDGER_TABLE} "
    f"(subject_type, subject_keys) WHERE predicate = 'register'",
)


def month_bounds(when: datetime):
    """`(start, end, suffix)` for the UTC month containing `when`.

    Everything is computed in UTC and the bounds are written with an explicit offset.
    A partition bound given without one is interpreted in the SESSION's TimeZone, so the
    same DDL run from two processes with different `TZ` would produce partitions that do
    not line up - and the row that falls in the gap fails to insert at all.
    """
    utc = when.astimezone(timezone.utc)
    start = datetime(utc.year, utc.month, 1, tzinfo=timezone.utc)
    end = datetime(utc.year + (utc.month // 12), (utc.month % 12) + 1, 1,
                   tzinfo=timezone.utc)
    return start, end, f"{start.year:04d}_{start.month:02d}"


def partition_name(when: datetime) -> str:
    return f"{LEDGER_TABLE}_{month_bounds(when)[2]}"


def create_partition_sql(when: datetime):
    start, end, _ = month_bounds(when)
    name = partition_name(when)
    return (f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF {LEDGER_TABLE} "
            f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')")


def _relation_exists(cursor, name: str) -> bool:
    """Catalogue gate before any DDL.

    Not decoration: a failed DDL statement poisons the transaction and every query after
    it fails for a reason that has nothing to do with the query. Asking the catalogue
    first is this project's standing rule for exactly that (server-pm lessons file).
    """
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
    return bool(cursor.fetchone()[0])


def ensure_schema(connection):
    """Create the ledger, the cursor table and the indexes. Idempotent, additive only.

    No DROP and no ALTER of anything that exists. Takes a DBAPI connection and commits
    once at the end, so a failure leaves nothing half-built.
    """
    with connection.cursor() as cursor:
        cursor.execute(CREATE_LEDGER)
        cursor.execute(CREATE_CURSOR)
        for statement in INDEXES:
            cursor.execute(statement)
    connection.commit()


def ensure_partition(connection, when: datetime, known=None):
    """Make sure the month containing `when` exists. Returns the partition name.

    Runs in its OWN transaction and commits before returning. That is deliberate: if
    partition creation ran inside the atom transaction and failed, the failure would roll
    back the molecule too and the operator would see an atomicity refusal for what is
    really a DDL problem. Two transactions keep the two failures distinguishable.

    `known` is an optional set the caller keeps across calls, so a backfill that stays
    inside one month issues one catalogue query instead of one per batch.
    """
    name = partition_name(when)
    if known is not None and name in known:
        return name
    try:
        with connection.cursor() as cursor:
            # 🔴 `CREATE TABLE ... PARTITION OF` takes ACCESS EXCLUSIVE on the PARENT,
            # so it queues behind every open reader of `ledger_events` - including a
            # reader belonging to the same process. That is not hypothetical: the first
            # run of this backfill wedged for minutes because its own page-reading
            # connection sat idle-in-transaction holding ACCESS SHARE while this
            # statement waited for it. `backfill.py` now ends that transaction before it
            # writes, and this timeout is the second net: a self-block must FAIL, with a
            # message that says what it was waiting for, rather than hang. A hung
            # process gives an operator nothing to diagnose (an instrument that goes
            # blind under its own fault is this project's own 2026-08-11 lesson).
            cursor.execute("SET LOCAL lock_timeout = '20s'")
            if not _relation_exists(cursor, name):
                cursor.execute(create_partition_sql(when))
                logger.info("[Ledger] created partition %s for %s", name,
                            when.astimezone(timezone.utc).date())
        connection.commit()
    except Exception as exc:
        # A racing creator is the expected reason to land here; anything else must not
        # be allowed to poison the connection for the caller's next statement. The
        # rollback is mandatory before the re-check: a failed statement leaves the
        # transaction aborted and every query after it fails for an unrelated reason
        # (server-pm lessons file).
        connection.rollback()
        with connection.cursor() as cursor:
            if not _relation_exists(cursor, name):
                if "lock_timeout" in str(exc) or "canceling statement" in str(exc):
                    raise RuntimeError(
                        f"could not create partition {name}: another session (possibly "
                        f"this process's own reader) holds a lock on "
                        f"{LEDGER_TABLE}. Partition DDL needs ACCESS EXCLUSIVE on the "
                        f"parent table. Original error: {exc}") from exc
                raise
        connection.commit()
    if known is not None:
        known.add(name)
    return name


def ensure_partitions_for_range(connection, first: datetime, last: datetime):
    """Every month from `first` to `last` inclusive. Returns the names it ensured."""
    names = []
    cursor_month = month_bounds(first)[0]
    end = month_bounds(last)[0]
    while cursor_month <= end:
        names.append(ensure_partition(connection, cursor_month))
        cursor_month = month_bounds(cursor_month + timedelta(days=32))[0]
    return names


def partitions(connection):
    """The ledger's partitions, by name. For the report and for a health check."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT c.relname, pg_get_expr(c.relpartbound, c.oid)
            FROM pg_class parent
            JOIN pg_inherits inh ON inh.inhparent = parent.oid
            JOIN pg_class c ON c.oid = inh.inhrelid
            WHERE parent.oid = to_regclass(%s)
            ORDER BY c.relname
        """, (LEDGER_TABLE,))
        return [(name, bound) for name, bound in cursor.fetchall()]
