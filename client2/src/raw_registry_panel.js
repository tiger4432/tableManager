// RAW REGISTRY — 「선언 하나를 제품 «안»에서 등록한다」의 «근원 템플릿»입니다.
//
// 🔴 왜 템플릿인가: 표 등록이 첫째였고 체인 규칙이 «둘째»입니다. 상설 —
//    「같은 종류가 «둘째»로 필요해지면 두 번째를 손으로 그리지 않는다. 첫째를 템플릿으로
//     올리고 «둘 다 선언»으로 만든다」(소유자 2026-08-24). 그래서 이 파일에는 도메인
//    낱말이 «하나도» 없고, 표·규칙은 각자 `spec` 한 덩이입니다.
//
// ═══ 이 파일이 지키는 다섯 ═══════════════════════════════════════════════════════════
//
// ① 편집 단위는 «하나»입니다. 파일 전체를 쓰기 단위로 삼으면 모든 저장이 «남의 등록»을
//    다시 쓰는 일이 됩니다 — 서버 둘이 각자 그 이유를 자기 주석에 적어 뒀습니다.
//
// ② `base` 지문을 «되돌려 보냅니다». 둘이 같은 파일을 열면 둘째가 첫째를 조용히 지웁니다.
//    서버가 `stale_base` 로 거절하고, 그건 «실패가 아니라» 「다시 열어라」입니다.
//
// ③ 거절은 «서버의 낱말»로 그립니다 — code · path · message. 문구를 «하나도» 짓지 않습니다.
//
// ④ 없는 것은 «—» 입니다. 철자는 `absent.js` 하나뿐입니다.
//
// ⑤ 🔴 «상태»는 값으로 그립니다. 저장이 「장전」까지인지 「발사」까지인지는 서버가
//    «값»으로 말하고, 이 파일은 그 값을 «보여»만 줍니다 — 문장을 짓지 않습니다.
//    (소유자 상설 2026-09-04: 「ui에 설명 문구 주저리주저리 금지」)
//
// ⛔ 삭제는 없습니다. 얕은 병합이 남의 등록을 지키는 장치이고, 지우는 것은 반경이 다릅니다.

import { ABSENT, countText } from './absent.js';
import { renderSkeletonForm } from './ontology_explorer_view.js';
import { emptyOf } from './ontology_skeleton.js';
import { writeShapeAtPath } from './ontology_path.js';

/**
 * 고르개가 «새 이름을 짓는 중»일 때 입는 말. 🔴 철자가 «하나»입니다 — 그리는 쪽과 비교하는
 * 쪽이 각자 적으면 둘이 갈라지고, 갈라진 날 고르개가 새 규칙을 «기존 이름처럼» 열려 합니다.
 */
export const NEW_NAME = '(새 규칙)';

/**
 * 아직 «아무것도 안 골랐을» 때 고르개가 입는 말.
 *
 * 🔴 이 자리는 처음 열 때마다 생깁니다 — 절이 이름 «없이» 한 번 읽으므로 응답에 이름이 없고,
 *    고르개는 브라우저 기본대로 «첫 항목»을 보여 줍니다. 그러면 화면이 「이 규칙을 보고 있다」고
 *    말하면서 칸은 비어 있습니다. 그건 거짓 상태이고, 운영자는 「왜 안 채워지나」로 헤맵니다.
 * ⚠️ 글자는 걷기 화면의 고르개와 «같은 말»입니다 — 같은 사실(아직 안 고름)에 두 낱말을 쓰면
 *    같은 제품이 두 목소리로 말합니다.
 */
export const PICK_NAME = '— 고르십시오 —';

