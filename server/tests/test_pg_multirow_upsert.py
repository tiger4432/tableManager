"""[P4] The bulk-upsert ACCEPTED branch - the one no SQLite test can enter.

WHY THIS FILE EXISTS
`crud._pg_multirow_upsert` returns `False` on `dialect.name != "postgresql"`,
so on this suite's in-memory SQLite every call falls through to the historical
send. Measured with a counting spy over the three files named for this path:
`entered=28 accepted=0 declined=28` across 42 passing tests. Not one line of
the SQL construction, the bind processors, the chunk loop or the
`row_sql_cache` had ever been executed by a test. Every test below runs on the
`pg_session` fixture (`conftest.py`) and therefore on the accepted branch.

🔴 THE FIRST TEST IN THIS FILE IS THE ONE THAT KEEPS THE REST HONEST.
Every other test here would still pass if `_pg_multirow_upsert` started
declining for all input - it would simply be measuring the fallback again,
under names that say otherwise. That is exactly the failure this file was
written to end, so `test_the_accepted_branch_is_the_branch_under_test` asserts
the decision itself, and the tests that need it assert it alongside their own
claim rather than trusting the file's title.

SKIPPING, NOT FAILING, is the contract when no PostgreSQL is declared - see
`conftest.PG_TEST_URL_ENV`. Run them with:

    ASSY_PG_TEST_DATABASE_URL=postgresql://postgres:...@localhost:5432/assy_qa \
        python -m pytest server/tests/test_pg_multirow_upsert.py
"""
import contextlib
import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from conftest import PG_TEST_SCHEMA, _resolve_pg_test_url
from database import crud, schemas


TABLE = "pgqa_bk_table"


# --- instrumentation --------------------------------------------------------

@contextlib.contextmanager
def upsert_decisions():
    """Record what `_pg_multirow_upsert` ANSWERED, per call.

    `[True]` = the accepted branch ran. `[False]` = it declined and the
    caller's fallback carried the write. `[]` = it was never reached
    (`_is_executemany_safe` refused first).

    ⚠️ A call that RAISES records `True`, not nothing. Recording only the
    return value made this instrument blind in exactly the case it was needed
    for - a failure raised out of the raw send is the accepted branch running,
    and an empty list would have been read as "the fast path was not taken".
    """
    answers = []
    real = crud._pg_multirow_upsert

    def spy(*args, **kwargs):
        try:
            answer = real(*args, **kwargs)
        except BaseException:
            answers.append(True)
            raise
        answers.append(answer)
        return answer

    crud._pg_multirow_upsert = spy
    try:
        yield answers
    finally:
        crud._pg_multirow_upsert = real


@contextlib.contextmanager
def forced_fallback():
    """Make the helper decline, so the caller takes the send this replaced.

    This is the ORACLE arm. The two paths must store the same row; where they
    do not, one of them is wrong, and the fallback is the one whose behaviour
    every other part of this system was built against.
    """
    real = crud._pg_multirow_upsert
    crud._pg_multirow_upsert = lambda *a, **kw: False
    try:
        yield
    finally:
        crud._pg_multirow_upsert = real


def _source_rows(db, prefix):
    return db.execute(text(
        "SELECT row_id, value::text, updated_by, ingested_at "
        "FROM cell_sources WHERE row_id LIKE :p ORDER BY row_id"),
        {"p": prefix + "%"}).fetchall()


def _mapping(i, value="v", ingested_at=None, row_prefix="R"):
    return {"table_name": TABLE, "row_id": f"{row_prefix}{i}",
            "column_name": "note", "source_name": "probe.csv",
            "value": value, "updated_by": "watcher",
            "ingested_at": ingested_at or datetime.now()}


def _overwrite(i, row_prefix="R", **over):
    row = {"table_name": TABLE, "row_id": f"{row_prefix}{i}",
           "column_name": "note", "is_overwrite": True,
           "updated_by": "operator", "updated_at": datetime.now(),
           "manual_priority_source": None}
    row.update(over)
    return row


# ===========================================================================
# 0. The meta-test
# ===========================================================================

