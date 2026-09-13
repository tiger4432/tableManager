# 🧩 Enrichment Queue — 클라이언트 단계① 구현 보고 (Client PM)

> **Status:** ✅ 구현 완료(소스) / ⏳ 통합 검증 대기 | **작성:** 2026-07-25 | **Owner:** Client PM
> **기준:** 승인 계획서 `agent_workspace/reports/Client_enrichment_plan.md` 단계① · `docs/spec/ENRICHMENT_QUEUE_SPEC.md` §5 확정 계약
> **작업 위치:** git worktree 브랜치 `worktree-agent-aa72a89912c1994d5` (main 병합·push 안 함 — 총괄 검수 후 병합)

---

## 1. 변경 파일

| 파일 | 성격 | 내용 |
|---|---|---|
| `client2/enrichment.html` | 신설 | 3구역 레이아웃(워크리스트 \| 판단·입력 \| 참조뷰 placeholder) + 자체 포함 CSS(메인 페이지 디자인 토큰 동일 팔레트: Outfit/JetBrains Mono, cyan/glass). 규칙 미배포 안내용 setup 오버레이, `showToast` 계약(`#toast-container` + `.toast.toast-{type}`) CSS 포함 |
| `client2/src/enrichment.js` | 신설 | 페이지 오케스트레이터. admin/map_editor 선례대로 **자체 모듈 지역 상태**(`state.js`/`dom.js`/`api.js`/`websocket.js` 미임포트). 재사용: `config.js`(`API_BASE`/`CURRENT_USER`/`pageLimit`), `utils.js`(`showToast`), AG-Grid Community(`theme:'legacy'` + `ModuleRegistry` — grid.js/main.js 선례) |
| `client2/vite.config.js` | 1줄 추가 | `input.enrichment` 멀티페이지 엔트리 (기존 3개 엔트리 불변) |

**범위 제외 준수:** 참조뷰 실데이터 연동·그리드 배지(`index.html`/`dom.js`/`ui.js`) 미접촉 — 단계②③.

## 2. 구현 요지

### 컨베이어 (판단 → Enter → 다음)
- 워크리스트 행 선택 → [B]에 판단키(`decision_key`)·단서(`list_columns`)·target 입력 필드(규칙 메타 기반 동적) 렌더, 첫 입력 자동 포커스.
- `Enter` → 전 필드 검증(전부 채워야 저장, 판단 1회 = 요청 1회) → `PUT /tables/{derived}/data/updates` → 200 시 **낙관적 행 제거**(`applyTransaction({remove})`) + 잔여 −1 + 세션 카운트 +1 → **제거된 자리의 다음 행 자동 선택·포커스**. 실패 시 입력·행 유지 + 에러 토스트.
- `↑/↓` 항목 이동, `Esc` 입력 지우기. 저장 성공 시 입력 블록 green flash 마이크로 애니메이션.

### 결손 필터·청크 페칭 (확장성 체크리스트)
- [x] **전량 로드 금지**: `GET /tables/{derived}/data?skip=0&limit=1000(pageLimit)&order_by=row_id&order_desc=false&filters={"<target>":{"type":"blank"}}` — 서버 blank 필터(main.py 846-855, `NULL OR ''`) 재사용. Load-All 류 UI 없음.
- [x] **깊은 OFFSET 없음**: 컨베이어는 항상 앞에서 소비. 보충은 버퍼 <50행 시 **`skip=0` 재페치**(채워진 행은 blank 필터에서 자동 이탈) + `row_id` Set dedupe 후 신규만 `applyTransaction({add})`. 구조적으로 큰 skip 미발생.
- [x] **세션 가드 UUID**: 규칙 전환/새로고침마다 토큰 재발급, 모든 비동기 응답(워크리스트/전체카운트/저장 후 UI 반영)은 토큰 불일치 시 폐기.
- [x] **프리징 없음**: AG-Grid 가상 렌더([A]), [B]/[C]는 선택 1건 분량 DOM. 다중 target도 저장 1요청.
- 진행률 분모(전체 유니크 키)는 `limit=1` 요청의 `total`만 사용(서버 5초 카운트 캐시) — 실패 시 무음, 잔여 카운트만으로 동작 지속.
- 다중 `target_fields` 결손 판정은 계획서 §4-B대로 **컬럼별 blank 나열(AND)**.

### 계약 준수 확인
- **규칙 메타(확정 계약)**: `GET /enrichment/rules` → `{rules:[{name, source_table, derived_table, decision_key, target_fields, list_columns, reference_views:[{label}]}]}` 소비. `derived_table` 없는 항목은 필터링(방어). `reference_views[].label`은 [C] placeholder 탭으로만 표시(비활성, 단계② 안내).
- **무음 가드**: 규칙 API 404/비정상/네트워크 실패/규칙 0건 → 각각 다른 안내 카드(오버레이) + 다시 시도 버튼. 콘솔 스팸 없음. **서버 미배포 상태에서도 페이지가 우아하게 동작.**
- **저장 계약 불변**: `handleCellEdit` 동일 페이로드 `{updates:[{row_id, updates:{col:val}, source_name:'user', updated_by:CURRENT_USER}], silent:false}` — 서버가 CellSource(user, priority 0) 기록.
- **셀 계약 불변**: 수신 `{value, is_overwrite, priority_source}`를 읽기 전용 `cellVal()` 헬퍼로 표시만 하고 형태 변조 없음. 클라이언트가 셀 객체를 만들 일 없음(파생 테이블 재조회 시 서버 형태 그대로).
- **경계 계약 무접촉**: 기존 REST 경로/응답, WS 이벤트, `/schema` 형태 전부 불변. WS 미사용(map_editor 선례, v1 REST-only).

