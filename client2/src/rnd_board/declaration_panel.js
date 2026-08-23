// ═══════════════════════════════════════════════════════════════════════════════
// 선언 블록 — 스팟파이어가 차트마다 오른쪽에 다는 그 패널.
//
// 🔴 ONE PART, DECLARED FIELDS. The owner's standing rule: build the template element, then
//    swap the data in. So this part knows nothing about trends, maps, walks or axes -- it
//    renders a LIST OF FIELDS a screen declares, and each field is one of three shapes:
//
//      { label, text }                       a fact, printed
//      { label, writes, options: 'y' }       a CHOICE -- a dropdown that writes into a marking
//      { label, reads }                      a marking, counted live
//
//    A second chart gets a second instance with different fields. Nothing here is edited.
//
// 🔴 THE CHOICE IS A MARKING, exactly as the pills are: choosing writes one id under the
//    declared name, so whoever declared they read that name follows along -- and the part that
//    follows does not know this panel exists.
//
// 🔴 AN OPTION LIST NOBODY SERVED IS NOT AN EMPTY DROPDOWN. It says so, and it says which list
//    is missing, because a dropdown with no options reads as 「고를 게 없다」.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';

export class DeclarationPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    this.fields = Array.isArray(options.fields) ? options.fields.slice() : [];
    // `(key) => Promise<[{id, label}]>` -- injected by the composition root, so this part
    // holds no route and no knowledge of what an option means.
    this.optionsFor = options.optionsFor || null;
    this.lists = Object.create(null);
    this._offs = [];
  }

  mount() {
    super.mount();
    for (const field of this.fields) {
      if (field.reads && this.markings) {
        this._offs.push(this.markings.subscribe(field.reads, () => this.render()));
      }
      if (field.writes && this.markings) {
        this._offs.push(this.markings.subscribe(field.writes, () => this.render()));
      }
      if (field.options && this.optionsFor) {
        Promise.resolve().then(() => this.optionsFor(field.options))
          .then((list) => { this.lists[field.options] = list || []; this.render(); })
          .catch(() => { this.lists[field.options] = []; this.render(); });
      }
    }
    this.render();
  }

  destroy() {
    for (const off of this._offs) off();
    this._offs = [];
    super.destroy();
  }

  render() {
    const doc = this.doc;
    if (!doc || !this.host) return;
    this.host.textContent = '';
    const root = doc.createElement('div');
    root.className = 'rb-decl';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    for (const field of this.fields) root.appendChild(this._field(field));
    this.host.appendChild(root);
  }

  _field(field) {
    const doc = this.doc;
    const row = doc.createElement('div');
    row.className = 'rb-decl-row';
    const key = doc.createElement('div');
    key.className = 'rb-decl-key';
    key.textContent = field.label;
    row.appendChild(key);

    if (field.options) {
      row.appendChild(this._select(field));
      return row;
    }
    const val = doc.createElement('div');
    if (field.reads) {
      const n = this.markings ? this.markings.count(field.reads) : 0;
      val.className = n > 0 ? 'rb-decl-val is-live' : 'rb-decl-val';
      // The name AND its size: 「어느 마킹에 반응하나」 and 「지금 몇 개인가」 are both the answer.
      val.textContent = `${field.reads} · ${n} marked`;
    } else {
      val.className = 'rb-decl-val';
      val.textContent = field.text === undefined || field.text === null ? '—' : String(field.text);
    }
    row.appendChild(val);
    return row;
  }

  _select(field) {
    const doc = this.doc;
    const list = this.lists[field.options];
    if (!list) {
      const wait = doc.createElement('div');
      wait.className = 'rb-decl-val';
      wait.textContent = '읽는 중…';
      return wait;
    }
    if (!list.length) {
      const none = doc.createElement('div');
      none.className = 'rb-decl-val is-absent';
      // Not an empty dropdown: an empty control reads as 「고를 게 없다」 when the truth is that
      // nobody served the list.
      none.textContent = `${field.options} 목록이 안 왔습니다`;
      return none;
    }
    const sel = doc.createElement('select');
    sel.className = 'rb-decl-select';
    const chosen = this._chosen(field);
    for (const opt of list) {
      const o = doc.createElement('option');
      o.setAttribute('value', opt.id);
      o.textContent = opt.label || opt.id;
      if (opt.id === chosen) o.setAttribute('selected', 'selected');
      sel.appendChild(o);
    }
    if (sel.addEventListener) {
      sel.addEventListener('change', (event) => {
        const id = (event && event.target && event.target.value) || sel.value;
        if (!id || !this.markings || !field.writes) return;
        // Replace: a chart plots one axis at a time. Same model as a plain click.
        this.markings.clear(field.writes);
        this.markings.set(field.writes, id, SIGN.CASE);
      });
    }
    return sel;
  }

  _chosen(field) {
    if (!field.writes || !this.markings) return null;
    const entries = this.markings.entries(field.writes);
    return entries.length ? entries[0][0] : null;
  }
}
