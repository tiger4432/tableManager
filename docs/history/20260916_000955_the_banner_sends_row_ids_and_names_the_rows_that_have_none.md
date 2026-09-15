# 배너는 그리드가 «들고 있는» 신원(`row_id`)을 보내고, 신원 «없는» 행은 이름을 달고 선다 — 그리고 하니스는 «보내는 것의 절반»만 보고 있었다 (C-112)

> **커밋:** `1295fab4` — feat(replay): the banner sends the identity the grid HOLDS, and names the rows that have none (design 워크트리) → main 병합 `cf50498b`
> **일자:** 2026-09-16 00:09
> **레인:** 클라 — S-254 서버 절반(`fe2d0c6c`) 뒤 초인종 `2cb960e1` → 착지 → 보고 `288420e4`(제안 표 포함) → 총괄 닫힘 `a5d55d8f`
> **측정 상자:** 이 워크스테이션 + design 워크트리 dev 서버(5174). **운영이 아니다.**
> **스위트:** replay_rules **34/0**(결함 변이 12/12 «이름 댄 단언»으로 잡힘 · 대조군 2/2 탈출 · 바닥 28→34) · redo_banner **51/0**(단언 «셋»을 지우지 않고 «반대로» 세움) · 계약 12/12 · 빌드 · `client2/dist` 동봉 (클라 보고). 총괄 확인 「하니스 34 + 51 초록 · dist 같이 · 실제 페이지(8080, dt_log 두 행 선택) 팝업 「2 rows」(전엔 「1 key from 1 row」)」.

## ① 왜 — 22:3x 의 셋째 발견, 클라 절반

배너가 «보이는 것»을 업무 키로 보냈고, composite 표의 저장 키는 «어느 컬럼에도 없는 조립 문자열»이라 서버가 한 행도 못 찾았다 — `rows_scanned 0`, 오류 없이. 서버가 `row_ids` 를 받게 됐으니(S-254) 이제 화면이 «그것을 보내야» 한다.

## ② 변경 — 새 배관 0, «컬럼 이름 하나»

```js
// client2/src/redo_banner.js — chainPayload
const { values, missing } = scopeValuesFor(rows, 'row_id', this.readValue);   // 종전: this.businessKey
if (!values.length) return { note: 'the selected rows carry no row_id' };
const from = `${values.length} row${values.length === 1 ? '' : 's'}`;         // 종전 「N keys from M rows」
const payload = { op: 'chain_replay', params: { row_ids: values.join(',') } }; // 종전 { businessKeys: values }
...
const skipped = missing
  ? [{ text: `row_id 없는 행 ${missing} — 다시 돌릴 수 없음`, params: null }] : [];
rows: skipped.concat(this.rules.map((rule) => ({ ..., params: name ? { rule: name, row_ids: keys } : null })))
```
```js
// client2/src/main.js — 업무 키를 더는 넘기지 않는다 (읽는 자리가 «하나»였다)
-  redoBanner.setBusinessKey(state.currentBusinessKey);
-    businessKey: state.currentBusinessKey || null,
```
그리드 행은 `row_id` 를 «이미» 든다(`grid.js` 의 `getRowId` · 삭제 경로가 몇 달째 `node.data.row_id` 를 `row_ids` 라는 이름으로 모아 왔다). 이 부품에 주입된 읽개가 봉투에 없는 키를 `row[col]` 로 떨어뜨리므로 «컬럼 이름만» 바뀌었다. `business_keys` 는 «아무도» 안 보낸다 — 서버가 둘 다 오면 거절하고, 평키 표만 옛 길을 타게 두면 «그 표에서만 나는 고장»이 남는다(기준 ④). `businessKey` 옵션과 `setBusinessKey` 는 부품에서 은퇴했다.

## ③ 🔴 하니스가 «보내는 것의 절반»만 보고 있었다 — 변이가 탈출했다

이 화면이 보내는 것은 «둘»이다: 줄을 누를 때의 `params` 와 「Open in admin」이 넘기는 짐(`adoptRescopeHandoff` 가 `params` 를 그대로 앉힌다). 첫 판 단언 B9 는 «누르는 길»만 봤고, 「두 신원을 다 보낸다」 변이(N12 — 서버가 거절하는 바로 그것)가 **탈출**했다. 둘 다 보게 고치니 잡혔다. 같은 손질에서, 줄이 없을 때 첨자로 들어가 «던지던» 변이(N10)를 «채점»으로 바꿨다 — 던진 하니스는 「잡았다」가 아니라 구멍이다.

## ④ 못 도는 행은 «이름을 달고» 선다 (판정 407 ②)

`row_id` 는 중복이 없어 «값의 수 = 행의 수» — 「N keys from M rows」가 「M rows」로 «접혔다». 신원 없는 행은 조용히 빠지지 않고 「row_id 없는 행 N — 다시 돌릴 수 없음」으로, «누를 수 없는 줄»로, 규칙 줄 «위»에 선다 — 각 줄이 「3 rows」라 말하는 이유가 그것이기 때문이다.

## ⑤ 지우지 않고 «반대로» 세운 단언 셋

redo_banner 하니스의 D1(업무 키를 «접어서» 넘긴다 → 모든 행을 «그대로» 넘긴다: row_id 는 접을 것이 없다) · D3(업무 키 없는 표는 문장 하나 → 업무 키 없어도 «돌린다») · M5 앵커(넘김 짐 모양 이동). 지우면 「신원이 바뀌었다」를 재는 줄이 아무데도 안 남는다.

## ⑥ 아키텍처 영향

- 그리드 → 소급의 «행 신원»이 하나(`row_id`)로 섰고, 누르는 길과 넘기는 길이 «같은 신원»을 나른다.
- 부품의 옵션 축 하나(`businessKey`)가 «은퇴» — 「표마다 알려 줄 것」이 없어졌다.
- 그대로인 것: 원장 쪽(`ledgerPayload` — 범위 컬럼 그룹) · 규칙 목록의 출처(C-109) · `scopeValuesFor` 의 셈.

## ⑦ 그때 남아 있던 것

- 클라가 «실제 그리드(8080)»는 못 걸었다 — main 의 dist 를 섬기므로. 총괄 닫힘 줄이 본 것은 배너 문구 「2 rows」이고, «서버 세기가 0 이 아닌 것»을 봤다는 문장은 닫힘 줄에 없다.
- 「row_ids 의 행이 이 규칙의 트리거 표가 아닐 때」 서버가 무엇이라 하는지는 «안 쟀다»(화면은 이 표의 규칙만 내밀어 그 경로가 나오려면 표를 바꾸고 판을 열어 둔 채 눌러야 한다).
- 문구는 아직 «영어 문장»이었다(「no admin token on this browser — …」 · 「Open in admin」) — 다음 라운드 C-113.
- 클라 제안 표(짓지 않음): 「row_id 없는 행」 줄을 누르면 그 행으로 스크롤(→ C-114) · 1,000 행 경고(→ C-113). C-111 은 S-241 뒤.

---
📎 이 항목의 수(34 · 12/12 · 51 · 「2 rows」)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 서버 절반: `20260915_234857_the_grid_replays_by_the_identity_it_holds_and_two_answers_are_refused.md` · 배너가 «그때부터» 이 결함을 들고 있던 커밋(C-109): `20260915_170746_the_grids_replay_list_belongs_to_the_table_and_the_loader_left_main_js.md` · 「던진 변이는 잡힐 게 아니다」(2026-08-23).
