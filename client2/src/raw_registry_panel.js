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
  node.appendChild(tag);
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

  _line(cls, text) {
    const el = this.doc.createElement('div');
    el.className = cls;
    el.textContent = text;
    return el;
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

    // 고르는 자리. 이름을 외우게 하지 않습니다 — 서버가 목록을 줍니다.
    const picker = doc.createElement('select');
    // 🔴 탐색기의 고르개 «그 자체»를 씁니다 — 값을 베끼는 대신 규칙에 «닿습니다».
    //    남는 `${spec.cls}-picker` 는 «배치»만 합니다 (폭·여백).
    picker.className = `${spec.cls}-picker oe-field-select`;
    picker.setAttribute('data-picker', spec.nameKey);
    for (const name of view.names) {
      const o = doc.createElement('option');
      o.value = name;
      o.textContent = name;
      if (name === view.name) o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    }
    if (picker.addEventListener && this.onOpen) {
      picker.addEventListener('change', (e) => {
        // 고르는 순간 «새 이름 짓기»에서 나옵니다 — 고른 것과 짓던 것이 같은 화면에 있으면
        // 저장이 둘 중 어느 것인지 화면이 말할 수 없습니다.
        this.newMode = false;
        this.onOpen(e?.target?.value || '');
      });
    }
    this.root.appendChild(picker);

    // ① 새 이름. 등록부가 «말»을 주지 않으면 컨트롤이 없습니다.
    if (spec.addLabel) {
      const addBtn = doc.createElement('button');
      addBtn.className = `admin-btn ${spec.cls}-add`;
      addBtn.setAttribute('data-action', `add-${spec.cls}`);
      addBtn.textContent = `+ ${spec.addLabel}`;
      if (addBtn.addEventListener) {
        addBtn.addEventListener('click', () => {
          this.newMode = true;
          this.render(this._payload, this._opts);
        });
      }
      this.root.appendChild(addBtn);
    }

    // 새 이름 칸. 이름이 «비어 있으면» 저장은 서버까지 안 갑니다 — 서버도 같은 것을
    // 거절하지만(`name_required`), 빈 이름으로 요청을 만드는 것은 길을 하나 더 여는 일입니다.
    let nameInput = null;
    if (this.newMode) {
      nameInput = doc.createElement('input');
      nameInput.className = `${spec.cls}-new-name oe-field-input`;
      nameInput.setAttribute('data-new-name', spec.nameKey);
      nameInput.setAttribute('placeholder', spec.nameKey);
      nameInput.value = '';
      this.root.appendChild(nameInput);
    }

    // 🔴 `base` 는 «화면에 보이는 값»이 아니라 저장이 되돌려 보낼 지문입니다. 눈에 띄게
    //    적지 않되, 저장 경로가 읽을 수 있게 요소에 답니다.
    this.root.setAttribute('data-base', view.base);
    // ⚠️ 이름을 «선언된 낱말»로도 달아 둡니다 (`data-table` · `data-name`).
    //    저장 경로와 하니스가 그 등록부의 말로 읽을 수 있게 하려고입니다.
    this.root.setAttribute(`data-${spec.nameKey}`, view.name);

    // ⑤ 이 등록부만의 상태. 값이 없으면 «아무것도 안 그립니다» — 「안 물어봤다」는
    //    「꺼져 있다」가 아닙니다.
    if (view.extra && view.extra.text) {
      const line = this._line(`${spec.cls}-state`, view.extra.text);
      if (view.extra.value != null) line.setAttribute('data-state', String(view.extra.value));
      this.root.appendChild(line);
    }

    // ② 폼. 서버가 스켈레톤을 실어 줄 때«만» 그립니다 — 없으면 오늘 그대로입니다.
    //
    // 🔴 «문서는 하나»입니다. 저장이 보내는 것은 아래 textarea 의 «글자»이고, 폼은 그 글자를
    //    고치는 두 번째 «편집기»이지 두 번째 «문서»가 아닙니다. 폼에서 한 칸을 고치면 그
    //    글자가 다시 쓰이고, 글자를 직접 고치면 폼이 그것을 다시 읽습니다. 그래서 둘이
    //    갈라질 수 없습니다 (criterion ④).
    const root = spec.formRoot ? spec.formRoot(payload) : null;
    const area = doc.createElement('textarea');
    if (root) {
      const held = this.newMode
        ? (emptyOf(root, (payload.skeleton || {}).defs) || {})
        : (payload.declaration && typeof payload.declaration === 'object'
          ? payload.declaration : {});
      const box = doc.createElement('div');
      box.className = `${spec.cls}-form`;
      const draw = (value) => {
        box.textContent = '';
        const form = renderSkeletonForm(
          formContext(payload.skeleton, this.lists, spec.choiceList), root, '', value, 0,
          this.newMode ? '' : view.name);
        if (form) box.appendChild(form);
        // ④ 서버가 «주소를 대어» 거절하면 그 칸 «옆»에 붙입니다 (S-204 ③).
        //    문장은 안 붙입니다 — 아래 거절 상자가 서버의 문장을 그대로 들고 있습니다.
        markRefusedField(box, view, spec);
      };
      draw(held);
      // 폼이 낸 편집을 문서에 «적습니다». 컨트롤의 낱말(`edit-shape`)은 탐색기의 것이고,
      // 이 파일은 그 낱말을 «읽을» 뿐 새로 짓지 않습니다.
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
          // 🔴 탐색기와 «같은 함수»입니다. 가지를 짓는 규칙과 타입을 지키는 규칙이 두 벌이면
          //    둘이 «오류 없이» 다른 문서를 씁니다. 그리고 새 문서를 «돌려받습니다» —
          //    `setAtPath` 는 제자리에서 안 고칩니다(그렇게 읽어 이 줄이 한 번 죽었습니다).
          const updated = writeShapeAtPath(held2, String(path), next);
          if (updated === null) return;
          area.value = JSON.stringify(updated, null, 2);
          draw(updated);
        };
        box.addEventListener('change', write);
      }
      this.root.appendChild(box);
      if (this.newMode) view = Object.freeze({ ...view, raw: JSON.stringify(held, null, 2) });
    }

    area.className = `${spec.cls}-raw`;
    area.setAttribute('data-raw', spec.nameKey);
    area.value = view.raw;
    area.textContent = view.raw;
    if (area.addEventListener && root) {
      // 글자가 문서입니다. 파싱이 안 되면 폼을 «그대로 둡니다» — 반쯤 친 JSON 위에서 폼을
      // 비우면 사람이 치던 것이 사라진 것처럼 보입니다.
      area.addEventListener('input', () => {
        let held2;
        try { held2 = JSON.parse(area.value || '{}'); } catch (e) { return; }
        const box = this.root.querySelector ? this.root.querySelector(`.${spec.cls}-form`) : null;
        if (!box) return;
        box.textContent = '';
        const form = renderSkeletonForm(
          formContext(payload.skeleton, this.lists, spec.choiceList), root, '', held2, 0, '');
        if (form) box.appendChild(form);
      });
    }
    this.root.appendChild(area);

    const controls = doc.createElement('div');
    controls.className = `${spec.cls}-controls`;
    const save = doc.createElement('button');
    save.className = `admin-btn btn-primary ${spec.cls}-save`;
    save.setAttribute('data-action', `save-${spec.cls}`);
    save.textContent = 'Save';
    if (save.addEventListener && this.onSave) {
      // 🔴 저장은 «한 길»입니다. 새 이름이든 고른 이름이든 같은 함수에 같은 모양으로 갑니다 —
      //    이름이 어디서 왔는지만 다릅니다. 두 번째 저장 경로를 만들면 그 둘이 갈라집니다.
      save.addEventListener('click', () => this.onSave({
        [spec.nameKey]: nameInput ? String(nameInput.value || '').trim() : view.name,
        base: view.base,
        raw: area.value,
      }));
    }
    controls.appendChild(save);
    this.root.appendChild(controls);

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

    // 저장이 «됐다»는 것도 값으로. 몇 개가 됐고 백업이 어디인지는 서버가 말합니다.
    if (view.saved) {
      this.root.appendChild(this._line(`${spec.cls}-saved`,
        `${view.saved.name} · ${view.saved.count} · ${view.saved.backup}`));
    }
    return view;
  }
}