/**
 * 한 등록부의 «선언». 도메인 낱말은 «전부» 여기로 들어옵니다.
 *
 * @typedef {object} RegistrySpec
 * @property {string} listKey   응답에서 «이름 목록»이 실린 칸  (예: 'tables' · 'rules')
 * @property {string} nameKey   응답과 저장이 «고른 하나»를 부르는 이름 (예: 'table' · 'name')
 * @property {string} cls       CSS 클래스 접두 (예: 'table-config' · 'chain-rule')
 * @property {(payload:object)=>object|null} [extra]  이 등록부에만 있는 값 (예: enabled)
 * @property {string} [addLabel]  «새 이름»을 만드는 컨트롤의 말 (예: '규칙 추가').
 *   🔴 값입니다. 없으면 그 등록부에는 컨트롤이 «안 그려집니다» — 서버가 새 이름을 안 받는
 *      등록부에 버튼을 그리면 그 버튼은 거절을 만들러 가는 길입니다. 오늘 둘 다 받습니다
 *      (실측: `save_chain_rule_raw` 는 새 이름을 «꺼진 채로» 적고,
 *       `save_table_config_raw` 는 얕은 병합이라 새 키를 만듭니다).
 * @property {string[]} [firstScreen]  「필수」는 아니지만 «첫 화면»에 서는 칸.
 *   🔴 「required」와 «다른 물음»입니다. required 는 「없으면 거절되나」이고 스켈레톤이 답합니다
 *      (실측 2026-09-13: 체인 규칙의 required 는 `name`·`trigger_table` «둘»). 이것은 「이것
 *      없이 규칙을 읽을 수 있나」이고 그 답은 «등록부»의 것입니다. 두 물음을 한 목록으로 접으면
 *      로더가 셋째를 요구하는 날 이 화면이 모릅니다.
 *   ⚠️ 값이 있는 칸은 이 목록과 무관하게 첫 화면입니다 — 접기가 값을 숨기면 지운 것처럼 읽힙니다.
 * @property {{one:string[], other:string[], list?:string}[]} [oneOf]  한 사실의 «두 철자».
 *   🔴 둘을 «같이» 보이면 화면이 「둘 다 적어야 하나」를 묻게 만듭니다. 문서가 든 철자가 이기고,
 *      아무것도 안 들었으면 `list` 가 답합니다 — «빈 목록»은 읽어서 안 사실(고를 것이 없음)이라
 *      다른 철자가 서고, «못 읽음»은 모르는 것이라 기본 철자가 자기 상태를 그립니다(세 상태).
 *   ⚠️ 가려진 철자는 «사라지지 않습니다» — 「고급」으로 갑니다. 없애면 철자를 바꿀 길이 없어집니다.
 * @property {string} [choiceList]  이 등록부의 «닫힌 목록» 이름 (예: 'mappers').
 *   🔴 칸 «이름»이 아닙니다. 스켈레톤이 `list` 로 이름을 대면 그 이름이 이기고, 안 대면 이
 *      등록부의 목록이 쓰입니다. 오늘 체인 스켈레톤은 `mapper` 를 `hint: 'choice'` 로만 내고
 *      «어느 목록인지 말하지 않습니다»(실측 `chain_bindings.skeleton()`), 그래서 이 한 줄이
 *      없으면 화면이 「선택지 없음」이라고 «거짓»을 말합니다 — 묻지도 않은 목록에 대해.
 *   ⚠️ 다리입니다. 서버가 그 리프에 `"list": "mappers"` 를 실으면 이 줄은 «지워집니다».
 * @property {(payload:object)=>object|null} [formRoot]  서버가 실어 준 «스켈레톤의 뿌리».
 *   🔴 칸 이름·종류는 «전부» 이 노드에서 나옵니다. 이 파일도, 등록부 선언도 칸 이름을
 *      한 글자도 적지 않습니다 — 적는 순간 서버가 키를 하나 더해도 화면이 모릅니다.
 *      응답에 스켈레톤이 없으면 `null` 이고, 그때 화면은 «오늘 그대로»(원문 편집기)입니다.
 */

/**
 * `payload` -> 그릴 것. 순수하고 총체적입니다.
 *
 * @param {object|null} payload  GET 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} opts
 * @param {RegistrySpec} spec
 */
export function registryView(payload, opts, spec) {
  const refusal = opts.refusal && typeof opts.refusal === 'object'
    ? Object.freeze({
      code: String(opts.refusal.code == null ? '' : opts.refusal.code),
      path: String(opts.refusal.path == null ? '' : opts.refusal.path),
      message: String(opts.refusal.message == null ? '' : opts.refusal.message),
    })
    : null;
  const empty = Object.freeze({
    available: false, reason: '', names: Object.freeze([]), count: ABSENT,
    name: '', raw: '', base: '', configPath: '', refusal, saved: null, extra: null,
  });
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({ ...empty, reason: opts.unavailable || '응답을 읽지 못했습니다.' });
  }
  // 🔴 파일을 못 읽은 것은 「등록이 없다」가 «아닙니다». 서버가 `error` 로 그 둘을 갈라 줍니다.
  if (payload.error) {
    return Object.freeze({ ...empty, reason: String(payload.error),
                           configPath: String(payload.config_path || '') });
  }
  const list = Array.isArray(payload[spec.listKey]) ? payload[spec.listKey].map(String) : [];
  return Object.freeze({
    available: true,
    reason: '',
    names: Object.freeze(list),
    count: countText(list.length),
    name: String(payload[spec.nameKey] == null ? '' : payload[spec.nameKey]),
    // `raw` 는 서버가 만든 문자열입니다 — 화면이 다시 직렬화하지 않습니다.
    raw: typeof payload.raw === 'string' ? payload.raw : '',
    base: String(payload.base == null ? '' : payload.base),
    configPath: String(payload.config_path || ''),
    refusal,
    // ⑤ 등록부마다 «자기 상태»가 있을 수 있습니다. 없으면 null 이고, 그리는 것도 없습니다.
    extra: spec.extra ? (spec.extra(payload, opts) || null) : null,
    saved: opts.saved && typeof opts.saved === 'object'
      ? Object.freeze({ name: String(opts.saved[spec.nameKey] || ''),
                        count: countText(opts.saved[spec.listKey]),
                        backup: String(opts.saved.backup || '') })
      : null,
  });
}

