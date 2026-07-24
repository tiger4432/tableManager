# 🗄️ Data Model & Layering

> **Status:** 🟢 Living | **Last-verified:** 2026-07-24 | **Owner:** Backend / Integrity
> **Source-of-truth:** `server/database/models.py`, `server/database/crud.py`, `server/config/table_config.json`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

---

## 1. 저장소: 정적 모델 + 동적 테이블

### 1.1 정적 ORM 모델 (`models.py`)

| 모델 | 테이블 | 핵심 컬럼 | 비고 |
|---|---|---|---|
| `DataRow` | `data_rows` | `row_id`(PK), `table_name`, `business_key_val`, `data`(JSON/JSONB) | **레거시** blob 저장. GIN+trigram 인덱스. 동적 테이블로 대체됨 |
| `AuditLog` | `audit_logs` | `table_name`, `row_id`, `column_name`, `old_value`, `new_value`, `source_name`, `updated_by`, `transaction_id`, `timestamp` | 셀 단위 변경 이력 |
| `DatabaseOutbox` | `database_outbox` | `event_uuid`(unique), `event_type`, `payload`, `status`, `retry_count`, `processed_chain` | 프로세스 간 이벤트(outbox 패턴). PENDING 부분 인덱스 |
| `FileIngestionLog` | `file_ingestion_logs` | `filename`, `filepath`, `table_name`, `status`, `error_message`, `retry_count` | FAILED/SUCCESS/PENDING/PENDING_RETRY |
| `CellOverwrite` | `cell_overwrites` | `table_name`, `row_id`, `column_name`, `is_overwrite`, `updated_by`, `manual_priority_source` | 셀 오버라이트/핀. (table,row,col) unique |
| `CellSource` | `cell_sources` | `table_name`, `row_id`, `column_name`, `source_name`, `value`, `ingested_at`, `updated_by` | **다중 소스 레이어링 저장소**. (table,row,col,source) unique |

### 1.2 동적 모델 (`init_dynamic_models`, models.py:145)

`table_config.json`의 각 테이블마다 **네이티브 타입 컬럼**을 가진 실제 SQLAlchemy `Table`을 명령형으로 생성:

- 타입 매핑: `number`→Float, `datetime`→DateTime, else String.
- 공용 메타 컬럼: `row_id`(PK), `business_key_val`, `created_at`, `updated_at`.
- 그래프 동기화 플래그: `is_graph_synced`, `needs_graph_rollback`, `graph_synced_at`.
- 신규 컬럼은 이미 매핑된 클래스에 핫스왑되며, `sync_dynamic_tables_schema`(:232)가 누락 컬럼에 `ALTER TABLE ADD COLUMN` 발행.

---

## 2. 다중 소스 레이어링 (핵심 비즈니스 규칙)

한 셀(table·row·col)은 여러 출처의 값을 동시에 보관합니다. 각 출처는 `CellSource` 한 행. 표시할 "진실된 값"은 우선순위로 결정합니다.

### 2.1 우선순위 규칙 (`crud.compute_priority_value`, crud.py:148)

```
SOURCE_PRIORITY = { user: 0, collision_merge: 1, pipeline_parser: 2, custom_script: 3 }
# 숫자가 낮을수록 우선
```

1. **수동 핀(manual_priority_source)이 있고 그 소스가 존재하면** → 그 소스가 승자.
2. 아니면 소스들을 우선순위 맵으로 정렬 → 최상위 선택.
3. 테이블별 `source_priority`(table_config) 오버라이드 지원.
4. 반환 `(value, winning_source)`.

즉 **수동 편집(user)은 항상 자동 파서 값보다 우선**하며, 사용자는 특정 소스를 핀 고정해 표시값을 강제할 수 있습니다.

### 2.2 오버라이트 & 시각화

- `CellOverwrite.is_overwrite=True` → 그리드에서 강조(수동 수정 표시).
- `manual_priority_source="collision_merge"` → 충돌 병합 흔적(빨간색 렌더).

---

## 3. 비즈니스 키 & 복합 키

- `business_key` — 테이블의 자연 키 컬럼. `business_key_val`(인덱스 컬럼)에 저장되어 고성능 정렬·업서트 매칭에 사용.
- `composite_key_source` + `composite_key_separator` — 여러 컬럼을 합쳐 복합 비즈니스 키 생성.
  - 예: `bonding_map` = `base_x_y`, `wafer_map_metadata` = `target_table_map_id`.
- `map_key_columns` — 맵 저장(`replace_map`) 시 어떤 행 집합을 purge할지 범위 결정.

---

## 4. 충돌 병합 & 데이터 보존 (Critical)

비즈니스 키 변경으로 두 행이 충돌 병합될 때, 사용자가 수동 수정한 값이 유실되지 않도록 보호합니다.

- 충돌 대상 행에 유효한 사용자 오버라이트가 있고 이번 요청에서 그 셀을 직접 고치지 않았다면 → **기존 값 보존**.
- 원천 소스명은 하드코딩 교체하지 말고 **원본 소스명을 계승**(`_load_metadata_row_cell`).
- 병합 흔적은 `CellOverwrite.updated_by="collision_merge"`로 이중 추적.

전체 규율: [data_preservation_and_signature_change](../guide/data_preservation_and_signature_change.md) **(필독)**

---

## 5. 설정 주도 스키마

`table_config.json`(테이블별): `business_key`, `column_types`, `display_columns`, `composite_key_source`/`separator`, `map_key_columns`, 선택적 `source_priority`. 변경은 `config_watcher.py` + `SYSTEM_RELOAD`로 무중단 반영.

현재 테이블: `bonding_map`, `inventory_master`, `production_plan`, `large_table_100`, `parts`, `wafer_map_metadata`.
