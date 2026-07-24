# 🔗 이벤트 기반 백엔드: Outbox · 체인 인제션 · Graph DB 동기화

> **Status:** 🟠 부분 최신 | **Last-verified:** 2026-07-24 | **Owner:** Backend / Sync | **Source-of-truth:** `server/database/database.py`, `chain_ingestion_worker.py`, `graph_sync_worker.py`
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

### 2.2 비동기 사용자 컨텍스트 전달 (`ContextVars`)
비동기 API 요청 루프와 완전히 디커플링된 ORM 이벤트 리스너 내부에서 "수정을 실행한 유저명"과 "요청의 성격(Source)" 등을 파악하기 위해 파이썬의 `ContextVars`를 사용합니다.

* **ContextVars 정의**: `server/database/context.py`
  * `request_user`: 수정자 ID (기본값: `"system"`)
  * `request_transaction_id`: 논리적 트랜잭션 그룹 ID
  * `request_source`: 호출 근원 (예: `"user"`, `"pipeline_parser"`, `"chain_ingestion"`)
* **미들웨어 바인딩**: `server/main.py` 내 `db_context_middleware`가 매 API 요청 시 헤더 또는 쿼리 파라미터를 읽어 ContextVars에 값을 격리 주입하며, 요청 종료 시 안전하게 리셋(reset)합니다.

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
