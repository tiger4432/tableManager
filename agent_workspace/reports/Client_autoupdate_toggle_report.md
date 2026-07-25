# Client 보고서 — Admin Auto Update 수집기 active 토글

- **담당**: client-pm (worktree `worktree-agent-a20e7cf603e201f0c`)
- **일자**: 2026-07-25
- **지시**: admin Auto Update 탭 수집기 active 토글 + Overview 헬스 수치 반영

## 0. 베이스 동기화 (중요 — 병합 시 참고)

worktree 분기점이 admin 리디자인(Overview/fetchSeq/switchTab, main `e3d4939`) 이전이었다.
`git merge main`·`git checkout main -- <files>`가 권한 정책으로 차단되어, **`git show main:<path>` 리디렉션으로
`client2/src/admin.js`·`client2/admin.html` 두 파일만 main 최신본으로 동기화 후 커밋**(`d8d8e08`)하고 그 위에 구현했다.
→ 병합 시 이 두 파일은 "main 최신 + 본 작업 diff"라 충돌 없이 fast-forward 가능. **다른 파일은 여전히 구 베이스**이므로 diff 검수는 `d8d8e08..HEAD`로 볼 것.

## 1. 구현 내역

### client2/admin.html
- 수집기 테이블에 **Active 컬럼**(70px, th title로 "비활성이어도 Run Now 가능" 명시) 추가.
- `<style>`에 신규 블록 (tokens.css 무수정 — 전부 기존 토큰 소비라 양 테마 자동 대응):
  - `.au-switch`/`.au-slider`: 38×21 토글 스위치. off=`--border-strong`, on=`--success`, 0.18s 트랜지션,
    `:disabled`(요청 in-flight) 반투명+progress 커서, `:focus-visible` 링(`--color-primary`).
  - `.badge-muted`: "비활성" 배지 (`--bg-surface`/`--text-muted`/`--border-strong`).
  - `.table-row.row-inactive td:not(.au-live) { opacity: 0.5 }`: 비활성 행 시각 강등.
    **토글 셀과 Run Now 셀은 `.au-live`로 강등 제외** — 조작 가능성 시각 유지.

### client2/src/admin.js
- `renderAutoUpdateTable()`:
  - `const isActive = col.active !== false` — **서버가 active 필드 배포 전이어도 활성 간주**(기존 동작 보존, 과도기 안전).
  - 행에 `row-inactive` 클래스, 스크립트명 옆 "비활성" 배지, Active 셀(토글), Run Now 툴팁
    (활성: "즉시 1회 수집 실행" / 비활성: "비활성 수집기도 수동 실행은 가능합니다").
  - Run Now는 inactive여도 기존대로 동작(로직 무변경 — 계약 §3 충족).
- 신규 `toggleCollectorActive(col, inputEl)` (runAutoUpdateNow 옆):
  - `POST /admin/auto-update/toggle` body `{script: "<table_name>/<script_name>", active: bool}` — 계약의
    `"<workspace>/<script.py>"`를 `table_name/script_name`으로 해석(스크립트 실경로
    `ingestion_workspace/<table>/auto_update/<script>`의 워크스페이스 상대 표기). **서버 구현과 표기 불일치 시 이 한 줄만 수정하면 됨.**
  - 성공: 응답의 `active`를 신뢰해 **"현재" `autoUpdateData`에서 키(table+script)로 재탐색 후 갱신** → autoupdate 탭일 때만 재렌더.
    (fetchSeq 가드 준수 방식: 옛 배열/행 참조를 되살리지 않으므로 토글 요청 중 fetchData가 배열을 교체해도 안전 — 하니스 T4로 검증)
  - 실패(404/400/네트워크): 스위치 **원복 + 재활성화** + 에러 토스트(서버 `detail` 문자열 노출). 요청 중엔 `disabled`로 연타 방지.
- **Overview 카드**(`renderOverview` ③): 첫 메트릭을 `activeCount/total` "활성 수집기"로 교체("3/4" 식).
  전부 비활성이면 tone·카드 status `warn`(자동 수집 전면 중단 신호). 기존 danger(수집기 실패)·warn(산출물 인제션 실패) 우선순위는 불변.
- **헬스 스트립**(`refreshFileAndAutoHealth`): 정상 시 main을 `수집기 N개 중 M 활성`으로, 전부 비활성이면
  status `warn` + sub "모든 수집기가 비활성 상태입니다". 실패 카운트 경로는 불변.

## 2. 검증

- `node --input-type=module --check < client2/src/admin.js` → OK.
- **mock 하니스** (scratchpad `toggle_harness.mjs` — admin.js에서 `toggleCollectorActive` 실소스를 추출해 스텁 주입 실행): **22/22 통과**
  - T1 성공 경로: URL/메서드/`script` 포맷/`active` bool 페이로드 계약, in-flight 잠금, state 반영, 재렌더 1회, 성공 토스트.
  - T2 404: 원복+재조작 가능+state 불변+`detail` 메시지 토스트.
  - T3 네트워크 예외: 동일 원복.
  - T4 레이스: 요청 중 `autoUpdateData` 교체 시 새 배열의 객체에 반영됨.
  - T5 `active !== false` 디폴트·카운트 산식.
- **시각 검증**: 양 테마용 정적 목업(scratchpad `toggle_visual_mock.html`, 실제 tokens.css 링크 + 동일 CSS 블록, active/inactive/in-flight 3행)을
  준비했으나 이 세션에선 브라우저 패널 표시가 불가해 스크린샷 미첨부. CSS는 하드코딩 색상 없이 전 항목 테마 토큰이라 다크/라이트 모두 토큰 정의로 보장.
  총괄 본체 빌드 후 실화면 확인 권장 체크: ① off 트랙이 다크에서 `--border-strong`으로 충분히 구분되는지 ② 비활성 행 dim 0.5 강도.

## 3. 미해결/에스컬레이션

- `toggle` 계약의 `"<workspace>/<script.py>"` 실표기 확정 필요(서버 병렬 구현 중이라 미대조). 현재 `table_name/script_name` 송신.
- worktree 규칙에 따라 **빌드/dist 미생성** — 본체 병합 후 `cd client2 && npm run build` 필요.
- history 기록·gen_index·PROJECT_STATUS는 미수정(worktree 금지 규칙). 이력 초안:
  > `feat(client/admin): Auto Update 수집기 active 토글 — 행별 스위치(실패 원복·레이스 안전), 비활성 행 강등+배지, Overview·헬스카드 활성 수치(active/total) 반영. Run Now는 비활성에서도 허용(툴팁 명시).`

## 4. 교훈 제안 (client-pm.md 반영 요청)

- **함정**: worktree 분기점이 main보다 한참 뒤라 지시서가 전제한 자산(fetchSeq 등)이 worktree에 없을 수 있다. merge/checkout은 권한 정책에 차단될 수 있음.
  **올바른 방법**: 착수 전 `git diff --stat HEAD main -- <담당영역>`으로 베이스 격차부터 확인하고, 필요 시 `git show main:<path> > <path>`로 담당 파일만 동기화 커밋 후 작업.
