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
