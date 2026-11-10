"""add_to_cache=False 경로에서 감사 로그가 DB(audit_logs)에도 적재되는지 검증하는 회귀 테스트.

과거 버그: create_audit_log(add_to_cache=False)는 인메모리 캐시 추가뿐 아니라
DB persist(db.add)도 생략하므로, 호출자가 bulk_insert_audit_logs로 직접 적재하지
않으면 로그가 웹서버 캐시에만 남고 서버 재시작 시 소실되었다.
"""
from database import models, crud


def _db_logs(db, table_name, column_name=None):
    q = db.query(models.AuditLog).filter(models.AuditLog.table_name == table_name)
    if column_name:
        q = q.filter(models.AuditLog.column_name == column_name)
    return q.all()


def test_delete_rows_batch_persists_audit_logs(db_session):
    table_model = models.DYNAMIC_TABLES["raw_table_1"]
    rows = db_session.query(table_model).limit(3).all()
    row_ids = [r.row_id for r in rows]

    deleted = crud.delete_rows_batch(db_session, "raw_table_1", row_ids, user_name="tester")
    assert deleted == 3

    from sqlalchemy import select

    from database import lines
    ln = lines.shape(db_session, "raw_table_1", crud.TABLE_CONFIG["raw_table_1"])["lines"]     # a «deleted» line a row
    said = db_session.execute(select(ln.c.row_id, ln.c.written_by).where(ln.c.line_kind == "deleted")).all()
    assert sorted(said) == sorted((r, "tester") for r in row_ids)


def test_create_empty_rows_batch_persists_audit_logs(db_session):
    """A «created» line a row (C 11-11), and the notification's entries from the write's own answer."""
    from sqlalchemy import select

    from database import lines
    entries = []
    new_rows = crud.create_empty_rows_batch(db_session, "inventory_master", 2, user_name="tester",
                                            created_lines=entries)
    assert len(new_rows) == 2

    ln = lines.shape(db_session, "inventory_master", crud.TABLE_CONFIG["inventory_master"])["lines"]
    said = db_session.execute(select(ln.c.row_id, ln.c.written_by).where(ln.c.line_kind == "created")).all()
    assert sorted(said) == sorted((r.row_id, "tester") for r in new_rows)
    assert sorted((e["row_id"], e["column_name"], e["new_value"], e["updated_by"]) for e in entries) == sorted(
        (r.row_id, crud.ROW_CREATION_COLUMN, "row created", "tester") for r in new_rows)


def test_delete_cell_source_batch_persists_audit_logs(db_session):
    table_model = models.DYNAMIC_TABLES["raw_table_1"]
    row = db_session.query(table_model).first()

    crud.delete_cell_source_batch(
        db_session, "raw_table_1",
        [{"row_id": row.row_id, "column_name": "EQP_ID"}],
        "system",
    )

    logs = _db_logs(db_session, "raw_table_1", "EQP_ID")
    assert any(l.row_id == row.row_id and l.source_name.startswith("delete_source:") for l in logs)
