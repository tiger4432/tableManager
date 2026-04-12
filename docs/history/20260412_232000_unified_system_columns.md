# 프로젝트 이력: 시스템 컬럼 통합 가시성(Unified Visibility) 확보 (2026-04-12)

## 1. 개요
데이터의 접근 경로(목록 조회, 단건 조회, 신규 생성, 업서트 등)에 따라 `created_at` 및 `updated_at` 정보가 UI 상에 누락되거나 불일치하는 현상을 방지하기 위해 서버 측 주입 로직을 통합함.

## 2. 상세 작업 내용

### 2.1 통합 데코레이터 (`inject_system_columns`) 구현
- SQLAlchemy Row 객체를 인자로 받아, 해당 객체의 데이터 JSON(`data`) 내부에 `created_at`과 `updated_at`을 UI 표준 셀 형식으로 주입하는 공통 함수를 신설함.
- `updated_at`이 `None`인 경우 `created_at`을 폴백으로 사용하여 정렬 및 가시성의 일관성을 확보함.

### 2.2 전방위 엔드포인트 적용
- **목록 조회 (`/data`)**: 페이징 데이터 반환 전 일괄 주입.
- **단건 조회 (`/{row_id}`)**: 상세 데이터 반환 전 주입 (Float-to-top 기능의 핵심 보완).
- **행 생성 (`POST /rows`)**: 빈 행 생성 즉시 시스템 컬럼 주입 후 반환 및 브로드캐스트.
- **업서트/인제션 (`PUT /upsert`)**: 신규 생성(row_create) 및 기존 수정(batch_cell_update) 시점에 모두 통합 데코레이터 적용.

## 3. 최종 결과
- 지연 로딩을 통한 목록 스크롤, 실시간 데이터 부상, 수동 행 추가 등 모든 시나리오에서 시스템 컬럼(`created_at`, `updated_at`)이 누락 없이 동기화되는 것을 확인함.

---
**기록자: Antigravity (Agent D v9)**
