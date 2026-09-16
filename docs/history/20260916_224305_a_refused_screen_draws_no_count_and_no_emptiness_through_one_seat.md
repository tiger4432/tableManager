# 거절된 화면은 «수»도 «없습니다»도 그리지 않는다 — 좌석 하나를 지나서

> **커밋:** `95a19ff8` (22:43) — 디자인(클라) 레인 · C-121
> **일자:** 2026-09-16
> **레인 보고:** `task/DESIGN_ORDERS.md` · 총괄 검증 `4704abed` (22:56)
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**

## 배경

온톨로지 탐색기가 401 을 이름 대면서, **그 옆에서 「선언 · 0개」와 「표시할 정의가 없습니다」를
같이 그리고 있었다.** 0 만 그리는 것보다 나쁘다 — 둘째는 «거짓»이고, 첫째와 «서로 반대»를 말하며,
고르는 일이 운영자에게 떠넘겨진다.

C-121 은 이 라운드 전에 **한 번 다시 쓰였다** — 첫 판의 전제가 철회됐고, 총괄이 낸 해법도
「둘째 문」이라 함께 철회됐다(`6b1b7c13`). 두 철회 모두 채널에 남겨 뒀다.

## 무엇을 바꿨나

### ① 「이걸 읽었나」를 묻는 좌석은 «하나»다

`countWithAbsence({unread})` 가 **이미** 그 뜻이었고 호출자가 여섯 있었다.
자리마다 `if (!state.error)` 를 적는 것이 «문 가르기»라, 레인이 자기 초안을 되돌렸다.

```js
const appendEmptyLine = (parent, count, unread, text, cls = 'oe-empty') => {
  const cell = countWithAbsence({ value: count, unread: unread || '' });
  if (!cell.read || Number(count) !== 0) return;
  parent.append(h('div', cls, text));
};
```
뷰에는 **어댑터 하나**만 생겼다 — 그 좌석의 답을 「노드」 또는 「아무것도 아님」으로 바꾸는 자리.

### ② 모집단은 «세었다» — 14

**`admin.js`, 8.** 짝지은 빈 상태 블록이 이제 수와 «같이» 거둬진다.

```js
const SECTION_EMPTY_STATE = {
  'file-log-count': 'file-empty',
  … 
  'enrichment-rule-count': 'enrichment-empty',
};
function markSectionUnread(id) {
  setSectionCount(id, UNREAD, null);
  const emptyId = SECTION_EMPTY_STATE[id];
  const el = emptyId ? byId(emptyId) : null;
  if (el) el.style.display = 'none';
}
```
이 블록은 숨김으로 시작하므로 **첫 거절은 이미 정직했다.** 결함은 «둘째 읽기»다 — 한 번
「… 없습니다」가 뜬 뒤 다음 401 이 배지를 「—」로 바꾸고 문장은 세워 뒀다.
목록을 여덟 자리에 흩으면 여덟째가 빠지므로 «맵 하나»다.

🔴 **여덟째는 아예 다른 문으로 실패하고 있었다.** `fetchEnrichmentStatus` 가 던져서 그 탭은
바깥 catch 로 빠지고 `markSectionUnread` 를 «안 지났다» — 거절 배너 옆에 «지난번 수»가
그대로 남았다. 총괄 평: 「그게 제일 나쁜 모양입니다(거절과 수가 «나란히»)」.

```js
+      let status = null;
+      try { status = await fetchEnrichmentStatus(); }
+      catch (err) { markSectionUnread('enrichment-rule-count'); allRead = false; }
       if (isStale()) return false;
-      renderEnrichmentTable(status);
+      if (status) renderEnrichmentTable(status);
```

**`ontology_explorer_view.js`, 6.** 선언 수 · 검색 빈 줄 · 층별 「None defined」 · 사용처 총계 ·
「상위 참조가 없습니다」 · 작업 영역 빈 줄.
그중 **둘은 레인이 앞서 보고하지 않았던 것**이고, 둘 다 자기가 측정한 화면에 있었다:
`renderIntegrity` 는 «선택이 없어도 무조건» 그려져, 거절된 «첫» 로드가
「이 정의를 사용하는 곳 · 0」과 「상위 참조가 없습니다」를 — **일어난 적 없는 읽기에 대해** — 찍었다.

