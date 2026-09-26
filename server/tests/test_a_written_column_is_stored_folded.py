# -*- coding: utf-8 -*-
"""A `write` column is stored folded through every write door - notation stage two (총괄
5ee9d3bd1 · 47aba5d44 · a7d2e90ec · 3eb161a9c).

The one seat that changes a value is the write funnel's head, once per call and ahead of its
retry loop; the chain key gate judges with the same function and forwards the item as it came.
A value the fold changed leaves one audit line when its cell is written. A row stored under the
raw spelling is found by it and re-keyed. The time rule's left-as-written values are named once
per file on the FILE line.
"""
import json
import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
for path in (server_dir, os.path.join(server_dir, "parsers")):
    if path not in sys.path:
        sys.path.insert(0, path)

import directory_watcher                                                   # noqa: E402
import notation_norm as nn                                                 # noqa: E402
from chain import ingestion_worker as worker                               # noqa: E402
from chain import key_gate                                                 # noqa: E402
from chain import replay                                                   # noqa: E402
from conftest import retire_dynamic_model                                  # noqa: E402
from database import crud, models, schemas                                 # noqa: E402
from database.database import Base                                         # noqa: E402
from directory_watcher import IngestionHandler                             # noqa: E402
from product_tables import NOTATION_ALIAS_TABLE, PRODUCT_TABLES            # noqa: E402
from test_heavy_lane import FakeLane                                       # noqa: E402

PLAIN, COMP = "notw_plain", "notw_comp"
TABLES = {
    PLAIN: {"business_key": "k",
            "column_types": {"k": "string", "v": "string", "seen": "string",
                             "note": "string"}},
    COMP: {"business_key": "row_key", "composite_key_source": ["lot", "wafer"],
           "composite_key_separator": "_", "map_key_columns": ["lot"],
           "column_types": {"row_key": "string", "lot": "string", "wafer": "string",
                            "x": "string"}},
}
#: 총괄 451ac4f75's example as written: 'wafer.1' -> 'wafer-01'.
OWNER = {"join": "-", "pad_last_number": 2}
TIME = {"time": {"from": ["%Y/%m/%d %H:%M:%S"]}}
DECLARED = {PLAIN: {"k": {"write": True, "rules": OWNER}, "v": {"write": True, "rules": OWNER},
                    "seen": {"write": True, "rules": TIME}, "note": {"rules": OWNER}},
            COMP: {"lot": {"write": True, "rules": {"join": "-"}},
                   "wafer": {"write": True, "rules": OWNER}}}


def _declare(tmp_path, monkeypatch, columns):
    path = tmp_path / "notation_rules.json"
    path.write_text(json.dumps({"columns": columns}), encoding="utf-8")
    monkeypatch.setattr(nn, "NOTATION_RULES_PATH", str(path))
    nn.reset_cache()


def _tables():
    return dict(TABLES, **{NOTATION_ALIAS_TABLE: PRODUCT_TABLES[NOTATION_ALIAS_TABLE]})


@pytest.fixture()
def env(db_session, tmp_path, monkeypatch):
    models.init_dynamic_models(_tables())
    crud.TABLE_CONFIG.update(_tables())
    Base.metadata.create_all(bind=db_session.get_bind())
    # The suite's sqlite outlives a test: start from empty tables and side tables.
    for name in _tables():
        db_session.query(models.DYNAMIC_TABLES[name]).delete()
    for side in (models.AuditLog, models.CellSource, models.CellOverwrite):
        db_session.query(side).filter(side.table_name.in_(list(_tables()))).delete(
            synchronize_session=False)
    db_session.commit()
    _declare(tmp_path, monkeypatch, DECLARED)
    yield db_session
    nn.reset_cache()
    for name in _tables():
        retire_dynamic_model(name)
        crud.TABLE_CONFIG.pop(name, None)


def _write(db, table, rows, source="f01.csv", report=None, **batch):
    crud.apply_batch_updates(db, table, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=dict(r), source_name=source, updated_by="t",
                                  business_key_val=r.get("k") if table == PLAIN else None)
        for r in rows], silent=True, **batch), notation_report=report)


