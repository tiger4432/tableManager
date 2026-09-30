# -*- coding: utf-8 -*-
"""총괄 791c0f45e 3 — 설정엔 있는데 그 프로세스의 모델이 모르는 칸(Reload 실패 · 설정과 모델 사이 ·
모델 짓기가 건너뛰는 이름)은 쓰기 문이 층만 쓰고 표 값은 조용히 안 썼다(0a7c46615 ㉠).
이제 층도 표도 안 쓰고 «버린 칸»으로 센다 — 사유 unmapped_column. 파일 줄에도 그 사유가 뜬다.
"""
import os
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from conftest import retire_dynamic_model                  # noqa: E402
from database.database import Base                         # noqa: E402
from database import crud, models, schemas                 # noqa: E402

T = "unmapped_probe"
HELD = {"business_key": "k", "column_types": {"k": "string", "s": "string"}}


@pytest.fixture(name="session")
def fixture_session(pg_engine):
    saved = dict(crud.TABLE_CONFIG)
    retire_dynamic_model(T)
    models.init_dynamic_models({T: HELD})
    crud.TABLE_CONFIG[T] = HELD
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    with pg_engine.begin() as conn:                       # the column exists in the table
        for column in ("t_late", "graph_synced_at"):
            conn.execute(text('ALTER TABLE "%s" ADD COLUMN %s TIMESTAMPTZ' % (T, column)))
    session = sessionmaker(bind=pg_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})


@pytest.mark.pg
@pytest.mark.parametrize("column", [
    "t_late",            # the config moved ahead of the model (a reload that failed half-way)
    "graph_synced_at",   # a declared name the model build skips on every start (FRAMEWORK_COLUMNS)
])
def test_a_column_the_model_does_not_hold_is_dropped_by_name(session, column):
    crud.TABLE_CONFIG[T] = {"business_key": "k", "column_types": dict(
        HELD["column_types"], **{column: "datetime"})}
    if column == "graph_synced_at":
        models.init_dynamic_models({T: crud.TABLE_CONFIG[T]})     # the build skips it
    assert column not in models.DYNAMIC_TABLES[T].__table__.columns
    drop = {}
    crud.apply_batch_updates(session, T, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val="u1", updates={
            "k": "u1", "s": "kept", column: "2026-09-29 10:00:00"},
            source_name="unmapped_probe.csv", updated_by="t")], silent=True), None, drop)
    table = session.execute(text('SELECT s, %s FROM "%s"' % (column, T))).one()
    layers = dict(session.execute(text(
        "SELECT column_name, value FROM cell_sources WHERE table_name = :t"), {"t": T}).all())

    assert tuple(table) == ("kept", None) and set(layers) == {"k", "s"}, "no layer, no value"
    assert drop["by_reason"] == {crud.DROP_UNMAPPED_COLUMN: 1}
    assert drop["by_column"] == {column: 1}


@pytest.mark.pg
def test_the_file_line_names_the_column_the_model_does_not_hold(session, pg_engine,
                                                                 monkeypatch):
    from parsers import directory_watcher as dw

    crud.TABLE_CONFIG[T] = {"business_key": "k", "column_types": dict(
        HELD["column_types"], t_late="datetime")}
    monkeypatch.setattr(dw, "SessionLocal", sessionmaker(bind=pg_engine))
    monkeypatch.setattr(dw.heartbeat, "beat", lambda *a, **k: None)
    handler = dw.IngestionHandler.__new__(dw.IngestionHandler)
    handler.scripts_path = ""
    handler.on_progress_callback = None
    handler.on_refresh_callback = None
    rows = [{"k": "f%d" % i, "s": "v", "t_late": "2026-09-29 10:00:00"} for i in range(3)]

    sentence = handler._send_to_upsert(rows, uploader="t", filename="unmapped.csv",
                                       t_name=T, table_info=crud.TABLE_CONFIG[T])

    assert "t_late=3" in sentence and crud.DROP_UNMAPPED_COLUMN in sentence, sentence
    assert sentence.startswith("Next: reload or restart"), sentence      # d4a949a8c ③

    # a file whose every column the model does not hold wrote nothing: the same refusal a file
    # of undeclared columns gets (d4a949a8c ③)
    with pytest.raises(crud.NothingWritten) as refused:
        handler._send_to_upsert([{"t_late": "2026-09-29 10:00:00"}], uploader="t",
                                filename="only_unmapped.csv", t_name=T,
                                table_info=crud.TABLE_CONFIG[T])
    assert refused.value.columns == {crud.DROP_UNMAPPED_COLUMN: ["t_late"]}, refused.value.columns
    assert session.execute(text('SELECT count(*) FROM "%s" WHERE t_late IS NULL' % T)
                           ).scalar() == 3
