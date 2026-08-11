# 🗄️ Data Model & Layering

> **Status:** 🟢 Living | **Last-verified:** 2026-08-11 (**§2.1 재작성 — 해결 순서가 명시적 전순서가 됐다**: 등재 우선순위 → `ingested_at` 내림차순 → `source_name` 오름차순. 종전 한 줄 `sorted`는 미등재 소스를 전원 99 동점으로 만들었고 stable sort가 **삽입 순서**로 떨어져 **구성상 기존 값이 모든 동점을 이겼다**(격리 `assy_qa` 실측 200/200 — **이 워크스테이션이며 운영 수치 아님**). 🔴 **서열 자체는 한 칸도 안 움직였다**(`user`(0)는 여전히 모든 기계 소스를 이긴다 — 2·3층은 **한 우선순위 안에서만** 동점을 가른다). 신규 **§2.2-ter R3 표시값 재계산** — 승자는 materialise되므로 규칙 수리는 **앞으로 쓰이는 셀만** 고친다. 🔴 **§2.1-ter의 「값 결정은 timestamp를 읽지 않는다」가 그 라운드에 거짓이 됐고 그 자리에 정정을 달았다**(사본 하나는 `backend.md`, 하나는 `CODE_MAP.md`에 더 있었다 — 후자는 code-mapper 소관). ⚠️ **저장 증가는 해결되지 않았다** — 이번 것은 정확성 절반뿐이다. 직전 **§4-bis의 「후보 공간이 4회전×2면」이 거짓이 됐다** — `db1ee42`부터 **4회전 × 2시작모서리**이고 거울은 후보 집합에서 나갔다. `grid_y_invert`를 안 쓰는 이유는 **안 바뀐다**(별칭 상쇄) → [spec/MAP_ALIGNMENT_SPEC §2.4](../spec/MAP_ALIGNMENT_SPEC.md). 직전 **§2.1-quater 신설 — 집합 기반 쓰기 경로(P3). 우선순위 판정은 한 줄도 바뀌지 않았고, 바뀐 것은 배치 경로에서 새 소스 층을 담는 객체가 `LightCellSource`가 됐다는 것 하나다(세션에 안 들어가고 우선순위 계산에만 참여하므로). 문장 301,100 → 1,200, 건수는 전부 동일**). 직전 **§2.1-ter 신설 — 「같은 값을 다시 쓰는 것은 사건이 아니다」가 이제 양쪽 계층에서 참이다**(`87a944e`). 값 계층은 처음부터 `has_changed`로 그렇게 판정했고 **소스 계층만 반대로 말하고 있었다** — 같은 사실에 두 계층이 다른 판정을 내리던 것이 결함이다. `CellOverwrite` 스킵이 `source_unchanged`를 조건에 포함하는 이유(오버라이트 행은 값을 담지 않아 진짜 편집에서도 셋이 같다)와, 그 스킵을 보는 엔드포인트가 없어 전용 그물 없이는 무방비라는 사실이 함께 있다. 직전 **§4-bis 두 문장 정정** — ① 「클라 절반은 아직 없다」가 같은 날 거짓이 됐다: `declaration.js`가 `CONFIRMED`를 싣고 `geometryDeclaration`·`frameFromDeclaration` 두 곳에 분기를 갖는다. **어휘 한 줄로는 부족했고 그 점이 `assumed`와 다르다** — `confirmed`는 **저장되므로** 분기가 없으면 아무도 안 잰 맵이 `declared`로 읽힌다. 아직 안 닫힌 것은 `grid_assumed_from`(클라 철자 0건 — 총괄 판정 대기). ② 「화면 쪽 arm-then-commit이 앞에 선다」가 거짓 — **확정은 한 동작**이고(`02416d4`) 앞에 서는 것은 조작자에게 보이는 절차가 아니라 **중복 전송 가드 셋**이다. 직전 **§2.1-bis 버전 게이트 신설** — `092b83f` `crud.version_gate_verdict`: `table_config`의 `version_column` 선언 시 기계의 기존 행 덮어쓰기를 「버전이 더 클 때만」으로 제한. 🔴 **레이어링 *앞*의 거부권이지 승급권이 아니고**, 그래서 더 높은 버전도 사람의 교정을 밀지 못한다. **선언한 테이블이 아직 없어 전 테이블 무동작**. 직전 **§2.2-bis 레이어 철회 신설** — R2 `chain_replay.withdraw_source`: 셀 레이어 단위 철회로 아래 레이어를 드러냄, `user`·핀 셀은 구조적 거절. 직전 **§5 config 로더·watcher 정정 라운드(H1~H5)** — BOM 인식 디코딩·최상위 타입 게이트·트레일링 엣지 디바운스·`on_created` 등재. 직전 **config→스키마 경로의 조용한 실패 3종 수리(#9/#13/#16ⓐ)** — §1.2에 부팅 스키마 구축이 **import 시점 → 명시적 기동 단계(`main.bootstrap_database_schema`)**로 이동, §5에 watcher `on_moved`(원자적 저장) 처리와 config 파싱 실패 fail-fast 등재. 직전 **§2.4 정본 계기 신설** — 완료까지의 상호작용 점수(`InteractionEffortLog` + `crud.get_effort_stats`) 서버 구현 착지, 정의 5결정·커버리지 규율·인덱스 2종 등재. 동시에 §2.3 재교정률을 **보조 계기로 강등** 표기(정의·계약은 무변경). 직전 `0f8d35f` — 제품 소유 4종 중 `map_doe`·`map_doe_source` 폐기 표기) | **Owner:** Backend / Integrity
> **Source-of-truth:** `server/database/models.py`, `server/database/crud.py`, `server/chain_replay.py`(레이어 철회), `server/config/table_config.json`, `server/product_tables.py`
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
- **부팅 시 물리 스키마 구축은 `main.bootstrap_database_schema()`** — `create_all` + `sync_dynamic_tables_schema`를 묶은 **명시적 기동 단계**이며 `startup_event`가 호출합니다. (2026-07-29 #16ⓐ: 예전에는 `main.py` **모듈 import 시점**에 실행돼, 앱을 import하기만 해도 그때 해석된 `DATABASE_URL`—미설정이면 **운영 DB**—로 DDL이 나갔습니다. 삭제가 아니라 **이동**입니다. 신규 설치가 "config에 테이블 추가 → 기동 → 즉시 사용"으로 테이블을 얻는 경로는 그대로 살아 있어야 하기 때문입니다.) **2026-07-31 완결**: 이동만으로는 부족했습니다 — 남은 방어가 `conftest.py`의 `DATABASE_URL` 핀 하나였고 그것은 테스트 트리 소유라 지우면 함께 사라졌습니다. 지금은 `server/db_safety.py`가 **운영 코드 쪽에서** 거절하며, pytest 프로세스에서는 sqlite 또는 `ASSY_TEST_DATABASE_URL`이 지목한 대상 외에는 **연결조차** 열리지 않습니다(운영에서는 전부 무동작 — `create_all`은 여전히 무가드). 상세는 [architecture/backend §1](./backend.md).

---

## 2. 다중 소스 레이어링 (핵심 비즈니스 규칙)

한 셀(table·row·col)은 여러 출처의 값을 동시에 보관합니다. 각 출처는 `CellSource` 한 행. 표시할 "진실된 값"은 우선순위로 결정합니다.

### 2.1 우선순위 규칙 (`crud.compute_priority_value`) — **순서는 명시적이고 전(全)순서입니다**

```
SOURCE_PRIORITY = { user: 0, collision_merge: 1, pipeline_parser: 2, custom_script: 3, chain_ingestion: 4 }
# 숫자가 낮을수록 우선
```

1. **수동 핀(manual_priority_source)이 있고 그 소스가 존재하면** → 그 소스가 승자(나머지 단계는 아예 돌지 않습니다).
2. 아니면 아래 **세 층**을 차례로 적용해 최상위 하나를 고릅니다.
3. 테이블별 `source_priority`(table_config) 오버라이드 지원.
4. 반환 `(value, winning_source)`.

| 층 | 기준 | 왜 있는가 |
|---|---|---|
| **1** | **등재된 우선순위**(`priority_map`, 미등재 = 99) | **선언된 서열이 권위이고 이 라운드는 그것을 한 칸도 움직이지 않았습니다** — `user`(0)는 여전히 모든 기계 소스를 이기고, 등재된 소스는 여전히 미등재 파일명을 이깁니다. 아래 두 층은 **한 우선순위 *안에서만*** 동점을 가르며, 낮은 서열을 높은 서열 위로 올리지 못합니다 |
| **2** | **`ingested_at` 내림차순**(최신 배달이 승) | 같은 서열이면 **가장 최근 배달이 현재의 사실 진술**이고 그보다 옛 것은 정의상 대체된 것입니다. 🔴 **timestamp를 모르는 층은 가진 층보다 *뒤로* 갑니다** — 레거시 NULL이 날짜 있는 배달을 밀어내지 못하게 하려는 것이고, 이 규칙이 없으면 `None`과 float을 비교해야 합니다 |
| **3** | **`source_name` 오름차순** | **전순서를 완성하는 마지막 층.** 한 배치가 `datetime.now()` 하나로 여러 소스를 쓰면 2층이 동점일 수 있습니다. `idx_sources_lookup_source`가 (table, row, column, source_name)에 UNIQUE이므로 **한 셀 안에서 `source_name`은 유일하고 3층은 항상 결판냅니다** |

🔴 **결과는 호출자가 `sources`를 조립한 순서·그 목록을 만든 SELECT·그 아래 물리 힙 순서 어느 것에도 의존하지 않습니다.** 그것이 전순서를 요구하는 이유의 전부입니다.

> **왜 이렇게 못박아야 했는가 (수리된 결함, 2026-08-11).** 종전 구현은 `sorted(sources.keys(), key=priority_map.get(k, 99))` 한 줄이 전부였습니다. **파일에서 유도된 소스명은 전부 미등재라 모두 99로 떨어져 전원 동점**이 되고, `sorted`는 stable이므로 승자가 **dict 삽입 순서**로 결정됐습니다. 그리고 그 순서는 임의가 아닙니다 — 쓰기 경로는 저장된 층을 먼저 싣고 들어온 층을 **마지막에** 붙이므로(`apply_row_update_internal`), **구성상 기존 값이 모든 동점을 이겼습니다.** 교정된 값을 든 나중 배달은 `cell_sources`에 저장된 뒤 **조용히 버려졌습니다** — 해결값이 안 움직이면 `has_changed`가 거짓이고, 그 가드 하나가 **컬럼 쓰기·감사 로그·아웃박스 이벤트를 한꺼번에** 막기 때문입니다(§2.1-ter).
> **실측(격리 `assy_qa` DB, 2026-08-11 — 이 워크스테이션이며 운영 수치가 아닙니다)**: 서로 **다른 값**을 든 동점 층 둘을 가진 셀 **200개**(전부 `wafer_map_metadata.grid_metadata`)에서 **200/200이 옛 값을 표시**하고 있었습니다. 수리 후 **200/200이 새 값**을 표시하며, `cell_sources`는 **2,432,116행 그대로**입니다 — 층은 하나도 만들어지거나 지워지거나 수정되지 않았습니다.
> ⚠️ **틀린 것보다 나쁜 점은 안정적이지도 않았다는 것입니다** — 동점의 실질 결정자가 물리 힙 순서였으므로, `VACUUM FULL` 하나로 **쓰기도 감사 기록도 없이 표시값이 바뀔 수 있었습니다.**

🔴 **이 수리는 「앞으로 쓰이는 셀」만 고칩니다.** 승자는 **materialise**되어 네이티브 컬럼에 앉아 있고 모든 조회는 층이 아니라 그 컬럼을 읽습니다. 이미 잘못 확정된 셀은 무엇이 다시 배달해 주지 않는 한 영원히 그대로이고, **다시 배달해 줄 그것이 바로 이 결함이 버리던 것**입니다. 이미 쌓인 셀을 고치는 경로는 **§2.2-ter의 R3**입니다.

⚠️ **`ingested_at`은 세 가지 철자로 옵니다** — `{"timestamp": ISO 문자열}`(crud·`main.py`) · `{"ingested_at": datetime}`(`chain_replay.withdraw_source`) · **timestamp를 실을 수 없는 호출자**(`main.fetch_and_merge_metadata` — 그 `sources` 페이로드는 `{소스: 값}` 형태의 클라 대면 계약입니다)를 위한 **out-of-band `ingested_at_by_source=` 맵**. 정규화는 `crud.resolution_ingested_at(entry, source_name=None, ingested_at_by_source=None)` **하나**가 담당합니다 — **세 번째 저장소는 없고**(`cell_sources.ingested_at`이 셋 모두의 유일한 원천), naive/aware datetime은 여기서 UTC로 접힙니다(쓰기 경로는 `datetime.now()`로 naive를 찍고 PostgreSQL `timestamptz`는 aware로 되읽어, 둘을 비교하면 `TypeError`가 납니다).

⚠️ **동점을 가를 수 있으려면 층 목록이 결정적이어야 합니다** — `crud.py`에서 해결기로 흘러가는 `cell_sources` SELECT **다섯 개**에 `ORDER BY source_name`이 붙어 있습니다. 3층이 있으므로 이것이 정확성의 조건은 아니지만, **같은 입력에 같은 진단**을 보장합니다.

서열의 단일 원천은 `crud.resolve_priority_map`/`get_source_priority` — 그래프 materializer의 엣지 provenance 판정도 같은 함수를 씁니다(하드코딩 서열 금지).

즉 **수동 편집(user)은 항상 자동 파서 값보다 우선**하며, 사용자는 특정 소스를 핀 고정해 표시값을 강제할 수 있습니다.

🔴 **이 라운드가 고친 것은 「어느 층이 이기는가」이지 「층이 몇 개 쌓이는가」가 아닙니다.** 저장 증가(같은 셀에 재사용되지 않는 소스명이 계속 쌓이는 문제)는 **해결되지 않았습니다** — 스케줄 수집기는 매 실행마다 타임스탬프가 박힌 새 파일명을 만들고 그것이 곧 새 `source_name`이 됩니다(`server/run_auto_update.py`). 후보 설계(피드 신원 / 값 신원 등)는 `agent_workspace/reports/Cell_sources_growth_diagnosis.md` §6에 분석돼 있고 **어느 것도 구현되지 않았습니다.**

### 2.1-bis 버전 게이트 (`crud.version_gate_verdict`) — 레이어링 **앞의 거부권** · 2026-08-04 `092b83f`

`table_config.json`에 `"version_column"`을 선언한 테이블은, **기계가 이미 있는 행을 덮어쓸 때** 「들어온 버전 > 저장된 버전」일 때만 그 행을 고려합니다. 선언이 없으면 판정 함수가 첫 줄에서 돌아가고, 그런 테이블의 동작은 이 기능 이전과 **완전히 같습니다**(last-write-wins).

🔴 **게이트는 거부권이지 승급권이 아니고, 그것이 「버전은 계층 *안에서만* 순서를 매긴다」의 전부입니다.** 게이트를 통과한 행도 셀 하나하나가 §2.1의 `compute_priority_value`를 그대로 지나가므로, **더 높은 버전이 사람이 고친 셀을 밀어내는 일은 구조적으로 없습니다.** 통과 시점에 페이로드를 행에 강제로 얹는 구현(「버전이 권위」의 그럴듯한 과대 해석)은 다음 인제션에 사람의 교정을 조용히 되돌리며, `server/tests/test_version_gated_overwrite.py::test_human_correction_survives_a_newer_version`이 그 순간 빨개지도록 있습니다.

- **판정 단위는 행이고, 시점은 행 확정 직후·첫 셀을 건드리기 전**입니다. 셀 단위 판정이었다면 낡은 행의 일부 컬럼만 받아들여 **내부적으로 모순된 행**을 만듭니다 — 통째로 받거나 통째로 거절하는 편이 낫습니다. 거절된 행은 `changed_cols`가 비어 값·`CellSource`·`AuditLog`·브로드캐스트 어느 것도 남기지 않습니다.
- **비교는 값에서 정해지고 텍스트 비교가 아닙니다**(`crud.parse_version_key`가 `(kind, sortable)` 쌍을 반환). `column_text_sql`/`TEMPORAL_TEXT_FORMAT`을 **일부러 쓰지 않습니다** — 그것들은 SQL 술어용 텍스트 렌더링이고, 텍스트야말로 버전을 잘못 정렬합니다(`'10' < '9'`). 재사용한 것은 그 뒤의 **추론**입니다: ISO-8601 순간은 순서가 있고 임의 텍스트는 없으며, aware 값은 UTC로 접힙니다. **양쪽 `kind`가 다르면 코에르션하지 않고 거절**합니다.
- **모름은 과거도 미래도 아닙니다.** 들어온 버전의 부재·공백·해석 불가·종류 불일치는 각자의 이름(`version_missing` / `version_unorderable`)으로 **거절**됩니다. 반대로 **저장 측**에 쓸 수 있는 버전이 없으면 들어온 값을 **채택하고 행을 씁니다**(`row_version_absent`) — 되돌아갈 과거가 없고, 양쪽 모두에 엄격하면 그 테이블이 수동 백필 뒤에 영원히 갇히기 때문입니다.
- **생성은 덮어쓰기가 아니고**(첫 도착은 막지 않습니다), **`user` 소스는 게이트에 닿지 않습니다**(그리드 편집은 셀 하나만 담고 버전 컬럼을 담지 않으므로, 게이트를 태우면 그 테이블이 사람에게 읽기 전용이 됩니다).
- **로그는 행마다 찍지 않습니다** — (테이블, 사유)당 프로세스 첫 목격에 WARNING 1회 + 배치당 INFO 1회(사유별 건수). 인제션 드롭 가시화와 같은 모양입니다.

🔴 **파생 쓰기는 버전 컬럼을 들고 오지 않습니다.** 체인 워커·체인 재적용 R1·결손 보정 자동 확정은 자기 매퍼/룰이 만든 컬럼만 쓰므로, **버전 게이트를 건 테이블이 동시에 파생 타깃이면 그 파생 쓰기가 기존 행에 대해 전부 `version_missing`으로 거절**됩니다(부재 행만 만드는 `map_meta_registrar`와 새 신원만 만드는 `enrichment_backfill`은 영향 없음). 운영자 관점의 확인 절차·명령은 [guide/config/table_config §7.2](../guide/config/table_config.md)가 정본입니다.

### 2.1-ter 같은 값을 다시 쓰는 것은 사건이 아니다 — **양쪽 계층에서** · 2026-08-06 `87a944e`

값 계층은 처음부터 이렇게 판정하고 있었습니다. `apply_row_update_internal`의 `has_changed` 가드는 해결된 값이 그대로면 **네이티브 컬럼 쓰기·`AuditLog`·아웃박스 이벤트·`updated_at` 갱신을 모두 억제**합니다(§2.3의 「동일값 재기입」 항목이 그 결과를 세고 있습니다 — 실측 0건).

🔴 **어긋나 있던 것은 소스 계층입니다.** `CellSource`는 `value`·`updated_by`가 완전히 같아도 셀-컬럼마다 무조건 다시 기록했고, `CellOverwrite`도 같았습니다. **같은 사실에 대해 두 계층이 서로 다른 판정을 내리고 있었던 것이 결함이고**, 그 대가는 PostgreSQL이 물었습니다 — `ON CONFLICT DO UPDATE`는 **새 튜플 버전을 씁니다**. 즉 「지우지 말고 upsert하자」는 순진한 수리는 삭제를 갱신으로 바꿀 뿐 dead tuple을 그대로 만듭니다(실측: 2,000셀 무변경 재-Push에서 삭제 24,000 → 갱신 24,000).

지금은 `value`와 `updated_by`가 그대로면 두 계층 모두 건드리지 않습니다.

- ⚠️ **`CellOverwrite` 쪽 스킵 조건에는 소스 쪽 판정(`source_unchanged`)이 **포함**됩니다.** 오버라이트 행은 플래그·작성자·핀만 담고 **값을 담지 않으므로**, 값이 진짜 바뀐 셀에서도 그 셋은 동일합니다. 그것만 보고 스킵하면 **진짜 사용자 편집에서 `updated_at` 갱신이 멈춰**, 다른 코드가 화면에 보여 주는 컬럼의 뜻이 조용히 바뀝니다. 없앨 부담은 어차피 「안 바뀐 셀」에만 있으므로 바뀐 셀은 종전 동작 그대로입니다.
- **`ingested_at`의 뜻이 정확해졌습니다** — 「누가 마지막으로 저장을 눌렀나」가 아니라 **「이 소스가 이 값을 마지막으로 세운 때」**. 움직이지 않는 timestamp가 아니라, **아무것도 안 바뀌었는데 움직이던 timestamp가 거짓말이었습니다.**
  - 🔴 **[2026-08-11 정정] 이 항목의 마지막 문장이 거짓이 됐습니다.** 종전에는 *「값 결정은 timestamp를 읽지 않으므로(`compute_priority_value`는 우선순위 맵만 정렬) 승자가 바뀌는 셀은 없습니다」*라고 적었고, **그때는 참이었습니다.** 지금은 `compute_priority_value`가 **같은 우선순위 안의 동점을 `ingested_at` 내림차순으로 가릅니다**(§2.1 2층) — 즉 이 컬럼은 **표시값 결정에 직접 참여**합니다. 그리고 두 변경은 **같은 방향**으로 맞물립니다: 무변경 재기입에서 timestamp를 안 움직이는 이 스킵이 없었다면, 아무것도 바꾸지 않은 재-Push가 **동점 판정을 뒤집었을** 것입니다. 「값이 그대로면 이 소스가 그 값을 세운 때도 그대로」라는 뜻이 2층의 전제입니다.
- 🔴 **`cell_overwrites.updated_at`을 노출하는 엔드포인트가 없습니다.** 그래서 `/sources`를 보는 기존 단언은 이 스킵을 **볼 수 없고**, 전용 그물(`test_an_unchanged_cell_does_not_rewrite_its_overwrite_marker` — `db_session`으로 직접 조회)이 없으면 이 자리는 무방비입니다. 실제로 그 그물을 쓰기 전, 스킵을 제거하는 변이(mutation)를 스위트 전체가 **한 건도 잡지 못했습니다.**

### 2.1-quater 집합 기반 쓰기 경로 — 레이어링은 그대로, 문장만 사라진다 · 2026-08-07 P3

대용량 인제션에서 배치 쓰기가 **행마다 3문장**(신원 SELECT 둘 + 데이터 INSERT 하나)을 내던 것을 **청크 단위**로 접었다. 실측(격리 `assy_qa`, 100,000행 맵 파일 — **이 워크스테이션이며 운영이 아니다**): 문장 **301,100 → 1,200**, 벽시계 **796.2s → 375.8s**. 절차는 [architecture/backend §3 2-ter](./backend.md)가 정본이고, 여기 적는 것은 **레이어링에 무엇이 바뀌었고 무엇이 안 바뀌었나**다.

- **우선순위 판정은 한 줄도 바뀌지 않았다.** `compute_priority_value`도 `resolve_priority_map`도 `SOURCE_PRIORITY`도 그대로다. 바뀐 것은 **그 판정에 들어가는 소스 목록을 어떻게 얻는가**뿐이다.
- 🔴 **바뀐 것: 배치 경로에서 새 소스 층을 담는 객체가 매핑 인스턴스가 아니라 `LightCellSource`다.** 그 객체는 **세션에 들어가지 않는다** — 실제 쓰기는 `cell_sources_to_upsert` 누산기에서 나가고, 이 객체는 `col_srcs`에 끼어 `compute_priority_value`에 참여하려고만 존재한다. 프리페치가 채우는 `sources_cache`는 **원래부터** `LightCellSource`였으므로 오히려 한 목록에 두 종류가 섞이던 것이 정리됐다. `CellOverwrite`도 같다(`LightCellOverwrite`).
  ⚠️ **누산기가 없는 호출자(비배치 경로)에서는 여전히 매핑 인스턴스다** — 거기서는 그 객체가 **곧 쓰기**이기 때문이다. 조건은 `cell_sources_to_upsert is None` 하나이고, 그 조건을 지우면 비배치 쓰기가 조용히 아무것도 저장하지 않는다.
- **`cell_sources` 업서트의 문장 모양은 같고 보내는 방식만 다르다** — 문장을 한 번 컴파일하고 파라미터 목록을 넘긴다. `BULK_CHUNK_SIZE` 청킹은 그대로다(그것은 튜닝값이 아니라 int16 파라미터 한계다). 균일하지 않은 키 집합이나 값에 든 SQL 식은 `_is_executemany_safe`가 걸러 **종전 경로로 되돌린다**.
- **감사·아웃박스·오버라이트 마커의 건수는 동일하다** — 10만 행 실측에서 `cell_sources` 700,000 / `audit_logs` 100,000 / `database_outbox` 100,000이 변경 전후 같다. 아웃박스는 `session.new`에서 나오므로 **ORM을 우회하는 벌크 삽입은 이 경로에서 금지**이고, 그것이 데이터 행을 끝까지 ORM으로 만드는 이유다.

### 2.2 오버라이트 & 시각화

- `CellOverwrite.is_overwrite=True` → 그리드에서 강조(수동 수정 표시).
- `manual_priority_source="collision_merge"` → 충돌 병합 흔적(빨간색 렌더).

### 2.2-bis 레이어 철회 (`chain_replay.withdraw_source`) — 2026-07-30 · R2

지금까지 레이어 스택은 **추가만** 가능했다. R2가 **한 소스의 기여를 되돌리는** 유일한 경로를 추가한다 — 행이 아니라 **셀 레이어** 단위다.

- `cell_sources` 행 **하나**를 삭제하고, 남은 소스로 `compute_priority_value`를 재계산해 표시값을 되쓴다. 소스가 둘이었다면 **아래 레이어가 드러나고 구멍이 남지 않는다.** (행 삭제·컬럼 NULL 처리는 다른 소스의 기여까지 파괴하므로 하지 않는다.)
- H2-b(그래프의 `_retarget_stale_edges`: 소스가 과거에 주장했으나 더는 주장하지 않는 것은 남겨두지 않고 적극 제거)를 **셀 버전 단위로 옮긴 것**이다.
- 🔴 **사람 값을 지울 수 있는 경로가 없다 — 두 거절이 그것을 보장한다**: ⓐ `user` 소스 철회는 **거부**(priority 0은 "사람이 입력했다"의 유일한 의미) ⓑ 그 소스를 사람이 핀한 셀(`CellOverwrite.manual_priority_source`)은 **건너뛰고 이유를 남긴다**(핀은 "이 소스를 보여 달라"는 사람의 선택).
- **무음이 아니다**: 표시값이 바뀐 셀마다 `AuditLog`에 소스 `chain_replay_withdraw` · `updated_by="withdraw:<소스명>"` · old/new가 남는다. 클라의 기존 셀 이력 타임라인이 그것을 읽으므로, 빈칸을 발견한 운영자가 **어느 소스가 사라졌는지** 확인할 수 있다.
- 절차·CLI 정본은 [guide/chain_ingestion_guide §5.4](../guide/chain_ingestion_guide.md).

### 2.2-ter 표시값 재계산 (`chain_replay.recompute_display_values`) — 2026-08-11 · R3

**승자는 materialise됩니다.** `apply_row_update_internal`은 마지막에 `setattr(row, col, new_val)`을 하고, 이후의 모든 조회는 **층이 아니라 그 컬럼**을 읽습니다. 그래서 §2.1의 해결 규칙을 고쳐도 **그 뒤에 쓰인 셀만** 고쳐집니다 — 이미 잘못 확정된 셀은 무엇인가가 다시 배달해 줄 때까지 그대로이고, **다시 배달해 줄 그것이 바로 결함이 버리던 것**입니다. R3는 셀이 **이미 가지고 있는 층들**로 `compute_priority_value`를 다시 돌려 **materialise된 컬럼만** 고칩니다.

- 🔴 **`cell_sources` 행을 하나도 만들지 않고, 지우지 않고, 고치지 않습니다.** 움직이는 것은 표시 컬럼뿐입니다. R1은 **매퍼**를 다시 돌리고(룰이 필요하고 새 층을 씁니다), R2는 **주장을 지웁니다** — 둘 다 「저장된 층 중 무엇이 이기는가」를 **저장된 것을 바꾸지 않고** 다시 답하지 못합니다. 그것이 세 번째 연산이 필요했던 이유입니다.
- 🔴 **층이 2개 미만인 셀은 절대 건드리지 않으며, 이것은 최적화가 아니라 안전 속성입니다.** 층이 하나면 가를 동점이 없어 애초에 이 결함의 피해자가 될 수 없고, 층이 **0개**면 해결 결과가 `(None, None)`이라 **다른 쓰기 경로가 소유한 컬럼을 이 패스가 비워 버립니다.** 이 관문이 「전체 테이블 실행이 자기가 이해하지 못하는 데이터를 파괴할 수 없다」의 근거입니다.
- **무음이 아닙니다.** 표시값이 움직인 셀마다 `AuditLog`에 `source_name="resolution_recompute"` · `updated_by="resolved:<이긴 소스명>"` · old/new가 남습니다. 클라의 **기존 셀 이력 타임라인**이 그것을 읽으므로 값의 변화가 어디서도 설명되지 않는 일이 없습니다 — **기록 없이 바뀌는 값**은 지금 수리 중인 결함과 같은 계급이므로 감사 쓰기는 선택 사항이 아니고, `--apply`는 **둘 다 하거나 둘 다 안 합니다.**
- **사람의 핀은 존중됩니다.** 핀은 **어느 층이 이기는가**를 정하는 것이지 materialise된 컬럼을 얼리는 것이 아니므로, 핀이 걸린 셀은 **핀이 지목한 층의 값으로** 해결됩니다. 보고서의 `pinned_changed`는 「핀을 무시했다」가 아니라 **「화면이 사람이 고른 층에서 멀어져 있었고 그것을 되돌렸다」**입니다.
- **신규 이벤트 타입도 신규 화면도 만들지 않습니다** — R2와 같은 자세로, 가시성은 **이미 있는 이력 타임라인** 하나로 충족합니다. ⚠️ **다만 「아웃박스 행을 하나도 안 만든다」고는 적지 않습니다** — `setattr`이 동적 테이블 행을 dirty로 만들고 `database.auto_stage_database_outbox`는 **모든 세션에 걸린 전역 `before_flush`**라, 커밋 시 행마다 `EDIT` 이벤트가 실릴 것으로 읽힙니다(정적 판독이며 **측정하지 않았습니다** — 총괄 확인 대기). 운영자 관점의 안전한 문장은 **「즉시 갱신을 약속하지 않는다 · 안 바뀌어 보이면 새로고침」**입니다.
- **기본은 dry-run이고 `--apply`만 씁니다.** 페이지 단위 커밋 + 키셋 순회(`keyset_scan.iter_pages`)라 대량 실행을 중간에 끊어도 됩니다. **dry-run이 곧 열거**입니다.
- 절차·CLI 정본은 [guide/chain_ingestion_guide §5.5](../guide/chain_ingestion_guide.md), 운영자 진입점은 [guide/BACKFILL_GUIDE §2.5](../guide/BACKFILL_GUIDE.md).

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

### 2.5 감사 이력(Audit History) 인덱스 — 최근 패널 discovery + 행/셀 페이징 · 2026-08-11 `dab9152`+`2630790`

`AuditLog`(§1.1)는 셀 단위 변경 이력을 무제한으로 쌓는 테이블이고, 그것을 훑는 세 경로(전역 최근 패널·행 이력·셀 이력)를 상한 짓는 인덱스 셋이 이 라운드에서 새로 생겼다. 셋 다 `models.py`의 `AuditLog.__table_args__`에 선언돼 있어 **신규** 데이터베이스는 `create_all`로 자동으로 받지만, `create_all`은 **기존** 테이블에 인덱스를 추가하지 않으므로 이미 떠 있는 배포는 마이그레이션을 손으로 한 번 돌려야 한다 → [DEPLOY_SETUP §6 8-ter](../guide/DEPLOY_SETUP.md) · 게이트 판정 [PRODUCTION_READINESS C4](../process/PRODUCTION_READINESS.md).

| 인덱스 | 정의 | 파일 | 크기(실측) | 무엇을 지키는가 |
|---|---|---|---|---|
| `idx_audit_recent_groups` | `("timestamp", id) INCLUDE (transaction_id)` | `add_audit_recent_groups_index.sql` | 166 MB / 60.1 B/행 (2,900,000행 픽스처, `CONCURRENTLY` 4.2초 빌드) | `/audit_logs/recent`의 discovery 걸음 — `transaction_id`를 leaf에만 실어 세 컬럼 조회를 **Index Only Scan**으로 만든다(200,000행 걸어도 heap 방문 0) |
| `idx_audit_row_history` | `(table_name, row_id, "timestamp", id)` | `add_audit_history_keyset_indexes.sql` | 19–91 MB(운영 규모 210,196행 대 픽스처 1,131,008행, ~170–195 B/행 — 폭은 `row_id` UUID 36자가 두 인덱스 각각에 반복되는 데서 온다) | 행 이력 페이지 — 이게 없으면 300,019행짜리 행 이력 조회가 `LIMIT 201`을 걸어도 전량 bitmap scan + top-N 정렬(9,421 buffers/121.6ms) |
| `idx_audit_cell_history` | `(table_name, row_id, column_name, "timestamp", id)` | `add_audit_history_keyset_indexes.sql` | (위와 합산 실측) | 셀 이력 페이지 — 행 인덱스만 있으면 `column_name`이 행 범위 안의 **Filter**로 남아, 300,019행짜리 행 안의 1건짜리 컬럼도 "페이지가 찰 때까지 걷기"가 된다(9,421 buffers/117.7ms → 5 buffers/0.09ms) |

- **셋 다 ASC로 선언한다** — 조회는 `timestamp DESC, id DESC`이지만 btree는 역방향 스캔 비용이 같고, ASC라야 `models.py`가 raw SQL 없이 선언할 수 있어 PostgreSQL과 테스트용 SQLite 양쪽을 한 선언으로 덮는다.
- **셋 다 `CONCURRENTLY`** — 라이브 스택에 쓰기 락 없이 반영 가능하지만 트랜잭션 블록 안에서 부를 수 없다(`psql -f` 자동커밋으로 실행). 중단되면 `INVALID` 인덱스가 쓰기 비용만 남기고 아무 읽기도 못 받으므로, 각 마이그레이션 파일 하단의 확인 SQL로 `indisvalid`를 재대조한다.
- 🔴 **인덱스 온리 스캔은 visibility map을 전제한다** — 대량 인제션 직후 새 페이지가 아직 all-visible이 아니면 `idx_audit_recent_groups`도 `Heap Fetches: N`을 내며 느려진다(같은 최초 콜이 이 인덱스를 만든 이유이므로 결함이 아니라 **VACUUM 전 정상 상태**다. 실측 1,956ms → VACUUM 후 612ms, 같은 인덱스·같은 상한).
- 행값(row-value) 비교 `(timestamp, id) < (ts, id)`를 `OR` 전개(`timestamp < ts OR (timestamp = ts AND id < id)`)로 "단순화"하지 말 것 — 논리는 같지만 플랜이 갈린다. PostgreSQL이 `OR` 전개에서는 경계를 btree에 밀어넣지 못해 **Filter**로 떨어지고 이미 본 행을 처음부터 다시 걷는다(같은 페이지 실측: Index Cond 18 buffers/0.114ms 대 Filter 2,311 buffers/4.949ms).

---

## 3. 비즈니스 키 & 복합 키

- `business_key` — 테이블의 자연 키 컬럼. `business_key_val`(인덱스 컬럼)에 저장되어 고성능 정렬·업서트 매칭에 사용.
- `composite_key_source` + `composite_key_separator` — 여러 컬럼을 합쳐 복합 비즈니스 키 생성.
  - 예: `bonding_map` = `base_x_y`, `wafer_map_metadata` = `target_table_map_id`.
- `map_key_columns` — 맵 저장(`replace_map`) 시 어떤 행 집합을 purge할지 범위 결정.

### 3.1 「업무 키 하나에 행 하나」는 **데이터베이스가 강제한다** · 2026-08-07 D3

종전에는 아무것도 강제하지 않았다. 2026-08-07 실측: `business_key_val`을 가진 25개 테이블에 그 컬럼을 언급하는 인덱스가 **50개인데 `indisunique`는 0개**였고, 유니크/PK 제약도 0개였다. 유일성은 **쓰기 경로가 먼저 조회했기 때문에** 우연히 성립하고 있었을 뿐이다.

그 우연이 깨지는 자리는 측정됐다 — `apply_batch_updates`의 프리페치는 **자기 세션의 루프에 대해서만** 부재를 증명하므로, 다른 OS 프로세스가 그 창 안에서 같은 키를 커밋하면 **한 업무 키에 두 행이 조용히** 생긴다(실제 프로세스 둘·운영 청크 1,000건·창 2.4초로 재현. 근거: `agent_workspace/reports/Server_M2_race_reachability.md`). 프로세스 간 락은 없다 — `grep -rn "pg_advisory" server/`가 0건이다.

- **인덱스**: `server/migrations/add_business_key_unique_index.py`가 테이블별 `uq_bk_<table>` UNIQUE 인덱스를 `CONCURRENTLY`로 만든다. **`models.py`에 선언하지 않는다** — `create_all`은 이미 있는 테이블에 인덱스를 추가하지 않으므로, 중복이 쌓일 수 있는 바로 그 데이터베이스들에서 조용한 무동작이 된다(`idx_sources_by_source`와 같은 계급의 함정).
- **NULL은 그대로 여러 개 허용된다.** PostgreSQL의 평범한 UNIQUE 인덱스는 NULL을 서로 다르게 보고, `create_empty_rows_batch`는 업무 키 없는 행을 만든다. `NULLS NOT DISTINCT`로 바꾸면 「빈 행 추가」가 두 번째 클릭부터 실패한다.
- **회복**: `crud.apply_batch_updates`가 이제 `IntegrityError`를 잡는다(`_is_business_key_unique_violation` — SQLSTATE 23505 + 제약 이름이 `uq_bk_` 접두일 때만). 롤백 후 배치를 재실행하면 **새 READ COMMITTED 스냅샷의 프리페치가 상대가 커밋한 행을 보므로** 그 행에 병합된다. 별도의 병합 코드는 없다 — **재실행 자체가 병합**이고, 신원 해석기는 여전히 하나다.
  🔴 **회복은 이름이 붙고 로그에 남는다**(`[BK Conflict Recovered]`). 조용한 재시도는 보이지 않는 실패를 다른 보이지 않는 실패로 바꾼다. 상한(`BK_CONFLICT_MAX_RETRIES`)을 넘기면 `[BK Conflict Unresolved]`로 **거절한다** — 진짜 중복 신원은 영원히 재시도할 대상이 아니다.
  ⚠️ **롤백의 대가 하나**: `ingestion_checkpoint.record_chunk_progress`가 같은 세션에서 미리 낸 오프셋 UPDATE도 함께 사라진다. 결과는 그 모듈이 이미 문서화한 열화(다음 크래시 시 그 청크 재처리, 업서트가 멱등이라 유실 아님)다.

### 3.1-bis 업무 키를 못 구한 행은 **빈 문자열이 아니라 NULL을 받는다** · 2026-08-07

`business_key_val`은 모든 쓰기 경로가 **「전에 본 행인가」를 판정하는 유일한 수단**이다. 종전에는 키 컬럼이 비어 온 행이 전부 **같은** 신원(`''`)을 지고 저장됐다. 🔴 **빈 문자열은 NULL과 달리 「값」이다** — 그래서 이것은 중복 행 문제가 아니라 **충돌** 문제이고, 3.1의 UNIQUE 인덱스는 그 충돌을 **장애**로 바꾼다.

이 워크스테이션에서 실 PostgreSQL로 실측(2026-08-07 — **시뮬레이션이지 운영이 아니다**). 키 컬럼이 비어 온 5행을 3회 push:

| | UNIQUE 인덱스 없음 | UNIQUE 인덱스 있음(3.1 적용 후) |
|---|---|---|
| 종전 (`''`) | 5 → 10 → 15행, 전부 키 `''` 하나 | **0 → 0 → 0행. 매 push가 `IntegrityError`로 거절된다** |
| 현재 (NULL) | 5 → 10 → 15행 | 5 → 10 → 15행 (NULL은 서로 다르므로 충돌 없음) |

🔴 **인덱스 있음 칸의 0행이 이 절이 존재하는 이유다.** `''` 다섯 개는 **한 트랜잭션 안에서 서로** 충돌하고, 3.1의 `IntegrityError` 회복은 「롤백 → 새 스냅샷으로 재조회 → 상대가 커밋한 행에 병합」이라 **아무도 커밋한 적 없는 충돌**을 풀 수 없다. 재실행이 같은 충돌을 재생산하고 `BK_CONFLICT_MAX_RETRIES` 소진 후 배치가 통째로 거절된다. **키 컬럼이 빈 파일 하나가 그 테이블의 인제션을 통째로 멈춘다** — 시끄럽게, 그러나 멈춘다.

- **수정 위치는 한 곳**: `crud._update_row_business_key`. 키 컬럼이 공백이면 `''` 대신 **NULL**을 쓴다(기존 키가 있었다면 함께 지운다 — 종전 `''` 동작과 같고 철자만 바뀐다). 복합 키 경로는 원래부터 NULL을 썼다.
- **NULL이 옳은 표적인 이유**: 평범한 UNIQUE 인덱스에서 PostgreSQL은 NULL을 서로 다르게 본다(3.1이 `NULLS NOT DISTINCT`를 **쓰지 않는** 이유가 이것이다). 게다가 키 없는 행이 이미 다른 곳에서 갖는 모양이다 — `create_empty_rows_batch`가 NULL을 쓰고, 그리드는 그런 행을 `row_id`로 다룬다. 실 DB에도 이미 있다(2026-08-07 실측: 수동 병합이 만든 `wafer_map_metadata` 11행 · `production_plan` 10행). 이 행들은 인덱스를 막지 못한다.
- 🔴 **자리표(placeholder)를 만들지 않는다.** 이 라운드의 초안은 그런 행에 `UNKEYED::<row_id>`를 찍었고 **제품 소유자가 기각했다** — *「키 없는 행은 인제션 될 일 없고 손으로만 다룸」*. 자리표의 값어치는 **나중의 인제션이 그 행을 알아보게** 하는 것인데, 여기서는 그 값을 걷어 갈 사람이 없다. 수동 작업은 행을 `row_id`로 지목하므로 `business_key_val`에 손잡이가 필요 없다. ⚠️ **다음에 여기에 합성 신원을 넣고 싶어지면 먼저 답할 질문은 「그걸 누가 읽는가」다.**
- 회귀 그물: `server/tests/test_blank_business_key_is_null.py`.

### 3.2 PK 컬럼에 `index=True`를 붙이지 않는다 · 2026-08-07 D3

`Column(..., primary_key=True, index=True)`는 PK가 이미 만드는 UNIQUE btree와 **키·opclass·collation이 같은 두 번째 인덱스**를 만든다. 쓰기마다 유지되고 읽는 곳은 없다. 2026-08-07 실측: **29개, 382.3MB**(최대 `ix_cell_sources_id` 314MB vs `cell_sources_pkey` 314MB).

선언은 **다섯**이었고 그중 하나가 26개를 만들었다 — `AuditLog.id` · `FileIngestionLog.id` · `CellOverwrite.id` · `CellSource.id`, 그리고 동적 테이블 공용 `Column("row_id", String, primary_key=True)`. ⚠️ **이 수는 세 번 틀렸다가 맞았다**(처음 셋 → 넷 → 실측 다섯/29개). **클래스를 하나씩 읽는 방식으로는 이 외연이 안 나온다** — 카탈로그에 술어를 먹여 세어야 한다. 구성원을 이름으로 적는 이유도 같다: 기수는 목록의 사본이라 낡는다.

정리는 같은 마이그레이션의 `--drop-redundant`가 한다. 대상은 하드코딩 목록이 아니라 `pg_index` 질의로 **매번 다시 증명**한다 — `indkey`·`indclass`·`indcollation`·**`indoption`**(정렬 방향·NULLS 위치)·access method가 PK 인덱스와 **전부** 같고, 부분·표현식·INVALID가 아닐 것. 🔴 **`indoption`을 빼면 `(a, b DESC)` 인덱스가 평범한 `(a, b)` PK의 사본으로 판정된다** — 역방향 스캔은 키 전체를 뒤집으므로 혼합 정렬을 대신하지 못하고, 이것이 이 스크립트에서 **재실행으로 되돌릴 수 없는 유일한 결과**(운영에서 멀쩡한 인덱스를 지움)다. 그 위에 이름 관문이 하나 더 있다 — SQLAlchemy 자동 생성형 `ix_*`가 아니면 **보고만 하고 두고 간다**.

**`setup_db_performance.py` Step 3.5와의 경계**: 저쪽은 `database_outbox` 인덱스 **넷을 이름으로** 지운다. 그중 PK 사본은 `ix_database_outbox_id` **하나뿐**이고 나머지 셋(`event_uuid`·`status`·`processed_chain`)은 **부분 인덱스로 대체됐거나 조회처가 없어서** 지우는 것이라 이 절의 판정식에 걸리지 않는다. 즉 **계급의 정본은 이쪽(D3)**이고 Step 3.5는 그 계급 밖의 셋을 마저 처리하는 자리다. 겹치는 하나는 어느 쪽이 먼저 돌아도 무해하다(둘 다 `IF EXISTS`·멱등).

---

## 4. 충돌 병합 & 데이터 보존 (Critical)

비즈니스 키 변경으로 두 행이 충돌 병합될 때, 사용자가 수동 수정한 값이 유실되지 않도록 보호합니다.

- 충돌 대상 행에 유효한 사용자 오버라이트가 있고 이번 요청에서 그 셀을 직접 고치지 않았다면 → **기존 값 보존**.
- 원천 소스명은 하드코딩 교체하지 말고 **원본 소스명을 계승**(`_load_metadata_row_cell`).
- 병합 흔적은 `CellOverwrite.updated_by="collision_merge"`로 이중 추적.

전체 규율: [data_preservation_and_signature_change](../guide/data_preservation_and_signature_change.md) **(필독)**

---

## 4-bis. 좌표계 확정 기록 (`frame_confirmation` · 맵 정렬 스펙 §0.2 층 ⑧)

[MAP_ALIGNMENT_SPEC](../spec/MAP_ALIGNMENT_SPEC.md)의 사슬 `좌표계 확정 → 소스 얼라인 → 다이 맵 확정 → 본딩 계획`에서 **쓰는 층은 하나**이고, 그 하나가 이 기록입니다. 사람이 「이 설비·제품의 좌표계는 이것이다」라고 정한 사실을 남깁니다.

| 테이블 | 단위 | 내용 |
|---|---|---|
| `frame_confirmation` | `(rule_name, unit_key, version)` | 머리 — **확정된 프레임(`frames` JSON + 주체 `confirmed_frame`/`map_table`/`x_col`/`y_col`/`value_col`)**, 기준(공통 바닥), `map_alignment` 판정 근거(개수만), 최약 기여자, 누가·언제, `superseded_by`/`supersedes_uid`, **`geometry_assumed`** |
| `frame_confirmation_source` | 소스 하나에 한 행 | **소스 목록** + 소스별 적용 프레임과 **시프트(dx, dy)** + 근거 개수 + 제외 사유 + **`geometry_basis`** |
| `cell_sources.confirmation_uid` | 셀 | 파생 도장 — 「이 셀은 어느 확정 아래에서 만들어졌나」. NULL이 기존 전 행의 상태 |

**소유자**: `server/frame_confirmation.py`(쓰기는 `record_confirmation` 하나) · 라우트 `POST /api/maps/alignment/confirm` · 모델 `server/database/models.py` · 스키마 `server/migrations/add_frame_confirmation.py` + `server/scripts/setup_db_performance.py` Step 3.10 · 회귀 그물 `server/tests/test_frame_confirmation.py` + `server/tests/test_frame_confirmation_meta.py`(2026-08-06 [D7]).

🔴 **결정 단위에 컬럼명을 적지 않습니다.** 단위의 정본은 규칙의 `decision_key` 선언이고, 저장은 `rule_name` + `unit_key`(그 규칙 파생 테이블의 `business_key_val`과 **같은 조립**: 선언된 `composite_key_separator`로 join) + `decision_key` JSON입니다. `dt_eqp`·`product` 컬럼은 첫 선언의 흔적으로 남아 있을 뿐 신규 코드의 단위가 아닙니다(추가 전용 규율이라 지우지 않고 NULL 허용으로 물러났습니다). 확정 대상도 마찬가지로 규칙의 `target_fields` 밖이면 거절합니다.

🔴 **확정된 값에도 컬럼명을 적지 않습니다 (2026-08-06, [D-1] 수정).** **결정키 절반만 일반화돼 있었습니다** — 단위는 `decision_key` JSON으로 물러났는데 **확정값은 `core_frame`·`dt_frame` 두 컬럼 그대로**였고, 그 두 이름은 첫 규칙(`eqp_product_frame_attribution`)의 `target_fields`입니다. 다른 이름을 선언한 규칙의 답은 갈 곳이 없어 **NULL로 들어가고 라우트는 200을 냈습니다**(실측 2026-08-06, 라이브 라우트: `dt_job_lot_slot_attribution`(`target_fields = dt_lot_confirmed, dt_slot_confirmed`) 확정이 `core_frame=None, dt_frame=None`으로 기록). 「무엇을 확정했나」가 빈 확정은 **거절된 확정보다 나쁩니다 — 완료로 보이기 때문입니다.**

- **정본은 `frames` JSON**(`{target_field: 프레임}`)입니다. `decision_key`와 **같은 이유·같은 모양**입니다. `core_frame`·`dt_frame`은 `dt_eqp`·`product`와 **같은 계급의 흔적 컬럼**으로 물러났고 그 규칙일 때만 채워집니다(추가 전용 규율이라 지우지 않습니다).
- 🔴 **확정의 주체는 「어느 좌표를 정렬했나」입니다** (제품 소유자 판정 2026-08-05: 「`CORE FRAME`은 **이름**이고 단위는 `CORE_X`/`CORE_Y`/`C_BN`」). 그래서 `confirmed_frame` + `map_table` + `x_col`/`y_col`/`value_col`이 머리에 있습니다. **클라(`client2/src/map2/api.js`)는 이 넷을 처음부터 보내고 있었고 라우트가 하나도 읽지 않았습니다** — 화면으로 만든 확정은 전부 주체가 빈 채로 남았습니다. `value_col`의 NULL은 결함이 아니라 점유 전용 실행입니다.
- ⚠️ **아무 프레임도 명명하지 않은 확정은 거절입니다.** `frames`도 비고 `frame`도 없으면 400이고, 선언된 이름에 빈 답을 붙여도 거절입니다(이름만으로는 무엇을 확정했는지 말하지 못합니다).
- ⚠️ **기존 테이블 확장 컬럼은 마이그레이션 순서 의존이 있습니다** — `migrations/add_frame_confirmation.py`(추가 전용·멱등, `decision_key JSONB`와 같은 방식)를 **조회 프로세스보다 먼저** 돌려야 하고, `server/tests/test_system_schema_drift.py`의 `SYSTEM_TABLE_COLUMNS`에 마이그레이션 이름과 함께 등재돼 있습니다. **구성원은 여기 세지 않습니다** — 정본은 그 파일의 `ALTER TABLE frame_confirmation ADD COLUMN` 문장들이고, 개수를 적으면 다음 추가에서 조용히 어긋납니다(실제로 어긋났습니다).
- 🔴 **이 순서 의존은 추상적 위험이 아닙니다 (실측 2026-08-06).** `reference_cell_count`·`thresholds_defaulted`가 마이그레이션 없이 모델에만 들어간 상태에서, 이 박스의 `frame_confirmation` 전체 엔티티 조회가 `UndefinedColumn`으로 죽었습니다 — **그 두 컬럼을 읽지 않는 코드까지 전부**(SQLAlchemy가 모든 SELECT·INSERT에 매핑된 컬럼을 전부 이름 대므로 테이블이 통째로 내려갑니다). 컬럼을 모델에 더하는 라운드는 같은 라운드에 이 마이그레이션을 늘려야 합니다.

🔴 **`ruling_state`는 `/view`가 **응답 최상위**에 싣는 값입니다 (2026-08-06, [D-2] 수정).** `map_alignment.build_alignment_view`는 판정 상태(`scored`/`no_winner`/`not_scorable`)를 응답의 `state`에 싣고 **`ruling` dict 안에는 넣지 않습니다.** 그런데 쓰기 경로는 `ruling["state"]`를 읽었고, 라우트 문서와 클라(`client2/src/map2/decode.js:243`)는 둘 다 「`ruling`을 그대로 넘겨라」였습니다 — 지시대로 하면 상태가 **통째로 사라지고** 어휘에 없는 낱말 `unscored`가 기본값으로 들어갑니다. 실측 2026-08-06: `winner=rot0_front`, `margin=87`인 판정의 기록이 `ruling_state=unscored`. **한 행이 「채점 안 됨」과 「승자는 rot0_front」를 동시에 주장했습니다.**

- 상태는 이제 요청의 **최상위 `state`**로 받습니다(`/view`가 두는 자리와 같은 자리 — 화면의 전사 규칙은 「`ruling`을 복사하고 `state`를 복사한다」 두 줄입니다).
- 안 왔고 판정이 **승자를 지명했으면** `scored`입니다. **유도가 아니라 전사입니다** — `build_alignment_view`가 화면의 상태를 정하는 첫 분기가 정확히 `if ruling.get("winner")`이고 같은 입력에 같은 식을 씁니다.
- 안 왔고 승자도 없으면 **모른다고 말합니다**(`frame_confirmation.STATE_NOT_TRANSPORTED`). 판정만으로는 `no_winner`와 `not_scorable`이 갈리지 않습니다(`no_candidate_scored` 하나가 양쪽 갈래에서 다 납니다). 여기서 표를 만들어 찍으면 그것이 **두 번째 판정 구현**입니다. 🔴 이 낱말은 `map_alignment.STATE_*`의 구성원이 **아닙니다** — 저쪽은 「채점이 무엇을 말했나」이고 이것은 「그 말이 여기까지 왔나」라, 다른 질문을 같은 집합에 넣으면 소비자가 판정으로 읽습니다.
- 🔴 **자기 판정과 어긋나는 상태는 거절합니다.** 승자를 지명한 판정은 정의상 채점된 판정이고, 「채점 안 됨 + 승자 있음」은 명시로 도착한다고 참이 되지 않습니다.
- ⚠️ **어휘의 정본은 `map_alignment` 하나입니다** — `frame_confirmation.accepted_ruling_states()`가 거기서 읽습니다(`_ASSUMED`·`bonding_plan`의 BINDING_* 블록과 같은 규율). 여기 철자를 복사하면 화면이 본 낱말과 기록된 낱말이 갈리는 날 양쪽 다 멀쩡해 보입니다.

🔴 **`POST /api/maps/alignment/confirm`은 이 사슬에서 데이터베이스에 쓰는 유일한 요청입니다.** (2026-08-06 [D7]부터 그 한 요청이 **표 두 개**에 씁니다 — 확정 기록과 `wafer_map_metadata`, **한 트랜잭션**으로. 아래 [D7] 문단이 그 계약의 정본입니다.) 같은 일을 하는 GET이 없고(404), 읽기 경로(`/api/maps/alignment/view`)에는 부작용이 없습니다. 🔴 **[2026-08-06 정정] 종전 이 문장은 「화면 쪽 arm-then-commit이 앞에 선다」로 끝났고 그것은 이제 거짓입니다** — **확정은 한 동작**(확정 버튼 클릭 또는 `Enter`)이고 무장 단계도 두 번째 확인창도 없습니다(제품 소유자 판정 2026-08-06, `02416d4`). 앞에 서는 것은 **중복 전송 가드 셋**(`preventDefault` · `confirmInFlight` · 재렌더 시 disable)이고, 그것은 조작자에게 보이는 절차가 아니라 **같은 한 번의 누름이 두 번 나가지 않게 하는 장치**입니다 — 셋이 겹치므로 「정확히 한 번 썼다」 단언 하나로는 셋을 함께 채점할 수 없어 각자 자기 단언을 갖습니다. **판정(`ruling`)과 소스 목록은 요청이 명시적으로 실어 옵니다** — 쓰기 경로가 재채점하면 조작자가 보고 결정한 것과 기록된 것이 갈릴 수 있고, 기록해야 하는 것은 조작자가 본 쪽입니다. 응답은 만들어진 기록 전체(`confirmation_uid`·`version` 포함)라 화면이 다시 조회할 필요가 없습니다. **WS 브로드캐스트는 없습니다**(총괄 결정 2026-08-05 — 듣는 쪽이 아직 없고 별도 결정입니다).

⚠️ **거절은 전부 무쓰기 경로입니다** — 결정키 미완·미선언 결정키·미선언 확정 대상·소스 없음·주체 없음·없는 규칙·**프레임 미명명**·**빈 프레임 값**·**미선언 판정 상태**·**판정과 어긋나는 상태**(뒤 넷은 2026-08-06 [D-1]/[D-2]). 소스 목록이 반쯤 들어간 확정은 목록이 있다고 주장하면서 틀린 목록을 주므로 없느니만 못합니다.

🔴 **enrichment 규칙을 대체하는 것이 아니라 그 위에 얹습니다.** 확정의 **몸짓**은 `enrichment_rules.json`의 `eqp_product_frame_attribution`이 이미 갖고 있고(판단 단위가 정확히 `(dt_eqp, product)`, 사람 확인 경로, `auto_confirm` 스윕과 dry-run, `reference_views`의 후보 제시, `cell_overwrites`가 나르는 누가·언제) 그것을 그대로 씁니다. 그 경로가 **담을 수 없는 셋만** 여기서 담습니다:

1. **소스 목록** — `eqp_frame_attribution`의 bk는 `dt_eqp|product` 하나라 단위당 한 행이 영원히 한 행입니다. N개 소스는 N행이 필요하고, 한 셀에 JSON으로 접으면 기여자가 뭉개져 §2의 최약 기여자 계산이 시작되기 전에 불가능해집니다.
2. **소스별 정렬** — `map_alignment.score_candidates`는 소스 맵마다 `(프레임, dx, dy)`를 **풉니다**. 스칼라 `target_fields` 둘은 프레임 하나씩만 담고 시프트를 담을 자리가 없습니다. **시프트는 장식이 아닙니다** — 0이 아닌 시프트를 버리면 다이가 통째로 밀립니다.
3. **판(version)** — 결정적입니다. `idx_sources_lookup_source`가 `(table, row, column, source_name)` UNIQUE라 재확정은 같은 셀을 제자리에서 덮어씁니다. 셀 이력 테이블은 없고 `audit_logs` 행은 가리킬 수 있는 대상이 아닙니다. 파생 행이 「내가 어느 확정 아래에서 만들어졌나」를 가리키려면 안정된 식별자가 있어야 합니다.

🔴 **도장을 `source_name`에 철자하지 마십시오.** `frame_confirm:<uid>` 쪽이 자연스러워 보이지만 틀립니다 — `crud.get_source_priority`는 정확 일치 dict 조회이고 미등재는 99이므로, 확정마다 새로 나는 이름은 `SOURCE_PRIORITY`에 미리 등재될 수 없습니다. 도장 찍힌 셀이 전부 `custom_script`·`chain_ingestion` 아래로 가라앉아 **도장이 자기가 도장한 값을 강등**합니다. 확정은 값을 공급하지 않고 값이 계산된 **프레임을 지목**합니다 — 다른 축이므로 다른 컬럼입니다.

🔴 **최약 기여자는 두 번째 규칙이 아닙니다.** `frame_confirmation.weakest_contributor`는 `graph_materializer`가 셀 레이어 진실을 고를 때 쓰는 것과 **같은 식**(`max(..., key=(priority, name))`)이고 둘 다 `crud.get_source_priority`에 도달하므로 서열의 원천이 하나입니다. 넷 중 하나가 미확정이면 그 확정도 미확정입니다(스펙 §0.2 ⑨).

⚠️ **이 기록은 재파생을 하지 않습니다.** 어느 줄을 다시 만들지는 이미 `frame_trigger_scope`+`SCOPE_ROW_CAP` · `chain_replay` R1/R2 · `plan_retraction` 셋이 풀어 놓았고 **넷째 철자를 만들지 않습니다**. `derived_cell_scope`는 그 셋이 범위로 쓸 셀 집합을 **질의로만** 돌려주며, 회수는 그대로 `chain_replay.withdraw_source`입니다. `superseded_by`도 삭제가 아니라 포인터입니다 — 지난 판과 그 아래 파생 셀은 남습니다.

✅ **층 ⑨(계획)가 이 기록을 읽습니다 (2026-08-05).** 읽는 자리는 `bonding_plan.canonical_basis` **하나**이고 `bonding_plan.get_core_summary`와 `transfer_plan._canonical_origin_meta`가 같은 함수를 부릅니다(한쪽만 읽으면 같은 웨이퍼가 M1·M2에서 다른 수치를 냅니다). 조회는 `frame_confirmation.live_confirmation_for_maps`로, **단위를 `(설비, 제품)`으로 되짚지 않습니다** — 계획의 신원은 `(lot, slot)`이고 되짚으려면 계획이 `dt_log`의 컬럼명을 알아야 하는데 그것은 「결정 단위에 컬럼명을 적지 마라」와 정면으로 어긋납니다. 대신 확정이 **스스로 적어 둔 사실**(어느 맵들을 합쳤는가)로 묻습니다. `excluded_reason`이 붙은 기여자는 답이 되지 않습니다 — 제외된 소스는 어디에도 정렬되지 않았으므로 그 판의 기준을 자기 근거라고 주장할 수 없습니다.

⚠️ **퇴화형은 폴백으로 남습니다** — 확정이 없는 단위는 종전대로 `bonding_plan.CANONICAL_FRAME_ROLES`(설정 순서 첫 역할)로 기준을 고르고, **그 사실을 응답의 `frame_basis`가 말합니다**(조용히 확정과 같아 보이면 안 됩니다). 계약과 중간 등급 `connected(not_declared)`는 [spec/MAP_EDITOR_SPEC §6.2-ter.2](../spec/MAP_EDITOR_SPEC.md)가 정본입니다. 🔴 **인덱스가 하나 더 늘었습니다** — `idx_frame_conf_src_map`(`source_table`, `map_id`)이 층 ⑨의 조회 방향이며, `idx_sources_confirmation`과 같은 계급으로 **`models.py`와 마이그레이션 두 곳**에 선언돼 있습니다.

⚠️ **인덱스는 두 곳입니다** — `idx_sources_confirmation`은 `models.py`와 `migrations/add_frame_confirmation.py`에 선언돼 있고 **둘 다 고쳐야 합니다**(`create_all`은 기존 테이블에 인덱스를 만들지 않습니다). `idx_sources_by_source`와 같은 계급입니다.

🔴 **`geometry_assumed` / `geometry_basis` — 「이 판은 무엇을 참이라 치고 나왔나」** (2026-08-05, 맵 정렬 스펙 [§9.1](../spec/MAP_ALIGNMENT_SPEC.md)). 규격 선언이 없는 소스 맵은 이제 **기준 맵의 웨이퍼 치수를 빌려** 채점될 수 있습니다. 빌린 값은 어디에도 저장되지 않지만 **그 위에서 나온 판정은 선언된 기하 위에서 나온 판정과 다른 사실**이고, 확정을 기록하는 이유 자체가 「나중에 그 가정이 거짓으로 밝혀지면 **어느 결정이 그 위에 서 있었나**」에 답하기 위해서입니다 — `cell_sources.confirmation_uid`와 같은 논거입니다.

- 머리의 `geometry_assumed`(BOOLEAN)는 **기여자 행들의 롤업**이고 부분 인덱스 `idx_frame_conf_assumed`가 그 질문 하나를 답합니다(가정 없는 판이 쌓여도 안 자랍니다). `weakest_source`와 같은 계급 — **저장된 계산이지 두 번째 규칙이 아닙니다.**
- 🔴 **요청이 이 값을 실어 오지 않습니다.** `record_confirmation`이 쓰기 시점에 유도합니다(`map_alignment.geometry_basis_of`). 클라가 보내면 그것이 같은 사실의 두 번째 철자이고, **낡은 클라 하나가 이 기록의 존재 이유를 통째로 흘립니다.** 이것은 「쓰기 경로에서 재채점하지 마라」와 어긋나지 않습니다 — 채점이 아니라 이미 DB에 있는 사실을 읽는 것이고, 질의는 **테이블마다 한 번**(+ 바닥 한 번)입니다.
- 🔴 **유도 규칙에는 축이 둘입니다** (맵 정렬 스펙 [§9.5-bis](../spec/MAP_ALIGNMENT_SPEC.md), 2026-08-05). 「제외되지 않았는데 자기 기하가 선언이 아니면 빌린 기하 위에 선 것」은 빌림의 입구가 조건 하나이던 시절의 규칙이고, 지금은 **phys를 선언한 맵이 격자만 빌려** 통과할 수 있습니다. 그래서 읽는 사실은 **그 맵의 메타 · 제외됐는가 · 바닥의 메타**입니다(**수를 적지 않습니다**)(격자를 빌렸는지는 소스 메타에 없고 소스와 바닥의 **차이**에만 있습니다). 바닥을 못 읽으면 phys 축만 보는 옛 답으로 퇴화합니다 — 바닥 조회 실패가 확정 기록 전체를 죽이지는 않습니다.
- ⚠️ **제외된 소스는 `assumed`가 아닙니다.** 어디에도 정렬되지 않았으므로 자기 토큰(`auto_registered`·`absent`…)을 그대로 갖습니다 — 일어나지 않은 일에 근거를 붙이면 이 컬럼이 답해야 할 질문의 답이 부풀려집니다.

🔴 **확정은 `wafer_map_metadata`까지 갑니다 — 사슬의 종점이고, 이것이 §9.1의 금지를 뒤집었습니다** (2026-08-06, 제품 소유자 확정, 맵 정렬 스펙 [§9.7](../spec/MAP_ALIGNMENT_SPEC.md)). 종전에 사슬은 이 표에서 끊겼고, 바로 위 문단의 「빌린 값은 어디에도 저장되지 않지만」은 **그 절반이 더 이상 참이 아닙니다.**

- **근거가 금지보다 셉니다**: 유효 다이 맵은 **제품 규격마다 다르므로**, 어떤 소스 맵이 특정 유효 다이 맵과 **일치한다**는 것은 같은 제품 규격이라는 뜻이고 따라서 웨이퍼·칩 기하가 같습니다. **일치가 곧 증거**이고, 제품별 기준에 대고 맞춰 본 정렬은 가정이 아니라 **파생**입니다. 금지가 막던 것은 **표지 없는** 빌림이었고 그 금지는 지금도 유효합니다.
- **일곱 번째 토큰 `confirmed`** — 서열은 `declared`와 `assumed` **사이**입니다. `geometry_computable`은 근거로 받아들이고 `geometry_declaration`은 **`declared`가 아니라고** 답합니다(이 맵을 잰 사람은 없습니다). 🔴 **이 토큰이 없으면 확정이 관측 불가능해집니다 — 실측입니다**: 씨앗 단위의 확정 승자가 `rot0_front`, 즉 정확히 무증거 삼중항이라 표지 없이 쓴 행은 **아무도 손대지 않은 맵의 행과 바이트 동일**합니다.
- **키는 둘입니다** — `phys_confirmed_from`(웨이퍼·칩 기하) / `frame_confirmed_from`(회전·면). 각각 `{table, map_id, confirmation_uid, confirmed_by, confirmed_at}`을 싣습니다. **`confirmation_uid`가 이 파생을 다시 검사 가능하게 만들고, 확정 없이 파생이 일어난 것처럼 읽히지 않게 하는 것도 그 키입니다.** 하나로 합치면 phys를 선언한 맵의 프레임만 확정한 경우에 거짓말이 됩니다(`grid_assumed_from`을 가른 것과 같은 이유).
- 🔴 **`grid_y_invert`는 쓰지 않습니다.** 후보 공간이 **4회전×2시작모서리**(2026-08-08 `db1ee42` — 종전 「4회전×2면」은 거짓이 됐습니다. 거울은 후보 집합에서 나갔고 면은 전부 `front`입니다)이고 y반전은 별칭으로 상쇄돼 **아무것도 그것을 채점하지 않습니다**. 확정된 프레임은 그 맵에 이미 적혀 있는 y반전에 **상대적으로** 표현된 것이라, 덮어쓰면 확정된 회전·면의 뜻 자체가 바뀝니다. 기존 행에서는 손대지 않고, 새 행에서는 어느 표지에도 덮이지 않아 `indeterminate`가 됩니다.
- 🔴 **격자는 채점에서 옵니다.** 정렬이 돈 격자는 그 맵의 셀이 아니라 **바닥에서 빌린 것**이고, 새로 합성하면 채점이 쓴 적 없는 프레임을 기록하게 됩니다. 철자는 `map_alignment.confirmed_meta_for` 하나이며 채점이 부르는 바로 그 함수들을 부릅니다. 격자를 쓰는 것은 **행을 새로 만들 때뿐**입니다(확정된 사실이 아니라, 행이 격자 없이는 읽히지 않아서 싣습니다).
- 🔴 **잰 phys는 덮지 않습니다.** 그 맵의 기하가 `declared`면 프레임만 기록합니다 — `assume_phys_from`의 거절과 **같은 조건**이라 같은 술어를 씁니다.
- 🔴 **머리 행·소스 행·메타 행이 한 트랜잭션입니다 — 규율이 아니라 구조로.** `crud.apply_batch_updates`가 무조건 커밋하고 그 세션이 아직 안 커밋된 확정 머리를 들고 있는 그 세션이라, 커밋 하나가 셋을 함께 내보냅니다. `record_confirmation(commit=False)`로 부르면서 메타를 쓰라는 요청은 **조용히 둘로 갈리는 대신 거절**합니다(`ValueError`).
- 🔴 **쓰기 서열은 `user`입니다.** 사람의 결정이고(`confirmed_by`), 그보다 낮게 쓰면 `custom_script`가 써 둔 셀이 이겨 **아무것도 안 바뀐 채 200이 나갑니다** — [D-1]이 방금 고친 실패의 같은 형태입니다. ⚠️ **그 서열의 대가 하나**: `user` 쓰기는 그 셀의 `manual_priority_source`를 해제합니다(2026-06-02 규칙). 확정은 규격 셀의 핀을 **조용히 풉니다** — 통제군 대조 결과 평범한 `user` 쓰기와 동작이 동일하므로 확정 고유의 파괴가 아니지만, 조작자에게는 메시지가 없습니다. 조작자용 서술은 [guide/data_preservation §3](../guide/data_preservation_and_signature_change.md)입니다. 업무 키는 `map_meta_registrar.meta_business_key` **한 철자**를 등록기와 공유합니다(두 철자면 재확정이 맵 하나를 두 행으로 쪼갭니다 — 실측).
- 🔴 **확정된 기하는 다시 빌리지 않습니다.** `phys_needs_basis`가 묻는 것은 「선언인가」가 아니라 「빌려야 하는가」이고, 다시 빌리면 값은 그대로인 채 표지만 `assumed`로 덮여 **확정 다음 조회가 확정 이전과 구별되지 않습니다.** 같은 술어를 `geometry_basis_of`와 목록의 `usable_map_count`/`assumable_map_count`도 씁니다.
- **소유자·회귀 그물**: `server/map_overlay.py`(어휘·표지·`geometry_declaration`/`geometry_computable`/`orientation_declaration`) · `server/map_alignment.py`(`confirmed_meta_for`·`phys_needs_basis`·`geometry_basis_of`) · `server/frame_confirmation.py`(`_write_confirmed_meta`) · `server/tests/test_frame_confirmation_meta.py`.
- ✅ **[2026-08-06 갱신] 클라 절반이 같은 날 착지했습니다.** 🔴 **종전 이 줄은 「클라 절반은 아직 없습니다 — `DECLARATION_TOKENS`에 `confirmed`가 없고 `decode.js`의 `token()`은 모르는 토큰을 `null`로 접습니다」였고, 서버 레인이 그것을 쓴 시점에는 참이었습니다.** 지금 `client2/src/map2/declaration.js`는 `CONFIRMED`를 내보내고 `DECLARATION_TOKENS`·`COMPUTABLE_TOKENS`에 싣습니다.
  - 🔴 **어휘 한 줄로는 부족했고, 그 점이 `assumed`와 다릅니다.** `assumed`는 서버 메모리에만 사는 표지라 클라는 **단어만 알면** 됐지만 `confirmed`는 **저장되므로** 클라가 확정된 메타를 DB에서 그대로 읽습니다 — `geometryDeclaration`에 분기가 없으면 아래 phys 여섯 값이 읽히므로 `declared`로 떨어져, **아무도 재지 않은 맵을 두고 「누가 쟀다」고 말합니다.** 그래서 분기는 `geometryDeclaration`(`phys_confirmed_from`)과 `frameFromDeclaration`(`frame_confirmed_from` → `rotation`·`side`만) **두 곳**에 있습니다.
  - 🔴 **표지 존재 판정이 양쪽에서 같은 뜻이어야 합니다** — 서버는 `if m.get(KEY):`이고 파이썬 `bool({})`은 거짓인데 JS `!!{}` 는 참입니다. `confirmed_meta_for`가 `dict(mark or {})`로 끝나므로 **빈 표지 `{}`는 실제로 나올 수 있는 모양**이고, 클라가 `!!`로 썼다면 서버가 무표지로 취급하는 바로 그 행에서 갈립니다. 클라 `markerPresent()`가 그 규칙을 맞춥니다(채점 `contracts/map2_seam/vectors.json`의 `empty_marker_is_inert`).
  - ⚠️ **아직 안 닫힌 것 하나 — `grid_assumed_from`에는 클라 철자가 없습니다.** 서버 `orientation_declaration`은 그 표지를 읽어 `grid_start_x/y`에 `assumed`를 답하는데 클라에는 분기가 없어 **`declared`로 돌아옵니다**(빌림이 선언을 사칭 — 위 `confirmed`와 같은 결함 계급). 실측 2026-08-06: `grid_assumed_from`이 있고 `grid_start_x: 4`인 메타가 서버 `{4, assumed}` / 클라 `{4, declared}`. 클라 소스에 기록돼 있고 **총괄 판정 대기**입니다.
- ⚠️ **두 컬럼 모두 NULL이 「아니오」가 아니라 「모름」입니다.** 이 어휘가 생기기 전에 남은 판은 그 질문을 받은 적이 없습니다. 기본값을 두면 옛 행들이 묻힌 적 없는 질문에 답하게 됩니다.
- ⚠️ **시스템 테이블 컬럼 추가는 마이그레이션 없이는 그 테이블 전체를 죽입니다** — 두 컬럼은 `migrations/add_frame_confirmation.py`에 있고 `server/tests/test_system_schema_drift.py`의 `SYSTEM_TABLE_COLUMNS`에 마이그레이션 이름과 함께 등재돼 있습니다.

---

## 5. 설정 주도 스키마

`table_config.json`(테이블별): `business_key`, `column_types`, `display_columns`, `composite_key_source`/`separator`, `map_key_columns`, 선택적 `source_priority`. 변경은 `config_watcher.py` + `SYSTEM_RELOAD`로 무중단 반영.

### 5.0-bis 다른 config가 좌표/키 컬럼을 생략하면 `table_config`에서 상속한다 · 2026-08-11 `68db020`

`map_overlay_config.json`의 `table_bindings`와 `ontology_mapping.json`의 `node.identity`는 둘 다 이 파일의 `map_key_columns`/좌표 선언을 **또 요구할 필요가 없다** — 키를 생략하면 **키마다** `local declaration > table_config에서 파생 > 이름을 대며 거절` 순서로 판정된다(관례 상수로 조용히 대체하던 것은 삭제). `ontology_config`는 자체 좌표 유도 로직을 갖지 않고 `map_overlay.derive_binding_parts`를 그대로 호출하므로, **그래프와 맵이 구조적으로 같은 답**을 낸다(둘이 따로 계산해서 우연히 같은 답이 아니다). `ontology_mapping.json`은 신규 키 `@map_key_columns`를 얻었고, `node.identity`를 아예 생략하면 그 자체가 "상속하라"는 뜻이다.

- **예외**: `val`(값 컬럼)은 상속하지 않는다 — 좌표가 선언된 맵에서 `val`을 생략하는 것은 "이 맵은 값이 없다"는 적극적 선언이라, 상속하면 occupancy 맵이 조용히 value 맵으로 뒤집힌다.
- **검증**: 이미 완전히 선언된 19/19 라이브 테이블은 `resolve_binding`/`resolve_binding_info` 응답이 이 변경으로 한 글자도 안 움직인다.
- 상세 메커니즘·함정은 [PRIMITIVES §3](./PRIMITIVES.md)의 「키를 지우면 상속한다」 항목 · 엔드포인트 계약은 [backend §2](./backend.md) `GET /api/maps/paint-rules`의 `binding` 필드 · 세팅 절차는 [CONFIG_GUIDE](../guide/CONFIG_GUIDE.md)의 `map_overlay_config.json`/`ontology_mapping.json` 행.

> **watcher가 처리하는 저장 형태**(🔴 **수를 적지 않습니다 — 아래 목록이 정본입니다**) (2026-07-29 #9/H2/H3). `on_modified`(제자리 쓰기) · `on_moved`(같은 디렉터리 temp + rename) · `on_created`(**다른** 디렉터리 temp + rename — 이 경우 `moved`가 아예 없고 `deleted`+`created`만 옵니다. `tempfile.mkstemp()`의 기본이 시스템 temp 디렉터리라 흔한 형태입니다). 측정 기준 watchdog 6.0.0/Windows.
>
> 그리고 디바운스는 **트레일링 엣지**입니다 — 이벤트마다 타이머를 재무장하고 **마지막 이벤트 후 1초**에 1회 발화합니다. 예전 리딩 엣지(창 안 첫 이벤트만 처리)는 ⓐ **0.3초 간격의 두 번째 저장을 통째로 버렸고**(디스크는 3컬럼, 물리 테이블은 2컬럼, 로그는 성공) ⓑ 느린 비원자적 쓰기의 **완료 이벤트**를 버렸습니다(첫 이벤트가 잘린 파일을 읽고 abort). ⓑ는 `crud.update_table_config`가 평범한 `open(w)`이라 **제품 자신의 쓰기 경로**였습니다.
>
> ⚠️ **여전히 참인 것**: 반영은 마지막 쓰기로부터 약 1초 뒤이고, **물리 반영의 증거는 `information_schema`뿐**입니다(`GET /tables/{t}/schema`는 config 싱글턴을 읽습니다). 반영이 불가능하면 `Config reload ABORTED: ...` ERROR를 남기고 기존 상태를 유지합니다 — 조용히 넘어가지 않습니다. 컬럼 삭제·타입 변경은 어느 경로도 반영하지 않습니다.

> **파싱 실패는 기동을 막습니다** (2026-07-29 #13). `crud.load_table_config()`는 예전에 파싱 실패 시 **로그 없이 `{}`** 를 반환했고, 가동 중에는 `refresh_dynamic_models`의 빈-config 가드가 막아줬지만 **손상 상태로 재기동하면 전 테이블이 사라졌습니다**. 지금은 로더가 둘로 나뉩니다 — `load_table_config()`(런타임: ERROR 로그 + `{}` 유지)와 `load_table_config_or_raise()`(기동: `TableConfigError`).
>
> **"파싱 실패"의 범위**(🔴 **「정확히 N」이라 적지 않습니다 — 아래 열거가 정본이고 로더가 자라면 이 수가 먼저 낡습니다**) (2026-07-29 H1/H5): ① 디코딩 불가 ② JSON 문법 오류 ③ **최상위가 객체가 아님**(`[]`·`null`·문자열·숫자). ③이 포함되는 이유는 측정 때문입니다 — `[]`는 게이트를 통과해 `init_dynamic_models`에서 `AttributeError`로 죽고, main의 광범위 `except`가 잡아 **동적 모델 0개로 부팅**했습니다(ERROR 한 줄, UI는 빈 화면). #13이 없애려던 실패 그 자체입니다.
>
> **BOM은 손상이 아닙니다** (H1). 로더는 UTF-8 BOM · UTF-16 LE/BE · UTF-32 BOM을 인식해 그 인코딩으로 읽습니다. Windows에서 BOM은 예외가 아니라 **기본값**입니다 — PowerShell 5.1의 `Set-Content -Encoding utf8`·`Out-File`이 UTF-8 BOM을, `>` 리다이렉트가 UTF-16 LE를 씁니다. 예전 엄격 `utf-8` 디코드는 이것들을 전부 파싱 실패로 만들었고, fail-fast와 곱해져 **모든 에디터에서 멀쩡해 보이는 파일로 웹서버가 영영 안 뜨는** 상태를 만들었습니다. BOM 없는 잘못된 인코딩(BOM 없는 cp949 등)은 그대로 거부합니다 — 관용이 아니라 **쓰인 인코딩으로 읽는 것**입니다.
>
> ⚠️ fail-fast는 위 **파싱 실패에 한정**합니다. 파일 부재·읽기 실패(OSError)·의미 수준 이상(이상한 선언)은 기동을 막지 않습니다.

**어떤 테이블이 있는지는 환경마다 다릅니다** — 이 파일은 gitignored인 현장 자산입니다. 갈리는 기준은 *누가 스키마를 정하는가*입니다.

- **제품 소유**(이름·컬럼을 제품이 정함): `wafer_map_metadata` · `map_split_registry`(M2.6부터 **DOE 그 자체** — 구간·자재가 `bands` JSON 컬럼 안에 있고 `knobs`·`split_desc`는 온톨로지가 소비하므로 평면 컬럼으로 남습니다) · 🗄️ `map_doe` · 🗄️ `map_doe_source`(**DEPRECATED 2026-07-27 — 아무것도 쓰지 않으며, 기존 행 읽기용 선언만 남아 있습니다. 물리 DROP은 운영자 승인 필요**). 정의의 원본은 **`server/product_tables.py` 하나**이며 `.sample`도 거기서 생성됩니다. 사이트 반영은 `server/scripts/install_product_tables.py`(현장 항목 무접촉 병합) → [CONFIG_GUIDE §5.8-ter](../guide/CONFIG_GUIDE.md).
- **현장 소유**: 공장 로그·맵 테이블 전부. `.sample`의 `bonding_map`·`inventory_master`·`production_plan`·`parts`·`large_table_100`은 **동작 예시**일 뿐 표준이 아닙니다.

> ⚠️ **선언되지 않은 컬럼은 저장에서 조용히 드롭되고 HTTP는 200입니다.** `column_types` 게이트가 미선언 컬럼을 버린 뒤 성공을 반환하므로, **컬럼 오타·config 누락이 저장 성공처럼 보입니다**(실제로 `map_doe`가 이 경로로 `eventtime`을 잃었습니다). 2026-07-27부터 `crud`가 **`(테이블, 컬럼)`당 1회** `[Schema]` 경고를 남깁니다(핫패스라 반복은 접고, 테이블당 예산을 넘기면 포화 사실도 1회 알립니다).

> ⚠️ **`map_key_columns`는 `replace_map`이 지울 범위의 정본입니다.** 과거에는 미선언 시 아무것도 지우지 않으면서 200을 내는 무음 no-op이었으나, **2026-07-28(U6)부터 범위를 못 잡으면 400으로 정직하게 거부**합니다(요청에 명시적 `scope` 필드를 실어 범위를 직접 지정할 수도 있고, 응답 `scope: {filters, deleted, inserted}`가 실제 삭제 범위·건수를 알립니다). 맵·계획 저장 테이블에는 반드시 선언하십시오 → [PRIMITIVES](./PRIMITIVES.md) `replace_map`.
