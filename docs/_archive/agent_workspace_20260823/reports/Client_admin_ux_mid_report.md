# 보고서: admin UX 중안 — 파이프라인 생애주기 축 탭 재편

- **작성**: Client PM | **일자**: 2026-07-25 | **지시서**: `agent_workspace/tasks/Client_admin_ux_mid_task.md`
- **브랜치**: `worktree-agent-aa5726ab0a2bd1072`, 커밋 `3e599d2` (main 병합·빌드는 총괄)
  - 선행 조치: worktree 베이스가 소안(7d02989) 이전이어서 **main을 브랜치로 역병합**(`327358c`)해 소안 자산 위에 증축함. 총괄 병합 시 이 merge 커밋 포함됨.
- **변경 파일**: `client2/admin.html`(전면 재작성), `client2/src/admin.js`(전면 재작성, 단일 파일 유지 — vite 엔트리 불변, admin_*.js 분리 불필요 판단: 상태 공유가 조밀해 분리 시 오히려 복잡)
- **검증**: `node --check src/admin.js` 통과. JS의 정적 `byId` 참조 전수 ↔ admin.html id 전수 교차 대조 완료(불일치 0 — 교훈 파일 "잔존 게터" 함정 예방). 시각 검증은 worktree 제약(소안 보고서와 동일: Vite 전용 import)으로 **통합 후 총괄/본체에서** — 하단 체크리스트.

---

## A. Before → After IA 매핑

| 구 탭 (메커니즘 7탭) | 신 위치 (파이프라인 5탭) | 비고 |
|---|---|---|
| (없음) | **Overview** (첫 화면) | 소안 헬스 스트립의 확장판이 본문 — 4카드(상세 수치+최근 이벤트 3건 미리보기+탭 딥링크), 좌패널 전폭(우패널·리사이저·스트립 숨김) |
| Outbox Failures | **Chain** §오류·실행 "Chain 실패 (Outbox Transactions)" | 사용자 진단(outbox fail = chain fail) 반영해 명칭·소속 정정. Retry/Retry All/페이지네이션 유지 |
| Chain Rules | **Chain** §현황 | 룰 행 → 진단 + Edit Mapper 딥링크(기존) |
| Mappers | **Chain** §코드·수정 | 행별 **🛠️ Edit 버튼 신설**(`mappers/<filename>` 즉시 오픈) |
| File Ingestions | **File Ingestion** §오류·실행 | 필터·정렬·페이지크기(소안 B3) 유지. 상태 필터는 헤더→섹션 헤더로 이동 |
| Workspaces | **File Ingestion** §현황 (기본 접힘) | 헤더에 요약("config 누락 N · 커스텀 파서 N개") — 접혀 있어도 건강도 1줄 노출. 14행이 로그를 밀어내지 않도록 기본 접힘 |
| Auto Updates | **Auto Update** §현황·실행 | 기존 그대로 + §오류 "산출물 인제션 실패" 섹션 신설(아래) |
| (없음) | **Enrichment** §현황 | `/enrichment/rules` + 규칙별 결손 카운트(blank 필터 total, ui.js 배지와 동일 로직) + 규칙별/전역 Queue 딥링크(`enrichment.html?rule=`) + read-only 편집 안내 노트 |
| Code Editor | **공용 뷰** (탭 아님) | 각 탭의 편집 딥링크(파서/맵퍼/수집기)로 진입. 트리 대체로 에디터 헤더에 **파일 피커**(optgroup: Mappers/Parsers/Collectors, `/admin/scripts/list` 캐시). 소안 dirty 가드·뷰 스택 자산 전부 재사용 |

**생애 단계 규율**: 각 탭 본문 = 접이식 스택 섹션(stage-chip: 현황 → 오류 → 수정/실행 순 상→하). "신규 추가"는 현재 API로 불가한 파이프라인 전부이므로 **placeholder 없이 생략**(지시대로 빈 껍데기 금지) — 유일한 예외적 표기는 Enrichment의 read-only 안내(공백을 "보이게"하라는 지시 이행).

