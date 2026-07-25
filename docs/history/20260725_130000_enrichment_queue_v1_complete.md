# Enrichment Queue v1 완성 — 클라 단계②③ 병합 + Living 승격

- **일시:** 2026-07-25 13:00
- **주체:** 총괄 PM 통합 (Client PM worktree 2건 병렬 산출물 병합)
- **영역:** client2 + 문서
- **커밋:** `100112c`(단계②③+dist), 병합 `1996864`, 개별 `24ddb27`(②) `016d497`(③)

## 무엇이 완성되었나

핵심가치 #1(최소 공수 교정)의 첫 실체인 Enrichment Queue가 v1 전 구성 완료:

- **서버** (기 커밋 `4c8c2a4`): `enrichment_rules.json` 로더/검증, dedup mapper(체인 룰 자동 파생 — HOL·SLO 계측·재시도·웜업 그대로 상속), API 2종(`GET /enrichment/rules`, `GET .../references/{i}`).
- **클라 단계①** (기 커밋 `c21bdb8`): `enrichment.html` 3구역 컨베이어(blank 필터 skip=0 청크, Enter→저장→자동 다음).
- **클라 단계②** (`24ddb27`): 참조뷰 실데이터 — `reference_views[].label` 탭(활성 탭만 조회), 250ms debounce + `refSeq`/`sessionToken` 이중 stale 가드, 행 내 탭 캐시, XSS-안전 경량 테이블, 상태별 UI(로딩/빈/400/404). 컨베이어 무간섭(비동기·`mousedown preventDefault` 포커스 보존).
- **클라 단계③** (`016d497`): 메인 그리드 결손 배지 — 규칙 1회 페치 캐시, `switchTable`/WS 훅 fire-and-forget(파생 테이블별 5s TTL, WS 500ms 디바운스, `limit=1` total만), 클릭 시 `enrichment.html?rule=` 진입, 규칙 API 부재 시 전체 무음 비활성.

## 검증

- 병렬 worktree 2건 무충돌 병합(파일 소유 분리 사전 설계). `npm run build` 4엔트리 정상(595ms).
- 통합 스모크: `/enrichment.html` 200 · index 200 · 워크리스트 쿼리 200.
- E2E(스모크 규칙 `production_plan`→`line_model_registry`): 인제션 5행 → dedup 3행(plan_count 2/1/2) → 컨베이어 채움 → 참조뷰 응답 실측 일치. 사용자 화면 확인 완료(단계①), ②③ 실브라우저 확인 항목은 각 phase 보고서 §5 참조.

## 아키텍처 영향

- 스펙 `ENRICHMENT_QUEUE_SPEC.md` **Proposal → Living 승격**, SSOT §6 서브시스템 지도에 배선.
- 신규 경계 계약: enrichment API 2종(형태는 스펙 §5). 기존 계약(셀 형태·WS·REST) 불변.
- 과정에서 발견된 제품 갭: 이슈 #7(런타임 신규 테이블 물리 CREATE 누락 — 재기동 필요) 보드 등재.

## 다음 단계

1. 실전 규칙 작성(사용자 실제 설비이력/bonding log 스키마 필요) — 스모크 규칙은 데모로 유지.
2. v2 후보: target 후보 추정 제안(어시스트 층), 이슈 #7 수정.
