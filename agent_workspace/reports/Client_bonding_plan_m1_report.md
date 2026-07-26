# 보고서: 본딩 실험계획 M1 — 클라이언트부 (map editor Info 패널, 조회 전용)

- 작성: client-pm (2026-07-26, v2 — rect 영역 선택 모드 삭제 반영)
- 지시서: `agent_workspace/tasks/Client_bonding_plan_m1_task.md` (+ 총괄 중간 지시 2건: ① 영역 지정 프리셋 규격 사용 → ② **rect 영역 선택 모드 전면 삭제**)
- 판정: **완료** — `npm run build` 성공, 라이브 검증 + 삭제 후 회귀 검증 전 항목 통과. 커밋/재기동 미수행(지시 준수).

## 0. [v2 추록] rect 영역 선택 모드 삭제 (사용자 지시)

M2에서 "값 페인팅" 방식이 정본으로 확정되어 **rect 영역 선택 모드를 전면 폐기**했다.
아래 본문 §2-C(영역 지정)와 §4의 영역 관련 검증 행은 v1 시점 기록으로, **현재 코드에는 존재하지 않는다.**

### 삭제 내역
- `map_editor.js`: 영역 선택 모드 엔진 전체 제거 — `regionMode` 상태, mousedown/mouseup `region`/`region-erase` 분기(원래 paint/erase로 원복), 캔버스 rect 오버레이(§6.5), 파일 말미 엔진 섹션(`snapshotEditorState`/`restoreEditorState`/`findRegionPreset`/`selectionBoxToChipRect`/`rectsIntersect`/`applyRegionSelectionBox`/`buildRegionBar`/`updateRegionBar`/`startRegionSelection`/`finishRegionSelection`/`escapeHtmlText`). `initBondingPlan()`은 인자 없이 호출.
- `bonding_plan.js`: `[영역▦]` 버튼·미니 썸네일(`drawThumb`)·`pickRegion`·region 재조회(`getCoreSummary`의 region 파라미터/캐시 키)·`(영역 기준)` 표기 제거. 행 모델에서 `core_region`/`base_region` 삭제.
- `bonding_plan.css`: `.bp-region-bar*`·`.bp-region-btn`·`.bp-thumb` 스타일 제거(`.bp-region-line` → 범용 `.bp-hint-line`으로 개명).
- **유지**: `applyPresetObject` 리팩터(무해한 정리, 총괄 지시), Info 패널의 나머지 전부(층 배정·수량 검증·이력·knob 비교·경고·초안), 서버 core-summary의 region 파라미터(서버측 유지 — 클라만 미사용화).
- **초안 하위호환**: 구 초안의 `core_region`/`base_region`은 로드 시 읽되 버림. 이후 편집 발생 시 재직렬화에서 자연 탈락(검증 완료).

### 삭제 후 회귀 검증 (라이브, DOM/JS 평가)
| 항목 | 결과 |
|---|---|
| `node --check` 2파일 + `npm run build` | PASS |
| `map_editor.js`에 region 참조 0건 (grep) | PASS |
| 패널 개폐·행 추가·초안 저장/복원 | PASS |
| region 포함 구 초안 로드 → 행 정상 복원 + region 무시, 편집 후 재직렬화에서 region 필드 탈락 | PASS |
| 영역 버튼·썸네일·영역 바 DOM 부재 | PASS |
| **실서버 core-summary 200 응답 확인** — 서버가 그 사이 신 엔드포인트를 서빙 중(auto-reload 추정). 실응답 렌더 정상: identity(객체→문자열 방어 파싱), sources 실역할(`process_history/defect/eds_fail/used_chips/total_chips`, missing=미연결 뱃지), 수량 라인, 잔여 0 < 소요 → 부족 경고 | PASS |
| knob 비교(실서버, 이력 없는 코어 → "공통 step 없음" 빈 상태) | PASS |
| 캔버스 페인팅 회귀: 드래그=페인트, 우클릭=지우기 원복 | PASS |
| 콘솔 에러 | 0건 |
| 테스트 초안 localStorage 정리 | 완료 |