**유기적 연계 신설 3건** (기존 API만으로):
1. **Auto Update §오류 — 산출물 인제션 실패**: auto-update 대상 테이블 ∩ `/admin/file-ingestion/failed?limit=100` 교집합을 표로 상설(초과 시 `N+`). 행 클릭 → 파일 진단, Retry 가능. 감사 §1.2 bonding_log 시나리오("수집기 SUCCESS ≠ 데이터 도착")가 탭 안에서 인과 사슬로 보임.
2. **Outbox 실패 진단 → Edit Mapper**: 이벤트 테이블과 매칭되는 chain rule(`trigger_table`/`target_table`)의 mapper를 진단 패널에서 바로 편집(`showEventDiagnostics`).
3. **파일 로그 진단 → Edit Parser**: 실패 로그의 대상 테이블 워크스페이스 커스텀 파서를 진단 패널에서 바로 편집(`selectFileRow` — File 탭·Auto Update 연계 표 공용).

## B. 구 탭 딥링크 → 신 탭 호환 표 (해시 라우터)

신설 라우터: `#<key>` 해시(+ `?tab=` 쿼리 폴백), 탭 전환 시 `history.replaceState`로 해시 동기(북마크 가능, 히스토리 스팸 없음), `hashchange` 청취.

| 진입 URL | 동작 |
|---|---|
| `#overview` / 해시 없음 / 미지의 키 | Overview (첫 화면) |
| `#file` (구·신 동명) | File Ingestion 탭 |
| `#outbox` (구) | **Chain 탭** |
| `#workspace` (구) | **File Ingestion 탭** |
| `#chain` (구·신 동명) | Chain 탭 |
| `#mapper` (구) | **Chain 탭** |
| `#autoupdate` (구·신 동명) | Auto Update 탭 |
| `#enrichment` (신) | Enrichment 탭 |
| `#editor` (구 Code Editor 탭) | 공용 에디터 뷰(파일 피커로 브라우즈) — Monaco 로딩 전 진입 시 대기 후 자동 오픈(`pendingEditorOpen`) |
| `#editor=<encoded path>` (신) | 해당 스크립트 즉시 오픈. 에디터에서 파일 전환 시 해시도 추종 |

(참고: 코드베이스 전수 grep 결과 구 탭으로의 외부 링크는 0건 — `index.html`의 `/admin.html` 단순 링크뿐. 별칭은 북마크/습관 호환용 보험.)

## C. 소안 자산 재사용 현황 (중복 구현 0)

| 소안 자산 | 중안에서의 재사용 |
|---|---|
| `switchTab()` | 5탭 정의로 재편 + `opts.statusFilter` 딥링크 옵션 + 해시 동기 + Overview 전폭 레이아웃 훅 |
| `fetchSeq` 레이스 가드 | 유지 — 탭당 다중 fetch(Promise.all)를 한 seq로 묶어 stale 렌더 차단 |
| 헬스 스트립 전체 | 유지(파이프라인 탭에서 상시) — Overview에선 본문이 확장판이므로 숨김. 카드 딥링크는 신 탭으로 갱신, enrichment 카드는 외부 페이지 대신 Enrichment 탭으로 |
| 에디터 dirty 가드 일습 (`ensureEditorViewClosed`·`selectEditorFile` 확인·beforeunload·dirty 도트) | 유지 — 트리 하이라이트 복원만 피커 복원(`syncEditorPicker`)으로 치환 |
| `formatTimestamp`·`shortTxId`·`markRefreshed`·30s 절제 폴링·Retry 실결과 피드백(F1)·Refresh 실결과 토스트(F3) | 유지. 폴링 대상은 Overview/File/Chain으로 조정(에디터 활성·dirty·hidden 스킵 동일) |
| enrichment 결손 카운트 로직 | `fetchEnrichmentStatus()`로 단일화(15s TTL 캐시) — 스트립·Enrichment 탭·Overview 3소비처 공용, 수동 Refresh/Reload Configs 시 캐시 강제 만료 |

