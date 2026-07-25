# Admin 페이지 UX 감사 보고서

- **감사자**: ui-designer | **일자**: 2026-07-25 | **대상**: `client2/admin.html` + `client2/src/admin.js` (main 트리, 코드 수정 없음)
- **방법**: 라이브(:8080/admin.html) 7탭 전부 실조작(1280×800, 라이트/다크 양 테마) + DOM/computed-style 계측 + 소스 대조. 브라우저 pane 스크린샷이 대형 캔버스 다운스케일로 판독 불가 → 세부 진단은 DOM/JS 계측 기준(교훈 파일의 pane 제약 준용).
- **라이브 데이터 규모**: outbox 실패 4 tx / 파일 인제션 로그 5,716건(실패 42) / 워크스페이스 14 / 체인 룰 2 / 맵퍼 2 / 오토업데이트 4 / 편집 가능 스크립트 11.

---

## 1. 축 1 — IA 갭 분석: 메커니즘 지향 7탭 vs 파이프라인 지향

사용자 진단(chain rule·mapper 분리, outbox fail=chain fail인데 분리 표시)은 정확하다. 현행 7탭은 **서버 내부 메커니즘**(outbox 테이블, 파일 로그 테이블, 워크스페이스 디렉터리, 룰 json, 맵퍼 모듈…)을 1:1로 노출한 구조이고, 사용자의 멘탈 모델인 **파이프라인 4종의 생애관리**와 직교한다.

### 1.1 매핑 표: 파이프라인 × 생애 단계 → 현행 탭

| 파이프라인 \ 생애 단계 | 오류 탐지 | 버그 수정 | 현황 관리 | 실행 관리 | 신규 추가(온보딩) |
|---|---|---|---|---|---|
| **File Ingestion** | `File Ingestions` 탭(단, FAILED 필터 수동 전환 필요) | `Workspaces` 행 선택→Edit Parser, 또는 `Code Editor` 탭 | `Workspaces` 탭(단, 건강도 정보 없음) | `File Ingestions`의 Retry | **UI 없음** — 디렉터리/config 수작업 + Reload 버튼 |
| **Chain** | `Outbox Failures` 탭(이름이 chain임을 드러내지 않음) | `Mappers` 탭(읽기) + `Chain Rules` 행→Edit Mapper + `Code Editor` | `Chain Rules` 탭 | `Outbox Failures`의 Retry | **UI 없음** — 룰 json 수기 |
| **Auto Update** | `Auto Updates`의 last_status/last_error | 행 선택→Edit Collector Script | `Auto Updates` 탭 | Run Now | **UI 없음** |
| **Enrichment** | **전무** | **전무** | **전무** | **전무** | **전무** — `server/config/enrichment_rules.json`은 gitignored(`.gitignore:44 server/config/*`) 수기 편집. 관리 뷰 자체가 없음 |

