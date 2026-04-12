# 프로젝트 이력: 데이터 최신성(updated_at) 기반 정렬 및 실시간 UI 연동 (2026-04-12)

## 1. 개요
데이터의 수정 순서에 따른 정렬(Recency Sort)의 정확도를 높이고, 사용자가 화면에서 수정 시간을 즉시 확인할 수 있도록 `updated_at` 컬럼을 UI에 노출하고 실시간 동기화 로직을 강화함.

## 2. 상세 작업 내용

### 2.1 지능형 정렬 로직 구현 (Backend)
- **문제 현상**: 기존에는 `updated_at`과 `created_at`으로 단순히 `order_by`를 하였으나, 수정되지 않은 데이터(updated_at이 NULL인 경우)의 정렬 순서가 모호해질 수 있음.
- **해결 방안**: `func.coalesce(models.DataRow.updated_at, models.DataRow.created_at).desc()`을 사용하여 수정된 데이터는 수정 시간 기준, 수정되지 않은 데이터는 생성 시간 기준으로 단일 정렬 축을 생성함.

### 2.2 실시간 타임스탬프 동기화 (WebSocket)
- **문제 현상**: 셀 수정 시 WebSocket 브로드캐스트에 `updated_at` 정보가 없어, 사용자가 새로고침하기 전까지는 화면상의 '수정 시간' 컬럼이 갱신되지 않음.
- **해결 방안**: `update_cell` 및 `update_cells_batch` 브로드캐스트 페이로드에 서버의 최신 `updated_at` 값을 포함시켜 전송하도록 개선함.

### 2.3 클라이언트 UI 연동 (Frontend)
- **변경 사항**: `ApiLazyTableModel`에서 WebSocket 메시지 수신 시, 해당 행의 `updated_at` 데이터도 함께 업데이트하고 `dataChanged` 시그널을 방출하여 UI 컬럼이 즉시 갱신되도록 처리함.

### 2.4 설정 최신화
- `server/config/table_config.json`: 모든 테이블의 `display_columns`에 `updated_at` 컬럼을 추가함.

## 3. 최종 결과
- 새롭게 데이터를 추가하거나 수정할 경우, 해당 행이 즉시 최상단으로 정렬되며 화면의 `updated_at` 컬럼에 실시간으로 수정 시각이 찍히는 것을 확인함.

---
**기록자: Antigravity (Agent D v6)**
