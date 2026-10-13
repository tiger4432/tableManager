// SHOW ITEMS - the root part's (base set 11, docs/architecture/ROOT_PART_BASE_SET.md): of the marks a kind draws (its
// units; the rows when it makes none) only the top or the bottom N by a value slot (Spotfire's Show/Hide items, «Top»
// and «Bottom»). A visibility rule, not a filter: the marks it hides are not dropped rows - the status says how many. A
// mark with no number on the slot (nothing, several, a text) is not among the N; equal values go by id. Applied before the
// trellis splits the marks, so the N is the picture's, not each panel's.

import { numberOf } from '../walk/reach_table.js';

/** The Top/Bottom by slot every kind holds; the rules (`show.rule`). */
export const SHOW_SLOT = Object.freeze({ key: 'show', label: 'Top/Bottom by' });
export const SHOW_RULES = Object.freeze([['all', 'All'], ['top', 'Top'], ['bottom', 'Bottom']]);

/**
 * The marks shown by the declaration's `show: {rule, n}` and its `show` slot - none, or rule all: every mark.
 * @param {Array<{id, reads: object}>} marks
 * @returns {{kept: Array, hidden: number, rule: string|null, n: number}}  kept in the marks' own order
 */
export function showItems(marks, decl) {
  const show = (decl && decl.show) || {};
  const n = Math.max(0, Math.floor(Number(show.n)));
  const slot = ((decl && decl.encode) || {}).show;
  if (!slot || (show.rule !== 'top' && show.rule !== 'bottom') || !Number.isFinite(n)) return { kept: marks, hidden: 0, rule: null, n: 0 };
  const valueOf = (m) => (m.reads && m.reads.show && m.reads.show.state === 'one' ? numberOf(m.reads.show.value) : null);
  const sign = show.rule === 'top' ? -1 : 1;
  const ranked = marks.map((m) => [m, valueOf(m)]).filter(([, v]) => v !== null)
    .sort(([a, x], [b, y]) => sign * (x - y) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const keep = new Set(ranked.slice(0, n).map(([m]) => m.id));
  const kept = marks.filter((m) => keep.has(m.id));
  return { kept, hidden: marks.length - kept.length, rule: show.rule, n };
}
