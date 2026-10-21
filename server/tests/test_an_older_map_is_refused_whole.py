# -*- coding: utf-8 -*-
"""소유자 10-21 「기본 행단위 버전으로, 맵교체랑 섞이면 맵단위로 버전관리」 (총괄 c8cb6aca0): a map replace on a table
that declares `version_column` judges the map whole, before anything is deleted - the map's version is its rows'
greatest; a map not newer than the stored one is neither written nor deleted, in the purge form and the diff form.

  older       rev 2 stored, a rev 1 file (the same cells · one fewer)  -> the rev 2 map as it was, layers as many
  same        rev 2 again                                              -> refused, version_same
  newer       rev 1 stored, a rev 2 file of one cell                   -> the map is the file's: one row
  judged      stored c1 rev 5, a file c1 rev 3 · c2 rev 6              -> passed whole, its rows not asked again
  edges       a person's map · an emptied scope · no version · a stored map with no version
  doors       the watcher's file · the chain's scoped batch · the grid's replace_map push
"""
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "parsers"))

import directory_watcher                                                   # noqa: E402
from chain import ingestion_worker as worker                               # noqa: E402
from conftest import retire_dynamic_model                                  # noqa: E402
from database import crud, models, schemas                                 # noqa: E402
from database.database import Base                                         # noqa: E402
from directory_watcher import IngestionHandler                             # noqa: E402
from test_heavy_lane import FakeLane                                       # noqa: E402

PURGE, DIFF = "mver_purge", "mver_diff"
COLUMNS = {"cell_key": "string", "job": "string", "cell": "string", "v": "string", "rev": "number"}
BASE = {"business_key": "cell_key", "map_key_columns": ["job"], "version_column": "rev", "allow_replace_map": True,
        "column_types": COLUMNS, "display_columns": list(COLUMNS)}
ROWS = "mver_rows"                      # version_column and no map replace: row by row
TABLES = {PURGE: dict(BASE), DIFF: dict(BASE, composite_key_source=["job", "cell"], composite_key_separator="_"),
          ROWS: {"business_key": "k", "version_column": "rev", "column_types": {"k": "string", "v": "string",
                                                                                "rev": "number"}}}


@pytest.fixture()
def env(db_session):
    models.init_dynamic_models(TABLES)
    crud.TABLE_CONFIG.update(TABLES)
    Base.metadata.create_all(bind=db_session.get_bind())
    for name in TABLES:
        db_session.query(models.DYNAMIC_TABLES[name]).delete()
    for side in (models.AuditLog, models.CellSource, models.CellOverwrite):
        db_session.query(side).filter(side.table_name.in_(list(TABLES))).delete(synchronize_session=False)
    db_session.commit()
    yield db_session
    for name in TABLES:
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


def _row(table, cell, v, rev):
    row = {"job": "J", "cell": cell, "v": v}
    if rev is not None:
        row["rev"] = rev
    if table == PURGE:
        row["cell_key"] = "J|" + cell
    return row


def _push(db, table, cells, rev, v, source="f.csv", replace_map=True, scope=None):
    report = {}
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(
        updates=[schemas.GeneralUpdateItem(updates=_row(table, cell, v, rev), source_name=source, updated_by="t")
                 for cell in cells], replace_map=replace_map, scope=scope, silent=True), replace_report=report)
    return report


def _map(db, table):
    db.expire_all()
    return sorted((r.cell, r.v, r.rev) for r in db.query(models.DYNAMIC_TABLES[table]).all())


def _layers(db, table):
    return db.query(models.CellSource).filter(models.CellSource.table_name == table).count()


NEW = [("c1", "new", 2.0), ("c2", "new", 2.0)]