**추가 정리**: Total 카운터(감사 F6의 근원)를 전역 헤더에서 제거 → 섹션별 카운트 배지(`data-tone`)로 대체. Retry All도 전역 헤더 → 해당 섹션 헤더로. 한 탭 다중 테이블화에 따라 `clearRowHighlights()`(전 목록 하이라이트 일괄 해제)·`clearSelections()` 신설로 크로스 섹션 하이라이트 누수 방지.

## D. 기존 API만 사용 (신규 서버 API 0 · 경계 계약 불변)

소비 엔드포인트: `/admin/outbox/failed`, `/admin/file-ingestion/{logs,failed,workspaces,retry-failed}`, `/admin/chain/rules`, `/admin/mappers/list`, `/admin/auto-update/{status,run-now}`, `/admin/scripts/{list,code}`, `/admin/reload-configs`, `/admin/outbox/retry-failed`, `/enrichment/rules`, `/tables/{t}/data`(blank 필터 카운트). 전부 기존. 응답 형태·WS·셀 계약 무접촉. tokens.css 등 공용 파일 무수정(페이지 전용 CSS만 admin.html `<style>`에 추가), 양 테마는 시맨틱 토큰만 사용으로 대응.

## E. 대안(온보딩 위저드·CRUD) 이관 목록

