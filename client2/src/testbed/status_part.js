// The status bar (lead 950448e5a): the active part's counts in Spotfire's bottom band - «N of M rows · K marked rows · C
// columns · source», and for now the filters' drops (lead 5835e6714 «system −a · part −b»; the system filter's start side
// «start −c», lead 10-13), a cut walk, the marked rows the filters hide. A drop is said when one of them is not 0. It reads
// a stats store, so any page whose parts publish there can seat it.

import { Panel } from '../rnd_board/panel.js';
import { unitText } from '../ui_words.js';

const n = (x) => Number(x || 0).toLocaleString('en-US');

/** The bar's words for one part's counts - each a span. */
export function statusWords(s) {
  if (!s) return ['No active visualization'];
  const words = [`${n(s.rows)} of ${n(s.of)} rows`];
  if (s.startDropped || s.system || s.part) {
    words.push([s.startDropped ? `start −${n(s.startDropped)}` : null, `system −${n(s.system)}`, `part −${n(s.part)}`].filter(Boolean).join(' · '));
  }
  if (s.cut) words.push('filter over a cut walk');
  words.push(`${unitText(n(s.marked), 'marked row')}${s.hidden ? ` · hidden ${n(s.hidden)}` : ''}`);
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
