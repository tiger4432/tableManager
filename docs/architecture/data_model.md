# 🗄️ Data Model & Layering

> **Status:** 🟢 Living | **Last-verified:** 2026-07-29 (**§2.4 정본 계기 신설** — 완료까지의 상호작용 점수(`InteractionEffortLog` + `crud.get_effort_stats`) 서버 구현 착지, 정의 5결정·커버리지 규율·인덱스 2종 등재. 동시에 §2.3 재교정률을 **보조 계기로 강등** 표기(정의·계약은 무변경). 직전 `0f8d35f` — 제품 소유 4종 중 `map_doe`·`map_doe_source` 폐기 표기) | **Owner:** Backend / Integrity
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
| `InteractionEffortLog` | `interaction_effort_logs` | `transaction_id`(unique), `session_id`, `key_count`, `mouse_count`, `nav_count`, `nav_preserved_count`, `timestamp` | **V1 정본 계기** — tx당 1행, **원시 카운트만**(점수는 조회 시점 계산). 상세 §2.4 |

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

### 2.3 재교정률 (`crud.get_recorrection_stats`) — **보조 계기**

> **⚠️ 2026-07-29 강등: 핵심가치 #1의 계기 자리에서 내려왔습니다.** 정본 계기는 이제 **완료까지의 상호작용**입니다(사용자 확정 — 가치 서술의 정본은 [SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md), 데이터 모델 관점은 **아래 §2.4**). 재교정률은 그 옆의 **간접 증거**로 남습니다.
> **강등 사유 둘** — ① **원인을 분리하지 못한다.** 같은 셀을 두 번 고친 이유가 *화면이 불편해서*(UI 공수)인지 *원본이 틀려서*(데이터 품질)인지 이 지표는 말하지 못합니다. 핵심가치 #1이 재려던 것은 앞쪽인데 지표는 둘을 합쳐 놓습니다. ② **분모 정책 하나로 6.5배 희석된다.** 대량 트랜잭션을 세느냐 접느냐에 따라 **2.01% ↔ 13.13%**로 갈립니다(아래 *행위 단위* 결정이 다루는 것과 같은 축입니다) — 단독으로 회귀를 판단할 근거가 되지 못합니다.
> **아래 정의·계약·함정은 그대로 유효합니다.** 바뀐 것은 지표의 **지위**뿐이고, 집계·응답·표시 계약은 변경 없이 계속 살아 있습니다.

