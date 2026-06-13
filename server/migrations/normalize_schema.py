"""
JSONB → Normalized Schema Migration Script
===========================================
기존 JSONB 동적 컬럼 구조 { value, is_overwrite, sources, updated_by }를
Native SQL 컬럼(String/Float/DateTime) + 메타데이터 분리 테이블(cell_overwrites, cell_sources)
구조로 전환하는 마이그레이션 스크립트입니다.

실행: python server/migrations/normalize_schema.py

안전장치:
  - 멱등성: 이미 정규화된 테이블은 자동 스킵
  - 중단 복구: _migration_backup 테이블 감지 시 자동 재개
  - 인덱스 충돌 방지: pg_indexes 조회 후 고아 인덱스 선제 제거
"""

import os
import sys
import json
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가하여 server 패키지 import 가능하게 함
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text, inspect
from server.database.database import engine, Base, SessionLocal
from server.database import models, crud


# ─────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────

def drop_orphan_indexes(db, table_name: str):
    """PostgreSQL pg_indexes에서 table_name을 포함하는 고아 인덱스를 선제적으로 제거합니다."""
    try:
        idx_rows = db.execute(text(
            "SELECT indexname FROM pg_indexes WHERE indexname LIKE :pattern"
        ), {"pattern": f"%{table_name}%"}).fetchall()
        for r in idx_rows:
            idx_name = r[0]
            if idx_name and not idx_name.endswith("_pkey"):
                print(f"  -> Dropping orphan index '{idx_name}'...")
                db.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
                db.commit()
    except Exception as e:
        print(f"  [!] Warning during index cleanup for '{table_name}': {e}")
        db.rollback()


def drop_backup_indexes(db, backup_table_name: str, is_sqlite: bool):
    """백업 테이블에 잔류하는 인덱스들을 일괄 제거하여 새 테이블 생성 시 이름 충돌을 방지합니다."""
    try:
        if not is_sqlite:
            idx_rows = db.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = :tablename"
            ), {"tablename": backup_table_name}).fetchall()
            index_names = [r[0] for r in idx_rows]
        else:
            inspector = inspect(engine)
            index_names = [idx.get("name") for idx in inspector.get_indexes(backup_table_name) if idx.get("name")]

        for idx_name in index_names:
            if idx_name and not idx_name.endswith("_pkey"):
                print(f"  -> Dropping backup index '{idx_name}'...")
                try:
                    db.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
                    db.commit()
                except Exception as e:
                    print(f"  [!] Could not drop index '{idx_name}': {e}")
                    db.rollback()
    except Exception as e:
        print(f"  [!] Failed to enumerate indexes for '{backup_table_name}': {e}")
        db.rollback()


def parse_jsonb_cell(cell_val) -> dict:
    """
    JSONB 셀 데이터를 표준 딕셔너리로 파싱합니다.
    반환: { value, is_overwrite, updated_by, sources: dict, manual_priority_source }
    """
    if cell_val is None:
        return None

    # 문자열인 경우 JSON 파싱 시도
    if isinstance(cell_val, str):
        try:
            cell_val = json.loads(cell_val)
        except (json.JSONDecodeError, ValueError):
            return {
                "value": cell_val,
                "is_overwrite": False,
                "sources": {},
                "updated_by": "system",
                "manual_priority_source": None
            }

    # dict가 아닌 경우 (숫자, 리스트 등) 래핑
    if not isinstance(cell_val, dict):
        return {
            "value": cell_val,
            "is_overwrite": False,
            "sources": {},
            "updated_by": "system",
            "manual_priority_source": None
        }

    return {
        "value": cell_val.get("value"),
        "is_overwrite": cell_val.get("is_overwrite", False),
        "updated_by": cell_val.get("updated_by", "system"),
        "sources": cell_val.get("sources", {}),
        "manual_priority_source": cell_val.get("manual_priority_source")
    }


