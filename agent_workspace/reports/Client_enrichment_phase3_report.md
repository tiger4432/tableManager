# 🧩 Enrichment Queue 단계③ — 메인 그리드 "결손 N건" 배지 구현 보고

> **Status:** ✅ 구현 완료 (worktree 브랜치, main 미병합) | **작성:** 2026-07-25 | **Owner:** Client PM (단계③ 위임 에이전트)
> **기준:** [Client_enrichment_plan.md](Client_enrichment_plan.md) §2·§6-③ · ENRICHMENT_QUEUE_SPEC §9-2
> **브랜치:** `worktree-agent-a0af6a0e08b31e3d5` (main `c21bdb8`에서 fast-forward 후 작업)
> **경계 준수:** `enrichment.html`·`src/enrichment.js` **무접촉** (단계② 병렬 소유) · 신규 서버 계약 없음(라이브 검증된 기존 계약만 소비)

---

## 1. 변경 파일 요약

| 파일 | 변경 | 내용 |
|---|---|---|
| `client2/index.html` | +4줄 | ① 헤더 `log-indicator-area`에 `#enrichment-badge` span (tx-pending-badge 옆, 기본 `display:none`) ② nav 드롭다운에 `🧩 Enrichment Queue` 링크 1줄 |
| `client2/src/dom.js` | +2줄(±1) | `elements.enrichmentBadge` 게터 1개 (DOM 일원화 규칙 준수) |
| `client2/src/ui.js` | +85줄 | 배지 로직 전체: `loadEnrichmentRules()`(1회 페치·캐시), `findEnrichmentRule()`, `updateEnrichmentBadge()`, `notifyEnrichmentTableEvent()` |
| `client2/src/api.js` | +4줄 | `switchTable()` 말미 fire-and-forget 훅(`await` 없음) + import 1개 확장 |
| `client2/src/websocket.js` | +7줄 | `handleWebSocketMessage()` 내 `batch_*` 이벤트 훅 — **currentTable 가드보다 앞** 배치 + import 1개 확장 |
| `client2/src/main.js` | +10줄 | 배지 클릭 리스너: `location.href = '/enrichment.html?rule=<name>'` (계획서 기준: 현재 탭) |
| `client2/src/style.css` | +15줄 | `#enrichment-badge` warning 톤(글래스 배지 계열) + hover 마이크로 애니메이션(lift + glow) |

## 2. 배지 갱신 트리거 설계

```
페이지 로드 ──(최초 필요 시 1회)── GET /enrichment/rules → 모듈 캐시
                                     실패/빈배열 → 기능 전체 무음 비활성
switchTable(t) 말미 ─ fire-and-forget → updateEnrichmentBadge()
  ├ t가 어느 규칙의 source_table 또는 derived_table? 아니면 → 숨김
  ├ 카운트: GET /tables/{derived}/data?skip=0&limit=1&filters={각 target: blank}
  │         → total (클라이언트 5초 TTL 캐시, derived별)
  ├ 응답 도착 시 currentTable 변동 → stale 폐기
  └ total>0 → "🧩 결손 N건" 표시 + dataset.rule 저장 / 0 → 숨김
WS batch_row_* / batch_refresh_required ─ notifyEnrichmentTableEvent(msg.table_name)
  ├ currentTable 가드 앞에서 훅 (source 뷰 중 derived 이벤트도 수신)
  ├ 이벤트 테이블 == 현재 뷰 관련 규칙의 derived_table 일 때만
  └ 500ms 디바운스 + force(캐시 우회) 재조회 → 소진 시 배지 자동 소멸
배지 클릭 → /enrichment.html?rule=<rule.name> (enrichment.js의 ?rule 소비 계약과 일치 확인)
```

- 폴링 없음 — 트리거는 테이블 전환·WS 델타·클릭 3종뿐.
- 다중 `target_fields`는 컬럼별 blank AND 필터(단계① `buildBlankFilters`와 동일 형태).

## 3. 회귀 안전 근거

1. **순수 추가만**: 기존 라인 삭제·수정 0 (import 2줄 확장 제외). 그리드 로드/편집/Tx/WS 델타 로직 무접촉.
2. **fire-and-forget**: `switchTable` 훅은 `await` 없음 → 테이블 전환 시간 불변. WS 훅은 동기 시그니처(내부 promise) → 델타 반영 경로 블로킹 0.
3. **무음 실패**: `updateEnrichmentBadge` 전체 try/catch — 규칙 API 404/네트워크 오류/파싱 실패 시 배지 숨김만 하고 콘솔 스팸 없음. **규칙 API 미배포 서버에 먼저 배포돼도 무해.**
4. **stale 가드**: 페치 전 `state.currentTable` 캡처, 응답 후 불일치 시 폐기 — 빠른 테이블 연속 전환에도 잘못된 카운트 표시 없음.
5. **WS 훅 위치 안전성**: `handleWebSocketMessage`의 currentTable 가드 **앞**에 두되 `batch_` prefix 이벤트에서만 호출, 내부에서 규칙 관련성 재판정 — 무관 테이블 이벤트는 promise 체인 1회로 종료.
6. **부하**: 카운트는 `limit=1` + 클라 5초 TTL + WS 500ms 디바운스 → 대량 인제션 브로드캐스트 폭주에도 최대 2 req/s 미만.
7. **경계 계약 불변**: 소비 REST·WS 이벤트·셀 형태 전부 기존 그대로. 신규 계약 없음.

## 4. 검증 결과

| 항목 | 결과 |
|---|---|
| `node --check` (ui/api/websocket/main/dom) | ✅ 전부 통과 (`npm run build`는 worktree 규칙상 금지 — 총괄 통합 시 필요) |
| 라이브 `GET /enrichment/rules` | ✅ `{"rules":[{name:"line_model_owner_attribution", source_table:"production_plan", derived_table:"line_model_registry", target_fields:["owner"], ...}]}` |
| 라이브 배지 쿼리 `GET /tables/line_model_registry/data?skip=0&limit=1&filters={"owner":{"type":"blank"}}` | ✅ `total: 1` — 라이브 상태면 `production_plan`/`line_model_registry` 뷰에서 "🧩 결손 1건" 표시될 조건 성립 |
| enrichment.html `?rule=` 소비 계약 | ✅ `enrichment.js:527-529`가 `r.name` 매칭 — 클릭 링크 정합 |

## 5. 통합 시 필요 항목 (총괄)

1. `cd client2 && npm run build` + dist 커밋 (worktree에서 금지되어 미실행 — **dist는 아직 구버전**).
2. 브라우저 실동: ① `production_plan` 선택 → 배지 "결손 1건" 표시 ② 클릭 → `enrichment.html?rule=line_model_owner_attribution` 진입 ③ enrichment 페이지에서 owner 입력 → 메인 그리드 복귀/WS 수신 시 배지 소멸 ④ 규칙 무관 테이블에서 숨김 ⑤ 규칙 API 차단 상태에서 그리드 정상 동작(무음).
3. 단계② 브랜치와 병합 — 본 브랜치는 `enrichment.html`/`enrichment.js` 무접촉이라 충돌 없음 예상.
4. 히스토리 기록 + `conda run -n assy_manager python docs/history/gen_index.py`, frontend.md 갱신 (worktree 규칙상 총괄 일괄).