(참고: 검증 중 미리보기 pane 비표시 상태에서 `setTimeout` 스로틀로 스크립트 1회 타임아웃 — 페이지 결함 아님, 동기 디스패치로 재검증 완료.)

## 1. 변경 파일 (client2/ 내부만)

| 파일 | 변경 |
|---|---|
| `client2/src/bonding_plan.js` | **신설** (~780줄) — 슬라이드 패널 전체(상태·초안·core-summary 소비·검증·knob 비교·자동완성) |
| `client2/src/bonding_plan.css` | **신설** — 패널·영역 선택 바 스타일 (tokens.css 시맨틱 토큰만, 듀얼 테마 자동 대응) |
| `client2/src/map_editor.js` | **(v2 최종)** `loadSelectedPreset` → `applyPresetObject` 추출 리팩터 + `initBondingPlan()` 배선만 잔존. v1의 영역 선택 모드 엔진·마우스 분기·rect 오버레이는 §0 지시로 전량 제거됨 |
| `client2/map_editor.html` | 툴바 진입 버튼 `#btn-bonding-plan`, 패널 마운트 `#bonding-plan-root` |
| `client2/dist/**` | 빌드 산출물. **주의:** P1 미커밋 변경(`src/admin.js`/`admin.html`)이 포함된 상태로 빌드되어 `dist/admin.html`·`dist/assets/admin-*.js`·`dist/index.html`·`main-*.js` 갱신이 diff에 함께 섞임 — 정상(지시서 명시 상황). `src/admin.js`·`admin.html` 소스는 건드리지 않음 |

server/·docs/ 미수정. API 계약 미변경(소비만).

## 2. 요구사항 대응

### A. Info 창 골격
- 툴바 `🧪 본딩 실험계획` 버튼 → 우측 고정 슬라이드 패널(500px, translateX 트랜지션, z-index 800). 헤더: 제목 + `초안 · HH:MM 보관됨` 뱃지 + `M1 조회 전용` 뱃지 + 닫기.
- Base 식별자 입력(그래프 자동완성 `label=Base`, 검색 미가용 시 수기 입력 폴백) + 총 층수 + 실험 메모(textarea).

### B. 층 범위 배정 목록
- 행 = `(layer_from–layer_to, core lot|slot, 층당 수량, ▦core 영역, ▦base 부착)` + 순서 이동(↑↓)/삭제/추가(다음 시작층 자동 제안). 코어 자동완성 `label=Wafer`(`/graph/nodes/search` 재사용, 200ms debounce + seq 가드).
- 행 선택 → `GET /api/bonding-plan/core-summary?lot=&slot=` 조회(캐시 + `detailSeq` stale 가드):
  - 수량 라인: `잔여 207 = 총 249 − defect 10 − EDS 8 − 기사용 24` / sources 역할별 뱃지(missing = 주황 `미연결`)
  - 소요 = 층당 수량 × 층 수. 잔여(영역 지정 시 영역 가용 우선) < 소요 → 행 경고(빨간 보더 + `⚠️ 수량 부족 (잔여 X < 소요 Y)` 사유 칩) + 상세의 부족 칩수 표기
  - 공정 이력 타임라인: step별 도트(FAIL = danger 색 + 글로우), eqp/recipe/time, step 클릭 → knob 칩 목록(`depth · 1.2um`) 확장
  - 서버 `warnings[]` 그대로 노출
- **knob 비교 뷰**: [비교 로드] → 배정 코어 전체의 summary 수집 → 공통 step × knob 표. 값 상이 행의 셀만 warning 하이라이트(조건 이탈). 공통 step 없음/요약 미확보 코어 제외 처리.
- 검증 섹션: 층 커버리지 스트립(1~총층: 배정=accent, 공백=danger-weak, 겹침=warning) + 텍스트(`공백 4층 (5, 6, 7, 8) · 겹침 1층 (4)`), 경고 3종 배지(수량 부족 / FAIL 이력 / 조건 이탈 — 미조회·미계산 상태 구분 표기).