def _rows(db, table):
    return db.query(models.DYNAMIC_TABLES[table]).all()


def _fold_lines(db, table, column):
    return sorted(((a.old_value, a.new_value, a.source_name) for a in db.query(models.AuditLog)
                   .filter(models.AuditLog.table_name == table,
                           models.AuditLog.column_name == column)), key=repr)


def _aliases(db, rows):
    crud.apply_batch_updates(db, NOTATION_ALIAS_TABLE, schemas.GeneralUpdateBatch(updates=[
        schemas.GeneralUpdateItem(updates=r, source_name="user", updated_by="t") for r in rows],
        silent=True))


# --- the funnel: what is stored, and the line it leaves -----------------------------------------

def test_a_write_column_is_stored_folded_and_says_what_arrived(env):
    _write(env, PLAIN, [{"k": "k.1", "v": "wafer.1", "note": "wafer.1"}])
    (row,) = _rows(env, PLAIN)
    assert (row.k, row.v, row.note, row.business_key_val) == ("k-01", "wafer-01", "wafer.1", "k-01")
    assert _fold_lines(env, PLAIN, "v") == [("wafer.1", "wafer-01", "f01.csv")]
    assert _fold_lines(env, PLAIN, "k") == [("k.1", "k-01", "f01.csv")]
    assert _fold_lines(env, PLAIN, "note") == [], "a compare-only column is stored as it came"


def test_an_alias_comes_first_and_a_blank_canonical_is_no_alias(env):
    _aliases(env, [{"table_name": PLAIN, "column_name": "v", "written": "WF#1",
                    "canonical": "wafer.1"},
                   {"table_name": PLAIN, "column_name": "k", "written": "Y", "canonical": "  "}])
    assert nn.aliases_by_column(env) == {(PLAIN, "v"): {"WF#1": "wafer.1"}}
    _write(env, PLAIN, [{"k": "K-01", "v": "WF#1"}, {"k": "Y", "v": "a"}])
    assert sorted((r.k, r.v) for r in _rows(env, PLAIN)) == [("K-01", "wafer-01"), ("Y", "a")]


def test_the_time_rule_folds_and_counts_what_it_left(env):
    report = {}
    _write(env, PLAIN, [{"k": "K-01", "seen": "2026/09/26 13:05:07"},
                        {"k": "K-02", "seen": "2026-09-26 13:05:07"},
                        {"k": "K-03", "seen": "yesterday"},
                        {"k": "K-04", "seen": "2026-09-26T13:05:07+09:00"}], report=report)
    assert sorted((r.k, r.seen) for r in _rows(env, PLAIN)) == [
        ("K-01", "2026-09-26 13:05:07"), ("K-02", "2026-09-26 13:05:07"),
        ("K-03", "yesterday"), ("K-04", "2026-09-26T13:05:07+09:00")]
    assert report == {"unmatched": 1, "zoned": 1}
    assert _fold_lines(env, PLAIN, "seen") == [
        ("2026/09/26 13:05:07", "2026-09-26 13:05:07", "f01.csv")]


def test_a_resent_spelling_whose_cell_is_not_written_leaves_no_line(env):
    """3eb161a9c ①: the hourly refetch the file-layer fold made a no-op mints no line."""
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer.1"}], source="day_0100.csv")
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer.1"}], source="day_0200.csv")
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer.1"}], source="day_0200.csv")
    assert len(_fold_lines(env, PLAIN, "v")) == 1
    _write(env, PLAIN, [{"k": "K-01", "v": "wafer.2"}], source="day_0300.csv")
    assert _fold_lines(env, PLAIN, "v")[-1] == ("wafer.2", "wafer-02", "day_0300.csv")
    assert len(_fold_lines(env, PLAIN, "v")) == 2


