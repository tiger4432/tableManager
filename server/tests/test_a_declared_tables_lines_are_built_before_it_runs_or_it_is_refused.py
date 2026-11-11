# -*- coding: utf-8 -*-
"""A declared table's line table is built before anything runs, or the table is refused (lead 11-11, owner «다 지어야
가동»). One judge, `lines.build_refusal`, for the build and the declaration save; every refusal at once,
`lines.LineTablesRefused`. The boot stops on it, the launcher's build starts nothing, a reload refuses the
declaration, a save is a 400 that writes nothing; a reload's new column lands on t and t__lines together or on
neither. sqlite."""
import json
import logging

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.pool import StaticPool

from conftest import retire_dynamic_model
from database import crud, lines, models

CFG = {"composite_key_source": ["k"], "column_types": {"k": "string", "a": "string"}}
LONG = "b63_" + "l" * 50                       # 54 bytes, one past lines.MAX_TABLE_NAME_BYTES
ORPHAN = "b63_orphan"
LONG_SAID = (LONG + ": line table not built - its name is 54 bytes; line tables need 53 or fewer - declare it under a "
             "shorter name (a non-ASCII character takes 3 bytes)")
ORPHAN_SAID = (ORPHAN + ": line table not built - b63_orphan__lines still holds the history of an earlier b63_orphan, "
               "which was dropped and made again - rename b63_orphan__lines or drop it (its history goes with it), "
               "then start or save again")


@pytest.fixture
def fresh(monkeypatch):
    monkeypatch.setattr(crud, "TABLE_CONFIG", dict(crud.TABLE_CONFIG))       # a reload clears and fills it
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(bind=engine)
    yield engine
    for name in (LONG, ORPHAN, "b63_reload_new", "b63_add"):
        if name in models.DYNAMIC_TABLES:
            retire_dynamic_model(name)
    engine.dispose()


def _declare(engine, *names, cfg=CFG):
    for name in names:
        crud.TABLE_CONFIG[name] = cfg
    models.init_dynamic_models({name: cfg for name in names})
    models.Base.metadata.create_all(bind=engine)


def _orphaned(engine):
    """ORPHAN with its lines built, then dropped and made again from its model - t__lines stays, won_by does not."""
    assert lines.ensure_declared(engine, [ORPHAN]) == {}
    table = models.DYNAMIC_TABLES[ORPHAN].__table__
    table.drop(bind=engine)
    table.create(bind=engine)


def test_a_boot_with_refused_tables_does_not_start_and_names_every_one(fresh):
    import main

    assert len(LONG.encode()) == lines.MAX_TABLE_NAME_BYTES + 1
    _declare(fresh, LONG, ORPHAN)
    _orphaned(fresh)
    with pytest.raises(lines.LineTablesRefused) as raised:
        main.bootstrap_database_schema(fresh)
    assert sorted(str(raised.value).splitlines()) == [LONG_SAID, ORPHAN_SAID]
    assert set(raised.value.refused) == {LONG, ORPHAN}


def test_the_launchers_build_says_every_refusal_and_starts_nothing(fresh, monkeypatch):
    _declare(fresh, LONG)
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: dict(crud.TABLE_CONFIG))
    said = []
    assert models.build_before_start(fresh, said.append) is False
    assert said == [LONG_SAID]


def test_the_launchers_build_makes_the_lines_own_tables_first(fresh, monkeypatch):
    """An upgrade: the launcher builds before the web server's create_all has made line_columns and the rest."""
    _declare(fresh, ORPHAN)
    with fresh.begin() as conn:
        for model in (lines.LineColumn, lines.AuditBatch, lines.LineSource):
            model.__table__.drop(bind=conn)
    assert not inspect(fresh).has_table("line_columns")                     # canary: the upgrade's state
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: dict(crud.TABLE_CONFIG))
    said = []
    assert models.build_before_start(fresh, said.append) is True, said
    assert inspect(fresh).has_table(lines.lines_relation(ORPHAN))


def test_a_built_table_declaring_a_framework_column_takes_no_ddl_at_the_next_start(fresh):
    """created_at declared in column_types is t__lines' own created_at, never a v_created_at cell."""
    cfg = {"composite_key_source": ["k"], "column_types": {**CFG["column_types"], "created_at": "datetime"}}
    _declare(fresh, ORPHAN, cfg=cfg)
    assert lines.ensure_declared(fresh, [ORPHAN]) == {}
    ddl = []
    listener = lambda conn, cursor, statement, *a: ddl.append(statement)          # noqa: E731
    event.listen(fresh, "before_cursor_execute", listener)
    try:
        assert lines.ensure_declared(fresh, [ORPHAN]) == {}
    finally:
        event.remove(fresh, "before_cursor_execute", listener)
    assert ddl, "canary: the second call read the catalogue"
    assert [s for s in ddl if s.lstrip().upper().startswith(("CREATE", "ALTER", "DROP"))] == []


