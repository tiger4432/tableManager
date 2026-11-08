"""QA 11-08 (1a501ad8b's retry): a withdrawal of what a deleted row fed that loses a lock part way - at the EDIT it
stages, or at a shell's delete - is raised at once, so the group rewinds whole and nothing half done is kept. A retry
inside ran after its pages had released their steps: it found nothing, told nothing, deleted no shell."""
import sys

import pytest
from sqlalchemy.exc import OperationalError

from tests.test_a_chain_layer_is_one_per_source_row import (  # noqa: F401
    fixture_db, _write, _drain, _id, SRC, TGT)
from chain import cell_layer
from chain import ingestion_worker as worker
from database import crud, models
import database.database as dbmod
from utils.payload_helper import get_payload_dict


def _edits_of(db, table, after):
    return [(e.event_type, sorted(get_payload_dict(e).get("row_ids") or [get_payload_dict(e).get("row_id")]))
            for e in db.query(models.DatabaseOutbox).filter(models.DatabaseOutbox.id > after,
                                                             models.DatabaseOutbox.table_name == table)]


def _deleted(db):
    ids = [_id(db, SRC, "s1")]
    crud.delete_rows_batch(db, SRC, ids, "cl")
    db.commit()
    return ids, db.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()[0]


def _withdraw(db, ids, lost):
    if lost:
        with pytest.raises(OperationalError):
            worker._withdraw_unanswered_deletions(db, {SRC: ids}, "unanswered")
        db.rollback()
    else:
        worker._withdraw_unanswered_deletions(db, {SRC: ids}, "unanswered")
        db.commit()
    db.expire_all()


@pytest.mark.parametrize("lost", [False, True])
def test_a_lock_lost_at_the_edit_it_stages_is_raised_and_rewinds_whole(db, monkeypatch, lost):
    _write(db, SRC, "user", s="s1", key="K", v="A")
    _drain(db)
    _write(db, TGT, "lot.csv", key="K", y="kept")          # not a shell after x goes
    target = _id(db, TGT, "K")
    ids, last = _deleted(db)
    real, losses = dbmod.stage_collapsed_event, []

    def staged(*a, **k):
        if lost and sys._getframe(1).f_code.co_name == "_withdraw_and_tell" and not losses:
            losses.append(1)
            raise OperationalError("UPDATE", {}, Exception("deadlock detected"))
        return real(*a, **k)
    monkeypatch.setattr(dbmod, "stage_collapsed_event", staged)

    _withdraw(db, ids, lost)

    x = db.query(models.CellSource).filter_by(table_name=TGT, row_id=target, column_name="x").count()
    if lost:
        assert x == 1 and _edits_of(db, TGT, last) == [], "rewound whole: the layer is back, nothing was told"
    else:
        assert x == 0 and ("EDIT", [target]) in _edits_of(db, TGT, last), "the row that lost a layer is told"


@pytest.mark.parametrize("lost", [False, True])
def test_a_lock_lost_at_a_shells_delete_is_raised_and_rewinds_whole(db, monkeypatch, lost):
    _write(db, SRC, "user", s="s1", key="K", v="A")
    _drain(db)
    ids, _last = _deleted(db)
    real, losses = crud.delete_rows_batch, []

    def deleting(*a, **k):
        if lost and not losses:
            losses.append(1)
            raise OperationalError("DELETE", {}, Exception("deadlock detected"))
        return real(*a, **k)
    monkeypatch.setattr(crud, "delete_rows_batch", deleting)

    _withdraw(db, ids, lost)

    rows = [r.row_id for r in db.query(models.DYNAMIC_TABLES[TGT])]
    if lost:
        assert len(rows) == 1 and cell_layer.shells(db, TGT, rows) == [], "rewound whole: the row and its layer are back"
    else:
        assert rows == [], "the shell went"