@pytest.mark.parametrize("table", [PURGE, DIFF])
@pytest.mark.parametrize("cells", [("c1", "c2"), ("c1",)])
def test_an_older_file_leaves_the_newer_map_as_it_was(env, table, cells):
    _push(env, table, ("c1", "c2"), 2, "new")
    layers = _layers(env, table)
    assert _map(env, table) == NEW and layers
    said = _push(env, table, cells, 1, "old")
    assert (said["mode"], said["reason"], said["deleted"]) == ("refused", crud.REASON_VERSION_OLDER, 0)
    assert _map(env, table) == NEW and _layers(env, table) == layers


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_the_same_version_again_is_refused(env, table):
    _push(env, table, ("c1", "c2"), 2, "new")
    said = _push(env, table, ("c1",), 2, "other")
    assert (said["mode"], said["reason"]) == ("refused", crud.REASON_VERSION_SAME)
    assert _map(env, table) == NEW


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_a_newer_file_replaces_the_map(env, table):
    _push(env, table, ("c1", "c2"), 1, "old")
    said = _push(env, table, ("c1",), 2, "new")
    assert said["mode"] in ("purge", "diff")
    assert _map(env, table) == [("c1", "new", 2.0)]


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_a_map_judged_whole_writes_its_rows_unasked(env, table):
    _push(env, table, ("c1",), 5, "stored")
    db = env
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=_row(table, "c1", "low", 3), source_name="f.csv", updated_by="t"),
        schemas.GeneralUpdateItem(updates=_row(table, "c2", "high", 6), source_name="f.csv", updated_by="t")],
        replace_map=True, silent=True))
    assert _map(env, table) == [("c1", "low", 3.0), ("c2", "high", 6.0)]


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_the_edges(env, table, caplog):
    _push(env, table, ("c1", "c2"), 2, "new")
    _push(env, table, ("c1",), 1, "person", source="user")                     # ㄱ a person's map: not asked
    assert _map(env, table) == [("c1", "person", 1.0)]
    _push(env, table, ("c1",), 3, "x")
    said = _push(env, table, (), None, "", scope={"job": "J"})                # ㄴ a scope emptied: not asked
    assert said["mode"] != "refused" and _map(env, table) == []
    _push(env, table, ("c1",), 4, "four")
    said = _push(env, table, ("c1", "c2"), None, "unversioned")                # ㄷ no version at all
    assert (said["mode"], said["reason"]) == ("refused", crud.REASON_VERSION_MISSING)
    crud.apply_batch_updates(env, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=_row(table, "c1", "part", None), source_name="f.csv", updated_by="t"),
        schemas.GeneralUpdateItem(updates=_row(table, "c2", "part", 5), source_name="f.csv", updated_by="t")],
        replace_map=True, silent=True))                                       # ㄷ some: the greatest decides
    # the row with no version is written with the map: a purge rewrites it whole, a diff keeps the cell it names not
    assert _map(env, table) == [("c1", "part", None if table == PURGE else 4.0), ("c2", "part", 5.0)]


@pytest.mark.parametrize("table", [PURGE, DIFF])
def test_a_stored_map_with_no_version_takes_the_first_versioned_one(env, table, caplog):
    _push(env, table, ("c1", "c2"), None, "before", replace_map=False)         # ㄹ written before the column
    assert _map(env, table) == [("c1", "before", None), ("c2", "before", None)]
    with caplog.at_level("INFO"):
        said = _push(env, table, ("c1",), 1, "first")
    assert said["mode"] != "refused" and _map(env, table) == [("c1", "first", 1.0)]
    assert any("row_version_absent" in r.getMessage() for r in caplog.records if "[VersionGate]" in r.getMessage())


# --- the doors -------------------------------------------------------------------------------------------------------

