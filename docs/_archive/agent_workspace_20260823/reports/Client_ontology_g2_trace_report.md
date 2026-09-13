# 보고서: 온톨로지 G2 클라이언트 — 추적 리포트 UI + 그리드 진입점

발신: Client PM / 수신: 총괄 PM
지시서: `agent_workspace/tasks/Client_ontology_g2_trace_ui_task.md`
브랜치: `worktree-agent-a25bc98e4e8dd043e` (main 병합·push 안 함 — 총괄 검수 후 병합)
착수 시 worktree가 main보다 뒤(그래프 뷰어 커밋 이전)라 **main을 fast-forward 병합 후 작업**(7932926 → 2b216e4).

## 1. 산출물

| 파일 | 변경 | 내용 |
|---|---|---|
| `client2/src/trace_core.js` | 신규 (~230줄) | 순수 로직(무의존, node 테스트 가능): identity 조립(compose 미러), 시드 파싱/캡/중복제거, missing 정규화, 요청 본문, 라벨 그룹핑, 타임라인 분리, 표시 헬퍼 |
| `client2/src/trace.js` | 신규 (~460줄) | trace.html 오케스트레이터 — POST /graph/trace, 시드 칩/depth/시간범위 컨트롤, 그룹·타임라인 렌더(청크), 상태 화면, URL 동기화 |
| `client2/trace.html` | 신규 (~800줄) | 리포트 페이지 — tokens.css 시맨틱 토큰만 사용, FOUC 스니펫, 양 테마, graph.html과 동일 헤더 문법 |
| `client2/src/trace_launch.js` | 신규 (~110줄) | index 진입점 — mapping-summary 판정, 선택 행→시드 변환(ensureCellObject 경유), 상한 20 토스트, 새 탭 이동 |
| `client2/index.html` | +2줄 | 툴바 `#trace-btn`("🕸️ 추적", 기본 숨김) + 컨텍스트 메뉴 `#menu-trace`(기본 숨김) |
| `client2/src/dom.js` | +2줄 | `traceBtn`/`menuTrace` 게터 (HTML id 실존 — 교훈 반영) |
| `client2/src/main.js` | +2줄 | `init()`에서 `initTraceEntry()` 호출 |
| `client2/src/api.js` | +4줄 | `switchTable` 말미 `refreshTraceEntry()` fire-and-forget (updateEnrichmentBadge 선례) |
| `client2/src/graph_viewer.js` | +7줄 | **유일한 허용 타 페이지 수정**: `init()`에 `?label=&identity=` 초기 중심 — 있으면 `explore()` 즉시 호출 (stats 병행 로드, renderStats는 select 값 보존이라 경쟁 무해) |
| `client2/vite.config.js` | +1줄 | `trace` 엔트리 추가 |

Menu 드롭다운 링크는 **추가하지 않음**(판단 위임 사항): trace.html은 시드 구동 페이지라 직링크 진입 시 빈 상태만 보임 — 진입은 그리드 선택 경유가 유일하게 유의미.

## 2. 설계 결정 (총괄 확인 요망 ⚠ 표시)