def migrate_row_sources(db, table_name: str, row_id: str, col: str, sources: dict):
    """JSONB 내 sources 딕셔너리를 cell_sources 테이블로 이관합니다."""
    for src_name, src_data in sources.items():
        if isinstance(src_data, dict):
            s_val = src_data.get("value")
            s_ts_str = src_data.get("timestamp")
            s_user = src_data.get("updated_by", "system")
        else:
            s_val = src_data
            s_ts_str = None
            s_user = "system"

        s_ts = None
        if s_ts_str:
            try:
                s_ts = datetime.fromisoformat(s_ts_str)
            except (ValueError, TypeError):
                s_ts = datetime.now()

        db.add(models.CellSource(
            table_name=table_name,
            row_id=row_id,
            column_name=col,
            source_name=src_name,
            value=s_val,
            ingested_at=s_ts,
            updated_by=s_user
        ))


def migrate_row_overwrite(db, table_name: str, row_id: str, col: str,
                          is_overwrite: bool, updated_by: str, updated_at, manual_pin):
    """JSONB 내 overwrite/pin 정보를 cell_overwrites 테이블로 이관합니다."""
    db.add(models.CellOverwrite(
        table_name=table_name,
        row_id=row_id,
        column_name=col,
        is_overwrite=is_overwrite,
        updated_by=updated_by,
        updated_at=updated_at or datetime.now(),
        manual_priority_source=manual_pin
    ))


# ─────────────────────────────────────────────
# 테이블 단위 마이그레이션
# ─────────────────────────────────────────────

def check_migration_needed(inspector, table_name: str, table_cfg: dict, is_sqlite: bool):
    """
    테이블의 마이그레이션 필요 여부를 판단합니다.
    반환: (needs_migration: bool, skip_rename: bool)
    """
    has_main = inspector.has_table(table_name)
    backup_name = f"{table_name}_migration_backup"
    has_backup = inspector.has_table(backup_name)

    if has_main:
        existing_columns = {c["name"]: c["type"] for c in inspector.get_columns(table_name)}

        for col_name in table_cfg.get("column_types", {}).keys():
            if col_name in ["created_at", "updated_at"]:
                continue
            col_type_str = str(existing_columns.get(col_name, "")).upper()
            if "JSON" in col_type_str or "JSONB" in col_type_str:
                return True, False

        # 이미 정규화됨 → 잔여 백업 테이블 정리
        if has_backup:
            return False, False  # caller에서 잔여 백업 정리 처리
        return False, False

    elif has_backup:
        # 이전 실행 중단 상태 → 재개
        return True, True

    else:
        # 테이블 자체가 없음 → 새로 생성
        return False, False