/**
 * 스켈레톤 폼이 필요로 하는 «맥락». 탐색기의 읽기 트리가 이미 하는 것과 같은 모양으로,
 * 계획(plan)에 속한 것은 «전부» 비워 둡니다 — 이 화면에는 계획이 없고, `planRow` 가 null 을
 * 내면 모든 리프가 «스켈레톤이 그리는» 컨트롤로 갑니다. 그것이 이 화면이 원하는 전부입니다.
 *
 * 🔴 도메인 낱말 «0». `lists` 는 등록부가 넘겨 준 «닫힌 목록»이고, 어느 칸이 그것을 쓰는지는
 *    스켈레톤의 `list` 가 말합니다 — 이 파일이 고르지 않습니다.
 */
function formContext(skeleton, lists, choiceList) {
  const defs = (skeleton && skeleton.defs) || {};
  return {
    schema: lists || {},
    readOnly: false,
    planRow: () => null,
    planLoaded: true,
    plannedMembers: () => [],
    covering: () => null,
    deref: (node) => {
      const shape = node && node.use ? defs[node.use] : node;
      // 🔴 어느 «칸»인지 묻지 않습니다 — 「목록에서 고르는 칸인데 목록 이름이 없다」만 봅니다.
      //    스켈레톤이 이름을 대면 그것이 이깁니다.
      if (shape && shape.kind === 'leaf' && shape.hint === 'choice' && !shape.list && choiceList) {
        return { ...shape, list: choiceList };
      }
      return shape;
    },
    declared: () => [],
    rolesNear: () => [],
    usedElsewhere: () => [],
    renderRow: () => null,
    suggest: (row) => row,
    hot: [],
    expanded: {},
    absolute: (at) => at,
  };
}

/**
 * 서버가 거절한 «칸»에 표시를 답니다. 주소는 서버의 것이고(`rules.<이름>.<칸>`), 접두는
 * 등록부의 «선언된 낱말»로 벗깁니다 — 이 파일은 'rules' 도 'mapper' 도 적지 않습니다.
 *
 * 🔴 «코드»만 답니다. 서버의 문장은 아래 거절 상자가 그대로 들고 있고, 같은 문장을 두 자리에
 *    그리면 한 사실이 두 번 읽힙니다. 주소가 뿌리(칸이 없음)이면 아무 칸도 안 짚습니다.
 */
/** 그 요소의 «직계» 자식 중 그 클래스를 가진 첫 번째. 후손으로 내려가지 않습니다 —
 *  가지 밑의 손자 줄을 집으면 거절이 «다른 칸»에 붙습니다. */
function firstChildOf(el, cls) {
  const kids = el && el.childNodes ? el.childNodes : [];
  for (const kid of kids) {
    const name = kid && typeof kid.className === 'string' ? kid.className : '';
    if (name.split(' ').indexOf(cls) !== -1) return kid;
  }
  return null;
}

