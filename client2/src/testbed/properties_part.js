// Visualization properties (reference §3, the mockup's panel): the active part's declaration, edited in place - Data
// (the marking it walks from, its row type, the system filter it uses, its own filter), each slot of its kind, the marking
// it writes. Names are the people's words (mockup fix ④), the store names stay inside.

import { Panel } from '../rnd_board/panel.js';
import { drawCondition, conditionKey, conditionWords } from './condition_editor.js';

export class PropertiesPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.active = d.active;
    this.stats = d.stats;
    this.partOf = d.partOf || (() => null);
    this.entities = d.entities || (() => []);
    this.markingNames = d.markingNames || [];
    this.filterNames = d.filterNames || [];
    this.openPicker = d.openPicker || (() => {});
    this.editing = null;
  }

  mount() {
    this._offs = [this.active.subscribe('active', () => { this.editing = null; this.render(); }),
      this.stats.subscribe('*', (id) => { if (id === this.active.get('active')) this.render(); })];
    this.render();
  }

  destroy() { for (const off of this._offs || []) off(); super.destroy(); }

  render() {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const root = el('aside', 'sf-panel sf-props');
    const head = el('div', 'sf-panel__h');
    head.append(el('span', '', 'Visualization properties'));
    root.append(head);
    const part = this.partOf(this.active.get('active'));
    if (!part || !part.decl || part.decl.part !== 'visual') { root.append(el('div', 'sf-say', 'Click a visualization')); this.host.replaceChildren(root); return; }
    const decl = part.declaration();
    root.append(el('div', 'sf-props__name', part.titleWords()));
    const tabs = el('div', 'sf-props__tabs');
    tabs.append(el('span', 'is-on', 'Configuration'), el('span', '', 'Appearance'));
    root.append(tabs);
    const section = (name) => { const s = el('div', 'sf-props__sec'); s.append(el('div', 'sf-props__h', name)); root.append(s); return s; };
    const select = (label, options, value, onPick) => {
      const line = el('label', 'sf-props__line');
      const s = el('select', 'sf-props__sel');
      for (const [v, words] of options) { const o = el('option', '', words); o.value = v === null ? '' : v; s.append(o); }
      s.value = value === null || value === undefined ? '' : value;
      s.addEventListener('change', () => onPick(s.value === '' ? null : s.value));
      line.append(el('span', 'sf-props__lab', label), s);
      return line;
    };
    // ── Data ──
    const data = section('Data');
    data.append(select('Marking', [[null, 'All'], ...this.markingNames.map((m) => [m.name, m.label])], decl.start && decl.start.marking,
      (v) => part.setDeclaration({ ...decl, start: { ...(decl.start || {}), marking: v } })));
    data.append(select('Route', this.entities().map((e) => [e.type, e.type]), decl.row, (v) => part.setDeclaration({ ...decl, row: v })));
    data.append(select('Filtering', [[null, '(None)'], ...this.filterNames.map((f) => [f.name, f.label])], decl.system,
      (v) => part.setDeclaration({ ...decl, system: v })));
    data.append(el('div', 'sf-props__lab', 'Filter'));
    const stats = this.stats.get(decl.id);
    const totals = new Map(((stats && stats.slots) || []).map((s) => [conditionKey({ row: s.row, ...s.slot }), s]));
    for (const c of decl.filter || []) {
      const line = el('div', 'sf-props__cond');
      line.append(el('span', '', conditionWords(c, (totals.get(conditionKey(c)) || { values: [] }).values.length)));
      const x = el('button', 'sf-props__x', '×');
      x.type = 'button';
      x.setAttribute('aria-label', 'Remove the filter');
      x.addEventListener('click', () => part.setDeclaration({ ...decl, filter: (decl.filter || []).filter((d) => conditionKey(d) !== conditionKey(c)) }));
      line.append(x);
      data.append(line);
    }
    const add = el('button', 'sf-props__add', '+ Add filter');
    add.type = 'button';
    add.addEventListener('click', () => { this.editing = this.editing ? null : 'pick'; this.render(); });
    data.append(add);
    if (this.editing) {
      const slots = (stats && stats.slots) || [];
      if (!slots.length) data.append(el('div', 'sf-say', 'Pick a slot value first'));
      for (const summary of slots) {
        const held = (decl.filter || []).find((c) => conditionKey(c) === conditionKey({ row: summary.row, ...summary.slot })) || null;
        data.append(drawCondition(doc, summary, held, (next) => {
          const rest = (decl.filter || []).filter((c) => conditionKey(c) !== conditionKey(next));
          part.setDeclaration({ ...decl, filter: [...rest, next] });
        }));
      }
    }
    // ── the kind's slots ──
    for (const s of (part.kind && part.kind.slots) || []) {
      const sec = section(s.label);
      sec.append(part.pill(s.key));
    }
    // ── Marking ──
    const marking = section('Marking');
    marking.append(select('Writes', [[null, '(None)'], ...this.markingNames.map((m) => [m.name, m.label])], decl.writes,
      (v) => { part.writes = v; part.setDeclaration({ ...part.declaration(), writes: v }); }));
    marking.append(select('Shows', [[null, '(None)'], ...this.markingNames.map((m) => [m.name, m.label])], decl.reads,
      (v) => part.showMarking(v)));
    this.host.replaceChildren(root);
  }
}
