# Client 보고서 — 디자인 방향 C(듀얼 토글) 구현

> **작성:** Client PM · 2026-07-25
> **브랜치:** `worktree-agent-a4c562e6bce05e458` (main 병합 금지 — 총괄 검수 대상)
> **명세 준수:** 토큰 이름·값은 `design_mockups/direction_C_dual_tokens.html`에서 그대로 채택 (Light=A, Dark=B "밝힌 다크"). 기본 테마 = **light**.

---

## 1. 단계별 완료 여부

| 단계 | 상태 | 커밋 |
|---|---|---|
| 1. 토큰 SSOT (`tokens.css`) + 토글 유틸 (`theme.js`) + 4엔트리 배선 + FOUC 방지 | ✅ 완료 | `765c7e5` |
| 2. 페이지 이관 (style.css·enrichment 인라인·admin 팔레트·main.js 모달·토스트 통합) | ✅ 완료 | `d8b6bca` |
| 3. AG-Grid 테마 전환 + 셀 tabular-nums/mono | ✅ 완료 (구조상 1·2단계 커밋에 포함) | `765c7e5`/`d8b6bca` |
| 4. 접근성 교정 (dim 대비·focus-visible·클릭 타깃) | ✅ 완료 | `30569c8` (+토큰 값으로 1단계에 선반영) |
| 5. map_editor 캔버스 토큰화 (~25곳 전량) | ✅ 완료 — 부분 구현 아님 | `b39fe73` |

## 2. 아키텍처 요약

- **`client2/src/tokens.css`** (신규, SSOT): 시맨틱 토큰 2세트(`:root[data-theme="light"|"dark"]`) + `:root` 단독 폴백(light). 목업 코어 토큰 21종 그대로 + 확장 토큰(accent-2/info/orange/overwrite/surface-hover/scrim/shadow-pop/flash/range-fill/`--canvas-*` 9종). **레거시 별칭 브리지**(`--color-primary`→`var(--accent)` 등) 포함 — 인라인 `style=""` 잔존 참조도 테마 추종. 공통 토스트·테마 토글 버튼·AG-Grid 듀얼 오버라이드·focus-visible 링도 이 파일에 일원화.
- **`client2/src/theme.js`** (신규): `getTheme/applyTheme/toggleTheme/initTheme`. `<html data-theme>` 스탬프 + `localStorage('theme')` 영속 + AG-Grid 클래스 스왑 + `themechange` CustomEvent 발행 + `storage` 이벤트로 탭 간 동기화.
- **배선**: main.js/enrichment.js/map_editor.js/admin.js 4엔트리 전부 `import './tokens.css'` + `initTheme()` 호출. admin.js는 이번에 최초로 모듈 임포트 도입(vite 엔트리이므로 안전).

## 3. FOUC 방지 방식

각 HTML `<head>` 최상단(모든 CSS·모듈 스크립트보다 앞)에 동기 인라인 스니펫:
```html
<script>(function(){try{var t=localStorage.getItem('theme');
document.documentElement.setAttribute('data-theme',t==='dark'?'dark':'light');}
catch(e){document.documentElement.setAttribute('data-theme','light');}})();</script>
```
+ `<html data-theme="light">` 정적 기본값 + tokens.css의 `:root` 폴백(light) 3중 안전망. JS 완전 실패 시에도 light로 렌더.

## 4. AG-Grid 전환 방식

- AG-Grid Community **35.3.0, `theme: 'legacy'`** (기존 그대로) — `ag-theme-quartz.css` 한 파일에 quartz/quartz-dark 클래스가 모두 포함되어 있음을 확인.
- `theme.js syncAgGridThemeClasses()`가 `data-theme`에 따라 컨테이너 div(`#myGrid`, `#worklist-grid`)의 클래스를 `ag-theme-quartz ↔ ag-theme-quartz-dark`로 스왑 — **grid 재생성 없이 재도색**.
- 색 변수는 tokens.css에서 `.ag-theme-quartz, .ag-theme-quartz-dark { --ag-*: var(--토큰) }` 공통 오버라이드 — 클래스가 무엇이든 값은 시맨틱 토큰이 결정. 데이터 배경이 `--bg-surface`(라이트=흰색)로 상향되어 감사 지적("데이터 영역이 가장 어둡다") 해소.
- **감사 Top4**: `.ag-cell { font-family: var(--font-mono); font-variant-numeric: tabular-nums }` (양 테마) + 행 스트라이프 `--row-stripe`, hover `--accent-weak` 가시화.

## 5. 토큰 커버리지 — 하드코딩 잔존 목록 (전수 감사 결과)

