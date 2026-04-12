---
name: DataIngester
description: 다양한 원천 데이터(Raw Data)를 파싱하여 assyManager 서버로 적재하는 전문가 스킬
---

# DataIngester Skill

이 스킬은 외부 데이터를 `assyManager` 시스템에 안정적으로 병합하기 위한 표준 절차를 정의합니다.

## 1. 데이터 업데이트 원칙 (Multi-Source Priority)
- **절대 원칙**: 모든 원천 데이터를 보존하되, 표출 우선순위는 `User(Human) > Parser_A > Parser_B` 순으로 결정됩니다.
- **Push 전략**: 파서는 자신의 소스 명칭(`source_name`)과 함께 데이터를 항시 밀어넣습니다. 사용자가 이미 수정한 셀이라도 파서의 최신 값은 `sources` 맵 내에 별도로 보관됩니다.

## 2. API 호출 규격
- **Endpoint**: `PUT /tables/{table_name}/cells/batch`
- **Payload Structure**:
  ```json
  {
    "updates": [
      {
        "row_id": "UUID",
        "column_name": "col_name",
        "value": "new_value",
        "source_name": "parser_a", 
        "updated_by": "ingester_agent"
      }
    ]
  }
  ```

## 3. 파싱 시 주의사항
- **Row Matching**: 원천 데이터의 Primary Key를 기반으로 기존 DB의 `row_id`를 정확히 매핑해야 합니다. 매핑되지 않는 신규 행은 `POST /tables/{table_name}/rows`를 통해 먼저 생성합니다.
- **Type Casting**: DB 스키마에 적합한 데이터 타입(정수, 실수, 날짜 등)으로 변환하여 전송하십시오.

---
*본 지침을 준수하여 데이터 무결성과 시스템 확장성을 보장하십시오.*
