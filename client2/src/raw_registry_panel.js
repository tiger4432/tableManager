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

/**
 * 한 등록부의 «선언». 도메인 낱말은 «전부» 여기로 들어옵니다.
 *
 * @typedef {object} RegistrySpec
 * @property {string} listKey   응답에서 «이름 목록»이 실린 칸  (예: 'tables' · 'rules')
 * @property {string} nameKey   응답과 저장이 «고른 하나»를 부르는 이름 (예: 'table' · 'name')
 * @property {string} cls       CSS 클래스 접두 (예: 'table-config' · 'chain-rule')
 * @property {(payload:object)=>object|null} [extra]  이 등록부에만 있는 값 (예: enabled)
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
    const view = registryView(payload, opts, spec);
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
    picker.className = `${spec.cls}-picker`;
    picker.setAttribute('data-picker', spec.nameKey);
    for (const name of view.names) {
      const o = doc.createElement('option');
      o.value = name;
      o.textContent = name;
      if (name === view.name) o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    }
    if (picker.addEventListener && this.onOpen) {
      picker.addEventListener('change', (e) => this.onOpen(e?.target?.value || ''));
    }
    this.root.appendChild(picker);

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

    const area = doc.createElement('textarea');
    area.className = `${spec.cls}-raw`;
    area.setAttribute('data-raw', spec.nameKey);
    area.value = view.raw;
    area.textContent = view.raw;
    this.root.appendChild(area);

    const controls = doc.createElement('div');
    controls.className = `${spec.cls}-controls`;
    const save = doc.createElement('button');
    save.className = `glass-btn btn-primary ${spec.cls}-save`;
    save.setAttribute('data-action', `save-${spec.cls}`);
    save.textContent = 'Save';
    if (save.addEventListener && this.onSave) {
      save.addEventListener('click', () => this.onSave({
        [spec.nameKey]: view.name, base: view.base, raw: area.value,
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