def test_a_retried_batch_is_folded_once(env, tmp_path, monkeypatch):
    """A non-idempotent declaration (x -> xx) would store 'axxx' if the retry folded again."""
    _declare(tmp_path, monkeypatch, {PLAIN: {"v": {"write": True,
                                                   "rules": {"replace": [["x", "xx"]]}}}})
    real, calls = crud._apply_batch_updates_once, []

    def lose_the_race_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise IntegrityError("INSERT", {}, Exception("uq_bk"))
        return real(*args, **kwargs)
    monkeypatch.setattr(crud, "_apply_batch_updates_once", lose_the_race_once)
    monkeypatch.setattr(crud, "_is_business_key_unique_violation", lambda exc: True)
    _write(env, PLAIN, [{"k": "K-01", "v": "ax"}])
    assert len(calls) == 2
    assert [r.v for r in _rows(env, PLAIN)] == ["axx"]
    assert _fold_lines(env, PLAIN, "v") == [("ax", "axx", "f01.csv")]


@pytest.mark.parametrize("table, raw, folded_key", [
    (PLAIN, {"k": "k.1", "v": "a"}, "k-01"),
    (COMP, {"lot": "L.1", "wafer": "wafer.1", "x": "a"}, "L-1_wafer-01"),
])
def test_a_row_stored_under_the_raw_spelling_is_found_and_rekeyed(env, tmp_path, monkeypatch,
                                                                   table, raw, folded_key):
    """3eb161a9c ②: the declaration lands on rows written before it - no second row."""
    _declare(tmp_path, monkeypatch, {})
    _write(env, table, [raw], source="f01.csv")
    _declare(tmp_path, monkeypatch, DECLARED)
    again = dict(raw, **({"v": "b"} if table == PLAIN else {"x": "b"}))
    _write(env, table, [again], source="f02.csv")
    (row,) = _rows(env, table)
    assert row.business_key_val == folded_key
    assert (row.v if table == PLAIN else row.x) == "b"


def test_a_new_composite_key_is_assembled_from_the_folded_parts(env):
    _write(env, COMP, [{"lot": "L.1", "wafer": "wafer.2", "x": "a"}])
    (row,) = _rows(env, COMP)
    assert (row.lot, row.wafer, row.business_key_val) == ("L-1", "wafer-02", "L-1_wafer-02")


def test_the_replace_map_scope_is_folded_with_the_values(env):
    """A raw scope would name a lot no stored row has any more, and replace nothing."""
    _write(env, COMP, [{"lot": "L.1", "wafer": "W1", "x": "a"},
                       {"lot": "L.1", "wafer": "W2", "x": "b"}], replace_map=True)
    assert sorted(r.lot for r in _rows(env, COMP)) == ["L-1", "L-1"]
    _write(env, COMP, [], replace_map=True, scope={"lot": "L.1"})
    assert _rows(env, COMP) == []


def test_a_table_with_no_write_column_reads_no_alias(env, tmp_path, monkeypatch):
    _declare(tmp_path, monkeypatch, {PLAIN: DECLARED[PLAIN]})

    def asked(_db):
        raise AssertionError("the alias table was read for a table with no write column")
    monkeypatch.setattr(nn, "aliases_by_column", asked)
    _write(env, COMP, [{"lot": "L.1", "wafer": "wafer.1", "x": "a"}])
    kept, _report = key_gate.screen(COMP, [schemas.GeneralUpdateItem(
        updates={"lot": "L.2", "wafer": "w.2"})])
    assert [(r.lot, r.wafer) for r in _rows(env, COMP)] == [("L.1", "wafer.1")]
    assert kept[0].updates == {"lot": "L.2", "wafer": "w.2"}


# --- the chain key gate: judges the stored spelling, forwards the one that came ----------------

