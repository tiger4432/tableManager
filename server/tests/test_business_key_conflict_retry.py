"""[D3] The `IntegrityError` recovery in `crud.apply_batch_updates`.

WHAT THIS GUARDS
`business_key_val` now carries a UNIQUE index, so the cross-process race that used to
produce two rows with one business key produces an `IntegrityError` instead. The wrapper
must turn that into the correct outcome (replay, so the prefetch re-reads the row the
winner committed and merges into it) and must NOT turn any other integrity failure into
a retry loop.

WHY THE TESTS LOOK LIKE THIS
The wrapper is a control-flow shell around `_apply_batch_updates_once`, so the axis that
matters is *which exception leads to which control flow*, not what the write does. A
test that drove real rows through a real database would exercise the write path (already
covered elsewhere) and would exercise the retry only by winning a race, i.e. flakily or
never. So `_apply_batch_updates_once` is replaced by a scripted double, and every test
below asserts on the number of attempts and on `db.rollback()` - the two things the
recovery actually consists of.

Each test names the mutation it kills. The repo has been burned by tests that pass both
with and without the code under test.
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

    def fake_once(db, table_name, batch, replace_report=None):
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


def test_conflict_rolls_back_and_replays_once(monkeypatch, caplog):
    """The headline: lose the race, roll back, replay, return the replay's result.

    The rollback assertion is not decoration - without it the replay would run inside
    an aborted transaction and every statement would fail, so "it retried" and "it
    recovered" are different claims and this test makes both.
    """
    calls = _script(monkeypatch, _pg_error("uq_bk_dt_log"), "MERGED")
    db = FakeDB()
    with caplog.at_level(logging.WARNING, logger="Server"):
        assert crud.apply_batch_updates(db, "dt_log", FakeBatch()) == "MERGED"
    assert len(calls) == 2
    assert db.rollbacks == 1
    assert any("BK Conflict Recovered" in r.message for r in caplog.records), \
        "the recovery must be NAMED in the log; a silent retry hides the race"


def test_sqlite_conflict_is_recovered_too(monkeypatch):
    """The path the test suite's own engine can reach, so this is not PG-only code."""
    calls = _script(monkeypatch, _sqlite_error(), "MERGED")
    db = FakeDB()
    assert crud.apply_batch_updates(db, "dt_log", FakeBatch()) == "MERGED"
    assert len(calls) == 2


def test_unrelated_integrity_error_is_raised_immediately(monkeypatch):
    """No retry, and NO ROLLBACK - the caller owns that failure and its transaction."""
    calls = _script(monkeypatch, _unrelated_error(), "NEVER")
    db = FakeDB()
    with pytest.raises(IntegrityError):
        crud.apply_batch_updates(db, "dt_log", FakeBatch())
    assert len(calls) == 1
    assert db.rollbacks == 0


def test_persistent_conflict_gives_up_and_reraises(monkeypatch, caplog):
    """A genuine duplicate identity must FAIL, loudly, not spin.

    This is the half of the design that stops the recovery from becoming the second
    invisible failure it was created to remove.
    """
    calls = _script(monkeypatch, _pg_error("uq_bk_dt_log"))
    db = FakeDB()
    with caplog.at_level(logging.ERROR, logger="Server"):
        with pytest.raises(IntegrityError):
            crud.apply_batch_updates(db, "dt_log", FakeBatch())
    assert len(calls) == crud.BK_CONFLICT_MAX_RETRIES + 1
    assert db.rollbacks == crud.BK_CONFLICT_MAX_RETRIES + 1
    assert any("BK Conflict Unresolved" in r.message for r in caplog.records)


def test_retry_count_is_bounded_by_the_declared_constant(monkeypatch):
    """Pins attempts to the CONSTANT, not to a literal.

    A test asserting `== 3` would keep passing if someone raised the constant to 50 and
    turned a bounded failure into a hang.
    """
    monkeypatch.setattr(crud, "BK_CONFLICT_MAX_RETRIES", 4)
    calls = _script(monkeypatch, _pg_error("uq_bk_dt_log"))
    with pytest.raises(IntegrityError):
        crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch())
    assert len(calls) == 5


# --- [F1] the payload the replay hands to the resolver -----------------------
# The mutation these kill: dropping the snapshot/restore, which is invisible on a
# single pass and only shows up on attempt 2.

class FakeItem:
    def __init__(self, updates, business_key_val=None, row_id=None):
        self.updates = dict(updates)
        self.business_key_val = business_key_val
        self.row_id = row_id


class MapBatch:
    replace_map = True
    transaction_id = "TX-MAP"

    def __init__(self, items):
        self.updates = items


def _map_table(monkeypatch, name="d3_map", business_key="map_pk",
               composite=("target_table", "map_id")):
    monkeypatch.setitem(crud.TABLE_CONFIG, name, {
        "business_key": business_key,
        "composite_key_source": list(composite),
        "composite_key_separator": "_",
        "column_types": {c: "string" for c in composite},
    })
    return name