**창 안에서 사람이 쓴 셀 중, 사람이 두 번 이상 쓴 셀의 비율**(낮을수록 좋음). 셀 = `(table_name, row_id, column_name)`. 소비 지점은 `GET /dashboard/summary``recorrection`([backend](./backend.md#재교정률-dashboardsummary--recorrection)).

정의를 지탱하는 4개 결정 — **하나라도 어기면 숫자가 조용히 틀린다**:

| 결정 | 규칙 | 근거 |
|---|---|---|
| 사람 쓰기 식별 | `source_name == crud.USER_SOURCE`(`"user"`, 우선순위 0)로 **양성 선택** | 파서는 **인제션 파일명을 소스명으로** 쓴다 → 자동 소스 값 집합이 열려 있다(2026-07-27 실측 10,750종). 블랙리스트는 원리적으로 불가능 |
| 행위 단위 | 같은 `transaction_id` 안의 중복은 **1회로 접음**(`count(DISTINCT transaction_id)`) | 엑셀 붙여넣기 한 번이 같은 셀을 여러 번 건드린다(실측 643그룹/1,286행). 행 수로 세면 44일 기준 2.96% → 3.88%로 부풀음 |
| 동일값 재기입 | 별도 처리 불필요 — `apply_row_update_internal`의 `has_changed` 가드가 **값이 바뀐 컬럼만** 기록하므로 애초에 로그에 없음(실측 0건). 단 `is_new`는 그 가드를 건너뛰므로 신규 행 생성이 남기는 **`null→null` 행은 분모에서 제외**(실측 4,290행 = 사람이 빈칸으로 둔 컬럼) | 사람이 채우지 않은 칸을 "쓴 셀"로 세면 분모가 부풀어 비율이 낮게 위장됨 |
| 창(window) | `RECORRECTION_WINDOW_DAYS = 7` 고정 | `audit_logs`에는 **보존 정책이 없다**(7일 보존은 `database_outbox` 전용). 전 기간 창이 가능하지만 과거 누적에 희석돼 회귀에 반응하지 않는다 |

**분모(`measured_cells`)는 항상 함께 반환·표시한다.** 표본 8개짜리 "12%"와 5만개짜리 "12%"를 구분할 수 없으면 지표가 아니다.

**스케일**: 전용 부분 커버링 인덱스 `idx_audit_user_recorrection`(`models.AuditLog.__table_args__` + `scripts/setup_db_performance.py` **양쪽에 정의 — 함께 고칠 것**)이 없으면 병렬 Seq Scan으로 떨어진다(2026-07-27 실측 2,628,453행/1.6GB에서 512ms·128,523블록). 부분 술어(`WHERE source_name='user'`)가 planner에 매칭되는 근거는 드라이버가 psycopg2(클라이언트측 파라미터 보간)라 리터럴이 서버에 도달하기 때문이다.

### 2.4 완료까지의 상호작용 점수 (`crud.get_effort_stats`) — 핵심가치 #1의 **정본 계기**

핵심가치 #1 **최소 공수 교정**([SYSTEM_OVERVIEW §1](../overview/SYSTEM_OVERVIEW.md))의 정본 계기(사용자 2026-07-29 교체). **한 교정 트랜잭션을 완료하는 데 사람이 쓴 손의 양**(낮을수록 좋음). 위 §2.3 재교정률은 보조로 강등됐다 — 같은 셀을 두 번 고쳤다는 사실만으로는 원인이 UI 공수인지 데이터 품질인지 갈라지지 않기 때문이다. 이 계기는 그 중간 추론을 건너뛰고 공수를 직접 잰다.

```
점수(tx) = key×w_key + mouse×w_mouse + nav×w_nav + nav_preserved×w_nav_preserved
                                          (기본 배점 1 / 3 / 5 / 0)
```

`nav`는 컨텍스트를 **잃는** 전이, `nav_preserved`는 **유지하는** 전이다. 후자의 기본 배점이 0이므로 **오늘의 점수는 이 항이 없던 때와 완전히 동일**하다 — 그런데도 카운트를 따로 보관하는 이유는 아래 §"분류는 조회 시점 해석"에 있다.

저장은 `models.InteractionEffortLog`(`interaction_effort_logs`), 소비 지점은 `GET /dashboard/summary` → `effort`([backend](./backend.md#상호작용-점수-dashboardsummary--effort)), 배점 선언은 `config/effort_metric.json`([세팅 절차](../guide/config/effort_metric.md)).

⚠️ **이 값은 소급 산출이 불가능하다** — 과거 세션에는 클릭 로그가 없다. 계측이 붙은 시점부터의 데이터만 존재하므로, **교정 표면(UI)을 고치기 전에 확보한 기간이 유일한 "before"다.**

정의를 지탱하는 5개 결정 — **하나라도 어기면 숫자가 조용히 틀린다**:

| 결정 | 규칙 | 근거 |
|---|---|---|
| 측정 단위 | **한 tx 묶음 교정 완료** = `AuditLog.transaction_id` 1건. 새 상관관계 개념을 만들지 않고 서버가 이미 긋고 있는 경계를 재사용 | tx는 이미 "사람의 한 행위"의 경계다(§2.3 재교정률도 같은 경계로 접는다). 별도 단위를 만들면 두 계기가 다른 것을 세게 된다 |
| 미계측 ≠ 0 | `effort`는 **선택 필드**. 없으면 **행 자체를 남기지 않는다**. 절대 0으로 채우지 않음 | 워커·인제션·체인은 같은 엔드포인트를 쓰지만 키보드 앞에 사람이 없다. 0으로 적으면 "공수 0의 완벽한 교정"이 집계에 섞여, **교정 표면이 나빠지는 동안 평균이 0으로 끌려간다** |
| 집계 단위 | **세션별 평균 → 세션 간 평균**(사용자 지정 "세션별 평균") | tx를 통째로 평균하면 한 세션이 500건 처리한 날 그 세션이 전체를 지배한다 — 대량 편집이 UI 개선처럼 보인다. 세션을 먼저 접으면 각 작업 세션이 같은 무게를 갖는다 |
| 원시 카운트만 저장 | 점수 컬럼 없음. 가중치는 **조회 시점**에 곱한다 | 점수를 굳혀 저장하면 배점을 재조정하는 순간 과거가 옛 배점에 갇혀 before/after 비교가 불가능해진다 — 이 계기의 존재 이유가 바로 그 비교다 |
| 화면 이동 판정 | **기본은 상실(5점)**, `context_preserving_transitions`에 **선언된 전이만** 유지로 분류 | 낙관 편향 방지. "웬만한 이동은 컨텍스트가 유지된다"를 기본값으로 잡으면 계기가 공수를 실제보다 낮게 보고하고, 그 편향은 계기를 소유한 쪽에 유리한 방향으로만 작동한다. 목록은 **비어서 출발**하고 항목은 제안·승인으로만 늘어난다. **와일드카드(`*`)는 거절**한다 — 정확 일치로만 판정하므로 무엇도 매칭하지 못하면서 선언한 것처럼 보이는 무력 리터럴이 된다 |
| 분류는 **조회 시점 해석** | 면제된 전이도 **버리지 않고** `nav_preserved_count`로 따로 센다(총괄 addendum 2026-07-29) | 수집 시점에 면제분을 `nav`에서 빼 버리면 그 판단이 저장된 숫자에 **굳어** 되돌릴 수 없다. 이 계기는 소급 산출이 불가능하므로 — 즉 다시 모을 기회가 없으므로 — 분류 오류 하나가 유일한 기준선을 **영구히** 틀리게 만든다. 두 카운트를 다 보관하면 허용목록이 **배점 하나(`nav_preserved`)를 바꾸는 것만으로** 과거까지 재해석된다(가중치 원칙과 동일) |

**`measured_ratio`(계측 tx / 창 안의 전체 사람 tx)는 항상 함께 반환·표시한다.** 계측은 클라이언트가 보내 줄 때만 이뤄지므로 커버리지를 1.0으로 가정할 수 없고, 비율 없는 평균은 **측정되지 않은 범위까지 대표하는 것처럼** 읽힌다(§2.3의 분모와 같은 규율). 분모는 §2.3과 동일하게 `source_name = 'user'` 양성 선택으로 세므로 파서 유입량에 흔들리지 않는다.

- **모집단 정합**: 계측 행은 **그 tx가 사람의 감사 로그를 실제로 남겼을 때만** 기록된다. 그러지 않으면 분자가 분모에 없는 tx를 세어 비율이 1을 넘고, 그 순간 비율은 커버리지가 아니라 잡음이 된다.
- **알려진 편향(정직한 한계)**: 사람이 손을 썼는데 값이 하나도 바뀌지 않은 tx(전부 `has_changed` 가드에 걸린 no-op)의 공수는 **그 tx에** 기록되지 않는다 — 완료된 교정이 없으므로 "완료까지의 공수"라는 단위가 성립하지 않는다.
  - 🚨 **그러나 그 공수를 버려서는 안 된다 (2026-07-29 F1, QA 실측).** 서버가 200을 주면 클라가 카운터를 리셋해 **no-op에 쓴 공수가 소멸**했다. 그 결과 "값이 이미 같아 보이는 셀을 20키+5클릭으로 고치려다 실패하고, 3키+1클릭으로 다시 성공"하는 **제품 최고 마찰 사건이 데이터셋 최저 점수(6, 실제 ~40)로** 기록됐다 — 계기가 잡아내야 할 대상과 역상관. 수리는 **기록 조건이 아니라 응답의 정직성**이다: `PUT`이 `effort_recorded: false`를 돌려주고 클라가 그때 리셋하지 않으면, 그 공수는 **다음(성공) tx에 합산**되어 2회 시도 교정 전체가 하나의 완료 단위로 계측된다([backend 수집 계약](./backend.md#상호작용-점수-dashboardsummary--effort)).
- **재도달 처리**: `transaction_id`는 UNIQUE이며 **첫 기록이 이긴다**. 클라 재시도는 사람이 새로 쓴 공수가 아니다(카운트 필드를 SET 의미론으로 두었다가 마지막 메시지가 총계를 덮어쓴 QA D-1의 재발 방지).

**스케일**: 전용 인덱스 2종 `uq_effort_transaction`(tx당 1행 불변식) + `idx_effort_window`(창 집계 커버링)이 `models.InteractionEffortLog.__table_args__` + `scripts/setup_db_performance.py` **양쪽에 정의 — 함께 고칠 것**. `measured_ratio`의 분모는 **§2.3의 `idx_audit_user_recorrection`을 그대로 재사용**한다(`timestamp` + `INCLUDE transaction_id WHERE source_name='user'`) — 새 감사 인덱스는 필요 없다.

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

> ⚠️ **`map_key_columns`는 `replace_map`이 지울 범위의 정본입니다.** 과거에는 미선언 시 아무것도 지우지 않으면서 200을 내는 무음 no-op이었으나, **2026-07-28(U6)부터 범위를 못 잡으면 400으로 정직하게 거부**합니다(요청에 명시적 `scope` 필드를 실어 범위를 직접 지정할 수도 있고, 응답 `scope: {filters, deleted, inserted}`가 실제 삭제 범위·건수를 알립니다). 맵·계획 저장 테이블에는 반드시 선언하십시오 → [PRIMITIVES](./PRIMITIVES.md) `replace_map`.
