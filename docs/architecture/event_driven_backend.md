# 🔗 이벤트 기반 백엔드: Outbox · 체인 인제션 · Graph DB 동기화

> **Status:** 🟠 부분 최신 | **Last-verified:** 2026-07-25 | **Owner:** Backend / Sync | **Source-of-truth:** `server/database/database.py`, `chain_ingestion_worker.py`, `graph_sync_worker.py`
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 개괄 [backend.md](./backend.md)
> 관련 howto: [chain_ingestion_guide](../guide/chain_ingestion_guide.md)(맵퍼 개발) · [graph_db_integration_plan](../spec/graph_db_integration_plan.md)(그래프 상세)
>
> ⚠️ **검증 주의:** §1 다이어그램·§2.1의 `data_rows`/`DataRow` 리스너 서술은 JSONB blob 시대 기준입니다. 현재는 동적 네이티브 테이블([data_model.md](./data_model.md))이 주 저장소이므로, Outbox staging 대상의 정확한 범위는 코드 재확인이 필요합니다. 패턴(Transactional Outbox + LISTEN/NOTIFY)은 유효합니다.

이 문서는 `assyManager` 백엔드 서버에 구축된 **Database Outbox**, **체인 인제션(Chained Ingestion)**, 그리고 **Graph DB(Neo4j) 동적 동기화** 시스템의 아키텍처, 설정 방법, 신규 연동 규칙 개발 가이드를 종합적으로 제공합니다.

---

## 1. 전체 시스템 아키텍처 개요

본 시스템은 데이터베이스의 변경 사항을 100% 신뢰성 있게 추적하고 연쇄 반응을 일으키기 위해 **이벤트 기반 아키텍처(EDA)**와 **Transactional Outbox 패턴**을 채택하고 있습니다.

```mermaid
graph TD
    Client[Client / Ingestion Watcher] -->|1. Data Mutation| FastAPI[FastAPI Server]
    
    subgraph PostgreSQL Transaction Boundary (ACID)
        FastAPI -->|2a. Update Data| DataRows[data_rows Table]
        FastAPI -->|2b. Auto-Stage (ORM Listener)| Outbox[database_outbox Table]
    end
    
    subgraph Background Daemons
        Outbox -->|3a. Poll processed_chain = False| ChainWorker[Chained Ingestion Worker]
        Outbox -->|3b. Poll status = PENDING| GraphWorker[Graph DB Sync Worker]
    end
    
    ChainWorker -->|4. Dynamic Ingestion| DataRows
    GraphWorker -->|5. Dynamic Cypher Commit| Neo4j[(Neo4j Graph DB)]
```

---

## 2. Database Outbox 시스템

### 2.1 자동 Staging 동작 원리
개발자가 CRUD 코드를 추가할 때 Outbox 적재 로직을 실수로 빠뜨리는 인적 오류(Human Error)를 방지하기 위해 **SQLAlchemy Event Listener**를 통해 데이터베이스 세션 레벨에서 이벤트를 가로챕니다.

* **동작 위치**: `server/database/database.py` 내 `@event.listens_for(Session, "before_flush")`
* **동작 방식**: 
  * `session.new`에 `DataRow` 감지 시 ➡️ `CREATE` 이벤트 적재.
  * `session.dirty`에 `DataRow` 감지 시 ➡️ `EDIT` 이벤트 적재.
  * `session.deleted`에 `DataRow` 감지 시 ➡️ `DELETE` 이벤트 적재.
* ⚠️ **단일 import 경로 불변식 (C-2, 2026-07-25)**: 이 리스너는 **Session 클래스 전역**에 등록되므로, `database.database` 모듈이 서로 다른 이름(`database.database` vs `server.database.database`)으로 이중 import되면 리스너가 2회 등록되어 **모든 outbox 이벤트가 ×2 중복 발행**된다(라이브 실측: 중복 그룹 1,259,076개). 모든 프로세스·스크립트는 반드시 `server/` 디렉토리를 sys.path에 두고 최상위 `database.*` 경로로만 import한다(`server.*` 접두 import 금지). 회귀 가드: `tests/test_contention_fixes.py`(리스너 1개·flush당 이벤트 1건 검증).