def test_the_replay_sees_the_payload_the_caller_handed_over(monkeypatch):
    """🔴 The headline of F1.

    `assemble_composite_business_key` writes the assembled key back into
    `updates[key_col]` in place. `derive_replace_map_scope`'s legacy branch builds the
    purge filters from every non-coordinate column of the FIRST payload row, so on the
    replay that written-back column becomes an EXTRA FILTER: a whole-map purge narrows
    to one row while the route still answers 200 with `deleted: 1`.
    """
    table = _map_table(monkeypatch)
    item = FakeItem({"target_table": "bonding_map", "map_id": "LOT1_01"})
    batch = MapBatch([item])
    seen = []

    def fake_once(db, table_name, b, replace_report=None):
        # what the scope resolver would see on this attempt
        seen.append(dict(b.updates[0].updates))
        crud.assemble_composite_business_key(table_name, b.updates[0])
        if len(seen) == 1:
            raise _pg_error("uq_bk_d3_map")
        return "MERGED"

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    assert crud.apply_batch_updates(FakeDB(), table, batch) == "MERGED"
    assert len(seen) == 2
    assert seen[0] == seen[1], (
        f"the replay derived its scope from a mutated payload: {seen[0]} -> {seen[1]}")
    assert "map_pk" not in seen[1]


def test_the_replay_also_clears_the_assembled_business_key(monkeypatch):
    """The other half of the same in-place write. If `business_key_val` survives, the
    replay's `assemble` short-circuits and the item is no longer re-derived from the
    values the caller actually sent."""
    table = _map_table(monkeypatch)
    item = FakeItem({"target_table": "bonding_map", "map_id": "LOT1_01"})
    batch = MapBatch([item])
    keys = []

    def fake_once(db, table_name, b, replace_report=None):
        keys.append(b.updates[0].business_key_val)
        crud.assemble_composite_business_key(table_name, b.updates[0])
        if len(keys) == 1:
            raise _pg_error("uq_bk_d3_map")
        return "MERGED"

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    crud.apply_batch_updates(FakeDB(), table, batch)
    assert keys == [None, None]


def test_a_key_the_caller_supplied_is_not_stripped_by_the_restore(monkeypatch):
    """The restore must undo OUR write, not the caller's value.

    Popping `updates[key_col]` unconditionally would delete a business key the payload
    genuinely carried, and the replay would then write a row with a NULL key column.
    """
    table = _map_table(monkeypatch)
    item = FakeItem({"target_table": "bonding_map", "map_id": "LOT1_01",
                     "map_pk": "CALLER_SUPPLIED"}, business_key_val="CALLER_BK")
    batch = MapBatch([item])
    seen = []

    def fake_once(db, table_name, b, replace_report=None):
        seen.append((dict(b.updates[0].updates), b.updates[0].business_key_val))
        if len(seen) == 1:
            raise _pg_error("uq_bk_d3_map")
        return "MERGED"

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    crud.apply_batch_updates(FakeDB(), table, batch)
    assert seen[1] == ({"target_table": "bonding_map", "map_id": "LOT1_01",
                        "map_pk": "CALLER_SUPPLIED"}, "CALLER_BK")


def test_the_snapshot_is_not_taken_when_it_cannot_matter(monkeypatch):
    """Cost gate. An ordinary (non-replace_map) ingestion batch of 100,000 items must
    not pay for a snapshot, because nothing there derives a decision from the payload."""
    table = _map_table(monkeypatch)

    class PlainBatch(MapBatch):
        replace_map = False

    assert crud._replay_sensitive_key_column(table, PlainBatch([])) is None
    assert crud._replay_sensitive_key_column(table, MapBatch([])) == "map_pk"


def test_a_table_without_a_composite_key_needs_no_restore(monkeypatch):
    monkeypatch.setitem(crud.TABLE_CONFIG, "d3_plain", {"business_key": "pk"})
    assert crud._replay_sensitive_key_column("d3_plain", MapBatch([])) is None


def test_replace_report_out_param_survives_a_replay(monkeypatch):
    """The 4-tuple contract and the out-param both belong to the WRAPPER now.

    `apply_batch_updates` is unpacked at eight call sites and fills `replace_report` in
    place for the API layer; the rename to `_apply_batch_updates_once` must not have
    moved either responsibility.
    """
    seen = {}

    def fake_once(db, table_name, batch, replace_report=None):
        if not seen:
            seen["first"] = True
            raise _pg_error("uq_bk_dt_log")
        replace_report["deleted"] = 7
        return ([], [], [], [])

    monkeypatch.setattr(crud, "_apply_batch_updates_once", fake_once)
    report = {}
    out = crud.apply_batch_updates(FakeDB(), "dt_log", FakeBatch(), report)
    assert len(out) == 4
    assert report["deleted"] == 7
