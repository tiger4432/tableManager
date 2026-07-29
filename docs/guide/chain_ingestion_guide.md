# 📖 체인 인제션 DB 세션 활용 데이터 조회 및 계산 가이드

> **Status:** 🟢 Living | **Last-verified:** 2026-07-29 (M3 맵 메타 자동 등록이 체인 워커 경로에도 붙음 — 맵퍼 계약 변화 없음, 포인터 1건 추가) | **Owner:** Ingester | **Source-of-truth:** `server/chain_ingestion_worker.py`, `server/mappers/`, `server/enrichment_config.py`, `server/enrichment_mapper.py` · 상위 [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md)

체인 인제션 파서 및 맵퍼 모듈을 작성할 때, 단순히 유입되는 파일의 값뿐만 아니라 **데이터베이스의 기존 테이블(예: 재고 정보, 설비 마스터 등)을 직접 검색 및 조인(Join)하여 파생 컬럼을 계산**해야 하는 경우가 많습니다.

본 가이드는 SQLAlchemy DB 세션(`db`)을 활용하여 기존 데이터를 조회하고 가공하는 실전적인 예제와 구현 절차를 안내합니다.

---

## 💡 실전 예시 시나리오: 생산 부족 수량 자동 계산
- **상황**: `production_plan` (생산 계획) 데이터가 인입될 때,
- **목표**: `inventory_master` (재고 마스터) 테이블에서 동일한 자재 코드(`material_code`)의 **현재 가용 재고(`current_stock`)**를 조회(Join/검색)합니다.
- **계산**: `생산 요구 수량(plan_qty) - 현재 재고(current_stock)`를 계산하여 **부족 수량(`shortage_qty`)** 컬럼 값을 자동으로 도출해 채워 넣습니다.

---

## 🛠️ 1. 맵퍼(Mapper) 함수 구현 예제

맵퍼 스크립트는 `server/mappers/` 디렉토리 하위에 작성되며, 가공 실행 시점에 SQLAlchemy 데이터베이스 세션(`db: Session`) 객체를 인자로 전달받아 직접 자유로운 SQL 쿼리 및 ORM 조작을 수행할 수 있습니다.

### `calculate_shortage.py` (예제 — 저장소에 없는 파일입니다)

> ⚠️ 아래는 **직접 만들어 보는 템플릿**이지 저장소에 있는 파일이 아닙니다. `server/mappers/*`는 gitignored(사용자 커스텀 영역)이고 트래킹되는 것은 `production_mapper.py.sample` 하나뿐이므로, 각 환경의 실제 맵퍼 구성은 **디렉터리를 직접 확인**해야 합니다. 이 파일명을 그대로 Read하려 하지 마십시오.
```python
import logging
from sqlalchemy.orm import Session
from sqlalchemy import text

# 통합 로거 활용
logger = logging.getLogger("Chain.calculate_shortage")

def map_production_plan_shortage(row_data: dict, db: Session) -> dict:
    """
    생산 계획 행 데이터에 대해 재고 마스터 테이블을 조회하여 
    가용 재고를 기반으로 부족 수량(shortage_qty)을 실시간으로 조인 및 계산합니다.
    
    :param row_data: 인입된 신규 생산 계획 행 (dict 형태)
    :param db: SQLAlchemy 데이터베이스 세션 객체
    :return: 가공/계산이 완료된 갱신된 행 데이터 (dict 형태)
    """
    material_code = row_data.get("material_code")
    plan_qty = float(row_data.get("plan_qty") or 0)
    
    if not material_code:
        row_data["shortage_qty"] = 0
        row_data["inventory_note"] = "자재 코드 누락"
        return row_data

    try:
        # ---------------------------------------------------------
        # [DB 조회 예시 1] ORM 모델을 활용한 검색 및 조인
        # ---------------------------------------------------------
        # database.models에 등록되어 있는 dynamic model을 가져옵니다.
        from database.models import get_dynamic_model_class
        
        # 'inventory_master' 테이블 클래스 동적 획득
        InventoryMaster = get_dynamic_model_class("inventory_master")
        
        if InventoryMaster:
            # 동일 자재 코드의 재고 행을 검색 (가장 최근 갱신된 내역 기준)
            inv_record = db.query(InventoryMaster).filter(
                InventoryMaster.material_code == material_code
            ).order_by(InventoryMaster.updated_at.desc()).first()
            
            if inv_record:
                current_stock = float(inv_record.current_stock or 0)
                location = inv_record.storage_location or "미지정"
            else:
                current_stock = 0.0
                location = "재고 정보 없음"
        else:
            # ---------------------------------------------------------
            # [DB 조회 예시 2] ORM 모델이 없을 때 Raw SQL 활용 쿼리
            # ---------------------------------------------------------
            # ORM 모델이 동적으로 로드되지 않는 극초기 단계이거나, 복잡한 조인이 필요할 때 안전한 폴백입니다.
            sql_query = text("""
                SELECT current_stock, storage_location 
                FROM inventory_master 
                WHERE material_code = :mat_code 
                ORDER BY updated_at DESC LIMIT 1
            """)
            result = db.execute(sql_query, {"mat_code": material_code}).fetchone()
            if result:
                current_stock = float(result[0] or 0)
                location = result[1] or "미지정"
            else:
                current_stock = 0.0
                location = "재고 정보 없음"

        # ---------------------------------------------------------
        # [비즈니스 로직 연산] 부족 수량 계산
        # shortage_qty = 생산 필요 수량 - 가용 재고
        # ---------------------------------------------------------
        shortage_qty = max(0.0, plan_qty - current_stock)
        
        # 가공된 데이터 행에 계산 결과 바인딩
        row_data["shortage_qty"] = shortage_qty
        row_data["inventory_note"] = f"현재고: {current_stock}개 (창고: {location})"
        
        logger.info(f"[ShortageCalc] Material={material_code} -> Plan={plan_qty}, Stock={current_stock} -> Shortage={shortage_qty}")
        
    except Exception as e:
        logger.error(f"Failed to calculate shortage for material '{material_code}': {e}")
        row_data["shortage_qty"] = 0
        row_data["inventory_note"] = f"재고 계산 오류: {str(e)}"
        
    return row_data
```