def test_the_key_gate_judges_the_stored_spelling_and_forwards_the_raw_one(env, tmp_path,
                                                                          monkeypatch):
    _declare(tmp_path, monkeypatch, {PLAIN: {
        "k": {"write": True, "rules": {"replace": [["^X\\Z", ""]]}},
        "v": {"write": True, "rules": OWNER}}})
    blanked = schemas.GeneralUpdateItem(updates={"k": "X", "v": "a"}, business_key_val="X")
    kept_one = schemas.GeneralUpdateItem(updates={"k": "K-01", "v": "wafer.1"},
                                         business_key_val="K-01")
    kept, report = key_gate.screen(PLAIN, [blanked, kept_one])
    assert report["refused_rows"] == 1 and report["rows"][0]["unfilled"] == ["k"]
    assert kept == [kept_one] and kept[0].updates["v"] == "wafer.1"


# --- the doors -----------------------------------------------------------------------------------

def test_the_grid_stores_the_folded_spelling(env, client):
    reply = client.put("/tables/%s/data/updates" % PLAIN, json={
        "updates": [{"business_key_val": "K-01", "updates": {"k": "K-01", "v": "wafer.1"}}],
        "transaction_id": "tx-grid"})
    assert reply.status_code == 200, reply.text
    assert [r.v for r in _rows(env, PLAIN)] == ["wafer-01"]
    assert ("wafer.1", "wafer-01", "user") in _fold_lines(env, PLAIN, "v")


def test_a_chain_write_stores_the_folded_spelling(env):
    ok, reason = worker.apply_chain_writes(
        env, "tx-chain", {"name": "r_probe", "target_table": PLAIN}, 0, {PLAIN: {"r_probe"}},
        {PLAIN: [{"business_key_val": "K-01", "updates": {"k": "K-01", "v": "wafer.1"},
                 "source_name": "chain_ingestion"}]},
        [], [], {PLAIN: ["r_probe"]}, [])
    assert ok, reason
    assert [r.v for r in _rows(env, PLAIN)] == ["wafer-01"]
    assert _fold_lines(env, PLAIN, "v") == [("wafer.1", "wafer-01", "chain_ingestion")]


@pytest.fixture(name="watcher")
def fixture_watcher(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    models.init_dynamic_models(_tables())
    for name, info in _tables().items():
        monkeypatch.setitem(crud.TABLE_CONFIG, name, dict(info))
    Base.metadata.create_all(bind=engine)
    models.ensure_ingestion_checkpoint_table(engine)
    _declare(tmp_path, monkeypatch, DECLARED)
    monkeypatch.setattr(directory_watcher, "load_global_table_config",
                        lambda: {PLAIN: TABLES[PLAIN]})
    monkeypatch.setattr(directory_watcher, "SessionLocal", factory)
    monkeypatch.setattr(directory_watcher, "INGESTION_SETTINGS_PATH",
                        str(tmp_path / "ingestion_settings.json"))
    workspace = str(tmp_path / "ws")
    for sub in ("raws", "archives", "err"):
        os.makedirs(os.path.join(workspace, sub))
    handler = IngestionHandler(workspace, None, os.path.join(workspace, "archives"),
                               default_table_name=PLAIN, heavy_lane=FakeLane())
    yield handler, workspace, factory
    nn.reset_cache()
    engine.dispose()
    for name in _tables():
        retire_dynamic_model(name)


def _stored(factory):
    db = factory()
    try:
        return sorted((r.k, r.v, r.seen) for r in db.query(models.DYNAMIC_TABLES[PLAIN]).all())
    finally:
        db.close()


def test_a_file_names_the_time_values_it_left_once_on_its_line(watcher, monkeypatch, caplog):
    handler, workspace, factory = watcher
    path = os.path.join(workspace, "raws", "times.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("k,v,seen\nk.1,wafer.1,2026/09/26 13:05:07\nK-02,a,yesterday\n"
                "K-03,b,2026-09-26T13:05:07+09:00\n")
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10 ** 9)
    with caplog.at_level("INFO"):
        handler._handle_event(path)
        handler.heavy_lane.run_all()
    lines = [r.getMessage() for r in caplog.records if " FILE times.csv:" in r.getMessage()]
    assert len(lines) == 1, lines
    assert ("· time rule left as written: no matching format 1, time zone written 1 ·"
            in lines[0]), lines[0]
    assert _stored(factory) == [("K-02", "a", "yesterday"),
                                ("K-03", "b", "2026-09-26T13:05:07+09:00"),
                                ("k-01", "wafer-01", "2026-09-26 13:05:07")]
    # 5ee9d3bd1 ②: the fold's lines are among the audit-log rows the line counts.
    db = factory()
    try:
        audit = db.query(models.AuditLog).filter(models.AuditLog.table_name == PLAIN).all()
    finally:
        db.close()
    assert sorted(a.column_name for a in audit if a.old_value in ("k.1", "wafer.1",
                                                                  "2026/09/26 13:05:07")) \
        == ["k", "seen", "v"]
    assert "audit logs " in lines[0] and "/ %d rows" % len(audit) in lines[0].split(
        "audit logs ", 1)[1].split(" · ", 1)[0], (len(audit), lines[0])