def test_the_accepted_branch_is_the_branch_under_test(pg_session):
    """[behaviour 1] The helper ACCEPTS here, and one chunk is one statement.

    Without this assertion the whole file is a second copy of the fallback
    tests. It also pins the send SHAPE, because "one multi-row VALUES per
    chunk" is the entire point: the send it replaced issued one server round
    trip per row while looking, in every log and every statement counter, like
    a batch.
    """
    statements = []

    from sqlalchemy import event

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("insert into cell_sources"):
            statements.append((statement, parameters, executemany))

    event.listen(pg_session.get_bind(), "before_cursor_execute", record)
    try:
        with upsert_decisions() as answers:
            crud.bulk_upsert_cell_sources(
                pg_session, [_mapping(i) for i in range(3)])
        pg_session.commit()
    finally:
        event.remove(pg_session.get_bind(), "before_cursor_execute", record)

    assert answers == [True], (
        "the accepted branch was not taken - every assertion in this file is "
        "then about the fallback, under a name that says otherwise")
    assert len(statements) == 1, "3 mappings must cost ONE statement, not three"
    sql, params, executemany = statements[0]
    assert not executemany, (
        "this is the defect the path was repaired for: `executemany` is a "
        "Python loop over `cursor.execute`, i.e. one round trip per row")
    # 3 rows x 7 columns, one flat tuple - not 3 parameter sets.
    assert isinstance(params, tuple) and len(params) == 21
    assert sql.count("(%s,%s,%s,%s,%s,%s,%s)") == 3
    assert "ON CONFLICT (table_name, row_id, column_name, source_name)" in sql
    assert "DO UPDATE SET value = EXCLUDED.value" in sql


# ===========================================================================
# 1. The divergence the fallback does not have
# ===========================================================================

def test_a_none_on_a_defaulted_column_lands_what_the_fallback_lands(pg_session):
    """🔴 [the D1 divergence] Two send paths, one stored row. They differ today.

    `_pg_multirow_upsert` names EVERY key of `mappings[0]` in its INSERT column
    list, so a key present with value `None` is sent as a literal NULL.
    SQLAlchemy's insert OMITS such a column when it carries a default, and
    PostgreSQL then applies the default. `CellOverwrite.is_overwrite` is
    `default=True`, so the same mapping stores `True` through the fallback and
    `NULL` through the fast path.

    ⚠️ WHY `is_overwrite` AND NOT THE TIMESTAMPS. `ingested_at`/`updated_at`
    carry `server_default=func.now()`, so the two arms cannot be compared by
    value - they run at different instants. They are asserted NOT NULL below
    instead. `is_overwrite` is a boolean with a Python-side default, so it is
    byte-comparable, and it is also the one that MATTERS: a NULL overwrite
    marker reads as falsy at `main.py`'s `has_overwrite`, which is a manually
    corrected cell quietly losing to the automatic layer - core value #4.

    ⚠️ This test is written to FAIL against the code as it stands and to pass
    once the decline (or the omission) covers present-but-None. It asserts the
    OBSERVABLE STORED VALUE and not which branch ran, so either repair
    strategy satisfies it.
    """
    mapping = _overwrite(1, row_prefix="ND_", is_overwrite=None,
                         updated_at=None)

    crud.bulk_upsert_cell_overwrites(pg_session, [dict(mapping)])
    pg_session.commit()
    fast = pg_session.execute(text(
        "SELECT is_overwrite, updated_at IS NOT NULL FROM cell_overwrites "
        "WHERE row_id = 'ND_1'")).one()

    pg_session.execute(text("DELETE FROM cell_overwrites WHERE row_id = 'ND_1'"))
    pg_session.commit()

    with forced_fallback():
        crud.bulk_upsert_cell_overwrites(pg_session, [dict(mapping)])
        pg_session.commit()
    fallback = pg_session.execute(text(
        "SELECT is_overwrite, updated_at IS NOT NULL FROM cell_overwrites "
        "WHERE row_id = 'ND_1'")).one()

    assert fallback[0] is True and fallback[1] is True, (
        "the oracle arm itself changed - the fallback no longer applies the "
        "column defaults, so this test is measuring the wrong thing")
    assert tuple(fast) == tuple(fallback), (
        f"the two send paths stored DIFFERENT rows for one mapping: fast "
        f"path {tuple(fast)}, fallback {tuple(fallback)}. A `None` on a "
        f"defaulted column must not become a literal NULL.")


