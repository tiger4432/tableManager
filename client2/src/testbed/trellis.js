// TRELLIS - the root part's (base set 12, docs/architecture/ROOT_PART_BASE_SET.md): the Panel by slot splits the rows by
// its value into panels, each the same picture of its rows (Spotfire's Trellis «Panels»). The split is of ROWS - a row
// with two values stands in both, none in (Empty) - and each panel's marks are made from its own rows, so a Marker by
// hub in a panel is its rows there: its id and conditions carry the panel's value. The kind draws each panel as it
// draws one picture; the root lays the panels out, gives every panel the same axis extents and appends the panel's
// condition to what a press in it marks.

import { categoriesOf, slotWords, EMPTY, categoryCompare } from './slot.js';
import { hubId } from './hubs.js';
import { numberOf } from '../walk/reach_table.js';

/** The Panel by slot every kind holds. */
export const PANEL_SLOT = Object.freeze({ key: 'panel', label: 'Panel by', category: true });

/**
 * The panels by the declaration's Panel by: [{name, rows, where}] in the values' order ((Empty) last); no slot - null.
 * @param {Array<{id, reads: object}>} rows
 */
export function panelsOf(rows, decl) {
  const slot = ((decl && decl.encode) || {}).panel;
  if (!slot) return null;
  const words = slotWords(slot);
  const groups = new Map();
  for (const row of rows) {
    const read = row.reads.panel;
    const values = read && categoriesOf(read).length ? categoriesOf(read).map(String) : [EMPTY];
    for (const v of new Set(values)) { if (!groups.has(v)) groups.set(v, []); groups.get(v).push(row); }
  }
  const names = [...groups.keys()].sort(categoryCompare());
  return names.map((name) => ({ name, rows: groups.get(name), where: [[words, name]] }));
}

/** A panel's marks: a hub its rows in the panel, its id and conditions carrying the panel's (a node, a record as it is). */
export const inPanel = (units, panel, row) => units.map((u) => (u.where
  ? { ...u, where: withPanel(u.where, panel), id: hubId(row, withPanel(u.where, panel)) } : u));

/** Conditions with the panel's appended - once. */
export function withPanel(where, panel) {
  const [[words]] = panel.where;
  return where.some(([w]) => w === words) ? where : [...where, ...panel.where];
}

/** Each slot's extent over every panel's marks - the same axis in every panel; a slot with no number - null. */
export function extentsOf(marks) {
  const out = {};
  for (const m of marks) {
    for (const [key, read] of Object.entries(m.reads || {})) {
      const x = read && read.state === 'one' ? numberOf(read.value) : null;
      if (x === null) continue;
      const e = out[key] || (out[key] = [x, x]);
      e[0] = Math.min(e[0], x);
      e[1] = Math.max(e[1], x);
    }
  }
  return (key) => out[key] || null;
}