def test_a_file_that_left_nothing_says_nothing_about_time(watcher, monkeypatch, caplog):
    handler, workspace, _factory = watcher
    path = os.path.join(workspace, "raws", "plain.csv")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("k,v\nk.1,wafer.1\n")
    monkeypatch.setattr(directory_watcher, "get_heavy_threshold_bytes", lambda: 10 ** 9)
    with caplog.at_level("INFO"):
        handler._handle_event(path)
        handler.heavy_lane.run_all()
    lines = [r.getMessage() for r in caplog.records if " FILE plain.csv:" in r.getMessage()]
    assert len(lines) == 1 and "time rule" not in lines[0], lines


def test_a_script_file_stores_the_folded_spelling(watcher):
    handler, _workspace, factory = watcher
    handler._send_to_upsert([{"k": "k.1", "v": "wafer.1"}], uploader="t", filename="s.csv",
                            t_name=PLAIN, table_info=TABLES[PLAIN])
    assert _stored(factory) == [("k-01", "wafer-01", None)]


# --- stage three: what was stored before the declaration is folded in place (총괄 2dc2c1baf) ----

def _stored_then_declared(db, tmp_path, monkeypatch, table, rows_by_source, declared=DECLARED):
    _declare(tmp_path, monkeypatch, {})
    for source, rows in rows_by_source:
        _write(db, table, rows, source=source)
    _declare(tmp_path, monkeypatch, declared)


def _layers_of(db, table, column):
    return sorted((s.source_name, s.value, s.ingested_at) for s in db.query(models.CellSource)
                  .filter(models.CellSource.table_name == table,
                          models.CellSource.column_name == column))


def test_the_backfill_folds_every_layer_in_place_and_the_same_layer_still_wins(
        env, tmp_path, monkeypatch):
    """Through the write door f03 would jump ahead of f07 and show 'wafer-01' (0d9a69a63)."""
    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN,
                          [("f03.csv", [{"k": "K-01", "v": "wafer.1"}]),
                           ("f07.csv", [{"k": "K-01", "v": "W-2"}])])
    before = _layers_of(env, PLAIN, "v")
    dry = replay.fold_written_notation(env, PLAIN)
    assert (dry["cells_folded"], dry["layers_folded"]) == (1, 2)
    assert [r.v for r in _rows(env, PLAIN)] == ["W-2"], "a dry run writes nothing"

    replay.fold_written_notation(env, PLAIN, apply=True)
    assert [r.v for r in _rows(env, PLAIN)] == ["W-02"]
    after = _layers_of(env, PLAIN, "v")
    assert [(s, v) for s, v, _ in after] == [("f03.csv", "wafer-01"), ("f07.csv", "W-02")]
    assert [at for _, _, at in after] == [at for _, _, at in before], "no layer's time moves"
    assert _fold_lines(env, PLAIN, "v")[-1] == ("W-2", "W-02", replay.NOTATION_BACKFILL_SOURCE)


