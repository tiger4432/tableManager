# -*- coding: utf-8 -*-
"""S-74. The product's DELETE door staged no outbox event, so nothing downstream saw a delete.

Every other write reaches the outbox because SQLAlchemy's `before_flush` walks
`session.deleted`. A bulk `.delete(synchronize_session=False)` never puts the rows in the
session, so that list is empty and the hook has nothing to stage -- and `delete_rows_batch`
is exactly that, with `delete_row` delegating to it, so BOTH doors were invisible.

🔴 MEASURED 2026-09-08, this box's whole outbox history: CREATE 1,618, RETROACTIVE_RUN 1,
DELETE **0** -- while an EDIT of the same row stages normally. The chain and the ledger's
follow-up, which withdraws a deleted row's facts, had therefore never once received a live
deletion; S-54-b's DELETE handling had only ever been exercised by tests.

⚠️ THE PRECEDENT WAS ALREADY HERE. `purge_map_rows` was fixed for the same reason on
2026-09-06 and CODE_MAP called it "the ONLY write the outbox could not see". This is the
second, and that sentence is corrected in the same commit.

⚠️ WHAT THIS FILE SCORES, said plainly: the CODE of the two doors, in the shape
`test_a_map_purge_is_visible_to_the_outbox.py` established for the same question -- that the
staging call is present, is the shared helper rather than a second spelling, and that the
second door reaches it by delegation. Whether the event lands in the table is the live
reproduction the lead PM runs.
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud                                            # noqa: E402


def body_of(function):
    """The function's code with its docstring removed -- what it DOES, not what it says."""
    source = inspect.getsource(function)
    doc = inspect.getdoc(function)
    if doc:
        for line in doc.splitlines():
            source = source.replace(line, "")
    return source


def test_the_batch_delete_stages_the_event():
    body = body_of(crud.delete_rows_batch)
    assert "stage_collapsed_event(" in body
    assert '"DELETE"' in body


def test_it_is_the_same_helper_the_map_purge_uses():
    """⛔ NOT A SECOND SPELLING. Two ways to announce a deletion is how one of them comes to
    be forgotten -- which is the shape this whole defect had."""
    assert "stage_collapsed_event(" in body_of(crud.purge_map_rows)
    assert "stage_collapsed_event(" in body_of(crud.delete_rows_batch)


def test_the_single_row_door_delegates_rather_than_repeating():
    """`delete_row` must reach the outbox by calling the batch, not by staging its own."""
    body = body_of(crud.delete_row)
    assert "delete_rows_batch(" in body
    assert "stage_collapsed_event(" not in body


def test_it_announces_the_rows_that_were_actually_removed():
    """A delete of something already gone is not a deletion, so the ids come from the rows
    that were read, not from what the caller asked for."""
    body = body_of(crud.delete_rows_batch)
    call = body.split("stage_collapsed_event(")[1].split(")")[0]
    assert "rows_to_delete" in call, call
