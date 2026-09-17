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
import { emptyOf, shapeAt } from './ontology_skeleton.js';
import { writeShapeAtPath, deleteAtPath, splitBundlePath, getAtPath } from './ontology_path.js';

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
 * 저장 안 된 글자가 있는데 «다른 문서»로 가려 할 때 묻는 말. 🔴 짧게, 그리고 «거짓말 없이» —
 * 초안은 이름별로 보관되므로 이동해도 «사라지지 않습니다». 묻는 이유는 잃어서가 아니라
 * 「지금 보던 것이 저장 안 된 상태」라는 사실을 운영자가 모르고 넘어가지 않게 하려는 것입니다.
 */
export const LEAVE_UNSAVED = '미저장 변경이 있습니다. 이동할까요?';

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
 * @property {{one:string[], other:string[], list?:string,
 *             split?:(value:string)=>object|null, join?:(held:object)=>string}[]} [oneOf]
 *   한 사실의 «두 철자».
 *   🔴 C-101 ③. `split` 이 있으면 그 «고르개 하나»가 두 철자를 다 씁니다 — 고른 것이 다른
 *      철자의 것이면 등록부가 «어느 칸들에 무엇을» 적을지 답하고(`null` 값은 그 칸을 지웁니다),
 *      `join` 은 그 반대로 «문서가 든 것»을 고르개의 값으로 되읽습니다. 철자의 저자는 등록부
 *      하나이고, 이 파일은 그 함수를 부를 뿐입니다.
 *   ⚠️ 없으면 오늘 그대로입니다 — 고르개가 자기 칸 하나에만 적습니다.
 *   🔴 둘을 «같이» 보이면 화면이 「둘 다 적어야 하나」를 묻게 만듭니다. 문서가 든 철자가 이기고,
 *      아무것도 안 들었으면 `list` 가 답합니다 — «빈 목록»은 읽어서 안 사실(고를 것이 없음)이라
 *      다른 철자가 서고, «못 읽음»은 모르는 것이라 기본 철자가 자기 상태를 그립니다(세 상태).
 *   ⚠️ 가려진 철자는 «사라지지 않습니다» — 「고급」으로 갑니다. 없애면 철자를 바꿀 길이 없어집니다.
 * @property {string} [refList]  «참조 칸»(`hint: 'ref'`)이 고르는 목록 이름 (예: 'tables').
 *   🔴 `choiceList` 와 같은 다리입니다 — 스켈레톤이 리프에 `section` 을 대면 그 이름이 이기고,
 *      안 대면 이 등록부의 이름이 쓰입니다. 실측 2026-09-13: 체인 스켈레톤의 ref 리프 «일곱»이
 *      전부 `section` 을 «안 댑니다». 그래서 이 줄이 없으면 탐색기가 제안을 못 찾고 일곱 칸이
 *      평문 입력으로 섭니다 — 표 이름을 손으로 적는 자리가 일곱입니다.
 *   ⚠️ 제안입니다. 컨트롤은 여전히 입력이고, 목록에 없는 이름도 «그대로» 남습니다(서버가 판정).
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
 * @property {(payload:object)=>{text:string,kind?:string}[]} [marks]  머리에 설 «수»들.
 *   🔴 무엇을 세나는 «등록부»가 압니다 — 여기서 세면 이 부품이 한 문법을 알게 되고, 그
 *      순간 다른 등록부와 갈라집니다. 이 부품은 자리만 내줍니다.
 *   ⛔ 빈 배열이면 아무것도 «안 그립니다». 안 센 자리에 0 을 세우지 않습니다 —
 *      「0 이다」와 「안 세어 봤다」는 다른 사실입니다.
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
function formContext(skeleton, lists, spec, held) {
  const defs = (skeleton && skeleton.defs) || {};
  const choiceList = spec.choiceList;
  const refList = spec.refList;
  /** 이름 하나로 목록 하나. 문자열 아닌 멤버는 «제안»이 될 수 없어 빠집니다. */
  const named = (name) => {
    const list = name ? (lists || {})[name] : null;
    return Array.isArray(list) ? list.filter((item) => typeof item === 'string') : [];
  };
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
    // 🔴 C-101 ②. 참조 칸의 제안 목록. 스켈레톤이 «칸마다» 다른 절을 댈 수 있으므로 그 이름이
    //    먼저이고, 안 대면 등록부가 댄 이름입니다 — 위 `deref` 와 «같은 규율»입니다.
    declared: (section) => named(section || refList),
    // 🔴 C-101 ③. 「이 고르개가 지금 무엇을 골랐나」가 «이 칸 하나»로 안 답해질 수 있습니다 —
    //    한 사실을 두 칸으로 적는 문법이 있고, 그때 이 칸은 비어 있는데 규칙은 그것을 «듭니다».
    //    번역은 등록부의 것이고(`join`), 이 자리는 그 함수를 부를 뿐입니다.
    heldChoice: (list, at) => {
      for (const group of spec.oneOf || []) {
        if (typeof group.join !== 'function') continue;
        if ((group.one || [])[0] !== at) continue;
        return group.join(held && typeof held === 'object' ? held : {});
      }
      return '';
    },
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
  // 🔴 «원소» 자식입니다. `childNodes` 는 글자 노드까지 내주고, 그 목록에서 클래스를 찾으면
  //    줄 사이의 공백이 먼저 걸립니다 — 그리고 그 철자는 이 저장소의 DOM 스텁에 없어서
  //    「값 열에 붙인다」가 하니스에서는 «언제나 폴백»으로 재어졌습니다 (실측 2026-09-13).
  const kids = el && el.children ? el.children : [];
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
    // 🔴 [판정 548] 문법을 «바꾸라고 시키는» 자리. 변환은 «서버»가 합니다 — 화면이 변환하면
    //    저자가 둘이 되고, 539 의 왕복 게이트가 «운영자가 안 지나는 길»을 재게 됩니다.
    this.onConvert = deps.onConvert || null;
    // 🔴 «새 이름»을 짓는 중인가. 패널의 상태이지 서버의 상태가 아니라서 여기 삽니다 —
    //    서버는 「이 이름이 파일에 있었나」만 알고, 그 답은 저장할 때 나옵니다.
    this.newMode = false;
    // 🔴 접힘은 «사람이 둔 자리»입니다 — 응답의 성질이 아니라서 여기 삽니다. 다시 그릴 때
    //    이 둘이 그대로라야 편집 한 번이 화면을 접어 버리지 않습니다.
    this.moreOpen = false;
    this.rawOpen = false;
    // 🔴 C-101 ①. 「무엇이 열려 있나」와 「저장 안 된 글자」는 «부품의» 사실입니다. 페이지는
    //    30초마다 목록을 다시 읽는데 그 읽기는 이름을 «안 댑니다» — 응답에 문서가 «없어서»
    //    그대로 그리면 편집기가 사라집니다(소유자 2026-09-13 「지혼자 새로고침되서 초기화」).
    //    ⚠️ 상태를 페이지에 두면 등록부마다 한 벌씩 생기고, 늦게 배우는 쪽만 초기화됩니다.
    this.open = '';      // 열려 있는 문서의 이름 (새 이름이면 NEW_NAME). 아무것도 없으면 ''
    // 「추가」로 갈 때 «보고 있던 문서»를 여기 둡니다. [취소] 가 그것으로 돌아갑니다(응용 Q-71).
    this._backTo = null;
    this.draft = null;   // 저장 안 된 «글자». `null`(고친 적 없음)과 ''(다 지웠음)이 다릅니다
    this.draftOf = '';   // 그 초안이 «어느 문서»의 것인가 — 남의 문서에 입히면 남의 값이 됩니다
    // 닫힌 목록(예: 맵퍼 등록부). 스켈레톤의 `list` 이름을 키로 하는 «값»이고, 이 파일은
    // 그 이름을 짓지 않습니다. 화면이 넣어 줍니다.
    //
    // 🔴 비어 있는 것이 «세 번째 상태»입니다. `closedListChoice` 는 목록을 «못 읽은» 것과
    //    「선택지가 없다」를 다른 픽셀로 그립니다 — 오늘 맵퍼 등록부를 내는 라우트가 없어서
    //    이 칸은 «못 읽음»으로 섭니다. 「없음」으로 그리면 안 물어본 것을 답으로 만듭니다.
    this.lists = deps.lists || {};
    // C-101 ③. 목록 «밖»의 줄들 — 「여기 있지만 고를 수 없는 것」. 값이고, 사유는 서버의 것입니다.
    this.notes = deps.notes || [];
    // 🔴 C-106 ④. 초안은 «새로고침을 넘어» 삽니다 — 오늘까지는 창을 닫으면 사라졌습니다.
    //    자리는 «이 브라우저»뿐이고 서버로 가지 않습니다. 못 쓰는 환경(프라이빗 모드)이면
    //    조용히 «없는 셈»이고, 그때도 메모리 초안은 그대로 돕니다.
    this.store = deps.storage !== undefined ? deps.storage
      : (typeof globalThis !== 'undefined' ? globalThis.localStorage : null);
    // C-106 ②. 「묻는 것」도 밖에서 올 수 있어야 채점됩니다.
    this.ask = deps.confirm
      || ((text) => (typeof globalThis !== 'undefined' && typeof globalThis.confirm === 'function'
        ? globalThis.confirm(text) : true));
    this.root = this.doc.createElement('div');
    this.root.className = `${spec.cls}-panel`;
    this.mount.appendChild(this.root);
    // 🔴 C-106 ①. Ctrl/⌘+S 는 «저장 버튼과 같은 길»입니다 — 두 번째 저장 경로를 만들면 둘이
    //    갈라질 수 있고(criterion ④), 갈라진 쪽은 아무도 안 누르는 동안 조용히 틀립니다.
    //    ⚠️ 뿌리에 답니다(문서가 아니라) — 같은 화면에 패널이 둘이면 각자 자기 것만 저장합니다.
    if (this.root.addEventListener) {
      this.root.addEventListener('keydown', (event) => {
        const key = event && event.key ? String(event.key).toLowerCase() : '';
        if (key !== 's' || !(event.ctrlKey || event.metaKey)) return;
        if (typeof event.preventDefault === 'function') event.preventDefault();
        if (this._saveNow) this._saveNow();
      });
    }
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

  /**
   * 목록 밖의 줄들을 넣습니다. 🔴 «빈 배열»이면 아무것도 안 그립니다 — 오늘 서버가 이 칸들을
   * 안 내므로 줄이 «없는» 것이 맞고, 자리를 비워 그리면 「없음」을 주장하게 됩니다.
   */
  setNotes(notes) {
    this.notes = Array.isArray(notes) ? notes : [];
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
   * ⚠️ 값이 «있는» 칸은 첫 화면입니다 — 접힌 뒤에 값이 숨으면 화면이 그 값을 지운 것처럼
   *    읽히기 때문입니다. 🔴 판정 511 의 «예외 하나»: `oneOf` 에서 «진» 철자는 값이 있어도
   *    첫 화면에 안 섭니다. 그 사실이 사라지는 것이 아니라 «이긴 철자가 같은 사실을 그립니다»
   *    (`join` 이 두 칸을 읽어 고르개에 세웁니다) — 그래서 여기서만 위 위험이 «없습니다».
   *    ⛔ 그 가드가 없으면 한 사실에 칸이 «셋»입니다: 고르개 + module + function.
   *       소유자 실측 2026-09-17 「어드민 체인 규칙 등록은 왜 옛날 모양이냐」가 그 화면입니다.
   *    진 철자는 «사라지지 않습니다» — 「고급」에 있고, 거기서 고쳐 쓸 수 있습니다.
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
      // 🔴 C-101 ③. 목록을 «읽을 수 있으면» 고르개 쪽이 첫 화면입니다 — 그 컨트롤이 이제 두
      //    철자를 «다» 쓰므로(고르면 다른 철자의 칸들이 채워집니다), 문서가 무엇을 들고 있는지로
      //    고르개를 숨기면 「고를 수 있는 유일한 자리」가 「고급」 뒤로 갑니다. 소유자가 본 것이
      //    그것입니다: 두 칸으로 적힌 규칙에서 목록이 «안 보였습니다».
      //    ⚠️ 값을 «든» 칸은 그래도 첫 화면입니다(아래 `value !== undefined`) — 고른 것이 무엇을
      //       적었는지 보여야 하고, 접힘이 값을 숨기면 지운 것처럼 읽힙니다.
      const useOne = (Array.isArray(list) && list.length) ? true
        : holds(one) ? true
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
      const onFirst = !hidden.has(key)
        && (value !== undefined || field.required === true || declared.has(key));
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
    let view = registryView(payload, opts, spec);
    const doc = this.doc;
    // 🔴 C-101 ①. «배경 갱신»은 목록입니다 — 열려 있는 문서를 갈아 끼우지 않습니다.
    //    ⚠️ 「고치는 중」만 지키는 것이 아닙니다: 고른 것이 «풀리는» 것도 초기화입니다.
    //    ⚠️ 못 읽은 배경 읽기도 아무것도 안 바꿉니다 — 이름 없는 읽기는 문서를 «안 실어서»
    //       그 자리에 놓을 것이 없고, 상태를 보이려고 편집 중인 글자를 지우는 것은 값을 잃는
    //       것입니다. 목록이 «그대로»면 고르개도 다시 안 짓습니다(열린 목록을 닫는 일뿐입니다).
    // 🔴 [판정 516 · 응용 Q-73] 「추가」가 시킨 읽기는 «이름이 없어서» 배경으로 표시돼 옵니다.
    //    그래서 그 «한 번»은 지나야 하는데, 지나도 되는 표시는 «그 응답 자신»이 들고 와야 합니다.
    // ⛔ 부품에 깃발을 세워 「다음 렌더」에 소진하면 안 됩니다 — 이름 없는 읽기가 «둘»이고
    //    (버튼 · 30초 자동 갱신) 둘이 같은 모양이라, 타이머 쪽이 먼저 오면 그 깃발을 «먹고»
    //    편집 중인 폼을 갈아 끼웁니다. 그게 이 가드가 막으려던 바로 그 증상입니다
    //    (소유자 2026-09-13 「지혼자 새로고침되서 초기화되는데?」).
    // ✅ 그래서 표시는 `opts.forNew` — 버튼이 «자기 요청에» 실어 보낸 것이고, 타이머의 응답에는
    //    «없습니다». 가드는 그대로이고 예외는 그 요청 하나에만 붙습니다.
    if (opts.background && this.open && !opts.forNew) {
      const names = view.available ? view.names.join('\u0000') : null;
      if (names !== null && names !== this._names) this._options(this._picker, view, this.open);
      return view;
    }
    // 「+ 추가」는 서버에 다시 묻지 않습니다 — 목록도 지문도 방금 받은 그대로입니다.
    this._payload = payload;
    this._opts = opts;
    this.open = '';
    this.root.textContent = '';

    if (!view.available) {
      this._forget();
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
    // 🔴 C-101 ①. 문서의 «이름». 초안은 그 이름을 같이 듭니다.
    const key = this.newMode ? NEW_NAME : String(view.name || '');
    // 🔴 C-95-b. 「무엇을 편집하고 있나」에 답이 있나. 없으면 편집기를 «안 그립니다» — 빈 편집기는
    //    친절이 아니라 «이름 없는 문서 위의 살아 있는 저장 버튼»입니다.
    const picked = this.newMode || Boolean(view.name);
    // 저장이 답하면 그 초안은 «끝»입니다 — 보관까지 지웁니다.
    if (opts.saved) this._forget();
    // ⚠️ 다른 문서가 열리면 «메모리에서만» 내려놓습니다. 보관은 그 이름으로 남아 있고 돌아오면
    //    그대로 섭니다 — 지우면 「이동하면 사라진다」가 되어 ②가 묻는 말이 거짓이 됩니다.
    if (this.draft !== null && this.draftOf !== key) { this.draft = null; this.draftOf = ''; }
    let drafted = this.draft !== null && this.draftOf === key ? this.draft : null;
    // 🔴 C-106 ④. 메모리에 없으면 «보관»을 봅니다(새로고침·탭 닫기를 넘어온 것). 복원된 것은
    //    배지가 «말합니다» — 말없이 되살아난 글자는 운영자가 「서버가 준 것」으로 읽습니다.
    let restored = false;
    if (drafted === null && picked && key) {
      const held = this._stored(key);
      if (held !== null) {
        drafted = held;
        this.draft = held;
        this.draftOf = key;
        restored = true;
      }
    }

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
    this._picker = picker;
    this._options(picker, view, picked ? key : '');
    if (picker.addEventListener && this.onOpen) {
      picker.addEventListener('change', (e) => {
        const value = e && e.target ? e.target.value || '' : '';
        if (value === NEW_NAME || value === PICK_NAME) return;
        // 🔴 C-106 ②. 저장 안 된 것이 있으면 «묻습니다». 타이머는 C-101 이 막았지만 사람의
        //    손은 안 막았고, 고르개 한 번이 화면을 바꾸는 유일한 자리입니다.
        if (drafted !== null && !this.ask(LEAVE_UNSAVED)) {
          // 보던 것으로 «되돌립니다» — 고르개가 가지 않은 곳을 가리키고 있으면 그 자체가 거짓입니다.
          if (this._picker) this._picker.value = this.newMode ? NEW_NAME : view.name;
          return;
        }
        this.newMode = false;
        // 고르개로 «다른 문서»를 열면 취소의 복귀 지점은 뜻을 잃습니다 — 그 자리에 둘 수 없습니다.
        this._backTo = null;
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
          // 🔴 C-106 ④ 의 뒷면: 취소는 «버리는» 것입니다. 새 이름의 초안을 보관에 남기면 다음
          //    [+ 규칙 추가] 가 «지난번에 버린 글자»로 열리고, 배지가 그것을 「복원」이라 말합니다 —
          //    운영자는 버렸는데 화면이 되살립니다.
          if (this.newMode) this._forget();
          this.newMode = !this.newMode;
          // 🔴 [판정 516] 새 규칙으로 «갈 때»는 이름 없이 «다시 받습니다». 종전에는 저장된
          //    payload 를 다시 그렸고(`_again`), 그래서 새 규칙이 «직전에 연 규칙»의 문법으로
          //    열렸습니다 — 서버는 이름 없는 읽기에 「새 규칙의 문법」을 이미 답하는데
          //    화면이 그걸 «안 물으러» 갔습니다.
          // ⛔ 화면이 문법을 «정하지» 않습니다. 저자는 서버 하나입니다(판정 411·516).
          // ⚠️ 취소는 그대로 `_again()` — 「보고 있던 것으로 돌아간다」이지 새로 묻는 것이 아닙니다.
          //    그리고 `onOpen` 이 없는 등록부는 물을 곳이 없으므로 종전대로 다시 그립니다.
          // 🔴 [응용 Q-71] 취소의 복귀 지점을 «곁에» 듭니다. 이름 없는 응답에는 문서가 «없어서»
          //    `_payload` 를 그것으로 갈아끼우면 [취소] 가 «빈 폼»으로 돌아옵니다 — 위 :528 의
          //    「보고 있던 것으로 돌아갑니다」가 그날부터 거짓이 됩니다.
          if (this.newMode && this.onOpen) {
            this._backTo = { payload: this._payload, opts: this._opts };
            this.onOpen('', { forNew: true });
          } else {
            if (this._backTo) { this._payload = this._backTo.payload; this._opts = this._backTo.opts; }
            this._backTo = null;
            this._again();
          }
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
    // 🔴 C-111 (계획 §9.3 ③). «어느 문법인가» 한 낱말. 이행 중에는 두 문법이 다
    //    열려 있어서, 이 낱말이 없으면 같은 화면이 규칙마다 다른 칸을 내미는 이유가
    //    화면 밖에 있습니다. ⚠️ 서버가 안 말했으면 안 그립니다 — 「모름」을 지어내지 않습니다.
    const grammar = picked && typeof spec.grammarOf === 'function'
      ? String(spec.grammarOf(payload) || '') : '';
    if (grammar) {
      const line = this._line(`${spec.cls}-grammar`, grammar);
      line.setAttribute('data-grammar', grammar);
      head.appendChild(line);
    }

    // 🔴 [판정 536 ④ · 538 ②] 이 화면이 «세어서» 말해야 하는 수들. 등록부가 답하고 폼은
    //    자리만 내줍니다 — 위 `grammarOf` 와 «같은 모양»입니다(한 낱말, 값 하나, 문장 없음).
    //    ⚠️ 무엇을 세나는 «등록부»가 압니다. 여기서 세면 이 부품이 체인 문법을 알게 되고,
    //       그 순간 표 설정 등록부와 갈라집니다.
    //    ⛔ 빈 배열이면 아무것도 안 그립니다 — 안 센 자리에 0 을 세우지 않습니다.
    const marks = typeof spec.marks === 'function' ? spec.marks(payload) : null;
    for (const mark of Array.isArray(marks) ? marks : []) {
      if (!mark || !mark.text) continue;
      const line = this._line(`${spec.cls}-mark`, String(mark.text));
      if (mark.kind) line.setAttribute('data-mark', String(mark.kind));
      head.appendChild(line);
    }

    // 🔴 C-106 ①. 「저장 안 됨」은 «값»입니다 — 배지 하나, 문장 없음. C-101 이 세운 가드(타이머가
    //    편집 중인 폼을 안 갈아 끼움)는 «보이지 않았고», 안 보이는 가드는 운영자에게 없는 것과
    //    같습니다. 복원된 초안도 «같은 배지»가 말합니다(값이 다릅니다).
    if (drafted !== null) {
      const mark = this._line(`${spec.cls}-unsaved`, restored ? '미저장 · 복원' : '미저장');
      mark.setAttribute('data-unsaved', restored ? 'restored' : 'edited');
      head.appendChild(mark);
      // 🔴 C-106 ③. 되돌릴 «길»이 있어야 합니다. 오늘까지는 다른 규칙에 들렀다 오는 것이
      //    유일한 길이었고, 그건 우연이지 컨트롤이 아닙니다.
      const undo = doc.createElement('button');
      undo.className = `admin-btn ${spec.cls}-undo`;
      undo.setAttribute('data-action', `undo-${spec.cls}`);
      undo.textContent = '되돌리기';
      if (undo.addEventListener) {
        undo.addEventListener('click', () => { this._forget(); this._again(); });
      }
      head.appendChild(undo);
    }

    // 🔴 [판정 548] 문법을 바꾸는 컨트롤 «하나». 방향은 등록부가 말합니다 — 한 문서가 갈 수
    //    있는 쪽은 «하나»뿐이고, 갈 곳이 없으면(문법을 못 읽으면) 컨트롤이 «없습니다».
    // ⚠️ 「되돌리기」를 따로 두지 않습니다: 되돌리기가 «반대 방향 변환»이라 같은 문입니다
    //    (판정 548 — 왕복이 항등이라 스냅샷도 이력도 필요 없습니다). 버튼을 둘 두면 한 일에
    //    문이 둘이 되고, 그중 하나만 고쳐지는 날이 옵니다.
    // ⛔ 「전부 변환」은 만들지 않습니다 (판정 548: 소유자 파일을 한 번에 바꾸는 길은 없습니다).
    const convert = picked && !this.newMode && typeof spec.convert === 'function'
      ? spec.convert(payload) : null;
    if (convert && convert.to && this.onConvert) {
      const btn = doc.createElement('button');
      btn.className = `admin-btn ${spec.cls}-convert`;
      btn.setAttribute('data-action', `convert-${spec.cls}`);
      btn.setAttribute('data-to', String(convert.to));
      btn.textContent = String(convert.label || convert.to);
      if (btn.addEventListener) {
        btn.addEventListener('click', () => {
          // 서버는 «저장된» 문서를 바꿉니다 — 화면에 저장 안 된 글자가 있으면 그것이
          // 사라지는 것처럼 보입니다. 그래서 «먼저» 묻습니다.
          if (drafted !== null && !this.ask(LEAVE_UNSAVED)) return;
          this.onConvert({ [spec.nameKey]: view.name, to: convert.to });
        });
      }
      head.appendChild(btn);
    }

    const save = doc.createElement('button');
    save.className = `admin-btn btn-primary ${spec.cls}-save`;
    save.setAttribute('data-action', `save-${spec.cls}`);
    save.textContent = '저장';
    // 🔴 저장은 «한 길»입니다. 새 이름이든 고른 이름이든 같은 함수에 같은 모양으로 갑니다.
    //    이름이 어디서 오는지만 다르고, 폼이 이름을 가지면 «문서가» 그 답을 들고 있습니다.
    //    ⚠️ C-106 ①: 단축키도 «이 함수»를 부릅니다. 두 번째 저장 본문을 만들지 않습니다.
    const runSave = () => {
      if (!this.onSave) return;
      let named = nameInput ? String(nameInput.value || '').trim() : view.name;
      if (formOwnsName) {
        let held;
        try { held = JSON.parse(area.value || '{}'); } catch (e) { held = null; }
        const fromDoc = held && typeof held === 'object' ? held[spec.nameKey] : undefined;
        if (typeof fromDoc === 'string' && fromDoc.trim()) named = fromDoc.trim();
        else if (this.newMode) named = '';
      }
      this.onSave({ [spec.nameKey]: named, base: view.base, raw: area.value });
    };
    this._saveNow = (picked || !root) ? runSave : null;
    if (save.addEventListener && this.onSave) save.addEventListener('click', runSave);
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
      let held = this.newMode
        ? (emptyOf(root, (payload.skeleton || {}).defs) || {})
        : (payload.declaration && typeof payload.declaration === 'object'
          ? payload.declaration : {});
      // 초안이 있으면 «그것»이 문서입니다. 반쯤 친 JSON 이면 폼은 종전 문서로 그리고 글자는
      // 초안 그대로 둡니다 — 원문 상자의 `input` 갈래가 이미 그 규율입니다.
      if (drafted !== null) {
        try {
          const typed = JSON.parse(drafted || '{}');
          if (typed && typeof typed === 'object') held = typed;
        } catch (e) { /* noqa */ }
      }
      const box = doc.createElement('div');
      // 🔴 탐색기의 «그 규칙»이 이 마운트에도 닿습니다 (C-95). 시트는 한 벌이고 문이 둘입니다 —
      //    같은 함수가 두 화면에서 다르게 보이던 것이 criterion ④ 의 실물이었습니다.
      box.className = `${spec.cls}-form oe-skeleton-form`;
      const draw = (value) => {
        box.textContent = '';
        const form = renderSkeletonForm(
          formContext(payload.skeleton, this.lists, spec, value),
          root, '', value, 0, this.newMode ? NEW_NAME : view.name);
        if (form) {
          this._partition(form, root, value);
          box.appendChild(form);
        }
        // ④ 서버가 «주소를 대어» 거절하면 그 칸 «옆»에 붙입니다 (S-204 ③).
        markRefusedField(box, view, spec);
        // 🔴 C-106 ⑥. 목록 «밖»의 줄들은 그 목록을 먹이는 칸 «바로 밑»에 섭니다 — 폼 아래에
        //    두면 「내 파일이 왜 안 보이나」의 답이 물음에서 한 화면 떨어져 있습니다.
        this._notesUnder(box);
      };
      draw(held);
      // 폼이 낸 편집을 문서에 «적습니다». 컨트롤의 낱말(`edit-shape`)은 탐색기의 것입니다.
      if (box.addEventListener) {
        const write = (event) => {
          const el = event && event.target;
          const action = el && el.dataset ? el.dataset.action : '';
          if (action !== 'edit-shape' && action !== 'edit-shape-flag'
              && action !== 'edit-shape-branch') return;
          const path = el.dataset.value || el.dataset.path || '';
          if (!path) return;
          let held2;
          try { held2 = JSON.parse(area.value || '{}'); } catch (e) { return; }
          // 🔴 C-111 (판정 407 · 411). «셋 중 하나»를 고르는 것은 칸 하나를 적는 것이
          //    아니라 «짐을 갈아 끼우는» 일입니다: 고른 가지 하나만 남고 나머지는 사라집니다.
          //    둔 것을 남기면(예: `join` 과 `mapper` 를 동시에) 로더가 둘 중 하나를 골라야 하고,
          //    그 고르기는 화면이 안 보여 준 판정입니다.
          // ⚠️ 적혀 있던 `kind` 는 «지키되 고른 것과 맞춥니다» — 운영자가 적은 칸을 지우지도,
          //    없던 칸을 만들지도 않습니다(로더는 `kind` 를 먼저 읽습니다).
          if (action === 'edit-shape-branch') {
            const picked2 = String(el.value || '');
            if (!picked2) return;
            const was = getAtPath(held2, splitBundlePath(String(path)));
            const kept = was && typeof was === 'object' && !Array.isArray(was) ? was : {};
            const next2 = {};
            if (Object.prototype.hasOwnProperty.call(kept, 'kind')) next2.kind = picked2;
            // 🔴 새 가지의 «빈 값»은 스켈레톤이 정합니다(`emptyOf`) — 레코드면 `{}`,
            //    잎이면 빈 문자열입니다. 항상 `{}` 를 적으면 잎 자리에 «문법에 없는 모양»을
            //    적는 것이고, 그 문서는 로더가 거절합니다.
            const oneOfNode = shapeAt(root, splitBundlePath(String(path)),
                                      (payload.skeleton || {}).defs);
            const branchNode = oneOfNode && oneOfNode.branches
              ? oneOfNode.branches[picked2] : null;
            next2[picked2] = kept[picked2] === undefined
              ? (branchNode ? emptyOf(branchNode, (payload.skeleton || {}).defs) : {})
              : kept[picked2];
            const written2 = writeShapeAtPath(held2, String(path), next2);
            if (written2 === null) return;
            area.value = JSON.stringify(written2, null, 2);
            this._keep(key, area.value);
            draw(written2);
            return;
          }
          const next = action === 'edit-shape-flag' ? Boolean(el.checked) : el.value;
          // 🔴 탐색기와 «같은 함수»입니다. 그리고 새 문서를 «돌려받습니다» — `setAtPath` 는
          //    제자리에서 안 고칩니다(그렇게 읽어 이 줄이 한 번 죽었습니다).
          // 🔴 C-101 ③. 한 번 고르기가 문서를 «한 번» 바꿉니다. 고른 것이 다른 철자의 것이면
          //    그 철자의 칸들로 펴지고, 이 칸은 비워집니다 — 두 컨트롤을 오갈 일이 없습니다.
          let updated = held2;
          for (const [at, val] of this._cells(String(path), next, held2)) {
            if (val === null) {
              // 없는 칸을 지우는 것은 «성공»입니다 — 그 자리는 이미 비어 있습니다.
              const gone = deleteAtPath(updated, splitBundlePath(at));
              if (gone !== null) updated = gone;
              continue;
            }
            const written = writeShapeAtPath(updated, at, val);
            if (written === null) return;
            updated = written;
          }
          area.value = JSON.stringify(updated, null, 2);
          this._keep(key, area.value);
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
    // 🔴 초안이 «문서»입니다 — 서버의 글자로 덮는 그 순간이 초기화입니다.
    const text = drafted !== null ? drafted : view.raw;
    area.value = text;
    area.textContent = text;
    if (area.addEventListener && root && picked) {
      // 글자가 문서입니다. 파싱이 안 되면 폼을 «그대로 둡니다» — 반쯤 친 JSON 위에서 폼을
      // 비우면 사람이 치던 것이 사라진 것처럼 보입니다.
      area.addEventListener('input', () => {
        // 🔴 파싱 여부와 «무관하게» 초안입니다. 반쯤 친 JSON 을 안 들고 있으면 다음 그림이
        //    그것을 지우고, 그 그림은 접기 버튼 하나로도 옵니다.
        this._keep(key, area.value);
        let held2;
        try { held2 = JSON.parse(area.value || '{}'); } catch (e) { return; }
        if (this._redraw) this._redraw(held2);
      });
    }
    if (root && picked) {
      this.root.appendChild(this._fold(`${spec.cls}-raw-fold`, '원본', null, this.rawOpen, () => {
        this.rawOpen = !this.rawOpen;
        this._again();
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
    // 🔴 C-101 ①. 「무엇이 열려 있나」를 적습니다 — 배경 갱신이 이것을 읽고 «비켜갑니다».
    this.open = picked ? key : '';
    return view;
  }

  /**
   * 고르개의 «선택지». 🔴 자리가 하나입니다 — 첫 그림과 배경 갱신이 각자 지으면 둘이 갈라지고,
   * 갈라진 날 목록 갱신이 자리표시자를 «되살려» 열려 있는 문서를 안 고른 것처럼 그립니다.
   *
   * @param {object|null} picker  고르개 (없으면 아무것도 안 합니다)
   * @param {object} view  방금 읽은 것
   * @param {string} open  «열려 있는» 문서의 이름. ''이면 아직 아무것도 안 골랐습니다
   */
  _options(picker, view, open) {
    if (!picker) return;
    const doc = this.doc;
    picker.textContent = '';
    const opt = (value, selected) => {
      const o = doc.createElement('option');
      o.value = value;
      o.textContent = value;
      if (selected) o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    };
    // 새 이름을 짓는 중이면 고르개가 «그것»을 보여 줍니다. 종전에는 이전 규칙의 이름이 그대로
    // 남아, 지금 보고 있는 것이 무엇인지 화면이 «틀리게» 말했습니다.
    if (this.newMode && this.spec.addLabel) opt(NEW_NAME, true);
    // C-95-b. 아직 아무것도 안 골랐습니다. 자리표시자가 없으면 고르개가 «첫 이름»을 보여 주고,
    // 그 이름의 내용은 아직 읽은 적이 없습니다.
    else if (!open) opt(PICK_NAME, true);
    for (const name of view.names) opt(name, name === open);
    this._names = view.names.join('\u0000');
  }

  /** 자기 자신을 다시 그립니다 — «사람이 누른» 것이라 배경 갱신이 «아닙니다». 세 자리가 각자
   *  부르던 것을 한 자리로 모았습니다: 그중 하나가 배경 깃발을 그대로 넘기면 접기 버튼이
   *  «아무 일도 안 하는» 버튼이 됩니다 (criterion ④). */
  _again() {
    this.render(this._payload, { ...this._opts, background: false });
  }

  /** 저장 안 된 글자를 «부품이» 듭니다. 이름을 같이 드는 이유는 생성자의 `draftOf` 를 보십시오. */
  _keep(key, text) {
    this.draft = String(text == null ? '' : text);
    this.draftOf = String(key || '');
    // 🔴 C-106 ④. 메모리와 «같은 순간»에 보관합니다 — 나중에 한 번 더 쓰는 자리를 만들면
    //    그 사이에 창이 닫히는 글자가 생기고, 그 창이 정확히 이 기능이 겨냥한 창입니다.
    if (!this.store || !this.draftOf) return;
    try { this.store.setItem(this._slot(this.draftOf), this.draft); } catch (e) { /* noqa */ }
  }

  _forget() {
    const was = this.draftOf;
    this.draft = null;
    this.draftOf = '';
    if (!this.store || !was) return;
    try { this.store.removeItem(this._slot(was)); } catch (e) { /* noqa */ }
  }

  /** 이 등록부의 «이 문서»에 붙는 열쇠. 등록부가 둘이면 열쇠도 둘입니다. */
  _slot(key) {
    return `assy.draft.${this.spec.cls}.${key}`;
  }

  /** 보관된 초안, 또는 `null`. 🔴 못 읽는 환경은 «없는 것»과 같은 답입니다 — 거기서 던지면
   *  초안 기능이 화면 «전체»를 못 그리게 만듭니다. */
  _stored(key) {
    if (!this.store || !key) return null;
    try {
      const held = this.store.getItem(this._slot(key));
      return typeof held === 'string' ? held : null;
    } catch (e) {
      return null;
    }
  }

  /** 닫힌 목록의 «그 항목». 없으면 null — 손으로 친 값은 목록에 없습니다. */
  _member(list, value) {
    const members = list ? (this.lists || {})[list] : null;
    if (!Array.isArray(members)) return null;
    return members.find((m) => m && typeof m === 'object' && m.value === value) || null;
  }

  /**
   * 목록 «밖»의 줄들을 그 목록을 쓰는 칸 밑에 답니다. 어느 칸인지는 «선언»이 말합니다 —
   * 목록을 든 `oneOf` 그룹의 첫 철자가 그 컨트롤입니다. 못 찾으면 폼 끝에 답니다.
   */
  _notesUnder(box) {
    if (!this.notes.length || !box || !box.querySelector) return;
    const group = (this.spec.oneOf || []).find((g) => g && g.list);
    const at = group ? (group.one || [])[0] : '';
    const host = (at && box.querySelector(`[data-path="${at}"]`)) || box;
    const wrap = this.doc.createElement('div');
    wrap.className = `${this.spec.cls}-list-notes`;
    let drawn = 0;
    for (const note of this.notes) {
      if (!note || !note.text) continue;
      const line = this._line(`${this.spec.cls}-list-note`, String(note.text));
      if (note.kind) line.setAttribute('data-note', String(note.kind));
      wrap.appendChild(line);
      drawn += 1;
    }
    // 줄이 하나도 «안 그려졌으면» 상자도 없습니다 — 빈 상자는 여백만 남는 주장입니다.
    if (drawn) host.appendChild(wrap);
  }

  /**
   * 이 컨트롤의 한 번 고르기가 «어느 칸들»에 무엇을 적나. 기본은 그 칸 하나입니다.
   * `null` 값은 「그 칸을 지운다」이고, 무엇이 그렇게 되는지는 «등록부»가 답합니다.
   */
  _cells(path, value, held) {
    let cells = null;
    // 어느 목록에서 온 값인가. 그룹이 자기 목록을 대면 그것이고, 아니면 이 등록부의 «닫힌
    // 목록»입니다 — 그 이름이 곧 `deref` 가 리프에 입혀 주는 목록이기 때문입니다.
    let list = this.spec.choiceList || '';
    for (const group of this.spec.oneOf || []) {
      if ((group.one || [])[0] !== path) continue;
      if (typeof group.split === 'function') {
        const spread = group.split(value);
        if (spread && typeof spread === 'object') cells = Object.entries(spread);
      }
      if (group.list) list = group.list;
      break;
    }
    // 🔴 C-106 ⑤. 고른 항목이 «자기가 무엇을 더 적어야 하는지» 압니다(선언된 파라미터).
    //    ⚠️ 문서에 «없는» 칸만 채웁니다 — 있는 값을 덮으면 고르기가 «지우기»가 됩니다.
    const extra = [];
    const member = this._member(list, value);
    const fill = member && member.fill && typeof member.fill === 'object' ? member.fill : null;
    if (fill) {
      for (const at of Object.keys(fill)) {
        if (getAtPath(held, splitBundlePath(at)) === undefined) extra.push([at, fill[at]]);
      }
    }
    return (cells || [[path, value]]).concat(extra);
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
    // 🔴 같은 이유로 «원소»입니다. 실측 2026-09-13: 이 줄이 `childNodes` 를 읽어 하니스에서
    //    한 줄도 «안 옮겨졌고», 접힘 버튼은 「고급 · 18」이라 세어 놓고 아무것도 안 숨겼습니다.
    //    브라우저에서는 돌던 코드라 화면은 맞았고 — 그래서 조용했습니다.
    const nodes = children.children ? [...children.children] : [];
    for (const node of nodes) {
      const at = node && node.dataset ? node.dataset.path : '';
      if (at && !keep.has(at)) later.appendChild(node);
    }
    children.appendChild(this._fold(`${spec.cls}-more`, '고급', rest.length, this.moreOpen, () => {
      this.moreOpen = !this.moreOpen;
      this._again();
    }));
    children.appendChild(later);
  }
}
