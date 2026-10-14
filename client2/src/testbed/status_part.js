// The status bar (lead 950448e5a): the active part's counts in Spotfire's bottom band - «N of M rows · K marked rows · C
// columns · source», and for now the filters' drops (lead 5835e6714 «system −a · part −b»; the system filter's start side
// «start −c», lead 10-13; a markings' limit «marking −d», lead 10-13), a cut walk, the rows an expression could not take as
// numbers, the marked rows the filters hide, its walks. A drop is said when one of them is not 0. It reads
// a stats store, so any page whose parts publish there can seat it.

import { Panel } from '../rnd_board/panel.js';
import { unitText } from '../ui_words.js';

const n = (x) => Number(x || 0).toLocaleString('en-US');

/** The bar's words for one part's counts - each a span. */
export function statusWords(s) {
  if (!s) return ['No active visualization'];
  const words = [`${n(s.rows)} of ${n(s.of)} rows`];
  // its walks (owner 10-14): «Rows N · complete» and a slot's «Color by · cached»
  if (s.walks && s.walks.rows) words.push(`Rows ${n(s.of)} · ${s.walks.rows}`);
  for (const v of (s.walks && s.walks.values) || []) words.push(`${v.name} · ${v.state}`);
  if (s.startDropped || s.system || s.part || s.limit) {
    words.push([s.startDropped ? `start −${n(s.startDropped)}` : null, `system −${n(s.system)}`, `part −${n(s.part)}`,
      s.limit ? `marking −${n(s.limit)}` : null].filter(Boolean).join(' · '));
  }
  if (s.cut) words.push('filter over a cut walk');
  if (s.shown) words.push(`${s.shown.rule === 'top' ? 'Top' : 'Bottom'} ${n(s.shown.n)} by ${s.shown.by} · ${n(s.shown.hidden)} not shown`);
  if (s.notNumber) words.push(`${unitText(n(s.notNumber), 'row')} not a number`);
  if (s.notTime) words.push(`${unitText(n(s.notTime), 'row')} not a time`);
  if (s.unknown) words.push(`${unitText(n(s.unknown), 'row')} unknown`);
  words.push(`${unitText(n(s.marked), 'marked row')}${!s.marked && s.heldOnly ? ` - marking holds ${s.heldOnly.join(', ')}; no relation to ${s.source}` : ''}${s.hidden ? ` · hidden ${n(s.hidden)}` : ''}`);
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
    bar.className = 'sf-status';
    for (const words of statusWords(this.stats.get(this.active.get('active')))) {
      const span = doc.createElement('span');
      span.textContent = words;
      bar.append(span);
    }
    this.host.replaceChildren(bar);
  }
}
