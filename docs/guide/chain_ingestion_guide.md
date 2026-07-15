# 📖 체인 인제션 DB 세션 활용 데이터 조회 및 계산 가이드

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

### [calculate_shortage.py](file:///c:/Users/kk980/Developments/assyManager/server/mappers/calculate_shortage.py)
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
