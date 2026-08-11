# The menus opened every time, and an ancestor clip cut all of them away

**Date:** 2026-08-11 19:54 · **Domain:** Client (맵 에디터 툴바 / 테마) · **Status:** 착지 — `738b6c1`

> ⚠️ 관측은 전부 **격리 환경 `:8081`** 에서 나왔다. 운영이 아니다.

---

## 배경 — 신고는 「위 버튼이 안 눌린다」였다

제품 소유자가 맵 에디터의 상단 버튼이 동작하지 않는다고 신고했다. 격리 환경에서 확인한
결과 **레거시 에디터**(`map_editor.html`)의 문제였고, 넷 중 둘만 죽어 있었다.

| 버튼 | 수리 전 관측 |
|---|---|
| 🔍 Select Tools | **아무것도 안 나타남.** 메뉴는 DOM에서 열린다(`display:flex`, rect `605,174,180,171`) |
| 🛠️ Edit Grid | **아무것도 안 나타남.** 같은 모양 |
| ⚡ Push Map Data | 동작함 — 가드 경고 발화, fetch 0건 |
| 📐 규격만 저장 | 동작함 — 토스트 발화, fetch 0건 |

즉 운영자가 보는 것은 **둘은 반응하고 둘은 돌덩이인 툴바**다. 신고 그대로다.

## 앞선 가설을 먼저 기각했다

지시서의 유력 용의자는 `42d7600`(map2 확정 훅)이었다. **소스를 열기 전에 콘솔을 먼저
읽었고**, 두 페이지 어디에도 잡히지 않은 예외가 없었다 — 레거시는 페인트 규칙 안내와
`transfer_plan_config` 폴백 경고 두 줄, 에디터 2는 의도된 부재 보고 여섯 줄뿐이다.

**「예외 하나가 뒤의 핸들러를 전부 죽인다」 이론이 여기서 닫혔고**, 그와 함께 용의자도
닫혔다. 핸들러 등록은 죽지 않았고 아무것도 언바인드되지 않았다.

## 근본 원인 — 메뉴는 매번 열렸다

```
#select-menu-dropdown            position:absolute  z-index:1000   ← y=174 에서 열린다
  .control-group.relative-menu     position:relative              ← 이것의 컨테이닝 블록
    .map-editor-toolbar__actions   overflow-x:auto; overflow-y:hidden
      .map-editor-toolbar          overflow:hidden; height:112px
```

액션 행의 클립 박스는 `53,126,1019,40` — **y=166에서 끝난다.** 메뉴는 **y=174에서
시작한다.** 100%가 밖이다.

그리고 잘린 것이 그림만이 아니다. 메뉴 중심에서 `document.elementsFromPoint()`가
`CANVAS#wafer-grid-canvas`부터 돌려준다 — **메뉴는 히트테스트 스택에 아예 없다.** 동시에
**안 보이고 안 눌린다.** 사용자에게 그것은 「메뉴가 열려 있다」로 읽히지 않고 **「버튼이
고장났다」**로 읽힌다.

`z-index:1000`은 아무것도 사 주지 않는다. 절대 위치 요소는 컨테이닝 블록 사슬에서
`overflow`가 `visible`이 아닌 **모든** 조상에게 잘리고, 여기엔 그런 조상이 **둘**이었다.

## 어디서 왔나 — 오늘 일이 아니다

`git log -L 1496,1570:client2/src/style.css`가 **정확히 한 커밋**을 돌려주고, 그 diff는
블록 **전체를 추가한다** — `a501d6d`(2026-08-09). 그 커밋의 의도는 자기 주석에 있다:
*상태 문자열은 커서가 움직일 때마다 바뀌지만 그것이 액션 행의 높이를 바꾸거나 아래
캔버스를 밀어서는 안 된다.* 그 목적을 달성하는 것은 `height:112px`이고, `overflow`는
**덤이었는데 메뉴를 같이 가져갔다.**

**자기가 선언한 목표는 달성한 변경이 이틀 동안 컨트롤 둘을 죽여 놓았다.**

## 무엇을 했나

```css
/* 🔴 THE FIXED `height` BELOW IS WHAT HOLDS THE CANVAS STILL — a clip is not, and
      this box must not establish one. ... Measured: menu at y=174 against a clip box
      ending at y=166, so 100% of it was cut and `elementFromPoint` at its centre
      returned the canvas. */
.map-editor-toolbar { ...; overflow: visible; }        /* was: hidden */

/* 🔴 AND `overflow-x: auto` CANNOT BE KEPT HERE EITHER ... CSS computes an
      `overflow-y: visible` paired with a non-visible x axis up to `auto`, so a
      scrollable x axis silently re-clips y and the menus vanish again. */
.map-editor-toolbar__actions { ...; overflow: visible; }  /* was: overflow-x:auto; overflow-y:hidden */
```

