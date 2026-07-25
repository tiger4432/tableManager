# UI 작업 보고 — 다크 모드 컬러셋 진하게 (dark deepen)

> 담당: ui-designer · 2026-07-25 · 본체 main 트리 · **커밋/빌드 미수행(총괄 몫)**
> 사용자 피드백: "다크 모드 컬러셋 좀 진하게 해줘"

## 1. 변경 요약

`client2/src/tokens.css`의 `[data-theme="dark"]` 값 세트만 한 단계 진하게 교체. **라이트 세트·시맨틱 토큰 이름·셀렉터 구조는 무변경** (diff 헌크 전부 5행 헤더 주석 + 69~115행 다크 블록 내부 — `git diff -U0`로 확인).

설계 원칙:
- 지면 L* **13.7 → 9.2** — 구 near-black(#07090e, L* 2.5)과 현행의 중간대. 회귀 아님.
- 표면 위계 ΔL*(app→surface) **4.8 → 5.4로 강화** — "검은 화면 한 장으로 뭉개짐"(Design_audit §1.4의 원죄) 재발 방지.
- 액센트/상태색 채도 상향(탈네온 기조 유지) — 어두워진 지면 위에서 대비가 또렷해지도록.

## 2. 주요 값 (before → after, L*·대비는 스크립트 계산치)

| 토큰 | before | after | 비고 |
|---|---|---|---|
| --bg-app | #1c2331 (L* 13.7) | **#121a29 (L* 9.2)** | 지면 |
| --bg-inset | #1e2634 | #141c2c (L* 10.3) | |
| --bg-header | #212a3b | #182134 (L* 12.8) | |
| --bg-surface | #242d3f (L* 18.4) | **#1b2537 (L* 14.6)** | ΔL* app→surface 5.4 |
| --border / -strong | #3b4763 / #4d5b7c | #36425f / #4a5980 | 표면 대비 1.54 / 2.22:1 (현행 1.49 / 2.04 대비 강화) |
| --text-dim | #8b98ac | #8b99ae | **표면 대비 4.72 → 5.32:1** (AA 여유 증가) |
| --accent | #6cc4ee | **#54c2f5** | 채도 ↑, 표면 대비 7.62:1 |
| --accent-contrast | #10202c | #0c1926 | accent 위 8.80:1 |
| --success / warning / danger / info / orange / overwrite | 45d195 / f5c04a / f58a8a / 6fd4e6 / f0975c / f5b45e | 33d68f / f6bd35 / f87e7e / 4ed3ec / f68e48 / f6ac43 | 전부 표면 대비 6.06~8.96:1 (AA) |
| *-weak 틴트 | alpha 0.12 | alpha 0.14 (overwrite 0.16) | 어두워진 지면에서 칩 존재감 보정 |
| --shadow-card / pop | 0.25 / 0.5 | 0.35 / 0.6 | 진한 지면에 맞춘 그림자 보정 |
| --row-stripe / canvas-line(-strong) | 0.025 / 0.05·0.08 | 0.03 / 0.06·0.09 | 스트라이프·캔버스 그리드선 가시성 유지 |
| canvas-wm-front/back, focus-ring, flash, range-fill | 구 sky/amber rgb | 새 accent/overwrite rgb로 통일 | |

### WCAG 검증 (스크립트: scratchpad/contrast.js, WCAG 2.1 상대휘도식)
- 본문 3단: text 13.09:1 · muted 7.40:1 · **dim 5.32:1** (모두 vs bg-surface, AA 4.5:1 통과. dim vs bg-app도 6.03:1)
- 상태색 6종 + accent·accent-2: 표면 대비 전부 ≥ 6.06:1
- 위계: app 9.2 → inset 10.3 → header 12.8 → surface 14.6 (단조 증가, 순서 현행과 동일)

## 3. 시각 검증

정적 하니스(scratchpad/harness/, 임시 node 서버 → 종료 완료)로 3면 동시 렌더 스크린샷 확인:
- **BEFORE(구 다크) vs AFTER(신 다크)**: 지면이 확연히 진해졌으나 카드·헤더·인셋·토스트 경계 모두 식별 가능(near-black식 뭉개짐 없음). 선택 행·상태 칩·모노 숫자 가독 양호.
- **LIGHT**: 무변경 렌더 확인 (diff상으로도 라이트 블록 미접촉).
- 미리보기 pane 비-compositing 제약(교훈 파일 이슈 #3)에 따라 정적 렌더까지만 확인 — 애니메이션 값은 이번 변경에 없음.

## 4. 사이드 이펙트 전수 점검 (SOP §0-4)

- **AG-Grid**: tokens.css 공통 오버라이드(`--ag-*` → 시맨틱 토큰)만 경유하므로 자동 추종. 셀 계약·컬럼 구조 무관.
- **Monaco vs-dark**: 에디터 배경 #1e1e1e(L* 11.3). 구 세트에선 페이지 표면(18.4)보다 에디터가 더 어두워 "구멍"처럼 보였는데, 신 세트(표면 14.6, 헤더 12.8)에선 편차가 줄어 정합이 오히려 개선.
- **맵 에디터 캔버스**: `map_editor.js`는 `--canvas-*`를 getComputedStyle로 1회 캐싱, themechange 시 재빌드 — **값만 바뀌고 토큰명 불변**이므로 캐시 경로 무영향.
- **레거시 별칭**(`--border-color` 등): var() 브리지라 자동 추종.
- **FOUC 폴백**: `:root` 단독 셀렉터(라이트) 미접촉 — 미스탬프 폴백 동작 동일.
- **로직/계약 변경: 없음** — Client PM 이관 항목 없음.
- 주의: 현재 working tree의 `docs/*` 변경분(README·SYSTEM_OVERVIEW 등)은 **본 작업과 무관한 병렬 세션 소산** — 커밋 시 tokens.css만 스테이징할 것.

## 5. 미검증 / 다음 단계

- 실브라우저(:8080 실서비스 화면)에서 AG-Grid 수만 행 + Monaco 실화면 최종 확인은 총괄 빌드 후 권장.
- 사용자가 "더/덜 진하게"를 원하면 bg 4종만 재조정하면 됨(스크립트 재사용 가능).

## 6. 교훈 제안 (총괄 검수 후 memory/ui-designer.md 반영 요청)

- **함정**: 미리보기 pane은 `file://` 네비게이션이 차단된다.
  **올바른 방법**: 정적 하니스는 scratchpad에서 node 원라이너 서버(임시 포트)로 서빙 후 localhost로 열고, 검증 끝나면 포트 프로세스를 종료한다.