---

## ⚙️ 2. 체인 룰 설정 파일에 맵퍼 등록

가공 연산이 정의된 파이썬 함수를 실제 인제션 파이프라인 흐름에 바인딩하기 위해 체인 룰 설정 파일에 맵퍼 모듈 정보를 기재합니다.

### [chain_rules.json](file:///c:/Users/kk980/Developments/assyManager/server/config/chain_rules.json)
```json
[
  {
    "rule_name": "Production Plan Shortage Ingestion",
    "source_table": "production_plan_raw",
    "target_table": "production_plan",
    "active": true,
    "mappers": [
      {
        "module": "mappers.calculate_shortage",
        "function": "map_production_plan_shortage"
      }
    ]
  }
]
```

---

## 💡 개발 시 주의해야 할 3대 Best Practices

1. **별도 트랜잭션 Commit 금지 (`db.commit()` 수행 자제)**:
   - 워커 메인 루프가 하나의 트랜잭션 단위로 전체 행 처리를 래핑하고 있습니다. 
   - 맵퍼 내에서 성급하게 `db.commit()`을 호출하면 트랜잭션 원자성이 깨져 에러 발생 시 부분 롤백이 불가능해지므로, 맵퍼 내부에서는 오직 데이터 **조회 및 할당**만 수행하고 커밋은 상위 워커 엔진에게 일임하십시오.
2. **N+1 쿼리 최소화 (Batching or Caching)**:
   - 인제션되는 행 수가 대량(수천~수만 건)인 경우, 매 행마다 `db.query()`를 날리면 네트워크/디스크 부하가 심각해집니다.
   - 대량 인제션이 예상되는 경우, `calculate_shortage.py` 모듈 초기화 시점에 `inventory_master` 전체 리스트를 한 번에 긁어 메모리 딕셔너리에 캐시해 두고 룩업(Lookup)을 도는 형태의 배칭 최적화를 권장합니다.
3. **스키마 동적 로드 시점 고려**:
   - `database.models.get_dynamic_model_class(table_name)`는 DB 초기화 이후 동작합니다. 안전을 위해 맵퍼 내부에서 모델 임포트 시 `from database.models import ...`를 함수 내부에서 지연 임포트(Lazy Import)하는 것이 안전합니다.

> ℹ️ **[M3 · 2026-07-29] 맵 테이블에 쓰는 체인 룰은 메타 자동 등록을 유발합니다.** 타깃 테이블이 `map_key_columns`를 선언하고 좌표 바인딩이 해석되면, 워커가 트랜잭션 그룹 처리 후 그 배치의 각 distinct 맵 키에 대해 **부재 시에만** `wafer_map_metadata` 행을 만듭니다(기존 행은 절대 덮지 않음). **맵퍼 코드는 바꿀 것이 없고** 실패해도 체인 적재는 정상 완료됩니다. 계약·끄는 법(`auto_register_map_meta`)은 [INGESTION_GUIDE §1.10](./INGESTION_GUIDE.md)이 정본입니다.

