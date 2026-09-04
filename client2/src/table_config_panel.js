// TABLE CONFIG — 표 하나를 «제품 안에서» 등록합니다.
//
// 읽는 것: `GET /admin/tables/config/raw`. 쓰는 것: `POST` 같은 주소, «표 하나» 단위.
//
// ═══ 이 파일이 지키는 넷 ═══════════════════════════════════════════════════════════
//
// ① 편집 단위는 «표 하나»입니다. 파일 전체를 쓰기 단위로 삼으면 모든 저장이 «남의 등록»을
//    다시 쓰는 일이 됩니다 — 서버가 그 이유를 자기 주석에 적어 뒀고, 화면도 같은 단위입니다.
//
// ② `base` 지문을 «되돌려 보냅니다». 두 사람이 같은 파일을 열면 둘째가 첫째를 조용히
//    지웁니다. 서버가 `stale_base` 로 거절하고, 그건 «실패가 아니라» 「다시 열어라」입니다.
//
// ③ 거절은 «서버의 낱말»로 그립니다 — code · path · message. 다섯 코드 전부에 서버가
//    문장을 실어 뒀으므로 이 파일은 문구를 «하나도» 짓지 않습니다.
//
// ④ 없는 것은 «—» 입니다. 철자는 `absent.js` 하나뿐입니다.
//
// ⛔ 삭제는 없습니다. 얕은 병합이 남의 등록을 지키는 장치이고, 지우는 것은 반경이 다릅니다.

import { ABSENT, countText } from './absent.js';

/**
 * `payload` -> 그릴 것. 순수하고 총체적입니다.
 *
 * @param {object|null} payload  GET 의 응답, 또는 null
 * @param {{unavailable?: string, refusal?: object, saved?: object}} [opts]
 */
export function tableConfigView(payload, opts = {}) {
  const refusal = opts.refusal && typeof opts.refusal === 'object'
    ? Object.freeze({
      code: String(opts.refusal.code == null ? '' : opts.refusal.code),
      path: String(opts.refusal.path == null ? '' : opts.refusal.path),
      message: String(opts.refusal.message == null ? '' : opts.refusal.message),
    })
    : null;
  const empty = Object.freeze({
    available: false, reason: '', tables: Object.freeze([]), count: ABSENT,
    table: '', raw: '', base: '', configPath: '', refusal, saved: null,
  });
  if (opts.unavailable || !payload || typeof payload !== 'object') {
    return Object.freeze({ ...empty, reason: opts.unavailable || '응답을 읽지 못했습니다.' });
  }
  // 🔴 파일을 못 읽은 것은 「표가 없다」가 «아닙니다». 서버가 `error` 로 그 둘을 갈라 줍니다.
  if (payload.error) {
    return Object.freeze({ ...empty, reason: String(payload.error),
                           configPath: String(payload.config_path || '') });
  }
  const tables = Array.isArray(payload.tables) ? payload.tables.map(String) : [];
  return Object.freeze({
    available: true,
    reason: '',
    tables: Object.freeze(tables),
    count: countText(tables.length),
    table: String(payload.table == null ? '' : payload.table),
    // `raw` 는 서버가 만든 문자열입니다 — 화면이 다시 직렬화하지 않습니다.
    raw: typeof payload.raw === 'string' ? payload.raw : '',
    base: String(payload.base == null ? '' : payload.base),
    configPath: String(payload.config_path || ''),
    refusal,
    saved: opts.saved && typeof opts.saved === 'object'
      ? Object.freeze({ table: String(opts.saved.table || ''),
                        tables: countText(opts.saved.tables),
                        backup: String(opts.saved.backup || '') })
      : null,
  });
}

/**
 * @param {HTMLElement} mount
 * @param {{doc?: Document, onOpen?: Function, onSave?: Function}} [deps]
 */
export class TableConfigPanel {
  constructor(mount, deps = {}) {
    if (!mount) throw new Error('TableConfigPanel needs a mount element');
    this.mount = mount;
    this.doc = deps.doc || mount.ownerDocument;
    if (!this.doc) throw new Error('TableConfigPanel needs a document (deps.doc or mount.ownerDocument)');
    this.onOpen = deps.onOpen || null;
    this.onSave = deps.onSave || null;
    this.root = this.doc.createElement('div');
    this.root.className = 'table-config-panel';
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
    const view = tableConfigView(payload, opts);
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
    picker.className = 'table-config-picker';
    picker.setAttribute('data-picker', 'table');
    for (const name of view.tables) {
      const o = doc.createElement('option');
      o.value = name;
      o.textContent = name;
      if (name === view.table) o.setAttribute('selected', 'selected');
      picker.appendChild(o);
    }
    if (picker.addEventListener && this.onOpen) {
      picker.addEventListener('change', (e) => this.onOpen(e?.target?.value || ''));
    }
    this.root.appendChild(picker);

    // 🔴 `base` 는 «화면에 보이는 값»이 아니라 저장이 되돌려 보낼 지문입니다. 눈에 띄게
    //    적지 않되, 저장 경로가 읽을 수 있게 요소에 답니다.
    this.root.setAttribute('data-base', view.base);
    this.root.setAttribute('data-table', view.table);

    const area = doc.createElement('textarea');
    area.className = 'table-config-raw';
    area.setAttribute('data-raw', 'table');
    area.value = view.raw;
    area.textContent = view.raw;
    this.root.appendChild(area);

    const controls = doc.createElement('div');
    controls.className = 'table-config-controls';
    const save = doc.createElement('button');
    save.className = 'glass-btn btn-primary table-config-save';
    save.setAttribute('data-action', 'save-table-config');
    save.textContent = 'Save';
    if (save.addEventListener && this.onSave) {
      save.addEventListener('click', () => this.onSave({
        table: view.table, base: view.base, raw: area.value,
      }));
    }
    controls.appendChild(save);
    this.root.appendChild(controls);

    // 🔴 거절은 «서버의 낱말»로. 이 파일은 문구를 짓지 않습니다.
    //    ⚠️ code 나 path 가 없으면 그 칸을 «안 그립니다» — 빈 칸이 아니라 없는 것입니다.
    if (view.refusal) {
      const box = doc.createElement('div');
      box.className = 'table-config-refusal';
      box.setAttribute('data-code', view.refusal.code);
      if (view.refusal.code) box.appendChild(this._line('table-config-refusal-code', view.refusal.code));
      if (view.refusal.path) box.appendChild(this._line('table-config-refusal-path', view.refusal.path));
      if (view.refusal.message) box.appendChild(this._line('table-config-refusal-why', view.refusal.message));
      this.root.appendChild(box);
    }

    // 저장이 «됐다»는 것도 값으로. 몇 개가 됐고 백업이 어디인지는 서버가 말합니다.
    if (view.saved) {
      this.root.appendChild(this._line('table-config-saved',
        `${view.saved.table} · ${view.saved.tables} · ${view.saved.backup}`));
    }
    return view;
  }
}
