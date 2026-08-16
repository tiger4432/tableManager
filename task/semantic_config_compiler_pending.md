# [Task] Enrichment 중심 Semantic Config Compiler

> **상태:** 대기(PENDING) | **우선순위:** 높음 | **등록:** 2026-08-16

## 목표

사용자는 소스·제품 테이블과 **Enrichment의 의미**만 선언한다. 시스템은 Enrichment를
실행하는 데 필요한 파생 테이블, materialization chain, Virtual Join, 원장 claim 및
결측 claim 워크리스트 계약을 하나의 컴파일 단계에서 자동 생성한다.

`dt_inventory`, `slot_trace_for_dt`, `bonding_inventory`,
`slot_trace_for_bonding`처럼 Enrichment의 구현 산출물인 테이블을 사용자가
`table_config.json`에 다시 손으로 선언하는 구조를 없애는 것이 핵심이다.

## 설계 원칙

1. **명시 입력**: 원천 테이블 스키마, 제품 소유 물리 테이블, Enrichment 의미 선언.
2. **생성 출력**: 파생 테이블 스키마·키·타입·인덱스, chain 실행 계획,
   Virtual Join, ontology claim emission, enrich action/worklist.
3. **단일 정본**: 생성 결과를 사람이 편집하지 않는다. 원 선언 경로·컴파일러 버전·해시를
   provenance로 남기고 effective config 조회 화면에서 읽기 전용으로 보여준다.
4. **fail-closed**: 컬럼 타입·키·fan-out·순환·동명 파생물 충돌이 있으면 일부만 생성하지
   말고 해당 선언 전체를 거절한다.
5. **결정적 컴파일**: 같은 입력은 항상 같은 effective config와 지문을 만든다.
6. **대규모 안전성**: Virtual Join은 무제한 결합을 금지하고, unique key/index와 예상
   cardinality를 컴파일 시점에 검증한다.

## 컴파일 파이프라인

`Source/Table 선언 → Enrichment AST → 의존성 DAG → 파생 스키마 → Materialization Plan
→ Virtual Join → Claim/Worklist emission → Effective Config`

## 인수 조건

- Enrichment 하나만 추가해도 필요한 파생 `table_config`, `chain_rules`,
  `virtual_join_rules`가 별도 수작업 없이 생성된다.
- 동일 파생 테이블을 여러 Enrichment가 요구하면 호환 선언은 병합하고, 키·타입이 다르면
  이름을 임의 변경하지 않고 명시적으로 거절한다.
- 선언 수정·은퇴 시 영향받는 파생물과 재처리 범위를 dry-run으로 먼저 보여준다.
- 생성된 모든 항목에서 원 Enrichment 선언까지 역추적할 수 있다.
- 사람이 작성한 원천/제품 테이블과 생성된 파생 테이블이 API와 UI에서 구분된다.
- 재기동 없이 원자적으로 effective config를 교체하고, 다중 프로세스가 같은 버전을 본다.
- 순환, fan-out 폭발, 누락 키, 타입 충돌, 중복 이름, 부분 컴파일 회귀 테스트를 포함한다.

## 비범위

- 현재 `enrichment_rules.json`, `chain_rules.json`, `virtual_join_rules.json` 내용을
  정본으로 승격하지 않는다. 이번 작업은 새 선언 문법과 컴파일러 경계를 먼저 확정한다.
- 과거 파생 데이터의 완전한 마이그레이션은 요구하지 않는다. 새 소스 셋업을 우선한다.