### C. 영역 지정 — **[v2에서 전면 삭제됨, §0 참조]** (이하 v1 기록)
- `[▦]` 버튼 → 패널 접힘 → map_editor `startRegionSelection({kind:'core'|'base'})` 진입:
  1. **편집 상태 스냅샷**(gridData·loadedFCells·메타 입력·그리드/물리 규격·회전/면·legend·brush)
  2. `/api/map-presets` 재조회 → 용도별 프리셋 탐색(core: `/core/→/eds/→/defect/`, base: `/base/→/bond/` — key·name 순) → `applyPresetObject`로 규격 적용(빈 좌표계 렌더). **프리셋 미등록 시 graceful**: 현재 그리드 규격 유지 + 바에 `프리셋 미연결 · 기본 그리드` 표기 + 토스트
  3. 플로팅 바(라벨·프리셋명·영역 수·실행취소/모두 지우기/완료/취소). 드래그 = rect 추가, 우클릭 드래그 = 교차 rect 제거. 확정 rect는 캔버스에 점선 + `#n` 태그 오버레이. 진입 중 Push 버튼 비활성(오적재 차단)
  4. rect는 칩(visual x/y) 좌표 `{x1,y1,x2,y2}`로 변환(4모서리 `getVisualCoords` → min/max, 회전/면반전 불변식 준수), **프리셋 그리드 범위로 클램프**, 그리드 완전 밖 드래그 무시
  5. 완료/취소 → **스냅샷 원복**(더티 가드) → 패널 재개방 → 행에 `{"rects":[...]}` 저장
- 행 미니 요약: 버튼에 rect 수 + 54×36 미니 썸네일(rect 정규화 렌더). core 영역 저장 시 `region` 파라미터 재조회 → 상세에 `2 rects · 영역 내 가용 142칩`. base 부착 영역 동일 UX(BASE 프리셋, 수량 재조회는 core 전용). 전체 오버레이는 M2 스코프대로 미구현.

### D. 초안 보관
- `localStorage['bonding_plan_draft::<base>']`에 500ms 디바운스 자동 저장, `bonding_plan_last_base`로 재접속 복원. base 변경 시 이전 base 초안 확정 저장 → 새 base 초안 있으면 복원(토스트).
- 직렬화(M2 서버 승격 대비 평탄 구조): `{version:1, base, total_layers, memo, assignments:[{layer_from, layer_to, core_lot, core_slot, qty_per_layer, core_region, base_region}], saved_at}` — region은 API 계약과 동일한 `{"rects":[...]}` 그대로.
- 패널 부제에 "저장(관리 테이블)은 M2에서 지원" 안내 상시 노출.

## 3. 서버 graceful (구버전 대응)
- `core-summary` 404(`{"detail":"Not Found"}`) / 405 → `serverSupported=false` → 상세·비교 영역에 "서버가 API를 아직 제공하지 않습니다(구버전)" 빈 상태 + [다시 시도]. 행 상태 `서버 미지원`. **초안 편집·영역 지정·커버리지 검증은 계속 동작.**
- 404에 detail이 있는 경우(신 서버의 코어 미존재 등)는 오류로 구분 표시. 네트워크 실패 → `조회 실패` + 재시도.
- 자동완성은 그래프 API 실패 시 조용히 드롭다운만 숨김(수기 입력 유지).

## 4. 라이브 검증 (실서버 :8080, 재기동 없이 — DOM/JS 평가 방식)

현재 서버 = core-summary **구버전(404)** / map-presets에는 `core_std`·`base_std` **이미 등록됨** 확인.