소안 이관분(파일 로그 서버 검색/정렬, 헬스 집계 API, `table_name` 필터, 오류 그룹핑) **유지** + 중안에서 추가 확인분:
1. **Enrichment 규칙 CRUD API** — 현재 read-only 안내로 공백만 가시화. `server/config/enrichment_rules.json`이 gitignored 수기 편집이라 UI 편집은 서버 API 필수.
2. **Chain rule CRUD API** — Chain 탭 §현황은 조회 전용. "신규 추가" 단계의 실구현은 대안.
3. **워크스페이스 생성/config 검증 API** — File 파이프라인 온보딩(이슈 #7로 서버 흐름은 열려 있음).
4. **파이프라인별 "신규 추가" 위저드 UI** — 위 1–3 API 합류 후 각 탭 최하단 섹션으로 증축(현재는 지시대로 생략).
5. Overview 최근 이벤트의 **시간창 통계**(24h 처리량 등) — 현 API는 상태 스냅숏뿐이라 카운트만 표시 중. 집계 API(소안 이관 3번)와 동건.

## F. doc-keeper 인계 — admin.js 함수 목록 (CODE_MAP §7 갱신용, 본 보고서로만 전달)

신규: `byId`, `setSectionCount`, `mapperModuleToPath`, `parseRoute`, `applyRoute`, `isEditorViewOpen`, `updatePanelLayout`, `buildFileLogRow`, `renderLinkedFailTable`, `renderEnrichmentTable`, `fetchOverview`, `ovEventItem`, `ovCard`, `renderOverview`, `clearSelections`, `clearRowHighlights`, `selectEnrichmentRow`, `populateEditorPicker`, `buildEditorPickerOptions`, `syncEditorPicker`, `fetchEnrichmentStatus`
변경: `switchTab`(5탭+opts+해시), `setupEventListeners`, `fetchData`(탭당 병렬 fetch), `renderOutboxTable`/`renderFileTable`/`renderWorkspaceTable`/`renderChainTable`/`renderMapperTable`/`renderAutoUpdateTable`(섹션 카운트·하이라이트), `selectTxRow`/`selectFileRow`(bodyEl 파라미터)/`selectWorkspaceRow`/`selectChainRow`/`selectMapperRow`/`selectAutoUpdateRow`, `showEventDiagnostics`(+mapper 딥링크), `clearDiagnostics`, `updatePaginationFooter`(file/chain), `retryTransaction`/`retryFileIngestion`/`retryAllFailed(kind)`, `reloadSystemConfigs`(캐시 만료), `initMonacoEditor`(+pending open), `selectEditorFile`(피커), `openInlineEditor`(path 옵션+레이아웃), `closeInlineEditor`(탭별 복원), `refreshEnrichmentHealth`(공용 상태 사용)
삭제: `renderEditorTree`, `createTreeFolder`, `createTreeSubFolder`, `createTreeFileItem` (에디터 좌측 트리 → 피커로 대체)

## G. 총괄 통합 검증 체크리스트 (본체 빌드 후)

1. `cd client2 && npm run build` → dist 커밋.
2. **라우팅**: `/admin.html` → Overview 첫 화면(전폭, 스트립·우패널 없음). `#outbox`·`#workspace`·`#mapper`·`#editor` 구 해시 각각 Chain/File/Chain/에디터 뷰로 진입 확인. `#editor=mappers/<실존파일>.py` 직접 오픈 확인.
3. **Overview**: 4카드 수치·최근 이벤트 3건·상태 도트, 카드/버튼 클릭 딥링크(File 카드는 실패>0일 때 FAILED 필터 프리셋). bonding_log류 시나리오에서 Auto Update 카드 warn + "산출물 인제션 실패 N".
4. **Chain 탭**: Rules→실패→Mappers 3섹션, outbox 실패 행 선택 → 진단에 🛠️ Edit Mapper 출현·클릭 시 해당 mapper 오픈. Retry All(섹션 헤더)·페이지네이션(하단 footer, 페이지 크기 outbox에 적용) 동작.
5. **File 탭**: Workspaces 기본 접힘+요약 문구, 로그 필터/정렬/페이지, 실패 로그 진단에 파서 편집 버튼(커스텀 파서 보유 테이블), Retry 후 실결과 토스트.
6. **Auto Update 탭**: Run Now, 산출물 인제션 실패 섹션(행 클릭 진단+Retry), 실패 없으면 🎉 빈 상태.
7. **Enrichment 탭**: 규칙 표+결손 배지, 규칙 행 진단(read-only 안내), Queue 버튼 → `enrichment.html?rule=<name>` 프리셀렉트 확인.
8. **에디터**: 딥링크 진입 → dirty 상태에서 좌측 행 클릭 confirm·탭 전환 무손실·피커로 파일 전환 시 dirty confirm(취소 시 피커 원복)·저장 도트. Overview에서 `#editor` 진입 시 우패널 복귀, Back 시 전폭 복귀.
9. 라이트/다크 양 테마에서 섹션 칩·카운트 톤·Overview 카드 확인. 리사이저 드래그 후 Overview 왕복 시 폭 복원 확인.
10. 30s 자동 갱신이 Overview/File/Chain에서만, 에디터 dirty 중 정지 확인.

## H. 히스토리 초안 (총괄 일괄 기록용)

> **2026-07-25 · client2/admin — UX 중안(IA 재편)**: 탭 축을 메커니즘 7탭에서 파이프라인 생애주기 5탭(Overview/File Ingestion/Chain/Auto Update/Enrichment)으로 재편. Chain 탭에 Outbox 실패(=chain fail)·Rules·Mappers 수렴, File 탭에 Workspaces 수렴, Auto Update 탭에 산출물 인제션 실패 연계 섹션, Enrichment 관리 뷰 신설(규칙+결손+Queue 딥링크, 편집 read-only 안내). Overview는 헬스 스트립 확장판 4카드 첫 화면. Code Editor는 독립 탭 폐지 → 편집 딥링크 공용 뷰+파일 피커, `#editor(=path)` URL 호환. 해시 라우터로 구 탭 별칭(`#outbox→chain` 등) 매핑. 생애 단계(현황→오류→수정/실행) 접이식 섹션 스택, 소안 자산 전부 재사용, 기존 API만 사용·경계 계약 불변. — `Admin_ux_audit.md` 중안 범위.

## I. 교훈 제안 (총괄 검수용 — 직접 추가 안 함)

- **worktree 베이스 확인 선행**: 병렬 위임 worktree가 선행 작업 병합 이전 커밋에서 분기되어 있을 수 있다. 착수 시 `git log main -- <대상 파일>`로 선행 커밋 포함 여부를 확인하고, 없으면 main을 자기 브랜치로 역병합한 뒤 증축할 것(이번 건: 소안 7d02989 부재 → `git merge main` 후 진행).
- 대규모 재작성 시 JS의 `getElementById` 참조 전수와 HTML id 전수를 grep 교차 대조하면(이번엔 불일치 0) "잔존 게터/유령 id" 류 함정을 기계적으로 차단할 수 있다.
