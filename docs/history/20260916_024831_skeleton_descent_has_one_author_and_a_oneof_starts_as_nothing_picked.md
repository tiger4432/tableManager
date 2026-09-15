# 스켈레톤 내려가기에 «저자가 하나» 생겼다 — record · map · oneOf 를 `childOf` 하나가 내려가고, `oneOf` 의 빈 값은 「안 고름」= `{}` 다 (새 규칙 씨앗의 `derive`/`into` 가 `""` 에서 `{}` 로) (C-115)

> **커밋:** `dd4cd689` — feat(skeleton): descent has one author, and it follows a oneOf by branch key (C-115) → main 병합 `17e26a04`
> **일자:** 2026-09-16 02:48
> **레인:** «워크트리 서브에이전트»(클라 대행) — 야간 코드맵 정비 패스가 잡음(보드 `3670e31f` ③ 「`ontology_skeleton.js` 가 oneOf 안의 oneOf 를 못 내려감」) → C-115 등급 4 큐 → 에이전트 → 총괄 닫힘 `2c93ae9f`
> **측정 상자:** 이 워크스테이션. **운영이 아니다.**
> **스위트:** 신설 skeleton_oneof_descent **15/0** · 변이 **3/3** 잡힘(바닥 15 등록) · declaration_attribute_seats **18/0** 유지, map 변이를 공유 헬퍼로 «다시 겨눔» **5/5** · 게이트 「127 하니스, 125 게이트 초록」 · dist 재빌드 (커밋 본문). 총괄 확인 「15/0 · `""`→`{}`」.

## ① 왜 — «두 독자»가 같은 문법을 각자 읽고 있었다

`shapeAt`(경로를 걸어 노드를 찾는다)과 `emptyOf`(노드의 빈 값을 심는다)가 record·map 내려가기를 «각자» 적고 있었다. S-241 로 `oneOf` 가 어휘에 들어오자 «둘 다» 그 노드를 몰랐고 — 오늘 화면의 호출자가 «이미 고른 노드»만 건네서 아무것도 안 깨졌다. 그래서 oneOf «안의» oneOf 는 둘 다에 보이지 않았다. 문서 정비 패스가 코드를 읽다 잡은 것이지 화면이 보여 준 것이 아니다. 「같은 기능에 두 경로가 있어서는 안 된다 — 둘이 «갈라질 수» 있나」(구성 기준 ④)의 실물이고, 다음 노드 종류가 올 때 «독자마다 한 줄»이 되는 자리였다.

## ② 변경 — 내려가기 «한 함수», 가지는 «가지 키 밑»

```js
// client2/src/ontology_skeleton.js
function childOf(node, step, defs) {
  if (!node) return null;
  if (node.kind === 'record') { const field = (node.fields || []).find((item) => item.key === String(step));
                                return field ? deref(field.node, defs) : null; }
  if (node.kind === 'map') return deref(node.of, defs);                    // 모든 멤버가 같은 모양
  if (node.kind === 'oneOf') { const branches = node.branches && typeof node.branches === 'object' ? node.branches : {};
                               const branch = branches[String(step)]; return branch ? deref(branch, defs) : null; }
  return null;                                                              // 잎 밑엔 아무것도 없다
}
export function shapeAt(node, steps, defs) { let cursor = deref(node, defs);
  for (const step of steps) { if (!cursor) return null; cursor = childOf(cursor, step, defs); } return cursor; }
// emptyOf — oneOf 는 「안 고름」으로 태어난다
if (shape.kind === 'oneOf') return {};
...
const child = childOf(shape, field.key, defs);        // record 의 자식도 «같은 독자»로
```
oneOf 는 «가지 키»로 내려간다 — 판정 411 「가지 노드는 가지 키 «밑»에 산다」(`derive.join` 은 record, `into.table` 은 leaf, 키가 곧 칸). 머리 주석의 「세 종류, 넷째 없음」은 「네 종류, 다섯째 없음」이 됐다.

## ③ «안 고름»은 `''` 가 아니라 `{}` 다 — 화면이 안 보여 주는 회귀

실측(커밋 본문) «전»: 출하된 새 규칙 씨앗이 `{"derive":"","into":""}` — 필수 oneOf 가 `emptyOf` 의 «잎 꼬리»로 떨어져 «문자열»로 심어졌다. 렌더러는 이름 없는 값에 가지를 안 그리고 로더(`rule_shape.from_declaration`)는 `''` 와 `{}` 를 «같이» kind "unknown" 으로 접어서, «양쪽이 관대한 동안만» 같은 모양으로 그려지고 같은 모양으로 읽힌다. 문법이 적는 것은 «매핑에 가지가 키 밑에 있는 것»이라, 안 고른 oneOf 는 «키 없는 그 매핑» = `{}` 이다. «후»: 둘 다 `{}`. 하니스 E4 가 «출하된» 스켈레톤에서 이것을 고정한다 — 화면에서는 보이지 않을 회귀라서.

