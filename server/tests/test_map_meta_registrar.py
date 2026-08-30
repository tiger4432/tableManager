"""M3 — auto-registration of wafer_map_metadata for ingestion-created maps.

Covers the spec's required axes:
- absent -> created with the batch bbox (non-trivial min corner pins the axis:
  a start-at-0 default or ignored bbox FAILS these asserts)
- present -> NEVER overwritten (user/editor meta authoritative)
- batch dedup: ONE indexed existence check per distinct key per work unit,
  zero checks on a process-cache hit
- knob `auto_register_map_meta` (default ON, hot at work-unit boundary,
  non-boolean falls back to default)
- recursion guard (meta table never self-registers)
- canonical map_id composition pinned for the 7b shared-fn integration
- end-to-end through BOTH writers: watcher `_send_to_upsert` and chain worker
  `process_chain_transaction_group`

Table names use the `mmrauto_test_*` prefix so they can never collide with a
real table in the user's gitignored config (server-pm memory: bonding_log trap).
"""
import asyncio
import json
import os
import sys
import uuid

import pytest
from sqlalchemy import create_engine, event as sa_event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

script_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.abspath(os.path.join(script_dir, ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)
parsers_dir = os.path.join(server_dir, "parsers")
if parsers_dir not in sys.path:
    sys.path.insert(0, parsers_dir)

from database.database import Base
from database import models, crud, schemas
import map_meta_registrar
import map_overlay
from map_meta_registrar import MapMetaCollector, compose_map_id, synthesize_grid_meta, META_TABLE
from product_tables import PRODUCT_TABLES

MAP_TABLE = "mmrauto_test_map"
REGISTRY_TABLE = "mmrauto_test_registry"

TEST_TABLE_CONFIG = {
    MAP_TABLE: {
        "business_key": "chip_key",
        "composite_key_source": ["lot", "slot", "x", "y"],
        "composite_key_separator": "_",
        "map_key_columns": ["lot", "slot"],
        "column_types": {
            "chip_key": "string", "lot": "string", "slot": "string",
            "x": "number", "y": "number", "val": "string",
        },
        "display_columns": ["chip_key", "lot", "slot", "x", "y", "val"],
    },
    # map_key_columns declared but NO x/y columns -> not interpretable as a map
    # (the map_split_registry shape). Must be skipped by binding resolution.
    REGISTRY_TABLE: {
        "business_key": "reg_key",
        "map_key_columns": ["ref_table", "map_key"],
        "column_types": {
            "reg_key": "string", "ref_table": "string",
            "map_key": "string", "note": "string",
        },
        "display_columns": ["reg_key", "ref_table", "map_key", "note"],
    },
    # The real meta table, canonical definition from product_tables (tracked code,
    # not the user's gitignored config).
    META_TABLE: PRODUCT_TABLES[META_TABLE],
}


@pytest.fixture()
def iso_db(tmp_path, monkeypatch):
    """Isolated sqlite DB + config singleton + deterministic registrar inputs."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    models.init_dynamic_models(TEST_TABLE_CONFIG)
    saved_config = dict(crud.TABLE_CONFIG)
    crud.TABLE_CONFIG.clear()
    crud.TABLE_CONFIG.update(TEST_TABLE_CONFIG)

    Base.metadata.create_all(bind=engine)
    models.sync_dynamic_tables_schema(engine)

    # Deterministic environment: no user overlay config, no user ingestion
    # settings (absent file == all defaults), empty process cache.
    monkeypatch.setattr(map_overlay, "load_overlay_config", lambda path=None: {})
    settings_path = str(tmp_path / "ingestion_settings.json")
    monkeypatch.setattr(map_meta_registrar, "INGESTION_SETTINGS_PATH", settings_path)
    map_meta_registrar.reset_known_cache()

    db = TestingSessionLocal()
    try:
        yield db, engine, settings_path
    finally:
        db.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved_config)
        engine.dispose()


def _knob_on(settings_path):
    """Declare the knob instead of leaning on the default.

    The default became OFF on 2026-08-30 (owner ruling: an auto-registered row pins
    `grid_start_x/y`, which the editor reads as the coordinate BASIS, so the hole was
    the safer state).  Every test that follows measures the MECHANISM rather than the
    default, and each one now says so out loud.  Without this the four tests that
    assert NOTHING was written would pass because the feature is switched off -- a
    green that measures nothing, which is worse than the red it replaces.
    """
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"auto_register_map_meta": True}, f)


def _rows(lot, slot, coords, val="v"):
    return [{"lot": lot, "slot": slot, "x": x, "y": y, "val": val} for x, y in coords]


def _meta_rows(db, target_table=None):
    model = models.DYNAMIC_TABLES[META_TABLE]
    q = db.query(model)
    if target_table:
        q = q.filter(model.target_table == target_table)
    return q.all()


# ---------------------------------------------------------------------------
# absent -> created with honest bbox
# ---------------------------------------------------------------------------

def test_absent_key_creates_meta_with_bbox(iso_db):
    db, _, settings_path = iso_db
    _knob_on(settings_path)
    # Non-trivial bbox: min corner (2,1), max (7,4). A start-at-(0,0) default or
    # an ignored extent cannot pass these asserts (defect-axis activation rule).
    coords = [(2, 1), (7, 4), (5, 3), (3, 2)]
    rows = _rows("LOTA", "3", coords)
    rows.append({"lot": "LOTA", "slot": "3", "x": "5.0", "y": "2", "val": "v"})  # stringly float -> integral

    collector = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
    assert collector.active
    collector.collect(rows)
    created = collector.flush(db)
    assert created == 1

    metas = _meta_rows(db, MAP_TABLE)
    assert len(metas) == 1
    row = metas[0]
    assert row.map_id == "LOTA_3"
    assert row.business_key_val == f"{MAP_TABLE}_LOTA_3"
    gm = json.loads(row.grid_metadata)
    assert gm["grid_cols"] == 6 and gm["grid_rows"] == 4
    assert gm["grid_start_x"] == 2 and gm["grid_start_y"] == 1
    assert gm["rotation"] == 0 and gm["side"] == "front" and gm["grid_y_invert"] is False
    # Mask-neutral physical vocabulary (editor 표준 mirror) — no guessed geometry.
    assert gm["phys_chip_x"] == 1 and gm["phys_chip_y"] == 1
    assert gm["phys_offset_x"] == 0 and gm["phys_offset_y"] == 0
    assert gm["phys_edge_margin"] == 3
    assert gm["phys_wafer_dia"] == 300  # small grid -> floor of 300
    assert gm["auto_registered"] is True


def test_synthetic_dia_circumscribes_large_grids():
    # 1000x1000 grid: half-diagonal ~707.1 -> dia must exceed the 300 floor and
    # circumscribe (2*(halfdiag+4) = ceil(1422.2)) so no cell is masked out.
    gm = synthesize_grid_meta(0, 0, 999, 999)
    assert gm["phys_wafer_dia"] == 1423


# ---------------------------------------------------------------------------
# present -> never overwritten
# ---------------------------------------------------------------------------

def test_existing_meta_is_never_overwritten(iso_db):
    db, _, settings_path = iso_db
    _knob_on(settings_path)
    user_meta = json.dumps({"grid_cols": 9, "grid_rows": 9, "grid_start_x": 0,
                            "grid_start_y": 0, "grid_y_invert": True, "rotation": 90,
                            "side": "back"})
    seed = schemas.GeneralUpdateBatch(updates=[schemas.GeneralUpdateItem(
        business_key_val=f"{MAP_TABLE}_LOTB_1",
        updates={"target_table": MAP_TABLE, "map_id": "LOTB_1", "grid_metadata": user_meta},
        source_name="user", updated_by="editor_user")])
    crud.apply_batch_updates(db, META_TABLE, seed)

    # Precondition that makes an overwrite detectable: the synthetic meta for
    # this batch differs from the seeded user meta (rotation 90 vs 0, dims).
    synthetic = synthesize_grid_meta(0, 0, 5, 5)
    assert synthetic["rotation"] != 90 and synthetic["grid_cols"] != 9

    collector = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
    collector.collect(_rows("LOTB", "1", [(0, 0), (5, 5)]))
    assert collector.flush(db) == 0

    metas = _meta_rows(db, MAP_TABLE)
    assert len(metas) == 1
    assert metas[0].grid_metadata == user_meta  # byte-identical: untouched


# ---------------------------------------------------------------------------
# batch dedup: one existence check per distinct key; cache kills repeats
# ---------------------------------------------------------------------------

def _count_existence_checks(engine, statements):
    """Listener matching ONLY the registrar's existence check: a bare
    business_key_val SELECT on the meta table (apply_batch_updates' row lookup
    also filters business_key_val but always selects row_id too)."""
    def _before(conn, cursor, statement, parameters, context, executemany):
        s = statement.lower()
        if ("from wafer_map_metadata" in s and "business_key_val in" in s
                and "row_id" not in s):
            statements.append(statement)
    sa_event.listen(engine, "before_cursor_execute", _before)
    return _before


def test_batch_dedup_one_existence_check_per_work_unit(iso_db):
    db, engine, settings_path = iso_db
    _knob_on(settings_path)
    statements = []
    hook = _count_existence_checks(engine, statements)
    try:
        # 5,000 rows over 2 distinct keys -> bbox dict has 2 entries and the
        # existence check is a single chunked IN query, not per-row/per-key.
        rows = _rows("LOTC", "1", [(i % 50, i // 50) for i in range(2500)])
        rows += _rows("LOTC", "2", [(i % 50, i // 50) for i in range(2500)])
        collector = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
        collector.collect(rows)
        assert len(collector.bboxes) == 2
        assert collector.flush(db) == 2
        assert len(statements) == 1, f"expected ONE existence check, got {len(statements)}"

        # Second work unit on the same keys: process cache -> ZERO queries.
        statements.clear()
        collector2 = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
        collector2.collect(_rows("LOTC", "1", [(0, 0)]))
        assert collector2.flush(db) == 0
        assert statements == []
    finally:
        sa_event.remove(engine, "before_cursor_execute", hook)


# ---------------------------------------------------------------------------
# knob: default OFF, on enables, non-boolean falls back, hot at unit boundary
# ---------------------------------------------------------------------------

def test_knob_off_disables_and_rewrites_hot(iso_db):
    db, _, settings_path = iso_db
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"auto_register_map_meta": False}, f)
    collector = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
    assert collector.active is False
    collector.collect(_rows("LOTD", "1", [(0, 0)]))
    assert collector.flush(db) == 0
    assert _meta_rows(db, MAP_TABLE) == []

    # Hot reload at the NEXT work-unit boundary (a new collector).
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"auto_register_map_meta": True}, f)
    collector2 = MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE])
    assert collector2.active is True


def test_knob_non_boolean_falls_back_to_default_off(iso_db):
    # WAS `..._default_on`, asserting True.  The default itself changed on 2026-08-30
    # by owner ruling, so this assertion moves with its subject rather than being
    # kept alive against a default that no longer exists.
    _, _, settings_path = iso_db
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump({"auto_register_map_meta": "true"}, f)  # string, not JSON boolean
    assert MapMetaCollector(MAP_TABLE, TEST_TABLE_CONFIG[MAP_TABLE]).active is False


# ---------------------------------------------------------------------------
# guards: recursion + non-map registry shape
# ---------------------------------------------------------------------------

def test_recursion_guard_meta_table_never_self_registers(iso_db):
    _, _, settings_path = iso_db
    _knob_on(settings_path)   # else `active is False` holds for every table
    # Belt: explicit refusal even if someone (mis)declares map_key_columns on
    # the meta table itself. Suspenders: the real config declares none.
    poisoned = dict(PRODUCT_TABLES[META_TABLE])
    poisoned["map_key_columns"] = ["target_table"]
    assert MapMetaCollector(META_TABLE, poisoned).active is False
    assert "map_key_columns" not in PRODUCT_TABLES[META_TABLE]


def test_registry_shaped_table_without_coordinates_is_skipped(iso_db):
    _, _, settings_path = iso_db
    _knob_on(settings_path)   # else `active is False` holds for every table
    # map_key_columns declared but no x/y -> resolve_binding None -> inert.
    assert MapMetaCollector(REGISTRY_TABLE, TEST_TABLE_CONFIG[REGISTRY_TABLE]).active is False


# ---------------------------------------------------------------------------
# canonical composition pin (7b integration anchor)
# ---------------------------------------------------------------------------

def test_map_id_composition_pinned_for_7b():
    """Pins the CURRENT canonical composition (editor '_' join + crud
    clean_str_value normalization) so tomorrow's rerouting through the shared
    canonicalization fn (TODO(7b) in map_meta_registrar.compose_map_id) is a
    provable no-op — if the shared fn composes differently, this fails loudly."""
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": "3"}) == "LOT1_3"
    # clean_str_value: integral floats lose the trailing .0 (matches crud bk assembly)
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": 3.0}) == "LOT1_3"
    assert compose_map_id(["base"], {"base": " B77 "}) == "B77"
    # A missing/empty part disqualifies the row — ingestion never registers a
    # partial identity (documented divergence from the editor's lenient join).
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1"}) is None
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": " "}) is None


# ---------------------------------------------------------------------------
# end-to-end: watcher path
# ---------------------------------------------------------------------------

def test_watcher_send_to_upsert_registers_meta(iso_db, monkeypatch):
    db, _, settings_path = iso_db
    _knob_on(settings_path)
    import directory_watcher

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: db)

    original_json_load = json.load

    def fake_load(fp, *args, **kwargs):
        if hasattr(fp, "name") and "table_config.json" in str(getattr(fp, "name", "")):
            return TEST_TABLE_CONFIG
        return original_json_load(fp, *args, **kwargs)

    monkeypatch.setattr(json, "load", fake_load)

    handler = directory_watcher.IngestionHandler(
        workspace_path="unused", config_path=None, archives_path="unused",
        default_table_name=MAP_TABLE)

    rows = [{"lot": "WLOT", "slot": "7", "x": x, "y": y, "val": "d"}
            for x, y in [(1, 1), (4, 6), (2, 3)]]
    handler._send_to_upsert(rows, uploader="tester", filename="wlot.csv")

    # Data landed…
    data_model = models.DYNAMIC_TABLES[MAP_TABLE]
    assert db.query(data_model).count() == 3
    # …and exactly one meta row for the one distinct key, with the file's bbox.
    metas = _meta_rows(db, MAP_TABLE)
    assert len(metas) == 1 and metas[0].map_id == "WLOT_7"
    gm = json.loads(metas[0].grid_metadata)
    assert (gm["grid_start_x"], gm["grid_start_y"]) == (1, 1)
    assert (gm["grid_cols"], gm["grid_rows"]) == (4, 6)

    # Re-ingesting the same file must not duplicate or touch the meta row.
    stamp = metas[0].grid_metadata
    handler._send_to_upsert(list(rows), uploader="tester", filename="wlot.csv")
    metas2 = _meta_rows(db, MAP_TABLE)
    assert len(metas2) == 1 and metas2[0].grid_metadata == stamp


def test_watcher_meta_failure_does_not_fail_ingestion(iso_db, monkeypatch):
    """A registrar crash is logged and swallowed — the file completes normally."""
    db, _, settings_path = iso_db
    _knob_on(settings_path)   # else flush() never runs and the boom never fires
    import directory_watcher

    monkeypatch.setattr(directory_watcher, "SessionLocal", lambda: db)
    original_json_load = json.load

    def fake_load(fp, *args, **kwargs):
        if hasattr(fp, "name") and "table_config.json" in str(getattr(fp, "name", "")):
            return TEST_TABLE_CONFIG
        return original_json_load(fp, *args, **kwargs)

    monkeypatch.setattr(json, "load", fake_load)

    def boom(self, db_):
        raise RuntimeError("meta boom")

    monkeypatch.setattr(map_meta_registrar.MapMetaCollector, "flush", boom)

    handler = directory_watcher.IngestionHandler(
        workspace_path="unused", config_path=None, archives_path="unused",
        default_table_name=MAP_TABLE)
    handler._send_to_upsert(
        [{"lot": "FLOT", "slot": "1", "x": 0, "y": 0, "val": "d"}],
        uploader="tester", filename="flot.csv")  # must not raise

    assert db.query(models.DYNAMIC_TABLES[MAP_TABLE]).count() == 1
    assert _meta_rows(db, MAP_TABLE) == []


# ---------------------------------------------------------------------------
# end-to-end: chain worker path
# ---------------------------------------------------------------------------

def mmrauto_chain_mapper(db, payload):
    return {"updates": [
        {"updates": {"lot": "CHLOT", "slot": "1", "x": i, "y": i + 2, "val": "c"},
         "source_name": "chain_ingestion", "updated_by": "chain"}
        for i in range(3)
    ]}


def test_chain_worker_registers_meta(iso_db):
    db, _, settings_path = iso_db
    _knob_on(settings_path)
    from database.models import DatabaseOutbox
    from chain_ingestion_worker import process_chain_transaction_group

    tx_id = "tx_mmrauto"
    trigger = DatabaseOutbox(
        event_uuid=str(uuid.uuid4()), event_type="CREATE",
        table_name="mmrauto_test_trigger",
        payload={"source_name": "user", "transaction_id": tx_id, "data": {"k": "v"}})
    rule = {
        "name": "mmrauto_rule", "trigger_table": "mmrauto_test_trigger",
        "target_table": MAP_TABLE,
        "mapper_module": "tests.test_map_meta_registrar",
        "mapper_function": "mmrauto_chain_mapper",
        "enabled": True, "is_batch": False,
    }

    success, error, _msgs = asyncio.run(
        process_chain_transaction_group(tx_id, [trigger], db, [rule]))
    assert success is True and error is None

    metas = _meta_rows(db, MAP_TABLE)
    assert len(metas) == 1 and metas[0].map_id == "CHLOT_1"
    gm = json.loads(metas[0].grid_metadata)
    assert (gm["grid_start_x"], gm["grid_start_y"]) == (0, 2)
    assert (gm["grid_cols"], gm["grid_rows"]) == (3, 3)
    assert gm["auto_registered"] is True
