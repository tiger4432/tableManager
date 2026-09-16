# 꺼진 컨트롤이 «자기 자리»에서 왜인지 말한다 — 그 좌석은 «지어진 것이 아니라 옮겨졌다»

> **커밋:** `dbdd3443` (23:18) — 디자인(클라) 레인 · C-120 + C-119 발견 ②
> **일자:** 2026-09-16
> **레인 보고:** `task/DESIGN_ORDERS.md` (`c7c41ac9`, 23:20)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경

소급 배너의 버튼 둘이 `title` 이 빈 채로 꺼져 있었다 — **같은 바에서 «옆에 선» 버튼 셋은
자기 사유를 달고 있는데.** 총괄이 C-119(화면 다섯 런타임 감사)의 발견 ②와 묶으라고 판정했다:
같은 병.

화면 다섯을 쓸어 보니 **「왜 못 누르나」에 답하는 방식이 넷**이었다 —
`title` · 컨트롤 옆 문구 · «다른 패널» · «아무것도 없음».
「깔끔 ④」 그대로다: 정본이 없으면 다섯째 컨트롤이 또 자기 방식을 고르고,
**「없음」이 제일 고르기 쉽다 — 아무것도 안 적으면 되니까.** 그리고 그 「없음」은 오류를 안 낸다.

## 무엇을 바꿨나

### ① 좌석은 «옮겨졌다». 새로 짓지 않았다

`write_guard.applyWriteGuards`(C-107)가 **이미** 정확히 이 일을 하고 있었다 — 끄고, 사유를 `title` 에
쓰고, 마크업 자기 말은 `data-title-was` 에 기억해 다시 켜질 때 잃지 않게.
그 루프 «몸통»이 `disabled_reason.setDisabledReason` 이 되고 `write_guard` 가 그것을 부른다.

```js
export function setDisabledReason(el, why) {
  if (!el) return;
  const reason = why || '';
  el.disabled = Boolean(reason);
  if (el.dataset && el.dataset.titleWas === undefined) {
    el.dataset.titleWas = (el.getAttribute && el.getAttribute('title')) || '';
  }
  const back = el.dataset ? el.dataset.titleWas : '';
  if (reason) { if (el.setAttribute) el.setAttribute('title', reason); }
  else if (back) { if (el.setAttribute) el.setAttribute('title', back); }
  else if (el.removeAttribute) { el.removeAttribute('title'); }
}
```
🔴 **그 자리에서 «확장»할 수는 없었다.** `write_guard` 가 답하는 물음은 「이 표에 쓸 수 있나」이고,
「행을 골랐나」는 **다른 물음**이다. 한 함수가 두 물음에 답하기 시작하는 것이 다음 라운드의 결함이다.

🔴 **끄는 것과 사유가 «한 줄»로 묶인 것이 요점이다.** 둘을 따로 두면 「끄기만 하고 사유는 안 적기」가
언제나 가능하고, 그것이 이 라운드가 고치는 결함의 모양이다.

### ② 네 컨트롤이 그 좌석을 지난다

```
소급 배너의 둘   「행을 고르십시오」  — 조건은 «줄곧 옳았다»(소급 목록이 `row_scoped`). 말을 안 했을 뿐
R&D 보드 「걷기」  사유가 «옆 패널»의 「마킹 1 · 0 marked」에 있었다
걷기 페이지 「날리기」 사유가 «옆 드롭다운»의 「— 고르십시오 —」였다
```

### ③ 🔴 «일부러 안 건드린» 것도 판정이다

`map_editor2` 는 사유를 각 컨트롤 «옆에 보이게» 이미 적고 있다. 그것을 툴팁으로 옮기면
**보이는 문장을 숨은 문장과 바꾸는 것**이라 더 나쁘다 — `write_guard` 자신의 배지가 그 이유로 존재한다.
탐색기의 `←` `→` 는 판정을 기다리게 뒀다(총괄 표가 「자명할 수 있다」로 적었고, 그건 발견이 아니다).

### ④ 새 문구를 «짓지 않았다» — 한 사실은 한 상수다

걷기 버튼에 「노드 타입을 고르십시오」를 새로 쓰려다 **되돌렸다.** 같은 화면의 전선이 같은 사실에
대고 이미 그 말을 하고 있었다(`fetchKeyValues` 의 거절문). 그래서 그 문장이 상수로 승격돼 둘이 같이 쓴다.

