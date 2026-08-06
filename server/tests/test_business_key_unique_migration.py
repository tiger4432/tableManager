"""[D3] The migration that makes `business_key_val` uniqueness a database invariant.

WHAT CAN AND CANNOT BE TESTED HERE
The suite runs on SQLite, so the catalogue queries themselves cannot execute. What CAN
be tested - and is what actually decides whether this migration is safe to point at a
14 GB production database - is the DECISION LOGIC: which verdict each situation
produces, that a refusal names the table and keeps going, that a re-run is a no-op, and
that nothing gets dropped that was not proven redundant.

Where a query is the proof rather than the code (section 2's redundancy test), the test
asserts on the SQL's load-bearing clauses. That is weaker than executing it, and it is
said out loud rather than dressed up: it kills "somebody deleted the `indclass`
comparison", not "the query returns the right rows".
"""
import pytest

from migrations import add_business_key_unique_index as mig


# --- index naming ----------------------------------------------------------

def test_name_is_prefixed_and_lowercased():
    assert mig.unique_index_name("bonding_map") == "uq_bk_bonding_map"
    assert mig.unique_index_name("Bonding_MAP") == "uq_bk_bonding_map"


def test_long_names_are_folded_within_the_identifier_limit():
    """PostgreSQL silently truncates at 63 bytes, and a truncated name makes the
    idempotency check consult a name the catalogue does not hold."""
    long = "t" * 120
    name = mig.unique_index_name(long)
    assert len(name.encode("utf-8")) <= mig._MAX_IDENTIFIER
    assert name.startswith(mig.INDEX_PREFIX)


def test_two_long_names_do_not_collide():
    """Truncation alone would map every long name onto one index - the digest is what
    stops two tables from claiming the same one."""
    a = mig.unique_index_name("t" * 100 + "_alpha")
    b = mig.unique_index_name("t" * 100 + "_beta")
    assert a != b


# --- the per-table decision ------------------------------------------------

def _stub(monkeypatch, census=None, present=None, byname=(False, False)):
    monkeypatch.setattr(mig, "duplicate_census", lambda conn, t: dict(
        {"table": t, "rows": 10, "null_keys": 0, "dup_keys": 0, "surplus": 0,
         "sample": [], "elapsed": 0.0}, **(census or {})))
    monkeypatch.setattr(mig, "existing_unique_index", lambda conn, t: present)
    monkeypatch.setattr(mig, "index_exists", lambda conn, n: byname)


def test_clean_table_is_buildable(monkeypatch):
    _stub(monkeypatch)
    assert mig.plan_table(None, "dt_log")["verdict"] is None


def test_duplicates_refuse_that_table_by_name_with_its_evidence(monkeypatch):
    """A refusal has to be actionable: the count and the offending keys travel with it."""
    _stub(monkeypatch, census={"dup_keys": 3, "surplus": 5, "sample": ["A", "B"]})
    r = mig.plan_table(None, "bonding_log")
    assert r["verdict"] == mig.REFUSED_DUPLICATES
    assert r["table"] == "bonding_log"
    assert r["surplus"] == 5 and r["sample"] == ["A", "B"]


def test_existing_valid_unique_index_is_a_no_op(monkeypatch):
    """Idempotency. A second run must report `already_enforced`, not attempt DDL."""
    _stub(monkeypatch, present=("uq_bk_dt_log", True))
    r = mig.plan_table(None, "dt_log")
    assert r["verdict"] == mig.OK_ALREADY
    assert r["index_name"] == "uq_bk_dt_log"


def test_an_invalid_leftover_is_refused_not_skipped(monkeypatch):
    """🔴 The trap `IF NOT EXISTS` sets.

    A cancelled CONCURRENTLY build leaves an INVALID index under the wanted name.
    `CREATE ... IF NOT EXISTS` then reports success forever while the column is
    unprotected. Reading that as 'already done' is the failure this verdict exists to
    prevent, so it must be its own state and not fold into OK_ALREADY.
    """
    _stub(monkeypatch, byname=(True, False))
    assert mig.plan_table(None, "dt_log")["verdict"] == mig.REFUSED_INVALID_INDEX


