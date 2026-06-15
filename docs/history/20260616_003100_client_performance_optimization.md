# 2026-06-16 Client Performance Optimization (Vanilla JS)

바닐라 JS 기반 프론트엔드(`client2`)의 실시간 타임라인 렌더링 부하와 캐시 정합성 및 윈도우 리사이즈 병목을 해결하기 위한 클라이언트 성능 최적화 작업을 진행했습니다.

## 주요 변경 사항

### 1. 타임라인 증분(Incremental) DOM Prepending 구현
- **AS-IS**: WebSocket을 통해 실시간 audit log가 수신될 때마다 기존 타임라인 DOM 전체를 비우고(`innerHTML = ''`) 수십~수백 개의 카드를 매번 재생성하여 브라우저 Reflow/Repaint 부하를 야기했습니다.
- **TO-BE**:
  - 단일 로그 카드를 생성하는 `createTimelineItemDom(log)` 및 `createGlobalTimelineItemDom(group)` 헬퍼 함수를 분리했습니다.
  - 새 로그 수신 시 기존 DOM을 유지한 채 최상단에 `insertBefore`를 사용하여 새 노드만 prepend하는 `renderTimelineIncremental(log)` 및 `renderGlobalTimelineIncremental(log)` 함수를 신설했습니다.
  - Global 탭의 경우, 기존 트랜잭션 그룹에 새 로그가 추가될 때 기존 DOM 엘리먼트(`li`)를 찾아 `replaceChild`로 갱신함으로써 트랜잭션 단위 카드의 일관성을 보존하며 렌더링 성능을 개선했습니다.

### 2. 인메모리 캐시(`pageCache`) 실시간 인플레이스(In-place) 업데이트
- **AS-IS**: WebSocket으로 `batch_row_upsert` 또는 `batch_row_create` 이벤트 수신 시, 클라이언트 캐시 전체를 강제 무효화(`pageCache.clear()`)하여 후속 화면 이동 및 렌더링 시 대량의 DB Fetch 요청이 반복해서 발생하는 비효율이 있었습니다.
- **TO-BE**:
  - `updatePageCacheOnUpsert(items)` 및 `updatePageCacheOnDelete(rowIds)` 헬퍼 함수를 작성했습니다.
  - `batch_row_upsert` 및 `batch_row_create` 수신 시, `pageCache` 맵의 모든 skip 엔트리를 돌며 이미 캐싱된 행(row_id 일치)의 데이터 필드들을 인플레이스 머지(Merge)합니다.
  - 정렬 기준이 최신순(`updated_at` 내림차순)이고 첫 페이지 캐시(`skip = 0`)가 존재하면, 신규 행인 경우 맨 앞에 unshift하고 `pageLimit`을 넘지 않도록 pop 처리합니다.
  - `batch_row_delete` 수신 시에는 캐시된 페이지들에서 해당 로우를 완전히 필터링하여 제거하고 `total` 카운트를 안전하게 차감합니다.

### 3. 클라이언트 빌드 검증 및 테스트
- Vite 환경에서 `npm run build`를 수행하여 코드 변경에 따른 컴파일 에러나 누락된 바인딩이 없음을 확인했습니다.