@pytest.mark.parametrize("table, raw, folded_key", [
    (PLAIN, {"k": "k.1", "v": "a"}, "k-01"),
    (COMP, {"lot": "L.1", "wafer": "wafer.1", "x": "a"}, "L-1_wafer-01"),
])
def test_the_backfill_rekeys_a_row_stored_under_the_raw_spelling(env, tmp_path, monkeypatch,
                                                                  table, raw, folded_key):
    _stored_then_declared(env, tmp_path, monkeypatch, table, [("f01.csv", [raw])])
    stats = replay.fold_written_notation(env, table, apply=True)
    (row,) = _rows(env, table)
    assert (stats["keys_changed"], row.business_key_val) == (1, folded_key)


def test_a_row_whose_folded_key_another_row_holds_is_skipped_and_named(env, tmp_path, monkeypatch):
    """총괄 2dc2c1baf ①: joining the two is a merge, and a merge cannot be undone."""
    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN,
                          [("f01.csv", [{"k": "k-01", "v": "a"}, {"k": "k.1", "v": "wafer.1"},
                                        {"k": "k_2", "v": "b"}, {"k": "k.2", "v": "c"}])])
    stats = replay.fold_written_notation(env, PLAIN, apply=True)
    assert stats["rows_skipped"] == 2
    assert sorted(s["folded_key"] for s in stats["skipped"]) == ["k-01", "k-02"]
    assert sorted((r.k, r.v) for r in _rows(env, PLAIN)) == [
        ("k-01", "a"), ("k-02", "b"), ("k.1", "wafer.1"), ("k.2", "c")], \
        "a skipped row keeps every cell as it was stored"


def test_a_value_a_second_fold_moves_again_stops_the_run_before_it_is_written(
        env, tmp_path, monkeypatch):
    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN,
                          [("f01.csv", [{"k": "K-01", "v": "ax"}])],
                          declared={PLAIN: {"v": {"write": True,
                                                  "rules": {"replace": [["x", "xx"]]}}}})
    assert replay.fold_written_notation(env, PLAIN)["moves_again"] == 2, "the cell and its layer"
    stats = replay.fold_written_notation(env, PLAIN, apply=True)
    assert stats["stopped_on_moves_again"] and stats["cells_folded"] == 0
    assert [r.v for r in _rows(env, PLAIN)] == ["ax"]


def test_the_folded_rows_go_out_as_retroactive_events_for_the_ledger(env, tmp_path, monkeypatch):
    """총괄 2dc2c1baf ③: the ledger follows by the events - nothing else is built for it."""
    import event_constants as ec
    from database.context import channel
    from utils.payload_helper import get_payload_dict

    _stored_then_declared(env, tmp_path, monkeypatch, PLAIN,
                          [("f01.csv", [{"k": "K-01", "v": "wafer.1"}])])
    last = env.query(models.DatabaseOutbox.id).order_by(models.DatabaseOutbox.id.desc()).first()
    with channel(ec.CHANNEL_RETROACTIVE):
        replay.fold_written_notation(env, PLAIN, apply=True)
    (row,) = _rows(env, PLAIN)
    events = [get_payload_dict(e.payload) for e in env.query(models.DatabaseOutbox).filter(
        models.DatabaseOutbox.table_name == PLAIN,
        models.DatabaseOutbox.id > (last[0] if last else 0))]
    assert events and all(ec.channel_of(p) == ec.CHANNEL_RETROACTIVE for p in events)
    assert any(row.row_id in (p.get("row_ids") or [p.get("row_id")]) for p in events), events


def test_the_dry_run_says_a_table_with_no_write_column_has_nothing_to_fold(
        env, tmp_path, monkeypatch):
    from admin import retroactive

    _declare(tmp_path, monkeypatch, {PLAIN: DECLARED[PLAIN]})
    out = retroactive.count(env, "fold_written_notation", {"table": COMP})
    assert out["absence"] == retroactive.ABSENCE_NOT_APPLICABLE
    assert out["detail"] == ("'notw_comp' declares no \"write\" column in notation_rules.json "
                             "- nothing is folded.")