def test_a_view_declared_without_kind_view_is_refused_by_name(fresh):
    with fresh.begin() as conn:
        conn.execute(text('CREATE VIEW "b63_view" AS SELECT 1 AS k, 2 AS a'))
    crud.TABLE_CONFIG["b63_view"] = CFG
    assert lines.ensure_declared(fresh, ["b63_view"]) == {"b63_view": "it is a view - declare it kind: view"}
    assert str(lines.LineTablesRefused({"b63_view": "it is a view - declare it kind: view"})) == \
        "b63_view: line table not built - it is a view - declare it kind: view"


def test_a_declared_table_the_database_lacks_is_refused_not_skipped(fresh):
    crud.TABLE_CONFIG["b63_absent"] = CFG
    assert lines.ensure_declared(fresh, ["b63_absent"]) == {
        "b63_absent": "it is declared but the database has no such table - start the server or save the declaration "
                      "again; both make it"}


@pytest.fixture
def save(tmp_path, monkeypatch):
    from database import config_watcher
    from ledger import admin

    path = tmp_path / "table_config.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    monkeypatch.setattr(admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(config_watcher, "changed", lambda *a, **k: None)

    def run(table, entry):
        return admin.save_table_config_raw(table, entry, admin.file_fingerprint(str(path)))

    run.path = path
    return run


def test_a_save_whose_lines_would_be_refused_is_400_and_writes_nothing(save):
    before = save.path.read_bytes()
    with pytest.raises(HTTPException) as raised:
        save(LONG, CFG)
    assert raised.value.status_code == 400
    assert raised.value.detail == {"ok": False, "code": "line_table_refused", "path": "tables." + LONG,
                                   "message": LONG_SAID}
    assert save.path.read_bytes() == before
    assert save("b63_short", CFG)["ok"] is True                      # canary: the same save under a short name lands


def test_the_build_and_the_save_ask_one_judge(fresh, save, monkeypatch):
    monkeypatch.setattr(lines, "build_refusal", lambda conn, t: "judged - by the one judge" if t == "probe" else None)
    crud.TABLE_CONFIG["probe"] = CFG
    assert lines.ensure_declared(fresh, ["probe"]) == {"probe": "judged - by the one judge"}
    with pytest.raises(HTTPException) as raised:
        save("probe", CFG)
    assert raised.value.detail["message"] == "probe: line table not built - judged - by the one judge"


def test_a_watcher_or_worker_reload_makes_the_table_and_builds_no_line_table(fresh, monkeypatch):
    """SYSTEM_RELOAD's refresh reads only (lead 11-11 ㄴ): the launcher and config_watcher's reload are the builders."""
    table = "b63_reload_new"
    declared = dict(crud.TABLE_CONFIG, **{table: CFG})
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: dict(declared))
    assert table in models.refresh_dynamic_models(fresh), "canary: the reload made t"
    assert not inspect(fresh).has_table(lines.lines_relation(table))
    assert "won_by" not in {c["name"] for c in inspect(fresh).get_columns(table)}


def test_a_column_add_refused_on_reload_leaves_both_tables_without_it(fresh, monkeypatch, caplog):
    from database.config_watcher import ConfigChangeHandler

    table = "b63_add"
    _declare(fresh, table)
    assert lines.ensure_declared(fresh, [table]) == {}
    wider = {"composite_key_source": ["k"], "column_types": {**CFG["column_types"], "c": "string"}}
    monkeypatch.setattr(crud, "load_table_config", lambda *a, **k: dict(crud.TABLE_CONFIG, **{table: wider}))
    refused_on = 'ALTER TABLE "%s" ADD COLUMN "%s"' % (lines.lines_relation(table), lines.value_column("c"))
    seen = []

    def refuse(conn, cursor, statement, *a):
        seen.append(statement)
        if statement.startswith(refused_on):
            raise RuntimeError("refused by the probe")

    event.listen(fresh, "before_cursor_execute", refuse)
    try:
        with caplog.at_level(logging.ERROR):
            ConfigChangeHandler(engine=fresh)._reload("table_config.json")
    finally:
        event.remove(fresh, "before_cursor_execute", refuse)
    assert any(s.startswith('ALTER TABLE "%s" ADD COLUMN "c"' % table) for s in seen), "canary: t's add was tried"
    assert any(s.startswith(refused_on) for s in seen), "canary: the line column's add was tried"
    said = [r.getMessage() for r in caplog.records if r.getMessage().startswith("[Reload] declaration refused - ")]
    assert len(said) == 1 and said[0].startswith("[Reload] declaration refused - %s: line table not built - " % table)
    assert said[0].endswith(" - restarting the server builds it again; if it still cannot be built, the boot stops "
                            "with that reason"), said
    assert "c" not in {c["name"] for c in inspect(fresh).get_columns(table)}
    assert lines.value_column("c") not in {c["name"] for c in inspect(fresh).get_columns(lines.lines_relation(table))}
