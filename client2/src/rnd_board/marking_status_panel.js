// ═══════════════════════════════════════════════════════════════════════════════
// 부품 — 마킹 상태. 스팟파이어의 상태바에 해당합니다.
//
// 🔴 SPOTFIRE ALWAYS SHOWS 「N marked」, and that is not decoration: every other panel on this
//    screen answers a question whose subject is a marking, so a reader who cannot see how many
//    things are marked cannot tell 「아직 안 골랐다」 from 「골랐는데 결과가 없다」.
//
// 🔴 IT READS THE NAMES IT WAS DECLARED WITH. A panel reads ONE name through the base class;
//    this one is about the store itself, so the names it watches are DATA in its declaration --
//    not a list this file keeps, and not every name the store happens to hold.
//
// 🔴 IT WRITES NOTHING. `writes` is null in the declaration and there is no `mark` call here.
// ═══════════════════════════════════════════════════════════════════════════════

import { Panel } from './panel.js';
import { SIGN } from './marking_store.js';

export class MarkingStatusPanel extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const options = deps || {};
    // `[{name, label}]` -- the label is what a reader calls it, the name is what the store knows.
    this.names = Array.isArray(options.names) ? options.names.slice() : [];
    this._offs = [];
  }

  mount() {
    super.mount();
    // Subscribed per declared name, so a count moves the instant anything writes.
    for (const entry of this.names) {
      const name = typeof entry === 'string' ? entry : entry.name;
      if (!name || !this.markings) continue;
      this._offs.push(this.markings.subscribe(name, () => this.render()));
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
    root.className = 'rb-status';

    if (this.title) {
      const cap = doc.createElement('div');
      cap.className = 'rb-part-title';
      cap.textContent = this.title;
      root.appendChild(cap);
    }

    for (const entry of this.names) {
      const name = typeof entry === 'string' ? entry : entry.name;
      const label = (typeof entry === 'string' ? entry : entry.label) || name;
      const counts = this._count(name);
      const el = doc.createElement('div');
      el.className = counts.total > 0 ? 'rb-status-row is-marked' : 'rb-status-row';
      el.setAttribute('data-marking', name);

      const key = doc.createElement('span');
      key.className = 'rb-status-key';
      key.textContent = label;

      const val = doc.createElement('span');
      val.className = counts.total > 0 ? 'rb-status-val' : 'rb-status-val is-empty';
      // 🔴 「0 marked」 IS A REAL STATE AND IT IS SAID, not hidden. An empty marking is why a
      //    marking-limited panel is blank, and a reader has to be able to see that from here.
      val.textContent = `${counts.total} marked`;

      el.append(key, val);
      // Case and control are counted apart: 「봤는데 안 났다」 is not a weaker case.
      if (counts.control > 0) {
        const ctrl = doc.createElement('span');
        ctrl.className = 'rb-status-control';
        ctrl.textContent = `컨트롤 ${counts.control}`;
        el.appendChild(ctrl);
      }
      root.appendChild(el);
    }

    this.host.appendChild(root);
  }

  _count(name) {
    if (!this.markings || !name) return { total: 0, control: 0 };
    let control = 0;
    for (const [, sign] of this.markings.entries(name)) {
      if (sign === SIGN.CONTROL) control += 1;
    }
    return { total: this.markings.count(name), control };
  }
}