### 진입/기타
- `?rule={name}` 파라미터로 규칙 자동 선택(없으면 첫 규칙), 헤더 드롭다운으로 전환.
- 헤더: 진행률 바(채운 키/전체 키, width 트랜지션) + `잔여 N건` 배지(0건 시 ✅ green) + 세션 카운트 + 🏠 Main 링크.
- 워크리스트 소진 상태: 잔여 0 → 🎉 완료 오버레이 / 잔여>0인데 버퍼 0(타 사용자 유입 등) → 새로고침 안내 오버레이.

## 3. 검증 결과 (worktree 제약 내)

| 항목 | 결과 |
|---|---|
| JS 문법 | `node --check` 통과 (`enrichment.js`, `vite.config.js`) |
| HTML 구조·디자인 | 브라우저 정적 렌더 스크린샷 확인 — 3구역 글래스 패널, 헤더 진행률 클러스터, empty state 정상. 메인 페이지 톤(다크 글래스·cyan) 일치 |
| `npm run build` | **미실행** (worktree에 node_modules 없음 — 총괄 통합 시 본체에서 1회 수행 지시 준수) |
| 서버 연동 실동 | **미실행** (통합 단계에서 총괄 수행 — 아래 §4 목록) |

## 4. 통합 검증 필요 항목 (총괄 수행용)

1. `cd client2 && npm run build` — enrichment 엔트리 포함 4페이지 산출 + 기존 3페이지 회귀 없음, dist 커밋.
2. `/enrichment.html` FastAPI dist fallback 서빙 확인(`/map_editor.html` 선례).
3. 서버 `GET /enrichment/rules` 배포 후: 규칙 로드·드롭다운·`?rule=` 파라미터 동작.
4. **미배포 상태 가드**: 서버에 엔드포인트 없는 채로 페이지 진입 → 안내 카드 표시(무음) 확인.
5. 시드된 파생 테이블 대상: 값 입력→Enter→행 이탈→다음 항목 자동 포커스(컨베이어 루프), 메인 그리드에서 해당 셀 `priority_source='user'` 표시, 재인제션 후 사람값 보존(레이어링).
6. 1만 행 시드: 초기 로드 1000행만, 버퍼 <50 시 skip=0 보충·dedupe, 스크롤/저장 프리징 없음.
7. 다중 `target_fields` 규칙이 실제 존재할 경우: AND blank 판정이 운영 의도와 일치하는지(부분 채움 행이 리스트에서 빠짐) Server PM과 확인.
8. blank 필터는 native 컬럼 전제 — 파생 테이블 target 필드가 `table_config.json` native 컬럼으로 시드되는지(Server PM 전제 재확인).
9. `total`(5초 캐시)과 로컬 감산치의 일시 오차가 UX상 문제없는지(새로고침 시 서버값으로 수렴).

## 5. 사이드이펙트 체크 (StableDevelopmentProtocol §1)

| 변경 | 2차 효과 | 처리 |
|---|---|---|
| vite 엔트리 추가 | 빌드 산출 구조 | 순수 추가, 기존 3 엔트리 불변 — 통합 빌드에서 회귀 확인(§4-1) |
| 신규 페이지 | 메인 그리드 공유 상태/이벤트 | `state.js`/`dom.js`/`websocket.js` 미임포트 → 공유 가변 상태·WS 흐름 무영향 |
| `utils.js` 재사용 | `showToast`가 `window.showToast` 전역 노출 | 기존 동작 그대로(다른 페이지도 동일 임포트), 무해 |
| AG-Grid 모듈 등록 | 페이지별 중복 등록 | 각 엔트리 독립 번들 — main.js와 동일 패턴, 충돌 없음 |
| 기존 파일 | index/admin/map_editor/src 기존 모듈 | **미접촉** (vite.config 1줄 외 기존 파일 수정 없음) |

## 6. 작업 이력 초안 (총괄 통합 시 `docs/history/`에 반영용 — worktree에서 history/STATUS 미접촉 지시 준수)

> **제안 파일명**: `20260725_HHMMSS_client_enrichment_queue_phase1.md`
> **요약**: Enrichment Queue 클라이언트 단계① — `enrichment.html`/`src/enrichment.js` 신설(3구역: 워크리스트 AG-Grid + 컨베이어 입력 + 참조뷰 placeholder), vite 멀티페이지 엔트리 추가. 확정 계약 `GET /enrichment/rules` 소비(미배포 시 무음 안내), 워크리스트는 기존 `GET /tables/{derived}/data`+blank 필터 skip=0 청크 소비(세션 가드 UUID, row_id dedupe), 저장은 기존 `PUT /tables/{derived}/data/updates`(source=user) 재사용 후 낙관적 제거·자동 다음 항목. 경계 계약 전부 불변. 검증: node --check, 정적 렌더 확인; 빌드·실동은 통합 단계.
> **리빙 문서**: `docs/architecture/frontend.md`에 4번째 엔트리(enrichment) 추가 필요(통합 시).

## 7. 미해결 / 다음 단계

- 단계②: 참조뷰 실데이터(`GET /enrichment/rules/{rule}/references/{i}` — D 계약 확정 대기), 선택 변경 debounce+stale 가드.
- 단계③: 메인 그리드 결손 배지(`index.html`/`dom.js`/`ui.js`/`websocket.js` 훅), nav 링크, 빌드+dist, 문서/히스토리 마감.
- 리스크(계획서 §8 유지): 다중 사용자 동시 편집은 last-write-wins(v1 허용), 다중 target AND 판정 운영 확인(§4-7).