def test_an_invalid_index_does_not_count_as_enforcement(monkeypatch):
    """Same point from the other side: `existing_unique_index` returning invalid=False
    must not satisfy the check."""
    _stub(monkeypatch, present=("uq_bk_dt_log", False), byname=(True, False))
    assert mig.plan_table(None, "dt_log")["verdict"] != mig.OK_ALREADY


def test_duplicates_are_measured_even_when_the_index_already_exists(monkeypatch):
    """'Measure before you build' is unconditional - the operator's report must carry
    the census for every table, including ones that need no work."""
    _stub(monkeypatch, census={"rows": 4242}, present=("uq_bk_dt_log", True))
    assert mig.plan_table(None, "dt_log")["rows"] == 4242


# --- the DDL ---------------------------------------------------------------

class RecordingConn:
    """Records SQL. `first()` returns None, i.e. "no such index in the catalogue" -
    which is the post-drop answer section 2 needs and the pre-build answer section 1
    needs, so tests that care about the other answer monkeypatch `index_exists`."""

    def __init__(self, valid_after=True, raise_on=None):
        self.sql = []
        self._valid = valid_after
        self._raise = raise_on

    def execute(self, clause, params=None):
        s = str(clause)
        self.sql.append(s)
        if self._raise and self._raise in s:
            raise RuntimeError("could not create unique index: Key (x)=(1) is duplicated")
        return self

    def first(self):
        return None

    def fetchall(self):
        return []


def test_build_ddl_is_concurrent_unique_and_idempotent(monkeypatch):
    conn = RecordingConn()
    monkeypatch.setattr(mig, "index_exists", lambda c, n: (True, True))
    verdict, ddl = mig.build_index(conn, "bonding_map", "uq_bk_bonding_map")
    assert verdict == mig.OK_CREATED
    assert "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS" in ddl
    assert "business_key_val" in ddl
    # CONCURRENTLY is not a preference: production `bonding_map` is ~1.76M rows and a
    # plain build holds a write lock for the whole build.
    assert "CONCURRENTLY" in conn.sql[0]


def test_a_build_that_comes_out_invalid_is_reported_as_failed(monkeypatch):
    """'The statement did not raise' is not enforcement.

    A CONCURRENTLY build can finish without raising and still leave an invalid index.
    Reporting that as success would ship the exact silent non-enforcement the migration
    exists to end.
    """
    conn = RecordingConn()
    monkeypatch.setattr(mig, "index_exists", lambda c, n: (True, False))
    verdict, detail = mig.build_index(conn, "bonding_map", "uq_bk_bonding_map")
    assert verdict == mig.FAILED
    assert "INVALID" in detail


def test_a_raising_build_does_not_propagate(monkeypatch):
    """One table's duplicates must not abort the other 24."""
    conn = RecordingConn(raise_on="CREATE")
    monkeypatch.setattr(mig, "index_exists", lambda c, n: (False, False))
    verdict, detail = mig.build_index(conn, "bonding_log", "uq_bk_bonding_log")
    assert verdict == mig.FAILED
    assert "duplicated" in detail


# --- section 2: redundant primary-key duplicates ---------------------------

def test_redundancy_query_compares_more_than_the_key_columns():
    """The proof lives in the SQL, so the SQL's load-bearing clauses are pinned.

    Dropping `indclass` from the comparison would make a `text_pattern_ops` prefix index
    look like a duplicate of the PK and delete the one index a prefix search needs.
    Dropping the `btree` restriction would do the same for a GIN index.
    """
    sql = mig._PK_DUPLICATE_SQL
    for clause in ("indkey", "indclass", "indcollation", "btree",
                   "NOT xd.indisunique", "NOT xd.indisprimary",
                   "indpred IS NULL", "indexprs IS NULL", "xd.indisvalid"):
        assert clause in sql, f"missing guard: {clause}"


def _redundant(monkeypatch, rows):
    monkeypatch.setattr(mig, "redundant_pk_indexes", lambda conn: rows)


