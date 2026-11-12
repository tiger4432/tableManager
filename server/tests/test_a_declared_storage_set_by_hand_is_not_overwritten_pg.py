"""Lead 11-09 ⓑ: a table's declared storage (a model's `info["storage"]`, a table_config.json entry's "storage", the
ledger partitions') beside what the table holds, and the record on the table's comment of what the product set last
(`maintenance_line.STORAGE_RECORD`).

  owed      the table holds nothing                     -> set and recorded
  held      as declared, no record                      -> recorded, no ALTER
  follows   held = the record, the declaration changed  -> set again
  differs   set by hand                                 -> not overwritten, until «Apply declared» (take=) names it
  refused   a parameter PostgreSQL has not / a value its kind does not take -> nothing set; a save refused
"""
import json
import logging

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.pg
T = "storage_probe_t"


@pytest.fixture(name="line")
def fixture_line(pg_engine, monkeypatch):
    from database import crud
    from database.database import Base
    from ledger import schema
    from runtime import maintenance_line

    monkeypatch.setattr(schema, "world_listing", lambda: {"worlds": [], "operating": schema.DEFAULT_WORLD})
    for table in Base.metadata.sorted_tables:                   # the models' own storage is the other test's
        if table.info.get("storage"):
            monkeypatch.setitem(table.info, "storage", {})
    entry = {"column_types": {"a": "string"}, "storage": {"fillfactor": 80}}
    monkeypatch.setattr(crud, "TABLE_CONFIG", {T: entry})
    import ingestion.settings
    monkeypatch.setattr(ingestion.settings, "read_ingestion_settings",   # the product's default for a declared
                        lambda path=None: {"table_autovacuum_threshold": None})   # table is the other test's
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))
        conn.execute(text('CREATE TABLE "%s" (a text)' % T))
        conn.execute(text("COMMENT ON TABLE \"%s\" IS 'made by the test'" % T))
    yield entry, lambda **kw: maintenance_line.apply_table_storage(sessionmaker(bind=pg_engine), **kw)
    with pg_engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS "%s"' % T))


def _held(engine):
    with engine.connect() as conn:
        row = conn.execute(text("SELECT c.reloptions, obj_description(c.oid, 'pg_class') FROM pg_class c"
                                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                                " WHERE c.relname = :t AND n.nspname = current_schema()"), {"t": T}).first()
    return dict(option.split("=", 1) for option in row[0] or ()), row[1]


def _states(engine):
    from runtime import maintenance_line

    db = sessionmaker(bind=engine)()
    try:
        return {row["parameter"]: row["state"] for row in maintenance_line.storage_states(db) if row["table"] == T}
    finally:
        db.close()


def _record(comment):
    from runtime import maintenance_line

    line = comment.splitlines()[-1]
    assert line.startswith(maintenance_line.STORAGE_RECORD), comment
    return json.loads(line[len(maintenance_line.STORAGE_RECORD):])


def test_owed_is_set_and_recorded_and_the_comment_keeps_its_other_lines(line, pg_engine):
    _entry, apply = line
    assert _states(pg_engine) == {"fillfactor": "owed"}
    assert apply() == {T: "set"}
    options, comment = _held(pg_engine)
    assert options == {"fillfactor": "80"}
    assert comment.splitlines()[0] == "made by the test"
    said = _record(comment)
    assert said["set"] == {"fillfactor": "80"} and said["by"] == "product" and said["at"]
    assert apply() == {} and _states(pg_engine) == {"fillfactor": "held"}


def test_a_held_value_without_a_record_is_recorded_without_an_alter(line, pg_engine):
    _entry, apply = line
    with pg_engine.begin() as conn:
        conn.execute(text('ALTER TABLE "%s" SET (fillfactor = 80)' % T))
    assert _states(pg_engine) == {"fillfactor": "held"}
    assert apply() == {T: "recorded"}
    assert _record(_held(pg_engine)[1])["set"] == {"fillfactor": "80"}
    assert apply() == {}


