# JSONB → Normalized Schema Migration

기존 JSONB 동적 컬럼 구조를 관계형 Native SQL 컬럼 + 메타데이터 테이블 구조로 전환하는 마이그레이션 도구입니다.

## 구조 변경 개요

### Before (JSONB)
각 사용자 컬럼이 하나의 JSONB 컬럼에 모든 데이터를 저장:
```json
{
  "value": "ABC-001",
  "is_overwrite": true,
  "updated_by": "user",
  "sources": {
    "ERP": {"value": "ABC-001", "timestamp": "2026-06-01T00:00:00"},
    "MES": {"value": "ABC-002", "timestamp": "2026-06-02T00:00:00"}
  },
  "manual_priority_source": "ERP"
}
```

### After (Normalized)
데이터를 3개 테이블로 분리:

| 테이블 | 역할 | 예시 |
|---|---|---|
| `inventory_master` | 비즈니스 데이터 (native 타입) | `part_no = 'ABC-001'` (String), `stock_qty = 100.0` (Float) |
| `cell_overwrites` | 수동 수정 마킹 및 Pin 정보 | `is_overwrite=True, updated_by='user', manual_priority_source='ERP'` |
| `cell_sources` | 원천 데이터별 수집 이력 | `source_name='ERP', value='ABC-001', ingested_at=...` |

## 사용법

### 1. 사전 조건
- PostgreSQL 데이터베이스가 구동 중이어야 합니다.
- `DATABASE_URL` 환경 변수 또는 `database.py`의 기본값이 올바르게 설정되어야 합니다.
- **반드시 백업을 수행한 후 실행하세요.**

### 2. 마이그레이션 실행
```bash
# conda 환경 활성화
conda activate assy_manager

# 마이그레이션 실행 - normalize_schema.py 는 11-11 은퇴(옛 층 표를 만든 일회용, 갈아엎기 뒤 쓸 곳 없음)
```

### 3. 검증
```bash
# 테스트 실행
python -m pytest server/tests -v
```

## 파일 구성

| 파일 | 설명 |
|---|---|
| `README.md` | 이 문서 |

