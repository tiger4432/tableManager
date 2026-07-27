# 첫 클릭이 죽던 이유 — mousedown이 **클릭 대상 자체를 파괴**하고 있었다

> 커밋 `280ebf0` · 2026-07-28 07:49 · 도메인 Client(맵 에디터·계획 패널, map-pm 라운드)
> 상위: [SYSTEM_OVERVIEW](../overview/SYSTEM_OVERVIEW.md) · 계약: [MAP_EDITOR_SPEC](../spec/MAP_EDITOR_SPEC.md)
> 선행: [DOE zone 클라 절반](./20260728_072317_doe_zone_client_half_config_backup_and_two_traps.md) (`b35bc9f` — 아래 ③의 원인 커밋)

## 배경

`b35bc9f` 착지 직후 사용자 사용감 피드백으로 모인 5건을 한 라운드로 처리했다. 각 건은
수정 후 **결함 재주입**(고친 줄을 되돌려 증상이 재현되는지)으로 검증했다.

## 변경 내용

### ① DOE 입력 랙 — 렌더가 아니라 **파괴**가 문제였다

"클릭 반응이 굼뜨다"의 실체: DOE 값 행 안에서 mousedown → `setBrush` →
`notifyLegendChanged` → `renderDoeList`가 `innerHTML`로 목록 전체를 재구성 →
**브라우저가 기본 포커스를 주기 전에, 방금 클릭한 그 input이 DOM에서 떨어져 나갔다.**
첫 클릭은 그래서 항상 죽었다. 랙처럼 보였지만 지연이 아니라 유실이었다.

```js
// map_editor.js — 이 커밋 시점의 수정
-  setBrush: (v) => { selectBrush(String(v)); updateLegendCounts(); },
+  // Selection alone changes no counts - updateLegendCounts here scanned every grid
+  // cell (O(cells)) on each mousedown in the panel and added visible click latency.
+  setBrush: (v) => { selectBrush(String(v)); },
```

원리는 하나다 — **선택은 데이터를 바꾸지 않는다.** 그러므로 선택이 legend notify(목록 재구성)도,
전 셀 카운트 스캔(O(cells))도 유발할 이유가 없다. 카운트는 실제로 값이 바뀌는 paint 경로에서
갱신한다. 부차 원인으로 `.glass-input`의 `transition: all 0.3s`가 매 포커스에 0.3초 시각 지연을
얹고 있어 `border-color/box-shadow 0.1s`로 좁혔다(토큰 자체는 손대지 않았다).

### ② 존재하지 않는 dt-map 키도 **LOAD와 같은 문으로** 들어간다

계획 패널에서 자재를 클릭했을 때, id가 (lot, slot)으로 쪼개지지 않으면 에러 토스트로 끝났다.
그런데 "1. Map Search & Load"에서 같은 문자열을 첫 키 컬럼에 직접 치면 **빈 그리드가 열리고
⚡ Push에서 키가 생성**된다. 같은 의도가 입구에 따라 다르게 끝나는 것이 결함이었다.

```js
// transfer_plan.js — 쪼개지지 않는 id는 첫 키 컬럼의 필터가 된다
const cols = S.keyColumns.get(table) || [];
metaValues = { [cols[0]]: String(id) };
```

경계는 유지했다: `probeMaterialMap`은 이런 id에 대해 여전히 `null`(미상)을 반환한다.
사용자가 요청한 **이동**을 위해 추측하는 것과, **존재 주장**을 위해 추측하는 것은 다른 일이다.

### ③ 오버레이 블록 CSS 실종 — `b35bc9f`의 전면 재작성이 떨어뜨린 것

직전 커밋이 `transfer_plan.css`를 재작성하면서 `.overlay-box` / `.ov-*` 규칙 세트 전체가
빠졌다 — `map_editor.html`과 `renderOverlayList()`는 그 클래스를 계속 쓰고 있었으므로
오버레이 블록이 무스타일로 렌더됐다. 규칙을 **원문 그대로** 복원했다. 재작성 당시 이 CSS
파일의 소비자가 계획 패널만이 아니라는 사실이 함께 확인되지 않았던 것이 원인이다.

### ④ DOE 활자 한 단계 확대

입력 `.68rem → .82rem`, 행 높이 동반 확대. 표시 계층만의 변경이고, 엑셀 붙여넣기 계약은
인덱스 기반이라 활자·레이아웃과 무관하다.

### ⑤ 새로고침이 마지막 맵으로 돌아온다

사용자 관측 그대로 — "새로 고침하면 그냥 아예 처음창으로 가는데". 초안 시스템은 **그린 내용**을
지키지만 **어느 맵을 보고 있었는지**는 아무도 지키지 않았다. `map_editor_last_open` 레코드를
Load/Push **성공 시점**에만 쓰고(자재 프레임은 제외 — 프레임은 여정이지 집이 아니므로 depth-0
정체성만 기록), 부팅에서 한 번 읽는다.

복원은 별도 경로를 만들지 않고 **수동 LOAD 경로를 그대로 걷는다** — 테이블 선택 → `switchTable`
→ 메타 입력 → `loadExistingMap({quiet})`. 그래서 초안 우선순위 판정도, 없는 키의 동작(빈 그리드,
Push에서 생성)도 복원 전용 사본 없이 기존 코드 하나로 유지됐다. 기록된 테이블이 사라졌으면
조용히 초기 화면으로 남는다 — 부팅은 에러 다이얼로그를 띄우지 않는다.

## 검증

| 무엇을 | 어떻게 | 결과 |
|---|---|---|
| 5건 각각 | 결함 재주입(수정 되돌림 → 증상 재현 확인 → 재적용) | 전부 재현·해소 확인 |
| 클라 하네스 3종 | `node contracts/<name>/client_harness.mjs` | 82 / 71 / 304 assertions, 전부 OK |
| 구문 | `node --check` | clean |
| 번들 | vite 재빌드 | dist 갱신 |

## 그때 남아 있던 것

- 자재 프레임 안에서 새로고침하면 **루트 맵**으로 돌아온다 — 프레임 스택은 기록 대상이 아니었다
  (설계 선택: 레코드는 depth-0 정체성만 담는다).
- ③의 복원은 클래스 소실 하나를 되살린 것이고, `b35bc9f`의 CSS 재작성 전체를 diff 대조로
  전수 감사한 것은 아니었다 — 이 라운드에서 무스타일로 드러난 것이 오버레이 블록뿐이었다.
- `.glass-input` 전역 토큰의 `transition`은 그대로였다 — 좁힌 것은 이 화면의 규칙 스코프다.