def _row(table, index, bytes_=1024):
    return {"table": table, "index": index, "pk_index": f"{table}_pkey",
            "bytes": bytes_, "index_def": "", "pk_def": "",
            "droppable": index.startswith("ix_") and len(index) > 3}


def test_check_mode_issues_no_ddl(monkeypatch):
    """The pre-flight an operator points at production must be incapable of writing."""
    _redundant(monkeypatch, [_row("cell_sources", "ix_cell_sources_id")])
    conn = RecordingConn()
    out = mig.drop_redundant_indexes(conn, apply=False)
    assert conn.sql == []
    assert out["dropped"] == []


def test_apply_drops_concurrently_and_idempotently(monkeypatch):
    _redundant(monkeypatch, [_row("cell_sources", "ix_cell_sources_id", 314 * 2 ** 20)])
    conn = RecordingConn()
    out = mig.drop_redundant_indexes(conn, apply=True)
    assert len(out["dropped"]) == 1
    assert conn.sql[0] == ('DROP INDEX CONCURRENTLY IF EXISTS '
                           'public."ix_cell_sources_id"')
    # and the drop is CONFIRMED against the catalogue, not assumed from the return code
    assert any("pg_index" in s for s in conn.sql[1:])


def test_a_hand_written_name_is_reported_and_left_alone(monkeypatch):
    """🔴 Two independent gates, and this is the second one.

    The catalogue query proves redundancy; the name gate proves nobody chose the index
    deliberately. An index that is structurally redundant but named by a human is
    REPORTED, never dropped - dropping the wrong index on a 14 GB database is not
    repaired by re-running the script.
    """
    _redundant(monkeypatch, [_row("cell_sources", "idx_sources_lookup")])
    conn = RecordingConn()
    out = mig.drop_redundant_indexes(conn, apply=True)
    assert conn.sql == []
    assert [r["index"] for r in out["skipped"]] == ["idx_sources_lookup"]


def test_a_failed_drop_does_not_stop_the_others(monkeypatch):
    _redundant(monkeypatch, [_row("a", "ix_a_id"), _row("b", "ix_b_id")])
    conn = RecordingConn(raise_on="ix_a_id")
    out = mig.drop_redundant_indexes(conn, apply=True)
    assert [r["index"] for r in out["failed"]] == ["ix_a_id"]
    assert [r["index"] for r in out["dropped"]] == ["ix_b_id"]


def test_nothing_found_is_a_clean_no_op(monkeypatch):
    """Re-running section 2 after a successful run: the discovery returns nothing."""
    _redundant(monkeypatch, [])
    conn = RecordingConn()
    out = mig.drop_redundant_indexes(conn, apply=True)
    assert conn.sql == [] and out["dropped"] == []


# --- [F2] a drop is not believed on the strength of its return code ----------

def test_a_drop_that_left_the_index_behind_is_not_counted(monkeypatch):
    """🔴 `IF EXISTS` turns a name that matches nothing into a silent success.

    Without the post-drop catalogue check the run prints `Reclaimed 314.0 MB` having
    reclaimed nothing - the same reasoning `build_index` already refuses for itself.
    """
    _redundant(monkeypatch, [_row("cell_sources", "ix_cell_sources_id", 314 * 2 ** 20)])
    monkeypatch.setattr(mig, "index_exists", lambda c, n: (True, True))
    out = mig.drop_redundant_indexes(RecordingConn(), apply=True)
    assert out["dropped"] == []
    assert len(out["failed"]) == 1
    assert "still in the catalogue" in out["failed"][0]["error"]


def test_the_drop_quotes_the_identifier(monkeypatch):
    """PostgreSQL case-folds unquoted identifiers, so `ix_Foo_Id` would become a request
    to drop `ix_foo_id` - a different, probably nonexistent, index."""
    _redundant(monkeypatch, [_row("foo", "ix_Foo_Id")])
    monkeypatch.setattr(mig, "index_exists", lambda c, n: (False, False))
    conn = RecordingConn()
    mig.drop_redundant_indexes(conn, apply=True)
    assert conn.sql == ['DROP INDEX CONCURRENTLY IF EXISTS public."ix_Foo_Id"']