def test_the_products_value_follows_a_changed_declaration(line, pg_engine):
    entry, apply = line
    assert apply() == {T: "set"}
    entry["storage"] = {"fillfactor": 90, "vacuum_truncate": False}
    assert _states(pg_engine) == {"fillfactor": "follows", "vacuum_truncate": "owed"}
    assert apply() == {T: "set"}
    assert _held(pg_engine)[0] == {"fillfactor": "90", "vacuum_truncate": "false"}
    assert _states(pg_engine) == {"fillfactor": "held", "vacuum_truncate": "held"}


def test_a_value_set_by_hand_is_not_overwritten_until_apply_declared(line, pg_engine, caplog):
    entry, apply = line
    assert apply() == {T: "set"}
    with pg_engine.begin() as conn:
        conn.execute(text('ALTER TABLE "%s" SET (fillfactor = 60)' % T))
    entry["storage"] = {"fillfactor": 90}
    assert _states(pg_engine) == {"fillfactor": "differs"}
    assert apply() == {T: "differs"}
    assert _held(pg_engine)[0] == {"fillfactor": "60"}, "set by hand: left"
    caplog.set_level(logging.INFO)
    assert apply(take=T, by="kim") == {T: "set"}
    options, comment = _held(pg_engine)
    assert options == {"fillfactor": "90"} and _record(comment)["by"] == "kim"
    assert any("%s storage set as declared by kim: fillfactor = 90 (held before: fillfactor 60)" % T in r.getMessage()
               for r in caplog.records), [r.getMessage() for r in caplog.records]
    assert apply() == {}


def test_a_refused_declaration_sets_nothing(line, pg_engine):
    entry, apply = line
    entry["storage"] = {"fillfactor": 80, "fill_factor": 70}
    assert apply() == {T: "refused"}
    assert _held(pg_engine)[0] == {}
    assert _states(pg_engine) == {None: "refused"}


def test_the_refusal_names_the_cell():
    from runtime import maintenance_line as m

    assert m.storage_refusal("t", {}) is None
    assert m.storage_refusal("t", {"storage": [1]})[0] == "tables.t.storage"
    assert m.storage_refusal("t", {"storage": {"fill_factor": 70}}) == (
        "tables.t.storage.fill_factor", "fill_factor is not a PostgreSQL table storage parameter")
    assert m.storage_refusal("t", {"storage": {"fillfactor": "70"}}) == (
        "tables.t.storage.fillfactor", "fillfactor takes a number")
    assert m.storage_refusal("t", {"storage": {"vacuum_truncate": "maybe"}})[1] == "vacuum_truncate takes true or false"
    assert m.storage_refusal("t", {"storage": {"vacuum_index_cleanup": "never"}})[1] == (
        "vacuum_index_cleanup takes auto or on or off")
    assert m.storage_refusal("t", {"kind": "view", "storage": {"fillfactor": 70}})[1] == "t is a view - a view has no storage"
    assert m.storage_refusal("t", {"storage": {"fillfactor": 70, "vacuum_truncate": "false",
                                               "vacuum_index_cleanup": "OFF"}}) is None


def test_a_save_with_a_refused_storage_is_refused(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from database import config_watcher
    from ledger import admin

    path = tmp_path / "table_config.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(admin, "table_config_path", lambda: str(path))
    monkeypatch.setattr(admin.config_backup, "backup_dir_for", lambda p: str(tmp_path / "backup"))
    monkeypatch.setattr(config_watcher, "changed", lambda *a, **k: None)
    with pytest.raises(HTTPException) as refused:
        admin.save_table_config_raw("probe", {"business_key": "pk", "storage": {"fillfactor": "high"}},
                                    admin.file_fingerprint(str(path)))
    assert refused.value.detail["code"] == "storage_refused", refused.value.detail
    assert json.loads(path.read_text(encoding="utf-8")) == {}, "nothing written"
