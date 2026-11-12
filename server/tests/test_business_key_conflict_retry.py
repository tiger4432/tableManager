"""[D3] The `IntegrityError` refusal in `crud.apply_batch_updates`.

WHAT THIS GUARDS
Two writers of one new business key end on one row inside `write_lines`' claim (ON CONFLICT on the key's unique
index) - the replay that once turned the lost race into a merge is retired with the race (lead 11-11 ㄹ; its PG
meaning, one row on the competitor's row_id, is `test_pg_multirow_upsert`'s). What is left: every IntegrityError is
refused by name, after a rollback, with a line that says what to do next - and the detector stays narrow.

WHY THE TESTS LOOK LIKE THIS
`_apply_batch_updates_once` is replaced by a scripted double; the tests assert on the number of attempts, on
`db.rollback()` and on the refusal line.
"""
import logging

import pytest
from sqlalchemy.exc import IntegrityError

import database.crud as crud


# --- doubles ---------------------------------------------------------------

class FakeDB:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class FakeBatch:
    def __init__(self, n=3, tx="TX-1"):
        self.updates = list(range(n))
        self.transaction_id = tx


def _pg_error(constraint):
    """An `IntegrityError` shaped like psycopg2's, including `orig.diag`."""
    class Diag:
        constraint_name = constraint

    class Orig(Exception):
        pgcode = "23505"
        diag = Diag()

        def __str__(self):
            return (f'duplicate key value violates unique constraint "{constraint}"\n'
                    f"DETAIL:  Key (business_key_val)=(LOT-A|01) already exists.")

    return IntegrityError("INSERT ...", {}, Orig())


def _sqlite_error(column="business_key_val"):
    """What the suite's own engine raises for the same event: no code, no name."""
    return IntegrityError("INSERT ...", {},
                          Exception(f"UNIQUE constraint failed: dt_log.{column}"))


def _unrelated_error():
    """A DIFFERENT constraint failing. Must never be retried."""
    class Diag:
        constraint_name = "idx_sources_lookup_source"

    class Orig(Exception):
        pgcode = "23505"
        diag = Diag()

        def __str__(self):
            return ('duplicate key value violates unique constraint '
                    '"idx_sources_lookup_source"')

    return IntegrityError("INSERT ...", {}, Orig())


def _script(monkeypatch, *outcomes):
    """Replace the inner write with a scripted sequence; return the attempt log."""
    calls = []

    def fake_once(db, table_name, batch, replace_report=None, drop_report=None, deleted_edits=None):
        outcome = outcomes[len(calls)] if len(calls) < len(outcomes) else outcomes[-1]
        calls.append(table_name)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    return calls


# --- the detector ----------------------------------------------------------
# (Mutation killed: widening the test to "any IntegrityError", which is the natural
#  shortcut and the one that would silently swallow a real constraint failure.)

def test_detector_accepts_postgres_bk_violation():
    assert crud._is_business_key_unique_violation(_pg_error("uq_bk_dt_log"))


def test_detector_accepts_sqlite_message():
    assert crud._is_business_key_unique_violation(_sqlite_error())


def test_detector_rejects_a_different_unique_constraint():
    """23505 is not enough. The constraint has to be OURS."""
    assert not crud._is_business_key_unique_violation(_unrelated_error())


def test_detector_rejects_not_null_and_foreign_key():
    class Orig(Exception):
        pgcode = "23502"
        diag = type("D", (), {"constraint_name": None})()

        def __str__(self):
            return 'null value in column "updated_by" violates not-null constraint'

    assert not crud._is_business_key_unique_violation(
        IntegrityError("INSERT ...", {}, Orig()))


def test_detector_rejects_sqlite_unique_on_another_column():
    assert not crud._is_business_key_unique_violation(_sqlite_error("row_id"))


# --- the control flow ------------------------------------------------------

def test_no_conflict_calls_the_write_exactly_once(monkeypatch):
    """The happy path must not have grown an extra attempt."""
    calls = _script(monkeypatch, "RESULT")
    db = FakeDB()
    assert crud.apply_batch_updates(db, "dt_log", FakeBatch()) == "RESULT"
    assert len(calls) == 1
    assert db.rollbacks == 0


def test_unrelated_integrity_error_is_raised_immediately(monkeypatch):
    """No retry — the narrowness of the detector is the point and it is unchanged.

    ⚰️ THIS USED TO ASSERT `rollbacks == 0`, on 「the caller owns that failure and its
    transaction」. Production disproved it on 2026-09-16 (S-269): the caller cannot own a
    transaction it does not know is aborted, and its next attribute read raised
    「Instance is not bound to a Session」 — an error naming SQLAlchemy, with the
    constraint's name nowhere and no action in it. See the two tests below.
    """
    calls = _script(monkeypatch, _unrelated_error(), "NEVER")
    db = FakeDB()
    with pytest.raises(IntegrityError):
        crud.apply_batch_updates(db, "dt_log", FakeBatch())
    assert len(calls) == 1