CSS/HTML: `style.css`의 `.side-indicator` FRONT(#38bdf8)/BACK(#f59e0b) 칩 **의도적 잔존** — 관찰면 상태 아이덴티티 색(캔버스 워터마크와 짝, 양 테마 판독 가능). 그 외 4페이지 CSS/HTML 하드코딩 0건.

JS 의도적 잔존(전부 테마 무관 도메인):
- `map_editor.js`: 기본 범례 색(GOOD/FAIL/EMPTY/REWORK 등, 사용자 데이터), 범례 미등록 값 폴백 `#10b981`, 채도 높은 범례 셀 위 흰 텍스트 `#ffffff`, Excel 클립보드 내보내기 스타일(외부 산출물), 콘솔 로그 색.
- `grid.js`: 콘솔 디버그 로그 색 1건.
- `theme colors 캐시의 fallback 리터럴`(tokens.css 미로드 시 안전값) — 정상 경로에서는 미사용.

## 6. map_editor 캔버스 성능 처리

- `rebuildThemeColorCache()`: `getComputedStyle(document.documentElement)` **1회 호출**로 `--canvas-*` 및 상태 토큰 17종을 평문 캐시 → 렌더 루프는 캐시 객체만 참조 (프레임당 스타일 리드 0회, 기존 성능 규율 유지).
- `themechange` 수신 시에만 재캐싱 + `scheduleRenderGridCanvas()` 1회 재렌더 (기존 rAF 스로틀 경유).

## 7. 접근성 (감사 Top5)

- `--text-dim`: light 5.6:1 / dark 4.7:1 (표면 기준) — AA 충족 (목업 값 자체가 교정본).
- 전역 `:focus-visible` 링(`2px var(--accent)`, 버튼/링크/셀렉트/체크박스) — enrichment 키보드 UX 모순 해소.
- 클릭 타깃: `.glass-page-btn`·`.page-input`·`.filter-tx-btn` min 24px, 체크박스 15→18px(글로벌)/14→16px(컬럼 셀렉터).

## 8. 검증

- `node --check`: 수정 JS 6종 전부 통과 (theme/main/enrichment/map_editor/admin/timeline).
- 정적 렌더 자기 검토: tokens.css+style.css를 인라인한 정적 하니스로 index·enrichment를 브라우저에서 **양 테마 토글 실확인** — 표면 위계·보더 가시성·배지/토글 아이콘 정상, 네온·글로우 부재 확인 (하니스는 검증 후 삭제, 미커밋).
- 잔존 색 전수 grep 감사(§5).

## 9. 통합 검증 필요 항목 (총괄 — 본체에서 `npm run build` 후 실브라우저 체크리스트)

1. **빌드**: `cd client2 && npm run build` 성공 + dist 커밋 (worktree 규칙상 미빌드 — dist는 stale 상태).
2. 4페이지 × 2테마 × 토글 왕복: FOUC 없음, 새로고침·페이지 간 이동 시 테마 유지(localStorage), 탭 2개 동시 열고 한쪽 토글 → 다른 탭 동기화.
3. **index 그리드**: 테이블 로드 후 라이트/다크 전환 시 그리드 재도색(quartz↔quartz-dark), 셀 상태색(cell-overwrite/dirty-tx/flash/범위선택) 양 테마 판독, 수만 행 스크롤 프리징 없음.
4. **enrichment**: 컨베이어 포커스 흐름(Enter/↑↓/Esc) 회귀 없음, 참조뷰 스트라이프·저장 플래시.
5. **map_editor**: 캔버스 라이트 렌더(원 밖 영역·격자선·원점·선택 박스·워터마크), 테마 전환 직후 1회 재렌더 확인, 드래그 페인팅 성능 체감 동일, Push/Load 회귀 없음.
6. **admin**: Monaco vs↔vs-dark 전환, 토스트(성공/실패), 7개 탭 테이블 가독성.
7. 데스크톱 셸(QtWebEngine)에서 localStorage 영속 동작.

## 10. 리스크·비고

- `--transition-smooth: all 0.3s` 광범위 적용(감사 #8)은 **범위 외로 미수정** — 테마 전환 시 다수 속성 트랜지션이 걸리나 body 색 전이(0.25s)와 함께 시각적으로 자연스러움. 후속 과제로 남김.
- admin.js에 모듈 임포트가 처음 추가됨 — dev(5173)·build 양쪽 vite 경로라 안전하나 빌드 검증 필수.
- 이모지 버튼 아이콘(감사 #9)·헤더 과밀(#6)·메인 그리드 빈 상태(#7)는 본 과업 범위 외.
- 경계 계약(REST/WS/셀 형태) 무변경 — 표현 계층만 수정.

## 11. 히스토리 초안 (총괄 통합 시 docs/history에 반영용)

```
# 듀얼 테마(방향 C) 구현 — 토큰 SSOT + 라이트 기본
- tokens.css 신설(시맨틱 토큰 2세트 + 레거시 별칭 + 토스트/AG-Grid/접근성 공통), theme.js(토글·localStorage·themechange)
- 4페이지 토큰 이관: 네온/글로우/블러 제거, admin Catppuccin·Fira Code 폐기, 토스트 3중 복제 해소
- AG-Grid quartz↔quartz-dark 동적 스왑 + 데이터 셀 mono/tabular-nums
- map_editor 캔버스 색 전량 토큰화(getComputedStyle 1회 캐싱, themechange 재캐싱)
- 접근성: text-dim AA, focus-visible 링, 클릭 타깃 24px
```
