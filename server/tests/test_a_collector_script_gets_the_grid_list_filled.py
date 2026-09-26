# -*- coding: utf-8 -*-
"""`{{LIST:table.column}}` in a collector script is filled with the grid's values of that
column, as a quoted SQL list (소유자 2026-09-26 「part 리스트를 메인 그리드에서 관리하고 오토
업데이트가 그걸 참조」 · 「ㄱ 으로 해 일단」).

🔴 THE SAME FILL SEAT AS THE WINDOW, THE SAME VALUE DOOR AS THE GRID. The list is read through
`value_suggest.suggest_values` - blank values out, each value once, in value order - and a
list that is empty, cut at the cap or unreadable REFUSES the run by name: a partial list
would quietly drop parts from the query.
"""
import csv
import io
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import collector_markers as cm                                             # noqa: E402
import run_auto_update as rau                                              # noqa: E402
from conftest import retire_dynamic_model                                  # noqa: E402
from database import crud, models, schemas                                 # noqa: E402
from database.database import Base                                         # noqa: E402

TABLE, SOURCE = "list_marker_parts", "list_probe_tbl"
MARKER = "{{LIST:list_marker_parts.part_id}}"
PARTS = ["P2", "O'Brien", "P1", "P2", "", None]
LITERAL = "'O''Brien','P1','P2'"


@pytest.fixture(name="grid")
def fixture_grid(monkeypatch):
    """A grid table on its own in-memory database; returns (session factory, writer)."""
    cfg = {"business_key": "k", "column_types": {"k": "string", "part_id": "string"}}
    monkeypatch.setitem(crud.TABLE_CONFIG, TABLE, cfg)
    models.init_dynamic_models({TABLE: cfg})
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)          # the write path also keeps its audit rows
    factory = sessionmaker(bind=engine)

    def write(values):
        db = factory()
        try:
            crud.apply_batch_updates(db, TABLE, schemas.GeneralUpdateBatch(updates=[
                schemas.GeneralUpdateItem(updates={"k": "k%d" % i, "part_id": value},
                                          source_name="user", updated_by="test")
                for i, value in enumerate(values)]))
        finally:
            db.close()
    yield factory, write
    engine.dispose()
    retire_dynamic_model(TABLE)


def _collector(tmp_path, body, factory, name="probe.py"):
    au_dir = os.path.join(str(tmp_path), "ingestion_workspace", SOURCE, "auto_update")
    os.makedirs(au_dir, exist_ok=True)
    path = os.path.join(au_dir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# schedule: * * * * *\n" + body)
    return rau.GenericScriptRunnerCollector(
        table_name=SOURCE, script_path=path, cron_expression="* * * * *",
        filename_prefix="list_probe", server_dir=str(tmp_path), session_factory=factory)


def _raw(collector):
    files = sorted(os.listdir(collector.target_dir))
    assert len(files) == 1, files
    with open(os.path.join(collector.target_dir, files[0]), encoding="utf-8") as f:
        return f.read()


#: The script writes this file FIRST, so its absence says the script never started.
STARTED = 'open(__file__ + ".started", "w").close()\n'


def _refused(tmp_path, factory):
    collector = _collector(tmp_path, STARTED + 'out = [{"parts": "%s"}]\n' % MARKER, factory)
    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))
    scheduler.execute_collector(collector)
    assert collector.last_status == "FAIL"
    assert not os.listdir(collector.target_dir), "a refused run writes no file"
    assert not os.path.exists(collector.script_path + ".started"), "the script never started"
    assert "Traceback" not in collector.last_error, "the tab shows the sentence, not a traceback"
    return collector.last_error


def test_the_exec_path_gets_the_grid_list_quoted(tmp_path, grid):
    factory, write = grid
    write(PARTS)
    collector = _collector(tmp_path, 'out = [{"parts": "%s"}]\n' % MARKER, factory)

    collector.execute()

    assert list(csv.DictReader(io.StringIO(_raw(collector)))) == [{"parts": LITERAL}]


def test_the_stdout_path_gets_the_same_list(tmp_path, grid):
    factory, write = grid
    write(PARTS)
    collector = _collector(tmp_path, 'print("parts")\nprint("%s")\n' % MARKER, factory)

    collector.execute()

    assert _raw(collector).splitlines() == ["parts", LITERAL]


def test_an_empty_list_refuses_the_run_by_name(tmp_path, grid):
    factory, write = grid
    write(["", None])

    said = _refused(tmp_path, factory)

    assert said == "%s has no value in '%s'. The run did not start." % (MARKER, TABLE)


def test_a_list_longer_than_the_cap_refuses_rather_than_cutting(tmp_path, grid):
    factory, write = grid
    write(["P%05d" % i for i in range(cm.LIST_MARKER_CAP + 1)])

    said = _refused(tmp_path, factory)

    assert "has more than %d values" % cm.LIST_MARKER_CAP in said


def test_a_list_of_exactly_the_cap_is_filled(tmp_path, grid):
    factory, write = grid
    write(["P%05d" % i for i in range(cm.LIST_MARKER_CAP)])
    collector = _collector(tmp_path, 'out = [{"parts": "%s"}]\n' % MARKER, factory)

    collector.execute()

    [row] = list(csv.DictReader(io.StringIO(_raw(collector))))
    assert row["parts"].count(",") == cm.LIST_MARKER_CAP - 1


def test_an_undeclared_column_refuses_by_name(tmp_path, grid):
    factory, _write = grid
    collector = _collector(tmp_path, 'out = [{"p": "{{LIST:list_marker_parts.nope}}"}]\n',
                           factory)
    scheduler = rau.MultiDiscoveryScheduler(server_dir=str(tmp_path))

    scheduler.execute_collector(collector)

    assert collector.last_status == "FAIL"
    assert collector.last_error.startswith("{{LIST:list_marker_parts.nope}} is not a column")


def test_an_unreadable_list_refuses_by_name(tmp_path, grid, monkeypatch):
    import value_suggest
    factory, write = grid
    write(PARTS)
    monkeypatch.setattr(value_suggest, "suggest_values", lambda *a, **k: {
        "values": [], "truncated": False, "unavailable_reason": "statement timeout"})

    said = _refused(tmp_path, factory)

    assert said == "%s could not be read (statement timeout). The run did not start." % MARKER


def test_the_scheduler_builds_the_models_the_list_reads_through(monkeypatch):
    cfg = {"business_key": "k", "column_types": {"k": "string", "part_id": "string"}}
    monkeypatch.setattr(crud, "TABLE_CONFIG", {TABLE: cfg})
    try:
        rau.init_models()
        assert TABLE in models.DYNAMIC_TABLES
    finally:
        retire_dynamic_model(TABLE)
