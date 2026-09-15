# 돌릴 수 없는 줄도 «어느 행인지»는 보여 준다 — 신원으로 못 찾는 행을 «객체 동일성»으로, 부품은 그리드를 모르고 함수 하나를 받는다 (C-114, 클라 큐 소진)

> **커밋:** `3bd3b829` — feat(replay): the line that cannot be replayed can still show you the row (design 워크트리) → main 병합 `cae48033`
> **일자:** 2026-09-16 01:34
> **레인:** 클라 — C-112 제안 표에서 채택 → 지시 `fc6729b0` → 착지 → 보고 `9b4e297c`(제안 표 포함, «클라 큐 소진») → 총괄 닫힘 `eea69cbc`(「재기동 PID 41872」)
> **측정 상자:** 이 워크스테이션 + design dev 서버. **운영이 아니다.**
> **스위트:** replay_rules **46/0**(결함 16/16 · 대조군 2/2 · 바닥 40→46 · 신설 단언 4 R1~R4 · 신설 변이 2) · 계약 12/12 · 빌드 · dist 동봉 (클라 보고). 총괄 확인 「46 · 51 초록 · dist 동봉」.

## ① 왜 — 「몇 개」는 알려 줬고 「어느 것」은 못 찾았다

C-112 의 「row_id 없는 행 N — 다시 돌릴 수 없음」은 «수»만 말했다. 그 행들은 «신원으로 찾을 수 없다» — 신원이 «없다는 것»이 그 줄의 주어이기 때문이다. 운영자는 여전히 손으로 찾아야 했다.

## ② 변경 — 부품은 «행»을 들고, 페이지는 «그리드»를 안다

```js
// client2/src/redo_banner.js — scopeValuesFor: «같은 걸음»에서 첫 구멍을 같이 든다
let firstMissing = null;
for (const row of rows || []) {
  const raw = read(row, column);
  if (raw === undefined || raw === null || raw === '') {
    missing += 1;
    if (firstMissing === null) firstMissing = row;         // «첫» 행. 둘째를 보여 주면 운영자를 틀린 자리로 보낸다
    continue;
  }
  ...
}
return { values: seen, missing, firstMissing };
```
```js
// 줄 그리기 — «돌리는 줄»과 «보여 주는 줄»은 다르다
const showable = !pressable && entry.reveal != null && typeof this.reveal === 'function';
const line = doc.createElement(pressable || showable ? 'button' : 'div');
...
} else if (showable) {
  line.type = 'button';
  line.dataset.reveal = 'row';
  line.addEventListener('click', () => this.reveal(entry.reveal));   // params 는 그대로 null — 돌리는 길에 «닿을 수 없다»
}
// chainPayload — skipped 줄이 첫 행을 «싣는다»
? [{ text: `row_id 없는 행 ${missing} — 다시 돌릴 수 없음`, params: null, reveal: firstMissing }] : []
```
```js
// client2/src/main.js — 페이지가 «보여 주는 법»을 준다. 신원으로 못 찾으니 «객체 동일성»으로
reveal: (row) => {
  if (!state.gridApi || !row) return;
  let found = null;
  state.gridApi.forEachNode((node) => { if (!found && node.data === row) found = node; });
  if (found) state.gridApi.ensureNodeVisible(found, 'middle');   // 이력 내비게이터가 8 월부터 쓰던 그 호출
},
```
부품은 그리드 API 를 «모른다» — `run` 과 «같은 규율»로 함수 하나를 주입받는다. 그래서 하니스가 진짜 그리드 없이 채점한다.

## ③ 아무 일 없는 버튼은 «화면이 하는 거짓»이다

주입된 함수가 «없으면» 그 줄은 «그냥 줄»(R4). 그리고 그 누름은 «아무것도 돌리지 않는다»(R3 — `params` 가 null 이라 run 경로에 «닿을 수 없다»). 「보여 주는 줄」은 토큰과 «무관»하다(읽기만 한다).

## ④ «두 벌의 판별식»을 만들지 않았다

첫 구멍을 «밖에서 다시 걸어» 찾으면 「비었나」의 판별식이 두 벌이 되고, 두 벌은 언젠가 갈라진다(기준 ④). 그래서 `scopeValuesFor` 가 «세면서» 같이 들고 나온다 — 같은 걸음, 칸 하나 더. 변이 N16(«마지막 행을 보여 줌»)이 「첫」을 잡는다.

## ⑤ 아키텍처 영향

- 배너 줄의 «종류»가 셋이 됐다: 돌리는 줄(button, params) · 보여 주는 줄(button, reveal) · 그냥 줄(div). 클래스는 «같다»(09-02 소유자 지적 그대로 — 태그가 달라도 흐름이 같아야 한다).
- 부품의 주입 축에 `reveal` 하나가 «더해졌다»(`run`·`handOff`·`hasToken`·`readValue` 옆).
- 그대로인 것: 짐(`row_ids`) · 셈(`missing`) · 경고 줄(C-113).

## ⑥ 그때 남아 있던 것

- «실제 그리드에서 스크롤이 일어나는지»는 8080(main dist)에서만 보인다 — 클라의 확인은 「부품이 주입된 함수를 «그 행»으로 부른다」까지. 함수 본문 두 줄은 이력 내비게이터와 같은 호출이라 새 위험은 없다는 것이 클라의 판단이고, 총괄 닫힘 줄에 «스크롤을 봤다»는 문장은 없다.
- 고른 행이 «다른 페이지»에 있으면(그리드는 페이지 단위로 읽는다) 노드가 지금 없을 수 있고, 그때는 «조용히» 아무 일도 안 난다 — 「없음」과 「안 움직임」이 같아 보인다.
- 클라 제안 표(짓지 않음, 아침에 소유자께): 보여 준 행을 «깜빡이기»(`flashCells` 가 이미 있다) · 그 행이 이 페이지에 없으면 한 줄 · 구멍이 여럿이면 «다음»으로 순회.
- **클라 큐 «소진»** — 이 뒤 정지·대기(15 분 감시만). 서버에 남은 항목은 S-234 하나, 구현자 침묵 중.
- C-111 의 실제 페이지 게이트는 같은 분에 착지한 S-241-b(`7c81c6d5`) 뒤 총괄이 «in-process raw view»로 봤다(어드민 토큰 부재로 폼 픽셀은 못 봄).

---
📎 이 항목의 수(46 · 16/16 · 40→46 · PID)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 이 줄이 태어난 라운드: `20260916_000955_the_banner_sends_row_ids_and_names_the_rows_that_have_none.md` · 경고 줄: `20260916_012250_a_big_selection_says_its_size_and_the_banner_speaks_one_language.md` · 「모든 UI 는 조립식 — 부품은 자기 mount 와 deps 를 받는다」(2026-08-23) · 「같아 보이는 다섯 개의 0」(⑥ 둘째 줄의 부류).
