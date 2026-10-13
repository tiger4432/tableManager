// The filters panel (lead 5835e6714 ①): it edits a SYSTEM filter - named, off-screen, like a marking - one control per
// value slot of the active part's data. A part that names the filter in its Data section keeps its rows by it.

import { Panel } from '../rnd_board/panel.js';
import { drawCondition, conditionKey } from './condition_editor.js';

export class FiltersPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.filters = d.filters;
    this.stats = d.stats;
    this.active = d.active;
    this.name = d.name || 'filter:1';
  }

  mount() {
    this._offs = [this.filters.subscribe(this.name, () => this.render()), this.active.subscribe('active', () => this.render()),
      this.stats.subscribe('*', (id) => { if (id === this.active.get('active')) this.render(); })];
    this.render();
  }

  destroy() { for (const off of this._offs || []) off(); super.destroy(); }

  conditions() { return this.filters.get(this.name) || []; }

  /** One slot's condition replaced (or added); a condition that keeps everything again still stands - Reset drops all. */
  put(next) {
    const list = this.conditions().filter((c) => conditionKey(c) !== conditionKey(next));
    this.filters.set(this.name, [...list, next]);
  }

  render() {
    const doc = this.doc;
    const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
    const root = el('aside', 'sf-panel tb-filters');
    const head = el('div', 'sf-panel__h');
    head.append(el('span', '', this.title || 'Filters'));
    const reset = el('button', 'sf-btn', 'Reset');
    reset.type = 'button';
    reset.addEventListener('click', () => this.filters.set(this.name, []));
    head.append(reset);
    root.append(head);
    const stats = this.stats.get(this.active.get('active'));
    const held = new Map(this.conditions().map((c) => [conditionKey(c), c]));
    if (!stats || !stats.slots || !stats.slots.length) root.append(el('div', 'sf-say', 'No values to filter'));
    for (const summary of (stats && stats.slots) || []) {
      const key = conditionKey({ row: summary.row, ...summary.slot });
      root.append(drawCondition(doc, summary, held.get(key) || null, (next) => this.put(next)));
    }
    this.host.replaceChildren(root);
  }
}