def test_a_none_on_a_defaulted_column_does_not_destroy_a_stored_value(pg_session):
    """The same divergence on the `DO UPDATE` arm, where it is DESTRUCTIVE.

    The insert case merely fails to apply a default. On conflict the statement
    writes its NULL over a value that is already there, so an existing
    `is_overwrite = true` becomes NULL and the cell stops being marked as
    manually corrected.
    """
    seed = _overwrite(2, row_prefix="ND_")
    crud.bulk_upsert_cell_overwrites(pg_session, [seed])
    pg_session.commit()
    assert pg_session.execute(text(
        "SELECT is_overwrite FROM cell_overwrites "
        "WHERE row_id = 'ND_2'")).scalar() is True

    crud.bulk_upsert_cell_overwrites(
        pg_session, [_overwrite(2, row_prefix="ND_", is_overwrite=None)])
    pg_session.commit()

    after = pg_session.execute(text(
        "SELECT is_overwrite FROM cell_overwrites "
        "WHERE row_id = 'ND_2'")).scalar()
    assert after is True, (
        "an upsert carrying `is_overwrite=None` destroyed the stored overwrite "
        f"marker (now {after!r}). The manual correction on this cell no longer "
        "beats the automatic layer.")


# ===========================================================================
# 2. Value fidelity through the raw send
# ===========================================================================

@pytest.mark.parametrize("value", [
    "a string", "", 0, 1, -3, 3.5, True, False, None,
    {"nested": {"dict": [1, 2, None]}}, [1, "two", None], "null", "0",
    "'); DROP TABLE cell_sources; --", "%s", "%(x)s", "%%", "),(",
    "back\\slash \"quote\" 'single'", "유니코드 값",
])
def test_json_value_lands_byte_identically_on_both_send_paths(pg_session, value):
    """[behaviour 2] The bind processors, which are the ONLY reason this works.

    `cell_sources.value` is a `JSON` column: without its dialect bind
    processor a bare Python string is not valid json and the statement fails
    outright. The docstring calls this "the ONLY reason the values land
    identically" - so it is compared against the fallback rather than against
    an expectation written by hand, and `value::text` is compared so the
    stored JSON is examined, not a round-tripped Python object.

    The injection-shaped members of this list are here because the raw send
    builds SQL TEXT: `%s`, `),(` and a quoted statement terminator must reach
    the parameter tuple and never the statement.

    ⚠️ The first arm asserts it was ACCEPTED. Comparing two paths is worthless
    if a future decline quietly makes both of them the fallback - the
    comparison would then pass for every value and mean nothing. `value` has
    no column default, so the `None` case is accepted here rather than
    declined; that is asserted, not assumed.
    """
    with upsert_decisions() as answers:
        crud.bulk_upsert_cell_sources(
            pg_session, [_mapping(1, value=value, row_prefix="FD_")])
        pg_session.commit()
    assert answers == [True], (
        f"the fast arm declined for {value!r}, so this test would be "
        f"comparing the fallback against itself")
    fast = _source_rows(pg_session, "FD_")

    pg_session.execute(text("DELETE FROM cell_sources WHERE row_id LIKE 'FD_%'"))
    pg_session.commit()

    with forced_fallback():
        crud.bulk_upsert_cell_sources(
            pg_session, [_mapping(1, value=value, row_prefix="FD_")])
        pg_session.commit()
    fallback = _source_rows(pg_session, "FD_")

    assert len(fast) == 1 and len(fallback) == 1
    assert fast[0][1] == fallback[0][1], (
        f"stored json differs between send paths for {value!r}: "
        f"{fast[0][1]!r} vs {fallback[0][1]!r}")
    # `None` and `''` have been confused on this path before, so the stored
    # json TYPE is pinned too - `null` and `""` are the same length in text.
    stored_type = pg_session.execute(text(
        "SELECT json_typeof(value) FROM cell_sources "
        "WHERE row_id = 'FD_1'")).scalar()
    expected_type = {str: "string", bool: "boolean", int: "number",
                     float: "number", dict: "object", list: "array",
                     type(None): "null"}[type(value)]
    assert stored_type == expected_type


# ===========================================================================
# 3. The declines
# ===========================================================================

