# source_config.xlsx 기반 Table Config 재구성

## 요청

사용자가 비워 둔 `server/config/table_config.json`을 루트 `source_config.xlsx`의 물리 컬럼 정의대로
다시 만들고, 제품이 소유하는 기본 시스템 테이블도 함께 선언한다. 과거 샘플 스키마는 복구하지
않고, 원본에 없는 합성 컬럼을 추가하지 않는다.

## 판정

1. 엑셀 `Sheet1!A1:G129`의 13개 소스 테이블, 128개 컬럼, 타입, 표시 순서를 그대로 사용한다.
2. `Unique Key`가 한 컬럼이면 `business_key`, 여러 컬럼이면 그 순서 그대로
   `composite_key_source`로 선언한다.
3. 복합키를 보관하기 위한 `cell_key`, `map_pk` 같은 물리 컬럼은 원본에 없으므로 만들지 않는다.
   조립한 신원은 프레임워크 시스템 컬럼 `business_key_val`에만 둔다.
   구분자는 랏·잡 이름에 흔한 `_` 충돌을 피하도록 제품 표와 같은 `|`를 사용한다.
4. `Map Overlay=key`만 `map_key_columns`로 옮긴다. x/y/value 바인딩은 별도
   `map_overlay_config` 작업이며 이번 table config에 추측해 넣지 않는다.
5. 제품 소유 기본 테이블은 `server/product_tables.py` 단일 정본의 3개
   (`wafer_map_metadata`, `map_split_registry`, `valid_die_ref`)를 그대로 설치한다.
6. `void`, `defect`, `metro`는 원본에 Unique Key 표기가 없으므로 키를 발명하지 않는다. 따라서
   표준 파서로 직접 적재하려면 후속 단계에서 원본 키를 확정하거나 전용 파서를 선언해야 한다.

## 구현

- 라이브 `server/config/table_config.json`
  - 소스 테이블 13개 / 소스 컬럼 128개
  - 제품 소유 기본 테이블 3개
  - 소스 컬럼명·타입·순서 외 물리 컬럼 추가 0개
- `server/database/crud.py`
  - `composite_key_source`만 있는 원천 스키마도 내부 `business_key_val`을 조립·저장
  - 실제 `business_key` 물리 컬럼이 선언된 기존 제품 테이블은 종전처럼 조립값을 함께 기록
  - 복합키 일부가 비면 기존과 같이 키 조립을 거절
- `server/tests/test_composite_key_prefetch_budget.py`
  - 합성 물리 컬럼 없는 복합키의 재적재 멱등성 및 결측 키 거절 회귀 추가
- `docs/guide/config/table_config.md`, `docs/architecture/data_model.md`
  - 원천 소유 복합키와 제품 소유 합성 키 컬럼의 차이를 문서화

## 검증

- artifact-tool 원본 대조: `source_tables=13`, `source_columns=128`, `product_tables=3`, PASS
- 제품 테이블 설치기 dry-run: 3개 모두 정본 일치, 변경 필요 0
- `test_install_product_tables.py`: **39 passed**
- 신규 source-exact 복합키 집중 테스트: **3 passed**
- 연관 4개 테스트 파일: **71 passed, 기존 stale 성능 oracle 1 failed**
  - 실패는 신규 insert SELECT 수를 201로 고정한 기존 예산 테스트이며 현재 구현 실측은 1이다.
    이번 키 의미 변경과 무관하고 나머지 계약 테스트는 통과했다.
- `py_compile server/database/crud.py`: 성공

## 아직 하지 않은 것

- 물리 DB의 CREATE/ALTER 및 기존 타입 일치 감사
- `Map Overlay=x/y/value`를 `map_overlay_config` 바인딩으로 옮기는 작업
- `void`, `defect`, `metro`의 원천 업무 키 판정
- chain, enrichment, transfer plan 등 후속 config 재작성
