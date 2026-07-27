# 🗄️ Data Model & Layering

> **Status:** 🟢 Living | **Last-verified:** 2026-07-27 (`0f8d35f` — 제품 소유 4종 중 `map_doe`·`map_doe_source` 폐기 표기) | **Owner:** Backend / Integrity
> **Source-of-truth:** `server/database/models.py`, `server/database/crud.py`, `server/config/table_config.json`, `server/product_tables.py`
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
| `GraphNode` | `graph_nodes` | `label`, `identity_key`, `props`(JSONB) | **온톨로지 그래프 노드**. (label,identity_key) UNIQUE — 정확 일치 MERGE |
| `GraphEdge` | `graph_edges` | `type`, `from_node`, `to_node`, `props`, `source_name`, `source_row_ref`, `event_time` | **온톨로지 그래프 엣지**(provenance 포함). (from,type)/(to,type) 인덱스 + (from,type,to,source_name) UNIQUE + `source_row_ref` 인덱스(retarget용) |
| `GraphSyncState` | `graph_sync_state` | `last_outbox_id` | materializer의 outbox 소비 커서(단일 행) |

그래프 3테이블은 `ensure_graph_tables(engine)`(#7 패턴: info_schema 게이트+checkfirst)로 생성되며 `refresh_dynamic_models`에 동승합니다. 승격 흐름은 [event_driven_backend §4](./event_driven_backend.md).

### 1.2 동적 모델 (`init_dynamic_models`)

`table_config.json`의 각 테이블마다 **네이티브 타입 컬럼**을 가진 실제 SQLAlchemy `Table`을 명령형으로 생성:

- 타입 매핑: `number`→Float, `datetime`→DateTime, else String.
- 공용 메타 컬럼: `row_id`(PK), `business_key_val`, `created_at`, `updated_at`.
- 그래프 동기화 플래그: `is_graph_synced`, `needs_graph_rollback`, `graph_synced_at`.
- 신규 컬럼은 이미 매핑된 클래스에 핫스왑되며, `sync_dynamic_tables_schema`가 누락 컬럼에 `ALTER TABLE ADD COLUMN` 발행(기존 테이블 전용).
- **신규 테이블의 물리 CREATE**는 `create_missing_dynamic_tables`(이슈 #7)가 담당하며, 공용 진입점 `refresh_dynamic_models(engine)`가 리로드 3경로(웹서버 reload-configs / config_watcher / 워커 SYSTEM_RELOAD) 전부에 배선되어 있습니다. (함수 앵커: [CODE_MAP §5](./CODE_MAP.md#5-소형-서버-모듈))

---

## 2. 다중 소스 레이어링 (핵심 비즈니스 규칙)

한 셀(table·row·col)은 여러 출처의 값을 동시에 보관합니다. 각 출처는 `CellSource` 한 행. 표시할 "진실된 값"은 우선순위로 결정합니다.

### 2.1 우선순위 규칙 (`crud.compute_priority_value`)

```
SOURCE_PRIORITY = { user: 0, collision_merge: 1, pipeline_parser: 2, custom_script: 3, chain_ingestion: 4 }
# 숫자가 낮을수록 우선
```

1. **수동 핀(manual_priority_source)이 있고 그 소스가 존재하면** → 그 소스가 승자.
2. 아니면 소스들을 우선순위 맵으로 정렬 → 최상위 선택.
3. 테이블별 `source_priority`(table_config) 오버라이드 지원.
4. 반환 `(value, winning_source)`.

서열의 단일 원천은 `crud.resolve_priority_map`/`get_source_priority` — 그래프 materializer의 엣지 provenance 판정도 같은 함수를 씁니다(하드코딩 서열 금지).

즉 **수동 편집(user)은 항상 자동 파서 값보다 우선**하며, 사용자는 특정 소스를 핀 고정해 표시값을 강제할 수 있습니다.

### 2.2 오버라이트 & 시각화

- `CellOverwrite.is_overwrite=True` → 그리드에서 강조(수동 수정 표시).
- `manual_priority_source="collision_merge"` → 충돌 병합 흔적(빨간색 렌더).

### 2.3 재교정률 (`crud.get_recorrection_stats`)

핵심가치 #1 **최소 공수 교정**([SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md))의 계기. **창 안에서 사람이 쓴 셀 중, 사람이 두 번 이상 쓴 셀의 비율**(낮을수록 좋음). 셀 = `(table_name, row_id, column_name)`. 소비 지점은 `GET /dashboard/summary``recorrection`([backend](./backend.md#재교정률-dashboardsummary--recorrection)).

정의를 지탱하는 4개 결정 — **하나라도 어기면 숫자가 조용히 틀린다**:

| 결정 | 규칙 | 근거 |
|---|---|---|
| 사람 쓰기 식별 | `source_name == crud.USER_SOURCE`(`"user"`, 우선순위 0)로 **양성 선택** | 파서는 **인제션 파일명을 소스명으로** 쓴다 → 자동 소스 값 집합이 열려 있다(2026-07-27 실측 10,750종). 블랙리스트는 원리적으로 불가능 |
| 행위 단위 | 같은 `transaction_id` 안의 중복은 **1회로 접음**(`count(DISTINCT transaction_id)`) | 엑셀 붙여넣기 한 번이 같은 셀을 여러 번 건드린다(실측 643그룹/1,286행). 행 수로 세면 44일 기준 2.96% → 3.88%로 부풀음 |
| 동일값 재기입 | 별도 처리 불필요 — `apply_row_update_internal`의 `has_changed` 가드가 **값이 바뀐 컬럼만** 기록하므로 애초에 로그에 없음(실측 0건). 단 `is_new`는 그 가드를 건너뛰므로 신규 행 생성이 남기는 **`null→null` 행은 분모에서 제외**(실측 4,290행 = 사람이 빈칸으로 둔 컬럼) | 사람이 채우지 않은 칸을 "쓴 셀"로 세면 분모가 부풀어 비율이 낮게 위장됨 |
| 창(window) | `RECORRECTION_WINDOW_DAYS = 7` 고정 | `audit_logs`에는 **보존 정책이 없다**(7일 보존은 `database_outbox` 전용). 전 기간 창이 가능하지만 과거 누적에 희석돼 회귀에 반응하지 않는다 |

**분모(`measured_cells`)는 항상 함께 반환·표시한다.** 표본 8개짜리 "12%"와 5만개짜리 "12%"를 구분할 수 없으면 지표가 아니다.

**스케일**: 전용 부분 커버링 인덱스 `idx_audit_user_recorrection`(`models.AuditLog.__table_args__` + `scripts/setup_db_performance.py` **양쪽에 정의 — 함께 고칠 것**)이 없으면 병렬 Seq Scan으로 떨어진다(2026-07-27 실측 2,628,453행/1.6GB에서 512ms·128,523블록). 부분 술어(`WHERE source_name='user'`)가 planner에 매칭되는 근거는 드라이버가 psycopg2(클라이언트측 파라미터 보간)라 리터럴이 서버에 도달하기 때문이다.

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

**어떤 테이블이 있는지는 환경마다 다릅니다** — 이 파일은 gitignored인 현장 자산입니다. 갈리는 기준은 *누가 스키마를 정하는가*입니다.

- **제품 소유**(이름·컬럼을 제품이 정함): `wafer_map_metadata` · `map_split_registry`(M2.6부터 **DOE 그 자체** — 구간·자재가 `bands` JSON 컬럼 안에 있고 `knobs`·`split_desc`는 온톨로지가 소비하므로 평면 컬럼으로 남습니다) · 🗄️ `map_doe` · 🗄️ `map_doe_source`(**DEPRECATED 2026-07-27 — 아무것도 쓰지 않으며, 기존 행 읽기용 선언만 남아 있습니다. 물리 DROP은 운영자 승인 필요**). 정의의 원본은 **`server/product_tables.py` 하나**이며 `.sample`도 거기서 생성됩니다. 사이트 반영은 `server/scripts/install_product_tables.py`(현장 항목 무접촉 병합) → [CONFIG_GUIDE §5.8-ter](../guide/CONFIG_GUIDE.md).
- **현장 소유**: 공장 로그·맵 테이블 전부. `.sample`의 `bonding_map`·`inventory_master`·`production_plan`·`parts`·`large_table_100`은 **동작 예시**일 뿐 표준이 아닙니다.

> ⚠️ **선언되지 않은 컬럼은 저장에서 조용히 드롭되고 HTTP는 200입니다.** `column_types` 게이트가 미선언 컬럼을 버린 뒤 성공을 반환하므로, **컬럼 오타·config 누락이 저장 성공처럼 보입니다**(실제로 `map_doe`가 이 경로로 `eventtime`을 잃었습니다). 2026-07-27부터 `crud`가 **`(테이블, 컬럼)`당 1회** `[Schema]` 경고를 남깁니다(핫패스라 반복은 접고, 테이블당 예산을 넘기면 포화 사실도 1회 알립니다).

> ⚠️ **`map_key_columns` 미선언은 기능 누락처럼 보입니다.** `replace_map` 쓰기가 지울 **범위**를 이 선언에서 잡으므로, 선언이 없으면 아무것도 지우지 않으면서 **똑같이 200을 냅니다**. 맵·계획 저장 테이블에는 반드시 선언하십시오 → [PRIMITIVES](./PRIMITIVES.md) `replace_map`.
