# 🔭 Enrichment Queue — 클라이언트 단계② 구현 보고 (Client PM)

> **Status:** ✅ 구현 완료(소스) / ⏳ 통합 검증 대기 | **작성:** 2026-07-25 | **Owner:** Client PM
> **기준:** 총괄 위임 지시(단계② 범위 1~5) · `docs/spec/ENRICHMENT_QUEUE_SPEC.md` §5 확정 계약 · 단계① 보고서(`Client_enrichment_phase1_report.md`)
> **작업 위치:** git worktree 브랜치 `worktree-agent-a136d6b35de42ef02` (main 병합·push 안 함 — 총괄 검수 후 병합)
> **선행 조치:** 브랜치가 main(c21bdb8, 단계① 병합분)보다 뒤에 있어 `git merge main`(fast-forward)으로 단계① 코드 위에서 작업.

---

## 1. 변경 파일 (커밋 `24ddb27`)

| 파일 | 내용 |
|---|---|
| `client2/enrichment.html` | [C] 패널 placeholder 마크업 제거 → 탭 + 상태 카드(스피너/아이콘/텍스트/서브) + 테이블 래퍼. CSS: 클릭형 탭(hover/active), `refSpin` 스피너, sticky-header 경량 테이블(mono 셀, hover row, `ref-null` dim), `detailIn` 재사용 |
| `client2/src/enrichment.js` | 참조뷰 모듈 신설(아래 §2) + 훅 3곳: `selectRule→initReferencePanel`, `renderDetail→scheduleReferenceLoad`, `showConveyorEmpty→clearReferencePanel`. `renderReferencePlaceholder` 삭제 |

기존 파일(`index.html`/`dom.js`/`ui.js`/`api.js`/`websocket.js` 등) **무접촉** — 단계①과 동일하게 페이지 자체 모듈 안에서만 변경.

## 2. 설계 요지

### 탭 UI (범위 1)
- `rule.reference_views[].label`로 뷰 N개 → 클릭형 탭 N개. 첫 탭 기본 활성.
- **활성 탭만 조회**(선택 이동당 최대 1요청 — "모든 탭" 대신 확장성 우선 선택지 채택). 탭 전환은 의도적 단일 행동이므로 debounce 없이 즉시 로드.
- 참조뷰 0개 규칙: 탭 영역 숨김 + "참조뷰 미설정" 안내 카드(범위 5).

### 로드 타이밍 · 폭주 방지 (범위 2)
- 선택 변경(`renderDetail`) 시 `scheduleReferenceLoad()`: **250ms debounce**(`REF_DEBOUNCE_MS`) — 고속 ↑/↓ 이동·연속 Enter 시 마지막 선택만 조회.
- **이중 stale 가드**: ① `refSeq`(요청 시퀀스 — schedule 시점에 선증가시켜 in-flight 응답 즉시 무효화, 모든 `await` 뒤 재검사) ② 단계①의 `sessionToken`(규칙 전환/새로고침 무효화) 준용. 이전 행의 데이터가 새 행에 표시될 경로 없음.
- **행 단위 탭 캐시** `refCache`(Map, `refCacheRowId` 불일치 시 클리어): 같은 행에서 탭을 오가면 재요청 없음, 행이 바뀌면 자동 무효(항상 신선한 데이터). 크기는 뷰 개수 상한이라 무한 성장 없음.

### 렌더링 · 상태 (범위 3)
- 계약 `{label, columns, rows}` → **경량 HTML 테이블**(읽기 전용, 서버 LIMIT ≤200 기본/≤1000 최대라 AG-Grid 불요). sticky 헤더, 전 셀 `textContent`만 사용(XSS 안전), `null/undefined → '-'(dim)`.
- 패널 meta에 `N건 · Xms` 표시.
- 상태 4종 + 오류 3종: 유휴("항목을 선택하면…") / 로딩 스피너 / 빈 결과("근거 데이터 없음") / 오류 — 400(서버 `detail` 표시), 404("규칙 설정 변경 가능성 — 새로고침"), 네트워크("서버에 연결할 수 없습니다").

### 컨베이어 무간섭 (범위 4)
- 로드는 순수 비동기 — 입력·Enter·이동을 절대 블로킹하지 않고, 참조뷰 코드는 어떤 `focus()`도 호출하지 않음.
- 탭 `mousedown`에 `preventDefault()` → 탭 클릭이 [B] 입력 포커스를 빼앗지 않음.
- 참조뷰 오류는 **토스트가 아닌 패널 내 표시** — 고속 이동 중 토스트 스팸으로 흐름을 방해하지 않음.

### 계약 준수
- 요청: `GET /enrichment/rules/{rule}/references/{i}?params=<urlencoded JSON>` — params는 **선택 행의 decision_key 전체 값만**(그 외 키 전송 없음 → 400 경로 원천 차단). 값은 단계① `cellVal()`로 추출(셀 계약 `{value, is_overwrite, priority_source}` 읽기 전용, 형태 변조 없음).
- 경계 계약 무접촉: 신규 소비는 확정 계약 1종뿐, 기존 REST/WS/`/schema`/셀 형태 전부 불변.

