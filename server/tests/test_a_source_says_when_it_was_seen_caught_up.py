# -*- coding: utf-8 -*-
"""S-65 ①. "Caught up" has to be SEEN, and the seeing has to be a measurement.

판정 144 splits the two paths: the outbox is the live path and the cursor is the catch-up
path, and a source may only hand new rows to the live path once it has been observed with
nothing past its cursor. That observation is the whole safety of the design -- hand it over
early and rows are skipped by both paths -- so this file is about WHAT is allowed to write
the mark.

🔴 THE MISTAKE THIS GUARDS IS "THE LOOP ENDED". A run stopped by `max_batches`, by the
pacing checkpoint, or by an operator's cancel also reaches the end of its page loop, and a
source cut short is not caught up. The run therefore asks `rows_past_cursor`, whose
`(rows, complete)` pair is the property itself: `complete` is what makes a zero exact
rather than a short read.

⚠️ NULL IS NOT "BEHIND", IT IS "NEVER SEEN CAUGHT UP" -- a source that has never run reads
NULL too, and neither may be treated as caught up.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger import schema                                            # noqa: E402


def test_the_shipped_table_declares_the_mark():
    """A NEW deployment gets the column from the CREATE, not from a migration."""
    assert schema.CAUGHT_UP_COLUMN == "caught_up_at"
    assert f"{schema.CAUGHT_UP_COLUMN} " in schema.CREATE_CURSOR
    assert "TIMESTAMPTZ" in schema.CREATE_CURSOR.split(schema.CAUGHT_UP_COLUMN)[1][:40]


def test_an_existing_deployment_is_migrated_to_it():
    """🔴 THE CREATE ALONE IS NOT ENOUGH, and that is the older half of this failure class.

    `CREATE TABLE IF NOT EXISTS` does nothing to a box that already has the table, so a
    column that lives only in the CREATE reaches new installs and no existing one. The
    addition list is the half that reaches the boxes that are already running.
    """
    added = {column for column, _statement in schema.CURSOR_ADDITIONS}
    assert schema.CAUGHT_UP_COLUMN in added
    statement = next(sql for column, sql in schema.CURSOR_ADDITIONS
                     if column == schema.CAUGHT_UP_COLUMN)
    assert statement.startswith(f"ALTER TABLE {schema.CURSOR_TABLE} ADD COLUMN ")
    assert "TIMESTAMPTZ" in statement


def test_the_decision_reads_the_relation_and_not_the_loop():
    """The run decides from `rows_past_cursor`, and both halves of its answer are used.

    ⚠️ THIS IS A TEXT ASSERTION ABOUT ONE DECISION, AND IT IS DELIBERATELY NARROW. What it
    pins is that the stamp is computed from the measurement's two-part answer rather than
    from a control-flow flag -- `result["stopped"]`, a loop-exit boolean, a batch count.
    The behavioural half (a run cut short by `max_batches` leaves the mark unset) needs a
    live source and is the next gate, not this one.
    """
    import inspect

    from ledger import backfill

    body = inspect.getsource(backfill._run_v2_lineage)
    decision = body.split('result["caught_up"]')[1].split("\n")[0]
    assert "rows_past_cursor" in body
    assert "exact" in decision and "remaining == 0" in decision, decision
    assert "stopped" not in decision, decision
