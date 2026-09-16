# -*- coding: utf-8 -*-
"""S-248. 제품이 세운 유일 인덱스는 «그것을 요구하는 조인»만큼만 산다.

🔴 THE OUTAGE THIS CLOSES, MEASURED ON THE BOX 2026-09-15. S-235 built
`uq_vjoin_dt_inventory_…` while that join was live and the data happened to be clean. The
join was later refused, migrated and switched off - and the INDEX stayed. `dedup` then
inserted an inventory row that collided with it: 23505, the group permanently failed, and
every retry failed the same way, on a different row each time.

⛔ AND THE WRITE GATE COULD NOT SEE IT. `crud.refuse_virtual_join_duplicates` knows the keys
of VERIFIED rules, so an index whose rule is gone bites from OUTSIDE the gate. 「규칙 없는
인덱스」 is the defect, and the product taking back its own is the fix.

⚠️ THE PREFIX IS THE WHOLE SAFETY. An index an operator built under their own name does not
start with `uq_vjoin_` and can never be retracted here.
"""
import os
import sys

import pytest

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from chain import unique_key                                   # noqa: E402
from virtual_join.config import INDEX_PREFIX                          # noqa: E402

PRESENT = [("dt_inventory", INDEX_PREFIX + "dt_inventory_dt_job_ns"),
           ("dt_log", INDEX_PREFIX + "dt_log_core_lot_ns")]


class _Connection:
    def __init__(self, sink):
        self.sink = sink

    def execution_options(self, **_kwargs):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, statement, *_a, **_k):
        self.sink.append(str(statement))


class _Bind:
    def __init__(self, sink, dialect="postgresql"):
        self.sink = sink
        self.dialect = type("D", (), {"name": dialect})()

    def connect(self):
        return _Connection(self.sink)


class _Session:
    """⚠️ A FAKE BIND THAT CAPTURES DDL, the style this suite already uses for DDL - the
    subject is the STATEMENT, and a real PostgreSQL is not available to every checkout."""

    def __init__(self, sink, present=None, dialect="postgresql", probe_error=None):
        self._bind = _Bind(sink, dialect)
        self.present = PRESENT if present is None else present
        self.probe_error = probe_error
        self.calls = 0
        self.rolled_back = 0

    def get_bind(self):
        return self._bind

    def execute(self, *_a, **_k):
        self.calls += 1
        if self.probe_error:
            raise RuntimeError(self.probe_error)
        return type("R", (), {"fetchall": lambda _s: list(self.present)})()

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture(autouse=True)
def _forget(monkeypatch):
    """⚠️ THE MEMO IS PROCESS-WIDE, so a case that left one behind would decide the next."""
    unique_key.forget_retractions()
    monkeypatch.delenv("ASSY_VJOIN_AUTO_INDEX", raising=False)
    yield
    unique_key.forget_retractions()


def test_an_index_no_live_join_requires_is_dropped_and_the_required_one_is_kept():
    """🔴 ONE DDL, AND IT IS THE ONE AN OPERATOR WOULD HAVE TYPED. `CONCURRENTLY` because a
    DROP that locks the table is the same outage wearing a different hat, and `IF EXISTS`
    because two processes may reach this at once."""
    ddl = []
    db = _Session(ddl)
    required = {PRESENT[0][1]}

    report = unique_key.retract_unrequired_once(db, required)

    assert report["dropped"] == [PRESENT[1][1]]
    assert report["kept"] == [PRESENT[0][1]]
    assert ddl == ['DROP INDEX CONCURRENTLY IF EXISTS "%s"' % PRESENT[1][1]]


def test_asking_twice_with_the_same_required_set_touches_the_database_once():
    """⚠️ THIS RUNS BEHIND THE READ PATH'S TTL. Asking again with the same set can only give
    the same answer, so a second database call buys nothing and costs a read."""
    ddl = []
    db = _Session(ddl)
    required = {PRESENT[0][1]}

    unique_key.retract_unrequired_once(db, required)
    unique_key.retract_unrequired_once(db, required)

    assert db.calls == 1 and len(ddl) == 1


