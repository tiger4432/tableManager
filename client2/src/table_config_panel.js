// TABLE CONFIG — 표 하나를 «제품 안에서» 등록합니다.
//
// 🔴 이 파일은 이제 «선언»입니다. 모양은 `raw_registry_panel.js` 가 들고 있고, 여기 남은
//    것은 「이 등록부는 무엇으로 불리는가」뿐입니다 — 상설 「근원 템플릿 요소 개발 후
//    데이터 갈아끼우기」. 체인 규칙이 «둘째»가 되면서 첫째를 템플릿으로 올렸습니다.
//
// 읽는 것: `GET /admin/tables/config/raw`. 쓰는 것: `POST` 같은 주소, «표 하나» 단위.
// 규율 넷(편집 단위 · base 지문 · 서버 낱말 그대로 · 없는 것은 —)은 템플릿이 지킵니다.

import { registryView, RawRegistryPanel } from './raw_registry_panel.js';

/**
 * 🔴 「선언은 됐는데 «물리 표»가 없는 것」을 «고르기 전»에 말합니다.
 *
 * 서버가 이것을 `admin/ledger/relations` 에서 «계속» 내고 있었고 (`missing_relations`),
 * 읽는 화면이 «0» 이었습니다. 그걸 고르면 저장이 `unknown_relation` 으로 거절되는데,
 * 거절은 «고른 뒤»에 옵니다 — 고르기 «전»에 말하는 것이 이 줄의 전부입니다.
 *
 * ⚠️ 세 상태입니다: 못 읽음 · 없음 · 있음.
 *    못 읽었으면 「모름」이고, 없으면 «아무것도 안 그립니다» (경고할 것이 없습니다).
 * ⛔ 문장을 쓰지 않습니다 — 상태는 명사, 이름은 `·` 로 (상설 2026-09-05).
 */
function missingRelations(payload, opts) {
  if (opts && opts.relationsUnread) return { value: 'unread', text: '물리 표 · 모름' };
  const names = Array.isArray(opts && opts.missingRelations) ? opts.missingRelations : null;
  if (!names || !names.length) return null;
  return { value: 'missing', text: `물리 표 없음 · ${names.join(' · ')}` };
}

/** 이 등록부의 낱말. 도메인 이름이 사는 자리는 «여기 하나»입니다. */
export const TABLE_REGISTRY = Object.freeze({
  listKey: 'tables',
  nameKey: 'table',
  cls: 'table-config',
  extra: missingRelations,
});

/**
 * @param {object|null} payload  `/admin/tables/config/raw` 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} [opts]
 */
export function tableConfigView(payload, opts = {}) {
  return registryView(payload, opts, TABLE_REGISTRY);
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} [deps]
 */
export class TableConfigPanel extends RawRegistryPanel {
  constructor(mount, deps = {}) {
    super(mount, deps, TABLE_REGISTRY);
  }
}
