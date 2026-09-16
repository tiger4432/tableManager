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

    def fake_once(db, table_name, batch, replace_report=None, drop_report=None):
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
    from virtual_join import config as vjc

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
    # 🔴 [S-247] THE LINE HAS TO SAY WHAT TO DO NEXT, and this assertion used to pin
    # only the TAG. 「중복 키」 here means the table's own identity does not tell two rows
    # apart, so the repair is the DECLARATION - the opposite of the join-key lines, which
    # send the operator to the data. An operator who reaches for the fix that worked there
    # gets it backwards, and the tag alone gave them nothing to tell the two apart with.
    import operator_line

    refusal = [r.message for r in caplog.records if "[BKConflict:dt_log]" in r.message]
    assert len(refusal) == 1, [r.message for r in caplog.records]
    assert "→ 다음: " in refusal[0]
    assert "composite_key_source" in refusal[0]
    assert operator_line.widen_the_key(
        "table_config 의 'dt_log' 의 `composite_key_source`",
        "두 행을 가르는 컬럼") in refusal[0]


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
    """The three identity fields `assemble_composite_business_key` writes, and no more.

    🔴 `_supplied_business_key_val` IS NOT OPTIONAL HERE (판정 191). A fake thinner
    than the real `GeneralUpdateItem` does not fail loudly at the seam it is thin at - it
    simply never walks that arm, so the snapshot/restore of the third field would go
    unmeasured while these tests stayed green.
    """

    def __init__(self, updates, business_key_val=None, row_id=None):
        self.updates = dict(updates)
        self.business_key_val = business_key_val
        self.row_id = row_id
        self._supplied_business_key_val = None


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

    def fake_once(db, table_name, b, replace_report=None, drop_report=None):
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

    def fake_once(db, table_name, b, replace_report=None, drop_report=None):
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

    def fake_once(db, table_name, b, replace_report=None, drop_report=None):
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

    def fake_once(db, table_name, batch, replace_report=None, drop_report=None):
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