def test_quote_ident_escapes_embedded_quotes():
    assert mig.quote_ident('ix_a"b') == '"ix_a""b"'


# --- [F3] the ordering half of the redundancy proof --------------------------

def test_redundancy_query_compares_sort_direction():
    """`(a, b DESC)` is not a duplicate of a plain `(a, b)` primary key - a backward scan
    reverses the WHOLE key and does not substitute for mixed ordering. Dropping that
    index is the one outcome here a re-run cannot undo."""
    assert "indoption" in mig._PK_DUPLICATE_SQL


# --- [F4] the producer half of the name gate, and the read-only pin ----------

class CatalogueConn:
    """Answers the catalogue queries by matching on the SQL, and records what it ran."""

    def __init__(self, redundant_rows=(), tables=()):
        self.sql = []
        self.invalidated = False
        self.closed = False
        self._redundant = list(redundant_rows)
        self._tables = list(tables)

    def execution_options(self, **kw):
        return self

    def execute(self, clause, params=None):
        s = str(clause)
        self.sql.append(s)
        if "information_schema" in s:
            return _Rows([(t,) for t in self._tables])
        if "xd.indkey = xp.indkey" in s:
            return _Rows(self._redundant)
        return _Rows([])

    def invalidate(self):
        self.invalidated = True

    def close(self):
        self.closed = True


class _Rows(list):
    def fetchall(self):
        return list(self)

    def first(self):
        return self[0] if self else None


class FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def connect(self):
        return self._conn


def test_droppable_is_decided_by_the_query_layer_not_the_caller(monkeypatch):
    """🔴 The PRODUCER half of the "second independent gate".

    The consumer tests above are fed `droppable` by their own helper, so on their own
    they would stay green if `redundant_pk_indexes` started returning `True` for every
    row. This is the test that reads the flag off the real function.
    """
    conn = CatalogueConn(redundant_rows=[
        ("t", "ix_t_id", "t_pkey", 1024, "def", "pkdef"),
        ("t", "idx_handwritten", "t_pkey", 1024, "def", "pkdef"),
        ("t", "ix_", "t_pkey", 1024, "def", "pkdef"),  # prefix only, no column part
    ])
    got = {r["index"]: r["droppable"] for r in mig.redundant_pk_indexes(conn)}
    assert got == {"ix_t_id": True, "idx_handwritten": False, "ix_": False}


def test_check_mode_pins_the_session_read_only_and_then_discards_it():
    """🔴 The defect only an end-to-end run caught, now netted.

    `SET SESSION` lives on the DBAPI connection and `close()` RETURNS that connection to
    the pool rather than closing it. Without `invalidate()` the next checkout inherits
    the read-only flag, and a check run in the same process silently disables the apply
    run that follows it - every CREATE/DROP fails with `ReadOnlySqlTransaction`.
    """
    conn = CatalogueConn()
    mig.run(apply=False, engine=FakeEngine(conn))
    assert any("default_transaction_read_only = on" in s for s in conn.sql)
    assert conn.invalidated, "a read-only-pinned connection must never re-enter the pool"


def test_write_mode_neither_pins_nor_discards():
    """The converse. Invalidating unconditionally would throw away a healthy connection
    on every apply, and pinning unconditionally would make the apply impossible."""
    conn = CatalogueConn()
    mig.run(apply=True, drop_redundant=True, engine=FakeEngine(conn))
    assert not any("default_transaction_read_only" in s for s in conn.sql)
    assert not conn.invalidated


def test_run_reports_both_sections_and_returns_them():
    conn = CatalogueConn(redundant_rows=[("t", "ix_t_id", "t_pkey", 8, "d", "p")])
    out = mig.run(apply=False, engine=FakeEngine(conn))
    assert out["results"] == []
    assert [r["index"] for r in out["redundant"]["found"]] == ["ix_t_id"]
    assert out["redundant"]["dropped"] == []