### 2.2 비동기 사용자 컨텍스트 전달 (`ContextVars`)
비동기 API 요청 루프와 완전히 디커플링된 ORM 이벤트 리스너 내부에서 "수정을 실행한 유저명"과 "요청의 성격(Source)" 등을 파악하기 위해 파이썬의 `ContextVars`를 사용합니다.

* **ContextVars 정의**: `server/database/context.py`
  * `request_user`: 수정자 ID (기본값: `"system"`)
  * `request_transaction_id`: 논리적 트랜잭션 그룹 ID
  * `request_source`: 호출 근원 (예: `"user"`, `"pipeline_parser"`, `"chain_ingestion"`)
* **미들웨어 바인딩**: `server/main.py` 내 `db_context_middleware`가 매 API 요청 시 헤더 또는 쿼리 파라미터를 읽어 ContextVars에 값을 격리 주입하며, 요청 종료 시 안전하게 리셋(reset)합니다.

### 2.3 Outbox 보관 정책 (7일) · 주기 Purge · 인덱스 구성 (C-3, 2026-07-25)

outbox는 이벤트당 행 버전 3개(INSERT → 처리 UPDATE → broadcast_at UPDATE)를 만드는 고쓰기 테이블이며, 무한 보존 시 DB의 최대 비중을 차지한다(실측 2.7M행/4.9GB). 다음 보관 정책이 적용된다.

* **보관 기간**: **7일** (사용자 확정). `processed_chain = true`이고 `created_at`이 7일 경과한 행을 삭제한다. **미처리(`processed_chain = false`) 행은 나이와 무관하게 절대 삭제하지 않는다.**
* **실행 주체**: 체인 워커의 저빈도 주기 태스크 — `chain_ingestion_worker.purge_expired_outbox_sync` (기동 직후 1회 + 1시간 주기, `asyncio.to_thread` 백그라운드 발사로 폴링 루프 비블로킹, 별도 짧은 세션, **1000행 청킹** + 사이클당 50청크 상한).
* **탐색 인덱스**: 부분 인덱스 `idx_outbox_purge` — `(created_at) WHERE processed_chain = true`. 보관 정책이 유지되는 정상 상태에선 테이블 자체가 약 7일치로 소규모 유지된다.
* **FAILED 격리 행 주의**: 3회 실패로 격리된(`status='FAILED'`, `processed_chain=true`) 행도 7일 후 삭제된다 → **수동 재시도(`/admin/outbox/retry-failed`)는 7일 이내에 수행**해야 한다. 관리 API 조회용 부분 인덱스: `idx_outbox_failed` — `(status, id) WHERE status = 'FAILED'`.
* **레거시 인덱스 정리**: 비부분 인덱스 4종(`ix_database_outbox_id`(pkey 중복)·`ix_database_outbox_event_uuid`(미사용)·`ix_database_outbox_status`(부분 인덱스로 대체)·`ix_database_outbox_processed_chain`(부분 인덱스로 대체), 실측 합계 429MB)은 models.py 선언에서 제거되었고 기존 운영 DB는 `scripts/setup_db_performance.py`의 멱등 DROP으로 정리한다.
* **기존 백로그 정리**: 라이브 프로세스가 건드리지 않는 수동 스크립트 `scripts/purge_outbox_backlog.py`(dry-run 지원, 청킹 DELETE) — 실행 순서는 스크립트 docstring 참조.

---

## 3. 체인 인제션 (Chained Ingestion) 가이드

한 테이블의 데이터 변화(인제션)에 대한 결과물로 다른 연관 테이블의 데이터를 연쇄적으로 자동 가공/반영하는 비동기 데몬입니다.

### 3.1 체인 규칙 설정 (`server/config/chain_rules.json`)
체인 실행 규칙을 선언적으로 JSON 파일에 선언합니다.