| 항목 | 결과 |
|---|---|
| 패널 마운트·개폐, 4개 섹션 렌더 | PASS |
| 구버전 서버 graceful (미지원 안내 + 행 `서버 미지원` + 편집 지속) | PASS (실서버 404로 실검증) |
| 초안 자동 저장·뱃지·**페이지 리로드 후 복원**(base/층수/행 2건/영역 2 rects) | PASS |
| 층 커버리지(공백 4층 → 행 추가 후 공백 없음·겹침 1층(4)) | PASS |
| 영역 선택: CORE 프리셋 자동 적용(10×10, chip 2.5 → **45×45, chip 7**) | PASS (실서버 `core_std`) |
| BASE 프리셋 적용(29×25) + 취소 시 원복 | PASS (실서버 `base_std`) |
| 드래그 rect 추가 2건 → 우클릭 드래그 제거 → 재추가 → 완료 저장(칩 좌표, 클램프) | PASS |
| 완료/취소 후 편집 상태 원복(그리드/물리 규격), Push 비활성↔복원, 바 제거, 패널 재개방 | PASS |
| **모의 응답 스텁**(계약 형태 그대로 fetch 인터셉트): 수량 라인·미연결 뱃지·영역 재조회(`2 rects · 가용 142칩`)·소요/부족 경고(`잔여 142(영역) < 소요 240 — 98칩 부족`)·FAIL 타임라인·knob 확장·서버 warnings | PASS |
| knob 비교: 공통 step 2개, `ETCH·depth` 1.2um vs 1.5um만 하이라이트, 조건 이탈 배지 1 | PASS |
| 콘솔 에러 | 없음 |
| 검증 후 테스트 초안 localStorage 정리 | 완료 |

(미리보기 pane 비-compositing 교훈 준수 — 스크린샷 대신 DOM/JS 평가로 검증.)

## 5. 재기동 후 확인 항목 (신 서버 배포 시) — v2 갱신
1. ~~실데이터 core-summary 200 렌더~~ → **v2 회귀 검증 중 실서버가 이미 신 엔드포인트를 서빙하여 실응답 렌더까지 확인 완료**(§0 표 참조). 실데이터 보유 코어(수량·이력 포함)로 1회 추가 확인만 권장.
2. 404이면서 detail이 있는 응답(코어 미존재 등)의 문구가 사용자에게 적절한지.
3. ~~region 좌표계 정합 / region_chips 수치 / 프리셋 findRegionPreset~~ → **rect 모드 폐기로 해당 없음** (region 파라미터는 M2 값 페인팅에서 재검증).

## 6. 알려진 한계 (M1 스코프 의도) — v2 갱신
- 영역 지정 기능 자체가 M1에서 제외됨(rect 모드 폐기 — M2 "값 페인팅" 방식으로 재설계 예정).
- knob 비교는 코어당 동일 step 다회 이력 시 마지막 이력의 knobs 사용.

## 7. 교훈 제안 (총괄 검수 후 반영)
- **함정**: Bash 툴(Git Bash)에서 한글 포함 대형 heredoc append가 따옴표 파싱 오류를 낼 수 있다. **올바른 방법**: Write로 스크래치 파일 생성 후 `cat file >> target`으로 append.

## 8. 히스토리 초안 (통합 시 총괄 기록용 — v2 갱신)
> feat(client): 본딩 실험계획 M1 — map editor 우측 슬라이드 Info 패널(조회 전용). 층 범위 배정(+core-summary 소비: 수량 라인/소스 미연결/FAIL 타임라인/knob 확장), knob 비교(공통 step 조건 이탈 하이라이트), 층 커버리지·경고 3종 검증, localStorage 초안 자동 보관/복원(base 키). 구버전 서버 graceful(404→미지원 안내). rect 영역 선택 모드는 개발 중 사용자 지시로 폐기(M2 "값 페인팅" 방식 예정 — 서버 region 파라미터는 유지, 클라 미사용). `loadSelectedPreset`→`applyPresetObject` 추출 정리. 신규: bonding_plan.js/.css.