# --- S-269: a constraint this lane cannot recover from is refused BY NAME --

def test_a_constraint_this_lane_cannot_recover_from_rolls_the_session_back(monkeypatch):
    """🔴 THE GATE. One rollback, before the raise — so the caller's next statement meets a
    usable session instead of an aborted transaction. The mutation this kills is the
    original code: `raise` with no rollback, which is green on every assertion about
    retries and control flow and was wrong for a year."""
    _script(monkeypatch, _unrelated_error(), "NEVER")
    db = FakeDB()

    with pytest.raises(IntegrityError):
        crud.apply_batch_updates(db, "dt_log", FakeBatch())

    assert db.rollbacks == 1, "the session was left holding an aborted transaction"


def test_the_refusal_names_the_constraint_and_the_next_action(monkeypatch, caplog):
    """⚠️ THE LINE IS THE ONLY RECORD — production logs cannot be pasted, so the sentence
    carries the constraint, the size of the refused batch and what to do next.

    🔴 AND THE ACTION IS NOT GUESSED HERE. `idx_sources_lookup_source` is not an index this
    product built from a declaration, and the two repairs for a unique violation are
    OPPOSITE (fold the rows / widen the key), so the line says 「가르십시오」 and names where
    that is decided. Choosing one would destroy a fact whenever it chose wrong."""
    _script(monkeypatch, _unrelated_error(), "NEVER")
    caplog.clear()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(IntegrityError):
            crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch())

    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Ingest:")]
    assert len(lines) == 1, [r.getMessage() for r in caplog.records]
    assert "idx_sources_lookup_source" in lines[0]
    assert "dt_log" in lines[0]
    assert "→ 다음: " in lines[0]
    assert "RUN.md" in lines[0], "the operator is told where the two repairs are told apart"
    assert "Instance is not bound" not in lines[0]


def test_an_index_the_product_built_is_repaired_by_retracting_its_declaration(monkeypatch,
                                                                              caplog):
    """🔴 THE ONE CASE WHERE THE PRODUCT DOES KNOW THE REPAIR (S-248). A `uq_vjoin_` index
    exists because a join declaration asked for it, and it lives exactly as long as that
    declaration — so the action is to retract the declaration, never a hand-rolled
    `DROP INDEX`, which the next restart would undo.

    ⚠️ The fixture's constraint differs from the one above in EXACTLY the claimed thing:
    the prefix that says who built it."""
    from chain import join_key_index as vjc

    class Diag:
        constraint_name = vjc.INDEX_PREFIX + "dt_log_wafer"

    class Orig(Exception):
        pgcode = "23505"
        diag = Diag()

        def __str__(self):
            return 'duplicate key value violates unique constraint "%s"' % Diag.constraint_name

    _script(monkeypatch, IntegrityError("INSERT ...", {}, Orig()), "NEVER")
    caplog.clear()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(IntegrityError):
            crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch())

    line = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Ingest:")][0]
    assert Diag.constraint_name in line
    assert "DROP INDEX" in line and "하지 마십시오" in line
    assert "RUN.md" not in line, "the product knows this repair; it must not punt"


def test_a_failing_refusal_line_does_not_replace_the_refusal(monkeypatch, caplog):
    """🔴 [S-275] 「진단기는 자기가 진단하는 것을 죽일 수 없다」. The line that EXPLAINS the
    refusal reads `batch.updates`, asks the exception for a constraint name and imports two
    modules; any of that can raise, and then the `raise` below it is never reached - the
    operator gets something other than the named `IntegrityError` this seat exists to hand
    them. The class landed nine minutes before this seat was written (`d00ac580`) and this
    call was left bare.

    ⚠️ AND THE FOLD IS SAID OUT LOUD - a diagnostic that quietly stops being written is one
    nobody knows to miss."""
    original = _unrelated_error()
    _script(monkeypatch, original, "NEVER")
    monkeypatch.setattr(crud, "_say_the_constraint_refused_this_batch",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("line is broken")))
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        with pytest.raises(IntegrityError) as raised:
            crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch())

    assert raised.value is original, "the diagnostic replaced the refusal it describes"
    folded = [r.getMessage() for r in caplog.records if "refusal line skipped" in r.getMessage()]
    assert len(folded) == 1, [r.getMessage() for r in caplog.records]
    assert "dt_log" in folded[0] and "RuntimeError" in folded[0]


def test_the_constraint_name_is_read_in_both_dialects():
    """SQLite gives no `diag` at all, and a reader that only understood PostgreSQL could
    never be exercised by this suite - the same two-dialect reason
    `_is_business_key_unique_violation` has."""
    assert crud._violated_constraint_name(_pg_error("uq_bk_dt_log")) == "uq_bk_dt_log"
    assert crud._violated_constraint_name(_sqlite_error()) == "dt_log.business_key_val"
    assert crud._violated_constraint_name(
        IntegrityError("INSERT ...", {}, Exception("something else"))) == ""