```json
{
  "rules": [
    {
      "name": "production_to_inventory_reservation",
      "trigger_table": "production_plan",
      "target_table": "inventory_master",
      "mapper_module": "mappers.production_mapper",
      "mapper_function": "reserve_materials_from_plan",
      "enabled": true
    }
  ]
}
```
* `trigger_table`: 이벤트를 감지할 원천 테이블.
* `target_table`: 연쇄 업데이트를 적용할 대상 테이블.
* `mapper_module`: 매퍼 모듈 경로 (패키지 구조 `mappers.모듈명`).
* `mapper_function`: 실행할 매퍼 함수의 이름.

### 3.2 커스텀 콜백 매퍼 개발 방법
새로운 연쇄 로직을 추가하고 싶다면, `server/mappers/` 패키지 하위에 파이썬 파일을 생성하고 규칙에 맞춰 함수를 정의하기만 하면 됩니다. (백엔드 코어 수정 불필요)

* **매퍼 함수 작성 규격**:
  ```python
  from sqlalchemy.orm import Session
  from typing import Dict, Any

  def reserve_materials_from_plan(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
      """
      - db: SQLAlchemy 세션 객체 (BOM 테이블 조회 등 필요한 경우 사용)
      - payload: Outbox에서 넘어온 원천 데이터 정보 (row_id, business_key, data 등 포함)
      - 반환값: 타겟 테이블에 인제션할 GeneralUpdateBatch 규격의 딕셔너리 페이로드
      """
      row_data = payload.get("data", {})
      planned_qty = int(row_data.get("PLANNED_QTY", {}).get("value") or 0)
      
      # 원하는 비즈니스 연산 수행
      computed_value = planned_qty * 5
      
      # GeneralUpdateBatch 포맷으로 반환
      return {
          "updates": [
              {
                  "row_id": "INV_MAT_STEEL_01",
                  "updates": {
                      "RESERVED_QTY": computed_value
                  },
                  "source_name": "chain_ingestion",
                  "updated_by": "chain_worker"
              }
          ]
      }
  ```

### 3.3 매퍼 반환 페이로드 스펙 (GeneralUpdateBatch)
매퍼 함수는 최종적으로 FastAPI 백엔드의 데이터 업데이트 규격인 `GeneralUpdateBatch` 형태의 딕셔너리를 반환해야 합니다.

#### 필드 상세 스펙
1. **`updates`** (List[Dict], 필수): 업데이트를 수행할 대상 행들의 목록입니다.
   * `row_id` (String, 선택): 수정할 대상 행의 고유 ID (`row_id`)입니다.
   * `business_key_val` (Any, 선택): 대상 행의 ID를 모를 때, 테이블 설정에 정의된 비즈니스 키 값을 기준으로 대상을 매칭하여 업서트할 때 사용합니다. (`row_id`와 `business_key_val` 중 최소 하나는 명시해야 합니다.)
   * `updates` (Dict[String, Any], 필수): 업데이트할 컬럼명과 값의 쌍입니다. (예: `{"STOCK_QTY": 150}`)
   * `source_name` (String, 필수): **반드시 `"chain_ingestion"`으로 고정**해야 합니다. (순환 체인 무한 루프 감지 밸브의 핵심 차단 키입니다.)
   * `updated_by` (String, 선택): 데이터 변경 이력(Audit Log)에 남을 수정 주체명입니다. `"chain_worker"` 지정을 권장합니다.
2. **`transaction_id`** (String, 선택): 연쇄 수정 트랜잭션의 ID입니다. 생략 시 기본적으로 원천 트랜잭션 ID를 고스란히 물려받아 추적합니다.
3. **`silent`** (Boolean, 선택): `True`로 지정 시, 웹 프론트엔드로 실시간 변경사항 알림(WebSocket)을 전송하지 않고 조용히 DB만 업데이트합니다.

#### 구성 양식 예제

##### 패턴 A: row_id 기반 특정 데이터 수정
```json
{
  "updates": [
    {
      "row_id": "INV_MAT_STEEL_01",
      "updates": {
        "RESERVED_QTY": 50,
        "STATUS": "RESERVED"
      },
      "source_name": "chain_ingestion",
      "updated_by": "chain_worker"
    }
  ],
  "silent": false
}
```

