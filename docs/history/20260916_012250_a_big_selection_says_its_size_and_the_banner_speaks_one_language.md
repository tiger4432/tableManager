# 큰 선택은 «자기 크기»를 한 줄로 말하고 «막지 않는다» — 기준은 부품에 박지 않고 옵션으로, 그리고 배너가 한 언어로 말한다 (C-113)

> **커밋:** `7156ee62` — feat(replay): a big selection says its size, and the banner speaks one language (design 워크트리) → main 병합 `0444cbfb`
> **일자:** 2026-09-16 01:22
> **레인:** 클라 — C-112 제안 표에서 총괄이 채택(`48d8ffa5`) → 지시 `664609d7` → 착지 → 보고 `429d5c9f`(제안 표 포함) → 총괄 닫힘 `fc6729b0`
> **측정 상자:** 이 워크스테이션 + design dev 서버(5174, `warnAbove: 2` 로 «일부러» 낮춰 봄). **운영이 아니다.**
> **스위트:** replay_rules **40/0**(결함 14/14 · 대조군 2/2 · 바닥 34→40 · 신설 단언 4 W1~W4 · 신설 변이 2) · redo_banner **51/0**(단언 다섯 + 변이 앵커 하나를 «오늘의 낱말»로) · 계약 12/12 · 빌드 · dist 동봉 (클라 보고). 총괄 확인 「51 · 40 초록 · dist 동봉」.

## ① 왜 — 운영 규격은 「한 트랜잭션에 수천 행」이다

큰 선택은 «틀린 것이 아니라 큰 것»이다(소유자 2026-09-08 규격). 막으면 정당하게 큰 범위를 돌릴 길이 없어진다. 그래서 화면은 «수 둘»만 적고, 누를지는 사람이 정한다. 그리고 C-112 시점의 배너는 영어 «문장» 여섯을 말하고 있었다 — 「설명 문구 주저리 금지」·「기호·짧은 영어·명사형」 상설과 어긋난다.

## ② 변경

```js
// client2/src/redo_banner.js
this.warnAbove = typeof options.warnAbove === 'number' ? options.warnAbove : 1000;   // 🔴 «얼마부터 큰가»는 이 부품이 정하지 않는다
...
const picked = this.getSelection ? (this.getSelection() || []) : [];
if (picked.length > this.warnAbove) {
  const big = doc.createElement('div');
  big.className = 'redo-panel__warn';
  big.textContent = `선택 ${picked.length}행 · 권장 ${this.warnAbove}행 이하`;         // 수 둘, 그것뿐. 줄들 «위». 막지 않는다
  box.appendChild(big);
}
```
```js
// 문장 여섯 → 명사형
'no admin token on this browser — open admin once, then come back'  → '관리자 토큰 없음 · 어드민 한 번 열기'
'Open in admin'                                                       → '어드민에서 열기'
'chain rules not loaded — open in admin to pick one'                  → '규칙 목록 못 읽음 · 어드민에서 선택'
'this table is not a ledger source'                                   → '원장 소스 아님'
'this source declares no scope column'                                → '범위 컬럼 선언 없음'
'no scope column has a value in the selected rows'                    → '선택 행에 범위 값 없음'
'the selected rows carry no row_id'                                   → '선택 행에 row_id 없음'
```
```css
/* client2/src/style.css — 투명도를 낮추지 않는다: 이것은 주문이 아니라 «수»다 */
.redo-panel__warn { padding: 8px 12px; width: 100%; color: var(--warning); border-bottom: 1px solid var(--border); }
```
크기 문자열(`3 rows` · `2 groups from 3 rows`)은 «그대로» — 상설이 짧은 영어를 «허용»하고, 그것까지 바꾸면 수를 세는 단언 전부를 건드리면서 읽는 사람에게 남는 것이 없다.

## ③ 기준을 «박지 않은» 이유가 변이로 서 있다

숫자를 부품에 박으면 그 숫자가 «이 박스의 것»인데 «모든 설치에 대해 참인 척»하게 된다 — 「임시로 박스에 설정한 것으로 말하지 말 것」 상설의 «코드 판». W4 는 「기본값에서 3 행은 조용, 1,001 행은 한 줄」로 옵션임을 재고, 변이 N14(«1000 을 박음»)와 N13(«전부 크다고 함»)이 그것을 잡는다.

## ④ 문구를 바꾸면 «문구를 베낀 하니스»가 빨개진다 — 주장은 그대로, 낱말만 오늘 것으로

redo_banner 하니스의 단언 다섯(`'no value'`·`'no scope column has a value'`·`'token'`·`'not loaded'`…)과 변이 M14 의 앵커가 옛 문장을 «글자로» 들고 있었다. 주장(「값 없는 컬럼은 안 넘긴다」 등)은 바꾸지 않고 찾는 낱말만 갈았다. 📌 「하니스가 문구를 베끼면 그 문구의 둘째 저자가 된다」(2026-09-13)의 다음 사례 — 이번엔 «여섯 문장에 여섯 자리»였다.

## ⑤ 아키텍처 영향

- 배너에 «옵션 축» 하나(`warnAbove`)가 생겼다. 값의 저자는 «화면»(주입)이고, 부품의 기본값은 «운영 규격 한 자리 아래»로 잡은 것이다.
- 「경고는 막지 않는다」가 부품의 성질로 섰다(W3: 넘어도 줄은 눌린다).
- 그대로인 것: 짐의 모양(`row_ids`) · 규칙 줄 · 원장 쪽 그룹.

## ⑥ 그때 남아 있던 것

- 기본값 1000 이 «이 제품의» 옳은 기준인지는 «모른다» — 소유자 몫이고, 부품에 «안 박힌» 것이 요점이다(총괄 「그 수가 이 제품의 기준인지는 소유자 몫」).
- 1,000 행이 넘는 선택을 «실제로 돌렸을 때» 서버가 어떻게 견디는지는 클라가 못 쟀다(박스 규격 밖).
- `main.js` 는 `warnAbove` 를 «넘기지 않았다» — 이 시점 실제 페이지는 기본값 1000 으로 돈다.
- 클라 제안 표(짓지 않음, 아침에 소유자께): 경고 줄에 «예상 시간»(서버 반 필요) · 원장 쪽 줄에도 같은 경고(그쪽은 «그룹 수»가 크기라 다른 수가 맞을 수 있음).
- 다음 C-114(「row_id 없는 행」 줄 누르면 스크롤).

---
📎 이 항목의 수(40 · 14/14 · 51 · 34→40 · 1000 · `warnAbove: 2`)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 ①의 소유자 규격 인용뿐이다.
📎 앞 라운드: `20260916_000955_the_banner_sends_row_ids_and_names_the_rows_that_have_none.md` · 규격의 출처: CLAUDE.md 「운영에서 재는 것은 보안상 불가능하다 — 박스를 운영 모양으로」(2026-09-08) · 문구 상설: 「설명 문구 주저리주저리 금지」(2026-09-04) · 「UI 문구는 번역체 금지」(2026-08-05).
