# 📋 AssyManager Client: Full Feature Checklist (QA & Inspection Guide)

본 문서는 AssyManager Enterprise Client의 모든 현재 기능을 정리한 전수 점검표입니다. 향후 시스템 업그레이드나 리팩토링 시 기능 회귀(Regression) 방지를 위한 표준 체크리스트로 활용하십시오.

---

## 1. 데이터 테이블 가시성 및 제어 (Core Table)
- [ ] **가상 로딩 (Lazy Loading)**: 수만 건의 데이터 중 필요한 부분(Chunk 50)만 로드하여 메모리 및 성능 최적화 보장.
- [ ] **동적 테이블 탭 생성**: 서버 설정(`table_config.json`)을 기반으로 테이블 별 독립 탭 자동 생성 및 전환.
- [ ] **가변 컬럼 렌더링**: 각 테이블의 스키마에 따라 컬럼 헤더 및 데이터가 동적으로 구성됨.
- [ ] **실시간 정렬 토글 (Sort Toggle)**: 
    *   `Latest First` ON: 데이터 수정 시 해당 행이 최상단으로 자동 부상(Floating).
    *   `Latest First` OFF: 데이터가 수정되어도 현재 행의 순서가 고정됨 (Business Key 기반 자연 정렬).
- [ ] **고성능 BK 정렬**: JSON 파싱이 아닌 DB 인덱스 컬럼(`business_key_val`) 기반의 즉각적인 '품번순' 정렬 지원.
- [ ] **범용 검색 (Filter Bar)**: 상단 필터 바를 통한 키워드 검색 및 실시간 리스팅 지원.

---

## 2. 데이터 수정 및 무결성 (Data Mutation & Integrity)
- [ ] **인플레이스 편집 (In-place Edit)**: 셀 더블 클릭을 통한 직접 수정 및 자동 서버 동기화.
- [ ] **범용 텍스트 입력**: 숫자 전용 셀 제약 없이 모든 셀에서 문자+숫자 혼합 입력 지원 (`str` 캐스팅 기반).
- [ ] **고유 식별자 타겟팅 (Row ID Targeting)**: 수정/삭제 시 인덱스가 아닌 `row_id`를 사용하여 정렬 중에도 데이터 정합성 100% 보장.
- [ ] **복사 및 붙여넣기 (Copy & Paste)**:
    *   다중 셀 클립보드 복사 지원.
    *   고속 붙여넣기(`bulkUpdateData`) 시 행 순서 변화에 무관하도록 개별 행 ID를 매핑하여 업데이트.
- [ ] **비동기 행 삭제 (Async Batch Delete)**: 
    *   다중 행 선택 및 일괄 삭제 요청.
    *   UI 프리징 방지를 위한 별도 워커 스레드 처리 및 결과 브로드캐스트 대기.

---

## 3. 사이드 패널 및 보조 기능 (Interactive UI)
- [ ] **실시간 업데이트 히스토리**: 
    *   모든 테이블의 변경 사항을 시간순으로 Prepend 표시.
    *   수동 수정(Yellow)과 자동 동기화(Blue)를 색상으로 구분.
- [ ] **항목 클릭 스크롤**: 히스토리 로그 클릭 시, 해당 테이블 탭으로 즉시 포커스 이동 및 해당 행을 화면 중앙으로 스크롤(`scrollTo`).
- [ ] **셀 계보 트래커 (Lineage Tracker)**: 히스토리 하단 패널을 통해 특정 셀의 **전체 변경 이력(History)**을 API에서 조회하여 노출.
- [ ] **데이터 원천 관리 (Source Manager)**:
    *   우클릭 메뉴를 통해 특정 셀에 중첩된(Nested) 모든 원천 데이터 시각화.
    *   원천 간 우선순위 수동 고정(Pin) 및 개별 원천 삭제 기능.

---

## 4. 시스템 동기화 및 신뢰성 (Sync & Reliability)
- [ ] **Shared WebSocket Listener**: 단일 스레드 기반의 효율적인 소켓 관리 및 모든 탭 동시 갱신.
- [ ] **동기화 병합 (Merge Architecture)**: 업데이트 수신 시 기존 행의 로컬 메타데이터를 유지하며 데이터만 병합하여 유실 방지.
- [ ] **자동 재연결 (Auto-Reconnect)**: 서버 장애 시 3초 간격으로 소켓 연결 자동 복구 시도.
- [ ] **비즈니스 에러 핸들링**: 통신 장애, 권한 부족, 유동 데이터(Placeholder) 수정 시도 등에 대한 시각적 에러 알림(QMessageBox).

---

## 5. UI/UX 및 브랜딩 (Aesthetics)
- [ ] **커스텀 프로그램 아이콘**: 작업 표시줄 및 윈도우 제목 표시줄에 전용 브랜드 아이콘 반영.
- [ ] **상태 표시줄 (Status Bar)**: 현재 로드된 데이터 건수 및 소켓 연결 상태 실시간 표시.
- [ ] **다크 모드 엔터프라이즈 테마**: 가독성 높은 다크 테마(Catppuccin 기반) 및 강조 효과 일관성 유지.

---
*Last Modified: 2026.04.17 | AssyManager Client Functional Checklist v1.2*
