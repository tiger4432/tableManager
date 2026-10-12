// The status bar (lead 950448e5a): the active part's counts in Spotfire's bottom band - «N of M rows · K marked · C
// columns · source», and for now the two filters' drops (lead 5835e6714 «system −a · part −b»), a cut walk, the marked
// nodes the filters hide. It reads a stats store, so any page whose parts publish there can seat it.

import { Panel } from '../rnd_board/panel.js';

const n = (x) => Number(x || 0).toLocaleString('en-US');

/** The bar's words for one part's counts - each a span. */
export function statusWords(s) {
  if (!s) return ['No active visualization'];
  const words = [`${n(s.rows)} of ${n(s.of)} rows`];
  if (s.system || s.part) words.push(`system −${n(s.system)} · part −${n(s.part)}`);
  if (s.cut) words.push('filter over a cut walk');
  words.push(`${n(s.marked)} marked${s.hidden ? ` · hidden ${n(s.hidden)}` : ''}`);
  words.push(`${n(s.columns)} columns`);
  if (s.source) words.push(s.source);
  return words;
}

export class StatusPart extends Panel {
  constructor(host, deps) {
    super(host, deps);
    const d = deps || {};
    this.stats = d.stats;
    this.active = d.active;
  }

  mount() {
    this._offs = [this.active.subscribe('active', () => this.render()),
      this.stats.subscribe('*', (id) => { if (id === this.active.get('active')) this.render(); })];
    this.render();
  }

  destroy() { for (const off of this._offs || []) off(); super.destroy(); }

  render() {
    const doc = this.doc;
    const bar = doc.createElement('div');
    bar.className = 'tb-status';
    for (const words of statusWords(this.stats.get(this.active.get('active')))) {
      const span = doc.createElement('span');
      span.textContent = words;
      bar.append(span);
    }
    this.host.replaceChildren(bar);
  }
}
