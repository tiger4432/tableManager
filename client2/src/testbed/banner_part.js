// The left bar (lead 10-13, Spotfire's): its chart button opens the add window beside it - a line a kind of the visual
// part, its picture and its name, in the kinds' order; a pick adds one (the page's `onAdd`) and the window closes, as a
// press outside it or Escape does. Its marking button opens the markings window (Spotfire's Edit › Markings): a line a
// marking - its colour, its name, × - and «+ New marking»; × on a marking parts use names them first. Its relations button
// opens the relations window (Spotfire's Relations): a line a relation - a node type, a predicate, a node type, «Both ways»,
// × - and one picked from the declaration's predicates. The windows hang over the page, not inside the bar.

import { Panel } from '../rnd_board/panel.js';

const SVG = 'http://www.w3.org/2000/svg';
const CHART = 'M4 12h4v9H4zM10 7h4v14h-4zM16 3h4v18h-4z';
const MARKING = 'M3 17l9-9 4 4-9 9H3zM14 6l2-2 4 4-2 2z';
const RELATION = 'M4 5h6v6H4zM14 13h6v6h-6zM10 8h4v2h-2v5h2v2h-4z';

export class BannerPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.kinds = d.kinds || {};
    this.onAdd = d.onAdd || (() => {});
    this.book = d.markingBook || null;
    this.relations = d.relations || null;
    this.predicates = d.predicates || (() => []);
    /** The window open: 'types', 'markings' or null. */
    this.open = null;
    /** A marking whose × asks first (parts use it), or one a docked panel keeps: {name, users, removed}. */
    this.asking = null;
  }

  mount() {
    super.mount();
    const doc = this.doc;
    this._press = (event) => {
      if (!this.open) return;
      const path = typeof event.composedPath === 'function' ? event.composedPath() : [event.target];
      if (!path.includes(this.flyout) && !this.buttons.some((b) => path.includes(b))) this.toggle(null);
    };
    this._key = (event) => { if (event.key === 'Escape') this.toggle(null); };
    doc.addEventListener('mousedown', this._press);
    doc.addEventListener('keydown', this._key);
    if (this.book) this._listOff = this.book.list.subscribe('list', () => { if (this.open === 'markings') this.render(); });
  }

  destroy() {
    if (typeof this.doc.removeEventListener === 'function') {
      this.doc.removeEventListener('mousedown', this._press);
      this.doc.removeEventListener('keydown', this._key);
    }
    if (this._listOff) this._listOff();
    super.destroy();
  }

  toggle(which) {
    this.open = which || null;
    this.asking = null;
    this.render();
  }

  /** A kind's line in the window: picked, the kind added. */
  pick(name) {
    this.toggle(null);
    this.onAdd(name);
  }

  /** × on a marking: one no part names goes; one parts name asks first (`sure`), then goes - or stays when a docked
   *  panel names it, the reply naming it. */
  remove(name, sure = false) {
    const users = this.book.users(name);
    if (users.length && !sure) { this.asking = { name, users, removed: null }; this.render(); return; }
    const reply = this.book.remove(name);
    this.asking = reply.removed ? null : { name, users: reply.users, removed: false };
    this.render();
  }

  render() {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const icon = (paths, cls) => {
      const svg = doc.createElementNS(SVG, 'svg');
      svg.setAttribute('viewBox', '0 0 24 24');
      if (cls) svg.setAttribute('class', cls);
      for (const [d, opacity] of paths) {
        const path = doc.createElementNS(SVG, 'path');
        path.setAttribute('d', d);
        if (opacity !== 1) path.setAttribute('opacity', String(opacity));
        svg.appendChild(path);
      }
      return svg;
    };
    const bar = el('nav', 'sf-banner');
    const button = (which, words, d) => {
      const b = el('button', `sf-banner__b${this.open === which ? ' is-on' : ''}`);
      b.type = 'button';
      b.title = words;
      b.setAttribute('aria-label', words);
      b.setAttribute('aria-expanded', String(this.open === which));
      b.append(icon([[d, 1]]));
      b.addEventListener('click', () => this.toggle(this.open === which ? null : which));
      bar.append(b);
      return b;
    };
    this.buttons = [button('types', 'Visualization types', CHART)];
    if (this.book) this.buttons.push(button('markings', 'Markings', MARKING));
    if (this.relations) this.buttons.push(button('relations', 'Relations', RELATION));
    this.button = this.buttons[0];
    this.flyout = null;
    if (this.open) {
      const fly = el('div', 'sf-flyout');
      fly.setAttribute('role', 'menu');
      if (this.open === 'types') this.drawTypes(fly, el, icon); else if (this.open === 'relations') this.drawRelations(fly, el); else this.drawMarkings(fly, el);
      // Beside the bar, its height: the bar's box on the screen.
      if (this.host.getBoundingClientRect) {
        const box = this.host.getBoundingClientRect();
        Object.assign(fly.style, { left: `${box.right}px`, top: `${box.top}px`, height: `${box.height}px` });
      }
      this.flyout = fly;
      bar.append(fly);
    }
    this.host.replaceChildren(bar);
  }

  drawTypes(fly, el, icon) {
    fly.append(el('div', 'sf-flyout__h', 'Visualization types'));
    for (const [name, kind] of Object.entries(this.kinds)) {
      const it = el('button', 'sf-flyout__it');
      it.type = 'button';
      it.setAttribute('role', 'menuitem');
      const pic = icon((kind.icon && kind.icon.paths) || [], 'sf-flyout__ico');
      if (kind.icon) pic.style.color = `var(--sf-${kind.icon.tone})`;
      it.append(pic, el('span', '', kind.label || name));
      it.addEventListener('click', () => this.pick(name));
      fly.append(it);
    }
  }

  drawMarkings(fly, el) {
    fly.append(el('div', 'sf-flyout__h', 'Markings'));
    for (const m of this.book.list.get('list')) {
      const line = el('div', 'sf-mark');
      line.setAttribute('data-marking', m.name);
      const color = el('input', 'sf-mark__color');
      color.type = 'color';
      color.value = m.color;
      color.setAttribute('aria-label', `${m.label} colour`);
      color.addEventListener('change', () => this.book.edit(m.name, { color: color.value }));
      const label = el('input', 'sf-mark__name');
      label.type = 'text';
      label.value = m.label;
      label.setAttribute('aria-label', 'Marking name');
      label.addEventListener('change', () => {
        const reply = label.value.trim() ? this.book.edit(m.name, { label: label.value.trim() }) : { refused: 'A marking needs a name' };
        if (reply.refused) { label.value = m.label; this.asking = { name: m.name, said: reply.refused }; this.render(); }
      });
      const x = el('button', 'sf-mark__x', '×');
      x.type = 'button';
      x.setAttribute('aria-label', `Delete ${m.label}`);
      x.addEventListener('click', () => this.remove(m.name));
      line.append(color, label, x);
      fly.append(line);
      if (this.asking && this.asking.name === m.name) fly.append(this.askLine(el, m));
    }
    const add = el('button', 'sf-flyout__it sf-mark__add', '+ New marking');
    add.type = 'button';
    add.addEventListener('click', () => this.book.add());
    fly.append(add);
  }

  /** The relations window: each relation a line - its words, «Both ways», × - and the declaration's predicates to add
   *  one from (a subject type, the predicate, an object type). */
  drawRelations(fly, el) {
    fly.append(el('div', 'sf-flyout__h', 'Relations'));
    const list = this.relations.get('list');
    const set = (next) => { this.relations.set('list', next); this.render(); };
    list.forEach((r, k) => {
      const line = el('div', 'sf-mark');
      line.setAttribute('data-relation', `${r.from} ${r.predicate} ${r.to}`);
      const words = el('span', 'sf-mark__words', `${r.from} — ${r.predicate} → ${r.to}`);
      words.setAttribute('data-clip-ok', '');
      line.append(words);
      const both = el('label', 'sf-props__check');
      const box = el('input');
      box.type = 'checkbox';
      box.checked = Boolean(r.both);
      box.addEventListener('change', () => set(list.map((x, i) => (i === k ? { ...x, both: box.checked } : x))));
      both.append(box, el('span', '', 'Both ways'));
      const x = el('button', 'sf-mark__x', '×');
      x.type = 'button';
      x.setAttribute('aria-label', 'Delete the relation');
      x.addEventListener('click', () => set(list.filter((_, i) => i !== k)));
      line.append(both, x);
      fly.append(line);
    });
    const choices = this.predicates().flatMap((p) => ((p.object && p.object.types) || []).flatMap((to) => (p.subjects || []).map((from) => ({ from, predicate: p.name, to }))))
      .filter((c) => !list.some((r) => r.from === c.from && r.predicate === c.predicate && r.to === c.to));
    const pick = el('select', 'sf-props__sel sf-mark__pick');
    pick.setAttribute('aria-label', 'Add a relation');
    const head = el('option', '', '+ Add a relation');
    head.value = '';
    pick.append(head, ...choices.map((c, k) => { const o = el('option', '', `${c.from} — ${c.predicate} → ${c.to}`); o.value = String(k); return o; }));
    pick.addEventListener('change', () => { if (pick.value !== '') set([...list, { ...choices[Number(pick.value)], both: false }]); });
    fly.append(pick);
  }

  /** Under a marking whose × asked: who uses it, and Delete / Cancel - or who keeps it. */
  askLine(el, m) {
    const ask = el('div', 'sf-mark__ask');
    if (this.asking.said) { ask.append(el('span', '', this.asking.said)); return ask; }
    if (this.asking.removed === false) {
      ask.append(el('span', '', `Not deleted - used by ${this.asking.users.join(', ')}`));
      return ask;
    }
    ask.append(el('span', '', `Used by ${this.asking.users.join(', ')}`));
    const yes = el('button', 'sf-btn', 'Delete');
    yes.type = 'button';
    yes.addEventListener('click', () => this.remove(m.name, true));
    const no = el('button', 'sf-btn', 'Cancel');
    no.type = 'button';
    no.addEventListener('click', () => { this.asking = null; this.render(); });
    ask.append(yes, no);
    return ask;
  }
}
