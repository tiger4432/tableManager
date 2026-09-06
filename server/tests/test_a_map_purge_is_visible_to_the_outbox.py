# -*- coding: utf-8 -*-
"""The one write in this system the outbox could not see.

Every other write reaches `database.stage_event` through SQLAlchemy's `before_flush`, which
walks `session.deleted`. A bulk `.delete(synchronize_session=False)` never loads its rows
into the session, so that list stays empty and a `replace_map` purge produced no event at
all -- no history to ask afterwards, and the graph and the undelivered sweep never learned.
That made this the exception to a rule everything else follows: one capability, two paths.

⛔ AND THERE WERE TWO PURGE SITES, NOT ONE. Measured 2026-09-06: the diff branch
(`removed_row_ids`) and the non-diff branch (`purged_row_ids`) each spelled the same three
deletes by hand. Repairing only the one that had been read would have left the other
invisible -- so both call one helper, and that is what makes the event impossible to add to
one and forget on the other.

⚠️ THIS FILE IS ABOUT THE OUTBOX HALF. The audit-history half was open when this was
written and was closed on 2026-09-07; it is scored in
`test_both_deletion_paths_leave_a_history.py`, and the one assertion here that pinned its
absence is now that absence's inverse rather than a deleted line.
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud, models                                # noqa: E402

TABLE = "dt_map"


def helper_code():
    """`purge_map_rows`'s body with the docstring removed.

    🔴 THE CODE, NOT THE PROSE. The docstring explains the defect and therefore NAMES
    `.delete(synchronize_session=False)`; scoring the raw source makes these assertions
    answer "what does it say" when they mean to ask "what does it do".
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(crud.purge_map_rows).lstrip())
    function = tree.body[0]
    if (function.body and isinstance(function.body[0], ast.Expr)
            and isinstance(function.body[0].value, ast.Constant)):
        function.body = function.body[1:]
    return ast.unparse(function)


def outbox_deletes(db, table_name=TABLE):
    return (db.query(models.DatabaseOutbox)
            .filter(models.DatabaseOutbox.event_type == "DELETE",
                    models.DatabaseOutbox.table_name == table_name)
            .order_by(models.DatabaseOutbox.id.asc()).all())


class FakeModel:
    """Stands in for the dynamic table model: the helper only filters on `row_id`."""


@pytest.fixture
def model():
    return models.CellSource          # any mapped class with a `row_id` column


# ----------------------------------------------------------- the deletion becomes visible

def test_a_purge_stages_an_event_naming_the_rows(db_session, model):
    """🔴 THE POINT. Not "a table changed" - WHICH rows went."""
    ids = [str(uuid.uuid4()) for _ in range(3)]
    crud.purge_map_rows(db_session, model, TABLE, ids)
    db_session.flush()

    events = outbox_deletes(db_session)
    assert events, "the purge is still invisible to the outbox"
    named = [r for e in events for r in (e.payload or {}).get("row_ids", [])]
    assert set(ids) <= set(named)


def test_the_event_is_staged_before_the_deletes_run(db_session, model):
    """The transactional-outbox guarantee: the event must be in the SAME flush that removes
    the rows, or a crash between them loses the notice while keeping the deletion."""
    body = helper_code()
    assert body.index("stage_collapsed_event") < body.index(".delete(")


def test_an_empty_purge_stages_nothing(db_session, model):
    """⛔ NO EVENT FOR NO WORK. An event naming zero rows would be a deletion notice for a
    deletion that never happened."""
    before = len(outbox_deletes(db_session))
    assert crud.purge_map_rows(db_session, model, TABLE, []) == []
    assert crud.purge_map_rows(db_session, model, TABLE, None) == []
    db_session.flush()
    assert len(outbox_deletes(db_session)) == before


def test_it_returns_the_ids_it_acted_on(db_session, model):
    ids = [str(uuid.uuid4())]
    assert crud.purge_map_rows(db_session, model, TABLE, ids) == ids


# ------------------------------------------------------------- both sites use the helper

def test_neither_purge_site_spells_the_deletes_by_hand_any_more():
    """🔴 THE REASON THIS IS A HELPER. Two sites each writing three bulk deletes is how the
    event gets added to one and forgotten on the other."""
    import inspect

    body = inspect.getsource(crud._apply_batch_updates_once)
    assert "purged_row_ids" in body and "removed_row_ids" in body
    for site in ("purge_map_rows(db, table_model, table_name, purged_row_ids)",
                 "purge_map_rows(db, table_model, table_name, removed_row_ids)"):
        assert site in body, "a purge site no longer goes through the helper"
    assert "CellOverwrite.row_id.in_(purged_row_ids)" not in body
    assert "CellOverwrite.row_id.in_(removed_row_ids)" not in body


def test_the_helper_still_clears_the_cell_metadata(db_session, model):
    """The rows' sources and overwrites must go with them; leaving them would make the map
    rows immortal in the two side tables."""
    body = helper_code()
    assert "models.CellSource" in body and "models.CellOverwrite" in body
    assert body.count("synchronize_session=False") == 3


# ------------------------------------------------------- what this does NOT claim to do

def test_the_other_half_is_closed_too():
    """🔴 REPLACED BY ITS INVERSE ON 2026-09-07, NOT RETIRED.

    This used to assert that the docstring still said 「DOES NOT WRITE AUDIT HISTORY」 -- an
    honest note about the half this file did not close. That half IS closed now, so the old
    assertion would have gone red for the right reason; deleting it instead would have left
    the new state unscored, and the file would once again say nothing about audit history
    either way.

    ⚠️ AND THE OLD NOTE IS WHY THE LINE STAYED OPEN. The lead closed grade-zero L-4 off
    the commit TITLE (「the map purge becomes visible to the outbox」) while the function's
    own docstring named the remaining half. One word, 「이력」, meant two things.
    """
    # The first spelling of this asserted the old sentence was GONE, and went red on the
    # new docstring -- which QUOTES that sentence to say when it stopped being true. A
    # text proxy for 'the note is gone' cannot tell a claim from a citation of one, so
    # this asks for the claim the docstring makes NOW and leaves the property itself to
    # `test_both_deletion_paths_leave_a_history.py`, which measures it by running.
    assert "AND IT WRITES AUDIT HISTORY" in crud.purge_map_rows.__doc__
    assert "record_row_deletions" in helper_code(), \
        "the purge stopped going through the one place that records a deletion"


def test_a_delete_event_cannot_wake_the_chain():
    """🔵 MEASURED BEFORE IT WAS WRITTEN, not left to the depth limit - depth bounds an
    unbounded cascade and would not have prevented a NEW one."""
    import inspect
    import re

    import chain_ingestion_worker as worker

    # The module, not one function: the guard appears at every place the worker SELECTS
    # trigger events, and naming the functions would make this test go red on a rename
    # rather than on the property it is about.
    source = inspect.getsource(worker)
    guards = re.findall(r'event_type in [\(\[]"CREATE", "EDIT"[\)\]]', source)
    assert len(guards) >= 3, "the CREATE/EDIT trigger guard moved or shrank: %d" % len(guards)
    assert 'event_type == "DELETE"' not in source
    assert '"DELETE"' not in source.split("def _rule_accepts_event", 1)[1][:400]