function markRefusedField(box, view, spec) {
  const refusal = view.refusal;
  if (!refusal || !refusal.path || !box.querySelector) return null;
  const prefix = `${spec.listKey}.${view.name}.`;
  if (!refusal.path.startsWith(prefix)) return null;
  // 접두를 뗀 나머지가 칸의 주소입니다. 빈 문자열을 «먼저 거르는 갈래»는 두지 않습니다 —
  // 실측(변이 하나): 그 갈래를 지워도 답이 안 바뀝니다. 서버는 규칙 전체를 `rules.<이름>`
  // 으로 부르고 그건 위 접두(점까지)로 «이미» 걸러지며, 남는다 해도 빈 주소를 가진 칸이 없습니다.
  const at = refusal.path.slice(prefix.length);
  const node = box.querySelector(`[data-path="${at}"]`);
  if (!node || !node.ownerDocument) return null;
  const tag = node.ownerDocument.createElement('i');
  tag.className = `${spec.cls}-field-refusal`;
  tag.setAttribute('data-refused', at);
  tag.textContent = refusal.code || '';
  // 🔴 그 칸의 «값 열»에 답니다. `[data-path]` 는 칸의 «상자»라서 거기 붙이면 코드가 줄
  //    «아래» 한 줄로 떨어지고, 줄이 세 열짜리 격자가 된 뒤로는 그것이 줄의 결을 끊습니다.
  //    ⚠️ 상태 열(필수·선택이 사는 곳)에 먼저 넣어 봤고 «재서» 물렸습니다 — 그 열은 92px
  //       고정이라 `unresolvable_mapper` 가 카드 밖으로 넘쳤습니다. 값 열은 1fr 이고,
  //       거기 붙으면 코드가 «그 입력 바로 아래»에 서서 어느 칸의 답인지가 자리로 보입니다.
  //    열을 못 찾으면 종전대로 상자에 답니다.
  // ⚠️ `:scope` 를 안 씁니다 — 하니스의 DOM 스텁이 못 읽는 선택자는 «조용히» 빗나갑니다.
  const own = firstChildOf(node, 'oe-node-row');
  const slot = own ? firstChildOf(own, 'oe-node-value') : null;
  (slot || node).appendChild(tag);
  return tag;
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} deps
 * @param {RegistrySpec} spec
 */
export class RawRegistryPanel {
  constructor(mount, deps, spec) {
    if (!mount) throw new Error('RawRegistryPanel needs a mount element');
    if (!spec || !spec.listKey || !spec.nameKey || !spec.cls) {
      throw new Error('RawRegistryPanel needs a spec {listKey, nameKey, cls}');
    }
    this.mount = mount;
    this.spec = spec;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('RawRegistryPanel needs a document (deps.doc or mount.ownerDocument)');
    this.onOpen = deps.onOpen || null;
    this.onSave = deps.onSave || null;
    // 🔴 «새 이름»을 짓는 중인가. 패널의 상태이지 서버의 상태가 아니라서 여기 삽니다 —
    //    서버는 「이 이름이 파일에 있었나」만 알고, 그 답은 저장할 때 나옵니다.
    this.newMode = false;
    // 🔴 접힘은 «사람이 둔 자리»입니다 — 응답의 성질이 아니라서 여기 삽니다. 다시 그릴 때
    //    이 둘이 그대로라야 편집 한 번이 화면을 접어 버리지 않습니다.
    this.moreOpen = false;
    this.rawOpen = false;
    // 닫힌 목록(예: 맵퍼 등록부). 스켈레톤의 `list` 이름을 키로 하는 «값»이고, 이 파일은
    // 그 이름을 짓지 않습니다. 화면이 넣어 줍니다.
    //
    // 🔴 비어 있는 것이 «세 번째 상태»입니다. `closedListChoice` 는 목록을 «못 읽은» 것과
    //    「선택지가 없다」를 다른 픽셀로 그립니다 — 오늘 맵퍼 등록부를 내는 라우트가 없어서
    //    이 칸은 «못 읽음»으로 섭니다. 「없음」으로 그리면 안 물어본 것을 답으로 만듭니다.
    this.lists = deps.lists || {};
    this.root = this.doc.createElement('div');
    this.root.className = `${spec.cls}-panel`;
    this.mount.appendChild(this.root);
  }