- **Chain 한 파이프라인이 4개 탭에 파편**(Outbox Failures + Chain Rules + Mappers + Code Editor). Mappers 탭은 사실상 Chain Rules의 부속 정보(mapper_module 필드의 실체)인데 별도 최상위 탭이다.
- **Auto Update만 유일하게 한 탭에 생애 대부분이 모여 있음**(현황+오류+실행+수정) — 나머지 파이프라인이 지향해야 할 원형.
- **"신규 추가" 단계는 4개 파이프라인 전부 공백.** 특히 서버는 config 추가→리로드→즉시 사용이 이미 뚫려 있으므로(이슈 #7 해소) 온보딩 UI의 서버측 전제는 갖춰져 있다.

### 1.2 크로스탭 단절 실증 (라이브 데이터)

`bonding_log` 파이프라인이 현재 실제로 아픈데, 어느 탭도 이를 보여주지 못한다:
- `Auto Updates` 탭: `generate_bonding.py` **SUCCESS** (2분마다 파일 생성 — 겉보기 건강)
- `File Ingestions` 탭: `eqp_bonding_log_*.csv` **동일 오류 42건 반복 실패**(directory_watcher.py:195 ValueError) — 단, FAILED 필터로 전환해야 보임 (기본 ALL에선 SUCCESS 로그에 파묻힘)
- `Workspaces` 탭: bonding_log 행은 config✓/1 file — **건강해 보임**

"수집기는 도는데 파서가 죽어 데이터가 2분마다 유실 중"이라는 인과 사슬을 파악하려면 3탭 왕복 + 필터 전환 + 행별 진단 클릭이 필요하다. 파이프라인 축이면 한 행이다.

### 1.3 용어·키 갭

- "Outbox Failures"는 구현 패턴 용어. 사용자 언어는 "chain 실패". 헤더 부제 "Chained Ingestion Failure Monitor"(admin.html:494)도 페이지 실체(7탭 시스템 어드민)와 불일치.
- Outbox 목록의 1열이 풀 UUID(Transaction ID) — 구현 관점 키. 사용자 관점 키(어느 룰/어느 타깃 테이블이 실패했나)는 2·3열에 밀려 있다.

---

## 2. 축 2 — 과업·마이크로 UX 발견

### 2.1 과업 차단 (Blocker)

| # | 발견 | 근거 | 개선안(1줄) |
|---|---|---|---|
| B1 | **인라인 에디터 열림 중 좌측 행 클릭 → 화면 무반응처럼 보임.** 진단 패널과 에디터가 동시 표시 상태가 되어(라이브 계측: 두 섹션 각 861px가 overflow:hidden 컨테이너에 스택) 진단이 클립됨 | `select*Row`(admin.js:737–1025)가 `editorContentWrapper`를 닫지 않음 · `openInlineEditor`(:1374) | 모든 `select*Row` 진입부에서 에디터 뷰 닫기(dirty면 확인 후) |
| B2 | **에디터 unsaved 변경 보호 전무** — 다른 트리 파일 클릭(`selectEditorFile` :1334 무조건 `setValue`), 탭 전환, 페이지 이탈 모두 경고 없이 편집 내용 유실. "파서 핫픽스" 핵심 과업의 데이터 유실 리스크 | admin.js:1318–1349, dirty 추적 부재, beforeunload 없음 | Monaco `onDidChangeModelContent`로 dirty 추적 + 전환/이탈 가드 + 저장 버튼에 dirty 도트 |
| B3 | **5,716건 로그에 검색·정렬·기간필터 없음, 10건 고정 페이지(572쪽), 페이지 점프 없음** — "특정 파일 실패 원인 찾기"가 페이지네이션 노가다. 오류 내용은 행 선택 전까지 안 보임 | admin.js:16(`fileLimit=10` 고정) · admin.html 파일 테이블 컬럼 구성 | 파일명/테이블 검색 입력 + 페이지 크기 선택 + 목록에 오류 요약 컬럼 (서버 쿼리 지원 필요 → §4) |

### 2.2 마찰 (Friction)

| # | 발견 | 근거 | 개선안(1줄) |
|---|---|---|---|
| F1 | Retry 후 **결과 확인 불가**(outbox): 목록에서 낙관적 제거만 하고 끝 — 재실패해도 수동 Refresh 전까지 모름 | `retryTransaction` admin.js:1080–1085 | 재시도 후 수 초 폴링해 재실패 시 토스트+행 복귀, 또는 상태 컬럼(RETRYING) 표시 |
| F2 | **자동 갱신 없음** — 모니터링 페이지인데 폴링/WS 미사용, 수동 Refresh 의존 | admin.js 전역(interval/WS 부재) | 30s 자동 갱신 + "마지막 갱신 hh:mm:ss" 표시 |
| F3 | Refresh 토스트가 **fetch 완료 전 무조건 success** — 실패 시 success·error 토스트 동시 출현 | admin.js:165–181(`fetchData()` await 없이 토스트) | fetch 완료 후 조건부 표시(또는 토스트 제거, 갱신 시각으로 대체) |
| F4 | **동일 오류 42건이 개별 행 나열** — 오류 시그니처/테이블별 묶음 없음, 신규 오류가 반복 오류에 파묻힘 | 라이브: bonding_log 42건 전부 동일 traceback | 동일 (table, 오류 1줄) 그룹 접기 + 건수 배지 |
| F5 | **로딩 상태 전무**: 탭 전환·페이지 이동 시 스피너 없이 이전 데이터가 그대로 → 갱신 여부 오인. fetch 실패 시에도 스테일 행 잔존(in-panel 오류 상태 없음) | `fetchData` admin.js:324–383 | 패널 로딩 오버레이 + 실패 시 테이블 자리에 오류 상태(재시도 버튼) |
| F6 | **Total 카운터 오표시**: 탭 공용인데 Code Editor 탭에서 직전 탭 값 잔존(라이브: "Total: 4" 그대로) | `renderEditorTree`(:1206)가 미갱신 | 탭별 라벨 명시("Failed: N" 등), editor 탭에선 숨김 |
| F7 | **Copy 버튼이 Auto Updates 탭에서 무반응**(무피드백 no-op) — 라이브 확인: 클릭해도 토스트 0 | copy 핸들러 admin.js:190–219에 `autoupdate` 분기 누락 | 분기 추가 또는 "현재 payload 뷰 텍스트 복사"로 단순화 |
| F8 | **풀 UUID + break-all → 행 높이 86px**(계측), 화면당 ~8행 — 스캔 밀도 저하 | admin.js:417(word-break) · admin.html:538(260px) | 8자 축약+hover 풀표시+copy 아이콘, 풀 ID는 우측 패널로 |
| F9 | Auto Updates 테이블 **고정폭 합계가 좌패널 기본폭 초과** → 가로 스크롤 + Actions 열 잘림(1280px, flex 3:2 기준) | admin.html:648–654(160+130+170+170+100+120+α) | 타임스탬프 축약 포맷·Next/Last Run 통합 등 컬럼 다이어트 |
| F10 | 네이티브 `confirm()` 6종 — 테마/타이포 불일치, 문구 장황, Enter 오폭 위험 | admin.js:185,249,258,433,512,718 | 공용 테마 모달(파괴적 액션만 유지, 단건 Retry는 undo 토스트로) |
| F11 | **키보드 접근 불가**: 행 선택 마우스 전용(tr 포커스 불가, 라이브 tabIndex=-1), 탭 버튼에 tab 시맨틱·:focus-visible 없음 | admin.html 스타일 · admin.js 행 생성부 | 행 `tabindex=0`+Enter 선택+방향키 이동, 탭에 `role=tablist/tab` |

### 2.3 폴리시 (Polish)

| # | 발견 | 근거 | 개선안(1줄) |
|---|---|---|---|
| P1 | 타임스탬프 포맷 불일치: `toLocaleString()` "2026. 7. 25. 오전 6:48:09" vs 오토업데이트 원시 "2026-07-25 13:30:00" — 장황·비정렬 | admin.js:408,485 vs :704–705 | mono 폰트 `MM-DD HH:mm:ss` 단일 포맷 + 상대시간("2분 전") 병기 |
| P2 | 색 시맨틱 오용: **실패 행의 파일명도 success 초록**(파일·맵퍼·수집기 이름 전부 초록), Retries는 0이어도 warning 주황 볼드 | admin.js:495,661,702 / :420,498 | 이름류는 `--text`+mono로, 색은 상태 배지에만 |
| P3 | 페이지 정체성: 타이틀 "Ingestion Outbox Admin / Chained Ingestion Failure Monitor" ≠ 실체(시스템 어드민) — §1.3과 연동 | admin.html:8,493–494 | IA 재편 시 "Pipeline Admin" 계열로 개칭 |
| P4 | i18n 혼재: UI 크롬 영문 + 토스트/컨펌 한글 | admin.js 토스트 전반 | 한 언어로 통일(사용자 R&D 엔지니어 기준 결정) |
| P5 | 에디터 트리: 폴더 제목 `cursor:pointer`인데 접기 미구현(어포던스 거짓), 트리 검색 없음 | admin.html:401–414, admin.js 폴더 클릭 핸들러 부재 | 접기 구현 또는 pointer 제거 + 파일 필터 입력 |
| P6 | 빈 상태(🎉/📁/🔗)는 양호. 오류 상태 부재는 F5로 귀속 | — | — |
| P7 | **양 테마 회귀 없음**(라이브 토글 검증: 토큰 전환·Monaco vs/vs-dark 동기화 정상). 토큰 별칭(--color-primary 등)도 tokens.css:130–138에 정의 확인 | — | — |

### 2.4 알려진 결함 재확인 (중복 보고 제외)
- `fetchItems` null 컨테이너 콘솔 에러 — 라이브 콘솔에서 재관찰(기존 칩 있음, 미보고).
- sticky 헤더 z-order — 수정 상태 확인.

---

## 3. 우선 개선 패키지 (파이프라인 IA 재편 전제)

### 소안 — "현행 7탭 유지 + Pipeline Health 스트립" (표현 계층 중심, 1–2일)
- 탭 바 위에 **파이프라인 4카드 요약 스트립** 추가: File Ingestion(실패 N/24h 처리량) · Chain(outbox 실패 N/룰 N) · Auto Update(최근 실행 상태) · Enrichment(규칙 N — 읽기 전용). 카드 클릭 → 해당 탭+필터 딥링크. **기존 `/admin/*` API 재사용으로 구현 가능**(enrichment만 규칙 조회 API 확인 필요).
- 동봉 수리: B1(에디터/진단 겹침) B2(dirty 가드) F3 F6 F7 F8 P1 P2 — 전부 표현 계층.
- 효과: §1.2의 크로스탭 단절이 최소 비용으로 완화. 리스크 최소.

### 중안 — "탭 축을 파이프라인으로 재편" (IA 재구성, 3–5일)
- 탭 구조: **[Overview] [File Ingestion] [Chain] [Auto Update] [Enrichment] [Code Editor]**
  - File Ingestion 탭 = 현행 File Ingestions(로그) + Workspaces(구성) 서브뷰 통합
  - Chain 탭 = Outbox Failures(오류) + Chain Rules(구성) + Mappers(코드) 통합 — 룰 행을 펼치면 해당 룰의 실패 tx·mapper 함수가 한 화면
  - Enrichment 탭 = 규칙 읽기 뷰부터(편집은 대안으로)
- 기존 API 그대로, 클라이언트 조합만 변경. 마이크로 수리(소안 목록) 포함.
- 효과: 사용자 멘탈 모델과 1:1 정렬, "outbox=chain 실패" 용어 갭 해소.

### 대안 — "파이프라인 상세 페이지 + 온보딩" (신규 API 다수, 총괄·Server PM 협의 필수)
- 파이프라인별 상세 뷰: 현황(처리량/최근 실행 타임라인) · 오류(그룹핑+재시도) · 구성(룰/워크스페이스 편집) · 실행(수동 트리거) · **온보딩 위저드**(신규 테이블: config 작성→검증→Reload→테스트 파일 투입까지 — 이슈 #7로 서버측 흐름은 이미 지원).
- 필요 신규 API: enrichment rules CRUD, chain rule CRUD, 워크스페이스 생성/config 검증, 파이프라인 헬스 집계.
- 효과: "4 파이프라인의 유기적 생애관리"라는 목표 상 완성형.

**권고**: 소안을 즉시(마이크로 수리+Health 스트립), 중안을 다음 사이클로. 대안은 중안 사용 피드백 후 API 스펙 협의.

---

## 4. 로직 변경 필요 항목 (Client PM / Server PM 이관)

| 항목 | 성격 |
|---|---|
| B3 검색/필터 — `/admin/file-ingestion/logs`에 filename/table 검색 쿼리 파라미터 | Server PM (엔드포인트 확장) |
| F1 재시도 후 상태 폴링, F2 주기 자동 갱신 | Client PM (데이터 로직) |
| 소안 Health 스트립의 enrichment 규칙 수 조회 | Server PM (경량 조회 API 1개) |
| 대안의 신규 CRUD API 일체 | 총괄 승인 후 Server PM |

## 5. 교훈 제안 (총괄 검수용 — 직접 추가 안 함)
- 브라우저 pane이 대형 캔버스를 다운스케일해 스크린샷 판독·ref 좌표 클릭이 모두 불안정한 경우가 있다 → 상호작용 검증은 JS `dispatchEvent`/`click()` 직접 호출로, 상태 확인은 computed-style/getBoundingClientRect 계측으로 수행하면 신뢰 가능.
