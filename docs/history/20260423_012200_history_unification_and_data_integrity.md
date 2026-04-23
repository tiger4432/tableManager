# Technical History: Unified Logging & Data Integrity Enhancement

**날짜**: 2026-04-23
**작성자**: Antigravity (AI Assistant)

## 1. 히스토리 로깅 및 내비게이션 통합
- **[중앙화]**: `MainWindow._dispatch_ws_message`를 이벤트 디스패칭의 단일 창구로 설정. 각 모델의 개별 로깅 시그널을 제거하여 데이터 흐름을 단순화함.
- **[인터랙트]**: 히스토리 항목 클릭 시 `nav_id`를 기반으로 해당 테이블의 탭을 자동으로 활성화하고, `EnsureVisible` 옵션을 사용하여 시각적 도약을 최소화한 스크롤 이동 구현.

## 2. 데이터 동기화 무결성 확보 (Integrity)
- **[ID 캐스팅]**: 서버의 정수형 `row_id`가 클라이언트의 문자열 맵과 충돌하여 업데이트가 누락되던 문제를 해결하기 위해 `str()` 캐스팅을 모든 전송/조회 구간에 강제 적용함.
- **[데이터 병합]**: `batch_row_upsert` 처리 시 단순 덮어쓰기가 아닌 개별 셀 단위의 병합 로직을 적용하여 부분 업데이트 시 기존 데이터 유실 방지.

## 3. 정렬 모드 및 페이지네이션 정합성 (Stability)
- **[정렬 규칙 준수]**: `Sort Latest` OFF(ID 순) 모드일 때 신규 행을 상단에 강제 삽입하던 버그를 수정. 신규 행은 카운트만 갱신하고 본래의 하위 순서에서 페칭되도록 조정.
- **[서버 정렬 안정화]**: `order_by="id"` 시 비즈니스 키 기반 정렬을 지원하되, DB 레벨의 tie-breaker(`row_id.asc()`)를 추가하여 수정 시 행의 위치가 불규칙하게 튀는 현상 방어.

## 4. 고급 중복 필터링 (Proxy Strategy)
- **[DuplicateFilterProxyModel]**: 
  - 페이지네이션 방식의 한계(행 이동 시 중복 노출)를 극복하기 위해 프록시 모델 도입.
  - 편집된 행이 원래 위치를 유지하면서 뒤쪽 페이지에서 또 나타날 경우(중복), 프록시 레이어에서 이를 자동으로 필터링하도록 설계.
  - `ApiLazyTableModel`에서 중복 마킹(`_is_duplicate`) 기능을 통해 오프셋 어긋남 없이 안정적인 데이터 구조 유지.

**참조 파일**:
- `client/main.py`: 디스패처 및 내비게이션
- `client/models/table_model.py`: 데이터 무결성 및 중복 마킹
- `client/ui/panel_filter.py`: 중복 필터링 프록시 모델
- `server/main.py`: 서버사이드 정렬 앵커링