def migrate_single_table(db, table_name: str, table_cfg: dict, is_sqlite: bool):
    """단일 테이블에 대한 JSONB → Normalized 마이그레이션을 수행합니다."""
    inspector = inspect(engine)
    backup_name = f"{table_name}_migration_backup"
    has_main = inspector.has_table(table_name)
    has_backup = inspector.has_table(backup_name)

    needs_migration, skip_rename = check_migration_needed(inspector, table_name, table_cfg, is_sqlite)

    if not needs_migration:
        if has_main:
            print(f"[OK] '{table_name}'  - already normalized, skipping.")
            if has_backup:
                print(f"  -> Dropping leftover backup table '{backup_name}'...")
                db.execute(text(f'DROP TABLE "{backup_name}"'))
                db.commit()
        else:
            print(f"[OK] '{table_name}'  - does not exist, creating directly...")
            table_obj = Base.metadata.tables.get(table_name)
            if table_obj is not None:
                table_obj.create(bind=engine, checkfirst=True)
        return

    if skip_rename:
        print(f"[~] '{table_name}'  - resuming from backup table...")
    else:
        print(f"[*] '{table_name}'  - migration required")

    # ── Step 1: RENAME 원본 → 백업 ──
    if not skip_rename:
        if has_backup:
            print(f"  -> Dropping old backup table '{backup_name}'...")
            db.execute(text(f'DROP TABLE "{backup_name}"'))
            db.commit()

        print(f"  -> Renaming '{table_name}' → '{backup_name}'...")
        db.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{backup_name}"'))
        db.commit()

    # ── Step 2: 백업 테이블 인덱스 제거 ──
    drop_backup_indexes(db, backup_name, is_sqlite)

    # ── Step 3: 새 정규화 테이블 생성 ──
    print(f"  -> Creating new normalized table '{table_name}'...")
    table_obj = Base.metadata.tables.get(table_name)
    if table_obj is not None:
        table_obj.create(bind=engine, checkfirst=True)

    # ── Step 4: 데이터 이관 (Raw Connection으로 JSONB 디코딩 충돌 우회) ──
    print(f"  -> Reading data from '{backup_name}' via raw connection...")
    raw_conn = db.connection().connection
    cursor = raw_conn.cursor()
    cursor.execute(f'SELECT * FROM "{backup_name}"')
    backup_rows = cursor.fetchall()
    backup_cols = [desc[0] for desc in cursor.description]
    cursor.close()
    print(f"  -> Found {len(backup_rows)} rows to migrate.")

    user_cols = [c for c in table_cfg.get("column_types", {}).keys() if c not in ["created_at", "updated_at"]]
    table_model = models.DYNAMIC_TABLES[table_name]
    migrated = 0

    for brow in backup_rows:
        row_dict = dict(zip(backup_cols, brow))
        row_id = row_dict.get("row_id")
        updated_at = row_dict.get("updated_at")

        # 새 행 생성
        new_row = table_model(
            row_id=row_id,
            business_key_val=row_dict.get("business_key_val"),
            created_at=row_dict.get("created_at"),
            updated_at=updated_at
        )
        db.add(new_row)

        # 사용자 컬럼 마이그레이션
        for col in user_cols:
            parsed = parse_jsonb_cell(row_dict.get(col))
            if parsed is None:
                continue

            # 기본 테이블에 raw value 지정
            setattr(new_row, col, parsed["value"])

            # cell_sources 적재
            if parsed["sources"]:
                migrate_row_sources(db, table_name, row_id, col, parsed["sources"])

            # cell_overwrites 적재
            if parsed["is_overwrite"] or parsed["manual_priority_source"]:
                migrate_row_overwrite(
                    db, table_name, row_id, col,
                    parsed["is_overwrite"], parsed["updated_by"],
                    updated_at, parsed["manual_priority_source"]
                )

        migrated += 1
        if migrated % 1000 == 0:
            db.flush()
            print(f"  -> Progress: {migrated}/{len(backup_rows)} rows...")

    db.commit()
    print(f"  [OK] Migrated {migrated} rows successfully.")

    # ── Step 5: 백업 테이블 DROP ──
    print(f"  -> Dropping backup table '{backup_name}'...")
    db.execute(text(f'DROP TABLE "{backup_name}"'))
    db.commit()


# ─────────────────────────────────────────────
# 메인 엔트리포인트
# ─────────────────────────────────────────────

def migrate_database():
    print("=" * 60)
    print("  JSONB → Normalized Schema Migration")
    print("=" * 60)

    # 1. 설정 로드
    config = crud.TABLE_CONFIG
    if not config:
        print("[FAIL] Error: No table configuration found in table_config.json.")
        return False

    print(f"\nTables to process: {list(config.keys())}")

    # 2. Dynamic models 초기화
    models.init_dynamic_models(config)

    db = SessionLocal()
    try:
        is_sqlite = "sqlite" in str(engine.url)

        # 3. 고아 인덱스 선제 청소 (PostgreSQL only)
        if not is_sqlite:
            print("\n[Phase 1] Pre-cleaning orphan indexes...")
            for table_name in config.keys():
                drop_orphan_indexes(db, table_name)

        # 4. Static 테이블 생성 (cell_overwrites, cell_sources 등)
        print("\n[Phase 2] Ensuring metadata tables exist...")
        static_tables = [
            tbl for name, tbl in Base.metadata.tables.items()
            if name not in config
        ]
        Base.metadata.create_all(bind=engine, tables=static_tables)
        print("  [OK] cell_overwrites, cell_sources tables ready.")

        # 5. 각 테이블 마이그레이션
        print("\n[Phase 3] Migrating tables...")
        for table_name, table_cfg in config.items():
            # 테이블별 인덱스 재청소 (이전 단계에서 RENAME 등으로 새로 발생 가능)
            if not is_sqlite:
                drop_orphan_indexes(db, table_name)
            migrate_single_table(db, table_name, table_cfg, is_sqlite)
            print()

        print("=" * 60)
        print("  [OK] All tables migrated successfully!")
        print("=" * 60)
        return True

    except Exception as e:
        db.rollback()
        print(f"\n[FAIL] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
