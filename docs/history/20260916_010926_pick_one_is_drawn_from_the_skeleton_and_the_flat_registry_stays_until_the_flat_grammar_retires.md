# 「셋 중 하나」를 폼이 «스켈레톤대로» 그린다 — 새 입력 0 줄, 고른 가지만, 그리고 평면 등록부의 `oneOf` 는 «평면 문법이 은퇴하는 날»까지 남는다 (C-111, 판정 412)

> **커밋:** `321e03c3` — feat(form): 「pick one」 is drawn from the skeleton, and only the picked branch carries cargo (design 워크트리) → main 병합 `a820ad1f`
> **일자:** 2026-09-16 01:09
> **레인:** 클라 — S-241(`0dda6f08`) 초인종 → 짓기 «전» 실측 `fedf6a15`(가지 셋이 한 층 깊다 → 판정 411) → 판정 411 규칙으로 지음 → 보고 `d39d46da`(판정 하나 요청) → 총괄 판정 412 · 닫힘 `664609d7`
> **측정 상자:** 이 워크스테이션 + design dev 서버. **운영이 아니다.**
> **스위트:** chain_rule_form **80/0**(결함 변이 40/40 «이름 댄 단언» · 대조군 2/2 탈출 · 바닥 69→80 · 신설 단언 11 U1~U11 · 신설 변이 3) · 이웃 chain_rule_user_path **44/0** · chain_rule_panel **59/0** · closed_list 오라클 «자리 셋»으로 갱신 · 계약 12/12 · 빌드 · dist 동봉 (클라 보고). 총괄 확인 「80 · 59 · 44 초록 · dist 에 oneOf」.

## ① 왜 — 서버가 `oneOf` 를 내니 «그릴 갈래»가 있어야 한다

판정 407 의 노드가 서버에 섰다(S-241). 그것을 «손으로» 그리면 화면이 문법의 둘째 저자다(계획 §9.2 「새 칸을 위한 화면 코드 0 줄」). 그리고 판정 411 이 「가지 노드는 가지 키 «밑»」을 정했다 — 모든 커밋된 선언이 이미 그 모양이다.

## ② 변경 — 렌더러에 갈래 «하나», 패널에 «갈아 끼우기» 하나, 등록부에 «문법 낱말»

```js
// client2/src/ontology_explorer_view.js — renderSkeletonForm
if (shape.kind === 'oneOf') return renderSkeletonOneOf(context, shape, path, value, depth, label, required);

function renderSkeletonOneOf(context, node, path, value, depth, label, required) {
  const names = Object.keys(node.branches);
  // 「지금 무엇을 골랐나」는 로더와 «같은 순서»: 적힌 `kind` 먼저, 없으면 «든 가지 키»(rule_shape.from_declaration)
  const stated = typeof held.kind === 'string' && branches[held.kind] ? held.kind : '';
  const chosen = stated || names.find((name) => held[name] !== undefined) || '';
  head.appendChild(renderClosedList(closedListChoice(names, chosen, { loaded: true, name: path }), h,
                                    { action: 'edit-shape-branch', path, label }));      // 이미 있는 «닫힌 목록 컨트롤»
  if (chosen && branches[chosen]) {                                                       // 고른 가지 «만». 안 고른 자리엔 «아무것도» 없다
    box.appendChild(branch.kind === 'record'
      ? renderSkeletonRecord(context, branch, `${path}.${chosen}`, held[chosen], depth)   // 고르개 «바로 밑»에 편다 (③)
      : renderSkeletonForm(context, branches[chosen], `${path}.${chosen}`, held[chosen], depth + 1, chosen));
  }
}
```
```js
// client2/src/raw_registry_panel.js — 고르기는 칸 하나를 적는 것이 아니라 «짐을 갈아 끼우는» 일
if (action === 'edit-shape-branch') {
  const next2 = {};
  if (Object.prototype.hasOwnProperty.call(kept, 'kind')) next2.kind = picked2;   // 적혀 있던 kind 는 «지키되 맞춘다» — 지우지도 만들지도 않는다
  const branchNode = oneOfNode && oneOfNode.branches ? oneOfNode.branches[picked2] : null;
  next2[picked2] = kept[picked2] === undefined
    ? (branchNode ? emptyOf(branchNode, defs) : {})                                // 잎이면 '' · 레코드면 {} — 항상 {} 면 잎 자리에 «문법에 없는 모양»
    : kept[picked2];
  ...writeShapeAtPath(held2, path, next2)                                          // 고른 가지 하나만 남고 나머지는 «간다»
}
```
```js
// client2/src/chain_rule_panel.js — CHAIN_RULE_REGISTRY
formRoot:  (payload) => (payload.grammar === 'unified' ? skeleton.unified_root : skeleton.root) || null,
grammarOf: (payload) => (typeof payload.grammar === 'string' ? payload.grammar : ''),   // 서버가 안 말했으면 «안 그린다»
```
선택지는 `branches` 의 «키»다 — 서버가 `list` 를 안 내는 사유(체인 쪽에 닫힌 목록 서버가 없음)를 클라가 옳다고 받았다. 「안 고름」과 「비어 있음」은 다른 사실이라 안 고른 가지는 그리지 않는다(§9.3 ①). 두 가지가 한 `derive` 에 남으면 «로더가» 고르게 되고, 그 고르기는 화면이 안 보여 준 판정이다.