##### 패턴 B: 비즈니스 키 기반 업서트 (Row ID를 모를 때)
```json
{
  "updates": [
    {
      "business_key_val": "PART-999-XYZ",
      "updates": {
        "STOCK_QTY": 120,
        "UNIT_PRICE": 5400
      },
      "source_name": "chain_ingestion",
      "updated_by": "chain_worker"
    }
  ]
}
```

### 3.4 순환 루프 방지 장치
체인 워커는 무한 재트리거(A 테이블 ➡️ B 테이블 ➡️ A 테이블...)를 막기 위해, 이벤트 페이로드 내 `source_name`이 `"chain_ingestion"`으로 설정된 건에 대해서는 **체인 규칙을 발동시키지 않고 즉시 패스**하도록 설계되어 있습니다.

### 3.5 폴링·브로드캐스트 지연 최적화 (Latency Model)
간헐적 반응 지연을 없애기 위해 다음 두 축이 적용되어 있습니다.

* **커밋 우선 → 통지 후행·인라인 (Commit-before-Broadcast, Inline Dispatch)**: 트랜잭션 그룹은 `apply_batch_updates` 성공 후 **먼저 `processed_chain=True` + `commit`** 을 확정하고, 그다음에 WebSocket 통지(`/internal/events/broadcast`)를 발사합니다. 통지는 배치의 모든 그룹 커밋 직후 **인라인 `await`** 로 발사합니다(`chain_ingestion_worker.py`, `_dispatch_broadcasts`). 한때 `asyncio.create_task` 배경 예약으로 구현했으나, 워커 이벤트 루프가 동기 DB 쿼리·매퍼에 블로킹되는 동안 태스크가 **기아(starvation)** 상태로 통지가 수 초 지연되고 스윕 오발동을 유발해 인라인으로 전환했습니다(커밋은 이미 완료된 뒤라 데이터 경로 지연 없음). 통지의 성공/실패는 처리 성공 여부·재시도 판정에 **절대 반영되지 않으며**, 재시도는 오직 실제 데이터 처리 실패로만 트리거됩니다(이미 커밋된 그룹의 재처리/중복 방지). 통지 HTTP 타임아웃은 3초입니다. **경계 계약(이벤트명 `batch_row_upsert`/`batch_row_delete`/`batch_refresh_required` 및 페이로드 형식)은 불변이며 타이밍만 커밋 이후로 이동**했습니다.
* **지연 SLO + 구간 계측**: 체인 경로의 목표는 **"값 변경 commit → 클라이언트 통지 도착 100ms 이내"** 입니다(`task/chain_outbox_latency.md` §SLO). 검증을 위해 워커는 통지가 있는 tx당 1줄의 INFO 계측 로그를 남깁니다 — `[Latency] tx=<id> wake=Xms mapper=Yms commit=Zms notify=Wms total=Tms ok=<bool>` (wake: outbox 감지→매퍼 시작, mapper: 매퍼+`apply_batch_updates`, commit, notify: 커밋→POST 응답+스탬프, total: 감지→통지 완료). 병목 구간은 로그만으로 특정 가능합니다.
* **Outbox 폴링 부분 인덱스**: `database_outbox` 스캔 비용을 상수화하기 위해 부분/표현식 인덱스를 사용합니다(`models.py` `DatabaseOutbox.__table_args__`, 기존 운영 DB는 `scripts/setup_db_performance.py`로 멱등 반영).
  * `idx_outbox_reload` — `(event_type, id) WHERE event_type='SYSTEM_RELOAD'`: SYSTEM_RELOAD 트리거 조회용. 조회 자체도 매 루프가 아니라 최소 1초 간격으로 스로틀됩니다.
  * `idx_outbox_unprocessed` — `(processed_chain, id) WHERE processed_chain=false`: 미처리 이벤트 큐 스캔용.
  * `idx_outbox_txid` — `(payload->>'transaction_id')` 표현식 인덱스(**PostgreSQL 전용**, SQLite는 dialect 가드로 미생성): tx 보완(dynamic fetch guard) 조회용.