1. **identity 조립 = 서버 G1 `compose_identity` 클라이언트 미러**: `"|"` 조인 + 이스케이프(`\`→`\\`, `|`→`\|`) + float 정수 안정화(`3.0`→`"3"`). 서버 코드는 읽지 않았고 `Server_ontology_g1_report.md`의 확정 계약 서술 기준. ⚠ **숫자형 문자열**(`"3.0"`)도 클라이언트에서 안정화함(그리드 셀 값이 문자열로 오는 경우 대비) — 서버가 str 값을 안정화하지 않는다면 이 부분만 어긋날 수 있음. 서버 G2 구현과 교차 확인 필요.
2. **결손 식별자 행은 시드 제외**: identity_columns 중 하나라도 null/공백이면 해당 행 스킵 + 건수 토스트.
3. **time_from/to**: datetime-local 값에 초만 보정(`YYYY-MM-DDTHH:mm:00`), 타임존 무변환(naive local). ⚠ 서버 비교 시맨틱(naive/UTC)과 일치 여부 확인 필요.
4. **재실행 트리거**: 시드 칩 제거·depth 변경은 즉시 재추적(graph_viewer 선례), 시간 범위는 「재실행」 버튼으로 적용. 시드 0개가 되면 no-seeds 상태로 전환.
5. **재실행 실패 시 기존 리포트 유지 + 토스트**(첫 로드 실패만 전면 오류 화면) — graph_viewer 선례.
6. **missing_seeds 방어 파싱**: 객체/`"Label:identity"` 문자열/기타 모두 수용. 해당 칩에 ⚠ + warning 스타일 + 메타 바 배지.
7. **DOM 청크 렌더**: 유계 데이터(≤1000노드)지만 프리징 금지 규율 준수 — 그룹 테이블 100행/타임라인 300건 단위 + "더 보기", 구조 관계는 `<details>` 열 때 1회 지연 렌더.
8. **URL 동기화**: 성공 시 `replaceState`로 seeds/depth/from/to 반영 — 새로고침·공유 시 조건 유지.
9. XSS: DB 유래 문자열(identity/label/type/source_name/props) 전부 esc 경유.

## 3. 검증 (총괄 재현 체크리스트)

### 3-1. 정적
- [x] `node --check` — trace_core/trace_launch/trace/graph_viewer/main/api/dom 전부 통과.
- [x] tokens.css 무수정 (`git diff` 목록에 없음), CODE_MAP·스펙·PROJECT_STATUS 무수정.
- [x] 기존 경계 계약(REST/WS/셀 형태) 불변 — 추가 소비만: `POST /graph/trace`, `GET /graph/mapping-summary` (지시서 계약).

### 3-2. 단위 하니스 (mock 데이터, 서버 불필요) — **56/56 통과**
스크래치패드 `trace_core_test.mjs` (임시 파일 — 커밋 안 함):
- identity 미러: 파이프/백슬래시 이스케이프 비대칭성(`("A|B","C")≠("A","B|C")`), float 안정화, 결손→null
- 시드: 25→20 캡+dropped 5, label 구분 중복제거, URL 파싱(형식 오류/비배열/빈 값)
- missing_seeds 3형태 정규화, label-blind 매칭
- 요청 본문: 초 보정, 빈 시간 생략, `{seeds,depth,limit}` 키
- 그룹핑: 시드 그룹 우선/度수 내림/라벨 오름 tie, degree 계산
- 타임라인: 오름차순, 파싱 불가 event_time→구조로 격리

### 3-3. 브라우저 하니스 (mock fetch 주입 정적 하니스 — vite/빌드 불필요)
스크래치패드 `make_harness.mjs`가 worktree의 trace.html/graph.html에 import map(`config.js`/`tokens.css` 스텁)+mock fetch를 주입해 http.server로 서빙. 확인 항목:
- [x] 정상: 시드 4개(1개 미발견) → 좌 그룹 5라벨/9엔티티(시드 ⦿·degree·props 요약), 우 타임라인 8건 오름차순, user provenance 강조 배지 2건(앰버 좌측 보더+👤 user), 구조 관계 3건 접이식(열 때 렌더). 콘솔 에러 0.
- [x] 요청 본문 실측: `{"seeds":[...],"depth":2,"limit":1000}` — 계약 일치.
- [x] 시드 칩 제거 → 즉시 재추적 + URL replaceState 반영, `3/20` 카운터 갱신.
- [x] 미발견 시드: 칩 warning 스타일+⚠, 메타 바 "⚠ 미발견 시드 1개".
- [x] truncated(mock=big, 800노드/799엣지): truncated 배지, depth=3 URL 복원, 타임라인 300건+「이후 299건 더 보기」→클릭 시 599건 완렌더·버튼 소멸, 그룹 100행 청크, 프리징 없음.
- [x] 오류(mock=503): 전면 오류 상태 + `HTTP 503 — graph store unavailable` 상세 + 재시도 버튼.
- [x] 빈 결과: empty 상태 + 가이드. 시드 없음: no-seeds 상태 + 메인 링크.
- [x] 크로스링크 URL(window.open 스텁 실측): 그룹 행 `graph.html?label=Wafer&identity=LOT77%7C3`(파이프 인코딩 정상), 타임라인 노드 칩 클릭도 동일.
- [x] **graph.html?label=Chip&identity=BLOG-003** → stats 랜딩 생략, 해당 노드 중심 서브그래프 즉시 로드 + 검색바 동기화 + Inspector CENTER.
- [x] 양 테마: 라이트/다크 전환 스크린샷 확인 — 전 컴포넌트 토큰 추종, FOUC 스니펫 포함.

### 3-4. 총괄 본체 통합 시 해야 할 것
1. `cd client2 && npm run build` (worktree라 빌드 미수행) + dist 커밋.
2. 실서버로: mapping-summary 없는 테이블에서 버튼 숨김 / 있는 테이블에서 선택→추적 왕복 1회.
3. §2-1(숫자 문자열 안정화)·§2-3(시간 TZ)을 서버 G2 구현과 교차 확인.

## 4. 리빙 문서 초안 (worktree 규칙상 직접 미수정 — 총괄/doc-keeper 반영용)

**CODE_MAP §7 추가분** (graph_viewer.js 항목도 현재 부재 — doc-keeper 동기화 대상):
- `trace_core.js` (~230줄) — G2 추적 순수 로직. export: `composeIdentity`(G1 compose 미러) `capSeeds`/`SEED_CAP=20` `parseSeedsParam` `normalizeMissingSeeds` `buildTraceRequest` `groupNodesByLabel` `splitTimeline` 등.
- `trace.js` (~460줄) — trace.html 엔트리. `runTrace()`(POST /graph/trace, seq 가드) → `renderReport()`(그룹+타임라인 청크 렌더). 소비 API: `POST /graph/trace`.
- `trace_launch.js` (~110줄) — index 진입점. export `initTraceEntry`/`refreshTraceEntry`/`openTraceForSelection`. 소비 API: `GET /graph/mapping-summary`.
- `graph_viewer.js` init: `?label=&identity=` 초기 중심 지원(trace 크로스링크).

**히스토리 초안** (`docs/history/20260725_HHMMSS_ontology_g2_trace_report_ui.md`):
> feat(client): G2 추적 리포트 UI — index 그리드 「🕸️ 추적」 진입점(mapping-summary 기반 활성화, 선택 행→identity 조립 시드, 상한 20) + 신규 trace.html/trace.js(시드 칩·depth 1-3·시간 범위, 라벨별 엔티티 그룹 테이블, event_time 시간순 타임라인 + user provenance 강조, 구조 엣지 접이식, truncated/로딩/빈/오류 상태) + graph.html 쿼리 파라미터 초기 중심(양방향 크로스링크). identity 조립은 서버 compose_identity 미러(| 조인+이스케이프+float 안정화). mock 하니스 56 단위 + 브라우저 시나리오 검증.

## 5. 교훈 제안 (client-pm.md 반영 후보)

- **함정**: Claude Browser의 `read_console_messages`가 각 로그를 2회 나열할 수 있어 "요청 중복 발생"으로 오판하기 쉽다. **올바른 방법**: 중복 의심 시 window 전역 카운터(`window.__x = (window.__x||0)+1`)로 실제 실행 횟수를 실측한다.
- **함정**: worktree가 main보다 뒤인 채 기동될 수 있다(이번: 그래프 뷰어 커밋 부재). **올바른 방법**: 착수 시 `git merge-base HEAD main` 확인 후 필요하면 main을 자기 브랜치로 병합(ff)하고 착수한다.
- **함정**: vite 전용 모듈(`import.meta.env`, CSS import)은 브라우저 단독 로드가 불가해 "정적 검증 불가"로 포기하기 쉽다. **올바른 방법**: import map으로 `config.js`/`tokens.css`만 data-URL 스텁 치환 + mock fetch 주입하면 빌드 없이 실브라우저 검증이 된다(스크래치패드 `make_harness.mjs` 패턴).