```js
export const PICK_TYPE_FIRST = '노드 타입을 먼저 고르십시오';
…
-  if (!type) return { ok: false, message: '노드 타입을 먼저 고르십시오' };
+  if (!type) return { ok: false, message: PICK_TYPE_FIRST };
```
```js
const RUNNING = '걷는 중';        // 라벨«이자» 꺼진 사유. 한 상수라 둘이 갈라질 수 없다
setDisabledReason(go, state.run === 'running'
  ? RUNNING
  : (state.type ? '' : PICK_TYPE_FIRST));
```

## 🔴 하니스 발견 셋 — 전부 같은 부류다

**「스텁이 못 보는 철자는 아무도 채점하지 않은 주장이다」**

```
board_dom 에 `removeAttribute` 가 없었다
   -> 「컨트롤이 돌아오면 사유가 사라진다」가 그 문서에서 «참일 수가 없었다» (두 라운드 안 넷째)
redo_banner_harness 의 스텁이 `setAttribute` 를 `dataset` 에 썼다
   -> 거기서 title 은 «측정 불가»였다
그 하니스는 `^import` 를 벗겨 vm 에서 돌린다
   -> `redo_banner.js` 에 import 를 «하나» 더하자 ReferenceError 로 죽었다
      — CLAUDE.md 가 그 금지의 «사유»로 드는 바로 그 문장이다
```
오늘은 그 인라인 목록에 파일 하나를 더해 초록을 유지했고, **C-117 ㉱ 의 «이름 붙은» 멤버**가 됐다 —
익명 부채가 아니라. 그 김에 잰 것: `redo_banner.js` 는 그 하니스가 vm 으로 집는 이름 셋을
«이미 export» 하므로 전환에 새 export 가 필요 없다.

`grid_view_readonly_harness` 의 변이 둘은 «겨냥하던 몸통을 따라» 옮겼다(새 하니스의 M3·M4).
거기서 좌석을 변이시키면 물지 않는다 — `write_guard` 가 «진짜 모듈»을 import 하기 때문이다.
그 파일에 남은 것은 그 파일의 것이다: 컨트롤 목록이 완전한가, 그리고 페이지가 컨트롤에게 말은 하는가.

## 아키텍처 영향

- 같은 물음에 답하는 자리가 넷 → **좌석 하나 + 그것을 지나는 자리들**이 됐다.
- 게이트의 주 단언이 «문장 목록»이 아니라 **성질**이다: 「각 화면에서, 사유 없이 꺼진 컨트롤이 없다」 —
  다섯째 컨트롤이 «존재만으로» 규칙에 들어온다.
  절반은 **대조 방향**이다: 살아 있는 버튼은 사유를 **가지고 있으면 안 된다** —
  안 그러면 수리가 사유를 «옮기기»만 한 것이다.

## 게이트

레인 보고: `disabled_reason_harness.mjs` 19 단언, 결함 변이 9/9 가 각각 자기가 이름 댄 검사에 잡힘,
대조 2/2 탈출. 하니스 130 중 128 게이트, 전부 초록(기존 빨강 둘은 그대로); contracts 12/12; dist 재빌드.
네 대상 모두 import 된다 — 잘라쓰기 없음.

⚠️ 레인이 스스로 적은 한계: **툴팁은 하니스가 단언할 수 있으면서도 «사람이 봐야» 하는 것**이다.

## 그때 남아 있던 것

- **탐색기의 `←` `→` 는 판정 대기**로 남았다. 다음 커밋(`f586188f`)이 그 자리를 다시 다룬다.
- `map_editor2` 의 내보내기 버튼은 이 커밋이 **건드리지 않았다.**
  📌 **뒤에 온 판정:** 2026-09-17 00:47 총괄 **판정 455**(`task/DESIGN_ORDERS.md`)가
  그 버튼은 **꺼진 채로 내놓지 말고 «아예 안 내놓는다»**로 정했다 — 같은 깃발
  (`artifactImplemented()`)이 `hidden` 을 몰게. 이 커밋이 틀렸다는 뜻이 아니다:
  이 커밋은 그 자리에 손대지 않았고, 다음 커밋이 그것을 «CONFLICT» 로 올렸으며, 판정은 그 뒤에 왔다.