## 3. 검증 결과 (worktree 제약 내)

| 항목 | 결과 |
|---|---|
| JS 문법 | `node --check src/enrichment.js` 통과 |
| 라이브 API 스모크(읽기 전용 GET, localhost:8080) | ✅ 4형태 전부 실측 일치 — `GET /enrichment/rules` 메타(`line_model_owner_attribution`, ref view 1개) / references/0 → `{"label":"관련 생산계획","columns":[3],"rows":[2]}` / index=99 → 404 / `params={"bogus":1}` → 400 `detail` 문자열 |
| 확장성 체크 | 전량 로드 없음(서버 LIMIT 강제 + 활성 탭만 조회), debounce 250ms, 행당 최대 1 in-flight(시퀀스 가드), 캐시 상한=뷰 수 |
| 사이드이펙트(단계① 회귀) | 코드 리뷰로 확인 — 컨베이어 경로(`saveCurrent`/`moveSelection`/`selectDisplayedIndex`/`fetchWorklist`) 무수정. 추가된 훅 3곳은 전부 말단 append(비동기 예약/클리어)라 기존 흐름의 제어·포커스에 영향 없음. `showConveyorEmpty`의 `clearReferencePanel`은 "참조뷰 미설정" 상태를 덮지 않음(refViews>0일 때만 유휴 전환) |
| 시각 검증 | ⚠️ 부분 — worktree에 node_modules 없어 vite 실행 불가, 브라우저 패널 미표시로 정적 스크린샷 미획득. CSS는 단계① 토큰(cyan/glass/Outfit·JetBrains Mono) 순수 추가라 통합 빌드 후 확인 필요(§4-2) |
| `npm run build` | 미실행(지시 준수 — 통합 시 본체에서 수행) |

## 4. 통합 검증 필요 항목 (총괄 수행용)

1. `cd client2 && npm run build` + dist 커밋(기존 4엔트리 회귀 없음).
2. 실브라우저: 항목 선택 → 스피너 → 테이블 렌더(`관련 생산계획` 탭), ↑/↓ 고속 이동 시 네트워크 탭에서 debounce 동작(마지막 선택만 요청)·stale 미표시 확인, 같은 행 탭 재클릭 시 캐시 히트(무요청).
3. 연속 Enter 컨베이어 루프 중 참조뷰 로딩이 입력 포커스·다음 이동을 방해하지 않는지(범위 4) 실감 확인.
4. 참조뷰 0개 규칙(또는 rules.json에서 임시 제거)으로 "참조뷰 미설정" 카드 확인.
5. 뷰 2개 이상 규칙 등록 시 탭 전환·행 전환 캐시 무효 동작 확인(현재 라이브 규칙은 1개뿐).
6. 다크 테마 시각 품질(sticky 헤더, hover, 스피너) — 프리미엄 디자인 기준.

## 5. 작업 이력 초안 (총괄 통합 시 `docs/history/` 반영용)

> **제안 파일명**: `20260725_HHMMSS_client_enrichment_queue_phase2.md`
> **요약**: Enrichment Queue 클라이언트 단계② — [C] 참조뷰 실데이터 연동. 확정 계약 `GET /enrichment/rules/{rule}/references/{i}?params={decision_key값}` 소비(활성 탭만, 서버 LIMIT 강제). 클릭형 탭 UI, 250ms debounce + refSeq/sessionToken 이중 stale 가드 + 행 단위 탭 캐시, 경량 XSS-안전 sticky-header 테이블, 상태 표시(유휴/로딩/근거 없음/400·404·네트워크), 참조뷰 미설정 안내. 컨베이어 무간섭(비동기·포커스 무접촉·탭 mousedown preventDefault·오류 패널 내 표시). 경계 계약 불변. 검증: node --check + 라이브 GET 스모크 4형태 실측 일치.
> **리빙 문서**: `docs/architecture/frontend.md` enrichment 항목에 참조뷰 연동 한 줄 추가(통합 시).

## 6. 미해결 / 다음 단계

- 단계③(잔여): 메인 그리드 결손 배지 + nav 링크(`index.html`/`dom.js`/`ui.js`/`websocket.js` 훅), 빌드+dist, 문서/히스토리 마감.
- 참조뷰 다건 동시 표시(스택 뷰)는 v1 범위 밖 — 운영 피드백에서 "탭 전환이 번거롭다"가 나오면 활성 탭 프리페치(인접 탭 백그라운드 로드)로 확장 가능(캐시 구조 그대로 재사용).
- 서버 참조뷰 쿼리의 필수 바인드 누락 시 400(`Reference query execution failed`)이 사용자에게 노출됨 — 규칙 작성 가이드 준수 전제(서버 소관).
