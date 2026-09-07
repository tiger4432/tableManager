# -*- coding: utf-8 -*-
"""`map_meta_registrar` — 은퇴된 «쓰기»가 정말 안 일어나는가, 그리고 남은 둘.

M3 자동 등록(`MapMetaCollector` · 손잡이 `auto_register_map_meta` · 배선 둘)은
2026-09-07 소유자 지시로 은퇴했다. 그것을 재던 열 시험은 같은 커밋에 같이 죽고,
대신 «안 쓴다»를 두 배선 자리에서 직접 재는 시험 둘이 남는다.

파일이 사라지지 않는 이유는 둘이다:
  ① 은퇴는 «사건»이다 — 배선이 돌아오면 이 둘이 빨개진다
  ② 모듈에 «쓰는 일과 무관한» 성질 둘이 남아 있다:
     `synthesize_grid_meta`  정렬이 미등록 맵을 가정할 때 부른다(`map_alignment:488`)
     `compose_map_id`        등록과 조회가 «같은 신원»을 지어야 한다(7b 공유 정규화)

표 이름은 `mmrauto_test_*` 접두라 사용자의 gitignore 된 설정과 절대 부딪히지 않는다.
"""
import asyncio
import json
import os
import sys
import uuid

import pytest
from sqlalchemy import create_engine
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
from database import models, crud
import map_overlay
from map_meta_registrar import compose_map_id, synthesize_grid_meta, META_TABLE
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
    """Isolated sqlite DB + config singleton, so both writers run on tables that
    cannot collide with the user's gitignored config."""
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
    db = TestingSessionLocal()
    try:
        yield db, engine
    finally:
        db.close()
        crud.TABLE_CONFIG.clear()
        crud.TABLE_CONFIG.update(saved_config)
        engine.dispose()


def _rows(lot, slot, coords, val="v"):
    return [{"lot": lot, "slot": slot, "x": x, "y": y, "val": val} for x, y in coords]


def _meta_rows(db, target_table=None):
    model = models.DYNAMIC_TABLES[META_TABLE]
    q = db.query(model)
    if target_table:
        q = q.filter(model.target_table == target_table)
    return q.all()


# ---------------------------------------------------------------------------
# 은퇴 관문 — 두 배선 자리에서 메타가 «안 생긴다»
# ---------------------------------------------------------------------------

def test_the_file_watcher_creates_no_meta_row(iso_db, monkeypatch):
    """맵 파일 하나를 적재해도 `wafer_map_metadata` 행은 0 이다.

    재는 것은 «부재»가 아니라 «사건»이다 — 데이터는 들어오고(3행) 메타만
    안 생긴다. 데이터 단언이 없으면 적재 자체가 죽어도 이 시험이 초록이 된다.
    """
    db, _ = iso_db
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
    handler._send_to_upsert(
        [{"lot": "WLOT", "slot": "7", "x": x, "y": y, "val": "d"}
         for x, y in [(1, 1), (4, 6), (2, 3)]],
        uploader="tester", filename="wlot.csv")

    assert db.query(models.DYNAMIC_TABLES[MAP_TABLE]).count() == 3
    assert _meta_rows(db, MAP_TABLE) == []


def mmrauto_chain_mapper(db, payload):
    return {"updates": [
        {"updates": {"lot": "CHLOT", "slot": "1", "x": i, "y": i + 2, "val": "c"},
         "source_name": "chain_ingestion", "updated_by": "chain"}
        for i in range(3)
    ]}


def test_the_chain_worker_creates_no_meta_row(iso_db):
    """같은 사실, 둘째 배선. 체인 쓰기는 성공하고 메타만 안 생긴다."""
    db, _ = iso_db
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
    assert db.query(models.DYNAMIC_TABLES[MAP_TABLE]).count() == 3
    assert _meta_rows(db, MAP_TABLE) == []


# ---------------------------------------------------------------------------
# 남은 둘
# ---------------------------------------------------------------------------

def test_synthetic_dia_circumscribes_large_grids():
    # 1000x1000 grid: half-diagonal ~707.1 -> dia must exceed the 300 floor and
    # circumscribe (2*(halfdiag+4) = ceil(1422.2)) so no cell is masked out.
    gm = synthesize_grid_meta(0, 0, 999, 999)
    assert gm["phys_wafer_dia"] == 1423


def test_map_id_composition_pinned_for_7b():
    """Pins the canonical composition (editor '_' join + the shared
    canonicalization) — registration and lookup must compose the SAME identity."""
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": "3"}) == "LOT1_3"
    # clean_str_value: integral floats lose the trailing .0 (matches crud bk assembly)
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": 3.0}) == "LOT1_3"
    assert compose_map_id(["base"], {"base": " B77 "}) == "B77"
    # A missing/empty part disqualifies the row — a partial identity is never composed
    # (documented divergence from the editor's lenient join).
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1"}) is None
    assert compose_map_id(["lot", "slot"], {"lot": "LOT1", "slot": " "}) is None