---

## 🧩 4. Enrichment Queue 규칙 작성 (dedup 투영 — 자동 파생 체인 룰)

> 기준 스펙: [ENRICHMENT_QUEUE_SPEC.md](../spec/ENRICHMENT_QUEUE_SPEC.md) · 구현: `server/enrichment_config.py`, `server/enrichment_mapper.py`

**맵퍼 코드를 쓸 필요가 없습니다.** `server/config/enrichment_rules.json`(사용자 영역, gitignored — 형식은 `enrichment_rules.json.sample` 참조)에 규칙을 선언하면, 체인 워커의 `load_chain_rules()`가 규칙마다 dedup 투영 체인 룰(`enrichment_mapper.map_enrichment_dedup`, `is_batch: true`)을 자동 파생하여 기존 체인 파이프라인(HOL 가드·SLO 계측·재시도·warmup)을 그대로 태웁니다.

### 4.1 규칙 스키마

```jsonc
// server/config/enrichment_rules.json — {규칙명: 규칙}
{
  "bonding_wafer_attribution": {
    "source_table":  "bonding_log",              // 필수: 대량 원본 테이블
    "derived_table": "bonding_job_inventory",    // 필수: 파생 영속 테이블 — table_config.json에 등록되어 있어야 함
    "decision_key":  ["equipment", "event_time"],// 필수: 판단키(사람이 1회 판단하는 단위)
    "target_fields": ["wafer_id"],               // 필수: 사람이 채울 필드 — 맵퍼는 이 필드를 절대 쓰지 않음
    "list_columns":  ["chip_count", "lot_hint"], // 선택: 워크리스트 표시 단서(배치 내 대표값)
    "aggregations":  { "chip_count": "count" },  // 선택(서버 전용): v1은 count만 — 영향 키 한정 재계산(멱등)
    "enabled": true,
    "reference_views": [
      { "label": "lot event",
        "query": "SELECT lot_id, event_time FROM lot_events WHERE equipment = :equipment", // 인라인 SQL
        "limit": 200 },
      { "label": "lot-slot 이력", "query_ref": "lot_slot_history" }  // config/enrichment_queries/<ref>.sql
    ]
  }
}
```

### 4.2 필수 전제·제약 (위반 시 규칙이 로그와 함께 **스킵**됨)

1. **파생 테이블 등록**: `derived_table`은 `table_config.json`의 보통 테이블이어야 합니다(레이어링·AuditLog·WS·그리드 편집이 공짜로 적용되는 이유). `decision_key`·`target_fields`·`list_columns`는 파생 테이블 컬럼이어야 하고, `decision_key`는 원본 테이블 컬럼이기도 해야 합니다.
2. **파생 테이블 키 계약**: 파생 테이블 config는 `composite_key_source ⊆ decision_key` 이거나 `business_key ∈ decision_key` 여야 합니다(맵퍼가 판단키로 business_key_val을 결정론적으로 조립 — 키당 1행 upsert의 근거).
3. **참조뷰 SQL**: 단일 SELECT(또는 WITH)만, `;` 다중문 금지, 바인드 파라미터(`:col`)는 decision_key 컬럼명만. 쿼리 본문은 서버에만 존재하며 클라이언트에는 label만 노출됩니다. LIMIT은 서버가 강제(기본 200, 최대 1000).
4. **[확장성] count 집계 인덱스**: `aggregations: count`는 "영향받은 판단키 한정" `GROUP BY` 재계산(500키 청킹)을 수행합니다. 원본 테이블이 대규모(수백만 행 이상)라면 **decision_key 컬럼 복합 인덱스**를 생성하십시오(미생성 시 청크당 스캔 발생).

### 4.3 동작 요약 (불변식)

- 원본 변경 이벤트 배치 → decision_key 유니크 조합 추출(**증분** — 이벤트 행만, 풀스캔 없음) → 파생 테이블에 키당 1행 upsert.
- **신규 키**: 행 생성, `target_fields`는 NULL(결손) → blank 필터 워크리스트에 잡힘.
- **기존 키**: 집계·단서 컬럼만 갱신. 맵퍼는 `target_fields`를 updates에 아예 포함하지 않으며(1차 방어), 설령 포함되더라도 source `chain_ingestion`(우선순위 최하)는 user(priority 0)를 이길 수 없습니다(2차 방어 — 레이어링).
- 규칙 반영: 웹서버는 요청 시마다 재로드(무중단), 워커는 `SYSTEM_RELOAD`(`/admin/reload-configs`) 시 재파생.