**세고 «뺀» 것도 사유와 함께 적혔다:** 펼칠 선언 / 직접 참조 / active 대비 변경은 선택 관문 뒤라
도착한 payload 에 대해서만 말할 수 있고, `renderStepBar`·`renderAuthoring` 은 빈 낱말 «대신»
`authoringError` 를 이미 찍고 있으며, `diagnostics-empty` 는 거절이 아니라 «안 고름»이다.

### ③ 게이트는 «문장 목록»이 아니라 «성질»이다

거절 시 보이는 텍스트에 「없습니다」가 **하나도 없고**, 어드민 본문에 `admin.html` 이 스스로
선언한 빈 상태 문장 여덟이 **하나도 없다** — 마크업에서 읽어 오므로 문장을 고쳐 검사를
공허하게 만들 수 없고, 아홉째 블록이 생기면 모집단 줄이 빨개진다.

단언의 절반이 **대조 방향**이다: 진짜 0 은 여전히 자기 수 «와» 자기 빈 문장을 찍어야 한다 —
억제만 재는 하니스는 «전부 숨긴 화면»에 만점을 준다(M4 가 문다는 것을 보인다).

측정은 **보이는 노드**로 했다 — `display:none` / `visibility:hidden` 을 걸러서, `textContent` 는 안 쓴다.
그 대리지표가 하루 전 감사에 «철회된 헤드라인»을 실어 보낸 그 자리다.

### ④ 스텁 구멍 셋째

```js
+ replaceChildren(...cs) {
+   for (const c of [...this.children]) this.removeChild(c);
+   for (const c of cs) this.appendChild(c);
+ },
```
`dom_patch.commitTree` 가 «첫 커밋»에 이것을 부른다. 없으면 탐색기가 그 문서에 «한 번도» 못 앉고,
그 화면에 대한 단언 전부가 「아무도 채점하지 않은 주장」이 된다.
두 라운드 안에 같은 부류 셋째다(`id` 접근자 · `remove()` · `replaceChildren`).

## 아키텍처 영향

- **「못 읽음」이 «수»만의 일이 아니게 됐다.** 수와 그 옆의 빈 상태 문장이 한 판단에 묶였다.
- 「같아 보이는 다섯 개의 0」 부류의 실물이다 — 거절의 0 과 진짜 0 이 같은 픽셀이었다.

## 🔴 클라가 «안 한» 것이 이 라운드의 판정이다

「진짜 0 이 «어떤» 0 인가」(`truly_none` 인지 `not_yet` 인지)를 **클라가 고르지 않았다.**
그 낱말은 «데이터의 성질»이지 화면의 성질이 아니고, 화면이 고르면 재지 않은 사실을 «저작»하는 것이다.
총괄이 그 판단을 승인하고 절반을 서버 라운드로 큐에 넣었다.

## 게이트

레인 보고: `absence_on_refusal_harness.mjs` 39 단언, 결함 변이 11/11 이 각각 자기가 이름 댄 검사에 잡힘,
대조 2/2 탈출. 하니스 129 중 127 게이트, 전부 초록; contracts 12/12; 같은 커밋에 dist 재빌드.
두 대상 모두 **import** 된다 — 뷰가 렌더러를 export 하고, `admin.js` 는 `probe_hooks.mjs` 가
`.css` 를 빈 모듈로 풀어 주어 통째로 로드된다(C-95).

총괄 확인: 좌석 하나 ✅ · 어댑터 하나 ✅ · 하니스 305줄 + `check_harnesses` 등록 ✅ ·
dist 재빌드(`admin-BdzNAuTZ.js`) ✅.

## 그때 남아 있던 것

- **서버 몫 절반은 안 닫혔다.** 「거절될 수 있는 읽기에서 0 을 돌려줄 수 있는 라우트」의 전수와,
  라우트마다 「서버는 «구별할 수 있나»」가 열려 있었다. 그동안 화면은 «맨 0» 이고, 그건 오늘과 같다.
- 레인이 자기 수를 무른 기록이 남아 있다 — 「셋이라 보고했는데 «다섯»이었다. 계기 탓이 아니라
  머리글 둘을 옮기고 나머지를 안 셌다」. 모집단 14 와 술어를 «적어» 낸 것이 그 보고의 값이다.