  /**
   * 닫힌 목록을 넣습니다. 응답이 «패널을 만든 뒤»에 오기 때문에 생성자만으로는 부족합니다.
   *
   * 🔴 «안 넣는 것»과 «빈 목록을 넣는 것»은 다른 답입니다. 안 넣으면 그 칸은 「못 읽음」이고,
   *    빈 배열을 넣으면 「선택지 없음」입니다 — 등록된 맵퍼가 하나도 없는 것은 «읽어서 안» 사실이고
   *    그건 값입니다.
   */
  setLists(lists) {
    this.lists = lists || {};
  }

  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
  }

  /**
   * 첫 화면과 「고급」을 가르는 «자리 하나». 순수 함수라 하니스가 그대로 채점합니다.
   *
   * 🔴 「필수」는 «스켈레톤이» 말합니다. 실측(2026-09-13, `chain_bindings.RULE_ROUTING_REQUIRED`):
   *    규칙의 required 는 `name`·`trigger_table` «둘»입니다. 그 둘을 여기 적으면 저자가 둘이
   *    되고, 로더가 셋째를 요구하는 날 이 화면만 모릅니다.
   * 🔴 그 위에 등록부가 «자기 첫 화면»을 선언할 수 있습니다(`firstScreen`). 그건 다른 물음입니다
   *    — 「없으면 거절되나」가 아니라 「이것 없이 규칙을 읽을 수 있나」.
   * ⚠️ 값이 «있는» 칸은 언제나 첫 화면입니다. 접힌 뒤에 값이 숨으면 화면이 그 값을 지운 것처럼
   *    읽힙니다 — 그리고 그것이 접기의 유일한 위험입니다.
   */
  _split(root, held) {
    const spec = this.spec;
    const fields = (root && root.fields) || [];
    const declared = new Set(spec.firstScreen || []);
    const hidden = new Set();
    // ① 한 가지 사실을 «두 철자»로 적는 칸들 — 한 번에 한 철자만 첫 화면에 섭니다.
    for (const group of spec.oneOf || []) {
      const one = group.one || [];
      const other = group.other || [];
      const holds = (keys) => keys.some((key) => held[key] !== undefined && held[key] !== '');
      // 문서가 든 철자가 이깁니다. 안 들었으면 목록이 답합니다 — «빈 목록»은 읽어서 안 사실이고
      // (고를 것이 없음), «못 읽음»은 아직 모르는 것이라 기본 철자가 자기 상태를 그립니다.
      const list = this.lists ? this.lists[group.list] : undefined;
      const useOne = holds(one) ? true
        : holds(other) ? false
          : !(Array.isArray(list) && list.length === 0);
      const won = useOne ? one : other;
      const lost = useOne ? other : one;
      for (const key of lost) hidden.add(key);
      // 🔴 첫 화면의 선언은 «사실»에 붙습니다 — 「이 규칙에 맵퍼 이름이 있어야 한다」이지
      //    「`mapper` 라는 칸이 있어야 한다」가 아닙니다. 선언된 철자가 져서 가려지면 «이긴»
      //    철자가 그 자리를 물려받습니다. 안 그러면 첫 화면에 그 사실을 적을 칸이 «하나도»
      //    없게 되고(실측: 등록부가 빈 새 규칙), 저장이 안 보이는 칸 때문에 거절됩니다.
      if (lost.some((key) => declared.has(key))) for (const key of won) declared.add(key);
    }
    const first = [];
    const rest = [];
    for (const field of fields) {
      const key = field && field.key;
      if (!key) continue;
      const value = held[key];
      const onFirst = value !== undefined
        || (field.required === true && !hidden.has(key))
        || (declared.has(key) && !hidden.has(key));
      (onFirst ? first : rest).push(key);
    }
    return { first, rest };
  }

  /** 접힌 것은 «개수»를 말합니다 — 말 없이 접는 것은 단계를 늘린 삭제입니다. */
  _fold(cls, label, count, open, onToggle) {
    const btn = this.doc.createElement('button');
    btn.className = cls;
    btn.setAttribute('data-action', cls);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    // 🔴 수는 «센 것이 있을 때»만. 원본은 상자 하나라 「· 1」이 아무것도 안 세고, 안 센 수를
    //    적으면 그 수가 «무엇의 수인지» 화면이 거짓을 말합니다.
    btn.textContent = open ? `− ${label}`
      : (count == null ? label : `${label} · ${count}`);
    if (btn.addEventListener) btn.addEventListener('click', onToggle);
    return btn;
  }

  /** @param {object|null} payload @param {object} [opts] */
  render(payload, opts = {}) {
    const spec = this.spec;
    // 「+ 추가」는 서버에 다시 묻지 않습니다 — 목록도 지문도 방금 받은 그대로입니다.
    this._payload = payload;
    this._opts = opts;
    let view = registryView(payload, opts, spec);
    const doc = this.doc;
    this.root.textContent = '';

    if (!view.available) {
      const box = doc.createElement('div');
      box.className = 'empty-state';
      const ic = doc.createElement('div');
      ic.className = 'empty-icon';
      ic.textContent = '⚪';
      box.appendChild(ic);
      box.appendChild(this._line('empty-text', view.reason));
      this.root.appendChild(box);
      return view;
    }

    const root = spec.formRoot ? spec.formRoot(payload) : null;
    // 🔴 «이름을 누가 갖고 있나». 폼이 그 칸을 그리면 이름 입력이 «하나»입니다 — 두 자리에 이름을
    //    받으면 저장이 어느 것을 쓰는지 화면이 말할 수 없습니다(실측 2026-09-13: [규칙 추가] 를
    //    누르면 이름 칸이 폼 «위»에 하나, 폼 «안»에 하나 — 둘이었습니다).
    const formOwnsName = Boolean(root)
      && ((root.fields || []).some((f) => f && f.key === spec.nameKey));
    // 🔴 C-95-b. 「무엇을 편집하고 있나」에 답이 있나. 없으면 편집기를 «안 그립니다» — 빈 편집기는
    //    친절이 아니라 «이름 없는 문서 위의 살아 있는 저장 버튼»입니다.
    const picked = this.newMode || Boolean(view.name);

    // 🔴 저장이 보내는 «글자»입니다. 폼은 이 글자를 고치는 두 번째 «편집기»이지 두 번째 «문서»가
    //    아닙니다 — 그래서 둘이 갈라질 수 없습니다 (criterion ④).
    const area = doc.createElement('textarea');

    // ═══ 머리 한 줄: 고르개 · 추가/취소 · 상태 · 저장 ══════════════════════════════════
    const head = doc.createElement('div');
    head.className = `${spec.cls}-head`;

    const picker = doc.createElement('select');
    // 🔴 탐색기의 고르개 «그 자체»를 씁니다 — 값을 베끼는 대신 규칙에 «닿습니다».
    picker.className = `${spec.cls}-picker oe-field-select`;
    picker.setAttribute('data-picker', spec.nameKey);
    // 새 이름을 짓는 중이면 고르개가 «그것»을 보여 줍니다. 종전에는 이전 규칙의 이름이 그대로
    // 남아, 지금 보고 있는 것이 무엇인지 화면이 «틀리게» 말했습니다.
    if (this.newMode && spec.addLabel) {
      const o = doc.createElement('option');
      o.value = NEW_NAME;
      o.textContent = NEW_NAME;
      o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    } else if (!picked) {
      // C-95-b. 아직 아무것도 안 골랐습니다. 자리표시자가 없으면 고르개가 «첫 이름»을 보여 주고,
      // 그 이름의 내용은 아직 읽은 적이 없습니다.
      const o = doc.createElement('option');
      o.value = PICK_NAME;
      o.textContent = PICK_NAME;
      o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    }
    for (const name of view.names) {
      const o = doc.createElement('option');
      o.value = name;
      o.textContent = name;
      if (!this.newMode && name === view.name) o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    }
    if (picker.addEventListener && this.onOpen) {
      picker.addEventListener('change', (e) => {
        const value = e && e.target ? e.target.value || '' : '';
        if (value === NEW_NAME || value === PICK_NAME) return;
        this.newMode = false;
        this.onOpen(value);
      });
    }
    head.appendChild(picker);

    // ① 새 이름. 등록부가 «말»을 주지 않으면 컨트롤이 없습니다.
    if (spec.addLabel) {
      const addBtn = doc.createElement('button');
      addBtn.className = `admin-btn ${spec.cls}-add`;
      addBtn.setAttribute('data-action', this.newMode ? `cancel-${spec.cls}` : `add-${spec.cls}`);
      addBtn.textContent = this.newMode ? '취소' : `+ ${spec.addLabel}`;
      if (addBtn.addEventListener) {
        addBtn.addEventListener('click', () => {
          // 취소는 «보고 있던 것»으로 돌아갑니다. 다시 묻지 않습니다 — 응답이 그대로 있습니다.
          this.newMode = !this.newMode;
          this.render(this._payload, this._opts);
        });
      }
      head.appendChild(addBtn);
    }

    // 새 이름 칸은 «폼이 이름을 안 가질 때»만. 서버도 빈 이름을 거절하지만(`name_required`),
    // 빈 이름으로 요청을 만드는 것은 길을 하나 더 여는 일입니다.
    let nameInput = null;
    if (this.newMode && !formOwnsName) {
      nameInput = doc.createElement('input');
      nameInput.className = `${spec.cls}-new-name oe-field-input`;
      nameInput.setAttribute('data-new-name', spec.nameKey);
      nameInput.setAttribute('placeholder', spec.nameKey);
      nameInput.value = '';
      head.appendChild(nameInput);
    }

    // ⑤ «값 하나». 거절이 있으면 그 코드가 지금의 상태이고, 아니면 등록부의 상태입니다.
    //    없으면 «아무것도 안 그립니다» — 「안 물어봤다」는 「꺼져 있다」가 아닙니다.
    // 🔴 새 이름을 짓는 중에는 «상태가 없습니다». 응답의 상태는 «방금까지 열려 있던» 이름의
    //    것이고, 그것을 새 이름 옆에 그리면 화면이 아직 없는 규칙에 대해 사실을 주장합니다
    //    (실측 2026-09-13: [규칙 추가] 를 눌러도 `enabled true` 가 그대로 남아 있었습니다).
    const status = view.refusal && view.refusal.code
      ? { text: view.refusal.code, value: 'refused' }
      : (picked && !this.newMode && view.extra && view.extra.text ? view.extra : null);
    if (status) {
      const line = this._line(`${spec.cls}-state`, status.text);
      if (status.value != null) line.setAttribute('data-state', String(status.value));
      head.appendChild(line);
    }

    const save = doc.createElement('button');
    save.className = `admin-btn btn-primary ${spec.cls}-save`;
    save.setAttribute('data-action', `save-${spec.cls}`);
    save.textContent = '저장';
    if (save.addEventListener && this.onSave) {
      // 🔴 저장은 «한 길»입니다. 새 이름이든 고른 이름이든 같은 함수에 같은 모양으로 갑니다.
      //    이름이 어디서 오는지만 다르고, 폼이 이름을 가지면 «문서가» 그 답을 들고 있습니다.
      save.addEventListener('click', () => {
        let named = nameInput ? String(nameInput.value || '').trim() : view.name;
        if (formOwnsName) {
          let held;
          try { held = JSON.parse(area.value || '{}'); } catch (e) { held = null; }
          const fromDoc = held && typeof held === 'object' ? held[spec.nameKey] : undefined;
          if (typeof fromDoc === 'string' && fromDoc.trim()) named = fromDoc.trim();
          else if (this.newMode) named = '';
        }
        this.onSave({ [spec.nameKey]: named, base: view.base, raw: area.value });
      });
    }
    // 🔴 C-95-b. 편집기가 없으면 저장도 없습니다 — 아무것도 안 고른 화면의 저장 버튼은
    //    «이름 없는 빈 문서»를 보내러 가는 길입니다. 서버도 거절하지만, 누를 수 있는 버튼을
    //    두고 거절로 답하는 것은 화면이 답할 수 있는 것을 서버에 미룬 것입니다.
    if (picked || !root) head.appendChild(save);
    this.root.appendChild(head);

    // 🔴 `base` 는 «화면에 보이는 값»이 아니라 저장이 되돌려 보낼 지문입니다.
    this.root.setAttribute('data-base', view.base);
    // ⚠️ 이름을 «선언된 낱말»로도 달아 둡니다 — 저장 경로와 하니스가 그 등록부의 말로 읽습니다.
    this.root.setAttribute(`data-${spec.nameKey}`, this.newMode ? '' : view.name);

    // ═══ 폼 ═══════════════════════════════════════════════════════════════════════════
    // ② 서버가 스켈레톤을 실어 줄 때«만» 그립니다 — 없으면 오늘 그대로입니다.
    if (root && picked) {
      const held = this.newMode
        ? (emptyOf(root, (payload.skeleton || {}).defs) || {})
        : (payload.declaration && typeof payload.declaration === 'object'
          ? payload.declaration : {});
      const box = doc.createElement('div');
      // 🔴 탐색기의 «그 규칙»이 이 마운트에도 닿습니다 (C-95). 시트는 한 벌이고 문이 둘입니다 —
      //    같은 함수가 두 화면에서 다르게 보이던 것이 criterion ④ 의 실물이었습니다.
      box.className = `${spec.cls}-form oe-skeleton-form`;
      const draw = (value) => {
        box.textContent = '';
        const form = renderSkeletonForm(
          formContext(payload.skeleton, this.lists, spec.choiceList), root, '', value, 0,
          this.newMode ? NEW_NAME : view.name);
        if (form) {
          this._partition(form, root, value);
          box.appendChild(form);
        }
        // ④ 서버가 «주소를 대어» 거절하면 그 칸 «옆»에 붙입니다 (S-204 ③).
        markRefusedField(box, view, spec);
      };
      draw(held);
      // 폼이 낸 편집을 문서에 «적습니다». 컨트롤의 낱말(`edit-shape`)은 탐색기의 것입니다.
      if (box.addEventListener) {
        const write = (event) => {
          const el = event && event.target;
          const action = el && el.dataset ? el.dataset.action : '';
          if (action !== 'edit-shape' && action !== 'edit-shape-flag') return;
          const path = el.dataset.value || el.dataset.path || '';
          if (!path) return;
          let held2;
          try { held2 = JSON.parse(area.value || '{}'); } catch (e) { return; }
          const next = action === 'edit-shape-flag' ? Boolean(el.checked) : el.value;
          // 🔴 탐색기와 «같은 함수»입니다. 그리고 새 문서를 «돌려받습니다» — `setAtPath` 는
          //    제자리에서 안 고칩니다(그렇게 읽어 이 줄이 한 번 죽었습니다).
          const updated = writeShapeAtPath(held2, String(path), next);
          if (updated === null) return;
          area.value = JSON.stringify(updated, null, 2);
          draw(updated);
        };
        box.addEventListener('change', write);
      }
      this.root.appendChild(box);
      this._redraw = draw;
      if (this.newMode) view = Object.freeze({ ...view, raw: JSON.stringify(held, null, 2) });
    }

    // 🔴 거절은 «서버의 낱말»로. 이 파일은 문구를 짓지 않습니다.
    //    ⚠️ code 나 path 가 없으면 그 칸을 «안 그립니다» — 빈 칸이 아니라 없는 것입니다.
    if (view.refusal) {
      const box = doc.createElement('div');
      box.className = `${spec.cls}-refusal`;
      box.setAttribute('data-code', view.refusal.code);
      if (view.refusal.code) box.appendChild(this._line(`${spec.cls}-refusal-code`, view.refusal.code));
      if (view.refusal.path) box.appendChild(this._line(`${spec.cls}-refusal-path`, view.refusal.path));
      if (view.refusal.message) box.appendChild(this._line(`${spec.cls}-refusal-why`, view.refusal.message));
      this.root.appendChild(box);
    }

    // ⑥ 원본은 «보조»입니다 — 폼과 같은 무게로 나란히 서면 무엇이 주 편집기인지 화면이
    //    말하지 않습니다. 문서는 그대로 여기 삽니다(접혀도 DOM 에 있습니다).
    area.className = `${spec.cls}-raw`;
    area.setAttribute('data-raw', spec.nameKey);
    area.value = view.raw;
    area.textContent = view.raw;
    if (area.addEventListener && root && picked) {
      // 글자가 문서입니다. 파싱이 안 되면 폼을 «그대로 둡니다» — 반쯤 친 JSON 위에서 폼을
      // 비우면 사람이 치던 것이 사라진 것처럼 보입니다.
      area.addEventListener('input', () => {
        let held2;
        try { held2 = JSON.parse(area.value || '{}'); } catch (e) { return; }
        if (this._redraw) this._redraw(held2);
      });
    }
    if (root && picked) {
      this.root.appendChild(this._fold(`${spec.cls}-raw-fold`, '원본', null, this.rawOpen, () => {
        this.rawOpen = !this.rawOpen;
        this.render(this._payload, this._opts);
      }));
      if (!this.rawOpen) area.hidden = true;
    }
    // 🔴 C-95-b. 아무것도 안 골랐으면 «문서 자체가 없습니다» — 원문 상자도 그 문서의 한 모습이라
    //    같이 빠집니다. 스켈레톤이 없는 등록부(표 등록)는 원문이 «유일한» 편집기라 그대로 섭니다.
    if (picked || !root) this.root.appendChild(area);

    // 저장이 «됐다»는 것도 값으로. 몇 개가 됐고 백업이 어디인지는 서버가 말합니다.
    if (view.saved) {
      this.root.appendChild(this._line(`${spec.cls}-saved`,
        `${view.saved.name} · ${view.saved.count} · ${view.saved.backup}`));
    }
    return view;
  }

  /**
   * 첫 화면과 「고급」. 🔴 그린 것을 «옮길» 뿐 새로 그리지 않습니다 — 배치는 부품 밖의 일이고
   * (상설 「조립식」), 두 번째 폼 코드를 쓰는 순간 이 화면이 선언에서 오는 것을 그만둡니다.
   */
  _partition(form, root, held) {
    const spec = this.spec;
    const doc = this.doc;
    if (!form || !form.querySelector) return;
    const children = form.querySelector('.oe-node-children');
    if (!children) return;
    const { first, rest } = this._split(root, held && typeof held === 'object' ? held : {});
    if (!rest.length) return;
    const keep = new Set(first);
    const later = doc.createElement('div');
    later.className = `oe-node-children ${spec.cls}-advanced`;
    if (!this.moreOpen) later.hidden = true;
    const nodes = children.childNodes ? [...children.childNodes] : [];
    for (const node of nodes) {
      const at = node && node.dataset ? node.dataset.path : '';
      if (at && !keep.has(at)) later.appendChild(node);
    }
    children.appendChild(this._fold(`${spec.cls}-more`, '고급', rest.length, this.moreOpen, () => {
      this.moreOpen = !this.moreOpen;
      this.render(this._payload, this._opts);
    }));
    children.appendChild(later);
  }
}
