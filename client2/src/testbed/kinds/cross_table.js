// The cross table kind of the visual part (reference §8): a row axis, a column axis, the cell values folded over the
// rows each cell holds, grand totals. A cell - and a row or column head - is a hub of its rows, marked whole.

import { combosOf, slotWords, foldRows, EMPTY } from '../slot.js';
import { colorOfIds } from '../color_by.js';

export const SLOTS = Object.freeze([
  { key: 'rows', label: 'Row axis', category: true },
  { key: 'columns', label: 'Column axis', category: true },
  { key: 'cells', label: 'Cell values', folds: true },
]);
export { EMPTY };
const TOTAL = 'Total';

/** A cell's number as the table says it: thousands grouped, at most three decimals. */
export const cellWords = (v) => (v === null || v === undefined ? '-'
  : typeof v === 'number' ? v.toLocaleString('en-US', { maximumFractionDigits: 3 }) : String(v));

/**
 * @param {Array<{id, reads: object, raw: object}>} rows  `raw.cells` - what the cell slot keeps of the row (slot.js rawOf)
 * @param {{marked: (id) => boolean, declaration?: object}} ctx  the declaration's cell slot: its reduce (none - Count) or its expression
 */
export function crossModel(rows, ctx) {
  const cellSlot = ((ctx.declaration && ctx.declaration.encode) || {}).cells;
  const cells = new Map();
  const keyOf = (r, c) => `${r}\u0000${c}`;
  const rowKeys = new Set();
  const colKeys = new Set();
  // A row with two values on an axis stands in both (lead aca803a7a «counts twice»); none - (Empty).
  for (const { values: [r, c], ids } of combosOf(rows, ['rows', 'columns'])) {
    rowKeys.add(r);
    colKeys.add(c);
    cells.set(keyOf(r, c), { ids });
  }
  const byId = new Map(rows.map((row) => [row.id, row]));
  /** A set of rows folded: the cell slot's values of each row once (a row in two columns counts once in its row's total). */
  const folded = (ids) => {
    const once = [...new Set(ids)];
    if (!rows.some((row) => row.raw && row.raw.cells)) return once.length;
    return foldRows(cellSlot, once.map((id) => byId.get(id).raw.cells));
  };
  const sort = (keys) => [...keys].sort((a, b) => (a === EMPTY) - (b === EMPTY) || (a < b ? -1 : a > b ? 1 : 0));
  const R = sort(rowKeys);
  const C = sort(colKeys);
  const grid = R.map((r) => C.map((c) => {
    const cell = cells.get(keyOf(r, c));
    if (!cell) return { value: null, ids: [], marked: false };
    // A cell in its rows' Color by colour (the root's), when one is declared.
    const color = ctx.colors && ctx.colors.any ? colorOfIds(ctx.colors, cell.ids).fill : null;
    return { value: folded(cell.ids), ids: cell.ids, marked: cell.ids.some(ctx.marked), color };
  }));
  const rowIds = R.map((_, i) => grid[i].flatMap((cell) => cell.ids));
  const colIds = C.map((_, j) => grid.flatMap((line) => line[j].ids));
  return {
    rowKeys: R, colKeys: C, grid,
    rowTotals: rowIds.map(folded), colTotals: colIds.map(folded), total: folded(rows.map((row) => row.id)),
    rowIds, colIds, anyMarked: rows.some((row) => ctx.marked(row.id)),
  };
}

/**
 * Draw a model: the column tray over the table, the row tray beside it, the cell tray under it, the legend; the table
 * scrolls inside its own box (mockup fix ①). A cell, a row head or a column head marks its hub through `ctx.markHub`.
 */
export function render(body, model, ctx) {
  const doc = ctx.doc;
  const el = (tag, cls, text) => { const n = doc.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  body.className = 'sf-part__body tb-cross';
  const top = el('div', 'tb-cross__top');
  top.append(ctx.pill('columns'), ctx.plus('columns'));
  const left = el('div', 'tb-cross__left');
  left.append(ctx.pill('rows', { vertical: true }));
  const wrap = el('div', 'tb-cross__wrap');
  const table = el('table', 'sf-table');
  const head = el('tr');
  head.append(el('th', 'sf-table__corner', ctx.words('rows')));
  const words = { rows: ctx.words('rows'), columns: ctx.words('columns') };
  model.colKeys.forEach((c, j) => {
    const th = el('th', 'sf-table__col', c);
    th.addEventListener('click', (event) => ctx.markHub([[words.columns, c]], model.colIds[j], event));
    head.append(th);
  });
  head.append(el('th', 'sf-table__col sf-table__total', TOTAL));
  table.append(head);
  model.rowKeys.forEach((r, i) => {
    const tr = el('tr');
    const th = el('th', 'sf-table__row', r);
    th.addEventListener('click', (event) => ctx.markHub([[words.rows, r]], model.rowIds[i], event));
    tr.append(th);
    model.grid[i].forEach((cell, j) => {
      const td = el('td', cell.marked ? 'is-marked' : '', cellWords(cell.value));
      if (cell.color && !cell.marked) td.style.background = cell.color;
      if (cell.ids.length) td.addEventListener('click', (event) => ctx.markHub([[words.rows, r], [words.columns, model.colKeys[j]]], cell.ids, event));
      tr.append(td);
    });
    tr.append(el('td', 'sf-table__total', cellWords(model.rowTotals[i])));
    table.append(tr);
  });
  const foot = el('tr', 'sf-table__totals');
  foot.append(el('th', 'sf-table__row', TOTAL));
  model.colTotals.forEach((v) => foot.append(el('td', 'sf-table__total', cellWords(v))));
  foot.append(el('td', 'sf-table__total', cellWords(model.total)));
  table.append(foot);
  wrap.append(table);
  const bottom = el('div', 'tb-cross__bottom');
  bottom.append(ctx.pill('cells'), ctx.plus('cells'));
  const legend = el('div', 'sf-legend');
  legend.append(ctx.legend());
  body.replaceChildren(top, left, wrap, legend, bottom);
  return { resize: () => {}, dispose: () => {} };
}

/** The title when the declaration names none - «Avg(press) per lot and product», no cell slot «Count». */
export const title = (encode) => `${encode.cells ? slotWords(encode.cells) : 'Count'} per ${slotWords(encode.rows)} and ${slotWords(encode.columns)}`;

/** The add window's picture of it: a head, a row head, cells. */
export const icon = { tone: 'cat-7', paths: [['M4 3h16v4H4zM4 9h4v12H4z', 1], ['M10 9h4v5h-4zM16 9h4v5h-4zM10 16h4v5h-4zM16 16h4v5h-4z', 0.6]] };

export const kind = { name: 'crossTable', label: 'Cross table', slots: SLOTS, title, model: crossModel, render, icon };
