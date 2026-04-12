# Development History: Bulk Ingestion Optimization & UI Enhancements

- **Date**: 2026-04-13
- **Phase**: 34 (Performance Optimization)

## 🎯 주요 목표
1. 대량 데이터 주입 시 시스템 지연(UI 프리징) 해결
2. CSV 익스포트 시 값 추출 무결성 방어 (이중 래핑 방지)
3. UI 편의성 개선 (복사 시 컬럼 헤더 포함)
4. 활성 탭 기준 행 수 카운터 정확도 확보

## 🛠️ 작업 내용
### 1. 고성능 배치 인제션 (Backend/Pipeline)
- **API**: `PUT /tables/{table_name}/upsert/batch` 신규 엔드포인트 구현. `CellUpsertBatch` 스키마 도입.
- **CRUD**: `upsert_rows_batch` 구현으로 단일 트랜잭션 내 다중 행 업서트 처리.
- **WebSocket**: 배치 처리 시 1회의 `batch_row_upsert` 이벤트만 전송하여 브로드캐스트 부하 최소화.
- **Pipeline**: `DirectoryWatcher`를 리팩토링하여 50행 단위 배치 송신 로직 적용.

### 2. CSV 익스포트 무결성 방어
- `main.py`의 `export_table_csv` 로직에 재귀적 `value` 추출 로직 추가.
- 마이그레이션 오류 등으로 인해 `value` 내부에 또 다른 `CellData` 객체가 중첩되는 케이스 자동 복구 및 방어.

### 3. UI/UX 고도화
- **Clipboard**: `copy_selection` 리팩토링. 데이터 복사 시 상단에 탭 구분자로 컬럼 헤더를 자동 포함.
- **Counter**: `FilterToolBar`가 현재 활성 모델(`_active_proxy`)을 추적하도록 수정하여 탭 전환 시 행 수 카운터가 즉시 갱신되도록 개선.
- **Optimization**: 클라이언트에서 `batch_row_upsert` 수신 시 `beginResetModel`/`endResetModel`을 사용하여 대량 갱신 시 응답성 유지.

## ✅ 결과 및 검증
- 1,000행 주입 테스트 시 HTTP 요청 수 98% 감소 (1,000회 -> 20회).
- 대량 주입 중에도 UI 프리징 없이 실시간 업데이트 확인.
- Excel 등으로 데이터 복사 시 컬럼 정보가 유지되어 외부 분석 도구 접근성 향상.
