// CHAIN RULE — 체인 규칙 하나를 «제품 안에서» 등록합니다.
//
// 🔴 이 파일도 «선언»입니다 — 모양은 `raw_registry_panel.js`. 표 등록과 «같은 모양»이라고
//    지시받았고, 그래서 두 번째를 손으로 그리지 않았습니다.
//
// 읽는 것: `GET /admin/chain/rules/raw`. 쓰는 것: `POST` 같은 주소, «규칙 하나» 단위.
//
// ═══ 표 등록과 «다른» 것 하나 ═══════════════════════════════════════════════════════
//
// 🔴 저장이 «장전»까지입니다. 표는 저장해도 아무것도 «안 돌지만», 규칙은 다음 리로드에
//    «돕니다» — 그래서 서버가 «새» 규칙을 `enabled: false` 로 적어 저장합니다.
//    그 사실을 화면이 «말하지 않으면» 운영자는 「저장했는데 왜 안 도나」로 헤맵니다.
//
//    ✅ 그래서 «값»을 보여 줍니다 — `enabled` 는 서버의 낱말이고, 참/거짓은 서버의 값입니다
//    ⛔ 문장을 짓지 않습니다 (소유자 상설: 「ui에 설명 문구 주저리주저리 금지」)
//    ⛔ 「켜기」 전용 컨트롤을 만들지 «않습니다» — 원문 편집기에서 `enabled` 를 고치면
//       됩니다 (소유자 판정: 「두 번째 컨트롤을 발명하지 않는다」)
//    🔴 그리고 «세 상태»입니다: true · false · «키가 없음»(이름을 안 고른 응답).
//       없는 것을 `false` 로 그리면 「안 물어봤다」가 「꺼져 있다」가 됩니다.

import { registryView, RawRegistryPanel } from './raw_registry_panel.js';

/**
 * 저장 답이 있으면 그것이 «더 새 사실»입니다 — 방금 쓴 값이니까요.
 * 둘 다 없으면 `null` 이고, 템플릿은 그때 아무것도 안 그립니다.
 */
function enabledState(payload, opts) {
  const from = (opts && opts.saved && typeof opts.saved.enabled === 'boolean')
    ? opts.saved
    : payload;
  if (!from || typeof from.enabled !== 'boolean') return null;
  return { value: from.enabled, text: `enabled ${from.enabled}` };
}

/** 이 등록부의 낱말. */
export const CHAIN_RULE_REGISTRY = Object.freeze({
  listKey: 'rules',
  nameKey: 'name',
  cls: 'chain-rule',
  extra: enabledState,
  // C-86 ①. 소유자: 「규칙 등록 영역에 규칙을 추가할 수가 없어」. 서버는 «이미» 새 이름을
  // 받습니다 — 새 규칙은 `enabled: false` 로 «장전»까지만 저장됩니다(위 절 참조).
  addLabel: '규칙 추가',
  // C-86 ②. 칸 이름·종류는 «서버가 실어 준» 스켈레톤에서 나옵니다(S-204). 이 파일도 칸 이름을
  // 적지 않습니다 — `chain_bindings.routing_keys()` 가 유일한 저자입니다.
  formRoot: (payload) => (payload && payload.skeleton && payload.skeleton.root) || null,
  // C-86 ③. 맵퍼 칸의 목록 이름. 값은 화면이 `GET /admin/mappers/list` 에서 받아 넣습니다 —
  // 이 파일은 «이름»만 대고 «목록»은 서버의 등록부입니다.
  choiceList: 'mappers',
  // C-101 ②. 표를 대는 칸들의 목록 이름. 값은 화면이 `GET /tables` 에서 받아 넣습니다 —
  // 그 라우트가 «제품이 아는 표 전부»(`crud.TABLE_CONFIG`)이고, 규칙이 읽고 쓸 수 있는 표가
  // 그 집합입니다. 🔴 실측 2026-09-13: 이 문법의 `hint: 'ref'` 리프가 일곱이고 전부 이
  // 목록을 씁니다 — 칸 이름을 여기 적지 않는 이유가 그것입니다(스켈레톤이 저자입니다).
  refList: 'tables',
  // C-95 ②. 「첫 화면」은 «필수»가 아닙니다 — 다른 물음입니다.
  //
  // 🔴 실측(2026-09-13, `chain_bindings.RULE_ROUTING_REQUIRED`): 이 문법의 required 는
  //    `name`·`trigger_table` «둘»뿐입니다. `target_table` 과 `mapper` 는 «선택»이고, 그 이유가
  //    그 파일 자기 주석에 적혀 있습니다 — 코드에 기본값이 있거나 데코레이터가 댈 수 있습니다.
  //    그래서 이 둘을 「필수」라고 적으면 «거짓»이 되고, required 를 여기 다시 적으면 저자가
  //    둘이 됩니다. 이 목록은 그 둘 중 어느 것도 아닙니다 — 「이것 없이 규칙을 읽을 수 있나」입니다.
  //    ⚠️ 규칙이 «쓰는 표»와 «도는 코드»를 안 보고는 규칙을 못 읽습니다. 그리고 맵퍼가 안 풀리면
  //       저장이 `unresolvable_mapper` 로 거절됩니다 — 첫 화면에서 보이지 않으면 그 거절이
  //       「고급」 뒤에서 옵니다.
  firstScreen: ['target_table', 'mapper'],
  // C-95 ③. 맵퍼를 대는 «두 철자». 로더가 둘 다 읽습니다(`chain_bindings.mapper_cells`) —
  // 하나가 이름 하나, 다른 하나가 module + function 입니다. 화면이 둘을 같이 내놓으면
  // 운영자가 「둘 다 적어야 하나」를 묻게 되고, 실측에서 그 셋이 한 화면에 서 있었습니다.
  // ⚠️ 가려진 철자는 「고급」에 있습니다 — 없애면 오늘 module+function 으로 적힌 규칙을
  //    한 칸짜리로 «바꿀 길»이 사라집니다.
  oneOf: [{ one: ['mapper'], other: ['mapper_module', 'mapper_function'], list: 'mappers' }],
});

/**
 * @param {object|null} payload  `/admin/chain/rules/raw` 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} [opts]
 */
export function chainRuleView(payload, opts = {}) {
  return registryView(payload, opts, CHAIN_RULE_REGISTRY);
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} [deps]
 */
export class ChainRulePanel extends RawRegistryPanel {
  constructor(mount, deps = {}) {
    super(mount, deps, CHAIN_RULE_REGISTRY);
  }
}