def test_an_unknown_mapping_key_declines_instead_of_guessing(pg_session):
    """[behaviour 4] A key that is not a column of the table.

    The write must still land, through the fallback, which silently ignores
    the extra key. With the guard removed the helper resolves `None` from
    `table.c` and dies on `AttributeError: 'NoneType' object has no attribute
    'type'` - measured.
    """
    mapping = _mapping(1, row_prefix="UK_")
    mapping["not_a_column"] = "x"

    with upsert_decisions() as answers:
        crud.bulk_upsert_cell_sources(pg_session, [mapping])
        pg_session.commit()

    assert answers == [False], "an unknown key must be DECLINED, not guessed at"
    assert len(_source_rows(pg_session, "UK_")) == 1, \
        "declining must fall back to a working write, not drop the row"


def test_a_python_default_the_mappings_omit_declines(pg_session):
    """[behaviour 3] The guard QA2's mutation showed to be the destructive one.

    `CellOverwrite.is_overwrite` is `default=True`. Omit the key and the raw
    statement cannot compute it, so the helper must decline; with the guard
    removed it accepts and stores NULL for every row, no error and no log.
    """
    mapping = _overwrite(1, row_prefix="PD_")
    mapping.pop("is_overwrite")

    with upsert_decisions() as answers:
        crud.bulk_upsert_cell_overwrites(pg_session, [mapping])
        pg_session.commit()

    assert answers == [False]
    assert pg_session.execute(text(
        "SELECT is_overwrite FROM cell_overwrites "
        "WHERE row_id = 'PD_1'")).scalar() is True, \
        "the fallback must supply the Python-side default"


# ===========================================================================
# 4. Chunk boundaries and the conflict target, on the accepted branch
# ===========================================================================

@pytest.mark.parametrize("n", [0, 1, crud.BULK_CHUNK_SIZE - 1,
                               crud.BULK_CHUNK_SIZE, crud.BULK_CHUNK_SIZE + 1])
