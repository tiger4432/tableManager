# [이슈 #7] 런타임 신규 테이블 물리 CREATE 회귀 테스트
#
# 재현 시나리오: table_config.json에 새 테이블 추가 → 핫리로드(SYSTEM_RELOAD / reload-configs)
# → ORM 등록은 되지만 물리 CREATE TABLE이 없어 재기동 전까지 조회가 UndefinedTable 500.
# 수정: models.refresh_dynamic_models(engine) / models.create_missing_dynamic_tables(engine)가
# 리로드 경로에서 신규 테이블에 한해 물리 CREATE를 수행한다.
#
# 주의: 테스트 테이블명은 사용자 config(gitignored)에 실존 불가능한 고유 접두어(rtct_*)를
# 사용한다 — 공유 in-memory sqlite 선점으로 인한 격리 실패 방지(교훈 파일 bonding_log 사례).

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from database import models, crud


def _make_new_table_config(table_name: str) -> dict:
    """기존 TABLE_CONFIG에 신규 테이블 1개가 추가된 config를 반환(실사용 시나리오 재현)."""
    new_config = {k: dict(v) for k, v in crud.TABLE_CONFIG.items()}
    new_config[table_name] = {
        "business_key": "lot_id",
        "column_types": {
            "lot_id": "string",
            "qty": "number",
        },
    }
    return new_config


def test_create_missing_dynamic_tables_creates_only_new(db_session):
    """신규 등록 테이블만 CREATE하고, 기존 테이블은 게이트에서 스킵(무DDL)한다."""
    engine = db_session.get_bind()
    table_name = "rtct_only_new"

    # 1. ORM 등록만 수행 (핫리로드 직후 상태 재현 — 물리 테이블 없음)
    models.init_dynamic_models({table_name: {
        "business_key": "lot_id",
        "column_types": {"lot_id": "string"},
    }})
    assert table_name in models.DYNAMIC_TABLES
    assert not inspect(engine).has_table(table_name)

    # 2. 물리 테이블이 없으므로 조회는 실패해야 정상 (버그 재현 지점)
    model = models.DYNAMIC_TABLES[table_name]
    with pytest.raises(OperationalError):
        db_session.query(model).count()
    db_session.rollback()  # 실패 트랜잭션 오염 제거

    # 3. 수정 함수 실행 — 신규 테이블만 생성되어야 함
    created = models.create_missing_dynamic_tables(engine)
    assert table_name in created
    assert "raw_table_1" not in created  # 기존 테이블은 게이트에서 스킵
    assert inspect(engine).has_table(table_name)

    # 4. 즉시 조회 가능 (재기동 불필요)
    assert db_session.query(model).count() == 0

    # 5. 멱등성 — 재호출 시 아무것도 생성하지 않음
    assert models.create_missing_dynamic_tables(engine) == []


def test_refresh_dynamic_models_hot_reload_then_query_200(client, db_session, monkeypatch):
    """이슈 #7 E2E: config에 테이블 추가 → 리로드 → 즉시 API 조회가 200."""
    engine = db_session.get_bind()
    table_name = "rtct_hot_reload"

    # 0. 리로드 전: 미등록 테이블 조회는 404
    res = client.get(f"/tables/{table_name}/data")
    assert res.status_code == 404

    # 1. table_config.json에 신규 테이블이 추가된 상황을 재현
    monkeypatch.setattr(crud, "load_table_config", lambda: _make_new_table_config(table_name))

    # 2. 핫리로드 공용 진입점 실행 (reload_local_process_cache / SYSTEM_RELOAD 핸들러가 호출)
    created = models.refresh_dynamic_models(engine)

    # 3. 캐시 정합: TABLE_CONFIG 싱글턴 + DYNAMIC_TABLES + 물리 테이블 모두 갱신
    assert table_name in created
    assert table_name in crud.TABLE_CONFIG
    assert table_name in models.DYNAMIC_TABLES
    assert inspect(engine).has_table(table_name)

    # 4. 재기동 없이 즉시 조회 200 (기존 UndefinedTable 500 회귀 지점)
    res = client.get(f"/tables/{table_name}/data")
    assert res.status_code == 200

    # 5. 기존 테이블 데이터는 그대로 유효 (리로드가 기존 캐시를 파괴하지 않음)
    res = client.get("/tables/raw_table_1/data")
    assert res.status_code == 200


def test_refresh_dynamic_models_guards_empty_config(db_session, monkeypatch):
    """config 로드 실패(빈 dict) 시 기존 TABLE_CONFIG 싱글턴을 지우지 않는다."""
    engine = db_session.get_bind()
    before = dict(crud.TABLE_CONFIG)
    assert before  # 픽스처가 시딩한 config 존재

    monkeypatch.setattr(crud, "load_table_config", lambda: {})
    assert models.refresh_dynamic_models(engine) == []
    assert crud.TABLE_CONFIG == before


def test_refresh_dynamic_models_without_engine_skips_ddl(db_session, monkeypatch):
    """engine=None(모델 캐시 갱신 전용) 경로는 DDL 없이 ORM 등록만 수행한다."""
    engine = db_session.get_bind()
    table_name = "rtct_no_engine"

    monkeypatch.setattr(crud, "load_table_config", lambda: _make_new_table_config(table_name))
    created = models.refresh_dynamic_models(None)

    assert created == []
    assert table_name in models.DYNAMIC_TABLES  # ORM 등록은 수행
    assert not inspect(engine).has_table(table_name)  # 물리 CREATE는 미수행