* **LISTEN 전용 커넥션 상시 유지 (`OutboxListener`)**: 빈 폴링 후 `LISTEN/NOTIFY` 대기 시, 예전에는 **대기마다 새 커넥션으로 `LISTEN outbox_event`를 재등록**하여 빈 폴링과 등록 사이 발행된 NOTIFY가 유실(최대 2초 tail latency)됐습니다. 이제 워커 시작 시 LISTEN 커넥션을 **1회만** 등록·재사용합니다(`chain_ingestion_worker.py`, `OutboxListener`). LISTEN이 항상 폴링보다 선행 등록되므로 폴링 이후 NOTIFY는 소켓에 버퍼링되고, 대기 진입 직후 버퍼된 통지를 먼저 소비(drain)해 즉시 재폴링을 유도합니다. 커넥션 끊김/예외 시 안전 재생성(누수 방지), blocking `select`는 `asyncio.to_thread`로 오프로딩, SYSTEM_RELOAD 통지도 같은 채널로 공존합니다.
* **실패 head-of-line 블로킹 제거 (`process_pending_groups`)**: 예전에는 한 그룹 실패 시 `break`로 **배치 전체를 중단**(+`sleep(1)`)하여, 큐 선두(id asc)의 실패 그룹이 3회 재시도 동안 뒤의 정상 이벤트를 전부 정체시켰습니다. 이제 실패 그룹은 rollback되어 미처리(`processed_chain=False`)로 남고 `retry_count`만 증가(3회 후 격리 유지), 나머지 그룹은 계속 처리합니다. **순서 보존**을 위해 실패 그룹이 기록하려던 `target_table`을 건드리는 **후속 그룹만** 이번 배치에서 보류하고(동일 target에 대해 나중 그룹이 먼저 적용되어 순서가 뒤집히는 것을 방지), 서로 다른 target_table 그룹은 계속 처리합니다. target_table은 규칙 설정에서 결정되므로 매퍼 실행 없이 정적으로 판정(`_group_target_tables`)합니다. 실패 그룹의 매퍼 쓰기는 rollback되어 커밋되지 않으므로 유실/중복이 없습니다.

### 3.6 브로드캐스트 전달 신뢰성 (Reliability Model) — 핵심가치 #3(실시간 신뢰 전파)

커밋 우선(§3.5) 설계는 지연을 없애는 대가로 통지 신뢰성을 약화시킬 수 있어, 다음 세 축으로 **"결국엔 반드시 반영된다(eventual delivery)"** 를 보장합니다. 세 축 모두 **경계 계약(이벤트명·페이로드 형식)은 불변**이며 신규 이벤트를 추가하지 않습니다.