## ③ 짓다가 잰 것 — 가지를 «상자에 넣으니» 접혔다

가지를 자기 노드 상자로 감싸니 깊이 규칙에 «접혀서», `join` 을 골라도 «닫힌 상자만 보이고 적을 칸이 없었다». 칸들을 고르개 «바로 밑»에 폈다 — 목업도 거기에 둔다. 상자의 이름은 바로 위 고르개가 «이미 말한» 낱말이었다.

## ④ 🔴 판정 412 — 지시받은 «한 걸음»을 안 했고, «왜»를 전수로 쟀다

지시는 `CHAIN_RULE_REGISTRY.oneOf` 「은퇴」였다. 클라가 그 칸이 «무엇을 먹이는지» 셌다: 평면 폼의 «네» 동작 — 두 철자 규칙에서 맵퍼 고르개가 고른 것을 보임(C-101 ③) · 둘째 철자를 「고급」 뒤로(C-95 ③) · 쓸 때 펴기(split) · 맵퍼 목록의 메모가 그 칸 밑에(C-106 ⑥). 넷 다 «평면 문법»의 것(`mapper` ↔ `mapper_module`+`mapper_function`)이고 통합 문법은 `derive.mapper` «한 칸»이라 그 기제가 필요 없다. 오늘 내리면 소유자가 화면에서 본 셋이 «한 번에» 되돌아간다.
```
판정 412 (총괄)  은퇴는 «평면 문법이 은퇴하는 날»(S-234 통째, 계획 4 단계)에 같이.
               「지금 이미 둘」이 아니라 「곧 하나」가 될 자리다.
               그때까지 두 기제는 «겹치지 않는다»: 스켈레톤 `oneOf` = 통합 · 등록부 `oneOf` = 평면
```

## ⑤ 게이트에서 «과장하지 않고» 적은 것

렌더러 쪽 주장(고른 가지만 · 가지 키 밑 · 안 고르면 없음)은 «진짜 모듈»로 채점했고 «변이는 못 걸었다» — 이 하니스는 한 번에 «모듈 하나»만 갈아 끼우고, 폼을 그리는 것은 다른 파일(`ontology_explorer_view.js`)이다. 신설 변이 셋은 패널 쪽(두 가지를 다 남김 · 고르기가 문서에 안 닿음 · 문법 낱말 안 그림). U8 은 「폼의 모든 컨트롤이 스켈레톤 주소를 단다」를 «수»로 단언한다(손그림 0 — 머리의 규칙 고르개는 폼의 칸이 아니라 «일부러» 제외). closed_list 오라클의 「부품에게 묻는 자리」 수가 2→3 — 수를 올리는 것이 오라클을 무디게 하지 않는다: 그 줄이 한 일이 바로 「새 자리가 생겼다」를 말한 것이다.

## ⑥ 아키텍처 영향

- 스켈레톤 어휘 `oneOf` 의 «소비자»가 생겼다 — 렌더러 갈래 하나, 패널 액션 하나(`edit-shape-branch`). 새 입력 컨트롤 «0».
- 「어느 문법인가」가 화면에 «한 낱말»로 선다(`flat` | `unified`). 이행 중 같은 화면이 규칙마다 다른 칸을 내미는 «이유»가 화면 안에 있다.
- 그대로인 것: 평면 폼과 그 등록부 `oneOf`(판정 412) · 닫힌 목록 부품 · `writeShapeAtPath`/`emptyOf`.

## ⑦ 그때 남아 있던 것

- **실제 페이지 게이트는 «참이 아니었다»** — S-241-b(서버 세 줄) 전에는 `into` 와 `derive.mapper` 가 record 라 폼이 한 층 깊게 그렸다. 클라는 그 상태로 「폼이 참」이라 적지 않았고, 초인종 뒤 `?name=inventory_confirmed` 스샷을 약속했다. S-241-b 는 26 분 뒤 총괄이 착지시켰다.
- `shapeAt` 은 «가지 안»으로 못 걷는다(중첩 `oneOf` 는 오늘 없다).
- `CHAIN_RULE_REGISTRY.oneOf` 는 «남아 있다» — 판정 412 대로.
- 클라 다음: C-113(1,000 행 경고 + 한국어 문구) → C-114.

---
📎 이 항목의 수(80 · 40/40 · 59 · 44 · 2→3 · 26 분)는 «이 박스»의 것이다. 「운영」이라 적은 줄은 없다.
📎 서버 절반: `20260916_004105_the_skeleton_declares_the_unified_grammar_and_a_branch_node_lives_under_its_key.md` · 이 칸이 먹이는 세 화면: C-95 ③ · C-101 ③ · C-106 ⑥ 의 항목들(2026-09-13 계열) · 「무한 케이스인가, 여럿이 될 거라는 베팅인가」(판정 412 의 근거 부류).