## ④ 하니스 — 대상 «둘», 독자 «하나»

```js
// client2/tests/skeleton_oneof_descent_harness.mjs — 대상을 IMPORT 한다
const CHAIN = JSON.parse(readFileSync(join(ROOT, 'server', 'chain_skeleton.json'), 'utf8'));   // 출하된 스켈레톤(추적 파일)
const NESTED = { kind: 'record', fields: [{ key: 'pick', required: true, node: { kind: 'oneOf', branches: {
  outer_a: { kind: 'oneOf', branches: { inner_x: { kind: 'leaf', hint: 'ref' }, inner_y: { use: 'shared' } } },
  outer_b: { kind: 'leaf', hint: 'free' } } } }, ... ] };                                        // 손 픽스처 — oneOf 안의 oneOf
ok(at(['derive', 'join', 'right_table']).kind === 'leaf', 'D2 ...');   // 오늘 화면이 «실제로» 내려가는 길
ok(at(['derive', 'no_such_branch']) === null, 'D4 CONTROL');          // «아무 키에나» 답하는 독자를 거른다
ok(M.shapeAt(NESTED, ['pick', 'outer_a', 'inner_y', 'inside'], DEFS).kind === 'map', 'N3 `{use}` 가지도 걸어 통과');
ok(M.emptyOf(M.shapeAt(NESTED, ['pick', 'outer_b'], DEFS), DEFS) === '', 'E5 CONTROL: 잎 가지는 여전히 잎처럼 빈다');
```
출하된 `chain_skeleton.json` 은 oneOf 둘을 «들지만» oneOf 안에 oneOf 를 «싣지 않는다» — 중첩은 «문법의 주장»이지 그 문서의 주장이 아니라서 손 픽스처로 재고 «그렇다고 적는다». 출하 문서는 오늘 화면의 길을 재고, 생성기에서 가지가 빠지면 클라 쪽에서 빨개진다. 변이 셋: oneOf 내려가기 끄기 · 아무 키에 첫 가지 답하기 · oneOf 빈 값을 잎 꼬리로 되돌리기 — 셋 다 잡힘. `declaration_attribute_seats` 의 map 변이는 옛 `shapeAt` 본문 줄을 겨누고 있었으니 «공유 헬퍼의 한 줄»로 옮겼다(앵커가 없어졌으면 프로브가 거절했을 것).

## ⑤ 아키텍처 영향

- 스켈레톤 «내려가기»의 저자가 `childOf` «하나». 다음 노드 종류는 «한 곳의 가지 하나»다.
- oneOf 의 빈 값 계약: `{}`(안 고름). 렌더러 · 로더 · 문법 «셋»이 같은 사실을 각자 말하고, 이제 씨앗도 그 모양이다.
- 그대로인 것: `deref`·`use` 따라가기 · record 의 «필수 컨테이너는 처음부터» 규칙 · map 의 `[]`/`{}` · 렌더러(C-111) · 로더(`rule_shape.from_declaration`).

## ⑥ 그때 남아 있던 것

- 출하된 어떤 스켈레톤도 oneOf «안에» oneOf 를 «싣지 않는다» — 중첩 경로는 손 픽스처에서만 참으로 잰 것이고, 화면이 그 길을 걸은 적은 없다.
- 로더가 `''` 와 `{}` 를 «여전히» 같이 접는다 — 이 커밋은 «심는 쪽»을 고쳤고 «읽는 쪽의 관대함»은 그대로다. 저장된 옛 씨앗(`""`)이 있다면 그것도 여전히 unknown 으로 읽힌다.
- dist 재빌드에 `map_editor.html` 926 줄 · `walk.html` 60 줄 변경이 «같이» 실렸다 — 이 커밋의 소스 변경은 `ontology_skeleton.js` 57 줄과 하니스뿐이므로 그 둘은 «빌드 시점의 트리»가 낸 차이다(어떤 소스 커밋의 것인지 이 커밋만으로는 알 수 없다).
- 「127 하니스, 125 게이트 초록」 — 게이트에 «안 들어간 둘»이 무엇인지 커밋 본문에 없다.
- 클라 레인은 «정지» 중 — 클라의 검수 줄은 없다.

---
📎 이 항목의 수(15 · 3/3 · 18 · 5/5 · 127/125 · 926)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 oneOf 가 태어난 자리: `20260916_004105_the_skeleton_declares_the_unified_grammar_and_a_branch_node_lives_under_its_key.md`(S-241/-b, 판정 407·411) · 그것을 그리는 쪽: `20260916_010926_pick_one_is_drawn_from_the_skeleton_and_the_flat_registry_stays_until_the_flat_grammar_retires.md`(C-111) · 「같은 기능에 두 경로 — 둘이 «갈라질 수» 있나」(구성 기준 ④, 2026-09-06).
