# -*- coding: utf-8 -*-
"""총괄 791c0f45e 2 — 기존 표에 칸을 더하고 재기동 없이 Reload 하면 그리드 목록이 그 칸을 모든 행에서 비웠다
(74101b158). 표와 층엔 값이 있었다 — 스왑 «전»에 컴파일된 질의 모양이 엔진 캐시에서 새 칸 없는 SELECT 로
나갔다. 칸을 더한 핫스왑은 그 엔진의 컴파일 캐시를 비운다. 칸이 안 바뀐 Reload 는 비우지 않는다.
"""
import json
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

T = "reload_adds_a_column"
OLD = {"business_key": "k", "column_types": {"k": "string", "s": "string"}}
NEW = {"business_key": "k", "column_types": {"k": "string", "s": "string", "d": "datetime"}}


@pytest.fixture(name="table")
def fixture_table(pg_engine, tmp_path, monkeypatch):
    """The table as a running process knows it BEFORE the column: its model, its config file."""
    saved = dict(crud.TABLE_CONFIG)
    path = tmp_path / "table_config.json"
    path.write_text(json.dumps({T: OLD}), encoding="utf-8")
    monkeypatch.setattr(crud, "CONFIG_PATH", str(path))
    retire_dynamic_model(T)
    models.init_dynamic_models({T: OLD})
    crud.TABLE_CONFIG[T] = OLD
    # The reloads walk EVERY registered model (create what is missing, sync columns); in the
    # scratch schema that would build lookalikes of relations other proofs create by their
    # own DDL (S-260) - so this process sees this table alone while it runs. The registry
    # comes back before `retire_dynamic_model` takes the table out of it (S-191).
    monkeypatch.setattr(models, "DYNAMIC_TABLES", {T: models.DYNAMIC_TABLES[T]})
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})
    Base.metadata.create_all(bind=pg_engine, tables=[models.DYNAMIC_TABLES[T].__table__])
    try:
        yield path
    finally:
        monkeypatch.undo()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved)
        retire_dynamic_model(T)
        with pg_engine.begin() as conn:
            conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
            conn.execute(text("DELETE FROM cell_sources WHERE table_name = :t"), {"t": T})


def _write(session, key, cells):
    crud.apply_batch_updates(session, T, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(business_key_val=key, updates=dict({"k": key}, **cells),
                                  source_name="reload_probe.csv", updated_by="t")], silent=True))


def _grid(session, ids):
    """The grid page's own row query and merge (main.get_table_data's last two steps)."""
    import main
    model = models.DYNAMIC_TABLES[T]
    rows = session.query(model).filter(model.row_id.in_(ids)).all()
    cols = [c for c in crud.TABLE_CONFIG[T]["column_types"]]
    return {r["data"]["k"]["value"]: (r["data"].get("d") or {}).get("value")
            for r in main.fetch_and_merge_metadata(session, T, rows, cols,
                                                   include_sources=False)}


def _reload(seat, path, pg_engine):
    if seat == "server_file_watch":
        from database.config_watcher import ConfigChangeHandler
        ConfigChangeHandler(engine=pg_engine)._reload(str(path))
    else:
        # A worker's Reload: the server's watch already added the physical column.
        with pg_engine.begin() as conn:
            conn.execute(text('ALTER TABLE "%s" ADD COLUMN d TIMESTAMPTZ' % T))
        models.refresh_dynamic_models(pg_engine)


@pytest.mark.pg
@pytest.mark.parametrize("seat", ["server_file_watch", "worker_reload"])
def test_a_column_added_by_reload_is_read_without_a_restart(table, pg_engine, seat, monkeypatch):
    from ledger import admin
    Session = sessionmaker(bind=pg_engine)
    cleared = []
    monkeypatch.setattr(pg_engine, "clear_compiled_cache",
                        lambda real=pg_engine.clear_compiled_cache: (cleared.append(1), real())[1])
    with Session() as session:
        _write(session, "r1", {"s": "a"})
        ids = [r.row_id for r in session.query(models.DYNAMIC_TABLES[T]).all()]
        assert _grid(session, ids) == {"r1": None}           # the page shape, compiled BEFORE

    admin.save_table_config_raw(T, NEW, admin.file_fingerprint(str(table)))
    _reload(seat, table, pg_engine)
    with Session() as session:
        _write(session, "r1", {"d": "2026-09-30 12:00:00+09:00"})
    with Session() as session:
        stored = session.execute(text('SELECT d FROM "%s"' % T)).scalar()
        shown = _grid(session, ids)

    assert stored is not None, "the value is in the table"
    assert shown == {"r1": stored}, "the grid page shows it without a restart"
    assert cleared == [1]


@pytest.mark.pg
def test_a_reload_that_adds_no_column_keeps_the_cache(table, pg_engine, monkeypatch):
    cleared = []
    monkeypatch.setattr(pg_engine, "clear_compiled_cache", lambda: cleared.append(1))
    models.refresh_dynamic_models(pg_engine)

    assert cleared == []