def test_chunk_boundaries_write_every_mapping_on_the_accepted_branch(pg_session, n):
    """[behaviour 5] The boundaries `test_bulk_chunking_budget` pins for the
    fallback, asserted for the path production actually takes.

    The statement count is asserted as well as the row count: `row_sql_cache`
    is keyed by chunk LENGTH, so an off-by-one in the cut shows up as a wrong
    number of statements before it shows up as a wrong number of rows.
    """
    from sqlalchemy import event
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().lower().startswith("insert into cell_sources"):
            statements.append(statement)

    event.listen(pg_session.get_bind(), "before_cursor_execute", record)
    try:
        crud.bulk_upsert_cell_sources(
            pg_session, [_mapping(i, row_prefix="CB_") for i in range(n)])
        pg_session.commit()
    finally:
        event.remove(pg_session.get_bind(), "before_cursor_execute", record)

    assert len(_source_rows(pg_session, "CB_")) == n
    expected = -(-n // crud.BULK_CHUNK_SIZE)  # ceil
    assert len(statements) == expected, \
        f"{n} mappings must be cut into {expected} statement(s)"


def test_on_conflict_do_update_replaces_the_value_on_the_accepted_branch(pg_session):
    """[behaviour 1] The conflict semantics, on the path that has them in raw SQL.

    The fallback's `ON CONFLICT` clause is built by SQLAlchemy; this one is a
    string this function assembles, so it is the one that can be wrong.
    """
    with upsert_decisions() as answers:
        crud.bulk_upsert_cell_sources(
            pg_session, [_mapping(1, value="first", row_prefix="CF_")])
        pg_session.commit()
        crud.bulk_upsert_cell_sources(
            pg_session, [_mapping(1, value="second", row_prefix="CF_")])
        pg_session.commit()

    assert answers == [True, True]
    rows = _source_rows(pg_session, "CF_")
    assert len(rows) == 1, "the conflict target did not match - a second row landed"
    assert rows[0][1] == '"second"'


def test_cell_overwrites_updates_all_four_columns_on_conflict(pg_session):
    """[behaviour 6] `cell_overwrites`' four-column `DO UPDATE SET`.

    A `SET` list built by hand is exactly where one column goes missing, and
    the one that would go missing silently is `manual_priority_source`: a pin
    that is not cleared keeps beating the layer the operator just chose.
    """
    early = datetime.now() - timedelta(days=1)
    with upsert_decisions() as answers:
        crud.bulk_upsert_cell_overwrites(pg_session, [_overwrite(
            1, row_prefix="OW_", is_overwrite=True, updated_by="first",
            updated_at=early, manual_priority_source="user")])
        pg_session.commit()
        crud.bulk_upsert_cell_overwrites(pg_session, [_overwrite(
            1, row_prefix="OW_", is_overwrite=False, updated_by="second",
            updated_at=early + timedelta(days=1),
            manual_priority_source=None)])
        pg_session.commit()

    assert answers == [True, True]
    row = pg_session.execute(text(
        "SELECT is_overwrite, updated_by, updated_at, manual_priority_source "
        "FROM cell_overwrites WHERE row_id = 'OW_1'")).one()
    assert row[0] is False, "is_overwrite was not in the SET list"
    assert row[1] == "second", "updated_by was not in the SET list"
    assert row[2].replace(tzinfo=None) > early.replace(tzinfo=None), \
        "updated_at was not in the SET list"
    assert row[3] is None, (
        "manual_priority_source was not in the SET list - a cleared pin "
        "survives and keeps outranking the layer the operator chose")


# ===========================================================================
# 5. Failure out of the raw send
# ===========================================================================

def test_a_database_error_arrives_as_the_sqlalchemy_class(pg_session):
    """[behaviour 8] The reason this send stays inside SQLAlchemy.

    `exec_driver_sql` keeps SQLAlchemy's error translation, so a NOT NULL
    breach arrives as `sqlalchemy.exc.IntegrityError` with the psycopg2 error
    preserved on `.orig`. A raw cursor (`psycopg2.extras.execute_values`,
    which measures the same speed and was rejected for this) would raise
    `psycopg2.errors.NotNullViolation`, and `main.py`'s batch-update endpoint
    catches `IntegrityError` - so the difference is a 500 instead of the
    handled path.

    Also pins that the business-key detector says NO to it: that detector's
    narrowness is what stops a genuine constraint failure being replayed until
    it gives up.
    """
    import psycopg2
    mapping = _overwrite(1, row_prefix="NN_", updated_by=None)

    with upsert_decisions() as answers:
        with pytest.raises(IntegrityError) as caught:
            crud.bulk_upsert_cell_overwrites(pg_session, [mapping])
            pg_session.flush()

    assert answers == [True], "this must be the raw send's own failure"
    assert isinstance(caught.value.orig, psycopg2.errors.NotNullViolation)
    assert caught.value.orig.pgcode == "23502"
    assert crud._is_business_key_unique_violation(caught.value) is False
    pg_session.rollback()


def test_a_failing_chunk_leaves_the_whole_batch_unwritten(pg_session):
    """[behaviour 9] Failure granularity: the batch stays all-or-nothing.

    Poison in the LAST chunk, so the earlier chunks have already been sent and
    a per-statement commit would leave them behind. PostgreSQL aborts the
    transaction at the first error and nothing here commits, so the correct
    outcome is zero rows - the same as the send this replaced.

    ⚠️ THE ROW IDS ARE ZERO-PADDED AND THAT IS LOAD-BEARING. `bulk_upsert_*`
    re-sorts its mappings by the conflict key before chunking (deadlock
    ordering), and that sort is on the STRING. Unpadded, `AB_1004` sorts
    between `AB_1003` and `AB_101`, i.e. into the FIRST chunk - so the test
    said "poison in the last chunk" while exercising the first one, and a
    `db.commit()` injected into the chunk loop left it green. Found by that
    mutation; the padding is what makes the docstring true.
    """
    # `cell_overwrites.updated_by` is the NOT NULL column on these two tables
    # (`cell_sources.updated_by` is nullable), so the poison goes there.
    n = crud.BULK_CHUNK_SIZE + 5
    ids = [f"AB_{i:06d}" for i in range(n)]
    mappings = [_overwrite("", row_prefix=rid) for rid in ids[:-1]]
    mappings.append(_overwrite("", row_prefix=ids[-1], updated_by=None))

    with pytest.raises(IntegrityError):
        crud.bulk_upsert_cell_overwrites(pg_session, mappings)
        pg_session.flush()

    pg_session.rollback()
    assert pg_session.execute(text(
        "SELECT count(*) FROM cell_overwrites "
        "WHERE row_id LIKE 'AB_%'")).scalar() == 0, \
        "a failed batch left rows behind - the write is no longer atomic"


# ===========================================================================
# 6. 🔴 The business-key recovery, against a REAL unique index
# ===========================================================================

def _competing_writer(url, business_key, row_id, withdraw_first=False):
    """Another OS process's write, committed on its OWN connection.

    A second SQLAlchemy Session on the same engine would share this test's
    transaction bookkeeping and could not commit underneath it, which is the
    whole event being reproduced. Raw psycopg2 is the smallest thing that is
    genuinely a different transaction.
    """
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{PG_TEST_SCHEMA}"')
            if withdraw_first:
                cur.execute(f'DELETE FROM "{TABLE}" WHERE business_key_val = %s',
                            (business_key,))
            cur.execute(
                f'INSERT INTO "{TABLE}" '
                "(row_id, business_key_val, part_no, qty, note) "
                "VALUES (%s, %s, %s, %s, %s)",
                (row_id, business_key, business_key, 99, "theirs"))
        conn.commit()
    finally:
        conn.close()


def _competitor_withdraws(url, business_key):
    """The competitor's row is gone again by the time we re-prefetch."""
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{PG_TEST_SCHEMA}"')
            cur.execute(f'DELETE FROM "{TABLE}" WHERE business_key_val = %s',
                        (business_key,))
        conn.commit()
    finally:
        conn.close()


def test_business_key_recovery_merges_onto_the_winners_row(pg_session, caplog):
    """🔴 [behaviour 7] The recovery, driven against a REAL UNIQUE index.

    THE GAP THIS CLOSES. `test_business_key_conflict_retry.py` covers the
    control flow with a `FakeDB` whose `rollback()` is `self.rollbacks += 1`.
    That proves which exception leads to which branch and NOTHING about the
    database: after a real PostgreSQL transaction aborts, every subsequent
    statement fails with `InFailedSqlTransaction` until something actually
    rolls back, so "it retried" and "it recovered" are different claims and
    only a real database can tell them apart.

    THE RACE, made deterministic. The competing writer commits the colliding
    business key from inside `bulk_upsert_cell_sources` on attempt 1 - that is,
    after the prefetch has proved the key absent and before `db.commit()`,
    which is precisely the window `ProbedIdentity` cannot cover because there
    is no cross-process lock (`grep -rn "pg_advisory" server/` = 0).

    WHAT RECOVERY MEANS HERE, asserted rather than implied: one row for the
    key, carrying the WINNER's `row_id` - so this is a merge, not a second
    insert - and the replay's values on it.

    ⚠️ Needs the `uq_bk_<table>` UNIQUE index. The isolated database has ZERO
    of them; `conftest.pg_engine` builds one on the scratch table only, inside
    the scratch schema, and drops it with the schema.
    """
    url, _ = _resolve_pg_test_url()
    index_name = pg_session.execute(text(
        "SELECT indexname FROM pg_indexes "
        "WHERE schemaname = :s AND indexname LIKE 'uq\\_bk\\_%'"),
        {"s": PG_TEST_SCHEMA}).scalar()
    assert index_name == f"uq_bk_{TABLE}", (
        "precondition absent: without a real UNIQUE index the collision is a "
        "duplicate row and this test would pass while proving nothing")

    winner_row_id = "THEIR-ROW-ID"
    fired = []
    real_bulk = crud.bulk_upsert_cell_sources

    def racing_bulk(db, mappings, *a, **kw):
        if not fired:
            fired.append(True)
            _competing_writer(url, "PN-2", winner_row_id)
        return real_bulk(db, mappings, *a, **kw)

    attempts = []
    real_once = crud._apply_batch_updates_once

    def counting_once(*a, **kw):
        attempts.append(1)
        return real_once(*a, **kw)

    items = [schemas.GeneralUpdateItem(
        business_key_val=f"PN-{i}",
        updates={"part_no": f"PN-{i}", "qty": i, "note": "mine"},
        source_name="probe.csv", updated_by="watcher") for i in range(5)]

    crud.bulk_upsert_cell_sources = racing_bulk
    crud._apply_batch_updates_once = counting_once
    try:
        with caplog.at_level(logging.WARNING, logger="Server"):
            results, changed, _logs, _deleted = crud.apply_batch_updates(
                pg_session, TABLE, schemas.GeneralUpdateBatch(updates=items))
    finally:
        crud.bulk_upsert_cell_sources = real_bulk
        crud._apply_batch_updates_once = real_once

    assert fired == [True], "the race never happened - this asserted nothing"
    assert len(attempts) == 2, (
        f"expected one lost race and one replay, got {len(attempts)} attempt(s)")
    assert any("BK Conflict Recovered" in r.message for r in caplog.records), (
        "the recovery must be NAMED in the log; a race nobody logs is a race "
        "nobody ever measures")

    rows = pg_session.execute(text(
        f'SELECT business_key_val, row_id, qty, note FROM "{TABLE}" '
        "ORDER BY business_key_val")).fetchall()
    assert [r[0] for r in rows] == [f"PN-{i}" for i in range(5)], \
        "the four uncontested rows must still be written"
    assert len(rows) == 5, f"a duplicate identity survived: {rows}"

    collided = [r for r in rows if r[0] == "PN-2"][0]
    assert collided[1] == winner_row_id, (
        "the batch inserted its OWN row instead of merging onto the row the "
        "winner committed - the replay did not re-read identity")
    assert (collided[2], collided[3]) == (2.0, "mine"), (
        "the replay's values did not land on the merged row")
    assert len(results) == 5


def test_a_persistent_business_key_conflict_is_refused_not_replayed(pg_session, caplog):
    """The other half of the design, against a real index.

    A competitor that wins EVERY attempt is not a lost race, it is a genuine
    duplicate identity. The batch must be refused after the declared bound
    rather than spun forever - and the exception must still classify as a
    business-key violation, because `main.py` maps that to a 409 and anything
    else to a 500.

    HOW A CONFLICT IS MADE TO PERSIST. A competitor that merely inserts once is
    recovered from on attempt 2 - that is the test above. To keep losing, the
    competitor has to be gone when the replay's prefetch looks (so identity is
    still resolved as absent) and back before the commit. So it withdraws at
    the top of every attempt and re-commits inside every `bulk_upsert`.
    """
    url, _ = _resolve_pg_test_url()
    seen = []
    real_bulk = crud.bulk_upsert_cell_sources
    real_once = crud._apply_batch_updates_once

    def withdrawing_once(*a, **kw):
        _competitor_withdraws(url, "PN-9")
        return real_once(*a, **kw)

    def racing_bulk(db, mappings, *a, **kw):
        seen.append(len(seen))
        _competing_writer(url, "PN-9", f"THEIRS-{len(seen)}",
                          withdraw_first=True)
        return real_bulk(db, mappings, *a, **kw)

    item = schemas.GeneralUpdateItem(
        business_key_val="PN-9", updates={"part_no": "PN-9", "qty": 1},
        source_name="probe.csv", updated_by="watcher")

    crud.bulk_upsert_cell_sources = racing_bulk
    crud._apply_batch_updates_once = withdrawing_once
    try:
        with caplog.at_level(logging.ERROR, logger="Server"):
            with pytest.raises(IntegrityError) as caught:
                crud.apply_batch_updates(
                    pg_session, TABLE,
                    schemas.GeneralUpdateBatch(updates=[item]))
    finally:
        crud.bulk_upsert_cell_sources = real_bulk
        crud._apply_batch_updates_once = real_once

    assert len(seen) == crud.BK_CONFLICT_MAX_RETRIES + 1
    assert crud._is_business_key_unique_violation(caught.value), (
        "the re-raised error no longer classifies as a business-key "
        "violation, so the endpoint would answer 500 instead of 409")
    assert caught.value.orig.diag.constraint_name == f"uq_bk_{TABLE}"
    assert any("BK Conflict Unresolved" in r.message for r in caplog.records)

    pg_session.rollback()
    # The session must be USABLE after the refusal - the caller's `finally`
    # and the next request both depend on it.
    assert pg_session.execute(text(
        f'SELECT count(*) FROM "{TABLE}"')).scalar() == 1