* **전달 확정 추적 (`broadcast_at` 컬럼) + 미전달 안전망 스윕 (F1)**: `database_outbox.broadcast_at`(nullable timestamptz)이 각 행의 브로드캐스트 전달 확정 시각을 기록합니다. 커밋 직후엔 통지할 메시지가 있는 그룹은 `NULL`(=미확정)로 두고, 통지할 것이 없는 no-op 그룹(순환 필터로 걸러진 그룹 등)은 즉시 스탬프합니다. 인라인 통지(`_dispatch_broadcasts`)가 그룹의 **모든** 메시지를 성공 전송하면 별도 짧은 세션으로 `broadcast_at`을 스탬프합니다. 웹서버 재시작·타임아웃(3s)·HTTP 실패로 통지가 유실되면 `broadcast_at`은 `NULL`로 남고, 워커 메인 루프의 주기 스윕(`sweep_undelivered_broadcasts`, 최소 5초 간격)이 이를 감지해 영향 `target_table`에 table-level `batch_refresh_required`를 **재발사**하고 확정합니다. 통지·스탬프가 배치 처리와 **같은 코루틴 반복 안에서 인라인 완료**되므로 스윕은 정상 경로("커밋됐지만 아직 미발사")를 구조적으로 볼 수 없고, **진짜 유실만** 잡습니다(정상 경로 오발동 제로, grace 5s 유지). `broadcast_at IS NULL` 마커는 DB에 durable하므로 **워커가 재시작돼도 복구**됩니다. 확장성: 부분 인덱스 `idx_outbox_undelivered`(`WHERE processed_chain=true AND status='SUCCESS' AND broadcast_at IS NULL`, 정상 상태에선 거의 빈 인덱스) + `LIMIT 500` + grace(`created_at < now()-5s`, in-flight 정상 통지 제외)로 **1000만행 누적에도 스윕이 O(미전달)** 로 동작합니다. **마이그레이션 필수**: 컬럼 최초 추가 시 기존 처리완료 행을 `COALESCE(processed_at, created_at)`로 **1회 청킹 백필**(`main.py` 기동 마이그레이션 + `scripts/setup_db_performance.py`)하여, 기존 outbox 전량이 미확정으로 오인되어 스윕이 대량 오발사(refresh storm)하는 것을 방지합니다.
* **그룹 간 브로드캐스트 순서 보존 (F2)**: 예전에는 성공 그룹마다 독립 배경 태스크를 발사하여 동일 `target_table`에 대한 두 그룹의 통지가 병렬 도착·역전(늦게 커밋된 최종값이 먼저 도착)될 수 있었습니다. 이제 한 배치의 모든 성공 그룹 통지를 `group_order` 순서의 `(event_ids, messages, timing)` 리스트로 모아, 배치 종료 시 **단일 순차 인라인 발사**합니다(그룹 간·그룹 내(삭제→upsert) 모두 직렬화). commit은 이미 완료된 뒤이므로 §3.5의 지연 이득은 유지됩니다.
* **tx 보완 쿼리 인덱스 정렬 (F3)**: 동적 fetch 가드의 tx 보완 쿼리를 `type_coerce(payload, JSONB)['transaction_id'].astext`(→ `payload ->> 'transaction_id'`로 컴파일)로 정렬하여 표현식 인덱스 `idx_outbox_txid`(`(payload->>'transaction_id')`)를 **실제로 사용**하게 했습니다. (기존 `.as_string()`은 `CAST(payload -> 'transaction_id' AS VARCHAR)`로 컴파일되어 인덱스식과 불일치했습니다. 인덱스·마이그레이션 변경 없음.)

> **⚠️ 순서 보존의 한계 (F4/F5) — 알려진 사각지대**
> * **순서 보존은 "동일 `target_table`" 정적 추정 기반**입니다(§3.5 HOL 가드 + §3.6 F2). 즉 **매퍼가 자신의 `target_table`이 아닌 다른 테이블을 read하여 계산하는 교차 테이블 의존(cross-table read dependency)** 은 이 가드가 보호하지 못합니다. 선행 그룹이 테이블 X를 쓰고 후행 그룹의 매퍼가 X를 읽어 테이블 Y를 쓰는 경우, 두 그룹의 `target_table`(Y vs X)이 달라 보류 대상이 아니므로 **순서가 보장되지 않습니다**. 이런 의존이 있는 규칙은 현재 선언적으로 표현할 수 없으며, 필요 시 규칙 스키마에 `depends_on`(교차 테이블 선행 조건) 도입을 검토해야 합니다.
> * **격리(3회 실패)의 순서 함의 (F5)**: 한 그룹이 3회 재시도 후 격리(`RETRYING` 유지)되면, **그 그룹이 기록하려던 값이 적용되지 않은 상태**에서 후속 그룹이 처리를 이어갑니다. 후속 그룹의 매퍼가 격리된 선행 그룹의 산출물에 (교차 테이블로) 의존하면 "적용된 적 없는 선행" 위에서 계산하게 됩니다. HOL 가드는 동일 `target_table` 후속만 보류하므로, 교차 테이블 의존이 없는 한 데이터 유실/중복은 없으나(실패 그룹 쓰기는 rollback), 교차 의존이 있으면 후속 산출물이 부정확할 수 있습니다.

---

## 4. Graph DB (Neo4j) 동기화 가이드

PostgreSQL의 RDB 관계형 데이터를 온톨로지(Ontology) 매핑 규칙에 따라 Graph DB의 엔티티(Nodes)와 의미적 연결(Relationships)로 동적 변환하여 동기화하는 데몬입니다.

### 4.1 온톨로지 매핑 설정 (`server/config/ontology_mapping.json`)
테이블명과 컬럼을 Neo4j의 노드 라벨, 속성 키, 관계 에지로 동적 치환하는 규칙을 선언합니다.

