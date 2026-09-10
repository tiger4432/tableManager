# -*- coding: utf-8 -*-
"""색인 크기는 «바뀌는 자리»에서 센다 (S-122-b, 판정 250).

🔴 WHAT WAS MEASURED. The paced census asked `count(DISTINCT row_id)` over the row index
for every source, every tick. On the QA box that was 2.055 s for the largest source - not
cheaper than the relation `count(*)` the same round had just removed - so the census went
on crowding the database after its louder half was fixed.

🔴 THE TWO SEATS THAT MOVE THE INDEX ARE BOTH INSIDE THE ATOMS' OWN TRANSACTION, so a
counter maintained there is exact by construction rather than by a repair job. Writing refs
adds the rows gaining their FIRST line; withdrawing them subtracts the rows losing their
LAST.

⛔ DISTINCT ROWS, NOT REF LINES, AND THAT IS THE OLD DEFECT. One physical row wears several
refs when a source says more than one thing about it; counting lines makes the remainder
too small and NEGATIVE on a two-sentence source, which the code that this replaces was
written to avoid. The increment and the decrement are both phrased in rows for that reason.

⚠️ `NULL` MEANS 「NEVER COUNTED」 AND NOT 「ZERO」. A source is counted exactly once - the
first tick that sees it - and maintained from then on; the human `census` command always
counts, which makes it the drift check as well as the plant.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema                                              # noqa: E402


def test_the_column_exists_and_a_database_that_predates_it_gets_it():
    """`create table` is not the only path: an installation older than this column is
    exactly the one that needs it, so the addition table is where it has to be named."""
    assert schema.ROWS_INDEXED_COLUMN == "rows_indexed"
    added = {name for name, _ddl in schema.CURSOR_ADDITIONS}
    assert schema.ROWS_INDEXED_COLUMN in added
    assert f"{schema.ROWS_INDEXED_COLUMN} BIGINT" in dict(schema.CURSOR_ADDITIONS)[
        schema.ROWS_INDEXED_COLUMN]


def test_the_writer_counts_rows_gaining_their_first_line():
    """⛔ NOT `len(rows)`. A source emitting two sentences about one row writes two lines
    and gains ONE row, and the difference is what kept the remainder from going negative."""
    import inspect

    from ledger import store

    body = inspect.getsource(store.LedgerStore._write_row_refs)
    assert "count(DISTINCT row_id)" in body, body[:600]
    assert "len(row_ids) - int(cursor.fetchone()[0] or 0)" in body, body[:600]
    # And it must not touch a source nobody has counted yet. Asserted on the CONSTANT's
    # name, not on its value: a literal here would be a second spelling of the column.
    assert "ROWS_INDEXED_COLUMN} IS NOT NULL" in body


def test_the_forgetter_counts_rows_losing_their_last_line_per_source():
    """🔴 GROUPED, BECAUSE ONE STATEMENT SPEAKS FOR SEVERAL SOURCES. `forget_row_refs` with
    no `source` drops every speaker's line about a deleted row - its own docstring says why
    - so a single number would credit one source with another's rows."""
    import inspect

    from ledger import store

    body = inspect.getsource(store.LedgerStore.forget_row_refs)
    assert "GROUP BY source_who" in body, body[:800]
    assert "GREATEST" in body, "a counter that can go negative is worse than one that stops"
    assert "ROWS_INDEXED_COLUMN} IS NOT NULL" in body


def test_the_paced_census_reads_the_counter_and_the_command_counts():
    """The whole point: the tick must not scan, and the exact answer must still exist."""
    import inspect

    from ledger import backfill

    body = inspect.getsource(backfill.rows_not_yet_translated)
    assert "if exact_rows is False:" in body, body[:900]
    assert "ROWS_INDEXED_COLUMN" in body
    # The scan is still reachable - for the CLI, and for a source never planted.
    assert "count(DISTINCT row_id)" in body


def test_a_census_line_says_which_of_the_two_answered():
    """⚠️ BOTH ARE EXACT AND THEY ARE NOT THE SAME ACT. A counted value maintained inside
    the atoms' commit and a fresh count are both true; an operator reading the line is
    entitled to know which one produced the number."""
    import inspect

    from ledger import backfill

    body = inspect.getsource(backfill.measure_row_census)
    assert "rows_indexed (counted at write time)" in body, body[-1200:]
    assert "indexed_rows_counted_now" in body


def test_the_flag_survives_the_stamping_because_it_did_not_the_first_time():
    """🔴 CAUGHT BY THE GATE, NOT BY A TEST. `measure_row_census` builds a NEW dict and
    copies named keys into it, so the flag set on the inner report never reached
    `measure_and_store` - the plant never fired and every counter stayed NULL after a full
    lap. It is carried explicitly now."""
    import inspect

    from ledger import backfill

    body = inspect.getsource(backfill.measure_row_census)
    assert 'stamped["indexed_rows_counted_now"]' in body, body[-1200:]

    planted = inspect.getsource(backfill.measure_and_store)
    assert 'census.get("indexed_rows_counted_now")' in planted, planted[:900]


def test_drift_is_named_rather_than_quietly_corrected():
    """⛔ BOTH SEATS ARE INSIDE THE ATOMS' COMMIT, so a difference is not a rounding error -
    it means one of them was not reached. A counter that silently corrects itself can never
    tell anybody it was wrong."""
    import inspect

    from ledger import backfill, store

    assert "drifted" in inspect.getsource(backfill.measure_and_store)
    plant = inspect.getsource(store.LedgerStore.plant_rows_indexed)
    assert "return None if previous is None" in plant, plant[-500:]


def test_the_lap_line_separates_what_it_measured_from_what_it_rested():
    """🔴 THE WALL CLOCK WAS BOTH (S-127 carry-over, 판정 14:09). The lap line reported
    `time.monotonic() - lap_started`, which includes the pacing sleeps between units - so
    「15 source(s) in 45.3s」 could be 45 s of database work or 0.3 s of it and 45 s of
    deliberate rest, and those two ask an operator to do opposite things.

    ⛔ THE PACE IS THE THING BEING TUNED, so a number that moves when the pace moves cannot
    be the number used to judge the pace. `measured` does not move with `rest`.
    """
    import inspect

    import chain_ingestion_worker as worker

    body = inspect.getsource(worker._ledger_census_loop) if hasattr(
        worker, "_ledger_census_loop") else inspect.getsource(worker)

    assert "measured %.3fs" in body, "the lap line names the paused-excluded time"
    assert "measured_seconds += time.monotonic() - source_started" in body
    # ⚠️ Timed OUTSIDE the try, so a source that RAISED still carries its cost.
    # Counting only the successes would report a lap as cheaper than it was.
    assert body.index('logger.warning("[LedgerCensus] %s failed: %s", source, exc)') <         body.index("measured_seconds += time.monotonic() - source_started")