def test_the_chain_s_scoped_batch_is_judged(env):
    def write(rev, v, cells):
        ok, reason = worker.apply_chain_writes(
            env, "tx-%s" % v, {"name": "r_probe", "target_table": DIFF}, 0, {DIFF: {"r_probe"}}, {}, [],
            [(DIFF, [{"updates": _row(DIFF, cell, v, rev), "source_name": "chain_ingestion"} for cell in cells],
              {"job": "J"}, None)], {DIFF: ["r_probe"]}, [])
        assert ok, reason
    write(2, "new", ("c1", "c2"))
    write(1, "old", ("c1",))
    assert _map(env, DIFF) == NEW
    write(3, "three", ("c1",))
    assert _map(env, DIFF) == [("c1", "three", 3.0)]


def test_the_grid_s_replace_map_push_is_judged(env, client):
    def push(rev, v, cells):
        reply = client.put("/tables/%s/data/updates" % PURGE, json={
            "updates": [{"updates": _row(PURGE, cell, v, rev), "source_name": "map_editor"} for cell in cells],
            "replace_map": True, "transaction_id": "tx-%s" % v})
        assert reply.status_code == 200, reply.text
        return reply.json()
    push(2, "new", ("c1", "c2"))
    said = push(1, "old", ("c1",))
    assert _map(env, PURGE) == NEW, said


@pytest.fixture(name="watcher")
def fixture_watcher(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(TABLES)
    for name, info in TABLES.items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, dict(info))
    Base.metadata.create_all(bind=engine)
    models.ensure_ingestion_checkpoint_table(engine)
    monkeypatch.setattr(directory_watcher, "load_global_table_config", lambda: dict(TABLES))
    monkeypatch.setattr(directory_watcher, "SessionLocal", factory)
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH", str(tmp_path / "ingestion_settings.json"))
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10 ** 9)
    workspace = str(tmp_path / "ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"), default_table_name=DIFF,
                               heavy_lane=FakeLane())
    yield handler, workspace, factory
    engine.dispose()
    for name in TABLES:
        retire_dynamic_model(name)


def test_the_watcher_s_file_is_judged(watcher):
    handler, workspace, factory = watcher

    def read(name, text):
        path = os.path.join(workspace, "raws", name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        handler._handle_event(path)
        handler.heavy_lane.run_all()
        db = factory()
        try:
            return _map(db, DIFF)
        finally:
            db.close()
    assert read("new.csv", "job,cell,v,rev\nJ,c1,new,2\nJ,c2,new,2\n") == NEW
    assert read("old.csv", "job,cell,v,rev\nJ,c1,old,1\n") == NEW
    assert read("newer.csv", "job,cell,v,rev\nJ,c1,newer,3\n") == [("c1", "newer", 3.0)]
    # 총괄 10-21: the refused file says so on its row, in the write's words - not a bare SUCCESS
    assert _results(factory) == {
        "new.csv": ("SUCCESS", 2, 2, 0, None),
        "old.csv": ("SUCCESS", 1, 0, 1, "1 map refused: version_older"),
        "newer.csv": ("SUCCESS", 1, 0, 0, None)}


def _results(factory):
    """{file: (status, rows read, rows new, rows refused, reason)} - the file's completion record."""
    db = factory()
    try:
        return {log.filename: (log.status, log.rows_read, log.rows_new, log.rows_refused, log.reason)
                for log in db.query(models.FileIngestionLog).all()}
    finally:
        db.close()


def test_a_file_s_rows_the_row_gate_refused_are_said_on_its_row(watcher, tmp_path):
    _handler, _workspace, factory = watcher
    workspace = str(tmp_path / "rows_ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"), default_table_name=ROWS,
                               heavy_lane=FakeLane())
    for name, text in (("a.csv", "k,v,rev\nK1,a,2\nK2,a,2\n"), ("b.csv", "k,v,rev\nK1,b,1\nK2,b,2\nK3,b,1\n")):
        path = os.path.join(workspace, "raws", name)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        handler._handle_event(path)
        handler.heavy_lane.run_all()
    assert _results(factory)["b.csv"] == ("SUCCESS", 3, 1, 2,
                                         "1 row refused: version_older · 1 row refused: version_same"
                                         " · 1 row version_same_content_differs")
