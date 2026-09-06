# -*- coding: utf-8 -*-
"""「무엇이 지워졌나」 has an answer for BOTH ways a row can go.

🔴 THE HALF THAT STAYED OPEN. `delete_rows_batch` had recorded every row it removed since
long before; the map purge recorded none. Same act — 「행을 지운다」 — and only one of them
left a place to ask afterwards. The rows are gone either way; what was missing was the
question's answer, and an absent answer is indistinguishable from 「아무것도 안 지워졌다」.

🔴 AND THE REPAIR SAID SO ITSELF. `purge_map_rows` closed the OUTBOX half on 2026-09-06 and
its own docstring spelled out the part it had not closed — 「IT DOES NOT WRITE AUDIT
HISTORY」. One word, 「이력」, meant two things (audit log · outbox visibility), and reading
the commit title closed the line on half of it.

⚠️ ONE PLACE, WHICH IS WHAT MAKES THE MUTATION SPLIT. `record_row_deletions` is called by
both paths, so deleting the recording in that one place has to redden BOTH of the tests
below. If only one goes red, the paths are not sharing after all and this file says so.
"""
import os
import sys
import uuid

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import crud, models                                # noqa: E402

TABLE = "dt_map"


@pytest.fixture
def model():
    """Any mapped class with a `row_id`, the way the sibling outbox file uses it."""
    return models.CellSource


def seeded(db, ids):
    """Rows the purge can find BEFORE it deletes them.

    🔴 THE FIXTURE IS PART OF THE ASSERTION. With nothing to find, the purge records
    nothing and 「it wrote no history」 and 「there was nothing to write about」 look the
    same — the exact confusion this file exists to end.
    """
    for row_id in ids:
        db.add(models.CellSource(table_name=TABLE, row_id=row_id,
                                 column_name="c", source_name="s"))
    db.flush()
    return ids


def deletion_logs(db, table_name=TABLE):
    return (db.query(models.AuditLog)
            .filter(models.AuditLog.table_name == table_name,
                    models.AuditLog.column_name == "DELETE")
            .order_by(models.AuditLog.id.asc()).all())


# --------------------------------------------------------------- the purge path, closed

def test_a_map_purge_leaves_a_row_saying_what_went(db_session, model):
    """🔴 THE GATE. Not 「a table shrank」 — WHICH rows, and one entry each."""
    ids = seeded(db_session, [str(uuid.uuid4()) for _ in range(3)])
    crud.purge_map_rows(db_session, model, TABLE, ids)
    db_session.flush()

    logs = deletion_logs(db_session)
    assert logs, "the purge still leaves no way to ask what was deleted"
    assert {log.row_id for log in logs} == set(ids)


def test_the_purge_records_nothing_when_there_was_nothing_to_delete(db_session, model):
    """⚠️ ABSENT IS NOT ZERO, AND ZERO IS NOT A LIE. Asking to purge ids that do not exist
    must not invent history for rows that never went anywhere."""
    crud.purge_map_rows(db_session, model, TABLE, [str(uuid.uuid4())])
    db_session.flush()
    assert deletion_logs(db_session) == []


# ------------------------------------------------- the path that already recorded, intact

def test_the_helper_is_what_the_batch_path_uses(db_session):
    """🔴 NO-REGRESSION, AND THE REASON THE MUTATION SPLITS. The batch path used to spell
    this block inline; it now calls the same place the purge does. Asserted on the CODE
    because the two paths sharing is the property, and a passing behaviour test would hold
    just as well if the block had been copied — which is how `_bare` became four bodies
    under one name.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(crud.delete_rows_batch).lstrip())
    body = ast.unparse(tree.body[0])
    assert "record_row_deletions(" in body, "the batch path stopped sharing the recorder"
    assert "create_audit_log(" not in body, "the batch path spells the recording again"


def test_the_recorder_writes_one_entry_per_row_and_carries_the_key(db_session):
    """The content the operator actually reads: which row, and its business key."""
    class Row:
        def __init__(self, row_id):
            self.row_id = row_id
            self.business_key_val = "BK-" + row_id[:4]

    rows = [Row(str(uuid.uuid4())) for _ in range(2)]
    tx = str(uuid.uuid4())
    logs = crud.record_row_deletions(db_session, TABLE, rows, "tester", tx)
    db_session.flush()

    assert len(logs) == 2
    assert {log["row_id"] for log in logs} == {row.row_id for row in rows}
    assert {log["business_key"] for log in logs} == {row.business_key_val for row in rows}
    assert {log["transaction_id"] for log in logs} == {tx}
    stored = deletion_logs(db_session)
    assert {log.row_id for log in stored} == {row.row_id for row in rows}


def test_a_row_without_a_business_key_is_still_recorded(db_session):
    """⚠️ THE PURGE'S ROWS ARE NOT THE BATCH'S. A model without `business_key_val` must
    still get an entry — dropping it would make this half quietly narrower than the other."""
    class Bare:
        row_id = str(uuid.uuid4())

    logs = crud.record_row_deletions(db_session, TABLE, [Bare()], "tester",
                                     str(uuid.uuid4()))
    assert len(logs) == 1 and logs[0]["business_key"] is None


def test_the_recorder_does_not_publish_to_the_in_memory_cache(db_session):
    """⚠️ THE SPLIT IS DELIBERATE AND IS WRITTEN DOWN. The cache is a post-COMMIT concern
    and this function does not own the commit — the purge runs inside a batch that commits
    later, so publishing here would seed the cache from a transaction that can still roll
    back. Asserted so the omission reads as a decision rather than as a gap.
    """
    import inspect

    body = inspect.getsource(crud.record_row_deletions)
    assert "audit_cache" not in body.split('"""')[-1]
    assert "post-COMMIT concern" in crud.record_row_deletions.__doc__
