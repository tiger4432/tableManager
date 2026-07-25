# 보고서: admin UX 소안 — 차단 수리 + 마이크로 수리 + 파이프라인 헬스 스트립

- **작성**: Client PM | **일자**: 2026-07-25 | **지시서**: `agent_workspace/tasks/Client_admin_ux_small_task.md`
- **브랜치**: `worktree-agent-a1050ee24cd051268` (worktree — main 병합·빌드는 총괄)
- **변경 파일**: `client2/admin.html`, `client2/src/admin.js` (+ `docs/architecture/CODE_MAP.md` §7 admin.js 항목 동기화)
- **검증**: `node --check` 통과 (ESM). **시각 검증은 통합 시 필요** — worktree엔 node_modules가 없고 admin.js가 `import './tokens.css'`(Vite 전용)를 쓰므로 dev 서버/빌드 없이는 브라우저 구동 불가. 하단 "통합 검증 체크리스트" 참조.

---

## A. 차단 결함 3건 (before → after)

### B1 — 에디터 뷰 스택 클리핑
- **before**: 인라인 에디터 열림 중 좌측 행 클릭 시 `select*Row`가 진단 패널만 `flex`로 켜서 에디터와 동시 표시(각 861px 스택, overflow:hidden에 클립) → 무반응처럼 보임.
- **after**: 신설 `ensureEditorViewClosed()`(admin.js ~948)를 5개 `select*Row` 진입부에 배선. 에디터 뷰가 열려 있으면 닫고 진행하되, **dirty면 confirm — 취소 시 행 선택 자체를 중단**. Monaco 내용은 유지되므로 같은 파일 재오픈 시 미저장 변경 보존. 부수 수리: `clearDiagnostics`가 인라인 에디터 활성 중 빈 상태를 겹쳐 켜지 않음, `closeInlineEditor`에서 복원할 선택이 없으면 빈 상태로 정리, 자동갱신/재선택 루프는 `isInlineEditorActive` 중 skip.

### B2 — 에디터 unsaved 보호
- **before**: dirty 추적 전무. 다른 트리 파일 클릭 시 무조건 `setValue`로 유실, beforeunload 없음.
- **after**: `onDidChangeModelContent`로 dirty 추적(프로그램틱 setValue는 `suppressDirtyTracking`으로 제외). ① `selectEditorFile` — 다른 파일 이동 시 confirm(취소 시 트리 하이라이트 원복), **동일 파일 재선택 시 서버 리로드로 덮어쓰지 않음**(편집 보존). ② `beforeunload` 가드. ③ 저장 버튼에 미저장 도트(`● var(--warning)`), 저장 성공 시 `markEditorClean`. ④ 탭 전환은 뷰만 닫고 내용 보존(재오픈 시 복원)이라 confirm 없이 무손실.

### B3 — 파일 로그 탐색성 (5,716건·10건 고정)
- **before**: `fileLimit=10` 고정, 정렬 없음.
- **after**: ① 푸터에 페이지 크기 선택 **10/50/100**(활성 탭의 limit에 적용, outbox에도 동작, 탭 전환 시 값 동기화). ② 파일 테이블 6개 헤더 클릭 정렬(현재 페이지 내 클라이언트 정렬, ▲/▼ 표시자, 숫자/문자 구분 비교) — 서버측 정렬·파일명 검색은 API 파라미터 필요라 **중안 이관**(하단). ③ status 필터는 기존 유지.

## B. 마이크로 수리 8건

| # | 항목 | after |
|---|---|---|
| 1 | Retry 피드백 (F1) | `retryTransaction`: 낙관적 제거 폐기 → info 토스트 후 3초 뒤 재조회로 확정. 잔존 시 warning("재시도 후에도 실패 상태") + 행 유지, 해제 시 success. `retryFileIngestion`: 동기 처리라 즉시 재조회 — status FAILED 잔존 시 warning. 양쪽 모두 헬스 스트립 동시 갱신 |
| 2 | Refresh 토스트 (F3) | `fetchData`가 성공 여부 반환 → **완료 후** 성공 시에만 탭별 메시지 토스트(실패 시 error 토스트는 fetchData 담당, 이중 출현 해소). autoupdate/editor 탭 메시지도 보강 |
| 3 | Copy no-op (F7) | `autoupdate` 분기 추가 + 미선택 시 warning 토스트(무피드백 no-op 제거) |
| 4 | UUID 축약 (F8) | outbox 1열 head8…(`single_` 접두 유지형) + title 풀값 + **클릭 복사**(`.tx-id-chip`, stopPropagation). 컬럼 260px→130px, word-break 제거로 행 높이 정상화. Retry confirm 문구도 축약 ID |
| 5 | 타임스탬프 단일화 (P1) | `formatTimestamp` — `MM-DD HH:mm:ss` mono 단일 포맷(ISO/원시 슬라이스 처리로 타임존 재해석 없음, title 풀값). outbox failed_at·file created_at·autoupdate next/last_run 적용, Next/Last Run 컬럼 170→140px (F9 완화) |
| 6 | 실패 색상 (P2) | 파일명·스크립트명·맵퍼명·워크스페이스 스크립트명 success 초록 → `--text`+mono (상태색은 배지 전용). Retries는 0이면 `--text-dim`, >0만 warning 볼드 |
| 7 | 탭 전환 fetch 레이스 | `fetchSeq` 시퀀스 + 발화 시점 탭 캡처 — await 후 stale이면 렌더/토스트 모두 폐기. **칩 task_d3326d6c(fetchItems null 에러)와 동근원(늦은 응답의 잘못된 렌더)을 흡수** — 총괄이 칩 dismiss 판단 요망 |
| 8 | 절제된 자동 갱신 (F2) | 30s 인터벌: 헬스 스트립 상시 + Outbox/File 탭만 silent 재조회. `document.hidden`·인라인 에디터 활성·dirty·editor 탭이면 skip. 헤더에 "갱신 HH:mm:ss" 표시(`markRefreshed`) |

