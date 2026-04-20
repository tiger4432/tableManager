# 2026-04-21: Increase Batch Chunk Size for Performance Optimization

## 1. 개요
대량 데이터 로딩 및 배치 업데이트 성능을 향상시키기 위해 클라이언트의 데이터 페칭 단위를 상향함.

## 2. 변경 사항
- **`_chunk_size` 변경**: 50 -> **500**
- **대상**: `ApiLazyTableModel` 전역 적용

## 3. 기대 효과
- **네트워크 오버헤드 감소**: 요청 횟수가 10배 감소하여 서버 부하 및 레이턴시 개선.
- **UI 반응성**: 1k 데이터 로드(`batchLoadRequested`) 등의 작업 시 더 적은 분할 요청으로 빠르게 전체 데이터를 확보 가능.