**`overflow-x: auto`를 남길 수 없었던 것이 이 수리의 핵심 제약이다.** x축이 `visible`이
아니면 CSS가 `overflow-y: visible`을 `auto`로 승격시켜 **조용히 다시 자른다.** 그래서
행 단위 가로 스크롤은 포기했다 — `main.main-layout`이 이미 페이지 스크롤러이므로 좁은
창에서도 버튼에 닿는다(900px에서 `scrollWidth 1371 > clientWidth 900` 확인).

캔버스를 붙들고 있는 `height:112px`은 **건드리지 않았다.** 앵커된 팝업이 없는
`.map-editor-toolbar__status`도 자기 클립을 그대로 유지한다.

## 곁에서 찾은 두 번째 결함 — 계열이 같다

에디터 2의 테마 토글이 **완전히 죽어 있었다.** `initTheme()`은 `main.js`·`admin.js`·
`graph_viewer.js`·`trace.js`·`enrichment.js`와 레거시 `map_editor.js`가 부르는데,
**`map_editor2.js`만 한 번도 부르지 않았다.**

숨은 이유가 이 건의 요점이다 — `map_editor2.html`이 로드 시점에 저장된 테마를 찍는 FOUC
스니펫을 갖고 있어서 **페이지는 테마를 아는 것처럼 보였고**, 그래서 죽은 버튼이 배선
누락이 아니라 렌더링 특이사항으로 읽혔다.

```js
function start() {
  // 🔴 THE TOGGLE IS MARKUP UNTIL SOMETHING BINDS IT. ... a control that looks live,
  //    reads as broken, and cannot be told apart from a dead page by any test that only
  //    checks what the page renders. ... Bound before the composition root so the button
  //    works even if bootstrap below fails.
  initTheme();
```

**형제 호출 지점 전부에 있고 한 곳에만 없는 가드** — 그날 같은 모양의 셋째 사례였다.

## 검증 — 실패할 수 있는 프로브였다

| | Select 메뉴 | 작업 메뉴 |
|---|---|---|
| 수리 후 | **4/4 도달** | **4/4** |
| **음성 대조(옛 CSS를 살려 둔 채)** | **0/4** | **0/4** |

**실패할 수 없는 프로브는 아무것도 증명하지 않는다.** 그래서 음성 대조를 같이 실었다.
끝단에서 실제 마우스 클릭이 `{x:695, y:201, target:"btn-set-origin"}`으로 기록됐고
리스너가 한 번 돌았으며 캔버스가 원점 모드로 들어갔다. 테마는 light → dark → light로
돌리고 환경을 복원했다. 레이아웃 무회귀 — 툴바는 여전히 112px, 캔버스 상단 불변,
900px에서도 두 메뉴 4/4.

**DB 쓰기 없음**: fetch 심이 GET 아닌 요청을 전부 막았고, 쓰기 버튼 둘은 요청을 0건
냈다 — 각자의 가드에서 거절했다.

**빌드 exit 0.** 세 개의 `prebuild` 게이트를 「전부 초록」으로 접지 않고 따로 보고했다 —
`check:clipboard` 0, `check:contracts` 0(계약 7건, 발산 없음), `check:harnesses` 0.

## 아키텍처 영향

소스 두 파일을 고쳤는데 **`dist` 표면은 그보다 훨씬 넓다.** vite가 main·admin·graph·
trace·config·effort_meter와 map_editor까지 재해시했고 dist HTML 여섯 개가 전부 바뀌었다.
공유 스타일시트 한 줄을 고치면 번들 경계가 통째로 움직인다는 뜻이다. **커밋 경로는
보고서가 아니라 `git status`에서 떴다** — 이 프로젝트가 반복해서 다시 배우는 규율이고,
레인이 스스로 그렇게 적었다.

## 남길 만한 방법 노트

`computer{coordinate}`는 **스크린샷 좌표계**를 받고(CSS px로는 ×1.806) ref 클릭은
**CSS px**로 보고한다. 초기 클릭 둘이 CSS 좌표 `(1255,361)`로 들어가 빗나갔는데,
그 모양은 **눌리지 않는 컨트롤과 구별되지 않는다.** 같은 혼동은 **멀쩡한 컨트롤을
고장난 것으로 읽게** 만들 수도 있다.

## 그때 남아 있던 것

- 이 결함은 `MAP_EDITOR_SPEC §7`에도 `EDITOR_USABILITY_FINDINGS.md`에도 **기록되지
  않은 채 남았다.** 두 문서 어디를 읽어도 이 툴바의 드롭다운이 이틀간 열리지 않았다는
  사실은 나오지 않는다.
- 레거시 에디터와 에디터 2가 **여전히 둘 다 살아 있다.** 이 커밋은 양쪽을 각각 고쳤을
  뿐 한쪽을 정리하지 않았다.
- `a501d6d`이 도입한 `height:112px`은 그대로다 — 캔버스를 붙들고 있는 것이 그것이고,
  잘라 낸 것은 `overflow`뿐이다.