- 보너스(F6, 1줄): editor 탭에서 직전 탭 Total 잔존 → `switchTab`이 라벨 숨김.

## C. 파이프라인 헬스 스트립

- 헤더 아래 `#health-strip` — **File Ingestion / Chain / Auto Update / Enrichment 4카드** 상시 표시. 카드 = 상태 도트(ok 초록/warn 주황/danger 빨강 — `data-status` + 토큰) + 핵심 수치 + 보조줄. 그리드 4열(1100px 미만 2열), tokens.css 시맨틱 토큰만 사용(공용 파일 무수정), 양 테마 대응, hover 1px lift만(과장 없음).
- **기존 API만 조합** (신규 서버 API 0):
  - File: `/admin/file-ingestion/failed?limit=100` → total. 실패>0 danger.
  - Chain: `/admin/outbox/failed?limit=1` → total(실패 tx 그룹 수).
  - Auto Update: `/admin/auto-update/status` → FAIL 수집기 수. **감사 §1.2 실증 시나리오 반영**: 수집기 전부 SUCCESS라도 auto-update 대상 테이블 ∩ 최근 실패 로그(위 100건 재사용) 교집합이 있으면 `warn` + "산출물 인제션 실패 N건" — bonding_log 케이스가 카드에서 즉시 보임.
  - Enrichment: `/enrichment/rules` + 규칙별 `/tables/{derived}/data?limit=1&filters={blank}` total 합산(ui.js `updateEnrichmentBadge`와 동일 로직 재사용). 결손>0 warn.
- 클릭 딥링크: File → File Ingestions 탭+FAILED 필터 / Chain → Outbox 탭 / Auto Update → Auto Updates 탭 / Enrichment → `/enrichment.html`. 탭 전환은 신설 `switchTab()`으로 버튼 클릭과 공용화.
- 갱신: 초기 로드 + 30s 폴링 + 수동 Refresh + Retry 후. `healthRefreshInFlight`로 중첩 방지. 조회 실패 시 카드만 "상태 조회 실패"(무음 — 본문 흐름 비방해).
- 레이아웃: main의 `height: calc(100vh-72px)` 고정 폐기 → body `height:100vh` + main `flex:1; min-height:0` (스트립 삽입에도 패널 스크롤 유지).

## 경계 계약

변경 없음 — 소비 REST 경로/응답 형태·WS·셀 계약 모두 불변(읽기 조합만 추가). tokens.css 등 공용 파일 무수정.

## 중안 이관 목록 (신규/확장 서버 API 필요분)

1. `/admin/file-ingestion/logs`에 **filename/table_name 부분 검색 파라미터** (B3 잔여 — "특정 파일 실패 찾기"의 완결에 필수).
2. 동 엔드포인트 **서버측 정렬 파라미터**(`sort`, `dir`) — 현재는 페이지 내 정렬만 가능함을 헤더 title로 고지 중.
3. **파이프라인 헬스 집계 API 1개**(`/admin/pipeline/health` 류) — 현재 스트립은 4~6회 fetch 조합(enrichment 규칙 수에 비례). 규칙이 늘면 단일 집계가 경제적.
4. auto-update 산출물 인제션 실패의 정확 카운트 — 현재는 최근 실패 100건 내 교집합(초과 시 `N+` 표기). `table_name` 필터 파라미터(1번과 동일)로 정확해짐.
5. (감사 F4) 동일 오류 시그니처 그룹핑 — 서버 집계 지원 필요.

## 통합 검증 체크리스트 (총괄 — 본체 빌드 후)

1. `cd client2 && npm run build` → dist 커밋.
2. 라이트/다크 양 테마에서 헬스 스트립 4카드 색·수치 확인(특히 bonding_log 시나리오: Auto Update 카드 warn + "산출물 인제션 실패 N건").
3. 인라인 에디터 열고 코드 1자 수정 → 좌측 행 클릭 → confirm 출현·취소 시 에디터 유지 확인. 같은 파일 재오픈 시 편집 보존 확인.
4. 파일 탭 100/page + Filename 헤더 정렬 + 카드 딥링크(FAILED 필터 자동 적용) 확인.
5. 새로고침(F5) 시 dirty 상태에서 브라우저 이탈 경고 확인.

## 히스토리 초안 (총괄 일괄 기록용)

> **2026-07-25 · client2/admin — UX 소안**: 차단 3건(에디터 뷰 스택 클리핑·unsaved 보호·파일 로그 페이지 크기/정렬), 마이크로 8건(Retry 실결과 피드백, Refresh 토스트 실결과화, Copy autoupdate 분기, UUID head8 축약+클릭복사, 타임스탬프 MM-DD HH:mm:ss 단일화, 이름류 중립색, fetch 레이스 가드, 30s 절제 폴링+갱신 시각), 파이프라인 헬스 4카드 스트립(기존 API 조합, 탭+필터 딥링크, auto-update×파일 실패 연계 수치) — `Admin_ux_audit.md` 소안 범위. 신규 서버 API 없음, 경계 계약 불변.

## 교훈 제안 (총괄 검수용 — 직접 추가 안 함)

- worktree에서는 Vite 전용 문법(`import './tokens.css'`) 때문에 브라우저 시각 검증 자체가 불가하다(빌드·dev 서버 모두 node_modules 필요). worktree 위임 지시서에 "시각 검증은 통합 후 총괄/본체에서" 단계를 명시하면 왕복이 준다.