```json
{
  "default": {
    "node_label": "Row",
    "identity_property": "row_id",
    "property_mappings": {},
    "relationships": {}
  },
  "tables": {
    "assemblies": {
      "node_label": "Assembly",
      "identity_property": "assembly_id",
      "property_mappings": {
        "desc": "description"
      },
      "relationships": {
        "supplier_id": {
          "type": "SUPPLIED_BY",
          "target_label": "Supplier",
          "target_identity": "supplier_id"
        }
      }
    }
  }
}
```
* `node_label`: Graph DB에 생성될 노드의 라벨 (예: `Assembly`).
* `identity_property`: 해당 노드의 Primary Key 속성명.
* `property_mappings`: 테이블의 컬럼명과 Graph DB 노드 프로퍼티명 간의 일대일 매핑.
* `relationships`: 컬럼 업데이트 시 추가로 연결해야 할 관계 에지(Edge) 정의.
  * 위 예시에서 `supplier_id` 컬럼 값이 업데이트되면, 자동으로 `(:Assembly)-[:SUPPLIED_BY]->(:Supplier {supplier_id: 값})` 관계 에지가 생성됩니다.

### 4.2 트랜잭션 기반 배치(Batch) 커밋 최적화
초당 대량의 쓰기 작업이 일어날 때 Neo4j의 커밋 오버헤드를 막기 위해 **트랜잭션 일괄 처리**가 적용되어 있습니다.
* **동작**: 워커가 `PENDING` 이벤트를 한 번에 최대 200개씩 읽어들인 뒤, 메모리에서 **`transaction_id` 단위로 그룹핑**합니다.
* **실행**: 그룹에 포함된 수십~수백 개의 Cypher 질의들을 단 1번의 Neo4j 트랜잭션(`session.execute_write`) 내에서 전부 실행하고 일괄 성공/실패 처리합니다.

### 4.3 헬스체크 및 Mock 모드 Fallback
* **연동 스위치**: 시스템 환경 변수 `NEO4J_ENABLED=true` 로 켜고 끌 수 있습니다.
* **Mock 모드**: 만약 `NEO4J_ENABLED`가 `false` 이거나, Neo4j 드라이버 라이브러리가 없거나, Neo4j 서버가 다운된 경우, 워커는 **자동으로 Mock 모드로 Fallback**합니다.
  * Mock 모드에서는 오류로 서버를 정지시키는 대신, 동적으로 생성된 Cypher 질의와 바인딩 파라미터를 백엔드 콘솔 로그 스트림에 이쁘게 출력하고 이벤트를 완료 처리하여 개발 편의성을 높입니다.

---

## 5. 모니터링 및 문제 해결 (Troubleshooting)

Outbox 테이블(`database_outbox`)을 조회하여 동기화 상태를 모니터링할 수 있습니다.

* **상태 필드 (`status`)**:
  * `PENDING`: 아직 Graph DB 싱크 워커가 처리하지 않은 대기 상태.
  * `DISPATCHED`: 성공적으로 Graph DB 동기화가 반영 완료된 상태.
  * `FAILED`: 3회 재시도 실패 후 영구 실패 처리된 상태 (에러 디버깅 필요).
* **체인 처리 필드 (`processed_chain`)**:
  * `False`: 체인 인제션 워커가 아직 검토하지 않은 상태.
  * `True`: 체인 인제션 규칙 매칭 및 연쇄 실행이 완결된 상태.
* **장애 처리 흐름**:
  * 특정 이벤트 처리 중 오류 발생 시, 2초 간격 지수 백오프 기반으로 **최대 3회 재시도**를 수행합니다.
  * 3회를 초과해 실패한 레코드는 `FAILED` 상태로 변환되며 경고 로그가 남습니다. 문제 원인(예: 스키마 제약조건 위반, 잘못된 매퍼 리턴 스키마 등)을 해결한 뒤, 해당 행의 `status = 'PENDING'`, `retry_count = 0`으로 수동 업데이트하여 재실행할 수 있습니다.