def test_the_switch_off_touches_no_database_at_all(monkeypatch):
    """⛔ OFF IS OFF (§0-ter ③). The same sentence `ensure_once` learned the day a switch that
    still probed took the read path down with it - and the report says the switch's NAME, so
    an operator reading it knows which one they turned."""
    monkeypatch.setenv("ASSY_VJOIN_AUTO_INDEX", "0")
    ddl = []
    db = _Session(ddl)

    report = unique_key.retract_unrequired_once(db, set())

    assert db.calls == 0 and ddl == []
    assert "ASSY_VJOIN_AUTO_INDEX" in report["skipped"]
    assert report["dropped"] == []


def test_a_dialect_that_is_not_postgresql_is_skipped_by_name():
    ddl = []
    db = _Session(ddl, dialect="sqlite")

    report = unique_key.retract_unrequired_once(db, set())

    assert db.calls == 0 and ddl == []
    assert "sqlite" in report["skipped"]


def test_a_probe_failure_rolls_back_and_says_so_rather_than_raising():
    """🔴 A FAILURE HERE MUST NOT POISON THE SESSION THAT FOLLOWS. On PostgreSQL a failed
    statement aborts the transaction, so the rollback is what keeps the caller's next read
    alive - the exact shape that took the read path down on 2026-09-14."""
    ddl = []
    db = _Session(ddl, probe_error="relation pg_index does not exist")

    report = unique_key.retract_unrequired_once(db, set())

    assert db.rolled_back == 1 and ddl == []
    assert "pg_index" in report["skipped"]


def test_only_this_products_own_indexes_are_ever_considered():
    """⚠️ THE PREFIX IS THE SAFETY. An operator's own unique index has another name, so it is
    not in the population this function can see at all."""
    import inspect

    body = inspect.getsource(unique_key.product_indexes)

    assert "INDEX_PREFIX" in body and "indisunique" in body


def test_one_index_that_cannot_be_dropped_does_not_stop_the_rest():
    """⚠️ ONE FAILURE IS ONE INDEX. An index still in use by a running query is a reason to
    leave THAT one and go on - 「값 하나가 배치를 죽이지 않는다」 at the DDL level."""
    ddl = []
    db = _Session(ddl, present=[("t1", INDEX_PREFIX + "one"),
                                ("t2", INDEX_PREFIX + "two")])
    first = {"n": 0}

    def flaky(statement, *_a, **_k):
        first["n"] += 1
        if first["n"] == 1:
            raise RuntimeError("index is in use")
        ddl.append(str(statement))

    db.get_bind().connect = lambda: type(
        "C", (), {"execution_options": lambda _s, **_k: _s,
                  "__enter__": lambda _s: _s, "__exit__": lambda *_a: False,
                  "execute": flaky})()

    report = unique_key.retract_unrequired_once(db, set())

    assert report["dropped"] == [INDEX_PREFIX + "two"]
    assert len(ddl) == 1


# ---------------------------------------------------------------------------
# 🔴 ⓒ — the failure line names the cause
# ---------------------------------------------------------------------------

def test_the_failure_cause_is_the_last_line_not_the_word_traceback():
    """🔴 A TRACEBACK'S FIRST LINE IS 「Traceback (most recent call last):」. So the one
    line an operator got about a permanent failure said nothing at all, and the sentence that
    names the cause sat below the cut - measured on the box as a full day of 「매번 다른
    행에서 permanently failed」 with no visible reason.

    ⚠️ SCORED ON THE FUNCTION, not on the module's text. A source-substring check would go
    red when the line is reformatted and green when the right words appear in a comment."""
    from chain.ingestion_worker import failure_cause

    lines = ["Traceback (most recent call last):",
             '  File "x.py", line 1, in <module>',
             "    do_it()",
             'psycopg2.errors.UniqueViolation: duplicate key value violates unique '
             'constraint "uq_vjoin_dt_inventory_dt_job_ns"']
    traceback_text = chr(10).join(lines)

    assert failure_cause(traceback_text).startswith("psycopg2.errors.UniqueViolation")
    assert "uq_vjoin_dt_inventory_dt_job_ns" in failure_cause(traceback_text)
    assert failure_cause("one line only") == "one line only"
    assert failure_cause("") == "(no reason recorded)"
    assert failure_cause(None) == "(no reason recorded)"
