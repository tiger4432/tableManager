# -*- coding: utf-8 -*-
"""A funnel write in the process that holds the history list stands on it at once - its transaction's group on top,
the table with the rows it changed - not at the next read's catch-up (lead 11-11 ㄱ: `audit_cache.add_changed` with
write_lines' `audit` after the commit). A process whose list is not loaded (a worker) is left alone."""
import pytest

from admin import audit_cache
from database import crud, lines, models, schemas
from database.database import Base

TABLE = "wl_hist_now"
CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}


@pytest.fixture(name="db")
def fixture_db(db_session, monkeypatch):
    models.init_dynamic_models({TABLE: CFG})
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, CFG)
    Base.metadata.create_all(bind=db_session.get_bind())
    lines.ensure_line_table(db_session, TABLE, CFG)
    db_session.commit()
    audit_cache.audit_cache.__init__()
    try:
        yield db_session
    finally:
        audit_cache.audit_cache.__init__()


def _write(db, *keys):
    crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=k, updates={"k": k, "a": "x"}, source_name="f1.csv", updated_by="loader") for k in keys]))
    return db.query(lines.AuditBatch).filter(lines.AuditBatch.table_name == TABLE).order_by(
        lines.AuditBatch.id.desc()).first().transaction_id


def test_a_write_stands_on_the_loaded_list_at_once(db):
    audit_cache.audit_cache.load_initial(db)
    assert audit_cache.audit_cache.is_loaded
    tx = _write(db, "K1", "K2")
    top = audit_cache.audit_cache.groups[0]
    assert top["transaction_id"] == audit_cache.group_of(tx), top
    assert top["changed"][TABLE] == 2 and top["tables"][TABLE]["written_by"] == ["loader"], top


def test_a_list_not_loaded_is_left_alone(db):
    _write(db, "K3")
    assert not audit_cache.audit_cache.is_loaded and audit_cache.audit_cache.groups == []
